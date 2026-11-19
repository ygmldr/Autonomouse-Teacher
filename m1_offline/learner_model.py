"""Evidence-driven learner model (M1 offline Teacher Core).

Invariants (enforced by tests):

* **No evidence, no mastery.**  A fresh model exposes an empty ``mastery`` map;
  only scored :class:`~m1_offline.types.EvidenceEvent` records can move it.
* **Failures lower mastery (or leave it unchanged); they never raise it.**
  ``observed_score`` below current mastery always moves mastery down with the
  same update rule used for gains.  An observation that carries ``error_codes``
  is a failed/partial attempt and is fail-closed: it may lower mastery or leave
  it unchanged, but it can never raise it (a failed assessment is not proof of
  improvement).
* **No phantom transfer.**  Every task is bound to the skill set it declares
  (first evidence payload ``skill_ids`` or an explicit
  :meth:`LearnerModel.register_task_skills`).  Repeated observations of the
  same task earn diminishing credit and can never credit skills outside that
  bound set, so re-doing one problem is not mistaken for transfer.
* **Deterministic replay.**  ``replay(events)`` starts from a clean model and
  applies events in order; the resulting state depends only on the events (the
  ``updated_at`` timestamp follows the last event timestamp).
* **Idempotent by event id.**  Applying the same ``event_id`` twice is a no-op,
  so at-least-once delivery cannot double-count evidence.

The model is deliberately simple and auditable: it is a bounded running
average, not a psychometric model, and it is labelled as a synthetic proxy.
"""

from __future__ import annotations

from .types import EvidenceEvent, LearnerProfile, LearnerState, now_utc

__all__ = [
    "LearnerModel",
    "SCORED_EVIDENCE_KINDS",
    "LEARNING_RATE",
    "REPEAT_CREDIT_FACTOR",
]

#: Evidence kinds that can move mastery when a score is present.
SCORED_EVIDENCE_KINDS = frozenset(
    {"ANSWER", "CODE_SUBMISSION", "EXPLANATION", "INTERVIEW_RESPONSE", "ASSESSMENT"}
)

#: Bounded running-average learning rate (synthetic, not calibrated).
LEARNING_RATE = 0.35

#: Credit factor applied to every scored observation after the first one for the
#: same task: repeats refresh retention but do not count as fresh transfer.
REPEAT_CREDIT_FACTOR = 0.25


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


