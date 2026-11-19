"""Curriculum planner tests: explainability, review/new balance, determinism."""

from __future__ import annotations

import pytest

from m1_offline.curriculum_planner import CurriculumPlanner
from m1_offline.types import CurriculumPlan, LearnerState, LearningGoal, LearningTask


def _goal(
    goal_id: str = "goal-001",
    target_skills: list[str] | None = None,
    deadline_days: int | None = 7,
    weekly_minutes: int = 180,
) -> LearningGoal:
    return LearningGoal(
        goal_id=goal_id,
        learner_id="learner-001",
        target_skills=target_skills or ["two-sum", "binary-search"],
        deadline_days=deadline_days,
        weekly_minutes=weekly_minutes,
    )


def _state(mastery: dict[str, float] | None = None, evidence_count: int = 2) -> LearnerState:
    return LearnerState(
        learner_id="learner-001",
        mastery=mastery or {},
        error_counts={},
        evidence_count=evidence_count,
    )


def _task(
    task_id: str,
    skill_ids: list[str],
    ordinal: int = 0,
    task_type: str = "CF_PROBLEM",
    difficulty: int = 2,
) -> LearningTask:
    return LearningTask(
        task_id=task_id,
        goal_id="goal-001",
        skill_ids=skill_ids,
        task_type=task_type,
        difficulty=difficulty,
        ordinal=ordinal,
    )


def _catalog() -> list[LearningTask]:
    return [
        _task("task-new-1", ["two-sum"], ordinal=1),
        _task("task-new-2", ["binary-search"], ordinal=2),
        _task("task-review-1", ["arrays"], ordinal=3, task_type="REVIEW"),
        _task("task-new-3", ["two-sum"], ordinal=4, difficulty=3),
    ]


def test_plan_contract_fields():
    planner = CurriculumPlanner()
    plan = planner.plan(_goal(), _state({"arrays": 0.85}), _catalog())
    assert isinstance(plan, CurriculumPlan)
    assert plan.goal_id == "goal-001"
    assert plan.policy_version == "planner_v0"
    assert plan.plan_id.startswith("plan_")
    assert plan.created_at
    assert isinstance(plan.tasks, list) and plan.tasks
    assert all(isinstance(task, LearningTask) for task in plan.tasks)
    assert plan.rationale and all(isinstance(line, str) and line for line in plan.rationale)


def test_rationale_is_explainable():
    plan = CurriculumPlanner().plan(_goal(), _state({"arrays": 0.85}), _catalog())
    joined = "\n".join(plan.rationale)
    assert "POLICY: planner_v0" in joined
    assert "GOAL: goal=goal-001" in joined
    assert "BALANCE:" in joined
    assert "REVIEW: task" in joined
    assert "NEW: task" in joined
    for line in plan.rationale:
        assert line.split(":")[0] in {
            "POLICY",
            "GOAL",
            "REVIEW",
            "NEW",
            "STRETCH",
            "BALANCE",
            "BUDGET",
            "OVER_BUDGET_MINIMUM",
            "REVIEW_DEFERRED",
            "NO_AVAILABLE_TASKS",
        }


def test_review_new_balance():
    plan = CurriculumPlanner().plan(
        _goal(target_skills=["two-sum", "binary-search"]),
        _state({"arrays": 0.9}),
        _catalog(),
    )
    task_ids = [task.task_id for task in plan.tasks]
    assert "task-review-1" in task_ids, task_ids
    assert any(task_id.startswith("task-new") for task_id in task_ids), task_ids
    review_count = sum(1 for task in plan.tasks if task.task_id == "task-review-1")
    new_count = len(plan.tasks) - review_count
    assert review_count >= 1
    assert review_count <= max(1, len(plan.tasks) // 3)
    assert new_count >= 1
    assert "BALANCE: 1 review +" in "\n".join(plan.rationale)


def test_all_mastered_catalog_uses_review_only():
    catalog = [
        _task("task-r1", ["arrays"], ordinal=1, task_type="REVIEW"),
        _task("task-r2", ["two-sum"], ordinal=2, task_type="REVIEW"),
    ]
    plan = CurriculumPlanner().plan(
        _goal(), _state({"arrays": 0.9, "two-sum": 0.85}), catalog
    )
    assert {task.task_id for task in plan.tasks} == {"task-r1", "task-r2"}
    assert "REVIEW: task" in "\n".join(plan.rationale)


def test_goal_target_skills_drive_new_tasks():
    only_goal_skill = [_task("task-two-sum", ["two-sum"], ordinal=1)]
    plan = CurriculumPlanner().plan(_goal(target_skills=["two-sum"]), _state(), only_goal_skill)
    assert [task.task_id for task in plan.tasks] == ["task-two-sum"]
    assert "goal target skill" in "\n".join(plan.rationale)


def test_deterministic_for_same_inputs():
    planner = CurriculumPlanner()
    goal = _goal()
    state = _state({"arrays": 0.85})
    catalog = _catalog()
    first = planner.plan(goal, state, catalog)
    second = planner.plan(goal, state, list(reversed(catalog)))
    assert first.plan_id == second.plan_id
    assert [task.task_id for task in first.tasks] == [task.task_id for task in second.tasks]
    assert first.rationale == second.rationale


def test_policy_version_allows_documented_rollback():
    plan = CurriculumPlanner().plan(_goal(), _state({"arrays": 0.85}), _catalog())
    assert plan.policy_version == CurriculumPlanner.policy_version
    assert plan.plan_id == CurriculumPlanner._plan_id(
        _goal(), list(plan.tasks)
    )


def test_empty_catalog_returns_empty_plan_not_fabricated_work():
    plan = CurriculumPlanner().plan(_goal(), _state(), [])
    assert plan.tasks == []
    assert any(line.startswith("NO_AVAILABLE_TASKS") for line in plan.rationale)
    assert plan.policy_version == "planner_v0"


def test_deadline_caps_plan_length():
    catalog = [_task(f"task-{index:02d}", ["two-sum"], ordinal=index) for index in range(10)]
    short = CurriculumPlanner().plan(_goal(deadline_days=2), _state(), catalog)
    long = CurriculumPlanner().plan(_goal(deadline_days=6), _state(), catalog)
    assert len(short.tasks) <= 2
    assert len(long.tasks) >= len(short.tasks)
    assert len(long.tasks) <= 6


def test_tight_budget_keeps_minimum_one_task_and_explains():
    expensive = [_task("task-hard", ["two-sum"], ordinal=1, difficulty=5)]
    plan = CurriculumPlanner().plan(
        _goal(weekly_minutes=20), _state(), expensive
    )
    assert [task.task_id for task in plan.tasks] == ["task-hard"]
    assert any(line.startswith("OVER_BUDGET_MINIMUM") for line in plan.rationale)


def test_invalid_inputs_fail_closed():
    planner = CurriculumPlanner()
    with pytest.raises(TypeError):
        planner.plan({"goal_id": "g"}, _state(), _catalog())  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        planner.plan(_goal(), {"learner_id": "l"}, _catalog())  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        planner.plan(_goal(), _state(), [{"task_id": "t"}])  # type: ignore[arg-type]
    foreign_state = LearnerState(
        learner_id="someone-else", mastery={}, error_counts={}, evidence_count=0
    )
    with pytest.raises(ValueError):
        planner.plan(_goal(), foreign_state, _catalog())


def test_plan_roundtrips_as_record():
    plan = CurriculumPlanner().plan(_goal(), _state({"arrays": 0.85}), _catalog())
    restored = CurriculumPlan.from_dict(plan.to_dict())
    assert restored == plan
    assert restored.tasks == plan.tasks
