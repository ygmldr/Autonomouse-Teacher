"""End-to-end tests for the teaching-session engine (B-PR4).

Covers the closed loop, evidence-driven mastery updates, EVAL_ERROR isolation,
idempotent response submission, pause/resume and restart recovery against the
real CF binary-search fixtures and a real SQLite repository.  The scorer is
scripted where the test needs a specific outcome; the scorer itself is covered
by ``test_assessment_scorer.py``.
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
OBJECTIVE_ID = "obj.cf.binary_search.mastery"


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
    error_counts: dict[str, int] | None = None,
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
        error_counts=dict(error_counts or {}),
        revision=1,
        created_at=TS,
        updated_at=TS,
    )


def seed_snapshot(
    repository: SqliteRepository,
    learner_id: str,
    spec: dict[str, tuple[float, int, float]],
    error_counts: dict[str, int] | None = None,
) -> LearnerSnapshot:
    repository.ensure_learner(learner_id, created_at=TS)
    snapshot = make_snapshot(learner_id, spec, error_counts)
    repository.upsert_snapshot(snapshot)
    return snapshot


class ScriptedScorer:
    """Deterministic test scorer with a scripted per-item outcome."""

    scorer_id = "m1a.test.scripted.v0"

    def __init__(
        self,
        status: str = "CORRECT",
        *,
        per_item: dict[str, str] | None = None,
        raise_error: bool = False,
    ) -> None:
        self._default_status = status
        self._per_item = dict(per_item or {})
        self._raise_error = raise_error
        self.calls: list[tuple[str, str, object, str | None]] = []

    def score(
        self,
        item: AssessmentItem,
        learner_id: str,
        response: str | dict,
        *,
        result_id: str | None = None,
    ) -> AssessmentResult:
        self.calls.append((item.item_id, learner_id, response, result_id))
        if self._raise_error:
            raise RuntimeError("scripted scorer infrastructure failure")
        status = self._per_item.get(item.item_id, self._default_status)
        score = {"CORRECT": 1.0, "INCORRECT": 0.0, "PARTIAL": 0.5, "NEEDS_REVIEW": None}.get(
            status
        )
        return AssessmentResult(
            result_id=result_id or f"result:{item.item_id}",
            item_id=item.item_id,
            learner_id=learner_id,
            status=status,
            score=score,
            max_score=item.max_score,
            scorer_id=self.scorer_id,
            failure_reason="" if status == "CORRECT" else f"SCRIPTED:{status}",
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


def start(
    engine: TeachingSessionEngine,
    learner_id: str,
    objective: LearningObjective,
) -> tuple[SessionStateLike, LearnerGoal]:  # noqa: F821 - typing helper alias below
    goal = make_goal(learner_id, objective)
    state = engine.start_session(learner_id, goal, objective)
    return state, goal


# A tiny alias so the helper signature above stays readable without importing
# the record type twice (the annotation is resolved lazily by ``from __future__``).
SessionStateLike = object


# ---------------------------------------------------------------------------
# Session creation
# ---------------------------------------------------------------------------
def test_start_session_creates_diagnose_state(
    adapter, graph, repository, objective
) -> None:
    engine = make_engine(adapter, graph, repository)
    state, _goal = start(engine, "learner.a", objective)
    assert state.phase == "DIAGNOSE"
    assert state.turn_index == 0
    assert state.pending_item_id is not None
    assert state.session_id.startswith("session:learner.a:")

    action = engine.current_action(state.session_id)
    assert action.kind == "DIAGNOSE"
    assert action.item_id == state.pending_item_id
    assert action.node_ids
    events = repository.list_events("learner.a")
    event_types = [event.event_type for event in events]
    assert "SESSION_STARTED" in event_types
    assert "PLAN_CREATED" in event_types
    assert "ACTION_TAKEN" in event_types
    started = next(event for event in events if event.event_type == "SESSION_STARTED")
    assert started.payload["phase"] == "DIAGNOSE"
    assert repository.get_goal(state.goal_id) is not None


def test_start_session_is_idempotent(adapter, graph, repository, objective) -> None:
    engine = make_engine(adapter, graph, repository)
    state, goal = start(engine, "learner.a", objective)
    event_count = len(repository.list_events("learner.a"))
    again = engine.start_session("learner.a", goal, objective)
    assert again == state
    assert len(repository.list_events("learner.a")) == event_count


def test_start_session_validates_identity(adapter, graph, repository, objective) -> None:
    engine = make_engine(adapter, graph, repository)
    goal = make_goal("learner.a", objective)
    with pytest.raises(ValidationError):
        engine.start_session("learner.b", goal, objective)
    wrong_goal = LearnerGoal(
        goal_id="goal-x",
        learner_id="learner.a",
        objective_id="obj.unknown",
        created_at=TS,
    )
    with pytest.raises(ValidationError):
        engine.start_session("learner.a", wrong_goal, objective)


def test_start_session_when_goal_already_complete(
    adapter, graph, repository, objective
) -> None:
    spec = {
        node_id: (0.9, 3, 0.9) for node_id in adapter_graph_node_ids(adapter)
    }
    seed_snapshot(repository, "learner.done", spec)
    engine = make_engine(adapter, graph, repository)
    state, _goal = start(engine, "learner.done", objective)
    assert state.phase == "COMPLETE"
    assert state.pending_item_id is None
    action = engine.current_action(state.session_id)
    assert action.kind == "GOAL_COMPLETE"
    assert "GOAL_COMPLETED" in [event.event_type for event in repository.list_events("learner.done")]
    with pytest.raises(ConflictError):
        engine.submit_response(state.session_id, "item.bs.mcq.001", "A")
    with pytest.raises(ConflictError):
        engine.advance_session(state.session_id)


def adapter_graph_node_ids(adapter: CFBinarySearchDomainAdapter) -> list[str]:
    return [node.node_id for node in adapter.knowledge_nodes()]


# ---------------------------------------------------------------------------
# Closed loop and evidence traceability
# ---------------------------------------------------------------------------
def test_full_closed_loop_runs_and_records_trace(
    adapter, graph, repository, objective
) -> None:
    engine = make_engine(adapter, graph, repository)
    state, _goal = start(engine, "learner.loop", objective)
    final = engine.run_until_goal(
        state.session_id, max_turns=8, responder=lambda item, session: "A"
    )
    phases = engine.phase_history(state.session_id)
    assert "DIAGNOSE" in phases
    assert "ASSESS" in phases
    assert "UPDATE" in phases
    assert "REVIEW" in phases
    assert "TEACH" in phases or "PRACTICE" in phases
    assert final.phase in {"REVIEW", "DIAGNOSE", "TEACH", "PRACTICE", "ASSESS", "COMPLETE"}

    events = repository.list_events("learner.loop")
    action_events = [event for event in events if event.event_type == "ACTION_TAKEN"]
    assessed = [event for event in events if event.event_type == "ASSESSED"]
    mastery_events = [event for event in events if event.event_type == "MASTERY_UPDATED"]
    assert action_events, "teaching actions must be recorded"
    assert assessed, "assessments must be recorded"
    assert mastery_events, "mastery updates must be recorded"
    for event in action_events:
        assert event.payload["action_kind"] in {
            "DIAGNOSE",
            "EXPLAIN",
            "HINT",
            "PRACTICE",
            "REVIEW",
            "RETEACH",
            "REASSESS",
        }
        assert isinstance(event.payload["node_ids"], list)
    for event in assessed:
        assert event.payload["status"] in {"CORRECT", "INCORRECT", "PARTIAL"}
        assert "result" in event.payload
    snapshot = repository.get_snapshot("learner.loop")
    assert snapshot is not None
    assert snapshot.revision == len(assessed)
    assert engine.history.verify_rebuild("learner.loop")


def test_correct_answer_updates_mastery_through_evidence(
    adapter, graph, repository, objective
) -> None:
    engine = make_engine(adapter, graph, repository)
    state, _goal = start(engine, "learner.correct", objective)
    action = engine.current_action(state.session_id)
    item = action.item_id
    assert item is not None
    result = engine.submit_response(state.session_id, item, "A")
    assert result.status == "CORRECT"
    snapshot = repository.get_snapshot("learner.correct")
    assert snapshot is not None
    assert snapshot.revision == 1
    node_ids = set(_item_node_ids(adapter, item))
    assert set(snapshot.masteries) == node_ids
    assert all(estimate.value > 0.0 for estimate in snapshot.masteries.values())
    assert snapshot.error_counts == {}
    assert item in snapshot.completed_item_ids
    assert engine.history.verify_rebuild("learner.correct")
    after = repository.load_session(state.session_id)
    assert after.phase == "REVIEW"
    assert after.pending_item_id is None


def test_incorrect_answer_records_error_evidence_not_mastery_raise(
    adapter, graph, repository, objective
) -> None:
    engine = make_engine(adapter, graph, repository, scorer=ScriptedScorer("INCORRECT"))
    state, _goal = start(engine, "learner.wrong", objective)
    action = engine.current_action(state.session_id)
    assert action.item_id is not None
    result = engine.submit_response(state.session_id, action.item_id, "A")
    assert result.status == "INCORRECT"
    snapshot = repository.get_snapshot("learner.wrong")
    assert snapshot is not None
    assert snapshot.revision == 1
    assert snapshot.error_counts, "an INCORRECT outcome must record an error counter"
    assert all(estimate.value == 0.0 for estimate in snapshot.masteries.values())


def test_action_ids_and_session_ids_are_deterministic(
    adapter, graph, repository, objective, tmp_path: Path
) -> None:
    other_repo = SqliteRepository(tmp_path / "other.sqlite")
    try:
        first = make_engine(adapter, graph, repository)
        second = make_engine(adapter, graph, other_repo)
        state_a, _goal = start(first, "learner.det", objective)
        state_b, _goal_b = start(second, "learner.det", objective)
        assert state_a.session_id == state_b.session_id
        action_a = first.current_action(state_a.session_id)
        action_b = second.current_action(state_b.session_id)
        assert action_a.action_id == action_b.action_id
        assert action_a.kind == action_b.kind
        assert action_a.item_id == action_b.item_id
    finally:
        other_repo.close()


# ---------------------------------------------------------------------------
# EVAL_ERROR isolation and idempotency
# ---------------------------------------------------------------------------
def test_raising_scorer_is_eval_error_and_never_evidence(
    adapter, graph, repository, objective
) -> None:
    scorer = ScriptedScorer(raise_error=True)
    engine = make_engine(
        adapter, graph, repository, scorer=scorer, policy=SessionPolicy(eval_error_retry_limit=2)
    )
    state, _goal = start(engine, "learner.eval", objective)
    action = engine.current_action(state.session_id)
    assert action.item_id is not None
    result = engine.submit_response(state.session_id, action.item_id, "A")
    assert result.status == "EVAL_ERROR"
    assert repository.get_snapshot("learner.eval") is None
    events = repository.list_events("learner.eval")
    assert any(event.event_type == "ERROR" for event in events)
    assert not any(event.event_type == "MASTERY_UPDATED" for event in events)
    assert not any(event.event_type == "ASSESSED" for event in events)
    after = repository.load_session(state.session_id)
    assert after.phase == "DIAGNOSE"
    assert after.pending_item_id == action.item_id

    # Retry the same pending item until the retry budget is exhausted.
    current = after
    for _attempt in range(2):
        current = repository.load_session(state.session_id)
        assert current.pending_item_id is not None
        retry = engine.submit_response(state.session_id, current.pending_item_id, "A")
        assert retry.status == "EVAL_ERROR"
    final = repository.load_session(state.session_id)
    assert final.phase == "REVIEW"
    assert final.pending_item_id is None
    errors = [event for event in repository.list_events("learner.eval") if event.event_type == "ERROR"]
    assert errors[-1].payload["retry_exhausted"] is True
    assert repository.get_snapshot("learner.eval") is None
    assert engine.history.verify_rebuild("learner.eval")


def test_returned_eval_error_status_is_isolated(
    adapter, graph, repository, objective
) -> None:
    scorer = ScriptedScorer("EVAL_ERROR")
    engine = make_engine(adapter, graph, repository, scorer=scorer)
    state, _goal = start(engine, "learner.eval2", objective)
    action = engine.current_action(state.session_id)
    result = engine.submit_response(state.session_id, action.item_id, "A")
    assert result.status == "EVAL_ERROR"
    assert repository.get_snapshot("learner.eval2") is None
    assert engine.history.verify_rebuild("learner.eval2")


def test_duplicate_submit_with_same_result_id_is_idempotent(
    adapter, graph, repository, objective
) -> None:
    engine = make_engine(adapter, graph, repository)
    state, _goal = start(engine, "learner.idem", objective)
    action = engine.current_action(state.session_id)
    assert action.item_id is not None
    first = engine.submit_response(
        state.session_id, action.item_id, "A", result_id="manual.result.1"
    )
    revision = repository.get_snapshot("learner.idem").revision
    event_count = len(repository.list_events("learner.idem"))
    second = engine.submit_response(
        state.session_id, action.item_id, "A", result_id="manual.result.1"
    )
    assert second == first
    assert repository.get_snapshot("learner.idem").revision == revision
    assert len(repository.list_events("learner.idem")) == event_count


# ---------------------------------------------------------------------------
# Pause / resume / restart recovery
# ---------------------------------------------------------------------------
def test_pause_resume_preserves_state_and_pending_item(
    adapter, graph, repository, objective
) -> None:
    engine = make_engine(adapter, graph, repository)
    state, goal = start(engine, "learner.pause", objective)
    action = engine.current_action(state.session_id)
    paused = engine.pause_session(state.session_id)
    assert paused.phase == "PAUSED"
    assert paused.pending_item_id == action.item_id == state.pending_item_id
    assert repository.load_session(state.session_id) == paused
    with pytest.raises(ConflictError):
        engine.current_action(state.session_id)
    with pytest.raises(ConflictError):
        engine.advance_session(state.session_id)
    with pytest.raises(ConflictError):
        engine.submit_response(state.session_id, action.item_id, "A")

    new_engine = make_engine(adapter, graph, repository)
    resumed = new_engine.resume_session(state.session_id)
    assert resumed.phase == "DIAGNOSE"
    assert resumed.pending_item_id == paused.pending_item_id
    assert new_engine.current_action(state.session_id) == action
    result = new_engine.submit_response(state.session_id, resumed.pending_item_id, "A")
    assert result.status == "CORRECT"
    assert new_engine.history.verify_rebuild("learner.pause")
    # A second resume is an illegal transition.
    with pytest.raises(ConflictError):
        new_engine.resume_session(state.session_id)


def test_restart_mid_session_recovers_identically(
    adapter, graph, repository, objective
) -> None:
    engine = make_engine(adapter, graph, repository)
    state, goal = start(engine, "learner.restart", objective)
    action = engine.current_action(state.session_id)
    engine.submit_response(state.session_id, action.item_id, "A")
    snapshot_before = repository.get_snapshot("learner.restart")
    session_before = repository.load_session(state.session_id)

    new_engine = make_engine(adapter, graph, repository)
    loaded = repository.load_session(state.session_id)
    assert loaded == session_before
    assert repository.get_snapshot("learner.restart") == snapshot_before
    assert new_engine.history.verify_rebuild("learner.restart")
    next_action = new_engine.current_action(state.session_id)
    assert next_action.action_id
    assert next_action.item_id is not None
    result = new_engine.submit_response(state.session_id, next_action.item_id, "A")
    assert result.status == "CORRECT"
    assert new_engine.history.verify_rebuild("learner.restart")


# ---------------------------------------------------------------------------
# Goal completion
# ---------------------------------------------------------------------------
def test_goal_completion_reaches_complete_phase(
    adapter, graph, repository, objective
) -> None:
    # Every prerequisite is mastered; the two required nodes are one correct
    # assessment away from the success threshold.
    spec = {node_id: (0.9, 3, 0.9) for node_id in adapter_graph_node_ids(adapter)}
    spec["cf.search.binary"] = (0.65, 1, 0.6)
    spec["cf.search.boundary"] = (0.65, 1, 0.6)
    seed_snapshot(repository, "learner.complete", spec)
    engine = make_engine(adapter, graph, repository)
    state, _goal = start(engine, "learner.complete", objective)
    final = engine.run_until_goal(
        state.session_id, max_turns=8, responder=lambda item, session: "A"
    )
    assert final.phase == "COMPLETE"
    assert final.pending_item_id is None
    action = engine.current_action(state.session_id)
    assert action.kind == "GOAL_COMPLETE"
    events = repository.list_events("learner.complete")
    assert any(event.event_type == "GOAL_COMPLETED" for event in events)
    assessed = [event for event in events if event.event_type == "ASSESSED"]
    assert assessed, "completion must be driven by observed assessment evidence"
    # The seeded snapshot cannot be rebuilt from an empty log, so the persisted
    # revision is the seed revision plus the observed assessments.
    assert repository.get_snapshot("learner.complete").revision == 1 + len(assessed)


def test_run_until_goal_without_responder_stops_at_pending_item(
    adapter, graph, repository, objective
) -> None:
    engine = make_engine(adapter, graph, repository)
    state, _goal = start(engine, "learner.stop", objective)
    stopped = engine.run_until_goal(state.session_id, max_turns=4, responder=None)
    assert stopped.pending_item_id is not None
    assert stopped.phase in {"DIAGNOSE", "PRACTICE", "ASSESS"}


# ---------------------------------------------------------------------------
# Scorer independence from teacher text
# ---------------------------------------------------------------------------
def test_scorer_receives_only_item_and_response(
    adapter, graph, repository, objective
) -> None:
    spy = ScriptedScorer()
    engine = make_engine(adapter, graph, repository, scorer=spy)
    state, _goal = start(engine, "learner.spy", objective)
    action = engine.current_action(state.session_id)
    engine.submit_response(state.session_id, action.item_id, "A")
    assert len(spy.calls) == 1
    item_id, learner_id, response, _result_id = spy.calls[0]
    assert item_id == action.item_id
    assert learner_id == "learner.spy"
    assert response == "A"
    # The teacher's action content is presentation text: it is not passed to
    # the scorer (which only ever sees the frozen item metadata + response).
    assert action.content not in {str(part) for part in spy.calls[0][:3]}


# ---------------------------------------------------------------------------
# Failure modes
# ---------------------------------------------------------------------------
def test_unknown_session_is_not_found(adapter, graph, repository) -> None:
    engine = make_engine(adapter, graph, repository)
    with pytest.raises(NotFoundError):
        engine.current_action("session:missing")
    with pytest.raises(NotFoundError):
        engine.submit_response("session:missing", "item.bs.mcq.001", "A")
    with pytest.raises(NotFoundError):
        engine.advance_session("session:missing")
    with pytest.raises(NotFoundError):
        engine.pause_session("session:missing")
    with pytest.raises(NotFoundError):
        engine.resume_session("session:missing")


def test_invalid_repository_is_rejected(adapter, graph) -> None:
    with pytest.raises(ValidationError):
        TeachingSessionEngine(adapter, graph, object())  # type: ignore[arg-type]


def _item_node_ids(adapter: CFBinarySearchDomainAdapter, item_id: str) -> list[str]:
    for item in adapter.assessment_items():
        if item.item_id == item_id:
            return list(item.node_ids)
    raise AssertionError(f"unknown item {item_id!r}")


# ---------------------------------------------------------------------------
# Non-evidence assessment outcomes (NEEDS_REVIEW / EVAL_ERROR) and static checks
# ---------------------------------------------------------------------------
def test_needs_review_is_recorded_without_mastery_update(
    adapter, graph, repository, objective
) -> None:
    engine = make_engine(
        adapter, graph, repository, scorer=ScriptedScorer("NEEDS_REVIEW")
    )
    state, _goal = start(engine, "learner.review", objective)
    action = engine.current_action(state.session_id)
    result = engine.submit_response(state.session_id, action.item_id, "A")
    assert result.status == "NEEDS_REVIEW"
    assert repository.get_snapshot("learner.review") is None
    events = repository.list_events("learner.review")
    assessed = [event for event in events if event.event_type == "ASSESSED"]
    mastery = [event for event in events if event.event_type == "MASTERY_UPDATED"]
    assert assessed and assessed[-1].payload["status"] == "NEEDS_REVIEW"
    assert mastery and mastery[-1].payload["applied"] is False
    after = repository.load_session(state.session_id)
    assert after.phase == "REVIEW"
    assert after.pending_item_id is None
    assert engine.history.verify_rebuild("learner.review")


def test_eval_error_preserves_existing_snapshot_exactly(
    adapter, graph, repository, objective
) -> None:
    spec = {node_id: (0.9, 3, 0.9) for node_id in adapter_graph_node_ids(adapter)}
    spec["cf.search.binary"] = (0.4, 3, 0.9)
    spec["cf.search.boundary"] = (0.4, 3, 0.9)
    seed_snapshot(repository, "learner.preserve", spec)
    engine = make_engine(
        adapter,
        graph,
        repository,
        scorer=ScriptedScorer(raise_error=True),
        policy=SessionPolicy(eval_error_retry_limit=1),
    )
    state, _goal = start(engine, "learner.preserve", objective)
    sid = state.session_id
    # Drive until an item is pending (plan may start with a content action).
    for _ in range(6):
        current = repository.load_session(sid)
        if current.pending_item_id is not None:
            break
        action = engine.current_action(sid)
        if action.item_id is not None:
            continue
        engine.advance_session(sid)
    pending = repository.load_session(sid).pending_item_id
    assert pending is not None
    before = repository.get_snapshot("learner.preserve").to_dict()
    result = engine.submit_response(sid, pending, "A")
    assert result.status == "EVAL_ERROR"
    after = repository.get_snapshot("learner.preserve").to_dict()
    assert after == before, "EVAL_ERROR must not change mastery, evidence or errors"
    assert not any(
        event.event_type in {"ASSESSED", "MASTERY_UPDATED"}
        for event in repository.list_events("learner.preserve")
    )


def test_session_module_is_offline_and_scoring_free() -> None:
    import ast

    source_dir = REPO_ROOT / "m1_teacher" / "session"
    files = sorted(path for path in source_dir.rglob("*.py") if "__pycache__" not in path.parts)
    assert files
    forbidden = {
        "autoteacher_m0",
        "socket",
        "ssl",
        "urllib",
        "urllib3",
        "http",
        "requests",
        "httpx",
        "aiohttp",
    }
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert "autoteacher_m0" not in text
        assert "scoring/" not in text, f"{path} references hidden scoring material"
        tree = ast.parse(text, filename=str(path))
        for node in ast.walk(tree):
            imported: list[str] = []
            if isinstance(node, ast.Import):
                imported = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imported = [node.module]
            for module in imported:
                assert module.split(".")[0] not in forbidden, (path, module)


# ---------------------------------------------------------------------------
# End-to-end with the real independent DeterministicScorer
# ---------------------------------------------------------------------------
def _scoring_spec(item: AssessmentItem) -> dict:
    import json

    parts = Path(item.scoring_spec_ref).parts
    relative = Path(*parts[1:]) if parts and parts[0] == "scoring" else Path(item.scoring_spec_ref)
    return json.loads(
        (FIXTURES_DIR / "domains" / "cf_binary_search" / "scoring" / relative).read_text(
            encoding="utf-8"
        )
    )


_REFERENCE_SOLUTIONS = {
    "binary_search_exact": """\
