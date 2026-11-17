#!/usr/bin/env python3
"""D3-C07: real cancel envelopes over the approved UDS.

Phases:
  before_send  - request, then cancel while the Broker is SIGSTOPped by the
                 Host. This deterministically lands before Claim/Attempt/Fake.
  after_send   - slow_usage Fake receipt is durable, then cancel before the
                 stream finishes; accounting must stay conservative (fee > 0).
  two_streams  - two connections; cancel one, the other must complete.
"""
from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, "/project/run/probes")
import probe_common as pc  # noqa: E402

REASON = "aborted"


def arg(name: str, default: str | None = None) -> str | None:
    for index, token in enumerate(sys.argv):
        if token == name and index + 1 < len(sys.argv):
            return sys.argv[index + 1]
    return default


def cancel_frame(transport: str) -> bytes:
    payload = {"request_id": transport, "reason": REASON}
    return pc.envelope_bytes(payload, kind="cancel", transport_id=transport,
                             seq=1)


def open_transport(session: str, suffix: str) -> tuple[str, bytes, "object"]:
    transport = "tr-" + suffix * 32
    payload = pc.request_payload(session=session)
    frame = pc.envelope_bytes(payload, transport_id=transport)
    return transport, frame, payload


def phase_before_send(session: str, sync_dir: str | None) -> dict:
    transport = "tr-" + "5" * 32
    frame = pc.envelope_bytes(pc.request_payload(session=session),
                              transport_id=transport)
    document: dict = {"phase": "before_send", "transport_id": transport}
    sock = pc.connect_unix(pc.SOCKET_PATH, timeout=3.0)
    try:
        sock.sendall(frame)
        document["request_sent_monotonic"] = time.monotonic()
        time.sleep(0.40)
        sock.sendall(cancel_frame(transport))
        document["cancel_sent_monotonic"] = time.monotonic()
        if sync_dir:
            marker = os.path.join(sync_dir, "d3-cancel-before-send.marker")
            with open(marker, "w", encoding="utf-8") as handle:
                json.dump({"utc_probe": pc.utc(),
                           "cancel_monotonic": document["cancel_sent_monotonic"]},
                          handle, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
        document["read"] = pc.read_frames(sock, timeout=8.0)
    finally:
        sock.close()
    return document


def phase_after_send(session: str) -> dict:
    transport = "tr-" + "6" * 32
    frame = pc.envelope_bytes(pc.request_payload(session=session),
                              transport_id=transport)
    document: dict = {"phase": "after_send", "transport_id": transport}
    sock = pc.connect_unix(pc.SOCKET_PATH, timeout=3.0)
    try:
        sock.sendall(frame)
        document["ack"] = pc.read_frames(sock, timeout=3.0, max_frames=1)
        # slow_usage writes its durable receipt first and sleeps 1.2s before
        # the first frame; this cancel intentionally lands after the receipt.
        time.sleep(0.45)
        document["cancel_sent_monotonic"] = time.monotonic()
        sock.sendall(cancel_frame(transport))
        document["read"] = pc.read_frames(sock, timeout=8.0)
    finally:
        sock.close()
    return document


def phase_two_streams(session: str) -> dict:
    transport_a = "tr-" + "7" * 32
    transport_b = "tr-" + "8" * 32
    frame_a = pc.envelope_bytes(pc.request_payload(session=session + "-a"),
                                transport_id=transport_a)
    frame_b = pc.envelope_bytes(pc.request_payload(session=session + "-b"),
                                transport_id=transport_b)
    result: dict = {"phase": "two_streams",
                    "transport_a": transport_a, "transport_b": transport_b}
    sock_a = pc.connect_unix(pc.SOCKET_PATH, timeout=3.0)
    try:
        sock_a.sendall(frame_a)
        result["ack_a"] = pc.read_frames(sock_a, timeout=3.0, max_frames=1)
        # Open the second stream while the first one is still active.
        sock_b = pc.connect_unix(pc.SOCKET_PATH, timeout=3.0)
        try:
            sock_b.sendall(frame_b)
            time.sleep(0.35)
            sock_a.sendall(cancel_frame(transport_a))
            result["cancel_a_sent_monotonic"] = time.monotonic()
            result["read_a"] = pc.read_frames(sock_a, timeout=10.0)
            result["read_b"] = pc.read_frames(sock_b, timeout=15.0)
        finally:
            sock_b.close()
    finally:
        sock_a.close()
    return result


def main() -> int:
    phase = arg("--phase", "before_send") or "before_send"
    session = arg("--session", "g3d-d3-cancel") or "g3d-d3-cancel"
    sync_dir = arg("--sync-dir")
    document = {"probe": "d3-cancel", "phase": phase,
                "identity": pc.identity()}
    try:
        if phase == "before_send":
            document.update(phase_before_send(session, sync_dir))
        elif phase == "after_send":
            document.update(phase_after_send(session))
        elif phase == "two_streams":
            document.update(phase_two_streams(session))
        else:
            document["error"] = f"unknown phase {phase}"
    except BaseException as exc:  # noqa: BLE001
        document["error"] = pc.errno_doc(exc)
    pc.emit(document)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
