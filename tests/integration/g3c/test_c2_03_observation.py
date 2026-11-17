"""G3-C C2-03: the Attempt Receipt/Observation journal is the single
authoritative observation location; replay is side-effect free and a different
Observation Digest cannot overwrite a trusted/terminal observation.
"""
from __future__ import annotations
import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from autoteacher_m0.security.egress import canonical_json
from test_c1_03_admission import collect, make_harness, payload
from test_c2_02_recovery import _crash, _prepare_root, _recover


def _digest(document: dict) -> str:
    return hashlib.sha256(canonical_json(document).encode("utf-8")).hexdigest()


def _resign(document: dict) -> str:
    document.pop("journal_digest", None)
    document["journal_digest"] = _digest(document)
    return json.dumps(document, sort_keys=True)


def test_c2_03a_same_observation_replay_has_no_side_effects(tmp_path: Path) -> None:
    harness = make_harness(tmp_path)
    try:
        frames = collect(harness.controller, payload())
        assert not any(frame["kind"] == "error" for frame in frames), frames
        row = harness.attempts_rows()[0]
        before = row["receipt_json"]
        before_settlement = row["settlement_json"]
        harness.controller.reconcile_on_startup(str(tmp_path / "receipts"))
        harness.controller.reconcile_on_startup(str(tmp_path / "receipts"))
        row = harness.attempts_rows()[0]
        assert row["state"] == "SETTLED"
        assert row["receipt_json"] == before
        assert row["settlement_json"] == before_settlement
        assert harness.receipt_count() == 1
    finally:
        harness.close()


def test_c2_03b_same_call_different_observation_digest_is_rejected(
        tmp_path: Path) -> None:
    harness = make_harness(tmp_path)
    try:
        frames = collect(harness.controller, payload())
        assert not any(frame["kind"] == "error" for frame in frames), frames
        row = harness.attempts_rows()[0]
        document = json.loads(row["receipt_json"])
        document["observation"]["input"] = 999
        document["observation_digest"] = hashlib.sha256(
            canonical_json(document["observation"]).encode("utf-8")).hexdigest()
        conflicting = _resign(document)
        with pytest.raises(ValueError, match="OBSERVATION_CONFLICT"):
            harness.attempts.mark_response_observed(
                row["attempt_id"], receipt_id=row["receipt_id"],
                receipt_json=conflicting)
        unchanged = harness.attempts_rows()[0]
        assert unchanged["state"] == "SETTLED"
        assert unchanged["receipt_json"] == row["receipt_json"]
        assert harness.status(row["reservation_id"])["status"] == "OK"
        assert harness.receipt_count() == 1
    finally:
        harness.close()


def test_c2_03c_missing_provenance_refuses_settlement(tmp_path: Path) -> None:
    _prepare_root(tmp_path)
    _crash(tmp_path, "after_response_before_settlement")
    conn = sqlite3.connect(tmp_path / "attempts.sqlite3")
    row = conn.execute("SELECT attempt_id, receipt_json FROM g3b_attempts").fetchone()
    document = json.loads(row[1])
    del document["provenance"]
    conn.execute("UPDATE g3b_attempts SET receipt_json=? WHERE attempt_id=?",
                 (_resign(document), row[0]))
    conn.commit()
    conn.close()
    harness = _recover(tmp_path)
    try:
        rows = harness.attempts_rows()
        assert [row["state"] for row in rows] == ["SETTLEMENT_UNCERTAIN"]
        assert "PROVENANCE" in (rows[0]["reason"] or "") or (
            rows[0]["reason"] or "") == "RECEIPT_DOCUMENT_INCOMPLETE"
        assert harness.status(rows[0]["reservation_id"])["status"] == "PENDING"
        assert harness.receipt_count() == 1
    finally:
        harness.close()


def test_c2_03d_broker_and_journal_summaries_are_consistent(tmp_path: Path) -> None:
    harness = make_harness(tmp_path)
    try:
        for index in range(2):
            frames = collect(harness.controller, payload(
                messages=[{"role": "user", "content": f"summary-{index}"}]))
            assert not any(frame["kind"] == "error" for frame in frames), frames
        rows = harness.attempts_rows()
        assert len(rows) == 2
        total_cost = 0.0
        total_input = total_output = 0
        for row in rows:
            document = json.loads(row["receipt_json"])
            settlement = json.loads(row["settlement_json"])
            entry = settlement.get("settlement", settlement)
            status = harness.status(row["reservation_id"])
            assert status["status"] == "OK"
            assert status["input_used"] == entry["input_tokens"]
            assert status["output_used"] == entry["output_tokens"]
            assert status["cost"] == entry["cost_usd"]
            assert document["usage"] == {
                "inputTokens": 11, "cacheReadTokens": 2, "cacheWriteTokens": 0,
                "outputTokens": 5, "reasoningTokens": 0, "totalTokens": 18}
            total_cost += float(status["cost"])
            total_input += status["input_used"]
            total_output += status["output_used"]
        snapshot = harness.snapshot()
        assert snapshot["requests"] == 2
        assert snapshot["input_tokens"] == total_input
        assert snapshot["output_tokens"] == total_output
        assert float(snapshot["committed_usd"]) == pytest.approx(total_cost)
        assert snapshot["claims"] == {"total": 2, "pending": 0, "completed": 2}
        # The legacy broker observation table is NOT the authoritative location
        # and is deliberately unused by the G3-C attempt-observation design.
        conn = harness.broker_db()
        try:
            try:
                count = conn.execute(
                    "SELECT COUNT(*) FROM budget_provider_observations").fetchone()[0]
            except sqlite3.OperationalError:
                count = 0
        finally:
            conn.close()
        assert count == 0
    finally:
        harness.close()


def test_c2_03e_v1_broker_client_regression_and_status_is_read_only(
        tmp_path: Path) -> None:
    harness = make_harness(tmp_path)
    try:
        # Legacy v1 reserve/settle message shape: no call_id, original fields.
        reserved = harness.broker.request("reserve", {
            "task_id": "g2-legacy-task", "route_id": "offline-test-only-g3b",
            "model": "fixture-bridge-v1", "purpose": "conversation",
            "input_tokens": 100, "output_tokens": 50, "retry": False})
        assert reserved["ok"] and reserved["code"] == "RESERVED"
        reservation_id = reserved["reservation_id"]
        status = harness.broker.reservation_status(reservation_id)
        assert status["ok"] and status["code"] == "RESERVATION_STATUS"
        assert status["status"] == "PENDING"
        assert status["route_id"] == "offline-test-only-g3b"
        assert status["model"] == "fixture-bridge-v1"
        assert status["input_bound"] == 100
        unknown = harness.broker.reservation_status("r-unknown")
        assert unknown["code"] == "UNKNOWN_RESERVATION"
        conn = harness.broker_db()
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM budget_broker_messages WHERE message_id LIKE "
                "'b2-reservation_status-%'").fetchone()[0]
        finally:
            conn.close()
        assert count == 0
        settled = harness.broker.settle(
            reservation_id=reservation_id,
            usage={"inputTokens": 11, "outputTokens": 5})
        assert settled["ok"] and settled["code"] == "SETTLED"
        assert harness.broker.snapshot()["snapshot"]["requests"] == 1
    finally:
        harness.close()
