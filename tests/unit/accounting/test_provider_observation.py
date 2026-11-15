"""G1 accounting determinism regression: reasoning policy, conservative partial
usage, and trusted-egress observation provenance.

Runs only inside the isolated no-Key container pytest image. No network, no
credentials, no real model/HTTP. Real provider wire/invoice remains UNVERIFIED.
"""
from decimal import Decimal
import hashlib
import json

import pytest

from autoteacher_m0.accounting import (CallIdentity, ObservationSchemaError, ProviderObservation,
                                       deliver_observation, derive_call_id, mock_prices,
                                       observation_digest)
from autoteacher_m0.accounting.broker import BookkeepingBroker
from autoteacher_m0.accounting.broker_usage import UsagePolicy
from autoteacher_m0.accounting.observation import (TrustedEgressProvenance,
                                                   issue_trusted_egress_provenance)

CALL_A = "call-" + "a" * 48
CALL_B = "call-" + "b" * 48
RESERVED_COST = "0.00112"


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


def reserve(identity="reserve-1", call_id=CALL_A, **changes):
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


def provenance(call_id=CALL_A, request_digest="a" * 64, **changes):
    value = {"call_id": call_id, "request_digest": request_digest,
             "observed_route": "offline-test-only", "model_reported": "fixture-v1"}
    value.update(changes)
    return issue_trusted_egress_provenance(**value)


def reserve_broker(tmp_path, *, call_id=CALL_A, input_tokens=100, output_tokens=10, identity=None):
    broker = BookkeepingBroker(config(tmp_path))
    message_id = identity or ("reserve-1" if call_id is None else "reserve-" + call_id[5:])
    granted = broker.handle(reserve(identity=message_id, call_id=call_id,
                                    input_tokens=input_tokens, output_tokens=output_tokens))
    assert granted["dispatch_allowed"], granted
    return broker, granted["reservation_id"]


def deliver(broker, call_id, record, *, policy="inclusive", cache=False, trust=None):
    return deliver_observation(broker.ledger, call_id, record, reasoning_policy=policy,
                               cache_discount_approved=cache, provenance=trust)


# ---------------------------------------------------------------- A5 / OBS-01/02

def test_obs01_additional_reasoning_can_exceed_output_and_is_measured(tmp_path):
    record = observation(output=3, reasoning=9)
    # Structural schema is policy-neutral; explicit additional policy accepts it.
    record.validate_for_policy("additional")
    usage = record.to_usage(reserved_input=100, reserved_output=10, reasoning_policy="additional",
                            cache_discount_approved=True)
    assert usage.output_tokens == 12          # 3 output + 9 separately-billed reasoning
    assert usage.input_tokens == 12
    assert usage.estimated is False
    broker, reservation = reserve_broker(tmp_path)
    response = deliver(broker, CALL_A, record, policy="additional", cache=True, trust=provenance())
    assert response["ok"] and response["code"] == "SETTLED"
    # (10*1 + 2*0.5 + 12*2)/1e6 + 0.001 = 0.001035
    assert response["settlement"]["cost_usd"] == "0.001035"
    assert response["settlement"]["status"] == "OK"


def test_obs02_inclusive_reasoning_greater_than_output_is_rejected(tmp_path):
    record = observation(output=3, reasoning=9)
    from autoteacher_m0.accounting.observation import ObservationSchemaError as SchemaError
    with pytest.raises(SchemaError, match="inclusive reasoning exceeds output"):
        record.validate_for_policy("inclusive")
    broker, reservation = reserve_broker(tmp_path)
    with pytest.raises(SchemaError, match="inclusive reasoning exceeds output"):
        deliver(broker, CALL_A, record, policy="inclusive", cache=True, trust=provenance())
    assert broker.ledger.snapshot()["pending"] == 1


def test_additional_policy_requires_explicit_reasoning_count():
    record = observation(reasoning=None)
    record.validate_for_policy("inclusive")       # subset count not required for inclusive
    with pytest.raises(ObservationSchemaError, match="requires reasoning count"):
        record.validate_for_policy("additional")
    with pytest.raises(ObservationSchemaError, match="requires reasoning count"):
        record.to_usage(reserved_input=100, reserved_output=10, reasoning_policy="additional",
                        cache_discount_approved=False)


