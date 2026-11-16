"""Controller-owned durable attempt journal (G3-B, SQLite WAL/FULL)."""
from __future__ import annotations
import functools
import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

ATTEMPTS_PATH = Path("/work/g3b/attempts.sqlite3")


def _locked(method):
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)
    return wrapper
STATES = frozenset({"RESERVED", "CLAIMED", "ATTEMPT_STARTED", "RESPONSE_OBSERVED",
                    "SETTLED", "WORST_CASE_HELD", "SETTLEMENT_UNCERTAIN"})


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class AttemptJournal:
    def __init__(self, sqlite_path: str | Path = ATTEMPTS_PATH):
        self.path = Path(sqlite_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(str(self.path), timeout=10, isolation_level=None,
                                    check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=FULL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("PRAGMA busy_timeout=10000")
        self._ddl()

    def _ddl(self) -> None:
        self.conn.executescript("""
CREATE TABLE IF NOT EXISTS g3b_attempts (
  attempt_id TEXT PRIMARY KEY, scope_id TEXT NOT NULL, call_id TEXT NOT NULL,
  reservation_id TEXT NOT NULL, prepared_digest TEXT NOT NULL,
  payload_digest TEXT NOT NULL, payload_length INTEGER NOT NULL,
  state TEXT NOT NULL CHECK(state IN ('RESERVED','CLAIMED','ATTEMPT_STARTED',
    'RESPONSE_OBSERVED','SETTLED','WORST_CASE_HELD','SETTLEMENT_UNCERTAIN')),
  receipt_id TEXT, receipt_json TEXT, settlement_json TEXT, reason TEXT,
  created_utc TEXT NOT NULL, updated_utc TEXT NOT NULL,
  UNIQUE(scope_id, call_id), UNIQUE(scope_id, reservation_id));
CREATE INDEX IF NOT EXISTS g3b_attempts_state ON g3b_attempts(scope_id,state);
CREATE TABLE IF NOT EXISTS g3b_admissions (
  admission_id TEXT PRIMARY KEY, admission_sha256 TEXT NOT NULL,
  consumed_utc TEXT NOT NULL, run_id TEXT NOT NULL,
  controller_instance_id TEXT NOT NULL);
""")

    @_locked
    def register_admission(self, admission_id: str, admission_sha256: str,
                           run_id: str, controller_instance_id: str) -> None:
        try:
            self.conn.execute("INSERT INTO g3b_admissions VALUES (?,?,?,?,?)",
                             (admission_id, admission_sha256, _utc(), run_id,
                              controller_instance_id))
        except sqlite3.IntegrityError as exc:
            raise ValueError("ADMISSION_REPLAYED") from exc

    @_locked
    def begin_attempt(self, *, scope_id: str, call_id: str, reservation_id: str,
                      prepared_digest: str, payload_digest: str,
                      payload_length: int) -> str:
        attempt_id = "att-" + uuid.uuid4().hex[:32]
        now = _utc()
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            self.conn.execute(
                "INSERT INTO g3b_attempts (attempt_id,scope_id,call_id,reservation_id,"
                "prepared_digest,payload_digest,payload_length,state,created_utc,updated_utc) "
                "VALUES (?,?,?,?,?,?,?, 'ATTEMPT_STARTED',?,?)",
                (attempt_id, scope_id, call_id, reservation_id, prepared_digest,
                 payload_digest, payload_length, now, now))
            self.conn.execute("COMMIT")
        except sqlite3.IntegrityError as exc:
            self.conn.execute("ROLLBACK")
            raise ValueError("ATTEMPT_ALREADY_STARTED") from exc
        except BaseException:
            if self.conn.in_transaction:
                self.conn.execute("ROLLBACK")
            raise
        return attempt_id

    @_locked
    def _update(self, attempt_id: str, state: str, **values) -> None:
        if state not in STATES:
            raise ValueError("invalid attempt state")
        fields = ["state=?", "updated_utc=?"]
        params = [state, _utc()]
        for key, value in values.items():
            fields.append(f"{key}=?")
            params.append(value)
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            self.conn.execute(f"UPDATE g3b_attempts SET {', '.join(fields)} WHERE attempt_id=?",
                              (*params, attempt_id))
            self.conn.execute("COMMIT")
        except BaseException:
            if self.conn.in_transaction:
                self.conn.execute("ROLLBACK")
            raise

    def mark_response_observed(self, attempt_id: str, *, receipt_id: str, receipt_json: str) -> None:
        self._update(attempt_id, "RESPONSE_OBSERVED", receipt_id=receipt_id,
                     receipt_json=receipt_json)

    def mark_settled(self, attempt_id: str, *, settlement_json: str) -> None:
        self._update(attempt_id, "SETTLED", settlement_json=settlement_json)

    def mark_worst_case(self, attempt_id: str, *, reason: str) -> None:
        self._update(attempt_id, "WORST_CASE_HELD", reason=reason)

    def mark_settlement_uncertain(self, attempt_id: str, *, reason: str) -> None:
        self._update(attempt_id, "SETTLEMENT_UNCERTAIN", reason=reason)

    @_locked
    def state_for_call(self, call_id: str) -> str | None:
        row = self.conn.execute("SELECT state FROM g3b_attempts WHERE call_id=?",
                                (call_id,)).fetchone()
        return None if row is None else row[0]

    @_locked
    def next_logical_step(self, run_id: str) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) FROM g3b_attempts WHERE call_id IN "
            "(SELECT call_id FROM g3b_attempts)").fetchone()
        return int(row[0])

    @_locked
    def reconcile_on_startup(self, receipt_dir: str | Path | None = None) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM g3b_attempts WHERE state IN "
            "('ATTEMPT_STARTED','RESPONSE_OBSERVED','SETTLEMENT_UNCERTAIN')").fetchall()
        if receipt_dir is not None:
            import glob
            for row in rows:
                if row["state"] != "ATTEMPT_STARTED":
                    continue
                for path in glob.glob(str(Path(receipt_dir) / "rcpt-*.json")):
                    try:
                        doc = json.loads(Path(path).read_text())
                    except Exception:
                        continue
                    if doc.get("raw_sha256") == row["payload_digest"]:
                        self._update(row["attempt_id"], "RESPONSE_OBSERVED",
                                     receipt_id=doc.get("receipt_id"),
                                     receipt_json=json.dumps(doc, sort_keys=True))
                        break
        rows = self.conn.execute(
            "SELECT * FROM g3b_attempts WHERE state IN "
            "('ATTEMPT_STARTED','RESPONSE_OBSERVED','SETTLEMENT_UNCERTAIN')").fetchall()
        return [dict(row) for row in rows]

    @_locked
    def close(self) -> None:
        self.conn.close()
