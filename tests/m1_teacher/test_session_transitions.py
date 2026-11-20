"""Transition-level tests for the teaching-session state machine (B-PR4).

Each documented transition (and skip/back-track/re-enter path) is exercised on
the real CF binary-search fixtures.  Scenarios are seeded with an explicit
``LearnerSnapshot`` where a specific state-machine edge is needed; the scoring
outcome comes from a scripted deterministic scorer so the tested rule — not
mastery arithmetic — drives the assertion.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from m1_teacher.contracts.errors import ConflictError, NotFoundError, ValidationError
from m1_teacher.contracts.types import (
    AssessmentItem,
    AssessmentResult,
    LearnerGoal,
    LearnerSnapshot,
    LearningObjective,
    MasteryEstimate,
)
from m1_teacher.domains.cf_binary_search import CFBinarySearchDomainAdapter
from m1_teacher.knowledge import KnowledgeGraph
from m1_teacher.learner.repository import SqliteRepository
from m1_teacher.session import SessionPolicy, TeachingSessionEngine

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = REPO_ROOT / "fixtures" / "m1_teacher"
TS = "2026-11-20T00:00:00Z"


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def adapter() -> CFBinarySearchDomainAdapter:
    domain = CFBinarySearchDomainAdapter(FIXTURES_DIR)
    domain.validate()
    return domain


@pytest.fixture(scope="module")
def graph(adapter: CFBinarySearchDomainAdapter) -> KnowledgeGraph:
    return KnowledgeGraph(adapter.knowledge_nodes(), adapter.prerequisite_edges())


@pytest.fixture(scope="module")
def objective(adapter: CFBinarySearchDomainAdapter) -> LearningObjective:
    return adapter.objectives()[0]


@pytest.fixture()
def repository(tmp_path: Path) -> SqliteRepository:
    repo = SqliteRepository(tmp_path / "m1a.sqlite")
    try:
        yield repo
    finally:
        repo.close()


def node_ids(adapter: CFBinarySearchDomainAdapter) -> list[str]:
    return [node.node_id for node in adapter.knowledge_nodes()]


def make_goal(learner_id: str, objective: LearningObjective) -> LearnerGoal:
    return LearnerGoal(
        goal_id=f"goal-{learner_id}",
        learner_id=learner_id,
        objective_id=objective.objective_id,
        created_at=TS,
    )


def make_snapshot(
    learner_id: str,
    spec: dict[str, tuple[float, int, float]],
) -> LearnerSnapshot:
    return LearnerSnapshot(
        learner_id=learner_id,
        masteries={
            node_id: MasteryEstimate(
                node_id=node_id,
                value=value,
                confidence=confidence,
                evidence_count=evidence_count,
                created_at=TS,
                updated_at=TS,
            )
            for node_id, (value, evidence_count, confidence) in spec.items()
        },
        revision=1,
        created_at=TS,
        updated_at=TS,
    )


def seed(
    repository: SqliteRepository,
    learner_id: str,
    overrides: dict[str, tuple[float, int, float]],
    adapter: CFBinarySearchDomainAdapter,
) -> LearnerSnapshot:
    spec = {node_id: (0.9, 3, 0.9) for node_id in node_ids(adapter)}
    spec.update(overrides)
    repository.ensure_learner(learner_id, created_at=TS)
    snapshot = make_snapshot(learner_id, spec)
    repository.upsert_snapshot(snapshot)
    return snapshot


class ScriptedScorer:
    scorer_id = "m1a.test.scripted.v0"

    def __init__(self, status: str = "CORRECT") -> None:
        self.status = status

    def score(
        self,
        item: AssessmentItem,
        learner_id: str,
        response: str | dict,
        *,
        result_id: str | None = None,
    ) -> AssessmentResult:
        score = {"CORRECT": 1.0, "INCORRECT": 0.0, "PARTIAL": 0.5}.get(self.status)
        return AssessmentResult(
            result_id=result_id or f"result:{item.item_id}",
            item_id=item.item_id,
            learner_id=learner_id,
            status=self.status,
            score=score,
            max_score=item.max_score,
            scorer_id=self.scorer_id,
            failure_reason="" if self.status == "CORRECT" else "SCRIPTED_REASON",
        )


def make_engine(
    adapter: CFBinarySearchDomainAdapter,
    graph: KnowledgeGraph,
    repository: SqliteRepository,
    *,
    scorer: object | None = None,
    policy: SessionPolicy | None = None,
) -> TeachingSessionEngine:
    return TeachingSessionEngine(
        adapter,
        graph,
        repository,
        scorer=scorer if scorer is not None else ScriptedScorer(),
        policy=policy or SessionPolicy(),
    )


def begin(
    engine: TeachingSessionEngine,
    learner_id: str,
    objective: LearningObjective,
) -> str:
    goal = make_goal(learner_id, objective)
    state = engine.start_session(learner_id, goal, objective)
    return state.session_id


def pending_or_action(engine: TeachingSessionEngine, repository: SqliteRepository, sid: str):
    """Submit the pending item, else return the next action for the caller."""

    state = repository.load_session(sid)
    if state.pending_item_id is not None:
        return ("submit", state.pending_item_id)
    return ("action", engine.current_action(sid))


def drive(
    engine: TeachingSessionEngine,
    repository: SqliteRepository,
    sid: str,
    steps: int,
    response: str = "A",
) -> list[tuple[str, object]]:
    """Advance the session; auto-submit pending items and acknowledge content actions."""

    trace: list[tuple[str, object]] = []
    for _ in range(steps):
        state = repository.load_session(sid)
        if state.phase in {"COMPLETE", "PAUSED"}:
            break
        if state.pending_item_id is not None:
            result = engine.submit_response(sid, state.pending_item_id, response)
            trace.append(("submit", result.status))
            continue
        action = engine.current_action(sid)
        trace.append(("action", (action.kind, action.reason.code if action.reason else None)))
        if action.kind == "GOAL_COMPLETE":
            break
        if action.item_id is None:
            engine.advance_session(sid)
    return trace


# ---------------------------------------------------------------------------
# DIAGNOSE transitions
# ---------------------------------------------------------------------------
def test_diagnose_action_contract(adapter, graph, repository, objective) -> None:
    engine = make_engine(adapter, graph, repository)
    sid = begin(engine, "learner.diag", objective)
    state = repository.load_session(sid)
    assert state.phase == "DIAGNOSE"
    action = engine.current_action(sid)
    assert action.kind == "DIAGNOSE"
    assert action.item_id == state.pending_item_id
    item = next(i for i in adapter.assessment_items() if i.item_id == action.item_id)
    assert action.node_ids == item.node_ids
    assert action.content == item.prompt
    event = [e for e in repository.list_events("learner.diag") if e.event_type == "ACTION_TAKEN"][-1]
    assert event.payload["action_kind"] == "DIAGNOSE"
    assert event.payload["node_ids"] == item.node_ids
    assert event.payload["phase"] == "DIAGNOSE"


def test_diagnose_repeats_until_minimum_then_moves_on(
    adapter, graph, repository, objective
) -> None:
    engine = make_engine(adapter, graph, repository)
    sid = begin(engine, "learner.min", objective)
    state = repository.load_session(sid)
    first_item = state.pending_item_id
    engine.submit_response(sid, first_item, "A")
    assert repository.load_session(sid).phase == "REVIEW"
    second_action = engine.current_action(sid)
    assert second_action.kind == "DIAGNOSE"
    assert second_action.item_id != first_item, "diagnostic items must not repeat immediately"
    engine.submit_response(sid, second_action.item_id, "A")
    after_two = engine.current_action(sid)
    assert after_two.kind != "DIAGNOSE", "diagnosis_min_items observations reached"
    diagnostic_actions = [
        event
        for event in repository.list_events("learner.min")
        if event.event_type == "ACTION_TAKEN" and event.payload["phase"] == "DIAGNOSE"
    ]
    assert len(diagnostic_actions) == 2


def test_diagnose_skipped_when_evidence_sufficient(
    adapter, graph, repository, objective
) -> None:
    # All relevant nodes already have sufficient observed evidence.
    seed(
        repository,
        "learner.evidence",
        {
            "cf.search.binary": (0.3, 3, 0.9),
            "cf.search.boundary": (0.3, 3, 0.9),
            "cf.search.lower_upper": (0.3, 3, 0.9),
            "cf.complexity.log": (0.3, 3, 0.9),
        },
        adapter,
    )
    engine = make_engine(adapter, graph, repository)
    sid = begin(engine, "learner.evidence", objective)
    actions = [event for event in repository.list_events("learner.evidence") if event.event_type == "ACTION_TAKEN"]
    assert actions
    assert all(event.payload["phase"] != "DIAGNOSE" for event in actions)
    state = repository.load_session(sid)
    assert state.phase in {"TEACH", "PRACTICE", "ASSESS", "REVIEW"}


# ---------------------------------------------------------------------------
# REVIEW -> TEACH / PRACTICE transitions
# ---------------------------------------------------------------------------
def test_review_reenters_teach_for_weak_prerequisite(
    adapter, graph, repository, objective
) -> None:
    seed(
        repository,
        "learner.weak",
        {
            "cf.array.basics": (0.2, 2, 0.6),
            "cf.search.binary": (0.3, 3, 0.9),
            "cf.search.boundary": (0.3, 3, 0.9),
            "cf.search.lower_upper": (0.3, 3, 0.9),
        },
        adapter,
    )
    engine = make_engine(adapter, graph, repository)
    sid = begin(engine, "learner.weak", objective)
    state = repository.load_session(sid)
    assert state.phase == "TEACH"
    action = engine.current_action(sid)
    assert action.kind == "RETEACH"
    assert action.item_id is None
    assert action.node_ids == ["cf.array.basics"]
    assert action.content == adapter.teaching_content("cf.array.basics", "EXPLAIN")


def test_teach_advance_returns_to_review_then_practice(
    adapter, graph, repository, objective
) -> None:
    seed(
        repository,
        "learner.teach",
        {
            "cf.array.basics": (0.2, 2, 0.6),
            "cf.search.binary": (0.3, 3, 0.9),
            "cf.search.boundary": (0.3, 3, 0.9),
            "cf.search.lower_upper": (0.3, 3, 0.9),
        },
        adapter,
    )
    engine = make_engine(adapter, graph, repository)
    sid = begin(engine, "learner.teach", objective)
    teach = engine.current_action(sid)
    assert teach.kind == "RETEACH"
    advanced = engine.advance_session(sid)
    assert advanced.phase == "REVIEW"
    assert advanced.turn_index == 1
    practice = engine.current_action(sid)
    assert practice.kind == "PRACTICE"
    assert practice.item_id is not None
    assert repository.load_session(sid).phase == "PRACTICE"
    assert practice.content
    assert teach.action_id != practice.action_id


def test_review_to_practice_when_teach_not_needed(
    adapter, graph, repository, objective
) -> None:
    seed(repository, "learner.practice", {"cf.search.boundary": (0.6, 3, 0.9)}, adapter)
    engine = make_engine(adapter, graph, repository)
    sid = begin(engine, "learner.practice", objective)
    action = engine.current_action(sid)
    assert action.kind == "PRACTICE"
    assert action.kind not in {"EXPLAIN", "RETEACH"}
    assert repository.load_session(sid).phase == "PRACTICE"
    assert action.item_id is not None


# ---------------------------------------------------------------------------
# PRACTICE / ASSESS back-tracking after INCORRECT
# ---------------------------------------------------------------------------
def test_incorrect_returns_to_instructional_phase_with_hint(
    adapter, graph, repository, objective
) -> None:
    seed(repository, "learner.back", {"cf.search.boundary": (0.6, 3, 0.9)}, adapter)
    engine = make_engine(
        adapter, graph, repository, scorer=ScriptedScorer("INCORRECT")
    )
    sid = begin(engine, "learner.back", objective)
    practice = engine.current_action(sid)
    assert practice.kind == "PRACTICE"
    result = engine.submit_response(sid, practice.item_id, "A")
    assert result.status == "INCORRECT"
    assert repository.load_session(sid).phase == "REVIEW"

    hint = engine.current_action(sid)
    assert hint.kind == "HINT"
    assert hint.reason.code == "HINT_LEVEL_2"
    assert hint.content == adapter.teaching_content(hint.node_ids[0], "HINT_L2")
    engine.advance_session(sid)
    next_action = engine.current_action(sid)
    assert next_action.phase if hasattr(next_action, "phase") else True
    assert next_action.kind in {"EXPLAIN", "RETEACH", "PRACTICE", "REASSESS"}
    assert repository.load_session(sid).phase in {"TEACH", "PRACTICE", "ASSESS"}


def test_two_incorrect_escalate_hints_to_l3_and_trigger_reassess(
    adapter, graph, repository, objective
) -> None:
    overrides = {
        "cf.search.boundary": (0.2, 2, 0.6),
        "cf.search.lower_upper": (0.2, 2, 0.6),
        "cf.search.binary": (0.85, 3, 0.9),
    }
    seed(repository, "learner.stuck", overrides, adapter)
    engine = make_engine(
        adapter, graph, repository, scorer=ScriptedScorer("INCORRECT")
    )
    sid = begin(engine, "learner.stuck", objective)
    hint_levels: list[str] = []
    kinds: list[str] = []
    trace = drive(engine, repository, sid, steps=12)
    for kind, detail in trace:
        if kind == "action":
            action_kind, code = detail  # type: ignore[misc]
            kinds.append(action_kind)
            if action_kind == "HINT":
                hint_levels.append(code)
    events = repository.list_events("learner.stuck")
    hint_events = [
        event
        for event in events
        if event.event_type == "ACTION_TAKEN"
        and event.payload["action_kind"] == "HINT"
    ]
    codes = [event.payload["action"]["reason"]["code"] for event in hint_events]
    assert codes, "repeated INCORRECT outcomes must escalate hints"
    assert "HINT_LEVEL_2" in codes
    assert "HINT_LEVEL_3" in codes
    assert all(int(code.rsplit("_", 1)[1]) <= 3 for code in codes), codes
    assert max(int(code.rsplit("_", 1)[1]) for code in codes) == 3
    assert "REASSESS" in kinds, f"expected a REASSESS action after two failures, got {kinds}"
    reassess = [
        event
        for event in events
        if event.event_type == "ACTION_TAKEN"
        and event.payload["action_kind"] == "REASSESS"
    ]
    assert reassess[0].payload["phase"] == "ASSESS"
    assert reassess[0].payload["node_ids"]
    # Hint content comes from the domain teaching content, never a synthetic string.
    for event in hint_events:
        level = event.payload["action"]["reason"]["code"].rsplit("_", 1)[1]
        node_id = event.payload["node_ids"][0]
        assert event.payload["action"]["content"] == adapter.teaching_content(
            node_id, f"HINT_L{level}"
        )


def test_hint_ladder_never_exceeds_l3(adapter, graph, repository, objective) -> None:
    seed(repository, "learner.hints", {"cf.search.boundary": (0.2, 2, 0.6)}, adapter)
    engine = make_engine(
        adapter, graph, repository, scorer=ScriptedScorer("INCORRECT")
    )
    sid = begin(engine, "learner.hints", objective)
    drive(engine, repository, sid, steps=14)
    hint_events = [
        event
        for event in repository.list_events("learner.hints")
        if event.event_type == "ACTION_TAKEN" and event.payload["action_kind"] == "HINT"
    ]
    assert hint_events
    levels = [
        int(event.payload["action"]["reason"]["code"].rsplit("_", 1)[1])
        for event in hint_events
    ]
    assert max(levels) <= 3
    # HINT_L4 does not exist in the domain teaching content: no L4 is emitted.
    for level in levels:
        assert level in {1, 2, 3}


# ---------------------------------------------------------------------------
# Skip / terminal / pause transitions
# ---------------------------------------------------------------------------
def test_goal_completion_skips_teach(adapter, graph, repository, objective) -> None:
    seed(
        repository,
        "learner.done",
        {
            "cf.search.binary": (0.85, 3, 0.9),
            "cf.search.boundary": (0.85, 3, 0.9),
        },
        adapter,
    )
    engine = make_engine(adapter, graph, repository)
    sid = begin(engine, "learner.done", objective)
    assert repository.load_session(sid).phase == "COMPLETE"
    assert engine.current_action(sid).kind == "GOAL_COMPLETE"
    kinds = [
        event.payload["action_kind"]
        for event in repository.list_events("learner.done")
        if event.event_type == "ACTION_TAKEN"
    ]
    assert "EXPLAIN" not in kinds and "RETEACH" not in kinds


def test_complete_terminal_blocks_mutations(
    adapter, graph, repository, objective
) -> None:
    seed(
        repository,
        "learner.terminal",
        {
            "cf.search.binary": (0.85, 3, 0.9),
            "cf.search.boundary": (0.85, 3, 0.9),
        },
        adapter,
    )
    engine = make_engine(adapter, graph, repository)
    sid = begin(engine, "learner.terminal", objective)
    assert "COMPLETE" in engine.phase_history(sid)
    with pytest.raises(ConflictError):
        engine.advance_session(sid)
    with pytest.raises(ConflictError):
        engine.submit_response(sid, "item.bs.mcq.001", "A")
    with pytest.raises(ConflictError):
        engine.pause_session(sid)
    with pytest.raises(ConflictError):
        engine.resume_session(sid)


def test_pause_and_resume_transitions(adapter, graph, repository, objective) -> None:
    engine = make_engine(adapter, graph, repository)
    sid = begin(engine, "learner.pause", objective)
    action = engine.current_action(sid)
    paused = engine.pause_session(sid)
    assert paused.phase == "PAUSED"
    assert paused.pending_item_id == action.item_id
    event_types = [event.event_type for event in repository.list_events("learner.pause")]
    assert "SESSION_PAUSED" in event_types
    paused_event = next(
        event for event in repository.list_events("learner.pause") if event.event_type == "SESSION_PAUSED"
    )
    assert paused_event.payload["previous_phase"] == "DIAGNOSE"

    with pytest.raises(ConflictError):
        engine.current_action(sid)
    with pytest.raises(ConflictError):
        engine.advance_session(sid)
    with pytest.raises(ConflictError):
        engine.submit_response(sid, action.item_id, "A")

    resumed = engine.resume_session(sid)
    assert resumed.phase == "DIAGNOSE"
    assert resumed.pending_item_id == paused.pending_item_id
    event_types = [event.event_type for event in repository.list_events("learner.pause")]
    assert "SESSION_RESUMED" in event_types
    assert engine.current_action(sid) == action
    with pytest.raises(ConflictError):
        engine.resume_session(sid)


# ---------------------------------------------------------------------------
# Illegal transitions / fail-closed inputs
# ---------------------------------------------------------------------------
def test_illegal_item_transitions_fail_closed(
    adapter, graph, repository, objective
) -> None:
    engine = make_engine(adapter, graph, repository)
    sid = begin(engine, "learner.illegal", objective)
    state = repository.load_session(sid)
    assert state.pending_item_id is not None
    with pytest.raises(ConflictError):
        engine.advance_session(sid)
    with pytest.raises(ConflictError):
        engine.submit_response(sid, "item.bs.code.001", "A")
    with pytest.raises(NotFoundError):
        engine.submit_response(sid, "item.unknown", "A")
    engine.submit_response(sid, state.pending_item_id, "A")
    assert repository.load_session(sid).phase == "REVIEW"
    with pytest.raises(ConflictError):
        engine.submit_response(sid, state.pending_item_id, "A")


def test_unknown_records_fail_closed(adapter, graph, repository, objective) -> None:
    engine = make_engine(adapter, graph, repository)
    with pytest.raises(NotFoundError):
        engine.current_action("session:missing")
    with pytest.raises(NotFoundError):
        engine.advance_session("session:missing")
    with pytest.raises(NotFoundError):
        engine.pause_session("session:missing")
    with pytest.raises(NotFoundError):
        engine.resume_session("session:missing")


def test_session_collision_with_different_goal_fails(
    adapter, graph, repository, objective
) -> None:
    engine = make_engine(adapter, graph, repository)
    goal = make_goal("learner.collide", objective)
    state = engine.start_session("learner.collide", goal, objective)
    other_goal = LearnerGoal(
        goal_id="goal-other",
        learner_id="learner.collide",
        objective_id=objective.objective_id,
        created_at=TS,
    )
    with pytest.raises(ConflictError):
        engine.start_session(
            "learner.collide", other_goal, objective, session_id=state.session_id
        )


def test_validation_of_invalid_hint_and_scorer_inputs(
    adapter, graph, repository, objective
) -> None:
    engine = make_engine(adapter, graph, repository)
    with pytest.raises(ValidationError):
        TeachingSessionEngine(adapter, graph, repository, scorer=object())  # type: ignore[arg-type]
    sid = begin(engine, "learner.valid", objective)
    state = repository.load_session(sid)
    with pytest.raises(ValidationError):
        engine.submit_response(sid, state.pending_item_id, "A", result_id="   ")


# ---------------------------------------------------------------------------
# Recorded action payload / idempotency of current_action
# ---------------------------------------------------------------------------
def test_current_action_is_idempotent_within_a_turn(
    adapter, graph, repository, objective
) -> None:
    engine = make_engine(adapter, graph, repository)
    sid = begin(engine, "learner.idem", objective)
    first = engine.current_action(sid)
    second = engine.current_action(sid)
    assert first == second
    events = [
        event
        for event in repository.list_events("learner.idem")
        if event.event_type == "ACTION_TAKEN"
    ]
    assert len(events) == 1
    engine.submit_response(sid, first.item_id, "A")
    third = engine.current_action(sid)
    assert third.action_id != first.action_id
    action_events = [
        event
        for event in repository.list_events("learner.idem")
        if event.event_type == "ACTION_TAKEN"
    ]
    assert len(action_events) == 2


def test_action_taken_payload_is_planner_consumable(
    adapter, graph, repository, objective
) -> None:
    seed(
        repository,
        "learner.payload",
        {
            "cf.array.basics": (0.2, 2, 0.6),
            "cf.search.binary": (0.3, 3, 0.9),
            "cf.search.boundary": (0.3, 3, 0.9),
            "cf.search.lower_upper": (0.3, 3, 0.9),
        },
        adapter,
    )
    engine = make_engine(adapter, graph, repository)
    sid = begin(engine, "learner.payload", objective)
    engine.advance_session(sid)
    engine.current_action(sid)
    valid_action_kinds = {
        "DIAGNOSE",
        "EXPLAIN",
        "HINT",
        "PRACTICE",
        "REVIEW",
        "RETEACH",
        "REASSESS",
        "GOAL_COMPLETE",
    }
    action_events = [
        event
        for event in repository.list_events("learner.payload")
        if event.event_type == "ACTION_TAKEN"
    ]
    assert action_events
    reteach_seen = False
    for event in action_events:
        payload = event.payload
        assert payload["action_kind"] in valid_action_kinds
        assert isinstance(payload["node_ids"], list)
        assert all(node_id in node_ids(adapter) for node_id in payload["node_ids"])
        assert payload["phase"] in {"DIAGNOSE", "TEACH", "PRACTICE", "ASSESS", "REVIEW", "COMPLETE"}
        assert isinstance(payload["turn_index"], int)
        assert isinstance(payload["snapshot_revision"], int)
        if payload["action_kind"] == "RETEACH":
            reteach_seen = True
    assert reteach_seen, "weak-prerequisite scenario must emit a RETEACH action"


def test_phase_history_orders_diagnose_assess_update_review(
    adapter, graph, repository, objective
) -> None:
    engine = make_engine(adapter, graph, repository)
    sid = begin(engine, "learner.phases", objective)
    first = engine.current_action(sid)
    engine.submit_response(sid, first.item_id, "A")
    phases = engine.phase_history(sid)
    for phase in ("DIAGNOSE", "ASSESS", "UPDATE", "REVIEW"):
        assert phase in phases, (phase, phases)
    assert phases.index("DIAGNOSE") < phases.index("ASSESS")
    assert phases.index("ASSESS") < phases.index("UPDATE")
    assert phases.index("UPDATE") < phases.index("REVIEW")

    drive(engine, repository, sid, steps=6)
    phases = engine.phase_history(sid)
    assert "TEACH" in phases or "PRACTICE" in phases, phases
