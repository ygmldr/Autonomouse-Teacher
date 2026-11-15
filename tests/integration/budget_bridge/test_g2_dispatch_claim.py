"""G2-BROKER integration: real SQLite + real stdio broker subprocess.

Covers INT-01/04/05/06/07/08/12/13/14/18 for the ADR-002 persistent dispatch
claim. No network, no credentials, no real model/HTTP. The local claim is a
one-shot local send authorization, NOT a remote exactly-once guarantee.
"""
import json
import signal
import subprocess
import sys

import pytest

from autoteacher_m0.accounting import ProviderObservation, deliver_observation, derive_call_id
from autoteacher_m0.accounting.broker import BookkeepingBroker
from autoteacher_m0.accounting.observation import issue_trusted_egress_provenance

DIGEST = "a" * 64


def setup_file(tmp_path, *, max_messages=16, max_requests=50):
    config = {"v": 1, "synthetic": True, "db_path": str(tmp_path / "ledger.sqlite3"),
              "scope_id": "fixed-offline-scope", "max_messages": max_messages,
              "limits": {"soft_usd": "3", "hard_usd": "10", "per_call_usd": "0.20",
                         "max_requests": max_requests, "max_input_tokens": 2500000,
                         "max_output_tokens": 600000, "max_steps": 8, "max_retries": 1},
              "routes": [{"route_id": "offline-test-only", "model": "fixture-v1",
                          "price": {"version": "fixture-v1", "input_per_million": "1",
                                    "output_per_million": "2", "cached_input_per_million": "0.5",
                                    "source": "synthetic fixture", "captured_at": "2026-11-13"},
                          "known_extra_fee_usd": "0.001",
                          "usage_policy": {"cache_write": "input_rate", "reasoning": "included_in_output"}}]}
    path = tmp_path / "startup.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config), encoding="utf-8")
    return config, path


def call_id(seed, digest=DIGEST):
    return derive_call_id(seed, 0, 0, digest)


def reserve(identity="reserve-1", call_id_value=None):
    message = {"v": 1, "id": identity, "op": "reserve", "task_id": "session-001",
               "route_id": "offline-test-only", "model": "fixture-v1", "purpose": "conversation",
               "input_tokens": 100, "output_tokens": 10, "retry": False}
    if call_id_value is not None:
        message["call_id"] = call_id_value
    return message


def claim(identity, call_id_value, reservation_id, digest=DIGEST):
    return {"v": 1, "id": identity, "op": "claim", "call_id": call_id_value,
            "reservation_id": reservation_id, "request_digest": digest}


def settle(identity, reservation_id):
    return {"v": 1, "id": identity, "op": "settle", "reservation_id": reservation_id,
            "usage": {"inputTokens": 7, "cacheReadTokens": 0, "cacheWriteTokens": 0,
                      "outputTokens": 3, "reasoningTokens": 0, "totalTokens": 10}}


def snapshot(identity="snapshot-1"):
    return {"v": 1, "id": identity, "op": "snapshot"}


def argv(path):
    return [sys.executable, "-B", "-m", "autoteacher_m0.accounting.broker", "--config", str(path)]


def run(path, messages):
    data = "".join(json.dumps(message) + "\n" for message in messages)
    process = subprocess.run(argv(path), input=data, text=True, capture_output=True, timeout=15)
    assert process.returncode == 0, (process.returncode, process.stdout, process.stderr)
    assert process.stderr == ""
    return [json.loads(line) for line in process.stdout.splitlines()]


def start_broker(path):
    return subprocess.Popen(argv(path), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True)


def send(process, message):
    process.stdin.write(json.dumps(message) + "\n")
    process.stdin.flush()
    return json.loads(process.stdout.readline())


def stop(process, *, kill=False):
    try:
        if kill:
            process.send_signal(signal.SIGKILL)
        else:
            process.stdin.close()
        process.wait(timeout=10)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)


def reserve_call(path, seed, identity="reserve-1", digest=DIGEST):
    call = call_id(seed, digest)
    grant = run(path, [reserve(identity=identity, call_id_value=call)])[0]
    assert grant["ok"] and grant["dispatch_allowed"], grant
    return call, grant["reservation_id"]


def observation(**changes):
    value = {"requested_route": "offline-test-only", "observed_route": "offline-test-only",
             "model_reported": "fixture-v1", "provider_request_id": "provider-request-1",
             "usage_raw_hash": "a" * 64, "input": 7, "cache_read": 2, "cache_write": 3,
             "output": 3, "reasoning": 1, "cost_estimate": None,
             "cost_source": "synthetic_fixture_cost", "error_kind": "none",
             "complete_or_uncertain": "AUTHORITATIVE"}
    value.update(changes)
    return ProviderObservation.from_mapping(value)


