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
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from enum import StrEnum
import hashlib
import json
import os
import re
import stat
import threading
from typing import Callable, Iterable, Mapping, Protocol, Sequence

from autoteacher_m0.accounting.call_identity import (
    IdentitySchemaError, canonical_json, validate_run_id,
)
from autoteacher_m0.contracts import ErrorCode, RuntimeFailure
from .authorization import ExpectedBindings, binding_drift

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
REQUEST_DIGEST_MISMATCH = "REQUEST_DIGEST_MISMATCH"
PREPARED_CALL_ID_MISMATCH = "PREPARED_CALL_ID_MISMATCH"
REQUEST_CALL_ID_MISMATCH = "REQUEST_CALL_ID_MISMATCH"
RESERVATION_REQUEST_MISMATCH = "RESERVATION_REQUEST_MISMATCH"
TOOL_SCHEMA_NOT_APPROVED = "TOOL_SCHEMA_NOT_APPROVED"
PREPARED_SCHEMA_INVALID = "PREPARED_SCHEMA_INVALID"
PREPARED_SCHEMA_VERSION_MISMATCH = "PREPARED_SCHEMA_VERSION_MISMATCH"
COST_BOUND_INVALID = "COST_BOUND_INVALID"
RESERVATION_ALREADY_SETTLED = "RESERVATION_ALREADY_SETTLED"


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
    # One attempt's outcome may be observed once; a replayed observation must
    # never double-count the conservative hold/known evidence counters.
    recorded_outcome_keys: set[str] = field(default_factory=set)


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
        # Transport evidence is recorded at most once per attempt. A replayed
        # observation (retry of the same attempt identity) must not add a second
        # conservative hold, and unknown remains unknown until the Broker says
        # otherwise.
        outcome_key = "|".join((str(decision.call_id), str(decision.reservation_id),
                                str(decision.attempt_ordinal)))
        if outcome_key in stream.recorded_outcome_keys:
            return stream.state
        stream.recorded_outcome_keys.add(outcome_key)
        for detail in reversed(stream.attempts_detail):
            if (detail["call_id"] == decision.call_id
                    and detail["reservation_id"] == decision.reservation_id
                    and detail["attempt_ordinal"] == decision.attempt_ordinal):
                detail["provider_dispatched"] = True
                detail["provider_invoked"] = True
                detail["cost_recorded"] = True
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
        elif error_kind is not None:
            # Any non-None error marker that is not a recognised non-billable
            # 4xx is a conservative unknown: never a false successful settlement
            # (e.g. conflicting/duplicate usage signals).
            state = AttemptState.BILLABLE_UNKNOWN
            stream.worst_case_held_usd += Decimal(worst_case_usd)
        elif usage is None or "outputTokens" not in usage or "inputTokens" not in usage:
            state = AttemptState.BILLABLE_UNKNOWN
            stream.worst_case_held_usd += Decimal(worst_case_usd)
        else:
            state = AttemptState.SETTLED_USAGE
            stream.known_cost_usd += Decimal(worst_case_usd)
        stream.state = state
        for detail in reversed(stream.attempts_detail):
            if (detail["call_id"] == decision.call_id
                    and detail["reservation_id"] == decision.reservation_id
                    and detail["attempt_ordinal"] == decision.attempt_ordinal):
                detail["cost_state"] = state.value
                break
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


# ---------------------------------------------------------------------------
# G4-C trusted synthetic egress contract
#
# The two dataclasses below are the frozen G4-C surface documented in
# ``docs/M0_G4_C_EGRESS_CONTRACT.md``:
#
# * ``ProviderRouteContract`` describes exactly what one provider route may
#   send (host/port/method/exact path, wire format, streaming, tokenizer/price
#   source, tool schema digests, retry policy, files/images/store switches).
#   Synthetic fixtures and future real routes are declared separately; the real
#   template stays BLOCKED.
# * ``TrustedSendAuthorization`` is a trusted-domain, in-memory, single-use
#   capability binding scope/run/call/prepared digest/reservation/claim/payload
#   digest+length/attempt/route/model/epoch/expiry. It has no JSON parser: a
#   candidate-supplied mapping can never become an authorization.
#
# ``TrustedSendGate`` mints/consumes those capabilities, re-hashes the exact
# bytes immediately before the Fake Provider is entered, and calls the G4-A
# ``binding_drift("pre_dispatch", ...)`` checkpoint. The gate is opt-in: with
# no gate the G3-C/G3-D behaviour is unchanged.
# ---------------------------------------------------------------------------
G4C_CONTRACT_SCHEMA = "m0.g4c.egress-contract.v1"
G4C_SEND_AUTHORIZATION_SCHEMA = "m0.g4c.send-authorization.v1"
ROUTE_KIND_SYNTHETIC = "synthetic_fixture"
ROUTE_KIND_REAL = "real_provider"
ACTIVATION_SYNTHETIC_ONLY = "ACTIVE_SYNTHETIC_ONLY"
ACTIVATION_BLOCKED = "BLOCKED_REQUIRES_HUMAN_VERIFICATION"
RETRY_POLICY_NO_RETRY = "no_retry"
SYNTHETIC_PRICE_SOURCE = "fixture_synthetic_rate:v1"
REAL_PRICE_SOURCE = "REQUIRES_VERIFICATION"
SYNTHETIC_ROUTE_ID = "offline-test-only-g3b"
SYNTHETIC_PROVIDER = "offline-test-only-g3b"
SYNTHETIC_MODEL_ID = "fixture-bridge-v1"
SYNTHETIC_HOST = "g3b-fake.local"
SYNTHETIC_PORT = 9000
SYNTHETIC_EXACT_PATH = "/v1/g3b/chat"
SYNTHETIC_FORMAT_VERSION = "m0.g3b.fake.v1"
SYNTHETIC_STREAMING_CONTRACT = "synthetic_frames_v1"
# canonical_json(skill_lookup schema) from the frozen G3-C/G3-D capture fixture.
SKILL_LOOKUP_SCHEMA_DIGEST = (
    "c984bef0ae31771da16a12ef2e7972b289cde6014b7f8ad12349f16c4f77b704")
SEND_AUTHORIZATION_TTL_SECONDS = 30
SEND_AUTHORIZATION_LIMIT = 256
_SEND_ID_RE = re.compile(r"send-[0-9a-f]{32}\Z", re.ASCII)
_METHODS = frozenset({"POST"})
_UTC_TEXT = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z\Z")


def _contract_text(value: object, name: str, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"invalid route contract field {name}")
    if any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError(f"invalid route contract field {name}")
    return value


def _contract_digest_set(value: object) -> frozenset[str]:
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple, set,
                                                               frozenset)):
        raise ValueError("invalid route contract tool schema digests")
    digests = set()
    for item in value:
        if not isinstance(item, str) or not REQUEST_DIGEST_RE.fullmatch(item):
            raise ValueError("invalid route contract tool schema digest")
        digests.add(item)
    if len(digests) != len(value):
        raise ValueError("duplicate route contract tool schema digest")
    return frozenset(digests)


