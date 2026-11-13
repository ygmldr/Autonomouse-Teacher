"""Evaluator-only package; not part of a candidate's public input."""
from .contracts import DATASET_VERSION, EVALUATOR_VERSION, EvalContract, EvaluationResult
from .graders import evaluate

__all__ = ["DATASET_VERSION", "EVALUATOR_VERSION", "EvalContract", "EvaluationResult", "evaluate"]
