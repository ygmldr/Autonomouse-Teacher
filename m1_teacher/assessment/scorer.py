"""Independent deterministic assessment scorer for the M1-A teacher (B-PR4).

Purpose
-------
The scorer is the **only** component allowed to read hidden evaluation material
(``fixtures/m1_teacher/domains/<domain_id>/scoring/<item_id>.json``).  It turns
a learner submission into a frozen
:class:`~m1_teacher.contracts.types.AssessmentResult` that the teaching session
engine consumes as *observed evidence*; teacher-visible code never sees hidden
tests, expected outputs or correct option indices.

Evidence rules (fail-closed)
----------------------------
* ``CORRECT`` / ``INCORRECT`` / ``PARTIAL`` are **student outcomes**: wrong
  answers, syntax errors, runtime exceptions, timeouts and missing functions in
  learner code are graded as ``INCORRECT``/``PARTIAL`` with a *generic*
  ``failure_reason`` (counts / error class only, never hidden test content).
* ``EVAL_ERROR`` is reserved for **scoring infrastructure / policy** failures:
  missing or corrupted scoring spec, path-escape in ``scoring_spec_ref``,
  worker protocol violations, unavailable OS sandbox, or the default
  ``UNTRUSTED_CODE_EXECUTION_BLOCKED`` policy.  An ``EVAL_ERROR`` is never
  evidence about the learner and must never lower mastery or record an error
  (the session engine enforces that separation).
* ``NEEDS_REVIEW`` is used for open-ended ``SHORT_ANSWER`` responses whose
  semantic evidence cannot be verified deterministically.  A semantic rubric
  can award at most ``PARTIAL`` credit; a plain string match can never yield
  ``CORRECT``.

Isolation
---------
``CODE`` items never execute learner code in the teacher process.  The scorer
only builds the trusted test list (``args``/``expected`` from the hidden
scoring spec) and delegates execution to
:class:`~m1_teacher.assessment.judge.supervisor.TrustedJudgeSupervisor`, which
compares the untrusted worker's observed actual value against its own expected
value.  By default learner CODE is **not executed at all**: the result is a
fail-closed ``EVAL_ERROR`` with ``failure_reason``
``UNTRUSTED_CODE_EXECUTION_BLOCKED`` and the learner state must not change.
Only the explicit synthetic CI opt-in ``trusted_fixture_only=True`` enables the
worker path; if the worker/OS sandbox is unavailable it also fails closed with
the same blocked classification and *never* falls back to an in-process or bare
subprocess runner.  MCQ / SHORT_ANSWER grading does not use a worker and is
unaffected by the policy.

Determinism
-----------
Scoring is a pure function of ``(item, learner_id, response, result_id)``;
randomness, network access and wall-clock reads are absent from the decision.
The ``created_at`` timestamp is metadata only and may be injected through the
``clock`` test hook for byte-identical replays.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from ..contracts.errors import ValidationError
from ..contracts.types import (
    ASSESSMENT_STATUS_VALUES,
    AssessmentItem,
    AssessmentResult,
    now_utc,
)
from .judge.supervisor import (
    STATUS_JUDGE_INFRA_ERROR,
    STATUS_JUDGE_SANDBOX_UNAVAILABLE,
    STATUS_PASS,
    STATUS_RE,
    STATUS_TLE,
    STATUS_UNTRUSTED_CODE_EXECUTION_BLOCKED,
    JudgeVerdict,
    TrustedJudgeSupervisor,
)

__all__ = [
    "AssessmentScorer",
    "DeterministicScorer",
    "SCORER_ID_DEFAULT",
]

SCORER_ID_DEFAULT = "m1a.deterministic.scorer.v0"

_MUTATING_STATUSES = frozenset({"CORRECT", "INCORRECT", "PARTIAL"})
_SCORING_DIR_NAME = "scoring"
_DEFAULT_TIMEOUT_S = 2.0
# Aligned with TrustedJudgeSupervisor/worker MAX_CASE_TIMEOUT_S=5.0 (review P2-10).
_MAX_TIMEOUT_S = 5.0
_MIN_RESPONSE_CHARS = 8
_MAX_RUBRIC_GROUPS = 32


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _require_nonempty_str(value: Any, where: str) -> str:
    if type(value) is not str or not value.strip():
        raise ValidationError(f"{where}: expected a non-blank string")
    return value


def _canonical(value: Any) -> str:
    """Canonical JSON representation used for comparison and result ids."""

    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class _ScorerInfrastructureError(Exception):
    """Internal marker: scoring infrastructure failed -> ``EVAL_ERROR``."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


