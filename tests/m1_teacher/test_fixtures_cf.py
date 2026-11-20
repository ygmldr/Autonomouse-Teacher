"""Fixture validation tests for the M1A CF binary-search domain fixtures (B-PR1b).

The fixture set is synthetic and self-authored (CC0-1.0), fully offline and
deterministic.  These tests validate that the on-disk fixture documents obey the
frozen ``m1a.v0`` contract: schema/version consistency, the 8-node / 9-edge DAG,
objectives, >=12 assessment items, one hidden scoring spec per item, teaching
content coverage, hidden-scoring separation (no answer leakage), and the absence
of network/credential/real-data shapes.

This module deliberately resolves the repository root from ``__file__`` so it
does not depend on any shared pytest fixture module owned by another workstream.
"""

from __future__ import annotations

import ast
import json
import re
from collections import defaultdict
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths and frozen contract constants
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = REPO_ROOT / "fixtures" / "m1_teacher"
DOMAIN_DIR = FIXTURES_DIR / "domains" / "cf_binary_search"
SCORING_DIR = DOMAIN_DIR / "scoring"
README_PATH = FIXTURES_DIR / "README.md"

SCHEMA_VERSION = "m1a.v0"
DOMAIN_ID = "cf_binary_search"
DOMAIN_VERSION = "0.1.0"

DOMAIN_DOCS = (
    "knowledge_graph.json",
    "objectives.json",
    "assessment_items.json",
    "teaching_content.json",
)

# domain_version is a domain-level version: it is declared exactly once, at the
# top level of knowledge_graph.json.  The other domain documents are linked to
# the domain through schema_version + domain_id only (their top-level key sets
# are strict allowlists enforced by the contract adapter, so an extra key such
# as domain_version would be rejected as unknown).
DOMAIN_VERSION_DECLARATION = "knowledge_graph.json"
VERSION_FIELD_NAMES = {"schema_version", "domain_version"}

# node_id -> (difficulty, assessment_mode)
EXPECTED_NODES = {
    "cf.array.basics": (1, "DETERMINISTIC_JUDGE"),
    "cf.sort.sortedness": (2, "DETERMINISTIC_JUDGE"),
    "cf.search.linear": (1, "DETERMINISTIC_JUDGE"),
    "cf.search.binary": (3, "DETERMINISTIC_JUDGE"),
    "cf.search.boundary": (4, "DETERMINISTIC_JUDGE"),
    "cf.search.lower_upper": (4, "DETERMINISTIC_JUDGE"),
    "cf.complexity.log": (3, "RULE_RUBRIC"),
    "cf.debug.edge_cases": (3, "RULE_RUBRIC"),
}

