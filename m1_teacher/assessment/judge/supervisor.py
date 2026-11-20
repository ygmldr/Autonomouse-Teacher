"""Trusted judge supervisor for the M1-B judge trust boundary (B-PR1).

The supervisor is the **trusted** half of the judge boundary frozen in
``docs/M1_B_THREAT_MODEL_JUDGE.md`` (m1b.judge.worker.v1):

* it owns the hidden ``expected`` values / test list and the final verdict;
* it hands one case at a time to an *untrusted* execution worker (the sibling
  ``judge.worker`` package owned by the sandbox workstream) which only receives
  ``code``, ``function_name`` and the JSON ``args`` of a single case;
* it treats every worker observation (``actual_canonical``, exception class,
  status, exit code, stdout/stderr) as **untrusted data** and compares the
  observed actual value against its own expected value using strict canonical
  JSON (``bool``/``int``/``float`` are not interchangeable);
* worker protocol violations, forged extra fields (``passed``/``verdict``/
  ``score``/``expected``/...), oversized payloads and crashes map to
  ``JUDGE_INFRA_ERROR`` -- never to ``PASS`` and never to a learner failure;
* the default policy is fail-closed: without an explicit
  ``trusted_fixture_only=True`` opt-in, learner CODE is *not executed* and a
  structured ``UNTRUSTED_CODE_EXECUTION_BLOCKED`` verdict is returned.  The
  same blocked verdict is returned when the worker / OS sandbox is unavailable;
  there is no fallback to an in-process or bare-subprocess runner.

Nothing in this module reads hidden fixture files: the caller (the independent
scorer) loads the scoring specification and passes ``tests``/``expected`` in.
The supervisor only serialises the per-case request into the worker and
aggregates verdicts.  Failure reasons contain **only** aggregate classification
counts, never expected values or hidden argument values.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

try:  # frozen worker protocol (owned by the sandbox workstream)
    from . import protocol as _protocol
except ImportError:  # pragma: no cover - pre-merge provisional state
    _protocol = None  # type: ignore[assignment]

try:  # untrusted worker implementation (owned by the sandbox workstream)
    from .worker import UntrustedExecutionWorker as _DefaultWorker
except ImportError:  # pragma: no cover - pre-merge provisional state
    _DefaultWorker = None  # type: ignore[assignment]

__all__ = [
    "DEFAULT_CASE_TIMEOUT_S",
    "MIN_CASE_TIMEOUT_S",
    "MAX_CASE_TIMEOUT_S",
    "STATUS_PASS",
    "STATUS_WA",
    "STATUS_RE",
    "STATUS_TLE",
    "STATUS_JUDGE_INFRA_ERROR",
    "STATUS_UNTRUSTED_CODE_EXECUTION_BLOCKED",
    "STATUS_JUDGE_SANDBOX_UNAVAILABLE",
    "JudgeVerdict",
    "TrustedJudgeSupervisor",
]

DEFAULT_CASE_TIMEOUT_S = 1.5
MIN_CASE_TIMEOUT_S = 0.05
MAX_CASE_TIMEOUT_S = 5.0

STATUS_PASS = "PASS"
STATUS_WA = "WA"
STATUS_RE = "RE"
STATUS_TLE = "TLE"
STATUS_JUDGE_INFRA_ERROR = "JUDGE_INFRA_ERROR"
STATUS_UNTRUSTED_CODE_EXECUTION_BLOCKED = "UNTRUSTED_CODE_EXECUTION_BLOCKED"
STATUS_JUDGE_SANDBOX_UNAVAILABLE = "JUDGE_SANDBOX_UNAVAILABLE"

# Worker-observation statuses (frozen protocol values).  They are deliberately
# duplicated here as plain strings so the trusted supervisor can keep working
# when the worker package is unavailable: a missing worker means "blocked",
# never "run something else".
_WORKER_COMPLETED = "COMPLETED"
_WORKER_RAISED = "RAISED"
_WORKER_SYNTAX_ERROR = "SYNTAX_ERROR"
_WORKER_IMPORT_ERROR = "IMPORT_ERROR"
_WORKER_MISSING_FUNCTION = "MISSING_FUNCTION"
_WORKER_TIMEOUT = "TIMEOUT"
_WORKER_INFRA_ERROR = "INFRA_ERROR"

_WORKER_STATUSES = frozenset(
    {
        _WORKER_COMPLETED,
        _WORKER_RAISED,
        _WORKER_SYNTAX_ERROR,
        _WORKER_IMPORT_ERROR,
        _WORKER_MISSING_FUNCTION,
        _WORKER_TIMEOUT,
        _WORKER_INFRA_ERROR,
    }
)
_STUDENT_FAILURE_STATUSES = frozenset(
    {
        _WORKER_RAISED,
        _WORKER_SYNTAX_ERROR,
        _WORKER_IMPORT_ERROR,
        _WORKER_MISSING_FUNCTION,
    }
)

_ALLOWED_OBSERVATION_KEYS = frozenset(
    {"status", "actual_canonical", "exception_type", "stdout_excerpt", "stderr_excerpt"}
)
_FORBIDDEN_OBSERVATION_KEYS = frozenset(
    {
        "passed",
        "verdict",
        "score",
        "correct",
        "expected",
        "tests",
        "hidden",
        "case_index",
        "scoring_spec_ref",
        "scoring_path",
        "result_path",
        "workspace",
        "db_path",
        "learner_id",
        "session_id",
        "assessment",
    }
)


def _canonical(value: Any) -> str:
    """Strict canonical JSON used for the actual/expected comparison."""

    if _protocol is not None:
        return _protocol.canonical_json(value)
    return json.dumps(  # pragma: no cover - only when worker branch is absent
        value,
        ensure_ascii=False,
        sort_keys=True,
        allow_nan=False,
        separators=(",", ":"),
    )


def _require_number(value: Any, where: str, *, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{where}: expected a number")
    number = float(value)
    if not minimum <= number <= maximum:
        raise ValueError(f"{where}: expected {minimum} <= value <= {maximum}")
    return number


@dataclass(frozen=True)
class JudgeVerdict:
    """Trusted, aggregate judge outcome for one submission.

    The verdict is intentionally aggregate-only: no expected value, hidden
    argument, worker excerpt or raw actual value is stored.  ``failure_codes``
    contains only classification labels and counts, safe for diagnostics/trace
    export (B1-06).
    """

    status: str
    score_ratio: float
    cases_total: int
    cases_passed: int
    failure_codes: tuple[str, ...] = ()
    infra_error: bool = False

    @property
    def passed(self) -> bool:
        return self.status == STATUS_PASS and not self.infra_error

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "score_ratio": self.score_ratio,
            "cases_total": self.cases_total,
            "cases_passed": self.cases_passed,
            "failure_codes": list(self.failure_codes),
            "infra_error": self.infra_error,
        }


class _ObservationInvalid(Exception):
    """Internal marker: the worker response is not a valid observation."""


class TrustedJudgeSupervisor:
    """Compare untrusted worker observations against trusted hidden expected values."""

    def __init__(
        self,
        worker: Any = None,
        *,
        timeout_s: float = DEFAULT_CASE_TIMEOUT_S,
        trusted_fixture_only: bool = False,
    ) -> None:
        self._timeout_s = _require_number(
            timeout_s,
            "TrustedJudgeSupervisor(timeout_s)",
            minimum=MIN_CASE_TIMEOUT_S,
            maximum=MAX_CASE_TIMEOUT_S,
        )
        if not isinstance(trusted_fixture_only, bool):
            raise ValueError("TrustedJudgeSupervisor(trusted_fixture_only): expected bool")
        if worker is not None and not callable(getattr(worker, "run_case", None)):
            raise ValueError(
                "TrustedJudgeSupervisor(worker=...): expected an object with run_case()"
            )
        self._trusted_fixture_only = trusted_fixture_only
        self._worker = worker
        if self._worker is None and _DefaultWorker is not None:
            self._worker = _DefaultWorker()

    # -- introspection -----------------------------------------------------
    @property
    def worker(self) -> Any:
        return self._worker

    @property
    def timeout_s(self) -> float:
        return self._timeout_s

    @property
    def trusted_fixture_only(self) -> bool:
        return self._trusted_fixture_only

    def worker_available(self) -> bool:
        """True when an OS-sandbox worker is present and its sandbox is usable."""

        worker = self._worker
        if worker is None:
            return False
        try:
            probe = getattr(worker, "sandbox_available", None)
            if callable(probe):
                return bool(probe())
            return True
        except Exception:  # noqa: BLE001 - any probe failure means "not available"
            return False

    # -- evaluation --------------------------------------------------------
    def evaluate(
        self,
        code: str,
        function_name: str,
        tests: Sequence[Mapping[str, Any]],
        *,
        timeout_s: float | None = None,
    ) -> JudgeVerdict:
        """Run one submission's cases through the worker and decide the verdict.

        ``tests`` is trustworthy (loaded by the trusted scorer from the hidden
        scoring spec); only per-case ``args`` cross into the worker.  The
        expected value is compared on the trusted side only.
        """

        tests_list = self._validate_tests(tests)
        total = len(tests_list)
        if not self._trusted_fixture_only:
            return self._blocked(total, STATUS_UNTRUSTED_CODE_EXECUTION_BLOCKED)
        if self._worker is None:
            return self._blocked(total, STATUS_JUDGE_SANDBOX_UNAVAILABLE)
        if not self.worker_available():
            return self._blocked(total, STATUS_JUDGE_SANDBOX_UNAVAILABLE)
        if not isinstance(code, str):
            return self._infra(total, "INVALID_CODE")
        if not isinstance(function_name, str) or not function_name.strip():
            return self._infra(total, "INVALID_FUNCTION_NAME")

        effective_timeout = self._effective_timeout(timeout_s)
        cases_passed = 0
        case_statuses: list[str] = []
        had_timeout = False
        for case in tests_list:
            try:
                observation = self._worker.run_case(
                    code, function_name, list(case["args"]), effective_timeout
                )
            except Exception:  # noqa: BLE001 - worker failure is infrastructure
                return self._infra(total, "WORKER_EXCEPTION")
            try:
                parsed = self._coerce_observation(observation)
            except _ObservationInvalid:
                return self._infra(total, "WORKER_PROTOCOL_ERROR")
            status = parsed["status"]
            if status == _WORKER_INFRA_ERROR:
                return self._infra(total, "WORKER_INFRA_ERROR")
            if status == _WORKER_TIMEOUT:
                had_timeout = True
                case_statuses.append(_WORKER_TIMEOUT)
                break
            if status == _WORKER_COMPLETED:
                actual = parsed["actual_canonical"]
                if not isinstance(actual, str):
                    return self._infra(total, "WORKER_PROTOCOL_ERROR")
                try:
                    decoded_actual = json.loads(actual)
                    actual_canonical = _canonical(decoded_actual)
                    expected_canonical = _canonical(case["expected"])
                except (TypeError, ValueError, json.JSONDecodeError):
                    return self._infra(total, "WORKER_PROTOCOL_ERROR")
                if actual_canonical != actual:
                    # The frozen protocol requires the worker to emit the exact
                    # canonical rendering (no duplicate keys/whitespace/non-JSON
                    # rewrites); anything else is a protocol violation, not data.
                    return self._infra(total, "WORKER_PROTOCOL_ERROR")
                if actual_canonical != expected_canonical:
                    case_statuses.append(status)
                else:
                    cases_passed += 1
                continue
            if status in _STUDENT_FAILURE_STATUSES:
                case_statuses.append(status)
                continue
            return self._infra(total, "WORKER_PROTOCOL_ERROR")  # pragma: no cover

        ratio = (cases_passed / total) if total else 0.0
        if had_timeout:
            return JudgeVerdict(
                status=STATUS_TLE,
                score_ratio=ratio,
                cases_total=total,
                cases_passed=cases_passed,
                failure_codes=("STUDENT_TLE", f"CASES_PASSED:{cases_passed}/{total}"),
                infra_error=False,
            )
        if not case_statuses:
            return JudgeVerdict(
                status=STATUS_PASS,
                score_ratio=1.0,
                cases_total=total,
                cases_passed=total,
                failure_codes=(),
                infra_error=False,
            )
        failed = total - cases_passed
        first_status = STATUS_WA if _WORKER_COMPLETED in case_statuses else STATUS_RE
        codes = [f"CASES_FAILED:{failed}/{total}"]
        if _WORKER_COMPLETED in case_statuses:
            codes.append("WA")
        if any(status in _STUDENT_FAILURE_STATUSES for status in case_statuses):
            codes.append("RE")
        return JudgeVerdict(
            status=first_status,
            score_ratio=ratio,
            cases_total=total,
            cases_passed=cases_passed,
            failure_codes=tuple(codes),
            infra_error=False,
        )

    # -- internal ----------------------------------------------------------
    @staticmethod
    def _validate_tests(tests: Any) -> list[Mapping[str, Any]]:
        if isinstance(tests, (str, bytes)) or not isinstance(tests, Sequence):
            raise ValueError("TrustedJudgeSupervisor.evaluate(tests): expected a sequence")
        normalized: list[Mapping[str, Any]] = []
        for case in tests:
            if not isinstance(case, Mapping) or "args" not in case or "expected" not in case:
                raise ValueError(
                    "TrustedJudgeSupervisor.evaluate(tests): each case needs args/expected"
                )
            if not isinstance(case["args"], list):
                raise ValueError("TrustedJudgeSupervisor.evaluate(tests): args must be a list")
            normalized.append(case)
        if not normalized:
            raise ValueError("TrustedJudgeSupervisor.evaluate(tests): at least one case required")
        return normalized

    def _effective_timeout(self, timeout_s: float | None) -> float:
        if timeout_s is None:
            return self._timeout_s
        try:
            requested = _require_number(
                timeout_s,
                "TrustedJudgeSupervisor.evaluate(timeout_s)",
                minimum=MIN_CASE_TIMEOUT_S,
                maximum=MAX_CASE_TIMEOUT_S,
            )
        except ValueError:
            return self._timeout_s
        return min(self._timeout_s, requested)

    @staticmethod
    def _coerce_observation(observation: Any) -> dict[str, Any]:
        if isinstance(observation, Mapping):
            keys = set(observation)
            if keys & _FORBIDDEN_OBSERVATION_KEYS:
                raise _ObservationInvalid("forbidden worker field")
            if keys - _ALLOWED_OBSERVATION_KEYS:
                raise _ObservationInvalid("unknown worker field")
            status = observation.get("status")
            actual = observation.get("actual_canonical")
        else:
            if any(
                hasattr(observation, name)
                for name in ("passed", "verdict", "score", "expected")
            ):
                raise _ObservationInvalid("forbidden worker field")
            status = getattr(observation, "status", None)
            actual = getattr(observation, "actual_canonical", None)
        if not isinstance(status, str) or status not in _WORKER_STATUSES:
            raise _ObservationInvalid("invalid worker status")
        if status == _WORKER_COMPLETED:
            if not isinstance(actual, str):
                raise _ObservationInvalid("COMPLETED observation requires actual")
        elif actual is not None:
            raise _ObservationInvalid("non-COMPLETED observation must not carry actual")
        return {"status": status, "actual_canonical": actual}

    @staticmethod
    def _blocked(total: int, status: str) -> JudgeVerdict:
        return JudgeVerdict(
            status=status,
            score_ratio=0.0,
            cases_total=total,
            cases_passed=0,
            failure_codes=(status,),
            infra_error=True,
        )

    @staticmethod
    def _infra(total: int, code: str) -> JudgeVerdict:
        return JudgeVerdict(
            status=STATUS_JUDGE_INFRA_ERROR,
            score_ratio=0.0,
            cases_total=total,
            cases_passed=0,
            failure_codes=(f"JUDGE_INFRA_ERROR:{code}",),
            infra_error=True,
        )
