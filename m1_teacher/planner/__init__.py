"""Curriculum-planner package of the M1-A teacher core (B4).

Public surface: :class:`CurriculumPlanner` (ordered, explainable
:class:`~m1_teacher.contracts.types.CurriculumPlan` with a structured
:class:`~m1_teacher.contracts.types.Reason` per step) and
:class:`PlannerPolicy` (deterministic, injectable thresholds).
"""

from __future__ import annotations

from .planner import (
    POLICY_VERSION,
    CurriculumPlanner,
    PlannerPolicy,
    REASON_GOAL_COMPLETE,
    REASON_GOAL_NOT_COMPLETE,
)

__all__ = [
    "CurriculumPlanner",
    "PlannerPolicy",
    "POLICY_VERSION",
    "REASON_GOAL_COMPLETE",
    "REASON_GOAL_NOT_COMPLETE",
]
