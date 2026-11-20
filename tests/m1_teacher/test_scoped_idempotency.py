"""B-PR3 scoped-idempotency tests (B3-01 / B3-02).

Every assertion here targets one of the frozen invariants from
``docs/M1_B_SCOPED_IDEMPOTENCY.md``:

* I1 same scope + same request digest -> same result, **zero** new events/writes;
* I2 same token with a different request/item/turn -> stable
  ``IDEMPOTENCY_CONFLICT`` with a machine-readable reason;
* I3 a result is only returned to the exact requesting scope (never another
  learner's/session's ``AssessmentResult``; error details carry requester data
  only);
* I4 one terminal assessment per attempt scope;
* I5 history stays append-only (conflict paths append nothing);
* I6 fail closed (invalid tokens, unknown legacy evidence, missing extension).

The external scorer is a deterministic in-process double (``MOCK`` evidence
class); no network, provider, credentials or wall-clock-dependent assertions are
used.  Real multi-process convergence is covered by
:func:`test_concurrent_same_token_same_response_converges`.
"""

from __future__ import annotations

import ast
import json
import subprocess
import time
from dataclasses import replace
from pathlib import Path

import pytest

from m1_teacher import demo
from m1_teacher.contracts.errors import ConflictError, ValidationError
from m1_teacher.contracts.types import (
    AssessmentItem,
    AssessmentResult,
    HistoryEvent,
    LearnerGoal,
    SessionState,
)
from m1_teacher.idempotency import ResultScope, request_digest
from m1_teacher.learner.history import LearningHistory
from m1_teacher.learner.repository import SqliteRepository, session_version
from m1_teacher.session import engine as engine_module
from m1_teacher.session.engine import TeachingSessionEngine
from txn_support import child_command, child_env, db_summary, setup_pending, REPO_ROOT

FIXTURES = REPO_ROOT / "fixtures" / "m1_teacher"
LEARNER = "m1b.pr3.learner.a"
LEARNER_B = "m1b.pr3.learner.b"
TS = demo.FIXED_TIMESTAMP


# ---------------------------------------------------------------------------
# Deterministic doubles / helpers
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def components() -> demo.Components:
    return demo.build_components(FIXTURES)


class ScriptedScorer:
    """Deterministic scorer double; counts invocations to prove replay semantics."""

    scorer_id = "m1b.pr3.scripted.v0"

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
        score = {"CORRECT": 1.0, "INCORRECT": 0.0, "PARTIAL": 0.5}.get(self.status)
        return AssessmentResult(
            result_id=result_id or f"scripted:{item.item_id}:{self.calls:03d}",
            item_id=item.item_id,
            learner_id=learner_id,
            status=self.status,
            score=score,
            max_score=float(item.max_score),
            scorer_id=self.scorer_id,
            failure_reason="" if self.status == "CORRECT" else f"SCRIPTED:{self.status}",
            created_at=TS,
        )


def build_engine(
    components: demo.Components, repository: SqliteRepository, scorer: object
) -> tuple[TeachingSessionEngine, LearningHistory]:
    return demo._make_engine(components, repository, scorer)  # noqa: SLF001 - test wiring


def start_pending(
    engine: TeachingSessionEngine,
    repository: SqliteRepository,
    components: demo.Components,
    learner_id: str = LEARNER,
    *,
    session_id: str | None = None,
    goal_suffix: str = "",
) -> SessionState:
    goal = LearnerGoal(
        goal_id=f"goal.{learner_id}.{components.objective.objective_id}{goal_suffix}",
        learner_id=learner_id,
        objective_id=components.objective.objective_id,
        created_at=TS,
    )
    state = engine.start_session(
        learner_id, goal, components.objective, session_id=session_id
    )
    return drive_to_pending(engine, repository, state.session_id)


def drive_to_pending(
    engine: TeachingSessionEngine, repository: SqliteRepository, session_id: str
) -> SessionState:
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
    raise AssertionError(f"session {session_id!r} did not reach a pending item")


def events_of(repository: SqliteRepository, learner_id: str) -> list[HistoryEvent]:
    return repository.list_events(learner_id)


def snapshot_projection(repository: SqliteRepository, learner_id: str) -> dict | None:
    snapshot = repository.get_snapshot(learner_id)
    return None if snapshot is None else snapshot.to_dict()


