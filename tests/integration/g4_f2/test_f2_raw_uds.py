"""G4-F2-03: raw UDS negative/positive matrix through the real IPC server.

The Server, Controller, Broker and Fake are the real trusted components; the
client is an AF_UNIX socket in this test process (host root). This is the
controller-boundary equivalent of the container raw-UDS run and it asserts the
same invariants: stable code, 0 Reserved/Claimed/Attempt, Fake 0, and one
journal record per observed dispatch with purpose/origin/tool identity.
"""
from __future__ import annotations

import json
import socket
import threading
from pathlib import Path

import pytest

from support import (
    LAUNCHER_UID, TOOL, close_all, deep_copy, journal_records,
    ledger, request_payload, start_controller, tool_digest,
)
from autoteacher_m0.bridge.ipc_server import BridgeServer
from autoteacher_m0.bridge.protocol import Envelope, encode_envelope


class UdsServer:
    def __init__(self, controller, path: Path, *,
                 expected_peer_uid: int | None = None) -> None:
        self.ready = threading.Event()
        self.server = BridgeServer(
            controller, str(path), expected_peer_uid=expected_peer_uid,
            on_ready=self.ready.set)
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       name="g4f2-uds-server", daemon=True)

    def __enter__(self) -> "UdsServer":
        self.thread.start()
        assert self.ready.wait(10.0), "bridge server did not become ready"
        return self

    def __exit__(self, *_exc) -> None:
        self.server.shutdown()
        self.thread.join(timeout=10.0)


