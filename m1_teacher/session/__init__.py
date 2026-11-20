"""Teaching-session state-machine package of the M1-A teacher (B-PR4 / B-NEXT).

Public surface:

* :class:`~m1_teacher.session.engine.TeachingSessionEngine` — persistent
  ``DIAGNOSE -> TEACH -> PRACTICE -> ASSESS -> UPDATE -> REVIEW`` state machine
  with ``COMPLETE``/``PAUSED`` terminals, pause/resume, idempotent response
  submission, B-NEXT two-phase transactional assessment turns
  (``ASSESSMENT_PREPARED`` -> external scorer -> terminal commit) and real
  crash recovery (:meth:`~m1_teacher.session.engine.TeachingSessionEngine.recover_session`).
* :class:`~m1_teacher.session.engine.SessionPolicy` — deterministic, injectable
  transition thresholds.
* :class:`~m1_teacher.session.engine.RecoveryReport` — explainable outcome of
  crash recovery (idempotent; never reports false completion).
"""

from __future__ import annotations

from .engine import (
    SESSION_POLICY_VERSION,
    RecoveryReport,
    SessionPolicy,
    TeachingSessionEngine,
)

__all__ = [
    "TeachingSessionEngine",
    "SessionPolicy",
    "RecoveryReport",
    "SESSION_POLICY_VERSION",
]
