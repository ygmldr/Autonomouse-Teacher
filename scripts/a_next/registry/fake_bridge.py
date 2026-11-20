#!/usr/bin/env python3
"""A-NEXT A-PR2 fake trusted-bridge provider (test-only, offline, no key).

The frozen candidate adapter (`spikes/g3b-trusted-bridge`, built into the
candidate Stage) connects to the fixed AF_UNIX path `/work/g3b/bridge.sock` and
speaks the newline-delimited, hash-bound bridge envelope. This module serves a
minimal synthetic provider so a real DSH turn can COMPLETE without any model,
key or network. It never speaks HTTP and never sees a Key.

It records each request envelope (including the effective `tools` face the
Candidate adapter sent) into a JSONL evidence file. That record is candidate
side, self-report, and is used only as an L1 cross-check — not as attestation.

Standalone use (for manual evidence collection):

    python3 fake_bridge.py --socket /work/g3b/bridge.sock --out req.jsonl
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

RECORD = None
LOCK = threading.Lock()
VERBOSE = False


def canonical_json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def envelope(kind: str, transport_id: str, seq: int, payload: dict) -> bytes:
    body = canonical_json(payload)
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    document = {
        "v": 1, "kind": kind, "transport_id": transport_id, "seq": seq,
        "payload": payload, "hash": digest,
    }
    return (json.dumps(document, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def record(kind: str, payload: dict) -> None:
    if RECORD is None:
        return
    with LOCK:
        with RECORD.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "schema": "a_next.fake_bridge.v1",
                "kind": kind,
                "utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                **payload,
            }, sort_keys=True) + "\n")


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def reply_text(transport_id: str) -> list[bytes]:
    """One plain text assistant turn: ack + content chunks + usage + stop finish."""
    text = "A-NEXT synthetic bridge reply (no model was called)."
    frames = [
        envelope("ack", transport_id, 1, {
            "accepted": True, "request_id": transport_id, "code": None,
        }),
        envelope("chunk", transport_id, 2, {
            "chunk": {"type": "block-start", "index": 0, "blockType": "text"},
        }),
        envelope("chunk", transport_id, 3, {
            "chunk": {"type": "text-delta", "index": 0, "text": text},
        }),
        envelope("chunk", transport_id, 4, {
            "chunk": {"type": "block-end", "index": 0,
                      "block": {"type": "text", "text": text}},
        }),
        envelope("chunk", transport_id, 5, {
            "chunk": {"type": "usage", "usage": {"inputTokens": 3, "outputTokens": 7}},
        }),
        envelope("finish", transport_id, 6, {"reason": {"kind": "stop"}}),
    ]
    return frames


def handle_connection(conn: socket.socket, request_log: Path) -> None:
    buffer = b""
    conn.settimeout(20.0)
    try:
        while b"\n" not in buffer:
            chunk = conn.recv(65536)
            if not chunk:
                return
            buffer += chunk
        line, _rest = buffer.split(b"\n", 1)
        request = json.loads(line)
        transport_id = request.get("transport_id")
        payload = request.get("payload") or {}
        record("request", {
            "transport_id": transport_id,
            "kind": request.get("kind"),
            "sessionId": payload.get("sessionId"),
            "provider": payload.get("provider"),
            "model": payload.get("model"),
            "purpose": payload.get("purpose"),
            "tool_names": [tool.get("name") for tool in payload.get("tools") or []],
            "tools": payload.get("tools"),
            "message_roles": [message.get("role") for message in payload.get("messages") or []],
        })
        if VERBOSE:
            print(f"[fake-bridge] request transport={transport_id} "
                  f"tools={[t.get('name') for t in payload.get('tools') or []]}",
                  flush=True)
        for frame in reply_text(str(transport_id)):
            conn.sendall(frame)
        time.sleep(0.02)
    except (json.JSONDecodeError, OSError):
        return
    finally:
        try:
            conn.close()
        except OSError:
            pass


def serve(socket_path: Path, request_log: Path, stop_event: threading.Event) -> threading.Thread:
    """Bind the UDS and serve until stop_event is set; returns the thread."""
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    if socket_path.exists():
        socket_path.unlink()
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(str(socket_path))
    os.chmod(socket_path, 0o600)
    server.listen(8)
    server.settimeout(0.2)

    def loop() -> None:
        # record("listening", {"socket": str(socket_path)})
        while not stop_event.is_set():
            try:
                conn, _ = server.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(target=handle_connection, args=(conn, request_log),
                             daemon=True).start()
        try:
            server.close()
        finally:
            try:
                socket_path.unlink()
            except OSError:
                pass

    thread = threading.Thread(target=loop, daemon=True)
    thread.start()
    return thread


def main() -> int:
    global RECORD, VERBOSE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--socket", default="/work/g3b/bridge.sock")
    parser.add_argument("--out", required=True)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    socket_path = Path(args.socket)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    RECORD = out
    VERBOSE = args.verbose
    record("start", {"socket": str(socket_path), "utc": utc_now()})
    stop = threading.Event()
    thread = serve(socket_path, out, stop)
    print(json.dumps({"listening": str(socket_path), "out": str(out)}), flush=True)
    try:
        while thread.is_alive():
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        thread.join(timeout=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
