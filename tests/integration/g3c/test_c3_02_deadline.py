"""G3-C C3-02 host tests: real Broker/Fake deadlines (no Key/network).

C3-02A: a Broker that stays alive but never writes stdout must produce a
bounded ``BrokerTimeoutError`` and the channel must never re-send the in-flight
message. C3-02B: a stuck Fake that already wrote its receipt must raise
``FakeTimeout`` carrying that receipt. The IPC response watchdog is also
exercised here: a synchronous Controller iteration that cannot be interrupted
still gets a real error frame and a closed connection (fail-closed).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import socket
import sys
import threading
import time

import pytest

from autoteacher_m0.bridge.broker_client import (
    BrokerClient, BrokerClientError, BrokerTimeoutError,
)
from autoteacher_m0.bridge.fake_backend import FakeBackend, FakeTimeout
from autoteacher_m0.bridge.ipc_server import BridgeServer
from autoteacher_m0.bridge.protocol import Envelope, encode_envelope, parse_envelope

FAKE = Path(__file__).resolve().parents[3] / "spikes/g3b-trusted-bridge/fake/fake_provider.py"
TRANSPORT = "tr-" + "d" * 32


def _fake_payload(mode: str, nonce: str) -> bytes:
    return json.dumps({
        "schema": "m0.g3b.fake.v1", "call_id": "call-" + "0" * 48,
        "prepared_digest": "b" * 64, "route_id": "offline-test-only-g3b",
        "model": "fixture-bridge-v1", "messages": [], "tools": [],
        "system": "", "max_output_tokens": 16, "stream": True,
        "mode": mode, "nonce": nonce,
    }, sort_keys=True, separators=(",", ":")).encode()


def _request_payload() -> dict:
    return {
        "sessionId": "g3c-c3-02", "provider": "offline-test-only-g3b",
        "model": "fixture-bridge-v1",
        "messages": [{"role": "user", "content": "hello"}], "tools": [],
        "system": None, "maxTokens": 64, "stream": True,
        "purpose": "conversation",
    }


def _make_slow_broker(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[str, Path]:
    """Slow Broker run by the trusted Python interpreter, not an exec'd wrapper.

    The old helper wrote a ``#!/bin/sh`` wrapper into ``tmp_path`` and made it
    executable.  The fixed OCI sandbox mounts ``/tmp`` ``noexec``, so ``execve``
    of that wrapper is denied by the kernel.  Python does not ``execve`` the
    imported module: the child interpreter reads it through ``PYTHONPATH``, so
    the same test works on an executable and a ``noexec`` tmpfs without
    removing ``--read-only-tmpfs=false`` or any other sandbox flag.
    """
    log = tmp_path / "broker-requests.log"
    shadow = tmp_path / "shadow"
    package = shadow / "autoteacher_m0" / "accounting"
    package.mkdir(parents=True)
    (shadow / "autoteacher_m0" / "__init__.py").write_text("", encoding="utf-8")
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "broker.py").write_text(
        "import sys, time\n"
        "from pathlib import Path\n"
        "args = sys.argv[1:]\n"
        "path = Path(args[args.index('--config') + 1])\n"
        "path.write_text('READY\\n')\n"
        "for line in sys.stdin:\n"
        "    with open(path, 'a', encoding='utf-8') as handle:\n"
        "        handle.write('REQ ' + line.strip() + '\\n')\n"
        "        handle.flush()\n"
        "    time.sleep(30)\n",
        encoding="utf-8")
    # Only the child interpreter sees this import root; the pytest process is
    # unaffected and monkeypatch restores the environment after the test.
    monkeypatch.setenv("PYTHONPATH", str(shadow))
    return sys.executable, log


def _wait_for(path: Path, timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists() and path.read_text(encoding="utf-8").strip():
            return True
        time.sleep(0.01)
    return False


def test_c3_02a_broker_alive_without_stdout_times_out_once(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    python, log = _make_slow_broker(tmp_path, monkeypatch)
    client = BrokerClient(config_path=str(log), python=python, timeout_s=5.0)
    client.start()
    try:
        started = time.monotonic()
        with pytest.raises(BrokerTimeoutError) as exc:
            client.request("snapshot", {},
                           deadline_monotonic=started + 1.0)
        elapsed = time.monotonic() - started
        assert exc.value.code == "BROKER_TIMEOUT"
        assert 0.80 <= elapsed < 3.0, elapsed
        assert _wait_for(log)
        text = log.read_text(encoding="utf-8")
        assert text.count("REQ ") == 1, text
        assert "READY" in text
        # Timeout poisons the channel: later calls fail closed without a re-send.
        with pytest.raises(BrokerClientError):
            client.request("snapshot", {},
                           deadline_monotonic=time.monotonic() + 5.0)
        time.sleep(0.05)
        assert log.read_text(encoding="utf-8").count("REQ ") == 1
        assert client.proc is None or client.proc.poll() is not None
    finally:
        client.close()


def test_c3_02a_timeout_remaining_uses_deadline_not_only_timeout_s(tmp_path: Path) -> None:
    client = BrokerClient(config_path=str(tmp_path / "unused.json"),
                          python=sys.executable, timeout_s=5.0)
    now = time.monotonic()
    assert 0.15 <= client._remaining(now + 0.2) <= 0.2
    assert client._remaining(None) == 5.0
    assert client._remaining(now + 30.0) == 5.0
    client.close()


def test_c3_02b_fake_stuck_with_receipt_raises_fake_timeout(tmp_path: Path) -> None:
    nonce = "c" * 32
    payload = _fake_payload("timeout", nonce)
    fake = FakeBackend(script=str(FAKE), receipt_dir=str(tmp_path / "receipts"),
                       python=sys.executable, timeout_s=5.0)
    started = time.monotonic()
    try:
        with pytest.raises(FakeTimeout) as exc:
            for _frame in fake.stream(payload,
                                      deadline_monotonic=started + 1.5):
                pass
        elapsed = time.monotonic() - started
        assert elapsed < 5.0, elapsed
        receipt = exc.value.receipt
        assert receipt is not None
        assert receipt.raw_sha256 == hashlib.sha256(payload).hexdigest()
        assert receipt.nonce == nonce
        assert fake.received_count() == 1
        assert fake._active_proc is None
    finally:
        fake.close()


class _BlockingController:
    """Yields one chunk, then blocks far past the IPC deadline."""

    def __init__(self) -> None:
        self.cancel_calls: list[tuple[str, str]] = []

    def handle_envelope(self, env):
        yield Envelope(1, "chunk", env.transport_id, 2,
                       {"chunk": {"type": "text-delta", "index": 0,
                                  "text": "partial"}}, None)
        time.sleep(2.0)
        yield Envelope(1, "finish", env.transport_id, 3,
                       {"reason": {"kind": "stop"}}, None)

    def cancel(self, *, transport_id: str, reason: str) -> None:
        self.cancel_calls.append((transport_id, reason))


class _RunningServer:
    def __init__(self, controller, tmp_path: Path, **kwargs) -> None:
        self.path = str(tmp_path / "bridge.sock")
        self.server = BridgeServer(controller, self.path, **kwargs)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        deadline = time.monotonic() + 5
        while not Path(self.path).exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert Path(self.path).exists()

    def connect(self) -> socket.socket:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect(self.path)
        return sock

    def close(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=5)


def _read_frames(sock: socket.socket, limit: int = 20):
    buffer = b""
    frames = []
    while len(frames) < limit:
        chunk = sock.recv(65536)
        if not chunk:
            break
        buffer += chunk
        while b"\n" in buffer:
            line, buffer = buffer.split(b"\n", 1)
            if line:
                frames.append(parse_envelope(line + b"\n"))
        if frames and frames[-1].kind in {"finish", "error"}:
            break
    return frames


def test_c3_02d_response_watchdog_writes_error_and_closes(tmp_path: Path) -> None:
    controller = _BlockingController()
    running = _RunningServer(controller, tmp_path,
                             first_frame_deadline_s=5.0,
                             request_deadline_s=0.4)
    try:
        sock = running.connect()
        try:
            request = Envelope(1, "request", TRANSPORT, 0, _request_payload(), None)
            started = time.monotonic()
            sock.sendall(encode_envelope(request) + b"\n")
            frames = _read_frames(sock)
            elapsed = time.monotonic() - started
        finally:
            sock.close()
        kinds = [frame.kind for frame in frames]
        assert kinds[0] == "ack"
        assert "finish" not in kinds
        assert frames[-1].kind == "error"
        assert frames[-1].payload["code"] == "DEADLINE_EXCEEDED"
        assert elapsed < 1.6, elapsed
        deadline = time.monotonic() + 4.0
        while running.server.active_connections and time.monotonic() < deadline:
            time.sleep(0.02)
        assert running.server.active_connections == 0
    finally:
        running.close()
