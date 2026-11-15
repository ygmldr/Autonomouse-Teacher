"""G2-EGRESS/Integration: real SQLite + real stdio Broker + FakeProvider loop.

No sockets, credentials, network, real provider or Live unlock. FakeProvider is
an in-process scripted synthetic fixture; TrustedEgressProvenance is a
same-process capability (V-G1-3), not cryptographic provenance. Local claim is
one-shot local send authorization, NOT remote exactly-once.
"""
from __future__ import annotations

import contextlib
import json
import signal
import subprocess
import sys

import pytest

from autoteacher_m0.accounting import (
    BudgetLedger, BudgetLimits, ProviderObservation, deliver_observation, derive_call_id,
)
from autoteacher_m0.accounting.observation import issue_trusted_egress_provenance
from autoteacher_m0.security.egress import (
    ClaimResult, EgressBoundary, EgressPolicy, EgressRequest,
)

ROUTE = "offline-test-only"
MODEL = "fixture-v1"
SCOPE = "fixed-offline-scope"
DIGEST = "a" * 64
REASONING_POLICY = "inclusive"


def make_config(tmp_path):
    return {"v": 1, "synthetic": True, "db_path": str(tmp_path / "ledger.sqlite3"),
            "scope_id": SCOPE, "max_messages": 32,
            "limits": {"soft_usd": "3", "hard_usd": "10", "per_call_usd": "0.20",
                       "max_requests": 50, "max_input_tokens": 2500000,
                       "max_output_tokens": 600000, "max_steps": 8, "max_retries": 1},
            "routes": [{"route_id": ROUTE, "model": MODEL,
                        "price": {"version": "fixture-v1", "input_per_million": "1",
                                  "output_per_million": "2", "cached_input_per_million": "0.5",
                                  "source": "synthetic fixture", "captured_at": "2026-11-13"},
                        "known_extra_fee_usd": "0.001",
                        "usage_policy": {"cache_write": "input_rate",
                                         "reasoning": "included_in_output"}}]}


def setup(tmp_path):
    config = make_config(tmp_path)
    path = tmp_path / "startup.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    limits = BudgetLimits(soft_usd="3", hard_usd="10", per_call_usd="0.20",
                          max_requests=50, max_input_tokens=2500000,
                          max_output_tokens=600000, max_steps=8, max_retries=1)
    ledger = BudgetLedger(tmp_path / "ledger.sqlite3", scope_id=SCOPE, limits=limits)
    return path, ledger


def broker_argv(path):
    return [sys.executable, "-B", "-m", "autoteacher_m0.accounting.broker",
            "--config", str(path)]


def start_broker(path):
    return subprocess.Popen(broker_argv(path), stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def send(process, message):
    process.stdin.write(json.dumps(message) + "\n")
    process.stdin.flush()
    return json.loads(process.stdout.readline())


def run(path, messages):
    data = "".join(json.dumps(message) + "\n" for message in messages)
    process = subprocess.run(broker_argv(path), input=data, text=True,
                             capture_output=True, timeout=15)
    assert process.returncode == 0, (process.returncode, process.stdout, process.stderr)
    return [json.loads(line) for line in process.stdout.splitlines()]


def stop(process, *, kill=False):
    try:
        if kill:
            process.send_signal(signal.SIGKILL)
        else:
            process.stdin.close()
        process.wait(timeout=10)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)


class StdioBrokerClaimer:
    """Real stdio Broker claim client (one subprocess per loop)."""

    def __init__(self, path):
        self.process = start_broker(path)
        self.sequence = 0

    def claim(self, request: EgressRequest) -> ClaimResult:
        self.sequence += 1
        reply = send(self.process, {
            "v": 1, "id": f"claim-{self.sequence}", "op": "claim",
            "call_id": request.call_id, "reservation_id": request.reservation_id,
            "request_digest": request.request_digest})
        if reply.get("ok") and reply.get("code") == "CLAIMED":
            return ClaimResult(True, "CLAIMED", (), reply.get("claim"))
        return ClaimResult(False, reply.get("code", "CLAIM_FAILED"), (), reply.get("claim"))

    def close(self):
        stop(self.process)


class BrokerDownClaimer:
    def claim(self, request: EgressRequest) -> ClaimResult:
        return ClaimResult(False, "BROKER_UNAVAILABLE", ("claim transport failed",))