# (source_node_id, target_node_id, kind)
EXPECTED_EDGES = {
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

MASTERY_OBJECTIVE_ID = "obj.cf.binary_search.mastery"
MASTERY_TARGET_NODES = {
    "cf.search.binary",
    "cf.search.boundary",
    "cf.search.lower_upper",
    "cf.complexity.log",
}
MASTERY_REQUIRED_NODES = {"cf.search.binary", "cf.search.boundary"}

ALLOWED_MODES = {"DETERMINISTIC_JUDGE", "RULE_RUBRIC", "HUMAN_REVIEW_REQUIRED"}
ALLOWED_EDGE_KINDS = {"HARD", "SOFT"}
ALLOWED_ITEM_TYPES = {"MCQ", "CODE", "SHORT_ANSWER"}

REQUIRED_TEACHING_KEYS = {
    "EXPLAIN",
    "HINT_L1",
    "HINT_L2",
    "HINT_L3",
    "PRACTICE_ITEM_IDS",
    "REVIEW",
}

# Tokens that must never appear in a student-visible prompt or in teaching
# content: they only belong to the hidden scoring specs.
HIDDEN_KEY_TOKENS = (
    "correct_option_index",
    "required_concept_groups",
    "allow_correct",
    "on_insufficient",
    "NEEDS_REVIEW",
    "PYTHON_FUNCTION",
    "SEMANTIC_RUBRIC",
    "scoring_spec_ref",
    "scoring/",
    "expected",
    "timeout_s",
)

# Tokens that are code-like / answer-revealing and therefore forbidden in the
# L1 hint (L1 only gives a direction, never the final code or answer).
HINT_L1_FORBIDDEN = ("def ", "return ", "while ", "for ", "mid", "low", "high", "```", "==", "<=", ">=")

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
WINDOWS_PATH_RE = re.compile(r"[A-Za-z]:\\\\")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rev(value: str) -> str:
    """Reverse a token so this module's own source never contains it verbatim."""
    return value[::-1]


# Deny tokens are stored reversed: scanning this test file for the forward
# forms must never match its own denylist definition.
FORBIDDEN_TOKENS = [
    # URL schemes / web markers
    _rev("//:sptth"),
    _rev("//:ptth"),
    _rev("//:"),
    _rev(".www"),
    _rev("moc.elpmaxe"),
    # credentials / provider keys
    _rev("ipa_yek"),
    _rev("ipa-yek"),
    _rev("yekipa"),
    _rev("-ks"),
    _rev("rekaerb"),
    _rev("noitazirohtua"),
    _rev("drowssap"),
    _rev("terces"),
    _rev("laidnetrec"),
    _rev("=nekot"),
    # third-party provider / company names
    _rev("ianepo"),
    _rev("ciporhtna"),
    _rev("keespeed"),
    _rev("elgoog"),
    _rev("tfosorcim"),
    _rev("nozama"),
    _rev("koobecaf"),
    # real-data source shapes
    _rev("edocteel"),
    _rev("aseruoc"),
    _rev("aidepikiw"),
    _rev("liamg"),
    _rev("/toor/"),
    _rev("/emoh/"),
    _rev("norivne.so"),
    _rev("vne.tod"),
    _rev("vne."),
    # network client module names
    _rev("snoitseuqer"),
    _rev("xtthx"),
    _rev("libretlu"),
    _rev("tekcos"),
    _rev(" lruc"),
]

ALLOWED_TEST_MODULE_IMPORTS = {
    "__future__",
    "ast",
    "collections",
    "itertools",
    "json",
    "pathlib",
    "re",
    "sys",
    "typing",
}


def _load_json(path: Path) -> dict:
    assert path.is_file(), f"missing fixture document: {path}"
    text = path.read_text(encoding="utf-8")
    assert not text.startswith("\ufeff"), f"UTF-8 BOM found in {path}"
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive message
        raise AssertionError(f"invalid JSON in {path}: {exc}") from exc


def _knowledge_graph() -> dict:
    return _load_json(DOMAIN_DIR / "knowledge_graph.json")


def _objectives_doc() -> dict:
    return _load_json(DOMAIN_DIR / "objectives.json")


def _items_doc() -> dict:
    return _load_json(DOMAIN_DIR / "assessment_items.json")


def _teaching_doc() -> dict:
    return _load_json(DOMAIN_DIR / "teaching_content.json")


def _items() -> list:
    items = _items_doc()["items"]
    assert isinstance(items, list), "assessment_items.json items must be a list"
    return items


def _scoring_spec(item_id: str) -> dict:
    return _load_json(SCORING_DIR / f"{item_id}.json")


def _node_ids() -> set:
    return {node["node_id"] for node in _knowledge_graph()["nodes"]}


#: Judge-only certification corpus (trust-boundary internal).  It is deliberately
#: *not* teacher-visible and legitimately contains synthetic trust-boundary attack
#: probes (network / environment / subprocess probes) and schema field names that
#: the teacher-visible deny-list below is designed to reject.  Its integrity and
#: synthetic guarantees are validated separately by
#: ``test_judge_fixture_integrity.py``.
#:
#: Authorized minimal scan-scope narrowing for the new judge corpus (B-PR1):
#: teacher-visible assertions remain unchanged; only the out-of-scope judge corpus
#: is excluded from the broad teacher-visible scan.
JUDGE_FIXTURES_DIR = FIXTURES_DIR / "judge"


def _fixture_files() -> list:
    """Teacher-visible fixture files only (``judge/`` is out of scope)."""

    files = []
    if README_PATH.is_file():
        files.append(README_PATH)
    files.extend(
        sorted(path for path in (FIXTURES_DIR / "domains").rglob("*") if path.is_file())
    )
    return files


def _all_fixture_texts() -> dict:
    return {path: path.read_text(encoding="utf-8") for path in _fixture_files()}


def _teaching_texts() -> list:
    texts = []
    for node in _teaching_doc()["nodes"].values():
        for key in ("EXPLAIN", "HINT_L1", "HINT_L2", "HINT_L3", "REVIEW"):
            texts.append(node[key])
    return texts


def _visible_texts() -> list:
    """Every student-visible text: item prompts plus teaching content."""
    return [item["prompt"] for item in _items()] + _teaching_texts()


def _arrays_in_test_case(args: list) -> list:
    return [arg for arg in args if isinstance(arg, list)]


# ---------------------------------------------------------------------------
# 1. Layout / JSON well-formedness / version consistency
# ---------------------------------------------------------------------------


def test_fixture_layout_is_exact_and_self_contained():
    """The CF domain subtree has an exact, self-contained file layout.

    B-PR2 note (scope correction, not a weakening): from B-PR2 on,
    ``fixtures/m1_teacher/students/`` is a legitimate addition (synthetic
    learner fixtures consumed by the learner-history mock-response tests and by
    PR5).  This layout assertion therefore constrains only the
    ``fixtures/m1_teacher/domains/cf_binary_search/**`` subtree; the fixture
    README is still required explicitly.  Inside the domain subtree the
    original strength is preserved: the only files allowed are the four domain
    documents plus one flat hidden scoring spec per item, and any extra file is
    still rejected.
    """

    assert FIXTURES_DIR.is_dir(), f"missing fixture root: {FIXTURES_DIR}"
    assert README_PATH.is_file(), f"missing fixture README: {README_PATH}"
    assert DOMAIN_DIR.is_dir(), f"missing domain directory: {DOMAIN_DIR}"
    assert DOMAIN_DIR.name == DOMAIN_ID, "domain directory name must equal domain_id"
    for name in DOMAIN_DOCS:
        assert (DOMAIN_DIR / name).is_file(), f"missing domain document: {name}"

    assert SCORING_DIR.is_dir(), f"missing hidden scoring directory: {SCORING_DIR}"
    scoring_files = sorted(SCORING_DIR.glob("*"))
    assert scoring_files, "hidden scoring directory is empty"
    for path in scoring_files:
        assert path.is_file(), f"scoring directory must contain only files: {path}"
        assert path.parent == SCORING_DIR, f"scoring specs must not nest: {path}"
        assert path.suffix == ".json", f"scoring spec must be JSON: {path}"

    expected = {DOMAIN_DIR / name for name in DOMAIN_DOCS} | set(scoring_files)
    actual = {path for path in DOMAIN_DIR.rglob("*") if path.is_file()}
    unexpected = actual - expected
    assert not unexpected, f"unexpected files in the CF domain fixture tree: {sorted(unexpected)}"
    missing = expected - actual
    assert not missing, f"missing CF domain fixture files: {sorted(missing)}"


def test_all_json_documents_parse_as_utf8_objects():
    json_paths = sorted(FIXTURES_DIR.rglob("*.json"))
    assert json_paths, "no fixture JSON documents found"
    for path in json_paths:
        text = path.read_text(encoding="utf-8")  # raises on invalid UTF-8
        assert text.strip(), f"empty fixture document: {path}"
        assert not text.startswith("\ufeff"), f"UTF-8 BOM found in {path}"
        parsed = json.loads(text)
        assert isinstance(parsed, dict), f"{path} must decode to a JSON object"


def test_domain_documents_versions_are_consistent():
    declared_versions = {}
    for name in DOMAIN_DOCS:
        doc = _load_json(DOMAIN_DIR / name)
        assert doc.get("schema_version") == SCHEMA_VERSION, f"{name}: schema_version"
        assert doc.get("domain_id") == DOMAIN_ID, f"{name}: domain_id"
        version_fields = {key for key in doc if "version" in key.lower()}
        undeclared = sorted(version_fields - VERSION_FIELD_NAMES)
        assert not undeclared, f"{name}: undeclared version-like field(s): {undeclared}"
        if "domain_version" in doc:
            declared_versions[name] = doc["domain_version"]

    assert DOMAIN_VERSION_DECLARATION in declared_versions, (
        f"{DOMAIN_VERSION_DECLARATION} must declare the domain-level domain_version"
    )
    for name, version in declared_versions.items():
        assert version == DOMAIN_VERSION, f"{name}: unexpected domain_version {version!r}"


def test_hidden_scoring_specs_declare_no_version_fields():
    for path in sorted(SCORING_DIR.glob("*.json")):
        spec = _load_json(path)
        version_fields = sorted(key for key in spec if "version" in key.lower())
        assert not version_fields, (
            f"{path.name}: hidden scoring specs must not declare version field(s)"
        )


def test_readme_documents_formats_license_and_provenance():
    text = README_PATH.read_text(encoding="utf-8")
    required_statements = (
        "schema_version",
        SCHEMA_VERSION,
        DOMAIN_ID,
        DOMAIN_VERSION,
        "CC0-1.0",
        "synthetic",
        "合成",
        "隐藏",
        "scoring/",
        "离线",
        "真实",
    )
    for needle in required_statements:
        assert needle in text, f"README is missing required statement: {needle!r}"
    for name in DOMAIN_DOCS:
        assert name in text, f"README does not document fixture file {name}"
    for kind in ("MCQ", "PYTHON_FUNCTION", "SEMANTIC_RUBRIC", "NEEDS_REVIEW"):
        assert kind in text, f"README does not document scoring kind/policy {kind}"


# ---------------------------------------------------------------------------
# 2. Knowledge graph: nodes
# ---------------------------------------------------------------------------


def test_knowledge_graph_has_exactly_the_frozen_node_set():
    kg = _knowledge_graph()
    nodes = kg["nodes"]
    assert isinstance(nodes, list), "nodes must be a list"
    node_ids = [node["node_id"] for node in nodes]
    assert len(node_ids) == len(set(node_ids)), f"duplicate node ids: {node_ids}"
    assert len(nodes) == 8, f"expected exactly 8 nodes, got {len(nodes)}"
    assert set(node_ids) == set(EXPECTED_NODES), (
        f"node set mismatch: missing={set(EXPECTED_NODES) - set(node_ids)}, "
        f"extra={set(node_ids) - set(EXPECTED_NODES)}"
    )

    for node in nodes:
        node_id = node["node_id"]
        expected_difficulty, expected_mode = EXPECTED_NODES[node_id]
        assert isinstance(node["title"], str) and node["title"].strip(), node_id
        assert isinstance(node["description"], str) and node["description"].strip(), node_id
        difficulty = node["difficulty"]
        assert isinstance(difficulty, int) and not isinstance(difficulty, bool), node_id
        assert node["difficulty"] == expected_difficulty, node_id
        assert 1 <= node["difficulty"] <= 5, node_id
        assert node["assessment_mode"] in ALLOWED_MODES, node_id
        assert node["assessment_mode"] == expected_mode, node_id
        tags = node["tags"]
        assert isinstance(tags, list) and tags, f"{node_id}: tags must be a non-empty list"
        assert all(isinstance(tag, str) and tag.strip() for tag in tags), node_id
        assert len(tags) == len(set(tags)), f"{node_id}: duplicate tags"
        assert isinstance(node["content_ref"], str) and node["content_ref"].strip(), node_id


# ---------------------------------------------------------------------------
# 3. Knowledge graph: edges and DAG acyclicity
# ---------------------------------------------------------------------------


def _topological_order(node_ids: set, edges: list) -> list:
    """Kahn's algorithm; returns the topological order (empty if cyclic)."""
    indegree = {node_id: 0 for node_id in node_ids}
    children = defaultdict(list)
    for source, target in edges:
        children[source].append(target)
        indegree[target] += 1
    ready = [node_id for node_id in node_ids if indegree[node_id] == 0]
    order = []
    while ready:
        current = ready.pop()
        order.append(current)
        for child in children[current]:
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
    return order


def test_knowledge_graph_edges_are_frozen_and_acyclic():
    kg = _knowledge_graph()
    node_ids = _node_ids()
    raw_edges = kg["edges"]
    assert isinstance(raw_edges, list), "edges must be a list"
    assert len(raw_edges) == 9, f"expected exactly 9 edges, got {len(raw_edges)}"

    triples = []
    for edge in raw_edges:
        source = edge["source_node_id"]
        target = edge["target_node_id"]
        assert source in node_ids, f"edge source references unknown node: {source}"
        assert target in node_ids, f"edge target references unknown node: {target}"
        assert source != target, f"self-loop edge: {source}"
        kind = edge["kind"]
        assert kind in ALLOWED_EDGE_KINDS, f"invalid edge kind: {kind}"
        weight = edge["weight"]
        assert isinstance(weight, (int, float)) and not isinstance(weight, bool), edge
        assert 0.0 <= float(weight) <= 1.0, f"edge weight out of range: {weight}"
        triples.append((source, target, kind))

    assert len(triples) == len(set(triples)), "duplicate edges found"
    assert set(triples) == EXPECTED_EDGES, (
        f"edge set mismatch: missing={sorted(EXPECTED_EDGES - set(triples))}, "
        f"extra={sorted(set(triples) - EXPECTED_EDGES)}"
    )

    order = _topological_order(node_ids, [(source, target) for source, target, _ in triples])
    assert len(order) == len(node_ids), "knowledge graph contains a cycle (DAG required)"

    # Every node must be reachable from the single root "cf.array.basics".
    children = defaultdict(list)
    for source, target, _ in triples:
        children[source].append(target)
    reachable = set()
    stack = ["cf.array.basics"]
    while stack:
        current = stack.pop()
        if current in reachable:
            continue
        reachable.add(current)
        stack.extend(children[current])
    assert reachable == node_ids, (
        f"nodes unreachable from cf.array.basics: {sorted(node_ids - reachable)}"
    )


# ---------------------------------------------------------------------------
# 4. Objectives
# ---------------------------------------------------------------------------


def test_objectives_reference_existing_nodes_and_valid_thresholds():
    doc = _objectives_doc()
    objectives = doc["objectives"]
    assert isinstance(objectives, list) and objectives, "at least one objective required"
    node_ids = _node_ids()

    objective_ids = [objective["objective_id"] for objective in objectives]
    assert len(objective_ids) == len(set(objective_ids)), "duplicate objective ids"
    assert MASTERY_OBJECTIVE_ID in objective_ids, f"missing objective {MASTERY_OBJECTIVE_ID}"

    for objective in objectives:
        assert isinstance(objective["title"], str) and objective["title"].strip()
        assert isinstance(objective["description"], str) and objective["description"].strip()
        targets = objective["target_node_ids"]
        assert isinstance(targets, list) and targets, "target_node_ids must be non-empty"
        assert len(targets) == len(set(targets)), "duplicate target node ids"
        for node_id in targets:
            assert node_id in node_ids, f"objective targets unknown node: {node_id}"

        criteria = objective["success_criteria"]
        assert isinstance(criteria, dict), "success_criteria must be an object"
        min_mastery = criteria["min_mastery"]
        max_error_rate = criteria["max_error_rate"]
        assert isinstance(min_mastery, (int, float)) and not isinstance(min_mastery, bool)
        assert 0.0 <= float(min_mastery) <= 1.0, "min_mastery must be within [0, 1]"
        assert isinstance(max_error_rate, (int, float)) and not isinstance(max_error_rate, bool)
        assert 0.0 <= float(max_error_rate) <= 1.0, "max_error_rate must be within [0, 1]"
        required = criteria["required_node_ids"]
        assert isinstance(required, list) and required, "required_node_ids must be non-empty"
        for node_id in required:
            assert node_id in node_ids, f"success criteria requires unknown node: {node_id}"
        assert set(required) <= set(targets), "required nodes must be a subset of targets"

        minutes = objective["estimated_minutes"]
        assert isinstance(minutes, int) and not isinstance(minutes, bool)
        assert minutes > 0, "estimated_minutes must be positive"

    mastery = next(o for o in objectives if o["objective_id"] == MASTERY_OBJECTIVE_ID)
    assert set(mastery["target_node_ids"]) == MASTERY_TARGET_NODES
    assert set(mastery["success_criteria"]["required_node_ids"]) == MASTERY_REQUIRED_NODES
    assert float(mastery["success_criteria"]["min_mastery"]) == 0.7
    assert float(mastery["success_criteria"]["max_error_rate"]) == 0.3


# ---------------------------------------------------------------------------
# 5. Assessment items: shared structure
# ---------------------------------------------------------------------------


def test_assessment_items_cover_every_node_and_are_well_formed():
    items = _items()
    assert len(items) >= 12, f"at least 12 assessment items required, got {len(items)}"

    item_ids = [item["item_id"] for item in items]
    assert len(item_ids) == len(set(item_ids)), "duplicate item ids"
    node_ids = _node_ids()

    covered = set()
    type_counts = defaultdict(int)
    for item in items:
        item_id = item["item_id"]
        assert isinstance(item_id, str) and item_id, "item_id must be a non-empty string"
        assert re.fullmatch(r"item\.bs\.(mcq|code|short)\.\d{3}", item_id), (
            f"unexpected item id shape: {item_id}"
        )
        item_type = item["item_type"]
        assert item_type in ALLOWED_ITEM_TYPES, f"{item_id}: invalid item_type {item_type}"
        prefix = item_id.split(".")[2]
        assert {"mcq": "MCQ", "code": "CODE", "short": "SHORT_ANSWER"}[prefix] == item_type, (
            f"{item_id}: id prefix does not match item_type {item_type}"
        )
        type_counts[item_type] += 1

        assert isinstance(item["prompt"], str) and item["prompt"].strip(), item_id
        difficulty = item["difficulty"]
        assert isinstance(difficulty, int) and not isinstance(difficulty, bool), item_id
        assert 1 <= difficulty <= 5, f"{item_id}: difficulty out of range"
        max_score = item["max_score"]
        assert isinstance(max_score, (int, float)) and not isinstance(max_score, bool), item_id
        assert float(max_score) > 0.0, f"{item_id}: max_score must be positive"
        assert isinstance(item["deterministic"], bool), f"{item_id}: deterministic must be bool"
        assert isinstance(item["public"], bool), f"{item_id}: public must be bool"

        item_nodes = item["node_ids"]
        assert isinstance(item_nodes, list) and item_nodes, f"{item_id}: node_ids required"
        assert len(item_nodes) == len(set(item_nodes)), f"{item_id}: duplicate node ids"
        for node_id in item_nodes:
            assert node_id in node_ids, f"{item_id}: unknown node id {node_id}"
        covered.update(item_nodes)

        assert item["scoring_spec_ref"] == f"scoring/{item_id}.json", (
            f"{item_id}: scoring_spec_ref must be scoring/<item_id>.json"
        )

    assert covered == node_ids, f"nodes without any assessment item: {sorted(node_ids - covered)}"
    assert set(type_counts) == ALLOWED_ITEM_TYPES, "all three item types must be used"
    assert type_counts["MCQ"] >= 6, "at least 6 MCQ items required"
    assert type_counts["CODE"] >= 4, "at least 4 CODE items required"
    assert type_counts["SHORT_ANSWER"] >= 2, "at least 2 SHORT_ANSWER items required"


def test_deterministic_flag_matches_item_type():
    for item in _items():
        item_id = item["item_id"]
        if item["item_type"] in ("MCQ", "CODE"):
            assert item["deterministic"] is True, f"{item_id}: MCQ/CODE items must be deterministic"
        else:
            assert item["deterministic"] is False, (
                f"{item_id}: open-ended items must not be deterministic"
            )


# ---------------------------------------------------------------------------
# 6. Assessment items: per-type contract and hidden scoring specs
# ---------------------------------------------------------------------------


def test_mcq_items_have_consistent_hidden_answer_keys():
    mcqs = [item for item in _items() if item["item_type"] == "MCQ"]
    assert mcqs, "expected MCQ items"
    correct_indexes = []
    for item in mcqs:
        item_id = item["item_id"]
        assert item["deterministic"] is True, f"{item_id}: MCQ must be deterministic"
        assert "function_name" not in item, f"{item_id}: MCQ must not declare function_name"
        options = item["options"]
        assert isinstance(options, list) and len(options) >= 2, f"{item_id}: options >= 2"
        assert all(isinstance(option, str) and option.strip() for option in options), item_id
        assert len(options) == len(set(options)), f"{item_id}: duplicate options"

        spec = _scoring_spec(item_id)
        assert spec["kind"] == "MCQ", f"{item_id}: scoring kind must be MCQ"
        index = spec["correct_option_index"]
        assert isinstance(index, int) and not isinstance(index, bool), item_id
        assert 0 <= index < len(options), f"{item_id}: correct_option_index out of range"
        correct_indexes.append(index)
        assert isinstance(spec["explanation"], str) and spec["explanation"].strip(), item_id

    assert len(set(correct_indexes)) >= 3, (
        "MCQ correct answers are clustered on too few option positions; "
        "shuffle options so the key is not guessable by position"
    )


def _code_items_with_specs() -> list:
    return [
        (item, _scoring_spec(item["item_id"]))
        for item in _items()
        if item["item_type"] == "CODE"
    ]


def test_code_items_have_executable_hidden_test_specs():
    code_items = _code_items_with_specs()
    assert len(code_items) >= 4, "expected at least 4 CODE items"

    duplicate_specs = 0
    for item, spec in code_items:
        item_id = item["item_id"]
        assert item["deterministic"] is True, f"{item_id}: CODE must be deterministic"
        assert "options" not in item, f"{item_id}: CODE must not declare options"
        function_name = item["function_name"]
        assert isinstance(function_name, str) and function_name.strip(), item_id
        assert re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", function_name), (
            f"{item_id}: function_name must be a Python identifier"
        )
        assert spec["kind"] == "PYTHON_FUNCTION", f"{item_id}: scoring kind must be PYTHON_FUNCTION"
        assert spec["function_name"] == function_name, f"{item_id}: function name mismatch"

        timeout_s = spec["timeout_s"]
        assert isinstance(timeout_s, (int, float)) and not isinstance(timeout_s, bool), item_id
        assert 0 < float(timeout_s) <= 10.0, f"{item_id}: timeout_s out of sane range"

        tests = spec["tests"]
        assert isinstance(tests, list) and len(tests) >= 6, (
            f"{item_id}: at least 6 hidden test cases required, got {len(tests)}"
        )
        has_empty_array = False
        has_single_element = False
        has_missing_target = False
        has_duplicate_values = False
        for case in tests:
            assert isinstance(case, dict) and set(case) == {"args", "expected"}, (
                f"{item_id}: each test case needs exactly args/expected"
            )
            args = case["args"]
            assert isinstance(args, list), f"{item_id}: test args must be a list"
            expected = case["expected"]
            assert isinstance(expected, (bool, int, float, str, list)), item_id
            json.dumps(case)  # must be JSON serializable

            arrays = _arrays_in_test_case(args)
            if arrays:
                if len(arrays[0]) == 0:
                    has_empty_array = True
                if len(arrays[0]) == 1:
                    has_single_element = True
                if len(arrays[0]) > 1 and len(arrays[0]) != len(set(map(repr, arrays[0]))):
                    has_duplicate_values = True
            if len(args) >= 2 and isinstance(args[0], list) and isinstance(expected, (int, float)):
                target = args[1]
                if isinstance(target, int) and not isinstance(target, bool) and target not in args[0]:
                    has_missing_target = True

        assert has_empty_array, f"{item_id}: hidden tests must include an empty array case"
        assert has_single_element, f"{item_id}: hidden tests must include a single-element case"
        if has_duplicate_values:
            duplicate_specs += 1
        if all(isinstance(case["expected"], bool) for case in tests):
            assert {case["expected"] for case in tests} == {True, False}, (
                f"{item_id}: boolean-returning function must cover both True and False"
            )
        else:
            assert has_missing_target, (
                f"{item_id}: index-returning function must include a target that is absent"
            )

    assert duplicate_specs >= 2, (
        "at least two CODE specs must exercise duplicate values (boundary/off-by-one coverage)"
    )
    assert any(
        case["expected"] == -1
        for _, spec in code_items
        for case in spec["tests"]
        if isinstance(case["expected"], int) and not isinstance(case["expected"], bool)
    ), "at least one CODE spec must encode the not-found sentinel -1"


