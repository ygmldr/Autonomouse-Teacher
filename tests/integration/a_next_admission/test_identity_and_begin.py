"""Run identity + epoch derivation + happy-path consume (A-NEXT A2 design §3)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from admission_support import (
    APPROVED_ROUTE, DEFAULT_ADMISSION_ID, DEFAULT_NONCE, begin, begin_kwargs, identity_for, journal_records, use_records,
    write_admission, write_state,
)
from autoteacher_m0.bridge import run_admission as ra


def test_epoch_is_deterministic_and_run_specific() -> None:
    first = ra.derive_run_epoch(admission_id=DEFAULT_ADMISSION_ID,
                                admission_nonce=DEFAULT_NONCE, run_id="run-a")
    assert first == ra.derive_run_epoch(admission_id=DEFAULT_ADMISSION_ID,
                                        admission_nonce=DEFAULT_NONCE,
                                        run_id="run-a")
    assert first != ra.derive_run_epoch(admission_id=DEFAULT_ADMISSION_ID,
                                        admission_nonce="c" * 32, run_id="run-a")
    assert first != ra.derive_run_epoch(admission_id=DEFAULT_ADMISSION_ID,
                                        admission_nonce=DEFAULT_NONCE,
                                        run_id="run-b")
    assert first.startswith("run-") and len(first) == 36


def test_identity_rejects_bad_field_or_derived_epoch() -> None:
    identity = ra.RunIdentity(run_id="run-a", admission_id=DEFAULT_ADMISSION_ID,
                              admission_nonce=DEFAULT_NONCE,
                              admission_sha256="d" * 64,
                              run_epoch=ra.derive_run_epoch(
                                  admission_id=DEFAULT_ADMISSION_ID,
                                  admission_nonce=DEFAULT_NONCE, run_id="run-a"))
    assert identity.run_id == "run-a"
    with pytest.raises(ra.RunAdmissionError) as error:
        ra.RunIdentity(run_id="run-a", admission_id="not-hex",
                       admission_nonce=DEFAULT_NONCE,
                       admission_sha256="d" * 64, run_epoch=identity.run_epoch)
    assert error.value.code == ra.RUN_ADMISSION_IDENTITY_INVALID
    with pytest.raises(ra.RunAdmissionError):
        ra.RunIdentity(run_id="run-a", admission_id=DEFAULT_ADMISSION_ID,
                       admission_nonce=DEFAULT_NONCE,
                       admission_sha256="d" * 64, run_epoch="run-tampered")
    with pytest.raises(ra.RunAdmissionError):
        ra.RunIdentity(run_id="bad run id", admission_id=DEFAULT_ADMISSION_ID,
                       admission_nonce=DEFAULT_NONCE,
                       admission_sha256="d" * 64, run_epoch=identity.run_epoch)


def test_build_run_identity_matches_admission_document(trusted, tmp_path: Path) -> None:
    admission_path = write_admission(tmp_path)
    identity = identity_for(admission_path, repo_root=trusted.repo)
    assert identity.run_id == "run-a2-host"
    assert identity.admission_id == DEFAULT_ADMISSION_ID
    assert identity.admission_nonce == DEFAULT_NONCE
    assert identity.run_epoch == ra.derive_run_epoch(
        admission_id=DEFAULT_ADMISSION_ID, admission_nonce=DEFAULT_NONCE,
        run_id="run-a2-host")
    # A document mutated *after* it was loaded no longer matches the loaded
    # sha256 that the launcher verified: the identity build must fail closed.
    from autoteacher_m0.bridge.admission import load_admission
    loaded = load_admission(admission_path, expected_uid=65534)
    document = json.loads(admission_path.read_text(encoding="utf-8"))
    document["run_id"] = "run-mutated"
    admission_path.write_text(json.dumps(document))
    with pytest.raises(ra.RunAdmissionError) as error:
        ra.build_run_identity(loaded, admission_path=admission_path,
                              repo_root=trusted.repo)
    assert error.value.code == ra.RUN_ADMISSION_IDENTITY_INVALID


def test_begin_success_consumes_once_and_records_audit(trusted, tmp_path: Path) -> None:
    use_log, journal_path = write_state(tmp_path)
    context = begin(trusted, tmp_path, use_log_dir=use_log,
                    journal_path=journal_path)
    try:
        assert context.state == ra.RUN_ADMISSION_ACTIVE
        assert context.identity.run_id == "run-a2-host"
        assert context.consumed == "YES"
        assert context.authorization_id == trusted.payload["authorization_id"]
        assert context.effective_max_calls == 8
        assert context.use_record_sha256 is not None
        context.ensure_startable()
        records = use_records(use_log)
        assert len(records) == 1
        body = json.loads(records[0].read_text(encoding="utf-8"))
        assert body["authorization_id"] == trusted.payload["authorization_id"]
        assert body["run_epoch"] == context.run_epoch
        journal = journal_records(journal_path)
        assert [record["event"] for record in journal] == ["intent", "outcome"]
        outcome = journal[-1]
        assert outcome["decision"] == "ALLOW"
        assert outcome["consumed"] == "YES"
        assert outcome["use_log_durability"] == "KNOWN"
        assert outcome["run_epoch"] == context.run_epoch
        assert outcome["external_network_calls"] == 0
        assert outcome["provider_keys_seen"] == 0
    finally:
        context.close("test")


def test_begin_effective_calls_use_minimum(trusted, tmp_path: Path) -> None:
    # An admission cap below the signed budget wins; the signed budget is 50.
    context = begin(trusted, tmp_path, admission_path=write_admission(
        tmp_path, max_calls=3, nonce="c" * 32, run_id="run-a2-cap"))
    try:
        assert context.effective_max_calls == 3
        assert context.max_attempts == 1
    finally:
        context.close("test")


def test_begin_requires_valid_limits_and_tool_schemas(trusted, tmp_path: Path) -> None:
    kwargs = begin_kwargs(trusted, tmp_path)
    kwargs["admission_limits"] = {"max_calls": 8, "max_attempts": 1}
    with pytest.raises(ra.RunAdmissionError) as error:
        ra.begin_run_admission(**kwargs)
    assert error.value.code == ra.RUN_ADMISSION_LIMITS_INVALID
    assert error.value.consumed == "NO"

    kwargs = begin_kwargs(trusted, tmp_path)
    kwargs["admission_tool_schemas"] = (("skill_lookup", "f" * 64),)
    kwargs["approved_tool_schemas"] = {"skill_lookup": "e" * 64}
    with pytest.raises(ra.RunAdmissionError) as error:
        ra.begin_run_admission(**kwargs)
    assert error.value.code == ra.RUN_ADMISSION_TOOL_SCHEMA_MISMATCH

    kwargs = begin_kwargs(trusted, tmp_path)
    kwargs["approved_tool_schemas"] = {"skill_lookup": "f" * 64}
    with pytest.raises(ra.RunAdmissionError) as error:
        ra.begin_run_admission(**kwargs)
    assert error.value.code == ra.RUN_ADMISSION_TOOL_SCHEMA_MISMATCH

    kwargs = begin_kwargs(trusted, tmp_path)
    kwargs["admission_tool_schemas"] = (("other_tool", "f" * 64),)
    with pytest.raises(ra.RunAdmissionError) as error:
        ra.begin_run_admission(**kwargs)
    assert error.value.code == ra.RUN_ADMISSION_TOOL_SCHEMA_MISMATCH
    assert "tool" in " ".join(error.value.reasons)


def test_budget_scope_mismatch_is_authorization_invalid(trusted, tmp_path: Path) -> None:
    with pytest.raises(ra.RunAdmissionError) as error:
        begin(trusted, tmp_path, budget_scope="not-the-approved-scope")
    assert error.value.code == ra.RUN_ADMISSION_AUTHORIZATION_INVALID
    assert any("BUDGET_SCOPE" in reason for reason in error.value.reasons)


def test_binding_drift_is_denied(trusted, tmp_path: Path) -> None:
    drifted = trusted.bindings.as_dict()
    drifted["code_sha256"] = "f" * 64
    kwargs = begin_kwargs(trusted, tmp_path)
    kwargs["observed_bindings"] = lambda: __import__(
        "autoteacher_m0.security.authorization", fromlist=["ExpectedBindings"]
    ).ExpectedBindings(**drifted)
    with pytest.raises(ra.RunAdmissionError) as error:
        ra.begin_run_admission(**kwargs)
    assert error.value.code == ra.RUN_ADMISSION_AUTHORIZATION_INVALID
    assert any("MISMATCH" in reason for reason in error.value.reasons)


def test_route_and_tools_follow_the_signed_document(trusted, tmp_path: Path) -> None:
    kwargs = begin_kwargs(trusted, tmp_path)
    kwargs["approved_route"] = type(APPROVED_ROUTE)(route_id="other-route",
                                                    provider="other",
                                                    model="other")
    with pytest.raises(ra.RunAdmissionError) as error:
        ra.begin_run_admission(**kwargs)
    assert error.value.code == ra.RUN_ADMISSION_AUTHORIZATION_INVALID
    assert any("ROUTE" in reason for reason in error.value.reasons)

    kwargs = begin_kwargs(trusted, tmp_path)
    kwargs["actual_tools"] = ("skill_lookup", "extra_tool")
    kwargs["admission_tool_schemas"] = (("skill_lookup", kwargs[
        "admission_tool_schemas"][0][1]), ("extra_tool", "e" * 64))
    with pytest.raises(ra.RunAdmissionError) as error:
        ra.begin_run_admission(**kwargs)
    assert error.value.code == ra.RUN_ADMISSION_AUTHORIZATION_INVALID
    assert any("ACTUAL_TOOL" in reason for reason in error.value.reasons)
