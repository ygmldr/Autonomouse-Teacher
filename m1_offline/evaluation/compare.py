"""teacher_v0 vs teacher_v1 offline comparison protocol (M1 evaluation).

Both policies run the same synthetic case catalog, the same simulated learner
and the same seeds through :mod:`m1_offline.evaluation.harness`.  Scoring is
**blind**: the rubric only receives an anonymised trajectory (case ids, action
kinds, hint levels, independent assessment outcomes).  Policy names never enter
the rubric, and no teacher self-report is used as ground truth.

The output is explicitly bounded: it is an **offline synthetic simulation; not
real teaching effect**, and the comparison makes no significance or real-world
effect claim whatsoever.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from typing import Any, Sequence

from m1_offline.cf.judge import CFJudge
from m1_offline.evaluation.harness import (
    CFCase,
    LoopResult,
    load_cf_cases,
    run_closed_loop,
    trace_digest,
)
from m1_offline.teaching_policy import AdaptivePolicy, FixedPolicy, TeachingPolicy

__all__ = [
    "DISCLAIMER",
    "DIMENSIONS",
    "SCORER_MODULE_ID",
    "BlindRound",
    "BlindTrajectory",
    "PolicyComparison",
    "ComparisonResult",
    "blind_score",
    "run_comparison",
    "build_blind_trajectory",
    "assert_no_overclaim",
]

#: Hard textual boundary for every comparison output.
DISCLAIMER = (
    "offline synthetic simulation; not real teaching effect. "
    "These numbers describe a deterministic local simulator over synthetic "
    "fixtures and must not be extrapolated to real learners, real models or "
    "real teaching outcomes."
)

#: Blind rubric identity (independent of the teacher).
SCORER_MODULE_ID = "blind_rubric_v0"

#: Scoring dimensions, frozen before any run.
DIMENSIONS = (
    "correctness",
    "rounds_to_first_success",
    "hint_efficiency",
    "independence",
)

#: Phrases that would overclaim; comparison text must not contain them.
FORBIDDEN_OVERCLAIM_PHRASES = (
    "proven",
    "proof that",
    "statistically significant",
    "真实提升",
    "显著提升",
    "证明有效",
    "真实教学效果提升",
)

#: Synthetic intervention weight per teacher action kind (0 = no intervention,
#: 1 = full solution).  Used only for the local blind rubric.
INTERVENTION_WEIGHT: dict[str, float] = {
    "LIGHT_HINT": 0.25,
    "INVARIANT_HINT": 0.50,
    "STRUCTURE_HINT": 0.75,
    "FULL_SOLUTION": 1.00,
    "SOCRATIC_QUESTION": 0.40,
    "EXPLAIN": 0.50,
    "REVIEW": 0.30,
    "PRACTICE": 0.30,
    "ASK_CLARIFICATION": 0.25,
}

#: A pass is "independent" when it happens with low teacher intervention.
INDEPENDENT_INTERVENTION_CEILING = 0.50

DEFAULT_SEEDS: tuple[int, ...] = (0, 1, 2)
DEFAULT_MAX_ROUNDS = 12
DEFAULT_MASTERY_THRESHOLD = 1.01  # frozen: comparison measures fixed rounds, no early stop


# ---------------------------------------------------------------------------
# Blind views
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class BlindRound:
    """One anonymised round visible to the blind rubric (no policy identity)."""

    round_index: int
    case_id: str
    action_kind: str
    action_hint_level: int | None
    assessment_passed: bool
    assessment_score: float
    hidden_cases_passed: int
    hidden_cases_total: int


@dataclass(frozen=True)
class BlindTrajectory:
    """Anonymised trajectory: only outcomes + action shape, never a policy name."""

    trajectory_id: str
    rounds: tuple[BlindRound, ...]

    @property
    def round_count(self) -> int:
        return len(self.rounds)


def build_blind_trajectory(loop_result: LoopResult) -> BlindTrajectory:
    """Strip policy identity and teacher prose from a loop result."""

    rounds: list[BlindRound] = []
    for record in loop_result.rounds:
        assessment = record.assessment
        if assessment is None:
            continue
        rounds.append(
            BlindRound(
                round_index=record.round,
                case_id=record.task_id,
                action_kind=record.action.kind,
                action_hint_level=record.action.hint_level,
                assessment_passed=bool(assessment.passed),
                assessment_score=float(assessment.score),
                hidden_cases_passed=int(assessment.hidden_cases_passed),
                hidden_cases_total=int(assessment.hidden_cases_total),
            )
        )
    digest = hashlib.sha256(
        "|".join(f"{round.case_id}:{round.round_index}" for round in rounds).encode("utf-8")
    ).hexdigest()
    return BlindTrajectory(trajectory_id=f"traj_{digest[:16]}", rounds=tuple(rounds))


# ---------------------------------------------------------------------------
# Blind rubric (independent scorer; must not receive policy metadata)
# ---------------------------------------------------------------------------
def blind_score(trajectory: BlindTrajectory) -> dict[str, float]:
    """Score one anonymised trajectory on the frozen four dimensions.

    Deliberately independent of the teacher: only assessed outcomes, the number
    of rounds and the *intervention weight* of the emitted action are used.
    No teacher text, no self-report, no policy name.
    """

    if not isinstance(trajectory, BlindTrajectory):
        raise TypeError(f"blind_score expects BlindTrajectory, got {type(trajectory).__name__}")
    rounds = trajectory.rounds
    if not rounds:
        return {dimension: 0.0 for dimension in DIMENSIONS}

    correctness = sum(round.assessment_score for round in rounds) / len(rounds)
    first_success = next((round.round_index for round in rounds if round.assessment_passed), None)
    if first_success is None:
        rounds_score = 0.0
    else:
        # 1.0 for a first-round success, decaying with the number of rounds used.
        rounds_score = max(0.0, 1.0 - (first_success - 1) / len(rounds))

    intervention = sum(INTERVENTION_WEIGHT.get(round.action_kind, 0.5) for round in rounds) / len(
        rounds
    )
    hint_efficiency = max(0.0, 1.0 - intervention)

    passed_rounds = [round for round in rounds if round.assessment_passed]
    if not passed_rounds:
        independence = 0.0
    else:
        independent_passes = sum(
            1
            for round in passed_rounds
            if INTERVENTION_WEIGHT.get(round.action_kind, 0.5) <= INDEPENDENT_INTERVENTION_CEILING
        )
        independence = independent_passes / len(passed_rounds)

    return {
        "correctness": round(correctness, 6),
        "rounds_to_first_success": round(rounds_score, 6),
        "hint_efficiency": round(hint_efficiency, 6),
        "independence": round(independence, 6),
    }


def _assert_rubric_is_blind() -> None:
    """Fail closed if the rubric signature/schema leaks strategy identity."""

    import inspect

    parameters = list(inspect.signature(blind_score).parameters)
    forbidden = {"policy", "policy_version", "teacher", "strategy", "arm", "variant"}
    if set(parameters) & forbidden:
        raise AssertionError(f"blind rubric leaks strategy metadata: {parameters}")
    allowed = {
        "trajectory_id",
        "rounds",
        "round_index",
        "case_id",
        "action_kind",
        "action_hint_level",
        "assessment_passed",
        "assessment_score",
        "hidden_cases_passed",
        "hidden_cases_total",
    }
    fields = set(BlindRound.__dataclass_fields__) | {"trajectory_id", "rounds"}
    if fields - allowed:
        raise AssertionError(f"blind view exposes non-blind fields: {sorted(fields - allowed)}")


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------
def _mean(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _variance(values: Sequence[float]) -> float:
    """Population variance (deterministic; no sampling assumptions)."""

    if not values:
        return 0.0
    mean = _mean(values)
    return sum((value - mean) ** 2 for value in values) / len(values)


@dataclass
class PolicyComparison:
    """One policy's measured dimension values across seeds."""

    policy_version: str
    policy_class: str
    seeds: tuple[int, ...]
    per_trajectory: list[dict[str, Any]] = field(default_factory=list)
    failure_cases: list[dict[str, Any]] = field(default_factory=list)

    def dimension_values(self) -> dict[str, list[float]]:
        values: dict[str, list[float]] = {dimension: [] for dimension in DIMENSIONS}
        for run in self.per_trajectory:
            for dimension in DIMENSIONS:
                values[dimension].append(float(run["scores"][dimension]))
        return values

    def statistics(self) -> dict[str, dict[str, float]]:
        return {
            dimension: {
                "mean": round(_mean(values), 6),
                "variance": round(_variance(values), 6),
                "stdev": round(math.sqrt(_variance(values)), 6),
                "n": len(values),
                "values": [round(value, 6) for value in values],
            }
            for dimension, values in self.dimension_values().items()
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_version": self.policy_version,
            "policy_class": self.policy_class,
            "seeds": list(self.seeds),
            "trajectories": len(self.per_trajectory),
            "runs": list(self.per_trajectory),
            "statistics": self.statistics(),
            "failure_cases": list(self.failure_cases),
        }


