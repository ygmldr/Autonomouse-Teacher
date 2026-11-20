"""B-PR3 schema v1 -> v2 migration and legacy-result adoption tests.

The migration is **additive**: it creates the ``result_scopes`` table/indexes and
derives metadata rows from the append-only event log.  It must not rewrite,
delete or reorder a single historical event/snapshot/session/goal, and it must
fail closed (whole migration rolled back) on corrupted evidence or an
unsupported on-disk version.

The v1 databases used here are real SQLite files produced by the engine, then
downgraded in-place (drop the additive table, set ``schema_meta.version = 1``,
strip the B-PR3-only payload keys) so the migration is exercised against the
same shapes a pre-B-PR3 worktree wrote.  All data is synthetic fixtures.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from m1_teacher import demo
from m1_teacher.contracts.errors import ConflictError, ValidationError
from m1_teacher.contracts.types import AssessmentItem, AssessmentResult, LearnerGoal
from m1_teacher.learner.history import LearningHistory
from m1_teacher.learner.repository import SCHEMA_VERSION, SqliteRepository
from m1_teacher.session.engine import TeachingSessionEngine

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "m1_teacher"
LEARNER = "m1b.pr3.migration.learner"
OTHER_LEARNER = "m1b.pr3.migration.other"
TS = demo.FIXED_TIMESTAMP
TOKEN = "pr3.legacy.token.1"


@pytest.fixture(scope="module")
def components() -> demo.Components:
    return demo.build_components(FIXTURES)


class ScriptedScorer:
    scorer_id = "m1b.pr3.migration.scorer.v0"

    def __init__(self, status: str = "CORRECT") -> None:
        self.status = status
        self.calls = 0

    def score(
        self,
        item: AssessmentItem,
        learner_id: str,
        response: str | dict,
        *,
        result_id: str | None = None,
    ) -> AssessmentResult:
        self.calls += 1
        return AssessmentResult(
            result_id=result_id or f"scripted:{item.item_id}:{self.calls:03d}",
            item_id=item.item_id,
            learner_id=learner_id,
            status=self.status,
            score=1.0 if self.status == "CORRECT" else 0.0,
            max_score=float(item.max_score),
            scorer_id=self.scorer_id,
            failure_reason="" if self.status == "CORRECT" else f"SCRIPTED:{self.status}",
            created_at=TS,
        )


def drive_to_pending(
    engine: TeachingSessionEngine, repository: SqliteRepository, session_id: str
):
    for _ in range(60):
        state = repository.load_session(session_id)
        assert state is not None
        if state.pending_item_id is not None:
            return state
        if state.phase in {"COMPLETE", "PAUSED"}:
            return state
        action = engine.current_action(session_id)
        if action.item_id is None:
            engine.advance_session(session_id)
    raise AssertionError("session did not reach a pending item")


def build_legacy_database(
    components: demo.Components,
    db_path: Path,
    *,
    drop_attempt_events: bool = False,
    corrupt_event_type: str | None = None,
    extra_audit_error: bool = False,
) -> dict:
    """Create one committed PR2-shaped session, then downgrade the file to v1."""

    repository = SqliteRepository(db_path)
    engine, _history = demo._make_engine(components, repository, ScriptedScorer())
    goal = LearnerGoal(
        goal_id=f"goal.{LEARNER}.{components.objective.objective_id}",
        learner_id=LEARNER,
        objective_id=components.objective.objective_id,
        created_at=TS,
    )
    state = engine.start_session(
        LEARNER, goal, components.objective, session_id="session.legacy.migration"
    )
    pending = drive_to_pending(engine, repository, state.session_id)
    item_id = pending.pending_item_id
    assert item_id is not None
    result = engine.submit_response(
        state.session_id, item_id, "A", result_id=TOKEN
    )
    session_id = state.session_id
    turn_index = pending.turn_index
    repository.close()

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("DROP TABLE result_scopes")
        conn.execute("UPDATE schema_meta SET version = 1")
        if extra_audit_error:
            seq = conn.execute(
                "SELECT COALESCE(MAX(seq), -1) + 1 FROM history_events WHERE learner_id = ?",
                (LEARNER,),
            ).fetchone()[0]
            conn.execute(
                "INSERT INTO history_events("
                "event_id, learner_id, session_id, seq, event_type, payload_json, created_at"
                ") VALUES (?, ?, ?, ?, 'ERROR', ?, ?)",
                (
                    "evt.recoveryerror.legacy.audit",
                    LEARNER,
                    session_id,
                    seq,
                    json.dumps(
                        {
                            "stage": "RECOVERY",
                            "status": "RECOVERY_STATE_INCONSISTENT",
                            "result_id": "audit.only.result",
                            "mastery_unchanged": True,
                        },
                        sort_keys=True,
                    ),
                    TS,
                ),
            )
        rows = conn.execute(
            "SELECT event_id, event_type, payload_json FROM history_events ORDER BY learner_id, seq"
        ).fetchall()
        for event_id, event_type, raw in rows:
            if drop_attempt_events and event_type in {
                "RESPONSE_SUBMITTED",
                "ASSESSMENT_PREPARED",
            }:
                conn.execute("DELETE FROM history_events WHERE event_id = ?", (event_id,))
                continue
            if corrupt_event_type is not None and event_type == corrupt_event_type:
                conn.execute(
                    "UPDATE history_events SET payload_json = '{not-json' WHERE event_id = ?",
                    (event_id,),
                )
                continue
            payload = json.loads(raw)
            payload.pop("scope", None)
            payload.pop("request_digest", None)
            conn.execute(
                "UPDATE history_events SET payload_json = ? WHERE event_id = ?",
                (
                    json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                    event_id,
                ),
            )
        conn.commit()
        history_rows = [
            tuple(row)
            for row in conn.execute(
                "SELECT event_id, learner_id, session_id, seq, event_type, payload_json, "
                "created_at FROM history_events ORDER BY learner_id, seq"
            ).fetchall()
        ]
        session_rows = [
            tuple(row)
            for row in conn.execute(
                "SELECT session_id, learner_id, state_json, updated_at FROM sessions "
                "ORDER BY session_id"
            ).fetchall()
        ]
        snapshot_rows = [
            tuple(row)
            for row in conn.execute(
                "SELECT learner_id, revision, updated_at, snapshot_json FROM snapshots "
                "ORDER BY learner_id"
            ).fetchall()
        ]
        goal_rows = [
            tuple(row)
            for row in conn.execute(
                "SELECT goal_id, learner_id, objective_id, status, goal_json, created_at "
                "FROM goals ORDER BY goal_id"
            ).fetchall()
        ]
        version_rows = [
            int(row[0]) for row in conn.execute("SELECT version FROM schema_meta").fetchall()
        ]
        assert version_rows == [1]
    finally:
        conn.close()
    return {
        "session_id": session_id,
        "item_id": item_id,
        "turn_index": turn_index,
        "result": result,
        "history_rows": history_rows,
        "session_rows": session_rows,
        "snapshot_rows": snapshot_rows,
        "goal_rows": goal_rows,
    }


def read_history_rows(db_path: Path) -> list[tuple]:
    conn = sqlite3.connect(db_path)
    try:
        return [
            tuple(row)
            for row in conn.execute(
                "SELECT event_id, learner_id, session_id, seq, event_type, payload_json, "
                "created_at FROM history_events ORDER BY learner_id, seq"
            ).fetchall()
        ]
    finally:
        conn.close()


def read_scope_rows(db_path: Path) -> list[tuple]:
    conn = sqlite3.connect(db_path)
    try:
        return [
            tuple(row)
            for row in conn.execute(
                "SELECT result_id, learner_id, session_id, item_id, turn_index, "
                "request_digest, status, origin, result_event_id FROM result_scopes "
                "ORDER BY result_id"
            ).fetchall()
        ]
    finally:
        conn.close()


def raw_version_rows(db_path: Path) -> list[int]:
    conn = sqlite3.connect(db_path)
    try:
        return [int(row[0]) for row in conn.execute("SELECT version FROM schema_meta")]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Fresh v2 schema
# ---------------------------------------------------------------------------


def test_fresh_database_is_schema_v2_with_empty_scope_index(tmp_path: Path) -> None:
    repository = SqliteRepository(tmp_path / "fresh.sqlite")
    try:
        assert SCHEMA_VERSION == 2
        assert repository.schema_version == 2
        version_rows = repository._conn.execute(  # noqa: SLF001 - white-box schema evidence
            "SELECT version FROM schema_meta"
        ).fetchall()
        assert [int(row["version"]) for row in version_rows] == [2]
        table = repository._conn.execute(  # noqa: SLF001
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'result_scopes'"
        ).fetchone()
        assert table is not None
        columns = {
            row["name"]
            for row in repository._conn.execute(  # noqa: SLF001
                "PRAGMA table_info(result_scopes)"
            ).fetchall()
        }
        assert {
            "result_id",
            "scope_version",
            "learner_id",
            "session_id",
            "item_id",
            "turn_index",
            "request_digest",
            "status",
            "attempt_id",
            "result_event_id",
            "origin",
            "created_at",
            "updated_at",
        } <= columns
        assert (
            repository._conn.execute(  # noqa: SLF001
                "SELECT COUNT(*) FROM result_scopes"
            ).fetchone()[0]
            == 0
        )
    finally:
        repository.close()


# ---------------------------------------------------------------------------
# Additive v1 -> v2 migration
# ---------------------------------------------------------------------------


def test_v1_database_migrates_additively_and_preserves_history(
    components: demo.Components, tmp_path: Path
) -> None:
    db_path = tmp_path / "migrate.sqlite"
    legacy = build_legacy_database(components, db_path)
    repository = SqliteRepository(db_path)
    try:
        assert repository.schema_version == 2
        assert raw_version_rows(db_path) == [2]
        # History / session / snapshot / goal rows are byte-identical: the
        # migration only added the result_scopes table + derived metadata rows.
        assert read_history_rows(db_path) == legacy["history_rows"]
        assert len(legacy["history_rows"]) > 0
        session_rows = [
            tuple(row)
            for row in repository._conn.execute(  # noqa: SLF001
                "SELECT session_id, learner_id, state_json, updated_at FROM sessions "
                "ORDER BY session_id"
            ).fetchall()
        ]
        assert session_rows == legacy["session_rows"]
        snapshot_rows = [
            tuple(row)
            for row in repository._conn.execute(  # noqa: SLF001
                "SELECT learner_id, revision, updated_at, snapshot_json FROM snapshots "
                "ORDER BY learner_id"
            ).fetchall()
        ]
        assert snapshot_rows == legacy["snapshot_rows"]
        goal_rows = [
            tuple(row)
            for row in repository._conn.execute(  # noqa: SLF001
                "SELECT goal_id, learner_id, objective_id, status, goal_json, created_at "
                "FROM goals ORDER BY goal_id"
            ).fetchall()
        ]
        assert goal_rows == legacy["goal_rows"]

        rows = read_scope_rows(db_path)
        assert len(rows) == 1, "one terminal legacy result must produce one metadata row"
        (
            result_id,
            learner_id,
            session_id,
            item_id,
            turn_index,
            request_digest_marker,
            status,
            origin,
            result_event_id,
        ) = rows[0]
        assert result_id == TOKEN
        assert learner_id == LEARNER
        assert session_id == legacy["session_id"]
        assert item_id == legacy["item_id"]
        assert turn_index == legacy["turn_index"]
        assert request_digest_marker == "legacy:" + hashlib.sha256(b"A").hexdigest()[:16]
        assert status == "TERMINAL"
        assert origin == "legacy"
        assert result_event_id == f"evt.assessed.{TOKEN}"

        history = LearningHistory(repository)
        assert history.verify_rebuild(LEARNER) is True
    finally:
        repository.close()


def test_v1_migration_is_idempotent_on_reopen(
    components: demo.Components, tmp_path: Path
) -> None:
    db_path = tmp_path / "reopen.sqlite"
    build_legacy_database(components, db_path)
    repository = SqliteRepository(db_path)
    repository.close()
    history_rows = read_history_rows(db_path)
    scope_rows = read_scope_rows(db_path)
    repository = SqliteRepository(db_path)
    try:
        assert raw_version_rows(db_path) == [2]
        assert read_history_rows(db_path) == history_rows
        assert read_scope_rows(db_path) == scope_rows
        assert len(scope_rows) == 1
    finally:
        repository.close()


def test_v1_migration_skips_audit_error_events_without_result_payload(
    components: demo.Components, tmp_path: Path
) -> None:
    db_path = tmp_path / "audit.sqlite"
    build_legacy_database(components, db_path, extra_audit_error=True)
    repository = SqliteRepository(db_path)
    try:
        rows = read_scope_rows(db_path)
        assert len(rows) == 1
        assert rows[0][0] == TOKEN, "only the real terminal assessment is indexed"
        assert all(row[0] != "audit.only.result" for row in rows)
        event_types = [
            event.event_type for event in repository.list_events(LEARNER)
        ]
        assert "ERROR" in event_types, "the audit ERROR event must be preserved"
        assert LearningHistory(repository).verify_rebuild(LEARNER) is True
    finally:
        repository.close()


# ---------------------------------------------------------------------------
# Migrated legacy results: digest-proven adoption / fail-closed rejection
# ---------------------------------------------------------------------------


def test_migrated_legacy_result_is_adoptable_with_digest_proof(
    components: demo.Components, tmp_path: Path
) -> None:
    db_path = tmp_path / "adopt.sqlite"
    legacy = build_legacy_database(components, db_path)
    repository = SqliteRepository(db_path)
    try:
        engine, history = demo._make_engine(  # noqa: SLF001 - test wiring
            components, repository, ScriptedScorer()
        )
        event_count = len(repository.list_events(LEARNER))
        # Same token + same response: proven legacy replay, zero events, no scoring.
        replay = engine.submit_response(
            legacy["session_id"], legacy["item_id"], "A", result_id=TOKEN
        )
        assert replay.to_dict() == legacy["result"].to_dict()
        assert replay.learner_id == LEARNER
        assert len(repository.list_events(LEARNER)) == event_count
        assert history.verify_rebuild(LEARNER) is True

        # Same token + different response: digest mismatch, no old grade returned.
        with pytest.raises(ConflictError) as excinfo:
            engine.submit_response(
                legacy["session_id"], legacy["item_id"], "B", result_id=TOKEN
            )
        assert excinfo.value.code == "IDEMPOTENCY_CONFLICT"
        assert excinfo.value.details["reason"] == "REQUEST_DIGEST_MISMATCH"
        assert len(repository.list_events(LEARNER)) == event_count

        # Foreign learner replaying the same legacy token is rejected.
        engine_other, _ = demo._make_engine(  # noqa: SLF001 - test wiring
            components, repository, ScriptedScorer()
        )
        goal = LearnerGoal(
            goal_id=f"goal.{OTHER_LEARNER}.{components.objective.objective_id}",
            learner_id=OTHER_LEARNER,
            objective_id=components.objective.objective_id,
            created_at=TS,
        )
        other_state = engine_other.start_session(
            OTHER_LEARNER,
            goal,
            components.objective,
            session_id="session.legacy.other",
        )
        other_pending = drive_to_pending(
            engine_other, repository, other_state.session_id
        )
        other_events = len(repository.list_events(OTHER_LEARNER))
        with pytest.raises(ConflictError) as excinfo:
            engine_other.submit_response(
                other_state.session_id,
                other_pending.pending_item_id,
                "A",
                result_id=TOKEN,
            )
        assert excinfo.value.code == "IDEMPOTENCY_CONFLICT"
        assert excinfo.value.details["reason"] == "LEGACY_SCOPE_MISMATCH"
        assert LEARNER not in json.dumps(excinfo.value.details)
        assert len(repository.list_events(OTHER_LEARNER)) == other_events
    finally:
        repository.close()


def test_unproven_legacy_result_is_rejected_by_default(
    components: demo.Components, tmp_path: Path
) -> None:
    db_path = tmp_path / "unproven.sqlite"
    legacy = build_legacy_database(components, db_path, drop_attempt_events=True)
    repository = SqliteRepository(db_path)
    try:
        rows = read_scope_rows(db_path)
        assert len(rows) == 1
        assert rows[0][0] == TOKEN
        assert rows[0][4] == -1, "pre-scope row has no provable turn"
        assert rows[0][5] == "legacy:unproven"
        engine, _ = demo._make_engine(  # noqa: SLF001 - test wiring
            components, repository, ScriptedScorer()
        )
        event_count = len(repository.list_events(LEARNER))
        with pytest.raises(ConflictError) as excinfo:
            engine.submit_response(
                legacy["session_id"], legacy["item_id"], "A", result_id=TOKEN
            )
        assert excinfo.value.code == "IDEMPOTENCY_CONFLICT"
        assert excinfo.value.details["reason"] == "LEGACY_DIGEST_UNPROVEN"
        assert len(repository.list_events(LEARNER)) == event_count
    finally:
        repository.close()


# ---------------------------------------------------------------------------
# Fail-closed schema handling
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("version", [3, 99, -1])
def test_unsupported_schema_version_fails_closed(tmp_path: Path, version: int) -> None:
    db_path = tmp_path / f"version-{version}.sqlite"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("CREATE TABLE schema_meta (version INTEGER NOT NULL)")
        conn.execute("INSERT INTO schema_meta(version) VALUES (?)", (version,))
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(ValidationError) as excinfo:
        SqliteRepository(db_path)
    assert "unsupported on-disk schema version" in excinfo.value.message


def test_corrupt_legacy_event_rolls_back_the_whole_migration(
    components: demo.Components, tmp_path: Path
) -> None:
    db_path = tmp_path / "corrupt.sqlite"
    build_legacy_database(components, db_path, corrupt_event_type="ASSESSED")
    with pytest.raises(ValidationError):
        SqliteRepository(db_path)
    assert raw_version_rows(db_path) == [1], "a failed migration must not bump the version"
    conn = sqlite3.connect(db_path)
    try:
        table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'result_scopes'"
        ).fetchone()
        assert table is None, "a failed migration must not leave a partial v2 table"
    finally:
        conn.close()


def test_v2_database_self_heals_a_missing_additive_table(tmp_path: Path) -> None:
    db_path = tmp_path / "selfheal.sqlite"
    repository = SqliteRepository(db_path)
    repository.ensure_learner(LEARNER)
    repository.close()
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("DROP TABLE result_scopes")
        conn.commit()
    finally:
        conn.close()
    repository = SqliteRepository(db_path)
    try:
        assert repository.schema_version == 2
        assert raw_version_rows(db_path) == [2]
        assert (
            repository._conn.execute(  # noqa: SLF001 - white-box evidence
                "SELECT COUNT(*) FROM result_scopes"
            ).fetchone()[0]
            == 0
        )
        assert repository.list_learners() == [LEARNER]
    finally:
        repository.close()
