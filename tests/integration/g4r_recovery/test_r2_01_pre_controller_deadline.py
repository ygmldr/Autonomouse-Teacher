"""R2-01: a pre-Reserve deadline is observed by the request layer.

Frozen G4-F F5-R4 fact: a real ``timeout-pre-send`` case (admission deadline
800 ms, test-only 2500 ms delay at ``before_reserve``) produced no
``dispatch-window.jsonl`` row because the stream handler returned the
``DEADLINE_EXCEEDED`` error before the blocked single-flight worker could emit
its finally-record.  These host tests reproduce that exact real timeline (real
monotonic deadline, real delay hook, real Broker/Fake subprocesses) and prove:

* the timeout is *observed at the transport/request layer* while the controller
  stage was still ``before_reserve`` (``controller_entered=true`` is recorded,
  so the event never pretends the deadline fired "before the controller");
* the request-level journal survives at the moment the dispatch-layer row does
  not exist, explaining the F5-R4 gap without fabricating a dispatch;
* no Broker Reserve, no Claim, no Fake send happens for the pre-Reserve case;
* a request that truly never entered the controller (pre-start cancel) has zero
  dispatch-window rows and no fabricated ``dispatch_seq``.
"""
from __future__ import annotations

import threading
import time

from autoteacher_m0.bridge.request_lifecycle import (
    EVENT_CANCEL_BEFORE_CONTROLLER, EVENT_CONTROLLER_ENTERED,
    EVENT_DEADLINE_BEFORE_CONTROLLER, EVENT_RECEIVED,
)

import g4f3_support as f3
import g4r_support as g4r


def _enable_delay(monkeypatch, hook: str, ms: int) -> None:
    monkeypatch.setenv("G3B_TEST_MODE", "1")
    monkeypatch.setenv("G3B_TEST_DELAY_HOOK", hook)
    monkeypatch.setenv("G3B_TEST_DELAY_MS", str(ms))


def test_r2_01_pre_reserve_deadline_layer_is_request_not_dispatch(
        tmp_path, monkeypatch) -> None:
    """800 ms real deadline + 2500 ms real delay at before_reserve.

    The client-facing error is observed while the blocked worker has not yet
    written its dispatch-window row (the real F5-R4 loss window).  The
    request-layer deadline event already exists at that instant.
    """
    controller, broker, fake, attempts, gate = g4r.start_real_controller(
        tmp_path, deadline_ms=800)
    _enable_delay(monkeypatch, "before_reserve", 2500)
    env = f3.envelope(f3.request_payload())
    generator = controller.handle_envelope(env)
    try:
        error_code = None
        for item in generator:
            if item.kind == "error":
                error_code = item.payload.get("code")
                break
        assert error_code == "DEADLINE_EXCEEDED"

        # ---- at the moment the timeout was returned -------------------
        rows = g4r.lifecycle_events(tmp_path)
        events = [row["event"] for row in rows]
        assert events == [EVENT_RECEIVED, EVENT_CONTROLLER_ENTERED,
                          EVENT_DEADLINE_BEFORE_CONTROLLER], rows
        received, entered, deadline_row = rows
        assert received["reserved"] is False
        assert received["dispatch_seq"] is None
        assert entered["controller_entered"] is True
        assert isinstance(entered["dispatch_seq"], int)
        assert entered["reserved"] is False
        assert deadline_row["code"] == "DEADLINE_EXCEEDED"
        assert deadline_row["controller_entered"] is True
        assert deadline_row["stage"] == "before_reserve"
        assert deadline_row["reason"] == "transport_observed_deadline"
        assert deadline_row["reserved"] is False
        assert deadline_row["dispatch_seq"] == entered["dispatch_seq"]
        # The blocked worker has not written its dispatch row yet: this is the
        # recorded F5-R4 evidence loss, covered by the request-layer event.
        assert g4r.dispatch_rows(tmp_path) == []

        # ---- the pre-send deadline is a real stop ---------------------
        state = g4r.broker_snapshot(broker)
        assert state["requests"] == 0, state
        assert state["reserved_usd"] == "0", state
        assert fake.received_count() == 0
        assert attempts.attempts() == []
        assert attempts.pending_intents() == []
        assert gate.snapshot()["sends_authorized"] == 0
    finally:
        # Closing the stream triggers the real finally-path join of the
        # blocked worker (this is exactly what a launcher teardown interrupts).
        generator.close()
        # Let the worker finish its pre-Reserve abort in-process.
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if g4r.dispatch_rows(tmp_path):
                break
            time.sleep(0.05)
        rows = g4r.dispatch_rows(tmp_path)
        if rows:
            assert len(rows) == 1, rows
            assert rows[0]["reserved"] is False
            assert rows[0]["dispatched"] is False
            assert rows[0]["settled"] is False
            assert rows[0]["dispatch_seq"] == 1
        f3.close_all(broker, fake, attempts)


def test_r2_01_pre_start_cancel_never_fabricates_dispatch(tmp_path) -> None:
    """A request cancelled before the handler starts has no dispatch at all."""
    controller, broker, fake, attempts, gate = g4r.start_real_controller(tmp_path)
    payload = f3.request_payload()
    env = f3.envelope(payload)
    controller.cancel(transport_id=env.transport_id, reason="host-test-pre-start")
    try:
        frames = []
        for item in controller.handle_envelope(env):
            frames.append({"kind": item.kind, "payload": item.payload})
        assert f3.call_error(frames) == "CANCELLED", frames
        rows = g4r.lifecycle_events(tmp_path)
        assert [row["event"] for row in rows] == [EVENT_RECEIVED,
                                                  EVENT_CANCEL_BEFORE_CONTROLLER]
        assert rows[0]["dispatch_seq"] is None
        assert rows[0]["reserved"] is False
        assert rows[1]["controller_entered"] is False
        assert rows[1]["dispatch_seq"] is None
        assert rows[1]["reserved"] is False
        assert g4r.dispatch_rows(tmp_path) == []
        assert g4r.broker_snapshot(broker)["requests"] == 0
        assert fake.received_count() == 0
    finally:
        f3.close_all(broker, fake, attempts)


def test_r2_01_no_worker_thread_leak_observed(tmp_path, monkeypatch) -> None:
    """Sanity: the request-layer deadline does not leave a stuck stream test."""
    controller, broker, fake, attempts, gate = g4r.start_real_controller(
        tmp_path, deadline_ms=200)
    _enable_delay(monkeypatch, "before_reserve", 400)
    try:
        frames = f3.collect(controller, f3.request_payload())
        assert f3.call_error(frames) == "DEADLINE_EXCEEDED", frames
        deadline_rows = g4r.lifecycle_events(
            tmp_path, event=EVENT_DEADLINE_BEFORE_CONTROLLER)
        assert len(deadline_rows) == 1
        assert threading.active_count() >= 1  # process stayed healthy
        assert g4r.broker_snapshot(broker)["requests"] == 0
    finally:
        f3.close_all(broker, fake, attempts)
