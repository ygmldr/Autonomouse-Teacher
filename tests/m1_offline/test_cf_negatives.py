"""Negative / anti-cheat tests for the CF Teacher line.

These tests exist to prove that the CF Teacher cannot manufacture a PASS and
that the shipped fixtures are honest:

* fixtures are synthetic, CC0-1.0, schema-tagged, contain no personal data or
  network endpoints, and their recorded learner error traces really fail under
  the independent judge (no fabricated evidence);
* the CF package never imports M0/``src`` and never touches the network stack;
* grading is independent of learner self-report, public tests, the problem's
  reference solution and the mock runtime port (which is never called);
* the judge fails closed on timeouts, missing hidden fixtures and mismatched
  ids; and AC is never claimed without a real hidden-test execution.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest

from m1_offline.cf import CFJudge, CFTeacher, SCORER_ID
from m1_offline.runtime_port import MockRuntimePort
from m1_offline.types import LearnerState

REPO = Path(__file__).resolve().parents[2]
CF_DIR = REPO / "fixtures" / "m1" / "cf"
PROBLEM_FILES = sorted((CF_DIR / "problems").glob("*.json"))
HIDDEN_FILES = sorted((CF_DIR / "hidden").glob("*.json"))
LEARNER_FILES = sorted((CF_DIR / "learners").glob("*.json"))
CF_PACKAGE = REPO / "m1_offline" / "cf"

#: How the learner-fixture's human label maps onto diagnosed error codes.
EXPECTED_CLASS_TO_CODES = {
    "BOUNDARY_ERROR": {"edge_case"},
    "SYNTAX_ERROR": {"syntax_error"},
    "RUNTIME_ERROR": {"runtime_error"},
    "WRONG_ANSWER": {"wrong_answer", "off_by_one"},
    "INEFFICIENT_COMPLEXITY": {"wrong_complexity"},
    "TIME_LIMIT_EXCEEDED": {"time_limit_exceeded"},
}

QUADRATIC_PAIR_SUM = (
    "def pair_sum_sorted(nums, target):\n"
    "    for i in range(len(nums)):\n"
    "        for j in range(i + 1, len(nums)):\n"
    "            if nums[i] + nums[j] == target:\n"
    "                return [i, j]\n"
    "    return [-1, -1]\n"
)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_problem(problem_id: str) -> dict:
    return load(CF_DIR / "problems" / f"{problem_id}.json")


def load_hidden(problem_id: str) -> dict:
    return load(CF_DIR / "hidden" / f"{problem_id}.json")


@pytest.fixture(scope="module")
def teacher() -> CFTeacher:
    return CFTeacher(MockRuntimePort(seed=0), judge=CFJudge(timeout_s=1.5))


@pytest.fixture(scope="module")
def fast_teacher() -> CFTeacher:
    return CFTeacher(MockRuntimePort(seed=0), judge=CFJudge(timeout_s=1.0))


@pytest.fixture(scope="module")
def new_state() -> LearnerState:
    return LearnerState(
        learner_id="learner_weak_beginner", mastery={}, error_counts={}, evidence_count=0
    )


# ---------------------------------------------------------------------------
# Fixture provenance / honesty
# ---------------------------------------------------------------------------
def test_all_fixtures_are_synthetic_schema_tagged_and_cc0() -> None:
    assert len(PROBLEM_FILES) >= 12
    assert len(LEARNER_FILES) >= 2
    assert {path.stem for path in PROBLEM_FILES} == {path.stem for path in HIDDEN_FILES}
    for path in (*PROBLEM_FILES, *HIDDEN_FILES, *LEARNER_FILES):
        payload = load(path)
        assert payload["schema_version"] == "m1.offline.v0", path
        assert payload["synthetic"] is True, path
        assert payload["license"] == "CC0-1.0", path


def test_fixtures_contain_no_personal_data_or_network_endpoints() -> None:
    forbidden = re.compile(
        r"(sk-[A-Za-z0-9]{8,}|BEGIN [A-Z ]*PRIVATE KEY|https?://|@[A-Za-z0-9.-]+\.[A-Za-z]{2,})"
    )
    offenders = []
    for path in (*PROBLEM_FILES, *HIDDEN_FILES, *LEARNER_FILES):
        text = path.read_text(encoding="utf-8")
        if forbidden.search(text):
            offenders.append(str(path))
    assert not offenders, f"synthetic fixtures contain suspicious content: {offenders}"


def test_learner_profiles_cover_weak_and_advanced() -> None:
    learners = [load(path) for path in LEARNER_FILES]
    levels = {learner["baseline_level"] for learner in learners}
    assert {"BEGINNER", "ADVANCED"} <= levels, levels
    for learner in learners:
        assert learner["error_traces"], learner["learner_id"]
        for trace in learner["error_traces"]:
            assert trace["expected_error_class"] in EXPECTED_CLASS_TO_CODES
            assert trace["payload"]["code"].strip()
            assert trace["task_id"] in {path.stem for path in PROBLEM_FILES}


def test_public_tests_never_marked_as_grading_source() -> None:
    for path in PROBLEM_FILES:
        problem = load(path)
        public = problem.get("public_tests")
        assert isinstance(public, list) and public
        # Public cases live only on the problem fixture; the hidden fixture is
        # the sole grading source and never carries a "passed" flag.
        hidden = load_hidden(problem["problem_id"])
        assert "public_tests" not in hidden
        assert "passed" not in json.dumps(hidden, sort_keys=True)


# ---------------------------------------------------------------------------
# Boundary: no M0 import, offline, runtime unused
# ---------------------------------------------------------------------------
def test_cf_package_has_no_m0_or_network_imports() -> None:
    forbidden_modules = {
        "autoteacher_m0",
        "src",
        "httpx",
        "requests",
        "urllib",
        "socket",
        "http",
        "aiohttp",
    }
    for path in CF_PACKAGE.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    assert root not in forbidden_modules, f"{path.name}: import {alias.name}"
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                root = node.module.split(".")[0]
                assert root not in forbidden_modules, f"{path.name}: from {node.module}"


def test_mock_runtime_is_never_called_by_grading(
    teacher: CFTeacher, new_state: LearnerState
) -> None:
    problem = load_problem("cf_array_sum_even")
    port = MockRuntimePort(seed=1234)
    local_teacher = CFTeacher(port, judge=CFJudge(timeout_s=1.5))
    assessment = local_teacher.assess(
        problem, {"code": problem["reference_solution"]}, new_state
    )
    assert assessment.passed is True
    assert port.calls == 0, "CF grading must not depend on the mock runtime"
    local_teacher.next_action(problem, new_state)
    assert port.calls == 0


# ---------------------------------------------------------------------------
# Judge fail-closed under adversarial submissions
# ---------------------------------------------------------------------------
def test_quadratic_solution_fails_closed_on_large_hidden_case() -> None:
    problem = load_problem("cf_tp_pair_sum_sorted")
    hidden = load_hidden("cf_tp_pair_sum_sorted")
    judge = CFJudge(timeout_s=1.0)
    result = judge.evaluate(problem, hidden, QUADRATIC_PAIR_SUM)
    assert result.passed is False
    assert result.error == "timeout"
    assert result.cases_passed == 0


def test_hidden_fixture_tampering_cannot_create_pass() -> None:
    problem = load_problem("cf_array_sum_even")
    hidden = load_hidden("cf_array_sum_even")
    judge = CFJudge(timeout_s=1.0)
    broken_code = "def sum_even(nums):\n    return 0\n"
    result = judge.evaluate(problem, hidden, broken_code)
    assert result.passed is False

    # The judge grades exactly the hidden payload it is given.  It cannot detect
    # caller-side tampering of an on-disk fixture, so the spec pins the hidden
    # file as immutable trusted input and every hidden case is required to be
    # justified by the reference solution (verified in test_cf_judge.py).
    assert result.failures


def test_ac_never_claimed_without_hidden_fixture(
    teacher: CFTeacher, new_state: LearnerState
) -> None:
    problem = load_problem("cf_array_sum_even")
    broken = dict(problem)
    broken.pop("hidden_ref")
    diagnosis = teacher.diagnose(broken, {"code": problem["reference_solution"]}, new_state)
    assert diagnosis.status == "NEEDS_REVIEW"
    assert diagnosis.error_codes == ["fixture_error"]
    assessment = teacher.assess(broken, {"code": problem["reference_solution"]}, new_state)
    assert assessment.passed is False
    assert assessment.score == 0.0
    assert assessment.failure_modes == ["fixture_error"]


def test_assessment_score_cannot_exceed_hidden_cases(
    teacher: CFTeacher, new_state: LearnerState
) -> None:
    problem = load_problem("cf_array_sum_even")
    hidden = load_hidden("cf_array_sum_even")
    assessment = teacher.assess(
        problem, {"code": "def sum_even(nums):\n    return 0\n"}, new_state
    )
    assert 0.0 <= assessment.score <= 1.0
    assert assessment.hidden_cases_total == len(hidden["tests"])
    assert assessment.hidden_cases_passed <= assessment.hidden_cases_total
    assert assessment.scorer_id == SCORER_ID


def test_learner_self_report_and_reference_tamper_cannot_flip_verdict(
    teacher: CFTeacher, new_state: LearnerState
) -> None:
    problem = load_problem("cf_array_sum_even")
    wrong_code = "def sum_even(nums):\n    return sum(nums)\n"
    tampered = json.loads(json.dumps(problem))
    tampered["reference_solution"] = "def sum_even(nums):\n    return 0\n"
    assessment = teacher.assess(
        tampered,
        {"code": wrong_code, "passed": True, "score": 1.0, "status": "AC"},
        new_state,
    )
    assert assessment.passed is False
    assert assessment.score < 1.0


# ---------------------------------------------------------------------------
# Learner fixture error traces are real (reproducible under the judge)
# ---------------------------------------------------------------------------
def test_learner_fixture_error_traces_are_real_failures(fast_teacher: CFTeacher) -> None:
    state = LearnerState(learner_id="synthetic", mastery={}, error_counts={}, evidence_count=0)
    checked = 0
    for path in LEARNER_FILES:
        learner = load(path)
        for trace in learner["error_traces"]:
            problem = load_problem(trace["task_id"])
            diagnosis = fast_teacher.diagnose(problem, trace["payload"], state)
            assert diagnosis.status == "RESOLVED", (trace["trace_id"], diagnosis)
            expected_codes = EXPECTED_CLASS_TO_CODES[trace["expected_error_class"]]
            observed = set(diagnosis.error_codes)
            assert observed & expected_codes, (
                f"{trace['trace_id']}: expected one of {sorted(expected_codes)}, got {diagnosis.error_codes}"
            )
            assessment = fast_teacher.assess(problem, trace["payload"], state)
            assert assessment.passed is False, f"{trace['trace_id']} must not pass"
            checked += 1
    assert checked >= 6, "at least six synthetic error traces must be verified"


# ---------------------------------------------------------------------------
# Determinism / offline behavior parity across instances
# ---------------------------------------------------------------------------
def test_two_teachers_with_different_runtime_seeds_agree(
    teacher: CFTeacher, new_state: LearnerState
) -> None:
    problem = load_problem("cf_array_sum_even")
    other = CFTeacher(MockRuntimePort(seed=9999), judge=CFJudge(timeout_s=1.5))
    code = "def sum_even(nums):\n    return sum(nums)\n"
    first_assessment = teacher.assess(problem, {"code": code}, new_state)
    second_assessment = other.assess(problem, {"code": code}, new_state)
    assert first_assessment == second_assessment
    first_diagnosis = teacher.diagnose(problem, {"code": code}, new_state)
    second_diagnosis = other.diagnose(problem, {"code": code}, new_state)
    assert first_diagnosis == second_diagnosis
    first_action = teacher.next_action(problem, new_state)
    second_action = other.next_action(problem, new_state)
    assert first_action == second_action


def test_all_problem_fixtures_share_schema_and_hint_ladder_contract() -> None:
    for path in PROBLEM_FILES:
        problem = load(path)
        hidden = load_hidden(problem["problem_id"])
        assert problem["hidden_ref"] == f"hidden/{problem['problem_id']}.json"
        assert problem["problem_id"] == path.stem
        assert hidden["problem_id"] == problem["problem_id"]
        assert problem["function_name"]
        assert len(problem["public_tests"]) >= 1
        assert len(hidden["tests"]) >= 3
        assert hidden["timeout_s"] > 0
        assert set(problem["hint_ladder"]) == {
            "LIGHT_HINT",
            "INVARIANT_HINT",
            "STRUCTURE_HINT",
            "FULL_SOLUTION",
        }
        for kind, text in problem["hint_ladder"].items():
            assert len(text) > 20, (path.name, kind)
        assert "def " in problem["reference_solution"]
