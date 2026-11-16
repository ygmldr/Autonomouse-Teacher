from __future__ import annotations
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from autoteacher_m0.bridge.admission import AdmissionError, load_admission
from autoteacher_m0.bridge.attempts import AttemptJournal
from autoteacher_m0.bridge.broker_client import BrokerClient
from autoteacher_m0.bridge.controller import TrustedController
from autoteacher_m0.bridge.fake_backend import FakeBackend
from autoteacher_m0.bridge.protocol import Envelope

ROUTE = "offline-test-only-g3b"
MODEL = "fixture-bridge-v1"
SCOPE = "fixed-offline-scope"
FAKE = Path(__file__).resolve().parents[3] / "spikes/g3b-trusted-bridge/fake/fake_provider.py"


def _write_admission(tmp_path: Path, *, scenario: str = "ok_usage") -> Path:
    tool = {"name": "skill_lookup", "sha256": hashlib.sha256(b"tool").hexdigest()}
    doc = {"schema": "m0.g3b.admission.v1", "admission_id": "a" * 32,
           "scope_id": SCOPE, "run_id": "run-g3b-test", "synthetic": True,
           "route": {"route_id": ROUTE, "provider": ROUTE, "model": MODEL},
           "tool_schemas": [tool],
           "limits": {"max_calls": 8, "max_attempts": 1, "max_input_tokens": 2500000,
                      "max_output_tokens": 1024, "deadline_ms": 30000},
           "fake_scenario": scenario, "expiry_utc": "2099-01-01T00:00:00Z",
           "launcher": {"uid": 65534, "container": True, "admission_nonce": "b" * 32}}
    path = tmp_path / "admission.json"
    path.write_text(json.dumps(doc))
    return path


def _broker_config(tmp_path: Path) -> Path:
    doc = {"v": 1, "synthetic": True, "db_path": str(tmp_path / "broker.sqlite3"),
           "scope_id": SCOPE, "max_messages": 64,
           "limits": {"soft_usd": "3", "hard_usd": "10", "per_call_usd": "0.20",
                      "max_requests": 50, "max_input_tokens": 2500000,
                      "max_output_tokens": 600000, "max_steps": 8, "max_retries": 1},
           "routes": [{"route_id": ROUTE, "model": MODEL,
                       "price": {"version": "fixture-v1", "input_per_million": "1",
                                 "output_per_million": "2", "cached_input_per_million": "0.5",
                                 "source": "synthetic fixture", "captured_at": "2026-11-16"},
                       "known_extra_fee_usd": "0.001",
                       "usage_policy": {"cache_write": "input_rate",
                                        "reasoning": "included_in_output"}}]}
    path = tmp_path / "broker.json"
    path.write_text(json.dumps(doc))
    return path


def _controller(tmp_path: Path, scenario: str = "ok_usage"):
    admission = load_admission(_write_admission(tmp_path, scenario=scenario), expected_uid=65534)
    broker = BrokerClient(config_path=str(_broker_config(tmp_path)), python=sys.executable)
    broker.start()
    fake = FakeBackend(script=str(FAKE), receipt_dir=str(tmp_path / "receipts"),
                       python=sys.executable, mode=scenario)
    attempts = AttemptJournal(tmp_path / "attempts.sqlite3")
    controller = TrustedController(admission, broker=broker, fake=fake, attempts=attempts,
                                   expected_uid=65534)
    return controller, broker, fake, attempts


def _env(payload):
    return Envelope(v=1, kind="request", transport_id="tr-" + "a" * 32,
                    seq=2, payload=payload, hash=None)


def _frames(controller, payload):
    result = []
    for env in controller.handle_envelope(_env(payload)):
        item = {"kind": env.kind, "payload": env.payload}
        if "chunk" in env.payload:
            item["chunk"] = env.payload["chunk"]
        if "reason" in env.payload:
            item["reason"] = env.payload["reason"]
        result.append(item)
    return result


