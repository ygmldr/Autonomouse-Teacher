from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import subprocess
import sys

import pytest

from autoteacher_m0.accounting import (BudgetExceeded, BudgetLedger, BudgetLimits,
                                     PriceSnapshot, Usage, normalize_usage)


def prices(route="official"):
    return PriceSnapshot(route, "deepseek-flash", "test", 1_000_000, 2_000_000,
                         500_000, "synthetic offline", "2026-11-14", mock=True)


def limits(**changes):
    values = {"hard_usd": Decimal("10"), "soft_usd": Decimal("3"), "per_call_usd": Decimal("20")}
    values.update(changes)
    return BudgetLimits(**values)


def ledger(path, **changes):
    return BudgetLedger(path, scope_id="approved-global", limits=limits(**changes))


def reserve(book, *, route="official", task="task", **changes):
    args = {"task_id": task, "prices": prices(route), "input_tokens": 1, "output_tokens": 1}
    args.update(changes)
    return book.reserve(**args)


def test_pending_survives_restart_and_never_refunds_automatically(tmp_path):
    path = tmp_path / "budget.sqlite3"
    first = ledger(path, hard_usd=3)
    token = reserve(first)
    restarted = ledger(path, hard_usd=3)
    assert restarted.snapshot()["reserved_usd"] == "3"
    assert restarted.snapshot()["pending"] == 1
    with pytest.raises(BudgetExceeded):
        reserve(restarted, route="openrouter")
    entry = restarted.fail(token.reservation_id)
    assert entry["estimated"] and entry["cost_usd"] == "3"
    assert ledger(path, hard_usd=3).snapshot()["spent_usd"] == "3"
    with pytest.raises(BudgetExceeded):
        reserve(ledger(path, hard_usd=3))


def test_two_routes_share_persistent_total_and_request_count(tmp_path):
    path = tmp_path / "budget.sqlite3"
    first = ledger(path, hard_usd=6)
    first.settle(reserve(first), Usage(1, 1))
    second = ledger(path, hard_usd=6)
    second.settle(reserve(second, route="openrouter", task="other"), Usage(1, 1))
    assert second.snapshot()["routes"] == ["official", "openrouter"]
    assert second.snapshot()["spent_usd"] == "6"
    assert first.snapshot()["requests"] == 2
    with pytest.raises(BudgetExceeded):
        reserve(first, route="third", task="third")


def test_policy_cannot_be_silently_raised_on_restart(tmp_path):
    path = tmp_path / "budget.sqlite3"
    ledger(path)
    with pytest.raises(ValueError, match="policy differs"):
        ledger(path, hard_usd=100)


def test_parallel_independent_connections_cannot_overreserve(tmp_path):
    path = tmp_path / "budget.sqlite3"
    ledger(path, hard_usd=6)
    def attempt(index):
        try:
            return reserve(ledger(path, hard_usd=6), task=str(index))
        except BudgetExceeded:
            return None
    with ThreadPoolExecutor(max_workers=4) as pool:
        tokens = [token for token in pool.map(attempt, range(8)) if token]
    assert len(tokens) == 2
    assert ledger(path, hard_usd=6).snapshot()["committed_usd"] == "6"


def test_independent_processes_share_atomic_budget(tmp_path):
    path = tmp_path / "process.sqlite3"
    ledger(path, hard_usd=6)
    script = '''
import sys
from autoteacher_m0.accounting import BudgetLedger, BudgetLimits, PriceSnapshot, BudgetExceeded
book=BudgetLedger(sys.argv[1],scope_id="approved-global",limits=BudgetLimits(hard_usd=6,soft_usd=3,per_call_usd=20))
price=PriceSnapshot(sys.argv[2],"deepseek-flash","test",1000000,2000000,500000,"synthetic offline","2026-11-14",mock=True)
try:
 book.reserve(task_id=sys.argv[2],prices=price,input_tokens=1,output_tokens=1)
 print("RESERVED")
except BudgetExceeded:
 print("BLOCKED")
'''
    processes = [subprocess.Popen([sys.executable, "-B", "-c", script, str(path), str(index)],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                 for index in range(4)]
    outputs = []
    for process in processes:
        stdout, stderr = process.communicate(timeout=15)
        assert process.returncode == 0, stderr
        outputs.append(stdout.strip())
    assert outputs.count("RESERVED") == 2 and outputs.count("BLOCKED") == 2
    assert ledger(path, hard_usd=6).snapshot()["pending"] == 2


@pytest.mark.parametrize("partial", [False, True])
def test_fees_survive_failures_and_partial_usage_after_restart(tmp_path, partial):
    path = tmp_path / "budget.sqlite3"
    token = reserve(ledger(path), extra_fees_usd=2)
    usage = normalize_usage(1, None, reserved_input=1, reserved_output=1) if partial else None
    entry = ledger(path).fail(token.reservation_id, usage)
    assert entry["cost_usd"] == "5"
    assert entry["estimated"]
    with pytest.raises(ValueError):
        ledger(path).fail(token.reservation_id)


def test_actual_bill_and_original_price_snapshot_are_used(tmp_path):
    path = tmp_path / "budget.sqlite3"
    token = reserve(ledger(path), extra_fees_usd=2)
    entry = ledger(path).settle(token, Usage(1, 1, actual_cost_usd=4))
    assert entry["cost_usd"] == "4" and entry["price_version"] == "test"


def test_overrun_trips_shared_scope_in_future_process_instances(tmp_path):
    path = tmp_path / "budget.sqlite3"
    token = reserve(ledger(path))
    entry = ledger(path).settle(token, Usage(5, 1))
    assert entry["reservation_exceeded"] and entry["cost_usd"] == "7"
    assert ledger(path).snapshot()["blocked"]
    with pytest.raises(BudgetExceeded):
        reserve(ledger(path), route="another")


def test_steps_retries_and_tokens_remain_counted_on_restart(tmp_path):
    path = tmp_path / "budget.sqlite3"
    first = ledger(path, max_steps=2, max_retries=1)
    first.fail(reserve(first))
    second = ledger(path, max_steps=2, max_retries=1)
    second.fail(reserve(second, retry=True))
    with pytest.raises(BudgetExceeded, match="step"):
        reserve(ledger(path, max_steps=2, max_retries=1))
    other_path = tmp_path / "request.sqlite3"
    book = ledger(other_path, max_requests=1)
    book.fail(reserve(book))
    with pytest.raises(BudgetExceeded, match="request"):
        reserve(ledger(other_path, max_requests=1), task="another")


def test_case_limit_cannot_exceed_global_call_limit(tmp_path):
    book = ledger(tmp_path / "budget.sqlite3")
    with pytest.raises(BudgetExceeded, match="per-call"):
        reserve(book, max_cost_usd=2)
    assert book.snapshot()["requests"] == 0


def test_memory_database_and_empty_scope_are_rejected(tmp_path):
    with pytest.raises(ValueError):
        BudgetLedger(":memory:", scope_id="x")
    with pytest.raises(ValueError):
        BudgetLedger(tmp_path / "file.db", scope_id="")
