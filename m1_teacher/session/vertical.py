"""Additive vertical-domain policy seam for the teaching-session engine (B-PR4).

The frozen ``m1a.v0`` session state machine is CF/domain-agnostic and only knows
one item/one scored response per turn.  B-PR4 adds a small, **additive** seam:

* :class:`VerticalPolicy` — optional per-engine policy.  When an engine is
  constructed with ``vertical_policy=None`` (default) every existing CF code
  path is byte-for-byte unchanged.  When supplied, the engine asks the policy
  for (a) session-start validation, (b) the next teaching action, (c) the
  result-transition override for multi-turn verticals and (d) additive event
  payload metadata.  The domain never writes learner state, never writes the
  event log and never reads hidden scoring material.
* :class:`InterviewVerticalPolicy` — the Interview vertical implementation:
  - five-stage Socratic follow-up ladder
    (``concept -> hypothesis -> complexity -> experiment_design -> online_triage``)
    persisted via ``ACTION_TAKEN``/``ASSESSED`` payloads only (no new
    ``SessionState`` fields);
  - learner-state-driven stage selection (prior observed mastery/evidence can
    accelerate the ladder by skipping the concept probe), deterministic;
  - ``ASK_CLARIFICATION`` when the question requires learner-owned project facts
    and the answer could not be verified (never fabricate facts);
  - an **interview-only** support ladder ``LIGHT -> INVARIANT -> STRUCTURE``
    (distinct from the CF hint ladder; ``FULL`` is disabled by default and only
    reachable through an explicit human-approval gate);
  - JD-window and knowledge-freshness gates at session start: expired/conflicting
    JDs and RECHECK/conflict/unauthoritative knowledge decisions fail closed with
    the stable ``MAP-E`` codes before any event/session is written.
* :class:`InterviewJudgeScorer` — adapts the scorer-side
  :class:`~m1_teacher.assessment.interview_judge.InterviewRubricJudge` to the
  frozen ``AssessmentScorer`` protocol; the judge's four-dimension sidecar is
  attached to the assessment event payloads as ``rubric_audit`` (dimensions +
  digest only, never hidden expectation text).

All state remains in the canonical event log (single writer: the engine's
``LearningHistory``/repository); replay is unchanged except that it skips the
additive payload keys.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

from ..assessment.interview_judge import InterviewAssessmentDetail, InterviewRubricJudge
from ..contracts.errors import NotFoundError, ValidationError
from ..contracts.types import (
    AssessmentItem,
    AssessmentResult,
    HistoryEvent,
    LearnerGoal,
    LearnerSnapshot,
    LearningObjective,
    Reason,
    SessionState,
    TeachingAction,
)
from ..domains.interview import FOLLOW_UP_STAGES, InterviewDomainAdapter
from ..knowledge.freshness import FreshnessDecision, KnowledgeFreshnessService

__all__ = [
    "ACCELERATED_MASTERY_THRESHOLD",
    "ACCELERATED_MIN_EVIDENCE",
    "FULL_MIN_EVIDENCE",
    "INTERVIEW_HINT_LADDER",
    "INTERVIEW_HINT_REASON_CODES",
    "MAX_INTERVIEW_HINT_LEVEL",
    "VERTICAL_POLICY_VERSION",
    "InterviewJudgeScorer",
    "InterviewVerticalPolicy",
    "VerticalActionContext",
    "VerticalPolicy",
    "VerticalSelection",
    "VerticalTransition",
    "VerticalTransitionContext",
]

VERTICAL_POLICY_VERSION = "b4.interview.policy.v1"

#: Interview-only support ladder.  Distinct from the CF hint ladder: it is
#: emitted only by the interview vertical policy, uses its own reason-code
#: namespace and can never escalate to ``FULL`` by default.
INTERVIEW_HINT_LADDER: tuple[str, ...] = ("LIGHT", "INVARIANT", "STRUCTURE", "FULL")
INTERVIEW_HINT_REASON_CODES: dict[str, str] = {
    "LIGHT": "INTERVIEW_HINT_LEVEL_1",
    "INVARIANT": "INTERVIEW_HINT_LEVEL_2",
    "STRUCTURE": "INTERVIEW_HINT_LEVEL_3",
    "FULL": "INTERVIEW_HINT_LEVEL_4",
}
MAX_INTERVIEW_HINT_LEVEL = 3
FULL_MIN_EVIDENCE = 5

#: Learner-state acceleration: with this much observed node mastery/evidence the
#: concept probe is skipped (deterministic, frozen per session at session start).
ACCELERATED_MASTERY_THRESHOLD = 0.25
ACCELERATED_MIN_EVIDENCE = 2

# Session phases used by the vertical seam (subset of the frozen enum).
_PHASE_ASSESS = "ASSESS"
_PHASE_REVIEW = "REVIEW"

_MAIN_REASON_CODE = "INTERVIEW_MAIN_QUESTION"
_PROBE_REASON_PREFIX = "INTERVIEW_PROBE_"
_CLARIFY_REASON_CODE = "PROJECT_FACTS_REQUIRED"
_ACTIVE_STATUSES = frozenset({"CORRECT", "INCORRECT", "PARTIAL"})
_ADVANCING_STATUSES = frozenset({"CORRECT", "PARTIAL"})
_TERMINAL_EVENT_TYPES = frozenset({"ASSESSED", "ERROR"})


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VerticalActionContext:
    """Read-only context for :meth:`VerticalPolicy.select_action`."""

    state: SessionState
    snapshot: LearnerSnapshot
    events: tuple[HistoryEvent, ...]
    item: AssessmentItem | None
    goal: LearnerGoal
    objective: LearningObjective


@dataclass(frozen=True)
class VerticalTransitionContext:
    """Read-only context for :meth:`VerticalPolicy.plan_transition`."""

    state: SessionState
    snapshot: LearnerSnapshot
    events: tuple[HistoryEvent, ...]
    item: AssessmentItem
    result: AssessmentResult
    goal: LearnerGoal
    objective: LearningObjective


@dataclass(frozen=True)
class VerticalSelection:
    """Next vertical action (the engine persists it as ``ACTION_TAKEN``)."""

    action: TeachingAction
    phase: str
    pending_item_id: str | None
    extra_events: tuple[tuple[str, dict[str, Any]], ...] = ()


@dataclass(frozen=True)
class VerticalTransition:
    """Session-state override after one scored vertical turn."""

    phase: str
    pending_item_id: str | None


@runtime_checkable
class VerticalPolicy(Protocol):
    """Additive session-engine policy for one vertical domain."""

    domain_id: str
    policy_version: str

    def validate_session_start(
        self,
        *,
        learner_id: str,
        goal: LearnerGoal,
        objective: LearningObjective,
        snapshot: LearnerSnapshot,
        session_id: str,
    ) -> None:
        """Fail closed *before* the first session/event write."""

    def select_action(self, context: VerticalActionContext) -> VerticalSelection | None:
        """Return the next vertical action, or ``None`` to defer to the core engine."""

    def plan_transition(
        self, context: VerticalTransitionContext
    ) -> VerticalTransition | None:
        """Override the post-assessment session transition (multi-turn verticals)."""

    def session_event_payload(self) -> dict[str, Any]:
        """Additive metadata merged into ``SESSION_STARTED``."""

    def plan_event_payload(self) -> dict[str, Any]:
        """Additive metadata merged into ``PLAN_CREATED``."""

    def action_event_payload(
        self, action: TeachingAction, state: SessionState
    ) -> dict[str, Any]:
        """Additive metadata merged into ``ACTION_TAKEN``."""

    def assessment_payload_extra(self, result: AssessmentResult) -> dict[str, Any] | None:
        """Additive metadata merged into ``ASSESSED``/``MASTERY_UPDATED``."""


# ---------------------------------------------------------------------------
# Scorer adapter (assessment-port semantics for the vertical judge)
# ---------------------------------------------------------------------------


class InterviewJudgeScorer:
    """Adapt :class:`InterviewRubricJudge` to the frozen ``AssessmentScorer`` protocol.

    The judge is scorer-side only: this adapter passes the teacher-visible
    :class:`AssessmentItem` + learner response and returns an
    :class:`AssessmentResult`; it never exposes rubric expectations or hidden
    answers to the engine.
    """

    def __init__(self, judge: InterviewRubricJudge) -> None:
        if not isinstance(judge, InterviewRubricJudge):
            raise ValidationError(
                "InterviewJudgeScorer(judge=...): expected an InterviewRubricJudge"
            )
        self._judge = judge

    @property
    def scorer_id(self) -> str:
        return self._judge.scorer_id

    @property
    def judge(self) -> InterviewRubricJudge:
        return self._judge

    def score(
        self,
        item: AssessmentItem,
        learner_id: str,
        response: str | dict,
        *,
        result_id: str | None = None,
    ) -> AssessmentResult:
        """Score one response through the independent interview rubric judge."""

        return self._judge.assess(
            item, learner_id, response, result_id=result_id
        )

    def detail(self, result_id: str) -> InterviewAssessmentDetail | None:
        return self._judge.detail(result_id)


# ---------------------------------------------------------------------------
# Interview vertical policy
# ---------------------------------------------------------------------------


class InterviewVerticalPolicy:
    """Deterministic five-stage interview policy for the canonical session engine."""

    domain_id = "interview_coach"
    policy_version = VERTICAL_POLICY_VERSION

    def __init__(
        self,
        domain: InterviewDomainAdapter,
        judge: InterviewRubricJudge,
        freshness: KnowledgeFreshnessService,
        *,
        question_id: str,
        jd_id: str = "jd:rec",
        now: str = "2026-07-01T00:00:00Z",
        knowledge_decisions: Sequence[FreshnessDecision] = (),
        human_approved_full: bool = False,
    ) -> None:
        if not isinstance(domain, InterviewDomainAdapter):
            raise ValidationError(
                "InterviewVerticalPolicy(domain=...): expected an InterviewDomainAdapter"
            )
        if not isinstance(judge, InterviewRubricJudge):
            raise ValidationError(
                "InterviewVerticalPolicy(judge=...): expected an InterviewRubricJudge"
            )
        if not isinstance(freshness, KnowledgeFreshnessService):
            raise ValidationError(
                "InterviewVerticalPolicy(freshness=...): expected a KnowledgeFreshnessService"
            )
        if type(question_id) is not str or not question_id.strip():
            raise ValidationError("InterviewVerticalPolicy(question_id=...): non-blank str required")
        if type(jd_id) is not str or not jd_id.strip():
            raise ValidationError("InterviewVerticalPolicy(jd_id=...): non-blank str required")
        if human_approved_full is not False:
            # M1-B has no human-approval workflow; wiring a True flag is refused.
            raise ValidationError(
                "InterviewVerticalPolicy(human_approved_full=True) is not available in M1-B "
                "(no human approval workflow); FULL solution stays disabled",
                code="MAP-E11_FULL_SOLUTION_FORBIDDEN",
            )
        item = next(
            (candidate for candidate in domain.assessment_items() if candidate.item_id == question_id),
            None,
        )
        if item is None:
            raise NotFoundError(
                f"InterviewVerticalPolicy: unknown interview item {question_id!r}"
            )
        self._domain = domain
        self._judge = judge
        self._freshness = freshness
        self._item = item
        self._question_id = item.item_id
        self._jd_id = jd_id
        self._now = now
        self._human_approved_full = False
        decisions = list(knowledge_decisions)
        for index, decision in enumerate(decisions):
            if not isinstance(decision, FreshnessDecision):
                raise ValidationError(
                    f"InterviewVerticalPolicy(knowledge_decisions[{index}]): expected a "
                    "FreshnessDecision"
                )
        self._knowledge_decisions = decisions
        self._jd_gate = freshness.active_jd(jd_id, now)
        self._stages_by_session: dict[str, tuple[str, ...]] = {}
        self._target_node_id = item.node_ids[0] if item.node_ids else ""

    # -- read-only properties ---------------------------------------------
    @property
    def question_id(self) -> str:
        return self._question_id

    @property
    def target_node_id(self) -> str:
        return self._target_node_id

    @property
    def active_jd_version(self) -> str | None:
        return self._jd_gate.active_version

    @property
    def jd_id(self) -> str:
        return self._jd_id

    @property
    def human_approved_full(self) -> bool:
        return self._human_approved_full

    # -- gates -------------------------------------------------------------
    def validate_session_start(
        self,
        *,
        learner_id: str,
        goal: LearnerGoal,
        objective: LearningObjective,
        snapshot: LearnerSnapshot,
        session_id: str,
    ) -> None:
        """Fail closed before any event/session write: domain/JD/knowledge gates."""

        if not isinstance(goal, LearnerGoal) or not isinstance(objective, LearningObjective):
            raise ValidationError("validate_session_start(): expected LearnerGoal/LearningObjective")
        if not isinstance(snapshot, LearnerSnapshot):
            raise ValidationError("validate_session_start(): expected a LearnerSnapshot")
        if objective.domain_id != self.domain_id or goal.objective_id != objective.objective_id:
            raise ValidationError(
                "validate_session_start(): objective/domain does not belong to the interview vertical",
                code="VERTICAL_DOMAIN_MISMATCH",
            )
        if self._target_node_id not in objective.target_node_ids:
            raise ValidationError(
                "validate_session_start(): interview question node is not covered by the objective",
                code="VERTICAL_OBJECTIVE_MISMATCH",
            )
        gate = self._freshness.active_jd(self._jd_id, self._now)
        if not gate.allowed_for_new_plan:
            raise ValidationError(
                "interview session start blocked by the JD gate: "
                f"{gate.reason_code}",
                code="FRESHNESS_JD_GATE_BLOCKED",
                details={
                    "jd_id": self._jd_id,
                    "now": self._now,
                    "reason_code": gate.reason_code,
                    "map_code": gate.map_code,
                    "active_version": gate.active_version,
                },
            )
        self._jd_gate = gate
        for index, decision in enumerate(self._knowledge_decisions):
            # KEEP requires no curriculum change and is benign; UPDATE is allowed
            # only when the freshness gate says it is writable; every RECHECK
            # (conflict/expired/unauthoritative/future-dated/ambiguous) is rejected
            # *before* any session/event is written.
            if decision.change_kind == "KEEP":
                continue
            if self._freshness.curriculum_eligible(decision):
                continue
            raise ValidationError(
                "interview session start blocked by the knowledge freshness gate: "
                f"{decision.reason_code}",
                code="FRESHNESS_KNOWLEDGE_GATE_BLOCKED",
                details={
                    "decision_index": index,
                    "source_id": decision.source_id,
                    "reason_code": decision.reason_code,
                    "map_code": decision.map_code,
                    "change_kind": decision.change_kind,
                    "recheck_required": decision.recheck_required,
                },
            )
        stages = tuple(self._stages_for_snapshot(snapshot))
        self._stages_by_session[session_id] = stages

    # -- engine hooks ------------------------------------------------------
    def select_action(self, context: VerticalActionContext) -> VerticalSelection | None:
        session_events = self._session_events(context)
        if self._unresolved_prepared(session_events):
            return None  # let the engine's retry/recovery path handle the pending attempt
        statuses = self._assessed_statuses(session_events)
        if not statuses:
            return self._main_selection(context)
        last_status = statuses[-1]
        if last_status == "NEEDS_REVIEW":
            if not self._requires_project_facts():
                # Non-project questions: a NEEDS_REVIEW answer is not an evidence
                # verdict; defer to the engine's retry/plan path (no fabrication).
                return None
            clarifications = self._actions_since_last_assessment(
                session_events, _CLARIFY_REASON_CODE
            )
            if clarifications < 2:
                return self._clarify_selection(context)
            return None
        if last_status == "INCORRECT":
            return self._hint_selection(context, statuses)
        advancing = sum(1 for status in statuses if status in _ADVANCING_STATUSES)
        stages = self._stages(context.state.session_id)
        stage_index = advancing - 1
        if stage_index < len(stages):
            return self._probe_selection(context, stages[stage_index])
        return None

    def plan_transition(self, context: VerticalTransitionContext) -> VerticalTransition | None:
        # NOTE: unlike select_action, the transactional commit path calls this
        # *before* the terminal ASSESSED/ERROR events are committed (the durable
        # PREPARED attempt is expected here), so no unresolved-prepared guard.
        session_events = self._session_events_from(context.state, context.events)
        if context.item.item_id != self._question_id:
            return None
        if context.result.status == "EVAL_ERROR":
            return None
        if context.result.status == "NEEDS_REVIEW":
            return VerticalTransition(phase=_PHASE_ASSESS, pending_item_id=self._question_id)
        statuses = self._assessed_statuses(session_events)
        advancing = sum(1 for status in statuses if status in _ADVANCING_STATUSES)
        if context.result.status in _ADVANCING_STATUSES:
            advancing += 1
        stages = self._stages(context.state.session_id)
        if advancing >= 1 + len(stages):
            return VerticalTransition(phase=_PHASE_REVIEW, pending_item_id=None)
        return VerticalTransition(phase=_PHASE_ASSESS, pending_item_id=self._question_id)

    # -- payload metadata --------------------------------------------------
    def session_event_payload(self) -> dict[str, Any]:
        return {
            "vertical": {
                "domain_id": self.domain_id,
                "policy_version": self.policy_version,
                "question_id": self._question_id,
                "target_node_id": self._target_node_id,
                "jd_id": self._jd_id,
                "jd_version": self._jd_gate.active_version,
                "jd_ref": f"{self._jd_id}@{self._jd_gate.active_version}",
                "requires_project_facts": self._requires_project_facts(),
                "knowledge_refs": self._knowledge_refs(),
                "interview_hint_ladder": list(INTERVIEW_HINT_LADDER),
                "full_solution_enabled": self._human_approved_full,
            }
        }

    def plan_event_payload(self) -> dict[str, Any]:
        return {
            "vertical": {
                "domain_id": self.domain_id,
                "policy_version": self.policy_version,
                "jd_ref": f"{self._jd_id}@{self._jd_gate.active_version}",
                "knowledge_refs": self._knowledge_refs(),
                "question_id": self._question_id,
            }
        }

    def action_event_payload(
        self, action: TeachingAction, state: SessionState
    ) -> dict[str, Any]:
        reason_code = action.reason.code if action.reason is not None else ""
        hint_level: int | None = None
        probe_stage: str | None = None
        if reason_code.startswith(_PROBE_REASON_PREFIX):
            probe_stage = reason_code[len(_PROBE_REASON_PREFIX) :].lower()
        if reason_code.startswith("INTERVIEW_HINT_LEVEL_"):
            try:
                hint_level = int(reason_code.rsplit("_", 1)[1])
            except (ValueError, IndexError):  # pragma: no cover - policy controlled
                hint_level = None
        return {
            "vertical": {
                "domain_id": self.domain_id,
                "policy_version": self.policy_version,
                "question_id": self._question_id,
                "reason_code": reason_code,
                "probe_stage": probe_stage,
                "hint_level": hint_level,
                "interview_ladder": "SOCRATIC_PROBE",
                "cf_hint_ladder_shared": False,
            }
        }

    def assessment_payload_extra(self, result: AssessmentResult) -> dict[str, Any] | None:
        if not isinstance(result, AssessmentResult):
            raise ValidationError("assessment_payload_extra(): expected an AssessmentResult")
        detail = self._judge.detail(result.result_id)
        vertical = {
            "domain_id": self.domain_id,
            "policy_version": self.policy_version,
            "question_id": self._question_id,
            "jd_ref": f"{self._jd_id}@{self._jd_gate.active_version}",
        }
        if detail is None:
            return {"vertical": vertical, "rubric_audit": None}
        return {
            "vertical": vertical,
            "rubric_audit": {
                "question_id": detail.question_id,
                "scorer_id": detail.scorer_id,
                "status": detail.status,
                "open_answer": detail.open_answer,
                "dimensions": dict(detail.dimensions),
                "failure_modes": list(detail.failure_modes),
                "spec_digest": detail.spec_digest,
            },
        }

    # -- FULL solution gate (interview-only; disabled by default) ----------
    def evidence_total(self, snapshot: LearnerSnapshot) -> int:
        return sum(estimate.evidence_count for estimate in snapshot.masteries.values())

    def full_solution_allowed(self, snapshot: LearnerSnapshot) -> bool:
        """FULL requires explicit human approval AND enough observed evidence."""

        return bool(self._human_approved_full) and self.evidence_total(snapshot) >= FULL_MIN_EVIDENCE

    def request_full_solution(self, snapshot: LearnerSnapshot) -> None:
        """Explicit FULL request fails closed unless the human-approval gate is met."""

        if not self.full_solution_allowed(snapshot):
            raise ValidationError(
                "FULL_SOLUTION is disabled for the interview vertical by default; it "
                "requires an explicit human approval (not available in M1-B) and at "
                f"least {FULL_MIN_EVIDENCE} observed evidence",
                code="MAP-E11_FULL_SOLUTION_FORBIDDEN",
                details={
                    "interview_hint_ladder": list(INTERVIEW_HINT_LADDER),
                    "max_default_level": MAX_INTERVIEW_HINT_LEVEL,
                    "human_approved_full": self._human_approved_full,
                    "evidence_total": self.evidence_total(snapshot),
                },
            )

    # -- internals ---------------------------------------------------------
    def _requires_project_facts(self) -> bool:
        return self._domain.requires_project_facts(self._question_id)

    def _knowledge_refs(self) -> list[str]:
        return sorted(
            {
                decision.new_version_id
                for decision in self._knowledge_decisions
                if decision.curriculum_eligible
            }
        )

    def _stages_for_snapshot(self, snapshot: LearnerSnapshot) -> list[str]:
        stages = list(FOLLOW_UP_STAGES)
        estimate = snapshot.masteries.get(self._target_node_id)
        if estimate is not None and (
            estimate.value >= ACCELERATED_MASTERY_THRESHOLD
            and estimate.evidence_count >= ACCELERATED_MIN_EVIDENCE
        ):
            stages = [stage for stage in stages if stage != "concept"]
        return stages

    def _stages(self, session_id: str) -> tuple[str, ...]:
        return self._stages_by_session.get(session_id, tuple(FOLLOW_UP_STAGES))

    def _session_events(self, context: VerticalActionContext) -> list[HistoryEvent]:
        return self._session_events_from(context.state, context.events)

    @staticmethod
    def _session_events_from(
        state: SessionState, events: Sequence[HistoryEvent]
    ) -> list[HistoryEvent]:
        return sorted(
            (event for event in events if event.session_id == state.session_id),
            key=lambda event: event.seq,
        )

    def _assessed_statuses(self, events: Sequence[HistoryEvent]) -> list[str]:
        statuses: list[str] = []
        for event in events:
            if event.event_type != "ASSESSED":
                continue
            if event.payload.get("item_id") != self._question_id:
                continue
            status = event.payload.get("status")
            if status in _ACTIVE_STATUSES or status == "NEEDS_REVIEW":
                statuses.append(status)
        return statuses

    @staticmethod
    def _unresolved_prepared(events: Sequence[HistoryEvent]) -> bool:
        last_prepared = -1
        last_terminal = -1
        for index, event in enumerate(events):
            if event.event_type == "ASSESSMENT_PREPARED":
                last_prepared = index
            elif event.event_type in _TERMINAL_EVENT_TYPES:
                last_terminal = index
        return last_prepared > last_terminal

    @staticmethod
    def _actions_since_last_assessment(
        events: Sequence[HistoryEvent], reason_code: str
    ) -> int:
        last_assessed = -1
        for index, event in enumerate(events):
            if event.event_type == "ASSESSED":
                last_assessed = index
        count = 0
        for event in events[last_assessed + 1 :]:
            if event.event_type != "ACTION_TAKEN":
                continue
            raw_action = event.payload.get("action")
            if not isinstance(raw_action, Mapping):
                continue
            raw_reason = raw_action.get("reason")
            if isinstance(raw_reason, Mapping) and raw_reason.get("code") == reason_code:
                count += 1
        return count

    def _hint_cap(self, context_or_snapshot: VerticalActionContext | LearnerSnapshot) -> int:
        snapshot = (
            context_or_snapshot.snapshot
            if isinstance(context_or_snapshot, VerticalActionContext)
            else context_or_snapshot
        )
        evidence = self.evidence_total(snapshot)
        if evidence <= 0:
            return 1
        if evidence == 1:
            return 2
        return MAX_INTERVIEW_HINT_LEVEL

    def _action_id(self, state: SessionState, kind: str, discriminator: str) -> str:
        digest = hashlib.sha256(
            "\x1f".join(
                (
                    self.policy_version,
                    state.session_id,
                    str(state.turn_index),
                    kind,
                    discriminator,
                )
            ).encode("utf-8")
        ).hexdigest()
        return f"vertical.act.{digest[:16]}"

    def _reason(self, code: str, detail: str) -> Reason:
        return Reason(
            code=code,
            node_ids=[self._target_node_id],
            detail=detail,
            policy_version=self.policy_version,
        )

    def _main_selection(self, context: VerticalActionContext) -> VerticalSelection:
        content = self._item.prompt
        if self._requires_project_facts():
            content += (
                "\n\n边界提示：请只基于你真实参与过的项目和可核验数据回答；"
                "如果缺少具体规模、指标或来源，请直接说明，我会先向你确认，"
                "不会替你编造事实。"
            )
        action = TeachingAction(
            action_id=self._action_id(context.state, "SOCRATIC_QUESTION", _MAIN_REASON_CODE),
            kind="SOCRATIC_QUESTION",
            node_ids=list(self._item.node_ids),
            content=content,
            reason=self._reason(
                _MAIN_REASON_CODE,
                "interview main question; five-stage Socratic follow-ups may follow",
            ),
            item_id=self._question_id,
            evidence_refs=[f"item:{self._question_id}"],
        )
        return VerticalSelection(
            action=action, phase=_PHASE_ASSESS, pending_item_id=self._question_id
        )

    def _probe_selection(
        self, context: VerticalActionContext, stage: str
    ) -> VerticalSelection:
        probes = {probe.stage: probe for probe in self._domain.follow_up_ladder(self._question_id)}
        probe = probes[stage]
        reason_code = f"{_PROBE_REASON_PREFIX}{stage.upper()}"
        action = TeachingAction(
            action_id=self._action_id(
                context.state, "SOCRATIC_QUESTION", f"probe:{stage}"
            ),
            kind="SOCRATIC_QUESTION",
            node_ids=list(self._item.node_ids),
            content=probe.prompt,
            reason=self._reason(
                reason_code,
                f"interview follow-up ladder stage {stage!r} ({probe.label}); "
                "Socratic probe only, never a hint rung",
            ),
            item_id=self._question_id,
            evidence_refs=[
                f"item:{self._question_id}",
                f"stage:{stage}",
            ],
        )
        return VerticalSelection(
            action=action, phase=_PHASE_ASSESS, pending_item_id=self._question_id
        )

    def _clarify_selection(self, context: VerticalActionContext) -> VerticalSelection:
        content = (
            "在继续追问之前，需要你补充真实项目事实（这些事实必须由你提供，我不会替你编造）：\n"
            "1) 你实际参与的项目/场景与你的角色是什么？\n"
            "2) 线上规模大概是什么量级（QPS / DAU / 数据量）？\n"
            "3) 优化前后的指标是什么？有没有 A/B、监控或日志等可核验来源？\n"
            "4) 如果确实没有线上数据，请直接说明，我会把后续讨论标注为假设推演。"
        )
        action = TeachingAction(
            action_id=self._action_id(context.state, "ASK_CLARIFICATION", _CLARIFY_REASON_CODE),
            kind="ASK_CLARIFICATION",
            node_ids=list(self._item.node_ids),
            content=content,
            reason=self._reason(
                _CLARIFY_REASON_CODE,
                "requires_project_facts but no verifiable learner-owned project facts were "
                "provided; ask instead of fabricating scale/metrics/results",
            ),
            item_id=self._question_id,
            evidence_refs=[f"item:{self._question_id}"],
        )
        return VerticalSelection(
            action=action, phase=_PHASE_ASSESS, pending_item_id=self._question_id
        )

    def _hint_selection(
        self,
        context: VerticalActionContext,
        statuses: Sequence[str],
    ) -> VerticalSelection:
        streak = 0
        for status in reversed(statuses):
            if status != "INCORRECT":
                break
            streak += 1
        cap = self._hint_cap(context)
        level = max(1, min(streak, cap, MAX_INTERVIEW_HINT_LEVEL))
        ladder_name = INTERVIEW_HINT_LADDER[level - 1]
        reason_code = INTERVIEW_HINT_REASON_CODES[ladder_name]
        content = self._domain.teaching_content(
            self._target_node_id, f"HINT_L{level}"
        )
        action = TeachingAction(
            action_id=self._action_id(
                context.state, "HINT", f"interview-hint:{level}:{streak}"
            ),
            kind="HINT",
            node_ids=list(self._item.node_ids),
            content=content,
            reason=self._reason(
                reason_code,
                f"interview support ladder {ladder_name} (level {level}/3; separate from the "
                "CF hint ladder), emitted after "
                f"{streak} consecutive INCORRECT answer(s); self-cap=level{cap}; "
                "FULL_SOLUTION is disabled by default and requires explicit human approval",
            ),
            item_id=self._question_id,
            evidence_refs=[
                f"item:{self._question_id}",
                f"consecutive-incorrect:{streak}",
            ],
        )
        return VerticalSelection(
            action=action, phase=_PHASE_ASSESS, pending_item_id=self._question_id
        )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"InterviewVerticalPolicy(question_id={self._question_id!r}, "
            f"jd={self._jd_id!r}@{self._jd_gate.active_version!r}, "
            f"policy_version={self.policy_version!r})"
        )
