"""Evaluator-owned contracts. Never pass these objects/labels to a candidate.

All bundled fixtures are PUBLIC MOCK data, including simulated holdout cases.
A real private set must live outside this repository and candidate mounts.
"""
from dataclasses import dataclass, field
from typing import Any

EVALUATOR_VERSION = "m0-eval-v1"
DATASET_VERSION = "public-mock-v1"


@dataclass(frozen=True)
class EvalContract:
    case_id: str
    split: str
    category: str
    student_input: str
    expected_concepts: tuple[str, ...]
    expected_misconceptions: tuple[str, ...]
    relation_patterns: tuple[str, ...]
    required_actions: tuple[str, ...]
    forbidden: tuple[str, ...]
    max_cost_usd: float = 0.10
    evaluator_version: str = EVALUATOR_VERSION
    provenance: str = "PUBLIC_FICTIONAL_MOCK"

    def __post_init__(self) -> None:
        if self.split not in {"development", "simulated_holdout"}:
            raise ValueError("bundled cases are public mock only")
        if self.provenance != "PUBLIC_FICTIONAL_MOCK":
            raise ValueError("public fixture cannot claim private provenance")
        if not self.case_id or not self.student_input or not self.relation_patterns:
            raise ValueError("case id, public input and relational grading rules required")
        if not self.expected_misconceptions or not self.required_actions:
            raise ValueError("diagnosis and action contract required")
        if not 0 < self.max_cost_usd <= 0.20:
            raise ValueError("invalid case budget")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "EvalContract":
        copied = dict(value)
        for name in ("expected_concepts", "expected_misconceptions", "relation_patterns",
                     "required_actions", "forbidden"):
            copied[name] = tuple(copied[name])
        return cls(**copied)


@dataclass(frozen=True)
class EvaluationResult:
    status: str  # SCORED / NEEDS_REVIEW / EVAL_ERROR / RUN_ERROR
    score: float | None
    evaluator_version: str
    checks: dict[str, bool] = field(default_factory=dict)
    reasons: tuple[str, ...] = ()