def test_short_answer_items_have_semantic_rubrics_needing_review():
    shorts = [
        (item, _scoring_spec(item["item_id"]))
        for item in _items()
        if item["item_type"] == "SHORT_ANSWER"
    ]
    assert len(shorts) >= 2, "expected at least 2 SHORT_ANSWER items"
    for item, spec in shorts:
        item_id = item["item_id"]
        assert item["deterministic"] is False, item_id
        assert "options" not in item, f"{item_id}: SHORT_ANSWER must not declare options"
        assert "function_name" not in item, f"{item_id}: SHORT_ANSWER must not declare a function"
        assert spec["kind"] == "SEMANTIC_RUBRIC", f"{item_id}: scoring kind must be SEMANTIC_RUBRIC"
        groups = spec["required_concept_groups"]
        assert isinstance(groups, list) and len(groups) >= 2, (
            f"{item_id}: at least two required concept groups (no single-string fake match)"
        )
        for group in groups:
            assert isinstance(group, list) and len(group) >= 2, (
                f"{item_id}: each concept group needs at least two synonyms"
            )
            assert all(isinstance(synonym, str) and synonym.strip() for synonym in group), item_id
            assert len(group) == len(set(group)), f"{item_id}: duplicate rubric synonyms"
        assert spec["allow_correct"] is False, (
            f"{item_id}: open-ended answers must never be auto-marked correct"
        )
        assert spec["on_insufficient"] == "NEEDS_REVIEW", (
            f"{item_id}: insufficient evidence must escalate to NEEDS_REVIEW"
        )
        for forbidden_key in ("correct_option_index", "expected", "correct_answer"):
            assert forbidden_key not in spec, f"{item_id}: open item must not embed {forbidden_key}"


