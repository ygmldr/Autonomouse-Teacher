"""Tests for the scorer-side InterviewRubricJudge (B-PR4 vertical layer).

Covers: four independent deterministic rubric dimensions, conservative
open-answer semantics (never CORRECT), NEEDS_REVIEW for missing project facts,
EVAL_ERROR isolation from learner evidence, assessment-port sidecar dimensions,
hidden-material non-leakage and offline/no-learner-writer guarantees.
"""

from __future__ import annotations

import ast
import inspect
import json
import re
import shutil
from pathlib import Path

import pytest

from m1_teacher.assessment import interview_judge as judge_module
from m1_teacher.assessment.interview_judge import (
    DIMENSIONS,
    SCORER_ID,
    InterviewAssessmentDetail,
    InterviewRubricJudge,
)
from m1_teacher.contracts.errors import ValidationError
from m1_teacher.contracts.types import AssessmentItem, AssessmentResult
from m1_teacher.domains.interview import InterviewDomainAdapter

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_ROOT = REPO_ROOT / "fixtures" / "m1_teacher"
INTERVIEW = FIXTURES_ROOT / "vertical" / "interview"
SCORING = INTERVIEW / "rubrics" / "scoring"
STAGES = ("concept", "hypothesis", "complexity", "experiment_design", "online_triage")


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def adapter() -> InterviewDomainAdapter:
    instance = InterviewDomainAdapter(FIXTURES_ROOT)
    instance.validate()
    return instance


@pytest.fixture(scope="module")
def judge() -> InterviewRubricJudge:
    return InterviewRubricJudge(FIXTURES_ROOT)


@pytest.fixture(scope="module")
def items(adapter: InterviewDomainAdapter) -> dict[str, AssessmentItem]:
    return {item.item_id: item for item in adapter.assessment_items()}


@pytest.fixture(scope="module")
def answers() -> dict[str, dict]:
    payload = _load(SCORING / "reference_answers.json")
    return {answer["answer_id"]: answer for answer in payload["answers"]}


def _answer(answers: dict[str, dict], answer_id: str) -> dict:
    return answers[answer_id]["response"]


def _spec_for(question_id: str) -> dict:
    return _load(SCORING / f"{question_id}.json")


# ---------------------------------------------------------------------------
# Basic result shape / sidecar
# ---------------------------------------------------------------------------


def test_judge_returns_frozen_result_and_hidden_sidecar(
    judge: InterviewRubricJudge, items: dict, answers: dict
) -> None:
    item = items["interview.item.q-ml-001"]
    response = _answer(answers, "a-correct-001")
    result = judge.assess(item, "learner-1", response)
    detail = judge.detail(result.result_id)

    assert isinstance(result, AssessmentResult)
    assert isinstance(detail, InterviewAssessmentDetail)
    assert result.item_id == item.item_id
    assert result.learner_id == "learner-1"
    assert result.scorer_id == SCORER_ID
    assert result.max_score == 1.0
    assert 0.0 <= result.score <= 1.0
    assert result.evidence_refs[0] == f"item:{item.item_id}"
    assert result.evidence_refs[1].startswith("spec-sha256:")
    assert len(detail.spec_digest) == 64
    assert set(detail.dimensions) == set(DIMENSIONS)
    assert all(0.0 <= value <= 1.0 for value in detail.dimensions.values())
    assert detail.open_answer is True
    # Dimensions live in the sidecar, not in the frozen teacher-visible result.
    assert not hasattr(result, "dimensions")
    assert "dimensions" not in result.to_dict()


def test_spec_digest_available_for_every_item(
    judge: InterviewRubricJudge, items: dict
) -> None:
    for item in items.values():
        digest = judge.spec_digest(item)
        assert len(digest) == 64
        int(digest, 16)


# ---------------------------------------------------------------------------
# Open-answer conservatism
# ---------------------------------------------------------------------------