def binary_search_exact(arr, target):
    low, high = 0, len(arr) - 1
    while low <= high:
        mid = (low + high) // 2
        if arr[mid] == target:
            return mid
        if arr[mid] < target:
            low = mid + 1
        else:
            high = mid - 1
    return -1
""",
    "lower_bound": """\
def lower_bound(arr, target):
    low, high = 0, len(arr)
    while low < high:
        mid = (low + high) // 2
        if arr[mid] < target:
            low = mid + 1
        else:
            high = mid
    return low
""",
    "first_occurrence": """\
def first_occurrence(arr, target):
    low, high = 0, len(arr) - 1
    answer = -1
    while low <= high:
        mid = (low + high) // 2
        if arr[mid] == target:
            answer = mid
            high = mid - 1
        elif arr[mid] < target:
            low = mid + 1
        else:
            high = mid - 1
    return answer
""",
    "count_occurrences": """\
def count_occurrences(arr, target):
    def bound(t, strict):
        low, high = 0, len(arr)
        while low < high:
            mid = (low + high) // 2
            if arr[mid] < t or (strict and arr[mid] == t):
                low = mid + 1
            else:
                high = mid
        return low
    return bound(target, True) - bound(target, False)
""",
    "is_non_decreasing": """\
def is_non_decreasing(arr):
    return all(arr[index] <= arr[index + 1] for index in range(len(arr) - 1))
