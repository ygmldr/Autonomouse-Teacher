"""Deterministic, replayable offline teaching closed-loop harness (M1).

The harness simulates the protocol required by ``docs/m1/EVALUATION_PROTOCOL.md``:

    Goal -> Baseline Diagnosis -> Knowledge/Skill Gap -> Teaching Action ->
    Learner Response -> Independent Assessment -> Memory Update -> Next Task

Everything here is local and synthetic:

* The **teacher** is a rule-based :class:`~m1_offline.teaching_policy.TeachingPolicy`
  (``FixedPolicy``/``AdaptivePolicy``); it never grades its own work.
* The **learner response** is produced through a :class:`~m1_offline.runtime_port.RuntimePort`
  (a deterministic ``MockRuntimePort`` by default, ``simulated=True``).  It is a
  scripted *simulated* learner, not a real model and not a real human.
* The **assessment** is an independent local judge (:class:`m1_offline.cf.judge.CFJudge`)
  that runs the submitted code against hidden fixtures.  Teacher text never
  influences the verdict; only executed code does.
* Mastery moves **only** when an :class:`~m1_offline.types.EvidenceEvent` carries a
  score derived from the independent assessment.  No evidence, no mastery.
* Every step is a :class:`~m1_offline.types.TraceEvent` with a deterministic
  timestamp; the full loop is written to JSONL (optional) and can be replayed
  from the events alone.  Two runs with the same inputs are byte-identical.

Boundary: results are **offline synthetic simulation; not real teaching effect**
and must never be extrapolated to real learners or real models.
"""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

from m1_offline import FIXTURES_DIR
from m1_offline.cf.judge import CFJudge, JudgeResult
from m1_offline.curriculum_planner import CurriculumPlanner
from m1_offline.learner_model import LearnerModel
from m1_offline.memory import LearningMemory
from m1_offline.runtime_port import MockRuntimePort, RuntimePort
from m1_offline.teaching_policy import (
    AdaptivePolicy,
    TeachingPolicy,
)
from m1_offline.types import (
    AssessmentResult,
    CurriculumPlan,
    DiagnosticResult,
    EvidenceEvent,
    LearnerProfile,
    LearnerState,
    LearningGoal,
    LearningTask,
    RuntimeRequest,
    RuntimeResponse,
    TeacherAction,
    TraceEvent,
)

__all__ = [
    "SCORER_ID",
    "LoopConfig",
    "SimulatedLearner",
    "ClosedLoopHarness",
    "LoopResult",
    "RoundRecord",
    "ReplayResult",
    "DeterministicClock",
    "load_cf_cases",
    "load_learner_fixture",
    "run_closed_loop",
    "replay_trace",
    "trace_digest",
    "DETERMINISTIC_EPOCH",
]

#: Scorer identity written into every :class:`AssessmentResult`.
SCORER_ID = "independent_cf_judge_v0"

#: Fixed clock epoch: makes traces/reports byte-reproducible.
DETERMINISTIC_EPOCH = "2026-01-01T00:00:00Z"

#: Support the teacher's action provides to the simulated learner, keyed by
#: ``TeacherAction.kind``.  This is a deliberately simple synthetic simulator
#: parameter (documented, not calibrated): hints help, clarifications do not.
ACTION_SUPPORT: dict[str, float] = {
    "LIGHT_HINT": 0.05,
    "INVARIANT_HINT": 0.15,
    "STRUCTURE_HINT": 0.25,
    "FULL_SOLUTION": 0.35,
    "SOCRATIC_QUESTION": 0.15,
    "EXPLAIN": 0.18,
    "REVIEW": 0.10,
    "PRACTICE": 0.05,
    "ASK_CLARIFICATION": 0.00,
}

#: Difficulty penalty per extra difficulty point (synthetic).
DIFFICULTY_PENALTY = 0.05

#: Skill mastery at/above which a goal target is considered mastered.
MASTERY_THRESHOLD = 0.70

#: Text patterns used to *explicitly flag* (never to reward) a simulated
#: learner who claims success without evidence.
HALLUCINATION_PATTERNS = (
    "all tests pass",
    "all hidden tests pass",
    "tests are passing",
    "i solved it",
    "solved perfectly",
    "no need to test",
    "全部通过",
    "已全部实现",
    "无需测试",
    "完美解决",
)
REFUSAL_PATTERNS = (
    "i can't help",
    "i cannot help",
    "i can't assist",
    "i cannot assist",
    "i must decline",
    "sorry, i can't",
    "抱歉，我不能",
    "无法协助",
)

#: Error class -> synthetic knowledge gap label (teacher-facing diagnosis only).
KNOWLEDGE_GAP_BY_ERROR = {
    "BOUNDARY_ERROR": "boundary conditions",
    "WRONG_ANSWER": "invariant reasoning",
    "SYNTAX_ERROR": "language syntax",
    "RUNTIME_ERROR": "execution semantics",
    "OFF_BY_ONE": "index arithmetic",
    "complexity": "complexity analysis",
}


