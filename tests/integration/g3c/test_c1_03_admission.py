"""G3-C C1-03: Admission is enforced before Reserve/Claim/Fake.

This module also hosts the shared real-subprocess harness used by the other
G3-C tests (real stdio Broker child, real Fake Provider child, real SQLite).
"""
from __future__ import annotations
import hashlib
import json
import os
import signal
import socket
import sqlite3
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import pytest

from autoteacher_m0.bridge.admission import load_admission
from autoteacher_m0.bridge.attempts import AttemptJournal
from autoteacher_m0.bridge.broker_client import BrokerClient
from autoteacher_m0.bridge.controller import (
    TrustedController, deadline_protocol_code,
)
from autoteacher_m0.bridge.fake_backend import FakeBackend
from autoteacher_m0.bridge.ipc_server import BridgeServer
from autoteacher_m0.bridge.protocol import (
    Envelope, canonical_payload_bytes, encode_envelope, parse_envelope, payload_digest,
)

ROUTE = "offline-test-only-g3b"
MODEL = "fixture-bridge-v1"
SCOPE = "fixed-offline-scope"
FAKE = Path(__file__).resolve().parents[3] / "spikes/g3b-trusted-bridge/fake/fake_provider.py"
G3C_DIR = Path(__file__).resolve().parent

DEFAULT_LIMITS = {"max_calls": 8, "max_attempts": 1, "max_input_tokens": 2500000,
                  "max_output_tokens": 1024, "deadline_ms": 30000}
DEFAULT_BROKER_LIMITS = {"soft_usd": "3", "hard_usd": "10", "per_call_usd": "0.20",
                         "max_requests": 50, "max_input_tokens": 2500000,
                         "max_output_tokens": 600000, "max_steps": 8, "max_retries": 1}


def write_admission(root: Path, *, scenario: str = "ok_usage", limits: dict | None = None,
                    admission_id: str = "a" * 32, run_id: str = "run-g3c-test",
                    nonce: str = "b" * 32) -> Path:
    tool = {"name": "skill_lookup", "sha256": hashlib.sha256(b"tool").hexdigest()}
    doc = {"schema": "m0.g3b.admission.v1", "admission_id": admission_id,
           "scope_id": SCOPE, "run_id": run_id, "synthetic": True,
           "route": {"route_id": ROUTE, "provider": ROUTE, "model": MODEL},
           "tool_schemas": [tool],
           "limits": {**DEFAULT_LIMITS, **(limits or {})},
           "fake_scenario": scenario, "expiry_utc": "2099-01-01T00:00:00Z",
           "launcher": {"uid": 65534, "container": True, "admission_nonce": nonce}}
    path = root / "admission.json"
    path.write_text(json.dumps(doc))
    return path


def write_broker_config(root: Path, *, limits: dict | None = None) -> Path:
    doc = {"v": 1, "synthetic": True, "db_path": str(root / "broker.sqlite3"),
           "scope_id": SCOPE, "max_messages": 64,
           "limits": {**DEFAULT_BROKER_LIMITS, **(limits or {})},
           "routes": [{"route_id": ROUTE, "model": MODEL,
                       "price": {"version": "fixture-v1", "input_per_million": "1",
                                 "output_per_million": "2", "cached_input_per_million": "0.5",
                                 "source": "synthetic fixture", "captured_at": "2026-11-16"},
                       "known_extra_fee_usd": "0.001",
                       "usage_policy": {"cache_write": "input_rate",
                                        "reasoning": "included_in_output"}}]}
    path = root / "broker.json"
    path.write_text(json.dumps(doc))
    return path


@dataclass
class Harness:
    root: Path
    admission: object
    broker: BrokerClient
    fake: FakeBackend
    attempts: AttemptJournal
    controller: TrustedController
    admission_path: Path
    broker_path: Path

    def close(self) -> None:
        try:
            self.broker.close()
        finally:
            try:
                self.fake.close()
            finally:
                self.attempts.close()

    def snapshot(self) -> dict:
        return self.broker.snapshot()["snapshot"]

    def status(self, reservation_id: str) -> dict:
        return self.controller._broker_status(reservation_id, time.monotonic() + 5.0)

    def attempts_rows(self) -> list[dict]:
        return self.attempts.attempts()

    def attempt(self, call_id: str) -> dict | None:
        return self.attempts.attempt_for_call(call_id)

    def receipt_count(self) -> int:
        return self.fake.received_count()

    def broker_db(self):
        import sqlite3
        conn = sqlite3.connect(self.root / "broker.sqlite3")
        conn.row_factory = sqlite3.Row
        return conn


