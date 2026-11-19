"""Teaching policy tests: hint ladder safety, v0 fixed vs v1 adaptive behaviour."""

from __future__ import annotations

import pytest

from m1_offline.teaching_policy import (
    AdaptivePolicy,
    EvidenceGate,
    FixedPolicy,
    hint_kind_for_level,
)
from m1_offline.types import HINT_LADDER, DiagnosticResult, LearnerState, TeacherAction


def _task(task_type: str = "CF_PROBLEM") -> dict:
    return {"task_id": "task-001", "skill_ids": ["two-sum"], "task_type": task_type}


def _state(
    evidence_count: int = 0,
    mastery: dict[str, float] | None = None,
    error_counts: dict[str, int] | None = None,
) -> LearnerState:
    return LearnerState(
        learner_id="learner-001",
        mastery=mastery or {},
        error_counts=error_counts or {},
        evidence_count=evidence_count,
    )


def _diagnosis(
    status: str = "RESOLVED", error_codes: list[str] | None = None
) -> DiagnosticResult:
    return DiagnosticResult(
        diagnosis_id="diag-001",
        task_id="task-001",
        error_codes=error_codes or [],
        confidence=0.8,
        status=status,
        explanation="synthetic diagnosis",
        evidence_refs=["ev-001"],
    )


# ---------------------------------------------------------------------------
# Hint ladder safety (both policies)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("policy_factory", [FixedPolicy, AdaptivePolicy], ids=["v0", "v1"])
def test_new_learner_defaults_to_light_hint(policy_factory):
    action = policy_factory().choose(_task(), _state(), None, hint_level=1)
    assert isinstance(action, TeacherAction)
    assert action.kind == "LIGHT_HINT"
    assert action.hint_level == 1


@pytest.mark.parametrize("policy_factory", [FixedPolicy, AdaptivePolicy], ids=["v0", "v1"])
def test_no_evidence_cannot_reach_full_solution(policy_factory):
    action = policy_factory().choose(_task(), _state(), None, hint_level=4)
    assert action.kind == "LIGHT_HINT"
    assert action.hint_level == 1
    assert "evidence_count=0" in action.rationale


@pytest.mark.parametrize("policy_factory", [FixedPolicy, AdaptivePolicy], ids=["v0", "v1"])
def test_default_level_never_returns_full_solution(policy_factory):
    for state in (
        _state(),
        _state(2, {"two-sum": 0.4}),
        _state(6, {"two-sum": 0.9}),
    ):
        action = policy_factory().choose(_task(), state, None, hint_level=1)
        assert action.kind != "FULL_SOLUTION"
        assert action.hint_level == 1


def test_hint_ladder_order_is_light_to_full():
    assert HINT_LADDER == ("LIGHT_HINT", "INVARIANT_HINT", "STRUCTURE_HINT", "FULL_SOLUTION")
    assert hint_kind_for_level == {
        1: "LIGHT_HINT",
        2: "INVARIANT_HINT",
        3: "STRUCTURE_HINT",
        4: "FULL_SOLUTION",
    }


def test_escalation_requires_evidence():
    policy = FixedPolicy()
    weak = policy.choose(_task(), _state(2, {"two-sum": 0.4}), None, hint_level=4)
    strong = policy.choose(_task(), _state(6, {"two-sum": 0.9}), None, hint_level=4)
    assert weak.kind == "STRUCTURE_HINT"
    assert strong.kind == "FULL_SOLUTION"
    assert "FULL_SOLUTION" not in policy.choose(
        _task(), _state(2, {"two-sum": 0.4}), None, hint_level=4
    ).content


def test_evidence_gate_is_monotone():
    levels = [
        EvidenceGate.max_level(_state(0)),
        EvidenceGate.max_level(_state(1, {"two-sum": 0.2})),
        EvidenceGate.max_level(_state(2, {"two-sum": 0.4})),
        EvidenceGate.max_level(_state(6, {"two-sum": 0.9})),
    ]
    assert levels == [1, 2, 3, 4]


# ---------------------------------------------------------------------------
# FixedPolicy (teacher_v0)
# ---------------------------------------------------------------------------
def test_fixed_policy_emits_requested_rung_below_cap():
    action = FixedPolicy().choose(_task(), _state(6, {"two-sum": 0.9}), None, hint_level=2)
    assert action.kind == "INVARIANT_HINT"
    assert action.hint_level == 2
    assert action.rationale.startswith("teacher_v0")


def test_fixed_policy_ignores_diagnosis():
    action = FixedPolicy().choose(
        _task(), _state(2, {"two-sum": 0.4}), _diagnosis(error_codes=["off_by_one"]), hint_level=2
    )
    assert action.kind == "INVARIANT_HINT"
    assert "non-adaptive" in action.rationale


def test_fixed_policy_always_returns_a_hint_kind():
    for task_type in ("CF_PROBLEM", "INTERVIEW_QUESTION", "REVIEW", "READING"):
        action = FixedPolicy().choose(_task(task_type), _state(6, {"two-sum": 0.9}), None, 2)
        assert action.kind in HINT_LADDER