# ---------------------------------------------------------------------------
# Deterministic clock
# ---------------------------------------------------------------------------
class DeterministicClock:
    """Counter-based ISO-8601 clock: deterministic across processes."""

    def __init__(self, start: str = DETERMINISTIC_EPOCH, step_seconds: int = 1) -> None:
        self._base = datetime.strptime(start, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        self._step = timedelta(seconds=step_seconds)
        self._ticks = 0

    def now(self) -> str:
        moment = self._base + self._step * self._ticks
        self._ticks += 1
        return moment.strftime("%Y-%m-%dT%H:%M:%SZ")

    @property
    def ticks(self) -> int:
        return self._ticks


# ---------------------------------------------------------------------------
# Fixture loading
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CFCase:
    """One synthetic CF problem: public problem view + hidden judge payload."""

    case_id: str
    problem: dict[str, Any]
    hidden: dict[str, Any] | None
    skills: tuple[str, ...]
    difficulty: int
    fixture_ref: str


def _cf_dir(fixtures_dir: Path | None = None) -> Path:
    return (fixtures_dir or FIXTURES_DIR) / "cf"


def load_cf_cases(
    fixtures_dir: Path | None = None,
    *,
    case_ids: Sequence[str] | None = None,
) -> list[CFCase]:
    """Load public CF problems and their hidden judge payloads (deterministic order)."""

    cf_dir = _cf_dir(fixtures_dir)
    problems_dir = cf_dir / "problems"
    if not problems_dir.is_dir():
        raise FileNotFoundError(f"CF problems fixture directory missing: {problems_dir}")
    cases: list[CFCase] = []
    for path in sorted(problems_dir.glob("*.json")):
        problem = json.loads(path.read_text(encoding="utf-8"))
        case_id = problem.get("problem_id") or path.stem
        if case_ids is not None and case_id not in set(case_ids):
            continue
        hidden_ref = problem.get("hidden_ref")
        hidden: dict[str, Any] | None = None
        if isinstance(hidden_ref, str) and hidden_ref:
            hidden_path = cf_dir / hidden_ref
            if hidden_path.is_file():
                hidden = json.loads(hidden_path.read_text(encoding="utf-8"))
        skills = tuple(problem.get("skills") or ())
        cases.append(
            CFCase(
                case_id=case_id,
                problem=problem,
                hidden=hidden,
                skills=skills,
                difficulty=int(problem.get("difficulty") or 1),
                fixture_ref=str(path.relative_to(cf_dir.parent.parent)),
            )
        )
    return cases


def load_learner_fixture(
    name: str = "learner_weak_beginner", fixtures_dir: Path | None = None
) -> dict[str, Any]:
    """Load one synthetic learner fixture (mastery priors + recorded error traces)."""

    path = (fixtures_dir or FIXTURES_DIR) / "cf" / "learners" / f"{name}.json"
    if not path.is_file():
        raise FileNotFoundError(f"learner fixture missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _profile_from_fixture(fixture: dict[str, Any]) -> LearnerProfile:
    profile_payload = fixture.get("profile") or {}
    return LearnerProfile(
        learner_id=profile_payload.get("learner_id") or fixture["learner_id"],
        display_name=profile_payload.get("display_name") or fixture.get("display_name", ""),
        baseline_level=profile_payload.get("baseline_level")
        or fixture.get("baseline_level", "BEGINNER"),
        created_at="2026-01-01T00:00:00Z",
    )


# ---------------------------------------------------------------------------
# Simulated learner
# ---------------------------------------------------------------------------
class SimulatedLearner:
    """Deterministic simulated learner whose output flows through a RuntimePort.

    The simulator chooses *which synthetic submission* the learner produces
    (a public reference-solution equivalent or a deliberately buggy variant).
    It never decides the grade: the independent judge evaluates the produced
    code against hidden tests, so a "confident" submission can still fail.

    ``simulated=True`` is recorded on every :class:`RuntimeResponse`; this is a
    scripted synthetic learner, not a real model and not a real human.
    """

    def __init__(
        self,
        profile: LearnerProfile,
        ability: dict[str, float],
        seed: int = 0,
        hint_support: dict[str, float] | None = None,
    ) -> None:
        self.profile = profile
        self.ability = dict(ability)
        self.seed = seed
        self.hint_support = dict(hint_support or ACTION_SUPPORT)

    # -- probability model (synthetic, documented in the protocol) ---------
    def success_probability(self, task: LearningTask, action: TeacherAction) -> float:
        skills = list(task.skill_ids) or ["default"]
        ability = sum(self.ability.get(skill, 0.25) for skill in skills) / len(skills)
        support = self.hint_support.get(action.kind, 0.0)
        penalty = DIFFICULTY_PENALTY * max(0, task.difficulty - 1)
        return max(0.0, min(1.0, ability + support - penalty))

    def _buggy_variant(self, problem: dict[str, Any], rng: random.Random) -> str:
        """Deterministically break a public reference solution (synthetic bug)."""

        reference = str(
            problem.get("reference_solution") or "def solution(*args):\n    return None\n"
        )
        strategy = rng.randrange(3)
        if strategy == 0:
            return reference.replace("return ", "return None  # simulated wrong answer: ")
        if strategy == 1:
            return reference.replace("return ", "return None  # simulated wrong answer: ", 1)
        lines = reference.splitlines()
        if len(lines) >= 2:
            return "\n".join([lines[0], "    return None  # simulated wrong answer"] + lines[1:])
        return reference

    def respond(
        self,
        *,
        task: LearningTask,
        problem: dict[str, Any],
        action: TeacherAction,
        round_index: int,
        loop_id: str,
    ) -> RuntimeResponse:
        """Produce the simulated learner's submission as a RuntimeResponse."""

        probability = self.success_probability(task, action)
        rng = random.Random(f"{self.seed}|{task.task_id}|{round_index}")
        correct = rng.random() < probability
        code = (
            str(problem.get("reference_solution") or "")
            if correct
            else self._buggy_variant(problem, rng)
        )
        script = {
            "responses": {
                f"{loop_id}:response:{round_index}": {
                    "text": code,
                    "tool_events": [{"tool": "write_code", "ok": True}],
                    "usage": {"prompt_tokens": 0, "completion_tokens": 0, "source": "mock"},
                }
            },
            "default": {"text": code},
        }
        port = MockRuntimePort(script=script, seed=self.seed)
        request = RuntimeRequest(
            request_id=f"{loop_id}:response:{round_index}",
            session_id=loop_id,
            messages=[
                {
                    "role": "system",
                    "content": "You are a SIMULATED learner in an offline evaluation. "
                    "Return only synthetic code for the given task.",
                },
                {"role": "user", "content": action.content},
            ],
            tools=[],
            metadata={"role": "simulated_learner", "simulated": True, "round": round_index},
        )
        return port.send(request)


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------
@dataclass
class RoundRecord:
    """One completed loop round (action -> response -> assess -> memory)."""

    round: int
    task_id: str
    task_skills: tuple[str, ...]
    action: TeacherAction
    assessment: AssessmentResult | None
    evidence_id: str | None
    state_after: dict[str, Any]
    failure_markers: list[str] = field(default_factory=list)
    duplicate_task: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "round": self.round,
            "task_id": self.task_id,
            "task_skills": list(self.task_skills),
            "action_kind": self.action.kind,
            "action_hint_level": self.action.hint_level,
            "assessment": self.assessment.to_dict() if self.assessment else None,
            "evidence_id": self.evidence_id,
            "state_after": self.state_after,
            "failure_markers": list(self.failure_markers),
            "duplicate_task": self.duplicate_task,
        }


@dataclass
class LoopResult:
    """Outcome of one full closed-loop run."""

    loop_id: str
    policy_version: str
    seed: int
    goal: LearningGoal
    diagnosis: DiagnosticResult
    gaps: dict[str, Any]
    plan: CurriculumPlan
    final_plan: CurriculumPlan
    rounds: list[RoundRecord]
    final_state: LearnerState
    events: list[TraceEvent]
    assessment_ids: list[str]
    baseline_evidence_ids: list[str]
    evidence_ids: list[str]
    halt_reason: str | None
    failure_markers: list[str]
    snapshots: dict[str, dict[str, Any]]
    trace_path: Path | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "m1.closed_loop_result.v0",
            "loop_id": self.loop_id,
            "policy_version": self.policy_version,
            "seed": self.seed,
            "goal": self.goal.to_dict(),
            "diagnosis": self.diagnosis.to_dict(),
            "gaps": self.gaps,
            "plan": self.plan.to_dict(),
            "final_plan_id": self.final_plan.plan_id,
            "rounds": [record.to_dict() for record in self.rounds],
            "final_state": self.final_state.to_dict(),
            "event_count": len(self.events),
            "assessment_ids": list(self.assessment_ids),
            "baseline_evidence_ids": list(self.baseline_evidence_ids),
            "evidence_ids": list(self.evidence_ids),
            "halt_reason": self.halt_reason,
            "failure_markers": list(self.failure_markers),
            "trace_path": str(self.trace_path) if self.trace_path else None,
            "boundary": "offline synthetic simulation; not real teaching effect",
        }

    @property
    def completed_rounds(self) -> int:
        return len(self.rounds)

    @property
    def passed_rounds(self) -> int:
        return sum(
            1
            for record in self.rounds
            if record.assessment is not None and record.assessment.passed
        )

    def step_sequence(self) -> list[tuple[int, str]]:
        return [(event.round, event.step) for event in self.events]

    def to_jsonl(self) -> str:
        return "".join(event.to_json() + "\n" for event in self.events)


