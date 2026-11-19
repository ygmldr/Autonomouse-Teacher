"""Shared TEST_ONLY helpers for G4-F3 accounting/authority host tests.

The Broker and Fake are real local subprocesses with the frozen synthetic
fixture; no Key, no model, no external socket. ``RecordingGate`` keeps the F3
cost-view snapshots at consume time so a test can observe the conservative
hold *before* the Broker terminal settlement releases it.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from autoteacher_m0.bridge.admission import load_admission
from autoteacher_m0.bridge.attempts import AttemptJournal
from autoteacher_m0.bridge.broker_client import BrokerClient
from autoteacher_m0.bridge.controller import TrustedController
from autoteacher_m0.bridge.fake_backend import FakeBackend
from autoteacher_m0.bridge.protocol import Envelope
from autoteacher_m0.security.egress import (
    SYNTHETIC_ROUTE_CONTRACT,
    TrustedSendGate,
)

from g4c_support import same_bindings

ROUTE = "offline-test-only-g3b"
MODEL = "fixture-bridge-v1"
SCOPE = "fixed-offline-scope"
FAKE = (Path(__file__).resolve().parents[3]
        / "spikes/g3b-trusted-bridge/fake/fake_provider.py")
RUN_ID = "run-g4f3-host"
AUTH_EPOCH = "g4f3-host-epoch"


def admission_document(*, scenario: str = "ok_usage", max_calls: int = 8) -> dict:
    tool = {"name": "skill_lookup", "sha256": hashlib.sha256(b"tool").hexdigest()}
    return {
        "schema": "m0.g3b.admission.v1", "admission_id": "a" * 32,
        "scope_id": SCOPE, "run_id": RUN_ID, "synthetic": True,
        "route": {"route_id": ROUTE, "provider": ROUTE, "model": MODEL},
        "tool_schemas": [tool],
        "limits": {"max_calls": max_calls, "max_attempts": 1,
                   "max_input_tokens": 2500000, "max_output_tokens": 1024,
                   "deadline_ms": 30000},
        "fake_scenario": scenario, "expiry_utc": "2099-01-01T00:00:00Z",
        "launcher": {"uid": 65534, "container": True,
                     "admission_nonce": "b" * 32},
    }


def broker_document(tmp_path: Path, *, per_call_usd: str = "0.20",
                    hard_usd: str = "10", max_requests: int = 50) -> dict:
    return {
        "v": 1, "synthetic": True,
        "db_path": str(tmp_path / "broker.sqlite3"),
        "scope_id": SCOPE, "max_messages": 64,
        "limits": {"soft_usd": "3", "hard_usd": hard_usd,
                   "per_call_usd": per_call_usd, "max_requests": max_requests,
                   "max_input_tokens": 2500000, "max_output_tokens": 600000,
                   "max_steps": 8, "max_retries": 1},
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


def write_admission(tmp_path: Path, *, scenario: str = "ok_usage",
                    max_calls: int = 8) -> Path:
    path = tmp_path / "admission.json"
    path.write_text(json.dumps(admission_document(scenario=scenario,
                                                  max_calls=max_calls)))
    return path


def write_broker_config(tmp_path: Path, *, per_call_usd: str = "0.20",
                        hard_usd: str = "10", max_requests: int = 50) -> Path:
    path = tmp_path / "broker.json"
    path.write_text(json.dumps(broker_document(tmp_path, per_call_usd=per_call_usd,
                                               hard_usd=hard_usd,
                                               max_requests=max_requests)))
    return path


class RecordingGate(TrustedSendGate):
    """Gate that snapshots its view at every consume (the pre-send moment)."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.probes: list[dict] = []

    def consume(self, authorization, **kwargs):  # type: ignore[override]
        denial = super().consume(authorization, **kwargs)
        self.probes.append({"denial": denial, "snapshot": self.snapshot()})
        return denial


def make_gate(*, budget=None) -> RecordingGate:
    bindings = same_bindings()
    kwargs = {} if budget is None else {"budget": budget}
    return RecordingGate(
        SYNTHETIC_ROUTE_CONTRACT, auth_epoch=AUTH_EPOCH,
        binding_approved=bindings, binding_observer=lambda: bindings, **kwargs)


def start_broker(tmp_path: Path, **options) -> BrokerClient:
    broker = BrokerClient(config_path=str(write_broker_config(tmp_path, **options)),
                          python=sys.executable)
    broker.start()
    return broker


def start_controller(tmp_path: Path, *, scenario: str = "ok_usage",
                     gate: TrustedSendGate | None = None,
                     broker: BrokerClient | None = None,
                     attempts: AttemptJournal | None = None,
                     broker_options: dict | None = None,
                     register_admission: bool = True,
                     max_calls: int = 8):
    admission = load_admission(write_admission(tmp_path, scenario=scenario,
                                               max_calls=max_calls),
                               expected_uid=65534)
    broker = broker or start_broker(tmp_path, **(broker_options or {}))
    fake = FakeBackend(script=str(FAKE), receipt_dir=str(tmp_path / "receipts"),
                       python=sys.executable, mode=scenario)
    attempts = attempts or AttemptJournal(tmp_path / "attempts.sqlite3")
    gate = gate or make_gate()
    controller = TrustedController(admission, broker=broker, fake=fake,
                                   attempts=attempts, expected_uid=65534,
                                   register_admission=register_admission,
                                   dispatch_gate=gate)
    return controller, broker, fake, attempts, gate


def request_payload(**overrides) -> dict:
    base = {"sessionId": "s1", "provider": ROUTE, "model": MODEL,
            "messages": [{"role": "user", "content": "hello"}], "tools": [],
            "system": None, "maxTokens": 256, "stream": True,
            "purpose": "conversation"}
    base.update(overrides)
    return base


def envelope(payload: dict) -> Envelope:
    return Envelope(v=1, kind="request", transport_id="tr-" + "a" * 32,
                    seq=2, payload=payload, hash=None)


def collect(controller: TrustedController, payload: dict) -> list[dict]:
    frames = []
    for env in controller.handle_envelope(envelope(payload)):
        item = {"kind": env.kind, "payload": env.payload}
        if "chunk" in env.payload:
            item["chunk"] = env.payload["chunk"]
        if "reason" in env.payload:
            item["reason"] = env.payload["reason"]
        frames.append(item)
    return frames


def call_error(frames: list[dict]) -> str | None:
    """Terminal error code from either an error frame or an error finish."""
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


def close_all(*resources) -> None:
    for resource in resources:
        if resource is None:
            continue
        try:
            resource.close()
        except Exception:  # noqa: BLE001 - best-effort test cleanup
            pass
