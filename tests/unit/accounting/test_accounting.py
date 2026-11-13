from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest

from autoteacher_m0.accounting import (BudgetExceeded, BudgetGuard, BudgetLimits,
                                     PriceSnapshot, Usage, conservative_input_bound,
                                     normalize_usage)


def prices():
    return PriceSnapshot("mock", "deepseek-flash", "test", 1_000_000, 2_000_000,
                         500_000, "synthetic", "2026-11-14", mock=True)


def guard(**overrides):
    values = {"hard_usd": Decimal("10"), "soft_usd": Decimal("3"), "per_call_usd": Decimal("20")}
    values.update(overrides)
    return BudgetGuard(prices(), BudgetLimits(**values))


def reserve(g, **overrides):
    values = {"task_id": "task", "route_id": "mock", "model": "deepseek-flash",
              "input_tokens": 1, "output_tokens": 1}
    values.update(overrides)
    return g.reserve(**values)


def test_channel_specific_cost_cached_and_actual_bill():
    assert prices().cost(4, 2, 2, 1) == Decimal("8")
    assert Usage(4, 2, 2, actual_cost_usd=Decimal("0.25"), extra_fees_usd=9).cost(prices()) == Decimal("0.25")


def test_missing_usage_never_zero_including_failed_requests():
    g = guard()
    token = reserve(g)
    entry = g.fail(token)
    assert entry["estimated"] is True and entry["status"] == "FAILED"
    assert entry["cost_usd"] == "3"
    assert g.snapshot()["pending"] == 0
    assert g.snapshot()["requests"] == 1


def test_partial_missing_usage_uses_full_missing_bound():
    usage = normalize_usage(1, None, reserved_input=5, reserved_output=7)
    assert (usage.input_tokens, usage.output_tokens, usage.estimated) == (1, 7, True)
    assert conservative_input_bound("中") >= 3 + 256


@pytest.mark.parametrize("mode", ["missing", "partial", "known"])
def test_known_extra_fee_is_never_refunded_on_missing_bill(mode):
    g = guard()
    token = reserve(g, extra_fees_usd="2")
    usage = None if mode == "missing" else (
        normalize_usage(1, None, reserved_input=1, reserved_output=1) if mode == "partial" else Usage(1, 1))
    entry = g.fail(token, usage)
    assert Decimal(entry["cost_usd"]) == 5
    assert Decimal(g.snapshot()["spent_usd"]) == 5


def test_actual_total_invoice_includes_fees_without_double_count():
    g = guard()
    token = reserve(g, extra_fees_usd=2)
    entry = g.settle(token, Usage(1, 1, actual_cost_usd=Decimal("4")))
    assert entry["cost_kind"] == "actual" and Decimal(entry["cost_usd"]) == 4


def test_inflight_reservation_blocks_concurrent_oversubscription():
    g = guard(hard_usd=6)
    def attempt(index):
        try:
            return reserve(g, task_id=str(index))
        except BudgetExceeded:
            return None
    with ThreadPoolExecutor(max_workers=4) as pool:
        tokens = [token for token in pool.map(attempt, range(8)) if token]
    assert len(tokens) == 2
    assert g.snapshot()["reserved_usd"] == "6"
    assert g.snapshot()["requests"] == 2


def test_retries_count_as_requests_and_steps_and_stay_bounded():
    g = guard(hard_usd=100, max_steps=2, max_retries=1)
    first = reserve(g)
    g.fail(first)
    second = reserve(g, retry=True)
    g.fail(second)
    with pytest.raises(BudgetExceeded, match="step"):
        reserve(g)
    assert g.snapshot()["requests"] == 2
    other = reserve(g, task_id="other", retry=True)
    g.fail(other)
    with pytest.raises(BudgetExceeded, match="retry"):
        reserve(g, task_id="other", retry=True)


def test_request_limit_not_refunded_by_failure():
    g = guard(max_requests=1)
    g.fail(reserve(g))
    with pytest.raises(BudgetExceeded, match="request"):
        reserve(g, task_id="different")


def test_exact_hard_limit_blocks_any_further_request():
    g = guard(hard_usd=3)
    g.settle(reserve(g), Usage(1, 1))
    with pytest.raises(BudgetExceeded, match="already reached"):
        reserve(g)


@pytest.mark.parametrize("axis", ["input", "output"])
def test_pending_and_settled_token_caps(axis):
    g = guard(**{"max_" + axis + "_tokens": 1})
    token = reserve(g)
    with pytest.raises(BudgetExceeded, match="token"):
        reserve(g, task_id="other")
    g.settle(token, Usage(1, 1))
    with pytest.raises(BudgetExceeded, match="already reached"):
        reserve(g, task_id="third")


def test_per_call_blocked_before_any_request_or_entry():
    g = guard(per_call_usd=2)
    with pytest.raises(BudgetExceeded, match="per-call"):
        reserve(g)
    assert g.snapshot()["requests"] == 0
    assert not g.entries


def test_case_limit_is_tighter_than_global_per_call_limit():
    g = guard()
    with pytest.raises(BudgetExceeded, match="per-call"):
        reserve(g, max_cost_usd=2)
    assert g.snapshot()["requests"] == 0


def test_overrun_honestly_recorded_then_fail_closed():
    g = guard()
    entry = g.settle(reserve(g), Usage(4, 2))
    assert entry["reservation_exceeded"] and Decimal(g.snapshot()["spent_usd"]) == 8
    with pytest.raises(BudgetExceeded, match="previous settlement"):
        reserve(g)


def test_double_settlement_and_channel_mismatch_rejected():
    g = guard()
    token = reserve(g)
    g.settle(token, Usage(1, 1))
    with pytest.raises(ValueError, match="already settled"):
        g.settle(token, Usage(1, 1))
    with pytest.raises(ValueError, match="channel"):
        reserve(g, route_id="openrouter")
    assert g.snapshot()["requests"] == 1


@pytest.mark.parametrize("value", [-1, "NaN", "Infinity"])
def test_invalid_price_or_fee_rejected(value):
    with pytest.raises(ValueError):
        PriceSnapshot("mock", "deepseek-flash", "v", value, 1, 1, "test", "today", True)


def test_price_provenance_and_usage_bounds():
    with pytest.raises(ValueError):
        PriceSnapshot("live", "deepseek-flash", "v", 0, 0, 0, "source", "today")
    with pytest.raises(ValueError):
        normalize_usage(None, None, reserved_input=0, reserved_output=5)
    with pytest.raises(ValueError):
        Usage(2, 1, cached_input_tokens=3)
    with pytest.raises(ValueError):
        reserve(guard(), input_tokens=True)
