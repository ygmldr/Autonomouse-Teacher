"""Deterministic, runtime-free four-dimension interview rubric.

Design constraints (M1 Offline Teacher, ``m1.offline.v0``):

* **Independent scorer.**  This module imports only the Python standard library.
  It does not import :mod:`m1_offline.runtime_port`, never calls a runtime /
  provider, and never reads the network.  A rubric instance has no runtime
  attribute, so a coach cannot smuggle model-generated text in as "evidence".
* **Deterministic.**  For byte-identical ``question``/``answer`` dicts the
  scores, feedback and failure modes are identical; no randomness, clocks or
  hash-order iteration are involved.
* **Four independent dimensions.**  ``factual_correctness`` uses the question's
  expected concept groups; ``explanation_clarity`` uses structural signals
  (length, sentences, connectors, paragraphs, vague wording);
  ``engineering_feasibility`` uses constraint/magnitude signals and infeasible
  design markers; ``evidence_sufficiency`` uses explicit evidence references,
  structured quantitative claims and project facts.  Each dimension is computed
  from a disjoint feature set on purpose, so tests can perturb one axis without
  moving the others.

Question contract consumed here (synthetic fixtures):
``question["rubric_points"][dimension]`` is a list of strings; every string is a
``token|synonym|...`` group and the dimension coverage is the fraction of groups
hit by at least one token.  Empty groups are treated as "no expectation" and do
not reduce the score.

Answer contract consumed here::

    {
      "text": str,                       # required
      "evidence_refs": [str, ...],       # sources actually cited
      "project_facts": [str, ...],       # learner-owned, verifiable project facts
      "quantitative_claims": [{"statement": str, "evidence_refs": [str, ...]}, ...],
      "misconceptions": [str, ...],      # explicit wrong statements in the answer
    }

The rubric never invents evidence: a quantitative claim without an
``evidence_refs`` entry is reported as ``unsourced_quantitative_claim`` and
lowers ``evidence_sufficiency`` only.
"""

from __future__ import annotations

import re
from typing import Any

SCHEMA_VERSION = "m1.offline.v0"
SCORER_ID = "InterviewRubric:m1.offline.v0"

DIMENSIONS = (
    "factual_correctness",
    "explanation_clarity",
    "engineering_feasibility",
    "evidence_sufficiency",
)

# Canonical failure-mode codes (stable order for deterministic reports).
FAILURE_MODES = (
    "incorrect_concept",
    "vague_explanation",
    "infeasible_engineering_design",
    "unsourced_quantitative_claim",
    "missing_project_facts",
    "insufficient_evidence",
    "misconceived_claim",
)

_CONNECTORS = (
    "首先",
    "其次",
    "然后",
    "最后",
    "因为",
    "所以",
    "因此",
    "例如",
    "比如",
    "具体来说",
    "第一",
    "第二",
    "第三",
    "结论",
    "总结",
    "换句话说",
    "对比",
    "区别于",
)

_VAGUE_WORDS = (
    "一些",
    "某些",
    "相关",
    "大概",
    "差不多",
    "可能",
    "应该",
    "估计",
    "很多",
    "各种",
    "之类的",
    "等等",
    "比较复杂",
    "看情况",
)

_INFEASIBLE_MARKERS = (
    "每秒重训",
    "全量实时训练",
    "不做缓存",
    "不需要降级",
    "不需要缓存",
    "暴力计算",
    "全量物品暴力",
    "所有特征全部实时",
    "资源不是问题",
    "无限机器",
    "无限资源",
    "没有资源上限",
)

# Structured "I improved X by N%" style statements in free text.  Deliberately
# narrow: design targets ("P99 控制在 10ms 内") are not matched.
_QUANT_CLAIM_PATTERNS = (
    re.compile(
        r"(?:提升|增长|提高|降低|减少|下降|节省|达到|做到)"
        r"[^0-9，。；：\n]{0,8}"
        r"\d+(?:\.\d+)?\s*(?:%|％|倍|个百分点|ms|毫秒|秒|万|亿|QPS|qps)"
    ),
    re.compile(r"\d+(?:\.\d+)?\s*(?:%|％|倍)\s*(?:的)?\s*(?:提升|增长|提高|降低|减少|下降)"),
)

