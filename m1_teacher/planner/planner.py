"""Curriculum planner (B4) of the M1-A offline teacher core (``m1a.v0``).

The planner turns a goal, its declarative objective, a
:class:`~m1_teacher.contracts.types.LearnerSnapshot` and (optionally) the
learner's :class:`~m1_teacher.contracts.types.HistoryEvent` log into an ordered
:class:`~m1_teacher.contracts.types.CurriculumPlan` of
:class:`~m1_teacher.contracts.types.PlanStep` records, each with a structured
:class:`~m1_teacher.contracts.types.Reason` explaining *why this node/step and
not another*.

Frozen B-PR3 planning policy (deterministic, no wall clock, no hidden data):

1. **Goal completion first.**  If the objective's ``success_criteria`` are met
   by *observed* mastery/error evidence (never by learner text) the plan is a
   single ``GOAL_COMPLETE`` step.
2. **HARD prerequisites block teaching.**  A strict HARD prerequisite of any
   objective target whose mastery is below
   :attr:`PlannerPolicy.prerequisite_mastery_threshold` is remediated
   (``RETEACH`` then ``PRACTICE``) *before* any target teaching step.  SOFT
   prerequisites are skipped unless
   :attr:`PlannerPolicy.remediate_soft_prerequisites` is enabled.
3. **Stuck nodes are reassessed, not drilled further.**  A node with at least
   :attr:`PlannerPolicy.reassess_after_failures` consecutive ``INCORRECT``
   assessment events, or a remediated node that already consumed
   :attr:`PlannerPolicy.max_relearn_attempts`, gets a ``REASSESS`` step.
4. **Targets are taught/practised/assessed in topological order.**  Objective
   targets are visited in knowledge-graph topological order (prerequisites
   first).  A node with high error pressure starts with practice, a node with
   no evidence starts with teaching, and every visited target is followed by an
   assessment step so progress is measured by observed evidence.
5. **Spaced review.**  A mastered node is reviewed only when its review
   interval is due: at least :attr:`PlannerPolicy.review_interval_turns`
   history turns since its last evidence, or a timestamp gap of at least
   :attr:`PlannerPolicy.review_interval_hours`, or repeated errors.
6. **Bounded and reproducible.**  The plan is capped at
   :attr:`PlannerPolicy.max_steps`; every record uses ``snapshot.updated_at``
   as ``created_at`` and ids derive from a content fingerprint, so the same
   inputs produce a byte-identical ``to_dict()`` replay.

The planner never reads hidden evaluation material and never opens files: it
only consumes the :class:`~m1_teacher.contracts.domain.DomainAdapter` read API.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Sequence

from ..contracts.domain import DomainAdapter
from ..contracts.errors import ValidationError
from ..contracts.types import (
    ITEM_TYPE_VALUES,
    CurriculumPlan,
    HistoryEvent,
    LearnerGoal,
    LearnerSnapshot,
    LearningObjective,
    MasteryEstimate,
    PlanStep,
    Reason,
)
from ..knowledge.graph import KnowledgeGraph

__all__ = [
    "CurriculumPlanner",
    "PlannerPolicy",
    "POLICY_VERSION",
    "REASON_GOAL_COMPLETE",
    "REASON_GOAL_NOT_COMPLETE",
]

POLICY_VERSION = "m1a.planner.v0"

REASON_GOAL_COMPLETE = "GOAL_COMPLETE"
REASON_GOAL_NOT_COMPLETE = "GOAL_NOT_COMPLETE"
REASON_REMEDIATE_HARD_PREREQUISITE = "REMEDIATE_HARD_PREREQUISITE"
REASON_PRACTICE_HARD_PREREQUISITE = "PRACTICE_HARD_PREREQUISITE"
REASON_REMEDIATE_SOFT_PREREQUISITE = "REMEDIATE_SOFT_PREREQUISITE"
REASON_PRACTICE_SOFT_PREREQUISITE = "PRACTICE_SOFT_PREREQUISITE"
REASON_REASSESS_STUCK_NODE = "REASSESS_STUCK_NODE"
REASON_TEACH_TARGET_NODE = "TEACH_TARGET_NODE"
REASON_PRACTICE_TARGET_NODE = "PRACTICE_TARGET_NODE"
REASON_ASSESS_PROGRESS = "ASSESS_PROGRESS"
REASON_REVIEW_DUE = "REVIEW_DUE"
REASON_REVIEW_REPEATED_ERRORS = "REVIEW_REPEATED_ERRORS"
REASON_FALLBACK_CONTINUE = "FALLBACK_CONTINUE"

_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
_PHASE_TEACH = "TEACH"
_PHASE_PRACTICE = "PRACTICE"
_PHASE_ASSESS = "ASSESS"
_PHASE_REVIEW = "REVIEW"
_PHASE_COMPLETE = "COMPLETE"
_ACTION_RETEACH = "RETEACH"
_ACTION_EXPLAIN = "EXPLAIN"
_ACTION_PRACTICE = "PRACTICE"
_ACTION_REASSESS = "REASSESS"
_ACTION_REVIEW = "REVIEW"
_ACTION_GOAL_COMPLETE = "GOAL_COMPLETE"
_ACTION_DIAGNOSE = "DIAGNOSE"
_ASSESSMENT_ITEM_TYPE_PRIORITY: tuple[str, ...] = ("CODE", "MCQ", "SHORT_ANSWER")
_EVIDENCE_HISTORY_TYPES = frozenset({"ASSESSED", "MASTERY_UPDATED"})


# ---------------------------------------------------------------------------
# Small deterministic helpers
# ---------------------------------------------------------------------------


def _fingerprint(*parts: Any) -> str:
    payload = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _require_str(value: Any, where: str) -> str:
    if type(value) is not str or not value.strip():
        raise ValidationError(f"{where}: expected a non-blank string, got {value!r}")
    return value


def _require_int(where: str, value: Any, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValidationError(f"{where}: expected an int >= {minimum}, got {value!r}")
    return value


def _require_unit(where: str, value: Any) -> float:
    if type(value) not in (int, float) or not 0.0 <= float(value) <= 1.0:
        raise ValidationError(f"{where}: expected a number in [0, 1], got {value!r}")
    return float(value)


def _require_bool(where: str, value: Any) -> bool:
    if type(value) is not bool:
        raise ValidationError(f"{where}: expected a bool, got {value!r}")
    return value


def _parse_timestamp(value: str, where: str) -> datetime:
    try:
        return datetime.strptime(value, _TIMESTAMP_FORMAT).replace(tzinfo=timezone.utc)
    except (TypeError, ValueError) as exc:  # pragma: no cover - records validate timestamps
        raise ValidationError(f"{where}: invalid timestamp {value!r}") from exc


# ---------------------------------------------------------------------------
# Planner policy
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PlannerPolicy:
    """Deterministic, injectable planning policy with explicit constants."""

    policy_version: str = POLICY_VERSION
    #: HARD prerequisite mastery below this value triggers remediation.
    prerequisite_mastery_threshold: float = 0.5
    #: Consecutive INCORRECT assessments that trigger a REASSESS step.
    reassess_after_failures: int = 2
    #: Maximum RETEACH cycles for one node before switching to REASSESS.
    max_relearn_attempts: int = 2
    #: Spaced review: minimum history turns since the node's last evidence.
    review_interval_turns: int = 3
    #: Spaced review: minimum timestamp gap since the node's last evidence.
    review_interval_hours: float = 72.0
    #: Mastery at or above this value makes a node eligible for review.
    review_mastery_threshold: float = 0.6
    #: Error count at or above this value forces a review step.
    review_error_threshold: int = 2
    #: Combined error pressure (error counts + consecutive failures) treated
    #: as "struggling, practise first" instead of "teach first".
    struggle_error_threshold: int = 2
    #: Remediate SOFT prerequisite gaps as well (off by default: SOFT gaps are
    #: helpful but not blocking).
    remediate_soft_prerequisites: bool = False
    #: Hard upper bound on plan steps.
    max_steps: int = 8
    #: Minimum observed evidence events required to consider success criteria.
    min_evidence_count: int = 1
    #: Preferred assessment item types (earlier = preferred).
    assessment_item_type_priority: tuple[str, ...] = _ASSESSMENT_ITEM_TYPE_PRIORITY

    def __post_init__(self) -> None:
        _require_str(self.policy_version, "PlannerPolicy.policy_version")
        _require_unit(
            "PlannerPolicy.prerequisite_mastery_threshold",
            self.prerequisite_mastery_threshold,
        )
        _require_int("PlannerPolicy.reassess_after_failures", self.reassess_after_failures,
                     minimum=1)
        _require_int("PlannerPolicy.max_relearn_attempts", self.max_relearn_attempts,
                     minimum=1)
        _require_int("PlannerPolicy.review_interval_turns", self.review_interval_turns,
                     minimum=1)
        if type(self.review_interval_hours) not in (int, float) or self.review_interval_hours <= 0:
            raise ValidationError("PlannerPolicy.review_interval_hours: expected a number > 0")
        _require_unit("PlannerPolicy.review_mastery_threshold", self.review_mastery_threshold)
        _require_int("PlannerPolicy.review_error_threshold", self.review_error_threshold,
                     minimum=1)
        _require_int("PlannerPolicy.struggle_error_threshold", self.struggle_error_threshold,
                     minimum=1)
        _require_bool("PlannerPolicy.remediate_soft_prerequisites",
                      self.remediate_soft_prerequisites)
        _require_int("PlannerPolicy.max_steps", self.max_steps, minimum=1)
        _require_int("PlannerPolicy.min_evidence_count", self.min_evidence_count)
        if type(self.assessment_item_type_priority) is not tuple or not (
            self.assessment_item_type_priority
        ):
            raise ValidationError(
                "PlannerPolicy.assessment_item_type_priority: expected a non-empty tuple"
            )
        for index, item_type in enumerate(self.assessment_item_type_priority):
            if type(item_type) is not str or item_type not in ITEM_TYPE_VALUES:
                raise ValidationError(
                    "PlannerPolicy.assessment_item_type_priority"
                    f"[{index}]: unknown item type {item_type!r}"
                )
        if len(set(self.assessment_item_type_priority)) != len(
            self.assessment_item_type_priority
        ):
            raise ValidationError(
                "PlannerPolicy.assessment_item_type_priority: duplicates"
            )


# ---------------------------------------------------------------------------
# Curriculum planner
# ---------------------------------------------------------------------------


class CurriculumPlanner:
    """Deterministic, explainable review/new curriculum planner (B4)."""

    def __init__(
        self,
        domain: DomainAdapter,
        graph: KnowledgeGraph,
        policy: PlannerPolicy | None = None,
    ) -> None:
        if not isinstance(domain, DomainAdapter):
            raise ValidationError(
                "CurriculumPlanner(domain=...): expected a DomainAdapter implementation"
            )
        if not isinstance(graph, KnowledgeGraph):
            raise ValidationError("CurriculumPlanner(graph=...): expected a KnowledgeGraph")
        if policy is None:
            policy = PlannerPolicy()
        elif not isinstance(policy, PlannerPolicy):
            raise ValidationError(
                "CurriculumPlanner(policy=...): expected a PlannerPolicy"
            )
        self._domain = domain
        self._graph = graph
        self._policy = policy
        self._topological = graph.topological_order()
        nodes = domain.knowledge_nodes()
        node_map = {node.node_id: node for node in nodes}
        if set(node_map) != set(graph.nodes_by_id()):
            raise ValidationError(
                "CurriculumPlanner: domain knowledge nodes and KnowledgeGraph nodes differ"
            )
        self._nodes = node_map
        graph_edges = {
            (edge.source_node_id, edge.target_node_id, edge.kind) for edge in graph.edges()
        }
        domain_edges = {
            (edge.source_node_id, edge.target_node_id, edge.kind)
            for edge in domain.prerequisite_edges()
        }
        if domain_edges != graph_edges:
            raise ValidationError(
                "CurriculumPlanner: domain prerequisite edges and KnowledgeGraph edges differ"
            )
        items = domain.assessment_items()
        items_by_id = {}
        items_by_node: dict[str, list] = {node_id: [] for node_id in node_map}
        for item in items:
            if item.item_id in items_by_id:
                raise ValidationError(
                    f"CurriculumPlanner: duplicate assessment item id {item.item_id!r}"
                )
            items_by_id[item.item_id] = item
            for node_id in item.node_ids:
                if node_id not in items_by_node:
                    raise ValidationError(
                        f"CurriculumPlanner: item {item.item_id!r} references unknown node "
                        f"{node_id!r}"
                    )
                items_by_node[node_id].append(item)
        self._items_by_id = items_by_id
        self._items_by_node = items_by_node
        practice_items: dict[str, list[str]] = {}
        for node_id in node_map:
            raw = domain.teaching_content(node_id, "PRACTICE")
            try:
                parsed = json.loads(raw)
            except (TypeError, json.JSONDecodeError) as exc:
                raise ValidationError(
                    f"CurriculumPlanner: PRACTICE content for node {node_id!r} is not JSON"
                ) from exc
            if type(parsed) is not list:
                raise ValidationError(
                    f"CurriculumPlanner: PRACTICE content for node {node_id!r} is not a list"
                )
            for item_id in parsed:
                if type(item_id) is not str or not item_id:
                    raise ValidationError(
                        f"CurriculumPlanner: PRACTICE content for node {node_id!r} has a "
                        "non-string item id"
                    )
                item = items_by_id.get(item_id)
                if item is None:
                    raise ValidationError(
                        f"CurriculumPlanner: PRACTICE item {item_id!r} for node {node_id!r} "
                        "does not exist"
                    )
                if node_id not in item.node_ids:
                    raise ValidationError(
                        f"CurriculumPlanner: PRACTICE item {item_id!r} does not cover node "
                        f"{node_id!r}"
                    )
            practice_items[node_id] = list(parsed)
        self._practice_items_by_node = practice_items

    # -- public API --------------------------------------------------------

    def check_goal_completion(
        self, objective: LearningObjective, snapshot: LearnerSnapshot
    ) -> tuple[bool, Reason]:
        """Judge objective completion from observed evidence only (never text)."""

        self._validate_objective(objective)
        if not isinstance(snapshot, LearnerSnapshot):
            raise ValidationError("check_goal_completion(snapshot=...): expected a LearnerSnapshot")
        criteria = objective.success_criteria
        required = list(criteria["required_node_ids"]) or list(objective.target_node_ids)
        min_mastery = float(criteria["min_mastery"])
        max_error_rate = float(criteria["max_error_rate"])
        complete = True
        details: list[str] = []
        for node_id in required:
            mastery = snapshot.masteries.get(node_id)
            if mastery is None:
                complete = False
                details.append(f"{node_id}: no observed evidence (missing mastery estimate)")
                continue
            error_rate = snapshot.error_counts.get(node_id, 0) / max(1, mastery.evidence_count)
            enough_evidence = mastery.evidence_count >= self._policy.min_evidence_count
            node_complete = (
                mastery.value >= min_mastery and enough_evidence and error_rate <= max_error_rate
            )
            complete = complete and node_complete
            details.append(
                f"{node_id}: mastery={mastery.value:.2f} (need >= {min_mastery:.2f}), "
                f"evidence_count={mastery.evidence_count} (need >= "
                f"{self._policy.min_evidence_count}), error_rate={error_rate:.2f} "
                f"(need <= {max_error_rate:.2f})"
            )
        reason = Reason(
            code=REASON_GOAL_COMPLETE if complete else REASON_GOAL_NOT_COMPLETE,
            node_ids=required,
            detail=(
                f"success_criteria required_node_ids={required}, min_mastery={min_mastery:.2f}, "
                f"max_error_rate={max_error_rate:.2f}: " + "; ".join(details)
                + "; completion is judged from observed mastery/error evidence only, never "
                "from learner claims or model text."
            ),
            policy_version=self._policy.policy_version,
            created_at=snapshot.updated_at,
        )
        return complete, reason

    def plan(
        self,
        goal: LearnerGoal,
        objective: LearningObjective,
        snapshot: LearnerSnapshot,
        history: list[HistoryEvent] | None = None,
    ) -> CurriculumPlan:
        """Build a deterministic, explainable curriculum plan."""

        targets, criteria = self._validate_inputs(goal, objective, snapshot)
        history = self._normalise_history(history, snapshot)
        complete, completion_reason = self.check_goal_completion(objective, snapshot)
        required = list(criteria["required_node_ids"]) or list(targets)
        if complete:
            step = self._make_step(
                0,
                _PHASE_COMPLETE,
                _ACTION_GOAL_COMPLETE,
                required,
                None,
                completion_reason,
                snapshot,
            )
            return self._build_plan(goal, objective, snapshot, [step])

        policy = self._policy
        target_set = set(targets)
        min_mastery = float(criteria["min_mastery"])
        hard_strict = self._strict_prerequisites(targets, kinds=("HARD",))
        soft_strict = self._strict_prerequisites(targets, kinds=("SOFT",))
        soft_strict -= hard_strict
        soft_strict -= target_set
        study_nodes = [
            node_id
            for node_id in self._topological
            if node_id in target_set or node_id in hard_strict or node_id in soft_strict
        ]
        consecutive_failures = self._consecutive_failures(history)
        remediation_attempts = self._remediation_attempts(history)
        step_specs: list[tuple[str, str, list[str], str | None, Reason]] = []
        handled: set[str] = set()

        def add(
            phase: str,
            action_kind: str,
            node_ids: list[str],
            item_id: str | None,
            code: str,
            detail: str,
        ) -> None:
            reason = Reason(
                code=code,
                node_ids=list(node_ids),
                detail=detail,
                policy_version=policy.policy_version,
                created_at=snapshot.updated_at,
            )
            step_specs.append((phase, action_kind, list(node_ids), item_id, reason))

        # -- Phase 1: HARD prerequisite remediation (before any target teaching)
        for node_id in study_nodes:
            if node_id not in hard_strict:
                continue
            if self._value(node_id, snapshot) >= policy.prerequisite_mastery_threshold:
                continue
            handled.add(node_id)
            failures = consecutive_failures.get(node_id, 0)
            attempts = remediation_attempts.get(node_id, 0)
            if failures >= policy.reassess_after_failures or attempts >= policy.max_relearn_attempts:
                item_id = self._assessment_item_id(node_id, snapshot)
                add(
                    _PHASE_ASSESS,
                    _ACTION_REASSESS,
                    [node_id],
                    item_id,
                    REASON_REASSESS_STUCK_NODE,
                    (
                        f"HARD prerequisite {node_id} mastery={self._value(node_id, snapshot):.2f} "
                        f"is below {policy.prerequisite_mastery_threshold:.2f}; it already has "
                        f"{failures} consecutive INCORRECT assessment(s) (threshold "
                        f"{policy.reassess_after_failures}) or {attempts} RETEACH attempt(s) "
                        f"(limit {policy.max_relearn_attempts}); reassess before further drilling."
                    ),
                )
                continue
            blocking = self._blocking_targets(node_id, targets)
            add(
                _PHASE_TEACH,
                _ACTION_RETEACH,
                [node_id],
                None,
                REASON_REMEDIATE_HARD_PREREQUISITE,
                (
                    f"HARD prerequisite {node_id} mastery={self._value(node_id, snapshot):.2f} "
                    f"is below {policy.prerequisite_mastery_threshold:.2f}; it blocks objective "
                    f"target(s) {blocking or sorted(target_set)}; reteach it before target teaching."
                ),
            )
            practice_item_id = self._practice_item_id(node_id, snapshot)
            if practice_item_id is not None:
                add(
                    _PHASE_PRACTICE,
                    _ACTION_PRACTICE,
                    [node_id],
                    practice_item_id,
                    REASON_PRACTICE_HARD_PREREQUISITE,
                    (
                        f"practice HARD prerequisite {node_id} with teacher-visible item "
                        f"{practice_item_id} to verify the remedial teaching before moving on."
                    ),
                )

        # -- Phase 1b: optional SOFT prerequisite remediation
        if policy.remediate_soft_prerequisites:
            for node_id in study_nodes:
                if node_id not in soft_strict:
                    continue
                if self._value(node_id, snapshot) >= policy.prerequisite_mastery_threshold:
                    continue
                handled.add(node_id)
                failures = consecutive_failures.get(node_id, 0)
                if failures >= policy.reassess_after_failures:
                    add(
                        _PHASE_ASSESS,
                        _ACTION_REASSESS,
                        [node_id],
                        self._assessment_item_id(node_id, snapshot),
                        REASON_REASSESS_STUCK_NODE,
                        (
                            f"SOFT prerequisite {node_id} has {failures} consecutive INCORRECT "
                            f"assessment(s) (threshold {policy.reassess_after_failures}); "
                            "reassess before deciding whether to skip it."
                        ),
                    )
                    continue
                add(
                    _PHASE_TEACH,
                    _ACTION_RETEACH,
                    [node_id],
                    None,
                    REASON_REMEDIATE_SOFT_PREREQUISITE,
                    (
                        f"SOFT prerequisite {node_id} mastery="
                        f"{self._value(node_id, snapshot):.2f} is below "
                        f"{policy.prerequisite_mastery_threshold:.2f} and the policy opted in to "
                        "soft remediation; reteach it as helpful (not blocking) support."
                    ),
                )
                practice_item_id = self._practice_item_id(node_id, snapshot)
                if practice_item_id is not None:
                    add(
                        _PHASE_PRACTICE,
                        _ACTION_PRACTICE,
                        [node_id],
                        practice_item_id,
                        REASON_PRACTICE_SOFT_PREREQUISITE,
                        (
                            f"practice SOFT prerequisite {node_id} with item "
                            f"{practice_item_id} to strengthen the helpful prerequisite."
                        ),
                    )

        # -- Phase 2: target teaching / practice / assessment (topological order)
        for node_id in study_nodes:
            if node_id not in target_set or node_id in handled:
                continue
            value = self._value(node_id, snapshot)
            if value >= min_mastery:
                continue
            handled.add(node_id)
            failures = consecutive_failures.get(node_id, 0)
            pressure = snapshot.error_counts.get(node_id, 0) + failures
            evidence_count = self._evidence_count(node_id, snapshot)
            practice_item_id = self._practice_item_id(node_id, snapshot)
            assessment_item_id = self._assessment_item_id(node_id, snapshot)
            if failures >= policy.reassess_after_failures:
                add(
                    _PHASE_ASSESS,
                    _ACTION_REASSESS,
                    [node_id],
                    assessment_item_id,
                    REASON_REASSESS_STUCK_NODE,
                    (
                        f"target {node_id} has {failures} consecutive INCORRECT assessment(s) "
                        f"(threshold {policy.reassess_after_failures}); reassess before teaching "
                        "the same content again."
                    ),
                )
            elif pressure >= policy.struggle_error_threshold:
                if practice_item_id is not None:
                    add(
                        _PHASE_PRACTICE,
                        _ACTION_PRACTICE,
                        [node_id],
                        practice_item_id,
                        REASON_PRACTICE_TARGET_NODE,
                        (
                            f"target {node_id} mastery={value:.2f} < objective min_mastery="
                            f"{min_mastery:.2f} and error pressure={pressure} (observed errors + "
                            f"consecutive failures, threshold "
                            f"{policy.struggle_error_threshold}); practise first with item "
                            f"{practice_item_id} rather than re-teaching."
                        ),
                    )
                add(
                    _PHASE_ASSESS,
                    _ACTION_DIAGNOSE,
                    [node_id],
                    assessment_item_id,
                    REASON_ASSESS_PROGRESS,
                    (
                        f"assess target {node_id} with item {assessment_item_id} after practice; "
                        "mastery changes only from observed assessment evidence."
                    ),
                )
            elif evidence_count == 0 or value < min_mastery / 2:
                add(
                    _PHASE_TEACH,
                    _ACTION_EXPLAIN,
                    [node_id],
                    None,
                    REASON_TEACH_TARGET_NODE,
                    (
                        f"target {node_id} mastery={value:.2f} < objective min_mastery="
                        f"{min_mastery:.2f} with evidence_count={evidence_count}; teach the "
                        "concept before asking for practice."
                    ),
                )
                if practice_item_id is not None:
                    add(
                        _PHASE_PRACTICE,
                        _ACTION_PRACTICE,
                        [node_id],
                        practice_item_id,
                        REASON_PRACTICE_TARGET_NODE,
                        (
                            f"practice target {node_id} with teacher-visible item "
                            f"{practice_item_id} right after teaching to apply the concept."
                        ),
                    )
                add(
                    _PHASE_ASSESS,
                    _ACTION_DIAGNOSE,
                    [node_id],
                    assessment_item_id,
                    REASON_ASSESS_PROGRESS,
                    (
                        f"assess target {node_id} with item {assessment_item_id}; observed "
                        "evidence updates mastery and error counts."
                    ),
                )
            else:
                if practice_item_id is not None:
                    add(
                        _PHASE_PRACTICE,
                        _ACTION_PRACTICE,
                        [node_id],
                        practice_item_id,
                        REASON_PRACTICE_TARGET_NODE,
                        (
                            f"target {node_id} mastery={value:.2f} < objective min_mastery="
                            f"{min_mastery:.2f} but has evidence and no elevated error pressure; "
                            f"practise with item {practice_item_id}."
                        ),
                    )
                add(
                    _PHASE_ASSESS,
                    _ACTION_DIAGNOSE,
                    [node_id],
                    assessment_item_id,
                    REASON_ASSESS_PROGRESS,
                    (
                        f"assess target {node_id} with item {assessment_item_id}; observed "
                        "evidence updates mastery and error counts."
                    ),
                )

        # -- Phase 3: spaced review for mastered study nodes not already planned
        planned_nodes = {node_id for spec in step_specs for node_id in spec[2]}
        for node_id in study_nodes:
            if node_id in planned_nodes:
                continue
            mastery = snapshot.masteries.get(node_id)
            if mastery is None or mastery.value < policy.review_mastery_threshold:
                continue
            due, code = self._review_due(node_id, snapshot, history)
            if not due:
                continue
            add(
                _PHASE_REVIEW,
                _ACTION_REVIEW,
                [node_id],
                None,
                code,
                (
                    f"review node {node_id} (mastery={mastery.value:.2f} >= "
                    f"{policy.review_mastery_threshold:.2f}); review is due because "
                    f"{self._review_due_detail(node_id, snapshot, history)}."
                ),
            )
            planned_nodes.add(node_id)

        # -- Phase 4: keep the plan non-empty while the goal is incomplete
        if not step_specs:
            pool = [node_id for node_id in study_nodes if node_id in target_set] or study_nodes
            if not pool:  # pragma: no cover - objectives always reference graph nodes
                pool = list(targets)
            node_id = sorted(
                pool, key=lambda candidate: (round(self._value(candidate, snapshot), 6), candidate)
            )[0]
            practice_item_id = self._practice_item_id(node_id, snapshot)
            if practice_item_id is not None:
                add(
                    _PHASE_PRACTICE,
                    _ACTION_PRACTICE,
                    [node_id],
                    practice_item_id,
                    REASON_FALLBACK_CONTINUE,
                    (
                        f"objective is incomplete but no remediation/teaching/review step is "
                        f"currently justified; continue with node {node_id} (mastery="
                        f"{self._value(node_id, snapshot):.2f}) so the session still has a "
                        "concrete next step."
                    ),
                )
            else:
                add(
                    _PHASE_TEACH,
                    _ACTION_EXPLAIN,
                    [node_id],
                    None,
                    REASON_FALLBACK_CONTINUE,
                    (
                        f"objective is incomplete; continue with node {node_id} (mastery="
                        f"{self._value(node_id, snapshot):.2f}) by teaching the concept."
                    ),
                )

        steps = [
            self._make_step(
                ordinal, phase, action_kind, node_ids, item_id, reason, snapshot
            )
            for ordinal, (phase, action_kind, node_ids, item_id, reason) in enumerate(
                step_specs[: policy.max_steps]
            )
        ]
        return self._build_plan(goal, objective, snapshot, steps)

    # -- input validation --------------------------------------------------

    def _validate_objective(self, objective: LearningObjective) -> None:
        if not isinstance(objective, LearningObjective):
            raise ValidationError("expected a LearningObjective")
        if objective.domain_id != self._domain.domain_id:
            raise ValidationError(
                "objective.domain_id and domain.domain_id differ "
                f"({objective.domain_id!r} != {self._domain.domain_id!r})"
            )
        self._graph.validate_objective(objective)

    def _validate_inputs(
        self,
        goal: LearnerGoal,
        objective: LearningObjective,
        snapshot: LearnerSnapshot,
    ) -> tuple[list[str], dict[str, Any]]:
        if not isinstance(goal, LearnerGoal):
            raise ValidationError("plan(goal=...): expected a LearnerGoal")
        if not isinstance(snapshot, LearnerSnapshot):
            raise ValidationError("plan(snapshot=...): expected a LearnerSnapshot")
        self._validate_objective(objective)
        if goal.learner_id != snapshot.learner_id:
            raise ValidationError(
                "plan(): goal.learner_id and snapshot.learner_id differ "
                f"({goal.learner_id!r} != {snapshot.learner_id!r})"
            )
        if goal.objective_id != objective.objective_id:
            raise ValidationError(
                "plan(): goal.objective_id and objective.objective_id differ "
                f"({goal.objective_id!r} != {objective.objective_id!r})"
            )
        return list(objective.target_node_ids), dict(objective.success_criteria)

    def _normalise_history(
        self, history: list[HistoryEvent] | None, snapshot: LearnerSnapshot
    ) -> list[HistoryEvent]:
        if history is None:
            return []
        if type(history) is not list:
            raise ValidationError("plan(history=...): expected a list or None")
        for index, event in enumerate(history):
            if not isinstance(event, HistoryEvent):
                raise ValidationError(
                    f"plan(history=[{index}]): expected a HistoryEvent"
                )
            if event.learner_id != snapshot.learner_id:
                raise ValidationError(
                    "plan(history=...): history learner_id "
                    f"{event.learner_id!r} does not match snapshot learner_id "
                    f"{snapshot.learner_id!r}"
                )
        return sorted(history, key=lambda event: (event.seq, event.event_id))

    # -- knowledge / evidence helpers -------------------------------------

    def _mastery(self, node_id: str, snapshot: LearnerSnapshot) -> MasteryEstimate | None:
        return snapshot.masteries.get(node_id)

    def _value(self, node_id: str, snapshot: LearnerSnapshot) -> float:
        mastery = self._mastery(node_id, snapshot)
        return mastery.value if mastery is not None else 0.0

    def _evidence_count(self, node_id: str, snapshot: LearnerSnapshot) -> int:
        mastery = self._mastery(node_id, snapshot)
        return mastery.evidence_count if mastery is not None else 0

    def _strict_prerequisites(
        self, targets: Sequence[str], *, kinds: tuple[str, ...]
    ) -> set[str]:
        closure: set[str] = set()
        for target in targets:
            closure |= self._graph.prerequisite_closure([target], kinds=kinds)
        return closure

    def _blocking_targets(self, node_id: str, targets: Sequence[str]) -> list[str]:
        blocking: list[str] = []
        for target in targets:
            if node_id in self._graph.prerequisite_closure([target], kinds=("HARD",)):
                blocking.append(target)
        return blocking

    def _event_node_ids(self, event: HistoryEvent) -> set[str]:
        node_ids: set[str] = set()
        payload = event.payload
        raw_nodes = payload.get("node_ids")
        if type(raw_nodes) is list:
            node_ids.update(value for value in raw_nodes if type(value) is str)
        raw_node = payload.get("node_id")
        if type(raw_node) is str:
            node_ids.add(raw_node)
        raw_item = payload.get("item_id")
        if type(raw_item) is str:
            item = self._items_by_id.get(raw_item)
            if item is not None:
                node_ids.update(item.node_ids)
        return node_ids

    def _consecutive_failures(self, history: Sequence[HistoryEvent]) -> dict[str, int]:
        streaks: dict[str, int] = {}
        for event in history:
            if event.event_type != "ASSESSED":
                continue
            status = event.payload.get("status")
            for node_id in self._event_node_ids(event):
                if status == "INCORRECT":
                    streaks[node_id] = streaks.get(node_id, 0) + 1
                elif status in ("CORRECT", "PARTIAL"):
                    streaks[node_id] = 0
        return streaks

    def _remediation_attempts(self, history: Sequence[HistoryEvent]) -> dict[str, int]:
        attempts: dict[str, int] = {}
        for event in history:
            if event.event_type != "ACTION_TAKEN":
                continue
            if event.payload.get("action_kind") != _ACTION_RETEACH:
                continue
            for node_id in self._event_node_ids(event):
                attempts[node_id] = attempts.get(node_id, 0) + 1
        return attempts

    def _last_evidence_turn(
        self, node_id: str, history: Sequence[HistoryEvent]
    ) -> int | None:
        last: int | None = None
        for index, event in enumerate(history):
            if event.event_type not in _EVIDENCE_HISTORY_TYPES:
                continue
            if node_id in self._event_node_ids(event):
                last = index
        return last

    def _turns_since_evidence(self, node_id: str, history: Sequence[HistoryEvent]) -> int | None:
        last = self._last_evidence_turn(node_id, history)
        if last is None:
            return None
        return len(history) - 1 - last

    def _hours_since(self, older: str, newer: str) -> float:
        older_dt = _parse_timestamp(older, "mastery.updated_at")
        newer_dt = _parse_timestamp(newer, "snapshot.updated_at")
        delta = (newer_dt - older_dt).total_seconds() / 3600.0
        return max(0.0, delta)

    def _review_due(
        self, node_id: str, snapshot: LearnerSnapshot, history: Sequence[HistoryEvent]
    ) -> tuple[bool, str]:
        if snapshot.error_counts.get(node_id, 0) >= self._policy.review_error_threshold:
            return True, REASON_REVIEW_REPEATED_ERRORS
        turns = self._turns_since_evidence(node_id, history)
        if turns is not None and turns >= self._policy.review_interval_turns:
            return True, REASON_REVIEW_DUE
        mastery = snapshot.masteries.get(node_id)
        if mastery is not None and self._hours_since(
            mastery.updated_at, snapshot.updated_at
        ) >= self._policy.review_interval_hours:
            return True, REASON_REVIEW_DUE
        return False, ""

    def _review_due_detail(
        self, node_id: str, snapshot: LearnerSnapshot, history: Sequence[HistoryEvent]
    ) -> str:
        errors = snapshot.error_counts.get(node_id, 0)
        if errors >= self._policy.review_error_threshold:
            return (
                f"repeated errors on the node ({errors} >= "
                f"{self._policy.review_error_threshold} error observations)"
            )
        turns = self._turns_since_evidence(node_id, history)
        mastery = snapshot.masteries.get(node_id)
        hours = (
            self._hours_since(mastery.updated_at, snapshot.updated_at)
            if mastery is not None
            else 0.0
        )
        return (
            f"review interval elapsed (turns_since_evidence={turns}, "
            f"hours_since_evidence={hours:.1f}; thresholds "
            f"{self._policy.review_interval_turns} turns / "
            f"{self._policy.review_interval_hours:.0f} hours)"
        )

    # -- item helpers ------------------------------------------------------

    def _practice_item_id(self, node_id: str, snapshot: LearnerSnapshot) -> str | None:
        candidates = self._practice_items_by_node.get(node_id, [])
        if not candidates:
            return None
        completed = set(snapshot.completed_item_ids)
        for item_id in candidates:
            if item_id not in completed:
                return item_id
        return candidates[0]

    def _assessment_item_id(self, node_id: str, snapshot: LearnerSnapshot) -> str | None:
        candidates = self._items_by_node.get(node_id, [])
        if not candidates:
            return None
        completed = set(snapshot.completed_item_ids)
        priority = self._policy.assessment_item_type_priority

        def sort_key(item: Any) -> tuple[int, int, int, str]:
            type_rank = (
                priority.index(item.item_type) if item.item_type in priority else len(priority)
            )
            return (
                0 if item.item_id not in completed else 1,
                0 if item.deterministic else 1,
                type_rank,
                item.item_id,
            )

        return min(candidates, key=sort_key).item_id

    # -- record builders ---------------------------------------------------

    def _make_step(
        self,
        ordinal: int,
        phase: str,
        action_kind: str,
        node_ids: Sequence[str],
        item_id: str | None,
        reason: Reason,
        snapshot: LearnerSnapshot,
    ) -> PlanStep:
        return PlanStep(
            step_id=(
                f"step:{ordinal:02d}:{action_kind}:{','.join(node_ids) if node_ids else 'none'}"
            ),
            ordinal=ordinal,
            phase=phase,
            node_ids=list(node_ids),
            action_kind=action_kind,
            rationale=reason,
            item_id=item_id,
            created_at=snapshot.updated_at,
        )

    def _build_plan(
        self,
        goal: LearnerGoal,
        objective: LearningObjective,
        snapshot: LearnerSnapshot,
        steps: list[PlanStep],
    ) -> CurriculumPlan:
        signature = [
            (
                step.ordinal,
                step.phase,
                step.action_kind,
                tuple(step.node_ids),
                step.item_id,
                step.rationale.code,
            )
            for step in steps
        ]
        plan_id = "plan:" + _fingerprint(
            self._domain.domain_id,
            goal.goal_id,
            objective.objective_id,
            snapshot.learner_id,
            snapshot.revision,
            snapshot.updated_at,
            self._policy.policy_version,
            signature,
        )
        return CurriculumPlan(
            plan_id=plan_id,
            learner_id=snapshot.learner_id,
            goal_id=goal.goal_id,
            objective_id=objective.objective_id,
            steps=steps,
            policy_version=self._policy.policy_version,
            created_at=snapshot.updated_at,
        )
