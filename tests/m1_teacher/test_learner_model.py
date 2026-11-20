"""Tests for the deterministic evidence-driven mastery model (B-PR2).

Every assertion is a real, reproducible numeric/behavioural check of the
documented update formulas.  No randomness, no clock, no network: result
timestamps are fixed constants and the model must be a pure function of
``(policy, snapshot, item, result)``.
"""

from __future__ import annotations

import json

import pytest

from m1_teacher.contracts.errors import ValidationError
from m1_teacher.contracts.types import (
    AssessmentItem,
    AssessmentResult,
    HistoryEvent,
    LearnerSnapshot,
)
from m1_teacher.learner.model import (
    EPOCH_TIMESTAMP,
    OBSERVED_EVIDENCE,
    MasteryModel,
    MasteryPolicy,
    applied_result_ids,
)

TS = "2026-11-20T12:00:00Z"
TS_LATER = "2026-11-20T12:05:00Z"
LEARNER = "learner.a"
ITEM_ID = "item.bs.mcq.004"
BINARY_NODE = "cf.search.binary"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_item(
    item_id: str = ITEM_ID,
    node_ids: tuple[str, ...] = (BINARY_NODE,),
    max_score: float = 1.0,
    created_at: str = TS,
) -> AssessmentItem:
    return AssessmentItem(
        item_id=item_id,
        domain_id="cf_binary_search",
        node_ids=list(node_ids),
        item_type="MCQ",
        difficulty=3,
        prompt="二分查找中 mid 的取值与边界是什么？",
        options=["选项 A", "选项 B", "选项 C", "选项 D"],
        max_score=max_score,
        created_at=created_at,
    )


def make_result(
    result_id: str = "result.1",
    item_id: str = ITEM_ID,
    learner_id: str = LEARNER,
    status: str = "CORRECT",
    score: float | None = None,
    max_score: float = 1.0,
    failure_reason: str = "",
    created_at: str = TS,
) -> AssessmentResult:
    return AssessmentResult(
        result_id=result_id,
        item_id=item_id,
        learner_id=learner_id,
        status=status,
        score=score,
        max_score=max_score,
        scorer_id="scorer.deterministic.v0",
        failure_reason=failure_reason,
        created_at=created_at,
    )


def make_assessed_event(
    seq: int,
    item: AssessmentItem,
    result: AssessmentResult,
    *,
    event_id: str | None = None,
    learner_id: str = LEARNER,
    embed_item: bool = True,
) -> HistoryEvent:
    payload: dict = {"result_id": result.result_id, "result": result.to_dict()}
    if embed_item:
        payload["item"] = item.to_dict()
    return HistoryEvent(
        event_id=event_id or f"evt.assessed.{result.result_id}",
        learner_id=learner_id,
        session_id="session.1",
        seq=seq,
        event_type="ASSESSED",
        payload=payload,
        created_at=result.created_at,
    )


def node_mastery(snapshot: LearnerSnapshot, node_id: str = BINARY_NODE):
    return snapshot.masteries[node_id]


def apply_sequence(model: MasteryModel, pairs: list[tuple[AssessmentItem, AssessmentResult]]):
    snapshot = model.initial_snapshot(LEARNER)
    for item, result in pairs:
        snapshot = model.apply_result(snapshot, item, result)
    return snapshot


# ---------------------------------------------------------------------------
# Policy constants and validation
# ---------------------------------------------------------------------------


def test_default_policy_constants_are_frozen():
    policy = MasteryPolicy()
    assert policy.initial_value == 0.0
    assert policy.correct_step == 0.2
    assert policy.incorrect_step == 0.2
    assert policy.partial_step == 0.1
    assert policy.partial_credit_threshold == 0.5
    assert policy.correct_confidence_gain == 0.5
    assert policy.incorrect_confidence_gain == 0.25
    assert policy.partial_confidence_gain == 0.25
    assert policy.max_value == 1.0
    assert policy.policy_version == "m1a.learner.mastery.heuristic.v0"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"initial_value": 1.5},
        {"max_value": 1.5},
        {"max_value": 0.0},
        {"correct_step": -0.1},
        {"partial_credit_threshold": 1.2},
        {"correct_confidence_gain": 0.0},
        {"incorrect_confidence_gain": 1.5},
        {"policy_version": "  "},
    ],
)
def test_invalid_policies_fail_closed(kwargs):
    with pytest.raises(ValidationError):
        MasteryPolicy(**kwargs)