def test_reasoning_policy_and_cache_approval_must_be_explicit():
    record = observation()
    with pytest.raises(ObservationSchemaError, match="invalid reasoning_policy"):
        record.to_usage(reserved_input=100, reserved_output=10, reasoning_policy="guess",
                        cache_discount_approved=False)
    with pytest.raises(ObservationSchemaError, match="cache_discount_approved"):
        record.to_usage(reserved_input=100, reserved_output=10, reasoning_policy="inclusive",
                        cache_discount_approved=None)  # type: ignore[arg-type]


def test_route_policy_helpers_map_inclusive_and_additional():
    included = UsagePolicy("input_rate", "included_in_output")
    additional = UsagePolicy("input_rate", "additional_output")
    assert included.reasoning_policy == "inclusive"
    assert additional.reasoning_policy == "additional"


def test_authoritative_usage_maps_cache_and_inclusive_reasoning():
    record = observation()
    usage = record.to_usage(reserved_input=100, reserved_output=10, reasoning_policy="inclusive",
                            cache_discount_approved=True)
    assert usage.input_tokens == 12
    assert usage.cached_input_tokens == 2
    assert usage.output_tokens == 3           # reasoning is included in output
    assert usage.estimated is False
    assert usage.cost(mock_prices()) == Decimal("0.000017")
    assert record.accounting_status() == "SETTLED"

    no_discount = record.to_usage(reserved_input=100, reserved_output=10,
                                  reasoning_policy="inclusive", cache_discount_approved=False)
    assert no_discount.cached_input_tokens == 0   # conservative: no unapproved cache discount


def test_authoritative_cache_discount_requires_route_approval():
    record = observation()
    approved = record.to_usage(reserved_input=100, reserved_output=10, reasoning_policy="inclusive",
                               cache_discount_approved=True)
    unapproved = record.to_usage(reserved_input=100, reserved_output=10, reasoning_policy="inclusive",
                                 cache_discount_approved=False)
    assert approved.cost(mock_prices()) < unapproved.cost(mock_prices())


# ---------------------------------------------------------------- A6 / OBS-03

def test_obs03_partial_never_below_conservative_bound(tmp_path):
    shapes = [
        {"input": 7, "cache_read": None, "cache_write": None, "output": None, "reasoning": None,
         "complete_or_uncertain": "PARTIAL"},
        {"input": None, "cache_read": 5, "cache_write": None, "output": None, "reasoning": None,
         "complete_or_uncertain": "PARTIAL"},
        {"input": 7, "cache_read": 2, "cache_write": 3, "output": None, "reasoning": None,
         "cost_source": "provider_invoice", "cost_estimate": "0.0001",
         "complete_or_uncertain": "PARTIAL"},
        {"input": 7, "cache_read": 2, "cache_write": 3, "output": None, "reasoning": 1,
         "cost_source": "provider_invoice", "cost_estimate": "0.0001",
         "complete_or_uncertain": "PARTIAL"},
        {"input": None, "cache_read": None, "cache_write": None, "output": None, "reasoning": None,
         "usage_raw_hash": None, "complete_or_uncertain": "MISSING",
         "cost_source": "provider_invoice", "cost_estimate": "0.0001"},
    ]
    for index, shape in enumerate(shapes):
        call_id = "call-" + f"{index:048x}"[:48]
        broker, reservation = reserve_broker(tmp_path, call_id=call_id)
        record = observation(**shape)
        usage = record.to_usage(reserved_input=100, reserved_output=10, reasoning_policy="inclusive",
                                cache_discount_approved=True)
        assert usage.estimated is True
        assert usage.actual_cost_usd is None           # partial invoice actual never lowers cost
        assert usage.cached_input_tokens == 0          # no cache discount on partial data
        assert usage.input_tokens >= 100
        assert usage.output_tokens >= 10
        response = deliver(broker, call_id, record, policy="inclusive", cache=True, trust=provenance(call_id))
        assert response["ok"] and response["code"] == "WORST_CASE_HELD", (shape, response)
        assert response["settlement"]["cost_usd"] == RESERVED_COST, (shape, response["settlement"])
        assert response["settlement"]["status"] == "FAILED"
        assert broker.ledger.snapshot()["pending"] == 0


def test_partial_usage_holds_worst_case_not_zero():
    record = observation(input=7, cache_read=None, cache_write=None, output=None, reasoning=None,
                         complete_or_uncertain="PARTIAL")
    usage = record.to_usage(reserved_input=100, reserved_output=10, reasoning_policy="inclusive",
                            cache_discount_approved=False)
    assert usage.input_tokens == 100
    assert usage.cached_input_tokens == 0
    assert usage.output_tokens == 10
    assert usage.estimated is True
    assert record.accounting_status() == "WORST_CASE_HELD"


