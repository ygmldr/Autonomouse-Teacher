"""Tests for the deterministic, runtime-free four-dimension interview rubric.

Coverage map (task-3 acceptance):
* fixture corpus shape/licensing + hidden-set separation basics;
* four separated, bounded dimensions and determinism (same input -> same output);
* dimension independence under single-axis perturbations;
* fabricated numbers / missing project facts -> low evidence + failure mode;
* rubric never touches a runtime (mock call count 0 + no runtime imports).
"""

from __future__ import annotations

import copy
import inspect
import json
import re
from pathlib import Path

import pytest

from m1_offline.interview import DIMENSIONS, FAILURE_MODES, InterviewRubric
from m1_offline.interview import rubric as rubric_module
from m1_offline.runtime_port import MockRuntimePort

REPO_ROOT = Path(__file__).resolve().parents[2]
INTERVIEW_DIR = REPO_ROOT / "fixtures" / "m1" / "interview"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _question(question_id: str) -> dict:
    return _load(INTERVIEW_DIR / "questions" / f"{question_id}.json")


def _answer(answer_id: str) -> dict:
    return _load(INTERVIEW_DIR / "answers" / f"{answer_id}.json")["answer"]


def _all_questions() -> list[dict]:
    return [_load(path) for path in sorted((INTERVIEW_DIR / "questions").glob("*.json"))]


def _all_answers() -> list[dict]:
    return [_load(path) for path in sorted((INTERVIEW_DIR / "answers").glob("*.json"))]


def _all_hidden() -> list[dict]:
    return [_load(path) for path in sorted((INTERVIEW_DIR / "hidden").glob("*.json"))]


@pytest.fixture(scope="module")
def rubric() -> InterviewRubric:
    return InterviewRubric()


def test_fixture_corpus_counts_and_contract() -> None:
    questions = _all_questions()
    answers = _all_answers()
    hidden = _all_hidden()

    assert len(questions) >= 20
    assert {question["track"] for question in questions} == {
        "recommendation_ctr",
        "ml_fundamentals",
        "engineering_metrics",
        "system_design",
    }, "all four required tracks must be covered"

    for question in questions:
        assert question["schema_version"] == "m1.offline.v0"
        assert question["synthetic"] is True
        assert question["license"] == "CC0-1.0"
        assert set(question["rubric_points"]) == set(DIMENSIONS)
        for dimension in DIMENSIONS:
            points = question["rubric_points"][dimension]
            assert isinstance(points, list) and points, f"{dimension} points missing"
            assert all(isinstance(item, str) and "|" in item for item in points)
        assert len(question["follow_up_ladder"]) == 5
        assert isinstance(question["requires_project_facts"], bool)

    assert len(answers) >= 8
    question_ids = {question["question_id"] for question in questions}
    for answer in answers:
        assert answer["schema_version"] == "m1.offline.v0"
        assert answer["question_id"] in question_ids
        assert answer["synthetic"] is True
        assert answer["license"] == "CC0-1.0"
        payload = answer["answer"]
        assert isinstance(payload["text"], str) and payload["text"].strip()
        assert isinstance(payload["evidence_refs"], list)
        assert isinstance(payload["project_facts"], list)
        assert isinstance(payload["quantitative_claims"], list)
        assert isinstance(payload["misconceptions"], list)

    assert len(hidden) >= 6
    assert all(item.get("hidden") is True for item in hidden)
    assert not ({item["question_id"] for item in hidden} & question_ids), "hidden ids must not leak into the public set"


def test_rubric_returns_four_bounded_dimensions(rubric: InterviewRubric) -> None:
    question, answer = _question("q-ml-001"), _answer("a-correct-001")
    scores = rubric.score(question, answer)

    assert list(scores) == list(DIMENSIONS)
    assert all(isinstance(value, float) for value in scores.values())
    assert all(0.0 <= value <= 1.0 for value in scores.values())

    feedback = rubric.feedback(question, answer)
    assert isinstance(feedback, list) and feedback
    assert all(isinstance(line, str) and line.strip() for line in feedback)
    assert set(rubric.failure_modes(question, answer)) <= set(FAILURE_MODES)