# ---------------------------------------------------------------------------
# AdaptivePolicy (teacher_v1)
# ---------------------------------------------------------------------------
def test_adaptive_review_task_emits_review_action():
    action = AdaptivePolicy().choose(_task("REVIEW"), _state(4, {"two-sum": 0.8}), None, 1)
    assert action.kind == "REVIEW"
    assert action.hint_level is None
    assert action.rationale.startswith("teacher_v1")


def test_adaptive_needs_review_asks_for_clarification():
    action = AdaptivePolicy().choose(
        _task(), _state(2, {"two-sum": 0.4}), _diagnosis("NEEDS_REVIEW", ["off_by_one"]), 1
    )
    assert action.kind == "ASK_CLARIFICATION"
    assert action.hint_level is None


def test_adaptive_conceptual_gap_explains():
    action = AdaptivePolicy().choose(
        _task(), _state(2, {"two-sum": 0.4}), _diagnosis("RESOLVED", ["conceptual_gap"]), 1
    )
    assert action.kind == "EXPLAIN"


def test_adaptive_other_error_codes_use_socratic_question():
    action = AdaptivePolicy().choose(
        _task(), _state(2, {"two-sum": 0.4}), _diagnosis("RESOLVED", ["off_by_one"]), 4
    )
    assert action.kind == "SOCRATIC_QUESTION"
    assert "off_by_one" in action.content
    assert action.evidence_refs == ["ev-001"]


def test_adaptive_repeated_errors_escalate_one_rung_over_requested():
    state = _state(2, {"two-sum": 0.5}, {"off_by_one": 2})
    fixed = FixedPolicy().choose(_task(), state, None, hint_level=2)
    adaptive = AdaptivePolicy().choose(_task(), state, None, hint_level=2)
    assert fixed.kind == "INVARIANT_HINT"
    assert adaptive.kind == "STRUCTURE_HINT"
    assert "repeat-errors=2" in adaptive.rationale


def test_sustained_errors_escalate_two_rungs_over_requested():
    state = _state(6, {"two-sum": 0.5}, {"off_by_one": 4})
    fixed = FixedPolicy().choose(_task(), state, None, hint_level=2)
    adaptive = AdaptivePolicy().choose(_task(), state, None, hint_level=2)
    assert fixed.kind == "INVARIANT_HINT"
    assert adaptive.kind == "STRUCTURE_HINT"  # requested L2 + 2 rungs, capped at L3
    assert "sustained" in adaptive.rationale


def test_adaptive_escalation_respects_evidence_cap():
    state = _state(1, {"two-sum": 0.1}, {"off_by_one": 2})
    action = AdaptivePolicy().choose(_task(), state, None, hint_level=1)
    # Repeated-error escalation asks for L2, but the evidence gate caps at L2 too.
    assert action.kind == "INVARIANT_HINT"


@pytest.mark.parametrize(
    "policy_factory", [FixedPolicy, AdaptivePolicy], ids=["v0", "v1"]
)
def test_v0_v1_are_distinguishable_on_diagnosis(policy_factory):
    state = _state(2, {"two-sum": 0.4})
    diagnosis = _diagnosis("RESOLVED", ["off_by_one"])
    fixed_action = FixedPolicy().choose(_task(), state, diagnosis, 2)
    adaptive_action = AdaptivePolicy().choose(_task(), state, diagnosis, 2)
    assert fixed_action.kind != adaptive_action.kind
    assert policy_factory is not None


def test_actions_are_deterministic():
    first = AdaptivePolicy().choose(
        _task(), _state(2, {"two-sum": 0.4}), _diagnosis("RESOLVED", ["off_by_one"]), 3
    )
    second = AdaptivePolicy().choose(
        _task(), _state(2, {"two-sum": 0.4}), _diagnosis("RESOLVED", ["off_by_one"]), 3
    )
    assert first.to_dict() == second.to_dict()


def test_actions_stay_serializable_and_roundtrip():
    action = FixedPolicy().choose(_task(), _state(6, {"two-sum": 0.9}), None, 1)
    restored = TeacherAction.from_dict(action.to_dict())
    assert restored == action
    assert action.target_skill_ids == ["two-sum"]
    assert action.content and action.rationale and action.action_id


def test_invalid_inputs_fail_closed():
    policy = FixedPolicy()
    with pytest.raises(ValueError):
        policy.choose(_task(), _state(), None, hint_level=0)
    with pytest.raises(ValueError):
        policy.choose(_task(), _state(), None, hint_level=5)
    with pytest.raises(ValueError):
        policy.choose({"skill_ids": ["two-sum"]}, _state(), None, hint_level=1)
    with pytest.raises(TypeError):
        policy.choose("task", _state(), None, hint_level=1)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        policy.choose(_task(), {"learner_id": "l"}, None, hint_level=1)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        policy.choose(_task(), _state(), {"status": "RESOLVED"}, hint_level=1)  # type: ignore[arg-type]
