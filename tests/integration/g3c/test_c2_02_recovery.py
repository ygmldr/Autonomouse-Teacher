"""G3-C C2-02: restart recovery uses the durable trusted Receipt/Observation and
the Broker's authoritative reservation status; never resends or double-charges.
"""
from __future__ import annotations
import json
import sqlite3
from pathlib import Path

import pytest

from test_c1_03_admission import (
    make_harness, run_crash, write_admission, write_broker_config,
)


def _prepare_root(root: Path, *, scenario: str = "ok_usage") -> None:
    root.mkdir(parents=True, exist_ok=True)
    write_admission(root, scenario=scenario)
    write_broker_config(root)


def _crash(root: Path, hook: str) -> None:
    proc = run_crash(root, hook)
    assert proc.returncode == 97, (proc.returncode, proc.stdout, proc.stderr)


def _recover(root: Path):
    harness = make_harness(root, register=False, write_configs=False)
    harness.controller.reconcile_on_startup(str(root / "receipts"))
    return harness


def _db_rows(root: Path, sql: str, params: tuple = ()) -> list[dict]:
    conn = sqlite3.connect(root / "attempts.sqlite3")
    conn.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def _attempt_rows(root: Path) -> list[dict]:
    return _db_rows(root, "SELECT * FROM g3b_attempts ORDER BY created_utc")


def _intent_rows(root: Path) -> list[dict]:
    return _db_rows(root, "SELECT * FROM g3b_send_intents ORDER BY created_utc")


def _broker_message_ids(root: Path) -> list[str]:
    conn = sqlite3.connect(root / "broker.sqlite3")
    try:
        return [row[0] for row in conn.execute(
            "SELECT message_id FROM budget_broker_messages ORDER BY message_id")]
    finally:
        conn.close()


def _receipt_files(root: Path) -> list[Path]:
    return sorted((root / "receipts").glob("rcpt-*.json"))


def test_c2_02a_authoritative_receipt_settles_exactly_once(tmp_path: Path) -> None:
    _prepare_root(tmp_path)
    _crash(tmp_path, "after_response_before_settlement")
    rows = _attempt_rows(tmp_path)
    assert [row["state"] for row in rows] == ["RESPONSE_OBSERVED"]
    document = json.loads(rows[0]["receipt_json"])
    assert document["schema"] == "m0.g3c.observation.v1"
    assert document["completeness"] == "AUTHORITATIVE"
    assert document["receipt"]["nonce"]
    assert document["usage_digest"]
    harness = _recover(tmp_path)
    try:
        rows = harness.attempts_rows()
        assert [row["state"] for row in rows] == ["SETTLED"]
        status = harness.status(rows[0]["reservation_id"])
        assert status["status"] == "OK"
        assert status["estimated"] is False
        assert status["input_used"] == 13 and status["output_used"] == 5
        assert harness.receipt_count() == 1
        message_ids = _broker_message_ids(tmp_path)
        settle_ids = [mid for mid in message_ids if "-settle-" in mid]
        assert len(settle_ids) == 1
        cost = status["cost"]
        frames = harness.controller.reconcile_on_startup(str(tmp_path / "receipts"))
        assert [row["state"] for row in frames] == ["SETTLED"]
        assert harness.receipt_count() == 1
        assert _broker_message_ids(tmp_path) == message_ids
        assert harness.status(rows[0]["reservation_id"])["cost"] == cost
    finally:
        harness.close()


def test_c2_02b_broker_settled_before_journal_mark_archives_settled(
        tmp_path: Path) -> None:
    _prepare_root(tmp_path)
    _crash(tmp_path, "after_broker_settle_before_journal_mark")
    rows = _attempt_rows(tmp_path)
    assert [row["state"] for row in rows] == ["RESPONSE_OBSERVED"]
    # Broker already committed the settlement before the crash.
    harness = make_harness(tmp_path, register=False, write_configs=False)
    try:
        status = harness.status(rows[0]["reservation_id"])
        assert status["status"] == "OK"
        before_messages = _broker_message_ids(tmp_path)
        before_cost = status["cost"]
        harness.controller.reconcile_on_startup(str(tmp_path / "receipts"))
        rows = harness.attempts_rows()
        assert [row["state"] for row in rows] == ["SETTLED"]
        assert harness.receipt_count() == 1
        assert _broker_message_ids(tmp_path) == before_messages
        after = harness.status(rows[0]["reservation_id"])
        assert after["status"] == "OK" and after["cost"] == before_cost
    finally:
        harness.close()


def test_c2_02c_missing_receipt_file_stays_pending_uncertain(tmp_path: Path) -> None:
    _prepare_root(tmp_path)
    _crash(tmp_path, "after_response_before_settlement")
    receipt_files = _receipt_files(tmp_path)
    assert len(receipt_files) == 1
    receipt_files[0].unlink()
    harness = _recover(tmp_path)
    try:
        rows = harness.attempts_rows()
        assert [row["state"] for row in rows] == ["SETTLEMENT_UNCERTAIN"]
        assert "RECEIPT_FILE_MISSING" in (rows[0]["reason"] or "")
        status = harness.status(rows[0]["reservation_id"])
        assert status["status"] == "PENDING"
        assert harness.receipt_count() == 1
        message_ids = _broker_message_ids(tmp_path)
        harness.controller.reconcile_on_startup(str(tmp_path / "receipts"))
        assert harness.attempts_rows()[0]["state"] == "SETTLEMENT_UNCERTAIN"
        assert _broker_message_ids(tmp_path) == message_ids
    finally:
        harness.close()


