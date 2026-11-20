"""Domain-adapter / registry / hidden-material-isolation tests (B-PR1a).

Two layers:

* synthetic temporary fixture trees (always run): loader allow-list behaviour,
  strict fail-closed validation, registry semantics, optional
  ``domain_version`` forward-compatibility, teaching-content kinds, node
  filtering and proof that an adapter built from a tree without the hidden
  evaluation directory behaves identically;
* the real B-PR1b CF binary-search fixtures (run once they are present): frozen
  on-disk format, graph/objective/item/content consistency, byte-stable
  behaviour with and without the hidden directory, and positive evidence that
  no hidden scoring material reaches teacher-visible objects.

A static AST/text scan asserts the teacher-side packages never reference hidden
evaluation paths, network modules or the M0 package.
"""

from __future__ import annotations

import ast
import json
import shutil
from pathlib import Path
from typing import Any, Callable

import pytest

from m1_teacher.contracts import (
    AssessmentItem,
    ConflictError,
    DomainAdapter,
    DomainRegistry,
    KnowledgeNode,
    LearningObjective,
    NotFoundError,
    PrerequisiteEdge,
    ValidationError,
)
from m1_teacher.domains import (
    CFBinarySearchDomainAdapter,
    build_default_registry,
    default_fixtures_root,
)
from m1_teacher.knowledge import KnowledgeGraph

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = REPO_ROOT / "fixtures" / "m1_teacher"
DOMAIN_DIR = FIXTURES_DIR / "domains" / "cf_binary_search"
REAL_FIXTURES_AVAILABLE = (DOMAIN_DIR / "knowledge_graph.json").is_file()
real_fixtures = pytest.mark.skipif(
    not REAL_FIXTURES_AVAILABLE,
    reason="B-PR1b CF binary-search fixtures are not present yet",
)

EXPECTED_REAL_NODE_IDS = {
    "cf.array.basics",
    "cf.sort.sortedness",
    "cf.search.linear",
    "cf.search.binary",
    "cf.search.boundary",
    "cf.search.lower_upper",
    "cf.complexity.log",
    "cf.debug.edge_cases",
}
EXPECTED_REAL_EDGES = {
    ("cf.array.basics", "cf.sort.sortedness", "HARD"),
    ("cf.array.basics", "cf.search.linear", "HARD"),
    ("cf.sort.sortedness", "cf.search.binary", "HARD"),
    ("cf.search.linear", "cf.search.binary", "SOFT"),
    ("cf.search.binary", "cf.search.boundary", "HARD"),
    ("cf.search.binary", "cf.search.lower_upper", "HARD"),
    ("cf.search.binary", "cf.complexity.log", "SOFT"),
    ("cf.search.boundary", "cf.debug.edge_cases", "SOFT"),
    ("cf.sort.sortedness", "cf.search.lower_upper", "SOFT"),
}
REAL_MASTERY_OBJECTIVE = "obj.cf.binary_search.mastery"
TEACHING_TEMPLATE_KINDS = ("EXPLAIN", "HINT_L1", "HINT_L2", "HINT_L3", "REVIEW")
TEACHING_ALL_KINDS = TEACHING_TEMPLATE_KINDS + ("PRACTICE",)

# ---------------------------------------------------------------------------
# Synthetic fixture tree
# ---------------------------------------------------------------------------

HIDDEN_MARKERS = (
    "HIDDEN_EXPLANATION_MARKER_7f3a",
    "HIDDEN_EXPECTED_MARKER_91bc",
    "HIDDEN_RUBRIC_MARKER_c4d2",
)

SYNTH_NODES = [
    {
        "node_id": "cf.demo.array",
        "title": "数组基础",
        "description": "0-based 下标与合法范围",
        "difficulty": 1,
        "assessment_mode": "DETERMINISTIC_JUDGE",
        "tags": ["array"],
        "content_ref": "cf.demo.array",
    },
    {
        "node_id": "cf.demo.binary",
        "title": "二分查找",
        "description": "对数时间的查找",
        "difficulty": 3,
        "assessment_mode": "DETERMINISTIC_JUDGE",
        "tags": ["search"],
        "content_ref": "cf.demo.binary",
    },
    {
        "node_id": "cf.demo.boundary",
        "title": "边界处理",
        "description": "区间收缩与边界变体",
        "difficulty": 4,
        "assessment_mode": "RULE_RUBRIC",
        "tags": ["boundary"],
        "content_ref": "cf.demo.boundary",
    },
]