def test_mastery_model_requires_mastery_policy_instance():
    with pytest.raises(ValidationError):
        MasteryModel(policy={"correct_step": 0.2})  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Initial state: unknown is not mastered
# ---------------------------------------------------------------------------


def test_initial_snapshot_is_canonical_and_empty():
    model = MasteryModel()
    snapshot = model.initial_snapshot(LEARNER)
    assert snapshot.learner_id == LEARNER
    assert snapshot.masteries == {}
    assert snapshot.completed_item_ids == []
    assert snapshot.error_counts == {}
    assert snapshot.revision == 0
    assert snapshot.created_at == EPOCH_TIMESTAMP
    assert snapshot.updated_at == EPOCH_TIMESTAMP
    # Deterministic: repeated calls produce identical wire payloads.
    assert model.initial_snapshot(LEARNER).to_dict() == snapshot.to_dict()


def test_initial_snapshot_rejects_blank_learner_id():
    with pytest.raises(ValidationError):
        MasteryModel().initial_snapshot("")


def test_no_evidence_means_no_mastery_entries():
    model = MasteryModel()
    snapshot = model.initial_snapshot(LEARNER)
    item = make_item()
    updated = model.apply_result(snapshot, item, make_result("r1", status="CORRECT"))
    assert set(updated.masteries) == {BINARY_NODE}
    # Unobserved nodes never appear (unknown is not treated as mastered).
    assert "cf.sort.sortedness" not in updated.masteries
    assert "cf.search.boundary" not in updated.masteries


# ---------------------------------------------------------------------------
# CORRECT: exact numeric rise
# ---------------------------------------------------------------------------


def test_correct_raises_mastery_confidence_and_evidence_count():
    model = MasteryModel()
    item = make_item()
    updated = model.apply_result(
        model.initial_snapshot(LEARNER), item, make_result("r1", status="CORRECT")
    )
    mastery = node_mastery(updated)
    # decay = 1 / (1 + 0) = 1 -> 0.0 + 0.2
    assert mastery.value == pytest.approx(0.2)
    # confidence = 0 + (1 - 0) * 0.5
    assert mastery.confidence == pytest.approx(0.5)
    assert mastery.evidence_count == 1
    assert mastery.node_id == BINARY_NODE
    assert updated.revision == 1
    assert updated.completed_item_ids == [ITEM_ID]
    assert updated.error_counts == {}
    assert updated.created_at == TS
    assert updated.updated_at == TS
    assert mastery.created_at == TS
    assert mastery.updated_at == TS


def test_correct_step_decays_with_evidence_count():
    model = MasteryModel()
    item = make_item()
    snapshot = apply_sequence(
        model,
        [
            (item, make_result("r1", status="CORRECT")),
            (item, make_result("r2", status="CORRECT")),
            (item, make_result("r3", status="CORRECT")),
        ],
    )
    mastery = node_mastery(snapshot)
    # 0.2 (e=0) + 0.2/2 (e=1) + 0.2/3 (e=2)
    assert mastery.value == pytest.approx(0.2 + 0.1 + 0.2 / 3)
    # 0.5, 0.75, 0.875
    assert mastery.confidence == pytest.approx(0.875)
    assert mastery.evidence_count == 3
    assert snapshot.revision == 3


def test_correct_mastery_is_bounded_by_max_value():
    model = MasteryModel()
    item = make_item()
    snapshot = model.initial_snapshot(LEARNER)
    for index in range(100):
        snapshot = model.apply_result(snapshot, item, make_result(f"r{index}", status="CORRECT"))
    mastery = node_mastery(snapshot)
    assert mastery.value == pytest.approx(1.0)
    assert mastery.confidence <= 1.0
    assert mastery.evidence_count == 100


