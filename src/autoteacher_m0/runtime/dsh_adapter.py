"""Only module allowed to import deepseek_harness.

Official SDK 0.2.2rc2 ABI was statically inspected from its hashed PyPI wheel.
Every public live entry is intentionally fail-closed. No editable approval file,
flag, environment variable or injected callback unlocks this baseline. Independent
human review and a separate controller authorization design remain required.
"""
import hashlib
import importlib.metadata
import json
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from autoteacher_m0.contracts import ErrorCode, RunRecord, RunRequest, RuntimeFailure
from autoteacher_m0.settings import RuntimeSettings
from autoteacher_m0.storage.artifacts import safe_id, sanitize

SDK_VERSION = "0.2.2rc2"


def classify_error(exc: Exception) -> str:
    """Classify in memory; never export provider diagnostic text or credentials."""
    if isinstance(exc, RuntimeFailure):
        return exc.code
    if isinstance(exc, TimeoutError):
        return str(ErrorCode.TIMEOUT)
    status = getattr(exc, "status_code", None)
    if status is None:
        status = getattr(getattr(exc, "response", None), "status_code", None)
    # SDK RPC error codes need a captured wire fixture before mapping; arbitrary
    # JSON-RPC codes are not HTTP statuses. Tests inject HTTP-shaped exceptions.
    if status in (401, 403):
        return str(ErrorCode.AUTH_ERROR)
    if status == 429:
        return str(ErrorCode.RATE_LIMIT)
    if isinstance(status, int) and 500 <= status <= 599:
        return str(ErrorCode.PROVIDER_ERROR)
    return str(ErrorCode.SDK_ERROR)


def sdk_options(settings: RuntimeSettings) -> dict[str, Any]:
    """Pure mapping, not initialization or a claim of merged-profile safety."""
    return {
        "dsh_home": str(settings.dsh_home), "cwd": str(settings.workspace),
        "runtime_cwd": str(settings.workspace), "profile": settings.profile,
        "provider": settings.provider, "model": settings.model,
        "max_tokens": settings.max_tokens, "patches": (str(settings.patch),),
        "initialize_timeout_seconds": settings.timeout_seconds,
        "request_timeout_seconds": settings.timeout_seconds,
        "shutdown_timeout_seconds": 1.0,
        # No approval responder or automatic approval is installed.
        "approval_requests": False,
    }


def normalize_result(request: RunRequest, result: Any) -> RunRecord:
    """Normalize an SDK-shaped value, without publishing the SDK object itself.

    The pinned RunResult has no guaranteed token/cost/model-version fields.
    Preserve absence as None. An event/accounting integration must verify actual
    usage wire fields before any live billing can be enabled.
    """
    if result.session_id != request.session_id:
        raise RuntimeFailure(ErrorCode.SDK_ERROR, "SDK returned a different session identity")
    reason = result.finish_reason
    if reason == "completed":
        status, error = "SUCCESS", None
    elif reason in ("aborted", "cancelled"):
        status, error = "INTERRUPTED", str(ErrorCode.INTERRUPTED)
    elif reason == "max-tokens":
        status, error = "ERROR", str(ErrorCode.INVALID_OUTPUT)
    else:
        status, error = "ERROR", str(ErrorCode.PROVIDER_ERROR)
    events = []
    for sequence, event in enumerate(result.events):
        if not isinstance(event, dict) or not isinstance(event.get("type"), str):
            raise RuntimeFailure(ErrorCode.SDK_ERROR, "malformed SDK root event")
        events.append({"type": event["type"], "sequence": sequence,
                       "data": sanitize(event.get("data", {}))})
    return RunRecord(
        run_id=uuid4().hex, case_id=request.case_id, candidate_id=request.candidate_id,
        session_id=request.session_id, route_id=request.route_id,
        text=sanitize(result.final_response), status=status, events=events,
        input_tokens=None, output_tokens=None, estimated_cost_usd=None, error_code=error,
        metadata={"mode": "live", "sdk_version": SDK_VERSION, "provider": request.provider,
                  "model": request.model, "actual_model_version": None,
                  "provider_request_id": None, "finish_reason": reason,
                  "created_at": datetime.now(timezone.utc).isoformat(),
                  "prompt_sha256": hashlib.sha256(request.prompt.encode()).hexdigest(),
                  "usage_kind": "unavailable", "cost_kind": "unknown_not_zero"},
    )


class HarnessAdapter:
    def __init__(self, settings: RuntimeSettings):
        self.settings = settings

    @staticmethod
    def _require_live_authorization() -> None:
        raise RuntimeFailure(
            ErrorCode.SECURITY_BLOCKED,
            "Live disabled: independent human approval, credential boundary, safe merged "
            "profile, bounded execution and budget integration are not established",
        )

    def _new_harness(self):
        # Defense in depth: even a direct call cannot import/launch the SDK.
        self._require_live_authorization()
        if importlib.metadata.version("deepseek-harness-sdk") != SDK_VERSION:
            raise RuntimeFailure(ErrorCode.SDK_ERROR, "SDK version differs from frozen baseline")
        from deepseek_harness import DeepSeekHarness
        return DeepSeekHarness(**sdk_options(self.settings))

    def _context_path(self, session_id: str):
        return self.settings.dsh_home / "project-context" / (safe_id(session_id) + ".json")

    def _validate_route(self, request: RunRequest) -> None:
        if (request.provider, request.model, request.route_id) != (
            self.settings.provider, self.settings.model, self.settings.route_id
        ):
            raise RuntimeFailure(ErrorCode.SECURITY_BLOCKED, "unapproved route/model mismatch")

    def run(self, request: RunRequest) -> RunRecord:
        self._require_live_authorization()
        self._validate_route(request)
        # Currently unreachable, retained as the reviewed SDK lifecycle mapping.
        # request_timeout_seconds is NOT a total activity bound. Before unlocking,
        # add an independent external process watchdog and reserve worst-case cost.
        try:
            with self._new_harness() as harness:
                result = harness.run(request.prompt, session_id=request.session_id)
                record = normalize_result(request, result)
            target = self._context_path(request.session_id)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps({
                "case_id": request.case_id, "candidate_id": request.candidate_id,
                "session_id": request.session_id, "provider": request.provider,
                "model": request.model, "route_id": request.route_id, "prompt": "",
            }), encoding="utf-8")
            return record
        except Exception as exc:
            # No automatic retries: timeout does not prove provider work stopped.
            raise RuntimeFailure(classify_error(exc), "SDK activity failed; diagnostics withheld") from None

    def resume(self, session_id: str, prompt: str) -> RunRecord:
        self._require_live_authorization()
        try:
            document = json.loads(self._context_path(session_id).read_text(encoding="utf-8"))
            request = replace(RunRequest(**document), prompt=prompt)
        except FileNotFoundError:
            raise RuntimeFailure(ErrorCode.SESSION_NOT_FOUND, "project session context missing") from None
        except (ValueError, TypeError, KeyError):
            raise RuntimeFailure(ErrorCode.SESSION_CORRUPT, "project session context invalid") from None
        self._validate_route(request)
        try:
            with self._new_harness() as harness:
                # start_session() is NOT restoration; only this official API is.
                session = harness.resume_session(session_id)
                return normalize_result(request, session.run(prompt))
        except Exception as exc:
            raise RuntimeFailure(classify_error(exc), "SDK restoration failed; diagnostics withheld") from None


# Friendly alias; no second implementation or unofficial SDK wrapper.
DSHAdapter = HarnessAdapter
