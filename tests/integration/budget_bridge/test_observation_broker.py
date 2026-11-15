"""PR4b stdio-level observation/call-identity integration (isolated container only).

Real stdio broker process + real SQLite ledger. No network, no credentials, no
real model/HTTP. Real provider wire/usage mapping remains UNVERIFIED.
"""
import json
import signal
import subprocess
import sys

from autoteacher_m0.accounting import ProviderObservation, deliver_observation, derive_call_id
from autoteacher_m0.accounting.observation import issue_trusted_egress_provenance
from autoteacher_m0.accounting.broker import BookkeepingBroker


def setup_file(tmp_path):
    config = {"v": 1, "synthetic": True, "db_path": str(tmp_path / "ledger.sqlite3"),
              "scope_id": "fixed-offline-scope", "max_messages": 8,
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


def call_id_for(seed: str) -> str:
    return derive_call_id(seed, 0, 0, "a" * 64)


def reserve(identity="stream-001", call_id=None):
    value = {"v": 1, "id": identity, "op": "reserve", "task_id": "session-001",
             "route_id": "offline-test-only", "model": "fixture-v1", "purpose": "conversation",
             "input_tokens": 100, "output_tokens": 10, "retry": False}
    if call_id is not None:
        value["call_id"] = call_id
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


def argv(path):
    return [sys.executable, "-B", "-m", "autoteacher_m0.accounting.broker", "--config", str(path)]


def run(path, messages):
    data = "".join(json.dumps(message) + "\n" for message in messages)
    process = subprocess.run(argv(path), input=data, text=True, capture_output=True, timeout=10)
    assert process.returncode == 0, (process.returncode, process.stdout, process.stderr)
    assert process.stderr == ""
    return [json.loads(line) for line in process.stdout.splitlines()]


def test_stdio_reserve_call_id_then_deliver_authoritative_observation(tmp_path):
    config, path = setup_file(tmp_path)
    call_id = call_id_for("run-a")
    first = run(path, [reserve(call_id=call_id), reserve(call_id=call_id)])[0]
    assert first["ok"] and first["dispatch_allowed"] and first["call_id"] == call_id
    replay = run(path, [reserve(call_id=call_id)])[0]
    assert replay["duplicate"] and not replay["dispatch_allowed"]
    broker = BookkeepingBroker(config)
    assert broker.ledger.call_reservation(call_id) == first["reservation_id"]
    trust = issue_trusted_egress_provenance(call_id=call_id, request_digest="a" * 64,
                                             observed_route="offline-test-only", model_reported="fixture-v1")
    response = deliver_observation(broker.ledger, call_id, observation(),
                                   reasoning_policy="inclusive", cache_discount_approved=True, provenance=trust)
    assert response["ok"] and response["code"] == "SETTLED"
    assert response["settlement"]["cost_usd"] == "0.001017"
    state = broker.ledger.snapshot()
    assert state["pending"] == 0 and state["requests"] == 1
    replay_delivery = deliver_observation(broker.ledger, call_id, observation(),
                                          reasoning_policy="inclusive", cache_discount_approved=True,
                                          provenance=trust)
    assert replay_delivery["duplicate"] is True and replay_delivery["code"] == "SETTLED"


def test_stdio_partial_usage_holds_full_bound_and_pending_survives_sigkill(tmp_path):
    config, path = setup_file(tmp_path)
    call_id = call_id_for("run-b")
    process = subprocess.Popen(argv(path), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True)
    try:
        process.stdin.write(json.dumps(reserve(call_id=call_id)) + "\n")
        process.stdin.flush()
        granted = json.loads(process.stdout.readline())
        assert granted["dispatch_allowed"]
        process.send_signal(signal.SIGKILL)
        process.wait(timeout=10)
    finally:
        if process.poll() is None:
            process.kill()
    broker = BookkeepingBroker(config)
    partial = observation(input=7, cache_read=None, cache_write=None, output=None,
                          reasoning=None, complete_or_uncertain="PARTIAL")
    response = deliver_observation(broker.ledger, call_id, partial,
                                   reasoning_policy="inclusive", cache_discount_approved=False)
    assert response["ok"] and response["code"] == "WORST_CASE_HELD"
    assert response["settlement"]["cost_usd"] == "0.00112"
    state = broker.ledger.snapshot()
    assert state["pending"] == 0 and state["requests"] == 1


def test_stdio_unknown_observation_keeps_reservation_pending(tmp_path):
    config, path = setup_file(tmp_path)
    call_id = call_id_for("run-c")
    granted = run(path, [reserve(call_id=call_id)])[0]
    assert granted["dispatch_allowed"]
    broker = BookkeepingBroker(config)
    unknown = observation(input=None, cache_read=None, cache_write=None, output=None, reasoning=None,
                          usage_raw_hash=None, cost_estimate=None, cost_source="unknown",
                          error_kind="transport", complete_or_uncertain="UNKNOWN")
    response = deliver_observation(broker.ledger, call_id, unknown,
                                   reasoning_policy="inclusive", cache_discount_approved=False)
    assert not response["ok"] and response["code"] == "SETTLEMENT_UNCERTAIN"
    assert broker.ledger.snapshot()["pending"] == 1
    # A restart still sees the unresolved reservation (no refund/zero fill).
    state = run(path, [{"v": 1, "id": "snap-after-uncertain", "op": "snapshot"}])[0]
    assert state["snapshot"]["pending"] == 1
