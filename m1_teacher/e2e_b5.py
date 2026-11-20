"""B5 unified end-to-end scenario on the canonical teacher core (B-PR5, additive).

This module is the deterministic, offline B5 integration runner required by the
B-NEXT acceptance matrix:

* **CF loop (B4-01)** — two synthetic student paths (the frozen M1-A
  ``student_a``/``student_b`` response scripts) run through the canonical
  ``m1_teacher`` closed loop in one SQLite learner/event journal.
* **Interview loop (B4-02)** — two synthetic interview learners with different
  learner states (seeded evidence vs. novice), the five-stage Socratic ladder,
  ``ASK_CLARIFICATION`` for missing learner-owned project facts, the interview
  support ladder (``FULL`` never emitted), the four-dimension rubric audit, and
  a JD ``v1 -> v2`` transition (new plans only; running sessions unaffected).
* **Cross-domain continuity** — the same synthetic learner pauses a CF session,
  starts an interview session, then resumes the CF session; learner snapshot,
  global per-learner ``seq`` and the single event table stay unified and
  replay-verifiable.
* **Freshness gate (B4-03)** — EXPIRED / CONFLICT / UNAUTHORITATIVE knowledge
  and expired/conflicting/not-yet-active JD windows are rejected *before* any
  session/event write (stable ``MAP-E*`` reason codes, zero events), while a
  verified authoritative update may enter a new plan.

Everything is deterministic and offline (no wall clock, no network, no
API Key/Provider, no real resume/JD).  Student and interview outcomes are
synthetic (``MOCK``); ids/state-machine/replay are deterministic
(``DETERMINISTIC``); real teaching effect is ``NOT_VERIFIED``.

Run as::

    python -m m1_teacher.e2e_b5                 # deterministic transcript
    python -m m1_teacher.e2e_b5 --json          # machine-readable summary
    python -m m1_teacher.e2e_b5 --write-evidence  # docs/m1b_evidence/*.jsonl + summary

The evidence projection strips every wall-clock/volatile field; two runs of the
same command produce byte-identical transcript and evidence (the summary embeds
a fixed artifact manifest, never a live git HEAD or wall clock).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Sequence

from . import demo
from .assessment.interview_judge import InterviewRubricJudge
from .contracts.types import AssessmentItem, AssessmentResult, LearnerGoal
from .diagnostic.engine import DiagnosticEngine
from .domains.interview import InterviewDomainAdapter
from .knowledge.freshness import KnowledgeFreshnessService
from .knowledge.graph import KnowledgeGraph
from .learner.history import LearningHistory
from .learner.repository import SqliteRepository
from .planner.planner import CurriculumPlanner, PlannerPolicy
from .session.engine import SessionPolicy, TeachingSessionEngine
from .session.vertical import InterviewJudgeScorer, InterviewVerticalPolicy

B5_SCHEMA = "m1b.b5.e2e.v1"
EVIDENCE_SCHEMA = "m1b.b5.evidence.v0"
SUMMARY_SCHEMA = "m1b.b5.summary.v1"
ARTIFACT_MANIFEST_VERSION = "m1b.b5.evidence.manifest.v1"

FIXED_TIMESTAMP = "2026-11-20T00:00:00Z"
EVIDENCE_DIR = Path("docs/m1b_evidence")
DEFAULT_MAX_TURNS = 10
DEFAULT_PAUSE_AFTER_TURNS = 4

BASE_SHA = "3e7afee077845a071cd364e93ab209cac20b2d5f"
#: Fixed provenance constant recorded in the artifact manifest.  It must be
#: updated *only* when the evidence is regenerated from a new frozen tree; the
#: runtime never reads ``git`` (the summary must stay reproducible without
#: ``.git`` or a live HEAD).
IMPLEMENTATION_COMMIT = "e2b6e85d8939b2411b2b6c6cc26538014c6f57e3"

CF_STUDENTS = ("a", "b")
CROSS_DOMAIN_LEARNER = "b5.cross_domain.learner"
INTERVIEW_LEARNER_A = "b5.interview.learner_a"
INTERVIEW_LEARNER_B = "b5.interview.learner_b"

QUESTION_REC = "interview.item.q-rec-001"
QUESTION_ENG = "interview.item.q-eng-001"
JD_ID = "jd:rec"
JD_NOW_V1 = "2026-07-01T00:00:00Z"
JD_NOW_V2 = "2026-10-15T00:00:00Z"

BOUNDARY: dict[str, str] = {
    "scope": "offline synthetic only, not real teaching effect",
    "evidence_classes": "MOCK + DETERMINISTIC; real teaching effect NOT_VERIFIED",
    "network": "NONE",
    "real_resume_or_jd": "NONE (synthetic interview/JD fixtures only)",
    "provider_or_live_gate": "NONE",
    "hidden_scoring": "SCORER_ONLY (rubric audit exposes dimension names + spec digests only)",
}

_VOLATILE_KEYS = frozenset(
    {
        "created_at",
        "updated_at",
        "timestamp",
        "session_version",
        "trace_path",
        "canonical_response",
        "response",
    }
)
_LEARNER_RESPONSE_KEYS = frozenset({"canonical_response", "response"})


# ---------------------------------------------------------------------------
# Small deterministic helpers
# ---------------------------------------------------------------------------
def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _strip_volatile(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _strip_volatile(item) for key, item in value.items() if key not in _VOLATILE_KEYS
        }
    if isinstance(value, list):
        return [_strip_volatile(item) for item in value]
    return value


def _round_mastery(masteries: dict[str, Any]) -> dict[str, dict[str, Any]]:
    def _field(entry: Any, name: str) -> Any:
        if isinstance(entry, dict):
            return entry[name]
        return getattr(entry, name)

    return {
        node_id: {
            "value": round(float(_field(entry, "value")), 6),
            "confidence": round(float(_field(entry, "confidence")), 6),
            "evidence_count": int(_field(entry, "evidence_count")),
        }
        for node_id, entry in sorted(masteries.items())
    }


def _json_dump(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _public(value: Any) -> Any:
    """Drop arbitrary private ``_key`` containers from a summary."""

    if isinstance(value, dict):
        return {key: _public(item) for key, item in value.items() if not key.startswith("_")}
    if isinstance(value, list):
        return [_public(item) for item in value]
    return value


# ---------------------------------------------------------------------------
# Evidence projection
# ---------------------------------------------------------------------------
def _project_payload(event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Project one canonical event payload into a deterministic evidence record.

    Learner response texts and wall-clock fields are deliberately not copied;
    the projection keeps the auditable decision metadata only.
    """

    payload = dict(payload or {})
    if event_type == "SESSION_STARTED":
        vertical = payload.get("vertical")
        return {
            "goal_id": payload.get("goal_id"),
            "objective_id": payload.get("objective_id"),
            "phase": payload.get("phase"),
            "snapshot_revision": payload.get("snapshot_revision"),
            "session_policy_version": payload.get("session_policy_version"),
            "vertical": (
                None
                if not isinstance(vertical, dict)
                else {
                    key: vertical.get(key)
                    for key in (
                        "domain_id",
                        "policy_version",
                        "question_id",
                        "jd_id",
                        "jd_version",
                        "jd_ref",
                        "requires_project_facts",
                        "knowledge_refs",
                        "interview_hint_ladder",
                        "full_solution_enabled",
                    )
                }
            ),
        }
    if event_type == "PLAN_CREATED":
        vertical = payload.get("vertical")
        return {
            "plan_id": payload.get("plan_id"),
            "objective_id": payload.get("objective_id"),
            "step_count": payload.get("step_count"),
            "policy_version": payload.get("policy_version"),
            "vertical": (
                None
                if not isinstance(vertical, dict)
                else {
                    key: vertical.get(key)
                    for key in (
                        "domain_id",
                        "policy_version",
                        "jd_ref",
                        "knowledge_refs",
                        "question_id",
                    )
                }
            ),
        }
    if event_type == "DIAGNOSIS_COMPLETED":
        return {
            key: payload.get(key)
            for key in (
                "diagnosis_id",
                "target_node_id",
                "selected_item_id",
                "reason",
                "status",
            )
            if key in payload
        }
    if event_type == "ACTION_TAKEN":
        action = payload.get("action") or {}
        vertical = payload.get("vertical")
        if not isinstance(action, dict):
            action = {}
        return {
            "phase": payload.get("phase"),
            "kind": action.get("kind"),
            "node_ids": action.get("node_ids"),
            "item_id": action.get("item_id"),
            "reason": _strip_volatile(action.get("reason")),
            "vertical": (
                None
                if not isinstance(vertical, dict)
                else {
                    key: vertical.get(key)
                    for key in (
                        "domain_id",
                        "policy_version",
                        "question_id",
                        "reason_code",
                        "probe_stage",
                        "hint_level",
                        "interview_ladder",
                        "cf_hint_ladder_shared",
                    )
                }
            ),
        }
    if event_type == "RESPONSE_SUBMITTED":
        return {key: payload.get(key) for key in ("item_id", "phase", "turn_index")}
    if event_type == "ASSESSED":
        result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
        rubric = payload.get("rubric_audit")
        vertical = payload.get("vertical")
        dimensions: dict[str, Any] | None = None
        if isinstance(rubric, dict):
            dimensions = {}
            for name, dimension in sorted((rubric.get("dimensions") or {}).items()):
                dimensions[name] = dimension
        return {
            "item_id": payload.get("item_id") or result.get("item_id"),
            "result": {
                key: result.get(key)
                for key in ("status", "score", "failure_reason", "scorer_id", "evidence_refs")
                if key in result
            },
            "rubric_audit": (
                None
                if not isinstance(rubric, dict)
                else {
                    "question_id": rubric.get("question_id"),
                    "scorer_id": rubric.get("scorer_id"),
                    "status": rubric.get("status"),
                    "open_answer": rubric.get("open_answer"),
                    "dimensions": dimensions,
                    "failure_modes": sorted(rubric.get("failure_modes") or []),
                    "spec_digest": rubric.get("spec_digest"),
                }
            ),
            "vertical": (
                None
                if not isinstance(vertical, dict)
                else {
                    key: vertical.get(key)
                    for key in ("domain_id", "policy_version", "question_id", "jd_ref")
                }
            ),
        }
    if event_type == "MASTERY_UPDATED":
        snapshot = payload.get("snapshot") or {}
        masteries = snapshot.get("masteries") if isinstance(snapshot, dict) else {}
        return {
            "result_id": payload.get("result_id"),
            "status": payload.get("status"),
            "applied": payload.get("applied"),
            "policy_version": payload.get("policy_version"),
            "masteries": _round_mastery(masteries or {}),
        }
    if event_type == "SESSION_PAUSED":
        return {
            key: payload.get(key) for key in ("previous_phase", "pending_item_id", "turn_index")
        }
    if event_type == "SESSION_RESUMED":
        return {key: payload.get(key) for key in ("phase",)}
    if event_type == "GOAL_COMPLETED":
        return {
            key: payload.get(key)
            for key in ("goal_id", "objective_id", "completion_reason", "status")
            if key in payload
        }
    if event_type == "ERROR":
        return {
            key: payload.get(key)
            for key in (
                "error_code",
                "classification",
                "failure_reason",
                "mastery_unchanged",
                "retry_count",
            )
            if key in payload
        }
    return _strip_volatile(payload)


