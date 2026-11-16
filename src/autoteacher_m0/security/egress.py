"""PR4a egress boundary: descriptor diagnostics and trusted send admission.

This module is transport-observer/security scaffolding, not a network proxy and
NOT a Live unlock. Provider calls are injected; the locked OCI denies sockets.
Descriptor evaluation (`evaluate_descriptor`/`authorize`/`require`) is policy-only
and can never drive a send. Only `claim_dispatch()` may create a
`DispatchPermission` after a trusted claim, and only a `TrustedEgressTransport`
may consume that permission and invoke the injected provider.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
import hashlib
import re
from typing import Callable, Iterable, Mapping, Protocol, Sequence

from autoteacher_m0.accounting.call_identity import (
    IdentitySchemaError, canonical_json, validate_run_id,
)
from autoteacher_m0.contracts import ErrorCode, RuntimeFailure

OPENCODE_GO_HOST = "opencode.ai"
OPENCODE_GO_PORT = 443
OPENCODE_GO_PATH_PREFIX = "/inference/go/"
MAX_ATTEMPTS_PER_STREAM = 4
MAX_OUTPUT_TOKENS = 1024
CALL_ID_RE = re.compile(r"call-[0-9a-f]{48}\Z", re.ASCII)
REQUEST_DIGEST_RE = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
BROKER_CLAIMER_UNAVAILABLE = "BROKER_CLAIMER_UNAVAILABLE"
BROKER_CLAIMER_ERROR = "BROKER_CLAIMER_ERROR"
BROKER_CLAIMER_BAD_REPLY = "BROKER_CLAIMER_BAD_REPLY"
BROKER_CLAIMER_BOUND_UNSUPPORTED = "CLAIM_BINDING_UNSUPPORTED"
PREPARED_REQUEST_INVALID = "PREPARED_REQUEST_INVALID"
PREPARED_DIGEST_MISMATCH = "PREPARED_DIGEST_MISMATCH"
RESERVATION_REQUEST_MISMATCH = "RESERVATION_REQUEST_MISMATCH"
TOOL_SCHEMA_NOT_APPROVED = "TOOL_SCHEMA_NOT_APPROVED"
PREPARED_SCHEMA_INVALID = "PREPARED_SCHEMA_INVALID"
PREPARED_SCHEMA_VERSION_MISMATCH = "PREPARED_SCHEMA_VERSION_MISMATCH"


class EgressViolation(RuntimeFailure):
    def __init__(self, reasons: Iterable[str]):
        super().__init__(ErrorCode.SECURITY_BLOCKED, "; ".join(reasons) or "EGRESS_DENIED")
        self.reasons = tuple(reasons)


class AttemptState(StrEnum):
    """Conservative billing state; UNKNOWN is never treated as zero."""

    NOT_DISPATCHED = "NOT_DISPATCHED"
    SETTLED_USAGE = "SETTLED_USAGE"
    BILLABLE_UNKNOWN = "BILLABLE_UNKNOWN"
    NOT_BILLABLE_HTTP_ERROR = "NOT_BILLABLE_HTTP_ERROR"


@dataclass(frozen=True)
class ClaimResult:
    """Normalized result from a trusted Broker dispatch-claim call."""
    claimed: bool
    code: str
    reasons: tuple[str, ...] = ()
    claim: Mapping[str, object] | None = None


class BrokerClaimer(Protocol):
    """Trusted stdio-Broker claim client; must talk to a real persistent ledger."""

    def claim(self, request: "EgressRequest") -> ClaimResult:
        ...


class BoundBrokerClaimer(Protocol):
    """Trusted claimer that sends the expected reservation route/model additively."""

    def claim_bound(self, request: "EgressRequest", *, expected_route_id: str,
                    expected_model: str) -> ClaimResult:
        ...


@dataclass(frozen=True)
class EgressRequest:
    logical_stream_id: str
    reservation_id: str
    attempt_ordinal: int
    route_id: str
    model: str
    host: str = OPENCODE_GO_HOST
    port: int = OPENCODE_GO_PORT
    method: str = "POST"
    path: str = OPENCODE_GO_PATH_PREFIX + "openai/v1/chat/completions"
    stream: bool = True
    max_tokens: int = 256
    has_files: bool = False
    has_images: bool = False
    store: bool = False
    estimated_cost_usd: str = "0.003933"
    call_id: str = ""
    request_digest: str = ""


@dataclass(frozen=True)
class EgressPolicy:
    host_ports: Mapping[str, frozenset[int]] = field(default_factory=lambda: {
        OPENCODE_GO_HOST: frozenset({OPENCODE_GO_PORT})})
    methods: frozenset[str] = frozenset({"POST"})
    path_prefix: str = OPENCODE_GO_PATH_PREFIX
    approved_routes: frozenset[tuple[str, str]] = frozenset({
        ("opencode-go", "deepseek-v4.1-flash")})
    max_tokens: int = MAX_OUTPUT_TOKENS
    max_attempts: int = MAX_ATTEMPTS_PER_STREAM
    require_reservation: bool = True
    allow_files: bool = False
    allow_images: bool = False
    allow_store: bool = False


PREPARED_SCHEMA_VERSION = "m0.prepared.v1"


@dataclass(frozen=True)
class PreparedProviderRequest:
    """Trusted prepared send descriptor; request_digest is recomputed by egress.

    This is an in-process descriptor, not a cryptographic token. The digest covers
    every field below except call_id/request_digest themselves; reservation_id is
    not part of call_id (ADR-002).
    """
    schema_version: str = PREPARED_SCHEMA_VERSION
    scope_id: str = ""
    run_id: str = ""
    logical_step: int = 0
    attempt_index: int = 0
    route_id: str = ""
    provider: str = ""
    model: str = ""
    host: str = OPENCODE_GO_HOST
    port: int = OPENCODE_GO_PORT
    method: str = "POST"
    path: str = ""
    stream: bool = True
    max_output_tokens: int = 256
    system: str = ""
    messages: tuple[Mapping[str, object], ...] = ()
    tools: tuple[Mapping[str, object], ...] = ()
    response_format: Mapping[str, object] | None = None
    retry_policy: Mapping[str, object] | None = None
    has_files: bool = False
    has_images: bool = False
    store: bool = False
    call_id: str = ""
    request_digest: str = ""


_PREPARED_DIGEST_FIELDS = (
    "schema_version", "scope_id", "run_id", "logical_step", "attempt_index",
    "route_id", "provider", "model", "host", "port", "method", "path", "stream",
    "max_output_tokens", "system", "messages", "tools", "response_format",
    "retry_policy", "has_files", "has_images", "store",
)


def prepared_payload(prepared: PreparedProviderRequest) -> dict[str, object]:
    return {name: getattr(prepared, name) for name in _PREPARED_DIGEST_FIELDS}


def prepared_schema_error(prepared: PreparedProviderRequest) -> str | None:
    """Strict Prepared schema/type validation; return a safe reason code or None."""
    if prepared.schema_version != PREPARED_SCHEMA_VERSION:
        return PREPARED_SCHEMA_VERSION_MISMATCH
    text_fields = (("scope_id", prepared.scope_id), ("run_id", prepared.run_id),
                   ("route_id", prepared.route_id), ("provider", prepared.provider),
                   ("model", prepared.model), ("host", prepared.host),
                   ("method", prepared.method), ("system", prepared.system))
    for name, value in text_fields:
        if not isinstance(value, str):
            return PREPARED_SCHEMA_INVALID
        if name not in ("system",) and (not value or value != value.strip()):
            return PREPARED_SCHEMA_INVALID
    try:
        validate_run_id(prepared.run_id)
    except IdentitySchemaError:
        return PREPARED_SCHEMA_INVALID
    path = prepared.path
    if not isinstance(path, str) or not path.startswith("/") or "\\" in path or ".." in path or "%2e" in path.casefold():
        return PREPARED_SCHEMA_INVALID
    if any(ord(char) < 32 or ord(char) == 127 for char in path):
        return PREPARED_SCHEMA_INVALID
    if type(prepared.logical_step) is not int or prepared.logical_step < 0:
        return PREPARED_SCHEMA_INVALID
    if type(prepared.attempt_index) is not int or prepared.attempt_index < 0:
        return PREPARED_SCHEMA_INVALID
    if type(prepared.port) is not int or not 1 <= prepared.port <= 65535:
        return PREPARED_SCHEMA_INVALID
    if type(prepared.max_output_tokens) is not int or prepared.max_output_tokens < 1:
        return PREPARED_SCHEMA_INVALID
    if type(prepared.stream) is not bool:
        return PREPARED_SCHEMA_INVALID
    for value in (prepared.has_files, prepared.has_images, prepared.store):
        if type(value) is not bool:
            return PREPARED_SCHEMA_INVALID
    if not isinstance(prepared.messages, (tuple, list)) or not all(
            isinstance(item, Mapping) for item in prepared.messages):
        return PREPARED_SCHEMA_INVALID
    if not isinstance(prepared.tools, (tuple, list)) or not all(
            isinstance(item, Mapping) for item in prepared.tools):
        return PREPARED_SCHEMA_INVALID
    for nested in (prepared.response_format, prepared.retry_policy):
        if nested is not None and not isinstance(nested, Mapping):
            return PREPARED_SCHEMA_INVALID
    if not isinstance(prepared.call_id, str) or not isinstance(prepared.request_digest, str):
        return PREPARED_SCHEMA_INVALID
    try:
        canonical_json(prepared_payload(prepared))
    except (TypeError, ValueError):
        return PREPARED_SCHEMA_INVALID
    return None


def prepared_request_digest(prepared: PreparedProviderRequest) -> str:
    return hashlib.sha256(canonical_json(prepared_payload(prepared)).encode("utf-8")).hexdigest()


def prepared_call_id(prepared: PreparedProviderRequest) -> str:
    digest = prepared_request_digest(prepared)
    material = {"v": 1, "run_id": prepared.run_id,
                "logical_step": prepared.logical_step,
                "attempt_index": prepared.attempt_index,
                "request_digest": digest}
    return "call-" + hashlib.sha256(canonical_json(material).encode("utf-8")).hexdigest()[:48]


@dataclass(frozen=True)
class PolicyEvaluation:
    """Policy-only descriptor evaluation; by construction it has no claim/permission."""
    allowed: bool
    reasons: tuple[str, ...]
    call_id: str
    legacy_egress_event_id: str
    logical_stream_id: str
    reservation_id: str
    attempt_ordinal: int
    route_model: tuple[str, str]


@dataclass(frozen=True)
class DispatchPermission:
    """Opaque capability created only by EgressBoundary.claim_dispatch() after a claim."""
    claim: ClaimResult
    call_id: str
    request_digest: str
    logical_stream_id: str
    reservation_id: str
    attempt_ordinal: int
    route_model: tuple[str, str]


@dataclass(frozen=True)
class EgressDecision:
    allowed: bool
    reasons: tuple[str, ...]
    call_id: str
    legacy_egress_event_id: str
    logical_stream_id: str
    reservation_id: str
    attempt_ordinal: int
    route_model: tuple[str, str]
    claim: ClaimResult | None = None
    permission: DispatchPermission | None = None


@dataclass
class LogicalStreamEgress:
    logical_stream_id: str
    reservation_id: str
    # legacy snapshot.attempts is kept as successful-claim count for compatibility;
    # authoritative counters are separate below.
    attempts: int = 0
    denied: int = 0
    policy_checks: int = 0
    policy_allowed: int = 0
    policy_denied: int = 0
    claims_granted: int = 0
    dispatch_attempted: int = 0
    provider_invocations: int = 0
    provider_dispatched: int = 0
    worst_case_held_usd: Decimal = Decimal("0")
    known_cost_usd: Decimal = Decimal("0")
    state: AttemptState = AttemptState.NOT_DISPATCHED
    attempts_detail: list[dict[str, object]] = field(default_factory=list)


def _legacy_egress_event_id(request: EgressRequest, route_model: tuple[str, str]) -> str:
    """Log-only PR4a event id; never a settlement/claim/broker identity."""
    material = "|".join((
        str(request.logical_stream_id), str(request.reservation_id), str(request.attempt_ordinal),
        route_model[0], route_model[1], str(request.host), str(request.port), str(request.path),
    ))
    return "eg-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def _strict_int(value: object, name: str, minimum: int, maximum: int | None = None) -> int:
    if type(value) is not int or value < minimum or (maximum is not None and value > maximum):
        raise ValueError(f"invalid policy {name}")
    return value


def _strict_bool(value: object, name: str) -> bool:
    if type(value) is not bool:
        raise ValueError(f"invalid policy {name}")
    return value


def _invalid_path(path: object, prefix: str) -> bool:
    """Reject traversal/backslash/encoded-dot/control paths; require absolute path."""
    if type(path) is not str or not path.startswith("/") or not path.startswith(prefix):
        return True
    if "\\" in path or ".." in path or "%2e" in path.casefold():
        return True
    return any(ord(char) < 32 or ord(char) == 127 for char in path)


class EgressBoundary:
    """Deterministic allowlist/deny diagnostics + trusted claim admission."""

    def __init__(self, policy: EgressPolicy | None = None,
                 claimer: BrokerClaimer | None = None) -> None:
        self.policy = policy or EgressPolicy()
        self.claimer = claimer
        self._streams: dict[str, LogicalStreamEgress] = {}
        self._decisions: list[dict] = []
        # Process-local capability registry: only object identity issued by this
        # boundary is accepted; constructing DispatchPermission externally fails.
        self._issued_permissions: dict[int, DispatchPermission] = {}

    def _stream(self, request: EgressRequest) -> LogicalStreamEgress:
        key = request.logical_stream_id
        if key not in self._streams:
            self._streams[key] = LogicalStreamEgress(key, request.reservation_id)
        return self._streams[key]

    def _evaluate(self, request: EgressRequest) -> PolicyEvaluation:
        """Pure policy/identity evaluation. Never grants a send permission."""
        policy = self.policy
        reasons: list[str] = []
        route_model = (request.route_id, request.model)
        if type(request.logical_stream_id) is not str or not request.logical_stream_id.strip():
            reasons.append("LOGICAL_STREAM_INVALID")
        if type(request.reservation_id) is not str:
            reasons.append("NO_RESERVATION")
        elif policy.require_reservation and not request.reservation_id.strip():
            reasons.append("NO_RESERVATION")
        if not isinstance(request.call_id, str) or not CALL_ID_RE.fullmatch(request.call_id):
            reasons.append("CALL_ID_INVALID_OR_MISSING")
        if (not isinstance(request.request_digest, str)
                or not REQUEST_DIGEST_RE.fullmatch(request.request_digest)):
            reasons.append("REQUEST_DIGEST_INVALID")
        if type(request.route_id) is not str or type(request.model) is not str:
            reasons.append("ROUTE_MODEL_NOT_APPROVED")
        elif route_model not in policy.approved_routes:
            reasons.append("ROUTE_MODEL_NOT_APPROVED")
        if type(request.host) is not str or not request.host.strip():
            reasons.append("HOST_PORT_NOT_ALLOWED")
        else:
            ports = policy.host_ports.get(request.host)
            if ports is None or type(request.port) is not int or request.port not in ports:
                reasons.append("HOST_PORT_NOT_ALLOWED")
        if type(request.method) is not str or request.method.upper() not in policy.methods:
            reasons.append("METHOD_NOT_ALLOWED")
        if _invalid_path(request.path, policy.path_prefix):
            reasons.append("PATH_NOT_ALLOWED")
        if type(request.max_tokens) is not int or request.max_tokens < 1:
            reasons.append("MAX_TOKENS_INVALID")
        elif request.max_tokens > policy.max_tokens:
            reasons.append("MAX_TOKENS_EXCEEDED")
        for name, value in (("has_files", request.has_files),
                            ("has_images", request.has_images),
                            ("store", request.store)):
            if type(value) is not bool:
                reasons.append(f"{name.upper()}_FLAG_INVALID")
        if request.has_files is True and not policy.allow_files:
            reasons.append("FILES_NOT_PERMITTED")
        if request.has_images is True and not policy.allow_images:
            reasons.append("IMAGES_NOT_PERMITTED")
        if request.store is True and not policy.allow_store:
            reasons.append("STORE_NOT_PERMITTED")
        if type(request.stream) is not bool:
            reasons.append("STREAM_FLAG_INVALID")
        stream = self._stream(request)
        if type(request.attempt_ordinal) is not int or request.attempt_ordinal < 1:
            reasons.append("ATTEMPT_ORDINAL_INVALID")
        elif stream.claims_granted + 1 > policy.max_attempts:
            reasons.append("ATTEMPT_LIMIT_EXCEEDED")
        return PolicyEvaluation(not reasons, tuple(reasons), str(request.call_id),
                                _legacy_egress_event_id(request, route_model),
                                str(request.logical_stream_id), str(request.reservation_id),
                                int(request.attempt_ordinal), route_model)

    def _record_policy(self, request: EgressRequest, evaluation: PolicyEvaluation) -> None:
        stream = self._stream(request)
        stream.policy_checks += 1
        stream.policy_allowed += int(evaluation.allowed)
        stream.policy_denied += int(not evaluation.allowed)
        if not evaluation.allowed:
            stream.denied += 1
        detail = {
            "logical_stream_id": evaluation.logical_stream_id,
            "reservation_id": evaluation.reservation_id,
            "call_id": evaluation.call_id,
            "attempt_ordinal": evaluation.attempt_ordinal,
            "route_model": list(evaluation.route_model),
            "policy_allowed": evaluation.allowed,
            "policy_reasons": list(evaluation.reasons),
            "claim_granted": False,
            "attempt_started": False,
            "provider_invoked": False,
            "provider_dispatched": False,
        }
        stream.attempts_detail.append(detail)
        self._decisions.append({
            "call_id": evaluation.call_id,
            "legacy_egress_event_id": evaluation.legacy_egress_event_id,
            "allowed": evaluation.allowed, "claim": None,
            "policy_allowed": evaluation.allowed,
            "claim_granted": False,
            "provider_dispatched": False,
            "reasons": list(evaluation.reasons), "stream": evaluation.logical_stream_id,
            "reservation": evaluation.reservation_id,
            "attempt": evaluation.attempt_ordinal,
            "route": request.route_id, "model": request.model,
        })

    def evaluate_descriptor(self, request: EgressRequest) -> PolicyEvaluation:
        """Descriptor-only diagnostic; never a formal send permission/capability."""
        evaluation = self._evaluate(request)
        self._record_policy(request, evaluation)
        return evaluation

    def authorize(self, request: EgressRequest) -> PolicyEvaluation:
        """Diagnostic alias for evaluate_descriptor; never a send permission."""
        return self.evaluate_descriptor(request)

    def require(self, request: EgressRequest) -> PolicyEvaluation:
        """Diagnostic require: raises only on descriptor deny; never dispatches."""
        evaluation = self.evaluate_descriptor(request)
        if not evaluation.allowed:
            raise EgressViolation(evaluation.reasons)
        return evaluation

    def _denied_decision(self, evaluation: PolicyEvaluation,
                         extra_reasons: Iterable[str] = (),
                         claim: ClaimResult | None = None) -> EgressDecision:
        reasons = evaluation.reasons + tuple(extra_reasons)
        return EgressDecision(False, reasons, evaluation.call_id,
                              evaluation.legacy_egress_event_id,
                              evaluation.logical_stream_id, evaluation.reservation_id,
                              evaluation.attempt_ordinal, evaluation.route_model, claim=claim)

    def _mark_claim(self, request: EgressRequest) -> None:
        stream = self._stream(request)
        stream.claims_granted += 1
        # legacy read-only compatibility: successful claim count, not policy checks.
        stream.attempts = stream.claims_granted
        for detail in reversed(stream.attempts_detail):
            if (detail["call_id"] == request.call_id
                    and detail["reservation_id"] == request.reservation_id
                    and detail["attempt_ordinal"] == request.attempt_ordinal):
                detail["claim_granted"] = True
                break

    def mark_dispatch_attempt_started(self, request: EgressRequest) -> None:
        """Record that a provider callable is about to be entered (may be billable)."""
        stream = self._stream(request)
        stream.dispatch_attempted += 1
        for detail in reversed(stream.attempts_detail):
            if (detail["call_id"] == request.call_id
                    and detail["reservation_id"] == request.reservation_id
                    and detail["attempt_ordinal"] == request.attempt_ordinal):
                detail["attempt_started"] = True
                break

    def _claim_with(self, request: EgressRequest,
                    expected_binding: tuple[str, str] | None = None) -> EgressDecision:
        evaluation = self.evaluate_descriptor(request)
        if not evaluation.allowed:
            return self._denied_decision(evaluation)
        if self.claimer is None:
            return self._denied_decision(evaluation, (BROKER_CLAIMER_UNAVAILABLE,))
        try:
            if expected_binding is None:
                claim = self.claimer.claim(request)
            else:
                bound = getattr(self.claimer, "claim_bound", None)
                if not callable(bound):
                    return self._denied_decision(
                        evaluation, (BROKER_CLAIMER_BOUND_UNSUPPORTED,))
                claim = bound(request, expected_route_id=expected_binding[0],
                              expected_model=expected_binding[1])
        except (KeyboardInterrupt, SystemExit, asyncio.CancelledError):
            # Fail closed and preserve cancellation/interrupt semantics; do not
            # convert these into a normal BROKER_CLAIMER_ERROR response.
            self._denied_decision(evaluation, ("CLAIM_INTERRUPTED",))
            raise
        except BaseException as error:  # includes timeout/EOF/transport failures
            return self._denied_decision(
                evaluation, (BROKER_CLAIMER_ERROR, f"CLAIM_ERROR:{type(error).__name__}"))
        if not isinstance(claim, ClaimResult):
            return self._denied_decision(evaluation, (BROKER_CLAIMER_BAD_REPLY,))
        if not claim.claimed:
            reasons = (f"CLAIM_REJECTED:{claim.code}",) + tuple(claim.reasons)
            return self._denied_decision(evaluation, reasons, claim=claim)
        permission = DispatchPermission(
            claim=claim, call_id=request.call_id, request_digest=request.request_digest,
            logical_stream_id=request.logical_stream_id,
            reservation_id=request.reservation_id,
            attempt_ordinal=request.attempt_ordinal,
            route_model=(request.route_id, request.model))
        self._issued_permissions[id(permission)] = permission
        self._mark_claim(request)
        return EgressDecision(True, evaluation.reasons, evaluation.call_id,
                              evaluation.legacy_egress_event_id,
                              evaluation.logical_stream_id, evaluation.reservation_id,
                              evaluation.attempt_ordinal, evaluation.route_model,
                              claim=claim, permission=permission)

    def claim_dispatch(self, request: EgressRequest) -> EgressDecision:
        """Legacy v1 claim path: trusted claimer without explicit expected fields.

        New trusted callers should use claim_dispatch_for_request(); this path
        retains old-client/broker behavior and does not itself prove reservation
        route/model binding (documented residual).
        """
        return self._claim_with(request)

    def _prepared_denied(self, request: EgressRequest, reasons: Iterable[str]) -> EgressDecision:
        return EgressDecision(False, tuple(reasons), request.call_id,
                              _legacy_egress_event_id(request, (request.route_id, request.model)),
                              request.logical_stream_id, request.reservation_id,
                              request.attempt_ordinal, (request.route_id, request.model))

    def claim_dispatch_for_request(
            self, prepared: PreparedProviderRequest, request: EgressRequest, *,
            expected_reservation_route_model: tuple[str, str] | None = None,
            approved_tool_schemas: frozenset[str] = frozenset()) -> EgressDecision:
        """Trusted claim admission for a prepared request; all checks precede claimer.

        Recomputes digest/call_id from PreparedProviderRequest (never trusts the
        candidate-provided digest), compares every bound field with EgressRequest,
        optionally checks the trusted reservation route/model and approved tool
        schemas, and only then calls a BoundBrokerClaimer. Any mismatch returns
        deny with zero claimer/provider calls.
        """
        if not isinstance(prepared, PreparedProviderRequest):
            return self._prepared_denied(request, (PREPARED_REQUEST_INVALID,))
        schema_error = prepared_schema_error(prepared)
        if schema_error is not None:
            return self._prepared_denied(request, (schema_error,))
        try:
            computed_digest = prepared_request_digest(prepared)
            computed_call_id = prepared_call_id(prepared)
        except (TypeError, ValueError) as error:
            return self._prepared_denied(
                request, (PREPARED_REQUEST_INVALID, f"PREPARED_INVALID:{type(error).__name__}"))
        reasons: list[str] = []
        if prepared.request_digest != computed_digest:
            reasons.append(PREPARED_DIGEST_MISMATCH)
        if request.request_digest != computed_digest:
            reasons.append("REQUEST_DIGEST_MISMATCH")
        if prepared.call_id != computed_call_id:
            reasons.append("PREPARED_CALL_ID_MISMATCH")
        if request.call_id != computed_call_id:
            reasons.append("REQUEST_CALL_ID_MISMATCH")
        comparisons = (
            ("ROUTE_MISMATCH", prepared.route_id, request.route_id),
            ("MODEL_MISMATCH", prepared.model, request.model),
            ("HOST_MISMATCH", prepared.host, request.host),
            ("PORT_MISMATCH", prepared.port, request.port),
            ("METHOD_MISMATCH", prepared.method.upper() if isinstance(prepared.method, str) else prepared.method,
             request.method.upper() if isinstance(request.method, str) else request.method),
            ("PATH_MISMATCH", prepared.path, request.path),
            ("STREAM_MISMATCH", prepared.stream, request.stream),
            ("MAX_TOKENS_MISMATCH", prepared.max_output_tokens, request.max_tokens),
            ("HAS_FILES_MISMATCH", prepared.has_files, request.has_files),
            ("HAS_IMAGES_MISMATCH", prepared.has_images, request.has_images),
            ("STORE_MISMATCH", prepared.store, request.store),
        )
        for reason, prepared_value, request_value in comparisons:
            if prepared_value != request_value:
                reasons.append(reason)
        if expected_reservation_route_model is not None:
            if (prepared.route_id, prepared.model) != tuple(expected_reservation_route_model):
                reasons.append(RESERVATION_REQUEST_MISMATCH)
        if prepared.tools:
            try:
                tool_keys = frozenset(canonical_json(tool) for tool in prepared.tools)
            except (TypeError, ValueError):
                reasons.append(PREPARED_REQUEST_INVALID)
            else:
                if not tool_keys.issubset(set(approved_tool_schemas)):
                    reasons.append(TOOL_SCHEMA_NOT_APPROVED)
        if reasons:
            return self._prepared_denied(request, reasons)
        return self._claim_with(request, expected_binding=(prepared.route_id, prepared.model))

    def require_claim(self, request: EgressRequest) -> EgressDecision:
        """Formal admission entrypoint: raises EgressViolation unless a claim succeeds."""
        decision = self.claim_dispatch(request)
        if not decision.allowed:
            raise EgressViolation(decision.reasons)
        return decision

    def record_outcome(self, decision: EgressDecision, *,
                       usage: Mapping[str, int] | None, http_status: int | None,
                       error_kind: str | None, worst_case_usd: str) -> AttemptState:
        stream = self._streams[decision.logical_stream_id]
        if not decision.allowed:
            return stream.state
        for detail in reversed(stream.attempts_detail):
            if (detail["call_id"] == decision.call_id
                    and detail["reservation_id"] == decision.reservation_id
                    and detail["attempt_ordinal"] == decision.attempt_ordinal):
                detail["provider_dispatched"] = True
                detail["provider_invoked"] = True
                break
        stream.provider_invocations += 1
        stream.provider_dispatched += 1
        if error_kind in {"timeout", "hang", "disconnect", "unknown_transport"}:
            state = AttemptState.BILLABLE_UNKNOWN
            stream.worst_case_held_usd += Decimal(worst_case_usd)
        elif http_status is not None and http_status >= 500:
            state = AttemptState.BILLABLE_UNKNOWN
            stream.worst_case_held_usd += Decimal(worst_case_usd)
        elif http_status is not None and 400 <= http_status < 500:
            state = AttemptState.NOT_BILLABLE_HTTP_ERROR
        elif usage is None or "outputTokens" not in usage or "inputTokens" not in usage:
            state = AttemptState.BILLABLE_UNKNOWN
            stream.worst_case_held_usd += Decimal(worst_case_usd)
        else:
            state = AttemptState.SETTLED_USAGE
            stream.known_cost_usd += Decimal(worst_case_usd)
        stream.state = state
        return state

    def stream(self, logical_stream_id: str) -> LogicalStreamEgress:
        if logical_stream_id not in self._streams:
            raise KeyError(logical_stream_id)
        return self._streams[logical_stream_id]

    def snapshot(self) -> dict:
        return {"streams": [
            {"logical_stream_id": s.logical_stream_id, "reservation_id": s.reservation_id,
             "attempts": s.attempts, "denied": s.denied,
             "policy_checks": s.policy_checks,
             "policy_allowed": s.policy_allowed, "policy_denied": s.policy_denied,
             "claims_granted": s.claims_granted,
             "dispatch_attempted": s.dispatch_attempted,
             "provider_invocations": s.provider_invocations,
             "provider_dispatched": s.provider_dispatched,
             "attempts_semantics": "legacy attempts=successful claims; attempts_detail authoritative",
             "state": s.state.value,
             "worst_case_held_usd": format(s.worst_case_held_usd, "f"),
             "known_cost_usd": format(s.known_cost_usd, "f"),
             "attempts_detail": [dict(detail) for detail in s.attempts_detail]}
            for s in sorted(self._streams.values(), key=lambda item: item.logical_stream_id)],
            "decisions": list(self._decisions)}



    def _permission_matches(self, request: EgressRequest,
                            permission: DispatchPermission) -> bool:
        claim = permission.claim
        if not isinstance(claim, ClaimResult) or claim.claimed is not True:
            return False
        return (
            permission.call_id == request.call_id
            and permission.request_digest == request.request_digest
            and permission.logical_stream_id == request.logical_stream_id
            and permission.reservation_id == request.reservation_id
            and permission.attempt_ordinal == request.attempt_ordinal
            and permission.route_model == (request.route_id, request.model)
        )

    def consume_permission(self, permission: object,
                           request: EgressRequest) -> bool:
        """Consume a process-local permission exactly once by object identity+fields.

        A newly constructed/copied/tampered DispatchPermission, a permission from
        another boundary, or a replayed permission fails. This is a process-local
        capability check, not cross-process cryptographic authorization.
        """
        if not isinstance(permission, DispatchPermission):
            return False
        if not self._permission_matches(request, permission):
            return False
        registered = self._issued_permissions.get(id(permission))
        if registered is not permission:
            return False
        del self._issued_permissions[id(permission)]
        return True


class TrustedEgressTransport:
    """Trusted dispatch wrapper: requires a DispatchPermission created by a claim.

    It never calls the provider unless the permission is a real DispatchPermission
    with claim.claimed is True and all identity fields match the request. Provider
    errors are fail-closed and counted as zero provider calls.
    """

    def __init__(self, boundary: EgressBoundary,
                 provider: Callable[[EgressRequest], Mapping[str, object]] | None = None) -> None:
        self.boundary = boundary
        self.provider = provider
        self.provider_calls = 0          # provider callable entry count (not HTTP attempts)
        self.dispatch_count = 0          # provider callable entry/attempt-start count (including after-entry failures); not confirmed HTTP/completed returns
        self.attempt_started_count = 0
        self.denied_count = 0
        self.worst_case_usd = "0.003933"

    def _denied(self, request: EgressRequest, reason: str) -> dict:
        self.denied_count += 1
        return {"call_id": request.call_id, "dispatched": False,
                "classification": "PRE_DISPATCH_DENIED", "attempt_started": False,
                "denied_reasons": [reason],
                "state": AttemptState.NOT_DISPATCHED.value,
                "provider_calls": self.provider_calls, "http_attempts": "UNVERIFIED"}

    def _started_failure(self, request: EgressRequest, permission: object,
                         reason: str, error_kind: str,
                         worst_case_usd: str | None) -> dict:
        self.dispatch_count += 1
        decision = EgressDecision(True, (), request.call_id, "",
                                  request.logical_stream_id, request.reservation_id,
                                  request.attempt_ordinal,
                                  (request.route_id, request.model),
                                  claim=permission.claim, permission=permission)
        state = self.boundary.record_outcome(
            decision, usage=None, http_status=None, error_kind=error_kind,
            worst_case_usd=worst_case_usd or self.worst_case_usd)
        return {"call_id": request.call_id, "dispatched": True,
                "classification": "ATTEMPT_STARTED",
                "attempt_started": True, "provider_invoked": True,
                "state": state.value, "denied_reasons": [reason],
                "provider_calls": self.provider_calls,
                "provider_invocations": self.boundary.stream(
                    request.logical_stream_id).provider_invocations,
                "http_attempts": "UNVERIFIED", "retry_attempted": False}

    def dispatch(self, request: EgressRequest, permission: object, *,
                 provider: Callable[[EgressRequest], Mapping[str, object]] | None = None,
                 worst_case_usd: str | None = None) -> dict:
        if not self.boundary.consume_permission(permission, request):
            return self._denied(request, "DISPATCH_PERMISSION_REQUIRED")
        selected = provider or self.provider
        if selected is None:
            return self._denied(request, "PROVIDER_UNAVAILABLE")
        # Attempt-start is recorded BEFORE entering the provider; may be billable.
        self.boundary.mark_dispatch_attempt_started(request)
        self.attempt_started_count += 1
        self.provider_calls += 1
        try:
            result = selected(request)
        except (KeyboardInterrupt, SystemExit, asyncio.CancelledError):
            self._started_failure(request, permission, "PROVIDER_INTERRUPTED",
                                  "provider_interrupted", worst_case_usd)
            raise
        except BaseException as error:
            return self._started_failure(request, permission,
                                         f"PROVIDER_ERROR:{type(error).__name__}",
                                         "provider_exception", worst_case_usd)
        if not isinstance(result, Mapping):
            return self._started_failure(request, permission,
                                         "PROVIDER_RESULT_INVALID",
                                         "provider_result_invalid", worst_case_usd)
        self.dispatch_count += 1
        state = self.boundary.record_outcome(
            EgressDecision(True, (), request.call_id, "", request.logical_stream_id,
                           request.reservation_id, request.attempt_ordinal,
                           (request.route_id, request.model), claim=permission.claim,
                           permission=permission),
            usage=result.get("usage") if isinstance(result.get("usage"), Mapping) else None,
            http_status=result.get("http_status", result.get("status")) if isinstance(result.get("http_status", result.get("status")), int) else None,
            error_kind=result.get("error_kind", result.get("error")) if isinstance(result.get("error_kind", result.get("error")), str) else None,
            worst_case_usd=worst_case_usd or str(result.get("worst_case_usd", self.worst_case_usd)))
        self.boundary._decisions.append({  # audit trace for actual provider dispatch
            "call_id": request.call_id, "legacy_egress_event_id": "",
            "allowed": True, "policy_allowed": True, "claim_granted": True,
            "provider_dispatched": True, "claim": dict(permission.claim.claim or {}),
            "reasons": [], "stream": request.logical_stream_id,
            "reservation": request.reservation_id, "attempt": request.attempt_ordinal,
            "route": request.route_id, "model": request.model,
        })
        usage = result.get("usage")
        classification = ("RESPONSE_COMPLETED" if state is AttemptState.SETTLED_USAGE
                          else "RESPONSE_PARTIAL" if isinstance(usage, Mapping)
                          else "RESPONSE_UNKNOWN")
        return {"call_id": request.call_id, "dispatched": True,
                "classification": classification,
                "attempt_started": True, "provider_invoked": True,
                "claim": dict(permission.claim.claim or {}),
                "http_status": result.get("http_status", result.get("status")),
                "state": state.value,
                "usage_known": isinstance(usage, Mapping),
                "worst_case_conservative": state is AttemptState.BILLABLE_UNKNOWN,
                "retry_attempted": False, "provider_calls": self.provider_calls,
                "provider_invocations": self.boundary.stream(
                    request.logical_stream_id).provider_invocations,
                "http_attempts": "UNVERIFIED", "scenario": result.get("scenario")}


class MockEgressTransport(TrustedEgressTransport):
    """Scripted synthetic transport; requires a real claim permission. No sockets."""

    SCENARIOS: Mapping[str, dict] = {
        "ok_usage": {"status": 200, "usage": {"inputTokens": 7, "outputTokens": 3},
                     "error": None},
        "ok_no_usage": {"status": 200, "usage": None, "error": None},
        "ok_partial_usage": {"status": 200, "usage": {"inputTokens": 7}, "error": None},
        "http_401": {"status": 401, "usage": None, "error": "auth"},
        "http_429": {"status": 429, "usage": None, "error": "rate_limit"},
        "http_500": {"status": 500, "usage": None, "error": "server"},
        "http_503": {"status": 503, "usage": None, "error": "server"},
        "timeout": {"status": None, "usage": None, "error": "timeout"},
        "hang": {"status": None, "usage": None, "error": "hang"},
        "disconnect": {"status": None, "usage": None, "error": "disconnect"},
        "unknown_transport": {"status": None, "usage": None, "error": "unknown_transport"},
    }

    def __init__(self, boundary: EgressBoundary) -> None:
        super().__init__(boundary, provider=None)
        self._retry_counts: dict[str, int] = {}

    def dispatch(self, request: EgressRequest, permission: object,
                 scenario: str = "ok_usage", worst_case_usd: str = "0.003933") -> dict:
        if scenario not in self.SCENARIOS:
            raise ValueError("unknown mock scenario")
        result = self.SCENARIOS[scenario]

        def provider(_request: EgressRequest) -> Mapping[str, object]:
            return result

        outcome = super().dispatch(request, permission, provider=provider,
                                   worst_case_usd=worst_case_usd)
        outcome["scenario"] = scenario
        if outcome["dispatched"]:
            self._retry_counts[request.logical_stream_id] = self._retry_counts.get(
                request.logical_stream_id, 0) + int(result["error"] is not None)
        return outcome


class PolicyOnlyFakeTransport:
    """Explicitly non-sending diagnostic transport for tests/scripts only.

    It never calls a provider and never returns dispatched=True. It exists so that
    descriptor-only legacy checks cannot be mistaken for a send admission path.
    """

    def __init__(self, boundary: EgressBoundary) -> None:
        self.boundary = boundary

    def dispatch(self, request: EgressRequest, scenario: str = "ok_usage") -> dict:
        evaluation = self.boundary.evaluate_descriptor(request)
        return {"call_id": evaluation.call_id, "dispatched": False,
                "policy_allowed": evaluation.allowed,
                "denied_reasons": list(evaluation.reasons),
                "scenario": scenario,
                "state": AttemptState.NOT_DISPATCHED.value}


def policy_from_json(raw: Mapping[str, object]) -> EgressPolicy:
    """Strict policy loader: reject unknown fields and bool/int coercion."""
    if not isinstance(raw, Mapping):
        raise TypeError("egress policy must be a mapping")
    allowed = {"host_ports", "methods", "path_prefix", "approved_routes", "max_tokens",
               "max_attempts", "require_reservation", "allow_files", "allow_images",
               "allow_store"}
    unknown = set(raw) - allowed
    if unknown:
        raise ValueError("unknown egress policy field")
    if "host_ports" in raw:
        ports_raw = raw["host_ports"]
        if not isinstance(ports_raw, Mapping) or not ports_raw:
            raise ValueError("invalid policy host_ports")
        host_ports: dict[str, frozenset[int]] = {}
        for host, ports in ports_raw.items():
            if not isinstance(host, str) or not host or host != host.strip():
                raise ValueError("invalid policy host")
            if isinstance(ports, (str, bytes)) or not isinstance(ports, Sequence) or not ports:
                raise ValueError("invalid policy ports")
            normalized = set()
            for port in ports:
                if type(port) is not int or not 1 <= port <= 65535:
                    raise ValueError("invalid policy port")
                normalized.add(port)
            if len(normalized) != len(ports):
                raise ValueError("duplicate policy port")
            host_ports[host] = frozenset(normalized)
    else:
        host_ports = {OPENCODE_GO_HOST: frozenset({OPENCODE_GO_PORT})}
    if "methods" in raw:
        methods_raw = raw["methods"]
        if isinstance(methods_raw, (str, bytes)) or not isinstance(methods_raw, Sequence) or not methods_raw:
            raise ValueError("invalid policy methods")
        methods_values = []
        for method in methods_raw:
            if not isinstance(method, str) or not method or method != method.strip():
                raise ValueError("invalid policy method")
            methods_values.append(method.upper())
        if len(set(methods_values)) != len(methods_values):
            raise ValueError("duplicate policy method")
        methods = frozenset(methods_values)
    else:
        methods = frozenset({"POST"})
    if "approved_routes" in raw:
        routes_raw = raw["approved_routes"]
        if isinstance(routes_raw, (str, bytes)) or not isinstance(routes_raw, Sequence) or not routes_raw:
            raise ValueError("invalid policy approved_routes")
        routes = set()
        for route in routes_raw:
            if (isinstance(route, (str, bytes)) or not isinstance(route, Sequence)
                    or len(route) != 2
                    or not all(isinstance(part, str) and part.strip() for part in route)):
                raise ValueError("invalid policy route")
            pair = (route[0], route[1])
            if pair in routes:
                raise ValueError("duplicate policy route")
            routes.add(pair)
        approved_routes = frozenset(routes)
    else:
        approved_routes = frozenset({("opencode-go", "deepseek-v4.1-flash")})
    if "path_prefix" in raw:
        path_prefix = raw["path_prefix"]
        if not isinstance(path_prefix, str) or not path_prefix.startswith("/") or ".." in path_prefix:
            raise ValueError("invalid policy path_prefix")
    else:
        path_prefix = OPENCODE_GO_PATH_PREFIX
    max_tokens = _strict_int(raw.get("max_tokens", MAX_OUTPUT_TOKENS), "max_tokens",
                             1, MAX_OUTPUT_TOKENS)
    max_attempts = _strict_int(raw.get("max_attempts", MAX_ATTEMPTS_PER_STREAM),
                               "max_attempts", 1, MAX_ATTEMPTS_PER_STREAM)
    flags = {}
    for name, default in (("require_reservation", True), ("allow_files", False),
                          ("allow_images", False), ("allow_store", False)):
        flags[name] = _strict_bool(raw.get(name, default), name)
    return EgressPolicy(host_ports=host_ports, methods=methods, path_prefix=path_prefix,
                        approved_routes=approved_routes, max_tokens=max_tokens,
                        max_attempts=max_attempts, **flags)