SYNTH_EDGES = [
    {"source_node_id": "cf.demo.array", "target_node_id": "cf.demo.binary", "kind": "HARD", "weight": 1.0},
    {"source_node_id": "cf.demo.binary", "target_node_id": "cf.demo.boundary", "kind": "HARD", "weight": 1.0},
]

SYNTH_ITEMS = [
    {
        "item_id": "item.demo.mcq.001",
        "node_ids": ["cf.demo.array"],
        "item_type": "MCQ",
        "difficulty": 1,
        "prompt": "长度为 n 的数组，最后一个元素的下标是什么？",
        "options": ["n-1", "n", "0", "-1"],
        "function_name": None,
        "max_score": 1.0,
        "deterministic": True,
        "scoring_spec_ref": "scoring/item.demo.mcq.001.json",
        "public": True,
    },
    {
        "item_id": "item.demo.code.001",
        "node_ids": ["cf.demo.binary"],
        "item_type": "CODE",
        "difficulty": 3,
        "prompt": "实现二分查找函数 binary_search_demo。",
        "options": None,
        "function_name": "binary_search_demo",
        "max_score": 1.0,
        "deterministic": True,
        "scoring_spec_ref": "scoring/item.demo.code.001.json",
        "public": True,
    },
    {
        "item_id": "item.demo.short.001",
        "node_ids": ["cf.demo.boundary"],
        "item_type": "SHORT_ANSWER",
        "difficulty": 4,
        "prompt": "解释二分查找的区间收缩为何一定能终止。",
        "options": None,
        "function_name": None,
        "max_score": 2.0,
        "deterministic": False,
        "scoring_spec_ref": "scoring/item.demo.short.001.json",
        "public": True,
    },
]

SYNTH_OBJECTIVE = {
    "objective_id": "obj.demo.binary_search",
    "title": "演示目标",
    "description": "演示二分查找目标",
    "target_node_ids": ["cf.demo.binary", "cf.demo.boundary"],
    "success_criteria": {
        "min_mastery": 0.7,
        "required_node_ids": ["cf.demo.binary"],
        "max_error_rate": 0.3,
    },
    "estimated_minutes": 60,
}

SYNTH_TEACHING_CONTENT = {
    "cf.demo.array": {
        "EXPLAIN": "数组用 0-based 下标，合法范围是 0 到 n-1。",
        "HINT_L1": "先想最后一个位置的下标。",
        "HINT_L2": "用 n=1 检验你的边界。",
        "HINT_L3": "最后一个元素下标比长度小 1。",
        "PRACTICE_ITEM_IDS": ["item.demo.mcq.001"],
        "REVIEW": "记住 0-based 下标范围。",
    },
    "cf.demo.binary": {
        "EXPLAIN": "二分查找每次把候选区间减半。",
        "HINT_L1": "比较中点与目标。",
        "HINT_L2": "决定保留左半还是右半。",
        "HINT_L3": "循环不变量是目标始终在区间内。",
        "PRACTICE_ITEM_IDS": ["item.demo.code.001"],
        "REVIEW": "二分查找要求输入有序。",
    },
    "cf.demo.boundary": {
        "EXPLAIN": "边界变体决定返回第一个或最后一个满足条件的位置。",
        "HINT_L1": "区分 lower_bound 与 upper_bound。",
        "HINT_L2": "用相等的元素验证返回值。",
        "HINT_L3": "每次循环区间长度至少减 1。",
        "PRACTICE_ITEM_IDS": ["item.demo.short.001"],
        "REVIEW": "边界处理决定结果正确性。",
    },
}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_fixture_tree(root: Path, *, with_hidden: bool = True) -> Path:
    """Create a minimal but contract-complete synthetic fixture tree at ``root``."""

    domain = root / "domains" / "cf_binary_search"
    domain.mkdir(parents=True, exist_ok=True)
    _write_json(
        domain / "knowledge_graph.json",
        {
            "schema_version": "m1a.v0",
            "domain_id": "cf_binary_search",
            "domain_version": "0.1.0",
            "nodes": SYNTH_NODES,
            "edges": SYNTH_EDGES,
        },
    )
    _write_json(
        domain / "objectives.json",
        {"schema_version": "m1a.v0", "domain_id": "cf_binary_search", "objectives": [SYNTH_OBJECTIVE]},
    )
    _write_json(
        domain / "assessment_items.json",
        {"schema_version": "m1a.v0", "domain_id": "cf_binary_search", "items": SYNTH_ITEMS},
    )
    _write_json(
        domain / "teaching_content.json",
        {
            "schema_version": "m1a.v0",
            "domain_id": "cf_binary_search",
            "nodes": SYNTH_TEACHING_CONTENT,
        },
    )
    if with_hidden:
        scoring = domain / "scoring"
        scoring.mkdir(exist_ok=True)
        _write_json(
            scoring / "item.demo.mcq.001.json",
            {"kind": "MCQ", "correct_option_index": 0, "explanation": HIDDEN_MARKERS[0]},
        )
        _write_json(
            scoring / "item.demo.code.001.json",
            {
                "kind": "PYTHON_FUNCTION",
                "function_name": "binary_search_demo",
                "tests": [{"args": [[1, 2, 3], 2], "expected": HIDDEN_MARKERS[1]}],
                "timeout_s": 2,
            },
        )
        _write_json(
            scoring / "item.demo.short.001.json",
            {
                "kind": "SEMANTIC_RUBRIC",
                "required_concept_groups": [[HIDDEN_MARKERS[2]]],
                "allow_correct": False,
                "on_insufficient": "NEEDS_REVIEW",
            },
        )
        # A poison file that is NOT allow-listed must never be read.
        _write_json(domain / "unexpected_answers.json", {"marker": "POISON_FILE_MARKER_f00d"})
    return root


