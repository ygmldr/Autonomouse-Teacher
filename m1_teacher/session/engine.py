"""Teaching-session state machine for the M1-A offline teacher (B-PR4).

The engine turns the frozen components into a persistent, replayable teaching
loop:

``DIAGNOSE -> TEACH -> PRACTICE -> ASSESS -> UPDATE -> REVIEW -> ...``

plus the terminal/parked phases ``COMPLETE`` and ``PAUSED``.  All state lives in
the shared persistent records (``SessionState`` in the session repository,
``HistoryEvent`` in the append-only learner history, ``LearnerSnapshot`` as the
materialised evidence state), so a fresh engine instance attached to the same
repository can continue a paused or interrupted session.

Transition contract (every rule has a test in ``tests/m1_teacher``)
-------------------------------------------------------------------
* ``start_session``: validate goal/objective, persist the goal, load the
  learner snapshot (canonical empty snapshot when none exists), write
  ``SESSION_STARTED`` (+ ``PLAN_CREATED``) and generate the first teaching
  action.  A goal whose success criteria are already met by *observed* evidence
  starts directly in ``COMPLETE`` (significant ``TEACH`` skip).
* ``DIAGNOSE``: while fewer than ``diagnosis_min_items`` diagnostic items have
  been attempted and the diagnostic engine returns ``READY``, the next action is
  a diagnostic item.  When the diagnostic engine reports
  ``INSUFFICIENT_EVIDENCE`` (or the minimum is reached) the session moves on to
  the plan.
* ``TEACH`` / ``REVIEW`` actions are *content* actions (no pending item).  The
  caller acknowledges them with :meth:`advance_session`; the engine returns to
  ``REVIEW`` and selects the next step.  Steps already presented for the same
  snapshot revision are skipped, so a content action cannot loop forever.
* ``PRACTICE`` / ``ASSESS`` present one item at a time (``pending_item_id``);
  the learner must answer via :meth:`submit_response`.
* ``submit_response``: ``RESPONSE_SUBMITTED`` (-> ASSESS) -> independent scorer
  (-> ASSESSED / ERROR) -> ``UPDATE`` (mastery only from observed
  ``CORRECT``/``INCORRECT``/``PARTIAL`` via ``LearningHistory``) -> ``REVIEW``
  (or ``COMPLETE`` when the objective is met).  ``NEEDS_REVIEW`` is recorded but
  never updates mastery; ``EVAL_ERROR`` is explicitly **not** learner evidence:
  the snapshot, mastery and error counters stay untouched, an ``ERROR`` event is
  recorded, and the same item is retried up to ``eval_error_retry_limit`` times
  before the engine hands the session back to ``REVIEW``.
* Repeated ``INCORRECT`` outcomes escalate the hint ladder
  (``HINT_L1`` -> ``HINT_L2`` -> ``HINT_L3``; never a fourth level) before the
  next practice/reassessment action.
* ``pause_session`` / ``resume_session`` persist the phase and pending item; a
  new engine instance resumes with identical state and history, and
  ``LearningHistory.verify_rebuild`` stays true.
* Idempotency: a repeated ``submit_response`` with the same ``result_id``
  returns the first ``AssessmentResult`` and writes no new events / no second
  mastery update.

The engine is offline and deterministic.  It never reads hidden scoring
material itself (only the injected scorer does), never imports M0 code and never
touches the network.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping, Sequence

from ..assessment.scorer import AssessmentScorer, DeterministicScorer
from ..contracts.domain import DomainAdapter
from ..contracts.errors import (
    IDEMPOTENCY_CONFLICT,
    IDEMPOTENCY_UNSUPPORTED,
    ConflictError,
    NotFoundError,
    UnsupportedOperationError,
    ValidationError,
)
from ..contracts.repository import LearnerRepository, SessionRepository
from ..contracts.types import (
    SESSION_PHASE_VALUES,
    AssessmentItem,
    AssessmentResult,
    HistoryEvent,
    LearnerGoal,
    LearnerSnapshot,
    LearningObjective,
    Reason,
    SessionState,
    TeachingAction,
    now_utc,
)
from ..diagnostic.engine import INSUFFICIENT_EVIDENCE, READY, DiagnosticEngine
from ..idempotency import (
    CONFLICT_REASON_LEGACY_DIGEST_UNPROVEN,
    CONFLICT_REASON_LEGACY_SCOPE,
    CONFLICT_REASON_REQUEST_DIGEST,
    CONFLICT_REASON_TURN_ALREADY_ASSESSED,
    IDEMPOTENCY_POLICY_VERSION,
    ResultScope,
    canonical_response,
    default_result_id,
    legacy_default_result_id,
    request_digest,
    validate_result_id,
)
from ..knowledge.graph import KnowledgeGraph
from ..learner.history import (
    EventDraft,
    LearningHistory,
    assessed_event_id,
    mastery_updated_event_id,
)
from ..planner.planner import CurriculumPlanner

__all__ = [
    "RecoveryReport",
    "SessionPolicy",
    "TeachingSessionEngine",
    "SESSION_POLICY_VERSION",
]

SESSION_POLICY_VERSION = "m1a.session.v0"

#: Session phases (subset of the frozen ``SESSION_PHASE_VALUES`` enum).
PHASE_DIAGNOSE = "DIAGNOSE"
PHASE_TEACH = "TEACH"
PHASE_PRACTICE = "PRACTICE"
PHASE_ASSESS = "ASSESS"
PHASE_UPDATE = "UPDATE"
PHASE_REVIEW = "REVIEW"
PHASE_COMPLETE = "COMPLETE"
PHASE_PAUSED = "PAUSED"

_MUTATING_STATUSES = frozenset({"CORRECT", "INCORRECT", "PARTIAL"})
_NON_EVIDENCE_STATUSES = frozenset({"NEEDS_REVIEW", "EVAL_ERROR"})
_CONTENT_ACTIONS = frozenset({"EXPLAIN", "RETEACH", "HINT", "REVIEW"})
_ITEM_ACTION_PHASES = {
    "DIAGNOSE": PHASE_DIAGNOSE,
    "PRACTICE": PHASE_PRACTICE,
    "REASSESS": PHASE_ASSESS,
    "ASSESS": PHASE_ASSESS,
    "DIAGNOSE_ITEM": PHASE_ASSESS,
}
_EVAL_ERROR_EVENT_PREFIX = "evt.evalerror."
_GOAL_COMPLETED_EVENT_PREFIX = "evt.goalcompleted."
_ATTEMPT_EVENT_PREFIX = "evt.responsesubmitted."
_PREPARED_EVENT_PREFIX = "evt.assessmentprepared."
_RECOVERY_ERROR_EVENT_PREFIX = "evt.recoveryerror."
_ATTEMPT_ID_PREFIX = "attempt:"
_TERMINAL_EVENT_TYPES = frozenset({"ASSESSED", "MASTERY_UPDATED", "ERROR", "GOAL_COMPLETED"})
_IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
_SESSION_VERSION_CONFLICT = "SESSION_VERSION_CONFLICT"
_EVENT_SEQ_CONFLICT = "EVENT_SEQ_CONFLICT"
_DUPLICATE_EVENT = "DUPLICATE_EVENT"
_KEEP = object()


# ---------------------------------------------------------------------------
# B-NEXT transactional turn / recovery structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _PreparedAttempt:
    """A durable ``ASSESSMENT_PREPARED`` attempt (transaction A evidence)."""

    attempt_id: str
    learner_id: str
    session_id: str
    result_id: str
    item_id: str
    turn_index: int
    response_digest: str
    response_kind: str
    canonical_response: str
    session_version: str
    event_id: str
    request_digest: str = ""
    scope: ResultScope | None = None


@dataclass(frozen=True)
class _TurnTransition:
    """Pure description of one assessment turn's persisted transition."""

    phase: str
    turn_index: int
    pending_item_id: str | None
    snapshot: LearnerSnapshot | None
    drafts: tuple[EventDraft, ...]
    goal: LearnerGoal | None


@dataclass(frozen=True)
class RecoveryReport:
    """Explainable outcome of :meth:`TeachingSessionEngine.recover_session`.

    ``status`` is one of ``ALREADY_CONSISTENT`` (nothing prepared, no write),
    ``RECOVERED`` (every prepared attempt received its terminal event),
    ``PARTIAL`` (some recovered, some need operator attention) or ``FAILED``
    (nothing recovered: the session stays pending and unchanged).
    """

    session_id: str
    learner_id: str
    status: str
    prepared_attempts: int
    recovered_attempts: int
    pending_attempt_ids: tuple[str, ...]
    error_codes: tuple[str, ...]
    events_appended: int


