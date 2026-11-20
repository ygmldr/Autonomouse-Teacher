"""M1-A Offline Adaptive Teacher MVP -- executable, deterministic demo (B-PR5).

Run with::

    cd /root/at-m1a-mvp
    "/root/Autonomous Teacher/.venv/bin/python" -m m1_teacher.demo

The demo wires the frozen PR1-PR4 components into the B-PR5 closed-loop
demonstration required by the M1-A brief:

    create learner + goal -> initial diagnosis -> personalised plan (with
    structured Reason) -> teaching / practice -> independent scoring /
    error explanation / mastery change -> interrupt + restart recovery ->
    next recommendation

and prints a deterministic transcript (and, with ``--write-evidence``, writes
reproducible JSONL evidence under ``docs/m1a_evidence/``).

Determinism
-----------
All clocks that can influence decisions are fixed:

* the E2E ``MockStudentScorer`` stamps ``created_at = FIXED_TIMESTAMP``;
* the session/plan ids, action ids and diagnosis ids are content fingerprints;
* the evidence JSONL projection deliberately omits wall-clock timestamps
  (session/history records still carry real timestamps internally, but nothing
  wall-clock-derived is printed or persisted as evidence).

Two consecutive runs therefore produce byte-identical stdout and byte-identical
JSONL evidence files.  ``e2e_summary.json`` additionally records only a fixed
artifact manifest (``manifest_version`` / fixed ``generated_at`` / fixed
``base_sha`` / fixed ``implementation_commit``) and no wall-clock or git state,
so it is byte-identical for the same content tree with or without ``.git``.

Evidence classification (fixed M1-A vocabulary)
-----------------------------------------------
* ``MOCK`` -- synthetic student fixtures / scripted outcomes / seeded prior
  evidence.  Not real learner behaviour and not real model behaviour.
* ``DETERMINISTIC`` -- state machine, learner model arithmetic, ids, replay
  verification and the reproducible pytest evidence around them.
* ``NOT_VERIFIED`` -- any claim about real teaching effectiveness; this demo
  makes no such claim ("offline synthetic only, not real teaching effect").
"""

# B-PR1 judge-policy note: this module never executes learner CODE -- every
# student outcome is replayed by MockStudentScorer (synthetic MOCK evidence).
# Any future demo path that grades CODE through the independent scorer must
# construct DeterministicScorer(..., trusted_fixture_only=True) explicitly and
# label the fixtures as trusted synthetic.  There is no CLI/request switch that
# enables untrusted CODE execution; the default policy remains
# UNTRUSTED_CODE_EXECUTION_BLOCKED until B1 is independently reviewed and
# human-approved.

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from m1_teacher.contracts.types import (
    ASSESSMENT_STATUS_VALUES,
    AssessmentItem,
    AssessmentResult,
    CurriculumPlan,
    DiagnosisResult,
    LearnerGoal,
    LearnerSnapshot,
    LearningObjective,
    SessionState,
)
from m1_teacher.diagnostic.engine import DiagnosticEngine
from m1_teacher.domains.cf_binary_search import (
    CFBinarySearchDomainAdapter,
    default_fixtures_root,
)
from m1_teacher.knowledge import KnowledgeGraph
from m1_teacher.learner.history import LearningHistory
from m1_teacher.learner.repository import SqliteRepository
from m1_teacher.planner.planner import CurriculumPlanner, PlannerPolicy
from m1_teacher.session.engine import SessionPolicy, TeachingSessionEngine

__all__ = [
    "CONTRACT_VERSION",
    "FIXED_TIMESTAMP",
    "EVIDENCE_DIR",
    "DISCLAIMER",
    "ARTIFACT_MANIFEST_VERSION",
    "BASE_COMMIT_SHA",
    "REVIEWED_IMPLEMENTATION_COMMIT",
    "MockStudentScorer",
    "DeterministicStudentResponder",
    "build_components",
    "artifact_manifest",
    "load_student_fixture",
    "seed_prior_evidence",
    "run_student_path",
    "run_scenario",
    "build_evidence_lines",
    "write_evidence",
    "render_text",
    "main",
]

CONTRACT_VERSION = "m1a.v0"
"""Frozen contract version exercised by the demo/CLI."""

FIXED_TIMESTAMP = "2026-11-20T00:00:00Z"
"""Deterministic clock value injected into the E2E mock scorer."""

ARTIFACT_MANIFEST_VERSION = "m1a.evidence.manifest.v1"
"""Fixed manifest schema version recorded in ``e2e_summary.json``."""

BASE_COMMIT_SHA = "3e7afee077845a071cd364e93ab209cac20b2d5f"
"""Fixed worktree baseline commit recorded in the artifact manifest (never read from git)."""

REVIEWED_IMPLEMENTATION_COMMIT = "d4f10f3b32ee115759e2f9409c033b7ec8d76f6c"
"""Fixed B-PR5 implementation commit recorded in the artifact manifest.

This is a provenance *constant* for reproducibility (C5 reviewed commit).  It is never
computed from the repository, so whether/when a ``.git`` directory exists cannot change
the generated evidence bytes.
"""

EVIDENCE_DIR = Path("docs/m1a_evidence")
DEFAULT_MAX_TURNS = 10
DEFAULT_PAUSE_AFTER_TURNS = 5
"""Turn budget of the E2E path; pause/restart happens at turn 5."""

SEED_PREREQUISITE_THRESHOLD = 0.25
"""Planner prerequisite threshold used by the synthetic E2E seed (MOCK).

Two seeded CORRECT observations per known node produce mastery 0.30 with the
frozen heuristic (0.2 then 0.2*1/2).  The default planner threshold 0.50 would
require ~7 repeated observations to represent a known prerequisite, so the E2E
demo injects an explicit, documented PlannerPolicy constant instead.  This is a
simulator constant for the demonstration, not a calibrated learner model.
"""

DISCLAIMER = (
    "offline synthetic only, not real teaching effect. "
    "M1-A is an offline deterministic teaching-loop prototype over synthetic "
    "CC0-1.0 fixtures; nothing here measures or claims real learning outcomes."
)

_SEED_SESSION_ID = "session.seed.prior-evidence"
_REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Deterministic JSON helpers
# ---------------------------------------------------------------------------
def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _repo_relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(_REPO_ROOT.resolve()))
    except ValueError:  # pragma: no cover - defensive
        return str(path)