@contextlib.contextmanager
def claim_boundary(path):
    claimer = StdioBrokerClaimer(path)
    boundary = EgressBoundary(
        EgressPolicy(approved_routes=frozenset({(ROUTE, MODEL)})), claimer=claimer)
    try:
        yield boundary, claimer
    finally:
        claimer.close()


class FakeProvider:
    """Scripted synthetic provider; never opens a socket or contacts a model."""

    synthetic = True
    scenarios = {
        "ok_usage": {"input": 7, "cache_read": 2, "cache_write": 3, "output": 3,
                     "reasoning": 1, "complete_or_uncertain": "AUTHORITATIVE",
                     "error_kind": "none"},
        "no_usage": {"input": None, "cache_read": None, "cache_write": None,
                     "output": None, "reasoning": None,
                     "complete_or_uncertain": "MISSING", "error_kind": "none",
                     "usage_raw_hash": None, "cost_source": "synthetic_fixture_cost"},
        "partial_usage": {"input": 7, "cache_read": None, "cache_write": None,
                          "output": None, "reasoning": None,
                          "complete_or_uncertain": "PARTIAL", "error_kind": "none"},
        "timeout": {"input": None, "cache_read": None, "cache_write": None,
                    "output": None, "reasoning": None,
                    "complete_or_uncertain": "UNKNOWN", "error_kind": "timeout",
                    "usage_raw_hash": None, "cost_source": "unknown"},
        "http_500": {"input": None, "cache_read": None, "cache_write": None,
                     "output": None, "reasoning": None,
                     "complete_or_uncertain": "UNKNOWN", "error_kind": "http_5xx",
                     "usage_raw_hash": None, "cost_source": "unknown"},
        "tampered_output": {"input": 7, "cache_read": 0, "cache_write": 0,
                            "output": 999_999, "reasoning": 0,
                            "complete_or_uncertain": "AUTHORITATIVE",
                            "error_kind": "none"},
    }

    def __init__(self):
        self.calls = 0
        self.network_attempts = 0

    def payload(self, scenario):
        if scenario not in self.scenarios:
            raise ValueError("unknown fake provider scenario")
        self.calls += 1
        payload = {"requested_route": ROUTE, "observed_route": ROUTE,
                   "model_reported": MODEL, "provider_request_id": "fixture-request-1",
                   "usage_raw_hash": "b" * 64, "input": None, "cache_read": None,
                   "cache_write": None, "output": None, "reasoning": None,
                   "cost_estimate": None, "cost_source": "synthetic_fixture_cost",
                   "error_kind": "none", "complete_or_uncertain": "AUTHORITATIVE"}
        payload.update(self.scenarios[scenario])
        return payload


def reserve_call(path, call_id, identity="reserve-1", *, with_call_id=True):
    message = {"v": 1, "id": identity, "op": "reserve", "task_id": "session-g2",
               "route_id": ROUTE, "model": MODEL, "purpose": "conversation",
               "input_tokens": 100, "output_tokens": 10, "retry": False}
    if with_call_id:
        message["call_id"] = call_id
    reply = run(path, [message])[0]
    return reply


def request_for(call_id, reservation_id, **overrides):
    base = {"logical_stream_id": "stream-g2", "reservation_id": reservation_id,
            "attempt_ordinal": 1, "route_id": ROUTE, "model": MODEL,
            "call_id": call_id, "request_digest": DIGEST}
    base.update(overrides)
    return EgressRequest(**base)


def deliver(ledger, call_id, provider, scenario, *, provenance=True):
    observation = ProviderObservation.from_mapping(provider.payload(scenario))
    trusted = (issue_trusted_egress_provenance(
        call_id=call_id, request_digest=DIGEST, observed_route=ROUTE, model_reported=MODEL)
        if provenance else None)
    return deliver_observation(ledger, call_id, observation,
                               reasoning_policy=REASONING_POLICY,
                               cache_discount_approved=False, provenance=trusted)


def snapshot(path):
    return run(path, [{"v": 1, "id": "snapshot-g2", "op": "snapshot"}])[0]["snapshot"]


