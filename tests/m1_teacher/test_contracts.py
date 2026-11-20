"""Contract-freeze tests for ``m1a.v0`` records, enums and errors (B-PR1a).

These tests are the executable definition of the frozen contract:

* every record round-trips losslessly through ``to_dict``/``from_dict`` and
  ``to_json``/``from_json`` and includes ``schema_version``;
* ``from_dict`` is fail-closed (unknown fields, missing/wrong schema version,
  missing required fields);
* construction-time validation rejects invalid enums, out-of-range numbers,
  wrong types, malformed timestamps and structurally invalid nested payloads;
* no teacher-visible type has answer/expected/correct/solution fields;
* cross-field invariants (objective success criteria, assessment score range,
  snapshot mastery consistency) are enforced.
"""

from __future__ import annotations

import json
import re
from dataclasses import MISSING, fields, is_dataclass, replace
from datetime import datetime, timezone
from typing import Any, Callable

import pytest

from m1_teacher.contracts import (
    ENUM_VALUES,
    FORBIDDEN_TEACHER_FIELD_TOKENS,
    RECORD_TYPES,
    SCHEMA_VERSION,
    AssessmentItem,
    AssessmentResult,
    ConflictError,
    CurriculumPlan,
    DiagnosisResult,
    EvidenceReference,
    HistoryEvent,
    KnowledgeNode,
    LearnerGoal,
    LearnerSnapshot,
    LearningObjective,
    M1AError,
    MasteryEstimate,
    NotFoundError,
    PlanStep,
    PrerequisiteEdge,
    Reason,
    Record,
    SessionState,
    TeachingAction,
    UnsupportedOperationError,
    ValidationError,
    now_utc,
    to_iso8601,
)

# ---------------------------------------------------------------------------
# Representative instances (one per frozen record type)
# ---------------------------------------------------------------------------


def _reason() -> Reason:
    return Reason(
        code="POLICY.PREREQ_GAP",
        node_ids=["cf.search.binary"],
        detail="hard prerequisite mastery below threshold",
        policy_version="policy.v0",
    )


def _mastery(node_id: str = "cf.search.binary") -> MasteryEstimate:
    return MasteryEstimate(node_id=node_id, value=0.5, confidence=0.8, evidence_count=3)


def _node() -> KnowledgeNode:
    return KnowledgeNode(
        node_id="cf.search.binary",
        domain_id="cf_binary_search",
        title="二分查找",
        description="在有序数组中查找目标值的对数时间算法",
        difficulty=3,
        assessment_mode="DETERMINISTIC_JUDGE",
        tags=["search", "binary"],
    )


def _edge() -> PrerequisiteEdge:
    return PrerequisiteEdge(
        source_node_id="cf.sort.sortedness",
        target_node_id="cf.search.binary",
        kind="HARD",
        weight=1.0,
    )


def _objective() -> LearningObjective:
    return LearningObjective(
        objective_id="obj.cf.binary_search.mastery",
        domain_id="cf_binary_search",
        title="掌握二分查找与边界处理",
        description="实现二分查找及边界变体",
        target_node_ids=[
            "cf.search.binary",
            "cf.search.boundary",
            "cf.search.lower_upper",
            "cf.complexity.log",
        ],
        success_criteria={
            "min_mastery": 0.7,
            "required_node_ids": ["cf.search.binary", "cf.search.boundary"],
            "max_error_rate": 0.3,
        },
        estimated_minutes=120,
    )


def _item() -> AssessmentItem:
    return AssessmentItem(
        item_id="item.bs.mcq.002",
        domain_id="cf_binary_search",
        node_ids=["cf.sort.sortedness"],
        item_type="MCQ",
        difficulty=2,
        prompt="二分查找能够正确工作的关键输入前提是什么？",
        options=["有序", "无序", "全为正数", "长度为奇数"],
        max_score=1.0,
        deterministic=True,
        scoring_spec_ref="scoring/item.bs.mcq.002.json",
    )


def _result() -> AssessmentResult:
    return AssessmentResult(
        result_id="result.0001",
        item_id="item.bs.mcq.002",
        learner_id="learner.a",
        status="CORRECT",
        scorer_id="scorer.deterministic.v0",
        score=1.0,
        max_score=1.0,
        failure_reason="",
        evidence_refs=["evt.0002"],
    )


