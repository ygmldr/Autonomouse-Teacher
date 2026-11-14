"""F1/F2 targeted regression: journal capacity split and logical-stream slots.

Runs only inside the isolated, credential-free container pytest image. These tests
are added by v0.5 PR1; they do not rewrite any historical evidence.
"""
from concurrent.futures import ThreadPoolExecutor


from autoteacher_m0.accounting.broker import BookkeepingBroker


def config(tmp_path, *, max_messages=8, limits=None):
    value = {"v": 1, "synthetic": True, "db_path": str(tmp_path / "broker.sqlite3"),
             "scope_id": "fixed-offline-scope", "max_messages": max_messages,
             "limits": {"soft_usd": "3", "hard_usd": "10", "per_call_usd": "0.20",
                        "max_requests": 50, "max_input_tokens": 2500000,
                        "max_output_tokens": 600000, "max_steps": 8, "max_retries": 1},
             "routes": [{"route_id": "offline-test-only", "model": "fixture-v1",
                         "price": {"version": "synthetic-v1", "input_per_million": "1",
                                   "output_per_million": "2", "cached_input_per_million": "0.5",
                                   "source": "synthetic fixture", "captured_at": "2026-11-13"},
                         "known_extra_fee_usd": "0.001",
                         "usage_policy": {"cache_write": "input_rate", "reasoning": "included_in_output"}}]}
    if limits:
        value["limits"].update(limits)
    return value


def reserve(identity="reserve-1", task="session-1", retry=False):
    return {"v": 1, "id": identity, "op": "reserve", "task_id": task,
            "route_id": "offline-test-only", "model": "fixture-v1", "purpose": "conversation",
            "input_tokens": 20, "output_tokens": 10, "retry": retry}


def usage():
    return {"inputTokens": 7, "cacheReadTokens": 0, "cacheWriteTokens": 0,
            "outputTokens": 3, "reasoningTokens": 0, "totalTokens": 10, "actual_cost_usd": None}


def complete(token, identity="settle-1", op="settle"):
    return {"v": 1, "id": identity, "op": op, "reservation_id": token, "usage": usage()}


def snapshot(broker, identity="state"):
    return broker.handle({"v": 1, "id": identity, "op": "snapshot"})


def journal_rows(broker):
    with broker.ledger._transaction() as database:
        return database.execute("SELECT COUNT(*) FROM budget_broker_messages WHERE scope_id=?",
                                (broker.ledger.scope_id,)).fetchone()[0]


def test_t_journal_01_capacity_boundaries_one_two_three(tmp_path):
    # max_messages=1 cannot admit a reservation: reserve row + completion slot > cap.
    one = BookkeepingBroker(config(tmp_path / "one", max_messages=1))
    assert one.handle(reserve())["code"] == "MESSAGE_LIMIT"
    assert one.ledger.snapshot()["pending"] == 0
    assert snapshot(one)["ok"] and journal_rows(one) == 0

    # max_messages=2 admits exactly one reservation and reserves its completion.
    two = BookkeepingBroker(config(tmp_path / "two", max_messages=2))
    first = two.handle(reserve())
    assert first["dispatch_allowed"]
    assert two.handle(reserve("reserve-2"))["code"] == "MESSAGE_LIMIT"
    assert journal_rows(two) == 1
    assert two.handle(complete(first["reservation_id"]))["ok"]
    assert journal_rows(two) == 2 == two.max_messages
    assert snapshot(two)["snapshot"]["pending"] == 0
    assert two.handle(reserve("reserve-3"))["code"] == "MESSAGE_LIMIT"

    # max_messages=3 also admits one reservation (existing pending capacity plus
    # the new reservation/completion pair would exceed three).
    three = BookkeepingBroker(config(tmp_path / "three", max_messages=3))
    a = three.handle(reserve())
    assert a["dispatch_allowed"]
    assert three.handle(reserve("reserve-2"))["code"] == "MESSAGE_LIMIT"
    assert three.handle(complete(a["reservation_id"]))["ok"]
    assert journal_rows(three) == 2 <= three.max_messages
    assert snapshot(three)["ok"]
    assert three.handle(reserve("reserve-3"))["code"] == "MESSAGE_LIMIT"


