"""PR4a egress boundary prototype: allowlist/deny, counters, stable attempt IDs.

This is transport-observer code, not a network proxy and NOT a Live unlock. The
fixed no-Key OCI used by this project denies socket creation entirely (evidence:
`socket()` raises PermissionError inside the locked rootfs/image), so this module
observes scripted attempt descriptors and explicitly does NOT claim to have
observed the real provider wire. Provider-internal retries, cache markers and
Files behaviour remain LIMITATION/UNVERIFIED until PR4b deploys a separately
reviewed egress proxy outside the candidate boundary.

The reservation id is supplied by the accounting/broker side (PR4b); this module
only derives a stable call id from it and NEVER writes accounting state.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
import hashlib
import re
from typing import Iterable, Mapping, Protocol

from autoteacher_m0.contracts import ErrorCode, RuntimeFailure

OPENCODE_GO_HOST = "opencode.ai"
OPENCODE_GO_PORT = 443
OPENCODE_GO_PATH_PREFIX = "/inference/go/"
MAX_ATTEMPTS_PER_STREAM = 4
MAX_OUTPUT_TOKENS = 1024
CALL_ID_RE = re.compile(r"call-[0-9a-f]{48}\Z", re.ASCII)
REQUEST_DIGEST_RE = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)


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


@dataclass
class LogicalStreamEgress:
    logical_stream_id: str
    reservation_id: str
    attempts: int = 0
    denied: int = 0
    worst_case_held_usd: Decimal = Decimal("0")
    known_cost_usd: Decimal = Decimal("0")
    state: AttemptState = AttemptState.NOT_DISPATCHED


def _legacy_egress_event_id(request: EgressRequest, route_model: tuple[str, str]) -> str:
    """Log-only PR4a event id; never a settlement/claim/broker identity."""
    material = "|".join((
        request.logical_stream_id, request.reservation_id, str(request.attempt_ordinal),
        route_model[0], route_model[1], request.host, str(request.port), request.path,
    ))
    return "eg-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


class EgressBoundary:
    """Deterministic allowlist/deny + counter + stable call-id prototype."""

    def __init__(self, policy: EgressPolicy | None = None,
                 claimer: BrokerClaimer | None = None) -> None:
        self.policy = policy or EgressPolicy()
        self.claimer = claimer
        self._streams: dict[str, LogicalStreamEgress] = {}
        self._decisions: list[dict] = []

    def _stream(self, request: EgressRequest) -> LogicalStreamEgress:
        key = request.logical_stream_id
        if key not in self._streams:
            self._streams[key] = LogicalStreamEgress(key, request.reservation_id)
        return self._streams[key]

    def _evaluate(self, request: EgressRequest) -> EgressDecision:
        """Pure policy/identity evaluation; counters are updated by callers."""
        policy = self.policy
        reasons: list[str] = []
        route_model = (request.route_id, request.model)
        if not isinstance(request.call_id, str) or not CALL_ID_RE.fullmatch(request.call_id):
            reasons.append("CALL_ID_INVALID_OR_MISSING")
        if (not isinstance(request.request_digest, str)
                or not REQUEST_DIGEST_RE.fullmatch(request.request_digest)):
            reasons.append("REQUEST_DIGEST_INVALID")
        if policy.require_reservation and not request.reservation_id.strip():
            reasons.append("NO_RESERVATION")
        if route_model not in policy.approved_routes:
            reasons.append("ROUTE_MODEL_NOT_APPROVED")
        ports = policy.host_ports.get(request.host)
        if ports is None or request.port not in ports:
            reasons.append("HOST_PORT_NOT_ALLOWED")
        if request.method.upper() not in policy.methods:
            reasons.append("METHOD_NOT_ALLOWED")
        if not request.path.startswith(policy.path_prefix):
            reasons.append("PATH_NOT_ALLOWED")
        if not isinstance(request.max_tokens, int) or request.max_tokens < 1:
            reasons.append("MAX_TOKENS_INVALID")
        elif request.max_tokens > policy.max_tokens:
            reasons.append("MAX_TOKENS_EXCEEDED")
        if request.has_files and not policy.allow_files:
            reasons.append("FILES_NOT_PERMITTED")
        if request.has_images and not policy.allow_images:
            reasons.append("IMAGES_NOT_PERMITTED")
        if request.store and not policy.allow_store:
            reasons.append("STORE_NOT_PERMITTED")
        if request.stream not in (True, False):
            reasons.append("STREAM_FLAG_INVALID")
        stream = self._stream(request)
        if request.attempt_ordinal < 1:
            reasons.append("ATTEMPT_ORDINAL_INVALID")
        elif stream.attempts + 1 > policy.max_attempts:
            reasons.append("ATTEMPT_LIMIT_EXCEEDED")
        return EgressDecision(not reasons, tuple(reasons), request.call_id,
                              _legacy_egress_event_id(request, route_model),
                              request.logical_stream_id, request.reservation_id,
                              request.attempt_ordinal, route_model)

    def _record(self, request: EgressRequest, decision: EgressDecision) -> None:
        stream = self._stream(request)
        stream.attempts += int(decision.allowed)
        stream.denied += int(not decision.allowed)
        if not decision.allowed and not request.reservation_id.strip():
            stream.state = AttemptState.BILLABLE_UNKNOWN
            stream.worst_case_held_usd += Decimal(request.estimated_cost_usd)
        self._decisions.append({
            "call_id": decision.call_id, "legacy_egress_event_id": decision.legacy_egress_event_id,
            "allowed": decision.allowed, "claim": (dict(decision.claim.claim)
            if decision.claim is not None and decision.claim.claim is not None else None),
            "reasons": list(decision.reasons), "stream": request.logical_stream_id,
            "reservation": request.reservation_id, "attempt": request.attempt_ordinal,
            "route": request.route_id, "model": request.model,
        })

    def authorize(self, request: EgressRequest) -> EgressDecision:
        decision = self._evaluate(request)
        self._record(request, decision)
        return decision

    def claim_dispatch(self, request: EgressRequest) -> EgressDecision:
        """Policy check then one persistent Broker claim; claim failure => 0 dispatch."""
        decision = self._evaluate(request)
        if not decision.allowed:
            self._record(request, decision)
            return decision
        if self.claimer is None:
            # Descriptor-only legacy path (PR4a tests); G2 integration always
            # supplies a real stdio-Broker claimer.
            self._record(request, decision)
            return decision
        claim = self.claimer.claim(request)
        if claim.claimed:
            decision = EgressDecision(decision.allowed, decision.reasons, decision.call_id,
                                      decision.legacy_egress_event_id, decision.logical_stream_id,
                                      decision.reservation_id, decision.attempt_ordinal,
                                      decision.route_model, claim=claim)
            self._record(request, decision)
            return decision
        reasons = decision.reasons + (f"CLAIM_REJECTED:{claim.code}",) + tuple(claim.reasons)
        denied = EgressDecision(False, reasons, decision.call_id, decision.legacy_egress_event_id,
                                decision.logical_stream_id, decision.reservation_id,
                                decision.attempt_ordinal, decision.route_model, claim=claim)
        self._record(request, denied)
        return denied

    def require_claim(self, request: EgressRequest) -> EgressDecision:
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
             "attempts": s.attempts, "denied": s.denied, "state": s.state.value,
             "worst_case_held_usd": format(s.worst_case_held_usd, "f"),
             "known_cost_usd": format(s.known_cost_usd, "f")}
            for s in sorted(self._streams.values(), key=lambda item: item.logical_stream_id)],
            "decisions": list(self._decisions)}

    def require(self, request: EgressRequest) -> EgressDecision:
        decision = self.authorize(request)
        if not decision.allowed:
            raise EgressViolation(decision.reasons)
        return decision


class MockEgressTransport:
    """Scripted in-process transport observer. No sockets, no HTTP, no model.

    Scenario results are explicit synthetic data used to exercise the failure
    matrix; they are not provider bills and never stand in for real wire evidence.
    """

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
        self.boundary = boundary
        self._retry_counts: dict[str, int] = {}

    def dispatch(self, request: EgressRequest, scenario: str,
                 worst_case_usd: str = "0.003933") -> dict:
        if scenario not in self.SCENARIOS:
            raise ValueError("unknown mock scenario")
        if self.boundary.claimer is not None:
            decision = self.boundary.claim_dispatch(request)
        else:
            decision = self.boundary.authorize(request)
        if not decision.allowed:
            return {"call_id": decision.call_id,
                    "legacy_egress_event_id": decision.legacy_egress_event_id,
                    "dispatched": False, "denied_reasons": list(decision.reasons),
                    "state": AttemptState.NOT_DISPATCHED.value}
        result = self.SCENARIOS[scenario]
        state = self.boundary.record_outcome(
            decision, usage=result["usage"], http_status=result["status"],
            error_kind=result["error"], worst_case_usd=worst_case_usd)
        # No automatic retry: the transport returns the single observed attempt.
        self._retry_counts[decision.logical_stream_id] = self._retry_counts.get(
            decision.logical_stream_id, 0) + int(result["error"] is not None)
        return {"call_id": decision.call_id,
                "legacy_egress_event_id": decision.legacy_egress_event_id,
                "claim": (dict(decision.claim.claim) if decision.claim is not None
                          and decision.claim.claim is not None else None),
                "dispatched": True, "scenario": scenario,
                "http_status": result["status"], "state": state.value,
                "usage_known": result["usage"] is not None,
                "worst_case_conservative": state is AttemptState.BILLABLE_UNKNOWN,
                "retry_attempted": False}


def policy_from_json(raw: Mapping[str, object]) -> EgressPolicy:
    """Strict-ish loader used only by tests/scripts; unknown fields rejected."""
    allowed = {"host_ports", "methods", "path_prefix", "approved_routes", "max_tokens",
               "max_attempts", "require_reservation", "allow_files", "allow_images",
               "allow_store"}
    if set(raw) - allowed:
        raise ValueError("unknown egress policy field")
    host_ports = {str(host): frozenset(int(port) for port in ports)
                  for host, ports in dict(raw.get("host_ports", {OPENCODE_GO_HOST: [443]})).items()}
    methods = frozenset(str(method).upper() for method in raw.get("methods", ["POST"]))
    routes = frozenset(tuple(route) for route in raw.get(
        "approved_routes", [["opencode-go", "deepseek-v4.1-flash"]]))
    return EgressPolicy(host_ports=host_ports, methods=methods,
                        path_prefix=str(raw.get("path_prefix", OPENCODE_GO_PATH_PREFIX)),
                        approved_routes=routes, max_tokens=int(raw.get("max_tokens", 1024)),
                        max_attempts=int(raw.get("max_attempts", 4)),
                        require_reservation=bool(raw.get("require_reservation", True)),
                        allow_files=bool(raw.get("allow_files", False)),
                        allow_images=bool(raw.get("allow_images", False)),
                        allow_store=bool(raw.get("allow_store", False)))
