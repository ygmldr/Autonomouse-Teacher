"""M1 Offline Teacher -- shared type contract (schema version ``m1.offline.v0``).

This module is the single source of truth for the data contract shared by every
M1 Offline Teacher module (Teacher Core, CF Teacher, Interview Coach/Freshness,
Evaluation/closure, demo).  Rules enforced here:

* Every record derives from :class:`Record`, carries ``schema_version`` and
  supports lossless JSON round-trips via ``to_dict()`` / ``from_dict()`` (and
  the ``to_json()`` / ``from_json()`` convenience wrappers).
* Field names are constructor parameter names, in the order of the shared
  contract.  Defaults shown in the contract may be omitted at construction.
* Enum-like values are plain upper-case strings, validated against the
  documented value sets below.  Invalid values fail closed with
  :class:`SchemaError` (a ``ValueError``).
* ``from_dict`` is strict: unknown keys and schema-version mismatches are
  rejected instead of silently ignored.
* Time fields default to :func:`now_utc` (UTC ISO-8601, ``YYYY-MM-DDTHH:MM:SSZ``);
  timestamps supplied explicitly are preserved verbatim so replay is
  deterministic.

Adding fields is allowed (documented in ``docs/m1/TEACHER_CORE_ARCHITECTURE.md``)
but existing fields must never be removed or renamed without a schema bump.
"""

from __future__ import annotations

import dataclasses
import json
import types as pytypes
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, ClassVar, Union, get_args, get_origin, get_type_hints

SCHEMA_VERSION = "m1.offline.v0"

# ---------------------------------------------------------------------------
# Enum-like value sets (upper-case strings; validated on construction)
# ---------------------------------------------------------------------------
CLAIM_STATUS_VALUES = ("VERIFIED", "REPORTED", "CONFLICT", "EXPIRED", "UNKNOWN")
CHANGE_KIND_VALUES = ("KEEP", "RECHECK", "UPDATE")
BASELINE_LEVEL_VALUES = ("BEGINNER", "INTERMEDIATE", "ADVANCED")
EVIDENCE_KIND_VALUES = (
    "ANSWER",
    "CODE_SUBMISSION",
    "EXPLANATION",
    "INTERVIEW_RESPONSE",
    "ASSESSMENT",
    "HINT_REQUEST",
)
TASK_TYPE_VALUES = ("CF_PROBLEM", "INTERVIEW_QUESTION", "REVIEW", "READING")
TEACHER_ACTION_KIND_VALUES = (
    "LIGHT_HINT",
    "INVARIANT_HINT",
    "STRUCTURE_HINT",
    "FULL_SOLUTION",
    "SOCRATIC_QUESTION",
    "EXPLAIN",
    "PRACTICE",
    "REVIEW",
    "ASK_CLARIFICATION",
)
DIAGNOSTIC_STATUS_VALUES = ("RESOLVED", "UNKNOWN", "NEEDS_REVIEW")

CLAIM_STATUS_SET = frozenset(CLAIM_STATUS_VALUES)
CHANGE_KIND_SET = frozenset(CHANGE_KIND_VALUES)
BASELINE_LEVEL_SET = frozenset(BASELINE_LEVEL_VALUES)
EVIDENCE_KIND_SET = frozenset(EVIDENCE_KIND_VALUES)
TASK_TYPE_SET = frozenset(TASK_TYPE_VALUES)
TEACHER_ACTION_KIND_SET = frozenset(TEACHER_ACTION_KIND_VALUES)
DIAGNOSTIC_STATUS_SET = frozenset(DIAGNOSTIC_STATUS_VALUES)

# Hint ladder: lowest intervention first; FULL_SOLUTION is the last resort and
# must never be emitted by default (see ``teaching_policy``).
HINT_LADDER = ("LIGHT_HINT", "INVARIANT_HINT", "STRUCTURE_HINT", "FULL_SOLUTION")
HINT_LEVEL_MIN = 1
HINT_LEVEL_MAX = len(HINT_LADDER)


