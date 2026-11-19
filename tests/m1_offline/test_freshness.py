"""Tests for the knowledge freshness / source-credibility manager.

Coverage map (task-3 acceptance):
* KEEP / UPDATE / RECHECK classification for 6+ timestamped synthetic updates;
* ``published_at`` (source publication) vs ``observed_at`` (observation time)
  explicitly recorded, including observation lag and future-dated anomalies;
* expired / conflicting / older / lower-authority sources -> RECHECK that can
  never silently enter the main curriculum;
* credibility layering (official doc / paper / JD / community / mirror) with a
  doc-vs-code consistency check and "JD change != question popularity";
* deterministic, offline, type-strict behaviour.
"""

from __future__ import annotations

import inspect
import json
import re
from pathlib import Path

import pytest

from m1_offline.freshness import (
    FreshnessManager,
    SOURCE_TIERS,
    content_hash,
    infer_source_tier,
    source_layers,
)
from m1_offline.types import (
    CHANGE_KIND_VALUES,
    CLAIM_STATUS_VALUES,
    KnowledgeRevision,
    KnowledgeSource,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
KNOWLEDGE_DIR = REPO_ROOT / "fixtures" / "m1" / "interview" / "knowledge"
POLICY_DOC = REPO_ROOT / "docs" / "m1" / "FRESHNESS_AND_SOURCE_POLICY.md"

HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})$")
TIER_TABLE_RE = re.compile(r"^\|\s*([a-z_]+)\s*\|\s*(\d+)\s*\|", re.MULTILINE)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _all_knowledge() -> list[dict]:
    return [_load(path) for path in sorted(KNOWLEDGE_DIR.glob("*.json"))]


def _source(payload: dict) -> KnowledgeSource:
    return KnowledgeSource(**payload)


def _pair(fixture: dict) -> tuple[KnowledgeSource, KnowledgeSource]:
    return _source(fixture["old_source"]), _source(fixture["new_source"])


def _revision(fixture: dict) -> KnowledgeRevision:
    old, new = _pair(fixture)
    return FreshnessManager().classify(old, new)


@pytest.fixture(scope="module")
def manager() -> FreshnessManager:
    return FreshnessManager()


@pytest.fixture(scope="module")
def policy_doc() -> str:
    assert POLICY_DOC.is_file(), "FRESHNESS_AND_SOURCE_POLICY.md is part of the deliverable"
    return POLICY_DOC.read_text(encoding="utf-8")


def test_fixture_corpus_shape_and_timestamps() -> None:
    fixtures = _all_knowledge()
    assert len(fixtures) >= 6
    kinds = set()
    for fixture in fixtures:
        assert fixture["schema_version"] == "m1.offline.v0"
        assert fixture["synthetic"] is True
        assert fixture["license"] == "CC0-1.0"
        assert fixture["update_id"] and fixture["topic"]
        assert fixture["expected_change_kind"] in CHANGE_KIND_VALUES
        kinds.add(fixture["expected_change_kind"])
        for source in (fixture["old_source"], fixture["new_source"]):
            for field in ("source_id", "uri", "publisher", "published_at", "observed_at"):
                assert isinstance(source[field], str) and source[field]
            assert ISO_RE.match(source["published_at"]), source["published_at"]
            assert ISO_RE.match(source["observed_at"]), source["observed_at"]
            if source["valid_until"] is not None:
                assert ISO_RE.match(source["valid_until"])
            assert source["claim_status"] in CLAIM_STATUS_VALUES
            assert 0.0 <= source["confidence"] <= 1.0
    assert kinds == {"KEEP", "UPDATE", "RECHECK"}, "fixtures must cover all three outcomes"


def test_classify_matches_expected_change_kinds(manager: FreshnessManager) -> None:
    for fixture in _all_knowledge():
        revision = _revision(fixture)
        assert isinstance(revision, KnowledgeRevision)
        assert revision.change_kind == fixture["expected_change_kind"], fixture["update_id"]
        assert revision.change_kind in CHANGE_KIND_VALUES
        assert revision.claim_status in CLAIM_STATUS_VALUES
        assert revision.revision_id.startswith("rev-")
        assert HEX64_RE.match(revision.old_hash) and HEX64_RE.match(revision.new_hash)
        assert revision.source_id == fixture["new_source"]["source_id"]
        assert revision.detected_at == fixture["new_source"]["observed_at"]
        assert revision.notes


