"""PR4b ProviderObservation/usage mapping and call-identity regression.

Runs only inside the isolated no-Key container pytest image. No network, no
credentials, no real model/HTTP. Real provider wire mapping remains UNVERIFIED.
"""
from decimal import Decimal
import hashlib
import json

import pytest

from autoteacher_m0.accounting import (CallIdentity, ObservationSchemaError, ProviderObservation,
                                       deliver_observation, derive_call_id, mock_prices,
                                       observation_digest)
from autoteacher_m0.accounting.broker import BookkeepingBroker


def config(tmp_path):
    return {"v": 1, "synthetic": True, "db_path": str(tmp_path / "broker.sqlite3"),
            "scope_id": "fixed-offline-scope", "max_messages": 32,
            "limits": {"soft_usd": "3", "hard_usd": "10", "per_call_usd": "0.20",
                       "max_requests": 50, "max_input_tokens": 2500000,
                       "max_output_tokens": 600000, "max_steps": 8, "max_retries": 1},
            "routes": [{"route_id": "offline-test-only", "model": "fixture-v1",
                        "price": {"version": "synthetic-v1", "input_per_million": "1",
                                  "output_per_million": "2", "cached_input_per_million": "0.5",
                                  "source": "synthetic fixture", "captured_at": "2026-11-13"},
                        "known_extra_fee_usd": "0.001",
                        "usage_policy": {"cache_write": "input_rate", "reasoning": "included_in_output"}}]}


def reserve(identity="reserve-1", call_id="call-" + "a" * 48, **changes):
    value = {"v": 1, "id": identity, "op": "reserve", "task_id": "session-1",
             "route_id": "offline-test-only", "model": "fixture-v1", "purpose": "conversation",
             "input_tokens": 100, "output_tokens": 10, "retry": False}
    if call_id is not None:
        value["call_id"] = call_id
    value.update(changes)
    return value


def observation(**changes):
    value = {"requested_route": "offline-test-only", "observed_route": "offline-test-only",
             "model_reported": "fixture-v1", "provider_request_id": "provider-request-1",
             "usage_raw_hash": "a" * 64, "input": 7, "cache_read": 2, "cache_write": 3,
             "output": 3, "reasoning": 1, "cost_estimate": None,
             "cost_source": "synthetic_fixture_cost", "error_kind": "none",
             "complete_or_uncertain": "AUTHORITATIVE"}
    value.update(changes)
    return ProviderObservation.from_mapping(value)


def reserve_broker(tmp_path, *, call_id="call-" + "a" * 48, input_tokens=100, output_tokens=10):
    broker = BookkeepingBroker(config(tmp_path))
    granted = broker.handle(reserve(call_id=call_id, input_tokens=input_tokens, output_tokens=output_tokens))
    assert granted["dispatch_allowed"], granted
    return broker, granted["reservation_id"]


def test_authoritative_usage_maps_cache_and_inclusive_reasoning():
    record = observation()
    usage = record.to_usage(reserved_input=100, reserved_output=10)
    assert usage.input_tokens == 12          # 7 uncached + 2 cache-read + 3 cache-write
    assert usage.cached_input_tokens == 2
    assert usage.output_tokens == 3          # reasoning is included in output
    assert usage.estimated is False
    assert usage.cost(mock_prices()) == Decimal("0.000017")
    assert record.accounting_status() == "SETTLED"

    additional = record.to_usage(reserved_input=100, reserved_output=10, reasoning_in_output=False)
    assert additional.output_tokens == 4
    assert additional.estimated is False


def test_partial_usage_holds_worst_case_not_zero():
    record = observation(input=7, cache_read=None, cache_write=None, output=None, reasoning=None,
                         complete_or_uncertain="PARTIAL")
    usage = record.to_usage(reserved_input=100, reserved_output=10)
    assert usage.input_tokens == 100          # missing cache dimensions -> full input bound
    assert usage.cached_input_tokens == 0     # no unverified cache discount
    assert usage.output_tokens == 10          # missing output -> full output bound
    assert usage.estimated is True
    assert record.accounting_status() == "WORST_CASE_HELD"


def test_t_usage_01_missing_usage_holds_full_reservation(tmp_path):
    record = observation(input=None, cache_read=None, cache_write=None, output=None, reasoning=None,
                         usage_raw_hash=None, complete_or_uncertain="MISSING")
    usage = record.to_usage(reserved_input=100, reserved_output=10)
    assert (usage.input_tokens, usage.output_tokens) == (100, 10)
    assert usage.estimated is True and usage.actual_cost_usd is None
    assert record.accounting_status() == "WORST_CASE_HELD"
    broker, reservation = reserve_broker(tmp_path)
    response = deliver_observation(broker.ledger, "call-" + "a" * 48, record)
    assert response["ok"] and response["code"] == "WORST_CASE_HELD"
    assert response["settlement"]["status"] == "FAILED"
    assert response["settlement"]["cost_usd"] == "0.00112"  # full reserved bound, not zero
    assert broker.ledger.snapshot()["pending"] == 0


def test_unknown_observation_stays_pending_uncertain(tmp_path):
    record = observation(input=None, cache_read=None, cache_write=None, output=None, reasoning=None,
                         usage_raw_hash=None, cost_estimate=None, cost_source="unknown",
                         error_kind="transport", complete_or_uncertain="UNKNOWN")
    assert record.accounting_status() == "SETTLEMENT_UNCERTAIN"
    broker, reservation = reserve_broker(tmp_path)
    response = deliver_observation(broker.ledger, "call-" + "a" * 48, record)
    assert not response["ok"] and response["code"] == "SETTLEMENT_UNCERTAIN"
    assert response["reservation_pending"] is True
    assert broker.ledger.snapshot()["pending"] == 1
    replay = deliver_observation(broker.ledger, "call-" + "a" * 48, record)
    assert replay["duplicate"] is True and replay["code"] == "SETTLEMENT_UNCERTAIN"


