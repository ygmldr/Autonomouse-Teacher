"""Runtime compatibility imports; contracts live outside all adapters."""
from autoteacher_m0.contracts import AgentRuntime, ErrorCode, RunRecord, RunRequest, RuntimeFailure

__all__ = ["AgentRuntime", "ErrorCode", "RunRecord", "RunRequest", "RuntimeFailure"]