def test_content_fingerprint_hash_rule(manager: FreshnessManager) -> None:
    keep = _load(KNOWLEDGE_DIR / "k-keep-001.json")
    old, new = _pair(keep)
    assert content_hash(old) == content_hash(new)
    revision = manager.classify(old, new)
    assert revision.change_kind == "KEEP"
    assert revision.old_hash == revision.new_hash == content_hash(new)
    assert "content_fingerprint_equal=true" in revision.notes

    update = _load(KNOWLEDGE_DIR / "k-update-001.json")
    old_upd, new_upd = _pair(update)
    assert content_hash(old_upd) != content_hash(new_upd)
    assert manager.classify(old_upd, new_upd).change_kind == "UPDATE"

    # deterministic + documented v0 limitation (no content body field)
    assert content_hash(old) == content_hash(_source(keep["old_source"]))


def test_update_requires_newer_publication_and_authority(manager: FreshnessManager) -> None:
    fixture = _load(KNOWLEDGE_DIR / "k-update-001.json")
    old, new = _pair(fixture)
    revision = manager.classify(old, new)

    assert revision.change_kind == "UPDATE"
    assert "newer_publication_with_higher_authority_or_confidence" in revision.notes
    assert revision.claim_status == "VERIFIED"
    assert manager.curriculum_eligible(revision) is True
    assert manager.recheck_required(revision) is False

    # Newer publication but *lower* confidence at the same layer -> RECHECK.
    weaker = KnowledgeSource(
        source_id="doc:auc-001",
        uri=new.uri,
        publisher=new.publisher,
        published_at="2026-12-01T00:00:00+00:00",
        observed_at="2026-12-02T00:00:00+00:00",
        valid_until="2027-12-01T00:00:00+00:00",
        confidence=0.55,
        claim_status="VERIFIED",
    )
    assert manager.classify(old, weaker).change_kind == "RECHECK"
    assert "newer_publication_but_lower_or_equal_authority" in manager.classify(old, weaker).notes

    # Higher confidence alone, same publication time, different uri -> ambiguous RECHECK.
    same_time = KnowledgeSource(
        source_id="doc:auc-001b",
        uri="https://docs.synthetic.invalid/rec/auc-metric-alt",
        publisher=new.publisher,
        published_at=old.published_at,
        observed_at="2026-12-02T00:00:00+00:00",
        valid_until="2027-12-01T00:00:00+00:00",
        confidence=0.99,
        claim_status="VERIFIED",
    )
    assert manager.classify(old, same_time).change_kind == "RECHECK"
    assert "ambiguous_change_requires_human_review" in manager.classify(old, same_time).notes


def test_keep_means_no_curriculum_change(manager: FreshnessManager) -> None:
    for update_id in ("k-keep-001", "k-keep-002"):
        revision = _revision(_load(KNOWLEDGE_DIR / f"{update_id}.json"))
        assert revision.change_kind == "KEEP"
        assert manager.curriculum_eligible(revision) is False
        assert manager.recheck_required(revision) is False
        assert "no_curriculum_change_required=true" in revision.notes
        assert "content_fingerprint_equal=true" in revision.notes


def test_expired_source_requires_recheck(manager: FreshnessManager) -> None:
    fixture = _load(KNOWLEDGE_DIR / "k-recheck-expired-001.json")
    revision = manager.classify(*_pair(fixture))

    assert revision.change_kind == "RECHECK"
    assert revision.claim_status == "EXPIRED"
    assert "observed_after_old_valid_until" in revision.notes
    assert "observed_after_old_valid_until=true" in revision.notes
    assert manager.recheck_required(revision) is True
    assert manager.curriculum_eligible(revision) is False
    assert "recheck_required=true" in revision.notes


