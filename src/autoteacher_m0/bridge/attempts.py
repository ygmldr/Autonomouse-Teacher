"""Controller-owned durable attempt journal (G3-B/G3-C, SQLite WAL/FULL).

G3-C additions are additive:
* ``g3b_send_intents`` records a durable pre-send intent between Broker Reserve
  and the durable ``ATTEMPT_STARTED`` row, so a crash in
  ``after_reserve_before_claim`` / ``after_claim_before_attempt`` remains visible
  to recovery (no send is ever inferred from an intent).
* ``g3b_request_identities`` durably binds one business request digest to one
  call id inside the admission scope; a replay of the same business request on
  another transport is rejected before a second send.
* ``begin_attempt`` consumes the intent in the same transaction as the durable
  attempt insert; send is allowed only after that commit.

P1-2 (G3-C review): the SQLite initialisation is deterministic under concurrent
cold starts. ``busy_timeout`` is installed before the ``journal_mode=WAL``
transition, WAL/DDL lock failures are retried for a bounded interval, benign
``duplicate column name`` races from two initialisers are accepted, and
exhaustion raises ``AttemptJournalUnavailable`` so the Controller can exit with
a stable ``ATTEMPT_JOURNAL_UNAVAILABLE`` code instead of a traceback.
"""
from __future__ import annotations
import functools
import json
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

ATTEMPTS_PATH = Path("/work/g3b/attempts.sqlite3")

# Journal initialisation is the only place where a cold Controller must wait for
# another SQLite writer. The wait is deliberately bounded and retried here
# instead of being an unbounded (or absent) ``busy_timeout``. A caller that
# exhausts the budget gets ``AttemptJournalUnavailable`` and can exit with a
# stable, auditable code instead of leaking ``sqlite3.OperationalError``.
DEFAULT_INIT_RETRY_SECONDS = 10.0
DEFAULT_INIT_RETRY_INTERVAL_SECONDS = 0.05
INIT_BUSY_TIMEOUT_MS = 250
RUNTIME_BUSY_TIMEOUT_MS = 10_000
_RETRYABLE_SQLITE_CODES = frozenset({5, 6})  # SQLITE_BUSY / SQLITE_LOCKED


class AttemptJournalUnavailable(RuntimeError):
    """The durable journal could not be opened after bounded lock retries."""

    code = "ATTEMPT_JOURNAL_UNAVAILABLE"

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.code)


def _is_retryable_lock_error(exc: BaseException) -> bool:
    """True only for transient SQLite lock/busy errors, never for real errors."""
    code = getattr(exc, "sqlite_errorcode", None)
    if isinstance(code, int) and (code & 0xFF) in _RETRYABLE_SQLITE_CODES:
        return True
    text = str(exc).lower()
    return "database is locked" in text or "database table is locked" in text \
        or "database schema is locked" in text or "database is busy" in text


def _locked(method):
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)
    return wrapper


STATES = frozenset({"RESERVED", "CLAIMED", "ATTEMPT_STARTED", "RESPONSE_OBSERVED",
                    "SETTLED", "WORST_CASE_HELD", "SETTLEMENT_UNCERTAIN"})
