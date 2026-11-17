#!/usr/bin/env python3
"""D3-C08: real half-close / client disconnect phases."""
from __future__ import annotations

import socket
import sys
import time

sys.path.insert(0, "/project/run/probes")
import probe_common as pc  # noqa: E402


def arg(name: str, default: str | None = None) -> str | None:
    for index, token in enumerate(sys.argv):
        if token == name and index + 1 < len(sys.argv):
            return sys.argv[index + 1]
    return default


def main() -> int:
    phase = arg("--phase", "half_close") or "half_close"
    session = arg("--session", "g3d-d3-disconnect") or "g3d-d3-disconnect"
    transport = "tr-" + "9" * 32
    frame = pc.envelope_bytes(pc.request_payload(session=session),
                              transport_id=transport)
    document = {"probe": "d3-half-close", "phase": phase,
                "transport_id": transport, "identity": pc.identity()}
    sock = None
    try:
        sock = pc.connect_unix(pc.SOCKET_PATH, timeout=3.0)
        document["connected"] = True
        sock.sendall(frame)
        document["sent_monotonic"] = time.monotonic()
        if phase == "half_close":
            sock.shutdown(socket.SHUT_WR)
            document["half_closed_write"] = True
            document["read"] = pc.read_frames(sock, timeout=8.0)
        elif phase == "disconnect_after_ack":
            document["first"] = pc.read_frames(sock, timeout=3.0, max_frames=1)
            document["closed_after_ack"] = True
            sock.close()
            sock = None
        elif phase == "disconnect_mid_stream":
            first = pc.read_frames(sock, timeout=3.0, max_frames=2)
            document["first"] = first
            document["closed_mid_stream"] = True
            sock.close()
            sock = None
        else:
            document["error"] = f"unknown phase {phase}"
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
