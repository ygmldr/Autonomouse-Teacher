"""G3-C C3-03 host tests: IPC first-frame deadline and resource bounds.

C3-03A/B: empty and 1-byte-at-a-time slow connections are interrupted by a real
first-frame deadline and fully cleaned. C3-03C: active connection cap rejects
overload without spawning another worker thread. C3-03E: response byte budgets
are per connection (two connections each get the full 1 MiB budget). Invalid
frames never reach the Controller, so they cannot produce a Fake send.
"""
from __future__ import annotations

import json
from pathlib import Path
import socket
import threading
import time

import pytest

from autoteacher_m0.bridge import (
    MAX_REQUEST_BYTES, MAX_TOTAL_REQUEST_BYTES,
)
from autoteacher_m0.bridge.ipc_server import BridgeServer
from autoteacher_m0.bridge.protocol import Envelope, encode_envelope, parse_envelope

TRANSPORT_A = "tr-" + "a" * 32
TRANSPORT_B = "tr-" + "b" * 32


def _payload(transport: str = TRANSPORT_A) -> dict:
    return {
        "sessionId": "g3c-c3-03", "provider": "offline-test-only-g3b",
        "model": "fixture-bridge-v1",
        "messages": [{"role": "user", "content": "hello"}], "tools": [],
        "system": None, "maxTokens": 64, "stream": True,
        "purpose": "conversation",
    }


def _request(transport: str = TRANSPORT_A, seq: int = 0) -> bytes:
    return encode_envelope(Envelope(1, "request", transport, seq,
                                    _payload(transport), None)) + b"\n"


def _frame(kind: str, payload: dict, transport: str, seq: int) -> bytes:
    return encode_envelope(Envelope(1, kind, transport, seq, payload, None)) + b"\n"


def _stop_finish() -> dict:
    return {"reason": {"kind": "stop"}}


def _chunk(text: str) -> dict:
    return {"chunk": {"type": "text-delta", "index": 0, "text": text}}