def test_open_answer_never_correct_even_for_perfect_response(
    judge: InterviewRubricJudge, items: dict, answers: dict
) -> None:
    item = items["interview.item.q-ml-001"]
    spec = _spec_for("q-ml-001")
    tokens = [group[0] for groups in spec["expectations"].values() for group in groups]
    perfect_text = (
        "结论先行：这道题考察泛化诊断。\n\n"
        "首先，" + "；".join(tokens) + " 都是必须讲清的概念，我会先定义再解释原因。\n\n"
        "其次，我会给出可证伪假设、量级估算与实验设计，例如训练集与验证集的 gap 变化、"
        "学习曲线形态、正则化与早停的取舍、模型容量与参数量的权衡。\n\n"
        "最后，我会引用来源、实验对照、指标口径与监控日志来支撑结论。"
    )
    perfect_response = {
        "text": perfect_text,
        "evidence_refs": ["synthetic:source-1", "synthetic:validation-curve"],
        "project_facts": ["合成项目：用时间切分验证集，离线/线上 gap 收敛（合成数据）"],
        "quantitative_claims": [
            {"statement": "验证集指标从 0.81 提升到 0.88", "evidence_refs": ["synthetic:validation-curve"]}
        ],
        "misconceptions": [],
    }
    result = judge.assess(item, "learner-1", perfect_response)
    detail = judge.detail(result.result_id)
    assert result.status == "PARTIAL", "open answers can be at most PARTIAL"
    assert result.failure_reason.startswith("PARTIAL:")
    assert result.score >= 0.6
    assert detail.dimensions["factual_correctness"] >= 0.5

    strong = judge.assess(items["interview.item.q-sys-002"], "learner-1", _answer(answers, "a-strong-008"))
    assert strong.status == "PARTIAL"


def test_needs_review_when_project_facts_missing(
    judge: InterviewRubricJudge, items: dict, answers: dict
) -> None:
    item = items["interview.item.q-eng-001"]
    result = judge.assess(item, "learner-1", _answer(answers, "a-missingfacts-004"))
    detail = judge.detail(result.result_id)
    assert result.status == "NEEDS_REVIEW"
    assert result.failure_reason == "NEEDS_REVIEW:PROJECT_FACTS_REQUIRED"
    assert "missing_project_facts" in detail.failure_modes
    assert detail.dimensions["evidence_sufficiency"] <= 0.2


def test_too_short_response_needs_review(
    judge: InterviewRubricJudge, items: dict
) -> None:
    result = judge.assess(items["interview.item.q-ml-001"], "learner-1", "不知道")
    assert result.status == "NEEDS_REVIEW"
    assert result.failure_reason == "NEEDS_REVIEW:INTERVIEW_RESPONSE_TOO_SHORT"
    assert judge.detail(result.result_id) is not None


def test_incorrect_for_low_factual_coverage(
    judge: InterviewRubricJudge, items: dict, answers: dict
) -> None:
    result = judge.assess(items["interview.item.q-rec-001"], "learner-1", _answer(answers, "a-vague-002"))
    detail = judge.detail(result.result_id)
    assert result.status == "INCORRECT"
    assert detail.dimensions["factual_correctness"] < 0.5
    assert "incorrect_concept" in detail.failure_modes


# ---------------------------------------------------------------------------
# Four independent dimensions
# ---------------------------------------------------------------------------


