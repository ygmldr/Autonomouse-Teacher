"""Rule-based diagnostic engine (M1 Teacher Core, offline/mock only).

The engine classifies a synthetic submission against a synthetic task into
auditable :class:`~m1_offline.types.DiagnosticResult` records.  It is
deliberately a **rule engine**, not a model: every emitted error code must be
justified by an explicit signal in the task/submission/learner state, and
anything ambiguous is returned as ``UNKNOWN`` or ``NEEDS_REVIEW`` instead of
being silently forced into a category.

Known error codes (shared vocabulary):

* ``off_by_one`` -- output differs by exactly one, or an index-boundary error
  is reported (``IndexError`` / "off-by-one").
* ``wrong_complexity`` -- declared complexity is asymptotically worse than the
  task requirement (``O(n^2)`` vs ``O(n)`` etc.).
* ``wrong_data_structure`` -- submission structure differs from the required
  structure.
* ``edge_case`` -- only edge/empty/single-element cases fail.
* ``conceptual_gap`` -- repeated error history on the task skills plus broad
  visible-case failure; the learner appears to miss the underlying concept.

Input conventions (both are synthetic fixture dicts, never real learner data)::

    task = {"task_id": str, "skill_ids": [str], "expected_output": Any?,
            "expected_complexity": "O(n)"?, "expected_data_structure": "dict"?,
            "edge_case_ids": [str]?}
    submission = {"output": Any?, "passed": bool?, "error_codes": [str]?,
                  "error_message": str?, "code": str?,
                  "complexity"/"time_complexity": "O(n)"?,
                  "data_structure": "dict"?,
                  "case_results": [{"case_id": str, "passed": bool,
                                    "is_edge_case": bool?, "expected": Any?,
                                    "actual": Any?}],
                  "evidence_refs": [str]?}

Status semantics: ``RESOLVED`` -- at least one known cause identified with no
conflicting signals; ``NEEDS_REVIEW`` -- signals conflict, failures are
unclassified, or an unknown error code was supplied; ``UNKNOWN`` -- no usable
signal at all.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .types import DiagnosticResult, LearnerState

__all__ = ["DiagnosticEngine", "KNOWN_ERROR_CODES", "COMPLEXITY_RANK"]

#: Error codes the rule engine may emit.
KNOWN_ERROR_CODES = (
    "off_by_one",
    "wrong_complexity",
    "wrong_data_structure",
    "edge_case",
    "conceptual_gap",
)

#: Asymptotic ranks: higher means worse.  Unknown labels are not rankable.
COMPLEXITY_RANK = {
    "O(1)": 0,
    "O(log n)": 1,
    "O(log(n))": 1,
    "O(n)": 2,
    "O(n log n)": 3,
    "O(nlog n)": 3,
    "O(n^2)": 4,
    "O(n²)": 4,
    "O(n^3)": 5,
    "O(2^n)": 6,
    "O(2n)": 6,
    "O(n!)": 7,
}

_ERROR_MESSAGE_HINTS = (
    ("off-by-one", "off_by_one"),
    ("off by one", "off_by_one"),
    ("indexerror", "off_by_one"),
    ("index out of range", "off_by_one"),
    ("time limit", "wrong_complexity"),
    ("timed out", "wrong_complexity"),
    ("tle", "wrong_complexity"),
    ("set(", "wrong_data_structure"),
    ("dict(", "wrong_data_structure"),
    ("empty", "edge_case"),
    ("null", "edge_case"),
    ("none", "edge_case"),
    ("misconception", "conceptual_gap"),
    ("conceptual", "conceptual_gap"),
)


def _digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.lower()
    return str(value).lower()


def _numeric(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


class DiagnosticEngine:
    """Deterministic rule-based diagnostic engine."""

    def diagnose(
        self,
        task: dict,
        submission: dict,
        learner_state: LearnerState,
    ) -> DiagnosticResult:
        if not isinstance(task, dict):
            raise TypeError(f"task must be dict, got {type(task).__name__}")
        if not isinstance(submission, dict):
            raise TypeError(f"submission must be dict, got {type(submission).__name__}")
        if not isinstance(learner_state, LearnerState):
            raise TypeError(
                f"learner_state must be LearnerState, got {type(learner_state).__name__}"
            )

        task_id = task.get("task_id") or submission.get("task_id")
        if not isinstance(task_id, str) or not task_id.strip():
            raise ValueError("task['task_id'] must be a non-empty str")
        skill_ids = task.get("skill_ids", [])
        if isinstance(skill_ids, str):
            skill_ids = [skill_ids]
        if not isinstance(skill_ids, list) or not all(
            isinstance(skill, str) for skill in skill_ids
        ):
            raise ValueError("task['skill_ids'] must be list[str]")

        codes: list[str] = []
        reasons: list[str] = []
        unknown_codes: list[str] = []
        conflicting = False

        def add(code: str, reason: str) -> None:
            if code not in codes:
                codes.append(code)
                reasons.append(f"{code}: {reason}")

        # 1) Explicit error codes supplied by the caller/fixture.
        explicit_codes = submission.get("error_codes")
        if explicit_codes is not None:
            if not isinstance(explicit_codes, list) or not all(
                isinstance(code, str) for code in explicit_codes
            ):
                raise ValueError("submission['error_codes'] must be list[str]")
            for code in explicit_codes:
                if code in KNOWN_ERROR_CODES:
                    add(code, "explicitly supplied by submission.error_codes")
                else:
                    unknown_codes.append(code)

        # 2) Visible case results.
        case_results = submission.get("case_results")
        if case_results is not None:
            if not isinstance(case_results, list) or not all(
                isinstance(case, dict) for case in case_results
            ):
                raise ValueError("submission['case_results'] must be list[dict]")
        else:
            case_results = []
        passed_cases = sum(1 for case in case_results if case.get("passed") is True)
        failed_cases = [case for case in case_results if case.get("passed") is not True]
        if case_results and not failed_cases and not explicit_codes:
            add("__all_cases_passed__", "all visible cases passed")

        # 3) off_by_one: numeric output difference of exactly one.
        expected_output = task.get("expected_output")
        actual_output = submission.get("output")
        expected_number = _numeric(expected_output)
        actual_number = _numeric(actual_output)
        if (
            expected_number is not None
            and actual_number is not None
            and abs(expected_number - actual_number) == 1.0
        ):
            add(
                "off_by_one",
                f"output {actual_number!r} differs from expected {expected_number!r} by exactly 1",
            )
        for position, case in enumerate(failed_cases):
            case_expected = _numeric(case.get("expected"))
            case_actual = _numeric(case.get("actual"))
            if (
                case_expected is not None
                and case_actual is not None
                and abs(case_expected - case_actual) == 1.0
            ):
                add("off_by_one", f"failing case #{position} differs from expected by exactly 1")

        # 4) wrong_complexity: asymptotic rank worse than required.
        required_complexity = task.get("expected_complexity")
        submitted_complexity = submission.get("complexity") or submission.get("time_complexity")
        if isinstance(required_complexity, str) and isinstance(submitted_complexity, str):
            required_rank = COMPLEXITY_RANK.get(required_complexity.strip())
            submitted_rank = COMPLEXITY_RANK.get(submitted_complexity.strip())
            if (
                required_rank is not None
                and submitted_rank is not None
                and submitted_rank > required_rank
            ):
                add(
                    "wrong_complexity",
                    f"submitted {submitted_complexity!r} is worse than required "
                    f"{required_complexity!r}",
                )

        # 5) wrong_data_structure.
        required_structure = task.get("expected_data_structure")
        submitted_structure = submission.get("data_structure")
        if isinstance(required_structure, str) and isinstance(submitted_structure, str):
            if required_structure.strip() != submitted_structure.strip():
                add(
                    "wrong_data_structure",
                    f"submitted {submitted_structure!r} != required {required_structure!r}",
                )

        # 6) edge_case: all failures are edge-tagged, or only edge cases fail.
        edge_case_ids = task.get("edge_case_ids") or []
        edge_case_ids = set(edge_case_ids) if isinstance(edge_case_ids, list) else set()
        if failed_cases and len(failed_cases) < len(case_results):
            failing_edge = [
                case
                for case in failed_cases
                if case.get("is_edge_case") is True or case.get("case_id") in edge_case_ids
            ]
            if len(failing_edge) == len(failed_cases):
                add(
                    "edge_case",
                    f"all {len(failed_cases)} failing visible case(s) are edge cases",
                )
        if failed_cases and len(failed_cases) == len(case_results):
            failing_edge = [
                case
                for case in failed_cases
                if case.get("is_edge_case") is True or case.get("case_id") in edge_case_ids
            ]
            if failing_edge and len(failing_edge) == len(failed_cases):
                add("edge_case", "every visible failing case is edge-tagged")

        # 7) error message keyword mapping.
        message = _as_text(submission.get("error_message"))
        if message:
            for needle, code in _ERROR_MESSAGE_HINTS:
                if needle in message:
                    add(code, f"error_message contains {needle!r}")
                    break

        # 8) explicit passed flag and conflict detection.
        passed_flag = submission.get("passed")
        if passed_flag is not None and not isinstance(passed_flag, bool):
            raise ValueError("submission['passed'] must be bool when present")
        if passed_flag is True and (failed_cases or explicit_codes):
            conflicting = True
            reasons.append(
                "conflict: submission.passed=True but failures/explicit error codes present"
            )
        if passed_flag is False and case_results and not failed_cases:
            conflicting = True
            reasons.append(
                "conflict: submission.passed=False but every visible case passed"
            )

        # 9) conceptual_gap from repeated error history + broad failure.
        # ``LearnerModel`` counts error codes, so accept both keyings: error-code
        # keys and per-skill keys, whichever yields the larger history signal.
        skill_history = sum(learner_state.error_counts.get(skill, 0) for skill in skill_ids)
        code_history = sum(learner_state.error_counts.values())
        history = max(skill_history, code_history)
        if case_results:
            visible_fail_ratio = len(failed_cases) / len(case_results)
        elif passed_flag is False:
            visible_fail_ratio = 1.0
        else:
            visible_fail_ratio = 0.0
        if history >= 2 and visible_fail_ratio >= 0.5 and "conceptual_gap" not in codes:
            add(
                "conceptual_gap",
                f"repeated error history on task skills (count={history}) and "
                f"{visible_fail_ratio:.0%} of visible cases failing",
            )

        if conflicting:
            status = "NEEDS_REVIEW"
        elif passed_flag is True and not failed_cases and not explicit_codes:
            codes = []
            reasons = ["submission.passed=True with no conflicting failures"]
            status = "RESOLVED"
        elif case_results and not failed_cases and passed_flag is not False:
            codes = []
            reasons = ["all visible cases passed and submission not marked failed"]
            status = "RESOLVED"
        elif unknown_codes:
            status = "NEEDS_REVIEW"
            reasons.append(f"unclassified error code(s): {sorted(set(unknown_codes))}")
        elif codes:
            status = "RESOLVED"
        elif failed_cases or passed_flag is False:
            status = "NEEDS_REVIEW"
            reasons.append("failures observed but no rule classified them")
        else:
            status = "UNKNOWN"
            reasons.append("no usable classification signal in task/submission/learner state")

        if status == "RESOLVED":
            confidence = max(0.5, 0.9 - 0.1 * max(0, len(codes) - 1))
        elif status == "NEEDS_REVIEW":
            confidence = 0.4
        else:
            confidence = 0.25

        explanation = "; ".join(reasons) if reasons else "no signals"
        evidence_refs = submission.get("evidence_refs", [])
        if evidence_refs is None:
            evidence_refs = []
        if not isinstance(evidence_refs, list) or not all(
            isinstance(ref, str) for ref in evidence_refs
        ):
            raise ValueError("submission['evidence_refs'] must be list[str]")
        evidence_refs = list(dict.fromkeys(evidence_refs))

        diagnosis_id = "diag_" + _digest(
            [task_id, submission, learner_state.evidence_count, sorted(codes), sorted(unknown_codes)]
        )[:16]
        return DiagnosticResult(
            diagnosis_id=diagnosis_id,
            task_id=task_id,
            error_codes=codes + sorted(set(unknown_codes)),
            confidence=round(confidence, 3),
            status=status,
            explanation=f"status={status}; " + explanation,
            evidence_refs=evidence_refs,
        )
