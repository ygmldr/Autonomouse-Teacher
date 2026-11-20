"""Scorer-side interview rubric judge for the M1-B vertical layer (B-PR4).

This module is the **only** vertical component that may read the hidden
interview scoring material (``vertical/interview/rubrics/scoring/``).  It is
deliberately separate from the teacher-visible domain adapter and from the
frozen ``assessment/scorer.py`` (owned by another workstream):

* deterministic four-dimension rubric scoring over the hidden scoring spec
  (``factual_correctness``, ``explanation_clarity``,
  ``engineering_feasibility``, ``evidence_sufficiency``), computed
  independently from disjoint feature sets;
* conservative open-answer semantics: an ``OPEN_ANSWER`` (``SHORT_ANSWER`` long
  form) can reach at most ``PARTIAL``; ``NEEDS_REVIEW`` is returned when the
  evidence cannot support a deterministic verdict (too short, project facts
  required but missing); ``EVAL_ERROR`` is returned for hidden-spec
  infrastructure problems and must not be treated as learner evidence;
* no runtime, network, repository or learner-model import: scoring can never
  write mastery and never uses the coach's own text as evidence;
* hidden material never leaks into teacher-visible outputs: results carry only
  status/score/codes and a spec digest, while per-dimension scores live in an
  assessment-port sidecar (:class:`InterviewAssessmentDetail`) that is not part
  of the frozen ``m1a.v0`` teacher-visible records.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..contracts.errors import NotFoundError, ValidationError
from ..contracts.types import AssessmentItem, AssessmentResult

__all__ = [
    "DIMENSIONS",
    "FIXTURE_CLOCK",
    "SCORER_ID",
    "InterviewAssessmentDetail",
    "InterviewRubricJudge",
    "default_fixtures_root",
]

SCHEMA_VERSION = "m1a.v0"
SCORER_ID = "interview.rubric.m1offline.v1"
SCORING_VERSION = "interview.rubric.v1"
FIXTURE_CLOCK = "2026-11-20T00:00:00Z"
FIXTURES_ENV_VAR = "M1_TEACHER_FIXTURES"
DEFAULT_FIXTURES_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "m1_teacher"

DIMENSIONS: tuple[str, ...] = (
    "factual_correctness",
    "explanation_clarity",
    "engineering_feasibility",
    "evidence_sufficiency",
)

_HIDDEN_SUBDIR = Path("vertical") / "interview" / "rubrics"
_ITEM_PREFIX = "interview.item."
_SPEC_REF_RE = re.compile(r"^scoring/[A-Za-z0-9_.-]+\.json$")
_SENTENCE_SPLIT_RE = re.compile(r"[。！？!?；;\n]+")
_MAGNITUDE_RE = re.compile(
    r"\d+(?:\.\d+)?\s*(?:ms|毫秒|秒|s|QPS|qps|万|亿|GB|TB|核|台|倍|%|％)"
)
_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")

_ALLOWED_SPEC_KEYS = frozenset(
    {
        "schema_version",
        "scoring_version",
        "question_id",
        "hidden",
        "synthetic",
        "license",
        "domain_id",
        "open_answer",
        "max_status",
        "requires_project_facts",
        "weights",
        "thresholds",
        "misconception_penalty",
        "expectations",
        "clarity_connectors",
        "vague_words",
        "infeasible_markers",
        "unsourced_claim_patterns",
    }
)
_ALLOWED_THRESHOLD_KEYS = frozenset(
    {"factual_min", "correct_min", "partial_min", "min_response_chars"}
)
_ALLOWED_OPEN_ANSWER_TYPES = frozenset({"SHORT_ANSWER"})


class _SpecError(Exception):
    """Internal hidden-spec failure; mapped to ``EVAL_ERROR`` (never learner blame)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


# ---------------------------------------------------------------------------
# Strict validators
# ---------------------------------------------------------------------------


