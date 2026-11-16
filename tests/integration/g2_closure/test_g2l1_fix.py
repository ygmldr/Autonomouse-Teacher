"""A1/A3 GREEN tests for G2-L1 egress split/claim gate/strict policy/trace.

Offline only: real SQLite + real stdio Broker subprocess for FIX-08, in-process
synthetic providers elsewhere. No sockets, keys, real models or network.
"""
from __future__ import annotations

import json
import signal
import sqlite3
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from autoteacher_m0.accounting import BudgetLedger, BudgetLimits, derive_call_id
from autoteacher_m0.security.egress import (
    AttemptState, BROKER_CLAIMER_UNAVAILABLE, OPENCODE_GO_HOST, OPENCODE_GO_PATH_PREFIX,
    OPENCODE_GO_PORT, ClaimResult, DispatchPermission, EgressBoundary,
    EgressPolicy, EgressRequest, EgressViolation, PolicyEvaluation,
    PreparedProviderRequest, TrustedEgressTransport, policy_from_json,
    prepared_call_id, prepared_request_digest,
)

ROUTE = "offline-test-only"
MODEL = "fixture-v1"
ROUTE_B = "offline-test-only-b"
MODEL_B = "fixture-v1-b"
SCOPE = "g2l1-fix-scope"
DIGEST = "a" * 64
CALL_A = "call-" + "a" * 48
CALL_B = "call-" + "b" * 48


def _route_entry(route: str, model: str) -> dict:
    return {"route_id": route, "model": model,
            "price": {"version": "fixture-v1", "input_per_million": "1",
                      "output_per_million": "2", "cached_input_per_million": "0.5",
                      "source": "synthetic fixture", "captured_at": "2026-11-13"},
            "known_extra_fee_usd": "0.001",
            "usage_policy": {"cache_write": "input_rate",
                             "reasoning": "included_in_output"}}


def make_config(tmp_path: Path, *, two_routes: bool = False,
                max_messages: int = 32) -> dict:
    routes = [_route_entry(ROUTE, MODEL)]
    if two_routes:
        routes.append(_route_entry(ROUTE_B, MODEL_B))
    return {"v": 1, "synthetic": True, "db_path": str(tmp_path / "ledger.sqlite3"),
            "scope_id": SCOPE, "max_messages": max_messages,
            "limits": {"soft_usd": "3", "hard_usd": "10", "per_call_usd": "0.20",
                       "max_requests": 50, "max_input_tokens": 2500000,
                       "max_output_tokens": 600000, "max_steps": 8, "max_retries": 1},
            "routes": routes}


def setup(tmp_path: Path, *, two_routes: bool = False, max_messages: int = 32):
    config = make_config(tmp_path, two_routes=two_routes, max_messages=max_messages)
    path = tmp_path / "startup.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    limits = BudgetLimits(soft_usd="3", hard_usd="10", per_call_usd="0.20",
                          max_requests=50, max_input_tokens=2500000,
                          max_output_tokens=600000, max_steps=8, max_retries=1)
    ledger = BudgetLedger(tmp_path / "ledger.sqlite3", scope_id=SCOPE, limits=limits)
    return path, ledger


def broker_argv(path: Path) -> list[str]:
    return [sys.executable, "-B", "-m", "autoteacher_m0.accounting.broker",
            "--config", str(path)]


