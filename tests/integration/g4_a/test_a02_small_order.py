"""G4-A-02: small-order Ed25519 public keys are rejected before any decision."""
from __future__ import annotations

import json

import pytest

from autoteacher_m0.security import ed25519
from g4a_support import KEY_ID, TEST_ONLY_SEED, base_payload, canonical

IDENTITY = "01" + "00" * 31
ORDER_FOUR_ZERO = "00" * 32
ORDER_FOUR_NEGATIVE_ZERO = "00" * 31 + "80"
ORDER_EIGHT = (
    "c7176a703d4dd84fba3c0b760d10670f2a2053fa2c39ccc64ec7fd7792ac037a",
    "c7176a703d4dd84fba3c0b760d10670f2a2053fa2c39ccc64ec7fd7792ac03fa",
    "26e8958fc2b227b045c3f489f2ef98f0d5dfac05d3c63339b13802886d53fc05",
    "26e8958fc2b227b045c3f489f2ef98f0d5dfac05d3c63339b13802886d53fc85",
)
SMALL_ORDER = (IDENTITY, ORDER_FOUR_ZERO, ORDER_FOUR_NEGATIVE_ZERO) + ORDER_EIGHT


@pytest.mark.parametrize("public_hex", SMALL_ORDER)
def test_a02_small_order_public_key_is_never_a_trusted_key(trusted, public_hex: str) -> None:
    assert ed25519.is_valid_public_key(bytes.fromhex(public_hex)) is False
    trusted.set_keys({KEY_ID: public_hex})
    trusted.write_signed(trusted.payload)
    decision = trusted.load()
    assert decision.approved is False
    assert decision.signature_valid is False
    assert any(reason.startswith("EXTERNAL_AUTHORIZATION_INVALID")
               for reason in decision.reasons), decision.reasons
    assert trusted.use_records() == []


def test_a02_identity_key_forgery_is_rejected(trusted) -> None:
    """A = identity reduces S*B == R + k*A to S*B == R; R=B, S=1 forges it.

    The strict public-key admission must reject the identity key even though the
    crafted signature equation holds, so no approval can be minted this way.
    """
    trusted.set_keys({KEY_ID: IDENTITY})
    base_point = bytes.fromhex(
        "5866666666666666666666666666666666666666666666666666666666666666")
    forged = base_payload(trusted.bindings.as_dict())
    forged["signature"] = {"algorithm": "ed25519", "key_id": KEY_ID,
                           "value": (base_point + (1).to_bytes(32, "little")).hex()}
    trusted.write_raw(json.dumps(forged))
    decision = trusted.load()
    assert decision.approved is False
    assert decision.signature_valid is False
    assert any(reason.startswith("EXTERNAL_AUTHORIZATION_INVALID")
               for reason in decision.reasons), decision.reasons


def test_a02_regular_prime_order_key_still_verifies(trusted) -> None:
    """Positive control: the same fixture with a prime-order key is accepted."""
    public = ed25519.public_key(TEST_ONLY_SEED)
    payload = base_payload(trusted.bindings.as_dict())
    signature = ed25519.sign(canonical(payload), TEST_ONLY_SEED)
    assert ed25519.is_valid_public_key(public) is True
    assert ed25519.verify(public, canonical(payload), signature) is True
    assert trusted.load().approved is True