INTENT_STATES = frozenset({"RESERVED", "CLAIMED", "HELD_UNCERTAIN", "CONSUMED"})
TERMINAL_ATTEMPT_STATES = frozenset({"SETTLED", "WORST_CASE_HELD"})
_NONTERMINAL = "('ATTEMPT_STARTED','RESPONSE_OBSERVED','SETTLEMENT_UNCERTAIN')"
_ATTEMPT_COLUMNS = {
    "run_id": "TEXT", "logical_step": "INTEGER", "mode": "TEXT",
    "input_bound_kind": "TEXT", "input_bound_tokens": "INTEGER",
    "fee_policy_version": "TEXT",
}


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class AttemptJournal:
    def __init__(self, sqlite_path: str | Path = ATTEMPTS_PATH, *,
                 init_retry_seconds: float = DEFAULT_INIT_RETRY_SECONDS,
                 init_retry_interval: float = DEFAULT_INIT_RETRY_INTERVAL_SECONDS):
        self.path = Path(sqlite_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.init_attempts = 0
        self.conn = sqlite3.connect(str(self.path), timeout=10, isolation_level=None,
                                    check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        try:
            self._initialize(max(float(init_retry_seconds), 0.0),
                             max(float(init_retry_interval), 0.001))
        except BaseException:
            try:
                self.conn.close()
            except sqlite3.Error:
                pass
            raise

    def _initialize(self, retry_seconds: float, retry_interval: float) -> None:
        """Set pragmas/DDL with a bounded retry on transient SQLite locks.

        Ordering matters: ``busy_timeout`` must be installed *before* the
        ``journal_mode=WAL`` transition. The short init timeout keeps the total
        wall-clock bound under our control (``retry_seconds``) while the
        runtime timeout is raised to the normal 10 s only after success.
        """
        deadline = time.monotonic() + retry_seconds
        while True:
            self.init_attempts += 1
            try:
                self.conn.execute(f"PRAGMA busy_timeout={INIT_BUSY_TIMEOUT_MS}")
                self.conn.execute("PRAGMA journal_mode=WAL")
                self.conn.execute("PRAGMA synchronous=FULL")
                self.conn.execute("PRAGMA foreign_keys=ON")
                self._ddl()
                self.conn.execute(f"PRAGMA busy_timeout={RUNTIME_BUSY_TIMEOUT_MS}")
                return
            except sqlite3.OperationalError as exc:
                if not _is_retryable_lock_error(exc):
                    raise
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise AttemptJournalUnavailable() from exc
                time.sleep(min(retry_interval, remaining))

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
CREATE TABLE IF NOT EXISTS g3b_send_intents (
  intent_id TEXT PRIMARY KEY, scope_id TEXT NOT NULL, call_id TEXT NOT NULL,
  reservation_id TEXT NOT NULL, prepared_digest TEXT NOT NULL,
  payload_digest TEXT NOT NULL, payload_length INTEGER NOT NULL,
  state TEXT NOT NULL CHECK(state IN ('RESERVED','CLAIMED','HELD_UNCERTAIN','CONSUMED')),
  reason TEXT, created_utc TEXT NOT NULL, updated_utc TEXT NOT NULL,
  UNIQUE(scope_id, call_id), UNIQUE(scope_id, reservation_id));
CREATE TABLE IF NOT EXISTS g3b_request_identities (
  scope_id TEXT NOT NULL, identity_digest TEXT NOT NULL, call_id TEXT NOT NULL,
  logical_step INTEGER NOT NULL, created_utc TEXT NOT NULL,
  PRIMARY KEY(scope_id, identity_digest));
""")
        existing = {row[1] for row in self.conn.execute("PRAGMA table_info(g3b_attempts)")}
        for name, kind in _ATTEMPT_COLUMNS.items():
            if name not in existing:
                try:
                    self.conn.execute(f"ALTER TABLE g3b_attempts ADD COLUMN {name} {kind}")
                except sqlite3.OperationalError as exc:
                    # Two cold initialisers can both observe the pre-migration
                    # schema and race the same ADD COLUMN. Losing that benign
                    # race is success as long as the column now exists.
                    if "duplicate column name" not in str(exc).lower():
                        raise
                    current = {row[1] for row in
                               self.conn.execute("PRAGMA table_info(g3b_attempts)")}
                    if name not in current:
                        raise

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
    def admission_registered(self, admission_id: str) -> bool:
        return self.conn.execute("SELECT 1 FROM g3b_admissions WHERE admission_id=?",
                                 (admission_id,)).fetchone() is not None

    @_locked
    def claim_request_identity(self, *, scope_id: str, identity_digest: str,
                               call_id: str, logical_step: int) -> bool:
        """Atomically reserve one business-request identity before any Broker call.

        Returns True on the first reservation and raises ``ATTEMPT_ALREADY_STARTED``
        for a durable replay (including a different IPC transport id). The row is
        intentionally not deleted on send failure: a crash must never allow a
        silent second send for the same business request.
        """
        if not isinstance(identity_digest, str) or len(identity_digest) != 64:
            raise ValueError("REQUEST_INVALID")
        try:
            self.conn.execute(
                "INSERT INTO g3b_request_identities VALUES (?,?,?,?,?)",
                (scope_id, identity_digest, call_id, logical_step, _utc()))
        except sqlite3.IntegrityError as exc:
            raise ValueError("ATTEMPT_ALREADY_STARTED") from exc
        return True

    @_locked
    def request_identity_for_call(self, call_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM g3b_request_identities WHERE call_id=?", (call_id,)).fetchone()
        return None if row is None else dict(row)

    @_locked
    def record_intent(self, *, scope_id: str, call_id: str, reservation_id: str,
                      prepared_digest: str, payload_digest: str,
                      payload_length: int) -> str:
        intent_id = "int-" + uuid.uuid4().hex[:32]
        now = _utc()
        try:
            self.conn.execute(
                "INSERT INTO g3b_send_intents (intent_id,scope_id,call_id,reservation_id,"
                "prepared_digest,payload_digest,payload_length,state,created_utc,updated_utc) "
                "VALUES (?,?,?,?,?,?,?,'RESERVED',?,?)",
                (intent_id, scope_id, call_id, reservation_id, prepared_digest,
                 payload_digest, payload_length, now, now))
        except sqlite3.IntegrityError as exc:
            raise ValueError("ATTEMPT_ALREADY_STARTED") from exc
        return intent_id

    @_locked
    def mark_intent_claimed(self, intent_id: str) -> None:
        self.conn.execute(
            "UPDATE g3b_send_intents SET state='CLAIMED', updated_utc=? "
            "WHERE intent_id=? AND state='RESERVED'", (_utc(), intent_id))

    @_locked
    def mark_intent_held(self, intent_id: str, *, reason: str) -> None:
        self.conn.execute(
            "UPDATE g3b_send_intents SET state='HELD_UNCERTAIN', reason=?, updated_utc=? "
            "WHERE intent_id=? AND state IN ('RESERVED','CLAIMED')",
            (str(reason)[:256], _utc(), intent_id))

    @_locked
    def intent_for_call(self, call_id: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM g3b_send_intents WHERE call_id=?",
                                (call_id,)).fetchone()
        return None if row is None else dict(row)

    @_locked
    def pending_intents(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM g3b_send_intents WHERE state IN ('RESERVED','CLAIMED','HELD_UNCERTAIN') "
            "ORDER BY created_utc").fetchall()
        return [dict(row) for row in rows]

    @_locked
    def begin_attempt(self, *, scope_id: str, call_id: str, reservation_id: str,
                      prepared_digest: str, payload_digest: str,
                      payload_length: int, run_id: str | None = None,
                      logical_step: int | None = None, mode: str | None = None,
                      input_bound_kind: str | None = None,
                      input_bound_tokens: int | None = None,
                      fee_policy_version: str | None = None) -> str:
        attempt_id = "att-" + uuid.uuid4().hex[:32]
        now = _utc()
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            self.conn.execute(
                "INSERT INTO g3b_attempts (attempt_id,scope_id,call_id,reservation_id,"
                "prepared_digest,payload_digest,payload_length,state,run_id,logical_step,"
                "mode,input_bound_kind,input_bound_tokens,fee_policy_version,"
                "created_utc,updated_utc) "
                "VALUES (?,?,?,?,?,?,?,'ATTEMPT_STARTED',?,?,?,?,?,?,?,?)",
                (attempt_id, scope_id, call_id, reservation_id, prepared_digest,
                 payload_digest, payload_length, run_id, logical_step, mode,
                 input_bound_kind, input_bound_tokens, fee_policy_version, now, now))
            # Consuming the pre-send intent and inserting the durable attempt are
            # one local transaction. A crash before COMMIT leaves the intent, never
            # an attempt that could be mistaken for a completed durable send.
            self.conn.execute(
                "UPDATE g3b_send_intents SET state='CONSUMED', updated_utc=? "
                "WHERE scope_id=? AND call_id=?", (now, scope_id, call_id))
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

    @_locked
    def mark_response_observed(self, attempt_id: str, *, receipt_id: str, receipt_json: str) -> None:
        """Persist the trusted observation exactly once per attempt.

        Same document replay is idempotent. A different Observation Digest for
        the same durable attempt is an identity conflict: the Controller must
        not overwrite the first trusted observation (C2-03B).
        """
        row = self.conn.execute(
            "SELECT state, receipt_json FROM g3b_attempts WHERE attempt_id=?",
            (attempt_id,)).fetchone()
        if row is not None and row["receipt_json"] is not None:
            try:
                previous = json.loads(row["receipt_json"])
                incoming = json.loads(receipt_json)
            except (TypeError, ValueError, json.JSONDecodeError):
                raise ValueError("OBSERVATION_CONFLICT") from None
            old_digest = previous.get("journal_digest") if isinstance(previous, dict) else None
            new_digest = incoming.get("journal_digest") if isinstance(incoming, dict) else None
            if old_digest == new_digest and old_digest is not None:
                return
            raise ValueError("OBSERVATION_CONFLICT")
        if row is not None and row["state"] in {"RESPONSE_OBSERVED", "SETTLED",
                                                 "WORST_CASE_HELD"}:
            raise ValueError("OBSERVATION_CONFLICT")
        self._update(attempt_id, "RESPONSE_OBSERVED", receipt_id=receipt_id,
                     receipt_json=receipt_json)

    def mark_settled(self, attempt_id: str, *, settlement_json: str) -> None:
        self._update(attempt_id, "SETTLED", settlement_json=settlement_json)

    def mark_worst_case(self, attempt_id: str, *, reason: str) -> None:
        # Known terminal archival of a conservative hold. Never used for an
        # already-settled Broker reservation: the Broker status is authoritative.
        self._update(attempt_id, "WORST_CASE_HELD", reason=reason)

    def mark_settlement_uncertain(self, attempt_id: str, *, reason: str) -> None:
        self._update(attempt_id, "SETTLEMENT_UNCERTAIN", reason=reason)

    @_locked
    def state_for_call(self, call_id: str) -> str | None:
        row = self.conn.execute("SELECT state FROM g3b_attempts WHERE call_id=?",
                                (call_id,)).fetchone()
        return None if row is None else row[0]

    @_locked
    def attempt_for_call(self, call_id: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM g3b_attempts WHERE call_id=?",
                                (call_id,)).fetchone()
        return None if row is None else dict(row)

    @_locked
    def attempts(self) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM g3b_attempts ORDER BY created_utc, call_id").fetchall()
        return [dict(row) for row in rows]

    @_locked
    def pending_attempts(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM g3b_attempts WHERE state IN " + _NONTERMINAL +
            " ORDER BY created_utc, call_id").fetchall()
        return [dict(row) for row in rows]

    @_locked
    def next_logical_step(self, run_id: str) -> int:
        # NOT used by the runtime path (documented P2 residual in the G3-C task
        # book); retained unchanged for callers that only need a conservative
        # count. It deliberately does not become an authorization source.
        row = self.conn.execute(
            "SELECT COUNT(*) FROM g3b_attempts WHERE call_id IN "
            "(SELECT call_id FROM g3b_attempts)").fetchone()
        return int(row[0])

    @_locked
    def reconcile_on_startup(self, receipt_dir: str | Path | None = None) -> list[dict]:
        entries = self.pending_attempts()
        if receipt_dir is not None:
            import glob
            for row in entries:
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
        return self.pending_attempts()

    @_locked
    def close(self) -> None:
        self.conn.close()
