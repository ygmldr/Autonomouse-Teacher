"""Shared TEST_ONLY harness for G4-F2 dispatch-window tests.

Real local Broker/Fake subprocesses and the real trusted Controller/Attempt
journal are used; no Key, no model, no external network. Every negative asserts
both the stable error code and the ledger (0 Reserved / 0 Claimed / 0 Attempt /
Fake counter 0) plus the per-dispatch journal record.
"""
from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Iterable

from autoteacher_m0.bridge.admission import load_admission
from autoteacher_m0.bridge.attempts import AttemptJournal
from autoteacher_m0.bridge.broker_client import BrokerClient
from autoteacher_m0.bridge.controller import TrustedController
from autoteacher_m0.bridge.fake_backend import FakeBackend
from autoteacher_m0.bridge.protocol import Envelope

REPO = Path(__file__).resolve().parents[3]
FAKE = REPO / "spikes/g3b-trusted-bridge/fake/fake_provider.py"
ROUTE = "offline-test-only-g3b"
MODEL = "fixture-bridge-v1"
SCOPE = "fixed-offline-scope"
LAUNCHER_UID = 65534

TOOL = {
    "name": "skill_lookup",
    "description": ("Look up fixed public skill metadata by a nonempty skill id. "
                    "Unknown ids return SKILL_NOT_FOUND. No filesystem paths are accepted."),
    "parameters": {
        "type": "object",
        "properties": {
            "skill_id": {
                "type": "string",
                "description": ("Nonempty stable skill id, e.g. binary_search; "
                                "not a filesystem path."),
            }
        },
        "required": ["skill_id"],
    },
}


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def tool_digest(tool: object) -> str:
    return hashlib.sha256(canonical(tool).encode("utf-8")).hexdigest()


def admission_document(*, scenario: str = "ok_usage", max_calls: int = 8,
                       launcher_uid: int = LAUNCHER_UID) -> dict:
    return {
        "schema": "m0.g3b.admission.v1", "admission_id": "a" * 32,
        "scope_id": SCOPE, "run_id": "run-g4f2-host", "synthetic": True,
        "route": {"route_id": ROUTE, "provider": ROUTE, "model": MODEL},
        "tool_schemas": [{"name": TOOL["name"], "sha256": tool_digest(TOOL)}],
        "limits": {"max_calls": max_calls, "max_attempts": 1,
                   "max_input_tokens": 2500000, "max_output_tokens": 1024,
                   "deadline_ms": 30000},
        "fake_scenario": scenario, "expiry_utc": "2099-01-01T00:00:00Z",
        "launcher": {"uid": launcher_uid, "container": True,
                     "admission_nonce": "b" * 32},
    }


def write_admission(tmp_path: Path, **options) -> Path:
    path = tmp_path / "admission.json"
    path.write_text(json.dumps(admission_document(**options)), encoding="utf-8")
    return path


def broker_document(tmp_path: Path) -> dict:
    return {
        "v": 1, "synthetic": True,
        "db_path": str(tmp_path / "broker.sqlite3"),
        "scope_id": SCOPE, "max_messages": 64,
        "limits": {"soft_usd": "3", "hard_usd": "10",
                   "per_call_usd": "0.20", "max_requests": 50,
                   "max_input_tokens": 2500000, "max_output_tokens": 600000,
                   "max_steps": 8, "max_retries": 0},
        "routes": [{
            "route_id": ROUTE, "model": MODEL,
            "price": {"version": "fixture-v1", "input_per_million": "1",
                      "output_per_million": "2",
                      "cached_input_per_million": "0.5",
                      "source": "synthetic fixture",
                      "captured_at": "2026-11-16"},
            "known_extra_fee_usd": "0.001",
            "usage_policy": {"cache_write": "input_rate",
                             "reasoning": "included_in_output"},
        }],
    }


def write_broker_config(tmp_path: Path) -> Path:
    path = tmp_path / "broker.json"
    path.write_text(json.dumps(broker_document(tmp_path)), encoding="utf-8")
    return path


def start_controller(tmp_path: Path, *, journal: bool = True,
                     scenario: str = "ok_usage", max_calls: int = 8,
                     launcher_uid: int = LAUNCHER_UID,
                     expected_uid: int = LAUNCHER_UID,
                     journal_path: Path | None = None,
                     require_origin: bool = False):
    admission = load_admission(
        write_admission(tmp_path, scenario=scenario, max_calls=max_calls,
                        launcher_uid=launcher_uid),
        expected_uid=expected_uid)
    broker = BrokerClient(config_path=str(write_broker_config(tmp_path)),
                          python=sys.executable)
    broker.start()
    fake = FakeBackend(script=str(FAKE), receipt_dir=str(tmp_path / "receipts"),
                       python=sys.executable, mode=scenario)
    attempts = AttemptJournal(tmp_path / "attempts.sqlite3")
    if journal_path is None:
        journal_path = tmp_path / "dispatch-window.jsonl"
    controller = TrustedController(
        admission, broker=broker, fake=fake, attempts=attempts,
        expected_uid=expected_uid,
        dispatch_journal=journal_path if journal else None,
        require_origin=require_origin)
    return controller, broker, fake, attempts


def request_payload(**overrides) -> dict:
    base = {
        "sessionId": "g4f2-session", "provider": ROUTE, "model": MODEL,
        "messages": [{"role": "user",
                      "content": [{"type": "text", "text": "G4F2"}]}],
        "tools": [], "system": None, "maxTokens": 256, "stream": True,
        "purpose": "conversation",
    }
    base.update(overrides)
    return base


def envelope(payload: dict, *, transport_id: str = "tr-" + "a" * 32) -> Envelope:
    return Envelope(v=1, kind="request", transport_id=transport_id, seq=2,
                    payload=payload, hash=None)


def collect(controller: TrustedController, payload: dict, *,
            transport_id: str = "tr-" + "a" * 32) -> list[dict]:
    frames = []
    for env in controller.handle_envelope(envelope(payload, transport_id=transport_id)):
        frames.append({"kind": env.kind, "payload": env.payload})
    return frames


def call_error(frames: Iterable[dict]) -> str | None:
    for frame in frames:
        if frame["kind"] == "error":
            return frame["payload"].get("code")
        if frame["kind"] == "finish":
            reason = frame["payload"].get("reason")
            if isinstance(reason, dict) and reason.get("kind") == "error":
                failure = reason.get("failure")
                if isinstance(failure, dict) and failure.get("code"):
                    return str(failure["code"])
                return "TERMINAL_ERROR"
    return None


def ledger(controller: TrustedController) -> dict:
    snapshot = controller.broker.snapshot()["snapshot"]
    return {
        "fake": controller.fake.received_count(),
        "attempts": controller.attempts.conn.execute(
            "SELECT COUNT(*) FROM g3b_attempts").fetchone()[0],
        "reservations": snapshot["requests"],
        "claims": snapshot["claims"]["total"],
    }


def journal_records(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def deep_copy(tool: dict) -> dict:
    return copy.deepcopy(tool)


def close_all(*resources) -> None:
    for resource in resources:
        if resource is None:
            continue
        try:
            resource.close()
        except Exception:  # noqa: BLE001 - best-effort test cleanup
            pass
