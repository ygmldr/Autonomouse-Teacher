"""Explicit policy-rule tests for the B4 curriculum planner.

These tests pin the *documented* planning rules instead of merely checking that
planning runs:

1. HARD prerequisites are remediated before target teaching.
2. SOFT prerequisites are not forced back into the plan by default (opt-in only).
3. A mastered node is not reviewed again before its review interval is due.
4. At least ``reassess_after_failures`` consecutive INCORRECT assessments (or
   ``max_relearn_attempts`` RETEACH cycles) trigger ``REASSESS``.
5. An incomplete objective can never produce a ``GOAL_COMPLETE`` step.
6. Step count/order/ids are deterministic for identical inputs.
7. Changing documented policy parameters changes behaviour in the documented way.
8. The planner never reads hidden answer material, the network or M0 code.
"""

from __future__ import annotations

import ast
import shutil
from pathlib import Path

import pytest

from m1_teacher.contracts.types import (
    HistoryEvent,
    LearnerGoal,
    LearnerSnapshot,
    MasteryEstimate,
)
from m1_teacher.domains import CFBinarySearchDomainAdapter
from m1_teacher.knowledge import KnowledgeGraph
from m1_teacher.planner import CurriculumPlanner, PlannerPolicy

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = REPO_ROOT / "fixtures" / "m1_teacher"
T0 = "2026-11-20T00:00:00Z"


@pytest.fixture(scope="module")
def adapter() -> CFBinarySearchDomainAdapter:
    domain = CFBinarySearchDomainAdapter(FIXTURES_DIR)
    domain.validate()
    return domain


@pytest.fixture(scope="module")
def graph(adapter: CFBinarySearchDomainAdapter) -> KnowledgeGraph:
    return KnowledgeGraph(adapter.knowledge_nodes(), adapter.prerequisite_edges())


@pytest.fixture(scope="module")
def objective(adapter: CFBinarySearchDomainAdapter):
    return adapter.objectives()[0]


def make_goal(learner_id: str, objective) -> LearnerGoal:
    return LearnerGoal(
        goal_id=f"goal-{learner_id}",
        learner_id=learner_id,
        objective_id=objective.objective_id,
        created_at=T0,
    )


def make_snapshot(
    learner_id: str,
    spec: dict[str, tuple[float, int, float]],
    error_counts: dict[str, int] | None = None,
    mastery_updated: str = T0,
    snapshot_updated: str = T0,
) -> LearnerSnapshot:
    return LearnerSnapshot(
        learner_id=learner_id,
        masteries={
            node_id: MasteryEstimate(
                node_id=node_id,
                value=value,
                confidence=confidence,
                evidence_count=evidence_count,
                created_at=mastery_updated,
                updated_at=mastery_updated,
            )
            for node_id, (value, evidence_count, confidence) in spec.items()
        },
        error_counts=dict(error_counts or {}),
        revision=1,
        created_at=snapshot_updated,
        updated_at=snapshot_updated,
    )


def make_event(event_id: str, seq: int, event_type: str, payload: dict, learner: str) -> HistoryEvent:
    return HistoryEvent(
        event_id=event_id,
        learner_id=learner,
        session_id="session-1",
        seq=seq,
        event_type=event_type,
        payload=payload,
        created_at=T0,
    )


def planner(adapter, graph, policy: PlannerPolicy | None = None) -> CurriculumPlanner:
    return CurriculumPlanner(adapter, graph, policy)


