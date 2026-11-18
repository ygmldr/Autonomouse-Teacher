"""Shared TEST_ONLY helpers for the G4-C contract/gate host tests."""
from __future__ import annotations

import hashlib
from dataclasses import replace

from autoteacher_m0.security.authorization import ExpectedBindings
from autoteacher_m0.security.egress import (
    ClaimResult,
    DispatchPermission,
    EgressRequest,
    PreparedProviderRequest,
    SYNTHETIC_ROUTE_CONTRACT,
    TrustedSendGate,
    canonical_json,
    prepared_call_id,
    prepared_request_digest,
)

SCOPE = "g4c-scope"
RUN = "run-g4c-host"
RESERVATION = "res-g4c-1"


def same_bindings(seed: str = "a") -> ExpectedBindings:
    return ExpectedBindings(*([seed * 64] * 5))


def approved_tool() -> dict:
    """Exact frozen skill_lookup schema (canonical digest c984bef0...)."""
    return {
        "name": "skill_lookup",
        "description": ("Look up fixed public skill metadata by a nonempty skill "
                        "id. Unknown ids return SKILL_NOT_FOUND. No filesystem "
                        "paths are accepted."),
        "parameters": {
            "type": "object",
            "properties": {"skill_id": {
                "type": "string",
                "description": ("Nonempty stable skill id, e.g. binary_search; "
                                "not a filesystem path.")}},
            "required": ["skill_id"],
        },
    }


def make_prepared(*, tools: tuple[dict, ...] = (), step: int = 0,
                  max_tokens: int = 64, **overrides) -> PreparedProviderRequest:
    prepared = PreparedProviderRequest(
        scope_id=SCOPE, run_id=RUN, logical_step=step, attempt_index=0,
        route_id=SYNTHETIC_ROUTE_CONTRACT.route_id,
        provider=SYNTHETIC_ROUTE_CONTRACT.provider,
        model=SYNTHETIC_ROUTE_CONTRACT.model_id,
        host=SYNTHETIC_ROUTE_CONTRACT.endpoint_host,
        port=SYNTHETIC_ROUTE_CONTRACT.port,
        method="POST", path=SYNTHETIC_ROUTE_CONTRACT.exact_path,
        stream=True, max_output_tokens=max_tokens, system="",
        messages=({"role": "user", "content": "hello"},), tools=tools,
        response_format=None, retry_policy=None, has_files=False,
        has_images=False, store=False)
    digest = prepared_request_digest(prepared)
    prepared = replace(prepared, request_digest=digest,
                       call_id=prepared_call_id(prepared))
    if overrides:
        prepared = replace(prepared, **overrides)
    return prepared


def make_request(prepared: PreparedProviderRequest, *,
                 reservation: str = RESERVATION,
                 ordinal: int = 1) -> EgressRequest:
    return EgressRequest(
        logical_stream_id=f"stream-{prepared.logical_step}",
        reservation_id=reservation, attempt_ordinal=ordinal,
        route_id=prepared.route_id, model=prepared.model,
        host=prepared.host, port=prepared.port, method=prepared.method,
        path=prepared.path, stream=prepared.stream,
        max_tokens=prepared.max_output_tokens,
        call_id=prepared.call_id, request_digest=prepared.request_digest,
        estimated_cost_usd="0.001")


def make_payload(prepared: PreparedProviderRequest, *, mode: str = "echo",
                 nonce: str = "00" * 16) -> bytes:
    document = {
        "schema": SYNTHETIC_ROUTE_CONTRACT.request_format_version,
        "call_id": prepared.call_id,
        "prepared_digest": prepared.request_digest,
        "route_id": prepared.route_id,
        "model": prepared.model,
        "messages": [dict(item) for item in prepared.messages],
        "tools": [dict(item) for item in prepared.tools],
        "system": prepared.system,
        "max_output_tokens": prepared.max_output_tokens,
        "stream": True,
        "mode": mode,
        "nonce": nonce,
    }
    return canonical_json(document).encode("utf-8")


def make_claim(prepared: PreparedProviderRequest, *,
               reservation: str = RESERVATION) -> dict:
    return {"call_id": prepared.call_id, "reservation_id": reservation,
            "request_digest": prepared.request_digest, "status": "CLAIMED"}


def make_permission(prepared: PreparedProviderRequest, claim: dict,
                    *, reservation: str = RESERVATION,
                    ordinal: int = 1) -> DispatchPermission:
    return DispatchPermission(
        ClaimResult(True, "CLAIMED", (), claim), prepared.call_id,
        prepared.request_digest, f"stream-{prepared.logical_step}",
        reservation, ordinal,
        (SYNTHETIC_ROUTE_CONTRACT.route_id, SYNTHETIC_ROUTE_CONTRACT.model_id))


def claim_digest(claim: dict) -> str:
    return hashlib.sha256(canonical_json(claim).encode("utf-8")).hexdigest()


def make_gate(*, binding_approved=None, binding_observer=None, contract=None,
              **kwargs) -> TrustedSendGate:
    approved = binding_approved if binding_approved is not None else same_bindings()
    observer = binding_observer if binding_observer is not None else (
        lambda: approved)
    return TrustedSendGate(
        contract or SYNTHETIC_ROUTE_CONTRACT,
        auth_epoch=kwargs.pop("auth_epoch", "epoch-g4c"),
        binding_approved=approved, binding_observer=observer, **kwargs)


def authorize(gate: TrustedSendGate, prepared: PreparedProviderRequest | None = None,
              request: EgressRequest | None = None, *,
              payload: bytes | None = None,
              permission: DispatchPermission | None = None,
              claim: dict | None = None,
              reservation: str = RESERVATION,
              **kwargs):
    prepared = prepared or make_prepared()
    request = request or make_request(prepared, reservation=reservation)
    payload = payload if payload is not None else make_payload(prepared)
    claim = claim or make_claim(prepared, reservation=reservation)
    permission = permission or make_permission(prepared, claim,
                                               reservation=reservation,
                                               ordinal=request.attempt_ordinal)
    cost = kwargs.pop("estimated_cost_usd", request.estimated_cost_usd)
    return gate.authorize(
        prepared=prepared, request=request, permission=permission,
        payload_bytes=payload, payload_digest=hashlib.sha256(payload).hexdigest(),
        payload_length=len(payload), reservation_id=reservation,
        broker_claim_id=prepared.call_id,
        broker_claim_digest=claim_digest(claim),
        estimated_cost_usd=cost, **kwargs)
