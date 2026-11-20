"""Run-admission rejection matrix R-01..R-04/R-08/R-14/R-17/R-18/R-23/R-26."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from admission_support import (
    begin_kwargs, journal_records, use_records, write_state,
)
from autoteacher_m0.bridge import run_admission as ra
from autoteacher_m0.security import authorization as authorization_module
from g4a_support import KEY_ID, ROTATED_KEY_ID, ROTATED_SEED


def _assert_denied(trusted, tmp_path: Path, *, code: str, consumed: str = "NO",
                   expect_use_record: bool = False, **overrides) -> None:
    use_log, journal_path = write_state(tmp_path)
    kwargs = begin_kwargs(trusted, tmp_path, use_log_dir=use_log,
                          journal_path=journal_path, **overrides)
    with pytest.raises(ra.RunAdmissionError) as error:
        ra.begin_run_admission(**kwargs)
    assert error.value.code == code, error.value
    assert error.value.consumed == consumed
    assert len(use_records(use_log)) == (1 if expect_use_record else 0)
    records = journal_records(journal_path)
    assert records and records[-1]["event"] == "outcome"
    assert records[-1]["decision"] == "DENY"


def test_r01_forged_signature(trusted, tmp_path: Path) -> None:
    payload = copy.deepcopy(trusted.payload)
    signed = trusted.sign(payload, seed=ROTATED_SEED, key_id=KEY_ID)
    trusted.authorization.write_text(json.dumps(signed))
    _assert_denied(trusted, tmp_path, code=ra.RUN_ADMISSION_AUTHORIZATION_INVALID)


def test_r02_unknown_approval_key(trusted, tmp_path: Path) -> None:
    trusted.set_keys({ROTATED_KEY_ID: "f" * 64})
    _assert_denied(trusted, tmp_path, code=ra.RUN_ADMISSION_AUTHORIZATION_INVALID)


def test_r03_expired_and_not_yet_valid(trusted, tmp_path: Path) -> None:
    payload = copy.deepcopy(trusted.payload)
    payload.update({"issued_utc": "2026-11-18T10:00:00Z",
                    "not_before_utc": "2026-11-18T10:05:00Z",
                    "expires_utc": "2026-11-18T10:30:00Z"})
    trusted.write_signed(payload)
    _assert_denied(trusted, tmp_path, code=ra.RUN_ADMISSION_AUTHORIZATION_INVALID)
    payload = copy.deepcopy(trusted.payload)
    payload.update({"issued_utc": "2026-11-18T12:10:00Z",
                    "not_before_utc": "2026-11-18T12:20:00Z",
                    "expires_utc": "2026-11-18T12:30:00Z"})
    trusted.write_signed(payload)
    _assert_denied(trusted, tmp_path, code=ra.RUN_ADMISSION_AUTHORIZATION_INVALID)


def test_r04_revoked_authorization(trusted, tmp_path: Path) -> None:
    trusted.set_revocations([trusted.payload["authorization_id"]])
    _assert_denied(trusted, tmp_path, code=ra.RUN_ADMISSION_AUTHORIZATION_INVALID)


def test_r26_markdown_or_self_signed_document(trusted, tmp_path: Path) -> None:
    trusted.write_raw("# this markdown is not an authorization\n")
    _assert_denied(trusted, tmp_path, code=ra.RUN_ADMISSION_AUTHORIZATION_INVALID)
    trusted.write_raw(json.dumps({"schema": "at-m0/execution-authorization/v1",
                                  "authorization_id": "self"}))
    _assert_denied(trusted, tmp_path, code=ra.RUN_ADMISSION_AUTHORIZATION_INVALID)


def test_r17_binding_drift_pre_start(trusted, tmp_path: Path) -> None:
    from autoteacher_m0.security.authorization import ExpectedBindings
    drifted = trusted.bindings.as_dict()
    drifted["runtime_sha256"] = "f" * 64
    _assert_denied(trusted, tmp_path,
                   code=ra.RUN_ADMISSION_AUTHORIZATION_INVALID,
                   observed_bindings=lambda: ExpectedBindings(**drifted))


def test_r18_tool_schema_digest_drift(trusted, tmp_path: Path) -> None:
    kwargs = begin_kwargs(trusted, tmp_path)
    kwargs["approved_tool_schemas"] = {"skill_lookup": "f" * 64}
    use_log = kwargs["use_log_dir"]
    with pytest.raises(ra.RunAdmissionError) as error:
        ra.begin_run_admission(**kwargs)
    assert error.value.code == ra.RUN_ADMISSION_TOOL_SCHEMA_MISMATCH
    assert error.value.consumed == "NO"
    assert use_records(use_log) == []


def test_r14_use_log_full_is_fail_closed(trusted, tmp_path: Path,
                                         monkeypatch) -> None:
    monkeypatch.setattr(authorization_module, "_count_use_log_entries",
                        lambda directory: (authorization_module.MAX_AUTHORIZATION_USES, 0))
    _assert_denied(trusted, tmp_path, code=ra.RUN_ADMISSION_LOG_UNAVAILABLE)


def test_r23_audit_journal_unavailable(trusted, tmp_path: Path) -> None:
    use_log, _ = write_state(tmp_path)
    kwargs = begin_kwargs(trusted, tmp_path, use_log_dir=use_log,
                          journal_path=tmp_path / "missing" / "journal.jsonl")
    with pytest.raises(ra.RunAdmissionError) as error:
        ra.begin_run_admission(**kwargs)
    assert error.value.code == ra.RUN_ADMISSION_AUDIT_UNAVAILABLE
    assert error.value.consumed == "NO"
    assert use_records(use_log) == []


def test_r23_audit_full_after_consume_is_tri_state(trusted, tmp_path: Path) -> None:
    use_log, journal_path = write_state(tmp_path)
    original = ra.RunAdmissionJournal(journal_path, max_records=1)
    try:
        kwargs = begin_kwargs(trusted, tmp_path, use_log_dir=use_log,
                              journal_path=journal_path, journal=original)
        with pytest.raises(ra.RunAdmissionError) as error:
            ra.begin_run_admission(**kwargs)
        assert error.value.code == ra.RUN_ADMISSION_AUDIT_UNAVAILABLE
        # The use record already exists: the outcome audit failure must not
        # pretend nothing was consumed.
        assert error.value.consumed == "YES"
        assert len(use_records(use_log)) == 1
    finally:
        original.close()


def test_r15_budget_scope_mismatch_denied(trusted, tmp_path: Path) -> None:
    _assert_denied(trusted, tmp_path, code=ra.RUN_ADMISSION_AUTHORIZATION_INVALID,
                   budget_scope="other-scope")


def test_r20_deadline_exceeded_at_dispatch(trusted, tmp_path: Path) -> None:
    context = ra.begin_run_admission(**begin_kwargs(trusted, tmp_path))
    try:
        context._deadline_monotonic = 0.0
        with pytest.raises(ra.RunAdmissionError) as error:
            context.begin_dispatch(call_id="call-a", prepared_digest="a" * 64,
                                   payload_digest="a" * 64)
        assert error.value.code == ra.RUN_DEADLINE_EXCEEDED
    finally:
        context.close("test")
