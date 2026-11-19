"""Tests for the CF isolated hidden-test judge (``m1_offline.cf.judge``).

Contract under test:

* learner code runs in an isolated local subprocess against **hidden** tests
  only (public tests are ignored);
* syntax errors, import-time exceptions, missing functions and timeouts all
  fail closed (``passed=False`` with ``error`` set);
* per-case exceptions are evidence (not a crash) and are reported per case;
* results are deterministic for identical inputs;
* every shipped reference solution passes its own hidden fixture.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from m1_offline.cf import CFJudge, DEFAULT_TIMEOUT_S, JUDGE_VERSION, JudgeResult

REPO = Path(__file__).resolve().parents[2]
CF_DIR = REPO / "fixtures" / "m1" / "cf"
PROBLEM_IDS = sorted(path.stem for path in (CF_DIR / "problems").glob("*.json"))

CORRECT_SUM_EVEN = """\
def sum_even(nums):
    total = 0
    for value in nums:
        if value % 2 == 0:
            total += value
    return total
"""

WRONG_SUM_EVEN = """\
def sum_even(nums):
    return sum(nums)
"""

SYNTAX_BROKEN = """\
def sum_even(nums)
    total = 0
    return total
"""

RAISES_EVERY_CASE = """\
def sum_even(nums):
    raise ValueError("boom")
"""

MODULE_LEVEL_FAILURE = """\
raise RuntimeError("module import exploded")
"""

MISSING_FUNCTION = """\
def not_the_expected_name(nums):
    return 0
"""

HANGING = """\
def sum_even(nums):
    while True:
        pass
"""

PRINTS_AND_PASSES = """\
def sum_even(nums):
    print("synthetic learner debug output")
    total = 0
    for value in nums:
        if value % 2 == 0:
            total += value
    return total
