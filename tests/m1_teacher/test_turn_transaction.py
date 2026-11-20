"""Unit/integration tests for the B-NEXT atomic teaching-turn commit API.

These tests exercise :meth:`SqliteRepository.commit_teaching_turn` directly
(compare-and-swap session version, duplicate/seq/ snapshot conflicts, transition
validation, rollback) and the transactional ``submit_response`` pipeline
(A -> external scorer -> B), including the recovery algorithm on deterministically
simulated interruptions.

Real ``SIGKILL`` crash evidence lives in ``test_crash_recovery.py``; this module
uses in-process *interruption* only for fast, focused recovery-algorithm tests
and never claims those interruptions are process crashes.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from m1_teacher import demo
from m1_teacher.contracts.errors import (
    ConflictError,
    NotFoundError,
    UnsupportedOperationError,
    ValidationError,
)
from m1_teacher.contracts.types import (
    AssessmentItem,
    AssessmentResult,
    HistoryEvent,
    LearnerGoal,
    SessionState,
)
from m1_teacher.learner.history import EventDraft, LearningHistory
from m1_teacher.learner.repository import SqliteRepository, session_version
from m1_teacher.session.engine import TeachingSessionEngine

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "fixtures" / "m1_teacher"
LEARNER = "m1b.txn.learner"
TS = demo.FIXED_TIMESTAMP


# ---------------------------------------------------------------------------
# Components / scorer doubles
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def components() -> demo.Components:
    return demo.build_components(FIXTURES)


def make_goal(learner_id: str, components: demo.Components, suffix: str = "") -> LearnerGoal:
    return LearnerGoal(
        goal_id=f"goal.{learner_id}.{components.objective.objective_id}{suffix}",
        learner_id=learner_id,
        objective_id=components.objective.objective_id,
        created_at=TS,
    )


class ScriptedScorer:
    """Deterministic test scorer (MOCK outcome source, deterministic result ids)."""

    scorer_id = "m1b.test.scripted.v0"

    def __init__(self, status: str = "CORRECT", *, raising: bool = False) -> None:
        self.status = status
        self.raising = raising
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
        if self.raising:
            raise RuntimeError("scripted scorer infrastructure failure")
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


class MismatchedResultIdScorer(ScriptedScorer):
    """Deterministic scorer whose re-score returns a different result_id."""

    scorer_id = "m1b.test.mismatch.v0"

    def score(self, item, learner_id, response, *, result_id=None):  # noqa: ANN001
        self.calls += 1
        return AssessmentResult(
            result_id=f"mismatch:{item.item_id}:{self.calls:03d}",
            item_id=item.item_id,
            learner_id=learner_id,
            status="CORRECT",
            score=float(item.max_score),
            max_score=float(item.max_score),
            scorer_id=self.scorer_id,
            created_at=TS,
        )


def build_engine(
    components: demo.Components,
    repository: SqliteRepository,
    scorer: object,
) -> tuple[TeachingSessionEngine, LearningHistory]:
    return demo._make_engine(components, repository, scorer)  # noqa: SLF001 - test wiring


def start_and_drive_to_pending(
    engine: TeachingSessionEngine,
    repository: SqliteRepository,
    components: demo.Components,
    learner_id: str = LEARNER,
    *,
    session_id: str | None = None,
    goal_suffix: str = "",
) -> SessionState:
    goal = make_goal(learner_id, components, goal_suffix)
    state = engine.start_session(
        learner_id, goal, components.objective, session_id=session_id
    )
    sid = state.session_id
    for _ in range(40):
        state = repository.load_session(sid)
        if state.pending_item_id is not None:
            return state
        if state.phase in {"COMPLETE", "PAUSED"}:
            raise AssertionError(f"session reached {state.phase} before a pending item")
        action = engine.current_action(sid)
        if action.item_id is None:
            engine.advance_session(sid)
    raise AssertionError("session did not reach a pending item")


def interrupt_after_prepare(
    engine: TeachingSessionEngine,
    session_id: str,
    item_id: str,
    response: str = "A",
    *,
    result_id: str | None = None,
) -> None:
    """Deterministically simulate a crash in the external-scoring window.

    Transaction A has committed; the scorer call is interrupted before
    transaction B.  This is explicitly an *in-process interruption* helper; the
    real ``SIGKILL`` matrices are in ``test_crash_recovery.py``.
    """

    original = engine._score_safely  # noqa: SLF001 - deliberate test seam

    def _interrupted(*_args, **_kwargs):  # noqa: ANN002, ANN003
        raise RuntimeError("simulated interruption between transaction A and B")

    engine._score_safely = _interrupted  # type: ignore[method-assign]  # noqa: SLF001
    try:
        with pytest.raises(RuntimeError):
            engine.submit_response(
                session_id, item_id, response, result_id=result_id
            )
    finally:
        engine._score_safely = original  # type: ignore[method-assign]  # noqa: SLF001


def materialize(
    repository: SqliteRepository,
    learner_id: str,
    session_id: str,
    drafts: list[EventDraft],
) -> list[HistoryEvent]:
    start = max((event.seq for event in repository.list_events(learner_id)), default=-1) + 1
    return [
        draft.materialize(learner_id=learner_id, session_id=session_id, seq=start + offset)
        for offset, draft in enumerate(drafts)
    ]


def prepared_drafts(
    state: SessionState,
    item: AssessmentItem,
    response: str,
    result_id: str,
) -> list[EventDraft]:
    canonical = response
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    version = session_version(state)
    return [
        EventDraft(
            event_id=f"evt.responsesubmitted.test.{item.item_id}",
            event_type="RESPONSE_SUBMITTED",
            payload={
                "item_id": item.item_id,
                "result_id": result_id,
                "response_digest": digest,
                "response_kind": "text",
                "attempt": state.turn_index,
                "session_version": version,
            },
            created_at=TS,
        ),
        EventDraft(
            event_id=f"evt.assessmentprepared.test.{item.item_id}",
            event_type="ASSESSMENT_PREPARED",
            payload={
                "attempt_id": f"attempt:test:{item.item_id}",
                "learner_id": state.learner_id,
                "session_id": state.session_id,
                "item_id": item.item_id,
                "turn_index": state.turn_index,
                "result_id": result_id,
                "response_digest": digest,
                "response_kind": "text",
                "canonical_response": canonical,
                "session_version": version,
            },
            created_at=TS,
        ),
    ]


def assert_invariants(
    repository: SqliteRepository,
    components: demo.Components,
    learner_id: str,
    session_id: str,
    *,
    seed_evidence: dict[str, int] | None = None,
    verify_rebuild: bool = True,
) -> None:
    events = repository.list_events(learner_id)
    seqs = [event.seq for event in events]
    assert seqs == sorted(seqs)
    assert len(seqs) == len(set(seqs))
    for event in events:
        assert event.learner_id == learner_id
    state = repository.load_session(session_id)
    assert state is not None and state.learner_id == learner_id
    snapshot = repository.get_snapshot(learner_id)
    history = LearningHistory(repository)
    if verify_rebuild:
        assert history.verify_rebuild(learner_id) is True
    prepared = [event for event in events if event.event_type == "ASSESSMENT_PREPARED"]
    terminal_ids = {
        event.payload.get("result_id")
        for event in events
        if event.event_type in {"ASSESSED", "ERROR"}
    }
    unresolved = [
        event for event in prepared if event.payload.get("result_id") not in terminal_ids
    ]
    if state.pending_item_id is None:
        assert unresolved == [], "pending=None with an unresolved PREPARED attempt"
    if snapshot is not None:
        items = {item.item_id: item for item in components.adapter.assessment_items()}
        expected: dict[str, int] = dict(seed_evidence or {})
        for event in events:
            if event.event_type != "ASSESSED":
                continue
            if event.payload.get("status") not in {"CORRECT", "INCORRECT", "PARTIAL"}:
                continue
            for node_id in items[event.payload["item_id"]].node_ids:
                expected[node_id] = expected.get(node_id, 0) + 1
        assert {
            node_id: estimate.evidence_count
            for node_id, estimate in snapshot.masteries.items()
        } == expected


# ---------------------------------------------------------------------------
# session_version (CAS digest)
# ---------------------------------------------------------------------------


def test_session_version_is_content_digest_with_documented_algorithm() -> None:
    state = SessionState(
        session_id="session.s",
        learner_id="learner.l",
        goal_id="goal.g",
        objective_id="obj.o",
        phase="REVIEW",
        turn_index=3,
        pending_item_id="item.x",
        created_at=TS,
        updated_at=TS,
    )
    canonical = json.dumps(
        state.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    assert session_version(state) == expected
    assert len(session_version(state)) == 16
    # Same content, reparsed round-trip: identical digest.
    assert session_version(SessionState.from_dict(state.to_dict())) == expected
    # Any content change changes the digest (CAS).
    assert session_version(replace(state, turn_index=4)) != expected
    assert session_version(replace(state, pending_item_id=None)) != expected
    assert session_version(replace(state, phase="TEACH")) != expected
    with pytest.raises(ValidationError):
        session_version({"session_id": "x"})  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# commit_teaching_turn: success + atomic rollback
# ---------------------------------------------------------------------------


def test_commit_teaching_turn_commits_events_snapshot_goal_and_session(
    components: demo.Components, tmp_path: Path
) -> None:
    repository = SqliteRepository(tmp_path / "commit.db")
    try:
        scorer = ScriptedScorer()
        engine, history = build_engine(components, repository, scorer)
        state = start_and_drive_to_pending(engine, repository, components)
        item = engine._items_by_id[state.pending_item_id]  # noqa: SLF001
        result_id = "result.commit.1"
        drafts = prepared_drafts(state, item, "A", result_id)
        version = session_version(state)
        next_state = replace(state, updated_at="2026-11-20T00:00:01Z")
        flags = repository.commit_teaching_turn(
            learner_id=LEARNER,
            session_id=state.session_id,
            expected_session_version=version,
            events=materialize(repository, LEARNER, state.session_id, drafts),
            snapshot=None,
            next_session=next_state,
            goal=None,
        )
        assert flags == [True, True]
        prepared = [
            event
            for event in repository.list_events(LEARNER)
            if event.event_type == "ASSESSMENT_PREPARED"
        ]
        assert len(prepared) == 1
        assert session_version(repository.load_session(state.session_id)) != version

        # Transaction B: terminal events + snapshot + goal + next session.
        current = repository.load_session(state.session_id)
        snapshot = engine._current_snapshot(LEARNER)  # noqa: SLF001
        result = scorer.score(item, LEARNER, "A", result_id=result_id)
        c_drafts, updated, mutated = history.assessment_event_drafts(
            LEARNER, state.session_id, item, result, snapshot
        )
        assert mutated is True
        goal = replace(
            repository.get_goal(state.goal_id), status="COMPLETED"
        )
        terminal = SessionState(
            session_id=current.session_id,
            learner_id=current.learner_id,
            goal_id=current.goal_id,
            objective_id=current.objective_id,
            phase="REVIEW",
            turn_index=current.turn_index + 1,
            pending_item_id=None,
            created_at=current.created_at,
            updated_at="2026-11-20T00:00:02Z",
        )
        flags = repository.commit_teaching_turn(
            learner_id=LEARNER,
            session_id=current.session_id,
            expected_session_version=session_version(current),
            events=materialize(repository, LEARNER, current.session_id, c_drafts),
            snapshot=updated,
            next_session=terminal,
            goal=goal,
        )
        assert flags == [True, True]
        persisted = repository.get_snapshot(LEARNER)
        assert persisted is not None and persisted.to_dict() == updated.to_dict()
        load = repository.load_session(current.session_id)
        assert load is not None
        assert load.turn_index == current.turn_index + 1
        assert load.pending_item_id is None
        assert repository.get_goal(state.goal_id).status == "COMPLETED"
        assert history.verify_rebuild(LEARNER) is True
    finally:
        repository.close()


def test_commit_rolls_back_all_writes_on_snapshot_conflict(
    components: demo.Components, tmp_path: Path
) -> None:
    repository = SqliteRepository(tmp_path / "rollback.db")
    try:
        scorer = ScriptedScorer()
        engine, history = build_engine(components, repository, scorer)
        state = start_and_drive_to_pending(engine, repository, components)
        item = engine._items_by_id[state.pending_item_id]  # noqa: SLF001
        repository.ensure_learner(LEARNER, created_at=TS)
        newer = engine._current_snapshot(LEARNER)  # noqa: SLF001
        from m1_teacher.contracts.types import MasteryEstimate

        seeded = replace(
            newer,
            revision=3,
            masteries={
                "cf.array.basics": MasteryEstimate(
                    node_id="cf.array.basics",
                    value=0.5,
                    confidence=0.5,
                    evidence_count=2,
                    created_at=TS,
                    updated_at=TS,
                )
            },
            updated_at=TS,
        )
        repository.upsert_snapshot(seeded)
        result = scorer.score(item, LEARNER, "A", result_id="result.rollback")
        c_drafts, _updated, _mutated = history.assessment_event_drafts(
            LEARNER, state.session_id, item, result, seeded
        )
        stale_snapshot = replace(seeded, revision=2)
        terminal = replace(
            state,
            phase="REVIEW",
            turn_index=state.turn_index + 1,
            pending_item_id=None,
            updated_at="2026-11-20T00:00:02Z",
        )
        events_before = len(repository.list_events(LEARNER))
        events = materialize(repository, LEARNER, state.session_id, c_drafts)
        # The prepared attempt is not required for this test; the snapshot
        # conflict must roll back the already-inserted terminal events and the
        # session write (validation order: events -> snapshot -> session).
        with pytest.raises(ConflictError) as excinfo:
            repository.commit_teaching_turn(
                learner_id=LEARNER,
                session_id=state.session_id,
                expected_session_version=session_version(state),
                events=events,
                snapshot=stale_snapshot,
                next_session=terminal,
                goal=None,
            )
        assert excinfo.value.code == "SNAPSHOT_REVISION_CONFLICT"
        assert len(repository.list_events(LEARNER)) == events_before
        load = repository.load_session(state.session_id)
        assert load is not None and load.to_dict() == state.to_dict()
        assert repository.get_snapshot(LEARNER).revision == 3
    finally:
        repository.close()


# ---------------------------------------------------------------------------
# commit_teaching_turn: fail-closed conflict codes
# ---------------------------------------------------------------------------


def test_commit_session_version_cas_conflict(
    components: demo.Components, tmp_path: Path
) -> None:
    repository = SqliteRepository(tmp_path / "cas.db")
    try:
        engine, _history = build_engine(components, repository, ScriptedScorer())
        state = start_and_drive_to_pending(engine, repository, components)
        item = engine._items_by_id[state.pending_item_id]  # noqa: SLF001
        drafts = prepared_drafts(state, item, "A", "result.cas")
        events = materialize(repository, LEARNER, state.session_id, drafts)
        with pytest.raises(ConflictError) as excinfo:
            repository.commit_teaching_turn(
                learner_id=LEARNER,
                session_id=state.session_id,
                expected_session_version="0" * 16,
                events=events,
                snapshot=None,
                next_session=replace(state, updated_at="2026-11-20T00:00:01Z"),
                goal=None,
            )
        assert excinfo.value.code == "SESSION_VERSION_CONFLICT"
        assert all(event.event_type != "ASSESSMENT_PREPARED" for event in repository.list_events(LEARNER))
        assert repository.load_session(state.session_id).to_dict() == state.to_dict()
    finally:
        repository.close()


def test_commit_duplicate_event_and_seq_conflict_codes(
    components: demo.Components, tmp_path: Path
) -> None:
    repository = SqliteRepository(tmp_path / "dup.db")
    try:
        engine, _history = build_engine(components, repository, ScriptedScorer())
        state = start_and_drive_to_pending(engine, repository, components)
        item = engine._items_by_id[state.pending_item_id]  # noqa: SLF001
        drafts = prepared_drafts(state, item, "A", "result.dup")
        events = materialize(repository, LEARNER, state.session_id, drafts)
        version = session_version(state)
        next_state = replace(state, updated_at="2026-11-20T00:00:01Z")
        repository.commit_teaching_turn(
            learner_id=LEARNER,
            session_id=state.session_id,
            expected_session_version=version,
            events=events,
            snapshot=None,
            next_session=next_state,
            goal=None,
        )
        current = repository.load_session(state.session_id)
        current_version = session_version(current)
        events_before_duplicate = len(repository.list_events(LEARNER))
        # Same deterministic event ids again -> DUPLICATE_EVENT (fail closed).
        duplicate_events = materialize(repository, LEARNER, state.session_id, drafts)
        with pytest.raises(ConflictError) as excinfo:
            repository.commit_teaching_turn(
                learner_id=LEARNER,
                session_id=state.session_id,
                expected_session_version=current_version,
                events=duplicate_events,
                snapshot=None,
                next_session=replace(current, updated_at="2026-11-20T00:00:02Z"),
                goal=None,
            )
        assert excinfo.value.code == "DUPLICATE_EVENT"
        assert len(repository.list_events(LEARNER)) == events_before_duplicate
        # Fresh event id on an already-used seq -> EVENT_SEQ_CONFLICT.
        conflict_event = HistoryEvent(
            event_id="evt.seq.conflict",
            learner_id=LEARNER,
            session_id=state.session_id,
            seq=0,
            event_type="ACTION_TAKEN",
            payload={"phase": "REVIEW"},
            created_at=TS,
        )
        with pytest.raises(ConflictError) as excinfo:
            repository.commit_teaching_turn(
                learner_id=LEARNER,
                session_id=state.session_id,
                expected_session_version=current_version,
                events=[conflict_event],
                snapshot=None,
                next_session=replace(current, updated_at="2026-11-20T00:00:03Z"),
                goal=None,
            )
        assert excinfo.value.code == "EVENT_SEQ_CONFLICT"
        assert repository.load_session(state.session_id).to_dict() == current.to_dict()
    finally:
        repository.close()


def test_commit_rejects_cross_learner_session_and_unknown_ids(
    components: demo.Components, tmp_path: Path
) -> None:
    repository = SqliteRepository(tmp_path / "scope.db")
    try:
        engine, _history = build_engine(components, repository, ScriptedScorer())
        state = start_and_drive_to_pending(engine, repository, components)
        item = engine._items_by_id[state.pending_item_id]  # noqa: SLF001
        drafts = prepared_drafts(state, item, "A", "result.scope")
        events = materialize(repository, LEARNER, state.session_id, drafts)
        events_before = len(repository.list_events(LEARNER))
        # Unknown session (events belong to the requested, unknown session id).
        unknown_session = "session.does.not.exist"
        with pytest.raises(NotFoundError):
            repository.commit_teaching_turn(
                learner_id=LEARNER,
                session_id=unknown_session,
                expected_session_version=session_version(state),
                events=[
                    replace(event, session_id=unknown_session) for event in events
                ],
                snapshot=None,
                next_session=replace(state, session_id=unknown_session),
                goal=None,
            )
        # Another learner claims the session.
        other = "m1b.txn.other"
        repository.ensure_learner(other, created_at=TS)
        with pytest.raises(ConflictError) as excinfo:
            repository.commit_teaching_turn(
                learner_id=other,
                session_id=state.session_id,
                expected_session_version=session_version(state),
                events=[
                    replace(event, learner_id=other) for event in events
                ],
                snapshot=None,
                next_session=replace(state, learner_id=other),
                goal=None,
            )
        assert excinfo.value.code == "SESSION_OWNER_CONFLICT"
        # Event/session mismatch is rejected before any write.
        with pytest.raises(ValidationError):
            repository.commit_teaching_turn(
                learner_id=LEARNER,
                session_id=state.session_id,
                expected_session_version=session_version(state),
                events=[replace(events[0], session_id="other.session")],
                snapshot=None,
                next_session=replace(state, updated_at="2026-11-20T00:00:01Z"),
                goal=None,
            )
        # next_session identity mismatch is rejected.
        with pytest.raises(ValidationError):
            repository.commit_teaching_turn(
                learner_id=LEARNER,
                session_id=state.session_id,
                expected_session_version=session_version(state),
                events=events,
                snapshot=None,
                next_session=replace(state, learner_id="someone.else"),
                goal=make_goal("someone.else", components),
            )
        assert len(repository.list_events(LEARNER)) == events_before
    finally:
        repository.close()


def test_commit_rejects_invalid_transitions_and_orphan_prepared(
    components: demo.Components, tmp_path: Path
) -> None:
    repository = SqliteRepository(tmp_path / "transition.db")
    try:
        engine, _history = build_engine(components, repository, ScriptedScorer())
        state = start_and_drive_to_pending(engine, repository, components)
        item = engine._items_by_id[state.pending_item_id]  # noqa: SLF001
        drafts = prepared_drafts(state, item, "A", "result.transition")
        version = session_version(state)
        repository.commit_teaching_turn(
            learner_id=LEARNER,
            session_id=state.session_id,
            expected_session_version=version,
            events=materialize(repository, LEARNER, state.session_id, drafts),
            snapshot=None,
            next_session=replace(state, updated_at="2026-11-20T00:00:01Z"),
            goal=None,
        )
        current = repository.load_session(state.session_id)
        current_version = session_version(current)
        terminal_event = HistoryEvent(
            event_id="evt.assessed.fake",
            learner_id=LEARNER,
            session_id=state.session_id,
            seq=len(repository.list_events(LEARNER)),
            event_type="ASSESSED",
            payload={"result_id": "fake", "item_id": item.item_id, "status": "CORRECT"},
            created_at=TS,
        )
        # A terminal commit must advance the turn by exactly one.
        with pytest.raises(ValidationError) as excinfo:
            repository.commit_teaching_turn(
                learner_id=LEARNER,
                session_id=state.session_id,
                expected_session_version=current_version,
                events=[terminal_event],
                snapshot=None,
                next_session=replace(current, updated_at="2026-11-20T00:00:02Z"),
                goal=None,
            )
        assert excinfo.value.code == "INVALID_SESSION_TRANSITION"
        # Clearing pending while the prepared attempt has no terminal event must
        # fail closed (it would be an unexplainable/orphan state).
        with pytest.raises(ValidationError) as excinfo:
            repository.commit_teaching_turn(
                learner_id=LEARNER,
                session_id=state.session_id,
                expected_session_version=current_version,
                events=[],
                snapshot=None,
                next_session=replace(
                    current,
                    phase="REVIEW",
                    pending_item_id=None,
                    updated_at="2026-11-20T00:00:03Z",
                ),
                goal=None,
            )
        assert excinfo.value.code == "INCONSISTENT_PENDING"
        assert repository.load_session(state.session_id).to_dict() == current.to_dict()
    finally:
        repository.close()


# ---------------------------------------------------------------------------
# Transactional submit pipeline (A -> score -> B)
# ---------------------------------------------------------------------------


def test_submit_response_is_transactional_and_keeps_invariants(
    components: demo.Components, tmp_path: Path
) -> None:
    repository = SqliteRepository(tmp_path / "pipeline.db")
    try:
        scorer = ScriptedScorer("CORRECT")
        engine, history = build_engine(components, repository, scorer)
        state = start_and_drive_to_pending(engine, repository, components)
        session_id = state.session_id
        for turn in range(3):
            current = repository.load_session(session_id)
            assert current.pending_item_id is not None
            item_id = current.pending_item_id
            result = engine.submit_response(session_id, item_id, "A")
            assert result.status == "CORRECT"
            after = repository.load_session(session_id)
            assert after is not None
            assert after.turn_index == current.turn_index + 1
            assert after.pending_item_id is None
            events = repository.list_events(LEARNER)
            turn_events = [event for event in events if event.seq >= 0]
            assert any(
                event.event_type == "ASSESSMENT_PREPARED"
                and event.payload.get("item_id") == item_id
                for event in turn_events
            )
            assert_invariants(repository, components, LEARNER, session_id)
            assert history.verify_rebuild(LEARNER) is True
            # Move to the next pending item for the next turn.
            for _ in range(10):
                current = repository.load_session(session_id)
                if current.pending_item_id is not None:
                    break
                action = engine.current_action(session_id)
                if action.item_id is None:
                    engine.advance_session(session_id)
        snapshot = repository.get_snapshot(LEARNER)
        assert snapshot is not None
        assessed = [
            event
            for event in repository.list_events(LEARNER)
            if event.event_type == "ASSESSED"
            and event.payload.get("status") in {"CORRECT", "INCORRECT", "PARTIAL"}
        ]
        assert snapshot.revision == len(assessed)
        assert_invariants(repository, components, LEARNER, session_id)
    finally:
        repository.close()


def test_submit_same_result_id_same_response_is_idempotent(
    components: demo.Components, tmp_path: Path
) -> None:
    repository = SqliteRepository(tmp_path / "idem.db")
    try:
        engine, _history = build_engine(components, repository, ScriptedScorer())
        state = start_and_drive_to_pending(engine, repository, components)
        item_id = state.pending_item_id
        first = engine.submit_response(
            state.session_id, item_id, "A", result_id="result.idem.1"
        )
        count = len(repository.list_events(LEARNER))
        revision = repository.get_snapshot(LEARNER).revision
        second = engine.submit_response(
            state.session_id, item_id, "A", result_id="result.idem.1"
        )
        assert second.to_dict() == first.to_dict()
        assert len(repository.list_events(LEARNER)) == count
        assert repository.get_snapshot(LEARNER).revision == revision
        assert_invariants(repository, components, LEARNER, state.session_id)
    finally:
        repository.close()


def test_submit_idempotency_conflict_in_prepared_window(
    components: demo.Components, tmp_path: Path
) -> None:
    repository = SqliteRepository(tmp_path / "conflict.db")
    try:
        engine, history = build_engine(components, repository, ScriptedScorer())
        state = start_and_drive_to_pending(engine, repository, components)
        item_id = state.pending_item_id
        interrupt_after_prepare(engine, state.session_id, item_id, "A")
        prepared_count = len(
            [event for event in repository.list_events(LEARNER) if event.event_type == "ASSESSMENT_PREPARED"]
        )
        assert prepared_count == 1
        with pytest.raises(ConflictError) as excinfo:
            engine.submit_response(state.session_id, item_id, "B")
        assert excinfo.value.code == "IDEMPOTENCY_CONFLICT"
        assert repository.load_session(state.session_id).pending_item_id == item_id
        assert len(
            [event for event in repository.list_events(LEARNER) if event.event_type == "ASSESSMENT_PREPARED"]
        ) == prepared_count
        # Retrying with the prepared response completes the turn exactly once.
        result = engine.submit_response(state.session_id, item_id, "A")
        assert result.status == "CORRECT"
        assert history.verify_rebuild(LEARNER) is True
        assert_invariants(repository, components, LEARNER, state.session_id)
    finally:
        repository.close()


# ---------------------------------------------------------------------------
# Recovery algorithm (in-process interruption; real SIGKILL elsewhere)
# ---------------------------------------------------------------------------


def test_recover_session_completes_prepared_attempt_then_is_idempotent(
    components: demo.Components, tmp_path: Path
) -> None:
    repository = SqliteRepository(tmp_path / "recover.db")
    try:
        engine, history = build_engine(components, repository, ScriptedScorer())
        state = start_and_drive_to_pending(engine, repository, components)
        session_id = state.session_id
        item_id = state.pending_item_id
        interrupt_after_prepare(engine, session_id, item_id, "A")
        events_before = len(repository.list_events(LEARNER))
        report = engine.recover_session(session_id)
        assert report.status == "RECOVERED"
        assert report.prepared_attempts == 1
        assert report.recovered_attempts == 1
        assert report.events_appended == 2
        assert report.pending_attempt_ids == ()
        after = repository.load_session(session_id)
        assert after is not None
        assert after.pending_item_id is None
        assert after.turn_index == state.turn_index + 1
        assert repository.get_snapshot(LEARNER).revision == 1
        assert history.verify_rebuild(LEARNER) is True
        assert_invariants(repository, components, LEARNER, session_id)
        # Idempotent repeat: zero appended events.
        repeat = engine.recover_session(session_id)
        assert repeat.status == "ALREADY_CONSISTENT"
        assert repeat.events_appended == 0
        assert len(repository.list_events(LEARNER)) == events_before + 2
        # A repeated submission with the recovered result id is a no-op.
        result_id = repository.list_events(LEARNER)[-1].payload.get("result_id")
        before_retry = len(repository.list_events(LEARNER))
        retried = engine.submit_response(
            session_id, item_id, "A", result_id=result_id
        )
        assert retried.result_id == result_id
        assert len(repository.list_events(LEARNER)) == before_retry
    finally:
        repository.close()


def test_recovery_scorer_mismatch_keeps_pending_and_is_explainable(
    components: demo.Components, tmp_path: Path
) -> None:
    repository = SqliteRepository(tmp_path / "mismatch.db")
    try:
        scorer = ScriptedScorer()
        engine, _history = build_engine(components, repository, scorer)
        state = start_and_drive_to_pending(engine, repository, components)
        session_id = state.session_id
        item_id = state.pending_item_id
        interrupt_after_prepare(engine, session_id, item_id, "A")
        engine._scorer = MismatchedResultIdScorer()  # noqa: SLF001 - test double swap
        report = engine.recover_session(session_id)
        assert report.status == "FAILED"
        assert "RECOVERY_SCORER_MISMATCH" in report.error_codes
        assert report.recovered_attempts == 0
        fresh = repository.load_session(session_id)
        assert fresh is not None and fresh.pending_item_id == item_id
        assert fresh.turn_index == state.turn_index
        assert repository.get_snapshot(LEARNER) is None
        errors = [
            event
            for event in repository.list_events(LEARNER)
            if event.event_type == "ERROR" and event.payload.get("stage") == "RECOVERY"
        ]
        assert errors and errors[-1].payload["status"] == "RECOVERY_SCORER_MISMATCH"
        assert errors[-1].payload["mastery_unchanged"] is True
        # Repeated recovery is a zero-event no-op for the same failure.
        count = len(repository.list_events(LEARNER))
        repeated = engine.recover_session(session_id)
        assert repeated.events_appended == 0
        assert len(repository.list_events(LEARNER)) == count
        # Restoring a deterministic scorer recovers the same pending attempt.
        engine._scorer = scorer  # noqa: SLF001
        recovered = engine.recover_session(session_id)
        assert recovered.status == "RECOVERED"
        assert repository.load_session(session_id).pending_item_id is None
    finally:
        repository.close()


def test_recovery_scorer_error_is_fail_closed_then_retryable(
    components: demo.Components, tmp_path: Path
) -> None:
    repository = SqliteRepository(tmp_path / "scorer_error.db")
    try:
        scorer = ScriptedScorer()
        engine, _history = build_engine(components, repository, scorer)
        state = start_and_drive_to_pending(engine, repository, components)
        session_id = state.session_id
        item_id = state.pending_item_id
        interrupt_after_prepare(engine, session_id, item_id, "A")
        engine._scorer = ScriptedScorer(raising=True)  # noqa: SLF001
        report = engine.recover_session(session_id)
        assert report.status == "FAILED"
        assert "RECOVERY_SCORER_ERROR" in report.error_codes
        assert repository.load_session(session_id).pending_item_id == item_id
        engine._scorer = scorer  # noqa: SLF001
        assert engine.recover_session(session_id).status == "RECOVERED"
        assert_invariants(repository, components, LEARNER, session_id)
    finally:
        repository.close()


def test_recovery_detects_inconsistent_pending_state(
    components: demo.Components, tmp_path: Path
) -> None:
    repository = SqliteRepository(tmp_path / "inconsistent.db")
    try:
        engine, _history = build_engine(components, repository, ScriptedScorer())
        state = start_and_drive_to_pending(engine, repository, components)
        session_id = state.session_id
        item_id = state.pending_item_id
        interrupt_after_prepare(engine, session_id, item_id, "A")
        # Tamper: someone advanced the session without committing the attempt.
        repository.save_session(
            replace(
                repository.load_session(session_id),
                turn_index=state.turn_index + 1,
                pending_item_id=None,
            )
        )
        report = engine.recover_session(session_id)
        assert report.status == "FAILED"
        assert "RECOVERY_STATE_INCONSISTENT" in report.error_codes
        errors = [
            event
            for event in repository.list_events(LEARNER)
            if event.event_type == "ERROR" and event.payload.get("stage") == "RECOVERY"
        ]
        assert errors
        assert errors[-1].payload["session_unchanged"] is True
        # No terminal event was fabricated: the attempt is still not completed.
        assert all(
            event.event_type != "ASSESSED" for event in repository.list_events(LEARNER)
        )
    finally:
        repository.close()


def test_recover_pending_turns_covers_all_sessions_of_a_learner(
    components: demo.Components, tmp_path: Path
) -> None:
    repository = SqliteRepository(tmp_path / "multi.db")
    try:
        engine, _history = build_engine(components, repository, ScriptedScorer())
        first = start_and_drive_to_pending(engine, repository, components)
        second = start_and_drive_to_pending(
            engine,
            repository,
            components,
            session_id="session.m1b.second",
            goal_suffix=".second",
        )
        assert first.session_id != second.session_id
        interrupt_after_prepare(engine, first.session_id, first.pending_item_id, "A")
        interrupt_after_prepare(engine, second.session_id, second.pending_item_id, "B")
        reports = engine.recover_pending_turns(LEARNER)
        assert [report.status for report in reports] == ["RECOVERED", "RECOVERED"]
        assert engine.recover_pending_turns(LEARNER) == []
        assert repository.load_session(first.session_id).pending_item_id is None
        assert repository.load_session(second.session_id).pending_item_id is None
        assert LearningHistory(repository).verify_rebuild(LEARNER) is True
    finally:
        repository.close()


# ---------------------------------------------------------------------------
# Legacy fallback (protocol-only repository) is documented non-atomic
# ---------------------------------------------------------------------------


class LegacyOnlyRepository:
    """Delegates the frozen protocols but hides the B-NEXT atomic extensions."""

    _BLOCKED = frozenset(
        {
            "commit_teaching_turn",
            "session_version",
            "append_events",
            "append_events_and_upsert_snapshot",
            "append_event_and_upsert_snapshot",
            "ensure_learner",
            "list_learners",
        }
    )

    def __init__(self, inner: SqliteRepository) -> None:
        self._inner = inner

    def __getattr__(self, name: str):  # noqa: ANN401 - transparent delegation
        if name in self._BLOCKED:
            raise AttributeError(name)
        return getattr(self._inner, name)


def test_engine_falls_back_to_legacy_flow_without_transactional_api(
    components: demo.Components, tmp_path: Path
) -> None:
    inner = SqliteRepository(tmp_path / "legacy.db")
    repository = LegacyOnlyRepository(inner)
    try:
        engine, history = build_engine(components, repository, ScriptedScorer())
        assert engine.supports_transactional_turns is False
        with pytest.raises(UnsupportedOperationError) as excinfo:
            engine.recover_session("session.x")
        assert excinfo.value.code == "RECOVERY_UNSUPPORTED"
        state = start_and_drive_to_pending(engine, repository, components)
        item_id = state.pending_item_id
        result = engine.submit_response(state.session_id, item_id, "A")
        assert result.status == "CORRECT"
        event_types = {event.event_type for event in inner.list_events(LEARNER)}
        assert "RESPONSE_SUBMITTED" in event_types
        assert "ASSESSED" in event_types
        assert "ASSESSMENT_PREPARED" not in event_types  # legacy non-atomic path
        assert inner.load_session(state.session_id).pending_item_id is None
        assert history.verify_rebuild(LEARNER) is True
    finally:
        inner.close()


# ---------------------------------------------------------------------------
# Review P2-1/P2-2 regressions
# ---------------------------------------------------------------------------


def test_recovery_audit_error_does_not_satisfy_terminal_invariant(
    components: demo.Components, tmp_path: Path
) -> None:
    """Review P2-1: RECOVERY audit ERROR events must not count as terminal.

    Before the fix the repository treated any ``ERROR`` payload containing a
    ``result_id`` as terminal, so after a failed recovery a direct repository
    call could clear ``pending_item_id`` while the PREPARED attempt had no real
    terminal event (bypassing INV-4).  The audit event must never satisfy the
    invariant.
    """

    repository = SqliteRepository(tmp_path / "p2_1.db")
    try:
        engine, _history = build_engine(components, repository, ScriptedScorer())
        state = start_and_drive_to_pending(engine, repository, components)
        session_id = state.session_id
        item_id = state.pending_item_id
        interrupt_after_prepare(engine, session_id, item_id, "A")
        # Tamper into the "inconsistent pending" state, then let recovery record
        # its audit ERROR (which carries the prepared result_id).
        repository.save_session(
            replace(
                repository.load_session(session_id),
                turn_index=state.turn_index + 1,
                pending_item_id=None,
            )
        )
        report = engine.recover_session(session_id)
        assert report.status == "FAILED"
        assert "RECOVERY_STATE_INCONSISTENT" in report.error_codes
        prepared_events = [
            event
            for event in repository.list_events(LEARNER)
            if event.event_type == "ASSESSMENT_PREPARED"
        ]
        assert len(prepared_events) == 1
        prepared_result_id = prepared_events[0].payload["result_id"]
        audit_errors = [
            event
            for event in repository.list_events(LEARNER)
            if event.event_type == "ERROR" and event.payload.get("stage") == "RECOVERY"
        ]
        assert len(audit_errors) == 1
        assert audit_errors[0].event_id.startswith("evt.recoveryerror.")
        assert audit_errors[0].payload.get("result_id") == prepared_result_id
        assert report.pending_attempt_ids == (
            prepared_events[0].payload["attempt_id"],
        )
        current = repository.load_session(session_id)
        assert current is not None and current.pending_item_id is None
        with pytest.raises(ValidationError) as excinfo:
            repository.commit_teaching_turn(
                learner_id=LEARNER,
                session_id=session_id,
                expected_session_version=session_version(current),
                events=[],
                snapshot=None,
                next_session=replace(current, updated_at="2026-11-20T00:00:05Z"),
                goal=None,
            )
        assert excinfo.value.code == "INCONSISTENT_PENDING"
        assert repository.load_session(session_id).to_dict() == current.to_dict()
    finally:
        repository.close()


def test_recovery_audit_event_seq_conflict_retry_branch(
    components: demo.Components, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review P2-2: the audit-event seq-conflict retry branch is reachable/covered.

    The first audit ``ERROR`` append is forced to use an already used seq (as a
    concurrent recovery would); the retry must allocate a fresh seq and return an
    explainable ``RecoveryReport`` instead of leaking a ``ConflictError``.
    """

    repository = SqliteRepository(tmp_path / "p2_2.db")
    try:
        engine, _history = build_engine(components, repository, ScriptedScorer())
        state = start_and_drive_to_pending(engine, repository, components)
        session_id = state.session_id
        item_id = state.pending_item_id
        interrupt_after_prepare(engine, session_id, item_id, "A")
        engine._scorer = MismatchedResultIdScorer()  # noqa: SLF001 - force audit path
        original_next_seq = engine._next_event_seq
        calls = {"count": 0}

        def flaky_next_seq(_learner_id: str) -> int:
            calls["count"] += 1
            if calls["count"] == 1:
                return 0  # already used by SESSION_STARTED: forces a native seq conflict
            return original_next_seq(_learner_id)

        monkeypatch.setattr(engine, "_next_event_seq", flaky_next_seq)
        report = engine.recover_session(session_id)
        monkeypatch.setattr(engine, "_next_event_seq", original_next_seq)
        assert calls["count"] >= 2, "the seq-conflict retry branch must be exercised"
        assert report.status == "FAILED"
        assert "RECOVERY_SCORER_MISMATCH" in report.error_codes
        audit_errors = [
            event
            for event in repository.list_events(LEARNER)
            if event.event_type == "ERROR"
            and event.payload.get("stage") == "RECOVERY"
            and event.event_id.startswith("evt.recoveryerror.")
        ]
        assert len(audit_errors) == 1
        # Once the scorer is deterministic again, recovery completes and a repeat
        # audit append is a zero-event no-op.
        engine._scorer = ScriptedScorer()  # noqa: SLF001
        assert engine.recover_session(session_id).status == "RECOVERED"
        assert len(
            [
                event
                for event in repository.list_events(LEARNER)
                if event.event_type == "ERROR" and event.payload.get("stage") == "RECOVERY"
            ]
        ) == 1
    finally:
        repository.close()


