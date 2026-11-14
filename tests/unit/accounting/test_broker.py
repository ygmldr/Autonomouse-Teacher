from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from decimal import Decimal
import io
import json

import pytest

from autoteacher_m0.accounting import BudgetGuard, BudgetLedger, BudgetLimits, PriceSnapshot
from autoteacher_m0.accounting.broker import BookkeepingBroker, MAX_FRAME, serve, strict_json


def config(tmp_path):
    return {"v": 1, "synthetic": True, "db_path": str(tmp_path / "broker.sqlite3"),
            "scope_id": "fixed-offline-scope", "max_messages": 4096,
            "limits": {"soft_usd": "3", "hard_usd": "10", "per_call_usd": "0.20",
                       "max_requests": 50, "max_input_tokens": 2500000,
                       "max_output_tokens": 600000, "max_steps": 8, "max_retries": 1},
            "routes": [{"route_id": "offline-test-only", "model": "fixture-v1",
                        "price": {"version": "synthetic-v1", "input_per_million": "1",
                                  "output_per_million": "2", "cached_input_per_million": "0.5",
                                  "source": "synthetic fixture", "captured_at": "2026-11-13"},
                        "known_extra_fee_usd": "0.001",
                        "usage_policy": {"cache_write": "input_rate", "reasoning": "included_in_output"}}]}


def request(identity="reserve-1", **changes):
    value = {"v": 1, "id": identity, "op": "reserve", "task_id": "session-1",
             "route_id": "offline-test-only", "model": "fixture-v1", "purpose": "conversation",
             "input_tokens": 20, "output_tokens": 10, "retry": False}
    value.update(changes)
    return value


def settle(token, usage=None, identity="settle-1", op="settle"):
    return {"v": 1, "id": identity, "op": op, "reservation_id": token, "usage": usage}


def usage(**changes):
    value = {"inputTokens": 7, "cacheReadTokens": 2, "cacheWriteTokens": 3,
             "outputTokens": 3, "reasoningTokens": 1, "totalTokens": 15, "actual_cost_usd": None}
    value.update(changes)
    return value


def test_reserve_commit_replay_never_grants_again_even_after_restart(tmp_path):
    setup = config(tmp_path)
    broker = BookkeepingBroker(setup)
    first = broker.handle(request())
    assert first["ok"] and first["dispatch_allowed"] and not first["duplicate"]
    replay = BookkeepingBroker(setup).handle(request())
    assert replay["ok"] and not replay["dispatch_allowed"] and replay["duplicate"]
    assert replay["code"] == "DUPLICATE_NO_DISPATCH"
    assert replay["reservation_id"] == first["reservation_id"]
    assert broker.ledger.snapshot()["requests"] == 1
    conflict = broker.handle(request(output_tokens=11))
    assert conflict["code"] == "IDEMPOTENCY_CONFLICT" and not conflict["dispatch_allowed"]


def test_complete_official_disjoint_cache_and_reasoning_mapping(tmp_path):
    broker = BookkeepingBroker(config(tmp_path))
    token = broker.handle(request())["reservation_id"]
    reply = broker.handle(settle(token, usage()))
    assert reply["ok"] and not reply["dispatch_allowed"]
    result = reply["settlement"]
    assert result["input_tokens"] == 12 and result["cached_input_tokens"] == 2
    assert result["output_tokens"] == 3  # reasoning already included, not +1
    assert Decimal(result["cost_usd"]) == Decimal("0.001017")
    assert reply["usage_mapping"]["cache_write_tokens"] == 3
    assert not result["estimated"]


def test_additional_reasoning_is_billed_once_and_missing_reasoning_is_conservative(tmp_path):
    setup = config(tmp_path)
    setup["routes"][0]["usage_policy"]["reasoning"] = "additional_output"
    broker = BookkeepingBroker(setup)
    token = broker.handle(request())["reservation_id"]
    answer = broker.handle(settle(token, usage(totalTokens=16)))
    assert answer["settlement"]["output_tokens"] == 4
    token2 = broker.handle(request("reserve-2"))["reservation_id"]
    reply = broker.handle(settle(token2, usage(reasoningTokens=None), "settle-2"))
    assert reply["settlement"]["estimated"]
    assert reply["settlement"]["output_tokens"] == 10
    assert Decimal(reply["settlement"]["cost_usd"]) >= Decimal("0.00104")


