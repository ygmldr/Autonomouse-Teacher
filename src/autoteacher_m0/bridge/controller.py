"""G3-B B2 trusted Controller (offline Fake chain; no DSH/Key/network)."""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from autoteacher_m0.bridge.admission import (
    Admission, AdmissionError, load_admission, validate_request_payload,
)
from autoteacher_m0.bridge.attempts import AttemptJournal
from autoteacher_m0.bridge.broker_client import BrokerClient, BrokerClientError
from autoteacher_m0.bridge.fake_backend import FakeBackend
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

    def handle_envelope(self, payload: Mapping[str, object]) -> list[dict]:
        try:
            if self.calls >= self.admission.max_calls:
                raise BridgeError("BUDGET_DENIED")
            step = self.calls
            self.calls += 1
            prepared, request = self._prepare(payload, step)
            fake_payload = {
                "schema": "m0.g3b.fake.v1", "call_id": prepared.call_id,
                "prepared_digest": prepared.request_digest, "route_id": ROUTE,
                "model": MODEL, "messages": list(prepared.messages),
                "tools": list(prepared.tools), "system": prepared.system,
                "max_output_tokens": prepared.max_output_tokens, "stream": True,
                "mode": self.admission.fake_scenario,
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
            request = EgressRequest(**{**request.__dict__, "reservation_id": reservation_id,
                                       "estimated_cost_usd": "0.001"})
            decision = self.boundary.claim_dispatch_for_request(
                prepared, request, expected_reservation_route_model=(ROUTE, MODEL))
            if not decision.allowed or decision.permission is None:
                raise BridgeError("CLAIM_DENIED")
            attempt_id = self.attempts.begin_attempt(
                scope_id=prepared.scope_id, call_id=prepared.call_id,
                reservation_id=reservation_id, prepared_digest=prepared.request_digest,
                payload_digest=payload_digest, payload_length=len(payload_bytes))
            outcome = self.transport.dispatch(request, decision.permission,
                                              provider=lambda _req: {"status": 200,
                                                                     "usage": None,
                                                                     "error": None})
            if outcome.get("state") != "SETTLED_USAGE":
                # Provider callable above is a stub; actual Fake send is below.
                pass
            receipt = self.fake.send_exact_bytes(payload_bytes)
            if (receipt.raw_sha256 != payload_digest
                    or receipt.raw_length != len(payload_bytes)
                    or receipt.nonce != self.admission.admission_nonce):
                self.attempts.mark_settlement_uncertain(attempt_id, reason="FAKE_RECEIPT_MISMATCH")
                raise BridgeError("FAKE_RECEIPT_MISMATCH")
            self.attempts.mark_response_observed(
                attempt_id, receipt_id=receipt.receipt_id,
                receipt_json=json.dumps({"receipt_id": receipt.receipt_id,
                                         "raw_sha256": receipt.raw_sha256,
                                         "raw_length": receipt.raw_length,
                                         "mode": receipt.mode}, sort_keys=True))
            usage = receipt.usage
            if receipt.mode == "ok_usage" and isinstance(usage, Mapping):
                settled = self.broker.settle(reservation_id=reservation_id, usage=dict(usage))
                if settled.get("ok"):
                    self.attempts.mark_settled(attempt_id, settlement_json=json.dumps(settled, sort_keys=True))
                    return ([{"kind": "chunk", "chunk": {"type": "text-delta", "text": "ok"}}]
                            + list(receipt.frames) + [{"kind": "receipt", "payload": {
                                "receipt_id": receipt.receipt_id,
                                "raw_sha256": receipt.raw_sha256,
                                "raw_length": receipt.raw_length}}])
                self.attempts.mark_settlement_uncertain(attempt_id, reason="SETTLE_REJECTED")
                raise BridgeError("SETTLEMENT_UNCERTAIN")
            # Known partial/missing/invalid usage: fail with known dimensions, hold worst case.
            mapped = None
            if isinstance(usage, Mapping) and "inputTokens" in usage:
                mapped = {k: v for k, v in usage.items() if k in
                          {"inputTokens", "cacheReadTokens", "cacheWriteTokens", "outputTokens"}}
            failed = self.broker.fail(reservation_id=reservation_id, usage=mapped)
            if failed.get("ok"):
                self.attempts.mark_worst_case(attempt_id, reason="USAGE_PARTIAL_OR_MISSING_OR_INVALID")
                return [{"kind": "receipt", "payload": {"receipt_id": receipt.receipt_id,
                                                         "raw_sha256": receipt.raw_sha256,
                                                         "raw_length": receipt.raw_length}},
                        {"kind": "finish", "reason": {"kind": "error"}}]
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
    for line in sys.stdin:
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            print(json.dumps({"kind": "error", "payload": {"code": "REQUEST_INVALID"}}), flush=True)
            continue
        for frame in controller.handle_envelope(payload):
            print(json.dumps(frame, sort_keys=True, separators=(",", ":")), flush=True)
    broker.close()
    fake.close()
    attempts.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
