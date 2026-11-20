"""Persistence protocols for the frozen M1-A teacher (``m1a.v0``).

These are structural Protocols only; the SQLite implementation lands in
B-PR2 (``m1_teacher/learner/repository.py``).  Keeping the protocols here
freezes the contract that B-PR2/B-PR4/B-PR5 code is written against.

Semantics required of implementations (see ``docs/M1_ARCHITECTURE.md``):

* ``append_event`` is idempotent on ``HistoryEvent.event_id``: re-appending an
  existing event returns ``False`` and must not duplicate history or bump
  sequence numbers.
* ``list_events`` returns events for one learner ordered by ascending
  ``seq``; ``since_seq`` (inclusive lower bound) supports incremental replay.
* learner snapshots must be rebuildable from the event log; repositories may
  cache materialised snapshots but the event log is the source of truth.
* invalid input fails closed with ``ValidationError``; unknown lookups return
  ``None`` (they are not errors for the ``get_*`` methods).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .types import HistoryEvent, LearnerGoal, LearnerSnapshot, SessionState

__all__ = ["LearnerRepository", "SessionRepository"]


@runtime_checkable
class LearnerRepository(Protocol):
    """Learner state, goal and append-only event-log persistence."""

    def get_snapshot(self, learner_id: str) -> LearnerSnapshot | None:
        """Return the current materialised snapshot, or ``None`` if unknown."""

    def upsert_snapshot(self, snapshot: LearnerSnapshot) -> None:
        """Insert or replace the snapshot for ``snapshot.learner_id``."""

    def append_event(self, event: HistoryEvent) -> bool:
        """Append an event; return ``False`` if ``event.event_id`` already exists."""

    def get_event(self, event_id: str) -> HistoryEvent | None:
        """Return one event by idempotency key, or ``None`` if unknown."""

    def list_events(
        self, learner_id: str, since_seq: int | None = None
    ) -> list[HistoryEvent]:
        """Return a learner's events in ascending ``seq`` order."""

    def get_goal(self, goal_id: str) -> LearnerGoal | None:
        """Return one goal by id, or ``None`` if unknown."""

    def upsert_goal(self, goal: LearnerGoal) -> None:
        """Insert or replace a learner goal."""


@runtime_checkable
class SessionRepository(Protocol):
    """Session-state persistence (pause/resume/restart recovery)."""

    def save_session(self, state: SessionState) -> None:
        """Insert or replace a session state."""

    def load_session(self, session_id: str) -> SessionState | None:
        """Return a session state by id, or ``None`` if unknown."""

    def list_sessions(self, learner_id: str) -> list[SessionState]:
        """Return a learner's sessions (stable order: newest first by caller choice)."""
