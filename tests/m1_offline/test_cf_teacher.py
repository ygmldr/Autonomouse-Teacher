"""Tests for ``m1_offline.cf.teacher.CFTeacher``.

Covers the B2 acceptance criteria that live on the teacher side:

* ``diagnose`` classifies real hidden-test failures (wrong code / wrong
  complexity / boundary bug / syntax) with explicit ``error_codes`` and
  ``evidence_refs``; ambiguous or missing evidence is ``UNKNOWN`` /
  ``NEEDS_REVIEW`` and never AC.
* AC/pass can only come from the independent hidden judge.
* hint ladder: new learner defaults to ``LIGHT_HINT``; repeated failures with
  evidence escalate; ``FULL_SOLUTION`` is never a default (only explicit
  request, gated by evidence).
* assessment is independent of learner self-report/public tests.
* learner state only moves on real observations; re-doing one problem does not
  transfer mastery to unrelated skills.
* a multi-round simulated teaching loop records explainable actions and shows
  the evidence changing the planner's next task selection.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from m1_offline.cf import CFJudge, CFTeacher, SCORER_ID
from m1_offline.curriculum_planner import CurriculumPlanner
from m1_offline.learner_model import LearnerModel
from m1_offline.runtime_port import MockRuntimePort
from m1_offline.types import (
    HINT_LADDER,
    EvidenceEvent,
    LearnerProfile,
    LearnerState,
    LearningGoal,
    LearningTask,
    TeacherAction,
)

REPO = Path(__file__).resolve().parents[2]
CF_DIR = REPO / "fixtures" / "m1" / "cf"

PROBLEM_IDS = sorted(path.stem for path in (CF_DIR / "problems").glob("*.json"))

WRONG_SUM_EVEN = "def sum_even(nums):\n    return sum(nums)\n"
SYNTAX_BROKEN = "def sum_even(nums)\n    return 0\n"
QUADRATIC_PAIR_SUM = (
    "def pair_sum_sorted(nums, target):\n"
    "    for i in range(len(nums)):\n"
    "        for j in range(i + 1, len(nums)):\n"
    "            if nums[i] + nums[j] == target:\n"
    "                return [i, j]\n"
    "    return [-1, -1]\n"
)
BOUNDARY_RUNNING_SUM = (
    "def running_sum(nums):\n"
    "    result = [nums[0]]\n"
    "    total = nums[0]\n"
    "    for value in nums[1:]:\n"
    "        total += value\n"
    "        result.append(total)\n"
    "    return result\n"
)
OFF_BY_ONE_FIRST_INDEX = (
    "def first_index(nums, target):\n"
    "    low, high = 0, len(nums) - 1\n"
    "    while low <= high:\n"
    "        mid = (low + high) // 2\n"
    "        if nums[mid] == target:\n"
    "            return mid\n"
    "        if nums[mid] < target:\n"
    "            low = mid + 1\n"
    "        else:\n"
    "            high = mid - 1\n"
    "    return -1\n"
)


def load_problem(problem_id: str) -> dict:
    return json.loads((CF_DIR / "problems" / f"{problem_id}.json").read_text(encoding="utf-8"))


def load_hidden(problem_id: str) -> dict:
    return json.loads((CF_DIR / "hidden" / f"{problem_id}.json").read_text(encoding="utf-8"))


def load_learner(learner_id: str) -> dict:
    return json.loads((CF_DIR / "learners" / f"{learner_id}.json").read_text(encoding="utf-8"))


def make_state(
    learner_id: str = "learner_weak_beginner",
    mastery: dict | None = None,
    error_counts: dict | None = None,
    evidence_count: int = 0,
) -> LearnerState:
    return LearnerState(
        learner_id=learner_id,
        mastery=mastery or {},
        error_counts=error_counts or {},
        evidence_count=evidence_count,
    )


NEW_LEARNER = make_state()
EVIDENCED = make_state(
    learner_id="learner_advanced", mastery={"two-pointers": 0.60}, evidence_count=3
)
REPEATED = make_state(
    learner_id="learner_mixed_intermediate",
    mastery={"two-pointers": 0.50},
    error_counts={"two-pointers": 2},
    evidence_count=3,
)
HEAVY = make_state(
    learner_id="learner_advanced",
    mastery={"two-pointers": 0.90},
    error_counts={"two-pointers": 10},
    evidence_count=10,
)


@pytest.fixture(scope="module")
def teacher() -> CFTeacher:
    return CFTeacher(MockRuntimePort(seed=0), judge=CFJudge(timeout_s=1.5))


@pytest.fixture(scope="module")
def fast_judge_teacher() -> CFTeacher:
    return CFTeacher(MockRuntimePort(seed=0), judge=CFJudge(timeout_s=1.0))


@pytest.fixture(scope="module")
def sum_even_problem() -> dict:
    return load_problem("cf_array_sum_even")


@pytest.fixture(scope="module")
def running_sum_problem() -> dict:
    return load_problem("cf_array_running_sum")


@pytest.fixture(scope="module")
def pair_sum_problem() -> dict:
    return load_problem("cf_tp_pair_sum_sorted")


@pytest.fixture(scope="module")
def first_index_problem() -> dict:
    return load_problem("cf_bs_first_index")


# ---------------------------------------------------------------------------
# Diagnosis
# ---------------------------------------------------------------------------
def test_diagnose_ac_only_from_hidden_judge(teacher: CFTeacher, sum_even_problem: dict) -> None:
    problem = sum_even_problem
    result = teacher.diagnose(problem, {"code": problem["reference_solution"]}, NEW_LEARNER)
    assert result.status == "RESOLVED"
    assert result.error_codes == []
    assert result.confidence == 1.0
    assert result.task_id == problem["problem_id"]
    assert any(ref.startswith("hidden:") for ref in result.evidence_refs)
    assert any(ref.startswith("judge:") for ref in result.evidence_refs)


def test_diagnose_wrong_answer(teacher: CFTeacher, sum_even_problem: dict) -> None:
    result = teacher.diagnose(sum_even_problem, {"code": WRONG_SUM_EVEN}, EVIDENCED)
    assert result.status == "RESOLVED"
    assert "wrong_answer" in result.error_codes
    assert result.confidence > 0.5
    assert result.evidence_refs


def test_diagnose_wrong_complexity(
    fast_judge_teacher: CFTeacher, pair_sum_problem: dict
) -> None:
    result = fast_judge_teacher.diagnose(
        pair_sum_problem, {"code": QUADRATIC_PAIR_SUM}, EVIDENCED
    )
    assert result.status == "RESOLVED"
    assert "wrong_complexity" in result.error_codes
    assert "large" in result.explanation or "wall-clock" in result.explanation
    assert any(ref.startswith("hidden:") for ref in result.evidence_refs)


def test_diagnose_boundary_error(teacher: CFTeacher, running_sum_problem: dict) -> None:
    result = teacher.diagnose(running_sum_problem, {"code": BOUNDARY_RUNNING_SUM}, EVIDENCED)
    assert result.status == "RESOLVED"
    assert "edge_case" in result.error_codes
    assert "edge" in result.explanation
    assert result.evidence_refs


def test_diagnose_off_by_one(teacher: CFTeacher, first_index_problem: dict) -> None:
    result = teacher.diagnose(first_index_problem, {"code": OFF_BY_ONE_FIRST_INDEX}, EVIDENCED)
    assert result.status == "RESOLVED"
    assert "off_by_one" in result.error_codes


def test_diagnose_syntax_error(teacher: CFTeacher, sum_even_problem: dict) -> None:
    result = teacher.diagnose(sum_even_problem, {"code": SYNTAX_BROKEN}, NEW_LEARNER)
    assert result.status == "RESOLVED"
    assert result.error_codes == ["syntax_error"]
    assert result.confidence >= 0.9


def test_diagnose_empty_submission_is_unknown(teacher: CFTeacher, sum_even_problem: dict) -> None:
    result = teacher.diagnose(sum_even_problem, {}, NEW_LEARNER)
    assert result.status == "UNKNOWN"
    assert result.error_codes == ["empty_submission"]
    assert result.confidence <= 0.3
    # Learner claims must not turn an empty submission into AC.
    claimed = teacher.diagnose(
        sum_even_problem, {"passed": True, "score": 1.0, "status": "AC"}, NEW_LEARNER
    )
    assert claimed.status == "UNKNOWN"
    assert claimed.error_codes == ["empty_submission"]


def test_diagnose_missing_hidden_fixture_needs_review(
    teacher: CFTeacher, sum_even_problem: dict
) -> None:
    broken = dict(sum_even_problem)
    broken.pop("hidden_ref")
    result = teacher.diagnose(broken, {"code": WORKING_CODE}, NEW_LEARNER)
    assert result.status == "NEEDS_REVIEW"
    assert result.error_codes == ["fixture_error"]
    assert result.confidence <= 0.2


WORKING_CODE = "def sum_even(nums):\n    return 0\n"


def test_diagnose_does_not_use_learner_self_report(
    teacher: CFTeacher, sum_even_problem: dict
) -> None:
    result = teacher.diagnose(
        sum_even_problem,
        {"code": WRONG_SUM_EVEN, "passed": True, "score": 1.0, "status": "AC"},
        EVIDENCED,
    )
    assert result.status != "AC"
    assert result.error_codes
    assert "wrong_answer" in result.error_codes or "off_by_one" in result.error_codes


def test_diagnose_is_deterministic(teacher: CFTeacher, sum_even_problem: dict) -> None:
    first = teacher.diagnose(sum_even_problem, {"code": WRONG_SUM_EVEN}, EVIDENCED)
    second = teacher.diagnose(sum_even_problem, {"code": WRONG_SUM_EVEN}, EVIDENCED)
    assert first == second


# ---------------------------------------------------------------------------
# Hint ladder
# ---------------------------------------------------------------------------
def test_new_learner_defaults_to_light_hint(teacher: CFTeacher) -> None:
    for problem_id in ("cf_array_sum_even", "cf_tp_pair_sum_sorted", "cf_dp_lcs"):
        problem = load_problem(problem_id)
        action = teacher.next_action(problem, NEW_LEARNER)
        assert action.kind == "LIGHT_HINT"
        assert action.hint_level == 1
        assert action.content == problem["hint_ladder"]["LIGHT_HINT"]
        assert "no evidence" in action.rationale.lower() or "safety floor" in action.rationale.lower()
        assert action.target_skill_ids == problem["skills"]
        assert action.evidence_refs


def test_explicit_hint_levels_are_recorded(teacher: CFTeacher, pair_sum_problem: dict) -> None:
    for requested in (1, 2, 3):
        action = teacher.next_action(pair_sum_problem, EVIDENCED, hint_level=requested)
        assert action.hint_level == requested
        assert action.kind == HINT_LADDER[requested - 1]
        assert action.content == pair_sum_problem["hint_ladder"][action.kind]
        assert f"requested L{requested}" in action.rationale


def test_repeated_errors_escalate_with_evidence(teacher: CFTeacher) -> None:
    problem = load_problem("cf_tp_pair_sum_sorted")
    action = teacher.next_action(problem, REPEATED)
    assert action.hint_level is not None and action.hint_level > 1
    assert action.hint_level <= 3
    assert action.kind == HINT_LADDER[action.hint_level - 1]
    assert "repeat-errors" in action.rationale


def test_code_keyed_error_history_also_escalates(teacher: CFTeacher) -> None:
    problem = load_problem("cf_tp_pair_sum_sorted")
    state = make_state(
        learner_id="learner_mixed_intermediate",
        mastery={"two-pointers": 0.55},
        error_counts={"wrong_answer": 2},
        evidence_count=3,
    )
    action = teacher.next_action(problem, state)
    assert action.hint_level is not None and action.hint_level > 1


def test_full_solution_never_default(teacher: CFTeacher) -> None:
    """Even a high-mastery learner with sustained errors gets STRUCTURE_HINT at most."""

    for problem_id in ("cf_array_sum_even", "cf_tp_pair_sum_sorted", "cf_dp_coin_change"):
        problem = load_problem(problem_id)
        heavy_matched = make_state(
            learner_id="learner_advanced",
            mastery={skill: 0.90 for skill in problem["skills"]},
            error_counts={"wrong_answer": 10},
            evidence_count=10,
        )
        action = teacher.next_action(problem, heavy_matched)
        assert action.hint_level is not None
        # Sustained errors may escalate to STRUCTURE_HINT, never past it.
        assert action.hint_level <= 3, action.hint_level
        assert action.kind != "FULL_SOLUTION"
        assert action.kind == HINT_LADDER[action.hint_level - 1]


class _AlwaysFullPolicy:
    """Hostile policy stub: always asks for FULL_SOLUTION (safety-net test)."""

    policy_version = "stub_always_full"

    def choose(self, task, learner_state, diagnosis, hint_level):  # noqa: ANN001
        return TeacherAction(
            action_id="act_stub_full",
            kind="FULL_SOLUTION",
            content="stub worked solution",
            rationale="stub policy always requests the worked solution",
            hint_level=4,
            target_skill_ids=list(task["skill_ids"]),
            evidence_refs=["stub"],
        )


def test_cf_teacher_clamps_hostile_policy_to_structure_hint(
    teacher: CFTeacher, pair_sum_problem: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(teacher, "policy", _AlwaysFullPolicy())
    action = teacher.next_action(pair_sum_problem, EVIDENCED)
    assert action.kind == "STRUCTURE_HINT"
    assert action.hint_level == 3
    assert action.content == pair_sum_problem["hint_ladder"]["STRUCTURE_HINT"]
    assert "never by default" in action.rationale
    # An explicit hint_level=4 request still passes through the CF safety net.
    explicit = teacher.next_action(pair_sum_problem, EVIDENCED, hint_level=4)
    assert explicit.kind == "FULL_SOLUTION"


def test_full_solution_only_on_explicit_evidence_gated_request(
    teacher: CFTeacher, pair_sum_problem: dict
) -> None:
    action = teacher.next_action(pair_sum_problem, HEAVY, hint_level=4)
    assert action.kind == "FULL_SOLUTION"
    assert action.hint_level == 4
    assert action.content == pair_sum_problem["hint_ladder"]["FULL_SOLUTION"]

    # Thin evidence cannot unlock the worked solution even when asked for it.
    thin = teacher.next_action(pair_sum_problem, EVIDENCED, hint_level=4)
    assert thin.hint_level is not None and thin.hint_level <= 3
    assert thin.kind != "FULL_SOLUTION"

    # A brand-new learner is always floored at LIGHT_HINT.
    newbie = teacher.next_action(pair_sum_problem, NEW_LEARNER, hint_level=4)
    assert newbie.kind == "LIGHT_HINT"
    assert newbie.hint_level == 1


def test_invalid_hint_level_rejected(teacher: CFTeacher, pair_sum_problem: dict) -> None:
    for bad in (0, 5, -1, True, "2"):
        with pytest.raises(ValueError):
            teacher.next_action(pair_sum_problem, EVIDENCED, hint_level=bad)  # type: ignore[arg-type]


def test_hint_level_matches_kind_and_fixture_content(
    teacher: CFTeacher, pair_sum_problem: dict
) -> None:
    observations = [
        teacher.next_action(pair_sum_problem, NEW_LEARNER),
        teacher.next_action(pair_sum_problem, EVIDENCED, hint_level=2),
        teacher.next_action(pair_sum_problem, REPEATED),
        teacher.next_action(pair_sum_problem, HEAVY),
    ]
    for action in observations:
        assert action.kind in HINT_LADDER
        assert action.hint_level == HINT_LADDER.index(action.kind) + 1
        assert action.content == pair_sum_problem["hint_ladder"][action.kind]
        assert action.rationale


# ---------------------------------------------------------------------------
# Assessment independence
# ---------------------------------------------------------------------------
def test_assess_pass_comes_from_hidden_judge(teacher: CFTeacher, sum_even_problem: dict) -> None:
    hidden = load_hidden("cf_array_sum_even")
    result = teacher.assess(sum_even_problem, {"code": sum_even_problem["reference_solution"]}, NEW_LEARNER)
    assert result.passed is True
    assert result.score == 1.0
    assert result.scorer_id == SCORER_ID
    assert result.scorer_id != "cf_teacher_self_report"
    assert result.hidden_cases_total == len(hidden["tests"])
    assert result.hidden_cases_passed == result.hidden_cases_total
    assert result.failure_modes == []
    assert set(result.dimensions) == {"correctness", "edge_case_accuracy", "efficiency"}
    assert all(0.0 <= value <= 1.0 for value in result.dimensions.values())


def test_assess_wrong_answer_fails(teacher: CFTeacher, sum_even_problem: dict) -> None:
    hidden = load_hidden("cf_array_sum_even")
    result = teacher.assess(sum_even_problem, {"code": WRONG_SUM_EVEN}, EVIDENCED)
    assert result.passed is False
    assert 0.0 < result.score < 1.0
    assert result.hidden_cases_total == len(hidden["tests"])
    assert result.hidden_cases_passed < result.hidden_cases_total
    assert result.failure_modes


def test_assess_ignores_learner_claims(teacher: CFTeacher, sum_even_problem: dict) -> None:
    result = teacher.assess(
        sum_even_problem,
        {"code": WRONG_SUM_EVEN, "passed": True, "score": 1.0, "status": "AC"},
        EVIDENCED,
    )
    assert result.passed is False
    assert result.score < 1.0


def test_assess_ignores_tampered_public_tests(teacher: CFTeacher, sum_even_problem: dict) -> None:
    baseline = teacher.assess(sum_even_problem, {"code": WRONG_SUM_EVEN}, EVIDENCED)
    tampered_problem = json.loads(json.dumps(sum_even_problem))
    tampered_problem["public_tests"] = [{"args": [[]], "expected": 123456}]
    tampered = teacher.assess(tampered_problem, {"code": WRONG_SUM_EVEN}, EVIDENCED)
    assert tampered.passed == baseline.passed
    assert tampered.score == baseline.score
    assert tampered.dimensions == baseline.dimensions
    assert tampered.failure_modes == baseline.failure_modes


def test_assess_boundary_bug_lowers_edge_accuracy(
    teacher: CFTeacher, running_sum_problem: dict
) -> None:
    result = teacher.assess(running_sum_problem, {"code": BOUNDARY_RUNNING_SUM}, EVIDENCED)
    assert result.passed is False
    assert result.dimensions["edge_case_accuracy"] < 1.0
    assert result.dimensions["correctness"] > 0.0


def test_assess_tampered_reference_solution_does_not_help(
    teacher: CFTeacher, sum_even_problem: dict
) -> None:
    tampered = json.loads(json.dumps(sum_even_problem))
    tampered["reference_solution"] = "def sum_even(nums):\n    return 0\n"
    result = teacher.assess(tampered, {"code": WRONG_SUM_EVEN}, EVIDENCED)
    assert result.passed is False


# ---------------------------------------------------------------------------
# Learner state: real observations only, no phantom transfer
# ---------------------------------------------------------------------------
def test_learner_state_only_moves_on_real_evidence(
    teacher: CFTeacher, sum_even_problem: dict
) -> None:
    profile = LearnerProfile(**load_learner("learner_weak_beginner")["profile"])
    model = LearnerModel(profile)
    state = model.state()
    assert state.mastery == {}
    assert state.evidence_count == 0

    assessment = teacher.assess(
        sum_even_problem, {"code": sum_even_problem["reference_solution"]}, state
    )
    # Assessing does not itself mutate learner state: only evidence application does.
    assert model.state().evidence_count == 0
    assert model.state().mastery == {}

    event = EvidenceEvent(
        event_id="ev-cf-001",
        learner_id=profile.learner_id,
        task_id=sum_even_problem["problem_id"],
        kind="CODE_SUBMISSION",
        payload={"skill_ids": list(sum_even_problem["skills"]), "code": "reference"},
        observed_score=assessment.score,
        error_codes=list(assessment.failure_modes),
        created_at="2026-11-05T00:00:00Z",
    )
    updated = model.apply_evidence(event)
    assert updated.evidence_count == 1
    assert set(updated.mastery) <= set(sum_even_problem["skills"])
    assert updated.mastery["array-basics"] > 0.0
    assert "dp-basics" not in updated.mastery


def test_repeating_one_problem_does_not_transfer_mastery(
    teacher: CFTeacher, sum_even_problem: dict
) -> None:
    profile = LearnerProfile(**load_learner("learner_advanced")["profile"])
    model = LearnerModel(profile)
    model.register_task_skills(sum_even_problem["problem_id"], list(sum_even_problem["skills"]))
    for index in range(3):
        model.apply_evidence(
            EvidenceEvent(
                event_id=f"ev-repeat-{index}",
                learner_id=profile.learner_id,
                task_id=sum_even_problem["problem_id"],
                kind="CODE_SUBMISSION",
                payload={
                    "skill_ids": list(sum_even_problem["skills"]) + ["dp-basics"],
                    "code": "reference",
                },
                observed_score=1.0,
                error_codes=[],
                created_at=f"2026-11-05T0{index}:00:00Z",
            )
        )
    state = model.state()
    assert set(state.mastery) <= set(sum_even_problem["skills"])
    assert "dp-basics" not in state.mastery
    # Repeated observations earn diminishing credit instead of fresh transfer.
    assert state.mastery["array-basics"] < 1.0


def test_failed_assessment_lowers_mastery_only_through_evidence(
    teacher: CFTeacher, sum_even_problem: dict
) -> None:
    profile = LearnerProfile(**load_learner("learner_weak_beginner")["profile"])
    model = LearnerModel(profile)
    model.apply_evidence(
        EvidenceEvent(
            event_id="ev-seed",
            learner_id=profile.learner_id,
            task_id="cf_array_sum_even",
            kind="CODE_SUBMISSION",
            payload={"skill_ids": ["array-basics"]},
            observed_score=0.8,
            error_codes=[],
            created_at="2026-11-05T00:00:00Z",
        )
    )
    before = model.state()
    all_fail_code = "def sum_even(nums):\n    return None\n"
    assessment = teacher.assess(sum_even_problem, {"code": all_fail_code}, before)
    assert assessment.passed is False
    assert assessment.score == 0.0
    after_failed = model.apply_evidence(
        EvidenceEvent(
            event_id="ev-fail",
            learner_id=profile.learner_id,
            task_id="cf_array_sum_even",
            kind="CODE_SUBMISSION",
            payload={"skill_ids": ["array-basics"]},
            observed_score=assessment.score,
            error_codes=list(assessment.failure_modes),
            created_at="2026-11-05T01:00:00Z",
        )
    )
    assert after_failed.evidence_count == before.evidence_count + 1
    assert after_failed.mastery["array-basics"] <= before.mastery["array-basics"]
    assert after_failed.error_counts, "failure error codes must be recorded as evidence"


# ---------------------------------------------------------------------------
# Multi-round simulated teaching loop
# ---------------------------------------------------------------------------
def test_multi_round_loop_actions_change_next_task(teacher: CFTeacher) -> None:
    learner_id = "learner_advanced"
    goal = LearningGoal(
        goal_id="goal-cf-001",
        learner_id=learner_id,
        target_skills=["array-basics", "dp-basics"],
        deadline_days=3,
        weekly_minutes=180,
    )
    order = [
        "cf_array_sum_even",
        "cf_array_running_sum",
        "cf_array_max_subarray",
        "cf_dp_climb_stairs",
    ]
    problems = {problem_id: load_problem(problem_id) for problem_id in order}
    tasks = [
        LearningTask(
            task_id=problem_id,
            goal_id=goal.goal_id,
            skill_ids=list(problems[problem_id]["skills"]),
            task_type="CF_PROBLEM",
            difficulty=problems[problem_id]["difficulty"],
            fixture_ref=problem_id,
            ordinal=index,
        )
        for index, problem_id in enumerate(order)
    ]
    planner = CurriculumPlanner()
    model = LearnerModel(LearnerProfile(learner_id=learner_id, display_name="Synthetic Advanced"))
    state = model.state()
    actions = []
    attempts = []

    # Round 1: plan with no evidence; the planner starts from the first new task.
    plan = planner.plan(goal, state, tasks)
    assert plan.rationale
    first_task_before = plan.tasks[0].task_id
    assert first_task_before == "cf_array_sum_even"

    for round_index in range(1, 4):
        plan = planner.plan(goal, state, tasks)
        attempted = {attempt["task_id"] for attempt in attempts}
        next_task = next(
            (task for task in plan.tasks if task.task_id not in attempted),
            plan.tasks[0],
        )
        problem = problems[next_task.task_id]
        action = teacher.next_action(problem, state)
        assert action.rationale
        assert action.content == problem["hint_ladder"][action.kind]
        assert action.target_skill_ids == problem["skills"]
        actions.append(action)

        assessment = teacher.assess(
            problem, {"code": problem["reference_solution"]}, state
        )
        assert assessment.passed is True
        attempts.append(
            {
                "round": round_index,
                "task_id": next_task.task_id,
                "action_id": action.action_id,
                "hint_level": action.hint_level,
                "passed": assessment.passed,
                "score": assessment.score,
            }
        )
        state = model.apply_evidence(
            EvidenceEvent(
                event_id=f"ev-loop-{round_index}",
                learner_id=learner_id,
                task_id=next_task.task_id,
                kind="CODE_SUBMISSION",
                payload={"skill_ids": list(problem["skills"])},
                observed_score=assessment.score,
                error_codes=list(assessment.failure_modes),
                created_at=f"2026-11-06T0{round_index}:00:00Z",
            )
        )

    # Round 4: the three fresh passes pushed array-basics mastery over the
    # planner's review threshold, so the next task selection changes.
    final_plan = planner.plan(goal, state, tasks)
    final_problem = problems[final_plan.tasks[0].task_id]
    final_action = teacher.next_action(final_problem, state)
    actions.append(final_action)
    first_task_after = final_plan.tasks[0].task_id

    assert len(actions) >= 4, "at least three explainable teaching actions are recorded"
    assert all(action.rationale for action in actions)
    assert all(action.hint_level in (1, 2, 3) for action in actions)
    assert any("REVIEW" in line for line in final_plan.rationale)
    assert first_task_after != first_task_before
    assert final_plan.rationale != plan.rationale
    assert [attempt["task_id"] for attempt in attempts] == order[:3]
    assert all(attempt["passed"] for attempt in attempts)
    assert state.evidence_count == 3
    assert len({action.action_id for action in actions}) >= 3


def test_loop_failure_evidence_escalates_hint(teacher: CFTeacher) -> None:
    """Two real failing assessments (recorded as evidence) escalate the hint rung."""

    problem = load_problem("cf_array_sum_even")
    hidden = load_hidden("cf_array_sum_even")
    learner_id = "learner_weak_beginner"
    model = LearnerModel(LearnerProfile(learner_id=learner_id))
    state = model.state()
    levels = []
    for round_index in range(1, 3):
        action = teacher.next_action(problem, state)
        levels.append(action.hint_level)
        assert action.hint_level is not None and action.hint_level <= 3
        assessment = teacher.assess(problem, {"code": WRONG_SUM_EVEN}, state)
        assert assessment.passed is False
        assert assessment.hidden_cases_total == len(hidden["tests"])
        state = model.apply_evidence(
            EvidenceEvent(
                event_id=f"ev-fail-{round_index}",
                learner_id=learner_id,
                task_id=problem["problem_id"],
                kind="CODE_SUBMISSION",
                payload={"skill_ids": list(problem["skills"])},
                observed_score=assessment.score,
                error_codes=list(assessment.failure_modes),
                created_at=f"2026-11-07T0{round_index}:00:00Z",
            )
        )
    escalated = teacher.next_action(problem, state)
    levels.append(escalated.hint_level)
    assert levels[0] == 1, "first attempt on a new learner must be LIGHT_HINT"
    assert levels[-1] is not None and levels[-1] > levels[0], levels
    assert escalated.kind == HINT_LADDER[escalated.hint_level - 1]
    assert escalated.hint_level <= 3, "failure evidence must never default to FULL_SOLUTION"
