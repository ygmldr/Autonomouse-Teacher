"""Tests for the B3 diagnostic engine (``m1_teacher.diagnostic``).

All data is synthetic/CC0-1.0 fixture data; nothing here reads hidden scoring
material.  The tests assert real behaviour: deterministic item selection,
structured reasons, evidence-gap prioritisation, exclusion, insufficient
evidence semantics and the hidden-answer/network isolation boundary.
"""

from __future__ import annotations

import ast
import json
import shutil
from pathlib import Path

import pytest

from m1_teacher.contracts.errors import ValidationError
from m1_teacher.contracts.types import (
    AssessmentItem,
    HistoryEvent,
    LearnerGoal,
    LearnerSnapshot,
    MasteryEstimate,
    Reason,
)
from m1_teacher.diagnostic import DiagnosticEngine, DiagnosticPolicy
from m1_teacher.domains import CFBinarySearchDomainAdapter
from m1_teacher.knowledge import KnowledgeGraph

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = REPO_ROOT / "fixtures" / "m1_teacher"
T0 = "2026-11-20T00:00:00Z"

#: The 7 candidate nodes for the frozen binary-search objective:
#: 4 objective targets plus their HARD/SOFT prerequisite closure.
CANDIDATE_NODES = (
    "cf.array.basics",
    "cf.sort.sortedness",
    "cf.search.linear",
    "cf.search.binary",
    "cf.search.boundary",
    "cf.search.lower_upper",
    "cf.complexity.log",
)
REQUIRED_NODES = ("cf.search.binary", "cf.search.boundary")


@pytest.fixture(scope="module")
def adapter() -> CFBinarySearchDomainAdapter:
    domain = CFBinarySearchDomainAdapter(FIXTURES_DIR)
    domain.validate()
    return domain


@pytest.fixture(scope="module")
def graph(adapter: CFBinarySearchDomainAdapter) -> KnowledgeGraph:
    return KnowledgeGraph(adapter.knowledge_nodes(), adapter.prerequisite_edges())


@pytest.fixture(scope="module")
def objective(adapter: CFBinarySearchDomainAdapter):
    return adapter.objectives()[0]


@pytest.fixture(scope="module")
def engine(adapter, graph) -> DiagnosticEngine:
    return DiagnosticEngine(adapter, graph)


def make_goal(objective, learner_id: str = "learner-A") -> LearnerGoal:
    return LearnerGoal(
        goal_id=f"goal-{learner_id}",
        learner_id=learner_id,
        objective_id=objective.objective_id,
        created_at=T0,
    )


def make_mastery(node_id: str, value: float, evidence_count: int, confidence: float = 0.9):
    return MasteryEstimate(
        node_id=node_id,
        value=value,
        confidence=confidence,
        evidence_count=evidence_count,
        created_at=T0,
        updated_at=T0,
    )


def make_snapshot(
    learner_id: str = "learner-A",
    masteries: dict[str, tuple[float, int, float]] | None = None,
    error_counts: dict[str, int] | None = None,
    completed_item_ids: list[str] | None = None,
    revision: int = 1,
) -> LearnerSnapshot:
    mastery_map = {
        node_id: make_mastery(node_id, value, evidence_count, confidence)
        for node_id, (value, evidence_count, confidence) in (masteries or {}).items()
    }
    return LearnerSnapshot(
        learner_id=learner_id,
        masteries=mastery_map,
        completed_item_ids=list(completed_item_ids or []),
        error_counts=dict(error_counts or {}),
        revision=revision,
        created_at=T0,
        updated_at=T0,
    )


def make_history_event(
    event_id: str,
    seq: int,
    event_type: str,
    payload: dict,
    learner_id: str = "learner-A",
) -> HistoryEvent:
    return HistoryEvent(
        event_id=event_id,
        learner_id=learner_id,
        session_id="session-1",
        seq=seq,
        event_type=event_type,
        payload=payload,
        created_at=T0,
    )


def evidenced_snapshot(
    learner_id: str = "learner-A",
    error_counts: dict[str, int] | None = None,
    **overrides,
) -> LearnerSnapshot:
    """Every candidate node observed, most of them mastered."""

    spec = {
        "cf.array.basics": (0.90, 4, 0.90),
        "cf.sort.sortedness": (0.85, 4, 0.90),
        "cf.search.linear": (0.80, 3, 0.85),
        "cf.search.binary": (0.85, 4, 0.90),
        "cf.search.boundary": (0.85, 4, 0.90),
        "cf.search.lower_upper": (0.80, 3, 0.85),
        "cf.complexity.log": (0.75, 3, 0.80),
    }
    spec.update(overrides)
    return make_snapshot(learner_id=learner_id, masteries=spec, error_counts=error_counts)