def test_authoritative_delivery_settles_and_duplicate_is_idempotent(tmp_path):
    broker, reservation = reserve_broker(tmp_path)
    record = observation(cost_source="synthetic_fixture_cost")
    first = deliver_observation(broker.ledger, "call-" + "a" * 48, record)
    assert first["ok"] and first["code"] == "SETTLED" and first["duplicate"] is False
    assert first["settlement"]["cost_usd"] == "0.001017"
    before = broker.ledger.snapshot()
    replay = deliver_observation(broker.ledger, "call-" + "a" * 48, record)
    assert replay["duplicate"] is True and replay["code"] == "SETTLED"
    assert broker.ledger.snapshot() == before
    conflict = observation(output=4)
    assert conflict.complete_or_uncertain == "AUTHORITATIVE"
    with pytest.raises(ValueError, match="observation identity conflict"):
        deliver_observation(broker.ledger, "call-" + "a" * 48, conflict)


def test_delivery_requires_bound_call_identity(tmp_path):
    broker, _ = reserve_broker(tmp_path, call_id=None)
    response = deliver_observation(broker.ledger, "call-" + "a" * 48, observation())
    assert not response["ok"] and response["code"] == "UNKNOWN_CALL"
    assert broker.ledger.call_reservation("call-" + "a" * 48) is None


def test_broker_links_call_id_and_refuses_retarget(tmp_path):
    broker, reservation = reserve_broker(tmp_path, call_id="call-" + "a" * 48)
    assert broker.ledger.call_reservation("call-" + "a" * 48) == reservation
    second = broker.handle(reserve(identity="reserve-2", call_id="call-" + "a" * 48))
    assert second["code"] == "CALL_ID_CONFLICT" and not second["dispatch_allowed"]
    assert broker.ledger.snapshot()["requests"] == 1
    other = broker.handle(reserve(identity="reserve-3", call_id="call-" + "b" * 48))
    assert other["dispatch_allowed"]


def test_call_identity_is_stable_bounded_and_injective():
    first = derive_call_id("run-1", 0, 0, "a" * 64)
    assert first == derive_call_id("run-1", 0, 0, "a" * 64)
    assert first.startswith("call-") and len(first) <= 96
    assert first != derive_call_id("run-1", 1, 0, "a" * 64)
    assert first != derive_call_id("run-1", 0, 1, "a" * 64)
    assert first != derive_call_id("run-2", 0, 0, "a" * 64)
    assert first != derive_call_id("run-1", 0, 0, "b" * 64)
    canonical = json.dumps(CallIdentity("run-1", 0, 0, "a" * 64).canonical(), sort_keys=True,
                           separators=(",", ":"), allow_nan=False)
    expected = "call-" + hashlib.sha256(canonical.encode()).hexdigest()[:48]
    assert first == expected
    with pytest.raises(ObservationSchemaError):
        derive_call_id("run-1", 0, 0, "not-a-hash")
    with pytest.raises(ObservationSchemaError):
        derive_call_id("bad\nrun", 0, 0, "a" * 64)


@pytest.mark.parametrize("changes", [
    {"input": True}, {"input": -1}, {"input": 10 ** 12}, {"usage_raw_hash": "A" * 64},
    {"cost_source": "free_magic"}, {"error_kind": "panic"}, {"complete_or_uncertain": "DONE"},
    {"reasoning": 9, "output": 3},  # inclusive reasoning exceeds output
    {"requested_route": ""}, {"requested_route": "bad\x00route"},
])
def test_observation_schema_rejects_invalid_fields(changes):
    with pytest.raises(ObservationSchemaError):
        observation(**changes)


@pytest.mark.parametrize("changes", [
    {"complete_or_uncertain": "AUTHORITATIVE", "output": None},
    {"complete_or_uncertain": "AUTHORITATIVE", "usage_raw_hash": None},
    {"complete_or_uncertain": "PARTIAL", "input": None, "cache_read": None, "cache_write": None,
     "output": None, "reasoning": None},
    {"complete_or_uncertain": "MISSING"},
    {"complete_or_uncertain": "UNKNOWN", "input": None, "cache_read": None, "cache_write": None,
     "output": None, "reasoning": None, "usage_raw_hash": None},
])
def test_observation_completeness_rules(changes):
    with pytest.raises(ObservationSchemaError):
        observation(**changes)


def test_unknown_or_missing_schema_keys_are_rejected():
    payload = observation().to_mapping()
    extra = dict(payload, leaked_sdk_field="x")
    with pytest.raises(ObservationSchemaError, match="unknown or missing observation schema"):
        ProviderObservation.from_mapping(extra)
    missing = dict(payload)
    missing.pop("usage_raw_hash")
    with pytest.raises(ObservationSchemaError, match="unknown or missing observation schema"):
        ProviderObservation.from_mapping(missing)
    with pytest.raises(ObservationSchemaError):
        ProviderObservation.from_mapping([payload])


def test_observation_digest_is_canonical_and_stable():
    first = observation_digest(observation())
    assert first == observation_digest(observation())
    assert first != observation_digest(observation(provider_request_id="other"))
    assert len(first) == 64
    assert int(first, 16) >= 0
