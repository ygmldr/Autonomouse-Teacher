"""G3-C trusted Controller (offline Fake chain; no DSH/Key/network).

G3-C scope implemented here:
* per-``transport_id`` cancellation state with executable pre-send/post-send
  checkpoints (never a process-global Event);
* admission enforcement before Reserve/Claim/Fake (output bound, valid-call
  quota, durable per-call attempt/request identity, byte-derived conservative
  input bound and a real monotonic deadline);
* validated Fake ``kind:usage`` -> DSH ``chunk:{type:'usage'}`` conversion, at
  most once and never after ``finish``;
* a full trusted Receipt/Observation document persisted at
  ``RESPONSE_OBSERVED`` and one authoritative restart reconciliation path that
  first verifies Attempt/Receipt identity/nonce/digests and then consults the
  Broker's read-only reservation status (OK/FAILED/PENDING);
* deterministic Broker error-code mapping; unknown Broker codes never become
  the client-side ``UNKNOWN_FIELD``.

No real Key/model/external HTTP is used or reachable from this module.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import signal
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from autoteacher_m0.bridge.admission import Admission, AdmissionError, load_admission
from autoteacher_m0.accounting.observation import (
    ProviderObservation, observation_digest,
)
from autoteacher_m0.bridge.protocol import (
    ERROR_CODES, Envelope, validate_chunk_payload, validate_error_payload,
    validate_request_payload,
)
from autoteacher_m0.bridge.attempts import AttemptJournal
from autoteacher_m0.bridge.broker_client import BrokerClient, BrokerClientError
from autoteacher_m0.bridge.fake_backend import FakeBackend
from autoteacher_m0.bridge.ipc_server import BridgeServer
from autoteacher_m0.security.egress import (
    ClaimResult, EgressBoundary, EgressPolicy, EgressRequest,
    PreparedProviderRequest, TrustedEgressTransport, canonical_json,
    prepared_call_id, prepared_request_digest, prepared_schema_error,
)

ROUTE = "offline-test-only-g3b"
MODEL = "fixture-bridge-v1"
OBSERVATION_SCHEMA = "m0.g3c.observation.v1"
FEE_POLICY_VERSION = "fixture-synthetic-v1"
INPUT_BOUND_KIND = "utf8_bytes_upper_bound"
SYNTHETIC_FIXTURE_ONLY = True
ABSOLUTE_DEADLINE_SECONDS = 30.0
MAX_CANCEL_STATES = 256
_CANCEL_PRUNE_TARGET = 128
_USAGE_FIELDS = frozenset({"inputTokens", "cacheReadTokens", "cacheWriteTokens",
                           "outputTokens", "reasoningTokens", "totalTokens"})
_FINISH_KINDS = frozenset({"stop", "tool-calls", "max-tokens", "aborted", "error", "blocked"})

# Broker v1 raw code -> (preferred additive G3-C protocol code, existing-code
# fallback used until Agent A's additive protocol enum is merged). The preferred
# code is selected only when it is actually part of protocol.ERROR_CODES, so the
# fallback path is always a valid frozen frame and never UNKNOWN_FIELD.
_BROKER_CODE_TARGETS = {
    "CALL_ID_CONFLICT": ("BROKER_CALL_ID_CONFLICT", "CLAIM_DENIED"),
    "IDEMPOTENCY_CONFLICT": ("BROKER_IDEMPOTENCY_CONFLICT", "CLAIM_DENIED"),
    "ALREADY_SETTLED": ("BROKER_ALREADY_SETTLED", "SETTLEMENT_UNCERTAIN"),
    "ALREADY_FAILED": ("BROKER_ALREADY_FAILED", "SETTLEMENT_UNCERTAIN"),
    "INVALID_USAGE": ("BROKER_INVALID_USAGE", "USAGE_INVALID"),
    "BROKER_TIMEOUT": ("BROKER_TIMEOUT", "SETTLEMENT_UNCERTAIN"),
    "DEADLINE_EXCEEDED": ("DEADLINE_EXCEEDED", "SETTLEMENT_UNCERTAIN"),
}
_BROKER_PRE_SEND_FALLBACKS = {
    "BUDGET_EXCEEDED": "BUDGET_DENIED",
    "MESSAGE_LIMIT": "BUDGET_DENIED",
    "ROUTE_BLOCKED": "ROUTE_MISMATCH",
    "UNKNOWN_RESERVATION": "CLAIM_DENIED",
    "RESERVATION_NOT_PENDING": "CLAIM_DENIED",
    "RESERVATION_ALREADY_CLAIMED": "CLAIM_DENIED",
    "CALL_LINK_MISMATCH": "CLAIM_DENIED",
    "UNBOUND_CALL": "CLAIM_DENIED",
    "INVALID_CALL_ID": "REQUEST_INVALID",
    "INVALID_REQUEST_DIGEST": "REQUEST_INVALID",
    "BUDGET_BOUND_BLOCKED": "BUDGET_DENIED",
    "SCOPE_BLOCKED": "BUDGET_DENIED",
    "UNKNOWN_SCOPE": "INTERNAL",
    "INVALID_USAGE": "USAGE_INVALID",
}


def broker_protocol_code(raw_code: object) -> str:
    """Map one Broker/client raw code to a frozen IPC code deterministically."""
    if isinstance(raw_code, str) and raw_code in ERROR_CODES:
        return raw_code
    if isinstance(raw_code, str) and raw_code in _BROKER_CODE_TARGETS:
        preferred, fallback = _BROKER_CODE_TARGETS[raw_code]
        return preferred if preferred in ERROR_CODES else fallback
    if isinstance(raw_code, str) and raw_code in _BROKER_PRE_SEND_FALLBACKS:
        fallback = _BROKER_PRE_SEND_FALLBACKS[raw_code]
        return fallback if fallback in ERROR_CODES else "INTERNAL"
    if isinstance(raw_code, str) and raw_code in {"BROKER_EOF", "BROKER_IO_ERROR",
                                                  "BROKER_EXITED", "BROKER_BAD_REPLY",
                                                  "BROKER_UNAVAILABLE"}:
        preferred, fallback = "BROKER_ERROR", "INTERNAL"
        return preferred if preferred in ERROR_CODES else fallback
    preferred = "BROKER_ERROR"
    return preferred if preferred in ERROR_CODES else "INTERNAL"


def deadline_protocol_code() -> str:
    return "DEADLINE_EXCEEDED" if "DEADLINE_EXCEEDED" in ERROR_CODES else "SETTLEMENT_UNCERTAIN"


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _hex32(value: object) -> bool:
    return (isinstance(value, str) and len(value) == 32
            and all(char in "0123456789abcdef" for char in value))


class BridgeError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class _Cancelled(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class _DeadlineExceeded(Exception):
    pass


@dataclass(frozen=True)
class ControllerConfig:
    admission_path: str
    broker_config_path: str
    fake_script: str
    receipt_dir: str
    attempt_db: str
    python: str = sys.executable
    fake_python: str | None = None
    expected_uid: int = 65534


class _BoundClaimer:
    def __init__(self, broker: BrokerClient):
        self.broker = broker
        self.deadline: float | None = None

    def claim_bound(self, request: EgressRequest, *, expected_route_id: str,
                    expected_model: str) -> ClaimResult:
        kwargs = dict(call_id=request.call_id,
                      reservation_id=request.reservation_id,
                      request_digest=request.request_digest,
                      expected_route_id=expected_route_id,
                      expected_model=expected_model)
        if hasattr(self.broker, "request"):
            kwargs["deadline_monotonic"] = self.deadline
        reply = self.broker.claim(**kwargs)
        if reply.get("ok") and reply.get("code") == "CLAIMED":
            return ClaimResult(True, "CLAIMED", (), reply.get("claim"))
        return ClaimResult(False, reply.get("code", "CLAIM_DENIED"), (), reply.get("claim"))


@dataclass
class _CancelState:
    event: threading.Event
    reason: str | None
    terminal: bool
    touched: float


@dataclass
class _FakeAnalysis:
    authoritative: bool
    usage: dict | None
    completeness: str
    chunks: list[dict]
    finish_kind: str | None
    failure_code: str | None
    terminal_error: bool


class TrustedController:
    def __init__(self, admission: Admission, *, broker: BrokerClient,
                 fake: FakeBackend, attempts: AttemptJournal,
                 expected_uid: int = 65534, register_admission: bool = True):
        self.admission = admission
        self.broker = broker
        self.fake = fake
        self.attempts = attempts
        self.expected_uid = expected_uid
        self.instance_id = "ctl-" + uuid.uuid4().hex[:16]
        self.calls = 0
        self.rejected_calls = 0
        self.deadline_seconds = min(admission.deadline_ms / 1000.0,
                                    ABSOLUTE_DEADLINE_SECONDS)
        self._quota_lock = threading.RLock()
        self._cancel_lock = threading.Lock()
        # One trusted Fake child at a time: the Fake backend is single-flight and
        # this lock also keeps Broker claim/settle ordering deterministic. The
        # admission quota is still allocated atomically before this lock.
        self._send_lock = threading.Lock()
        self._cancellations: dict[str, _CancelState] = {}
        if register_admission:
            self.attempts.register_admission(admission.admission_id, admission.sha256,
                                             admission.run_id, self.instance_id)
        self.boundary = EgressBoundary(EgressPolicy(
            host_ports={"g3b-fake.local": frozenset({9000})},
            methods=frozenset({"POST"}), path_prefix="/v1/g3b/",
            approved_routes=frozenset({(ROUTE, MODEL)}), max_tokens=1024,
            max_attempts=1, require_reservation=True,
            allow_files=False, allow_images=False, allow_store=False),
            claimer=_BoundClaimer(broker))
        self.transport = TrustedEgressTransport(self.boundary, provider=None)

    # -- cancellation contract ----------------------------------------
    def _state_for_start(self, transport_id: str) -> _CancelState:
        with self._cancel_lock:
            state = self._cancellations.get(transport_id)
            if state is None or state.terminal:
                state = _CancelState(threading.Event(), None, False, time.monotonic())
                self._cancellations[transport_id] = state
                self._prune_cancellations_locked()
            state.touched = time.monotonic()
            return state

    def _prune_cancellations_locked(self) -> None:
        if len(self._cancellations) <= MAX_CANCEL_STATES:
            return
        terminal = [(st.touched, tid) for tid, st in self._cancellations.items()
                    if st.terminal]
        for _, tid in sorted(terminal)[: max(1, len(self._cancellations) - _CANCEL_PRUNE_TARGET)]:
            self._cancellations.pop(tid, None)

    def _finish_transport(self, transport_id: str) -> None:
        with self._cancel_lock:
            state = self._cancellations.get(transport_id)
            if state is not None:
                state.terminal = True
                state.touched = time.monotonic()

    def cancel(self, *, transport_id: str, reason: str) -> None:
        """Cancel exactly one transport's stream; repeated/unknown ids are safe.

        A cancel that arrives before ``handle_envelope`` starts is remembered in
        the bounded per-transport registry so the later handler observes it at
        its first checkpoint. A late duplicate for an already-terminal transport
        is a no-op and never leaks into a future stream reusing the same id.
        """
        if not isinstance(transport_id, str) or not transport_id:
            raise ValueError("transport_id must be a non-empty string")
        if not isinstance(reason, str) or not reason:
            raise ValueError("reason must be a non-empty string")
        with self._cancel_lock:
            state = self._cancellations.get(transport_id)
            if state is None:
                state = _CancelState(threading.Event(), None, False, time.monotonic())
                self._cancellations[transport_id] = state
                self._prune_cancellations_locked()
            if state.terminal:
                return
            if state.reason is None:
                state.reason = reason[:128]
            state.event.set()
            state.touched = time.monotonic()

    @staticmethod
    def _checkpoint(state: _CancelState | None, deadline: float, stage: str) -> None:
        if state is not None and state.event.is_set():
            raise _Cancelled(state.reason or "aborted")
        if time.monotonic() > deadline:
            raise _DeadlineExceeded(stage)

    # -- admission / prepared request ---------------------------------
    def _prepare(self, payload: Mapping[str, object], step: int):
        """Backward-compatible two-value form used by G3-B tests/callers."""
        prepared, request, _business_digest, _input_bound = self._prepare_checked(payload, step)
        return prepared, request

    def _prepare_checked(self, payload: Mapping[str, object], step: int):
        validate_request_payload(payload)
        if payload.get("provider") != ROUTE or payload.get("model") != MODEL:
            raise BridgeError("ROUTE_MISMATCH")
        max_tokens = payload.get("maxTokens")
        if type(max_tokens) is not int or not 1 <= max_tokens <= 1024:
            raise BridgeError("REQUEST_INVALID")
        if max_tokens > self.admission.max_output_tokens:
            # Admission output bound is enforced before Reserve/Claim/Fake.
            raise BridgeError("BUDGET_DENIED")
        messages = payload.get("messages", [])
        if isinstance(messages, list):
            for message in messages:
                content = message.get("content") if isinstance(message, Mapping) else None
                if not isinstance(content, list):
                    continue
                for block in content:
                    if isinstance(block, Mapping) and block.get("type") in {
                            "image", "file", "attachment", "store"}:
                        raise BridgeError("REQUEST_INVALID")
        tool_hashes = []
        admission_tools = dict(self.admission.tool_schemas)
        tools = payload.get("tools", [])
        if not isinstance(tools, list):
            raise BridgeError("REQUEST_INVALID")
        for tool in tools:
            if not isinstance(tool, Mapping) or not isinstance(tool.get("name"), str):
                raise BridgeError("REQUEST_INVALID")
            try:
                raw = canonical_json(tool).encode("utf-8")
            except (TypeError, ValueError):
                raise BridgeError("REQUEST_INVALID") from None
            digest = hashlib.sha256(raw).hexdigest()
            if admission_tools.get(tool["name"]) != digest:
                raise BridgeError("ADMISSION_TOOL_SCHEMA_MISMATCH")
            tool_hashes.append(tool)
        # Conservative input bound. We cannot prove a model/tokenizer token count,
        # so we refuse to pretend the old fixed 1024-token estimate was a bound.
        # Every BPE token covers at least one input byte, so the canonical UTF-8
        # byte length of the model-visible input is a provable upper bound. It is
        # marked synthetic_fixture_only because this is a no-Key fixture chain.
        input_material = {"system": payload.get("system") or "",
                          "messages": list(payload.get("messages", [])),
                          "tools": [(tool["name"], canonical_json(tool)) for tool in tool_hashes]}
        input_bytes = len(canonical_json(input_material).encode("utf-8"))
        if input_bytes > self.admission.max_input_tokens:
            raise BridgeError("BUDGET_DENIED")
        input_bound = max(1, input_bytes)
        prepared = PreparedProviderRequest(
            schema_version="m0.prepared.v1", scope_id=self.admission.scope_id,
            run_id=self.admission.run_id, logical_step=step, attempt_index=0,
            route_id=ROUTE, provider=ROUTE, model=MODEL,
            host="g3b-fake.local", port=9000, method="POST", path="/v1/g3b/chat",
            stream=True, max_output_tokens=max_tokens,
            system=payload.get("system") or "", messages=tuple(payload.get("messages", [])),
            tools=tuple(tool_hashes), response_format=None, retry_policy=None,
            has_files=False, has_images=False, store=False, call_id="", request_digest="")
        error = prepared_schema_error(prepared)
        if error:
            raise BridgeError(error)
        digest = prepared_request_digest(prepared)
        prepared = PreparedProviderRequest(**{**prepared.__dict__, "request_digest": digest,
                                               "call_id": prepared_call_id(prepared)})
        request = EgressRequest(
            logical_stream_id=f"stream-{step}", reservation_id="", attempt_ordinal=1,
            route_id=ROUTE, model=MODEL, host="g3b-fake.local", port=9000,
            method="POST", path="/v1/g3b/chat", stream=True, max_tokens=max_tokens,
            call_id=prepared.call_id, request_digest=prepared.request_digest)
        business_digest = _sha256({
            "v": 1, "sessionId": payload.get("sessionId"),
            "provider": payload.get("provider"), "model": payload.get("model"),
            "messages": payload.get("messages"), "tools": payload.get("tools"),
            "system": payload.get("system"), "maxTokens": payload.get("maxTokens"),
            "purpose": payload.get("purpose"),
        })
        return prepared, request, business_digest, input_bound

    # -- envelope handling --------------------------------------------
    def handle_envelope(self, env: Envelope):
        if not isinstance(env, Envelope):
            raise BridgeError("BAD_TYPE")
        transport_id = getattr(env, "transport_id", "")
        state = self._state_for_start(transport_id) if isinstance(transport_id, str) else None
        deadline = time.monotonic() + self.deadline_seconds
        try:
            if state is not None and state.event.is_set():
                yield self._error_envelope(env, "CANCELLED")
                return
            try:
                validate_request_payload(env.payload)
            except Exception as exc:
                code = getattr(exc, "code", "REQUEST_INVALID")
                if isinstance(env.payload, Mapping) and set(env.payload) & {
                        "call_id", "reservation_id", "request_digest", "authorized", "admission"}:
                    code = "ADMISSION_SELF_AUTH_DENIED"
                yield self._error_envelope(env, code)
                return
            try:
                frames = self._handle_payload(env.payload, transport_id, deadline, state)
            except _Cancelled:
                yield self._error_envelope(env, "CANCELLED")
                return
            except _DeadlineExceeded:
                yield self._error_envelope(env, deadline_protocol_code())
                return
            except Exception as exc:
                yield self._error_envelope(env, self._exception_code(exc))
                return
            seq = env.seq + 1
            for frame in frames:
                if state is not None and state.event.is_set() and frame.get("kind") == "finish":
                    # Post-send cancellation has already completed conservative
                    # accounting; do not emit a success finish after the client
                    # cancelled. The accounting state (not this frame) is truth.
                    yield self._error_envelope(env, "CANCELLED")
                    return
                kind = frame.get("kind")
                if kind == "receipt":
                    continue
                if kind == "chunk":
                    payload = {"chunk": frame["chunk"]}
                    try:
                        validate_chunk_payload(payload)
                    except Exception:
                        yield self._error_envelope(env, "REQUEST_INVALID")
                        return
                elif kind == "finish":
                    payload = {"reason": frame["reason"]}
                elif kind == "error":
                    payload = frame["payload"]
                else:
                    continue
                yield Envelope(1, kind, env.transport_id, seq, payload, None)
                seq += 1
        finally:
            self._finish_transport(transport_id) if isinstance(transport_id, str) else None

    def _error_envelope(self, env: Envelope, code: object) -> Envelope:
        safe = self._normalize_code(code) if isinstance(code, str) else "INTERNAL"
        if safe not in ERROR_CODES:
            safe = "INTERNAL"
        return Envelope(1, "error", env.transport_id, env.seq + 1,
                        validate_error_payload(safe), None)

    @staticmethod
    def _normalize_code(code: str) -> str:
        if code in ERROR_CODES:
            return code
        return broker_protocol_code(code)

    @classmethod
    def _exception_code(cls, exc: BaseException) -> str:
        code = getattr(exc, "code", None)
        if isinstance(code, str):
            return cls._normalize_code(code)
        text = str(exc)
        if text in ERROR_CODES or text in _BROKER_CODE_TARGETS or text in _BROKER_PRE_SEND_FALLBACKS:
            return broker_protocol_code(text)
        if isinstance(exc, _DeadlineExceeded):
            return deadline_protocol_code()
        if isinstance(exc, BrokerClientError):
            return broker_protocol_code("BROKER_ERROR")
        return "INTERNAL"

    # -- main request path --------------------------------------------
    def _handle_payload(self, payload: Mapping[str, object], transport_id: str,
                        deadline: float, state: _CancelState | None) -> list[dict]:
        with self._send_lock:
            return self._handle_payload_serial(payload, transport_id, deadline, state)

    def _handle_payload_serial(self, payload: Mapping[str, object], transport_id: str,
                               deadline: float,
                               state: _CancelState | None) -> list[dict]:
        attempt_id: str | None = None
        intent_id: str | None = None
        call_id: str | None = None
        try:
            with self._quota_lock:
                self._checkpoint(state, deadline, "admission")
                if self.calls >= self.admission.max_calls:
                    raise BridgeError("BUDGET_DENIED")
                step = self.calls
                try:
                    prepared, request, business_digest, input_bound = self._prepare_checked(payload, step)
                except BaseException:
                    self.rejected_calls += 1
                    raise
                if (self.attempts.attempt_for_call(prepared.call_id) is not None
                        or self.attempts.intent_for_call(prepared.call_id) is not None):
                    raise BridgeError("ATTEMPT_ALREADY_STARTED")
                self.attempts.claim_request_identity(
                    scope_id=self.admission.scope_id,
                    identity_digest=business_digest, call_id=prepared.call_id,
                    logical_step=step)
                call_id = prepared.call_id
                self.calls += 1
            self._checkpoint(state, deadline, "prepare")
            mode = self.admission.fake_scenario
            if mode == "tool":
                mode = "tool_once" if step == 0 else "tool_final"
            nonce = os.urandom(16).hex()
            fake_payload = {
                "schema": "m0.g3b.fake.v1", "call_id": prepared.call_id,
                "prepared_digest": prepared.request_digest, "route_id": ROUTE,
                "model": MODEL, "messages": list(prepared.messages),
                "tools": list(prepared.tools), "system": prepared.system,
                "max_output_tokens": prepared.max_output_tokens, "stream": True,
                "mode": mode,
                "nonce": nonce,
            }
            payload_bytes = canonical_json(fake_payload).encode("utf-8")
            payload_digest = hashlib.sha256(payload_bytes).hexdigest()
            task_id = "g3b-" + hashlib.sha256(self.admission.run_id.encode()).hexdigest()[:32]
            self._checkpoint(state, deadline, "before_reserve")
            reserved = self._broker_reserve(task_id=task_id, input_tokens=input_bound,
                                            output_tokens=prepared.max_output_tokens,
                                            call_id=prepared.call_id, deadline=deadline)
            reservation_id = reserved["reservation_id"]
            intent_id = self.attempts.record_intent(
                scope_id=self.admission.scope_id, call_id=prepared.call_id,
                reservation_id=reservation_id, prepared_digest=prepared.request_digest,
                payload_digest=payload_digest, payload_length=len(payload_bytes))
            self._crash("after_reserve_before_claim")
            try:
                self._checkpoint(state, deadline, "after_reserve")
            except (_Cancelled, _DeadlineExceeded) as exc:
                self.attempts.mark_intent_held(
                    intent_id, reason=f"PRE_SEND_ABORT:{type(exc).__name__}")
                raise
            request = EgressRequest(**{**request.__dict__, "reservation_id": reservation_id,
                                       "estimated_cost_usd": "0.001"})
            approved_tools = frozenset(canonical_json(tool) for tool in prepared.tools)
            self.boundary.claimer.deadline = deadline
            decision = self.boundary.claim_dispatch_for_request(
                prepared, request, expected_reservation_route_model=(ROUTE, MODEL),
                approved_tool_schemas=approved_tools)
            if not decision.allowed or decision.permission is None:
                raw = decision.claim.code if decision.claim is not None else "CLAIM_DENIED"
                self.attempts.mark_intent_held(intent_id, reason=f"CLAIM_DENIED:{raw}")
                raise BridgeError(broker_protocol_code(raw))
            self.attempts.mark_intent_claimed(intent_id)
            self._crash("after_claim_before_attempt_start")
            try:
                self._checkpoint(state, deadline, "after_claim")
            except (_Cancelled, _DeadlineExceeded) as exc:
                # Claimed permission is process-local and is never reused; the
                # reservation is held conservatively and the intent stays durable.
                self.attempts.mark_intent_held(
                    intent_id, reason=f"PRE_SEND_ABORT:{type(exc).__name__}")
                raise
            attempt_id = self.attempts.begin_attempt(
                scope_id=prepared.scope_id, call_id=prepared.call_id,
                reservation_id=reservation_id, prepared_digest=prepared.request_digest,
                payload_digest=payload_digest, payload_length=len(payload_bytes),
                run_id=prepared.run_id, logical_step=prepared.logical_step, mode=mode,
                input_bound_kind=INPUT_BOUND_KIND, input_bound_tokens=input_bound,
                fee_policy_version=FEE_POLICY_VERSION)
            self._crash("after_attempt_start_before_fake_send")
            self._checkpoint(state, deadline, "before_send")
            holder: dict[str, object] = {}

            def provider(_req):
                if state is not None and state.event.is_set():
                    holder["cancelled_before_send"] = True
                    raise _Cancelled(state.reason or "aborted")
                try:
                    receipt, frames = self._invoke_fake(payload_bytes, nonce,
                                                        deadline, state)
                except _DeadlineExceeded:
                    holder["deadline"] = True
                    raise
                except _Cancelled:
                    holder["cancelled_before_send"] = True
                    raise
                except BaseException as exc:
                    if self._is_timeout_exception(exc):
                        holder["deadline"] = True
                        raise _DeadlineExceeded("fake_timeout")
                    if self._is_cancel_exception(exc):
                        receipt = getattr(exc, "receipt", None)
                        if receipt is not None:
                            # The send boundary was crossed; keep the trusted
                            # receipt and let normal accounting finish.
                            holder["receipt"] = receipt
                            holder["frames"] = list(getattr(receipt, "frames", ()) or ())
                            holder["cancelled_after_send"] = True
                        else:
                            holder["cancelled_before_send"] = True
                        raise _Cancelled(state.reason if state is not None else "aborted")
                    receipt = getattr(exc, "receipt", None)
                    if receipt is not None:
                        holder["receipt"] = receipt
                        holder["frames"] = list(getattr(receipt, "frames", ()) or ())
                        holder["fake_error"] = exc
                        return {"status": 200, "usage": receipt.usage, "error": None}
                    holder["fake_error"] = exc
                    raise
                holder["receipt"] = receipt
                holder["frames"] = frames
                holder["sent"] = getattr(self.fake, "sent_payload_digest", None)
                mapped_usage = receipt.usage if isinstance(receipt.usage, Mapping) else None
                return {"status": 200, "usage": mapped_usage, "error": None}

            self.transport.dispatch(request, decision.permission, provider=provider)
            if holder.get("cancelled_before_send"):
                if attempt_id is not None:
                    self.attempts.mark_settlement_uncertain(
                        attempt_id, reason="CANCELLED_BEFORE_FAKE_SEND")
                raise _Cancelled(state.reason if state is not None else "aborted")
            if holder.get("deadline"):
                if attempt_id is not None:
                    self.attempts.mark_settlement_uncertain(
                        attempt_id, reason="DEADLINE_BEFORE_FAKE_RESULT")
                raise _DeadlineExceeded("fake")
            receipt = holder.get("receipt")
            if receipt is None or not hasattr(receipt, "raw_sha256"):
                if holder.get("fake_error") is not None:
                    if attempt_id is not None:
                        self.attempts.mark_settlement_uncertain(
                            attempt_id, reason="FAKE_IO_ERROR")
                    raise BridgeError("FAKE_IO_ERROR")
                if attempt_id is not None:
                    self.attempts.mark_settlement_uncertain(
                        attempt_id, reason="FAKE_RECEIPT_MISSING")
                raise BridgeError("SETTLEMENT_UNCERTAIN")
            self._crash("after_fake_receive_before_response")
            sent_digest = holder.get("sent") or getattr(receipt, "raw_sha256", None)
            if (receipt.raw_sha256 != payload_digest
                    or sent_digest != payload_digest
                    or receipt.raw_length != len(payload_bytes)
                    or receipt.nonce != nonce):
                self.attempts.mark_settlement_uncertain(
                    attempt_id, reason="FAKE_RECEIPT_MISMATCH")
                raise BridgeError("FAKE_RECEIPT_MISMATCH")
            analysis = self._analyze_fake_frames(
                receipt, allow_incomplete_stream=bool(holder.get("cancelled_after_send")))
            observation, document = self._build_observation_document(
                prepared, reservation_id, payload_digest, len(payload_bytes),
                receipt, analysis, input_bound, attempt_id=attempt_id)
            self.attempts.mark_response_observed(
                attempt_id, receipt_id=receipt.receipt_id,
                receipt_json=json.dumps(document, sort_keys=True))
            self._crash("after_response_before_settlement")
            camel = self._camel_usage(analysis.usage)
            if analysis.authoritative:
                reply = self._broker_settle(reservation_id=reservation_id, usage=camel,
                                            deadline=deadline)
            else:
                reply = self._broker_fail(reservation_id=reservation_id, usage=camel,
                                          deadline=deadline)
            self._crash("after_broker_settle_before_journal_mark")
            self._apply_completion_reply(
                reply, attempt_id=attempt_id, reservation_id=reservation_id,
                authoritative=analysis.authoritative, deadline=deadline)
            self._crash("after_journal_mark_before_sdk_finish")
            self._crash("after_settlement_before_sdk_finish")
            if state is not None and state.event.is_set():
                raise _Cancelled(state.reason or "aborted")
            if time.monotonic() > deadline:
                raise _DeadlineExceeded("after_settlement")
            return self._terminal_frames(analysis)
        except (AdmissionError, BridgeError, BrokerClientError, ValueError,
                _Cancelled, _DeadlineExceeded) as exc:
            if intent_id is not None:
                try:
                    self.attempts.mark_intent_held(
                        intent_id, reason=f"REQUEST_ABORT:{type(exc).__name__}")
                except Exception:
                    pass
            if attempt_id is not None and call_id is not None:
                try:
                    row = self.attempts.attempt_for_call(call_id)
                except Exception:
                    row = None
                if row is not None and row.get("state") == "ATTEMPT_STARTED":
                    # Send may already have happened; never label it free. A
                    # RESPONSE_OBSERVED row is left intact for reconcile.
                    try:
                        self.attempts.mark_settlement_uncertain(
                            attempt_id, reason=f"REQUEST_ABORT:{type(exc).__name__}")
                    except Exception:
                        pass
            raise

    @staticmethod
    def _is_timeout_exception(exc: BaseException) -> bool:
        name = type(exc).__name__
        code = getattr(exc, "code", None)
        return (isinstance(exc, TimeoutError) or name in {"FakeTimeout", "BrokerTimeoutError"}
                or code in {"BROKER_TIMEOUT", "FAKE_TIMEOUT"})

    @staticmethod
    def _is_cancel_exception(exc: BaseException) -> bool:
        name = type(exc).__name__
        code = getattr(exc, "code", None)
        return name == "FakeCancelled" or (
            code == "SETTLEMENT_UNCERTAIN" and "CANCEL" in str(exc).upper())

    # -- Fake invocation ----------------------------------------------
    def _invoke_fake(self, payload_bytes: bytes, nonce: str, deadline: float,
                     state: _CancelState | None):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise _DeadlineExceeded("before_fake")
        if state is not None and state.event.is_set():
            raise _Cancelled(state.reason or "aborted")
        stream = getattr(self.fake, "stream", None)
        if callable(stream):
            frames: list[dict] = []
            iterator = stream(payload_bytes, deadline_monotonic=deadline,
                              cancel_event=state.event if state is not None else None)
            for frame in iterator:
                frames.append(frame)
                if time.monotonic() > deadline:
                    raise _DeadlineExceeded("fake_stream")
            receipt = getattr(self.fake, "last_receipt", None)
            if receipt is None:
                path = Path(getattr(self.fake, "receipt_dir", "")) / f"rcpt-{nonce}.json"
                receipt = self._receipt_from_file(path, nonce)
            return receipt, frames
        holder: dict[str, object] = {}

        def run() -> None:
            try:
                holder["receipt"] = self.fake.send_exact_bytes(payload_bytes, nonce)
            except BaseException as exc:  # preserved for the caller thread
                holder["error"] = exc

        worker = threading.Thread(target=run, name="g3c-fake-call", daemon=True)
        worker.start()
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise _DeadlineExceeded("fake")
            worker.join(timeout=min(0.05, remaining))
            if not worker.is_alive():
                break
        if "error" in holder:
            raise holder["error"]  # type: ignore[misc]
        receipt = holder.get("receipt")
        return receipt, list(getattr(receipt, "frames", ()) or ())

    def _receipt_from_file(self, path: Path, nonce: str):
        try:
            doc = json.loads(Path(path).read_text())
        except (OSError, ValueError, json.JSONDecodeError):
            raise ValueError("FAKE_RECEIPT_MISMATCH") from None
        if doc.get("nonce") != nonce:
            raise ValueError("FAKE_RECEIPT_MISMATCH")
        from autoteacher_m0.bridge.fake_backend import FakeReceipt
        return FakeReceipt(doc["receipt_id"], doc["raw_sha256"], doc["raw_length"],
                           doc["mode"], doc.get("usage"), doc["nonce"], Path(path), ())

    # -- usage / receipt validation -----------------------------------
    @staticmethod
    def _classify_usage(usage: object) -> tuple[dict | None, str]:
        if usage is None:
            return None, "MISSING"
        if not isinstance(usage, Mapping):
            return None, "INVALID"
        values = dict(usage)
        if set(values) - _USAGE_FIELDS:
            return None, "INVALID"
        clean: dict[str, int] = {}
        for key, value in values.items():
            if type(value) is not int or value < 0:
                return None, "INVALID"
            clean[key] = value
        if not {"inputTokens", "outputTokens"} <= set(clean):
            return clean, "PARTIAL"
        if not {"cacheReadTokens", "cacheWriteTokens"} <= set(clean):
            return clean, "PARTIAL"
        return clean, "AUTHORITATIVE"

    @staticmethod
    def _camel_usage(usage: Mapping | None) -> dict | None:
        if not isinstance(usage, Mapping):
            return None
        result = {}
        for key in ("inputTokens", "cacheReadTokens", "cacheWriteTokens",
                    "outputTokens", "reasoningTokens", "totalTokens"):
            value = usage.get(key)
            if type(value) is int and value >= 0:
                result[key] = value
        return result or None

    def _analyze_fake_frames(self, receipt,
                             *, allow_incomplete_stream: bool = False) -> _FakeAnalysis:
        usage_frame = None
        chunks: list[dict] = []
        finish_reason: dict | None = None
        invalid: str | None = None
        for frame in getattr(receipt, "frames", ()) or ():
            if not isinstance(frame, Mapping) or not isinstance(frame.get("kind"), str):
                invalid = "FAKE_FRAME_INVALID"
                break
            kind = frame["kind"]
            if finish_reason is not None:
                invalid = "FRAME_AFTER_FINISH"
                break
            if kind == "usage":
                if usage_frame is not None:
                    invalid = "MULTIPLE_USAGE"
                    break
                usage_frame = frame.get("usage")
            elif kind == "chunk":
                try:
                    validate_chunk_payload({"chunk": frame.get("chunk")})
                except Exception:
                    invalid = "FAKE_CHUNK_INVALID"
                    break
                chunks.append({"kind": "chunk", "chunk": dict(frame["chunk"])})
            elif kind == "finish":
                reason = frame.get("reason")
                if not isinstance(reason, Mapping) or reason.get("kind") not in _FINISH_KINDS:
                    invalid = "FAKE_FINISH_INVALID"
                    break
                if reason.get("kind") in {"error", "aborted"}:
                    failure = reason.get("failure")
                    if not (isinstance(failure, Mapping)
                            and set(failure) == {"code", "message"}
                            and isinstance(failure.get("code"), str)
                            and isinstance(failure.get("message"), str)):
                        # Fake's legacy error finish omits failure{code,message}.
                        # We refuse to forward it and normalize terminal error.
                        invalid = "FAKE_FINISH_ERROR_SCHEMA"
                finish_reason = dict(reason)
            elif kind == "error":
                invalid = "FAKE_ERROR_FRAME"
                break
            else:
                invalid = "FAKE_FRAME_UNKNOWN"
                break

        frame_usage, frame_state = self._classify_usage(usage_frame)
        receipt_usage, receipt_state = self._classify_usage(receipt.usage)
        failure: str | None = None
        terminal_error = bool(
            finish_reason is not None
            and finish_reason.get("kind") in {"error", "aborted"})
        if finish_reason is None and invalid is None:
            invalid = "FAKE_EOF"
        if invalid == "FAKE_FINISH_ERROR_SCHEMA":
            terminal_error = True
        if terminal_error:
            failure = "FAKE_PROVIDER_ERROR"
        if invalid is not None and invalid not in {"FAKE_FINISH_ERROR_SCHEMA"}:
            allow_missing_stream = (
                allow_incomplete_stream and invalid == "FAKE_EOF"
                and receipt_state == "AUTHORITATIVE")
            if not allow_missing_stream:
                failure = {
                    "FAKE_EOF": "FAKE_EOF",
                    "FAKE_FRAME_INVALID": "FAKE_IO_ERROR",
                    "FAKE_CHUNK_INVALID": "FAKE_IO_ERROR",
                    "FAKE_FINISH_INVALID": "FAKE_IO_ERROR",
                    "FAKE_ERROR_FRAME": "FAKE_IO_ERROR",
                    "FAKE_FRAME_UNKNOWN": "FAKE_IO_ERROR",
                    "FRAME_AFTER_FINISH": "FRAME_AFTER_FINISH",
                    "MULTIPLE_USAGE": "MULTIPLE_USAGE",
                }.get(invalid, "FAKE_IO_ERROR")
                return _FakeAnalysis(False, receipt_usage, "INVALID", chunks,
                                     None, failure, terminal_error)
        if usage_frame is None:
            if (allow_incomplete_stream and receipt_state == "AUTHORITATIVE"
                    and invalid in {None, "FAKE_EOF"}):
                # Post-send Cancel: the trusted receipt-first Usage is complete,
                # but the stream did not finish. Accounting may still settle the
                # real synthetic usage; the DSH terminal frame is CANCELLED.
                return _FakeAnalysis(True, receipt_usage, "AUTHORITATIVE",
                                     chunks, None, None, False)
            return _FakeAnalysis(False, receipt_usage,
                                 "MISSING" if receipt_state != "INVALID" else "INVALID",
                                 chunks, finish_reason.get("kind") if finish_reason else None,
                                 failure or "USAGE_MISSING", terminal_error)
        if frame_state == "INVALID":
            return _FakeAnalysis(False, None, "INVALID", chunks,
                                 finish_reason.get("kind") if finish_reason else None,
                                 failure or "USAGE_INVALID", terminal_error)
        if frame_state == "PARTIAL" or receipt_state != "AUTHORITATIVE":
            return _FakeAnalysis(False, frame_usage or receipt_usage, "PARTIAL", chunks,
                                 finish_reason.get("kind") if finish_reason else None,
                                 failure or "USAGE_PARTIAL", terminal_error)
        if canonical_json(frame_usage) != canonical_json(receipt_usage):
            return _FakeAnalysis(False, None, "INVALID", chunks,
                                 finish_reason.get("kind") if finish_reason else None,
                                 "FAKE_RECEIPT_MISMATCH", terminal_error)
        return _FakeAnalysis(False if terminal_error else True, frame_usage,
                             "AUTHORITATIVE", chunks,
                             finish_reason.get("kind") if finish_reason else None,
                             failure, terminal_error)

    @staticmethod
    def _terminal_frames(analysis: _FakeAnalysis) -> list[dict]:
        frames = list(analysis.chunks)
        if analysis.authoritative and not analysis.terminal_error:
            if analysis.usage is not None:
                frames.append({"kind": "chunk",
                               "chunk": {"type": "usage", "usage": dict(analysis.usage)}})
            kind = analysis.finish_kind if analysis.finish_kind in {
                "stop", "tool-calls", "max-tokens", "blocked"} else "stop"
            frames.append({"kind": "finish", "reason": {"kind": kind}})
            return frames
        code = analysis.failure_code or "FAKE_PROVIDER_ERROR"
        frames.append({"kind": "finish", "reason": {
            "kind": "error",
            "failure": {"code": code, "message": "synthetic fake provider did not produce "
                                                 "authoritative usage"}}})
        return frames

    # -- observation document -----------------------------------------
    def _make_observation(self, receipt_id: str, raw_sha256: str, usage: object,
                          usage_state: str) -> tuple[ProviderObservation, str]:
        if usage_state in {"AUTHORITATIVE", "PARTIAL"}:
            counters = self._camel_usage(usage) or {}
        else:
            # An invalid classification must never leave counters in a MISSING
            # observation (that would silently turn bad usage into evidence).
            counters = {}
        if usage_state == "AUTHORITATIVE":
            status, raw_hash, error_kind = "AUTHORITATIVE", raw_sha256, "none"
        elif usage_state == "PARTIAL":
            status, raw_hash, error_kind = "PARTIAL", raw_sha256, "none"
        else:
            status, raw_hash, error_kind = "MISSING", None, "unknown"
        observation = ProviderObservation.from_mapping({
            "requested_route": ROUTE, "observed_route": ROUTE,
            "model_reported": MODEL, "provider_request_id": receipt_id,
            "usage_raw_hash": raw_hash,
            "input": counters.get("inputTokens"),
            "cache_read": counters.get("cacheReadTokens"),
            "cache_write": counters.get("cacheWriteTokens"),
            "output": counters.get("outputTokens"),
            "reasoning": counters.get("reasoningTokens"),
            "cost_estimate": None, "cost_source": "synthetic_fixture_cost",
            "error_kind": error_kind, "complete_or_uncertain": status})
        observation.validate_for_policy("inclusive")
        return observation, status

    def _build_observation_document(self, prepared, reservation_id: str,
                                    payload_digest: str, payload_length: int,
                                    receipt, analysis: _FakeAnalysis,
                                    input_bound: int,
                                    attempt_id: str | None = None
                                    ) -> tuple[ProviderObservation, dict]:
        observation, status = self._make_observation(
            receipt.receipt_id, receipt.raw_sha256, analysis.usage,
            analysis.completeness)
        obs_digest = observation_digest(observation)
        receipt_usage = self._camel_usage(receipt.usage)
        document = {
            "schema": OBSERVATION_SCHEMA,
            "attempt_id": attempt_id,
            "scope_id": prepared.scope_id,
            "run_id": prepared.run_id,
            "logical_step": prepared.logical_step,
            "call_id": prepared.call_id,
            "reservation_id": reservation_id,
            "route_id": ROUTE,
            "model": MODEL,
            "prepared_digest": prepared.request_digest,
            "receipt": {
                "receipt_id": receipt.receipt_id,
                "raw_sha256": receipt.raw_sha256,
                "raw_length": receipt.raw_length,
                "mode": receipt.mode,
                "nonce": receipt.nonce,
            },
            "payload_digest": payload_digest,
            "payload_length": payload_length,
            "usage": receipt_usage,
            "usage_digest": None if receipt_usage is None else _sha256(receipt_usage),
            "observation": observation.to_mapping(),
            "observation_digest": obs_digest,
            "completeness": status,
            "fee_policy_version": FEE_POLICY_VERSION,
            "synthetic": SYNTHETIC_FIXTURE_ONLY,
            "synthetic_fixture_only": SYNTHETIC_FIXTURE_ONLY,
            "provenance": "trusted_fake_receipt",
            "trusted_source": "controller.fake_receipt",
            "input_bound": {
                "tokens": input_bound, "kind": INPUT_BOUND_KIND,
                "synthetic_fixture_only": SYNTHETIC_FIXTURE_ONLY,
            },
            "created_utc": _now_utc(),
        }
        # Digest over every field except journal_digest itself. Recovery
        # recomputes this before it trusts any counter/nonce/usage claim.
        document["journal_digest"] = _sha256(document)
        return observation, document

    # -- Broker calls --------------------------------------------------
    def _broker_reserve(self, *, task_id: str, input_tokens: int, output_tokens: int,
                        call_id: str, deadline: float) -> dict:
        self._check_deadline(deadline)
        try:
            kwargs = dict(task_id=task_id, route_id=ROUTE, model=MODEL,
                          input_tokens=input_tokens, output_tokens=output_tokens,
                          call_id=call_id)
            if hasattr(self.broker, "request"):
                kwargs["deadline_monotonic"] = deadline
            reply = self.broker.reserve(**kwargs)
        except BrokerClientError as exc:
            raise BridgeError(broker_protocol_code(str(exc))) from None
        if not reply.get("ok"):
            raise BridgeError(broker_protocol_code(reply.get("code", "BUDGET_DENIED")))
        return reply

    def _broker_settle(self, *, reservation_id: str, usage: dict | None,
                       deadline: float) -> dict:
        return self._completion_call("settle", reservation_id, usage, deadline)

    def _broker_fail(self, *, reservation_id: str, usage: dict | None,
                     deadline: float) -> dict:
        return self._completion_call("fail", reservation_id, usage, deadline)

    def _completion_call(self, op: str, reservation_id: str, usage: dict | None,
                         deadline: float) -> dict:
        self._check_deadline(deadline)
        try:
            kwargs = {"reservation_id": reservation_id, "usage": usage}
            if hasattr(self.broker, "request"):
                kwargs["deadline_monotonic"] = deadline
            if op == "settle":
                return self.broker.settle(**kwargs)
            return self.broker.fail(**kwargs)
        except BrokerClientError:
            # The settlement/ack may have been committed before the lost reply.
            # Never claim success; recovery re-reads the authoritative status.
            raise BridgeError("SETTLEMENT_UNCERTAIN") from None

    def _broker_status(self, reservation_id: str, deadline: float) -> dict:
        try:
            self._check_deadline(deadline)
        except _DeadlineExceeded:
            return {"ok": False, "code": "DEADLINE_EXCEEDED"}
        try:
            request = getattr(self.broker, "request", None)
            status_helper = getattr(self.broker, "reservation_status", None)
            if callable(status_helper):
                return status_helper(reservation_id, deadline_monotonic=deadline)
            if callable(request):
                return request("reservation_status",
                               {"reservation_id": reservation_id},
                               deadline_monotonic=deadline)
            legacy = getattr(self.broker, "_request", None)
            if callable(legacy):
                # Transitional compatibility for the pre-G3-C trusted client.
                return legacy("reservation_status", reservation_id=reservation_id)
            return {"ok": False, "code": "BROKER_ERROR"}
        except BrokerClientError as exc:
            return {"ok": False, "code": broker_protocol_code(str(exc))}
        except Exception:
            return {"ok": False, "code": "BROKER_ERROR"}

    @staticmethod
    def _check_deadline(deadline: float) -> None:
        if time.monotonic() > deadline:
            raise _DeadlineExceeded("broker")

    def _apply_completion_reply(self, reply: Mapping, *, attempt_id: str,
                                reservation_id: str, authoritative: bool,
                                deadline: float) -> bool:
        code = reply.get("code")
        if reply.get("ok") and code in {"SETTLED", "FAILED"}:
            if authoritative:
                self.attempts.mark_settled(
                    attempt_id, settlement_json=json.dumps(reply, sort_keys=True))
                return True
            self.attempts.mark_worst_case(attempt_id, reason="USAGE_NOT_AUTHORITATIVE")
            return False
        if code in {"ALREADY_SETTLED", "ALREADY_FAILED"}:
            status = self._broker_status(reservation_id, deadline)
            if status.get("ok") and status.get("status") == "OK":
                # P1-1: ALREADY_SETTLED must never be miswritten as held.
                self.attempts.mark_settled(
                    attempt_id,
                    settlement_json=json.dumps({"archived_from_broker": status},
                                               sort_keys=True))
                return True
            if status.get("ok") and status.get("status") == "FAILED":
                self.attempts.mark_worst_case(attempt_id, reason="BROKER_ALREADY_FAILED")
                return False
            self.attempts.mark_settlement_uncertain(
                attempt_id, reason="ALREADY_SETTLED_STATUS_UNKNOWN")
            raise BridgeError("SETTLEMENT_UNCERTAIN")
        self.attempts.mark_settlement_uncertain(attempt_id, reason="SETTLE_REJECTED")
        raise BridgeError(broker_protocol_code(code or "SETTLEMENT_UNCERTAIN"))

    # -- startup reconciliation ---------------------------------------
    def reconcile_on_startup(self, receipt_dir: str | None = None) -> list[dict]:
        """Single authoritative recovery path; never sends a new Provider call."""
        deadline = time.monotonic() + max(self.deadline_seconds, 1.0)
        receipt_root = Path(receipt_dir) if receipt_dir else Path(self.fake.receipt_dir)
        for intent in self.attempts.pending_intents():
            if intent.get("state") == "CONSUMED":
                continue
            status = self._broker_status(intent["reservation_id"], deadline)
            if status.get("ok") and status.get("status") in {"OK", "FAILED"}:
                self.attempts.mark_intent_held(
                    intent["intent_id"],
                    reason=f"BROKER_ALREADY_{status['status']}_NO_SEND_RECORD")
            else:
                self.attempts.mark_intent_held(
                    intent["intent_id"], reason="CRASH_BEFORE_SEND_NO_EVIDENCE")
        for row in self.attempts.pending_attempts():
            attempt_id = row["attempt_id"]
            if row["state"] != "SETTLED" and row["state"] != "WORST_CASE_HELD":
                if row["state"] == "ATTEMPT_STARTED" and receipt_root is not None:
                    upgraded = self._upgrade_from_receipt_file(row, receipt_root)
                    if upgraded:
                        row = self.attempts.attempt_for_call(row["call_id"]) or row
            if row["state"] in {"SETTLED", "WORST_CASE_HELD"}:
                continue
            if row["state"] == "ATTEMPT_STARTED":
                self.attempts.mark_settlement_uncertain(
                    attempt_id, reason="NO_RECEIPT_AFTER_CRASH")
                continue
            verified, reason = self._verify_receipt_document(row, receipt_root)
            if not verified:
                status_reply = self._broker_status(row["reservation_id"], deadline)
                if status_reply.get("ok") and status_reply.get("status") == "OK":
                    # A-04: the Broker's final state is authoritative; a local
                    # evidence defect must not miswrite a committed OK settlement
                    # as held/uncertain.
                    self.attempts.mark_settled(
                        attempt_id,
                        settlement_json=json.dumps(
                            {"archived_from_broker": status_reply,
                             "local_evidence_reason": reason}, sort_keys=True))
                    continue
                if status_reply.get("ok") and status_reply.get("status") == "FAILED":
                    self.attempts.mark_worst_case(
                        attempt_id, reason=f"BROKER_ALREADY_FAILED:{reason}")
                    continue
                self.attempts.mark_settlement_uncertain(attempt_id, reason=reason)
                continue
            status_reply = self._broker_status(row["reservation_id"], deadline)
            if not status_reply.get("ok"):
                self.attempts.mark_settlement_uncertain(
                    attempt_id, reason="BROKER_STATUS_UNAVAILABLE")
                continue
            status = status_reply.get("status")
            if status == "OK":
                self.attempts.mark_settled(
                    attempt_id,
                    settlement_json=json.dumps({"archived_from_broker": status_reply},
                                               sort_keys=True))
                continue
            if status == "FAILED":
                self.attempts.mark_worst_case(attempt_id, reason="BROKER_ALREADY_FAILED")
                continue
            if status != "PENDING":
                self.attempts.mark_settlement_uncertain(
                    attempt_id, reason="BROKER_STATUS_UNKNOWN")
                continue
            document = verified
            authoritative = document.get("completeness") == "AUTHORITATIVE"
            usage = document.get("usage")
            camel = self._camel_usage(usage)
            try:
                if authoritative:
                    reply = self._broker_settle(reservation_id=row["reservation_id"],
                                                 usage=camel, deadline=deadline)
                else:
                    reply = self._broker_fail(reservation_id=row["reservation_id"],
                                              usage=camel, deadline=deadline)
            except (BridgeError, BrokerClientError):
                self.attempts.mark_settlement_uncertain(
                    attempt_id, reason="RECONCILE_SETTLE_FAILED")
                continue
            try:
                self._apply_completion_reply(
                    reply, attempt_id=attempt_id, reservation_id=row["reservation_id"],
                    authoritative=authoritative, deadline=deadline)
            except BridgeError:
                self.attempts.mark_settlement_uncertain(
                    attempt_id, reason="RECONCILE_SETTLE_REJECTED")
        return self.attempts.attempts()

    def _upgrade_from_receipt_file(self, row: dict, receipt_root: Path) -> bool:
        if not isinstance(row.get("payload_digest"), str) or len(row["payload_digest"]) != 64:
            return False
        for path in sorted(receipt_root.glob("rcpt-*.json")):
            try:
                doc = json.loads(path.read_text())
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            if doc.get("raw_sha256") != row["payload_digest"]:
                continue
            if doc.get("raw_length") != row["payload_length"]:
                continue
            if not _hex32(doc.get("nonce")):
                return False
            usage, usage_state = self._classify_usage(doc.get("usage"))
            if doc.get("usage") is not None and usage is None:
                return False
            observation, status = self._make_observation(
                str(doc.get("receipt_id")), row["payload_digest"], usage, usage_state)
            receipt_usage = self._camel_usage(usage)
            document = {
                "schema": OBSERVATION_SCHEMA,
                "attempt_id": row["attempt_id"],
                "scope_id": row["scope_id"],
                "run_id": row.get("run_id") or self.admission.run_id,
                "logical_step": row.get("logical_step") if row.get("logical_step") is not None else 0,
                "call_id": row["call_id"],
                "reservation_id": row["reservation_id"],
                "route_id": ROUTE,
                "model": MODEL,
                "prepared_digest": row["prepared_digest"],
                "receipt": {
                    "receipt_id": doc["receipt_id"],
                    "raw_sha256": doc["raw_sha256"],
                    "raw_length": doc["raw_length"],
                    "mode": doc.get("mode"),
                    "nonce": doc["nonce"],
                },
                "payload_digest": row["payload_digest"],
                "payload_length": row["payload_length"],
                "usage": receipt_usage,
                "usage_digest": None if receipt_usage is None else _sha256(receipt_usage),
                "observation": observation.to_mapping(),
                "observation_digest": observation_digest(observation),
                "completeness": status,
                "fee_policy_version": row.get("fee_policy_version") or FEE_POLICY_VERSION,
                "synthetic": SYNTHETIC_FIXTURE_ONLY,
                "synthetic_fixture_only": SYNTHETIC_FIXTURE_ONLY,
                "provenance": "trusted_fake_receipt",
                "trusted_source": "controller.fake_receipt",
                "input_bound": {
                    "tokens": row.get("input_bound_tokens") or 1,
                    "kind": row.get("input_bound_kind") or INPUT_BOUND_KIND,
                    "synthetic_fixture_only": SYNTHETIC_FIXTURE_ONLY,
                },
                "created_utc": row.get("created_utc") or _now_utc(),
            }
            document["journal_digest"] = _sha256(document)
            self.attempts.mark_response_observed(
                row["attempt_id"], receipt_id=doc.get("receipt_id"),
                receipt_json=json.dumps(document, sort_keys=True))
            return True
        return False

    def _verify_receipt_document(self, row: dict,
                                 receipt_root: Path | None) -> tuple[dict | None, str]:
        try:
            document = json.loads(row.get("receipt_json") or "null")
        except (TypeError, ValueError, json.JSONDecodeError):
            return None, "RECEIPT_DOCUMENT_INVALID"
        if not isinstance(document, dict) or document.get("schema") != OBSERVATION_SCHEMA:
            return None, "RECEIPT_DOCUMENT_SCHEMA_INVALID"
        recorded_digest = document.pop("journal_digest", None)
        if not isinstance(recorded_digest, str) or len(recorded_digest) != 64:
            return None, "RECEIPT_JOURNAL_DIGEST_MISSING"
        if recorded_digest != _sha256(document):
            return None, "RECEIPT_JOURNAL_DIGEST_MISMATCH"
        required = {"attempt_id", "scope_id", "run_id", "call_id", "reservation_id",
                    "route_id", "model", "prepared_digest", "payload_digest",
                    "payload_length", "fee_policy_version", "provenance",
                    "trusted_source", "synthetic_fixture_only"}
        if not required <= set(document) or any(
                document.get(field) is None for field in required):
            return None, "RECEIPT_DOCUMENT_INCOMPLETE"
        if document.get("call_id") != row["call_id"]:
            return None, "RECEIPT_CALL_MISMATCH"
        if document.get("reservation_id") != row["reservation_id"]:
            return None, "RECEIPT_RESERVATION_MISMATCH"
        if document.get("attempt_id") not in (None, row["attempt_id"]):
            return None, "RECEIPT_ATTEMPT_MISMATCH"
        if document.get("prepared_digest") != row["prepared_digest"]:
            return None, "RECEIPT_PREPARED_DIGEST_MISMATCH"
        if document.get("payload_digest") != row["payload_digest"]:
            return None, "RECEIPT_PAYLOAD_DIGEST_MISMATCH"
        if document.get("payload_length") != row["payload_length"]:
            return None, "RECEIPT_LENGTH_MISMATCH"
        if document.get("route_id") != ROUTE or document.get("model") != MODEL:
            return None, "RECEIPT_ROUTE_MISMATCH"
        if document.get("synthetic_fixture_only") is not True or document.get("synthetic") is not True:
            return None, "RECEIPT_PROVENANCE_MISSING"
        if document.get("provenance") != "trusted_fake_receipt":
            return None, "RECEIPT_PROVENANCE_MISSING"
        if not isinstance(document.get("fee_policy_version"), str) or \
                not document.get("fee_policy_version"):
            return None, "RECEIPT_FEE_POLICY_MISSING"
        receipt = document.get("receipt")
        if not isinstance(receipt, dict):
            return None, "RECEIPT_IDENTITY_MISSING"
        for key in ("receipt_id", "raw_sha256", "raw_length", "mode", "nonce"):
            if key not in receipt:
                return None, "RECEIPT_IDENTITY_MISSING"
        if receipt.get("raw_sha256") != row["payload_digest"]:
            return None, "RECEIPT_DIGEST_MISMATCH"
        if receipt.get("raw_length") != row["payload_length"]:
            return None, "RECEIPT_LENGTH_MISMATCH"
        if not _hex32(receipt.get("nonce")):
            return None, "RECEIPT_NONCE_INVALID"
        usage = document.get("usage")
        if usage is not None:
            clean, state = self._classify_usage(usage)
            if clean is None or state == "INVALID":
                return None, "RECEIPT_USAGE_INVALID"
            if document.get("usage_digest") != _sha256(clean):
                return None, "RECEIPT_USAGE_DIGEST_MISMATCH"
            document["usage"] = clean
        elif document.get("usage_digest") is not None:
            return None, "RECEIPT_USAGE_DIGEST_MISMATCH"
        try:
            observation = ProviderObservation.from_mapping(document.get("observation"))
        except Exception:
            return None, "RECEIPT_OBSERVATION_INVALID"
        if document.get("observation_digest") != observation_digest(observation):
            return None, "RECEIPT_OBSERVATION_DIGEST_MISMATCH"
        if document.get("completeness") not in {"AUTHORITATIVE", "PARTIAL", "MISSING", "INVALID"}:
            return None, "RECEIPT_COMPLETENESS_INVALID"
        if receipt_root is None:
            return None, "RECEIPT_FILE_UNAVAILABLE"
        path = receipt_root / f"rcpt-{receipt['nonce']}.json"
        try:
            file_doc = json.loads(path.read_text())
        except (OSError, ValueError, json.JSONDecodeError):
            return None, "RECEIPT_FILE_MISSING"
        if (file_doc.get("raw_sha256") != receipt.get("raw_sha256")
                or file_doc.get("raw_length") != receipt.get("raw_length")
                or file_doc.get("nonce") != receipt.get("nonce")
                or file_doc.get("mode") != receipt.get("mode")):
            return None, "RECEIPT_FILE_MISMATCH"
        file_usage, _ = self._classify_usage(file_doc.get("usage"))
        if (file_usage is None) != (usage is None):
            return None, "RECEIPT_FILE_USAGE_MISMATCH"
        if file_usage is not None and canonical_json(file_usage) != canonical_json(usage):
            return None, "RECEIPT_FILE_USAGE_MISMATCH"
        return document, "OK"

    # -- test crash hook ----------------------------------------------
    def _crash(self, hook: str) -> None:
        """Test-only crash hook; disabled unless launcher sets both env vars."""
        if os.environ.get("G3B_TEST_MODE") == "1" and os.environ.get("G3B_CRASH_HOOK") == hook:
            os._exit(97)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args(argv)
    config = json.loads(Path(args.config).read_text())
    required = {"admission_path", "broker_config_path", "fake_script", "receipt_dir",
                "attempt_db", "socket_path", "python", "expected_uid"}
    if not isinstance(config, dict) or set(config) - (required | {"fake_python"}):
        raise SystemExit("CONFIG_INVALID")
    if required - set(config):
        raise SystemExit("CONFIG_INVALID")
    for key in ("admission_path", "broker_config_path", "fake_script", "receipt_dir",
                "attempt_db", "socket_path"):
        value = config[key]
        if not isinstance(value, str) or not value.startswith("/") or ".." in Path(value).parts:
            raise SystemExit("CONFIG_INVALID")
    socket_path = Path(config["socket_path"])
    socket_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.path.lexists(socket_path):
        socket_path.unlink()
    admission = load_admission(config["admission_path"], expected_uid=config.get("expected_uid", 65534))
    broker = BrokerClient(config_path=config["broker_config_path"], python=config["python"])
    broker.start()
    fake = FakeBackend(script=config["fake_script"], receipt_dir=config["receipt_dir"],
                       python=config.get("fake_python", config["python"]),
                       mode=admission.fake_scenario)
    attempts = AttemptJournal(config["attempt_db"])
    controller = TrustedController(admission, broker=broker, fake=fake, attempts=attempts,
                                   expected_uid=config.get("expected_uid", 65534),
                                   register_admission=False)
    # G3-C2-04 frozen order: recover old attempts BEFORE consuming a new
    # admission. An ADMISSION_REPLAYED therefore cannot strand durable state.
    controller.reconcile_on_startup(config.get("receipt_dir"))
    try:
        attempts.register_admission(admission.admission_id, admission.sha256,
                                    admission.run_id, controller.instance_id)
    except ValueError as exc:
        if str(exc) == "ADMISSION_REPLAYED":
            sys.stderr.write("ADMISSION_REPLAYED_AFTER_RECOVERY\n")
            broker.close()
            fake.close()
            attempts.close()
            return 3
        raise
    server = BridgeServer(controller, config["socket_path"])

    def _stop(_signum, _frame):
        server.shutdown()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    try:
        server.serve_forever()
    finally:
        broker.close()
        fake.close()
        attempts.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
