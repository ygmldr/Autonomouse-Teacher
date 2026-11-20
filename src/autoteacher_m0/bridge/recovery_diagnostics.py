"""G4-R P2-06 append-only recovery diagnostics (no Key, no network).

G4-F F5-R5 recorded a real defect: ``reconcile_on_startup`` classified a
post-Reserve attempt as ``SETTLEMENT_UNCERTAIN`` because its Receipt document
was missing/invalid, and that single ``reason`` column overwrote the stable
first cause written by the live request path (for example
``REVOKED_PRE_SEND:RUN_AUTHORIZATION_REVOKED``).  Two different facts were
competing for one field:

* **first_cause** - why the attempt became conservative while the process was
  alive (revocation, pre-send abort, deadline, ...);
* **reconciliation_observation** - what the *latest restart verification* saw
  (missing receipt, schema-invalid receipt document, Broker status, ...).

This module keeps both facts without touching the frozen Attempt DB schema:

* the existing ``reason`` column keeps the proven first cause **only** when the
  old value belongs to the explicitly proven revocation enumeration *and* the
  Broker is still ``PENDING`` (so the outcome is not yet terminal and the first
  cause still explains why it is held);
* a separate append-only JSONL diagnostic always records the recovery
  observation, the Broker answer and the action taken.

It is diagnostics only: no Broker/fee/state-machine authority is moved here.
Broker ``OK``/``FAILED`` stays authoritative; this module never sends, settles,
fails or releases anything.  A write failure increments counters and surfaces an
``observability_gap`` indicator but never changes the recovery decision.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

RECOVERY_DIAGNOSTIC_SCHEMA = "m0.g4r.recovery-diagnostic.v1"
DEFAULT_RECOVERY_FILENAME = "recovery-diagnostics.jsonl"
MAX_DIAGNOSTIC_NAME = 128

# Only these already-proven first-cause enumerations may be preserved as the
# primary reason.  This is deliberately a closed set: a future/unknown reason
# must never be silently frozen (that could hide a new severe state).
PRESERVABLE_PRIMARY_CAUSES = frozenset({"RUN_AUTHORIZATION_REVOKED"})
PRESERVABLE_PRIMARY_CAUSE_PREFIXES = ("REVOKED_PRE_SEND:",)

ACTION_MARK_SETTLED = "MARK_SETTLED"
ACTION_MARK_WORST_CASE = "MARK_WORST_CASE"
ACTION_MARK_UNCERTAIN = "MARK_SETTLEMENT_UNCERTAIN"
ACTION_SKIP = "SKIP_ALREADY_TERMINAL"


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sanitize_name(value: object, *, maximum: int = MAX_DIAGNOSTIC_NAME) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    cleaned = "".join(
        char if ord(char) >= 0x20 and ord(char) != 0x7F else "?" for char in value)
    return cleaned[:maximum] or None


def is_preservable_primary_cause(reason: object) -> bool:
    """True only for the proven revocation first-cause enumeration."""
    if not isinstance(reason, str) or not reason:
        return False
    if reason in PRESERVABLE_PRIMARY_CAUSES:
        return True
    return any(reason.startswith(prefix) for prefix in PRESERVABLE_PRIMARY_CAUSE_PREFIXES)


def primary_cause_view(reason: object) -> str:
    """Classify the prior reason without copying arbitrary text into new fields."""
    if not isinstance(reason, str) or not reason:
        return "NONE"
    if reason in PRESERVABLE_PRIMARY_CAUSES:
        return "RUN_AUTHORIZATION_REVOKED"
    if reason.startswith(PRESERVABLE_PRIMARY_CAUSE_PREFIXES):
        return "REVOKED_PRE_SEND"
    # The raw prior reason is kept separately (bounded) only when it is the
    # proven enum; unknown values are described by class, not echoed blindly.
    return "OTHER"


def build_record(*, attempt_id: object, reservation_id: object, call_id: object,
                 prior_state: object, prior_reason: object, observation: object,
                 broker_status: object, broker_authoritative: bool,
                 action: str, primary_cause_preserved: bool,
                 receipt_verified: bool) -> dict:
    """Build one bounded recovery-diagnostic row (no secrets, no prompts)."""
    return {
        "schema": RECOVERY_DIAGNOSTIC_SCHEMA,
        "utc": utc_now(),
        "attempt_id": sanitize_name(attempt_id),
        "reservation_id": sanitize_name(reservation_id),
        "call_id": sanitize_name(call_id),
        "prior_state": sanitize_name(prior_state),
        "prior_reason_class": primary_cause_view(prior_reason),
        # Raw prior reason is evidence for the proven revocation enum only; the
        # field is a stable trusted reason, never candidate content.
        "primary_cause": (sanitize_name(prior_reason, maximum=200)
                          if is_preservable_primary_cause(prior_reason) else None),
        "primary_cause_preserved": bool(primary_cause_preserved),
        "reconciliation_observation": sanitize_name(observation),
        "broker_status": sanitize_name(broker_status),
        "broker_authoritative": bool(broker_authoritative),
        "receipt_verified": bool(receipt_verified),
        "action": action,
        "reserved": False,
        "observability_gap": False,
    }


class RecoveryDiagnostics:
    """Append-only JSONL writer for recovery observations (best effort)."""

    def __init__(self, path: str | os.PathLike[str] | None = None) -> None:
        self.path = Path(path) if path is not None else None
        if self.path is not None and not self.path.is_absolute():
            raise ValueError("recovery diagnostic journal path must be absolute")
        self._lock = threading.Lock()
        self.written = 0
        self.errors = 0
        self.last_error: str | None = None

    @property
    def enabled(self) -> bool:
        return self.path is not None

    def append(self, record: Mapping[str, object]) -> bool:
        if self.path is None:
            return False
        try:
            data = (json.dumps(record, sort_keys=True, separators=(",", ":"),
                               ensure_ascii=True, allow_nan=False) + "\n").encode("utf-8")
        except (TypeError, ValueError) as exc:
            with self._lock:
                self.errors += 1
                self.last_error = type(exc).__name__
            return False
        flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            fd = os.open(self.path, flags, 0o600)
        except OSError as exc:
            with self._lock:
                self.errors += 1
                self.last_error = type(exc).__name__
            return False
        try:
            written = 0
            while written < len(data):
                count = os.write(fd, data[written:])
                if count <= 0:
                    raise OSError("zero progress")
                written += count
            os.fsync(fd)
        except OSError as exc:
            with self._lock:
                self.errors += 1
                self.last_error = type(exc).__name__
            return False
        finally:
            os.close(fd)
        with self._lock:
            self.written += 1
        return True

    def gap_indicator(self) -> dict:
        with self._lock:
            errors = self.errors
            written = self.written
            last_error = self.last_error
        return {
            "schema": RECOVERY_DIAGNOSTIC_SCHEMA,
            "journal": "recovery-diagnostics",
            "enabled": self.enabled,
            "written": written,
            "write_errors": errors,
            "last_error": last_error,
            "observability_gap": bool(errors),
        }


def default_recovery_path(attempt_db: str | os.PathLike[str]) -> Path:
    """Recovery journal lives beside the trusted Attempt DB (same state dir)."""
    return Path(attempt_db).with_name(DEFAULT_RECOVERY_FILENAME)
