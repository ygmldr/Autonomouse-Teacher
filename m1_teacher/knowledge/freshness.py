"""Knowledge freshness service for the M1-B vertical layer (B-PR4).

Implements the additive :class:`m1_teacher.extensions.KnowledgeFreshnessPort`
surface plus the richer gate methods needed by the vertical fixtures:

* ``classify(request)`` -- protocol-compatible single-observation classification;
  observations without a content digest fail closed to ``RECHECK`` instead of
  pretending to be a ``KEEP``/``UPDATE``.
* ``classify_pair(old_version_id, new_version_id)`` -- deterministic
  ``KEEP`` / ``UPDATE`` / ``RECHECK`` classification over versioned, timestamped
  synthetic knowledge.
* ``curriculum_eligible`` / ``recheck_required`` / ``require_curriculum_eligible``
  -- the only curriculum write gate.  Conflicts, expiry, future-dated sources,
  older/mirrored sources and unauthoritative layers are never eligible.
* ``active_jd`` / ``jd_change_impact`` -- JD version gate: JD changes are hiring
  context for **new plans only**; they never mutate a running session, never act
  as topic popularity and never update mastery.

Hard boundaries: offline, deterministic, no network, no wall clock reads (all
timestamps come from fixtures / explicit ``now`` arguments), no learner or
session writes.  Failure reasons use the stable ``MAP-E`` codes from
``docs/M1_B_INTERVIEW_FRESHNESS_MAPPING.md`` for the curriculum gates.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from ..contracts.errors import NotFoundError, ValidationError
from ..extensions.interfaces import KnowledgeFreshnessPort, KnowledgeFreshnessRequest

__all__ = [
    "CHANGE_KINDS",
    "CLAIM_STATUSES",
    "SOURCE_TIERS",
    "TIER_MAY_UPDATE_CURRICULUM",
    "FreshnessDecision",
    "JdChangeImpact",
    "JdGateDecision",
    "JdVersion",
    "KnowledgeFreshnessService",
    "KnowledgeSourceVersion",
    "default_fixtures_root",
]

SCHEMA_VERSION = "m1a.v0"
DOMAIN_ID = "interview_coach"
FIXTURES_ENV_VAR = "M1_TEACHER_FIXTURES"
DEFAULT_FIXTURES_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "m1_teacher"

CHANGE_KINDS = ("KEEP", "UPDATE", "RECHECK")
CLAIM_STATUSES = ("VERIFIED", "REPORTED", "CONFLICT", "EXPIRED", "UNKNOWN")

SOURCE_TIERS: dict[str, int] = {
    "official_document": 3,
    "paper": 2,
    "engineering_blog": 2,
    "jd": 2,
    "community": 1,
    "mirror": 0,
    "unknown": 0,
}
TIER_MAY_UPDATE_CURRICULUM: dict[str, bool] = {
    "official_document": True,
    "paper": True,
    "engineering_blog": True,
    "jd": False,
    "community": False,
    "mirror": False,
    "unknown": False,
}

# Stable rejection / gate codes from docs/M1_B_INTERVIEW_FRESHNESS_MAPPING.md §3.9.
MAP_E07_KNOWLEDGE_PROVENANCE_LOSS = "MAP-E07_KNOWLEDGE_PROVENANCE_LOSS"
MAP_E08_KNOWLEDGE_RECHECK_BLOCKED = "MAP-E08_KNOWLEDGE_RECHECK_BLOCKED"
MAP_E09_KNOWLEDGE_CONFLICT_BLOCKED = "MAP-E09_KNOWLEDGE_CONFLICT_BLOCKED"
MAP_E10_JD_EXPIRED_OR_CONFLICT = "MAP-E10_JD_EXPIRED_OR_CONFLICT"

TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
HASH_RE = re.compile(r"^[0-9a-f]{64}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_KNOWLEDGE_KEYS = frozenset(
    {
        "version_id",
        "source_id",
        "topic",
        "role",
        "uri",
        "publisher",
        "published_at",
        "observed_at",
        "valid_until",
        "confidence",
        "claim_status",
        "source_tier",
        "content_hash",
        "synthetic",
        "license",
    }
)
_JD_KEYS = frozenset(
    {
        "jd_id",
        "version",
        "source_jd_id",
        "role",
        "company_synthetic",
        "requirements",
        "skills",
        "valid_from",
        "valid_until",
        "supersedes",
        "delta",
        "content_digest",
        "synthetic",
        "license",
    }
)
_DELTA_KEYS = frozenset(
    {"added_requirements", "removed_requirements", "added_skills", "removed_skills"}
)


# ---------------------------------------------------------------------------
# Strict fixture validators
# ---------------------------------------------------------------------------


def _expect_mapping(value: Any, where: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise ValidationError(
            f"{where}: expected an object, got {type(value).__name__}",
            code="FRESHNESS_FIXTURE_INVALID",
        )
    return value


def _expect_list(value: Any, where: str, *, min_length: int = 0) -> list[Any]:
    if type(value) is not list:
        raise ValidationError(
            f"{where}: expected a list, got {type(value).__name__}",
            code="FRESHNESS_FIXTURE_INVALID",
        )
    if len(value) < min_length:
        raise ValidationError(
            f"{where}: expected at least {min_length} element(s)",
            code="FRESHNESS_FIXTURE_INVALID",
        )
    return value


def _expect_str(value: Any, where: str, *, allow_empty: bool = False) -> str:
    if type(value) is not str:
        raise ValidationError(
            f"{where}: expected str, got {type(value).__name__}",
            code="FRESHNESS_FIXTURE_INVALID",
        )
    if not allow_empty and not value.strip():
        raise ValidationError(
            f"{where}: expected a non-blank string", code="FRESHNESS_FIXTURE_INVALID"
        )
    return value


def _expect_number(value: Any, where: str, *, minimum: float, maximum: float) -> float:
    if type(value) not in (int, float):
        raise ValidationError(
            f"{where}: expected a number, got {type(value).__name__}",
            code="FRESHNESS_FIXTURE_INVALID",
        )
    number = float(value)
    if not minimum <= number <= maximum:
        raise ValidationError(
            f"{where}: expected within [{minimum}, {maximum}], got {number}",
            code="FRESHNESS_FIXTURE_INVALID",
        )
    return number


def _expect_bool(value: Any, where: str) -> bool:
    if type(value) is not bool:
        raise ValidationError(
            f"{where}: expected bool, got {type(value).__name__}",
            code="FRESHNESS_FIXTURE_INVALID",
        )
    return value


def _expect_enum(value: Any, allowed: tuple[str, ...], where: str) -> str:
    text = _expect_str(value, where)
    if text not in allowed:
        raise ValidationError(
            f"{where}: {text!r} is not one of {list(allowed)}",
            code="FRESHNESS_FIXTURE_INVALID",
        )
    return text


def _expect_str_list(value: Any, where: str) -> list[str]:
    entries = _expect_list(value, where)
    return [_expect_str(entry, f"{where}[{index}]") for index, entry in enumerate(entries)]


def _expect_timestamp(value: Any, where: str, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    text = _expect_str(value, where)
    if not TIMESTAMP_RE.match(text):
        raise ValidationError(
            f"{where}: expected UTC ISO-8601 second precision 'YYYY-MM-DDTHH:MM:SSZ', "
            f"got {text!r}",
            code="FRESHNESS_FIXTURE_INVALID",
        )
    return text


def _expect_date(value: Any, where: str) -> str:
    text = _expect_str(value, where)
    if not DATE_RE.match(text):
        raise ValidationError(
            f"{where}: expected 'YYYY-MM-DD', got {text!r}", code="FRESHNESS_FIXTURE_INVALID"
        )
    return text


def _reject_unknown_keys(mapping: Mapping[str, Any], allowed: frozenset[str], where: str) -> None:
    unknown = sorted(repr(key) for key in mapping if key not in allowed)
    if unknown:
        raise ValidationError(
            f"{where}: unknown key(s): {', '.join(unknown)}",
            code="FRESHNESS_FIXTURE_INVALID",
        )


def _require_schema(payload: Mapping[str, Any], filename: str) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValidationError(
            f"{filename}: schema_version must be {SCHEMA_VERSION!r}",
            code="FRESHNESS_FIXTURE_INVALID",
        )


def _canonical_sha256(value: Any) -> str:
    blob = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(blob).hexdigest()


def default_fixtures_root() -> Path:
    """Default ``fixtures/m1_teacher`` root (overridable via ``M1_TEACHER_FIXTURES``)."""

    env_value = os.environ.get(FIXTURES_ENV_VAR)
    if env_value:
        return Path(env_value).expanduser().resolve()
    return Path(DEFAULT_FIXTURES_ROOT)


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
# Value objects (service-local, not part of the frozen m1a.v0 contract)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class KnowledgeSourceVersion:
    """One immutable version of a synthetic knowledge source."""

    version_id: str
    source_id: str
    topic: str
    role: str
    uri: str
    publisher: str
    published_at: str
    observed_at: str
    valid_until: str | None
    confidence: float
    claim_status: str
    source_tier: str
    content_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "version_id": self.version_id,
            "source_id": self.source_id,
            "topic": self.topic,
            "role": self.role,
            "uri": self.uri,
            "publisher": self.publisher,
            "published_at": self.published_at,
            "observed_at": self.observed_at,
            "valid_until": self.valid_until,
            "confidence": self.confidence,
            "claim_status": self.claim_status,
            "source_tier": self.source_tier,
            "content_hash": self.content_hash,
        }


@dataclass(frozen=True)
class FreshnessDecision:
    """Deterministic KEEP/UPDATE/RECHECK decision with curriculum gate flags."""

    source_id: str
    old_version_id: str
    new_version_id: str
    change_kind: str
    claim_status: str
    reason_code: str
    map_code: str | None
    curriculum_eligible: bool
    recheck_required: bool
    detected_at: str
    old_hash: str
    new_hash: str
    notes: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "old_version_id": self.old_version_id,
            "new_version_id": self.new_version_id,
            "change_kind": self.change_kind,
            "claim_status": self.claim_status,
            "reason_code": self.reason_code,
            "map_code": self.map_code,
            "curriculum_eligible": self.curriculum_eligible,
            "recheck_required": self.recheck_required,
            "detected_at": self.detected_at,
            "old_hash": self.old_hash,
            "new_hash": self.new_hash,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class JdVersion:
    """One version of a synthetic job-description context (hiring requirements only)."""

    jd_id: str
    version: str
    source_jd_id: str
    role: str
    requirements: tuple[str, ...]
    skills: tuple[str, ...]
    valid_from: str
    valid_until: str
    supersedes: str | None
    delta: dict[str, list[str]]
    content_digest: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "jd_id": self.jd_id,
            "version": self.version,
            "source_jd_id": self.source_jd_id,
            "role": self.role,
            "requirements": list(self.requirements),
            "skills": list(self.skills),
            "valid_from": self.valid_from,
            "valid_until": self.valid_until,
            "supersedes": self.supersedes,
            "delta": {key: list(value) for key, value in self.delta.items()},
            "content_digest": self.content_digest,
        }


@dataclass(frozen=True)
class JdGateDecision:
    """Result of consulting the JD window for new-plan creation at ``now``."""

    jd_id: str
    now: str
    active_version: str | None
    allowed_for_new_plan: bool
    reason_code: str
    map_code: str | None
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "jd_id": self.jd_id,
            "now": self.now,
            "active_version": self.active_version,
            "allowed_for_new_plan": self.allowed_for_new_plan,
            "reason_code": self.reason_code,
            "map_code": self.map_code,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class JdChangeImpact:
    """Impact of a JD version change: new plans only, never running sessions/mastery."""

    jd_id: str
    old_version: str
    new_version: str
    affects_running_sessions: bool
    affects_new_plans: bool
    reason_code: str
    delta: dict[str, list[str]]
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "jd_id": self.jd_id,
            "old_version": self.old_version,
            "new_version": self.new_version,
            "affects_running_sessions": self.affects_running_sessions,
            "affects_new_plans": self.affects_new_plans,
            "reason_code": self.reason_code,
            "delta": {key: list(value) for key, value in self.delta.items()},
            "detail": self.detail,
        }


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class KnowledgeFreshnessService:
    """Deterministic offline freshness + source-credibility + JD-window gate."""

    def __init__(self, fixtures_root: str | Path | None = None) -> None:
        root = fixtures_root if fixtures_root is not None else default_fixtures_root()
        self._fixtures_root = _coerce_fixtures_root(root)
        self._interview_dir = self._fixtures_root / "vertical" / "interview"
        self._freshness_dir = self._fixtures_root / "vertical" / "freshness"
        self._versions: dict[str, KnowledgeSourceVersion] = {}
        self._versions_by_source: dict[str, list[KnowledgeSourceVersion]] = {}
        self._jds: list[JdVersion] = []
        self._jds_by_id: dict[str, list[JdVersion]] = {}
        self._knowledge_scenarios: list[dict[str, Any]] = []
        self._jd_scenarios: list[dict[str, Any]] = []
        self._jd_change_scenarios: list[dict[str, Any]] = []
        self._load()

    # -- properties --------------------------------------------------------
    @property
    def fixtures_root(self) -> Path:
        return self._fixtures_root

    # -- loading -----------------------------------------------------------
    @staticmethod
    def _read_json(path: Path, label: str) -> dict[str, Any]:
        if not path.is_file():
            raise NotFoundError(f"freshness fixture file not found: {path}")
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:  # pragma: no cover - filesystem failure
            raise NotFoundError(f"cannot read freshness fixture {path}: {exc}") from exc
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValidationError(
                f"{label}: invalid JSON: {exc}", code="FRESHNESS_FIXTURE_INVALID"
            ) from exc
        return _expect_mapping(payload, label)

    def _load(self) -> None:
        self._load_knowledge_sources(
            self._read_json(self._interview_dir / "knowledge_sources.json", "knowledge_sources.json")
        )
        self._load_jds(self._read_json(self._interview_dir / "jds.json", "jds.json"))
        self._load_scenarios(
            self._read_json(self._freshness_dir / "scenarios.json", "scenarios.json")
        )

    def _load_provenance(self, payload: Mapping[str, Any], filename: str) -> None:
        provenance = _expect_mapping(payload.get("provenance"), f"{filename}.provenance")
        if provenance.get("synthetic") is not True:
            raise ValidationError(
                f"{filename}.provenance.synthetic must be True",
                code="FRESHNESS_FIXTURE_INVALID",
            )
        if provenance.get("license") != "CC0-1.0":
            raise ValidationError(
                f"{filename}.provenance.license must be 'CC0-1.0'",
                code="FRESHNESS_FIXTURE_INVALID",
            )

    def _load_knowledge_sources(self, payload: dict[str, Any]) -> None:
        _reject_unknown_keys(
            payload,
            frozenset({"schema_version", "domain_id", "domain_version", "provenance", "versions"}),
            "knowledge_sources.json",
        )
        _require_schema(payload, "knowledge_sources.json")
        if payload.get("domain_id") != DOMAIN_ID:
            raise ValidationError(
                f"knowledge_sources.json.domain_id must be {DOMAIN_ID!r}",
                code="FRESHNESS_FIXTURE_INVALID",
            )
        _expect_str(payload.get("domain_version"), "knowledge_sources.json.domain_version")
        self._load_provenance(payload, "knowledge_sources.json")
        versions: dict[str, KnowledgeSourceVersion] = {}
        by_source: dict[str, list[KnowledgeSourceVersion]] = {}
        for index, raw in enumerate(
            _expect_list(payload.get("versions"), "knowledge_sources.json.versions", min_length=1)
        ):
            where = f"knowledge_sources.json.versions[{index}]"
            entry = _expect_mapping(raw, where)
            _reject_unknown_keys(entry, _KNOWLEDGE_KEYS, where)
            claim_status = _expect_enum(
                entry.get("claim_status"), CLAIM_STATUSES, f"{where}.claim_status"
            )
            source_tier = _expect_enum(
                entry.get("source_tier"), tuple(SOURCE_TIERS), f"{where}.source_tier"
            )
            content_hash = _expect_str(entry.get("content_hash"), f"{where}.content_hash")
            if not HASH_RE.match(content_hash):
                raise ValidationError(
                    f"{where}.content_hash must be a 64-hex sha256 digest",
                    code="FRESHNESS_FIXTURE_INVALID",
                )
            if entry.get("synthetic") is not True:
                raise ValidationError(
                    f"{where}.synthetic must be True", code="FRESHNESS_FIXTURE_INVALID"
                )
            if entry.get("license") != "CC0-1.0":
                raise ValidationError(
                    f"{where}.license must be 'CC0-1.0'", code="FRESHNESS_FIXTURE_INVALID"
                )
            version = KnowledgeSourceVersion(
                version_id=_expect_str(entry.get("version_id"), f"{where}.version_id"),
                source_id=_expect_str(entry.get("source_id"), f"{where}.source_id"),
                topic=_expect_str(entry.get("topic"), f"{where}.topic"),
                role=_expect_enum(entry.get("role"), ("old", "new"), f"{where}.role"),
                uri=_expect_str(entry.get("uri"), f"{where}.uri"),
                publisher=_expect_str(entry.get("publisher"), f"{where}.publisher"),
                published_at=_expect_timestamp(
                    entry.get("published_at"), f"{where}.published_at"
                ),
                observed_at=_expect_timestamp(entry.get("observed_at"), f"{where}.observed_at"),
                valid_until=_expect_timestamp(
                    entry.get("valid_until"), f"{where}.valid_until", optional=True
                ),
                confidence=_expect_number(
                    entry.get("confidence"), f"{where}.confidence", minimum=0.0, maximum=1.0
                ),
                claim_status=claim_status,
                source_tier=source_tier,
                content_hash=content_hash,
            )
            if version.version_id in versions:
                raise ValidationError(
                    f"{where}: duplicate version_id {version.version_id!r}",
                    code="FRESHNESS_FIXTURE_INVALID",
                )
            versions[version.version_id] = version
            by_source.setdefault(version.source_id, []).append(version)
        self._versions = versions
        self._versions_by_source = {
            source_id: sorted(group, key=lambda version: version.observed_at)
            for source_id, group in by_source.items()
        }

    def _load_jds(self, payload: dict[str, Any]) -> None:
        _reject_unknown_keys(
            payload,
            frozenset({"schema_version", "domain_id", "domain_version", "provenance", "jds"}),
            "jds.json",
        )
        _require_schema(payload, "jds.json")
        if payload.get("domain_id") != DOMAIN_ID:
            raise ValidationError(
                f"jds.json.domain_id must be {DOMAIN_ID!r}", code="FRESHNESS_FIXTURE_INVALID"
            )
        _expect_str(payload.get("domain_version"), "jds.json.domain_version")
        self._load_provenance(payload, "jds.json")
        jds: list[JdVersion] = []
        for index, raw in enumerate(
            _expect_list(payload.get("jds"), "jds.json.jds", min_length=1)
        ):
            where = f"jds.json.jds[{index}]"
            entry = _expect_mapping(raw, where)
            _reject_unknown_keys(entry, _JD_KEYS, where)
            if entry.get("company_synthetic") is not True:
                raise ValidationError(
                    f"{where}.company_synthetic must be True",
                    code="FRESHNESS_FIXTURE_INVALID",
                )
            if entry.get("synthetic") is not True:
                raise ValidationError(
                    f"{where}.synthetic must be True", code="FRESHNESS_FIXTURE_INVALID"
                )
            if entry.get("license") != "CC0-1.0":
                raise ValidationError(
                    f"{where}.license must be 'CC0-1.0'", code="FRESHNESS_FIXTURE_INVALID"
                )
            raw_delta = _expect_mapping(entry.get("delta"), f"{where}.delta")
            _reject_unknown_keys(raw_delta, _DELTA_KEYS, f"{where}.delta")
            delta = {
                key: _expect_str_list(raw_delta.get(key), f"{where}.delta.{key}")
                for key in _DELTA_KEYS
            }
            content_digest = _expect_str(entry.get("content_digest"), f"{where}.content_digest")
            if not HASH_RE.match(content_digest):
                raise ValidationError(
                    f"{where}.content_digest must be a 64-hex sha256 digest",
                    code="FRESHNESS_FIXTURE_INVALID",
                )
            supersedes = entry.get("supersedes")
            if supersedes is not None:
                supersedes = _expect_str(supersedes, f"{where}.supersedes")
            jds.append(
                JdVersion(
                    jd_id=_expect_str(entry.get("jd_id"), f"{where}.jd_id"),
                    version=_expect_str(entry.get("version"), f"{where}.version"),
                    source_jd_id=_expect_str(entry.get("source_jd_id"), f"{where}.source_jd_id"),
                    role=_expect_str(entry.get("role"), f"{where}.role"),
                    requirements=tuple(
                        _expect_str_list(entry.get("requirements"), f"{where}.requirements")
                    ),
                    skills=tuple(_expect_str_list(entry.get("skills"), f"{where}.skills")),
                    valid_from=_expect_date(entry.get("valid_from"), f"{where}.valid_from"),
                    valid_until=_expect_date(entry.get("valid_until"), f"{where}.valid_until"),
                    supersedes=supersedes,
                    delta=delta,
                    content_digest=content_digest,
                )
            )
        seen: set[tuple[str, str]] = set()
        for jd in jds:
            key = (jd.jd_id, jd.version)
            if key in seen:
                raise ValidationError(
                    f"jds.json: duplicate (jd_id, version) {key}",
                    code="FRESHNESS_FIXTURE_INVALID",
                )
            seen.add(key)
            if jd.supersedes is not None:
                parent = next(
                    (candidate for candidate in jds if candidate.jd_id == jd.jd_id
                     and candidate.version == jd.supersedes),
                    None,
                )
                if parent is None:
                    raise ValidationError(
                        f"jds.json: {jd.jd_id}@{jd.version} supersedes unknown version "
                        f"{jd.supersedes!r}",
                        code="FRESHNESS_FIXTURE_INVALID",
                    )
        self._jds = jds
        by_id: dict[str, list[JdVersion]] = {}
        for jd in jds:
            by_id.setdefault(jd.jd_id, []).append(jd)
        self._jds_by_id = by_id

    def _load_scenarios(self, payload: dict[str, Any]) -> None:
        _reject_unknown_keys(
            payload,
            frozenset(
                {
                    "schema_version",
                    "domain_id",
                    "domain_version",
                    "provenance",
                    "knowledge_scenarios",
                    "jd_scenarios",
                    "jd_change_scenarios",
                }
            ),
            "scenarios.json",
        )
        _require_schema(payload, "scenarios.json")
        if payload.get("domain_id") != DOMAIN_ID:
            raise ValidationError(
                f"scenarios.json.domain_id must be {DOMAIN_ID!r}",
                code="FRESHNESS_FIXTURE_INVALID",
            )
        _expect_str(payload.get("domain_version"), "scenarios.json.domain_version")
        self._load_provenance(payload, "scenarios.json")
        knowledge_scenarios: list[dict[str, Any]] = []
        for index, raw in enumerate(
            _expect_list(
                payload.get("knowledge_scenarios"),
                "scenarios.json.knowledge_scenarios",
                min_length=6,
            )
        ):
            where = f"scenarios.json.knowledge_scenarios[{index}]"
            entry = _expect_mapping(raw, where)
            _reject_unknown_keys(
                entry,
                frozenset(
                    {
                        "scenario_id",
                        "old_version_id",
                        "new_version_id",
                        "expected_change_kind",
                        "expected_reason_code",
                        "expected_map_code",
                        "expected_curriculum_eligible",
                        "expected_recheck_required",
                    }
                ),
                where,
            )
            old_id = _expect_str(entry.get("old_version_id"), f"{where}.old_version_id")
            new_id = _expect_str(entry.get("new_version_id"), f"{where}.new_version_id")
            for version_id in (old_id, new_id):
                if version_id not in self._versions:
                    raise ValidationError(
                        f"{where}: unknown version_id {version_id!r}",
                        code="FRESHNESS_FIXTURE_INVALID",
                    )
            map_code = entry.get("expected_map_code")
            if map_code is not None:
                map_code = _expect_str(map_code, f"{where}.expected_map_code")
            knowledge_scenarios.append(
                {
                    "scenario_id": _expect_str(entry.get("scenario_id"), f"{where}.scenario_id"),
                    "old_version_id": old_id,
                    "new_version_id": new_id,
                    "expected_change_kind": _expect_enum(
                        entry.get("expected_change_kind"),
                        CHANGE_KINDS,
                        f"{where}.expected_change_kind",
                    ),
                    "expected_reason_code": _expect_str(
                        entry.get("expected_reason_code"), f"{where}.expected_reason_code"
                    ),
                    "expected_map_code": map_code,
                    "expected_curriculum_eligible": _expect_bool(
                        entry.get("expected_curriculum_eligible"),
                        f"{where}.expected_curriculum_eligible",
                    ),
                    "expected_recheck_required": _expect_bool(
                        entry.get("expected_recheck_required"),
                        f"{where}.expected_recheck_required",
                    ),
                }
            )
        jd_scenarios: list[dict[str, Any]] = []
        for index, raw in enumerate(
            _expect_list(payload.get("jd_scenarios"), "scenarios.json.jd_scenarios", min_length=1)
        ):
            where = f"scenarios.json.jd_scenarios[{index}]"
            entry = _expect_mapping(raw, where)
            _reject_unknown_keys(
                entry,
                frozenset(
                    {
                        "scenario_id",
                        "jd_id",
                        "now",
                        "expected_active_version",
                        "expected_allowed_for_new_plan",
                        "expected_reason_code",
                        "expected_map_code",
                    }
                ),
                where,
            )
            expected_active = entry.get("expected_active_version")
            if expected_active is not None:
                expected_active = _expect_str(
                    expected_active, f"{where}.expected_active_version"
                )
            map_code = entry.get("expected_map_code")
            if map_code is not None:
                map_code = _expect_str(map_code, f"{where}.expected_map_code")
            jd_id = _expect_str(entry.get("jd_id"), f"{where}.jd_id")
            if jd_id not in self._jds_by_id:
                raise ValidationError(
                    f"{where}: unknown jd_id {jd_id!r}", code="FRESHNESS_FIXTURE_INVALID"
                )
            jd_scenarios.append(
                {
                    "scenario_id": _expect_str(entry.get("scenario_id"), f"{where}.scenario_id"),
                    "jd_id": jd_id,
                    "now": _expect_timestamp(entry.get("now"), f"{where}.now"),
                    "expected_active_version": expected_active,
                    "expected_allowed_for_new_plan": _expect_bool(
                        entry.get("expected_allowed_for_new_plan"),
                        f"{where}.expected_allowed_for_new_plan",
                    ),
                    "expected_reason_code": _expect_str(
                        entry.get("expected_reason_code"), f"{where}.expected_reason_code"
                    ),
                    "expected_map_code": map_code,
                }
            )
        jd_change_scenarios: list[dict[str, Any]] = []
        for index, raw in enumerate(
            _expect_list(
                payload.get("jd_change_scenarios"),
                "scenarios.json.jd_change_scenarios",
                min_length=1,
            )
        ):
            where = f"scenarios.json.jd_change_scenarios[{index}]"
            entry = _expect_mapping(raw, where)
            _reject_unknown_keys(
                entry,
                frozenset(
                    {
                        "scenario_id",
                        "jd_id",
                        "old_version",
                        "new_version",
                        "expected_affects_running_sessions",
                        "expected_affects_new_plans",
                        "expected_reason_code",
                        "expected_delta_added_requirements",
                    }
                ),
                where,
            )
            jd_change_scenarios.append(
                {
                    "scenario_id": _expect_str(entry.get("scenario_id"), f"{where}.scenario_id"),
                    "jd_id": _expect_str(entry.get("jd_id"), f"{where}.jd_id"),
                    "old_version": _expect_str(entry.get("old_version"), f"{where}.old_version"),
                    "new_version": _expect_str(entry.get("new_version"), f"{where}.new_version"),
                    "expected_affects_running_sessions": _expect_bool(
                        entry.get("expected_affects_running_sessions"),
                        f"{where}.expected_affects_running_sessions",
                    ),
                    "expected_affects_new_plans": _expect_bool(
                        entry.get("expected_affects_new_plans"),
                        f"{where}.expected_affects_new_plans",
                    ),
                    "expected_reason_code": _expect_str(
                        entry.get("expected_reason_code"), f"{where}.expected_reason_code"
                    ),
                    "expected_delta_added_requirements": _expect_str_list(
                        entry.get("expected_delta_added_requirements"),
                        f"{where}.expected_delta_added_requirements",
                    ),
                }
            )
        self._knowledge_scenarios = knowledge_scenarios
        self._jd_scenarios = jd_scenarios
        self._jd_change_scenarios = jd_change_scenarios

    # -- read helpers ------------------------------------------------------
    def knowledge_versions(self) -> list[KnowledgeSourceVersion]:
        return list(self._versions.values())

    def version(self, version_id: str) -> KnowledgeSourceVersion:
        if type(version_id) is not str or not version_id.strip():
            raise ValidationError("version(): version_id must be a non-blank string")
        try:
            return self._versions[version_id]
        except KeyError:
            raise NotFoundError(f"version(): unknown version_id {version_id!r}") from None

    def knowledge_scenarios(self) -> list[dict[str, Any]]:
        return [dict(scenario) for scenario in self._knowledge_scenarios]

    def jd_versions(self, jd_id: str | None = None) -> list[JdVersion]:
        if jd_id is None:
            return list(self._jds)
        if type(jd_id) is not str or not jd_id.strip():
            raise ValidationError("jd_versions(): jd_id must be a non-blank string")
        return list(self._jds_by_id.get(jd_id, []))

    # -- classification ----------------------------------------------------
    def classify_pair(self, old_version_id: str, new_version_id: str) -> FreshnessDecision:
        """Classify ``new_version_id`` against ``old_version_id`` (fail closed)."""

        old = self.version(old_version_id)
        new = self.version(new_version_id)
        old_rank = SOURCE_TIERS[old.source_tier]
        new_rank = SOURCE_TIERS[new.source_tier]

        # Explicit time semantics: published_at is the source's own publication
        # time; observed_at is our retrieval time.
        future_dated = new.published_at > new.observed_at
        observed_after_old_valid = bool(
            old.valid_until is not None and new.observed_at > old.valid_until
        )
        observed_after_new_valid = bool(
            new.valid_until is not None and new.observed_at > new.valid_until
        )
        new_older = new.published_at < old.published_at
        hash_equal = old.content_hash == new.content_hash

        map_code: str | None = None
        if future_dated:
            change_kind = "RECHECK"
            reason_code = "RECHECK_FUTURE_DATED"
            map_code = MAP_E08_KNOWLEDGE_RECHECK_BLOCKED
        elif new.claim_status == "CONFLICT" or old.claim_status == "CONFLICT":
            change_kind = "RECHECK"
            reason_code = "RECHECK_CONFLICT"
            map_code = MAP_E09_KNOWLEDGE_CONFLICT_BLOCKED
        elif (
            new.claim_status == "EXPIRED"
            or old.claim_status == "EXPIRED"
            or observed_after_old_valid
            or observed_after_new_valid
        ):
            change_kind = "RECHECK"
            reason_code = "RECHECK_EXPIRED"
            map_code = MAP_E08_KNOWLEDGE_RECHECK_BLOCKED
        elif new_older:
            change_kind = "RECHECK"
            reason_code = "RECHECK_OLDER_SOURCE"
            map_code = MAP_E08_KNOWLEDGE_RECHECK_BLOCKED
        elif hash_equal:
            change_kind = "KEEP"
            reason_code = "KEEP_CONTENT_UNCHANGED"
        elif new.claim_status != "VERIFIED":
            change_kind = "RECHECK"
            reason_code = "RECHECK_UNVERIFIED_SOURCE"
            map_code = MAP_E08_KNOWLEDGE_RECHECK_BLOCKED
        elif not TIER_MAY_UPDATE_CURRICULUM[new.source_tier]:
            change_kind = "RECHECK"
            reason_code = "RECHECK_UNAUTHORITATIVE_SOURCE"
            map_code = MAP_E09_KNOWLEDGE_CONFLICT_BLOCKED
        elif new.published_at <= old.published_at:
            change_kind = "RECHECK"
            reason_code = "RECHECK_AMBIGUOUS_CHANGE"
            map_code = MAP_E08_KNOWLEDGE_RECHECK_BLOCKED
        else:
            authority_not_worse = new_rank >= old_rank
            authority_improved = (new_rank > old_rank) or (new.confidence > old.confidence + 1e-9)
            if authority_not_worse and authority_improved:
                change_kind = "UPDATE"
                reason_code = "UPDATE_VERIFIED_AUTHORITATIVE"
            else:
                change_kind = "RECHECK"
                reason_code = "RECHECK_LOWER_AUTHORITY"
                map_code = MAP_E08_KNOWLEDGE_RECHECK_BLOCKED

        if change_kind == "UPDATE":
            revision_claim = "VERIFIED"
        elif change_kind == "KEEP":
            revision_claim = old.claim_status
        elif reason_code == "RECHECK_CONFLICT":
            revision_claim = "CONFLICT"
        elif reason_code == "RECHECK_EXPIRED":
            revision_claim = "EXPIRED"
        else:
            revision_claim = "REPORTED"

        curriculum_eligible = bool(
            change_kind == "UPDATE"
            and revision_claim == "VERIFIED"
            and TIER_MAY_UPDATE_CURRICULUM[new.source_tier]
        )
        recheck_required = change_kind == "RECHECK"

        publish_delta = _seconds_between(old.published_at, new.published_at)
        observation_lag = _seconds_between(new.published_at, new.observed_at)
        notes = (
            f"decision={change_kind}; reason={reason_code}; "
            f"source_id={old.source_id}->{new.source_id}; "
            f"tier={old.source_tier}(rank={old_rank})->{new.source_tier}(rank={new_rank}); "
            f"confidence={old.confidence:.2f}->{new.confidence:.2f}; "
            f"published_at={old.published_at}->{new.published_at}; "
            f"observed_at={old.observed_at}->{new.observed_at}; "
            f"publish_delta_seconds={publish_delta}; observation_lag_seconds={observation_lag}; "
            f"old_valid_until={old.valid_until}; "
            f"observed_after_old_valid_until={str(observed_after_old_valid).lower()}; "
            f"published_after_observed={str(future_dated).lower()}; "
            f"content_hash_equal={str(hash_equal).lower()}; "
            "time_semantics=published_at is source publication time, observed_at is retrieval "
            "time; "
            f"curriculum_eligible={str(curriculum_eligible).lower()}"
        )
        if change_kind == "RECHECK":
            notes += "; recheck_required=true; RECHECK must not enter the curriculum silently"
        if "jd" in (old.source_tier, new.source_tier):
            notes += "; jd_change_does_not_imply_topic_popularity=true"

        return FreshnessDecision(
            source_id=new.source_id,
            old_version_id=old.version_id,
            new_version_id=new.version_id,
            change_kind=change_kind,
            claim_status=revision_claim,
            reason_code=reason_code,
            map_code=map_code,
            curriculum_eligible=curriculum_eligible,
            recheck_required=recheck_required,
            detected_at=new.observed_at,
            old_hash=old.content_hash,
            new_hash=new.content_hash,
            notes=notes,
        )

    def classify_all_scenarios(self) -> list[FreshnessDecision]:
        """Classify every knowledge scenario fixture in file order (deterministic)."""

        decisions: list[FreshnessDecision] = []
        for scenario in self._knowledge_scenarios:
            decision = self.classify_pair(
                scenario["old_version_id"], scenario["new_version_id"]
            )
            decisions.append(decision)
        return decisions

    def decisions_checksum(self) -> str:
        """Deterministic sha256 over the canonical decision payloads."""

        return _canonical_sha256([decision.to_dict() for decision in self.classify_all_scenarios()])

    def classify(self, request: KnowledgeFreshnessRequest) -> dict[str, Any]:
        """Protocol-compatible classification of a single re-observation request.

        ``KnowledgeFreshnessRequest`` carries no content digest, so a plain
        observation can never prove an ``UPDATE``.  It fails closed to
        ``RECHECK`` (except for a verified conflict/expiry, which is reported as
        such); this prevents silent curriculum pollution from partial data.
        """

        if not isinstance(request, KnowledgeFreshnessRequest):
            raise ValidationError(
                "classify(): expected a KnowledgeFreshnessRequest",
                code="FRESHNESS_INVALID_REQUEST",
            )
        if request.claim_status not in CLAIM_STATUSES:
            raise ValidationError(
                f"classify(): unknown claim_status {request.claim_status!r}",
                code="FRESHNESS_INVALID_REQUEST",
            )
        _expect_timestamp(request.observed_at, "KnowledgeFreshnessRequest.observed_at")
        versions = self._versions_by_source.get(request.source_id, [])
        if not versions:
            return {
                "source_id": request.source_id,
                "change_kind": "RECHECK",
                "claim_status": "REPORTED",
                "reason_code": "RECHECK_UNKNOWN_SOURCE",
                "map_code": MAP_E07_KNOWLEDGE_PROVENANCE_LOSS,
                "curriculum_eligible": False,
                "recheck_required": True,
                "detected_at": request.observed_at,
            }
        latest = versions[-1]
        if request.claim_status == "CONFLICT":
            change_kind, claim_status, reason_code, map_code = (
                "RECHECK",
                "CONFLICT",
                "RECHECK_CONFLICT",
                MAP_E09_KNOWLEDGE_CONFLICT_BLOCKED,
            )
        elif request.claim_status == "EXPIRED":
            change_kind, claim_status, reason_code, map_code = (
                "RECHECK",
                "EXPIRED",
                "RECHECK_EXPIRED",
                MAP_E08_KNOWLEDGE_RECHECK_BLOCKED,
            )
        else:
            change_kind, claim_status, reason_code, map_code = (
                "RECHECK",
                "REPORTED",
                "RECHECK_OBSERVATION_WITHOUT_DIGEST",
                MAP_E08_KNOWLEDGE_RECHECK_BLOCKED,
            )
        return {
            "source_id": request.source_id,
            "change_kind": change_kind,
            "claim_status": claim_status,
            "reason_code": reason_code,
            "map_code": map_code,
            "curriculum_eligible": False,
            "recheck_required": True,
            "detected_at": request.observed_at,
            "latest_version_id": latest.version_id,
        }

    # -- curriculum gate ---------------------------------------------------
    @staticmethod
    def curriculum_eligible(decision: FreshnessDecision) -> bool:
        if not isinstance(decision, FreshnessDecision):
            raise ValidationError("curriculum_eligible(): expected a FreshnessDecision")
        return decision.curriculum_eligible

    @staticmethod
    def recheck_required(decision: FreshnessDecision) -> bool:
        if not isinstance(decision, FreshnessDecision):
            raise ValidationError("recheck_required(): expected a FreshnessDecision")
        return decision.recheck_required

    def require_curriculum_eligible(self, decision: FreshnessDecision) -> None:
        """Fail closed when a non-eligible decision (RECHECK/conflict/etc.) is planned."""

        if not isinstance(decision, FreshnessDecision):
            raise ValidationError(
                "require_curriculum_eligible(): expected a FreshnessDecision",
                code="FRESHNESS_CURRICULUM_BLOCKED",
            )
        if decision.curriculum_eligible:
            return
        raise ValidationError(
            "knowledge decision is not eligible for the curriculum",
            code="FRESHNESS_CURRICULUM_BLOCKED",
            details={
                "reason_code": decision.reason_code,
                "map_code": decision.map_code,
                "change_kind": decision.change_kind,
                "recheck_required": decision.recheck_required,
            },
        )

    # -- JD window gate ----------------------------------------------------
    def active_jd(self, jd_id: str, now: str) -> JdGateDecision:
        """Return the single active JD version for new-plan creation at ``now``."""

        if type(jd_id) is not str or not jd_id.strip():
            raise ValidationError("active_jd(): jd_id must be a non-blank string")
        now = _expect_timestamp(now, "active_jd(now)")
        today = now[:10]
        versions = self._jds_by_id.get(jd_id, [])
        if not versions:
            return JdGateDecision(
                jd_id=jd_id,
                now=now,
                active_version=None,
                allowed_for_new_plan=False,
                reason_code="RECHECK_JD_UNKNOWN",
                map_code=MAP_E10_JD_EXPIRED_OR_CONFLICT,
                detail="no JD version is known for this jd_id; new plans are blocked",
            )
        active = [
            version
            for version in versions
            if version.valid_from <= today <= version.valid_until
        ]
        if len(active) > 1:
            return JdGateDecision(
                jd_id=jd_id,
                now=now,
                active_version=None,
                allowed_for_new_plan=False,
                reason_code="RECHECK_JD_CONFLICT",
                map_code=MAP_E10_JD_EXPIRED_OR_CONFLICT,
                detail=(
                    "multiple JD versions overlap the requested window "
                    f"({[version.version for version in active]}); human review required; "
                    "jd_change_does_not_imply_topic_popularity=true"
                ),
            )
        if len(active) == 1:
            version = active[0]
            return JdGateDecision(
                jd_id=jd_id,
                now=now,
                active_version=version.version,
                allowed_for_new_plan=True,
                reason_code="JD_ACTIVE",
                map_code=None,
                detail=(
                    f"active JD version {version.version!r} valid "
                    f"{version.valid_from}..{version.valid_until}; JD context affects new plans "
                    "only, never topic popularity or mastery"
                ),
            )
        all_expired = all(version.valid_until < today for version in versions)
        reason_code = "RECHECK_JD_EXPIRED" if all_expired else "RECHECK_JD_NOT_YET_ACTIVE"
        return JdGateDecision(
            jd_id=jd_id,
            now=now,
            active_version=None,
            allowed_for_new_plan=False,
            reason_code=reason_code,
            map_code=MAP_E10_JD_EXPIRED_OR_CONFLICT,
            detail=(
                "no JD version covers the requested time; new plans are blocked "
                f"(expired={all_expired})"
            ),
        )

    def jd_change_impact(
        self, jd_id: str, old_version: str, new_version: str
    ) -> JdChangeImpact:
        """Describe a JD version change: new plans only, never running sessions."""

        versions = {version.version: version for version in self._jds_by_id.get(jd_id, [])}
        if old_version not in versions or new_version not in versions:
            raise ValidationError(
                f"jd_change_impact(): unknown JD version for {jd_id!r}",
                code="FRESHNESS_JD_CHAIN_INVALID",
            )
        old = versions[old_version]
        new = versions[new_version]
        if new.supersedes != old.version:
            raise ValidationError(
                f"jd_change_impact(): {jd_id}@{new.version} does not supersede "
                f"{old.version!r}",
                code="FRESHNESS_JD_CHAIN_INVALID",
            )
        return JdChangeImpact(
            jd_id=jd_id,
            old_version=old.version,
            new_version=new.version,
            affects_running_sessions=False,
            affects_new_plans=True,
            reason_code="JD_CHANGE_NEW_PLANS_ONLY",
            delta={key: list(value) for key, value in new.delta.items()},
            detail=(
                "JD version change is hiring context for new plans only; running sessions keep "
                "their objective, no mastery update, no topic-popularity signal"
            ),
        )

    # -- scenario helpers --------------------------------------------------
    def jd_scenarios(self) -> list[dict[str, Any]]:
        return [dict(scenario) for scenario in self._jd_scenarios]

    def jd_change_scenarios(self) -> list[dict[str, Any]]:
        return [dict(scenario) for scenario in self._jd_change_scenarios]

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"KnowledgeFreshnessService(versions={len(self._versions)}, "
            f"jds={len(self._jds)}, fixtures_root={str(self._fixtures_root)!r})"
        )


def _seconds_between(earlier: str, later: str) -> int:
    """Whole seconds between two validated ``...Z`` timestamps (no wall clock)."""

    from datetime import datetime, timezone

    def parse(value: str) -> datetime:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)

    return int((parse(later) - parse(earlier)).total_seconds())


# Structural checks: the class is expected to satisfy the additive freshness port.
_ = KnowledgeFreshnessPort
