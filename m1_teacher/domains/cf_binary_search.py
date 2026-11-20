"""CF binary-search learning domain adapter for the M1-A teacher.

The adapter loads the domain strictly from a frozen, explicitly allow-listed
set of fixture files:

* ``knowledge_graph.json``
* ``objectives.json``
* ``assessment_items.json``
* ``teaching_content.json``

It never enumerates the fixture directory and never reads any other file, so
hidden evaluation material that lives next to these files is structurally
unreachable from the teacher-visible API (a dedicated test proves that a
fixture copy without the evaluation directory still produces an identical
adapter).

The adapter is read-only, deterministic and offline: no network access, no
provider/API key, no randomness.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping

from ..contracts.domain import DomainRegistry
from ..contracts.errors import NotFoundError, ValidationError
from ..contracts.types import (
    ASSESSMENT_MODE_VALUES,
    EDGE_KIND_VALUES,
    ITEM_TYPE_VALUES,
    SCHEMA_VERSION,
    AssessmentItem,
    KnowledgeNode,
    LearningObjective,
    PrerequisiteEdge,
)
from ..knowledge.graph import KnowledgeGraph

__all__ = [
    "CFBinarySearchDomainAdapter",
    "build_default_registry",
    "default_fixtures_root",
    "DOMAIN_ID",
    "DEFAULT_DOMAIN_VERSION",
]

DOMAIN_ID = "cf_binary_search"
DEFAULT_DOMAIN_VERSION = "0.1.0"

FIXTURES_ENV_VAR = "M1_TEACHER_FIXTURES"

_ALLOWED_FILES: tuple[str, ...] = (
    "knowledge_graph.json",
    "objectives.json",
    "assessment_items.json",
    "teaching_content.json",
)

TEACHING_CONTENT_TEMPLATE_KINDS: tuple[str, ...] = (
    "EXPLAIN",
    "HINT_L1",
    "HINT_L2",
    "HINT_L3",
    "REVIEW",
)
TEACHING_CONTENT_KINDS: tuple[str, ...] = TEACHING_CONTENT_TEMPLATE_KINDS + ("PRACTICE",)
_PRACTICE_ITEM_IDS_KEY = "PRACTICE_ITEM_IDS"

_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FIXTURES_ROOT = _REPO_ROOT / "fixtures" / "m1_teacher"

_GRAPH_FILE_KEYS = frozenset(
    {"schema_version", "domain_id", "domain_version", "nodes", "edges"}
)
_NODE_KEYS = frozenset(
    {"node_id", "title", "description", "difficulty", "assessment_mode", "tags", "content_ref"}
)
_EDGE_KEYS = frozenset({"source_node_id", "target_node_id", "kind", "weight"})
_OBJECTIVES_FILE_KEYS = frozenset(
    {"schema_version", "domain_id", "domain_version", "objectives"}
)
_OBJECTIVE_KEYS = frozenset(
    {
        "objective_id",
        "title",
        "description",
        "target_node_ids",
        "success_criteria",
        "estimated_minutes",
    }
)
_SUCCESS_CRITERIA_KEYS = frozenset({"min_mastery", "required_node_ids", "max_error_rate"})
_ITEMS_FILE_KEYS = frozenset(
    {"schema_version", "domain_id", "domain_version", "items"}
)
_ITEM_KEYS = frozenset(
    {
        "item_id",
        "node_ids",
        "item_type",
        "difficulty",
        "prompt",
        "options",
        "function_name",
        "max_score",
        "deterministic",
        "scoring_spec_ref",
        "public",
    }
)
_TEACHING_FILE_KEYS = frozenset(
    {"schema_version", "domain_id", "domain_version", "nodes"}
)
_TEACHING_NODE_KEYS = frozenset(
    {*TEACHING_CONTENT_TEMPLATE_KINDS, _PRACTICE_ITEM_IDS_KEY}
)


# ---------------------------------------------------------------------------
# Small JSON validation helpers (fail-closed, contract-style errors)
# ---------------------------------------------------------------------------


def _expect_mapping(value: Any, where: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValidationError(f"{where}: expected a JSON object")
    return dict(value)


def _expect_list(value: Any, where: str) -> list[Any]:
    if type(value) is not list:
        raise ValidationError(f"{where}: expected a JSON array")
    return value


def _expect_str(
    value: Any, where: str, *, allow_empty: bool = False, what: str = "string"
) -> str:
    if type(value) is not str:
        raise ValidationError(f"{where}: expected a {what}")
    if not allow_empty and not value.strip():
        raise ValidationError(f"{where}: must not be blank")
    return value


def _expect_bool(value: Any, where: str) -> bool:
    if type(value) is not bool:
        raise ValidationError(f"{where}: expected a boolean")
    return value


def _expect_int(value: Any, where: str, *, minimum: int | None = None,
                maximum: int | None = None) -> int:
    if type(value) is not int:
        raise ValidationError(f"{where}: expected an integer")
    if minimum is not None and value < minimum:
        raise ValidationError(f"{where}: {value!r} is below the minimum {minimum!r}")
    if maximum is not None and value > maximum:
        raise ValidationError(f"{where}: {value!r} is above the maximum {maximum!r}")
    return value


def _expect_number(value: Any, where: str, *, minimum: float | None = None,
                   maximum: float | None = None) -> float:
    if type(value) not in (int, float):
        raise ValidationError(f"{where}: expected a number")
    number = float(value)
    if minimum is not None and number < minimum:
        raise ValidationError(f"{where}: {number!r} is below the minimum {minimum!r}")
    if maximum is not None and number > maximum:
        raise ValidationError(f"{where}: {number!r} is above the maximum {maximum!r}")
    return number


def _expect_str_list(value: Any, where: str, *, min_length: int = 0) -> list[str]:
    items = _expect_list(value, where)
    for index, element in enumerate(items):
        if type(element) is not str or not element.strip():
            raise ValidationError(f"{where}[{index}]: expected a non-blank string")
    if len(items) < min_length:
        raise ValidationError(f"{where}: expected at least {min_length} element(s)")
    return list(items)


def _expect_enum(value: Any, allowed: tuple[str, ...], where: str) -> str:
    if type(value) is not str:
        raise ValidationError(f"{where}: expected one of {list(allowed)}")
    if value not in allowed:
        raise ValidationError(f"{where}: {value!r} is not one of {list(allowed)}")
    return value


def _require_key(mapping: Mapping[str, Any], key: str, where: str) -> Any:
    if key not in mapping:
        raise ValidationError(f"{where}: missing required key {key!r}")
    return mapping[key]


def _reject_unknown_keys(mapping: Mapping[str, Any], allowed: frozenset[str], where: str) -> None:
    unknown = sorted(key for key in mapping if key not in allowed)
    if unknown:
        raise ValidationError(f"{where}: unknown key(s): {', '.join(unknown)}")


def _require_schema(payload: Mapping[str, Any], filename: str) -> None:
    version = _require_key(payload, "schema_version", filename)
    if version != SCHEMA_VERSION:
        raise ValidationError(
            f"{filename}: schema_version {version!r} is not the frozen {SCHEMA_VERSION!r}"
        )
    domain_id = _require_key(payload, "domain_id", filename)
    if domain_id != DOMAIN_ID:
        raise ValidationError(
            f"{filename}: domain_id {domain_id!r} is not {DOMAIN_ID!r}"
        )


def _check_file_domain_version(
    payload: Mapping[str, Any], filename: str, expected: str
) -> None:
    """Forward-compatible tolerance for an optional per-file ``domain_version``.

    The frozen fixture format declares ``domain_version`` only once, at the top
    level of ``knowledge_graph.json``.  Other payload files are linked through
    ``schema_version`` + ``domain_id``.  If a future fixture revision repeats
    the optional key, it must at least agree with the graph version; any other
    unknown key still fails closed via the strict allow-lists above.
    """

    if "domain_version" not in payload:
        return
    version = _expect_str(payload["domain_version"], f"{filename}.domain_version")
    if version != expected:
        raise ValidationError(
            f"{filename}: domain_version {version!r} does not match "
            f"knowledge_graph.json ({expected!r})"
        )


def _resolve_domain_dir(fixtures_root: Path) -> Path:
    nested = fixtures_root / "domains" / DOMAIN_ID
    if nested.is_dir():
        return nested
    # Convenience: also accept the domain directory itself.
    if (fixtures_root / "knowledge_graph.json").is_file():
        return fixtures_root
    raise NotFoundError(
        f"CF binary-search fixture directory not found under {fixtures_root}"
    )


def _coerce_fixtures_root(fixtures_root: str | Path) -> Path:
    if isinstance(fixtures_root, Path):
        root = fixtures_root
    elif isinstance(fixtures_root, str):
        if not fixtures_root.strip():
            raise ValidationError("fixtures_root must not be blank")
        root = Path(fixtures_root)
    else:
        raise ValidationError("fixtures_root must be a str or pathlib.Path")
    root = root.expanduser().resolve()
    if not root.is_dir():
        raise NotFoundError(f"fixtures_root does not exist or is not a directory: {root}")
    return root


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class CFBinarySearchDomainAdapter:
    """Teacher-visible domain adapter for the synthetic CF binary-search domain."""

    domain_id: str = DOMAIN_ID

    def __init__(self, fixtures_root: str | Path) -> None:
        self._fixtures_root = _coerce_fixtures_root(fixtures_root)
        self._domain_dir = _resolve_domain_dir(self._fixtures_root)
        self._nodes: list[KnowledgeNode] = []
        self._edges: list[PrerequisiteEdge] = []
        self._objectives: list[LearningObjective] = []
        self._items: list[AssessmentItem] = []
        self._teaching_content: dict[str, dict[str, Any]] = {}
        self._domain_version: str = DEFAULT_DOMAIN_VERSION
        self._graph: KnowledgeGraph | None = None
        self._load()

    # -- loading --------------------------------------------------------------

    def _load_json(self, filename: str) -> dict[str, Any]:
        if filename not in _ALLOWED_FILES:  # pragma: no cover - defensive
            raise ValidationError(f"fixture file {filename!r} is not allow-listed")
        path = self._domain_dir / filename
        if not path.is_file():
            raise NotFoundError(f"required fixture file not found: {path}")
        try:
            raw_text = path.read_text(encoding="utf-8")
        except OSError as exc:  # pragma: no cover - filesystem failure
            raise NotFoundError(f"cannot read fixture file {path}: {exc}") from exc
        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise ValidationError(f"{filename}: invalid JSON: {exc}") from exc
        return _expect_mapping(payload, filename)

    def _load(self) -> None:
        graph_payload = self._load_json("knowledge_graph.json")
        _require_schema(graph_payload, "knowledge_graph.json")
        _reject_unknown_keys(graph_payload, _GRAPH_FILE_KEYS, "knowledge_graph.json")
        self._domain_version = _expect_str(
            _require_key(graph_payload, "domain_version", "knowledge_graph.json"),
            "knowledge_graph.json.domain_version",
        )
        self._nodes = self._load_nodes(
            _expect_list(
                _require_key(graph_payload, "nodes", "knowledge_graph.json"),
                "knowledge_graph.json.nodes",
            )
        )
        self._edges = self._load_edges(
            _expect_list(
                _require_key(graph_payload, "edges", "knowledge_graph.json"),
                "knowledge_graph.json.edges",
            )
        )
        self._graph = KnowledgeGraph(self._nodes, self._edges)

        objectives_payload = self._load_json("objectives.json")
        _require_schema(objectives_payload, "objectives.json")
        _reject_unknown_keys(objectives_payload, _OBJECTIVES_FILE_KEYS, "objectives.json")
        _check_file_domain_version(objectives_payload, "objectives.json", self._domain_version)
        self._objectives = self._load_objectives(
            _expect_list(
                _require_key(objectives_payload, "objectives", "objectives.json"),
                "objectives.json.objectives",
            )
        )

        items_payload = self._load_json("assessment_items.json")
        _require_schema(items_payload, "assessment_items.json")
        _reject_unknown_keys(items_payload, _ITEMS_FILE_KEYS, "assessment_items.json")
        _check_file_domain_version(items_payload, "assessment_items.json", self._domain_version)
        self._items = self._load_items(
            _expect_list(
                _require_key(items_payload, "items", "assessment_items.json"),
                "assessment_items.json.items",
            )
        )

        teaching_payload = self._load_json("teaching_content.json")
        _require_schema(teaching_payload, "teaching_content.json")
        _reject_unknown_keys(teaching_payload, _TEACHING_FILE_KEYS, "teaching_content.json")
        _check_file_domain_version(
            teaching_payload, "teaching_content.json", self._domain_version
        )
        self._teaching_content = self._load_teaching_content(
            _expect_mapping(
                _require_key(teaching_payload, "nodes", "teaching_content.json"),
                "teaching_content.json.nodes",
            )
        )

    def _load_nodes(self, raw_nodes: list[Any]) -> list[KnowledgeNode]:
        nodes: list[KnowledgeNode] = []
        seen: set[str] = set()
        for index, raw in enumerate(raw_nodes):
            where = f"knowledge_graph.json.nodes[{index}]"
            node = _expect_mapping(raw, where)
            _reject_unknown_keys(node, _NODE_KEYS, where)
            node_id = _expect_str(_require_key(node, "node_id", where), f"{where}.node_id")
            if node_id in seen:
                raise ValidationError(f"{where}: duplicate node_id {node_id!r}")
            seen.add(node_id)
            tags = _expect_str_list(node.get("tags", []), f"{where}.tags")
            nodes.append(
                KnowledgeNode(
                    node_id=node_id,
                    domain_id=DOMAIN_ID,
                    title=_expect_str(_require_key(node, "title", where), f"{where}.title"),
                    description=_expect_str(
                        _require_key(node, "description", where),
                        f"{where}.description",
                        allow_empty=True,
                    ),
                    difficulty=_expect_int(
                        _require_key(node, "difficulty", where),
                        f"{where}.difficulty",
                        minimum=1,
                        maximum=5,
                    ),
                    assessment_mode=_expect_enum(
                        _require_key(node, "assessment_mode", where),
                        ASSESSMENT_MODE_VALUES,
                        f"{where}.assessment_mode",
                    ),
                    tags=tags,
                    content_ref=_expect_str(
                        node.get("content_ref", ""), f"{where}.content_ref", allow_empty=True
                    ),
                )
            )
        return nodes

    def _load_edges(self, raw_edges: list[Any]) -> list[PrerequisiteEdge]:
        edges: list[PrerequisiteEdge] = []
        for index, raw in enumerate(raw_edges):
            where = f"knowledge_graph.json.edges[{index}]"
            edge = _expect_mapping(raw, where)
            _reject_unknown_keys(edge, _EDGE_KEYS, where)
            edges.append(
                PrerequisiteEdge(
                    source_node_id=_expect_str(
                        _require_key(edge, "source_node_id", where),
                        f"{where}.source_node_id",
                    ),
                    target_node_id=_expect_str(
                        _require_key(edge, "target_node_id", where),
                        f"{where}.target_node_id",
                    ),
                    kind=_expect_enum(
                        _require_key(edge, "kind", where),
                        EDGE_KIND_VALUES,
                        f"{where}.kind",
                    ),
                    weight=_expect_number(
                        edge.get("weight", 1.0),
                        f"{where}.weight",
                        minimum=0.0,
                        maximum=1.0,
                    ),
                )
            )
        return edges

    def _load_objectives(self, raw_objectives: list[Any]) -> list[LearningObjective]:
        objectives: list[LearningObjective] = []
        for index, raw in enumerate(raw_objectives):
            where = f"objectives.json.objectives[{index}]"
            objective = _expect_mapping(raw, where)
            _reject_unknown_keys(objective, _OBJECTIVE_KEYS, where)
            criteria = _expect_mapping(
                _require_key(objective, "success_criteria", where),
                f"{where}.success_criteria",
            )
            _reject_unknown_keys(criteria, _SUCCESS_CRITERIA_KEYS, f"{where}.success_criteria")
            objectives.append(
                LearningObjective(
                    objective_id=_expect_str(
                        _require_key(objective, "objective_id", where),
                        f"{where}.objective_id",
                    ),
                    domain_id=DOMAIN_ID,
                    title=_expect_str(
                        _require_key(objective, "title", where), f"{where}.title"
                    ),
                    description=_expect_str(
                        _require_key(objective, "description", where),
                        f"{where}.description",
                        allow_empty=True,
                    ),
                    target_node_ids=_expect_str_list(
                        _require_key(objective, "target_node_ids", where),
                        f"{where}.target_node_ids",
                        min_length=1,
                    ),
                    success_criteria=criteria,
                    estimated_minutes=_expect_int(
                        objective.get("estimated_minutes", 120),
                        f"{where}.estimated_minutes",
                        minimum=0,
                    ),
                )
            )
        return objectives

    def _load_items(self, raw_items: list[Any]) -> list[AssessmentItem]:
        items: list[AssessmentItem] = []
        seen: set[str] = set()
        for index, raw in enumerate(raw_items):
            where = f"assessment_items.json.items[{index}]"
            item = _expect_mapping(raw, where)
            _reject_unknown_keys(item, _ITEM_KEYS, where)
            item_id = _expect_str(
                _require_key(item, "item_id", where), f"{where}.item_id"
            )
            if item_id in seen:
                raise ValidationError(f"{where}: duplicate item_id {item_id!r}")
            seen.add(item_id)
            function_name = item.get("function_name")
            if function_name is not None:
                function_name = _expect_str(function_name, f"{where}.function_name")
            public = item.get("public", True)
            # Fixture-level metadata only: the frozen m1a.v0 AssessmentItem does
            # not expose it.  It is validated here and intentionally dropped.
            _expect_bool(public, f"{where}.public")
            options_raw = item.get("options")
            options = (
                [] if options_raw is None else _expect_str_list(options_raw, f"{where}.options")
            )
            items.append(
                AssessmentItem(
                    item_id=item_id,
                    domain_id=DOMAIN_ID,
                    node_ids=_expect_str_list(
                        _require_key(item, "node_ids", where),
                        f"{where}.node_ids",
                        min_length=1,
                    ),
                    item_type=_expect_enum(
                        _require_key(item, "item_type", where),
                        ITEM_TYPE_VALUES,
                        f"{where}.item_type",
                    ),
                    difficulty=_expect_int(
                        _require_key(item, "difficulty", where),
                        f"{where}.difficulty",
                        minimum=1,
                        maximum=5,
                    ),
                    prompt=_expect_str(
                        _require_key(item, "prompt", where), f"{where}.prompt"
                    ),
                    options=options,
                    function_name=function_name,
                    max_score=_expect_number(
                        item.get("max_score", 1.0), f"{where}.max_score", minimum=0.0
                    ),
                    deterministic=_expect_bool(
                        item.get("deterministic", True), f"{where}.deterministic"
                    ),
                    scoring_spec_ref=_expect_str(
                        item.get("scoring_spec_ref", ""),
                        f"{where}.scoring_spec_ref",
                        allow_empty=True,
                    ),
                )
            )
        return items

    def _load_teaching_content(
        self, raw_nodes: Mapping[str, Any]
    ) -> dict[str, dict[str, Any]]:
        content: dict[str, dict[str, Any]] = {}
        for node_id, raw_templates in raw_nodes.items():
            where = f"teaching_content.json.nodes[{node_id!r}]"
            if type(node_id) is not str or not node_id.strip():
                raise ValidationError(
                    "teaching_content.json.nodes: node keys must be non-blank strings"
                )
            templates = _expect_mapping(raw_templates, where)
            _reject_unknown_keys(templates, _TEACHING_NODE_KEYS, where)
            parsed: dict[str, Any] = {}
            for kind in TEACHING_CONTENT_TEMPLATE_KINDS:
                parsed[kind] = _expect_str(
                    _require_key(templates, kind, where),
                    f"{where}.{kind}",
                    what="teaching content template string",
                )
            parsed[_PRACTICE_ITEM_IDS_KEY] = _expect_str_list(
                templates.get(_PRACTICE_ITEM_IDS_KEY, []),
                f"{where}.{_PRACTICE_ITEM_IDS_KEY}",
            )
            content[node_id] = parsed
        return content

    # -- DomainAdapter API ----------------------------------------------------

    @property
    def domain_version(self) -> str:
        return self._domain_version

    def knowledge_nodes(self) -> list[KnowledgeNode]:
        return list(self._nodes)

    def prerequisite_edges(self) -> list[PrerequisiteEdge]:
        return list(self._edges)

    def objectives(self) -> list[LearningObjective]:
        return list(self._objectives)

    def assessment_items(self, node_id: str | None = None) -> list[AssessmentItem]:
        if node_id is None:
            return list(self._items)
        if type(node_id) is not str or not node_id.strip():
            raise ValidationError("assessment_items(): node_id must be a non-blank string")
        if node_id not in {node.node_id for node in self._nodes}:
            raise NotFoundError(f"assessment_items(): unknown node_id {node_id!r}")
        return [item for item in self._items if node_id in item.node_ids]

    def teaching_content(self, node_id: str, kind: str) -> str:
        if type(node_id) is not str or not node_id.strip():
            raise ValidationError("teaching_content(): node_id must be a non-blank string")
        if type(kind) is not str:
            raise ValidationError("teaching_content(): kind must be a string")
        if kind not in TEACHING_CONTENT_KINDS:
            raise ValidationError(
                f"teaching_content(): unsupported kind {kind!r}; "
                f"supported kinds: {list(TEACHING_CONTENT_KINDS)}"
            )
        if node_id not in self._teaching_content:
            raise NotFoundError(f"teaching_content(): no content for node {node_id!r}")
        templates = self._teaching_content[node_id]
        if kind == "PRACTICE":
            return json.dumps(
                templates[_PRACTICE_ITEM_IDS_KEY], ensure_ascii=False, separators=(",", ":")
            )
        return templates[kind]

    def validate(self) -> None:
        """Cross-file consistency validation (fail-closed, deterministic)."""

        graph = self._graph
        assert graph is not None  # set by _load()
        node_ids = set(graph.nodes_by_id())

        objective_ids: set[str] = set()
        for objective in self._objectives:
            if objective.objective_id in objective_ids:
                raise ValidationError(
                    f"objectives.json: duplicate objective_id {objective.objective_id!r}"
                )
            objective_ids.add(objective.objective_id)
            graph.validate_objective(objective)

        item_ids: set[str] = set()
        for item in self._items:
            if item.item_id in item_ids:
                raise ValidationError(
                    f"assessment_items.json: duplicate item_id {item.item_id!r}"
                )
            item_ids.add(item.item_id)
            unknown = [node_id for node_id in item.node_ids if node_id not in node_ids]
            if unknown:
                raise ValidationError(
                    f"assessment_items.json: item {item.item_id!r} references unknown "
                    f"node(s): {unknown}"
                )
            if item.item_type == "MCQ" and len(item.options) < 2:
                raise ValidationError(
                    f"assessment_items.json: MCQ item {item.item_id!r} needs >= 2 options"
                )
            if item.item_type == "CODE" and not item.function_name:
                raise ValidationError(
                    f"assessment_items.json: CODE item {item.item_id!r} needs function_name"
                )
            if item.item_type != "CODE" and item.function_name is not None:
                raise ValidationError(
                    f"assessment_items.json: item {item.item_id!r} is {item.item_type} but "
                    "declares function_name (CODE-only field)"
                )
            if not item.max_score > 0.0:
                raise ValidationError(
                    f"assessment_items.json: item {item.item_id!r} needs max_score > 0"
                )

        content_nodes = set(self._teaching_content)
        missing = sorted(node_ids - content_nodes)
        if missing:
            raise ValidationError(
                f"teaching_content.json: missing teaching content for node(s): {missing}"
            )
        unknown_content = sorted(content_nodes - node_ids)
        if unknown_content:
            raise ValidationError(
                f"teaching_content.json: content for unknown node(s): {unknown_content}"
            )
        if not self._nodes:
            raise ValidationError("knowledge_graph.json: domain must declare at least one node")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"CFBinarySearchDomainAdapter(domain_id={self.domain_id!r}, "
            f"domain_version={self.domain_version!r}, nodes={len(self._nodes)}, "
            f"items={len(self._items)})"
        )


def default_fixtures_root() -> Path:
    """Default ``fixtures/m1_teacher`` root (overridable via ``M1_TEACHER_FIXTURES``)."""

    env_value = os.environ.get(FIXTURES_ENV_VAR)
    if env_value:
        return Path(env_value).expanduser().resolve()
    return Path(DEFAULT_FIXTURES_ROOT)


def build_default_registry(fixtures_root: str | Path | None = None) -> DomainRegistry:
    """Build a :class:`DomainRegistry` with the CF binary-search domain loaded.

    ``fixtures_root`` defaults to ``$M1_TEACHER_FIXTURES`` when set, otherwise
    ``<repo>/fixtures/m1_teacher``.  The adapter is validated before it is
    registered so an invalid fixture tree fails fast.
    """

    root = fixtures_root if fixtures_root is not None else default_fixtures_root()
    adapter = CFBinarySearchDomainAdapter(root)
    adapter.validate()
    registry = DomainRegistry()
    registry.register(adapter)
    return registry