# ---------------------------------------------------------------------------
# READY selection behaviour
# ---------------------------------------------------------------------------


def test_empty_snapshot_selects_legal_base_item(adapter, engine, objective) -> None:
    goal = make_goal(objective)
    snapshot = make_snapshot()
    result = engine.select_next_item(goal, objective, snapshot)

    assert result.status == "READY"
    assert result.learner_id == "learner-A"
    assert result.created_at == T0
    assert result.selected_item_id is not None
    item = next(
        item for item in adapter.assessment_items() if item.item_id == result.selected_item_id
    )
    assert isinstance(item, AssessmentItem)
    closure = graph_closure(adapter)
    assert result.target_node_id in closure
    assert set(item.node_ids) & {result.target_node_id}
    # A brand-new learner gets the most basic item (difficulty 1, MCQ first).
    assert result.selected_item_id == "item.bs.mcq.001"
    assert result.target_node_id == "cf.array.basics"
    assert result.hypothesis
    assert isinstance(result.reason, Reason)
    assert result.reason.code
    assert len(result.reason.detail) > 20
    assert result.reason.policy_version == "m1a.diagnostic.v0"
    assert result.evidence_refs and result.evidence_refs[0].startswith("snapshot:")


def graph_closure(adapter) -> set[str]:
    graph = KnowledgeGraph(adapter.knowledge_nodes(), adapter.prerequisite_edges())
    objective = adapter.objectives()[0]
    targets = list(objective.target_node_ids)
    return set(targets) | graph.prerequisite_closure(targets, kinds=("HARD", "SOFT"))


def test_observed_evidence_moves_to_next_gap(engine, objective) -> None:
    # Everything is evidenced except boundary, whose estimate is still thin and
    # low: the engine must pick the remaining evidence gap, not a mastered node.
    snapshot = evidenced_snapshot(
        **{
            "cf.search.boundary": (0.25, 1, 0.40),
            "cf.search.lower_upper": (0.15, 3, 0.90),
            "cf.complexity.log": (0.30, 2, 0.80),
        }
    )
    result = engine.select_next_item(make_goal(objective), objective, snapshot)
    assert result.status == "READY"
    assert result.target_node_id == "cf.search.boundary"
    assert result.selected_item_id in {
        "item.bs.mcq.005",
        "item.bs.code.003",
        "item.bs.short.001",
    }
    assert result.reason.code == "TARGET_EVIDENCE_GAP"
    assert result.reason.node_ids == ["cf.search.boundary"]
    assert "cf.search.boundary" in result.reason.detail


def test_error_history_marks_node_as_diagnostic_gap(engine, objective) -> None:
    # Boundary has (just) sufficient evidence, but repeated off-by-one errors
    # make the estimate untrustworthy -> probe again instead of trusting it.
    snapshot = evidenced_snapshot(
        **{"cf.search.boundary": (0.40, 2, 0.70)},
        error_counts={"cf.search.boundary": 3, "off_by_one": 2},
    )
    result = engine.select_next_item(make_goal(objective), objective, snapshot)
    assert result.status == "READY"
    assert result.target_node_id == "cf.search.boundary"


def test_item_selection_is_deterministic(engine, objective) -> None:
    goal = make_goal(objective)
    snapshot = evidenced_snapshot(**{"cf.search.boundary": (0.25, 1, 0.40)})
    first = engine.select_next_item(goal, objective, snapshot)
    second = engine.select_next_item(goal, objective, snapshot)
    assert first.to_dict() == second.to_dict()
    assert first.diagnosis_id == second.diagnosis_id


# ---------------------------------------------------------------------------
# INSUFFICIENT_EVIDENCE semantics
# ---------------------------------------------------------------------------


def test_goal_already_met_returns_insufficient_evidence(engine, adapter, objective) -> None:
    snapshot = evidenced_snapshot()
    result = engine.select_next_item(make_goal(objective), objective, snapshot)
    assert result.status == "INSUFFICIENT_EVIDENCE"
    assert result.selected_item_id is None
    assert isinstance(result.reason, Reason)
    assert result.reason.code == "INSUFFICIENT_EVIDENCE"
    assert "satisfied" in result.reason.detail
    assert result.reason.node_ids
    assert result.target_node_id in graph_closure(adapter)




