from __future__ import annotations
import sqlite3
from pathlib import Path
import pytest

from autoteacher_m0.bridge.attempts import AttemptJournal


def test_attempt_journal_transitions_and_unique(tmp_path: Path) -> None:
    journal = AttemptJournal(tmp_path / "attempts.sqlite3")
    attempt = journal.begin_attempt(scope_id="fixed-offline-scope", call_id="call-" + "a" * 48,
                                    reservation_id="r1", prepared_digest="a" * 64,
                                    payload_digest="b" * 64, payload_length=10)
    assert journal.state_for_call("call-" + "a" * 48) == "ATTEMPT_STARTED"
    with pytest.raises(ValueError, match="ATTEMPT_ALREADY_STARTED"):
        journal.begin_attempt(scope_id="fixed-offline-scope", call_id="call-" + "a" * 48,
                              reservation_id="r2", prepared_digest="a" * 64,
                              payload_digest="b" * 64, payload_length=10)
    journal.mark_response_observed(attempt, receipt_id="rcpt-" + "c" * 32,
                                   receipt_json="{}")
    journal.mark_worst_case(attempt, reason="partial")
    with sqlite3.connect(tmp_path / "attempts.sqlite3") as db:
        row = db.execute("SELECT state, receipt_id, payload_digest FROM g3b_attempts").fetchone()
    assert row[0] == "WORST_CASE_HELD" and row[1] == "rcpt-" + "c" * 32
    assert row[2] == "b" * 64
    journal.close()