def test_t_usage_01_missing_usage_holds_full_reservation(tmp_path):
    record = observation(input=None, cache_read=None, cache_write=None, output=None, reasoning=None,
                         usage_raw_hash=None, complete_or_uncertain="MISSING")
    usage = record.to_usage(reserved_input=100, reserved_output=10, reasoning_policy="inclusive",
                            cache_discount_approved=False)
    assert (usage.input_tokens, usage.output_tokens) == (100, 10)
    assert usage.estimated is True and usage.actual_cost_usd is None
    broker, reservation = reserve_broker(tmp_path)
    response = deliver(broker, CALL_A, record)
    assert response["ok"] and response["code"] == "WORST_CASE_HELD"
    assert response["settlement"]["status"] == "FAILED"
    assert response["settlement"]["cost_usd"] == RESERVED_COST
    assert broker.ledger.snapshot()["pending"] == 0


# ---------------------------------------------------- A7 / OBS-05/06 + INT-15

def test_int15_untrusted_authoritative_does_not_settle_then_trusted_can_upgrade(tmp_path):
    broker, reservation = reserve_broker(tmp_path)
    record = observation()
    rejected = deliver(broker, CALL_A, record)      # no provenance
    assert not rejected["ok"] and rejected["code"] == "UNAUTHORIZED_OBSERVATION"
    assert rejected["reservation_pending"] is True
    assert broker.ledger.snapshot()["pending"] == 1
    # A rejected delivery is not persisted, so trusted egress can still settle
    # the same call/observation once (auditable upgrade path).
    settled = deliver(broker, CALL_A, record, cache=True, trust=provenance())
    assert settled["ok"] and settled["code"] == "SETTLED" and settled["duplicate"] is False
    assert broker.ledger.snapshot()["pending"] == 0


def test_obs06_untrusted_provider_invoice_is_rejected(tmp_path):
    broker, reservation = reserve_broker(tmp_path)
    record = observation(cost_source="provider_invoice", cost_estimate="0.0001")
    response = deliver(broker, CALL_A, record, cache=True)
    assert not response["ok"] and response["code"] == "UNAUTHORIZED_OBSERVATION"
    assert broker.ledger.snapshot()["pending"] == 1
    trusted = deliver(broker, CALL_A, record, cache=True, trust=provenance())
    assert trusted["ok"] and trusted["code"] == "SETTLED"
    # Trusted, complete invoice actual is allowed and recorded as actual.
    assert trusted["settlement"]["cost_usd"] == "0.0001"
    assert trusted["settlement"]["cost_kind"] == "actual"


def test_obs05_route_or_model_mismatch_is_not_settled(tmp_path):
    cases = [
        {"requested_route": "other-route"},
        {"observed_route": "other-route"},
        {"model_reported": "other-model"},
    ]
    for index, changes in enumerate(cases):
        call_id = "call-" + f"{index + 10:048x}"[:48]
        broker, reservation = reserve_broker(tmp_path / f"case{index}", call_id=call_id)
        record = observation(**changes)
        response = deliver(broker, call_id, record, cache=True, trust=provenance(call_id))
        assert not response["ok"] and response["code"] == "ROUTE_MISMATCH", (changes, response)
        assert response["reservation_pending"] is True
        assert broker.ledger.snapshot()["pending"] == 1
    # Provenance itself claiming a different route is also rejected.
    call_id = CALL_B
    broker, reservation = reserve_broker(tmp_path / "provenance", call_id=call_id)
    response = deliver(broker, call_id, observation(),
                       cache=True, trust=provenance(call_id, observed_route="other-route"))
    assert response["code"] == "ROUTE_MISMATCH"
    assert broker.ledger.snapshot()["pending"] == 1


def test_forged_provenance_and_mismatched_call_id_are_rejected(tmp_path):
    broker, reservation = reserve_broker(tmp_path)
    with pytest.raises(ObservationSchemaError, match="untrusted provenance"):
        TrustedEgressProvenance(call_id=CALL_A, request_digest="a" * 64,
                                observed_route="offline-test-only", model_reported="fixture-v1")
    with pytest.raises(ObservationSchemaError, match="untrusted provenance"):
        deliver(broker, CALL_A, observation(), cache=True, trust={"source": "trusted"})  # type: ignore[arg-type]
    other = provenance(CALL_B)
    with pytest.raises(ObservationSchemaError, match="call_id mismatch"):
        deliver(broker, CALL_A, observation(), cache=True, trust=other)
    assert broker.ledger.snapshot()["pending"] == 1