class LearnerModel:
    """Evidence-driven, replayable learner state for one synthetic learner."""

    def __init__(self, profile: LearnerProfile):
        if not isinstance(profile, LearnerProfile):
            raise TypeError(f"profile must be LearnerProfile, got {type(profile).__name__}")
        self._profile = profile
        self._mastery: dict[str, float] = {}
        self._error_counts: dict[str, int] = {}
        self._evidence_count = 0
        self._task_skills: dict[str, tuple[str, ...]] = {}
        self._task_scored_observations: dict[str, int] = {}
        self._applied_event_ids: set[str] = set()
        self._last_timestamp: str = ""

    # -- introspection -----------------------------------------------------
    @property
    def profile(self) -> LearnerProfile:
        return self._profile

    @property
    def learner_id(self) -> str:
        return self._profile.learner_id

    def task_skills(self, task_id: str) -> tuple[str, ...]:
        """Skill set bound to ``task_id`` (empty when never observed)."""

        return tuple(self._task_skills.get(task_id, ()))

    def register_task_skills(self, task_id: str, skill_ids: list[str]) -> None:
        """Bind a task to the skills it legitimately evidences.

        Registering the same task again must not silently widen its skill set:
        extra skills are rejected (fail closed) so task->skill mapping stays
        auditable and cannot be used to fake cross-skill transfer.
        """

        if not isinstance(task_id, str) or not task_id.strip():
            raise ValueError("task_id must be a non-empty str")
        if not isinstance(skill_ids, list) or not skill_ids:
            raise ValueError("skill_ids must be a non-empty list[str]")
        normalized: list[str] = []
        for skill in skill_ids:
            if not isinstance(skill, str) or not skill.strip():
                raise ValueError("skill_ids entries must be non-empty str")
            if skill not in normalized:
                normalized.append(skill)
        existing = self._task_skills.get(task_id)
        if existing is None:
            self._task_skills[task_id] = tuple(normalized)
            return
        if set(normalized) - set(existing):
            raise ValueError(
                f"task {task_id!r} is already bound to {existing}; "
                f"cannot widen to {tuple(normalized)}"
            )

    def state(self) -> LearnerState:
        """Return a snapshot copy of the current learner state."""

        return LearnerState(
            learner_id=self.learner_id,
            mastery=dict(self._mastery),
            error_counts=dict(self._error_counts),
            evidence_count=self._evidence_count,
            updated_at=self._last_timestamp or now_utc(),
        )

    # -- evidence application ---------------------------------------------
    def _credit_skills(self, event: EvidenceEvent) -> tuple[str, ...]:
        payload = event.payload
        declared = payload.get("skill_ids")
        if isinstance(declared, str):
            declared = [declared]
        if declared is not None and (
            not isinstance(declared, list)
            or not all(isinstance(skill, str) and skill.strip() for skill in declared)
        ):
            raise ValueError(f"evidence {event.event_id}: payload.skill_ids must be list[str]")
        declared_skills = tuple(dict.fromkeys(declared or ()))
        single = payload.get("skill_id")
        if single is not None:
            if not isinstance(single, str) or not single.strip():
                raise ValueError(f"evidence {event.event_id}: payload.skill_id must be str")
            declared_skills = tuple(dict.fromkeys((*declared_skills, single)))

        bound = self._task_skills.get(event.task_id)
        if bound is None:
            if not declared_skills:
                # No skill signal at all: the event still counts as evidence
                # (and error counts) but cannot move mastery.
                return ()
            self._task_skills[event.task_id] = declared_skills
            return declared_skills
        if not declared_skills:
            return bound
        # Transfer guard: only skills bound to this task are ever credited.
        # Declared skills outside the binding are ignored, never transferred.
        creditable = tuple(skill for skill in declared_skills if skill in bound)
        return creditable

    def apply_evidence(self, event: EvidenceEvent) -> LearnerState:
        """Apply one observed evidence event and return the updated state."""

        if not isinstance(event, EvidenceEvent):
            raise TypeError(f"event must be EvidenceEvent, got {type(event).__name__}")
        if event.learner_id != self.learner_id:
            raise ValueError(
                f"evidence learner_id={event.learner_id!r} does not match "
                f"model learner_id={self.learner_id!r}"
            )
        if event.event_id in self._applied_event_ids:
            return self.state()

        credited_skills = self._credit_skills(event)
        scored = event.kind in SCORED_EVIDENCE_KINDS and event.observed_score is not None
        if scored:
            repeat_index = self._task_scored_observations.get(event.task_id, 0)
            credit_factor = 1.0 if repeat_index == 0 else REPEAT_CREDIT_FACTOR
            target = _clamp01(float(event.observed_score))
            # Fail-closed rule: evidence carrying error codes is a failed/partial
            # attempt.  It may pull mastery down toward the observed score but can
            # never push it up (failure is not proof of improvement).
            failed_attempt = bool(event.error_codes)
            for skill in credited_skills:
                previous = self._mastery.get(skill, 0.0)
                effective_target = min(target, previous) if failed_attempt else target
                updated = previous + LEARNING_RATE * credit_factor * (
                    effective_target - previous
                )
                self._mastery[skill] = round(_clamp01(updated), 6)
            self._task_scored_observations[event.task_id] = repeat_index + 1

        for code in event.error_codes:
            self._error_counts[code] = self._error_counts.get(code, 0) + 1

        self._evidence_count += 1
        self._applied_event_ids.add(event.event_id)
        if event.created_at:
            self._last_timestamp = event.created_at
        return self.state()

    def replay(self, events: list[EvidenceEvent]) -> LearnerState:
        """Replay ``events`` in order from a clean model and return the state."""

        if not isinstance(events, list):
            raise TypeError(f"events must be list[EvidenceEvent], got {type(events).__name__}")
        self._mastery = {}
        self._error_counts = {}
        self._evidence_count = 0
        self._task_skills = {}
        self._task_scored_observations = {}
        self._applied_event_ids = set()
        self._last_timestamp = ""
        for event in events:
            self.apply_evidence(event)
        return self.state()
