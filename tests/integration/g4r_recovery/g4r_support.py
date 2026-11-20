"""Shared TEST_ONLY helpers for the G4-R R2 recovery/observability host tests.

Two harnesses are provided:

* ``start_real_controller`` - the real local Broker/Fake subprocess fixture
  (G4-F3/G4-F5 support) plus the new G4-R request-lifecycle and recovery
  diagnostic journals. Used for the wire-level timeout/cancel/reject cases.
* ``start_recovery_harness`` - an in-process stub Broker with an authoritative
  configurable reservation status. Used to exercise the recovery decision table
  deterministically without spawning anything.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from autoteacher_m0.bridge.attempts import AttemptJournal
from autoteacher_m0.bridge.controller import TrustedController
from autoteacher_m0.bridge.dispatch_audit import DispatchAudit
from autoteacher_m0.bridge.request_lifecycle import RequestLifecycleAudit

import g4f3_support as f3
import g4f5_support as f5

LIFECYCLE = "request-lifecycle.jsonl"
DISPATCH = "dispatch-window.jsonl"
DIAGNOSTICS = "recovery-diagnostics.jsonl"


def attach_journals(controller: TrustedController, root: Path) -> TrustedController:
    """Inject the G4-R journals into a controller built by the F3/F5 harness."""
    controller.request_lifecycle = RequestLifecycleAudit(str(root / LIFECYCLE))
    controller.dispatch_audit = DispatchAudit(str(root / DISPATCH))
    return controller


def start_real_controller(tmp_path: Path, *, scenario: str = "ok_usage",
                          deadline_ms: int = 30000, max_calls: int = 8,
                          gate=None):
    """Real Broker+Fake subprocess chain with the G4-R journals attached."""
    controller, broker, fake, attempts, gate = f5.start_controller(
        tmp_path, gate=gate or f5.make_gate(), scenario=scenario,
        deadline_ms=deadline_ms, max_calls=max_calls)
    attach_journals(controller, tmp_path)
    return controller, broker, fake, attempts, gate


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def lifecycle_events(root: Path, *, event: str | None = None) -> list[dict]:
    rows = read_jsonl(root / LIFECYCLE)
    if event is None:
        return rows
    return [row for row in rows if row.get("event") == event]


def dispatch_rows(root: Path) -> list[dict]:
    return read_jsonl(root / DISPATCH)


def diagnostic_rows(root: Path) -> list[dict]:
    return read_jsonl(root / DIAGNOSTICS)


def broker_snapshot(broker) -> dict:
    reply = broker.snapshot()
    assert reply.get("ok") is True, reply
    return reply["snapshot"]


class StubBroker:
    """Minimal authoritative-status Broker double for recovery decision tests.

    It is *not* a fee authority replacement: it only answers the read-only
    ``reservation_status`` question that recovery already asks, and it records
    every settle/fail call so tests can prove at-most-once.
    """

    def __init__(self, status: str = "PENDING", *, settle_code: str = "SETTLED",
                 fail_code: str = "FAILED") -> None:
        self.status = status
        self.settle_code = settle_code
        self.fail_code = fail_code
        self.status_calls: list[str] = []
        self.settle_calls: list[dict] = []
        self.fail_calls: list[dict] = []

    def reservation_status(self, reservation_id, deadline_monotonic=None) -> dict:
        self.status_calls.append(reservation_id)
        return {
            "ok": True,
            "status": self.status,
            "reservation": {"reservation_id": reservation_id,
                            "status": self.status},
        }

    def settle(self, **kwargs) -> dict:
        self.settle_calls.append(dict(kwargs))
        return {"ok": True, "code": self.settle_code, "settlement": {"cost": "0.001"}}

    def fail(self, **kwargs) -> dict:
        self.fail_calls.append(dict(kwargs))
        return {"ok": True, "code": self.fail_code, "settlement": {"cost": "0"}}


class StubFake:
    """Receipt-directory carrier; recovery must never enter the Fake."""

    def __init__(self, root: Path) -> None:
        self.receipt_dir = str(root / "receipts")
        self.last_receipt = None

    def received_count(self) -> int:
        return 0


def start_recovery_harness(tmp_path: Path, *, broker_status: str = "PENDING",
                           settle_code: str = "SETTLED",
                           fail_code: str = "FAILED"):
    """Controller + stub Broker for the reconcile decision table."""
    from autoteacher_m0.bridge.admission import load_admission
    admission = load_admission(f3.write_admission(tmp_path), expected_uid=65534)
    broker = StubBroker(broker_status, settle_code=settle_code,
                        fail_code=fail_code)
    fake = StubFake(tmp_path)
    attempts = AttemptJournal(tmp_path / "attempts.sqlite3")
    controller = TrustedController(
        admission, broker=broker, fake=fake, attempts=attempts,
        expected_uid=65534, register_admission=False,
        recovery_diagnostics=str(tmp_path / DIAGNOSTICS))
    return controller, broker, attempts, fake


_UNSET = object()


def seed_attempt(attempts: AttemptJournal, *, reservation_id: str = "res-r2",
                 call_id: str = "call-r2", state: str = "RESPONSE_OBSERVED",
                 reason: str | None = None,
                 receipt_json: str | None | object = _UNSET,
                 attempt_id: str = "att-r2") -> str:
    """Insert one durable Attempt row exactly as a real Controller could leave it."""
    now = "2026-11-20T00:00:00Z"
    if receipt_json is _UNSET:
        receipt_json = json.dumps({"schema": "m0.g3c.observation.v1"},
                                  sort_keys=True)
    attempts.conn.execute(
        "INSERT OR REPLACE INTO g3b_attempts (attempt_id, scope_id, call_id,"
        " reservation_id, prepared_digest, payload_digest, payload_length, state,"
        " receipt_id, receipt_json, settlement_json, reason, created_utc,"
        " updated_utc, run_id, logical_step, mode, input_bound_kind,"
        " input_bound_tokens, fee_policy_version) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (attempt_id, f3.SCOPE, call_id, reservation_id, "a" * 64, "b" * 64, 64,
         state, None, receipt_json, None, reason, now, now, f3.RUN_ID, 0,
         "ok_usage", "utf8_bytes_upper_bound", 1, "fixture-synthetic-v1"))
    return attempt_id


def attempt_rows(path: Path) -> list[dict]:
    """Independent read-only view of the raw durable Attempt rows."""
    uri = f"file:{path}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in
                connection.execute("SELECT * FROM g3b_attempts ORDER BY call_id")]
    finally:
        connection.close()
