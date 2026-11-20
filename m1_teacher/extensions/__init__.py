"""Next-phase extension interface stubs for the M1-A teacher (B-PR5).

Importable, offline, contract-only interfaces for the next phase; the frozen
``m1a.v0`` contract is unchanged.  See :mod:`m1_teacher.extensions.interfaces`.
"""

from __future__ import annotations

from .interfaces import (
    EXTENSION_CONTRACT_VERSION,
    AutonomousResearchPort,
    InMemoryTeacherImprovementLog,
    InterviewCoachPort,
    InterviewTurnRequest,
    KnowledgeFreshnessPort,
    KnowledgeFreshnessRequest,
    NotConfiguredAutonomousResearch,
    NotConfiguredInterviewCoach,
    NotConfiguredKnowledgeFreshness,
    NotConfiguredWebApp,
    ResearchTaskSpec,
    StubNotImplementedError,
    TeacherExperimentRecord,
    TeacherImprovementStore,
    WebAppPort,
    WebSessionView,
)

__all__ = [
    "EXTENSION_CONTRACT_VERSION",
    "AutonomousResearchPort",
    "InMemoryTeacherImprovementLog",
    "InterviewCoachPort",
    "InterviewTurnRequest",
    "KnowledgeFreshnessPort",
    "KnowledgeFreshnessRequest",
    "NotConfiguredAutonomousResearch",
    "NotConfiguredInterviewCoach",
    "NotConfiguredKnowledgeFreshness",
    "NotConfiguredWebApp",
    "ResearchTaskSpec",
    "StubNotImplementedError",
    "TeacherExperimentRecord",
    "TeacherImprovementStore",
    "WebAppPort",
    "WebSessionView",
]