def test_scoring_specs_and_items_are_in_bijection():
    item_ids = {item["item_id"] for item in _items()}
    scoring_ids = {path.stem for path in SCORING_DIR.glob("*.json")}
    assert scoring_ids == item_ids, (
        f"scoring/item mismatch: missing={sorted(item_ids - scoring_ids)}, "
        f"orphan={sorted(scoring_ids - item_ids)}"
    )
    for item in _items():
        spec_path = DOMAIN_DIR / item["scoring_spec_ref"]
        assert spec_path.is_file(), (
            f"{item['item_id']}: scoring_spec_ref does not resolve: {item['scoring_spec_ref']}"
        )
        assert spec_path.parent == SCORING_DIR, "scoring specs must live directly in scoring/"
        assert ".." not in Path(item["scoring_spec_ref"]).parts


# ---------------------------------------------------------------------------
# 7. Teaching content
# ---------------------------------------------------------------------------


def test_teaching_content_covers_every_node_completely():
    teaching = _teaching_doc()["nodes"]
    assert isinstance(teaching, dict), "teaching_content.nodes must be an object"
    node_ids = _node_ids()
    assert set(teaching) == node_ids, (
        f"teaching coverage mismatch: missing={sorted(node_ids - set(teaching))}, "
        f"extra={sorted(set(teaching) - node_ids)}"
    )

    kg_by_id = {node["node_id"]: node for node in _knowledge_graph()["nodes"]}
    item_ids = {item["item_id"] for item in _items()}
    referenced_by_practice = set()

    for node_id, content in teaching.items():
        assert set(content) >= REQUIRED_TEACHING_KEYS, (
            f"{node_id}: missing teaching keys {sorted(REQUIRED_TEACHING_KEYS - set(content))}"
        )
        for key in ("EXPLAIN", "HINT_L1", "HINT_L2", "HINT_L3", "REVIEW"):
            value = content[key]
            assert isinstance(value, str) and value.strip(), f"{node_id}: {key} must be non-empty"
        assert content["HINT_L1"] != content["HINT_L2"], f"{node_id}: HINT_L1 must add hints"
        assert content["HINT_L2"] != content["HINT_L3"], f"{node_id}: HINT_L2/L3 must differ"
        assert len(content["HINT_L1"]) < len(content["HINT_L3"]), (
            f"{node_id}: HINT_L1 must be the least revealing level"
        )
        lowered_l1 = content["HINT_L1"].lower()
        for token in HINT_L1_FORBIDDEN:
            assert token.lower() not in lowered_l1, (
                f"{node_id}: HINT_L1 leaks code/answer token {token!r}"
            )

        assert kg_by_id[node_id]["content_ref"] in teaching, (
            f"{node_id}: content_ref does not point at teaching content"
        )

        practice = content["PRACTICE_ITEM_IDS"]
        assert isinstance(practice, list) and practice, f"{node_id}: PRACTICE_ITEM_IDS required"
        assert len(practice) == len(set(practice)), f"{node_id}: duplicate practice item ids"
        for item_id in practice:
            assert item_id in item_ids, f"{node_id}: practice item does not exist: {item_id}"
            referenced_by_practice.add(item_id)
        for item in _items():
            if item["item_id"] in practice:
                assert node_id in item["node_ids"], (
                    f"{node_id}: practice item {item['item_id']} does not cover this node"
                )

    assert referenced_by_practice == item_ids, (
        f"assessment items missing from teaching practice lists: "
        f"{sorted(item_ids - referenced_by_practice)}"
    )


