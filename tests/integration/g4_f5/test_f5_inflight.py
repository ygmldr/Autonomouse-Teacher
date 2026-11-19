"""G4-F5 in-flight failure windows: authorize -> consume -> Fake -> settle.

The host tests use the same durable state a trusted-process death leaves behind
(Broker PENDING, Attempt row, gate journal). The process-level crash is exercised
by the real container matrix in ``artifacts/g4f/f5`` with the existing
``G3B_TEST_MODE`` crash hooks.
"""
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


def _recover(tmp_path, controller, broker, fake):
    gate2 = f5.make_gate()
    attempts2 = AttemptJournal(tmp_path / "attempts.sqlite3")
    controller2 = TrustedController(
        controller.admission, broker=broker, fake=fake, attempts=attempts2,
        expected_uid=65534, register_admission=False, dispatch_gate=gate2)
    controller2.reconcile_on_startup(str(tmp_path / "receipts"))
    return controller2, attempts2, gate2


def test_crash_after_authorize_conserves_held_and_never_sends(tmp_path) -> None:
    gate = f5.CrashAfterAuthorizeGate()
    controller, broker, fake, attempts, gate = f5.start_controller(
        tmp_path, gate=gate, max_calls=8)
    try:
        frames = f3.collect(controller, f3.request_payload())
        assert f3.call_error(frames) is not None, frames
        assert fake.received_count() == 0
        state = _broker_snapshot(broker)
        assert state["requests"] == 1
        assert state["pending"] == 1
        assert Decimal(state["reserved_usd"]) > 0
        assert Decimal(state["spent_usd"]) == 0
        rows = attempts.attempts()
        assert len(rows) == 1
        # The process never reached its normal abort handler: the durable row
        # is exactly what a crash leaves behind.
        assert rows[0]["state"] == "ATTEMPT_STARTED"
        snapshot = gate.snapshot()
        assert snapshot["sends_authorized"] == 1
        assert snapshot["consumed"] == 0
        assert Decimal(snapshot["worst_case_held_usd"]) > 0

        controller2, attempts2, gate2 = _recover(tmp_path, controller, broker, fake)
        recovery_state = _broker_snapshot(broker)
        assert recovery_state["requests"] == 1
        assert fake.received_count() == 0
        row2 = attempts2.attempts()[0]
        assert row2["state"] == "SETTLEMENT_UNCERTAIN"
        recovery = gate2.snapshot()
        assert Decimal(recovery["worst_case_held_usd"]) == Decimal(
            recovery_state["reserved_usd"])
        assert recovery["known_cost_usd"] == "0"
        assert recovery["cost_view"]["reservations"][0]["broker_status"] == "PENDING"

        # Replay is a no-op: no second reservation, no second Fake, no resend.
        replay = f3.collect(controller2, f3.request_payload())
        assert f3.call_error(replay) == "ATTEMPT_ALREADY_STARTED", replay
        assert _broker_snapshot(broker)["requests"] == 1
        assert fake.received_count() == 0
    finally:
        f3.close_all(broker, fake, attempts)


def test_crash_after_consume_burns_capability_and_never_sends(tmp_path) -> None:
    gate = f5.CrashAfterConsumeGate()
    controller, broker, fake, attempts, gate = f5.start_controller(
        tmp_path, gate=gate, max_calls=8)
    try:
        frames = f3.collect(controller, f3.request_payload())
        assert f3.call_error(frames) is not None, frames
        assert fake.received_count() == 0
        state = _broker_snapshot(broker)
        assert state["requests"] == 1 and state["pending"] == 1
        assert Decimal(state["spent_usd"]) == 0
        rows = attempts.attempts()
        assert len(rows) == 1 and rows[0]["state"] == "ATTEMPT_STARTED"
        snapshot = gate.snapshot()
        assert snapshot["sends_authorized"] == 1
        assert snapshot["consumed"] == 1
        # The capability cannot be re-consumed (burned before the Fake).
        assert gate._issued == {}  # noqa: SLF001 - test-only capability view

        controller2, attempts2, gate2 = _recover(tmp_path, controller, broker, fake)
        assert fake.received_count() == 0
        assert attempts2.attempts()[0]["state"] == "SETTLEMENT_UNCERTAIN"
        recovery = gate2.snapshot()
        assert Decimal(recovery["worst_case_held_usd"]) > 0
        assert recovery["known_cost_usd"] == "0"
        assert _broker_snapshot(broker)["requests"] == 1
    finally:
        f3.close_all(broker, fake, attempts)


def test_crash_after_receipt_before_settlement_holds_then_settles(tmp_path) -> None:
    gate = f5.make_gate()
    controller, broker, fake, attempts, gate = f5.start_controller(
        tmp_path, gate=gate, max_calls=8)
    real_completion = controller._completion_call
    lost = {"raised": False}

    def lossy_completion(op, reservation_id, usage, deadline):
        if not lost["raised"]:
            lost["raised"] = True
            raise RuntimeError("simulated crash between receipt and settlement")
        return real_completion(op, reservation_id, usage, deadline)

    try:
        controller._completion_call = lossy_completion
        frames = f3.collect(controller, f3.request_payload())
        assert f3.call_error(frames) is not None, frames
        assert fake.received_count() == 1
        state = _broker_snapshot(broker)
        assert state["pending"] == 1
        assert Decimal(state["reserved_usd"]) > 0
        snapshot = gate.snapshot()
        assert Decimal(snapshot["worst_case_held_usd"]) == Decimal(
            state["reserved_usd"])
        assert snapshot["known_cost_usd"] == "0"
        rows = attempts.attempts()
        assert len(rows) == 1
        assert rows[0]["state"] == "RESPONSE_OBSERVED"
        assert rows[0]["receipt_id"] is not None

        # Recovery settles exactly once from the durable receipt (Broker
        # authority); the Fake is never re-entered.
        controller._completion_call = real_completion
        gate2 = f5.make_gate()
        attempts2 = AttemptJournal(tmp_path / "attempts.sqlite3")
        controller2 = TrustedController(
            controller.admission, broker=broker, fake=fake, attempts=attempts2,
            expected_uid=65534, register_admission=False, dispatch_gate=gate2)
        controller2.reconcile_on_startup(str(tmp_path / "receipts"))
        state = _broker_snapshot(broker)
        assert state["pending"] == 0
        assert state["requests"] == 1
        assert Decimal(state["spent_usd"]) > 0
        recovery = gate2.snapshot()
        assert recovery["worst_case_held_usd"] == "0"
        assert recovery["known_cost_usd"] == state["spent_usd"]
        assert fake.received_count() == 1
        assert attempts2.attempts()[0]["state"] == "SETTLED"
    finally:
        controller._completion_call = real_completion
        f3.close_all(broker, fake, attempts)