class _RecoveryFailure(Exception):
    """Internal: recovery could not deterministically re-score an attempt."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail



@dataclass(frozen=True)
class SessionPolicy:
    """Deterministic, injectable constants of the teaching-session state machine.

    Every threshold is explicit so the transition rules are reviewable and
    testable; the defaults are the frozen ``m1a.session.v0`` policy.
    """

    policy_version: str = SESSION_POLICY_VERSION
    #: Minimum number of diagnostic items before the plan is allowed to start.
    diagnosis_min_items: int = 2
    #: Consecutive INCORRECT outcomes needed per additional hint rung.
    hint_escalation_threshold: int = 1
    #: Maximum hint level the session engine will emit (never beyond L3).
    max_hint_level: int = 3
    #: EVAL_ERROR retries of the same item before returning to REVIEW.
    eval_error_retry_limit: int = 2
    #: Hard cap on session turns handled by ``run_until_goal``/the engine.
    max_turns: int = 32
    #: Consecutive INCORRECT threshold that forces a reassessment action
    #: instead of more teaching/practice (also mirrored by the planner rule).
    reassess_after_incorrect: int = 2
    #: Maximum practice actions for one node between two observed assessments;
    #: beyond it the engine surfaces the assessment step instead of drilling.
    max_practice_attempts: int = 3
    #: Upper bound on the number of actions ``run_until_goal`` may generate.
    max_actions_per_run: int = 64

    def __post_init__(self) -> None:
        if type(self.policy_version) is not str or not self.policy_version.strip():
            raise ValidationError("SessionPolicy.policy_version: expected a non-blank string")
        for name in (
            "diagnosis_min_items",
            "hint_escalation_threshold",
            "eval_error_retry_limit",
            "max_turns",
            "reassess_after_incorrect",
            "max_practice_attempts",
            "max_actions_per_run",
        ):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise ValidationError(f"SessionPolicy.{name}: expected an int >= 1")
        if not 1 <= self.max_hint_level <= 3:
            raise ValidationError("SessionPolicy.max_hint_level: expected 1..3")


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _require_nonempty_str(value: Any, where: str) -> str:
    if type(value) is not str or not value.strip():
        raise ValidationError(f"{where}: expected a non-blank string")
    return value


def _require_int(value: Any, where: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValidationError(f"{where}: expected an int >= {minimum}")
    return value


def _fingerprint(*parts: Any) -> str:
    payload = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _canonical_response(response: Any) -> str:
    """Canonical response text (delegates to the scoped-idempotency helper)."""

    return canonical_response(response)


def _response_kind(response: Any) -> str:
    if isinstance(response, str):
        return "text"
    if isinstance(response, dict):
        return "structured"
    return type(response).__name__


_SESSION_TS_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def _fresh_session_timestamp(previous: str) -> str:
    """Return the current UTC second, strictly greater than ``previous``.

    The compare-and-swap session version is a content digest; a write that only
    changes ``updated_at`` (transaction A persists the prepared attempt without
    changing turn/pending/phase) must therefore produce a new timestamp even
    when it happens within the same wall-clock second.  The value stays a valid
    second-precision UTC timestamp (the frozen ``SessionState`` contract).
    """

    candidate = now_utc()
    if candidate > previous:
        return candidate
    try:
        moment = datetime.strptime(previous, _SESSION_TS_FORMAT).replace(
            tzinfo=timezone.utc
        )
    except ValueError:  # pragma: no cover - persisted contract guarantees format
        return candidate
    return (moment + timedelta(seconds=1)).strftime(_SESSION_TS_FORMAT)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class TeachingSessionEngine:
    """Persistent, deterministic teaching-session state machine."""

    def __init__(
        self,
        domain: DomainAdapter,
        graph: KnowledgeGraph,
        repository: LearnerRepository | SessionRepository,
        *,
        history: LearningHistory | None = None,
        diagnostic: DiagnosticEngine | None = None,
        planner: CurriculumPlanner | None = None,
        scorer: AssessmentScorer | None = None,
        policy: SessionPolicy | None = None,
    ) -> None:
        if not isinstance(domain, DomainAdapter):
            raise ValidationError(
                "TeachingSessionEngine(domain=...): expected a DomainAdapter implementation"
            )
        if not isinstance(graph, KnowledgeGraph):
            raise ValidationError("TeachingSessionEngine(graph=...): expected a KnowledgeGraph")
        missing = [
            name
            for name in (
                "get_snapshot",
                "upsert_snapshot",
                "append_event",
                "get_event",
                "list_events",
                "get_goal",
                "upsert_goal",
                "save_session",
                "load_session",
            )
            if not callable(getattr(repository, name, None))
        ]
        if missing:
            raise ValidationError(
                "TeachingSessionEngine(repository=...): object is missing required "
                f"repository method(s): {', '.join(missing)}"
            )
        if history is not None and not isinstance(history, LearningHistory):
            raise ValidationError("TeachingSessionEngine(history=...): expected LearningHistory")
        if diagnostic is not None and not isinstance(diagnostic, DiagnosticEngine):
            raise ValidationError("TeachingSessionEngine(diagnostic=...): expected DiagnosticEngine")
        if planner is not None and not isinstance(planner, CurriculumPlanner):
            raise ValidationError("TeachingSessionEngine(planner=...): expected CurriculumPlanner")
        if scorer is not None and not callable(getattr(scorer, "score", None)):
            raise ValidationError(
                "TeachingSessionEngine(scorer=...): expected an AssessmentScorer implementation"
            )
        if policy is not None and not isinstance(policy, SessionPolicy):
            raise ValidationError("TeachingSessionEngine(policy=...): expected SessionPolicy")
        self._domain = domain
        self._graph = graph
        self._repository = repository
        self._history = history if history is not None else LearningHistory(repository)
        self._diagnostic = diagnostic if diagnostic is not None else DiagnosticEngine(domain, graph)
        self._planner = planner if planner is not None else CurriculumPlanner(domain, graph)
        self._scorer: AssessmentScorer = scorer if scorer is not None else DeterministicScorer()
        self._policy = policy if policy is not None else SessionPolicy()
        self._supports_txn = callable(
            getattr(repository, "commit_teaching_turn", None)
        ) and callable(getattr(repository, "session_version", None))
        self._supports_scoped = all(
            callable(getattr(repository, name, None))
            for name in ("find_result_in_scope", "find_scope_owner", "get_event_for_learner")
        )
        self._items_by_id = {item.item_id: item for item in domain.assessment_items()}
        self._objectives_by_id = {
            objective.objective_id: objective for objective in domain.objectives()
        }
        self._nodes_by_id = {node.node_id: node for node in domain.knowledge_nodes()}
        self._practice_items_by_node: dict[str, list[str]] = {}
        for node_id in self._nodes_by_id:
            raw = domain.teaching_content(node_id, "PRACTICE")
            try:
                parsed = json.loads(raw)
            except (TypeError, json.JSONDecodeError) as exc:  # pragma: no cover - adapter validates
                raise ValidationError(
                    f"TeachingSessionEngine: PRACTICE content for node {node_id!r} is not JSON"
                ) from exc
            if type(parsed) is not list or not all(
                type(entry) is str and entry in self._items_by_id for entry in parsed
            ):
                raise ValidationError(
                    f"TeachingSessionEngine: PRACTICE content for node {node_id!r} is invalid"
                )
            self._practice_items_by_node[node_id] = list(parsed)

    # -- properties --------------------------------------------------------
    @property
    def domain(self) -> DomainAdapter:
        return self._domain

    @property
    def graph(self) -> KnowledgeGraph:
        return self._graph

    @property
    def history(self) -> LearningHistory:
        return self._history

    @property
    def scorer(self) -> AssessmentScorer:
        return self._scorer

    @property
    def policy(self) -> SessionPolicy:
        return self._policy

    @property
    def repository(self) -> LearnerRepository | SessionRepository:
        return self._repository

    # -- session lifecycle -------------------------------------------------
    def start_session(
        self,
        learner_id: str,
        goal: LearnerGoal,
        objective: LearningObjective,
        *,
        session_id: str | None = None,
    ) -> SessionState:
        """Create (or idempotently return) the teaching session and first action."""

        learner_id = _require_nonempty_str(
            learner_id, "TeachingSessionEngine.start_session(learner_id)"
        )
        if not isinstance(goal, LearnerGoal):
            raise ValidationError("start_session(goal=...): expected a LearnerGoal")
        if not isinstance(objective, LearningObjective):
            raise ValidationError("start_session(objective=...): expected a LearningObjective")
        if goal.learner_id != learner_id:
            raise ValidationError(
                "start_session(): goal.learner_id "
                f"{goal.learner_id!r} does not match learner {learner_id!r}"
            )
        if goal.objective_id != objective.objective_id:
            raise ValidationError(
                "start_session(): goal.objective_id "
                f"{goal.objective_id!r} does not match objective {objective.objective_id!r}"
            )
        if objective.domain_id != self._domain.domain_id:
            raise ValidationError(
                "start_session(): objective.domain_id "
                f"{objective.domain_id!r} does not match domain {self._domain.domain_id!r}"
            )
        self._graph.validate_objective(objective)
        if session_id is None:
            session_id = f"session:{learner_id}:{goal.goal_id}"
        else:
            session_id = _require_nonempty_str(
                session_id, "TeachingSessionEngine.start_session(session_id)"
            )
        existing = self._repository.load_session(session_id)
        if existing is not None:
            if (
                existing.learner_id != learner_id
                or existing.goal_id != goal.goal_id
                or existing.objective_id != objective.objective_id
            ):
                raise ConflictError(
                    f"start_session(): session {session_id!r} already exists for a different "
                    "learner/goal/objective"
                )
            return existing

        self._repository.upsert_goal(goal)
        snapshot = self._current_snapshot(learner_id)
        complete, completion_reason = self._planner.check_goal_completion(objective, snapshot)
        phase = PHASE_COMPLETE if complete else PHASE_DIAGNOSE
        state = SessionState(
            session_id=session_id,
            learner_id=learner_id,
            goal_id=goal.goal_id,
            objective_id=objective.objective_id,
            phase=phase,
            turn_index=0,
            pending_item_id=None,
        )
        self._repository.save_session(state)
        self._append_event(
            state,
            "SESSION_STARTED",
            {
                "learner_id": learner_id,
                "goal_id": goal.goal_id,
                "objective_id": objective.objective_id,
                "phase": phase,
                "snapshot_revision": snapshot.revision,
                "session_policy_version": self._policy.policy_version,
            },
        )
        plan = self._planner.plan(goal, objective, snapshot, history=self._events(learner_id))
        self._append_event(
            state,
            "PLAN_CREATED",
            {
                "plan_id": plan.plan_id,
                "objective_id": plan.objective_id,
                "step_count": len(plan.steps),
                "policy_version": plan.policy_version,
            },
        )
        if complete:
            self._record_goal_completed(state, objective, completion_reason)
            return self._load_session(session_id)
        new_state, _action = self._generate_and_persist(state)
        return new_state

    def current_action(self, session_id: str) -> TeachingAction:
        """Return the action for the current turn (idempotent per turn)."""

        state = self._load_session(session_id)
        if state.phase == PHASE_PAUSED:
            raise ConflictError(
                f"current_action({session_id!r}): session is PAUSED; resume it first"
            )
        if state.phase == PHASE_COMPLETE:
            return self._complete_action(state)
        existing = self._action_for_current_turn(state)
        if existing is not None:
            return existing
        _new_state, action = self._generate_and_persist(state)
        return action

    def advance_session(self, session_id: str) -> SessionState:
        """Acknowledge a content action (TEACH/HINT/REVIEW) and advance one turn."""

        state = self._load_session(session_id)
        if state.phase == PHASE_PAUSED:
            raise ConflictError(f"advance_session({session_id!r}): session is PAUSED")
        if state.phase == PHASE_COMPLETE:
            raise ConflictError(f"advance_session({session_id!r}): session is COMPLETE")
        if state.pending_item_id is not None:
            raise ConflictError(
                f"advance_session({session_id!r}): pending item "
                f"{state.pending_item_id!r} must be answered with submit_response()"
            )
        return self._save_state(
            state,
            phase=PHASE_REVIEW,
            turn_index=state.turn_index + 1,
            pending_item_id=None,
        )

    def pause_session(self, session_id: str) -> SessionState:
        """Persist a pause without losing the pending item or the phase."""

        state = self._load_session(session_id)
        if state.phase == PHASE_PAUSED:
            return state
        if state.phase == PHASE_COMPLETE:
            raise ConflictError(f"pause_session({session_id!r}): session is COMPLETE")
        self._append_event(
            state,
            "SESSION_PAUSED",
            {
                "previous_phase": state.phase,
                "pending_item_id": state.pending_item_id,
                "turn_index": state.turn_index,
            },
        )
        return self._save_state(state, phase=PHASE_PAUSED)

    def resume_session(self, session_id: str) -> SessionState:
        """Resume a paused session, restoring its previous phase and pending item."""

        state = self._load_session(session_id)
        if state.phase != PHASE_PAUSED:
            raise ConflictError(
                f"resume_session({session_id!r}): session is not PAUSED "
                f"(phase={state.phase!r})"
            )
        previous_phase = self._last_pause_phase(state)
        if previous_phase is None:
            raise ValidationError(
                f"resume_session({session_id!r}): no SESSION_PAUSED event with a valid "
                "previous phase was found"
            )
        self._append_event(state, "SESSION_RESUMED", {"phase": previous_phase})
        return self._save_state(state, phase=previous_phase)

    # -- response handling -------------------------------------------------
    def submit_response(
        self,
        session_id: str,
        item_id: str,
        response: str | dict,
        *,
        result_id: str | None = None,
        caller_learner_id: str | None = None,
    ) -> AssessmentResult:
        """Score one submission and advance the session through ASSESS -> UPDATE.

        With a repository that implements the B-NEXT transactional extension
        (:meth:`SqliteRepository.commit_teaching_turn`), the submission runs as:

        * **transaction A** — atomically persist the durable attempt
          (``RESPONSE_SUBMITTED`` + ``ASSESSMENT_PREPARED`` with the canonical
          response and session version; compare-and-swap protected);
        * **outside any database transaction** — call the injected external
          scorer (at-least-once invocation is possible after a crash; state
          application stays exactly-once via the terminal event ids);
        * **transaction B** — atomically commit ``ASSESSED``/``MASTERY_UPDATED``
          (or ``ERROR`` for ``EVAL_ERROR``), the learner snapshot, the optional
          ``GOAL_COMPLETED`` event/goal row and the next session state.

        A crash between A and B leaves a recoverable prepared attempt that
        :meth:`recover_session` completes deterministically.  Legacy repositories
        without the extension fall back to the old multi-transaction flow, which
        is explicitly **not atomic** (``supports_transactional_turns`` is
        ``False`` and the recovery API fails closed).

        B-PR3 scoped idempotency: an explicit ``result_id`` is bound to
        ``(learner_id, session_id, item_id, turn_index, result_id,
        request_digest)``.  A same-scope/same-response retry returns the first
        result with zero extra events; a same-key/different-response or
        cross-scope replay raises ``IDEMPOTENCY_CONFLICT`` (never returns another
        learner's/session's grade and never writes state).  ``caller_learner_id``
        is an optional identity assertion supplied by the trusted outer layer
        (M1 has no real auth): when provided it must match the session owner,
        otherwise the call fails closed before any lookup.  Authentication and
        multi-tenant security are **not** provided by this method.
        """

        if self._supports_txn:
            return self._submit_response_transactional(
                session_id,
                item_id,
                response,
                result_id=result_id,
                caller_learner_id=caller_learner_id,
            )
        return self._submit_response_legacy(
            session_id,
            item_id,
            response,
            result_id=result_id,
            caller_learner_id=caller_learner_id,
        )

    @property
    def supports_transactional_turns(self) -> bool:
        """Whether the attached repository supports the B-NEXT atomic turn API."""

        return self._supports_txn

    @property
    def supports_scoped_idempotency(self) -> bool:
        """Whether the attached repository supports B-PR3 scoped idempotency."""

        return self._supports_scoped

    def _submit_response_legacy(
        self,
        session_id: str,
        item_id: str,
        response: str | dict,
        *,
        result_id: str | None = None,
        caller_learner_id: str | None = None,
    ) -> AssessmentResult:
        """Legacy fallback: the pre-B-NEXT multi-transaction submit flow.

        Kept for protocol-only repositories; documented as **non-atomic** (a
        crash may leave a scored-but-not-advanced session).  Behaviour is
        unchanged from M1-A so existing callers keep working.
        """

        state = self._load_session(session_id)
        self._assert_caller_learner(state, caller_learner_id)
        item_id = _require_nonempty_str(
            item_id, "TeachingSessionEngine.submit_response(item_id)"
        )
        if state.phase == PHASE_PAUSED:
            raise ConflictError(f"submit_response({session_id!r}): session is PAUSED")
        if state.phase == PHASE_COMPLETE:
            raise ConflictError(f"submit_response({session_id!r}): session is COMPLETE")
        item = self._items_by_id.get(item_id)
        if item is None:
            raise NotFoundError(f"submit_response(): unknown item_id {item_id!r}")
        digest = request_digest(response)
        scope: ResultScope | None = None
        # Idempotency first: an explicit result_id that was already applied
        # returns the first result without re-validating the (already advanced)
        # turn/pending state or writing any event.  This lookup is scoped and
        # learner/session/item/turn/digest bound; it never falls back to a
        # global event_id read.
        if result_id is not None:
            result_id = validate_result_id(
                result_id, "TeachingSessionEngine.submit_response(result_id)"
            )
            scope = self._make_scope(state, item_id, result_id, digest)
            existing = self._lookup_result_for_scope(scope)
            if existing is not None:
                return existing
        if state.pending_item_id is None:
            raise ConflictError(
                f"submit_response({session_id!r}): no item is pending; call "
                "current_action() first"
            )
        if state.pending_item_id != item_id:
            raise ConflictError(
                f"submit_response(): pending item is {state.pending_item_id!r}, "
                f"not {item_id!r}"
            )
        if result_id is None:
            result_id = self._default_attempt_result_id(state, item_id, response)
            scope = self._make_scope(state, item_id, result_id, digest)
            if self._supports_scoped:
                existing = self._lookup_result_for_scope(scope)
                if existing is not None:
                    return existing
        assert scope is not None
        snapshot = self._current_snapshot(state.learner_id)
        result = self._score_safely(item, state.learner_id, response, result_id)
        if self._supports_scoped:
            existing = self._lookup_result_for_scope(scope)
            if existing is not None:
                return existing

        self._append_event(
            state,
            "RESPONSE_SUBMITTED",
            {
                "item_id": item.item_id,
                "result_id": result.result_id,
                "response_digest": hashlib.sha256(
                    _canonical_response(response).encode("utf-8")
                ).hexdigest()[:16],
                "response_kind": _response_kind(response),
                "attempt": state.turn_index,
            },
        )
        if result.status == "EVAL_ERROR":
            new_state = self._handle_eval_error(state, item, result)
        elif result.status == "NEEDS_REVIEW":
            new_state = self._handle_needs_review(state, item, result, snapshot)
        elif result.status in _MUTATING_STATUSES:
            new_state = self._handle_observed_result(state, item, result, snapshot)
        else:  # pragma: no cover - scorer contract is closed
            raise ValidationError(f"submit_response(): unsupported status {result.status!r}")
        self._repository.save_session(new_state)
        return result

    # -- B-NEXT: transactional submit (A -> score -> B) --------------------

    def _submit_response_transactional(
        self,
        session_id: str,
        item_id: str,
        response: str | dict,
        *,
        result_id: str | None = None,
        caller_learner_id: str | None = None,
    ) -> AssessmentResult:
        state = self._load_session(session_id)
        self._assert_caller_learner(state, caller_learner_id)
        item_id = _require_nonempty_str(
            item_id, "TeachingSessionEngine.submit_response(item_id)"
        )
        if state.phase == PHASE_PAUSED:
            raise ConflictError(f"submit_response({session_id!r}): session is PAUSED")
        if state.phase == PHASE_COMPLETE:
            raise ConflictError(f"submit_response({session_id!r}): session is COMPLETE")
        item = self._items_by_id.get(item_id)
        if item is None:
            raise NotFoundError(f"submit_response(): unknown item_id {item_id!r}")
        learner_id = state.learner_id
        canonical = canonical_response(response)
        digest = request_digest(response)
        digest16 = digest[:16]
        response_kind = _response_kind(response)

        # 1) Scoped idempotency fast path (before any pending/turn validation so
        #    a same-scope retry works after the turn advanced).  The lookup is
        #    learner/session/item/turn/digest bound; it never falls back to a
        #    global result-id read.
        requested_result_id: str | None = None
        requested_scope: ResultScope | None = None
        if result_id is not None:
            requested_result_id = validate_result_id(
                result_id, "TeachingSessionEngine.submit_response(result_id)"
            )
            requested_scope = self._make_scope(state, item_id, requested_result_id, digest)
            existing = self._lookup_result_for_scope(requested_scope)
            if existing is not None:
                return existing
        if state.pending_item_id is None:
            self._raise_consumed_turn_if_applicable(state, item_id, requested_scope)
            raise ConflictError(
                f"submit_response({session_id!r}): no item is pending; call "
                "current_action() first"
            )
        if state.pending_item_id != item_id:
            raise ConflictError(
                f"submit_response(): pending item is {state.pending_item_id!r}, "
                f"not {item_id!r}"
            )

        # 2) Durable attempt identity: one attempt per (learner, session, item,
        #    turn).  A retry must resume the same PREPARED attempt / hit the
        #    same terminal result; it must never become a second scoring attempt.
        attempt_id = self._attempt_id(session_id, state.turn_index, item_id)
        prepared_payload = self._prepared_payload(state, attempt_id)
        if prepared_payload is not None:
            prepared = self._decode_prepared(attempt_id, prepared_payload)
            if (
                requested_result_id is not None
                and prepared.result_id != requested_result_id
            ):
                self._idempotency_conflict(
                    CONFLICT_REASON_TURN_ALREADY_ASSESSED,
                    requested_scope or prepared.scope,
                    message=(
                        "the pending teaching turn was already prepared with a different "
                        "result_id; reuse the original idempotency token"
                    ),
                )
            self._assert_attempt_matches_request(
                prepared, state, item, digest, requested_result_id
            )
            terminal = self._lookup_result_for_scope(prepared.scope)
            if terminal is not None:
                return terminal
            current_state = self._load_session(session_id)
        else:
            result_id_final = (
                requested_result_id
                if requested_result_id is not None
                else self._default_attempt_result_id(state, item_id, response)
            )
            scope = self._make_scope(state, item_id, result_id_final, digest)
            if requested_result_id is None and self._supports_scoped:
                # Upgrade compatibility: a pre-B-PR3 database may hold a
                # terminal result under the old default-id shape.  Only adopt it
                # when its learner/session/item/turn/digest can be proven.
                legacy_existing = self._lookup_legacy_default_result(
                    state, item_id, response, digest
                )
                if legacy_existing is not None:
                    return legacy_existing
            try:
                prepared = self._prepare_attempt(
                    state=state,
                    item=item,
                    canonical_response=canonical,
                    request_digest=digest,
                    response_digest=digest16,
                    response_kind=response_kind,
                    attempt_id=attempt_id,
                    result_id=result_id_final,
                    scope=scope,
                )
            except ConflictError as exc:
                code = getattr(exc, "code", "")
                if code not in {
                    _SESSION_VERSION_CONFLICT,
                    _DUPLICATE_EVENT,
                    IDEMPOTENCY_CONFLICT,
                }:
                    raise
                retry_payload = self._prepared_payload(state, attempt_id)
                if retry_payload is None:
                    terminal = self._lookup_result_for_scope(scope)
                    if terminal is not None:
                        return terminal
                    raise
                prepared = self._decode_prepared(attempt_id, retry_payload)
                if (
                    requested_result_id is not None
                    and prepared.result_id != requested_result_id
                ):
                    self._idempotency_conflict(
                        CONFLICT_REASON_TURN_ALREADY_ASSESSED,
                        requested_scope or prepared.scope,
                    )
                self._assert_attempt_matches_request(
                    prepared, state, item, digest, requested_result_id
                )
                terminal = self._lookup_result_for_scope(prepared.scope)
                if terminal is not None:
                    return terminal
            current_state = self._load_session(session_id)

        # 3) The external scorer runs OUTSIDE any database transaction.  It may
        #    be invoked more than once across a crash/retry; persisted state is
        #    still applied exactly once because the terminal event ids are
        #    deterministic functions of result_id and the commit fails closed on
        #    duplicates.
        result = self._score_safely(item, learner_id, response, prepared.result_id)
        return self._commit_result_turn(current_state, item, result, prepared.scope)

    def _prepare_attempt(
        self,
        *,
        state: SessionState,
        item: AssessmentItem,
        canonical_response: str,
        request_digest: str,
        response_digest: str,
        response_kind: str,
        attempt_id: str,
        result_id: str,
        scope: ResultScope,
    ) -> _PreparedAttempt:
        """Transaction A: atomically persist the durable assessment attempt."""

        expected_version = self._repository.session_version(state)
        now = now_utc()
        prepared_event_id = f"{_PREPARED_EVENT_PREFIX}{attempt_id}"
        scope_payload = scope.to_dict()
        drafts = (
            EventDraft(
                event_id=f"{_ATTEMPT_EVENT_PREFIX}{attempt_id}",
                event_type="RESPONSE_SUBMITTED",
                payload={
                    "item_id": item.item_id,
                    "result_id": result_id,
                    "response_digest": response_digest,
                    "request_digest": request_digest,
                    "response_kind": response_kind,
                    "attempt": state.turn_index,
                    "attempt_id": attempt_id,
                    "session_version": expected_version,
                    "scope": scope_payload,
                },
                created_at=now,
            ),
            EventDraft(
                event_id=prepared_event_id,
                event_type="ASSESSMENT_PREPARED",
                payload={
                    "attempt_id": attempt_id,
                    "learner_id": state.learner_id,
                    "session_id": state.session_id,
                    "item_id": item.item_id,
                    "turn_index": state.turn_index,
                    "result_id": result_id,
                    "response_digest": response_digest,
                    "request_digest": request_digest,
                    "response_kind": response_kind,
                    "canonical_response": canonical_response,
                    "session_version": expected_version,
                    "session_policy_version": self._policy.policy_version,
                    "scope": scope_payload,
                },
                created_at=now,
            ),
        )
        self._commit_turn_with_retry(
            learner_id=state.learner_id,
            session_id=state.session_id,
            expected_version=expected_version,
            drafts=drafts,
            snapshot=None,
            next_state=replace(
                state, updated_at=_fresh_session_timestamp(state.updated_at)
            ),
            goal=None,
            scope=scope,
        )
        return _PreparedAttempt(
            attempt_id=attempt_id,
            learner_id=state.learner_id,
            session_id=state.session_id,
            result_id=result_id,
            item_id=item.item_id,
            turn_index=state.turn_index,
            response_digest=response_digest,
            response_kind=response_kind,
            canonical_response=canonical_response,
            session_version=expected_version,
            event_id=prepared_event_id,
            request_digest=request_digest,
            scope=scope,
        )

    def _commit_result_turn(
        self,
        state: SessionState,
        item: AssessmentItem,
        result: AssessmentResult,
        scope: ResultScope | None = None,
    ) -> AssessmentResult:
        """Transaction B: atomically apply the scored assessment turn."""

        snapshot = self._current_snapshot(state.learner_id)
        transition = self._plan_result_transition(state, item, result, snapshot, scope)
        next_state = self._next_state_from_transition(state, transition)
        expected_version = self._repository.session_version(state)
        try:
            self._commit_turn_with_retry(
                learner_id=state.learner_id,
                session_id=state.session_id,
                expected_version=expected_version,
                drafts=transition.drafts,
                snapshot=transition.snapshot,
                next_state=next_state,
                goal=transition.goal,
                scope=scope,
            )
        except ConflictError as exc:
            code = getattr(exc, "code", "")
            if scope is not None and code in {
                _SESSION_VERSION_CONFLICT,
                _DUPLICATE_EVENT,
                IDEMPOTENCY_CONFLICT,
            }:
                # Never return a *global* terminal result: re-read only through
                # the exact scoped key (this also handles a concurrent writer
                # that already committed the same turn).
                terminal = self._lookup_result_for_scope(scope)
                if terminal is not None:
                    return terminal
            raise
        return result

    def _plan_result_transition(
        self,
        state: SessionState,
        item: AssessmentItem,
        result: AssessmentResult,
        snapshot: LearnerSnapshot,
        scope: ResultScope | None = None,
    ) -> _TurnTransition:
        """Pure transition planner for one scored response (no writes)."""

        next_turn = state.turn_index + 1
        scope_payload = None if scope is None else scope.to_dict()
        scope_extra = {} if scope_payload is None else {"scope": scope_payload}
        if result.status == "EVAL_ERROR":
            retries = self._eval_error_streak(self._session_events(state), item.item_id) + 1
            exhausted = retries > self._policy.eval_error_retry_limit
            draft = EventDraft(
                event_id=f"{_EVAL_ERROR_EVENT_PREFIX}{result.result_id}",
                event_type="ERROR",
                payload={
                    "stage": "ASSESS",
                    "status": "EVAL_ERROR",
                    "item_id": item.item_id,
                    "result_id": result.result_id,
                    "result": result.to_dict(),
                    "failure_reason": result.failure_reason,
                    "retry_attempt": retries,
                    "retry_exhausted": exhausted,
                    "mastery_unchanged": True,
                    **scope_extra,
                },
                created_at=now_utc(),
            )
            return _TurnTransition(
                phase=PHASE_REVIEW if exhausted else state.phase,
                turn_index=next_turn,
                pending_item_id=None if exhausted else item.item_id,
                snapshot=None,
                drafts=(draft,),
                goal=None,
            )
        drafts, updated, mutated = self._history.assessment_event_drafts(
            state.learner_id, state.session_id, item, result, snapshot, scope=scope
        )
        phase = PHASE_REVIEW
        goal_update: LearnerGoal | None = None
        if mutated and result.status in _MUTATING_STATUSES:
            objective = self._objective(state)
            complete, completion_reason = self._planner.check_goal_completion(
                objective, updated
            )
            if complete:
                phase = PHASE_COMPLETE
                goal_event_id = f"{_GOAL_COMPLETED_EVENT_PREFIX}{objective.objective_id}"
                if self._repository.get_event(goal_event_id) is None:
                    drafts.append(
                        EventDraft(
                            event_id=goal_event_id,
                            event_type="GOAL_COMPLETED",
                            payload={
                                "objective_id": objective.objective_id,
                                "reason": completion_reason.to_dict(),
                                "policy_version": self._policy.policy_version,
                                **scope_extra,
                            },
                            created_at=now_utc(),
                        )
                    )
                goal_update = replace(self._goal(state), status="COMPLETED")
        return _TurnTransition(
            phase=phase,
            turn_index=next_turn,
            pending_item_id=None,
            snapshot=updated if mutated else None,
            drafts=tuple(drafts),
            goal=goal_update,
        )

    @staticmethod
    def _next_state_from_transition(
        state: SessionState, transition: _TurnTransition
    ) -> SessionState:
        return SessionState(
            session_id=state.session_id,
            learner_id=state.learner_id,
            goal_id=state.goal_id,
            objective_id=state.objective_id,
            phase=transition.phase,
            turn_index=transition.turn_index,
            pending_item_id=transition.pending_item_id,
            created_at=state.created_at,
            updated_at=_fresh_session_timestamp(state.updated_at),
        )

    def _commit_turn_with_retry(
        self,
        *,
        learner_id: str,
        session_id: str,
        expected_version: str,
        drafts: Sequence[EventDraft],
        snapshot: LearnerSnapshot | None,
        next_state: SessionState,
        goal: LearnerGoal | None,
        scope: ResultScope | None = None,
    ) -> list[bool]:
        """Commit drafts; retry only on an explicit cross-writer seq conflict."""

        last: ConflictError | None = None
        for attempt in range(3):
            start_seq = self._next_event_seq(learner_id)
            events = [
                draft.materialize(
                    learner_id=learner_id, session_id=session_id, seq=start_seq + offset
                )
                for offset, draft in enumerate(drafts)
            ]
            try:
                return list(
                    self._repository.commit_teaching_turn(
                        learner_id=learner_id,
                        session_id=session_id,
                        expected_session_version=expected_version,
                        events=events,
                        snapshot=snapshot,
                        next_session=next_state,
                        goal=goal,
                        scope=scope,
                    )
                )
            except ConflictError as exc:
                last = exc
                if getattr(exc, "code", "") == _EVENT_SEQ_CONFLICT and attempt < 2:
                    continue
                raise
        assert last is not None  # pragma: no cover - defensive
        raise last

    def _next_event_seq(self, learner_id: str) -> int:
        return max((event.seq for event in self._events(learner_id)), default=-1) + 1

    @staticmethod
    def _attempt_id(session_id: str, turn_index: int, item_id: str) -> str:
        return f"{_ATTEMPT_ID_PREFIX}{session_id}:{turn_index}:{item_id}"

    # -- B-PR3 scoped idempotency helpers ----------------------------------

    def _assert_caller_learner(
        self, state: SessionState, caller_learner_id: str | None
    ) -> None:
        """Optional trusted-caller identity assertion (M1 has no real auth)."""

        if caller_learner_id is None:
            return
        caller = _require_nonempty_str(
            caller_learner_id, "TeachingSessionEngine.submit_response(caller_learner_id)"
        )
        if caller != state.learner_id:
            # Deliberately does not echo the session owner: the caller supplied
            # an identity that does not own this session.
            raise ConflictError(
                "submit_response(): caller identity does not own the requested session "
                "(authentication is not provided by M1; the trusted outer layer must "
                "supply the correct learner id)",
                details={"reason": "CALLER_LEARNER_MISMATCH"},
            )

    def _make_scope(
        self,
        state: SessionState,
        item_id: str,
        result_id: str,
        digest: str,
    ) -> ResultScope:
        return ResultScope(
            learner_id=state.learner_id,
            session_id=state.session_id,
            item_id=item_id,
            turn_index=state.turn_index,
            result_id=result_id,
            request_digest=digest,
        )

    def _idempotency_conflict(
        self,
        reason: str,
        scope: ResultScope,
        *,
        message: str | None = None,
    ) -> None:
        """Raise the stable scoped-idempotency conflict (requester data only)."""

        raise ConflictError(
            message
            or (
                f"submit_response(): idempotency conflict for result_id "
                f"{scope.result_id!r} ({reason}); the key is bound to a different "
                "request/scope"
            ),
            code=IDEMPOTENCY_CONFLICT,
            details={
                "reason": reason,
                "requested_scope": scope.to_dict(),
                "policy_version": IDEMPOTENCY_POLICY_VERSION,
            },
        )

    @staticmethod
    def _prepared_scope(prepared: _PreparedAttempt) -> ResultScope:
        if prepared.scope is not None:
            return prepared.scope
        digest = prepared.request_digest or hashlib.sha256(
            prepared.canonical_response.encode("utf-8")
        ).hexdigest()
        return ResultScope(
            learner_id=prepared.learner_id,
            session_id=prepared.session_id,
            item_id=prepared.item_id,
            turn_index=prepared.turn_index,
            result_id=prepared.result_id,
            request_digest=digest,
        )

    def _lookup_result_for_scope(self, scope: ResultScope) -> AssessmentResult | None:
        """Return the stored result for an **exactly matching** scope (or ``None``).

        Never performs a global ``result_id`` / ``event_id`` lookup.  With the
        scoped repository extension the v1 row is authoritative; legacy
        (pre-scope) rows/events are only adopted by the explicit legacy adapter
        below, which requires learner/session/item match and digest proof.
        Without the extension the engine fails closed
        (``IDEMPOTENCY_UNSUPPORTED``) instead of falling back to global reads.
        """

        if not isinstance(scope, ResultScope):
            raise ValidationError(
                "TeachingSessionEngine._lookup_result_for_scope(): expected a ResultScope"
            )
        if not self._supports_scoped:
            raise UnsupportedOperationError(
                "submit_response(): the repository does not implement scoped idempotency; "
                "refusing a global result lookup (fail closed)",
                code=IDEMPOTENCY_UNSUPPORTED,
            )
        try:
            found = self._repository.find_result_in_scope(scope)
        except ConflictError as exc:
            found = self._lookup_scope_turn_tolerant(scope, exc)
        if found is not None:
            return found
        owner = self._repository.find_scope_owner(scope.result_id)
        if owner is not None and owner.origin == "legacy":
            return self._legacy_result_from_owner(owner, scope)
        return self._legacy_event_lookup(scope)

    def _lookup_scope_turn_tolerant(
        self, scope: ResultScope, conflict: ConflictError
    ) -> AssessmentResult | None:
        """Handle the one legitimate turn drift: retrying a just-committed turn.

        A successful commit advances ``turn_index``, so a same-token/same-response
        retry of the *same logical submission* now has ``scope.turn_index ==
        owner.turn_index + 1`` with an identical learner/session/item/digest.
        That is resumed as an idempotent replay (matrix M1).  Any other turn
        mismatch (reusing a token in a later turn) stays a conflict.
        """

        if getattr(conflict, "code", "") != IDEMPOTENCY_CONFLICT:
            raise conflict
        details = getattr(conflict, "details", {}) or {}
        if details.get("reason") != "TURN_MISMATCH":
            raise conflict
        owner = self._repository.find_scope_owner(scope.result_id)
        if owner is None or owner.origin != "v1" or owner.status != "TERMINAL":
            raise conflict
        if (
            owner.learner_id != scope.learner_id
            or owner.session_id != scope.session_id
            or owner.item_id != scope.item_id
            or owner.request_digest != scope.request_digest
            or owner.turn_index != scope.turn_index - 1
        ):
            raise conflict
        cached_scope = ResultScope(
            learner_id=owner.learner_id,
            session_id=owner.session_id,
            item_id=owner.item_id,
            turn_index=owner.turn_index,
            result_id=owner.result_id,
            request_digest=owner.request_digest,
        )
        return self._repository.find_result_in_scope(cached_scope)

    def _lookup_legacy_default_result(
        self,
        state: SessionState,
        item_id: str,
        response: str | dict,
        digest: str,
    ) -> AssessmentResult | None:
        """Adopt a pre-B-PR3 default-id result for a same-request retry (upgrade path)."""

        if not self._supports_scoped:
            return None
        legacy_id = legacy_default_result_id(
            state.session_id, state.turn_index, item_id, response
        )
        try:
            scope = ResultScope(
                learner_id=state.learner_id,
                session_id=state.session_id,
                item_id=item_id,
                turn_index=state.turn_index,
                result_id=legacy_id,
                request_digest=digest,
            )
        except ValidationError:
            return None
        return self._lookup_result_for_scope(scope)

    def _legacy_result_from_owner(
        self, owner: Any, scope: ResultScope
    ) -> AssessmentResult | None:
        """Adopt a migrated legacy scope row after proving it is the same request."""

        if owner.learner_id != scope.learner_id or owner.session_id != scope.session_id:
            self._idempotency_conflict(
                CONFLICT_REASON_LEGACY_SCOPE,
                scope,
                message=(
                    "result_id is bound to a legacy record of a different learner/session; "
                    "refusing to return it"
                ),
            )
        if owner.item_id != scope.item_id:
            self._idempotency_conflict(
                CONFLICT_REASON_LEGACY_SCOPE,
                scope,
                message="result_id is bound to a legacy record of a different item",
            )
        # ``-1``: pre-scope row with no provable turn.  ``scope.turn_index - 1``:
        # the same logical submission retried after its commit advanced the turn.
        if owner.turn_index not in (-1, scope.turn_index, scope.turn_index - 1):
            self._idempotency_conflict(
                CONFLICT_REASON_LEGACY_SCOPE,
                scope,
                message="result_id is bound to a legacy record of a different turn",
            )
        self._assert_legacy_digest_matches(owner.request_digest, scope)
        if owner.result_event_id is None:  # pragma: no cover - migration invariant
            raise ValidationError(
                f"legacy scope row for result_id {scope.result_id!r} has no terminal event"
            )
        event = self._repository.get_event_for_learner(
            owner.learner_id, owner.result_event_id
        )
        if event is None:  # pragma: no cover - corrupted index
            raise ValidationError(
                f"legacy scope row for result_id {scope.result_id!r} references a missing event"
            )
        if event.session_id != scope.session_id:
            self._idempotency_conflict(CONFLICT_REASON_LEGACY_SCOPE, scope)
        return self._result_from_terminal_event(event, scope)

    def _legacy_event_lookup(self, scope: ResultScope) -> AssessmentResult | None:
        """Event-log legacy adapter for rows never backfilled into ``result_scopes``.

        Only events of the **same learner** are read (``list_events(learner_id)``
        is learner-scoped); the session/item/result id and the stored response
        digest prefix must all match, otherwise the call fails closed.
        """

        terminal: HistoryEvent | None = None
        for event in self._events(scope.learner_id):
            if event.event_type not in ("ASSESSED", "ERROR"):
                continue
            payload = event.payload
            raw = payload.get("result")
            if not isinstance(raw, Mapping):
                continue
            result_id = payload.get("result_id", raw.get("result_id"))
            if result_id == scope.result_id:
                terminal = event
        if terminal is None:
            return None
        if terminal.session_id != scope.session_id:
            self._idempotency_conflict(
                CONFLICT_REASON_LEGACY_SCOPE,
                scope,
                message=(
                    "result_id is bound to a legacy result of a different session; "
                    "refusing to return it"
                ),
            )
        result = self._result_from_terminal_event(terminal, scope)
        digest_marker = self._legacy_response_digest(scope)
        if digest_marker is None:
            self._idempotency_conflict(
                CONFLICT_REASON_LEGACY_DIGEST_UNPROVEN,
                scope,
                message=(
                    "cannot prove the stored legacy result belongs to this request "
                    "(no comparable response digest); refusing to return it"
                ),
            )
        self._assert_legacy_digest_matches(digest_marker, scope)
        return result

    def _legacy_response_digest(self, scope: ResultScope) -> str | None:
        marker: str | None = None
        for event in self._events(scope.learner_id):
            if event.event_type not in ("ASSESSMENT_PREPARED", "RESPONSE_SUBMITTED"):
                continue
            payload = event.payload
            if not isinstance(payload, Mapping):
                continue
            if payload.get("result_id") != scope.result_id:
                continue
            if event.session_id != scope.session_id:
                continue
            raw_digest = payload.get("response_digest")
            if type(raw_digest) is str and len(raw_digest) == 16:
                marker = f"legacy:{raw_digest}"
        return marker

    def _assert_legacy_digest_matches(self, stored: str, scope: ResultScope) -> None:
        if type(stored) is str and stored.startswith("legacy:"):
            marker = stored[len("legacy:") :]
            if len(marker) == 16:
                if marker != scope.request_digest[:16]:
                    self._idempotency_conflict(
                        CONFLICT_REASON_REQUEST_DIGEST,
                        scope,
                        message=(
                            "result_id was already used with a different response; "
                            "refusing to return the old grade"
                        ),
                    )
                return
        self._idempotency_conflict(
            CONFLICT_REASON_LEGACY_DIGEST_UNPROVEN,
            scope,
            message=(
                "cannot prove the stored legacy result belongs to this request; "
                "refusing to return it"
            ),
        )

    def _result_from_terminal_event(
        self, event: HistoryEvent, scope: ResultScope
    ) -> AssessmentResult:
        payload = event.payload
        if not isinstance(payload, Mapping):
            raise ValidationError(
                f"stored terminal event for result_id {scope.result_id!r} has no payload"
            )
        item_id = payload.get("item_id")
        if isinstance(item_id, str) and item_id != scope.item_id:
            self._idempotency_conflict(
                CONFLICT_REASON_LEGACY_SCOPE,
                scope,
                message="result_id is bound to a stored result of a different item",
            )
        raw = payload.get("result")
        if not isinstance(raw, Mapping):
            raise ValidationError(
                f"stored terminal event for result_id {scope.result_id!r} has no result payload"
            )
        try:
            result = AssessmentResult.from_dict(dict(raw))
        except ValidationError:
            raise ValidationError(
                f"stored assessment result {scope.result_id!r} is corrupted"
            ) from None
        if result.learner_id != scope.learner_id:
            self._idempotency_conflict(
                CONFLICT_REASON_LEGACY_SCOPE,
                scope,
                message="result_id is bound to a stored result of a different learner",
            )
        if result.item_id != scope.item_id:
            self._idempotency_conflict(
                CONFLICT_REASON_LEGACY_SCOPE,
                scope,
                message="result_id is bound to a stored result of a different item",
            )
        return result

    def _raise_consumed_turn_if_applicable(
        self,
        state: SessionState,
        item_id: str,
        requested_scope: ResultScope | None,
    ) -> None:
        """Stable conflict when an explicit new token targets an already-assessed turn.

        Content-based implicit de-duplication is deliberately rejected: a new
        ``result_id`` signals a new logical submission that the single-use turn
        state machine cannot accept, so the caller must reuse the original token.
        """

        if requested_scope is None or not self._supports_scoped:
            return
        terminal = [
            event
            for event in self._session_events(state)
            if event.event_type in ("ASSESSED", "ERROR")
            and event.payload.get("item_id") == item_id
        ]
        if not terminal:
            return
        # The latest terminal event belongs to the previous turn of this session.
        self._idempotency_conflict(
            CONFLICT_REASON_TURN_ALREADY_ASSESSED,
            requested_scope,
            message=(
                "this teaching turn was already assessed with a different result_id; "
                "content-equality is not used for implicit de-duplication -- reuse the "
                "original result_id for an idempotent retry"
            ),
        )

    def _prepared_payload(
        self, state: SessionState, attempt_id: str
    ) -> dict[str, Any] | None:
        event_id = f"{_PREPARED_EVENT_PREFIX}{attempt_id}"
        if self._supports_scoped:
            event = self._repository.get_event_for_learner(state.learner_id, event_id)
        else:  # pragma: no cover - degraded legacy repositories only
            event = self._repository.get_event(event_id)
        if event is None:
            return None
        payload = event.payload
        if not isinstance(payload, Mapping):
            raise ValidationError(
                f"stored ASSESSMENT_PREPARED event for attempt {attempt_id!r} is corrupted"
            )
        return dict(payload)

    def _decode_prepared(
        self, attempt_id: str, payload: Mapping[str, Any]
    ) -> _PreparedAttempt:
        where = f"stored ASSESSMENT_PREPARED event for attempt {attempt_id!r}"
        expected = (
            "attempt_id",
            "learner_id",
            "session_id",
            "result_id",
            "item_id",
            "turn_index",
            "response_digest",
            "response_kind",
            "canonical_response",
            "session_version",
        )
        missing = [key for key in expected if key not in payload]
        if missing:
            raise ValidationError(f"{where}: missing field(s) {missing}")
        turn_index = payload["turn_index"]
        if type(turn_index) is not int or turn_index < 0:
            raise ValidationError(f"{where}: invalid turn_index {turn_index!r}")
        for key in expected:
            if key == "turn_index":
                continue
            if type(payload[key]) is not str or not payload[key]:
                raise ValidationError(f"{where}: expected a non-blank string for {key!r}")
        if payload["attempt_id"] != attempt_id:
            raise ValidationError(f"{where}: attempt_id does not match the event id")
        canonical = payload["canonical_response"]
        prepared_digest = payload.get("request_digest")
        if type(prepared_digest) is not str or len(prepared_digest) != 64:
            # Pre-B-PR3 prepared events only carried the 16-hex response_digest;
            # the full digest is a deterministic function of the canonical
            # response, so it can be recomputed without guessing.
            prepared_digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        raw_scope = payload.get("scope")
        if raw_scope is not None:
            scope = ResultScope.from_dict(raw_scope)
            if (
                scope.learner_id != payload["learner_id"]
                or scope.session_id != payload["session_id"]
                or scope.item_id != payload["item_id"]
                or scope.result_id != payload["result_id"]
                or scope.turn_index != turn_index
            ):
                raise ValidationError(f"{where}: embedded scope does not match the attempt")
        else:
            scope = ResultScope(
                learner_id=payload["learner_id"],
                session_id=payload["session_id"],
                item_id=payload["item_id"],
                turn_index=turn_index,
                result_id=payload["result_id"],
                request_digest=prepared_digest,
            )
        return _PreparedAttempt(
            attempt_id=attempt_id,
            learner_id=payload["learner_id"],
            session_id=payload["session_id"],
            result_id=payload["result_id"],
            item_id=payload["item_id"],
            turn_index=turn_index,
            response_digest=payload["response_digest"],
            response_kind=payload["response_kind"],
            canonical_response=canonical,
            session_version=payload["session_version"],
            event_id=f"{_PREPARED_EVENT_PREFIX}{attempt_id}",
            request_digest=prepared_digest,
            scope=scope,
        )

    def _assert_attempt_matches_request(
        self,
        prepared: _PreparedAttempt,
        state: SessionState,
        item: AssessmentItem,
        request_digest_value: str,
        requested_result_id: str | None,
    ) -> None:
        def _conflict(reason: str, detail: str) -> None:
            raise ConflictError(
                f"submit_response(): idempotency conflict for attempt "
                f"{prepared.attempt_id!r}: {detail}",
                code=IDEMPOTENCY_CONFLICT,
                details={
                    "reason": reason,
                    "requested_scope": {
                        "learner_id": state.learner_id,
                        "session_id": state.session_id,
                        "item_id": item.item_id,
                        "turn_index": state.turn_index,
                        "result_id": requested_result_id or prepared.result_id,
                    },
                    "policy_version": IDEMPOTENCY_POLICY_VERSION,
                },
            )

        if (
            prepared.learner_id != state.learner_id
            or prepared.session_id != state.session_id
            or prepared.item_id != item.item_id
            or prepared.turn_index != state.turn_index
        ):
            _conflict(
                "ATTEMPT_PAYLOAD_MISMATCH",
                "prepared attempt belongs to a different learner/session/item/turn",
            )
        if prepared.request_digest != request_digest_value:
            _conflict(
                "REQUEST_DIGEST_MISMATCH",
                "the same attempt was already prepared with a different response",
            )
        if requested_result_id is not None and requested_result_id != prepared.result_id:
            _conflict(
                "ATTEMPT_PAYLOAD_MISMATCH",
                "the same attempt was already prepared with a different result_id",
            )

    # -- B-NEXT: crash recovery -------------------------------------------

    def recover_session(self, session_id: str) -> RecoveryReport:
        """Complete prepared-but-uncommitted assessment turns from the event log.

        Algorithm (deterministic, idempotent):

        1. load the session and collect ``ASSESSMENT_PREPARED`` events for it
           that have no terminal ``ASSESSED``/``ERROR`` event;
        2. for each attempt, verify the persisted ``pending_item_id`` and
           ``turn_index`` still match the prepared attempt (otherwise record an
           explicit ``RECOVERY_STATE_INCONSISTENT`` ``ERROR`` event and keep the
           session untouched);
        3. re-score the persisted canonical response with the injected scorer
           (outside any transaction) and require the same deterministic
           ``result_id``/item/learner identity; a scorer failure or identity
           mismatch is recorded as ``RECOVERY_SCORER_ERROR`` /
           ``RECOVERY_SCORER_MISMATCH`` and the session stays pending (**no
           false completion**);
        4. commit the terminal events + snapshot + next session through the same
           atomic API as a normal turn.

        Repeating the call after a successful recovery writes **zero** events
        (the terminal events are found first) and returns
        ``status="ALREADY_CONSISTENT"``.
        """

        if not self._supports_txn:
            raise UnsupportedOperationError(
                "recover_session(): the repository does not support transactional "
                "teaching-turn commits; the legacy flow has no recovery guarantee",
                code="RECOVERY_UNSUPPORTED",
            )
        session_id = _require_nonempty_str(
            session_id, "TeachingSessionEngine.recover_session()"
        )
        state = self._load_session(session_id)
        learner_id = state.learner_id
        events_before = len(self._events(learner_id))
        unresolved = self._unresolved_prepared_attempts(state)
        if not unresolved:
            return RecoveryReport(
                session_id=session_id,
                learner_id=learner_id,
                status="ALREADY_CONSISTENT",
                prepared_attempts=0,
                recovered_attempts=0,
                pending_attempt_ids=(),
                error_codes=(),
                events_appended=0,
            )
        recovered = 0
        pending_ids: list[str] = []
        error_codes: list[str] = []
        for prepared in unresolved:
            fresh = self._load_session(session_id)
            prepared_scope = self._prepared_scope(prepared)
            if self._lookup_result_for_scope(prepared_scope) is not None:
                recovered += 1
                continue
            if (
                fresh.pending_item_id != prepared.item_id
                or fresh.turn_index != prepared.turn_index
            ):
                code = "RECOVERY_STATE_INCONSISTENT"
                error_codes.append(code)
                pending_ids.append(prepared.attempt_id)
                self._record_recovery_error(
                    fresh,
                    prepared,
                    code,
                    "session pending_item_id/turn_index does not match the prepared attempt",
                )
                continue
            item = self._items_by_id.get(prepared.item_id)
            if item is None:
                code = "RECOVERY_UNKNOWN_ITEM"
                error_codes.append(code)
                pending_ids.append(prepared.attempt_id)
                self._record_recovery_error(
                    fresh, prepared, code, "the prepared item is not in the domain"
                )
                continue
            try:
                response = self._decode_prepared_response(prepared)
                result = self._rescore_for_recovery(fresh, item, response, prepared)
            except _RecoveryFailure as exc:
                error_codes.append(exc.code)
                pending_ids.append(prepared.attempt_id)
                self._record_recovery_error(fresh, prepared, exc.code, exc.detail)
                continue
            try:
                self._commit_result_turn(fresh, item, result, prepared_scope)
            except ConflictError as exc:
                if self._lookup_result_for_scope(prepared_scope) is not None:
                    recovered += 1
                    continue
                code = f"RECOVERY_{getattr(exc, 'code', 'CONFLICT')}"
                error_codes.append(code)
                pending_ids.append(prepared.attempt_id)
                self._record_recovery_error(fresh, prepared, code, str(exc))
                continue
            except Exception as exc:  # noqa: BLE001 - fail closed with a reason
                code = "RECOVERY_INTERNAL_ERROR"
                error_codes.append(code)
                pending_ids.append(prepared.attempt_id)
                self._record_recovery_error(fresh, prepared, code, repr(exc))
                continue
            recovered += 1
        if recovered == len(unresolved) and not error_codes:
            status = "RECOVERED"
        elif recovered == 0:
            status = "FAILED"
        else:
            status = "PARTIAL"
        return RecoveryReport(
            session_id=session_id,
            learner_id=learner_id,
            status=status,
            prepared_attempts=len(unresolved),
            recovered_attempts=recovered,
            pending_attempt_ids=tuple(pending_ids),
            error_codes=tuple(error_codes),
            events_appended=len(self._events(learner_id)) - events_before,
        )

    def recover_pending_turns(self, learner_id: str) -> list[RecoveryReport]:
        """Recover every session of ``learner_id`` that has prepared attempts."""

        if not self._supports_txn:
            raise UnsupportedOperationError(
                "recover_pending_turns(): the repository does not support "
                "transactional teaching-turn commits",
                code="RECOVERY_UNSUPPORTED",
            )
        learner_id = _require_nonempty_str(
            learner_id, "TeachingSessionEngine.recover_pending_turns()"
        )
        list_sessions = getattr(self._repository, "list_sessions", None)
        if not callable(list_sessions):
            raise UnsupportedOperationError(
                "recover_pending_turns(): the repository does not expose list_sessions()",
                code="RECOVERY_UNSUPPORTED",
            )
        reports: list[RecoveryReport] = []
        for session in list_sessions(learner_id):
            if not isinstance(session, SessionState):
                raise ValidationError(
                    "recover_pending_turns(): list_sessions() returned a non-SessionState"
                )
            report = self.recover_session(session.session_id)
            if report.prepared_attempts:
                reports.append(report)
        return reports

    def _unresolved_prepared_attempts(
        self, state: SessionState
    ) -> list[_PreparedAttempt]:
        attempts: list[_PreparedAttempt] = []
        seen: set[str] = set()
        for event in self._session_events(state):
            if event.event_type != "ASSESSMENT_PREPARED":
                continue
            payload = event.payload
            if not isinstance(payload, Mapping):
                raise ValidationError(
                    "corrupted ASSESSMENT_PREPARED event payload (not an object)"
                )
            attempt_id = payload.get("attempt_id")
            if type(attempt_id) is not str or not attempt_id:
                raise ValidationError(
                    "corrupted ASSESSMENT_PREPARED event payload (missing attempt_id)"
                )
            if attempt_id in seen:
                continue
            seen.add(attempt_id)
            prepared = self._decode_prepared(attempt_id, payload)
            if self._lookup_result_for_scope(self._prepared_scope(prepared)) is None:
                attempts.append(prepared)
        return attempts

    def _decode_prepared_response(self, prepared: _PreparedAttempt):
        kind = prepared.response_kind
        canonical = prepared.canonical_response
        if kind == "text":
            return canonical
        if kind == "structured":
            try:
                return json.loads(canonical)
            except json.JSONDecodeError:
                raise _RecoveryFailure(
                    "RECOVERY_RESPONSE_CORRUPT",
                    "persisted structured response is not valid JSON",
                ) from None
        return canonical

    def _rescore_for_recovery(
        self,
        state: SessionState,
        item: AssessmentItem,
        response: Any,
        prepared: _PreparedAttempt,
    ) -> AssessmentResult:
        try:
            result = self._scorer.score(
                item, state.learner_id, response, result_id=prepared.result_id
            )
        except Exception as exc:  # noqa: BLE001 - recovery must fail closed, not crash
            raise _RecoveryFailure(
                "RECOVERY_SCORER_ERROR", f"scorer raised {type(exc).__name__}"
            ) from None
        if not isinstance(result, AssessmentResult):
            raise _RecoveryFailure(
                "RECOVERY_SCORER_MISMATCH", "scorer returned a non-AssessmentResult"
            )
        if (
            result.result_id != prepared.result_id
            or result.item_id != prepared.item_id
            or result.learner_id != state.learner_id
        ):
            raise _RecoveryFailure(
                "RECOVERY_SCORER_MISMATCH",
                "re-scored result identity differs from the persisted attempt "
                f"(persisted result_id={prepared.result_id!r}, "
                f"re-scored result_id={result.result_id!r})",
            )
        return result

    def _record_recovery_error(
        self,
        state: SessionState,
        prepared: _PreparedAttempt,
        code: str,
        detail: str,
    ) -> None:
        """Append one deterministic, explainable RECOVERY ``ERROR`` event."""

        event_id = f"{_RECOVERY_ERROR_EVENT_PREFIX}{prepared.attempt_id}"
        if self._repository.get_event(event_id) is not None:
            return
        payload = {
            "stage": "RECOVERY",
            "status": code,
            "attempt_id": prepared.attempt_id,
            "result_id": prepared.result_id,
            "item_id": prepared.item_id,
            "turn_index": prepared.turn_index,
            "response_digest": prepared.response_digest,
            "detail": str(detail)[:500],
            "mastery_unchanged": True,
            "session_unchanged": True,
        }
        for _attempt in range(2):
            seq = self._next_event_seq(state.learner_id)
            event = HistoryEvent(
                event_id=event_id,
                learner_id=state.learner_id,
                session_id=state.session_id,
                seq=seq,
                event_type="ERROR",
                payload=payload,
                created_at=now_utc(),
            )
            try:
                self._repository.append_event(event)
                return
            except ConflictError as exc:
                if getattr(exc, "code", "") == _EVENT_SEQ_CONFLICT:
                    continue
                raise
        return

    # -- convenience loop --------------------------------------------------
    def run_until_goal(
        self,
        session_id: str,
        max_turns: int | None = None,
        responder: Callable[[AssessmentItem, SessionState], str | dict] | None = None,
    ) -> SessionState:
        """Drive the session deterministically (used by E2E tests/demo).

        ``responder`` is a deterministic mock learner: it receives the presented
        item and the current session state and returns a response.  Without a
        responder the loop stops at the first pending item and returns the state
        so the caller can submit the answer itself.
        """

        limit = _require_int(
            self._policy.max_turns if max_turns is None else max_turns,
            "run_until_goal(max_turns)",
            minimum=1,
        )
        if responder is not None and not callable(responder):
            raise ValidationError("run_until_goal(responder=...): expected a callable or None")
        actions = 0
        while actions < self._policy.max_actions_per_run:
            state = self._load_session(session_id)
            if state.phase in {PHASE_COMPLETE, PHASE_PAUSED}:
                return state
            if state.turn_index >= limit:
                return state
            if state.pending_item_id is not None:
                if responder is None:
                    return state
                item = self._items_by_id.get(state.pending_item_id)
                if item is None:  # pragma: no cover - pending ids are validated on write
                    raise NotFoundError(
                        f"run_until_goal(): pending item {state.pending_item_id!r} is unknown"
                    )
                response = responder(item, state)
                self.submit_response(session_id, item.item_id, response)
                actions += 1
                continue
            action = self.current_action(session_id)
            if action.kind == "GOAL_COMPLETE":
                return self._load_session(session_id)
            if action.item_id is not None:
                actions += 1
                continue
            self.advance_session(session_id)
            actions += 1
        return self._load_session(session_id)

    # -- introspection helpers ---------------------------------------------
    def phase_history(self, session_id: str) -> list[str]:
        """Recorded phase sequence of a session (for tests and audit traces).

        ``ASSESS`` and ``UPDATE`` are internal phases executed inside
        :meth:`submit_response`; they are reconstructed from the event log
        (``RESPONSE_SUBMITTED`` -> ASSESS, ``ASSESSED`` -> UPDATE).
        """

        state = self._load_session(session_id)
        phases: list[str] = []
        for event in self._events(state.learner_id):
            if event.session_id != session_id:
                continue
            if event.event_type == "SESSION_STARTED":
                phase = event.payload.get("phase")
                if phase in SESSION_PHASE_VALUES:
                    phases.append(phase)
            elif event.event_type == "DIAGNOSIS_COMPLETED":
                phases.append(PHASE_DIAGNOSE)
            elif event.event_type == "ACTION_TAKEN":
                phase = event.payload.get("phase")
                if phase in SESSION_PHASE_VALUES:
                    phases.append(phase)
            elif event.event_type == "RESPONSE_SUBMITTED":
                phases.append(PHASE_ASSESS)
            elif event.event_type == "ASSESSED":
                phases.append(PHASE_UPDATE)
            elif event.event_type == "MASTERY_UPDATED":
                phases.append(PHASE_REVIEW)
            elif event.event_type == "GOAL_COMPLETED":
                phases.append(PHASE_COMPLETE)
            elif event.event_type == "SESSION_PAUSED":
                phases.append(PHASE_PAUSED)
            elif event.event_type == "SESSION_RESUMED":
                phase = event.payload.get("phase")
                if phase in SESSION_PHASE_VALUES:
                    phases.append(phase)
        return phases

    # ------------------------------------------------------------------
    # Internal: persistence helpers
    # ------------------------------------------------------------------
    def _load_session(self, session_id: str) -> SessionState:
        session_id = _require_nonempty_str(
            session_id, "TeachingSessionEngine(session_id)"
        )
        state = self._repository.load_session(session_id)
        if state is None:
            raise NotFoundError(f"unknown session_id {session_id!r}")
        return state

    def _current_snapshot(self, learner_id: str) -> LearnerSnapshot:
        snapshot = self._repository.get_snapshot(learner_id)
        if snapshot is not None:
            return snapshot
        return self._history.model.initial_snapshot(learner_id)

    def _events(self, learner_id: str) -> list[HistoryEvent]:
        events = self._repository.list_events(learner_id)
        if type(events) is not list or not all(
            isinstance(event, HistoryEvent) for event in events
        ):  # pragma: no cover - protocol invariant
            raise ValidationError("repository.list_events() must return list[HistoryEvent]")
        return sorted(events, key=lambda event: event.seq)

    def _session_events(self, state: SessionState) -> list[HistoryEvent]:
        return [event for event in self._events(state.learner_id) if event.session_id == state.session_id]

    def _save_state(
        self,
        state: SessionState,
        *,
        phase: str | None = None,
        turn_index: int | None = None,
        pending_item_id: Any = _KEEP,
    ) -> SessionState:
        new_pending = state.pending_item_id if pending_item_id is _KEEP else pending_item_id
        new_state = SessionState(
            session_id=state.session_id,
            learner_id=state.learner_id,
            goal_id=state.goal_id,
            objective_id=state.objective_id,
            phase=state.phase if phase is None else phase,
            turn_index=state.turn_index if turn_index is None else turn_index,
            pending_item_id=new_pending,
            created_at=state.created_at,
            updated_at=now_utc(),
        )
        self._repository.save_session(new_state)
        return new_state

    def _append_event(
        self, state: SessionState, event_type: str, payload: Mapping[str, Any]
    ) -> HistoryEvent:
        return self._history.append_event(
            state.learner_id, state.session_id, event_type, dict(payload)
        )

    def _record_deterministic_events(
        self,
        state: SessionState,
        entries: Sequence[tuple[str, str, Mapping[str, Any]]],
    ) -> list[bool]:
        """Append events with caller-chosen (deterministic) event ids."""

        events = self._events(state.learner_id)
        next_seq = max((event.seq for event in events), default=-1) + 1
        built: list[HistoryEvent] = []
        for offset, (event_id, event_type, payload) in enumerate(entries):
            built.append(
                HistoryEvent(
                    event_id=event_id,
                    learner_id=state.learner_id,
                    session_id=state.session_id,
                    seq=next_seq + offset,
                    event_type=event_type,
                    payload=dict(payload),
                    created_at=now_utc(),
                )
            )
        batch = getattr(self._repository, "append_events", None)
        if callable(batch):
            return list(batch(built))
        return [self._history.record_event(event) for event in built]

    def _record_goal_completed(
        self, state: SessionState, objective: LearningObjective, reason: Reason
    ) -> bool:
        event_id = f"{_GOAL_COMPLETED_EVENT_PREFIX}{objective.objective_id}"
        if self._repository.get_event(event_id) is not None:
            return False
        return self._record_deterministic_events(
            state,
            [
                (
                    event_id,
                    "GOAL_COMPLETED",
                    {
                        "objective_id": objective.objective_id,
                        "reason": reason.to_dict(),
                        "policy_version": self._policy.policy_version,
                    },
                )
            ],
        )[0]

    # ------------------------------------------------------------------
    # Internal: goal / objective / events helpers
    # ------------------------------------------------------------------
    def _goal(self, state: SessionState) -> LearnerGoal:
        goal = self._repository.get_goal(state.goal_id)
        if goal is None:
            raise NotFoundError(f"session {state.session_id!r}: goal {state.goal_id!r} is missing")
        return goal

    def _objective(self, state: SessionState) -> LearningObjective:
        objective = self._objectives_by_id.get(state.objective_id)
        if objective is None:
            raise NotFoundError(
                f"session {state.session_id!r}: objective {state.objective_id!r} is unknown"
            )
        return objective

    # ------------------------------------------------------------------
    # Internal: scoring
    # ------------------------------------------------------------------
    def _default_attempt_result_id(
        self, state: SessionState, item_id: str, response: Any
    ) -> str:
        """Deterministic B-PR3 default result id (``result.v1.<32-hex>``).

        A same-request retry on the same scope regenerates the same id; a
        different learner/session/item/turn/digest never collides in practice.
        """

        return default_result_id(
            state.learner_id, state.session_id, item_id, state.turn_index, response
        )

    @staticmethod
    def _fallback_result(
        item: AssessmentItem,
        learner_id: str,
        result_id: str,
        failure_reason: str,
    ) -> AssessmentResult:
        max_score = float(item.max_score) if item.max_score > 0.0 else 1.0
        return AssessmentResult(
            result_id=result_id,
            item_id=item.item_id,
            learner_id=learner_id,
            status="EVAL_ERROR",
            score=None,
            max_score=max_score,
            scorer_id="m1a.session.scorer-fallback",
            failure_reason=failure_reason,
            evidence_refs=[f"item:{item.item_id}"],
            created_at=now_utc(),
        )

    def _score_safely(
        self,
        item: AssessmentItem,
        learner_id: str,
        response: Any,
        result_id: str | None,
    ) -> AssessmentResult:
        fallback_id = result_id or (
            f"result:{item.item_id}:"
            f"{hashlib.sha256(_canonical_response(response).encode('utf-8')).hexdigest()[:16]}"
        )
        try:
            result = self._scorer.score(item, learner_id, response, result_id=result_id)
        except BaseException:  # noqa: BLE001 - scorer failures are EVAL_ERROR, not e
            return self._fallback_result(item, learner_id, fallback_id, "SCORER_EXCEPTION")
        if not isinstance(result, AssessmentResult):  # pragma: no cover - defensive
            return self._fallback_result(item, learner_id, fallback_id, "SCORER_INVALID_RESULT")
        if result.item_id != item.item_id or result.learner_id != learner_id:
            return self._fallback_result(item, learner_id, fallback_id, "SCORER_RESULT_MISMATCH")
        return result

    # ------------------------------------------------------------------
    # Internal: response branches
    # ------------------------------------------------------------------
    def _handle_eval_error(
        self, state: SessionState, item: AssessmentItem, result: AssessmentResult
    ) -> SessionState:
        events = self._session_events(state)
        retries = self._eval_error_streak(events, item.item_id)
        retries += 1
        exhausted = retries > self._policy.eval_error_retry_limit
        self._record_deterministic_events(
            state,
            [
                (
                    f"{_EVAL_ERROR_EVENT_PREFIX}{result.result_id}",
                    "ERROR",
                    {
                        "stage": "ASSESS",
                        "status": "EVAL_ERROR",
                        "item_id": item.item_id,
                        "result_id": result.result_id,
                        "result": result.to_dict(),
                        "failure_reason": result.failure_reason,
                        "retry_attempt": retries,
                        "retry_exhausted": exhausted,
                        "mastery_unchanged": True,
                    },
                )
            ],
        )
        if exhausted:
            return self._save_state(
                state,
                phase=PHASE_REVIEW,
                turn_index=state.turn_index + 1,
                pending_item_id=None,
            )
        return self._save_state(
            state,
            phase=state.phase,
            turn_index=state.turn_index + 1,
            pending_item_id=item.item_id,
        )

    def _handle_needs_review(
        self,
        state: SessionState,
        item: AssessmentItem,
        result: AssessmentResult,
        snapshot: LearnerSnapshot,
    ) -> SessionState:
        self._record_deterministic_events(
            state,
            [
                (
                    assessed_event_id(result.result_id),
                    "ASSESSED",
                    {
                        "result_id": result.result_id,
                        "item_id": item.item_id,
                        "status": result.status,
                        "result": result.to_dict(),
                        "item": item.to_dict(),
                    },
                ),
                (
                    mastery_updated_event_id(result.result_id),
                    "MASTERY_UPDATED",
                    {
                        "result_id": result.result_id,
                        "status": result.status,
                        "applied": False,
                        "snapshot": snapshot.to_dict(),
                        "policy_version": self._history.model.policy.policy_version,
                        "reason": "NEEDS_REVIEW is not observed mastery evidence",
                    },
                ),
            ],
        )
        return self._save_state(
            state,
            phase=PHASE_REVIEW,
            turn_index=state.turn_index + 1,
            pending_item_id=None,
        )

    def _handle_observed_result(
        self,
        state: SessionState,
        item: AssessmentItem,
        result: AssessmentResult,
        snapshot: LearnerSnapshot,
    ) -> SessionState:
        updated = self._history.apply_assessment(
            state.learner_id, state.session_id, item, result, snapshot=snapshot
        )
        objective = self._objective(state)
        complete, completion_reason = self._planner.check_goal_completion(objective, updated)
        if complete:
            self._record_goal_completed(state, objective, completion_reason)
            return self._save_state(
                state,
                phase=PHASE_COMPLETE,
                turn_index=state.turn_index + 1,
                pending_item_id=None,
            )
        return self._save_state(
            state,
            phase=PHASE_REVIEW,
            turn_index=state.turn_index + 1,
            pending_item_id=None,
        )

    def _eval_error_streak(self, events: Sequence[HistoryEvent], item_id: str) -> int:
        last_assessed = -1
        for index, event in enumerate(events):
            if event.event_type == "ASSESSED" and event.payload.get("item_id") == item_id:
                last_assessed = index
        streak = 0
        for event in events[last_assessed + 1 :]:
            if (
                event.event_type == "ERROR"
                and event.payload.get("status") == "EVAL_ERROR"
                and event.payload.get("item_id") == item_id
            ):
                streak += 1
        return streak

    # ------------------------------------------------------------------
    # Internal: action generation
    # ------------------------------------------------------------------
    def _action_for_current_turn(self, state: SessionState) -> TeachingAction | None:
        for event in reversed(self._session_events(state)):
            if event.event_type != "ACTION_TAKEN":
                continue
            if event.payload.get("turn_index") != state.turn_index:
                continue
            raw = event.payload.get("action")
            if not isinstance(raw, Mapping):
                continue
            try:
                action = TeachingAction.from_dict(dict(raw))
            except ValidationError:
                continue
            if action.action_id:
                return action
        return None

    def _generate_and_persist(
        self, state: SessionState
    ) -> tuple[SessionState, TeachingAction]:
        snapshot = self._current_snapshot(state.learner_id)
        events = self._events(state.learner_id)
        selection = self._select_action(state, snapshot, events)
        action, phase, pending_item_id, extra_events = selection
        self._append_event(
            state,
            "ACTION_TAKEN",
            {
                "action": action.to_dict(),
                "action_kind": action.kind,
                "node_ids": list(action.node_ids),
                "item_id": action.item_id,
                "phase": phase,
                "turn_index": state.turn_index,
                "snapshot_revision": snapshot.revision,
                "session_policy_version": self._policy.policy_version,
            },
        )
        for event_type, payload in extra_events:
            self._append_event(state, event_type, payload)
        if phase == PHASE_COMPLETE:
            objective = self._objective(state)
            _complete, reason = self._planner.check_goal_completion(objective, snapshot)
            self._record_goal_completed(state, objective, reason)
        new_state = self._save_state(
            state,
            phase=phase,
            turn_index=state.turn_index,
            pending_item_id=pending_item_id,
        )
        return new_state, action

    def _select_action(
        self,
        state: SessionState,
        snapshot: LearnerSnapshot,
        events: Sequence[HistoryEvent],
    ) -> tuple[TeachingAction, str, str | None, list[tuple[str, dict[str, Any]]]]:
        """Choose the next action and its target phase (pure, no writes)."""

        goal = self._goal(state)
        objective = self._objective(state)
        extra_events: list[tuple[str, dict[str, Any]]] = []

        # 1) Resume/retry of an item that is still pending (pause or EVAL_ERROR).
        if state.pending_item_id is not None:
            item = self._items_by_id.get(state.pending_item_id)
            if item is None:
                raise NotFoundError(
                    f"session {state.session_id!r}: pending item "
                    f"{state.pending_item_id!r} is unknown"
                )
            kind = self._pending_action_kind(state)
            phase = _ITEM_ACTION_PHASES.get(kind, PHASE_PRACTICE)
            action = self._item_action(
                state,
                snapshot,
                item=item,
                kind=kind,
                phase=phase,
                reason=self._reason(
                    state,
                    "RETRY_PENDING_ITEM",
                    item.node_ids,
                    "the pending item was not scored successfully yet; retry it",
                ),
            )
            return action, phase, item.item_id, []

        # 2) Completes the objective as soon as the observed criteria are met.
        complete, completion_reason = self._planner.check_goal_completion(objective, snapshot)
        if complete:
            return (
                self._complete_action(state),
                PHASE_COMPLETE,
                None,
                [],
            )

        # 3) Hint escalation after repeated INCORRECT outcomes (before the next
        #    diagnostic/plan step, so a struggling learner gets support first).
        hint = self._hint_selection(state, events)
        if hint is not None:
            level, node_ids = hint
            action = self._hint_action(state, snapshot, level=level, node_ids=node_ids)
            return action, PHASE_REVIEW, None, extra_events

        # 4) Diagnostic phase (first ``diagnosis_min_items`` observations).
        diagnostic_attempts = self._diagnostic_attempt_count(state)
        attempted_items = self._attempted_item_ids(state, events)
        diagnosis = self._diagnostic.select_next_item(
            goal,
            objective,
            snapshot,
            history=list(events),
            exclude_item_ids=attempted_items,
        )
        if diagnosis.status == READY and diagnostic_attempts < self._policy.diagnosis_min_items:
            item_id = diagnosis.selected_item_id
            if item_id is not None and item_id in self._items_by_id:
                item = self._items_by_id[item_id]
                extra_events.append(
                    ("DIAGNOSIS_COMPLETED", {"diagnosis": diagnosis.to_dict()})
                )
                action = self._item_action(
                    state,
                    snapshot,
                    item=item,
                    kind="DIAGNOSE",
                    phase=PHASE_DIAGNOSE,
                    reason=self._reason(
                        state,
                        "DIAGNOSTIC_ITEM",
                        [diagnosis.target_node_id],
                        diagnosis.hypothesis or "diagnostic item selected",
                    ),
                )
                return action, PHASE_DIAGNOSE, item.item_id, extra_events
        if diagnosis.status == INSUFFICIENT_EVIDENCE and diagnostic_attempts == 0:
            # No evidence gap remains at all: the plan/evidence state decides.
            extra_events.append(
                ("DIAGNOSIS_COMPLETED", {"diagnosis": diagnosis.to_dict()})
            )

        # 5) Sustained INCORRECT outcomes force a reassessment of the struggling
        #    node(s) before any further teaching/practice.
        streak, struggling_nodes = self._consecutive_incorrect(state)
        if streak >= self._policy.reassess_after_incorrect and struggling_nodes:
            attempted = self._attempted_item_ids(state, events)
            for node_id in struggling_nodes:
                for item in self._domain.assessment_items(node_id):
                    if item.item_id in attempted:
                        continue
                    action = self._item_action(
                        state,
                        snapshot,
                        item=item,
                        kind="REASSESS",
                        phase=PHASE_ASSESS,
                        reason=self._reason(
                            state,
                            "REASSESS_STUCK_NODE",
                            [node_id],
                            f"{streak} consecutive INCORRECT outcomes; reassess before "
                            "drilling the same content again",
                        ),
                    )
                    return action, PHASE_ASSESS, item.item_id, extra_events

        # 6) Plan-driven selection (skip steps already presented for this revision).
        plan = self._planner.plan(goal, objective, snapshot, history=list(events))
        extra_events.append(
            ("PLAN_CREATED", {"plan_id": plan.plan_id, "step_count": len(plan.steps),
                              "policy_version": plan.policy_version})
        )
        taken = self._taken_step_signatures(state, snapshot.revision)
        for step in plan.steps:
            if step.action_kind == "GOAL_COMPLETE":
                return self._complete_action(state), PHASE_COMPLETE, None, []
            signature = (
                step.phase,
                step.action_kind,
                tuple(step.node_ids),
                step.item_id,
            )
            if signature in taken:
                continue
            if step.action_kind == "PRACTICE" and self._practice_actions_since_assessment(
                state, step.node_ids
            ) >= self._policy.max_practice_attempts:
                # Too much drilling without observed evidence: skip the practice
                # step so the following assessment step is surfaced instead.
                continue
            mapped = self._action_from_plan_step(state, plan.plan_id, step, snapshot)
            if mapped is None:
                continue
            action, phase, pending_item_id = mapped
            return action, phase, pending_item_id, extra_events

        # 6) Fallback: keep the session moving with an untried practice item.
        fallback = self._fallback_action(state, snapshot, plan.plan_id)
        if fallback is not None:
            action, phase, pending_item_id = fallback
            return action, phase, pending_item_id, extra_events
        raise ConflictError(
            f"session {state.session_id!r}: no actionable plan step remains and the "
            "objective is not complete"
        )

    def _diagnostic_attempt_count(self, state: SessionState) -> int:
        """Observed diagnostic items (EVAL_ERROR retries are not extra attempts)."""

        diagnostic_item_ids: set[str] = set()
        for event in self._session_events(state):
            if (
                event.event_type == "ACTION_TAKEN"
                and event.payload.get("phase") == PHASE_DIAGNOSE
                and type(event.payload.get("item_id")) is str
            ):
                diagnostic_item_ids.add(event.payload["item_id"])
        if not diagnostic_item_ids:
            return 0
        assessed: set[str] = set()
        for event in self._session_events(state):
            if event.event_type == "ASSESSED" and type(event.payload.get("item_id")) is str:
                assessed.add(event.payload["item_id"])
        return len(diagnostic_item_ids & assessed)

    def _practice_actions_since_assessment(
        self, state: SessionState, node_ids: Sequence[str]
    ) -> int:
        count = 0
        for event in reversed(self._session_events(state)):
            if event.event_type in {"ASSESSED", "MASTERY_UPDATED"}:
                break
            if (
                event.event_type == "ACTION_TAKEN"
                and event.payload.get("action_kind") == "PRACTICE"
                and event.payload.get("item_id") is not None
            ):
                payload_nodes = event.payload.get("node_ids")
                if not isinstance(payload_nodes, list):
                    continue
                if set(payload_nodes) & set(node_ids):
                    count += 1
        return count

    def _pending_action_kind(self, state: SessionState) -> str:
        for event in reversed(self._session_events(state)):
            if event.event_type != "ACTION_TAKEN":
                continue
            if event.payload.get("item_id") != state.pending_item_id:
                continue
            kind = event.payload.get("action_kind")
            if type(kind) is str and kind in _ITEM_ACTION_PHASES:
                return kind
        if state.phase == PHASE_DIAGNOSE:
            return "DIAGNOSE"
        return "PRACTICE"

    def _attempted_item_ids(
        self, state: SessionState, events: Sequence[HistoryEvent]
    ) -> set[str]:
        attempted: set[str] = set()
        for event in events:
            if event.event_type != "ASSESSED":
                continue
            item_id = event.payload.get("item_id")
            if type(item_id) is str:
                attempted.add(item_id)
        if state.pending_item_id is not None:
            attempted.add(state.pending_item_id)
        return attempted

    def _taken_step_signatures(
        self, state: SessionState, revision: int
    ) -> set[tuple[str, str, tuple[str, ...], str | None]]:
        taken: set[tuple[str, str, tuple[str, ...], str | None]] = set()
        for event in self._session_events(state):
            if event.event_type != "ACTION_TAKEN":
                continue
            if event.payload.get("snapshot_revision") != revision:
                continue
            phase = event.payload.get("phase")
            kind = event.payload.get("action_kind")
            raw_nodes = event.payload.get("node_ids")
            raw_item = event.payload.get("item_id")
            if type(phase) is not str or type(kind) is not str or type(raw_nodes) is not list:
                continue
            taken.add(
                (
                    phase,
                    kind,
                    tuple(node for node in raw_nodes if type(node) is str),
                    raw_item if type(raw_item) is str else None,
                )
            )
        return taken

    # -- action builders ---------------------------------------------------
    def _reason(
        self,
        state: SessionState,
        code: str,
        node_ids: Sequence[str],
        detail: str,
    ) -> Reason:
        return Reason(
            code=code,
            node_ids=[node for node in node_ids if type(node) is str],
            detail=detail,
            policy_version=self._policy.policy_version,
            created_at=state.updated_at,
        )

    def _action_id(
        self,
        state: SessionState,
        kind: str,
        node_ids: Sequence[str],
        item_id: str | None,
        discriminator: str = "",
    ) -> str:
        return "action:" + _fingerprint(
            state.session_id,
            state.turn_index,
            kind,
            list(node_ids),
            item_id,
            discriminator,
            self._policy.policy_version,
        )

    def _build_action(
        self,
        state: SessionState,
        *,
        kind: str,
        node_ids: Sequence[str],
        content: str,
        reason: Reason,
        item_id: str | None = None,
        evidence_refs: Sequence[str] = (),
        discriminator: str = "",
    ) -> TeachingAction:
        return TeachingAction(
            action_id=self._action_id(state, kind, node_ids, item_id, discriminator),
            kind=kind,
            node_ids=list(node_ids),
            content=content,
            reason=reason,
            item_id=item_id,
            evidence_refs=list(evidence_refs),
        )

    def _item_action(
        self,
        state: SessionState,
        snapshot: LearnerSnapshot,
        *,
        item: AssessmentItem,
        kind: str,
        phase: str,
        reason: Reason,
    ) -> TeachingAction:
        return self._build_action(
            state,
            kind=kind,
            node_ids=list(item.node_ids),
            content=item.prompt,
            item_id=item.item_id,
            reason=reason,
            evidence_refs=[
                f"snapshot:{state.learner_id}:revision={snapshot.revision}",
                f"item:{item.item_id}",
            ],
            discriminator=phase,
        )

    def _hint_action(
        self,
        state: SessionState,
        snapshot: LearnerSnapshot,
        *,
        level: int,
        node_ids: Sequence[str],
    ) -> TeachingAction:
        node_id = sorted(node_ids)[0] if node_ids else self._objective(state).target_node_ids[0]
        content = self._domain.teaching_content(node_id, f"HINT_L{level}")
        reason = self._reason(
            state,
            f"HINT_LEVEL_{level}",
            [node_id],
            f"escalated hint to level {level} after repeated INCORRECT outcomes",
        )
        return self._build_action(
            state,
            kind="HINT",
            node_ids=[node_id],
            content=content,
            reason=reason,
            evidence_refs=[f"snapshot:{state.learner_id}:revision={snapshot.revision}"],
            discriminator=f"HINT_L{level}",
        )

    def _complete_action(self, state: SessionState) -> TeachingAction:
        objective = self._objective(state)
        snapshot = self._current_snapshot(state.learner_id)
        _complete, reason = self._planner.check_goal_completion(objective, snapshot)
        return self._build_action(
            state,
            kind="GOAL_COMPLETE",
            node_ids=list(reason.node_ids),
            content=(
                f"目标 {objective.objective_id} 的成功标准已由观测证据满足；会话结束。"
            ),
            reason=reason,
            evidence_refs=[f"snapshot:{state.learner_id}:revision={snapshot.revision}"],
            discriminator="GOAL_COMPLETE",
        )

    def _action_from_plan_step(
        self,
        state: SessionState,
        plan_id: str,
        step: Any,
        snapshot: LearnerSnapshot,
    ) -> tuple[TeachingAction, str, str | None] | None:
        node_ids = list(step.node_ids)
        if not node_ids:
            return None
        primary = node_ids[0]
        refs = [f"plan:{plan_id}", f"step:{step.step_id}"]
        if step.action_kind in {"EXPLAIN", "RETEACH"}:
            content = self._domain.teaching_content(primary, "EXPLAIN")
            reason = step.rationale
            action = self._build_action(
                state,
                kind=step.action_kind,
                node_ids=node_ids,
                content=content,
                reason=reason,
                evidence_refs=refs,
                discriminator=step.step_id,
            )
            return action, PHASE_TEACH, None
        if step.action_kind == "REVIEW":
            content = self._domain.teaching_content(primary, "REVIEW")
            action = self._build_action(
                state,
                kind="REVIEW",
                node_ids=node_ids,
                content=content,
                reason=step.rationale,
                evidence_refs=refs,
                discriminator=step.step_id,
            )
            return action, PHASE_REVIEW, None
        item_id = step.item_id or self._assigned_item_id(step, snapshot)
        if item_id is None or item_id not in self._items_by_id:
            return None
        item = self._items_by_id[item_id]
        if step.action_kind == "PRACTICE":
            phase = PHASE_PRACTICE
            action_kind = "PRACTICE"
        else:  # DIAGNOSE / REASSESS / ASSESS plan steps present an item in ASSESS
            phase = PHASE_ASSESS
            action_kind = step.action_kind if step.action_kind in _ITEM_ACTION_PHASES else "REASSESS"
        action = self._item_action(
            state,
            snapshot,
            item=item,
            kind=action_kind,
            phase=phase,
            reason=step.rationale,
        )
        return action, phase, item.item_id

    def _assigned_item_id(self, step: Any, snapshot: LearnerSnapshot) -> str | None:
        for node_id in step.node_ids:
            candidates = [
                item_id
                for item_id in self._practice_items_by_node.get(node_id, [])
                if item_id not in set(snapshot.completed_item_ids)
            ]
            if candidates:
                return candidates[0]
            practice = self._practice_items_by_node.get(node_id) or []
            if practice:
                return practice[0]
        return None

    def _fallback_action(
        self, state: SessionState, snapshot: LearnerSnapshot, plan_id: str
    ) -> tuple[TeachingAction, str, str | None] | None:
        objective = self._objective(state)
        attempted = self._attempted_item_ids(state, self._events(state.learner_id))
        ranked_nodes = sorted(
            objective.target_node_ids,
            key=lambda node_id: (
                snapshot.masteries.get(node_id).value
                if snapshot.masteries.get(node_id) is not None
                else 0.0,
                node_id,
            ),
        )
        for node_id in ranked_nodes:
            for item in self._domain.assessment_items(node_id):
                if item.item_id in attempted:
                    continue
                action = self._item_action(
                    state,
                    snapshot,
                    item=item,
                    kind="REASSESS",
                    phase=PHASE_ASSESS,
                    reason=self._reason(
                        state,
                        "SESSION_CONTINUE",
                        [node_id],
                        "continue the session with an untried observed-evidence item",
                    ),
                )
                return action, PHASE_ASSESS, item.item_id
        node_id = ranked_nodes[0]
        content = self._domain.teaching_content(node_id, "REVIEW")
        action = self._build_action(
            state,
            kind="REVIEW",
            node_ids=[node_id],
            content=content,
            reason=self._reason(
                state,
                "SESSION_CONTINUE_REVIEW",
                [node_id],
                "no untried item remains; revisit the invariant before re-planning",
            ),
            evidence_refs=[f"plan:{plan_id}"],
            discriminator="fallback-review",
        )
        return action, PHASE_REVIEW, None

    # -- hint escalation helpers ------------------------------------------
    def _consecutive_incorrect(
        self, state: SessionState
    ) -> tuple[int, list[str]]:
        streak = 0
        nodes: list[str] = []
        for event in self._session_events(state):
            if event.event_type != "ASSESSED":
                continue
            status = event.payload.get("status")
            if status == "INCORRECT":
                streak += 1
                item_id = event.payload.get("item_id")
                item = self._items_by_id.get(item_id) if type(item_id) is str else None
                if item is not None:
                    for node_id in item.node_ids:
                        if node_id not in nodes:
                            nodes.append(node_id)
            elif status in {"CORRECT", "PARTIAL"}:
                streak = 0
                nodes = []
            # NEEDS_REVIEW / EVAL_ERROR are not learner evidence: streak unchanged.
        return streak, nodes

    def _offered_hint_level(self, state: SessionState) -> int:
        offered = 0
        reset_index = 0
        session_events = self._session_events(state)
        for index, event in enumerate(session_events):
            if event.event_type == "ASSESSED" and event.payload.get("status") in {
                "CORRECT",
                "PARTIAL",
            }:
                reset_index = index + 1
                offered = 0
        for event in session_events[reset_index:]:
            if event.event_type != "ACTION_TAKEN":
                continue
            raw = event.payload.get("action")
            if not isinstance(raw, Mapping):
                continue
            raw_reason = raw.get("reason")
            if not isinstance(raw_reason, Mapping):
                continue
            code = raw_reason.get("code")
            if type(code) is str and code.startswith("HINT_LEVEL_"):
                try:
                    offered = max(offered, int(code.rsplit("_", 1)[1]))
                except (ValueError, IndexError):  # pragma: no cover - defensive
                    continue
        return offered

    def _hint_selection(
        self, state: SessionState, events: Sequence[HistoryEvent]
    ) -> tuple[int, list[str]] | None:
        streak, nodes = self._consecutive_incorrect(state)
        if streak < 1:
            return None
        desired = min(
            self._policy.max_hint_level,
            1 + streak // self._policy.hint_escalation_threshold,
        )
        if desired <= self._offered_hint_level(state):
            return None
        if not nodes:
            objective = self._objective(state)
            nodes = list(objective.target_node_ids[:1]) or ["cf.search.binary"]
        return desired, nodes

    # ------------------------------------------------------------------
    # Internal: pause helpers
    # ------------------------------------------------------------------
    def _last_pause_phase(self, state: SessionState) -> str | None:
        for event in reversed(self._session_events(state)):
            if event.event_type != "SESSION_PAUSED":
                continue
            phase = event.payload.get("previous_phase")
            if phase in SESSION_PHASE_VALUES and phase != PHASE_PAUSED:
                return phase
        return None


def stream_item(event: HistoryEvent) -> str | None:
    """Return the ``item_id`` referenced by an assessment event payload."""

    item_id = event.payload.get("item_id")
    return item_id if type(item_id) is str else None