# A learner who has mastered the prerequisites and binary search but is weak at
# boundary handling: targets remain unmastered.
BASE_SPEC = {
    "cf.array.basics": (0.90, 4, 0.90),
    "cf.sort.sortedness": (0.85, 4, 0.90),
    "cf.search.linear": (0.80, 3, 0.85),
    "cf.search.binary": (0.85, 4, 0.90),
    "cf.search.boundary": (0.20, 2, 0.60),
    "cf.search.lower_upper": (0.20, 2, 0.60),
    "cf.complexity.log": (0.20, 2, 0.60),
}
# A learner whose prerequisites are weak: HARD remediation must kick in.
WEAK_PREREQ_SPEC = {
    "cf.array.basics": (0.70, 3, 0.85),
    "cf.sort.sortedness": (0.10, 2, 0.50),
    "cf.search.linear": (0.70, 2, 0.80),
    "cf.search.binary": (0.20, 1, 0.40),
    "cf.search.boundary": (0.05, 0, 0.10),
    "cf.search.lower_upper": (0.00, 0, 0.10),
    "cf.complexity.log": (0.00, 0, 0.10),
}
# All required nodes mastered except a high error rate keeps the goal open.
ALL_MASTERED_SPEC = {
    "cf.array.basics": (0.90, 3, 0.90),
    "cf.sort.sortedness": (0.90, 3, 0.90),
    "cf.search.linear": (0.90, 3, 0.90),
    "cf.search.binary": (0.90, 3, 0.90),
    "cf.search.boundary": (0.90, 3, 0.90),
    "cf.search.lower_upper": (0.90, 3, 0.90),
    "cf.complexity.log": (0.90, 3, 0.90),
}


def plan_for(adapter, graph, objective, spec, history=None, *, learner="learner-A", policy=None,
             errors=None, mastery_updated=T0, snapshot_updated=T0):
    snapshot = make_snapshot(
        learner, spec, errors,
        mastery_updated=mastery_updated, snapshot_updated=snapshot_updated,
    )
    return planner(adapter, graph, policy).plan(
        make_goal(learner, objective), objective, snapshot, history
    )


# ---------------------------------------------------------------------------
# Rule 1: HARD prerequisites before target teaching
# ---------------------------------------------------------------------------


def test_rule_1_hard_prerequisite_remediation_runs_first(adapter, graph, objective) -> None:
    plan = plan_for(adapter, graph, objective, WEAK_PREREQ_SPEC, learner="learner-B")
    assert plan.steps[0].rationale.code == "REMEDIATE_HARD_PREREQUISITE"
    assert plan.steps[0].node_ids == ["cf.sort.sortedness"]
    remediation = [
        step.ordinal for step in plan.steps
        if step.rationale.code in {
            "REMEDIATE_HARD_PREREQUISITE",
            "PRACTICE_HARD_PREREQUISITE",
            "REASSESS_STUCK_NODE",
        }
    ]
    teaching = [
        step.ordinal for step in plan.steps if step.rationale.code == "TEACH_TARGET_NODE"
    ]
    assert remediation and teaching
    assert max(remediation) < min(teaching)


# ---------------------------------------------------------------------------
# Rule 2: SOFT prerequisites are not forced by default
# ---------------------------------------------------------------------------


def test_rule_2_soft_prerequisite_is_not_forced_by_default(adapter, graph, objective) -> None:
    spec = dict(BASE_SPEC)
    spec["cf.search.linear"] = (0.05, 1, 0.40)  # SOFT prerequisite of binary search
    default_plan = plan_for(adapter, graph, objective, spec)
    assert not any(
        "cf.search.linear" in step.node_ids for step in default_plan.steps
    ), "SOFT prerequisite must not force a remediation step by default"

    opted_in = plan_for(
        adapter,
        graph,
        objective,
        spec,
        policy=PlannerPolicy(remediate_soft_prerequisites=True),
    )
    soft_steps = [
        step for step in opted_in.steps
        if step.rationale.code in {
            "REMEDIATE_SOFT_PREREQUISITE",
            "PRACTICE_SOFT_PREREQUISITE",
        }
    ]
    assert soft_steps
    assert soft_steps[0].node_ids == ["cf.search.linear"]
    assert soft_steps[0].ordinal == 0  # remediation is planned before target teaching


# ---------------------------------------------------------------------------
# Rule 3: review interval gating
# ---------------------------------------------------------------------------


