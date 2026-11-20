"""Frozen teacher-visible data contracts for the M1-A teacher (``m1a.v0``).

Design rules (see ``docs/M1_ADR_001_DOMAIN_CONTRACTS.md``):

* Every record is a mutable :class:`dataclasses.dataclass` that inherits from
  :class:`Record`.  It carries a ``schema_version`` (``"m1a.v0"``), a UTC
  ISO-8601 (second precision) ``created_at`` timestamp and strict
  ``to_dict``/``from_dict``/``to_json``/``from_json`` serialisation helpers.
* ``from_dict`` is fail-closed: unknown fields, a missing/wrong
  ``schema_version``, invalid enum values, out-of-range numbers, malformed
  timestamps and structurally invalid nested payloads all raise
  :class:`~m1_teacher.contracts.errors.ValidationError`.
* Enumerations are plain uppercase strings, validated at construction time.
  They are exposed as ``*_VALUES`` tuples and in :data:`ENUM_VALUES`.
* **No teacher-visible type may contain answer/expected/correct/solution
  fields.** Hidden scoring specifications live outside this package (fixture
  ``scoring`` specs are loaded only by the independent assessment scorer in a
  later PR).  :data:`FORBIDDEN_TEACHER_FIELD_TOKENS` records the enforcement
  rule and the module fails to import if a violating field is ever added.
* Records are value objects: they are validated at construction.  Mutating a
  record in place is possible (dataclasses are not frozen) but bypasses
  validation; producers should build new records instead.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from dataclasses import MISSING, dataclass, field, fields, is_dataclass
from datetime import datetime, timezone
from functools import lru_cache
from types import UnionType
from typing import Any, ClassVar, TypeVar, Union, get_args, get_origin, get_type_hints

from .errors import ValidationError

SCHEMA_VERSION = "m1a.v0"
"""Wire schema version of every frozen teacher-visible record."""

# ---------------------------------------------------------------------------
# Enumerations.  Plain uppercase strings validated at construction time.
# These tuples are frozen contract: append values, never rename/remove.
# ---------------------------------------------------------------------------

ASSESSMENT_STATUS_VALUES: tuple[str, ...] = (
    "CORRECT",
    "INCORRECT",
    "PARTIAL",
    "NEEDS_REVIEW",
    "EVAL_ERROR",
)

EVIDENCE_SOURCE_VALUES: tuple[str, ...] = (
    "OBSERVED",
    "INFERRED",
)

EDGE_KIND_VALUES: tuple[str, ...] = (
    "HARD",
    "SOFT",
)

ASSESSMENT_MODE_VALUES: tuple[str, ...] = (
    "DETERMINISTIC_JUDGE",
    "RULE_RUBRIC",
    "HUMAN_REVIEW_REQUIRED",
)

ITEM_TYPE_VALUES: tuple[str, ...] = (
    "MCQ",
    "CODE",
    "SHORT_ANSWER",
)

TEACHING_ACTION_KIND_VALUES: tuple[str, ...] = (
    "DIAGNOSE",
    "EXPLAIN",
    "HINT",
    "PRACTICE",
    "REVIEW",
    "RETEACH",
    "REASSESS",
    "GOAL_COMPLETE",
    "SESSION_PAUSE",
    "SESSION_RESUME",
)

SESSION_PHASE_VALUES: tuple[str, ...] = (
    "DIAGNOSE",
    "TEACH",
    "PRACTICE",
    "ASSESS",
    "UPDATE",
    "REVIEW",
    "COMPLETE",
    "PAUSED",
)

HISTORY_EVENT_TYPE_VALUES: tuple[str, ...] = (
    "SESSION_STARTED",
    "PLAN_CREATED",
    "DIAGNOSIS_COMPLETED",
    "ITEM_PRESENTED",
    "RESPONSE_SUBMITTED",
    "ASSESSED",
    "MASTERY_UPDATED",
    "ACTION_TAKEN",
    "SESSION_PAUSED",
    "SESSION_RESUMED",
    "GOAL_COMPLETED",
    "ERROR",
    # B-NEXT (B-PR2) additive value: a durable assessment attempt/prepared
    # response record written atomically before the external scorer runs, so a
    # crash between scoring preparation and the terminal ASSESSED/ERROR events
    # is recoverable.  Appended only; no existing value is renamed/removed.
    "ASSESSMENT_PREPARED",
)

DIAGNOSIS_STATUS_VALUES: tuple[str, ...] = (
    "READY",
    "INSUFFICIENT_EVIDENCE",
)

GOAL_STATUS_VALUES: tuple[str, ...] = (
    "ACTIVE",
    "COMPLETED",
    "PAUSED",
)

ENUM_VALUES: dict[str, tuple[str, ...]] = {
    "ASSESSMENT_STATUS": ASSESSMENT_STATUS_VALUES,
    "EVIDENCE_SOURCE": EVIDENCE_SOURCE_VALUES,
    "EDGE_KIND": EDGE_KIND_VALUES,
    "ASSESSMENT_MODE": ASSESSMENT_MODE_VALUES,
    "ITEM_TYPE": ITEM_TYPE_VALUES,
    "TEACHING_ACTION_KIND": TEACHING_ACTION_KIND_VALUES,
    "SESSION_PHASE": SESSION_PHASE_VALUES,
    "HISTORY_EVENT_TYPE": HISTORY_EVENT_TYPE_VALUES,
    "DIAGNOSIS_STATUS": DIAGNOSIS_STATUS_VALUES,
    "GOAL_STATUS": GOAL_STATUS_VALUES,
}
"""Public read-only convenience map (enum name -> allowed values)."""

FORBIDDEN_TEACHER_FIELD_TOKENS: tuple[str, ...] = (
    "answer",
    "expected",
    "correct",
    "solution",
)
"""Substrings that may never appear in a teacher-visible record field name.

