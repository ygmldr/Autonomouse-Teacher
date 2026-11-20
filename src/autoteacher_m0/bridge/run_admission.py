"""A-NEXT P2-02 run-level ExecutionAuthorization admission (trusted, no-key).

This module closes the G4-R scope gap recorded as P2-02: the module-level
``consume_execution_authorization()`` had no production caller, so a real Run
had no mandatory single-use authorization entry.  The design ADR is
``docs/A_NEXT_RUN_ADMISSION_DESIGN.md``; this implementation follows it with the
Reviewer conditions C2-C8:

* the authorization is consumed **once per Run**, before any Broker/Fake/
  Controller is constructed (a denied Run therefore creates no Reservation, no
  Fake send and no Attempt);
* ``run_epoch`` is derived deterministically from the trusted Admission document
  (admission id + launcher nonce + run id), so restarting the same Run is
  classified ``AUTHORIZATION_REPLAYED`` while another Run reusing the same
  authorization is ``AUTHORIZATION_EPOCH_MISMATCH``;
* the business ``call_id`` is a *different* identity and is never confused with
  the run epoch;
* after ``consume`` returns, the use record is asserted to carry exactly the
  expected authorization id and run epoch (C2 TOCTOU check); a mismatch is
  ``RUN_ADMISSION_AUTHORIZATION_DRIFT`` and never sends anything;
* each dispatch must consume one in-process ``DispatchAdmissionToken`` minted by
  the Run principal; there is no JSON constructor for the token and a copied/
  replayed/foreign token is always denied (default deny);
* an append-only, allowlisted run-admission journal records the decision
  (including the tri-state consumed outcome) without ever writing a Key, a raw
  prompt, a message, a tool argument or session text.

The module is intentionally offline: it imports no network, Key, Provider or
LiveGate code path.  This is a no-key / test-only capability; it does not and
cannot authorize a live call (see ``security/authorization.py``: an accepted
document still never sets ``billable_send_authorized``).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import threading
import time
import uuid
from typing import Any, Callable, Mapping

from autoteacher_m0.security.authorization import (
    AuthorizationRejected,
    AuthorizationUse,
    ExpectedBindings,
    consume_execution_authorization,
    load_execution_authorization,
)

RUN_ADMISSION_SCHEMA = "m0.g4r.run-admission.v1"
DISPATCH_TOKEN_SCHEMA = "m0.g4r.dispatch-admission-token.v1"
RUN_EPOCH_SCHEMA = "m0.g4r.run-epoch.v1"

RUN_ADMISSION_ACTIVE = "ACTIVE"
RUN_ADMISSION_CLOSED = "CLOSED"

DISPATCH_TOKEN_TTL_SECONDS = 30
MAX_JOURNAL_BYTES = 1_048_576
MAX_JOURNAL_RECORDS = 4096
MAX_AUTHORIZATION_FILE_BYTES = 64 * 1024
MAX_USE_RECORD_BYTES = 8 * 1024

# -- stable outcome / denial codes (closed set; audit reasons are these only) --
RUN_ADMISSION_AUTHORIZATION_INVALID = "RUN_ADMISSION_AUTHORIZATION_INVALID"
RUN_ADMISSION_ALREADY_CONSUMED = "RUN_ADMISSION_ALREADY_CONSUMED"
RUN_ADMISSION_EPOCH_MISMATCH = "RUN_ADMISSION_EPOCH_MISMATCH"
RUN_ADMISSION_RECORD_INVALID = "RUN_ADMISSION_RECORD_INVALID"
RUN_ADMISSION_LOG_UNAVAILABLE = "RUN_ADMISSION_LOG_UNAVAILABLE"
RUN_ADMISSION_DURABILITY_UNKNOWN = "RUN_ADMISSION_DURABILITY_UNKNOWN"
RUN_ADMISSION_AUTHORIZATION_DRIFT = "RUN_ADMISSION_AUTHORIZATION_DRIFT"
RUN_ADMISSION_AUDIT_UNAVAILABLE = "RUN_ADMISSION_AUDIT_UNAVAILABLE"
RUN_ADMISSION_AUDIT_FULL = "RUN_ADMISSION_AUDIT_FULL"
RUN_ADMISSION_IDENTITY_INVALID = "RUN_ADMISSION_IDENTITY_INVALID"
RUN_ADMISSION_LIMITS_INVALID = "RUN_ADMISSION_LIMITS_INVALID"
RUN_ADMISSION_TOOL_SCHEMA_MISMATCH = "RUN_ADMISSION_TOOL_SCHEMA_MISMATCH"
RUN_ADMISSION_REQUIRED = "RUN_ADMISSION_REQUIRED"
RUN_ADMISSION_NOT_ACTIVE = "RUN_ADMISSION_NOT_ACTIVE"
RUN_ADMISSION_INTERNAL = "RUN_ADMISSION_INTERNAL"

ADMISSION_TOKEN_UNKNOWN = "ADMISSION_TOKEN_UNKNOWN"
ADMISSION_TOKEN_REPLAYED = "ADMISSION_TOKEN_REPLAYED"
ADMISSION_TOKEN_ORDER_INVALID = "ADMISSION_TOKEN_ORDER_INVALID"
ADMISSION_TOKEN_BINDING_MISMATCH = "ADMISSION_TOKEN_BINDING_MISMATCH"
ADMISSION_TOKEN_EXPIRED = "ADMISSION_TOKEN_EXPIRED"
RUN_EPOCH_MISMATCH = "RUN_EPOCH_MISMATCH"
RUN_ADMISSION_INACTIVE = "RUN_ADMISSION_INACTIVE"
RUN_DEADLINE_EXCEEDED = "RUN_DEADLINE_EXCEEDED"
RUN_BUDGET_CALLS_EXCEEDED = "RUN_BUDGET_CALLS_EXCEEDED"

CONSUMED_YES = "YES"
CONSUMED_NO = "NO"
CONSUMED_UNKNOWN = "UNKNOWN"

_IDENTIFIER = re.compile(r"[A-Za-z0-9._:-]{1,128}")
_HEX32 = re.compile(r"[0-9a-f]{32}")
_HEX64 = re.compile(r"[0-9a-f]{64}")
_UTC_TEXT = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
_RECORD_EVENTS = frozenset({"intent", "outcome", "dispatch_denied", "final"})
_JOURNAL_FIELDS = frozenset({
    "schema", "event", "utc",
    "launcher_instance_id", "launcher_uid",
    "run_id", "admission_id", "admission_sha256", "admission_nonce_sha256",
    "authorization_id", "approver", "key_id",
    "authorization_payload_sha256", "authorization_file_sha256",
    "run_epoch", "expected_bindings_sha256", "observed_bindings_sha256",
    "binding_checkpoint", "route_id", "provider", "model",
    "tool_set_sha256", "tool_names",
    "budget_scope", "authorization_max_calls", "admission_max_calls",
    "effective_max_calls",
    "authorization_expires_utc", "run_deadline_utc",
    "decision", "reject_reasons", "consumed", "use_record_sha256",
    "use_log_durability",
    "historical_holds_observed", "historical_holds_modified",
    "attempt_db_touched",
    "dispatch_ordinal", "dispatch_denial", "call_id_sha256",
    "external_network_calls", "real_model_calls", "provider_keys_seen",
})


class RunAdmissionError(Exception):
    """Fail-closed admission/denial with a stable machine code.

    ``consumed`` is tri-state and is deliberately part of the error: a denial
    is not always "nothing happened".  In particular
    ``RUN_ADMISSION_DURABILITY_UNKNOWN`` means the final use record is visible
    (the use is spent) but the directory fsync failed, so no dispatch may
    follow and a later attempt is expected to be classified as a replay.
    """

    def __init__(self, code: str, reasons: tuple[str, ...] = (), *,
                 consumed: str = CONSUMED_NO, outcome: str | None = None,
                 record: Mapping[str, object] | None = None) -> None:
        super().__init__(f"{code}: {'; '.join(reasons)}" if reasons else code)
        self.code = code
        self.reasons = tuple(reasons)
        self.consumed = consumed
        self.outcome = outcome or code
        self.record = dict(record) if record else {}


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _canonical(payload: object) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _utc_text(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def derive_run_epoch(*, admission_id: str, admission_nonce: str,
                     run_id: str) -> str:
    """Deterministic per-Run epoch from the trusted Admission identity.

    The same Admission document (hence the same launcher nonce) always yields
    the same epoch, so restarting the same Run is a replay of the single use.
    A different Run must use a different Admission document, which changes the
    epoch and classifies the reuse as ``AUTHORIZATION_EPOCH_MISMATCH``.
    """
    payload = {
        "schema": RUN_EPOCH_SCHEMA,
        "admission_id": admission_id,
        "admission_nonce": admission_nonce,
        "run_id": run_id,
    }
    return "run-" + _sha256_hex(_canonical(payload))[:32]


def _require_identifier(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise RunAdmissionError(RUN_ADMISSION_IDENTITY_INVALID,
                                (f"{label}_INVALID",))
    return value


def _require_hex(value: object, *, label: str, length: int = 64) -> str:
    pattern = _HEX64 if length == 64 else _HEX32
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise RunAdmissionError(RUN_ADMISSION_IDENTITY_INVALID,
                                (f"{label}_INVALID",))
    return value


@dataclass(frozen=True)
class RunIdentity:
    """Trusted per-Run identity; immutable and validated on construction."""

    run_id: str
    admission_id: str
    admission_nonce: str
    admission_sha256: str
    run_epoch: str

    def __post_init__(self) -> None:
        _require_identifier(self.run_id, label="run_id")
        _require_hex(self.admission_id, label="admission_id", length=32)
        _require_hex(self.admission_nonce, label="admission_nonce", length=32)
        _require_hex(self.admission_sha256, label="admission_sha256")
        _require_identifier(self.run_epoch, label="run_epoch")
        expected = derive_run_epoch(admission_id=self.admission_id,
                                    admission_nonce=self.admission_nonce,
                                    run_id=self.run_id)
        if self.run_epoch != expected:
            raise RunAdmissionError(RUN_ADMISSION_IDENTITY_INVALID,
                                    ("run_epoch_derivation_mismatch",))


def _read_trusted_bytes(path: Path, *, repo_root: Path, label: str,
                        max_bytes: int) -> bytes:
    """Strict read of one operator-owned external file (no links, bounded)."""
    if not isinstance(path, Path) or not path.is_absolute():
        raise ValueError(f"{label} path must be absolute")
    if path.is_symlink():
        raise ValueError(f"{label} must not be a symlink")
    try:
        resolved = path.resolve(strict=True)
        root = repo_root.resolve(strict=True)
    except OSError as error:
        raise ValueError(f"{label} does not exist") from error
    if resolved.is_relative_to(root):
        raise ValueError(f"{label} must live outside the repository")
    parent = resolved.parent
    try:
        parent_info = parent.stat()
    except OSError as error:
        raise ValueError(f"{label} directory is unreadable") from error
    if not stat.S_ISDIR(parent_info.st_mode) or parent.is_symlink():
        raise ValueError(f"{label} directory is invalid")
    if parent_info.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise ValueError(f"{label} directory must not be group/world writable")
    try:
        descriptor = os.open(resolved, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as error:
        raise ValueError(f"{label} is unreadable") from error
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError(f"{label} must be a regular file")
        if info.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            raise ValueError(f"{label} must not be group/world writable")
        if not 0 < info.st_size <= max_bytes:
            raise ValueError(f"{label} size is outside the permitted range")
        chunks: list[bytes] = []
        remaining = max_bytes + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(remaining, 65536))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
    except OSError as error:
        raise ValueError(f"{label} is unreadable") from error
    finally:
        os.close(descriptor)
    if len(data) != info.st_size or len(data) > max_bytes:
        raise ValueError(f"{label} changed while it was being read")
    return data


def _external_sha256(path: Path, *, repo_root: Path, label: str,
                     max_bytes: int = MAX_AUTHORIZATION_FILE_BYTES) -> str:
    try:
        return _sha256_hex(_read_trusted_bytes(path, repo_root=repo_root,
                                               label=label, max_bytes=max_bytes))
    except ValueError as error:
        raise RunAdmissionError(RUN_ADMISSION_AUTHORIZATION_INVALID,
                                (f"EXTERNAL_AUTHORIZATION_INVALID:{error}",)) from None


def build_run_identity(admission: object, *, admission_path: Path,
                       repo_root: Path) -> RunIdentity:
    """Build the trusted Run identity from one loaded Admission document."""
    admission_id = getattr(admission, "admission_id", None)
    run_id = getattr(admission, "run_id", None)
    nonce = getattr(admission, "admission_nonce", None)
    sha = getattr(admission, "sha256", None)
    for value, label in ((admission_id, "admission_id"), (run_id, "run_id"),
                         (nonce, "admission_nonce"), (sha, "admission_sha256")):
        if not isinstance(value, str) or not value:
            raise RunAdmissionError(RUN_ADMISSION_IDENTITY_INVALID,
                                    (f"{label}_MISSING",))
    raw = _read_trusted_bytes(admission_path, repo_root=repo_root,
                              label="admission", max_bytes=MAX_AUTHORIZATION_FILE_BYTES)
    if _sha256_hex(raw) != sha:
        raise RunAdmissionError(RUN_ADMISSION_IDENTITY_INVALID,
                                ("admission_document_changed",))
    return RunIdentity(run_id=run_id, admission_id=admission_id,
                       admission_nonce=nonce, admission_sha256=sha,
                       run_epoch=derive_run_epoch(admission_id=admission_id,
                                                  admission_nonce=nonce,
                                                  run_id=run_id))


class RunAdmissionJournal:
    """Append-only allowlisted run-admission journal (no Key/raw request).

    Every record is a bounded canonical JSON line; the file is opened with
    ``O_NOFOLLOW|O_APPEND`` and each append is followed by ``fsync``.  A journal
    that cannot be written is a fail-closed condition for the admission (the
    caller must not start a Broker).  The two-phase ``intent``/``outcome``
    sequence makes a crash after consumption auditable: the intent exists, the
    use log carries the authoritative spent state, and a restart is classified
    as a replay for manual reconciliation.
    """

    def __init__(self, path: Path, *, max_records: int = MAX_JOURNAL_RECORDS) -> None:
        if not isinstance(path, Path) or not path.is_absolute():
            raise RunAdmissionError(RUN_ADMISSION_AUDIT_UNAVAILABLE,
                                    ("journal_path_invalid",))
        self.path = path
        self.max_records = max_records
        self._lock = threading.RLock()
        self._fd: int | None = None
        try:
            parent = path.parent
            info = parent.lstat()
            if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
                raise ValueError("journal directory is invalid")
            if info.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
                raise ValueError("journal directory must not be group/world writable")
            self._entries = self._count_entries()
            flags = os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_CLOEXEC
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            self._fd = os.open(path, flags, 0o600)
            file_info = os.fstat(self._fd)
            if not stat.S_ISREG(file_info.st_mode):
                raise ValueError("journal must be a regular file")
            if file_info.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
                raise ValueError("journal must not be group/world writable")
            os.fsync(self._fd)
            directory_fd = os.open(parent, os.O_RDONLY | os.O_CLOEXEC)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except (OSError, ValueError) as error:
            self.close()
            raise RunAdmissionError(RUN_ADMISSION_AUDIT_UNAVAILABLE,
                                    (f"journal_open_failed:{type(error).__name__}",)) from None

    def _count_entries(self) -> int:
        try:
            data = self.path.read_bytes()
        except FileNotFoundError:
            return 0
        except OSError as error:
            raise ValueError("journal is unreadable") from error
        return data.count(b"\n")

    def append(self, event: str, fields: Mapping[str, object]) -> dict:
        if event not in _RECORD_EVENTS:
            raise RunAdmissionError(RUN_ADMISSION_AUDIT_UNAVAILABLE,
                                    ("journal_event_invalid",))
        unknown = set(fields) - _JOURNAL_FIELDS
        if unknown:
            raise RunAdmissionError(RUN_ADMISSION_AUDIT_UNAVAILABLE,
                                    ("journal_field_rejected",))
        document: dict[str, object] = {"schema": RUN_ADMISSION_SCHEMA,
                                       "event": event, "utc": utc_now()}
        document.update(fields)
        sanitized = {key: _sanitize_field(value) for key, value in document.items()}
        payload = _canonical(sanitized) + b"\n"
        if len(payload) > MAX_JOURNAL_BYTES:
            raise RunAdmissionError(RUN_ADMISSION_AUDIT_FULL,
                                    ("journal_record_too_large",))
        with self._lock:
            if self._entries >= self.max_records:
                raise RunAdmissionError(RUN_ADMISSION_AUDIT_FULL,
                                        ("journal_full",))
            descriptor = self._fd
            if descriptor is None:
                raise RunAdmissionError(RUN_ADMISSION_AUDIT_UNAVAILABLE,
                                        ("journal_closed",))
            try:
                written = os.write(descriptor, payload)
                if written != len(payload):
                    raise OSError("short journal write")
                os.fsync(descriptor)
            except OSError:
                raise RunAdmissionError(RUN_ADMISSION_AUDIT_UNAVAILABLE,
                                        ("journal_write_failed",)) from None
            self._entries += 1
        return sanitized

    def close(self) -> None:
        descriptor = self._fd
        self._fd = None
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass


def _sanitize_field(value: object) -> object:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        if len(value) > 512:
            raise RunAdmissionError(RUN_ADMISSION_AUDIT_UNAVAILABLE,
                                    ("journal_value_too_long",))
        return value
    if isinstance(value, (list, tuple)):
        if len(value) > 16:
            raise RunAdmissionError(RUN_ADMISSION_AUDIT_UNAVAILABLE,
                                    ("journal_list_too_long",))
        items: list[str] = []
        for item in value:
            if not isinstance(item, str) or len(item) > 256:
                raise RunAdmissionError(RUN_ADMISSION_AUDIT_UNAVAILABLE,
                                        ("journal_list_item_invalid",))
            items.append(item)
        return items
    raise RunAdmissionError(RUN_ADMISSION_AUDIT_UNAVAILABLE,
                            ("journal_value_type_invalid",))


@dataclass(frozen=True)
class DispatchAdmissionToken:
    """Trusted per-dispatch capability; there is no JSON constructor path."""

    schema_version: str
    run_id: str
    run_epoch: str
    authorization_id: str
    scope_id: str
    call_id: str
    prepared_digest: str
    payload_digest: str
    payload_length: int
    dispatch_ordinal: int
    route_id: str
    model_id: str
    issued_utc: str
    expires_utc: str
    principal_instance_id: str
    nonce_sha256: str
    synthetic: bool = True

    def __post_init__(self) -> None:
        if self.schema_version != DISPATCH_TOKEN_SCHEMA:
            raise ValueError("dispatch token schema mismatch")
        for value, label in ((self.run_epoch, "run_epoch"),
                             (self.authorization_id, "authorization_id"),
                             (self.scope_id, "scope_id"),
                             (self.call_id, "call_id"),
                             (self.route_id, "route_id"),
                             (self.model_id, "model_id"),
                             (self.issued_utc, "issued_utc"),
                             (self.expires_utc, "expires_utc"),
                             (self.principal_instance_id, "principal_instance_id")):
            if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
                raise ValueError(f"dispatch token {label} invalid")
        for value, label in ((self.prepared_digest, "prepared_digest"),
                             (self.payload_digest, "payload_digest"),
                             (self.nonce_sha256, "nonce_sha256")):
            if not isinstance(value, str) or not _HEX64.fullmatch(value):
                raise ValueError(f"dispatch token {label} invalid")
        if type(self.payload_length) is not int or self.payload_length < 0:
            raise ValueError("dispatch token payload length invalid")
        if type(self.dispatch_ordinal) is not int or self.dispatch_ordinal < 1:
            raise ValueError("dispatch token ordinal invalid")
        if self.synthetic is not True:
            raise ValueError("dispatch token must be synthetic")


class RunAdmissionContext:
    """Active trusted principal for one consumed Run.

    Only this object mints and verifies ``DispatchAdmissionToken`` instances.
    Verification is by object identity in an in-process registry (the same
    approach as ``TrustedSendGate``): a copied dataclass, a JSON mapping or a
    token from another Run/process is never accepted.
    """

    def __init__(self, *, identity: RunIdentity, authorization_id: str,
                 authorization_sha256: str, authorization_payload_sha256: str,
                 approver: str, key_id: str,
                 expected_bindings_sha256: str, observed_bindings_sha256: str,
                 binding_checkpoint: str, tool_set_sha256: str,
                 tool_names: tuple[str, ...], route_id: str, provider: str,
                 model: str, budget_scope: str, effective_max_calls: int,
                 max_attempts: int, run_deadline_seconds: int,
                 authorization_expires_utc: str, use_record_sha256: str | None,
                 journal: RunAdmissionJournal, launcher_instance_id: str,
                 launcher_uid: int,
                 dispatch_token_ttl_seconds: int = DISPATCH_TOKEN_TTL_SECONDS
                 ) -> None:
        self.identity = identity
        self.authorization_id = authorization_id
        self.authorization_sha256 = authorization_sha256
        self.authorization_payload_sha256 = authorization_payload_sha256
        self.approver = approver
        self.key_id = key_id
        self.expected_bindings_sha256 = expected_bindings_sha256
        self.observed_bindings_sha256 = observed_bindings_sha256
        self.binding_checkpoint = binding_checkpoint
        self.tool_set_sha256 = tool_set_sha256
        self.tool_names = tuple(tool_names)
        self.route_id = route_id
        self.provider = provider
        self.model = model
        self.budget_scope = budget_scope
        self.effective_max_calls = effective_max_calls
        self.max_attempts = max_attempts
        self.run_deadline_seconds = run_deadline_seconds
        self.authorization_expires_utc = authorization_expires_utc
        self.use_record_sha256 = use_record_sha256
        self.journal = journal
        self.launcher_instance_id = launcher_instance_id
        self.launcher_uid = launcher_uid
        self.dispatch_token_ttl_seconds = dispatch_token_ttl_seconds
        self.instance_id = "radm-" + uuid.uuid4().hex
        self.owner_pid = os.getpid()
        self._nonce = os.urandom(32)
        self._lock = threading.RLock()
        self._issued: dict[int, DispatchAdmissionToken] = {}
        self._issued_deadline: dict[int, float] = {}
        self._consumed_ordinals: set[int] = set()
        self._consumed_token_ids: set[int] = set()
        self._next_ordinal = 1
        self._state = RUN_ADMISSION_ACTIVE
        self._deadline_monotonic = time.monotonic() + float(run_deadline_seconds)
        self._base_fields = self._audit_fields()

    # -- read-only surface --------------------------------------------------
    @property
    def state(self) -> str:
        return self._state

    @property
    def consumed(self) -> str:
        return CONSUMED_YES

    @property
    def run_epoch(self) -> str:
        return self.identity.run_epoch

    @property
    def run_id(self) -> str:
        return self.identity.run_id

    @property
    def scope_id(self) -> str:
        return self._scope_id if hasattr(self, "_scope_id") else ""

    @property
    def remaining_seconds(self) -> float:
        return max(0.0, self._deadline_monotonic - time.monotonic())

    def ensure_startable(self) -> None:
        """Fail closed unless this exact process may start the trusted chain."""
        with self._lock:
            if self._state != RUN_ADMISSION_ACTIVE:
                raise RunAdmissionError(RUN_ADMISSION_NOT_ACTIVE,
                                        (self._state.lower(),))
            if self.owner_pid != os.getpid():
                raise RunAdmissionError(RUN_ADMISSION_NOT_ACTIVE,
                                        ("foreign_process",))
            if time.monotonic() >= self._deadline_monotonic:
                raise RunAdmissionError(RUN_DEADLINE_EXCEEDED, ("run_deadline",))

    # -- dispatch capabilities ---------------------------------------------
    def begin_dispatch(self, *, call_id: str, prepared_digest: str,
                       payload_digest: str, payload_length: int = 0,
                       scope_id: str = "", route_id: str = "",
                       model_id: str = "") -> DispatchAdmissionToken:
        moment = datetime.now(timezone.utc)
        with self._lock:
            self._check_active_locked()
            if not isinstance(call_id, str) or not _IDENTIFIER.fullmatch(call_id):
                raise RunAdmissionError(ADMISSION_TOKEN_BINDING_MISMATCH,
                                        ("call_id_invalid",))
            for value, label in ((prepared_digest, "prepared_digest"),
                                 (payload_digest, "payload_digest")):
                if not isinstance(value, str) or not _HEX64.fullmatch(value):
                    raise RunAdmissionError(ADMISSION_TOKEN_BINDING_MISMATCH,
                                            (f"{label}_invalid",))
            if type(payload_length) is not int or payload_length < 0:
                raise RunAdmissionError(ADMISSION_TOKEN_BINDING_MISMATCH,
                                        ("payload_length_invalid",))
            ordinal = self._next_ordinal
            if ordinal > self.effective_max_calls:
                raise RunAdmissionError(RUN_BUDGET_CALLS_EXCEEDED,
                                        ("effective_max_calls",))
            ttl = min(self.dispatch_token_ttl_seconds,
                      max(1, int(self.remaining_seconds) or 1))
            expires_utc = _utc_text(moment.replace(microsecond=0)
                                    + timedelta(seconds=ttl))
            token = DispatchAdmissionToken(
                schema_version=DISPATCH_TOKEN_SCHEMA,
                run_id=self.identity.run_id,
                run_epoch=self.identity.run_epoch,
                authorization_id=self.authorization_id,
                scope_id=scope_id or getattr(self, "_scope_id", "") or self.budget_scope,
                call_id=call_id,
                prepared_digest=prepared_digest,
                payload_digest=payload_digest,
                payload_length=payload_length,
                dispatch_ordinal=ordinal,
                route_id=route_id or self.route_id,
                model_id=model_id or self.model,
                issued_utc=_utc_text(moment),
                expires_utc=expires_utc,
                principal_instance_id=self.instance_id,
                nonce_sha256=_sha256_hex(self._nonce),
            )
            self._issued[id(token)] = token
            self._issued_deadline[id(token)] = time.monotonic() + float(ttl)
            self._next_ordinal += 1
            return token

    def consume_dispatch(self, token: object, *, call_id: str,
                         prepared_digest: str, payload_digest: str
                         ) -> str | None:
        """Consume exactly one token; None accepted, otherwise a stable code."""
        with self._lock:
            if self._state != RUN_ADMISSION_ACTIVE:
                return RUN_ADMISSION_INACTIVE
            issued = self._issued.get(id(token))
            if not isinstance(token, DispatchAdmissionToken) or issued is not token:
                return self._deny(ADMISSION_TOKEN_UNKNOWN, None, call_id)
            if (id(token) in self._consumed_token_ids
                    or token.dispatch_ordinal in self._consumed_ordinals):
                return self._deny(ADMISSION_TOKEN_REPLAYED, token, call_id)
            if (token.run_id != self.identity.run_id
                    or token.run_epoch != self.identity.run_epoch
                    or token.authorization_id != self.authorization_id):
                return self._deny(RUN_EPOCH_MISMATCH, token, call_id)
            if token.call_id != call_id or token.prepared_digest != prepared_digest \
                    or token.payload_digest != payload_digest:
                return self._deny(ADMISSION_TOKEN_BINDING_MISMATCH, token, call_id)
            if token.dispatch_ordinal < 1 or token.dispatch_ordinal > self.effective_max_calls:
                return self._deny(ADMISSION_TOKEN_ORDER_INVALID, token, call_id)
            if time.monotonic() >= self._deadline_monotonic:
                return self._deny(RUN_DEADLINE_EXCEEDED, token, call_id)
            deadline = self._issued_deadline.get(id(token), 0.0)
            if time.monotonic() >= deadline:
                return self._deny(ADMISSION_TOKEN_EXPIRED, token, call_id)
            self._consumed_ordinals.add(token.dispatch_ordinal)
            self._consumed_token_ids.add(id(token))
            self._issued_deadline.pop(id(token), None)
            return None

    def _check_active_locked(self) -> None:
        if self._state != RUN_ADMISSION_ACTIVE:
            raise RunAdmissionError(RUN_ADMISSION_INACTIVE, (self._state.lower(),))
        if self.owner_pid != os.getpid():
            raise RunAdmissionError(RUN_ADMISSION_INACTIVE, ("foreign_process",))
        if time.monotonic() >= self._deadline_monotonic:
            raise RunAdmissionError(RUN_DEADLINE_EXCEEDED, ("run_deadline",))

    def _deny(self, code: str, token: DispatchAdmissionToken | None,
              call_id: str) -> str:
        ordinal = token.dispatch_ordinal if token is not None else 0
        try:
            self.journal.append("dispatch_denied", {
                **self._base_fields,
                "decision": "DENY",
                "reject_reasons": [code],
                "consumed": CONSUMED_NO,
                "dispatch_ordinal": ordinal,
                "dispatch_denial": code,
                "call_id_sha256": _sha256_hex(call_id.encode("utf-8")),
            })
        except RunAdmissionError:
            raise RunAdmissionError(RUN_ADMISSION_AUDIT_UNAVAILABLE,
                                    ("dispatch_denial_audit_failed",)) from None
        return code

    def close(self, reason: str = "closed") -> None:
        with self._lock:
            self._state = RUN_ADMISSION_CLOSED
            self._issued.clear()
            self._issued_deadline.clear()
            self._consumed_token_ids.clear()
        try:
            self.journal.append("final", {
                **self._base_fields,
                "decision": "CLOSED",
                "reject_reasons": [reason],
                "consumed": CONSUMED_YES,
            })
        except RunAdmissionError:
            pass
        finally:
            self.journal.close()

    def _audit_fields(self) -> dict[str, object]:
        return {
            "launcher_instance_id": self.launcher_instance_id,
            "launcher_uid": self.launcher_uid,
            "run_id": self.identity.run_id,
            "admission_id": self.identity.admission_id,
            "admission_sha256": self.identity.admission_sha256,
            "admission_nonce_sha256": _sha256_hex(
                self.identity.admission_nonce.encode("ascii")),
            "authorization_id": self.authorization_id,
            "approver": self.approver,
            "key_id": self.key_id,
            "authorization_payload_sha256": self.authorization_payload_sha256,
            "authorization_file_sha256": self.authorization_sha256,
            "run_epoch": self.identity.run_epoch,
            "expected_bindings_sha256": self.expected_bindings_sha256,
            "observed_bindings_sha256": self.observed_bindings_sha256,
            "binding_checkpoint": self.binding_checkpoint,
            "route_id": self.route_id,
            "provider": self.provider,
            "model": self.model,
            "tool_set_sha256": self.tool_set_sha256,
            "tool_names": list(self.tool_names),
            "budget_scope": self.budget_scope,
            "authorization_max_calls": self._authorization_max_calls(),
            "admission_max_calls": self._admission_max_calls(),
            "effective_max_calls": self.effective_max_calls,
            "authorization_expires_utc": self.authorization_expires_utc,
            "run_deadline_utc": _utc_text(
                datetime.now(timezone.utc)
                + timedelta(seconds=self.run_deadline_seconds)),
            "historical_holds_observed": 0,
            "historical_holds_modified": False,
            "attempt_db_touched": False,
            "external_network_calls": 0,
            "real_model_calls": 0,
            "provider_keys_seen": 0,
        }

    def _authorization_max_calls(self) -> int:
        return int(getattr(self, "_authorization_calls", self.effective_max_calls))

    def _admission_max_calls(self) -> int:
        return int(getattr(self, "_admission_calls", self.effective_max_calls))


def _tool_set_digest(admission_tool_schemas: tuple[tuple[str, str], ...],
                     actual_tools: tuple[str, ...],
                     approved_tool_schemas: Mapping[str, str] | None = None
                     ) -> tuple[str, tuple[str, ...]]:
    if not isinstance(admission_tool_schemas, tuple) or not admission_tool_schemas:
        raise RunAdmissionError(RUN_ADMISSION_TOOL_SCHEMA_MISMATCH,
                                ("admission_tool_schemas_missing",))
    names: list[str] = []
    schemas: dict[str, str] = {}
    for item in admission_tool_schemas:
        if (not isinstance(item, tuple) or len(item) != 2
                or not isinstance(item[0], str) or not _IDENTIFIER.fullmatch(item[0])
                or not isinstance(item[1], str) or not _HEX64.fullmatch(item[1])):
            raise RunAdmissionError(RUN_ADMISSION_TOOL_SCHEMA_MISMATCH,
                                    ("admission_tool_schema_invalid",))
        if item[0] in schemas:
            raise RunAdmissionError(RUN_ADMISSION_TOOL_SCHEMA_MISMATCH,
                                    ("admission_tool_schema_duplicate",))
        names.append(item[0])
        schemas[item[0]] = item[1]
    if tuple(sorted(names)) != tuple(sorted(actual_tools)):
        raise RunAdmissionError(RUN_ADMISSION_TOOL_SCHEMA_MISMATCH,
                                ("tool_names_mismatch",))
    if approved_tool_schemas is not None:
        if (not isinstance(approved_tool_schemas, Mapping)
                or dict(approved_tool_schemas) != schemas):
            raise RunAdmissionError(RUN_ADMISSION_TOOL_SCHEMA_MISMATCH,
                                    ("approved_tool_schema_digest_mismatch",))
    digest = _sha256_hex(_canonical({"names": sorted(schemas),
                                     "schemas": schemas}))
    return digest, tuple(sorted(names))


def _limits(admission_limits: Mapping[str, object], *,
            authorization_calls: int, authorization_seconds: int
            ) -> tuple[int, int, int]:
    if not isinstance(admission_limits, Mapping) or set(admission_limits) != {
            "max_calls", "max_attempts", "deadline_ms"}:
        raise RunAdmissionError(RUN_ADMISSION_LIMITS_INVALID,
                                ("admission_limits_fields",))
    values: dict[str, int] = {}
    for key, maximum in (("max_calls", 50), ("max_attempts", 50),
                         ("deadline_ms", 3_600_000)):
        value = admission_limits[key]
        if type(value) is not int or not 1 <= value <= maximum:
            raise RunAdmissionError(RUN_ADMISSION_LIMITS_INVALID,
                                    (f"{key}_out_of_range",))
        values[key] = value
    effective_calls = min(authorization_calls, values["max_calls"])
    effective_attempts = min(50, values["max_attempts"])
    effective_seconds = min(authorization_seconds,
                            max(1, values["deadline_ms"] // 1000))
    return effective_calls, effective_attempts, effective_seconds


def _map_consume_reasons(reasons: tuple[str, ...]) -> tuple[str, str]:
    joined = " ".join(reasons)
    if "DURABILITY_UNKNOWN" in joined:
        return RUN_ADMISSION_DURABILITY_UNKNOWN, CONSUMED_UNKNOWN
    if "REPLAYED" in joined:
        return RUN_ADMISSION_ALREADY_CONSUMED, CONSUMED_NO
    if "EPOCH_MISMATCH" in joined:
        return RUN_ADMISSION_EPOCH_MISMATCH, CONSUMED_NO
    if "USE_RECORD_INVALID" in joined or "UNREADABLE" in joined:
        return RUN_ADMISSION_RECORD_INVALID, CONSUMED_NO
    if any(token in joined for token in (
            "WRITE_FAILED", "LOG_FULL", "LOG_INVALID", "LOG_UNREADABLE",
            "USE_LOG_INVALID")):
        return RUN_ADMISSION_LOG_UNAVAILABLE, CONSUMED_NO
    return RUN_ADMISSION_AUTHORIZATION_INVALID, CONSUMED_NO


def _identity_audit_fields(identity: RunIdentity, *,
                           launcher_instance_id: str,
                           launcher_uid: int) -> dict[str, object]:
    return {
        "launcher_instance_id": launcher_instance_id,
        "launcher_uid": launcher_uid,
        "run_id": identity.run_id,
        "admission_id": identity.admission_id,
        "admission_sha256": identity.admission_sha256,
        "admission_nonce_sha256": _sha256_hex(
            identity.admission_nonce.encode("ascii")),
        "run_epoch": identity.run_epoch,
        "historical_holds_observed": 0,
        "historical_holds_modified": False,
        "attempt_db_touched": False,
        "external_network_calls": 0,
        "real_model_calls": 0,
        "provider_keys_seen": 0,
    }


def _outcome_fields(*, identity: RunIdentity, authorization: object,
                    authorization_file_sha256: str,
                    expected_digest: str, observed_digest: str,
                    tool_set_sha256: str, tool_names: tuple[str, ...],
                    launcher_instance_id: str, launcher_uid: int,
                    effective_calls: int, admission_calls: int,
                    authorization_calls: int, deadline_utc: str,
                    decision: str, reasons: tuple[str, ...],
                    consumed: str, use_record_sha256: str | None,
                    durability: str) -> dict[str, object]:
    budget = getattr(authorization, "budget")
    route = getattr(authorization, "route")
    return {
        **_identity_audit_fields(
            identity, launcher_instance_id=launcher_instance_id,
            launcher_uid=launcher_uid),
        "authorization_id": getattr(authorization, "authorization_id"),
        "approver": getattr(authorization, "approver"),
        "key_id": getattr(authorization, "key_id"),
        "authorization_payload_sha256": _sha256_hex(
            getattr(authorization, "payload_bytes")),
        "authorization_file_sha256": authorization_file_sha256,
        "expected_bindings_sha256": expected_digest,
        "observed_bindings_sha256": observed_digest,
        "binding_checkpoint": "pre_start",
        "route_id": getattr(route, "route_id"),
        "provider": getattr(route, "provider"),
        "model": getattr(route, "model"),
        "tool_set_sha256": tool_set_sha256,
        "tool_names": list(tool_names),
        "budget_scope": getattr(budget, "scope"),
        "authorization_max_calls": authorization_calls,
        "admission_max_calls": admission_calls,
        "effective_max_calls": effective_calls,
        "authorization_expires_utc": _utc_text(
            getattr(authorization, "expires_utc")),
        "run_deadline_utc": deadline_utc,
        "decision": decision,
        "reject_reasons": list(reasons),
        "consumed": consumed,
        "use_record_sha256": use_record_sha256,
        "use_log_durability": durability,
    }


def _journal_deny(journal: RunAdmissionJournal, fields: dict[str, object],
                  code: str, reasons: tuple[str, ...], *,
                  consumed: str) -> dict[str, object]:
    record = dict(fields)
    record.update({
        "decision": "DENY",
        "reject_reasons": [code, *reasons],
        "consumed": consumed,
        "use_log_durability": "UNKNOWN" if consumed == CONSUMED_UNKNOWN else "KNOWN",
    })
    try:
        return journal.append("outcome", record)
    except RunAdmissionError:
        raise RunAdmissionError(RUN_ADMISSION_AUDIT_UNAVAILABLE,
                                ("outcome_audit_failed",),
                                consumed=consumed) from None


def _begin_run_admission_impl(
    *,
    identity: RunIdentity,
    admission_path: Path,
    admission_limits: Mapping[str, object],
    authorization_path: Path,
    trusted_keys_path: Path,
    revocation_path: Path,
    repo_root: Path,
    expected_bindings: ExpectedBindings,
    approved_route: object,
    actual_tools: tuple[str, ...],
    admission_tool_schemas: tuple[tuple[str, str], ...],
    budget_scope: str,
    use_log_dir: Path,
    journal_path: Path,
    observed_bindings: Callable[[], ExpectedBindings],
    approved_tool_schemas: Mapping[str, str] | None = None,
    now: datetime | None = None,
    launcher_uid: int | None = None,
    launcher_instance_id: str | None = None,
    journal: RunAdmissionJournal,
) -> RunAdmissionContext:
    """Consume the Run's single authorization use and return the principal.

    The caller (trusted Launcher/entry) must invoke this **before** creating a
    Broker, Fake backend, Controller or any attempt.  A denial raises
    ``RunAdmissionError`` with a stable code and a tri-state ``consumed``; the
    broker/fake/controller must not be started on any denial.
    """
    moment = now or datetime.now(timezone.utc)
    if not isinstance(moment, datetime) or moment.tzinfo is None:
        raise RunAdmissionError(RUN_ADMISSION_INTERNAL, ("now_must_be_aware",))
    if not isinstance(identity, RunIdentity):
        raise RunAdmissionError(RUN_ADMISSION_IDENTITY_INVALID, ("identity_type",))
    uid = os.getuid() if launcher_uid is None else launcher_uid
    if type(uid) is not int or not 0 <= uid <= 0xFFFFFFFE:
        raise RunAdmissionError(RUN_ADMISSION_IDENTITY_INVALID, ("launcher_uid",))
    instance = launcher_instance_id or ("launch-" + uuid.uuid4().hex)
    if not isinstance(instance, str) or not _IDENTIFIER.fullmatch(instance):
        raise RunAdmissionError(RUN_ADMISSION_IDENTITY_INVALID,
                                ("launcher_instance_id",))

    # The Admission document hash is part of the trusted Run identity.
    try:
        admission_sha = _sha256_hex(_read_trusted_bytes(
            admission_path, repo_root=repo_root, label="admission",
            max_bytes=MAX_AUTHORIZATION_FILE_BYTES))
    except ValueError as error:
        raise RunAdmissionError(RUN_ADMISSION_IDENTITY_INVALID,
                                (f"ADMISSION_INVALID:{error}",)) from None
    if admission_sha != identity.admission_sha256:
        raise RunAdmissionError(RUN_ADMISSION_IDENTITY_INVALID,
                                ("admission_sha256_mismatch",))

    expected_digest = _sha256_hex(_canonical(expected_bindings.as_dict()))
    try:
        observed = observed_bindings()
    except Exception as error:  # noqa: BLE001 - observer must never be trusted
        raise RunAdmissionError(RUN_ADMISSION_AUTHORIZATION_INVALID,
                                (f"OBSERVER_FAILED:{type(error).__name__}",)) from None
    if not isinstance(observed, ExpectedBindings):
        raise RunAdmissionError(RUN_ADMISSION_AUTHORIZATION_INVALID,
                                ("OBSERVER_INVALID",))
    observed_digest = _sha256_hex(_canonical(observed.as_dict()))

    tool_set_sha256, tool_names = _tool_set_digest(admission_tool_schemas,
                                                   actual_tools,
                                                   approved_tool_schemas)
    if not isinstance(budget_scope, str) or not budget_scope:
        raise RunAdmissionError(RUN_ADMISSION_LIMITS_INVALID, ("budget_scope",))
    base_fields = _identity_audit_fields(
        identity, launcher_instance_id=instance, launcher_uid=uid)
    try:
        journal.append("intent", {
            **base_fields,
            "decision": "PENDING",
            "consumed": None,
            "admission_max_calls": admission_limits.get("max_calls"),
        })
    except RunAdmissionError as error:
        raise RunAdmissionError(RUN_ADMISSION_AUDIT_UNAVAILABLE,
                                error.reasons, consumed=CONSUMED_NO) from None

    authorization_file_sha256 = ""
    try:
        authorization_file_sha256 = _external_sha256(
            authorization_path, repo_root=repo_root, label="authorization")
    except RunAdmissionError:
        # load_execution_authorization will report the precise external-file
        # reason; the digest is only evidence and must not mask it.
        authorization_file_sha256 = ""

    load_kwargs: dict[str, Any] = {
        "authorization_path": authorization_path,
        "trusted_keys_path": trusted_keys_path,
        "revocation_path": revocation_path,
        "repo_root": repo_root,
        "expected": expected_bindings,
        "approved_route": approved_route,
        "actual_tools": actual_tools,
        "budget_scope": budget_scope,
        "now": moment,
        "checkpoint": "pre_start",
        "observed": observed,
    }
    decision = load_execution_authorization(**load_kwargs)
    if not decision.approved or decision.authorization is None:
        error = RunAdmissionError(
            RUN_ADMISSION_AUTHORIZATION_INVALID, tuple(decision.reasons),
            consumed=CONSUMED_NO)
        if authorization_file_sha256:
            fields = {
                **base_fields,
                "authorization_file_sha256": authorization_file_sha256,
                "expected_bindings_sha256": expected_digest,
                "observed_bindings_sha256": observed_digest,
            }
            _journal_deny(journal, fields, error.code, error.reasons,
                          consumed=CONSUMED_NO)
        raise error
    authorization = decision.authorization
    authorization_calls = int(getattr(authorization, "budget").max_calls)
    authorization_seconds = int(getattr(authorization, "deadline").total_seconds)
    effective_calls, effective_attempts, effective_seconds = _limits(
        admission_limits, authorization_calls=authorization_calls,
        authorization_seconds=authorization_seconds)
    deadline_utc = _utc_text(moment + timedelta(seconds=effective_seconds))

    # C2 TOCTOU: observe the authorized file again after the full load; a file
    # that changed while being verified must never be consumed.
    try:
        after_load_sha = _external_sha256(authorization_path,
                                          repo_root=repo_root,
                                          label="authorization")
    except RunAdmissionError as error:
        _journal_deny(journal, base_fields, error.code, error.reasons,
                      consumed=CONSUMED_NO)
        raise
    if after_load_sha != authorization_file_sha256:
        error = RunAdmissionError(RUN_ADMISSION_AUTHORIZATION_DRIFT,
                                  ("authorization_file_changed_before_consume",),
                                  consumed=CONSUMED_NO,
                                  record={"authorization_file_sha256":
                                          authorization_file_sha256})
        _journal_deny(journal, base_fields, error.code, error.reasons,
                      consumed=CONSUMED_NO)
        raise error

    consume_kwargs: dict[str, Any] = dict(load_kwargs)
    consume_kwargs.pop("now", None)
    consume_kwargs["checkpoint"] = "pre_reserve"
    try:
        consume_kwargs["observed"] = observed_bindings()
    except Exception as error:  # noqa: BLE001 - observer fail closed
        raise RunAdmissionError(RUN_ADMISSION_AUTHORIZATION_INVALID,
                                (f"OBSERVER_FAILED:{type(error).__name__}",)) from None
    try:
        use = consume_execution_authorization(
            use_log_dir=use_log_dir, run_epoch=identity.run_epoch,
            now=moment, **consume_kwargs)
    except AuthorizationRejected as error:
        reasons = tuple(str(reason) for reason in (
            getattr(error, "reasons", ()) or ("AUTHORIZATION_REJECTED",)))
        code, consumed = _map_consume_reasons(reasons)
        outcome = RunAdmissionError(code, reasons, consumed=consumed)
        fields = _outcome_fields(
            identity=identity, authorization=authorization,
            authorization_file_sha256=authorization_file_sha256,
            expected_digest=expected_digest, observed_digest=observed_digest,
            tool_set_sha256=tool_set_sha256, tool_names=tool_names,
            launcher_instance_id=instance, launcher_uid=uid,
            effective_calls=effective_calls,
            admission_calls=int(admission_limits["max_calls"]),
            authorization_calls=authorization_calls,
            deadline_utc=deadline_utc, decision="DENY", reasons=reasons,
            consumed=consumed, use_record_sha256=None,
            durability=("UNKNOWN" if consumed == CONSUMED_UNKNOWN else "KNOWN"))
        _journal_deny(journal, fields, outcome.code, outcome.reasons,
                      consumed=consumed)
        raise outcome from None

    # C2: the published use record must be exactly the one this Run loaded.
    drift: tuple[str, ...] = ()
    if not isinstance(use, AuthorizationUse):
        drift = ("authorization_use_type_invalid",)
    elif getattr(use, "authorization_id", None) != authorization.authorization_id:
        drift = ("authorization_id_mismatch",)
    elif getattr(use, "run_epoch", None) != identity.run_epoch:
        drift = ("run_epoch_mismatch",)
    else:
        expected_name = _sha256_hex(authorization.authorization_id.encode("ascii")) \
            + ".json"
        if Path(getattr(use, "record_path")).name != expected_name:
            drift = ("use_record_path_mismatch",)
    use_record_sha256: str | None = None
    try:
        use_record_sha256 = _sha256_hex(_read_trusted_bytes(
            Path(use.record_path), repo_root=repo_root, label="use record",
            max_bytes=MAX_USE_RECORD_BYTES))
    except (ValueError, RunAdmissionError):
        use_record_sha256 = None

    after_consume_sha = ""
    try:
        after_consume_sha = _external_sha256(authorization_path,
                                             repo_root=repo_root,
                                             label="authorization")
    except RunAdmissionError:
        after_consume_sha = ""
    if after_consume_sha != authorization_file_sha256 and not drift:
        drift = ("authorization_file_changed_after_consume",)
    if drift:
        code = RUN_ADMISSION_AUTHORIZATION_DRIFT
        outcome = RunAdmissionError(code, drift, consumed=CONSUMED_UNKNOWN,
                                    record={"authorization_file_sha256":
                                            authorization_file_sha256,
                                            "use_record_sha256": use_record_sha256})
        fields = _outcome_fields(
            identity=identity, authorization=authorization,
            authorization_file_sha256=authorization_file_sha256,
            expected_digest=expected_digest, observed_digest=observed_digest,
            tool_set_sha256=tool_set_sha256, tool_names=tool_names,
            launcher_instance_id=instance, launcher_uid=uid,
            effective_calls=effective_calls,
            admission_calls=int(admission_limits["max_calls"]),
            authorization_calls=authorization_calls,
            deadline_utc=deadline_utc, decision="DENY", reasons=drift,
            consumed=CONSUMED_UNKNOWN, use_record_sha256=use_record_sha256,
            durability="UNKNOWN")
        _journal_deny(journal, fields, outcome.code, outcome.reasons,
                      consumed=CONSUMED_UNKNOWN)
        raise outcome

    fields = _outcome_fields(
        identity=identity, authorization=authorization,
        authorization_file_sha256=authorization_file_sha256,
        expected_digest=expected_digest, observed_digest=observed_digest,
        tool_set_sha256=tool_set_sha256, tool_names=tool_names,
        launcher_instance_id=instance, launcher_uid=uid,
        effective_calls=effective_calls,
        admission_calls=int(admission_limits["max_calls"]),
        authorization_calls=authorization_calls,
        deadline_utc=deadline_utc, decision="ALLOW", reasons=(),
        consumed=CONSUMED_YES, use_record_sha256=use_record_sha256,
        durability="KNOWN")
    try:
        journal.append("outcome", fields)
    except RunAdmissionError as error:
        # The use is spent but the outcome record failed: no dispatch may
        # follow; a restart of the same Run will be classified as a replay and
        # needs manual reconciliation.
        raise RunAdmissionError(RUN_ADMISSION_AUDIT_UNAVAILABLE,
                                error.reasons, consumed=CONSUMED_YES) from None

    context = RunAdmissionContext(
        identity=identity,
        authorization_id=authorization.authorization_id,
        authorization_sha256=authorization_file_sha256,
        authorization_payload_sha256=_sha256_hex(authorization.payload_bytes),
        approver=authorization.approver,
        key_id=authorization.key_id,
        expected_bindings_sha256=expected_digest,
        observed_bindings_sha256=observed_digest,
        binding_checkpoint="pre_start",
        tool_set_sha256=tool_set_sha256,
        tool_names=tool_names,
        route_id=authorization.route.route_id,
        provider=authorization.route.provider,
        model=authorization.route.model,
        budget_scope=authorization.budget.scope,
        effective_max_calls=effective_calls,
        max_attempts=effective_attempts,
        run_deadline_seconds=effective_seconds,
        authorization_expires_utc=_utc_text(authorization.expires_utc),
        use_record_sha256=use_record_sha256,
        journal=journal,
        launcher_instance_id=instance,
        launcher_uid=uid,
    )
    context._authorization_calls = authorization_calls
    context._admission_calls = int(admission_limits["max_calls"])
    context._scope_id = _scope_from_tools(actual_tools)
    return context


def begin_run_admission(
    *,
    journal_path: Path,
    **kwargs: Any,
) -> RunAdmissionContext:
    """Public entry: own the journal lifecycle around the admission attempt."""
    supplied_journal = kwargs.pop("journal", None)
    journal = supplied_journal
    created = journal is None
    if created:
        journal = RunAdmissionJournal(journal_path)
    try:
        return _begin_run_admission_impl(journal_path=journal_path,
                                         journal=journal, **kwargs)
    except RunAdmissionError:
        if created:
            journal.close()
        raise


def _scope_from_tools(actual_tools: tuple[str, ...]) -> str:
    """Scope marker used only by the audit/token when the caller omits one."""
    return "scope-" + _sha256_hex(_canonical(sorted(actual_tools)))[:16]



__all__ = [
    "RunAdmissionContext",
    "RunAdmissionError",
    "RunAdmissionJournal",
    "RunIdentity",
    "DispatchAdmissionToken",
    "begin_run_admission",
    "build_run_identity",
    "derive_run_epoch",
    "RUN_ADMISSION_SCHEMA",
    "DISPATCH_TOKEN_SCHEMA",
    "RUN_ADMISSION_AUTHORIZATION_INVALID",
    "RUN_ADMISSION_ALREADY_CONSUMED",
    "RUN_ADMISSION_EPOCH_MISMATCH",
    "RUN_ADMISSION_RECORD_INVALID",
    "RUN_ADMISSION_LOG_UNAVAILABLE",
    "RUN_ADMISSION_DURABILITY_UNKNOWN",
    "RUN_ADMISSION_AUTHORIZATION_DRIFT",
    "RUN_ADMISSION_AUDIT_UNAVAILABLE",
    "RUN_ADMISSION_AUDIT_FULL",
    "RUN_ADMISSION_IDENTITY_INVALID",
    "RUN_ADMISSION_LIMITS_INVALID",
    "RUN_ADMISSION_TOOL_SCHEMA_MISMATCH",
    "RUN_ADMISSION_REQUIRED",
    "RUN_ADMISSION_NOT_ACTIVE",
    "RUN_ADMISSION_INTERNAL",
    "ADMISSION_TOKEN_UNKNOWN",
    "ADMISSION_TOKEN_REPLAYED",
    "ADMISSION_TOKEN_ORDER_INVALID",
    "ADMISSION_TOKEN_BINDING_MISMATCH",
    "ADMISSION_TOKEN_EXPIRED",
    "RUN_EPOCH_MISMATCH",
    "RUN_ADMISSION_INACTIVE",
    "RUN_DEADLINE_EXCEEDED",
    "RUN_BUDGET_CALLS_EXCEEDED",
]