def test_t_journal_01_completion_after_cap_and_duplicate_idempotence(tmp_path):
    broker = BookkeepingBroker(config(tmp_path, max_messages=2))
    first = broker.handle(reserve())
    assert first["dispatch_allowed"]
    assert broker.handle(reserve("reserve-2"))["code"] == "MESSAGE_LIMIT"
    # Snapshot remains independently readable after the journal is full.
    seen = snapshot(broker)
    assert seen["ok"] and seen["snapshot"]["pending"] == 1
    settled = broker.handle(complete(first["reservation_id"]))
    assert settled["code"] == "SETTLED"
    before = broker.ledger.snapshot()
    replay = broker.handle(complete(first["reservation_id"], identity="settle-2"))
    assert replay["code"] == "ALREADY_SETTLED" and not replay["dispatch_allowed"]
    assert broker.ledger.snapshot() == before
    assert journal_rows(broker) == 2
    assert snapshot(broker)["ok"]


def test_t_journal_01_completion_precedes_message_limit_check(tmp_path):
    broker = BookkeepingBroker(config(tmp_path, max_messages=4))
    a = broker.handle(reserve("reserve-a"))
    b = broker.handle(reserve("reserve-b"))
    assert a["dispatch_allowed"] and b["dispatch_allowed"]
    assert broker.handle(reserve("reserve-c"))["code"] == "MESSAGE_LIMIT"
    assert broker.handle(complete(a["reservation_id"], identity="settle-a"))["ok"]
    assert broker.handle(complete(b["reservation_id"], op="fail", identity="settle-b"))["ok"]
    assert journal_rows(broker) == 4 == broker.max_messages
    assert broker.ledger.snapshot()["pending"] == 0
    assert snapshot(broker)["ok"]


def test_t_journal_03_pending_survives_restart_and_completes_once(tmp_path):
    setup = config(tmp_path, max_messages=2)
    first = BookkeepingBroker(setup)
    granted = first.handle(reserve())
    assert granted["dispatch_allowed"]
    # A fresh broker process (same durable DB/policy) sees the pending reservation.
    restarted = BookkeepingBroker(setup)
    state = snapshot(restarted)
    assert state["snapshot"]["pending"] == 1 and state["snapshot"]["requests"] == 1
    # The restart cannot grant the same logical stream again.
    replay = restarted.handle(reserve())
    assert replay["duplicate"] and not replay["dispatch_allowed"]
    assert replay["code"] == "DUPLICATE_NO_DISPATCH"
    assert restarted.handle(complete(granted["reservation_id"], identity="settle-after-restart"))["ok"]
    assert restarted.ledger.snapshot()["pending"] == 0
    assert restarted.ledger.snapshot()["requests"] == 1


def test_t_retry_01_two_logical_streams_consume_two_step_and_request_slots(tmp_path):
    setup = config(tmp_path, limits={"max_steps": 2, "max_requests": 10, "max_retries": 1})
    broker = BookkeepingBroker(setup)
    first = broker.handle(reserve("reserve-1"))
    second = broker.handle(reserve("reserve-2"))
    assert first["dispatch_allowed"] and second["dispatch_allowed"]
    # Every logical stream counts as a step, whether or not a retry label exists.
    denied = broker.handle(reserve("reserve-3"))
    assert denied["code"] == "BUDGET_EXCEEDED"
    assert broker.ledger.snapshot()["blocked"] is True
    assert broker.ledger.snapshot()["requests"] == 2
    with broker.ledger._transaction() as database:
        rows = database.execute("SELECT retry FROM budget_reservations WHERE scope_id=?",
                                (broker.ledger.scope_id,)).fetchall()
    assert [row[0] for row in rows] == [0, 0]