Hidden scoring material (answer keys, expected outputs, correct option
indices) is deliberately outside the teacher-visible contract; expose it only
through the independent scorer's own types in a later PR.
"""

# ---------------------------------------------------------------------------
# UTC ISO-8601 (second precision) timestamp helpers
# ---------------------------------------------------------------------------

_TS_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
_UTC_SECONDS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def now_utc() -> str:
    """Return the current UTC time as canonical ``YYYY-MM-DDTHH:MM:SSZ``."""

    return datetime.now(timezone.utc).strftime(_TS_FORMAT)


def to_iso8601(moment: datetime) -> str:
    """Convert an aware datetime to the canonical UTC ISO-8601 second string."""

    if not isinstance(moment, datetime):
        raise ValidationError("to_iso8601() expects a datetime instance")
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValidationError("to_iso8601() expects a timezone-aware datetime")
    return moment.astimezone(timezone.utc).strftime(_TS_FORMAT)


def _coerce_timestamp(value: Any, where: str) -> str:
    if type(value) is not str:
        raise ValidationError(f"{where}: timestamp must be an ISO-8601 string")
    candidate = value
    if candidate.endswith("+00:00"):
        candidate = candidate[:-6] + "Z"
    if not _UTC_SECONDS_RE.match(candidate):
        raise ValidationError(
            f"{where}: timestamp {value!r} is not UTC ISO-8601 with second precision"
        )
    try:
        datetime.strptime(candidate, _TS_FORMAT)
    except ValueError as exc:
        raise ValidationError(f"{where}: timestamp {value!r} is not a real date/time") from exc
    return candidate


# ---------------------------------------------------------------------------
# Field metadata keys used by the generic validator/deserialiser
# ---------------------------------------------------------------------------

_META_ENUM = "enum"
_META_MIN = "min"
_META_MAX = "max"
_META_MIN_LENGTH = "min_length"
_META_RECORD = "record"
_META_RECORD_LIST = "record_list"
_META_RECORD_MAP = "record_map"
_META_TIMESTAMP = "timestamp"
_META_DICT_JSON = "dict_json"
_META_DICT_INT = "dict_int"


def _enum_meta(values: tuple[str, ...]) -> dict[str, Any]:
    return {_META_ENUM: tuple(values)}


def _range_meta(*, minimum: float | None = None, maximum: float | None = None) -> dict[str, Any]:
    meta: dict[str, Any] = {}
    if minimum is not None:
        meta[_META_MIN] = minimum
    if maximum is not None:
        meta[_META_MAX] = maximum
    return meta


def _timestamp_meta() -> dict[str, Any]:
    return {_META_TIMESTAMP: True}


def _created_at_field() -> Any:
    return field(default_factory=now_utc, metadata=_timestamp_meta(), kw_only=True)


def _updated_at_field() -> Any:
    return field(default_factory=now_utc, metadata=_timestamp_meta())


_UNION_ORIGINS = (Union, UnionType)

_NONEMPTY_STRING_FIELDS = frozenset({"code", "title", "prompt"})


def _string_must_be_nonempty(field_name: str) -> bool:
    """Identifiers, codes, titles and prompts must not be blank."""

    return field_name.endswith("_id") or field_name in _NONEMPTY_STRING_FIELDS


@lru_cache(maxsize=None)
def _class_hints(cls: type) -> dict[str, Any]:
    return get_type_hints(cls)


def _split_optional(hint: Any) -> tuple[bool, Any]:
    if hint is None:
        return False, None
    origin = get_origin(hint)
    if origin in _UNION_ORIGINS:
        args = tuple(arg for arg in get_args(hint) if arg is not type(None))
        if len(args) == 1:
            return True, args[0]
    return False, hint


def _check_enum_value(value: Any, allowed: tuple[str, ...], where: str) -> None:
    if type(value) is not str:
        raise ValidationError(
            f"{where}: expected one of {list(allowed)}, got {type(value).__name__}"
        )
    if value not in allowed:
        raise ValidationError(
            f"{where}: {value!r} is not a valid enum value; allowed: {list(allowed)}"
        )


def _check_range(value: float | int, meta: Mapping[str, Any], where: str) -> None:
    minimum = meta.get(_META_MIN)
    maximum = meta.get(_META_MAX)
    if minimum is not None and value < minimum:
        raise ValidationError(f"{where}: {value!r} is below the minimum {minimum!r}")
    if maximum is not None and value > maximum:
        raise ValidationError(f"{where}: {value!r} is above the maximum {maximum!r}")


def _check_unit_interval(value: Any, where: str) -> None:
    if type(value) not in (int, float):
        raise ValidationError(f"{where}: expected a number in [0, 1], got {type(value).__name__}")
    number = float(value)
    if not math.isfinite(number):
        raise ValidationError(f"{where}: expected a finite number in [0, 1]")
    if number < 0.0 or number > 1.0:
        raise ValidationError(f"{where}: {value!r} is outside [0, 1]")


def _check_json_payload(value: Any, where: str) -> None:
    if type(value) is not dict:
        raise ValidationError(f"{where}: expected a dict, got {type(value).__name__}")
    for key in value:
        if type(key) is not str:
            raise ValidationError(f"{where}: dict keys must be strings")
    try:
        json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{where}: payload is not JSON-serialisable: {exc}") from exc


def _validate_value(record: "Record", spec: Any, value: Any) -> None:
    """Validate (and where safe, normalise) one dataclass field."""

    meta = spec.metadata
    where = f"{type(record).__name__}.{spec.name}"
    hint = _class_hints(type(record)).get(spec.name)
    optional, base = _split_optional(hint)

    if value is None:
        if optional:
            return
        raise ValidationError(f"{where}: field must not be None")

    if _META_TIMESTAMP in meta:
        setattr(record, spec.name, _coerce_timestamp(value, where))
        return

    if _META_ENUM in meta:
        _check_enum_value(value, meta[_META_ENUM], where)
        return

    if _META_RECORD in meta:
        expected = meta[_META_RECORD]
        if not isinstance(value, expected):
            raise ValidationError(
                f"{where}: expected a {expected.__name__} instance, got {type(value).__name__}"
            )
        return

    if _META_RECORD_LIST in meta:
        expected = meta[_META_RECORD_LIST]
        if type(value) is not list:
            raise ValidationError(f"{where}: expected a list, got {type(value).__name__}")
        for index, element in enumerate(value):
            if not isinstance(element, expected):
                raise ValidationError(
                    f"{where}[{index}]: expected a {expected.__name__} instance, "
                    f"got {type(element).__name__}"
                )
        minimum_length = meta.get(_META_MIN_LENGTH)
        if minimum_length is not None and len(value) < minimum_length:
            raise ValidationError(f"{where}: expected at least {minimum_length} element(s)")
        return

    if _META_RECORD_MAP in meta:
        expected = meta[_META_RECORD_MAP]
        if type(value) is not dict:
            raise ValidationError(f"{where}: expected a dict, got {type(value).__name__}")
        for key, element in value.items():
            if type(key) is not str or not key:
                raise ValidationError(f"{where}: dict keys must be non-empty strings")
            if not isinstance(element, expected):
                raise ValidationError(
                    f"{where}[{key!r}]: expected a {expected.__name__} instance, "
                    f"got {type(element).__name__}"
                )
        return

    if _META_DICT_JSON in meta:
        _check_json_payload(value, where)
        return

    if _META_DICT_INT in meta:
        if type(value) is not dict:
            raise ValidationError(f"{where}: expected a dict, got {type(value).__name__}")
        minimum = meta.get(_META_MIN)
        for key, element in value.items():
            if type(key) is not str:
                raise ValidationError(f"{where}: dict keys must be strings")
            if type(element) is not int:
                raise ValidationError(f"{where}[{key!r}]: expected int, got {type(element).__name__}")
            if minimum is not None and element < minimum:
                raise ValidationError(f"{where}[{key!r}]: {element!r} is below the minimum {minimum!r}")
        return

    origin = get_origin(base)
    args = get_args(base)
    if origin is list:
        if args != (str,):
            raise RuntimeError(f"{where}: unsupported list annotation {base!r} in frozen contract")
        if type(value) is not list:
            raise ValidationError(f"{where}: expected a list, got {type(value).__name__}")
        for index, element in enumerate(value):
            if type(element) is not str:
                raise ValidationError(
                    f"{where}[{index}]: expected str, got {type(element).__name__}"
                )
        minimum_length = meta.get(_META_MIN_LENGTH)
        if minimum_length is not None and len(value) < minimum_length:
            raise ValidationError(f"{where}: expected at least {minimum_length} element(s)")
        return

    if base is str:
        if type(value) is not str:
            raise ValidationError(f"{where}: expected str, got {type(value).__name__}")
        if _string_must_be_nonempty(spec.name) and not value.strip():
            raise ValidationError(f"{where}: identifier/code/title/prompt must not be blank")
        return

    if base is bool:
        if type(value) is not bool:
            raise ValidationError(f"{where}: expected bool, got {type(value).__name__}")
        return

    if base is int:
        if type(value) is not int:
            raise ValidationError(f"{where}: expected int, got {type(value).__name__}")
        _check_range(value, meta, where)
        return

    if base is float:
        if type(value) not in (int, float):
            raise ValidationError(f"{where}: expected a number, got {type(value).__name__}")
        converted = float(value)
        if not math.isfinite(converted):
            raise ValidationError(f"{where}: expected a finite number")
        _check_range(converted, meta, where)
        setattr(record, spec.name, converted)
        return

    if base is dict:
        if type(value) is not dict:
            raise ValidationError(f"{where}: expected a dict, got {type(value).__name__}")
        return

    raise RuntimeError(f"{where}: unsupported field annotation {base!r} in frozen contract")


def _decode_field(spec: Any, raw: Any, where: str) -> Any:
    """Decode one raw JSON value into the constructor argument for ``spec``."""

    if raw is None:
        return None
    meta = spec.metadata
    if _META_RECORD in meta:
        expected = meta[_META_RECORD]
        if not isinstance(raw, Mapping):
            raise ValidationError(f"{where}: expected an object, got {type(raw).__name__}")
        return expected.from_dict(raw)
    if _META_RECORD_LIST in meta:
        expected = meta[_META_RECORD_LIST]
        if type(raw) is not list:
            raise ValidationError(f"{where}: expected a list, got {type(raw).__name__}")
        decoded: list[Any] = []
        for index, element in enumerate(raw):
            if not isinstance(element, Mapping):
                raise ValidationError(
                    f"{where}[{index}]: expected an object, got {type(element).__name__}"
                )
            decoded.append(expected.from_dict(element))
        return decoded
    if _META_RECORD_MAP in meta:
        expected = meta[_META_RECORD_MAP]
        if not isinstance(raw, Mapping):
            raise ValidationError(f"{where}: expected an object, got {type(raw).__name__}")
        decoded_map: dict[str, Any] = {}
        for key, element in raw.items():
            if type(key) is not str:
                raise ValidationError(f"{where}: dict keys must be strings")
            if not isinstance(element, Mapping):
                raise ValidationError(
                    f"{where}[{key!r}]: expected an object, got {type(element).__name__}"
                )
            decoded_map[key] = expected.from_dict(element)
        return decoded_map
    return raw


def _encode_value(value: Any) -> Any:
    if isinstance(value, Record):
        return value.to_dict()
    if isinstance(value, list):
        return [_encode_value(element) for element in value]
    if isinstance(value, dict):
        return {key: _encode_value(element) for key, element in value.items()}
    return value


_RecordT = TypeVar("_RecordT", bound="Record")


class Record:
    """Base class for all frozen teacher-visible records.

    Subclasses are standard dataclasses; they inherit the strict serialisation
    contract, the construction-time validation pass and the timestamp helpers.
    """

    schema_version: ClassVar[str] = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not is_dataclass(self):
            raise TypeError("Record subclasses must be dataclasses")
        for spec in fields(self):
            _validate_value(self, spec, getattr(self, spec.name))
        self._validate_extra()

    def _validate_extra(self) -> None:
        """Subclass hook for cross-field invariants (runs after field validation)."""

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable dict including ``schema_version``."""

        payload: dict[str, Any] = {"schema_version": self.schema_version}
        for spec in fields(self):
            payload[spec.name] = _encode_value(getattr(self, spec.name))
        return payload

    @classmethod
    def from_dict(cls: type[_RecordT], data: Mapping[str, Any]) -> _RecordT:
        """Strictly rebuild a record from :meth:`to_dict` output.

        Unknown fields, a missing or mismatched ``schema_version``, missing
        required fields and invalid nested structures raise
        :class:`ValidationError` (other field validation happens through the
        normal constructor path).
        """

        if not isinstance(data, Mapping):
            raise ValidationError(f"{cls.__name__}.from_dict: expected a mapping")
        if "schema_version" not in data:
            raise ValidationError(f"{cls.__name__}.from_dict: missing schema_version")
        version = data["schema_version"]
        if version != cls.schema_version:
            raise ValidationError(
                f"{cls.__name__}.from_dict: schema_version {version!r} is not "
                f"the frozen {cls.schema_version!r}"
            )
        raw = dict(data)
        allowed = {spec.name for spec in fields(cls)}
        unknown = sorted(repr(key) for key in raw if key not in allowed and key != "schema_version")
        if unknown:
            raise ValidationError(
                f"{cls.__name__}.from_dict: unknown field(s): {', '.join(unknown)}"
            )
        kwargs: dict[str, Any] = {}
        for spec in fields(cls):
            if spec.name not in raw:
                if spec.default is MISSING and spec.default_factory is MISSING:
                    raise ValidationError(
                        f"{cls.__name__}.from_dict: missing required field {spec.name!r}"
                    )
                continue
            where = f"{cls.__name__}.{spec.name}"
            kwargs[spec.name] = _decode_field(spec, raw[spec.name], where)
        try:
            return cls(**kwargs)
        except TypeError as exc:  # pragma: no cover - defensive safety net
            raise ValidationError(f"{cls.__name__}.from_dict: {exc}") from exc

    def to_json(self) -> str:
        """Serialise the record to JSON (insertion order, UTF-8 friendly)."""

        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_json(cls: type[_RecordT], raw: str) -> _RecordT:
        """Parse JSON produced by :meth:`to_json` (strictly, via ``from_dict``)."""

        if type(raw) is not str:
            raise ValidationError(f"{cls.__name__}.from_json: expected a string")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValidationError(f"{cls.__name__}.from_json: invalid JSON: {exc}") from exc
        return cls.from_dict(payload)


