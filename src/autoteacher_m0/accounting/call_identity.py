"""Canonical CallIdentity (ADR-002): the only settlement-relevant call identity.

`call_id = "call-" + sha256(canonical_json({v:1, run_id, logical_step,
attempt_index, request_digest}))[:48]`

Identity fields are produced/rechecked by the trusted Controller/Bridge before a
reservation; egress may only receive and validate this value. Legacy egress
event ids (`eg-...`) are log-only fields and MUST NOT be used for broker claims,
reservations or settlement. No SDK/credential/network dependency.
"""
from dataclasses import dataclass
import hashlib
import json
import re
from typing import Mapping

from .broker_usage import MAX_COUNTER

CALL_ID_PATTERN = re.compile(r"call-[0-9a-f]{48}\Z", re.ASCII)
REQUEST_DIGEST_PATTERN = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
MAX_ID_LEN = 96


def _canonical_value(value: object) -> object:
    """Strict JSON-compatible recursion: reject NaN/Inf/non-string mapping keys."""
    if value is None or type(value) in (str, int, bool):
        return value
    if type(value) is float:
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError("non-finite float")
        return value
    if isinstance(value, Mapping):
        result = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("non-string mapping key")
            result[key] = _canonical_value(item)
        return result
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    raise TypeError(f"non-canonical JSON value: {type(value).__name__}")


def canonical_json(value: object) -> str:
    """Single canonical JSON implementation (UTF-8, sorted keys, compact, no NaN)."""
    return json.dumps(_canonical_value(value), sort_keys=True,
                      separators=(",", ":"), ensure_ascii=False, allow_nan=False)


class ObservationSchemaError(ValueError):
    """Rejected schema/identity value; message never embeds raw caller payload."""


# Backwards/identity-specific alias; same class object as ObservationSchemaError.
IdentitySchemaError = ObservationSchemaError


def _bounded_text(value: object, name: str, maximum: int = 128) -> str:
    if (not isinstance(value, str) or not 1 <= len(value) <= maximum
            or any(ord(char) < 32 for char in value)):
        raise IdentitySchemaError(f"invalid {name}")
    return value


def is_call_id(value: object) -> bool:
    return isinstance(value, str) and CALL_ID_PATTERN.fullmatch(value) is not None


def validate_call_id(value: object) -> str:
    if not is_call_id(value):
        raise IdentitySchemaError("invalid call_id")
    return value  # type: ignore[return-value]


def is_request_digest(value: object) -> bool:
    return isinstance(value, str) and REQUEST_DIGEST_PATTERN.fullmatch(value) is not None


def validate_request_digest(value: object) -> str:
    if not is_request_digest(value):
        raise IdentitySchemaError("invalid request_digest")
    return value  # type: ignore[return-value]


@dataclass(frozen=True)
class CallIdentity:
    """Trusted identity of one external logical call/attempt; no SDK dependence."""
    run_id: str
    logical_step: int
    attempt_index: int
    request_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _bounded_text(self.run_id, "run_id"))
        if type(self.logical_step) is not int or not 0 <= self.logical_step <= MAX_COUNTER:
            raise IdentitySchemaError("invalid logical_step")
        if type(self.attempt_index) is not int or not 0 <= self.attempt_index <= MAX_COUNTER:
            raise IdentitySchemaError("invalid attempt_index")
        validate_request_digest(self.request_digest)

    def canonical(self) -> dict:
        return {"v": 1, "run_id": self.run_id, "logical_step": self.logical_step,
                "attempt_index": self.attempt_index, "request_digest": self.request_digest}

    @property
    def call_id(self) -> str:
        material = canonical_json(self.canonical())
        return "call-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:48]


def derive_call_id(run_id: str, logical_step: int, attempt_index: int, request_digest: str) -> str:
    """Stable, bounded call id: same identity -> same id; any field change -> new id."""
    return CallIdentity(run_id, logical_step, attempt_index, request_digest).call_id