_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _round(value: float) -> float:
    return round(_clamp(value), 4)


def _answer_text(answer: dict[str, Any]) -> str:
    if not isinstance(answer, dict):
        raise TypeError(f"answer must be dict, got {type(answer).__name__}")
    text = answer.get("text", "")
    if not isinstance(text, str):
        raise TypeError("answer['text'] must be str")
    return text


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def _groups(question: dict[str, Any], dimension: str) -> list[tuple[str, ...]]:
    if not isinstance(question, dict):
        raise TypeError(f"question must be dict, got {type(question).__name__}")
    points = question.get("rubric_points")
    if not isinstance(points, dict):
        return []
    raw = points.get(dimension)
    if not isinstance(raw, list):
        return []
    groups: list[tuple[str, ...]] = []
    for item in raw:
        if not isinstance(item, str):
            continue
        tokens = tuple(token.strip().lower() for token in item.split("|") if token.strip())
        if tokens:
            groups.append(tokens)
    return groups


def _coverage(groups: list[tuple[str, ...]], text_lower: str) -> tuple[float, int]:
    """Return (fraction of groups hit, number of groups)."""

    if not groups:
        return 0.0, 0
    hits = sum(1 for group in groups if any(token in text_lower for token in group))
    return hits / len(groups), len(groups)


def _claims(answer: dict[str, Any]) -> list[dict[str, Any]]:
    raw = answer.get("quantitative_claims")
    claims: list[dict[str, Any]] = []
    if not isinstance(raw, list):
        return claims
    for item in raw:
        if not isinstance(item, dict):
            continue
        statement = item.get("statement", "")
        if not isinstance(statement, str) or not statement.strip():
            continue
        claims.append(
            {
                "statement": statement,
                "evidence_refs": _string_list(item.get("evidence_refs")),
            }
        )
    return claims


def _free_text_quant_claims(text: str) -> list[str]:
    hits: list[str] = []
    seen: set[str] = set()
    for pattern in _QUANT_CLAIM_PATTERNS:
        for match in pattern.finditer(text):
            snippet = match.group(0)
            if snippet not in seen:
                seen.add(snippet)
                hits.append(snippet)
    return hits


def _factual_score(question: dict[str, Any], answer: dict[str, Any]) -> tuple[float, dict[str, int]]:
    text_lower = _answer_text(answer).lower()
    groups = _groups(question, "factual_correctness")
    coverage, total = _coverage(groups, text_lower)
    misconceptions = _string_list(answer.get("misconceptions"))
    penalty = 0.25 * min(len(misconceptions), 2)
    score = _round(coverage - penalty)
    return score, {"hit_groups": round(coverage * total) if total else 0, "total_groups": total}


def _clarity_score(question: dict[str, Any], answer: dict[str, Any]) -> float:
    text = _answer_text(answer)
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

    sentences = [part for part in re.split(r"[。！？!?；;\n]+", text) if part.strip()]
    sentence_score = min(1.0, len(sentences) / 4.0)

    connector_hits = sum(1 for token in _CONNECTORS if token in text)
    connector_score = min(1.0, connector_hits / 3.0)

    paragraph_score = 1.0 if "\n\n" in text else 0.0

    vague_hits = sum(text.count(word) for word in _VAGUE_WORDS)
    vague_penalty = min(0.4, 0.08 * vague_hits)

    groups = _groups(question, "explanation_clarity")
    coverage, _total = _coverage(groups, text.lower())

    score = (
        0.25 * length_score
        + 0.20 * sentence_score
        + 0.30 * connector_score
        + 0.10 * paragraph_score
        + 0.15 * coverage
    )
    return _round(score - vague_penalty)


