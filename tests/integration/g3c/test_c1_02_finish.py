"""G3-C C1-02: Finish(error) is always schema-correct; Fake terminal states are
independently asserted against the Broker ledger.
"""
from __future__ import annotations
import json
from pathlib import Path

import pytest

from autoteacher_m0.accounting.observation import ProviderObservation, observation_digest
from autoteacher_m0.bridge.protocol import Envelope, encode_envelope
from test_c1_03_admission import (
    collect, error_code, finishes, make_harness, payload,
)

FAILURE_SCENARIOS = [
    ("error", "FAKE_PROVIDER_ERROR"),
    ("no_usage", "USAGE_MISSING"),
    ("partial_usage", "USAGE_PARTIAL"),
    ("usage_invalid", "USAGE_INVALID"),
    ("eof", "FAKE_EOF"),
]


def _assert_schema_valid(frames: list[dict]) -> None:
    seq = 1
    for frame in frames:
        kind = frame["kind"]
        if kind == "chunk":
            payload_dict = {"chunk": frame["chunk"]}
        elif kind == "finish":
            payload_dict = {"reason": frame["reason"]}
        elif kind == "error":
            payload_dict = frame["payload"]
        else:  # pragma: no cover - controller never emits other kinds
            pytest.fail(f"unexpected frame kind {kind}")
        encode_envelope(Envelope(1, kind, "tr-" + "a" * 32, seq, payload_dict, None))
        seq += 1


@pytest.mark.parametrize("scenario,failure_code", FAILURE_SCENARIOS)
def test_c1_02_failure_terminal_is_schema_valid_and_broker_is_held(
        tmp_path: Path, scenario: str, failure_code: str) -> None:
    harness = make_harness(tmp_path, scenario=scenario)
    try:
        frames = collect(harness.controller, payload())
        _assert_schema_valid(frames)
        terminal = finishes(frames)
        assert terminal, frames
        assert terminal[-1]["kind"] == "error", frames
        assert set(terminal[-1]["failure"]) == {"code", "message"}
        assert terminal[-1]["failure"]["code"] == failure_code
        assert terminal[-1]["failure"]["message"]
        assert not any(finish["kind"] == "stop" for finish in terminal)
        assert harness.receipt_count() == 1
        rows = harness.attempts_rows()
        assert len(rows) == 1
        assert rows[0]["state"] == "WORST_CASE_HELD"
        status = harness.status(rows[0]["reservation_id"])
        assert status["ok"] and status["status"] == "FAILED"
        assert status["input_used"] == status["input_bound"]
        assert status["output_used"] == status["output_bound"]
    finally:
        harness.close()


def test_c1_02_ok_usage_finish_is_success_and_receipt_is_authoritative(
        tmp_path: Path) -> None:
    harness = make_harness(tmp_path)
    try:
        frames = collect(harness.controller, payload())
        _assert_schema_valid(frames)
        assert not any(frame["kind"] == "error" for frame in frames), frames
        finish = finishes(frames)
        assert len(finish) == 1 and finish[0] == {"kind": "stop"}
        usage_frames = [frame["chunk"] for frame in frames
                        if frame["kind"] == "chunk" and frame["chunk"]["type"] == "usage"]
        assert len(usage_frames) == 1
        receipt = harness.fake.last_receipt
        assert receipt is not None
        assert usage_frames[0]["usage"] == dict(receipt.usage)
        rows = harness.attempts_rows()
        assert len(rows) == 1 and rows[0]["state"] == "SETTLED"
        document = json.loads(rows[0]["receipt_json"])
        assert document["completeness"] == "AUTHORITATIVE"
        assert document["receipt"]["nonce"] == receipt.nonce
        assert document["observation_digest"] == observation_digest(
            ProviderObservation.from_mapping(document["observation"]))
        status = harness.status(rows[0]["reservation_id"])
        assert status["ok"] and status["status"] == "OK"
        assert status["input_used"] == 13 and status["output_used"] == 5  # 11 + cacheRead 2
        assert status["estimated"] is False
    finally:
        harness.close()


def test_c1_02_error_envelope_codes_are_frozen(tmp_path: Path) -> None:
    harness = make_harness(tmp_path)
    try:
        cases = [
            (payload(provider="offline-test-only-other"), "ROUTE_MISMATCH"),
            (payload(call_id="call-" + "a" * 48), "ADMISSION_SELF_AUTH_DENIED"),
            (payload(maxTokens=0), "BAD_TYPE"),
            (payload(stream=False), "BAD_TYPE"),
        ]
        for bad, expected in cases:
            frames = collect(harness.controller, bad)
            assert error_code(frames) == expected, frames
            _assert_schema_valid(frames)
        assert harness.receipt_count() == 0
    finally:
        harness.close()


def test_c1_02_malformed_fake_finish_is_normalized_not_forwarded(tmp_path: Path) -> None:
    harness = make_harness(tmp_path, scenario="error")
    try:
        frames = collect(harness.controller, payload())
        _assert_schema_valid(frames)
        finish = finishes(frames)
        assert finish[-1]["kind"] == "error"
        # The Fake emits {"kind":"error"} without failure; the Controller must
        # never forward that malformed reason verbatim.
        assert "failure" in finish[-1]
        assert finish[-1]["failure"]["code"] == "FAKE_PROVIDER_ERROR"
    finally:
        harness.close()
