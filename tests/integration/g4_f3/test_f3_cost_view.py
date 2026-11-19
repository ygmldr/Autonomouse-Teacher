"""G4-F3: TrustedSendGate conservative cost view semantics (host, no Key).

Every assertion here is about the *view*: the Broker remains the only cost
authority and none of these tests can charge or refund anything.
"""
from __future__ import annotations

import threading
from decimal import Decimal

import pytest

from autoteacher_m0.security.egress import (
    AttemptState,
    ClaimResult,
    EgressBoundary,
    EgressViolation,
    REAL_ROUTE_TEMPLATE,
    SyntheticSendBudget,
    TrustedEgressTransport,
)
import g4c_support as g4c

RESERVATION = g4c.RESERVATION


def _authorize(gate, *, step: int = 0, reservation: str = RESERVATION, **kwargs):
    prepared = g4c.make_prepared(step=step)
    return g4c.authorize(gate, prepared, reservation=reservation, **kwargs)


def _decimals(snapshot: dict) -> tuple[Decimal, Decimal]:
    return (Decimal(snapshot["known_cost_usd"]),
            Decimal(snapshot["worst_case_held_usd"]))


def test_authorize_holds_a_positive_conservative_bound() -> None:
    gate = g4c.make_gate()
    assert _decimals(gate.snapshot()) == (Decimal("0"), Decimal("0"))

    _authorize(gate, worst_case_usd="0.003933")
    snapshot = gate.snapshot()
    known, held = _decimals(snapshot)
    assert known == 0
    assert held == Decimal("0.003933")  # Broker reserved_cost copy
    view = snapshot["cost_view"]
    assert view["schema"] == "m0.g4c.cost-view.v1"
    assert view["authority"] == "broker_reservation_settlement"
    assert view["role"] == "conservative_read_only_view"
    assert view["billing_authority"] is False
    assert view["scope"] == "process_local"
    assert view["unresolved_reservations"] == 1
    assert view["reservations"][0]["state"] == "HELD"
    assert view["reservations"][0]["held_source"] == "broker_reserved_cost"
    assert view["reservations"][0]["broker_status"] == "PENDING"
    assert all(view["invariants"].values()), view["invariants"]


def test_authorize_without_broker_bound_uses_the_budget_ceiling() -> None:
    gate = g4c.make_gate()
    _authorize(gate)
    snapshot = gate.snapshot()
    assert Decimal(snapshot["worst_case_held_usd"]) == gate.budget.hard_call_usd
    assert snapshot["cost_view"]["reservations"][0]["held_source"] == "gate_budget_bound"


def test_authorize_denial_adds_no_hold() -> None:
    gate = g4c.make_gate()
    with pytest.raises(EgressViolation) as exc:
        _authorize(gate, estimated_cost_usd="10.01")
    assert "PER_CALL_BUDGET_EXCEEDED" in exc.value.reasons
    snapshot = gate.snapshot()
    assert _decimals(snapshot) == (Decimal("0"), Decimal("0"))
    assert snapshot["cost_view"]["reservations"] == []


def test_consume_keeps_the_hold_until_a_broker_terminal_state() -> None:
    gate = g4c.make_gate()
    prepared = g4c.make_prepared()
    authorization = g4c.authorize(gate, prepared, worst_case_usd="0.003933")
    payload = g4c.make_payload(prepared)
    assert gate.consume(authorization, payload_bytes=payload) is None
    snapshot = gate.snapshot()
    assert _decimals(snapshot) == (Decimal("0"), Decimal("0.003933"))
    assert snapshot["cost_view"]["reservations"][0]["held_source"] == "consume"
    assert snapshot["consumed"] == 1

    verdict = gate.record_broker_settlement(
        reservation_id=RESERVATION, broker_status="OK", cost_usd="0.001013")
    assert verdict == "SETTLED"
    snapshot = gate.snapshot()
    assert _decimals(snapshot) == (Decimal("0.001013"), Decimal("0"))
    view = snapshot["cost_view"]
    assert view["settled_reservations"] == 1
    assert view["unresolved_reservations"] == 0
    assert view["reservations"][0]["state"] == "SETTLED_KNOWN"
    assert view["reservations"][0]["known_source"] == "broker_completion"
    assert all(view["invariants"].values())


def test_broker_pending_refines_the_hold_and_never_double_counts() -> None:
    gate = g4c.make_gate()
    _authorize(gate, worst_case_usd="0.200000")
    status = {"ok": True, "found": True, "reservation_id": RESERVATION,
              "status": "PENDING", "reserved_cost": "0.003933",
              "cost": "0.003933", "call_id": g4c.make_prepared().call_id}
    assert gate.record_broker_status(status) == "HELD"
    assert _decimals(gate.snapshot()) == (Decimal("0"), Decimal("0.003933"))
    assert gate.record_broker_status(dict(status)) == "HELD"
    snapshot = gate.snapshot()
    assert _decimals(snapshot) == (Decimal("0"), Decimal("0.003933"))
    assert snapshot["cost_view"]["reconciled_with_broker"] is True
    assert snapshot["cost_view"]["reservations"][0]["held_source"] == "broker_status"


