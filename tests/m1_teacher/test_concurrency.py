"""Concurrency / robustness tests for B-NEXT session transactions (B2-03).

All concurrent writes are real OS processes (``tests/m1_teacher/txn_child.py``)
started against the same SQLite file behind a file-barrier.  The asserted
contract is:

* same session + concurrent submissions: at most one turn is applied; every
  loser either receives the same result (identical request id) or a stable
  explicit ``ConflictError`` — never a silent last-write-wins;
* same learner + two sessions: updates serialise, or a loser fails closed with
  an explicit revision/seq conflict; the session can then be recovered by the
  recovery API and the final state must still rebuild exactly from the log;
* cross-process cold start, busy/locked database, unsupported/old schema and
  corrupted JSON all fail closed.

The "single active writer per learner/session" product constraint and the
exactly-once state / at-least-once scorer boundary are documented in
``docs/M1_B_TXN_RECOVERY.md``.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import time
from pathlib import Path

import pytest

from m1_teacher import demo
from m1_teacher.contracts.errors import ConflictError, ValidationError
from m1_teacher.contracts.types import HistoryEvent
from m1_teacher.learner.history import LearningHistory
from m1_teacher.learner.repository import SqliteRepository
from m1_teacher.session.engine import TeachingSessionEngine
from txn_support import (  # noqa: F401 - local test support module
    LEARNER,
    child_command,
    child_env,
    components,
    db_summary,
    run_child,
    setup_pending,
)

EXPLICIT_CONFLICT_CODES = {
    "IDEMPOTENCY_CONFLICT",
    "SESSION_VERSION_CONFLICT",
    "SNAPSHOT_REVISION_CONFLICT",
    "EVENT_SEQ_CONFLICT",
    "DUPLICATE_EVENT",
    "CONFLICT",
}


# ---------------------------------------------------------------------------
# Process helpers
# ---------------------------------------------------------------------------


def _start_pair(
    commands: list[list[str]], barrier: Path
) -> list[tuple[int, str, str]]:
    """Start children that wait for ``barrier``, release them, collect results."""

    processes = [
        subprocess.Popen(
            command,
            cwd=str(Path(__file__).resolve().parents[2]),
            env=child_env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for command in commands
    ]
    # Give every child time to reach the wait loop before releasing the barrier.
    time.sleep(0.4)
    barrier.write_text("go", encoding="utf-8")
    results: list[tuple[int, str, str]] = []
    for process in processes:
        stdout, stderr = process.communicate(timeout=120)
        results.append((process.returncode, stdout, stderr))
    return results


def _parse_child(result: tuple[int, str, str]) -> dict:
    returncode, stdout, stderr = result
    payload = json.loads(stdout)
    payload["_returncode"] = returncode
    payload["_stderr"] = stderr
    return payload


def _engine_for(db_path: Path, *, busy_timeout_ms: int | None = None) -> TeachingSessionEngine:
    components_ = components()
    student = demo.load_student_fixture(components_.fixtures_root, "student_a")
    kwargs = {} if busy_timeout_ms is None else {"busy_timeout_ms": busy_timeout_ms}
    repository = SqliteRepository(db_path, **kwargs)
    engine, _history = demo._make_engine(  # noqa: SLF001
        components_, repository, demo.MockStudentScorer(student)
    )
    return engine


def _open_repository(db_path: Path) -> SqliteRepository:
    return SqliteRepository(db_path)


def _assert_single_learner_log(
    repository: SqliteRepository,
    *,
    learner_id: str = LEARNER,
    snapshot_learner: str | None = LEARNER,
) -> dict:
    events = repository.list_events(learner_id)
    seqs = [event.seq for event in events]
    assert seqs == sorted(seqs)
    assert len(seqs) == len(set(seqs))
    for event in events:
        assert event.learner_id == learner_id
    assert repository.list_learners() == [learner_id]
    snapshot = repository.get_snapshot(learner_id)
    if snapshot_learner is None:
        assert snapshot is None
    else:
        assert snapshot is not None and snapshot.learner_id == snapshot_learner
    assert LearningHistory(repository).verify_rebuild(learner_id) is True
    return {
        "events": events,
        "snapshot": snapshot,
        "snapshot_revision": None if snapshot is None else snapshot.revision,
    }


# ---------------------------------------------------------------------------
# Same session, two processes
# ---------------------------------------------------------------------------


def test_concurrent_same_session_different_responses_one_explicit_conflict(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "same_session.db"
    setup = setup_pending(db_path)
    barrier = tmp_path / "barrier"
    commands = [
        child_command(
            db_path=db_path,
            session_id=setup.session_id,
            item_id=setup.item_id,
            response=response,
            wait_file=barrier,
        )
        for response in ("A", "B")
    ]
    results = [_parse_child(result) for result in _start_pair(commands, barrier)]
    successes = [result for result in results if result["_returncode"] == 0]
    failures = [result for result in results if result["_returncode"] != 0]
    assert len(successes) == 1, results
    assert len(failures) == 1, results
    assert failures[0].get("code") in EXPLICIT_CONFLICT_CODES, failures[0]

    repository = _open_repository(db_path)
    try:
        state = repository.load_session(setup.session_id)
        assert state is not None
        assert state.turn_index == setup.turn_index + 1
        assert state.pending_item_id is None
        log = _assert_single_learner_log(repository)
        terminal = [event for event in log["events"] if event.event_type == "ASSESSED"]
        assert len(terminal) == 1, "exactly one response may be applied"
        assert log["snapshot_revision"] == 1
    finally:
        repository.close()

    # The winner's result id retry is idempotent: zero appended events.
    winner_index = results.index(successes[0])
    winner_result_id = successes[0]["result"]["result_id"]
    summary_before = db_summary(db_path, setup.session_id)
    retry = run_child(
        db_path=db_path,
        session_id=setup.session_id,
        item_id=setup.item_id,
        response=("A", "B")[winner_index],
        result_id=winner_result_id,
    )
    assert retry.returncode == 0, retry.stdout + retry.stderr
    summary_after = db_summary(db_path, setup.session_id)
    assert summary_after["event_count"] == summary_before["event_count"]
    assert summary_after["content_hash"] == summary_before["content_hash"]


def test_concurrent_same_session_same_request_returns_same_result_exactly_once(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "same_request.db"
    setup = setup_pending(db_path)
    barrier = tmp_path / "barrier"
    result_id = "m1b.concurrent.shared-result"
    commands = [
        child_command(
            db_path=db_path,
            session_id=setup.session_id,
            item_id=setup.item_id,
            response="A",
            result_id=result_id,
            wait_file=barrier,
        )
        for _ in range(2)
    ]
    results = [_parse_child(result) for result in _start_pair(commands, barrier)]
    assert [result["_returncode"] for result in results] == [0, 0], results
    assert {result["result"]["result_id"] for result in results} == {result_id}
    repository = _open_repository(db_path)
    try:
        state = repository.load_session(setup.session_id)
        assert state is not None and state.pending_item_id is None
        log = _assert_single_learner_log(repository)
        # Exactly-once *state application* even though the scorer may run twice.
        assert len([e for e in log["events"] if e.event_type == "ASSESSED"]) == 1
        assert len([e for e in log["events"] if e.event_type == "ASSESSMENT_PREPARED"]) == 1
        assert log["snapshot_revision"] == 1
    finally:
        repository.close()


# ---------------------------------------------------------------------------
# Same learner, two sessions (shared snapshot / sequence space)
# ---------------------------------------------------------------------------


def test_concurrent_two_sessions_same_learner_serialize_or_conflict_never_lose(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "two_sessions.db"
    first = setup_pending(db_path)
    second = setup_pending(
        db_path,
        session_suffix=".second",
        explicit_session_id="session.m1b.second",
    )
    assert first.session_id != second.session_id
    barrier = tmp_path / "barrier"
    specs = [
        (first, "A", "m1b.result.first"),
        (second, "C", "m1b.result.second"),
    ]
    commands = [
        child_command(
            db_path=db_path,
            session_id=setup.session_id,
            item_id=setup.item_id,
            response=response,
            result_id=result_id,
            wait_file=barrier,
        )
        for setup, response, result_id in specs
    ]
    results = [_parse_child(result) for result in _start_pair(commands, barrier)]
    assert any(result["_returncode"] == 0 for result in results), results
    for result in results:
        if result["_returncode"] != 0:
            assert result.get("code") in EXPLICIT_CONFLICT_CODES, result

    repository = _open_repository(db_path)
    try:
        for setup, _response, _result_id in specs:
            state = repository.load_session(setup.session_id)
            assert state is not None
            if state.pending_item_id is not None:
                assert state.turn_index == setup.turn_index
        log = _assert_single_learner_log(repository)
        successes = sum(1 for result in results if result["_returncode"] == 0)
        assert len([e for e in log["events"] if e.event_type == "ASSESSED"]) == successes
    finally:
        repository.close()

    # Any failed session must be recoverable (prepared attempt) or retryable
    # (nothing prepared); after recovery both sessions have advanced exactly once.
    for (setup, response, result_id), result in zip(specs, results, strict=True):
        if result["_returncode"] == 0:
            continue
        recovery = run_child(db_path=db_path, session_id=setup.session_id, mode="recover")
        assert recovery.returncode == 0, recovery.stdout + recovery.stderr
        status = json.loads(recovery.stdout)["report"]["status"]
        assert status in {"RECOVERED", "ALREADY_CONSISTENT"}, status
        if status == "ALREADY_CONSISTENT":
            retry = run_child(
                db_path=db_path,
                session_id=setup.session_id,
                item_id=setup.item_id,
                response=response,
                result_id=result_id,
            )
            assert retry.returncode == 0, retry.stdout + retry.stderr

    repository = _open_repository(db_path)
    try:
        for setup, _response, _result_id in specs:
            state = repository.load_session(setup.session_id)
            assert state is not None
            assert state.pending_item_id is None, "both sessions must finish the turn"
            assert state.turn_index == setup.turn_index + 1
        snapshot = repository.get_snapshot(LEARNER)
        assert snapshot is not None
        assert snapshot.revision == 2, "both mutating results must be applied once"
        assert LearningHistory(repository).verify_rebuild(LEARNER) is True
        events = repository.list_events(LEARNER)
        assert len([e for e in events if e.event_type == "ASSESSED"]) == 2
        seqs = [event.seq for event in events]
        assert seqs == sorted(seqs) and len(seqs) == len(set(seqs))
    finally:
        repository.close()


# ---------------------------------------------------------------------------
# Cross-process cold start / cross-learner isolation
# ---------------------------------------------------------------------------


def test_cold_start_child_process_continues_existing_database(tmp_path: Path) -> None:
    db_path = tmp_path / "cold_start.db"
    setup = setup_pending(db_path)  # parent opens and closes the database
    start = run_child(
        db_path=db_path,
        session_id=setup.session_id,
        item_id=setup.item_id,
        response="A",
    )
    assert start.returncode == 0, start.stdout + start.stderr
    result_id = json.loads(start.stdout)["result"]["result_id"]
    repository = _open_repository(db_path)
    try:
        state = repository.load_session(setup.session_id)
        assert state is not None and state.pending_item_id is None
        assert repository.get_snapshot(LEARNER) is not None
        _assert_single_learner_log(repository)
    finally:
        repository.close()
    # A second cold process retries the same result id: idempotent.
    retry = run_child(
        db_path=db_path,
        session_id=setup.session_id,
        item_id=setup.item_id,
        response="A",
        result_id=result_id,
    )
    assert retry.returncode == 0, retry.stdout + retry.stderr
    assert json.loads(retry.stdout)["result"]["result_id"] == result_id
    summary = db_summary(db_path, setup.session_id)
    repository = _open_repository(db_path)
    try:
        assert summary["event_count"] == len(repository.list_events(LEARNER))
    finally:
        repository.close()


def test_concurrent_two_learners_do_not_pollute_each_other(tmp_path: Path) -> None:
    db_path = tmp_path / "isolated.db"
    other_learner = "m1b.other.learner"
    first = setup_pending(db_path)
    second = setup_pending(db_path, learner_id=other_learner, session_suffix=".b")
    assert first.session_id != second.session_id
    barrier = tmp_path / "barrier"
    commands = [
        child_command(
            db_path=db_path,
            session_id=first.session_id,
            item_id=first.item_id,
            response="A",
            wait_file=barrier,
        ),
        child_command(
            db_path=db_path,
            session_id=second.session_id,
            item_id=second.item_id,
            response="B",
            learner_id=other_learner,
            wait_file=barrier,
        ),
    ]
    results = [_parse_child(result) for result in _start_pair(commands, barrier)]
    assert [result["_returncode"] for result in results] == [0, 0], results
    repository = _open_repository(db_path)
    try:
        assert repository.list_learners() == [LEARNER, other_learner]
        for learner, setup in ((LEARNER, first), (other_learner, second)):
            events = repository.list_events(learner)
            assert events, f"learner {learner!r} has no events"
            assert all(event.learner_id == learner for event in events)
            snapshot = repository.get_snapshot(learner)
            assert snapshot is not None and snapshot.learner_id == learner
            assert LearningHistory(repository).verify_rebuild(learner) is True
            state = repository.load_session(setup.session_id)
            assert state is not None and state.pending_item_id is None
        a_result_id = results[0]["result"]["result_id"]
        b_result_id = results[1]["result"]["result_id"]
        assert a_result_id != b_result_id
        assert all(
            event.learner_id == LEARNER
            for event in repository.list_events(LEARNER)
            if event.payload.get("result_id") == a_result_id
        )
        assert all(
            event.learner_id == other_learner
            for event in repository.list_events(other_learner)
            if event.payload.get("result_id") == b_result_id
        )
    finally:
        repository.close()


# ---------------------------------------------------------------------------
# Busy / locked database, old schema and corrupted JSON fail closed
# ---------------------------------------------------------------------------


def test_busy_database_fails_closed_with_db_busy_and_can_be_retried(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "busy.db"
    setup = setup_pending(db_path)
    engine = _engine_for(db_path, busy_timeout_ms=100)
    repository = engine.repository
    try:
        locker = sqlite3.connect(str(db_path), isolation_level=None, timeout=5.0)
        try:
            locker.execute("BEGIN IMMEDIATE")
            started = time.monotonic()
            with pytest.raises(ConflictError) as excinfo:
                engine.submit_response(setup.session_id, setup.item_id, "A")
            elapsed = time.monotonic() - started
            assert excinfo.value.code == "DB_BUSY"
            assert elapsed < 5.0, "the configured busy timeout must bound the wait"
            assert not any(
                event.event_type == "ASSESSMENT_PREPARED"
                for event in repository.list_events(LEARNER)
            )
        finally:
            locker.execute("ROLLBACK")
            locker.close()
        # After the lock is released the same submission succeeds.
        result = engine.submit_response(setup.session_id, setup.item_id, "A")
        assert result.status == "CORRECT"
        summary = db_summary(db_path, setup.session_id)
        assert summary["terminal_results"] == 1
    finally:
        repository.close()


def test_old_schema_version_fails_closed(tmp_path: Path) -> None:
    db_path = tmp_path / "old_schema.db"
    connection = sqlite3.connect(str(db_path))
    try:
        connection.execute("CREATE TABLE schema_meta (version INTEGER NOT NULL)")
        connection.execute("INSERT INTO schema_meta(version) VALUES (999)")
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(ValidationError):
        SqliteRepository(db_path)


def test_corrupted_prepared_event_fails_recovery_closed(tmp_path: Path) -> None:
    db_path = tmp_path / "corrupt_prepared.db"
    setup = setup_pending(db_path)
    repository = _open_repository(db_path)
    try:
        repository.append_event(
            HistoryEvent(
                event_id="evt.assessmentprepared.corrupt",
                learner_id=LEARNER,
                session_id=setup.session_id,
                seq=max((event.seq for event in repository.list_events(LEARNER)), default=-1) + 1,
                event_type="ASSESSMENT_PREPARED",
                payload={"attempt_id": "corrupt"},
                created_at=demo.FIXED_TIMESTAMP,
            )
        )
        engine = _engine_for(db_path)
        with pytest.raises(ValidationError):
            engine.recover_session(setup.session_id)
        # Fail-closed: no terminal event and no session advancement were fabricated.
        state = repository.load_session(setup.session_id)
        assert state is not None and state.pending_item_id == setup.item_id
        assert not any(
            event.event_type in {"ASSESSED", "ERROR"}
            for event in repository.list_events(LEARNER)
        )
    finally:
        repository.close()


def test_corrupted_snapshot_json_fails_closed(tmp_path: Path) -> None:
    db_path = tmp_path / "corrupt_snapshot.db"
    setup = setup_pending(db_path)
    started = run_child(
        db_path=db_path,
        session_id=setup.session_id,
        item_id=setup.item_id,
        response="A",
    )
    assert started.returncode == 0, started.stdout + started.stderr
    connection = sqlite3.connect(str(db_path))
    try:
        connection.execute("UPDATE snapshots SET snapshot_json = '{broken'")
        connection.commit()
    finally:
        connection.close()
    repository = _open_repository(db_path)
    try:
        with pytest.raises(ValidationError):
            repository.get_snapshot(LEARNER)
        engine = _engine_for(db_path)
        with pytest.raises(ValidationError):
            engine.current_action(setup.session_id)
    finally:
        repository.close()
