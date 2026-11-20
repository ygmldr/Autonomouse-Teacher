"""Tests for the stdlib SQLite persistence layer (B-PR2).

Covers schema creation/WAL/foreign keys, restart recovery, event idempotency and
``(learner_id, seq)`` uniqueness, optimistic snapshot revisions, atomic
event+snapshot commits with rollback, session/goal persistence, corrupted-JSON
fail-closed behaviour and unsupported-schema rejection.  All databases live in
``tmp_path`` (or ``:memory:``); no fixture data and no network are involved.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from m1_teacher.contracts.errors import ConflictError, ValidationError
from m1_teacher.contracts.repository import LearnerRepository, SessionRepository
from m1_teacher.contracts.types import (
    HistoryEvent,
    LearnerGoal,
    LearnerSnapshot,
    MasteryEstimate,
    SessionState,
)
from m1_teacher.learner.repository import SCHEMA_VERSION, SqliteRepository

TS = "2026-11-20T12:00:00Z"
TS2 = "2026-11-20T12:05:00Z"
TS3 = "2026-11-20T12:10:00Z"
LEARNER = "learner.a"
SESSION = "session.1"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_event(
    event_id: str,
    seq: int,
    *,
    learner_id: str = LEARNER,
    session_id: str = SESSION,
    event_type: str = "SESSION_STARTED",
    payload: dict | None = None,
    created_at: str = TS,
) -> HistoryEvent:
    return HistoryEvent(
        event_id=event_id,
        learner_id=learner_id,
        session_id=session_id,
        seq=seq,
        event_type=event_type,
        payload=payload if payload is not None else {"n": seq},
        created_at=created_at,
    )


def make_snapshot(
    revision: int = 1,
    *,
    learner_id: str = LEARNER,
    value: float = 0.5,
    created_at: str = TS,
    updated_at: str = TS2,
) -> LearnerSnapshot:
    return LearnerSnapshot(
        learner_id=learner_id,
        masteries={
            "cf.search.binary": MasteryEstimate(
                node_id="cf.search.binary",
                value=value,
                confidence=0.75,
                evidence_count=2,
                created_at=created_at,
                updated_at=updated_at,
            )
        },
        completed_item_ids=["item.bs.mcq.004"],
        error_counts={"off_by_one": 1},
        revision=revision,
        created_at=created_at,
        updated_at=updated_at,
    )


def make_session(
    session_id: str = SESSION,
    *,
    learner_id: str = LEARNER,
    phase: str = "PAUSED",
    turn_index: int = 0,
    updated_at: str = TS,
) -> SessionState:
    return SessionState(
        session_id=session_id,
        learner_id=learner_id,
        goal_id="goal.1",
        objective_id="obj.cf.binary_search.mastery",
        phase=phase,
        turn_index=turn_index,
        updated_at=updated_at,
    )


def make_goal(
    goal_id: str = "goal.1",
    *,
    learner_id: str = LEARNER,
    status: str = "ACTIVE",
) -> LearnerGoal:
    return LearnerGoal(
        goal_id=goal_id,
        learner_id=learner_id,
        objective_id="obj.cf.binary_search.mastery",
        status=status,
    )


def table_names(repository: SqliteRepository) -> set[str]:
    rows = repository._conn.execute(  # noqa: SLF001 - white-box schema assertion
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    ).fetchall()
    return {row["name"] for row in rows}


@pytest.fixture()
def repository(tmp_path: Path):
    repo = SqliteRepository(tmp_path / "m1.db")
    try:
        yield repo
    finally:
        repo.close()


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "m1.db"


# ---------------------------------------------------------------------------
# Schema, pragmas and lifecycle
# ---------------------------------------------------------------------------


def test_creates_schema_version_and_enables_wal_and_foreign_keys(repository: SqliteRepository, db_path: Path):
    assert db_path.is_file()
    assert {"schema_meta", "learners", "snapshots", "history_events", "goals", "sessions"} <= (
        table_names(repository)
    )
    version_rows = repository._conn.execute(  # noqa: SLF001 - white-box schema assertion
        "SELECT version FROM schema_meta"
    ).fetchall()
    assert [int(row["version"]) for row in version_rows] == [SCHEMA_VERSION]
    journal_mode = repository._conn.execute(  # noqa: SLF001
        "PRAGMA journal_mode"
    ).fetchone()
    assert str(journal_mode[0]).lower() == "wal"
    foreign_keys = repository._conn.execute(  # noqa: SLF001
        "PRAGMA foreign_keys"
    ).fetchone()
    assert int(foreign_keys[0]) == 1


def test_reopening_keeps_single_schema_version_row(db_path: Path):
    first = SqliteRepository(db_path)
    first.close()
    second = SqliteRepository(db_path)
    try:
        rows = second._conn.execute("SELECT version FROM schema_meta").fetchall()  # noqa: SLF001
        assert [int(row["version"]) for row in rows] == [SCHEMA_VERSION]
        assert second.schema_version == SCHEMA_VERSION
    finally:
        second.close()


def test_unsupported_on_disk_schema_version_fails_closed(db_path: Path):
    connection = sqlite3.connect(str(db_path))
    try:
        connection.execute("CREATE TABLE schema_meta (version INTEGER NOT NULL)")
        connection.execute("INSERT INTO schema_meta(version) VALUES (99)")
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(ValidationError):
        SqliteRepository(db_path)


def test_in_memory_database_supported():
    repository = SqliteRepository(":memory:")
    try:
        assert repository.append_event(make_event("evt.a.0", 0)) is True
        assert repository.get_event("evt.a.0") is not None
    finally:
        repository.close()


def test_close_is_idempotent_and_closed_repo_fails_closed(repository: SqliteRepository):
    repository.close()
    repository.close()
    assert repository.closed is True
    with pytest.raises(ValidationError):
        repository.get_snapshot(LEARNER)
    with pytest.raises(ValidationError):
        repository.append_event(make_event("evt.a.0", 0))


def test_context_manager_closes_repository(db_path: Path):
    with SqliteRepository(db_path) as repository:
        repository.ensure_learner(LEARNER)
    assert repository.closed is True


def test_repository_implements_frozen_protocols(repository: SqliteRepository):
    assert isinstance(repository, LearnerRepository)
    assert isinstance(repository, SessionRepository)


# ---------------------------------------------------------------------------
# Restart recovery: snapshots, events, sessions, goals
# ---------------------------------------------------------------------------


def test_snapshot_and_events_survive_reopen(db_path: Path):
    repository = SqliteRepository(db_path)
    repository.ensure_learner(LEARNER, created_at=TS)
    snapshot = make_snapshot(revision=3)
    repository.upsert_snapshot(snapshot)
    assert repository.append_event(make_event("evt.a.0", 0, payload={"phase": "DIAGNOSE"})) is True
    assert repository.append_event(make_event("evt.a.1", 1, payload={"phase": "TEACH"})) is True
    repository.close()

    reopened = SqliteRepository(db_path)
    try:
        restored = reopened.get_snapshot(LEARNER)
        assert restored is not None
        assert restored.to_dict() == snapshot.to_dict()
        events = reopened.list_events(LEARNER)
        assert [event.to_dict() for event in events] == [
            make_event("evt.a.0", 0, payload={"phase": "DIAGNOSE"}).to_dict(),
            make_event("evt.a.1", 1, payload={"phase": "TEACH"}).to_dict(),
        ]
        assert reopened.get_event("evt.a.0").to_dict() == events[0].to_dict()
        assert reopened.list_learners() == [LEARNER]
    finally:
        reopened.close()


def test_session_roundtrip_and_newest_first_ordering(db_path: Path):
    repository = SqliteRepository(db_path)
    repository.save_session(make_session("session.old", updated_at=TS))
    repository.save_session(make_session("session.new", updated_at=TS3, phase="TEACH"))
    repository.save_session(make_session("session.tie", updated_at=TS3, phase="PRACTICE"))
    loaded = repository.load_session("session.new")
    assert loaded is not None
    assert loaded.phase == "TEACH"
    sessions = repository.list_sessions(LEARNER)
    assert [session.session_id for session in sessions] == [
        "session.new",
        "session.tie",
        "session.old",
    ]
    # Overwrite a session (same id) and reload.
    repository.save_session(make_session("session.new", updated_at=TS2, phase="REVIEW"))
    reloaded = repository.load_session("session.new")
    assert reloaded is not None
    assert reloaded.phase == "REVIEW"
    repository.close()

    reopened = SqliteRepository(db_path)
    try:
        assert reopened.load_session("session.new").phase == "REVIEW"
        assert reopened.load_session("unknown.session") is None
        assert reopened.list_sessions("unknown.learner") == []
    finally:
        reopened.close()


def test_goal_roundtrip_and_update(db_path: Path):
    repository = SqliteRepository(db_path)
    goal = make_goal()
    repository.upsert_goal(goal)
    stored = repository.get_goal(goal.goal_id)
    assert stored is not None
    assert stored.to_dict() == goal.to_dict()
    repository.upsert_goal(make_goal(status="COMPLETED"))
    updated = repository.get_goal(goal.goal_id)
    assert updated is not None
    assert updated.status == "COMPLETED"
    assert repository.get_goal("unknown.goal") is None
    repository.close()

    reopened = SqliteRepository(db_path)
    try:
        assert reopened.get_goal(goal.goal_id).status == "COMPLETED"
    finally:
        reopened.close()


# ---------------------------------------------------------------------------
# Event idempotency, sequence uniqueness and ordering
# ---------------------------------------------------------------------------


def test_duplicate_event_id_is_idempotent(repository: SqliteRepository):
    first = make_event("evt.a.0", 0, payload={"phase": "DIAGNOSE"})
    assert repository.append_event(first) is True
    duplicate = make_event("evt.a.0", 0, payload={"phase": "TAMPERED"})
    assert repository.append_event(duplicate) is False
    assert len(repository.list_events(LEARNER)) == 1
    stored = repository.get_event("evt.a.0")
    assert stored is not None
    assert stored.payload == {"phase": "DIAGNOSE"}


def test_seq_conflict_raises_conflict_error(repository: SqliteRepository):
    assert repository.append_event(make_event("evt.a.0", 0)) is True
    with pytest.raises(ConflictError):
        repository.append_event(make_event("evt.a.other", 0))
    assert len(repository.list_events(LEARNER)) == 1


def test_events_are_listed_by_ascending_seq_with_since_seq(repository: SqliteRepository):
    # Deliberately insert out of order: seq uniqueness only (single-writer seq
    # allocation is the history layer's job).
    for seq in (2, 0, 1):
        assert repository.append_event(make_event(f"evt.a.{seq}", seq)) is True
    assert [event.seq for event in repository.list_events(LEARNER)] == [0, 1, 2]
    assert [event.seq for event in repository.list_events(LEARNER, since_seq=1)] == [1, 2]
    assert [event.seq for event in repository.list_events(LEARNER, since_seq=0)] == [0, 1, 2]
    assert repository.list_events(LEARNER, since_seq=3) == []
    with pytest.raises(ValidationError):
        repository.list_events(LEARNER, since_seq=-1)
    with pytest.raises(ValidationError):
        repository.list_events(LEARNER, since_seq="1")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        repository.list_events(LEARNER, since_seq=True)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Input validation (fail-closed)
# ---------------------------------------------------------------------------


def test_invalid_event_inputs_fail_closed(repository: SqliteRepository):
    with pytest.raises(ValidationError):
        repository.append_event({"event_id": "nope"})  # type: ignore[arg-type]

    blank_id = make_event("evt.blank", 0)
    blank_id.event_id = ""
    with pytest.raises(ValidationError):
        repository.append_event(blank_id)

    negative_seq = make_event("evt.neg", 5)
    negative_seq.seq = -1
    with pytest.raises(ValidationError):
        repository.append_event(negative_seq)

    bad_payload = make_event("evt.bad", 0)
    bad_payload.payload = {"not": object()}
    with pytest.raises(ValidationError):
        repository.append_event(bad_payload)

    assert repository.list_events(LEARNER) == []


def test_invalid_ids_and_lookups_fail_closed(repository: SqliteRepository):
    for call in (
        lambda: repository.get_snapshot(""),
        lambda: repository.get_event("   "),
        lambda: repository.list_events(""),
        lambda: repository.get_goal(""),
        lambda: repository.load_session(""),
        lambda: repository.list_sessions(""),
        lambda: repository.ensure_learner(""),
    ):
        with pytest.raises(ValidationError):
            call()
    with pytest.raises(ValidationError):
        repository.upsert_goal({"goal_id": "x"})  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        repository.save_session({"session_id": "x"})  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        repository.upsert_snapshot({"learner_id": LEARNER})  # type: ignore[arg-type]


def test_unknown_learner_has_no_state(repository: SqliteRepository):
    assert repository.get_snapshot("learner.unknown") is None
    assert repository.get_event("evt.unknown") is None
    assert repository.list_events("learner.unknown") == []
    assert repository.get_goal("goal.unknown") is None
    assert repository.load_session("session.unknown") is None
    assert repository.list_sessions("learner.unknown") == []
    assert repository.list_learners() == []


def test_upsert_snapshot_requires_registered_learner(repository: SqliteRepository):
    with pytest.raises(ValidationError):
        repository.upsert_snapshot(make_snapshot())
    repository.ensure_learner(LEARNER, created_at=TS)
    repository.upsert_snapshot(make_snapshot())
    assert repository.get_snapshot(LEARNER) is not None


def test_ensure_learner_is_idempotent_and_listed_sorted(repository: SqliteRepository):
    repository.ensure_learner(LEARNER, created_at=TS)
    repository.ensure_learner(LEARNER, created_at=TS2)
    repository.ensure_learner("learner.b", created_at=TS)
    assert repository.list_learners() == ["learner.a", "learner.b"]
    with pytest.raises(ValidationError):
        repository.ensure_learner(LEARNER, created_at="not-a-timestamp")


def test_snapshot_optimistic_revision_guard(repository: SqliteRepository):
    repository.ensure_learner(LEARNER, created_at=TS)
    repository.upsert_snapshot(make_snapshot(revision=2))
    with pytest.raises(ConflictError):
        repository.upsert_snapshot(make_snapshot(revision=1))
    # Equal revision is an idempotent rewrite; newer is accepted.
    repository.upsert_snapshot(make_snapshot(revision=2, value=0.6))
    stored = repository.get_snapshot(LEARNER)
    assert stored.masteries["cf.search.binary"].value == pytest.approx(0.6)
    repository.upsert_snapshot(make_snapshot(revision=3, value=0.7))
    stored = repository.get_snapshot(LEARNER)
    assert stored.revision == 3
    assert stored.masteries["cf.search.binary"].value == pytest.approx(0.7)


# ---------------------------------------------------------------------------
# Atomic event + snapshot extension
# ---------------------------------------------------------------------------


def test_append_event_and_upsert_snapshot_is_atomic(repository: SqliteRepository):
    event = make_event("evt.a.0", 0)
    snapshot = make_snapshot(revision=1)
    assert repository.append_event_and_upsert_snapshot(event, snapshot) is True
    assert repository.get_event("evt.a.0") is not None
    stored = repository.get_snapshot(LEARNER)
    assert stored is not None
    assert stored.to_dict() == snapshot.to_dict()
    # Retrying the duplicate event still self-heals the snapshot revision.
    newer = make_snapshot(revision=2, value=0.9)
    assert repository.append_event_and_upsert_snapshot(event, newer) is False
    assert len(repository.list_events(LEARNER)) == 1
    healed = repository.get_snapshot(LEARNER)
    assert healed is not None
    assert healed.revision == 2
    assert healed.masteries["cf.search.binary"].value == pytest.approx(0.9)


def test_append_events_batch_and_duplicates(repository: SqliteRepository):
    events = [make_event("evt.a.0", 0), make_event("evt.a.1", 1, event_type="ACTION_TAKEN")]
    assert repository.append_events(events) == [True, True]
    assert repository.append_events(events) == [False, False]
    assert repository.append_events([]) == []
    assert [event.seq for event in repository.list_events(LEARNER)] == [0, 1]
    # Duplicate inside the same batch: first wins, second is reported idempotent.
    assert repository.append_events(
        [make_event("evt.a.2", 2), make_event("evt.a.2", 2)]
    ) == [True, False]


def test_atomic_batch_rolls_back_on_conflict(repository: SqliteRepository):
    repository.append_event(make_event("evt.a.0", 0))
    conflicting = make_event("evt.a.conflict", 0)
    fresh = make_event("evt.a.1", 1)
    with pytest.raises(ConflictError):
        repository.append_events_and_upsert_snapshot(
            [fresh, conflicting], make_snapshot(revision=1)
        )
    # The whole transaction rolled back: no seq 1 event and no snapshot.
    assert [event.seq for event in repository.list_events(LEARNER)] == [0]
    assert repository.get_snapshot(LEARNER) is None


def test_atomic_batch_fails_closed_on_mismatched_learners(repository: SqliteRepository):
    with pytest.raises(ValidationError):
        repository.append_events_and_upsert_snapshot(
            [make_event("evt.a.0", 0, learner_id="learner.a")],
            make_snapshot(revision=1, learner_id="learner.b"),
        )
    with pytest.raises(ValidationError):
        repository.append_events_and_upsert_snapshot([], make_snapshot(revision=1))


# ---------------------------------------------------------------------------
# Corrupted persisted JSON fails closed
# ---------------------------------------------------------------------------


def test_corrupted_persisted_json_fails_closed(db_path: Path):
    repository = SqliteRepository(db_path)
    repository.ensure_learner(LEARNER, created_at=TS)
    repository.upsert_snapshot(make_snapshot(revision=1))
    repository.append_event(make_event("evt.a.0", 0))
    repository.save_session(make_session())
    repository.upsert_goal(make_goal())
    repository.close()

    connection = sqlite3.connect(str(db_path))
    try:
        connection.execute("UPDATE snapshots SET snapshot_json = '{broken'")
        connection.execute("UPDATE history_events SET payload_json = 'not-json'")
        connection.execute("UPDATE sessions SET state_json = '[]'")
        connection.execute("UPDATE goals SET goal_json = '{broken'")
        connection.commit()
    finally:
        connection.close()

    reopened = SqliteRepository(db_path)
    try:
        with pytest.raises(ValidationError):
            reopened.get_snapshot(LEARNER)
        with pytest.raises(ValidationError):
            reopened.get_event("evt.a.0")
        with pytest.raises(ValidationError):
            reopened.list_events(LEARNER)
        with pytest.raises(ValidationError):
            reopened.load_session(SESSION)
        with pytest.raises(ValidationError):
            reopened.get_goal("goal.1")
    finally:
        reopened.close()


# ---------------------------------------------------------------------------
# Foreign keys are actually enforced
# ---------------------------------------------------------------------------


def test_foreign_keys_are_enforced(repository: SqliteRepository):
    with pytest.raises(sqlite3.IntegrityError):
        repository._conn.execute(  # noqa: SLF001 - raw write to prove the FK pragma
            "INSERT INTO snapshots(learner_id, revision, updated_at, snapshot_json) "
            "VALUES ('ghost.learner', 0, ?, '{}')",
            (TS,),
        )
