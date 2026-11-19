"""Diagnostic engine tests: known error codes, ambiguity -> UNKNOWN/NEEDS_REVIEW."""

from __future__ import annotations

import pytest

from m1_offline.diagnostics import KNOWN_ERROR_CODES, DiagnosticEngine
from m1_offline.types import DiagnosticResult, LearnerState


def _state(error_counts: dict[str, int] | None = None, evidence_count: int = 2) -> LearnerState:
    return LearnerState(
        learner_id="learner-001",
        mastery={},
        error_counts=error_counts or {},
        evidence_count=evidence_count,
    )


def _task(**overrides) -> dict:
    task = {"task_id": "task-001", "skill_ids": ["two-sum"]}
    task.update(overrides)
    return task


def test_engine_returns_contract_record():
    result = DiagnosticEngine().diagnose(_task(), {"output": 42}, _state())
    assert isinstance(result, DiagnosticResult)
    assert result.task_id == "task-001"
    assert result.diagnosis_id.startswith("diag_")
    assert result.explanation
    assert result.status in {"RESOLVED", "UNKNOWN", "NEEDS_REVIEW"}
    assert DiagnosticResult.from_dict(result.to_dict()) == result


def test_off_by_one_detected_from_numeric_output():
    result = DiagnosticEngine().diagnose(
        _task(expected_output=42), {"output": 41}, _state()
    )
    assert result.status == "RESOLVED"
    assert result.error_codes == ["off_by_one"]
    assert "exactly 1" in result.explanation
    assert result.confidence >= 0.8


def test_off_by_one_detected_from_failing_case():
    result = DiagnosticEngine().diagnose(
        _task(),
        {
            "case_results": [
                {"case_id": "c1", "passed": True},
                {"case_id": "c2", "passed": False, "expected": 10, "actual": 11},
            ]
        },
        _state(),
    )
    assert result.status == "RESOLVED"
    assert "off_by_one" in result.error_codes


def test_wrong_complexity_detected():
    result = DiagnosticEngine().diagnose(
        _task(expected_complexity="O(n)"),
        {"passed": False, "complexity": "O(n^2)"},
        _state(),
    )
    assert result.status == "RESOLVED"
    assert result.error_codes == ["wrong_complexity"]


def test_wrong_complexity_not_flagged_when_better_than_required():
    result = DiagnosticEngine().diagnose(
        _task(expected_complexity="O(n^2)"),
        {"passed": False, "complexity": "O(n)"},
        _state(),
    )
    assert "wrong_complexity" not in result.error_codes


def test_wrong_data_structure_detected():
    result = DiagnosticEngine().diagnose(
        _task(expected_data_structure="dict"),
        {"passed": False, "data_structure": "list"},
        _state(),
    )
    assert result.status == "RESOLVED"
    assert result.error_codes == ["wrong_data_structure"]


def test_edge_case_detected_when_only_edge_cases_fail():
    result = DiagnosticEngine().diagnose(
        _task(edge_case_ids=["c-empty"]),
        {
            "passed": False,
            "case_results": [
                {"case_id": "c1", "passed": True},
                {"case_id": "c-empty", "passed": False},
            ],
        },
        _state(),
    )
    assert result.status == "RESOLVED"
    assert "edge_case" in result.error_codes


def test_conceptual_gap_requires_error_history():
    # Same broad failure without history: no conceptual_gap classification.
    without_history = DiagnosticEngine().diagnose(
        _task(),
        {"passed": False, "case_results": [{"case_id": "c1", "passed": False}]},
        _state(error_counts={}),
    )
    assert "conceptual_gap" not in without_history.error_codes

    with_history = DiagnosticEngine().diagnose(
        _task(),
        {"passed": False, "case_results": [{"case_id": "c1", "passed": False}]},
        _state(error_counts={"off_by_one": 2}),
    )
    assert "conceptual_gap" in with_history.error_codes
    assert with_history.status == "RESOLVED"


def test_explicit_known_error_code_is_respected():
    result = DiagnosticEngine().diagnose(
        _task(), {"error_codes": ["off_by_one"]}, _state()
    )
    assert result.status == "RESOLVED"
    assert result.error_codes == ["off_by_one"]
    assert "explicitly supplied" in result.explanation


def test_all_cases_passed_is_resolved_without_error_codes():
    result = DiagnosticEngine().diagnose(
        _task(),
        {
            "passed": True,
            "case_results": [
                {"case_id": "c1", "passed": True},
                {"case_id": "c2", "passed": True},
            ],
        },
        _state(),
    )
    assert result.status == "RESOLVED"
    assert result.error_codes == []


def test_unknown_error_code_needs_review():
    result = DiagnosticEngine().diagnose(
        _task(), {"error_codes": ["mystery_failure"]}, _state()
    )
    assert result.status == "NEEDS_REVIEW"
    assert "mystery_failure" in result.error_codes
    assert "unclassified" in result.explanation


def test_no_signals_is_unknown():
    result = DiagnosticEngine().diagnose(_task(), {}, _state(evidence_count=0))
    assert result.status == "UNKNOWN"
    assert result.error_codes == []
    assert result.confidence <= 0.3


def test_unclassified_failure_needs_review():
    result = DiagnosticEngine().diagnose(
        _task(),
        {"case_results": [{"case_id": "c1", "passed": False}]},
        _state(error_counts={}),
    )
    assert result.status == "NEEDS_REVIEW"
    assert "no rule classified" in result.explanation


def test_conflicting_passed_flag_needs_review():
    result = DiagnosticEngine().diagnose(
        _task(),
        {
            "passed": True,
            "case_results": [{"case_id": "c1", "passed": False}],
        },
        _state(),
    )
    assert result.status == "NEEDS_REVIEW"
    assert "conflict" in result.explanation


def test_error_message_hint_mapping():
    result = DiagnosticEngine().diagnose(
        _task(), {"passed": False, "error_message": "IndexError: index out of range"}, _state()
    )
    assert "off_by_one" in result.error_codes
    result = DiagnosticEngine().diagnose(
        _task(), {"passed": False, "error_message": "Time limit exceeded"}, _state()
    )
    assert "wrong_complexity" in result.error_codes


def test_diagnosis_is_deterministic():
    engine = DiagnosticEngine()
    task = _task(expected_output=5)
    submission = {"output": 6, "evidence_refs": ["ev-1", "ev-1"]}
    first = engine.diagnose(task, submission, _state())
    second = engine.diagnose(task, submission, _state())
    assert first.to_dict() == second.to_dict()


def test_evidence_refs_are_preserved_and_deduplicated():
    result = DiagnosticEngine().diagnose(
        _task(), {"output": 41, "evidence_refs": ["ev-1", "ev-1", "ev-2"]}, _state()
    )
    assert result.evidence_refs == ["ev-1", "ev-2"]


def test_invalid_inputs_fail_closed():
    engine = DiagnosticEngine()
    with pytest.raises(TypeError):
        engine.diagnose("task", {}, _state())  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        engine.diagnose(_task(), [], _state())  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        engine.diagnose(_task(), {}, {"learner_id": "l"})  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        engine.diagnose({"skill_ids": ["two-sum"]}, {}, _state())
    with pytest.raises(ValueError):
        engine.diagnose(_task(), {"error_codes": "off_by_one"}, _state())
    with pytest.raises(ValueError):
        engine.diagnose(_task(), {"passed": "yes"}, _state())


def test_known_code_vocabulary_is_stable():
    assert KNOWN_ERROR_CODES == (
        "off_by_one",
        "wrong_complexity",
        "wrong_data_structure",
        "edge_case",
        "conceptual_gap",
    )