def make_harness(root: Path, *, scenario: str = "ok_usage",
                 limits: dict | None = None, broker_limits: dict | None = None,
                 admission_id: str = "a" * 32, run_id: str = "run-g3c-test",
                 register: bool = True, fake_timeout: float = 10.0,
                 write_configs: bool = True) -> Harness:
    root.mkdir(parents=True, exist_ok=True)
    if write_configs:
        admission_path = write_admission(root, scenario=scenario, limits=limits,
                                         admission_id=admission_id, run_id=run_id)
        broker_path = write_broker_config(root, limits=broker_limits)
    else:
        admission_path = root / "admission.json"
        broker_path = root / "broker.json"
    admission = load_admission(admission_path, expected_uid=65534)
    broker = BrokerClient(config_path=str(broker_path), python=sys.executable)
    broker.start()
    fake = FakeBackend(script=str(FAKE), receipt_dir=str(root / "receipts"),
                       python=sys.executable, mode=scenario, timeout_s=fake_timeout)
    attempts = AttemptJournal(root / "attempts.sqlite3")
    controller = TrustedController(admission, broker=broker, fake=fake, attempts=attempts,
                                   expected_uid=65534, register_admission=register)
    return Harness(root, admission, broker, fake, attempts, controller,
                   admission_path, broker_path)


def payload(**overrides):
    base = {"sessionId": "s1", "provider": ROUTE, "model": MODEL,
            "messages": [{"role": "user", "content": "hello g3c"}], "tools": [],
            "system": None, "maxTokens": 256, "stream": True, "purpose": "conversation"}
    base.update(overrides)
    return base


def request_env(payload_dict, transport_id: str | None = None) -> Envelope:
    transport_id = transport_id or "tr-" + "a" * 32
    return Envelope(v=1, kind="request", transport_id=transport_id,
                    seq=0, payload=payload_dict, hash=None)


def collect(controller: TrustedController, payload_dict, *,
            transport_id: str | None = None) -> list[dict]:
    result = []
    for env in controller.handle_envelope(request_env(payload_dict, transport_id)):
        item = {"kind": env.kind, "payload": env.payload}
        if "chunk" in env.payload:
            item["chunk"] = env.payload["chunk"]
        if "reason" in env.payload:
            item["reason"] = env.payload["reason"]
        result.append(item)
    return result


def codes(frames: list[dict]) -> list[str]:
    return [frame["payload"]["code"] for frame in frames if frame["kind"] == "error"]


def finishes(frames: list[dict]) -> list[dict]:
    return [frame["reason"] for frame in frames if frame["kind"] == "finish"]


def error_code(frames: list[dict]) -> str | None:
    found = codes(frames)
    return found[0] if found else None


def uds_roundtrip(controller: TrustedController, payload_dict, *,
                  socket_path: Path, transport_id: str | None = None,
                  cancel_after_ack: tuple[str, str] | None = None,
                  timeout: float = 20.0):
    """Real UDS request/response through the frozen B1 BridgeServer."""
    server = BridgeServer(controller, str(socket_path))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    deadline = time.monotonic() + 5
    while not socket_path.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert socket_path.exists(), "bridge socket not created"
    transport_id = transport_id or "tr-" + "b" * 32
    received: list[Envelope] = []
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(timeout)
    try:
        client.connect(str(socket_path))
        payload_dict = dict(payload_dict)
        env = Envelope(v=1, kind="request", transport_id=transport_id, seq=0,
                       payload=payload_dict,
                       hash=payload_digest(canonical_payload_bytes(payload_dict)))
        client.sendall(encode_envelope(env) + b"\n")
        buffer = b""
        cancelled = False
        while True:
            chunk = client.recv(65536)
            if not chunk:
                break
            buffer += chunk
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                if not line:
                    continue
                parsed = parse_envelope(line)
                received.append(parsed)
                if (cancel_after_ack is not None and not cancelled
                        and parsed.kind == "ack"):
                    reason = cancel_after_ack[1]
                    cancel = Envelope(v=1, kind="cancel", transport_id=transport_id,
                                      seq=2, payload={"request_id": transport_id,
                                                      "reason": reason}, hash=None)
                    client.sendall(encode_envelope(cancel) + b"\n")
                    cancelled = True
                if parsed.kind in {"finish", "error"}:
                    return received, server, thread
    finally:
        client.close()
    return received, server, thread


