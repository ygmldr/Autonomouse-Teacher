"""G4-F3: Broker-authoritative accounting through the real controller path.

These tests start a real local Broker subprocess and a real local Fake
subprocess (synthetic fixture) but no container, no Key, no external socket.
They pin the F3 chain: Broker settlement -> controller relay -> gate view.
"""
from __future__ import annotations

import time
from decimal import Decimal

from autoteacher_m0.bridge.attempts import AttemptJournal
from autoteacher_m0.bridge.controller import BridgeError, TrustedController

import g4f3_support as f3


def _broker_snapshot(broker) -> dict:
    reply = broker.snapshot()
    assert reply.get("ok") is True, reply
    return reply["snapshot"]


def _attempt_row(controller: TrustedController, call_id: str) -> dict:
    row = controller.attempts.attempt_for_call(call_id)
    assert row is not None
    return row


def test_ok_usage_known_cost_equals_broker_settlement(tmp_path) -> None:
    controller, broker, fake, attempts, gate = f3.start_controller(tmp_path)
    try:
        frames = f3.collect(controller, f3.request_payload())
        assert f3.call_error(frames) is None, frames
        snapshot = gate.snapshot()
        broker_state = _broker_snapshot(broker)
        assert broker_state["requests"] == 1
        assert broker_state["pending"] == 0
        assert Decimal(snapshot["known_cost_usd"]) == Decimal(broker_state["spent_usd"])
        assert Decimal(snapshot["worst_case_held_usd"]) == 0
        assert (Decimal(snapshot["cost_view"]["committed_usd"])
                == Decimal(broker_state["committed_usd"]))
        view = snapshot["cost_view"]
        assert view["authority"] == "broker_reservation_settlement"
        assert view["reconciled_with_broker"] is True
        assert view["settled_reservations"] == 1
        reservation = view["reservations"][0]
        assert reservation["state"] == "SETTLED_KNOWN"
        assert reservation["broker_status"] == "OK"
        assert reservation["known_usd"] == broker_state["spent_usd"]
        assert all(view["invariants"].values())
        # The conservative hold existed at the pre-send moment (consume).
        assert gate.probes, "gate.consume was never observed"
        probe = gate.probes[0]
        assert probe["denial"] is None
        assert Decimal(probe["snapshot"]["worst_case_held_usd"]) > 0
        assert Decimal(probe["snapshot"]["known_cost_usd"]) == 0
        assert probe["snapshot"]["cost_view"]["reservations"][0]["state"] == "HELD"
        # Exactly one settlement; no replay/duplicate Broker message.
        assert broker_state["claims"]["total"] == 1
        assert fake.received_count() == 1
    finally:
        f3.close_all(broker, fake, attempts)


def test_no_usage_is_committed_conservatively_not_free(tmp_path) -> None:
    controller, broker, fake, attempts, gate = f3.start_controller(
        tmp_path, scenario="no_usage")
    try:
        frames = f3.collect(controller, f3.request_payload())
        assert f3.call_error(frames) is not None, frames
        snapshot = gate.snapshot()
        broker_state = _broker_snapshot(broker)
        assert broker_state["pending"] == 0
        assert Decimal(broker_state["spent_usd"]) > 0
        assert Decimal(snapshot["worst_case_held_usd"]) == 0
        assert Decimal(snapshot["known_cost_usd"]) == Decimal(broker_state["spent_usd"])
        reservation = snapshot["cost_view"]["reservations"][0]
        assert reservation["state"] == "SETTLED_CONSERVATIVE"
        assert reservation["broker_status"] == "FAILED"
        assert Decimal(reservation["known_usd"]) == Decimal(
            broker_state["spent_usd"])
        row = attempts.attempts()[0]
        assert row["state"] == "WORST_CASE_HELD"
    finally:
        f3.close_all(broker, fake, attempts)


