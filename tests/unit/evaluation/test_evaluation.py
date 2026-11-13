import json
from dataclasses import replace

import pytest

from autoteacher_m0.contracts import RunRequest
from autoteacher_m0.evaluation import EvaluationResult, evaluate
from autoteacher_m0.evaluation.leakage_checks import check_solution_leakage
from autoteacher_m0.experiments.fixtures import load_cases
from autoteacher_m0.experiments.mock import TeachingMockRuntime


def example():
    case = load_cases()[0]
    request = RunRequest(case.case_id, case.student_input, "teacher_v0", "test-session",
                         "mock", "deepseek-flash", "mock")
    return case, TeachingMockRuntime().run(request)


def test_all_fixture_contracts_public_fictional_and_split():
    cases = load_cases()
    assert len(cases) == 20
    assert sum(case.split == "development" for case in cases) == 12
    assert sum(case.required_actions == ("ask_clarification",) for case in cases) == 2
    assert all(case.provenance == "PUBLIC_FICTIONAL_MOCK" for case in cases)


def test_genuine_mock_relational_explanation_passes():
    case, record = example()
    result = evaluate(case, record)
    assert result.status == "SCORED" and result.score == 1
    assert result.checks["concept_relations"]


def test_keyword_soup_does_not_earn_concept_relation_credit():
    case, record = example()
    response = json.loads(record.text)
    response["explanation"] = "binary search feasibility monotonicity log n predicate"
    record.text = json.dumps(response)
    result = evaluate(case, record)
    assert result.status == "SCORED" and result.score < 1
    assert result.checks["concept_relations"] is False


def test_negated_relational_sentence_needs_review_not_confident_pass():
    case, record = example()
    response = json.loads(record.text)
    response["explanation"] = "It is not true that " + response["explanation"]
    record.text = json.dumps(response)
    result = evaluate(case, record)
    assert result.status == "NEEDS_REVIEW" and result.score is None


def test_grader_exception_is_error_with_none_not_zero_or_payload():
    case, record = example()
    def broken(*args):
        raise RuntimeError("sk-FAKE_SENTINEL_NEVER_LOG")
    result = evaluate(case, record, grader=broken)
    assert result.status == "EVAL_ERROR" and result.score is None
    assert "sk-FAKE" not in str(result)


@pytest.mark.parametrize("result", [None, 0, EvaluationResult("SCORED", None, "v"),
                                   EvaluationResult("NEEDS_REVIEW", 0, "v"),
                                   EvaluationResult("BOGUS", None, "v")])
def test_invalid_grader_results_fail_explicitly(result):
    case, record = example()
    actual = evaluate(case, record, grader=lambda *args: result)
    assert actual.status == "EVAL_ERROR" and actual.score is None


def test_runtime_failure_is_not_score_zero():
    case, record = example()
    record.status, record.error_code = "ERROR", "TIMEOUT"
    result = evaluate(case, record)
    assert result.status == "RUN_ERROR" and result.score is None


def test_unsupported_evaluator_and_case_mismatch_are_errors():
    case, record = example()
    assert evaluate(replace(case, evaluator_version="unknown"), record).status == "EVAL_ERROR"
    record.case_id = "other"
    assert evaluate(case, record).status == "EVAL_ERROR"


@pytest.mark.parametrize("text", [
    "```python\ndef solve(a):\n    for x in a:\n        if x:\n            return x\n```",
    "```cpp\nint main(){ int n; cin>>n; for(int i=0;i<n;i++) cout<<i; return 0;}\n```",
    "class Solution { int solve(){ return 1; } };",
    "n=int(input())\nfor i in range(n):\n print(i)",
    "Complete solution: first do all the work, then output it.",
])
def test_representative_complete_solution_negative_cases(text):
    assert check_solution_leakage(text).status == "LEAK"


@pytest.mark.parametrize("text", ["```python\nmid = l + (r-l)//2\n```", "```\nincomplete", "return index"])
def test_boundary_code_is_review_not_a_clean_pass(text):
    assert check_solution_leakage(text).status == "NEEDS_REVIEW"


def test_complete_code_scores_zero_with_explicit_leak_reason():
    case, record = example()
    response = json.loads(record.text)
    response["code"] = "def solve(a):\n    for x in a:\n        return x"
    record.text = json.dumps(response)
    result = evaluate(case, record)
    assert result.status == "SCORED" and result.score == 0
    assert result.checks["no_complete_solution"] is False


def test_unstructured_or_schema_invalid_is_needs_review():
    case, record = example()
    record.text = "A natural-language answer requiring independent review."
    assert evaluate(case, record).status == "NEEDS_REVIEW"
    record.text = "[]"
    assert evaluate(case, record).score is None