# ---------------------------------------------------------------------------
# Frozen records
# ---------------------------------------------------------------------------


@dataclass
class KnowledgeNode(Record):
    """One teachable knowledge node of a domain."""

    node_id: str
    domain_id: str
    title: str
    description: str
    difficulty: int = field(metadata=_range_meta(minimum=1, maximum=5))
    assessment_mode: str = field(metadata=_enum_meta(ASSESSMENT_MODE_VALUES))
    tags: list[str] = field(default_factory=list)
    content_ref: str = ""
    created_at: str = _created_at_field()


@dataclass
class PrerequisiteEdge(Record):
    """Directed prerequisite edge: ``source_node_id`` is a prerequisite of ``target_node_id``."""

    source_node_id: str
    target_node_id: str
    kind: str = field(metadata=_enum_meta(EDGE_KIND_VALUES))
    weight: float = field(default=1.0, metadata=_range_meta(minimum=0.0, maximum=1.0))
    created_at: str = _created_at_field()


_SUCCESS_CRITERIA_KEYS = frozenset({"min_mastery", "required_node_ids", "max_error_rate"})


@dataclass
class LearningObjective(Record):
    """Declarative learning objective with objective-level success criteria."""

    objective_id: str
    domain_id: str
    title: str
    description: str
    target_node_ids: list[str] = field(metadata={_META_MIN_LENGTH: 1})
    success_criteria: dict[str, Any] = field(metadata={_META_DICT_JSON: True})
    estimated_minutes: int = field(default=120, metadata=_range_meta(minimum=0))
    created_at: str = _created_at_field()

    def _validate_extra(self) -> None:
        criteria = self.success_criteria
        keys = set(criteria)
        missing = sorted(_SUCCESS_CRITERIA_KEYS - keys)
        if missing:
            raise ValidationError(
                f"LearningObjective.success_criteria: missing required key(s): {', '.join(missing)}"
            )
        unknown = sorted(keys - _SUCCESS_CRITERIA_KEYS)
        if unknown:
            raise ValidationError(
                f"LearningObjective.success_criteria: unknown key(s): {', '.join(unknown)}"
            )
        _check_unit_interval(
            criteria["min_mastery"], "LearningObjective.success_criteria.min_mastery"
        )
        _check_unit_interval(
            criteria["max_error_rate"], "LearningObjective.success_criteria.max_error_rate"
        )
        required = criteria["required_node_ids"]
        if type(required) is not list:
            raise ValidationError(
                "LearningObjective.success_criteria.required_node_ids: expected a list"
            )
        for index, node_id in enumerate(required):
            if type(node_id) is not str or not node_id:
                raise ValidationError(
                    "LearningObjective.success_criteria.required_node_ids"
                    f"[{index}]: expected a non-empty string"
                )
        unknown_required = sorted(set(required) - set(self.target_node_ids))
        if unknown_required:
            raise ValidationError(
                "LearningObjective.success_criteria.required_node_ids must be a subset of "
                f"target_node_ids; unknown: {unknown_required}"
            )