def _feasibility_score(question: dict[str, Any], answer: dict[str, Any]) -> float:
    text = _answer_text(answer)
    text_lower = text.lower()

    groups = _groups(question, "engineering_feasibility")
    coverage, _total = _coverage(groups, text_lower)

    magnitude_hits = len(
        re.findall(
            r"\d+(?:\.\d+)?\s*(?:ms|毫秒|秒|s|QPS|qps|万|亿|GB|TB|核|台|倍|%|％)",
            text,
        )
    )
    magnitude_score = min(1.0, magnitude_hits / 3.0)

    infeasible_hits = sum(1 for marker in _INFEASIBLE_MARKERS if marker in text)
    infeasible_penalty = min(0.8, 0.3 * infeasible_hits)

    score = 0.6 * coverage + 0.4 * magnitude_score - infeasible_penalty
    return _round(score)


def _evidence_score(
    question: dict[str, Any], answer: dict[str, Any]
) -> tuple[float, dict[str, int]]:
    text = _answer_text(answer)
    refs = _string_list(answer.get("evidence_refs"))
    project_facts = _string_list(answer.get("project_facts"))
    claims = _claims(answer)
    unsourced_claims = [claim for claim in claims if not claim["evidence_refs"]]

    free_claims = _free_text_quant_claims(text)
    covered_free = 0
    for snippet in free_claims:
        number_match = _NUMBER_RE.search(snippet)
        if number_match is None:
            continue
        number = number_match.group(0)
        if any(number in claim["statement"] and claim["evidence_refs"] for claim in claims):
            covered_free += 1
    free_unsourced = max(0, len(free_claims) - covered_free)
    unsourced_total = len(unsourced_claims) + free_unsourced

    groups = _groups(question, "evidence_sufficiency")
    coverage, total = _coverage(groups, text.lower())

    sourced_ratio = 0.0
    if claims:
        sourced_ratio = (len(claims) - len(unsourced_claims)) / len(claims)

    score = (
        0.10
        + 0.25 * coverage
        + min(0.25, 0.10 * len(refs))
        + (0.15 if project_facts else 0.0)
        + 0.15 * sourced_ratio
    )
    if unsourced_total == 0 and (refs or project_facts or claims):
        score += 0.10  # reward: no unsupported quantitative claim at all
    score -= 0.20 * min(unsourced_total, 2)

    requires_facts = bool(question.get("requires_project_facts"))
    if requires_facts and not project_facts:
        score -= 0.25

    detail = {
        "evidence_refs": len(refs),
        "sourced_claims": len(claims) - len(unsourced_claims),
        "unsourced_claims": unsourced_total,
        "project_facts": len(project_facts),
        "groups_hit": round(coverage * total) if total else 0,
        "groups_total": total,
    }
    return _round(score), detail


