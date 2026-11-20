"""Validated, deterministic knowledge graph for the M1-A teacher (``m1a.v0``).

Semantics frozen in B-PR1:

* Nodes are :class:`~m1_teacher.contracts.types.KnowledgeNode` records with
  unique ``node_id`` values.
* Edges are :class:`~m1_teacher.contracts.types.PrerequisiteEdge` records:
  ``source_node_id`` **is a prerequisite of** ``target_node_id``.  ``HARD``
  edges are mandatory prerequisites (remediation is required before the target
  is taught); ``SOFT`` edges are helpful but not blocking.
* The graph must be acyclic (a DAG).  Self-loops, dangling endpoints,
  duplicate node ids, unknown edge kinds and duplicate edges are rejected at
  construction time with :class:`ValidationError` (fail-closed).
* ``topological_order()`` returns a deterministic order where every
  prerequisite appears before its dependants; node insertion order breaks
  ties.
* ``prerequisite_closure(node_ids, kinds=("HARD", "SOFT"))`` returns all
  transitive prerequisites of the seeds.  Seed nodes themselves are never in
  the result (even when one seed is a prerequisite of another seed).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from ..contracts.errors import ValidationError
from ..contracts.types import (
    EDGE_KIND_VALUES,
    KnowledgeNode,
    LearningObjective,
    PrerequisiteEdge,
)

__all__ = ["KnowledgeGraph"]

_DEFAULT_CLOSURE_KINDS: tuple[str, ...] = ("HARD", "SOFT")


class KnowledgeGraph:
    """A validated prerequisite DAG over teacher-visible knowledge nodes."""

    def __init__(
        self,
        nodes: list[KnowledgeNode],
        edges: list[PrerequisiteEdge],
    ) -> None:
        if type(nodes) is not list:
            raise ValidationError("KnowledgeGraph(nodes=...) expects a list")
        if type(edges) is not list:
            raise ValidationError("KnowledgeGraph(edges=...) expects a list")

        node_map: dict[str, KnowledgeNode] = {}
        for index, node in enumerate(nodes):
            if not isinstance(node, KnowledgeNode):
                raise ValidationError(
                    f"KnowledgeGraph.nodes[{index}]: expected a KnowledgeNode instance"
                )
            if node.node_id in node_map:
                raise ValidationError(
                    f"KnowledgeGraph: duplicate node_id {node.node_id!r}"
                )
            node_map[node.node_id] = node
        self._nodes: dict[str, KnowledgeNode] = node_map

        self._edges: list[PrerequisiteEdge] = []
        seen_edges: set[tuple[str, str, str]] = set()
        for index, edge in enumerate(edges):
            if not isinstance(edge, PrerequisiteEdge):
                raise ValidationError(
                    f"KnowledgeGraph.edges[{index}]: expected a PrerequisiteEdge instance"
                )
            if edge.kind not in EDGE_KIND_VALUES:
                raise ValidationError(
                    f"KnowledgeGraph.edges[{index}]: unknown edge kind {edge.kind!r}"
                )
            if edge.source_node_id not in node_map:
                raise ValidationError(
                    f"KnowledgeGraph.edges[{index}]: unknown source node "
                    f"{edge.source_node_id!r}"
                )
            if edge.target_node_id not in node_map:
                raise ValidationError(
                    f"KnowledgeGraph.edges[{index}]: unknown target node "
                    f"{edge.target_node_id!r}"
                )
            if edge.source_node_id == edge.target_node_id:
                raise ValidationError(
                    f"KnowledgeGraph.edges[{index}]: self-loop on node "
                    f"{edge.source_node_id!r} is not allowed"
                )
            key = (edge.source_node_id, edge.target_node_id, edge.kind)
            if key in seen_edges:
                raise ValidationError(
                    "KnowledgeGraph.edges: duplicate edge "
                    f"{edge.source_node_id!r} -> {edge.target_node_id!r} ({edge.kind})"
                )
            seen_edges.add(key)
            self._edges.append(edge)

        self._prerequisites: dict[str, list[PrerequisiteEdge]] = {
            node_id: [] for node_id in self._nodes
        }
        self._dependents: dict[str, list[PrerequisiteEdge]] = {
            node_id: [] for node_id in self._nodes
        }
        for edge in self._edges:
            self._prerequisites[edge.target_node_id].append(edge)
            self._dependents[edge.source_node_id].append(edge)

        self._topological: list[str] = self._compute_topological_order()

    # -- construction helpers -------------------------------------------------

    def _compute_topological_order(self) -> list[str]:
        indegree: dict[str, int] = {node_id: 0 for node_id in self._nodes}
        for edge in self._edges:
            indegree[edge.target_node_id] += 1
        ready: list[str] = [node_id for node_id in self._nodes if indegree[node_id] == 0]
        order: list[str] = []
        cursor = 0
        while cursor < len(ready):
            node_id = ready[cursor]
            cursor += 1
            order.append(node_id)
            for edge in self._dependents[node_id]:
                target = edge.target_node_id
                indegree[target] -= 1
                if indegree[target] == 0:
                    ready.append(target)
        if len(order) != len(self._nodes):
            cycle_nodes = sorted(node_id for node_id, degree in indegree.items() if degree > 0)
            raise ValidationError(
                "KnowledgeGraph contains a cycle involving node(s): "
                f"{', '.join(cycle_nodes)}"
            )
        return order

    def _require_node(self, node_id: Any, where: str) -> None:
        if type(node_id) is not str or not node_id:
            raise ValidationError(f"{where}: expected a non-empty node_id string")
        if node_id not in self._nodes:
            raise ValidationError(f"{where}: unknown node_id {node_id!r}")

    # -- read API (frozen) ----------------------------------------------------

    def nodes_by_id(self) -> dict[str, KnowledgeNode]:
        """A copy of the node-id -> node mapping (preserves insertion order)."""

        return dict(self._nodes)

    def topological_order(self) -> list[str]:
        """Deterministic topological order of all node ids (prerequisites first)."""

        return list(self._topological)

    def prerequisite_closure(
        self,
        node_ids: Iterable[str],
        kinds: Iterable[str] = _DEFAULT_CLOSURE_KINDS,
    ) -> set[str]:
        """Transitive prerequisite node ids of ``node_ids`` (seeds excluded)."""

        if isinstance(node_ids, str):
            raise ValidationError(
                "KnowledgeGraph.prerequisite_closure(): node_ids must be an iterable "
                "of node_id strings, not a single string"
            )
        seeds: list[str] = []
        for node_id in node_ids:
            self._require_node(node_id, "KnowledgeGraph.prerequisite_closure()")
            seeds.append(node_id)
        if not seeds:
            return set()

        selected_kinds: tuple[str, ...]
        if isinstance(kinds, str):
            selected_kinds = (kinds,)
        else:
            selected_kinds = tuple(kinds)
        if not selected_kinds:
            raise ValidationError(
                "KnowledgeGraph.prerequisite_closure(): kinds must not be empty"
            )
        for kind in selected_kinds:
            if kind not in EDGE_KIND_VALUES:
                raise ValidationError(
                    f"KnowledgeGraph.prerequisite_closure(): unknown edge kind {kind!r}"
                )
        kind_set = set(selected_kinds)
        seed_set = set(seeds)

        closure: set[str] = set()
        seen: set[str] = set(seeds)
        frontier: list[str] = list(seeds)
        while frontier:
            current = frontier.pop()
            for edge in self._prerequisites[current]:
                if edge.kind not in kind_set:
                    continue
                source = edge.source_node_id
                if source in seen:
                    continue
                seen.add(source)
                if source not in seed_set:
                    closure.add(source)
                frontier.append(source)
        return closure

    def direct_prerequisites(self, node_id: str) -> list[PrerequisiteEdge]:
        """Edges whose target is ``node_id`` (insertion order)."""

        self._require_node(node_id, "KnowledgeGraph.direct_prerequisites()")
        return list(self._prerequisites[node_id])

    def hard_prerequisites(self, node_id: str) -> list[str]:
        """Direct ``HARD`` prerequisite source node ids of ``node_id`` (unique, ordered)."""

        self._require_node(node_id, "KnowledgeGraph.hard_prerequisites()")
        result: list[str] = []
        for edge in self._prerequisites[node_id]:
            if edge.kind == "HARD" and edge.source_node_id not in result:
                result.append(edge.source_node_id)
        return result

    def dependents(self, node_id: str) -> list[str]:
        """Direct dependant target node ids of ``node_id`` (unique, ordered)."""

        self._require_node(node_id, "KnowledgeGraph.dependents()")
        result: list[str] = []
        for edge in self._dependents[node_id]:
            if edge.target_node_id not in result:
                result.append(edge.target_node_id)
        return result

    def validate_objective(self, objective: LearningObjective) -> None:
        """Validate an objective against this graph (unknown nodes -> ValidationError)."""

        if not isinstance(objective, LearningObjective):
            raise ValidationError(
                "KnowledgeGraph.validate_objective(): expected a LearningObjective instance"
            )
        unknown = [node_id for node_id in objective.target_node_ids if node_id not in self._nodes]
        if unknown:
            raise ValidationError(
                "LearningObjective.target_node_ids references unknown node(s): "
                f"{unknown}"
            )
        required = objective.success_criteria.get("required_node_ids", [])
        unknown_required = [node_id for node_id in required if node_id not in self._nodes]
        if unknown_required:
            raise ValidationError(
                "LearningObjective.success_criteria.required_node_ids references unknown "
                f"node(s): {unknown_required}"
            )

    # -- additive convenience helpers (not part of the frozen minimal contract) --

    def node_ids(self) -> list[str]:
        """All node ids in insertion order."""

        return list(self._nodes)

    def edges(self) -> list[PrerequisiteEdge]:
        """A copy of the prerequisite edge list (insertion order)."""

        return list(self._edges)

    def __len__(self) -> int:
        return len(self._nodes)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"KnowledgeGraph(nodes={len(self._nodes)}, edges={len(self._edges)})"
