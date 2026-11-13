"""Offline paired orchestration. No live runtime or credential discovery exists."""
import hashlib
from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from autoteacher_m0.accounting import (BudgetGuard, BudgetLimits, conservative_input_bound,
                                     mock_prices, normalize_usage)
from autoteacher_m0.contracts import AgentRuntime, RunRecord, RunRequest
from autoteacher_m0.evaluation import DATASET_VERSION, EVALUATOR_VERSION, evaluate
from .fixtures import load_cases
from .mock import TeachingMockRuntime

STRATEGIES = {
    "teacher_v0": "Directly identify and explain the student's misconception; do not provide a complete solution.",
    "teacher_v1": "Diagnose the misconception; guide the student to explain or construct a counterexample; no complete solution.",
}
OUTPUT_SCHEMA = ('Return JSON strings: misconception, explanation, action, question. '
                 'For insufficient evidence ask for code, constraints and a failing input.')


def run_mock_pairs(*, fixture_path: Path | str | None = None,
                   runtime_factory: Callable[[], AgentRuntime] = TeachingMockRuntime,
                   grader: Callable | None = None,
                   experiment_id: str | None = None) -> dict:
    """Candidate sees ONLY RunRequest; contracts remain in the evaluator plane.

    Python object separation is NOT hostile-code isolation. Dynamic candidates
    require security's separate restricted containers without this source tree.
    """
    cases = load_cases(fixture_path)
    experiment = experiment_id or ("mock-" + str(uuid4()))
    guard = BudgetGuard(mock_prices(), BudgetLimits())
    runs = []
    seen_run_ids: set[str] = set()
    seen_session_ids: set[str] = set()
    for case in cases:
        for candidate_id, strategy in STRATEGIES.items():
            session_id = "pair-" + str(uuid4())
            prompt = strategy + "\n" + OUTPUT_SCHEMA + "\nStudent: " + case.student_input
            request = RunRequest(case.case_id, prompt, candidate_id, session_id,
                                 "mock", "deepseek-flash", "mock")
            reservation = guard.reserve(task_id=session_id, route_id="mock", model=request.model,
                                        input_tokens=conservative_input_bound(prompt), output_tokens=2048,
                                        max_cost_usd=case.max_cost_usd)
            try:
                runtime = runtime_factory()  # new instance AND session for each arm/case
                record = runtime.run(request)
                if (record.case_id, record.candidate_id, record.session_id, record.route_id) != (
                        request.case_id, candidate_id, session_id, "mock"):
                    raise ValueError("runtime returned mismatched identity")
                if record.metadata.get("mode") != "mock":
                    raise ValueError("offline experiment requires explicit Mock provenance")
                if record.run_id in seen_run_ids or record.session_id in seen_session_ids:
                    raise ValueError("paired executions must have independent run/session ids")
                usage = normalize_usage(record.input_tokens, record.output_tokens,
                                        reserved_input=reservation.input_tokens,
                                        reserved_output=reservation.output_tokens)
                accounting = guard.settle(reservation, usage, status=record.status)
            except Exception as exc:
                accounting = guard.fail(reservation)
                record = RunRecord(str(uuid4()), case.case_id, candidate_id, session_id,
                                   "mock", "", "ERROR", [], error_code="PROVIDER_ERROR",
                                   metadata={"mode": "mock", "error_type": type(exc).__name__})
            seen_run_ids.add(record.run_id)
            seen_session_ids.add(record.session_id)
            result = evaluate(case, record, grader=grader)
            runs.append({"record": asdict(record), "evaluation": asdict(result),
                         "split": case.split, "public_input": case.student_input,
                         "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                         "accounting": accounting, "billable_cost_usd": "0",
                         "cost_note": "synthetic accounting estimate; Mock has no API bill"})
    pairs = []
    for case in cases:
        arms = [entry for entry in runs if entry["record"]["case_id"] == case.case_id]
        scores = [entry["evaluation"]["score"] for entry in arms]
        comparable = all(entry["evaluation"]["status"] == "SCORED" for entry in arms)
        pairs.append({"case_id": case.case_id, "split": case.split,
                      "run_ids": [entry["record"]["run_id"] for entry in arms],
                      "teacher_v0_score": scores[0], "teacher_v1_score": scores[1],
                      "delta_v1_minus_v0": scores[1] - scores[0] if comparable else None,
                      "comparison_status": "COMPARABLE" if comparable else "INCOMPLETE"})
    return {"experiment_id": experiment, "mode": "mock", "provenance": "PUBLIC_FICTIONAL_MOCK",
            "dataset_version": DATASET_VERSION, "evaluator_version": EVALUATOR_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "provider": "mock", "model": "deepseek-flash", "route_id": "mock",
            "sampling": "fixed scripted output; not a model seed",
            "tool_source": "none; no tool calls asserted", "output_token_limit": 2048,
            "live_status": "BLOCKED: no human approval, credentials or model calls",
            "private_eval_status": "NOT_RUN: true private data must remain outside repository",
            "runtime_version": "public-teacher-mock-v1", "git_sha": "UNRECORDED",
            "sdk_version": "NOT_USED", "profile": "NOT_USED",
            "runs": runs, "pairs": pairs, "budget": guard.snapshot(),
            "price_snapshot": {"version": guard.prices.version, "source": guard.prices.source,
                               "mock": True},
            "limitations": ["Fixed public Mock outputs test infrastructure, not teaching quality.",
                            "Public simulated holdout is not hidden or private evaluation.",
                            "Deterministic rules require independent human semantic spot checks.",
                            "Candidate process isolation is provided separately by security, not Python objects.",
                            "Live SDK internal autonomous steps are not proven bounded; Live stays blocked."]}
