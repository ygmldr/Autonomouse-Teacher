"""Tests for the independent deterministic assessment scorer (B-PR4).

Every test is a real assertion against the synthetic CF binary-search fixtures:

* MCQ / CODE / SHORT_ANSWER happy paths and student-error paths;
* the fail-closed EVAL_ERROR boundary (missing / corrupted / path-escaping
  scoring specs, infrastructure failures) and its isolation from mastery;
* semantic rubrics can never fake CORRECT, and hidden material never leaks into
  an ``AssessmentResult``;
* deterministic scoring and the ``AssessmentScorer`` protocol contract.

The tests are allowed to read the hidden scoring specs (they are test code, not
teacher code); teacher-visible modules never import ``scoring/``.
"""

from __future__ import annotations

import ast
import json
import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from m1_teacher.assessment import AssessmentScorer, DeterministicScorer, SCORER_ID_DEFAULT
from m1_teacher.contracts.errors import ValidationError
from m1_teacher.contracts.types import AssessmentItem
from m1_teacher.domains.cf_binary_search import CFBinarySearchDomainAdapter
from m1_teacher.learner.model import MasteryModel

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = REPO_ROOT / "fixtures" / "m1_teacher"
DOMAIN_DIR = FIXTURES_DIR / "domains" / "cf_binary_search"
SCORING_DIR = DOMAIN_DIR / "scoring"
FIXED_TS = "2026-11-20T00:00:00Z"

REFERENCE_SOLUTIONS: dict[str, str] = {
    "binary_search_exact": """\
def binary_search_exact(arr, target):
    low, high = 0, len(arr) - 1
    while low <= high:
        mid = (low + high) // 2
        if arr[mid] == target:
            return mid
        if arr[mid] < target:
            low = mid + 1
        else:
            high = mid - 1
    return -1
""",
    "lower_bound": """\
def lower_bound(arr, target):
    low, high = 0, len(arr)
    while low < high:
        mid = (low + high) // 2
        if arr[mid] < target:
            low = mid + 1
        else:
            high = mid
    return low
""",
    "first_occurrence": """\
def first_occurrence(arr, target):
    low, high = 0, len(arr) - 1
    answer = -1
    while low <= high:
        mid = (low + high) // 2
        if arr[mid] == target:
            answer = mid
            high = mid - 1
        elif arr[mid] < target:
            low = mid + 1
        else:
            high = mid - 1
    return answer
""",
    "count_occurrences": """\
def count_occurrences(arr, target):
    def bound(t, strict):
        low, high = 0, len(arr)
        while low < high:
            mid = (low + high) // 2
            if arr[mid] < t or (strict and arr[mid] == t):
                low = mid + 1
            else:
                high = mid
        return low
    return bound(target, True) - bound(target, False)
""",
    "is_non_decreasing": """\
def is_non_decreasing(arr):
    return all(arr[index] <= arr[index + 1] for index in range(len(arr) - 1))
""",
}


