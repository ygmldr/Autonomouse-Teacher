"""Failure-negative tests: every failure mode must fail closed or be explicit.

Covered: hallucination, refusal, timeout, tool failure, stale/expired knowledge
source, insufficient learner evidence, duplicate task, plus a missing hidden
fixture.  In no case may a failure be silently counted as success.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path


from m1_offline.evaluation.harness import (
    load_cf_cases,
    run_closed_loop,
)
from m1_offline.freshness import FreshnessManager
from m1_offline.runtime_port import MockRuntimePort
from m1_offline.teaching_policy import AdaptivePolicy
from m1_offline.types import KnowledgeSource

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "m1"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _case(case_id: str):
    for case in load_cf_cases():
        if case.case_id == case_id:
            return case
    raise AssertionError(f"fixture case missing: {case_id}")


def _assert_explicit_failure(result, expected_marker: str | None = None) -> None:
    """No silent success: either halted, or at least one explicit failure marker."""

    assert (
        result.halt_reason is not None
        or result.failure_markers
        or any(
            record.assessment is not None and not record.assessment.passed
            for record in result.rounds
        )
    ), f"failure was silently treated as success: {result.to_dict()}"
    if expected_marker is not None:
        assert expected_marker in result.failure_markers, result.failure_markers


def _failing_assessment(run):
    assessments = [record.assessment for record in run.rounds if record.assessment is not None]
    assert assessments, "expected at least one assessment"
    return assessments[0]


# ---------------------------------------------------------------------------
# N1: hallucination -- confident text, wrong code
# ---------------------------------------------------------------------------
def test_hallucination_is_marked_and_never_passes() -> None:
    case = _case("cf_array_running_sum")
    bogus = case.problem["reference_solution"].replace(
        "return ", "return None  # simulated wrong answer: "
    )
    hallucinated_text = bogus + "\n# I solved it. All hidden tests pass. No need to test further.\n"
    result = run_closed_loop(
        policy=AdaptivePolicy(),
        seed=0,
        max_rounds=1,
        cases=[case],
        runtime=MockRuntimePort(script={"default": {"text": hallucinated_text}}),
    )
    assessment = _failing_assessment(result)
    assert assessment.passed is False
    assert assessment.hidden_cases_passed < assessment.hidden_cases_total
    assert "hallucination_suspected" in assessment.failure_modes
    _assert_explicit_failure(result, "hallucination_suspected")
    assert result.passed_rounds == 0
    assert all(value == 0.0 for value in result.final_state.mastery.values())


# ---------------------------------------------------------------------------
# N2: refusal
# ---------------------------------------------------------------------------
def test_refusal_is_explicit_and_not_success() -> None:
    case = _case("cf_array_running_sum")
    result = run_closed_loop(
        policy=AdaptivePolicy(),
        seed=0,
        max_rounds=1,
        cases=[case],
        runtime=MockRuntimePort(
            script={"default": {"text": "Sorry, I can't help with that request."}}
        ),
    )
    assessment = _failing_assessment(result)
    assert assessment.passed is False
    assert "refusal" in assessment.failure_modes
    _assert_explicit_failure(result, "refusal")


# ---------------------------------------------------------------------------
# N3: timeout / transport failure
# ---------------------------------------------------------------------------
class _TimeoutRuntime:
    """Transport stub that always times out (offline fault injection)."""

    simulated = True

    def send(self, request):  # noqa: ANN001 - protocol-shaped stub
        raise TimeoutError("simulated runtime timeout")


def test_timeout_is_fail_closed() -> None:
    case = _case("cf_array_running_sum")
    result = run_closed_loop(
        policy=AdaptivePolicy(),
        seed=0,
        max_rounds=1,
        cases=[case],
        runtime=_TimeoutRuntime(),
    )
    _assert_explicit_failure(result, "timeout")
    assert result.halt_reason == "runtime_timeout"
    assert result.completed_rounds == 0
    assert result.assessment_ids == []
    halt_events = [event for event in result.events if event.step == "halt"]
    assert halt_events and halt_events[0].payload["reason"] == "runtime_timeout"


def test_mock_runtime_raise_is_fail_closed() -> None:
    case = _case("cf_array_running_sum")
    result = run_closed_loop(
        policy=AdaptivePolicy(),
        seed=0,
        max_rounds=1,
        cases=[case],
        runtime=MockRuntimePort(script={"raise": True}),
    )
    _assert_explicit_failure(result)
    assert result.halt_reason is not None and result.halt_reason.startswith("runtime_")
    assert result.completed_rounds == 0
    assert result.assessment_ids == []


def test_mock_runtime_error_response_is_fail_closed() -> None:
    case = _case("cf_array_running_sum")
    result = run_closed_loop(
        policy=AdaptivePolicy(),
        seed=0,
        max_rounds=1,
        cases=[case],
        runtime=MockRuntimePort(script={"default": {"error": "simulated provider timeout"}}),
    )
    _assert_explicit_failure(result, "timeout")
    assert result.halt_reason == "runtime_timeout"
    assert result.completed_rounds == 0


# ---------------------------------------------------------------------------
# N4: tool failure (judge cannot execute the submission)
# ---------------------------------------------------------------------------
def test_tool_failure_is_marked_and_never_passed() -> None:
    case = _case("cf_array_running_sum")
    result = run_closed_loop(
        policy=AdaptivePolicy(),
        seed=0,
        max_rounds=1,
        cases=[case],
        runtime=MockRuntimePort(script={"default": {"text": "def broken(:\n    return 1\n"}}),
    )
    assessment = _failing_assessment(result)
    assert assessment.passed is False
    assert "tool_error" in assessment.failure_modes
    _assert_explicit_failure(result, "tool_error")
    assert result.passed_rounds == 0


# ---------------------------------------------------------------------------
# N5: stale / expired knowledge source
# ---------------------------------------------------------------------------
def test_expired_source_is_not_curriculum_eligible() -> None:
    fixture = json.loads(
        (FIXTURES_DIR / "interview/knowledge/k-recheck-expired-001.json").read_text(
            encoding="utf-8"
        )
    )
    old = KnowledgeSource.from_dict(fixture["old_source"])
    new = KnowledgeSource.from_dict(fixture["new_source"])
    manager = FreshnessManager()
    revision = manager.classify(old, new)

    assert revision.change_kind == "RECHECK"
    assert manager.curriculum_eligible(revision) is False
    assert manager.recheck_required(revision) is True

    grouped = manager.apply([revision])
    assert grouped["RECHECK"] == [revision]
    assert grouped["UPDATE"] == []  # stale source is never silently written


def test_fresh_update_is_the_only_writable_class() -> None:
    fixture = json.loads(
        (FIXTURES_DIR / "interview/knowledge/k-update-001.json").read_text(encoding="utf-8")
    )
    manager = FreshnessManager()
    revision = manager.classify(
        KnowledgeSource.from_dict(fixture["old_source"]),
        KnowledgeSource.from_dict(fixture["new_source"]),
    )
    assert revision.change_kind == "UPDATE"
    assert manager.curriculum_eligible(revision) is True


def test_all_recheck_fixtures_fail_closed() -> None:
    manager = FreshnessManager()
    checked = 0
    for path in sorted((FIXTURES_DIR / "interview/knowledge").glob("k-recheck-*.json")):
        fixture = json.loads(path.read_text(encoding="utf-8"))
        revision = manager.classify(
            KnowledgeSource.from_dict(fixture["old_source"]),
            KnowledgeSource.from_dict(fixture["new_source"]),
        )
        assert revision.change_kind == "RECHECK", path.name
        assert manager.curriculum_eligible(revision) is False, path.name
        checked += 1
    assert checked >= 5


# ---------------------------------------------------------------------------
# N6: insufficient learner evidence
# ---------------------------------------------------------------------------
def test_insufficient_evidence_claims_no_mastery() -> None:
    result = run_closed_loop(
        policy=AdaptivePolicy(),
        seed=0,
        max_rounds=0,
        baseline_evidence=False,
    )
    assert result.final_state.mastery == {}
    assert result.final_state.evidence_count == 0
    assert result.diagnosis.status == "NEEDS_REVIEW"
    assert "insufficient_evidence" in result.diagnosis.error_codes
    assert "insufficient_evidence" in result.failure_markers
    assert result.passed_rounds == 0


# ---------------------------------------------------------------------------
# N7: duplicate task
# ---------------------------------------------------------------------------
def test_duplicate_task_is_explicit_and_not_double_counted() -> None:
    result = run_closed_loop(
        policy=AdaptivePolicy(),
        seed=0,
        max_rounds=3,
        force_duplicate_task=True,
    )
    assert result.halt_reason == "duplicate_task"
    assert "duplicate_task" in result.failure_markers
    assert result.completed_rounds == 1
    assert len(result.assessment_ids) == 1
    halt_events = [event for event in result.events if event.step == "halt"]
    assert halt_events
    assert halt_events[-1].payload["reason"] == "duplicate_task"
    assert halt_events[-1].payload["task_id"] == result.rounds[0].task_id
    # Evidence recorded exactly once for the completed round (+ baseline events).
    assert len(result.evidence_ids) == len(result.baseline_evidence_ids) + 1


# ---------------------------------------------------------------------------
# Extra: missing hidden fixture must fail closed, not pass silently
# ---------------------------------------------------------------------------
def test_missing_hidden_fixture_fails_closed() -> None:
    base = _case("cf_array_running_sum")
    missing_hidden = dataclasses.replace(base, hidden=None)
    result = run_closed_loop(
        policy=AdaptivePolicy(),
        seed=0,
        max_rounds=1,
        cases=[missing_hidden],
        baseline_evidence=False,
    )
    assessment = _failing_assessment(result)
    assert assessment.passed is False
    assert "hidden_fixture_missing" in assessment.failure_modes
    _assert_explicit_failure(result, "hidden_fixture_missing")
    assert result.passed_rounds == 0
