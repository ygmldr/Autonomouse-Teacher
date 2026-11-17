#!/usr/bin/env python3
"""D2-06: Candidate forges admission/route/call identity, bad frames and socket."""
from __future__ import annotations

import os
import socket
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import probe_common as pc  # noqa: E402

TRANSPORT = "tr-" + "6" * 32
BASE = pc.request_payload(session="g3d-d2-06")


def raw_deep_payload() -> bytes:
    nested: dict = {"leaf": True}
    for _ in range(60):
        nested = {"n": nested}
    payload = pc.request_payload(session="g3d-d2-06")
    payload["messages"] = [nested]
    return pc.envelope_bytes(payload)


def phase() -> str:
    for index, token in enumerate(sys.argv):
        if token == "--phase" and index + 1 < len(sys.argv):
            return sys.argv[index + 1]
    return "all"


def main() -> int:
    selected = phase()
    document = {"probe": "d2-06", "phase": selected,
                "identity": pc.identity(), "negatives": [],
                "socket_ops": [], "positive": None}
    negatives: list[tuple[str, str, bytes]] = [
        ("envelope_authorized", "UNKNOWN_FIELD",
         pc.envelope_bytes(BASE, extra_envelope={"authorized": True})),
        ("envelope_admission", "UNKNOWN_FIELD",
         pc.envelope_bytes(BASE, extra_envelope={"admission_id": "forged"})),
        ("payload_call_id", "UNKNOWN_FIELD",
         pc.envelope_bytes({**BASE, "call_id": "call-" + "f" * 48})),
        ("payload_reservation_id", "UNKNOWN_FIELD",
         pc.envelope_bytes({**BASE, "reservation_id": "forged-reservation"})),
        ("payload_admission_id", "UNKNOWN_FIELD",
         pc.envelope_bytes({**BASE, "admission_id": "forged-admission"})),
        ("payload_authorized", "UNKNOWN_FIELD",
         pc.envelope_bytes({**BASE, "authorized": True})),
        ("payload_approved_payload", "UNKNOWN_FIELD",
         pc.envelope_bytes({**BASE, "approved_payload": {"ok": True}})),
        ("payload_request_digest", "UNKNOWN_FIELD",
         pc.envelope_bytes({**BASE, "request_digest": "0" * 64})),
        ("payload_route_provider", "ROUTE_MISMATCH",
         pc.envelope_bytes({**BASE, "provider": "attacker-provider"})),
        ("payload_route_model", "ROUTE_MISMATCH",
         pc.envelope_bytes({**BASE, "model": "attacker-model"})),
        ("payload_tools_forged", "ADMISSION_TOOL_SCHEMA_MISMATCH",
         pc.envelope_bytes({**BASE, "tools": [{"name": "not-allowed"}]})),
        ("payload_bad_hash", "PREPARED_DIGEST_MISMATCH",
         pc.envelope_bytes(BASE, include_hash=False)[:-2] +
         b',"hash":"' + b"0" * 64 + b'"}\n'),
        ("payload_seq_out_of_order", "SEQ_OUT_OF_ORDER",
         pc.envelope_bytes(BASE, seq=1)),
        ("payload_bad_json", "REQUEST_INVALID", b"{not-json}\n"),
        ("payload_duplicate_key", "DUPLICATE_KEY",
         b'{"v":1,"v":1,"kind":"request","transport_id":"' +
         TRANSPORT.encode() + b'","seq":0,"payload":' + pc.canonical(BASE) + b'}\n'),
        ("payload_deep_nesting", "DEPTH_EXCEEDED", raw_deep_payload()),
        ("payload_oversized", "FRAME_TOO_LARGE",
         b'{"v":1,"kind":"request","pad":"' + b"x" * 300000 + b'"}\n'),
        ("payload_half_frame", "REQUEST_INVALID", b'{"v":1,'),
    ]
    if selected in {"all", "negatives"}:
        for name, expected, frame in negatives:
            record = pc.exchange(frame, timeout=4.0,
                                 shutdown_write=(name == "payload_half_frame"))
            record["id"] = name
            record["expected_code"] = expected
            document["negatives"].append(record)
    if selected in {"all", "negatives"}:
        for op_id, callable_ in (
            ("unlink_bridge", lambda: os.unlink(pc.SOCKET_PATH)),
            ("rename_bridge", lambda: os.rename(pc.SOCKET_PATH,
                                                pc.SOCKET_PATH + ".candidate")),
            ("chmod_bridge", lambda: os.chmod(pc.SOCKET_PATH, 0o666)),
            ("create_in_ipc", lambda: pc.open_flags(
                "/work/g3b/candidate-write-probe", os.O_WRONLY | os.O_CREAT,
                write=b"x")),
            ("symlink_in_ipc", lambda: os.symlink("/work/session/evil",
                                                  "/work/g3b/candidate-link")),
        ):
            document["socket_ops"].append(pc.attempt(op_id, callable_))

    def bind_existing() -> dict:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.bind(pc.SOCKET_PATH)
            return {"bound": True}
        finally:
            sock.close()

    def bind_new() -> dict:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.bind("/work/g3b/bridge-candidate.sock")
            return {"bound": True}
        finally:
            sock.close()

    def rename_over() -> dict:
        path = "/work/session/candidate-bridge.sock"
        try:
            os.unlink(path)
        except OSError:
            pass
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.bind(path)
        finally:
            sock.close()
        return os.rename(path, pc.SOCKET_PATH)

    if selected in {"all", "negatives"}:
        document["socket_ops"].append(
            pc.attempt("bind_existing_bridge", bind_existing))
        document["socket_ops"].append(pc.attempt("bind_new_in_ipc", bind_new))
        document["socket_ops"].append(pc.attempt("rename_over_bridge", rename_over))
    if selected in {"all", "positive"}:
        document["positive"] = pc.exchange(
            pc.envelope_bytes(pc.request_payload(session="g3d-d2-06-positive"),
                              transport_id=TRANSPORT), timeout=6.0)
    document["ipc_stat"] = pc.attempt(
        "stat_bridge", lambda: pc.socket_stat(pc.SOCKET_PATH))
    pc.emit(document)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