@pytest.mark.parametrize("tamper", ["journal_usage", "journal_nonce", "journal_call",
                                    "file_nonce", "file_usage"])
def test_c2_02d_tampered_or_cross_call_receipt_is_never_settled(
        tmp_path: Path, tamper: str) -> None:
    _prepare_root(tmp_path)
    _crash(tmp_path, "after_response_before_settlement")
    conn = sqlite3.connect(tmp_path / "attempts.sqlite3")
    row = conn.execute("SELECT attempt_id, receipt_json FROM g3b_attempts").fetchone()
    document = json.loads(row[1])
    if tamper == "journal_usage":
        document["usage"]["outputTokens"] = 999
        conn.execute("UPDATE g3b_attempts SET receipt_json=? WHERE attempt_id=?",
                     (json.dumps(document, sort_keys=True), row[0]))
    elif tamper == "journal_nonce":
        document["receipt"]["nonce"] = "f" * 32
        conn.execute("UPDATE g3b_attempts SET receipt_json=? WHERE attempt_id=?",
                     (json.dumps(document, sort_keys=True), row[0]))
    elif tamper == "journal_call":
        document["call_id"] = "call-" + "0" * 48
        conn.execute("UPDATE g3b_attempts SET receipt_json=? WHERE attempt_id=?",
                     (json.dumps(document, sort_keys=True), row[0]))
    elif tamper == "file_nonce":
        path = _receipt_files(tmp_path)[0]
        file_doc = json.loads(path.read_text())
        file_doc["nonce"] = "e" * 32
        path.write_text(json.dumps(file_doc))
    elif tamper == "file_usage":
        path = _receipt_files(tmp_path)[0]
        file_doc = json.loads(path.read_text())
        file_doc["usage"]["outputTokens"] = 777
        path.write_text(json.dumps(file_doc))
    conn.commit()
    conn.close()
    harness = _recover(tmp_path)
    try:
        rows = harness.attempts_rows()
        assert [row["state"] for row in rows] == ["SETTLEMENT_UNCERTAIN"], rows
        status = harness.status(rows[0]["reservation_id"])
        assert status["status"] == "PENDING"
        assert harness.receipt_count() == 1
    finally:
        harness.close()


def test_c2_02e_two_reconciles_are_idempotent(tmp_path: Path) -> None:
    _prepare_root(tmp_path)
    _crash(tmp_path, "after_response_before_settlement")
    harness = _recover(tmp_path)
    try:
        first = harness.attempts_rows()
        first_messages = _broker_message_ids(tmp_path)
        first_status = harness.status(first[0]["reservation_id"])
        second = harness.controller.reconcile_on_startup(str(tmp_path / "receipts"))
        assert [row["state"] for row in second] == ["SETTLED"]
        assert harness.receipt_count() == 1
        assert _broker_message_ids(tmp_path) == first_messages
        assert harness.status(first[0]["reservation_id"])["cost"] == first_status["cost"]
        assert harness.status(first[0]["reservation_id"])["status"] == "OK"
    finally:
        harness.close()


def test_c2_02f_broker_failed_recovery_is_held_not_settled(tmp_path: Path) -> None:
    _prepare_root(tmp_path, scenario="partial_usage")
    _crash(tmp_path, "after_response_before_settlement")
    rows = _attempt_rows(tmp_path)
    assert [row["state"] for row in rows] == ["RESPONSE_OBSERVED"]
    document = json.loads(rows[0]["receipt_json"])
    assert document["completeness"] == "PARTIAL"
    harness = _recover(tmp_path)
    try:
        rows = harness.attempts_rows()
        assert [row["state"] for row in rows] == ["WORST_CASE_HELD"]
        assert rows[0]["state"] != "SETTLED"
        status = harness.status(rows[0]["reservation_id"])
        assert status["status"] == "FAILED"
        assert status["estimated"] is True
        assert status["input_used"] == status["input_bound"]
        assert harness.receipt_count() == 1
        harness.controller.reconcile_on_startup(str(tmp_path / "receipts"))
        assert harness.attempts_rows()[0]["state"] == "WORST_CASE_HELD"
    finally:
        harness.close()


