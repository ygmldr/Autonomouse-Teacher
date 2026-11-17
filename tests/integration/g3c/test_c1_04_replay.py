"""G3-C C1-04: request replay / business-identity conflicts never send twice."""
from __future__ import annotations
from pathlib import Path

from autoteacher_m0.bridge.controller import broker_protocol_code
from test_c1_03_admission import (
    ROUTE, MODEL, collect, error_code, make_harness, payload,
)


def _first_success(tmp_path: Path):
    harness = make_harness(tmp_path)
    frames = collect(harness.controller, payload())
    assert error_code(frames) is None, frames
    rows = harness.attempts_rows()
    assert len(rows) == 1
    return harness, rows[0]


def test_c1_04a_same_request_on_new_transport_is_rejected_without_send(
        tmp_path: Path) -> None:
    harness, row = _first_success(tmp_path)
    try:
        before = harness.snapshot()
        replay = collect(harness.controller, payload(), transport_id="tr-" + "c" * 32)
        assert error_code(replay) == "ATTEMPT_ALREADY_STARTED", replay
        assert harness.receipt_count() == 1
        after = harness.snapshot()
        assert after["requests"] == before["requests"] == 1
        assert after["claims"]["total"] == 1
        assert harness.attempts_rows()[0]["state"] == "SETTLED"
        assert harness.attempts.attempt_for_call(row["call_id"])["state"] == "SETTLED"
    finally:
        harness.close()


def test_c1_04b_same_call_different_digest_maps_to_frozen_broker_code(
        tmp_path: Path) -> None:
    harness = make_harness(tmp_path)
    try:
        call_id = "call-" + "7" * 48
        reserved = harness.broker.reserve(
            task_id="g3b-task", route_id=ROUTE, model=MODEL,
            input_tokens=100, output_tokens=50, call_id=call_id)
        assert reserved["ok"] and reserved["code"] == "RESERVED"
        reservation_id = reserved["reservation_id"]
        claimed = harness.broker.claim(
            call_id=call_id, reservation_id=reservation_id,
            request_digest="a" * 64, expected_route_id=ROUTE, expected_model=MODEL)
        assert claimed["ok"] and claimed["code"] == "CLAIMED"
        conflict = harness.broker.claim(
            call_id=call_id, reservation_id=reservation_id,
            request_digest="f" * 64, expected_route_id=ROUTE, expected_model=MODEL)
        assert conflict["code"] == "CALL_ID_CONFLICT", conflict
        mapped = broker_protocol_code(conflict["code"])
        assert mapped == broker_protocol_code("CALL_ID_CONFLICT")
        assert mapped != "UNKNOWN_FIELD"
        assert mapped in {"BROKER_CALL_ID_CONFLICT", "CLAIM_DENIED"}
        assert harness.receipt_count() == 0
        status = harness.status(reservation_id)
        assert status["status"] == "PENDING"
        snapshot = harness.snapshot()
        assert snapshot["requests"] == 1
        assert snapshot["claims"]["total"] == 1
    finally:
        harness.close()


def test_c1_04c_reservation_mismatch_is_rejected_by_real_broker(
        tmp_path: Path) -> None:
    harness = make_harness(tmp_path)
    try:
        call_id = "call-" + "8" * 48
        reserved = harness.broker.reserve(
            task_id="g3b-task", route_id=ROUTE, model=MODEL,
            input_tokens=100, output_tokens=50, call_id=call_id)
        reservation_id = reserved["reservation_id"]
        unknown = harness.broker.claim(
            call_id=call_id, reservation_id="r-does-not-exist",
            request_digest="b" * 64, expected_route_id=ROUTE, expected_model=MODEL)
        assert unknown["code"] == "UNKNOWN_RESERVATION"
        assert broker_protocol_code(unknown["code"]) == "CLAIM_DENIED"
        other_call = "call-" + "9" * 48
        reused = harness.broker.claim(
            call_id=other_call, reservation_id=reservation_id,
            request_digest="b" * 64, expected_route_id=ROUTE, expected_model=MODEL)
        assert reused["code"] in {"UNBOUND_CALL", "CALL_LINK_MISMATCH",
                                  "RESERVATION_ALREADY_CLAIMED", "CALL_ID_CONFLICT"}, reused
        assert broker_protocol_code(reused["code"]) == "CLAIM_DENIED"
        assert harness.receipt_count() == 0
    finally:
        harness.close()


def test_c1_04d_already_settled_is_not_overwritten(tmp_path: Path) -> None:
    harness, row = _first_success(tmp_path)
    try:
        status_before = harness.status(row["reservation_id"])
        repeat = harness.broker.settle(reservation_id=row["reservation_id"],
                                       usage={"inputTokens": 11, "cacheReadTokens": 2,
                                              "cacheWriteTokens": 0, "outputTokens": 5,
                                              "reasoningTokens": 0, "totalTokens": 18})
        assert repeat["code"] == "ALREADY_SETTLED"
        status_after = harness.status(row["reservation_id"])
        assert status_after["status"] == "OK"
        assert status_after["cost"] == status_before["cost"]
        assert status_after["input_used"] == status_before["input_used"]
        assert harness.attempts_rows()[0]["state"] == "SETTLED"
        assert harness.receipt_count() == 1
    finally:
        harness.close()


def test_c1_04e_claim_path_is_mandatory_and_not_bypassed(tmp_path: Path) -> None:
    harness = make_harness(tmp_path)
    try:
        calls = []
        original = harness.controller.boundary.claim_dispatch_for_request

        def spy(prepared, request, **kwargs):
            calls.append(request.call_id)
            return original(prepared, request, **kwargs)

        harness.controller.boundary.claim_dispatch_for_request = spy
        frames = collect(harness.controller, payload())
        assert error_code(frames) is None, frames
        assert len(calls) == 1
        replay = collect(harness.controller, payload())
        assert error_code(replay) == "ATTEMPT_ALREADY_STARTED"
        assert len(calls) == 1
        assert harness.receipt_count() == 1
        # A denied Boundary decision must produce zero Fake sends.
        class _Denied:
            allowed = False
            permission = None
            claim = None

        harness.controller.boundary.claim_dispatch_for_request = (
            lambda *args, **kwargs: _Denied())
        denied = collect(harness.controller, payload(
            messages=[{"role": "user", "content": "another request"}]))
        assert error_code(denied) is not None, denied
        assert harness.receipt_count() == 1
    finally:
        harness.close()


def test_c1_04f_distinct_business_request_is_allowed(tmp_path: Path) -> None:
    harness = make_harness(tmp_path)
    try:
        first = collect(harness.controller, payload())
        assert error_code(first) is None, first
        second = collect(harness.controller, payload(
            messages=[{"role": "user", "content": "a genuinely different request"}]),
            transport_id="tr-" + "d" * 32)
        assert error_code(second) is None, second
        assert harness.receipt_count() == 2
        assert harness.snapshot()["requests"] == 2
        rows = harness.attempts_rows()
        assert len(rows) == 2
        assert len({row["call_id"] for row in rows}) == 2
    finally:
        harness.close()
