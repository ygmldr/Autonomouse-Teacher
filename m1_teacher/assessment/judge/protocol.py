"""Frozen untrusted-worker protocol ``m1b.judge.worker.v1`` (B-PR1).

Trust boundary
--------------
The :class:`~m1_teacher.assessment.judge.worker.UntrustedExecutionWorker` only
executes **learner code for a single case** and reports *observations*.  This
module freezes both directions of the protocol:

* trusted -> worker: exactly one JSON request with ``function_name`` and
  ``args``; it never contains ``expected``/``tests``/verdict/paths;
* worker -> trusted: exactly one JSON line with an observed ``status`` and the
  canonicalised ``actual_canonical`` value; it never contains a verdict,
  ``passed``/``score`` field, hidden expected value or host path.

Anything malformed (unknown field, duplicate key, wrong type, version, request
id mismatch, oversized/undersized payload, multi-line output, ...) fails closed
with :class:`WorkerProtocolError`; callers map that to ``JUDGE_INFRA_ERROR``.

Public surface
--------------
* :data:`PROTOCOL_VERSION`, policy codes (:data:`JUDGE_SANDBOX_UNAVAILABLE`,
  :data:`UNTRUSTED_CODE_EXECUTION_BLOCKED`, :data:`JUDGE_INFRA_ERROR`);
* :class:`WorkerObservation` -- the only worker result shape (no verdict);
* :func:`build_request` / :func:`parse_worker_response`;
* :func:`canonical_json` -- the single canonicalisation used for comparison on
  the *trusted* side as well as inside the runner.
"""

from __future__ import annotations

import json
import math
import re
import secrets
from dataclasses import dataclass
from typing import Any, Sequence

__all__ = [
    "PROTOCOL_VERSION",
    "JUDGE_SANDBOX_UNAVAILABLE",
    "UNTRUSTED_CODE_EXECUTION_BLOCKED",
    "JUDGE_INFRA_ERROR",
    "WORKER_STATUSES",
    "WORKER_STATUS_COMPLETED",
    "WORKER_STATUS_RAISED",
    "WORKER_STATUS_SYNTAX_ERROR",
    "WORKER_STATUS_IMPORT_ERROR",
    "WORKER_STATUS_MISSING_FUNCTION",
    "WORKER_STATUS_TIMEOUT",
    "WORKER_STATUS_INFRA_ERROR",
    "WorkerObservation",
    "WorkerProtocolError",
    "build_request",
    "parse_worker_response",
    "canonical_json",
    "new_request_id",
    "infra_observation",
    "timeout_observation",
    "REQUEST_FIELDS",
    "RESPONSE_FIELDS",
    "FORBIDDEN_FIELDS",
]

# ---------------------------------------------------------------------------
# Frozen constants
# ---------------------------------------------------------------------------

PROTOCOL_VERSION = "m1b.judge.worker.v1"

#: Fail-closed policy code: the OS sandbox cannot be established; no learner
#: code was executed.
JUDGE_SANDBOX_UNAVAILABLE = "JUDGE_SANDBOX_UNAVAILABLE"

#: Fail-closed policy code: untrusted CODE execution is disabled by policy and
#: learner code was *not* executed (mastery must stay unchanged).
UNTRUSTED_CODE_EXECUTION_BLOCKED = "UNTRUSTED_CODE_EXECUTION_BLOCKED"

#: Non-student infrastructure failure: the observation cannot be trusted.
JUDGE_INFRA_ERROR = "JUDGE_INFRA_ERROR"

WORKER_STATUS_COMPLETED = "COMPLETED"
WORKER_STATUS_RAISED = "RAISED"
WORKER_STATUS_SYNTAX_ERROR = "SYNTAX_ERROR"
WORKER_STATUS_IMPORT_ERROR = "IMPORT_ERROR"
WORKER_STATUS_MISSING_FUNCTION = "MISSING_FUNCTION"
WORKER_STATUS_TIMEOUT = "TIMEOUT"
WORKER_STATUS_INFRA_ERROR = "INFRA_ERROR"

