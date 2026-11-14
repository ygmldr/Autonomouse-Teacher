"""Normalized provider observation and usage mapping (no SDK types leaked).

PR4b accounting-side contract:

* ``ProviderObservation`` is a strict, plain-Python normalized record of one
  external provider call. Missing fields stay ``None`` and are never filled with
  zero. Unknown keys/schema are rejected.
* ``CallIdentity`` derives a stable, bounded ``call_id`` from trusted identity
  fields so an egress/HTTP attempt can be correlated with a broker reservation.
* ``deliver_observation`` durably maps one ``call_id`` to its reservation and
  settles it: AUTHORITATIVE -> SETTLED, PARTIAL/MISSING -> WORST_CASE_HELD,
  UNKNOWN -> SETTLEMENT_UNCERTAIN (reservation stays PENDING). Delivery is
  idempotent per ``call_id``; a different observation for the same call_id is a
  conflict.

This module does NOT read credentials, does not perform network I/O and does not
claim that any real provider wire format was verified. Real HTTP/usage evidence
remains UNVERIFIED/BLOCKED until a genuine authorized Live run exists.
"""
from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
import re

from .broker_usage import MAX_COUNTER
from .pricing import money
from .usage import Usage

OBSERVATION_KEYS = frozenset({
    "requested_route", "observed_route", "model_reported", "provider_request_id",
    "usage_raw_hash", "input", "cache_read", "cache_write", "output", "reasoning",
    "cost_estimate", "cost_source", "error_kind", "complete_or_uncertain",
})
COST_SOURCES = frozenset({"provider_invoice", "synthetic_fixture_cost", "local_estimate", "unknown"})
ERROR_KINDS = frozenset({"none", "timeout", "http_4xx", "http_5xx", "transport", "sdk_error", "unknown"})
COMPLETENESS = frozenset({"AUTHORITATIVE", "PARTIAL", "MISSING", "UNKNOWN"})
COUNTER_FIELDS = ("input", "cache_read", "cache_write", "output", "reasoning")
_HASH = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_CALL_ID = re.compile(r"call-[0-9a-f]{48}\Z", re.ASCII)
_REQUEST_DIGEST = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_DECIMAL = re.compile(r"(?:0|[1-9][0-9]{0,11})(?:\.[0-9]{1,9})?\Z", re.ASCII)


class ObservationSchemaError(ValueError):
    """Rejected observation/call-identity schema; message never embeds raw payload."""


def _bounded_text(value: object, field: str, maximum: int) -> str:
    if (not isinstance(value, str) or not 1 <= len(value) <= maximum
            or any(ord(char) < 32 for char in value)):
        raise ObservationSchemaError(f"invalid {field}")
    return value


