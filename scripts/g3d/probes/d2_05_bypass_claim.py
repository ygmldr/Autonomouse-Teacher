#!/usr/bin/env python3
"""D2-05: Candidate bypasses the Controller to Reserve/Claim/Fake directly."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import probe_common as pc  # noqa: E402

TRANSPORT = "tr-" + "5" * 32
BROKER_SOCKETS = (
    "/work/g3b/broker.sock",
    "/work/g3b/controller.sock",
    "/work/private/controller.sock",
    "/work/state/broker.sock",
)


def phase() -> str:
    for index, token in enumerate(sys.argv):
        if token == "--phase" and index + 1 < len(sys.argv):
            return sys.argv[index + 1]
    return "all"


def main() -> int:
    selected = phase()
    document = {"probe": "d2-05", "phase": selected,
                "identity": pc.identity(), "ops": [],
                "negatives": [], "positive": None}
    if selected in {"all", "negatives"}:
        for path in BROKER_SOCKETS:
            def connect(path: str = path) -> dict:
                sock = pc.connect_unix(path, timeout=1.0)
                sock.close()
                return {"connected": True}
            document["ops"].append(pc.attempt("connect_broker:" + path, connect))
    payload = pc.request_payload(session="g3d-d2-05")
    negative_frames = [
        ("broker_kind_reserve", pc.envelope_bytes({}, kind="reserve")),
        ("broker_kind_claim", pc.envelope_bytes({}, kind="claim")),
        ("broker_kind_settle", pc.envelope_bytes({}, kind="settle")),
        ("payload_reservation_id",
         pc.envelope_bytes({**payload, "reservation_id": "forged-reservation"})),
        ("payload_claim_id",
         pc.envelope_bytes({**payload, "claim_id": "forged-claim"})),
        ("payload_authorized",
         pc.envelope_bytes({**payload, "authorized": True})),
        ("payload_dispatch_allowed",
         pc.envelope_bytes({**payload, "dispatch_allowed": True})),
        ("envelope_dispatch_allowed",
         pc.envelope_bytes(payload, extra_envelope={"dispatch_allowed": True})),
    ]
    if selected in {"all", "negatives"}:
        for name, frame in negative_frames:
            record = pc.exchange(frame, timeout=4.0)
            record["id"] = name
            document["negatives"].append(record)
        document["socket_unlink"] = pc.attempt(
            "unlink_bridge", lambda: os.unlink(pc.SOCKET_PATH))
        document["socket_stat"] = pc.attempt(
            "stat_bridge", lambda: pc.socket_stat(pc.SOCKET_PATH))
    if selected in {"all", "positive"}:
        document["positive"] = pc.exchange(
            pc.envelope_bytes(pc.request_payload(session="g3d-d2-05-positive"),
                              transport_id=TRANSPORT), timeout=6.0)
    pc.emit(document)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