@dataclass
class ReplayResult:
    """State rebuilt purely from trace events."""

    loop_id: str
    events: list[TraceEvent]
    step_sequence: list[tuple[int, str]]
    tests_started: int
    assessments: list[AssessmentResult]
    evidence: list[EvidenceEvent]
    final_state: LearnerState | None
    halt_reason: str | None

    def assessment_ids(self) -> list[str]:
        return [item.assessment_id for item in self.assessments]

    def evidence_ids(self) -> list[str]:
        return [item.event_id for item in self.evidence]


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------
@dataclass
class LoopConfig:
    """Deterministic loop configuration."""

    seed: int = 0
    max_rounds: int = 3
    loop_id: str = ""
    mastery_threshold: float = MASTERY_THRESHOLD
    requested_hint_level: int = 1
    baseline_evidence: bool = True
    force_duplicate_task: bool = False
    clock_start: str = DETERMINISTIC_EPOCH
    clock_step_seconds: int = 1
    trace_path: str | None = None

    def resolved_loop_id(self, policy_version: str) -> str:
        return self.loop_id or f"loop_{policy_version}_seed{self.seed}"


class ClosedLoopHarness:
    """Runs the deterministic offline closed loop for one policy/learner pair."""

    def __init__(
        self,
        *,
        cases: Sequence[CFCase],
        learner_fixture: dict[str, Any],
        policy: TeachingPolicy,
        config: LoopConfig | None = None,
        judge: CFJudge | None = None,
        runtime: RuntimePort | None = None,
        planner: CurriculumPlanner | None = None,
        goal: LearningGoal | None = None,
    ) -> None:
        if not cases:
            raise ValueError("harness needs at least one CF case")
        self.cases = list(cases)
        self.cases_by_id = {case.case_id: case for case in self.cases}
        self.learner_fixture = learner_fixture
        self.policy = policy
        self.config = config or LoopConfig()
        self.judge = judge or CFJudge()
        # An injected runtime wins over the internal simulated learner (used by
        # failure-injection tests: error/timeout/refusal responses).
        self.injected_runtime = runtime
        self.planner = planner or CurriculumPlanner()
        self.clock = DeterministicClock(self.config.clock_start, self.config.clock_step_seconds)
        self.profile = _profile_from_fixture(learner_fixture)
        self.model = LearnerModel(self.profile)
        self.memory = LearningMemory()
        self._events: list[TraceEvent] = []
        self._seq = 0
        self._learners_ability = {
            str(key): float(value) for key, value in (learner_fixture.get("mastery") or {}).items()
        }
        self.learner = SimulatedLearner(
            profile=self.profile, ability=self._learners_ability, seed=self.config.seed
        )
        self.loop_id = self.config.resolved_loop_id(policy.policy_version)
        self.goal = goal or LearningGoal(
            goal_id=f"goal_{self.loop_id}",
            learner_id=self.profile.learner_id,
            target_skills=list(learner_fixture.get("focus_skills") or ["array-basics"]),
            deadline_days=7,
            weekly_minutes=300,
        )

    # -- trace helpers -----------------------------------------------------
    def _record(self, *, round_index: int, step: str, payload: dict[str, Any]) -> TraceEvent:
        payload = dict(payload)
        payload.setdefault("learner_id", self.profile.learner_id)
        payload["seq"] = self._seq
        event = TraceEvent(
            event_id=f"{self.loop_id}:e{self._seq:04d}",
            loop_id=self.loop_id,
            round=round_index,
            step=step,
            payload=payload,
            timestamp=self.clock.now(),
        )
        self._events.append(event)
        self.memory.append(event)
        self._seq += 1
        return event

    def _state_snapshot(self) -> LearnerState:
        """Snapshot with a deterministic timestamp even when no evidence exists."""

        state = self.model.state()
        if state.evidence_count == 0:
            state.updated_at = DETERMINISTIC_EPOCH
        return state

    def _deterministic_plan(self, state: LearnerState) -> CurriculumPlan:
        """Plan with an injected deterministic ``created_at`` (planner defaults to wall clock)."""

        plan = self.planner.plan(self.goal, state, self._learning_tasks())
        plan.created_at = self.clock.now()
        return plan

    def _task_dict(self, task: LearningTask) -> dict[str, Any]:
        return {
            "task_id": task.task_id,
            "skill_ids": list(task.skill_ids),
            "task_type": task.task_type,
            "difficulty": task.difficulty,
            "goal_id": task.goal_id,
        }

    def _learning_tasks(self) -> list[LearningTask]:
        return [
            LearningTask(
                task_id=case.case_id,
                goal_id=self.goal.goal_id,
                skill_ids=list(case.skills) or ["general"],
                task_type="CF_PROBLEM",
                difficulty=case.difficulty,
                fixture_ref=case.fixture_ref,
                ordinal=index,
            )
            for index, case in enumerate(self.cases)
        ]

    # -- baseline diagnosis ------------------------------------------------
    def _baseline_evidence(self) -> list[EvidenceEvent]:
        events: list[EvidenceEvent] = []
        if not self.config.baseline_evidence:
            return events
        traces = self.learner_fixture.get("error_traces") or []
        for trace in traces:
            task_id = str(trace.get("task_id") or "")
            case = self.cases_by_id.get(task_id)
            skills = list(case.skills) if case else []
            events.append(
                EvidenceEvent(
                    event_id=f"{self.loop_id}:baseline:{trace.get('trace_id') or len(events)}",
                    learner_id=self.profile.learner_id,
                    task_id=task_id or "unknown-task",
                    kind=str(trace.get("kind") or "CODE_SUBMISSION"),
                    payload={
                        "skill_ids": skills,
                        "source": "synthetic-fixture",
                        "note": "recorded baseline error trace from synthetic learner fixture",
                        "fixture_created_at": trace.get("created_at"),
                    },
                    observed_score=float(trace.get("observed_score") or 0.0),
                    error_codes=[str(trace.get("expected_error_class") or "UNKNOWN")],
                    created_at=self.clock.now(),
                )
            )
        return events

    def _diagnose(self, round_index: int = 0) -> tuple[DiagnosticResult, list[EvidenceEvent]]:
        evidence = self._baseline_evidence()
        state = self._state_snapshot()
        for item in evidence:
            state = self.model.apply_evidence(item)
        error_classes: list[str] = []
        for item in evidence:
            for code in item.error_codes:
                if code not in error_classes:
                    error_classes.append(code)
        if evidence:
            diagnosis = DiagnosticResult(
                diagnosis_id=f"{self.loop_id}:diagnosis",
                task_id=evidence[0].task_id,
                error_codes=error_classes,
                confidence=0.8,
                status="RESOLVED",
                explanation=(
                    f"baseline diagnosis from {len(evidence)} recorded synthetic error traces "
                    f"(synthetic-fixture); error classes={error_classes}"
                ),
                evidence_refs=[item.event_id for item in evidence],
            )
        else:
            diagnosis = DiagnosticResult(
                diagnosis_id=f"{self.loop_id}:diagnosis",
                task_id=self.cases[0].case_id,
                error_codes=["insufficient_evidence"],
                confidence=0.0,
                status="NEEDS_REVIEW",
                explanation=(
                    "no learner evidence available: baseline diagnosis is UNKNOWN and no "
                    "mastery may be claimed without assessment evidence"
                ),
                evidence_refs=[],
            )
        self._record(
            round_index=round_index,
            step="diagnose",
            payload={
                "kind": "FACT",
                "source": "synthetic-fixture" if evidence else "harness",
                "diagnosis": diagnosis.to_dict(),
                "evidence_events": [item.to_dict() for item in evidence],
                "state_after": state.to_dict(),
                "insufficient_evidence": not bool(evidence),
            },
        )
        return diagnosis, evidence

    # -- gaps --------------------------------------------------------------
    def _identify_gaps(
        self, diagnosis: DiagnosticResult, state: LearnerState, round_index: int = 0
    ) -> dict[str, Any]:
        skill_gaps = [
            skill
            for skill in self.goal.target_skills
            if state.mastery.get(skill, 0.0) < self.config.mastery_threshold
        ]
        knowledge_gaps: list[str] = []
        for code in diagnosis.error_codes:
            label = KNOWLEDGE_GAP_BY_ERROR.get(code)
            if label and label not in knowledge_gaps:
                knowledge_gaps.append(label)
        if not knowledge_gaps and skill_gaps:
            knowledge_gaps = ["core invariants and boundary handling"]
        gaps = {
            "target_skills": list(self.goal.target_skills),
            "mastery_threshold": self.config.mastery_threshold,
            "skill_gaps": skill_gaps,
            "knowledge_gaps": knowledge_gaps,
            "mastery_snapshot": dict(state.mastery),
            "diagnosis_error_codes": list(diagnosis.error_codes),
        }
        self._record(
            round_index=round_index,
            step="gap",
            payload={
                "kind": "INFERENCE",
                "source": "harness",
                "gaps": gaps,
                "learner_id": self.profile.learner_id,
            },
        )
        return gaps

    # -- per-round diagnosis for the policy ---------------------------------
    @staticmethod
    def diagnosis_from_assessment(
        assessment: AssessmentResult,
        loop_id: str,
        round_index: int,
    ) -> DiagnosticResult | None:
        """Derive a teacher-facing diagnosis from the *independent* assessment."""

        if assessment.passed:
            return None
        codes: list[str] = []
        for mode in assessment.failure_modes:
            if mode in {"hidden_cases_failed"}:
                codes.append("WRONG_ANSWER")
            elif mode in {"tool_error"}:
                codes.append("UNKNOWN_FAILURE")
            elif mode in {"refusal"}:
                codes.append("REFUSAL")
            elif mode in {"timeout"}:
                codes.append("TIMEOUT")
            elif mode not in codes:
                codes.append(mode.upper())
        if not codes:
            codes = ["UNKNOWN_FAILURE"]
        status = (
            "RESOLVED"
            if all(code not in {"UNKNOWN_FAILURE", "TIMEOUT"} for code in codes)
            else "NEEDS_REVIEW"
        )
        return DiagnosticResult(
            diagnosis_id=f"{loop_id}:diagnosis:r{round_index}",
            task_id=assessment.task_id,
            error_codes=codes,
            confidence=0.6 if status == "RESOLVED" else 0.2,
            status=status,
            explanation=(
                f"assessment {assessment.assessment_id} failed with modes={assessment.failure_modes}; "
                "diagnosis is derived from the independent assessment, not from teacher self-report"
            ),
            evidence_refs=[assessment.assessment_id],
        )

    # -- learner response ---------------------------------------------------
    @staticmethod
    def _contains_any(text: str, patterns: Iterable[str]) -> bool:
        lowered = text.casefold()
        return any(pattern.casefold() in lowered for pattern in patterns)

    def _obtain_response(
        self,
        *,
        task: LearningTask,
        case: CFCase,
        action: TeacherAction,
        round_index: int,
    ) -> tuple[RuntimeResponse | None, str | None, list[str]]:
        """Send through the RuntimePort; fail closed on transport problems."""

        request_id = f"{self.loop_id}:response:{round_index}"
        request = RuntimeRequest(
            request_id=request_id,
            session_id=self.loop_id,
            messages=[
                {
                    "role": "system",
                    "content": "SIMULATED offline learner; return synthetic code only.",
                },
                {
                    "role": "user",
                    "content": f"[{action.kind}] {action.content}",
                },
            ],
            metadata={"role": "simulated_learner", "simulated": True, "round": round_index},
        )
        markers: list[str] = []
        try:
            if self.injected_runtime is not None:
                response = self.injected_runtime.send(request)
            else:
                response = self.learner.respond(
                    task=task,
                    problem=case.problem,
                    action=action,
                    round_index=round_index,
                    loop_id=self.loop_id,
                )
        except TimeoutError as exc:  # explicit timeout injection
            return None, "timeout", [f"timeout: {exc}"]
        except Exception as exc:  # noqa: BLE001 - transport failure must fail closed
            message = str(exc)
            marker = "timeout" if "timeout" in message.casefold() else "runtime_failure"
            return None, marker, [f"{marker}: {type(exc).__name__}: {message}"]

        if not isinstance(response, RuntimeResponse):
            return None, "invalid_runtime_response", ["invalid_runtime_response"]
        if response.simulated is not True:
            return None, "non_simulated_response", ["non_simulated_response"]
        if response.error:
            marker = "timeout" if "timeout" in response.error.casefold() else "runtime_error"
            return response, marker, [f"{marker}: {response.error}"]
        text = response.text or ""
        if self._contains_any(text, REFUSAL_PATTERNS):
            markers.append("refusal")
        if self._contains_any(text, HALLUCINATION_PATTERNS):
            markers.append("hallucination_suspected")
        return response, None, markers

    # -- assessment ---------------------------------------------------------
    def _assess(
        self, case: CFCase, code: str, round_index: int
    ) -> tuple[AssessmentResult, JudgeResult | None]:
        total = len((case.hidden or {}).get("tests") or [])
        if case.hidden is None:
            return (
                AssessmentResult(
                    assessment_id=f"{self.loop_id}:assessment:{round_index}",
                    task_id=case.case_id,
                    learner_id=self.profile.learner_id,
                    scorer_id=SCORER_ID,
                    passed=False,
                    score=0.0,
                    dimensions={"hidden_cases": 0.0, "correctness": 0.0},
                    failure_modes=["hidden_fixture_missing"],
                    hidden_cases_passed=0,
                    hidden_cases_total=0,
                ),
                None,
            )
        try:
            verdict = self.judge.evaluate(case.problem, case.hidden, code)
        except Exception:  # noqa: BLE001 - judge crash must fail closed
            return (
                AssessmentResult(
                    assessment_id=f"{self.loop_id}:assessment:{round_index}",
                    task_id=case.case_id,
                    learner_id=self.profile.learner_id,
                    scorer_id=SCORER_ID,
                    passed=False,
                    score=0.0,
                    dimensions={"hidden_cases": 0.0, "correctness": 0.0},
                    failure_modes=["tool_error"],
                    hidden_cases_passed=0,
                    hidden_cases_total=total,
                ),
                None,
            )
        ratio = (verdict.cases_passed / verdict.cases_total) if verdict.cases_total else 0.0
        failure_modes: list[str] = []
        if verdict.error is not None:
            failure_modes.append("tool_error")
        elif not verdict.passed:
            failure_modes.append("hidden_cases_failed")
        assessment = AssessmentResult(
            assessment_id=f"{self.loop_id}:assessment:{round_index}",
            task_id=case.case_id,
            learner_id=self.profile.learner_id,
            scorer_id=SCORER_ID,
            passed=bool(verdict.passed),
            score=round(ratio, 6),
            dimensions={
                "hidden_cases": round(ratio, 6),
                "correctness": 1.0 if verdict.passed else 0.0,
            },
            failure_modes=failure_modes,
            hidden_cases_passed=int(verdict.cases_passed),
            hidden_cases_total=int(verdict.cases_total),
        )
        return assessment, verdict

    # -- plan selection -----------------------------------------------------
    def _select_task(
        self, plan: CurriculumPlan, attempted: set[str], round_index: int
    ) -> LearningTask | None:
        if self.config.force_duplicate_task and round_index == 2 and attempted:
            # Deliberate failure negative: force the round-1 task again.
            task_id = sorted(attempted)[0]
            for task in plan.tasks:
                if task.task_id == task_id:
                    return task
            return self._learning_tasks()[0]
        for task in plan.tasks:
            if task.task_id in attempted:
                continue
            return task
        for task in self._learning_tasks():
            if task.task_id in attempted:
                continue
            return task
        return None

    # -- main loop ----------------------------------------------------------
    def run(self) -> LoopResult:
        config = self.config
        goal = self.goal
        self._record(
            round_index=0,
            step="goal",
            payload={
                "kind": "FACT",
                "source": "synthetic-fixture",
                "goal": goal.to_dict(),
                "learner_id": self.profile.learner_id,
            },
        )
        diagnosis, baseline_events = self._diagnose(round_index=0)
        state = self.model.state()
        gaps = self._identify_gaps(diagnosis, state, round_index=0)
        initial_plan = self._deterministic_plan(state)
        plan = initial_plan
        self._record(
            round_index=0,
            step="plan",
            payload={
                "kind": "INFERENCE",
                "source": self.planner.policy_version,
                "plan": plan.to_dict(),
            },
        )

        rounds: list[RoundRecord] = []
        assessments: list[AssessmentResult] = []
        baseline_evidence_ids = [item.event_id for item in baseline_events]
        evidence_ids: list[str] = list(baseline_evidence_ids)
        snapshots: dict[str, dict[str, Any]] = {}
        attempted: set[str] = set()
        failure_markers: list[str] = []
        halt_reason: str | None = None
        previous_assessment: AssessmentResult | None = None

        if not config.baseline_evidence:
            failure_markers.append("insufficient_evidence")

        for round_index in range(1, config.max_rounds + 1):
            task = self._select_task(plan, attempted, round_index)
            if task is None:
                halt_reason = "no_unattempted_task"
                self._record(
                    round_index=round_index,
                    step="halt",
                    payload={
                        "kind": "ERROR",
                        "source": "harness",
                        "reason": halt_reason,
                        "failure_markers": list(failure_markers),
                    },
                )
                break
            if task.task_id in attempted:
                # Duplicate task: explicit fail-closed, never silently counted.
                failure_markers.append("duplicate_task")
                halt_reason = "duplicate_task"
                self._record(
                    round_index=round_index,
                    step="halt",
                    payload={
                        "kind": "ERROR",
                        "source": "harness",
                        "reason": halt_reason,
                        "task_id": task.task_id,
                        "failure_markers": list(failure_markers),
                    },
                )
                break
            attempted.add(task.task_id)
            case = self.cases_by_id[task.task_id]

            policy_diagnosis = (
                diagnosis
                if round_index == 1 or previous_assessment is None
                else self.diagnosis_from_assessment(previous_assessment, self.loop_id, round_index)
            )
            state_before = self._state_snapshot()
            action = self.policy.choose(
                self._task_dict(task),
                state_before,
                policy_diagnosis,
                config.requested_hint_level,
            )
            self._record(
                round_index=round_index,
                step="action",
                payload={
                    "kind": "ACTION",
                    "source": self.policy.policy_version,
                    "action": action.to_dict(),
                    "task_id": task.task_id,
                    "state_before": state_before.to_dict(),
                },
            )

            response, transport_marker, response_markers = self._obtain_response(
                task=task, case=case, action=action, round_index=round_index
            )
            if response is None or transport_marker is not None:
                marker = transport_marker or "runtime_failure"
                failure_markers.append(marker)
                halt_reason = f"runtime_{marker}"
                self._record(
                    round_index=round_index,
                    step="response",
                    payload={
                        "kind": "ERROR",
                        "source": "mock_runtime",
                        "simulated": True,
                        "transport_marker": marker,
                        "message": (response_markers[0] if response_markers else marker),
                    },
                )
                self._record(
                    round_index=round_index,
                    step="halt",
                    payload={
                        "kind": "ERROR",
                        "source": "harness",
                        "reason": halt_reason,
                        "failure_markers": list(failure_markers),
                    },
                )
                break

            self._record(
                round_index=round_index,
                step="response",
                payload={
                    "kind": "OBSERVATION",
                    "source": "mock_runtime",
                    "simulated": True,
                    "response": response.to_dict(),
                    "request_id": response.request_id,
                    "response_markers": list(response_markers),
                },
            )
            failure_markers.extend(response_markers)

            code = response.text or ""
            assessment, verdict = self._assess(case, code, round_index)
            assessments.append(assessment)
            if verdict is not None:
                judge_error = verdict.error
                failure_count = len(verdict.failures)
            else:
                judge_error = None
                failure_count = 0
            assessment_modes = list(assessment.failure_modes)
            for marker in response_markers:
                if marker not in assessment_modes:
                    assessment_modes.append(marker)
            for mode in assessment_modes:
                if mode not in failure_markers:
                    failure_markers.append(mode)
            if assessment_modes != assessment.failure_modes:
                assessment = AssessmentResult.from_dict(assessment.to_dict())
                assessment.failure_modes = assessment_modes
                assessments[-1] = assessment
            self._record(
                round_index=round_index,
                step="assess",
                payload={
                    "kind": "OBSERVATION",
                    "source": SCORER_ID,
                    "assessment": assessment.to_dict(),
                    "judge_error": judge_error,
                    "judge_failure_count": failure_count,
                    "independent_of_teacher": True,
                },
            )

            # Memory update: evidence ONLY from the independent assessment.
            error_codes = [mode.upper() for mode in assessment.failure_modes]
            evidence = EvidenceEvent(
                event_id=f"{self.loop_id}:evidence:{round_index}",
                learner_id=self.profile.learner_id,
                task_id=task.task_id,
                kind="ASSESSMENT",
                payload={
                    "skill_ids": list(task.skill_ids),
                    "source": SCORER_ID,
                    "assessment_id": assessment.assessment_id,
                    "hidden_cases_passed": assessment.hidden_cases_passed,
                    "hidden_cases_total": assessment.hidden_cases_total,
                },
                observed_score=assessment.score,
                error_codes=error_codes,
                created_at=self.clock.now(),
            )
            state_after = self.model.apply_evidence(evidence)
            evidence_ids.append(evidence.event_id)
            memory_event = self._record(
                round_index=round_index,
                step="memory",
                payload={
                    "kind": "FACT",
                    "source": "learner_model",
                    "evidence": evidence.to_dict(),
                    "state_after": state_after.to_dict(),
                    "evidence_driven": True,
                    "text_evidence_ignored": True,
                },
            )
            snapshots[memory_event.event_id] = state_after.to_dict()

            round_markers = [mode for mode in assessment.failure_modes]
            record = RoundRecord(
                round=round_index,
                task_id=task.task_id,
                task_skills=tuple(task.skill_ids),
                action=action,
                assessment=assessment,
                evidence_id=evidence.event_id,
                state_after=state_after.to_dict(),
                failure_markers=round_markers,
            )
            rounds.append(record)
            previous_assessment = assessment

            # Re-plan for the next round (memories of assessment are now facts).
            plan = self._deterministic_plan(state_after)
            mastered = all(
                state_after.mastery.get(skill, 0.0) >= config.mastery_threshold
                for skill in self.goal.target_skills
            )
            next_task_id = None
            if mastered:
                halt_reason = "goal_mastered"
            elif round_index < config.max_rounds:
                candidate = self._select_task(plan, attempted, round_index + 1)
                next_task_id = candidate.task_id if candidate else None
                if next_task_id is None:
                    halt_reason = "no_unattempted_task"
            self._record(
                round_index=round_index,
                step="next_task",
                payload={
                    "kind": "ACTION",
                    "source": self.planner.policy_version,
                    "plan_id": plan.plan_id,
                    "next_task_id": next_task_id,
                    "goal_mastered": mastered,
                    "mastery_snapshot": dict(state_after.mastery),
                },
            )
            if halt_reason is not None:
                self._record(
                    round_index=round_index,
                    step="halt",
                    payload={
                        "kind": "ERROR" if halt_reason != "goal_mastered" else "FACT",
                        "source": "harness",
                        "reason": halt_reason,
                        "failure_markers": list(failure_markers),
                    },
                )
                break

        trace_path = None
        if config.trace_path:
            trace_path = Path(config.trace_path)
            trace_path.parent.mkdir(parents=True, exist_ok=True)
            trace_path.write_text(
                "".join(event.to_json() + "\n" for event in self._events),
                encoding="utf-8",
            )

        return LoopResult(
            loop_id=self.loop_id,
            policy_version=self.policy.policy_version,
            seed=config.seed,
            goal=self.goal,
            diagnosis=diagnosis,
            gaps=gaps,
            plan=initial_plan,
            final_plan=plan,
            rounds=rounds,
            final_state=self._state_snapshot(),
            events=self._events,
            assessment_ids=[item.assessment_id for item in assessments],
            baseline_evidence_ids=baseline_evidence_ids,
            evidence_ids=evidence_ids,
            halt_reason=halt_reason,
            failure_markers=failure_markers,
            snapshots=snapshots,
            trace_path=trace_path,
        )


