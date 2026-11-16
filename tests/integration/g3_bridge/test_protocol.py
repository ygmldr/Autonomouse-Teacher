"""G3-B B1 protocol tests (host Python allowed; no network/provider/Key).

These tests exercise the strict Envelope codec and the UDS server with a stub
Controller. The stub is NOT a trusted Controller and is not G3-B evidence for
Controller/Broker/Fake behavior.
"""
from __future__ import annotations

import json
import socket
import threading
import time
import uuid

import pytest

from autoteacher_m0.bridge import (
    MAX_REQUEST_BYTES, MAX_RESPONSE_BYTES, BridgeError,
)
from autoteacher_m0.bridge.ipc_server import BridgeServer, FrameReader
from autoteacher_m0.bridge.protocol import (
    ERROR_CODES, Envelope, canonical_payload_bytes, encode_envelope,
    parse_envelope, payload_digest, validate_chunk_payload,
    validate_request_payload,
)

DIGEST = "a" * 64
TRANSPORT = "tr-" + "b" * 32


def request_payload(**overrides):
    payload = {
        "sessionId": "g3b-session-test",
        "provider": "offline-test-only-g3b",
        "model": "fixture-bridge-v1",
        "messages": [{"role": "user", "content": [{"type": "text", "text": "hello"}]}],
        "tools": [],
        "system": None,
        "maxTokens": 256,
        "stream": True,
        "purpose": None,
    }
    payload.update(overrides)
    return payload


def request_env(payload=None, *, seq=0, transport=TRANSPORT):
    return Envelope(v=1, kind="request", transport_id=transport, seq=seq,
                    payload=payload or request_payload(), hash=None)


def chunk_payload(**chunk):
    base = {"type": "text-delta", "index": 0, "text": "hi"}
    base.update(chunk)
    return {"chunk": base}


def finish_payload(kind="stop"):
    reason = {"kind": kind}
    if kind in {"aborted", "error"}:
        reason["failure"] = {"message": "safe fixture failure", "code": "FIXTURE"}
    return {"reason": reason}


def error_payload(code="BUDGET_DENIED"):
    return {"code": code, "message": code, "retryable": False}


def encode_line(kind, payload, *, seq=1, transport=TRANSPORT):
    return encode_envelope(Envelope(v=1, kind=kind, transport_id=transport,
                                    seq=seq, payload=payload, hash=None)) + b"\n"


def raw_envelope(**fields):
    base = {"v": 1, "kind": "request", "transport_id": TRANSPORT,
            "seq": 0, "payload": request_payload()}
    base.update(fields)
    return json.dumps(base, separators=(",", ":")).encode()


class StubController:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.cancel_calls = []
        self.cancel_event = threading.Event()

    def handle_envelope(self, env):
        yield from self.outputs

    def cancel(self, *, transport_id, reason):
        self.cancel_calls.append((transport_id, reason))
        self.cancel_event.set()


_BUFFERS: dict[int, bytes] = {}


def read_frame(sock):
    key = id(sock)
    buffer = _BUFFERS.get(key, b"")
    while b"\n" not in buffer:
        part = sock.recv(65536)
        if not part:
            return None
        buffer += part
    line, _, rest = buffer.partition(b"\n")
    _BUFFERS[key] = rest
    return parse_envelope(line + b"\n")


def recv_frames(sock, limit=300):
    frames = []
    while len(frames) < limit:
        frame = read_frame(sock)
        if frame is None:
            break
        frames.append(frame)
        if frame.kind in {"finish", "error"}:
            break
    return frames


class RunningServer:
    def __init__(self, controller):
        self.path = f"/tmp/g3b-b1-{uuid.uuid4().hex[:12]}.sock"
        self.server = BridgeServer(controller, socket_path=self.path)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.error = None
        self.thread.start()
        for _ in range(100):
            if __import__("os").path.exists(self.path):
                break
            time.sleep(0.01)
        else:
            raise AssertionError("server did not bind")

    def connect(self):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect(self.path)
        return sock

    def close(self):
        self.server.shutdown()
        self.thread.join(timeout=5)
        try:
            __import__("os").unlink(self.path)
        except OSError:
            pass


# ---------------- codec / validators ----------------

def test_valid_request_roundtrip_and_hash():
    raw = encode_envelope(request_env())
    env = parse_envelope(raw + b"\n")
    assert env.kind == "request" and env.v == 1 and env.seq == 0
    assert env.payload == request_payload()
    assert env.hash == payload_digest(canonical_payload_bytes(request_payload()))
    assert encode_envelope(env) == raw


def test_envelope_rejects_duplicate_json_keys():
    raw = (b'{"v":1,"kind":"request","transport_id":"' + TRANSPORT.encode() +
           b'","seq":0,"payload":{"sessionId":"a","sessionId":"b"}}')
    with pytest.raises(BridgeError, match="DUPLICATE_KEY"):
        parse_envelope(raw)


