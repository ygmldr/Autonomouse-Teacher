"""ADR-002 canonical CallIdentity unit regression (offline, no Key/network)."""
import hashlib
import json

import pytest

from autoteacher_m0.accounting.call_identity import (CALL_ID_PATTERN, IdentitySchemaError,
                                                     CallIdentity, derive_call_id, is_call_id,
                                                     validate_call_id, validate_request_digest)


def test_canonical_call_id_derivation_is_stable_bounded_and_injective():
    first = derive_call_id("run-1", 0, 0, "a" * 64)
    assert first == derive_call_id("run-1", 0, 0, "a" * 64)
    assert CALL_ID_PATTERN.fullmatch(first)
    assert first.startswith("call-") and len(first) == 53
    assert first != derive_call_id("run-1", 1, 0, "a" * 64)
    assert first != derive_call_id("run-1", 0, 1, "a" * 64)
    assert first != derive_call_id("run-2", 0, 0, "a" * 64)
    assert first != derive_call_id("run-1", 0, 0, "b" * 64)
    canonical = json.dumps(CallIdentity("run-1", 0, 0, "a" * 64).canonical(), sort_keys=True,
                           separators=(",", ":"), allow_nan=False)
    assert first == "call-" + hashlib.sha256(canonical.encode()).hexdigest()[:48]


def test_legacy_egress_ids_are_not_settlement_identities():
    # ADR-002: old eg-... event ids are log-only; they are not canonical call ids.
    for legacy in ("eg-1234", "eg-" + "a" * 64, "call-short", "call-" + "A" * 48):
        assert not is_call_id(legacy)
        with pytest.raises(IdentitySchemaError):
            validate_call_id(legacy)


def test_identity_fields_are_strictly_validated():
    with pytest.raises(IdentitySchemaError):
        CallIdentity("run-1", -1, 0, "a" * 64)
    with pytest.raises(IdentitySchemaError):
        CallIdentity("run-1", 0, 0, "not-a-digest")
    with pytest.raises(IdentitySchemaError):
        CallIdentity("bad\x00run", 0, 0, "a" * 64)
    with pytest.raises(IdentitySchemaError):
        validate_request_digest("A" * 64)
    assert validate_request_digest("b" * 64) == "b" * 64


def test_observation_reexports_canonical_identity_for_v1_compatibility():
    from autoteacher_m0.accounting import CallIdentity as ExportedIdentity
    from autoteacher_m0.accounting import derive_call_id as exported_derive
    from autoteacher_m0.accounting import observation

    assert ExportedIdentity is observation.CallIdentity
    assert exported_derive is observation.derive_call_id
    assert ExportedIdentity("run-1", 0, 0, "a" * 64).call_id == derive_call_id("run-1", 0, 0, "a" * 64)


def test_observation_deliver_uses_the_same_canonical_call_id():
    from autoteacher_m0.accounting.observation import ObservationSchemaError, deliver_observation

    class Dummy:
        scope_id = "s"

    with pytest.raises((ObservationSchemaError, IdentitySchemaError, ValueError)):
        deliver_observation(Dummy(), "eg-legacy", None, reasoning_policy="inclusive",
                            cache_discount_approved=False)
