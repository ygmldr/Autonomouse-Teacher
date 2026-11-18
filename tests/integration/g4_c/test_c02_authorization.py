"""G4-C TrustedSendAuthorization: binding, single use, fail-closed negatives."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json

import pytest

from autoteacher_m0.security.egress import (
    EgressViolation,
    REAL_ROUTE_TEMPLATE,
    SyntheticSendBudget,
    TrustedSendAuthorization,
    TrustedSendGate,
)
from g4c_support import (
    RESERVATION, authorize, claim_digest, make_claim, make_gate, make_payload,
    make_permission, make_prepared, make_request, same_bindings, approved_tool,
)


def _reasons(exc: pytest.ExceptionInfo[EgressViolation]) -> tuple[str, ...]:
    return tuple(exc.value.reasons)


def test_c02_authorization_binds_every_required_field() -> None:
    prepared = make_prepared()
    gate = make_gate()
    auth = authorize(gate, prepared)
    assert isinstance(auth, TrustedSendAuthorization)
    assert auth.scope_id == prepared.scope_id
    assert auth.run_id == prepared.run_id
    assert auth.call_id == prepared.call_id
    assert auth.prepared_digest == prepared.request_digest
    assert auth.reservation_id == RESERVATION
    assert auth.broker_claim_id == prepared.call_id
    assert auth.broker_claim_digest == claim_digest(make_claim(prepared))
    assert auth.payload_length == len(make_payload(prepared))
    assert auth.attempt_ordinal == 1
    assert auth.route_id == prepared.route_id
    assert auth.model_id == prepared.model
    assert auth.auth_epoch == "epoch-g4c"
    assert auth.expires_utc > auth.issued_utc
    assert auth.synthetic is True and auth.route_kind == "synthetic_fixture"
    assert auth.to_audit_dict()["payload_digest"] == auth.payload_digest


def test_c02_no_json_constructor_or_parser_exists() -> None:
    for name in ("from_json", "from_dict", "parse", "load", "from_mapping"):
        assert not hasattr(TrustedSendAuthorization, name)
    assert not hasattr(TrustedSendGate, "authorize_from_json")


def test_c02_consume_once_then_replay_rejected() -> None:
    prepared = make_prepared()
    payload = make_payload(prepared)
    gate = make_gate()
    auth = authorize(gate, prepared, payload=payload)
    assert gate.consume(auth, payload_bytes=payload) is None
    assert gate.consume(auth, payload_bytes=payload) == "AUTHORIZATION_REPLAYED"


def test_c02_reconstructed_from_audit_dict_is_not_a_credential() -> None:
    prepared = make_prepared()
    payload = make_payload(prepared)
    gate = make_gate()
    auth = authorize(gate, prepared, payload=payload)
    with pytest.raises(TypeError):
        TrustedSendAuthorization(**auth.to_audit_dict())
    forged = replace(auth)
    assert gate.consume(forged, payload_bytes=payload) == "AUTHORIZATION_UNKNOWN"
    assert gate.consume({"authorization_id": auth.authorization_id},
                        payload_bytes=payload) == "AUTHORIZATION_UNKNOWN"


def test_c02_payload_mutation_after_authorization_never_sends() -> None:
    prepared = make_prepared()
    payload = make_payload(prepared)
    gate = make_gate()
    auth = authorize(gate, prepared, payload=payload)
    tampered = payload.replace(b'"echo"', b'"tool_final"')
    assert tampered != payload
    assert gate.consume(auth, payload_bytes=tampered) == "PAYLOAD_LENGTH_MISMATCH" \
        or gate.consume(auth, payload_bytes=tampered) == "PAYLOAD_DIGEST_MISMATCH" \
        or gate.consume(auth, payload_bytes=tampered) == "AUTHORIZATION_UNKNOWN"


def test_c02_payload_digest_mismatch_denied_at_authorize() -> None:
    prepared = make_prepared()
    payload = make_payload(prepared)
    gate = make_gate()
    claim = make_claim(prepared)
    permission = make_permission(prepared, claim)
    request = make_request(prepared)
    with pytest.raises(EgressViolation) as exc:
        gate.authorize(
            prepared=prepared, request=request, permission=permission,
            payload_bytes=payload, payload_digest="f" * 64,
            payload_length=len(payload), reservation_id=RESERVATION,
            broker_claim_id=prepared.call_id,
            broker_claim_digest=claim_digest(claim),
            estimated_cost_usd="0.001")
    assert "PAYLOAD_DIGEST_MISMATCH" in _reasons(exc)


def test_c02_prepared_changed_after_claim_denied() -> None:
    prepared = make_prepared()
    claim = make_claim(prepared)
    request = make_request(prepared)
    permission = make_permission(prepared, claim)
    mutated = replace(prepared, max_output_tokens=32)
    payload = make_payload(prepared)
    gate = make_gate()
    with pytest.raises(EgressViolation) as exc:
        gate.authorize(
            prepared=mutated, request=request, permission=permission,
            payload_bytes=payload, payload_digest=__import__("hashlib").sha256(
                payload).hexdigest(), payload_length=len(payload),
            reservation_id=RESERVATION, broker_claim_id=prepared.call_id,
            broker_claim_digest=claim_digest(claim),
            estimated_cost_usd="0.001")
    assert "PREPARED_DIGEST_MISMATCH" in _reasons(exc)


@pytest.mark.parametrize("field,value,expected", [
    ("route_id", "opencode-go", "ROUTE_CONTRACT_MISMATCH:route_id"),
    ("provider", "opencode-go", "ROUTE_CONTRACT_MISMATCH:provider"),
    ("model", "deepseek-v4.1-flash", "ROUTE_CONTRACT_MISMATCH:model_id"),
    ("host", "opencode.ai", "ROUTE_CONTRACT_MISMATCH:host"),
    ("port", 443, "ROUTE_CONTRACT_MISMATCH:port"),
    ("method", "PUT", "ROUTE_CONTRACT_MISMATCH:method"),
    ("path", "/inference/go/openai/v1/chat/completions",
     "ROUTE_CONTRACT_MISMATCH:path"),
    ("max_output_tokens", 2048, "MAX_TOKENS_EXCEEDED"),
    ("retry_policy", {"mode": "retry"}, "RETRY_POLICY_NOT_APPROVED"),
    ("has_files", True, "HAS_FILES_NOT_PERMITTED"),
    ("has_images", True, "HAS_IMAGES_NOT_PERMITTED"),
    ("store", True, "STORE_NOT_PERMITTED"),
])
def test_c02_route_and_flag_tamper_fail_closed(field, value, expected) -> None:
    prepared = make_prepared()
    request = make_request(prepared)
    claim = make_claim(prepared)
    permission = make_permission(prepared, claim)
    mutated = replace(prepared, **{field: value})
    payload = make_payload(prepared)
    gate = make_gate()
    with pytest.raises(EgressViolation) as exc:
        gate.authorize(
            prepared=mutated, request=request, permission=permission,
            payload_bytes=payload, payload_digest=__import__("hashlib").sha256(
                payload).hexdigest(), payload_length=len(payload),
            reservation_id=RESERVATION, broker_claim_id=prepared.call_id,
            broker_claim_digest=claim_digest(claim),
            estimated_cost_usd="0.001")
    assert expected in _reasons(exc)


def test_c02_request_tamper_after_prepared_denied() -> None:
    prepared = make_prepared()
    request = replace(make_request(prepared), path="/v1/g3b/other")
    claim = make_claim(prepared)
    permission = make_permission(prepared, claim)
    payload = make_payload(prepared)
    gate = make_gate()
    with pytest.raises(EgressViolation) as exc:
        gate.authorize(
            prepared=prepared, request=request, permission=permission,
            payload_bytes=payload, payload_digest=__import__("hashlib").sha256(
                payload).hexdigest(), payload_length=len(payload),
            reservation_id=RESERVATION, broker_claim_id=prepared.call_id,
            broker_claim_digest=claim_digest(claim),
            estimated_cost_usd="0.001")
    assert "ROUTE_CONTRACT_MISMATCH:request_path" in _reasons(exc)


def test_c02_unapproved_tool_schema_denied() -> None:
    tool = approved_tool()
    prepared = make_prepared(tools=(tool,))
    request = make_request(prepared)
    claim = make_claim(prepared)
    permission = make_permission(prepared, claim)
    payload = make_payload(prepared)
    gate = make_gate()
    auth = gate.authorize(
        prepared=prepared, request=request, permission=permission,
        payload_bytes=payload, payload_digest=__import__("hashlib").sha256(
            payload).hexdigest(), payload_length=len(payload),
        reservation_id=RESERVATION, broker_claim_id=prepared.call_id,
        broker_claim_digest=claim_digest(claim), estimated_cost_usd="0.001")
    assert gate.consume(auth, payload_bytes=payload) is None

    tampered = dict(tool)
    tampered["parameters"] = {"type": "object",
                              "properties": {"path": {"type": "string"}}}
    prepared_bad = make_prepared(tools=(tampered,))
    with pytest.raises(EgressViolation) as exc:
        gate.authorize(
            prepared=prepared_bad, request=make_request(prepared_bad),
            permission=make_permission(prepared_bad, make_claim(prepared_bad)),
            payload_bytes=make_payload(prepared_bad),
            payload_digest=__import__("hashlib").sha256(
                make_payload(prepared_bad)).hexdigest(),
            payload_length=len(make_payload(prepared_bad)),
            reservation_id=RESERVATION, broker_claim_id=prepared_bad.call_id,
            broker_claim_digest=claim_digest(make_claim(prepared_bad)),
            estimated_cost_usd="0.001")
    assert "TOOL_SCHEMA_NOT_APPROVED" in _reasons(exc)


def test_c02_broker_claim_and_permission_binding_must_match() -> None:
    prepared = make_prepared()
    request = make_request(prepared)
    payload = make_payload(prepared)
    gate = make_gate()
    other_claim = make_claim(prepared)
    other_claim["request_digest"] = "e" * 64
    with pytest.raises(EgressViolation) as exc:
        gate.authorize(
            prepared=prepared, request=request,
            permission=make_permission(prepared, other_claim),
            payload_bytes=payload,
            payload_digest=__import__("hashlib").sha256(payload).hexdigest(),
            payload_length=len(payload), reservation_id=RESERVATION,
            broker_claim_id=prepared.call_id,
            broker_claim_digest=claim_digest(other_claim),
            estimated_cost_usd="0.001")
    assert "BROKER_CLAIM_DIGEST_MISMATCH" in _reasons(exc)


def test_c02_no_permission_denied() -> None:
    prepared = make_prepared()
    payload = make_payload(prepared)
    gate = make_gate()
    with pytest.raises(EgressViolation) as exc:
        gate.authorize(
            prepared=prepared, request=make_request(prepared), permission=None,
            payload_bytes=payload,
            payload_digest=__import__("hashlib").sha256(payload).hexdigest(),
            payload_length=len(payload), reservation_id=RESERVATION,
            broker_claim_id=prepared.call_id,
            broker_claim_digest=claim_digest(make_claim(prepared)),
            estimated_cost_usd="0.001")
    assert "DISPATCH_PERMISSION_REQUIRED" in _reasons(exc)


def test_c02_expiry_and_epoch_are_enforced() -> None:
    start = datetime(2026, 11, 18, 12, 0, 0, tzinfo=timezone.utc)
    clock = {"now": start}
    gate = make_gate(now=lambda: clock["now"])
    prepared = make_prepared()
    payload = make_payload(prepared)
    auth = authorize(gate, prepared, payload=payload)
    clock["now"] = start + timedelta(seconds=31)
    assert gate.consume(auth, payload_bytes=payload) == "AUTHORIZATION_EXPIRED"

    other = make_gate(auth_epoch="epoch-other")
    auth2 = authorize(other, prepared)
    other.auth_epoch = "epoch-mutated"
    assert other.consume(auth2, payload_bytes=make_payload(prepared)) == \
        "AUTH_EPOCH_MISMATCH"


def test_c02_soft_and_hard_budget_boundaries() -> None:
    prepared = make_prepared()
    request = make_request(prepared)
    payload = make_payload(prepared)
    soft_budget = SyntheticSendBudget(
        soft_total_usd=__import__("decimal").Decimal("0.0005"),
        hard_total_usd=__import__("decimal").Decimal("10.00"),
        soft_call_usd=__import__("decimal").Decimal("0.0001"),
        hard_call_usd=__import__("decimal").Decimal("0.20"),
        max_sends=50)
    gate = make_gate(budget=soft_budget)
    claim = make_claim(prepared)
    auth = gate.authorize(
        prepared=prepared, request=request,
        permission=make_permission(prepared, claim), payload_bytes=payload,
        payload_digest=__import__("hashlib").sha256(payload).hexdigest(),
        payload_length=len(payload), reservation_id=RESERVATION,
        broker_claim_id=prepared.call_id, broker_claim_digest=claim_digest(claim),
        estimated_cost_usd="0.001")
    assert auth is not None
    assert any(event["kind"] == "soft_total"
               for event in gate.snapshot()["soft_events"])

    hard_budget = SyntheticSendBudget(
        soft_total_usd=__import__("decimal").Decimal("0.001"),
        hard_total_usd=__import__("decimal").Decimal("0.0015"),
        soft_call_usd=__import__("decimal").Decimal("0.0001"),
        hard_call_usd=__import__("decimal").Decimal("0.001"),
        max_sends=50)
    hard_gate = make_gate(budget=hard_budget)
    hard_gate.authorize(
        prepared=prepared, request=request,
        permission=make_permission(prepared, claim), payload_bytes=payload,
        payload_digest=__import__("hashlib").sha256(payload).hexdigest(),
        payload_length=len(payload), reservation_id=RESERVATION,
        broker_claim_id=prepared.call_id, broker_claim_digest=claim_digest(claim),
        estimated_cost_usd="0.001")
    with pytest.raises(EgressViolation) as exc:
        hard_gate.authorize(
            prepared=prepared, request=request,
            permission=make_permission(prepared, claim), payload_bytes=payload,
            payload_digest=__import__("hashlib").sha256(payload).hexdigest(),
            payload_length=len(payload), reservation_id=RESERVATION,
            broker_claim_id=prepared.call_id,
            broker_claim_digest=claim_digest(claim),
            estimated_cost_usd="0.001")
    assert "HARD_BUDGET_CEILING_EXCEEDED" in _reasons(exc)


def test_c02_per_call_budget_and_unknown_cost() -> None:
    prepared = make_prepared()
    payload = make_payload(prepared)
    gate = make_gate()
    with pytest.raises(EgressViolation) as exc:
        authorize(gate, prepared, payload=payload,
                   estimated_cost_usd="10.01")
    reasons = _reasons(exc)
    assert "PER_CALL_BUDGET_EXCEEDED" in reasons
    assert "HARD_BUDGET_CEILING_EXCEEDED" in reasons
    with pytest.raises(EgressViolation) as exc:
        authorize(gate, prepared, payload=payload, estimated_cost_usd="not-a-number")
    assert "COST_UNKNOWN" in _reasons(exc)


def test_c02_real_route_gate_never_authorizes() -> None:
    gate = make_gate(contract=REAL_ROUTE_TEMPLATE)
    with pytest.raises(EgressViolation) as exc:
        authorize(gate)
    reasons = _reasons(exc)
    assert "REAL_ROUTE_BLOCKED_REQUIRES_HUMAN_VERIFICATION" in reasons
    assert "PRICING_SOURCE_UNVERIFIED" in reasons


def test_c02_pre_dispatch_binding_check_wiring() -> None:
    prepared = make_prepared()
    payload = make_payload(prepared)
    approved = same_bindings("a")
    drifted = same_bindings("b")
    gate = make_gate(binding_approved=approved, binding_observer=lambda: drifted)
    with pytest.raises(EgressViolation) as exc:
        authorize(gate, prepared, payload=payload)
    assert any(reason.startswith("BINDING_DRIFT:PRE_DISPATCH:")
               for reason in _reasons(exc))

    incomplete = TrustedSendGate.__new__(TrustedSendGate)
    configured = make_gate()
    incomplete.__dict__.update(configured.__dict__)
    incomplete.binding_approved = None
    with pytest.raises(EgressViolation) as exc:
        authorize(incomplete, prepared, payload=payload)
    assert "PRE_DISPATCH_CHECK_INCOMPLETE" in _reasons(exc)

    def boom():
        raise RuntimeError("observer failed")

    failing = make_gate(binding_observer=boom)
    with pytest.raises(EgressViolation) as exc:
        authorize(failing, prepared, payload=payload)
    assert "PRE_DISPATCH_CHECK_ERROR" in _reasons(exc)


def test_c02_audit_journal_records_authorize_and_consume(tmp_path) -> None:
    journal = tmp_path / "journal.jsonl"
    gate = make_gate(journal_path=journal)
    prepared = make_prepared()
    payload = make_payload(prepared)
    auth = authorize(gate, prepared, payload=payload)
    assert gate.consume(auth, payload_bytes=payload) is None
    decisions = [json.loads(line)["decision"]
                 for line in journal.read_text(encoding="utf-8").splitlines()]
    assert decisions == ["AUTHORIZED", "CONSUMED"]


def test_c02_epoch_must_be_nonempty() -> None:
    with pytest.raises(ValueError):
        TrustedSendGate(__import__("autoteacher_m0.security.egress",
                                   fromlist=["SYNTHETIC_ROUTE_CONTRACT"]
                                   ).SYNTHETIC_ROUTE_CONTRACT, auth_epoch="")
