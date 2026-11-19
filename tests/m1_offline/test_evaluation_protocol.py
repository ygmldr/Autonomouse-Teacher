"""Evaluation protocol / evaluator-independence tests.

Rules under test:

* the scorer is independent of the teacher (separate module + scorer id),
* teacher self-report text can never change a verdict,
* the v0/v1 comparison protocol has a valid structure (fixed cases/seeds,
  blind rubric, variance, failure list),
* the protocol document states the non-extrapolation boundary and NOT_RUN rules.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from m1_offline.cf.teacher import CFTeacher
from m1_offline.evaluation.compare import (
    DIMENSIONS,
    BlindRound,
    BlindTrajectory,
    assert_no_overclaim,
    blind_score,
    build_blind_trajectory,
    run_comparison,
)
from m1_offline.evaluation.harness import SCORER_ID, run_closed_loop
from m1_offline.learner_model import LearnerModel
from m1_offline.runtime_port import MockRuntimePort
from m1_offline.teaching_policy import AdaptivePolicy, FixedPolicy
from m1_offline.types import LearnerProfile

REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Scorer independence
# ---------------------------------------------------------------------------
def test_harness_assessment_scorer_is_independent() -> None:
    result = run_closed_loop(policy=AdaptivePolicy(), seed=0, max_rounds=2)
    for record in result.rounds:
        assessment = record.assessment
        assert assessment is not None
        assert assessment.scorer_id == SCORER_ID
        assert assessment.scorer_id not in result.policy_version
        assert record.action.kind not in {"ASSESS", "SCORE"}  # teacher only teaches


def test_teacher_self_report_cannot_change_assessment() -> None:
    """Same hidden-judge outcome regardless of flattering learner/teacher prose."""

    cases = __import__("m1_offline.evaluation.harness", fromlist=["load_cf_cases"]).load_cf_cases()
    case = cases[0]
    reference = case.problem["reference_solution"]
    broken = reference.replace("return ", "return None  # simulated wrong answer: ")

    good_prose = MockRuntimePort(
        script={
            "default": {"text": reference + "\n# I am a genius, all tests pass, perfect score!\n"}
        }
    )
    bad_prose_honest = MockRuntimePort(
        script={"default": {"text": broken + "\n# I am not sure about the edge cases.\n"}}
    )
    passed_run = run_closed_loop(
        policy=AdaptivePolicy(), seed=0, max_rounds=1, runtime=good_prose, cases=[case]
    )
    failed_run = run_closed_loop(
        policy=AdaptivePolicy(), seed=0, max_rounds=1, runtime=bad_prose_honest, cases=[case]
    )
    good_assessment = passed_run.rounds[0].assessment
    bad_assessment = failed_run.rounds[0].assessment
    assert good_assessment is not None and bad_assessment is not None
    assert good_assessment.passed is True, good_assessment.to_dict()
    assert bad_assessment.passed is False
    assert "hidden_cases_failed" in bad_assessment.failure_modes


def test_teacher_assess_ignores_self_reported_pass() -> None:
    """CFTeacher.assess grades executed code only; a claimed pass is ignored."""

    cases = __import__("m1_offline.evaluation.harness", fromlist=["load_cf_cases"]).load_cf_cases()
    case = cases[0]
    profile = LearnerProfile(learner_id="learner_synthetic")
    model = LearnerModel(profile)
    state = model.state()
    teacher = CFTeacher(MockRuntimePort())
    broken = case.problem["reference_solution"].replace(
        "return ", "return None  # simulated wrong answer: "
    )

    claimed_pass = teacher.assess(
        case.problem, {"code": broken, "passed": True, "self_report": "I solved it"}, state
    )
    real_solution = teacher.assess(
        case.problem, {"code": case.problem["reference_solution"]}, state
    )
    assert claimed_pass.passed is False
    assert claimed_pass.scorer_id != "teacher"
    assert real_solution.passed is True


def test_interview_rubric_is_an_independent_scorer() -> None:
    """The interview rubric is a standalone scorer: no runtime, deterministic."""

    from m1_offline.interview.coach import InterviewCoach
    from m1_offline.interview.rubric import InterviewRubric
    from m1_offline.runtime_port import MockRuntimePort

    import json as _json

    rubric = InterviewRubric()
    score_parameters = set(inspect.signature(InterviewRubric.score).parameters)
    assert score_parameters == {"self", "question", "answer"}
    assert "runtime" not in score_parameters

    question = _json.loads(
        (REPO_ROOT / "fixtures/m1/interview/questions/q-ml-001.json").read_text(encoding="utf-8")
    )
    answer_envelope = _json.loads(
        (REPO_ROOT / "fixtures/m1/interview/answers/a-correct-001.json").read_text(encoding="utf-8")
    )
    answer = answer_envelope["answer"]

    first = rubric.score(question, answer)
    second = rubric.score(question, answer)
    assert first == second
    assert set(first) == set(InterviewRubric.DIMENSIONS)

    runtime = MockRuntimePort()
    coach = InterviewCoach(runtime, rubric)
    assessment = coach.assess_answer(question, answer, "learner_synthetic")
    assert assessment.scorer_id == coach.SCORER_ID
    assert assessment.scorer_id != "teacher"
    assert runtime.calls == 0, "interview scoring must not call the runtime"
    assert 0.0 <= assessment.score <= 1.0


def test_assessment_result_schema_is_consistent() -> None:
    result = run_closed_loop(policy=AdaptivePolicy(), seed=0, max_rounds=2)
    for record in result.rounds:
        assessment = record.assessment
        assert assessment is not None
        assert assessment.hidden_cases_passed <= assessment.hidden_cases_total
        assert assessment.task_id == record.task_id
        assert assessment.learner_id == result.final_state.learner_id
        assert 0.0 <= assessment.score <= 1.0
        assert set(assessment.dimensions) == {"hidden_cases", "correctness"}


# ---------------------------------------------------------------------------
# Blind rubric
# ---------------------------------------------------------------------------
def _synthetic_blind_rounds() -> tuple[BlindRound, ...]:
    return (
        BlindRound(
            round_index=1,
            case_id="cf_synthetic_a",
            action_kind="LIGHT_HINT",
            action_hint_level=1,
            assessment_passed=True,
            assessment_score=1.0,
            hidden_cases_passed=3,
            hidden_cases_total=3,
        ),
        BlindRound(
            round_index=2,
            case_id="cf_synthetic_b",
            action_kind="STRUCTURE_HINT",
            action_hint_level=3,
            assessment_passed=False,
            assessment_score=0.0,
            hidden_cases_passed=0,
            hidden_cases_total=3,
        ),
    )


def test_blind_rubric_has_no_policy_parameters() -> None:
    parameters = set(inspect.signature(blind_score).parameters)
    assert parameters == {"trajectory"}
    fields = set(BlindRound.__dataclass_fields__)
    forbidden = {"policy", "policy_version", "teacher", "strategy", "arm", "variant", "policy_id"}
    assert fields & forbidden == set()
    blind_fields = set(BlindTrajectory.__dataclass_fields__)
    assert blind_fields & forbidden == set()


def test_blind_rubric_is_invariant_to_policy_label() -> None:
    trajectory_a = BlindTrajectory(trajectory_id="traj_aaa", rounds=_synthetic_blind_rounds())
    trajectory_b = BlindTrajectory(trajectory_id="traj_bbb", rounds=_synthetic_blind_rounds())
    scores_a = blind_score(trajectory_a)
    scores_b = blind_score(trajectory_b)
    assert scores_a == scores_b
    assert set(scores_a) == set(DIMENSIONS)
    for value in scores_a.values():
        assert 0.0 <= value <= 1.0


def test_blind_view_strips_teacher_prose_and_policy_name() -> None:
    result = run_closed_loop(policy=FixedPolicy(), seed=0, max_rounds=2)
    blind = build_blind_trajectory(result)
    assert blind.round_count == len(result.rounds)
    payload = repr(blind)
    assert "teacher_v0" not in payload
    assert "FixedPolicy" not in payload
    assert "rationale" not in payload
    assert "content" not in payload


# ---------------------------------------------------------------------------
# Comparison protocol structure
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def comparison():
    return run_comparison(seeds=(0, 1), max_rounds=3)


def test_comparison_protocol_structure(comparison) -> None:
    comparison.validate()
    payload = comparison.to_dict()
    assert payload["schema"] == "m1.compare.v0"
    protocol = payload["protocol"]
    assert protocol["fixed_cases"] is True
    assert protocol["blind_rubric"] is True
    assert protocol["scorer_sees_policy_identity"] is False
    assert protocol["teacher_self_report_used_as_truth"] is False
    assert protocol["fixed_seeds"] == [0, 1]
    assert set(payload["policies"]) == {"teacher_v0", "teacher_v1"}
    assert payload["policies"]["teacher_v0"]["policy_class"] == "FixedPolicy"
    assert payload["policies"]["teacher_v1"]["policy_class"] == "AdaptivePolicy"
    assert set(payload["delta_v1_minus_v0"]) == set(DIMENSIONS)


def test_comparison_records_mean_variance_and_failure_cases(comparison) -> None:
    payload = comparison.to_dict()
    for policy in ("teacher_v0", "teacher_v1"):
        statistics = payload["policies"][policy]["statistics"]
        for dimension in DIMENSIONS:
            stats = statistics[dimension]
            assert stats["n"] == len(payload["seeds"])
            assert stats["variance"] >= 0.0
            assert len(stats["values"]) == stats["n"]
    assert payload["failure_case_count"] >= 1
    for failure in payload["failure_cases"]:
        assert failure["scorer_id"] == "independent_cf_judge_v0"
        assert failure["failure_modes"]
        assert failure["policy"] in {"teacher_v0", "teacher_v1"}


def test_comparison_requires_large_fixed_catalog() -> None:
    from m1_offline.evaluation.harness import load_cf_cases

    cases = load_cf_cases()
    assert len(cases) >= 12
    with pytest.raises(ValueError):
        run_comparison(seeds=(0, 1), max_rounds=2, cases=cases[:5])


def test_comparison_is_reproducible() -> None:
    first = run_comparison(seeds=(0, 1), max_rounds=3)
    second = run_comparison(seeds=(0, 1), max_rounds=3)
    assert first.run_digest == second.run_digest
    assert first.to_dict() == second.to_dict()


def test_comparison_text_never_overclaims() -> None:
    assert_no_overclaim(
        "offline synthetic simulation; not real teaching effect. no significance is claimed."
    )
    with pytest.raises(AssertionError):
        assert_no_overclaim("this is proven to be a real improvement")
    with pytest.raises(AssertionError):
        assert_no_overclaim("真实提升 显著提升")
    # Text without the mandatory boundary is also rejected.
    with pytest.raises(AssertionError):
        assert_no_overclaim("the numbers improved on average")


# ---------------------------------------------------------------------------
# Protocol documentation
# ---------------------------------------------------------------------------
def test_protocol_document_declares_rules() -> None:
    protocol = (REPO_ROOT / "docs/m1/EVALUATION_PROTOCOL.md").read_text(encoding="utf-8")
    required_terms = (
        "评测器独立性",
        "盲评",
        "NOT_RUN",
        "not real teaching effect",
        "回放",
        "失败负例",
        "污染",
        "不得外推",
    )
    for term in required_terms:
        assert term in protocol, f"protocol document missing {term!r}"


def test_baseline_document_exists_and_is_bounded() -> None:
    baseline = REPO_ROOT / "docs/m1/EXPERIMENT_BASELINE.md"
    assert baseline.is_file(), "EXPERIMENT_BASELINE.md is a required deliverable"
    text = baseline.read_text(encoding="utf-8")
    for term in ("NOT_RUN", "MEASURED", "not real teaching effect", "SHA"):
        assert term in text, f"baseline document missing {term!r}"