def test_four_dimensions_are_computed_independently(
    judge: InterviewRubricJudge, items: dict, answers: dict
) -> None:
    item = items["interview.item.q-ml-001"]
    base = _answer(answers, "a-correct-001")

    def scored(response: dict) -> dict[str, float]:
        result = judge.assess(item, "learner-1", response)
        detail = judge.detail(result.result_id)
        assert detail is not None
        return dict(detail.dimensions)

    base_scores = scored(base)

    # 1) Clarity-only perturbation: structure/connectors, no factual tokens added.
    clarity_variant = json.loads(json.dumps(base))
    clarity_variant["text"] += "\n\n首先，我会说明背景；其次，我会说明原因；最后，我会给出结论。"
    clarity_scores = scored(clarity_variant)
    assert clarity_scores["explanation_clarity"] > base_scores["explanation_clarity"]
    assert clarity_scores["factual_correctness"] == base_scores["factual_correctness"]
    assert clarity_scores["engineering_feasibility"] == base_scores["engineering_feasibility"]
    assert clarity_scores["evidence_sufficiency"] == base_scores["evidence_sufficiency"]

    # 2) Evidence-only perturbation: attach verifiable references/project facts.
    evidence_variant = json.loads(json.dumps(base))
    evidence_variant["evidence_refs"] = [
        "synthetic:audit-1",
        "synthetic:ab-report-2",
        "synthetic:validation-curve",
        "synthetic:ablation-4",
    ]
    evidence_variant["project_facts"] = ["合成项目：验证集指标收敛（合成数据）"]
    evidence_scores = scored(evidence_variant)
    assert evidence_scores["evidence_sufficiency"] > base_scores["evidence_sufficiency"]
    assert evidence_scores["factual_correctness"] == base_scores["factual_correctness"]
    assert evidence_scores["explanation_clarity"] == base_scores["explanation_clarity"]
    assert evidence_scores["engineering_feasibility"] == base_scores["engineering_feasibility"]

    # 3) Feasibility-only perturbation: constraints and magnitude numbers.
    feasibility_variant = json.loads(json.dumps(base))
    feasibility_variant["text"] += "\n\n工程约束：训练成本约 3 张 GPU，数据量约 100 万样本，显存 80GB。"
    feasibility_scores = scored(feasibility_variant)
    assert feasibility_scores["engineering_feasibility"] > base_scores["engineering_feasibility"]
    assert feasibility_scores["factual_correctness"] == base_scores["factual_correctness"]
    assert feasibility_scores["evidence_sufficiency"] == base_scores["evidence_sufficiency"]

    # 4) Factual-only perturbation: remove one expected concept group.
    factual_variant = json.loads(json.dumps(base))
    factual_variant["text"] = (
        factual_variant["text"]
        .replace("正则化", "处理C")
        .replace("L1", "处理A")
        .replace("L2", "处理B")
    )
    factual_scores = scored(factual_variant)
    assert factual_scores["factual_correctness"] < base_scores["factual_correctness"]
    assert factual_scores["explanation_clarity"] == base_scores["explanation_clarity"]
    assert factual_scores["evidence_sufficiency"] == base_scores["evidence_sufficiency"]

    # 5) Misconception penalty affects factual only.
    misconception_variant = json.loads(json.dumps(base))
    misconception_variant["misconceptions"] = ["错误说法：验证集越大越容易过拟合"]
    misconception_scores = scored(misconception_variant)
    assert misconception_scores["factual_correctness"] < base_scores["factual_correctness"]
    assert misconception_scores["explanation_clarity"] == base_scores["explanation_clarity"]
    assert "misconceived_claim" in judge.detail(
        judge.assess(item, "learner-1", misconception_variant).result_id
    ).failure_modes


def test_fabricated_numbers_lower_evidence_and_raise_failure_mode(
    judge: InterviewRubricJudge, items: dict, answers: dict
) -> None:
    result = judge.assess(items["interview.item.q-eng-001"], "learner-1", _answer(answers, "a-fabricated-003"))
    detail = judge.detail(result.result_id)
    assert detail.dimensions["evidence_sufficiency"] <= 0.3
    assert "unsourced_quantitative_claim" in detail.failure_modes
    assert "missing_project_facts" in detail.failure_modes
    assert result.status in {"NEEDS_REVIEW", "INCORRECT"}
    assert result.score < 0.65


# ---------------------------------------------------------------------------
# EVAL_ERROR must stay infrastructure-only
# ---------------------------------------------------------------------------


def test_corrupt_spec_returns_eval_error_and_no_sidecar(
    judge: InterviewRubricJudge, tmp_path: Path, items: dict
) -> None:
    root = tmp_path / "fixtures" / "m1_teacher"
    root.mkdir(parents=True)
    shutil.copytree(INTERVIEW, root / "vertical" / "interview")
    spec_path = root / "vertical" / "interview" / "rubrics" / "scoring" / "q-ml-001.json"
    spec_path.write_text("{not-json", encoding="utf-8")

    broken_judge = InterviewRubricJudge(root)
    result = broken_judge.assess(items["interview.item.q-ml-001"], "learner-1", "x" * 60)
    assert result.status == "EVAL_ERROR"
    assert result.score is None
    assert result.failure_reason == "EVAL_ERROR:INTERVIEW_SPEC_INVALID_JSON"
    assert broken_judge.detail(result.result_id) is None

    spec_path.unlink()
    missing_judge = InterviewRubricJudge(root)
    missing_result = missing_judge.assess(items["interview.item.q-ml-001"], "learner-1", "x" * 60)
    assert missing_result.status == "EVAL_ERROR"
    assert missing_result.failure_reason == "EVAL_ERROR:INTERVIEW_SPEC_MISSING"