@dataclass
class AssessmentItem(Record):
    """A teacher-visible assessment item.

    Deliberately contains **no** answer/expected/scoring values: hidden scoring
    specifications are stored only in fixtures and loaded by the independent
    scorer in a later PR.  ``scoring_spec_ref`` is an opaque reference string,
    not scoring content.
    """

    item_id: str
    domain_id: str
    node_ids: list[str] = field(metadata={_META_MIN_LENGTH: 1})
    item_type: str = field(metadata=_enum_meta(ITEM_TYPE_VALUES))
    difficulty: int = field(metadata=_range_meta(minimum=1, maximum=5))
    prompt: str
    options: list[str] = field(default_factory=list)
    function_name: str | None = None
    max_score: float = field(default=1.0, metadata=_range_meta(minimum=0.0))
    deterministic: bool = True
    scoring_spec_ref: str = ""
    created_at: str = _created_at_field()


@dataclass
class AssessmentResult(Record):
    """Outcome of one independent assessment attempt.

    ``scorer_id`` is required by the frozen contract but is listed after the
    optional ``score`` / ``max_score`` fields, so it is declared keyword-only
    here to preserve the documented field order.  Wire field *names* are the
    contract; timestamps are keyword-only for the same reason.
    """

    result_id: str
    item_id: str
    learner_id: str
    status: str = field(metadata=_enum_meta(ASSESSMENT_STATUS_VALUES))
    score: float | None = None
    max_score: float = field(default=1.0, metadata=_range_meta(minimum=0.0))
    scorer_id: str = field(kw_only=True)
    failure_reason: str = ""
    evidence_refs: list[str] = field(default_factory=list)
    created_at: str = _created_at_field()

    def _validate_extra(self) -> None:
        if self.max_score <= 0.0:
            raise ValidationError("AssessmentResult.max_score must be greater than 0")
        if self.score is not None:
            if self.score < 0.0 or self.score > self.max_score:
                raise ValidationError(
                    f"AssessmentResult.score {self.score!r} is outside [0, {self.max_score!r}]"
                )