def test_sufficient_evidence_but_unmet_goal_returns_insufficient(engine, objective) -> None:
    # All candidate nodes have enough evidence, yet mastery is too low: this is
    # a teaching/planning gap, not a diagnostic one; never guess mastery.
    snapshot = make_snapshot(
        masteries={node_id: (0.20, 3, 0.90) for node_id in CANDIDATE_NODES}
    )
    result = engine.select_next_item(make_goal(objective), objective, snapshot)
    assert result.status == "INSUFFICIENT_EVIDENCE"
    assert result.selected_item_id is None
    assert "teaching or planning" in result.reason.detail
    assert result.reason.code == "INSUFFICIENT_EVIDENCE"


def test_exclude_item_ids_are_honoured(engine, objective, adapter) -> None:
    goal = make_goal(objective)
    snapshot = make_snapshot()
    first = engine.select_next_item(goal, objective, snapshot)
    second = engine.select_next_item(
        goal, objective, snapshot, exclude_item_ids={first.selected_item_id}
    )
    assert second.status == "READY"
    assert second.selected_item_id != first.selected_item_id
    third = engine.select_next_item(
        goal,
        objective,
        snapshot,
        exclude_item_ids={item.item_id for item in adapter.assessment_items()},
    )
    assert third.status == "INSUFFICIENT_EVIDENCE"
    assert third.selected_item_id is None
    assert "excluded" in third.reason.detail


def test_snapshot_objective_mismatch_returns_insufficient(engine, objective) -> None:
    snapshot = make_snapshot(masteries={"unknown.node": (0.9, 3, 0.9)})
    result = engine.select_next_item(make_goal(objective), objective, snapshot)
    assert result.status == "INSUFFICIENT_EVIDENCE"
    assert result.selected_item_id is None
    assert "mismatch" in result.reason.detail
    assert "unknown.node" in result.reason.detail


# ---------------------------------------------------------------------------
# Policy injection and history usage
# ---------------------------------------------------------------------------


def test_policy_injection_changes_node_selection(engine, adapter, graph, objective) -> None:
    snapshot = evidenced_snapshot(
        **{
            "cf.search.boundary": (0.25, 1, 0.70),
            "cf.search.lower_upper": (0.15, 3, 0.90),
        }
    )
    default = engine.select_next_item(make_goal(objective), objective, snapshot)
    assert default.target_node_id == "cf.search.boundary"

    strict_engine = DiagnosticEngine(
        adapter, graph, DiagnosticPolicy(min_evidence_count=5)
    )
    strict = strict_engine.select_next_item(make_goal(objective), objective, snapshot)
    assert strict.status == "READY"
    assert strict.target_node_id == "cf.search.lower_upper"
    assert strict.target_node_id != default.target_node_id
    assert strict.reason.policy_version == "m1a.diagnostic.v0"


def test_recently_presented_item_is_deprioritised(engine, objective) -> None:
    snapshot = evidenced_snapshot(**{"cf.search.boundary": (0.25, 1, 0.40)})
    default = engine.select_next_item(make_goal(objective), objective, snapshot)
    assert default.selected_item_id == "item.bs.mcq.005"
    history = [
        make_history_event(
            "hist-1",
            1,
            "ITEM_PRESENTED",
            {"item_id": "item.bs.mcq.005", "node_ids": ["cf.search.boundary"]},
        )
    ]
    with_history = engine.select_next_item(
        make_goal(objective), objective, snapshot, history=history
    )
    assert with_history.selected_item_id != "item.bs.mcq.005"
    assert any(ref == "history:hist-1" for ref in with_history.evidence_refs)


def test_history_evidence_refs_are_attached(engine, objective) -> None:
    snapshot = evidenced_snapshot(**{"cf.search.boundary": (0.25, 1, 0.40)})
    history = [
        make_history_event(
            "hist-a", 1, "ASSESSED", {"node_ids": ["cf.search.boundary"], "status": "INCORRECT"}
        ),
        make_history_event(
            "hist-b", 2, "ITEM_PRESENTED", {"node_ids": ["cf.search.boundary"]}
        ),
    ]
    result = engine.select_next_item(
        make_goal(objective), objective, snapshot, history=history
    )
    assert "history:hist-a" in result.evidence_refs
    assert "history:hist-b" in result.evidence_refs


# ---------------------------------------------------------------------------
# Fail-closed input validation
# ---------------------------------------------------------------------------


def test_invalid_inputs_fail_closed(engine, objective) -> None:
    goal = make_goal(objective)
    snapshot = make_snapshot()
    with pytest.raises(ValidationError):
        engine.select_next_item(goal, objective, make_snapshot(learner_id="other-learner"))
    with pytest.raises(ValidationError):
        engine.select_next_item(
            make_goal(objective), objective, make_snapshot(), history="not-a-list"
        )
    with pytest.raises(ValidationError):
        engine.select_next_item(
            make_goal(objective), objective, snapshot, exclude_item_ids=[123]
        )
    with pytest.raises(ValidationError):
        DiagnosticEngine(object(), object())  # type: ignore[arg-type]
    assert isinstance(DiagnosticPolicy, type)
    assert strict_policy_is_injectable(engine, objective)