def _evidence_records(repository: SqliteRepository, learner_id: str, section: str) -> list[dict]:
    records: list[dict] = []
    for event in repository.list_events(learner_id):
        records.append(
            {
                "schema": EVIDENCE_SCHEMA,
                "evidence_classes": ["MOCK", "DETERMINISTIC"],
                "section": section,
                "learner_id": learner_id,
                "session_id": event.session_id,
                "seq": event.seq,
                "event_type": event.event_type,
                "payload": _project_payload(event.event_type, event.payload),
            }
        )
    return records


def _session_events(repository: SqliteRepository, learner_id: str, session_id: str) -> list:
    return [event for event in repository.list_events(learner_id) if event.session_id == session_id]


# ---------------------------------------------------------------------------
# Fixtures / interview helpers
# ---------------------------------------------------------------------------
def default_fixtures_root() -> Path:
    return Path(__file__).resolve().parents[1] / "fixtures" / "m1_teacher"


def _reference_responses(fixtures_root: Path) -> dict[str, dict]:
    path = (
        fixtures_root / "vertical" / "interview" / "rubrics" / "scoring" / "reference_answers.json"
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {answer["answer_id"]: answer["response"] for answer in payload["answers"]}


def _knowledge_scenario_ids(fixtures_root: Path) -> dict[tuple[str, str], str]:
    path = fixtures_root / "vertical" / "freshness" / "scenarios.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        (scenario["old_version_id"], scenario["new_version_id"]): scenario["scenario_id"]
        for scenario in payload["knowledge_scenarios"]
    }