def test_rule_3_review_not_repeated_before_interval(adapter, graph, objective) -> None:
    # One error keeps the goal open (error rate 1/3 > 0.3) without crossing
    # the review_error_threshold, so review scheduling is what is exercised.
    errors = {"cf.search.binary": 1}
    # Evidence is recent -> no review, regardless of mastery.
    recent_plan = plan_for(
        adapter, graph, objective, ALL_MASTERED_SPEC, errors=errors
    )
    assert not any(
        step.rationale.code in {"REVIEW_DUE", "REVIEW_REPEATED_ERRORS"}
        for step in recent_plan.steps
    )
    # Evidence is older than the interval -> a review step appears.
    old_plan = plan_for(
        adapter, graph, objective, ALL_MASTERED_SPEC, errors=errors,
        mastery_updated="2026-11-15T00:00:00Z",
    )
    assert any(step.rationale.code == "REVIEW_DUE" for step in old_plan.steps)
    # A shorter configured interval makes the turn-based rule fire earlier.
    history = [
        make_event(
            "r-0", 0, "ASSESSED",
            {"node_ids": ["cf.search.binary"], "status": "CORRECT"}, "learner-A",
        ),
        make_event("r-1", 1, "ITEM_PRESENTED", {"node_ids": ["cf.search.binary"]}, "learner-A"),
    ]
    short_interval_plan = plan_for(
        adapter, graph, objective, ALL_MASTERED_SPEC, history,
        errors=errors, policy=PlannerPolicy(review_interval_turns=1),
    )
    assert any(step.rationale.code == "REVIEW_DUE" for step in short_interval_plan.steps)
    default_plan = plan_for(
        adapter, graph, objective, ALL_MASTERED_SPEC, history, errors=errors
    )
    assert not any(step.rationale.code == "REVIEW_DUE" for step in default_plan.steps)


# ---------------------------------------------------------------------------
# Rule 4: consecutive failures trigger REASSESS
# ---------------------------------------------------------------------------


def test_rule_4_consecutive_failures_trigger_reassess(adapter, graph, objective) -> None:
    failures = [
        make_event(
            "f-0", 0, "ASSESSED",
            {"node_ids": ["cf.search.boundary"], "status": "INCORRECT"}, "learner-A",
        ),
        make_event(
            "f-1", 1, "ASSESSED",
            {"node_ids": ["cf.search.boundary"], "status": "INCORRECT"}, "learner-A",
        ),
    ]
    plan = plan_for(adapter, graph, objective, BASE_SPEC, failures)
    reassess = [step for step in plan.steps if step.action_kind == "REASSESS"]
    assert reassess
    assert reassess[0].phase == "ASSESS"
    assert reassess[0].node_ids == ["cf.search.boundary"]
    assert reassess[0].rationale.code == "REASSESS_STUCK_NODE"

    # One failure only: no REASSESS under the default threshold of 2 ...
    one_failure = failures[:1]
    default_plan = plan_for(adapter, graph, objective, BASE_SPEC, one_failure)
    assert not any(step.action_kind == "REASSESS" for step in default_plan.steps)
    # ... but a stricter configured threshold makes it fire.
    strict_plan = plan_for(
        adapter, graph, objective, BASE_SPEC, one_failure,
        policy=PlannerPolicy(reassess_after_failures=1),
    )
    assert any(step.action_kind == "REASSESS" for step in strict_plan.steps)


def test_rule_4_max_relearn_attempts_switch_to_reassess(adapter, graph, objective) -> None:
    attempts = [
        make_event(
            "a-0", 0, "ACTION_TAKEN",
            {"action_kind": "RETEACH", "node_ids": ["cf.sort.sortedness"]}, "learner-B",
        ),
        make_event(
            "a-1", 1, "ACTION_TAKEN",
            {"action_kind": "RETEACH", "node_ids": ["cf.sort.sortedness"]}, "learner-B",
        ),
    ]
    plan = plan_for(adapter, graph, objective, WEAK_PREREQ_SPEC, attempts, learner="learner-B")
    reassess = [step for step in plan.steps if step.action_kind == "REASSESS"]
    assert reassess
    assert reassess[0].node_ids == ["cf.sort.sortedness"]
    assert reassess[0].rationale.code == "REASSESS_STUCK_NODE"
    assert "RETEACH" in reassess[0].rationale.detail


