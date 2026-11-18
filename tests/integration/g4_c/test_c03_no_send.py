"""G4-C: no send without a claim/permission, no automatic retry, no FREE state."""
from __future__ import annotations

from autoteacher_m0.security.egress import (
    AttemptState,
    ClaimResult,
    EgressBoundary,
    EgressPolicy,
    MockEgressTransport,
    PolicyOnlyFakeTransport,
    SYNTHETIC_ROUTE_CONTRACT,
    TrustedEgressTransport,
)
from g4c_support import (
    approved_tool, make_prepared, make_request,
)


class BoundClaimer:
    def __init__(self) -> None:
        self.calls = 0

    def claim_bound(self, request, *, expected_route_id, expected_model):
        self.calls += 1
        claim = {"call_id": request.call_id,
                 "reservation_id": request.reservation_id,
                 "request_digest": request.request_digest, "status": "CLAIMED"}
        return ClaimResult(True, "CLAIMED", (), claim)


class SpyProvider:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, request):
        self.calls += 1
        return {"status": 200, "usage": {"inputTokens": 7, "outputTokens": 3},
                "error": None}


def _boundary(claimer=None) -> EgressBoundary:
    return EgressBoundary(EgressPolicy(
        host_ports={"g3b-fake.local": frozenset({9000})},
        methods=frozenset({"POST"}), path_prefix="/v1/g3b/",
        approved_routes=frozenset({(SYNTHETIC_ROUTE_CONTRACT.route_id,
                                    SYNTHETIC_ROUTE_CONTRACT.model_id)}),
        max_tokens=1024, max_attempts=2, require_reservation=True,
        allow_files=False, allow_images=False, allow_store=False),
        claimer=claimer or BoundClaimer())


def _claimed(boundary):
    prepared = make_prepared()
    request = make_request(prepared)
    decision = boundary.claim_dispatch_for_request(
        prepared, request,
        approved_tool_schemas=frozenset({__import__(
            "autoteacher_m0.security.egress", fromlist=["tool_schema_digest"]
        ).tool_schema_digest(approved_tool())}))
    return prepared, request, decision


def test_c03_transport_without_permission_calls_provider_zero_times() -> None:
    boundary = _boundary()
    prepared, request, decision = _claimed(boundary)
    assert decision.allowed and decision.permission is not None
    spy = SpyProvider()
    transport = TrustedEgressTransport(boundary, provider=spy)
    outcome = transport.dispatch(request, None)
    assert outcome["dispatched"] is False
    assert outcome["attempt_started"] is False
    assert outcome["denied_reasons"] == ["DISPATCH_PERMISSION_REQUIRED"]
    assert spy.calls == 0
    assert transport.provider_calls == 0


def test_c03_replayed_permission_calls_provider_once() -> None:
    boundary = _boundary()
    prepared, request, decision = _claimed(boundary)
    spy = SpyProvider()
    transport = TrustedEgressTransport(boundary, provider=spy)
    first = transport.dispatch(request, decision.permission)
    assert first["dispatched"] is True and spy.calls == 1
    second = transport.dispatch(request, decision.permission)
    assert second["dispatched"] is False
    assert spy.calls == 1


def test_c03_no_claim_means_no_provider_call() -> None:
    boundary = EgressBoundary(EgressPolicy(
        host_ports={"g3b-fake.local": frozenset({9000})},
        methods=frozenset({"POST"}), path_prefix="/v1/g3b/",
        approved_routes=frozenset({(SYNTHETIC_ROUTE_CONTRACT.route_id,
                                    SYNTHETIC_ROUTE_CONTRACT.model_id)}),
        max_tokens=1024, max_attempts=2, require_reservation=True),
        claimer=None)
    prepared = make_prepared()
    request = make_request(prepared)
    decision = boundary.claim_dispatch_for_request(prepared, request)
    assert decision.allowed is False
    assert "BROKER_CLAIMER_UNAVAILABLE" in decision.reasons
    assert decision.permission is None
    spy = SpyProvider()
    transport = TrustedEgressTransport(boundary, provider=spy)
    outcome = transport.dispatch(request, None)
    assert outcome["dispatched"] is False and spy.calls == 0


def test_c03_policy_only_transport_never_dispatches() -> None:
    boundary = _boundary()
    prepared, request, _decision = _claimed(boundary)
    transport = PolicyOnlyFakeTransport(boundary)
    outcome = transport.dispatch(request)
    assert outcome["dispatched"] is False
    assert outcome["state"] == AttemptState.NOT_DISPATCHED.value


def test_c10_synthetic_error_scenarios_never_retry_or_free() -> None:
    scenarios = {
        "http_429": AttemptState.NOT_BILLABLE_HTTP_ERROR,
        "http_500": AttemptState.BILLABLE_UNKNOWN,
        "http_503": AttemptState.BILLABLE_UNKNOWN,
        "timeout": AttemptState.BILLABLE_UNKNOWN,
        "hang": AttemptState.BILLABLE_UNKNOWN,
        "disconnect": AttemptState.BILLABLE_UNKNOWN,
        "unknown_transport": AttemptState.BILLABLE_UNKNOWN,
        "ok_no_usage": AttemptState.BILLABLE_UNKNOWN,
        "ok_partial_usage": AttemptState.BILLABLE_UNKNOWN,
    }
    for scenario, expected in scenarios.items():
        boundary = _boundary()
        prepared, request, decision = _claimed(boundary)
        transport = MockEgressTransport(boundary)
        outcome = transport.dispatch(request, decision.permission,
                                     scenario=scenario)
        assert outcome["dispatched"] is True, scenario
        assert outcome["state"] == expected.value, (scenario, outcome)
        assert outcome["retry_attempted"] is False
        assert outcome["provider_calls"] == 1
        assert transport.provider_calls == 1


def test_c10_eof_is_not_success() -> None:
    boundary = _boundary()
    prepared, request, decision = _claimed(boundary)

    def eof(_request):
        raise EOFError("peer closed")

    transport = TrustedEgressTransport(boundary, provider=eof)
    outcome = transport.dispatch(request, decision.permission)
    assert outcome["dispatched"] is True
    assert outcome["state"] == AttemptState.BILLABLE_UNKNOWN.value
    assert outcome["retry_attempted"] is False
    assert transport.provider_calls == 1


def test_c11_usage_shapes_never_settle_as_free() -> None:
    for usage in (None, {}, {"inputTokens": 7},
                  {"outputTokens": 3}, {"totalTokens": 10}):
        boundary2 = _boundary()
        prepared2, request2, decision2 = _claimed(boundary2)
        transport2 = TrustedEgressTransport(
            boundary2, provider=lambda _req, usage=usage: {
                "status": 200, "usage": usage, "error": None})
        outcome = transport2.dispatch(request2, decision2.permission)
        assert outcome["state"] == AttemptState.BILLABLE_UNKNOWN.value, usage
        assert outcome["classification"] != "RESPONSE_COMPLETED"
        assert "FREE" not in outcome["state"]


def test_c11_conflicting_usage_is_not_a_success_shape() -> None:
    boundary = _boundary()
    prepared, request, decision = _claimed(boundary)
    transport = TrustedEgressTransport(
        boundary, provider=lambda _req: {
            "status": 200,
            "usage": {"inputTokens": 1, "outputTokens": 1},
            "error": "usage_conflict"})
    outcome = transport.dispatch(request, decision.permission)
    assert outcome["state"] == AttemptState.BILLABLE_UNKNOWN.value
    assert outcome["retry_attempted"] is False