@pytest.mark.parametrize("raw", [None, {}, {"inputTokens": 7, "outputTokens": 3},
                                 {"inputTokens": None, "cacheReadTokens": 2, "cacheWriteTokens": 3}])
def test_unknown_usage_and_known_fee_are_not_refunded(tmp_path, raw):
    setup = config(tmp_path)
    broker = BookkeepingBroker(setup)
    token = broker.handle(request())["reservation_id"]
    reply = BookkeepingBroker(setup).handle(settle(token, raw, op="fail"))
    assert reply["ok"] and reply["settlement"]["estimated"]
    assert Decimal(reply["settlement"]["cost_usd"]) >= Decimal("0.00104")
    assert reply["settlement"]["status"] == "FAILED"
    assert broker.ledger.snapshot()["pending"] == 0


def test_actual_inclusive_invoice_not_double_charged_even_without_tokens(tmp_path):
    broker = BookkeepingBroker(config(tmp_path))
    token = broker.handle(request())["reservation_id"]
    reply = broker.handle(settle(token, {"actual_cost_usd": "0.0009"}))
    assert reply["settlement"]["cost_usd"] == "0.0009"
    assert reply["settlement"]["cost_kind"] == "actual"
    assert reply["settlement"]["estimated"]  # tokens remain estimated


def test_duplicate_settlement_same_or_new_id_cannot_double_charge_or_refund(tmp_path):
    broker = BookkeepingBroker(config(tmp_path))
    token = broker.handle(request())["reservation_id"]
    original = broker.handle(settle(token, usage()))
    snapshot = broker.ledger.snapshot()
    replay = broker.handle(settle(token, usage()))
    assert replay["duplicate"] and replay["settlement"] == original["settlement"]
    assert not replay["dispatch_allowed"]
    assert broker.handle(settle(token, usage(), "another-id"))["code"] == "ALREADY_SETTLED"
    assert broker.handle(settle(token, None, "different-fail", "fail"))["code"] == "ALREADY_SETTLED"
    assert broker.ledger.snapshot() == snapshot
    assert broker.handle(settle(token, None))["code"] == "IDEMPOTENCY_CONFLICT"


@pytest.mark.parametrize("raw", [
    {"unpriced_dimension": 100}, {"cacheWriteTokens": -1}, {"outputTokens": True},
    {"inputTokens": "7"}, {"actual_cost_usd": 0.001}, {"actual_cost_usd": "NaN"},
    usage(totalTokens=900), usage(reasoningTokens=99),
])
def test_invalid_usage_keeps_full_pending_reservation(tmp_path, raw):
    broker = BookkeepingBroker(config(tmp_path))
    token = broker.handle(request())["reservation_id"]
    reply = broker.handle(settle(token, raw))
    assert reply["code"] == "INVALID_USAGE" and not reply["dispatch_allowed"]
    assert broker.ledger.snapshot()["pending"] == 1
    assert broker.ledger.snapshot()["reserved_usd"] == "0.00104"


def test_overrun_and_budget_denial_are_persistent_across_restart_and_routes(tmp_path):
    setup = config(tmp_path)
    other = deepcopy(setup["routes"][0])
    other["route_id"] = "offline-test-only-secondary"
    setup["routes"].append(other)
    broker = BookkeepingBroker(setup)
    token = broker.handle(request())["reservation_id"]
    reply = broker.handle(settle(token, usage(actual_cost_usd="1")))
    assert reply["settlement"]["reservation_exceeded"]
    denied = BookkeepingBroker(setup).handle(request("other", route_id=other["route_id"]))
    assert denied["code"] == "BUDGET_EXCEEDED"
    assert broker.ledger.snapshot()["requests"] == 1 and broker.ledger.snapshot()["blocked"]


