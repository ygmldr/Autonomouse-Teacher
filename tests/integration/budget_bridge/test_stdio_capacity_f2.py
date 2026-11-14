"""F2 stdio-level regression: completion capacity, snapshot, process restart.

Every child here is launched ONLY by isolated-container pytest. No network, no
credentials and no real model are involved.
"""
import json
import signal
import subprocess
import sys

from autoteacher_m0.accounting.broker import BookkeepingBroker


def setup_file(tmp_path, *, max_messages=2):
    config = {"v": 1, "synthetic": True, "db_path": str(tmp_path / "ledger.sqlite3"),
              "scope_id": "fixed-offline-scope", "max_messages": max_messages,
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


def settle(token, identity="settle-001"):
    return {"v": 1, "id": identity, "op": "settle", "reservation_id": token,
            "usage": {"inputTokens": 7, "cacheReadTokens": 0, "cacheWriteTokens": 0,
                      "outputTokens": 3, "reasoningTokens": 0, "totalTokens": 10}}


def argv(path):
    return [sys.executable, "-B", "-m", "autoteacher_m0.accounting.broker", "--config", str(path)]


def run(path, messages):
    data = "".join(json.dumps(message) + "\n" for message in messages)
    process = subprocess.run(argv(path), input=data, text=True, capture_output=True, timeout=10)
    assert process.returncode == 0, (process.returncode, process.stdout, process.stderr)
    assert process.stderr == ""
    return [json.loads(line) for line in process.stdout.splitlines()]


def test_stdio_completion_capacity_snapshot_after_full_journal(tmp_path):
    _, path = setup_file(tmp_path, max_messages=2)
    first = run(path, [reserve()])[0]
    assert first["ok"] and first["dispatch_allowed"]
    denied = run(path, [reserve("stream-002")])[0]
    assert denied["code"] == "MESSAGE_LIMIT"
    # Observation stays available with a full journal, and it adds no journal row.
    state = run(path, [{"v": 1, "id": "snap-1", "op": "snapshot"}])[0]
    assert state["ok"] and state["snapshot"]["pending"] == 1
    # The reserved completion slot can be consumed despite the full journal.
    settled = run(path, [settle(first["reservation_id"])])[0]
    assert settled["ok"] and settled["code"] == "SETTLED"
    final = run(path, [{"v": 1, "id": "snap-2", "op": "snapshot"}])[0]
    assert final["snapshot"]["pending"] == 0 and final["snapshot"]["requests"] == 1
    assert BookkeepingBroker(json.loads(path.read_text(encoding="utf-8"))).ledger.snapshot()["requests"] == 1


def test_stdio_pending_survives_sigkill_and_completes_once(tmp_path):
    config, path = setup_file(tmp_path, max_messages=2)
    process = subprocess.Popen(argv(path), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True)
    try:
        process.stdin.write(json.dumps(reserve()) + "\n")
        process.stdin.flush()
        granted = json.loads(process.stdout.readline())
        assert granted["dispatch_allowed"]
        process.send_signal(signal.SIGKILL)
        process.wait(timeout=10)
    finally:
        if process.poll() is None:
            process.kill()
    # Nothing was refunded by the crash; a new process sees the same PENDING row.
    state = run(path, [{"v": 1, "id": "snap-after-kill", "op": "snapshot"}])[0]
    assert state["snapshot"]["pending"] == 1
    replay = run(path, [reserve()])[0]
    assert replay["duplicate"] and not replay["dispatch_allowed"]
    settled = run(path, [settle(granted["reservation_id"]), settle(granted["reservation_id"], "settle-002")])
    assert settled[0]["code"] == "SETTLED"
    assert settled[1]["code"] == "ALREADY_SETTLED" and not settled[1]["dispatch_allowed"]
    final = run(path, [{"v": 1, "id": "snap-final", "op": "snapshot"}])[0]
    assert final["snapshot"]["pending"] == 0 and final["snapshot"]["requests"] == 1