@dataclass
class Reason(Record):
    """Structured, machine-checkable explanation used by diagnose/plan/act.

    ``code`` is a short stable policy code (upper snake case by convention),
    ``node_ids`` lists the knowledge nodes the decision is about,
    ``policy_version`` records which policy produced it.
    """

    code: str
    node_ids: list[str] = field(default_factory=list)
    detail: str = ""
    policy_version: str = ""
    created_at: str = _created_at_field()


@dataclass
class TeachingAction(Record):
    """One teacher action (explain, hint, practice, review, pause, ...)."""

    action_id: str
    kind: str = field(metadata=_enum_meta(TEACHING_ACTION_KIND_VALUES))
    node_ids: list[str] = field(default_factory=list)
    content: str = ""
    reason: Reason | None = field(default=None, metadata={_META_RECORD: Reason})
    item_id: str | None = None
    evidence_refs: list[str] = field(default_factory=list)
    created_at: str = _created_at_field()


@dataclass
class EvidenceReference(Record):
    """Pointer to a learner-history event that supports a claim."""

    evidence_id: str
    source: str = field(metadata=_enum_meta(EVIDENCE_SOURCE_VALUES))
    event_id: str
    detail: str = ""
    created_at: str = _created_at_field()


@dataclass
class MasteryEstimate(Record):
    """Per-node mastery estimate with uncertainty metadata."""

    node_id: str
    value: float = field(metadata=_range_meta(minimum=0.0, maximum=1.0))
    confidence: float = field(metadata=_range_meta(minimum=0.0, maximum=1.0))
    evidence_count: int = field(metadata=_range_meta(minimum=0))
    created_at: str = _created_at_field()
    updated_at: str = _updated_at_field()