def assert_conflict_details_are_requester_only(
    exc: ConflictError,
    *,
    learner_id: str,
    session_id: str,
    item_id: str,
    result_id: str,
    forbidden: tuple[str, ...] = (),
) -> None:
    """The structured error must not leak another scope's data or grading material."""

    details = exc.details
    assert set(details) == {"reason", "requested_scope", "policy_version"}
    assert type(details["reason"]) is str and details["reason"]
    assert details["policy_version"] == "m1b.idempotency.v1"
    scope = details["requested_scope"]
    assert scope["learner_id"] == learner_id
    assert scope["session_id"] == session_id
    assert scope["item_id"] == item_id
    assert scope["result_id"] == result_id
    assert len(scope["request_digest"]) == 64
    serialized = json.dumps(details, ensure_ascii=False, sort_keys=True)
    for marker in ("score", "max_score", "snapshot", "masteries", "failure_reason"):
        assert marker not in serialized
    for marker in forbidden:
        assert marker not in serialized


def scope_row(repository: SqliteRepository, result_id: str) -> dict | None:
    row = repository._conn.execute(  # noqa: SLF001 - white-box evidence assertion
        "SELECT result_id, learner_id, session_id, item_id, turn_index, request_digest, "
        "status, attempt_id, result_event_id, origin, created_at, updated_at "
        "FROM result_scopes WHERE result_id = ?",
        (result_id,),
    ).fetchone()
    return None if row is None else dict(row)


# ---------------------------------------------------------------------------
# I1: same scope + same digest is a zero-write idempotent replay
# ---------------------------------------------------------------------------


def test_same_token_same_response_returns_first_result_and_writes_nothing(
    components: demo.Components, tmp_path: Path
) -> None:
    repository = SqliteRepository(tmp_path / "idem.sqlite")
    scorer = ScriptedScorer()
    try:
        engine, _history = build_engine(components, repository, scorer)
        state = start_pending(engine, repository, components)
        item_id = state.pending_item_id
        assert item_id is not None

        first = engine.submit_response(
            state.session_id, item_id, "A", result_id="pr3.tok.same"
        )
        assert scorer.calls == 1
        event_count = len(events_of(repository, LEARNER))
        revision = repository.get_snapshot(LEARNER).revision  # type: ignore[union-attr]
        scope_after_first = scope_row(repository, "pr3.tok.same")
        assert scope_after_first is not None
        assert scope_after_first["status"] == "TERMINAL"
        assert scope_after_first["origin"] == "v1"

        second = engine.submit_response(
            state.session_id, item_id, "A", result_id="pr3.tok.same"
        )
        assert second.to_dict() == first.to_dict()
        assert second.learner_id == LEARNER
        assert scorer.calls == 1, "an idempotent replay must not re-invoke the scorer"
        assert len(events_of(repository, LEARNER)) == event_count
        assert repository.get_snapshot(LEARNER).revision == revision  # type: ignore[union-attr]
        assert scope_row(repository, "pr3.tok.same") == scope_after_first
        assert LearningHistory(repository).verify_rebuild(LEARNER) is True
    finally:
        repository.close()


def test_scope_and_request_digest_are_persisted_in_events_and_index(
    components: demo.Components, tmp_path: Path
) -> None:
    repository = SqliteRepository(tmp_path / "payload.sqlite")
    try:
        engine, _history = build_engine(components, repository, ScriptedScorer())
        state = start_pending(engine, repository, components)
        item_id = state.pending_item_id
        assert item_id is not None
        engine.submit_response(state.session_id, item_id, "A", result_id="pr3.tok.payload")

        expected_digest = request_digest("A")
        row = scope_row(repository, "pr3.tok.payload")
        assert row is not None
        assert row["request_digest"] == expected_digest
        assert row["learner_id"] == LEARNER
        assert row["session_id"] == state.session_id
        assert row["item_id"] == item_id
        assert row["turn_index"] == state.turn_index
        assert row["attempt_id"]

        scoped_events = [
            event
            for event in events_of(repository, LEARNER)
            if event.event_type
            in {"RESPONSE_SUBMITTED", "ASSESSMENT_PREPARED", "ASSESSED", "MASTERY_UPDATED"}
        ]
        assert scoped_events, "expected scoped assessment events"
        for event in scoped_events:
            scope = event.payload.get("scope")
            assert isinstance(scope, dict), f"{event.event_type} must carry a scope payload"
            assert scope["learner_id"] == LEARNER
            assert scope["session_id"] == state.session_id
            assert scope["item_id"] == item_id
            assert scope["result_id"] == "pr3.tok.payload"
            assert scope["request_digest"] == expected_digest
            assert scope["scope_version"] == "m1b.scope.v1"
        prepared = next(
            event for event in scoped_events if event.event_type == "ASSESSMENT_PREPARED"
        )
        assert prepared.payload["request_digest"] == expected_digest
        assert len(prepared.payload["response_digest"]) == 16
    finally:
        repository.close()