def _action() -> TeachingAction:
    return TeachingAction(
        action_id="action.0001",
        kind="HINT",
        node_ids=["cf.search.binary"],
        content="观察区间收缩方式",
        reason=_reason(),
        item_id="item.bs.code.001",
        evidence_refs=["evt.0002"],
    )


def _evidence() -> EvidenceReference:
    return EvidenceReference(
        evidence_id="evd.0001",
        source="OBSERVED",
        event_id="evt.0002",
        detail="correct answer observed",
    )


def _snapshot() -> LearnerSnapshot:
    return LearnerSnapshot(
        learner_id="learner.a",
        masteries={"cf.search.binary": _mastery()},
        completed_item_ids=["item.bs.mcq.002"],
        error_counts={"off_by_one": 2},
        revision=4,
    )


def _goal() -> LearnerGoal:
    return LearnerGoal(
        goal_id="goal.0001",
        learner_id="learner.a",
        objective_id="obj.cf.binary_search.mastery",
        status="ACTIVE",
    )


def _event() -> HistoryEvent:
    return HistoryEvent(
        event_id="evt.0002",
        learner_id="learner.a",
        session_id="session.0001",
        seq=2,
        event_type="ASSESSED",
        payload={"item_id": "item.bs.mcq.002", "status": "CORRECT", "score": 1.0},
    )


def _session() -> SessionState:
    return SessionState(
        session_id="session.0001",
        learner_id="learner.a",
        goal_id="goal.0001",
        objective_id="obj.cf.binary_search.mastery",
        phase="TEACH",
        turn_index=3,
        pending_item_id=None,
    )


def _plan_step() -> PlanStep:
    return PlanStep(
        step_id="step.0001",
        ordinal=0,
        phase="TEACH",
        node_ids=["cf.search.binary"],
        action_kind="EXPLAIN",
        rationale=_reason(),
        item_id=None,
    )


def _plan() -> CurriculumPlan:
    return CurriculumPlan(
        plan_id="plan.0001",
        learner_id="learner.a",
        goal_id="goal.0001",
        objective_id="obj.cf.binary_search.mastery",
        steps=[_plan_step()],
        policy_version="policy.v0",
    )


def _diagnosis() -> DiagnosisResult:
    return DiagnosisResult(
        diagnosis_id="diag.0001",
        learner_id="learner.a",
        status="READY",
        target_node_id="cf.search.boundary",
        selected_item_id="item.bs.code.001",
        hypothesis="off-by-one boundary handling",
        reason=_reason(),
        evidence_refs=["evt.0002"],
    )


FACTORIES: dict[type[Record], Callable[[], Record]] = {
    KnowledgeNode: _node,
    PrerequisiteEdge: _edge,
    LearningObjective: _objective,
    AssessmentItem: _item,
    AssessmentResult: _result,
    Reason: _reason,
    TeachingAction: _action,
    EvidenceReference: _evidence,
    MasteryEstimate: _mastery,
    LearnerSnapshot: _snapshot,
    LearnerGoal: _goal,
    HistoryEvent: _event,
    SessionState: _session,
    PlanStep: _plan_step,
    CurriculumPlan: _plan,
    DiagnosisResult: _diagnosis,
}

RECORD_IDS = [record_type.__name__ for record_type in FACTORIES]


def _required_field_names(record_type: type[Record]) -> list[str]:
    required: list[str] = []
    for spec in fields(record_type):
        if spec.default is MISSING and spec.default_factory is MISSING:
            required.append(spec.name)
    return required