def test_rubric_is_deterministic_and_side_effect_free(rubric: InterviewRubric) -> None:
    question, answer = _question("q-sys-002"), _answer("a-strong-008")
    question_snapshot, answer_snapshot = copy.deepcopy(question), copy.deepcopy(answer)

    first = (rubric.score(question, answer), rubric.feedback(question, answer), rubric.failure_modes(question, answer))
    second_rubric = InterviewRubric()
    second = (
        second_rubric.score(question, answer),
        second_rubric.feedback(question, answer),
        second_rubric.failure_modes(question, answer),
    )

    assert first == second
    assert question == question_snapshot and answer == answer_snapshot, "rubric must not mutate inputs"


def test_dimensions_are_computed_independently(rubric: InterviewRubric) -> None:
    question = _question("q-eng-001")
    base = _answer("a-fabricated-003")
    base_scores = rubric.score(question, base)

    # 1) Clarity-only perturbation: add structure/connectors without factual tokens.
    clarity_variant = copy.deepcopy(base)
    clarity_variant["text"] += "\n\n首先，我会说明背景定义；其次，我会说明原因；最后，我会给出结论。"
    clarity_scores = rubric.score(question, clarity_variant)
    assert clarity_scores["explanation_clarity"] > base_scores["explanation_clarity"]
    assert clarity_scores["factual_correctness"] == base_scores["factual_correctness"]
    assert clarity_scores["engineering_feasibility"] == base_scores["engineering_feasibility"]
    assert clarity_scores["evidence_sufficiency"] == base_scores["evidence_sufficiency"]

    # 2) Evidence-only perturbation: attach verifiable references to the same claims.
    evidence_variant = copy.deepcopy(base)
    evidence_variant["evidence_refs"] = ["synthetic:audit-log-1", "synthetic:ab-report-2"]
    for claim in evidence_variant["quantitative_claims"]:
        claim["evidence_refs"] = ["synthetic:audit-log-1"]
    evidence_scores = rubric.score(question, evidence_variant)
    assert evidence_scores["evidence_sufficiency"] > base_scores["evidence_sufficiency"]
    assert evidence_scores["factual_correctness"] == base_scores["factual_correctness"]
    assert evidence_scores["explanation_clarity"] == base_scores["explanation_clarity"]
    assert evidence_scores["engineering_feasibility"] == base_scores["engineering_feasibility"]

    # 3) Factual-only perturbation: remove one expected concept group from the text.
    factual_variant = copy.deepcopy(_answer("a-correct-001"))
    factual_variant["text"] = (
        factual_variant["text"]
        .replace("正则化", "处理C")
        .replace("L1", "处理A")
        .replace("L2", "处理B")
    )
    factual_scores = rubric.score(_question("q-ml-001"), factual_variant)
    original_scores = rubric.score(_question("q-ml-001"), _answer("a-correct-001"))
    assert factual_scores["factual_correctness"] < original_scores["factual_correctness"]
    assert factual_scores["explanation_clarity"] == original_scores["explanation_clarity"]
    assert factual_scores["engineering_feasibility"] == original_scores["engineering_feasibility"]
    assert factual_scores["evidence_sufficiency"] == original_scores["evidence_sufficiency"]

    # 4) Misconception perturbation: factual penalty only.
    misconception_variant = copy.deepcopy(_answer("a-correct-001"))
    misconception_variant["misconceptions"] = ["错误说法：验证集越大越容易过拟合"]
    misconception_scores = rubric.score(_question("q-ml-001"), misconception_variant)
    assert misconception_scores["factual_correctness"] < original_scores["factual_correctness"]
    assert misconception_scores["explanation_clarity"] == original_scores["explanation_clarity"]
    assert misconception_scores["evidence_sufficiency"] == original_scores["evidence_sufficiency"]


def test_fabricated_numbers_lower_evidence_only(rubric: InterviewRubric) -> None:
    question, answer = _question("q-eng-001"), _answer("a-fabricated-003")
    scores = rubric.score(question, answer)
    modes = rubric.failure_modes(question, answer)

    assert scores["evidence_sufficiency"] <= 0.3, "unsourced 37% / scale claims must be low evidence"
    assert "unsourced_quantitative_claim" in modes
    assert "missing_project_facts" in modes
    assert scores["factual_correctness"] >= 0.5, "fabrication is an evidence failure, not a keyword failure"

    feedback = " ".join(rubric.feedback(question, answer))
    assert "无来源" in feedback
    assert "项目事实边界" in feedback