def _expect_mapping(value: Any, where: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise ValidationError(f"{where}: expected an object, got {type(value).__name__}")
    return value


def _expect_list(value: Any, where: str) -> list[Any]:
    if type(value) is not list:
        raise ValidationError(f"{where}: expected a list, got {type(value).__name__}")
    return value


def _expect_str(value: Any, where: str, *, allow_empty: bool = False) -> str:
    if type(value) is not str:
        raise ValidationError(f"{where}: expected str, got {type(value).__name__}")
    if not allow_empty and not value.strip():
        raise ValidationError(f"{where}: expected a non-blank string")
    return value


def _expect_bool(value: Any, where: str) -> bool:
    if type(value) is not bool:
        raise ValidationError(f"{where}: expected bool, got {type(value).__name__}")
    return value


def _expect_number(
    value: Any, where: str, *, minimum: float, maximum: float
) -> float:
    if type(value) not in (int, float):
        raise ValidationError(f"{where}: expected a number, got {type(value).__name__}")
    number = float(value)
    if not minimum <= number <= maximum:
        raise ValidationError(f"{where}: expected within [{minimum}, {maximum}], got {number}")
    return number


def _expect_str_groups(value: Any, where: str) -> list[tuple[str, ...]]:
    groups: list[tuple[str, ...]] = []
    for index, raw_group in enumerate(_expect_list(value, where)):
        group_where = f"{where}[{index}]"
        tokens: list[str] = []
        for token_index, raw_token in enumerate(_expect_list(raw_group, group_where)):
            token = _expect_str(raw_token, f"{group_where}[{token_index}]")
            tokens.append(token.lower())
        if not tokens:
            raise ValidationError(f"{group_where}: expected at least one token")
        groups.append(tuple(tokens))
    return groups


def _expect_str_list(value: Any, where: str) -> list[str]:
    return [
        _expect_str(entry, f"{where}[{index}]")
        for index, entry in enumerate(_expect_list(value, where))
    ]


def _expect_regex_list(value: Any, where: str) -> list[re.Pattern[str]]:
    patterns: list[re.Pattern[str]] = []
    for index, raw in enumerate(_expect_str_list(value, where)):
        try:
            patterns.append(re.compile(raw))
        except re.error as exc:
            raise ValidationError(f"{where}[{index}]: invalid regex: {exc}") from exc
    return patterns


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _round(value: float) -> float:
    return round(_clamp(value), 4)


def _coverage(groups: list[tuple[str, ...]], text_lower: str) -> float:
    if not groups:
        return 0.0
    hits = sum(1 for group in groups if any(token in text_lower for token in group))
    return hits / len(groups)


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
# Sidecar detail (assessment-port only; not a frozen teacher-visible record)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class InterviewAssessmentDetail:
    """Per-dimension sidecar detail for one interview assessment.

    Not part of ``m1a.v0``: kept by the assessment port so the teacher-visible
    :class:`~m1_teacher.contracts.types.AssessmentResult` stays frozen.  It never
    contains hidden expectation tokens, expected answers or spec bodies.
    """

    assessment_id: str
    question_id: str
    scorer_id: str
    status: str
    dimensions: dict[str, float]
    failure_modes: tuple[str, ...]
    spec_digest: str
    open_answer: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "assessment_id": self.assessment_id,
            "question_id": self.question_id,
            "scorer_id": self.scorer_id,
            "status": self.status,
            "dimensions": dict(self.dimensions),
            "failure_modes": list(self.failure_modes),
            "spec_digest": self.spec_digest,
            "open_answer": self.open_answer,
        }


# ---------------------------------------------------------------------------
# Judge
# ---------------------------------------------------------------------------


