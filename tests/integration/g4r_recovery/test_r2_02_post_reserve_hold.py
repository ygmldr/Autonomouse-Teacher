"""R2-02: post-Reserve cancel/timeout stays PENDING/held, never FREE.

The request has a real Broker Reservation and a durable send intent when the
cancel/deadline hits a post-Reserve pre-send window.  The new observation
journals are additive evidence; they must not release the reservation, must not
create a second Attempt, and must not produce a Fake send.
"""
from __future__ import annotations

import threading
import time
from decimal import Decimal

from autoteacher_m0.bridge.request_lifecycle import (
    EVENT_CONTROLLER_ENTERED, EVENT_DEADLINE_BEFORE_CONTROLLER, EVENT_RECEIVED,
)

import g4f3_support as f3

import g4r_support as g4r


def _enable_delay(monkeypatch, hook: str, ms: int) -> None:
    monkeypatch.setenv("G3B_TEST_MODE", "1")
    monkeypatch.setenv("G3B_TEST_DELAY_HOOK", hook)
    monkeypatch.setenv("G3B_TEST_DELAY_MS", str(ms))


def _assert_held_not_free(controller, broker, fake, attempts, gate) -> dict:
    state = g4r.broker_snapshot(broker)
    # Real Broker reservation exists and is still pending: the full reserved
    # upper bound remains held (never released as a free request).
    assert state["requests"] == 1, state
    assert state["pending"] == 1, state
    assert Decimal(state["reserved_usd"]) > 0, state
    assert fake.received_count() == 0
    assert attempts.attempts() == []
    intents = attempts.pending_intents()
    assert len(intents) == 1, intents
    assert intents[0]["state"] == "HELD_UNCERTAIN", intents
    assert intents[0]["reason"].startswith("PRE_SEND_ABORT:"), intents
    snapshot = gate.snapshot()
    assert snapshot["sends_authorized"] == 0, snapshot
    assert Decimal(snapshot["known_cost_usd"]) == 0, snapshot
    return state


def test_r2_02_post_reserve_cancel_is_pending_held(tmp_path, monkeypatch) -> None:
    controller, broker, fake, attempts, gate = g4r.start_real_controller(
        tmp_path, deadline_ms=30000)
    _enable_delay(monkeypatch, "after_reserve_before_send", 800)
    payload = f3.request_payload()
    env = f3.envelope(payload)
    try:
        def cancel_later() -> None:
            time.sleep(0.2)
            controller.cancel(transport_id=env.transport_id, reason="host-cancel")

        thread = threading.Thread(target=cancel_later, daemon=True)
        thread.start()
        frames = []
        for item in controller.handle_envelope(env):
            frames.append({"kind": item.kind, "payload": item.payload})
        assert f3.call_error(frames) == "CANCELLED", frames
        _assert_held_not_free(controller, broker, fake, attempts, gate)
        # Request layer truthfully records controller entry but no deadline;
        # the post-Reserve cancel is a Controller/dispatch-layer fact.
        events = [row["event"] for row in g4r.lifecycle_events(tmp_path)]
        assert events == [EVENT_RECEIVED, EVENT_CONTROLLER_ENTERED], events
        rows = g4r.dispatch_rows(tmp_path)
        assert len(rows) == 1, rows
        assert rows[0]["reserved"] is True
        assert rows[0]["dispatched"] is False
        assert rows[0]["settled"] is False
        assert rows[0]["error_code"] in {"CANCELLED", "INTERNAL"}
    finally:
        f3.close_all(broker, fake, attempts)


def test_r2_02_post_reserve_timeout_is_pending_held(tmp_path, monkeypatch) -> None:
    controller, broker, fake, attempts, gate = g4r.start_real_controller(
        tmp_path, deadline_ms=800)
    _enable_delay(monkeypatch, "after_reserve_before_send", 2500)
    try:
        frames = f3.collect(controller, f3.request_payload())
        assert f3.call_error(frames) == "DEADLINE_EXCEEDED", frames
        deadline_row = g4r.lifecycle_events(
            tmp_path, event=EVENT_DEADLINE_BEFORE_CONTROLLER)[0]
        assert deadline_row["controller_entered"] is True
        assert deadline_row["stage"] == "reserved"
        # The transport answered before the worker finished, so wait for the
        # real pre-send abort to be durably classified.
        time.sleep(2.0)
        _assert_held_not_free(controller, broker, fake, attempts, gate)
        rows = g4r.dispatch_rows(tmp_path)
        assert len(rows) == 1, rows
        assert rows[0]["reserved"] is True
        assert rows[0]["dispatched"] is False
        assert rows[0]["settled"] is False
    finally:
        f3.close_all(broker, fake, attempts)


def test_r2_02_new_journal_never_triggers_release(tmp_path) -> None:
    """No new observation event by itself can release a held reservation."""
    controller, broker, fake, attempts, gate = g4r.start_real_controller(
        tmp_path, deadline_ms=30000)
    try:
        # A rejected second request after one real success must not touch the
        # reservation of the accepted request.
        first = f3.collect(controller, f3.request_payload())
        assert f3.call_error(first) is None, first
        replay = f3.collect(controller, f3.request_payload())
        assert f3.call_error(replay) in {"ATTEMPT_ALREADY_STARTED", "BUDGET_DENIED"}
        state = g4r.broker_snapshot(broker)
        assert state["requests"] == 1
        assert state["pending"] == 0
        # A protocol rejection is request-layer only: no dispatch row and no
        # dispatch_seq is fabricated for it.
        bad = dict(f3.request_payload())
        bad["purpose"] = "title"
        frames = f3.collect(controller, bad)
        assert f3.call_error(frames) == "BAD_TYPE"
        rows = g4r.dispatch_rows(tmp_path)
        protocol_rows = [row for row in rows if row.get("request_level_only")]
        assert protocol_rows, rows
        assert all(row["dispatch_seq"] is None for row in protocol_rows)
        assert all(row["reserved"] is False for row in protocol_rows)
    finally:
        f3.close_all(broker, fake, attempts)
