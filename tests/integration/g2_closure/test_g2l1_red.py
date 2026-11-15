"""A0 RED: G2-L1 fail-first tests against the pre-fix G2 code.

These tests are intentionally written against the expected post-fix API/behavior.
On the frozen G2 baseline (32bea5b) they must fail; the A0 design xfail placeholders
were converted/removed in A1/A2 and real BIND coverage lives in test_g2l1_fix.py.
No sockets, credentials, real model or external network are used.
"""
from __future__ import annotations

import pytest

from autoteacher_m0.security.egress import (
    EgressBoundary,
    EgressRequest,
    EgressViolation,
    MockEgressTransport,
    policy_from_json,
)

CALL_ID = "call-" + "a" * 48
REQUEST_DIGEST = "b" * 64


def request(**overrides: object) -> EgressRequest:
    values: dict[str, object] = {
        "logical_stream_id": "g2l1-red-stream",
        "reservation_id": "reservation-red-1",
        "attempt_ordinal": 1,
        "route_id": "opencode-go",
        "model": "deepseek-v4.1-flash",
        "call_id": CALL_ID,
        "request_digest": REQUEST_DIGEST,
    }
    values.update(overrides)
    return EgressRequest(**values)  # type: ignore[arg-type]


# ---------------------------------------------------------------- L1-b
def test_l1b_claim_dispatch_without_claimer_denies() -> None:
    boundary = EgressBoundary()
    decision = boundary.claim_dispatch(request())
    assert decision.allowed is False, "claim_dispatch must fail-closed without a Claimer"


def test_l1b_require_claim_without_claimer_raises() -> None:
    boundary = EgressBoundary()
    with pytest.raises(EgressViolation):
        boundary.require_claim(request())


# ---------------------------------------------------------------- L1-d
def test_l1d_mock_transport_without_claimer_must_not_dispatch() -> None:
    boundary = EgressBoundary()
    outcome = MockEgressTransport(boundary).dispatch(request(), "ok_usage")
    assert outcome["dispatched"] is False, "Mock fallback must not dispatch without claimer"


# ---------------------------------------------------------------- L1-e
@pytest.mark.parametrize("payload", [
    {"allow_files": "false"},
    {"allow_store": "0"},
    {"max_tokens": "256"},
    {"require_reservation": 0},
])
def test_l1e_policy_loader_rejects_bool_int_coercion(payload: dict[str, object]) -> None:
    with pytest.raises((TypeError, ValueError)):
        policy_from_json(payload)


# ---------------------------------------------------------------- bool/int confusion
@pytest.mark.parametrize("overrides", [
    {"max_tokens": True},
    {"attempt_ordinal": True},
    {"stream": 0},
])
def test_bool_int_confusion_is_denied(overrides: dict[str, object]) -> None:
    boundary = EgressBoundary()
    decision = boundary.authorize(request(**overrides))
    assert decision.allowed is False, f"bool/int confusion must be denied: {overrides!r}"


# ---------------------------------------------------------------- A1 design tests
def test_l1a_l1c_descriptor_evaluation_is_not_send_permission() -> None:
    """Descriptor policy evaluation must not be a formal send permission.

    Post-fix: evaluate_descriptor() returns policy-only evaluation; require_claim()
    remains the only formal dispatch admission and must fail without a Claimer.
    """
    boundary = EgressBoundary()
    evaluator = getattr(boundary, "evaluate_descriptor", None)
    assert callable(evaluator), "A1 requires evaluate_descriptor()"
    evaluation = evaluator(request())
    assert evaluation.allowed is True
    with pytest.raises(EgressViolation):
        boundary.require_claim(request())
