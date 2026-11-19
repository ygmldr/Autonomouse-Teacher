"""G4-F5 revocation: pre-reserve / pre-send / in-flight, no resend, no FREE."""
from __future__ import annotations

from decimal import Decimal

from autoteacher_m0.bridge.attempts import AttemptJournal
from autoteacher_m0.bridge.controller import TrustedController

import g4f3_support as f3
import g4f5_support as f5


def _broker_snapshot(broker) -> dict:
    reply = broker.snapshot()
    assert reply.get("ok") is True, reply
    return reply["snapshot"]


def test_gate_revocation_document_is_strict_and_fail_closed(tmp_path) -> None:
    path = f5.revocation_path(tmp_path)
    gate = f5.make_gate(revocation=path)

    # Missing configured document: fail closed, never "assume valid".
    missing = gate.revocation_check("pre_reserve")
    assert missing["reason"] == "REVOCATION_STATE_INVALID"
    assert missing["revoked"] is True

    f5.write_revocation(path, revoked=False)
    assert gate.revocation_check("pre_reserve")["reason"] is None

    f5.write_revocation(path, revoked=True)
    revoked = gate.revocation_check("pre_reserve")
    assert revoked["reason"] == "RUN_AUTHORIZATION_REVOKED"
    assert revoked["revoked"] is True

    # A revocation aimed at another epoch/id does not revoke this run.
    f5.write_revocation(path, revoked=True, epoch="other-epoch")
    other_epoch = gate.revocation_check("pre_reserve")
    assert other_epoch["reason"] is None
    assert other_epoch["targets_run"] is False

    path.write_text("{not json", encoding="utf-8")
    invalid = gate.revocation_check("pre_send")
    assert invalid["reason"] == "REVOCATION_STATE_INVALID"
    snapshot = gate.snapshot()
    assert snapshot["revocation"]["configured"] is True
    assert snapshot["revocation"]["authorization_id"] == f5.AUTHORIZATION_ID
    assert len(snapshot["revocation"]["checks"]) >= 4


def test_pre_reserve_revocation_creates_no_ledger_row(tmp_path) -> None:
    path = f5.revocation_path(tmp_path)
    f5.write_revocation(path, revoked=True)
    gate = f5.make_gate(revocation=path)
    controller, broker, fake, attempts, gate = f5.start_controller(
        tmp_path, gate=gate, max_calls=8)
    try:
        frames = f3.collect(controller, f3.request_payload())
        assert f3.call_error(frames) == "ADMISSION_SELF_AUTH_DENIED", frames
        state = _broker_snapshot(broker)
        assert state["requests"] == 0
        assert state["reserved_usd"] == "0"
        assert Decimal(state["spent_usd"]) == 0
        assert fake.received_count() == 0
        assert attempts.attempts() == []
        assert attempts.pending_intents() == []
        assert controller.calls == 0
        snapshot = gate.snapshot()
        assert snapshot["sends_authorized"] == 0
        assert snapshot["worst_case_held_usd"] == "0"
        assert snapshot["known_cost_usd"] == "0"
        assert any(row["checkpoint"] == "pre_reserve"
                   and row["reason"] == "RUN_AUTHORIZATION_REVOKED"
                   for row in snapshot["revocation"]["checks"])
    finally:
        f3.close_all(broker, fake, attempts)


def test_post_reserve_revocation_denies_before_send_and_is_conserved(tmp_path) -> None:
    path = f5.revocation_path(tmp_path)
    f5.write_revocation(path, revoked=False)
    gate = f5.RevokeOnAuthorizeGate(path)
    controller, broker, fake, attempts, gate = f5.start_controller(
        tmp_path, gate=gate, max_calls=8)
    try:
        frames = f3.collect(controller, f3.request_payload())
        assert f3.call_error(frames) == "ADMISSION_SELF_AUTH_DENIED", frames
        assert gate.revocation_writes, "the revocation window was never written"
        assert fake.received_count() == 0
        state = _broker_snapshot(broker)
        assert state["requests"] == 1
        assert state["pending"] == 1
        assert Decimal(state["reserved_usd"]) > 0
        assert Decimal(state["spent_usd"]) == 0
        assert state["claims"]["total"] == 1
        rows = attempts.attempts()
        assert len(rows) == 1
        assert rows[0]["state"] == "SETTLEMENT_UNCERTAIN"
        snapshot = gate.snapshot()
        # authorize() denied: no capability, no hold in this process.
        assert snapshot["sends_authorized"] == 0
        assert snapshot["worst_case_held_usd"] == "0"

        # A *new* request is refused at pre-reserve: one reservation only.
        second = f3.collect(controller, f5.second_payload())
        assert f3.call_error(second) == "ADMISSION_SELF_AUTH_DENIED", second
        state = _broker_snapshot(broker)
        assert state["requests"] == 1
        assert fake.received_count() == 0
        assert len(attempts.attempts()) == 1

        # Recovery is readonly and conservative: Broker PENDING -> held>0.
        gate2 = f5.make_gate(revocation=path)
        attempts2 = AttemptJournal(tmp_path / "attempts.sqlite3")
        controller2 = TrustedController(
            controller.admission, broker=broker, fake=fake, attempts=attempts2,
            expected_uid=65534, register_admission=False, dispatch_gate=gate2)
        controller2.reconcile_on_startup(str(tmp_path / "receipts"))
        recovery = gate2.snapshot()
        assert recovery["worst_case_held_usd"] == state["reserved_usd"]
        assert recovery["known_cost_usd"] == "0"
        assert recovery["cost_view"]["reservations"][0]["broker_status"] == "PENDING"
        assert fake.received_count() == 0
        assert len(attempts2.attempts()) == 1
    finally:
        f3.close_all(broker, fake, attempts)


