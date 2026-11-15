"""Offline fail-closed tests for ExecutionAuthorization (no key, no model call)."""
from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from autoteacher_m0.security import ed25519
from autoteacher_m0.security.authorization import (
    ApprovedRoute,
    AuthorizationRejected,
    ExpectedBindings,
    load_execution_authorization,
    require_execution_authorization,
)

NOW = datetime(2026, 11, 14, 12, 0, 0, tzinfo=timezone.utc)
SEED = bytes.fromhex("31" * 32)
KEY_ID = "human-maintainer-test-1"
BINDINGS = {name: (char * 64) for name, char in zip(
    ("code_sha256", "lock_sha256", "runtime_sha256", "plugin_sha256", "merged_profile_sha256"),
    "12345")}
ROUTE = {"route_id": "opencode-go", "provider": "opencode-go", "model": "deepseek-v4.1-flash"}
SCOPE = "live-m0-pr3-rehearsal"


def canonical(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("utf-8")


def base_payload() -> dict:
    return {
        "schema": "at-m0/execution-authorization/v1",
        "authorization_id": "auth-pr3-offline-1",
        "approver": "maintainer@example.invalid",
        "approval_note": "Offline PR3 rehearsal authorization, no key, no model call",
        "issued_utc": "2026-11-14T11:50:00Z",
        "not_before_utc": "2026-11-14T11:55:00Z",
        "expires_utc": "2026-11-14T12:30:00Z",
        "bindings": dict(BINDINGS),
        "route": dict(ROUTE),
        "allowed_tools": ["skill_lookup"],
        "budget": {"scope": SCOPE, "per_call_cap_usd": "0.10",
                   "total_cap_usd": "1.00", "max_calls": 10},
        "deadline": {"total_seconds": 120, "max_steps": 8, "max_dispatch_attempts": 8},
    }


class External:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.repo = root / "repo"
        self.repo.mkdir()
        self.external = root / "external"
        self.external.mkdir()
        self.revoked = self.external / "revoked.json"
        self.revoked.write_text(json.dumps(
            {"schema": "at-m0/revocation/v1", "revoked_ids": []}), encoding="utf-8")
        self.keys = self.external / "trusted-keys.json"
        self.authorization = self.external / "authorization.json"
        self.set_keys()
        self.write_signed(base_payload())

    def set_keys(self, seed: bytes = SEED) -> None:
        self.keys.write_text(json.dumps({"schema": "at-m0/trusted-approver-keys/v1",
                                         "keys": {KEY_ID: ed25519.public_key(seed).hex()}}),
                             encoding="utf-8")

    def sign(self, payload: dict, seed: bytes = SEED) -> dict:
        signed = copy.deepcopy(payload)
        signed["signature"] = {"algorithm": "ed25519", "key_id": KEY_ID,
                               "value": ed25519.sign(canonical(payload), seed).hex()}
        return signed

    def write_signed(self, payload: dict, seed: bytes = SEED) -> None:
        self.authorization.write_text(json.dumps(self.sign(payload, seed)),
                                      encoding="utf-8")

    def load(self, *, now: datetime = NOW, actual_tools: tuple[str, ...] = ("skill_lookup",),
             expected: ExpectedBindings | None = None, route: ApprovedRoute | None = None,
             scope: str = SCOPE, authorization: Path | None = None,
             keys: Path | None = None, revoked: Path | None = None):
        return load_execution_authorization(
            authorization_path=authorization or self.authorization,
            trusted_keys_path=keys or self.keys,
            revocation_path=revoked or self.revoked,
            repo_root=self.repo,
            expected=expected or ExpectedBindings(**BINDINGS),
            approved_route=route or ApprovedRoute(**ROUTE),
            actual_tools=actual_tools,
            budget_scope=scope,
            now=now,
        )


@pytest.fixture()
def external(tmp_path: Path) -> External:
    return External(tmp_path)


def test_valid_external_signed_authorization_is_accepted(external: External) -> None:
    decision = external.load()
    assert decision.approved is True, decision.reasons
    assert decision.reasons == ()
    authorization = decision.require()
    assert authorization.route.route_id == "opencode-go"
    assert authorization.budget.per_call_cap_usd == authorization.budget.total_cap_usd / 10
    assert authorization.allowed_tools == ("skill_lookup",)
    assert authorization.bindings.as_dict() == BINDINGS
    assert KEY_ID == authorization.key_id


def test_require_raises_security_blocked_on_deny(external: External) -> None:
    external.authorization.write_text("{not json", encoding="utf-8")
    with pytest.raises(AuthorizationRejected) as error:
        require_execution_authorization(
            authorization_path=external.authorization,
            trusted_keys_path=external.keys, revocation_path=external.revoked,
            repo_root=external.repo, expected=ExpectedBindings(**BINDINGS),
            approved_route=ApprovedRoute(**ROUTE), actual_tools=("skill_lookup",),
            budget_scope=SCOPE, now=NOW)
    assert error.value.code == "SECURITY_BLOCKED"


def test_in_repo_or_symlinked_authorization_is_rejected(external: External) -> None:
    in_repo = external.repo / "authorization.json"
    in_repo.write_text(external.authorization.read_text(encoding="utf-8"), encoding="utf-8")
    assert "EXTERNAL_AUTHORIZATION_INVALID" in external.load(authorization=in_repo).reasons[0]
    link = external.external / "link.json"
    link.symlink_to(external.authorization)
    assert "EXTERNAL_AUTHORIZATION_INVALID" in external.load(authorization=link).reasons[0]
    in_repo_keys = external.repo / "keys.json"
    in_repo_keys.write_text(external.keys.read_text(encoding="utf-8"), encoding="utf-8")
    assert "EXTERNAL_AUTHORIZATION_INVALID" in external.load(keys=in_repo_keys).reasons[0]


@pytest.mark.parametrize("markdown", ["# APPROVED BY HUMAN\n", "**yes**\n"])
def test_markdown_is_not_an_authorization(external: External, markdown: str) -> None:
    external.authorization.write_text(markdown, encoding="utf-8")
    decision = external.load()
    assert decision.approved is False
    assert decision.reasons[0].startswith("EXTERNAL_AUTHORIZATION_INVALID")


def test_self_signed_and_unknown_key_are_rejected(external: External) -> None:
    payload = external.sign(base_payload())
    payload["signature"]["key_id"] = "untrusted-agent"
    external.authorization.write_text(json.dumps(payload), encoding="utf-8")
    assert "UNKNOWN_APPROVAL_KEY" in external.load().reasons
    wrong_seed = bytes.fromhex("32" * 32)
    external.write_signed(base_payload(), seed=wrong_seed)
    assert "HUMAN_SIGNATURE_INVALID" in external.load().reasons
    payload = base_payload()
    payload["signature"] = {"algorithm": "ed25519", "key_id": KEY_ID, "value": "00" * 64}
    external.authorization.write_text(json.dumps(payload), encoding="utf-8")
    assert "HUMAN_SIGNATURE_INVALID" in external.load().reasons


def test_tampered_payload_or_signature_is_rejected(external: External) -> None:
    signed = external.sign(base_payload())
    signed["approval_note"] = "tampered after signing"
    external.authorization.write_text(json.dumps(signed), encoding="utf-8")
    assert "HUMAN_SIGNATURE_INVALID" in external.load().reasons
    signed = external.sign(base_payload())
    signed["signature"]["value"] = signed["signature"]["value"][:-2] + "00"
    external.authorization.write_text(json.dumps(signed), encoding="utf-8")
    assert "HUMAN_SIGNATURE_INVALID" in external.load().reasons


def test_duplicate_json_keys_are_rejected(external: External) -> None:
    text = external.authorization.read_text(encoding="utf-8")
    duplicated = text.replace('"approver":', '"approver":"x", "approver":', 1)
    external.authorization.write_text(duplicated, encoding="utf-8")
    assert external.load().reasons[0].startswith("EXTERNAL_AUTHORIZATION_INVALID")


def test_schema_and_unknown_fields_are_rejected(external: External) -> None:
    signed = external.sign(base_payload())
    signed["extra_agent_claim"] = True
    external.authorization.write_text(json.dumps(signed), encoding="utf-8")
    assert "AUTHORIZATION_SCHEMA_FIELDS_INVALID" in external.load().reasons
    payload = base_payload()
    payload["schema"] = "agent/self-approved/v1"
    external.write_signed(payload)
    assert "AUTHORIZATION_SCHEMA_UNKNOWN" in external.load().reasons


@pytest.mark.parametrize("name", tuple(BINDINGS))
def test_every_binding_mismatch_blocks(external: External, name: str) -> None:
    wrong = dict(BINDINGS)
    wrong[name] = "f" * 64
    assert f"{name.upper()}_MISMATCH" in external.load(
        expected=ExpectedBindings(**wrong)).reasons
    assert external.load().approved is True


def test_route_tool_and_scope_mismatch_block(external: External) -> None:
    other = ApprovedRoute(route_id="deepseek-official", provider="deepseek-official",
                          model="deepseek-flash")
    assert "ROUTE_NOT_APPROVED" in external.load(route=other).reasons
    assert "ACTUAL_TOOL_REGISTRY_NOT_APPROVED" in external.load(
        actual_tools=("skill_lookup", "shell")).reasons
    assert "BUDGET_SCOPE_MISMATCH" in external.load(scope="other-scope").reasons
    payload = base_payload()
    payload["allowed_tools"] = ["skill_lookup", "shell"]
    external.write_signed(payload)
    assert "ALLOWED_TOOLS_NOT_PERMITTED" in external.load().reasons
    payload = base_payload()
    payload["allowed_tools"] = ["skill_lookup", "skill_lookup"]
    external.write_signed(payload)
    assert "ALLOWED_TOOLS_INVALID" in external.load().reasons


@pytest.mark.parametrize("budget,reason", [
    ({"scope": SCOPE, "per_call_cap_usd": "2.00", "total_cap_usd": "1.00", "max_calls": 1},
     "PER_CALL_CAP_EXCEEDS_TOTAL_CAP"),
    ({"scope": SCOPE, "per_call_cap_usd": "0.10", "total_cap_usd": "10.01", "max_calls": 1},
     "TOTAL_CAP_EXCEEDS_HARD_BUDGET"),
    ({"scope": SCOPE, "per_call_cap_usd": "0.10", "total_cap_usd": "1.00", "max_calls": 0},
     "MAX_CALLS_OUT_OF_RANGE"),
    ({"scope": SCOPE, "per_call_cap_usd": "0.10", "total_cap_usd": "1.00", "max_calls": 51},
     "MAX_CALLS_OUT_OF_RANGE"),
    ({"scope": SCOPE, "per_call_cap_usd": "NaN", "total_cap_usd": "1.00", "max_calls": 1},
     "BUDGET_VALUES_INVALID"),
])
def test_budget_limits_block(external: External, budget: dict, reason: str) -> None:
    payload = base_payload()
    payload["budget"] = budget
    external.write_signed(payload)
    assert reason in external.load().reasons


@pytest.mark.parametrize("deadline", [
    {"total_seconds": 0, "max_steps": 8, "max_dispatch_attempts": 8},
    {"total_seconds": 3601, "max_steps": 8, "max_dispatch_attempts": 8},
    {"total_seconds": 60, "max_steps": 201, "max_dispatch_attempts": 8},
    {"total_seconds": 60, "max_steps": 8, "max_dispatch_attempts": 51},
])
def test_deadline_limits_block(external: External, deadline: dict) -> None:
    payload = base_payload()
    payload["deadline"] = deadline
    external.write_signed(payload)
    assert "DEADLINE_OUT_OF_RANGE" in external.load().reasons


def test_time_window_expiry_and_age_block(external: External) -> None:
    assert "AUTHORIZATION_NOT_CURRENT" in external.load(
        now=NOW + timedelta(hours=1)).reasons
    assert "AUTHORIZATION_NOT_CURRENT" in external.load(
        now=NOW - timedelta(hours=1)).reasons
    assert "AUTHORIZATION_TOO_OLD" in external.load(
        now=NOW + timedelta(days=8)).reasons
    payload = base_payload()
    payload["expires_utc"] = "2026-11-15T12:00:00Z"
    external.write_signed(payload)
    assert "AUTHORIZATION_LIFETIME_TOO_LONG" in external.load().reasons


def test_revocation_file_and_revoked_id_block(external: External) -> None:
    external.revoked.unlink()
    assert external.load().reasons[0].startswith("EXTERNAL_AUTHORIZATION_INVALID")
    external.revoked.write_text(json.dumps(
        {"schema": "at-m0/revocation/v1", "revoked_ids": ["auth-pr3-offline-1"]}),
        encoding="utf-8")
    assert "AUTHORIZATION_REVOKED" in external.load().reasons
    external.revoked.write_text("not json", encoding="utf-8")
    assert external.load().approved is False


def test_environment_variables_and_flags_cannot_unlock(external: External,
                                                      monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in (("AT_M0_LIVE_APPROVED", "1"), ("AT_M0_ALLOW_LIVE", "true"),
                        ("LIVE_CONTROLLER_APPROVED", "yes")):
        monkeypatch.setenv(name, value)
    external.authorization.unlink()
    decision = external.load()
    assert decision.approved is False
    assert decision.reasons[0].startswith("EXTERNAL_AUTHORIZATION_INVALID")
    # A completely absent authorization cannot be replaced by an env/flag value.
    assert external.load().approved is False


def test_agent_editable_markdown_approval_never_used(external: External) -> None:
    markdown = external.repo / "SECURITY_APPROVALS.md"
    markdown.write_text("# HUMAN APPROVED\nlive=true key=present\n", encoding="utf-8")
    assert external.load().approved is True  # loader ignores repo markdown entirely
    external.authorization.unlink()
    assert external.load().approved is False


# ---- G1-SEC fail-first: AUTH-02 trusted public-key admission ----
BASE_POINT_ENCODING = bytes.fromhex(
    "5866666666666666666666666666666666666666666666666666666666666666")
IDENTITY_PUBLIC_HEX = ("01" + "00" * 31)
NONCANONICAL_IDENTITY_PUBLIC_HEX = ("01" + "00" * 31)[:-2] + "80"
LOW_ORDER_PUBLIC_HEX = "00" * 32


def _write_custom_trusted_key(external: External, public_hex: str) -> None:
    external.keys.write_text(json.dumps({
        "schema": "at-m0/trusted-approver-keys/v1",
        "keys": {KEY_ID: public_hex}}), encoding="utf-8")


def _write_identity_key_signature(external: External) -> None:
    """Craft an Ed25519 signature that identity/non-canonical identity verifies.

    A = identity => S*B == R + k*A reduces to S*B == R; choose R=B, S=1.
    """
    payload = base_payload()
    signed = copy.deepcopy(payload)
    crafted = BASE_POINT_ENCODING + (1).to_bytes(32, "little")
    signed["signature"] = {"algorithm": "ed25519", "key_id": KEY_ID,
                           "value": crafted.hex()}
    external.authorization.write_text(json.dumps(signed), encoding="utf-8")


def test_auth02_identity_public_key_is_rejected(external: External) -> None:
    _write_custom_trusted_key(external, IDENTITY_PUBLIC_HEX)
    _write_identity_key_signature(external)
    decision = external.load()
    assert decision.approved is False, "identity public key must never be admitted"
    assert any(reason.startswith("EXTERNAL_AUTHORIZATION_INVALID")
               for reason in decision.reasons), decision.reasons


def test_auth02_noncanonical_identity_point_is_rejected(external: External) -> None:
    _write_custom_trusted_key(external, NONCANONICAL_IDENTITY_PUBLIC_HEX)
    _write_identity_key_signature(external)
    decision = external.load()
    assert decision.approved is False, "non-canonical point encoding must be rejected"
    assert any(reason.startswith("EXTERNAL_AUTHORIZATION_INVALID")
               for reason in decision.reasons), decision.reasons


def test_auth02_low_order_public_key_is_rejected(external: External) -> None:
    _write_custom_trusted_key(external, LOW_ORDER_PUBLIC_HEX)
    external.write_signed(base_payload())
    decision = external.load()
    assert decision.approved is False, "small-order public key must never be trusted"
    assert any(reason.startswith("EXTERNAL_AUTHORIZATION_INVALID")
               for reason in decision.reasons), decision.reasons


def test_auth02_rfc8032_positive_vector_still_verifies() -> None:
    seed = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
    public = bytes.fromhex("d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a")
    signature = bytes.fromhex(
        "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b")
    assert ed25519.verify(public, b"", signature) is True
    assert ed25519.verify(public, b"x", signature) is False
    assert ed25519.public_key(seed) == public


# ---- G1-SEC fail-first: AUTH-05 strict integer types ----
@pytest.mark.parametrize("field,bad", [
    ("max_calls", "10"), ("max_calls", 10.5), ("max_calls", True),
    ("total_seconds", "120"), ("total_seconds", 120.5), ("total_seconds", True),
    ("max_steps", "8"), ("max_steps", True),
    ("max_dispatch_attempts", "8"), ("max_dispatch_attempts", True),
])
def test_auth05_integer_coercion_is_rejected(external: External, field: str,
                                             bad: object) -> None:
    payload = base_payload()
    if field == "max_calls":
        payload["budget"][field] = bad
    else:
        payload["deadline"][field] = bad
    external.write_signed(payload)
    decision = external.load()
    assert decision.approved is False, f"{field}={bad!r} must not be coerced"
    if field == "max_calls":
        assert "BUDGET_VALUES_INVALID" in decision.reasons, decision.reasons
    else:
        assert "DEADLINE_VALUES_INVALID" in decision.reasons, decision.reasons


# ---- G1-SEC fail-first: AUTH-06 fail-closed on approver/time exceptions ----
@pytest.mark.parametrize("field,bad,reason", [
    ("approver", 123, "APPROVER_INVALID"),
    ("approver", "", "APPROVER_INVALID"),
    ("issued_utc", 123, "AUTHORIZATION_TIME_INVALID"),
    ("not_before_utc", None, "AUTHORIZATION_TIME_INVALID"),
    ("expires_utc", 12.5, "AUTHORIZATION_TIME_INVALID"),
])
def test_auth06_bad_approver_or_time_is_fail_closed(external: External, field: str,
                                                    bad: object, reason: str) -> None:
    payload = base_payload()
    payload[field] = bad
    external.write_signed(payload)
    decision = external.load()
    assert decision.approved is False, field
    assert reason in decision.reasons, decision.reasons
