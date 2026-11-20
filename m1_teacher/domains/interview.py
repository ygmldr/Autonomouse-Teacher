"""Teacher-visible Interview domain adapter for the M1-B vertical layer (B-PR4).

Scope and boundaries
--------------------
* Implements the frozen :class:`m1_teacher.contracts.domain.DomainAdapter`
  contract only with **teacher-visible** data: knowledge nodes, prerequisite
  edges, objectives, assessment-item metadata, teaching content and the
  five-stage follow-up probe ladder.
* Loads exactly one allow-listed fixture file (``questions.json``) from
  ``<fixtures_root>/vertical/interview/``.  Hidden rubric/answer material lives
  in a separate scorer-only tree that this module never opens, never enumerates
  and never references: the ``scoring_spec_ref`` value on a
  :class:`~m1_teacher.contracts.types.AssessmentItem` stays an opaque relative
  reference consumed only by the scorer-side interview judge.
* Read-only and deterministic: no learner/session/event writes, no repository,
  no network, no clock reads (fixtures carry a fixed ``converted_at`` timestamp
  that is re-used for record ``created_at`` so serialisation round-trips are
  byte-stable).
* The five-stage follow-up ladder (concept -> hypothesis -> complexity ->
  experiment_design -> online_triage) is *teaching content*, not a hint rung and
  not scoring material; it is exposed through the additive
  :meth:`InterviewDomainAdapter.follow_up_ladder` method without changing the
  frozen ``DomainAdapter`` protocol.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from ..contracts.domain import DomainAdapter, DomainRegistry
from ..contracts.errors import NotFoundError, ValidationError
from ..contracts.types import (
    AssessmentItem,
    KnowledgeNode,
    LearningObjective,
    PrerequisiteEdge,
)
from ..knowledge.graph import KnowledgeGraph

__all__ = [
    "DOMAIN_ID",
    "DEFAULT_DOMAIN_VERSION",
    "FIXTURE_CREATED_AT",
    "FOLLOW_UP_STAGES",
    "STAGE_LABELS",
    "FollowUpProbe",
    "InterviewDomainAdapter",
    "build_interview_registry",
    "default_fixtures_root",
]

DOMAIN_ID = "interview_coach"
DEFAULT_DOMAIN_VERSION = "0.1.0"
SCHEMA_VERSION = "m1a.v0"
FIXTURE_CREATED_AT = "2026-11-20T00:00:00Z"
FIXTURES_ENV_VAR = "M1_TEACHER_FIXTURES"
DEFAULT_FIXTURES_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "m1_teacher"

#: Allow-listed teacher-visible fixture file (hidden material is never listed).
_ALLOWED_FILES = frozenset({"questions.json"})
_DOMAIN_SUBDIR = Path("vertical") / "interview"

FOLLOW_UP_STAGES: tuple[str, ...] = (
    "concept",
    "hypothesis",
    "complexity",
    "experiment_design",
    "online_triage",
)
STAGE_LABELS: dict[str, str] = {
    "concept": "概念澄清",
    "hypothesis": "可证伪假设",
    "complexity": "复杂度与量级",
    "experiment_design": "实验设计",
    "online_triage": "线上定位",
}
TEACHING_CONTENT_KINDS = frozenset({"EXPLAIN", "HINT_L1", "HINT_L2", "HINT_L3", "REVIEW", "PRACTICE"})
_ITEM_TYPE = "SHORT_ANSWER"
_ASSESSMENT_MODE = "RULE_RUBRIC"
_OPAQUE_SPEC_REF_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\.json$")
_ALLOWED_ITEM_TYPES = frozenset({"MCQ", "CODE", "SHORT_ANSWER"})
_ALLOWED_ASSESSMENT_MODES = frozenset(
    {"DETERMINISTIC_JUDGE", "RULE_RUBRIC", "HUMAN_REVIEW_REQUIRED"}
)


# ---------------------------------------------------------------------------
# Small strict validators (fail closed; mirrors the CF adapter fixture style)
# ---------------------------------------------------------------------------


def _expect_mapping(value: Any, where: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise ValidationError(f"{where}: expected an object, got {type(value).__name__}")
    return value


def _expect_list(value: Any, where: str, *, min_length: int = 0) -> list[Any]:
    if type(value) is not list:
        raise ValidationError(f"{where}: expected a list, got {type(value).__name__}")
    if len(value) < min_length:
        raise ValidationError(f"{where}: expected at least {min_length} element(s)")
    return value


def _expect_str(value: Any, where: str, *, allow_empty: bool = False) -> str:
    if type(value) is not str:
        raise ValidationError(f"{where}: expected str, got {type(value).__name__}")
    if not allow_empty and not value.strip():
        raise ValidationError(f"{where}: expected a non-blank string")
    return value


def _expect_int(value: Any, where: str, *, minimum: int | None = None, maximum: int | None = None) -> int:
    if type(value) is not int:
        raise ValidationError(f"{where}: expected int, got {type(value).__name__}")
    if minimum is not None and value < minimum:
        raise ValidationError(f"{where}: expected >= {minimum}, got {value}")
    if maximum is not None and value > maximum:
        raise ValidationError(f"{where}: expected <= {maximum}, got {value}")
    return value


def _expect_number(
    value: Any, where: str, *, minimum: float | None = None, maximum: float | None = None
) -> float:
    if type(value) not in (int, float):
        raise ValidationError(f"{where}: expected a number, got {type(value).__name__}")
    number = float(value)
    if minimum is not None and number < minimum:
        raise ValidationError(f"{where}: expected >= {minimum}, got {number}")
    if maximum is not None and number > maximum:
        raise ValidationError(f"{where}: expected <= {maximum}, got {number}")
    return number


def _expect_bool(value: Any, where: str) -> bool:
    if type(value) is not bool:
        raise ValidationError(f"{where}: expected bool, got {type(value).__name__}")
    return value


def _expect_str_list(value: Any, where: str, *, min_length: int = 0) -> list[str]:
    items = _expect_list(value, where, min_length=min_length)
    return [_expect_str(item, f"{where}[{index}]") for index, item in enumerate(items)]


def _reject_unknown_keys(mapping: Mapping[str, Any], allowed: frozenset[str], where: str) -> None:
    unknown = sorted(repr(key) for key in mapping if key not in allowed)
    if unknown:
        raise ValidationError(f"{where}: unknown key(s): {', '.join(unknown)}")


def _require_schema(payload: Mapping[str, Any], filename: str) -> None:
    schema = payload.get("schema_version")
    if schema != SCHEMA_VERSION:
        raise ValidationError(
            f"{filename}: schema_version must be {SCHEMA_VERSION!r}, got {schema!r}"
        )


def _resolve_domain_dir(fixtures_root: Path) -> Path:
    nested = fixtures_root / _DOMAIN_SUBDIR
    if nested.is_dir():
        return nested
    if (fixtures_root / "questions.json").is_file():
        return fixtures_root
    raise NotFoundError(f"interview fixture directory not found under {fixtures_root}")


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


def default_fixtures_root() -> Path:
    """Default ``fixtures/m1_teacher`` root (overridable via ``M1_TEACHER_FIXTURES``)."""

    env_value = os.environ.get(FIXTURES_ENV_VAR)
    if env_value:
        return Path(env_value).expanduser().resolve()
    return Path(DEFAULT_FIXTURES_ROOT)


# ---------------------------------------------------------------------------
# Additive teacher-visible value object (not part of the frozen contract)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FollowUpProbe:
    """One teacher-visible Socratic follow-up prompt of the five-stage ladder."""

    stage: str
    label: str
    prompt: str

    def to_dict(self) -> dict[str, str]:
        return {"stage": self.stage, "label": self.label, "prompt": self.prompt}


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class InterviewDomainAdapter:
    """Teacher-visible adapter for the synthetic interview vertical domain.

    ``domain_id`` is ``interview_coach``; ``domain_version`` comes from the
    fixture and is recorded in plans/sessions by the caller.  The class is
    intentionally constructible without any learner/session/scorer dependency.
    """

    domain_id: str = DOMAIN_ID

    def __init__(self, fixtures_root: str | Path | None = None) -> None:
        root = fixtures_root if fixtures_root is not None else default_fixtures_root()
        self._fixtures_root = _coerce_fixtures_root(root)
        self._domain_dir = _resolve_domain_dir(self._fixtures_root)
        self._nodes: list[KnowledgeNode] = []
        self._edges: list[PrerequisiteEdge] = []
        self._objectives: list[LearningObjective] = []
        self._items: list[AssessmentItem] = []
        self._teaching_content: dict[str, dict[str, Any]] = {}
        self._question_meta: dict[str, dict[str, Any]] = {}
        self._follow_up_ladders: dict[str, list[FollowUpProbe]] = {}
        self._domain_version: str = DEFAULT_DOMAIN_VERSION
        self._graph: KnowledgeGraph | None = None
        self._load()

    # -- properties --------------------------------------------------------
    @property
    def domain_version(self) -> str:
        return self._domain_version

    @property
    def fixtures_root(self) -> Path:
        return self._fixtures_root

    # -- loading ------------------------------------------------------------
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
        payload = self._load_json("questions.json")
        _reject_unknown_keys(
            payload,
            frozenset(
                {
                    "schema_version",
                    "domain_id",
                    "domain_version",
                    "provenance",
                    "nodes",
                    "edges",
                    "objectives",
                    "teaching",
                    "questions",
                }
            ),
            "questions.json",
        )
        _require_schema(payload, "questions.json")
        domain_id = _expect_str(payload.get("domain_id"), "questions.json.domain_id")
        if domain_id != DOMAIN_ID:
            raise ValidationError(
                f"questions.json.domain_id must be {DOMAIN_ID!r}, got {domain_id!r}"
            )
        self._domain_version = _expect_str(
            payload.get("domain_version"), "questions.json.domain_version"
        )
        provenance = _expect_mapping(payload.get("provenance"), "questions.json.provenance")
        if provenance.get("synthetic") is not True:
            raise ValidationError("questions.json.provenance.synthetic must be True")
        if provenance.get("license") != "CC0-1.0":
            raise ValidationError("questions.json.provenance.license must be 'CC0-1.0'")

        self._load_nodes(_expect_list(payload.get("nodes"), "questions.json.nodes", min_length=1))
        self._load_edges(_expect_list(payload.get("edges"), "questions.json.edges"))
        self._load_objectives(
            _expect_list(payload.get("objectives"), "questions.json.objectives", min_length=1)
        )
        self._load_teaching(_expect_mapping(payload.get("teaching"), "questions.json.teaching"))
        self._load_questions(
            _expect_list(payload.get("questions"), "questions.json.questions", min_length=1)
        )
        self._graph = KnowledgeGraph(self._nodes, self._edges)

    def _load_nodes(self, raw_nodes: list[Any]) -> None:
        nodes: list[KnowledgeNode] = []
        node_ids: set[str] = set()
        for index, raw in enumerate(raw_nodes):
            where = f"questions.json.nodes[{index}]"
            entry = _expect_mapping(raw, where)
            _reject_unknown_keys(
                entry,
                frozenset(
                    {
                        "node_id",
                        "title",
                        "description",
                        "difficulty",
                        "assessment_mode",
                        "tags",
                        "content_ref",
                    }
                ),
                where,
            )
            node_id = _expect_str(entry.get("node_id"), f"{where}.node_id")
            if node_id in node_ids:
                raise ValidationError(f"{where}: duplicate node_id {node_id!r}")
            node_ids.add(node_id)
            assessment_mode = _expect_str(entry.get("assessment_mode"), f"{where}.assessment_mode")
            if assessment_mode not in _ALLOWED_ASSESSMENT_MODES:
                raise ValidationError(
                    f"{where}.assessment_mode {assessment_mode!r} is not one of "
                    f"{sorted(_ALLOWED_ASSESSMENT_MODES)}"
                )
            nodes.append(
                KnowledgeNode(
                    node_id=node_id,
                    domain_id=DOMAIN_ID,
                    title=_expect_str(entry.get("title"), f"{where}.title"),
                    description=_expect_str(entry.get("description"), f"{where}.description"),
                    difficulty=_expect_int(
                        entry.get("difficulty"), f"{where}.difficulty", minimum=1, maximum=5
                    ),
                    assessment_mode=assessment_mode,
                    tags=_expect_str_list(entry.get("tags", []), f"{where}.tags"),
                    content_ref=_expect_str(
                        entry.get("content_ref", ""), f"{where}.content_ref", allow_empty=True
                    ),
                    created_at=FIXTURE_CREATED_AT,
                )
            )
        self._nodes = nodes

    def _load_edges(self, raw_edges: list[Any]) -> None:
        edges: list[PrerequisiteEdge] = []
        for index, raw in enumerate(raw_edges):
            where = f"questions.json.edges[{index}]"
            entry = _expect_mapping(raw, where)
            _reject_unknown_keys(
                entry,
                frozenset({"source_node_id", "target_node_id", "kind", "weight"}),
                where,
            )
            kind = _expect_str(entry.get("kind"), f"{where}.kind")
            if kind not in ("HARD", "SOFT"):
                raise ValidationError(f"{where}.kind {kind!r} must be HARD or SOFT")
            edges.append(
                PrerequisiteEdge(
                    source_node_id=_expect_str(
                        entry.get("source_node_id"), f"{where}.source_node_id"
                    ),
                    target_node_id=_expect_str(
                        entry.get("target_node_id"), f"{where}.target_node_id"
                    ),
                    kind=kind,
                    weight=_expect_number(entry.get("weight", 1.0), f"{where}.weight", minimum=0.0, maximum=1.0),
                    created_at=FIXTURE_CREATED_AT,
                )
            )
        self._edges = edges

    def _load_objectives(self, raw_objectives: list[Any]) -> None:
        objectives: list[LearningObjective] = []
        seen: set[str] = set()
        for index, raw in enumerate(raw_objectives):
            where = f"questions.json.objectives[{index}]"
            entry = _expect_mapping(raw, where)
            _reject_unknown_keys(
                entry,
                frozenset(
                    {
                        "objective_id",
                        "title",
                        "description",
                        "target_node_ids",
                        "success_criteria",
                        "estimated_minutes",
                    }
                ),
                where,
            )
            objective_id = _expect_str(entry.get("objective_id"), f"{where}.objective_id")
            if objective_id in seen:
                raise ValidationError(f"{where}: duplicate objective_id {objective_id!r}")
            seen.add(objective_id)
            objectives.append(
                LearningObjective(
                    objective_id=objective_id,
                    domain_id=DOMAIN_ID,
                    title=_expect_str(entry.get("title"), f"{where}.title"),
                    description=_expect_str(entry.get("description"), f"{where}.description"),
                    target_node_ids=_expect_str_list(
                        entry.get("target_node_ids"), f"{where}.target_node_ids", min_length=1
                    ),
                    success_criteria=_expect_mapping(
                        entry.get("success_criteria"), f"{where}.success_criteria"
                    ),
                    estimated_minutes=_expect_int(
                        entry.get("estimated_minutes", 120),
                        f"{where}.estimated_minutes",
                        minimum=0,
                    ),
                    created_at=FIXTURE_CREATED_AT,
                )
            )
        self._objectives = objectives

    def _load_teaching(self, raw_teaching: dict[str, Any]) -> None:
        teaching: dict[str, dict[str, Any]] = {}
        for node_id, raw in raw_teaching.items():
            where = f"questions.json.teaching[{node_id!r}]"
            node_id = _expect_str(node_id, f"{where}.node_id")
            entry = _expect_mapping(raw, where)
            _reject_unknown_keys(
                entry,
                frozenset({"EXPLAIN", "HINT_L1", "HINT_L2", "HINT_L3", "REVIEW"}),
                where,
            )
            teaching[node_id] = {
                kind: _expect_str(entry.get(kind), f"{where}.{kind}")
                for kind in ("EXPLAIN", "HINT_L1", "HINT_L2", "HINT_L3", "REVIEW")
            }
        self._teaching_content = teaching

    def _load_questions(self, raw_questions: list[Any]) -> None:
        items: list[AssessmentItem] = []
        node_ids = {node.node_id for node in self._nodes}
        item_ids: set[str] = set()
        question_meta: dict[str, dict[str, Any]] = {}
        ladders: dict[str, list[FollowUpProbe]] = {}
        for index, raw in enumerate(raw_questions):
            where = f"questions.json.questions[{index}]"
            entry = _expect_mapping(raw, where)
            _reject_unknown_keys(
                entry,
                frozenset(
                    {
                        "question_id",
                        "item_id",
                        "track",
                        "topic",
                        "node_ids",
                        "item_type",
                        "difficulty",
                        "prompt",
                        "options",
                        "function_name",
                        "max_score",
                        "deterministic",
                        "assessment_mode",
                        "scoring_spec_ref",
                        "requires_project_facts",
                        "follow_up_ladder",
                        "synthetic",
                        "license",
                    }
                ),
                where,
            )
            question_id = _expect_str(entry.get("question_id"), f"{where}.question_id")
            item_id = _expect_str(entry.get("item_id"), f"{where}.item_id")
            if item_id in item_ids:
                raise ValidationError(f"{where}: duplicate item_id {item_id!r}")
            item_ids.add(item_id)
            item_node_ids = _expect_str_list(entry.get("node_ids"), f"{where}.node_ids", min_length=1)
            unknown_nodes = sorted(set(item_node_ids) - node_ids)
            if unknown_nodes:
                raise ValidationError(f"{where}.node_ids: unknown node(s): {unknown_nodes}")
            item_type = _expect_str(entry.get("item_type"), f"{where}.item_type")
            if item_type not in _ALLOWED_ITEM_TYPES:
                raise ValidationError(
                    f"{where}.item_type {item_type!r} is not one of {sorted(_ALLOWED_ITEM_TYPES)}"
                )
            assessment_mode = _expect_str(entry.get("assessment_mode"), f"{where}.assessment_mode")
            if assessment_mode not in _ALLOWED_ASSESSMENT_MODES:
                raise ValidationError(
                    f"{where}.assessment_mode {assessment_mode!r} is not allowed"
                )
            scoring_ref = _expect_str(entry.get("scoring_spec_ref"), f"{where}.scoring_spec_ref")
            if not _OPAQUE_SPEC_REF_RE.match(scoring_ref) or ".." in scoring_ref:
                raise ValidationError(
                    f"{where}.scoring_spec_ref must be an opaque relative scoring reference"
                )
            if entry.get("synthetic") is not True:
                raise ValidationError(f"{where}.synthetic must be True")
            if entry.get("license") != "CC0-1.0":
                raise ValidationError(f"{where}.license must be 'CC0-1.0'")
            ladder = self._load_ladder(entry.get("follow_up_ladder"), f"{where}.follow_up_ladder")
            requires_project_facts = _expect_bool(
                entry.get("requires_project_facts"), f"{where}.requires_project_facts"
            )
            items.append(
                AssessmentItem(
                    item_id=item_id,
                    domain_id=DOMAIN_ID,
                    node_ids=item_node_ids,
                    item_type=item_type,
                    difficulty=_expect_int(
                        entry.get("difficulty"), f"{where}.difficulty", minimum=1, maximum=5
                    ),
                    prompt=_expect_str(entry.get("prompt"), f"{where}.prompt"),
                    options=_expect_str_list(entry.get("options", []), f"{where}.options"),
                    function_name=entry.get("function_name"),
                    max_score=_expect_number(
                        entry.get("max_score", 1.0), f"{where}.max_score", minimum=0.0
                    ),
                    deterministic=_expect_bool(
                        entry.get("deterministic"), f"{where}.deterministic"
                    ),
                    scoring_spec_ref=scoring_ref,
                    created_at=FIXTURE_CREATED_AT,
                )
            )
            question_meta[item_id] = {
                "question_id": question_id,
                "track": _expect_str(entry.get("track"), f"{where}.track"),
                "topic": _expect_str(entry.get("topic"), f"{where}.topic"),
                "requires_project_facts": requires_project_facts,
            }
            ladders[item_id] = ladder
        self._items = items
        self._question_meta = question_meta
        self._follow_up_ladders = ladders

    @staticmethod
    def _load_ladder(raw: Any, where: str) -> list[FollowUpProbe]:
        entries = _expect_list(raw, where, min_length=len(FOLLOW_UP_STAGES))
        if len(entries) != len(FOLLOW_UP_STAGES):
            raise ValidationError(
                f"{where}: expected exactly {len(FOLLOW_UP_STAGES)} stages, got {len(entries)}"
            )
        probes: list[FollowUpProbe] = []
        for index, (raw_entry, expected_stage) in enumerate(zip(entries, FOLLOW_UP_STAGES)):
            entry_where = f"{where}[{index}]"
            entry = _expect_mapping(raw_entry, entry_where)
            _reject_unknown_keys(entry, frozenset({"stage", "label", "prompt"}), entry_where)
            stage = _expect_str(entry.get("stage"), f"{entry_where}.stage")
            if stage != expected_stage:
                raise ValidationError(
                    f"{entry_where}.stage must be {expected_stage!r} at position {index}, "
                    f"got {stage!r}"
                )
            label = _expect_str(entry.get("label"), f"{entry_where}.label")
            probes.append(
                FollowUpProbe(
                    stage=stage,
                    label=label,
                    prompt=_expect_str(entry.get("prompt"), f"{entry_where}.prompt"),
                )
            )
        return probes

    # -- DomainAdapter read API ---------------------------------------------
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
        known = {node.node_id for node in self._nodes}
        if node_id not in known:
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
                f"supported kinds: {sorted(TEACHING_CONTENT_KINDS)}"
            )
        if node_id not in self._teaching_content:
            raise NotFoundError(f"teaching_content(): no content for node {node_id!r}")
        if kind == "PRACTICE":
            item_ids = [
                item.item_id for item in self._items if node_id in item.node_ids
            ]
            return json.dumps(item_ids, ensure_ascii=False, separators=(",", ":"))
        return self._teaching_content[node_id][kind]

    def validate(self) -> None:
        """Cross-file consistency validation (fail-closed, deterministic)."""

        graph = self._graph
        assert graph is not None  # set by _load()
        node_ids = set(graph.nodes_by_id())
        if not self._nodes:
            raise ValidationError("questions.json: at least one knowledge node is required")
        if not self._items:
            raise ValidationError("questions.json: at least one assessment item is required")
        for objective in self._objectives:
            graph.validate_objective(objective)
        for node_id in self._teaching_content:
            if node_id not in node_ids:
                raise ValidationError(
                    f"questions.json.teaching: unknown node_id {node_id!r}"
                )
        for node_id in node_ids:
            if node_id not in self._teaching_content:
                raise ValidationError(
                    f"questions.json.teaching: missing teaching content for node {node_id!r}"
                )
            for kind in ("EXPLAIN", "HINT_L1", "HINT_L2", "HINT_L3", "REVIEW"):
                if not self._teaching_content[node_id][kind].strip():
                    raise ValidationError(
                        f"questions.json.teaching[{node_id!r}].{kind}: must not be blank"
                    )
        for item in self._items:
            for node_id in item.node_ids:
                if node_id not in node_ids:
                    raise ValidationError(
                        f"questions.json.questions[{item.item_id!r}]: unknown node {node_id!r}"
                    )
            if item.item_id not in self._follow_up_ladders:
                raise ValidationError(
                    f"questions.json.questions[{item.item_id!r}]: missing follow-up ladder"
                )
        covered_nodes = {node_id for item in self._items for node_id in item.node_ids}
        if covered_nodes != node_ids:  # pragma: no cover - fixtures cover all tracks
            raise ValidationError(
                f"questions.json: nodes without items: {sorted(node_ids - covered_nodes)}"
            )

    # -- additive teacher-visible helpers (not part of the frozen protocol) ---
    def follow_up_ladder(self, item_id: str) -> list[FollowUpProbe]:
        """Return the five teacher-visible Socratic probes for an interview item."""

        if type(item_id) is not str or not item_id.strip():
            raise ValidationError("follow_up_ladder(): item_id must be a non-blank string")
        try:
            return list(self._follow_up_ladders[item_id])
        except KeyError:
            raise NotFoundError(f"follow_up_ladder(): unknown item_id {item_id!r}") from None

    def requires_project_facts(self, item_id: str) -> bool:
        """Whether the item requires learner-owned, verifiable project facts."""

        return self.question_metadata(item_id)["requires_project_facts"]

    def question_metadata(self, item_id: str) -> dict[str, Any]:
        """Teacher-visible question metadata (track/topic/project-fact boundary only)."""

        if type(item_id) is not str or not item_id.strip():
            raise ValidationError("question_metadata(): item_id must be a non-blank string")
        try:
            return dict(self._question_meta[item_id])
        except KeyError:
            raise NotFoundError(f"question_metadata(): unknown item_id {item_id!r}") from None

    # -- introspection ------------------------------------------------------
    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"InterviewDomainAdapter(domain_id={self.domain_id!r}, "
            f"domain_version={self._domain_version!r}, nodes={len(self._nodes)}, "
            f"items={len(self._items)})"
        )


def build_interview_registry(fixtures_root: str | Path | None = None) -> DomainRegistry:
    """Build a :class:`DomainRegistry` containing only the validated interview domain."""

    adapter = InterviewDomainAdapter(fixtures_root)
    adapter.validate()
    registry = DomainRegistry()
    registry.register(adapter)
    return registry


# Explicitly keep the frozen protocol importable from this module for structural
# checks/tests without duplicating its definition.
_ = DomainAdapter
