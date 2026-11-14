"""Every child in this module is launched ONLY by isolated-container pytest."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from autoteacher_m0.accounting.broker import BookkeepingBroker


def setup_file(tmp_path):
    config = {"v": 1, "synthetic": True, "db_path": str(tmp_path / "ledger.sqlite3"),
              "scope_id": "fixed-offline-scope", "max_messages": 4096,
              "limits": {"soft_usd": "3", "hard_usd": "10", "per_call_usd": "0.20",
                         "max_requests": 50, "max_input_tokens": 2500000,
                         "max_output_tokens": 600000, "max_steps": 8, "max_retries": 1},
              "routes": [{"route_id": "offline-test-only", "model": "fixture-v1",
                          "price": {"version": "fixture-v1", "input_per_million": "1",
                                    "output_per_million": "2", "cached_input_per_million": "0.5",
                                    "source": "synthetic fixture", "captured_at": "2026-11-13"},
                          "known_extra_fee_usd": "0.001",
                          "usage_policy": {"cache_write": "input_rate", "reasoning": "included_in_output"}}]}
    path = tmp_path / "startup.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return config, path


def reserve(identity="stream-001"):
    return {"v": 1, "id": identity, "op": "reserve", "task_id": "session-001",
            "route_id": "offline-test-only", "model": "fixture-v1", "purpose": "conversation",
            "input_tokens": 100, "output_tokens": 50, "retry": False}


def argv(path):
    return [sys.executable, "-B", "-m", "autoteacher_m0.accounting.broker", "--config", str(path)]


def run(path, messages):
    data = "".join(json.dumps(message) + "\n" for message in messages)
    process = subprocess.run(argv(path), input=data, text=True, capture_output=True, timeout=10)
    assert process.returncode == 0, (process.returncode, process.stdout, process.stderr)
    assert process.stderr == ""
    return [json.loads(line) for line in process.stdout.splitlines()]


def test_real_stdio_restart_duplicate_and_inclusive_usage(tmp_path):
    config, path = setup_file(tmp_path)
    first = run(path, [reserve()])[0]
    assert first["dispatch_allowed"] and first["ok"]
    second = run(path, [reserve()])[0]
    assert not second["dispatch_allowed"] and second["duplicate"]
    assert second["reservation_id"] == first["reservation_id"]
    settle = {"v": 1, "id": "settle-001", "op": "settle", "reservation_id": first["reservation_id"],
              "usage": {"inputTokens": 7, "cacheReadTokens": 0, "cacheWriteTokens": 0,
                        "outputTokens": 3, "reasoningTokens": 0, "totalTokens": 10}}
    replies = run(path, [settle, settle, {"v": 1, "id": "state", "op": "snapshot"}])
    assert replies[0]["settlement"]["cost_usd"] == "0.001013"
    assert replies[1]["duplicate"] and not replies[1]["dispatch_allowed"]
    assert replies[2]["snapshot"]["requests"] == 1 and replies[2]["snapshot"]["pending"] == 0
    assert BookkeepingBroker(config).ledger.snapshot()["spent_usd"] == "0.001013"


def test_true_process_death_after_ack_keeps_pending_and_no_regrant(tmp_path):
    config, path = setup_file(tmp_path)
    child = subprocess.Popen(argv(path), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True)
    try:
        child.stdin.write(json.dumps(reserve()) + "\n")
        child.stdin.flush()
        reply = json.loads(child.stdout.readline())
        assert reply["dispatch_allowed"]
        child.kill()  # known test child only; no controller/provider is killed
        child.communicate(timeout=5)
        assert child.returncode < 0
    finally:
        if child.poll() is None:
            child.kill()
            child.communicate(timeout=5)
    assert BookkeepingBroker(config).ledger.snapshot()["pending"] == 1
    assert not run(path, [reserve()])[0]["dispatch_allowed"]


def test_crash_inside_sqlite_transaction_rolls_back_before_any_ack(tmp_path):
    config, path = setup_file(tmp_path)
    BookkeepingBroker(config)
    script = '''
import json,os,sys
from pathlib import Path
from autoteacher_m0.accounting.broker import BookkeepingBroker
broker=BookkeepingBroker(json.loads(Path(sys.argv[1]).read_text()))
def crash(database):
 policy=next(iter(broker.routes.values()))
 broker.ledger.reserve(task_id="crash-task",prices=policy.prices,input_tokens=10,output_tokens=10)
 os._exit(42)
broker.ledger.journal_once("crash-message","fixture-digest",crash)
'''
    child = subprocess.run([sys.executable, "-B", "-c", script, str(path)], capture_output=True, timeout=10)
    assert child.returncode == 42 and not child.stdout and not child.stderr
    assert BookkeepingBroker(config).ledger.snapshot()["requests"] == 0
    assert run(path, [reserve()])[0]["dispatch_allowed"]


def test_four_independent_broker_processes_one_logical_id_get_one_grant(tmp_path):
    config, path = setup_file(tmp_path)
    BookkeepingBroker(config)
    children = [subprocess.Popen(argv(path), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, text=True) for _ in range(4)]
    try:
        for child in children:
            child.stdin.write(json.dumps(reserve()) + "\n")
            child.stdin.close()
            child.stdin = None
        replies = []
        for child in children:
            out, err = child.communicate(timeout=10)
            assert child.returncode == 0 and err == ""
            replies.append(json.loads(out))
        assert sum(reply["dispatch_allowed"] for reply in replies) == 1
        assert len({reply["reservation_id"] for reply in replies}) == 1
        assert BookkeepingBroker(config).ledger.snapshot()["requests"] == 1
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
                child.communicate(timeout=5)


@pytest.mark.parametrize("mutation", [
    lambda c: c.update(synthetic=False),
    lambda c: c["routes"][0]["usage_policy"].update(cache_write="unknown"),
    lambda c: c["routes"][0]["usage_policy"].update(reasoning="unknown"),
    lambda c: c["routes"][0].update(route_id="deepseek-official"),
    lambda c: c["routes"][0].update(model="deepseek-flash"),
    lambda c: c["routes"][0]["price"].update(input_per_million=0.1),
    lambda c: c.update(execute="FAKE_PRIVATE_PAYLOAD"),
])
def test_invalid_startup_is_fixed_error_without_db_or_payload(tmp_path, mutation):
    config, path = setup_file(tmp_path)
    mutation(config)
    path.write_text(json.dumps(config), encoding="utf-8")
    process = subprocess.run(argv(path), input="", text=True, capture_output=True, timeout=10)
    assert process.returncode == 2 and process.stderr == ""
    answer = json.loads(process.stdout)
    assert answer["code"] == "STARTUP_BLOCKED" and not answer["dispatch_allowed"]
    assert "FAKE_PRIVATE_PAYLOAD" not in process.stdout and str(path) not in process.stdout
    assert not Path(config["db_path"]).exists()


def test_policy_change_is_startup_blocked_and_old_pending_remains(tmp_path):
    config, path = setup_file(tmp_path)
    run(path, [reserve()])
    changed = deepcopy(config)
    changed["routes"][0]["price"]["input_per_million"] = "9"
    path.write_text(json.dumps(changed))
    process = subprocess.run(argv(path), input="", text=True, capture_output=True, timeout=10)
    assert process.returncode == 2 and json.loads(process.stdout)["code"] == "STARTUP_BLOCKED"
    assert BookkeepingBroker(config).ledger.snapshot()["pending"] == 1


def test_malformed_frames_and_argument_cleanup(tmp_path):
    config, path = setup_file(tmp_path)
    process = subprocess.run(argv(path), input=b'{"id":"x","id":"y"}\n' + b'x'*16385,
                             capture_output=True, timeout=10)
    assert process.returncode == 2
    replies = [json.loads(line) for line in process.stdout.splitlines()]
    assert [reply["code"] for reply in replies] == ["INVALID_MESSAGE", "FRAME_TOO_LARGE"]
    assert not any(reply["dispatch_allowed"] for reply in replies)
    process = subprocess.run(argv(path) + ["--execute", "FAKE_DO_NOT_ECHO"], input=b"",
                             capture_output=True, timeout=10)
    assert process.returncode == 2 and b"FAKE_DO_NOT_ECHO" not in process.stdout + process.stderr
    assert BookkeepingBroker(config).ledger.snapshot()["requests"] == 0