WORKER_STATUSES = frozenset(
    {
        WORKER_STATUS_COMPLETED,
        WORKER_STATUS_RAISED,
        WORKER_STATUS_SYNTAX_ERROR,
        WORKER_STATUS_IMPORT_ERROR,
        WORKER_STATUS_MISSING_FUNCTION,
        WORKER_STATUS_TIMEOUT,
        WORKER_STATUS_INFRA_ERROR,
    }
)

# Statuses that mean "the learner submission itself failed" (student evidence).
STUDENT_FAILURE_STATUSES = frozenset(
    {
        WORKER_STATUS_RAISED,
        WORKER_STATUS_SYNTAX_ERROR,
        WORKER_STATUS_IMPORT_ERROR,
        WORKER_STATUS_MISSING_FUNCTION,
    }
)

# Fixed payload limits (stdout/stderr limits are also per-request).
#
# B-PR1 deviation from threat-model 4096B, approved by Lead for trusted-fixture
# certification cases: the threat model §3.2 freezes args <= 4096 bytes and the
# request <= 16 KiB.  The 14-problem certification corpus contains 11
# ``large`` hidden cases whose JSON args exceed that budget (largest ~644 KiB,
# e.g. 100000-element arrays), and B1-05 requires those reference cases to be
# judged.  The request is generated only by the *trusted* supervisor from
# hidden fixtures -- learner code cannot influence its size -- and the worker
# stays bounded by RLIMIT_AS + hard read caps, so the sizes below are raised by
# the minimum needed to run the frozen corpus:
#   args 4096 B -> 1 MiB, request 16 KiB -> 2 MiB,
#   actual_canonical 8192 B -> 64 KiB, response 16 KiB -> 128 KiB
# (largest hidden actual is ~38.5 KiB for the 5000-element running-sum list).
# All field names, forbidden fields and semantic rules are unchanged.
MAX_REQUEST_BYTES = 2 * 1024 * 1024
MAX_RESPONSE_BYTES = 128 * 1024
MAX_ARGS_BYTES = 1024 * 1024
MAX_ARGS_DEPTH = 4
MAX_ARGS_NODES = 1024 * 1024
MAX_ACTUAL_CANONICAL_BYTES = 64 * 1024
MAX_EXCERPT_BYTES = 4096
MIN_TIMEOUT_MS = 50
MAX_TIMEOUT_MS = 5000
DEFAULT_TIMEOUT_MS = 1500
DEFAULT_STDOUT_LIMIT = 512
DEFAULT_STDERR_LIMIT = 512

REQUEST_ID_RE = re.compile(r"^[a-f0-9]{16,64}$")
FUNCTION_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
EXCEPTION_TYPE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]{0,127}$")

REQUEST_FIELDS = frozenset(
    {
        "schema_version",
        "request_id",
        "function_name",
        "args",
        "timeout_ms",
        "stdout_limit",
        "stderr_limit",
    }
)
RESPONSE_FIELDS = frozenset(
    {
        "schema_version",
        "request_id",
        "status",
        "actual_canonical",
        "exception_type",
        "stdout_excerpt",
        "stderr_excerpt",
    }
)

#: Field names that must never cross the trust boundary in either direction.
FORBIDDEN_FIELDS = frozenset(
    {
        "expected",
        "tests",
        "hidden",
        "case_index",
        "scoring_spec_ref",
        "scoring_path",
        "workspace",
        "result_path",
        "db_path",
        "learner_id",
        "session_id",
        "verdict",
        "passed",
        "score",
        "correct",
        "case_count",
        "assessment",
    }
)


# ---------------------------------------------------------------------------
# Errors and observation shape
# ---------------------------------------------------------------------------


class WorkerProtocolError(ValueError):
    """Raised when a worker request/response violates the frozen protocol.

    Callers must map this to ``JUDGE_INFRA_ERROR`` (fail closed); it must never
    be interpreted as a learner failure or as a PASS.
    """