# ---------------------------------------------------------------- crash windows
def test_crash_window_after_reserve_before_claim_is_held_and_replay_blocked(
        tmp_path: Path) -> None:
    _prepare_root(tmp_path)
    _crash(tmp_path, "after_reserve_before_claim")
    assert _attempt_rows(tmp_path) == []
    intents = _intent_rows(tmp_path)
    assert len(intents) == 1
    assert intents[0]["state"] == "RESERVED"
    harness = _recover(tmp_path)
    try:
        intent = _intent_rows(tmp_path)[0]
        assert intent["state"] == "HELD_UNCERTAIN"
        status = harness.status(intent["reservation_id"])
        assert status["status"] == "PENDING"
        assert harness.receipt_count() == 0
        from test_c1_03_admission import collect, error_code, payload
        replay = collect(harness.controller, payload())
        assert error_code(replay) == "ATTEMPT_ALREADY_STARTED"
        assert harness.receipt_count() == 0
    finally:
        harness.close()


def test_crash_window_after_claim_before_attempt_is_held(tmp_path: Path) -> None:
    _prepare_root(tmp_path)
    _crash(tmp_path, "after_claim_before_attempt_start")
    assert _attempt_rows(tmp_path) == []
    intents = _intent_rows(tmp_path)
    assert len(intents) == 1 and intents[0]["state"] == "CLAIMED"
    harness = _recover(tmp_path)
    try:
        intent = _intent_rows(tmp_path)[0]
        assert intent["state"] == "HELD_UNCERTAIN"
        status = harness.status(intent["reservation_id"])
        assert status["status"] == "PENDING"
        assert harness.snapshot()["claims"]["total"] == 1
        assert harness.receipt_count() == 0
    finally:
        harness.close()


def test_crash_window_after_attempt_before_send_is_uncertain(tmp_path: Path) -> None:
    _prepare_root(tmp_path)
    _crash(tmp_path, "after_attempt_start_before_fake_send")
    assert [row["state"] for row in _attempt_rows(tmp_path)] == ["ATTEMPT_STARTED"]
    harness = _recover(tmp_path)
    try:
        rows = harness.attempts_rows()
        assert [row["state"] for row in rows] == ["SETTLEMENT_UNCERTAIN"]
        assert harness.status(rows[0]["reservation_id"])["status"] == "PENDING"
        assert harness.receipt_count() == 0
    finally:
        harness.close()


def test_crash_window_after_fake_receive_settles_from_receipt_file(
        tmp_path: Path) -> None:
    _prepare_root(tmp_path)
    _crash(tmp_path, "after_fake_receive_before_response")
    assert [row["state"] for row in _attempt_rows(tmp_path)] == ["ATTEMPT_STARTED"]
    assert len(_receipt_files(tmp_path)) == 1
    harness = _recover(tmp_path)
    try:
        rows = harness.attempts_rows()
        assert [row["state"] for row in rows] == ["SETTLED"]
        assert harness.receipt_count() == 1
        assert harness.status(rows[0]["reservation_id"])["status"] == "OK"
    finally:
        harness.close()


def test_crash_window_after_journal_mark_is_terminal(tmp_path: Path) -> None:
    _prepare_root(tmp_path)
    _crash(tmp_path, "after_journal_mark_before_sdk_finish")
    assert [row["state"] for row in _attempt_rows(tmp_path)] == ["SETTLED"]
    harness = make_harness(tmp_path, register=False, write_configs=False)
    try:
        before = _broker_message_ids(tmp_path)
        harness.controller.reconcile_on_startup(str(tmp_path / "receipts"))
        assert harness.attempts_rows()[0]["state"] == "SETTLED"
        assert _broker_message_ids(tmp_path) == before
        assert harness.receipt_count() == 1
    finally:
        harness.close()


def test_c2_02_settle_reply_loss_replay_is_idempotent(tmp_path: Path) -> None:
    harness = make_harness(tmp_path)
    try:
        call_id = "call-" + "6" * 48
        reserved = harness.broker.reserve(
            task_id="g3b-task", route_id="offline-test-only-g3b",
            model="fixture-bridge-v1", input_tokens=100, output_tokens=50,
            call_id=call_id)
        reservation_id = reserved["reservation_id"]
        claimed = harness.broker.claim(
            call_id=call_id, reservation_id=reservation_id, request_digest="a" * 64,
            expected_route_id="offline-test-only-g3b", expected_model="fixture-bridge-v1")
        assert claimed["ok"]
        message = {"v": 1, "id": "g3c-dup-settle", "op": "settle",
                   "reservation_id": reservation_id,
                   "usage": {"inputTokens": 11, "cacheReadTokens": 2,
                             "cacheWriteTokens": 0, "outputTokens": 5,
                             "reasoningTokens": 0, "totalTokens": 18}}

        def raw(message_dict: dict) -> dict:
            harness.broker.proc.stdin.write(
                (json.dumps(message_dict, separators=(",", ":")) + "\n").encode())
            harness.broker.proc.stdin.flush()
            return json.loads(harness.broker.proc.stdout.readline())

        first = raw(message)
        second = raw(message)
        assert first["ok"] and first["code"] == "SETTLED", first
        assert second["code"] == "SETTLED" and second.get("duplicate") is True, second
        status = harness.status(reservation_id)
        assert status["status"] == "OK"
        assert status["input_used"] == 13 and status["output_used"] == 5
        assert _broker_message_ids(tmp_path).count("g3c-dup-settle") == 1
        assert harness.receipt_count() == 0
    finally:
        harness.close()
