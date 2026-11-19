"""CF Teacher package: algorithm-problem tutoring over a hidden-test judge.

Public surface (shared B-line contract):

* :class:`~m1_offline.cf.judge.CFJudge` /
  :class:`~m1_offline.cf.judge.JudgeResult` -- isolated local execution of
  learner code against hidden tests only.
* :class:`~m1_offline.cf.teacher.CFTeacher` -- ``diagnose`` / ``next_action`` /
  ``assess`` for algorithm problems, using the shared M1 types and the b-core
  hint-ladder policy.

The package is offline and synthetic-only: no network, no provider, no M0
import.  See ``docs/m1/CF_TEACHER_SPEC.md`` for the full contract.
"""

from __future__ import annotations

from .judge import CFJudge, DEFAULT_TIMEOUT_S, JUDGE_VERSION, JudgeResult
from .teacher import (
    CF_ERROR_CODES,
    CFTeacher,
    DEFAULT_HINT_LEVEL,
    MAX_DEFAULT_HINT_LEVEL,
    SCORER_ID,
)

__all__ = [
    "CFJudge",
    "JudgeResult",
    "JUDGE_VERSION",
    "DEFAULT_TIMEOUT_S",
    "CFTeacher",
    "SCORER_ID",
    "CF_ERROR_CODES",
    "DEFAULT_HINT_LEVEL",
    "MAX_DEFAULT_HINT_LEVEL",
]