def test_terminal_settlement_is_counted_exactly_once() -> None:
    gate = g4c.make_gate()
    _authorize(gate, worst_case_usd="0.003933")
    assert gate.record_broker_settlement(
        reservation_id=RESERVATION, broker_status="OK",
        cost_usd="0.001013") == "SETTLED"
    first = gate.snapshot()
    assert gate.record_broker_settlement(
        reservation_id=RESERVATION, broker_status="OK",
        cost_usd="0.001013") == "ALREADY_RECORDED"
    second = gate.snapshot()
    assert _decimals(first) == _decimals(second) == (Decimal("0.001013"), Decimal("0"))
    # A conflicting amount/status never mutates the archived authority copy.
    assert gate.record_broker_settlement(
        reservation_id=RESERVATION, broker_status="OK",
        cost_usd="0.002000") == "BROKER_SETTLEMENT_CONFLICT"
    assert gate.record_broker_settlement(
        reservation_id=RESERVATION, broker_status="FAILED",
        cost_usd="0.001013") == "BROKER_SETTLEMENT_CONFLICT"
    after = gate.snapshot()
    assert _decimals(after) == (Decimal("0.001013"), Decimal("0"))
    kinds = [event["kind"] for event in after["cost_view"]["events"]]
    assert "BROKER_SETTLEMENT_CONFLICT" in kinds


def test_failed_settlement_is_committed_known_cost_not_a_refund() -> None:
    gate = g4c.make_gate()
    _authorize(gate, worst_case_usd="0.003933")
    assert gate.record_broker_settlement(
        reservation_id=RESERVATION, broker_status="FAILED",
        cost_usd="0.003933") == "SETTLED"
    snapshot = gate.snapshot()
    assert _decimals(snapshot) == (Decimal("0.003933"), Decimal("0"))
    view = snapshot["cost_view"]["reservations"][0]
    assert view["state"] == "SETTLED_CONSERVATIVE"
    assert view["broker_status"] == "FAILED"


def test_missing_terminal_cost_keeps_the_hold() -> None:
    gate = g4c.make_gate()
    _authorize(gate, worst_case_usd="0.003933")
    assert gate.record_broker_settlement(
        reservation_id=RESERVATION, broker_status="OK",
        cost_usd=None) == "BROKER_COST_UNKNOWN"
    assert _decimals(gate.snapshot()) == (Decimal("0"), Decimal("0.003933"))
    assert gate.record_broker_status(
        {"ok": True, "found": True, "reservation_id": RESERVATION,
         "status": "OK", "reserved_cost": "0.003933", "cost": None}
    ) == "BROKER_COST_UNKNOWN"
    snapshot = gate.snapshot()
    assert _decimals(snapshot) == (Decimal("0"), Decimal("0.003933"))
    assert snapshot["cost_view"]["reservations"][0]["state"] == "HELD"


def test_unavailable_or_unknown_broker_status_never_releases() -> None:
    gate = g4c.make_gate()
    _authorize(gate, worst_case_usd="0.003933")
    assert gate.record_broker_status({"ok": False, "code": "BROKER_ERROR"}) == \
        "BROKER_STATUS_INVALID"
    assert gate.record_broker_status(
        {"ok": False, "code": "UNKNOWN_RESERVATION", "reservation_id": RESERVATION}
    ) == "BROKER_STATUS_UNAVAILABLE"
    assert gate.record_broker_status(
        {"ok": True, "found": True, "reservation_id": RESERVATION,
         "status": "SOMETHING_NEW", "reserved_cost": "0.003933"}
    ) == "BROKER_STATUS_UNKNOWN"
    snapshot = gate.snapshot()
    assert _decimals(snapshot) == (Decimal("0"), Decimal("0.003933"))
    assert snapshot["cost_view"]["reservations"][0]["broker_status"] == "PENDING"


def test_settled_reservation_cannot_be_reauthorized() -> None:
    gate = g4c.make_gate()
    _authorize(gate, worst_case_usd="0.003933")
    gate.record_broker_settlement(reservation_id=RESERVATION, broker_status="OK",
                                  cost_usd="0.001013")
    before = gate.snapshot()
    with pytest.raises(EgressViolation) as exc:
        _authorize(gate, step=1, worst_case_usd="0.003933")
    assert "RESERVATION_ALREADY_SETTLED" in exc.value.reasons
    after = gate.snapshot()
    assert _decimals(after) == _decimals(before)
    assert after["sends_authorized"] == before["sends_authorized"]
    assert after["issued"] == before["issued"]


def test_two_authorizations_before_settlement_hold_one_reservation_once() -> None:
    # G4-D epoch tests mint two tickets for one reservation; one Broker row must
    # still mean at most one held amount.
    gate = g4c.make_gate()
    _authorize(gate, step=0, worst_case_usd="0.003933")
    _authorize(gate, step=1, worst_case_usd="0.003933")
    snapshot = gate.snapshot()
    assert _decimals(snapshot) == (Decimal("0"), Decimal("0.003933"))
    assert len(snapshot["cost_view"]["reservations"]) == 1
    kinds = [event["kind"] for event in snapshot["cost_view"]["events"]]
    assert "RESERVATION_REUSED_BEFORE_SETTLEMENT" in kinds


