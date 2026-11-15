#!/usr/bin/env python3
"""PR4a egress boundary/failure-matrix verifier (no key, no network, no model).

Runs inside the fixed no-Key OCI. It exercises the in-process transport observer,
the allowlist/deny prototype, request counters and stable call IDs, then prints a
JSON report and exits non-zero if any invariant fails. It cannot and does not
prove real provider wire/retry behaviour: the locked OCI denies socket() creation
(recorded below), so provider-internal HTTP attempts remain LIMITATION/UNVERIFIED
and Live stays BLOCKED.
"""
from __future__ import annotations

import hashlib
import json

from autoteacher_m0.security.egress import (
    AttemptState, ClaimResult, EgressBoundary, EgressPolicy, EgressRequest,
    EgressViolation, MockEgressTransport, TrustedEgressTransport, policy_from_json,
)

CHECKS: list[dict] = []
FAILURES: list[str] = []


def check(name: str, condition: bool, detail: object = None) -> None:
    CHECKS.append({"name": name, "ok": bool(condition), "detail": detail})
    if not condition:
        FAILURES.append(name)


CALL_ID = "call-" + "a" * 48
REQUEST_DIGEST = "a" * 64


class AlwaysClaimer:
    def claim(self, request: EgressRequest) -> ClaimResult:
        return ClaimResult(True, "CLAIMED", (), {"call_id": request.call_id})


def request(**overrides: object) -> EgressRequest:
    base = dict(logical_stream_id="stream-pr4a-1", reservation_id="res-pr4a-1",
                attempt_ordinal=1, route_id="opencode-go", model="deepseek-v4.1-flash",
                call_id=CALL_ID, request_digest=REQUEST_DIGEST)
    base.update(overrides)
    if "call_id" not in overrides:
        material = "|".join(str(base[key]) for key in
                            ("logical_stream_id", "reservation_id", "attempt_ordinal",
                             "route_id", "model", "request_digest"))
        base["call_id"] = "call-" + hashlib.sha256(material.encode()).hexdigest()[:48]
    return EgressRequest(**base)


def main() -> int:
    boundary = EgressBoundary()

    allowed = boundary.require(request())
    check("approved_request_allowed", allowed.allowed and allowed.call_id.startswith("call-"))
    same = boundary.authorize(request())
    check("stable_call_id_is_deterministic", same.call_id == allowed.call_id)
    next_attempt = boundary.authorize(request(attempt_ordinal=2))
    check("call_id_changes_per_attempt", next_attempt.call_id != allowed.call_id)

    deny_cases = {
        "no_reservation": request(reservation_id=""),
        "unapproved_route_model": request(model="deepseek-flash"),
        "host_not_allowed": request(host="api.deepseek.com"),
        "port_not_allowed": request(port=80),
        "path_not_allowed": request(path="/v1/chat/completions"),
        "method_not_allowed": request(method="GET"),
        "max_tokens_exceeded": request(max_tokens=9999),
        "files_not_permitted": request(has_files=True),
        "images_not_permitted": request(has_images=True),
        "store_not_permitted": request(store=True),
    }
    for name, candidate in deny_cases.items():
        decision = boundary.authorize(candidate)
        check(f"deny_{name}", not decision.allowed, decision.reasons)
        try:
            boundary.require(candidate)
            check(f"require_raises_{name}", False)
        except EgressViolation:
            check(f"require_raises_{name}", True)
    boundary.require(request())  # keep stream alive for limit check
    limited = EgressBoundary(EgressPolicy(max_attempts=1))
    limited.require(request())
    decision = limited.authorize(request(attempt_ordinal=2))
    check("attempt_limit_denied", not decision.allowed and "ATTEMPT_LIMIT_EXCEEDED" in decision.reasons)

    matrix = {}
    for scenario in MockEgressTransport.SCENARIOS:
        cases = EgressBoundary(claimer=AlwaysClaimer())
        stream = f"stream-{scenario}"
        candidate = request(logical_stream_id=stream, reservation_id=f"res-{scenario}")
        grant = cases.claim_dispatch(candidate)
        result = MockEgressTransport.SCENARIOS[scenario]

        def provider(_request):
            return result

        probe = TrustedEgressTransport(cases, provider)
        outcome = probe.dispatch(candidate, grant.permission)
        state = cases.stream(stream).state.value
        matrix[scenario] = {"dispatched": outcome["dispatched"], "state": state,
                            "retry_attempted": outcome["retry_attempted"],
                            "usage_known": outcome.get("usage_known")}
        expected = {"ok_usage": AttemptState.SETTLED_USAGE.value,
                    "http_401": AttemptState.NOT_BILLABLE_HTTP_ERROR.value,
                    "http_429": AttemptState.NOT_BILLABLE_HTTP_ERROR.value,
                    "http_500": AttemptState.BILLABLE_UNKNOWN.value,
                    "http_503": AttemptState.BILLABLE_UNKNOWN.value}.get(scenario)
        if expected is not None:
            check(f"matrix_{scenario}", state == expected, state)
        if scenario in {"ok_no_usage", "ok_partial_usage", "timeout", "hang",
                        "disconnect", "unknown_transport"}:
            check(f"matrix_unknown_not_zero_{scenario}",
                  state == AttemptState.BILLABLE_UNKNOWN.value
                  and cases.stream(stream).worst_case_held_usd > 0, state)
        check(f"matrix_no_retry_{scenario}", outcome["retry_attempted"] is False)
        check(f"matrix_provider_calls_{scenario}", probe.provider_calls == 1)

    policy = policy_from_json({"max_tokens": 512, "max_attempts": 2})
    check("policy_json_roundtrip", policy.max_tokens == 512 and policy.max_attempts == 2)
    try:
        policy_from_json({"bogus": True})
        check("policy_rejects_unknown_field", False)
    except ValueError:
        check("policy_rejects_unknown_field", True)

    socket_denied = None
    try:
        import socket
        socket.socket()
        socket_denied = False
    except PermissionError as error:
        socket_denied = True
        socket_error = type(error).__name__
    except OSError as error:
        socket_denied = True
        socket_error = type(error).__name__
    check("locked_oci_denies_sockets", socket_denied is True, socket_error)
    report = {"status": "PASS" if not FAILURES else "FAIL", "failures": FAILURES,
              "checks": CHECKS, "matrix": matrix,
              "boundary_snapshot": boundary.snapshot(),
              "limitations": [
                  "real provider wire/retry/cache/files NOT observed: locked OCI denies socket()",
                  "mock transport results are synthetic; never provider bills",
                  "no accounting/broker state written here; reservation id is an interface placeholder",
              ]}
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not FAILURES else 30


if __name__ == "__main__":
    raise SystemExit(main())