def test_mastery_timestamps_follow_evidence_timestamps():
    model = MasteryModel()
    item = make_item()
    snapshot = model.apply_result(
        model.initial_snapshot(LEARNER), item, make_result("r1", created_at=TS)
    )
    snapshot = model.apply_result(snapshot, item, make_result("r2", created_at=TS_LATER))
    mastery = node_mastery(snapshot)
    assert mastery.created_at == TS
    assert mastery.updated_at == TS_LATER
    assert snapshot.created_at == TS
    assert snapshot.updated_at == TS_LATER


# ---------------------------------------------------------------------------
# INCORRECT: never raises mastery, counts an error
# ---------------------------------------------------------------------------


def test_incorrect_never_raises_mastery_from_zero():
    model = MasteryModel()
    updated = model.apply_result(
        model.initial_snapshot(LEARNER),
        make_item(),
        make_result("r1", status="INCORRECT"),
    )
    mastery = node_mastery(updated)
    assert mastery.value == pytest.approx(0.0)
    assert mastery.confidence == pytest.approx(0.25)
    assert mastery.evidence_count == 1
    assert updated.error_counts == {ITEM_ID: 1}
    assert updated.completed_item_ids == [ITEM_ID]


def test_incorrect_lowers_mastery_but_never_raises_it():
    model = MasteryModel()
    item = make_item()
    snapshot = apply_sequence(
        model,
        [
            (item, make_result("r1", status="CORRECT")),
            (item, make_result("r2", status="CORRECT")),
            (item, make_result("r3", status="CORRECT")),
        ],
    )
    before = node_mastery(snapshot).value
    updated = model.apply_result(
        snapshot, item, make_result("r4", status="INCORRECT", failure_reason="off_by_one")
    )
    mastery = node_mastery(updated)
    # evidence_count was 3 -> decay 1/4; 0.3666... - 0.05
    assert mastery.value == pytest.approx(before - 0.2 / 4)
    assert mastery.value < before
    assert mastery.confidence == pytest.approx(0.875 + (1 - 0.875) * 0.25)
    assert mastery.evidence_count == 4
    # Failure reason (an error code supplied by the scorer) keys the counter.
    assert updated.error_counts == {"off_by_one": 1}
    assert updated.revision == 4


def test_incorrect_error_counts_fall_back_to_item_id():
    model = MasteryModel()
    updated = model.apply_result(
        model.initial_snapshot(LEARNER),
        make_item(item_id="item.bs.code.003"),
        make_result(
            "r1", item_id="item.bs.code.003", status="INCORRECT", failure_reason="   "
        ),
    )
    assert updated.error_counts == {"item.bs.code.003": 1}


# ---------------------------------------------------------------------------
# PARTIAL: threshold-guarded small rise
# ---------------------------------------------------------------------------


def test_partial_above_threshold_rises_slightly():
    model = MasteryModel()
    updated = model.apply_result(
        model.initial_snapshot(LEARNER),
        make_item(),
        make_result("r1", status="PARTIAL", score=1.0),
    )
    mastery = node_mastery(updated)
    assert mastery.value == pytest.approx(0.1)
    assert mastery.confidence == pytest.approx(0.25)
    assert mastery.evidence_count == 1


def test_partial_at_threshold_rises():
    model = MasteryModel()
    updated = model.apply_result(
        model.initial_snapshot(LEARNER),
        make_item(),
        make_result("r1", status="PARTIAL", score=0.5),
    )
    assert node_mastery(updated).value == pytest.approx(0.1)


def test_partial_below_threshold_does_not_rise():
    model = MasteryModel()
    updated = model.apply_result(
        model.initial_snapshot(LEARNER),
        make_item(),
        make_result("r1", status="PARTIAL", score=0.25),
    )
    mastery = node_mastery(updated)
    assert mastery.value == pytest.approx(0.0)  # no rise, no drop
    assert mastery.confidence == pytest.approx(0.25)  # evidence still counted
    assert mastery.evidence_count == 1
    assert updated.error_counts == {}  # PARTIAL is not an INCORRECT error
    assert updated.completed_item_ids == [ITEM_ID]