def _raw_frame(payload: dict, *, transport_id: str) -> bytes:
    """Encode without the client-side payload validator.

    A real (possibly hostile) Candidate is not obliged to run our validator; the
    server must decide. This lets the test send an auxiliary ``purpose`` that the
    Controller-side validator would otherwise reject before the bytes exist.
    """
    import hashlib
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False, allow_nan=False).encode("utf-8")
    document = {"v": 1, "kind": "request", "transport_id": transport_id,
                "seq": 0, "payload": payload,
                "hash": hashlib.sha256(canonical).hexdigest()}
    return json.dumps(document, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8") + b"\n"


def exchange(path: Path, payload: dict, *, transport_id: str,
             validate_locally: bool = True) -> list[dict]:
    if validate_locally:
        envelope = Envelope(v=1, kind="request", transport_id=transport_id,
                            seq=0, payload=payload, hash=None)
        line = encode_envelope(envelope) + b"\n"
    else:
        line = _raw_frame(payload, transport_id=transport_id)
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(20.0)
    try:
        sock.connect(str(path))
        sock.sendall(line)
        buffer = b""
        frames: list[dict] = []
        while True:
            data = sock.recv(65_536)
            if not data:
                return frames
            buffer += data
            while b"\n" in buffer:
                raw, buffer = buffer.split(b"\n", 1)
                frame = json.loads(raw)
                frames.append(frame)
                if frame.get("kind") in {"error", "finish"}:
                    return frames
    finally:
        sock.close()


def _error_code(frames: list[dict]) -> str | None:
    for frame in frames:
        if frame.get("kind") == "error":
            return frame.get("payload", {}).get("code")
        if frame.get("kind") == "finish":
            reason = frame.get("payload", {}).get("reason")
            if isinstance(reason, dict) and reason.get("kind") == "error":
                failure = reason.get("failure")
                return str((failure or {}).get("code") or "TERMINAL_ERROR")
    return None


def test_raw_uds_tool_surface_and_auxiliary_purpose_matrix(tmp_path: Path) -> None:
    # This host-level run executes as the test user; the Admission launcher UID
    # is the same real peer UID the kernel reports (in the container matrix this
    # is 65534). The origin contract itself is exercised below with a mismatch.
    controller, broker, fake, attempts = start_controller(
        tmp_path, launcher_uid=0, expected_uid=0, require_origin=True)
    modified = deep_copy(TOOL)
    modified["parameters"]["properties"]["skill_id"]["maxLength"] = 64
    extra = {"name": "fs_read", "description": "read files",
             "parameters": {"type": "object", "properties": {}}}
    bash = {"name": "bash", "description": "run shell",
            "parameters": {"type": "object",
                           "properties": {"command": {"type": "string"}}}}
    # ``purpose`` is part of the frozen request schema, so the IPC parser
    # rejects an auxiliary purpose before the Controller generator exists. This
    # is stronger than (and earlier than) the Controller's own conversation-only
    # re-check; the raw matrix asserts the rejection and that no dispatch journal
    # record is produced. In-process callers are covered separately, where the
    # Controller must reject the same payload itself.
    cases = [
        ("unapproved_tool", request_payload(tools=[bash]),
         "ADMISSION_TOOL_SCHEMA_MISMATCH", True),
        ("modified_schema", request_payload(tools=[modified]),
         "ADMISSION_TOOL_SCHEMA_MISMATCH", True),
        ("extra_tool", request_payload(tools=[TOOL, extra]),
         "ADMISSION_TOOL_SCHEMA_MISMATCH", True),
        ("message_tool_call", request_payload(tools=[TOOL], messages=[
            {"role": "assistant", "content": [
                {"type": "tool-call", "id": "call-x", "name": "bash",
                 "arguments": "{}"}]}]), "ADMISSION_TOOL_SCHEMA_MISMATCH", True),
        ("auxiliary_title", request_payload(tools=[TOOL], purpose="title"),
         "BAD_TYPE", False),
        ("auxiliary_title_replay", request_payload(tools=[TOOL], purpose="title"),
         "BAD_TYPE", False),
        ("approved_tool", request_payload(tools=[TOOL]), None, True),
    ]
    results = []
    journal = tmp_path / "dispatch-window.jsonl"
    with UdsServer(controller, tmp_path / "bridge.sock", expected_peer_uid=0):
        for index, (label, payload, expected, reaches_controller) in enumerate(cases):
            before = len(journal_records(journal))
            frames = exchange(tmp_path / "bridge.sock", payload,
                              transport_id="tr-" + f"{index:032x}",
                              validate_locally=reaches_controller)
            actual = _error_code(frames)
            results.append({"label": label, "actual": actual,
                            "expected": expected,
                            "reaches_controller": reaches_controller})
            assert actual == expected
            after = len(journal_records(journal))
            assert after - before == (1 if reaches_controller else 0), label
    try:
        assert ledger(controller) == {"fake": 1, "attempts": 1,
                                      "reservations": 1, "claims": 1}
        rows = journal_records(journal)
        assert len(rows) == 5
        assert [row["outcome"] for row in rows] == [
            "rejected", "rejected", "rejected", "rejected", "completed"]
        assert rows[-1]["tools"][0]["schema_sha256"] == tool_digest(TOOL)
        assert all(row["purpose"] == "conversation" for row in rows)
        for row in rows:
            assert row["origin"] == {"kind": "unix_peer", "uid": 0,
                                     "gid": 0, "pid": row["origin"]["pid"]}
        assert sum(1 for row in rows if row["reserved"]) == 1
        assert sum(1 for row in rows if row["dispatched"]) == 1
    finally:
        close_all(broker, fake, attempts)


def test_raw_uds_foreign_origin_is_rejected_before_reserve(tmp_path: Path) -> None:
    controller, broker, fake, attempts = start_controller(
        tmp_path, require_origin=True)
    try:
        with UdsServer(controller, tmp_path / "bridge.sock"):
            frames = exchange(tmp_path / "bridge.sock",
                              request_payload(tools=[TOOL]),
                              transport_id="tr-" + "c" * 32)
        assert _error_code(frames) == "ADMISSION_LAUNCHER_MISMATCH"
        assert ledger(controller) == {"fake": 0, "attempts": 0,
                                      "reservations": 0, "claims": 0}
        row = journal_records(tmp_path / "dispatch-window.jsonl")[0]
        assert row["origin"]["kind"] == "unix_peer"
        assert row["origin"]["uid"] == 0
        assert row["outcome"] == "rejected"
        assert row["error_code"] == "ADMISSION_LAUNCHER_MISMATCH"
    finally:
        close_all(broker, fake, attempts)


def test_raw_uds_malformed_tool_reference_is_rejected(tmp_path: Path) -> None:
    controller, broker, fake, attempts = start_controller(
        tmp_path, launcher_uid=0, expected_uid=0, require_origin=True)
    try:
        with UdsServer(controller, tmp_path / "bridge.sock", expected_peer_uid=0):
            frames = exchange(
                tmp_path / "bridge.sock",
                request_payload(tools=[TOOL], messages=[
                    {"role": "assistant", "content": [
                        {"type": "tool-addition", "toolName": 7}]}]),
                transport_id="tr-" + "d" * 32)
        assert _error_code(frames) == "REQUEST_INVALID"
        assert ledger(controller)["reservations"] == 0
        row = journal_records(tmp_path / "dispatch-window.jsonl")[0]
        assert row["message_tool_refs"][0]["name"] is None
        assert row["message_tool_refs"][0]["approved"] is False
    finally:
        close_all(broker, fake, attempts)


@pytest.mark.parametrize("expected", [LAUNCHER_UID, None])
def test_uds_server_requires_a_ready_socket(tmp_path: Path, expected) -> None:
    controller, broker, fake, attempts = start_controller(tmp_path)
    try:
        with UdsServer(controller, tmp_path / "bridge.sock",
                       expected_peer_uid=expected):
            assert (tmp_path / "bridge.sock").is_socket()
    finally:
        close_all(broker, fake, attempts)