# ---------------------------------------------------------------------------
# I2: same token with different content/scope is a stable conflict
# ---------------------------------------------------------------------------


def test_same_token_different_response_conflicts_and_never_returns_old_grade(
    components: demo.Components, tmp_path: Path
) -> None:
    repository = SqliteRepository(tmp_path / "diff.sqlite")
    scorer = ScriptedScorer()
    try:
        engine, _history = build_engine(components, repository, scorer)
        state = start_pending(engine, repository, components)
        item_id = state.pending_item_id
        assert item_id is not None
        engine.submit_response(state.session_id, item_id, "A", result_id="pr3.tok.diff")
        events_before = events_of(repository, LEARNER)
        snapshot_before = snapshot_projection(repository, LEARNER)
        calls_before = scorer.calls

        with pytest.raises(ConflictError) as excinfo:
            engine.submit_response(
                state.session_id, item_id, "A (different text)", result_id="pr3.tok.diff"
            )
        assert excinfo.value.code == "IDEMPOTENCY_CONFLICT"
        assert excinfo.value.details["reason"] == "REQUEST_DIGEST_MISMATCH"
        assert_conflict_details_are_requester_only(
            excinfo.value,
            learner_id=LEARNER,
            session_id=state.session_id,
            item_id=item_id,
            result_id="pr3.tok.diff",
        )
        assert scorer.calls == calls_before
        assert events_of(repository, LEARNER) == events_before
        assert snapshot_projection(repository, LEARNER) == snapshot_before
        assert scope_row(repository, "pr3.tok.diff") is not None
    finally:
        repository.close()


def test_new_token_on_consumed_turn_is_stable_conflict(
    components: demo.Components, tmp_path: Path
) -> None:
    repository = SqliteRepository(tmp_path / "consumed.sqlite")
    try:
        engine, _history = build_engine(components, repository, ScriptedScorer())
        state = start_pending(engine, repository, components)
        item_id = state.pending_item_id
        assert item_id is not None
        engine.submit_response(state.session_id, item_id, "A", result_id="pr3.tok.first")
        events_before = events_of(repository, LEARNER)

        with pytest.raises(ConflictError) as excinfo:
            engine.submit_response(
                state.session_id, item_id, "A", result_id="pr3.tok.second"
            )
        assert excinfo.value.code == "IDEMPOTENCY_CONFLICT"
        assert excinfo.value.details["reason"] == "TURN_ALREADY_ASSESSED"
        assert_conflict_details_are_requester_only(
            excinfo.value,
            learner_id=LEARNER,
            session_id=state.session_id,
            item_id=item_id,
            result_id="pr3.tok.second",
        )
        assert events_of(repository, LEARNER) == events_before
    finally:
        repository.close()


def test_same_token_for_different_item_in_same_session_conflicts(
    components: demo.Components, tmp_path: Path
) -> None:
    repository = SqliteRepository(tmp_path / "item.sqlite")
    try:
        engine, _history = build_engine(components, repository, ScriptedScorer())
        state = start_pending(engine, repository, components)
        first_item = state.pending_item_id
        assert first_item is not None
        engine.submit_response(state.session_id, first_item, "A", result_id="pr3.tok.item")
        next_state = drive_to_pending(engine, repository, state.session_id)
        second_item = next_state.pending_item_id
        assert second_item is not None and second_item != first_item
        events_before = events_of(repository, LEARNER)
        with pytest.raises(ConflictError) as excinfo:
            engine.submit_response(
                state.session_id, second_item, "A", result_id="pr3.tok.item"
            )
        assert excinfo.value.code == "IDEMPOTENCY_CONFLICT"
        assert excinfo.value.details["reason"] in {"ITEM_MISMATCH", "TURN_MISMATCH"}
        assert events_of(repository, LEARNER) == events_before
    finally:
        repository.close()


# ---------------------------------------------------------------------------
# I3: never return another learner's/session's result
# ---------------------------------------------------------------------------


