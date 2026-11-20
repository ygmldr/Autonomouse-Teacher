"""SQLite persistence for the M1-A teacher (B-PR2).

:class:`SqliteRepository` implements the frozen
:class:`~m1_teacher.contracts.repository.LearnerRepository` and
:class:`~m1_teacher.contracts.repository.SessionRepository` protocols with the
Python standard library only (``sqlite3``).  It also provides a few **additive**
extensions required for crash-consistent state + history updates:

``append_event(event)``
    Idempotent on ``event_id`` (returns ``False`` for a duplicate).
``append_events(events)``
    Atomic batch append (all-or-nothing transaction), same idempotency rule.
``append_event_and_upsert_snapshot(event, snapshot)`` / ``append_events_and_upsert_snapshot(events, snapshot)``
    Atomically append event(s) **and** upsert the materialised snapshot in a
    single transaction; this is the primitive :class:`LearningHistory` uses so
    that a crash can never leave the snapshot ahead of / behind the log.
``ensure_learner(learner_id)``
    Explicitly register a learner row (writes otherwise auto-provision it).

Schema (``schema_meta.version == 1``)
-------------------------------------
* ``schema_meta(version)`` — one row with the schema version; opening a
  database written by an unsupported/newer version fails closed.
* ``learners(learner_id PK, created_at, updated_at)``
* ``snapshots(learner_id PK -> learners, revision, updated_at, snapshot_json)``
* ``history_events(event_id PK, learner_id -> learners, session_id, seq,
  event_type, payload_json, created_at, UNIQUE(learner_id, seq))``
* ``goals(goal_id PK, learner_id -> learners, objective_id, status, goal_json,
  created_at)``
* ``sessions(session_id PK, learner_id -> learners, state_json, updated_at)``

``PRAGMA journal_mode=WAL``, ``PRAGMA foreign_keys=ON`` and a busy timeout are
enabled on every connection.  Writes use ``BEGIN IMMEDIATE`` transactions.

Fail-closed rules
-----------------
* Empty/blank ids, malformed records, non-JSON payloads, negative ``seq`` and
  invalid timestamps raise :class:`ValidationError` **before** anything is
  written.
* Duplicate ``event_id`` returns ``False`` (never an exception, never a
  duplicate row).
* A ``(learner_id, seq)`` collision with a different ``event_id`` raises
  :class:`~m1_teacher.contracts.errors.ConflictError` (the alternative return
  value was deliberately rejected: a silent collision would corrupt replay).
* Optimistic concurrency for snapshots: replacing a snapshot with a **lower**
  ``revision`` than the stored one raises ``ConflictError``; equal or newer
  revisions are accepted (equal revision is an idempotent rewrite).
* Corrupted JSON found in the database (for example after manual tampering)
  raises ``ValidationError`` instead of returning wrong state.
* ``upsert_snapshot`` for a learner with no row in ``learners`` raises
  ``ValidationError``: a materialised snapshot must be tied to history (or an
  explicit ``ensure_learner`` call).

Single-writer assumption
------------------------
The repository serialises writers with SQLite, but sequence allocation is owned
by :class:`LearningHistory`/the session engine and assumes one writer per
learner *scope*: concurrent writers are serialised by ``BEGIN IMMEDIATE`` and
must resolve explicit ``ConflictError`` codes (``SESSION_VERSION_CONFLICT``,
``EVENT_SEQ_CONFLICT``, ``DUPLICATE_EVENT``, ``DB_BUSY``) by reloading and
retrying.  Silent last-write-wins is never allowed.  Multi-process operation
against one SQLite file is supported for crash recovery and serialised
concurrency tests; a single active writer per learner/session remains the
product constraint documented in ``docs/M1_B_TXN_RECOVERY.md``.

B-NEXT (B-PR2) transactional teaching-turn commit
-------------------------------------------------
``commit_teaching_turn(learner_id=..., session_id=..., expected_session_version=...,
events=..., snapshot=None, next_session=..., goal=None)`` commits the whole
assessment turn in **one** ``BEGIN IMMEDIATE`` transaction:

1. validate every argument (re-using the fail-closed ``_validated_*`` helpers);
2. compare the stored session content digest with ``expected_session_version``
   (compare-and-swap; mismatch -> ``ConflictError`` code
   ``SESSION_VERSION_CONFLICT``).  The digest is
   :meth:`SqliteRepository.session_version`, a 16-hex-character SHA-256 prefix
   of the canonical JSON session payload (no schema/field change);
3. insert the events (duplicate ``event_id`` -> ``ConflictError`` code
   ``DUPLICATE_EVENT``; ``(learner_id, seq)`` collision -> ``ConflictError`` code
   ``EVENT_SEQ_CONFLICT``);
4. upsert the snapshot when supplied (stale ``revision`` ->
   ``ConflictError`` code ``SNAPSHOT_REVISION_CONFLICT``);
5. optionally upsert the goal;
6. write ``next_session`` after validating identity, monotonic
   ``turn_index`` and the pending/terminal/PREPARED consistency invariant;
7. ``COMMIT``; any exception rolls the whole transaction back.

The method is *additive*: all legacy methods keep their old behaviour and the
engine falls back to the legacy (non-atomic, explicitly documented) flow when a
repository does not implement it.

Crash failpoints (test-only)
----------------------------
When the environment variable :data:`FAILPOINT_ENV` is set (never in normal
operation), the commit path calls ``os.kill(os.getpid(), SIGKILL)`` at the named
write point, producing a *real* process crash (never a mock exception).  Point
names: ``after_begin``, ``after_session_check``,
``before_event_insert_<n>``/``after_event_insert_<n>`` (1-based),
``before_snapshot``/``after_snapshot``, ``before_goal``/``after_goal``,
``before_session``/``after_session``, ``before_commit``, ``after_commit``.
A ``prepare:`` / ``commit:`` prefix restricts the failpoint to the
``ASSESSMENT_PREPARED`` transaction A / terminal transaction B respectively
(inferred from the event types); an unprefixed name matches both.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from ..contracts.errors import ConflictError, NotFoundError, ValidationError
from ..contracts.types import (
    HistoryEvent,
    LearnerGoal,
    LearnerSnapshot,
    SessionState,
    now_utc,
)

__all__ = ["FAILPOINT_ENV", "SCHEMA_VERSION", "SqliteRepository", "session_version"]

SCHEMA_VERSION = 1
"""Current on-disk schema version."""

_TS_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
_TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

FAILPOINT_ENV = "M1B_CRASH_FAILPOINT"
"""Environment variable enabling the real-process crash failpoints (test only)."""

_SESSION_VERSION_LENGTH = 16
_PREPARED_EVENT_TYPE = "ASSESSMENT_PREPARED"
_TERMINAL_EVENT_TYPES = frozenset({"ASSESSED", "MASTERY_UPDATED", "ERROR", "GOAL_COMPLETED"})
_FAILPOINT_SCOPES = frozenset({"prepare", "commit"})
_DEFAULT_BUSY_TIMEOUT_MS = 5000


def _canonical_session_payload(state: SessionState) -> str:
    """Canonical (sorted-key, compact) JSON of a validated session state."""

    try:
        normalized = SessionState.from_dict(state.to_dict())
    except ValidationError as exc:
        raise ValidationError(f"session_version(): invalid SessionState: {exc.message}") from None
    return json.dumps(
        normalized.to_dict(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def session_version(state: SessionState) -> str:
    """Content digest used as the optimistic-concurrency version of a session.

    ``sha256(canonical_json(session.to_dict()))[:16]``.  The frozen
    :class:`SessionState` contract is unchanged: no field is added, the version
    is a pure function of the persisted content (so any state change, including
    a ``pending_item_id``/``turn_index``/``phase`` transition, changes it).
    """

    if not isinstance(state, SessionState):
        raise ValidationError("session_version(): expected a SessionState instance")
    payload = _canonical_session_payload(state)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:_SESSION_VERSION_LENGTH]


def _crash_failpoint(point: str, scope: str) -> None:
    """Kill the current process at a named write point when explicitly enabled.

    Disabled unless :data:`FAILPOINT_ENV` is set to exactly this point (or to
    ``"<scope>:<point>"``); the normal code path is unchanged (a dictionary
    lookup returning immediately).
    """

    raw = os.environ.get(FAILPOINT_ENV)
    if not raw:
        return
    wanted_point = raw
    wanted_scope: str | None = None
    if ":" in raw:
        prefix, _, suffix = raw.partition(":")
        if prefix in _FAILPOINT_SCOPES:
            wanted_scope = prefix
            wanted_point = suffix
    if wanted_scope is not None and wanted_scope != scope:
        return
    if wanted_point != point:
        return
    os.kill(os.getpid(), signal.SIGKILL)

_TABLE_SQL: tuple[str, ...] = (
    """CREATE TABLE IF NOT EXISTS schema_meta (
           version INTEGER NOT NULL
       )""",
    """CREATE TABLE IF NOT EXISTS learners (
           learner_id TEXT PRIMARY KEY,
           created_at TEXT NOT NULL,
           updated_at TEXT NOT NULL
       )""",
    """CREATE TABLE IF NOT EXISTS snapshots (
           learner_id TEXT PRIMARY KEY REFERENCES learners(learner_id),
           revision INTEGER NOT NULL,
           updated_at TEXT NOT NULL,
           snapshot_json TEXT NOT NULL
       )""",
    """CREATE TABLE IF NOT EXISTS history_events (
           event_id TEXT PRIMARY KEY,
           learner_id TEXT NOT NULL REFERENCES learners(learner_id),
           session_id TEXT NOT NULL,
           seq INTEGER NOT NULL CHECK (seq >= 0),
           event_type TEXT NOT NULL,
           payload_json TEXT NOT NULL,
           created_at TEXT NOT NULL,
           UNIQUE (learner_id, seq)
       )""",
    "CREATE INDEX IF NOT EXISTS idx_history_events_learner_seq "
    "ON history_events(learner_id, seq)",
    """CREATE TABLE IF NOT EXISTS goals (
           goal_id TEXT PRIMARY KEY,
           learner_id TEXT NOT NULL REFERENCES learners(learner_id),
           objective_id TEXT NOT NULL,
           status TEXT NOT NULL,
           goal_json TEXT NOT NULL,
           created_at TEXT NOT NULL
       )""",
    "CREATE INDEX IF NOT EXISTS idx_goals_learner ON goals(learner_id)",
    """CREATE TABLE IF NOT EXISTS sessions (
           session_id TEXT PRIMARY KEY,
           learner_id TEXT NOT NULL REFERENCES learners(learner_id),
           state_json TEXT NOT NULL,
           updated_at TEXT NOT NULL
       )""",
    "CREATE INDEX IF NOT EXISTS idx_sessions_learner_updated "
    "ON sessions(learner_id, updated_at)",
)


# ---------------------------------------------------------------------------
# Small validation helpers
# ---------------------------------------------------------------------------


def _require_nonempty_str(value: Any, where: str) -> str:
    if type(value) is not str or not value.strip():
        raise ValidationError(f"{where}: expected a non-blank string")
    return value


def _require_int(value: Any, where: str, *, minimum: int | None = None) -> int:
    if type(value) is not int:
        raise ValidationError(f"{where}: expected an integer, got {type(value).__name__}")
    if minimum is not None and value < minimum:
        raise ValidationError(f"{where}: {value!r} is below the minimum {minimum!r}")
    return value


def _require_timestamp(value: Any, where: str) -> str:
    if type(value) is not str or not _TS_RE.match(value):
        raise ValidationError(f"{where}: expected a UTC ISO-8601 second-precision timestamp")
    try:
        datetime.strptime(value, _TS_FORMAT)
    except ValueError as exc:
        raise ValidationError(f"{where}: {value!r} is not a real date/time") from exc
    return value


def _json_dumps(value: Any, where: str) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{where}: payload is not JSON-serialisable: {exc}") from None


def _decode_json_object(raw: Any, where: str) -> dict[str, Any]:
    if type(raw) is not str:
        raise ValidationError(f"{where}: stored JSON must be a string")
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValidationError(f"{where}: stored JSON is corrupted: {exc}") from None
    if not isinstance(decoded, dict):
        raise ValidationError(f"{where}: stored JSON must decode to an object")
    return decoded


def _parse_snapshot(raw: Any, learner_id: str) -> LearnerSnapshot:
    where = f"SqliteRepository: snapshot for learner {learner_id!r}"
    decoded = _decode_json_object(raw, where)
    try:
        return LearnerSnapshot.from_dict(decoded)
    except ValidationError as exc:
        raise ValidationError(f"{where}: invalid stored snapshot: {exc.message}") from None


def _parse_goal(raw: Any, goal_id: str) -> LearnerGoal:
    where = f"SqliteRepository: goal {goal_id!r}"
    decoded = _decode_json_object(raw, where)
    try:
        return LearnerGoal.from_dict(decoded)
    except ValidationError as exc:
        raise ValidationError(f"{where}: invalid stored goal: {exc.message}") from None


def _parse_session(raw: Any, session_id: str) -> SessionState:
    where = f"SqliteRepository: session {session_id!r}"
    decoded = _decode_json_object(raw, where)
    try:
        return SessionState.from_dict(decoded)
    except ValidationError as exc:
        raise ValidationError(f"{where}: invalid stored session: {exc.message}") from None


def _event_from_row(row: sqlite3.Row) -> HistoryEvent:
    event_id = row["event_id"]
    where = f"SqliteRepository: event {event_id!r}"
    payload = _decode_json_object(row["payload_json"], where)
    try:
        return HistoryEvent(
            event_id=event_id,
            learner_id=row["learner_id"],
            session_id=row["session_id"],
            seq=row["seq"],
            event_type=row["event_type"],
            payload=payload,
            created_at=row["created_at"],
        )
    except ValidationError as exc:
        raise ValidationError(f"{where}: invalid stored event: {exc.message}") from None


class SqliteRepository:
    """Stdlib SQLite implementation of learner + session persistence."""

    def __init__(
        self,
        db_path: str | Path,
        *,
        initialize: bool = True,
        busy_timeout_ms: int = _DEFAULT_BUSY_TIMEOUT_MS,
    ) -> None:
        if type(busy_timeout_ms) is not int or busy_timeout_ms < 0:
            raise ValidationError(
                "SqliteRepository(busy_timeout_ms=...): expected an int >= 0"
            )
        self._busy_timeout_ms = busy_timeout_ms
        if isinstance(db_path, Path):
            candidate: str | Path = db_path
        elif isinstance(db_path, str):
            if not db_path.strip():
                raise ValidationError("SqliteRepository(db_path): must not be blank")
            candidate = db_path
        else:
            raise ValidationError("SqliteRepository(db_path): expected a str or pathlib.Path")

        if candidate == ":memory:":
            self._db_path: str | Path = ":memory:"
            target = ":memory:"
        else:
            path = Path(candidate).expanduser()
            if path.exists() and path.is_dir():
                raise ValidationError(
                    f"SqliteRepository(db_path): {path} is a directory, not a database file"
                )
            if not path.parent.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
            self._db_path = path
            target = str(path)

        try:
            self._conn: sqlite3.Connection = sqlite3.connect(
                target,
                isolation_level=None,
                timeout=max(0.1, float(busy_timeout_ms) / 1000.0),
            )
        except sqlite3.Error as exc:  # pragma: no cover - filesystem failure
            raise ValidationError(f"SqliteRepository(): cannot open database: {exc}") from exc
        self._conn.row_factory = sqlite3.Row
        self._closed = False
        self._configure_connection()
        if initialize:
            try:
                self.initialize_schema()
            except BaseException:
                self._conn.close()
                self._closed = True
                raise

    # -- lifecycle ------------------------------------------------------------

    def _configure_connection(self) -> None:
        if self._db_path != ":memory:":
            row = self._conn.execute("PRAGMA journal_mode=WAL").fetchone()
            mode = str(row[0]).lower() if row is not None else ""
            if mode != "wal":  # pragma: no cover - defensive (e.g. exotic filesystems)
                raise ValidationError(
                    f"SqliteRepository(): could not enable WAL journal mode (got {mode!r})"
                )
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute(f"PRAGMA busy_timeout={int(self._busy_timeout_ms)}")
        self._conn.execute("PRAGMA synchronous=NORMAL")

    def initialize_schema(self) -> None:
        """Create/migrate the schema (idempotent; version mismatch fails closed)."""

        with self._write_transaction() as conn:
            for statement in _TABLE_SQL:
                conn.execute(statement)
            row = conn.execute("SELECT version FROM schema_meta LIMIT 1").fetchone()
            if row is None:
                conn.execute("INSERT INTO schema_meta(version) VALUES (?)", (SCHEMA_VERSION,))
            else:
                found = row["version"]
                if type(found) is not int or found != SCHEMA_VERSION:
                    raise ValidationError(
                        "SqliteRepository(): unsupported on-disk schema version "
                        f"{found!r} (this build supports {SCHEMA_VERSION})"
                    )

    @property
    def db_path(self) -> str | Path:
        """Database target (``Path`` for files, ``":memory:"`` for memory DBs)."""

        return self._db_path

    @property
    def schema_version(self) -> int:
        """Schema version written by this build."""

        return SCHEMA_VERSION

    @property
    def closed(self) -> bool:
        """Whether :meth:`close` has been called."""

        return self._closed

    @staticmethod
    def session_version(state: SessionState) -> str:
        """Content digest CAS version of a :class:`SessionState` (see module docstring)."""

        return session_version(state)

    def close(self) -> None:
        """Close the SQLite connection (idempotent)."""

        if not self._closed:
            self._conn.close()
            self._closed = True

    def __enter__(self) -> "SqliteRepository":
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()

    def _ensure_open(self) -> None:
        if self._closed:
            raise ValidationError("SqliteRepository: operation on a closed repository")

    @contextmanager
    def _write_transaction(self) -> Iterator[sqlite3.Connection]:
        self._ensure_open()
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            yield self._conn
        except BaseException:
            self._conn.execute("ROLLBACK")
            raise
        else:
            self._conn.execute("COMMIT")

    # -- input normalisation (fail-closed re-validation) ----------------------

    @staticmethod
    def _validated_event(event: Any) -> HistoryEvent:
        if not isinstance(event, HistoryEvent):
            raise ValidationError(
                "SqliteRepository.append_event(): expected a HistoryEvent instance"
            )
        try:
            return HistoryEvent.from_dict(event.to_dict())
        except ValidationError as exc:
            raise ValidationError(
                f"SqliteRepository.append_event(): invalid event: {exc.message}"
            ) from None

    @staticmethod
    def _validated_snapshot(snapshot: Any) -> LearnerSnapshot:
        if not isinstance(snapshot, LearnerSnapshot):
            raise ValidationError(
                "SqliteRepository.upsert_snapshot(): expected a LearnerSnapshot instance"
            )
        try:
            return LearnerSnapshot.from_dict(snapshot.to_dict())
        except ValidationError as exc:
            raise ValidationError(
                f"SqliteRepository.upsert_snapshot(): invalid snapshot: {exc.message}"
            ) from None

    @staticmethod
    def _validated_goal(goal: Any) -> LearnerGoal:
        if not isinstance(goal, LearnerGoal):
            raise ValidationError(
                "SqliteRepository.upsert_goal(): expected a LearnerGoal instance"
            )
        try:
            return LearnerGoal.from_dict(goal.to_dict())
        except ValidationError as exc:
            raise ValidationError(
                f"SqliteRepository.upsert_goal(): invalid goal: {exc.message}"
            ) from None

    @staticmethod
    def _validated_session(state: Any) -> SessionState:
        if not isinstance(state, SessionState):
            raise ValidationError(
                "SqliteRepository.save_session(): expected a SessionState instance"
            )
        try:
            return SessionState.from_dict(state.to_dict())
        except ValidationError as exc:
            raise ValidationError(
                f"SqliteRepository.save_session(): invalid session: {exc.message}"
            ) from None

    # -- internal SQL helpers -------------------------------------------------

    @staticmethod
    def _ensure_learner_row(
        conn: sqlite3.Connection, learner_id: str, timestamp: str
    ) -> None:
        conn.execute(
            "INSERT INTO learners(learner_id, created_at, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(learner_id) DO NOTHING",
            (learner_id, timestamp, timestamp),
        )

    @staticmethod
    def _event_exists(conn: sqlite3.Connection, event_id: str) -> bool:
        row = conn.execute(
            "SELECT 1 FROM history_events WHERE event_id = ?", (event_id,)
        ).fetchone()
        return row is not None

    @staticmethod
    def _check_seq_conflict(
        conn: sqlite3.Connection,
        event: HistoryEvent,
        *,
        code: str = "CONFLICT",
    ) -> None:
        row = conn.execute(
            "SELECT event_id FROM history_events WHERE learner_id = ? AND seq = ?",
            (event.learner_id, event.seq),
        ).fetchone()
        if row is not None and row["event_id"] != event.event_id:
            raise ConflictError(
                f"SqliteRepository.append_event(): seq {event.seq} for learner "
                f"{event.learner_id!r} is already used by event {row['event_id']!r}",
                code=code,
                details={"learner_id": event.learner_id, "seq": event.seq},
            )

    @staticmethod
    def _insert_event(conn: sqlite3.Connection, event: HistoryEvent) -> None:
        conn.execute(
            "INSERT INTO history_events(event_id, learner_id, session_id, seq, "
            "event_type, payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                event.event_id,
                event.learner_id,
                event.session_id,
                event.seq,
                event.event_type,
                _json_dumps(event.payload, f"event {event.event_id!r} payload"),
                event.created_at,
            ),
        )

    @staticmethod
    def _upsert_snapshot_row(
        conn: sqlite3.Connection,
        snapshot: LearnerSnapshot,
        *,
        code: str = "CONFLICT",
        require_advance: bool = False,
    ) -> None:
        row = conn.execute(
            "SELECT revision FROM snapshots WHERE learner_id = ?",
            (snapshot.learner_id,),
        ).fetchone()
        stored_revision = None if row is None else int(row["revision"])
        stale = stored_revision is not None and stored_revision > snapshot.revision
        not_advancing = (
            require_advance
            and stored_revision is not None
            and stored_revision >= snapshot.revision
        )
        if stale or not_advancing:
            raise ConflictError(
                "SqliteRepository.upsert_snapshot(): stale snapshot revision "
                f"{snapshot.revision} for learner {snapshot.learner_id!r} "
                f"(stored revision is {stored_revision})",
                code=code,
                details={
                    "learner_id": snapshot.learner_id,
                    "revision": snapshot.revision,
                    "stored_revision": stored_revision,
                },
            )
        conn.execute(
            "INSERT INTO snapshots(learner_id, revision, updated_at, snapshot_json) "
            "VALUES (?, ?, ?, ?) ON CONFLICT(learner_id) DO UPDATE SET "
            "revision = excluded.revision, updated_at = excluded.updated_at, "
            "snapshot_json = excluded.snapshot_json",
            (
                snapshot.learner_id,
                snapshot.revision,
                snapshot.updated_at,
                snapshot.to_json(),
            ),
        )

    @staticmethod
    def _write_session_row(conn: sqlite3.Connection, state: SessionState) -> None:
        conn.execute(
            "INSERT INTO sessions(session_id, learner_id, state_json, updated_at) "
            "VALUES (?, ?, ?, ?) ON CONFLICT(session_id) DO UPDATE SET "
            "learner_id = excluded.learner_id, state_json = excluded.state_json, "
            "updated_at = excluded.updated_at",
            (state.session_id, state.learner_id, state.to_json(), state.updated_at),
        )

    @staticmethod
    def _write_goal_row(conn: sqlite3.Connection, goal: LearnerGoal) -> None:
        conn.execute(
            "INSERT INTO goals(goal_id, learner_id, objective_id, status, goal_json, "
            "created_at) VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(goal_id) DO UPDATE SET "
            "learner_id = excluded.learner_id, objective_id = excluded.objective_id, "
            "status = excluded.status, goal_json = excluded.goal_json, "
            "created_at = excluded.created_at",
            (
                goal.goal_id,
                goal.learner_id,
                goal.objective_id,
                goal.status,
                goal.to_json(),
                goal.created_at,
            ),
        )

    @staticmethod
    def _session_row(conn: sqlite3.Connection, session_id: str) -> SessionState | None:
        row = conn.execute(
            "SELECT state_json FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        if row is None:
            return None
        return _parse_session(row["state_json"], session_id)

    @staticmethod
    def _prepared_attempt_rows(
        conn: sqlite3.Connection, session_id: str
    ) -> list[dict[str, Any]]:
        rows = conn.execute(
            "SELECT event_id, seq, payload_json FROM history_events "
            "WHERE session_id = ? AND event_type = ? ORDER BY seq ASC",
            (session_id, _PREPARED_EVENT_TYPE),
        ).fetchall()
        attempts: list[dict[str, Any]] = []
        for row in rows:
            payload = _decode_json_object(
                row["payload_json"], f"prepared event {row['event_id']!r}"
            )
            attempts.append(
                {"event_id": row["event_id"], "seq": int(row["seq"]), "payload": payload}
            )
        return attempts

    @staticmethod
    def _terminal_result_ids(conn: sqlite3.Connection, session_id: str) -> set[str]:
        rows = conn.execute(
            "SELECT event_id, payload_json FROM history_events "
            "WHERE session_id = ? AND event_type IN ('ASSESSED', 'ERROR')",
            (session_id,),
        ).fetchall()
        result_ids: set[str] = set()
        for row in rows:
            payload = _decode_json_object(
                row["payload_json"], f"terminal event {row['event_id']!r}"
            )
            result_id = payload.get("result_id")
            if type(result_id) is str and result_id:
                result_ids.add(result_id)
        return result_ids

    @classmethod
    def _assert_no_unresolved_prepared(
        cls, conn: sqlite3.Connection, session_id: str
    ) -> None:
        """Invariant: a session without a pending item has no orphan PREPARED attempt."""

        prepared = cls._prepared_attempt_rows(conn, session_id)
        if not prepared:
            return
        terminal_ids = cls._terminal_result_ids(conn, session_id)
        for attempt in prepared:
            payload = attempt["payload"]
            result_id = payload.get("result_id")
            if type(result_id) is not str or result_id not in terminal_ids:
                raise ValidationError(
                    "SqliteRepository.commit_teaching_turn(): refusing to leave a "
                    "session without a pending item while attempt "
                    f"{payload.get('attempt_id')!r} (result {result_id!r}) has no "
                    "terminal ASSESSED/ERROR event; this state is not recoverable",
                    code="INCONSISTENT_PENDING",
                    details={
                        "session_id": session_id,
                        "attempt_id": payload.get("attempt_id"),
                        "result_id": result_id,
                    },
                )

    @staticmethod
    def _validate_turn_transition(
        current: SessionState,
        next_session: SessionState,
        events: Sequence[HistoryEvent],
    ) -> None:
        def _fail(message: str) -> None:
            raise ValidationError(
                f"SqliteRepository.commit_teaching_turn(): {message}",
                code="INVALID_SESSION_TRANSITION",
                details={
                    "session_id": next_session.session_id,
                    "current_turn_index": current.turn_index,
                    "next_turn_index": next_session.turn_index,
                },
            )

        if next_session.goal_id != current.goal_id:
            _fail("goal_id must not change within a session")
        if next_session.objective_id != current.objective_id:
            _fail("objective_id must not change within a session")
        if next_session.turn_index < current.turn_index:
            _fail("turn_index must be monotonic non-decreasing")
        has_prepared = any(event.event_type == _PREPARED_EVENT_TYPE for event in events)
        has_terminal = any(event.event_type in _TERMINAL_EVENT_TYPES for event in events)
        if has_prepared and has_terminal:
            _fail("PREPARED and terminal events must not share one commit")
        if has_prepared:
            if next_session.turn_index != current.turn_index:
                _fail("a PREPARED attempt must not advance turn_index")
            if next_session.pending_item_id != current.pending_item_id:
                _fail("a PREPARED attempt must not change the pending item")
            if next_session.phase != current.phase:
                _fail("a PREPARED attempt must not change the session phase")
        elif has_terminal:
            if next_session.turn_index != current.turn_index + 1:
                _fail("a terminal turn commit must advance turn_index by exactly one")
        elif next_session.turn_index > current.turn_index + 1:
            _fail("a session write may advance turn_index by at most one")
        if next_session.pending_item_id is not None and next_session.phase == "COMPLETE":
            _fail("a COMPLETE session cannot keep a pending item")

    # -- B-NEXT: transactional teaching-turn commit ---------------------------

    def commit_teaching_turn(
        self,
        *,
        learner_id: str,
        session_id: str,
        expected_session_version: str,
        events: Sequence[HistoryEvent],
        snapshot: LearnerSnapshot | None = None,
        next_session: SessionState,
        goal: LearnerGoal | None = None,
    ) -> list[bool]:
        """Atomically commit one teaching turn (events + snapshot + goal + session).

        See the module docstring for the ordering, the compare-and-swap session
        version, the fail-closed error codes and the real-process crash
        failpoints.  Returns one ``True`` flag per inserted event (duplicates and
        conflicts are errors here, not silent ``False`` results, so an engine can
        never mistake a lost turn for success).
        """

        learner_id = _require_nonempty_str(
            learner_id, "SqliteRepository.commit_teaching_turn(learner_id)"
        )
        session_id = _require_nonempty_str(
            session_id, "SqliteRepository.commit_teaching_turn(session_id)"
        )
        expected_session_version = _require_nonempty_str(
            expected_session_version,
            "SqliteRepository.commit_teaching_turn(expected_session_version)",
        )
        if isinstance(events, (str, bytes)) or not isinstance(events, Sequence):
            raise ValidationError(
                "SqliteRepository.commit_teaching_turn(events=...): expected a sequence "
                "of HistoryEvent instances"
            )
        normalized_events: list[HistoryEvent] = []
        seen_event_ids: set[str] = set()
        last_seq = -1
        for index, event in enumerate(events):
            event = self._validated_event(event)
            where = f"SqliteRepository.commit_teaching_turn(events[{index}])"
            if event.learner_id != learner_id:
                raise ValidationError(f"{where}: event belongs to another learner")
            if event.session_id != session_id:
                raise ValidationError(f"{where}: event belongs to another session")
            if event.event_id in seen_event_ids:
                raise ValidationError(f"{where}: duplicate event_id {event.event_id!r} in request")
            seen_event_ids.add(event.event_id)
            if event.seq <= last_seq:
                raise ValidationError(
                    f"{where}: event seq values must be strictly ascending "
                    f"({event.seq} after {last_seq})"
                )
            last_seq = event.seq
            normalized_events.append(event)
        next_session = self._validated_session(next_session)
        if next_session.session_id != session_id:
            raise ValidationError(
                "SqliteRepository.commit_teaching_turn(): next_session.session_id "
                f"{next_session.session_id!r} does not match {session_id!r}"
            )
        if next_session.learner_id != learner_id:
            raise ValidationError(
                "SqliteRepository.commit_teaching_turn(): next_session.learner_id "
                f"{next_session.learner_id!r} does not match {learner_id!r}"
            )
        if snapshot is not None:
            snapshot = self._validated_snapshot(snapshot)
            if snapshot.learner_id != learner_id:
                raise ValidationError(
                    "SqliteRepository.commit_teaching_turn(): snapshot.learner_id "
                    f"{snapshot.learner_id!r} does not match {learner_id!r}"
                )
        if goal is not None:
            goal = self._validated_goal(goal)
            if goal.learner_id != learner_id:
                raise ValidationError(
                    "SqliteRepository.commit_teaching_turn(): goal.learner_id "
                    f"{goal.learner_id!r} does not match {learner_id!r}"
                )
            if goal.goal_id != next_session.goal_id:
                raise ValidationError(
                    "SqliteRepository.commit_teaching_turn(): goal.goal_id "
                    f"{goal.goal_id!r} does not match the session goal "
                    f"{next_session.goal_id!r}"
                )
        scope = (
            "prepare"
            if any(event.event_type == _PREPARED_EVENT_TYPE for event in normalized_events)
            else "commit"
        )
        self._ensure_open()
        try:
            self._conn.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError as exc:
            raise ConflictError(
                "SqliteRepository.commit_teaching_turn(): cannot acquire the SQLite "
                f"write lock: {exc}",
                code="DB_BUSY",
            ) from None
        try:
            conn = self._conn
            _crash_failpoint("after_begin", scope)
            current = self._session_row(conn, session_id)
            if current is None:
                raise NotFoundError(
                    f"SqliteRepository.commit_teaching_turn(): unknown session_id "
                    f"{session_id!r}"
                )
            if current.learner_id != learner_id:
                raise ConflictError(
                    "SqliteRepository.commit_teaching_turn(): session belongs to "
                    f"learner {current.learner_id!r}, not {learner_id!r}",
                    code="SESSION_OWNER_CONFLICT",
                )
            current_version = session_version(current)
            if current_version != expected_session_version:
                raise ConflictError(
                    "SqliteRepository.commit_teaching_turn(): stale session version "
                    f"for {session_id!r} (expected {expected_session_version!r}, "
                    f"stored {current_version!r}); another writer advanced the session",
                    code="SESSION_VERSION_CONFLICT",
                    details={
                        "session_id": session_id,
                        "expected_session_version": expected_session_version,
                        "current_session_version": current_version,
                    },
                )
            _crash_failpoint("after_session_check", scope)
            self._validate_turn_transition(current, next_session, normalized_events)
            for index, event in enumerate(normalized_events, start=1):
                _crash_failpoint(f"before_event_insert_{index}", scope)
                if self._event_exists(conn, event.event_id):
                    raise ConflictError(
                        "SqliteRepository.commit_teaching_turn(): duplicate event_id "
                        f"{event.event_id!r}",
                        code="DUPLICATE_EVENT",
                        details={"event_id": event.event_id},
                    )
                self._check_seq_conflict(conn, event, code="EVENT_SEQ_CONFLICT")
                self._ensure_learner_row(conn, learner_id, event.created_at)
                self._insert_event(conn, event)
                _crash_failpoint(f"after_event_insert_{index}", scope)
            if snapshot is not None:
                _crash_failpoint("before_snapshot", scope)
                # A teaching turn must strictly advance the materialised
                # snapshot revision: a stale caller snapshot (loaded before a
                # concurrent turn of the same learner) fails closed instead of
                # silently overwriting newer evidence.
                self._upsert_snapshot_row(
                    conn,
                    snapshot,
                    code="SNAPSHOT_REVISION_CONFLICT",
                    require_advance=True,
                )
                _crash_failpoint("after_snapshot", scope)
            if goal is not None:
                _crash_failpoint("before_goal", scope)
                self._write_goal_row(conn, goal)
                _crash_failpoint("after_goal", scope)
            _crash_failpoint("before_session", scope)
            self._write_session_row(conn, next_session)
            _crash_failpoint("after_session", scope)
            if next_session.pending_item_id is None:
                self._assert_no_unresolved_prepared(conn, session_id)
            _crash_failpoint("before_commit", scope)
            conn.execute("COMMIT")
        except BaseException:
            try:
                self._conn.execute("ROLLBACK")
            except sqlite3.Error:  # pragma: no cover - transaction already gone
                pass
            raise
        _crash_failpoint("after_commit", scope)
        return [True] * len(normalized_events)

    # -- LearnerRepository: snapshots ----------------------------------------

    def get_snapshot(self, learner_id: str) -> LearnerSnapshot | None:
        """Return the stored snapshot, ``None`` if the learner has none."""

        learner_id = _require_nonempty_str(learner_id, "SqliteRepository.get_snapshot()")
        self._ensure_open()
        row = self._conn.execute(
            "SELECT snapshot_json FROM snapshots WHERE learner_id = ?", (learner_id,)
        ).fetchone()
        if row is None:
            return None
        return _parse_snapshot(row["snapshot_json"], learner_id)

    def upsert_snapshot(self, snapshot: LearnerSnapshot) -> None:
        """Insert/replace a snapshot; requires a registered learner row."""

        snapshot = self._validated_snapshot(snapshot)
        with self._write_transaction() as conn:
            known = conn.execute(
                "SELECT 1 FROM learners WHERE learner_id = ?", (snapshot.learner_id,)
            ).fetchone()
            if known is None:
                raise ValidationError(
                    "SqliteRepository.upsert_snapshot(): unknown learner "
                    f"{snapshot.learner_id!r}; append an event or call ensure_learner() first"
                )
            self._upsert_snapshot_row(conn, snapshot)

    # -- LearnerRepository: events -------------------------------------------

    def append_event(self, event: HistoryEvent) -> bool:
        """Append one event; ``False`` for a duplicate ``event_id``."""

        event = self._validated_event(event)
        with self._write_transaction() as conn:
            if self._event_exists(conn, event.event_id):
                return False
            self._check_seq_conflict(conn, event)
            self._ensure_learner_row(conn, event.learner_id, event.created_at)
            self._insert_event(conn, event)
        return True

    def append_events(self, events: Sequence[HistoryEvent]) -> list[bool]:
        """Atomically append a batch of events; returns one flag per event."""

        normalized = self._validated_event_batch(events, "append_events")
        if not normalized:
            return []
        flags: list[bool] = []
        with self._write_transaction() as conn:
            for event in normalized:
                if self._event_exists(conn, event.event_id):
                    flags.append(False)
                    continue
                self._check_seq_conflict(conn, event)
                self._ensure_learner_row(conn, event.learner_id, event.created_at)
                self._insert_event(conn, event)
                flags.append(True)
            return flags

    def append_event_and_upsert_snapshot(
        self, event: HistoryEvent, snapshot: LearnerSnapshot
    ) -> bool:
        """Atomically append one event and upsert the snapshot; returns the flag."""

        return self.append_events_and_upsert_snapshot([event], snapshot)[0]

    def append_events_and_upsert_snapshot(
        self, events: Sequence[HistoryEvent], snapshot: LearnerSnapshot
    ) -> list[bool]:
        """Atomically append events and upsert the snapshot in one transaction.

        The snapshot upsert happens even when every event is a duplicate, which
        makes a retry self-healing after a non-atomic-writing crash.  Any
        validation/conflict error rolls the whole transaction back.
        """

        normalized = self._validated_event_batch(events, "append_events_and_upsert_snapshot")
        if not normalized:
            raise ValidationError(
                "SqliteRepository.append_events_and_upsert_snapshot(): events must not be empty"
            )
        snapshot = self._validated_snapshot(snapshot)
        learner_ids = {event.learner_id for event in normalized}
        if learner_ids != {snapshot.learner_id}:
            raise ValidationError(
                "SqliteRepository.append_events_and_upsert_snapshot(): every event and the "
                f"snapshot must belong to the same learner, got events {sorted(learner_ids)} "
                f"and snapshot {snapshot.learner_id!r}"
            )
        flags: list[bool] = []
        with self._write_transaction() as conn:
            for event in normalized:
                if self._event_exists(conn, event.event_id):
                    flags.append(False)
                    continue
                self._check_seq_conflict(conn, event)
                self._ensure_learner_row(conn, event.learner_id, event.created_at)
                self._insert_event(conn, event)
                flags.append(True)
            self._upsert_snapshot_row(conn, snapshot)
        return flags

    def get_event(self, event_id: str) -> HistoryEvent | None:
        """Return one event by idempotency key, ``None`` if unknown."""

        event_id = _require_nonempty_str(event_id, "SqliteRepository.get_event()")
        self._ensure_open()
        row = self._conn.execute(
            "SELECT event_id, learner_id, session_id, seq, event_type, payload_json, "
            "created_at FROM history_events WHERE event_id = ?",
            (event_id,),
        ).fetchone()
        if row is None:
            return None
        return _event_from_row(row)

    def list_events(
        self, learner_id: str, since_seq: int | None = None
    ) -> list[HistoryEvent]:
        """Return a learner's events in ascending ``seq`` order.

        ``since_seq`` is an **inclusive** lower bound (protocol contract).
        Unknown learners simply have no events (empty list).
        """

        learner_id = _require_nonempty_str(learner_id, "SqliteRepository.list_events()")
        if since_seq is not None:
            since_seq = _require_int(
                since_seq, "SqliteRepository.list_events(since_seq=...)", minimum=0
            )
        self._ensure_open()
        if since_seq is None:
            rows = self._conn.execute(
                "SELECT event_id, learner_id, session_id, seq, event_type, payload_json, "
                "created_at FROM history_events WHERE learner_id = ? ORDER BY seq ASC",
                (learner_id,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT event_id, learner_id, session_id, seq, event_type, payload_json, "
                "created_at FROM history_events WHERE learner_id = ? AND seq >= ? "
                "ORDER BY seq ASC",
                (learner_id, since_seq),
            ).fetchall()
        return [_event_from_row(row) for row in rows]

    # -- LearnerRepository: goals --------------------------------------------

    def get_goal(self, goal_id: str) -> LearnerGoal | None:
        """Return one goal by id, ``None`` if unknown."""

        goal_id = _require_nonempty_str(goal_id, "SqliteRepository.get_goal()")
        self._ensure_open()
        row = self._conn.execute(
            "SELECT goal_json FROM goals WHERE goal_id = ?", (goal_id,)
        ).fetchone()
        if row is None:
            return None
        return _parse_goal(row["goal_json"], goal_id)

    def upsert_goal(self, goal: LearnerGoal) -> None:
        """Insert/replace a learner goal (auto-registers a new learner row)."""

        goal = self._validated_goal(goal)
        with self._write_transaction() as conn:
            self._ensure_learner_row(conn, goal.learner_id, goal.created_at)
            self._write_goal_row(conn, goal)

    # -- SessionRepository ----------------------------------------------------

    def save_session(self, state: SessionState) -> None:
        """Insert/replace a session state (auto-registers a new learner row)."""

        state = self._validated_session(state)
        with self._write_transaction() as conn:
            self._ensure_learner_row(conn, state.learner_id, state.updated_at)
            self._write_session_row(conn, state)

    def load_session(self, session_id: str) -> SessionState | None:
        """Return a session state by id, ``None`` if unknown."""

        session_id = _require_nonempty_str(session_id, "SqliteRepository.load_session()")
        self._ensure_open()
        row = self._conn.execute(
            "SELECT state_json FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        if row is None:
            return None
        return _parse_session(row["state_json"], session_id)

    def list_sessions(self, learner_id: str) -> list[SessionState]:
        """Return a learner's sessions, newest ``updated_at`` first (stable tie-break)."""

        learner_id = _require_nonempty_str(learner_id, "SqliteRepository.list_sessions()")
        self._ensure_open()
        rows = self._conn.execute(
            "SELECT session_id, state_json FROM sessions WHERE learner_id = ? "
            "ORDER BY updated_at DESC, session_id ASC",
            (learner_id,),
        ).fetchall()
        return [_parse_session(row["state_json"], row["session_id"]) for row in rows]

    # -- additive extensions --------------------------------------------------

    def ensure_learner(self, learner_id: str, *, created_at: str | None = None) -> None:
        """Register a learner row if it does not exist (idempotent)."""

        learner_id = _require_nonempty_str(
            learner_id, "SqliteRepository.ensure_learner()"
        )
        timestamp = now_utc() if created_at is None else _require_timestamp(
            created_at, "SqliteRepository.ensure_learner(created_at=...)"
        )
        with self._write_transaction() as conn:
            self._ensure_learner_row(conn, learner_id, timestamp)

    def list_learners(self) -> list[str]:
        """All registered learner ids in deterministic (sorted) order."""

        self._ensure_open()
        rows = self._conn.execute(
            "SELECT learner_id FROM learners ORDER BY learner_id ASC"
        ).fetchall()
        return [row["learner_id"] for row in rows]

    @staticmethod
    def _validated_event_batch(
        events: Any, method: str
    ) -> list[HistoryEvent]:
        if isinstance(events, (str, bytes)) or not isinstance(events, Sequence):
            raise ValidationError(
                f"SqliteRepository.{method}(): expected a sequence of HistoryEvent instances"
            )
        normalized: list[HistoryEvent] = []
        for index, event in enumerate(events):
            if not isinstance(event, HistoryEvent):
                raise ValidationError(
                    f"SqliteRepository.{method}(): events[{index}] must be a HistoryEvent"
                )
            normalized.append(SqliteRepository._validated_event(event))
        return normalized