def test_t_retry_01_request_slots_are_shared_not_reset_by_new_task(tmp_path):
    setup = config(tmp_path, limits={"max_steps": 8, "max_requests": 2, "max_retries": 1})
    broker = BookkeepingBroker(setup)
    assert broker.handle(reserve("reserve-1", task="task-a"))["dispatch_allowed"]
    assert broker.handle(reserve("reserve-2", task="task-b"))["dispatch_allowed"]
    assert broker.handle(reserve("reserve-3", task="task-c"))["code"] == "BUDGET_EXCEEDED"
    assert broker.ledger.snapshot()["requests"] == 2


def test_t_retry_02_absent_attempt_metadata_uses_no_retry_quota(tmp_path):
    setup = config(tmp_path, limits={"max_steps": 8, "max_requests": 8, "max_retries": 0})
    broker = BookkeepingBroker(setup)
    # retry=false is an attribution-only legacy field; two logical streams are
    # admitted by step/request slots and never consume the retry quota.
    assert broker.handle(reserve("reserve-1", retry=False))["dispatch_allowed"]
    assert broker.handle(reserve("reserve-2", retry=False))["dispatch_allowed"]
    # A caller that self-declares retry=true with max_retries=0 gets the retry
    # limit; missing attempt metadata is never treated as free retry quota.
    assert broker.handle(reserve("reserve-3", retry=True))["code"] == "BUDGET_EXCEEDED"
    assert broker.ledger.snapshot()["requests"] == 2


def test_t_journal_concurrent_completion_contends_for_last_slot(tmp_path):
    setup = config(tmp_path, max_messages=4)
    broker = BookkeepingBroker(setup)
    first = broker.handle(reserve("reserve-1"))
    second = broker.handle(reserve("reserve-2"))
    assert first["dispatch_allowed"] and second["dispatch_allowed"]
    assert broker.handle(reserve("reserve-3"))["code"] == "MESSAGE_LIMIT"
    # Two writers race for the last completion slots; both completions must land
    # exactly once with no duplicate journal rows.
    outcomes = {
        broker.handle(complete(first["reservation_id"], identity="settle-1"))["code"],
        broker.handle(complete(second["reservation_id"], identity="settle-2"))["code"],
        broker.handle(complete(first["reservation_id"], identity="settle-3"))["code"],
        broker.handle(complete(second["reservation_id"], identity="settle-4"))["code"],
    }
    assert outcomes == {"SETTLED", "ALREADY_SETTLED"}
    assert journal_rows(broker) == 4
    assert broker.ledger.snapshot()["pending"] == 0


def test_reservation_replay_after_capacity_denial_never_dispatches(tmp_path):
    broker = BookkeepingBroker(config(tmp_path, max_messages=2))
    first = broker.handle(reserve())
    assert first["dispatch_allowed"]
    assert broker.handle(reserve("reserve-2"))["code"] == "MESSAGE_LIMIT"
    # Replaying a previously granted reservation (even after cap) never re-grants.
    replay = broker.handle(reserve())
    assert replay["duplicate"] and replay["code"] == "DUPLICATE_NO_DISPATCH"
    assert not replay["dispatch_allowed"]
    assert broker.ledger.snapshot()["requests"] == 1


def test_t_journal_concurrent_threads_contend_for_last_completion_slots(tmp_path):
    setup = config(tmp_path, max_messages=4)
    broker = BookkeepingBroker(setup)
    first = broker.handle(reserve("reserve-1"))
    second = broker.handle(reserve("reserve-2"))
    assert first["dispatch_allowed"] and second["dispatch_allowed"]
    assert broker.handle(reserve("reserve-3"))["code"] == "MESSAGE_LIMIT"
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(broker.handle, complete(first["reservation_id"], identity="settle-1")),
            pool.submit(broker.handle, complete(second["reservation_id"], identity="settle-2")),
        ]
        outcomes = sorted(future.result()["code"] for future in futures)
    # Both reserved completion slots are available under contention, and no
    # duplicate journal row is created beyond the hard capacity.
    assert outcomes == ["SETTLED", "SETTLED"]
    assert journal_rows(broker) == 4 == broker.max_messages
    assert broker.ledger.snapshot()["pending"] == 0