# ---------------- INT-01: closed loop reserve -> claim -> provider -> observation -> settle
def test_int01_closed_loop_settles_once(tmp_path):
    path, ledger = setup(tmp_path)
    call = derive_call_id("run-int01", 0, 0, DIGEST)
    granted = reserve_call(path, call)
    assert granted["ok"] and granted["dispatch_allowed"]
    reservation = granted["reservation_id"]
    provider = FakeProvider()
    with claim_boundary(path) as (boundary, _claimer):
        decision = boundary.claim_dispatch(request_for(call, reservation))
        assert decision.allowed and decision.claim and decision.claim.claimed
        assert decision.call_id == call
        assert decision.legacy_egress_event_id.startswith("eg-")
        result = deliver(ledger, call, provider, "ok_usage")
    assert result["ok"] is True and result["code"] == "SETTLED", result
    state = snapshot(path)
    assert state["claims"] == {"total": 1, "pending": 0, "completed": 1}
    assert state["requests"] == 1 and state["pending"] == 0
    assert provider.network_attempts == 0


# ---------------- INT-02 / INT-03: non-empty fake reservation / unbound call => 0 dispatch
def test_int02_fake_reservation_never_dispatches(tmp_path):
    path, ledger = setup(tmp_path)
    call = derive_call_id("run-int02", 0, 0, DIGEST)
    with claim_boundary(path) as (boundary, _claimer):
        decision = boundary.claim_dispatch(request_for(call, "reservation-forged"))
        assert not decision.allowed
        assert any("CLAIM_REJECTED:UNKNOWN_RESERVATION" in reason
                   for reason in decision.reasons), decision.reasons
    assert snapshot(path)["claims"]["total"] == 0


def test_int03_unbound_call_never_dispatches(tmp_path):
    path, ledger = setup(tmp_path)
    call = derive_call_id("run-int03", 0, 0, DIGEST)
    granted = reserve_call(path, call, with_call_id=False)
    assert granted["ok"]
    with claim_boundary(path) as (boundary, _claimer):
        decision = boundary.claim_dispatch(request_for(call, granted["reservation_id"]))
        assert not decision.allowed
        assert any("CLAIM_REJECTED:UNBOUND_CALL" in reason
                   for reason in decision.reasons), decision.reasons
    assert snapshot(path)["claims"]["total"] == 0


# ---------------- INT-04 / INT-17: duplicate/second attempt never grants second dispatch
def test_int04_duplicate_claim_is_zero_dispatch(tmp_path):
    path, ledger = setup(tmp_path)
    call = derive_call_id("run-int04", 0, 0, DIGEST)
    reservation = reserve_call(path, call)["reservation_id"]
    with claim_boundary(path) as (boundary, _claimer):
        first = boundary.claim_dispatch(request_for(call, reservation))
        second = boundary.claim_dispatch(request_for(call, reservation))
        assert first.allowed and first.claim.claimed
        assert not second.allowed
        assert any("CLAIM_REJECTED:ALREADY_CLAIMED" in reason
                   for reason in second.reasons), second.reasons
    assert snapshot(path)["claims"] == {"total": 1, "pending": 1, "completed": 0}


def test_int17_second_call_for_same_reservation_is_rejected(tmp_path):
    path, ledger = setup(tmp_path)
    call = derive_call_id("run-int17", 0, 0, DIGEST)
    other = derive_call_id("run-int17", 0, 1, DIGEST)
    reservation = reserve_call(path, call)["reservation_id"]
    ledger.bind_call(other, reservation)  # bind both calls before claiming
    with claim_boundary(path) as (boundary, _claimer):
        assert boundary.claim_dispatch(request_for(call, reservation)).allowed
        second = boundary.claim_dispatch(request_for(other, reservation))
        assert not second.allowed
        assert any("CLAIM_REJECTED:RESERVATION_ALREADY_CLAIMED" in reason
                   for reason in second.reasons), second.reasons


# ---------------- INT-06 / INT-07 / INT-12 / INT-18: crash replay, digest conflict, broker down, restart
def test_int06_sigkill_restart_does_not_replay_dispatch(tmp_path):
    path, ledger = setup(tmp_path)
    call = derive_call_id("run-int06", 0, 0, DIGEST)
    reservation = reserve_call(path, call)["reservation_id"]
    claimer = StdioBrokerClaimer(path)
    proc = start_broker(path)
    reply = send(proc, {"v": 1, "id": "claim-1", "op": "claim", "call_id": call,
                        "reservation_id": reservation, "request_digest": DIGEST})
    assert reply["ok"] and reply["code"] == "CLAIMED"
    stop(proc, kill=True)
    claimer.close() if False else None  # keep separate client ownership explicit
    replay = send(start_broker(path), {"v": 1, "id": "claim-2", "op": "claim",
                                       "call_id": call, "reservation_id": reservation,
                                       "request_digest": DIGEST})
    assert replay["ok"] is False and replay["code"] == "ALREADY_CLAIMED"
    assert replay["dispatch_allowed"] is False
    assert snapshot(path)["claims"]["total"] == 1