def test_denial_is_monotonic_after_earlier_reservation_is_settled_cheaply(tmp_path):
    setup = config(tmp_path)
    setup["limits"].update(soft_usd="0.00104", hard_usd="0.00104")
    broker = BookkeepingBroker(setup)
    token = broker.handle(request())["reservation_id"]
    assert broker.handle(request("denial"))["code"] == "BUDGET_EXCEEDED"
    assert broker.handle(settle(token, usage(actual_cost_usd="0.001")))["ok"]
    assert BookkeepingBroker(setup).handle(request("attempt-after-release"))["code"] == "BUDGET_EXCEEDED"


def test_concurrent_brokers_share_atomic_journal_and_single_grant(tmp_path):
    setup = config(tmp_path)
    BookkeepingBroker(setup)
    def attempt(_):
        return BookkeepingBroker(setup).handle(request())
    with ThreadPoolExecutor(max_workers=4) as pool:
        replies = list(pool.map(attempt, range(12)))
    assert sum(reply["dispatch_allowed"] for reply in replies) == 1
    assert len({reply["reservation_id"] for reply in replies}) == 1
    assert BookkeepingBroker(setup).ledger.snapshot()["requests"] == 1


def test_ledger_nested_mutations_and_journal_roll_back_together(tmp_path):
    broker = BookkeepingBroker(config(tmp_path))
    def crash(database):
        broker.ledger.reserve(task_id="t", prices=next(iter(broker.routes.values())).prices,
                              input_tokens=10, output_tokens=10)
        raise RuntimeError("FAKE_EXCEPTION_PAYLOAD_DO_NOT_ECHO")
    with pytest.raises(RuntimeError):
        broker.ledger.journal_once("crash", "digest", crash)
    assert broker.ledger.snapshot()["requests"] == 0
    assert broker.handle(request())["dispatch_allowed"]


def test_broken_ack_keeps_reservation_and_suppresses_regrant(tmp_path):
    setup = config(tmp_path)
    broker = BookkeepingBroker(setup)
    class BrokenOutput:
        def write(self, value):
            raise BrokenPipeError("FAKE_SENSITIVE_PAYLOAD")
    result = serve(broker, io.BytesIO((json.dumps(request()) + "\n").encode()), BrokenOutput())
    assert result == 3 and broker.ledger.snapshot()["pending"] == 1
    assert not BookkeepingBroker(setup).handle(request())["dispatch_allowed"]


@pytest.mark.parametrize("mutation", [
    lambda c: c["limits"].update(hard_usd="20"),
    lambda c: c["routes"][0]["price"].update(input_per_million="5"),
    lambda c: c["routes"][0].update(known_extra_fee_usd="0"),
    lambda c: c["routes"][0]["usage_policy"].update(reasoning="additional_output"),
    lambda c: c.update(scope_id="new-scope"),
    lambda c: c.update(max_messages=5000),
])
def test_durable_policy_drift_is_refused(tmp_path, mutation):
    setup = config(tmp_path)
    broker = BookkeepingBroker(setup)
    token = broker.handle(request())["reservation_id"]
    changed = deepcopy(setup)
    mutation(changed)
    with pytest.raises(ValueError):
        BookkeepingBroker(changed)
    assert broker.ledger.snapshot()["pending"] == 1
    assert broker.handle(settle(token, None))["ok"]


def test_additive_migration_preserves_old_budgetledger_pending(tmp_path):
    setup = config(tmp_path)
    old = BudgetLedger(setup["db_path"], scope_id=setup["scope_id"])
    price = PriceSnapshot("offline-test-only", "fixture-v1", "legacy", 1, 2, "0.5", "test", "today", True)
    token = old.reserve(task_id="legacy-task", prices=price, input_tokens=10, output_tokens=10,
                        extra_fees_usd="0.001")
    broker = BookkeepingBroker(setup)
    assert broker.ledger.snapshot()["pending"] == 1
    result = broker.handle(settle(token.reservation_id, None))
    assert result["settlement"]["cost_usd"] == "0.00103"
    assert result["settlement"]["price_version"] == "legacy"