def _expected_enums() -> dict[str, tuple[str, ...]]:
    return {
        "ASSESSMENT_STATUS": (
            "CORRECT",
            "INCORRECT",
            "PARTIAL",
            "NEEDS_REVIEW",
            "EVAL_ERROR",
        ),
        "EVIDENCE_SOURCE": ("OBSERVED", "INFERRED"),
        "EDGE_KIND": ("HARD", "SOFT"),
        "ASSESSMENT_MODE": (
            "DETERMINISTIC_JUDGE",
            "RULE_RUBRIC",
            "HUMAN_REVIEW_REQUIRED",
        ),
        "ITEM_TYPE": ("MCQ", "CODE", "SHORT_ANSWER"),
        "TEACHING_ACTION_KIND": (
            "DIAGNOSE",
            "EXPLAIN",
            "HINT",
            "PRACTICE",
            "REVIEW",
            "RETEACH",
            "REASSESS",
            "GOAL_COMPLETE",
            "SESSION_PAUSE",
            "SESSION_RESUME",
            # B-NEXT B-PR4 additive values (vertical interview turns).
            "SOCRATIC_QUESTION",
            "ASK_CLARIFICATION",
        ),
        "SESSION_PHASE": (
            "DIAGNOSE",
            "TEACH",
            "PRACTICE",
            "ASSESS",
            "UPDATE",
            "REVIEW",
            "COMPLETE",
            "PAUSED",
        ),
        "HISTORY_EVENT_TYPE": (
            "SESSION_STARTED",
            "PLAN_CREATED",
            "DIAGNOSIS_COMPLETED",
            "ITEM_PRESENTED",
            "RESPONSE_SUBMITTED",
            "ASSESSED",
            "MASTERY_UPDATED",
            "ACTION_TAKEN",
            "SESSION_PAUSED",
            "SESSION_RESUMED",
            "GOAL_COMPLETED",
            "ERROR",
            # B-NEXT B-PR2 additive event type (durable assessment attempt).
            "ASSESSMENT_PREPARED",
        ),
        "DIAGNOSIS_STATUS": ("READY", "INSUFFICIENT_EVIDENCE"),
        "GOAL_STATUS": ("ACTIVE", "COMPLETED", "PAUSED"),
    }


# ---------------------------------------------------------------------------
# Schema version and enum freeze
# ---------------------------------------------------------------------------


def test_contract_version_is_frozen() -> None:
    assert SCHEMA_VERSION == "m1a.v0"
    assert Record.schema_version == "m1a.v0"
    for record_type in RECORD_TYPES:
        assert issubclass(record_type, Record)
        assert record_type.schema_version == "m1a.v0"
        assert is_dataclass(record_type)
    assert set(RECORD_TYPES) == set(FACTORIES)


def test_enums_are_frozen_uppercase_strings() -> None:
    assert ENUM_VALUES == _expected_enums()
    for values in ENUM_VALUES.values():
        assert isinstance(values, tuple)
        for value in values:
            assert isinstance(value, str)
            assert value == value.upper()
            assert value.strip() == value


@pytest.mark.parametrize("record_type", FACTORIES, ids=RECORD_IDS)
def test_every_record_roundtrips_through_dict_json(record_type: type[Record]) -> None:
    record = FACTORIES[record_type]()
    payload = record.to_dict()
    assert payload["schema_version"] == "m1a.v0"
    assert record_type.from_dict(payload) == record
    assert record_type.from_dict(payload).to_dict() == payload
    assert record_type.from_json(record.to_json()) == record
    assert record.to_json() == record.to_json()  # deterministic serialisation
    assert json.loads(record.to_json()) == payload


@pytest.mark.parametrize("record_type", FACTORIES, ids=RECORD_IDS)
def test_unknown_fields_are_rejected(record_type: type[Record]) -> None:
    payload = FACTORIES[record_type]().to_dict()
    payload["unexpected_field"] = "boom"
    with pytest.raises(ValidationError, match="unknown field"):
        record_type.from_dict(payload)


@pytest.mark.parametrize("record_type", FACTORIES, ids=RECORD_IDS)
def test_missing_schema_version_is_rejected(record_type: type[Record]) -> None:
    payload = FACTORIES[record_type]().to_dict()
    del payload["schema_version"]
    with pytest.raises(ValidationError, match="missing schema_version"):
        record_type.from_dict(payload)


@pytest.mark.parametrize("record_type", FACTORIES, ids=RECORD_IDS)
def test_wrong_schema_version_is_rejected(record_type: type[Record]) -> None:
    payload = FACTORIES[record_type]().to_dict()
    payload["schema_version"] = "m1a.v999"
    with pytest.raises(ValidationError, match="schema_version"):
        record_type.from_dict(payload)


@pytest.mark.parametrize("record_type", FACTORIES, ids=RECORD_IDS)
def test_missing_required_field_is_rejected(record_type: type[Record]) -> None:
    required = _required_field_names(record_type)
    assert required, f"{record_type.__name__} must have at least one required field"
    payload = FACTORIES[record_type]().to_dict()
    del payload[required[0]]
    with pytest.raises(ValidationError, match="missing required field"):
        record_type.from_dict(payload)


