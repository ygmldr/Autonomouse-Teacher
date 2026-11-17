#!/usr/bin/env python3
"""Deliberately untrusted UDS stub for B1 adapter tests.

This is NOT a trusted Controller and NOT G3-B evidence for admission/budget/
claim/Fake semantics. It only emits protocol-valid or intentionally malformed
frames so the candidate-side adapter can be tested in the container.
"""
from __future__ import annotations
import json
import os
import socket
import sys
import time

SOCKET = "/work/g3b/bridge.sock"
MODE = os.environ.get("G3B_STUB_MODE", "ok")


def payload(kind, extra):
    return extra


def frame(kind, transport, seq, payload, *, hash=None):
    value = {"v": 1, "kind": kind, "transport_id": transport, "seq": seq, "payload": payload}
    if hash is not None:
        value["hash"] = hash
    return (json.dumps(value, separators=(",", ":"), sort_keys=True) + "\n").encode()


def main() -> int:
    os.makedirs(os.path.dirname(SOCKET), mode=0o700, exist_ok=True)
    try:
        os.unlink(SOCKET)
    except FileNotFoundError:
        pass
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(SOCKET)
    os.chmod(SOCKET, 0o600)
    server.listen(1)
    conn, _ = server.accept()
    try:
        buf = b""
        while b"\n" not in buf:
            part = conn.recv(65536)
            if not part:
                return 0
            buf += part
        request = json.loads(buf.split(b"\n", 1)[0])
        transport = request["transport_id"]
        conn.sendall(frame("ack", transport, 1,
                           {"request_id": transport, "accepted": True, "code": None}))
        seq = 2
        if MODE == "ok":
            conn.sendall(frame("chunk", transport, seq,
                               {"chunk": {"type": "block-start", "index": 0,
                                          "blockType": "text"}})); seq += 1
            conn.sendall(frame("chunk", transport, seq,
                               {"chunk": {"type": "text-delta", "index": 0,
                                          "text": "fixture"}})); seq += 1
            conn.sendall(frame("chunk", transport, seq,
                               {"chunk": {"type": "block-end", "index": 0,
                                          "block": {"type": "text", "text": "fixture"}}})); seq += 1
            conn.sendall(frame("chunk", transport, seq,
                               {"chunk": {"type": "usage",
                                          "usage": {"inputTokens": 11, "outputTokens": 5}}})); seq += 1
            conn.sendall(frame("finish", transport, seq, {"reason": {"kind": "stop"}}))
        elif MODE == "duplicate_finish":
            conn.sendall(frame("finish", transport, seq, {"reason": {"kind": "stop"}})); seq += 1
            conn.sendall(frame("finish", transport, seq, {"reason": {"kind": "stop"}}))
        elif MODE == "bad_frame":
            conn.sendall(b"this is not json\n")
        elif MODE == "large_frame":
            conn.sendall(frame("chunk", transport, seq,
                               {"chunk": {"type": "text-delta", "index": 0,
                                          "text": "x" * 70000}}))
        elif MODE == "error":
            conn.sendall(frame("error", transport, seq,
                               {"code": "BUDGET_DENIED", "message": "BUDGET_DENIED",
                                "retryable": False}))
        elif MODE == "slow":
            conn.sendall(frame("chunk", transport, seq,
                               {"chunk": {"type": "block-start", "index": 0,
                                          "blockType": "text"}}))
            seq += 1
            time.sleep(30)
        elif MODE == "broker_conflict":
            conn.sendall(frame("error", transport, seq,
                               {"code": "BROKER_CALL_ID_CONFLICT",
                                "message": "BROKER_CALL_ID_CONFLICT",
                                "retryable": False}))
        elif MODE == "line_flood":
            payloads = []
            for _ in range(300):
                payloads.append(frame("chunk", transport, seq,
                                      {"chunk": {"type": "text-delta",
                                                 "index": 0, "text": "x"}}))
                seq += 1
            conn.sendall(b"".join(payloads))
        elif MODE == "total_bytes":
            payloads = []
            for _ in range(20):
                payloads.append(frame("chunk", transport, seq,
                                      {"chunk": {"type": "text-delta",
                                                 "index": 0,
                                                 "text": "x" * 60000}}))
                seq += 1
            conn.sendall(b"".join(payloads))
        elif MODE == "deep_payload":
            deep = {}
            cursor = deep
            for _ in range(40):
                cursor["x"] = {}
                cursor = cursor["x"]
            conn.sendall(frame("chunk", transport, seq,
                               {"chunk": {"type": "text-delta", "index": 0,
                                          "text": "deep"},
                                "extra": deep}))
        else:
            conn.sendall(frame("error", transport, seq,
                               {"code": "INTERNAL", "message": "STUB_MODE_UNKNOWN",
                                "retryable": False}))
    finally:
        try:
            conn.close()
        finally:
            server.close()
            try:
                os.unlink(SOCKET)
            except FileNotFoundError:
                pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
