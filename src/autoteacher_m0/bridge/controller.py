"""G3-B B2 trusted Controller (offline Fake chain; no DSH/Key/network)."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from autoteacher_m0.bridge.admission import Admission, AdmissionError, load_admission
from autoteacher_m0.accounting.observation import ProviderObservation
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


class BridgeError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


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

    def claim_bound(self, request: EgressRequest, *, expected_route_id: str,
                    expected_model: str) -> ClaimResult:
        reply = self.broker.claim(call_id=request.call_id,
                                  reservation_id=request.reservation_id,
                                  request_digest=request.request_digest,
                                  expected_route_id=expected_route_id,
                                  expected_model=expected_model)
        if reply.get("ok") and reply.get("code") == "CLAIMED":
            return ClaimResult(True, "CLAIMED", (), reply.get("claim"))
        return ClaimResult(False, reply.get("code", "CLAIM_DENIED"), (), reply.get("claim"))


class TrustedController:
    def __init__(self, admission: Admission, *, broker: BrokerClient,
                 fake: FakeBackend, attempts: AttemptJournal,
                 expected_uid: int = 65534):
        self.admission = admission
        self.broker = broker
        self.fake = fake
        self.attempts = attempts
        self.expected_uid = expected_uid
        self.instance_id = "ctl-" + uuid.uuid4().hex[:16]
        self.calls = 0
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

    def _crash(self, hook: str) -> None:
        """Test-only crash hook; disabled unless launcher sets both env vars."""
        if os.environ.get("G3B_TEST_MODE") == "1" and os.environ.get("G3B_CRASH_HOOK") == hook:
            os._exit(97)

    def reconcile_on_startup(self, receipt_dir: str | None = None) -> list[dict]:
        pending = self.attempts.reconcile_on_startup(receipt_dir)
        for row in pending:
            if row.get("state") in {"ATTEMPT_STARTED", "RESPONSE_OBSERVED"}:
                if not row.get("receipt_id"):
                    self.attempts.mark_settlement_uncertain(row["attempt_id"],
                                                             reason="NO_RECEIPT_AFTER_CRASH")
                else:
                    self.attempts.mark_worst_case(row["attempt_id"],
                                                   reason="RECEIPT_RECONCILED_NO_RESEND")
        return self.attempts.reconcile_on_startup()

    def _prepare(self, payload: Mapping[str, object], step: int) -> tuple[PreparedProviderRequest, EgressRequest]:
        validate_request_payload(payload)
        if payload.get("provider") != ROUTE or payload.get("model") != MODEL:
            raise BridgeError("ROUTE_MISMATCH")
        max_tokens = payload.get("maxTokens")
        if type(max_tokens) is not int or not 1 <= max_tokens <= 1024:
            raise BridgeError("REQUEST_INVALID")
        tool_hashes = []
        admission_tools = dict(self.admission.tool_schemas)
        tools = payload.get("tools", [])
        if not isinstance(tools, list):
            raise BridgeError("REQUEST_INVALID")
        for tool in tools:
            if not isinstance(tool, Mapping) or not isinstance(tool.get("name"), str):
                raise BridgeError("REQUEST_INVALID")
            raw = canonical_json(tool).encode("utf-8")
            digest = hashlib.sha256(raw).hexdigest()
            if admission_tools.get(tool["name"]) != digest:
                raise BridgeError("ADMISSION_TOOL_SCHEMA_MISMATCH")
            tool_hashes.append(tool)
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
        return prepared, request

    def handle_envelope(self, env: Envelope):
        if not isinstance(env, Envelope):
            raise BridgeError("BAD_TYPE")
        try:
            validate_request_payload(env.payload)
        except Exception as exc:
            code = getattr(exc, "code", "REQUEST_INVALID")
            if isinstance(env.payload, Mapping) and set(env.payload) & {
                    "call_id", "reservation_id", "request_digest", "authorized", "admission"}:
                code = "ADMISSION_SELF_AUTH_DENIED"
            yield Envelope(1, "error", env.transport_id, env.seq + 1,
                           validate_error_payload(code if code in ERROR_CODES else "REQUEST_INVALID"), None)
            return
        try:
            frames = self._handle_payload(env.payload)
        except Exception as exc:
            code = getattr(exc, "code", "INTERNAL")
            if code not in ERROR_CODES:
                code = "INTERNAL"
            yield Envelope(1, "error", env.transport_id, env.seq + 1,
                           validate_error_payload(code), None)
            return
        seq = env.seq + 1
        for frame in frames:
            kind = frame.get("kind")
            if kind == "receipt":
                continue
            if kind == "chunk":
                payload = {"chunk": frame["chunk"]}
                try:
                    validate_chunk_payload(payload)
                except Exception:
                    yield Envelope(1, "error", env.transport_id, seq,
                                   validate_error_payload("REQUEST_INVALID"), None)
                    return
            elif kind == "finish":
                payload = {"reason": frame["reason"]}
            elif kind == "error":
                payload = frame["payload"]
            else:
                continue
            yield Envelope(1, kind, env.transport_id, seq, payload, None)
            seq += 1

    def _handle_payload(self, payload: Mapping[str, object]) -> list[dict]:
        try:
            if self.calls >= self.admission.max_calls:
                raise BridgeError("BUDGET_DENIED")
            step = self.calls
            self.calls += 1
            prepared, request = self._prepare(payload, step)
            mode = self.admission.fake_scenario
            if mode == "tool":
                mode = "tool_once" if step == 0 else "tool_final"
            fake_payload = {
                "schema": "m0.g3b.fake.v1", "call_id": prepared.call_id,
                "prepared_digest": prepared.request_digest, "route_id": ROUTE,
                "model": MODEL, "messages": list(prepared.messages),
                "tools": list(prepared.tools), "system": prepared.system,
                "max_output_tokens": prepared.max_output_tokens, "stream": True,
                "mode": mode,
                "nonce": self.admission.admission_nonce,
            }
            payload_bytes = canonical_json(fake_payload).encode("utf-8")
            payload_digest = hashlib.sha256(payload_bytes).hexdigest()
            task_id = "g3b-" + hashlib.sha256(self.admission.run_id.encode()).hexdigest()[:32]
            reserved = self.broker.reserve(task_id=task_id, route_id=ROUTE, model=MODEL,
                                           input_tokens=min(1024, self.admission.max_input_tokens),
                                           output_tokens=prepared.max_output_tokens,
                                           call_id=prepared.call_id)
            if not reserved.get("ok"):
                raise BridgeError(reserved.get("code", "BUDGET_DENIED"))
            reservation_id = reserved["reservation_id"]
            self._crash("after_reserve_before_claim")
            request = EgressRequest(**{**request.__dict__, "reservation_id": reservation_id,
                                       "estimated_cost_usd": "0.001"})
            decision = self.boundary.claim_dispatch_for_request(
                prepared, request, expected_reservation_route_model=(ROUTE, MODEL))
            if not decision.allowed or decision.permission is None:
                raise BridgeError("CLAIM_DENIED")
            self._crash("after_claim_before_attempt_start")
            attempt_id = self.attempts.begin_attempt(
                scope_id=prepared.scope_id, call_id=prepared.call_id,
                reservation_id=reservation_id, prepared_digest=prepared.request_digest,
                payload_digest=payload_digest, payload_length=len(payload_bytes))
            self._crash("after_attempt_start_before_fake_send")
            holder: dict[str, object] = {}

            def provider(_req):
                if hashlib.sha256(payload_bytes).hexdigest() != payload_digest:
                    raise ValueError("FAKE_RECEIPT_MISMATCH")
                rec = self.fake.send_exact_bytes(payload_bytes)
                holder["receipt"] = rec
                holder["sent"] = self.fake.sent_payload_digest
                mapped_usage = rec.usage if isinstance(rec.usage, Mapping) else None
                return {"status": 200, "usage": mapped_usage, "error": None}

            self.transport.dispatch(request, decision.permission, provider=provider)
            receipt = holder.get("receipt")
            self._crash("after_fake_receive_before_response")
            if receipt is None or not isinstance(receipt, object) or not hasattr(receipt, "raw_sha256"):
                self.attempts.mark_settlement_uncertain(attempt_id, reason="FAKE_RECEIPT_MISSING")
                raise BridgeError("SETTLEMENT_UNCERTAIN")
            if (receipt.raw_sha256 != payload_digest
                    or holder.get("sent") != payload_digest
                    or receipt.raw_length != len(payload_bytes)
                    or receipt.nonce != self.admission.admission_nonce):
                self.attempts.mark_settlement_uncertain(attempt_id, reason="FAKE_RECEIPT_MISMATCH")
                raise BridgeError("FAKE_RECEIPT_MISMATCH")
            usage = receipt.usage
            usage_map = usage if isinstance(usage, Mapping) else {}
            def _num(key: str):
                value = usage_map.get(key)
                return value if type(value) is int and value >= 0 else None
            complete = all(_num(k) is not None for k in
                           ("inputTokens", "cacheReadTokens", "cacheWriteTokens", "outputTokens"))
            if usage is None:
                complete_state = "MISSING"
            elif complete:
                complete_state = "AUTHORITATIVE"
            else:
                complete_state = "PARTIAL"
            observation = ProviderObservation.from_mapping({
                "requested_route": ROUTE, "observed_route": ROUTE,
                "model_reported": MODEL, "provider_request_id": receipt.receipt_id,
                "usage_raw_hash": receipt.raw_sha256,
                "input": _num("inputTokens"), "cache_read": _num("cacheReadTokens"),
                "cache_write": _num("cacheWriteTokens"), "output": _num("outputTokens"),
                "reasoning": _num("reasoningTokens"), "cost_estimate": None,
                "cost_source": "synthetic_fixture_cost",
                "error_kind": "none", "complete_or_uncertain": complete_state})
            observation.validate_for_policy("inclusive")
            observation_digest = hashlib.sha256(canonical_json(observation.to_mapping()).encode()).hexdigest()
            self.attempts.mark_response_observed(
                attempt_id, receipt_id=receipt.receipt_id,
                receipt_json=json.dumps({"receipt_id": receipt.receipt_id,
                                         "raw_sha256": receipt.raw_sha256,
                                         "raw_length": receipt.raw_length,
                                         "mode": receipt.mode,
                                         "observation_digest": observation_digest}, sort_keys=True))
            self._crash("after_response_before_settlement")
            camel = None
            if usage_map:
                camel = {key: usage_map[key] for key in
                         ("inputTokens", "cacheReadTokens", "cacheWriteTokens",
                          "outputTokens", "reasoningTokens", "totalTokens")
                         if key in usage_map}
            if complete_state == "AUTHORITATIVE":
                settled = self.broker.settle(reservation_id=reservation_id, usage=camel)
                if settled.get("ok"):
                    self.attempts.mark_settled(attempt_id, settlement_json=json.dumps(settled, sort_keys=True))
                    self._crash("after_settlement_before_sdk_finish")
                    return ([{"kind": "chunk", "chunk": {"type": "text-delta", "index": 0, "text": "ok"}}]
                            + [dict(frame, chunk={**frame["chunk"], "index": 0})
                               if frame.get("kind") == "chunk" and "index" not in frame.get("chunk", {})
                               else frame for frame in receipt.frames])
                self.attempts.mark_settlement_uncertain(attempt_id, reason="SETTLE_REJECTED")
                raise BridgeError("SETTLEMENT_UNCERTAIN")
            failed = self.broker.fail(reservation_id=reservation_id, usage=camel)
            if failed.get("ok"):
                self.attempts.mark_worst_case(attempt_id, reason="USAGE_NOT_AUTHORITATIVE")
                return [{"kind": "finish", "reason": {"kind": "error"}}]
            self.attempts.mark_settlement_uncertain(attempt_id, reason="FAIL_REJECTED")
            raise BridgeError("SETTLEMENT_UNCERTAIN")
        except (AdmissionError, BridgeError, BrokerClientError, ValueError) as exc:
            return [{"kind": "error", "payload": {"code": getattr(exc, "code", "INTERNAL"),
                                                   "message": "safe error", "retryable": False}}]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args(argv)
    config = json.loads(Path(args.config).read_text())
    admission = load_admission(config["admission_path"], expected_uid=config.get("expected_uid", 65534))
    broker = BrokerClient(config_path=config["broker_config_path"], python=config["python"])
    broker.start()
    fake = FakeBackend(script=config["fake_script"], receipt_dir=config["receipt_dir"],
                       python=config.get("fake_python", config["python"]),
                       mode=admission.fake_scenario)
    attempts = AttemptJournal(config["attempt_db"])
    controller = TrustedController(admission, broker=broker, fake=fake, attempts=attempts,
                                   expected_uid=config.get("expected_uid", 65534))
    server = BridgeServer(controller, config["socket_path"])
    try:
        server.serve_forever()
    finally:
        broker.close()
        fake.close()
        attempts.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