def test_consume_window_revocation_burns_the_capability(tmp_path) -> None:
    path = f5.revocation_path(tmp_path)
    f5.write_revocation(path, revoked=False)
    gate = f5.RevokeOnConsumeGate(path)
    controller, broker, fake, attempts, gate = f5.start_controller(
        tmp_path, gate=gate, max_calls=8)
    try:
        frames = f3.collect(controller, f3.request_payload())
        assert f3.call_error(frames) == "ADMISSION_SELF_AUTH_DENIED", frames
        assert fake.received_count() == 0
        state = _broker_snapshot(broker)
        assert state["requests"] == 1 and state["pending"] == 1
        assert Decimal(state["spent_usd"]) == 0
        rows = attempts.attempts()
        assert len(rows) == 1 and rows[0]["state"] == "SETTLEMENT_UNCERTAIN"
        snapshot = gate.snapshot()
        assert snapshot["sends_authorized"] == 1
        assert snapshot["consumed"] == 1
        assert snapshot["denials"], snapshot

        # The capability is burned: even after clearing the revocation
        # document, the same capability can never be consumed again.
        f5.write_revocation(path, revoked=False)
        authorization = gate._issued  # noqa: SLF001 - test-only capability view
        assert authorization == {}
    finally:
        f3.close_all(broker, fake, attempts)


def test_post_send_revocation_cannot_retract_settlement_or_resend(tmp_path) -> None:
    path = f5.revocation_path(tmp_path)
    f5.write_revocation(path, revoked=False)
    gate = f5.RevokeAfterSendGate(path)
    controller, broker, fake, attempts, gate = f5.start_controller(
        tmp_path, gate=gate, scenario="slow_usage", max_calls=8)
    try:
        frames = f3.collect(controller, f3.request_payload())
        assert f3.call_error(frames) is None, frames
        assert gate.consumed_count == 1
        assert fake.received_count() == 1
        state = _broker_snapshot(broker)
        assert state["requests"] == 1
        assert state["pending"] == 0
        assert Decimal(state["spent_usd"]) > 0
        rows = attempts.attempts()
        assert len(rows) == 1 and rows[0]["state"] == "SETTLED"
        snapshot = gate.snapshot()
        assert snapshot["worst_case_held_usd"] == "0"
        assert snapshot["known_cost_usd"] == state["spent_usd"]
        assert snapshot["sends_authorized"] == 1
        assert snapshot["consumed"] == 1

        # The settlement happened after the revocation document was already
        # revoked; it is still Broker-authoritative and never resendable.
        assert snapshot["revocation"]["checks"]
        second = f3.collect(controller, f5.second_payload())
        assert f3.call_error(second) == "ADMISSION_SELF_AUTH_DENIED", second
        assert _broker_snapshot(broker)["requests"] == 1
        assert fake.received_count() == 1
    finally:
        f3.close_all(broker, fake, attempts)


def test_invalid_revocation_state_stops_the_controller_before_reserve(tmp_path) -> None:
    path = f5.revocation_path(tmp_path)
    path.write_text('{"schema":"m0.g4c.revocation.v1"}', encoding="utf-8")
    gate = f5.make_gate(revocation=path)
    controller, broker, fake, attempts, gate = f5.start_controller(
        tmp_path, gate=gate, max_calls=8)
    try:
        frames = f3.collect(controller, f3.request_payload())
        assert f3.call_error(frames) == "ADMISSION_SELF_AUTH_DENIED", frames
        assert _broker_snapshot(broker)["requests"] == 0
        assert fake.received_count() == 0
        assert attempts.attempts() == []
    finally:
        f3.close_all(broker, fake, attempts)