def _payload(**overrides):
    base = {"sessionId": "s1", "provider": ROUTE, "model": MODEL,
            "messages": [{"role": "user", "content": "hello"}], "tools": [],
            "system": None, "maxTokens": 256, "stream": True, "purpose": "conversation"}
    base.update(overrides)
    return base


def test_b2_01_success_chain_real_broker_and_fake(tmp_path: Path) -> None:
    controller, broker, fake, attempts = _controller(tmp_path)
    try:
        frames = _frames(controller, _payload())
        assert not any(frame["kind"] == "error" for frame in frames), frames
        receipt = fake.last_receipt
        assert receipt is not None and receipt.raw_sha256 == fake.sent_payload_digest
        assert fake.received_count() == 1
        assert attempts.conn.execute("SELECT COUNT(*) FROM g3b_attempts").fetchone()[0] == 1
        snapshot = broker.snapshot()["snapshot"]
        assert snapshot["claims"]["total"] == 1
        assert snapshot["requests"] == 1
    finally:
        broker.close()
        fake.close()
        attempts.close()


def test_b2_03_route_mismatch_zero_fake(tmp_path: Path) -> None:
    controller, broker, fake, attempts = _controller(tmp_path)
    try:
        frames = _frames(controller, _payload(provider="offline-test-only-other"))
        assert frames[0]["kind"] == "error"
        assert frames[0]["payload"]["code"] == "ROUTE_MISMATCH"
        assert fake.received_count() == 0
        assert broker.snapshot()["snapshot"]["requests"] == 0
    finally:
        broker.close()
        fake.close()
        attempts.close()


def test_b2_04_missing_admission_or_self_auth_zero_fake(tmp_path: Path) -> None:
    with pytest.raises(AdmissionError) as exc:
        load_admission(tmp_path / "missing.json", expected_uid=65534)
    assert exc.value.code == "ADMISSION_MISSING"
    controller, broker, fake, attempts = _controller(tmp_path)
    try:
        frames = _frames(controller, _payload(call_id="call-" + "a" * 48))
        assert frames[0]["kind"] == "error"
        assert frames[0]["payload"]["code"] == "ADMISSION_SELF_AUTH_DENIED"
        assert fake.received_count() == 0
    finally:
        broker.close()
        fake.close()
        attempts.close()


def test_b2_09_partial_usage_holds_without_zeroing(tmp_path: Path) -> None:
    controller, broker, fake, attempts = _controller(tmp_path, scenario="partial_usage")
    try:
        frames = _frames(controller, _payload())
        assert any(frame["kind"] == "finish" and frame.get("reason", {}).get("kind") == "error"
                   for frame in frames), frames
        assert fake.received_count() == 1
        row = attempts.conn.execute("SELECT state, reason FROM g3b_attempts").fetchone()
        assert row[0] == "WORST_CASE_HELD"
        snapshot = broker.snapshot()["snapshot"]
        assert snapshot["claims"]["total"] == 1
    finally:
        broker.close()
        fake.close()
        attempts.close()


def test_b2_02_prepared_tamper_zero_fake(tmp_path: Path) -> None:
    controller, broker, fake, attempts = _controller(tmp_path)
    try:
        prepared, request = controller._prepare(_payload(), 0)
        tampered = prepared.__class__(**{**prepared.__dict__,
                                        "route_id": "offline-test-only-other"})
        decision = controller.boundary.claim_dispatch_for_request(
            tampered, request, expected_reservation_route_model=(ROUTE, MODEL))
        assert decision.allowed is False
        assert fake.received_count() == 0
    finally:
        broker.close()
        fake.close()
        attempts.close()


def test_b2_07_attempt_journal_failure_prevents_fake(tmp_path: Path, monkeypatch) -> None:
    controller, broker, fake, attempts = _controller(tmp_path)
    try:
        original = attempts.begin_attempt
        def fail(*args, **kwargs):
            raise ValueError("ATTEMPT_JOURNAL_UNAVAILABLE")
        monkeypatch.setattr(attempts, "begin_attempt", fail)
        frames = _frames(controller, _payload())
        assert frames[0]["kind"] == "error"
        assert fake.received_count() == 0
        monkeypatch.setattr(attempts, "begin_attempt", original)
    finally:
        broker.close()
        fake.close()
        attempts.close()


