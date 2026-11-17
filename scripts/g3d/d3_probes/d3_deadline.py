#!/usr/bin/env python3
"""D3-C09: one request with a bounded real read; records elapsed + terminal."""
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
    session = arg("--session", "g3d-d3-deadline") or "g3d-d3-deadline"
    timeout = float(arg("--timeout", "20") or 20)
    transport = "tr-" + "b" * 32
    frame = pc.envelope_bytes(pc.request_payload(session=session),
                              transport_id=transport)
    document = {"probe": "d3-deadline", "transport_id": transport,
                "identity": pc.identity()}
    sock = None
    started = time.monotonic()
    try:
        sock = pc.connect_unix(pc.SOCKET_PATH, timeout=3.0)
        sock.sendall(frame)
        document["sent_monotonic"] = time.monotonic()
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