# ---------------------------------------------------------------------------
# Rule 5: incomplete objective never completes the goal
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "spec,history,learner",
    [
        (BASE_SPEC, None, "learner-A"),
        (WEAK_PREREQ_SPEC, None, "learner-B"),
        (ALL_MASTERED_SPEC, None, "learner-A"),  # complete by mastery, no errors...
    ],
    ids=["boundary-gap", "prereq-gap", "all-mastered"],
)
def test_rule_5_incomplete_goal_never_emits_goal_complete(
    adapter, graph, objective, spec, history, learner
) -> None:
    # For the all-mastered case add a high error rate so the goal stays open.
    errors = {"cf.search.binary": 2} if spec is ALL_MASTERED_SPEC else None
    plan = plan_for(adapter, graph, objective, spec, history, learner=learner, errors=errors)
    assert not any(step.action_kind == "GOAL_COMPLETE" for step in plan.steps)
    assert not any(step.phase == "COMPLETE" for step in plan.steps)


# ---------------------------------------------------------------------------
# Rule 6: determinism of steps, order and ids
# ---------------------------------------------------------------------------


def test_rule_6_steps_order_and_ids_are_deterministic(adapter, graph, objective) -> None:
    snapshot = make_snapshot("learner-A", BASE_SPEC)
    goal = make_goal("learner-A", objective)
    builder = planner(adapter, graph)
    first = builder.plan(goal, objective, snapshot)
    second = builder.plan(goal, objective, snapshot)
    third = planner(adapter, graph).plan(goal, objective, snapshot)
    assert first.to_dict() == second.to_dict() == third.to_dict()
    assert [step.step_id for step in first.steps] == [step.step_id for step in third.steps]
    assert [step.ordinal for step in first.steps] == list(range(len(first.steps)))
    assert first.plan_id == second.plan_id


# ---------------------------------------------------------------------------
# Rule 7: documented policy parameters change behaviour
# ---------------------------------------------------------------------------


def test_rule_7_max_steps_changes_plan_length(adapter, graph, objective) -> None:
    default_plan = plan_for(adapter, graph, objective, WEAK_PREREQ_SPEC, learner="learner-B")
    capped_plan = plan_for(
        adapter, graph, objective, WEAK_PREREQ_SPEC, learner="learner-B",
        policy=PlannerPolicy(max_steps=2),
    )
    assert len(capped_plan.steps) == 2
    assert len(default_plan.steps) <= 8
    assert len(default_plan.steps) != len(capped_plan.steps)
    assert [step.ordinal for step in capped_plan.steps] == [0, 1]


def test_rule_7_prerequisite_threshold_changes_behaviour(adapter, graph, objective) -> None:
    default_plan = plan_for(adapter, graph, objective, WEAK_PREREQ_SPEC, learner="learner-B")
    assert default_plan.steps[0].rationale.code == "REMEDIATE_HARD_PREREQUISITE"
    relaxed_plan = plan_for(
        adapter, graph, objective, WEAK_PREREQ_SPEC, learner="learner-B",
        policy=PlannerPolicy(prerequisite_mastery_threshold=0.05),
    )
    # 0.10 mastery >= 0.05 threshold: no HARD remediation step for sortedness.
    assert not any(
        step.rationale.code == "REMEDIATE_HARD_PREREQUISITE" for step in relaxed_plan.steps
    )
    assert relaxed_plan.steps[0].rationale.code == "TEACH_TARGET_NODE"


def test_rule_7_struggle_threshold_changes_first_action(adapter, graph, objective) -> None:
    spec = dict(BASE_SPEC)
    spec["cf.search.boundary"] = (0.20, 2, 0.60)
    errors = {"cf.search.boundary": 1}
    default_plan = plan_for(adapter, graph, objective, spec, errors=errors)
    struggling_plan = plan_for(
        adapter, graph, objective, spec, errors=errors,
        policy=PlannerPolicy(struggle_error_threshold=1),
    )
    # Default threshold 2 not reached with one error + no consecutive failures:
    # the boundary target is taught before practice.
    assert default_plan.steps[0].node_ids == ["cf.search.boundary"]
    assert default_plan.steps[0].action_kind == "EXPLAIN"
    # Lowering the threshold documents "practice first" for error pressure 1.
    assert struggling_plan.steps[0].node_ids == ["cf.search.boundary"]
    assert struggling_plan.steps[0].action_kind == "PRACTICE"


