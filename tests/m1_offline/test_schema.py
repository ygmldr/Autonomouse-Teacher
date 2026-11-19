"""Schema contract tests for ``m1_offline.types`` (v0).

Covers: schema_version, lossless JSON round-trips for every record, enum and
required-field validation, provenance handling and current UTC timestamp
defaults.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

import pytest

from m1_offline import types as t

SCHEMA_VERSION = "m1.offline.v0"
UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def _records() -> list[t.Record]:
    provenance = t.Provenance(experiment_id="exp-synthetic-001", source="synthetic")
    task = t.LearningTask(
        task_id="task-001",
        goal_id="goal-001",
        skill_ids=["two-sum"],
        task_type="CF_PROBLEM",
    )
    return [
        provenance,
        t.SkillNode(
            skill_id="two-sum",
            name="Two Sum",
            domain="algorithms",
            prerequisites=["arrays"],
            description="synthetic skill",
        ),
        t.KnowledgeSource(
            source_id="ks-001",
            uri="cc0://synthetic/source-001",
            publisher="synthetic-publisher",
            published_at="2026-01-01T00:00:00Z",
            observed_at="2026-01-02T00:00:00Z",
            valid_until="2026-06-01T00:00:00Z",
            confidence=0.8,
            claim_status="REPORTED",
        ),
        t.KnowledgeRevision(
            revision_id="kr-001",
            source_id="ks-001",
            old_hash="a" * 64,
            new_hash="b" * 64,
            change_kind="UPDATE",
            detected_at="2026-02-01T00:00:00Z",
            claim_status="REPORTED",
            notes="synthetic revision",
        ),
        t.LearnerProfile(
            learner_id="learner-001",
            display_name="Synthetic Learner",
            baseline_level="BEGINNER",
        ),
        t.EvidenceEvent(
            event_id="ev-001",
            learner_id="learner-001",
            task_id="task-001",
            kind="ANSWER",
            payload={"skill_ids": ["two-sum"], "answer": "synthetic"},
            observed_score=0.75,
            error_codes=["off_by_one"],
            provenance=provenance,
        ),
        t.LearnerState(
            learner_id="learner-001",
            mastery={"two-sum": 0.75},
            error_counts={"off_by_one": 1},
            evidence_count=3,
        ),
        t.LearningGoal(
            goal_id="goal-001",
            learner_id="learner-001",
            target_skills=["two-sum", "binary-search"],
            deadline_days=14,
            weekly_minutes=180,
        ),
        task,
        t.CurriculumPlan(
            plan_id="plan-001",
            goal_id="goal-001",
            tasks=[task],
            rationale=["POLICY: planner_v0", "BALANCE: 0 review + 1 new"],
            policy_version="planner_v0",
        ),
        t.TeacherAction(
            action_id="act-001",
            kind="LIGHT_HINT",
            content="synthetic hint",
            rationale="no evidence yet -> LIGHT_HINT",
            hint_level=1,
            target_skill_ids=["two-sum"],
            evidence_refs=["ev-001"],
        ),
        t.DiagnosticResult(
            diagnosis_id="diag-001",
            task_id="task-001",
            error_codes=["off_by_one"],
            confidence=0.9,
            status="RESOLVED",
            explanation="output differs by exactly one",
            evidence_refs=["ev-001"],
        ),
        t.AssessmentResult(
            assessment_id="assess-001",
            task_id="task-001",
            learner_id="learner-001",
            scorer_id="scorer-v0",
            passed=True,
            score=0.9,
            dimensions={"correctness": 1.0, "complexity": 0.75},
            failure_modes=[],
            hidden_cases_passed=3,
            hidden_cases_total=4,
        ),
        t.RuntimeRequest(
            request_id="req-001",
            session_id="session-001",
            messages=[{"role": "user", "content": "synthetic prompt"}],
            tools=[],
            metadata={"mock": True},
        ),
        t.RuntimeResponse(
            request_id="req-001",
            session_id="session-001",
            text="synthetic reply",
            tool_events=[{"tool": "mock", "status": "ok"}],
            usage={"prompt_tokens": 3, "completion_tokens": 3, "total_tokens": 6},
            error=None,
            simulated=True,
        ),
        t.TraceEvent(
            event_id="trace-001",
            loop_id="loop-001",
            round=0,
            step="plan",
            payload={"kind": "FACT", "source": "synthetic-fixture"},
        ),
    ]


def test_schema_version_constant():
    assert t.SCHEMA_VERSION == SCHEMA_VERSION
    assert t.Record.SCHEMA_VERSION == SCHEMA_VERSION
    assert t.Provenance(experiment_id="exp").schema_version == SCHEMA_VERSION


@pytest.mark.parametrize("record", _records(), ids=lambda record: type(record).__name__)
def test_to_dict_contains_schema_version(record: t.Record):
    data = record.to_dict()
    assert data["schema_version"] == SCHEMA_VERSION
    assert list(data)[0] == "schema_version"


@pytest.mark.parametrize("record", _records(), ids=lambda record: type(record).__name__)
def test_lossless_json_roundtrip(record: t.Record):
    data = record.to_dict()
    encoded = json.dumps(data, ensure_ascii=False)
    restored = type(record).from_dict(json.loads(encoded))
    assert restored == record
    assert restored.to_dict() == data
    assert type(record).from_json(record.to_json()) == record


def test_nested_provenance_and_tasks_roundtrip():
    event = _records()[5]
    assert isinstance(event, t.EvidenceEvent)
    data = event.to_dict()
    assert data["provenance"]["experiment_id"] == "exp-synthetic-001"
    restored = t.EvidenceEvent.from_dict(data)
    assert isinstance(restored.provenance, t.Provenance)
    assert restored.provenance.to_dict() == event.provenance.to_dict()

    plan = _records()[9]
    assert isinstance(plan, t.CurriculumPlan)
    restored_plan = t.CurriculumPlan.from_dict(plan.to_dict())
    assert all(isinstance(task, t.LearningTask) for task in restored_plan.tasks)
    assert restored_plan.tasks == plan.tasks


@pytest.mark.parametrize(
    "factory",
    [
        lambda: t.KnowledgeSource(
            source_id="s",
            uri="cc0://s",
            publisher="p",
            published_at="2026-01-01T00:00:00Z",
            observed_at="2026-01-01T00:00:00Z",
            claim_status="NOT_A_STATUS",
        ),
        lambda: t.KnowledgeRevision(
            revision_id="r",
            source_id="s",
            old_hash="a",
            new_hash="b",
            change_kind="DELETE",
            detected_at="2026-01-01T00:00:00Z",
            claim_status="VERIFIED",
        ),
        lambda: t.LearnerProfile(learner_id="l", baseline_level="EXPERT"),
        lambda: t.EvidenceEvent(
            event_id="e", learner_id="l", task_id="t", kind="HOMEWORK", payload={}
        ),
        lambda: t.LearningTask(task_id="t", goal_id="g", skill_ids=["s"], task_type="ESSAY"),
        lambda: t.TeacherAction(action_id="a", kind="TELL_ANSWER", content="c", rationale="r"),
        lambda: t.DiagnosticResult(
            diagnosis_id="d",
            task_id="t",
            error_codes=[],
            confidence=0.5,
            status="FIXED",
            explanation="x",
        ),
    ],
    ids=[
        "claim_status",
        "change_kind",
        "baseline_level",
        "evidence_kind",
        "task_type",
        "action_kind",
        "diagnostic_status",
    ],
)
def test_enum_validation_fails_closed(factory):
    with pytest.raises(t.SchemaError):
        factory()


@pytest.mark.parametrize(
    "factory",
    [
        lambda: t.Provenance(experiment_id=""),
        lambda: t.SkillNode(skill_id="s", name="", domain="d"),
        lambda: t.EvidenceEvent(event_id="", learner_id="l", task_id="t", kind="ANSWER", payload={}),
        lambda: t.LearnerState(learner_id="l", mastery={"s": 1.2}, error_counts={}, evidence_count=0),
        lambda: t.LearnerState(learner_id="l", mastery={}, error_counts={"e": -1}, evidence_count=0),
        lambda: t.LearningGoal(goal_id="g", learner_id="l", target_skills=[]),
        lambda: t.LearningTask(task_id="t", goal_id="g", skill_ids=["s"], task_type="REVIEW", difficulty=9),
        lambda: t.TeacherAction(action_id="a", kind="LIGHT_HINT", content="c", rationale="r", hint_level=5),
        lambda: t.AssessmentResult(
            assessment_id="a",
            task_id="t",
            learner_id="l",
            scorer_id="s",
            passed=True,
            score=0.5,
            dimensions={},
            hidden_cases_passed=4,
            hidden_cases_total=2,
        ),
        lambda: t.KnowledgeSource(
            source_id="s",
            uri="u",
            publisher="p",
            published_at="2026-01-01T00:00:00Z",
            observed_at="2026-01-01T00:00:00Z",
            confidence=1.5,
        ),
    ],
    ids=[
        "empty_experiment_id",
        "empty_name",
        "empty_event_id",
        "mastery_gt_one",
        "negative_error_count",
        "empty_target_skills",
        "difficulty_gt_five",
        "hint_level_gt_four",
        "hidden_cases_inconsistent",
        "confidence_gt_one",
    ],
)
def test_field_validation_fails_closed(factory):
    with pytest.raises(t.SchemaError):
        factory()


def test_from_dict_rejects_unknown_field_and_schema_mismatch():
    payload = t.Provenance(experiment_id="exp").to_dict()
    with pytest.raises(t.SchemaError):
        t.Provenance.from_dict({**payload, "unexpected": 1})
    with pytest.raises(t.SchemaError):
        t.Provenance.from_dict({**payload, "schema_version": "m1.offline.v99"})
    with pytest.raises(t.SchemaError):
        t.Provenance.from_dict({**payload, "experiment_id": None})


def test_from_dict_fill_defaults_and_validate_enum():
    data = {"experiment_id": "exp"}
    restored = t.Provenance.from_dict(data)
    assert restored.schema_version == SCHEMA_VERSION
    assert UTC_RE.match(restored.created_at)
    with pytest.raises(t.SchemaError):
        t.LearnerProfile.from_dict({"learner_id": "l", "baseline_level": "GOD"})


def test_time_defaults_are_utc_iso8601():
    cases = [
        (t.Provenance(experiment_id="exp"), "created_at"),
        (t.LearnerProfile(learner_id="l"), "created_at"),
        (
            t.EvidenceEvent(
                event_id="e", learner_id="l", task_id="t", kind="ANSWER", payload={}
            ),
            "created_at",
        ),
        (
            t.LearnerState(learner_id="l", mastery={}, error_counts={}, evidence_count=0),
            "updated_at",
        ),
        (
            t.CurriculumPlan(
                plan_id="p",
                goal_id="g",
                tasks=[],
                rationale=["r"],
                policy_version="planner_v0",
            ),
            "created_at",
        ),
        (
            t.TraceEvent(event_id="e", loop_id="l", round=0, step="s", payload={}),
            "timestamp",
        ),
    ]
    for instance, attribute in cases:
        value = getattr(instance, attribute)
        assert UTC_RE.match(value), (type(instance).__name__, attribute, value)
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        assert abs((datetime.now(timezone.utc) - parsed).total_seconds()) < 300


def test_now_utc_format():
    value = t.now_utc()
    assert UTC_RE.match(value)
    assert value.endswith("Z")


def test_provenance_roundtrip_preserves_explicit_timestamp():
    provenance = t.Provenance(
        experiment_id="exp", source="synthetic", created_at="2020-01-02T03:04:05Z"
    )
    assert provenance.created_at == "2020-01-02T03:04:05Z"
    assert t.Provenance.from_dict(provenance.to_dict()).created_at == "2020-01-02T03:04:05Z"


def test_record_to_json_is_json_object():
    record = t.LearnerProfile(learner_id="l")
    data = json.loads(record.to_json())
    assert isinstance(data, dict)
    assert data["schema_version"] == SCHEMA_VERSION
