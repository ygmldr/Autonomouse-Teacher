#!/usr/bin/env python3
"""D2-10: Candidate SIGKILL/self-terminate, half-close, disconnect and reconnect."""
from __future__ import annotations

import json
import os
import signal
import socket
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import probe_common as pc  # noqa: E402

TRANSPORT = "tr-" + "1" * 32


def arg(name: str, default: str | None = None) -> str | None:
    for index, token in enumerate(sys.argv):
        if token == name and index + 1 < len(sys.argv):
            return sys.argv[index + 1]
    return default


def session_payload() -> dict:
    return pc.request_payload(session=arg("--session", "g3d-d2-10") or "g3d-d2-10")


def main() -> int:
    window = arg("--window", "a") or "a"
    transport = arg("--transport-id", TRANSPORT) or TRANSPORT
    document = {"probe": "d2-10", "window": window,
                "identity": pc.identity(), "ops": {},
                "transport_id": transport}
    sock = None
    try:
        sock = pc.connect_unix(pc.SOCKET_PATH, timeout=3.0)
        document["connected"] = True
        frame = pc.envelope_bytes(session_payload(), transport_id=transport)
        if window == "before_send":
            document["ops"]["note"] = "connected then SIGKILL before any byte"
            print("D2_10 BEFORE_SEND connected", flush=True)
            os.kill(os.getpid(), signal.SIGKILL)
        elif window == "half_close":
            sock.sendall(frame[:11])
            document["ops"]["sent_bytes"] = 11
            sock.shutdown(socket.SHUT_WR)
            document["ops"]["half_closed_write"] = True
            document["ops"]["read"] = pc.read_frames(sock, timeout=4.0)
        elif window == "after_send":
            sock.sendall(frame)
            document["ops"]["sent"] = True
            print("D2_10 AFTER_SEND sent_then_SIGKILL", flush=True)
            os.kill(os.getpid(), signal.SIGKILL)
        elif window == "after_ack":
            sock.sendall(frame)
            document["ops"]["sent"] = True
            first = None
            deadline = time.monotonic() + 6.0
            buffer = b""
            while time.monotonic() < deadline and first is None:
                sock.settimeout(max(0.1, deadline - time.monotonic()))
                try:
                    chunk = sock.recv(65536)
                except socket.timeout:
                    break
                if not chunk:
                    break
                buffer += chunk
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    try:
                        frame_doc = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    first = frame_doc
                    break
            document["ops"]["first_frame"] = first
            print("D2_10 AFTER_ACK then SIGKILL", flush=True)
            os.kill(os.getpid(), signal.SIGKILL)
        elif window == "after_chunk":
            sock.sendall(frame)
            document["ops"]["sent"] = True
            first = None
            deadline = time.monotonic() + 6.0
            buffer = b""
            while time.monotonic() < deadline and first is None:
                sock.settimeout(max(0.1, deadline - time.monotonic()))
                try:
                    chunk = sock.recv(65536)
                except socket.timeout:
                    break
                if not chunk:
                    break
                buffer += chunk
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    try:
                        frame_doc = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if frame_doc.get("kind") == "chunk":
                        first = frame_doc
                        break
            document["ops"]["first_chunk"] = first
            document["ops"]["closed_without_finish"] = True
        elif window == "reconnect":
            sock.sendall(frame)
            document["ops"]["sent"] = True
            document["ops"]["read"] = pc.read_frames(sock, timeout=6.0)
        elif window == "trusted_crash":
            sock.sendall(frame)
            document["ops"]["sent"] = True
            document["ops"]["read"] = pc.read_frames(sock, timeout=12.0)
            document["ops"]["eof_without_finish"] = (
                document["ops"]["read"].get("terminal") not in {"finish", "error"})
            sock.close()
            sock = None
            time.sleep(0.5)
            reconnect_record = pc.attempt(
                "reconnect_after_trusted_crash",
                lambda: (lambda s: (s.close(), {"connected": True}))(
                    pc.connect_unix(pc.SOCKET_PATH, timeout=2.0)))
            document["ops"]["reconnect"] = reconnect_record
            if reconnect_record.get("ok"):
                document["ops"]["reconnect_send"] = pc.exchange(
                    frame, timeout=4.0)
        else:
            document["ops"]["error"] = f"unknown window {window}"
    except BaseException as exc:  # noqa: BLE001
        document["error"] = pc.errno_doc(exc)
    finally:
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
    pc.emit(document)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
