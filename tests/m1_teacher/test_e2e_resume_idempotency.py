"""B-PR5 robustness tests: pause/restart recovery, idempotency, EVAL_ERROR
isolation, hidden-label isolation and learner-model arithmetic.

All components are the real frozen PR1-PR4 implementations.  Student outcomes
come from deterministic test scorers (``MOCK`` evidence) except the explicit
EVAL_ERROR tests, which exercise the real independent scorer on a temporary
fixture copy with a broken/missing scoring spec.  No test reads hidden scoring
content; the only hidden-material operation is deleting/overwriting files in a
temporary copy.
"""

from __future__ import annotations

import ast
import json
import shutil
from pathlib import Path

import pytest

from m1_teacher import demo
from m1_teacher.assessment.scorer import DeterministicScorer
from m1_teacher.contracts.errors import ConflictError, UnsupportedOperationError
from m1_teacher.contracts.types import (
    AssessmentItem,
    AssessmentResult,
    LearnerGoal,
    LearnerSnapshot,
    LearningObjective,
    MasteryEstimate,
)
from m1_teacher.diagnostic.engine import DiagnosticEngine
from m1_teacher.extensions import (
    InMemoryTeacherImprovementLog,
    NotConfiguredAutonomousResearch,
    NotConfiguredInterviewCoach,
    NotConfiguredKnowledgeFreshness,
    NotConfiguredWebApp,
    StubNotImplementedError,
    TeacherExperimentRecord,
)
from m1_teacher.learner.history import LearningHistory
from m1_teacher.learner.repository import SqliteRepository
from m1_teacher.planner.planner import CurriculumPlanner, PlannerPolicy

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "fixtures" / "m1_teacher"
TS = demo.FIXED_TIMESTAMP
LEARNER = "m1a.test.learner"
CREDIT_STEP = 0.2
"""Frozen heuristic CORRECT step (m1a.learner.mastery.heuristic.v0)."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
class FixedStatusScorer:
    """Deterministic test scorer returning one fixed status (MOCK test double)."""

    scorer_id = "m1a.test.fixed-status.v0"

    def __init__(self, status: str = "CORRECT") -> None:
        self.status = status
        self.calls: list[str] = []

    def score(
        self,
        item: AssessmentItem,
        learner_id: str,
        response: str | dict,
        *,
        result_id: str | None = None,
    ) -> AssessmentResult:
        self.calls.append(item.item_id)
        if self.status == "CORRECT":
            score, reason = float(item.max_score), ""
        elif self.status == "INCORRECT":
            score, reason = 0.0, "SCRIPTED_INCORRECT"
        else:  # pragma: no cover - tests only use CORRECT/INCORRECT here
            score, reason = None, f"SCRIPTED_{self.status}"
        return AssessmentResult(
            result_id=result_id or f"fixed:{item.item_id}:{len(self.calls):03d}",
            item_id=item.item_id,
            learner_id=learner_id,
            status=self.status,
            score=score,
            max_score=float(item.max_score),
            scorer_id=self.scorer_id,
            failure_reason=reason,
            created_at=TS,
        )


class RaisingScorer:
    """Scorer double that raises: the engine must convert this to EVAL_ERROR."""

    scorer_id = "m1a.test.raising.v0"

    def score(self, item, learner_id, response, *, result_id=None):  # noqa: ANN001
        raise RuntimeError("scripted scorer infrastructure failure")


@pytest.fixture(scope="module")
def components() -> demo.Components:
    return demo.build_components(FIXTURES)


@pytest.fixture(scope="module")
def objective(components: demo.Components) -> LearningObjective:
    return components.objective


def make_goal(objective: LearningObjective, learner_id: str = LEARNER) -> LearnerGoal:
    return LearnerGoal(
        goal_id=f"goal.{learner_id}",
        learner_id=learner_id,
        objective_id=objective.objective_id,
        created_at=TS,
    )


def start_engine(components: demo.Components, db_path: Path, *, scorer):
    repository = SqliteRepository(db_path)
    engine, history = demo._make_engine(components, repository, scorer)
    state = engine.start_session(LEARNER, make_goal(components.objective), components.objective)
    return repository, engine, history, state


@pytest.fixture(scope="module")
def scenario() -> dict:
    return demo.run_scenario(fixtures_root=FIXTURES)


def item_lookup(components: demo.Components) -> dict[str, AssessmentItem]:
    return {item.item_id: item for item in components.adapter.assessment_items()}


def expected_correct_value(evidence_count: int) -> float:
    return min(1.0, sum(CREDIT_STEP * (1.0 / (1.0 + index)) for index in range(evidence_count)))


# ---------------------------------------------------------------------------
# Pause / restart recovery (requirement 5)
# ---------------------------------------------------------------------------
def test_pause_restart_new_engine_same_db_is_consistent(tmp_path: Path) -> None:
    db_path = tmp_path / "resume.sqlite"
    summary = demo.run_student_path(
        "b", db_path=db_path, fixtures_root=FIXTURES, max_turns=10, pause_after_turns=4
    )
    resume = summary["interrupt_resume"]
    assert resume["snapshot_equal"] is True
    assert resume["plan_equal"] is True
    assert resume["paused_plan_equal"] is True
    assert resume["pending_equal"] is True
    assert resume["verify_rebuild_before_restart"] is True
    assert resume["verify_rebuild_after_restart"] is True
    phases = summary["phase_sequence"]
    assert "PAUSED" in phases
    pause_index = phases.index("PAUSED")
    resumed_phase = phases[pause_index + 1]
    assert resumed_phase == resume["pause_phase"]
    assert summary["final"]["turn_index"] >= 10


def test_resume_requires_paused_state(components: demo.Components, tmp_path: Path) -> None:
    repository, engine, history, state = start_engine(
        components, tmp_path / "db.sqlite", scorer=FixedStatusScorer()
    )
    try:
        with pytest.raises(ConflictError):
            engine.resume_session(state.session_id)
        engine.pause_session(state.session_id)
        resumed = engine.resume_session(state.session_id)
        assert resumed.phase == state.phase
        with pytest.raises(ConflictError):
            engine.resume_session(state.session_id)
    finally:
        repository.close()


# ---------------------------------------------------------------------------
# Learner model arithmetic under observed evidence (requirements 3/8)
# ---------------------------------------------------------------------------
def test_wrong_answers_never_raise_mastery(components: demo.Components, tmp_path: Path) -> None:
    repository, engine, _history, state = start_engine(
        components, tmp_path / "wrong.sqlite", scorer=FixedStatusScorer("INCORRECT")
    )
    try:
        engine.run_until_goal(
            state.session_id, max_turns=5, responder=demo.DeterministicStudentResponder()
        )
        snapshot = repository.get_snapshot(LEARNER)
        assert snapshot is not None
        assert snapshot.revision > 0
        assert all(estimate.value == 0.0 for estimate in snapshot.masteries.values())
        assert snapshot.error_counts, "INCORRECT outcomes must be recorded as errors"
        events = repository.list_events(LEARNER)
        assessed = [event for event in events if event.event_type == "ASSESSED"]
        assert snapshot.revision == len(assessed)
    finally:
        repository.close()


def test_consecutive_correct_raise_mastery_exactly(
    components: demo.Components, tmp_path: Path
) -> None:
    repository, engine, history, state = start_engine(
        components, tmp_path / "correct.sqlite", scorer=FixedStatusScorer("CORRECT")
    )
    try:
        engine.run_until_goal(
            state.session_id, max_turns=6, responder=demo.DeterministicStudentResponder()
        )
        snapshot = repository.get_snapshot(LEARNER)
        assert snapshot is not None
        items = item_lookup(components)
        evidence_counts: dict[str, int] = {}
        for event in repository.list_events(LEARNER):
            if event.event_type != "ASSESSED":
                continue
            assert event.payload.get("status") == "CORRECT"
            item = items[str(event.payload.get("item_id"))]
            for node_id in item.node_ids:
                evidence_counts[node_id] = evidence_counts.get(node_id, 0) + 1
        assert evidence_counts, "at least one node must receive observed evidence"
        for node_id, count in evidence_counts.items():
            estimate = snapshot.masteries[node_id]
            assert estimate.evidence_count == count
            assert estimate.value == pytest.approx(expected_correct_value(count), abs=1e-9)
            assert estimate.confidence == pytest.approx(1.0 - 0.5**count, abs=1e-9)
        assert max(estimate.value for estimate in snapshot.masteries.values()) > 0.3
        assert history.verify_rebuild(LEARNER) is True
    finally:
        repository.close()


def test_duplicate_result_id_updates_mastery_once(
    components: demo.Components, tmp_path: Path
) -> None:
    repository, engine, _history, state = start_engine(
        components, tmp_path / "dup.sqlite", scorer=FixedStatusScorer("CORRECT")
    )
    try:
        action = engine.current_action(state.session_id)
        assert action.item_id is not None
        first = engine.submit_response(
            state.session_id, action.item_id, "A", result_id="dup-result-1"
        )
        snapshot = repository.get_snapshot(LEARNER)
        assert snapshot is not None
        revision = snapshot.revision
        assessed_count = sum(
            1 for event in repository.list_events(LEARNER) if event.event_type == "ASSESSED"
        )
        second = engine.submit_response(
            state.session_id, action.item_id, "A (different text)", result_id="dup-result-1"
        )
        assert second.to_dict() == first.to_dict()
        again = repository.get_snapshot(LEARNER)
        assert again is not None and again.revision == revision
        assert (
            sum(1 for event in repository.list_events(LEARNER) if event.event_type == "ASSESSED")
            == assessed_count
        )
        assert engine.history.verify_rebuild(LEARNER) is True
    finally:
        repository.close()


def test_duplicate_history_event_is_idempotent(components: demo.Components, tmp_path: Path) -> None:
    repository = SqliteRepository(tmp_path / "history.sqlite")
    try:
        history = LearningHistory(repository)
        item = item_lookup(components)["item.bs.code.001"]
        result = FixedStatusScorer("CORRECT").score(item, LEARNER, "A", result_id="history-dup-1")
        first = history.apply_assessment(LEARNER, "session.seed", item, result)
        events_after_first = len(repository.list_events(LEARNER))
        second = history.apply_assessment(LEARNER, "session.seed", item, result)
        assert second.to_dict() == first.to_dict()
        assert len(repository.list_events(LEARNER)) == events_after_first
        assert history.verify_rebuild(LEARNER) is True
        existing = repository.list_events(LEARNER)[0]
        assert repository.append_event(existing) is False
    finally:
        repository.close()


# ---------------------------------------------------------------------------
# EVAL_ERROR isolation (requirement 6): never student evidence
# ---------------------------------------------------------------------------
def test_raising_scorer_is_eval_error_and_never_lowers_mastery(
    components: demo.Components, tmp_path: Path
) -> None:
    repository = SqliteRepository(tmp_path / "evalerror.sqlite")
    try:
        history = LearningHistory(repository)
        item = item_lookup(components)["item.bs.code.001"]
        seeded_result = AssessmentResult(
            result_id="seed-mastery-1",
            item_id=item.item_id,
            learner_id=LEARNER,
            status="CORRECT",
            score=float(item.max_score),
            max_score=float(item.max_score),
            scorer_id="m1a.test.seed.v0",
            created_at=TS,
        )
        seeded = history.apply_assessment(LEARNER, "session.seed", item, seeded_result)
        before = repository.get_snapshot(LEARNER)
        assert before is not None and before.revision == 1
        assert seeded.masteries["cf.search.binary"].value > 0.0

        engine, engine_history = demo._make_engine(components, repository, RaisingScorer())
        state = engine.start_session(LEARNER, make_goal(components.objective), components.objective)
        action = engine.current_action(state.session_id)
        assert action.item_id is not None
        result = engine.submit_response(state.session_id, action.item_id, "A")
        assert result.status == "EVAL_ERROR"
        after = repository.get_snapshot(LEARNER)
        assert after is not None and after.to_dict() == before.to_dict()
        assert not any(
            event.event_type == "ASSESSED" and event.session_id == state.session_id
            for event in repository.list_events(LEARNER)
        )
        errors = [
            event
            for event in repository.list_events(LEARNER)
            if event.event_type == "ERROR" and event.session_id == state.session_id
        ]
        assert errors
        assert errors[-1].payload["mastery_unchanged"] is True
        assert engine_history.verify_rebuild(LEARNER) is True
    finally:
        repository.close()


def test_missing_scoring_spec_is_eval_error_only(
    components: demo.Components, tmp_path: Path
) -> None:
    fixture_copy = tmp_path / "fixtures_copy"
    shutil.copytree(FIXTURES, fixture_copy)
    copied = demo.build_components(fixture_copy)
    repository, engine, _history, state = start_engine(
        copied,
        tmp_path / "badspec.sqlite",
        scorer=DeterministicScorer(fixture_copy, clock=lambda: TS),
    )
    try:
        action = engine.current_action(state.session_id)
        assert action.item_id is not None
        item = item_lookup(copied)[action.item_id]
        spec_path = fixture_copy / "domains" / copied.adapter.domain_id / item.scoring_spec_ref
        assert spec_path.is_file()
        spec_path.unlink()  # break the scoring infrastructure, not the learner
        before = repository.get_snapshot(LEARNER)
        statuses = [
            engine.submit_response(state.session_id, action.item_id, "A").status for _ in range(3)
        ]
        assert statuses == ["EVAL_ERROR", "EVAL_ERROR", "EVAL_ERROR"]
        after = repository.get_snapshot(LEARNER)
        assert before is None and after is None
        session_state = repository.load_session(state.session_id)
        assert session_state is not None and session_state.phase == "REVIEW"
        errors = [event for event in repository.list_events(LEARNER) if event.event_type == "ERROR"]
        assert errors and errors[-1].payload["retry_exhausted"] is True
        assert all(error.payload["mastery_unchanged"] is True for error in errors)
        assert not any(event.event_type == "ASSESSED" for event in repository.list_events(LEARNER))
    finally:
        repository.close()


# ---------------------------------------------------------------------------
# Hidden-label isolation (requirement 7)
# ---------------------------------------------------------------------------
def _stable(record_dict: dict) -> dict:
    """Record content comparison without per-load wall-clock ``created_at``."""

    return {key: value for key, value in record_dict.items() if key != "created_at"}


def _strip_scoring(copy_root: Path) -> None:
    shutil.rmtree(copy_root / "domains" / "cf_binary_search" / "scoring")


def test_teacher_components_do_not_need_hidden_scoring_material(
    components: demo.Components, tmp_path: Path
) -> None:
    no_scoring = tmp_path / "fixtures_nohidden"
    shutil.copytree(FIXTURES, no_scoring)
    _strip_scoring(no_scoring)
    stripped = demo.build_components(no_scoring)

    assert [_stable(node.to_dict()) for node in stripped.adapter.knowledge_nodes()] == [
        _stable(node.to_dict()) for node in components.adapter.knowledge_nodes()
    ]
    assert [_stable(edge.to_dict()) for edge in stripped.adapter.prerequisite_edges()] == [
        _stable(edge.to_dict()) for edge in components.adapter.prerequisite_edges()
    ]
    assert [_stable(objective.to_dict()) for objective in stripped.adapter.objectives()] == [
        _stable(objective.to_dict()) for objective in components.adapter.objectives()
    ]
    assert [_stable(item.to_dict()) for item in stripped.adapter.assessment_items()] == [
        _stable(item.to_dict()) for item in components.adapter.assessment_items()
    ]

    snapshot = LearnerSnapshot(
        learner_id=LEARNER,
        masteries={
            "cf.sort.sortedness": MasteryEstimate(
                node_id="cf.sort.sortedness",
                value=0.0,
                confidence=0.25,
                evidence_count=1,
                created_at=TS,
                updated_at=TS,
            )
        },
        revision=1,
        created_at=TS,
        updated_at=TS,
    )
    goal = make_goal(components.objective)
    for candidate in (components, stripped):
        planner = CurriculumPlanner(
            candidate.adapter,
            candidate.graph,
            PlannerPolicy(prerequisite_mastery_threshold=0.25),
        )
        plan = planner.plan(goal, candidate.objective, snapshot, [])
        assert plan.steps
        if candidate is components:
            baseline_plan = plan.to_dict()
        else:
            assert plan.to_dict() == baseline_plan

        diagnostic = DiagnosticEngine(candidate.adapter, candidate.graph)
        diagnosis = diagnostic.select_next_item(goal, candidate.objective, snapshot)
        if candidate is components:
            baseline_diagnosis = diagnosis.to_dict()
        else:
            assert diagnosis.to_dict() == baseline_diagnosis


def test_tampered_scoring_specs_do_not_change_teacher_behaviour(
    components: demo.Components, tmp_path: Path
) -> None:
    tampered_root = tmp_path / "fixtures_tampered"
    shutil.copytree(FIXTURES, tampered_root)
    scoring_dir = tampered_root / "domains" / "cf_binary_search" / "scoring"
    for path in scoring_dir.iterdir():
        path.write_text('{"kind": "TAMPERED_BY_ISOLATION_TEST"}', encoding="utf-8")
    tampered = demo.build_components(tampered_root)
    snapshot = LearnerSnapshot(
        learner_id=LEARNER,
        masteries={
            "cf.search.binary": MasteryEstimate(
                node_id="cf.search.binary",
                value=0.3,
                confidence=0.75,
                evidence_count=2,
                created_at=TS,
                updated_at=TS,
            )
        },
        revision=1,
        created_at=TS,
        updated_at=TS,
    )
    goal = make_goal(components.objective)
    baseline = CurriculumPlanner(
        components.adapter, components.graph, PlannerPolicy(prerequisite_mastery_threshold=0.25)
    ).plan(goal, components.objective, snapshot, [])
    tampered_plan = CurriculumPlanner(
        tampered.adapter, tampered.graph, PlannerPolicy(prerequisite_mastery_threshold=0.25)
    ).plan(goal, tampered.objective, snapshot, [])
    assert tampered_plan.to_dict() == baseline.to_dict()
    assert (
        DiagnosticEngine(tampered.adapter, tampered.graph)
        .select_next_item(goal, tampered.objective, snapshot)
        .to_dict()
        == DiagnosticEngine(components.adapter, components.graph)
        .select_next_item(goal, components.objective, snapshot)
        .to_dict()
    )


def test_teacher_code_references_hidden_scoring_only_in_scorer() -> None:
    offenders: list[str] = []
    for path in sorted((REPO_ROOT / "m1_teacher").rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        if "scoring/" in text and path.name != "scorer.py":
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert offenders == [], f"teacher modules reference hidden scoring paths: {offenders}"

    forbidden_modules = {
        "socket",
        "http",
        "urllib",
        "requests",
        "httpx",
        "aiohttp",
        "autoteacher_m0",
    }
    new_surfaces = [
        REPO_ROOT / "m1_teacher" / "demo.py",
        REPO_ROOT / "m1_teacher" / "cli.py",
        REPO_ROOT / "m1_teacher" / "extensions" / "__init__.py",
        REPO_ROOT / "m1_teacher" / "extensions" / "interfaces.py",
    ]
    for path in new_surfaces:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [(node.module or "").split(".")[0]]
            else:
                continue
            for name in names:
                assert name not in forbidden_modules, f"{path.name} imports forbidden {name!r}"


# ---------------------------------------------------------------------------
# Determinism of the persisted evidence at the byte level
# ---------------------------------------------------------------------------
def test_evidence_artifacts_are_byte_reproducible(scenario: dict, tmp_path: Path) -> None:
    first = demo.write_evidence(scenario, tmp_path / "a")
    second = demo.write_evidence(scenario, tmp_path / "b")
    for name in ("e2e_student_a.jsonl", "e2e_student_b.jsonl"):
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes()
    assert first["hashes"]["e2e_student_a.jsonl"] == second["hashes"]["e2e_student_a.jsonl"]
    summary = json.loads((tmp_path / "a" / "e2e_summary.json").read_text(encoding="utf-8"))
    # The summary records the hashes of the JSONL evidence files it indexes
    # (it cannot contain its own hash).
    assert summary["evidence_hashes"] == {
        name: value for name, value in first["hashes"].items() if name.endswith(".jsonl")
    }


# ---------------------------------------------------------------------------
# Next-phase interface stubs (contract only; fail closed)
# ---------------------------------------------------------------------------
def test_next_phase_interface_stubs_fail_closed() -> None:
    for stub, method, args in (
        (NotConfiguredWebApp(), "session_view", ("session-x",)),
        (NotConfiguredInterviewCoach(), "start", ("learner-x", None)),
        (NotConfiguredKnowledgeFreshness(), "classify", (None,)),
        (NotConfiguredAutonomousResearch(), "plan_task", (None,)),
    ):
        with pytest.raises(StubNotImplementedError) as excinfo:
            getattr(stub, method)(*args)
        assert excinfo.value.code == "EXTENSION_NOT_IMPLEMENTED"
    log = InMemoryTeacherImprovementLog()
    record = TeacherExperimentRecord(
        experiment_id="exp-1",
        policy_version="m1a.test.policy.v0",
        initial_state_digest="a" * 16,
        behaviour_digest="b" * 16,
        result_digest="c" * 16,
        notes=("synthetic only",),
    )
    log.record(record)
    assert log.list_records() == [record]
    with pytest.raises(UnsupportedOperationError):
        log.record(
            TeacherExperimentRecord(
                experiment_id="exp-2",
                policy_version="m1a.test.policy.v0",
                initial_state_digest="a" * 16,
                behaviour_digest="b" * 16,
                result_digest="c" * 16,
                real_effect_claim=True,
            )
        )