class InterviewRubric:
    """Deterministic independent scorer for synthetic interview answers.

    The class intentionally takes no runtime / client argument: scoring must not
    depend on any model call.  ``SCORER_ID`` is embedded in
    :class:`~m1_offline.types.AssessmentResult.scorer_id` by the coach.
    """

    DIMENSIONS = DIMENSIONS
    SCORER_ID = SCORER_ID
    FAILURE_MODES = FAILURE_MODES
    SCHEMA_VERSION = SCHEMA_VERSION

    def score(self, question: dict[str, Any], answer: dict[str, Any]) -> dict[str, float]:
        """Return the four dimension scores, each within ``[0, 1]``."""

        factual, _fact_detail = _factual_score(question, answer)
        clarity = _clarity_score(question, answer)
        feasibility = _feasibility_score(question, answer)
        evidence, _evid_detail = _evidence_score(question, answer)
        return {
            "factual_correctness": factual,
            "explanation_clarity": clarity,
            "engineering_feasibility": feasibility,
            "evidence_sufficiency": evidence,
        }

    def failure_modes(self, question: dict[str, Any], answer: dict[str, Any]) -> list[str]:
        """Return canonical failure-mode codes (stable order, no duplicates)."""

        scores = self.score(question, answer)
        modes: list[str] = []
        if scores["factual_correctness"] < 0.5:
            modes.append("incorrect_concept")
        if scores["explanation_clarity"] < 0.5:
            modes.append("vague_explanation")
        if any(marker in _answer_text(answer) for marker in _INFEASIBLE_MARKERS):
            modes.append("infeasible_engineering_design")
        _evidence, detail = _evidence_score(question, answer)
        if detail["unsourced_claims"] > 0:
            modes.append("unsourced_quantitative_claim")
        if question.get("requires_project_facts") and detail["project_facts"] == 0:
            modes.append("missing_project_facts")
        if scores["evidence_sufficiency"] < 0.5:
            modes.append("insufficient_evidence")
        if _string_list(answer.get("misconceptions")):
            modes.append("misconceived_claim")
        # keep canonical order and drop duplicates
        ordered = [mode for mode in FAILURE_MODES if mode in modes]
        return ordered

    def feedback(self, question: dict[str, Any], answer: dict[str, Any]) -> list[str]:
        """Return deterministic, human-readable feedback lines."""

        scores = self.score(question, answer)
        _factual, fact_detail = _factual_score(question, answer)
        _evidence, evid_detail = _evidence_score(question, answer)
        lines: list[str] = [
            (
                "factual_correctness={:.2f}（命中要点 {}/{}）".format(
                    scores["factual_correctness"],
                    fact_detail["hit_groups"],
                    fact_detail["total_groups"],
                )
            ),
            "explanation_clarity={:.2f}".format(scores["explanation_clarity"]),
            "engineering_feasibility={:.2f}".format(scores["engineering_feasibility"]),
            "evidence_sufficiency={:.2f}".format(scores["evidence_sufficiency"]),
        ]

        if scores["factual_correctness"] < 0.6:
            missing = [
                group[0]
                for group in _groups(question, "factual_correctness")
                if not any(token in _answer_text(answer).lower() for token in group)
            ]
            if missing:
                lines.append("事实正确性不足：缺少关键要点 " + "、".join(missing[:4]))
        if scores["explanation_clarity"] < 0.6:
            lines.append("表达清晰度不足：缺少结构性连接词/分段，或存在模糊措辞，建议按‘定义-原因-方法-结论’组织。")
        if scores["engineering_feasibility"] < 0.6:
            if any(marker in _answer_text(answer) for marker in _INFEASIBLE_MARKERS):
                lines.append("工程可行性不足：方案含不现实约束（如每秒全量重训、全量暴力计算、无缓存无降级）。")
            else:
                lines.append("工程可行性不足：缺少延迟/QPS/成本等约束与量级说明。")
        if scores["evidence_sufficiency"] < 0.6:
            detail = (
                "缺少可核验来源或实验数据"
                if evid_detail["evidence_refs"] == 0
                else "证据链不完整"
            )
            lines.append("证据充分性不足：{0}".format(detail))
            if evid_detail["unsourced_claims"] > 0:
                lines.append(
                    "检测到 {0} 条无来源的量化说法（如提升百分比/规模），必须补充可核验出处，否则不得作为事实。".format(
                        evid_detail["unsourced_claims"]
                    )
                )
        if question.get("requires_project_facts") and evid_detail["project_facts"] == 0:
            lines.append("项目事实边界：题目要求真实项目经历，但回答未提供可核验的项目事实；应询问学习者而非替其编造。")
        if _string_list(answer.get("misconceptions")):
            lines.append("回答包含明确错误陈述：" + "；".join(_string_list(answer.get("misconceptions"))[:3]))

        if len(lines) == 4:  # four raw scores only -> no weakness found
            lines.append("四个维度均达到阈值，可作为参考样本；仍需人工抽查事实细节。")
        return lines


__all__ = [
    "SCHEMA_VERSION",
    "SCORER_ID",
    "DIMENSIONS",
    "FAILURE_MODES",
    "InterviewRubric",
]