def strict_policy_is_injectable(engine, objective) -> bool:
    # A custom policy is a distinct object yet keeps the same contract version.
    policy = DiagnosticPolicy(min_evidence_count=3)
    return policy.policy_version == "m1a.diagnostic.v0" and engine is not None


# ---------------------------------------------------------------------------
# Hidden-answer / network boundary
# ---------------------------------------------------------------------------


def _copy_fixtures_without_hidden(destination: Path) -> Path:
    target = destination / "fixtures"
    shutil.copytree(FIXTURES_DIR, target, ignore=shutil.ignore_patterns("scoring"))
    assert not (target / "domains" / "cf_binary_search" / "scoring").exists()
    return target


def test_behaviour_unchanged_without_hidden_scoring_directory(
    tmp_path: Path, adapter, graph, objective
) -> None:
    fixtures_copy = _copy_fixtures_without_hidden(tmp_path)
    copy_adapter = CFBinarySearchDomainAdapter(fixtures_copy)
    copy_adapter.validate()
    copy_graph = KnowledgeGraph(
        copy_adapter.knowledge_nodes(), copy_adapter.prerequisite_edges()
    )
    assert (
        copy_adapter.objectives()[0].to_dict() == objective.to_dict()
    )
    original = DiagnosticEngine(adapter, graph).select_next_item(
        make_goal(objective), objective, evidenced_snapshot(**{"cf.search.boundary": (0.2, 1, 0.3)})
    )
    copied = DiagnosticEngine(copy_adapter, copy_graph).select_next_item(
        make_goal(objective), objective, evidenced_snapshot(**{"cf.search.boundary": (0.2, 1, 0.3)})
    )
    assert original.to_dict() == copied.to_dict()


def test_tampering_hidden_scoring_does_not_change_behaviour(tmp_path: Path, adapter, graph, objective) -> None:
    target = tmp_path / "fixtures"
    shutil.copytree(FIXTURES_DIR, target)
    hidden_dir = target / "domains" / "cf_binary_search" / "scoring"
    for spec_path in hidden_dir.glob("*.json"):
        spec_path.write_text("{not-valid-hidden-json", encoding="utf-8")
    tampered_adapter = CFBinarySearchDomainAdapter(target)
    tampered_adapter.validate()
    tampered_graph = KnowledgeGraph(
        tampered_adapter.knowledge_nodes(), tampered_adapter.prerequisite_edges()
    )
    pristine = DiagnosticEngine(adapter, graph).select_next_item(
        make_goal(objective), objective, make_snapshot()
    )
    tampered = DiagnosticEngine(tampered_adapter, tampered_graph).select_next_item(
        make_goal(objective), objective, make_snapshot()
    )
    assert pristine.to_dict() == tampered.to_dict()


def test_diagnostic_source_has_no_hidden_material_or_network() -> None:
    source_dir = REPO_ROOT / "m1_teacher" / "diagnostic"
    files = sorted(path for path in source_dir.rglob("*.py"))
    assert files
    forbidden_roots = {
        "autoteacher_m0",
        "socket",
        "httpx",
        "requests",
        "urllib",
        "urllib3",
        "aiohttp",
        "ssl",
        "http",
        "os",
        "subprocess",
    }
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert "scoring/" not in text, f"{path} references the hidden evaluation path"
        tree = ast.parse(text, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in forbidden_roots, (
                        f"{path} imports forbidden module {alias.name}"
                    )
            elif isinstance(node, ast.ImportFrom):
                root = (node.module or "").split(".")[0]
                assert root not in forbidden_roots, f"{path} imports forbidden module {node.module}"
            elif isinstance(node, ast.Call):
                func = node.func
                name = getattr(func, "id", None) or getattr(func, "attr", None)
                assert name not in {"open", "read_text", "read_bytes", "iterdir"}, (
                    f"{path} performs filesystem I/O ({name})"
                )
    # The engine source must not reference the hidden evaluation *path*.
    assert not any("scoring/" in path.read_text(encoding="utf-8") for path in files)


def test_result_json_contains_no_hidden_material(engine, objective) -> None:
    result_json = engine.select_next_item(
        make_goal(objective), objective, make_snapshot()
    ).to_json()
    assert "scoring" not in result_json
    assert json.loads(result_json)["schema_version"] == "m1a.v0"