def test_lost_settlement_ack_holds_then_reconciles_from_broker(tmp_path) -> None:
    controller, broker, fake, attempts, gate = f3.start_controller(tmp_path)
    real_completion = controller._completion_call
    lost = {"raised": False}

    def lossy_completion(op, reservation_id, usage, deadline):
        if not lost["raised"]:
            lost["raised"] = True
            raise BridgeError("SETTLEMENT_UNCERTAIN")
        return real_completion(op, reservation_id, usage, deadline)

    try:
        controller._completion_call = lossy_completion
        frames = f3.collect(controller, f3.request_payload())
        assert f3.call_error(frames) is not None, frames
        assert lost["raised"] is True

        # The send happened and the receipt is durable, but the Broker row is
        # still PENDING: the gate must hold conservatively, never FREE.
        snapshot = gate.snapshot()
        broker_state = _broker_snapshot(broker)
        assert broker_state["pending"] == 1
        assert Decimal(broker_state["reserved_usd"]) > 0
        assert Decimal(snapshot["known_cost_usd"]) == 0
        assert Decimal(snapshot["worst_case_held_usd"]) == Decimal(
            broker_state["reserved_usd"])
        assert snapshot["cost_view"]["reservations"][0]["state"] == "HELD"
        assert snapshot["cost_view"]["reservations"][0]["broker_status"] == "PENDING"
        assert fake.received_count() == 1

        # Recovery: a fresh observation of the same durable state settles from
        # the Broker and releases the hold exactly once.
        controller._completion_call = real_completion
        controller.reconcile_on_startup(str(tmp_path / "receipts"))
        broker_state = _broker_snapshot(broker)
        snapshot = gate.snapshot()
        assert broker_state["pending"] == 0
        assert broker_state["requests"] == 1
        assert Decimal(snapshot["worst_case_held_usd"]) == 0
        assert Decimal(snapshot["known_cost_usd"]) == Decimal(broker_state["spent_usd"])
        assert (Decimal(snapshot["cost_view"]["committed_usd"])
                == Decimal(broker_state["committed_usd"]))
        reservation = snapshot["cost_view"]["reservations"][0]
        assert reservation["state"] == "SETTLED_KNOWN"
        assert fake.received_count() == 1  # recovery never re-sends
        assert attempts.attempts()[0]["state"] == "SETTLED"
    finally:
        controller._completion_call = real_completion
        f3.close_all(broker, fake, attempts)


def test_replay_does_not_add_hold_or_second_settlement(tmp_path) -> None:
    controller, broker, fake, attempts, gate = f3.start_controller(tmp_path)
    try:
        assert f3.call_error(f3.collect(controller, f3.request_payload())) is None
        before_gate = gate.snapshot()
        before_broker = _broker_snapshot(broker)
        before_receipts = fake.received_count()

        frames = f3.collect(controller, f3.request_payload())
        assert f3.call_error(frames) == "ATTEMPT_ALREADY_STARTED", frames

        after_gate = gate.snapshot()
        after_broker = _broker_snapshot(broker)
        assert Decimal(after_gate["known_cost_usd"]) == Decimal(
            before_gate["known_cost_usd"])
        assert Decimal(after_gate["worst_case_held_usd"]) == Decimal(
            before_gate["worst_case_held_usd"])
        assert after_gate["sends_authorized"] == before_gate["sends_authorized"]
        assert after_gate["issued"] == before_gate["issued"]
        assert after_gate["cost_view"]["reservations"] == \
            before_gate["cost_view"]["reservations"]
        assert after_broker["requests"] == before_broker["requests"] == 1
        assert after_broker["spent_usd"] == before_broker["spent_usd"]
        assert fake.received_count() == before_receipts == 1
    finally:
        f3.close_all(broker, fake, attempts)


def test_broker_refusal_adds_no_hold(tmp_path) -> None:
    controller, broker, fake, attempts, gate = f3.start_controller(
        tmp_path, broker_options={"per_call_usd": "0.000001"})
    try:
        frames = f3.collect(controller, f3.request_payload())
        assert f3.call_error(frames) is not None, frames
        snapshot = gate.snapshot()
        broker_state = _broker_snapshot(broker)
        assert broker_state["requests"] == 0
        assert Decimal(snapshot["known_cost_usd"]) == 0
        assert Decimal(snapshot["worst_case_held_usd"]) == 0
        assert snapshot["cost_view"]["reservations"] == []
        assert fake.received_count() == 0
    finally:
        f3.close_all(broker, fake, attempts)


def _seed_reservation(controller: TrustedController, *, call_id: str,
                      input_tokens: int = 100, output_tokens: int = 64) -> tuple[str, str]:
    reply = controller.broker.reserve(
        task_id="task-g4f3-crash", route_id=f3.ROUTE, model=f3.MODEL,
        input_tokens=input_tokens, output_tokens=output_tokens, call_id=call_id)
    assert reply.get("ok") is True, reply
    reservation_id = reply["reservation_id"]
    reserved_cost = reply["reservation"]["cost_usd"]
    return reservation_id, reserved_cost


