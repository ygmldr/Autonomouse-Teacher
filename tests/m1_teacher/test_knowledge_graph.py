"""Knowledge-graph contract tests for ``m1a.v0`` (B-PR1a).

Covers construction-time fail-closed validation (duplicate nodes, unknown edge
endpoints, self-loops, cycles, duplicate edges), deterministic topological
ordering, prerequisite closure/direct/hard/dependants semantics and objective
validation against the graph.

The graph shape mirrors the frozen CF binary-search fixture domain (8 nodes,
9 edges) so that the semantics tested here are the ones later PRs rely on.
"""

from __future__ import annotations

import pytest

from m1_teacher.contracts import (
    KnowledgeNode,
    LearningObjective,
    PrerequisiteEdge,
    ValidationError,
)
from m1_teacher.knowledge import KnowledgeGraph

# (node_id, difficulty, assessment_mode)
NODES = [
    ("cf.array.basics", 1, "DETERMINISTIC_JUDGE"),
    ("cf.sort.sortedness", 2, "DETERMINISTIC_JUDGE"),
    ("cf.search.linear", 1, "DETERMINISTIC_JUDGE"),
    ("cf.search.binary", 3, "DETERMINISTIC_JUDGE"),
    ("cf.search.boundary", 4, "DETERMINISTIC_JUDGE"),
    ("cf.search.lower_upper", 4, "DETERMINISTIC_JUDGE"),
    ("cf.complexity.log", 3, "RULE_RUBRIC"),
    ("cf.debug.edge_cases", 3, "RULE_RUBRIC"),
]

# (source, target, kind, weight)
EDGES = [
    ("cf.array.basics", "cf.sort.sortedness", "HARD", 1.0),
    ("cf.array.basics", "cf.search.linear", "HARD", 1.0),
    ("cf.sort.sortedness", "cf.search.binary", "HARD", 1.0),
    ("cf.search.linear", "cf.search.binary", "SOFT", 0.5),
    ("cf.search.binary", "cf.search.boundary", "HARD", 1.0),
    ("cf.search.binary", "cf.search.lower_upper", "HARD", 1.0),
    ("cf.search.binary", "cf.complexity.log", "SOFT", 0.5),
    ("cf.search.boundary", "cf.debug.edge_cases", "SOFT", 0.5),
    ("cf.sort.sortedness", "cf.search.lower_upper", "SOFT", 0.5),
]

NODE_IDS = [node_id for node_id, _, _ in NODES]


def _node(node_id: str, difficulty: int = 2) -> KnowledgeNode:
    return KnowledgeNode(
        node_id=node_id,
        domain_id="cf_binary_search",
        title=node_id,
        description=f"node {node_id}",
        difficulty=difficulty,
        assessment_mode="DETERMINISTIC_JUDGE",
    )


def _edge(source: str, target: str, kind: str = "HARD", weight: float = 1.0) -> PrerequisiteEdge:
    return PrerequisiteEdge(
        source_node_id=source,
        target_node_id=target,
        kind=kind,
        weight=weight,
    )


def _graph(
    nodes: list[KnowledgeNode] | None = None,
    edges: list[PrerequisiteEdge] | None = None,
) -> KnowledgeGraph:
    graph_nodes = [_node(node_id, difficulty) for node_id, difficulty, _ in NODES] if nodes is None else nodes
    graph_edges = [_edge(*raw) for raw in EDGES] if edges is None else edges
    return KnowledgeGraph(graph_nodes, graph_edges)


def _objective() -> LearningObjective:
    return LearningObjective(
        objective_id="obj.cf.binary_search.mastery",
        domain_id="cf_binary_search",
        title="掌握二分查找与边界处理",
        description="实现二分查找及边界变体",
        target_node_ids=[
            "cf.search.binary",
            "cf.search.boundary",
            "cf.search.lower_upper",
            "cf.complexity.log",
        ],
        success_criteria={
            "min_mastery": 0.7,
            "required_node_ids": ["cf.search.binary", "cf.search.boundary"],
            "max_error_rate": 0.3,
        },
    )


# ---------------------------------------------------------------------------
# Construction-time validation
# ---------------------------------------------------------------------------


def test_graph_construction_and_basic_reads() -> None:
    graph = _graph()
    assert len(graph) == 8
    assert graph.node_ids() == NODE_IDS
    assert [edge.source_node_id for edge in graph.edges()] == [raw[0] for raw in EDGES]
    node_map = graph.nodes_by_id()
    assert set(node_map) == set(NODE_IDS)
    assert node_map["cf.search.binary"].difficulty == 3


def test_nodes_by_id_returns_a_defensive_copy() -> None:
    graph = _graph()
    mapping = graph.nodes_by_id()
    mapping.pop("cf.array.basics")
    assert "cf.array.basics" in graph.nodes_by_id()
    assert len(graph) == 8


def test_duplicate_node_ids_are_rejected() -> None:
    nodes = [_node("cf.a"), _node("cf.a")]
    with pytest.raises(ValidationError, match="duplicate node_id"):
        KnowledgeGraph(nodes, [])