@pytest.mark.parametrize("raw", [
    b'{"v":1,"kind":"request","transport_id":"' + TRANSPORT.encode() + b'","seq":0,"payload":{"maxTokens":NaN}}',
    b'{"v":1,"kind":"request","transport_id":"' + TRANSPORT.encode() + b'","seq":0,"payload":{"maxTokens":Infinity}}',
])
def test_envelope_rejects_nan_inf(raw):
    with pytest.raises(BridgeError, match="NAN_OR_INF"):
        parse_envelope(raw)


def test_envelope_rejects_bad_utf8_and_unknown_fields():
    with pytest.raises(BridgeError, match="BAD_TYPE"):
        parse_envelope(b'{"v":1,"kind":"request","transport_id":"' + TRANSPORT.encode() + b'","seq":0,"payload":{"x":"\xff"}}')
    with pytest.raises(BridgeError, match="UNKNOWN_FIELD"):
        parse_envelope(raw_envelope(extra=True))
    with pytest.raises(BridgeError, match="BAD_TYPE"):
        parse_envelope(raw_envelope(seq=True))
    with pytest.raises(BridgeError, match="PROTOCOL_VERSION"):
        parse_envelope(raw_envelope(v=2))
    with pytest.raises(BridgeError, match="UNKNOWN_KIND"):
        parse_envelope(raw_envelope(kind="nope"))


def test_envelope_size_is_checked_before_json():
    raw = b"{" + b" " * (MAX_REQUEST_BYTES + 1)
    with pytest.raises(BridgeError, match="FRAME_TOO_LARGE"):
        parse_envelope(raw)


def test_request_payload_no_attempt_ordinal_and_limits():
    with pytest.raises(BridgeError, match="UNKNOWN_FIELD"):
        validate_request_payload(request_payload(attemptOrdinal=1))
    with pytest.raises(BridgeError, match="UNKNOWN_FIELD"):
        validate_request_payload(request_payload(call_id="call-" + "0" * 48))
    with pytest.raises(BridgeError, match="BAD_TYPE"):
        validate_request_payload(request_payload(maxTokens=True))
    with pytest.raises(BridgeError, match="BAD_TYPE"):
        validate_request_payload(request_payload(stream=False))
    with pytest.raises(BridgeError, match="BAD_TYPE"):
        validate_request_payload(request_payload(sessionId=""))
    with pytest.raises(BridgeError, match="BAD_TYPE"):
        validate_request_payload(request_payload(purpose="judge"))


def test_depth_and_control_rejected():
    deep = {"x": None}
    cursor = deep
    for _ in range(40):
        cursor["x"] = {"x": None}
        cursor = cursor["x"]
    with pytest.raises(BridgeError, match="DEPTH_EXCEEDED"):
        validate_request_payload(request_payload(messages=[deep]))
    with pytest.raises(BridgeError, match="BAD_TYPE"):
        validate_request_payload(request_payload(system="bad\u0001control"))


def test_chunk_whitelist_and_usage():
    validate_chunk_payload({"chunk": {"type": "block-start", "index": 0, "blockType": "text"}})
    validate_chunk_payload({"chunk": {"type": "text-delta", "index": 0, "text": "x"}})
    validate_chunk_payload({"chunk": {"type": "usage", "usage": {"inputTokens": 1, "outputTokens": 2}}})
    with pytest.raises(BridgeError):
        validate_chunk_payload({"chunk": {"type": "finish", "reason": {"kind": "stop"}}})
    with pytest.raises(BridgeError):
        validate_chunk_payload({"chunk": {"type": "text-delta", "index": True, "text": "x"}})
    with pytest.raises(BridgeError):
        validate_chunk_payload({"chunk": {"type": "usage", "usage": {"inputTokens": True, "outputTokens": 2}}})
    with pytest.raises(BridgeError):
        validate_chunk_payload({"chunk": {"type": "text-delta", "index": 0, "text": "x", "extra": 1}})


def test_error_code_set_is_frozen():
    assert {"FRAME_TOO_LARGE", "SEQ_OUT_OF_ORDER", "UNKNOWN_KIND",
            "DUPLICATE_KEY", "NAN_OR_INF", "SETTLEMENT_UNCERTAIN"} <= ERROR_CODES


# ---------------- server behavior ----------------