def test_cross_learner_token_replay_is_rejected_without_foreign_result_leak(
    components: demo.Components, tmp_path: Path
) -> None:
    repository = SqliteRepository(tmp_path / "cross.sqlite")
    try:
        engine_a, _ = build_engine(components, repository, ScriptedScorer())
        state_a = start_pending(engine_a, repository, components, LEARNER)
        item_a = state_a.pending_item_id
        assert item_a is not None
        result_a = engine_a.submit_response(
            state_a.session_id, item_a, "A", result_id="pr3.shared.token"
        )
        assert result_a.learner_id == LEARNER

        engine_b, _ = build_engine(components, repository, ScriptedScorer())
        state_b = start_pending(
            engine_b, repository, components, LEARNER_B, session_id="session.b.cross"
        )
        events_b_before = events_of(repository, LEARNER_B)
        snapshot_b_before = snapshot_projection(repository, LEARNER_B)
        with pytest.raises(ConflictError) as excinfo:
            engine_b.submit_response(
                state_b.session_id,
                state_b.pending_item_id,
                "A",
                result_id="pr3.shared.token",
            )
        assert excinfo.value.code == "IDEMPOTENCY_CONFLICT"
        assert excinfo.value.details["reason"] == "RESULT_ID_SCOPE_MISMATCH"
        assert_conflict_details_are_requester_only(
            excinfo.value,
            learner_id=LEARNER_B,
            session_id=state_b.session_id,
            item_id=state_b.pending_item_id,
            result_id="pr3.shared.token",
            forbidden=(LEARNER, state_a.session_id),
        )
        # Learner B's stored state is untouched and still its own.
        assert events_of(repository, LEARNER_B) == events_b_before
        assert snapshot_projection(repository, LEARNER_B) == snapshot_b_before
        assert all(
            event.learner_id == LEARNER_B
            for event in events_of(repository, LEARNER_B)
        ), "learner B must not gain foreign events"
    finally:
        repository.close()


def test_cross_session_same_learner_token_replay_conflicts(
    components: demo.Components, tmp_path: Path
) -> None:
    repository = SqliteRepository(tmp_path / "cross_session.sqlite")
    try:
        engine, _ = build_engine(components, repository, ScriptedScorer())
        state_one = start_pending(
            engine, repository, components, LEARNER, session_id="session.one"
        )
        item_one = state_one.pending_item_id
        assert item_one is not None
        engine.submit_response(state_one.session_id, item_one, "A", result_id="pr3.tok.crosssession")
        state_two = start_pending(
            engine, repository, components, LEARNER, session_id="session.two"
        )
        events_before = events_of(repository, LEARNER)
        with pytest.raises(ConflictError) as excinfo:
            engine.submit_response(
                state_two.session_id,
                state_two.pending_item_id,
                "A",
                result_id="pr3.tok.crosssession",
            )
        assert excinfo.value.code == "IDEMPOTENCY_CONFLICT"
        assert excinfo.value.details["reason"] == "RESULT_ID_SCOPE_MISMATCH"
        assert_conflict_details_are_requester_only(
            excinfo.value,
            learner_id=LEARNER,
            session_id=state_two.session_id,
            item_id=state_two.pending_item_id,
            result_id="pr3.tok.crosssession",
            forbidden=("session.one",),
        )
        assert events_of(repository, LEARNER) == events_before
    finally:
        repository.close()


def test_two_learners_with_distinct_tokens_stay_isolated(
    components: demo.Components, tmp_path: Path
) -> None:
    repository = SqliteRepository(tmp_path / "isolation.sqlite")
    try:
        engine_a, _ = build_engine(components, repository, ScriptedScorer())
        engine_b, _ = build_engine(components, repository, ScriptedScorer())
        state_a = start_pending(engine_a, repository, components, LEARNER)
        state_b = start_pending(
            engine_b, repository, components, LEARNER_B, session_id="session.b.isolation"
        )
        result_a = engine_a.submit_response(
            state_a.session_id, state_a.pending_item_id, "A", result_id="pr3.tok.a"
        )
        result_b = engine_b.submit_response(
            state_b.session_id, state_b.pending_item_id, "A", result_id="pr3.tok.b"
        )
        assert result_a.learner_id == LEARNER
        assert result_b.learner_id == LEARNER_B
        assert result_a.result_id != result_b.result_id
        assert all(
            event.learner_id == LEARNER for event in events_of(repository, LEARNER)
        )
        assert all(
            event.learner_id == LEARNER_B for event in events_of(repository, LEARNER_B)
        )
        assert scope_row(repository, "pr3.tok.a")["learner_id"] == LEARNER  # type: ignore[index]
        assert scope_row(repository, "pr3.tok.b")["learner_id"] == LEARNER_B  # type: ignore[index]
        assert LearningHistory(repository).verify_rebuild(LEARNER) is True
        assert LearningHistory(repository).verify_rebuild(LEARNER_B) is True
    finally:
        repository.close()