def test_conflicting_source_requires_recheck_and_never_updates(manager: FreshnessManager) -> None:
    fixture = _load(KNOWLEDGE_DIR / "k-recheck-conflict-001.json")
    old, new = _pair(fixture)
    revision = manager.classify(old, new)

    assert revision.change_kind == "RECHECK"
    assert revision.claim_status == "CONFLICT"
    assert "claim_status_conflict" in revision.notes
    assert manager.curriculum_eligible(revision) is False
    assert "recheck_required=true" in revision.notes

    grouped = manager.apply([revision])
    assert [item.revision_id for item in grouped["RECHECK"]] == [revision.revision_id]
    assert grouped["UPDATE"] == [] and grouped["KEEP"] == []


def test_newer_but_lower_authority_cannot_update(manager: FreshnessManager) -> None:
    fixture = _load(KNOWLEDGE_DIR / "k-recheck-community-001.json")
    old, new = _pair(fixture)
    revision = manager.classify(old, new)

    assert revision.change_kind == "RECHECK"
    assert "newer_publication_but_lower_or_equal_authority" in revision.notes
    assert infer_source_tier(old) == "official_document"
    assert infer_source_tier(new) == "community"
    assert SOURCE_TIERS["official_document"]["rank"] > SOURCE_TIERS["community"]["rank"]
    assert manager.curriculum_eligible(revision) is False


def test_older_or_mirrored_source_requires_recheck(manager: FreshnessManager) -> None:
    fixture = _load(KNOWLEDGE_DIR / "k-recheck-older-001.json")
    revision = manager.classify(*_pair(fixture))

    assert revision.change_kind == "RECHECK"
    assert "new_source_published_earlier_than_old" in revision.notes
    assert manager.curriculum_eligible(revision) is False


def test_future_dated_source_requires_recheck(manager: FreshnessManager) -> None:
    fixture = _load(KNOWLEDGE_DIR / "k-recheck-futuredate-001.json")
    revision = manager.classify(*_pair(fixture))

    assert revision.change_kind == "RECHECK"
    assert "published_after_observed=true" in revision.notes
    assert "new_published_at_after_new_observed_at" in revision.notes
    assert manager.curriculum_eligible(revision) is False


def test_published_at_and_observed_at_divergence_is_explicit(manager: FreshnessManager) -> None:
    fixture = _load(KNOWLEDGE_DIR / "k-update-001.json")
    old, new = _pair(fixture)
    revision = manager.classify(old, new)

    for token in (
        "published_at=",
        "observed_at=",
        "publish_delta_seconds=",
        "observation_lag_seconds=",
        "time_semantics=",
    ):
        assert token in revision.notes, token

    # publication was 2026-09-15T00:00Z, observed 2026-11-02T09:00Z -> 48d 9h lag
    assert "observation_lag_seconds=4179600" in revision.notes
    assert "publish_delta_seconds=" in revision.notes
    assert revision.detected_at == new.observed_at
    assert revision.detected_at != new.published_at
    assert "published_after_observed=false" in revision.notes


def test_apply_groups_revisions_and_blocks_silent_pollution(manager: FreshnessManager) -> None:
    revisions = [_revision(fixture) for fixture in _all_knowledge()]
    grouped = manager.apply(revisions)

    assert set(grouped) == {"KEEP", "UPDATE", "RECHECK"}
    assert sum(len(bucket) for bucket in grouped.values()) == len(revisions)
    for change_kind, bucket in grouped.items():
        assert all(revision.change_kind == change_kind for revision in bucket)

    curriculum_sources = {
        revision.source_id
        for revision in grouped["UPDATE"]
        if manager.curriculum_eligible(revision)
    }
    blocked_sources = {revision.source_id for revision in grouped["RECHECK"]}
    assert curriculum_sources == {"doc:auc-001", "paper:ns-001"}
    assert curriculum_sources.isdisjoint(blocked_sources)
    for revision in grouped["RECHECK"]:
        assert manager.curriculum_eligible(revision) is False
        assert manager.recheck_required(revision) is True
    # conflict/expired updates must never be silently materialized
    assert "community:post-009" not in curriculum_sources
    assert "doc:cal-001" not in curriculum_sources


