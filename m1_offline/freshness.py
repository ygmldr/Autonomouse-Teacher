"""Knowledge freshness / source-credibility manager (``m1.offline.v0``).

The manager classifies a re-observed knowledge item against its previous
version and decides whether the curriculum may consume it:

* ``KEEP``    -- content fingerprint unchanged; nothing to do.
* ``UPDATE``  -- newer publication **and** not-worse source authority/confidence;
                 the only bucket that can feed the main curriculum, and even
                 then only when the revision's ``claim_status`` is ``VERIFIED``.
* ``RECHECK`` -- expired, conflicting, older/mirrored, future-dated, or
                 ambiguous changes; **must be human-reviewed before any
                 curriculum write** and is never silently applied.

Time semantics are deliberately explicit: ``published_at`` is the source's own
publication time, ``observed_at`` is when we fetched/observed it.  Their
divergence (observation lag, future-dated sources, newly published versions) is
recorded in :attr:`KnowledgeRevision.notes` so replay/audit can distinguish
"the source changed" from "we noticed it today".

Source credibility is layered (see :data:`SOURCE_TIERS` and
``docs/m1/FRESHNESS_AND_SOURCE_POLICY.md``).  A JD revision is a *hiring
requirement* change only -- it is explicitly not a topic-popularity signal and
never a knowledge update for the curriculum.  Likewise a community post can
raise a RECHECK flag but cannot silently override an official document.

Content fingerprint note: :class:`~m1_offline.types.KnowledgeSource` has no
content-body field in ``m1.offline.v0``, so the content hash is approximated by
a canonical sha256 over ``(uri, publisher, published_at, claim_status)``.  Any
upstream body digest is UNVERIFIED in this offline phase; real integrations must
pass a body digest through the same field.  This limitation is documented and
tested.

The manager is deterministic, offline and never calls a runtime/provider.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from datetime import datetime, timezone

from m1_offline.types import CHANGE_KIND_VALUES, KnowledgeRevision, KnowledgeSource

SCHEMA_VERSION = "m1.offline.v0"

#: Layer -> metadata.  ``rank`` is used for authority comparison; a higher rank
#: may UPDATE a lower one only together with a newer ``published_at``.
SOURCE_TIERS: dict[str, dict] = {
    "official_document": {
        "rank": 3,
        "description": "官方文档/规范/内部权威 wiki；可进入主课程（仅当 UPDATE 且 claim_status=VERIFIED）",
        "may_update_curriculum": True,
        "signals_topic_popularity": False,
    },
    "paper": {
        "rank": 2,
        "description": "论文/预印本；可作更新来源，必须标注未复现，且需复核",
        "may_update_curriculum": True,
        "signals_topic_popularity": False,
    },
    "engineering_blog": {
        "rank": 2,
        "description": "工程团队博客；可作更新来源，需标注实践经验未经独立验证",
        "may_update_curriculum": True,
        "signals_topic_popularity": False,
    },
    "jd": {
        "rank": 2,
        "description": "招聘 JD；只表示岗位要求变化，不代表题目热度或知识更新",
        "may_update_curriculum": False,
        "signals_topic_popularity": False,
    },
    "community": {
        "rank": 1,
        "description": "社区讨论/论坛；只能作为线索触发 RECHECK，不能单独驱动课程更新",
        "may_update_curriculum": False,
        "signals_topic_popularity": False,
    },
    "mirror": {
        "rank": 0,
        "description": "镜像/转载站点；旧内容风险高，默认 RECHECK",
        "may_update_curriculum": False,
        "signals_topic_popularity": False,
    },
    "unknown": {
        "rank": 0,
        "description": "未知来源；默认 RECHECK，禁止进入主课程",
        "may_update_curriculum": False,
        "signals_topic_popularity": False,
    },
}

_TIER_KEYWORDS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("arxiv", "paper", "preprint"), "paper"),
    (("community", "forum", "bbs", "reddit", "stackoverflow"), "community"),
    (("jd", "job_description"), "jd"),
    (("mirror", "mirror_site", "cache"), "mirror"),
    (("official", "docs.", "documentation", "spec", "wiki"), "official_document"),
    (("blog", "engineering_blog"), "engineering_blog"),
)


def _parse_ts(value: str | None) -> datetime | None:
    """Parse an ISO-8601 timestamp string (``Z`` or offset) into UTC datetime."""

    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _delta_seconds(later: datetime | None, earlier: datetime | None) -> int | None:
    if later is None or earlier is None:
        return None
    return int((later - earlier).total_seconds())


def _fingerprint(source: KnowledgeSource) -> dict[str, str]:
    """Canonical content descriptor used as the v0 content fingerprint input."""

    return {
        "uri": source.uri,
        "publisher": source.publisher,
        "published_at": source.published_at,
        "claim_status": source.claim_status,
    }


def content_hash(source: KnowledgeSource) -> str:
    """Return the 64-hex content fingerprint for a knowledge source.

    v0 limitation: the source record carries no body/content digest, so this is
    a canonical sha256 over ``(uri, publisher, published_at, claim_status)``.
    """

    if not isinstance(source, KnowledgeSource):
        raise TypeError(f"source must be KnowledgeSource, got {type(source).__name__}")
    canonical = json.dumps(_fingerprint(source), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def infer_source_tier(source: KnowledgeSource) -> str:
    """Infer the credibility layer from synthetic publisher/uri/source_id text."""

    if not isinstance(source, KnowledgeSource):
        raise TypeError(f"source must be KnowledgeSource, got {type(source).__name__}")
    haystack = " ".join((source.publisher, source.uri, source.source_id)).lower()
    for keywords, tier in _TIER_KEYWORDS:
        if any(keyword in haystack for keyword in keywords):
            return tier
    return "unknown"


def source_layers() -> dict[str, dict]:
    """Return a defensive copy of the layered source policy (tests compare docs)."""

    return copy.deepcopy(SOURCE_TIERS)


def _revision_new_tier(notes: str) -> str | None:
    """Extract the new-source layer recorded in ``KnowledgeRevision.notes``."""

    if not isinstance(notes, str):
        return None
    match = re.search(r"source_tier=[a-z_]+\(rank=\d+\)->([a-z_]+)\(rank=\d+\)", notes)
    return match.group(1) if match else None


class FreshnessManager:
    """Classify knowledge re-observations and gate curriculum writes."""

    SCHEMA_VERSION = SCHEMA_VERSION
    SOURCE_TIERS = SOURCE_TIERS

    # -- classification ----------------------------------------------------
    def classify(self, old: KnowledgeSource, new: KnowledgeSource) -> KnowledgeRevision:
        """Classify ``new`` against ``old`` (deterministic, no I/O)."""

        if not isinstance(old, KnowledgeSource):
            raise TypeError(f"old must be KnowledgeSource, got {type(old).__name__}")
        if not isinstance(new, KnowledgeSource):
            raise TypeError(f"new must be KnowledgeSource, got {type(new).__name__}")

        old_tier = infer_source_tier(old)
        new_tier = infer_source_tier(new)
        old_rank = SOURCE_TIERS[old_tier]["rank"]
        new_rank = SOURCE_TIERS[new_tier]["rank"]
        old_hash = content_hash(old)
        new_hash = content_hash(new)

        old_published = _parse_ts(old.published_at)
        new_published = _parse_ts(new.published_at)
        new_observed = _parse_ts(new.observed_at)
        old_valid_until = _parse_ts(old.valid_until)
        new_valid_until = _parse_ts(new.valid_until)

        publish_delta = _delta_seconds(new_published, old_published)
        observation_lag = _delta_seconds(new_observed, new_published)
        observed_after_old_valid_until = bool(
            old_valid_until is not None
            and new_observed is not None
            and new_observed > old_valid_until
        )
        observed_after_new_valid_until = bool(
            new_valid_until is not None
            and new_observed is not None
            and new_observed > new_valid_until
        )
        published_after_observed = bool(
            new_published is not None
            and new_observed is not None
            and new_published > new_observed
        )
        new_older_than_old = bool(
            new_published is not None
            and old_published is not None
            and new_published < old_published
        )
        fingerprint_equal = old_hash == new_hash

        kind = ""
        reasons: list[str] = []

        # Fail-closed precedence: anomalies/conflicts/expiry before any UPDATE.
        if published_after_observed:
            kind = "RECHECK"
            reasons.append("new_published_at_after_new_observed_at(future_dated_or_clock_skew)")
        elif new.claim_status == "CONFLICT" or old.claim_status == "CONFLICT":
            kind = "RECHECK"
            reasons.append("claim_status_conflict")
        elif new.claim_status == "EXPIRED" or old.claim_status == "EXPIRED":
            kind = "RECHECK"
            reasons.append("claim_status_expired")
        elif observed_after_old_valid_until:
            kind = "RECHECK"
            reasons.append("observed_after_old_valid_until")
        elif observed_after_new_valid_until:
            kind = "RECHECK"
            reasons.append("observed_after_new_valid_until")
        elif new_older_than_old:
            kind = "RECHECK"
            reasons.append("new_source_published_earlier_than_old")
        elif fingerprint_equal:
            kind = "KEEP"
            reasons.append("content_fingerprint_unchanged")
        else:
            published_newer = bool(
                new_published is not None
                and old_published is not None
                and new_published > old_published
            )
            authority_not_worse = new_rank >= old_rank
            authority_improved = (new_rank > old_rank) or (new.confidence > old.confidence + 1e-9)
            if published_newer and authority_not_worse and authority_improved:
                kind = "UPDATE"
                reasons.append("newer_publication_with_higher_authority_or_confidence")
            elif published_newer:
                kind = "RECHECK"
                reasons.append("newer_publication_but_lower_or_equal_authority")
            else:
                kind = "RECHECK"
                reasons.append("ambiguous_change_requires_human_review")

        assert kind in CHANGE_KIND_VALUES, kind  # internal invariant

        if kind == "UPDATE":
            revision_claim = "VERIFIED" if new.claim_status == "VERIFIED" else "REPORTED"
        elif kind == "KEEP":
            revision_claim = old.claim_status
        elif new.claim_status == "CONFLICT" or old.claim_status == "CONFLICT":
            revision_claim = "CONFLICT"
        elif (
            new.claim_status == "EXPIRED"
            or old.claim_status == "EXPIRED"
            or observed_after_old_valid_until
            or observed_after_new_valid_until
        ):
            revision_claim = "EXPIRED"
        else:
            revision_claim = "REPORTED"

        if kind == "UPDATE":
            curriculum_eligible = revision_claim == "VERIFIED"
        else:
            curriculum_eligible = False

        jd_involved = "jd" in (old_tier, new_tier)
        notes_parts = [
            f"decision={kind}",
            "reasons=" + ",".join(reasons),
            f"source_id={old.source_id}->{new.source_id}",
            f"source_tier={old_tier}(rank={old_rank})->{new_tier}(rank={new_rank})",
            f"confidence={old.confidence:.2f}->{new.confidence:.2f}",
            f"published_at={old.published_at}->{new.published_at}",
            f"observed_at={old.observed_at}->{new.observed_at}",
            f"publish_delta_seconds={publish_delta}",
            f"observation_lag_seconds={observation_lag}",
            f"old_valid_until={old.valid_until}",
            f"observed_after_old_valid_until={str(observed_after_old_valid_until).lower()}",
            f"published_after_observed={str(published_after_observed).lower()}",
            f"content_fingerprint_equal={str(fingerprint_equal).lower()}",
            "time_semantics=published_at 为来源发布时间，observed_at 为抓取/观测时间，二者显式区分",
        ]
        if jd_involved:
            notes_parts.append("jd_change_does_not_imply_topic_popularity=true")
        notes_parts.append(f"curriculum_eligible={str(curriculum_eligible).lower()}")
        if kind == "RECHECK":
            notes_parts.append("recheck_required=true；RECHECK/冲突项必须人工复核后才能更新主课程，禁止静默写入")
        if kind == "KEEP":
            notes_parts.append("no_curriculum_change_required=true")
        notes = "; ".join(notes_parts)

        revision_id = "rev-" + hashlib.sha256(
            "\x1f".join(
                (
                    old.source_id,
                    new.source_id,
                    kind,
                    old_hash,
                    new_hash,
                    new.observed_at,
                )
            ).encode("utf-8")
        ).hexdigest()[:16]

        return KnowledgeRevision(
            revision_id=revision_id,
            source_id=new.source_id,
            old_hash=old_hash,
            new_hash=new_hash,
            change_kind=kind,
            detected_at=new.observed_at,
            claim_status=revision_claim,
            notes=notes,
        )

    # -- application gate --------------------------------------------------
    def apply(self, revisions: list[KnowledgeRevision]) -> dict[str, list[KnowledgeRevision]]:
        """Group revisions by change kind; nothing is written to any curriculum.

        The caller may only materialize the ``UPDATE`` bucket and only through
        :meth:`curriculum_eligible`.  ``RECHECK`` stays a review queue and must
        never be silently merged into the main curriculum.
        """

        if not isinstance(revisions, list):
            raise TypeError(f"revisions must be list, got {type(revisions).__name__}")
        grouped: dict[str, list[KnowledgeRevision]] = {"KEEP": [], "UPDATE": [], "RECHECK": []}
        for index, revision in enumerate(revisions):
            if not isinstance(revision, KnowledgeRevision):
                raise TypeError(
                    f"revisions[{index}] must be KnowledgeRevision, got {type(revision).__name__}"
                )
            grouped[revision.change_kind].append(revision)
        return grouped

    def curriculum_eligible(self, revision: KnowledgeRevision) -> bool:
        """True only for a writable revision: ``UPDATE`` + ``VERIFIED`` + credible layer.

        ``SOURCE_TIERS[tier]["may_update_curriculum"]`` must also be true, so a
        JD/community/mirror/unknown-layer revision can never feed the curriculum
        even if it looks like an UPDATE.  Everything else stays in RECHECK.
        """

        if not isinstance(revision, KnowledgeRevision):
            raise TypeError(f"revision must be KnowledgeRevision, got {type(revision).__name__}")
        if revision.change_kind != "UPDATE" or revision.claim_status != "VERIFIED":
            return False
        new_tier = _revision_new_tier(revision.notes)
        if new_tier is not None and not SOURCE_TIERS.get(new_tier, {}).get(
            "may_update_curriculum", False
        ):
            return False
        return True

    def recheck_required(self, revision: KnowledgeRevision) -> bool:
        """True for revisions that must stay in the human-review queue."""

        if not isinstance(revision, KnowledgeRevision):
            raise TypeError(f"revision must be KnowledgeRevision, got {type(revision).__name__}")
        return revision.change_kind == "RECHECK"


__all__ = [
    "SCHEMA_VERSION",
    "SOURCE_TIERS",
    "FreshnessManager",
    "content_hash",
    "infer_source_tier",
    "source_layers",
]
