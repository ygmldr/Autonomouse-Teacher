"""G4-R P2-05 request-level lifecycle observability (no Key, no network).

The G4-F2 ``dispatch-window.jsonl`` journal belongs to the *Controller dispatch
layer*: it is created when a request actually enters
``TrustedController._handle_payload_serial`` and it may only record
``reserved`` / ``dispatched`` / ``settled`` transitions of that real dispatch.
A request can be rejected or seen to time out *before* that handler exists
(malformed envelope, auxiliary purpose, a pre-start cancel, or a transport-level
deadline observed while the single-flight worker is still blocked in a
pre-Reserve window).  Those cases have no dispatch, and the frozen G4-F2
journal cannot represent them without implying a dispatch that never happened
(G4-F4 F5-R4 recorded exactly that gap).

This module is a **separate, request/transport-level** append-only journal:

* ``received``                  - one envelope was accepted by the transport;
* ``protocol_rejected``         - the payload failed the frozen protocol
  validation before any Controller dispatch existed;
* ``cancel_before_controller``  - a cancel was already pending when the
  transport started the request (no dispatch was entered);
* ``deadline_before_controller``- the transport observed the request deadline
  before the dispatch layer produced a terminal frame.  ``controller_entered``
  tells the truth about whether the worker had started, so this event never
  pretends a deadline happened before the Controller when it did not;
* ``controller_entered``        - the single-flight worker really entered the
  dispatch handler (this is the only place a real ``dispatch_seq`` may be
  referenced; pre-Controller events always carry ``dispatch_seq: null``);
* ``failed_before_reserve``     - the worker aborted before it created a
  Reservation (deadline/cancel at a pre-Reserve checkpoint, revocation,
  admission/origin rejection, ...).

The journal is *observability only*.  Every handler that writes it tolerates a
write error; a failed write increments counters and surfaces an
``observability_gap`` indicator instead of changing any allow/deny, Broker,
Fake, Authorization or settlement decision.  Fields are a bounded allowlist:
schema/version, request sequence, SHA-256 of the transport id (never the raw
id), numeric kernel-reported origin UID, sanitized purpose enum, stage/reason/
code, timestamp, ``reserved: false`` (request layer never claims a reserve),
``controller_entered`` and the real ``dispatch_seq`` when one exists.  No
prompt, message, tool argument, session text, Key or credential is written.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

REQUEST_LIFECYCLE_SCHEMA = "m0.g4r.request-lifecycle.v1"
REQUEST_LIFECYCLE_VERSION = 1
DEFAULT_LIFECYCLE_FILENAME = "request-lifecycle.jsonl"
MAX_LIFECYCLE_NAME = 128

EVENT_RECEIVED = "received"
EVENT_PROTOCOL_REJECTED = "protocol_rejected"
EVENT_CANCEL_BEFORE_CONTROLLER = "cancel_before_controller"
EVENT_DEADLINE_BEFORE_CONTROLLER = "deadline_before_controller"
EVENT_CONTROLLER_ENTERED = "controller_entered"
EVENT_FAILED_BEFORE_RESERVE = "failed_before_reserve"

REQUEST_LIFECYCLE_EVENTS = frozenset({
    EVENT_RECEIVED,
    EVENT_PROTOCOL_REJECTED,
    EVENT_CANCEL_BEFORE_CONTROLLER,
    EVENT_DEADLINE_BEFORE_CONTROLLER,
    EVENT_CONTROLLER_ENTERED,
    EVENT_FAILED_BEFORE_RESERVE,
})


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sanitize_name(value: object, *, maximum: int = MAX_LIFECYCLE_NAME) -> str | None:
    """Return a bounded printable name (identical policy to dispatch_audit)."""
    if not isinstance(value, str) or not value:
        return None
    cleaned = "".join(
        char if ord(char) >= 0x20 and ord(char) != 0x7F else "?" for char in value)
    return cleaned[:maximum] or None


def transport_id_sha256(transport_id: object) -> str | None:
    """SHA-256 of the transport id; the raw id is never written here."""
    if not isinstance(transport_id, str) or not transport_id:
        return None
    return hashlib.sha256(transport_id.encode("utf-8", "surrogatepass")).hexdigest()


def describe_purpose(payload: object) -> object:
    """Bounded enum view of ``payload.purpose`` (no message content)."""
    if not isinstance(payload, Mapping):
        return "<not_an_object>"
    if "purpose" not in payload:
        return "<missing>"
    value = payload.get("purpose")
    if value is None:
        return None
    if isinstance(value, str):
        return sanitize_name(value)
    return "<invalid:" + type(value).__name__ + ">"


class RequestLifecycleAudit:
    """Append-only JSONL writer for the request/transport observation layer.

    ``path=None`` disables writing (legacy in-process callers keep the frozen
    G3-C/G4-F behaviour byte-for-byte).  ``written``/``errors`` are the
    observability-gap counters: they are diagnostics for the trusted launcher
    and are never consulted by an admission decision.
    """

    def __init__(self, path: str | os.PathLike[str] | None = None) -> None:
        self.path = Path(path) if path is not None else None
        if self.path is not None and not self.path.is_absolute():
            raise ValueError("request lifecycle journal path must be absolute")
        self._lock = threading.Lock()
        self.written = 0
        self.errors = 0
        self.last_error: str | None = None
        self._request_seq = 0

    @property
    def enabled(self) -> bool:
        return self.path is not None

    def new_request(self, *, transport_id: object,
                    origin: Mapping[str, object] | None = None,
                    payload: object = None,
                    instance_id: str | None = None) -> dict:
        """Allocate the per-request record shared by every later lifecycle event.

        The returned mapping is a mutable *observation carrier* only; it is
        never passed to enforcement code.  ``controller_stage`` is updated by
        the single-flight worker so a transport-level deadline can report which
        pre-Reserve window was open when the deadline fired.
        """
        with self._lock:
            self._request_seq += 1
            sequence = self._request_seq
        uid = None
        kind = None
        if isinstance(origin, Mapping):
            value = origin.get("uid")
            if type(value) is int and 0 <= value <= 0xFFFFFFFE:
                uid = value
            kind = sanitize_name(origin.get("kind"))
        return {
            "request_seq": sequence,
            "transport_id_sha256": transport_id_sha256(transport_id),
            "origin_uid": uid,
            "origin_kind": kind,
            "purpose": describe_purpose(payload),
            "instance_id": instance_id,
            "controller_entered": False,
            "controller_stage": "transport",
            "dispatch_seq": None,
            "reserved": False,
        }

    def emit(self, record: Mapping[str, object], event: str, *,
             stage: str | None = None,
             code: str | None = None,
             reason: str | None = None,
             controller_entered: bool | None = None,
             dispatch_seq: int | None = None) -> bool:
        """Append one request-level event; a failure only bumps the gap counter.

        ``dispatch_seq`` is written **only** when the caller has a real dispatch
        record allocated by the dispatch layer; callers that never entered the
        Controller pass nothing and the field stays ``None``.
        """
        if event not in REQUEST_LIFECYCLE_EVENTS:
            raise ValueError("unknown request lifecycle event")
        document = {
            "schema": REQUEST_LIFECYCLE_SCHEMA,
            "version": REQUEST_LIFECYCLE_VERSION,
            "utc": utc_now(),
            "event": event,
            "stage": sanitize_name(stage) if stage is not None else None,
            "code": sanitize_name(code),
            "reason": sanitize_name(reason),
            "request_seq": record.get("request_seq"),
            "transport_id_sha256": record.get("transport_id_sha256"),
            "origin_uid": record.get("origin_uid"),
            "origin_kind": record.get("origin_kind"),
            "purpose": record.get("purpose"),
            "instance_id": sanitize_name(record.get("instance_id")),
            "reserved": False,
            "controller_entered": bool(controller_entered),
            "dispatch_seq": (dispatch_seq if isinstance(dispatch_seq, int)
                             and not isinstance(dispatch_seq, bool) else None),
        }
        if not self._write(document):
            return False
        return True

    def _write(self, document: Mapping[str, object]) -> bool:
        if self.path is None:
            return False
        try:
            data = (json.dumps(document, sort_keys=True, separators=(",", ":"),
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
        """Observability-gap summary (never an enforcement input)."""
        with self._lock:
            errors = self.errors
            written = self.written
            last_error = self.last_error
        return {
            "schema": REQUEST_LIFECYCLE_SCHEMA,
            "journal": "request-lifecycle",
            "enabled": self.enabled,
            "written": written,
            "write_errors": errors,
            "last_error": last_error,
            "observability_gap": bool(errors),
        }


def default_lifecycle_path(attempt_db: str | os.PathLike[str]) -> Path:
    """Lifecycle journal lives beside the trusted Attempt DB (same state dir)."""
    return Path(attempt_db).with_name(DEFAULT_LIFECYCLE_FILENAME)
