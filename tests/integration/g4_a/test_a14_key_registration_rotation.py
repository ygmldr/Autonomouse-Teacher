"""G4-A-14: unregistered/rotated approval keys are denied; rotation invalidates."""
from __future__ import annotations

import json

import pytest

from autoteacher_m0.security import ed25519
from g4a_support import (
    KEY_ID,
    NOW,
    ROTATED_KEY_ID,
    ROTATED_SEED,
    TEST_ONLY_SEED,
    UNREGISTERED_SEED,
)

SMALL_ORDER = "01" + "00" * 31


def _assert_invalid(trusted, **kwargs) -> None:
    decision = trusted.load(**kwargs)
    assert decision.approved is False
    assert decision.signature_valid is False
    assert decision.reasons[0].startswith("EXTERNAL_AUTHORIZATION_INVALID"), decision.reasons
    assert trusted.use_records() == []


@pytest.mark.parametrize("document", [
    "not json",
    json.dumps({"schema": "at-m0/trusted-approver-keys/v1"}),
    json.dumps({"schema": "at-m0/trusted-approver-keys/v1", "keys": {}}),
    json.dumps({"schema": "at-m0/trusted-approver-keys/v1", "keys": [],
                "extra": 1}),
    json.dumps({"schema": "at-m0/trusted-approver-keys/v1",
                "keys": {KEY_ID: ed25519.public_key(TEST_ONLY_SEED).hex().upper()}}),
    json.dumps({"schema": "at-m0/trusted-approver-keys/v1",
                "keys": {KEY_ID: ed25519.public_key(TEST_ONLY_SEED).hex()[:-2]}}),
    json.dumps({"schema": "at-m0/trusted-approver-keys/v1",
                "keys": {KEY_ID: "zz" * 32}}),
    json.dumps({"schema": "at-m0/trusted-approver-keys/v1", "keys": {KEY_ID: SMALL_ORDER}}),
    json.dumps({"schema": "at-m0/trusted-approver-keys/v1",
                "keys": {"bad key id": ed25519.public_key(TEST_ONLY_SEED).hex()}}),
    json.dumps({"schema": "at-m0/trusted-approver-keys/v1",
                "keys": {KEY_ID: ed25519.public_key(TEST_ONLY_SEED).hex() + "00"}}),
    json.dumps({"schema": "at-m0/trusted-approver-keys/v1", "keys": {KEY_ID: "00" * 32}}),
])
def test_a14_malformed_or_unsafe_key_registry_fails_closed(trusted, document: str) -> None:
    trusted.keys.write_text(document, encoding="utf-8")
    _assert_invalid(trusted, keys=trusted.keys)


def test_a14_duplicate_key_id_in_registry_is_rejected(trusted) -> None:
    public = ed25519.public_key(TEST_ONLY_SEED).hex()
    document = ('{"schema": "at-m0/trusted-approver-keys/v1", '
                f'"keys": {{"{KEY_ID}": "{public}", "{KEY_ID}": "{public}"}}}}')
    trusted.keys.write_text(document, encoding="utf-8")
    _assert_invalid(trusted, keys=trusted.keys)


def test_a14_unregistered_key_ids_are_denied(trusted) -> None:
    trusted.write_signed(trusted.payload, key_id="TEST_ONLY_unregistered_agent_key")
    decision = trusted.load()
    assert decision.approved is False
    assert "UNKNOWN_APPROVAL_KEY" in decision.reasons
    assert decision.signature_valid is False

    trusted.write_signed(trusted.payload, seed=UNREGISTERED_SEED)
    decision = trusted.load()
    assert "HUMAN_SIGNATURE_INVALID" in decision.reasons
    assert decision.signature_valid is False


def test_a14_key_rotation_invalidates_old_signatures(trusted) -> None:
    trusted.set_keys({KEY_ID: ed25519.public_key(ROTATED_SEED).hex()})
    # The old signature was minted by the retired key.
    decision = trusted.load()
    assert decision.approved is False
    assert "HUMAN_SIGNATURE_INVALID" in decision.reasons
    assert decision.signature_valid is False
    # Re-signing with the rotated key is accepted (the operator chose the new key).
    trusted.write_signed(trusted.payload, seed=ROTATED_SEED)
    assert trusted.load().approved is True


def test_a14_key_removal_is_a_revocation(trusted) -> None:
    trusted.set_keys({ROTATED_KEY_ID: ed25519.public_key(ROTATED_SEED).hex()})
    decision = trusted.load()
    assert decision.approved is False
    assert "UNKNOWN_APPROVAL_KEY" in decision.reasons
    assert trusted.use_records() == []


def test_a14_multiple_registered_keys_are_supported(trusted) -> None:
    trusted.set_keys({
        KEY_ID: ed25519.public_key(TEST_ONLY_SEED).hex(),
        ROTATED_KEY_ID: ed25519.public_key(ROTATED_SEED).hex(),
    })
    assert trusted.load().approved is True
    trusted.write_signed(trusted.payload, seed=ROTATED_SEED, key_id=ROTATED_KEY_ID)
    decision = trusted.load()
    assert decision.approved is True
    assert decision.signature_valid is True
    assert decision.billable_send_authorized is False


def test_a14_key_id_must_match_the_signing_key(trusted) -> None:
    trusted.set_keys({KEY_ID: ed25519.public_key(ROTATED_SEED).hex()})
    trusted.write_signed(trusted.payload, seed=ROTATED_SEED, key_id="TEST_ONLY_other_id")
    decision = trusted.load()
    assert decision.approved is False
    assert "UNKNOWN_APPROVAL_KEY" in decision.reasons


def test_a14_keys_file_inside_candidate_stage_is_denied_by_controller(trusted) -> None:
    staged = trusted.stage / "trusted-keys.json"
    staged.write_bytes(trusted.keys.read_bytes())
    decision = trusted.controller(keys=staged).inspect(now=NOW)
    assert decision.status == "BLOCKED"
    assert "TRUSTED_KEYS_PATH_INSIDE_CANDIDATE_STAGE" in decision.reasons
    assert decision.billable_send_authorized is False