""",
}


def correct_response(item: AssessmentItem) -> str | dict:
    """Test-only responder that answers an item correctly (reads hidden specs)."""

    spec = _scoring_spec(item)
    if item.item_type == "MCQ":
        return {"choice_index": spec["correct_option_index"]}
    if item.item_type == "CODE":
        return _REFERENCE_SOLUTIONS[spec["function_name"]]
    key_words = [group[0] for group in spec["required_concept_groups"]]
    return "；".join(key_words) + "，以上概念组齐备所以这个回答是完整的解释文本。"


def test_end_to_end_with_real_deterministic_scorer(
    adapter, graph, repository, objective
) -> None:
    engine = TeachingSessionEngine(adapter, graph, repository)  # real DeterministicScorer
    goal = make_goal("learner.e2e", objective)
    state = engine.start_session("learner.e2e", goal, objective)
    final = engine.run_until_goal(
        state.session_id, max_turns=10, responder=lambda item, session: correct_response(item)
    )
    phases = engine.phase_history(state.session_id)
    assert "DIAGNOSE" in phases
    assert "ASSESS" in phases
    assert "UPDATE" in phases
    assert "REVIEW" in phases
    events = repository.list_events("learner.e2e")
    assessed = [event for event in events if event.event_type == "ASSESSED"]
    assert assessed, "the real scorer must produce observed assessment evidence"
    scorer_ids = {event.payload["result"]["scorer_id"] for event in assessed}
    assert scorer_ids == {"m1a.deterministic.scorer.v0"}
    statuses = {event.payload["status"] for event in assessed}
    assert "CORRECT" in statuses
    snapshot = repository.get_snapshot("learner.e2e")
    assert snapshot is not None and snapshot.revision == len(assessed)
    assert engine.history.verify_rebuild("learner.e2e")
    assert final.phase in {"REVIEW", "TEACH", "PRACTICE", "ASSESS", "DIAGNOSE", "COMPLETE"}