def test_partial_without_score_does_not_rise():
    model = MasteryModel()
    updated = model.apply_result(
        model.initial_snapshot(LEARNER),
        make_item(),
        make_result("r1", status="PARTIAL", score=None),
    )
    assert node_mastery(updated).value == pytest.approx(0.0)
    assert node_mastery(updated).evidence_count == 1


def test_partial_rise_is_smaller_than_correct_rise():
    model = MasteryModel()
    item = make_item()
    correct = model.apply_result(
        model.initial_snapshot(LEARNER), item, make_result("r1", status="CORRECT")
    )
    partial = model.apply_result(
        model.initial_snapshot(LEARNER),
        item,
        make_result("r2", status="PARTIAL", score=1.0),
    )
    assert node_mastery(partial).value < node_mastery(correct).value


# ---------------------------------------------------------------------------
# NEEDS_REVIEW / EVAL_ERROR: zero state change
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", ["NEEDS_REVIEW", "EVAL_ERROR"])
def test_non_evidence_statuses_change_nothing(status):
    model = MasteryModel()
    item = make_item()
    snapshot = apply_sequence(
        model,
        [
            (item, make_result("r1", status="CORRECT")),
            (item, make_result("r2", status="INCORRECT", failure_reason="off_by_one")),
        ],
    )
    before = snapshot.to_dict()
    updated = model.apply_result(
        snapshot, item, make_result("r3", status=status, failure_reason="judge crashed")
    )
    assert updated.to_dict() == before
    assert updated is snapshot  # documented: the snapshot is returned untouched
    assert updated.revision == 2
    assert updated.error_counts == {"off_by_one": 1}
    assert node_mastery(updated).evidence_count == 2


def test_eval_error_is_never_counted_as_learner_error():
    model = MasteryModel()
    snapshot = model.initial_snapshot(LEARNER)
    for index in range(3):
        snapshot = model.apply_result(
            snapshot, make_item(), make_result(f"r{index}", status="EVAL_ERROR")
        )
    assert snapshot.to_dict() == model.initial_snapshot(LEARNER).to_dict()
    assert snapshot.error_counts == {}
    assert snapshot.completed_item_ids == []
    assert snapshot.masteries == {}


# ---------------------------------------------------------------------------
# Fail-closed evidence validation
# ---------------------------------------------------------------------------


def test_only_observed_evidence_is_accepted():
    model = MasteryModel()
    snapshot = model.initial_snapshot(LEARNER)
    item = make_item()
    result = make_result("r1", status="CORRECT")
    with pytest.raises(ValidationError):
        model.apply_result(snapshot, item, result, evidence_source="INFERRED")
    with pytest.raises(ValidationError):
        model.apply_result(snapshot, item, result, evidence_source="BOGUS")
    # The documented default is OBSERVED and works.
    accepted = model.apply_result(snapshot, item, result, evidence_source=OBSERVED_EVIDENCE)
    assert accepted.revision == 1


def test_mismatched_item_and_learner_fail_closed():
    model = MasteryModel()
    snapshot = model.initial_snapshot(LEARNER)
    item = make_item(item_id="item.bs.mcq.004")
    with pytest.raises(ValidationError):
        model.apply_result(
            snapshot,
            item,
            make_result("r1", item_id="item.bs.mcq.005", status="CORRECT"),
        )
    with pytest.raises(ValidationError):
        model.apply_result(
            snapshot,
            item,
            make_result("r1", learner_id="learner.b", status="CORRECT"),
        )


def test_wrong_argument_types_fail_closed():
    model = MasteryModel()
    snapshot = model.initial_snapshot(LEARNER)
    item = make_item()
    result = make_result("r1", status="CORRECT")
    with pytest.raises(ValidationError):
        model.apply_result({"learner_id": LEARNER}, item, result)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        model.apply_result(snapshot, "item", result)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        model.apply_result(snapshot, item, "result")  # type: ignore[arg-type]
    mutated_item = make_item()
    mutated_item.node_ids = []
    with pytest.raises(ValidationError):
        model.apply_result(snapshot, mutated_item, result)


