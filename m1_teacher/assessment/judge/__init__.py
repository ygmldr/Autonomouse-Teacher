"""M1-B judge trust boundary: frozen worker protocol + bwrap confinement (B-PR1).

The package separates the *trusted* supervisor (owned by B-PR1's integration
workstream) from the *untrusted* execution worker:

* :mod:`~m1_teacher.assessment.judge.protocol` -- frozen ``m1b.judge.worker.v1``
  request/response shapes, strict parsing, canonical JSON and the fail-closed
  policy codes.  There is no verdict/passed field anywhere in the protocol;
  only the trusted supervisor compares actual vs expected.
* :mod:`~m1_teacher.assessment.judge.sandbox` -- ``BwrapSandbox``: bwrap OS
  confinement (user/pid/net/ipc/uts namespaces, non-root uid, read-only minimal
  rootfs, private tmpfs, rlimits, wall clock, process-group kill) with an
  explicit canary self-check.  Unavailable sandbox -> fail closed, no fallback
  to a bare subprocess.
* :mod:`~m1_teacher.assessment.judge.worker` -- ``UntrustedExecutionWorker``:
  runs one case per process and returns a :class:`WorkerObservation` only; it
  never receives ``expected``/hidden tests.

Default policy for real learner CODE remains ``UNTRUSTED_CODE_EXECUTION_BLOCKED``
until this boundary is independently reviewed and a supervisor integrates it;
this package itself never enables untrusted execution implicitly.
"""

from __future__ import annotations

from .protocol import (
    FORBIDDEN_FIELDS,
    JUDGE_INFRA_ERROR,
    JUDGE_SANDBOX_UNAVAILABLE,
    PROTOCOL_VERSION,
    REQUEST_FIELDS,
    RESPONSE_FIELDS,
    UNTRUSTED_CODE_EXECUTION_BLOCKED,
    WORKER_STATUSES,
    WORKER_STATUS_COMPLETED,
    WORKER_STATUS_IMPORT_ERROR,
    WORKER_STATUS_INFRA_ERROR,
    WORKER_STATUS_MISSING_FUNCTION,
    WORKER_STATUS_RAISED,
    WORKER_STATUS_SYNTAX_ERROR,
    WORKER_STATUS_TIMEOUT,
    WorkerObservation,
    WorkerProtocolError,
    build_request,
    canonical_json,
    infra_observation,
    new_request_id,
    parse_request,
    parse_worker_response,
    timeout_observation,
)
from .sandbox import (
    BWRAP_BINARY,
    WORKER_PYTHON,
    BwrapSandbox,
    SandboxLaunchError,
    SandboxResult,
    SandboxUnavailable,
)
from .worker import UntrustedExecutionWorker

__all__ = [
    # protocol constants / policy
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
    "REQUEST_FIELDS",
    "RESPONSE_FIELDS",
    "FORBIDDEN_FIELDS",
    # protocol API
    "WorkerObservation",
    "WorkerProtocolError",
    "build_request",
    "parse_request",
    "parse_worker_response",
    "canonical_json",
    "new_request_id",
    "infra_observation",
    "timeout_observation",
    # sandbox
    "BWRAP_BINARY",
    "WORKER_PYTHON",
    "BwrapSandbox",
    "SandboxLaunchError",
    "SandboxResult",
    "SandboxUnavailable",
    # worker
    "UntrustedExecutionWorker",
]