@pytest.mark.parametrize("old_fee,new_fee", [("0.001", "0.01"), ("0.01", "0.001")])
@pytest.mark.parametrize("usage_kind", ["complete", "partial", "missing", "actual_invoice"])
@pytest.mark.parametrize("operation", ["settle", "fail"])
def test_legacy_migration_preserves_original_fee_and_price_snapshot(
        tmp_path, old_fee, new_fee, usage_kind, operation):
    setup = config(tmp_path)
    legacy = BudgetLedger(setup["db_path"], scope_id=setup["scope_id"])
    original_prices = PriceSnapshot("offline-test-only", "fixture-v1", "legacy-price",
                                   1, 2, "0.5", "synthetic legacy", "2026-11-13", True)
    token = legacy.reserve(task_id="already-dispatched", prices=original_prices,
                           input_tokens=100, output_tokens=10, extra_fees_usd=old_fee)
    # First broker binding may introduce a new policy for FUTURE requests, but
    # cannot reprice a legacy request whose original snapshot is already stored.
    setup["routes"][0]["known_extra_fee_usd"] = new_fee
    setup["routes"][0]["price"].update(version="startup-new-price", input_per_million="10",
                                      output_per_million="20", cached_input_per_million="5")
    broker = BookkeepingBroker(setup)
    complete = usage(inputTokens=7, cacheReadTokens=0, cacheWriteTokens=0,
                     outputTokens=3, reasoningTokens=0, totalTokens=10)
    raw = {"complete": complete, "partial": {"inputTokens": 7, "outputTokens": None},
           "missing": None, "actual_invoice": dict(complete, actual_cost_usd="0.0009")}[usage_kind]
    message = settle(token.reservation_id, raw, op=operation)
    answer = broker.handle(message)
    expected = (Decimal("0.0009") if usage_kind == "actual_invoice" else
                original_prices.cost(7, 3, extra_fees=old_fee) if usage_kind == "complete" else token.cost_usd)
    assert answer["ok"], answer
    result = answer["settlement"]
    assert Decimal(result["cost_usd"]) == expected
    assert result["price_version"] == "legacy-price"
    assert result["status"] == ("FAILED" if operation == "fail" else "OK")
    assert result["estimated"] == (usage_kind in {"partial", "missing"})
    assert result["cost_kind"] == ("actual" if usage_kind == "actual_invoice" else "estimated")
    assert not result["reservation_exceeded"]
    state = BookkeepingBroker(setup).ledger.snapshot()
    assert not state["blocked"] and state["pending"] == 0 and state["requests"] == 1
    assert Decimal(state["spent_usd"]) == expected
    # Replays and a second correlation ID do not change the correctly priced bill.
    assert broker.handle(message)["duplicate"]
    assert broker.handle(dict(message, id="different-settlement"))["code"] == "ALREADY_SETTLED"
    assert broker.ledger.snapshot() == state
    future = broker.handle(request("future-request", task_id="future-task", input_tokens=100, output_tokens=10))
    assert future["dispatch_allowed"]  # no false overrun latch from old fee
    assert future["reservation"]["extra_fees_usd"] == new_fee
    assert Decimal(future["reservation"]["cost_usd"]) == Decimal(new_fee) + Decimal("0.0012")


def test_no_invoice_estimates_never_refund_more_expensive_cache_path(tmp_path):
    price = PriceSnapshot("mock", "fixture", "v", 1, 2, 5, "test", "today", True)
    g = BudgetGuard(price)
    token = g.reserve(task_id="t", route_id="mock", model="fixture", input_tokens=10, output_tokens=10)
    assert Decimal(g.fail(token)["cost_usd"]) == token.cost_usd
    book = BudgetLedger(tmp_path / "legacy.db", scope_id="s")
    token = book.reserve(task_id="t", prices=price, input_tokens=10, output_tokens=10)
    assert Decimal(book.fail(token)["cost_usd"]) == token.cost_usd


