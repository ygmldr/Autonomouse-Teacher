"""G4-A-03: non-canonical encodings and torsion/mixed-subgroup points are rejected."""
from __future__ import annotations

import json

import pytest

from autoteacher_m0.security import ed25519
from g4a_support import KEY_ID, TEST_ONLY_SEED, base_payload, canonical

FIELD = 2**255 - 19
ORDER_EIGHT = bytes.fromhex(
    "c7176a703d4dd84fba3c0b760d10670f2a2053fa2c39ccc64ec7fd7792ac037a")
TORSION = ed25519._decode_point(ORDER_EIGHT)
MIXED_ORDER = ed25519._encode_point(ed25519._edwards_add(ed25519._B, TORSION))
NONCANONICAL_Y = (FIELD + 1).to_bytes(32, "little")
NONCANONICAL_IDENTITY = (b"\x01" + b"\x00" * 30) + b"\x80"
PUBLIC = ed25519.public_key(TEST_ONLY_SEED)
MESSAGE = canonical(base_payload({name: "0" * 64 for name in (
    "code_sha256", "lock_sha256", "runtime_sha256", "plugin_sha256",
    "merged_profile_sha256")}))
SIGNATURE = ed25519.sign(MESSAGE, TEST_ONLY_SEED)


def test_a03_mixed_order_public_key_is_not_prime_order() -> None:
    assert ed25519._in_prime_order_subgroup(ed25519._decode_point(MIXED_ORDER)) is False
    assert ed25519.is_valid_public_key(MIXED_ORDER) is False
    assert ed25519.verify(MIXED_ORDER, MESSAGE, SIGNATURE) is False


def test_a03_noncanonical_public_key_encoding_is_rejected() -> None:
    with pytest.raises(ValueError):
        ed25519._decode_point(NONCANONICAL_Y)
    with pytest.raises(ValueError):
        ed25519._decode_point(NONCANONICAL_IDENTITY)
    assert ed25519.is_valid_public_key(NONCANONICAL_Y) is False
    assert ed25519.is_valid_public_key(NONCANONICAL_IDENTITY) is False
    assert ed25519.verify(NONCANONICAL_Y, MESSAGE, SIGNATURE) is False


@pytest.mark.parametrize("point", [
    ORDER_EIGHT,
    ed25519._encode_point(ed25519._IDENTITY),
    ed25519._encode_point(ed25519._scalar_mult(ed25519._B, 1)),
    NONCANONICAL_Y,
])
def test_a03_signature_r_must_be_canonical_prime_order(point: bytes) -> None:
    crafted = point + SIGNATURE[32:]
    assert ed25519.verify(PUBLIC, MESSAGE, crafted) is False


def test_a03_authorization_with_torsion_material_never_approves(trusted) -> None:
    # Mixed-order trusted key: rejected by the pinned-key admission.
    trusted.set_keys({KEY_ID: MIXED_ORDER.hex()})
    trusted.write_signed(trusted.payload)
    decision = trusted.load()
    assert decision.approved is False
    assert decision.signature_valid is False
    assert any(reason.startswith("EXTERNAL_AUTHORIZATION_INVALID")
               for reason in decision.reasons), decision.reasons

    # A canonical prime-order key with a non-canonical R encoding must not verify
    # with a stable signature reason.
    trusted.set_keys({KEY_ID: PUBLIC.hex()})
    signed = trusted.sign(trusted.payload)
    signed["signature"]["value"] = (NONCANONICAL_Y + SIGNATURE[32:]).hex()
    trusted.write_raw(json.dumps(signed))
    decision = trusted.load()
    assert decision.approved is False
    assert "HUMAN_SIGNATURE_INVALID" in decision.reasons
    assert trusted.use_records() == []


def test_a03_torsion_signature_r_with_identity_key_is_rejected(trusted) -> None:
    trusted.set_keys({KEY_ID: ed25519._encode_point(ed25519._IDENTITY).hex()})
    signed = trusted.sign(trusted.payload)
    signed["signature"]["value"] = (ORDER_EIGHT + (1).to_bytes(32, "little")).hex()
    trusted.write_raw(json.dumps(signed))
    decision = trusted.load()
    assert decision.approved is False
    assert decision.signature_valid is False
