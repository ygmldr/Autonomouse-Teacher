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
import json
from pathlib import Path
import re
from typing import Any, Mapping

from autoteacher_m0.contracts import ErrorCode, RuntimeFailure

from . import ed25519

AUTHORIZATION_SCHEMA = "at-m0/execution-authorization/v1"
MAX_AUTHORIZATION_BYTES = 64 * 1024
MAX_KEYS_BYTES = 16 * 1024
MAX_REVOCATION_BYTES = 64 * 1024
ALLOWED_TOOLS = frozenset({"skill_lookup"})
BINDING_NAMES = (
    "code_sha256",
    "lock_sha256",
    "runtime_sha256",
    "plugin_sha256",
    "merged_profile_sha256",
)
_DIGEST = re.compile(r"[a-f0-9]{64}\Z")
_IDENTIFIER = re.compile(r"[A-Za-z0-9._:-]{1,128}\Z")
_USD = re.compile(r"(?:0|[1-9][0-9]{0,5})(?:\.[0-9]{1,6})?\Z")
_UTC_TEXT = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z\Z")
_MAX_AUTHORIZATION_LIFETIME = timedelta(hours=24)
_MAX_ISSUED_AGE = timedelta(days=7)


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


def _external_regular_file(path: Path, *, repo_root: Path, label: str,
                           max_bytes: int) -> bytes:
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
    if not resolved.is_file():
        raise ValueError(f"{label} must be a regular file")
    size = resolved.stat().st_size
    if size <= 0 or size > max_bytes:
        raise ValueError(f"{label} size is outside the permitted range")
    return resolved.read_bytes()


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
    approved: bool
    reasons: tuple[str, ...]
    authorization: ExecutionAuthorization | None

    def require(self) -> ExecutionAuthorization:
        if not self.approved or self.authorization is None:
            raise AuthorizationRejected(self.reasons or ("AUTHORIZATION_REJECTED",))
        return self.authorization


def _canonical_payload(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("utf-8")


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
                                 now: datetime | None = None) -> AuthorizationDecision:
    """Return a deny decision unless every external-human check passes."""
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
    if public_key is None:
        reasons.append("UNKNOWN_APPROVAL_KEY")
    elif not signature or not ed25519.verify(public_key, signed_bytes, signature):
        reasons.append("HUMAN_SIGNATURE_INVALID")

    if not (not_before <= moment < expires):
        reasons.append("AUTHORIZATION_NOT_CURRENT")
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
                                 authorization if approved else None)


def require_execution_authorization(**kwargs: Any) -> ExecutionAuthorization:
    """Fail-closed convenience wrapper; no retry and no partial approval."""
    return load_execution_authorization(**kwargs).require()