def _interview_setup(fixtures_root: Path):
    adapter = InterviewDomainAdapter(fixtures_root)
    adapter.validate()
    graph = KnowledgeGraph(adapter.knowledge_nodes(), adapter.prerequisite_edges())
    freshness = KnowledgeFreshnessService(fixtures_root)
    judge = InterviewRubricJudge(fixtures_root)
    return adapter, graph, freshness, judge


def _probe_stage(reason: str) -> str:
    return (
        reason[len("INTERVIEW_PROBE_") :].lower()
        if reason.startswith("INTERVIEW_PROBE_")
        else reason
    )


def _interview_item(adapter: InterviewDomainAdapter, item_id: str) -> AssessmentItem:
    return next(item for item in adapter.assessment_items() if item.item_id == item_id)


def _interview_objective(adapter: InterviewDomainAdapter, item_id: str):
    item = _interview_item(adapter, item_id)
    node_id = item.node_ids[0]
    return next(
        objective for objective in adapter.objectives() if node_id in objective.target_node_ids
    )


def _interview_goal(learner_id: str, objective, suffix: str = "") -> LearnerGoal:
    return LearnerGoal(
        goal_id=f"goal:{learner_id}{suffix}",
        learner_id=learner_id,
        objective_id=objective.objective_id,
        created_at=FIXED_TIMESTAMP,
    )


def _seed_prior_correct(
    history: LearningHistory, item: AssessmentItem, learner_id: str, *, count: int = 3
) -> None:
    for index in range(count):
        history.apply_assessment(
            learner_id,
            "seed:b5.interview",
            item,
            AssessmentResult(
                result_id=f"seed:{learner_id}:{index}",
                item_id=item.item_id,
                learner_id=learner_id,
                status="CORRECT",
                score=1.0,
                max_score=1.0,
                scorer_id="synthetic.seed",
                created_at=FIXED_TIMESTAMP,
            ),
        )


def _run_interview_flow(
    *,
    repository: SqliteRepository,
    adapter: InterviewDomainAdapter,
    graph: KnowledgeGraph,
    freshness: KnowledgeFreshnessService,
    judge: InterviewRubricJudge,
    learner_id: str,
    question_id: str,
    session_id: str,
    now: str,
    responses: Sequence[dict],
    seed_correct: int = 0,
    stop_after: int | None = None,
    goal_suffix: str = "",
) -> dict[str, Any]:
    history = LearningHistory(repository)
    item = _interview_item(adapter, question_id)
    if seed_correct:
        _seed_prior_correct(history, item, learner_id, count=seed_correct)
    objective = _interview_objective(adapter, question_id)
    policy = InterviewVerticalPolicy(adapter, judge, freshness, question_id=question_id, now=now)
    engine = TeachingSessionEngine(
        adapter,
        graph,
        repository,
        history=history,
        scorer=InterviewJudgeScorer(judge),
        vertical_policy=policy,
    )
    engine.start_session(
        learner_id,
        _interview_goal(learner_id, objective, goal_suffix),
        objective,
        session_id=session_id,
    )
    observations: list[dict[str, Any]] = []
    for index, response in enumerate(responses):
        state = repository.load_session(session_id)
        if state.pending_item_id is None:
            break
        action = engine.current_action(session_id)
        result = engine.submit_response(session_id, state.pending_item_id, response)
        observations.append(
            {
                "step": index,
                "turn": state.turn_index,
                "phase_before": state.phase,
                "action_kind": action.kind,
                "action_reason": action.reason.code if action.reason else None,
                "status": result.status,
                "score": None if result.score is None else round(float(result.score), 6),
                "failure_reason": result.failure_reason,
            }
        )
        if stop_after is not None and len(observations) >= stop_after:
            break
    final_state = repository.load_session(session_id)
    events = _session_events(repository, learner_id, session_id)
    session_started = next(
        (event for event in events if event.event_type == "SESSION_STARTED"), None
    )
    vertical_started = (session_started.payload.get("vertical") or {}) if session_started else {}
    rubric_audits = [
        event.payload["rubric_audit"]
        for event in events
        if event.event_type == "ASSESSED" and event.payload.get("rubric_audit")
    ]
    return {
        "learner_id": learner_id,
        "question_id": question_id,
        "objective_id": objective.objective_id,
        "session_id": session_id,
        "jd_id": JD_ID,
        "jd_version": vertical_started.get("jd_version"),
        "jd_ref": vertical_started.get("jd_ref"),
        "seed_correct_evidence": seed_correct,
        "observations": observations,
        "probe_sequence": [
            observation["action_reason"]
            for observation in observations
            if observation["action_reason"]
            and observation["action_reason"].startswith("INTERVIEW_PROBE_")
        ],
        "hint_levels": sorted(
            {
                int(observation["action_reason"].rsplit("_", 1)[1])
                for observation in observations
                if observation["action_reason"]
                and observation["action_reason"].startswith("INTERVIEW_HINT_LEVEL_")
            }
        ),
        "clarification_count": sum(
            1 for observation in observations if observation["action_kind"] == "ASK_CLARIFICATION"
        ),
        "rubric_audit_dimensions": sorted(
            rubric_audits[0].get("dimensions", {}).keys() if rubric_audits else []
        ),
        "rubric_spec_digests": len({audit.get("spec_digest") for audit in rubric_audits}),
        "final_phase": final_state.phase,
        "final_pending_item_id": final_state.pending_item_id,
        "final_turn": final_state.turn_index,
        "event_count": len(events),
        "verify_rebuild": bool(history.verify_rebuild(learner_id)),
    }


# ---------------------------------------------------------------------------
# CF helpers
# ---------------------------------------------------------------------------
def _cf_engine(components, repository: SqliteRepository, student_fixture: dict):
    planner = CurriculumPlanner(
        components.adapter,
        components.graph,
        PlannerPolicy(prerequisite_mastery_threshold=demo.SEED_PREREQUISITE_THRESHOLD),
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
        scorer=demo.MockStudentScorer(student_fixture),
        policy=SessionPolicy(),
    )
    return engine, history