def stop_server(server: BridgeServer, thread: threading.Thread) -> None:
    server.shutdown()
    thread.join(timeout=5)


_CRASH_CHILD = (
    "import sys\n"
    "from pathlib import Path\n"
    "sys.path.insert(0, str(Path.cwd() / 'tests/integration/g3c'))\n"
    "import test_c1_03_admission as h\n"
    "h.crash_main(Path(sys.argv[1]), sys.argv[2])\n"
)


def crash_main(root: Path, hook: str) -> int:
    harness = make_harness(root, register=True, write_configs=False)
    try:
        collect(harness.controller, payload())
    finally:
        harness.close()
    return 0


def run_crash(root: Path, hook: str, *, timeout: float = 40.0):
    env = {**os.environ, "G3B_TEST_MODE": "1", "G3B_CRASH_HOOK": hook,
           "PYTHONPATH": os.environ.get("PYTHONPATH", "src:artifacts/foundation/deps")}
    return subprocess.run([sys.executable, "-B", "-c", _CRASH_CHILD, str(root), hook],
                          cwd=str(Path(__file__).resolve().parents[3]), env=env,
                          capture_output=True, text=True, timeout=timeout)


def wait_for_counter(root: Path, expected: int = 1, timeout: float = 5.0) -> int:
    deadline = time.monotonic() + timeout
    path = root / "receipts" / "received-count.json"
    while time.monotonic() < deadline:
        try:
            count = int(json.loads(path.read_text())["count"])
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            count = 0
        if count >= expected:
            return count
        time.sleep(0.02)
    return 0


# ---------------------------------------------------------------- C1-03 tests
def test_c1_03a_output_limit_rejected_before_reserve_and_fake(tmp_path: Path) -> None:
    harness = make_harness(tmp_path, limits={"max_output_tokens": 128})
    try:
        frames = collect(harness.controller, payload(maxTokens=512))
        assert error_code(frames) == "BUDGET_DENIED", frames
        assert harness.receipt_count() == 0
        assert harness.snapshot()["requests"] == 0
        assert harness.controller.calls == 0
    finally:
        harness.close()


def test_c1_03b_invalid_request_does_not_consume_quota(tmp_path: Path) -> None:
    harness = make_harness(tmp_path, limits={"max_calls": 1})
    try:
        invalid_payloads = [
            payload(provider="offline-test-only-other"),
            payload(model="fixture-other"),
            payload(maxTokens=0),
            payload(provider=ROUTE, model=MODEL, extra_field=True),
            payload(tools=[{"name": "not-approved", "parameters": {}}]),
        ]
        for bad in invalid_payloads:
            frames = collect(harness.controller, bad)
            assert error_code(frames) is not None, frames
            assert harness.receipt_count() == 0
        assert harness.controller.calls == 0
        ok = collect(harness.controller, payload())
        assert error_code(ok) is None, ok
        assert harness.receipt_count() == 1
        assert harness.controller.calls == 1
        assert harness.snapshot()["requests"] == 1
    finally:
        harness.close()


def test_c1_03c_valid_call_quota_is_final(tmp_path: Path) -> None:
    harness = make_harness(tmp_path, limits={"max_calls": 1})
    try:
        first = collect(harness.controller, payload())
        assert error_code(first) is None, first
        second = collect(harness.controller, payload(
            messages=[{"role": "user", "content": "second distinct request"}]))
        assert error_code(second) == "BUDGET_DENIED", second
        assert harness.receipt_count() == 1
        assert harness.snapshot()["requests"] == 1
        assert len(harness.attempts_rows()) == 1
    finally:
        harness.close()


def test_c1_03d_concurrent_admission_never_exceeds_quota(tmp_path: Path) -> None:
    harness = make_harness(tmp_path, limits={"max_calls": 2})
    try:
        payloads = [payload(messages=[{"role": "user", "content": f"concurrent-{index}"}])
                    for index in range(8)]

        def run(item):
            return collect(harness.controller, item)

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(run, payloads))
        successes = [frames for frames in results if error_code(frames) is None]
        denied = [frames for frames in results if error_code(frames) == "BUDGET_DENIED"]
        assert len(successes) == 2, results
        assert len(denied) == 6, results
        assert harness.receipt_count() == 2
        snapshot = harness.snapshot()
        assert snapshot["requests"] == 2
        assert snapshot["claims"]["total"] == 2
        assert len(harness.attempts_rows()) == 2
    finally:
        harness.close()