# ---------------------------------------------------------------------------
# I6: fail-closed validation / capability checks
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_token",
    ["", "   ", "../escape", "a" * 129, "bad/token", "bad token", "bad\ttoken", "é"],
)
def test_invalid_result_id_is_rejected_before_any_state_change(
    components: demo.Components, tmp_path: Path, bad_token: str
) -> None:
    repository = SqliteRepository(tmp_path / f"invalid-{abs(hash(bad_token))}.sqlite")
    scorer = ScriptedScorer()
    try:
        engine, _history = build_engine(components, repository, scorer)
        state = start_pending(engine, repository, components)
        events_before = events_of(repository, LEARNER)
        with pytest.raises(ValidationError) as excinfo:
            engine.submit_response(
                state.session_id, state.pending_item_id, "A", result_id=bad_token
            )
        assert excinfo.value.code == "INVALID_RESULT_ID"
        assert excinfo.value.details == {"reason": "INVALID_RESULT_ID"}
        assert scorer.calls == 0
        assert events_of(repository, LEARNER) == events_before
    finally:
        repository.close()


def test_valid_token_charset_is_accepted(
    components: demo.Components, tmp_path: Path
) -> None:
    repository = SqliteRepository(tmp_path / "charset.sqlite")
    try:
        engine, _history = build_engine(components, repository, ScriptedScorer())
        state = start_pending(engine, repository, components)
        result = engine.submit_response(
            state.session_id,
            state.pending_item_id,
            "A",
            result_id="Case.Id_1.2:@-token",
        )
        assert result.result_id == "Case.Id_1.2:@-token"
        assert scope_row(repository, "Case.Id_1.2:@-token") is not None
    finally:
        repository.close()


def test_caller_learner_mismatch_fails_closed_before_scoped_read(
    components: demo.Components, tmp_path: Path
) -> None:
    repository = SqliteRepository(tmp_path / "caller.sqlite")
    scorer = ScriptedScorer()
    try:
        engine, _history = build_engine(components, repository, scorer)
        state = start_pending(engine, repository, components, LEARNER)
        events_before = events_of(repository, LEARNER)
        with pytest.raises(ConflictError) as excinfo:
            engine.submit_response(
                state.session_id,
                state.pending_item_id,
                "A",
                result_id="pr3.tok.caller",
                caller_learner_id=LEARNER_B,
            )
        assert excinfo.value.code == "CONFLICT"
        assert excinfo.value.details == {"reason": "CALLER_LEARNER_MISMATCH"}
        assert LEARNER not in json.dumps(excinfo.value.details)
        assert scorer.calls == 0
        assert events_of(repository, LEARNER) == events_before

        # The correct trusted-caller assertion still works end to end.
        result = engine.submit_response(
            state.session_id,
            state.pending_item_id,
            "A",
            result_id="pr3.tok.caller",
            caller_learner_id=LEARNER,
        )
        assert result.learner_id == LEARNER
    finally:
        repository.close()


def test_missing_scoped_extension_fails_closed_for_explicit_tokens(
    components: demo.Components, tmp_path: Path
) -> None:
    inner = SqliteRepository(tmp_path / "unsupported.sqlite")

    class BlockedScopedRepository:
        _BLOCKED = {"find_result_in_scope", "find_scope_owner", "get_event_for_learner"}

        def __init__(self, wrapped: SqliteRepository) -> None:
            self._inner = wrapped

        def __getattr__(self, name: str):  # noqa: ANN401 - transparent delegation
            if name in self._BLOCKED:
                raise AttributeError(name)
            return getattr(self._inner, name)

    repository = BlockedScopedRepository(inner)
    try:
        engine, _ = build_engine(components, repository, ScriptedScorer())
        assert engine.supports_scoped_idempotency is False
        state = start_pending(engine, repository, components)
        with pytest.raises(Exception) as excinfo:  # noqa: BLE001 - code asserted below
            engine.submit_response(
                state.session_id, state.pending_item_id, "A", result_id="pr3.tok.unsupported"
            )
        assert getattr(excinfo.value, "code", "") == "IDEMPOTENCY_UNSUPPORTED"
    finally:
        inner.close()


# ---------------------------------------------------------------------------
# Prepared-window retries: at-least-once scorer, exactly-once state
# ---------------------------------------------------------------------------