@dataclass
class ComparisonResult:
    """Structured v0/v1 comparison result (protocol + measurements)."""

    protocol: dict[str, Any]
    policies: dict[str, PolicyComparison]
    case_catalog_size: int
    cases_assessed: list[str]
    seeds: tuple[int, ...]
    max_rounds: int
    total_rounds_measured: int
    run_digest: str
    disclaimer: str = DISCLAIMER

    # -- helpers -----------------------------------------------------------
    def dimension_delta(self) -> dict[str, float]:
        v0 = self.policies["teacher_v0"].statistics()
        v1 = self.policies["teacher_v1"].statistics()
        return {
            dimension: round(v1[dimension]["mean"] - v0[dimension]["mean"], 6)
            for dimension in DIMENSIONS
        }

    def failure_cases(self) -> list[dict[str, Any]]:
        failures: list[dict[str, Any]] = []
        for comparison in self.policies.values():
            failures.extend(comparison.failure_cases)
        return failures

    def conclusion(self) -> str:
        delta = self.dimension_delta()
        parts = [f"{dimension}: delta(v1-v0)={delta[dimension]:+.3f}" for dimension in DIMENSIONS]
        return (
            "Offline synthetic simulation only. Between-policy differences "
            "(teacher_v1 minus teacher_v0: "
            + "; ".join(parts)
            + ") are simulator-internal behaviour differences on fixed synthetic cases and "
            f"{len(self.seeds)} seeds. This is not real teaching effect: no significance is "
            "claimed and no real-world effectiveness is demonstrated. Conclusions are limited "
            "to this deterministic simulator."
        )

    def validate(self) -> None:
        """Structural protocol validation (raises on malformed comparison)."""

        if set(self.policies) != {"teacher_v0", "teacher_v1"}:
            raise ValueError(f"comparison must contain exactly v0/v1, got {sorted(self.policies)}")
        if self.case_catalog_size < 12:
            raise ValueError(
                f"case catalog must contain >=12 fixed cases, got {self.case_catalog_size}"
            )
        if len(self.seeds) < 2:
            raise ValueError("comparison needs >=2 fixed seeds to record variance")
        for name, comparison in self.policies.items():
            expected_class = {"teacher_v0": "FixedPolicy", "teacher_v1": "AdaptivePolicy"}[name]
            if comparison.policy_class != expected_class:
                raise ValueError(f"{name} must use {expected_class}, got {comparison.policy_class}")
            statistics = comparison.statistics()
            for dimension in DIMENSIONS:
                if dimension not in statistics:
                    raise ValueError(f"{name}: missing dimension {dimension}")
                if statistics[dimension]["n"] < 2:
                    raise ValueError(f"{name}:{dimension} needs >=2 values for variance")
                for value in statistics[dimension]["values"]:
                    if not 0.0 <= value <= 1.0:
                        raise ValueError(f"{name}:{dimension} value out of [0,1]: {value}")
        self.assert_no_overclaim(self.conclusion())
        if "not real teaching effect" not in self.disclaimer.casefold():
            raise ValueError("comparison disclaimer must state 'not real teaching effect'")

    @staticmethod
    def assert_no_overclaim(text: str) -> None:
        assert_no_overclaim(text)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "m1.compare.v0",
            "protocol": dict(self.protocol),
            "case_catalog_size": self.case_catalog_size,
            "cases_assessed": list(self.cases_assessed),
            "seeds": list(self.seeds),
            "max_rounds": self.max_rounds,
            "total_rounds_measured": self.total_rounds_measured,
            "run_digest": self.run_digest,
            "policies": {name: comparison.to_dict() for name, comparison in self.policies.items()},
            "delta_v1_minus_v0": self.dimension_delta(),
            "failure_cases": self.failure_cases(),
            "failure_case_count": len(self.failure_cases()),
            "conclusion": self.conclusion(),
            "disclaimer": self.disclaimer,
        }

    def to_markdown(self) -> str:
        lines: list[str] = []
        lines.append("# teacher_v0 vs teacher_v1 -- offline synthetic comparison")
        lines.append("")
        lines.append(f"> **Boundary:** {self.disclaimer}")
        lines.append("")
        lines.append("## Protocol")
        lines.append("")
        lines.append(f"- fixed seeds: `{list(self.seeds)}`")
        lines.append(f"- fixed case catalog size: `{self.case_catalog_size}`")
        lines.append(f"- max rounds per trajectory: `{self.max_rounds}`")
        lines.append(f"- blind rubric: `{SCORER_MODULE_ID}` (scores anonymised trajectories only)")
        lines.append(f"- trajectory run digest: `{self.run_digest}`")
        lines.append("")
        lines.append("## Dimension means and variance")
        lines.append("")
        header = "| dimension | teacher_v0 mean | teacher_v0 var | teacher_v1 mean | teacher_v1 var | delta(v1-v0) |"
        lines.append(header)
        lines.append("| --- | --- | --- | --- | --- | --- |")
        v0_stats = self.policies["teacher_v0"].statistics()
        v1_stats = self.policies["teacher_v1"].statistics()
        delta = self.dimension_delta()
        for dimension in DIMENSIONS:
            lines.append(
                f"| {dimension} | {v0_stats[dimension]['mean']:.4f} | "
                f"{v0_stats[dimension]['variance']:.6f} | {v1_stats[dimension]['mean']:.4f} | "
                f"{v1_stats[dimension]['variance']:.6f} | {delta[dimension]:+.4f} |"
            )
        lines.append("")
        lines.append("## Failure cases")
        lines.append("")
        failures = self.failure_cases()
        lines.append(f"- recorded failing rounds: `{len(failures)}`")
        for failure in failures[:12]:
            lines.append(
                f"- policy={failure['policy']} seed={failure['seed']} round={failure['round']} "
                f"case={failure['case_id']} modes={failure['failure_modes']}"
            )
        if len(failures) > 12:
            lines.append(f"- ... and {len(failures) - 12} more")
        lines.append("")
        lines.append("## Conclusion (bounded)")
        lines.append("")
        lines.append(self.conclusion())
        lines.append("")
        return "\n".join(lines)


