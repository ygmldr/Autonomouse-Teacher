"""Learner model tests: evidence-driven mastery, no phantom transfer, replay."""

from __future__ import annotations

import pytest

from m1_offline.learner_model import (
    LEARNING_RATE,
    REPEAT_CREDIT_FACTOR,
    LearnerModel,
    SCORED_EVIDENCE_KINDS,
)
from m1_offline.types import EvidenceEvent, LearnerProfile, LearnerState


def _profile(learner_id: str = "learner-001") -> LearnerProfile:
    return LearnerProfile(learner_id=learner_id, display_name="Synthetic Learner")


def _event(
    event_id: str,
    task_id: str,
    skill_ids: list[str],
    score: float | None,
    *,
    kind: str = "ANSWER",
    error_codes: list[str] | None = None,
    created_at: str = "",
    learner_id: str = "learner-001",
    payload_extra: dict | None = None,
) -> EvidenceEvent:
    payload: dict = {"skill_ids": skill_ids}
    if payload_extra:
        payload.update(payload_extra)
    return EvidenceEvent(
        event_id=event_id,
        learner_id=learner_id,
        task_id=task_id,
        kind=kind,
        payload=payload,
        observed_score=score,
        error_codes=error_codes or [],
        created_at=created_at,
    )


def test_fresh_model_has_no_mastery():
    model = LearnerModel(_profile())
    state = model.state()
    assert isinstance(state, LearnerState)
    assert state.learner_id == "learner-001"
    assert state.mastery == {}
    assert state.error_counts == {}
    assert state.evidence_count == 0


def test_no_evidence_means_no_mastery_gain():
    model = LearnerModel(_profile())
    assert model.state().mastery == {}
    # Replaying an empty stream must not fabricate any mastery either.
    model.replay([])
    assert model.state().mastery == {}


def test_observed_success_raises_only_evidenced_skill():
    model = LearnerModel(_profile())
    model.apply_evidence(_event("e1", "task-1", ["two-sum"], 0.8))
    state = model.state()
    assert set(state.mastery) == {"two-sum"}
    assert state.mastery["two-sum"] == pytest.approx(LEARNING_RATE * 0.8, abs=1e-6)
    assert state.evidence_count == 1


def test_failure_lowers_mastery():
    model = LearnerModel(_profile())
    model.apply_evidence(_event("e1", "task-1", ["two-sum"], 0.9))
    after_success = model.state().mastery["two-sum"]
    model.apply_evidence(_event("e2", "task-1", ["two-sum"], 0.0))
    after_failure = model.state().mastery["two-sum"]
    assert after_failure < after_success
    assert after_failure >= 0.0


def test_unscored_evidence_does_not_change_mastery():
    model = LearnerModel(_profile())
    model.apply_evidence(_event("e1", "task-1", ["two-sum"], None))
    state = model.state()
    assert state.mastery == {}
    assert state.evidence_count == 1


def test_hint_request_is_not_scored_evidence():
    assert "HINT_REQUEST" not in SCORED_EVIDENCE_KINDS
    model = LearnerModel(_profile())
    model.apply_evidence(
        _event("e1", "task-1", ["two-sum"], 1.0, kind="HINT_REQUEST")
    )
    assert model.state().mastery == {}
    assert model.state().evidence_count == 1


def test_repeated_same_task_credit_is_diminishing():
    model = LearnerModel(_profile())
    model.apply_evidence(_event("e1", "task-1", ["two-sum"], 0.6))
    first_gain = model.state().mastery["two-sum"]
    model.apply_evidence(_event("e2", "task-1", ["two-sum"], 0.6))
    second_gain = model.state().mastery["two-sum"] - first_gain
    expected_second = LEARNING_RATE * REPEAT_CREDIT_FACTOR * (0.6 - first_gain)
    assert second_gain == pytest.approx(expected_second, abs=1e-6)
    assert second_gain < first_gain
    assert REPEAT_CREDIT_FACTOR < 1.0


def test_repeated_same_task_is_not_treated_as_cross_skill_transfer():
    model = LearnerModel(_profile())
    model.apply_evidence(_event("e1", "task-1", ["two-sum"], 0.9))
    assert model.task_skills("task-1") == ("two-sum",)
    # An event on the same task that claims a *different* skill must not credit
    # that other skill: the task is already bound to its declared skill set.
    model.apply_evidence(_event("e2", "task-1", ["graphs"], 1.0))
    state = model.state()
    assert "graphs" not in state.mastery
    assert set(state.mastery) == {"two-sum"}


def test_first_event_binds_task_skills_and_cannot_be_widened():
    model = LearnerModel(_profile())
    model.register_task_skills("task-9", ["arrays"])
    with pytest.raises(ValueError):
        model.register_task_skills("task-9", ["arrays", "graphs"])
    model.apply_evidence(_event("e1", "task-9", ["arrays", "graphs"], 0.9))
    assert set(model.state().mastery) == {"arrays"}