def test_int01_claim_once_settle_and_claim_completion(tmp_path):
    config, path = setup_file(tmp_path)
    call, reservation = reserve_call(path, "run-int01")
    reply = run(path, [claim("claim-1", call, reservation)])[0]
    assert reply["ok"] and reply["code"] == "CLAIMED" and reply["dispatch_allowed"]
    assert reply["claim"] == {"call_id": call, "reservation_id": reservation,
                              "request_digest": DIGEST, "status": "CLAIMED"}
    state = run(path, [snapshot()])[0]["snapshot"]
    assert state["claims"] == {"total": 1, "pending": 1, "completed": 0}
    assert state["pending"] == 1
    settled = run(path, [settle("settle-1", reservation)])[0]
    assert settled["ok"] and settled["code"] == "SETTLED"
    assert settled["settlement"]["cost_usd"] == "0.001013"
    state = run(path, [snapshot("snapshot-2")])[0]["snapshot"]
    assert state["claims"] == {"total": 1, "pending": 0, "completed": 1}
    assert state["pending"] == 0 and state["requests"] == 1


def test_int04_duplicate_claim_never_grants_second_dispatch(tmp_path):
    config, path = setup_file(tmp_path)
    call, reservation = reserve_call(path, "run-int04")
    first = run(path, [claim("claim-1", call, reservation)])[0]
    assert first["dispatch_allowed"]
    replay = run(path, [claim("claim-2", call, reservation)])[0]
    assert not replay["dispatch_allowed"] and replay["duplicate"] is True
    assert replay["ok"] is False and replay["code"] == "ALREADY_CLAIMED"
    conflict = run(path, [claim("claim-3", call, reservation, digest="b" * 64)])[0]
    assert not conflict["dispatch_allowed"] and conflict["code"] == "CALL_ID_CONFLICT"
    state = run(path, [snapshot()])[0]["snapshot"]
    assert state["claims"]["total"] == 1 and state["pending"] == 1
    # settle/fail stay idempotent and do not consume a second claim
    settled = run(path, [settle("settle-1", reservation), settle("settle-2", reservation)])[0]
    assert settled["code"] == "SETTLED"
    assert run(path, [snapshot()])[0]["snapshot"]["pending"] == 0


def test_int05_two_broker_processes_concurrent_claim_single_grant(tmp_path):
    config, path = setup_file(tmp_path)
    call, reservation = reserve_call(path, "run-int05")
    first = start_broker(path)
    second = start_broker(path)
    try:
        first.stdin.write(json.dumps(claim("race-a", call, reservation)) + "\n")
        first.stdin.flush()
        second.stdin.write(json.dumps(claim("race-b", call, reservation)) + "\n")
        second.stdin.flush()
        replies = [json.loads(first.stdout.readline()), json.loads(second.stdout.readline())]
    finally:
        stop(first)
        stop(second)
    grants = [reply for reply in replies if reply["dispatch_allowed"]]
    assert len(grants) == 1, replies
    denied = [reply for reply in replies if not reply["dispatch_allowed"]]
    assert len(denied) == 1
    assert denied[0]["code"] in {"ALREADY_CLAIMED", "CLAIM_RACE_LOST"}
    assert run(path, [snapshot()])[0]["snapshot"]["claims"]["total"] == 1


def test_int06_sigkill_after_claim_restart_replay_no_regrant(tmp_path):
    config, path = setup_file(tmp_path)
    call = call_id("run-int06")
    child = start_broker(path)
    try:
        granted = send(child, reserve(call_id_value=call))
        assert granted["dispatch_allowed"]
        reservation = granted["reservation_id"]
        claimed = send(child, claim("claim-1", call, reservation))
        assert claimed["dispatch_allowed"]
        stop(child, kill=True)
    finally:
        if child.poll() is None:
            stop(child, kill=True)
    state = run(path, [snapshot()])[0]["snapshot"]
    assert state["claims"] == {"total": 1, "pending": 1, "completed": 0}
    assert state["pending"] == 1
    replay = run(path, [claim("claim-2", call, reservation)])[0]
    assert not replay["dispatch_allowed"] and replay["code"] == "ALREADY_CLAIMED"
    settled = run(path, [settle("settle-after-restart", reservation)])[0]
    assert settled["code"] == "SETTLED"
    assert BookkeepingBroker(config).ledger.snapshot()["claims"]["pending"] == 0


def test_int07_int08_digest_and_reservation_retarget_denied(tmp_path):
    config, path = setup_file(tmp_path)
    call_a, reservation_a = reserve_call(path, "run-int08-a", identity="reserve-a")
    call_b, reservation_b = reserve_call(path, "run-int08-b", identity="reserve-b")
    assert run(path, [claim("claim-a", call_a, reservation_a)])[0]["dispatch_allowed"]
    conflict = run(path, [claim("claim-a2", call_a, reservation_a, digest="c" * 64)])[0]
    assert conflict["code"] == "CALL_ID_CONFLICT"
    retarget = run(path, [claim("claim-a3", call_a, reservation_b)])[0]
    assert retarget["code"] == "CALL_LINK_MISMATCH"
    unbound = run(path, [claim("claim-c", call_id("run-int08-c"), reservation_a)])[0]
    assert unbound["code"] == "UNBOUND_CALL"
    assert not conflict["dispatch_allowed"] and not retarget["dispatch_allowed"]
    state = run(path, [snapshot()])[0]["snapshot"]
    assert state["claims"] == {"total": 1, "pending": 1, "completed": 0}
    assert state["pending"] == 2