@pytest.mark.parametrize(
    ("source", "target"),
    [
        ("cf.unknown", "cf.array.basics"),
        ("cf.array.basics", "cf.unknown"),
    ],
)
def test_unknown_edge_endpoints_are_rejected(source: str, target: str) -> None:
    nodes = [_node("cf.array.basics")]
    with pytest.raises(ValidationError, match="unknown (source|target) node"):
        KnowledgeGraph(nodes, [_edge(source, target)])


def test_self_loop_is_rejected() -> None:
    nodes = [_node("cf.array.basics")]
    with pytest.raises(ValidationError, match="self-loop"):
        KnowledgeGraph(nodes, [_edge("cf.array.basics", "cf.array.basics")])


def test_cycle_is_rejected() -> None:
    nodes = [_node("cf.a"), _node("cf.b"), _node("cf.c")]
    edges = [_edge("cf.a", "cf.b"), _edge("cf.b", "cf.c"), _edge("cf.c", "cf.a")]
    with pytest.raises(ValidationError, match="cycle"):
        KnowledgeGraph(nodes, edges)


def test_two_node_cycle_is_rejected() -> None:
    nodes = [_node("cf.a"), _node("cf.b")]
    with pytest.raises(ValidationError, match="cycle"):
        KnowledgeGraph(nodes, [_edge("cf.a", "cf.b"), _edge("cf.b", "cf.a")])


def test_duplicate_edges_are_rejected() -> None:
    nodes = [_node("cf.a"), _node("cf.b")]
    with pytest.raises(ValidationError, match="duplicate edge"):
        KnowledgeGraph(nodes, [_edge("cf.a", "cf.b"), _edge("cf.a", "cf.b")])


def test_same_pair_with_different_kinds_is_allowed() -> None:
    nodes = [_node("cf.a"), _node("cf.b")]
    graph = KnowledgeGraph(nodes, [_edge("cf.a", "cf.b", "HARD"), _edge("cf.a", "cf.b", "SOFT")])
    assert len(graph.edges()) == 2
    assert graph.hard_prerequisites("cf.b") == ["cf.a"]


@pytest.mark.parametrize(
    ("nodes", "edges"),
    [
        (None, []),
        ([], None),
    ],
)
def test_non_list_arguments_are_rejected(nodes: object, edges: object) -> None:
    with pytest.raises(ValidationError):
        KnowledgeGraph(nodes, edges)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("nodes", "edges"),
    [
        ([object()], []),
        ([_node("cf.a")], [object()]),
    ],
)
def test_non_record_arguments_are_rejected(nodes: list, edges: list) -> None:
    with pytest.raises(ValidationError):
        KnowledgeGraph(nodes, edges)


def test_empty_graph_is_valid() -> None:
    graph = KnowledgeGraph([], [])
    assert graph.topological_order() == []
    assert graph.nodes_by_id() == {}
    assert graph.prerequisite_closure([]) == set()
    assert len(graph) == 0


# ---------------------------------------------------------------------------
# Topological order
# ---------------------------------------------------------------------------


def test_topological_order_respects_all_edges() -> None:
    graph = _graph()
    order = graph.topological_order()
    assert sorted(order) == sorted(NODE_IDS)
    assert len(order) == len(set(order))
    position = {node_id: index for index, node_id in enumerate(order)}
    for source, target, _, _ in EDGES:
        assert position[source] < position[target], f"{source} must precede {target}"
    assert order[0] == "cf.array.basics"
    assert order[-1] == "cf.debug.edge_cases"


def test_topological_order_is_deterministic() -> None:
    assert _graph().topological_order() == _graph().topological_order()
    graph = _graph()
    assert graph.topological_order() == graph.topological_order()


def test_topological_order_returns_a_defensive_copy() -> None:
    graph = _graph()
    order = graph.topological_order()
    order.reverse()
    assert graph.topological_order()[0] == "cf.array.basics"


# ---------------------------------------------------------------------------
# Prerequisites / dependants
# ---------------------------------------------------------------------------


def test_direct_prerequisites() -> None:
    graph = _graph()
    direct = graph.direct_prerequisites("cf.search.binary")
    assert [(edge.source_node_id, edge.kind) for edge in direct] == [
        ("cf.sort.sortedness", "HARD"),
        ("cf.search.linear", "SOFT"),
    ]
    assert graph.direct_prerequisites("cf.array.basics") == []


def test_hard_prerequisites() -> None:
    graph = _graph()
    assert graph.hard_prerequisites("cf.search.binary") == ["cf.sort.sortedness"]
    assert graph.hard_prerequisites("cf.search.lower_upper") == ["cf.search.binary"]
    assert graph.hard_prerequisites("cf.debug.edge_cases") == []
    assert graph.hard_prerequisites("cf.array.basics") == []


