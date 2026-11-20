"""Correctness certification for the trusted judge supervisor (B-PR1 / B1-05).

This module exercises the **real** untrusted worker + bwrap sandbox from the
merged sandbox workstream through :class:`TrustedJudgeSupervisor`:

* all 14 reference solutions in ``fixtures/m1_teacher/judge/certification/``
  pass every hidden case (112/112 total) through the trusted comparison path;
* the synthetic negatives are classified as WA / RE / TLE / PASS (edge-correct)
  according to the certification corpus;
* identical inputs produce identical aggregate verdicts;
* failure codes stay aggregate-only (classification/counts), never expected or
  argument values.

Evidence class: ``MOCK`` / ``DETERMINISTIC`` (offline synthetic fixtures only;
no network, no Provider/Key, no real learner data).  If the host cannot provide
the bwrap sandbox (e.g. user namespaces disabled), the module skips with an
explicit reason: the fail-closed policy itself is covered by
``test_judge_supervisor.py`` without touching an OS sandbox.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest

from m1_teacher.assessment.judge.worker import UntrustedExecutionWorker
from m1_teacher.assessment.judge.supervisor import (
    STATUS_JUDGE_SANDBOX_UNAVAILABLE,
    STATUS_PASS,
    STATUS_RE,
    STATUS_TLE,
    STATUS_WA,
    TrustedJudgeSupervisor,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
JUDGE_FIXTURES = REPO_ROOT / "fixtures" / "m1_teacher" / "judge"
CASES_PATH = JUDGE_FIXTURES / "certification" / "cases.json"
NEGATIVES_PATH = JUDGE_FIXTURES / "certification" / "negatives.json"

CERT_TIMEOUT_S = 2.0
TLE_TIMEOUT_S = 0.5


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


CASES_DOC = _load_json(CASES_PATH)
NEGATIVES_DOC = _load_json(NEGATIVES_PATH)
CASES = {case["case_id"]: case for case in CASES_DOC["cases"]}
NEGATIVES = {negative["negative_id"]: negative for negative in NEGATIVES_DOC["negatives"]}


@pytest.fixture(scope="module")
def worker() -> UntrustedExecutionWorker:
    candidate = UntrustedExecutionWorker()
    if not candidate.sandbox_available():
        pytest.skip(
            "OS sandbox (bwrap) is unavailable on this host; "
            "fail-closed blocked policy is covered by test_judge_supervisor.py"
        )
    return candidate


def test_certification_corpus_is_the_expected_shape() -> None:
    assert CASES_DOC["schema_version"] == "m1b.judge.certification.v0"
    assert CASES_DOC["synthetic"] is True
    assert CASES_DOC["evidence_class"] == "MOCK"
    assert len(CASES) == 14
    assert sum(len(case["tests"]) for case in CASES.values()) == 112
    assert all(case["expected_classification"] == "PASS" for case in CASES.values())
    assert len(NEGATIVES) == 7


# ---------------------------------------------------------------------------
# Reference solutions: 14/14 PASS, 112/112 hidden cases
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("case_id", sorted(CASES))
def test_reference_solution_passes_every_hidden_case(
    worker: UntrustedExecutionWorker, case_id: str
) -> None:
    case = CASES[case_id]
    supervisor = TrustedJudgeSupervisor(worker, trusted_fixture_only=True)
    verdict = supervisor.evaluate(
        case["reference_solution"],
        case["function_name"],
        case["tests"],
        timeout_s=CERT_TIMEOUT_S,
    )
    assert verdict.infra_error is False
    assert verdict.status == STATUS_PASS
    assert verdict.cases_passed == len(case["tests"])
    assert verdict.cases_total == len(case["tests"])
    assert verdict.score_ratio == 1.0


def test_reference_solutions_total_112_of_112_cases(
    worker: UntrustedExecutionWorker,
) -> None:
    supervisor = TrustedJudgeSupervisor(worker, trusted_fixture_only=True)
    passed = 0
    total = 0
    started = time.monotonic()
    for case in CASES.values():
        verdict = supervisor.evaluate(
            case["reference_solution"],
            case["function_name"],
            case["tests"],
            timeout_s=CERT_TIMEOUT_S,
        )
        assert verdict.status == STATUS_PASS, case["case_id"]
        passed += verdict.cases_passed
        total += verdict.cases_total
    elapsed = time.monotonic() - started
    assert (passed, total) == (112, 112)
    # Offline certification on the reference host measured ~4s; keep a generous
    # deterministic-budget guard rather than a fragile wall-clock assertion.
    assert elapsed < 120.0


# ---------------------------------------------------------------------------
# Synthetic negatives: classification matrix
# ---------------------------------------------------------------------------
def _score_negative(worker: UntrustedExecutionWorker, negative: dict[str, Any]):
    case = CASES[negative["case_id"]]
    timeout = TLE_TIMEOUT_S if negative["failure_mode"] == "infinite_loop" else CERT_TIMEOUT_S
    supervisor = TrustedJudgeSupervisor(
        worker, trusted_fixture_only=True, timeout_s=timeout
    )
    return supervisor.evaluate(
        negative["code"],
        case["function_name"],
        case["tests"],
        timeout_s=timeout,
    )


def test_negative_matrix_has_required_failure_modes() -> None:
    modes = {negative["failure_mode"] for negative in NEGATIVES.values()}
    assert modes == {
        "constant_return",
        "off_by_one",
        "edge_correct",
        "syntax_error",
        "runtime_exception",
        "missing_function",
        "infinite_loop",
    }


@pytest.mark.parametrize("negative_id", sorted(NEGATIVES))
def test_negative_classification(
    worker: UntrustedExecutionWorker, negative_id: str
) -> None:
    negative = NEGATIVES[negative_id]
    verdict = _score_negative(worker, negative)
    expected = negative["expected_classification"]
    assert verdict.infra_error is False
    if expected == "PASS":
        # edge-correct control submission: must actually pass, not be blocked.
        assert verdict.status == STATUS_PASS
        assert verdict.cases_passed == verdict.cases_total
    elif expected == "TLE":
        assert verdict.status == STATUS_TLE
        assert verdict.cases_passed < verdict.cases_total
    elif expected == "RE":
        assert verdict.status == STATUS_RE
        assert verdict.cases_passed == 0
    elif expected == "WA":
        assert verdict.status == STATUS_WA
        assert verdict.cases_passed < verdict.cases_total
    else:  # pragma: no cover - fixture schema is validated separately
        raise AssertionError(f"unexpected expected_classification: {expected!r}")


def test_negative_verdicts_do_not_echo_hidden_material(
    worker: UntrustedExecutionWorker,
) -> None:
    for negative in NEGATIVES.values():
        verdict = _score_negative(worker, negative)
        rendered = repr(verdict.to_dict())
        assert "expected" not in rendered.lower()
        assert "args" not in rendered.lower()
        assert isinstance(verdict.failure_codes, tuple)
        assert all(isinstance(code, str) and len(code) <= 64 for code in verdict.failure_codes)


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------
def test_identical_inputs_produce_identical_verdicts(
    worker: UntrustedExecutionWorker,
) -> None:
    case = CASES["cf_array_sum_even"]
    supervisor = TrustedJudgeSupervisor(worker, trusted_fixture_only=True)
    first = supervisor.evaluate(
        case["reference_solution"], case["function_name"], case["tests"], timeout_s=1.5
    )
    second = supervisor.evaluate(
        case["reference_solution"], case["function_name"], case["tests"], timeout_s=1.5
    )
    assert first == second
    assert first.to_dict() == second.to_dict()


def test_trusted_fixture_only_is_required_even_with_real_worker(
    worker: UntrustedExecutionWorker,
) -> None:
    supervisor = TrustedJudgeSupervisor(worker)  # default policy: blocked
    case = CASES["cf_array_sum_even"]
    verdict = supervisor.evaluate(
        case["reference_solution"], case["function_name"], case["tests"]
    )
    assert verdict.status in {
        "UNTRUSTED_CODE_EXECUTION_BLOCKED",
        STATUS_JUDGE_SANDBOX_UNAVAILABLE,
    }
    assert verdict.cases_passed == 0
    assert verdict.infra_error is True
