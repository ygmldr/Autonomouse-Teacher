"""Tests for the knowledge freshness / source-credibility service (B-PR4 vertical).

Covers: KnowledgeFreshnessPort structural compatibility, KEEP/UPDATE/RECHECK
classification over timestamped synthetic versions, explicit
published_at-vs-observed_at semantics, expired/conflict/future-dated/
unauthoritative gates that block curriculum entry, JD v1->v2 window gating
(new plans only), deterministic checksums, fail-closed fixture validation and
offline/single-writer isolation.
"""

from __future__ import annotations

import ast
import inspect
import json
import shutil
from pathlib import Path

import pytest

from m1_teacher.contracts.errors import NotFoundError, ValidationError
from m1_teacher.extensions.interfaces import KnowledgeFreshnessPort, KnowledgeFreshnessRequest
from m1_teacher.knowledge import freshness as freshness_module
from m1_teacher.knowledge.freshness import (
    CHANGE_KINDS,
    SOURCE_TIERS,
    TIER_MAY_UPDATE_CURRICULUM,
    KnowledgeFreshnessService,
    default_fixtures_root,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_ROOT = REPO_ROOT / "fixtures" / "m1_teacher"
INTERVIEW_DIR = FIXTURES_ROOT / "vertical" / "interview"
FRESHNESS_DIR = FIXTURES_ROOT / "vertical" / "freshness"


def _service() -> KnowledgeFreshnessService:
    return KnowledgeFreshnessService(FIXTURES_ROOT)


@pytest.fixture(scope="module")
def service() -> KnowledgeFreshnessService:
    return KnowledgeFreshnessService(FIXTURES_ROOT)


# ---------------------------------------------------------------------------
# Fixture corpus / protocol
# ---------------------------------------------------------------------------


def test_service_satisfies_freshness_port(service: KnowledgeFreshnessService) -> None:
    assert isinstance(service, KnowledgeFreshnessPort)
    assert len(service.knowledge_versions()) >= 18
    assert len(service.knowledge_scenarios()) >= 9
    assert len(service.jd_versions()) >= 6
    assert len(service.jd_scenarios()) >= 6
    assert isinstance(service.decisions_checksum(), str)
    assert len(service.decisions_checksum()) == 64


def test_knowledge_version_fixtures_are_timestamped_and_synthetic(
    service: KnowledgeFreshnessService,
) -> None:
    seen_ids: set[str] = set()
    for version in service.knowledge_versions():
        assert version.version_id not in seen_ids
        seen_ids.add(version.version_id)
        assert version.published_at.endswith("Z")
        assert version.observed_at.endswith("Z")
        assert version.valid_until is None or version.valid_until.endswith("Z")
        assert 0.0 <= version.confidence <= 1.0
        assert version.claim_status in {
            "VERIFIED",
            "REPORTED",
            "CONFLICT",
            "EXPIRED",
            "UNKNOWN",
        }
        assert version.source_tier in SOURCE_TIERS
        assert version.content_hash and len(version.content_hash) == 64
        assert version.role in ("old", "new")


# ---------------------------------------------------------------------------
# Classification against the frozen expectations
# ---------------------------------------------------------------------------


def test_classify_matches_all_fixture_expectations(service: KnowledgeFreshnessService) -> None:
    scenarios = service.knowledge_scenarios()
    kinds: set[str] = set()
    for scenario in scenarios:
        decision = service.classify_pair(scenario["old_version_id"], scenario["new_version_id"])
        assert decision.change_kind == scenario["expected_change_kind"], scenario["scenario_id"]
        assert decision.reason_code == scenario["expected_reason_code"], scenario["scenario_id"]
        assert decision.map_code == scenario["expected_map_code"], scenario["scenario_id"]
        assert decision.curriculum_eligible is scenario["expected_curriculum_eligible"]
        assert decision.recheck_required is scenario["expected_recheck_required"]
        assert service.curriculum_eligible(decision) is scenario["expected_curriculum_eligible"]
        assert service.recheck_required(decision) is scenario["expected_recheck_required"]
        assert decision.change_kind in CHANGE_KINDS
        kinds.add(decision.change_kind)
    assert kinds == {"KEEP", "UPDATE", "RECHECK"}


def test_keep_has_identical_content_hash_and_no_curriculum_change(
    service: KnowledgeFreshnessService,
) -> None:
    for scenario in service.knowledge_scenarios():
        if scenario["expected_change_kind"] != "KEEP":
            continue
        decision = service.classify_pair(scenario["old_version_id"], scenario["new_version_id"])
        assert decision.old_hash == decision.new_hash
        assert decision.curriculum_eligible is False
        assert decision.map_code is None


def test_update_requires_verified_authoritative_newer_source(
    service: KnowledgeFreshnessService,
) -> None:
    updates = [
        decision
        for decision in service.classify_all_scenarios()
        if decision.change_kind == "UPDATE"
    ]
    assert len(updates) == 2
    for decision in updates:
        new_version = service.version(decision.new_version_id)
        old_version = service.version(decision.old_version_id)
        assert new_version.published_at > old_version.published_at
        assert new_version.claim_status == "VERIFIED"
        assert TIER_MAY_UPDATE_CURRICULUM[new_version.source_tier] is True
        assert decision.claim_status == "VERIFIED"
        assert decision.curriculum_eligible is True
        assert decision.recheck_required is False


@pytest.mark.parametrize(
    "scenario_id",
    [
        "k-recheck-expired-001",
        "k-recheck-conflict-001",
        "k-recheck-older-001",
        "k-recheck-community-001",
        "k-recheck-futuredate-001",
    ],
)
def test_recheck_gate_blocks_curriculum(
    service: KnowledgeFreshnessService, scenario_id: str
) -> None:
    scenario = next(
        entry for entry in service.knowledge_scenarios() if entry["scenario_id"] == scenario_id
    )
    decision = service.classify_pair(scenario["old_version_id"], scenario["new_version_id"])
    assert decision.change_kind == "RECHECK"
    assert decision.recheck_required is True
    assert decision.curriculum_eligible is False
    assert decision.map_code in {
        "MAP-E08_KNOWLEDGE_RECHECK_BLOCKED",
        "MAP-E09_KNOWLEDGE_CONFLICT_BLOCKED",
    }
    with pytest.raises(ValidationError) as excinfo:
        service.require_curriculum_eligible(decision)
    assert excinfo.value.code == "FRESHNESS_CURRICULUM_BLOCKED"
    assert excinfo.value.details["map_code"] == decision.map_code
    assert excinfo.value.details["reason_code"] == decision.reason_code


def test_expired_conflict_future_and_unauthoritative_specifics(
    service: KnowledgeFreshnessService,
) -> None:
    expired = service.classify_pair(
        next(s for s in service.knowledge_scenarios() if s["scenario_id"] == "k-recheck-expired-001")[
            "old_version_id"
        ],
        next(s for s in service.knowledge_scenarios() if s["scenario_id"] == "k-recheck-expired-001")[
            "new_version_id"
        ],
    )
    assert "observed_after_old_valid_until=true" in expired.notes
    assert expired.claim_status == "EXPIRED"

    conflict = service.classify_pair(
        next(s for s in service.knowledge_scenarios() if s["scenario_id"] == "k-recheck-conflict-001")[
            "old_version_id"
        ],
        next(s for s in service.knowledge_scenarios() if s["scenario_id"] == "k-recheck-conflict-001")[
            "new_version_id"
        ],
    )
    assert conflict.claim_status == "CONFLICT"
    assert "recheck_required=true" in conflict.notes

    future = service.classify_pair(
        next(s for s in service.knowledge_scenarios() if s["scenario_id"] == "k-recheck-futuredate-001")[
            "old_version_id"
        ],
        next(s for s in service.knowledge_scenarios() if s["scenario_id"] == "k-recheck-futuredate-001")[
            "new_version_id"
        ],
    )
    assert future.reason_code == "RECHECK_FUTURE_DATED"
    assert "published_after_observed=true" in future.notes

    community = service.classify_pair(
        next(s for s in service.knowledge_scenarios() if s["scenario_id"] == "k-recheck-community-001")[
            "old_version_id"
        ],
        next(s for s in service.knowledge_scenarios() if s["scenario_id"] == "k-recheck-community-001")[
            "new_version_id"
        ],
    )
    assert community.reason_code == "RECHECK_UNAUTHORITATIVE_SOURCE"
    assert TIER_MAY_UPDATE_CURRICULUM["community"] is False


def test_published_at_and_observed_at_are_explicit_and_distinct(
    service: KnowledgeFreshnessService,
) -> None:
    scenario = next(
        entry for entry in service.knowledge_scenarios() if entry["scenario_id"] == "k-update-001"
    )
    decision = service.classify_pair(scenario["old_version_id"], scenario["new_version_id"])
    new_version = service.version(decision.new_version_id)
    for token in (
        "published_at=",
        "observed_at=",
        "publish_delta_seconds=",
        "observation_lag_seconds=",
        "time_semantics=",
    ):
        assert token in decision.notes, token
    assert decision.detected_at == new_version.observed_at
    assert decision.detected_at != new_version.published_at
    assert "observed_after_old_valid_until=false" in decision.notes


def test_protocol_classify_is_fail_closed(service: KnowledgeFreshnessService) -> None:
    known = service.knowledge_versions()[0]
    request = KnowledgeFreshnessRequest(
        source_id=known.source_id,
        uri=known.uri,
        observed_at="2026-12-01T00:00:00Z",
        claim_status="VERIFIED",
    )
    result = service.classify(request)
    assert result["change_kind"] == "RECHECK", "a request without a digest can never prove UPDATE/KEEP"
    assert result["reason_code"] == "RECHECK_OBSERVATION_WITHOUT_DIGEST"
    assert result["curriculum_eligible"] is False

    conflict_request = KnowledgeFreshnessRequest(
        source_id=known.source_id,
        uri=known.uri,
        observed_at="2026-12-01T00:00:00Z",
        claim_status="CONFLICT",
    )
    conflict_result = service.classify(conflict_request)
    assert conflict_result["change_kind"] == "RECHECK"
    assert conflict_result["claim_status"] == "CONFLICT"
    assert conflict_result["map_code"] == "MAP-E09_KNOWLEDGE_CONFLICT_BLOCKED"

    unknown_request = KnowledgeFreshnessRequest(
        source_id="knowledge:does-not-exist",
        uri="https://docs.synthetic.invalid/x",
        observed_at="2026-12-01T00:00:00Z",
        claim_status="UNKNOWN",
    )
    unknown_result = service.classify(unknown_request)
    assert unknown_result["reason_code"] == "RECHECK_UNKNOWN_SOURCE"
    assert unknown_result["map_code"] == "MAP-E07_KNOWLEDGE_PROVENANCE_LOSS"

    with pytest.raises(ValidationError):
        service.classify({"source_id": known.source_id})  # type: ignore[arg-type]
    bad_status = KnowledgeFreshnessRequest(
        source_id=known.source_id,
        uri=known.uri,
        observed_at="2026-12-01T00:00:00Z",
        claim_status="NOT_A_STATUS",
    )
    with pytest.raises(ValidationError):
        service.classify(bad_status)


# ---------------------------------------------------------------------------
# Curriculum gate / determinism
# ---------------------------------------------------------------------------


def test_combined_decisions_gate_curriculum(service: KnowledgeFreshnessService) -> None:
    decisions = service.classify_all_scenarios()
    eligible = [decision for decision in decisions if service.curriculum_eligible(decision)]
    blocked = [decision for decision in decisions if service.recheck_required(decision)]
    assert len(decisions) == len(service.knowledge_scenarios())
    assert {decision.source_id for decision in eligible} == {"doc:auc-001", "paper:ns-001"}
    assert {decision.source_id for decision in blocked} == {
        "doc:cal-001",
        "community:post-009",
        "mirror:mtl-001",
        "community:cold-007",
        "doc:leak-001",
    }
    assert {decision.source_id for decision in eligible}.isdisjoint(
        {decision.source_id for decision in blocked}
    )
    for decision in eligible:
        assert service.curriculum_eligible(decision) is True
        service.require_curriculum_eligible(decision)  # must not raise
    for decision in blocked:
        with pytest.raises(ValidationError):
            service.require_curriculum_eligible(decision)


def test_decisions_are_deterministic() -> None:
    first, second = _service(), _service()
    assert first.classify_all_scenarios() == second.classify_all_scenarios()
    assert first.decisions_checksum() == second.decisions_checksum()
    assert first.decisions_checksum() == _service().decisions_checksum()
    json.dumps([decision.to_dict() for decision in first.classify_all_scenarios()], sort_keys=True)


# ---------------------------------------------------------------------------
# JD version gate (v1 -> v2, expiry, conflict, not-yet-active)
# ---------------------------------------------------------------------------


def test_jd_window_gate_matches_fixture_expectations(service: KnowledgeFreshnessService) -> None:
    scenarios = service.jd_scenarios()
    assert len(scenarios) >= 6
    active_versions = set()
    reasons = set()
    for scenario in scenarios:
        decision = service.active_jd(scenario["jd_id"], scenario["now"])
        assert decision.active_version == scenario["expected_active_version"], scenario["scenario_id"]
        assert decision.allowed_for_new_plan is scenario["expected_allowed_for_new_plan"]
        assert decision.reason_code == scenario["expected_reason_code"]
        assert decision.map_code == scenario["expected_map_code"]
        if decision.active_version is not None:
            active_versions.add(decision.active_version)
        if not decision.allowed_for_new_plan:
            reasons.add(decision.reason_code)
    assert active_versions == {"v1", "v2"}
    assert {"RECHECK_JD_EXPIRED", "RECHECK_JD_NOT_YET_ACTIVE", "RECHECK_JD_CONFLICT"} <= reasons


def test_jd_change_affects_new_plans_only(service: KnowledgeFreshnessService) -> None:
    scenarios = service.jd_change_scenarios()
    assert scenarios
    for scenario in scenarios:
        impact = service.jd_change_impact(
            scenario["jd_id"], scenario["old_version"], scenario["new_version"]
        )
        assert impact.affects_running_sessions is False
        assert impact.affects_new_plans is True
        assert impact.reason_code == "JD_CHANGE_NEW_PLANS_ONLY"
        assert impact.delta["added_requirements"] == scenario[
            "expected_delta_added_requirements"
        ]
        assert "no mastery update" in impact.detail
        assert "popularity" in impact.detail

    with pytest.raises(ValidationError) as excinfo:
        service.jd_change_impact("jd:rec", "v2", "v1")
    assert excinfo.value.code == "FRESHNESS_JD_CHAIN_INVALID"
    with pytest.raises(ValidationError):
        service.jd_change_impact("jd:rec", "v1", "v9")


def test_jd_versions_are_synthetic_and_chained(service: KnowledgeFreshnessService) -> None:
    versions = service.jd_versions()
    assert len(versions) >= 6
    by_key = {(version.jd_id, version.version): version for version in versions}
    assert len(by_key) == len(versions)
    for version in versions:
        assert version.valid_from < version.valid_until
        assert version.content_digest and len(version.content_digest) == 64
        if version.supersedes is not None:
            parent = by_key[(version.jd_id, version.supersedes)]
            assert parent.version == version.supersedes
            assert version.jd_id == parent.jd_id


# ---------------------------------------------------------------------------
# Fail-closed validation / offline guarantees
# ---------------------------------------------------------------------------


def test_corrupt_freshness_fixture_fails_closed(tmp_path: Path) -> None:
    root = tmp_path / "fixtures" / "m1_teacher"
    root.mkdir(parents=True)
    shutil.copytree(FIXTURES_ROOT / "vertical", root / "vertical")
    scenarios_path = root / "vertical" / "freshness" / "scenarios.json"
    original = json.loads(scenarios_path.read_text(encoding="utf-8"))
    broken = json.loads(json.dumps(original))
    broken["knowledge_scenarios"][0]["expected_change_kind"] = "NOT_A_KIND"
    scenarios_path.write_text(json.dumps(broken), encoding="utf-8")
    with pytest.raises(ValidationError) as excinfo:
        KnowledgeFreshnessService(root)
    assert excinfo.value.code == "FRESHNESS_FIXTURE_INVALID"

    broken = json.loads(json.dumps(original))
    broken["knowledge_scenarios"][0]["old_version_id"] = "missing@version"
    scenarios_path.write_text(json.dumps(broken), encoding="utf-8")
    with pytest.raises(ValidationError):
        KnowledgeFreshnessService(root)


def test_service_is_offline_and_has_no_learner_writer() -> None:
    source = inspect.getsource(freshness_module)
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported.isdisjoint({"httpx", "requests", "urllib", "socket", "aiohttp", "autoteacher_m0"})
    for forbidden_method in (
        "upsert_snapshot",
        "apply_assessment",
        "apply_result",
        "save_session",
    ):
        assert not hasattr(KnowledgeFreshnessService, forbidden_method)
    assert "now_utc" not in source  # no wall-clock reads: callers pass explicit timestamps


def test_default_fixtures_root_honours_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("M1_TEACHER_FIXTURES", str(tmp_path))
    assert default_fixtures_root() == tmp_path.resolve()
    monkeypatch.delenv("M1_TEACHER_FIXTURES")
    assert default_fixtures_root() == FIXTURES_ROOT.resolve()


def test_unknown_version_and_jd_lookups_fail_closed(service: KnowledgeFreshnessService) -> None:
    with pytest.raises(NotFoundError):
        service.version("missing@version")
    with pytest.raises(ValidationError):
        service.version("   ")
    with pytest.raises(ValidationError):
        service.curriculum_eligible("not-a-decision")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        service.recheck_required(object())  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        service.active_jd("jd:rec", "not-a-timestamp")