def _domain_dir(root: Path) -> Path:
    return root / "domains" / "cf_binary_search"


def _stable_records(records: list[Any]) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for record in records:
        payload = record.to_dict()
        payload.pop("created_at", None)
        payloads.append(payload)
    return payloads


def adapter_snapshot(adapter: DomainAdapter) -> dict[str, Any]:
    """Deterministic view of everything the teacher-visible adapter exposes."""

    node_ids = [node.node_id for node in adapter.knowledge_nodes()]
    return {
        "domain_id": adapter.domain_id,
        "domain_version": adapter.domain_version,
        "knowledge_nodes": _stable_records(adapter.knowledge_nodes()),
        "prerequisite_edges": _stable_records(adapter.prerequisite_edges()),
        "objectives": _stable_records(adapter.objectives()),
        "assessment_items": _stable_records(adapter.assessment_items()),
        "teaching_content": {
            node_id: {
                kind: adapter.teaching_content(node_id, kind) for kind in TEACHING_ALL_KINDS
            }
            for node_id in node_ids
        },
    }


def _copy_without_hidden_directory(source_domain: Path, dest_root: Path) -> Path:
    dest_domain = dest_root / "domains" / "cf_binary_search"
    shutil.copytree(
        source_domain,
        dest_domain,
        ignore=shutil.ignore_patterns("scoring", "unexpected_answers.json"),
    )
    return dest_root


def _load_and_validate(root: Path) -> CFBinarySearchDomainAdapter:
    adapter = CFBinarySearchDomainAdapter(root)
    adapter.validate()
    return adapter


# ---------------------------------------------------------------------------
# Synthetic loader / API behaviour
# ---------------------------------------------------------------------------


def test_synthetic_adapter_loads_and_validates(tmp_path: Path) -> None:
    root = build_fixture_tree(tmp_path / "fixtures")
    adapter = _load_and_validate(root)

    assert isinstance(adapter, DomainAdapter)
    assert adapter.domain_id == "cf_binary_search"
    assert adapter.domain_version == "0.1.0"
    assert [node.node_id for node in adapter.knowledge_nodes()] == [
        "cf.demo.array",
        "cf.demo.binary",
        "cf.demo.boundary",
    ]
    assert {(edge.source_node_id, edge.target_node_id, edge.kind) for edge in adapter.prerequisite_edges()} == {
        ("cf.demo.array", "cf.demo.binary", "HARD"),
        ("cf.demo.binary", "cf.demo.boundary", "HARD"),
    }
    assert [objective.objective_id for objective in adapter.objectives()] == [
        "obj.demo.binary_search"
    ]
    assert {item.item_id for item in adapter.assessment_items()} == {
        "item.demo.mcq.001",
        "item.demo.code.001",
        "item.demo.short.001",
    }
    for node, edge, objective, item in (
        (adapter.knowledge_nodes()[0], adapter.prerequisite_edges()[0], adapter.objectives()[0], adapter.assessment_items()[0]),
    ):
        assert isinstance(node, KnowledgeNode)
        assert isinstance(edge, PrerequisiteEdge)
        assert isinstance(objective, LearningObjective)
        assert isinstance(item, AssessmentItem)

    # The teacher API is graph-consistent.
    graph = KnowledgeGraph(adapter.knowledge_nodes(), adapter.prerequisite_edges())
    assert graph.topological_order() == ["cf.demo.array", "cf.demo.binary", "cf.demo.boundary"]
    graph.validate_objective(adapter.objectives()[0])