def test_int12_scope_blocked_and_broker_down_do_not_grant(tmp_path):
    config, path = setup_file(tmp_path, max_requests=1)
    call, reservation = reserve_call(path, "run-int12")
    # Second reserve exceeds max_requests and durably blocks the scope.
    denied = run(path, [reserve(identity="reserve-2", call_id_value=call_id("run-int12-b"))])[0]
    assert not denied["dispatch_allowed"] and denied["code"] == "BUDGET_EXCEEDED"
    blocked = run(path, [claim("claim-1", call, reservation)])[0]
    assert not blocked["dispatch_allowed"] and blocked["code"] == "SCOPE_BLOCKED"
    assert run(path, [snapshot()])[0]["snapshot"]["claims"]["total"] == 0
    # A dead broker process cannot grant a claim; nothing is recorded. Use a
    # fresh unblocked scope for this sub-case.
    _config2, path2 = setup_file(tmp_path / "down")
    child = start_broker(path2)
    try:
        granted = send(child, reserve(identity="reserve-3", call_id_value=call_id("run-int12-c")))
        assert granted["dispatch_allowed"]
        stop(child, kill=True)
        try:
            send(child, claim("claim-down", call_id("run-int12-c"), granted["reservation_id"]))
            raise AssertionError("write to dead broker should fail")
        except (BrokenPipeError, ValueError, OSError):
            pass
    finally:
        if child.poll() is None:
            stop(child, kill=True)
    assert run(path2, [snapshot()])[0]["snapshot"]["claims"]["total"] == 0


def test_int13_int14_observation_idempotent_and_conflict_after_claim(tmp_path):
    config, path = setup_file(tmp_path)
    call, reservation = reserve_call(path, "run-int13")
    assert run(path, [claim("claim-1", call, reservation)])[0]["dispatch_allowed"]
    broker = BookkeepingBroker(config)
    trust = issue_trusted_egress_provenance(call_id=call, request_digest=DIGEST,
                                             observed_route="offline-test-only", model_reported="fixture-v1")
    first = deliver_observation(broker.ledger, call, observation(), reasoning_policy="inclusive",
                                cache_discount_approved=True, provenance=trust)
    assert first["ok"] and first["code"] == "SETTLED"
    assert broker.ledger.snapshot()["claims"]["completed"] == 1
    replay = deliver_observation(broker.ledger, call, observation(), reasoning_policy="inclusive",
                                 cache_discount_approved=True, provenance=trust)
    assert replay["duplicate"] is True and replay["code"] == "SETTLED"
    with pytest.raises(ValueError, match="conflict"):
        deliver_observation(broker.ledger, call, observation(output=4), reasoning_policy="inclusive",
                            cache_discount_approved=True, provenance=trust)
    assert broker.ledger.snapshot()["requests"] == 1 and broker.ledger.snapshot()["pending"] == 0


def test_int18_restart_balance_and_claims_are_durable(tmp_path):
    config, path = setup_file(tmp_path)
    call, reservation = reserve_call(path, "run-int18")
    assert run(path, [claim("claim-1", call, reservation)])[0]["dispatch_allowed"]
    assert run(path, [settle("settle-1", reservation)])[0]["settlement"]["cost_usd"] == "0.001013"
    before = run(path, [snapshot()])[0]["snapshot"]
    after = run(path, [snapshot("snapshot-after-restart")])[0]["snapshot"]
    for key in ("requests", "pending", "spent_usd", "reserved_usd", "committed_usd",
                "input_tokens", "output_tokens"):
        assert after[key] == before[key], (key, before, after)
    assert before["spent_usd"] == "0.001013" and before["committed_usd"] == "0.001013"
    assert after["claims"] == {"total": 1, "pending": 0, "completed": 1}
    replay = run(path, [claim("claim-2", call, reservation)])[0]
    assert not replay["dispatch_allowed"]
    assert run(path, [snapshot("snapshot-final")])[0]["snapshot"]["spent_usd"] == "0.001013"


def test_legacy_egress_ids_are_rejected_as_settlement_ids(tmp_path):
    config, path = setup_file(tmp_path)
    legacy = run(path, [reserve(identity="reserve-legacy", call_id_value="eg-1234")])[0]
    assert not legacy["ok"] and not legacy["dispatch_allowed"]
    assert legacy["code"] == "INVALID_CALL_ID"
    claim_legacy = {"v": 1, "id": "claim-legacy", "op": "claim", "call_id": "eg-1234",
                    "reservation_id": "res-1", "request_digest": DIGEST}
    rejected = run(path, [claim_legacy])[0]
    assert rejected["code"] == "INVALID_CALL_ID" and not rejected["dispatch_allowed"]
