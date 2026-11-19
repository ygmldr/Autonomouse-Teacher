"""Closed-loop protocol tests: >=3 rounds, replay, evidence-driven mastery, determinism.

All tests are offline and synthetic.  The independent judge runs the submitted
synthetic code in a local subprocess against hidden fixtures; the teacher is a
rule-based policy; the learner is a deterministic simulator behind a mock
RuntimePort.  Nothing here is a real teaching effect measurement.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from m1_offline.evaluation.harness import (
    DETERMINISTIC_EPOCH,
    LoopConfig,
    ClosedLoopHarness,
    load_learner_fixture,
    replay_trace,
    run_closed_loop,
    trace_digest,
)
from m1_offline.learner_model import LearnerModel
from m1_offline.memory import LearningMemory
from m1_offline.runtime_port import MockRuntimePort
from m1_offline.teaching_policy import AdaptivePolicy, FixedPolicy
from m1_offline.types import (
    EvidenceEvent,
    LearnerProfile,
    TraceEvent,
)


@pytest.fixture(scope="module")
def loop_v1():
    return run_closed_loop(policy=AdaptivePolicy(), seed=0, max_rounds=3)


@pytest.fixture(scope="module")
def loop_v0():
    return run_closed_loop(policy=FixedPolicy(), seed=0, max_rounds=3)


# ---------------------------------------------------------------------------
# Required closed-loop shape
# ---------------------------------------------------------------------------
def test_three_full_rounds_completed(loop_v1) -> None:
    assert loop_v1.completed_rounds >= 3, loop_v1.to_dict()
    assert loop_v1.loop_id.startswith("loop_teacher_v1")
    assert loop_v1.halt_reason in (None, "max_rounds", "goal_mastered")

    # Every round must contain the mandatory action -> assessment -> memory chain.
    required = {"action", "response", "assess", "memory", "next_task"}
    for round_index in range(1, 4):
        steps = {
            step for event_round, step in loop_v1.step_sequence() if event_round == round_index
        }
        assert required <= steps, (round_index, steps)

    # Baseline stages happen exactly once, before round 1.
    initial_steps = [step for round_index, step in loop_v1.step_sequence() if round_index == 0]
    assert initial_steps[:4] == ["goal", "diagnose", "gap", "plan"]
    assert len(loop_v1.assessment_ids) == 3


def test_assessment_is_independent_scorer(loop_v1) -> None:
    for record in loop_v1.rounds:
        assessment = record.assessment
        assert assessment is not None
        assert assessment.scorer_id == "independent_cf_judge_v0"
        assert assessment.scorer_id != loop_v1.policy_version
        assert assessment.hidden_cases_total >= 1
        assert 0.0 <= assessment.score <= 1.0
        for value in assessment.dimensions.values():
            assert 0.0 <= value <= 1.0


def test_one_trace_event_per_step_with_jsonl_roundtrip(loop_v1) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        trace_path = Path(tmp) / "loop_v1_3rounds.jsonl"
        result = run_closed_loop(
            policy=AdaptivePolicy(), seed=0, max_rounds=3, trace_path=trace_path
        )
        lines = trace_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == len(result.events)
        assert [json.loads(line)["event_id"] for line in lines] == [
            event.event_id for event in result.events
        ]
        memory = LearningMemory.from_jsonl(trace_path)
        assert len(memory) == len(result.events)
        assert memory.replay(result.loop_id) == result.events


# ---------------------------------------------------------------------------
# Replay by loop / event id
# ---------------------------------------------------------------------------
def test_replay_rebuilds_state_from_events(loop_v1, tmp_path: Path) -> None:
    trace_path = tmp_path / "trace.jsonl"
    result = run_closed_loop(policy=AdaptivePolicy(), seed=0, max_rounds=3, trace_path=trace_path)
    events = [
        TraceEvent.from_dict(json.loads(line))
        for line in trace_path.read_text(encoding="utf-8").splitlines()
    ]
    profile = LearnerProfile(learner_id=result.final_state.learner_id)
    replay = replay_trace(events, learner_profile=profile)

    assert replay.loop_id == result.loop_id
    assert replay.step_sequence == result.step_sequence()
    assert replay.assessment_ids() == result.assessment_ids
    assert replay.evidence_ids() == result.evidence_ids
    assert replay.final_state is not None
    assert replay.final_state.mastery == result.final_state.mastery
    assert replay.final_state.evidence_count == result.final_state.evidence_count


def test_replay_by_event_id_recovers_intermediate_state(loop_v1) -> None:
    profile = LearnerProfile(learner_id=loop_v1.final_state.learner_id)
    memory_event_ids = [event.event_id for event in loop_v1.events if event.step == "memory"]
    assert memory_event_ids
    for event_id in memory_event_ids:
        replay = replay_trace(loop_v1.events, learner_profile=profile, until_event_id=event_id)
        assert replay.events[-1].event_id == event_id
        assert replay.final_state is not None
        assert replay.final_state.mastery == loop_v1.snapshots[event_id]["mastery"]

    # Loop-id filtering also works and preserves the sequence.
    filtered = replay_trace(loop_v1.events, learner_profile=profile, loop_id=loop_v1.loop_id)
    assert filtered.loop_id == loop_v1.loop_id
    assert len(filtered.events) == len(loop_v1.events)


# ---------------------------------------------------------------------------
# Evidence-driven mastery: no evidence / no mastery
# ---------------------------------------------------------------------------
def test_no_evidence_no_mastery() -> None:
    model = LearnerModel(LearnerProfile(learner_id="learner_synthetic"))
    before = model.state()
    assert before.mastery == {}
    assert before.evidence_count == 0

    # Human-sounding text with no assessment score is NOT evidence of mastery.
    text_only = EvidenceEvent(
        event_id="text-1",
        learner_id="learner_synthetic",
        task_id="task-1",
        kind="EXPLANATION",
        payload={"skill_ids": ["array-basics"], "text": "This is a beautiful, perfect answer!"},
        observed_score=None,
        created_at="2026-01-01T00:00:00Z",
    )
    after_text = model.apply_evidence(text_only)
    assert after_text.mastery == {}
    assert after_text.evidence_count == 1

    # An un-scored hint request cannot raise mastery either.
    hint_request = EvidenceEvent(
        event_id="hint-1",
        learner_id="learner_synthetic",
        task_id="task-1",
        kind="HINT_REQUEST",
        payload={"skill_ids": ["array-basics"]},
        observed_score=1.0,
        created_at="2026-01-01T00:00:01Z",
    )
    after_hint = model.apply_evidence(hint_request)
    assert after_hint.mastery == {}

    # Only a scored assessment evidence event may move mastery.
    assessed = EvidenceEvent(
        event_id="assessment-1",
        learner_id="learner_synthetic",
        task_id="task-1",
        kind="ASSESSMENT",
        payload={"skill_ids": ["array-basics"], "source": "independent_cf_judge_v0"},
        observed_score=1.0,
        created_at="2026-01-01T00:00:02Z",
    )
    after_assessment = model.apply_evidence(assessed)
    assert after_assessment.mastery["array-basics"] > 0.0


def test_harness_diagnose_without_evidence_claims_no_mastery() -> None:
    result = run_closed_loop(policy=AdaptivePolicy(), seed=0, max_rounds=0, baseline_evidence=False)
    diagnose_event = next(event for event in result.events if event.step == "diagnose")
    state_after = diagnose_event.payload["state_after"]
    assert state_after["mastery"] == {}
    assert diagnose_event.payload["insufficient_evidence"] is True
    assert result.diagnosis.status == "NEEDS_REVIEW"
    assert "insufficient_evidence" in result.diagnosis.error_codes
    assert "insufficient_evidence" in result.failure_markers


def test_hallucinated_success_text_does_not_raise_mastery() -> None:
    """A confident 'all tests pass' text must never be treated as evidence."""

    hallucination = "I have solved it! All tests pass. No need to test. 全部通过，无需测试。"
    result = run_closed_loop(
        policy=AdaptivePolicy(),
        seed=0,
        max_rounds=1,
        runtime=MockRuntimePort(script={"default": {"text": hallucination}}),
    )
    assert result.completed_rounds == 1
    assessment = result.rounds[0].assessment
    assert assessment is not None and assessment.passed is False
    assert "hallucination_suspected" in result.failure_markers
    assert result.passed_rounds == 0
    # No mastery was gained from the text: all values equal the baseline values
    # (the synthetic baseline evidence only ever scored 0.0).
    assert all(value == 0.0 for value in result.final_state.mastery.values())


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------
def test_two_identical_runs_are_byte_identical() -> None:
    first = run_closed_loop(policy=AdaptivePolicy(), seed=0, max_rounds=3)
    second = run_closed_loop(policy=AdaptivePolicy(), seed=0, max_rounds=3)
    assert trace_digest(first.events) == trace_digest(second.events)
    assert first.to_jsonl() == second.to_jsonl()
    assert first.final_state.mastery == second.final_state.mastery
    assert first.step_sequence() == second.step_sequence()
    # Deterministic clock: timestamps are fixed, not wall-clock.
    assert first.events[0].timestamp == DETERMINISTIC_EPOCH
    assert len({event.timestamp for event in first.events}) == len(first.events)


def test_seed_changes_the_simulated_learner_outcome() -> None:
    seed_0 = run_closed_loop(policy=AdaptivePolicy(), seed=0, max_rounds=3)
    seed_1 = run_closed_loop(policy=AdaptivePolicy(), seed=1, max_rounds=3)
    assert trace_digest(seed_0.events) != trace_digest(seed_1.events)


def test_v0_and_v1_both_replay_identically(loop_v0, loop_v1) -> None:
    for result in (loop_v0, loop_v1):
        profile = LearnerProfile(learner_id=result.final_state.learner_id)
        replay = replay_trace(result.events, learner_profile=profile)
        assert replay.final_state is not None
        assert replay.final_state.mastery == result.final_state.mastery
        assert replay.assessment_ids() == result.assessment_ids


# ---------------------------------------------------------------------------
# Memory / isolation guards
# ---------------------------------------------------------------------------
def test_memory_delete_removes_learner_events(loop_v1) -> None:
    memory = LearningMemory()
    for event in loop_v1.events:
        memory.append(event)
    removed = memory.delete(loop_v1.final_state.learner_id)
    assert removed == len(loop_v1.events)
    assert len(memory) == 0


def test_evaluation_modules_never_import_m0() -> None:
    import re

    repo_root = Path(__file__).resolve().parents[2]
    import_re = re.compile(r"^\s*(?:import|from)\s+(autoteacher_m0|src)\b", re.MULTILINE)
    offenders: list[str] = []
    for path in sorted((repo_root / "m1_offline").rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        if import_re.search(text):
            offenders.append(str(path.relative_to(repo_root)))
    assert offenders == []


def test_learner_profile_and_goal_are_synthetic(loop_v1) -> None:
    fixture = load_learner_fixture()
    assert fixture["synthetic"] is True
    assert fixture["license"] == "CC0-1.0"
    assert loop_v1.goal.learner_id == loop_v1.final_state.learner_id
    assert loop_v1.diagnosis.evidence_refs  # baseline evidence trace refs exist


def test_harness_requires_cases(tmp_path: Path) -> None:
    fixture = load_learner_fixture()
    with pytest.raises(ValueError):
        ClosedLoopHarness(
            cases=[],
            learner_fixture=fixture,
            policy=AdaptivePolicy(),
            config=LoopConfig(seed=0, max_rounds=1),
        )