def assert_no_overclaim(text: str) -> None:
    """Reject comparison text that overclaims real-world effectiveness."""

    lowered = text.casefold()
    for phrase in FORBIDDEN_OVERCLAIM_PHRASES:
        if phrase.casefold() in lowered:
            raise AssertionError(f"comparison text overclaims: contains {phrase!r}")
    if "not real teaching effect" not in lowered:
        raise AssertionError("comparison text must contain the 'not real teaching effect' boundary")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
def _policy_factory(name: str) -> TeachingPolicy:
    if name == "teacher_v0":
        return FixedPolicy()
    if name == "teacher_v1":
        return AdaptivePolicy()
    raise ValueError(f"unknown policy: {name}")


def _trajectory_digest(loop_result: LoopResult) -> str:
    return trace_digest(loop_result.events)


def run_comparison(
    *,
    seeds: Sequence[int] = DEFAULT_SEEDS,
    max_rounds: int = DEFAULT_MAX_ROUNDS,
    cases: Sequence[CFCase] | None = None,
    judge: CFJudge | None = None,
    learner_fixture_name: str = "learner_weak_beginner",
    policy_names: Sequence[str] = ("teacher_v0", "teacher_v1"),
    case_catalog_size: int | None = None,
) -> ComparisonResult:
    """Run the fixed-case, fixed-seed, blind-scored v0/v1 comparison."""

    _assert_rubric_is_blind()
    if cases is None:
        cases = load_cf_cases()
    if case_catalog_size is not None:
        cases = list(cases)[:case_catalog_size]
    if len(cases) < 12:
        raise ValueError(f"comparison needs a fixed catalog of >=12 cases, got {len(cases)}")
    seeds = tuple(int(seed) for seed in seeds)
    if len(seeds) < 2:
        raise ValueError("comparison needs >=2 fixed seeds to record variance")

    policies: dict[str, PolicyComparison] = {}
    cases_assessed: set[str] = set()
    total_rounds = 0
    digests: list[str] = []

    for policy_name in policy_names:
        policy = _policy_factory(policy_name)
        comparison = PolicyComparison(
            policy_version=policy.policy_version,
            policy_class=type(policy).__name__,
            seeds=seeds,
        )
        for seed in seeds:
            result = run_closed_loop(
                policy=policy,
                cases=cases,
                learner_fixture_name=learner_fixture_name,
                seed=seed,
                max_rounds=max_rounds,
                mastery_threshold=DEFAULT_MASTERY_THRESHOLD,
                judge=judge,
            )
            if result.halt_reason not in (None, "goal_mastered"):
                raise RuntimeError(
                    f"comparison run halted unexpectedly for {policy_name} seed={seed}: "
                    f"{result.halt_reason} markers={result.failure_markers}"
                )
            blind = build_blind_trajectory(result)
            scores = blind_score(blind)
            comparison.per_trajectory.append(
                {
                    "seed": seed,
                    "trajectory_id": blind.trajectory_id,
                    "rounds": blind.round_count,
                    "scores": scores,
                    "trace_digest": _trajectory_digest(result),
                    "halt_reason": result.halt_reason,
                    "failure_markers": list(result.failure_markers),
                }
            )
            total_rounds += blind.round_count
            cases_assessed.update(round.case_id for round in blind.rounds)
            digests.append(_trajectory_digest(result))
            for record in result.rounds:
                assessment = record.assessment
                if assessment is None or assessment.passed:
                    continue
                comparison.failure_cases.append(
                    {
                        "policy": policy_name,
                        "policy_version": policy.policy_version,
                        "seed": seed,
                        "round": record.round,
                        "case_id": record.task_id,
                        "scorer_id": assessment.scorer_id,
                        "failure_modes": list(assessment.failure_modes),
                        "hidden_cases_passed": assessment.hidden_cases_passed,
                        "hidden_cases_total": assessment.hidden_cases_total,
                    }
                )
        policies[policy_name] = comparison

    run_digest = hashlib.sha256("|".join(digests).encode("utf-8")).hexdigest()
    protocol = {
        "protocol_id": "m1.compare.v0",
        "policies": {
            "teacher_v0": "FixedPolicy (fixed LIGHT_HINT ladder, non-adaptive)",
            "teacher_v1": "AdaptivePolicy (diagnosis/evidence adaptive hint ladder)",
        },
        "fixed_cases": True,
        "case_catalog": "fixtures/m1/cf/problems (synthetic, public) + hidden judge fixtures",
        "fixed_seeds": list(seeds),
        "max_rounds": max_rounds,
        "blind_rubric": True,
        "scorer_module": SCORER_MODULE_ID,
        "scorer_sees_policy_identity": False,
        "teacher_self_report_used_as_truth": False,
        "dimensions": list(DIMENSIONS),
        "mastery_threshold": DEFAULT_MASTERY_THRESHOLD,
        "mastery_threshold_note": (
            "frozen above 1.0 for the comparison only so both policies run the same fixed "
            "number of rounds; this is a protocol control, not a claim about learning."
        ),
    }
    result = ComparisonResult(
        protocol=protocol,
        policies=policies,
        case_catalog_size=len(cases),
        cases_assessed=sorted(cases_assessed),
        seeds=seeds,
        max_rounds=max_rounds,
        total_rounds_measured=total_rounds,
        run_digest=run_digest,
    )
    result.validate()
    return result