def _drive_until_turn(
    engine: TeachingSessionEngine,
    repository: SqliteRepository,
    adapter,
    session_id: str,
    responder,
    until_turn: int,
) -> Any:
    items = {item.item_id: item for item in adapter.assessment_items()}
    for _ in range(400):
        state = repository.load_session(session_id)
        if state is None or state.phase in {"COMPLETE", "PAUSED"}:
            return state
        if state.turn_index >= until_turn:
            return state
        if state.pending_item_id is not None:
            item = items[state.pending_item_id]
            engine.submit_response(session_id, item.item_id, responder(item, state))
            continue
        action = engine.current_action(session_id)
        if action.kind == "GOAL_COMPLETE":
            return state
        if action.item_id is not None:
            continue
        engine.advance_session(session_id)
    return repository.load_session(session_id)


def _session_fingerprint(repository: SqliteRepository, session_id: str) -> dict[str, Any]:
    state = repository.load_session(session_id)
    events = [
        {
            "seq": event.seq,
            "event_type": event.event_type,
            "payload": _project_payload(event.event_type, event.payload),
        }
        for event in repository.list_events(state.learner_id)
        if event.session_id == session_id
    ]
    digest = hashlib.sha256(
        json.dumps(events, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return {
        "phase": state.phase,
        "pending_item_id": state.pending_item_id,
        "turn_index": state.turn_index,
        "event_count": len(events),
        "journal_sha256": digest,
    }


def _snapshot_view(repository: SqliteRepository, learner_id: str) -> dict[str, Any]:
    snapshot = repository.get_snapshot(learner_id)
    if snapshot is None:
        return {"masteries": {}, "revision": 0, "completed_item_count": 0}
    return {
        "masteries": _round_mastery(snapshot.masteries),
        "revision": snapshot.revision,
        "completed_item_count": len(snapshot.completed_item_ids),
    }


# ---------------------------------------------------------------------------
# Scenario sections
# ---------------------------------------------------------------------------
def _run_cf_section(db_path: Path, fixtures_root: Path, max_turns: int, pause_after_turns: int):
    components = demo.build_components(fixtures_root)
    results = []
    for student in CF_STUDENTS:
        summary = demo.run_student_path(
            student,
            db_path=db_path,
            fixtures_root=fixtures_root,
            max_turns=max_turns,
            pause_after_turns=min(pause_after_turns, max_turns),
        )
        results.append(
            {
                "student_fixture": summary["student_fixture"],
                "learner_id": summary["learner_id"],
                "session_id": summary["session_id"],
                "first_action": summary.get("first_action"),
                "initial_plan_steps": summary.get("initial_plan", {}).get("steps"),
                "phase_sequence": summary.get("phase_sequence"),
                "assessment_status_counts": summary.get("assessment_status_counts"),
                "mastery_after": {
                    node_id: round(float(entry["value"]), 6)
                    for node_id, entry in sorted(summary.get("mastery_after", {}).items())
                },
                "verify_rebuild": bool(summary.get("verify_rebuild")),
                "event_count": int(summary.get("event_count", 0)),
            }
        )
    paths_differ = (
        results[0]["first_action"] != results[1]["first_action"]
        and results[0]["mastery_after"] != results[1]["mastery_after"]
    )
    return {
        "components": components,
        "learners": results,
        "paths_differ": bool(paths_differ),
        "shared_journal": "one canonical SQLite database: per-learner event/seq log + session table",
    }


def _run_interview_section(repository, fixtures_root: Path):
    adapter, graph, freshness, judge = _interview_setup(fixtures_root)
    responses = _reference_responses(fixtures_root)
    facts_answer = dict(responses["a-missingfacts-004"])
    facts_answer["project_facts"] = [
        "合成项目：负责推荐延迟优化，P99 从 800ms 降到 200ms（合成数据，仅演示）"
    ]
    vague_with_facts = {
        "text": "大概加一些缓存、优化一下特征，可能就快了。",
        "project_facts": facts_answer["project_facts"],
    }

    learner_a_v1 = _run_interview_flow(
        repository=repository,
        adapter=adapter,
        graph=graph,
        freshness=freshness,
        judge=judge,
        learner_id=INTERVIEW_LEARNER_A,
        question_id=QUESTION_REC,
        session_id="b5.interview.a.jd_v1",
        now=JD_NOW_V1,
        responses=[responses["a-unsourced-007"]] * 8,
        seed_correct=3,
        goal_suffix=":jd_v1",
    )
    old_session = _session_fingerprint(repository, "b5.interview.a.jd_v1")
    impact = freshness.jd_change_impact(JD_ID, "v1", "v2")
    learner_a_v2 = _run_interview_flow(
        repository=repository,
        adapter=adapter,
        graph=graph,
        freshness=freshness,
        judge=judge,
        learner_id=INTERVIEW_LEARNER_A,
        question_id=QUESTION_REC,
        session_id="b5.interview.a.jd_v2",
        now=JD_NOW_V2,
        responses=[responses["a-unsourced-007"]] * 2,
        goal_suffix=":jd_v2",
    )
    new_session = _session_fingerprint(repository, "b5.interview.a.jd_v2")
    learner_b = _run_interview_flow(
        repository=repository,
        adapter=adapter,
        graph=graph,
        freshness=freshness,
        judge=judge,
        learner_id=INTERVIEW_LEARNER_B,
        question_id=QUESTION_ENG,
        session_id="b5.interview.b.jd_v2",
        now=JD_NOW_V2,
        responses=[
            responses["a-missingfacts-004"],
            vague_with_facts,
            facts_answer,
            facts_answer,
            facts_answer,
            facts_answer,
            facts_answer,
            facts_answer,
        ],
    )
    learners = [
        {
            "learner_id": INTERVIEW_LEARNER_A,
            "learner_state": "seeded_evidence (3 CORRECT synthetic observations)",
            "sessions": [learner_a_v1, learner_a_v2],
        },
        {
            "learner_id": INTERVIEW_LEARNER_B,
            "learner_state": "novice (no prior interview evidence)",
            "sessions": [learner_b],
        },
    ]
    all_learner_sessions = [session for learner in learners for session in learner["sessions"]]
    return {
        "learners": learners,
        "jd_versions": [session["jd_version"] for session in all_learner_sessions],
        "jd_change": {
            "jd_id": impact.jd_id,
            "old_version": impact.old_version,
            "new_version": impact.new_version,
            "affects_running_sessions": impact.affects_running_sessions,
            "affects_new_plans": impact.affects_new_plans,
            "reason_code": impact.reason_code,
            "delta": {key: sorted(value) for key, value in impact.delta.items()},
            "old_session_before": old_session,
            "old_session_after": _session_fingerprint(repository, "b5.interview.a.jd_v1"),
            "new_session": new_session,
        },
        "probe_stages_seen": {
            f"{learner['learner_id']}::{session['session_id']}": [
                _probe_stage(reason) for reason in session["probe_sequence"]
            ]
            for learner in learners
            for session in learner["sessions"]
        },
        "paths_differ": learner_a_v1["probe_sequence"] != learner_b["probe_sequence"],
        "full_solution_emitted": any(
            reason == "INTERVIEW_HINT_LEVEL_4"
            for session in all_learner_sessions
            for reason in [obs["action_reason"] for obs in session["observations"]]
        ),
        "shared_journal": "one canonical SQLite database: same event table as the CF section",
    }


def _run_cross_domain_section(
    repository: SqliteRepository, fixtures_root: Path, max_turns: int, pause_after_turns: int
):
    components = demo.build_components(fixtures_root)
    student_fixture = demo.load_student_fixture(fixtures_root, "a")
    demo.seed_prior_evidence(
        repository, components, student_fixture, learner_id=CROSS_DOMAIN_LEARNER
    )
    engine, history = _cf_engine(components, repository, student_fixture)
    objective = components.objective
    goal = LearnerGoal(
        goal_id=f"goal:{CROSS_DOMAIN_LEARNER}:cf",
        learner_id=CROSS_DOMAIN_LEARNER,
        objective_id=objective.objective_id,
        created_at=FIXED_TIMESTAMP,
    )
    cf_state = engine.start_session(
        CROSS_DOMAIN_LEARNER, goal, objective, session_id="b5.cross.cf.session"
    )
    responder = demo.DeterministicStudentResponder()
    _drive_until_turn(
        engine,
        repository,
        components.adapter,
        cf_state.session_id,
        responder,
        until_turn=min(pause_after_turns, max_turns),
    )
    snapshot_before_pause = _snapshot_view(repository, CROSS_DOMAIN_LEARNER)
    seq_before_pause = max(event.seq for event in repository.list_events(CROSS_DOMAIN_LEARNER))
    paused = engine.pause_session(cf_state.session_id)

    adapter, graph, freshness, judge = _interview_setup(fixtures_root)
    responses = _reference_responses(fixtures_root)
    facts_answer = dict(responses["a-missingfacts-004"])
    facts_answer["project_facts"] = [
        "合成项目：负责推荐延迟优化，P99 从 800ms 降到 200ms（合成数据，仅演示）"
    ]
    interview = _run_interview_flow(
        repository=repository,
        adapter=adapter,
        graph=graph,
        freshness=freshness,
        judge=judge,
        learner_id=CROSS_DOMAIN_LEARNER,
        question_id=QUESTION_ENG,
        session_id="b5.cross.interview.session",
        now=JD_NOW_V2,
        responses=[
            responses["a-missingfacts-004"],
            {**facts_answer, "text": "大概加一些缓存、优化一下特征，可能就快了。"},
            facts_answer,
        ],
        stop_after=3,
    )
    snapshot_after_interview = _snapshot_view(repository, CROSS_DOMAIN_LEARNER)
    seq_after_interview = max(event.seq for event in repository.list_events(CROSS_DOMAIN_LEARNER))
    resumed = engine.resume_session(cf_state.session_id)
    final_state = engine.run_until_goal(
        cf_state.session_id, max_turns=max_turns, responder=responder
    )
    events = repository.list_events(CROSS_DOMAIN_LEARNER)
    seqs = [event.seq for event in events]
    sessions = repository.list_sessions(CROSS_DOMAIN_LEARNER)
    snapshot_final = _snapshot_view(repository, CROSS_DOMAIN_LEARNER)
    return {
        "learner_id": CROSS_DOMAIN_LEARNER,
        "cf_session_id": cf_state.session_id,
        "interview_session_id": "b5.cross.interview.session",
        "paused_phase": paused.phase,
        "pause_turn": paused.turn_index,
        "interview_stop_after": 3,
        "resumed_phase": resumed.phase,
        "final_cf_phase": final_state.phase,
        "final_cf_turn": final_state.turn_index,
        "snapshot_before_pause": snapshot_before_pause,
        "snapshot_after_interview": snapshot_after_interview,
        "snapshot_final": snapshot_final,
        "seq_before_pause": seq_before_pause,
        "seq_after_interview": seq_after_interview,
        "seq_contiguous": seqs == list(range(seqs[0], seqs[0] + len(seqs))) if seqs else False,
        "unified_event_types": sorted({event.event_type for event in events}),
        "unified_domains": sorted(
            {
                components.adapter.domain_id,
                adapter.domain_id,
            }
        ),
        "session_count": len(sessions),
        "session_ids": sorted(state.session_id for state in sessions),
        "verify_rebuild": bool(history.verify_rebuild(CROSS_DOMAIN_LEARNER)),
        "interview_jd_version": interview["jd_version"],
        "interview_clarifications": interview["clarification_count"],
        "interview_probe_sequence": interview["probe_sequence"],
        "snapshot_changed_after_interview": (snapshot_after_interview != snapshot_before_pause),
    }


def _run_freshness_section(repository: SqliteRepository, fixtures_root: Path):
    adapter, graph, freshness, judge = _interview_setup(fixtures_root)
    decisions = freshness.classify_all_scenarios()
    scenario_ids = _knowledge_scenario_ids(fixtures_root)
    blocked = [decision for decision in decisions if decision.recheck_required]
    eligible = [decision for decision in decisions if decision.curriculum_eligible]
    blocked_records: list[dict[str, Any]] = []
    for index, decision in enumerate(blocked):
        learner_id = f"b5.freshness.blocked.{index}"
        policy = InterviewVerticalPolicy(
            adapter,
            judge,
            freshness,
            question_id=QUESTION_ENG,
            now=JD_NOW_V2,
            knowledge_decisions=[decision],
        )
        history = LearningHistory(repository)
        engine = TeachingSessionEngine(
            adapter,
            graph,
            repository,
            history=history,
            scorer=InterviewJudgeScorer(judge),
            vertical_policy=policy,
        )
        objective = _interview_objective(adapter, QUESTION_ENG)
        try:
            engine.start_session(
                learner_id,
                _interview_goal(learner_id, objective, f":blocked:{index}"),
                objective,
                session_id=f"b5.freshness.session.blocked.{index}",
            )
            rejected = False
            error_code = None
            details_map_code = None
            events_written = len(repository.list_events(learner_id))
        except Exception as exc:  # ValidationError is the fail-closed contract
            rejected = True
            error_code = getattr(exc, "code", None)
            details = getattr(exc, "details", {}) or {}
            details_map_code = details.get("map_code")
            events_written = len(repository.list_events(learner_id))
        blocked_records.append(
            {
                "section": "freshness",
                "record": "blocked_knowledge",
                "scenario_id": scenario_ids.get(
                    (decision.old_version_id, decision.new_version_id),
                    f"k-unknown-{index}",
                ),
                "source_id": decision.source_id,
                "change_kind": decision.change_kind,
                "reason_code": decision.reason_code,
                "map_code": decision.map_code,
                "rejected": rejected,
                "error_code": error_code,
                "details_map_code": details_map_code,
                "events_written": events_written,
            }
        )
    eligible_records: list[dict[str, Any]] = []
    for index, decision in enumerate(eligible):
        learner_id = f"b5.freshness.eligible.{index}"
        policy = InterviewVerticalPolicy(
            adapter,
            judge,
            freshness,
            question_id=QUESTION_ENG,
            now=JD_NOW_V2,
            knowledge_decisions=[decision],
        )
        history = LearningHistory(repository)
        engine = TeachingSessionEngine(
            adapter,
            graph,
            repository,
            history=history,
            scorer=InterviewJudgeScorer(judge),
            vertical_policy=policy,
        )
        objective = _interview_objective(adapter, QUESTION_ENG)
        engine.start_session(
            learner_id,
            _interview_goal(learner_id, objective, f":eligible:{index}"),
            objective,
            session_id=f"b5.freshness.session.eligible.{index}",
        )
        engine.pause_session(f"b5.freshness.session.eligible.{index}")
        eligible_records.append(
            {
                "section": "freshness",
                "record": "eligible_update",
                "learner_id": learner_id,
                "scenario_id": scenario_ids.get(
                    (decision.old_version_id, decision.new_version_id),
                    f"k-unknown-{index}",
                ),
                "source_id": decision.source_id,
                "change_kind": decision.change_kind,
                "reason_code": decision.reason_code,
                "curriculum_eligible": decision.curriculum_eligible,
                "events_written": len(repository.list_events(learner_id)),
            }
        )
    jd_blocked_records: list[dict[str, Any]] = []
    for index, scenario in enumerate(freshness.jd_scenarios()):
        if scenario.get("expected_allowed_for_new_plan"):
            continue
        learner_id = f"b5.freshness.jd_blocked.{index}"
        policy = InterviewVerticalPolicy(
            adapter,
            judge,
            freshness,
            question_id=QUESTION_ENG,
            jd_id=scenario["jd_id"],
            now=scenario["now"],
        )
        history = LearningHistory(repository)
        engine = TeachingSessionEngine(
            adapter,
            graph,
            repository,
            history=history,
            scorer=InterviewJudgeScorer(judge),
            vertical_policy=policy,
        )
        objective = _interview_objective(adapter, QUESTION_ENG)
        try:
            engine.start_session(
                learner_id,
                _interview_goal(learner_id, objective, f":jdblocked:{index}"),
                objective,
                session_id=f"b5.freshness.session.jd_blocked.{index}",
            )
            rejected = False
            error_code = None
        except Exception as exc:
            rejected = True
            error_code = getattr(exc, "code", None)
        jd_blocked_records.append(
            {
                "section": "freshness",
                "record": "blocked_jd",
                "scenario_id": scenario["scenario_id"],
                "jd_id": scenario["jd_id"],
                "now": scenario["now"],
                "reason_code": scenario["expected_reason_code"],
                "map_code": scenario["expected_map_code"],
                "rejected": rejected,
                "error_code": error_code,
                "events_written": len(repository.list_events(learner_id)),
            }
        )
    return {
        "adapter": adapter,
        "decision_counts": {
            kind: sum(1 for decision in decisions if decision.change_kind == kind)
            for kind in sorted({decision.change_kind for decision in decisions})
        },
        "blocked_knowledge": blocked_records,
        "eligible_updates": eligible_records,
        "blocked_jd": jd_blocked_records,
        "silent_imports": sum(
            record["events_written"] for record in blocked_records + jd_blocked_records
        ),
        "gate_enforced": all(
            record["rejected"] and record["events_written"] == 0
            for record in blocked_records + jd_blocked_records
        ),
    }


# ---------------------------------------------------------------------------
# Evidence building / writing
# ---------------------------------------------------------------------------
def build_evidence_lines(scenario: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Return the deterministic JSONL evidence projection per section file."""

    evidence = scenario.get("_evidence") or {}
    files: dict[str, list[dict[str, Any]]] = {}
    for name, records in evidence.items():
        files[f"e2e_b5_{name}.jsonl"] = records
    return files


def _record_hash(records: list[dict[str, Any]]) -> str:
    text = "".join(
        json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records
    )
    return sha256_text(text)


def _manifest() -> dict[str, Any]:
    return {
        "manifest_version": ARTIFACT_MANIFEST_VERSION,
        "generated_at": FIXED_TIMESTAMP,
        "base_sha": BASE_SHA,
        "implementation_commit": IMPLEMENTATION_COMMIT,
        "note": (
            "fixed artifact manifest: no wall clock and no live git HEAD are read; "
            "the same content tree regenerates byte-identical evidence"
        ),
    }


def write_evidence(scenario: dict[str, Any], out_dir: str | Path = EVIDENCE_DIR) -> dict[str, Any]:
    """Write deterministic JSONL evidence plus the summary JSON."""

    root = Path(out_dir)
    if not root.is_absolute():
        root = Path(__file__).resolve().parents[1] / root
    root.mkdir(parents=True, exist_ok=True)
    files = build_evidence_lines(scenario)
    hashes: dict[str, str] = {}
    for name, records in files.items():
        text = "".join(
            json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records
        )
        (root / name).write_text(text, encoding="utf-8")
        hashes[name] = sha256_text(text)
    summary_payload = _public(scenario)
    summary_payload["evidence_files"] = sorted(files)
    summary_payload["evidence_hashes"] = dict(sorted(hashes.items()))
    summary_text = _json_dump(summary_payload)
    (root / "e2e_b5_summary.json").write_text(summary_text, encoding="utf-8")
    return {
        "out_dir": str(root),
        "hashes": dict(sorted(hashes.items())),
        "files": sorted(files) + ["e2e_b5_summary.json"],
        "summary_sha256": sha256_text(summary_text),
    }


# ---------------------------------------------------------------------------
# Scenario driver
# ---------------------------------------------------------------------------
def run_scenario(
    *,
    fixtures_root: str | Path | None = None,
    max_turns: int = DEFAULT_MAX_TURNS,
    pause_after_turns: int = DEFAULT_PAUSE_AFTER_TURNS,
) -> dict[str, Any]:
    """Run the unified B5 scenario and return the deterministic summary."""

    if max_turns < 2:
        raise ValueError("max_turns must be >= 2")
    if not 1 <= pause_after_turns < max_turns:
        raise ValueError("pause_after_turns must be in [1, max_turns)")
    root = Path(fixtures_root) if fixtures_root is not None else default_fixtures_root()
    workdir = Path(tempfile.mkdtemp(prefix="m1b_b5_e2e_"))
    db_path = workdir / "m1b_b5.sqlite"

    cf_section = _run_cf_section(db_path, root, max_turns, pause_after_turns)
    repository = SqliteRepository(db_path)
    try:
        interview_section = _run_interview_section(repository, root)
        cross_section = _run_cross_domain_section(repository, root, max_turns, pause_after_turns)
        freshness_section = _run_freshness_section(repository, root)

        evidence: dict[str, list[dict[str, Any]]] = {}
        cf_learner_ids = [learner["learner_id"] for learner in cf_section["learners"]]
        interview_learner_ids = sorted(
            {learner["learner_id"] for learner in interview_section["learners"]}
        )
        evidence["cf"] = [
            record
            for learner_id in cf_learner_ids
            for record in _evidence_records(repository, learner_id, "cf")
        ]
        evidence["interview"] = [
            record
            for learner_id in interview_learner_ids
            for record in _evidence_records(repository, learner_id, "interview")
        ]
        evidence["cross_domain"] = _evidence_records(
            repository, CROSS_DOMAIN_LEARNER, "cross_domain"
        )
        freshness_records = (
            [
                {
                    **record,
                    "schema": EVIDENCE_SCHEMA,
                    "evidence_classes": ["MOCK", "DETERMINISTIC"],
                }
                for record in freshness_section["blocked_knowledge"]
            ]
            + [
                {
                    **record,
                    "schema": EVIDENCE_SCHEMA,
                    "evidence_classes": ["MOCK", "DETERMINISTIC"],
                }
                for record in freshness_section["eligible_updates"]
            ]
            + [
                {
                    **record,
                    "schema": EVIDENCE_SCHEMA,
                    "evidence_classes": ["MOCK", "DETERMINISTIC"],
                }
                for record in freshness_section["blocked_jd"]
            ]
        )
        for record in freshness_section["eligible_updates"]:
            freshness_records.extend(
                _evidence_records(repository, record["learner_id"], "freshness")
            )
        evidence["freshness"] = freshness_records

        unified_learners = sorted(
            {learner["learner_id"] for learner in cf_section["learners"]}
            | set(interview_learner_ids)
            | {CROSS_DOMAIN_LEARNER}
        )
        unified = []
        all_rebuild_ok = True
        for learner_id in unified_learners:
            events = repository.list_events(learner_id)
            seqs = [event.seq for event in events]
            history = LearningHistory(repository)
            rebuild_ok = bool(history.verify_rebuild(learner_id))
            all_rebuild_ok = all_rebuild_ok and rebuild_ok
            unified.append(
                {
                    "learner_id": learner_id,
                    "event_count": len(events),
                    "event_types": sorted({event.event_type for event in events}),
                    "seq_contiguous": seqs == list(range(seqs[0], seqs[0] + len(seqs)))
                    if seqs
                    else False,
                    "session_count": len(repository.list_sessions(learner_id)),
                    "snapshot": _snapshot_view(repository, learner_id),
                    "verify_rebuild": rebuild_ok,
                }
            )
        scenario: dict[str, Any] = {
            "schema": B5_SCHEMA,
            "summary_schema": SUMMARY_SCHEMA,
            "artifact_manifest": _manifest(),
            "fixed_timestamp": FIXED_TIMESTAMP,
            "boundary": dict(BOUNDARY),
            "classification": {
                "MOCK": "synthetic CF students, interview answers, JD/resume and knowledge fixtures",
                "DETERMINISTIC": "state machine, ids/seq, planner policy, rubric arithmetic, replay",
                "NOT_VERIFIED": "real teaching effect, real resume/JD, real provider or Live",
            },
            "max_turns": max_turns,
            "pause_after_turns": pause_after_turns,
            "cf": {key: value for key, value in cf_section.items() if key != "components"},
            "interview": interview_section,
            "cross_domain": cross_section,
            "freshness": {
                key: value for key, value in freshness_section.items() if key != "adapter"
            },
            "unified_journal": {
                "schema": "m1b.b5.unified_journal.v1",
                "learners": unified,
                "all_verify_rebuild": all_rebuild_ok,
                "one_sqlite_file": True,
                "event_table": "canonical history_events (per-learner seq) + sessions table",
            },
            "_evidence": evidence,
        }
        return json.loads(json.dumps(_strip_volatile(scenario), ensure_ascii=False))
    finally:
        repository.close()


# ---------------------------------------------------------------------------
# Rendering / CLI
# ---------------------------------------------------------------------------
def render_json(scenario: dict[str, Any]) -> str:
    return json.dumps(scenario, ensure_ascii=False, indent=2, sort_keys=True)


def _fmt(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def render_text(scenario: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("B5 unified E2E demo (offline synthetic only, not real teaching effect)")
    lines.append(
        f"[schema] {scenario['schema']} max_turns={scenario['max_turns']} "
        f"pause_after_turns={scenario['pause_after_turns']}"
    )
    cf = scenario["cf"]
    lines.append(
        f"[cf] learners={len(cf['learners'])} paths_differ={cf['paths_differ']} "
        f"shared_journal={cf['shared_journal']}"
    )
    for learner in cf["learners"]:
        mastery = _fmt(learner["mastery_after"])
        status_counts = _fmt(learner["assessment_status_counts"])
        first_action = learner["first_action"]
        if isinstance(first_action, dict):
            first_action_view = {
                "kind": first_action.get("action_kind"),
                "item_id": first_action.get("item_id"),
                "reason_code": first_action.get("reason_code"),
            }
        else:  # pragma: no cover - defensive
            first_action_view = first_action
        lines.append(
            f"[cf:{learner['student_fixture']}] learner={learner['learner_id']} "
            f"first_action={_fmt(first_action_view)} assessments={status_counts} "
            f"mastery_after={mastery} verify_rebuild={learner['verify_rebuild']}"
        )
    interview = scenario["interview"]
    lines.append(
        f"[interview] learners={len(interview['learners'])} "
        f"paths_differ={interview['paths_differ']} "
        f"jd_versions={_fmt(interview['jd_versions'])}"
    )
    for learner in interview["learners"]:
        lines.append(
            f"[interview:{learner['learner_id']}] state={learner['learner_state']} "
            f"sessions={len(learner['sessions'])}"
        )
        for session in learner["sessions"]:
            lines.append(
                f"[interview:{learner['learner_id']}:{session['session_id']}] "
                f"jd={session['jd_version']} probes={_fmt(session['probe_sequence'])} "
                f"hints={session['hint_levels']} "
                f"clarifications={session['clarification_count']} "
                f"rubric_dimensions={_fmt(session['rubric_audit_dimensions'])} "
                f"final_phase={session['final_phase']}"
            )
    jd_change = interview["jd_change"]
    lines.append(
        f"[interview:jd_change] {jd_change['jd_id']} {jd_change['old_version']}->{jd_change['new_version']} "
        f"affects_running_sessions={jd_change['affects_running_sessions']} "
        f"affects_new_plans={jd_change['affects_new_plans']} "
        f"old_session_unchanged={jd_change['old_session_before'] == jd_change['old_session_after']}"
    )
    cross = scenario["cross_domain"]
    lines.append(
        f"[cross-domain] learner={cross['learner_id']} cf_session={cross['cf_session_id']} "
        f"interview_session={cross['interview_session_id']} "
        f"paused_turn={cross['pause_turn']} resumed_phase={cross['resumed_phase']} "
        f"final_cf_phase={cross['final_cf_phase']} seq_contiguous={cross['seq_contiguous']} "
        f"domains={_fmt(cross['unified_domains'])} session_count={cross['session_count']} "
        f"verify_rebuild={cross['verify_rebuild']}"
    )
    freshness = scenario["freshness"]
    lines.append(
        f"[freshness] decision_counts={_fmt(freshness['decision_counts'])} "
        f"blocked_knowledge={len(freshness['blocked_knowledge'])} "
        f"blocked_jd={len(freshness['blocked_jd'])} "
        f"eligible_updates={len(freshness['eligible_updates'])} "
        f"silent_imports={freshness['silent_imports']} gate_enforced={freshness['gate_enforced']}"
    )
    for record in freshness["blocked_knowledge"]:
        lines.append(
            f"[freshness:blocked] {record['scenario_id']} {record['change_kind']} "
            f"reason={record['reason_code']} map={record['map_code']} "
            f"rejected={record['rejected']} events={record['events_written']}"
        )
    for record in freshness["blocked_jd"]:
        lines.append(
            f"[freshness:jd_blocked] {record['scenario_id']} reason={record['reason_code']} "
            f"rejected={record['rejected']} events={record['events_written']}"
        )
    for record in freshness["eligible_updates"]:
        lines.append(
            f"[freshness:eligible] {record['scenario_id']} change={record['change_kind']} "
            f"events={record['events_written']}"
        )
    unified = scenario["unified_journal"]
    lines.append(
        f"[journal] learners={len(unified['learners'])} "
        f"all_verify_rebuild={unified['all_verify_rebuild']} one_sqlite_file=True"
    )
    lines.append(
        "[evidence-class] MOCK=synthetic students/interview/JD/knowledge; "
        "DETERMINISTIC=state machine/ids/replay/rubric; "
        "NOT_VERIFIED=real teaching effect"
    )
    lines.append(
        "[boundary] offline synthetic only, not real teaching effect; no network, no Key, no real resume/JD"
    )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Deterministic offline B5 unified E2E demo (MOCK + DETERMINISTIC; "
            "real teaching effect NOT_VERIFIED)"
        )
    )
    parser.add_argument(
        "--json", action="store_true", help="emit the machine-readable JSON summary"
    )
    parser.add_argument(
        "--write-evidence",
        nargs="?",
        const=str(EVIDENCE_DIR),
        default=None,
        help="write evidence JSONL + summary under the given directory",
    )
    parser.add_argument(
        "--fixtures",
        default=None,
        help="fixtures root (default: <repo>/fixtures/m1_teacher)",
    )
    parser.add_argument("--max-turns", type=int, default=DEFAULT_MAX_TURNS)
    parser.add_argument("--pause-after-turns", type=int, default=DEFAULT_PAUSE_AFTER_TURNS)
    args = parser.parse_args(argv)

    scenario = run_scenario(
        fixtures_root=args.fixtures,
        max_turns=args.max_turns,
        pause_after_turns=args.pause_after_turns,
    )
    if args.write_evidence is not None:
        result = write_evidence(scenario, args.write_evidence)
        for name in result["files"]:
            print(
                f"[evidence] {name} sha256={result['hashes'].get(name, result['summary_sha256'])}"
            )
    public_scenario = _public(scenario)
    if args.json:
        print(render_json(public_scenario))
    else:
        print(render_text(public_scenario))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main(sys.argv[1:]))