def test_dependents() -> None:
    graph = _graph()
    assert graph.dependents("cf.array.basics") == ["cf.sort.sortedness", "cf.search.linear"]
    assert graph.dependents("cf.search.binary") == [
        "cf.search.boundary",
        "cf.search.lower_upper",
        "cf.complexity.log",
    ]
    assert graph.dependents("cf.debug.edge_cases") == []


@pytest.mark.parametrize(
    "method_name",
    ["direct_prerequisites", "hard_prerequisites", "dependents"],
)
def test_prerequisite_queries_reject_unknown_nodes(method_name: str) -> None:
    graph = _graph()
    with pytest.raises(ValidationError, match="unknown node_id"):
        getattr(graph, method_name)("cf.does.not.exist")


# ---------------------------------------------------------------------------
# Prerequisite closure
# ---------------------------------------------------------------------------


def test_prerequisite_closure_default_kinds() -> None:
    graph = _graph()
    assert graph.prerequisite_closure(["cf.search.binary"]) == {
        "cf.array.basics",
        "cf.sort.sortedness",
        "cf.search.linear",
    }
    assert graph.prerequisite_closure(["cf.search.lower_upper"]) == {
        "cf.array.basics",
        "cf.sort.sortedness",
        "cf.search.binary",
        "cf.search.linear",
    }
    assert graph.prerequisite_closure(["cf.debug.edge_cases"]) == {
        "cf.array.basics",
        "cf.sort.sortedness",
        "cf.search.linear",
        "cf.search.binary",
        "cf.search.boundary",
    }
    assert graph.prerequisite_closure(["cf.array.basics"]) == set()


def test_prerequisite_closure_kind_filtering() -> None:
    graph = _graph()
    assert graph.prerequisite_closure(["cf.search.binary"], kinds=("HARD",)) == {
        "cf.array.basics",
        "cf.sort.sortedness",
    }
    assert graph.prerequisite_closure(["cf.search.binary"], kinds=("SOFT",)) == {
        "cf.search.linear"
    }
    assert graph.prerequisite_closure(["cf.search.binary"], kinds=["HARD", "SOFT"]) == {
        "cf.array.basics",
        "cf.sort.sortedness",
        "cf.search.linear",
    }


def test_prerequisite_closure_never_contains_seed_nodes() -> None:
    graph = _graph()
    closure = graph.prerequisite_closure(["cf.sort.sortedness", "cf.search.binary"])
    assert "cf.sort.sortedness" not in closure
    assert "cf.search.binary" not in closure
    assert closure == {"cf.array.basics", "cf.search.linear"}


def test_seed_that_is_prerequisite_of_another_seed_is_excluded() -> None:
    nodes = [_node("cf.a"), _node("cf.b")]
    graph = KnowledgeGraph(nodes, [_edge("cf.a", "cf.b")])
    # cf.a is a prerequisite of cf.b, but both are seeds -> excluded by contract.
    assert graph.prerequisite_closure(["cf.a", "cf.b"]) == set()


def test_prerequisite_closure_empty_seeds() -> None:
    assert _graph().prerequisite_closure([]) == set()


@pytest.mark.parametrize(
    "node_ids",
    [
        ["cf.unknown"],
        ["cf.search.binary", "cf.unknown"],
        ["cf.search.binary", ""],
        "cf.search.binary",  # bare string is an error, not an iterable of chars
    ],
)
def test_prerequisite_closure_rejects_bad_node_ids(node_ids: object) -> None:
    with pytest.raises(ValidationError):
        _graph().prerequisite_closure(node_ids)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "kinds",
    [
        ("MAYBE",),
        ("HARD", "MAYBE"),
        (),
    ],
)
def test_prerequisite_closure_rejects_bad_kinds(kinds: tuple[str, ...]) -> None:
    with pytest.raises(ValidationError):
        _graph().prerequisite_closure(["cf.search.binary"], kinds=kinds)


def test_prerequisite_closure_single_kind_string_is_accepted() -> None:
    graph = _graph()
    assert graph.prerequisite_closure(["cf.search.binary"], kinds="HARD") == {
        "cf.array.basics",
        "cf.sort.sortedness",
    }


# ---------------------------------------------------------------------------
# Objective validation
# ---------------------------------------------------------------------------


def test_validate_objective_accepts_valid_objective() -> None:
    _graph().validate_objective(_objective())


def test_validate_objective_rejects_unknown_target_node() -> None:
    objective = _objective()
    objective.target_node_ids = ["cf.search.binary", "cf.not.in.graph"]
    with pytest.raises(ValidationError, match="unknown node"):
        _graph().validate_objective(objective)


def test_validate_objective_rejects_unknown_required_node() -> None:
    objective = _objective()
    # Bypasses the record-level subset check on purpose: the graph must defend too.
    objective.success_criteria["required_node_ids"] = ["cf.not.in.graph"]
    with pytest.raises(ValidationError, match="unknown node"):
        _graph().validate_objective(objective)


def test_validate_objective_rejects_wrong_type() -> None:
    with pytest.raises(ValidationError):
        _graph().validate_objective(object())  # type: ignore[arg-type]