"""


def load_problem(problem_id: str) -> dict:
    return json.loads((CF_DIR / "problems" / f"{problem_id}.json").read_text(encoding="utf-8"))


def load_hidden(problem_id: str) -> dict:
    return json.loads((CF_DIR / "hidden" / f"{problem_id}.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def judge() -> CFJudge:
    return CFJudge(timeout_s=1.5)


@pytest.fixture(scope="module")
def sum_even_problem() -> dict:
    return load_problem("cf_array_sum_even")


@pytest.fixture(scope="module")
def sum_even_hidden() -> dict:
    return load_hidden("cf_array_sum_even")


# ---------------------------------------------------------------------------
# Inventory / reference self-consistency
# ---------------------------------------------------------------------------
def test_fixture_inventory_has_required_coverage() -> None:
    """>=12 problems covering every required algorithm family, with hidden files."""

    assert len(PROBLEM_IDS) >= 12, f"expected >=12 problems, found {len(PROBLEM_IDS)}"
    skills: set[str] = set()
    for problem_id in PROBLEM_IDS:
        problem = load_problem(problem_id)
        hidden = load_hidden(problem_id)
        assert problem["hidden_ref"] == f"hidden/{problem_id}.json"
        assert hidden["problem_id"] == problem_id
        assert hidden["tests"], f"{problem_id}: hidden tests must not be empty"
        assert problem["synthetic"] is True
        assert problem["license"] == "CC0-1.0"
        assert set(problem["hint_ladder"]) == {
            "LIGHT_HINT",
            "INVARIANT_HINT",
            "STRUCTURE_HINT",
            "FULL_SOLUTION",
        }
        skills.update(problem["skills"])
        # Every function name in a fixture is what the judge invokes.
        assert problem["function_name"]
        # Hidden cases are JSON-test shaped and tagged for diagnosis.
        for case in hidden["tests"]:
            assert isinstance(case["args"], list)
            assert "expected" in case
            assert case.get("kind") in {"edge", "normal", "large"}
    # Required families: arrays, two pointers, sorting/binary search, graphs, DP.
    assert {"array-basics", "two-pointers", "binary-search", "graph-basics", "dp-basics"} <= skills
    assert any(skill in skills for skill in ("prefix-sums", "sorting", "bfs"))
    assert sum(
        1
        for problem_id in PROBLEM_IDS
        if any(case["kind"] == "large" for case in load_hidden(problem_id)["tests"])
    ) >= 5


@pytest.mark.parametrize("problem_id", PROBLEM_IDS)
def test_reference_solution_passes_own_hidden_tests(problem_id: str, judge: CFJudge) -> None:
    problem = load_problem(problem_id)
    hidden = load_hidden(problem_id)
    result = judge.evaluate(problem, hidden, problem["reference_solution"])
    assert isinstance(result, JudgeResult)
    assert result.error is None, result.error
    assert result.cases_total == len(hidden["tests"])
    assert result.cases_passed == result.cases_total, result.failures
    assert result.passed is True


# ---------------------------------------------------------------------------
# Hidden-only grading
# ---------------------------------------------------------------------------
def test_uses_hidden_tests_only_and_ignores_public_tests(
    judge: CFJudge, sum_even_problem: dict, sum_even_hidden: dict
) -> None:
    baseline = judge.evaluate(sum_even_problem, sum_even_hidden, CORRECT_SUM_EVEN)
    assert baseline.passed is True

    tampered_problem = json.loads(json.dumps(sum_even_problem))
    tampered_problem["public_tests"] = [{"args": [[]], "expected": 999999}]
    tampered_problem["reference_solution"] = "def sum_even(nums): return 42"
    tampered = judge.evaluate(tampered_problem, sum_even_hidden, CORRECT_SUM_EVEN)
    assert tampered == baseline

    # A submission that matches a tampered public expectation must still fail
    # against the real hidden tests.
    cheating_problem = json.loads(json.dumps(sum_even_problem))
    cheating_problem["public_tests"] = [{"args": [[]], "expected": 0}]
    result = judge.evaluate(cheating_problem, sum_even_hidden, "def sum_even(nums):\n    return 999999\n")
    assert result.passed is False
    assert result.error is None


def test_public_tests_alone_cannot_pass_a_hidden_failing_submission(
    judge: CFJudge, sum_even_problem: dict, sum_even_hidden: dict
) -> None:
    # Passes both public cases, fails hidden cases.
    code = "def sum_even(nums):\n    return 6 if nums else 0\n"
    for case in sum_even_problem["public_tests"]:
        assert (6 if case["args"][0] else 0) == case["expected"]
    result = judge.evaluate(sum_even_problem, sum_even_hidden, code)
    assert result.passed is False
    assert result.cases_passed < result.cases_total
    assert result.failures


# ---------------------------------------------------------------------------
# Correct / wrong answers
# ---------------------------------------------------------------------------
def test_correct_solution_passes(
    judge: CFJudge, sum_even_problem: dict, sum_even_hidden: dict
) -> None:
    result = judge.evaluate(sum_even_problem, sum_even_hidden, CORRECT_SUM_EVEN)
    assert result.passed is True
    assert result.error is None
    assert result.cases_passed == result.cases_total
    assert result.failures == []
    assert result.stdout_excerpt == ""


def test_wrong_solution_fails_with_per_case_failures(
    judge: CFJudge, sum_even_problem: dict, sum_even_hidden: dict
) -> None:
    result = judge.evaluate(sum_even_problem, sum_even_hidden, WRONG_SUM_EVEN)
    assert result.passed is False
    assert result.error is None
    assert result.cases_total == len(sum_even_hidden["tests"])
    assert result.cases_passed < result.cases_total
    assert result.failures, "wrong answers must be reported as per-case failures"
    assert all(failure.startswith("case-") for failure in result.failures)


def test_learner_stdout_is_captured_as_excerpt(
    judge: CFJudge, sum_even_problem: dict, sum_even_hidden: dict
) -> None:
    result = judge.evaluate(sum_even_problem, sum_even_hidden, PRINTS_AND_PASSES)
    assert result.passed is True
    assert "synthetic learner debug output" in result.stdout_excerpt


def test_per_case_exception_is_evidence_not_a_crash(
    judge: CFJudge, sum_even_problem: dict, sum_even_hidden: dict
) -> None:
    result = judge.evaluate(sum_even_problem, sum_even_hidden, RAISES_EVERY_CASE)
    assert result.passed is False
    assert result.error is None, "per-case exceptions are recorded as failures, not fatal errors"
    assert result.cases_passed == 0
    assert result.failures
    assert all("raised ValueError" in failure for failure in result.failures)


# ---------------------------------------------------------------------------
# Fail-closed abnormal conditions
# ---------------------------------------------------------------------------
def test_syntax_error_fails_closed(
    judge: CFJudge, sum_even_problem: dict, sum_even_hidden: dict
) -> None:
    result = judge.evaluate(sum_even_problem, sum_even_hidden, SYNTAX_BROKEN)
    assert result.passed is False
    assert result.error == "syntax_error"
    assert result.cases_passed == 0


def test_module_level_exception_fails_closed(
    judge: CFJudge, sum_even_problem: dict, sum_even_hidden: dict
) -> None:
    result = judge.evaluate(sum_even_problem, sum_even_hidden, MODULE_LEVEL_FAILURE)
    assert result.passed is False
    assert result.error == "import_error"
    assert result.cases_passed == 0


def test_missing_function_fails_closed(
    judge: CFJudge, sum_even_problem: dict, sum_even_hidden: dict
) -> None:
    result = judge.evaluate(sum_even_problem, sum_even_hidden, MISSING_FUNCTION)
    assert result.passed is False
    assert result.error == "missing_function"
    assert result.cases_passed == 0
    assert result.cases_total == len(sum_even_hidden["tests"])


def test_timeout_fails_closed(
    sum_even_problem: dict, sum_even_hidden: dict
) -> None:
    fast_judge = CFJudge(timeout_s=0.5)
    started = time.monotonic()
    result = fast_judge.evaluate(sum_even_problem, sum_even_hidden, HANGING)
    elapsed = time.monotonic() - started
    assert result.passed is False
    assert result.error == "timeout"
    assert result.cases_passed == 0
    assert elapsed < 3.0, f"timeout enforcement took {elapsed:.2f}s"


def test_judge_rejects_empty_hidden_suite_fail_closed(
    judge: CFJudge, sum_even_problem: dict
) -> None:
    result = judge.evaluate(sum_even_problem, {"tests": []}, CORRECT_SUM_EVEN)
    assert result.passed is False
    assert result.error == "invalid_input"


def test_judge_rejects_hidden_problem_id_mismatch(
    judge: CFJudge, sum_even_problem: dict, sum_even_hidden: dict
) -> None:
    mismatched = json.loads(json.dumps(sum_even_hidden))
    mismatched["problem_id"] = "cf_dp_lcs"
    result = judge.evaluate(sum_even_problem, mismatched, CORRECT_SUM_EVEN)
    assert result.passed is False
    assert result.error == "invalid_input"


def test_judge_rejects_non_string_code(
    judge: CFJudge, sum_even_problem: dict, sum_even_hidden: dict
) -> None:
    result = judge.evaluate(sum_even_problem, sum_even_hidden, None)  # type: ignore[arg-type]
    assert result.passed is False
    assert result.error == "invalid_input"


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------
def test_result_is_deterministic_for_identical_input(
    judge: CFJudge, sum_even_problem: dict, sum_even_hidden: dict
) -> None:
    first = judge.evaluate(sum_even_problem, sum_even_hidden, WRONG_SUM_EVEN)
    second = judge.evaluate(sum_even_problem, sum_even_hidden, WRONG_SUM_EVEN)
    assert first == second
    fresh_judge = CFJudge(timeout_s=1.5)
    third = fresh_judge.evaluate(sum_even_problem, sum_even_hidden, WRONG_SUM_EVEN)
    assert third == first


def test_correct_result_is_deterministic(
    judge: CFJudge, sum_even_problem: dict, sum_even_hidden: dict
) -> None:
    first = judge.evaluate(sum_even_problem, sum_even_hidden, CORRECT_SUM_EVEN)
    second = judge.evaluate(sum_even_problem, sum_even_hidden, CORRECT_SUM_EVEN)
    assert first == second


def test_judge_module_is_offline_and_m0_free() -> None:
    source = Path(__file__).resolve().parents[2] / "m1_offline" / "cf" / "judge.py"
    text = source.read_text(encoding="utf-8")
    assert "autoteacher_m0" not in text
    for forbidden in ("httpx", "requests", "urllib.request", "socket."):
        assert forbidden not in text, f"judge must not use network stack: {forbidden}"
    assert JUDGE_VERSION == "cf.hidden.judge.v0"
    assert DEFAULT_TIMEOUT_S < 5.0
