"""Diagnostic engine (B3) of the M1-A offline teacher core (``m1a.v0``).

The engine selects the **next diagnostic assessment item** from teacher-visible
data only:

* :class:`~m1_teacher.contracts.types.LearnerSnapshot` (observed mastery/error
  evidence; inferred or fabricated values are never created here),
* :class:`~m1_teacher.contracts.types.AssessmentItem` metadata (id, node ids,
  type, difficulty, deterministic flag; *never* scoring material),
* the validated :class:`~m1_teacher.knowledge.graph.KnowledgeGraph`,
* the declarative :class:`~m1_teacher.contracts.types.LearningObjective`.

Design rules (frozen B-PR3 policy):

1. **No hidden material.**  The engine never opens fixture files, never
   enumerates the domain directory and has no access path to hidden evaluation
   content; it only consumes the :class:`~m1_teacher.contracts.domain.
   DomainAdapter` read API.
2. **Never invent mastery.**  A node that was never observed is treated as
   "no evidence" for ranking purposes; the engine never writes it back as a
   mastery value and never returns a mastery guess.  Insufficient evidence is
   reported as ``INSUFFICIENT_EVIDENCE`` with a structured reason.
3. **Deterministic and explainable.**  Node scoring is a documented, stable
   ordering (evidence gap -> low mastery -> hard-prerequisite priority ->
   difficulty match -> ``node_id``); item scoring prefers discriminating items
   (policy tag heuristic), uncompleted/unseen items, deterministic items, the
   configured item-type priority and the difficulty closest to the node.
   ``created_at`` is copied from ``snapshot.updated_at`` instead of the wall
   clock, so the same inputs produce a byte-identical ``to_dict()`` replay.
4. **Structured reasoning.**  Every result carries a :class:`Reason` whose
   ``code``/``node_ids``/``detail``/``policy_version`` explain *why this node
   and this item*, and what hypothesis the item is meant to distinguish.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Sequence

from ..contracts.domain import DomainAdapter
from ..contracts.errors import ValidationError
from ..contracts.types import (
    ITEM_TYPE_VALUES,
    AssessmentItem,
    DiagnosisResult,
    HistoryEvent,
    LearnerGoal,
    LearnerSnapshot,
    LearningObjective,
    MasteryEstimate,
    Reason,
)
from ..knowledge.graph import KnowledgeGraph

__all__ = ["DiagnosticEngine", "DiagnosticPolicy", "POLICY_VERSION"]

POLICY_VERSION = "m1a.diagnostic.v0"

READY = "READY"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"

REASON_TARGET_EVIDENCE_GAP = "TARGET_EVIDENCE_GAP"
REASON_HARD_PREREQUISITE_GAP = "HARD_PREREQUISITE_GAP"
REASON_PREREQUISITE_EVIDENCE_GAP = "PREREQUISITE_EVIDENCE_GAP"
REASON_INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"

_DEFAULT_ITEM_TYPE_PRIORITY: tuple[str, ...] = ("MCQ", "CODE", "SHORT_ANSWER")
_DEFAULT_DISCRIMINATING_TAGS: tuple[str, ...] = (
    "boundary",
    "off-by-one",
    "monotonicity",
    "edge-cases",
)
_TARGET_EVIDENCE_HISTORY_TYPES = frozenset({"ASSESSED", "MASTERY_UPDATED"})


# ---------------------------------------------------------------------------
# Small deterministic helpers
# ---------------------------------------------------------------------------


def _fingerprint(*parts: Any) -> str:
    payload = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


def _require_int(where: str, value: Any, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValidationError(f"{where}: expected an int >= {minimum}, got {value!r}")
    return value


def _require_unit(where: str, value: Any) -> float:
    if type(value) not in (int, float) or not 0.0 <= float(value) <= 1.0:
        raise ValidationError(f"{where}: expected a number in [0, 1], got {value!r}")
    return float(value)


@dataclass(frozen=True)
class DiagnosticPolicy:
    """Deterministic, injectable diagnostic policy.

    The defaults implement the frozen B-PR3 heuristic; every threshold is an
    explicit constant so policy changes are reviewable and testable.
    """

    policy_version: str = POLICY_VERSION
    #: A node needs at least this many *observed* evidence events before its
    #: mastery estimate is considered sufficient for diagnosis.
    min_evidence_count: int = 2
    #: Mastery confidence below this value is treated as insufficient evidence.
    min_confidence: float = 0.5
    #: Mastery at or above this value is "no diagnostic gap" for ranking.
    mastery_gap_threshold: float = 0.5
    #: Error counts at or above this value also mark a node as a diagnostic gap.
    error_count_gap_threshold: int = 2
    #: Prefer nodes that are strict HARD prerequisites of an objective target.
    prefer_hard_prerequisite_evidence: bool = True
    #: Include SOFT prerequisite closure in the candidate node set.
    include_soft_prerequisites: bool = True
    #: Node tags that mark an item as hypothesis-discriminating (policy level).
    discriminating_tags: tuple[str, ...] = _DEFAULT_DISCRIMINATING_TAGS
    #: Preferred assessment item types (earlier = preferred).
    item_type_priority: tuple[str, ...] = _DEFAULT_ITEM_TYPE_PRIORITY
    prefer_deterministic_items: bool = True
    prefer_uncompleted_items: bool = True
    #: How many recent history events are checked for already-seen items.
    recent_item_lookback: int = 10
    #: Maximum number of history event references attached to a result.
    max_evidence_refs: int = 5

    def __post_init__(self) -> None:
        _require_str(self.policy_version, "DiagnosticPolicy.policy_version")
        _require_int("DiagnosticPolicy.min_evidence_count", self.min_evidence_count)
        _require_unit("DiagnosticPolicy.min_confidence", self.min_confidence)
        _require_unit("DiagnosticPolicy.mastery_gap_threshold", self.mastery_gap_threshold)
        _require_int("DiagnosticPolicy.error_count_gap_threshold",
                     self.error_count_gap_threshold)
        if type(self.prefer_hard_prerequisite_evidence) is not bool:
            raise ValidationError("DiagnosticPolicy.prefer_hard_prerequisite_evidence: bool")
        if type(self.include_soft_prerequisites) is not bool:
            raise ValidationError("DiagnosticPolicy.include_soft_prerequisites: bool")
        _require_str_tuple("DiagnosticPolicy.discriminating_tags", self.discriminating_tags)
        _require_str_tuple("DiagnosticPolicy.item_type_priority", self.item_type_priority)
        unknown_types = [value for value in self.item_type_priority if value not in ITEM_TYPE_VALUES]
        if unknown_types:
            raise ValidationError(
                "DiagnosticPolicy.item_type_priority: unknown item type(s): "
                f"{unknown_types}"
            )
        if len(set(self.item_type_priority)) != len(self.item_type_priority):
            raise ValidationError("DiagnosticPolicy.item_type_priority: duplicates")
        if type(self.prefer_deterministic_items) is not bool:
            raise ValidationError("DiagnosticPolicy.prefer_deterministic_items: bool")
        if type(self.prefer_uncompleted_items) is not bool:
            raise ValidationError("DiagnosticPolicy.prefer_uncompleted_items: bool")
        _require_int("DiagnosticPolicy.recent_item_lookback", self.recent_item_lookback)
        _require_int("DiagnosticPolicy.max_evidence_refs", self.max_evidence_refs, minimum=1)


def _require_str(value: Any, where: str) -> str:
    if type(value) is not str or not value.strip():
        raise ValidationError(f"{where}: expected a non-blank string, got {value!r}")
    return value


def _require_str_tuple(where: str, value: Any) -> tuple[str, ...]:
    if type(value) is not tuple or not value:
        raise ValidationError(f"{where}: expected a non-empty tuple of strings")
    for index, element in enumerate(value):
        if type(element) is not str or not element.strip():
            raise ValidationError(f"{where}[{index}]: expected a non-blank string")
    return value


# ---------------------------------------------------------------------------
# Diagnostic engine
# ---------------------------------------------------------------------------


class DiagnosticEngine:
    """Select the next diagnostic assessment item from teacher-visible data."""

    def __init__(
        self,
        domain: DomainAdapter,
        graph: KnowledgeGraph,
        policy: DiagnosticPolicy | None = None,
    ) -> None:
        if not isinstance(domain, DomainAdapter):
            raise ValidationError(
                "DiagnosticEngine(domain=...): expected a DomainAdapter implementation"
            )
        if not isinstance(graph, KnowledgeGraph):
            raise ValidationError("DiagnosticEngine(graph=...): expected a KnowledgeGraph")
        if policy is None:
            policy = DiagnosticPolicy()
        elif not isinstance(policy, DiagnosticPolicy):
            raise ValidationError(
                "DiagnosticEngine(policy=...): expected a DiagnosticPolicy"
            )
        self._domain = domain
        self._graph = graph
        self._policy = policy
        self._topological: list[str] = graph.topological_order()
        nodes = domain.knowledge_nodes()
        node_map = {node.node_id: node for node in nodes}
        if set(node_map) != set(graph.nodes_by_id()):
            raise ValidationError(
                "DiagnosticEngine: domain knowledge nodes and KnowledgeGraph nodes differ"
            )
        self._nodes = node_map
        domain_edges = {
            (edge.source_node_id, edge.target_node_id, edge.kind)
            for edge in domain.prerequisite_edges()
        }
        graph_edges = {
            (edge.source_node_id, edge.target_node_id, edge.kind) for edge in graph.edges()
        }
        if domain_edges != graph_edges:
            raise ValidationError(
                "DiagnosticEngine: domain prerequisite edges and KnowledgeGraph edges differ"
            )
        items = domain.assessment_items()
        items_by_id: dict[str, AssessmentItem] = {}
        for item in items:
            if item.item_id in items_by_id:
                raise ValidationError(
                    f"DiagnosticEngine: duplicate assessment item id {item.item_id!r}"
                )
            items_by_id[item.item_id] = item
        self._items_by_id = items_by_id
        items_by_node: dict[str, list[AssessmentItem]] = {node_id: [] for node_id in node_map}
        for item in items:
            for node_id in item.node_ids:
                if node_id not in items_by_node:
                    raise ValidationError(
                        f"DiagnosticEngine: item {item.item_id!r} references unknown node "
                        f"{node_id!r}"
                    )
                items_by_node[node_id].append(item)
        self._items_by_node = items_by_node

    # -- public API --------------------------------------------------------

    def select_next_item(
        self,
        goal: LearnerGoal,
        objective: LearningObjective,
        snapshot: LearnerSnapshot,
        history: list[HistoryEvent] | None = None,
        exclude_item_ids: set[str] | None = None,
    ) -> DiagnosisResult:
        """Return the next diagnostic item (or a structured no-evidence result)."""

        targets, criteria = self._validate_inputs(goal, objective, snapshot)
        history = self._normalise_history(history, snapshot)
        excluded = self._normalise_exclude(exclude_item_ids)
        target_set = set(targets)
        required = list(criteria["required_node_ids"]) or list(targets)

        unknown_mastery = sorted(set(snapshot.masteries) - set(self._nodes))
        if unknown_mastery:
            return self._insufficient(
                goal,
                objective,
                snapshot,
                node_ids=list(targets),
                detail=(
                    "snapshot/objective mismatch: LearnerSnapshot contains mastery for node(s) "
                    f"unknown to the domain knowledge graph: {unknown_mastery}; refusing to treat "
                    "them as diagnostic evidence."
                ),
            )

        if self._policy.include_soft_prerequisites:
            closure = self._graph.prerequisite_closure(targets, kinds=("HARD", "SOFT"))
        else:
            closure = self._graph.prerequisite_closure(targets, kinds=("HARD",))
        hard_blocking: set[str] = set()
        for target in targets:
            hard_blocking |= self._graph.prerequisite_closure([target], kinds=("HARD",))
        candidate_nodes = [
            node_id for node_id in self._topological if node_id in target_set or node_id in closure
        ]
        if not candidate_nodes:  # pragma: no cover - graphs always contain their targets
            return self._insufficient(
                goal,
                objective,
                snapshot,
                node_ids=list(targets),
                detail="no candidate nodes could be derived from the objective and graph.",
            )

        needs_evidence = [
            node_id
            for node_id in candidate_nodes
            if self._needs_evidence(node_id, snapshot)
        ]
        if self._goal_is_met(objective, snapshot) and not needs_evidence:
            return self._insufficient(
                goal,
                objective,
                snapshot,
                node_ids=list(required),
                detail=(
                    "success criteria already satisfied and all candidate nodes have sufficient "
                    "observed evidence; no diagnostic gap remains, so no further item is needed."
                ),
            )
        if not needs_evidence:
            return self._insufficient(
                goal,
                objective,
                snapshot,
                node_ids=list(required),
                detail=(
                    "candidate nodes already have sufficient observed evidence but the objective "
                    "is not met; the remaining mastery/error gap requires teaching or planning, "
                    "not another diagnostic item."
                ),
            )

        ability_level = self._ability_level(snapshot)
        ordered = sorted(
            needs_evidence,
            key=lambda node_id: self._node_sort_key(
                node_id, target_set, hard_blocking, ability_level, snapshot
            ),
        )
        excluded_unavailable = False
        for node_id in ordered:
            usable = [
                item
                for item in self._items_by_node.get(node_id, ())
                if item.item_id not in excluded
            ]
            if not usable:
                if self._items_by_node.get(node_id):
                    excluded_unavailable = True
                continue
            item = min(
                usable,
                key=lambda candidate: self._item_sort_key(
                    candidate, node_id, snapshot, history
                ),
            )
            return self._ready(
                goal,
                objective,
                snapshot,
                history,
                node_id=node_id,
                item=item,
                target_set=target_set,
                hard_blocking=hard_blocking,
            )

        if excluded_unavailable:
            detail = (
                "no diagnostic item is selectable: every teacher-visible item for the "
                f"evidence-insufficient node(s) {ordered} is excluded via exclude_item_ids="
                f"{sorted(excluded)}."
            )
        else:
            detail = (
                "no teacher-visible assessment item exists for the evidence-insufficient "
                f"candidate node(s) {ordered}."
            )
        return self._insufficient(
            goal, objective, snapshot, node_ids=list(ordered), detail=detail
        )

    # -- input validation --------------------------------------------------

    def _validate_inputs(
        self,
        goal: LearnerGoal,
        objective: LearningObjective,
        snapshot: LearnerSnapshot,
    ) -> tuple[list[str], dict[str, Any]]:
        if not isinstance(goal, LearnerGoal):
            raise ValidationError("select_next_item(goal=...): expected a LearnerGoal")
        if not isinstance(objective, LearningObjective):
            raise ValidationError(
                "select_next_item(objective=...): expected a LearningObjective"
            )
        if not isinstance(snapshot, LearnerSnapshot):
            raise ValidationError(
                "select_next_item(snapshot=...): expected a LearnerSnapshot"
            )
        if goal.learner_id != snapshot.learner_id:
            raise ValidationError(
                "select_next_item(): goal.learner_id and snapshot.learner_id differ "
                f"({goal.learner_id!r} != {snapshot.learner_id!r})"
            )
        if goal.objective_id != objective.objective_id:
            raise ValidationError(
                "select_next_item(): goal.objective_id and objective.objective_id differ "
                f"({goal.objective_id!r} != {objective.objective_id!r})"
            )
        if objective.domain_id != self._domain.domain_id:
            raise ValidationError(
                "select_next_item(): objective.domain_id and domain.domain_id differ "
                f"({objective.domain_id!r} != {self._domain.domain_id!r})"
            )
        self._graph.validate_objective(objective)
        targets = list(objective.target_node_ids)
        criteria = objective.success_criteria
        if type(criteria.get("required_node_ids")) is not list:
            raise ValidationError("LearningObjective.success_criteria.required_node_ids: list")
        return targets, dict(criteria)

    def _normalise_history(
        self, history: list[HistoryEvent] | None, snapshot: LearnerSnapshot
    ) -> list[HistoryEvent]:
        if history is None:
            return []
        if type(history) is not list:
            raise ValidationError("select_next_item(history=...): expected a list or None")
        for index, event in enumerate(history):
            if not isinstance(event, HistoryEvent):
                raise ValidationError(
                    f"select_next_item(history=[{index}]): expected a HistoryEvent"
                )
            if event.learner_id != snapshot.learner_id:
                raise ValidationError(
                    "select_next_item(history=...): history learner_id "
                    f"{event.learner_id!r} does not match snapshot learner_id "
                    f"{snapshot.learner_id!r}"
                )
        return sorted(history, key=lambda event: (event.seq, event.event_id))

    def _normalise_exclude(self, exclude_item_ids: set[str] | None) -> set[str]:
        if exclude_item_ids is None:
            return set()
        if not isinstance(exclude_item_ids, (set, frozenset, list, tuple)):
            raise ValidationError(
                "select_next_item(exclude_item_ids=...): expected a set of item ids or None"
            )
        excluded: set[str] = set()
        for value in exclude_item_ids:
            if type(value) is not str or not value.strip():
                raise ValidationError(
                    "select_next_item(exclude_item_ids=...): entries must be non-blank strings"
                )
            excluded.add(value)
        return excluded

    # -- evidence / mastery helpers ---------------------------------------

    def _mastery(self, node_id: str, snapshot: LearnerSnapshot) -> MasteryEstimate | None:
        return snapshot.masteries.get(node_id)

    def _needs_evidence(self, node_id: str, snapshot: LearnerSnapshot) -> bool:
        """True when the node still has a diagnostic evidence gap.

        A node needs probing when it was never observed, when its observed
        evidence is too thin/low-confidence, or when repeated errors (at or
        above ``error_count_gap_threshold``) show that the current estimate is
        not trustworthy enough to plan on.
        """

        mastery = self._mastery(node_id, snapshot)
        if mastery is None:
            return True
        if mastery.evidence_count < self._policy.min_evidence_count:
            return True
        if mastery.confidence < self._policy.min_confidence:
            return True
        return (
            snapshot.error_counts.get(node_id, 0)
            >= self._policy.error_count_gap_threshold
        )

    def _ability_level(self, snapshot: LearnerSnapshot) -> int:
        values = [mastery.value for mastery in snapshot.masteries.values()]
        if not values:
            return 1
        average = sum(values) / len(values)
        return _clamp(int(round(1 + average * 4)), 1, 5)

    def _node_sort_key(
        self,
        node_id: str,
        target_set: set[str],
        hard_blocking: set[str],
        ability_level: int,
        snapshot: LearnerSnapshot,
    ) -> tuple[float, int, int, str]:
        mastery = self._mastery(node_id, snapshot)
        value = mastery.value if mastery is not None else 0.0
        if self._policy.prefer_hard_prerequisite_evidence and node_id in hard_blocking:
            hard_rank = 0
        elif node_id in target_set:
            hard_rank = 1
        else:
            hard_rank = 2
        difficulty_gap = abs(self._nodes[node_id].difficulty - ability_level)
        return (round(value, 6), hard_rank, difficulty_gap, node_id)

    def _item_sort_key(
        self,
        item: AssessmentItem,
        node_id: str,
        snapshot: LearnerSnapshot,
        history: Sequence[HistoryEvent],
    ) -> tuple[int, int, int, int, int, int, str]:
        completed = set(snapshot.completed_item_ids)
        seen = self._recent_item_ids(history)
        type_priority = self._policy.item_type_priority
        type_rank = (
            type_priority.index(item.item_type)
            if item.item_type in type_priority
            else len(type_priority)
        )
        return (
            0 if item.item_id not in completed else 1,
            0 if item.item_id not in seen else 1,
            0 if item.deterministic or not self._policy.prefer_deterministic_items else 1,
            -self._discrimination(item),
            type_rank,
            abs(item.difficulty - self._nodes[node_id].difficulty),
            item.item_id,
        )

    def _discrimination(self, item: AssessmentItem) -> int:
        tags = self._policy.discriminating_tags
        score = 0
        for node_id in item.node_ids:
            node = self._nodes.get(node_id)
            if node is None:
                continue
            score += sum(1 for tag in node.tags if tag in tags)
        return score

    def _recent_item_ids(self, history: Sequence[HistoryEvent]) -> set[str]:
        seen: set[str] = set()
        window = self._policy.recent_item_lookback
        for event in history[-window:] if window else ():
            item_id = event.payload.get("item_id")
            if type(item_id) is str and item_id:
                seen.add(item_id)
        return seen

    def _goal_is_met(
        self, objective: LearningObjective, snapshot: LearnerSnapshot
    ) -> bool:
        criteria = objective.success_criteria
        required = list(criteria["required_node_ids"]) or list(objective.target_node_ids)
        min_mastery = float(criteria["min_mastery"])
        max_error_rate = float(criteria["max_error_rate"])
        for node_id in required:
            mastery = snapshot.masteries.get(node_id)
            if mastery is None or mastery.evidence_count <= 0:
                return False
            if mastery.value < min_mastery:
                return False
            error_rate = snapshot.error_counts.get(node_id, 0) / max(1, mastery.evidence_count)
            if error_rate > max_error_rate:
                return False
        return True

    # -- result builders ---------------------------------------------------

    def _diagnosis_id(
        self,
        goal: LearnerGoal,
        objective: LearningObjective,
        snapshot: LearnerSnapshot,
        selected_item_id: str | None,
        history: Sequence[HistoryEvent],
    ) -> str:
        history_ids = [event.event_id for event in history]
        return "diag:" + _fingerprint(
            self._domain.domain_id,
            goal.goal_id,
            objective.objective_id,
            snapshot.learner_id,
            snapshot.revision,
            snapshot.updated_at,
            selected_item_id,
            self._policy.policy_version,
            history_ids,
        )

    def _evidence_refs(
        self,
        snapshot: LearnerSnapshot,
        node_id: str,
        item: AssessmentItem | None,
        history: Sequence[HistoryEvent],
    ) -> list[str]:
        refs = [
            f"snapshot:{snapshot.learner_id}:revision={snapshot.revision}:"
            f"updated_at={snapshot.updated_at}"
        ]
        mastery = snapshot.masteries.get(node_id)
        if mastery is not None:
            refs.append(
                f"mastery:{node_id}:value={mastery.value:.2f}:"
                f"evidence={mastery.evidence_count}"
            )
        relevant: list[HistoryEvent] = []
        for event in reversed(history):
            if node_id in self._event_node_ids(event):
                relevant.append(event)
                if len(relevant) >= self._policy.max_evidence_refs:
                    break
        for event in relevant:
            refs.append(f"history:{event.event_id}")
        return refs

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

    def _ready(
        self,
        goal: LearnerGoal,
        objective: LearningObjective,
        snapshot: LearnerSnapshot,
        history: Sequence[HistoryEvent],
        *,
        node_id: str,
        item: AssessmentItem,
        target_set: set[str],
        hard_blocking: set[str],
    ) -> DiagnosisResult:
        mastery = self._mastery(node_id, snapshot)
        value = mastery.value if mastery is not None else 0.0
        evidence_count = mastery.evidence_count if mastery is not None else 0
        confidence = mastery.confidence if mastery is not None else 0.0
        if node_id in target_set:
            code = REASON_TARGET_EVIDENCE_GAP
            reason_nodes = [node_id]
        elif node_id in hard_blocking:
            code = REASON_HARD_PREREQUISITE_GAP
            blocking = [
                target
                for target in objective.target_node_ids
                if node_id in self._graph.prerequisite_closure([target], kinds=("HARD",))
            ]
            reason_nodes = [node_id, *sorted(blocking)]
        else:
            code = REASON_PREREQUISITE_EVIDENCE_GAP
            reason_nodes = [node_id]
        detail = (
            f"selected node {node_id}: observed evidence is insufficient "
            f"(evidence_count={evidence_count} < {self._policy.min_evidence_count} or "
            f"confidence={confidence:.2f} < {self._policy.min_confidence}); current mastery "
            f"estimate={value:.2f} is below the diagnostic gap threshold "
            f"{self._policy.mastery_gap_threshold:.2f}. Item {item.item_id} "
            f"(type={item.item_type}, difficulty={item.difficulty}) covers node(s) "
            f"{item.node_ids} and discriminates tags "
            f"{sorted(set(self._nodes[node_id].tags) & set(self._policy.discriminating_tags))}; "
            f"candidate nodes were ranked by evidence gap, low mastery, hard-prerequisite "
            f"priority and difficulty match; policy={self._policy.policy_version}."
        )
        hypothesis = (
            f"{code}: {node_id} is below mastery threshold "
            f"{self._policy.mastery_gap_threshold:.2f} or insufficiently observed; a response "
            f"to item {item.item_id} would distinguish 'not yet learned' from "
            "'learned but not yet evidenced'."
        )
        return DiagnosisResult(
            diagnosis_id=self._diagnosis_id(
                goal, objective, snapshot, item.item_id, history
            ),
            learner_id=snapshot.learner_id,
            status=READY,
            target_node_id=node_id,
            selected_item_id=item.item_id,
            hypothesis=hypothesis,
            reason=Reason(
                code=code,
                node_ids=reason_nodes,
                detail=detail,
                policy_version=self._policy.policy_version,
                created_at=snapshot.updated_at,
            ),
            evidence_refs=self._evidence_refs(snapshot, node_id, item, history),
            created_at=snapshot.updated_at,
        )

    def _insufficient(
        self,
        goal: LearnerGoal,
        objective: LearningObjective,
        snapshot: LearnerSnapshot,
        *,
        node_ids: list[str],
        detail: str,
    ) -> DiagnosisResult:
        reason_nodes = list(node_ids) or list(self._topological) or ["m1a.unknown.node"]
        primary = reason_nodes[0]
        return DiagnosisResult(
            diagnosis_id=self._diagnosis_id(goal, objective, snapshot, None, ()),
            learner_id=snapshot.learner_id,
            status=INSUFFICIENT_EVIDENCE,
            target_node_id=primary,
            selected_item_id=None,
            hypothesis=(
                "insufficient_evidence: no diagnostic item can be selected without guessing "
                "mastery; the reason detail states what is missing."
            ),
            reason=Reason(
                code=REASON_INSUFFICIENT_EVIDENCE,
                node_ids=reason_nodes,
                detail=detail,
                policy_version=self._policy.policy_version,
                created_at=snapshot.updated_at,
            ),
            evidence_refs=[
                f"snapshot:{snapshot.learner_id}:revision={snapshot.revision}:"
                f"updated_at={snapshot.updated_at}"
            ],
            created_at=snapshot.updated_at,
        )
