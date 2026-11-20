"""Run-admission audit allowlist and no-sensitive-content tests (design §5)."""
from __future__ import annotations

from pathlib import Path

import pytest

from admission_support import (
    begin, begin_kwargs, journal_records, write_state,
)
from autoteacher_m0.bridge import run_admission as ra

FORBIDDEN_SUBSTRINGS = (
    "sk-", "Bearer", "BEGIN PRIVATE", "api_key", "API_KEY",
    "password", "prompt", "messages", "session_text", "tool_args",
)


def _read_raw(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_audit_records_are_allowlisted_and_content_free(trusted, tmp_path: Path) -> None:
    use_log, journal_path = write_state(tmp_path)
    context = begin(trusted, tmp_path, use_log_dir=use_log,
                    journal_path=journal_path)
    try:
        token = context.begin_dispatch(call_id="call-audit", prepared_digest="a" * 64,
                                       payload_digest="a" * 64)
        assert context.consume_dispatch(
            token, call_id="call-audit", prepared_digest="a" * 64,
            payload_digest="a" * 64) is None
        context.consume_dispatch(token, call_id="call-audit",
                                 prepared_digest="a" * 64,
                                 payload_digest="a" * 64)  # replay -> dispatch_denied
    finally:
        context.close("test")
    records = journal_records(journal_path)
    assert records[0]["event"] == "intent"
    assert records[-1]["event"] == "final"
    for record in records:
        assert set(record) <= (ra._JOURNAL_FIELDS | {"schema", "event", "utc"})
        assert record["external_network_calls"] == 0
        assert record["provider_keys_seen"] == 0
        assert record["real_model_calls"] == 0
        assert record["attempt_db_touched"] is False
        assert record["historical_holds_modified"] is False
    raw = _read_raw(journal_path)
    for forbidden in FORBIDDEN_SUBSTRINGS:
        assert forbidden not in raw, forbidden
    # The raw business call id is never written; only its SHA-256 digest.
    assert "call-audit" not in raw
    denied = [record for record in records if record["event"] == "dispatch_denied"]
    assert len(denied) == 1
    assert denied[0]["dispatch_denial"] == ra.ADMISSION_TOKEN_REPLAYED
    assert denied[0]["call_id_sha256"] == __import__("hashlib").sha256(
        b"call-audit").hexdigest()


def test_journal_rejects_unknown_or_oversized_fields(trusted, tmp_path: Path) -> None:
    context = begin(trusted, tmp_path)
    try:
        with pytest.raises(ra.RunAdmissionError) as error:
            context.journal.append("final", {"prompt": "secret"})
        assert error.value.code == ra.RUN_ADMISSION_AUDIT_UNAVAILABLE
        with pytest.raises(ra.RunAdmissionError):
            context.journal.append("final", {"reject_reasons": ["x" * 300]})
        with pytest.raises(ra.RunAdmissionError):
            context.journal.append("not-an-event", {})
        with pytest.raises(ra.RunAdmissionError):
            context.journal.append("final", {"consumed": {"nested": True}})
    finally:
        context.close("test")


def test_audit_intent_precedes_outcome(trusted, tmp_path: Path) -> None:
    _, journal_path = write_state(tmp_path)
    context = begin(trusted, tmp_path, journal_path=journal_path)
    try:
        events = [record["event"] for record in journal_records(journal_path)]
        assert events == ["intent", "outcome"]
        intent = journal_records(journal_path)[0]
        assert intent["decision"] == "PENDING"
        assert intent["consumed"] is None
        outcome = journal_records(journal_path)[1]
        assert outcome["decision"] == "ALLOW"
        assert outcome["consumed"] == "YES"
        assert outcome["use_log_durability"] == "KNOWN"
        assert outcome["authorization_file_sha256"]
        assert outcome["authorization_payload_sha256"]
        assert outcome["use_record_sha256"]
    finally:
        context.close("test")


def test_audit_deny_records_reason_codes(trusted, tmp_path: Path) -> None:
    from admission_support import write_admission
    admission_path = write_admission(tmp_path)
    context = begin(trusted, tmp_path, admission_path=admission_path)
    context.close("first")
    kwargs = begin_kwargs(trusted, tmp_path, admission_path=admission_path)
    with pytest.raises(ra.RunAdmissionError):
        ra.begin_run_admission(**kwargs)
    records = journal_records(Path(kwargs["journal_path"]))
    outcome = records[-1]
    assert outcome["event"] == "outcome"
    assert outcome["decision"] == "DENY"
    assert outcome["consumed"] == "NO"
    assert outcome["reject_reasons"][0] == ra.RUN_ADMISSION_ALREADY_CONSUMED