def test_untrusted_partial_remains_allowed_and_conservative(tmp_path):
    broker, reservation = reserve_broker(tmp_path)
    record = observation(input=7, cache_read=None, cache_write=None, output=None, reasoning=None,
                         complete_or_uncertain="PARTIAL")
    response = deliver(broker, CALL_A, record)
    assert response["ok"] and response["code"] == "WORST_CASE_HELD"
    assert response["settlement"]["cost_usd"] == RESERVED_COST


# ------------------------------------------------------------- idempotency etc.

def test_authoritative_delivery_settles_and_duplicate_is_idempotent(tmp_path):
    broker, reservation = reserve_broker(tmp_path)
    record = observation()
    trust = provenance()
    first = deliver(broker, CALL_A, record, cache=True, trust=trust)
    assert first["ok"] and first["code"] == "SETTLED" and first["duplicate"] is False
    assert first["settlement"]["cost_usd"] == "0.001017"
    before = broker.ledger.snapshot()
    replay = deliver(broker, CALL_A, record, cache=True, trust=trust)
    assert replay["duplicate"] is True and replay["code"] == "SETTLED"
    assert broker.ledger.snapshot() == before
    conflict = observation(output=4)
    with pytest.raises(ValueError, match="observation identity conflict"):
        deliver(broker, CALL_A, conflict, cache=True, trust=trust)


def test_unknown_observation_stays_pending_uncertain(tmp_path):
    record = observation(input=None, cache_read=None, cache_write=None, output=None, reasoning=None,
                         usage_raw_hash=None, cost_estimate=None, cost_source="unknown",
                         error_kind="transport", complete_or_uncertain="UNKNOWN")
    assert record.accounting_status() == "SETTLEMENT_UNCERTAIN"
    broker, reservation = reserve_broker(tmp_path)
    response = deliver(broker, CALL_A, record)
    assert not response["ok"] and response["code"] == "SETTLEMENT_UNCERTAIN"
    assert response["reservation_pending"] is True
    assert broker.ledger.snapshot()["pending"] == 1
    replay = deliver(broker, CALL_A, record)
    assert replay["duplicate"] is True and replay["code"] == "SETTLEMENT_UNCERTAIN"


def test_delivery_requires_bound_call_identity(tmp_path):
    broker, _ = reserve_broker(tmp_path, call_id=None)
    response = deliver(broker, CALL_A, observation())
    assert not response["ok"] and response["code"] == "UNKNOWN_CALL"
    assert broker.ledger.call_reservation(CALL_A) is None


def test_broker_links_call_id_and_refuses_retarget(tmp_path):
    broker, reservation = reserve_broker(tmp_path, call_id=CALL_A)
    assert broker.ledger.call_reservation(CALL_A) == reservation
    second = broker.handle(reserve(identity="reserve-2", call_id=CALL_A))
    assert second["code"] == "CALL_ID_CONFLICT" and not second["dispatch_allowed"]
    assert broker.ledger.snapshot()["requests"] == 1
    other = broker.handle(reserve(identity="reserve-3", call_id=CALL_B))
    assert other["dispatch_allowed"]


def test_call_identity_is_stable_bounded_and_injective():
    first = derive_call_id("run-1", 0, 0, "a" * 64)
    assert first == derive_call_id("run-1", 0, 0, "a" * 64)
    assert first.startswith("call-") and len(first) <= 96
    assert first != derive_call_id("run-1", 1, 0, "a" * 64)
    assert first != derive_call_id("run-1", 0, 1, "a" * 64)
    assert first != derive_call_id("run-2", 0, 0, "a" * 64)
    canonical = json.dumps(CallIdentity("run-1", 0, 0, "a" * 64).canonical(), sort_keys=True,
                           separators=(",", ":"), allow_nan=False)
    expected = "call-" + hashlib.sha256(canonical.encode()).hexdigest()[:48]
    assert first == expected
    with pytest.raises(ObservationSchemaError):
        derive_call_id("run-1", 0, 0, "not-a-hash")


@pytest.mark.parametrize("changes", [
    {"input": True}, {"input": -1}, {"input": 10 ** 12}, {"usage_raw_hash": "A" * 64},
    {"cost_source": "free_magic"}, {"error_kind": "panic"}, {"complete_or_uncertain": "DONE"},
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