@dataclass(frozen=True)
class WorkerObservation:
    """Untrusted observation reported by the worker for a single case.

    There is deliberately **no** verdict/passed/score field: the trusted
    supervisor compares ``actual_canonical`` against its own canonicalised
    expected value and alone decides PASS/WA/RE/TLE.
    """

    status: str
    actual_canonical: str | None = None
    exception_type: str | None = None
    stdout_excerpt: str = ""
    stderr_excerpt: str = ""
    request_id: str = ""

    def __post_init__(self) -> None:
        if self.status not in WORKER_STATUSES:
            raise WorkerProtocolError(f"unknown worker status: {self.status!r}")


def infra_observation(
    request_id: str = "", *, exception_type: str | None = None
) -> WorkerObservation:
    """Build the fail-closed observation for an infrastructure failure."""

    return WorkerObservation(
        status=WORKER_STATUS_INFRA_ERROR,
        actual_canonical=None,
        exception_type=exception_type,
        stdout_excerpt="",
        stderr_excerpt="",
        request_id=request_id,
    )


def timeout_observation(request_id: str = "") -> WorkerObservation:
    """Build the observation for a worker that exceeded its wall clock."""

    return WorkerObservation(
        status=WORKER_STATUS_TIMEOUT,
        actual_canonical=None,
        exception_type=None,
        stdout_excerpt="",
        stderr_excerpt="",
        request_id=request_id,
    )


# ---------------------------------------------------------------------------
# Canonical JSON (single source of truth for both sides)
# ---------------------------------------------------------------------------


def canonical_json(value: Any) -> str:
    """Canonical JSON used for actual/expected comparison and request args.

    ``ensure_ascii=False, sort_keys=True, allow_nan=False`` with compact
    separators; the UTF-8 byte string is the comparison domain.
    """

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        allow_nan=False,
        separators=(",", ":"),
    )


def new_request_id() -> str:
    """Return a fresh 32-hex-character request id (audit correlation only)."""

    return secrets.token_hex(16)


# ---------------------------------------------------------------------------
# Request construction / validation
# ---------------------------------------------------------------------------


def _validate_args(args: Any) -> None:
    if not isinstance(args, list):
        raise WorkerProtocolError("args must be a JSON array")
    nodes = 0

    def walk(value: Any, depth: int) -> None:
        nonlocal nodes
        nodes += 1
        if nodes > MAX_ARGS_NODES:
            raise WorkerProtocolError("args exceed the node budget")
        if depth > MAX_ARGS_DEPTH:
            raise WorkerProtocolError("args exceed the depth budget")
        if isinstance(value, dict):
            for key, item in value.items():
                if not isinstance(key, str):
                    raise WorkerProtocolError("args object keys must be strings")
                walk(item, depth + 1)
        elif isinstance(value, list):
            for item in value:
                walk(item, depth + 1)
        elif isinstance(value, bool) or value is None or isinstance(value, str):
            return
        elif isinstance(value, int):
            return
        elif isinstance(value, float):
            if math.isnan(value) or math.isinf(value):
                raise WorkerProtocolError("args must not contain NaN/Infinity")
        else:
            raise WorkerProtocolError("args contain a value that is not JSON")

    walk(args, 1)
    if len(canonical_json(args).encode("utf-8")) > MAX_ARGS_BYTES:
        raise WorkerProtocolError("args exceed the canonical byte budget")


def _validate_timeout_ms(timeout_ms: Any) -> int:
    if isinstance(timeout_ms, bool) or not isinstance(timeout_ms, int):
        raise WorkerProtocolError("timeout_ms must be an integer")
    if not MIN_TIMEOUT_MS <= timeout_ms <= MAX_TIMEOUT_MS:
        raise WorkerProtocolError("timeout_ms is outside the allowed range")
    return timeout_ms


