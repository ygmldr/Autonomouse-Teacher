#!/usr/bin/env python3
"""D3 request-once raw UDS probe (Candidate identity, real Controller).

Sends one schema-valid synthetic request on the approved socket and records
the real frames it receives. The Host D3 runner injects trusted crashes at
specific hooks; this probe never decides the outcome.
"""
from __future__ import annotations

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
    session = arg("--session", "g3d-d3-request") or "g3d-d3-request"
    transport = arg("--transport-id", "tr-" + "4" * 32) or "tr-" + "4" * 32
    label = arg("--label", "request") or "request"
    timeout = float(arg("--timeout", "20") or 20)
    document = {"probe": "d3-request-once", "label": label,
                "session": session, "transport_id": transport,
                "identity": pc.identity()}
    payload = pc.request_payload(session=session)
    frame = pc.envelope_bytes(payload, transport_id=transport)
    sock = None
    started = time.monotonic()
    try:
        sock = pc.connect_unix(pc.SOCKET_PATH, timeout=3.0)
        document["connected"] = True
        sock.sendall(frame)
        document["sent"] = True
        document["send_monotonic"] = time.monotonic()
        document["read"] = pc.read_frames(sock, timeout=timeout)
    except BaseException as exc:  # noqa: BLE001
        document["error"] = pc.errno_doc(exc)
    finally:
        document["elapsed_seconds"] = round(time.monotonic() - started, 4)
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
    pc.emit(document)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