def test_loader_accepts_domain_directory_and_str_paths(tmp_path: Path) -> None:
    root = build_fixture_tree(tmp_path / "fixtures")
    from_root = CFBinarySearchDomainAdapter(str(root))
    from_domain = CFBinarySearchDomainAdapter(_domain_dir(root))
    assert adapter_snapshot(from_root) == adapter_snapshot(from_domain)


def test_options_null_is_normalised_to_empty_list(tmp_path: Path) -> None:
    root = build_fixture_tree(tmp_path / "fixtures")
    adapter = _load_and_validate(root)
    by_id = {item.item_id: item for item in adapter.assessment_items()}
    assert by_id["item.demo.mcq.001"].options == ["n-1", "n", "0", "-1"]
    assert by_id["item.demo.code.001"].options == []
    assert by_id["item.demo.short.001"].options == []
    assert by_id["item.demo.code.001"].function_name == "binary_search_demo"
    assert by_id["item.demo.short.001"].deterministic is False


def test_assessment_items_filtering_by_node(tmp_path: Path) -> None:
    adapter = _load_and_validate(build_fixture_tree(tmp_path / "fixtures"))

    filtered = adapter.assessment_items(node_id="cf.demo.binary")
    assert [item.item_id for item in filtered] == ["item.demo.code.001"]
    for item in filtered:
        assert "cf.demo.binary" in item.node_ids

    assert adapter.assessment_items(node_id="cf.demo.array")[0].item_id == "item.demo.mcq.001"
    assert adapter.assessment_items() == adapter.assessment_items(node_id=None)

    with pytest.raises(NotFoundError):
        adapter.assessment_items(node_id="cf.demo.unknown")
    with pytest.raises(ValidationError):
        adapter.assessment_items(node_id="")


def test_teaching_content_all_kinds_and_fail_closed(tmp_path: Path) -> None:
    adapter = _load_and_validate(build_fixture_tree(tmp_path / "fixtures"))

    for node in adapter.knowledge_nodes():
        for kind in TEACHING_TEMPLATE_KINDS:
            content = adapter.teaching_content(node.node_id, kind)
            assert isinstance(content, str)
            assert content.strip(), f"{node.node_id}/{kind} must not be blank"
    assert adapter.teaching_content("cf.demo.array", "PRACTICE") == json.dumps(
        ["item.demo.mcq.001"]
    )

    with pytest.raises(ValidationError, match="unsupported kind"):
        adapter.teaching_content("cf.demo.array", "FULL_SOLUTION")
    with pytest.raises(ValidationError):
        adapter.teaching_content("cf.demo.array", 42)  # type: ignore[arg-type]
    with pytest.raises(NotFoundError):
        adapter.teaching_content("cf.unknown.node", "EXPLAIN")


def test_teacher_visible_objects_have_no_hidden_material(tmp_path: Path) -> None:
    root = build_fixture_tree(tmp_path / "fixtures")
    adapter = _load_and_validate(root)

    snapshot = adapter_snapshot(adapter)
    serialised = json.dumps(snapshot, ensure_ascii=False)
    for marker in HIDDEN_MARKERS:
        assert marker not in serialised
    assert "POISON_FILE_MARKER_f00d" not in serialised
    assert "correct_option_index" not in serialised

    for item_payload in snapshot["assessment_items"]:
        lowered = {key.lower() for key in item_payload}
        for token in ("answer", "expected", "correct", "solution"):
            assert not any(token in key for key in lowered)


def test_adapter_works_from_tree_without_hidden_material(tmp_path: Path) -> None:
    root = build_fixture_tree(tmp_path / "fixtures")
    full = _load_and_validate(root)
    stripped_root = _copy_without_hidden_directory(_domain_dir(root), tmp_path / "stripped")
    stripped = _load_and_validate(stripped_root)
    assert adapter_snapshot(full) == adapter_snapshot(stripped)


def test_two_constructions_are_deterministic(tmp_path: Path) -> None:
    root = build_fixture_tree(tmp_path / "fixtures")
    first = _load_and_validate(root)
    second = _load_and_validate(root)
    assert adapter_snapshot(first) == adapter_snapshot(second)