# ---------------------------------------------------------------------------
# Goal completion is committed in the same transaction as the mastery update
# ---------------------------------------------------------------------------


def test_goal_completion_is_atomic_and_persists_goal_status(
    components: demo.Components, tmp_path: Path
) -> None:
    repository = SqliteRepository(tmp_path / "goal.db")
    try:
        engine, history = build_engine(components, repository, ScriptedScorer("CORRECT"))
        # Seed the same near-complete snapshot as the existing M1-A goal test.
        from m1_teacher.contracts.types import MasteryEstimate

        adapter = components.adapter
        masteries = {
            node.node_id: MasteryEstimate(
                node_id=node.node_id,
                value=0.9,
                confidence=0.9,
                evidence_count=3,
                created_at=TS,
                updated_at=TS,
            )
            for node in adapter.knowledge_nodes()
        }
        for node_id in ("cf.search.binary", "cf.search.boundary"):
            masteries[node_id] = MasteryEstimate(
                node_id=node_id,
                value=0.65,
                confidence=0.6,
                evidence_count=1,
                created_at=TS,
                updated_at=TS,
            )
        from m1_teacher.contracts.types import LearnerSnapshot

        seeded = LearnerSnapshot(
            learner_id=LEARNER,
            masteries=masteries,
            revision=1,
            created_at=TS,
            updated_at=TS,
        )
        repository.ensure_learner(LEARNER, created_at=TS)
        repository.upsert_snapshot(seeded)
        state = start_and_drive_to_pending(engine, repository, components)
        final = engine.run_until_goal(
            state.session_id, max_turns=8, responder=lambda item, session: "A"
        )
        assert final.phase == "COMPLETE"
        goal = repository.get_goal(state.goal_id)
        assert goal is not None and goal.status == "COMPLETED"
        events = repository.list_events(LEARNER)
        assert any(event.event_type == "GOAL_COMPLETED" for event in events)
        assert_invariants(
            repository,
            components,
            LEARNER,
            state.session_id,
            seed_evidence={
                node_id: estimate.evidence_count
                for node_id, estimate in seeded.masteries.items()
            },
            verify_rebuild=False,  # the seeded snapshot predates the event log
        )
        assert history.verify_rebuild(LEARNER) is False  # documented seed limitation
    finally:
        repository.close()