def test_prepared_attempt_retry_same_token_resumes_without_duplicate_mastery(
    components: demo.Components, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = SqliteRepository(tmp_path / "prepare_window.sqlite")
    scorer = ScriptedScorer()
    try:
        engine, history = build_engine(components, repository, scorer)
        state = start_pending(engine, repository, components)
        item_id = state.pending_item_id
        assert item_id is not None
        original_commit = engine._commit_result_turn  # noqa: SLF001 - simulated interruption

        def interrupt(*args, **kwargs):  # noqa: ANN002, ANN003 - test double
            raise RuntimeError("simulated interruption between transaction A and B")

        monkeypatch.setattr(engine, "_commit_result_turn", interrupt)
        with pytest.raises(RuntimeError):
            engine.submit_response(
                state.session_id, item_id, "A", result_id="pr3.tok.window"
            )
        prepared_events = [
            event
            for event in events_of(repository, LEARNER)
            if event.event_type == "ASSESSMENT_PREPARED"
        ]
        assert len(prepared_events) == 1
        assert not any(
            event.event_type in {"ASSESSED", "ERROR", "MASTERY_UPDATED"}
            for event in events_of(repository, LEARNER)
        )
        monkeypatch.setattr(engine, "_commit_result_turn", original_commit)
        calls_before = scorer.calls

        # A different token must not silently become a second scoring attempt.
        with pytest.raises(ConflictError) as excinfo:
            engine.submit_response(
                state.session_id, item_id, "A", result_id="pr3.tok.window.other"
            )
        assert excinfo.value.code == "IDEMPOTENCY_CONFLICT"
        assert excinfo.value.details["reason"] == "TURN_ALREADY_ASSESSED"
        assert scorer.calls == calls_before

        # Same token resumes the durable attempt and applies the turn once.
        result = engine.submit_response(
            state.session_id, item_id, "A", result_id="pr3.tok.window"
        )
        assert result.result_id == "pr3.tok.window"
        assert scorer.calls == calls_before + 1
        assessed = [
            event
            for event in events_of(repository, LEARNER)
            if event.event_type == "ASSESSED"
        ]
        assert len(assessed) == 1
        assert repository.get_snapshot(LEARNER).revision == 1  # type: ignore[union-attr]
        assert history.verify_rebuild(LEARNER) is True
    finally:
        repository.close()


# ---------------------------------------------------------------------------
# Repository-level atomicity: scope conflict rolls the whole turn back
# ---------------------------------------------------------------------------


def test_scope_conflict_rolls_back_events_and_session(
    components: demo.Components, tmp_path: Path
) -> None:
    repository = SqliteRepository(tmp_path / "rollback.sqlite")
    try:
        engine, _ = build_engine(components, repository, ScriptedScorer())
        state = start_pending(engine, repository, components)
        item_id = state.pending_item_id
        assert item_id is not None
        engine.submit_response(state.session_id, item_id, "A", result_id="pr3.tok.rollback")
        current = repository.load_session(state.session_id)
        assert current is not None
        events_before = events_of(repository, LEARNER)
        session_before = current.to_dict()
        scope_rows_before = repository._conn.execute(  # noqa: SLF001 - white-box
            "SELECT COUNT(*) FROM result_scopes"
        ).fetchone()[0]

        conflicting_event = HistoryEvent(
            event_id="evt.assessed.pr3.conflict.1",
            learner_id=LEARNER,
            session_id=state.session_id,
            seq=(events_before[-1].seq + 1) if events_before else 0,
            event_type="ASSESSED",
            payload={
                "result_id": "pr3.tok.rollback",
                "item_id": item_id,
                "status": "CORRECT",
                "result": ScriptedScorer().score(
                    components.adapter.assessment_items()[0], LEARNER, "A"
                ).to_dict(),
            },
            created_at=TS,
        )
        conflicting_scope = ResultScope(
            learner_id=LEARNER,
            session_id=state.session_id,
            item_id="different.item",
            turn_index=current.turn_index,
            result_id="pr3.tok.rollback",
            request_digest="0" * 64,
        )
        next_session = replace(
            current, turn_index=current.turn_index + 1, updated_at="2026-11-20T00:00:01Z"
        )
        with pytest.raises(ConflictError) as excinfo:
            repository.commit_teaching_turn(
                learner_id=LEARNER,
                session_id=state.session_id,
                expected_session_version=session_version(current),
                events=[conflicting_event],
                next_session=next_session,
                scope=conflicting_scope,
            )
        assert excinfo.value.code == "IDEMPOTENCY_CONFLICT"
        assert excinfo.value.details["reason"] in {"ITEM_MISMATCH", "REQUEST_DIGEST_MISMATCH"}
        assert events_of(repository, LEARNER) == events_before
        reloaded = repository.load_session(state.session_id)
        assert reloaded is not None and reloaded.to_dict() == session_before
        assert (
            repository._conn.execute(  # noqa: SLF001 - white-box
                "SELECT COUNT(*) FROM result_scopes"
            ).fetchone()[0]
            == scope_rows_before
        )
    finally:
        repository.close()


# ---------------------------------------------------------------------------
# I4/I5: concurrent same-token writers converge on one terminal result
# ---------------------------------------------------------------------------


def test_concurrent_same_token_same_response_converges(tmp_path: Path) -> None:
    db_path = tmp_path / "concurrent.sqlite"
    setup = setup_pending(db_path)
    barrier = tmp_path / "barrier"
    command = child_command(
        db_path=db_path,
        session_id=setup.session_id,
        item_id=setup.item_id,
        response="A",
        mode="submit",
        result_id="pr3.tok.concurrent",
        wait_file=barrier,
    )
    processes = [
        subprocess.Popen(
            command,
            cwd=str(REPO_ROOT),
            env=child_env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for _ in range(2)
    ]
    time.sleep(0.4)
    barrier.write_text("go", encoding="utf-8")
    outputs = [process.communicate(timeout=120) for process in processes]
    for process, (stdout, stderr) in zip(processes, outputs):
        assert process.returncode == 0, stdout + stderr
        payload = json.loads(stdout)
        assert payload["result"]["result_id"] == "pr3.tok.concurrent"
        assert payload["result"]["learner_id"] == "m1b.crash.learner"
    summary = db_summary(db_path, setup.session_id)
    assert summary["terminal_results"] == 1, "exactly one terminal result may be committed"
    assert summary["event_types"].get("ASSESSED") == 1
    assert summary["event_types"].get("MASTERY_UPDATED") == 1
    assert summary["snapshot_revision"] == 1
    assert summary["verify_rebuild"] is True
    repository = SqliteRepository(db_path)
    try:
        rows = repository._conn.execute(  # noqa: SLF001 - white-box evidence
            "SELECT result_id, status, COUNT(*) FROM result_scopes GROUP BY result_id, status"
        ).fetchall()
        assert [tuple(row) for row in rows] == [("pr3.tok.concurrent", "TERMINAL", 1)]
    finally:
        repository.close()


# ---------------------------------------------------------------------------
# T-5: EVAL_ERROR retries stay scoped (same result, zero extra events)
# ---------------------------------------------------------------------------


def test_eval_error_retry_is_scoped_and_zero_extra_events(
    components: demo.Components, tmp_path: Path
) -> None:
    repository = SqliteRepository(tmp_path / "eval_error.sqlite")
    scorer = ScriptedScorer(status="EVAL_ERROR")
    try:
        engine, history = build_engine(components, repository, scorer)
        state = start_pending(engine, repository, components)
        item_id = state.pending_item_id
        assert item_id is not None
        first = engine.submit_response(
            state.session_id, item_id, "A", result_id="pr3.tok.evalerror"
        )
        assert first.status == "EVAL_ERROR"
        events_after_first = events_of(repository, LEARNER)
        snapshot_after_first = snapshot_projection(repository, LEARNER)
        calls_after_first = scorer.calls
        # Same token + same response: the stored EVAL_ERROR result is returned,
        # no re-scoring and no new terminal/mastery event.
        second = engine.submit_response(
            state.session_id, item_id, "A", result_id="pr3.tok.evalerror"
        )
        assert second.to_dict() == first.to_dict()
        assert scorer.calls == calls_after_first
        assert events_of(repository, LEARNER) == events_after_first
        assert snapshot_projection(repository, LEARNER) == snapshot_after_first
        assert not any(
            event.event_type == "ASSESSED" for event in events_after_first
        ), "EVAL_ERROR must be recorded as ERROR, never as mastery evidence"
        assert any(event.event_type == "ERROR" for event in events_after_first)
        assert history.verify_rebuild(LEARNER) is True
    finally:
        repository.close()


# ---------------------------------------------------------------------------
# T-14: static isolation checks (no unscoped result read / no network)
# ---------------------------------------------------------------------------


def test_no_unscoped_result_lookup_in_engine_source() -> None:
    """Result-reading helpers must use learner-filtered reads, never ``get_event``."""

    source = engine_module.__file__
    assert source is not None
    tree = ast.parse(Path(source).read_text(encoding="utf-8"))
    scoped_helpers = {
        "_lookup_result_for_scope",
        "_lookup_scope_turn_tolerant",
        "_lookup_legacy_default_result",
        "_legacy_result_from_owner",
        "_legacy_event_lookup",
        "_legacy_response_digest",
        "_result_from_terminal_event",
    }
    offending: list[tuple[str, int]] = []

    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self._stack: list[str] = []

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self._stack.append(node.name)
            self.generic_visit(node)
            self._stack.pop()

        def visit_Call(self, node: ast.Call) -> None:
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "get_event":
                enclosing = self._stack[-1] if self._stack else ""
                if enclosing in scoped_helpers:
                    offending.append((enclosing, node.lineno))
            self.generic_visit(node)

    Visitor().visit(tree)
    assert not offending, f"scoped result helpers must not call get_event(): {offending}"
    # The scoped lookup must actually use the repository extension + learner filter.
    scoped_source = Path(source).read_text(encoding="utf-8")
    assert "find_result_in_scope(" in scoped_source
    assert "find_scope_owner(" in scoped_source
    assert "get_event_for_learner(" in scoped_source
    # The optional non-scoped legacy fallback is the only attempt read allowed to
    # use the global accessor, and it never returns an AssessmentResult.
    prepared_source = scoped_source.split("def _prepared_payload", 1)[1].split(
        "def _decode_prepared", 1
    )[0]
    assert "get_event_for_learner(" in prepared_source
    assert "AssessmentResult" not in prepared_source


def test_idempotency_module_is_pure_and_offline() -> None:
    import m1_teacher.idempotency as idempotency_module

    source = Path(idempotency_module.__file__).read_text(encoding="utf-8")  # type: ignore[arg-type]
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert not (
        imported
        & {
            "socket",
            "ssl",
            "requests",
            "httpx",
            "urllib",
            "http",
            "subprocess",
            "os",
            "sqlite3",
        }
    ), f"idempotency helpers must stay pure/offline (imports: {sorted(imported)})"


# ---------------------------------------------------------------------------
# T-10: concurrent same token across learners has exactly one winner
# ---------------------------------------------------------------------------


def test_concurrent_cross_learner_same_token_single_winner(tmp_path: Path) -> None:
    db_path = tmp_path / "cross_concurrent.sqlite"
    setup_a = setup_pending(db_path, learner_id=LEARNER, session_suffix=".a")
    setup_b = setup_pending(
        db_path, learner_id=LEARNER_B, session_suffix=".b", explicit_session_id="session.race.b"
    )
    barrier = tmp_path / "race_barrier"
    command_a = child_command(
        db_path=db_path,
        session_id=setup_a.session_id,
        item_id=setup_a.item_id,
        response="A",
        mode="submit",
        result_id="pr3.tok.race",
        wait_file=barrier,
        learner_id=LEARNER,
    )
    command_b = child_command(
        db_path=db_path,
        session_id=setup_b.session_id,
        item_id=setup_b.item_id,
        response="A",
        mode="submit",
        result_id="pr3.tok.race",
        wait_file=barrier,
        learner_id=LEARNER_B,
    )
    processes = [
        subprocess.Popen(
            command,
            cwd=str(REPO_ROOT),
            env=child_env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for command in (command_a, command_b)
    ]
    time.sleep(0.4)
    barrier.write_text("go", encoding="utf-8")
    results = [process.communicate(timeout=120) for process in processes]
    parsed: list[dict] = []
    for process, (stdout, _stderr) in zip(processes, results):
        payload = json.loads(stdout)
        assert process.returncode in (0, 3), stdout
        parsed.append(payload)
    winners = [payload for payload in parsed if "result" in payload]
    losers = [payload for payload in parsed if "error" in payload]
    assert len(winners) == 1, parsed
    assert len(losers) == 1, parsed
    assert losers[0]["code"] == "IDEMPOTENCY_CONFLICT"
    winner_result = winners[0]["result"]
    winner_learner = winner_result["learner_id"]
    loser_learner = LEARNER_B if winner_learner == LEARNER else LEARNER
    assert winner_learner in {LEARNER, LEARNER_B}
    # Cross-learner loser gets a scoped conflict (never the winner's result).
    assert losers[0]["code"] == "IDEMPOTENCY_CONFLICT"
    repository = SqliteRepository(db_path)
    try:
        rows = [
            tuple(row)
            for row in repository._conn.execute(  # noqa: SLF001 - white-box evidence
                "SELECT result_id, learner_id, status FROM result_scopes"
            ).fetchall()
        ]
        assert rows == [("pr3.tok.race", winner_learner, "TERMINAL")]
        other_events = repository.list_events(loser_learner)
        assert not any(
            event.event_type in {"ASSESSED", "MASTERY_UPDATED"} for event in other_events
        ), "the losing learner must not receive assessment events"
        winner_events = repository.list_events(winner_learner)
        assessed = [
            event for event in winner_events if event.event_type == "ASSESSED"
        ]
        assert len(assessed) == 1
        assert LearningHistory(repository).verify_rebuild(LEARNER) is True
    finally:
        repository.close()
