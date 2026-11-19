"""Interview Coach + independent rubric (M1 Offline Teacher, ``m1.offline.v0``).

Owned by b-interview.  Public surface consumed by other M1 modules
(``b-eval`` etc.) is intentionally limited to:

* :class:`~m1_offline.interview.coach.InterviewCoach`
  (``start`` / ``follow_up`` / ``assess_answer`` / ``system_instructions``)
* :class:`~m1_offline.interview.rubric.InterviewRubric`
  (``score`` / ``feedback`` / ``failure_modes``)
* :data:`~m1_offline.interview.coach.LADDER_STAGES` and
  :data:`~m1_offline.interview.rubric.SCORER_ID`

The rubric is dependency-free (stdlib only).  The coach depends only on
``m1_offline.types`` / ``m1_offline.runtime_port`` and never calls the runtime.
"""

from __future__ import annotations

from .coach import LADDER_STAGES, STAGE_LABELS, InterviewCoach
from .rubric import DIMENSIONS, FAILURE_MODES, SCORER_ID, InterviewRubric

__all__ = [
    "DIMENSIONS",
    "FAILURE_MODES",
    "LADDER_STAGES",
    "SCORER_ID",
    "STAGE_LABELS",
    "InterviewCoach",
    "InterviewRubric",
]