def artifact_manifest() -> dict[str, str]:
    """Fixed evidence-provenance manifest for ``e2e_summary.json``.

    Reproducibility contract (P1-1 fix): the summary must be a pure function of the
    content tree.  It therefore contains **no wall-clock timestamp and no git
    state**: ``generated_at`` is the fixed deterministic timestamp, while
    ``base_sha`` / ``implementation_commit`` are fixed provenance *constants*.
    Regenerating on the same tree — with or without ``.git``, on any date —
    produces byte-identical summary bytes.
    """

    return {
        "manifest_version": ARTIFACT_MANIFEST_VERSION,
        "generated_at": FIXED_TIMESTAMP,
        "base_sha": BASE_COMMIT_SHA,
        "implementation_commit": REVIEWED_IMPLEMENTATION_COMMIT,
        "provenance_note": (
            "fixed artifact manifest: no wall-clock timestamp and no git state are read; "
            "the same content tree regenerates byte-identical summary bytes (with or "
            "without .git)"
        ),
    }


# ---------------------------------------------------------------------------
# Domain / student fixtures
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Components:
    """Frozen PR1-PR4 components wired for one E2E run."""

    fixtures_root: Path
    adapter: CFBinarySearchDomainAdapter
    graph: KnowledgeGraph
    objective: LearningObjective


def build_components(fixtures_root: str | Path | None = None) -> Components:
    """Load and validate the CF binary-search domain (teacher-visible only)."""

    root = (
        Path(fixtures_root).expanduser().resolve()
        if fixtures_root is not None
        else Path(default_fixtures_root())
    )
    adapter = CFBinarySearchDomainAdapter(root)
    adapter.validate()
    graph = KnowledgeGraph(adapter.knowledge_nodes(), adapter.prerequisite_edges())
    objectives = adapter.objectives()
    if not objectives:
        raise RuntimeError(f"domain {adapter.domain_id!r} declares no learning objective")
    return Components(
        fixtures_root=root,
        adapter=adapter,
        graph=graph,
        objective=objectives[0],
    )


