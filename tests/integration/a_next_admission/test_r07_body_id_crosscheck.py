"""R-07: real use-record body-id cross-check (A1 / P2-01), public consume only.

After the A1 merge (``fix/a-next-auth-record`` e6f3aa6), ``_read_use_record``
cross-checks the record body ``authorization_id`` against its storage name and
the verified authorization.  The run-admission layer must classify every such
mismatch as ``AUTHORIZATION_USE_RECORD_INVALID`` (never a replay) and must not
start a Broker/dispatch.  These tests use the public
``begin_run_admission()`` path only; no A1 private function is imported.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from admission_support import begin_kwargs, journal_records, use_records, write_state
from autoteacher_m0.bridge import run_admission as ra

USE_LOG_SCHEMA = "at-m0/authorization-use/v1"


def _record_path(use_log: Path, authorization_id: str) -> Path:
    return use_log / (hashlib.sha256(authorization_id.encode("ascii")).hexdigest()
                      + ".json")


def _deny(kwargs: dict) -> tuple[str, str]:
    with pytest.raises(ra.RunAdmissionError) as error:
        ra.begin_run_admission(**kwargs)
    return error.value.code, error.value.consumed


def test_r07_foreign_body_id_after_real_consume_is_invalid_not_replay(
        trusted, tmp_path: Path) -> None:
    use_log, journal_path = write_state(tmp_path)
    kwargs = begin_kwargs(trusted, tmp_path, use_log_dir=use_log,
                          journal_path=journal_path)
    authorization_id = trusted.payload["authorization_id"]
    context = ra.begin_run_admission(**kwargs)
    context.close("crash-after-consume-before-broker")
    record = _record_path(use_log, authorization_id)
    body = json.loads(record.read_text(encoding="utf-8"))
    assert body["authorization_id"] == authorization_id
    # A1 cross-check: filename is the expected sha256(id) but the body claims a
    # different (valid identifier) authorization.  That is corruption/foreign
    # state, NOT a replay: the run must be denied with RECORD_INVALID.
    body["authorization_id"] = "auth-foreign-body-id"
    record.write_text(json.dumps(body), encoding="utf-8")
    code, consumed = _deny(kwargs)
    assert code == ra.RUN_ADMISSION_RECORD_INVALID
    assert consumed == "NO"
    assert code not in (ra.RUN_ADMISSION_ALREADY_CONSUMED,
                        ra.RUN_ADMISSION_EPOCH_MISMATCH)
    # The final record is observed, never cleaned up or rewritten by A2.
    assert len(use_records(use_log)) == 1
    outcome = journal_records(journal_path)[-1]
    assert outcome["event"] == "outcome"
    assert outcome["decision"] == "DENY"
    assert outcome["consumed"] == "NO"


def test_r07_body_id_not_matching_storage_name_is_invalid(trusted, tmp_path: Path) -> None:
    use_log, journal_path = write_state(tmp_path)
    kwargs = begin_kwargs(trusted, tmp_path, use_log_dir=use_log,
                          journal_path=journal_path)
    authorization_id = trusted.payload["authorization_id"]
    record = _record_path(use_log, authorization_id)
    record.write_text(json.dumps({
        "schema": USE_LOG_SCHEMA,
        # body id hashes to a different filename than the one that exists
        "authorization_id": "auth-other-storage-id",
        "run_epoch": "run-unrelated-epoch",
        "consumed_utc": "2026-11-21T00:00:00Z",
    }), encoding="utf-8")
    code, consumed = _deny(kwargs)
    assert code == ra.RUN_ADMISSION_RECORD_INVALID
    assert consumed == "NO"


def test_r07_invalid_consumed_utc_is_invalid(trusted, tmp_path: Path) -> None:
    use_log, journal_path = write_state(tmp_path)
    kwargs = begin_kwargs(trusted, tmp_path, use_log_dir=use_log,
                          journal_path=journal_path)
    authorization_id = trusted.payload["authorization_id"]
    _record_path(use_log, authorization_id).write_text(json.dumps({
        "schema": USE_LOG_SCHEMA,
        "authorization_id": authorization_id,
        "run_epoch": "run-unrelated-epoch",
        "consumed_utc": "not-a-utc-timestamp",
    }), encoding="utf-8")
    code, consumed = _deny(kwargs)
    assert code == ra.RUN_ADMISSION_RECORD_INVALID
    assert consumed == "NO"


def test_r07_expected_id_valid_record_still_replays(trusted, tmp_path: Path) -> None:
    """Control: an untampered record for this authorization is a real replay."""
    use_log, journal_path = write_state(tmp_path)
    kwargs = begin_kwargs(trusted, tmp_path, use_log_dir=use_log,
                          journal_path=journal_path)
    ra.begin_run_admission(**kwargs).close("first")
    code, consumed = _deny(kwargs)
    assert code == ra.RUN_ADMISSION_ALREADY_CONSUMED
    assert consumed == "NO"