# ---------------------------------------------------------------------------
# Replay
# ---------------------------------------------------------------------------
def replay_trace(
    events: Sequence[TraceEvent],
    *,
    learner_profile: LearnerProfile | None = None,
    loop_id: str | None = None,
    until_event_id: str | None = None,
) -> ReplayResult:
    """Rebuild loop state purely from trace events.

    ``loop_id`` selects one loop; ``until_event_id`` replays only events up to
    and including that event id (for point-in-time state recovery).  When a
    learner profile is supplied, the final :class:`LearnerState` is rebuilt by
    replaying the recorded assessment-derived evidence events through
    :class:`~m1_offline.learner_model.LearnerModel`.
    """

    if not isinstance(events, (list, tuple)):
        raise TypeError(f"events must be a list, got {type(events).__name__}")
    trace_events: list[TraceEvent] = []
    for event in events:
        if not isinstance(event, TraceEvent):
            raise TypeError(f"replay_trace expects TraceEvent, got {type(event).__name__}")
        if loop_id is not None and event.loop_id != loop_id:
            continue
        trace_events.append(event)
    if not trace_events:
        raise ValueError("no trace events to replay for the requested loop_id")

    seqs = [event.payload.get("seq") for event in trace_events]
    if any(not isinstance(seq, int) for seq in seqs):
        raise ValueError("trace events missing integer payload.seq")
    if any(right != left + 1 for left, right in zip(seqs, seqs[1:])):
        raise ValueError("trace event sequence is not continuous")

    selected = trace_events
    if until_event_id is not None:
        index = next(
            (
                position
                for position, event in enumerate(trace_events)
                if event.event_id == until_event_id
            ),
            None,
        )
        if index is None:
            raise ValueError(f"event_id not found in trace: {until_event_id}")
        selected = trace_events[: index + 1]

    assessments: list[AssessmentResult] = []
    evidence: list[EvidenceEvent] = []
    halt_reason: str | None = None
    for event in selected:
        payload = event.payload
        if event.step == "assess":
            payload_assessment = payload.get("assessment")
            if isinstance(payload_assessment, dict):
                assessments.append(AssessmentResult.from_dict(payload_assessment))
        elif event.step == "diagnose":
            # Baseline diagnosis carries the historical (synthetic) evidence
            # that seeded the learner model before round 1.
            for raw_evidence in payload.get("evidence_events") or []:
                if isinstance(raw_evidence, dict):
                    evidence.append(EvidenceEvent.from_dict(raw_evidence))
        elif event.step == "memory":
            payload_evidence = payload.get("evidence")
            if isinstance(payload_evidence, dict):
                evidence.append(EvidenceEvent.from_dict(payload_evidence))
        elif event.step == "halt":
            candidate = payload.get("reason")
            if isinstance(candidate, str):
                halt_reason = candidate

    final_state: LearnerState | None = None
    if learner_profile is not None:
        model = LearnerModel(learner_profile)
        final_state = model.replay(evidence)

    return ReplayResult(
        loop_id=selected[0].loop_id,
        events=list(selected),
        step_sequence=[(event.round, event.step) for event in selected],
        tests_started=sum(1 for event in selected if event.step == "action"),
        assessments=assessments,
        evidence=evidence,
        final_state=final_state,
        halt_reason=halt_reason,
    )


