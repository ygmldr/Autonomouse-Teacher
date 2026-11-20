"""Tests for the teacher-visible Interview domain adapter (B-PR4 vertical layer).

Covers: DomainAdapter protocol conformance, fixture-driven knowledge graph /
objectives / assessment-item metadata, five-stage teacher-visible follow-up
ladder, teaching content coverage, deterministic serialisation, hidden-scoring
separation (the adapter works with the ``rubrics/`` tree physically removed),
fail-closed fixture validation and offline/M0 isolation.

The adapter is read-only and teacher-facing; it must never expose rubric
expectations, expected answers or hidden test material.
"""

from __future__ import annotations

import ast
import inspect
import json
import shutil
from pathlib import Path

import pytest

from m1_teacher.contracts.domain import DomainAdapter, DomainRegistry
from m1_teacher.contracts.errors import ConflictError, NotFoundError, ValidationError
from m1_teacher.domains import interview as interview_module
from m1_teacher.domains.interview import (
    DOMAIN_ID,
    FOLLOW_UP_STAGES,
    STAGE_LABELS,
    FollowUpProbe,
    InterviewDomainAdapter,
    build_interview_registry,
    default_fixtures_root,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_ROOT = REPO_ROOT / "fixtures" / "m1_teacher"
INTERVIEW_DIR = FIXTURES_ROOT / "vertical" / "interview"

HIDDEN_TOKENS = (
    "rubric_points",
    "factual_correctness",
    "explanation_clarity",
    "engineering_feasibility",
    "evidence_sufficiency",
    "expectations",
    "misconception",
    "reference_answer",
    "answer_key",
    "expected_score",
)


def _adapter() -> InterviewDomainAdapter:
    return InterviewDomainAdapter(FIXTURES_ROOT)


@pytest.fixture(scope="module")
def adapter() -> InterviewDomainAdapter:
    instance = InterviewDomainAdapter(FIXTURES_ROOT)
    instance.validate()
    return instance


def _assert_no_hidden_tokens(blob: str, where: str) -> None:
    lowered = blob.lower()
    for token in HIDDEN_TOKENS:
        assert token not in lowered, f"{where} leaked hidden token {token!r}"


# ---------------------------------------------------------------------------
# Protocol / fixture shape
# ---------------------------------------------------------------------------


def test_adapter_implements_frozen_domain_protocol(adapter: InterviewDomainAdapter) -> None:
    assert isinstance(adapter, DomainAdapter)
    assert adapter.domain_id == DOMAIN_ID == "interview_coach"
    assert adapter.domain_version == "0.1.0"

    nodes = adapter.knowledge_nodes()
    edges = adapter.prerequisite_edges()
    objectives = adapter.objectives()
    items = adapter.assessment_items()

    assert len(nodes) == 4, "one teacher-visible knowledge node per interview track"
    assert len(edges) == 4
    assert len(objectives) == 4
    assert len(items) >= 20, "task-3 corpus requires at least 20 interview questions"

    node_ids = {node.node_id for node in nodes}
    assert len(node_ids) == len(nodes)
    for node in nodes:
        assert node.domain_id == DOMAIN_ID
        assert node.assessment_mode == "RULE_RUBRIC"
        assert 1 <= node.difficulty <= 5
        assert node.title.strip() and node.description.strip()

    for edge in edges:
        assert edge.source_node_id in node_ids and edge.target_node_id in node_ids
        assert edge.kind in ("HARD", "SOFT")
        assert 0.0 <= edge.weight <= 1.0

    for objective in objectives:
        assert objective.domain_id == DOMAIN_ID
        assert objective.target_node_ids
        assert set(objective.success_criteria) == {
            "min_mastery",
            "required_node_ids",
            "max_error_rate",
        }
        assert set(objective.success_criteria["required_node_ids"]) <= set(
            objective.target_node_ids
        )

    for item in items:
        assert item.domain_id == DOMAIN_ID
        assert item.item_type == "SHORT_ANSWER"
        assert item.deterministic is False
        assert item.max_score == 1.0
        assert item.options == []
        assert item.node_ids and set(item.node_ids) <= node_ids
        assert 1 <= item.difficulty <= 5
        assert item.prompt.strip()
        assert item.scoring_spec_ref.startswith("scoring/")
        assert item.scoring_spec_ref.endswith(".json")
        assert ".." not in item.scoring_spec_ref


def test_adapter_serialisation_is_deterministic() -> None:
    first, second = _adapter(), _adapter()
    assert [node.to_dict() for node in first.knowledge_nodes()] == [
        node.to_dict() for node in second.knowledge_nodes()
    ]
    assert [item.to_dict() for item in first.assessment_items()] == [
        item.to_dict() for item in second.assessment_items()
    ]
    # Fixed fixture timestamp: no wall clock leaks into records.
    assert {node.created_at for node in first.knowledge_nodes()} == {"2026-11-20T00:00:00Z"}


def test_assessment_items_filter_by_node(adapter: InterviewDomainAdapter) -> None:
    for node in adapter.knowledge_nodes():
        filtered = adapter.assessment_items(node.node_id)
        assert filtered
        assert all(node.node_id in item.node_ids for item in filtered)
    assert len(adapter.assessment_items()) == sum(
        len(adapter.assessment_items(node.node_id)) for node in adapter.knowledge_nodes()
    )
    with pytest.raises(NotFoundError):
        adapter.assessment_items("interview.node.does-not-exist")


# ---------------------------------------------------------------------------
# Five-stage follow-up ladder (teacher-visible teaching content)
# ---------------------------------------------------------------------------


def test_follow_up_ladder_has_exactly_five_ordered_stages(adapter: InterviewDomainAdapter) -> None:
    assert FOLLOW_UP_STAGES == (
        "concept",
        "hypothesis",
        "complexity",
        "experiment_design",
        "online_triage",
    )
    for item in adapter.assessment_items():
        probes = adapter.follow_up_ladder(item.item_id)
        assert len(probes) == 5
        assert all(isinstance(probe, FollowUpProbe) for probe in probes)
        assert tuple(probe.stage for probe in probes) == FOLLOW_UP_STAGES
        assert tuple(probe.label for probe in probes) == tuple(
            STAGE_LABELS[stage] for stage in FOLLOW_UP_STAGES
        )
        for probe in probes:
            assert probe.prompt.strip()
        _assert_no_hidden_tokens(json.dumps([probe.to_dict() for probe in probes]), item.item_id)


def test_follow_up_ladder_errors_fail_closed(adapter: InterviewDomainAdapter) -> None:
    with pytest.raises(NotFoundError):
        adapter.follow_up_ladder("interview.item.not-a-question")
    with pytest.raises(ValidationError):
        adapter.follow_up_ladder("   ")
    with pytest.raises(NotFoundError):
        adapter.question_metadata("interview.item.not-a-question")
    with pytest.raises(ValidationError):
        adapter.question_metadata(None)  # type: ignore[arg-type]


def test_requires_project_facts_is_exposed_per_item(adapter: InterviewDomainAdapter) -> None:
    flags = {
        item.item_id: adapter.requires_project_facts(item.item_id)
        for item in adapter.assessment_items()
    }
    assert set(flags.values()) == {True, False}, "fixture must cover both sides of the boundary"
    assert flags["interview.item.q-eng-001"] is True
    assert flags["interview.item.q-ml-001"] is False
    metadata = adapter.question_metadata("interview.item.q-eng-001")
    assert metadata["track"] == "engineering_metrics"
    assert metadata["requires_project_facts"] is True
    assert set(metadata) == {"question_id", "track", "topic", "requires_project_facts"}


# ---------------------------------------------------------------------------
# Teaching content
# ---------------------------------------------------------------------------


def test_teaching_content_matrix(adapter: InterviewDomainAdapter) -> None:
    for node in adapter.knowledge_nodes():
        for kind in ("EXPLAIN", "HINT_L1", "HINT_L2", "HINT_L3", "REVIEW"):
            content = adapter.teaching_content(node.node_id, kind)
            assert content.strip()
            _assert_no_hidden_tokens(content, f"{node.node_id}.{kind}")
        practice = adapter.teaching_content(node.node_id, "PRACTICE")
        item_ids = json.loads(practice)
        assert item_ids == [
            item.item_id for item in adapter.assessment_items() if node.node_id in item.node_ids
        ]
        assert item_ids

    with pytest.raises(ValidationError):
        adapter.teaching_content(adapter.knowledge_nodes()[0].node_id, "FULL_SOLUTION")
    with pytest.raises(NotFoundError):
        adapter.teaching_content("interview.node.unknown", "EXPLAIN")


def test_all_interview_items_are_covered_by_teaching_content(adapter: InterviewDomainAdapter) -> None:
    covered = set()
    for node in adapter.knowledge_nodes():
        covered.update(json.loads(adapter.teaching_content(node.node_id, "PRACTICE")))
    assert covered == {item.item_id for item in adapter.assessment_items()}


# ---------------------------------------------------------------------------
# Validation / registry
# ---------------------------------------------------------------------------


def test_validate_accepts_fixture_tree(adapter: InterviewDomainAdapter) -> None:
    assert adapter.validate() is None


def test_registry_registration_and_duplicates() -> None:
    registry = build_interview_registry(FIXTURES_ROOT)
    assert registry.list_domains() == [DOMAIN_ID]
    assert registry.get(DOMAIN_ID).domain_version == "0.1.0"
    assert isinstance(registry, DomainRegistry)
    with pytest.raises(ConflictError):
        registry.register(registry.get(DOMAIN_ID))
    with pytest.raises(NotFoundError):
        registry.get("unknown_domain")


def test_corrupt_teacher_visible_fixture_fails_closed(tmp_path: Path) -> None:
    root = tmp_path / "fixtures" / "m1_teacher"
    shutil.copytree(INTERVIEW_DIR, root / "vertical" / "interview")
    questions_path = root / "vertical" / "interview" / "questions.json"
    original = json.loads(questions_path.read_text(encoding="utf-8"))

    broken = json.loads(json.dumps(original))
    broken["schema_version"] = "m1a.v9"
    questions_path.write_text(json.dumps(broken), encoding="utf-8")
    with pytest.raises(ValidationError):
        InterviewDomainAdapter(root)

    broken = json.loads(json.dumps(original))
    broken["questions"][0]["rubric_points"] = {"factual_correctness": ["hidden"]}
    questions_path.write_text(json.dumps(broken), encoding="utf-8")
    with pytest.raises(ValidationError):
        InterviewDomainAdapter(root)

    broken = json.loads(json.dumps(original))
    broken["questions"][0]["follow_up_ladder"][2]["stage"] = "wrong_stage"
    questions_path.write_text(json.dumps(broken), encoding="utf-8")
    with pytest.raises(ValidationError):
        InterviewDomainAdapter(root)


# ---------------------------------------------------------------------------
# Hidden-scoring separation / offline guarantees
# ---------------------------------------------------------------------------


def test_adapter_never_reads_hidden_scoring_tree(tmp_path: Path) -> None:
    """A fixture tree without the hidden ``rubrics/`` tree must work identically."""

    root = tmp_path / "fixtures" / "m1_teacher"
    (root / "vertical" / "interview").mkdir(parents=True)
    shutil.copy2(INTERVIEW_DIR / "questions.json", root / "vertical" / "interview" / "questions.json")
    assert not (root / "vertical" / "interview" / "rubrics").exists()

    adapter = InterviewDomainAdapter(root)
    adapter.validate()
    reference = InterviewDomainAdapter(FIXTURES_ROOT)
    assert [item.to_dict() for item in adapter.assessment_items()] == [
        item.to_dict() for item in reference.assessment_items()
    ]
    assert interview_module._ALLOWED_FILES == frozenset({"questions.json"})

    # Teacher-visible serialisations never contain hidden scoring material.
    blobs = [
        json.dumps([node.to_dict() for node in adapter.knowledge_nodes()], ensure_ascii=False),
        json.dumps([item.to_dict() for item in adapter.assessment_items()], ensure_ascii=False),
        json.dumps([objective.to_dict() for objective in adapter.objectives()], ensure_ascii=False),
    ]
    for blob in blobs:
        _assert_no_hidden_tokens(blob, "teacher-visible adapter output")


def test_adapter_source_has_no_network_or_m0_imports() -> None:
    source = inspect.getsource(interview_module)
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    forbidden = {"httpx", "requests", "urllib", "socket", "aiohttp", "autoteacher_m0"}
    assert imported.isdisjoint(forbidden)
    assert "open(" not in source or "questions.json" in source


def test_default_fixtures_root_honours_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("M1_TEACHER_FIXTURES", str(tmp_path))
    assert default_fixtures_root() == tmp_path.resolve()
    monkeypatch.delenv("M1_TEACHER_FIXTURES")
    assert default_fixtures_root() == FIXTURES_ROOT.resolve()
