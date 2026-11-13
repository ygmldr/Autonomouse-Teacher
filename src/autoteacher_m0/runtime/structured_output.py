"""Dedicated E1-02 project JSON/Pydantic contract and DATA-ONLY Mock probe.

This module never imports the SDK, accepts a production Runtime/RunRecord,
constructs a credentialed process, or changes Live authorization. Retry here is
only deterministic OFFLINE invalid-structure retry, NOT SDK/provider retry.
"""
from dataclasses import asdict, dataclass
import json
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, StrictBool, field_validator

from autoteacher_m0.contracts import ErrorCode, RunRecord, RunRequest, RuntimeFailure
from autoteacher_m0.runtime.mock_adapter import MockRuntime

MAX_E1_JSON_BYTES = 4096
INVALID_OUTPUT_MESSAGE = "E1-02 output failed the strict JSON/Pydantic contract"


class E1Output(BaseModel):
    """Exact E1-02 answer, not a general-purpose skill lookup schema.

    Call validate_e1_json for untrusted text: raw Pydantic ValidationError objects
    must never be exported. StrictBool is intentional; Literal[True] alone can
    accept Python-equal integer 1 in some versions.
    """
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True,
                              hide_input_in_errors=True)
    skill_id: Literal["binary_search"]
    ready: StrictBool

    @field_validator("ready")
    @classmethod
    def _must_be_ready(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError("E1-02 requires ready=true")
        return value


def _unique_members(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON member")
        result[key] = value
    return result


def _reject_constant(_value: str) -> None:
    raise ValueError("non-standard JSON constant")


def validate_e1_json(text: str) -> E1Output:
    """Validate one whole UTF-8 JSON object; do not repair/extract/coerce it.

    No raw text, Pydantic detail, bad field name/value or original exception chain
    leaves this boundary, even when the input contains an invented key sentinel.
    The fixed 4096-byte cap is a defensive parser bound, not an acceptance waiver.
    """
    output = None
    try:
        if type(text) is not str or len(text) > MAX_E1_JSON_BYTES:
            raise ValueError("invalid JSON input")
        if len(text.encode("utf-8")) > MAX_E1_JSON_BYTES:
            raise ValueError("JSON byte limit")
        document = json.loads(text, object_pairs_hook=_unique_members,
                              parse_constant=_reject_constant)
        output = E1Output.model_validate(document)
    except (ValueError, TypeError, RecursionError, UnicodeError):
        # Raise only AFTER leaving the except block: even __context__ cannot
        # retain the Pydantic/JSON exception or a substring of the input.
        pass
    if output is None:
        raise RuntimeFailure(ErrorCode.INVALID_OUTPUT, INVALID_OUTPUT_MESSAGE)
    return output


@dataclass(frozen=True)
class E1MockAttempt:
    number: int
    run_id: str
    status: str
    error_code: str | None


@dataclass(frozen=True)
class E1MockResult:
    status: str
    output: E1Output | None
    attempts: tuple[E1MockAttempt, ...]
    error_code: str | None

    def to_dict(self) -> dict:
        return {"case_id": "E1-02", "mode": "mock", "route_id": "mock",
                "model_label": "deepseek-flash", "status": self.status,
                "output": self.output.model_dump() if self.output is not None else None,
                "attempts": [asdict(attempt) for attempt in self.attempts],
                "error_code": self.error_code, "billable_cost_usd": "0",
                "real_sdk_e1_02": "BLOCKED"}


def _stable_error(code: object) -> str:
    return str(code) if isinstance(code, str) and code in {item.value for item in ErrorCode} else str(ErrorCode.SDK_ERROR)


def _run_mock_once(runtime: MockRuntime, request: RunRequest) -> RunRecord:
    record = None
    error = None
    try:
        record = runtime.run(request)
    except RuntimeFailure as exc:
        error = _stable_error(exc.code)
    except Exception:
        error = str(ErrorCode.SDK_ERROR)
    if error is not None:
        raise RuntimeFailure(error, "E1-02 offline Mock execution failed")
    if type(record) is not RunRecord:
        raise RuntimeFailure(ErrorCode.SDK_ERROR, "E1-02 offline Mock record invalid")
    if (record.route_id, record.case_id, record.candidate_id, record.session_id,
            record.metadata.get("mode"), record.metadata.get("provider"),
            record.metadata.get("model")) != (
            "mock", request.case_id, request.candidate_id, request.session_id,
            "mock", "mock", "deepseek-flash"):
        raise RuntimeFailure(ErrorCode.SECURITY_BLOCKED, "E1-02 requires local Mock provenance")
    if record.status != "SUCCESS":
        raise RuntimeFailure(_stable_error(record.error_code), "E1-02 offline Mock run unsuccessful")
    return record


def run_e1_mock_validation(*, responses: tuple[str, ...] | None = None,
                           max_retries: int = 0) -> E1MockResult:
    """Generate a fixed local Mock request, then validate with at most ONE retry.

    responses is deterministic fixture DATA, not a callable, Runtime, provider or
    production record. If supplied it has exactly max_retries+1 string entries.
    With None the real existing MockRuntime JSON branch supplies each response.
    Only INVALID_OUTPUT from validation of a SUCCESSful local Mock record is
    retryable. Transport/security/provenance failures are terminal and sanitized.
    No fixture is sent to a model; no invalid raw text is retained in the result.
    """
    if type(max_retries) is not int or max_retries not in (0, 1):
        raise ValueError("E1-02 offline retries must be integer 0 or 1")
    if responses is not None and (
        type(responses) is not tuple or len(responses) != max_retries + 1
        or any(type(item) is not str for item in responses)
    ):
        raise ValueError("E1-02 response fixtures must match the bounded attempt count")
    attempts = []
    with MockRuntime() as runtime:
        for index in range(max_retries + 1):
            request = RunRequest(
                case_id="E1-02", prompt='Return JSON {"skill_id":"binary_search","ready":true}.',
                candidate_id="e1-02-offline-json", session_id="json-" + uuid4().hex,
                provider="mock", model="deepseek-flash", route_id="mock",
            )
            record = _run_mock_once(runtime, request)
            text = record.text if responses is None else responses[index]
            output = None
            validation_error = None
            try:
                output = validate_e1_json(text)
            except RuntimeFailure as exc:
                validation_error = _stable_error(exc.code)
            if validation_error is not None:
                if validation_error != ErrorCode.INVALID_OUTPUT:
                    # Never retry security/runtime failures. Replace diagnostics
                    # outside except so even an injected failure retains no chain.
                    raise RuntimeFailure(validation_error, "E1-02 validation aborted")
                attempts.append(E1MockAttempt(index + 1, record.run_id, "ERROR", validation_error))
            else:
                attempts.append(E1MockAttempt(index + 1, record.run_id, "SUCCESS", None))
                return E1MockResult("SUCCESS", output, tuple(attempts), None)
    return E1MockResult("ERROR", None, tuple(attempts), str(ErrorCode.INVALID_OUTPUT))