# ---------------------------------------------------------------------------
# 8. Hidden-scoring separation and answer-leak prevention
# ---------------------------------------------------------------------------


def test_teaching_content_does_not_reference_hidden_scoring():
    teaching_raw = (DOMAIN_DIR / "teaching_content.json").read_text(encoding="utf-8")
    assert "scoring/" not in teaching_raw, "teaching content must not reference scoring/"
    for item in _items():
        assert "scoring/" not in item["prompt"], (
            f"{item['item_id']}: prompt must not reference scoring/"
        )
    for text in _teaching_texts():
        for token in HIDDEN_KEY_TOKENS:
            assert token not in text, f"teaching content leaks hidden-scoring token {token!r}"

    for item in _items():
        for token in HIDDEN_KEY_TOKENS:
            assert token not in item["prompt"], (
                f"{item['item_id']}: prompt leaks hidden-scoring token {token!r}"
            )


def test_public_fields_do_not_leak_answers_or_hidden_tests():
    visible_teaching = "\n".join(_teaching_texts())

    for item in _items():
        item_id = item["item_id"]
        prompt = item["prompt"]
        spec = _scoring_spec(item_id)

        if item["item_type"] == "MCQ":
            correct_text = item["options"][spec["correct_option_index"]]
            assert correct_text not in prompt, f"{item_id}: prompt contains the correct option"
            assert correct_text not in visible_teaching, (
                f"{item_id}: teaching content contains the correct option verbatim"
            )
            assert spec["explanation"] not in prompt, f"{item_id}: prompt contains explanation"
            assert spec["explanation"] not in visible_teaching, (
                f"{item_id}: teaching content contains the hidden explanation"
            )

        elif item["item_type"] == "CODE":
            assert "```" not in prompt, f"{item_id}: prompt must not embed a code block"
            assert "def " not in prompt, f"{item_id}: prompt must not embed an implementation"
            for case in spec["tests"]:
                dumped = json.dumps(case["args"], ensure_ascii=False)
                assert dumped not in prompt, f"{item_id}: prompt leaks hidden test args"
                assert dumped not in visible_teaching, (
                    f"{item_id}: teaching content leaks hidden test args"
                )

        else:  # SHORT_ANSWER
            dumped_groups = json.dumps(spec["required_concept_groups"], ensure_ascii=False)
            assert dumped_groups not in prompt, f"{item_id}: prompt leaks the semantic rubric"
            assert "NEEDS_REVIEW" not in prompt, f"{item_id}: prompt leaks review policy"