def test_int07_same_call_different_digest_conflicts(tmp_path):
    path, ledger = setup(tmp_path)
    call = derive_call_id("run-int07", 0, 0, DIGEST)
    reservation = reserve_call(path, call)["reservation_id"]
    assert run(path, [{"v": 1, "id": "claim-1", "op": "claim", "call_id": call,
                       "reservation_id": reservation, "request_digest": DIGEST}])[0]["ok"]
    conflict = run(path, [{"v": 1, "id": "claim-2", "op": "claim", "call_id": call,
                           "reservation_id": reservation,
                           "request_digest": "c" * 64}])[0]
    assert conflict["ok"] is False and conflict["code"] == "CALL_ID_CONFLICT"
    assert conflict["dispatch_allowed"] is False
    assert snapshot(path)["claims"]["total"] == 1


def test_int12_broker_down_yields_zero_dispatch(tmp_path):
    path, ledger = setup(tmp_path)
    call = derive_call_id("run-int12", 0, 0, DIGEST)
    reservation = reserve_call(path, call)["reservation_id"]
    boundary = EgressBoundary(
        EgressPolicy(approved_routes=frozenset({(ROUTE, MODEL)})),
        claimer=BrokerDownClaimer())
    decision = boundary.claim_dispatch(request_for(call, reservation))
    assert not decision.allowed
    assert any("CLAIM_REJECTED:BROKER_UNAVAILABLE" in reason for reason in decision.reasons)
    assert snapshot(path)["claims"]["total"] == 0


def test_int18_restart_does_not_reduce_balance_or_claims(tmp_path):
    path, ledger = setup(tmp_path)
    call = derive_call_id("run-int18", 0, 0, DIGEST)
    reservation = reserve_call(path, call)["reservation_id"]
    before = snapshot(path)
    with claim_boundary(path) as (boundary, _claimer):
        assert boundary.claim_dispatch(request_for(call, reservation)).allowed
    after = snapshot(path)  # new broker process/restart
    assert after["claims"]["total"] == 1
    assert after["pending"] == 1
    assert after["spent_usd"] == before["spent_usd"]
    assert after["committed_usd"] == before["committed_usd"]


# ---------------- INT-09 / INT-10 / INT-11 / INT-13/14/15/16: egress and observation semantics
def test_int09_new_logical_step_gets_new_identity_and_claim(tmp_path):
    path, ledger = setup(tmp_path)
    first = derive_call_id("run-int09", 0, 0, DIGEST)
    second = derive_call_id("run-int09", 1, 0, DIGEST)
    assert first != second
    reservations = [reserve_call(path, first)["reservation_id"],
                    reserve_call(path, second, identity="reserve-2")["reservation_id"]]
    with claim_boundary(path) as (boundary, _claimer):
        assert boundary.claim_dispatch(request_for(first, reservations[0])).allowed
        assert boundary.claim_dispatch(request_for(
            second, reservations[1], attempt_ordinal=2)).allowed
    assert snapshot(path)["claims"]["total"] == 2


def test_int10_no_or_partial_usage_never_uses_zero(tmp_path):
    path, ledger = setup(tmp_path)
    for offset, scenario in enumerate(("no_usage", "partial_usage")):
        call = derive_call_id("run-int10", offset, 0, DIGEST)
        reservation = reserve_call(path, call, identity=f"reserve-{offset}")["reservation_id"]
        with claim_boundary(path) as (boundary, _claimer):
            assert boundary.claim_dispatch(request_for(call, reservation)).allowed
        result = deliver(ledger, call, FakeProvider(), scenario)
        assert result["ok"] is True and result["code"] == "WORST_CASE_HELD", result
        assert result["settlement"]["cost_usd"] != "0"
        state = snapshot(path)
        assert state["pending"] == 0
        assert float(state["spent_usd"]) > 0


def test_int11_route_path_method_mismatch_never_claims(tmp_path):
    path, ledger = setup(tmp_path)
    call = derive_call_id("run-int11", 0, 0, DIGEST)
    reservation = reserve_call(path, call)["reservation_id"]
    boundary = EgressBoundary(
        EgressPolicy(approved_routes=frozenset({(ROUTE, MODEL)})))
    for overrides, reason in [({"path": "/v1/chat/completions"}, "PATH_NOT_ALLOWED"),
                              ({"method": "GET"}, "METHOD_NOT_ALLOWED"),
                              ({"model": "fixture-v2"}, "ROUTE_MODEL_NOT_APPROVED")]:
        decision = boundary.claim_dispatch(request_for(call, reservation, **overrides))
        assert not decision.allowed and reason in decision.reasons
    assert snapshot(path)["claims"]["total"] == 0