def test_unknown_skill_mapping_does_not_move_mastery():
    model = LearnerModel(_profile())
    # No payload skill signal and no registered mapping: evidence still counts
    # but cannot credit any skill.
    model.apply_evidence(
        EvidenceEvent(
            event_id="e1",
            learner_id="learner-001",
            task_id="task-x",
            kind="ANSWER",
            payload={"answer": "synthetic"},
            observed_score=1.0,
        )
    )
    assert model.state().mastery == {}
    assert model.state().evidence_count == 1


def test_failed_evidence_with_error_codes_cannot_raise_mastery():
    model = LearnerModel(_profile())
    # A first (unflagged) observation seeds mastery, then a repeated attempt with
    # a *higher* raw score but error codes must not raise mastery: failure is not
    # proof of improvement (fail-closed).
    model.apply_evidence(_event("e1", "task-1", ["two-sum"], 0.5))
    seeded = model.state().mastery["two-sum"]
    model.apply_evidence(
        _event("e2", "task-1", ["two-sum"], 0.9, error_codes=["edge_case"])
    )
    assert model.state().mastery["two-sum"] == pytest.approx(seeded)
    # It may still lower mastery when the observed score is below the estimate.
    model.apply_evidence(
        _event("e3", "task-1", ["two-sum"], 0.0, error_codes=["off_by_one"])
    )
    assert model.state().mastery["two-sum"] < seeded


def test_first_failed_observation_does_not_create_mastery():
    model = LearnerModel(_profile())
    model.apply_evidence(
        _event("e1", "task-1", ["two-sum"], 0.9, error_codes=["edge_case"])
    )
    assert model.state().mastery.get("two-sum", 0.0) == 0.0


def test_error_counts_accumulate():
    model = LearnerModel(_profile())
    model.apply_evidence(_event("e1", "task-1", ["two-sum"], 0.0, error_codes=["off_by_one"]))
    model.apply_evidence(_event("e2", "task-2", ["two-sum"], 0.0, error_codes=["off_by_one", "edge_case"]))
    state = model.state()
    assert state.error_counts == {"off_by_one": 2, "edge_case": 1}


def test_duplicate_event_is_idempotent():
    model = LearnerModel(_profile())
    event = _event("e1", "task-1", ["two-sum"], 0.8)
    model.apply_evidence(event)
    snapshot = model.state().to_dict()
    model.apply_evidence(event)
    assert model.state().to_dict() == snapshot


def test_replay_is_deterministic():
    events = [
        _event("e1", "task-1", ["two-sum"], 0.5, created_at="2026-01-01T00:00:00Z"),
        _event("e2", "task-2", ["arrays"], 0.9, created_at="2026-01-01T00:01:00Z"),
        _event("e3", "task-1", ["two-sum"], 0.2, created_at="2026-01-01T00:02:00Z"),
    ]
    first = LearnerModel(_profile()).replay(events)
    second = LearnerModel(_profile()).replay(events)
    assert first.to_dict() == second.to_dict()
    assert first.updated_at == "2026-01-01T00:02:00Z"


def test_replay_order_matters_and_can_be_reproduced():
    profile = _profile()
    events = [
        _event("e1", "task-1", ["two-sum"], 1.0),
        _event("e2", "task-1", ["two-sum"], 0.0),
    ]
    forward = LearnerModel(profile).replay(events).mastery["two-sum"]
    reversed_state = LearnerModel(profile).replay(list(reversed(events))).mastery["two-sum"]
    assert forward != reversed_state


def test_replay_from_non_empty_model_is_clean():
    model = LearnerModel(_profile())
    model.apply_evidence(_event("stale", "task-0", ["old-skill"], 0.9))
    state = model.replay([_event("e1", "task-1", ["two-sum"], 0.8)])
    assert "old-skill" not in state.mastery
    assert state.evidence_count == 1


def test_foreign_learner_evidence_is_rejected():
    model = LearnerModel(_profile("learner-001"))
    with pytest.raises(ValueError):
        model.apply_evidence(_event("e1", "task-1", ["two-sum"], 0.8, learner_id="someone-else"))


def test_state_snapshot_is_a_copy():
    model = LearnerModel(_profile())
    model.apply_evidence(_event("e1", "task-1", ["two-sum"], 0.8))
    snapshot = model.state()
    snapshot.mastery["two-sum"] = 0.0
    assert model.state().mastery["two-sum"] > 0.0


def test_invalid_inputs_fail_closed():
    model = LearnerModel(_profile())
    with pytest.raises(TypeError):
        LearnerModel({"learner_id": "x"})  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        model.apply_evidence({"event_id": "e"})  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        model.replay("not-a-list")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        model.register_task_skills("", ["two-sum"])
