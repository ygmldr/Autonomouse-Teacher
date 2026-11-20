"""Next-phase interface stubs for the M1-A teacher (B-PR5, M1_NEXT_PHASE_PLAN).

These are **contracts only**: frozen, importable, offline Protocols plus
lightweight value objects for the next phase (Web App, Interview Coach,
Knowledge Freshness, Autonomous Research, Teacher Improvement experiments).

Nothing here connects to a network, reads credentials or claims an
implementation exists.  Every concrete stub deliberately raises
``UnsupportedOperationError`` so a caller can never mistake a stub for a working
integration.  The interfaces are additive and do not change the frozen
``m1a.v0`` contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from ..contracts.errors import UnsupportedOperationError
from ..contracts.types import LearningObjective

__all__ = [
    "EXTENSION_CONTRACT_VERSION",
    "WebAppPort",
    "InterviewCoachPort",
    "KnowledgeFreshnessPort",
    "AutonomousResearchPort",
    "TeacherImprovementStore",
    "ResearchTaskSpec",
    "KnowledgeFreshnessRequest",
    "TeacherExperimentRecord",
    "StubNotImplementedError",
    "NotConfiguredWebApp",
    "NotConfiguredInterviewCoach",
    "NotConfiguredKnowledgeFreshness",
    "NotConfiguredAutonomousResearch",
    "InMemoryTeacherImprovementLog",
]

EXTENSION_CONTRACT_VERSION = "m1a.extensions.v0"
"""Additive next-phase contract version (does not change ``m1a.v0``)."""


class StubNotImplementedError(UnsupportedOperationError):
    """Raised by an intentionally unimplemented next-phase stub."""

    code = "EXTENSION_NOT_IMPLEMENTED"


# ---------------------------------------------------------------------------
# Web App
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class WebSessionView:
    """Read-only view of a teaching session for a future web front end."""

    session_id: str
    learner_id: str
    phase: str
    turn_index: int
    pending_item_id: str | None
    next_action_kind: str | None


@runtime_checkable
class WebAppPort(Protocol):
    """Structural contract for a future offline web front end (stub only)."""

    def session_view(self, session_id: str) -> WebSessionView:
        """Return a read-only session view."""

    def submit(self, session_id: str, item_id: str, response: str) -> dict[str, Any]:
        """Submit one response through the existing engine (stub only)."""


# ---------------------------------------------------------------------------
# Interview Coach
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class InterviewTurnRequest:
    """One interview-coach turn request (next phase; stub only)."""

    learner_id: str
    question_id: str
    answer_text: str
    untrusted_context: tuple[str, ...] = ()


@runtime_checkable
class InterviewCoachPort(Protocol):
    """Structural contract for the next-phase interview coach (stub only)."""

    def start(self, learner_id: str, objective: LearningObjective) -> InterviewTurnRequest:
        """Return the first interview turn for a learner."""

    def assess_answer(self, request: InterviewTurnRequest) -> dict[str, Any]:
        """Return a deterministic assessment payload for one answer."""


# ---------------------------------------------------------------------------
# Knowledge freshness
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class KnowledgeFreshnessRequest:
    """Re-observation request for the next-phase knowledge freshness service."""

    source_id: str
    uri: str
    observed_at: str
    claim_status: str = "UNKNOWN"


@runtime_checkable
class KnowledgeFreshnessPort(Protocol):
    """Structural contract for versioned knowledge freshness (stub only)."""

    def classify(self, request: KnowledgeFreshnessRequest) -> dict[str, Any]:
        """Return ``KEEP``/``UPDATE``/``RECHECK`` with a structured reason."""


# ---------------------------------------------------------------------------
# Autonomous research (contract only; never online in M1-A)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ResearchTaskSpec:
    """Offline contract for a future autonomous-research task.

    ``allowed_sources`` is an explicit allow-list; ``requires_network`` is fixed
    to ``False`` in M1-A so a stub can never be mistaken for an online crawler.
    """

    task_id: str
    question: str
    allowed_sources: tuple[str, ...] = ()
    max_steps: int = 8
    requires_network: bool = False
    evidence_refs: tuple[str, ...] = ()


@runtime_checkable
class AutonomousResearchPort(Protocol):
    """Structural contract for offline research planning (stub only)."""

    def plan_task(self, objective: LearningObjective) -> ResearchTaskSpec:
        """Return a deterministic offline research task specification."""

    def collect_evidence(self, task: ResearchTaskSpec) -> list[str]:
        """Return offline evidence references for a task (stub only)."""


# ---------------------------------------------------------------------------
# Teacher improvement experiment log
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class TeacherExperimentRecord:
    """One recorded teacher-improvement experiment (policy/state/behaviour/result)."""

    experiment_id: str
    policy_version: str
    initial_state_digest: str
    behaviour_digest: str
    result_digest: str
    notes: tuple[str, ...] = field(default_factory=tuple)
    evidence_class: str = "DETERMINISTIC"
    real_effect_claim: bool = False


@runtime_checkable
class TeacherImprovementStore(Protocol):
    """Structural contract for teacher-improvement experiment records (stub only)."""

    def record(self, record: TeacherExperimentRecord) -> None:
        """Append one experiment record."""

    def list_records(self) -> list[TeacherExperimentRecord]:
        """Return records in append order."""


# ---------------------------------------------------------------------------
# Explicit not-configured stubs (never silently succeed)
# ---------------------------------------------------------------------------
class _NotConfigured:
    """Base stub: every operation fails closed with ``EXTENSION_NOT_IMPLEMENTED``."""

    component = "extension"

    def _raise(self, operation: str) -> None:
        raise StubNotImplementedError(
            f"{self.component}.{operation}: next-phase interface stub is not implemented "
            "in M1-A (contract only)",
            details={"component": self.component, "operation": operation},
        )


class NotConfiguredWebApp(_NotConfigured):
    component = "web_app"

    def session_view(self, session_id: str) -> WebSessionView:
        self._raise("session_view")

    def submit(self, session_id: str, item_id: str, response: str) -> dict[str, Any]:
        self._raise("submit")


class NotConfiguredInterviewCoach(_NotConfigured):
    component = "interview_coach"

    def start(self, learner_id: str, objective: LearningObjective) -> InterviewTurnRequest:
        self._raise("start")

    def assess_answer(self, request: InterviewTurnRequest) -> dict[str, Any]:
        self._raise("assess_answer")


class NotConfiguredKnowledgeFreshness(_NotConfigured):
    component = "knowledge_freshness"

    def classify(self, request: KnowledgeFreshnessRequest) -> dict[str, Any]:
        self._raise("classify")


class NotConfiguredAutonomousResearch(_NotConfigured):
    component = "autonomous_research"

    def plan_task(self, objective: LearningObjective) -> ResearchTaskSpec:
        self._raise("plan_task")

    def collect_evidence(self, task: ResearchTaskSpec) -> list[str]:
        self._raise("collect_evidence")


class InMemoryTeacherImprovementLog:
    """Minimal deterministic in-memory experiment log (contract smoke only)."""

    def __init__(self) -> None:
        self._records: list[TeacherExperimentRecord] = []

    def record(self, record: TeacherExperimentRecord) -> None:
        if not isinstance(record, TeacherExperimentRecord):
            raise UnsupportedOperationError(
                "InMemoryTeacherImprovementLog.record(): expected a TeacherExperimentRecord"
            )
        if record.real_effect_claim:
            raise UnsupportedOperationError(
                "InMemoryTeacherImprovementLog.record(): real_effect_claim must stay False "
                "for M1-A (no real teaching effect claims)"
            )
        self._records.append(record)

    def list_records(self) -> list[TeacherExperimentRecord]:
        return list(self._records)
