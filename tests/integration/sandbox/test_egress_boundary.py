"""PR4a egress boundary prototype tests; in-process only, no sockets/network/key.

Runs inside the fixed no-Key OCI test container. NullModel/transport outcomes are
synthetic observers, not provider wire evidence; Live stays BLOCKED.
"""
from __future__ import annotations
import pytest

from autoteacher_m0.security.egress import (
    AttemptState, EgressBoundary, EgressPolicy, EgressRequest, EgressViolation,
    MockEgressTransport, policy_from_json,
)


def req(**overrides):
    base = dict(logical_stream_id="s1", reservation_id="r1", attempt_ordinal=1,
                route_id="opencode-go", model="deepseek-v4.1-flash")
    base.update(overrides)
    return EgressRequest(**base)


def test_allowlist_allows_only_approved_route_and_call_ids_are_stable():
    boundary = EgressBoundary()
    first = boundary.require(req())
    assert first.call_id.startswith("eg-") and len(first.call_id) == 27
    assert boundary.authorize(req()).call_id == first.call_id
    assert boundary.authorize(req(attempt_ordinal=2)).call_id != first.call_id


@pytest.mark.parametrize("overrides,reason", [
    ({"reservation_id": ""}, "NO_RESERVATION"),
    ({"model": "deepseek-flash"}, "ROUTE_MODEL_NOT_APPROVED"),
    ({"host": "api.deepseek.com"}, "HOST_PORT_NOT_ALLOWED"),
    ({"port": 80}, "HOST_PORT_NOT_ALLOWED"),
    ({"path": "/v1/chat/completions"}, "PATH_NOT_ALLOWED"),
    ({"method": "GET"}, "METHOD_NOT_ALLOWED"),
    ({"max_tokens": 4096}, "MAX_TOKENS_EXCEEDED"),
    ({"has_files": True}, "FILES_NOT_PERMITTED"),
    ({"has_images": True}, "IMAGES_NOT_PERMITTED"),
    ({"store": True}, "STORE_NOT_PERMITTED"),
])
def test_unapproved_requests_denied_before_dispatch(overrides, reason):
    boundary = EgressBoundary()
    decision = boundary.authorize(req(**overrides))
    assert decision.allowed is False and reason in decision.reasons
    with pytest.raises(EgressViolation):
        boundary.require(req(**overrides))


def test_attempt_limit_denied():
    boundary = EgressBoundary(EgressPolicy(max_attempts=2))
    boundary.require(req())
    boundary.require(req(attempt_ordinal=2))
    decision = boundary.authorize(req(attempt_ordinal=3))
    assert "ATTEMPT_LIMIT_EXCEEDED" in decision.reasons


@pytest.mark.parametrize("scenario,state", [
    ("ok_usage", AttemptState.SETTLED_USAGE.value),
    ("http_401", AttemptState.NOT_BILLABLE_HTTP_ERROR.value),
    ("http_429", AttemptState.NOT_BILLABLE_HTTP_ERROR.value),
    ("http_500", AttemptState.BILLABLE_UNKNOWN.value),
    ("http_503", AttemptState.BILLABLE_UNKNOWN.value),
    ("ok_no_usage", AttemptState.BILLABLE_UNKNOWN.value),
    ("ok_partial_usage", AttemptState.BILLABLE_UNKNOWN.value),
    ("timeout", AttemptState.BILLABLE_UNKNOWN.value),
    ("hang", AttemptState.BILLABLE_UNKNOWN.value),
    ("disconnect", AttemptState.BILLABLE_UNKNOWN.value),
    ("unknown_transport", AttemptState.BILLABLE_UNKNOWN.value),
])
def test_failure_matrix_never_treats_unknown_as_zero(scenario, state):
    boundary = EgressBoundary()
    outcome = MockEgressTransport(boundary).dispatch(req(), scenario)
    assert outcome["state"] == state and outcome["retry_attempted"] is False
    stream = boundary.stream("s1")
    if state == AttemptState.BILLABLE_UNKNOWN.value:
        assert stream.worst_case_held_usd > 0


def test_policy_loader_rejects_unknown_fields():
    assert policy_from_json({"max_attempts": 2}).max_attempts == 2
    with pytest.raises(ValueError):
        policy_from_json({"arbitrary": True})