def test_c1_03e_admission_deadline_is_wall_clock_effective(tmp_path: Path) -> None:
    harness = make_harness(tmp_path, scenario="slow_usage",
                           limits={"deadline_ms": 300})
    try:
        started = time.monotonic()
        frames = collect(harness.controller, payload())
        elapsed = time.monotonic() - started
        assert elapsed < 1.0, elapsed
        assert error_code(frames) == deadline_protocol_code(), frames
        assert not any(finish.get("kind") == "stop" for finish in finishes(frames))
        assert wait_for_counter(tmp_path, 1) == 1
        attempts = harness.attempts_rows()
        assert len(attempts) == 1
        assert attempts[0]["state"] == "SETTLEMENT_UNCERTAIN"
        status = harness.status(attempts[0]["reservation_id"])
        assert status["ok"] and status["status"] == "PENDING"
        assert harness.controller.deadline_seconds == pytest.approx(0.3)
    finally:
        harness.close()


def test_c1_03f_input_bound_is_conservative_and_marked_synthetic(tmp_path: Path) -> None:
    too_small = make_harness(tmp_path / "small", limits={"max_input_tokens": 64})
    try:
        frames = collect(too_small.controller, payload(system="x" * 400))
        assert error_code(frames) == "BUDGET_DENIED", frames
        assert too_small.receipt_count() == 0
        assert too_small.snapshot()["requests"] == 0
    finally:
        too_small.close()
    harness = make_harness(tmp_path / "ok")
    try:
        frames = collect(harness.controller, payload(system="short"))
        assert error_code(frames) is None, frames
        attempt = harness.attempts_rows()[0]
        status = harness.status(attempt["reservation_id"])
        document = json.loads(attempt["receipt_json"])
        assert status["input_bound"] == document["input_bound"]["tokens"]
        assert status["input_bound"] > 1
        assert document["input_bound"]["kind"] == "utf8_bytes_upper_bound"
        assert document["input_bound"]["synthetic_fixture_only"] is True
        assert document["synthetic_fixture_only"] is True
        assert document["fee_policy_version"]
    finally:
        harness.close()


# ---------------------------------------------------------------- C3-01 Cancel
def _intent_rows(root: Path) -> list[dict]:
    conn = sqlite3.connect(root / "attempts.sqlite3")
    conn.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in conn.execute(
            "SELECT * FROM g3b_send_intents ORDER BY created_utc").fetchall()]
    finally:
        conn.close()


def _cancel(controller, transport_id: str, reason: str = "aborted") -> None:
    controller.cancel(transport_id=transport_id, reason=reason)


def test_c3_01a_pre_send_cancel_is_zero_fake(tmp_path: Path) -> None:
    harness = make_harness(tmp_path)
    try:
        transport_id = "tr-" + "a" * 32
        _cancel(harness.controller, transport_id)
        frames = collect(harness.controller, payload(), transport_id=transport_id)
        assert error_code(frames) == "CANCELLED", frames
        assert harness.receipt_count() == 0
        assert harness.snapshot()["requests"] == 0
        assert harness.attempts_rows() == []
        assert _intent_rows(tmp_path) == []
    finally:
        harness.close()


def test_c3_01a2_cancel_after_reserve_before_claim_holds_reservation(
        tmp_path: Path) -> None:
    harness = make_harness(tmp_path)
    try:
        transport_id = "tr-" + "b" * 32
        original = harness.broker.reserve

        def reserve_then_cancel(**kwargs):
            reply = original(**kwargs)
            _cancel(harness.controller, transport_id)
            return reply

        harness.broker.reserve = reserve_then_cancel
        frames = collect(harness.controller, payload(), transport_id=transport_id)
        assert error_code(frames) == "CANCELLED", frames
        assert harness.receipt_count() == 0
        snapshot = harness.snapshot()
        assert snapshot["requests"] == 1
        assert snapshot["claims"]["total"] == 0
        intents = _intent_rows(tmp_path)
        assert len(intents) == 1 and intents[0]["state"] == "HELD_UNCERTAIN"
        status = harness.status(intents[0]["reservation_id"])
        assert status["status"] == "PENDING"
        assert harness.attempts_rows() == []
    finally:
        harness.close()


