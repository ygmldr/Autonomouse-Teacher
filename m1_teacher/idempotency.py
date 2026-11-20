"""Scoped idempotency helpers for B-NEXT (B-PR3), pure and offline.

This module is the single source of truth for the **scoped idempotency key** of
one teaching submission::

    scope = (learner_id, session_id, item_id, turn_index, result_id)
    request_digest = sha256(canonical_response(response))     # 64 lowercase hex

Design rules (see ``docs/M1_B_SCOPED_IDEMPOTENCY.md`` and
``docs/M1_B_SCOPED_IDEMPOTENCY_IMPLEMENTATION.md``):

* A result lookup always needs the **complete scope** plus the request digest;
  there is no "lookup by result_id only" helper in this module.  Repositories
  enforce the same rule (``find_result_in_scope`` never returns another
  learner's ``AssessmentResult``).
* ``result_id`` is a *scope-local* idempotency token.  New default ids are
  deterministic functions of the scope and the request digest
  (``result.v1.<32-hex>``), so a same-response retry regenerates the same id;
  caller-supplied ids are validated for a safe character set/length and must be
  reused verbatim on retry.
* ``request_digest`` is computed from the canonical response only; the session
  and turn are bound through the scope, not mixed into the digest.
* **Two JSON projections are intentionally kept** (B-PR3 review P1-1):
  ``canonical_response`` (compact separators) is the projection used by *new*
  B-PR3 writes, while ``legacy_canonical_response``/``legacy_request_digest``
  reproduce the pre-B-PR3 engine projection (``json.dumps`` with default
  ``", "``/``": "`` separators).  Legacy evidence written by the old engine only
  becomes comparable through the latter; mixing them silently would make a
  provable legacy digest look like a mismatch.
* Everything here is a pure function of its arguments; no clock, no I/O, no
  environment, no network, no hidden scoring material.

Nothing in this module reads or serialises assessment answers/expected values.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Mapping

from .contracts.errors import INVALID_RESULT_ID, ValidationError

__all__ = [
    "SCOPE_VERSION",
    "IDEMPOTENCY_POLICY_VERSION",
    "MAX_RESULT_ID_LENGTH",
    "ResultScope",
    "ScopeMetadata",
    "canonical_response",
    "request_digest",
    "legacy_canonical_response",
    "legacy_request_digest",
    "validate_result_id",
    "validate_request_digest",
    "default_result_id",
    "default_attempt_id",
    "legacy_default_result_id",
    "scope_payload",
    "scope_from_payload",
    "scope_from_event",
]

SCOPE_VERSION = "m1b.scope.v1"
"""Version tag stored in every scoped idempotency payload/row."""

IDEMPOTENCY_POLICY_VERSION = "m1b.idempotency.v1"
"""Policy version attached to structured idempotency error details."""

MAX_RESULT_ID_LENGTH = 128
"""Maximum accepted length of a caller-supplied ``result_id``."""

_RESULT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_LEGACY_DIGEST_PREFIX_RE = re.compile(r"^[0-9a-f]{16}$")
_DEFAULT_RESULT_ID_PREFIX = "result.v1."
_DEFAULT_ATTEMPT_ID_PREFIX = "attempt.v1."
_LEGACY_DEFAULT_RESULT_ID_PREFIX = "result:"

#: Stable reason codes for ``IDEMPOTENCY_CONFLICT`` error details.
CONFLICT_REASON_REQUEST_DIGEST = "REQUEST_DIGEST_MISMATCH"
CONFLICT_REASON_ITEM = "ITEM_MISMATCH"
CONFLICT_REASON_TURN = "TURN_MISMATCH"
CONFLICT_REASON_TURN_ALREADY_ASSESSED = "TURN_ALREADY_ASSESSED"
CONFLICT_REASON_RESULT_ID_SCOPE = "RESULT_ID_SCOPE_MISMATCH"
CONFLICT_REASON_LEGACY_SCOPE = "LEGACY_SCOPE_MISMATCH"
CONFLICT_REASON_LEGACY_DIGEST_UNPROVEN = "LEGACY_DIGEST_UNPROVEN"
CONFLICT_REASON_ATTEMPT = "ATTEMPT_PAYLOAD_MISMATCH"
CONFLICT_REASON_CONCURRENT = "CONCURRENT_RETRY_EXHAUSTED"


# ---------------------------------------------------------------------------
# Validation / canonicalisation
# ---------------------------------------------------------------------------


def _require_nonempty_str(value: Any, where: str) -> str:
    if type(value) is not str or not value.strip():
        raise ValidationError(f"{where}: expected a non-blank string")
    return value


def canonical_response(response: str | dict) -> str:
    """Canonical text form used by **new B-PR3 writes**.

    ``dict``/``list`` are serialised with sorted keys and compact separators
    (``json.dumps(..., separators=(",", ":"))``); anything else uses ``str()``.
    This projection differs from the pre-B-PR3 engine projection for structured
    responses, so it must never be used to verify legacy 16-hex digests -- use
    :func:`legacy_request_digest` for that.
    """

    if isinstance(response, (dict, list)):
        return json.dumps(
            response,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    return str(response)


def legacy_canonical_response(response: str | dict) -> str:
    """Pre-B-PR3 engine projection (read-only compatibility).

    The old ``session.engine._canonical_response`` used
    ``json.dumps(..., ensure_ascii=False, sort_keys=True, allow_nan=False)``
    *without* ``separators``, i.e. the default ``", "``/``": "`` spacing for
    dicts/lists (``str()`` otherwise).  Every legacy 16-hex ``response_digest``
    and every ``result:<session>:<turn>:<item>:<digest16>`` default id was
    produced with this projection.
    """

    if isinstance(response, (dict, list)):
        return json.dumps(
            response,
            ensure_ascii=False,
            sort_keys=True,
            allow_nan=False,
        )
    return str(response)


def request_digest(response: str | dict) -> str:
    """Full 64-hex ``sha256(canonical_response(response))`` (new projection)."""

    return hashlib.sha256(canonical_response(response).encode("utf-8")).hexdigest()


def legacy_request_digest(response: str | dict) -> str:
    """Full 64-hex digest under the pre-B-PR3 projection (legacy comparison)."""

    return hashlib.sha256(legacy_canonical_response(response).encode("utf-8")).hexdigest()


def validate_result_id(result_id: Any, where: str = "result_id") -> str:
    """Validate a caller-supplied ``result_id``; fail closed with ``INVALID_RESULT_ID``.

    Accepted: 1..128 chars, first char alphanumeric, remaining characters
    ``[A-Za-z0-9._:@-]``.  Rejected: empty/blank, non-str, path separators,
    whitespace, control/NUL or any other character that would make logs,
    exports or event-id concatenation ambiguous.
    """

    if type(result_id) is not str or not result_id:
        raise ValidationError(
            f"{where}: result_id must be a non-empty string",
            code=INVALID_RESULT_ID,
            details={"reason": "INVALID_RESULT_ID"},
        )
    if len(result_id) > MAX_RESULT_ID_LENGTH or not _RESULT_ID_RE.match(result_id):
        raise ValidationError(
            f"{where}: result_id is not a safe idempotency token "
            f"(allowed: 1-{MAX_RESULT_ID_LENGTH} chars, "
            "'[A-Za-z0-9][A-Za-z0-9._:@-]*')",
            code=INVALID_RESULT_ID,
            details={"reason": "INVALID_RESULT_ID"},
        )
    return result_id


def validate_request_digest(digest: Any, where: str = "request_digest") -> str:
    """Validate a full 64-lowercase-hex request digest."""

    if type(digest) is not str or not _DIGEST_RE.match(digest):
        raise ValidationError(
            f"{where}: expected a 64-character lowercase hex sha256 digest"
        )
    return digest


# ---------------------------------------------------------------------------
# Scope records
# ---------------------------------------------------------------------------


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _scope_digest(parts: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(parts).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ResultScope:
    """The frozen idempotency key of one assessment submission (v1)."""

    learner_id: str
    session_id: str
    item_id: str
    turn_index: int
    result_id: str
    request_digest: str

    def __post_init__(self) -> None:
        _require_nonempty_str(self.learner_id, "ResultScope.learner_id")
        _require_nonempty_str(self.session_id, "ResultScope.session_id")
        _require_nonempty_str(self.item_id, "ResultScope.item_id")
        if type(self.turn_index) is not int or self.turn_index < 0:
            raise ValidationError(
                f"ResultScope.turn_index: expected an int >= 0, got {self.turn_index!r}"
            )
        validate_result_id(self.result_id, "ResultScope.result_id")
        validate_request_digest(self.request_digest, "ResultScope.request_digest")

    def to_dict(self) -> dict[str, Any]:
        """JSON-serialisable payload used inside event/log payloads."""

        return {
            "scope_version": SCOPE_VERSION,
            "learner_id": self.learner_id,
            "session_id": self.session_id,
            "item_id": self.item_id,
            "turn_index": self.turn_index,
            "result_id": self.result_id,
            "request_digest": self.request_digest,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ResultScope":
        if not isinstance(data, Mapping):
            raise ValidationError("ResultScope.from_dict(): expected a mapping")
        allowed = {
            "scope_version",
            "learner_id",
            "session_id",
            "item_id",
            "turn_index",
            "result_id",
            "request_digest",
        }
        unknown = sorted(set(data) - allowed)
        if unknown:
            raise ValidationError(f"ResultScope.from_dict(): unknown field(s) {unknown}")
        version = data.get("scope_version", SCOPE_VERSION)
        if version != SCOPE_VERSION:
            raise ValidationError(
                f"ResultScope.from_dict(): unsupported scope_version {version!r}"
            )
        missing = sorted(allowed - set(data) - {"scope_version"})
        if missing:
            raise ValidationError(f"ResultScope.from_dict(): missing field(s) {missing}")
        return cls(
            learner_id=data["learner_id"],
            session_id=data["session_id"],
            item_id=data["item_id"],
            turn_index=data["turn_index"],
            result_id=data["result_id"],
            request_digest=data["request_digest"],
        )

    def digest(self) -> str:
        """Stable 32-hex digest of the complete v1 scope (audit/id helper)."""

        return _scope_digest(self.to_dict())[:32]

    def as_event_payload(self) -> dict[str, Any]:
        """Alias of :meth:`to_dict` for readability at event-building sites."""

        return self.to_dict()


@dataclass(frozen=True)
class ScopeMetadata:
    """Metadata-only projection of a ``result_scopes`` row.

    Deliberately contains **no** ``AssessmentResult`` payload: conflict decisions
    and error details can be built from metadata without ever loading another
    learner's/session's grading result.
    """

    learner_id: str
    session_id: str
    item_id: str
    turn_index: int
    result_id: str
    request_digest: str
    status: str
    attempt_id: str
    result_event_id: str | None = None
    origin: str = "v1"
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        _require_nonempty_str(self.learner_id, "ScopeMetadata.learner_id")
        _require_nonempty_str(self.session_id, "ScopeMetadata.session_id")
        _require_nonempty_str(self.item_id, "ScopeMetadata.item_id")
        if type(self.turn_index) is not int or self.turn_index < -1:
            raise ValidationError("ScopeMetadata.turn_index: expected an int >= -1")
        _require_nonempty_str(self.result_id, "ScopeMetadata.result_id")
        _require_nonempty_str(self.request_digest, "ScopeMetadata.request_digest")
        if self.status not in ("PREPARED", "TERMINAL"):
            raise ValidationError(
                f"ScopeMetadata.status: expected PREPARED|TERMINAL, got {self.status!r}"
            )
        _require_nonempty_str(self.attempt_id, "ScopeMetadata.attempt_id")
        if self.origin not in ("v1", "legacy"):
            raise ValidationError(
                f"ScopeMetadata.origin: expected v1|legacy, got {self.origin!r}"
            )


# ---------------------------------------------------------------------------
# Deterministic ids
# ---------------------------------------------------------------------------


def default_result_id(
    learner_id: str,
    session_id: str,
    item_id: str,
    turn_index: int,
    response: str | dict,
) -> str:
    """Deterministic v1 default ``result_id`` for one submission.

    Same scope + same canonical response cannot yield a different id (safe
    same-request retry); different learner/session/item/turn/digest never
    collide in practice (256-bit hash).
    """

    _require_nonempty_str(learner_id, "default_result_id(learner_id)")
    _require_nonempty_str(session_id, "default_result_id(session_id)")
    _require_nonempty_str(item_id, "default_result_id(item_id)")
    if type(turn_index) is not int or turn_index < 0:
        raise ValidationError("default_result_id(turn_index): expected an int >= 0")
    digest = _scope_digest(
        {
            "kind": "result",
            "version": SCOPE_VERSION,
            "learner_id": learner_id,
            "session_id": session_id,
            "item_id": item_id,
            "turn_index": turn_index,
            "request_digest": request_digest(response),
        }
    )
    return f"{_DEFAULT_RESULT_ID_PREFIX}{digest[:32]}"


def legacy_default_result_id(
    session_id: str, turn_index: int, item_id: str, response: str | dict
) -> str:
    """The pre-B-PR3 default id shape (read-only compatibility helper).

    Old sessions may have committed with
    ``result:<session_id>:<turn_index>:<item_id>:<16-hex-prefix>``.  New writes
    never use this shape; the engine only uses it to *find* a legacy result for
    a same-request retry after an upgrade.
    """

    digest16 = legacy_request_digest(response)[:16]
    return f"{_LEGACY_DEFAULT_RESULT_ID_PREFIX}{session_id}:{turn_index}:{item_id}:{digest16}"


def default_attempt_id(
    learner_id: str, session_id: str, item_id: str, turn_index: int
) -> str:
    """Deterministic v1 attempt id (used by new repos/helpers; engine keeps the
    historical attempt id shape for on-disk recovery compatibility)."""

    _require_nonempty_str(learner_id, "default_attempt_id(learner_id)")
    _require_nonempty_str(session_id, "default_attempt_id(session_id)")
    _require_nonempty_str(item_id, "default_attempt_id(item_id)")
    if type(turn_index) is not int or turn_index < 0:
        raise ValidationError("default_attempt_id(turn_index): expected an int >= 0")
    digest = _scope_digest(
        {
            "kind": "attempt",
            "version": SCOPE_VERSION,
            "learner_id": learner_id,
            "session_id": session_id,
            "item_id": item_id,
            "turn_index": turn_index,
        }
    )
    return f"{_DEFAULT_ATTEMPT_ID_PREFIX}{digest[:32]}"


# ---------------------------------------------------------------------------
# Scope <-> event payload helpers
# ---------------------------------------------------------------------------


def scope_payload(scope: ResultScope | None) -> dict[str, Any] | None:
    """Return the additive ``scope`` payload object (or ``None``)."""

    if scope is None:
        return None
    if not isinstance(scope, ResultScope):
        raise ValidationError("scope_payload(): expected a ResultScope or None")
    return scope.to_dict()


def scope_from_payload(payload: Mapping[str, Any]) -> ResultScope | None:
    """Extract an event payload's ``scope`` object; ``None`` for legacy payloads.

    Malformed scopes fail closed with ``ValidationError`` instead of being
    silently ignored (a corrupted scope must never be treated as legacy).
    """

    if not isinstance(payload, Mapping):
        raise ValidationError("scope_from_payload(): expected a mapping")
    raw = payload.get("scope")
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise ValidationError("scope_from_payload(): payload['scope'] must be an object")
    return ResultScope.from_dict(raw)


def scope_from_event(event: Any) -> ResultScope | None:
    """Extract the scope from a ``HistoryEvent``-like object (or ``None``)."""

    payload = getattr(event, "payload", None)
    if not isinstance(payload, Mapping):
        raise ValidationError("scope_from_event(): event has no mapping payload")
    scope = scope_from_payload(payload)
    if scope is not None and (
        scope.learner_id != getattr(event, "learner_id", scope.learner_id)
        or scope.session_id != getattr(event, "session_id", scope.session_id)
    ):
        raise ValidationError(
            "scope_from_event(): payload scope does not match the event owner/session"
        )
    return scope


def legacy_digest_prefix_matches(
    stored_digest: str, response: str | dict
) -> bool | None:
    """Compare a stored legacy digest marker with the current request.

    Returns ``True``/``False`` when the stored marker is comparable
    (``legacy:<16hex>``), or ``None`` when it is ``legacy:unproven`` (the caller
    must decide fail-closed).
    """

    if type(stored_digest) is not str:
        return None
    expected_prefix = legacy_request_digest(response)[:16]
    if stored_digest.startswith("legacy:"):
        marker = stored_digest[len("legacy:") :]
        if _LEGACY_DIGEST_PREFIX_RE.match(marker):
            return expected_prefix == marker
        return None
    # A raw 16-hex prefix is accepted for rows written by early migrations.
    if _LEGACY_DIGEST_PREFIX_RE.match(stored_digest):
        return expected_prefix == stored_digest
    return None