def test_item_with_multiple_nodes_updates_all_observed_nodes():
    model = MasteryModel()
    item = make_item(node_ids=("cf.search.binary", "cf.search.boundary"))
    updated = model.apply_result(
        model.initial_snapshot(LEARNER), item, make_result("r1", status="CORRECT")
    )
    assert set(updated.masteries) == {"cf.search.binary", "cf.search.boundary"}
    for mastery in updated.masteries.values():
        assert mastery.value == pytest.approx(0.2)
        assert mastery.evidence_count == 1


# ---------------------------------------------------------------------------
# Idempotency by result_id
# ---------------------------------------------------------------------------


def test_duplicate_result_id_is_ignored_when_declared_applied():
    model = MasteryModel()
    item = make_item()
    result = make_result("r1", status="CORRECT")
    snapshot = model.apply_result(model.initial_snapshot(LEARNER), item, result)
    again = model.apply_result(
        snapshot, item, result, applied_result_ids=[result.result_id]
    )
    assert again is snapshot
    assert node_mastery(again).value == pytest.approx(0.2)
    assert node_mastery(again).evidence_count == 1
    assert again.revision == 1


def test_apply_results_batch_deduplicates_result_ids():
    model = MasteryModel()
    item = make_item()
    r1 = make_result("r1", status="CORRECT")
    r2 = make_result("r2", status="CORRECT")
    batched = model.apply_results(model.initial_snapshot(LEARNER), [(item, r1), (item, r1), (item, r2)])
    sequential = apply_sequence(model, [(item, r1), (item, r2)])
    assert batched.to_dict() == sequential.to_dict()
    assert node_mastery(batched).evidence_count == 2
    assert batched.revision == 2


def test_apply_results_honours_cross_batch_applied_ids():
    model = MasteryModel()
    item = make_item()
    r1 = make_result("r1", status="CORRECT")
    r2 = make_result("r2", status="CORRECT")
    snapshot = model.apply_result(model.initial_snapshot(LEARNER), item, r1)
    extended = model.apply_results(
        snapshot, [(item, r1), (item, r2)], applied_result_ids={r1.result_id}
    )
    expected = model.apply_result(snapshot, item, r2)
    assert extended.to_dict() == expected.to_dict()


def test_apply_results_rejects_malformed_batches():
    model = MasteryModel()
    snapshot = model.initial_snapshot(LEARNER)
    item = make_item()
    result = make_result("r1", status="CORRECT")
    with pytest.raises(ValidationError):
        model.apply_results(snapshot, "not-a-batch")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        model.apply_results(snapshot, [(item,)])  # type: ignore[list-item]
    with pytest.raises(ValidationError):
        model.apply_results(snapshot, [(item, result)], applied_result_ids=[" "])
    with pytest.raises(ValidationError):
        model.apply_results(snapshot, [(item, result)], evidence_source="INFERRED")


# ---------------------------------------------------------------------------
# Custom policy injection (still deterministic)
# ---------------------------------------------------------------------------


def test_injected_policy_changes_updates_deterministically():
    policy = MasteryPolicy(
        initial_value=0.5,
        correct_step=0.4,
        partial_credit_threshold=0.8,
        correct_confidence_gain=1.0,
    )
    model = MasteryModel(policy)
    item = make_item()
    first = model.apply_result(
        model.initial_snapshot(LEARNER), item, make_result("r1", status="CORRECT")
    )
    mastery = node_mastery(first)
    assert mastery.value == pytest.approx(0.9)
    assert mastery.confidence == pytest.approx(1.0)

    # 0.7 / 1.0 is below the injected 0.8 threshold: no rise.
    below = model.apply_result(
        model.initial_snapshot(LEARNER),
        item,
        make_result("r2", status="PARTIAL", score=0.7),
    )
    assert node_mastery(below).value == pytest.approx(0.5)
    # 0.8 / 1.0 meets the threshold: +0.1.
    at = model.apply_result(
        model.initial_snapshot(LEARNER),
        item,
        make_result("r3", status="PARTIAL", score=0.8),
    )
    assert node_mastery(at).value == pytest.approx(0.6)

    # Determinism: identical model+input produce identical output.
    repeat = MasteryModel(policy).apply_result(
        MasteryModel(policy).initial_snapshot(LEARNER),
        item,
        make_result("r1", status="CORRECT"),
    )
    assert repeat.to_dict() == first.to_dict()