class _CountingController:
    def __init__(self) -> None:
        self.calls = 0
        self.cancel_calls: list[tuple[str, str]] = []

    def handle_envelope(self, env):
        self.calls += 1
        yield Envelope(1, "finish", env.transport_id, 2, _stop_finish(), None)

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

    def connect(self, timeout: float = 5) -> socket.socket:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect(self.path)
        return sock

    def wait_active(self, count: int, timeout: float = 2.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.server.active_connections == count:
                return True
            time.sleep(0.01)
        return self.server.active_connections == count

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


def test_c3_03a_empty_connection_first_frame_deadline(tmp_path: Path) -> None:
    controller = _CountingController()
    running = _RunningServer(controller, tmp_path, first_frame_deadline_s=0.30,
                             request_deadline_s=5.0, max_connections=4)
    try:
        sock = running.connect()
        started = time.monotonic()
        try:
            frames = _read_frames(sock)
            elapsed = time.monotonic() - started
        finally:
            sock.close()
        assert elapsed < 2.0, elapsed
        assert frames and frames[-1].kind == "error"
        assert frames[-1].payload["code"] == "DEADLINE_EXCEEDED"
        assert controller.calls == 0
        assert running.wait_active(0)
        assert running.server.thread_count == 0
    finally:
        running.close()


def test_c3_03b_slow_one_byte_connection_is_interrupted(tmp_path: Path) -> None:
    controller = _CountingController()
    running = _RunningServer(controller, tmp_path, first_frame_deadline_s=0.30,
                             request_deadline_s=5.0, max_connections=4)
    try:
        sock = running.connect()
        started = time.monotonic()
        try:
            for _ in range(12):
                try:
                    sock.sendall(b"{")
                except OSError:
                    break
                time.sleep(0.06)
            frames = _read_frames(sock)
            elapsed = time.monotonic() - started
        finally:
            sock.close()
        assert elapsed < 2.5, elapsed
        assert frames and frames[-1].kind == "error"
        assert frames[-1].payload["code"] == "DEADLINE_EXCEEDED"
        assert controller.calls == 0
        assert running.wait_active(0)
        assert running.server.thread_count == 0
    finally:
        running.close()


def test_c3_03c_active_connection_cap_rejects_without_extra_threads(tmp_path: Path) -> None:
    controller = _CountingController()
    running = _RunningServer(controller, tmp_path, first_frame_deadline_s=5.0,
                             request_deadline_s=5.0, max_connections=2)
    first = running.connect()
    second = running.connect()
    try:
        assert running.wait_active(2), running.server.active_connections
        assert running.server.thread_count == 2
        third = running.connect()
        try:
            frames = _read_frames(third, limit=3)
        finally:
            third.close()
        assert frames and frames[-1].kind == "error"
        assert frames[-1].payload["code"] == "TOO_MANY_CONNECTIONS"
        assert running.server.active_connections == 2
        assert running.server.thread_count == 2
    finally:
        first.close()
        second.close()
        assert running.wait_active(0, timeout=3.0)
        assert running.server.thread_count == 0
        running.close()


class _BudgetController:
    """Per-transport response scripts; used to compare two byte budgets."""

    def __init__(self, scripts: dict[str, list[tuple[str, dict]]]) -> None:
        self.scripts = scripts
        self.calls = 0

    def handle_envelope(self, env):
        self.calls += 1
        for kind, payload in self.scripts[env.transport_id]:
            yield Envelope(1, kind, env.transport_id, 0, payload, None)

    def cancel(self, *, transport_id: str, reason: str) -> None:
        raise AssertionError("cancel not expected")


def test_c3_03e_response_byte_budget_is_per_connection(tmp_path: Path) -> None:
    a_error = {"code": "INTERNAL", "message": "x" * 512, "retryable": False}
    a_last = _frame("error", a_error, TRANSPORT_A, 2)
    ack_b = _frame("ack", {"request_id": TRANSPORT_B, "accepted": True,
                           "code": None}, TRANSPORT_B, 1)
    assert len(a_last) > len(ack_b) + 10, (len(a_last), len(ack_b))

    # Connection A leaves a large final frame in the old class-level
    # `_last_frame_bytes`; connection B legitimately reaches the 1 MiB budget.
    chunks = 255
    base_text = 3_810
    text_lengths = [base_text] * chunks

    def total_b() -> int:
        total = len(ack_b)
        for index, length in enumerate(text_lengths):
            total += len(_frame("chunk", _chunk("x" * length),
                                TRANSPORT_B, 2 + index))
        total += len(_frame("finish", _stop_finish(), TRANSPORT_B, 2 + chunks))
        return total

    target = MAX_TOTAL_REQUEST_BYTES - 1
    difference = target - total_b()
    assert difference > 0
    increment, remainder = divmod(difference, chunks)
    text_lengths = [base_text + increment] * chunks
    for index in range(remainder):
        text_lengths[index] += 1
    assert total_b() == target, (total_b(), target)
    assert all(len(_frame("chunk", _chunk("x" * length), TRANSPORT_B,
                          2 + index)) < 65_536
               for index, length in enumerate(text_lengths))

    scripts = {
        TRANSPORT_A: [("error", a_error)],
        TRANSPORT_B: ([("chunk", _chunk("x" * length))
                       for length in text_lengths]
                      + [("finish", _stop_finish())]),
    }
    controller = _BudgetController(scripts)
    running = _RunningServer(controller, tmp_path, first_frame_deadline_s=5.0,
                             request_deadline_s=10.0, max_connections=4)
    try:
        first = running.connect(timeout=10)
        try:
            first.sendall(_request(TRANSPORT_A))
            frames_a = _read_frames(first, limit=3)
        finally:
            first.close()
        assert frames_a[-1].kind == "error"
        # The old shared counter would start B at len(a_last) and exceed the
        # budget before finish; the fixed per-connection counter must not.
        second = running.connect(timeout=10)
        try:
            second.sendall(_request(TRANSPORT_B))
            frames_b = _read_frames(second, limit=300)
        finally:
            second.close()
        assert [frame.kind for frame in frames_b[:1]] == ["ack"]
        assert "error" not in {frame.kind for frame in frames_b}, [
            frame.payload for frame in frames_b if frame.kind == "error"]
        assert frames_b[-1].kind == "finish"
        assert sum(len(_frame("chunk", _chunk("x" * length), TRANSPORT_B,
                              2 + index))
                   for index, length in enumerate(text_lengths)) > 800_000
        assert running.wait_active(0)
    finally:
        running.close()


def _nested(depth: int) -> dict:
    value: dict = {}
    cursor = value
    for _ in range(depth):
        cursor["x"] = {}
        cursor = cursor["x"]
    return value


def _raw_case(case: str) -> bytes:
    if case == "oversized":
        return b"{" + b" " * (MAX_REQUEST_BYTES + 80)
    if case == "bad_utf8":
        return b'{"v":1,"kind":"request","transport_id":"' + TRANSPORT_A.encode() + \
            b'","seq":0,"payload":{"sessionId":"\xff"}}\n'
    if case == "duplicate_key":
        return (b'{"v":1,"kind":"request","transport_id":"' + TRANSPORT_A.encode()
                + b'","seq":0,"payload":' + json.dumps(_payload()).encode()
                + b',"payload":' + json.dumps(_payload()).encode() + b"}\n")
    if case == "deep":
        document = {"v": 1, "kind": "request", "transport_id": TRANSPORT_A,
                    "seq": 0, "payload": {"deep": _nested(40)}}
        return (json.dumps(document, separators=(",", ":")).encode() + b"\n")
    if case == "invalid_seq":
        return _request(TRANSPORT_A, seq=1)
    if case == "unknown_kind":
        document = {"v": 1, "kind": "nope", "transport_id": TRANSPORT_A,
                    "seq": 0, "payload": {}}
        return (json.dumps(document, separators=(",", ":")).encode() + b"\n")
    raise AssertionError(case)


@pytest.mark.parametrize(("case", "expected"), [
    ("oversized", "FRAME_TOO_LARGE"),
    ("bad_utf8", "BAD_TYPE"),
    ("duplicate_key", "DUPLICATE_KEY"),
    ("deep", "DEPTH_EXCEEDED"),
    ("invalid_seq", "SEQ_OUT_OF_ORDER"),
    ("unknown_kind", "UNKNOWN_KIND"),
])
def test_c3_03f_invalid_first_frames_never_reach_controller(
        tmp_path: Path, case: str, expected: str) -> None:
    controller = _CountingController()
    running = _RunningServer(controller, tmp_path, first_frame_deadline_s=5.0,
                             request_deadline_s=5.0, max_connections=4)
    try:
        sock = running.connect()
        try:
            sock.sendall(_raw_case(case))
            frames = _read_frames(sock, limit=3)
        finally:
            sock.close()
        assert frames and frames[-1].kind == "error"
        assert frames[-1].payload["code"] == expected, frames[-1].payload
        assert controller.calls == 0
        assert running.wait_active(0)
        assert running.server.thread_count == 0
    finally:
        running.close()


def test_c3_03f_client_send_after_error_cannot_start_a_request(tmp_path: Path) -> None:
    controller = _CountingController()
    running = _RunningServer(controller, tmp_path, first_frame_deadline_s=5.0,
                             request_deadline_s=5.0, max_connections=2)
    try:
        sock = running.connect()
        try:
            sock.sendall(_request(TRANSPORT_A, seq=1))
            frames = _read_frames(sock, limit=3)
            assert frames[-1].kind == "error"
            assert frames[-1].payload["code"] == "SEQ_OUT_OF_ORDER"
            try:
                sock.sendall(_request(TRANSPORT_A))
            except OSError:
                pass
            time.sleep(0.05)
        finally:
            sock.close()
        assert controller.calls == 0
        assert running.wait_active(0)
        assert running.server.thread_count == 0
    finally:
        running.close()


def test_c3_03f_truncated_frame_without_lf_fails_closed(tmp_path: Path) -> None:
    controller = _CountingController()
    running = _RunningServer(controller, tmp_path, first_frame_deadline_s=5.0,
                             request_deadline_s=5.0, max_connections=4)
    try:
        sock = running.connect()
        try:
            sock.sendall(_request(TRANSPORT_A).rstrip(b"\n"))
            sock.shutdown(socket.SHUT_WR)
            frames = _read_frames(sock, limit=3)
        finally:
            sock.close()
        assert frames and frames[-1].kind == "error"
        assert frames[-1].payload["code"] == "REQUEST_INVALID"
        assert controller.calls == 0
    finally:
        running.close()


def test_c3_03f_finish_and_error_are_terminal(tmp_path: Path) -> None:
    seen = {"after_finish": False, "after_error": False}

    class _TerminalController:
        def __init__(self, kind: str) -> None:
            self.kind = kind

        def handle_envelope(self, env):
            if self.kind == "finish":
                yield Envelope(1, "finish", env.transport_id, 2,
                               _stop_finish(), None)
                seen["after_finish"] = True
                yield Envelope(1, "finish", env.transport_id, 3,
                               _stop_finish(), None)
            else:
                yield Envelope(1, "error", env.transport_id, 2,
                               {"code": "INTERNAL", "message": "INTERNAL",
                                "retryable": False}, None)
                seen["after_error"] = True
                yield Envelope(1, "finish", env.transport_id, 3,
                               _stop_finish(), None)

        def cancel(self, *, transport_id: str, reason: str) -> None:
            pass

    for kind in ("finish", "error"):
        running = _RunningServer(_TerminalController(kind), tmp_path,
                                 first_frame_deadline_s=5.0,
                                 request_deadline_s=5.0, max_connections=2)
        try:
            sock = running.connect()
            try:
                sock.sendall(_request(TRANSPORT_A))
                frames = _read_frames(sock, limit=10)
            finally:
                sock.close()
            assert frames[-1].kind == kind
            assert [frame.kind for frame in frames].count(kind) == 1
        finally:
            running.close()
    assert seen == {"after_finish": False, "after_error": False}


def test_c3_03g_cancel_wrong_signature_is_logged_not_silently_swallowed(tmp_path: Path) -> None:
    release = threading.Event()

    class _BadCancelController:
        def handle_envelope(self, env):
            yield Envelope(1, "chunk", env.transport_id, 2,
                           _chunk("start"), None)
            release.wait(timeout=5)
            yield Envelope(1, "finish", env.transport_id, 3,
                           _stop_finish(), None)

        def cancel(self):  # deliberately wrong signature (old G3-B bug)
            raise AssertionError("must never be called without kwargs")

    running = _RunningServer(_BadCancelController(), tmp_path,
                             first_frame_deadline_s=5.0,
                             request_deadline_s=5.0, max_connections=2)
    try:
        sock = running.connect()
        try:
            sock.sendall(_request(TRANSPORT_A))
            first = _read_frames(sock, limit=2)
            assert first[-1].kind == "chunk"
            cancel = Envelope(1, "cancel", TRANSPORT_A, 1,
                              {"request_id": TRANSPORT_A, "reason": "aborted"}, None)
            sock.sendall(encode_envelope(cancel) + b"\n")
            deadline = time.monotonic() + 3
            while not running.server.cancel_failures and time.monotonic() < deadline:
                time.sleep(0.01)
            assert running.server.cancel_failures == ["TypeError"]
            release.set()
            rest = _read_frames(sock, limit=3)
        finally:
            sock.close()
        assert rest[-1].kind == "finish"
    finally:
        release.set()
        running.close()