@dataclass
class LearnerSnapshot(Record):
    """Materialised learner state (later PRs must be able to rebuild it from events)."""

    learner_id: str
    masteries: dict[str, MasteryEstimate] = field(
        default_factory=dict, metadata={_META_RECORD_MAP: MasteryEstimate}
    )
    completed_item_ids: list[str] = field(default_factory=list)
    error_counts: dict[str, int] = field(
        default_factory=dict, metadata={_META_DICT_INT: True, _META_MIN: 0}
    )
    revision: int = field(default=0, metadata=_range_meta(minimum=0))
    created_at: str = _created_at_field()
    updated_at: str = _updated_at_field()

    def _validate_extra(self) -> None:
        for node_id, mastery in self.masteries.items():
            if mastery.node_id != node_id:
                raise ValidationError(
                    f"LearnerSnapshot.masteries[{node_id!r}].node_id "
                    f"{mastery.node_id!r} does not match its dict key"
                )


@dataclass
class LearnerGoal(Record):
    """A learner's goal against one domain objective."""

    goal_id: str
    learner_id: str
    objective_id: str
    status: str = field(default="ACTIVE", metadata=_enum_meta(GOAL_STATUS_VALUES))
    created_at: str = _created_at_field()


@dataclass
class HistoryEvent(Record):
    """Append-only learner history event.

    ``event_id`` is the idempotency key used by repositories
    (``append_event`` returns ``False`` when it already exists) and
    ``seq`` provides a per-learner ordering for rebuilds.
    """

    event_id: str
    learner_id: str
    session_id: str
    seq: int = field(metadata=_range_meta(minimum=0))
    event_type: str = field(metadata=_enum_meta(HISTORY_EVENT_TYPE_VALUES))
    payload: dict[str, Any] = field(default_factory=dict, metadata={_META_DICT_JSON: True})
    created_at: str = _created_at_field()