@pytest.mark.parametrize("message", [[], {"v": True, "id": "x", "op": "snapshot"},
    {"v": 1, "id": "x", "op": []}, request(input_tokens=True), request(output_tokens=-1),
    request(retry=1), request(purpose="unknown"), request(extra_key="/tmp/FAKE_PRIVATE_PATH"),
    request(db_path="/tmp/new.sqlite3"), request(scope_id="new"), request(prices={}),
    request(task_id="../private"), request(id="x" * 100)])
def test_strict_message_schema_no_mutation_or_arbitrary_echo(tmp_path, message):
    broker = BookkeepingBroker(config(tmp_path))
    reply = broker.handle(message)
    assert not reply["dispatch_allowed"] and reply["code"] == "INVALID_MESSAGE"
    assert broker.ledger.snapshot()["requests"] == 0
    assert "FAKE_PRIVATE_PATH" not in str(reply)


@pytest.mark.parametrize("raw", [b'{"v":1,"v":1}\n', b'{"x":1.0}\n', b'{"x":NaN}\n', b'\xff\n'])
def test_strict_json_rejects_duplicate_float_nan_and_invalid_utf8(raw):
    with pytest.raises((ValueError, UnicodeError)):
        strict_json(raw)


def test_transport_frame_limits_and_normal_protocol_recovery(tmp_path):
    broker = BookkeepingBroker(config(tmp_path))
    for raw, expected in ((b"x" * (MAX_FRAME + 1), "FRAME_TOO_LARGE"),
                          (b'{"v":1}', "INCOMPLETE_FRAME")):
        output = io.BytesIO()
        assert serve(broker, io.BytesIO(raw), output) == 2
        assert json.loads(output.getvalue())["code"] == expected
    output = io.BytesIO()
    raw = b'not-json\n' + json.dumps({"v": 1, "id": "s", "op": "snapshot"}).encode() + b"\n"
    assert serve(broker, io.BytesIO(raw), output) == 0
    replies = [json.loads(line) for line in output.getvalue().splitlines()]
    assert replies[0]["code"] == "INVALID_MESSAGE" and replies[1]["code"] == "SNAPSHOT"


def test_complete_tokens_without_invoice_can_release_and_money_is_plain_decimal(tmp_path):
    setup = config(tmp_path)
    setup["routes"][0]["known_extra_fee_usd"] = "0"
    broker = BookkeepingBroker(setup)
    first = broker.handle(request(input_tokens=1, output_tokens=1))
    assert first["reservation"]["cost_usd"] == "0.000003"
    raw = usage(inputTokens=0, cacheReadTokens=1, cacheWriteTokens=0, outputTokens=0,
                reasoningTokens=0, totalTokens=1)
    reply = broker.handle(settle(first["reservation_id"], raw))
    assert reply["settlement"]["cost_usd"] == "0.0000005"
    assert reply["settlement"]["cost_kind"] == "estimated"  # no dollar invoice
    assert not reply["settlement"]["estimated"]  # complete, authoritative tokens
    assert broker.ledger.snapshot()["spent_usd"] == "0.0000005"
    assert "E-" not in json.dumps(reply)
    # The plain output is valid under the protocol's decimal-string input rule.
    from autoteacher_m0.accounting.broker_usage import decimal_string
    assert decimal_string(reply["settlement"]["cost_usd"]) == Decimal("0.0000005")


def test_legacy_scientific_policy_strings_migrate_without_relaxing_limits(tmp_path):
    book = BudgetLedger(tmp_path / "legacy.db", scope_id="s", limits=BudgetLimits(
        soft_usd=Decimal("1E-7"), hard_usd=Decimal("1E-6"), per_call_usd=Decimal("1E-7")))
    with book._transaction() as database:
        raw = database.execute("SELECT limits_json FROM budget_scopes WHERE scope_id='s'").fetchone()[0]
        old = json.loads(raw)
        old.update(soft_usd="1E-7", hard_usd="1E-6", per_call_usd="1E-7")
        database.execute("UPDATE budget_scopes SET limits_json=? WHERE scope_id='s'", (json.dumps(old),))
    restarted = BudgetLedger(tmp_path / "legacy.db", scope_id="s", limits=BudgetLimits(
        soft_usd=Decimal("0.0000001"), hard_usd=Decimal("0.000001"), per_call_usd=Decimal("0.0000001")))
    assert restarted.snapshot()["requests"] == 0