def test_server_ack_chunks_finish_and_single_finish():
    outputs = [
        Envelope(1, "chunk", TRANSPORT, 0, chunk_payload(), None),
        Envelope(1, "chunk", TRANSPORT, 0, chunk_payload(type="text-delta", index=1, text="!"), None),
        Envelope(1, "finish", TRANSPORT, 0, finish_payload(), None),
    ]
    running = RunningServer(StubController(outputs))
    try:
        with running.connect() as sock:
            sock.sendall(encode_envelope(request_env()) + b"\n")
            frames = recv_frames(sock)
        assert frames[0].kind == "ack"
        assert frames[0].payload == {"request_id": TRANSPORT, "accepted": True, "code": None}
        assert [f.kind for f in frames] == ["ack", "chunk", "chunk", "finish"]
        assert [f.seq for f in frames] == [1, 2, 3, 4]
        assert frames[-1].payload["reason"]["kind"] == "stop"
    finally:
        running.close()


def test_server_oversized_request_fails_before_ack():
    running = RunningServer(StubController([]))
    try:
        with running.connect() as sock:
            sock.sendall(b"{" + b" " * (MAX_REQUEST_BYTES + 80))
            frame = read_frame(sock)
        assert frame is not None and frame.kind == "error"
        assert frame.payload["code"] == "FRAME_TOO_LARGE"
    finally:
        running.close()


def test_server_truncated_eof_without_newline_fails_closed():
    running = RunningServer(StubController([]))
    try:
        with running.connect() as sock:
            sock.sendall(b'{"v":1,"kind":"request"')
            sock.shutdown(socket.SHUT_WR)
            frame = read_frame(sock)
        assert frame is not None and frame.kind == "error"
    finally:
        running.close()


def test_server_rejects_oversized_response_frame():
    huge = {"chunk": {"type": "text-delta", "index": 0, "text": "x" * (MAX_RESPONSE_BYTES + 10)}}
    running = RunningServer(StubController([Envelope(1, "chunk", TRANSPORT, 0, huge, None)]))
    try:
        with running.connect() as sock:
            sock.sendall(encode_envelope(request_env()) + b"\n")
            frames = recv_frames(sock)
        assert frames[0].kind == "ack"
        assert frames[-1].kind == "error"
        assert frames[-1].payload["code"] == "RESPONSE_FRAME_TOO_LARGE"
    finally:
        running.close()


def test_server_controller_error_is_terminal_error_frame():
    outputs = [Envelope(1, "error", TRANSPORT, 0, error_payload(), None)]
    running = RunningServer(StubController(outputs))
    try:
        with running.connect() as sock:
            sock.sendall(encode_envelope(request_env()) + b"\n")
            frames = recv_frames(sock)
        assert [f.kind for f in frames] == ["ack", "error"]
        assert frames[-1].payload["code"] == "BUDGET_DENIED"
    finally:
        running.close()


def test_server_cancel_reader_delivers_cancel_independently():
    controller = StubController([Envelope(1, "finish", TRANSPORT, 0,
                                          finish_payload("aborted"), None)])
    running = RunningServer(controller)
    try:
        with running.connect() as sock:
            sock.sendall(encode_envelope(request_env()) + b"\n")
            ack = read_frame(sock)
            assert ack.kind == "ack"
            cancel = Envelope(1, "cancel", TRANSPORT, 1,
                              {"request_id": TRANSPORT, "reason": "aborted"}, None)
            sock.sendall(encode_envelope(cancel) + b"\n")
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and not controller.cancel_calls:
                time.sleep(0.01)
            frames = recv_frames(sock)
        assert controller.cancel_calls == [(TRANSPORT, "aborted")]
        assert frames[-1].kind == "finish" and frames[-1].payload["reason"]["kind"] == "aborted"
    finally:
        running.close()


def test_frame_reader_memory_is_bounded_without_newline():
    left, right = socket.socketpair()
    try:
        reader = FrameReader(left, max_bytes=1024)
        right.sendall(b"x" * 2048)
        with pytest.raises(BridgeError, match="FRAME_TOO_LARGE"):
            reader.readline()
        assert reader.buffered_bytes() <= 1024
    finally:
        left.close()
        right.close()


def test_server_rejects_nonzero_request_seq():
    running = RunningServer(StubController([]))
    try:
        with running.connect() as sock:
            sock.sendall(encode_envelope(request_env(seq=1)) + b"\n")
            frame = read_frame(sock)
        assert frame is not None and frame.kind == "error"
        assert frame.payload["code"] == "SEQ_OUT_OF_ORDER"
    finally:
        running.close()


def test_escaped_newlines_in_messages_are_allowed():
    payload = request_payload()
    payload["messages"] = [
        {"role": "user", "content": [{"type": "text", "text": "line1\nline2\ttabbed"}]},
    ]
    validate_request_payload(payload)
    env = request_env(payload=payload)
    assert parse_envelope(encode_envelope(env) + b"\n").payload["messages"][0]["content"][0]["text"].endswith("tabbed")