def test_forward_compatible_optional_domain_version(tmp_path: Path) -> None:
    root = build_fixture_tree(tmp_path / "fixtures")
    objectives_path = _domain_dir(root) / "objectives.json"
    payload = _read_json(objectives_path)
    payload["domain_version"] = "0.1.0"
    _write_json(objectives_path, payload)
    _load_and_validate(root)  # matching version tolerated

    payload["domain_version"] = "9.9.9"
    _write_json(objectives_path, payload)
    with pytest.raises(ValidationError, match="domain_version"):
        _load_and_validate(root)


# ---------------------------------------------------------------------------
# Fail-closed fixture validation
# ---------------------------------------------------------------------------


def _mutate_objectives(payload: dict[str, Any]) -> dict[str, Any]:
    payload["objectives"][0]["success_criteria"]["min_mastery"] = 2.0
    return payload


def _mutate_items_unknown_key(payload: dict[str, Any]) -> dict[str, Any]:
    payload["items"][0]["answer"] = "n-1"
    return payload


def _mutate_items_unknown_node(payload: dict[str, Any]) -> dict[str, Any]:
    payload["items"][0]["node_ids"] = ["cf.demo.unknown"]
    return payload


def _mutate_items_mcq_options(payload: dict[str, Any]) -> dict[str, Any]:
    payload["items"][0]["options"] = ["only-one"]
    return payload


def _mutate_items_code_function(payload: dict[str, Any]) -> dict[str, Any]:
    payload["items"][1]["function_name"] = None
    return payload


def _mutate_teaching_missing_node(payload: dict[str, Any]) -> dict[str, Any]:
    del payload["nodes"]["cf.demo.boundary"]
    return payload


def _mutate_teaching_bad_template(payload: dict[str, Any]) -> dict[str, Any]:
    payload["nodes"]["cf.demo.array"]["EXPLAIN"] = ""
    return payload


def _mutate_graph_unknown_key(payload: dict[str, Any]) -> dict[str, Any]:
    payload["nodes"][0]["unexpected"] = True
    return payload


def _mutate_graph_cycle(payload: dict[str, Any]) -> dict[str, Any]:
    payload["edges"].append(
        {"source_node_id": "cf.demo.boundary", "target_node_id": "cf.demo.array", "kind": "HARD", "weight": 1.0}
    )
    return payload


def _mutate_graph_bad_difficulty(payload: dict[str, Any]) -> dict[str, Any]:
    payload["nodes"][0]["difficulty"] = 6
    return payload


def _delete_file(domain: Path, filename: str) -> None:
    (domain / filename).unlink()


def _write_bad_json(domain: Path, filename: str) -> None:
    (domain / filename).write_text("{not valid json", encoding="utf-8")


INVALID_FIXTURE_CASES: list[tuple[str, Callable[[Path], None], type[Exception]]] = [
    (
        "bad schema_version",
        lambda domain: _write_json(
            domain / "knowledge_graph.json",
            {**_read_json(domain / "knowledge_graph.json"), "schema_version": "m1a.v999"},
        ),
        ValidationError,
    ),
    (
        "domain id mismatch",
        lambda domain: _write_json(
            domain / "knowledge_graph.json",
            {**_read_json(domain / "knowledge_graph.json"), "domain_id": "other.domain"},
        ),
        ValidationError,
    ),
    (
        "graph unknown node key",
        lambda domain: _write_json(
            domain / "knowledge_graph.json",
            _mutate_graph_unknown_key(_read_json(domain / "knowledge_graph.json")),
        ),
        ValidationError,
    ),
    (
        "graph cycle",
        lambda domain: _write_json(
            domain / "knowledge_graph.json",
            _mutate_graph_cycle(_read_json(domain / "knowledge_graph.json")),
        ),
        ValidationError,
    ),
    (
        "graph bad difficulty",
        lambda domain: _write_json(
            domain / "knowledge_graph.json",
            _mutate_graph_bad_difficulty(_read_json(domain / "knowledge_graph.json")),
        ),
        ValidationError,
    ),
    (
        "objectives bad criteria range",
        lambda domain: _write_json(
            domain / "objectives.json",
            _mutate_objectives(_read_json(domain / "objectives.json")),
        ),
        ValidationError,
    ),
    (
        "objectives unknown top-level key",
        lambda domain: _write_json(
            domain / "objectives.json",
            {**_read_json(domain / "objectives.json"), "unexpected": 1},
        ),
        ValidationError,
    ),
    (
        "item answer key smuggled into fixture",
        lambda domain: _write_json(
            domain / "assessment_items.json",
            _mutate_items_unknown_key(_read_json(domain / "assessment_items.json")),
        ),
        ValidationError,
    ),
    (
        "item unknown node id",
        lambda domain: _write_json(
            domain / "assessment_items.json",
            _mutate_items_unknown_node(_read_json(domain / "assessment_items.json")),
        ),
        ValidationError,
    ),
    (
        "mcq with one option",
        lambda domain: _write_json(
            domain / "assessment_items.json",
            _mutate_items_mcq_options(_read_json(domain / "assessment_items.json")),
        ),
        ValidationError,
    ),
    (
        "code item without function name",
        lambda domain: _write_json(
            domain / "assessment_items.json",
            _mutate_items_code_function(_read_json(domain / "assessment_items.json")),
        ),
        ValidationError,
    ),
    (
        "teaching content missing node",
        lambda domain: _write_json(
            domain / "teaching_content.json",
            _mutate_teaching_missing_node(_read_json(domain / "teaching_content.json")),
        ),
        ValidationError,
    ),
    (
        "teaching content blank template",
        lambda domain: _write_json(
            domain / "teaching_content.json",
            _mutate_teaching_bad_template(_read_json(domain / "teaching_content.json")),
        ),
        ValidationError,
    ),
    (
        "missing required file",
        lambda domain: _delete_file(domain, "objectives.json"),
        NotFoundError,
    ),
    (
        "malformed json file",
        lambda domain: _write_bad_json(domain, "assessment_items.json"),
        ValidationError,
    ),
]