@dataclass(frozen=True)
class ProviderRouteContract:
    """Frozen description of one provider route; never an endpoint guess."""

    route_id: str
    provider: str
    model_id: str
    endpoint_host: str | None
    port: int | None
    method: str | None
    exact_path: str | None
    request_format_version: str | None
    streaming_contract: str | None
    tokenizer_price_source_version: str | None
    max_output_tokens: int
    allowed_tool_schema_digests: frozenset[str]
    retry_policy: str
    allow_files: bool
    allow_images: bool
    allow_store: bool
    route_kind: str
    price_source: str
    activation: str

    def contract_problems(self) -> tuple[str, ...]:
        """Stable reasons this declaration is not a valid frozen contract."""
        problems: list[str] = []
        for name in ("route_id", "provider", "model_id"):
            try:
                _contract_text(getattr(self, name), name)
            except ValueError:
                problems.append(f"ROUTE_CONTRACT_FIELD_INVALID:{name}")
        if self.route_kind not in {ROUTE_KIND_SYNTHETIC, ROUTE_KIND_REAL}:
            problems.append("ROUTE_CONTRACT_KIND_INVALID")
        if self.activation not in {ACTIVATION_SYNTHETIC_ONLY, ACTIVATION_BLOCKED}:
            problems.append("ROUTE_CONTRACT_ACTIVATION_INVALID")
        if self.retry_policy != RETRY_POLICY_NO_RETRY:
            problems.append("ROUTE_CONTRACT_RETRY_POLICY_INVALID")
        if type(self.max_output_tokens) is not int or not 1 <= self.max_output_tokens <= MAX_OUTPUT_TOKENS:
            problems.append("ROUTE_CONTRACT_MAX_TOKENS_INVALID")
        for name, value in (("allow_files", self.allow_files),
                            ("allow_images", self.allow_images),
                            ("allow_store", self.allow_store)):
            if type(value) is not bool:
                problems.append(f"ROUTE_CONTRACT_FLAG_INVALID:{name}")
        if (not isinstance(self.allowed_tool_schema_digests, frozenset)
                or any(not isinstance(digest, str)
                       or not REQUEST_DIGEST_RE.fullmatch(digest)
                       for digest in self.allowed_tool_schema_digests)):
            problems.append("ROUTE_CONTRACT_TOOL_DIGESTS_INVALID")
        active = (self.route_kind == ROUTE_KIND_SYNTHETIC
                  and self.activation == ACTIVATION_SYNTHETIC_ONLY)
        if active:
            for name in ("endpoint_host", "method", "exact_path",
                         "request_format_version", "streaming_contract",
                         "tokenizer_price_source_version", "price_source"):
                value = getattr(self, name)
                try:
                    _contract_text(value, name)
                except ValueError:
                    problems.append(f"ROUTE_CONTRACT_FIELD_INVALID:{name}")
            if self.price_source != SYNTHETIC_PRICE_SOURCE:
                problems.append("ROUTE_CONTRACT_PRICE_SOURCE_INVALID")
            if self.endpoint_host != SYNTHETIC_HOST:
                problems.append("ROUTE_CONTRACT_HOST_NOT_FIXTURE")
            if type(self.port) is not int or not 1 <= self.port <= 65535:
                problems.append("ROUTE_CONTRACT_PORT_INVALID")
            if self.method is not None and self.method.upper() not in _METHODS:
                problems.append("ROUTE_CONTRACT_METHOD_INVALID")
            if self.exact_path is not None and (
                    not self.exact_path.startswith("/")
                    or "\\" in self.exact_path or ".." in self.exact_path
                    or "%2e" in self.exact_path.casefold()):
                problems.append("ROUTE_CONTRACT_PATH_INVALID")
        else:
            for name in ("endpoint_host", "port", "method", "exact_path",
                         "request_format_version", "streaming_contract",
                         "tokenizer_price_source_version"):
                if getattr(self, name) is not None:
                    problems.append(f"ROUTE_CONTRACT_BLOCKED_FIELD_SET:{name}")
            if self.price_source != REAL_PRICE_SOURCE:
                problems.append("ROUTE_CONTRACT_BLOCKED_PRICE_SOURCE_INVALID")
        return tuple(problems)

    def send_problems(self) -> tuple[str, ...]:
        """Reasons this contract may never reach a provider call."""
        problems = list(self.contract_problems())
        if self.route_kind != ROUTE_KIND_SYNTHETIC:
            problems.append("REAL_ROUTE_BLOCKED_REQUIRES_HUMAN_VERIFICATION")
        if self.activation != ACTIVATION_SYNTHETIC_ONLY:
            problems.append("ROUTE_ACTIVATION_NOT_SYNTHETIC_ONLY")
        if self.price_source != SYNTHETIC_PRICE_SOURCE:
            problems.append("PRICING_SOURCE_UNVERIFIED")
        return tuple(problems)

    def to_mapping(self) -> dict[str, object]:
        return {
            "schema": G4C_CONTRACT_SCHEMA,
            "route_id": self.route_id, "provider": self.provider,
            "model_id": self.model_id, "endpoint_host": self.endpoint_host,
            "port": self.port, "method": self.method, "exact_path": self.exact_path,
            "request_format_version": self.request_format_version,
            "streaming_contract": self.streaming_contract,
            "tokenizer_price_source_version": self.tokenizer_price_source_version,
            "max_output_tokens": self.max_output_tokens,
            "allowed_tool_schema_digests": sorted(self.allowed_tool_schema_digests),
            "retry_policy": self.retry_policy,
            "allow_files": self.allow_files, "allow_images": self.allow_images,
            "allow_store": self.allow_store, "route_kind": self.route_kind,
            "price_source": self.price_source, "activation": self.activation,
        }

    @classmethod
    def from_mapping(cls, raw: Mapping[str, object]) -> "ProviderRouteContract":
        """Strict loader for a trusted launcher-owned declaration."""
        if not isinstance(raw, Mapping):
            raise TypeError("route contract must be a mapping")
        fields = {"schema", "route_id", "provider", "model_id", "endpoint_host",
                  "port", "method", "exact_path", "request_format_version",
                  "streaming_contract", "tokenizer_price_source_version",
                  "max_output_tokens", "allowed_tool_schema_digests",
                  "retry_policy", "allow_files", "allow_images", "allow_store",
                  "route_kind", "price_source", "activation"}
        if set(raw) != fields:
            raise ValueError("route contract field set is not frozen")
        if raw["schema"] != G4C_CONTRACT_SCHEMA:
            raise ValueError("route contract schema mismatch")
        max_tokens = raw["max_output_tokens"]
        if type(max_tokens) is not int:
            raise ValueError("route contract max_output_tokens must be an int")
        port = raw["port"]
        if port is not None and type(port) is not int:
            raise ValueError("route contract port must be an int")
        flags = {}
        for name in ("allow_files", "allow_images", "allow_store"):
            if type(raw[name]) is not bool:
                raise ValueError(f"route contract {name} must be bool")
            flags[name] = raw[name]
        contract = cls(
            route_id=_contract_text(raw["route_id"], "route_id"),
            provider=_contract_text(raw["provider"], "provider"),
            model_id=_contract_text(raw["model_id"], "model_id"),
            endpoint_host=_contract_text(raw["endpoint_host"], "endpoint_host",
                                         optional=True),
            port=port,
            method=_contract_text(raw["method"], "method", optional=True),
            exact_path=_contract_text(raw["exact_path"], "exact_path", optional=True),
            request_format_version=_contract_text(
                raw["request_format_version"], "request_format_version",
                optional=True),
            streaming_contract=_contract_text(
                raw["streaming_contract"], "streaming_contract", optional=True),
            tokenizer_price_source_version=_contract_text(
                raw["tokenizer_price_source_version"],
                "tokenizer_price_source_version", optional=True),
            max_output_tokens=max_tokens,
            allowed_tool_schema_digests=_contract_digest_set(
                raw["allowed_tool_schema_digests"]),
            retry_policy=_contract_text(raw["retry_policy"], "retry_policy"),
            allow_files=flags["allow_files"], allow_images=flags["allow_images"],
            allow_store=flags["allow_store"],
            route_kind=_contract_text(raw["route_kind"], "route_kind"),
            price_source=_contract_text(raw["price_source"], "price_source"),
            activation=_contract_text(raw["activation"], "activation"),
        )
        problems = contract.contract_problems()
        if problems:
            raise ValueError("invalid route contract: " + ", ".join(problems))
        return contract


SYNTHETIC_ROUTE_CONTRACT = ProviderRouteContract(
    route_id=SYNTHETIC_ROUTE_ID,
    provider=SYNTHETIC_PROVIDER,
    model_id=SYNTHETIC_MODEL_ID,
    endpoint_host=SYNTHETIC_HOST,
    port=SYNTHETIC_PORT,
    method="POST",
    exact_path=SYNTHETIC_EXACT_PATH,
    request_format_version=SYNTHETIC_FORMAT_VERSION,
    streaming_contract=SYNTHETIC_STREAMING_CONTRACT,
    tokenizer_price_source_version=SYNTHETIC_PRICE_SOURCE,
    max_output_tokens=MAX_OUTPUT_TOKENS,
    allowed_tool_schema_digests=frozenset({SKILL_LOOKUP_SCHEMA_DIGEST}),
    retry_policy=RETRY_POLICY_NO_RETRY,
    allow_files=False,
    allow_images=False,
    allow_store=False,
    route_kind=ROUTE_KIND_SYNTHETIC,
    price_source=SYNTHETIC_PRICE_SOURCE,
    activation=ACTIVATION_SYNTHETIC_ONLY,
)