@dataclass
class SessionState(Record):
    """Persistent state of one teaching session."""

    session_id: str
    learner_id: str
    goal_id: str
    objective_id: str
    phase: str = field(default="PAUSED", metadata=_enum_meta(SESSION_PHASE_VALUES))
    turn_index: int = field(default=0, metadata=_range_meta(minimum=0))
    pending_item_id: str | None = None
    created_at: str = _created_at_field()
    updated_at: str = _updated_at_field()


@dataclass
class PlanStep(Record):
    """One explainable step of a curriculum plan."""

    step_id: str
    ordinal: int = field(metadata=_range_meta(minimum=0))
    phase: str = field(metadata=_enum_meta(SESSION_PHASE_VALUES))
    node_ids: list[str]
    action_kind: str = field(metadata=_enum_meta(TEACHING_ACTION_KIND_VALUES))
    rationale: Reason = field(metadata={_META_RECORD: Reason})
    item_id: str | None = None
    created_at: str = _created_at_field()


@dataclass
class CurriculumPlan(Record):
    """Deterministic, versioned plan produced by the curriculum planner."""

    plan_id: str
    learner_id: str
    goal_id: str
    objective_id: str
    steps: list[PlanStep] = field(metadata={_META_RECORD_LIST: PlanStep})
    policy_version: str
    created_at: str = _created_at_field()