def _optional_text(value: object, field: str, maximum: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not 1 <= len(value) <= maximum or any(ord(char) < 32 for char in value):
        raise ObservationSchemaError(f"invalid {field}")
    return value


def _optional_counter(value: object, field: str) -> int | None:
    if value is None:
        return None
    if type(value) is not int or value < 0 or value > MAX_COUNTER:
        raise ObservationSchemaError(f"invalid {field}")
    return value


def _optional_hash(value: object, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not _HASH.fullmatch(value):
        raise ObservationSchemaError(f"invalid {field}")
    return value


def _optional_cost(value: object) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        parsed = value
    elif isinstance(value, str) and _DECIMAL.fullmatch(value):
        parsed = Decimal(value)
    else:
        raise ObservationSchemaError("invalid cost_estimate")
    if parsed < 0 or parsed > MAX_COUNTER:
        raise ObservationSchemaError("invalid cost_estimate")
    return money(parsed)


@dataclass(frozen=True)
class ProviderObservation:
    requested_route: str
    observed_route: str | None = None
    model_reported: str | None = None
    provider_request_id: str | None = None
    usage_raw_hash: str | None = None
    input: int | None = None
    cache_read: int | None = None
    cache_write: int | None = None
    output: int | None = None
    reasoning: int | None = None
    cost_estimate: Decimal | None = None
    cost_source: str = "unknown"
    error_kind: str = "unknown"
    complete_or_uncertain: str = "UNKNOWN"

    def __post_init__(self) -> None:
        object.__setattr__(self, "requested_route",
                           _bounded_text(self.requested_route, "requested_route", 128))
        object.__setattr__(self, "observed_route", _optional_text(self.observed_route, "observed_route", 128))
        object.__setattr__(self, "model_reported", _optional_text(self.model_reported, "model_reported", 256))
        object.__setattr__(self, "provider_request_id", _optional_text(self.provider_request_id, "provider_request_id", 256))
        object.__setattr__(self, "usage_raw_hash", _optional_hash(self.usage_raw_hash, "usage_raw_hash"))
        for field in COUNTER_FIELDS:
            object.__setattr__(self, field, _optional_counter(getattr(self, field), field))
        object.__setattr__(self, "cost_estimate", _optional_cost(self.cost_estimate))
        if self.cost_source not in COST_SOURCES:
            raise ObservationSchemaError("invalid cost_source")
        if self.error_kind not in ERROR_KINDS:
            raise ObservationSchemaError("invalid error_kind")
        if self.complete_or_uncertain not in COMPLETENESS:
            raise ObservationSchemaError("invalid complete_or_uncertain")
        self._validate_completeness()

    def _validate_completeness(self) -> None:
        status = self.complete_or_uncertain
        counters = {field: getattr(self, field) for field in COUNTER_FIELDS}
        present = [field for field, value in counters.items() if value is not None]
        if status == "AUTHORITATIVE":
            if self.error_kind != "none":
                raise ObservationSchemaError("authoritative observation cannot carry an error")
            if self.usage_raw_hash is None:
                raise ObservationSchemaError("authoritative observation requires usage_raw_hash")
            for field in ("input", "cache_read", "cache_write", "output"):
                if getattr(self, field) is None:
                    raise ObservationSchemaError(f"authoritative observation requires {field}")
            if self.reasoning is not None and self.reasoning > self.output:
                raise ObservationSchemaError("reasoning subset exceeds inclusive output")
        elif status == "PARTIAL":
            if not 0 < len(present) < len(COUNTER_FIELDS):
                raise ObservationSchemaError("partial observation requires some but not all counters")
            if self.usage_raw_hash is None:
                raise ObservationSchemaError("partial observation requires usage_raw_hash")
        elif status == "MISSING":
            if present:
                raise ObservationSchemaError("missing observation must not claim counters")
        elif status == "UNKNOWN":
            if present:
                raise ObservationSchemaError("unknown observation must not claim counters")
            if self.cost_source != "unknown" or self.cost_estimate is not None:
                raise ObservationSchemaError("unknown observation must not claim cost")

    def to_mapping(self) -> dict:
        return {
            "requested_route": self.requested_route,
            "observed_route": self.observed_route,
            "model_reported": self.model_reported,
            "provider_request_id": self.provider_request_id,
            "usage_raw_hash": self.usage_raw_hash,
            "input": self.input,
            "cache_read": self.cache_read,
            "cache_write": self.cache_write,
            "output": self.output,
            "reasoning": self.reasoning,
            "cost_estimate": None if self.cost_estimate is None else format(self.cost_estimate, "f"),
            "cost_source": self.cost_source,
            "error_kind": self.error_kind,
            "complete_or_uncertain": self.complete_or_uncertain,
        }

    @classmethod
    def from_mapping(cls, payload: object) -> "ProviderObservation":
        if not isinstance(payload, dict):
            raise ObservationSchemaError("observation must be an object")
        keys = set(payload)
        if keys - OBSERVATION_KEYS or OBSERVATION_KEYS - keys:
            raise ObservationSchemaError("unknown or missing observation schema")
        return cls(
            requested_route=_bounded_text(payload["requested_route"], "requested_route", 128),
            observed_route=_optional_text(payload["observed_route"], "observed_route", 128),
            model_reported=_optional_text(payload["model_reported"], "model_reported", 256),
            provider_request_id=_optional_text(payload["provider_request_id"], "provider_request_id", 256),
            usage_raw_hash=_optional_hash(payload["usage_raw_hash"], "usage_raw_hash"),
            input=_optional_counter(payload["input"], "input"),
            cache_read=_optional_counter(payload["cache_read"], "cache_read"),
            cache_write=_optional_counter(payload["cache_write"], "cache_write"),
            output=_optional_counter(payload["output"], "output"),
            reasoning=_optional_counter(payload["reasoning"], "reasoning"),
            cost_estimate=_optional_cost(payload["cost_estimate"]),
            cost_source=payload["cost_source"],
            error_kind=payload["error_kind"],
            complete_or_uncertain=payload["complete_or_uncertain"],
        )

    def accounting_status(self) -> str:
        """Map observation completeness to the PR1 accounting status vocabulary."""
        if self.complete_or_uncertain == "AUTHORITATIVE":
            return "SETTLED"
        if self.complete_or_uncertain in {"PARTIAL", "MISSING"}:
            return "WORST_CASE_HELD"
        return "SETTLEMENT_UNCERTAIN"

    def to_usage(self, *, reserved_input: int, reserved_output: int, known_fee: object = 0,
                 reasoning_in_output: bool = True) -> Usage:
        """Map to ledger Usage without ever substituting zero for missing usage.

        ``reasoning_in_output`` must come from the verified route billing policy;
        the caller supplies it explicitly instead of guessing.
        """
        if type(reserved_input) is not int or reserved_input <= 0:
            raise ValueError("positive reserved input bound required")
        if type(reserved_output) is not int or reserved_output <= 0:
            raise ValueError("positive reserved output bound required")
        fee = money(known_fee)
        status = self.complete_or_uncertain
        if status == "AUTHORITATIVE":
            total_input = (self.input or 0) + (self.cache_read or 0) + (self.cache_write or 0)
            total_output = self.output or 0
            if not reasoning_in_output:
                total_output += self.reasoning or 0
            actual = self.cost_estimate if self.cost_source == "provider_invoice" else None
            return Usage(total_input, total_output, self.cache_read or 0, False, actual, fee)
        if status in {"PARTIAL", "MISSING"}:
            input_parts = (self.input, self.cache_read, self.cache_write)
            known_input = sum(part for part in input_parts if part is not None)
            complete_input = all(part is not None for part in input_parts)
            total_input = known_input if complete_input else max(reserved_input, known_input)
            cache_read = self.cache_read if complete_input else 0
            complete_output = self.output is not None and (reasoning_in_output or self.reasoning is not None)
            known_output = (self.output or 0) + (0 if reasoning_in_output else (self.reasoning or 0))
            total_output = known_output if complete_output else max(reserved_output, known_output)
            actual = self.cost_estimate if self.cost_source == "provider_invoice" else None
            return Usage(total_input, total_output, cache_read, True, actual, fee)
        # UNKNOWN: no trustworthy counters exist; hold the full reserved bounds.
        return Usage(reserved_input, reserved_output, 0, True, None, fee)


def observation_digest(observation: ProviderObservation) -> str:
    material = json.dumps(observation.to_mapping(), sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CallIdentity:
    """Trusted identity of one external logical call/attempt; no SDK dependence."""
    run_id: str
    logical_step: int
    attempt_index: int
    request_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _bounded_text(self.run_id, "run_id", 128))
        if type(self.logical_step) is not int or not 0 <= self.logical_step <= MAX_COUNTER:
            raise ObservationSchemaError("invalid logical_step")
        if type(self.attempt_index) is not int or not 0 <= self.attempt_index <= MAX_COUNTER:
            raise ObservationSchemaError("invalid attempt_index")
        if not isinstance(self.request_digest, str) or not _REQUEST_DIGEST.fullmatch(self.request_digest):
            raise ObservationSchemaError("invalid request_digest")

    def canonical(self) -> dict:
        return {"v": 1, "run_id": self.run_id, "logical_step": self.logical_step,
                "attempt_index": self.attempt_index, "request_digest": self.request_digest}

    @property
    def call_id(self) -> str:
        material = json.dumps(self.canonical(), sort_keys=True, separators=(",", ":"), allow_nan=False)
        return "call-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:48]


def derive_call_id(run_id: str, logical_step: int, attempt_index: int, request_digest: str) -> str:
    """Stable, bounded call id: same identity -> same id; different attempt -> different id."""
    return CallIdentity(run_id, logical_step, attempt_index, request_digest).call_id


def deliver_observation(ledger, call_id: str, observation: ProviderObservation | dict,
                        *, reasoning_in_output: bool = True) -> dict:
    """Durably link one observation to its reservation and settle it once.

    The caller must bind the call to a reservation first (``ledger.bind_call``),
    which the broker does when a reserve message carries an optional ``call_id``.
    Repeated delivery for the same call_id+payload is idempotent; a different
    payload for the same call_id is a conflict. UNKNOWN keeps the reservation
    PENDING (SETTLEMENT_UNCERTAIN) rather than refunding or guessing.
    """
    if not isinstance(call_id, str) or not _CALL_ID.fullmatch(call_id):
        raise ObservationSchemaError("invalid call_id")
    if not isinstance(observation, ProviderObservation):
        observation = ProviderObservation.from_mapping(observation)
    digest = observation_digest(observation)

    def operation(database):
        link = database.execute("SELECT reservation_id FROM budget_call_links WHERE scope_id=? AND call_id=?",
                                (ledger.scope_id, call_id)).fetchone()
        if link is None:
            return {"ok": False, "code": "UNKNOWN_CALL", "call_id": call_id,
                    "accounting_status": "SETTLEMENT_UNCERTAIN", "reservation_pending": True}
        reservation_id = link[0]
        row = database.execute("SELECT * FROM budget_reservations WHERE scope_id=? AND reservation_id=?",
                               (ledger.scope_id, reservation_id)).fetchone()
        if row is None:
            return {"ok": False, "code": "UNKNOWN_RESERVATION", "call_id": call_id,
                    "accounting_status": "SETTLEMENT_UNCERTAIN", "reservation_pending": True}
        status = observation.accounting_status()
        if row["status"] != "PENDING":
            existing = "SETTLED" if row["status"] == "OK" else "WORST_CASE_HELD"
            return {"ok": True, "code": "ALREADY_SETTLED", "call_id": call_id,
                    "reservation_id": reservation_id, "accounting_status": existing}
        if status == "SETTLEMENT_UNCERTAIN":
            return {"ok": False, "code": "SETTLEMENT_UNCERTAIN", "call_id": call_id,
                    "reservation_id": reservation_id, "accounting_status": status,
                    "reservation_pending": True, "observation_digest": digest}
        usage = observation.to_usage(reserved_input=row["input_bound"], reserved_output=row["output_bound"],
                                     known_fee=Decimal(row["known_fee"]), reasoning_in_output=reasoning_in_output)
        settlement = ledger.settle(reservation_id, usage, status="OK" if status == "SETTLED" else "FAILED")
        return {"ok": True, "code": status, "call_id": call_id, "reservation_id": reservation_id,
                "accounting_status": status, "settlement": settlement, "observation_digest": digest}

    response, duplicate = ledger.observation_once(call_id, digest, operation)
    response["duplicate"] = duplicate
    return response