def test_from_dict_rejects_non_mapping_input() -> None:
    for bad in (None, [], "{}", 42):
        with pytest.raises(ValidationError):
            KnowledgeNode.from_dict(bad)  # type: ignore[arg-type]


def test_from_json_rejects_invalid_json_and_non_mapping_json() -> None:
    with pytest.raises(ValidationError, match="invalid JSON"):
        KnowledgeNode.from_json("{not json")
    with pytest.raises(ValidationError):
        KnowledgeNode.from_json("[]")
    with pytest.raises(ValidationError):
        KnowledgeNode.from_json(None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Enum / range / type fail-closed validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("factory", "field_name", "bad_value"),
    [
        (_node, "assessment_mode", "MAYBE_DETERMINISTIC"),
        (_edge, "kind", "MEDIUM"),
        (_item, "item_type", "ESSAY"),
        (_result, "status", "OK"),
        (_evidence, "source", "GUESSED"),
        (_goal, "status", "DONE"),
        (_action, "kind", "LECTURE"),
        (_event, "event_type", "UNKNOWN_EVENT"),
        (_session, "phase", "IDLE"),
        (_plan_step, "phase", "READING"),
        (_plan_step, "action_kind", "NOPE"),
        (_diagnosis, "status", "MAYBE"),
    ],
)
def test_invalid_enum_values_fail_closed(
    factory: Callable[[], Record], field_name: str, bad_value: str
) -> None:
    record = factory()
    with pytest.raises(ValidationError, match=field_name):
        replace(record, **{field_name: bad_value})
    payload = record.to_dict()
    payload[field_name] = bad_value
    with pytest.raises(ValidationError, match=field_name):
        type(record).from_dict(payload)


@pytest.mark.parametrize(
    ("factory", "field_name", "bad_value"),
    [
        (_node, "difficulty", 0),
        (_node, "difficulty", 6),
        (_edge, "weight", -0.1),
        (_edge, "weight", 1.1),
        (_mastery, "value", -0.01),
        (_mastery, "value", 1.01),
        (_mastery, "confidence", 1.5),
        (_mastery, "evidence_count", -1),
        (_event, "seq", -1),
        (_session, "turn_index", -1),
        (_snapshot, "revision", -1),
        (_plan_step, "ordinal", -1),
        (_objective, "estimated_minutes", -1),
        (_item, "difficulty", 0),
        (_item, "max_score", -0.5),
        (_result, "score", 1.5),
        (_result, "score", -0.1),
        (_result, "max_score", 0.0),
    ],
)
def test_out_of_range_values_fail_closed(
    factory: Callable[[], Record], field_name: str, bad_value: float | int
) -> None:
    record = factory()
    with pytest.raises(ValidationError, match=field_name):
        replace(record, **{field_name: bad_value})
    payload = record.to_dict()
    payload[field_name] = bad_value
    with pytest.raises(ValidationError, match=field_name):
        type(record).from_dict(payload)


@pytest.mark.parametrize(
    ("factory", "field_name", "bad_value"),
    [
        (_node, "difficulty", True),
        (_node, "difficulty", "3"),
        (_node, "description", 5),
        (_node, "tags", "array"),
        (_node, "tags", [1]),
        (_item, "deterministic", 1),
        (_item, "max_score", "1.0"),
        (_event, "payload", []),
        (_snapshot, "error_counts", {"off_by_one": -1}),
        (_snapshot, "error_counts", {"off_by_one": "2"}),
        (_action, "reason", {"code": "NOT_A_RECORD"}),
        (_plan_step, "rationale", None),
        (_plan, "steps", [{"step_id": "x"}]),
    ],
)
def test_wrong_types_fail_closed(
    factory: Callable[[], Record], field_name: str, bad_value: Any
) -> None:
    record = factory()
    with pytest.raises(ValidationError, match=field_name):
        replace(record, **{field_name: bad_value})


def test_blank_identifiers_are_rejected() -> None:
    with pytest.raises(ValidationError, match="node_id"):
        replace(_node(), node_id="   ")
    with pytest.raises(ValidationError, match="code"):
        Reason(code="")


def test_non_finite_numbers_are_rejected() -> None:
    with pytest.raises(ValidationError):
        replace(_mastery(), value=float("nan"))
    with pytest.raises(ValidationError):
        replace(_mastery(), value=float("inf"))


