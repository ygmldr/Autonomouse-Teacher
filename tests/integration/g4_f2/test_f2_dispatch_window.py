"""G4-F2-01/02/04: per-dispatch tool surface, purpose and origin observability.

Every rejection asserts the stable IPC error code, the ledger (Reserved=0,
Claimed=0, Attempt=0, Fake counter=0) and the append-only dispatch record, so
"rejected before Reserve/Claim" is evidence, not an inference from stderr.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from support import (
    LAUNCHER_UID, ROUTE, MODEL, TOOL, admission_document, call_error,
    close_all, collect, deep_copy, envelope, journal_records, ledger,
    load_admission, request_payload, start_controller, tool_digest,
)

ZERO = {"fake": 0, "attempts": 0, "reservations": 0, "claims": 0}
TRANSPORT = "tr-" + "a" * 32


def _run(tmp_path: Path, payload: dict, **options):
    controller, broker, fake, attempts = start_controller(tmp_path, **options)
    frames = collect(controller, payload)
    return controller, broker, fake, attempts, frames


def test_approved_tool_is_dispatched_and_journaled(tmp_path: Path) -> None:
    controller, broker, fake, attempts, frames = _run(
        tmp_path, request_payload(tools=[TOOL]))
    try:
        assert call_error(frames) is None
        assert ledger(controller) == {"fake": 1, "attempts": 1,
                                      "reservations": 1, "claims": 1}
        rows = journal_records(tmp_path / "dispatch-window.jsonl")
        assert len(rows) == 1
        row = rows[0]
        assert row["schema"] == "m0.g4f.dispatch-window.v1"
        assert row["outcome"] == "completed"
        assert row["reserved"] is True and row["dispatched"] is True
        assert row["settled"] is True and row["error_code"] is None
        assert row["purpose"] == "conversation"
        assert row["origin"] == {"kind": "in_process"}
        assert row["tool_count"] == 1
        assert row["tools"] == [{
            "origin": "request.tools", "index": 0, "name": "skill_lookup",
            "schema_sha256": tool_digest(TOOL),
            "approved_sha256": tool_digest(TOOL), "approved": True}]
        assert row["call_id"].startswith("call-")
        assert isinstance(row["reservation_id"], str) and row["reservation_id"]
        assert len(row["approved_tool_set_sha256"]) == 64
    finally:
        close_all(broker, fake, attempts)


def test_purpose_null_is_the_conversation_shape(tmp_path: Path) -> None:
    controller, broker, fake, attempts, frames = _run(
        tmp_path, request_payload(tools=[], purpose=None))
    try:
        assert call_error(frames) is None
        row = journal_records(tmp_path / "dispatch-window.jsonl")[0]
        assert row["purpose"] is None and row["outcome"] == "completed"
    finally:
        close_all(broker, fake, attempts)


@pytest.mark.parametrize("purpose", ["title", "judge", "compaction"])
def test_auxiliary_purpose_rejected_before_reserve(tmp_path: Path,
                                                   purpose: str) -> None:
    controller, broker, fake, attempts, frames = _run(
        tmp_path, request_payload(tools=[TOOL], purpose=purpose))
    try:
        assert call_error(frames) == "BAD_TYPE"
        assert ledger(controller) == ZERO
        row = journal_records(tmp_path / "dispatch-window.jsonl")[0]
        assert row["purpose"] == purpose
        assert row["outcome"] == "rejected" and row["error_code"] == "BAD_TYPE"
        assert row["reserved"] is False and row["dispatched"] is False
    finally:
        close_all(broker, fake, attempts)


def test_missing_purpose_rejected_before_reserve(tmp_path: Path) -> None:
    payload = request_payload(tools=[TOOL])
    payload.pop("purpose")
    controller, broker, fake, attempts, frames = _run(tmp_path, payload)
    try:
        assert call_error(frames) in {"REQUEST_INVALID", "BAD_TYPE"}
        assert ledger(controller) == ZERO
        row = journal_records(tmp_path / "dispatch-window.jsonl")[0]
        assert row["purpose"] == "<missing>" and row["outcome"] == "rejected"
    finally:
        close_all(broker, fake, attempts)


def test_unapproved_tool_is_rejected_and_journaled(tmp_path: Path) -> None:
    bash = {"name": "bash", "description": "run shell",
            "parameters": {"type": "object",
                           "properties": {"command": {"type": "string"}}}}
    controller, broker, fake, attempts, frames = _run(
        tmp_path, request_payload(tools=[bash]))
    try:
        assert call_error(frames) == "ADMISSION_TOOL_SCHEMA_MISMATCH"
        assert ledger(controller) == ZERO
        row = journal_records(tmp_path / "dispatch-window.jsonl")[0]
        assert row["outcome"] == "rejected"
        assert row["error_code"] == "ADMISSION_TOOL_SCHEMA_MISMATCH"
        assert row["tools"][0]["name"] == "bash"
        assert row["tools"][0]["approved"] is False
        assert row["tools"][0]["approved_sha256"] is None
    finally:
        close_all(broker, fake, attempts)


def test_nested_schema_change_is_rejected(tmp_path: Path) -> None:
    modified = deep_copy(TOOL)
    modified["parameters"]["properties"]["skill_id"]["maxLength"] = 64
    controller, broker, fake, attempts, frames = _run(
        tmp_path, request_payload(tools=[modified]))
    try:
        assert call_error(frames) == "ADMISSION_TOOL_SCHEMA_MISMATCH"
        assert ledger(controller) == ZERO
        row = journal_records(tmp_path / "dispatch-window.jsonl")[0]
        assert row["tools"][0]["approved"] is False
        assert row["tools"][0]["schema_sha256"] != row["tools"][0]["approved_sha256"]
    finally:
        close_all(broker, fake, attempts)


def test_extra_tool_alongside_approved_is_rejected(tmp_path: Path) -> None:
    extra = {"name": "fs_read", "description": "read files",
             "parameters": {"type": "object", "properties": {}}}
    controller, broker, fake, attempts, frames = _run(
        tmp_path, request_payload(tools=[TOOL, extra]))
    try:
        assert call_error(frames) == "ADMISSION_TOOL_SCHEMA_MISMATCH"
        assert ledger(controller) == ZERO
        row = journal_records(tmp_path / "dispatch-window.jsonl")[0]
        assert [item["approved"] for item in row["tools"]] == [True, False]
        assert row["tool_count"] == 2
    finally:
        close_all(broker, fake, attempts)


def test_duplicate_tool_name_is_rejected(tmp_path: Path) -> None:
    controller, broker, fake, attempts, frames = _run(
        tmp_path, request_payload(tools=[TOOL, deep_copy(TOOL)]))
    try:
        assert call_error(frames) == "ADMISSION_TOOL_SCHEMA_MISMATCH"
        assert ledger(controller) == ZERO
        row = journal_records(tmp_path / "dispatch-window.jsonl")[0]
        assert row["tool_count"] == 2 and row["outcome"] == "rejected"
    finally:
        close_all(broker, fake, attempts)


def test_non_string_tool_name_is_rejected(tmp_path: Path) -> None:
    malformed = {"name": 7, "description": "numeric name", "parameters": {}}
    controller, broker, fake, attempts, frames = _run(
        tmp_path, request_payload(tools=[malformed]))
    try:
        assert call_error(frames) == "REQUEST_INVALID"
        assert ledger(controller) == ZERO
        row = journal_records(tmp_path / "dispatch-window.jsonl")[0]
        assert row["tools"][0]["name"] is None
        assert row["tools"][0]["approved"] is False
    finally:
        close_all(broker, fake, attempts)


@pytest.mark.parametrize("kind,name", [
    ("tool-call", "bash"),
    ("tool-addition", "bash"),
    ("tool-removal", "bash"),
])
def test_message_tool_reference_to_unapproved_tool_is_rejected(
        tmp_path: Path, kind: str, name: str) -> None:
    block = ({"type": kind, "toolName": name} if kind != "tool-call"
             else {"type": "tool-call", "id": "call-x", "name": name,
                   "arguments": "{}"})
    messages = [{"role": "assistant", "content": [block]}]
    controller, broker, fake, attempts, frames = _run(
        tmp_path, request_payload(tools=[TOOL], messages=messages))
    try:
        assert call_error(frames) == "ADMISSION_TOOL_SCHEMA_MISMATCH"
        assert ledger(controller) == ZERO
        row = journal_records(tmp_path / "dispatch-window.jsonl")[0]
        assert row["message_tool_ref_count"] == 1
        assert row["message_tool_refs"][0]["name"] == name
        assert row["message_tool_refs"][0]["approved"] is False
    finally:
        close_all(broker, fake, attempts)


def test_message_tool_call_to_approved_tool_is_accepted(tmp_path: Path) -> None:
    messages = [
        {"role": "assistant", "content": [
            {"type": "tool-call", "id": "call-1", "name": "skill_lookup",
             "arguments": json.dumps({"skill_id": "binary_search"})}]},
        {"role": "tool", "content": [{"type": "text", "text": "ok"}]},
    ]
    controller, broker, fake, attempts, frames = _run(
        tmp_path, request_payload(tools=[TOOL], messages=messages))
    try:
        assert call_error(frames) is None
        assert ledger(controller)["reservations"] == 1
        row = journal_records(tmp_path / "dispatch-window.jsonl")[0]
        assert row["message_tool_refs"][0]["approved"] is True
        assert row["outcome"] == "completed"
    finally:
        close_all(broker, fake, attempts)


def test_unknown_origin_rejected_before_reserve(tmp_path: Path) -> None:
    controller, broker, fake, attempts = start_controller(
        tmp_path, require_origin=True)
    try:
        controller.observe_peer(TRANSPORT, 0, 0, 1234)
        frames = collect(controller, request_payload(tools=[TOOL]),
                         transport_id=TRANSPORT)
        assert call_error(frames) == "ADMISSION_LAUNCHER_MISMATCH"
        assert ledger(controller) == ZERO
        row = journal_records(tmp_path / "dispatch-window.jsonl")[0]
        assert row["origin"] == {"kind": "unix_peer", "uid": 0, "gid": 0,
                                 "pid": 1234}
        assert row["outcome"] == "rejected"
    finally:
        close_all(broker, fake, attempts)


def test_launcher_origin_is_accepted_and_journaled(tmp_path: Path) -> None:
    controller, broker, fake, attempts = start_controller(
        tmp_path, require_origin=True)
    try:
        controller.observe_peer(TRANSPORT, LAUNCHER_UID, 2000, 4242)
        frames = collect(controller, request_payload(tools=[TOOL]),
                         transport_id=TRANSPORT)
        assert call_error(frames) is None
        assert ledger(controller)["reservations"] == 1
        row = journal_records(tmp_path / "dispatch-window.jsonl")[0]
        assert row["origin"] == {"kind": "unix_peer", "uid": LAUNCHER_UID,
                                 "gid": 2000, "pid": 4242}
        assert row["outcome"] == "completed"
    finally:
        close_all(broker, fake, attempts)


def test_unknown_origin_after_a_known_peer_is_fail_closed(tmp_path: Path) -> None:
    controller, broker, fake, attempts = start_controller(
        tmp_path, require_origin=True)
    try:
        controller.observe_peer("tr-" + "b" * 32, LAUNCHER_UID, 2000, 1)
        frames = collect(controller, request_payload(tools=[TOOL]),
                         transport_id=TRANSPORT)
        assert call_error(frames) == "ADMISSION_LAUNCHER_MISMATCH"
        assert ledger(controller) == ZERO
    finally:
        close_all(broker, fake, attempts)


def test_duplicate_dispatch_is_not_sent_twice(tmp_path: Path) -> None:
    payload = request_payload(tools=[TOOL])
    controller, broker, fake, attempts = start_controller(tmp_path)
    try:
        first = collect(controller, payload)
        assert call_error(first) is None
        second = collect(controller, payload)
        assert call_error(second) == "ATTEMPT_ALREADY_STARTED"
        assert ledger(controller) == {"fake": 1, "attempts": 1,
                                      "reservations": 1, "claims": 1}
        rows = journal_records(tmp_path / "dispatch-window.jsonl")
        assert [row["outcome"] for row in rows] == ["completed", "rejected"]
        assert rows[1]["error_code"] == "ATTEMPT_ALREADY_STARTED"
    finally:
        close_all(broker, fake, attempts)


def test_auxiliary_replay_never_reserves_or_sends(tmp_path: Path) -> None:
    payload = request_payload(tools=[TOOL], purpose="title")
    controller, broker, fake, attempts = start_controller(tmp_path)
    try:
        for _ in range(2):
            frames = collect(controller, payload)
            assert call_error(frames) == "BAD_TYPE"
        assert ledger(controller) == ZERO
        rows = journal_records(tmp_path / "dispatch-window.jsonl")
        assert len(rows) == 2
        assert all(row["outcome"] == "rejected" for row in rows)
        assert all(row["reserved"] is False for row in rows)
    finally:
        close_all(broker, fake, attempts)


def test_journal_write_failure_never_changes_the_decision(tmp_path: Path) -> None:
    directory_as_journal = tmp_path / "journal-is-a-directory"
    directory_as_journal.mkdir()
    controller, broker, fake, attempts, frames = _run(
        tmp_path, request_payload(tools=[TOOL]),
        journal_path=directory_as_journal)
    try:
        assert call_error(frames) is None
        assert ledger(controller)["reservations"] == 1
        assert controller.dispatch_audit.errors >= 1
        assert controller.dispatch_audit.written == 0
    finally:
        close_all(broker, fake, attempts)


def test_admission_duplicate_tool_names_are_rejected(tmp_path: Path) -> None:
    document = admission_document()
    document["tool_schemas"].append(dict(document["tool_schemas"][0]))
    path = tmp_path / "admission.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    from autoteacher_m0.bridge.admission import AdmissionError
    with pytest.raises(AdmissionError) as excinfo:
        load_admission(path, expected_uid=LAUNCHER_UID)
    assert excinfo.value.code == "ADMISSION_INVALID"


def test_admission_non_hex_tool_digest_is_rejected(tmp_path: Path) -> None:
    document = admission_document()
    document["tool_schemas"][0]["sha256"] = "Z" * 64
    path = tmp_path / "admission.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    from autoteacher_m0.bridge.admission import AdmissionError
    with pytest.raises(AdmissionError) as excinfo:
        load_admission(path, expected_uid=LAUNCHER_UID)
    assert excinfo.value.code == "ADMISSION_INVALID"


def test_envelope_helper_matches_route_and_model() -> None:
    env = envelope(request_payload(tools=[TOOL]), transport_id=TRANSPORT)
    assert env.payload["provider"] == ROUTE
    assert env.payload["model"] == MODEL
    assert env.seq == 2