class InterviewRubricJudge:
    """Deterministic, hidden-spec-based interview rubric scorer (scorer-side)."""

    scorer_id: str = SCORER_ID
    SCORER_ID = SCORER_ID

    def __init__(self, fixtures_root: str | Path | None = None, *, clock: str = FIXTURE_CLOCK) -> None:
        root = fixtures_root if fixtures_root is not None else default_fixtures_root()
        self._fixtures_root = _coerce_fixtures_root(root)
        self._hidden_dir = (self._fixtures_root / _HIDDEN_SUBDIR).resolve()
        if not self._hidden_dir.is_dir():
            raise NotFoundError(f"hidden interview scoring directory not found: {self._hidden_dir}")
        if type(clock) is not str or not clock.strip():
            raise ValidationError("clock must be a non-blank ISO-8601 timestamp string")
        self._clock = clock
        self._spec_cache: dict[str, tuple[dict[str, Any], str]] = {}
        self._details: dict[str, InterviewAssessmentDetail] = {}

    # -- public API --------------------------------------------------------
    def assess(
        self,
        item: AssessmentItem,
        learner_id: str,
        response: str | dict,
        *,
        result_id: str | None = None,
    ) -> AssessmentResult:
        """Score one open-answer response against the hidden interview spec."""

        if not isinstance(item, AssessmentItem):
            raise ValidationError("assess(): expected an AssessmentItem")
        if item.item_type not in _ALLOWED_OPEN_ANSWER_TYPES:
            raise ValidationError(
                f"assess(): only open-answer items are supported, got item_type "
                f"{item.item_type!r}"
            )
        learner_id = _expect_str(learner_id, "assess(learner_id)")
        if result_id is not None:
            result_id = _expect_str(result_id, "assess(result_id)")
        text, parsed = self._parse_response(response)
        if result_id is None:
            result_id = self._result_id(item, learner_id, response)

        try:
            spec, spec_digest = self._load_spec(item)
        except _SpecError as exc:
            return self._eval_error(item, learner_id, result_id, exc.code)

        max_score = float(item.max_score) if item.max_score > 0.0 else 1.0
        dimensions, failure_modes = self._score(item, spec, text, parsed)
        weights = spec["weights"]
        weighted = _round(
            sum(weights[dimension] * dimensions[dimension] for dimension in DIMENSIONS)
        )
        thresholds = spec["thresholds"]
        open_answer = bool(spec["open_answer"])
        requires_project_facts = bool(spec["requires_project_facts"])

        if len(text.strip()) < int(thresholds["min_response_chars"]):
            status = "NEEDS_REVIEW"
            failure_reason = "NEEDS_REVIEW:INTERVIEW_RESPONSE_TOO_SHORT"
            score: float | None = weighted
        elif requires_project_facts and not parsed["project_facts"]:
            status = "NEEDS_REVIEW"
            failure_reason = "NEEDS_REVIEW:PROJECT_FACTS_REQUIRED"
            score = weighted
        elif (
            dimensions["factual_correctness"] < float(thresholds["factual_min"])
            or weighted < float(thresholds["partial_min"])
        ):
            status = "INCORRECT"
            failure_reason = "INCORRECT:INTERVIEW_RUBRIC"
            score = weighted
        elif open_answer:
            # Open-ended answers can never be claimed as CORRECT.
            status = "PARTIAL"
            failure_reason = "PARTIAL:INTERVIEW_RUBRIC_OPEN_ANSWER"
            score = weighted
        elif weighted >= float(thresholds["correct_min"]):
            status = "CORRECT"
            failure_reason = ""
            score = weighted
        else:
            status = "PARTIAL"
            failure_reason = "PARTIAL:INTERVIEW_RUBRIC"
            score = weighted

        result = AssessmentResult(
            result_id=result_id,
            item_id=item.item_id,
            learner_id=learner_id,
            status=status,
            score=score,
            max_score=max_score,
            scorer_id=self.scorer_id,
            failure_reason=failure_reason,
            evidence_refs=[
                f"item:{item.item_id}",
                f"spec-sha256:{spec_digest[:16]}",
            ],
            created_at=self._clock,
        )
        self._details[result_id] = InterviewAssessmentDetail(
            assessment_id=result_id,
            question_id=spec["question_id"],
            scorer_id=self.scorer_id,
            status=status,
            dimensions={dimension: dimensions[dimension] for dimension in DIMENSIONS},
            failure_modes=tuple(failure_modes),
            spec_digest=spec_digest,
            open_answer=open_answer,
        )
        return result

    def detail(self, result_id: str) -> InterviewAssessmentDetail | None:
        """Return the sidecar detail for a scored result (``None`` for EVAL_ERROR)."""

        if type(result_id) is not str or not result_id.strip():
            raise ValidationError("detail(): result_id must be a non-blank string")
        return self._details.get(result_id)

    def spec_digest(self, item: AssessmentItem) -> str:
        """Return the sha256 digest of the hidden spec behind ``item`` (opaque)."""

        if not isinstance(item, AssessmentItem):
            raise ValidationError("spec_digest(): expected an AssessmentItem")
        try:
            _spec, digest = self._load_spec(item)
        except _SpecError as exc:
            raise ValidationError(
                f"spec_digest(): hidden spec unavailable ({exc.code})"
            ) from None
        return digest

    # -- hidden spec loading ----------------------------------------------
    def _spec_path(self, item: AssessmentItem) -> Path:
        ref = item.scoring_spec_ref
        if type(ref) is not str or not _SPEC_REF_RE.match(ref):
            raise _SpecError("INTERVIEW_SPEC_REF_INVALID")
        candidate = (self._hidden_dir / ref).resolve()
        expected_parent = (self._hidden_dir / "scoring").resolve()
        if candidate.parent != expected_parent:
            raise _SpecError("INTERVIEW_SPEC_PATH_ESCAPE")
        return candidate

    def _load_spec(self, item: AssessmentItem) -> tuple[dict[str, Any], str]:
        path = self._spec_path(item)
        cache_key = str(path)
        if cache_key in self._spec_cache:
            return self._spec_cache[cache_key]
        if not path.is_file():
            raise _SpecError("INTERVIEW_SPEC_MISSING")
        try:
            raw_bytes = path.read_bytes()
        except OSError:  # pragma: no cover - filesystem failure
            raise _SpecError("INTERVIEW_SPEC_UNREADABLE") from None
        try:
            payload = json.loads(raw_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise _SpecError("INTERVIEW_SPEC_INVALID_JSON") from None
        spec = self._validate_spec(payload, item)
        digest = hashlib.sha256(raw_bytes).hexdigest()
        self._spec_cache[cache_key] = (spec, digest)
        return spec, digest

    def _validate_spec(self, payload: Any, item: AssessmentItem) -> dict[str, Any]:
        if type(payload) is not dict:
            raise _SpecError("INTERVIEW_SPEC_INVALID")
        unknown = sorted(set(payload) - _ALLOWED_SPEC_KEYS)
        if unknown:
            raise _SpecError("INTERVIEW_SPEC_UNKNOWN_FIELDS")
        if payload.get("schema_version") != SCHEMA_VERSION:
            raise _SpecError("INTERVIEW_SPEC_SCHEMA_VERSION")
        if payload.get("scoring_version") != SCORING_VERSION:
            raise _SpecError("INTERVIEW_SPEC_SCORING_VERSION")
        derived_question_id = item.item_id[len(_ITEM_PREFIX) :] if item.item_id.startswith(_ITEM_PREFIX) else ""
        if type(payload.get("question_id")) is not str or payload["question_id"] != derived_question_id:
            raise _SpecError("INTERVIEW_SPEC_QUESTION_MISMATCH")
        if payload.get("hidden") is not True:
            raise _SpecError("INTERVIEW_SPEC_NOT_HIDDEN")
        if type(payload.get("open_answer")) is not bool:
            raise _SpecError("INTERVIEW_SPEC_INVALID")
        if payload.get("max_status") not in ("PARTIAL", "CORRECT"):
            raise _SpecError("INTERVIEW_SPEC_INVALID")

        raw_weights = payload.get("weights")
        if type(raw_weights) is not dict or set(raw_weights) != set(DIMENSIONS):
            raise _SpecError("INTERVIEW_SPEC_WEIGHTS_INVALID")
        weights: dict[str, float] = {}
        for dimension in DIMENSIONS:
            value = raw_weights[dimension]
            if type(value) not in (int, float) or not 0.0 <= float(value) <= 1.0:
                raise _SpecError("INTERVIEW_SPEC_WEIGHTS_INVALID")
            weights[dimension] = float(value)
        if abs(sum(weights.values()) - 1.0) > 1e-6:
            raise _SpecError("INTERVIEW_SPEC_WEIGHTS_INVALID")

        raw_thresholds = payload.get("thresholds")
        if type(raw_thresholds) is not dict or set(raw_thresholds) != _ALLOWED_THRESHOLD_KEYS:
            raise _SpecError("INTERVIEW_SPEC_THRESHOLDS_INVALID")
        thresholds: dict[str, float] = {}
        for key in _ALLOWED_THRESHOLD_KEYS:
            value = raw_thresholds[key]
            if type(value) not in (int, float):
                raise _SpecError("INTERVIEW_SPEC_THRESHOLDS_INVALID")
            thresholds[key] = float(value)
        if not 0.0 <= thresholds["partial_min"] <= thresholds["correct_min"] <= 1.0:
            raise _SpecError("INTERVIEW_SPEC_THRESHOLDS_INVALID")
        if not 0.0 <= thresholds["factual_min"] <= 1.0:
            raise _SpecError("INTERVIEW_SPEC_THRESHOLDS_INVALID")
        if thresholds["min_response_chars"] < 1:
            raise _SpecError("INTERVIEW_SPEC_THRESHOLDS_INVALID")

        raw_expectations = payload.get("expectations")
        if type(raw_expectations) is not dict or set(raw_expectations) != set(DIMENSIONS):
            raise _SpecError("INTERVIEW_SPEC_EXPECTATIONS_INVALID")
        expectations = {
            dimension: _expect_str_groups(
                raw_expectations[dimension], f"spec.expectations.{dimension}"
            )
            for dimension in DIMENSIONS
        }
        try:
            connectors = _expect_str_list(
                payload.get("clarity_connectors"), "spec.clarity_connectors"
            )
            vague_words = _expect_str_list(payload.get("vague_words"), "spec.vague_words")
            infeasible_markers = _expect_str_list(
                payload.get("infeasible_markers"), "spec.infeasible_markers"
            )
            unsourced_patterns = _expect_regex_list(
                payload.get("unsourced_claim_patterns"), "spec.unsourced_claim_patterns"
            )
            misconception_penalty = _expect_number(
                payload.get("misconception_penalty"),
                "spec.misconception_penalty",
                minimum=0.0,
                maximum=1.0,
            )
        except ValidationError:
            raise _SpecError("INTERVIEW_SPEC_INVALID") from None

        return {
            "question_id": payload["question_id"],
            "open_answer": bool(payload["open_answer"]),
            "requires_project_facts": payload.get("requires_project_facts") is True,
            "weights": weights,
            "thresholds": thresholds,
            "expectations": expectations,
            "clarity_connectors": connectors,
            "vague_words": vague_words,
            "infeasible_markers": infeasible_markers,
            "unsourced_claim_patterns": unsourced_patterns,
            "misconception_penalty": misconception_penalty,
        }

    # -- response + scoring ------------------------------------------------
    @staticmethod
    def _parse_response(response: str | dict) -> tuple[str, dict[str, Any]]:
        if type(response) is str:
            return response, {
                "evidence_refs": [],
                "project_facts": [],
                "quantitative_claims": [],
                "misconceptions": [],
            }
        if type(response) is not dict:
            raise ValidationError(
                f"assess(response): expected str or dict, got {type(response).__name__}"
            )
        text = response.get("text", "")
        if type(text) is not str:
            raise ValidationError("assess(response['text']): expected str")
        evidence_refs = [
            entry
            for entry in response.get("evidence_refs", []) or []
            if type(entry) is str and entry.strip()
        ]
        project_facts = [
            entry
            for entry in response.get("project_facts", []) or []
            if type(entry) is str and entry.strip()
        ]
        claims: list[dict[str, Any]] = []
        for raw_claim in response.get("quantitative_claims", []) or []:
            if type(raw_claim) is not dict:
                continue
            statement = raw_claim.get("statement", "")
            if type(statement) is not str or not statement.strip():
                continue
            refs = [
                entry
                for entry in raw_claim.get("evidence_refs", []) or []
                if type(entry) is str and entry.strip()
            ]
            claims.append({"statement": statement, "evidence_refs": refs})
        misconceptions = [
            entry
            for entry in response.get("misconceptions", []) or []
            if type(entry) is str and entry.strip()
        ]
        return text, {
            "evidence_refs": evidence_refs,
            "project_facts": project_facts,
            "quantitative_claims": claims,
            "misconceptions": misconceptions,
        }

    @staticmethod
    def _score(
        item: AssessmentItem,
        spec: dict[str, Any],
        text: str,
        parsed: dict[str, Any],
    ) -> tuple[dict[str, float], list[str]]:
        text_lower = text.lower()
        expectations = spec["expectations"]

        # -- factual correctness: expected concept groups only -----------
        factual = _coverage(expectations["factual_correctness"], text_lower)
        factual -= spec["misconception_penalty"] * min(len(parsed["misconceptions"]), 2)
        factual = _round(factual)

        # -- explanation clarity: structural signals only -----------------
        length = len(text.strip())
        if length >= 120:
            length_score = 1.0
        elif length >= 60:
            length_score = 0.8
        elif length >= 30:
            length_score = 0.5
        elif length >= 10:
            length_score = 0.25
        else:
            length_score = 0.0
        sentences = [part for part in _SENTENCE_SPLIT_RE.split(text) if part.strip()]
        sentence_score = min(1.0, len(sentences) / 4.0)
        connector_hits = sum(1 for token in spec["clarity_connectors"] if token in text)
        connector_score = min(1.0, connector_hits / 3.0)
        paragraph_score = 1.0 if "\n\n" in text else 0.0
        vague_hits = sum(text.count(word) for word in spec["vague_words"])
        vague_penalty = min(0.4, 0.08 * vague_hits)
        clarity = _round(
            0.25 * length_score
            + 0.20 * sentence_score
            + 0.30 * connector_score
            + 0.10 * paragraph_score
            + 0.15 * _coverage(expectations["explanation_clarity"], text_lower)
            - vague_penalty
        )

        # -- engineering feasibility: constraints + magnitude + markers ---
        magnitude_hits = len(_MAGNITUDE_RE.findall(text))
        magnitude_score = min(1.0, magnitude_hits / 3.0)
        infeasible_hits = sum(1 for marker in spec["infeasible_markers"] if marker in text)
        feasibility = _round(
            0.6 * _coverage(expectations["engineering_feasibility"], text_lower)
            + 0.4 * magnitude_score
            - min(0.8, 0.3 * infeasible_hits)
        )

        # -- evidence sufficiency: refs/project facts/claims --------------
        refs = parsed["evidence_refs"]
        project_facts = parsed["project_facts"]
        claims = parsed["quantitative_claims"]
        unsourced_claims = [claim for claim in claims if not claim["evidence_refs"]]
        free_claims: list[str] = []
        for pattern in spec["unsourced_claim_patterns"]:
            free_claims.extend(match.group(0) for match in pattern.finditer(text))
        covered_free = 0
        for snippet in free_claims:
            number_match = _NUMBER_RE.search(snippet)
            if number_match is None:
                continue
            number = number_match.group(0)
            if any(
                number in claim["statement"] and claim["evidence_refs"]
                for claim in claims
            ):
                covered_free += 1
        unsourced_total = len(unsourced_claims) + max(0, len(free_claims) - covered_free)
        sourced_ratio = 0.0
        if claims:
            sourced_ratio = (len(claims) - len(unsourced_claims)) / len(claims)
        evidence = (
            0.10
            + 0.25 * _coverage(expectations["evidence_sufficiency"], text_lower)
            + min(0.25, 0.10 * len(refs))
            + (0.15 if project_facts else 0.0)
            + 0.15 * sourced_ratio
        )
        if unsourced_total == 0 and (refs or project_facts or claims):
            evidence += 0.10
        evidence -= 0.20 * min(unsourced_total, 2)
        requires_project_facts = bool(spec["requires_project_facts"])
        if requires_project_facts and not project_facts:
            evidence -= 0.25
        evidence = _round(evidence)

        dimensions = {
            "factual_correctness": factual,
            "explanation_clarity": clarity,
            "engineering_feasibility": feasibility,
            "evidence_sufficiency": evidence,
        }

        failure_modes: list[str] = []
        thresholds = spec["thresholds"]
        if factual < thresholds["factual_min"]:
            failure_modes.append("incorrect_concept")
        if clarity < 0.5:
            failure_modes.append("vague_explanation")
        if infeasible_hits:
            failure_modes.append("infeasible_engineering_design")
        if unsourced_total:
            failure_modes.append("unsourced_quantitative_claim")
        if requires_project_facts and not project_facts:
            failure_modes.append("missing_project_facts")
        if evidence < 0.5:
            failure_modes.append("insufficient_evidence")
        if parsed["misconceptions"]:
            failure_modes.append("misconceived_claim")
        return dimensions, failure_modes

    # -- helpers -----------------------------------------------------------
    def _result_id(self, item: AssessmentItem, learner_id: str, response: str | dict) -> str:
        digest = _canonical_sha256(
            {
                "learner_id": learner_id,
                "item_id": item.item_id,
                "response": response,
                "scorer_id": self.scorer_id,
            }
        )
        return "interview.assess." + digest[:16]

    def _eval_error(
        self, item: AssessmentItem, learner_id: str, result_id: str, code: str
    ) -> AssessmentResult:
        max_score = float(item.max_score) if item.max_score > 0.0 else 1.0
        return AssessmentResult(
            result_id=result_id,
            item_id=item.item_id,
            learner_id=learner_id,
            status="EVAL_ERROR",
            score=None,
            max_score=max_score,
            scorer_id=self.scorer_id,
            failure_reason=f"EVAL_ERROR:{code}",
            evidence_refs=[f"item:{item.item_id}"],
            created_at=self._clock,
        )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"InterviewRubricJudge(scorer_id={self.scorer_id!r}, "
            f"hidden_dir={str(self._hidden_dir)!r})"
        )