def test_nested_payload_must_be_json_serialisable() -> None:
    with pytest.raises(ValidationError, match="payload"):
        HistoryEvent(
            event_id="evt.bad",
            learner_id="learner.a",
            session_id="session.a",
            seq=0,
            event_type="ERROR",
            payload={"bad": {1, 2, 3}},
        )
    with pytest.raises(ValidationError, match="payload"):
        HistoryEvent(
            event_id="evt.bad",
            learner_id="learner.a",
            session_id="session.a",
            seq=0,
            event_type="ERROR",
            payload={1: "non-string-key"},
        )


# ---------------------------------------------------------------------------
# Timestamps
# ---------------------------------------------------------------------------


def test_now_utc_and_to_iso8601_are_canonical() -> None:
    stamp = now_utc()
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", stamp), stamp
    assert to_iso8601(datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)) == (
        "2026-01-02T03:04:05Z"
    )
    with pytest.raises(ValidationError):
        to_iso8601(datetime(2026, 1, 2, 3, 4, 5))  # naive datetime rejected
    with pytest.raises(ValidationError):
        to_iso8601("2026-01-02T03:04:05Z")  # type: ignore[arg-type]


@pytest.mark.parametrize("record_type", FACTORIES, ids=RECORD_IDS)
def test_default_timestamps_are_canonical(record_type: type[Record]) -> None:
    payload = FACTORIES[record_type]().to_dict()
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", payload["created_at"])


def test_explicit_utc_offset_is_normalised_to_z() -> None:
    node = _node()
    node_plus = replace(node, created_at="2026-01-02T03:04:05+00:00")
    assert node_plus.created_at == "2026-01-02T03:04:05Z"
    assert node_plus.to_dict()["created_at"] == "2026-01-02T03:04:05Z"


@pytest.mark.parametrize(
    "bad_timestamp",
    [
        "2026-01-02T03:04:05",  # missing timezone
        "2026-01-02 03:04:05Z",  # space instead of T
        "2026-13-02T03:04:05Z",  # month 13
        "2026-01-02T03:04:05.123Z",  # sub-second precision not allowed
        "2026-01-02T03:04:05+01:00",  # not UTC
        123,
        datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
    ],
)
def test_malformed_timestamps_fail_closed(bad_timestamp: Any) -> None:
    with pytest.raises(ValidationError):
        replace(_node(), created_at=bad_timestamp)


def test_missing_created_at_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _node().to_dict()
    del payload["created_at"]
    restored = KnowledgeNode.from_dict(payload)
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", restored.created_at)


# ---------------------------------------------------------------------------
# Answer-free teacher-visible contract
# ---------------------------------------------------------------------------

_ASSESSMENT_ITEM_FIELDS = frozenset(
    {
        "item_id",
        "domain_id",
        "node_ids",
        "item_type",
        "difficulty",
        "prompt",
        "options",
        "function_name",
        "max_score",
        "deterministic",
        "scoring_spec_ref",
        "created_at",
    }
)


def test_assessment_item_has_no_answer_fields() -> None:
    assert FORBIDDEN_TEACHER_FIELD_TOKENS == ("answer", "expected", "correct", "solution")
    item_field_names = {spec.name for spec in fields(AssessmentItem)}
    assert item_field_names == _ASSESSMENT_ITEM_FIELDS
    for name in item_field_names:
        lowered = name.lower()
        for token in FORBIDDEN_TEACHER_FIELD_TOKENS:
            assert token not in lowered, f"AssessmentItem.{name} leaks hidden-answer material"


def test_no_teacher_visible_record_has_answer_fields() -> None:
    for record_type in RECORD_TYPES:
        for spec in fields(record_type):
            lowered = spec.name.lower()
            for token in FORBIDDEN_TEACHER_FIELD_TOKENS:
                assert token not in lowered, f"{record_type.__name__}.{spec.name}"


def test_assessment_item_cannot_be_constructed_or_parsed_with_answer_fields() -> None:
    with pytest.raises(TypeError):
        AssessmentItem(
            item_id="item.bad",
            domain_id="cf_binary_search",
            node_ids=["cf.search.binary"],
            item_type="MCQ",
            difficulty=2,
            prompt="p",
            options=["a", "b"],
            answer="a",  # type: ignore[call-arg]
        )
    payload = _item().to_dict()
    for leaked_key in ("answer", "expected", "correct_option_index", "solution", "answer_key"):
        leaked = dict(payload)
        leaked[leaked_key] = "A"
        with pytest.raises(ValidationError, match="unknown field"):
            AssessmentItem.from_dict(leaked)