def test_concurrent_authorize_never_oversells_or_double_holds() -> None:
    budget = SyntheticSendBudget(soft_total_usd=Decimal("0.002"),
                                 hard_total_usd=Decimal("0.005"),
                                 soft_call_usd=Decimal("0.0001"),
                                 hard_call_usd=Decimal("0.002"), max_sends=50)
    gate = g4c.make_gate(budget=budget)
    count = 8
    barrier = threading.Barrier(count)
    outcomes: list[str] = []
    lock = threading.Lock()

    def worker(index: int) -> None:
        barrier.wait()
        try:
            _authorize(gate, step=index, reservation=f"res-concurrent-{index}",
                       estimated_cost_usd="0.001", worst_case_usd="0.001")
            verdict = "AUTHORIZED"
        except EgressViolation as exc:
            verdict = "DENIED:" + ",".join(exc.reasons)
        with lock:
            outcomes.append(verdict)

    threads = [threading.Thread(target=worker, args=(index,))
               for index in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    authorized = [item for item in outcomes if item == "AUTHORIZED"]
    denied = [item for item in outcomes if item != "AUTHORIZED"]
    snapshot = gate.snapshot()
    # 0.005 / 0.001 => exactly five grants; the check and the hold are atomic.
    assert len(authorized) == 5, outcomes
    assert len(denied) == 3 and all("HARD_BUDGET_CEILING_EXCEEDED" in item
                                    for item in denied), outcomes
    assert _decimals(snapshot) == (Decimal("0"), Decimal("0.005"))
    assert len(snapshot["cost_view"]["reservations"]) == 5
    reservation_ids = {view["reservation_id"]
                       for view in snapshot["cost_view"]["reservations"]}
    assert len(reservation_ids) == 5
    assert all(snapshot["cost_view"]["invariants"].values())


def test_snapshot_totals_always_equal_the_view_sum() -> None:
    gate = g4c.make_gate()
    for index in range(3):
        _authorize(gate, step=index, reservation=f"res-sum-{index}",
                   worst_case_usd="0.003933")
    gate.record_broker_settlement(reservation_id="res-sum-1", broker_status="OK",
                                  cost_usd="0.001013")
    gate.record_broker_status({"ok": True, "found": True,
                               "reservation_id": "res-sum-2",
                               "status": "PENDING", "reserved_cost": "0.004000",
                               "cost": "0.004000"})
    snapshot = gate.snapshot()
    view = snapshot["cost_view"]
    known = sum(Decimal(item["known_usd"]) for item in view["reservations"])
    held = sum(Decimal(item["held_usd"]) for item in view["reservations"])
    assert Decimal(snapshot["known_cost_usd"]) == known
    assert Decimal(snapshot["worst_case_held_usd"]) == held
    assert Decimal(view["committed_usd"]) == known + held
    assert all(view["invariants"].values())
    assert view["reservations"] == sorted(view["reservations"],
                                          key=lambda item: item["reservation_id"])


def test_real_route_gate_denies_without_creating_a_hold() -> None:
    gate = g4c.make_gate(contract=REAL_ROUTE_TEMPLATE)
    with pytest.raises(EgressViolation) as exc:
        _authorize(gate)
    assert "REAL_ROUTE_BLOCKED_REQUIRES_HUMAN_VERIFICATION" in exc.value.reasons
    snapshot = gate.snapshot()
    assert _decimals(snapshot) == (Decimal("0"), Decimal("0"))
    assert snapshot["cost_view"]["reservations"] == []


class _AlwaysClaimer:
    def claim(self, request):
        return ClaimResult(True, "CLAIMED", (), {"call_id": request.call_id})


def _boundary_request():
    from autoteacher_m0.security.egress import EgressRequest

    return EgressRequest(logical_stream_id="s-f3", reservation_id="r-f3",
                         attempt_ordinal=1, route_id="opencode-go",
                         model="deepseek-v4.1-flash", request_digest="a" * 64,
                         call_id="call-" + "b" * 48)


def test_boundary_record_outcome_is_idempotent_and_never_zeroes_unknown() -> None:
    boundary = EgressBoundary(claimer=_AlwaysClaimer())
    request = _boundary_request()
    decision = boundary.claim_dispatch(request)
    assert decision.allowed and decision.permission is not None

    def provider(_request):
        return {"status": 200, "usage": None, "error": None}

    transport = TrustedEgressTransport(boundary, provider)
    outcome = transport.dispatch(request, decision.permission)
    assert outcome["state"] == AttemptState.BILLABLE_UNKNOWN.value
    stream = boundary.stream(request.logical_stream_id)
    held = stream.worst_case_held_usd
    assert held > 0
    # A replayed observation must not double the conservative hold.
    state = boundary.record_outcome(
        decision, usage=None, http_status=200, error_kind=None,
        worst_case_usd="0.003933")
    assert state is AttemptState.BILLABLE_UNKNOWN
    assert stream.worst_case_held_usd == held
    assert stream.provider_invocations == 1