def test_invalid_item_or_response_fail_closed(
    judge: InterviewRubricJudge, items: dict
) -> None:
    item = items["interview.item.q-ml-001"]
    with pytest.raises(ValidationError):
        judge.assess("not-an-item", "learner-1", "text")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        judge.assess(item, " ", "text")
    with pytest.raises(ValidationError):
        judge.assess(item, "learner-1", 123)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        judge.detail("   ")

    non_open = AssessmentItem(
        item_id="interview.item.q-ml-001",
        domain_id="interview_coach",
        node_ids=["interview.node.ml_fundamentals"],
        item_type="MCQ",
        difficulty=2,
        prompt="placeholder",
        options=["a", "b"],
        max_score=1.0,
        deterministic=True,
        scoring_spec_ref="scoring/q-ml-001.json",
    )
    with pytest.raises(ValidationError):
        judge.assess(non_open, "learner-1", "text")

    invalid_ref = AssessmentItem(
        item_id="interview.item.q-ml-001",
        domain_id="interview_coach",
        node_ids=["interview.node.ml_fundamentals"],
        item_type="SHORT_ANSWER",
        difficulty=2,
        prompt="placeholder",
        max_score=1.0,
        deterministic=False,
        scoring_spec_ref="../../evil.json",
    )
    escaped = judge.assess(invalid_ref, "learner-1", "x" * 60)
    assert escaped.status == "EVAL_ERROR"
    assert escaped.failure_reason.startswith("EVAL_ERROR:INTERVIEW_SPEC")


# ---------------------------------------------------------------------------
# Determinism / hidden non-leakage / offline
# ---------------------------------------------------------------------------


def test_judge_is_deterministic(
    judge: InterviewRubricJudge, items: dict, answers: dict
) -> None:
    item = items["interview.item.q-ml-001"]
    response = _answer(answers, "a-correct-001")
    first = judge.assess(item, "learner-1", response)
    second = judge.assess(item, "learner-1", response)
    assert first.to_dict() == second.to_dict()
    assert first.result_id == second.result_id

    other = judge.assess(item, "learner-2", response)
    assert other.result_id != first.result_id
    assert other.score == first.score


def test_hidden_material_never_leaks_into_outputs(
    judge: InterviewRubricJudge, items: dict, answers: dict
) -> None:
    for answer in answers.values():
        item = items[f"interview.item.{answer['question_id']}"]
        result = judge.assess(item, "learner-1", answer["response"])
        detail = judge.detail(result.result_id)
        blob = json.dumps(result.to_dict(), ensure_ascii=False)
        if detail is not None:
            blob += json.dumps(detail.to_dict(), ensure_ascii=False)
        spec = _spec_for(answer["question_id"])
        # Hashes in the outputs are opaque digests, not hidden rubric text.
        scrubbed = re.sub(r"[0-9a-f]{16,}", "", blob.lower())
        for groups in spec["expectations"].values():
            for group in groups:
                for token in group:
                    if len(token) < 3:
                        continue
                    assert token.lower() not in scrubbed, (
                        f"hidden expectation token {token!r} leaked for {answer['answer_id']}"
                    )
        assert answer["response"]["text"] not in blob
        assert "rubrics" not in blob.lower()
        assert "expected" not in blob.lower()
        assert result.failure_reason == "" or result.failure_reason.split(":")[0] in {
            "EVAL_ERROR",
            "NEEDS_REVIEW",
            "INCORRECT",
            "PARTIAL",
            "CORRECT",
        }


def test_judge_is_offline_and_cannot_write_learner_state() -> None:
    source = inspect.getsource(judge_module)
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported.isdisjoint({"httpx", "requests", "urllib", "socket", "aiohttp", "autoteacher_m0"})
    for forbidden in (
        "upsert_snapshot",
        "apply_assessment",
        "apply_result",
        "save_session",
        "runtime_port",
    ):
        assert forbidden not in source
    assert "rubrics" in source  # the scorer-side module is the only allowed reader


def test_hidden_spec_matches_adapter_items(
    judge: InterviewRubricJudge, items: dict, adapter: InterviewDomainAdapter
) -> None:
    import hashlib

    for item in items.values():
        question_id = item.item_id.removeprefix("interview.item.")
        spec = _load(SCORING / f"{question_id}.json")
        assert spec["question_id"] == question_id
        assert spec["requires_project_facts"] == adapter.requires_project_facts(item.item_id)
        digest = judge.spec_digest(item)
        assert digest == hashlib.sha256((SCORING / f"{question_id}.json").read_bytes()).hexdigest()
