"""G4-C: durable business-identity replay guard (session/turn/call boundaries)."""
from __future__ import annotations

import sqlite3

import pytest

from autoteacher_m0.bridge.attempts import AttemptJournal


def _identity(step: int = 0, suffix: str = "a") -> str:
    return (suffix * 64)[:64]


def test_c06_same_business_identity_is_sent_at_most_once(tmp_path) -> None:
    journal = AttemptJournal(tmp_path / "attempts.sqlite3")
    try:
        call_id = "call-" + "1" * 48
        assert journal.claim_request_identity(
            scope_id="scope-g4c", identity_digest=_identity(),
            call_id=call_id, logical_step=0) is True
        with pytest.raises(ValueError) as exc:
            journal.claim_request_identity(
                scope_id="scope-g4c", identity_digest=_identity(),
                call_id="call-" + "2" * 48, logical_step=0)
        assert str(exc.value) == "ATTEMPT_ALREADY_STARTED"
    finally:
        journal.close()


def test_c06_new_logical_step_is_a_new_business_request(tmp_path) -> None:
    journal = AttemptJournal(tmp_path / "attempts.sqlite3")
    try:
        assert journal.claim_request_identity(
            scope_id="scope-g4c", identity_digest=_identity(0, "a"),
            call_id="call-" + "3" * 48, logical_step=0) is True
        assert journal.claim_request_identity(
            scope_id="scope-g4c", identity_digest=_identity(1, "b"),
            call_id="call-" + "4" * 48, logical_step=1) is True
        rows = journal.conn.execute(
            "SELECT call_id, logical_step FROM g3b_request_identities "
            "ORDER BY logical_step").fetchall()
        assert [tuple(row) for row in rows] == [
            ("call-" + "3" * 48, 0), ("call-" + "4" * 48, 1)]
    finally:
        journal.close()


def test_c06_session_resume_reuses_the_same_durable_guard(tmp_path) -> None:
    """A resumed session must not mint a second send for an old business request."""
    path = tmp_path / "attempts.sqlite3"
    first = AttemptJournal(path)
    try:
        assert first.claim_request_identity(
            scope_id="scope-g4c", identity_digest=_identity(0, "c"),
            call_id="call-" + "5" * 48, logical_step=0) is True
    finally:
        first.close()
    # The Controller restarts (session resume); the identity table is durable.
    reopened = AttemptJournal(path)
    try:
        with pytest.raises(ValueError) as exc:
            reopened.claim_request_identity(
                scope_id="scope-g4c", identity_digest=_identity(0, "c"),
                call_id="call-" + "6" * 48, logical_step=0)
        assert str(exc.value) == "ATTEMPT_ALREADY_STARTED"
    finally:
        reopened.close()
    connection = sqlite3.connect(path)
    try:
        count = connection.execute(
            "SELECT COUNT(*) FROM g3b_request_identities").fetchone()[0]
    finally:
        connection.close()
    assert count == 1
