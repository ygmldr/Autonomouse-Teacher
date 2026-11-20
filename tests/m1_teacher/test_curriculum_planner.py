"""Tests for the B4 curriculum planner (``m1_teacher.planner``).

Two synthetic learners exercise divergent, explainable paths on the frozen
CF binary-search fixtures:

* **Student A** -- binary search understood, boundary handling weak with many
  off-by-one errors: the plan starts with boundary *practice*.
* **Student B** -- sortedness prerequisite very weak and binary search weak:
  the plan starts with HARD-prerequisite *remediation* (sortedness) before any
  target teaching.

Everything is deterministic: the same inputs must produce the same plan,
including record ids and timestamps (no wall clock).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from m1_teacher.contracts.errors import ValidationError
from m1_teacher.contracts.types import (
    CurriculumPlan,
    HistoryEvent,
    LearnerGoal,
    LearnerSnapshot,
    LearningObjective,
    MasteryEstimate,
    PlanStep,
    Reason,
    SESSION_PHASE_VALUES,
    TEACHING_ACTION_KIND_VALUES,
)
from m1_teacher.domains import CFBinarySearchDomainAdapter
from m1_teacher.knowledge import KnowledgeGraph
from m1_teacher.planner import CurriculumPlanner, PlannerPolicy

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = REPO_ROOT / "fixtures" / "m1_teacher"
T0 = "2026-11-20T00:00:00Z"

REASON_CODES = frozenset(
    {
        "GOAL_COMPLETE",
        "GOAL_NOT_COMPLETE",
        "REMEDIATE_HARD_PREREQUISITE",
        "PRACTICE_HARD_PREREQUISITE",
        "REMEDIATE_SOFT_PREREQUISITE",
        "PRACTICE_SOFT_PREREQUISITE",
        "REASSESS_STUCK_NODE",
        "TEACH_TARGET_NODE",
        "PRACTICE_TARGET_NODE",
        "ASSESS_PROGRESS",
        "REVIEW_DUE",
        "REVIEW_REPEATED_ERRORS",
        "FALLBACK_CONTINUE",
    }
)

STUDENT_A_SPEC = {
    "cf.array.basics": (0.90, 4, 0.90),
    "cf.sort.sortedness": (0.85, 4, 0.90),
    "cf.search.linear": (0.80, 3, 0.85),
    "cf.search.binary": (0.85, 4, 0.90),
    "cf.search.boundary": (0.25, 2, 0.60),
    "cf.search.lower_upper": (0.15, 1, 0.50),
    "cf.complexity.log": (0.30, 1, 0.50),
    "cf.debug.edge_cases": (0.20, 1, 0.50),
}
STUDENT_A_ERRORS = {"cf.search.boundary": 3, "off_by_one": 2}

STUDENT_B_SPEC = {
    "cf.array.basics": (0.70, 3, 0.85),
    "cf.sort.sortedness": (0.10, 2, 0.50),
    "cf.search.linear": (0.70, 2, 0.80),
    "cf.search.binary": (0.20, 1, 0.40),
    "cf.search.boundary": (0.05, 0, 0.10),
    "cf.search.lower_upper": (0.00, 0, 0.10),
    "cf.complexity.log": (0.00, 0, 0.10),
    "cf.debug.edge_cases": (0.00, 0, 0.10),
}
STUDENT_B_ERRORS = {"cf.search.binary": 2}


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


@pytest.fixture(scope="module")
def planner(adapter, graph) -> CurriculumPlanner:
    return CurriculumPlanner(adapter, graph)


def make_goal(learner_id: str, objective: LearningObjective) -> LearnerGoal:
    return LearnerGoal(
        goal_id=f"goal-{learner_id}",
        learner_id=learner_id,
        objective_id=objective.objective_id,
        created_at=T0,
    )


def make_snapshot(
    learner_id: str,
    mastery_spec: dict[str, tuple[float, int, float]],
    error_counts: dict[str, int] | None = None,
    *,
    mastery_updated: str = T0,
    snapshot_updated: str = T0,
    completed_item_ids: list[str] | None = None,
) -> LearnerSnapshot:
    masteries = {
        node_id: MasteryEstimate(
            node_id=node_id,
            value=value,
            confidence=confidence,
            evidence_count=evidence_count,
            created_at=mastery_updated,
            updated_at=mastery_updated,
        )
        for node_id, (value, evidence_count, confidence) in mastery_spec.items()
    }
    return LearnerSnapshot(
        learner_id=learner_id,
        masteries=masteries,
        completed_item_ids=list(completed_item_ids or []),
        error_counts=dict(error_counts or {}),
        revision=1,
        created_at=snapshot_updated,
        updated_at=snapshot_updated,
    )


def make_event(
    event_id: str,
    seq: int,
    event_type: str,
    payload: dict,
    learner_id: str,
) -> HistoryEvent:
    return HistoryEvent(
        event_id=event_id,
        learner_id=learner_id,
        session_id="session-1",
        seq=seq,
        event_type=event_type,
        payload=payload,
        created_at=T0,
    )


def student_a_snapshot() -> LearnerSnapshot:
    return make_snapshot("learner-A", STUDENT_A_SPEC, STUDENT_A_ERRORS)


def student_a_history() -> list[HistoryEvent]:
    return [
        make_event(
            "a-0", 0, "ASSESSED",
            {"node_ids": ["cf.search.boundary"], "status": "CORRECT"}, "learner-A",
        ),
        make_event(
            "a-1", 1, "ASSESSED",
            {"node_ids": ["cf.search.boundary"], "status": "INCORRECT"}, "learner-A",
        ),
    ]


def student_b_snapshot() -> LearnerSnapshot:
    return make_snapshot("learner-B", STUDENT_B_SPEC, STUDENT_B_ERRORS)


def student_b_history() -> list[HistoryEvent]:
    return [
        make_event(
            "b-0", 0, "ASSESSED",
            {"node_ids": ["cf.sort.sortedness"], "status": "INCORRECT"}, "learner-B",
        )
    ]


def study_nodes(graph: KnowledgeGraph, objective: LearningObjective) -> set[str]:
    targets = list(objective.target_node_ids)
    return set(targets) | graph.prerequisite_closure(targets, kinds=("HARD", "SOFT"))


# ---------------------------------------------------------------------------
# Student A vs Student B: divergent, sensible plans
# ---------------------------------------------------------------------------


def test_student_a_plan_starts_with_boundary_practice(planner, objective) -> None:
    plan = planner.plan(make_goal("learner-A", objective), objective, student_a_snapshot(),
                        student_a_history())
    first = plan.steps[0]
    assert first.phase == "PRACTICE"
    assert first.action_kind == "PRACTICE"
    assert first.node_ids == ["cf.search.boundary"]
    assert first.item_id in {
        "item.bs.mcq.005", "item.bs.code.003", "item.bs.short.001"
    }
    assert first.rationale.code == "PRACTICE_TARGET_NODE"
    assert "error pressure" in first.rationale.detail
    assert "cf.search.boundary" in first.rationale.detail
    # Boundary is a target: no HARD-prerequisite remediation should come first.
    assert not any(
        step.rationale.code == "REMEDIATE_HARD_PREREQUISITE" for step in plan.steps
    )


def test_student_b_plan_starts_with_hard_prerequisite_remediation(planner, objective) -> None:
    plan = planner.plan(make_goal("learner-B", objective), objective, student_b_snapshot(),
                        student_b_history())
    first = plan.steps[0]
    assert first.phase == "TEACH"
    assert first.action_kind == "RETEACH"
    assert first.node_ids == ["cf.sort.sortedness"]
    assert first.rationale.code == "REMEDIATE_HARD_PREREQUISITE"
    assert "cf.sort.sortedness" in first.rationale.detail
    assert "cf.search.binary" in first.rationale.detail  # blocking target named


def test_student_a_and_b_plans_diverge(planner, objective) -> None:
    goal_a = make_goal("learner-A", objective)
    goal_b = make_goal("learner-B", objective)
    plan_a = planner.plan(goal_a, objective, student_a_snapshot(), student_a_history())
    plan_b = planner.plan(goal_b, objective, student_b_snapshot(), student_b_history())
    assert plan_a.plan_id != plan_b.plan_id
    assert [step.node_ids for step in plan_a.steps] != [step.node_ids for step in plan_b.steps]
    assert plan_a.steps[0].node_ids != plan_b.steps[0].node_ids
    assert len(plan_a.steps) <= 8 and len(plan_b.steps) <= 8


def test_hard_remediation_precedes_target_teaching(planner, objective) -> None:
    plan = planner.plan(make_goal("learner-B", objective), objective, student_b_snapshot(),
                        student_b_history())
    remediation = [
        index for index, step in enumerate(plan.steps)
        if step.rationale.code in {
            "REMEDIATE_HARD_PREREQUISITE",
            "PRACTICE_HARD_PREREQUISITE",
            "REASSESS_STUCK_NODE",
        }
    ]
    teaching = [
        index for index, step in enumerate(plan.steps)
        if step.rationale.code == "TEACH_TARGET_NODE"
    ]
    assert remediation
    assert teaching
    assert max(remediation) < min(teaching)


# ---------------------------------------------------------------------------
# Step structure and explainability
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("learner", ["learner-A", "learner-B"])
def test_every_step_is_structured_and_in_scope(planner, graph, objective, learner) -> None:
    snapshot = student_a_snapshot() if learner == "learner-A" else student_b_snapshot()
    history = student_a_history() if learner == "learner-A" else student_b_history()
    plan = planner.plan(make_goal(learner, objective), objective, snapshot, history)
    assert isinstance(plan, CurriculumPlan)
    assert plan.policy_version == "m1a.planner.v0"
    assert plan.created_at == T0
    assert plan.learner_id == learner
    assert plan.objective_id == objective.objective_id
    assert plan.steps
    scope = study_nodes(graph, objective)
    step_ids: set[str] = set()
    for ordinal, step in enumerate(plan.steps):
        assert isinstance(step, PlanStep)
        assert step.ordinal == ordinal
        assert step.step_id not in step_ids
        step_ids.add(step.step_id)
        assert step.phase in SESSION_PHASE_VALUES
        assert step.action_kind in TEACHING_ACTION_KIND_VALUES
        assert step.node_ids and set(step.node_ids) <= scope
        assert isinstance(step.rationale, Reason)
        assert step.rationale.code in REASON_CODES
        assert step.rationale.node_ids
        assert set(step.rationale.node_ids) <= scope
        assert len(step.rationale.detail) > 20
        assert step.rationale.policy_version == "m1a.planner.v0"
        assert step.created_at == T0
        if step.item_id is not None:
            assert step.action_kind in {"PRACTICE", "REASSESS", "DIAGNOSE", "REVIEW"}
        if step.action_kind == "GOAL_COMPLETE":
            assert step.phase == "COMPLETE"


def test_plan_serialisation_roundtrip(planner, objective) -> None:
    plan = planner.plan(make_goal("learner-A", objective), objective, student_a_snapshot(),
                        student_a_history())
    restored = CurriculumPlan.from_dict(plan.to_dict())
    assert restored == plan
    assert [step.to_dict() for step in restored.steps] == [
        step.to_dict() for step in plan.steps
    ]


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_same_inputs_produce_identical_plan(planner, objective) -> None:
    goal = make_goal("learner-A", objective)
    first = planner.plan(goal, objective, student_a_snapshot(), student_a_history())
    second = planner.plan(goal, objective, student_a_snapshot(), student_a_history())
    assert first.to_dict() == second.to_dict()
    assert first.plan_id == second.plan_id


def test_history_order_does_not_change_plan(planner, objective) -> None:
    goal = make_goal("learner-A", objective)
    forward = planner.plan(goal, objective, student_a_snapshot(), student_a_history())
    reversed_plan = planner.plan(
        goal, objective, student_a_snapshot(), list(reversed(student_a_history()))
    )
    assert forward.to_dict() == reversed_plan.to_dict()


def test_max_steps_is_enforced(planner, adapter, graph, objective) -> None:
    goal = make_goal("learner-B", objective)
    capped = CurriculumPlanner(
        adapter, graph, PlannerPolicy(max_steps=3)
    ).plan(goal, objective, student_b_snapshot(), student_b_history())
    assert len(capped.steps) <= 3
    assert [step.ordinal for step in capped.steps] == list(range(len(capped.steps)))
    default = planner.plan(goal, objective, student_b_snapshot(), student_b_history())
    assert len(default.steps) <= PlannerPolicy().max_steps


# ---------------------------------------------------------------------------
# Goal completion judgment
# ---------------------------------------------------------------------------


def test_goal_completion_uses_observed_mastery_and_error_rates(adapter, objective) -> None:
    planner = CurriculumPlanner(adapter, KnowledgeGraph(
        adapter.knowledge_nodes(), adapter.prerequisite_edges()
    ))
    complete_spec = {
        "cf.search.binary": (0.90, 3, 0.90),
        "cf.search.boundary": (0.85, 3, 0.90),
    }
    complete, reason = planner.check_goal_completion(
        objective, make_snapshot("learner-A", complete_spec)
    )
    assert complete is True
    assert reason.code == "GOAL_COMPLETE"
    assert reason.node_ids == ["cf.search.binary", "cf.search.boundary"]
    assert "success_criteria" in reason.detail
    plan = planner.plan(
        make_goal("learner-A", objective), objective, make_snapshot("learner-A", complete_spec)
    )
    assert len(plan.steps) == 1
    assert plan.steps[0].phase == "COMPLETE"
    assert plan.steps[0].action_kind == "GOAL_COMPLETE"
    assert plan.steps[0].rationale.code == "GOAL_COMPLETE"
    assert plan.steps[0].item_id is None


def test_goal_completion_requires_success_criteria(adapter, objective) -> None:
    planner = CurriculumPlanner(adapter, KnowledgeGraph(
        adapter.knowledge_nodes(), adapter.prerequisite_edges()
    ))
    # Boundary below the objective's min_mastery -> not complete.
    incomplete_spec = {
        "cf.search.binary": (0.90, 3, 0.90),
        "cf.search.boundary": (0.40, 3, 0.90),
    }
    complete, reason = planner.check_goal_completion(
        objective, make_snapshot("learner-A", incomplete_spec)
    )
    assert complete is False
    assert reason.code == "GOAL_NOT_COMPLETE"
    assert "need >= 0.70" in reason.detail
    plan = planner.plan(
        make_goal("learner-A", objective), objective, make_snapshot("learner-A", incomplete_spec)
    )
    assert not any(step.action_kind == "GOAL_COMPLETE" for step in plan.steps)


def test_high_error_rate_blocks_completion(adapter, objective) -> None:
    planner = CurriculumPlanner(adapter, KnowledgeGraph(
        adapter.knowledge_nodes(), adapter.prerequisite_edges()
    ))
    spec = {
        "cf.search.binary": (0.90, 3, 0.90),
        "cf.search.boundary": (0.90, 3, 0.90),
    }
    error_counts = {"cf.search.binary": 2}  # 2/3 = 0.67 > max_error_rate 0.3
    complete, reason = planner.check_goal_completion(
        objective, make_snapshot("learner-A", spec, error_counts)
    )
    assert complete is False
    assert reason.code == "GOAL_NOT_COMPLETE"
    assert "error_rate" in reason.detail


def test_learner_claims_and_text_do_not_complete_goal(adapter, objective) -> None:
    planner = CurriculumPlanner(adapter, KnowledgeGraph(
        adapter.knowledge_nodes(), adapter.prerequisite_edges()
    ))
    snapshot = make_snapshot("learner-A", {})
    complete, reason = planner.check_goal_completion(objective, snapshot)
    assert complete is False
    claim_history = [
        make_event(
            "claim-1",
            1,
            "GOAL_COMPLETED",
            {"student_says_understood": True, "claimed_mastery": 1.0},
            "learner-A",
        )
    ]
    plan = planner.plan(
        make_goal("learner-A", objective), objective, snapshot, claim_history
    )
    assert not any(step.action_kind == "GOAL_COMPLETE" for step in plan.steps)
    # The learner's text claim never becomes evidence: no step cites it and the
    # plan still works from the (empty) observed snapshot.
    assert all(
        "claim" not in step.rationale.detail.lower()
        and "student_says_understood" not in step.rationale.detail
        for step in plan.steps
    )


# ---------------------------------------------------------------------------
# Review scheduling with fixed timestamps / turns
# ---------------------------------------------------------------------------


def _mastered_except_boundary_spec() -> dict[str, tuple[float, int, float]]:
    return {
        "cf.array.basics": (0.90, 3, 0.90),
        "cf.sort.sortedness": (0.90, 3, 0.90),
        "cf.search.linear": (0.90, 3, 0.90),
        "cf.search.binary": (0.90, 3, 0.90),
        "cf.search.boundary": (0.20, 2, 0.60),
        "cf.search.lower_upper": (0.90, 3, 0.90),
        "cf.complexity.log": (0.90, 3, 0.90),
    }


def test_review_not_due_when_evidence_is_recent(planner, objective) -> None:
    snapshot = make_snapshot(
        "learner-A", _mastered_except_boundary_spec(), snapshot_updated=T0, mastery_updated=T0
    )
    plan = planner.plan(make_goal("learner-A", objective), objective, snapshot)
    assert not any(
        step.rationale.code in {"REVIEW_DUE", "REVIEW_REPEATED_ERRORS"} for step in plan.steps
    )


def test_review_due_when_timestamp_gap_exceeds_interval(planner, objective) -> None:
    old = "2026-11-15T00:00:00Z"  # 120 h before snapshot.updated_at > 72 h interval
    snapshot = make_snapshot(
        "learner-A", _mastered_except_boundary_spec(),
        snapshot_updated=T0, mastery_updated=old,
    )
    plan = planner.plan(make_goal("learner-A", objective), objective, snapshot)
    review_steps = [
        step for step in plan.steps if step.rationale.code == "REVIEW_DUE"
    ]
    assert review_steps
    assert review_steps[0].phase == "REVIEW"
    assert review_steps[0].action_kind == "REVIEW"
    assert review_steps[0].node_ids


def test_review_due_after_configured_history_turns(planner, objective) -> None:
    history = [
        make_event(
            "t-0", 0, "ASSESSED",
            {"node_ids": ["cf.search.binary"], "status": "CORRECT"}, "learner-A",
        ),
        make_event("t-1", 1, "ITEM_PRESENTED", {"node_ids": ["cf.search.binary"]}, "learner-A"),
        make_event("t-2", 2, "ITEM_PRESENTED", {"node_ids": ["cf.search.binary"]}, "learner-A"),
        make_event("t-3", 3, "ITEM_PRESENTED", {"node_ids": ["cf.search.binary"]}, "learner-A"),
    ]
    snapshot = make_snapshot(
        "learner-A", _mastered_except_boundary_spec(), snapshot_updated=T0, mastery_updated=T0
    )
    plan = planner.plan(make_goal("learner-A", objective), objective, snapshot, history)
    review_steps = [step for step in plan.steps if step.rationale.code == "REVIEW_DUE"]
    assert review_steps
    assert any("cf.search.binary" in step.node_ids for step in review_steps)


def test_recent_evidence_suppresses_turn_based_review(planner, objective) -> None:
    history = [
        make_event("t-0", 0, "ITEM_PRESENTED", {"node_ids": ["cf.search.binary"]}, "learner-A"),
        make_event("t-1", 1, "ITEM_PRESENTED", {"node_ids": ["cf.search.binary"]}, "learner-A"),
        make_event(
            "t-2", 2, "ASSESSED",
            {"node_ids": ["cf.search.binary"], "status": "CORRECT"}, "learner-A",
        ),
    ]
    snapshot = make_snapshot(
        "learner-A", _mastered_except_boundary_spec(), snapshot_updated=T0, mastery_updated=T0
    )
    plan = planner.plan(make_goal("learner-A", objective), objective, snapshot, history)
    assert not any(step.rationale.code == "REVIEW_DUE" for step in plan.steps)


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


def test_invalid_inputs_fail_closed(planner, objective) -> None:
    snapshot = student_a_snapshot()
    goal = make_goal("learner-A", objective)
    with pytest.raises(ValidationError):
        planner.plan(goal, objective, make_snapshot("someone-else", STUDENT_A_SPEC))
    with pytest.raises(ValidationError):
        planner.plan(goal, objective, snapshot, history="not-a-list")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        planner.plan(goal, objective, snapshot, history=[{"event_id": "x"}])  # type: ignore[list-item]
    with pytest.raises(ValidationError):
        planner.check_goal_completion(objective, object())  # type: ignore[arg-type]
