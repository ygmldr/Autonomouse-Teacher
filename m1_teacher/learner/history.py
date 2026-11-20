"""Append-only learning-history service for the M1-A teacher (B-PR2).

``LearningHistory`` is the single-writer orchestration layer between the
deterministic mastery model (:mod:`m1_teacher.learner.model`) and a
:class:`~m1_teacher.contracts.repository.LearnerRepository` implementation.

Semantics
---------
* **Append-only.**  Events are never deleted or rewritten.  ``record_event``
  delegates to ``repository.append_event`` and is idempotent on
  ``HistoryEvent.event_id`` (a duplicate returns ``False`` and changes
  nothing).  There is deliberately no update/delete API.
* **Per-learner sequence.**  ``append_event`` allocates
  ``seq = (current max seq for that learner) + 1`` (the first event is ``0``).
  This assumes a **single writer per learner**: busy-wait/retry and
  multi-writer sequence allocation are explicitly out of scope for B-PR2 and
  would need a later PR (the SQLite implementation additionally enforces
  ``UNIQUE(learner_id, seq)`` and fails closed with ``ConflictError``).
* **JSON payloads.**  Every event payload is a JSON-serialisable ``dict``
  (enforced by the frozen :class:`HistoryEvent` contract before it reaches the
  repository).
* **Idempotent assessment application.**  ``apply_assessment`` derives
  deterministic event ids from ``result.result_id``
  (``evt.assessed.<result_id>`` / ``evt.mastery.<result_id>``).  Re-applying the
  same result returns the current state without touching mastery again.
* **Atomic state + history.**  When the assessment actually changes the
  snapshot, the history layer prefers the repository's additive
  ``append_events_and_upsert_snapshot(events, snapshot)`` extension, which
  commits the events and the materialised snapshot in **one transaction**
  (the SQLite repository implements it).  A repository that only implements
  the frozen protocol falls back to sequential ``append_event`` calls plus
  ``upsert_snapshot``; that fallback is documented as **not atomic** (a crash
  between the two can leave a snapshot lagging behind the log, which
  ``rebuild_state`` can repair).
* **Rebuild.**  ``rebuild_state`` replays the append-only log through the
  deterministic model; ``verify_rebuild`` compares the rebuilt snapshot with
  the persisted one field-by-field.  A learner with no persisted snapshot is
  compared against the canonical empty snapshot (``revision == 0``).
* **Stale snapshots fail closed.**  Passing a snapshot whose ``revision`` is
  behind the persisted one raises
  :class:`~m1_teacher.contracts.errors.ConflictError`: the caller must reload
  the current snapshot instead of silently recomputing from stale state.
* ``NEEDS_REVIEW`` / ``EVAL_ERROR`` assessments are recorded in the history
  (reason included in the payload) but never mutate the snapshot and therefore
  do not force a snapshot write.

Event payload schemas produced by this module (all fields JSON-serialisable):

``ASSESSED``
    ``{"result_id", "item_id", "status", "result": <AssessmentResult.to_dict()>,
    "item": <AssessmentItem.to_dict()>}`` — self-contained so the log alone is
    enough to rebuild state: the teacher-visible item metadata and the
    assessment outcome travel with the event.

``MASTERY_UPDATED``
    ``{"result_id", "status", "applied": bool, "snapshot":
    <LearnerSnapshot.to_dict()>, "policy_version"}`` — an audit trail of the
    exact snapshot produced by the policy version, including no-op updates
    (``applied=false`` for ``NEEDS_REVIEW``/``EVAL_ERROR``).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from ..contracts.errors import ConflictError, ValidationError
from ..contracts.repository import LearnerRepository
from ..contracts.types import (
    HISTORY_EVENT_TYPE_VALUES,
    AssessmentItem,
    AssessmentResult,
    HistoryEvent,
    LearnerSnapshot,
    now_utc,
)
from .model import MasteryModel, applied_result_ids

__all__ = [
    "ASSESSED_EVENT_PREFIX",
    "MASTERY_UPDATED_EVENT_PREFIX",
    "EventDraft",
    "LearningHistory",
]

ASSESSED_EVENT_PREFIX = "evt.assessed."
MASTERY_UPDATED_EVENT_PREFIX = "evt.mastery."


@dataclass(frozen=True)
class EventDraft:
    """A sequence-independent event ready to be materialised inside a commit.

    The B-NEXT transactional turn commit builds drafts without a ``seq`` (the
    sequence number is allocated inside the single SQLite transaction and
    retried on an explicit ``EVENT_SEQ_CONFLICT``), then materialises them with
    :meth:`materialize`.  Drafts are JSON/payload-only and never persisted
    directly.
    """

    event_id: str
    event_type: str
    payload: Mapping[str, Any]
    created_at: str

    def materialize(
        self, *, learner_id: str, session_id: str, seq: int
    ) -> HistoryEvent:
        """Build the frozen :class:`HistoryEvent` record for this draft."""

        return HistoryEvent(
            event_id=self.event_id,
            learner_id=learner_id,
            session_id=session_id,
            seq=seq,
            event_type=self.event_type,
            payload=dict(self.payload),
            created_at=self.created_at,
        )

_REQUIRED_REPOSITORY_METHODS: tuple[str, ...] = (
    "get_snapshot",
    "upsert_snapshot",
    "append_event",
    "get_event",
    "list_events",
    "get_goal",
    "upsert_goal",
)


def _require_nonempty_str(value: Any, where: str) -> str:
    if type(value) is not str or not value.strip():
        raise ValidationError(f"{where}: expected a non-blank string")
    return value


def _require_instance(value: Any, expected: type, where: str) -> Any:
    if not isinstance(value, expected):
        raise ValidationError(
            f"{where}: expected a {expected.__name__} instance, got {type(value).__name__}"
        )
    return value


def assessed_event_id(result_id: str) -> str:
    """Deterministic idempotency key of the ``ASSESSED`` event for a result."""

    return f"{ASSESSED_EVENT_PREFIX}{result_id}"


def mastery_updated_event_id(result_id: str) -> str:
    """Deterministic idempotency key of the ``MASTERY_UPDATED`` event for a result."""

    return f"{MASTERY_UPDATED_EVENT_PREFIX}{result_id}"


class LearningHistory:
    """Append-only learning history + mastery snapshot orchestration."""

    def __init__(self, repository: LearnerRepository, *, model: MasteryModel | None = None) -> None:
        missing = [
            name for name in _REQUIRED_REPOSITORY_METHODS if not callable(getattr(repository, name, None))
        ]
        if missing:
            raise ValidationError(
                "LearningHistory(repository=...): object is missing LearnerRepository "
                f"method(s): {', '.join(missing)}"
            )
        if model is None:
            model = MasteryModel()
        _require_instance(model, MasteryModel, "LearningHistory(model=...)")
        self._repository = repository
        self._model = model

    @property
    def repository(self) -> LearnerRepository:
        """The repository backing this history service."""

        return self._repository

    @property
    def model(self) -> MasteryModel:
        """The mastery model used to interpret assessment evidence."""

        return self._model

    # -- raw event log --------------------------------------------------------

    def record_event(self, event: HistoryEvent) -> bool:
        """Append a pre-built event; ``False`` if its ``event_id`` already exists.

        The event is not modified.  This is the raw append path (used for
        session/plan/diagnosis/action/error events); assessment events are
        normally produced by :meth:`apply_assessment`.
        """

        _require_instance(event, HistoryEvent, "LearningHistory.record_event()")
        return bool(self._repository.append_event(event))

    def append_event(
        self,
        learner_id: str,
        session_id: str,
        event_type: str,
        payload: Mapping[str, Any],
    ) -> HistoryEvent:
        """Append a new event with the next per-learner ``seq``.

        The event id is deterministic: ``evt.<learner_id>.<seq>``.  A
        collision (which would indicate a second writer or a corrupted log) is
        reported as :class:`~m1_teacher.contracts.errors.ConflictError`.
        """

        learner_id = _require_nonempty_str(learner_id, "LearningHistory.append_event()")
        session_id = _require_nonempty_str(
            session_id, "LearningHistory.append_event(session_id)"
        )
        if type(event_type) is not str or event_type not in HISTORY_EVENT_TYPE_VALUES:
            raise ValidationError(
                "LearningHistory.append_event(event_type): expected one of "
                f"{list(HISTORY_EVENT_TYPE_VALUES)}, got {event_type!r}"
            )
        if type(payload) is not dict:
            raise ValidationError(
                "LearningHistory.append_event(payload): expected a JSON-serialisable dict"
            )
        seq = self._next_seq(learner_id)
        event = HistoryEvent(
            event_id=f"evt.{learner_id}.{seq}",
            learner_id=learner_id,
            session_id=session_id,
            seq=seq,
            event_type=event_type,
            payload=dict(payload),
            created_at=now_utc(),
        )
        if not self._repository.append_event(event):
            raise ConflictError(
                f"LearningHistory.append_event(): event_id {event.event_id!r} already "
                "exists; concurrent writers are not supported"
            )
        return event

    # -- assessment application ----------------------------------------------

    def assessment_event_drafts(
        self,
        learner_id: str,
        session_id: str,
        item: AssessmentItem,
        result: AssessmentResult,
        snapshot: LearnerSnapshot,
    ) -> tuple[list[EventDraft], LearnerSnapshot, bool]:
        """Build the canonical ``ASSESSED``/``MASTERY_UPDATED`` drafts (pure).

        This is the single source of the assessment event payload schema, reused
        by :meth:`apply_assessment` and by the session engine's transactional
        teaching-turn commit.  It applies the deterministic mastery model to
        ``snapshot`` (the caller passes the current persisted snapshot) and
        returns ``(drafts, updated_snapshot, mutated)``.  The model maps
        ``NEEDS_REVIEW``/``EVAL_ERROR`` to a *no-op* update (``mutated=False``),
        so both statuses produce audit ``ASSESSED``/``MASTERY_UPDATED`` drafts
        with ``applied=false``; the session engine records ``EVAL_ERROR`` as an
        ``ERROR`` event instead (never as mastery evidence).
        """

        learner_id = _require_nonempty_str(
            learner_id, "LearningHistory.assessment_event_drafts()"
        )
        session_id = _require_nonempty_str(
            session_id, "LearningHistory.assessment_event_drafts(session_id)"
        )
        _require_instance(
            item, AssessmentItem, "LearningHistory.assessment_event_drafts(item)"
        )
        _require_instance(
            result, AssessmentResult, "LearningHistory.assessment_event_drafts(result)"
        )
        _require_instance(
            snapshot, LearnerSnapshot, "LearningHistory.assessment_event_drafts(snapshot)"
        )
        if result.learner_id != learner_id:
            raise ValidationError(
                "LearningHistory.assessment_event_drafts(): result.learner_id "
                f"{result.learner_id!r} does not match learner {learner_id!r}"
            )
        if result.item_id != item.item_id:
            raise ValidationError(
                "LearningHistory.assessment_event_drafts(): result.item_id "
                f"{result.item_id!r} does not match item.item_id {item.item_id!r}"
            )
        if snapshot.learner_id != learner_id:
            raise ValidationError(
                "LearningHistory.assessment_event_drafts(): snapshot belongs to learner "
                f"{snapshot.learner_id!r}, not {learner_id!r}"
            )
        updated = self._model.apply_result(snapshot, item, result)
        mutated = updated is not snapshot
        drafts = [
            EventDraft(
                event_id=assessed_event_id(result.result_id),
                event_type="ASSESSED",
                payload={
                    "result_id": result.result_id,
                    "item_id": item.item_id,
                    "status": result.status,
                    "result": result.to_dict(),
                    "item": item.to_dict(),
                },
                created_at=result.created_at,
            ),
            EventDraft(
                event_id=mastery_updated_event_id(result.result_id),
                event_type="MASTERY_UPDATED",
                payload={
                    "result_id": result.result_id,
                    "status": result.status,
                    "applied": mutated,
                    "snapshot": updated.to_dict(),
                    "policy_version": self._model.policy.policy_version,
                },
                created_at=result.created_at,
            ),
        ]
        return drafts, updated, mutated

    def apply_assessment(
        self,
        learner_id: str,
        session_id: str,
        item: AssessmentItem,
        result: AssessmentResult,
        snapshot: LearnerSnapshot | None = None,
    ) -> LearnerSnapshot:
        """Record one assessment and return the updated learner snapshot.

        Writes one ``ASSESSED`` event (self-contained evidence) plus one
        ``MASTERY_UPDATED`` event and, when the evidence mutates state, upserts
        the new snapshot atomically with the events (see module docstring).
        Applying the same ``result.result_id`` twice is idempotent: the second
        call returns the persisted snapshot and appends nothing.
        """

        learner_id = _require_nonempty_str(
            learner_id, "LearningHistory.apply_assessment()"
        )
        session_id = _require_nonempty_str(
            session_id, "LearningHistory.apply_assessment(session_id)"
        )
        _require_instance(item, AssessmentItem, "LearningHistory.apply_assessment(item)")
        _require_instance(result, AssessmentResult, "LearningHistory.apply_assessment(result)")
        if result.learner_id != learner_id:
            raise ValidationError(
                "LearningHistory.apply_assessment(): result.learner_id "
                f"{result.learner_id!r} does not match learner {learner_id!r}"
            )
        if result.item_id != item.item_id:
            raise ValidationError(
                "LearningHistory.apply_assessment(): result.item_id "
                f"{result.item_id!r} does not match item.item_id {item.item_id!r}"
            )
        if snapshot is not None:
            _require_instance(
                snapshot, LearnerSnapshot, "LearningHistory.apply_assessment(snapshot)"
            )
            if snapshot.learner_id != learner_id:
                raise ValidationError(
                    "LearningHistory.apply_assessment(): snapshot belongs to learner "
                    f"{snapshot.learner_id!r}, not {learner_id!r}"
                )
            base = snapshot
            persisted = self._repository.get_snapshot(learner_id)
            if persisted is not None and snapshot.revision < persisted.revision:
                raise ConflictError(
                    "LearningHistory.apply_assessment(): stale snapshot revision "
                    f"{snapshot.revision} for learner {learner_id!r} (persisted "
                    f"revision is {persisted.revision}); reload the current snapshot"
                )
        else:
            persisted = self._repository.get_snapshot(learner_id)
            base = persisted if persisted is not None else self._model.initial_snapshot(learner_id)

        existing = self._repository.get_event(assessed_event_id(result.result_id))
        if existing is not None:
            current = self._repository.get_snapshot(learner_id)
            if current is not None:
                return current
            # The event log already contains this assessment but the
            # materialised snapshot is missing (crash in a non-atomic fallback
            # writer): heal from the log instead of returning stale state.
            rebuilt = self.rebuild_state(learner_id)
            if rebuilt.revision > 0:
                self._repository.upsert_snapshot(rebuilt)
            return rebuilt

        drafts, updated, mutated = self.assessment_event_drafts(
            learner_id, session_id, item, result, base
        )
        seq = self._next_seq(learner_id)
        events = [
            draft.materialize(learner_id=learner_id, session_id=session_id, seq=seq + offset)
            for offset, draft in enumerate(drafts)
        ]

        if mutated:
            atomic = getattr(self._repository, "append_events_and_upsert_snapshot", None)
            if callable(atomic):
                appended = atomic(events, updated)
                if not self._all_appended(appended):
                    current = self._repository.get_snapshot(learner_id)
                    return current if current is not None else base
                return updated
            # Documented non-atomic fallback for protocol-only repositories.
            appended_flags = [self._repository.append_event(event) for event in events]
            if not self._all_appended(appended_flags):
                return base
            self._repository.upsert_snapshot(updated)
            return updated

        batch = getattr(self._repository, "append_events", None)
        if callable(batch):
            batch(events)
        else:
            for event in events:
                self._repository.append_event(event)
        return base

    # -- rebuild / verification ----------------------------------------------

    def rebuild_state(self, learner_id: str) -> LearnerSnapshot:
        """Rebuild the learner snapshot from the append-only event log."""

        learner_id = _require_nonempty_str(
            learner_id, "LearningHistory.rebuild_state()"
        )
        events = self._list_events(learner_id)
        items_by_id: dict[str, AssessmentItem] = {}
        for event in events:
            if event.event_type != "ASSESSED":
                continue
            raw_item = event.payload.get("item")
            if isinstance(raw_item, Mapping):
                item = AssessmentItem.from_dict(raw_item)
                items_by_id[item.item_id] = item
        return self._model.rebuild_snapshot(learner_id, events, items_by_id)

    def verify_rebuild(self, learner_id: str) -> bool:
        """``True`` when the persisted snapshot equals the rebuilt snapshot.

        A learner without a persisted snapshot verifies against the canonical
        empty snapshot (no evidence applied yet).
        """

        learner_id = _require_nonempty_str(
            learner_id, "LearningHistory.verify_rebuild()"
        )
        rebuilt = self.rebuild_state(learner_id)
        persisted = self._repository.get_snapshot(learner_id)
        if persisted is None:
            canonical = self._model.initial_snapshot(learner_id)
            return rebuilt.to_dict() == canonical.to_dict()
        return persisted.to_dict() == rebuilt.to_dict()

    def known_result_ids(self, learner_id: str) -> set[str]:
        """All ``result_id`` values already applied for ``learner_id``.

        Convenience for callers that want to pass ``applied_result_ids`` to the
        stateless model before applying a batch.
        """

        learner_id = _require_nonempty_str(
            learner_id, "LearningHistory.known_result_ids()"
        )
        return applied_result_ids(self._list_events(learner_id))

    # -- internals ------------------------------------------------------------

    def _list_events(self, learner_id: str) -> list[HistoryEvent]:
        events = self._repository.list_events(learner_id)
        if type(events) is not list:
            raise ValidationError(
                "LearningHistory: repository.list_events() must return a list"
            )
        for index, event in enumerate(events):
            if not isinstance(event, HistoryEvent):
                raise ValidationError(
                    "LearningHistory: repository.list_events() returned a non-HistoryEvent "
                    f"at index {index}"
                )
        return events

    def _next_seq(self, learner_id: str) -> int:
        events = self._list_events(learner_id)
        for index, event in enumerate(events):
            if type(event.seq) is not int or event.seq < 0:
                raise ValidationError(
                    "LearningHistory: repository event at index "
                    f"{index} has invalid seq {event.seq!r}"
                )
        return max((event.seq for event in events), default=-1) + 1

    @staticmethod
    def _all_appended(flags: Sequence[bool]) -> bool:
        if isinstance(flags, bool):
            return flags
        return all(flags)
