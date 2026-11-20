"""Tests for the append-only learning-history service (B-PR2).

The service is exercised against two repositories:

* :class:`FakeRepository` below — implements only the frozen
  ``LearnerRepository`` protocol (no atomic extensions) so the documented
  non-atomic fallback path is covered;
* :class:`m1_teacher.learner.repository.SqliteRepository` — the real B-PR2
  persistence layer, proving the atomic event+snapshot commit path and restart
  recovery.

The last section loads the synthetic ``student_a`` / ``student_b`` fixtures and
drives the history with their ``response_script`` — the same deterministic mock
learner responses PR5 consumes (no network, no real data, no hidden answers).
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import pytest

from m1_teacher.contracts.errors import ConflictError, ValidationError
from m1_teacher.contracts.types import (
    AssessmentItem,
    AssessmentResult,
    HistoryEvent,
    LearnerGoal,
    LearnerSnapshot,
)
from m1_teacher.domains.cf_binary_search import CFBinarySearchDomainAdapter
from m1_teacher.learner.history import LearningHistory
from m1_teacher.learner.model import MasteryModel
from m1_teacher.learner.repository import SqliteRepository

TS = "2026-11-20T12:00:00Z"
TS_LATER = "2026-11-20T12:05:00Z"
LEARNER = "learner.a"
SESSION = "session.1"
ITEM_ID = "item.bs.mcq.004"
BINARY_NODE = "cf.search.binary"
BOUNDARY_NODE = "cf.search.boundary"
SORTEDNESS_NODE = "cf.sort.sortedness"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _copy_event(event: HistoryEvent) -> HistoryEvent:
    return HistoryEvent.from_json(event.to_json())


def _copy_snapshot(snapshot: LearnerSnapshot) -> LearnerSnapshot:
    return LearnerSnapshot.from_json(snapshot.to_json())


def make_item(
    item_id: str = ITEM_ID,
    node_ids: tuple[str, ...] = (BINARY_NODE,),
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
        created_at=created_at,
    )


def make_result(
    result_id: str = "result.1",
    item_id: str = ITEM_ID,
    learner_id: str = LEARNER,
    status: str = "CORRECT",
    score: float | None = None,
    failure_reason: str = "",
    created_at: str = TS,
) -> AssessmentResult:
    return AssessmentResult(
        result_id=result_id,
        item_id=item_id,
        learner_id=learner_id,
        status=status,
        score=score,
        max_score=1.0,
        scorer_id="scorer.deterministic.v0",
        failure_reason=failure_reason,
        created_at=created_at,
    )


def make_event(
    event_id: str,
    seq: int,
    event_type: str = "SESSION_STARTED",
    payload: dict | None = None,
    learner_id: str = LEARNER,
    created_at: str = TS,
) -> HistoryEvent:
    return HistoryEvent(
        event_id=event_id,
        learner_id=learner_id,
        session_id=SESSION,
        seq=seq,
        event_type=event_type,
        payload=payload or {},
        created_at=created_at,
    )


class FakeRepository:
    """Minimal in-memory ``LearnerRepository`` (frozen protocol only).

    It deliberately has **no** ``append_events_and_upsert_snapshot`` /
    ``append_events`` extension, so ``LearningHistory`` exercises its
    documented non-atomic fallback path.  Stored records are copied so a test
    can prove the history is append-only and never hands out live state.
    """

    def __init__(self) -> None:
        self.snapshots: dict[str, LearnerSnapshot] = {}
        self.events: dict[str, HistoryEvent] = {}
        self.events_by_learner: dict[str, list[HistoryEvent]] = defaultdict(list)
        self.goals: dict[str, LearnerGoal] = {}

    def get_snapshot(self, learner_id: str) -> LearnerSnapshot | None:
        snapshot = self.snapshots.get(learner_id)
        return _copy_snapshot(snapshot) if snapshot is not None else None

    def upsert_snapshot(self, snapshot: LearnerSnapshot) -> None:
        existing = self.snapshots.get(snapshot.learner_id)
        if existing is not None and existing.revision > snapshot.revision:
            raise ConflictError("stale snapshot revision")
        self.snapshots[snapshot.learner_id] = _copy_snapshot(snapshot)

    def append_event(self, event: HistoryEvent) -> bool:
        if event.event_id in self.events:
            return False
        for existing in self.events_by_learner.get(event.learner_id, []):
            if existing.seq == event.seq:
                raise ConflictError(f"seq {event.seq} already used")
        stored = _copy_event(event)
        self.events[event.event_id] = stored
        self.events_by_learner[event.learner_id].append(stored)
        return True

    def get_event(self, event_id: str) -> HistoryEvent | None:
        event = self.events.get(event_id)
        return _copy_event(event) if event is not None else None

    def list_events(self, learner_id: str, since_seq: int | None = None) -> list[HistoryEvent]:
        events = sorted(self.events_by_learner.get(learner_id, []), key=lambda e: e.seq)
        if since_seq is not None:
            events = [event for event in events if event.seq >= since_seq]
        return [_copy_event(event) for event in events]

    def get_goal(self, goal_id: str) -> LearnerGoal | None:
        goal = self.goals.get(goal_id)
        return LearnerGoal.from_json(goal.to_json()) if goal is not None else None

    def upsert_goal(self, goal: LearnerGoal) -> None:
        self.goals[goal.goal_id] = LearnerGoal.from_json(goal.to_json())


def _history(repository: FakeRepository | SqliteRepository | None = None) -> LearningHistory:
    return LearningHistory(repository if repository is not None else FakeRepository())


# ---------------------------------------------------------------------------
# append_event: per-learner seq allocation and payloads
# ---------------------------------------------------------------------------


def test_append_event_allocates_consecutive_per_learner_sequences():
    repository = FakeRepository()
    history = _history(repository)
    first = history.append_event(LEARNER, SESSION, "SESSION_STARTED", {"phase": "DIAGNOSE"})
    second = history.append_event(LEARNER, SESSION, "ACTION_TAKEN", {"kind": "EXPLAIN"})
    third = history.append_event(LEARNER, SESSION, "ITEM_PRESENTED", {"item_id": ITEM_ID})
    assert [first.seq, second.seq, third.seq] == [0, 1, 2]
    assert first.event_id == f"evt.{LEARNER}.0"
    assert second.event_id == f"evt.{LEARNER}.1"
    assert [event.event_type for event in repository.list_events(LEARNER)] == [
        "SESSION_STARTED",
        "ACTION_TAKEN",
        "ITEM_PRESENTED",
    ]
    # A second learner gets an independent sequence.
    other = history.append_event("learner.b", "session.2", "SESSION_STARTED", {})
    assert other.seq == 0


def test_append_event_validates_inputs():
    history = _history()
    with pytest.raises(ValidationError):
        history.append_event("", SESSION, "SESSION_STARTED", {})
    with pytest.raises(ValidationError):
        history.append_event(LEARNER, "   ", "SESSION_STARTED", {})
    with pytest.raises(ValidationError):
        history.append_event(LEARNER, SESSION, "NOT_AN_EVENT", {})
    with pytest.raises(ValidationError):
        history.append_event(LEARNER, SESSION, "SESSION_STARTED", ["not", "a", "dict"])  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        history.append_event(LEARNER, SESSION, "SESSION_STARTED", {"bad": object()})


def test_append_event_surfaces_event_id_collision_as_conflict():
    class RacingRepository(FakeRepository):
        """A concurrent writer that fills the deterministic id first."""

        def append_event(self, event: HistoryEvent) -> bool:
            return False

    history = _history(RacingRepository())
    with pytest.raises(ConflictError):
        history.append_event(LEARNER, SESSION, "SESSION_STARTED", {})


# ---------------------------------------------------------------------------
# record_event: idempotency and append-only semantics
# ---------------------------------------------------------------------------


def test_record_event_is_idempotent_by_event_id():
    repository = FakeRepository()
    history = _history(repository)
    event = make_event("evt.session.started", 0, payload={"phase": "DIAGNOSE"})
    assert history.record_event(event) is True
    stored_before = repository.get_event(event.event_id)
    assert stored_before is not None
    before = stored_before.to_dict()
    assert history.record_event(event) is False
    assert len(repository.list_events(LEARNER)) == 1
    stored_after = repository.get_event(event.event_id)
    assert stored_after is not None
    assert stored_after.to_dict() == before


def test_record_event_rejects_non_events():
    history = _history()
    with pytest.raises(ValidationError):
        history.record_event({"event_id": "fake"})  # type: ignore[arg-type]


def test_history_is_append_only():
    history = _history()
    for name in ("delete_event", "update_event", "remove_event", "rewrite_event"):
        assert not hasattr(history, name)
    repository = history.repository
    for name in ("delete_event", "update_event", "remove_event"):
        assert not hasattr(repository, name)


def test_returned_events_are_copies():
    repository = FakeRepository()
    history = _history(repository)
    event = history.append_event(LEARNER, SESSION, "SESSION_STARTED", {"phase": "DIAGNOSE"})
    fetched = repository.list_events(LEARNER)[0]
    fetched.payload["phase"] = "TAMPERED"
    fetched.seq = 999
    assert repository.list_events(LEARNER)[0].to_dict() == event.to_dict()
    assert repository.get_event(event.event_id).to_dict() == event.to_dict()


# ---------------------------------------------------------------------------
# apply_assessment: event + snapshot consistency
# ---------------------------------------------------------------------------


def test_apply_assessment_writes_events_and_updates_snapshot():
    repository = FakeRepository()
    history = _history(repository)
    item = make_item()
    result = make_result("r1", status="CORRECT")
    snapshot = history.apply_assessment(LEARNER, SESSION, item, result)
    assert snapshot.revision == 1
    mastery = snapshot.masteries[BINARY_NODE]
    assert mastery.value == pytest.approx(0.2)
    assert mastery.confidence == pytest.approx(0.5)
    assert mastery.evidence_count == 1

    persisted = repository.get_snapshot(LEARNER)
    assert persisted is not None
    assert persisted.to_dict() == snapshot.to_dict()

    events = repository.list_events(LEARNER)
    assert [event.event_type for event in events] == ["ASSESSED", "MASTERY_UPDATED"]
    assert [event.seq for event in events] == [0, 1]

    assessed = events[0]
    assert assessed.event_id == "evt.assessed.r1"
    assert assessed.payload["result_id"] == "r1"
    assert assessed.payload["status"] == "CORRECT"
    # The log is self-contained: the teacher-visible item travels with the event.
    assert assessed.payload["item"]["item_id"] == ITEM_ID
    assert assessed.payload["result"]["result_id"] == "r1"

    mastery_event = events[1]
    assert mastery_event.event_id == "evt.mastery.r1"
    assert mastery_event.payload["applied"] is True
    assert mastery_event.payload["snapshot"]["revision"] == 1
    assert mastery_event.payload["policy_version"] == MasteryModel().policy.policy_version

    # Every payload is JSON-serialisable (append-only audit log requirement).
    for event in events:
        json.dumps(event.payload, ensure_ascii=False)


def test_apply_assessment_is_idempotent_on_result_id():
    repository = FakeRepository()
    history = _history(repository)
    item = make_item()
    result = make_result("r1", status="CORRECT")
    first = history.apply_assessment(LEARNER, SESSION, item, result)
    duplicate = history.apply_assessment(LEARNER, SESSION, item, result, first)
    assert duplicate.to_dict() == first.to_dict()
    assert len(repository.list_events(LEARNER)) == 2
    persisted = repository.get_snapshot(LEARNER)
    assert persisted is not None
    assert persisted.masteries[BINARY_NODE].evidence_count == 1
    # The deterministic idempotency keys are what the duplicate call found.
    assert repository.get_event("evt.assessed.r1") is not None
    assert repository.get_event("evt.mastery.r1") is not None


def test_apply_assessment_without_explicit_snapshot_uses_persisted_state():
    repository = FakeRepository()
    history = _history(repository)
    item = make_item()
    first = history.apply_assessment(
        LEARNER, SESSION, item, make_result("r1", status="CORRECT")
    )
    second = history.apply_assessment(
        LEARNER, SESSION, item, make_result("r2", status="CORRECT")
    )
    assert second.revision == first.revision + 1
    assert second.masteries[BINARY_NODE].evidence_count == 2


def test_apply_assessment_records_but_does_not_apply_non_evidence_statuses():
    repository = FakeRepository()
    history = _history(repository)
    item = make_item()
    for status in ("NEEDS_REVIEW", "EVAL_ERROR"):
        returned = history.apply_assessment(
            LEARNER,
            SESSION,
            item,
            make_result(f"r.{status}", status=status, failure_reason="judge unavailable"),
        )
        assert returned.to_dict() == history.model.initial_snapshot(LEARNER).to_dict()
    assert repository.get_snapshot(LEARNER) is None  # no snapshot written
    events = repository.list_events(LEARNER)
    assert [event.event_type for event in events] == ["ASSESSED", "MASTERY_UPDATED"] * 2
    assert [event.seq for event in events] == [0, 1, 2, 3]
    for event in events:
        if event.event_type == "MASTERY_UPDATED":
            assert event.payload["applied"] is False  # no learner error recorded
    # A learner with only non-evidence attempts rebuilds to the canonical empty state.
    assert history.verify_rebuild(LEARNER) is True
    assert history.rebuild_state(LEARNER).to_dict() == history.model.initial_snapshot(
        LEARNER
    ).to_dict()


def test_non_evidence_statuses_do_not_change_existing_state():
    repository = FakeRepository()
    history = _history(repository)
    item = make_item()
    snapshot = history.apply_assessment(
        LEARNER, SESSION, item, make_result("r1", status="CORRECT")
    )
    before = repository.get_snapshot(LEARNER)
    assert before is not None
    returned = history.apply_assessment(
        LEARNER, SESSION, item, make_result("r2", status="EVAL_ERROR"), snapshot
    )
    assert returned.to_dict() == before.to_dict()
    after = repository.get_snapshot(LEARNER)
    assert after is not None and after.to_dict() == before.to_dict()
    assert history.verify_rebuild(LEARNER) is True


def test_apply_assessment_rejects_stale_snapshot():
    repository = FakeRepository()
    history = _history(repository)
    item = make_item()
    history.apply_assessment(LEARNER, SESSION, item, make_result("r1", status="CORRECT"))
    stale = history.model.initial_snapshot(LEARNER)
    with pytest.raises(ConflictError):
        history.apply_assessment(
            LEARNER, SESSION, item, make_result("r2", status="CORRECT"), stale
        )
    # The rejected write did not append events or change the snapshot.
    assert [event.seq for event in repository.list_events(LEARNER)] == [0, 1]
    persisted = repository.get_snapshot(LEARNER)
    assert persisted is not None
    assert persisted.masteries[BINARY_NODE].evidence_count == 1
    assert history.verify_rebuild(LEARNER) is True


def test_first_mutation_after_rejected_attempts_canonicalises_snapshot():
    repository = FakeRepository()
    history = _history(repository)
    item = make_item()
    # A caller-created snapshot with wall-clock timestamps is not canonical: the
    # first *mutating* evidence must re-base timestamps on the evidence itself so
    # the persisted snapshot is exactly what a rebuild produces.
    caller_snapshot = LearnerSnapshot(
        learner_id=LEARNER, created_at=TS_LATER, updated_at=TS_LATER
    )
    returned = history.apply_assessment(
        LEARNER,
        SESSION,
        item,
        make_result("r1", status="NEEDS_REVIEW", failure_reason="judge unavailable"),
        caller_snapshot,
    )
    assert returned.to_dict() == caller_snapshot.to_dict()
    assert repository.get_snapshot(LEARNER) is None
    updated = history.apply_assessment(
        LEARNER, SESSION, item, make_result("r2", status="CORRECT"), caller_snapshot
    )
    assert updated.created_at == TS
    assert updated.updated_at == TS
    persisted = repository.get_snapshot(LEARNER)
    assert persisted is not None
    assert persisted.to_dict() == updated.to_dict()
    assert history.verify_rebuild(LEARNER) is True


def test_apply_assessment_fails_closed_on_mismatched_inputs():
    history = _history()
    item = make_item()
    with pytest.raises(ValidationError):
        history.apply_assessment(LEARNER, SESSION, item, make_result("r1", learner_id="learner.b"))
    with pytest.raises(ValidationError):
        history.apply_assessment(
            LEARNER, SESSION, item, make_result("r1", item_id="item.bs.mcq.005")
        )
    with pytest.raises(ValidationError):
        history.apply_assessment(LEARNER, "", item, make_result("r1"))
    with pytest.raises(ValidationError):
        history.apply_assessment(
            LEARNER,
            SESSION,
            item,
            make_result("r1"),
            history.model.initial_snapshot("learner.b"),
        )
    with pytest.raises(ValidationError):
        history.apply_assessment(LEARNER, SESSION, "item", make_result("r1"))  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        history.apply_assessment(LEARNER, SESSION, item, "result")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Rebuild + verification
# ---------------------------------------------------------------------------


def test_rebuild_state_matches_persisted_snapshot():
    repository = FakeRepository()
    history = _history(repository)
    item = make_item()
    boundary_item = make_item("item.bs.code.003", (BOUNDARY_NODE,))
    history.apply_assessment(LEARNER, SESSION, item, make_result("r1", status="CORRECT"))
    history.apply_assessment(
        LEARNER,
        SESSION,
        boundary_item,
        make_result(
            "r2", item_id="item.bs.code.003", status="INCORRECT", failure_reason="off_by_one"
        ),
    )
    history.apply_assessment(
        LEARNER, SESSION, item, make_result("r3", status="PARTIAL", score=0.5)
    )
    persisted = repository.get_snapshot(LEARNER)
    assert persisted is not None
    rebuilt = history.rebuild_state(LEARNER)
    assert rebuilt.to_dict() == persisted.to_dict()
    assert history.verify_rebuild(LEARNER) is True
    assert rebuilt.error_counts == {"off_by_one": 1}
    assert rebuilt.masteries[BOUNDARY_NODE].value == pytest.approx(0.0)
    assert rebuilt.masteries[BINARY_NODE].value > rebuilt.masteries[BOUNDARY_NODE].value


def test_verify_rebuild_detects_tampered_snapshot():
    repository = FakeRepository()
    history = _history(repository)
    item = make_item()
    history.apply_assessment(LEARNER, SESSION, item, make_result("r1", status="CORRECT"))
    persisted = repository.get_snapshot(LEARNER)
    assert persisted is not None
    tampered = LearnerSnapshot.from_dict(persisted.to_dict())
    tampered.masteries[BINARY_NODE].value = 0.99
    repository.upsert_snapshot(tampered)
    assert history.verify_rebuild(LEARNER) is False


def test_verify_rebuild_for_unknown_or_empty_learner():
    history = _history()
    assert history.verify_rebuild("learner.unknown") is True
    history.append_event("learner.unknown", SESSION, "SESSION_STARTED", {})
    assert history.verify_rebuild("learner.unknown") is True
    with pytest.raises(ValidationError):
        history.verify_rebuild("")


def test_sequence_continuity_and_replay_with_mixed_events():
    repository = FakeRepository()
    history = _history(repository)
    item = make_item()
    history.append_event(LEARNER, SESSION, "SESSION_STARTED", {"phase": "DIAGNOSE"})
    history.apply_assessment(LEARNER, SESSION, item, make_result("r1", status="CORRECT"))
    history.append_event(LEARNER, SESSION, "ACTION_TAKEN", {"kind": "EXPLAIN"})
    history.apply_assessment(LEARNER, SESSION, item, make_result("r2", status="INCORRECT"))
    history.append_event(LEARNER, SESSION, "SESSION_PAUSED", {"phase": "PAUSED"})
    events = repository.list_events(LEARNER)
    assert [event.seq for event in events] == list(range(7))
    assert [event.event_type for event in events] == [
        "SESSION_STARTED",
        "ASSESSED",
        "MASTERY_UPDATED",
        "ACTION_TAKEN",
        "ASSESSED",
        "MASTERY_UPDATED",
        "SESSION_PAUSED",
    ]
    persisted = repository.get_snapshot(LEARNER)
    assert persisted is not None
    assert history.rebuild_state(LEARNER).to_dict() == persisted.to_dict()
    assert history.verify_rebuild(LEARNER) is True


def test_known_result_ids_reflects_applied_assessments():
    repository = FakeRepository()
    history = _history(repository)
    item = make_item()
    history.apply_assessment(LEARNER, SESSION, item, make_result("r1", status="CORRECT"))
    history.apply_assessment(LEARNER, SESSION, item, make_result("r2", status="INCORRECT"))
    assert history.known_result_ids(LEARNER) == {"r1", "r2"}
    assert history.known_result_ids("learner.unknown") == set()


def test_duplicate_apply_heals_missing_snapshot_after_partial_crash(tmp_path: Path):
    repository = SqliteRepository(tmp_path / "heal.db")
    history = LearningHistory(repository)
    item = make_item()
    result = make_result("r1", status="CORRECT")
    # Simulate a crash after the event commit but before the snapshot write by
    # appending exactly the event the history would have produced.
    repository.append_event(
        HistoryEvent(
            event_id="evt.assessed.r1",
            learner_id=LEARNER,
            session_id=SESSION,
            seq=0,
            event_type="ASSESSED",
            payload={
                "result_id": "r1",
                "item_id": item.item_id,
                "status": "CORRECT",
                "result": result.to_dict(),
                "item": item.to_dict(),
            },
            created_at=result.created_at,
        )
    )
    recovered = history.apply_assessment(LEARNER, SESSION, item, result)
    assert recovered.revision == 1
    assert recovered.masteries[BINARY_NODE].value == pytest.approx(0.2)
    persisted = repository.get_snapshot(LEARNER)
    assert persisted is not None
    assert persisted.to_dict() == recovered.to_dict()
    assert len(repository.list_events(LEARNER)) == 1  # nothing appended twice
    assert history.verify_rebuild(LEARNER) is True
    repository.close()


# ---------------------------------------------------------------------------
# Construction validation
# ---------------------------------------------------------------------------


def test_history_requires_learner_repository():
    with pytest.raises(ValidationError):
        LearningHistory(object())  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        LearningHistory(FakeRepository(), model={"not": "a model"})  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# SQLite integration: atomic commit path + restart recovery
# ---------------------------------------------------------------------------


def test_history_with_sqlite_repository_scenario(tmp_path: Path):
    db_path = tmp_path / "history.db"
    repository = SqliteRepository(db_path)
    history = LearningHistory(repository)
    item = make_item()
    boundary_item = make_item("item.bs.code.003", (BOUNDARY_NODE,))
    history.append_event(LEARNER, SESSION, "SESSION_STARTED", {"phase": "DIAGNOSE"})
    history.apply_assessment(LEARNER, SESSION, item, make_result("r1", status="CORRECT"))
    history.apply_assessment(
        LEARNER,
        SESSION,
        boundary_item,
        make_result(
            "r2", item_id="item.bs.code.003", status="INCORRECT", failure_reason="off_by_one"
        ),
    )
    history.apply_assessment(
        LEARNER, SESSION, item, make_result("r3", status="NEEDS_REVIEW", failure_reason="n/a")
    )
    persisted_before = repository.get_snapshot(LEARNER)
    assert persisted_before is not None
    events_before = repository.list_events(LEARNER)
    assert history.verify_rebuild(LEARNER) is True
    repository.close()

    reopened = SqliteRepository(db_path)
    reopened_history = LearningHistory(reopened)
    persisted_after = reopened.get_snapshot(LEARNER)
    assert persisted_after is not None
    assert persisted_after.to_dict() == persisted_before.to_dict()
    assert [event.to_dict() for event in reopened.list_events(LEARNER)] == [
        event.to_dict() for event in events_before
    ]
    assert reopened_history.verify_rebuild(LEARNER) is True
    assert (
        reopened_history.rebuild_state(LEARNER).to_dict() == persisted_after.to_dict()
    )
    reopened.close()


def test_history_sqlite_duplicate_apply_is_stable_across_restart(tmp_path: Path):
    db_path = tmp_path / "history.db"
    repository = SqliteRepository(db_path)
    history = LearningHistory(repository)
    item = make_item()
    result = make_result("r1", status="CORRECT")
    first = history.apply_assessment(LEARNER, SESSION, item, result)
    repository.close()

    reopened = SqliteRepository(db_path)
    reopened_history = LearningHistory(reopened)
    duplicate = reopened_history.apply_assessment(LEARNER, SESSION, item, result)
    assert duplicate.to_dict() == first.to_dict()
    assert len(reopened.list_events(LEARNER)) == 2
    reopened.close()


# ---------------------------------------------------------------------------
# Synthetic student fixtures drive deterministic mock learner responses
# ---------------------------------------------------------------------------

STUDENTS_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "m1_teacher" / "students"
_STATUS_VALUES = {"CORRECT", "INCORRECT", "PARTIAL", "NEEDS_REVIEW", "EVAL_ERROR"}


def _load_student(name: str) -> dict:
    path = STUDENTS_DIR / f"{name}.json"
    assert path.is_file(), f"missing synthetic student fixture: {path}"
    text = path.read_text(encoding="utf-8")
    assert not text.startswith("\ufeff")
    return json.loads(text)


def _script_status(student: dict, item_id: str) -> dict:
    entry = student["response_script"]["per_item"].get(item_id)
    if entry is not None:
        return entry
    default = student["response_script"]["default"]
    return {"status": default["kind"]}


def _mock_result_from_script(
    student: dict, item: AssessmentItem, *, learner_id: str
) -> AssessmentResult:
    entry = _script_status(student, item.item_id)
    score = entry.get("score")
    return AssessmentResult(
        result_id=f"mock.{learner_id}.{item.item_id}",
        item_id=item.item_id,
        learner_id=learner_id,
        status=entry["status"],
        score=score,
        max_score=item.max_score,
        scorer_id="scorer.mock.script.v0",
        failure_reason=entry.get("error", ""),
        created_at=TS,
    )


def _run_student_script(
    adapter: CFBinarySearchDomainAdapter, student: dict, learner_id: str
) -> tuple[LearningHistory, LearnerSnapshot]:
    repository = FakeRepository()
    history = LearningHistory(repository)
    snapshot = history.model.initial_snapshot(learner_id)
    for item in adapter.assessment_items():
        result = _mock_result_from_script(student, item, learner_id=learner_id)
        snapshot = history.apply_assessment(learner_id, "session.script", item, result, snapshot)
    return history, snapshot


def test_student_fixtures_are_self_describing_synthetic_scripts(cf_domain_dir: Path):
    assert STUDENTS_DIR.is_dir(), f"missing synthetic student fixture directory: {STUDENTS_DIR}"
    adapter = CFBinarySearchDomainAdapter(cf_domain_dir)
    adapter.validate()
    items_by_id = {item.item_id: item for item in adapter.assessment_items()}
    node_ids = {node.node_id for node in adapter.knowledge_nodes()}
    names = {path.stem for path in STUDENTS_DIR.glob("*.json")}
    assert {"student_a", "student_b"} <= names, f"missing required student profiles: {names}"
    for name in sorted(names):
        student = _load_student(name)
        assert student["schema_version"] == "m1a.v0"
        assert student["student_id"] == name
        assert student["synthetic"] is True
        assert student["license"] == "CC0-1.0"
        assert student["display_name"].strip()
        assert student["description"].strip()
        traits = student["expected_traits"]
        assert set(traits) == {"known_nodes", "weak_nodes", "missing_prerequisites"}
        for key in ("known_nodes", "weak_nodes", "missing_prerequisites"):
            assert isinstance(traits[key], list), f"{name}.{key} must be a list"
            assert set(traits[key]) <= node_ids, f"{name}.{key}: unknown node ids"
        assert set(traits["known_nodes"]).isdisjoint(set(traits["weak_nodes"]))
        script = student["response_script"]
        assert set(script) == {"default", "per_item"}
        default = script["default"]
        assert isinstance(default, dict)
        assert default["kind"] in _STATUS_VALUES, f"{name}.default: illegal status"
        per_item = script["per_item"]
        assert isinstance(per_item, dict)
        for item_id, entry in per_item.items():
            assert item_id in items_by_id, f"{name}: per_item references unknown {item_id!r}"
            assert isinstance(entry, dict) and entry, f"{name}.{item_id}: empty script entry"
            assert set(entry) <= {"status", "error", "score"}
            assert entry["status"] in _STATUS_VALUES
            if "score" in entry:
                assert 0.0 <= float(entry["score"]) <= items_by_id[item_id].max_score
            if "error" in entry:
                assert entry["error"].strip()
        # Both synthetic profiles are exercised against real domain items.
        assert any(
            _script_status(student, item.item_id)["status"] != "CORRECT"
            for item in adapter.assessment_items()
        ), f"{name}: script does not exercise any non-CORRECT response"


def test_student_a_script_matches_expected_traits(cf_domain_dir: Path):
    student = _load_student("student_a")
    adapter = CFBinarySearchDomainAdapter(cf_domain_dir)
    history, snapshot = _run_student_script(adapter, student, "student_a")
    # Known node (binary search) is at the correct-evidence level; the weak
    # boundary node only collects a small partial-credit rise.
    assert snapshot.masteries[BINARY_NODE].value == pytest.approx(0.3)
    assert snapshot.masteries[BOUNDARY_NODE].value == pytest.approx(0.1 / 3)
    assert snapshot.masteries[BINARY_NODE].value > snapshot.masteries[BOUNDARY_NODE].value
    assert snapshot.error_counts == {"off_by_one": 2}
    assert student["expected_traits"]["known_nodes"] == [BINARY_NODE]
    assert student["expected_traits"]["weak_nodes"] == [BOUNDARY_NODE]
    assert student["expected_traits"]["missing_prerequisites"] == []
    assert history.verify_rebuild("student_a") is True


def test_student_b_script_shows_missing_sortedness_prerequisite(cf_domain_dir: Path):
    student = _load_student("student_b")
    adapter = CFBinarySearchDomainAdapter(cf_domain_dir)
    history, snapshot = _run_student_script(adapter, student, "student_b")
    # The missing monotonicity prerequisite and the dependent binary node both
    # stay at the floor: first evidence is INCORRECT and mastery can never rise.
    assert snapshot.masteries[SORTEDNESS_NODE].value == pytest.approx(0.0)
    assert snapshot.masteries[BINARY_NODE].value == pytest.approx(0.0)
    assert snapshot.masteries[SORTEDNESS_NODE].evidence_count == 2
    assert snapshot.masteries[BINARY_NODE].evidence_count == 2
    # Failure codes point at remediation targets (sortedness first, then binary).
    assert snapshot.error_counts == {"sortedness_missing": 2, "prerequisite_gap": 4}
    assert student["expected_traits"]["missing_prerequisites"] == [SORTEDNESS_NODE]
    assert set(student["expected_traits"]["weak_nodes"]) == {
        SORTEDNESS_NODE,
        BINARY_NODE,
    }
    # Known basics are still credited; remediation is targeted at the gap.
    assert snapshot.masteries["cf.array.basics"].value > 0.0
    assert snapshot.masteries["cf.search.linear"].value > 0.0
    assert history.verify_rebuild("student_b") is True
