"""R2-05..R2-09: recovery first_cause vs reconciliation observation.

G4-F F5-R5 recorded that startup reconciliation overwrote the live first cause
(``REVOKED_PRE_SEND:RUN_AUTHORIZATION_REVOKED``) with the downstream
``RECEIPT_DOCUMENT_SCHEMA_INVALID`` observation.  These tests prove the G4-R
split:

* the Attempt ``reason`` keeps the proven revocation first cause only while the
  authoritative Broker answer is still ``PENDING``;
* an independent append-only recovery diagnostic always records the latest
  reconciliation observation (missing/corrupt receipt, Broker status, action);
* no prior cause -> ``NO_RECEIPT_AFTER_CRASH`` (a known enum), never a
  misleading invented reason;
* Broker ``OK``/``FAILED`` stays authoritative and is archived exactly once;
* the decision is independently re-derivable from the raw DB rows + JSONL.
"""
from __future__ import annotations

import json

from autoteacher_m0.bridge.recovery_diagnostics import (
    ACTION_MARK_SETTLED, ACTION_MARK_UNCERTAIN, ACTION_MARK_WORST_CASE,
    is_preservable_primary_cause,
)
import g4r_support as g4r

REVOKED = "REVOKED_PRE_SEND:RUN_AUTHORIZATION_REVOKED"


def _corrupt_receipt() -> str:
    """A well-formed JSON document with the wrong Observation schema."""
    return json.dumps({"schema": "m0.g3c.not-the-observation-schema.v1",
                       "broken": True})


def test_r2_05_revocation_primary_cause_preserved_on_pending(tmp_path) -> None:
    controller, broker, attempts, fake = g4r.start_recovery_harness(
        tmp_path, broker_status="PENDING")
    g4r.seed_attempt(attempts, state="RESPONSE_OBSERVED", reason=REVOKED,
                     receipt_json=_corrupt_receipt())
    try:
        controller.reconcile_on_startup(str(tmp_path / "receipts"))
        rows = attempts.attempts()
        assert len(rows) == 1
        assert rows[0]["state"] == "SETTLEMENT_UNCERTAIN"
        # The live first cause is preserved while the Broker is still PENDING.
        assert rows[0]["reason"] == REVOKED
        # No Broker settle/fail was issued: the reservation stays held.
        assert broker.settle_calls == [] and broker.fail_calls == []
        assert broker.status == "PENDING"
        diagnostics = g4r.diagnostic_rows(tmp_path)
        assert len(diagnostics) == 1, diagnostics
        record = diagnostics[0]
        assert record["primary_cause"] == REVOKED
        assert record["primary_cause_preserved"] is True
        assert record["reconciliation_observation"] == "RECEIPT_DOCUMENT_SCHEMA_INVALID"
        assert record["broker_status"] == "PENDING"
        assert record["action"] == ACTION_MARK_UNCERTAIN
        assert record["reserved"] is False
        assert is_preservable_primary_cause(rows[0]["reason"])
        # No Fake send happened: recovery never enters the provider.
        assert fake.received_count() == 0
    finally:
        attempts.close()


def test_r2_05_other_reason_is_not_silently_frozen(tmp_path) -> None:
    """Only the proven revocation enumeration may be preserved."""
    controller, broker, attempts, fake = g4r.start_recovery_harness(
        tmp_path, broker_status="PENDING")
    g4r.seed_attempt(attempts, state="RESPONSE_OBSERVED",
                     reason="SOMETHING_NEW_AND_SEVERE",
                     receipt_json=_corrupt_receipt())
    try:
        controller.reconcile_on_startup(str(tmp_path / "receipts"))
        row = attempts.attempts()[0]
        assert row["state"] == "SETTLEMENT_UNCERTAIN"
        # A non-proven reason is replaced by the concrete observation instead of
        # being frozen (it could hide a new severe state).
        assert row["reason"] == "RECEIPT_DOCUMENT_SCHEMA_INVALID"
        record = g4r.diagnostic_rows(tmp_path)[0]
        assert record["primary_cause_preserved"] is False
        assert record["prior_reason_class"] == "OTHER"
    finally:
        attempts.close()


def test_r2_06_crash_without_prior_reason_is_known_enum(tmp_path) -> None:
    controller, broker, attempts, fake = g4r.start_recovery_harness(
        tmp_path, broker_status="PENDING")
    g4r.seed_attempt(attempts, state="ATTEMPT_STARTED", reason=None,
                     receipt_json=None)
    # No receipt file exists for this attempt.
    try:
        controller.reconcile_on_startup(str(tmp_path / "receipts"))
        rows = attempts.attempts()
        assert len(rows) == 1
        assert rows[0]["state"] == "SETTLEMENT_UNCERTAIN"
        assert rows[0]["reason"] == "NO_RECEIPT_AFTER_CRASH"
        record = g4r.diagnostic_rows(tmp_path)[0]
        assert record["reconciliation_observation"] == "NO_RECEIPT_AFTER_CRASH"
        assert record["primary_cause"] is None
        assert record["action"] == ACTION_MARK_UNCERTAIN
        assert record["broker_status"] is None
    finally:
        attempts.close()