def test_serialised_items_have_no_answer_shaped_keys() -> None:
    pattern = re.compile(r'"(answer|expected|correct|solution)[a-z_]*"\s*:')
    serialised = json.dumps([_item().to_dict()], ensure_ascii=False)
    assert pattern.search(serialised) is None


def test_scoring_reference_is_an_opaque_string_not_scoring_content() -> None:
    item = _item()
    # The v0 contract allows only an opaque reference; it must stay a plain string.
    assert isinstance(item.scoring_spec_ref, str)
    assert not isinstance(item.scoring_spec_ref, (dict, list))


# ---------------------------------------------------------------------------
# Cross-field invariants
# ---------------------------------------------------------------------------


def test_objective_success_criteria_are_validated() -> None:
    base = _objective()
    assert base.success_criteria["required_node_ids"] == [
        "cf.search.binary",
        "cf.search.boundary",
    ]

    def _with(criteria: dict[str, Any]) -> LearningObjective:
        return replace(base, success_criteria=criteria)

    valid = {
        "min_mastery": 0.0,
        "required_node_ids": [],
        "max_error_rate": 1.0,
    }
    _with(valid)  # boundary values accepted

    with pytest.raises(ValidationError, match="missing required key"):
        _with({"min_mastery": 0.7, "max_error_rate": 0.3})
    with pytest.raises(ValidationError, match="unknown key"):
        _with(
            {
                "min_mastery": 0.7,
                "required_node_ids": [],
                "max_error_rate": 0.3,
                "extra": 1,
            }
        )
    with pytest.raises(ValidationError, match="min_mastery"):
        _with({"min_mastery": 1.2, "required_node_ids": [], "max_error_rate": 0.3})
    with pytest.raises(ValidationError, match="min_mastery"):
        _with({"min_mastery": "high", "required_node_ids": [], "max_error_rate": 0.3})
    with pytest.raises(ValidationError, match="max_error_rate"):
        _with({"min_mastery": 0.7, "required_node_ids": [], "max_error_rate": -0.1})
    with pytest.raises(ValidationError, match="required_node_ids"):
        _with({"min_mastery": 0.7, "required_node_ids": "cf.search.binary", "max_error_rate": 0.3})
    with pytest.raises(ValidationError, match="subset"):
        _with(
            {
                "min_mastery": 0.7,
                "required_node_ids": ["cf.not.a.target"],
                "max_error_rate": 0.3,
            }
        )
    with pytest.raises(ValidationError):
        replace(base, target_node_ids=[])


def test_assessment_result_score_range_invariants() -> None:
    result = _result()
    assert result.score == 1.0
    assert replace(result, score=0.0).score == 0.0
    assert replace(result, score=None, status="EVAL_ERROR").score is None
    with pytest.raises(ValidationError, match="score"):
        replace(result, score=1.01)
    with pytest.raises(ValidationError, match="score"):
        replace(result, score=-0.01)
    with pytest.raises(ValidationError, match="max_score"):
        replace(result, max_score=0.0)
    with pytest.raises(ValidationError, match="score"):
        replace(result, score="1.0")  # type: ignore[arg-type]


def test_learner_snapshot_nested_mastery_roundtrip_and_consistency() -> None:
    snapshot = _snapshot()
    payload = snapshot.to_dict()
    nested = payload["masteries"]["cf.search.binary"]
    assert nested["schema_version"] == "m1a.v0"
    assert LearnerSnapshot.from_dict(payload) == snapshot

    with pytest.raises(ValidationError, match="masteries"):
        LearnerSnapshot(
            learner_id="learner.a",
            masteries={"cf.search.binary": _mastery(node_id="cf.search.boundary")},
        )
    with pytest.raises(ValidationError):
        LearnerSnapshot(
            learner_id="learner.a",
            masteries={"cf.search.binary": {"node_id": "cf.search.binary"}},  # type: ignore[dict-item]
        )

    corrupted = snapshot.to_dict()
    corrupted["masteries"]["cf.search.binary"]["value"] = 2.0
    with pytest.raises(ValidationError, match="value"):
        LearnerSnapshot.from_dict(corrupted)

    nested_unknown = snapshot.to_dict()
    nested_unknown["masteries"]["cf.search.binary"]["unexpected"] = 1
    with pytest.raises(ValidationError, match="unknown field"):
        LearnerSnapshot.from_dict(nested_unknown)


