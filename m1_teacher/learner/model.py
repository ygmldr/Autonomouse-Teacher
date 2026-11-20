"""Deterministic, evidence-driven learner mastery model for the M1-A teacher (B-PR2).

Scope
-----
This module turns **observed assessment outcomes** into a materialised
:class:`~m1_teacher.contracts.types.LearnerSnapshot`.  It is a small,
explainable heuristic (not a statistical/BKT estimator, not a claim of real
teaching effectiveness) with fixed, injectable constants:

* :class:`MasteryPolicy` holds every constant of the update rule.  The
  defaults below are the frozen ``m1a.learner.mastery.heuristic.v0`` policy.
  Tests may inject a different policy, but the default is deterministic and
  has no randomness, no clock reads and no network/IO.
* :class:`MasteryModel` is a pure function object: ``apply_result`` never
  mutates its arguments, and the same inputs always produce the same output
  (timestamps are copied from the assessment evidence, never read from the
  wall clock).

Evidence rules (fail-closed)
----------------------------
Only **observed** evidence is accepted.  The frozen ``m1a.v0``
:class:`~m1_teacher.contracts.types.AssessmentResult` has no
``evidence_source`` field, so the caller (the independent scorer / assessment
pipeline) asserts the source explicitly through ``evidence_source=``; the only
accepted value is ``EVIDENCE_SOURCE.OBSERVED``.  Inferred/unknown sources raise
:class:`~m1_teacher.contracts.errors.ValidationError` instead of silently
updating mastery.

Evaluation errors never count as learner errors: ``NEEDS_REVIEW`` and
``EVAL_ERROR`` outcomes leave the snapshot **completely unchanged** (mastery,
confidence, evidence count, completed items, error counters, revision and
timestamps).  The failure reason is stored by the history layer in the
``ASSESSED`` event payload.

Update formulas (per knowledge node ``n`` reported by the item)
---------------------------------------------------------------
Let ``v`` be the current mastery value, ``c`` the confidence and ``e`` the
evidence count of node ``n`` *before* this update.  An unseen node starts at
``MasteryPolicy.initial_value`` (default ``0.0``: unknown is never treated as
mastered) with confidence ``0.0`` and evidence count ``0``.

The step size decays with the amount of evidence already collected::

    decay = 1 / (1 + e)

This yields the classic "large corrections early, small corrections later"
behaviour and makes the result order-independent only to the extent the event
order is fixed (it is: replay is by ``seq``).

* ``CORRECT``::

      v' = min(policy.max_value, v + policy.correct_step * decay)
      c' = c + (1 - c) * policy.correct_confidence_gain
      e' = e + 1

* ``INCORRECT`` (mastery can only go down or stay flat; a wrong answer never
  raises mastery)::

      v' = max(0.0, v - policy.incorrect_step * decay)
      c' = c + (1 - c) * policy.incorrect_confidence_gain
      e' = e + 1
      error_counts[result.failure_reason or item.item_id] += 1

* ``PARTIAL``: ``ratio = result.score / result.max_score`` (``0.0`` when the
  scorer supplied no score).  The partial credit threshold guards against
  "mostly wrong" answers being rewarded::

      if ratio >= policy.partial_credit_threshold:
          v' = min(policy.max_value, v + policy.partial_step * decay)
      else:
          v' = v                      # neutral evidence: no rise, no drop
      c' = c + (1 - c) * policy.partial_confidence_gain
      e' = e + 1

* ``NEEDS_REVIEW`` / ``EVAL_ERROR``: no change at all (the snapshot is
  returned as-is).

Completed items are recorded in ``completed_item_ids`` (append order, no
duplicates); wrongly/partially answered items count as completed attempts.
Only nodes listed in ``item.node_ids`` are ever touched: no other mastery entry
is created, and an unobserved node never appears in the snapshot.

Idempotency / duplicate submissions
-----------------------------------
``apply_result`` is *stateless*.  It cannot know whether a result was applied
before unless the caller tells it through ``applied_result_ids``.  The
documented contract is:

* ``apply_result(...)`` applies exactly one observed result.  Passing
  ``applied_result_ids`` (for example :func:`applied_result_ids` computed from
  the history events) makes the call idempotent on ``result.result_id``:
  duplicate submissions return the snapshot unchanged.
* ``apply_results(snapshot, pairs)`` is the convenience batch API: it
  de-duplicates ``result.result_id`` **within the batch** and replays the
  remaining pairs in order.
* The authoritative cross-call de-duplication is owned by
  :class:`m1_teacher.learner.history.LearningHistory`, which derives a
  deterministic ``ASSESSED`` event id per ``result_id`` and refuses to apply a
  result twice.

Rebuild
-------
:meth:`MasteryModel.rebuild_snapshot` replays ``ASSESSED`` history events
(sorted by ``seq``, de-duplicated by ``result_id``) and must reproduce the
incrementally materialised snapshot **exactly** (field-level equality).  This
is guaranteed because the model reads no clock: snapshot/mastery timestamps are
copied from ``AssessmentResult.created_at``, and the canonical empty snapshot
uses :data:`EPOCH_TIMESTAMP`.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from ..contracts.errors import ValidationError
from ..contracts.types import (
    ASSESSMENT_STATUS_VALUES,
    EVIDENCE_SOURCE_VALUES,
    AssessmentItem,
    AssessmentResult,
    HistoryEvent,
    LearnerSnapshot,
    MasteryEstimate,
)

__all__ = [
    "EPOCH_TIMESTAMP",
    "OBSERVED_EVIDENCE",
    "MasteryModel",
    "MasteryPolicy",
    "applied_result_ids",
]

OBSERVED_EVIDENCE = "OBSERVED"
"""The only accepted evidence source for mastery updates."""

EPOCH_TIMESTAMP = "1970-01-01T00:00:00Z"
"""Deterministic timestamp of the canonical empty snapshot (replay base)."""

_MUTATING_STATUSES: tuple[str, ...] = ("CORRECT", "INCORRECT", "PARTIAL")
_NO_OP_STATUSES: tuple[str, ...] = ("NEEDS_REVIEW", "EVAL_ERROR")

# Decay/confidence arithmetic is deterministic; the constants are deliberately
# plain floats and are never rounded, so callers can reproduce values exactly
# with the documented formulas.


@dataclass(frozen=True)
class MasteryPolicy:
    """Frozen constants of the deterministic mastery heuristic.

    Defaults are the ``m1a.learner.mastery.heuristic.v0`` policy.  All fields
    are validated at construction; a policy that could produce an invalid
    :class:`~m1_teacher.contracts.types.MasteryEstimate` (for example
    ``max_value > 1.0``) is rejected fail-closed.
    """

    initial_value: float = 0.0
    correct_step: float = 0.2
    incorrect_step: float = 0.2
    partial_step: float = 0.1
    partial_credit_threshold: float = 0.5
    correct_confidence_gain: float = 0.5
    incorrect_confidence_gain: float = 0.25
    partial_confidence_gain: float = 0.25
    max_value: float = 1.0
    policy_version: str = "m1a.learner.mastery.heuristic.v0"

    def __post_init__(self) -> None:
        for name in (
            "initial_value",
            "correct_step",
            "incorrect_step",
            "partial_step",
            "partial_credit_threshold",
            "correct_confidence_gain",
            "incorrect_confidence_gain",
            "partial_confidence_gain",
            "max_value",
        ):
            value = getattr(self, name)
            if type(value) not in (int, float):
                raise ValidationError(
                    f"MasteryPolicy.{name}: expected a finite number, got {type(value).__name__}"
                )
            number = float(value)
            if not math.isfinite(number):
                raise ValidationError(f"MasteryPolicy.{name}: expected a finite number")
            if number < 0.0:
                raise ValidationError(f"MasteryPolicy.{name}: must be >= 0, got {number!r}")
        if not 0.0 <= float(self.initial_value) <= float(self.max_value):
            raise ValidationError("MasteryPolicy.initial_value must be within [0, max_value]")
        if not 0.0 < float(self.max_value) <= 1.0:
            raise ValidationError("MasteryPolicy.max_value must be within (0, 1]")
        if not 0.0 <= float(self.partial_credit_threshold) <= 1.0:
            raise ValidationError("MasteryPolicy.partial_credit_threshold must be within [0, 1]")
        for name in (
            "correct_confidence_gain",
            "incorrect_confidence_gain",
            "partial_confidence_gain",
        ):
            if not 0.0 < float(getattr(self, name)) <= 1.0:
                raise ValidationError(f"MasteryPolicy.{name} must be within (0, 1]")
        if type(self.policy_version) is not str or not self.policy_version.strip():
            raise ValidationError("MasteryPolicy.policy_version must be a non-blank string")


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


def _clamp(value: float, *, minimum: float, maximum: float) -> float:
    if value < minimum:
        return minimum
    if value > maximum:
        return maximum
    return value


def applied_result_ids(events: Iterable[HistoryEvent]) -> set[str]:
    """Collect the ``result_id`` values of all ``ASSESSED`` events.

    Callers can pass the returned set to :meth:`MasteryModel.apply_result` /
    :meth:`MasteryModel.apply_results` as ``applied_result_ids`` to make
    single-call application idempotent on ``result_id``.
    """

    result: set[str] = set()
    for index, event in enumerate(events):
        _require_instance(event, HistoryEvent, f"applied_result_ids()[{index}]")
        if event.event_type != "ASSESSED":
            continue
        payload = event.payload
        if not isinstance(payload, Mapping):
            raise ValidationError(
                f"applied_result_ids()[{index}]: ASSESSED payload must be a mapping"
            )
        result_id = payload.get("result_id")
        if result_id is None:
            nested = payload.get("result")
            if isinstance(nested, Mapping):
                result_id = nested.get("result_id")
        if type(result_id) is not str or not result_id.strip():
            raise ValidationError(
                f"applied_result_ids()[{index}]: ASSESSED payload has no result_id"
            )
        result.add(result_id)
    return result


class MasteryModel:
    """Deterministic observed-evidence mastery model (see module docstring)."""

    def __init__(self, policy: MasteryPolicy | None = None) -> None:
        if policy is None:
            policy = MasteryPolicy()
        _require_instance(policy, MasteryPolicy, "MasteryModel(policy=...)")
        self._policy = policy

    @property
    def policy(self) -> MasteryPolicy:
        """The immutable policy used by this model."""

        return self._policy

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"MasteryModel(policy_version={self._policy.policy_version!r})"

    # -- snapshots ------------------------------------------------------------

    def initial_snapshot(self, learner_id: str) -> LearnerSnapshot:
        """Canonical empty snapshot (deterministic epoch timestamps)."""

        learner_id = _require_nonempty_str(learner_id, "MasteryModel.initial_snapshot()")
        return LearnerSnapshot(
            learner_id=learner_id,
            created_at=EPOCH_TIMESTAMP,
            updated_at=EPOCH_TIMESTAMP,
        )

    # -- single result --------------------------------------------------------

    def apply_result(
        self,
        snapshot: LearnerSnapshot,
        item: AssessmentItem,
        result: AssessmentResult,
        *,
        evidence_source: str = OBSERVED_EVIDENCE,
        applied_result_ids: Iterable[str] | None = None,
    ) -> LearnerSnapshot:
        """Apply one observed assessment result and return the new snapshot.

        The returned snapshot is a new value object; the input snapshot, item
        and result are never mutated.  ``applied_result_ids`` makes the call
        idempotent on ``result.result_id`` (see module docstring); it must be an
        iterable of strings.
        """

        self._validate_evidence(snapshot, item, result, evidence_source=evidence_source)
        already_applied = self._coerce_applied_result_ids(applied_result_ids)
        if result.result_id in already_applied:
            return snapshot
        return self._apply_one(snapshot, item, result)

    # -- batch ----------------------------------------------------------------

    def apply_results(
        self,
        snapshot: LearnerSnapshot,
        pairs: Sequence[tuple[AssessmentItem, AssessmentResult]],
        *,
        evidence_source: str = OBSERVED_EVIDENCE,
        applied_result_ids: Iterable[str] | None = None,
    ) -> LearnerSnapshot:
        """Apply a batch of ``(item, result)`` pairs in order.

        ``result_id`` values already present in ``applied_result_ids`` and
        duplicates **within the batch** are skipped exactly once, so repeated
        submissions never update mastery twice.
        """

        _require_instance(snapshot, LearnerSnapshot, "MasteryModel.apply_results(snapshot)")
        if isinstance(pairs, (str, bytes)) or not isinstance(pairs, Sequence):
            raise ValidationError(
                "MasteryModel.apply_results(pairs): expected a sequence of "
                "(item, result) pairs"
            )
        seen = self._coerce_applied_result_ids(applied_result_ids)
        current = snapshot
        for index, pair in enumerate(pairs):
            where = f"MasteryModel.apply_results(pairs[{index}])"
            if type(pair) is not tuple or len(pair) != 2:
                raise ValidationError(f"{where}: expected a (item, result) tuple")
            item, result = pair
            self._validate_evidence(current, item, result, evidence_source=evidence_source)
            if result.result_id in seen:
                continue
            current = self._apply_one(current, item, result)
            seen.add(result.result_id)
        return current

    # -- rebuild --------------------------------------------------------------

    def rebuild_snapshot(
        self,
        learner_id: str,
        events: list[HistoryEvent],
        items_by_id: Mapping[str, AssessmentItem],
    ) -> LearnerSnapshot:
        """Rebuild a snapshot by replaying ``ASSESSED`` events.

        Events are replayed in ascending ``seq`` order and de-duplicated by
        ``result.result_id``.  Each event payload must be self-contained
        (``payload["result"]``) and either embed ``payload["item"]`` or
        reference an item available in ``items_by_id``; anything else fails
        closed with :class:`~m1_teacher.contracts.errors.ValidationError`.
        """

        learner_id = _require_nonempty_str(learner_id, "MasteryModel.rebuild_snapshot()")
        if type(events) is not list:
            raise ValidationError("MasteryModel.rebuild_snapshot(events=...): expected a list")
        if not isinstance(items_by_id, Mapping):
            raise ValidationError(
                "MasteryModel.rebuild_snapshot(items_by_id=...): expected a mapping"
            )
        for key, value in items_by_id.items():
            if type(key) is not str or not key.strip():
                raise ValidationError(
                    "MasteryModel.rebuild_snapshot(items_by_id): keys must be non-blank strings"
                )
            _require_instance(value, AssessmentItem, f"MasteryModel.rebuild_snapshot[{key!r}]")

        ordered = self._ordered_events(learner_id, events)
        snapshot = self.initial_snapshot(learner_id)
        seen: set[str] = set()
        for event in ordered:
            if event.event_type != "ASSESSED":
                continue
            item, result = self._decode_assessment_event(event, items_by_id)
            if result.result_id in seen:
                continue
            snapshot = self._apply_one(snapshot, item, result)
            seen.add(result.result_id)
        return snapshot

    # -- internals ------------------------------------------------------------

    def _ordered_events(
        self, learner_id: str, events: list[HistoryEvent]
    ) -> list[HistoryEvent]:
        seen_seq: set[int] = set()
        for index, event in enumerate(events):
            where = f"MasteryModel.rebuild_snapshot(events[{index}])"
            _require_instance(event, HistoryEvent, where)
            if event.learner_id != learner_id:
                raise ValidationError(
                    f"{where}: event belongs to learner {event.learner_id!r}, "
                    f"not {learner_id!r}"
                )
            if type(event.seq) is not int or event.seq < 0:
                raise ValidationError(f"{where}: seq must be a non-negative integer")
            if event.seq in seen_seq:
                raise ValidationError(f"{where}: duplicate seq {event.seq!r}")
            seen_seq.add(event.seq)
        return sorted(events, key=lambda event: event.seq)

    def _decode_assessment_event(
        self, event: HistoryEvent, items_by_id: Mapping[str, AssessmentItem]
    ) -> tuple[AssessmentItem, AssessmentResult]:
        where = f"MasteryModel.rebuild_snapshot(ASSESSED event {event.event_id!r})"
        payload = event.payload
        if not isinstance(payload, Mapping):
            raise ValidationError(f"{where}: payload must be a mapping")
        raw_result = payload.get("result")
        if not isinstance(raw_result, Mapping):
            raise ValidationError(f"{where}: payload.result must be a mapping")
        try:
            result = AssessmentResult.from_dict(raw_result)
        except ValidationError as exc:
            raise ValidationError(f"{where}: invalid payload.result: {exc.message}") from None
        raw_item = payload.get("item")
        if raw_item is not None:
            if not isinstance(raw_item, Mapping):
                raise ValidationError(f"{where}: payload.item must be a mapping")
            try:
                item = AssessmentItem.from_dict(raw_item)
            except ValidationError as exc:
                raise ValidationError(f"{where}: invalid payload.item: {exc.message}") from None
        else:
            item = items_by_id.get(result.item_id)
            if item is None:
                raise ValidationError(
                    f"{where}: event embeds no item and items_by_id has no "
                    f"{result.item_id!r}; rebuild needs self-contained events"
                )
        if item.item_id != result.item_id:
            raise ValidationError(
                f"{where}: item {item.item_id!r} does not match result item "
                f"{result.item_id!r}"
            )
        return item, result

    def _validate_evidence(
        self,
        snapshot: Any,
        item: Any,
        result: Any,
        *,
        evidence_source: Any,
    ) -> None:
        _require_instance(snapshot, LearnerSnapshot, "MasteryModel.apply_result(snapshot)")
        _require_instance(item, AssessmentItem, "MasteryModel.apply_result(item)")
        _require_instance(result, AssessmentResult, "MasteryModel.apply_result(result)")
        if type(evidence_source) is not str or evidence_source not in EVIDENCE_SOURCE_VALUES:
            raise ValidationError(
                "MasteryModel.apply_result(evidence_source=...): expected one of "
                f"{list(EVIDENCE_SOURCE_VALUES)}, got {evidence_source!r}"
            )
        if evidence_source != OBSERVED_EVIDENCE:
            raise ValidationError(
                "MasteryModel.apply_result(): only OBSERVED evidence may update mastery; "
                f"got {evidence_source!r}"
            )
        if type(result.status) is not str or result.status not in ASSESSMENT_STATUS_VALUES:
            raise ValidationError(
                "MasteryModel.apply_result(result.status): unknown assessment status "
                f"{result.status!r}"
            )
        if result.item_id != item.item_id:
            raise ValidationError(
                "MasteryModel.apply_result(): result.item_id "
                f"{result.item_id!r} does not match item.item_id {item.item_id!r}"
            )
        if result.learner_id != snapshot.learner_id:
            raise ValidationError(
                "MasteryModel.apply_result(): result.learner_id "
                f"{result.learner_id!r} does not match snapshot learner "
                f"{snapshot.learner_id!r}"
            )
        if type(item.node_ids) is not list or not item.node_ids:
            raise ValidationError(
                "MasteryModel.apply_result(item.node_ids): expected a non-empty list"
            )
        for index, node_id in enumerate(item.node_ids):
            if type(node_id) is not str or not node_id.strip():
                raise ValidationError(
                    "MasteryModel.apply_result(item.node_ids"
                    f"[{index}]): expected a non-blank node_id"
                )
        for node_id, mastery in snapshot.masteries.items():
            if mastery.node_id != node_id:
                raise ValidationError(
                    f"MasteryModel.apply_result(snapshot.masteries[{node_id!r}]): "
                    "mastery.node_id does not match its dict key"
                )

    @staticmethod
    def _coerce_applied_result_ids(
        applied_result_ids: Iterable[str] | None,
    ) -> set[str]:
        if applied_result_ids is None:
            return set()
        if isinstance(applied_result_ids, (str, bytes)) or not isinstance(
            applied_result_ids, Iterable
        ):
            raise ValidationError(
                "MasteryModel.apply_result(applied_result_ids=...): expected an iterable "
                "of result_id strings"
            )
        result: set[str] = set()
        for value in applied_result_ids:
            if type(value) is not str or not value.strip():
                raise ValidationError(
                    "MasteryModel.apply_result(applied_result_ids=...): entries must be "
                    "non-blank strings"
                )
            result.add(value)
        return result

    def _apply_one(
        self, snapshot: LearnerSnapshot, item: AssessmentItem, result: AssessmentResult
    ) -> LearnerSnapshot:
        if result.status in _NO_OP_STATUSES:
            # NEEDS_REVIEW / EVAL_ERROR: never counted as learner evidence.
            return snapshot
        if result.status not in _MUTATING_STATUSES:  # pragma: no cover - enum is closed
            raise ValidationError(
                f"MasteryModel.apply_result(): unsupported status {result.status!r}"
            )

        policy = self._policy
        masteries = dict(snapshot.masteries)
        completed = list(snapshot.completed_item_ids)
        error_counts = dict(snapshot.error_counts)

        for node_id in item.node_ids:
            existing = masteries.get(node_id)
            if existing is None:
                value = float(policy.initial_value)
                confidence = 0.0
                evidence_count = 0
                created_at = result.created_at
            else:
                value = float(existing.value)
                confidence = float(existing.confidence)
                evidence_count = int(existing.evidence_count)
                created_at = existing.created_at

            decay = 1.0 / (1.0 + evidence_count)
            if result.status == "CORRECT":
                value = min(
                    float(policy.max_value), value + float(policy.correct_step) * decay
                )
                confidence = confidence + (1.0 - confidence) * float(
                    policy.correct_confidence_gain
                )
            elif result.status == "INCORRECT":
                value = max(0.0, value - float(policy.incorrect_step) * decay)
                confidence = confidence + (1.0 - confidence) * float(
                    policy.incorrect_confidence_gain
                )
            else:  # PARTIAL
                ratio = 0.0
                if result.score is not None and result.max_score > 0.0:
                    ratio = float(result.score) / float(result.max_score)
                if ratio >= float(policy.partial_credit_threshold):
                    value = min(
                        float(policy.max_value), value + float(policy.partial_step) * decay
                    )
                confidence = confidence + (1.0 - confidence) * float(
                    policy.partial_confidence_gain
                )

            masteries[node_id] = MasteryEstimate(
                node_id=node_id,
                value=_clamp(value, minimum=0.0, maximum=1.0),
                confidence=_clamp(confidence, minimum=0.0, maximum=1.0),
                evidence_count=evidence_count + 1,
                created_at=created_at,
                updated_at=result.created_at,
            )

        if result.status == "INCORRECT":
            error_key = result.failure_reason.strip() or item.item_id
            error_counts[error_key] = error_counts.get(error_key, 0) + 1

        if item.item_id not in completed:
            completed.append(item.item_id)

        created_at = (
            result.created_at if snapshot.revision == 0 else snapshot.created_at
        )
        return LearnerSnapshot(
            learner_id=snapshot.learner_id,
            masteries=masteries,
            completed_item_ids=completed,
            error_counts=error_counts,
            revision=snapshot.revision + 1,
            created_at=created_at,
            updated_at=result.created_at,
        )
