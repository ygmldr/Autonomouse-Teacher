"""Project-owned ABI v1; no SDK objects cross this boundary.

CLI integration: smoke uses AgentRuntime.run; paired/report are delegated to
experiments.cli.run_paired(*, artifact_dir: Path) / render_report(*,
artifact_dir: Path, experiment: str) once the integration task is opened.
Live requests are blocked before any SDK construction or credential inspection.
"""
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

CONTRACT_VERSION = "m0-runtime-v1"


class ErrorCode(StrEnum):
    PROVIDER_ERROR = "PROVIDER_ERROR"
    AUTH_ERROR = "AUTH_ERROR"
    RATE_LIMIT = "RATE_LIMIT"
    INVALID_MODEL = "INVALID_MODEL"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    TOOL_ERROR = "TOOL_ERROR"
    INVALID_OUTPUT = "INVALID_OUTPUT"
    EVAL_ERROR = "EVAL_ERROR"
    TIMEOUT = "TIMEOUT"
    SECURITY_BLOCKED = "SECURITY_BLOCKED"
    SESSION_NOT_FOUND = "SESSION_NOT_FOUND"
    SESSION_CORRUPT = "SESSION_CORRUPT"
    SESSION_BUSY = "SESSION_BUSY"
    INTERRUPTED = "INTERRUPTED"
    SDK_ERROR = "SDK_ERROR"


class RuntimeFailure(RuntimeError):
    """Only a stable code and sanitized message may leave a runtime."""
    def __init__(self, code: ErrorCode | str, message: str):
        self.code = str(code)
        super().__init__(message)


@dataclass(frozen=True)
class RunRequest:
    case_id: str
    prompt: str
    candidate_id: str
    session_id: str
    provider: str
    model: str
    route_id: str


@dataclass
class RunRecord:
    run_id: str
    case_id: str
    candidate_id: str
    session_id: str
    route_id: str
    text: str
    status: str
    events: list[dict[str, Any]]
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost_usd: float | None = None
    error_code: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class AgentRuntime(Protocol):
    def run(self, request: RunRequest) -> RunRecord: ...
    def resume(self, session_id: str, prompt: str) -> RunRecord: ...


# Event envelope: {"type": str, "sequence": int, "data": dict}.
# SDK-native payloads must be normalized/redacted first. status is
# SUCCESS / ERROR / BLOCKED / INTERRUPTED, not an experimental PASS claim.
# Mock records carry metadata["mode"] == "mock" and zero *mock* cost only;
# missing live token/cost values remain None (never silently zero).