def test_nested_records_roundtrip_in_actions_plans_and_diagnoses() -> None:
    action = _action()
    assert TeachingAction.from_dict(action.to_dict()) == action
    assert action.reason is not None
    assert action.reason.code == "POLICY.PREREQ_GAP"

    plan = _plan()
    restored_plan = CurriculumPlan.from_dict(plan.to_dict())
    assert restored_plan == plan
    assert restored_plan.steps[0].rationale.policy_version == "policy.v0"

    diagnosis = _diagnosis()
    assert DiagnosisResult.from_dict(diagnosis.to_dict()) == diagnosis

    # Unknown fields inside nested records are also rejected.
    payload = action.to_dict()
    payload["reason"]["unexpected"] = True
    with pytest.raises(ValidationError, match="unknown field"):
        TeachingAction.from_dict(payload)


# ---------------------------------------------------------------------------
# Defaults / optionality / value semantics
# ---------------------------------------------------------------------------


def test_documented_defaults() -> None:
    item = AssessmentItem(
        item_id="item.defaults",
        domain_id="cf_binary_search",
        node_ids=["cf.search.binary"],
        item_type="SHORT_ANSWER",
        difficulty=1,
        prompt="解释单调性",
    )
    assert item.options == []
    assert item.function_name is None
    assert item.max_score == 1.0
    assert item.deterministic is True
    assert item.scoring_spec_ref == ""

    assert _node().content_ref == ""
    assert _goal().status == "ACTIVE"
    default_session = SessionState(
        session_id="session.defaults",
        learner_id="learner.a",
        goal_id="goal.0001",
        objective_id="obj.cf.binary_search.mastery",
    )
    assert default_session.phase == "PAUSED"
    assert default_session.turn_index == 0
    assert default_session.pending_item_id is None
    assert _objective().estimated_minutes == 120
    assert _result().score == 1.0
    default_reason = Reason(code="POLICY.TEST")
    assert default_reason.node_ids == []
    assert default_reason.detail == ""
    assert default_reason.policy_version == ""


def test_mutable_defaults_are_per_instance() -> None:
    node_a = _node()
    node_b = _node()
    node_a.tags.append("mutated")
    assert "mutated" not in node_b.tags
    reason_a = _reason()
    reason_b = _reason()
    reason_a.node_ids.append("cf.search.boundary")
    assert "cf.search.boundary" not in reason_b.node_ids


def test_optional_fields_accept_none() -> None:
    assert _session().pending_item_id is None
    assert replace(_action(), reason=None).reason is None
    assert replace(_diagnosis(), reason=None).reason is None
    assert replace(_diagnosis(), selected_item_id=None).selected_item_id is None
    assert replace(_item(), function_name=None).function_name is None


# ---------------------------------------------------------------------------
# Error hierarchy
# ---------------------------------------------------------------------------


def test_error_hierarchy_and_stable_codes() -> None:
    assert issubclass(ValidationError, M1AError)
    assert issubclass(NotFoundError, M1AError)
    assert issubclass(ConflictError, M1AError)
    assert issubclass(UnsupportedOperationError, M1AError)
    assert M1AError.code == "M1A_ERROR"
    assert ValidationError.code == "VALIDATION_ERROR"
    assert NotFoundError.code == "NOT_FOUND"
    assert ConflictError.code == "CONFLICT"
    assert UnsupportedOperationError.code == "UNSUPPORTED_OPERATION"
    assert ValidationError("bad input").code == "VALIDATION_ERROR"
    assert ValidationError("bad input", details={"field": "difficulty"}).details == {
        "field": "difficulty"
    }
    custom = M1AError("custom", code="CUSTOM_CODE")
    assert custom.code == "CUSTOM_CODE"
    assert custom.to_dict() == {
        "code": "CUSTOM_CODE",
        "message": "custom",
        "details": {},
    }
    with pytest.raises(M1AError):
        raise ValidationError("wrapped")