# ---------------------------------------------------------------- crash hooks (subprocess)
CRASH_CHILD = Path(__file__).resolve().parent / "_crash_child.py"


def _crash_run(tmp_path: Path, hook: str):
    env = {**os.environ, "G3B_TEST_MODE": "1", "G3B_CRASH_HOOK": hook,
           "PYTHONPATH": "src:artifacts/foundation/deps"}
    proc = subprocess.run([sys.executable, "-B", str(CRASH_CHILD), str(tmp_path)],
                          env=env, capture_output=True, text=True, timeout=30)
    return proc


def _journal_state(tmp_path: Path) -> str | None:
    import sqlite3
    db = sqlite3.connect(tmp_path / "attempts.sqlite3")
    try:
        row = db.execute("SELECT state FROM g3b_attempts").fetchone()
        return None if row is None else row[0]
    finally:
        db.close()


def test_crash_after_claim_before_attempt_start_no_resend(tmp_path: Path) -> None:
    proc = _crash_run(tmp_path, "after_claim_before_attempt_start")
    assert proc.returncode == 97, (proc.stdout, proc.stderr)
    assert (tmp_path / "receipts" / "received-count.json").exists() is False
    assert _journal_state(tmp_path) is None


def test_crash_after_attempt_start_before_fake_send_pending(tmp_path: Path) -> None:
    proc = _crash_run(tmp_path, "after_attempt_start_before_fake_send")
    assert proc.returncode == 97, (proc.stdout, proc.stderr)
    assert _journal_state(tmp_path) == "ATTEMPT_STARTED"
    counter = tmp_path / "receipts" / "received-count.json"
    assert not counter.exists()
    from autoteacher_m0.bridge.attempts import AttemptJournal
    journal = AttemptJournal(tmp_path / "attempts.sqlite3")
    try:
        assert journal.reconcile_on_startup()[0]["state"] == "ATTEMPT_STARTED"
    finally:
        journal.close()


def test_crash_after_fake_receive_before_response_receipt_persisted(tmp_path: Path) -> None:
    proc = _crash_run(tmp_path, "after_fake_receive_before_response")
    assert proc.returncode == 97, (proc.stdout, proc.stderr)
    assert _journal_state(tmp_path) == "ATTEMPT_STARTED"
    receipts = list((tmp_path / "receipts").glob("rcpt-*.json"))
    assert len(receipts) == 1
    assert json.loads(receipts[0].read_text())["raw_sha256"]


def test_b2_reconcile_after_fake_receive_settles_without_resend(tmp_path: Path) -> None:
    proc = _crash_run(tmp_path, "after_fake_receive_before_response")
    assert proc.returncode == 97, (proc.stdout, proc.stderr)
    admission = load_admission(tmp_path / "admission.json", expected_uid=65534)
    broker = BrokerClient(config_path=str(tmp_path / "broker.json"), python=sys.executable)
    broker.start()
    fake = FakeBackend(script=str(FAKE), receipt_dir=str(tmp_path / "receipts"),
                       python=sys.executable, mode="ok_usage")
    journal = AttemptJournal(tmp_path / "attempts.sqlite3")
    controller = TrustedController(admission, broker=broker, fake=fake, attempts=journal,
                                   expected_uid=65534, register_admission=False)
    try:
        controller.reconcile_on_startup(str(tmp_path / "receipts"))
        state = journal.conn.execute("SELECT state FROM g3b_attempts").fetchone()[0]
        assert state in {"SETTLED", "WORST_CASE_HELD"}
        assert fake.received_count() == 1
        snapshot = broker.snapshot()["snapshot"]
        assert snapshot["claims"]["total"] == 1
        controller.reconcile_on_startup(str(tmp_path / "receipts"))
        assert fake.received_count() == 1
        assert journal.conn.execute("SELECT state FROM g3b_attempts").fetchone()[0] == state
    finally:
        broker.close()
        fake.close()
        journal.close()