#: Marker raised when CODE execution is disabled by policy (no learner code ran).
UNTRUSTED_CODE_EXECUTION_BLOCKED = STATUS_UNTRUSTED_CODE_EXECUTION_BLOCKED


class _AssessmentBlocked(Exception):
    """Internal marker: CODE execution is disabled / sandbox unavailable."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class _JudgeInfrastructureFailure(Exception):
    """Internal marker: trusted judge could not obtain a trustworthy observation."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@runtime_checkable
class AssessmentScorer(Protocol):
    """Structural contract of an independent assessment scorer.

    ``score`` must be deterministic for identical inputs, must not consult
    teacher text/session state and must return an ``AssessmentResult`` whose
    ``scorer_id`` names this scorer.
    """

    scorer_id: str

    def score(
        self,
        item: AssessmentItem,
        learner_id: str,
        response: str | dict,
        *,
        result_id: str | None = None,
    ) -> AssessmentResult:
        """Score one submission against the hidden scoring specification."""


# ---------------------------------------------------------------------------
# Deterministic scorer
# ---------------------------------------------------------------------------


class DeterministicScorer:
    """Deterministic, offline scorer for MCQ / CODE / SHORT_ANSWER items."""

    def __init__(
        self,
        fixtures_root: str | Path | None = None,
        *,
        timeout_s: float = _DEFAULT_TIMEOUT_S,
        scorer_id: str = SCORER_ID_DEFAULT,
        clock: Callable[[], str] | None = None,
        trusted_fixture_only: bool = False,
        judge_worker: Any = None,
    ) -> None:
        if fixtures_root is None:
            from ..domains.cf_binary_search import default_fixtures_root

            root = default_fixtures_root()
        else:
            root = self._coerce_root(fixtures_root)
        if type(timeout_s) not in (int, float):
            raise ValidationError("DeterministicScorer(timeout_s): expected a number")
        timeout = float(timeout_s)
        if not 0.0 < timeout <= _MAX_TIMEOUT_S:
            raise ValidationError(
                f"DeterministicScorer(timeout_s): expected 0 < timeout <= {_MAX_TIMEOUT_S}"
            )
        scorer_id = _require_nonempty_str(scorer_id, "DeterministicScorer(scorer_id)")
        if clock is not None and not callable(clock):
            raise ValidationError("DeterministicScorer(clock): expected a callable or None")
        if not isinstance(trusted_fixture_only, bool):
            raise ValidationError(
                "DeterministicScorer(trusted_fixture_only): expected a bool"
            )
        if judge_worker is not None and not callable(getattr(judge_worker, "run_case", None)):
            raise ValidationError(
                "DeterministicScorer(judge_worker=...): expected an object with run_case()"
            )
        self._fixtures_root = root
        self._timeout_s = timeout
        self._scorer_id = scorer_id
        self._clock: Callable[[], str] = clock if clock is not None else now_utc
        # Learner CODE execution is fail-closed by default.  The synthetic CI
        # opt-in only enables the trusted-supervisor -> untrusted-worker path.
        self._trusted_fixture_only = trusted_fixture_only
        self._judge_worker = judge_worker
        self._supervisor: TrustedJudgeSupervisor | None = None

    # -- properties --------------------------------------------------------
    @property
    def scorer_id(self) -> str:
        return self._scorer_id

    @property
    def fixtures_root(self) -> Path:
        return self._fixtures_root

    @property
    def timeout_s(self) -> float:
        return self._timeout_s

    @property
    def trusted_fixture_only(self) -> bool:
        return self._trusted_fixture_only

    @property
    def judge_worker(self) -> Any:
        return self._judge_worker

    def _get_supervisor(self) -> TrustedJudgeSupervisor:
        if self._supervisor is None:
            self._supervisor = TrustedJudgeSupervisor(
                self._judge_worker,
                timeout_s=self._timeout_s,
                trusted_fixture_only=True,
            )
        return self._supervisor

    # -- public API --------------------------------------------------------
    def score(
        self,
        item: AssessmentItem,
        learner_id: str,
        response: str | dict,
        *,
        result_id: str | None = None,
    ) -> AssessmentResult:
        """Score ``response`` against the hidden spec of ``item`` (fail-closed)."""

        item = self._validate_item(item)
        learner_id = _require_nonempty_str(learner_id, "DeterministicScorer.score(learner_id)")
        if result_id is not None:
            result_id = _require_nonempty_str(
                result_id, "DeterministicScorer.score(result_id)"
            )
        max_score = float(item.max_score) if item.max_score > 0.0 else 1.0
        rid = result_id or self._default_result_id(item, response)
        try:
            spec, _spec_digest = self._load_spec(item)
            status, score, reason = self._score_with_spec(
                item, spec, response, max_score
            )
        except _AssessmentBlocked as exc:
            return self._result(
                item,
                learner_id,
                rid,
                max_score,
                "EVAL_ERROR",
                None,
                exc.reason,
                [f"item:{item.item_id}"],
            )
        except _JudgeInfrastructureFailure as exc:
            return self._result(
                item,
                learner_id,
                rid,
                max_score,
                "EVAL_ERROR",
                None,
                exc.reason,
                [f"item:{item.item_id}"],
            )
        except _ScorerInfrastructureError as exc:
            return self._result(
                item,
                learner_id,
                rid,
                max_score,
                "EVAL_ERROR",
                None,
                f"EVAL_ERROR:{exc.code}",
                [f"item:{item.item_id}"],
            )
        return self._result(
            item,
            learner_id,
            rid,
            max_score,
            status,
            score,
            reason,
            # review P2-4: no truncated hidden-spec hash in teacher-visible
            # evidence refs (low-entropy dictionary signal); the item id alone is
            # the auditable reference.
            [f"item:{item.item_id}"],
        )

    # -- validation --------------------------------------------------------
    @staticmethod
    def _coerce_root(fixtures_root: Any) -> Path:
        if isinstance(fixtures_root, Path):
            root = fixtures_root
        elif isinstance(fixtures_root, str):
            if not fixtures_root.strip():
                raise ValidationError("DeterministicScorer(fixtures_root): must not be blank")
            root = Path(fixtures_root)
        else:
            raise ValidationError(
                "DeterministicScorer(fixtures_root): expected a str or pathlib.Path"
            )
        root = root.expanduser().resolve()
        if not root.is_dir():
            raise ValidationError(
                f"DeterministicScorer(fixtures_root): not a directory: {root}"
            )
        return root

    @staticmethod
    def _validate_item(item: Any) -> AssessmentItem:
        if not isinstance(item, AssessmentItem):
            raise ValidationError(
                "DeterministicScorer.score(item=...): expected an AssessmentItem"
            )
        if type(item.item_type) is not str or item.item_type not in {
            "MCQ",
            "CODE",
            "SHORT_ANSWER",
        }:
            raise ValidationError(
                f"DeterministicScorer.score(): unsupported item_type {item.item_type!r}"
            )
        return item

    # -- result plumbing ---------------------------------------------------
    @staticmethod
    def _default_result_id(item: AssessmentItem, response: Any) -> str:
        return f"result:{item.item_id}:{_digest(_canonical(response))[:16]}"

    def _result(
        self,
        item: AssessmentItem,
        learner_id: str,
        result_id: str,
        max_score: float,
        status: str,
        score: float | None,
        failure_reason: str,
        evidence_refs: list[str],
    ) -> AssessmentResult:
        if status not in ASSESSMENT_STATUS_VALUES:  # pragma: no cover - internal invariant
            raise ValidationError(f"scorer produced invalid status {status!r}")
        if score is not None:
            score = max(0.0, min(float(max_score), float(score)))
        return AssessmentResult(
            result_id=result_id,
            item_id=item.item_id,
            learner_id=learner_id,
            status=status,
            score=score,
            max_score=max_score,
            scorer_id=self._scorer_id,
            failure_reason=failure_reason,
            evidence_refs=list(evidence_refs),
            created_at=self._clock(),
        )

    # -- spec loading (the only hidden-material read path) ------------------
    def _domain_dir(self, item: AssessmentItem) -> Path:
        nested = self._fixtures_root / "domains" / item.domain_id
        if nested.is_dir():
            return nested
        # Convenience for tests: a domain directory passed directly.
        if (self._fixtures_root / "knowledge_graph.json").is_file():
            return self._fixtures_root
        raise _ScorerInfrastructureError("FIXTURES_MISSING")

    def _scoring_dir(self, item: AssessmentItem) -> Path:
        return self._domain_dir(item) / _SCORING_DIR_NAME

    def _resolve_spec_path(self, item: AssessmentItem) -> tuple[Path, Path]:
        scoring_dir = self._scoring_dir(item)
        ref = item.scoring_spec_ref
        if type(ref) is not str or not ref.strip():
            raise _ScorerInfrastructureError("SPEC_REF_MISSING")
        relative = Path(ref)
        if relative.is_absolute():
            raise _ScorerInfrastructureError("SPEC_REF_ABSOLUTE")
        parts = relative.parts
        if any(part in {"", ".", ".."} for part in parts):
            raise _ScorerInfrastructureError("SPEC_REF_TRAVERSAL")
        # Fixtures use domain-relative refs ("scoring/item.json"); also accept a
        # ref that is already relative to the scoring directory itself.
        if parts and parts[0] == _SCORING_DIR_NAME:
            parts = parts[1:]
        if not parts:
            raise _ScorerInfrastructureError("SPEC_REF_MISSING")
        candidate = scoring_dir.joinpath(*parts)
        try:
            resolved = candidate.resolve(strict=False)
            scoring_resolved = scoring_dir.resolve(strict=False)
        except OSError:  # pragma: no cover - defensive
            raise _ScorerInfrastructureError("SPEC_REF_UNRESOLVABLE") from None
        if resolved != scoring_resolved and scoring_resolved not in resolved.parents:
            raise _ScorerInfrastructureError("SPEC_REF_OUTSIDE_SCORING")
        return resolved, scoring_dir

    def _load_spec(self, item: AssessmentItem) -> tuple[dict[str, Any], str]:
        path, _scoring_dir = self._resolve_spec_path(item)
        if not path.is_file():
            raise _ScorerInfrastructureError("SPEC_MISSING")
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            raise _ScorerInfrastructureError("SPEC_UNREADABLE") from None
        try:
            spec = json.loads(text)
        except json.JSONDecodeError:
            raise _ScorerInfrastructureError("SPEC_INVALID_JSON") from None
        if not isinstance(spec, dict):
            raise _ScorerInfrastructureError("SPEC_INVALID_SHAPE")
        return spec, _digest(text)

    # -- dispatch ----------------------------------------------------------
    def _score_with_spec(
        self,
        item: AssessmentItem,
        spec: Mapping[str, Any],
        response: Any,
        max_score: float,
    ) -> tuple[str, float | None, str]:
        kind = spec.get("kind")
        if kind == "MCQ":
            return self._score_mcq(item, spec, response, max_score)
        if kind == "PYTHON_FUNCTION":
            return self._score_code(item, spec, response, max_score)
        if kind == "SEMANTIC_RUBRIC":
            return self._score_short_answer(item, spec, response, max_score)
        raise _ScorerInfrastructureError("SPEC_UNKNOWN_KIND")

    # -- MCQ ---------------------------------------------------------------
    @staticmethod
    def _choice_index(response: Any) -> int | None:
        if isinstance(response, bool):
            return None
        if isinstance(response, int):
            return response
        if isinstance(response, dict):
            if "choice_index" not in response:
                return None
            return DeterministicScorer._choice_index(response["choice_index"])
        if isinstance(response, str):
            text = response.strip()
            if len(text) == 1 and text.isalpha():
                return ord(text.upper()) - ord("A")
            if text.isdigit():
                return int(text)
        return None

    def _score_mcq(
        self,
        item: AssessmentItem,
        spec: Mapping[str, Any],
        response: Any,
        max_score: float,
    ) -> tuple[str, float | None, str]:
        correct_index = spec.get("correct_option_index")
        if (
            type(correct_index) is not int
            or correct_index < 0
            or correct_index >= len(item.options)
        ):
            raise _ScorerInfrastructureError("SPEC_MCQ_INDEX_INVALID")
        index = self._choice_index(response)
        if index is None:
            return "INCORRECT", 0.0, "INVALID_RESPONSE"
        if not 0 <= index < len(item.options):
            return "INCORRECT", 0.0, "OPTION_OUT_OF_RANGE"
        if index == correct_index:
            return "CORRECT", max_score, ""
        return "INCORRECT", 0.0, "WRONG_OPTION"

    # -- CODE --------------------------------------------------------------
    def _score_code(
        self,
        item: AssessmentItem,
        spec: Mapping[str, Any],
        response: Any,
        max_score: float,
    ) -> tuple[str, float | None, str]:
        # Fail closed *before* any learner-code execution path is considered.
        if not self._trusted_fixture_only:
            raise _AssessmentBlocked(STATUS_UNTRUSTED_CODE_EXECUTION_BLOCKED)
        function_name = spec.get("function_name")
        tests = spec.get("tests")
        if type(function_name) is not str or not function_name.strip():
            raise _ScorerInfrastructureError("SPEC_CODE_FUNCTION_INVALID")
        if type(tests) is not list or not tests:
            raise _ScorerInfrastructureError("SPEC_CODE_TESTS_INVALID")
        normalized_tests: list[dict[str, Any]] = []
        for case in tests:
            if (
                type(case) is not dict
                or type(case.get("args")) is not list
                or "expected" not in case
            ):
                raise _ScorerInfrastructureError("SPEC_CODE_TESTS_INVALID")
            normalized_tests.append({"args": case["args"], "expected": case["expected"]})
        if type(response) is not str or not response.strip():
            return "INCORRECT", 0.0, "EMPTY_CODE"
        spec_timeout = spec.get("timeout_s", self._timeout_s)
        if type(spec_timeout) not in (int, float) or not spec_timeout > 0:
            raise _ScorerInfrastructureError("SPEC_CODE_TIMEOUT_INVALID")
        timeout = max(0.1, min(float(self._timeout_s), float(spec_timeout)))
        try:
            verdict = self._get_supervisor().evaluate(
                response,
                function_name,
                normalized_tests,
                timeout_s=timeout,
            )
        except Exception:  # noqa: BLE001 - judge failure must fail closed
            raise _JudgeInfrastructureFailure("JUDGE_INFRA_ERROR:SUPERVISOR_EXCEPTION") from None
        return self._map_judge_verdict(verdict, max_score)

    @staticmethod
    def _map_judge_verdict(
        verdict: JudgeVerdict, max_score: float
    ) -> tuple[str, float | None, str]:
        """Map a trusted aggregate verdict to student evidence (no hidden data)."""

        total = max(0, int(verdict.cases_total))
        passed = max(0, min(total, int(verdict.cases_passed)))
        failed = total - passed
        if verdict.infra_error or verdict.status in {
            STATUS_JUDGE_INFRA_ERROR,
            STATUS_JUDGE_SANDBOX_UNAVAILABLE,
            STATUS_UNTRUSTED_CODE_EXECUTION_BLOCKED,
        }:
            if verdict.status in {
                STATUS_JUDGE_SANDBOX_UNAVAILABLE,
                STATUS_UNTRUSTED_CODE_EXECUTION_BLOCKED,
            }:
                raise _AssessmentBlocked(STATUS_UNTRUSTED_CODE_EXECUTION_BLOCKED)
            code = "UNKNOWN"
            for failure_code in verdict.failure_codes:
                if failure_code.startswith("JUDGE_INFRA_ERROR:"):
                    code = failure_code.split(":", 1)[1]
                    break
            raise _JudgeInfrastructureFailure(f"JUDGE_INFRA_ERROR:{code}")
        if verdict.status == STATUS_PASS and passed == total and total > 0:
            return "CORRECT", max_score, ""
        ratio = (passed / total) if total else 0.0
        if passed > 0:
            timeout_failure = verdict.status == STATUS_TLE
            reason = (
                f"JUDGE_STUDENT_TLE:{passed}/{total}"
                if timeout_failure
                else f"JUDGE_CASES_FAILED:{failed}/{total}"
            )
            return "PARTIAL", max_score * ratio, reason
        if verdict.status == STATUS_TLE:
            return "INCORRECT", 0.0, "JUDGE_STUDENT_TLE"
        if verdict.status == STATUS_RE:
            return "INCORRECT", 0.0, "JUDGE_STUDENT_RE"
        return "INCORRECT", 0.0, f"JUDGE_CASES_FAILED:0/{total}"

    # -- SHORT_ANSWER ------------------------------------------------------
    def _score_short_answer(
        self,
        item: AssessmentItem,
        spec: Mapping[str, Any],
        response: Any,
        max_score: float,
    ) -> tuple[str, float | None, str]:
        groups = spec.get("required_concept_groups")
        allow_correct = spec.get("allow_correct", False)
        on_insufficient = spec.get("on_insufficient", "NEEDS_REVIEW")
        if allow_correct is not False:
            # A semantic rubric must never be allowed to fake a CORRECT verdict.
            raise _ScorerInfrastructureError("SPEC_RUBRIC_ALLOW_CORRECT_UNSUPPORTED")
        if on_insufficient != "NEEDS_REVIEW":
            raise _ScorerInfrastructureError("SPEC_RUBRIC_ON_INSUFFICIENT_UNSUPPORTED")
        if type(groups) is not list or not groups or len(groups) > _MAX_RUBRIC_GROUPS:
            raise _ScorerInfrastructureError("SPEC_RUBRIC_GROUPS_INVALID")
        normalized: list[list[str]] = []
        for group in groups:
            if type(group) is not list or not group:
                raise _ScorerInfrastructureError("SPEC_RUBRIC_GROUPS_INVALID")
            keywords = [
                keyword.casefold()
                for keyword in group
                if type(keyword) is str and keyword.strip()
            ]
            if not keywords:
                raise _ScorerInfrastructureError("SPEC_RUBRIC_GROUPS_INVALID")
            normalized.append(keywords)
        if type(response) is not str or not response.strip():
            return "NEEDS_REVIEW", None, "SEMANTIC_UNVERIFIABLE"
        text = response.casefold()
        if len(text) < _MIN_RESPONSE_CHARS:
            return "NEEDS_REVIEW", None, "SEMANTIC_UNVERIFIABLE"
        matched = sum(
            1 for keywords in normalized if any(keyword in text for keyword in keywords)
        )
        ratio = matched / len(normalized)
        if ratio >= 1.0:
            # Full rubric coverage still yields only PARTIAL: deterministic
            # keyword evidence cannot prove semantic understanding.
            return "PARTIAL", max_score, "SEMANTIC_RUBRIC_FULL_MATCH"
        if ratio > 0.0:
            return "PARTIAL", max_score * ratio, f"SEMANTIC_RUBRIC_PARTIAL:{matched}/{len(normalized)}"
        return "NEEDS_REVIEW", None, "SEMANTIC_UNVERIFIABLE"
