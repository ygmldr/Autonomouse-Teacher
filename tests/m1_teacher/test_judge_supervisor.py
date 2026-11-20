"""Unit tests for the trusted judge supervisor (B-PR1 / B1-02/03/04).

The supervisor is exercised with deterministic fake workers, so these tests do
**not** require an OS sandbox: they pin the trust boundary itself:

* default policy is fail-closed (no worker call, blocked verdict);
* the trusted side compares untrusted ``actual_canonical`` values against its
  own expected values with strict canonical JSON (bool/int/float are distinct);
* forged worker observations (``passed``/``verdict``/unknown fields), protocol
  violations and worker failures map to ``JUDGE_INFRA_ERROR``, never PASS;
* the aggregate verdict only exposes classification/count codes; expected and
  argument values never appear in the verdict.

Synthetic sentinels are used and only compared by equality -- never printed.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from m1_teacher.assessment.judge.supervisor import (
    STATUS_JUDGE_INFRA_ERROR,
    STATUS_JUDGE_SANDBOX_UNAVAILABLE,
    STATUS_PASS,
    STATUS_RE,
    STATUS_TLE,
    STATUS_UNTRUSTED_CODE_EXECUTION_BLOCKED,
    STATUS_WA,
    JudgeVerdict,
    TrustedJudgeSupervisor,
)

SENTINEL_EXPECTED = "SENTINEL_DO_NOT_LEAK_EXPECTED_0001"
SENTINEL_ARG = "SENTINEL_DO_NOT_LEAK_ARG_0002"


def observation(status: str, actual_canonical: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        status=status,
        actual_canonical=actual_canonical,
        exception_type=None,
    )


def completed(actual) -> SimpleNamespace:
    import json

    return observation(
        "COMPLETED",
        json.dumps(actual, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(",", ":")),
    )


class FakeWorker:
    """Deterministic worker double; records exactly what crosses the boundary."""

    def __init__(self, outputs, *, available: bool = True) -> None:
        self.outputs = list(outputs)
        self.available = available
        self.calls: list[dict] = []

    def sandbox_available(self) -> bool:
        return self.available

    def run_case(self, code, function_name, args, timeout_s=None):
        self.calls.append(
            {
                "code": code,
                "function_name": function_name,
                "args": list(args),
                "timeout_s": timeout_s,
            }
        )
        if not self.outputs:
            raise AssertionError("fake worker ran out of scripted observations")
        output = self.outputs.pop(0)
        if isinstance(output, BaseException):
            raise output
        return output


def make_tests(*pairs) -> list[dict]:
    return [{"args": list(args), "expected": expected} for args, expected in pairs]


# ---------------------------------------------------------------------------
# Default policy / blocked
# ---------------------------------------------------------------------------
def test_default_policy_blocks_without_touching_worker() -> None:
    worker = FakeWorker([completed(42)])
    supervisor = TrustedJudgeSupervisor(worker)
    verdict = supervisor.evaluate("def f(): return 42", "f", make_tests(([], 42)))
    assert isinstance(verdict, JudgeVerdict)
    assert verdict.status == STATUS_UNTRUSTED_CODE_EXECUTION_BLOCKED
    assert verdict.infra_error is True
    assert verdict.cases_passed == 0
    assert verdict.cases_total == 1
    assert worker.calls == []
    assert "UNTRUSTED_CODE_EXECUTION_BLOCKED" in verdict.failure_codes


def test_explicit_trusted_fixture_only_enables_worker() -> None:
    worker = FakeWorker([completed(42)])
    supervisor = TrustedJudgeSupervisor(worker, trusted_fixture_only=True)
    verdict = supervisor.evaluate("def f(): return 42", "f", make_tests(([], 42)))
    assert verdict.status == STATUS_PASS
    assert verdict.infra_error is False
    assert verdict.score_ratio == 1.0
    assert len(worker.calls) == 1
    assert worker.calls[0]["function_name"] == "f"
    assert worker.calls[0]["args"] == []


def test_unavailable_sandbox_still_fails_closed_without_execution() -> None:
    worker = FakeWorker([completed(42)], available=False)
    supervisor = TrustedJudgeSupervisor(worker, trusted_fixture_only=True)
    verdict = supervisor.evaluate("def f(): return 42", "f", make_tests(([], 42)))
    assert verdict.status == STATUS_JUDGE_SANDBOX_UNAVAILABLE
    assert verdict.infra_error is True
    assert worker.calls == []


# ---------------------------------------------------------------------------
# PASS / WA / strict canonical comparison
# ---------------------------------------------------------------------------
def test_wrong_actual_is_wa_not_pass() -> None:
    worker = FakeWorker([completed(41)])
    supervisor = TrustedJudgeSupervisor(worker, trusted_fixture_only=True)
    verdict = supervisor.evaluate("def f(): return 41", "f", make_tests(([], 42)))
    assert verdict.status == STATUS_WA
    assert verdict.cases_passed == 0
    assert verdict.cases_total == 1
    assert verdict.infra_error is False


def test_partial_cases_are_aggregated() -> None:
    worker = FakeWorker([completed(1), completed(2), completed(3)])
    supervisor = TrustedJudgeSupervisor(worker, trusted_fixture_only=True)
    verdict = supervisor.evaluate(
        "def f(x): return x",
        "f",
        make_tests(([1], 1), ([2], 9), ([3], 3)),
    )
    assert verdict.status == STATUS_WA
    assert verdict.cases_passed == 2
    assert verdict.cases_total == 3
    assert verdict.score_ratio == pytest.approx(2 / 3)
    assert "CASES_FAILED:1/3" in verdict.failure_codes


@pytest.mark.parametrize(
    ("actual", "expected"),
    [
        (1, True),          # int is not bool
        (True, 1),          # bool is not int
        (1, 1.0),           # int is not float
        (1.0, 1),           # float is not int
        ("1", 1),           # string is not number
        ([1, 2], [1, 2.0]),  # list element types differ
    ],
)
def test_canonical_comparison_is_type_strict(actual, expected) -> None:
    worker = FakeWorker([completed(actual)])
    supervisor = TrustedJudgeSupervisor(worker, trusted_fixture_only=True)
    verdict = supervisor.evaluate("def f(): pass", "f", make_tests(([], expected)))
    assert verdict.status == STATUS_WA
    assert verdict.cases_passed == 0


def test_canonical_containers_and_unicode_compare_by_value() -> None:
    worker = FakeWorker([completed({"b": [2, 1], "a": "héllo"})])
    supervisor = TrustedJudgeSupervisor(worker, trusted_fixture_only=True)
    verdict = supervisor.evaluate(
        "def f(): pass", "f", make_tests(([], {"a": "héllo", "b": [2, 1]}))
    )
    assert verdict.status == STATUS_PASS


# ---------------------------------------------------------------------------
# Student failure / timeout classification
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "worker_status", ["RAISED", "SYNTAX_ERROR", "IMPORT_ERROR", "MISSING_FUNCTION"]
)
def test_student_failure_observations_map_to_re(worker_status: str) -> None:
    worker = FakeWorker([observation(worker_status)])
    supervisor = TrustedJudgeSupervisor(worker, trusted_fixture_only=True)
    verdict = supervisor.evaluate("def f(): pass", "f", make_tests(([], 1)))
    assert verdict.status == STATUS_RE
    assert verdict.cases_passed == 0
    assert verdict.infra_error is False


def test_timeout_is_student_tle_even_with_partial_passes() -> None:
    worker = FakeWorker([completed(1), observation("TIMEOUT")])
    supervisor = TrustedJudgeSupervisor(worker, trusted_fixture_only=True)
    verdict = supervisor.evaluate(
        "def f(x): return x", "f", make_tests(([1], 1), ([2], 2))
    )
    assert verdict.status == STATUS_TLE
    assert verdict.cases_passed == 1
    assert verdict.cases_total == 2
    assert verdict.score_ratio == pytest.approx(0.5)
    assert "STUDENT_TLE" in verdict.failure_codes


# ---------------------------------------------------------------------------
# Forged / malformed worker responses -> JUDGE_INFRA_ERROR (fail closed)
# ---------------------------------------------------------------------------
def test_forged_passed_field_is_infra_error() -> None:
    forged = {
        "status": "COMPLETED",
        "actual_canonical": "42",
        "passed": True,
    }
    worker = FakeWorker([forged])
    supervisor = TrustedJudgeSupervisor(worker, trusted_fixture_only=True)
    verdict = supervisor.evaluate("def f(): return 42", "f", make_tests(([], 42)))
    assert verdict.status == STATUS_JUDGE_INFRA_ERROR
    assert verdict.infra_error is True
    assert verdict.cases_passed == 0


@pytest.mark.parametrize(
    "forged",
    [
        {"status": "COMPLETED", "actual_canonical": "42", "verdict": "PASS"},
        {"status": "COMPLETED", "actual_canonical": "42", "score": 1.0},
        {"status": "COMPLETED", "actual_canonical": "42", "expected": 42},
        {"status": "COMPLETED", "actual_canonical": "42", "unknown_field": 1},
        {"status": "COMPLETED", "actual_canonical": "not-json"},
        {"status": "COMPLETED", "actual_canonical": '{"a": 1, "a": 2}'},
        {"status": "COMPLETED", "actual_canonical": " 42 "},
    ],
)
def test_malformed_or_forged_observation_is_infra_error(forged: dict) -> None:
    worker = FakeWorker([forged])
    supervisor = TrustedJudgeSupervisor(worker, trusted_fixture_only=True)
    verdict = supervisor.evaluate("def f(): return 42", "f", make_tests(([], 42)))
    assert verdict.status == STATUS_JUDGE_INFRA_ERROR
    assert verdict.infra_error is True


def test_worker_exception_is_infra_error_not_student_failure() -> None:
    worker = FakeWorker([RuntimeError("worker exploded")])
    supervisor = TrustedJudgeSupervisor(worker, trusted_fixture_only=True)
    verdict = supervisor.evaluate("def f(): return 42", "f", make_tests(([], 42)))
    assert verdict.status == STATUS_JUDGE_INFRA_ERROR
    assert verdict.infra_error is True
    assert verdict.cases_passed == 0


def test_worker_infra_error_observation_is_infra_error() -> None:
    worker = FakeWorker([observation("INFRA_ERROR")])
    supervisor = TrustedJudgeSupervisor(worker, trusted_fixture_only=True)
    verdict = supervisor.evaluate("def f(): pass", "f", make_tests(([], 1)))
    assert verdict.status == STATUS_JUDGE_INFRA_ERROR
    assert verdict.infra_error is True


# ---------------------------------------------------------------------------
# No hidden material / argument values in the aggregate verdict
# ---------------------------------------------------------------------------
def test_verdict_never_contains_expected_or_arg_values() -> None:
    worker = FakeWorker([completed(SENTINEL_ARG), completed(SENTINEL_ARG)])
    supervisor = TrustedJudgeSupervisor(worker, trusted_fixture_only=True)
    verdict = supervisor.evaluate(
        "def f(x): return x",
        "f",
        make_tests(([SENTINEL_ARG], SENTINEL_EXPECTED), ([SENTINEL_ARG], SENTINEL_EXPECTED)),
    )
    rendered = repr(verdict) + repr(verdict.to_dict()) + repr(verdict.failure_codes)
    assert SENTINEL_EXPECTED not in rendered
    assert SENTINEL_ARG not in rendered
    # failure codes are aggregate labels/counts only
    assert all(
        code.startswith(("CASES_FAILED:", "JUDGE_INFRA_ERROR:", "STUDENT_TLE", "WA", "RE"))
        or code in {"WA", "RE", "STUDENT_TLE"}
        for code in verdict.failure_codes
    )


def test_request_boundary_only_receives_code_function_name_and_args() -> None:
    worker = FakeWorker([completed(7)])
    supervisor = TrustedJudgeSupervisor(worker, trusted_fixture_only=True)
    supervisor.evaluate(
        "def f(x): return 7", "f", make_tests(([SENTINEL_ARG], SENTINEL_EXPECTED))
    )
    call = worker.calls[0]
    assert call["code"] == "def f(x): return 7"
    assert call["function_name"] == "f"
    assert call["args"] == [SENTINEL_ARG]
    rendered = repr(call)
    assert SENTINEL_EXPECTED not in rendered
    assert "tests" not in call and "expected" not in call


# ---------------------------------------------------------------------------
# Determinism / validation
# ---------------------------------------------------------------------------
def test_supervisor_is_deterministic_for_identical_inputs() -> None:
    tests = make_tests(([1], 2), ([2], 4))
    first = TrustedJudgeSupervisor(
        FakeWorker([completed(2), completed(4)]), trusted_fixture_only=True
    ).evaluate("def f(x): return 2 * x", "f", tests)
    second = TrustedJudgeSupervisor(
        FakeWorker([completed(2), completed(4)]), trusted_fixture_only=True
    ).evaluate("def f(x): return 2 * x", "f", tests)
    assert first == second
    assert first.to_dict() == second.to_dict()


def test_invalid_tests_configuration_fails_closed() -> None:
    supervisor = TrustedJudgeSupervisor(FakeWorker([]), trusted_fixture_only=True)
    with pytest.raises(ValueError):
        supervisor.evaluate("def f(): pass", "f", [])
    with pytest.raises(ValueError):
        supervisor.evaluate("def f(): pass", "f", [{"args": []}])


def test_invalid_timeout_and_worker_are_rejected() -> None:
    with pytest.raises(ValueError):
        TrustedJudgeSupervisor(timeout_s=0)
    with pytest.raises(ValueError):
        TrustedJudgeSupervisor(timeout_s=60)
    with pytest.raises(ValueError):
        TrustedJudgeSupervisor(trusted_fixture_only="yes")
    with pytest.raises(ValueError):
        TrustedJudgeSupervisor(object())


def test_to_dict_exposes_only_aggregate_fields() -> None:
    verdict = JudgeVerdict(
        status=STATUS_PASS,
        score_ratio=1.0,
        cases_total=3,
        cases_passed=3,
    )
    payload = verdict.to_dict()
    assert set(payload) == {
        "status",
        "score_ratio",
        "cases_total",
        "cases_passed",
        "failure_codes",
        "infra_error",
    }
    assert payload["failure_codes"] == []


# ---------------------------------------------------------------------------
# P1-01: the trusted-fixture opt-in is a code/deployment construction decision
# only; caller data (item/response/result_id/request-like dicts/env) can never
# enable learner-code execution.
# ---------------------------------------------------------------------------
def test_policy_cannot_be_enabled_from_caller_data_paths(monkeypatch) -> None:
    from m1_teacher import demo
    from m1_teacher.assessment.scorer import DeterministicScorer

    components = demo.build_components()
    item = next(
        candidate
        for candidate in components.adapter.assessment_items()
        if candidate.item_type == "CODE"
    )
    executed: list[str] = []

    class NeverWorker:
        def sandbox_available(self) -> bool:
            return True

        def run_case(self, code, function_name, args, timeout_s=None):  # noqa: ANN001
            executed.append(function_name)
            raise AssertionError("learner code must not be executed by default policy")

    scorer = DeterministicScorer(
        components.fixtures_root, judge_worker=NeverWorker()  # default: blocked
    )
    attempts = [
        "def target(*args):\n    return 0\n",
        {
            "code": "def target(*args):\n    return 0\n",
            "trusted_fixture_only": True,
            "execution_policy": "trusted_fixture_only",
            "assessment_job": {"enable_code_execution": True},
        },
        ["def target(*args):\n    return 0\n"],
    ]
    for response in attempts:
        result = scorer.score(
            item,
            "learner.p1-01",
            response,
            result_id="trusted_fixture_only=True;request=enable-code",
        )
        assert result.status == "EVAL_ERROR"
        assert result.failure_reason == "UNTRUSTED_CODE_EXECUTION_BLOCKED"
        assert result.score is None
    assert executed == []

    # No hidden keyword back door on the scoring call itself.
    import pytest as _pytest

    with _pytest.raises(TypeError):
        scorer.score(
            item,
            "learner.p1-01",
            "def target(*args):\n    return 0\n",
            trusted_fixture_only=True,  # type: ignore[call-arg]
        )

    # Environment variables are not a policy source either.
    monkeypatch.setenv("M1B_TRUSTED_FIXTURE_ONLY", "1")
    monkeypatch.setenv("M1_TEACHER_TRUSTED_FIXTURE_ONLY", "1")
    result = scorer.score(
        item, "learner.p1-01", "def target(*args):\n    return 0\n"
    )
    assert result.status == "EVAL_ERROR"
    assert result.failure_reason == "UNTRUSTED_CODE_EXECUTION_BLOCKED"
    assert executed == []

    # The supervisor's default is likewise blocked regardless of test data.
    supervisor = TrustedJudgeSupervisor(NeverWorker(), trusted_fixture_only=False)
    verdict = supervisor.evaluate(
        "def target(*args):\n    return 0\n",
        "target",
        [{"args": [], "expected": 0}],
    )
    assert verdict.status == STATUS_UNTRUSTED_CODE_EXECUTION_BLOCKED
    assert executed == []


def test_constructor_opt_in_is_explicit_and_validated() -> None:
    from m1_teacher import demo
    from m1_teacher.assessment.scorer import DeterministicScorer

    components = demo.build_components()
    scorer = DeterministicScorer(components.fixtures_root)
    assert scorer.trusted_fixture_only is False
    explicit = DeterministicScorer(components.fixtures_root, trusted_fixture_only=True)
    assert explicit.trusted_fixture_only is True
    with pytest.raises(Exception):
        DeterministicScorer(components.fixtures_root, trusted_fixture_only=1)


# ---------------------------------------------------------------------------
# B-Q1: the legacy in-process / bare-subprocess runner must be gone
# ---------------------------------------------------------------------------
def test_legacy_in_process_runner_path_is_removed() -> None:
    import inspect

    from m1_teacher.assessment import scorer as scorer_module

    source = inspect.getsource(scorer_module)
    for forbidden in (
        "_CODE_RUNNER_SOURCE",
        "_run_learner_code",
        "_classify_code_outcome",
        "result.json",
        "subprocess.Popen",
        "sys.executable",
        "import subprocess",
    ):
        assert forbidden not in source, f"legacy CODE runner remnant: {forbidden}"
