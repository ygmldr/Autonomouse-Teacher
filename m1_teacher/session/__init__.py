"""Teaching-session state-machine package of the M1-A teacher (B-PR4).

Public surface:

* :class:`~m1_teacher.session.engine.TeachingSessionEngine` — persistent
  ``DIAGNOSE -> TEACH -> PRACTICE -> ASSESS -> UPDATE -> REVIEW`` state machine
  with ``COMPLETE``/``PAUSED`` terminals, pause/resume, idempotent response
  submission and independent-scorer-driven mastery updates.
* :class:`~m1_teacher.session.engine.SessionPolicy` — deterministic, injectable
  transition thresholds.
"""

from __future__ import annotations

from .engine import (
    SESSION_POLICY_VERSION,
    SessionPolicy,
    TeachingSessionEngine,
)

__all__ = [
    "TeachingSessionEngine",
    "SessionPolicy",
    "SESSION_POLICY_VERSION",
]