def _validate_limit(value: Any, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise WorkerProtocolError(f"{where} must be an integer")
    if not 0 <= value <= MAX_EXCERPT_BYTES:
        raise WorkerProtocolError(f"{where} is outside the allowed range")
    return value


def build_request(
    function_name: str,
    args: Sequence[Any],
    *,
    request_id: str | None = None,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
    stdout_limit: int = DEFAULT_STDOUT_LIMIT,
    stderr_limit: int = DEFAULT_STDERR_LIMIT,
) -> str:
    """Build the frozen single-case request JSON text for the worker.

    The request contains only what the worker needs to execute the case; it can
    never carry ``expected``/``tests``/verdict/paths.  A protocol violation in
    the arguments raises :class:`WorkerProtocolError` (fail closed).
    """

    if not isinstance(function_name, str) or not FUNCTION_NAME_RE.fullmatch(function_name):
        raise WorkerProtocolError("function_name is not a valid Python identifier")
    request_id = request_id if request_id is not None else new_request_id()
    if not isinstance(request_id, str) or not REQUEST_ID_RE.fullmatch(request_id):
        raise WorkerProtocolError("request_id is not a valid correlation id")
    _validate_args(list(args))
    payload = {
        "schema_version": PROTOCOL_VERSION,
        "request_id": request_id,
        "function_name": function_name,
        "args": list(args),
        "timeout_ms": _validate_timeout_ms(timeout_ms),
        "stdout_limit": _validate_limit(stdout_limit, "stdout_limit"),
        "stderr_limit": _validate_limit(stderr_limit, "stderr_limit"),
    }
    assert set(payload) <= REQUEST_FIELDS
    assert not (set(payload) & FORBIDDEN_FIELDS)
    text = canonical_json(payload)
    if len(text.encode("utf-8")) > MAX_REQUEST_BYTES:  # pragma: no cover - defensive
        raise WorkerProtocolError("request exceeds the byte budget")
    return text


def parse_request(text: bytes | str) -> dict:
    """Strictly parse/validate a worker request (used by the sandbox runner)."""

    raw = _to_bytes(text)
    if len(raw) > MAX_REQUEST_BYTES:
        raise WorkerProtocolError("request exceeds the byte budget")
    try:
        decoded = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise WorkerProtocolError("request is not valid UTF-8") from exc
    if not decoded.strip():
        raise WorkerProtocolError("request is empty")
    payload = _loads_strict(decoded)
    if not isinstance(payload, dict):
        raise WorkerProtocolError("request must be a JSON object")
    _reject_unknown_or_missing(payload, REQUEST_FIELDS, "request")
    if payload["schema_version"] != PROTOCOL_VERSION:
        raise WorkerProtocolError("request protocol version mismatch")
    request_id = payload["request_id"]
    if not isinstance(request_id, str) or not REQUEST_ID_RE.fullmatch(request_id):
        raise WorkerProtocolError("request request_id is invalid")
    function_name = payload["function_name"]
    if not isinstance(function_name, str) or not FUNCTION_NAME_RE.fullmatch(function_name):
        raise WorkerProtocolError("request function_name is invalid")
    _validate_args(payload["args"])
    _validate_timeout_ms(payload["timeout_ms"])
    _validate_limit(payload["stdout_limit"], "stdout_limit")
    _validate_limit(payload["stderr_limit"], "stderr_limit")
    return payload


# ---------------------------------------------------------------------------
# Response parsing / strict validation
# ---------------------------------------------------------------------------


def _to_bytes(text: bytes | str) -> bytes:
    if isinstance(text, bytes):
        return text
    if isinstance(text, str):
        return text.encode("utf-8")
    raise WorkerProtocolError("protocol payload must be bytes or str")


def _loads_strict(text: str) -> Any:
    def _no_duplicates(pairs: list) -> dict:
        seen: set = set()
        for key, _value in pairs:
            if key in seen:
                raise WorkerProtocolError("duplicate JSON key in protocol payload")
            seen.add(key)
        return dict(pairs)

    def _no_nonfinite(value: str) -> None:
        raise WorkerProtocolError("protocol payload must not contain NaN/Infinity")

    try:
        return json.loads(text, object_pairs_hook=_no_duplicates, parse_constant=_no_nonfinite)
    except json.JSONDecodeError as exc:
        raise WorkerProtocolError("protocol payload is not valid JSON") from exc


def _reject_unknown_or_missing(payload: dict, allowed: frozenset, where: str) -> None:
    unknown = set(payload) - allowed
    missing = set(allowed) - set(payload)
    if unknown:
        raise WorkerProtocolError(f"{where} contains unknown field(s)")
    if missing:
        raise WorkerProtocolError(f"{where} is missing required field(s)")


def _validate_actual_canonical(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise WorkerProtocolError("COMPLETED observation needs an actual_canonical string")
    if len(value.encode("utf-8")) > MAX_ACTUAL_CANONICAL_BYTES:
        raise WorkerProtocolError("actual_canonical exceeds the byte budget")
    parsed = _loads_strict(value)
    try:
        re_canonical = canonical_json(parsed)
    except (TypeError, ValueError) as exc:
        raise WorkerProtocolError("actual_canonical is not canonical JSON") from exc
    if re_canonical != value:
        raise WorkerProtocolError("actual_canonical is not in canonical form")
    return value


def _validate_exception_type(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not EXCEPTION_TYPE_RE.fullmatch(value):
        raise WorkerProtocolError("exception_type is invalid")
    return value


def _validate_excerpt(value: Any, where: str) -> str:
    if not isinstance(value, str):
        raise WorkerProtocolError(f"{where} must be a string")
    if len(value.encode("utf-8")) > MAX_EXCERPT_BYTES:
        raise WorkerProtocolError(f"{where} exceeds the byte budget")
    return value


def parse_worker_response(text: bytes | str) -> WorkerObservation:
    """Strictly parse one worker response line into an untrusted observation.

    Any structural problem raises :class:`WorkerProtocolError`; the caller must
    treat it as ``JUDGE_INFRA_ERROR`` -- never as a verdict and never as PASS.
    """

    raw = _to_bytes(text)
    if not raw:
        raise WorkerProtocolError("worker response is empty")
    if len(raw) > MAX_RESPONSE_BYTES:
        raise WorkerProtocolError("worker response exceeds the byte budget")
    try:
        decoded = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise WorkerProtocolError("worker response is not valid UTF-8") from exc
    stripped = decoded.strip()
    if not stripped:
        raise WorkerProtocolError("worker response is empty")
    lines = [line for line in stripped.splitlines() if line.strip()]
    if len(lines) != 1:
        raise WorkerProtocolError("worker response must be exactly one line")
    payload = _loads_strict(lines[0])
    if not isinstance(payload, dict):
        raise WorkerProtocolError("worker response must be a JSON object")
    _reject_unknown_or_missing(payload, RESPONSE_FIELDS, "worker response")
    if any(field in payload for field in FORBIDDEN_FIELDS):
        raise WorkerProtocolError("worker response contains a forbidden verdict field")
    if payload["schema_version"] != PROTOCOL_VERSION:
        raise WorkerProtocolError("worker response protocol version mismatch")
    request_id = payload["request_id"]
    if not isinstance(request_id, str) or not REQUEST_ID_RE.fullmatch(request_id):
        raise WorkerProtocolError("worker response request_id is invalid")
    status = payload["status"]
    if not isinstance(status, str) or status not in WORKER_STATUSES:
        raise WorkerProtocolError("worker response status is invalid")
    actual = payload["actual_canonical"]
    exception_type = _validate_exception_type(payload["exception_type"])
    stdout_excerpt = _validate_excerpt(payload["stdout_excerpt"], "stdout_excerpt")
    stderr_excerpt = _validate_excerpt(payload["stderr_excerpt"], "stderr_excerpt")

    if status == WORKER_STATUS_COMPLETED:
        if actual is None:
            raise WorkerProtocolError("COMPLETED observation needs actual_canonical")
        if exception_type is not None:
            raise WorkerProtocolError("COMPLETED observation must not carry an exception")
        _validate_actual_canonical(actual)
    else:
        if actual is not None:
            raise WorkerProtocolError("non-COMPLETED observation must not carry actual_canonical")

    return WorkerObservation(
        status=status,
        actual_canonical=actual,
        exception_type=exception_type,
        stdout_excerpt=stdout_excerpt,
        stderr_excerpt=stderr_excerpt,
        request_id=request_id,
    )