def test_r2_07_corrupt_receipt_plus_revocation_keeps_both_facts(tmp_path) -> None:
    controller, broker, attempts, fake = g4r.start_recovery_harness(
        tmp_path, broker_status="PENDING")
    # A malformed document (not even JSON) plus a revoked first cause.
    g4r.seed_attempt(attempts, state="RESPONSE_OBSERVED", reason=REVOKED,
                     receipt_json="{not-json")
    try:
        controller.reconcile_on_startup(str(tmp_path / "receipts"))
        row = attempts.attempts()[0]
        assert row["state"] == "SETTLEMENT_UNCERTAIN"
        assert row["reason"] == REVOKED
        assert broker.settle_calls == [] and broker.fail_calls == []
        assert broker.status == "PENDING"
        record = g4r.diagnostic_rows(tmp_path)[0]
        assert record["primary_cause"] == REVOKED
        assert record["primary_cause_preserved"] is True
        assert record["reconciliation_observation"] == "RECEIPT_DOCUMENT_INVALID"
        assert record["reserved"] is False
    finally:
        attempts.close()


def test_r2_08_broker_terminal_truth_wins_exactly_once(tmp_path) -> None:
    controller, broker, attempts, fake = g4r.start_recovery_harness(
        tmp_path, broker_status="OK")
    g4r.seed_attempt(attempts, state="RESPONSE_OBSERVED", reason=REVOKED,
                     receipt_json=_corrupt_receipt())
    try:
        controller.reconcile_on_startup(str(tmp_path / "receipts"))
        row = attempts.attempts()[0]
        assert row["state"] == "SETTLED"
        settlement = json.loads(row["settlement_json"])
        assert settlement["archived_from_broker"]["status"] == "OK"
        assert settlement["local_evidence_reason"] == "RECEIPT_DOCUMENT_SCHEMA_INVALID"
        # Archival only: recovery must not issue a second Broker settlement.
        assert broker.settle_calls == [] and broker.fail_calls == []
        first = g4r.diagnostic_rows(tmp_path)
        assert first[0]["action"] == ACTION_MARK_SETTLED
        # A second reconcile is idempotent and adds no settlement.
        controller.reconcile_on_startup(str(tmp_path / "receipts"))
        assert attempts.attempts()[0]["state"] == "SETTLED"
        assert broker.settle_calls == [] and broker.fail_calls == []
        assert len(g4r.diagnostic_rows(tmp_path)) == 1
    finally:
        attempts.close()


def test_r2_08_broker_failed_terminal_truth_wins(tmp_path) -> None:
    controller, broker, attempts, fake = g4r.start_recovery_harness(
        tmp_path, broker_status="FAILED")
    g4r.seed_attempt(attempts, state="RESPONSE_OBSERVED", reason=REVOKED,
                     receipt_json=_corrupt_receipt())
    try:
        controller.reconcile_on_startup(str(tmp_path / "receipts"))
        row = attempts.attempts()[0]
        assert row["state"] == "WORST_CASE_HELD"
        assert row["reason"] == "BROKER_ALREADY_FAILED:RECEIPT_DOCUMENT_SCHEMA_INVALID"
        assert broker.settle_calls == [] and broker.fail_calls == []
        record = g4r.diagnostic_rows(tmp_path)[0]
        assert record["action"] == ACTION_MARK_WORST_CASE
        assert record["broker_status"] == "FAILED"
    finally:
        attempts.close()


def test_r2_09_read_only_db_and_jsonl_reconcile_held_equals_reserved(
        tmp_path) -> None:
    controller, broker, attempts, fake = g4r.start_recovery_harness(
        tmp_path, broker_status="PENDING")
    g4r.seed_attempt(attempts, state="RESPONSE_OBSERVED", reason=REVOKED,
                     receipt_json=_corrupt_receipt())
    g4r.seed_attempt(attempts, call_id="call-r2b", reservation_id="res-r2b",
                     attempt_id="att-r2b", state="ATTEMPT_STARTED",
                     reason=None, receipt_json=None)
    try:
        controller.reconcile_on_startup(str(tmp_path / "receipts"))
        # Independent read-only view of the raw durable rows.
        raw = g4r.attempt_rows(tmp_path / "attempts.sqlite3")
        assert [row["attempt_id"] for row in raw] == ["att-r2", "att-r2b"]
        assert [row["state"] for row in raw] == [
            "SETTLEMENT_UNCERTAIN", "SETTLEMENT_UNCERTAIN"]
        assert raw[0]["reason"] == REVOKED
        assert raw[1]["reason"] == "NO_RECEIPT_AFTER_CRASH"
        diagnostics = g4r.diagnostic_rows(tmp_path)
        assert len(diagnostics) == 2, diagnostics
        # The two conservative attempts correspond to two Broker PENDING holds:
        # held == reserved for the recovered set (no release, no spend).
        assert broker.settle_calls == [] and broker.fail_calls == []
        assert broker.status == "PENDING"
        held_attempts = [row for row in raw
                         if row["state"] in {"SETTLEMENT_UNCERTAIN",
                                             "WORST_CASE_HELD",
                                             "ATTEMPT_STARTED"}]
        assert len(held_attempts) == len(diagnostics) == 2
        assert all(row["reason"] for row in held_attempts)
        # The diagnostic stream is itself content-free/bounded.
        for record in diagnostics:
            assert record["schema"] == "m0.g4r.recovery-diagnostic.v1"
            assert "prompt" not in record and "session" not in record
    finally:
        attempts.close()