class SchemaError(ValueError):
    """Raised when a record violates the shared M1 schema contract."""


# ---------------------------------------------------------------------------
# Clock
# ---------------------------------------------------------------------------
def now_utc() -> str:
    """Return the current UTC time as an ISO-8601 string, second precision.

    Format: ``YYYY-MM-DDTHH:MM:SSZ`` -- deterministic shape (no microseconds),
    timezone-aware by construction.  Injected/frozen timestamps are preserved
    by the records so tests can replay deterministically.
    """

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------
def _fail(owner: str, message: str) -> "SchemaError":
    return SchemaError(f"{owner}: {message}")


def _as_str(owner: str, name: str, value: Any, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise _fail(owner, f"{name} must be str, got {type(value).__name__}")
    if not allow_empty and not value.strip():
        raise _fail(owner, f"{name} must be a non-empty str")
    return value


def _as_bool(owner: str, name: str, value: Any) -> bool:
    if not isinstance(value, bool):
        raise _fail(owner, f"{name} must be bool, got {type(value).__name__}")
    return value


def _as_int(owner: str, name: str, value: Any, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise _fail(owner, f"{name} must be int, got {type(value).__name__}")
    if minimum is not None and value < minimum:
        raise _fail(owner, f"{name} must be >= {minimum}, got {value}")
    return value


def _as_float01(owner: str, name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _fail(owner, f"{name} must be a number, got {type(value).__name__}")
    number = float(value)
    if not 0.0 <= number <= 1.0:
        raise _fail(owner, f"{name} must be within [0, 1], got {number}")
    return number


def _as_str_list(owner: str, name: str, value: Any) -> list[str]:
    if not isinstance(value, list):
        raise _fail(owner, f"{name} must be list[str], got {type(value).__name__}")
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise _fail(owner, f"{name}[{index}] must be a non-empty str")
    return list(value)


def _as_dict(owner: str, name: str, value: Any) -> dict:
    if not isinstance(value, dict):
        raise _fail(owner, f"{name} must be dict, got {type(value).__name__}")
    return dict(value)


def _as_enum(owner: str, name: str, value: Any, allowed: tuple[str, ...]) -> str:
    if not isinstance(value, str):
        raise _fail(owner, f"{name} must be str, got {type(value).__name__}")
    if value not in allowed:
        raise _fail(owner, f"{name}={value!r} is not one of {allowed}")
    return value


def _as_mastery(owner: str, name: str, value: Any) -> dict[str, float]:
    raw = _as_dict(owner, name, value)
    normalized: dict[str, float] = {}
    for key, item in raw.items():
        if not isinstance(key, str) or not key.strip():
            raise _fail(owner, f"{name} keys must be non-empty str")
        normalized[key] = _as_float01(owner, f"{name}[{key!r}]", item)
    return normalized


def _as_counts(owner: str, name: str, value: Any) -> dict[str, int]:
    raw = _as_dict(owner, name, value)
    normalized: dict[str, int] = {}
    for key, item in raw.items():
        if not isinstance(key, str) or not key.strip():
            raise _fail(owner, f"{name} keys must be non-empty str")
        normalized[key] = _as_int(owner, f"{name}[{key!r}]", item, minimum=0)
    return normalized


# ---------------------------------------------------------------------------
# JSON (de)serialization plumbing
# ---------------------------------------------------------------------------
def _to_jsonable(value: Any) -> Any:
    if isinstance(value, Record):
        return value.to_dict()
    if isinstance(value, dict):
        return {key: _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value


def _from_jsonable(value: Any, hint: Any, owner: str) -> Any:
    """Convert a JSON value back to the declared annotation ``hint``."""

    origin = get_origin(hint)
    args = get_args(hint)

    if origin in (Union, pytypes.UnionType):
        non_none = [arg for arg in args if arg is not type(None)]
        optional = len(non_none) != len(args)
        if value is None:
            if optional:
                return None
            raise _fail(owner, f"null is not allowed for {hint!r}")
        if len(non_none) == 1:
            return _from_jsonable(value, non_none[0], owner)
        return value

    if hint is Any or hint is object:
        return value
    if hint is None or hint is type(None):
        if value is not None:
            raise _fail(owner, f"expected null, got {type(value).__name__}")
        return None
    if isinstance(hint, type) and issubclass(hint, Record):
        if not isinstance(value, dict):
            raise _fail(owner, f"expected object for {hint.__name__}, got {type(value).__name__}")
        return hint.from_dict(value)
    if origin in (list, tuple):
        if not isinstance(value, list):
            raise _fail(owner, f"expected list, got {type(value).__name__}")
        item_hint = args[0] if args else Any
        return [_from_jsonable(item, item_hint, owner) for item in value]
    if origin is dict or hint is dict:
        if not isinstance(value, dict):
            raise _fail(owner, f"expected object, got {type(value).__name__}")
        value_hint = args[1] if len(args) > 1 else Any
        converted: dict[Any, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise _fail(owner, "object keys must be strings in JSON")
            converted[key] = _from_jsonable(item, value_hint, owner)
        return converted
    if hint is str:
        if not isinstance(value, str):
            raise _fail(owner, f"expected str, got {type(value).__name__}")
        return value
    if hint is bool:
        return _as_bool(owner, "value", value)
    if hint is int:
        return _as_int(owner, "value", value)
    if hint is float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise _fail(owner, f"expected number, got {type(value).__name__}")
        return float(value)
    return value


def _fill_time(owner: str, name: str, value: Any) -> str:
    """Return an explicit timestamp or fall back to :func:`now_utc`."""

    if value is None or value == "":
        return now_utc()
    return _as_str(owner, name, value)


# ---------------------------------------------------------------------------
# Record base
# ---------------------------------------------------------------------------
class Record:
    """Base class for every M1 schema record.

    ``schema_version`` is exposed as a read-only property and always serialized
    as the first key of ``to_dict()``.  Subclasses are dataclasses; they do not
    declare ``schema_version`` as a dataclass field so constructor signatures
    match the shared contract exactly.
    """

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION

    @property
    def schema_version(self) -> str:
        return SCHEMA_VERSION

    # -- serialization ------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"schema_version": self.schema_version}
        for data_field in dataclasses.fields(self):
            data[data_field.name] = _to_jsonable(getattr(self, data_field.name))
        return data

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Record":
        if not isinstance(data, dict):
            raise _fail(cls.__name__, f"from_dict expects dict, got {type(data).__name__}")
        version = data.get("schema_version")
        if version is not None and version != SCHEMA_VERSION:
            raise _fail(
                cls.__name__,
                f"schema_version mismatch: expected {SCHEMA_VERSION!r}, got {version!r}",
            )
        field_names = {item.name for item in dataclasses.fields(cls)}
        unknown = sorted(set(data) - field_names - {"schema_version"})
        if unknown:
            raise _fail(cls.__name__, f"unknown field(s): {unknown}")
        hints = get_type_hints(cls)
        kwargs: dict[str, Any] = {}
        for data_field in dataclasses.fields(cls):
            if data_field.name not in data:
                continue
            kwargs[data_field.name] = _from_jsonable(
                data[data_field.name], hints[data_field.name], f"{cls.__name__}.{data_field.name}"
            )
        try:
            return cls(**kwargs)
        except TypeError as exc:  # missing required field / bad signature
            raise _fail(cls.__name__, f"invalid record payload: {exc}") from exc

    @classmethod
    def from_json(cls, text: str) -> "Record":
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise _fail(cls.__name__, f"invalid JSON: {exc}") from exc
        return cls.from_dict(data)


# ---------------------------------------------------------------------------
# Records (field order == shared contract order)
# ---------------------------------------------------------------------------
@dataclass
class Provenance(Record):
    experiment_id: str
    source: str = ""
    created_at: str = ""

    def __post_init__(self) -> None:
        self.experiment_id = _as_str("Provenance", "experiment_id", self.experiment_id)
        self.source = _as_str("Provenance", "source", self.source, allow_empty=True)
        self.created_at = _fill_time("Provenance", "created_at", self.created_at)


@dataclass
class SkillNode(Record):
    skill_id: str
    name: str
    domain: str
    prerequisites: list[str] = field(default_factory=list)
    description: str = ""

    def __post_init__(self) -> None:
        self.skill_id = _as_str("SkillNode", "skill_id", self.skill_id)
        self.name = _as_str("SkillNode", "name", self.name)
        self.domain = _as_str("SkillNode", "domain", self.domain)
        self.prerequisites = _as_str_list("SkillNode", "prerequisites", self.prerequisites)
        self.description = _as_str(
            "SkillNode", "description", self.description, allow_empty=True
        )


@dataclass
class KnowledgeSource(Record):
    source_id: str
    uri: str
    publisher: str
    published_at: str
    observed_at: str
    valid_until: str | None = None
    confidence: float = 0.5
    claim_status: str = "UNKNOWN"

    def __post_init__(self) -> None:
        self.source_id = _as_str("KnowledgeSource", "source_id", self.source_id)
        self.uri = _as_str("KnowledgeSource", "uri", self.uri)
        self.publisher = _as_str("KnowledgeSource", "publisher", self.publisher)
        self.published_at = _as_str("KnowledgeSource", "published_at", self.published_at)
        self.observed_at = _as_str("KnowledgeSource", "observed_at", self.observed_at)
        if self.valid_until is not None:
            self.valid_until = _as_str("KnowledgeSource", "valid_until", self.valid_until)
        self.confidence = _as_float01("KnowledgeSource", "confidence", self.confidence)
        self.claim_status = _as_enum(
            "KnowledgeSource", "claim_status", self.claim_status, CLAIM_STATUS_VALUES
        )


@dataclass
class KnowledgeRevision(Record):
    revision_id: str
    source_id: str
    old_hash: str
    new_hash: str
    change_kind: str
    detected_at: str
    claim_status: str
    notes: str = ""

    def __post_init__(self) -> None:
        self.revision_id = _as_str("KnowledgeRevision", "revision_id", self.revision_id)
        self.source_id = _as_str("KnowledgeRevision", "source_id", self.source_id)
        self.old_hash = _as_str("KnowledgeRevision", "old_hash", self.old_hash)
        self.new_hash = _as_str("KnowledgeRevision", "new_hash", self.new_hash)
        self.change_kind = _as_enum(
            "KnowledgeRevision", "change_kind", self.change_kind, CHANGE_KIND_VALUES
        )
        self.detected_at = _as_str("KnowledgeRevision", "detected_at", self.detected_at)
        self.claim_status = _as_enum(
            "KnowledgeRevision", "claim_status", self.claim_status, CLAIM_STATUS_VALUES
        )
        self.notes = _as_str("KnowledgeRevision", "notes", self.notes, allow_empty=True)


@dataclass
class LearnerProfile(Record):
    learner_id: str
    display_name: str = ""
    baseline_level: str = "BEGINNER"
    created_at: str = ""

    def __post_init__(self) -> None:
        self.learner_id = _as_str("LearnerProfile", "learner_id", self.learner_id)
        self.display_name = _as_str(
            "LearnerProfile", "display_name", self.display_name, allow_empty=True
        )
        self.baseline_level = _as_enum(
            "LearnerProfile", "baseline_level", self.baseline_level, BASELINE_LEVEL_VALUES
        )
        self.created_at = _fill_time("LearnerProfile", "created_at", self.created_at)


@dataclass
class EvidenceEvent(Record):
    event_id: str
    learner_id: str
    task_id: str
    kind: str
    payload: dict
    observed_score: float | None = None
    error_codes: list[str] = field(default_factory=list)
    provenance: Provenance | None = None
    created_at: str = ""

    def __post_init__(self) -> None:
        self.event_id = _as_str("EvidenceEvent", "event_id", self.event_id)
        self.learner_id = _as_str("EvidenceEvent", "learner_id", self.learner_id)
        self.task_id = _as_str("EvidenceEvent", "task_id", self.task_id)
        self.kind = _as_enum("EvidenceEvent", "kind", self.kind, EVIDENCE_KIND_VALUES)
        self.payload = _as_dict("EvidenceEvent", "payload", self.payload)
        if self.observed_score is not None:
            self.observed_score = _as_float01(
                "EvidenceEvent", "observed_score", self.observed_score
            )
        self.error_codes = _as_str_list("EvidenceEvent", "error_codes", self.error_codes)
        if self.provenance is not None and not isinstance(self.provenance, Provenance):
            raise _fail("EvidenceEvent", "provenance must be Provenance | None")
        self.created_at = _fill_time("EvidenceEvent", "created_at", self.created_at)


@dataclass
class LearnerState(Record):
    learner_id: str
    mastery: dict[str, float]
    error_counts: dict[str, int]
    evidence_count: int
    updated_at: str = ""

    def __post_init__(self) -> None:
        self.learner_id = _as_str("LearnerState", "learner_id", self.learner_id)
        self.mastery = _as_mastery("LearnerState", "mastery", self.mastery)
        self.error_counts = _as_counts("LearnerState", "error_counts", self.error_counts)
        self.evidence_count = _as_int(
            "LearnerState", "evidence_count", self.evidence_count, minimum=0
        )
        self.updated_at = _fill_time("LearnerState", "updated_at", self.updated_at)


@dataclass
class LearningGoal(Record):
    goal_id: str
    learner_id: str
    target_skills: list[str]
    deadline_days: int | None = None
    weekly_minutes: int = 180

    def __post_init__(self) -> None:
        self.goal_id = _as_str("LearningGoal", "goal_id", self.goal_id)
        self.learner_id = _as_str("LearningGoal", "learner_id", self.learner_id)
        self.target_skills = _as_str_list("LearningGoal", "target_skills", self.target_skills)
        if not self.target_skills:
            raise _fail("LearningGoal", "target_skills must not be empty")
        if self.deadline_days is not None:
            self.deadline_days = _as_int(
                "LearningGoal", "deadline_days", self.deadline_days, minimum=1
            )
        self.weekly_minutes = _as_int(
            "LearningGoal", "weekly_minutes", self.weekly_minutes, minimum=1
        )


@dataclass
class LearningTask(Record):
    task_id: str
    goal_id: str
    skill_ids: list[str]
    task_type: str
    difficulty: int = 2
    fixture_ref: str = ""
    ordinal: int = 0

    def __post_init__(self) -> None:
        self.task_id = _as_str("LearningTask", "task_id", self.task_id)
        self.goal_id = _as_str("LearningTask", "goal_id", self.goal_id)
        self.skill_ids = _as_str_list("LearningTask", "skill_ids", self.skill_ids)
        if not self.skill_ids:
            raise _fail("LearningTask", "skill_ids must not be empty")
        self.task_type = _as_enum("LearningTask", "task_type", self.task_type, TASK_TYPE_VALUES)
        self.difficulty = _as_int("LearningTask", "difficulty", self.difficulty, minimum=1)
        if self.difficulty > 5:
            raise _fail("LearningTask", "difficulty must be <= 5")
        self.fixture_ref = _as_str(
            "LearningTask", "fixture_ref", self.fixture_ref, allow_empty=True
        )
        self.ordinal = _as_int("LearningTask", "ordinal", self.ordinal, minimum=0)


@dataclass
class CurriculumPlan(Record):
    plan_id: str
    goal_id: str
    tasks: list[LearningTask]
    rationale: list[str]
    policy_version: str
    created_at: str = ""

    def __post_init__(self) -> None:
        self.plan_id = _as_str("CurriculumPlan", "plan_id", self.plan_id)
        self.goal_id = _as_str("CurriculumPlan", "goal_id", self.goal_id)
        if not isinstance(self.tasks, list) or not all(
            isinstance(task, LearningTask) for task in self.tasks
        ):
            raise _fail("CurriculumPlan", "tasks must be list[LearningTask]")
        self.tasks = list(self.tasks)
        self.rationale = _as_str_list("CurriculumPlan", "rationale", self.rationale)
        self.policy_version = _as_str(
            "CurriculumPlan", "policy_version", self.policy_version
        )
        self.created_at = _fill_time("CurriculumPlan", "created_at", self.created_at)


@dataclass
class TeacherAction(Record):
    action_id: str
    kind: str
    content: str
    rationale: str
    hint_level: int | None = None
    target_skill_ids: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.action_id = _as_str("TeacherAction", "action_id", self.action_id)
        self.kind = _as_enum(
            "TeacherAction", "kind", self.kind, TEACHER_ACTION_KIND_VALUES
        )
        self.content = _as_str("TeacherAction", "content", self.content)
        self.rationale = _as_str("TeacherAction", "rationale", self.rationale)
        if self.hint_level is not None:
            self.hint_level = _as_int("TeacherAction", "hint_level", self.hint_level)
            if not HINT_LEVEL_MIN <= self.hint_level <= HINT_LEVEL_MAX:
                raise _fail(
                    "TeacherAction",
                    f"hint_level must be within [{HINT_LEVEL_MIN}, {HINT_LEVEL_MAX}]",
                )
        self.target_skill_ids = _as_str_list(
            "TeacherAction", "target_skill_ids", self.target_skill_ids
        )
        self.evidence_refs = _as_str_list(
            "TeacherAction", "evidence_refs", self.evidence_refs
        )


@dataclass
class DiagnosticResult(Record):
    diagnosis_id: str
    task_id: str
    error_codes: list[str]
    confidence: float
    status: str
    explanation: str
    evidence_refs: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.diagnosis_id = _as_str("DiagnosticResult", "diagnosis_id", self.diagnosis_id)
        self.task_id = _as_str("DiagnosticResult", "task_id", self.task_id)
        self.error_codes = _as_str_list("DiagnosticResult", "error_codes", self.error_codes)
        self.confidence = _as_float01("DiagnosticResult", "confidence", self.confidence)
        self.status = _as_enum(
            "DiagnosticResult", "status", self.status, DIAGNOSTIC_STATUS_VALUES
        )
        self.explanation = _as_str("DiagnosticResult", "explanation", self.explanation)
        self.evidence_refs = _as_str_list(
            "DiagnosticResult", "evidence_refs", self.evidence_refs
        )


@dataclass
class AssessmentResult(Record):
    assessment_id: str
    task_id: str
    learner_id: str
    scorer_id: str
    passed: bool
    score: float
    dimensions: dict[str, float]
    failure_modes: list[str] = field(default_factory=list)
    hidden_cases_passed: int = 0
    hidden_cases_total: int = 0

    def __post_init__(self) -> None:
        self.assessment_id = _as_str("AssessmentResult", "assessment_id", self.assessment_id)
        self.task_id = _as_str("AssessmentResult", "task_id", self.task_id)
        self.learner_id = _as_str("AssessmentResult", "learner_id", self.learner_id)
        self.scorer_id = _as_str("AssessmentResult", "scorer_id", self.scorer_id)
        self.passed = _as_bool("AssessmentResult", "passed", self.passed)
        self.score = _as_float01("AssessmentResult", "score", self.score)
        self.dimensions = _as_mastery("AssessmentResult", "dimensions", self.dimensions)
        self.failure_modes = _as_str_list(
            "AssessmentResult", "failure_modes", self.failure_modes
        )
        self.hidden_cases_passed = _as_int(
            "AssessmentResult", "hidden_cases_passed", self.hidden_cases_passed, minimum=0
        )
        self.hidden_cases_total = _as_int(
            "AssessmentResult", "hidden_cases_total", self.hidden_cases_total, minimum=0
        )
        if self.hidden_cases_passed > self.hidden_cases_total:
            raise _fail(
                "AssessmentResult",
                "hidden_cases_passed cannot exceed hidden_cases_total",
            )


@dataclass
class RuntimeRequest(Record):
    request_id: str
    session_id: str
    messages: list[dict]
    tools: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.request_id = _as_str("RuntimeRequest", "request_id", self.request_id)
        self.session_id = _as_str("RuntimeRequest", "session_id", self.session_id)
        if not isinstance(self.messages, list) or not all(
            isinstance(message, dict) for message in self.messages
        ):
            raise _fail("RuntimeRequest", "messages must be list[dict]")
        self.messages = list(self.messages)
        self.tools = _as_str_list("RuntimeRequest", "tools", self.tools)
        self.metadata = _as_dict("RuntimeRequest", "metadata", self.metadata)


@dataclass
class RuntimeResponse(Record):
    request_id: str
    session_id: str
    text: str
    tool_events: list[dict] = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    error: str | None = None
    simulated: bool = True

    def __post_init__(self) -> None:
        self.request_id = _as_str("RuntimeResponse", "request_id", self.request_id)
        self.session_id = _as_str("RuntimeResponse", "session_id", self.session_id)
        self.text = _as_str("RuntimeResponse", "text", self.text, allow_empty=True)
        if not isinstance(self.tool_events, list) or not all(
            isinstance(event, dict) for event in self.tool_events
        ):
            raise _fail("RuntimeResponse", "tool_events must be list[dict]")
        self.tool_events = list(self.tool_events)
        self.usage = _as_dict("RuntimeResponse", "usage", self.usage)
        if self.error is not None:
            self.error = _as_str("RuntimeResponse", "error", self.error)
        self.simulated = _as_bool("RuntimeResponse", "simulated", self.simulated)


@dataclass
class TraceEvent(Record):
    event_id: str
    loop_id: str
    round: int
    step: str
    payload: dict
    timestamp: str = ""

    def __post_init__(self) -> None:
        self.event_id = _as_str("TraceEvent", "event_id", self.event_id)
        self.loop_id = _as_str("TraceEvent", "loop_id", self.loop_id)
        self.round = _as_int("TraceEvent", "round", self.round, minimum=0)
        self.step = _as_str("TraceEvent", "step", self.step)
        self.payload = _as_dict("TraceEvent", "payload", self.payload)
        self.timestamp = _fill_time("TraceEvent", "timestamp", self.timestamp)


# ---------------------------------------------------------------------------
# Public exports
# ---------------------------------------------------------------------------
__all__ = [
    "SCHEMA_VERSION",
    "SchemaError",
    "Record",
    "now_utc",
    "CLAIM_STATUS_VALUES",
    "CHANGE_KIND_VALUES",
    "BASELINE_LEVEL_VALUES",
    "EVIDENCE_KIND_VALUES",
    "TASK_TYPE_VALUES",
    "TEACHER_ACTION_KIND_VALUES",
    "DIAGNOSTIC_STATUS_VALUES",
    "CLAIM_STATUS_SET",
    "CHANGE_KIND_SET",
    "BASELINE_LEVEL_SET",
    "EVIDENCE_KIND_SET",
    "TASK_TYPE_SET",
    "TEACHER_ACTION_KIND_SET",
    "DIAGNOSTIC_STATUS_SET",
    "HINT_LADDER",
    "HINT_LEVEL_MIN",
    "HINT_LEVEL_MAX",
    "Provenance",
    "SkillNode",
    "KnowledgeSource",
    "KnowledgeRevision",
    "LearnerProfile",
    "EvidenceEvent",
    "LearnerState",
    "LearningGoal",
    "LearningTask",
    "CurriculumPlan",
    "TeacherAction",
    "DiagnosticResult",
    "AssessmentResult",
    "RuntimeRequest",
    "RuntimeResponse",
    "TraceEvent",
]