@dataclass
class DiagnosisResult(Record):
    """Diagnosis outcome: a next diagnostic item plus structured reasoning."""

    diagnosis_id: str
    learner_id: str
    status: str = field(metadata=_enum_meta(DIAGNOSIS_STATUS_VALUES))
    target_node_id: str
    selected_item_id: str | None = None
    hypothesis: str = ""
    reason: Reason | None = field(default=None, metadata={_META_RECORD: Reason})
    evidence_refs: list[str] = field(default_factory=list)
    created_at: str = _created_at_field()


RECORD_TYPES: tuple[type[Record], ...] = (
    KnowledgeNode,
    PrerequisiteEdge,
    LearningObjective,
    AssessmentItem,
    AssessmentResult,
    Reason,
    TeachingAction,
    EvidenceReference,
    MasteryEstimate,
    LearnerSnapshot,
    LearnerGoal,
    HistoryEvent,
    SessionState,
    PlanStep,
    CurriculumPlan,
    DiagnosisResult,
)
"""All frozen teacher-visible record types (add-only)."""


def _assert_teacher_visible_types_are_answer_free() -> None:
    for record_type in RECORD_TYPES:
        for spec in fields(record_type):
            lowered = spec.name.lower()
            for token in FORBIDDEN_TEACHER_FIELD_TOKENS:
                if token in lowered:
                    raise RuntimeError(
                        "Frozen m1a.v0 contract violation: "
                        f"{record_type.__name__}.{spec.name} looks like hidden-answer material"
                    )


_assert_teacher_visible_types_are_answer_free()


__all__ = [
    "SCHEMA_VERSION",
    "ASSESSMENT_STATUS_VALUES",
    "EVIDENCE_SOURCE_VALUES",
    "EDGE_KIND_VALUES",
    "ASSESSMENT_MODE_VALUES",
    "ITEM_TYPE_VALUES",
    "TEACHING_ACTION_KIND_VALUES",
    "SESSION_PHASE_VALUES",
    "HISTORY_EVENT_TYPE_VALUES",
    "DIAGNOSIS_STATUS_VALUES",
    "GOAL_STATUS_VALUES",
    "ENUM_VALUES",
    "FORBIDDEN_TEACHER_FIELD_TOKENS",
    "RECORD_TYPES",
    "now_utc",
    "to_iso8601",
    "Record",
    "KnowledgeNode",
    "PrerequisiteEdge",
    "LearningObjective",
    "AssessmentItem",
    "AssessmentResult",
    "Reason",
    "TeachingAction",
    "EvidenceReference",
    "MasteryEstimate",
    "LearnerSnapshot",
    "LearnerGoal",
    "HistoryEvent",
    "SessionState",
    "PlanStep",
    "CurriculumPlan",
    "DiagnosisResult",
]