def test_c3_01a3_cancel_after_claim_before_attempt_never_reuses_permission(
        tmp_path: Path) -> None:
    harness = make_harness(tmp_path)
    try:
        transport_id = "tr-" + "c" * 32
        original = harness.broker.claim

        def claim_then_cancel(**kwargs):
            reply = original(**kwargs)
            _cancel(harness.controller, transport_id)
            return reply

        harness.broker.claim = claim_then_cancel
        frames = collect(harness.controller, payload(), transport_id=transport_id)
        assert error_code(frames) == "CANCELLED", frames
        assert harness.receipt_count() == 0
        snapshot = harness.snapshot()
        assert snapshot["claims"]["total"] == 1
        intents = _intent_rows(tmp_path)
        assert len(intents) == 1 and intents[0]["state"] == "HELD_UNCERTAIN"
        assert harness.status(intents[0]["reservation_id"])["status"] == "PENDING"
        assert harness.attempts_rows() == []
    finally:
        harness.close()


def test_c3_01b_during_fake_cancel_settles_trusted_usage_and_stops_success(
        tmp_path: Path) -> None:
    harness = make_harness(tmp_path, scenario="slow_usage")
    try:
        transport_id = "tr-" + "d" * 32
        result: dict = {}

        def run() -> None:
            result["frames"] = collect(harness.controller, payload(),
                                       transport_id=transport_id)

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        assert wait_for_counter(tmp_path, 1) == 1
        _cancel(harness.controller, transport_id)
        thread.join(timeout=15)
        assert not thread.is_alive()
        frames = result["frames"]
        assert error_code(frames) == "CANCELLED", frames
        assert not any(finish["kind"] == "stop" for finish in finishes(frames))
        assert harness.receipt_count() == 1
        rows = harness.attempts_rows()
        assert [row["state"] for row in rows] == ["SETTLED"]
        status = harness.status(rows[0]["reservation_id"])
        assert status["status"] == "OK"
        assert status["estimated"] is False
        assert status["input_used"] == 13 and status["output_used"] == 5
    finally:
        harness.close()


def test_c3_01c_two_concurrent_streams_only_one_is_cancelled(tmp_path: Path) -> None:
    harness = make_harness(tmp_path, scenario="slow_usage")
    try:
        good_id = "tr-" + "e" * 32
        cancelled_id = "tr-" + "f" * 32
        _cancel(harness.controller, cancelled_id)
        payload_a = payload(messages=[{"role": "user", "content": "stream-a"}])
        payload_b = payload(messages=[{"role": "user", "content": "stream-b"}])
        with ThreadPoolExecutor(max_workers=2) as pool:
            future_a = pool.submit(collect, harness.controller, payload_a, transport_id=good_id)
            future_b = pool.submit(collect, harness.controller, payload_b,
                                   transport_id=cancelled_id)
            frames_a = future_a.result(timeout=30)
            frames_b = future_b.result(timeout=30)
        assert error_code(frames_a) is None, frames_a
        assert any(finish["kind"] == "stop" for finish in finishes(frames_a))
        assert error_code(frames_b) == "CANCELLED", frames_b
        assert harness.receipt_count() == 1
        assert harness.snapshot()["requests"] == 1
        assert len(harness.attempts_rows()) == 1
    finally:
        harness.close()


def test_c3_01d_cancel_contract_rejects_wrong_signature_and_unknown_ids(
        tmp_path: Path) -> None:
    harness = make_harness(tmp_path)
    try:
        with pytest.raises(TypeError):
            harness.controller.cancel()  # old no-arg signature must not work
        with pytest.raises(TypeError):
            harness.controller.cancel("tr-" + "0" * 32, "aborted")  # positional
        with pytest.raises(ValueError):
            harness.controller.cancel(transport_id="", reason="aborted")
        assert harness.controller.cancel(
            transport_id="tr-" + "9" * 32, reason="aborted") is None
        assert harness.controller.cancel(
            transport_id="tr-" + "9" * 32, reason="aborted") is None
        # Late Cancel for an unknown/terminal id must not poison a new stream.
        first = collect(harness.controller, payload(), transport_id="tr-" + "8" * 32)
        assert error_code(first) is None, first
        _cancel(harness.controller, "tr-" + "8" * 32)
        second = collect(harness.controller, payload(
            messages=[{"role": "user", "content": "after late cancel"}]),
            transport_id="tr-" + "8" * 32)
        assert error_code(second) is None, second
        assert harness.receipt_count() == 2
    finally:
        harness.close()