def trace_digest(events: Sequence[TraceEvent]) -> str:
    """Deterministic SHA-256 over the canonical JSONL rendering of a trace."""

    blob = "".join(event.to_json() + "\n" for event in events)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Convenience entry point
# ---------------------------------------------------------------------------
def run_closed_loop(
    *,
    policy: TeachingPolicy | None = None,
    cases: Sequence[CFCase] | None = None,
    learner_fixture_name: str = "learner_weak_beginner",
    seeded_learner_fixture: dict[str, Any] | None = None,
    seed: int = 0,
    max_rounds: int = 3,
    loop_id: str = "",
    trace_path: str | Path | None = None,
    judge: CFJudge | None = None,
    runtime: RuntimePort | None = None,
    baseline_evidence: bool = True,
    force_duplicate_task: bool = False,
    requested_hint_level: int = 1,
    mastery_threshold: float = MASTERY_THRESHOLD,
) -> LoopResult:
    """Build default components and run one deterministic closed loop."""

    policy = policy or AdaptivePolicy()
    if cases is None:
        cases = load_cf_cases()
    if seeded_learner_fixture is not None:
        learner_fixture = seeded_learner_fixture
    else:
        learner_fixture = load_learner_fixture(learner_fixture_name)
    config = LoopConfig(
        seed=seed,
        max_rounds=max_rounds,
        loop_id=loop_id,
        baseline_evidence=baseline_evidence,
        force_duplicate_task=force_duplicate_task,
        requested_hint_level=requested_hint_level,
        mastery_threshold=mastery_threshold,
        trace_path=str(trace_path) if trace_path is not None else None,
    )
    harness = ClosedLoopHarness(
        cases=cases,
        learner_fixture=learner_fixture,
        policy=policy,
        config=config,
        judge=judge,
        runtime=runtime,
    )
    return harness.run()
