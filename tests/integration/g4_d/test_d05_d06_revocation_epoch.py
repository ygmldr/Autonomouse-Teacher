"""D05/D06: revocation denies the future; an in-flight attempt is conserved."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from autoteacher_m0.bridge.attempts import AttemptJournal
from autoteacher_m0.security.authorization import AuthorizationRejected
from autoteacher_m0.security.egress import (
    EgressViolation,
)
import g4c_support as g4c
from g4a_support import RUN_EPOCH, TrustedFixture


def test_revocation_denies_and_keeps_single_use_record(tmp_path: Path) -> None:
    trusted = TrustedFixture(tmp_path)
    use = trusted.consume()
    assert use.record_path.is_file()
    trusted.set_revocations([use.authorization_id])
    decision = trusted.load()
    assert decision.approved is False
    assert "AUTHORIZATION_REVOKED" in decision.reasons
    with pytest.raises(AuthorizationRejected) as error:
        trusted.consume(run_epoch="g4d-epoch-2")
    assert "AUTHORIZATION_REVOKED" in error.value.reasons
    assert len(trusted.use_records()) == 1


def test_pending_attempt_is_conserved_and_never_resent(tmp_path: Path) -> None:
    journal = AttemptJournal(tmp_path / "attempts.sqlite3")
    call_id = "call-g4d-d05-host"
    attempt_id = journal.begin_attempt(
        scope_id="g4d-scope", call_id=call_id, reservation_id="res-g4d-d05-host",
        prepared_digest="33" * 32, payload_digest="44" * 32,
        payload_length=11, run_id="run-g4d-d05", logical_step=0, mode="synthetic")
    assert journal.state_for_call(call_id) == "ATTEMPT_STARTED"
    pending = journal.pending_attempts()
    assert len(pending) == 1 and pending[0]["attempt_id"] == attempt_id
    with pytest.raises(ValueError) as error:
        journal.begin_attempt(
            scope_id="g4d-scope", call_id=call_id,
            reservation_id="res-g4d-d05-host-2",
            prepared_digest="33" * 32, payload_digest="44" * 32,
            payload_length=11, run_id="run-g4d-d05", logical_step=0,
            mode="synthetic")
    assert "ATTEMPT_ALREADY_STARTED" in str(error.value)
    row = journal.attempt_for_call(call_id)
    assert row is not None and row["state"] == "ATTEMPT_STARTED"
    assert row["receipt_id"] is None
    journal.close()


def test_gate_epoch_change_denies_old_ticket(tmp_path: Path) -> None:
    bindings = g4c.same_bindings()
    gate = g4c.make_gate(binding_approved=bindings,
                         journal_path=tmp_path / "journal.jsonl")
    ticket = g4c.authorize(gate)
    stale = g4c.authorize(gate, prepared=g4c.make_prepared(step=1))
    gate.auth_epoch = "g4d-epoch-2"
    payload = g4c.make_payload(g4c.make_prepared(step=1))
    assert gate.consume(stale, payload_bytes=payload) == "AUTH_EPOCH_MISMATCH"
    # A new run's gate cannot spend with the previous run's ticket at all.
    other = g4c.make_gate(binding_approved=bindings, auth_epoch="g4d-epoch-3")
    assert other.consume(ticket, payload_bytes=g4c.make_payload(
        g4c.make_prepared())) in {"AUTHORIZATION_UNKNOWN", "AUTH_EPOCH_MISMATCH"}


def test_contract_epoch_mismatch_requires_a_new_authorization(tmp_path: Path) -> None:
    trusted = TrustedFixture(tmp_path)
    trusted.consume(run_epoch=RUN_EPOCH)
    with pytest.raises(AuthorizationRejected) as error:
        trusted.consume(run_epoch=RUN_EPOCH + "-next")
    assert "AUTHORIZATION_EPOCH_MISMATCH" in error.value.reasons


def test_binding_drift_blocks_authorization_before_any_send(tmp_path: Path) -> None:
    bindings = g4c.same_bindings()
    mutated = g4c.same_bindings()
    object.__setattr__(mutated, "code_sha256", hashlib.sha256(b"changed").hexdigest())
    gate = g4c.make_gate(binding_approved=bindings,
                         binding_observer=lambda: mutated)
    with pytest.raises(EgressViolation) as error:
        g4c.authorize(gate)
    assert any("PRE_DISPATCH" in reason or "BINDING" in reason
               for reason in error.value.reasons), error.value.reasons
