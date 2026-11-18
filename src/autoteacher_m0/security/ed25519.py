"""Dependency-free Ed25519 (RFC 8032) primitives for external human sign-off.

The trusted controller verifies *detached* authorization signatures with a public
key supplied by the operator from outside this repository. No private key, key
store or signing path is part of the controller deployment; ``sign`` exists only
so the offline no-key rehearsal/tests can mint a rehearsal approval with a test
seed (it is never called by the controller).

This is the straightforward RFC 8032 reference construction, not constant-time
code. Verification only touches public data; signing is limited to tests.
"""
from __future__ import annotations

import hashlib

_BITS = 256
_BYTES_TYPES = (bytes, bytearray, memoryview)
_Q = 2**255 - 19
_L = 2**252 + 27742317777372353535851937790883648493


def _inv(value: int) -> int:
    return pow(value, _Q - 2, _Q)


_D = -121665 * _inv(121666) % _Q
_I = pow(2, (_Q - 1) // 4, _Q)


def _xrecover(y: int) -> int:
    xx = (y * y - 1) * _inv(_D * y * y + 1) % _Q
    x = pow(xx, (_Q + 3) // 8, _Q)
    if (x * x - xx) % _Q != 0:
        x = x * _I % _Q
    if x % 2 != 0:
        x = _Q - x
    return x


_BY = 4 * _inv(5) % _Q
_B = (_xrecover(_BY) % _Q, _BY)
_IDENTITY = (0, 1)


def _edwards_add(left: tuple[int, int], right: tuple[int, int]) -> tuple[int, int]:
    x1, y1 = left
    x2, y2 = right
    product = _D * x1 * x2 * y1 * y2 % _Q
    x3 = (x1 * y2 + x2 * y1) * _inv(1 + product) % _Q
    y3 = (y1 * y2 + x1 * x2) * _inv(1 - product) % _Q
    return x3, y3


def _scalar_mult(point: tuple[int, int], scalar: int) -> tuple[int, int]:
    result = (0, 1)
    addend = point
    while scalar:
        if scalar & 1:
            result = _edwards_add(result, addend)
        addend = _edwards_add(addend, addend)
        scalar >>= 1
    return result


def _encode_int(value: int) -> bytes:
    return value.to_bytes(32, "little")


def _encode_point(point: tuple[int, int]) -> bytes:
    x, y = point
    return (y | ((x & 1) << 255)).to_bytes(32, "little")


def _is_on_curve(point: tuple[int, int]) -> bool:
    x, y = point
    return (-x * x + y * y - 1 - _D * x * x * y * y) % _Q == 0


def _decode_point(encoded: bytes) -> tuple[int, int]:
    if len(encoded) != 32:
        raise ValueError("Ed25519 point must be 32 bytes")
    y = int.from_bytes(encoded, "little") & ((1 << 255) - 1)
    if y >= _Q:
        raise ValueError("Ed25519 point y out of range")
    x = _xrecover(y)
    if (x & 1) != (encoded[31] >> 7):
        x = _Q - x
    if x >= _Q:
        raise ValueError("Ed25519 point has a non-canonical x coordinate")
    point = (x, y)
    if not _is_on_curve(point):
        raise ValueError("Ed25519 point is not on the curve")
    if _encode_point(point) != encoded:
        raise ValueError("Ed25519 point encoding is not canonical")
    return point


def _is_small_order(point: tuple[int, int]) -> bool:
    """True for identity and the other low-order points killed by [8]P."""
    return _scalar_mult(point, 8) == _IDENTITY


def _in_prime_order_subgroup(point: tuple[int, int]) -> bool:
    """Strict admission: P must satisfy [L]P == identity (no torsion component)."""
    return _scalar_mult(point, _L) == _IDENTITY


def _as_bytes(value: object) -> bytes | None:
    """Normalize bytes-like input; anything else is rejected, never coerced."""
    if isinstance(value, bytes):
        return value
    if isinstance(value, _BYTES_TYPES):
        return bytes(value)
    return None


def is_valid_public_key(public: bytes) -> bool:
    """True only for canonical, non-small-order, prime-order Ed25519 public keys."""
    encoded = _as_bytes(public)
    if encoded is None or len(encoded) != 32:
        return False
    try:
        point = _decode_point(encoded)
    except (ValueError, TypeError):
        return False
    if _is_small_order(point):
        return False
    return _in_prime_order_subgroup(point)


def _hash(message: bytes) -> bytes:
    return hashlib.sha512(message).digest()


def _hash_int(message: bytes) -> int:
    return int.from_bytes(_hash(message), "little") % _L


def _expand_seed(seed: bytes) -> tuple[int, bytes]:
    if len(seed) != 32:
        raise ValueError("Ed25519 seed must be 32 bytes")
    digest = _hash(seed)
    scalar = 2 ** (_BITS - 2)
    scalar += sum(2**i * ((digest[i // 8] >> (i % 8)) & 1) for i in range(3, _BITS - 2))
    prefix = digest[_BITS // 8:_BITS // 4]
    return scalar, prefix


def public_key(seed: bytes) -> bytes:
    """Test-only: derive the 32-byte public key for a 32-byte seed."""
    scalar, _ = _expand_seed(seed)
    return _encode_point(_scalar_mult(_B, scalar))


def sign(message: bytes, seed: bytes) -> bytes:
    """Test-only deterministic signature; the controller never holds a seed."""
    scalar, prefix = _expand_seed(seed)
    public = _encode_point(_scalar_mult(_B, scalar))
    nonce = _hash_int(prefix + message)
    encoded_r = _encode_point(_scalar_mult(_B, nonce))
    challenge = _hash_int(encoded_r + public + message)
    response = (nonce + challenge * scalar) % _L
    return encoded_r + _encode_int(response)


def verify(public: bytes, message: bytes, signature: bytes) -> bool:
    """Return True only for a valid RFC 8032 signature; malformed input is False.

    Every rejection is a plain ``False``: non-bytes input, wrong lengths, bad
    point decoding, non-canonical encodings, small-order/torsion points and
    out-of-range scalars never raise out of this function.
    """
    public_bytes = _as_bytes(public)
    message_bytes = _as_bytes(message)
    signature_bytes = _as_bytes(signature)
    if (public_bytes is None or message_bytes is None or signature_bytes is None
            or len(public_bytes) != 32 or len(signature_bytes) != 64):
        return False
    try:
        point_r = _decode_point(signature_bytes[:32])
        response = int.from_bytes(signature_bytes[32:], "little")
        if response >= _L:
            return False
        point_a = _decode_point(public_bytes)
    except (ValueError, TypeError):
        return False
    # Strict Ed25519: both signature R and public A must be canonical,
    # non-small-order and in the prime-order subgroup.
    if _is_small_order(point_r) or not _in_prime_order_subgroup(point_r):
        return False
    if _is_small_order(point_a) or not _in_prime_order_subgroup(point_a):
        return False
    challenge = _hash_int(signature_bytes[:32] + public_bytes + message_bytes)
    return _scalar_mult(_B, response) == _edwards_add(point_r, _scalar_mult(point_a, challenge))
