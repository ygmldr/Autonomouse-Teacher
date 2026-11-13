"""Fixed public Mock responses, NOT a language model or teaching-effect evidence.

This candidate stub imports neither fixtures nor evaluator rules. Its catalog is
intentionally public and deterministic; agreement with rules tests plumbing only.
"""
import json
from uuid import uuid4
from autoteacher_m0.contracts import RunRecord, RunRequest

# Public scripted candidate behavior, maintained independently of grader loading.
RESPONSES = {
    "mono-001": ("assumes_monotonicity", "Binary search requires a monotone feasibility predicate."),
    "mono-002": ("unsorted_binary_search", "Discarding half is justified only when ordering excludes that half."),
    "mono-003": ("multiple_transitions", "Multiple true-false transitions invalidate the binary search invariant."),
    "mono-004": ("reversed_capacity_feasibility", "Increasing capacity cannot invalidate an already feasible loading."),
    "mono-005": ("samples_prove_monotonicity", "Two samples cannot prove monotonicity for every candidate value."),
    "bound-001": ("half_open_last_excluded", "A half-open upper bound excludes r, so covering index n-1 requires r=n."),
    "bound-002": ("nonshrinking_interval", "Setting l=mid when mid=l leaves the interval unchanged."),
    "bound-003": ("missing_no_solution_sentinel", "An all-false predicate requires a no-solution sentinel rather than a valid index."),
    "bound-004": ("lower_bound_any_duplicate", "Lower-bound must return the first position whose value is at least the target."),
    "bound-005": ("empty_array_access", "An empty array has no valid index, so length must be checked before access."),
    "complex-001": ("ignores_predicate_cost", "Logarithmic checks times a linear check cost gives O(n log n)."),
    "complex-002": ("ignores_repeated_sorting", "Sorting inside every query multiplies the sorting cost by the query count."),
    "complex-003": ("nested_always_quadratic", "Doubling the inner variable gives logarithmic iterations, so n outer iterations cost O(n log n)."),
    "complex-004": ("missing_predicate_prerequisite", "A predicate maps each candidate to true or false and defines what the search preserves."),
    "code-001": ("midpoint_addition_overflow", "l+r can overflow before division even when the midpoint fits."),
    "code-002": ("late_widening", "Multiplication occurs in the operand type before assignment to a wider destination."),
    "code-003": ("float_midpoint_index", "Python / produces a float whereas array indexing requires an integer."),
    "code-004": ("stateful_feasibility", "Retaining mutable state can change the answer for the same candidate and breaks a stable predicate."),
    "unclear-001": ("insufficient_evidence", "Without code and a failing input, the faulty line cannot be determined."),
    "unclear-002": ("insufficient_evidence", "A timeout alone does not establish overflow; constraints and code are needed."),
}


class TeachingMockRuntime:
    """Each instance accepts one fresh session only; no resume/history sharing."""
    def __init__(self) -> None:
        self.used = False

    def run(self, request: RunRequest) -> RunRecord:
        if self.used:
            raise RuntimeError("paired Mock runtime instances are one-session only")
        self.used = True
        if request.route_id != "mock" or request.model != "deepseek-flash":
            raise ValueError("Mock refuses any real route/model change")
        if request.candidate_id not in {"teacher_v0", "teacher_v1"}:
            raise ValueError("unknown scripted strategy")
        misconception, explanation = RESPONSES[request.case_id]
        unclear = request.case_id.startswith("unclear-")
        action = "ask_clarification" if unclear else ("explain" if request.candidate_id == "teacher_v0" else "ask_counterexample")
        question = ("Can you share the code, constraints and one failing input?" if unclear
                    else "Can you construct a small counterexample and explain what fails?")
        response = {"misconception": misconception, "explanation": explanation,
                    "action": action, "question": question if action != "explain" else ""}
        text = json.dumps(response, sort_keys=True)
        return RunRecord(str(uuid4()), request.case_id, request.candidate_id, request.session_id,
                         request.route_id, text, "SUCCESS",
                         [{"type": "mock_response", "sequence": 0,
                           "data": {"mode": "mock", "script_version": "public-teacher-mock-v1"}}],
                         len(request.prompt.encode("utf-8")), len(text.encode("utf-8")),
                         0.0, metadata={"mode": "mock", "provider": "mock", "model": request.model,
                                        "sampling": "fixed scripted output", "billable_cost_usd": 0.0})

    def resume(self, session_id: str, prompt: str) -> RunRecord:
        raise RuntimeError("pairing requires fresh sessions; resume is forbidden")
