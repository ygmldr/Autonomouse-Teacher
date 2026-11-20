"""Fail-closed ExecutionAuthorization loading for a separately deployed controller.

Nothing in this module can be produced by the candidate Agent or by editing files
inside this repository. An authorization is accepted only when it is:

* a strict JSON document stored outside the repository tree,
* bound to the exact expected code/lock/runtime/plugin/merged-profile digests,
* bound to one approved route/model, exact tool registry, budget and deadline,
* signed with Ed25519 by a key pinned in an operator-supplied, repo-external key
  file, and
* not expired/not-yet-valid/revoked according to an external revocation file.

A repository Markdown approval, environment variable, ``--live`` flag or
self-signed/in-repo JSON never reaches this loader; they cannot satisfy the
external-file and pinned-key requirements. Any missing/failed check yields a
deny decision and ``require_execution_authorization`` raises ``SecurityBlocked``.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import errno
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
from stat import S_ISDIR, S_ISREG, S_IWGRP, S_IWOTH
import time
from typing import Any, Mapping

from autoteacher_m0.contracts import ErrorCode, RuntimeFailure

from . import ed25519

AUTHORIZATION_SCHEMA = "at-m0/execution-authorization/v1"
MAX_AUTHORIZATION_BYTES = 64 * 1024
MAX_KEYS_BYTES = 16 * 1024
MAX_REVOCATION_BYTES = 64 * 1024
MAX_BUDGET_POLICY_BYTES = 16 * 1024
MAX_USE_RECORD_BYTES = 4 * 1024
MAX_AUTHORIZATION_USES = 4096
# A publisher crash can leave at most one temporary file per interrupted call.
# Temps are never use records: the capacity count above deliberately ignores
# them, they have their own bound, and stale ones are reaped so crash residue
# can neither block nor deny service indefinitely.
MAX_USE_RECORD_TEMPS = 256
_USE_RECORD_TEMP_PREFIX = ".use-record-tmp-"
_USE_RECORD_TEMP_SUFFIX = ".tmp"
_USE_RECORD_TEMP_TTL_SECONDS = 300
# A record is published atomically, so an existing record is already complete.
# The bounded retry only keeps the replay classification stable if a record
# written by an older (non-atomic) publisher is still settling; a persistently
# malformed/replaced record still fails closed with USE_RECORD_INVALID.
_USE_RECORD_READ_ATTEMPTS = 5
_USE_RECORD_READ_DELAY_SECONDS = 0.01
# Host uid of the G3-D candidate process (uid_map 0 65534 1). A trusted file
# owned by this uid, or writable by group/other, is candidate-writable.
CANDIDATE_HOST_UID = 65534
ALLOWED_TOOLS = frozenset({"skill_lookup"})
BINDING_NAMES = (
    "code_sha256",
    "lock_sha256",
    "runtime_sha256",
    "plugin_sha256",
    "merged_profile_sha256",
)
# The v1 authorization has exactly these five binding fields. Each one is the
# aggregate root of one named group of runtime-relevant inputs; every component
# must appear in exactly one group so no runtime input can be left unbound.
BINDING_CLOSURE: Mapping[str, tuple[str, ...]] = {
    "code_sha256": (
        "trusted_controller",
        "trusted_broker",
        "egress_boundary",
        "candidate_adapter",
        "security_primitives",
    ),
    "lock_sha256": (
        "dependency_lock",
        "runtime_dependencies",
    ),
    "runtime_sha256": (
        "runtime_binary",
        "candidate_stage",
    ),
    "plugin_sha256": (
        "plugin_tree",
        "tool_registry_schema",
    ),
    "merged_profile_sha256": (
        "merged_profile",
        "route_policy",
        "budget_policy",
        "price_snapshot",
    ),
}
BINDING_COMPONENTS = tuple(
    component for root in BINDING_NAMES for component in BINDING_CLOSURE.get(root, ()))
# A dispatch admission must re-check the bindings at all three points; one
# pre-start check is explicitly not enough.
TOCTOU_CHECKPOINTS = ("pre_start", "pre_reserve", "pre_dispatch")
_USE_LOG_SCHEMA = "at-m0/authorization-use/v1"
_DIGEST = re.compile(r"[a-f0-9]{64}\Z")
_IDENTIFIER = re.compile(r"[A-Za-z0-9._:-]{1,128}\Z")
_USD = re.compile(r"(?:0|[1-9][0-9]{0,5})(?:\.[0-9]{1,6})?\Z")
_POLICY_KEY = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
_POLICY_SCALAR = re.compile(r"[A-Za-z0-9_.:-]{1,64}\Z")
_POLICY_NUMBER = re.compile(r"(?:0|[1-9][0-9]{0,9})(?:\.[0-9]{1,6})?\Z")
_POLICY_INTEGER = re.compile(r"(?:0|[1-9][0-9]{0,9})\Z")
_UTC_TEXT = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z\Z")
_MAX_AUTHORIZATION_LIFETIME = timedelta(hours=24)
_MAX_ISSUED_AGE = timedelta(days=7)
BUDGET_POLICY_KEYS = (
    "soft_total_usd",
    "hard_total_usd",
    "soft_call_usd",
    "hard_call_usd",
    "max_live_requests",
    "max_steps_per_task",
    "max_retries_per_task",
    "max_input_tokens",
    "max_output_tokens",
    "live_pricing_snapshot",
)
UNVERIFIED_PRICE_SNAPSHOT = "REQUIRED_UNVERIFIED"


class AuthorizationRejected(RuntimeFailure):
    """Sanitized denial; the code is always SECURITY_BLOCKED."""

    def __init__(self, reasons: tuple[str, ...]):
        super().__init__(ErrorCode.SECURITY_BLOCKED, "; ".join(reasons) or "AUTHORIZATION_REJECTED")
        self.reasons = reasons


class _DuplicateKey(ValueError):
    pass


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    seen: dict[str, Any] = {}
    for key, value in pairs:
        if key in seen:
            raise _DuplicateKey(f"duplicate key: {key}")
        seen[key] = value
    return seen


def _parse_json_object(raw: bytes, *, label: str) -> dict[str, Any]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"{label} is not UTF-8 JSON") from error
    if text.lstrip().startswith("#"):
        raise ValueError(f"{label} looks like Markdown, not a signed JSON document")
    try:
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicates,
            parse_float=Decimal,
            parse_constant=lambda token: (_ for _ in ()).throw(ValueError(f"invalid {token}")),
        )
    except (ValueError, InvalidOperation) as error:
        raise ValueError(f"{label} is not strict JSON: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _require_private_node(info: os.stat_result, *, label: str) -> None:
    """Reject candidate-writable nodes: group/other write or candidate ownership."""
    if info.st_mode & (S_IWGRP | S_IWOTH):
        raise ValueError(f"{label} must not be group/world writable")
    if info.st_uid == CANDIDATE_HOST_UID:
        raise ValueError(f"{label} is owned by the candidate host uid")


def _trusted_directory(directory: Path, *, repo_root: Path, label: str) -> Path:
    """Resolve an operator-controlled directory that the candidate cannot write."""
    if not isinstance(directory, Path) or not directory.is_absolute():
        raise ValueError(f"{label} directory must be absolute")
    if directory.is_symlink():
        raise ValueError(f"{label} directory must not be a symlink")
    try:
        resolved = directory.resolve(strict=True)
        root = repo_root.resolve(strict=True)
    except OSError as error:
        raise ValueError(f"{label} directory does not exist") from error
    if resolved.is_relative_to(root):
        raise ValueError(f"{label} must live outside the repository")
    try:
        info = resolved.stat()
    except OSError as error:
        raise ValueError(f"{label} directory is unreadable") from error
    if not S_ISDIR(info.st_mode):
        raise ValueError(f"{label} must be a directory")
    _require_private_node(info, label=f"{label} directory")
    return resolved


def _external_regular_file(path: Path, *, repo_root: Path, label: str,
                           max_bytes: int) -> bytes:
    """Read one strict external file without following links or trusting a path race.

    The trusted location is an operator-owned directory outside the repository
    that is neither group/other writable nor owned by the candidate uid. The
    final open uses ``O_NOFOLLOW`` and re-checks the opened descriptor, so a
    last-moment symlink or file-type swap cannot redirect the read.
    """
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
    _trusted_directory(resolved.parent, repo_root=root, label=label)
    try:
        descriptor = os.open(resolved, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as error:
        raise ValueError(f"{label} is unreadable") from error
    try:
        info = os.fstat(descriptor)
        if not S_ISREG(info.st_mode):
            raise ValueError(f"{label} must be a regular file")
        _require_private_node(info, label=label)
        if info.st_size <= 0 or info.st_size > max_bytes:
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


def _require_text(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 512:
        raise ValueError(f"{field} must be a nonempty string of at most 512 chars")
    return value


def _require_sha(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not _DIGEST.fullmatch(value):
        raise ValueError(f"{field} must be a lowercase sha256 digest")
    return value


def _require_utc(value: Any, *, field: str) -> datetime:
    if not isinstance(value, str) or not _UTC_TEXT.fullmatch(value):
        raise ValueError(f"{field} must be an RFC3339 UTC timestamp")
    parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return parsed


def _require_int(value: Any, *, field: str) -> int:
    """Strict JSON integer admission: no bool/float/str/Decimal coercion."""
    if type(value) is not int:
        raise ValueError(f"{field} must be a JSON integer")
    return value


def _require_usd(value: Any, *, field: str) -> Decimal:
    if not isinstance(value, str) or not _USD.fullmatch(value):
        raise ValueError(f"{field} must be a plain decimal string such as 0.10")
    amount = Decimal(value)
    if not amount.is_finite() or amount <= 0:
        raise ValueError(f"{field} must be positive")
    return amount


@dataclass(frozen=True)
class ExpectedBindings:
    code_sha256: str
    lock_sha256: str
    runtime_sha256: str
    plugin_sha256: str
    merged_profile_sha256: str

    def as_dict(self) -> dict[str, str]:
        return {name: getattr(self, name) for name in BINDING_NAMES}

    def mismatches(self, observed: "ExpectedBindings") -> tuple[str, ...]:
        """Stable per-root mismatch codes; never mutates either binding set."""
        return tuple(f"{name.upper()}_MISMATCH" for name in BINDING_NAMES
                     if getattr(self, name) != getattr(observed, name))

    @classmethod
    def from_closure(cls, components: Mapping[str, str]) -> "ExpectedBindings":
        """Derive the five v1 roots from the complete component closure."""
        return cls(**closure_digests(components))


@dataclass(frozen=True)
class ApprovedRoute:
    route_id: str
    provider: str
    model: str


@dataclass(frozen=True)
class BudgetLimits:
    scope: str
    per_call_cap_usd: Decimal
    total_cap_usd: Decimal
    max_calls: int


@dataclass(frozen=True)
class DeadlineLimits:
    total_seconds: int
    max_steps: int
    max_dispatch_attempts: int


@dataclass(frozen=True)
class ExecutionAuthorization:
    authorization_id: str
    approver: str
    issued_utc: datetime
    not_before_utc: datetime
    expires_utc: datetime
    bindings: ExpectedBindings
    route: ApprovedRoute
    allowed_tools: tuple[str, ...]
    budget: BudgetLimits
    deadline: DeadlineLimits
    key_id: str
    signature: bytes
    payload_bytes: bytes


@dataclass(frozen=True)
class AuthorizationDecision:
    """Inspection result.

    ``approved`` only means the offline authorization document verifies. It is
    deliberately not a dispatch permission: ``billable_send_authorized`` can
    never be true in this module, and ``LiveGate``/CLI/Adapter still block.
    """

    approved: bool
    reasons: tuple[str, ...]
    authorization: ExecutionAuthorization | None
    signature_valid: bool = False
    billable_send_authorized: bool = False

    def __post_init__(self) -> None:
        if self.billable_send_authorized:
            raise ValueError("this module can never authorize a billable send")

    def require(self) -> ExecutionAuthorization:
        if not self.approved or self.authorization is None:
            raise AuthorizationRejected(self.reasons or ("AUTHORIZATION_REJECTED",))
        return self.authorization


def _canonical_payload(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("utf-8")


def _validate_binding_closure() -> None:
    """Import-time guard: every v1 root has components and no component is unbound."""
    if set(BINDING_CLOSURE) != set(BINDING_NAMES):
        raise RuntimeError("binding closure must cover exactly the v1 binding roots")
    seen: list[str] = []
    for root in BINDING_NAMES:
        names = BINDING_CLOSURE[root]
        if not names:
            raise RuntimeError(f"binding root {root} has no components")
        seen.extend(names)
    if len(seen) != len(set(seen)):
        raise RuntimeError("a binding component may belong to only one root")
    for name in seen:
        if (not isinstance(name, str) or not _IDENTIFIER.fullmatch(name)
                or name != name.lower()):
            raise RuntimeError(f"invalid binding component name: {name!r}")


_validate_binding_closure()


def inventory_digest(files: Mapping[str, bytes]) -> str:
    """Deterministic digest of an explicit ``relative path -> bytes`` inventory."""
    if not isinstance(files, Mapping) or not files:
        raise ValueError("an inventory digest requires a nonempty file map")
    entries: list[list[str]] = []
    for name, content in files.items():
        if not isinstance(name, str) or not isinstance(content, bytes):
            raise TypeError("inventory entries must be (str, bytes)")
        path = PurePosixPath(name)
        if (not name or path.is_absolute() or ".." in path.parts or "\\" in name
                or path.as_posix() != name):
            raise ValueError("inventory paths must be normalized relative POSIX paths")
        entries.append([name, hashlib.sha256(content).hexdigest()])
    entries.sort(key=lambda item: item[0])
    return hashlib.sha256(_canonical_payload(entries)).hexdigest()


def closure_digests(components: Mapping[str, str]) -> dict[str, str]:
    """Derive the five v1 binding roots from the complete component closure.

    Missing or extra components are rejected: a partial, candidate-selected
    inventory must never be able to produce an accepted binding set.
    """
    if not isinstance(components, Mapping):
        raise TypeError("components must be a mapping")
    if set(components) != set(BINDING_COMPONENTS):
        missing = sorted(set(BINDING_COMPONENTS) - set(components))
        extra = sorted(set(components) - set(BINDING_COMPONENTS))
        raise ValueError("closure inventory must cover exactly the declared components; "
                         f"missing={missing} extra={extra}")
    for name in BINDING_COMPONENTS:
        _require_sha(components[name], field=f"binding component {name}")
    return {
        root: hashlib.sha256(_canonical_payload(
            {name: components[name] for name in BINDING_CLOSURE[root]})).hexdigest()
        for root in BINDING_NAMES
    }


def binding_drift(checkpoint: str, *, approved: ExpectedBindings,
                  observed: ExpectedBindings) -> tuple[str, ...]:
    """Re-check the approved bindings at one mandatory TOCTOU checkpoint."""
    if checkpoint not in TOCTOU_CHECKPOINTS:
        raise ValueError(f"checkpoint must be one of {TOCTOU_CHECKPOINTS}")
    if not isinstance(approved, ExpectedBindings) or not isinstance(observed, ExpectedBindings):
        raise TypeError("approved and observed must be ExpectedBindings")
    return tuple(f"BINDING_DRIFT:{checkpoint.upper()}:{reason}"
                 for reason in approved.mismatches(observed))


def _load_trusted_keys(raw: bytes) -> dict[str, bytes]:
    parsed = _parse_json_object(raw, label="trusted approval keys")
    keys = parsed.get("keys")
    if parsed.keys() - {"schema", "keys"} or not isinstance(keys, dict) or not keys:
        raise ValueError("trusted approval keys must be {'keys': {key_id: hex_public_key}}")
    result: dict[str, bytes] = {}
    for key_id, encoded in keys.items():
        if not isinstance(key_id, str) or not _IDENTIFIER.fullmatch(key_id):
            raise ValueError("trusted key id is invalid")
        if not isinstance(encoded, str) or not re.fullmatch(r"[a-f0-9]{64}", encoded):
            raise ValueError("trusted key must be a 32-byte lowercase hex public key")
        public = bytes.fromhex(encoded)
        if not ed25519.is_valid_public_key(public):
            raise ValueError("trusted key is not a strict prime-order Ed25519 point")
        result[key_id] = public
    return result


def _revoked_ids(raw: bytes) -> frozenset[str]:
    parsed = _parse_json_object(raw, label="revocation state")
    if parsed.keys() - {"schema", "revoked_ids"}:
        raise ValueError("revocation state has unknown fields")
    ids = parsed.get("revoked_ids")
    if not isinstance(ids, list) or any(not isinstance(item, str) for item in ids):
        raise ValueError("revocation state must contain a revoked_ids list")
    return frozenset(ids)


def load_execution_authorization(*, authorization_path: Path, trusted_keys_path: Path,
                                 revocation_path: Path, repo_root: Path,
                                 expected: ExpectedBindings, approved_route: ApprovedRoute,
                                 actual_tools: tuple[str, ...], budget_scope: str,
                                 now: datetime | None = None,
                                 observed: ExpectedBindings | None = None,
                                 checkpoint: str = "pre_start"
                                 ) -> AuthorizationDecision:
    """Return a deny decision unless every external-human check passes.

    ``expected`` is the approved binding set; ``observed`` is an optional
    independently recomputed set. ``checkpoint`` names the TOCTOU point the
    observation was taken at; any drift is reported and denies the decision.
    """
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    reasons: list[str] = []
    try:
        raw = _external_regular_file(authorization_path, repo_root=repo_root,
                                     label="authorization", max_bytes=MAX_AUTHORIZATION_BYTES)
        keys_raw = _external_regular_file(trusted_keys_path, repo_root=repo_root,
                                          label="trusted keys", max_bytes=MAX_KEYS_BYTES)
        revocation_raw = _external_regular_file(revocation_path, repo_root=repo_root,
                                                label="revocation state",
                                                max_bytes=MAX_REVOCATION_BYTES)
        payload = _parse_json_object(raw, label="authorization")
        trusted_keys = _load_trusted_keys(keys_raw)
        revoked = _revoked_ids(revocation_raw)
    except ValueError as error:
        return AuthorizationDecision(False, (f"EXTERNAL_AUTHORIZATION_INVALID:{error}",), None)

    required = {"schema", "authorization_id", "approver", "approval_note", "issued_utc",
                "not_before_utc", "expires_utc", "bindings", "route", "allowed_tools",
                "budget", "deadline", "signature"}
    if payload.keys() != required:
        return AuthorizationDecision(False, ("AUTHORIZATION_SCHEMA_FIELDS_INVALID",), None)

    if payload["schema"] != AUTHORIZATION_SCHEMA:
        reasons.append("AUTHORIZATION_SCHEMA_UNKNOWN")
    approval_note = payload["approval_note"]
    if not isinstance(approval_note, str) or len(approval_note) > 2000:
        reasons.append("APPROVAL_NOTE_INVALID")
    authorization_id = payload["authorization_id"]
    if not isinstance(authorization_id, str) or not _IDENTIFIER.fullmatch(authorization_id):
        reasons.append("AUTHORIZATION_ID_INVALID")
        authorization_id = ""
    # AUTH-06: approver and timestamps are parsed independently so any failure
    # yields a deny decision instead of leaving an unbound variable to crash later.
    approver = ""
    try:
        approver = _require_text(payload["approver"], field="approver")
    except ValueError:
        reasons.append("APPROVER_INVALID")
    issued = not_before = expires = moment
    time_known = True
    try:
        issued = _require_utc(payload["issued_utc"], field="issued_utc")
        not_before = _require_utc(payload["not_before_utc"], field="not_before_utc")
        expires = _require_utc(payload["expires_utc"], field="expires_utc")
        if not (issued <= not_before < expires):
            reasons.append("AUTHORIZATION_TIME_WINDOW_INVALID")
        if expires - issued > _MAX_AUTHORIZATION_LIFETIME:
            reasons.append("AUTHORIZATION_LIFETIME_TOO_LONG")
        if issued < moment - _MAX_ISSUED_AGE:
            reasons.append("AUTHORIZATION_TOO_OLD")
    except ValueError:
        reasons.append("AUTHORIZATION_TIME_INVALID")
        time_known = False
        issued = not_before = expires = moment

    bindings_payload = payload["bindings"]
    actual_bindings = expected.as_dict()
    if not isinstance(bindings_payload, dict) or set(bindings_payload) != set(BINDING_NAMES):
        reasons.append("BINDING_FIELDS_INVALID")
        bindings = ExpectedBindings(*("", ) * 5)  # type: ignore[arg-type]
    else:
        try:
            bindings = ExpectedBindings(**{name: _require_sha(bindings_payload[name], field=name)
                                           for name in BINDING_NAMES})
        except ValueError:
            reasons.append("BINDING_DIGESTS_INVALID")
            bindings = ExpectedBindings(*("", ) * 5)  # type: ignore[arg-type]
    for name in BINDING_NAMES:
        if getattr(bindings, name) != actual_bindings[name]:
            reasons.append(f"{name.upper()}_MISMATCH")
    if observed is not None:
        if not isinstance(observed, ExpectedBindings):
            raise TypeError("observed must be ExpectedBindings")
        reasons.extend(binding_drift(checkpoint, approved=expected, observed=observed))

    route_payload = payload["route"]
    if not isinstance(route_payload, dict) or set(route_payload) != {"route_id", "provider",
                                                                     "model"}:
        reasons.append("ROUTE_FIELDS_INVALID")
        route = ApprovedRoute("", "", "")
    else:
        try:
            route = ApprovedRoute(*(_require_text(route_payload[name], field=name)
                                    for name in ("route_id", "provider", "model")))
        except ValueError:
            reasons.append("ROUTE_FIELDS_INVALID")
            route = ApprovedRoute("", "", "")
    if route != approved_route:
        reasons.append("ROUTE_NOT_APPROVED")

    tools = payload["allowed_tools"]
    if not isinstance(tools, list) or any(not isinstance(item, str) for item in tools):
        reasons.append("ALLOWED_TOOLS_INVALID")
        allowed_tools: tuple[str, ...] = ()
    else:
        allowed_tools = tuple(tools)
        if len(set(allowed_tools)) != len(allowed_tools):
            reasons.append("ALLOWED_TOOLS_INVALID")
        if not allowed_tools or not set(allowed_tools) <= ALLOWED_TOOLS:
            reasons.append("ALLOWED_TOOLS_NOT_PERMITTED")
    if tuple(sorted(allowed_tools)) != tuple(sorted(actual_tools)):
        reasons.append("ACTUAL_TOOL_REGISTRY_NOT_APPROVED")

    budget_payload = payload["budget"]
    if not isinstance(budget_payload, dict) or set(budget_payload) != {
            "scope", "per_call_cap_usd", "total_cap_usd", "max_calls"}:
        reasons.append("BUDGET_FIELDS_INVALID")
        budget = BudgetLimits("", Decimal("0"), Decimal("0"), 0)
    else:
        try:
            budget = BudgetLimits(
                _require_text(budget_payload["scope"], field="budget.scope"),
                _require_usd(budget_payload["per_call_cap_usd"], field="per_call_cap_usd"),
                _require_usd(budget_payload["total_cap_usd"], field="total_cap_usd"),
                _require_int(budget_payload["max_calls"], field="max_calls"),
            )
            if budget.scope != budget_scope:
                reasons.append("BUDGET_SCOPE_MISMATCH")
            if not 1 <= budget.max_calls <= 50:
                reasons.append("MAX_CALLS_OUT_OF_RANGE")
            if budget.per_call_cap_usd > budget.total_cap_usd:
                reasons.append("PER_CALL_CAP_EXCEEDS_TOTAL_CAP")
            if budget.total_cap_usd > Decimal("10"):
                reasons.append("TOTAL_CAP_EXCEEDS_HARD_BUDGET")
        except (ValueError, TypeError, InvalidOperation):
            reasons.append("BUDGET_VALUES_INVALID")
            budget = BudgetLimits("", Decimal("0"), Decimal("0"), 0)

    deadline_payload = payload["deadline"]
    if not isinstance(deadline_payload, dict) or set(deadline_payload) != {
            "total_seconds", "max_steps", "max_dispatch_attempts"}:
        reasons.append("DEADLINE_FIELDS_INVALID")
        deadline = DeadlineLimits(0, 0, 0)
    else:
        try:
            deadline = DeadlineLimits(
                _require_int(deadline_payload["total_seconds"], field="total_seconds"),
                _require_int(deadline_payload["max_steps"], field="max_steps"),
                _require_int(deadline_payload["max_dispatch_attempts"],
                             field="max_dispatch_attempts"),
            )
            if not (1 <= deadline.total_seconds <= 3600
                    and 1 <= deadline.max_steps <= 200
                    and 1 <= deadline.max_dispatch_attempts <= 50):
                reasons.append("DEADLINE_OUT_OF_RANGE")
        except (ValueError, TypeError):
            reasons.append("DEADLINE_VALUES_INVALID")
            deadline = DeadlineLimits(0, 0, 0)

    signature_payload = payload["signature"]
    if (not isinstance(signature_payload, dict)
            or set(signature_payload) != {"algorithm", "key_id", "value"}):
        reasons.append("SIGNATURE_FIELDS_INVALID")
        key_id = ""
        signature = b""
    else:
        key_id = signature_payload["key_id"]
        encoded_signature = signature_payload["value"]
        if signature_payload["algorithm"] != "ed25519":
            reasons.append("SIGNATURE_ALGORITHM_NOT_APPROVED")
        if (not isinstance(key_id, str) or not _IDENTIFIER.fullmatch(key_id)
                or not isinstance(encoded_signature, str)
                or not re.fullmatch(r"[a-f0-9]{128}", encoded_signature)):
            reasons.append("SIGNATURE_ENCODING_INVALID")
            key_id = ""
            signature = b""
        else:
            signature = bytes.fromhex(encoded_signature)

    payload_without_signature = {key: value for key, value in payload.items()
                                 if key != "signature"}
    try:
        signed_bytes = _canonical_payload(payload_without_signature)
    except (TypeError, ValueError):
        reasons.append("AUTHORIZATION_NOT_CANONICAL")
        signed_bytes = b""
    public_key = trusted_keys.get(key_id) if isinstance(key_id, str) else None
    signature_valid = False
    if public_key is None:
        reasons.append("UNKNOWN_APPROVAL_KEY")
    else:
        signature_valid = bool(signature) and ed25519.verify(public_key, signed_bytes, signature)
        if not signature_valid:
            reasons.append("HUMAN_SIGNATURE_INVALID")

    if not (not_before <= moment < expires):
        reasons.append("AUTHORIZATION_NOT_CURRENT")
        if time_known:
            # No clock-skew allowance: a verifier clock even slightly before
            # not_before or at/after expiry is a deny, not a tolerance case.
            reasons.append("AUTHORIZATION_EXPIRED" if moment >= expires
                           else "AUTHORIZATION_NOT_YET_VALID")
    if authorization_id in revoked:
        reasons.append("AUTHORIZATION_REVOKED")

    authorization = ExecutionAuthorization(
        authorization_id=authorization_id, approver=approver, issued_utc=issued,
        not_before_utc=not_before, expires_utc=expires, bindings=bindings, route=route,
        allowed_tools=allowed_tools, budget=budget, deadline=deadline, key_id=key_id,
        signature=signature, payload_bytes=signed_bytes,
    )
    approved = not reasons
    return AuthorizationDecision(approved, tuple(dict.fromkeys(reasons)),
                                 authorization if approved else None, signature_valid)


def require_execution_authorization(**kwargs: Any) -> ExecutionAuthorization:
    """Fail-closed convenience wrapper; no retry and no partial approval."""
    return load_execution_authorization(**kwargs).require()


# ---------------------------------------------------------------------------
# Budget authority: config/budgets.yaml is an agent-writable declarative mirror,
# never the authority. The frozen constants live in code (and are bound through
# code_sha256); this parser only makes disagreement impossible to ignore.
# ---------------------------------------------------------------------------
def parse_budget_policy(raw: bytes) -> dict[str, str]:
    """Parse the frozen flat M0 budget file with no YAML coercion or ambiguity."""
    if not isinstance(raw, bytes) or not raw:
        raise ValueError("budget policy is empty")
    if len(raw) > MAX_BUDGET_POLICY_BYTES:
        raise ValueError("budget policy is too large")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("budget policy is not UTF-8") from error
    policy: dict[str, str] = {}
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "\t" in line:
            raise ValueError(f"budget policy line {number} contains a tab")
        key, separator, value = line.partition(":")
        if not separator:
            raise ValueError(f"budget policy line {number} is not a key/value entry")
        key, value = key.strip(), value.strip()
        if not _POLICY_KEY.fullmatch(key):
            raise ValueError(f"budget policy line {number} has an invalid key")
        if key not in BUDGET_POLICY_KEYS:
            raise ValueError(f"budget policy has an unknown field: {key}")
        if key in policy:
            raise ValueError(f"budget policy repeats {key}")
        if not _POLICY_SCALAR.fullmatch(value):
            raise ValueError(f"budget policy value for {key} is not a plain scalar")
        policy[key] = value
    missing = [key for key in BUDGET_POLICY_KEYS if key not in policy]
    if missing:
        raise ValueError("budget policy is missing fields: " + ",".join(missing))
    return policy


_NUMERIC_POLICY_FIELDS = (
    "soft_total_usd",
    "hard_total_usd",
    "soft_call_usd",
    "hard_call_usd",
    "max_live_requests",
    "max_steps_per_task",
    "max_retries_per_task",
    "max_input_tokens",
    "max_output_tokens",
)


def budget_policy_drift_reasons(policy: Mapping[str, str], *, expected: BudgetLimits,
                                soft_call_cap_usd: Decimal,
                                soft_total_cap_usd: Decimal) -> tuple[str, ...]:
    """Compare the declarative budget file to the frozen constants; never ignore drift."""
    reasons: list[str] = []
    numeric: dict[str, Decimal] = {}
    for key in _NUMERIC_POLICY_FIELDS:
        value = policy.get(key)
        pattern = _POLICY_INTEGER if key.startswith("max_") else _POLICY_NUMBER
        if not isinstance(value, str) or not pattern.fullmatch(value):
            reasons.append(f"BUDGET_POLICY_VALUE_INVALID:{key}")
            continue
        numeric[key] = Decimal(value)
    comparisons = (
        ("hard_call_usd", expected.per_call_cap_usd),
        ("hard_total_usd", expected.total_cap_usd),
        ("max_live_requests", Decimal(expected.max_calls)),
        ("soft_call_usd", soft_call_cap_usd),
        ("soft_total_usd", soft_total_cap_usd),
    )
    for key, frozen in comparisons:
        if key in numeric and numeric[key] != frozen:
            reasons.append(f"BUDGET_POLICY_DRIFT:{key}")
    snapshot = policy.get("live_pricing_snapshot")
    if snapshot == UNVERIFIED_PRICE_SNAPSHOT:
        reasons.append("LIVE_PRICING_SNAPSHOT_UNVERIFIED")
    else:
        # G4-A cannot verify any price source; claiming one is itself a denial.
        reasons.append("BUDGET_POLICY_PRICE_SNAPSHOT_UNSUPPORTED")
    return tuple(dict.fromkeys(reasons))


# ---------------------------------------------------------------------------
# Single-use authorization contract (replay / run-epoch)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class AuthorizationUse:
    authorization_id: str
    run_epoch: str
    consumed_utc: str
    record_path: Path


def _read_use_record(path: Path, *,
                     expected_authorization_id: str) -> tuple[str, str]:
    """Read one complete use record, or fail closed with a precise reason.

    Publication is atomic, so an existing record is already complete. The read
    itself still validates the node: ``O_NOFOLLOW`` rejects a symlink,
    ``O_NONBLOCK`` keeps a FIFO/device from blocking the reader (a no-op for a
    regular file), the size bound rejects partial/oversized documents,
    ``nlink > 2`` rejects a record that has been hardlinked elsewhere
    (``nlink == 2`` is tolerated because a crash between link and temp cleanup
    leaves the final plus its own temp), and a group/world-writable record is
    never trusted.

    The body is additionally cross-checked against its own storage name and
    against the authorization the caller verified (G4-R P2-01): the body
    ``authorization_id`` must obey the same identifier rule as the signed
    authorization, must hash to ``sha256(id) + ".json"`` (this record's final
    name), and must equal ``expected_authorization_id``. Any mismatch is a
    stable ``AUTHORIZATION_USE_RECORD_INVALID``: a foreign or mismatched record
    is never reported as a real replay. ``consumed_utc`` must also use the one
    UTC form the publisher writes. Returns ``(authorization_id, run_epoch)``.
    """
    if (not isinstance(expected_authorization_id, str)
            or not _IDENTIFIER.fullmatch(expected_authorization_id)):
        raise AuthorizationRejected(("AUTHORIZATION_USE_RECORD_INVALID",))
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
                             | os.O_CLOEXEC)
    except OSError as error:
        if error.errno == errno.ELOOP:
            raise AuthorizationRejected(("AUTHORIZATION_USE_RECORD_INVALID",)) from None
        raise AuthorizationRejected(("AUTHORIZATION_USE_RECORD_UNREADABLE",)) from None
    try:
        info = os.fstat(descriptor)
        if (not S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_USE_RECORD_BYTES
                or info.st_nlink > 2 or info.st_mode & (S_IWGRP | S_IWOTH)):
            raise AuthorizationRejected(("AUTHORIZATION_USE_RECORD_INVALID",))
        chunks: list[bytes] = []
        remaining = MAX_USE_RECORD_BYTES + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(remaining, 65536))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
    except OSError:
        raise AuthorizationRejected(("AUTHORIZATION_USE_RECORD_UNREADABLE",)) from None
    finally:
        os.close(descriptor)
    raw = b"".join(chunks)
    if len(raw) != info.st_size:
        raise AuthorizationRejected(("AUTHORIZATION_USE_RECORD_INVALID",))
    try:
        parsed = _parse_json_object(raw, label="authorization use record")
    except ValueError:
        raise AuthorizationRejected(("AUTHORIZATION_USE_RECORD_INVALID",)) from None
    authorization_id = parsed.get("authorization_id")
    epoch = parsed.get("run_epoch")
    consumed_utc = parsed.get("consumed_utc")
    if (set(parsed) != {"schema", "authorization_id", "run_epoch", "consumed_utc"}
            or parsed.get("schema") != _USE_LOG_SCHEMA
            or not isinstance(authorization_id, str)
            or not _IDENTIFIER.fullmatch(authorization_id)
            or not isinstance(epoch, str) or not _IDENTIFIER.fullmatch(epoch)
            or not isinstance(consumed_utc, str)
            or not _UTC_TEXT.fullmatch(consumed_utc)):
        raise AuthorizationRejected(("AUTHORIZATION_USE_RECORD_INVALID",))
    expected_name = (hashlib.sha256(authorization_id.encode("ascii")).hexdigest()
                     + ".json")
    if path.name != expected_name or authorization_id != expected_authorization_id:
        # Body id, storage name and the verified authorization must all agree;
        # a mismatch is corruption, not a replay.
        raise AuthorizationRejected(("AUTHORIZATION_USE_RECORD_INVALID",))
    return authorization_id, epoch


def _read_use_record_settled(path: Path, *,
                             expected_authorization_id: str) -> tuple[str, str]:
    """Read a record, tolerating a transiently partial legacy publisher.

    Records published by this module are complete before they become visible, so
    the retry can only matter for a record produced by the old create-then-write
    publisher that is still settling. It can never weaken a decision: a record
    that stays malformed, foreign to this path/authorization, symlinked or
    replaced still fails closed with ``AUTHORIZATION_USE_RECORD_INVALID``.
    """
    attempts = max(1, _USE_RECORD_READ_ATTEMPTS)
    for attempt in range(attempts):
        try:
            return _read_use_record(
                path, expected_authorization_id=expected_authorization_id)
        except AuthorizationRejected as error:
            if (attempt + 1 >= attempts
                    or error.reasons != ("AUTHORIZATION_USE_RECORD_INVALID",)
                    or path.is_symlink()):
                raise
            time.sleep(_USE_RECORD_READ_DELAY_SECONDS)
    raise AuthorizationRejected(("AUTHORIZATION_USE_RECORD_INVALID",))  # pragma: no cover


def _replay_reason(previous_epoch: str, run_epoch: str) -> str:
    return ("AUTHORIZATION_EPOCH_MISMATCH" if previous_epoch != run_epoch
            else "AUTHORIZATION_REPLAYED")


def _use_record_temp_path(directory: Path) -> Path:
    """A same-directory temporary name that can never collide with a final record."""
    return directory / (_USE_RECORD_TEMP_PREFIX + os.urandom(16).hex()
                        + _USE_RECORD_TEMP_SUFFIX)


def _open_use_record_temp(temporary: Path) -> int:
    """Create the private same-directory temporary record (O_EXCL, no follow)."""
    return os.open(temporary,
                   os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
                   | os.O_CLOEXEC, 0o600)


def _write_use_record_body(descriptor: int, body: bytes) -> None:
    """Write the complete canonical body; zero progress is an I/O failure."""
    written = 0
    while written < len(body):
        progress = os.write(descriptor, body[written:])
        if progress <= 0:
            raise OSError(errno.EIO, "authorization use record write made no progress")
        written += progress


def _link_use_record_no_replace(temporary: Path, record_path: Path) -> bool:
    """Atomically publish ``record_path`` without ever replacing an existing name.

    ``link(2)`` is the only linearization point: the final name either does not
    exist or already refers to the complete, fsynced record. It returns
    ``False`` when a concurrent consumer published first. Unsupported or
    cross-device links fail closed as ``OSError``: there is deliberately no
    fallback to direct final-name creation, which is the racy old path.
    """
    try:
        os.link(temporary, record_path, follow_symlinks=False)
    except FileExistsError:
        return False
    except NotImplementedError:
        raise OSError(errno.ENOTSUP, "atomic no-replace link is unsupported") from None
    return True


def _fsync_directory(directory: Path) -> None:
    """Persist the directory entry created by the publish; failure is fatal."""
    descriptor = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                         | os.O_CLOEXEC)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _safe_unlink_temp(temporary: Path) -> None:
    """Remove only our temporary inode; a failure must not change a decision."""
    try:
        os.unlink(temporary)
    except FileNotFoundError:
        pass
    except OSError:
        # A leftover temp is not a use record and is excluded from the capacity
        # count; stale temps are reaped later. Cleanup failure must not turn a
        # successful consumption into a caller-visible I/O failure, and must
        # never touch the published final.
        pass


def _count_use_log_entries(directory: Path) -> tuple[int, int]:
    """Count complete use records and temps separately within one bounded scan."""
    finals = 0
    temps = 0
    try:
        with os.scandir(directory) as entries:
            for entry in entries:
                if entry.name.startswith(_USE_RECORD_TEMP_PREFIX):
                    temps += 1
                    continue
                try:
                    is_regular = entry.is_file(follow_symlinks=False)
                except OSError:
                    is_regular = False
                if is_regular:
                    finals += 1
    except OSError:
        raise AuthorizationRejected(("AUTHORIZATION_USE_LOG_UNREADABLE",)) from None
    return finals, temps


def _reap_stale_use_record_temps(directory: Path) -> None:
    """Best-effort reap of stale publisher temps; a published final is never touched.

    Only names with the reserved temp prefix are candidates, and only after a
    grace period, so a concurrent live publisher's fresh temp is left alone.
    Crash residue therefore cannot accumulate into a denial of service.
    """
    deadline = time.time() - _USE_RECORD_TEMP_TTL_SECONDS
    try:
        with os.scandir(directory) as entries:
            for entry in entries:
                if not entry.name.startswith(_USE_RECORD_TEMP_PREFIX):
                    continue
                try:
                    if not entry.is_file(follow_symlinks=False):
                        continue
                    if entry.stat(follow_symlinks=False).st_mtime > deadline:
                        continue
                    os.unlink(entry.path)
                except OSError:
                    continue
    except OSError:
        return


def consume_execution_authorization(*, use_log_dir: Path, run_epoch: str,
                                    now: datetime | None = None,
                                    checkpoint: str = "pre_reserve",
                                    **load_kwargs: Any) -> AuthorizationUse:
    """Consume the single use of an authorization at the pre-Reserve checkpoint.

    The full offline verification is repeated here (files, pinned keys,
    revocation, bindings, time window) and only an accepted decision may publish
    one immutable use record. The body is written completely to a same-directory
    temporary file, ``fsync``-ed, atomically published with ``os.link`` (which
    can never replace an existing name), and the directory entry is ``fsync``-ed
    before success is returned. Therefore:

    * at most one concurrent consumer returns success; every loser observes an
      already complete record and is classified as REPLAYED / EPOCH_MISMATCH,
      never as a half-written INVALID record;
    * a record is either invisible or complete, so a malformed persisted record
      still fails closed with USE_RECORD_INVALID;
    * a directory ``fsync`` failure after the publish is a fail-closed
      ``DURABILITY_UNKNOWN`` rejection: the use is spent, so a later attempt sees
      the complete final and is classified as replay, and no dispatch proceeds;
    * a crash at any point leaves either no final (nothing was consumed) or a
      complete final (one use consumed), never a partial final.

    This function has no Broker/Ledger/Reserve/Claim path at all: it cannot send
    or account for anything, so the link is the only consumption event.
    """
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    if not isinstance(run_epoch, str) or not _IDENTIFIER.fullmatch(run_epoch):
        raise AuthorizationRejected(("RUN_EPOCH_INVALID",))
    repo_root = load_kwargs.get("repo_root")
    if not isinstance(repo_root, Path):
        raise AuthorizationRejected(("AUTHORIZATION_USE_LOG_INVALID:missing repo root",))
    decision = load_execution_authorization(now=moment, checkpoint=checkpoint,
                                            **load_kwargs)
    authorization = decision.require()
    if not (authorization.not_before_utc <= moment < authorization.expires_utc):
        raise AuthorizationRejected(("AUTHORIZATION_NOT_CURRENT",))
    try:
        directory = _trusted_directory(use_log_dir, repo_root=repo_root,
                                       label="authorization use log")
    except ValueError as error:
        raise AuthorizationRejected((f"AUTHORIZATION_USE_LOG_INVALID:{error}",)) from None
    record_path = directory / (hashlib.sha256(
        authorization.authorization_id.encode("ascii")).hexdigest() + ".json")
    # Fast path: an already published final is classified before touching the
    # log. The authoritative classification for a racing publish is the
    # EEXIST branch of the atomic link below.
    if record_path.exists() or record_path.is_symlink():
        _recorded_id, previous_epoch = _read_use_record_settled(
            record_path, expected_authorization_id=authorization.authorization_id)
        raise AuthorizationRejected((_replay_reason(previous_epoch, run_epoch),))
    _reap_stale_use_record_temps(directory)
    finals, temps = _count_use_log_entries(directory)
    if finals >= MAX_AUTHORIZATION_USES:
        raise AuthorizationRejected(("AUTHORIZATION_USE_LOG_FULL",))
    if temps >= MAX_USE_RECORD_TEMPS:
        # Extraordinary crash/concurrency residue: fail closed rather than
        # allowing unbounded temp growth. Stale temps are reaped above, so a
        # normal crash restarts without this being reachable.
        raise AuthorizationRejected(("AUTHORIZATION_USE_LOG_WRITE_FAILED",))
    consumed = moment.strftime("%Y-%m-%dT%H:%M:%SZ")
    body = _canonical_payload({
        "schema": _USE_LOG_SCHEMA,
        "authorization_id": authorization.authorization_id,
        "run_epoch": run_epoch,
        "consumed_utc": consumed,
    })
    temporary = _use_record_temp_path(directory)
    try:
        descriptor = _open_use_record_temp(temporary)
    except OSError:
        raise AuthorizationRejected(("AUTHORIZATION_USE_LOG_WRITE_FAILED",)) from None
    try:
        _write_use_record_body(descriptor, body)
        os.fsync(descriptor)
    except OSError:
        _safe_unlink_temp(temporary)
        raise AuthorizationRejected(("AUTHORIZATION_USE_LOG_WRITE_FAILED",)) from None
    finally:
        try:
            os.close(descriptor)
        except OSError:
            pass
    try:
        linked = _link_use_record_no_replace(temporary, record_path)
    except OSError:
        # Unsupported link / cross-device / permission failure: fail closed. The
        # final name is untouched and there is no direct-write fallback.
        _safe_unlink_temp(temporary)
        raise AuthorizationRejected(("AUTHORIZATION_USE_LOG_WRITE_FAILED",)) from None
    if not linked:
        # A concurrent consumer won the atomic publish. Its record was complete
        # before it became visible, so classification is stable; our unborn
        # temp is removed and can never become a second record. A foreign or
        # mismatched body id is INVALID, never a replay.
        _safe_unlink_temp(temporary)
        _recorded_id, previous_epoch = _read_use_record_settled(
            record_path, expected_authorization_id=authorization.authorization_id)
        raise AuthorizationRejected((_replay_reason(previous_epoch, run_epoch),))
    try:
        _fsync_directory(directory)
    except OSError:
        # The final name is already visible, so the single use is spent: never
        # remove it and never report success. Durability is unknown, therefore
        # this is a fail-closed rejection and no dispatch may follow. A later
        # attempt observes the complete final and is classified as replay.
        _safe_unlink_temp(temporary)
        raise AuthorizationRejected(("AUTHORIZATION_USE_LOG_DURABILITY_UNKNOWN",)) from None
    _safe_unlink_temp(temporary)
    return AuthorizationUse(authorization.authorization_id, run_epoch, consumed, record_path)
