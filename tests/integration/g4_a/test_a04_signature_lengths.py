"""G4-A-04: malformed R/S, wrong lengths and non-byte inputs fail closed, never raise."""
from __future__ import annotations

import json

import pytest

from autoteacher_m0.security import ed25519
from g4a_support import TEST_ONLY_SEED, base_payload, canonical

L = 2**252 + 27742317777372353535851937790883648493
PUBLIC = ed25519.public_key(TEST_ONLY_SEED)
MESSAGE = b'{"g4a":"signature-negative"}'
SIGNATURE = ed25519.sign(MESSAGE, TEST_ONLY_SEED)
assert ed25519.verify(PUBLIC, MESSAGE, SIGNATURE) is True


def _with_scalar(value: int) -> bytes:
    return SIGNATURE[:32] + value.to_bytes(32, "little")


def test_a04_tampered_r_and_s_are_rejected() -> None:
    tampered_r = bytes([SIGNATURE[0] ^ 1]) + SIGNATURE[1:]
    assert ed25519.verify(PUBLIC, MESSAGE, tampered_r) is False
    tampered_s = SIGNATURE[:32] + bytes([SIGNATURE[32] ^ 1]) + SIGNATURE[33:]
    assert ed25519.verify(PUBLIC, MESSAGE, tampered_s) is False
    for scalar in (0, 1, L - 1, L, L + 1, 2**256 - 1):
        assert ed25519.verify(PUBLIC, MESSAGE, _with_scalar(scalar)) is False, scalar


@pytest.mark.parametrize("size", [0, 1, 31, 32, 63, 65, 96, 128])
def test_a04_wrong_signature_length_is_rejected(size: int) -> None:
    blob = (SIGNATURE * 3)[:size]
    assert ed25519.verify(PUBLIC, MESSAGE, blob) is False


@pytest.mark.parametrize("size", [0, 1, 31, 33, 64, 96])
def test_a04_wrong_public_key_length_is_rejected(size: int) -> None:
    blob = (PUBLIC * 3)[:size]
    assert ed25519.verify(blob, MESSAGE, SIGNATURE) is False
    assert ed25519.is_valid_public_key(blob) is False


@pytest.mark.parametrize("bad", [None, 123, 12.5, object(), "a" * 64, b"\x00" * 64 + b"\x00"])
def test_a04_non_bytes_input_never_raises(bad) -> None:
    assert ed25519.verify(PUBLIC, MESSAGE, bad) is False
    assert ed25519.verify(bad, MESSAGE, SIGNATURE) is False
    assert ed25519.verify(PUBLIC, bad, SIGNATURE) is False
    assert ed25519.is_valid_public_key(bad) is False


def test_a04_bytes_like_inputs_are_normalized() -> None:
    assert ed25519.verify(bytearray(PUBLIC), bytearray(MESSAGE), bytearray(SIGNATURE)) is True
    assert ed25519.verify(memoryview(PUBLIC), memoryview(MESSAGE),
                          memoryview(SIGNATURE)) is True
    assert ed25519.is_valid_public_key(bytearray(PUBLIC)) is True


@pytest.mark.parametrize("value,reason", [
    (SIGNATURE.hex().upper(), "SIGNATURE_ENCODING_INVALID"),
    ("zz" * 64, "SIGNATURE_ENCODING_INVALID"),
    ((SIGNATURE + b"\x00")[:64].hex()[:-2], "SIGNATURE_ENCODING_INVALID"),
    ("00" * 63, "SIGNATURE_ENCODING_INVALID"),
    ("00", "SIGNATURE_ENCODING_INVALID"),
])
def test_a04_authorization_signature_encoding_fails_closed(trusted, value: str,
                                                           reason: str) -> None:
    signed = trusted.sign(trusted.payload)
    signed["signature"]["value"] = value
    trusted.write_raw(json.dumps(signed))
    decision = trusted.load()
    assert decision.approved is False
    assert reason in decision.reasons, decision.reasons
    assert decision.signature_valid is False
    assert trusted.use_records() == []


def test_a04_authorization_wrong_algorithm_and_zero_signature(trusted) -> None:
    signed = trusted.sign(trusted.payload)
    signed["signature"]["algorithm"] = "rsa"
    trusted.write_raw(json.dumps(signed))
    decision = trusted.load()
    assert decision.approved is False
    assert "SIGNATURE_ALGORITHM_NOT_APPROVED" in decision.reasons

    signed = trusted.sign(trusted.payload)
    signed["signature"]["value"] = "00" * 64
    trusted.write_raw(json.dumps(signed))
    decision = trusted.load()
    assert decision.approved is False
    assert "HUMAN_SIGNATURE_INVALID" in decision.reasons
    assert decision.signature_valid is False


def test_a04_signed_payload_cannot_be_replayed_with_another_message() -> None:
    other = canonical(base_payload({name: "1" * 64 for name in (
        "code_sha256", "lock_sha256", "runtime_sha256", "plugin_sha256",
        "merged_profile_sha256")}))
    assert ed25519.verify(PUBLIC, other, SIGNATURE) is False