def test_crash_after_reserve_reconcile_holds_broker_reserved(tmp_path) -> None:
    controller, broker, fake, attempts, gate = f3.start_controller(tmp_path)
    attempts2 = None
    try:
        call_id = "call-" + "12" * 24
        reservation_id, reserved_cost = _seed_reservation(controller, call_id=call_id)
        controller.attempts.record_intent(
            scope_id=f3.SCOPE, call_id=call_id, reservation_id=reservation_id,
            prepared_digest="33" * 32, payload_digest="44" * 32, payload_length=11)
        assert _broker_snapshot(broker)["pending"] == 1

        # New process: fresh gate + fresh journal handle, same durable Broker.
        gate2 = f3.make_gate()
        attempts2 = AttemptJournal(tmp_path / "attempts.sqlite3")
        controller2 = TrustedController(
            controller.admission, broker=broker, fake=fake, attempts=attempts2,
            expected_uid=65534, register_admission=False, dispatch_gate=gate2)
        controller2.reconcile_on_startup(str(tmp_path / "receipts"))

        snapshot = gate2.snapshot()
        broker_state = _broker_snapshot(broker)
        assert Decimal(snapshot["worst_case_held_usd"]) == Decimal(reserved_cost)
        assert Decimal(snapshot["known_cost_usd"]) == 0
        assert Decimal(snapshot["worst_case_held_usd"]) == Decimal(
            broker_state["reserved_usd"])
        assert snapshot["cost_view"]["reservations"][0]["held_source"] == "broker_status"
        assert fake.received_count() == 0
        assert attempts2.intent_for_call(call_id)["state"] == "HELD_UNCERTAIN"

        # Recovery later mirrors the Broker's terminal fail exactly once.
        deadline = time.monotonic() + 5
        reply = controller2._broker_fail(reservation_id=reservation_id,
                                         usage=None, deadline=deadline)
        controller2._record_gate_settlement(reply, reservation_id=reservation_id,
                                            source="broker_completion")
        snapshot = gate2.snapshot()
        broker_state = _broker_snapshot(broker)
        assert Decimal(snapshot["worst_case_held_usd"]) == 0
        assert Decimal(snapshot["known_cost_usd"]) == Decimal(broker_state["spent_usd"])
        assert Decimal(snapshot["known_cost_usd"]) > 0
        assert snapshot["cost_view"]["reservations"][0]["state"] == \
            "SETTLED_CONSERVATIVE"
        assert fake.received_count() == 0
    finally:
        f3.close_all(attempts2, broker, fake, attempts)


def test_crash_after_attempt_reconcile_holds_broker_reserved(tmp_path) -> None:
    controller, broker, fake, attempts, gate = f3.start_controller(tmp_path)
    attempts2 = None
    try:
        call_id = "call-" + "13" * 24
        reservation_id, reserved_cost = _seed_reservation(controller, call_id=call_id)
        controller.attempts.begin_attempt(
            scope_id=f3.SCOPE, call_id=call_id, reservation_id=reservation_id,
            prepared_digest="33" * 32, payload_digest="44" * 32,
            payload_length=11, run_id=f3.RUN_ID, logical_step=0, mode="echo",
            input_bound_kind="utf8_bytes_upper_bound", input_bound_tokens=100,
            fee_policy_version="v1")

        gate2 = f3.make_gate()
        attempts2 = AttemptJournal(tmp_path / "attempts.sqlite3")
        controller2 = TrustedController(
            controller.admission, broker=broker, fake=fake, attempts=attempts2,
            expected_uid=65534, register_admission=False, dispatch_gate=gate2)
        controller2.reconcile_on_startup(str(tmp_path / "receipts"))

        snapshot = gate2.snapshot()
        assert Decimal(snapshot["worst_case_held_usd"]) == Decimal(reserved_cost)
        assert Decimal(snapshot["known_cost_usd"]) == 0
        assert snapshot["cost_view"]["reservations"][0]["broker_status"] == "PENDING"
        row = attempts2.attempt_for_call(call_id)
        assert row["state"] == "SETTLEMENT_UNCERTAIN"
        assert fake.received_count() == 0
        assert _broker_snapshot(broker)["pending"] == 1
    finally:
        f3.close_all(attempts2, broker, fake, attempts)


def test_settlement_relay_is_never_the_request_outcome(tmp_path) -> None:
    """A recording failure in the view must not change a successful request."""
    controller, broker, fake, attempts, gate = f3.start_controller(tmp_path)
    try:
        def broken_recorder(**_kwargs):
            raise RuntimeError("view broken")

        gate.record_broker_settlement = broken_recorder  # type: ignore[assignment]
        frames = f3.collect(controller, f3.request_payload())
        assert f3.call_error(frames) is None, frames
        assert _broker_snapshot(broker)["pending"] == 0
        # The view stayed conservative (hold not released) instead of claiming
        # a known cost it never received.
        snapshot = gate.snapshot()
        assert Decimal(snapshot["known_cost_usd"]) == 0
        assert Decimal(snapshot["worst_case_held_usd"]) > 0
    finally:
        f3.close_all(broker, fake, attempts)