@pytest.mark.parametrize(
    ("mutation", "expected_error"),
    [(case[1], case[2]) for case in INVALID_FIXTURE_CASES],
    ids=[case[0] for case in INVALID_FIXTURE_CASES],
)
def test_invalid_fixture_trees_fail_closed(
    tmp_path: Path, mutation: Callable[[Path], None], expected_error: type[Exception]
) -> None:
    root = build_fixture_tree(tmp_path / "fixtures")
    mutation(_domain_dir(root))
    with pytest.raises(expected_error):
        _load_and_validate(root)


def test_invalid_fixtures_root_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(NotFoundError):
        CFBinarySearchDomainAdapter(tmp_path / "does" / "not" / "exist")
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(NotFoundError):
        CFBinarySearchDomainAdapter(empty)
    with pytest.raises(ValidationError):
        CFBinarySearchDomainAdapter(42)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_registry_register_get_list(tmp_path: Path) -> None:
    adapter = _load_and_validate(build_fixture_tree(tmp_path / "fixtures"))
    registry = DomainRegistry()

    registry.register(adapter)
    assert registry.list_domains() == ["cf_binary_search"]
    assert registry.get("cf_binary_search") is adapter
    assert "cf_binary_search" in registry
    assert len(registry) == 1

    with pytest.raises(ConflictError):
        registry.register(_load_and_validate(build_fixture_tree(tmp_path / "fixtures2")))
    with pytest.raises(NotFoundError):
        registry.get("cf.other.domain")
    with pytest.raises(ValidationError):
        registry.get("")
    with pytest.raises(ValidationError):
        registry.register(object())  # type: ignore[arg-type]


def test_build_default_registry_from_explicit_root(tmp_path: Path) -> None:
    root = build_fixture_tree(tmp_path / "fixtures")
    registry = build_default_registry(root)
    assert registry.list_domains() == ["cf_binary_search"]
    adapter = registry.get("cf_binary_search")
    assert isinstance(adapter.domain_version, str)
    assert len(adapter.knowledge_nodes()) == 3


def test_build_default_registry_honours_env_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = build_fixture_tree(tmp_path / "fixtures")
    monkeypatch.setenv("M1_TEACHER_FIXTURES", str(root))
    assert default_fixtures_root() == root.resolve()
    registry = build_default_registry()
    assert registry.list_domains() == ["cf_binary_search"]