# ---------------------------------------------------------------------------
# 9. Synthetic/offline guarantees (no network, keys, or real-data shapes)
# ---------------------------------------------------------------------------


def test_fixtures_contain_no_network_key_or_real_data_shapes():
    texts = _all_fixture_texts()
    assert texts, "no fixture files found to scan"
    # The judge corpus is excluded by _fixture_files(); prove the exclusion is
    # explicit and still covered by the dedicated integrity suite.
    assert JUDGE_FIXTURES_DIR.is_dir(), "judge corpus expected to exist and be validated separately"
    assert all(JUDGE_FIXTURES_DIR not in path.parents for path in texts)

    for path, text in texts.items():
        lowered = text.lower()
        for token in FORBIDDEN_TOKENS:
            assert token not in lowered, f"{path.name}: forbidden token {token!r} in fixture"
        assert "@" not in text, f"{path.name}: fixtures must not contain identity/email shapes"
        assert not EMAIL_RE.search(text), f"{path.name}: email-like shape found"
        assert not WINDOWS_PATH_RE.search(text), f"{path.name}: Windows absolute path found"
        assert not re.search(r"(?<![A-Za-z])/(root|home|Users)/", text), (
            f"{path.name}: absolute user path found"
        )


def test_test_module_is_offline_and_imports_only_stdlib():
    source = Path(__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                assert root in ALLOWED_TEST_MODULE_IMPORTS, (
                    f"test module imports non-stdlib/side-effecting module: {alias.name}"
                )
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "test module must not use relative imports"
            root = (node.module or "").split(".")[0]
            assert root in ALLOWED_TEST_MODULE_IMPORTS, (
                f"test module imports non-stdlib/side-effecting module: {node.module}"
            )

    lowered = source.lower()
    for token in FORBIDDEN_TOKENS:
        assert token not in lowered, f"test module contains forbidden token {token!r}"

    # The module must not depend on another workstream's shared fixture module.
    assert _rev("tsetfnoc") not in lowered, (
        "test module must stay independent of shared fixture modules"
    )


# ---------------------------------------------------------------------------
# 10. Assessment design supports the two synthetic student profiles
# ---------------------------------------------------------------------------


def test_item_design_can_diagnose_off_by_one_and_monotonicity_gaps():
    items = _items()

    boundary_items = [
        item for item in items if "cf.search.boundary" in item["node_ids"]
    ]
    sortedness_items = [
        item for item in items if "cf.sort.sortedness" in item["node_ids"]
    ]

    # Student A (understands binary search, off-by-one at boundaries) needs
    # boundary-targeted items of several formats.
    assert len(boundary_items) >= 2, "boundary/off-by-one coverage is too thin"
    boundary_types = {item["item_type"] for item in boundary_items}
    assert {"MCQ", "CODE", "SHORT_ANSWER"} <= boundary_types, (
        f"boundary items must mix formats, got {sorted(boundary_types)}"
    )
    boundary_code_specs = [
        _scoring_spec(item["item_id"])
        for item in boundary_items
        if item["item_type"] == "CODE"
    ]
    assert boundary_code_specs, "boundary coverage needs a CODE item"
    duplicates_exercised = False
    for spec in boundary_code_specs:
        for case in spec["tests"]:
            for array in _arrays_in_test_case(case["args"]):
                if len(array) > 1 and len(array) != len(set(map(repr, array))):
                    duplicates_exercised = True
    assert duplicates_exercised, (
        "boundary CODE item must exercise duplicate values to expose off-by-one bugs"
    )

    # Student B (does not understand the monotonicity precondition) needs
    # monotonicity-targeted items that explicitly probe the precondition.
    assert len(sortedness_items) >= 2, "monotonicity-precondition coverage is too thin"
    sortedness_types = {item["item_type"] for item in sortedness_items}
    assert "MCQ" in sortedness_types, "need an MCQ probing the monotonicity precondition"
    assert "SHORT_ANSWER" in sortedness_types, (
        "need an open-ended item asking why sortedness is required"
    )
    sortedness_code_specs = [
        _scoring_spec(item["item_id"])
        for item in sortedness_items
        if item["item_type"] == "CODE"
    ]
    assert sortedness_code_specs, "monotonicity coverage needs a CODE item"
    assert any(
        case["expected"] is False
        for spec in sortedness_code_specs
        for case in spec["tests"]
    ), "monotonicity CODE item must include a non-monotonic input expecting False"

    # Both profiles must be distinguishable: they are targeted by different nodes.
    assert set(item["item_id"] for item in boundary_items).isdisjoint(
        set(item["item_id"] for item in sortedness_items)
    ), "diagnosis requires separate boundary and monotonicity item sets"