def test_c3_01d2_server_cancel_reader_reaches_exact_contract(tmp_path: Path) -> None:
    harness = make_harness(tmp_path, scenario="slow_usage")
    calls: list[tuple[str, str]] = []
    inner = harness.controller

    class SpyController:
        def handle_envelope(self, env):
            return inner.handle_envelope(env)

        def cancel(self, *, transport_id: str, reason: str) -> None:
            calls.append((transport_id, reason))
            inner.cancel(transport_id=transport_id, reason=reason)

    spy = SpyController()
    transport_id = "tr-" + "7" * 32
    received, server, thread = uds_roundtrip(
        spy, payload(), socket_path=tmp_path / "bridge.sock",
        transport_id=transport_id, cancel_after_ack=("request_id", "aborted"))
    try:
        assert calls == [(transport_id, "aborted")]
        assert received[-1].kind == "error"
        assert received[-1].payload["code"] == "CANCELLED"
        assert harness.receipt_count() in {0, 1}
    finally:
        stop_server(server, thread)
        harness.close()


def _controller_config(root: Path) -> Path:
    document = {
        "admission_path": str(root / "admission.json"),
        "broker_config_path": str(root / "broker.json"),
        "fake_script": str(FAKE),
        "receipt_dir": str(root / "receipts"),
        "attempt_db": str(root / "attempts.sqlite3"),
        "socket_path": str(root / "bridge.sock"),
        "python": sys.executable,
        "expected_uid": 65534,
    }
    path = root / "controller.json"
    path.write_text(json.dumps(document))
    return path


def _start_controller_main(root: Path):
    env = {**os.environ, "PYTHONPATH": os.environ.get(
        "PYTHONPATH", "src:artifacts/foundation/deps")}
    return subprocess.Popen(
        [sys.executable, "-B", "-m", "autoteacher_m0.bridge.controller",
         "--config", str(_controller_config(root))],
        cwd=str(Path(__file__).resolve().parents[3]), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def test_c3_01e_sigterm_cleans_socket_and_broker_child(tmp_path: Path) -> None:
    write_admission(tmp_path)
    write_broker_config(tmp_path)
    proc = _start_controller_main(tmp_path)
    socket_path = tmp_path / "bridge.sock"
    try:
        deadline = time.monotonic() + 15
        while not socket_path.exists() and time.monotonic() < deadline:
            if proc.poll() is not None:
                break
            time.sleep(0.02)
        assert socket_path.exists(), (proc.poll(), proc.stdout.read(), proc.stderr.read())
        proc.send_signal(signal.SIGTERM)
        returncode = proc.wait(timeout=15)
        assert returncode == 0, (returncode, proc.stderr.read())
        assert not socket_path.exists()
        probe = subprocess.run(["pgrep", "-f", str(tmp_path / "broker.json")],
                               capture_output=True, text=True)
        assert probe.returncode != 0, probe.stdout
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)
        for stream in (proc.stdout, proc.stderr):
            if stream:
                stream.close()


def test_c3_01f_disconnect_does_not_kill_followup_stream(tmp_path: Path) -> None:
    harness = make_harness(tmp_path)
    socket_path = tmp_path / "bridge.sock"
    server = BridgeServer(harness.controller, str(socket_path))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 5
        while not socket_path.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.settimeout(10)
        try:
            client.connect(str(socket_path))
            document = payload()
            env = Envelope(1, "request", "tr-" + "6" * 32, 0, document,
                           payload_digest(canonical_payload_bytes(document)))
            client.sendall(encode_envelope(env) + b"\n")
            client.recv(65536)  # ack, then disconnect before any terminal frame
        finally:
            client.close()
        time.sleep(0.2)
        follow = collect(harness.controller, payload(
            messages=[{"role": "user", "content": "after disconnect"}]),
            transport_id="tr-" + "5" * 32)
        assert error_code(follow) is None, follow
        assert harness.receipt_count() == 2
    finally:
        stop_server(server, thread)
        harness.close()
