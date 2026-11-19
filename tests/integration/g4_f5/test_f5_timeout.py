"""G4-F5 timeout: pre-send deadline (no send) and post-send uncertain (held)."""
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


def test_pre_send_deadline_sends_nothing(tmp_path, monkeypatch) -> None:
    gate = f5.make_gate()
    controller, broker, fake, attempts, gate = f5.start_controller(
        tmp_path, gate=gate, deadline_ms=150, max_calls=8)
    real_prepare = controller._prepare_checked

    def slow_prepare(payload, step):
        import time
        time.sleep(0.4)  # real elapsed time; the deadline is real
        return real_prepare(payload, step)

    monkeypatch.setattr(controller, "_prepare_checked", slow_prepare)
    try:
        frames = f3.collect(controller, f3.request_payload())
        assert f3.call_error(frames) == "DEADLINE_EXCEEDED", frames
        state = _broker_snapshot(broker)
        assert state["requests"] == 0
        assert state["reserved_usd"] == "0"
        assert fake.received_count() == 0
        assert attempts.attempts() == []
        assert attempts.pending_intents() == []
        snapshot = gate.snapshot()
        assert snapshot["sends_authorized"] == 0
        assert snapshot["worst_case_held_usd"] == "0"
        assert snapshot["known_cost_usd"] == "0"
    finally:
        f3.close_all(broker, fake, attempts)


def test_post_send_timeout_is_uncertain_held_and_never_resent(tmp_path) -> None:
    gate = f5.make_gate()
    controller, broker, fake, attempts, gate = f5.start_controller(
        tmp_path, gate=gate, scenario="slow_usage", deadline_ms=800,
        max_calls=8)
    try:
        frames = f3.collect(controller, f3.request_payload())
        assert f3.call_error(frames) == "DEADLINE_EXCEEDED", frames
        # The Fake really received the bytes (receipt-first, then it stalls).
        assert fake.received_count() == 1
        state = _broker_snapshot(broker)
        assert state["requests"] == 1
        assert state["pending"] == 1
        assert Decimal(state["reserved_usd"]) > 0
        assert Decimal(state["spent_usd"]) == 0
        rows = attempts.attempts()
        assert len(rows) == 1
        assert rows[0]["state"] == "SETTLEMENT_UNCERTAIN"
        assert rows[0]["receipt_id"] is None
        snapshot = gate.snapshot()
        assert Decimal(snapshot["worst_case_held_usd"]) == Decimal(
            state["reserved_usd"])
        assert snapshot["known_cost_usd"] == "0"
        assert snapshot["cost_view"]["reservations"][0]["state"] == "HELD"

        # A retry policy must not auto-resend: same identity is refused and the
        # Fake counter does not move.
        replay = f3.collect(controller, f3.request_payload())
        assert f3.call_error(replay) in {"ATTEMPT_ALREADY_STARTED",
                                         "BUDGET_DENIED"}, replay
        assert fake.received_count() == 1
        assert _broker_snapshot(broker)["requests"] == 1

        # Recovery from the durable receipt may settle (Broker is authority),
        # but it can never be free and never re-enters the Fake.
        gate2 = f5.make_gate()
        attempts2 = AttemptJournal(tmp_path / "attempts.sqlite3")
        controller2 = TrustedController(
            controller.admission, broker=broker, fake=fake, attempts=attempts2,
            expected_uid=65534, register_admission=False, dispatch_gate=gate2)
        controller2.reconcile_on_startup(str(tmp_path / "receipts"))
        recovery = gate2.snapshot()
        assert fake.received_count() == 1
        if recovery["cost_view"]["reservations"]:
            reservation = recovery["cost_view"]["reservations"][0]
            assert reservation["broker_status"] in {"PENDING", "OK", "FAILED"}
            if reservation["broker_status"] == "PENDING":
                assert Decimal(recovery["worst_case_held_usd"]) > 0
            else:
                assert Decimal(recovery["known_cost_usd"]) > 0
                assert recovery["worst_case_held_usd"] == "0"
        assert _broker_snapshot(broker)["requests"] == 1
        assert len(attempts2.attempts()) == 1
    finally:
        f3.close_all(broker, fake, attempts)


def test_revocation_then_timeout_never_marks_free(tmp_path) -> None:
    """A revoked pre-send window plus a deadline still never yields FREE."""
    path = f5.revocation_path(tmp_path)
    f5.write_revocation(path, revoked=False)
    gate = f5.RevokeOnAuthorizeGate(path)

    controller, broker, fake, attempts, gate = f5.start_controller(
        tmp_path, gate=gate, deadline_ms=30000, max_calls=8)
    try:
        frames = f3.collect(controller, f3.request_payload())
        assert f3.call_error(frames) == "ADMISSION_SELF_AUTH_DENIED", frames
        state = _broker_snapshot(broker)
        assert state["pending"] == 1
        snapshot = gate.snapshot()
        assert snapshot["worst_case_held_usd"] == "0"
        assert snapshot["known_cost_usd"] == "0"
        # Broker still reserves the full conservative amount: not free.
        assert Decimal(state["reserved_usd"]) > 0
        assert Decimal(state["committed_usd"]) > 0
        assert fake.received_count() == 0
    finally:
        f3.close_all(broker, fake, attempts)
