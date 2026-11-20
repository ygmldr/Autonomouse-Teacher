"""Fixture validation tests for the B-PR4 vertical interview/freshness data.

Validates the canonical ``m1a.v0`` vertical fixtures: teacher-visible question
metadata (no hidden rubric/expected material), hidden scoring specs under
``rubrics/scoring/`` (assessment-port only), versioned JD context, timestamped
knowledge versions, freshness scenarios and untrusted prompt-injection
documents.  All data is synthetic/CC0-1.0, offline and static.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_ROOT = REPO_ROOT / "fixtures" / "m1_teacher"
VERTICAL = FIXTURES_ROOT / "vertical"
INTERVIEW = VERTICAL / "interview"
FRESHNESS = VERTICAL / "freshness"
SCORING = INTERVIEW / "rubrics" / "scoring"

SCHEMA_VERSION = "m1a.v0"
DOMAIN_ID = "interview_coach"
STAGES = ("concept", "hypothesis", "complexity", "experiment_design", "online_triage")
CLAIM_STATUSES = {"VERIFIED", "REPORTED", "CONFLICT", "EXPIRED", "UNKNOWN"}
SOURCE_TIERS = {
    "official_document",
    "paper",
    "engineering_blog",
    "jd",
    "community",
    "mirror",
    "unknown",
}
HIDDEN_TOKENS = (
    "rubric_points",
    "rubrics/",
    "expectations",
    "reference_answer",
    "answer_key",
    "factual_correctness",
    "explanation_clarity",
    "engineering_feasibility",
    "evidence_sufficiency",
    "misconception",
)
TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
HASH_RE = re.compile(r"^[0-9a-f]{64}$")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical_sha256(value: object) -> str:
    blob = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(blob).hexdigest()


def _files() -> list[Path]:
    return sorted(VERTICAL.rglob("*.json"))


@pytest.fixture(scope="module")
def questions_doc() -> dict:
    return _load(INTERVIEW / "questions.json")


@pytest.fixture(scope="module")
def jds_doc() -> dict:
    return _load(INTERVIEW / "jds.json")


@pytest.fixture(scope="module")
def knowledge_doc() -> dict:
    return _load(INTERVIEW / "knowledge_sources.json")


@pytest.fixture(scope="module")
def scenarios_doc() -> dict:
    return _load(FRESHNESS / "scenarios.json")


# ---------------------------------------------------------------------------
# Teacher-visible questions
# ---------------------------------------------------------------------------


def test_teacher_visible_questions_doc_shape(questions_doc: dict) -> None:
    assert questions_doc["schema_version"] == SCHEMA_VERSION
    assert questions_doc["domain_id"] == DOMAIN_ID
    assert questions_doc["domain_version"] == "0.1.0"
    provenance = questions_doc["provenance"]
    assert provenance["synthetic"] is True
    assert provenance["license"] == "CC0-1.0"
    assert len(questions_doc["nodes"]) == 4
    assert len(questions_doc["edges"]) == 4
    assert len(questions_doc["objectives"]) == 4
    questions = questions_doc["questions"]
    assert len(questions) >= 20

    node_ids = {node["node_id"] for node in questions_doc["nodes"]}
    item_ids = {question["item_id"] for question in questions}
    question_ids = {question["question_id"] for question in questions}
    assert len(item_ids) == len(questions)
    assert len(question_ids) == len(questions)

    tracks = set()
    for question in questions:
        assert question["synthetic"] is True
        assert question["license"] == "CC0-1.0"
        assert question["item_id"] == f"interview.item.{question['question_id']}"
        assert question["item_type"] == "SHORT_ANSWER"
        assert question["deterministic"] is False
        assert question["assessment_mode"] == "RULE_RUBRIC"
        assert question["max_score"] == 1.0
        assert 1 <= question["difficulty"] <= 5
        assert question["prompt"].strip()
        assert set(question["node_ids"]) <= node_ids
        assert question["scoring_spec_ref"] == f"rubric/{question['question_id']}.json"
        assert "scoring/" not in question["scoring_spec_ref"]
        assert isinstance(question["requires_project_facts"], bool)
        ladder = question["follow_up_ladder"]
        assert [probe["stage"] for probe in ladder] == list(STAGES)
        assert len(ladder) == 5
        for probe in ladder:
            assert probe["prompt"].strip()
            assert probe["label"].strip()
        tracks.add(question["track"])
    assert tracks == {
        "recommendation_ctr",
        "ml_fundamentals",
        "engineering_metrics",
        "system_design",
    }
    assert any(question["requires_project_facts"] for question in questions)
    assert any(not question["requires_project_facts"] for question in questions)


def test_teacher_visible_files_contain_no_hidden_rubric_material(
    questions_doc: dict, jds_doc: dict, knowledge_doc: dict
) -> None:
    teacher_blobs = {
        "questions.json": json.dumps(questions_doc, ensure_ascii=False),
        "jds.json": json.dumps(jds_doc, ensure_ascii=False),
        "knowledge_sources.json": json.dumps(knowledge_doc, ensure_ascii=False),
    }
    for name, blob in teacher_blobs.items():
        lowered = blob.lower()
        for token in HIDDEN_TOKENS:
            assert token not in lowered, f"{name} leaks hidden token {token!r}"
        assert "rubrics/" not in blob
        assert "reference_answers" not in blob
    assert "rubrics" not in (INTERVIEW / "questions.json").read_text(encoding="utf-8")


def test_questions_hidden_scoring_specs_are_complete_and_isolated(questions_doc: dict) -> None:
    question_ids = {question["question_id"] for question in questions_doc["questions"]}
    spec_paths = sorted(SCORING.glob("*.json"))
    reference_files = {path for path in spec_paths if path.name == "reference_answers.json"}
    spec_files = [path for path in spec_paths if path.name != "reference_answers.json"]
    assert len(spec_files) == len(question_ids)
    assert {path.stem for path in spec_files} == question_ids

    for path in spec_files:
        spec = _load(path)
        assert spec["schema_version"] == SCHEMA_VERSION
        assert spec["scoring_version"] == "interview.rubric.v1"
        assert spec["hidden"] is True
        assert spec["synthetic"] is True
        assert spec["license"] == "CC0-1.0"
        assert spec["question_id"] == path.stem
        assert spec["open_answer"] is True
        assert spec["max_status"] == "PARTIAL"
        assert set(spec["expectations"]) == {
            "factual_correctness",
            "explanation_clarity",
            "engineering_feasibility",
            "evidence_sufficiency",
        }
        for groups in spec["expectations"].values():
            assert groups
            assert all(group and all(token.strip() for token in group) for group in groups)
        assert abs(sum(spec["weights"].values()) - 1.0) < 1e-6
        assert set(spec["weights"]) == set(spec["expectations"])
        assert 0.0 <= spec["thresholds"]["partial_min"] <= spec["thresholds"]["correct_min"] <= 1.0
        assert spec["thresholds"]["min_response_chars"] >= 1

    assert len(reference_files) == 1
    reference = _load(reference_files.pop())
    assert reference["hidden"] is True
    assert reference["synthetic"] is True
    answers = reference["answers"]
    assert len(answers) >= 8
    covered_questions = set()
    for answer in answers:
        assert answer["question_id"] in question_ids
        assert answer["response"]["text"].strip()
        covered_questions.add(answer["question_id"])
    assert len(answers) >= 8
    assert len(covered_questions) >= 7
    # Hidden answers are present only on the hidden side.
    assert reference["scoring_version"].startswith("interview.reference_answers")


# ---------------------------------------------------------------------------
# JD versions
# ---------------------------------------------------------------------------


def test_jd_versions_are_versioned_and_deltas_are_consistent(jds_doc: dict) -> None:
    assert jds_doc["schema_version"] == SCHEMA_VERSION
    assert jds_doc["provenance"]["synthetic"] is True
    versions = jds_doc["jds"]
    assert len(versions) >= 6
    by_key = {(jd["jd_id"], jd["version"]): jd for jd in versions}
    assert len(by_key) == len(versions)

    seen_digests = set()
    for jd in versions:
        assert jd["company_synthetic"] is True
        assert jd["synthetic"] is True
        assert jd["license"] == "CC0-1.0"
        assert DATE_RE.match(jd["valid_from"]) and DATE_RE.match(jd["valid_until"])
        assert jd["valid_from"] < jd["valid_until"]
        assert jd["requirements"] and jd["skills"]
        digest = jd["content_digest"]
        assert HASH_RE.match(digest)
        expected_digest = _canonical_sha256(
            {
                "jd_id": jd["jd_id"],
                "version": jd["version"],
                "role": jd["role"],
                "requirements": jd["requirements"],
                "skills": jd["skills"],
                "valid_from": jd["valid_from"],
                "valid_until": jd["valid_until"],
            }
        )
        assert digest == expected_digest
        seen_digests.add(digest)

        if jd["supersedes"] is not None:
            parent = by_key.get((jd["jd_id"], jd["supersedes"]))
            assert parent is not None
            old_requirements, new_requirements = (
                set(parent["requirements"]),
                set(jd["requirements"]),
            )
            old_skills, new_skills = set(parent["skills"]), set(jd["skills"])
            assert jd["delta"]["added_requirements"] == sorted(
                new_requirements - old_requirements
            )
            assert jd["delta"]["removed_requirements"] == sorted(
                old_requirements - new_requirements
            )
            assert jd["delta"]["added_skills"] == sorted(new_skills - old_skills)
            assert jd["delta"]["removed_skills"] == sorted(old_skills - new_skills)
        else:
            assert jd["delta"]["removed_requirements"] == []
            assert jd["delta"]["removed_skills"] == []
    assert len(seen_digests) == len(versions)


# ---------------------------------------------------------------------------
# Knowledge versions
# ---------------------------------------------------------------------------


def test_knowledge_versions_have_explicit_time_semantics(knowledge_doc: dict) -> None:
    assert knowledge_doc["schema_version"] == SCHEMA_VERSION
    assert knowledge_doc["provenance"]["synthetic"] is True
    versions = knowledge_doc["versions"]
    assert len(versions) >= 12
    by_id = {version["version_id"]: version for version in versions}
    assert len(by_id) == len(versions)

    by_hash: dict[str, list[dict]] = {}
    for version in versions:
        assert version["synthetic"] is True
        assert version["license"] == "CC0-1.0"
        assert TIMESTAMP_RE.match(version["published_at"])
        assert TIMESTAMP_RE.match(version["observed_at"])
        if version["valid_until"] is not None:
            assert TIMESTAMP_RE.match(version["valid_until"])
        assert version["claim_status"] in CLAIM_STATUSES
        assert version["source_tier"] in SOURCE_TIERS
        assert HASH_RE.match(version["content_hash"])
        assert version["version_id"] == f"{version['source_id']}::{version['observed_at']}"
        assert "://" not in version["uri"], "fixtures must not embed URL schemes"
        assert "@" not in version["uri"]
        host = version["uri"].split("/", 1)[0]
        assert host.endswith(".invalid"), "fixtures must use unreachable synthetic hosts"
        assert version["publisher"].startswith("Synthetic")
        expected_hash = _canonical_sha256(
            {
                "uri": version["uri"],
                "publisher": version["publisher"],
                "published_at": version["published_at"],
                "claim_status": version["claim_status"],
            }
        )
        assert version["content_hash"] == expected_hash
        by_hash.setdefault(version["content_hash"], []).append(version)

    # The KEEP scenarios must reference different version ids with equal content hashes.
    keep_pairs = [
        ("doc:pb-001", "doc:pb-001"),
        ("doc:tower-001", "mirror:tower-001"),
    ]
    for old_source, new_source in keep_pairs:
        old = next(v for v in versions if v["source_id"] == old_source and v["role"] == "old")
        new = next(v for v in versions if v["source_id"] == new_source and v["role"] == "new")
        assert old["version_id"] != new["version_id"]
        assert old["content_hash"] == new["content_hash"]
    assert len(by_hash) < len(versions)


# ---------------------------------------------------------------------------
# Freshness scenarios
# ---------------------------------------------------------------------------


def test_freshness_scenarios_reference_existing_versions(scenarios_doc: dict) -> None:
    assert scenarios_doc["schema_version"] == SCHEMA_VERSION
    knowledge = _load(INTERVIEW / "knowledge_sources.json")
    version_ids = {version["version_id"] for version in knowledge["versions"]}
    jds = _load(INTERVIEW / "jds.json")["jds"]
    jd_ids = {jd["jd_id"] for jd in jds}

    knowledge_scenarios = scenarios_doc["knowledge_scenarios"]
    assert len(knowledge_scenarios) >= 9
    kinds = set()
    map_codes = set()
    for scenario in knowledge_scenarios:
        assert scenario["old_version_id"] in version_ids
        assert scenario["new_version_id"] in version_ids
        assert scenario["expected_change_kind"] in {"KEEP", "UPDATE", "RECHECK"}
        kinds.add(scenario["expected_change_kind"])
        if scenario["expected_map_code"] is not None:
            assert scenario["expected_map_code"].startswith("MAP-E")
            map_codes.add(scenario["expected_map_code"])
        if scenario["expected_change_kind"] == "RECHECK":
            assert scenario["expected_recheck_required"] is True
            assert scenario["expected_curriculum_eligible"] is False
        if scenario["expected_change_kind"] == "UPDATE":
            assert scenario["expected_curriculum_eligible"] is True
    assert kinds == {"KEEP", "UPDATE", "RECHECK"}
    assert map_codes == {
        "MAP-E08_KNOWLEDGE_RECHECK_BLOCKED",
        "MAP-E09_KNOWLEDGE_CONFLICT_BLOCKED",
    }

    jd_scenarios = scenarios_doc["jd_scenarios"]
    assert len(jd_scenarios) >= 6
    reasons = set()
    for scenario in jd_scenarios:
        assert scenario["jd_id"] in jd_ids
        assert TIMESTAMP_RE.match(scenario["now"])
        reasons.add(scenario["expected_reason_code"])
        if scenario["expected_allowed_for_new_plan"] is False:
            assert scenario["expected_map_code"] == "MAP-E10_JD_EXPIRED_OR_CONFLICT"
    assert {
        "JD_ACTIVE",
        "RECHECK_JD_EXPIRED",
        "RECHECK_JD_NOT_YET_ACTIVE",
        "RECHECK_JD_CONFLICT",
    } <= reasons

    change_scenarios = scenarios_doc["jd_change_scenarios"]
    assert change_scenarios
    for scenario in change_scenarios:
        assert scenario["expected_affects_running_sessions"] is False
        assert scenario["expected_affects_new_plans"] is True
        assert scenario["expected_reason_code"] == "JD_CHANGE_NEW_PLANS_ONLY"


# ---------------------------------------------------------------------------
# Untrusted injection documents
# ---------------------------------------------------------------------------


def test_untrusted_injection_docs_are_data_only_and_never_teacher_visible() -> None:
    payload = _load(INTERVIEW / "untrusted" / "injection_docs.json")
    assert payload["untrusted"] is True
    assert payload["treatment"] == "DATA_ONLY"
    documents = payload["documents"]
    assert len(documents) >= 3
    for document in documents:
        assert document["expected_treatment"] == "DATA_ONLY"
        assert document["content"].strip()
        assert document["attack_type"].strip()
    blob = json.dumps(documents, ensure_ascii=False)
    assert "Ignore all previous instructions" in blob or "管理员权限" in blob
    teacher_text = " ".join(
        (INTERVIEW / name).read_text(encoding="utf-8")
        for name in ("questions.json", "jds.json", "knowledge_sources.json")
    )
    for document in documents:
        assert document["content"] not in teacher_text
    assert "injection_docs" not in teacher_text


# ---------------------------------------------------------------------------
# Round-trip / provenance / no-real-data guards
# ---------------------------------------------------------------------------


def test_all_vertical_json_files_roundtrip_and_are_cc0_synthetic() -> None:
    files = _files()
    assert files, "vertical fixture tree must not be empty"
    for path in files:
        raw_bytes = path.read_bytes()
        assert not raw_bytes.startswith(b"\xef\xbb\xbf"), f"{path}: UTF-8 BOM is not allowed"
        text = raw_bytes.decode("utf-8")
        payload = json.loads(text)
        assert json.loads(json.dumps(payload, ensure_ascii=False)) == payload
        if "provenance" in payload:
            assert payload["provenance"]["synthetic"] is True
            assert payload["provenance"]["license"] == "CC0-1.0"
        elif path.name == "reference_answers.json":
            assert payload["synthetic"] is True
            assert payload["license"] == "CC0-1.0"
        else:
            assert payload["synthetic"] is True
            assert payload["license"] == "CC0-1.0"


def test_no_network_or_real_personal_data_in_fixtures() -> None:
    for path in _files():
        text = path.read_text(encoding="utf-8")
        assert "://" not in text, f"{path}: URL schemes are not allowed in fixtures"
        assert "@" not in text, f"{path}: identity-like '@' shape is not allowed"
        assert not EMAIL_RE.search(text), f"{path}: email-like personal data found"
        lowered = text.lower()
        for forbidden in ("api_key", "access_key", "secret_key", "password", "authorization"):
            assert forbidden not in lowered


def test_expected_fixture_counts_cover_task_requirements() -> None:
    questions = _load(INTERVIEW / "questions.json")["questions"]
    specs = [
        path
        for path in SCORING.glob("*.json")
        if path.name != "reference_answers.json"
    ]
    jds = _load(INTERVIEW / "jds.json")["jds"]
    knowledge = _load(INTERVIEW / "knowledge_sources.json")["versions"]
    injections = _load(INTERVIEW / "untrusted" / "injection_docs.json")["documents"]
    answers = _load(SCORING / "reference_answers.json")["answers"]

    assert len(questions) >= 20
    assert len(specs) == len(questions)
    assert len(jds) >= 6
    assert len({(jd["jd_id"], jd["version"]) for jd in jds}) == len(jds)
    assert len(knowledge) >= 12
    assert len({version["source_id"] for version in knowledge}) >= 6
    assert len(injections) >= 3
    assert len(answers) >= 8