def test_default_model_is_deterministic():
    model = MasteryModel()
    item = make_item()
    results = [
        make_result("r1", status="CORRECT"),
        make_result("r2", status="INCORRECT", failure_reason="off_by_one"),
        make_result("r3", status="PARTIAL", score=0.5),
        make_result("r4", status="NEEDS_REVIEW"),
    ]
    first = apply_sequence(model, [(item, result) for result in results])
    second = apply_sequence(MasteryModel(), [(item, result) for result in results])
    assert first.to_dict() == second.to_dict()
    assert json.dumps(first.to_dict(), sort_keys=True) == json.dumps(
        second.to_dict(), sort_keys=True
    )


# ---------------------------------------------------------------------------
# applied_result_ids helper
# ---------------------------------------------------------------------------


def test_applied_result_ids_from_events():
    item = make_item()
    events = [
        make_assessed_event(0, item, make_result("r1", status="CORRECT")),
        HistoryEvent(
            event_id="evt.session",
            learner_id=LEARNER,
            session_id="session.1",
            seq=1,
            event_type="SESSION_STARTED",
            payload={},
            created_at=TS,
        ),
        make_assessed_event(2, item, make_result("r2", status="INCORRECT")),
    ]
    assert applied_result_ids(events) == {"r1", "r2"}
    assert applied_result_ids([]) == set()


def test_applied_result_ids_rejects_malformed_events():
    with pytest.raises(ValidationError):
        applied_result_ids(["not-an-event"])  # type: ignore[list-item]
    with pytest.raises(ValidationError):
        applied_result_ids(
            [
                HistoryEvent(
                    event_id="evt.assessed.bad",
                    learner_id=LEARNER,
                    session_id="session.1",
                    seq=0,
                    event_type="ASSESSED",
                    payload={"result_id": 42},
                    created_at=TS,
                )
            ]
        )


# ---------------------------------------------------------------------------
# Rebuild from events must equal incremental application
# ---------------------------------------------------------------------------


def _incremental_and_events():
    model = MasteryModel()
    item = make_item()
    other_item = make_item(
        item_id="item.bs.code.003", node_ids=("cf.search.boundary",)
    )
    pairs = [
        (item, make_result("r1", status="CORRECT", created_at=TS)),
        (other_item, make_result("r2", item_id=other_item.item_id, status="INCORRECT", failure_reason="off_by_one", created_at=TS)),
        (item, make_result("r3", status="CORRECT", created_at=TS_LATER)),
        (
            item,
            make_result("r4", status="PARTIAL", score=0.5, created_at=TS_LATER),
        ),
        (item, make_result("r5", status="NEEDS_REVIEW", created_at=TS_LATER)),
    ]
    incremental = apply_sequence(model, pairs)
    events = [
        make_assessed_event(index, pair_item, pair_result)
        for index, (pair_item, pair_result) in enumerate(pairs)
    ]
    items_by_id = {item.item_id: item, other_item.item_id: other_item}
    return model, incremental, events, items_by_id, item, other_item


def test_rebuild_equals_incremental_application():
    model, incremental, events, items_by_id, _, _ = _incremental_and_events()
    rebuilt = model.rebuild_snapshot(LEARNER, events, items_by_id)
    assert rebuilt.to_dict() == incremental.to_dict()
    assert rebuilt.revision == 4  # r1..r4 mutate; NEEDS_REVIEW does not bump revision
    assert rebuilt.error_counts == {"off_by_one": 1}


