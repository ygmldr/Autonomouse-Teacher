"""Independent deterministic grader for a narrow, auditable Mock response schema.

The expected label alone or a bag of concept keywords cannot earn a full score:
relational explanations and actions are checked separately. Rules are bounded,
not a substitute for blinded human semantic review or real learning measurement.
"""
import json
import re
from collections.abc import Callable
from autoteacher_m0.contracts import RunRecord
from .contracts import EVALUATOR_VERSION, EvalContract, EvaluationResult
from .leakage_checks import check_solution_leakage


def _grade(contract: EvalContract, record: RunRecord) -> EvaluationResult:
    if contract.evaluator_version != EVALUATOR_VERSION:
        raise ValueError("unsupported evaluator version")
    if record.case_id != contract.case_id:
        raise ValueError("run/contract case mismatch")
    if record.status != "SUCCESS":
        return EvaluationResult("RUN_ERROR", None, EVALUATOR_VERSION,
                                reasons=(record.error_code or record.status,))
    leak = check_solution_leakage(record.text)
    try:
        response = json.loads(record.text)
    except (json.JSONDecodeError, TypeError):
        return EvaluationResult("NEEDS_REVIEW", None, EVALUATOR_VERSION,
                                reasons=("response is outside audited JSON schema", leak.reason))
    if not isinstance(response, dict) or any(not isinstance(response.get(key), str)
                                           for key in ("misconception", "explanation", "action", "question")):
        return EvaluationResult("NEEDS_REVIEW", None, EVALUATOR_VERSION,
                                reasons=("response schema needs human review",))
    explanation = response["explanation"].strip().lower()
    checks = {
        "diagnosis": response["misconception"] in contract.expected_misconceptions,
        # Whole relational clauses: mere occurrences of the constituent words fail.
        "concept_relations": all(re.search(pattern, explanation, re.I) is not None
                                 for pattern in contract.relation_patterns),
        "required_action": response["action"] in contract.required_actions,
        "no_complete_solution": leak.status != "LEAK",
    }
    if response["action"] == "ask_clarification":
        checks["clarification_question"] = (len(response["question"].strip()) >= 12
                                            and "?" in response["question"])
    if leak.status == "NEEDS_REVIEW":
        return EvaluationResult("NEEDS_REVIEW", None, EVALUATOR_VERSION, checks, (leak.reason,))
    # Negation/quotation around otherwise correct clauses is unsafe to auto-grade.
    if re.search(r"\b(?:not true that|false that|wrong that|ignore the rule|do not need|never need)\b", explanation):
        return EvaluationResult("NEEDS_REVIEW", None, EVALUATOR_VERSION, checks,
                                ("possible negation or contradiction requires human review",))
    if leak.status == "LEAK" and "complete_solution_code" in contract.forbidden:
        return EvaluationResult("SCORED", 0.0, EVALUATOR_VERSION, checks, (leak.reason,))
    score = sum(checks.values()) / len(checks)
    return EvaluationResult("SCORED", score, EVALUATOR_VERSION, checks,
                            tuple(name for name, passed in checks.items() if not passed))


def evaluate(contract: EvalContract, record: RunRecord, *,
             grader: Callable[[EvalContract, RunRecord], EvaluationResult] | None = None) -> EvaluationResult:
    """Faulty evaluators are EVAL_ERROR with score=None, never a disguised zero."""
    try:
        result = (grader or _grade)(contract, record)
        if not isinstance(result, EvaluationResult):
            raise TypeError("grader returned invalid result")
        if result.status not in {"SCORED", "NEEDS_REVIEW", "EVAL_ERROR", "RUN_ERROR"}:
            raise ValueError("grader returned unknown status")
        if result.status == "SCORED":
            if result.score is None or not 0 <= result.score <= 1:
                raise ValueError("invalid score")
        elif result.score is not None:
            raise ValueError("non-scored result must not carry a numeric score")
        return result
    except Exception as exc:
        # Do not expose arbitrary exception payloads (may contain secrets/input).
        return EvaluationResult("EVAL_ERROR", None, EVALUATOR_VERSION,
                                reasons=("grader exception: " + type(exc).__name__,))
