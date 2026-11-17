"""G3-C C2-01: one validated Fake usage is forwarded as exactly one DSH
``chunk:{type:'usage'}`` before ``finish``; the Broker settles the same usage.
"""
from __future__ import annotations
import json
from pathlib import Path

import pytest

from test_c1_03_admission import (
    collect, error_code, finishes, make_harness, payload, stop_server, uds_roundtrip,
)

ROUTE = "offline-test-only-g3b"
MODEL = "fixture-bridge-v1"


def _usage_chunks(frames) -> list[dict]:
    return [frame.payload["chunk"] for frame in frames
            if frame.kind == "chunk" and frame.payload["chunk"].get("type") == "usage"]


def test_c2_01a_adapter_visible_usage_equals_fake_usage_and_broker_mapping(
        tmp_path: Path) -> None:
    harness = make_harness(tmp_path, scenario="ok_usage")
    received, server, thread = uds_roundtrip(
        harness.controller, payload(), socket_path=tmp_path / "bridge.sock",
        transport_id="tr-" + "e" * 32)
    try:
        assert received[0].kind == "ack"
        assert received[-1].kind == "finish"
        assert received[-1].payload["reason"] == {"kind": "stop"}
        usages = _usage_chunks(received)
        assert len(usages) == 1, usages
        chunk = usages[0]["usage"]
        receipt = harness.fake.last_receipt
        assert receipt is not None
        # Field-for-field equality between the adapter-visible synthetic usage
        # and the trusted Fake receipt usage (the same value Broker maps).
        assert chunk == dict(receipt.usage)
        assert chunk["inputTokens"] == 11
        assert chunk["outputTokens"] == 5
        # usage precedes finish and there is no later chunk.
        usage_index = [index for index, env in enumerate(received)
                       if env.kind == "chunk" and env.payload["chunk"].get("type") == "usage"]
        finish_index = [index for index, env in enumerate(received) if env.kind == "finish"]
        assert usage_index[0] < finish_index[0]
        assert finish_index[0] == len(received) - 1
        rows = harness.attempts_rows()
        assert rows[0]["state"] == "SETTLED"
        document = json.loads(rows[0]["receipt_json"])
        assert json.loads(rows[0]["receipt_json"])["observation"]["input"] == 11
        assert document["observation"]["complete_or_uncertain"] == "AUTHORITATIVE"
        assert document["usage"] == chunk
        status = harness.status(rows[0]["reservation_id"])
        assert status["status"] == "OK"
        assert status["input_used"] == (chunk["inputTokens"] + chunk["cacheReadTokens"]
                                        + chunk["cacheWriteTokens"])
        assert status["output_used"] == chunk["outputTokens"]
        assert status["estimated"] is False
    finally:
        stop_server(server, thread)
        harness.close()


def test_c2_01b_tool_two_turns_each_have_independent_usage(tmp_path: Path) -> None:
    harness = make_harness(tmp_path, scenario="tool")
    try:
        first = collect(harness.controller, payload())
        assert error_code(first) is None, first
        second_payload = payload(messages=[
            {"role": "user", "content": "hello g3c"},
            {"role": "assistant", "content": [
                {"type": "tool-call", "id": "call-skill-lookup-1",
                 "name": "skill_lookup", "arguments": '{"skill_id":"binary_search"}'}]},
            {"role": "tool", "content": [
                {"type": "tool-result", "toolCallId": "call-skill-lookup-1",
                 "result": {"found": True}}]},
        ])
        second = collect(harness.controller, second_payload,
                         transport_id="tr-" + "f" * 32)
        assert error_code(second) is None, second
        assert finishes(first)[-1]["kind"] == "tool-calls"
        assert finishes(second)[-1]["kind"] == "stop"
        usages_first = [frame["payload"]["chunk"]["usage"] for frame in first
                        if frame["kind"] == "chunk"
                        and frame["payload"]["chunk"]["type"] == "usage"]
        usages_second = [frame["payload"]["chunk"]["usage"] for frame in second
                         if frame["kind"] == "chunk"
                         and frame["payload"]["chunk"]["type"] == "usage"]
        assert len(usages_first) == len(usages_second) == 1
        assert usages_first[0] == usages_second[0]
        rows = harness.attempts_rows()
        assert len(rows) == 2
        assert {row["state"] for row in rows} == {"SETTLED"}
        assert len({row["call_id"] for row in rows}) == 2
        assert len({row["reservation_id"] for row in rows}) == 2
        snapshot = harness.snapshot()
        assert snapshot["requests"] == 2
        assert snapshot["claims"]["total"] == 2
        assert harness.receipt_count() == 2
    finally:
        harness.close()


@pytest.mark.parametrize("scenario,failure_code", [
    ("no_usage", "USAGE_MISSING"),
    ("partial_usage", "USAGE_PARTIAL"),
    ("usage_invalid", "USAGE_INVALID"),
])
def test_c2_01c_missing_partial_invalid_usage_never_succeeds(
        tmp_path: Path, scenario: str, failure_code: str) -> None:
    harness = make_harness(tmp_path, scenario=scenario)
    try:
        frames = collect(harness.controller, payload())
        assert not any(finish["kind"] == "stop" for finish in finishes(frames))
        assert finishes(frames)[-1]["kind"] == "error"
        assert finishes(frames)[-1]["failure"]["code"] == failure_code
        assert not any(frame["kind"] == "chunk" and frame["chunk"]["type"] == "usage"
                       for frame in frames)
        assert harness.receipt_count() == 1
        rows = harness.attempts_rows()
        assert rows[0]["state"] == "WORST_CASE_HELD"
        status = harness.status(rows[0]["reservation_id"])
        assert status["status"] == "FAILED"
        assert status["estimated"] is True
        assert status["input_used"] == status["input_bound"]
        assert status["output_used"] == status["output_bound"]
    finally:
        harness.close()


@pytest.mark.parametrize("scenario,failure_code", [
    ("multi_usage", "MULTIPLE_USAGE"),
    ("usage_after_finish", "FRAME_AFTER_FINISH"),
    ("usage_conflict", "FAKE_RECEIPT_MISMATCH"),
])
def test_c2_01d_duplicate_after_finish_or_conflicting_usage_is_rejected(
        tmp_path: Path, scenario: str, failure_code: str) -> None:
    harness = make_harness(tmp_path, scenario=scenario)
    try:
        frames = collect(harness.controller, payload())
        assert not any(finish["kind"] == "stop" for finish in finishes(frames))
        terminal = finishes(frames)[-1]
        assert terminal["kind"] == "error"
        assert terminal["failure"]["code"] == failure_code, terminal
        assert harness.receipt_count() == 1
        rows = harness.attempts_rows()
        assert rows[0]["state"] == "WORST_CASE_HELD"
        status = harness.status(rows[0]["reservation_id"])
        assert status["status"] == "FAILED"
    finally:
        harness.close()


def test_c2_01e_usage_chunk_is_not_a_success_indicator(tmp_path: Path) -> None:
    # A complete usage frame alone must not be reported as a successful finish:
    # this mode ends with malformed error finish, so the SDK terminal state is
    # error even though the receipt usage is complete.
    harness = make_harness(tmp_path, scenario="error")
    try:
        frames = collect(harness.controller, payload())
        assert finishes(frames)[-1]["kind"] == "error"
        assert finishes(frames)[-1]["failure"]["code"] == "FAKE_PROVIDER_ERROR"
        rows = harness.attempts_rows()
        assert rows[0]["state"] == "WORST_CASE_HELD"
    finally:
        harness.close()