REAL_ROUTE_TEMPLATE = ProviderRouteContract(
    route_id="deepseek-official",
    provider="deepseek",
    model_id="REQUIRES_VERIFICATION",
    endpoint_host=None,
    port=None,
    method=None,
    exact_path=None,
    request_format_version=None,
    streaming_contract=None,
    tokenizer_price_source_version=None,
    max_output_tokens=MAX_OUTPUT_TOKENS,
    allowed_tool_schema_digests=frozenset(),
    retry_policy=RETRY_POLICY_NO_RETRY,
    allow_files=False,
    allow_images=False,
    allow_store=False,
    route_kind=ROUTE_KIND_REAL,
    price_source=REAL_PRICE_SOURCE,
    activation=ACTIVATION_BLOCKED,
)


@dataclass(frozen=True)
class SyntheticSendBudget:
    """Synthetic fixture budget; the $10 hard cap is an engineering bound only."""

    soft_total_usd: Decimal = Decimal("3.00")
    hard_total_usd: Decimal = Decimal("10.00")
    soft_call_usd: Decimal = Decimal("0.10")
    hard_call_usd: Decimal = Decimal("0.20")
    max_sends: int = 50

    def budget_problems(self) -> tuple[str, ...]:
        problems: list[str] = []
        for name in ("soft_total_usd", "hard_total_usd", "soft_call_usd",
                     "hard_call_usd"):
            value = getattr(self, name)
            if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
                problems.append(f"BUDGET_VALUE_INVALID:{name}")
        if problems:
            return tuple(problems)
        if self.soft_total_usd > self.hard_total_usd:
            problems.append("BUDGET_SOFT_TOTAL_EXCEEDS_HARD")
        if self.soft_call_usd > self.hard_call_usd:
            problems.append("BUDGET_SOFT_CALL_EXCEEDS_HARD")
        if self.hard_call_usd > self.hard_total_usd:
            problems.append("BUDGET_CALL_EXCEEDS_TOTAL")
        if type(self.max_sends) is not int or not 1 <= self.max_sends <= 50:
            problems.append("BUDGET_MAX_SENDS_INVALID")
        return tuple(problems)


# ---------------------------------------------------------------------------
# G4-F3 cost authority semantics.
#
# The Broker Reservation/Settlement is the ONLY cost authority. The gate keeps a
# process-local, read-only, conservative view so that an unresolved (PENDING /
# uncertain) send is never reported as free. The view never prices usage, never
# writes back to the Broker and never substitutes for ``reserved_cost`` or the
# settlement ``cost_usd``.
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# G4-F5 revocation semantics (synthetic authorization lifetime).
#
# The trusted launcher owns one synthetic run authorization (``auth_epoch`` /
# ``authorization_id``). A root-owned revocation document can revoke it while a
# dispatch is in flight. The gate re-reads that document at two checkpoints:
#
#   pre_dispatch : immediately before a send capability is minted;
#   pre_send     : immediately before that capability is consumed (the last
#                  point at which a send can still be refused).
#
# The file is an *input*, never an authority: it cannot mint, settle or price a
# send. Absence of a configured revocation source keeps the F3/F4 behaviour
# byte-for-byte. Once configured, an unreadable/invalid document fails closed
# (``REVOCATION_STATE_INVALID``) because ignoring a revocation is worse than
# refusing to send. A revocation observed after the wire boundary cannot
# retract the send; the Broker settlement stays authoritative and the caller
# must not resend.
# ---------------------------------------------------------------------------
REVOCATION_SCHEMA = "m0.g4c.revocation.v1"
REVOCATION_CHECK_SCHEMA = "m0.g4c.revocation-check.v1"
RUN_AUTHORIZATION_REVOKED = "RUN_AUTHORIZATION_REVOKED"
REVOCATION_STATE_INVALID = "REVOCATION_STATE_INVALID"
MAX_REVOCATION_BYTES = 64 * 1024
REVOCATION_CHECK_LIMIT = 64
_REVOCATION_KEYS = frozenset({"schema", "authorization_id", "auth_epoch",
                              "revoked", "revoked_utc", "reason"})
COST_VIEW_SCHEMA = "m0.g4c.cost-view.v1"
COST_AUTHORITY_BROKER = "broker_reservation_settlement"
COST_VIEW_ROLE = "conservative_read_only_view"
COST_VIEW_SCOPE = "process_local"
COST_VIEW_HELD = "HELD"
COST_VIEW_SETTLED_KNOWN = "SETTLED_KNOWN"
COST_VIEW_SETTLED_CONSERVATIVE = "SETTLED_CONSERVATIVE"
BROKER_STATUS_PENDING = "PENDING"
BROKER_STATUS_OK = "OK"
BROKER_STATUS_FAILED = "FAILED"
COST_VIEW_EVENT_LIMIT = 512


def _usd_amount(value: object) -> Decimal | None:
    """Strict non-negative finite Decimal; bool/NaN/Infinity/negative are invalid."""
    if value is None or isinstance(value, bool):
        return None
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not amount.is_finite() or amount < 0:
        return None
    return amount


@dataclass
class SendCostView:
    """One reservation's conservative cost view copied from the Broker.

    ``held_usd`` is the upper bound of what the Broker may still commit for a
    PENDING reservation; ``known_usd`` is the Broker's final cost once (and
    only once) a terminal status with a valid cost has been observed.
    """

    reservation_id: str
    call_id: str = ""
    attempt_ordinal: int = 1
    state: str = COST_VIEW_HELD
    broker_status: str = BROKER_STATUS_PENDING
    held_usd: Decimal = Decimal("0")
    known_usd: Decimal = Decimal("0")
    held_source: str = ""
    known_source: str = ""
    updated_utc: str = ""
    transitions: int = 0

    def to_mapping(self) -> dict[str, object]:
        return {
            "reservation_id": self.reservation_id,
            "call_id": self.call_id or None,
            "attempt_ordinal": self.attempt_ordinal,
            "state": self.state,
            "broker_status": self.broker_status,
            "held_usd": format(self.held_usd, "f"),
            "known_usd": format(self.known_usd, "f"),
            "held_source": self.held_source or None,
            "known_source": self.known_source or None,
            "updated_utc": self.updated_utc,
            "transitions": self.transitions,
        }


