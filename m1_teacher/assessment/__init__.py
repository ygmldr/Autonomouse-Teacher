"""Independent assessment scoring package of the M1-A teacher (B-PR4).

Public surface:

* :class:`~m1_teacher.assessment.scorer.AssessmentScorer` — structural protocol
  every scorer implementation must satisfy.
* :class:`~m1_teacher.assessment.scorer.DeterministicScorer` — offline scorer
  for MCQ / CODE / SHORT_ANSWER items, the only component allowed to read the
  hidden scoring specifications.

The scorer returns observed evidence only: learner mistakes are
``INCORRECT``/``PARTIAL``; scoring-infrastructure failures are ``EVAL_ERROR``
and are never treated as evidence about the learner.
"""

from __future__ import annotations

from .scorer import (
    SCORER_ID_DEFAULT,
    AssessmentScorer,
    DeterministicScorer,
)

__all__ = [
    "AssessmentScorer",
    "DeterministicScorer",
    "SCORER_ID_DEFAULT",
]
