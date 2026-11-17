#!/usr/bin/env python3
"""D3-C11 same-claim negative: two Controllers, identical business request.

Two raw clients connect to two audited Controller sockets and send the exact
same payload (same sessionId/messages/tools/system/maxTokens) concurrently.
Each Controller starts at logical_step 0, so the same run_id/step/digest would
otherwise produce the same CallIdentity. The shared AttemptJournal must admit
at most one; the loser must get a precise protocol code and create no
Reservation/Claim/Attempt/Fake.
"""
from __future__ import annotations

import sys
import threading
import time

sys.path.insert(0, "/project/run/probes")
import probe_common as pc  # noqa: E402


def arg(name: str, default: str | None = None) -> str | None:
    for index, token in enumerate(sys.argv):
        if token == name and index + 1 < len(sys.argv):
            return sys.argv[index + 1]
    return default


def main() -> int:
    socket_a = arg("--socket-a", "/work/g3b/bridge.sock") or "/work/g3b/bridge.sock"
    socket_b = arg("--socket-b", "/work/g3b/bridge2.sock") or "/work/g3b/bridge2.sock"
    session = arg("--session", "g3d-d3-same-claim") or "g3d-d3-same-claim"
    payload = pc.request_payload(session=session)
    barrier = threading.Barrier(2)
    results: dict[str, dict] = {}

    def run_one(label: str, path: str) -> None:
        transport = "tr-" + ("c" if label == "a" else "d") * 32
        frame = pc.envelope_bytes(payload, transport_id=transport)
        record: dict = {"label": label, "path": path,
                        "transport_id": transport,
                        "payload_sha256": pc.payload_digest(payload)}
        sock = None
        try:
            sock = pc.connect_unix(path, timeout=3.0)
            record["connected"] = True
            barrier.wait(timeout=5.0)
            record["send_monotonic"] = time.monotonic()
            sock.sendall(frame)
            record["read"] = pc.read_frames(sock, timeout=12.0)
        except BaseException as exc:  # noqa: BLE001
            record["error"] = pc.errno_doc(exc)
        finally:
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass
            results[label] = record

    threads = [threading.Thread(target=run_one, args=("a", socket_a)),
               threading.Thread(target=run_one, args=("b", socket_b))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20.0)
    document = {"probe": "d3-same-claim", "identity": pc.identity(),
                "session": session, "payload_sha256": pc.payload_digest(payload),
                "results": results,
                "both_joined": all(not thread.is_alive() for thread in threads)}
    pc.emit(document)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