def load_spec(item: AssessmentItem) -> dict:
    relative = item.scoring_spec_ref
    parts = Path(relative).parts
    if parts and parts[0] == "scoring":
        relative = str(Path(*parts[1:]))
    return json.loads((SCORING_DIR / relative).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def adapter() -> CFBinarySearchDomainAdapter:
    domain = CFBinarySearchDomainAdapter(FIXTURES_DIR)
    domain.validate()
    return domain


@pytest.fixture(scope="module")
def items(adapter: CFBinarySearchDomainAdapter) -> dict[str, AssessmentItem]:
    return {item.item_id: item for item in adapter.assessment_items()}


@pytest.fixture(scope="module")
def scorer() -> DeterministicScorer:
    return DeterministicScorer(
        FIXTURES_DIR, clock=lambda: FIXED_TS, trusted_fixture_only=True
    )


# ---------------------------------------------------------------------------
# Protocol / construction
# ---------------------------------------------------------------------------
def test_scorer_satisfies_protocol(scorer: DeterministicScorer) -> None:
    assert isinstance(scorer, AssessmentScorer)
    assert scorer.scorer_id == SCORER_ID_DEFAULT


def test_scorer_rejects_invalid_configuration(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        DeterministicScorer(tmp_path / "missing-fixtures")
    with pytest.raises(ValidationError):
        DeterministicScorer(FIXTURES_DIR, timeout_s=0)
    with pytest.raises(ValidationError):
        DeterministicScorer(FIXTURES_DIR, timeout_s=-1.0)
    with pytest.raises(ValidationError):
        DeterministicScorer(FIXTURES_DIR, scorer_id="  ")
    with pytest.raises(ValidationError):
        DeterministicScorer(FIXTURES_DIR, clock=object())  # type: ignore[arg-type]


def test_scorer_rejects_invalid_inputs(scorer: DeterministicScorer) -> None:
    item = item_of("item.bs.mcq.001")
    with pytest.raises(ValidationError):
        scorer.score(object(), "learner", "A")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        scorer.score(item, "", "A")
    with pytest.raises(ValidationError):
        scorer.score(item, "learner", "A", result_id="  ")


# ---------------------------------------------------------------------------
# MCQ
# ---------------------------------------------------------------------------
def item_of(item_id: str) -> AssessmentItem:
    """Small module-level convenience used by validation tests."""

    adapter = CFBinarySearchDomainAdapter(FIXTURES_DIR)
    for candidate in adapter.assessment_items():
        if candidate.item_id == item_id:
            return candidate
    raise AssertionError(f"unknown item {item_id!r}")


def test_mcq_accepts_structured_letter_and_integer_responses(
    scorer: DeterministicScorer, items: dict[str, AssessmentItem]
) -> None:
    item = items["item.bs.mcq.001"]
    correct = load_spec(item)["correct_option_index"]
    letter = chr(ord("A") + correct)
    for response in ({"choice_index": correct}, letter, correct):
        result = scorer.score(item, "learner.a", response)
        assert result.status == "CORRECT"
        assert result.score == result.max_score == item.max_score
        assert result.failure_reason == ""
        assert result.scorer_id == scorer.scorer_id
        assert result.item_id == item.item_id
        assert result.learner_id == "learner.a"


def test_mcq_wrong_and_invalid_responses(
    scorer: DeterministicScorer, items: dict[str, AssessmentItem]
) -> None:
    item = items["item.bs.mcq.001"]
    correct = load_spec(item)["correct_option_index"]
    wrong = (correct + 1) % len(item.options)
    result = scorer.score(item, "learner.a", {"choice_index": wrong})
    assert result.status == "INCORRECT"
    assert result.score == 0.0
    assert result.failure_reason == "WRONG_OPTION"

    invalid = scorer.score(item, "learner.a", {"not_a_choice": 1})
    assert invalid.status == "INCORRECT"
    assert invalid.failure_reason == "INVALID_RESPONSE"

    out_of_range = scorer.score(item, "learner.a", 99)
    assert out_of_range.status == "INCORRECT"
    assert out_of_range.failure_reason == "OPTION_OUT_OF_RANGE"


# ---------------------------------------------------------------------------
# CODE
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("item_id", "function_name"),
    [
        ("item.bs.code.001", "binary_search_exact"),
        ("item.bs.code.002", "lower_bound"),
        ("item.bs.code.003", "first_occurrence"),
        ("item.bs.code.004", "count_occurrences"),
        ("item.bs.code.005", "is_non_decreasing"),
    ],
)
def test_code_reference_solution_is_correct(
    scorer: DeterministicScorer,
    items: dict[str, AssessmentItem],
    item_id: str,
    function_name: str,
) -> None:
    item = items[item_id]
    assert item.function_name == function_name
    result = scorer.score(item, "learner.a", REFERENCE_SOLUTIONS[function_name])
    assert result.status == "CORRECT", result.failure_reason
    assert result.score == item.max_score


def test_code_partial_credit(
    scorer: DeterministicScorer, items: dict[str, AssessmentItem]
) -> None:
    result = scorer.score(
        items["item.bs.code.001"],
        "learner.a",
        "def binary_search_exact(arr, target):\n    return -1\n",
    )
    assert result.status == "PARTIAL"
    assert 0.0 < (result.score or 0.0) < result.max_score
    assert result.failure_reason.startswith("JUDGE_CASES_FAILED:")


def test_code_wrong_answer_is_incorrect(
    scorer: DeterministicScorer, items: dict[str, AssessmentItem]
) -> None:
    result = scorer.score(
        items["item.bs.code.004"],
        "learner.a",
        "def count_occurrences(arr, target):\n    return -1\n",
    )
    assert result.status == "INCORRECT"
    assert result.score == 0.0
    assert result.failure_reason.startswith("JUDGE_CASES_FAILED:")


def test_code_student_failures_are_not_eval_errors(
    scorer: DeterministicScorer, items: dict[str, AssessmentItem]
) -> None:
    item = items["item.bs.code.001"]
    syntax = scorer.score(item, "learner.a", "def broken(:\n    pass\n")
    assert syntax.status == "INCORRECT"
    assert syntax.failure_reason == "JUDGE_STUDENT_RE"

    runtime = scorer.score(
        item,
        "learner.a",
        "def binary_search_exact(arr, target):\n    raise ValueError('boom')\n",
    )
    assert runtime.status == "INCORRECT"
    assert runtime.failure_reason == "JUDGE_STUDENT_RE"

    missing = scorer.score(item, "learner.a", "def other_name(arr, target):\n    return -1\n")
    assert missing.status == "INCORRECT"
    assert missing.failure_reason == "JUDGE_STUDENT_RE"

    empty = scorer.score(item, "learner.a", "   ")
    assert empty.status == "INCORRECT"
    assert empty.failure_reason == "EMPTY_CODE"


def test_code_timeout_is_student_failure_not_infrastructure(
    items: dict[str, AssessmentItem],
) -> None:
    fast = DeterministicScorer(
        FIXTURES_DIR,
        timeout_s=0.5,
        clock=lambda: FIXED_TS,
        trusted_fixture_only=True,
    )
    result = fast.score(
        items["item.bs.code.001"],
        "learner.a",
        "def binary_search_exact(arr, target):\n    while True:\n        pass\n",
    )
    assert result.status == "INCORRECT"
    assert result.failure_reason == "JUDGE_STUDENT_TLE"
    assert result.score == 0.0


# ---------------------------------------------------------------------------
# EVAL_ERROR: fail-closed infrastructure boundary
# ---------------------------------------------------------------------------
def _referred(item: AssessmentItem, spec_ref: str) -> AssessmentItem:
    return replace(item, scoring_spec_ref=spec_ref)


def test_missing_spec_is_eval_error(
    scorer: DeterministicScorer, items: dict[str, AssessmentItem]
) -> None:
    result = scorer.score(
        _referred(items["item.bs.mcq.001"], "scoring/does_not_exist.json"), "learner.a", 0
    )
    assert result.status == "EVAL_ERROR"
    assert result.score is None
    assert result.failure_reason.startswith("EVAL_ERROR:")


@pytest.mark.parametrize(
    "spec_ref",
    [
        "../assessment_items.json",
        "scoring/../../knowledge_graph.json",
        "/etc/passwd",
        "",
    ],
)
def test_unsafe_or_missing_spec_refs_fail_closed(
    scorer: DeterministicScorer,
    items: dict[str, AssessmentItem],
    spec_ref: str,
) -> None:
    result = scorer.score(_referred(items["item.bs.mcq.001"], spec_ref), "learner.a", 0)
    assert result.status == "EVAL_ERROR"
    assert result.score is None


def test_corrupted_spec_is_eval_error(tmp_path: Path) -> None:
    target = tmp_path / "fixtures"
    shutil.copytree(FIXTURES_DIR, target)
    bad = target / "domains" / "cf_binary_search" / "scoring" / "item.bs.mcq.001.json"
    bad.write_text("{ this is not json", encoding="utf-8")
    local = DeterministicScorer(target, clock=lambda: FIXED_TS)
    adapter = CFBinarySearchDomainAdapter(target)
    item = next(i for i in adapter.assessment_items() if i.item_id == "item.bs.mcq.001")
    result = local.score(item, "learner.a", 0)
    assert result.status == "EVAL_ERROR"
    assert result.failure_reason == "EVAL_ERROR:SPEC_INVALID_JSON"


def test_mcq_spec_with_out_of_range_index_is_eval_error(tmp_path: Path) -> None:
    target = tmp_path / "fixtures"
    shutil.copytree(FIXTURES_DIR, target)
    spec_path = target / "domains" / "cf_binary_search" / "scoring" / "item.bs.mcq.001.json"
    payload = json.loads(spec_path.read_text(encoding="utf-8"))
    payload["correct_option_index"] = 99
    spec_path.write_text(json.dumps(payload), encoding="utf-8")
    local = DeterministicScorer(target, clock=lambda: FIXED_TS)
    adapter = CFBinarySearchDomainAdapter(target)
    item = next(i for i in adapter.assessment_items() if i.item_id == "item.bs.mcq.001")
    result = local.score(item, "learner.a", 0)
    assert result.status == "EVAL_ERROR"
    assert result.failure_reason == "EVAL_ERROR:SPEC_MCQ_INDEX_INVALID"


def test_eval_error_never_mutates_mastery(
    scorer: DeterministicScorer, items: dict[str, AssessmentItem]
) -> None:
    item = _referred(items["item.bs.code.001"], "scoring/missing.json")
    result = scorer.score(item, "learner.a", REFERENCE_SOLUTIONS["binary_search_exact"])
    assert result.status == "EVAL_ERROR"
    model = MasteryModel()
    snapshot = model.initial_snapshot("learner.a")
    updated = model.apply_result(snapshot, item, result)
    assert updated is snapshot
    assert updated.revision == 0
    assert updated.masteries == {}
    assert updated.error_counts == {}


# ---------------------------------------------------------------------------
# SHORT_ANSWER semantic rubric
# ---------------------------------------------------------------------------
def test_short_answer_full_rubric_is_at_most_partial(
    scorer: DeterministicScorer, items: dict[str, AssessmentItem]
) -> None:
    item = items["item.bs.short.001"]
    spec = load_spec(item)
    keywords = [group[0] for group in spec["required_concept_groups"]]
    response = "；".join(keywords) + "，所以区间会持续收缩并最终终止而不出现死循环。"
    result = scorer.score(item, "learner.a", response)
    assert result.status == "PARTIAL"
    assert result.status != "CORRECT"
    assert result.score is not None and 0.0 < result.score <= result.max_score


def test_short_answer_partial_rubric_hits_partial_credit(
    scorer: DeterministicScorer, items: dict[str, AssessmentItem]
) -> None:
    item = items["item.bs.short.003"]
    spec = load_spec(item)
    first_group = spec["required_concept_groups"][0]
    response = f"{first_group[0]}是下界语义，这里只覆盖一个概念组的回答需要更长的文本才能通过。"
    result = scorer.score(item, "learner.a", response)
    assert result.status == "PARTIAL"
    assert result.score is not None and result.score < result.max_score


@pytest.mark.parametrize("response", ["", "   ", "不知道", "abc"])
def test_short_answer_insufficient_is_needs_review_never_correct(
    scorer: DeterministicScorer, items: dict[str, AssessmentItem], response: str
) -> None:
    result = scorer.score(items["item.bs.short.002"], "learner.a", response)
    assert result.status == "NEEDS_REVIEW"
    assert result.status != "CORRECT"
    assert result.score is None
    assert result.failure_reason == "SEMANTIC_UNVERIFIABLE"


def test_short_answer_spec_with_allow_correct_is_rejected(tmp_path: Path) -> None:
    target = tmp_path / "fixtures"
    shutil.copytree(FIXTURES_DIR, target)
    spec_path = target / "domains" / "cf_binary_search" / "scoring" / "item.bs.short.001.json"
    payload = json.loads(spec_path.read_text(encoding="utf-8"))
    payload["allow_correct"] = True
    spec_path.write_text(json.dumps(payload), encoding="utf-8")
    local = DeterministicScorer(target, clock=lambda: FIXED_TS)
    adapter = CFBinarySearchDomainAdapter(target)
    item = next(i for i in adapter.assessment_items() if i.item_id == "item.bs.short.001")
    result = local.score(item, "learner.a", "排除已经比较过的中点，防止死循环，保证区间收缩。")
    assert result.status == "EVAL_ERROR"
    assert "ALLOW_CORRECT" in result.failure_reason


# ---------------------------------------------------------------------------
# Hidden-material leakage
# ---------------------------------------------------------------------------
def test_results_do_not_leak_hidden_spec_material(
    scorer: DeterministicScorer, items: dict[str, AssessmentItem]
) -> None:
    for item_id in ("item.bs.mcq.001", "item.bs.code.001", "item.bs.short.001"):
        item = items[item_id]
        spec = load_spec(item)
        for response in (0, "A", "def broken(:\n    pass\n", "排除已经比较过的中点"):
            result = scorer.score(item, "learner.a", response)
            payload = json.dumps(result.to_dict(), ensure_ascii=False)
            assert "correct_option_index" not in payload
            assert "required_concept_groups" not in payload
            assert "explanation" not in payload
            assert "scoring/" not in payload
            assert '"expected"' not in payload
            assert '"tests"' not in payload
            if "explanation" in spec:
                assert spec["explanation"] not in payload
            for hidden_case in spec.get("tests", []):
                args_repr = json.dumps(hidden_case["args"], ensure_ascii=False)
                if len(args_repr) > 8:
                    assert args_repr not in payload


# ---------------------------------------------------------------------------
# Determinism and identity
# ---------------------------------------------------------------------------
def test_scoring_is_deterministic(
    scorer: DeterministicScorer, items: dict[str, AssessmentItem]
) -> None:
    item = items["item.bs.code.003"]
    code = REFERENCE_SOLUTIONS["first_occurrence"]
    first = scorer.score(item, "learner.a", code)
    second = scorer.score(item, "learner.a", code)
    assert first.to_dict() == second.to_dict()
    assert first.result_id == second.result_id
    assert first.created_at == FIXED_TS

    explicit = scorer.score(item, "learner.a", code, result_id="result.explicit.1")
    assert explicit.result_id == "result.explicit.1"


def test_default_result_id_is_deterministic_and_item_scoped(
    scorer: DeterministicScorer, items: dict[str, AssessmentItem]
) -> None:
    first = scorer.score(items["item.bs.mcq.001"], "learner.a", 0)
    second = scorer.score(items["item.bs.mcq.001"], "learner.b", 0)
    assert first.result_id == second.result_id
    assert first.result_id.startswith("result:item.bs.mcq.001:")
    other = scorer.score(items["item.bs.mcq.002"], "learner.a", 0)
    assert other.result_id != first.result_id


# ---------------------------------------------------------------------------
# Static isolation: only the scorer module may reference the hidden path
# ---------------------------------------------------------------------------
def test_only_scorer_module_references_hidden_scoring_path() -> None:
    package = REPO_ROOT / "m1_teacher"
    offenders: list[str] = []
    for path in sorted(package.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if "scoring/" in text and path.name != "scorer.py":
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, f"modules reference the hidden scoring path: {offenders}"


def test_scorer_has_no_network_or_m0_imports() -> None:
    source = (REPO_ROOT / "m1_teacher" / "assessment" / "scorer.py").read_text(encoding="utf-8")
    assert "autoteacher_m0" not in source
    tree = ast.parse(source)
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imported.append(node.module.split(".")[0])
    forbidden = {"socket", "http", "httpx", "requests", "urllib", "ssl", "aiohttp", "autoteacher_m0"}
    assert not (set(imported) & forbidden), imported
