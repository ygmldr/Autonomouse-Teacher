"""Structured error types for the frozen M1-A teacher contract ``m1a.v0``.

Every public failure mode of the teacher core is expressed with an
:class:`M1AError` subclass carrying a stable, machine-readable ``code``
attribute.  Callers (later PRs, the CLI and the review tooling) can branch on
``exc.code`` without parsing human-readable messages.

The codes are part of the frozen contract: append new codes, never rename or
remove them.
"""

from __future__ import annotations

from typing import Any, Mapping

__all__ = [
    "M1AError",
    "ValidationError",
    "NotFoundError",
    "ConflictError",
    "UnsupportedOperationError",
    "IDEMPOTENCY_CONFLICT",
    "INVALID_RESULT_ID",
    "IDEMPOTENCY_UNSUPPORTED",
]

# ---------------------------------------------------------------------------
# B-NEXT (B-PR3) additive error codes for scoped idempotency.
#
# These are *codes* (strings passed via ``M1AError(code=...)``), not new
# exception classes: callers keep catching ``ConflictError`` /
# ``ValidationError`` / ``UnsupportedOperationError`` exactly as before, and
# the frozen class-level defaults are unchanged.  Codes are append-only.
# ---------------------------------------------------------------------------

#: ``ConflictError.code``: the same scoped idempotency key was reused with a
#: different request/scope, or a result_id already belongs to another scope.
#: ``details`` only ever contains the *requesting* scope and a stable reason
#: (never another learner's/session's data).
IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"

#: ``ValidationError.code``: a caller-supplied ``result_id`` is not a safe,
#: well-formed idempotency token (empty, too long, path/control characters).
INVALID_RESULT_ID = "INVALID_RESULT_ID"

#: ``UnsupportedOperationError.code``: the repository has no scoped-idempotency
#: extension, so a safe idempotent replay cannot be verified (fail closed
#: instead of falling back to a global lookup).
IDEMPOTENCY_UNSUPPORTED = "IDEMPOTENCY_UNSUPPORTED"


class M1AError(Exception):
    """Base class for all M1-A contract errors.

    Parameters
    ----------
    message:
        Human-readable description. Kept short and deterministic; it must not
        contain secrets, fixture answer material or environment-specific paths
        that would make failure reports non-reproducible.
    code:
        Optional override of the class-level :attr:`code` (defaults to
        ``"M1A_ERROR"`` / the subclass default).
    details:
        Optional structured payload (JSON-serialisable values only).
    """

    code = "M1A_ERROR"

    def __init__(
        self,
        message: str = "",
        *,
        code: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        if type(message) is not str:
            raise TypeError("M1AError message must be a string")
        if code is not None:
            if type(code) is not str or not code:
                raise TypeError("M1AError code override must be a non-empty string")
            # Instance attribute shadowing the class default; keeps
            # ``ValidationError.code`` intact for callers that inspect the class.
            self.code = code
        self.message = message
        self.details = dict(details or {})
        super().__init__(message or self.code)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation of the error."""

        return {
            "code": self.code,
            "message": self.message,
            "details": dict(self.details),
        }


class ValidationError(M1AError):
    """Input/contract validation failed (fail-closed).

    Raised for unknown fields, wrong ``schema_version``, invalid enum values,
    out-of-range numbers, malformed timestamps and structurally invalid domain
    fixtures.
    """

    code = "VALIDATION_ERROR"


class NotFoundError(M1AError):
    """A requested record, domain or fixture does not exist."""

    code = "NOT_FOUND"


class ConflictError(M1AError):
    """An operation conflicts with existing state (e.g. duplicate registration)."""

    code = "CONFLICT"


class UnsupportedOperationError(M1AError):
    """The requested operation is not supported by this component/version."""

    code = "UNSUPPORTED_OPERATION"