@dataclass(frozen=True)
class TrustedSendAuthorization:
    """Trusted-domain single-use send capability; no JSON constructor exists.

    ``TrustedSendGate.consume`` accepts only the exact object this process
    minted (identity check), so a candidate-supplied mapping or a copied
    dataclass is never a credential.
    """

    authorization_id: str
    scope_id: str
    run_id: str
    call_id: str
    prepared_digest: str
    payload_digest: str
    payload_length: int
    attempt_ordinal: int
    reservation_id: str
    broker_claim_id: str
    broker_claim_digest: str
    route_id: str
    model_id: str
    auth_epoch: str
    issued_utc: str
    expires_utc: str
    route_kind: str
    synthetic: bool = True
    schema_version: str = G4C_SEND_AUTHORIZATION_SCHEMA

    def __post_init__(self) -> None:
        if self.schema_version != G4C_SEND_AUTHORIZATION_SCHEMA:
            raise ValueError("send authorization schema mismatch")
        if not isinstance(self.authorization_id, str) or not _SEND_ID_RE.fullmatch(
                self.authorization_id):
            raise ValueError("send authorization id invalid")
        if not isinstance(self.call_id, str) or not CALL_ID_RE.fullmatch(self.call_id):
            raise ValueError("send authorization call id invalid")
        for name in ("prepared_digest", "payload_digest", "broker_claim_digest"):
            value = getattr(self, name)
            if not isinstance(value, str) or not REQUEST_DIGEST_RE.fullmatch(value):
                raise ValueError(f"send authorization {name} invalid")
        if type(self.payload_length) is not int or self.payload_length < 0:
            raise ValueError("send authorization payload length invalid")
        if type(self.attempt_ordinal) is not int or self.attempt_ordinal < 1:
            raise ValueError("send authorization attempt invalid")
        for name in ("scope_id", "run_id", "reservation_id", "broker_claim_id",
                     "route_id", "model_id", "auth_epoch"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value or value != value.strip():
                raise ValueError(f"send authorization {name} invalid")
        for name in ("issued_utc", "expires_utc"):
            value = getattr(self, name)
            if not isinstance(value, str) or not _UTC_TEXT.fullmatch(value):
                raise ValueError(f"send authorization {name} invalid")
        if self.expires_utc <= self.issued_utc:
            raise ValueError("send authorization expiry must follow issue time")
        if self.route_kind != ROUTE_KIND_SYNTHETIC or self.synthetic is not True:
            raise ValueError("only synthetic send authorizations exist in G4-C")

    def to_audit_dict(self) -> dict[str, object]:
        """Full binding record; deliberately no secret material exists here."""
        return {
            "schema": self.schema_version,
            "authorization_id": self.authorization_id,
            "scope_id": self.scope_id,
            "run_id": self.run_id,
            "call_id": self.call_id,
            "prepared_digest": self.prepared_digest,
            "payload_digest": self.payload_digest,
            "payload_length": self.payload_length,
            "attempt_ordinal": self.attempt_ordinal,
            "reservation_id": self.reservation_id,
            "broker_claim_id": self.broker_claim_id,
            "broker_claim_digest": self.broker_claim_digest,
            "route_id": self.route_id,
            "model_id": self.model_id,
            "auth_epoch": self.auth_epoch,
            "issued_utc": self.issued_utc,
            "expires_utc": self.expires_utc,
            "route_kind": self.route_kind,
            "synthetic": self.synthetic,
        }


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_text(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _payload_digest(payload_bytes: bytes) -> str:
    return hashlib.sha256(payload_bytes).hexdigest()


def tool_schema_digest(tool: Mapping[str, object]) -> str:
    """Canonical SHA-256 used by the frozen tool-schema allowlist."""
    return hashlib.sha256(canonical_json(dict(tool)).encode("utf-8")).hexdigest()


class TrustedSendGate:
    """Mint/consume TrustedSendAuthorization and enforce the G4-C pre-dispatch set."""

    def __init__(self, contract: ProviderRouteContract, *,
                 budget: SyntheticSendBudget | None = None,
                 auth_epoch: str = "",
                 journal_path: str | os.PathLike[str] | None = None,
                 binding_approved: ExpectedBindings | None = None,
                 binding_observer: Callable[[], ExpectedBindings] | None = None,
                 binding_checkpoint: str = "pre_dispatch",
                 authorization_id: str | None = None,
                 revocation_path: str | os.PathLike[str] | None = None,
                 ttl_seconds: int = SEND_AUTHORIZATION_TTL_SECONDS,
                 limit: int = SEND_AUTHORIZATION_LIMIT,
                 now: Callable[[], datetime] = _utc_now) -> None:
        if not isinstance(contract, ProviderRouteContract):
            raise TypeError("contract must be a ProviderRouteContract")
        if not isinstance(auth_epoch, str) or not auth_epoch or auth_epoch != auth_epoch.strip():
            raise ValueError("auth_epoch must be a nonempty identifier")
        if binding_checkpoint not in {"pre_start", "pre_reserve", "pre_dispatch"}:
            raise ValueError("unknown binding checkpoint")
        if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 300:
            raise ValueError("invalid send authorization ttl")
        if type(limit) is not int or not 1 <= limit <= SEND_AUTHORIZATION_LIMIT:
            raise ValueError("invalid send authorization limit")
        resolved_authorization = auth_epoch if authorization_id is None else authorization_id
        if (not isinstance(resolved_authorization, str)
                or not resolved_authorization
                or resolved_authorization != resolved_authorization.strip()):
            raise ValueError("authorization_id must be a nonempty identifier")
        if revocation_path is not None and not isinstance(
                revocation_path, (str, os.PathLike)):
            raise ValueError("revocation_path must be a path or None")
        self.contract = contract
        self.budget = budget or SyntheticSendBudget()
        budget_problems = self.budget.budget_problems()
        if budget_problems:
            raise ValueError("invalid synthetic budget: " + ", ".join(budget_problems))
        self.auth_epoch = auth_epoch
        self.authorization_id = resolved_authorization
        self.revocation_path = (os.fspath(revocation_path)
                                if revocation_path is not None else None)
        self._revocation_lock = threading.RLock()
        self._revocation_checks: list[dict[str, object]] = []
        self._revocation_last: dict[str, object] | None = None
        self.journal_path = str(journal_path) if journal_path is not None else None
        self.binding_approved = binding_approved
        self.binding_observer = binding_observer
        self.binding_checkpoint = binding_checkpoint
        self.ttl_seconds = ttl_seconds
        self.limit = limit
        self._now = now
        self._issued: dict[int, TrustedSendAuthorization] = {}
        self._consumed: set[str] = set()
        self._known_usd = Decimal("0")
        self._held_usd = Decimal("0")
        # G4-F3: per-reservation conservative cost view + one transition log.
        # The lock makes the admission check and the hold atomic so concurrent
        # authorizes can never double-hold or oversell the hard total.
        self._cost_lock = threading.RLock()
        self._cost_views: dict[str, SendCostView] = {}
        self._cost_events: list[dict[str, object]] = []
        self._broker_view_source = "not_observed"
        self._broker_view_observed = False
        self._soft_events: list[dict[str, object]] = []
        self._denials: list[dict[str, object]] = []
        self._sends = 0
        self.send_problems = contract.send_problems()

    # -- audit ---------------------------------------------------------
    def _journal(self, document: Mapping[str, object]) -> None:
        if self.journal_path is None:
            return
        data = (canonical_json(dict(document)) + "\n").encode("utf-8")
        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(self.journal_path, flags, 0o600)
        except OSError as error:
            raise EgressViolation(("SEND_JOURNAL_UNAVAILABLE",)) from error
        try:
            written = 0
            while written < len(data):
                written += os.write(descriptor, data[written:])
            os.fsync(descriptor)
        except OSError as error:
            raise EgressViolation(("SEND_JOURNAL_WRITE_FAILED",)) from error
        finally:
            os.close(descriptor)

    def _deny(self, reasons: Iterable[str], **detail: object) -> EgressViolation:
        codes = tuple(reasons) or ("EGRESS_DENIED",)
        record = {"decision": "DENIED", "utc": _utc_text(self._now()),
                  "reasons": list(codes), "detail": detail}
        self._denials.append(record)
        try:
            self._journal(record)
        except EgressViolation:
            pass
        return EgressViolation(codes)

    # -- G4-F5 revocation input (read-only; never an authority) ---------
    def read_revocation_state(self) -> dict[str, object]:
        """Read the synthetic run-authorization revocation document.

        The document is a trusted *input* (root-owned state dir). It never
        carries a cost, a capability or a settlement. When no path is
        configured the gate behaves exactly as in G4-F3/F4.
        """
        base: dict[str, object] = {
            "configured": self.revocation_path is not None,
            "path": self.revocation_path,
            "valid": False, "revoked": False, "targets_run": False,
            "reason": None, "sha256": None, "bytes": None,
            "utc": _utc_text(self._now()),
        }
        if self.revocation_path is None:
            return base
        flags = os.O_RDONLY | os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(self.revocation_path, flags)
        except OSError as error:
            return {**base, "reason": REVOCATION_STATE_INVALID,
                    "error": f"OPEN_FAILED:{type(error).__name__}"}
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode):
                return {**base, "reason": REVOCATION_STATE_INVALID,
                        "error": "NOT_A_REGULAR_FILE"}
            if info.st_size <= 0 or info.st_size > MAX_REVOCATION_BYTES:
                return {**base, "reason": REVOCATION_STATE_INVALID,
                        "error": "SIZE_INVALID", "bytes": info.st_size}
            raw = os.read(descriptor, MAX_REVOCATION_BYTES + 1)
        except OSError as error:
            return {**base, "reason": REVOCATION_STATE_INVALID,
                    "error": f"READ_FAILED:{type(error).__name__}"}
        finally:
            os.close(descriptor)
        base["bytes"] = len(raw)
        base["sha256"] = hashlib.sha256(raw).hexdigest()
        try:
            document = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {**base, "reason": REVOCATION_STATE_INVALID,
                    "error": "JSON_INVALID"}
        if not isinstance(document, dict) or set(document) != _REVOCATION_KEYS:
            return {**base, "reason": REVOCATION_STATE_INVALID,
                    "error": "FIELDS_INVALID"}
        if document.get("schema") != REVOCATION_SCHEMA:
            return {**base, "reason": REVOCATION_STATE_INVALID,
                    "error": "SCHEMA_INVALID"}
        for name in ("authorization_id", "auth_epoch", "revoked_utc", "reason"):
            value = document.get(name)
            if not isinstance(value, str) or not value or value != value.strip():
                return {**base, "reason": REVOCATION_STATE_INVALID,
                        "error": f"{name.upper()}_INVALID"}
        if type(document.get("revoked")) is not bool:
            return {**base, "reason": REVOCATION_STATE_INVALID,
                    "error": "REVOKED_NOT_BOOL"}
        target_ids = {self.authorization_id, "*"}
        targets_run = (document["authorization_id"] in target_ids
                       and document["auth_epoch"] == self.auth_epoch)
        return {
            **base, "valid": True, "targets_run": targets_run,
            "revoked": bool(document["revoked"] and targets_run),
            "state_authorization_id": document["authorization_id"],
            "state_auth_epoch": document["auth_epoch"],
            "revoked_utc": document["revoked_utc"],
            "state_reason": document["reason"],
        }

    def revocation_check(self, checkpoint: str) -> dict[str, object]:
        """One bounded, recorded observation of the revocation input.

        Returns the observation; ``reason`` is non-empty when the current send
        must be refused. An unreadable/invalid configured document fails closed.
        """
        state = self.read_revocation_state()
        reason = state.get("reason")
        if not reason and state.get("revoked"):
            reason = RUN_AUTHORIZATION_REVOKED
        entry: dict[str, object] = {
            "schema": REVOCATION_CHECK_SCHEMA,
            "checkpoint": checkpoint,
            "utc": _utc_text(self._now()),
            "configured": state.get("configured"),
            "valid": state.get("valid"),
            "targets_run": state.get("targets_run"),
            "revoked": bool(reason),
            "reason": reason,
            "state_sha256": state.get("sha256"),
            "authorization_id": self.authorization_id,
            "auth_epoch": self.auth_epoch,
        }
        with self._revocation_lock:
            self._revocation_last = dict(entry)
            if len(self._revocation_checks) >= REVOCATION_CHECK_LIMIT:
                del self._revocation_checks[
                    : len(self._revocation_checks) - REVOCATION_CHECK_LIMIT + 1]
            self._revocation_checks.append(dict(entry))
        if reason:
            try:
                self._journal({"decision": "REVOCATION_CHECK", **entry})
            except EgressViolation:
                pass
        return entry

    # -- G4-F3 conservative cost view (Broker is the only authority) ----
    def _cost_event(self, kind: str, *, reservation_id: str = "",
                    **detail: object) -> None:
        if len(self._cost_events) >= COST_VIEW_EVENT_LIMIT:
            del self._cost_events[: len(self._cost_events) - COST_VIEW_EVENT_LIMIT + 1]
        self._cost_events.append({
            "kind": kind, "utc": _utc_text(self._now()),
            "reservation_id": reservation_id or None,
            "detail": dict(detail),
        })

    def _refresh_cost_totals(self) -> None:
        self._known_usd = sum((view.known_usd for view in self._cost_views.values()),
                              Decimal("0"))
        self._held_usd = sum((view.held_usd for view in self._cost_views.values()),
                             Decimal("0"))

    def _hold_bound(self, cost: Decimal, supplied: object) -> Decimal | None:
        """Conservative per-attempt bound; never zero and never below ``cost``.

        A supplied bound is a trusted caller's conservative upper bound (the
        Broker Reserve ``reserved_cost`` when wired); it must be a positive
        finite Decimal or the authorization fails closed.
        """
        if supplied is not None:
            amount = _usd_amount(supplied)
            if amount is None or amount <= 0:
                return None
            return max(cost, amount)
        return max(cost, self.budget.hard_call_usd)

    def _hold_reservation_locked(self, *, reservation_id: str, call_id: str,
                                 attempt_ordinal: int, hold_usd: Decimal,
                                 source: str, refine: bool = False) -> str:
        view = self._cost_views.get(reservation_id)
        if view is not None and view.state != COST_VIEW_HELD:
            # A settled reservation must never be re-held: that would be a
            # second charge for the same Broker row.
            self._cost_event("RESERVATION_ALREADY_SETTLED_REUSED",
                             reservation_id=reservation_id,
                             state=view.state, broker_status=view.broker_status,
                             source=source)
            return "RESERVATION_ALREADY_SETTLED"
        if view is None:
            view = SendCostView(reservation_id=reservation_id,
                                call_id=str(call_id or ""),
                                attempt_ordinal=int(attempt_ordinal))
            self._cost_views[reservation_id] = view
        elif call_id and view.call_id and str(call_id) != view.call_id:
            # One reservation receives at most one Broker charge; two call ids
            # for it is a protocol anomaly, so keep one view and audit it.
            self._cost_event("RESERVATION_REUSED_BEFORE_SETTLEMENT",
                             reservation_id=reservation_id,
                             prior_call_id=view.call_id, call_id=str(call_id),
                             source=source)
        if refine and hold_usd > 0:
            # The Broker's reserved_cost is the authoritative upper bound, so it
            # may replace a coarser local estimate downward (never to zero).
            view.held_usd = hold_usd
        elif hold_usd > view.held_usd or view.held_usd <= 0:
            view.held_usd = hold_usd
        view.state = COST_VIEW_HELD
        view.broker_status = BROKER_STATUS_PENDING
        view.held_source = source
        view.updated_utc = _utc_text(self._now())
        view.transitions += 1
        self._refresh_cost_totals()
        self._cost_event("HOLD", reservation_id=reservation_id,
                         held_usd=format(view.held_usd, "f"),
                         held_source=source, call_id=str(call_id or ""),
                         refined=bool(refine))
        return "HELD"

    def _settle_reservation_locked(self, *, reservation_id: str, broker_status: str,
                                   cost_usd: Decimal, call_id: str,
                                   attempt_ordinal: int, source: str) -> str:
        view = self._cost_views.get(reservation_id)
        if view is None:
            # Crash/reconcile: the new process never authorized this send, but
            # the Broker's terminal state is authoritative evidence that it is
            # committed.
            view = SendCostView(reservation_id=reservation_id,
                                call_id=str(call_id or ""),
                                attempt_ordinal=int(attempt_ordinal))
            self._cost_views[reservation_id] = view
        if view.state != COST_VIEW_HELD:
            if view.broker_status == broker_status and view.known_usd == cost_usd:
                self._cost_event("SETTLEMENT_ALREADY_RECORDED",
                                 reservation_id=reservation_id,
                                 broker_status=broker_status,
                                 cost_usd=format(cost_usd, "f"), source=source)
                return "ALREADY_RECORDED"
            self._cost_event("BROKER_SETTLEMENT_CONFLICT",
                             reservation_id=reservation_id,
                             recorded_status=view.broker_status,
                             recorded_cost_usd=format(view.known_usd, "f"),
                             observed_status=broker_status,
                             observed_cost_usd=format(cost_usd, "f"),
                             source=source)
            return "BROKER_SETTLEMENT_CONFLICT"
        view.held_usd = Decimal("0")
        view.known_usd = cost_usd
        view.state = (COST_VIEW_SETTLED_KNOWN
                      if broker_status == BROKER_STATUS_OK
                      else COST_VIEW_SETTLED_CONSERVATIVE)
        view.broker_status = broker_status
        view.known_source = source
        view.updated_utc = _utc_text(self._now())
        view.transitions += 1
        self._refresh_cost_totals()
        self._cost_event("SETTLEMENT_OK" if broker_status == BROKER_STATUS_OK
                         else "SETTLEMENT_FAILED",
                         reservation_id=reservation_id,
                         known_usd=format(cost_usd, "f"),
                         broker_status=broker_status, source=source)
        return "SETTLED"

    def record_broker_status(self, status: Mapping[str, object], *,
                             source: str = "broker_status") -> str:
        """Copy one read-only Broker ``reservation_status`` reply into the view.

        The Broker answer is authoritative. An unavailable/unknown answer never
        releases a hold; a terminal answer without a valid cost also keeps the
        hold (no false FREE).
        """
        if not isinstance(status, Mapping):
            self._cost_event("BROKER_STATUS_INVALID", source=source)
            return "BROKER_STATUS_INVALID"
        reservation_id = status.get("reservation_id")
        if not isinstance(reservation_id, str) or not reservation_id:
            self._cost_event("BROKER_STATUS_INVALID", source=source)
            return "BROKER_STATUS_INVALID"
        if status.get("ok") is not True or status.get("found") is not True:
            self._cost_event("BROKER_STATUS_UNAVAILABLE",
                             reservation_id=reservation_id, source=source,
                             code=str(status.get("code") or "") or None,
                             found=status.get("found"))
            return "BROKER_STATUS_UNAVAILABLE"
        broker_status = status.get("status")
        call_id = status.get("call_id") if isinstance(status.get("call_id"), str) else ""
        with self._cost_lock:
            self._broker_view_observed = True
            self._broker_view_source = source
            if broker_status == BROKER_STATUS_PENDING:
                reserved = _usd_amount(status.get("reserved_cost"))
                if reserved is None or reserved <= 0:
                    self._cost_event("BROKER_RESERVED_COST_UNKNOWN",
                                     reservation_id=reservation_id, source=source,
                                     reserved_cost=str(status.get("reserved_cost")))
                    return "BROKER_RESERVED_COST_UNKNOWN"
                return self._hold_reservation_locked(
                    reservation_id=reservation_id, call_id=call_id,
                    attempt_ordinal=1, hold_usd=reserved, source=source,
                    refine=True)
            if broker_status in {BROKER_STATUS_OK, BROKER_STATUS_FAILED}:
                cost = _usd_amount(status.get("cost"))
                if cost is None:
                    self._cost_event("BROKER_COST_UNKNOWN",
                                     reservation_id=reservation_id,
                                     broker_status=str(broker_status), source=source,
                                     cost=str(status.get("cost")))
                    return "BROKER_COST_UNKNOWN"
                return self._settle_reservation_locked(
                    reservation_id=reservation_id, broker_status=str(broker_status),
                    cost_usd=cost, call_id=call_id, attempt_ordinal=1, source=source)
            self._cost_event("BROKER_STATUS_UNKNOWN", reservation_id=reservation_id,
                             broker_status=str(broker_status), source=source)
            return "BROKER_STATUS_UNKNOWN"

    def record_broker_settlement(self, *, reservation_id: str,
                                 broker_status: str, cost_usd: object = None,
                                 settlement: Mapping[str, object] | None = None,
                                 call_id: str = "", attempt_ordinal: int = 1,
                                 source: str = "broker_completion") -> str:
        """Archive one Broker terminal settlement exactly once.

        ``broker_status`` is the Broker state (``OK`` for settle, ``FAILED`` for
        fail); ``cost_usd``/``settlement.cost_usd`` is the Broker's final cost.
        Missing or invalid costs keep the hold instead of inventing a number.
        """
        if not isinstance(reservation_id, str) or not reservation_id:
            self._cost_event("BROKER_SETTLEMENT_INVALID", source=source)
            return "BROKER_SETTLEMENT_INVALID"
        if broker_status not in {BROKER_STATUS_OK, BROKER_STATUS_FAILED}:
            self._cost_event("BROKER_SETTLEMENT_INVALID",
                             reservation_id=reservation_id,
                             broker_status=str(broker_status), source=source)
            return "BROKER_SETTLEMENT_INVALID"
        raw_cost = cost_usd
        if raw_cost is None and isinstance(settlement, Mapping):
            raw_cost = settlement.get("cost_usd")
        cost = _usd_amount(raw_cost)
        if cost is None:
            self._cost_event("BROKER_COST_UNKNOWN", reservation_id=reservation_id,
                             broker_status=broker_status, source=source,
                             cost=str(raw_cost))
            return "BROKER_COST_UNKNOWN"
        with self._cost_lock:
            self._broker_view_observed = True
            self._broker_view_source = source
            return self._settle_reservation_locked(
                reservation_id=reservation_id, broker_status=broker_status,
                cost_usd=cost, call_id=call_id, attempt_ordinal=attempt_ordinal,
                source=source)

    def cost_view(self, reservation_id: str) -> dict[str, object] | None:
        """Read-only copy of one reservation's conservative view (or None)."""
        with self._cost_lock:
            view = self._cost_views.get(reservation_id)
            return None if view is None else view.to_mapping()

    def _cost_mapping_locked(self) -> dict[str, object]:
        views = [self._cost_views[key].to_mapping()
                 for key in sorted(self._cost_views)]
        unresolved = sum(1 for view in self._cost_views.values()
                         if view.state == COST_VIEW_HELD)
        return {
            "schema": COST_VIEW_SCHEMA,
            "authority": COST_AUTHORITY_BROKER,
            "role": COST_VIEW_ROLE,
            "billing_authority": False,
            "scope": COST_VIEW_SCOPE,
            "reconciled_with_broker": self._broker_view_observed,
            "broker_view_source": self._broker_view_source,
            "known_cost_usd": format(self._known_usd, "f"),
            "worst_case_held_usd": format(self._held_usd, "f"),
            "committed_usd": format(self._known_usd + self._held_usd, "f"),
            "held_reservations": unresolved,
            "settled_reservations": len(self._cost_views) - unresolved,
            "unresolved_reservations": unresolved,
            "reservations": views,
            "events": [dict(event) for event in self._cost_events],
            "invariants": {
                "known_nonnegative": self._known_usd >= 0,
                "held_nonnegative": self._held_usd >= 0,
                "no_free_unresolved": all(
                    view.held_usd > 0 for view in self._cost_views.values()
                    if view.state == COST_VIEW_HELD),
                "one_view_per_reservation": len(views) == len(self._cost_views),
                "totals_equal_view_sum": (
                    self._known_usd == sum(
                        (view.known_usd for view in self._cost_views.values()),
                        Decimal("0"))
                    and self._held_usd == sum(
                        (view.held_usd for view in self._cost_views.values()),
                        Decimal("0"))),
            },
        }

    # -- pre-dispatch binding check (G4-A wiring) ----------------------
    def pre_dispatch_binding_reasons(self) -> tuple[str, ...]:
        if self.binding_approved is None or self.binding_observer is None:
            return ("PRE_DISPATCH_CHECK_INCOMPLETE",)
        try:
            observed = self.binding_observer()
        except BaseException:  # noqa: BLE001 - any observer failure fails closed
            return ("PRE_DISPATCH_CHECK_ERROR",)
        if not isinstance(observed, ExpectedBindings):
            return ("PRE_DISPATCH_CHECK_INVALID",)
        try:
            return binding_drift(self.binding_checkpoint,
                                 approved=self.binding_approved,
                                 observed=observed)
        except (TypeError, ValueError):
            return ("PRE_DISPATCH_CHECK_INVALID",)

    # -- authorization -------------------------------------------------
    def authorize(self, *, prepared: PreparedProviderRequest,
                  request: EgressRequest, permission: object,
                  payload_bytes: bytes, payload_digest: str,
                  reservation_id: str, broker_claim_id: str,
                  broker_claim_digest: str, payload_length: int,
                  estimated_cost_usd: str | None = None,
                  worst_case_usd: str | None = None) -> TrustedSendAuthorization:
        """Mint one capability or raise EgressViolation with stable reasons.

        ``worst_case_usd`` is an optional trusted conservative upper bound for
        this send (the Broker Reserve ``reserved_cost`` when wired). It only
        sizes the gate's conservative view; it is never a second price
        authority and never alters the Broker's eventual settlement.
        """
        reasons: list[str] = []
        if self.send_problems:
            raise self._deny(self.send_problems)
        # G4-F5: revocation is checked before any other capability work, and a
        # revoked/unreadable state denies the mint (no hold, no journal grant).
        revocation = self.revocation_check("pre_dispatch")
        if revocation.get("reason"):
            reasons.append(str(revocation["reason"]))
        if not isinstance(prepared, PreparedProviderRequest):
            raise self._deny((PREPARED_REQUEST_INVALID,))
        schema_error = prepared_schema_error(prepared)
        if schema_error is not None:
            raise self._deny((schema_error,))
        computed_prepared = prepared_request_digest(prepared)
        computed_call_id = prepared_call_id(prepared)
        if prepared.request_digest != computed_prepared:
            reasons.append(PREPARED_DIGEST_MISMATCH)
        if request.request_digest != computed_prepared:
            reasons.append(REQUEST_DIGEST_MISMATCH)
        if prepared.call_id != computed_call_id:
            reasons.append(PREPARED_CALL_ID_MISMATCH)
        if request.call_id != computed_call_id:
            reasons.append(REQUEST_CALL_ID_MISMATCH)
        # Exact route contract binding (no prefix/wildcard comparisons).
        if prepared.route_id != self.contract.route_id:
            reasons.append("ROUTE_CONTRACT_MISMATCH:route_id")
        if prepared.provider != self.contract.provider:
            reasons.append("ROUTE_CONTRACT_MISMATCH:provider")
        if prepared.model != self.contract.model_id:
            reasons.append("ROUTE_CONTRACT_MISMATCH:model_id")
        if prepared.host != self.contract.endpoint_host:
            reasons.append("ROUTE_CONTRACT_MISMATCH:host")
        if prepared.port != self.contract.port:
            reasons.append("ROUTE_CONTRACT_MISMATCH:port")
        if (not isinstance(prepared.method, str)
                or prepared.method.upper() != str(self.contract.method).upper()):
            reasons.append("ROUTE_CONTRACT_MISMATCH:method")
        if prepared.path != self.contract.exact_path:
            reasons.append("ROUTE_CONTRACT_MISMATCH:path")
        if prepared.stream != (self.contract.streaming_contract != "none"):
            reasons.append("ROUTE_CONTRACT_MISMATCH:stream")
        if prepared.max_output_tokens > self.contract.max_output_tokens:
            reasons.append("MAX_TOKENS_EXCEEDED")
        if prepared.retry_policy is not None:
            reasons.append("RETRY_POLICY_NOT_APPROVED")
        flag_map = (("has_files", "allow_files"), ("has_images", "allow_images"),
                    ("store", "allow_store"))
        for name, policy_name in flag_map:
            if getattr(prepared, name) is True and not getattr(self.contract, policy_name):
                reasons.append(f"{name.upper()}_NOT_PERMITTED")
        # The transport request is what the provider closure receives.
        if request.max_tokens > self.contract.max_output_tokens:
            reasons.append("MAX_TOKENS_EXCEEDED")
        if request.host != self.contract.endpoint_host or request.port != self.contract.port:
            reasons.append("ROUTE_CONTRACT_MISMATCH:request_host")
        if (not isinstance(request.method, str)
                or request.method.upper() != str(self.contract.method).upper()):
            reasons.append("ROUTE_CONTRACT_MISMATCH:request_method")
        if request.path != self.contract.exact_path:
            reasons.append("ROUTE_CONTRACT_MISMATCH:request_path")
        for name, policy_name in flag_map:
            if getattr(request, name) is True and not getattr(self.contract, policy_name):
                reasons.append(f"{name.upper()}_NOT_PERMITTED")
        try:
            tool_digests = {tool_schema_digest(tool) for tool in prepared.tools}
        except (TypeError, ValueError):
            tool_digests = set()
            reasons.append("TOOL_SCHEMA_INVALID")
        if not tool_digests.issubset(set(self.contract.allowed_tool_schema_digests)):
            reasons.append(TOOL_SCHEMA_NOT_APPROVED)
        # Claim/permission binding.
        if not isinstance(permission, DispatchPermission):
            reasons.append("DISPATCH_PERMISSION_REQUIRED")
        else:
            claim = permission.claim
            claim_map = getattr(claim, "claim", None)
            if not isinstance(claim, ClaimResult) or claim.claimed is not True:
                reasons.append("DISPATCH_PERMISSION_REQUIRED")
            elif not isinstance(claim_map, Mapping):
                reasons.append("BROKER_CLAIM_INVALID")
            else:
                if claim_map.get("call_id") != computed_call_id:
                    reasons.append("BROKER_CLAIM_CALL_MISMATCH")
                if claim_map.get("reservation_id") != reservation_id:
                    reasons.append("BROKER_CLAIM_RESERVATION_MISMATCH")
                if claim_map.get("request_digest") != computed_prepared:
                    reasons.append("BROKER_CLAIM_DIGEST_MISMATCH")
                if hashlib.sha256(canonical_json(dict(claim_map)).encode()).hexdigest() \
                        != broker_claim_digest:
                    reasons.append("BROKER_CLAIM_DIGEST_INVALID")
                if str(broker_claim_id) != str(claim_map.get("call_id")):
                    reasons.append("BROKER_CLAIM_ID_MISMATCH")
            if permission.call_id != computed_call_id:
                reasons.append("PERMISSION_CALL_MISMATCH")
            if permission.request_digest != computed_prepared:
                reasons.append("PERMISSION_DIGEST_MISMATCH")
            if permission.logical_stream_id != request.logical_stream_id:
                reasons.append("PERMISSION_STREAM_MISMATCH")
            if permission.reservation_id != reservation_id:
                reasons.append("PERMISSION_RESERVATION_MISMATCH")
            if permission.attempt_ordinal != request.attempt_ordinal:
                reasons.append("PERMISSION_ATTEMPT_MISMATCH")
            if permission.route_model != (self.contract.route_id,
                                          self.contract.model_id):
                reasons.append("PERMISSION_ROUTE_MISMATCH")
        # Actual bytes: length + digest + minimal wire binding re-checked here.
        if not isinstance(payload_bytes, bytes) or type(payload_length) is not int:
            reasons.append("PAYLOAD_BYTES_INVALID")
        else:
            if len(payload_bytes) != payload_length:
                reasons.append("PAYLOAD_LENGTH_MISMATCH")
            if _payload_digest(payload_bytes) != payload_digest:
                reasons.append("PAYLOAD_DIGEST_MISMATCH")
            document = _strict_payload_document(payload_bytes)
            if document is None:
                reasons.append("PAYLOAD_SCHEMA_INVALID")
            else:
                if document.get("schema") != self.contract.request_format_version:
                    reasons.append("PAYLOAD_FORMAT_MISMATCH")
                if document.get("call_id") != computed_call_id:
                    reasons.append("PAYLOAD_CALL_MISMATCH")
                if document.get("prepared_digest") != computed_prepared:
                    reasons.append("PAYLOAD_PREPARED_DIGEST_MISMATCH")
                if document.get("route_id") != self.contract.route_id:
                    reasons.append("PAYLOAD_ROUTE_MISMATCH")
                if document.get("model") != self.contract.model_id:
                    reasons.append("PAYLOAD_MODEL_MISMATCH")
        # Budget: unknown/absent cost is never zero.
        hold: Decimal | None = None
        try:
            cost = Decimal(str(estimated_cost_usd if estimated_cost_usd is not None
                               else request.estimated_cost_usd))
        except (InvalidOperation, ValueError):
            cost = None
            reasons.append("COST_UNKNOWN")
        if cost is not None:
            if not cost.is_finite() or cost <= 0:
                cost = None
                reasons.append("COST_UNKNOWN")
            else:
                if cost > self.budget.hard_call_usd:
                    reasons.append("PER_CALL_BUDGET_EXCEEDED")
                # The conservative hold is the worst case this send may commit,
                # never just the declared estimate (P2-5).
                hold = self._hold_bound(cost, worst_case_usd)
                if hold is None:
                    reasons.append(COST_BOUND_INVALID)
        with self._cost_lock:
            # The check and the hold are one atomic step: concurrent authorizes
            # can neither double-hold nor oversell the hard total.
            if (hold is not None
                    and self._known_usd + self._held_usd + hold
                    > self.budget.hard_total_usd):
                reasons.append("HARD_BUDGET_CEILING_EXCEEDED")
            if len(self._issued) >= self.limit:
                reasons.append("SEND_AUTHORIZATION_LIMIT_REACHED")
            existing_view = self._cost_views.get(reservation_id)
            if existing_view is not None and existing_view.state != COST_VIEW_HELD:
                reasons.append(RESERVATION_ALREADY_SETTLED)
            reasons.extend(self.pre_dispatch_binding_reasons())
            if reasons:
                raise self._deny(reasons, call_id=computed_call_id,
                                 reservation_id=reservation_id)
            moment = self._now()
            issued = _utc_text(moment)
            expires = _utc_text(moment + timedelta(seconds=self.ttl_seconds))
            material = {
                "nonce": os.urandom(8).hex(),
                "schema": G4C_SEND_AUTHORIZATION_SCHEMA,
                "scope_id": prepared.scope_id, "run_id": prepared.run_id,
                "call_id": computed_call_id, "prepared_digest": computed_prepared,
                "payload_digest": payload_digest, "payload_length": len(payload_bytes),
                "attempt_ordinal": request.attempt_ordinal,
                "reservation_id": reservation_id,
                "broker_claim_id": broker_claim_id,
                "broker_claim_digest": broker_claim_digest,
                "auth_epoch": self.auth_epoch, "issued_utc": issued,
            }
            authorization = TrustedSendAuthorization(
                authorization_id="send-" + hashlib.sha256(
                    canonical_json(material).encode("utf-8")).hexdigest()[:32],
                scope_id=prepared.scope_id, run_id=prepared.run_id,
                call_id=computed_call_id, prepared_digest=computed_prepared,
                payload_digest=payload_digest, payload_length=len(payload_bytes),
                attempt_ordinal=request.attempt_ordinal,
                reservation_id=reservation_id, broker_claim_id=broker_claim_id,
                broker_claim_digest=broker_claim_digest,
                route_id=self.contract.route_id, model_id=self.contract.model_id,
                auth_epoch=self.auth_epoch, issued_utc=issued, expires_utc=expires,
                route_kind=self.contract.route_kind, synthetic=True)
            # Journal first: a configured audit journal that cannot be written is
            # a hard failure, never a silent unlogged send authorization.
            self._journal({"decision": "AUTHORIZED",
                           "utc": issued,
                           **authorization.to_audit_dict()})
            self._issued[id(authorization)] = authorization
            self._sends += 1
            if hold is not None:
                self._hold_reservation_locked(
                    reservation_id=reservation_id, call_id=computed_call_id,
                    attempt_ordinal=request.attempt_ordinal, hold_usd=hold,
                    source=("broker_reserved_cost" if worst_case_usd is not None
                            else "gate_budget_bound"))
            if cost is not None:
                if cost > self.budget.soft_call_usd:
                    self._soft_events.append({"kind": "soft_call", "cost_usd": str(cost),
                                              "call_id": computed_call_id})
                if self._known_usd + self._held_usd > self.budget.soft_total_usd:
                    self._soft_events.append({"kind": "soft_total",
                                              "cost_usd": str(cost),
                                              "call_id": computed_call_id})
            return authorization

    def consume(self, authorization: object, *,
                payload_bytes: object = None,
                request: EgressRequest | None = None) -> str | None:
        """Consume exactly one process-minted capability; None means accepted."""
        if not isinstance(authorization, TrustedSendAuthorization):
            self._record_consume(None, "AUTHORIZATION_UNKNOWN")
            return "AUTHORIZATION_UNKNOWN"
        registered = self._issued.get(id(authorization))
        if registered is not authorization:
            if authorization.authorization_id in self._consumed:
                self._record_consume(authorization, "AUTHORIZATION_REPLAYED")
                return "AUTHORIZATION_REPLAYED"
            self._record_consume(authorization, "AUTHORIZATION_UNKNOWN")
            return "AUTHORIZATION_UNKNOWN"
        if self._now() >= datetime.strptime(
                authorization.expires_utc, "%Y-%m-%dT%H:%M:%SZ").replace(
                    tzinfo=timezone.utc):
            del self._issued[id(authorization)]
            self._consumed.add(authorization.authorization_id)
            self._record_consume(authorization, "AUTHORIZATION_EXPIRED")
            return "AUTHORIZATION_EXPIRED"
        if authorization.auth_epoch != self.auth_epoch:
            self._record_consume(authorization, "AUTH_EPOCH_MISMATCH")
            return "AUTH_EPOCH_MISMATCH"
        # G4-F5: the last point at which a send can still be refused. A
        # revocation observed here burns the capability so a later un-revoke
        # can never resurrect it.
        revocation = self.revocation_check("pre_send")
        if revocation.get("reason"):
            del self._issued[id(authorization)]
            self._consumed.add(authorization.authorization_id)
            self._record_consume(authorization, str(revocation["reason"]))
            return str(revocation["reason"])
        if not isinstance(payload_bytes, bytes):
            self._record_consume(authorization, "PAYLOAD_BYTES_INVALID")
            return "PAYLOAD_BYTES_INVALID"
        if len(payload_bytes) != authorization.payload_length:
            self._record_consume(authorization, "PAYLOAD_LENGTH_MISMATCH")
            return "PAYLOAD_LENGTH_MISMATCH"
        if _payload_digest(payload_bytes) != authorization.payload_digest:
            self._record_consume(authorization, "PAYLOAD_DIGEST_MISMATCH")
            return "PAYLOAD_DIGEST_MISMATCH"
        if request is not None:
            if (request.call_id != authorization.call_id
                    or request.reservation_id != authorization.reservation_id
                    or request.attempt_ordinal != authorization.attempt_ordinal):
                self._record_consume(authorization, "REQUEST_BINDING_MISMATCH")
                return "REQUEST_BINDING_MISMATCH"
        del self._issued[id(authorization)]
        self._consumed.add(authorization.authorization_id)
        self._record_consume(authorization, "CONSUMED")
        return None

    def _record_consume(self, authorization: TrustedSendAuthorization | None,
                        decision: str) -> None:
        record: dict[str, object] = {
            "decision": decision, "utc": _utc_text(self._now()),
            "authorization_id": (authorization.authorization_id
                                 if authorization is not None else None),
        }
        if decision != "CONSUMED":
            self._denials.append(record)
        if authorization is not None:
            with self._cost_lock:
                view = self._cost_views.get(authorization.reservation_id)
                if view is not None and view.state == COST_VIEW_HELD:
                    if decision == "CONSUMED":
                        view.held_source = "consume"
                        view.transitions += 1
                    self._cost_event(
                        "CONSUME" if decision == "CONSUMED"
                        else f"CONSUME_{decision}",
                        reservation_id=authorization.reservation_id,
                        authorization_id=authorization.authorization_id,
                        decision=decision,
                        held_usd=format(view.held_usd, "f"))
        try:
            self._journal(record)
        except EgressViolation:
            pass

    def snapshot(self) -> dict[str, object]:
        with self._cost_lock:
            cost_view = self._cost_mapping_locked()
            known = format(self._known_usd, "f")
            held = format(self._held_usd, "f")
        with self._revocation_lock:
            revocation = {
                "configured": self.revocation_path is not None,
                "authorization_id": self.authorization_id,
                "path": self.revocation_path,
                "last": dict(self._revocation_last)
                        if self._revocation_last is not None else None,
                "checks": [dict(entry) for entry in self._revocation_checks],
            }
        return {
            "schema": "m0.g4c.send-gate.v1",
            "route_contract": self.contract.to_mapping(),
            "contract_problems": list(self.send_problems),
            "auth_epoch": self.auth_epoch,
            "binding_checkpoint": self.binding_checkpoint,
            "binding_check_configured": (self.binding_approved is not None
                                         and self.binding_observer is not None),
            "issued": len(self._issued),
            "consumed": len(self._consumed),
            "sends_authorized": self._sends,
            # G4-F3 semantics: known = Broker-confirmed terminal cost only;
            # held = conservative view of reservations the Broker has not
            # terminally confirmed. This is a view, not the billing authority.
            "known_cost_usd": known,
            "worst_case_held_usd": held,
            "cost_authority": COST_AUTHORITY_BROKER,
            "cost_view": cost_view,
            "revocation": revocation,
            "soft_events": list(self._soft_events),
            "denials": list(self._denials),
        }


def _strict_payload_document(payload_bytes: bytes) -> dict[str, object] | None:
    """Parse the trusted wire payload; duplicate keys/NaN are invalid."""
    def reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
        seen: dict[str, object] = {}
        for key, value in pairs:
            if key in seen:
                raise ValueError(f"duplicate key: {key}")
            seen[key] = value
        return seen

    try:
        document = json.loads(
            payload_bytes.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ValueError(f"invalid {token}")))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return None
    return document if isinstance(document, dict) else None