@pytest.mark.parametrize("limit_name", ["max_requests", "max_steps", "max_retries"])
def test_broker_forwards_persistent_request_step_and_retry_caps(tmp_path, limit_name):
    setup = config(tmp_path)
    setup["limits"][limit_name] = 1
    broker = BookkeepingBroker(setup)
    attempt = request(retry=limit_name == "max_retries")
    assert broker.handle(attempt)["dispatch_allowed"]
    assert BookkeepingBroker(setup).handle(dict(attempt, id="second"))["code"] == "BUDGET_EXCEEDED"
    assert broker.ledger.snapshot()["requests"] == 1


def test_two_allowed_fixture_routes_cannot_reset_shared_hard_budget(tmp_path):
    setup = config(tmp_path)
    setup["limits"].update(soft_usd="0.00208", hard_usd="0.00208")
    second_route = deepcopy(setup["routes"][0])
    second_route["route_id"] = "offline-test-only-secondary"
    setup["routes"].append(second_route)
    broker = BookkeepingBroker(setup)
    assert broker.handle(request())["dispatch_allowed"]
    assert BookkeepingBroker(setup).handle(request("second", route_id=second_route["route_id"]))["dispatch_allowed"]
    assert broker.handle(request("third"))["code"] == "BUDGET_EXCEEDED"
    assert broker.ledger.snapshot()["committed_usd"] == "0.00208"
    assert broker.ledger.snapshot()["routes"] == ["offline-test-only", "offline-test-only-secondary"]


def test_unexpected_exception_payload_is_fixed_sanitized_error(tmp_path, monkeypatch):
    broker = BookkeepingBroker(config(tmp_path))
    def broken(*args, **kwargs):
        raise RuntimeError("sk-FAKE_EXCEPTION_PAYLOAD_PRIVATE_PATH")
    monkeypatch.setattr(broker.ledger, "journal_once", broken)
    answer = broker.handle(request())
    assert answer["code"] == "INTERNAL_ERROR" and not answer["dispatch_allowed"]
    assert "FAKE_EXCEPTION" not in json.dumps(answer)


def test_message_journal_cap_preserves_existing_identities_and_pending(tmp_path):
    setup = config(tmp_path)
    setup["max_messages"] = 1
    broker = BookkeepingBroker(setup)
    # F2: reserve admission also reserves one future settle/fail journal slot,
    # so a journal limit of one message cannot admit any reservation at all.
    denied = broker.handle(request())
    assert denied["code"] == "MESSAGE_LIMIT" and not denied["dispatch_allowed"]
    assert broker.ledger.snapshot()["pending"] == 0
    # A replay of the denied reservation must not grant one either.
    assert not broker.handle(request())["dispatch_allowed"]


def test_message_journal_cap_completes_existing_pending_and_snapshot(tmp_path):
    setup = config(tmp_path)
    setup["max_messages"] = 2
    broker = BookkeepingBroker(setup)
    first = broker.handle(request())
    assert first["dispatch_allowed"]
    # One reservation row plus its reserved completion slot fill the journal.
    assert broker.handle(request("new"))["code"] == "MESSAGE_LIMIT"
    snapshot = broker.handle({"v": 1, "id": "state", "op": "snapshot"})
    assert snapshot["ok"] and snapshot["snapshot"]["pending"] == 1
    completed = broker.handle(settle(first["reservation_id"]))
    assert completed["ok"] and completed["code"] == "SETTLED"
    assert broker.ledger.snapshot()["pending"] == 0
    # Repeating the completion is idempotent: no second charge, no extra row.
    assert broker.handle(settle(first["reservation_id"], identity="settle-2"))["code"] == "ALREADY_SETTLED"
    assert broker.ledger.snapshot()["requests"] == 1
    # The journal is permanently full for new reservations; snapshots stay readable.
    assert broker.handle(request("third"))["code"] == "MESSAGE_LIMIT"
    assert broker.handle({"v": 1, "id": "state-2", "op": "snapshot"})["ok"]
