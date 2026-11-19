"""CF Teacher -- algorithm-problem tutoring with an independent hidden-test judge.

The CF Teacher is the "competitive-programming / algorithm" half of the M1
Offline Teacher.  It is deliberately split from grading:

* :class:`~m1_offline.cf.judge.CFJudge` executes learner code in an isolated
  local subprocess against **hidden** tests only.
* :class:`CFTeacher` turns real judge evidence into (a) a diagnosis,
  (b) one explainable teaching action on the shared hint ladder, and (c) an
  assessment whose ``passed`` flag can only come from the independent judge.

Hard rules enforced here:

* ``assess()`` never trusts teacher text, learner self-report or a public test
  case: ``passed`` is exactly ``CFJudge.evaluate(hidden).passed`` and
  ``scorer_id`` names the independent judge.
* ``diagnose()`` uses real judge output plus the shared rule-based
  :class:`~m1_offline.diagnostics.DiagnosticEngine`; ambiguous evidence is
  returned as ``UNKNOWN`` / ``NEEDS_REVIEW`` instead of being forced into a
  category.
* ``next_action()`` delegates rung selection to the b-core
  :class:`~m1_offline.teaching_policy.AdaptivePolicy` (evidence gate, repeated
  error escalation).  It never defaults to ``FULL_SOLUTION``: without an
  explicit ``hint_level=4`` request it hard-caps the emitted rung at
  ``STRUCTURE_HINT``.
* The teacher never imports ``autoteacher_m0``, never touches the network and
  never calls a real provider.  The ``runtime`` argument is stored for
  interface compatibility only; grading and hint selection are deterministic
  and offline.

Fixtures are resolved from ``fixtures/m1/cf/problems/<id>.json`` (the hidden
ref is read from the problem fixture).  Synthetic/CC0-1.0 only.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .. import FIXTURES_DIR, load_json
from ..diagnostics import DiagnosticEngine
from ..teaching_policy import AdaptivePolicy
from ..types import (
    HINT_LADDER,
    HINT_LEVEL_MAX,
    HINT_LEVEL_MIN,
    AssessmentResult,
    DiagnosticResult,
    LearnerState,
    TeacherAction,
)
from .judge import CFJudge, JUDGE_VERSION, JudgeResult

__all__ = [
    "CFTeacher",
    "SCORER_ID",
    "CF_ERROR_CODES",
    "DEFAULT_HINT_LEVEL",
    "MAX_DEFAULT_HINT_LEVEL",
]

#: Scorer identity recorded on every :class:`AssessmentResult`; names the
#: independent hidden-test judge (never the teacher text).  Aligned with the
#: M1 evaluation protocol's independent-scorer convention.
SCORER_ID = "independent_cf_judge_v0"

#: Lowest rung of the shared hint ladder; the only default for a new learner.
DEFAULT_HINT_LEVEL = 1

#: Hard cap for evidence-driven (non-explicit) escalation: without an explicit
#: ``hint_level=4`` request the CF Teacher never emits ``FULL_SOLUTION``.
MAX_DEFAULT_HINT_LEVEL = 3

#: Error-code vocabulary emitted by the CF Teacher.  Shared b-core codes
#: (``off_by_one``, ``wrong_complexity``, ``edge_case``, ``conceptual_gap``)
#: keep their snake_case spelling; CF-specific codes are added for cases the
#: shared rule engine cannot see (syntax/import failures, process timeouts).
CF_ERROR_CODES = (
    "syntax_error",
    "runtime_error",
    "time_limit_exceeded",
    "wrong_complexity",
    "wrong_answer",
    "off_by_one",
    "edge_case",
    "conceptual_gap",
    "empty_submission",
    "fixture_error",
)

_CASE_PREFIX = re.compile(r"^case-(\d+) kind=(\w+) (raised|mismatch)\b")
_MISMATCH_VALUES = re.compile(r"expected=(.*?) actual=(.*)$")


def _stable_id(prefix: str, payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False)
    return prefix + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def _hint_kind(level: int) -> str:
    return HINT_LADDER[level - 1]


def _coerce_hint_level(hint_level: int) -> int:
    if isinstance(hint_level, bool) or not isinstance(hint_level, int):
        raise ValueError(f"hint_level must be int, got {type(hint_level).__name__}")
    if not HINT_LEVEL_MIN <= hint_level <= HINT_LEVEL_MAX:
        raise ValueError(
            f"hint_level must be within [{HINT_LEVEL_MIN}, {HINT_LEVEL_MAX}], got {hint_level}"
        )
    return hint_level


def _parse_literal(text: str) -> Any:
    try:
        return ast.literal_eval(text.strip())
    except (ValueError, SyntaxError):
        return _MISSING


class _Missing:
    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return "<missing>"


_MISSING = _Missing()


class CFTeacher:
    """Offline CF Teacher built on the independent hidden-test judge."""

    def __init__(
        self,
        runtime: Any,
        fixtures_dir: str | Path | None = None,
        judge: CFJudge | None = None,
    ) -> None:
        # ``runtime`` is accepted for interface compatibility with the shared
        # ``RuntimePort`` contract.  CF grading/hints must stay offline and
        # deterministic, so the port is never used to judge or to pick hints.
        self.runtime = runtime
        if fixtures_dir is None:
            self.fixtures_dir: Path = Path(FIXTURES_DIR) / "cf"
        else:
            self.fixtures_dir = Path(fixtures_dir)
        self.judge: CFJudge = judge if isinstance(judge, CFJudge) else CFJudge()
        self.diagnostic_engine = DiagnosticEngine()
        self.policy = AdaptivePolicy()

    # -- problem/fixture plumbing -----------------------------------------
    @staticmethod
    def _task_dict(problem: dict) -> dict:
        problem_id = problem.get("problem_id")
        if not isinstance(problem_id, str) or not problem_id.strip():
            raise ValueError("problem['problem_id'] must be a non-empty str")
        skills = problem.get("skills")
        if not isinstance(skills, list) or not skills or not all(
            isinstance(skill, str) and skill.strip() for skill in skills
        ):
            raise ValueError("problem['skills'] must be a non-empty list[str]")
        difficulty = problem.get("difficulty", 2)
        if isinstance(difficulty, bool) or not isinstance(difficulty, int):
            difficulty = 2
        return {
            "task_id": problem_id,
            "skill_ids": list(skills),
            "task_type": "CF_PROBLEM",
            "difficulty": max(1, min(5, difficulty)),
            "fixture_ref": problem_id,
        }

    def _resolve_hidden(self, problem: dict) -> dict | None:
        inline = problem.get("hidden")
        if isinstance(inline, dict) and isinstance(inline.get("tests"), list) and inline["tests"]:
            return inline
        hidden_ref = problem.get("hidden_ref")
        if not isinstance(hidden_ref, str) or not hidden_ref.strip():
            return None
        path = Path(hidden_ref)
        if not path.is_absolute():
            path = self.fixtures_dir / hidden_ref
        try:
            hidden = load_json(path)
        except (OSError, ValueError):
            return None
        if not isinstance(hidden.get("tests"), list) or not hidden["tests"]:
            return None
        return hidden

    def _problem_hint_ladder(self, problem: dict) -> dict[str, str]:
        ladder = problem.get("hint_ladder")
        if not isinstance(ladder, dict):
            return {}
        return {
            kind: value
            for kind, value in ladder.items()
            if kind in HINT_LADDER and isinstance(value, str) and value.strip()
        }

    @staticmethod
    def _submission_code(submission: dict) -> str:
        for key in ("code", "solution", "source", "answer"):
            value = submission.get(key)
            if isinstance(value, str):
                return value
        return ""

    # -- diagnosis ---------------------------------------------------------
    def diagnose(
        self, problem: dict, submission: dict, learner_state: LearnerState
    ) -> DiagnosticResult:
        """Diagnose the submission from real hidden-test judge output.

        Uses only the hidden fixture; public tests and learner self-reports are
        ignored.  Empty submissions and broken fixtures are reported as
        ``UNKNOWN`` / ``NEEDS_REVIEW`` instead of an AC verdict.
        """

        if not isinstance(problem, dict):
            raise TypeError(f"problem must be dict, got {type(problem).__name__}")
        if not isinstance(submission, dict):
            raise TypeError(f"submission must be dict, got {type(submission).__name__}")
        if not isinstance(learner_state, LearnerState):
            raise TypeError(
                f"learner_state must be LearnerState, got {type(learner_state).__name__}"
            )
        task = self._task_dict(problem)
        task_id = task["task_id"]
        code = self._submission_code(submission)
        if not code.strip():
            return DiagnosticResult(
                diagnosis_id=_stable_id("diag_", [task_id, "empty_submission"]),
                task_id=task_id,
                error_codes=["empty_submission"],
                confidence=0.2,
                status="UNKNOWN",
                explanation=(
                    "status=UNKNOWN; submission has no executable code under "
                    "submission['code']; nothing was judged, so no pass can be claimed."
                ),
                evidence_refs=[f"learner:{learner_state.learner_id}", f"problem:{task_id}"],
            )
        hidden = self._resolve_hidden(problem)
        if hidden is None:
            return DiagnosticResult(
                diagnosis_id=_stable_id("diag_", [task_id, "fixture_error"]),
                task_id=task_id,
                error_codes=["fixture_error"],
                confidence=0.1,
                status="NEEDS_REVIEW",
                explanation=(
                    "status=NEEDS_REVIEW; hidden fixture could not be loaded from "
                    f"problem['hidden_ref']={problem.get('hidden_ref')!r}; no judgment is possible."
                ),
                evidence_refs=[f"problem:{task_id}"],
            )
        result = self.judge.evaluate(problem, hidden, code)
        return self._diagnose_from_result(problem, task, learner_state, hidden, result, code)

    def _diagnose_from_result(
        self,
        problem: dict,
        task: dict,
        learner_state: LearnerState,
        hidden: dict,
        result: JudgeResult,
        code: str,
    ) -> DiagnosticResult:
        task_id = task["task_id"]
        refs = [
            f"hidden:{task_id}",
            f"judge:{JUDGE_VERSION}",
            f"cases:{result.cases_passed}/{result.cases_total}",
        ]

        # 1) Fail-closed process-level outcomes (no case evidence at all).
        if result.error in {"syntax_error", "import_error", "missing_function"}:
            code = "syntax_error" if result.error == "syntax_error" else "runtime_error"
            detail = result.failures[0] if result.failures else result.error
            return DiagnosticResult(
                diagnosis_id=_stable_id("diag_", [task_id, code, detail]),
                task_id=task_id,
                error_codes=[code],
                confidence=0.95 if code == "syntax_error" else 0.9,
                status="RESOLVED",
                explanation=(
                    f"status=RESOLVED; hidden execution failed closed ({result.error}): {detail}; "
                    f"cases_passed=0/{result.cases_total}."
                ),
                evidence_refs=refs,
            )
        if result.error == "timeout":
            return self._diagnose_timeout(problem, task, code, hidden, refs)
        if result.error is not None:
            return DiagnosticResult(
                diagnosis_id=_stable_id("diag_", [task_id, "fixture_error", result.error]),
                task_id=task_id,
                error_codes=["fixture_error"],
                confidence=0.1,
                status="NEEDS_REVIEW",
                explanation=(
                    f"status=NEEDS_REVIEW; judge infrastructure error {result.error!r}; "
                    "the learner's code was not reliably observed, so no classification is asserted."
                ),
                evidence_refs=refs,
            )

        # 2) Independent judge says all hidden cases passed: the only AC source.
        if result.passed:
            return DiagnosticResult(
                diagnosis_id=_stable_id("diag_", [task_id, "ac", result.cases_total]),
                task_id=task_id,
                error_codes=[],
                confidence=1.0,
                status="RESOLVED",
                explanation=(
                    f"status=RESOLVED; independent hidden judge passed all "
                    f"{result.cases_passed}/{result.cases_total} cases; no error codes."
                ),
                evidence_refs=refs,
            )

        # 3) Completed run with wrong answers / per-case exceptions.
        parsed = self._parse_failures(result.failures)
        tests = hidden["tests"]
        failed_indexes = {item["index"] for item in parsed if item["index"] is not None}
        exception_count = sum(1 for item in parsed if item["mode"] == "raised")
        failed_kinds = {
            (tests[item["index"]].get("kind", "normal") if item["index"] is not None else "normal")
            for item in parsed
        }
        edge_total = sum(1 for case in tests if case.get("kind") == "edge")
        edge_fail = sum(
            1
            for item in parsed
            if item["index"] is not None and tests[item["index"]].get("kind") == "edge"
        )

        case_results: list[dict] = []
        for index, case in enumerate(tests):
            case_results.append(
                {
                    "case_id": f"case-{index:02d}",
                    "passed": index not in failed_indexes,
                    "is_edge_case": case.get("kind") == "edge",
                }
            )
        engine_submission = {
            "passed": False,
            "case_results": case_results,
            "evidence_refs": list(refs),
        }
        engine_result = self.diagnostic_engine.diagnose(task, engine_submission, learner_state)
        codes: list[str] = list(engine_result.error_codes)
        reasons: list[str] = [engine_result.explanation]

        if exception_count:
            if "runtime_error" not in codes:
                codes.append("runtime_error")
            reasons.append(
                f"{exception_count}/{len(parsed)} failing hidden case(s) raised an exception"
            )
        mismatch_count = len(parsed) - exception_count
        if mismatch_count or not parsed:
            if "off_by_one" not in codes and self._has_off_by_one(result.failures):
                codes.append("off_by_one")
                reasons.append("at least one failing case differs from expected by exactly 1")
        if "edge_case" in codes:
            reasons.append(
                f"{edge_fail}/{edge_total} edge-tagged hidden case(s) failed while other cases passed"
            )
        if not codes and mismatch_count:
            codes.append("wrong_answer")
            reasons.append(
                f"{len(failed_indexes)}/{result.cases_total} hidden case(s) failed with wrong output"
            )
        elif mismatch_count and not (set(codes) & {"edge_case", "off_by_one", "conceptual_gap"}):
            if "wrong_answer" not in codes:
                codes.append("wrong_answer")

        # Dedupe preserving order; never invent codes outside the vocabulary.
        codes = [code for code in dict.fromkeys(codes) if code in CF_ERROR_CODES]

        needs_review = engine_result.status == "NEEDS_REVIEW"
        if needs_review and not codes:
            return DiagnosticResult(
                diagnosis_id=_stable_id(
                    "diag_", [task_id, "needs_review", result.cases_passed, result.cases_total]
                ),
                task_id=task_id,
                error_codes=[],
                confidence=0.35,
                status="NEEDS_REVIEW",
                explanation=(
                    "status=NEEDS_REVIEW; failures were observed but no rule could classify them; "
                    + "; ".join(reasons)
                ),
                evidence_refs=refs,
            )
        confidence = self._diagnosis_confidence(codes, engine_result.confidence, needs_review)
        status = "NEEDS_REVIEW" if (needs_review and not codes) else "RESOLVED"
        explanation = (
            f"status={status}; failed_kinds={sorted(failed_kinds)}; "
            f"cases_passed={result.cases_passed}/{result.cases_total}; "
            + "; ".join(reason for reason in reasons if reason)
        )
        return DiagnosticResult(
            diagnosis_id=_stable_id(
                "diag_", [task_id, codes, result.cases_passed, result.cases_total, failed_kinds]
            ),
            task_id=task_id,
            error_codes=codes,
            confidence=confidence,
            status=status,
            explanation=explanation,
            evidence_refs=refs,
        )

    def _diagnose_timeout(
        self,
        problem: dict,
        task: dict,
        code: str,
        hidden: dict,
        refs: list[str],
    ) -> DiagnosticResult:
        """Distinguish an algorithmic complexity problem from a general hang.

        Real judge evidence only: the same submission is re-run against the
        non-large hidden cases under a bounded budget.  If those cases pass but
        the full run timed out, the failure is attributable to the large case
        (asymptotic cost); if the small run also times out, the submission hangs
        outright.
        """

        small_tests = [case for case in hidden["tests"] if case.get("kind") != "large"]
        small_probe = None
        if small_tests:
            probe_timeout = min(
                0.5, float(hidden.get("timeout_s") or self.judge.timeout_s)
            )
            probe_hidden = {
                "schema_version": hidden.get("schema_version"),
                "problem_id": hidden.get("problem_id"),
                "timeout_s": probe_timeout,
                "tests": small_tests,
            }
            small_probe = self.judge.evaluate(problem, probe_hidden, code)
        return self._timeout_diagnosis(task, hidden, small_probe, refs)

    def _timeout_diagnosis(
        self,
        task: dict,
        hidden: dict,
        small_probe: JudgeResult | None,
        refs: list[str],
    ) -> DiagnosticResult:
        task_id = task["task_id"]
        if small_probe is not None and small_probe.passed:
            codes = ["wrong_complexity"]
            confidence = 0.8
            detail = (
                "passes all small/edge hidden cases but exceeds the wall-clock budget on the "
                "large hidden case, which is evidence of an asymptotically too-slow solution"
            )
        else:
            codes = ["time_limit_exceeded"]
            confidence = 0.7
            detail = "hidden execution exceeded the wall-clock budget before completing any case"
        return DiagnosticResult(
            diagnosis_id=_stable_id("diag_", [task_id, codes, "timeout"]),
            task_id=task_id,
            error_codes=codes,
            confidence=confidence,
            status="RESOLVED",
            explanation=f"status=RESOLVED; {detail}.",
            evidence_refs=refs,
        )

    @staticmethod
    def _parse_failures(failures: list[str]) -> list[dict]:
        parsed: list[dict] = []
        for failure in failures:
            match = _CASE_PREFIX.match(failure)
            if match is None:
                parsed.append({"index": None, "kind": "unknown", "mode": "unknown"})
                continue
            parsed.append(
                {
                    "index": int(match.group(1)),
                    "kind": match.group(2),
                    "mode": match.group(3),
                }
            )
        return parsed

    @staticmethod
    def _has_off_by_one(failures: list[str]) -> bool:
        """True only when *every* observable mismatch is a numeric difference of 1.

        Conservative by construction: unparseable/non-numeric/truncated failures
        make the answer ``False`` so a single ±1 coincidence cannot mask a broad
        wrong-answer failure.
        """

        saw_mismatch = False
        for failure in failures:
            if "mismatch:" not in failure:
                continue
            saw_mismatch = True
            match = _MISMATCH_VALUES.search(failure)
            if match is None:
                return False
            expected = _parse_literal(match.group(1))
            actual = _parse_literal(match.group(2))
            if isinstance(expected, bool) or isinstance(actual, bool):
                return False
            if not isinstance(expected, (int, float)) or not isinstance(
                actual, (int, float)
            ):
                return False
            if abs(float(expected) - float(actual)) != 1.0:
                return False
        return saw_mismatch

    @staticmethod
    def _diagnosis_confidence(codes: list[str], engine_confidence: float, needs_review: bool) -> float:
        if not codes:
            return 0.35
        specificity = {
            "syntax_error": 0.95,
            "runtime_error": 0.85,
            "wrong_complexity": 0.8,
            "time_limit_exceeded": 0.7,
            "off_by_one": 0.8,
            "edge_case": 0.8,
            "wrong_answer": 0.7,
            "conceptual_gap": 0.65,
        }
        best = max(specificity.get(code, 0.5) for code in codes)
        confidence = max(best, min(0.9, engine_confidence))
        if needs_review:
            confidence = min(confidence, 0.6)
        return round(min(0.95, confidence), 3)

    # -- teaching action ---------------------------------------------------
    def next_action(
        self,
        problem: dict,
        learner_state: LearnerState,
        hint_level: int | None = None,
    ) -> TeacherAction:
        """Choose one explainable teaching action on the shared hint ladder.

        Rung selection is delegated to the b-core ``AdaptivePolicy`` (evidence
        gate + repeated-error escalation).  Without an explicit
        ``hint_level=4`` request the emitted level is hard-capped at
        ``STRUCTURE_HINT``, so ``FULL_SOLUTION`` is never a default.
        """

        if not isinstance(problem, dict):
            raise TypeError(f"problem must be dict, got {type(problem).__name__}")
        if not isinstance(learner_state, LearnerState):
            raise TypeError(
                f"learner_state must be LearnerState, got {type(learner_state).__name__}"
            )
        task = self._task_dict(problem)
        skills = task["skill_ids"]

        explicit = hint_level is not None
        if explicit:
            requested = _coerce_hint_level(hint_level)  # type: ignore[arg-type]
            allow_full_solution = requested == HINT_LEVEL_MAX
        else:
            requested = DEFAULT_HINT_LEVEL
            # Error history may be keyed by skill (hand-seeded states) or by
            # error code (b-core LearnerModel counts codes); both are real
            # evidence, so escalate on the stronger of the two signals.
            repeated = sum(learner_state.error_counts.get(skill, 0) for skill in skills)
            repeated = max(
                repeated,
                sum(
                    learner_state.error_counts.get(code, 0) for code in CF_ERROR_CODES
                ),
            )
            if repeated >= 4:
                requested = 3
            elif repeated >= 2:
                requested = 2
            allow_full_solution = False

        policy_action = self.policy.choose(task, learner_state, None, requested)
        ladder = self._problem_hint_ladder(problem)
        evidence_refs = [f"learner:{learner_state.learner_id}"]
        evidence_refs.append(f"policy:{self.policy.policy_version}")
        evidence_refs.append(f"requested:L{requested}")
        for skill in skills:
            count = learner_state.error_counts.get(skill, 0)
            if count:
                evidence_refs.append(f"skill-error:{skill}={count}")

        # Safety clamp: an evidence-driven escalation may never default to the
        # worked solution; only an explicit hint_level=4 request passes through
        # (and even then the b-core EvidenceGate caps it when evidence is thin).
        if (
            policy_action.hint_level is not None
            and policy_action.hint_level > MAX_DEFAULT_HINT_LEVEL
            and not allow_full_solution
        ):
            content = ladder.get("STRUCTURE_HINT") or policy_action.content
            clamped = TeacherAction(
                action_id=_stable_id(
                    "act_", [task["task_id"], "cf-clamp", "STRUCTURE_HINT", learner_state.evidence_count]
                ),
                kind="STRUCTURE_HINT",
                content=content,
                rationale=(
                    f"{policy_action.rationale} CFTeacher safety clamp: FULL_SOLUTION never by "
                    f"default (requested L{requested}, emitted L{MAX_DEFAULT_HINT_LEVEL} STRUCTURE_HINT)."
                ),
                hint_level=MAX_DEFAULT_HINT_LEVEL,
                target_skill_ids=list(skills),
                evidence_refs=evidence_refs,
            )
            return clamped

        if policy_action.kind in HINT_LADDER and policy_action.hint_level is not None:
            kind = policy_action.kind
            content = ladder.get(kind) or policy_action.content
            rationale = (
                f"{policy_action.rationale}; CFTeacher rendered problem-specific hint "
                f"content from problem.hint_ladder[{kind}]."
            )
            return TeacherAction(
                action_id=policy_action.action_id,
                kind=kind,
                content=content,
                rationale=rationale,
                hint_level=policy_action.hint_level,
                target_skill_ids=list(dict.fromkeys(policy_action.target_skill_ids or skills)),
                evidence_refs=evidence_refs,
            )

        # Non-hint actions (e.g. REVIEW from the shared policy) pass through.
        return TeacherAction(
            action_id=policy_action.action_id,
            kind=policy_action.kind,
            content=policy_action.content,
            rationale=policy_action.rationale,
            hint_level=policy_action.hint_level,
            target_skill_ids=list(dict.fromkeys(policy_action.target_skill_ids or skills)),
            evidence_refs=evidence_refs,
        )

    # -- assessment --------------------------------------------------------
    def assess(
        self,
        problem: dict,
        submission: dict,
        learner_state: LearnerState,
    ) -> AssessmentResult:
        """Assess a submission with the independent hidden-test judge.

        ``passed`` is exactly the judge verdict; learner claims such as
        ``submission["passed"] = True`` are ignored, and public tests never
        contribute to the score.
        """

        if not isinstance(problem, dict):
            raise TypeError(f"problem must be dict, got {type(problem).__name__}")
        if not isinstance(submission, dict):
            raise TypeError(f"submission must be dict, got {type(submission).__name__}")
        if not isinstance(learner_state, LearnerState):
            raise TypeError(
                f"learner_state must be LearnerState, got {type(learner_state).__name__}"
            )
        task = self._task_dict(problem)
        task_id = task["task_id"]
        learner_id = learner_state.learner_id
        code = self._submission_code(submission)
        hidden = self._resolve_hidden(problem)
        if hidden is None:
            return AssessmentResult(
                assessment_id=_stable_id("asmt_", [task_id, learner_id, "fixture_error"]),
                task_id=task_id,
                learner_id=learner_id,
                scorer_id=SCORER_ID,
                passed=False,
                score=0.0,
                dimensions={"correctness": 0.0, "edge_case_accuracy": 0.0, "efficiency": 0.0},
                failure_modes=["fixture_error"],
                hidden_cases_passed=0,
                hidden_cases_total=0,
            )
        result = self.judge.evaluate(problem, hidden, code)
        total = result.cases_total
        correctness = (result.cases_passed / total) if total else 0.0
        diagnostics = self._diagnose_from_result(
            problem, task, learner_state, hidden, result, code
        )
        failure_modes = list(diagnostics.error_codes)
        if not result.passed and not failure_modes:
            failure_modes = ["unclassified_failure"]
        parsed = self._parse_failures(result.failures)
        tests = hidden["tests"]
        failed_index = {item["index"] for item in parsed if item["index"] is not None}
        edge_total = sum(1 for case in tests if case.get("kind") == "edge")
        edge_failed = sum(
            1
            for index in failed_index
            if isinstance(index, int) and index < len(tests) and tests[index].get("kind") == "edge"
        )
        if result.error is not None:
            edge_accuracy = 0.0
            efficiency = 0.0
        else:
            edge_accuracy = ((edge_total - edge_failed) / edge_total) if edge_total else 1.0
            efficiency = 0.0 if result.error == "timeout" else 1.0
        dimensions = {
            "correctness": round(correctness, 6),
            "edge_case_accuracy": round(edge_accuracy, 6),
            "efficiency": round(efficiency, 6),
        }
        return AssessmentResult(
            assessment_id=_stable_id(
                "asmt_",
                [task_id, learner_id, code, result.cases_passed, result.cases_total, result.error],
            ),
            task_id=task_id,
            learner_id=learner_id,
            scorer_id=SCORER_ID,
            passed=bool(result.passed),
            score=round(correctness, 6),
            dimensions=dimensions,
            failure_modes=failure_modes,
            hidden_cases_passed=result.cases_passed if result.error is None else 0,
            hidden_cases_total=total,
        )
