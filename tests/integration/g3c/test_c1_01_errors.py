"""G3-C C1-01/C1-02 host tests (no Key/network/provider).

C1-01: raw Broker conflict codes must map through the trusted Controller to the
frozen additive ``BROKER_*`` IPC codes; the resulting Error Envelope must be
encode/parse-clean on the Python side (C1-01D). C1-02: the protocol-level
finish(error/aborted) schema requires ``failure{message,code}``.

The Broker here is a deterministic stub: the Controller path (not the Broker
process) is under test. A separate test proves the stdio client preserves raw
codes for that single mapping authority.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import pytest

from autoteacher_m0.bridge import BridgeError
from autoteacher_m0.bridge.attempts import AttemptJournal
from autoteacher_m0.bridge.controller import TrustedController
from autoteacher_m0.bridge.fake_backend import FakeBackend
from autoteacher_m0.bridge.protocol import (
    BROKER_ERROR_CODE_MAP, ERROR_CODES, Envelope, encode_envelope,
    normalize_broker_error_code, parse_envelope, validate_error_payload,
    validate_finish_payload,
)

ROUTE = "offline-test-only-g3b"
MODEL = "fixture-bridge-v1"
SCOPE = "fixed-offline-scope"
FAKE = Path(__file__).resolve().parents[3] / "spikes/g3b-trusted-bridge/fake/fake_provider.py"
TRANSPORT = "tr-" + "c" * 32


def _write_admission(tmp_path: Path) -> Path:
    doc = {
        "schema": "m0.g3b.admission.v1", "admission_id": "a" * 32,
        "scope_id": SCOPE, "run_id": "run-g3c-c1-errors", "synthetic": True,
        "route": {"route_id": ROUTE, "provider": ROUTE, "model": MODEL},
        "tool_schemas": [{"name": "skill_lookup",
                          "sha256": hashlib.sha256(b"tool").hexdigest()}],
        "limits": {"max_calls": 8, "max_attempts": 1, "max_input_tokens": 2500000,
                   "max_output_tokens": 1024, "deadline_ms": 30000},
        "fake_scenario": "ok_usage", "expiry_utc": "2099-01-01T00:00:00Z",
        "launcher": {"uid": 65534, "container": True,
                     "admission_nonce": "b" * 32},
    }
    path = tmp_path / "admission.json"
    path.write_text(json.dumps(doc))
    return path


def _payload(**overrides):
    payload = {
        "sessionId": "g3c-c1-errors", "provider": ROUTE, "model": MODEL,
        "messages": [{"role": "user", "content": "hello"}], "tools": [],
        "system": None, "maxTokens": 64, "stream": True,
        "purpose": "conversation",
    }
    payload.update(overrides)
    return payload


class _ConflictBroker:
    """Broker stub returning one raw Broker code from reserve()."""

    def __init__(self, code: str) -> None:
        self.code = code
        self.reserve_calls: list[dict] = []

    def reserve(self, **fields):
        self.reserve_calls.append(fields)
        return {"v": 1, "ok": False, "code": self.code,
                "dispatch_allowed": False}

    def claim(self, **fields):
        raise AssertionError("claim must not be reached after reserve denial")

    def settle(self, **fields):
        raise AssertionError("settle must not be reached after reserve denial")

    def fail(self, **fields):
        raise AssertionError("fail must not be reached after reserve denial")

    def snapshot(self):
        raise AssertionError("snapshot not used")

    def request(self, op, fields, *, deadline_monotonic=None):
        raise AssertionError(f"broker.request({op}) not used")

    def reservation_status(self, reservation_id, *, deadline_monotonic=None):
        raise AssertionError("reservation_status not used")


@pytest.mark.parametrize(("raw_code", "expected"), [
    ("CALL_ID_CONFLICT", "BROKER_CALL_ID_CONFLICT"),
    ("IDEMPOTENCY_CONFLICT", "BROKER_IDEMPOTENCY_CONFLICT"),
    ("ALREADY_SETTLED", "BROKER_ALREADY_SETTLED"),
    ("ALREADY_FAILED", "BROKER_ALREADY_FAILED"),
    ("INVALID_USAGE", "BROKER_INVALID_USAGE"),
    ("INTERNAL_ERROR", "BROKER_ERROR"),
    ("UNRECOGNIZED_BROKER_CODE", "BROKER_ERROR"),
])
def test_c1_01_broker_raw_codes_map_through_controller(
        tmp_path: Path, raw_code: str, expected: str) -> None:
    from autoteacher_m0.bridge.admission import load_admission

    admission = load_admission(_write_admission(tmp_path), expected_uid=65534)
    broker = _ConflictBroker(raw_code)
    receipt_dir = tmp_path / "receipts"
    fake = FakeBackend(script=str(FAKE), receipt_dir=str(receipt_dir),
                       python=sys.executable, mode="ok_usage")
    attempts = AttemptJournal(tmp_path / "attempts.sqlite3")
    controller = TrustedController(admission, broker=broker, fake=fake,
                                   attempts=attempts, expected_uid=65534,
                                   register_admission=False)
    try:
        request = Envelope(1, "request", TRANSPORT, 0, _payload(), None)
        frames = list(controller.handle_envelope(request))
        assert len(frames) == 1, frames
        error = frames[0]
        assert error.kind == "error"
        assert error.payload["code"] == expected
        assert error.payload["code"] in ERROR_CODES
        assert error.payload["code"] != "UNKNOWN_FIELD"
        assert error.payload["retryable"] is False
        # C1-01D: the legal rejection envelope is wire-encodable and parses.
        wire = encode_envelope(error) + b"\n"
        parsed = parse_envelope(wire)
        assert parsed.kind == "error"
        assert parsed.payload["code"] == expected
        assert parsed.transport_id == TRANSPORT
        assert fake.received_count() == 0
        assert len(broker.reserve_calls) == 1
    finally:
        attempts.close()
        fake.close()


def test_c1_01_protocol_mapping_is_finite_and_additive() -> None:
    expected = {
        "BROKER_CALL_ID_CONFLICT", "BROKER_IDEMPOTENCY_CONFLICT",
        "BROKER_ALREADY_SETTLED", "BROKER_ALREADY_FAILED",
        "BROKER_INVALID_USAGE", "BROKER_ERROR", "BROKER_TIMEOUT",
        "DEADLINE_EXCEEDED", "TOO_MANY_CONNECTIONS",
    }
    assert expected <= ERROR_CODES
    # Raw Broker implementation codes must never become wire error codes.
    assert not {"CALL_ID_CONFLICT", "IDEMPOTENCY_CONFLICT",
                "ALREADY_SETTLED", "ALREADY_FAILED"} & ERROR_CODES
    assert BROKER_ERROR_CODE_MAP["CALL_ID_CONFLICT"] == "BROKER_CALL_ID_CONFLICT"
    assert BROKER_ERROR_CODE_MAP["IDEMPOTENCY_CONFLICT"] == "BROKER_IDEMPOTENCY_CONFLICT"
    assert normalize_broker_error_code("ALREADY_FAILED") == "BROKER_ALREADY_FAILED"
    assert normalize_broker_error_code("BUDGET_EXCEEDED_NOT_MAPPED") == "BROKER_ERROR"
    assert normalize_broker_error_code(None) == "BROKER_ERROR"
    for code in ("BROKER_CALL_ID_CONFLICT", "BROKER_IDEMPOTENCY_CONFLICT",
                 "BROKER_ALREADY_SETTLED", "BROKER_ALREADY_FAILED",
                 "BROKER_INVALID_USAGE", "BROKER_ERROR", "BROKER_TIMEOUT",
                 "DEADLINE_EXCEEDED", "TOO_MANY_CONNECTIONS"):
        payload = validate_error_payload(code)
        env = Envelope(1, "error", TRANSPORT, 2, payload, None)
        assert parse_envelope(encode_envelope(env) + b"\n").payload["code"] == code
    with pytest.raises(BridgeError) as exc:
        validate_error_payload("NOT_A_FROZEN_CODE")
    assert exc.value.code == "UNKNOWN_FIELD"


# ---------------- C1-02: finish schema (protocol layer only) ----------------

@pytest.mark.parametrize("kind", ["stop", "tool-calls", "max-tokens", "blocked"])
def test_c1_02_finish_non_error_kinds_need_no_failure(kind: str) -> None:
    validate_finish_payload({"reason": {"kind": kind}})
    env = Envelope(1, "finish", TRANSPORT, 2, {"reason": {"kind": kind}}, None)
    parsed = parse_envelope(encode_envelope(env) + b"\n")
    assert parsed.payload == {"reason": {"kind": kind}}


@pytest.mark.parametrize("kind", ["error", "aborted"])
def test_c1_02_finish_error_kinds_require_failure(kind: str) -> None:
    with pytest.raises(BridgeError) as exc:
        validate_finish_payload({"reason": {"kind": kind}})
    assert exc.value.code == "UNKNOWN_FIELD"
    with pytest.raises(BridgeError):
        validate_finish_payload({"reason": {"kind": kind,
                                            "failure": {"message": "safe"}}})
    valid = {"reason": {"kind": kind,
                        "failure": {"message": "safe fixture failure",
                                    "code": "BROKER_CALL_ID_CONFLICT"}}}
    validate_finish_payload(valid)
    env = Envelope(1, "finish", TRANSPORT, 2, valid, None)
    assert parse_envelope(encode_envelope(env) + b"\n").payload == valid


def test_c1_02_finish_rejects_extra_fields_and_bad_failure_types() -> None:
    with pytest.raises(BridgeError) as exc:
        validate_finish_payload({"reason": {"kind": "stop", "failure": {}}})
    assert exc.value.code == "UNKNOWN_FIELD"
    with pytest.raises(BridgeError):
        validate_finish_payload({"reason": {"kind": "error",
                                            "failure": {"message": 1, "code": "X"}}})
    with pytest.raises(BridgeError):
        validate_finish_payload({"reason": {"kind": "error",
                                            "failure": {"message": "x", "code": ""}}})
    with pytest.raises(BridgeError):
        validate_finish_payload({"reason": {"kind": "stop"}, "extra": True})
    with pytest.raises(BridgeError) as exc:
        validate_finish_payload({"reason": {"kind": "unknown"}})
    assert exc.value.code in {"BAD_TYPE", "UNKNOWN_FIELD"}
