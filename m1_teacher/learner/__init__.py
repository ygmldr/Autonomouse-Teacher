"""Learner model, learning history and SQLite persistence (B-PR2).

Public surface:

* :class:`~m1_teacher.learner.model.MasteryPolicy` — frozen constants of the
  deterministic heuristic.
* :class:`~m1_teacher.learner.model.MasteryModel` — observed-evidence mastery
  updates and deterministic rebuild from history events.
* :class:`~m1_teacher.learner.history.LearningHistory` — append-only event log
  orchestration, idempotent assessment application and rebuild verification.
* :class:`~m1_teacher.learner.repository.SqliteRepository` — stdlib SQLite
  implementation of the frozen ``LearnerRepository``/``SessionRepository``
  protocols plus atomic state + history extensions.

Everything here is offline and deterministic: no network, no API keys, no M0
imports and no wall-clock reads inside the update formulas (timestamps are
copied from assessment evidence; only freshly appended generic events are
timestamped with the current UTC time).
"""

from __future__ import annotations

from .history import LearningHistory
from .model import (
    EPOCH_TIMESTAMP,
    OBSERVED_EVIDENCE,
    MasteryModel,
    MasteryPolicy,
    applied_result_ids,
)
from .repository import SCHEMA_VERSION as DB_SCHEMA_VERSION
from .repository import SqliteRepository

__all__ = [
    "EPOCH_TIMESTAMP",
    "OBSERVED_EVIDENCE",
    "DB_SCHEMA_VERSION",
    "LearningHistory",
    "MasteryModel",
    "MasteryPolicy",
    "SqliteRepository",
    "applied_result_ids",
]