def test_rebuild_is_independent_of_input_event_order():
    model, incremental, events, items_by_id, _, _ = _incremental_and_events()
    shuffled = [events[2], events[0], events[4], events[3], events[1]]
    rebuilt = model.rebuild_snapshot(LEARNER, shuffled, items_by_id)
    assert rebuilt.to_dict() == incremental.to_dict()


def test_rebuild_deduplicates_assessed_result_ids():
    model, incremental, events, items_by_id, item, _ = _incremental_and_events()
    duplicate = make_assessed_event(
        100, item, make_result("r1", status="CORRECT", created_at=TS), event_id="evt.dup"
    )
    rebuilt = model.rebuild_snapshot(LEARNER, events + [duplicate], items_by_id)
    assert rebuilt.to_dict() == incremental.to_dict()


def test_rebuild_ignores_non_assessment_events():
    model, incremental, events, items_by_id, _, _ = _incremental_and_events()
    noise = HistoryEvent(
        event_id="evt.session",
        learner_id=LEARNER,
        session_id="session.1",
        seq=100,
        event_type="SESSION_STARTED",
        payload={"phase": "DIAGNOSE"},
        created_at=TS_LATER,
    )
    rebuilt = model.rebuild_snapshot(LEARNER, [noise, *events], items_by_id)
    assert rebuilt.to_dict() == incremental.to_dict()


def test_rebuild_empty_history_is_canonical_empty_snapshot():
    model = MasteryModel()
    rebuilt = model.rebuild_snapshot(LEARNER, [], {})
    assert rebuilt.to_dict() == model.initial_snapshot(LEARNER).to_dict()


def test_rebuild_falls_back_to_items_by_id():
    model = MasteryModel()
    item = make_item()
    result = make_result("r1", status="CORRECT")
    event = make_assessed_event(0, item, result, embed_item=False)
    rebuilt = model.rebuild_snapshot(LEARNER, [event], {item.item_id: item})
    incremental = model.apply_result(model.initial_snapshot(LEARNER), item, result)
    assert rebuilt.to_dict() == incremental.to_dict()
    with pytest.raises(ValidationError):
        model.rebuild_snapshot(LEARNER, [event], {})


def test_rebuild_rejects_inconsistent_inputs():
    model = MasteryModel()
    item = make_item()
    result = make_result("r1", status="CORRECT")
    good = make_assessed_event(0, item, result)
    items_by_id = {item.item_id: item}
    with pytest.raises(ValidationError):
        model.rebuild_snapshot("", [good], items_by_id)
    with pytest.raises(ValidationError):
        model.rebuild_snapshot(LEARNER, "events", items_by_id)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        model.rebuild_snapshot(LEARNER, [good], "items")  # type: ignore[arg-type]
    # Event belongs to another learner.
    with pytest.raises(ValidationError):
        model.rebuild_snapshot(
            "learner.b", [make_assessed_event(0, item, result, learner_id="learner.a")], items_by_id
        )
    # Duplicate seq.
    with pytest.raises(ValidationError):
        model.rebuild_snapshot(
            LEARNER,
            [good, make_assessed_event(0, item, make_result("r2"), event_id="evt.other")],
            items_by_id,
        )
    # Not a HistoryEvent.
    with pytest.raises(ValidationError):
        model.rebuild_snapshot(LEARNER, ["nope"], items_by_id)  # type: ignore[list-item]
    # Payload without the nested result.
    with pytest.raises(ValidationError):
        model.rebuild_snapshot(
            LEARNER,
            [
                HistoryEvent(
                    event_id="evt.assessed.bad",
                    learner_id=LEARNER,
                    session_id="session.1",
                    seq=0,
                    event_type="ASSESSED",
                    payload={"item": item.to_dict()},
                    created_at=TS,
                )
            ],
            items_by_id,
        )


def test_rebuild_output_contains_no_unobserved_nodes():
    model, _, events, items_by_id, _, _ = _incremental_and_events()
    rebuilt = model.rebuild_snapshot(LEARNER, events, items_by_id)
    assert set(rebuilt.masteries) == {"cf.search.binary", "cf.search.boundary"}