def test_curriculum_eligible_rejects_newsier_jd_layer(manager: FreshnessManager) -> None:
    old = KnowledgeSource(
        source_id="jd:rec-v1",
        uri="https://jd.synthetic.invalid/rec/v1",
        publisher="SyntheticJdPortal",
        published_at="2026-06-01T00:00:00+00:00",
        observed_at="2026-06-02T00:00:00+00:00",
        valid_until="2026-12-31T00:00:00+00:00",
        confidence=0.70,
        claim_status="VERIFIED",
    )
    new = KnowledgeSource(
        source_id="jd:rec-v2",
        uri="https://jd.synthetic.invalid/rec/v2",
        publisher="SyntheticJdPortal",
        published_at="2026-10-01T00:00:00+00:00",
        observed_at="2026-10-02T00:00:00+00:00",
        valid_until="2027-03-31T00:00:00+00:00",
        confidence=0.90,
        claim_status="VERIFIED",
    )
    revision = manager.classify(old, new)

    assert revision.change_kind == "UPDATE"
    assert "jd_change_does_not_imply_topic_popularity=true" in revision.notes
    assert "jd" in revision.notes
    assert manager.curriculum_eligible(revision) is False
    assert SOURCE_TIERS["jd"]["may_update_curriculum"] is False
    assert SOURCE_TIERS["jd"]["signals_topic_popularity"] is False


def test_source_credibility_layering_matches_policy_doc(policy_doc: str) -> None:
    layers = source_layers()
    assert set(layers) == {
        "official_document",
        "paper",
        "engineering_blog",
        "jd",
        "community",
        "mirror",
        "unknown",
    }
    for tier, metadata in layers.items():
        assert tier in policy_doc, f"{tier} missing from policy doc"
        assert metadata["signals_topic_popularity"] is False
        assert isinstance(metadata["may_update_curriculum"], bool)
        assert metadata["description"]

    table_ranks = {
        tier: int(rank) for tier, rank in TIER_TABLE_RE.findall(policy_doc) if tier in layers
    }
    assert table_ranks, "policy doc must contain a layer/rank table"
    for tier, rank in table_ranks.items():
        assert layers[tier]["rank"] == rank, f"doc/code rank mismatch for {tier}"

    assert "JD 变化" in policy_doc and "题目热度" in policy_doc
    assert "content fingerprint" in policy_doc or "内容指纹" in policy_doc
    assert "published_at" in policy_doc and "observed_at" in policy_doc
    assert "KEEP" in policy_doc and "UPDATE" in policy_doc and "RECHECK" in policy_doc


def test_source_tier_inference_on_fixtures() -> None:
    expectations = {
        "k-keep-001": ("official_document", "official_document"),
        "k-update-002": ("paper", "paper"),
        "k-recheck-conflict-001": ("official_document", "community"),
        "k-recheck-older-001": ("official_document", "mirror"),
    }
    for update_id, (old_tier, new_tier) in expectations.items():
        fixture = _load(KNOWLEDGE_DIR / f"{update_id}.json")
        old, new = _pair(fixture)
        assert infer_source_tier(old) == old_tier
        assert infer_source_tier(new) == new_tier


def test_source_layers_returns_defensive_copy() -> None:
    layers = source_layers()
    layers["official_document"]["rank"] = 999
    layers.clear()
    fresh = source_layers()
    assert fresh["official_document"]["rank"] == 3
    assert SOURCE_TIERS["official_document"]["rank"] == 3


def test_manager_is_deterministic_offline_and_type_strict() -> None:
    fixture = _load(KNOWLEDGE_DIR / "k-update-002.json")
    old, new = _pair(fixture)

    first = FreshnessManager().classify(old, new)
    second = FreshnessManager().classify(old, new)
    assert first.to_dict() == second.to_dict()

    with pytest.raises(TypeError):
        FreshnessManager().classify({"not": "a source"}, new)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        FreshnessManager().classify(old, "not-a-source")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        FreshnessManager().apply("not-a-list")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        FreshnessManager().apply([{"not": "a revision"}])  # type: ignore[list-item]

    source = inspect.getsource(FreshnessManager)
    assert "runtime" not in source
    for network_token in ("httpx", "requests", "urllib", "socket"):
        assert network_token not in source