def start_broker(path: Path):
    return subprocess.Popen(broker_argv(path), stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def send(process, message):
    process.stdin.write(json.dumps(message) + "\n")
    process.stdin.flush()
    return json.loads(process.stdout.readline())


def run(path: Path, messages):
    data = "".join(json.dumps(message) + "\n" for message in messages)
    process = subprocess.run(broker_argv(path), input=data, text=True,
                             capture_output=True, timeout=20)
    assert process.returncode == 0, (process.returncode, process.stdout, process.stderr)
    return [json.loads(line) for line in process.stdout.splitlines()]


def reserve_call(path: Path, call_id: str, *, route: str = ROUTE, model: str = MODEL,
                 identity: str = "reserve-bind"):
    return run(path, [{"v": 1, "id": identity, "op": "reserve", "task_id": "session-bind",
                       "route_id": route, "model": model, "purpose": "conversation",
                       "input_tokens": 100, "output_tokens": 10, "retry": False,
                       "call_id": call_id}])[0]


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
    def __init__(self, path: Path):
        self.process = start_broker(path)
        self.sequence = 0

    def claim(self, request: EgressRequest) -> ClaimResult:
        self.sequence += 1
        reply = send(self.process, {"v": 1, "id": f"fix-claim-{self.sequence}", "op": "claim",
                                    "call_id": request.call_id,
                                    "reservation_id": request.reservation_id,
                                    "request_digest": request.request_digest})
        if reply.get("ok") and reply.get("code") == "CLAIMED":
            return ClaimResult(True, "CLAIMED", (), reply.get("claim"))
        return ClaimResult(False, reply.get("code", "CLAIM_FAILED"), (), reply.get("claim"))

    def close(self) -> None:
        stop(self.process)


class BoundBrokerClaimer:
    """Real stdio Broker claim client that sends additive expected route/model."""

    def __init__(self, path: Path):
        self.process = start_broker(path)
        self.sequence = 0

    def claim_bound(self, request: EgressRequest, *, expected_route_id: str,
                    expected_model: str) -> ClaimResult:
        self.sequence += 1
        reply = send(self.process, {
            "v": 1, "id": f"bound-claim-{self.sequence}", "op": "claim",
            "call_id": request.call_id, "reservation_id": request.reservation_id,
            "request_digest": request.request_digest,
            "expected_route_id": expected_route_id, "expected_model": expected_model})
        if reply.get("ok") and reply.get("code") == "CLAIMED":
            return ClaimResult(True, "CLAIMED", (), reply.get("claim"))
        return ClaimResult(False, reply.get("code", "CLAIM_FAILED"), (), reply.get("claim"))

    def close(self) -> None:
        stop(self.process)


class CountingBoundClaimer:
    def __init__(self, claimed: bool = True):
        self.claimed = claimed
        self.calls = 0

    def claim_bound(self, request: EgressRequest, *, expected_route_id: str,
                    expected_model: str) -> ClaimResult:
        self.calls += 1
        if self.claimed:
            return ClaimResult(True, "CLAIMED", (), {"call_id": request.call_id})
        return ClaimResult(False, "ALREADY_CLAIMED", ("replay",))


class AlwaysClaimer:
    def __init__(self, claimed: bool = True):
        self.claimed = claimed
        self.calls = 0

    def claim(self, request: EgressRequest) -> ClaimResult:
        self.calls += 1
        if self.claimed:
            return ClaimResult(True, "CLAIMED", (), {"call_id": request.call_id})
        return ClaimResult(False, "ALREADY_CLAIMED", ("claim already exists",))


class RaisingClaimer:
    def claim(self, request: EgressRequest) -> ClaimResult:
        raise EOFError("synthetic broker EOF")


class BadReplyClaimer:
    def claim(self, request: EgressRequest) -> object:
        return {"claimed": True}


class CountProvider:
    def __init__(self):
        self.calls = 0

    def __call__(self, request: EgressRequest) -> dict:
        self.calls += 1
        return {"status": 200, "usage": {"inputTokens": 7, "outputTokens": 3}, "error": None}


def request(**overrides: object) -> EgressRequest:
    values: dict[str, object] = {
        "logical_stream_id": "g2l1-fix-stream", "reservation_id": "reservation-a",
        "attempt_ordinal": 1, "route_id": ROUTE, "model": MODEL,
        "call_id": CALL_A, "request_digest": DIGEST,
    }
    values.update(overrides)
    return EgressRequest(**values)  # type: ignore[arg-type]


def boundary_with(claimer: object, *, routes=None) -> EgressBoundary:
    return EgressBoundary(
        EgressPolicy(approved_routes=routes or frozenset({(ROUTE, MODEL)})),
        claimer=claimer)  # type: ignore[arg-type]


def prepared_pair(*, route: str = ROUTE, model: str = MODEL,
                  max_output_tokens: int = 256, path: str | None = None,
                  method: str = "POST", host: str = OPENCODE_GO_HOST) -> tuple[PreparedProviderRequest, EgressRequest]:
    base = PreparedProviderRequest(
        schema_version="m0.prepared.v1", scope_id=SCOPE, run_id="run-bind",
        logical_step=0, attempt_index=0, route_id=route, provider=route, model=model,
        host=host, port=OPENCODE_GO_PORT, method=method,
        path=path or OPENCODE_GO_PATH_PREFIX + "openai/v1/chat/completions",
        stream=True, max_output_tokens=max_output_tokens, system="root system",
        messages=({"role": "user", "content": "hello"},), tools=(),
        response_format=None, retry_policy=None, has_files=False, has_images=False,
        store=False, call_id="", request_digest="")
    digest = prepared_request_digest(base)
    call = prepared_call_id(base)
    prepared = replace(base, call_id=call, request_digest=digest)
    request_value = EgressRequest(
        logical_stream_id="g2l1-fix-stream", reservation_id="reservation-bind",
        attempt_ordinal=1, route_id=route, model=model, host=host,
        port=OPENCODE_GO_PORT, method=method, path=prepared.path, stream=True,
        max_tokens=max_output_tokens, has_files=False, has_images=False, store=False,
        call_id=call, request_digest=digest)
    return prepared, request_value


def snapshot_broker(path: Path) -> dict:
    return run(path, [{"v": 1, "id": "snapshot-bind", "op": "snapshot"}])[0]["snapshot"]


def rebind(prepared: PreparedProviderRequest, request: EgressRequest, **changes: object):
    new_prepared = replace(prepared, **changes)
    digest = prepared_request_digest(new_prepared)
    call = prepared_call_id(new_prepared)
    new_prepared = replace(new_prepared, call_id=call, request_digest=digest)
    # Keep the actual EgressRequest carrying the same trusted digest/call id so the
    # test isolates the specific binding field rather than a digest mismatch.
    new_request = replace(request, call_id=call, request_digest=digest)
    return new_prepared, new_request


# ---------------------------------------------------------------- FIX-01..08
def test_fix01_descriptor_evaluation_is_policy_only() -> None:
    boundary = boundary_with(AlwaysClaimer())
    evaluation = boundary.evaluate_descriptor(request())
    assert isinstance(evaluation, PolicyEvaluation)
    assert evaluation.allowed is True
    assert not hasattr(evaluation, "permission")
    assert boundary.authorize(request()).allowed is True
    assert boundary.require(request()).allowed is True


def test_fix02_no_claimer_claim_dispatch_fails_closed() -> None:
    boundary = EgressBoundary(EgressPolicy(approved_routes=frozenset({(ROUTE, MODEL)})))
    decision = boundary.claim_dispatch(request())
    assert decision.allowed is False
    assert BROKER_CLAIMER_UNAVAILABLE in decision.reasons
    assert decision.permission is None
    with pytest.raises(EgressViolation):
        boundary.require_claim(request())


@pytest.mark.parametrize("claimer", [
    AlwaysClaimer(claimed=False),
    RaisingClaimer(),
    BadReplyClaimer(),
])
def test_fix03_claim_failures_fail_closed(claimer: object) -> None:
    boundary = boundary_with(claimer)
    decision = boundary.claim_dispatch(request())
    assert decision.allowed is False
    assert decision.permission is None


def test_fix04_descriptor_deny_never_calls_claimer() -> None:
    claimer = AlwaysClaimer()
    boundary = boundary_with(claimer)
    decision = boundary.claim_dispatch(request(route_id="not-approved"))
    assert decision.allowed is False
    assert decision.permission is None
    assert claimer.calls == 0


@pytest.mark.parametrize("permission", [None, "forged", {"claim": {"claimed": True}}])
def test_fix05_trusted_transport_rejects_non_permission(permission: object) -> None:
    provider = CountProvider()
    transport = TrustedEgressTransport(boundary_with(AlwaysClaimer()), provider)
    outcome = transport.dispatch(request(), permission)
    assert outcome["dispatched"] is False
    assert provider.calls == 0
    assert transport.provider_calls == 0


def test_fix06_trusted_transport_dispatches_once() -> None:
    provider = CountProvider()
    boundary = boundary_with(AlwaysClaimer())
    decision = boundary.claim_dispatch(request())
    assert decision.permission is not None
    transport = TrustedEgressTransport(boundary, provider)
    outcome = transport.dispatch(request(), decision.permission)
    assert outcome["dispatched"] is True and provider.calls == 1
    replay = transport.dispatch(request(), decision.permission)
    assert replay["dispatched"] is False
    assert provider.calls == 1
    assert boundary.stream("g2l1-fix-stream").provider_dispatched == 1


def test_fix07_permission_is_bound_to_request_identity() -> None:
    provider = CountProvider()
    boundary = boundary_with(AlwaysClaimer())
    permission = boundary.claim_dispatch(request()).permission
    assert permission is not None
    transport = TrustedEgressTransport(boundary, provider)
    outcome = transport.dispatch(request(reservation_id="reservation-other"), permission)
    assert outcome["dispatched"] is False and provider.calls == 0


def test_fix08_real_stdio_claim_and_single_synthetic_dispatch(tmp_path: Path) -> None:
    path, _ledger = setup(tmp_path)
    call = derive_call_id("run-fix08", 0, 0, DIGEST)
    reply = run(path, [{"v": 1, "id": "reserve-fix08", "op": "reserve",
                        "task_id": "session-fix08", "route_id": ROUTE, "model": MODEL,
                        "purpose": "conversation", "input_tokens": 100,
                        "output_tokens": 10, "retry": False, "call_id": call}])[0]
    assert reply["ok"] and reply["dispatch_allowed"]
    reservation = reply["reservation_id"]
    claimer = StdioBrokerClaimer(path)
    try:
        boundary = boundary_with(claimer)
        candidate = request(call_id=call, reservation_id=reservation)
        first = boundary.claim_dispatch(candidate)
        assert first.allowed and first.permission is not None
        provider = CountProvider()
        transport = TrustedEgressTransport(boundary, provider)
        outcome = transport.dispatch(candidate, first.permission)
        assert outcome["dispatched"] is True and provider.calls == 1
        replay = boundary.claim_dispatch(candidate)
        assert replay.allowed is False and replay.permission is None
        assert provider.calls == 1
        no_claimer = EgressBoundary(
            EgressPolicy(approved_routes=frozenset({(ROUTE, MODEL)})))
        assert no_claimer.claim_dispatch(candidate).allowed is False
        assert provider.calls == 1
    finally:
        claimer.close()


# ---------------------------------------------------------------- STRICT-01..04
@pytest.mark.parametrize("payload", [
    {"allow_files": "false"},
    {"allow_store": "0"},
    {"max_tokens": "256"},
    {"require_reservation": 0},
])
def test_strict01_policy_loader_rejects_coercion(payload: dict[str, object]) -> None:
    with pytest.raises((TypeError, ValueError)):
        policy_from_json(payload)


@pytest.mark.parametrize("payload", [
    {"max_tokens": 0}, {"max_tokens": 99999}, {"max_attempts": 0},
    {"max_attempts": True}, {"host_ports": {"h": [0]}},
    {"host_ports": {"h": ["443"]}}, {"methods": []}, {"methods": [""]},
    {"approved_routes": [["a"]]}, {"approved_routes": [["a", "b"], ["a", "b"]]},
    {"path_prefix": "relative"}, {"path_prefix": "/a/../b"}, {"unknown": 1},
])
def test_strict02_policy_loader_rejects_invalid_schema(payload: dict[str, object]) -> None:
    with pytest.raises((TypeError, ValueError)):
        policy_from_json(payload)


def test_strict03_policy_loader_accepts_strict_valid_payload() -> None:
    policy = policy_from_json({"max_tokens": 512, "max_attempts": 2,
                               "allow_files": True, "allow_store": False,
                               "methods": ["POST"], "host_ports": {"opencode.ai": [443]},
                               "approved_routes": [["opencode-go", "deepseek-v4.1-flash"]],
                               "path_prefix": "/inference/go/"})
    assert policy.max_tokens == 512 and policy.max_attempts == 2
    assert policy.allow_files is True and policy.allow_store is False


@pytest.mark.parametrize("overrides", [
    {"max_tokens": True}, {"attempt_ordinal": True}, {"stream": 0},
    {"has_files": 1}, {"has_images": 0}, {"store": 1},
    {"max_tokens": 0}, {"attempt_ordinal": 0},
])
def test_strict04_request_flags_reject_bool_int_confusion(overrides: dict[str, object]) -> None:
    decision = boundary_with(AlwaysClaimer()).claim_dispatch(request(**overrides))
    assert decision.allowed is False
    assert decision.permission is None




def test_fix09_forged_tampered_cross_boundary_and_replayed_permission_never_dispatch() -> None:
    request_value = request()
    boundary = boundary_with(AlwaysClaimer())
    real = boundary.claim_dispatch(request_value).permission
    assert real is not None
    forged = DispatchPermission(
        claim=ClaimResult(True, "CLAIMED", (), {"call_id": request_value.call_id}),
        call_id=request_value.call_id, request_digest=request_value.request_digest,
        logical_stream_id=request_value.logical_stream_id,
        reservation_id=request_value.reservation_id,
        attempt_ordinal=request_value.attempt_ordinal,
        route_model=(request_value.route_id, request_value.model))
    assert forged is not real
    provider = CountProvider()
    transport = TrustedEgressTransport(boundary, provider)
    assert transport.dispatch(request_value, forged)["dispatched"] is False
    assert provider.calls == 0
    tampered = replace(real, reservation_id="reservation-tampered")
    assert transport.dispatch(request_value, tampered)["dispatched"] is False
    assert provider.calls == 0
    other_boundary = boundary_with(AlwaysClaimer())
    other_transport = TrustedEgressTransport(other_boundary, provider)
    assert other_transport.dispatch(request_value, real)["dispatched"] is False
    assert provider.calls == 0
    assert transport.dispatch(request_value, real)["dispatched"] is True
    assert provider.calls == 1
    assert transport.dispatch(request_value, real)["dispatched"] is False
    assert provider.calls == 1


@pytest.mark.parametrize("payload", [
    {"methods": ["POST", "POST"]},
    {"methods": [" POST "]},
    {"host_ports": {"opencode.ai": [443, 443]}},
    {"host_ports": {" opencode.ai": [443]}},
])
def test_strict03b_policy_loader_rejects_duplicates_and_whitespace(payload: dict[str, object]) -> None:
    with pytest.raises((TypeError, ValueError)):
        policy_from_json(payload)


@pytest.mark.parametrize("path", [
    "/v1/../admin",
    "/inference/go/../../admin",
    "/inference/go\\openai/v1/chat",
    "/inference/go/%2e%2e/admin",
    "/inference/go/%2E%2E/admin",
    "/inference/go/\x00admin",
    "relative/path",
])
def test_strict04b_path_traversal_backslash_encoding_and_control_denied(path: str) -> None:
    boundary = boundary_with(AlwaysClaimer())
    decision = boundary.claim_dispatch(request(path=path))
    assert decision.allowed is False
    assert decision.permission is None
    provider = CountProvider()
    transport = TrustedEgressTransport(boundary, provider)
    assert transport.dispatch(request(path=path), None)["dispatched"] is False
    assert provider.calls == 0


# ---------------------------------------------------------------- BIND-01..08
def test_bind01_reservation_a_actual_b_route_mismatch_ledger(tmp_path: Path) -> None:
    path, _ledger = setup(tmp_path, two_routes=True)
    prepared, actual = prepared_pair(route=ROUTE_B, model=MODEL_B)
    reserved = reserve_call(path, actual.call_id, route=ROUTE, model=MODEL)
    assert reserved["ok"] and reserved["dispatch_allowed"]
    actual = replace(actual, reservation_id=reserved["reservation_id"])
    claimer = BoundBrokerClaimer(path)
    try:
        boundary = boundary_with(claimer, routes=frozenset({(ROUTE, MODEL), (ROUTE_B, MODEL_B)}))
        provider = CountProvider()
        transport = TrustedEgressTransport(boundary, provider)
        decision = boundary.claim_dispatch_for_request(prepared, actual)
        assert decision.allowed is False and decision.permission is None
        assert any("ROUTE_MISMATCH" in reason for reason in decision.reasons)
        assert provider.calls == 0
        assert transport.provider_calls == 0
        assert snapshot_broker(path)["claims"]["total"] == 0
    finally:
        claimer.close()


def test_bind02_prepared_message_digest_change_denied() -> None:
    prepared, actual = prepared_pair()
    mutated = replace(prepared, messages=({"role": "user", "content": "changed"},))
    claimer = CountingBoundClaimer()
    boundary = boundary_with(claimer)
    decision = boundary.claim_dispatch_for_request(mutated, actual)
    assert decision.allowed is False and decision.permission is None
    assert claimer.calls == 0


def test_bind03_max_tokens_mismatch_denied() -> None:
    prepared, actual = prepared_pair()
    prepared2, actual2 = rebind(prepared, actual, max_output_tokens=512)
    claimer = CountingBoundClaimer()
    decision = boundary_with(claimer).claim_dispatch_for_request(prepared2, actual2)
    assert decision.allowed is False and decision.permission is None
    assert claimer.calls == 0


def test_bind04_method_path_host_bypass_denied() -> None:
    prepared, actual = prepared_pair()
    claimer = CountingBoundClaimer()
    for changes in ({"method": "GET"}, {"path": "/v1/chat/completions"},
                    {"host": "api.deepseek.com"}):
        prepared2, actual2 = rebind(prepared, actual, **changes)
        decision = boundary_with(claimer).claim_dispatch_for_request(prepared2, actual2)
        assert decision.allowed is False and decision.permission is None
        assert claimer.calls == 0


def test_bind05_unapproved_tool_schema_denied() -> None:
    prepared, actual = prepared_pair()
    prepared2, actual2 = rebind(prepared, actual, tools=({"name": "unapproved_tool"},))
    claimer = CountingBoundClaimer()
    decision = boundary_with(claimer).claim_dispatch_for_request(prepared2, actual2)
    assert decision.allowed is False and decision.permission is None
    assert any("TOOL_SCHEMA" in reason for reason in decision.reasons)
    assert claimer.calls == 0


def test_bind06_duplicate_bound_claim_at_most_once(tmp_path: Path) -> None:
    path, _ledger = setup(tmp_path)
    prepared, actual = prepared_pair()
    reserved = reserve_call(path, actual.call_id)
    assert reserved["ok"] and reserved["dispatch_allowed"]
    actual = replace(actual, reservation_id=reserved["reservation_id"])
    claimer = BoundBrokerClaimer(path)
    try:
        boundary = boundary_with(claimer)
        provider = CountProvider()
        transport = TrustedEgressTransport(boundary, provider)
        first = boundary.claim_dispatch_for_request(prepared, actual)
        assert first.allowed and first.permission is not None
        assert transport.dispatch(actual, first.permission)["dispatched"] is True
        replay = boundary.claim_dispatch_for_request(prepared, actual)
        assert replay.allowed is False and replay.permission is None
        assert provider.calls == 1
        assert snapshot_broker(path)["claims"]["total"] == 1
    finally:
        claimer.close()


def test_bind07_unmodified_success_once_and_ledger_link(tmp_path: Path) -> None:
    path, _ledger = setup(tmp_path)
    prepared, actual = prepared_pair()
    reserved = reserve_call(path, actual.call_id)
    assert reserved["ok"] and reserved["dispatch_allowed"]
    actual = replace(actual, reservation_id=reserved["reservation_id"])
    claimer = BoundBrokerClaimer(path)
    try:
        boundary = boundary_with(claimer)
        provider = CountProvider()
        transport = TrustedEgressTransport(boundary, provider)
        decision = boundary.claim_dispatch_for_request(prepared, actual)
        assert decision.allowed and decision.permission is not None
        outcome = transport.dispatch(actual, decision.permission)
        assert outcome["dispatched"] is True and provider.calls == 1
        assert snapshot_broker(path)["claims"]["total"] == 1
    finally:
        claimer.close()


def test_bind08_reserve_dispatch_allowed_without_claim_zero_dispatch(tmp_path: Path) -> None:
    path, _ledger = setup(tmp_path)
    prepared, actual = prepared_pair()
    reserved = reserve_call(path, actual.call_id)
    assert reserved["ok"] and reserved["dispatch_allowed"] is True
    provider = CountProvider()
    transport = TrustedEgressTransport(boundary_with(AlwaysClaimer(claimed=False)), provider)
    outcome = transport.dispatch(actual, None)
    assert outcome["dispatched"] is False and provider.calls == 0
    assert snapshot_broker(path)["claims"]["total"] == 0



def test_v1_old_claim_without_expected_fields_still_succeeds(tmp_path: Path) -> None:
    path, _ledger = setup(tmp_path)
    prepared, actual = prepared_pair()
    reserved = reserve_call(path, actual.call_id)
    assert reserved["ok"] and reserved["dispatch_allowed"]
    actual = replace(actual, reservation_id=reserved["reservation_id"])
    claimer = StdioBrokerClaimer(path)
    try:
        # Old v1 client: no expected_route_id/expected_model; legacy behavior must hold.
        legacy = claimer.claim(actual)
        assert legacy.claimed and legacy.code == "CLAIMED"
        assert snapshot_broker(path)["claims"]["total"] == 1
    finally:
        claimer.close()


def test_v1_new_egress_rejects_unbound_claimer(tmp_path: Path) -> None:
    path, _ledger = setup(tmp_path)
    prepared, actual = prepared_pair()
    reserved = reserve_call(path, actual.call_id)
    assert reserved["ok"] and reserved["dispatch_allowed"]
    actual = replace(actual, reservation_id=reserved["reservation_id"])
    claimer = AlwaysClaimer()
    boundary = boundary_with(claimer)
    provider = CountProvider()
    transport = TrustedEgressTransport(boundary, provider)
    decision = boundary.claim_dispatch_for_request(prepared, actual)
    assert decision.allowed is False and decision.permission is None
    assert "CLAIM_BINDING_UNSUPPORTED" in decision.reasons
    assert claimer.calls == 0
    assert provider.calls == 0
    assert transport.provider_calls == 0

# ---------------------------------------------------------------- TRACE-01 / PROC-01
def test_trace01_same_stream_multiple_reservations_kept_in_detail() -> None:
    boundary = boundary_with(AlwaysClaimer())
    first = boundary.claim_dispatch(request(reservation_id="reservation-a", call_id=CALL_A))
    second = boundary.claim_dispatch(request(reservation_id="reservation-b", call_id=CALL_B,
                                             attempt_ordinal=2))
    assert first.allowed and second.allowed
    stream = boundary.stream("g2l1-fix-stream")
    assert stream.attempts == 2 and stream.claims_granted == 2
    detail = stream.attempts_detail
    assert [entry["reservation_id"] for entry in detail] == ["reservation-a", "reservation-b"]
    assert [entry["call_id"] for entry in detail] == [CALL_A, CALL_B]
    assert all(entry["claim_granted"] is True for entry in detail)


def test_proc01_stdiabroker_client_is_closed(tmp_path: Path) -> None:
    path, _ledger = setup(tmp_path)
    claimer = StdioBrokerClaimer(path)
    process = claimer.process
    assert process.poll() is None
    try:
        claimer.close()
    finally:
        if process.poll() is None:
            stop(process, kill=True)
    assert process.poll() is not None

# ---------------------------------------------------------------- G2-L1.1 L11 tests
class L11CountingProvider:
    def __init__(self, behavior: str = "raise"):
        self.behavior = behavior
        self.calls = 0

    def __call__(self, request: EgressRequest):
        self.calls += 1
        if self.behavior == "raise":
            raise RuntimeError("after-entry synthetic failure")
        if self.behavior == "interrupt":
            raise KeyboardInterrupt()
        if self.behavior == "nonmapping":
            return "not-a-mapping"
        return {"status": 200, "usage": None, "error": None}


class L11CountingBoundClaimer:
    def __init__(self):
        self.calls = 0

    def claim_bound(self, request: EgressRequest, *, expected_route_id: str,
                    expected_model: str) -> ClaimResult:
        self.calls += 1
        return ClaimResult(True, "CLAIMED", (), {"call_id": request.call_id})


def _permission(boundary: EgressBoundary, request_value: EgressRequest):
    decision = boundary.claim_dispatch(request_value)
    assert decision.allowed and decision.permission is not None
    return decision.permission


def test_l11_att_01_no_permission_zero_provider() -> None:
    provider = L11CountingProvider("raise")
    transport = TrustedEgressTransport(boundary_with(AlwaysClaimer()), provider)
    outcome = transport.dispatch(request(), None)
    assert outcome["dispatched"] is False
    assert outcome["classification"] == "PRE_DISPATCH_DENIED"
    assert outcome["state"] == AttemptState.NOT_DISPATCHED.value
    assert provider.calls == 0 and transport.provider_calls == 0


def test_l11_att_02_after_claim_before_provider_zero_calls() -> None:
    provider = L11CountingProvider("raise")
    boundary = boundary_with(AlwaysClaimer())
    permission = _permission(boundary, request())
    transport = TrustedEgressTransport(boundary, provider)
    outcome = transport.dispatch(request(reservation_id="different"), permission)
    assert outcome["state"] == AttemptState.NOT_DISPATCHED.value
    assert provider.calls == 0 and transport.provider_calls == 0


def test_l11_att_03_provider_entry_then_runtimeerror_is_billable_unknown() -> None:
    provider = L11CountingProvider("raise")
    boundary = boundary_with(AlwaysClaimer())
    request_value = request()
    permission = _permission(boundary, request_value)
    transport = TrustedEgressTransport(boundary, provider)
    outcome = transport.dispatch(request_value, permission)
    assert provider.calls == 1 and transport.provider_calls == 1
    assert outcome["attempt_started"] is True and outcome["provider_invoked"] is True
    assert outcome["state"] == AttemptState.BILLABLE_UNKNOWN.value
    assert outcome["provider_calls"] == 1
    assert outcome["retry_attempted"] is False
    assert boundary.stream("g2l1-fix-stream").worst_case_held_usd > 0


def test_l11_att_04_invalid_result_is_unknown_not_not_dispatched() -> None:
    provider = L11CountingProvider("nonmapping")
    boundary = boundary_with(AlwaysClaimer())
    request_value = request()
    permission = _permission(boundary, request_value)
    transport = TrustedEgressTransport(boundary, provider)
    outcome = transport.dispatch(request_value, permission)
    assert provider.calls == 1
    assert outcome["state"] == AttemptState.BILLABLE_UNKNOWN.value
    assert outcome["classification"] == "ATTEMPT_STARTED"
    assert outcome["retry_attempted"] is False


def test_l11_att_05_permission_single_use() -> None:
    provider = L11CountingProvider("nonmapping")
    boundary = boundary_with(AlwaysClaimer())
    request_value = request()
    permission = _permission(boundary, request_value)
    transport = TrustedEgressTransport(boundary, provider)
    transport.dispatch(request_value, permission)
    calls = provider.calls
    second = transport.dispatch(request_value, permission)
    assert second["state"] == AttemptState.NOT_DISPATCHED.value
    assert provider.calls == calls


def test_l11_att_06_keyboardinterrupt_preserved_and_unknown() -> None:
    provider = L11CountingProvider("interrupt")
    boundary = boundary_with(AlwaysClaimer())
    request_value = request()
    permission = _permission(boundary, request_value)
    transport = TrustedEgressTransport(boundary, provider)
    with pytest.raises(KeyboardInterrupt):
        transport.dispatch(request_value, permission)
    assert provider.calls == 1
    assert boundary.stream("g2l1-fix-stream").state is AttemptState.BILLABLE_UNKNOWN


def test_l11_id_01_ascii_accounting_egress_match() -> None:
    prepared, _request = prepared_pair()
    digest = prepared_request_digest(prepared)
    assert prepared_call_id(prepared) == derive_call_id(prepared.run_id, prepared.logical_step,
                                                         prepared.attempt_index, digest)


def test_l11_id_02_unicode_run_id_accounting_egress_match() -> None:
    prepared, _request = prepared_pair()
    prepared = replace(prepared, run_id="运行-中文-α")
    digest = prepared_request_digest(prepared)
    prepared = replace(prepared, request_digest=digest, call_id=prepared_call_id(prepared))
    assert prepared_call_id(prepared) == derive_call_id(prepared.run_id, prepared.logical_step,
                                                         prepared.attempt_index, digest)


def test_l11_id_03_cross_process_ascii_and_unicode() -> None:
    code = ("from autoteacher_m0.accounting.call_identity import derive_call_id;"
            "print(derive_call_id('运行-中文',0,0,'a'*64))")
    proc = subprocess.run([sys.executable, "-c", code], text=True, capture_output=True, check=True)
    expected = derive_call_id("运行-中文", 0, 0, "a" * 64)
    assert proc.stdout.strip() == expected


def test_l11_id_04_single_field_changes_identity() -> None:
    base = derive_call_id("run", 0, 0, "a" * 64)
    assert derive_call_id("run", 1, 0, "a" * 64) != base
    assert derive_call_id("run", 0, 1, "a" * 64) != base
    assert derive_call_id("run", 0, 0, "b" * 64) != base


def test_l11_id_05_bool_nan_and_invalid_types_rejected() -> None:
    from autoteacher_m0.accounting.call_identity import IdentitySchemaError
    with pytest.raises(IdentitySchemaError):
        derive_call_id("run", True, 0, "a" * 64)
    with pytest.raises(IdentitySchemaError):
        derive_call_id("run", True, 0, "a" * 64)
    prepared, _ = prepared_pair()
    with pytest.raises((TypeError, ValueError)):
        prepared_request_digest(replace(prepared, messages=({"x": float("nan")},)))


def test_l11_id_06_legacy_ascii_id_is_stable() -> None:
    first = derive_call_id("legacy-run", 2, 1, "c" * 64)
    assert first == derive_call_id("legacy-run", 2, 1, "c" * 64)
    assert first.startswith("call-") and len(first) == 53


def test_l11_prep_01_unknown_schema_version_denied() -> None:
    prepared, actual = prepared_pair()
    claimer = L11CountingBoundClaimer()
    bad = replace(prepared, schema_version="m0.prepared.v0")
    decision = boundary_with(claimer).claim_dispatch_for_request(
        bad, actual, expected_reservation_route_model=(ROUTE, MODEL))
    assert decision.allowed is False and decision.permission is None
    assert claimer.calls == 0


def test_l11_prep_02_bool_as_int_denied() -> None:
    prepared, actual = prepared_pair()
    prepared = replace(prepared, logical_step=True)
    claimer = L11CountingBoundClaimer()
    decision = boundary_with(claimer).claim_dispatch_for_request(prepared, actual)
    assert decision.allowed is False and decision.permission is None
    assert claimer.calls == 0


def test_l11_prep_03_message_change_changes_digest() -> None:
    prepared, _ = prepared_pair()
    changed = replace(prepared, messages=({"role": "user", "content": "changed"},))
    assert prepared_request_digest(prepared) != prepared_request_digest(changed)


def test_l11_prep_04_mutated_nested_mapping_denied() -> None:
    prepared, actual = prepared_pair()
    mutable = {"role": "user", "content": "literal"}
    prepared = replace(prepared, messages=(mutable,))
    prepared = replace(prepared, request_digest=prepared_request_digest(prepared),
                       call_id=prepared_call_id(prepared))
    mutable["content"] = "mutated"
    claimer = L11CountingBoundClaimer()
    decision = boundary_with(claimer).claim_dispatch_for_request(prepared, actual)
    assert decision.allowed is False and claimer.calls == 0


def test_l11_prep_05_route_method_path_host_change_denied() -> None:
    prepared, actual = prepared_pair()
    claimer = L11CountingBoundClaimer()
    for changes in ({"max_output_tokens": 512}, {"method": "GET"},
                    {"path": "/v1/chat/completions"}, {"host": "api.deepseek.com"}):
        changed = replace(prepared, **changes)
        decision = boundary_with(claimer).claim_dispatch_for_request(changed, actual)
        assert decision.allowed is False and decision.permission is None
        assert claimer.calls == 0


def test_l11_jrn_01_unknown_reservation_completions_do_not_grow_journal(tmp_path: Path) -> None:
    path, _ledger = setup(tmp_path)
    for index in range(6):
        reply = run(path, [{"v": 1, "id": f"unknown-{index}", "op": "settle",
                            "reservation_id": "missing-reservation",
                            "usage": {"inputTokens": 1, "outputTokens": 1}}])[0]
        assert reply["ok"] is False and reply["code"] == "UNKNOWN_RESERVATION"
    with sqlite3.connect(tmp_path / "ledger.sqlite3") as database:
        count = database.execute("SELECT COUNT(*) FROM budget_broker_messages").fetchone()[0]
    assert count == 0


def test_l11_jrn_02_valid_pending_settle_and_fail_remain_available(tmp_path: Path) -> None:
    path, _ledger = setup(tmp_path, max_messages=8)
    first = derive_call_id("run-jrn2-a", 0, 0, DIGEST)
    second = derive_call_id("run-jrn2-b", 0, 0, DIGEST)
    first_res = reserve_call(path, first, identity="reserve-jrn2-a")["reservation_id"]
    second_res = reserve_call(path, second, identity="reserve-jrn2-b")["reservation_id"]
    settled = run(path, [{"v": 1, "id": "settle-jrn2", "op": "settle",
                          "reservation_id": first_res,
                          "usage": {"inputTokens": 1, "outputTokens": 1}}])[0]
    failed = run(path, [{"v": 1, "id": "fail-jrn2", "op": "fail",
                         "reservation_id": second_res,
                         "usage": {"inputTokens": 1, "outputTokens": 1}}])[0]
    assert settled["ok"] and settled["code"] == "SETTLED"
    assert failed["ok"] and failed["code"] == "FAILED"


def test_l11_jrn_03_same_message_id_idempotent(tmp_path: Path) -> None:
    path, _ledger = setup(tmp_path)
    call = derive_call_id("run-jrn3", 0, 0, DIGEST)
    reservation = reserve_call(path, call)["reservation_id"]
    message = {"v": 1, "id": "settle-jrn3", "op": "settle", "reservation_id": reservation,
               "usage": {"inputTokens": 1, "outputTokens": 1}}
    first = run(path, [message])[0]
    second = run(path, [message])[0]
    assert first["ok"] and second["ok"] and second["code"] == "SETTLED"


def test_l11_jrn_04_new_id_for_settled_reservation_does_not_grow_journal(tmp_path: Path) -> None:
    path, _ledger = setup(tmp_path)
    call = derive_call_id("run-jrn4", 0, 0, DIGEST)
    reservation = reserve_call(path, call)["reservation_id"]
    run(path, [{"v": 1, "id": "settle-jrn4-a", "op": "settle",
                "reservation_id": reservation,
                "usage": {"inputTokens": 1, "outputTokens": 1}}])
    with sqlite3.connect(tmp_path / "ledger.sqlite3") as database:
        before = database.execute("SELECT COUNT(*) FROM budget_broker_messages").fetchone()[0]
    reply = run(path, [{"v": 1, "id": "settle-jrn4-b", "op": "settle",
                        "reservation_id": reservation,
                        "usage": {"inputTokens": 1, "outputTokens": 1}}])[0]
    with sqlite3.connect(tmp_path / "ledger.sqlite3") as database:
        after = database.execute("SELECT COUNT(*) FROM budget_broker_messages").fetchone()[0]
    assert reply["ok"] is False and after == before


def test_l11_diag_01_descriptor_diagnostics_do_not_consume_attempt_quota() -> None:
    boundary = EgressBoundary(
        EgressPolicy(approved_routes=frozenset({(ROUTE, MODEL)}), max_attempts=1),
        claimer=AlwaysClaimer())
    for _ in range(5):
        assert boundary.evaluate_descriptor(request()).allowed
    decision = boundary.claim_dispatch(request())
    assert decision.allowed and decision.permission is not None
    stream = boundary.stream("g2l1-fix-stream")
    assert stream.policy_checks == 6  # 5 diagnostics + 1 claim admission check
    assert stream.claims_granted == 1


def test_l11_diag_02_claim_and_dispatch_counters() -> None:
    provider = L11CountingProvider("nonmapping")
    boundary = boundary_with(AlwaysClaimer())
    request_value = request()
    permission = _permission(boundary, request_value)
    TrustedEgressTransport(boundary, provider).dispatch(request_value, permission)
    stream = boundary.stream("g2l1-fix-stream")
    assert stream.policy_checks == 1
    assert stream.policy_allowed == 1
    assert stream.claims_granted == 1
    assert stream.dispatch_attempted == 1
    assert stream.provider_invocations == 1
    assert stream.attempts == 1  # legacy successful-claim compatibility only


def test_l11_diag_03_attempts_detail_multi_reservation() -> None:
    boundary = boundary_with(AlwaysClaimer())
    first = boundary.claim_dispatch(request(reservation_id="reservation-a", call_id=CALL_A))
    second = boundary.claim_dispatch(request(reservation_id="reservation-b", call_id=CALL_B,
                                             attempt_ordinal=2))
    assert first.allowed and second.allowed
    stream = boundary.stream("g2l1-fix-stream")
    assert stream.attempts_detail[0]["reservation_id"] == "reservation-a"
    assert stream.attempts_detail[1]["reservation_id"] == "reservation-b"
    assert stream.attempts_detail[0]["claim_granted"] is True
