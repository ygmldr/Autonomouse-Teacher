"""teacher_v0 vs teacher_v1 comparison tests.

Checks the protocol is reproducible (same fixed cases/seeds => same digest),
records per-dimension mean/variance and failure cases, scores blindly, and that
the conclusion text never overclaims real teaching effectiveness.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from m1_offline.evaluation.compare import (
    DEFAULT_MASTERY_THRESHOLD,
    DEFAULT_MAX_ROUNDS,
    DEFAULT_SEEDS,
    DIMENSIONS,
    DISCLAIMER,
    FORBIDDEN_OVERCLAIM_PHRASES,
    SCORER_MODULE_ID,
    assert_no_overclaim,
    run_comparison,
)
from m1_offline.evaluation.harness import load_cf_cases

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE_REPORT = REPO_ROOT / "docs/m1/reports/eval_baseline_v1.json"


@pytest.fixture(scope="module")
def comparison():
    """One full fixed-case/fixed-seed comparison (module scope: judge is a subprocess)."""

    return run_comparison()


def test_default_protocol_uses_fixed_cases_and_seeds(comparison) -> None:
    payload = comparison.to_dict()
    assert payload["seeds"] == list(DEFAULT_SEEDS)
    assert payload["max_rounds"] == DEFAULT_MAX_ROUNDS
    assert payload["case_catalog_size"] >= 12
    assert len(payload["cases_assessed"]) >= 12
    assert payload["total_rounds_measured"] == 2 * len(DEFAULT_SEEDS) * DEFAULT_MAX_ROUNDS
    assert payload["protocol"]["mastery_threshold"] == DEFAULT_MASTERY_THRESHOLD
    assert payload["protocol"]["blind_rubric"] is True
    assert payload["protocol"]["scorer_module"] == SCORER_MODULE_ID


def test_each_policy_ran_the_same_fixed_cases(comparison) -> None:
    payload = comparison.to_dict()
    v0_runs = payload["policies"]["teacher_v0"]["runs"]
    v1_runs = payload["policies"]["teacher_v1"]["runs"]
    assert len(v0_runs) == len(DEFAULT_SEEDS)
    assert len(v1_runs) == len(DEFAULT_SEEDS)
    # Same trajectory ids certified independently per policy run.
    assert [run["trajectory_id"] for run in v0_runs] == [run["trajectory_id"] for run in v1_runs]


def test_variance_is_recorded_per_dimension(comparison) -> None:
    payload = comparison.to_dict()
    for policy in ("teacher_v0", "teacher_v1"):
        statistics = payload["policies"][policy]["statistics"]
        for dimension in DIMENSIONS:
            stats = statistics[dimension]
            assert stats["n"] == len(DEFAULT_SEEDS)
            assert stats["variance"] >= 0.0
            assert math.isclose(stats["stdev"] ** 2, stats["variance"], rel_tol=1e-6, abs_tol=1e-6)
            assert len(stats["values"]) == stats["n"]
            for value in stats["values"]:
                assert 0.0 <= value <= 1.0
            # Mean must be the mean of the recorded values.
            recorded_mean = sum(stats["values"]) / len(stats["values"])
            assert math.isclose(stats["mean"], recorded_mean, rel_tol=1e-6, abs_tol=1e-6)


def test_failure_cases_exist_and_are_attributed(comparison) -> None:
    payload = comparison.to_dict()
    assert payload["failure_case_count"] >= 1
    seen: set[tuple[str, int, int]] = set()
    for failure in payload["failure_cases"]:
        assert failure["policy"] in {"teacher_v0", "teacher_v1"}
        assert failure["scorer_id"] == "independent_cf_judge_v0"
        assert failure["failure_modes"]
        assert failure["hidden_cases_passed"] <= failure["hidden_cases_total"]
        key = (failure["policy"], failure["seed"], failure["round"])
        assert key not in seen
        seen.add(key)


def test_delta_matches_recorded_means(comparison) -> None:
    payload = comparison.to_dict()
    delta = payload["delta_v1_minus_v0"]
    for dimension in DIMENSIONS:
        v0_mean = payload["policies"]["teacher_v0"]["statistics"][dimension]["mean"]
        v1_mean = payload["policies"]["teacher_v1"]["statistics"][dimension]["mean"]
        assert math.isclose(delta[dimension], v1_mean - v0_mean, rel_tol=1e-6, abs_tol=1e-6)


def test_comparison_is_reproducible(comparison) -> None:
    repeated = run_comparison()
    assert repeated.run_digest == comparison.run_digest
    assert repeated.to_dict() == comparison.to_dict()
    assert repeated.to_markdown() == comparison.to_markdown()


def test_blueprint_conclusion_is_bounded(comparison) -> None:
    conclusion = comparison.conclusion()
    lowered = conclusion.casefold()
    assert "not real teaching effect" in lowered
    assert "no significance" in lowered
    assert "synthetic simulation" in lowered
    for phrase in FORBIDDEN_OVERCLAIM_PHRASES:
        assert phrase.casefold() not in lowered, phrase
    markdown = comparison.to_markdown()
    assert "not real teaching effect" in markdown.casefold()
    assert DISCLAIMER.casefold() in markdown.casefold()
    assert comparison.to_dict()["disclaimer"] == DISCLAIMER


def test_blind_rubric_scores_are_used_for_both_policies(comparison) -> None:
    payload = comparison.to_dict()
    for policy in ("teacher_v0", "teacher_v1"):
        for run in payload["policies"][policy]["runs"]:
            assert set(run["scores"]) == set(DIMENSIONS)
            for value in run["scores"].values():
                assert 0.0 <= value <= 1.0
            assert run["trace_digest"]
    # Scores must come from the blind scorer, not from teacher self-report.
    assert payload["protocol"]["teacher_self_report_used_as_truth"] is False
    assert payload["protocol"]["scorer_sees_policy_identity"] is False


def test_comparison_output_is_synthetic_and_hidden_is_not_embedded(comparison) -> None:
    payload_text = json_dumps(comparison.to_dict())
    markdown = comparison.to_markdown()
    assert "offline synthetic simulation" in payload_text
    # No hidden expected test arrays may be embedded in the comparison output.
    assert "reference_solution" not in payload_text
    assert "hidden_cases_total" in payload_text
    assert "not real teaching effect" in markdown.casefold()


def test_comparison_catalog_comes_from_synthetic_fixtures(comparison) -> None:
    cases = load_cf_cases()
    assert len(cases) == comparison.case_catalog_size
    assert all(case.hidden is not None for case in cases)
    assert all(case.problem.get("synthetic") is True for case in cases)
    assert all(case.problem.get("license") == "CC0-1.0" for case in cases)


def test_overclaim_guard_raises() -> None:
    with pytest.raises(AssertionError):
        assert_no_overclaim("proven statistically significant real teaching effect")
    assert_no_overclaim(DISCLAIMER)


# json.dumps with a helper keeps the assertion concise and deterministic.
def json_dumps(value) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def test_persisted_report_contains_comparison_failure_cases(comparison) -> None:
    """P1-1: the artifact must persist the real per-failure list, not just aggregates."""

    assert BASELINE_REPORT.is_file(), "eval_baseline_v1.json artifact is required"
    artifact = json.loads(BASELINE_REPORT.read_text(encoding="utf-8"))
    assert "comparison" in artifact, sorted(artifact)
    section = artifact["comparison"]

    assert section["run_digest"] == comparison.run_digest
    failures = section["failure_cases"]
    assert isinstance(failures, list)
    assert len(failures) == section["failure_case_count"]
    assert section["failure_case_count"] == comparison.to_dict()["failure_case_count"]
    assert len(failures) >= 1

    required = {"policy", "seed", "round", "case_id", "scorer_id", "failure_modes"}
    for failure in failures:
        assert required <= set(failure), failure
        assert failure["policy"] in {"teacher_v0", "teacher_v1"}
        assert failure["scorer_id"] == "independent_cf_judge_v0"
        assert failure["failure_modes"]

    assert set(section["statistics"]) == {"teacher_v0", "teacher_v1"}
    for policy in ("teacher_v0", "teacher_v1"):
        for dimension in DIMENSIONS:
            assert "mean" in section["statistics"][policy][dimension]
            assert "variance" in section["statistics"][policy][dimension]
    assert "not real teaching effect" in section["disclaimer"].casefold()
