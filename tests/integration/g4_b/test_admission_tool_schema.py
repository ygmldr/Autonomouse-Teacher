"""G4-B-04/B06: unapproved tool schemas and extra requests are fail-closed.

These tests drive the **real** trusted components in-process (``load_admission``,
the Broker subprocess, ``AttemptJournal``, ``FakeBackend``, ``TrustedController``)
with a synthetic admission whose approved tool set is computed here.  They
answer the two P0/P1 questions with a ledger:

* B04 — an unapproved tool, an extra tool, or a modified schema is rejected with
  ``ADMISSION_TOOL_SCHEMA_MISMATCH`` *before* Reserve/Claim, with Fake counter 0
  and zero attempts;
* B06 — an additional provider request either takes its own
  Reserve/Claim/Attempt/Receipt or is denied with zero sends.

They are host-level, so they do not replace the raw-UDS evidence produced by
``scripts/g4/run_g4_b.py``; they do run on every CI invocation.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
FAKE = REPO_ROOT / "spikes" / "g3b-trusted-bridge" / "fake" / "fake_provider.py"
ROUTE = "offline-test-only-g3b"
MODEL = "fixture-bridge-v1"
SCOPE = "fixed-offline-scope"

TOOLS = (
    {"name": "skill_lookup", "description": "lookup fixed skill metadata",
     "parameters": {"type": "object",
                    "properties": {"skill_id": {"type": "string"}},
                    "required": ["skill_id"]}},
    {"name": "skill_meta", "description": "fixed metadata only",
     "parameters": {"type": "object", "properties": {"id": {"type": "string"}}}},
)


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)


def _tool_digest(tool: object) -> str:
    return hashlib.sha256(_canonical(tool).encode("utf-8")).hexdigest()


def _write_admission(tmp_path: Path, *, max_calls: int = 8) -> Path:
    document = {
        "schema": "m0.g3b.admission.v1",
        "admission_id": "a" * 32,
        "scope_id": SCOPE,
        "run_id": "run-g4b-contract",
        "synthetic": True,
        "route": {"route_id": ROUTE, "provider": ROUTE, "model": MODEL},
        "tool_schemas": [{"name": tool["name"], "sha256": _tool_digest(tool)}
                         for tool in TOOLS],
        "limits": {"max_calls": max_calls, "max_attempts": 1,
                   "max_input_tokens": 100000, "max_output_tokens": 1024,
                   "deadline_ms": 30000},
        "fake_scenario": "ok_usage",
        "expiry_utc": "2099-01-01T00:00:00Z",
        "launcher": {"uid": 65534, "container": True,
                     "admission_nonce": "b" * 32},
    }
    path = tmp_path / "admission.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _write_broker(tmp_path: Path) -> Path:
    document = {
        "v": 1, "synthetic": True, "db_path": str(tmp_path / "broker.sqlite3"),
        "scope_id": SCOPE, "max_messages": 64,
        "limits": {"soft_usd": "3", "hard_usd": "10", "per_call_usd": "0.2",
                   "max_requests": 50, "max_input_tokens": 2500000,
                   "max_output_tokens": 600000, "max_steps": 8, "max_retries": 0},
        "routes": [{"route_id": ROUTE, "model": MODEL,
                    "price": {"version": "fixture-v1",
                              "input_per_million": "1",
                              "output_per_million": "2",
                              "cached_input_per_million": "0.5",
                              "source": "synthetic fixture",
                              "captured_at": "2026-11-16"},
                    "known_extra_fee_usd": "0.001",
                    "usage_policy": {"cache_write": "input_rate",
                                     "reasoning": "included_in_output"}}],
    }
    path = tmp_path / "broker.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _harness(tmp_path: Path, *, max_calls: int = 8):
    sys.path.insert(0, str(REPO_ROOT / "src"))
    from autoteacher_m0.bridge.admission import load_admission
    from autoteacher_m0.bridge.attempts import AttemptJournal
    from autoteacher_m0.bridge.broker_client import BrokerClient
    from autoteacher_m0.bridge.controller import TrustedController
    from autoteacher_m0.bridge.fake_backend import FakeBackend

    receipts = tmp_path / "receipts"
    receipts.mkdir(exist_ok=True)
    admission = load_admission(_write_admission(tmp_path, max_calls=max_calls),
                               expected_uid=65534)
    broker = BrokerClient(config_path=str(_write_broker(tmp_path)),
                          python=sys.executable)
    broker.start()
    fake = FakeBackend(script=str(FAKE), receipt_dir=str(receipts),
                       python=sys.executable, mode="ok_usage")
    attempts = AttemptJournal(tmp_path / "attempts.sqlite3")
    controller = TrustedController(admission, broker=broker, fake=fake,
                                   attempts=attempts, expected_uid=65534)
    return controller, broker, fake, attempts


def _payload(tools: object, *, session: str = "g4b-test",
             messages: list | None = None, purpose: object = "conversation"):
    return {"sessionId": session, "provider": ROUTE, "model": MODEL,
            "messages": messages if messages is not None else
            [{"role": "user", "content": [{"type": "text", "text": "G4B"}]}],
            "tools": tools, "system": None, "maxTokens": 256, "stream": True,
            "purpose": purpose}


def _run(controller, payload: dict) -> tuple[list[dict], dict]:
    from autoteacher_m0.bridge.protocol import Envelope
    frames = []
    envelope = Envelope(v=1, kind="request", transport_id="tr-" + "c" * 32,
                        seq=1, payload=payload, hash=None)
    for response in controller.handle_envelope(envelope):
        frames.append({"kind": response.kind, "payload": response.payload})
    ledger = {
        "fake": controller.fake.received_count(),
        "attempts": controller.attempts.conn.execute(
            "SELECT COUNT(*) FROM g3b_attempts").fetchone()[0],
        "reservations": controller.broker.snapshot()["snapshot"]["requests"],
        "claims": controller.broker.snapshot()["snapshot"]["claims"]["total"],
    }
    return frames, ledger


def _close(broker, fake, attempts) -> None:
    broker.close()
    fake.close()
    attempts.close()


def test_unapproved_tool_is_rejected_before_reserve_claim(tmp_path: Path) -> None:
    controller, broker, fake, attempts = _harness(tmp_path)
    try:
        unapproved = {"name": "bash", "description": "run commands",
                      "parameters": {"type": "object",
                                     "properties": {"command": {"type": "string"}}}}
        frames, ledger = _run(controller, _payload([unapproved]))
        assert frames[-1]["kind"] == "error"
        assert frames[-1]["payload"]["code"] == "ADMISSION_TOOL_SCHEMA_MISMATCH"
        assert ledger == {"fake": 0, "attempts": 0, "reservations": 0,
                          "claims": 0}
    finally:
        _close(broker, fake, attempts)


def test_extra_and_modified_tools_are_rejected(tmp_path: Path) -> None:
    controller, broker, fake, attempts = _harness(tmp_path)
    try:
        approved = TOOLS[0]
        extra = {"name": "fs_read", "description": "read",
                 "parameters": {"type": "object", "properties": {}}}
        cases = [
            [approved, extra],
            [{**approved, "description": approved["description"] + " "}],
            [{**approved, "name": "skill_lookup_shadow"}],
        ]
        for tools in cases:
            frames, ledger = _run(controller, _payload(tools))
            assert frames[-1]["kind"] == "error"
            assert frames[-1]["payload"]["code"] == "ADMISSION_TOOL_SCHEMA_MISMATCH"
            assert ledger["fake"] == 0 and ledger["reservations"] == 0
            assert ledger["attempts"] == 0 and ledger["claims"] == 0
    finally:
        _close(broker, fake, attempts)


def test_file_and_image_blocks_are_rejected(tmp_path: Path) -> None:
    controller, broker, fake, attempts = _harness(tmp_path)
    try:
        for block in ({"type": "file", "file": {"path": "/work/session/x"}},
                      {"type": "image", "image": {"data": "AAAA"}}):
            frames, ledger = _run(controller, _payload(
                [TOOLS[0]],
                messages=[{"role": "user", "content": [
                    {"type": "text", "text": "x"}, block]}]))
            assert frames[-1]["payload"]["code"] == "REQUEST_INVALID"
            assert ledger["fake"] == 0 and ledger["reservations"] == 0
    finally:
        _close(broker, fake, attempts)


def test_auxiliary_purpose_is_rejected_by_protocol(tmp_path: Path) -> None:
    controller, broker, fake, attempts = _harness(tmp_path)
    try:
        frames, ledger = _run(controller, _payload([TOOLS[0]], purpose="title"))
        assert frames[-1]["kind"] == "error"
        assert frames[-1]["payload"]["code"] == "BAD_TYPE"
        assert ledger["fake"] == 0 and ledger["reservations"] == 0
    finally:
        _close(broker, fake, attempts)


def test_approved_tool_cycle_is_accounted_once(tmp_path: Path) -> None:
    controller, broker, fake, attempts = _harness(tmp_path)
    try:
        frames, ledger = _run(controller, _payload([TOOLS[0]]))
        assert frames[-1]["kind"] == "finish", frames
        assert ledger == {"fake": 1, "attempts": 1, "reservations": 1,
                          "claims": 1}
        # a *different* business identity must take its own cycle
        frames, ledger = _run(controller, _payload([TOOLS[0]], session="g4b-2"))
        assert frames[-1]["kind"] == "finish"
        assert ledger == {"fake": 2, "attempts": 2, "reservations": 2,
                          "claims": 2}
    finally:
        _close(broker, fake, attempts)


def test_extra_request_over_quota_is_denied_with_zero_send(tmp_path: Path) -> None:
    controller, broker, fake, attempts = _harness(tmp_path, max_calls=1)
    try:
        frames, ledger = _run(controller, _payload([TOOLS[0]], session="q1"))
        assert frames[-1]["kind"] == "finish"
        assert ledger == {"fake": 1, "attempts": 1, "reservations": 1,
                          "claims": 1}
        frames, ledger = _run(controller, _payload([TOOLS[0]], session="q2"))
        assert frames[-1]["kind"] == "error"
        assert frames[-1]["payload"]["code"] == "BUDGET_DENIED"
        assert ledger == {"fake": 1, "attempts": 1, "reservations": 1,
                          "claims": 1}
    finally:
        _close(broker, fake, attempts)


def test_approved_tool_set_has_no_duplicate_digest() -> None:
    digests = [_tool_digest(tool) for tool in TOOLS]
    assert len(set(digests)) == len(digests)
    assert all(len(digest) == 64 for digest in digests)
    with pytest.raises(ValueError):
        # the Controller canonicalises with sort_keys; NaN must never hash
        json.dumps({"x": float("nan")}, sort_keys=True, allow_nan=False)