# ---------------------------------------------------------------------------
# Rule 8: hidden-answer / network / M0 isolation
# ---------------------------------------------------------------------------


def test_rule_8_planner_source_has_no_hidden_material_or_network() -> None:
    source_dir = REPO_ROOT / "m1_teacher" / "planner"
    files = sorted(path for path in source_dir.rglob("*.py"))
    assert files
    forbidden_roots = {
        "autoteacher_m0",
        "socket",
        "httpx",
        "requests",
        "urllib",
        "urllib3",
        "aiohttp",
        "ssl",
        "http",
        "os",
        "subprocess",
    }
    io_calls = {"open", "read_text", "read_bytes", "iterdir", "glob", "rglob", "write_text"}
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert "scoring/" not in text, f"{path} references the hidden evaluation path"
        tree = ast.parse(text, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in forbidden_roots, (
                        f"{path} imports forbidden module {alias.name}"
                    )
            elif isinstance(node, ast.ImportFrom):
                root = (node.module or "").split(".")[0]
                assert root not in forbidden_roots, f"{path} imports forbidden module {node.module}"
            elif isinstance(node, ast.Call):
                func = node.func
                name = getattr(func, "id", None) or getattr(func, "attr", None)
                assert name not in io_calls, f"{path} performs filesystem I/O ({name})"


def test_rule_8_plan_unchanged_without_or_with_tampered_scoring(
    adapter, graph, objective, tmp_path
) -> None:
    goal = make_goal("learner-B", objective)
    snapshot = make_snapshot("learner-B", WEAK_PREREQ_SPEC)
    pristine = planner(adapter, graph).plan(goal, objective, snapshot)

    without_hidden = tmp_path / "without_hidden"
    shutil.copytree(FIXTURES_DIR, without_hidden, ignore=shutil.ignore_patterns("scoring"))
    assert not (without_hidden / "domains" / "cf_binary_search" / "scoring").exists()
    copy_adapter = CFBinarySearchDomainAdapter(without_hidden)
    copy_adapter.validate()
    copy_graph = KnowledgeGraph(
        copy_adapter.knowledge_nodes(), copy_adapter.prerequisite_edges()
    )
    stripped_plan = planner(copy_adapter, copy_graph).plan(goal, objective, snapshot)
    assert stripped_plan.to_dict() == pristine.to_dict()

    tampered = tmp_path / "tampered"
    shutil.copytree(FIXTURES_DIR, tampered)
    scoring_dir = tampered / "domains" / "cf_binary_search" / "scoring"
    for spec_path in scoring_dir.glob("*.json"):
        spec_path.write_text('{"kind": "TAMPERED", "answer": "leaked"}', encoding="utf-8")
    tampered_adapter = CFBinarySearchDomainAdapter(tampered)
    tampered_adapter.validate()
    tampered_graph = KnowledgeGraph(
        tampered_adapter.knowledge_nodes(), tampered_adapter.prerequisite_edges()
    )
    tampered_plan = planner(tampered_adapter, tampered_graph).plan(goal, objective, snapshot)
    assert tampered_plan.to_dict() == pristine.to_dict()


def test_rule_8_plan_and_goal_completion_json_contain_no_hidden_material(
    adapter, graph, objective
) -> None:
    snapshot = make_snapshot("learner-A", BASE_SPEC)
    plan = planner(adapter, graph).plan(make_goal("learner-A", objective), objective, snapshot)
    plan_json = plan.to_json()
    assert "scoring" not in plan_json
    assert "correct_option_index" not in plan_json
    complete, reason = planner(adapter, graph).check_goal_completion(objective, snapshot)
    assert complete is False
    assert "scoring" not in reason.to_json()