def test_default_fixtures_root_is_repo_fixtures(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("M1_TEACHER_FIXTURES", raising=False)
    assert default_fixtures_root() == (REPO_ROOT / "fixtures" / "m1_teacher").resolve()


def test_domain_adapter_has_no_scoring_capability(tmp_path: Path) -> None:
    adapter = _load_and_validate(build_fixture_tree(tmp_path / "fixtures"))
    for name in dir(adapter):
        lowered = name.lower()
        assert "scor" not in lowered, f"unexpected scoring capability {name!r}"
        assert "answer" not in lowered, f"unexpected answer capability {name!r}"
    protocol_methods = {
        name for name in dir(DomainAdapter) if not name.startswith("_")
    }
    assert not any("scor" in name.lower() or "answer" in name.lower() for name in protocol_methods)


# ---------------------------------------------------------------------------
# Static isolation scan of the teacher-side source
# ---------------------------------------------------------------------------

_SCAN_DIRS = (
    REPO_ROOT / "m1_teacher" / "domains",
    REPO_ROOT / "m1_teacher" / "knowledge",
    REPO_ROOT / "m1_teacher" / "contracts",
)
_FORBIDDEN_NETWORK_ROOTS = {
    "socket",
    "ssl",
    "urllib",
    "urllib3",
    "http",
    "requests",
    "httpx",
    "aiohttp",
    "websocket",
    "websockets",
    "openai",
    "anthropic",
    "deepseek",
    "boto3",
    "google",
    "azure",
}


def _teacher_source_files() -> list[Path]:
    files: list[Path] = []
    for directory in _SCAN_DIRS:
        files.extend(
            path
            for path in directory.rglob("*.py")
            if "__pycache__" not in path.parts
        )
    return sorted(files)


def test_teacher_source_has_no_hidden_scoring_path_references() -> None:
    assert _teacher_source_files(), "expected teacher source files to scan"
    for path in _teacher_source_files():
        text = path.read_text(encoding="utf-8")
        assert "scoring/" not in text, f"{path} references hidden evaluation paths"
        assert "autoteacher_m0" not in text, f"{path} references the M0 package"


def test_teacher_source_has_no_network_or_m0_imports() -> None:
    for path in _teacher_source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            imported: list[str] = []
            if isinstance(node, ast.Import):
                imported = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                imported = [node.module or ""]
            for module in imported:
                root = module.split(".")[0]
                assert root != "autoteacher_m0", f"{path} imports M0"
                assert root not in _FORBIDDEN_NETWORK_ROOTS, (
                    f"{path} imports network/provider module {module!r}"
                )


# ---------------------------------------------------------------------------
# Real B-PR1b fixtures (integration)
# ---------------------------------------------------------------------------


@real_fixtures
def test_real_fixtures_on_disk_format_is_frozen() -> None:
    assert DOMAIN_DIR.is_dir()
    graph = _read_json(DOMAIN_DIR / "knowledge_graph.json")
    assert set(graph) == {"schema_version", "domain_id", "domain_version", "nodes", "edges"}
    assert graph["schema_version"] == "m1a.v0"
    assert graph["domain_id"] == "cf_binary_search"
    assert graph["domain_version"] == "0.1.0"
    for filename, payload_key in (
        ("objectives.json", "objectives"),
        ("assessment_items.json", "items"),
        ("teaching_content.json", "nodes"),
    ):
        payload = _read_json(DOMAIN_DIR / filename)
        assert set(payload) == {"schema_version", "domain_id", payload_key}, filename
        assert payload["schema_version"] == "m1a.v0"
        assert payload["domain_id"] == "cf_binary_search"


@real_fixtures
def test_real_fixture_adapter_contract() -> None:
    adapter = _load_and_validate(FIXTURES_DIR)

    assert adapter.domain_id == "cf_binary_search"
    assert adapter.domain_version == "0.1.0"
    assert {node.node_id for node in adapter.knowledge_nodes()} == EXPECTED_REAL_NODE_IDS
    assert {(edge.source_node_id, edge.target_node_id, edge.kind) for edge in adapter.prerequisite_edges()} == EXPECTED_REAL_EDGES

    graph = KnowledgeGraph(adapter.knowledge_nodes(), adapter.prerequisite_edges())
    order = graph.topological_order()
    position = {node_id: index for index, node_id in enumerate(order)}
    for source, target, _kind in EXPECTED_REAL_EDGES:
        assert position[source] < position[target]
    assert graph.prerequisite_closure(["cf.search.binary"]) == {
        "cf.array.basics",
        "cf.sort.sortedness",
        "cf.search.linear",
    }

    objectives = adapter.objectives()
    assert [objective.objective_id for objective in objectives] == [REAL_MASTERY_OBJECTIVE]
    objective = objectives[0]
    assert set(objective.target_node_ids) == {
        "cf.search.binary",
        "cf.search.boundary",
        "cf.search.lower_upper",
        "cf.complexity.log",
    }
    assert set(objective.success_criteria["required_node_ids"]) == {
        "cf.search.binary",
        "cf.search.boundary",
    }
    graph.validate_objective(objective)

    items = adapter.assessment_items()
    assert len(items) >= 12
    assert len({item.item_id for item in items}) == len(items)
    item_types = {item.item_type for item in items}
    assert item_types == {"MCQ", "CODE", "SHORT_ANSWER"}
    for item in items:
        assert item.node_ids
        assert all(node_id in EXPECTED_REAL_NODE_IDS for node_id in item.node_ids)
        if item.item_type == "MCQ":
            assert len(item.options) >= 2
        if item.item_type == "CODE":
            assert item.function_name
        if item.item_type == "SHORT_ANSWER":
            assert item.deterministic is False

    for node_id in EXPECTED_REAL_NODE_IDS:
        for kind in TEACHING_TEMPLATE_KINDS:
            assert adapter.teaching_content(node_id, kind).strip()
        practice_ids = json.loads(adapter.teaching_content(node_id, "PRACTICE"))
        assert isinstance(practice_ids, list)


@real_fixtures
def test_real_fixture_items_match_public_fixture_documents() -> None:
    adapter = _load_and_validate(FIXTURES_DIR)
    raw_items = _read_json(DOMAIN_DIR / "assessment_items.json")["items"]
    adapter_items = {item.item_id: item for item in adapter.assessment_items()}
    assert set(adapter_items) == {raw["item_id"] for raw in raw_items}
    for raw in raw_items:
        item = adapter_items[raw["item_id"]]
        assert item.node_ids == raw["node_ids"]
        assert item.item_type == raw["item_type"]
        assert item.prompt == raw["prompt"]
        assert item.difficulty == raw["difficulty"]
        assert item.options == (raw.get("options") or [])
        assert item.function_name == raw.get("function_name")
        assert item.max_score == float(raw.get("max_score", 1.0))
        assert item.deterministic == raw.get("deterministic", True)
        assert item.scoring_spec_ref == raw.get("scoring_spec_ref", "")


@real_fixtures
def test_real_fixtures_behave_identically_without_hidden_directory(tmp_path: Path) -> None:
    full = _load_and_validate(FIXTURES_DIR)
    stripped_root = _copy_without_hidden_directory(DOMAIN_DIR, tmp_path / "stripped")
    assert not any(
        path.name == "scoring"
        for path in (stripped_root / "domains" / "cf_binary_search").iterdir()
    )
    stripped = _load_and_validate(stripped_root)
    assert adapter_snapshot(full) == adapter_snapshot(stripped)


@real_fixtures
def test_real_fixtures_do_not_leak_hidden_scoring_content() -> None:
    adapter = _load_and_validate(FIXTURES_DIR)
    scoring_dir = DOMAIN_DIR / "scoring"
    assert scoring_dir.is_dir()
    items = {item.item_id: item for item in adapter.assessment_items()}
    serialised_items = {
        item_id: json.dumps(item.to_dict(), ensure_ascii=False)
        for item_id, item in items.items()
    }

    for spec_path in sorted(scoring_dir.glob("*.json")):
        spec = _read_json(spec_path)
        item_id = spec_path.stem
        assert item_id in items, f"hidden spec without public item: {spec_path.name}"
        payload = serialised_items[item_id]
        kind = spec.get("kind")

        if kind == "MCQ":
            # The correct option index is hidden-only material.
            assert "correct_option_index" not in payload
            correct_index = spec.get("correct_option_index")
            assert type(correct_index) is int
            explanation = spec.get("explanation")
            if isinstance(explanation, str) and explanation.strip():
                assert explanation not in payload
        elif kind == "PYTHON_FUNCTION":
            assert "timeout_s" not in payload
            for test_case in spec.get("tests", []):
                assert json.dumps(test_case, ensure_ascii=False) not in payload
                expected = test_case.get("expected")
                if isinstance(expected, str) and len(expected) >= 3:
                    assert expected not in payload
        elif kind == "SEMANTIC_RUBRIC":
            for group in spec.get("required_concept_groups", []):
                assert json.dumps(group, ensure_ascii=False) not in payload
            assert spec.get("on_insufficient") not in payload
        else:  # pragma: no cover - fixture drift guard
            pytest.fail(f"unexpected scoring spec kind {kind!r} in {spec_path.name}")


@real_fixtures
def test_real_fixture_registry_end_to_end(tmp_path: Path) -> None:
    registry = build_default_registry(FIXTURES_DIR)
    assert registry.list_domains() == ["cf_binary_search"]
    adapter = registry.get("cf_binary_search")
    assert len(adapter.assessment_items()) >= 12
    assert isinstance(adapter, DomainAdapter)