def test_int13_14_observation_idempotent_and_conflict(tmp_path):
    path, ledger = setup(tmp_path)
    call = derive_call_id("run-int13", 0, 0, DIGEST)
    reservation = reserve_call(path, call)["reservation_id"]
    with claim_boundary(path) as (boundary, _claimer):
        assert boundary.claim_dispatch(request_for(call, reservation)).allowed
    first = deliver(ledger, call, FakeProvider(), "ok_usage")
    replay = deliver(ledger, call, FakeProvider(), "ok_usage")
    assert first["ok"] is True and first["duplicate"] is False
    assert replay["ok"] is True and replay["duplicate"] is True
    assert replay["code"] in {"SETTLED", "ALREADY_SETTLED"}
    with pytest.raises(ValueError):
        deliver(ledger, call, FakeProvider(), "no_usage")


def test_int15_forged_authoritative_never_settles(tmp_path):
    path, ledger = setup(tmp_path)
    call = derive_call_id("run-int15", 0, 0, DIGEST)
    reservation = reserve_call(path, call)["reservation_id"]
    with claim_boundary(path) as (boundary, _claimer):
        assert boundary.claim_dispatch(request_for(call, reservation)).allowed
    result = deliver(ledger, call, FakeProvider(), "ok_usage", provenance=False)
    assert result["ok"] is False and result["code"] == "UNAUTHORIZED_OBSERVATION"
    state = snapshot(path)
    assert state["pending"] == 1 and state["claims"]["pending"] == 1


def test_int16_tampered_output_is_not_silently_accepted(tmp_path):
    path, ledger = setup(tmp_path)
    call = derive_call_id("run-int16", 0, 0, DIGEST)
    reservation = reserve_call(path, call)["reservation_id"]
    with claim_boundary(path) as (boundary, _claimer):
        assert boundary.claim_dispatch(request_for(call, reservation)).allowed
    result = deliver(ledger, call, FakeProvider(), "tampered_output")
    assert result["ok"] is True
    assert result["settlement"]["reservation_exceeded"] is True
    state = snapshot(path)
    assert state["blocked"] is True or state["spent_usd"] != "0"


def test_int05_two_broker_processes_race_one_license(tmp_path):
    path, ledger = setup(tmp_path)
    call = derive_call_id("run-int05", 0, 0, DIGEST)
    reservation = reserve_call(path, call)["reservation_id"]
    first, second = start_broker(path), start_broker(path)
    try:
        for proc, identity in ((first, "claim-a"), (second, "claim-b")):
            proc.stdin.write(json.dumps({"v": 1, "id": identity, "op": "claim",
                                         "call_id": call, "reservation_id": reservation,
                                         "request_digest": DIGEST}) + "\n")
            proc.stdin.flush()
        replies = [json.loads(proc.stdout.readline()) for proc in (first, second)]
        claimed = [reply for reply in replies if reply.get("ok") and reply.get("code") == "CLAIMED"]
        assert len(claimed) == 1, replies
        assert all(reply.get("dispatch_allowed") is False for reply in replies if reply not in claimed)
        assert snapshot(path)["claims"] == {"total": 1, "pending": 1, "completed": 0}
    finally:
        stop(first)
        stop(second)


def test_int08_same_stream_new_reservation_is_a_new_claim(tmp_path):
    path, ledger = setup(tmp_path)
    first = derive_call_id("run-int08", 0, 0, DIGEST)
    second = derive_call_id("run-int08", 1, 0, DIGEST)
    first_reservation = reserve_call(path, first)["reservation_id"]
    second_reservation = reserve_call(path, second, identity="reserve-int08-b")["reservation_id"]
    with claim_boundary(path) as (boundary, _claimer):
        d1 = boundary.claim_dispatch(request_for(first, first_reservation))
        d2 = boundary.claim_dispatch(request_for(
            second, second_reservation, attempt_ordinal=2))
    assert d1.allowed and d2.allowed
    assert boundary.stream("stream-g2").attempts == 2
    assert snapshot(path)["claims"]["total"] == 2