def load_student_fixture(fixtures_root: str | Path, student: str) -> dict[str, Any]:
    """Load one synthetic student fixture (``student_a`` / ``student_b``)."""

    key = student if student.startswith("student_") else f"student_{student}"
    path = Path(fixtures_root) / "students" / f"{key}.json"
    if not path.is_file():
        raise FileNotFoundError(f"student fixture not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("synthetic") is not True or payload.get("license") != "CC0-1.0":
        raise ValueError(f"student fixture {path} is not synthetic/CC0-1.0")
    return payload


def _scripted_status(student: dict[str, Any], item_id: str) -> str:
    """Deterministic outcome the synthetic student fixture scripts for an item."""

    script = student.get("response_script") or {}
    entry = (script.get("per_item") or {}).get(item_id)
    if isinstance(entry, dict) and isinstance(entry.get("status"), str):
        status = entry["status"]
    else:
        default = script.get("default") or {}
        status = default.get("kind", "CORRECT")
    if status not in ASSESSMENT_STATUS_VALUES:
        raise ValueError(f"student script for {item_id} has invalid status {status!r}")
    return status


# ---------------------------------------------------------------------------
# MOCK assessment scorer + deterministic responder
# ---------------------------------------------------------------------------
class MockStudentScorer:
    """MOCK assessment scorer driven by the synthetic student's response script.

    This test/demo double implements the ``AssessmentScorer`` protocol using the
    ``response_script`` embedded in ``fixtures/m1_teacher/students/*.json``.  It
    **does not read or need** the hidden scoring specifications and is
    labelled ``MOCK``: outcomes are synthetic scripted assumptions, not real
    learner performance.  The real independent scorer is exercised separately
    (``test_e2e_resume_idempotency.py``) for ``EVAL_ERROR`` isolation.
    """

    scorer_id = "m1a.mock.student.script.v0"
    evidence_class = "MOCK"

    def __init__(self, student: dict[str, Any], *, timestamp: str = FIXED_TIMESTAMP) -> None:
        if student.get("synthetic") is not True:
            raise ValueError("MockStudentScorer expects a synthetic student fixture")
        self._student = student
        self._timestamp = timestamp
        self.calls: list[tuple[str, str]] = []

    def score(
        self,
        item: AssessmentItem,
        learner_id: str,
        response: str | dict,
        *,
        result_id: str | None = None,
    ) -> AssessmentResult:
        status = _scripted_status(self._student, item.item_id)
        script = (self._student.get("response_script") or {}).get("per_item") or {}
        entry = script.get(item.item_id) if isinstance(script, dict) else None
        if status == "CORRECT":
            score: float | None = float(item.max_score)
            failure_reason = ""
        elif status == "INCORRECT":
            score = 0.0
            failure_reason = str((entry or {}).get("error") or f"SCRIPTED_INCORRECT:{item.item_id}")
        elif status == "PARTIAL":
            fraction = float((entry or {}).get("score", 0.5))
            score = round(float(item.max_score) * fraction, 6)
            failure_reason = f"SCRIPTED_PARTIAL:{item.item_id}"
        else:  # NEEDS_REVIEW
            score = None
            failure_reason = f"SCRIPTED_{status}:{item.item_id}"
        self.calls.append((item.item_id, status))
        rid = result_id or f"mock-result:{item.item_id}:{len(self.calls):03d}"
        return AssessmentResult(
            result_id=rid,
            item_id=item.item_id,
            learner_id=learner_id,
            status=status,
            score=score,
            max_score=float(item.max_score),
            scorer_id=self.scorer_id,
            failure_reason=failure_reason,
            evidence_refs=[f"item:{item.item_id}"],
            created_at=self._timestamp,
        )


class DeterministicStudentResponder:
    """Deterministic synthetic responder (content is irrelevant for the MOCK scorer)."""

    def __call__(self, item: AssessmentItem, session: SessionState) -> str:
        if item.item_type == "MCQ":
            return "A"
        if item.item_type == "CODE":
            return "def solution(*args):\n    raise NotImplementedError  # mock response\n"
        return "synthetic mock answer text that is long enough to be plausible."


# ---------------------------------------------------------------------------
# Prior-evidence seeding (evidence-driven, MOCK)
# ---------------------------------------------------------------------------
def _student_traits(student: dict[str, Any]) -> tuple[list[str], list[str]]:
    traits = student.get("expected_traits") or {}
    known_roots: list[str] = []
    weak: list[str] = []
    for node_id in traits.get("known_nodes") or []:
        if type(node_id) is str and node_id not in known_roots:
            known_roots.append(node_id)
    for field in ("weak_nodes", "missing_prerequisites"):
        for node_id in traits.get(field) or []:
            if type(node_id) is str and node_id not in weak:
                weak.append(node_id)
    return known_roots, weak


def _seed_schedule(components: Components, student: dict[str, Any]) -> list[tuple[str, str, str]]:
    """Derive a deterministic (item_id, status, rationale) seed schedule.

    Known nodes (and their HARD+SOFT prerequisite closure) get two CORRECT
    observations each; weak/missing-prerequisite nodes get one INCORRECT
    observation so the planner sees a remediation need without a "stuck node"
    reassessment streak.
    """

    adapter, graph = components.adapter, components.graph
    known_roots, weak = _student_traits(student)
    weak_set = set(weak)
    known: set[str] = set()
    for node_id in known_roots:
        known.add(node_id)
        known |= graph.prerequisite_closure([node_id], kinds=("HARD", "SOFT"))
    known -= weak_set
    items_by_node: dict[str, list[AssessmentItem]] = {
        node_id: sorted(adapter.assessment_items(node_id), key=lambda item: item.item_id)
        for node_id in known | weak_set
    }
    schedule: list[tuple[str, str, str]] = []
    for node_id in sorted(known):
        items = items_by_node.get(node_id) or []
        if not items:
            continue
        selected = items[:2] if len(items) >= 2 else items
        repetitions = 1 if len(selected) >= 2 else 2
        for item in selected:
            for _ in range(repetitions):
                schedule.append(
                    (item.item_id, "CORRECT", f"known prerequisite/target evidence: {node_id}")
                )
    for node_id in sorted(weak_set):
        items = items_by_node.get(node_id) or []
        if not items:
            continue
        incorrect_items = [
            item for item in items if _scripted_status(student, item.item_id) == "INCORRECT"
        ]
        chosen = (incorrect_items or items)[0]
        schedule.append(
            (chosen.item_id, "INCORRECT", f"weak/missing prerequisite evidence: {node_id}")
        )
    return schedule


def seed_prior_evidence(
    repository: SqliteRepository,
    components: Components,
    student: dict[str, Any],
    *,
    learner_id: str,
) -> tuple[LearnerSnapshot, list[dict[str, Any]]]:
    """Seed synthetic prior evidence through the real history/model pipeline.

    The prior state is therefore *evidence-driven* (the materialised snapshot is
    rebuildable from the seeded ``ASSESSED`` events), but the evidence itself is
    MOCK: scripted synthetic student outcomes, not real learner behaviour.
    """

    scorer = MockStudentScorer(student)
    history = LearningHistory(repository)
    items = {item.item_id: item for item in components.adapter.assessment_items()}
    submissions: list[dict[str, Any]] = []
    for index, (item_id, expected_status, rationale) in enumerate(
        _seed_schedule(components, student)
    ):
        item = items.get(item_id)
        if item is None:  # pragma: no cover - schedule derives ids from the adapter
            raise RuntimeError(f"seed schedule references unknown item {item_id!r}")
        result = scorer.score(
            item,
            learner_id,
            "seed-response",
            result_id=f"m1a.seed.{learner_id}.{index:03d}",
        )
        if result.status != expected_status:  # pragma: no cover - script consistency
            raise RuntimeError(
                f"seed schedule expected {expected_status} for {item_id}, got {result.status}"
            )
        history.apply_assessment(learner_id, _SEED_SESSION_ID, item, result)
        submissions.append(
            {
                "item_id": item_id,
                "status": result.status,
                "score": result.score,
                "result_id": result.result_id,
                "rationale": rationale,
            }
        )
    snapshot = repository.get_snapshot(learner_id)
    if snapshot is None:  # pragma: no cover - seeding always writes a snapshot
        raise RuntimeError("seeded prior evidence produced no snapshot")
    return snapshot, submissions


# ---------------------------------------------------------------------------
# One E2E student path
# ---------------------------------------------------------------------------
def _mastery_map(snapshot: LearnerSnapshot | None) -> dict[str, dict[str, Any]]:
    if snapshot is None:
        return {}
    return {
        node_id: {
            "value": round(estimate.value, 6),
            "confidence": round(estimate.confidence, 6),
            "evidence_count": estimate.evidence_count,
        }
        for node_id, estimate in sorted(snapshot.masteries.items())
    }


def _plan_projection(plan: CurriculumPlan) -> dict[str, Any]:
    return {
        "plan_id": plan.plan_id,
        "policy_version": plan.policy_version,
        "steps": [
            {
                "ordinal": step.ordinal,
                "phase": step.phase,
                "action_kind": step.action_kind,
                "node_ids": list(step.node_ids),
                "item_id": step.item_id,
                "reason_code": step.rationale.code if step.rationale else None,
                "reason_detail": step.rationale.detail if step.rationale else "",
            }
            for step in plan.steps
        ],
    }


def _diagnosis_projection(diagnosis: DiagnosisResult) -> dict[str, Any]:
    return {
        "diagnosis_id": diagnosis.diagnosis_id,
        "status": diagnosis.status,
        "target_node_id": diagnosis.target_node_id,
        "selected_item_id": diagnosis.selected_item_id,
        "hypothesis": diagnosis.hypothesis,
        "reason_code": diagnosis.reason.code if diagnosis.reason else None,
        "reason_detail": diagnosis.reason.detail if diagnosis.reason else "",
        "policy_version": diagnosis.reason.policy_version if diagnosis.reason else None,
    }


def _action_projection(event_payload: dict[str, Any]) -> dict[str, Any]:
    raw = event_payload.get("action") or {}
    reason = raw.get("reason") or {}
    return {
        "turn_index": event_payload.get("turn_index"),
        "phase": event_payload.get("phase"),
        "action_id": raw.get("action_id"),
        "action_kind": raw.get("kind"),
        "node_ids": list(raw.get("node_ids") or []),
        "item_id": raw.get("item_id"),
        "reason_code": reason.get("code"),
        "reason_detail": reason.get("detail") or "",
    }


def _make_engine(
    components: Components,
    repository: SqliteRepository,
    scorer: MockStudentScorer,
) -> tuple[TeachingSessionEngine, LearningHistory]:
    planner = CurriculumPlanner(
        components.adapter,
        components.graph,
        PlannerPolicy(prerequisite_mastery_threshold=SEED_PREREQUISITE_THRESHOLD),
    )
    diagnostic = DiagnosticEngine(components.adapter, components.graph)
    history = LearningHistory(repository)
    engine = TeachingSessionEngine(
        components.adapter,
        components.graph,
        repository,
        history=history,
        diagnostic=diagnostic,
        planner=planner,
        scorer=scorer,
        policy=SessionPolicy(),
    )
    return engine, history


def _run_until_turn(
    engine: TeachingSessionEngine,
    session_id: str,
    responder: DeterministicStudentResponder,
    turn_limit: int,
) -> SessionState:
    return engine.run_until_goal(session_id, max_turns=turn_limit, responder=responder)


def _first_diagnosis(repository: SqliteRepository, learner_id: str) -> DiagnosisResult:
    for event in repository.list_events(learner_id):
        if event.event_type == "DIAGNOSIS_COMPLETED":
            payload = event.payload.get("diagnosis")
            if isinstance(payload, dict):
                return DiagnosisResult.from_dict(payload)
    raise RuntimeError("session produced no DIAGNOSIS_COMPLETED event")


def _event_plan_id(repository: SqliteRepository, learner_id: str) -> str:
    for event in repository.list_events(learner_id):
        if event.event_type == "PLAN_CREATED":
            plan_id = event.payload.get("plan_id")
            if isinstance(plan_id, str):
                return plan_id
    raise RuntimeError("session produced no PLAN_CREATED event")


def run_student_path(
    student: str,
    *,
    db_path: str | Path,
    fixtures_root: str | Path | None = None,
    max_turns: int = DEFAULT_MAX_TURNS,
    pause_after_turns: int = DEFAULT_PAUSE_AFTER_TURNS,
) -> dict[str, Any]:
    """Run one deterministic Student-A/B E2E path with pause/restart recovery."""

    components = build_components(fixtures_root)
    student_fixture = load_student_fixture(components.fixtures_root, student)
    learner_id = f"m1a.learner.{student_fixture['student_id']}"
    goal = LearnerGoal(
        goal_id=f"goal.{learner_id}.{components.objective.objective_id}",
        learner_id=learner_id,
        objective_id=components.objective.objective_id,
        created_at=FIXED_TIMESTAMP,
    )

    repository = SqliteRepository(db_path)
    try:
        snapshot_before, seed_submissions = seed_prior_evidence(
            repository, components, student_fixture, learner_id=learner_id
        )
        history = LearningHistory(repository)
        verify_seed_rebuild = history.verify_rebuild(learner_id)

        scorer = MockStudentScorer(student_fixture)
        engine, _history = _make_engine(components, repository, scorer)
        state = engine.start_session(learner_id, goal, components.objective)
        session_id = state.session_id
        first_action = engine.current_action(session_id)
        diagnosis = _first_diagnosis(repository, learner_id)

        # Plan used by the session, projected from the deterministic planner.
        initial_plan = engine_plan(
            components, goal, snapshot_before, repository.list_events(learner_id)
        )
        recorded_plan_id = _event_plan_id(repository, learner_id)
        if initial_plan.plan_id != recorded_plan_id:  # pragma: no cover - contract check
            raise RuntimeError(
                "deterministic planner replay disagrees with the recorded PLAN_CREATED id: "
                f"{initial_plan.plan_id!r} != {recorded_plan_id!r}"
            )

        responder = DeterministicStudentResponder()
        phase1_state = _run_until_turn(
            engine, session_id, responder, min(pause_after_turns, max_turns)
        )
        phase1_snapshot = repository.get_snapshot(learner_id)
        pre_pause_plan = engine_plan(
            components, goal, phase1_snapshot, repository.list_events(learner_id)
        )
        paused = engine.pause_session(session_id)
        paused_snapshot = repository.get_snapshot(learner_id)
        paused_plan = engine_plan(
            components, goal, paused_snapshot, repository.list_events(learner_id)
        )
        verify_before_restart = _history.verify_rebuild(learner_id)
    finally:
        repository.close()

    # -- restart: a brand-new engine + new connection on the same SQLite file ----
    repository = SqliteRepository(db_path)
    try:
        scorer = MockStudentScorer(student_fixture)
        engine2, history2 = _make_engine(components, repository, scorer)
        resumed = engine2.resume_session(session_id)
        resumed_snapshot = repository.get_snapshot(learner_id)
        resumed_plan = engine_plan(
            components, goal, resumed_snapshot, repository.list_events(learner_id)
        )
        interrupt_resume = {
            "paused_at_turn": paused.turn_index,
            "pause_phase": phase1_state.phase,
            "resumed_phase": resumed.phase,
            "pending_equal": resumed.pending_item_id == phase1_state.pending_item_id,
            "snapshot_equal": (
                resumed_snapshot is not None
                and phase1_snapshot is not None
                and resumed_snapshot.to_dict() == phase1_snapshot.to_dict()
            ),
            "plan_equal": pre_pause_plan.to_dict() == resumed_plan.to_dict(),
            "paused_plan_equal": paused_plan.to_dict() == resumed_plan.to_dict(),
            "verify_rebuild_before_restart": verify_before_restart,
            "verify_rebuild_after_restart": history2.verify_rebuild(learner_id),
        }

        responder = DeterministicStudentResponder()
        final_state = _run_until_turn(engine2, session_id, responder, max_turns)
        final_snapshot = repository.get_snapshot(learner_id)
        events = repository.list_events(learner_id)
        session_events = [event for event in events if event.session_id == session_id]
        actions = [
            _action_projection(event.payload)
            for event in session_events
            if event.event_type == "ACTION_TAKEN"
        ]
        assessments: list[dict[str, Any]] = []
        for event in session_events:
            if event.event_type != "ASSESSED":
                continue
            raw_result = event.payload.get("result")
            if not isinstance(raw_result, dict):  # pragma: no cover - log invariant
                continue
            result = AssessmentResult.from_dict(raw_result)
            assessments.append(
                {
                    "item_id": result.item_id,
                    "status": result.status,
                    "score": result.score,
                    "result_id": result.result_id,
                    "scorer_id": result.scorer_id,
                    "failure_reason": result.failure_reason,
                    "created_at_fixed": result.created_at,
                }
            )
        verify_rebuild = history2.verify_rebuild(learner_id)
        plan_after = engine_plan(components, goal, final_snapshot, events)
        next_recommendation = (
            _plan_projection(plan_after)
            if plan_after.steps
            else {"plan_id": plan_after.plan_id, "steps": []}
        )
        phase_sequence = engine2.phase_history(session_id)
        summary: dict[str, Any] = {
            "schema": "m1a.e2e_student.v0",
            "student_fixture": student_fixture["student_id"],
            "display_name": student_fixture.get("display_name", ""),
            "learner_id": learner_id,
            "goal_id": goal.goal_id,
            "objective_id": components.objective.objective_id,
            "session_id": session_id,
            "fixed_timestamp": FIXED_TIMESTAMP,
            "evidence_classification": {
                "seeded_prior_evidence": "MOCK",
                "student_responses_and_outcomes": "MOCK",
                "state_machine_model_and_ids": "DETERMINISTIC",
                "real_teaching_effect": "NOT_VERIFIED",
            },
            "seed": {
                "known_prerequisite_nodes": sorted(
                    {
                        node_id
                        for submission in seed_submissions
                        for node_id in _submission_nodes(components, submission["item_id"])
                    }
                ),
                "submissions": seed_submissions,
                "mastery_before": _mastery_map(snapshot_before),
                "verify_rebuild": verify_seed_rebuild,
            },
            "diagnosis": _diagnosis_projection(diagnosis),
            "first_action": _action_projection(
                {
                    "turn_index": 0,
                    "phase": state.phase,
                    "action": first_action.to_dict(),
                }
            ),
            "initial_plan": _plan_projection(initial_plan),
            "interrupt_resume": interrupt_resume,
            "actions": actions,
            "assessments": assessments,
            "assessment_status_counts": _status_counts(assessments),
            "phase_sequence": phase_sequence,
            "final": {
                "phase": final_state.phase,
                "turn_index": final_state.turn_index,
                "pending_item_id": final_state.pending_item_id,
            },
            "mastery_after": _mastery_map(final_snapshot),
            "next_recommendation": next_recommendation,
            "verify_rebuild": verify_rebuild,
            # B-PR4 additive replay markers (TURN_ADVANCED) are engine-internal
            # acknowledgements; the frozen M1-A demo summary keeps its historical
            # event_count/hash semantics (default output is byte-identical).
            "event_count": len(
                [
                    event
                    for event in session_events
                    if event.event_type != "TURN_ADVANCED"
                ]
            ),
            "_session_events": session_events,
        }
        return summary
    finally:
        repository.close()


def _submission_nodes(components: Components, item_id: str) -> list[str]:
    for item in components.adapter.assessment_items():
        if item.item_id == item_id:
            return list(item.node_ids)
    return []


def _public_scenario(scenario: dict[str, Any]) -> dict[str, Any]:
    """Return a JSON-safe copy of a scenario (drops private ``_``-prefixed keys)."""

    def clean(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: clean(item) for key, item in value.items() if not key.startswith("_")}
        if isinstance(value, list):
            return [clean(item) for item in value]
        return value

    return clean(scenario)


def _status_counts(assessments: Sequence[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for assessment in assessments:
        status = str(assessment.get("status"))
        counts[status] = counts.get(status, 0) + 1
    return {status: counts[status] for status in sorted(counts)}


def engine_plan(
    components: Components,
    goal: LearnerGoal,
    snapshot: LearnerSnapshot | None,
    history: list[Any],
) -> CurriculumPlan:
    """Recompute the deterministic plan for a snapshot/history (pure read)."""

    if snapshot is None:
        raise RuntimeError("engine_plan requires a materialised snapshot")
    planner = CurriculumPlanner(
        components.adapter,
        components.graph,
        PlannerPolicy(prerequisite_mastery_threshold=SEED_PREREQUISITE_THRESHOLD),
    )
    return planner.plan(goal, components.objective, snapshot, history=list(history))


# ---------------------------------------------------------------------------
# Scenario: both students, same objective
# ---------------------------------------------------------------------------
def _path_differences(summaries: dict[str, dict[str, Any]]) -> dict[str, bool]:
    first_a = summaries["a"]["first_action"]
    first_b = summaries["b"]["first_action"]

    def action_key(action: dict[str, Any]) -> tuple[Any, Any, tuple[str, ...]]:
        return (
            action.get("action_kind"),
            action.get("item_id"),
            tuple(action.get("node_ids") or []),
        )

    def plan_key(summary: dict[str, Any]) -> list[tuple[Any, tuple[str, ...], Any]]:
        return [
            (step.get("action_kind"), tuple(step.get("node_ids") or []), step.get("item_id"))
            for step in summary["initial_plan"]["steps"]
        ]

    def recommendation_key(summary: dict[str, Any]) -> list[tuple[Any, tuple[str, ...], Any]]:
        return [
            (step.get("action_kind"), tuple(step.get("node_ids") or []), step.get("item_id"))
            for step in summary["next_recommendation"]["steps"][:3]
        ]

    return {
        "first_action_differs": action_key(first_a) != action_key(first_b),
        "initial_plan_differs": plan_key(summaries["a"]) != plan_key(summaries["b"]),
        "phase_sequence_differs": summaries["a"]["phase_sequence"]
        != summaries["b"]["phase_sequence"],
        "final_mastery_differs": summaries["a"]["mastery_after"] != summaries["b"]["mastery_after"],
        "next_recommendation_differs": recommendation_key(summaries["a"])
        != recommendation_key(summaries["b"]),
    }


def _prerequisite_before_target(summary: dict[str, Any]) -> bool:
    """True when prerequisite remediation precedes teaching the objective target."""

    target_nodes = {
        "cf.search.binary",
        "cf.search.boundary",
        "cf.search.lower_upper",
        "cf.complexity.log",
    }
    remediation_index: int | None = None
    target_index: int | None = None
    for step in summary["initial_plan"]["steps"]:
        nodes = set(step.get("node_ids") or [])
        if (
            remediation_index is None
            and step.get("action_kind") in {"RETEACH", "PRACTICE", "REASSESS"}
            and nodes & {"cf.sort.sortedness"}
        ):
            remediation_index = step["ordinal"]
        if (
            target_index is None
            and step.get("action_kind") in {"EXPLAIN", "RETEACH", "PRACTICE", "DIAGNOSE"}
            and nodes & target_nodes
        ):
            target_index = step["ordinal"]
    if remediation_index is None:
        return False
    return target_index is None or remediation_index < target_index


def run_scenario(
    *,
    fixtures_root: str | Path | None = None,
    max_turns: int = DEFAULT_MAX_TURNS,
    pause_after_turns: int = DEFAULT_PAUSE_AFTER_TURNS,
) -> dict[str, Any]:
    """Run both synthetic students through the E2E path (deterministic)."""

    summaries: dict[str, dict[str, Any]] = {}
    with tempfile.TemporaryDirectory(prefix="m1a_demo_") as tmp:
        db_path = Path(tmp) / "m1a_demo.sqlite"
        for student in ("a", "b"):
            summaries[student] = run_student_path(
                student,
                db_path=db_path,
                fixtures_root=fixtures_root,
                max_turns=max_turns,
                pause_after_turns=pause_after_turns,
            )
    path_differences = _path_differences(summaries)
    scenario: dict[str, Any] = {
        "schema": "m1a.e2e_scenario.v0",
        "contract_version": CONTRACT_VERSION,
        "command": (
            'cd /root/at-m1a-mvp && "/root/Autonomous Teacher/.venv/bin/python" -m m1_teacher.demo'
        ),
        "artifact_manifest": artifact_manifest(),
        "fixed_timestamp": FIXED_TIMESTAMP,
        "max_turns": max_turns,
        "pause_after_turns": pause_after_turns,
        "students": summaries,
        "path_differences": path_differences,
        "policy_checks": {
            "prerequisite_remediation_before_target": _prerequisite_before_target(summaries["b"]),
            "student_a_has_no_prerequisite_remediation": not any(
                step["action_kind"] in {"RETEACH", "REASSESS"}
                for step in summaries["a"]["initial_plan"]["steps"]
            ),
            "interrupt_resume_state_equal": all(
                summaries[key]["interrupt_resume"][field]
                for key in ("a", "b")
                for field in ("snapshot_equal", "plan_equal", "pending_equal")
            ),
            "history_verify_rebuild": all(summaries[key]["verify_rebuild"] for key in ("a", "b")),
        },
        "classification": {
            "MOCK": "synthetic student fixtures, scripted outcomes and seeded prior evidence",
            "DETERMINISTIC": "state machine, learner model arithmetic, ids, replay verification",
            "HUMAN_REVIEWED": "NOT_RUN in this PR (independent review follows)",
            "NOT_VERIFIED": "real teaching effectiveness, real learner outcomes",
        },
        "not_run": [
            "real learner data or real teaching effect measurement (offline synthetic only)",
            "network/LLM provider integration (out of scope for M1-A)",
            "human expert review of teaching quality (independent review follows this PR)",
        ],
        "disclaimer": DISCLAIMER,
    }
    return scenario


# ---------------------------------------------------------------------------
# Evidence projection (deterministic JSONL; no wall-clock fields, no hidden data)
# ---------------------------------------------------------------------------
def _project_session_event(event: Any) -> dict[str, Any] | None:
    """Project one session-history event into deterministic evidence fields.

    Wall-clock event timestamps are deliberately dropped; every remaining field
    is content-derived (ids, phases, statuses, mastery arithmetic).
    """

    payload = event.payload
    projected: dict[str, Any] = {
        "seq": event.seq,
        "event_type": event.event_type,
    }
    if event.event_type == "SESSION_STARTED":
        projected.update(
            {
                "event": "session_started",
                "phase": payload.get("phase"),
                "snapshot_revision": payload.get("snapshot_revision"),
                "session_policy_version": payload.get("session_policy_version"),
            }
        )
    elif event.event_type == "PLAN_CREATED":
        projected.update(
            {
                "event": "plan_created",
                "plan_id": payload.get("plan_id"),
                "step_count": payload.get("step_count"),
                "policy_version": payload.get("policy_version"),
            }
        )
    elif event.event_type == "DIAGNOSIS_COMPLETED":
        raw = payload.get("diagnosis") or {}
        projected.update(
            {
                "event": "diagnosis_step",
                "phase": "DIAGNOSE",
                "status": raw.get("status"),
                "target_node_id": raw.get("target_node_id"),
                "selected_item_id": raw.get("selected_item_id"),
                "reason_code": (raw.get("reason") or {}).get("code"),
            }
        )
    elif event.event_type == "ACTION_TAKEN":
        raw_action = payload.get("action") or {}
        reason = raw_action.get("reason") or {}
        projected.update(
            {
                "event": "action",
                "phase": payload.get("phase"),
                "turn_index": payload.get("turn_index"),
                "action_id": raw_action.get("action_id"),
                "action_kind": raw_action.get("kind"),
                "node_ids": list(raw_action.get("node_ids") or []),
                "item_id": raw_action.get("item_id"),
                "reason_code": reason.get("code"),
                "reason_detail": reason.get("detail") or "",
                "snapshot_revision": payload.get("snapshot_revision"),
            }
        )
    elif event.event_type == "RESPONSE_SUBMITTED":
        projected.update(
            {
                "event": "response_submitted",
                "phase": "ASSESS",
                "item_id": payload.get("item_id"),
                "result_id": payload.get("result_id"),
                "response_digest": payload.get("response_digest"),
                "attempt": payload.get("attempt"),
            }
        )
    elif event.event_type == "ASSESSED":
        raw_result = payload.get("result") or {}
        projected.update(
            {
                "event": "assessed",
                "phase": "ASSESS",
                "item_id": payload.get("item_id"),
                "status": payload.get("status"),
                "score": raw_result.get("score"),
                "max_score": raw_result.get("max_score"),
                "result_id": payload.get("result_id"),
                "scorer_id": raw_result.get("scorer_id"),
                "failure_reason": raw_result.get("failure_reason"),
            }
        )
    elif event.event_type == "MASTERY_UPDATED":
        snapshot = payload.get("snapshot") or {}
        masteries = snapshot.get("masteries") or {}
        projected.update(
            {
                "event": "mastery_updated",
                "phase": "UPDATE",
                "result_id": payload.get("result_id"),
                "status": payload.get("status"),
                "applied": payload.get("applied"),
                "masteries": {
                    node_id: {
                        "value": round(float(estimate.get("value", 0.0)), 6),
                        "confidence": round(float(estimate.get("confidence", 0.0)), 6),
                        "evidence_count": int(estimate.get("evidence_count", 0)),
                    }
                    for node_id, estimate in sorted(masteries.items())
                },
            }
        )
    elif event.event_type == "SESSION_PAUSED":
        projected.update(
            {
                "event": "paused",
                "phase": "PAUSED",
                "previous_phase": payload.get("previous_phase"),
                "pending_item_id": payload.get("pending_item_id"),
                "turn_index": payload.get("turn_index"),
            }
        )
    elif event.event_type == "SESSION_RESUMED":
        projected.update(
            {
                "event": "resumed",
                "phase": payload.get("phase"),
            }
        )
    elif event.event_type == "GOAL_COMPLETED":
        projected.update(
            {
                "event": "goal_completed",
                "phase": "COMPLETE",
                "objective_id": payload.get("objective_id"),
                "reason_code": (payload.get("reason") or {}).get("code"),
            }
        )
    elif event.event_type == "ERROR":
        projected.update(
            {
                "event": "error",
                "phase": "ASSESS",
                "status": payload.get("status"),
                "item_id": payload.get("item_id"),
                "result_id": payload.get("result_id"),
                "failure_reason": payload.get("failure_reason"),
                "retry_exhausted": payload.get("retry_exhausted"),
                "mastery_unchanged": payload.get("mastery_unchanged"),
            }
        )
    else:  # pragma: no cover - frozen history event enum is closed
        return None
    return projected


def build_evidence_lines(summary: dict[str, Any]) -> list[dict[str, Any]]:
    """Project one deterministic evidence JSONL file for a student path.

    The JSONL is an ordered projection of the *real* session events (DIAGNOSE ->
    TEACH/PRACTICE -> ASSESS -> UPDATE -> REVIEW, plus pause/resume), with all
    wall-clock timestamps and hidden scoring material omitted so the file is
    reproducible byte-for-byte from the fixed command.
    """

    base = {
        "schema": "m1a.evidence.v0",
        "student": summary["student_fixture"],
        "learner_id": summary["learner_id"],
        "session_id": summary["session_id"],
        "goal_id": summary["goal_id"],
        "objective_id": summary["objective_id"],
        "contract_version": CONTRACT_VERSION,
        "fixed_timestamp": FIXED_TIMESTAMP,
        "evidence_classes": ["MOCK", "DETERMINISTIC"],
    }
    lines: list[dict[str, Any]] = []
    for index, submission in enumerate(summary["seed"]["submissions"]):
        lines.append(
            {
                **base,
                "line": index,
                "event": "seeded_prior_evidence",
                "item_id": submission["item_id"],
                "status": submission["status"],
                "score": submission["score"],
                "result_id": submission["result_id"],
                "rationale": submission["rationale"],
            }
        )
    offset = len(lines)
    lines.append({**base, "line": offset, "event": "diagnosis", **summary["diagnosis"]})
    lines.append(
        {
            **base,
            "line": offset + 1,
            "event": "plan",
            **summary["initial_plan"],
        }
    )
    lines.append(
        {
            **base,
            "line": offset + 2,
            "event": "mastery_before",
            "masteries": summary["seed"]["mastery_before"],
        }
    )
    for event in summary.get("_session_events", []):
        projected = _project_session_event(event)
        if projected is None:
            continue
        lines.append({**base, "line": len(lines), **projected})
    lines.append(
        {
            **base,
            "line": len(lines),
            "event": "interrupt_resume_check",
            **summary["interrupt_resume"],
        }
    )
    lines.append(
        {
            **base,
            "line": len(lines),
            "event": "mastery_after",
            "masteries": summary["mastery_after"],
            "verify_rebuild": summary["verify_rebuild"],
            "final_phase": summary["final"]["phase"],
            "final_turn_index": summary["final"]["turn_index"],
            "phase_sequence": summary["phase_sequence"],
            "next_recommendation": summary["next_recommendation"],
        }
    )
    return lines


def _evidence_jsonl(lines: Sequence[dict[str, Any]]) -> str:
    return "".join(
        json.dumps(line, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        for line in lines
    )


def write_evidence(
    scenario: dict[str, Any],
    out_dir: str | Path = EVIDENCE_DIR,
) -> dict[str, Any]:
    """Write reproducible per-student JSONL evidence and the scenario summary."""

    root = Path(out_dir)
    if not root.is_absolute():
        root = _REPO_ROOT / root
    root.mkdir(parents=True, exist_ok=True)
    hashes: dict[str, str] = {}
    for student in ("a", "b"):
        summary = scenario["students"][student]
        text = _evidence_jsonl(build_evidence_lines(summary))
        target = root / f"e2e_student_{student}.jsonl"
        target.write_text(text, encoding="utf-8")
        hashes[f"e2e_student_{student}.jsonl"] = _sha256_text(text)
    summary_payload = _public_scenario(scenario)
    summary_payload["evidence_hashes"] = hashes
    # Fixed bare file names: the summary must not depend on where it is written.
    summary_payload["evidence_files"] = [f"e2e_student_{student}.jsonl" for student in ("a", "b")]
    summary_text = json.dumps(summary_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    summary_path = root / "e2e_summary.json"
    summary_path.write_text(summary_text, encoding="utf-8")
    hashes["e2e_summary.json"] = _sha256_text(summary_text)
    return {
        "out_dir": _repo_relative(root),
        "hashes": hashes,
        "files": [_repo_relative(root / name) for name in sorted(hashes)],
    }


# ---------------------------------------------------------------------------
# Deterministic text rendering
# ---------------------------------------------------------------------------
def _fmt_mastery(mastery: dict[str, dict[str, Any]]) -> str:
    parts = [
        f"{node}={item['value']:.2f}/{item['evidence_count']}" for node, item in mastery.items()
    ]
    return "{" + ", ".join(parts) + "}"


def render_text(scenario: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("== M1-A Offline Adaptive Teacher MVP demo (B-PR5) ==")
    lines.append(f"[contract] {CONTRACT_VERSION}; fixed_timestamp={FIXED_TIMESTAMP}")
    lines.append(f"[boundary] {DISCLAIMER}")
    lines.append("[boundary] no network / no API key / no real provider / no real learner data")
    for key in sorted(scenario["students"]):
        summary = scenario["students"][key]
        lines.append("")
        lines.append(
            f"-- Student {key.upper()}: {summary['student_fixture']} ({summary['display_name']}) --"
        )
        lines.append(
            "[seed] prior evidence (MOCK scripted outcomes): "
            f"submissions={len(summary['seed']['submissions'])} "
            f"mastery_before={_fmt_mastery(summary['seed']['mastery_before'])}"
        )
        diagnosis = summary["diagnosis"]
        lines.append(
            "[diagnose] status={status} target={target} item={item} reason={reason}".format(
                status=diagnosis["status"],
                target=diagnosis["target_node_id"],
                item=diagnosis["selected_item_id"],
                reason=diagnosis["reason_code"],
            )
        )
        plan = summary["initial_plan"]
        lines.append(f"[plan] plan_id={plan['plan_id']} steps={len(plan['steps'])}")
        for step in plan["steps"]:
            lines.append(
                "[plan] step {ordinal:02d} phase={phase} action={action} nodes={nodes} "
                "item={item} reason={reason}".format(
                    ordinal=step["ordinal"],
                    phase=step["phase"],
                    action=step["action_kind"],
                    nodes=",".join(step["node_ids"]) or "-",
                    item=step["item_id"] or "-",
                    reason=step["reason_code"],
                )
            )
        lines.append(
            "[teach] actions={actions} assessments={assessments} status_counts={counts}".format(
                actions=len(summary["actions"]),
                assessments=len(summary["assessments"]),
                counts=json.dumps(summary["assessment_status_counts"], sort_keys=True),
            )
        )
        failures = [
            assessment
            for assessment in summary["assessments"]
            if assessment["status"] not in {"CORRECT"}
        ]
        if failures:
            for failure in failures[:3]:
                lines.append(
                    "[assess] item={item} status={status} score={score} reason={reason}".format(
                        item=failure["item_id"],
                        status=failure["status"],
                        score=failure["score"],
                        reason=failure["failure_reason"],
                    )
                )
        else:
            lines.append("[assess] all observed assessments were CORRECT")
        lines.append("[phase] sequence=" + ">".join(summary["phase_sequence"]))
        lines.append("[mastery] before=" + _fmt_mastery(summary["seed"]["mastery_before"]))
        lines.append("[mastery] after=" + _fmt_mastery(summary["mastery_after"]))
        resume = summary["interrupt_resume"]
        lines.append(
            "[resume] pause_phase={p} resumed_phase={r} snapshot_equal={s} plan_equal={pl} "
            "pending_equal={pe} verify_rebuild={v}".format(
                p=resume["pause_phase"],
                r=resume["resumed_phase"],
                s=resume["snapshot_equal"],
                pl=resume["plan_equal"],
                pe=resume["pending_equal"],
                v=resume["verify_rebuild_after_restart"],
            )
        )
        recommendation = summary["next_recommendation"]
        first = recommendation["steps"][0] if recommendation["steps"] else None
        if first is None:
            lines.append("[review] next recommendation: goal complete (no further step)")
        else:
            lines.append(
                "[review] next recommendation: phase={phase} action={action} nodes={nodes} "
                "item={item} reason={reason}".format(
                    phase=first["phase"],
                    action=first["action_kind"],
                    nodes=",".join(first["node_ids"]) or "-",
                    item=first["item_id"] or "-",
                    reason=first["reason_code"],
                )
            )
        lines.append(
            f"[final] phase={summary['final']['phase']} turn={summary['final']['turn_index']} "
            f"verify_rebuild={summary['verify_rebuild']}"
        )
    differences = scenario.get("path_differences")
    lines.append("")
    if differences is not None:
        lines.append("[paths] " + json.dumps(differences, sort_keys=True))
    checks = scenario.get("policy_checks")
    if checks is not None:
        lines.append("[checks] " + json.dumps(checks, sort_keys=True))
    lines.append(
        "[evidence-class] MOCK=scripted synthetic outcomes; "
        "DETERMINISTIC=state machine/model/ids/replay; "
        "NOT_VERIFIED=real teaching effect"
    )
    lines.append("[result] offline demo PASS (no network, no API key, deterministic)")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m m1_teacher.demo",
        description=(
            "Deterministic offline M1-A teacher demo (synthetic students/evidence; "
            "no network, no API key)."
        ),
    )
    parser.add_argument(
        "--write-evidence",
        nargs="?",
        const=str(EVIDENCE_DIR),
        default=None,
        help=(
            "write reproducible JSONL evidence under docs/m1a_evidence/ (or the given directory)"
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print the scenario summary as JSON instead of the text transcript",
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=DEFAULT_MAX_TURNS,
        help=f"turn budget per student path (default: {DEFAULT_MAX_TURNS})",
    )
    parser.add_argument(
        "--pause-after-turns",
        type=int,
        default=DEFAULT_PAUSE_AFTER_TURNS,
        help=f"pause/restart turn (default: {DEFAULT_PAUSE_AFTER_TURNS})",
    )
    parser.add_argument(
        "--fixtures",
        default=None,
        help="fixtures/m1_teacher root (default: repository fixtures)",
    )
    args = parser.parse_args(argv)
    if args.max_turns < 1 or args.pause_after_turns < 1:
        print("error: --max-turns/--pause-after-turns must be >= 1", file=sys.stderr)
        return 2
    if args.pause_after_turns >= args.max_turns:
        print("error: --pause-after-turns must be < --max-turns", file=sys.stderr)
        return 2
    scenario = run_scenario(
        fixtures_root=args.fixtures,
        max_turns=args.max_turns,
        pause_after_turns=args.pause_after_turns,
    )
    if args.write_evidence is not None:
        result = write_evidence(scenario, args.write_evidence)
        scenario["evidence"] = result
        print(f"[evidence] wrote {result['out_dir']}")
        for name in result["files"]:
            print(f"[evidence] {name} sha256={result['hashes'][Path(name).name]}")
    if args.json:
        payload = _public_scenario(scenario)
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render_text(scenario))
    return 0


if __name__ == "__main__":
    sys.exit(main())