def test_correct_answer_scores_high_without_failure_modes(rubric: InterviewRubric) -> None:
    question, answer = _question("q-ml-001"), _answer("a-correct-001")
    scores = rubric.score(question, answer)

    assert scores["factual_correctness"] >= 0.75
    assert scores["explanation_clarity"] >= 0.6
    assert scores["evidence_sufficiency"] >= 0.6
    assert rubric.failure_modes(question, answer) == []


def test_vague_answer_flags_clarity_and_concept(rubric: InterviewRubric) -> None:
    question, answer = _question("q-rec-001"), _answer("a-vague-002")
    scores = rubric.score(question, answer)
    modes = rubric.failure_modes(question, answer)

    assert scores["explanation_clarity"] < 0.3
    assert "vague_explanation" in modes
    assert "incorrect_concept" in modes
    assert "表达清晰度不足" in " ".join(rubric.feedback(question, answer))


def test_infeasible_design_lowers_feasibility(rubric: InterviewRubric) -> None:
    question, answer = _question("q-sys-001"), _answer("a-infeasible-006")
    scores = rubric.score(question, answer)
    modes = rubric.failure_modes(question, answer)

    assert scores["engineering_feasibility"] <= 0.2
    assert "infeasible_engineering_design" in modes
    assert "不现实约束" in " ".join(rubric.feedback(question, answer))


def test_misconception_is_penalised_as_misconceived_claim(rubric: InterviewRubric) -> None:
    question, answer = _question("q-ml-002"), _answer("a-partial-005")
    scores = rubric.score(question, answer)
    modes = rubric.failure_modes(question, answer)

    assert "misconceived_claim" in modes
    assert scores["factual_correctness"] < 0.8
    assert "错误陈述" in " ".join(rubric.feedback(question, answer))


def test_unsourced_claim_lowers_evidence_but_not_factual(rubric: InterviewRubric) -> None:
    question, answer = _question("q-rec-001"), _answer("a-unsourced-007")
    scores = rubric.score(question, answer)

    assert scores["evidence_sufficiency"] <= 0.2
    assert scores["factual_correctness"] >= 0.75, "concept coverage is a separate dimension"
    assert "unsourced_quantitative_claim" in rubric.failure_modes(question, answer)


def test_all_questions_are_scorable(rubric: InterviewRubric) -> None:
    generic_answer = {"text": "我会先看指标，再分析原因，最后给出结论。", "evidence_refs": []}
    for question in _all_questions():
        scores = rubric.score(question, generic_answer)
        assert set(scores) == set(DIMENSIONS)
        assert all(0.0 <= value <= 1.0 for value in scores.values())
        assert isinstance(rubric.feedback(question, generic_answer), list)


def test_rubric_never_uses_runtime(rubric: InterviewRubric) -> None:
    runtime = MockRuntimePort(seed=7)
    for answer in _all_answers():
        question = _question(answer["question_id"])
        rubric.score(question, answer["answer"])
        rubric.feedback(question, answer["answer"])
        rubric.failure_modes(question, answer["answer"])
    assert runtime.calls == 0

    assert not hasattr(rubric, "runtime")
    source = inspect.getsource(rubric_module)
    assert not re.search(r"(?m)^\s*(?:from|import)\s+m1_offline\.runtime_port", source)
    assert not re.search(r"(?m)^\s*(?:from|import).*\bRuntimePort\b", source)
    for network_token in ("requests", "httpx", "socket"):
        assert network_token not in source


def test_rubric_rejects_malformed_inputs(rubric: InterviewRubric) -> None:
    question, answer = _question("q-ml-001"), _answer("a-correct-001")
    with pytest.raises(TypeError):
        rubric.score("not-a-dict", answer)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        rubric.score(question, {"text": 123})
    with pytest.raises(TypeError):
        rubric.feedback(question, "not-a-dict")  # type: ignore[arg-type]
