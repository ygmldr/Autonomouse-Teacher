"""Deterministic B4 closed-loop demo (B-PR4 integration, additive).

This module demonstrates, offline and deterministically, the B-NEXT B4 closed
loops on the canonical ``m1_teacher`` core:

* **B4-01** — two synthetic CF learners run through the existing deterministic
  E2E student paths and land in the same canonical learner/session journal.
* **B4-02** — two synthetic Interview learners with different evidence states,
  a JD v1 -> v2 transition, the five-stage Socratic follow-up ladder,
  ``ASK_CLARIFICATION`` for missing project facts, the interview support ladder
  (FULL disabled) and four-dimension rubric audit payloads.
* **B4-03** — synthetic knowledge-freshness decisions: expired/conflicting/
  unauthoritative knowledge is rejected before any session/event write, while a
  verified authoritative UPDATE may enter a new plan.

Hard boundaries (unchanged): no network, no real resume/JD/company data, no
Provider/API key/LiveGate, no real teaching-effect claim.  Everything is
``MOCK`` (+ deterministic ids/state-machine behaviour) and ``NOT_VERIFIED`` for
learning effects.  ``m1_teacher.demo`` (the frozen historical evidence CLI) is
not modified; this module is a separate additive demo.

Run as::

    python -m m1_teacher.demo_b4 [--json]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Sequence

from .assessment.interview_judge import InterviewRubricJudge
from .contracts.types import LearnerGoal
from .domains.interview import InterviewDomainAdapter
from .knowledge.freshness import KnowledgeFreshnessService
from .knowledge.graph import KnowledgeGraph
from .learner.history import LearningHistory
from .learner.repository import SqliteRepository
from .session.engine import TeachingSessionEngine
from .session.vertical import InterviewJudgeScorer, InterviewVerticalPolicy

B4_DEMO_SCHEMA = "m1b.b4.demo.v1"
FIXED_TIMESTAMP = "2026-11-20T00:00:00Z"

INTERVIEW_LEARNER_A = "b4.interview.learner_a"
INTERVIEW_LEARNER_B = "b4.interview.learner_b"
INTERVIEW_QUESTION_A = "interview.item.q-ml-001"
INTERVIEW_QUESTION_B = "interview.item.q-eng-001"
INTERVIEW_JD_NOW_A = "2026-10-15T00:00:00Z"  # jd:rec v2 window
INTERVIEW_JD_NOW_B = "2026-07-01T00:00:00Z"  # jd:rec v1 window

_QUESTION_TRACK = {
    INTERVIEW_QUESTION_A: "ml_fundamentals",
    INTERVIEW_QUESTION_B: "engineering_metrics",
}

BOUNDARY = {
    "evidence_class": "MOCK+DETERMINISTIC",
    "real_teaching_effect": "NOT_VERIFIED",
    "network": "NONE",
    "real_resume_or_jd": "NONE",
    "provider_or_live_gate": "NONE",
    "hidden_scoring": "SCORER_ONLY (rubric audit exposes 4 dimensions + spec digest only)",
}

_VOLATILE_KEYS = frozenset({"created_at", "updated_at", "timestamp", "session_version", "trace_path"})


def _strip_volatile(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _strip_volatile(item)
            for key, item in value.items()
            if key not in _VOLATILE_KEYS
        }
    if isinstance(value, list):
        return [_strip_volatile(item) for item in value]
    return value


def _load_learner_script(fixtures_root: Path) -> tuple[dict[str, dict], str]:
    """Load the teacher-visible synthetic MOCK learner script.

    P1-2: the demo is a teacher-visible consumer and must never read hidden
    rubric/reference-answer material.  This file lives outside the hidden
    scoring tree and contains only synthetic learner responses.
    """

    path = (
        fixtures_root
        / "vertical"
        / "interview"
        / "learner_scripts"
        / "answers.json"
    )
    raw = path.read_bytes()
    payload = json.loads(raw.decode("utf-8"))
    if payload.get("synthetic") is not True or payload.get("license") != "CC0-1.0":
        raise ValueError("learner script must be synthetic CC0-1.0 data")
    answers = {answer["answer_id"]: answer["response"] for answer in payload["answers"]}
    return answers, hashlib.sha256(raw).hexdigest()


def _run_cf_learners(db_path: Path, fixtures_root: Path) -> dict[str, Any]:
    from . import demo  # frozen historical demo module: reuse its deterministic helpers

    summaries = []
    for student in ("student_a", "student_b"):
        summaries.append(
            demo.run_student_path(student, db_path=db_path, fixtures_root=fixtures_root)
        )
    projected = []
    for summary in summaries:
        projected.append(
            {
                "student": summary["student_fixture"],
                "learner_id": summary["learner_id"],
                "session_id": summary["session_id"],
                "action_sequence": [
                    {
                        "kind": action.get("action_kind") or action.get("kind"),
                        "reason": (action.get("reason") or {}).get("code")
                        if isinstance(action.get("reason"), dict)
                        else None,
                        "item_id": action.get("item_id"),
                    }
                    for action in summary["actions"]
                ],
                "phase_sequence": list(summary["phase_sequence"]),
                "assessment_status_counts": dict(summary["assessment_status_counts"]),
                "mastery_after": {
                    node_id: round(entry["value"], 6)
                    for node_id, entry in sorted(summary["mastery_after"].items())
                },
                "verify_rebuild": bool(summary["verify_rebuild"]),
                "event_count": int(summary["event_count"]),
            }
        )
    paths_differ = (
        projected[0]["action_sequence"] != projected[1]["action_sequence"]
        and projected[0]["mastery_after"] != projected[1]["mastery_after"]
    )
    return {
        "learners": projected,
        "paths_differ": bool(paths_differ),
        "shared_journal": "canonical SQLite learner/event tables (one database, two learners)",
    }


def _objective(adapter: InterviewDomainAdapter, question_id: str):
    track = _QUESTION_TRACK[question_id]
    return next(
        objective
        for objective in adapter.objectives()
        if objective.objective_id == f"obj.interview.{track}.mastery"
    )


def _goal(learner_id: str, objective) -> LearnerGoal:
    return LearnerGoal(
        goal_id=f"goal:{learner_id}",
        learner_id=learner_id,
        objective_id=objective.objective_id,
        created_at=FIXED_TIMESTAMP,
    )


def _seed_prior_correct(
    history: LearningHistory, item, learner_id: str, *, count: int = 3
) -> None:
    from .contracts.types import AssessmentResult

    for index in range(count):
        history.apply_assessment(
            learner_id,
            "seed:interview",
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
    now: str,
    responses: Sequence[dict],
    seed_correct: int = 0,
) -> dict[str, Any]:
    history = LearningHistory(repository)
    item = next(
        candidate
        for candidate in adapter.assessment_items()
        if candidate.item_id == question_id
    )
    if seed_correct:
        _seed_prior_correct(history, item, learner_id, count=seed_correct)
    objective = _objective(adapter, question_id)
    policy = InterviewVerticalPolicy(
        adapter, judge, freshness, question_id=question_id, now=now
    )
    engine = TeachingSessionEngine(
        adapter,
        graph,
        repository,
        history=history,
        scorer=InterviewJudgeScorer(judge),
        vertical_policy=policy,
    )
    session_id = f"b4.interview.session.{learner_id.split('.')[-1]}"
    engine.start_session(learner_id, _goal(learner_id, objective), objective, session_id=session_id)
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
                "result_status": result.status,
                "result_score": None if result.score is None else round(result.score, 6),
                "failure_reason": result.failure_reason,
            }
        )
    final_state = repository.load_session(session_id)
    events = [event.to_dict() for event in repository.list_events(learner_id)]
    session_events = [event for event in events if event["session_id"] == session_id]
    session_started = next(
        event for event in session_events if event["event_type"] == "SESSION_STARTED"
    )
    rubric_audits = [
        event["payload"]["rubric_audit"]
        for event in session_events
        if event["event_type"] == "ASSESSED" and event["payload"].get("rubric_audit")
    ]
    return {
        "learner_id": learner_id,
        "question_id": question_id,
        "objective_id": objective.objective_id,
        "session_id": session_id,
        "jd_version": session_started["payload"]["vertical"]["jd_version"],
        "seed_correct_evidence": seed_correct,
        "observations": _strip_volatile(observations),
        "final_phase": final_state.phase,
        "final_pending_item": final_state.pending_item_id,
        "final_turn": final_state.turn_index,
        "verify_rebuild": bool(history.verify_rebuild(learner_id)),
        "event_count": len(events),
        "rubric_audit_dimensions": sorted(
            rubric_audits[0]["dimensions"].keys() if rubric_audits else []
        ),
        "rubric_spec_digests": len({audit["spec_digest"] for audit in rubric_audits}),
        "clarification_count": sum(
            1 for obs in observations if obs["action_kind"] == "ASK_CLARIFICATION"
        ),
        "hint_levels": sorted(
            {
                int(obs["action_reason"].rsplit("_", 1)[1])
                for obs in observations
                if obs["action_reason"]
                and obs["action_reason"].startswith("INTERVIEW_HINT_LEVEL_")
            }
        ),
        "probe_sequence": [
            obs["action_reason"]
            for obs in observations
            if obs["action_reason"]
            and obs["action_reason"].startswith("INTERVIEW_PROBE_")
        ],
    }


def _run_interview_learners(db_path: Path, fixtures_root: Path) -> dict[str, Any]:
    adapter = InterviewDomainAdapter(fixtures_root)
    adapter.validate()
    graph = KnowledgeGraph(adapter.knowledge_nodes(), adapter.prerequisite_edges())
    freshness = KnowledgeFreshnessService(fixtures_root)
    judge = InterviewRubricJudge(fixtures_root)
    repository = SqliteRepository(db_path)
    learner_answers, script_digest = _load_learner_script(fixtures_root)

    learner_a = _run_interview_flow(
        repository=repository,
        adapter=adapter,
        graph=graph,
        freshness=freshness,
        judge=judge,
        learner_id=INTERVIEW_LEARNER_A,
        question_id=INTERVIEW_QUESTION_A,
        now=INTERVIEW_JD_NOW_A,
        responses=[learner_answers["learner-ml-overfit-v1"]] * 8,
        seed_correct=3,
    )
    learner_b = _run_interview_flow(
        repository=repository,
        adapter=adapter,
        graph=graph,
        freshness=freshness,
        judge=judge,
        learner_id=INTERVIEW_LEARNER_B,
        question_id=INTERVIEW_QUESTION_B,
        now=INTERVIEW_JD_NOW_B,
        responses=[
            learner_answers["learner-eng-missing-facts-v1"],  # NEEDS_REVIEW -> ASK_CLARIFICATION
            learner_answers["learner-eng-vague-with-facts-v1"],  # INCORRECT -> support ladder LIGHT
            learner_answers["learner-eng-facts-v1"],  # PARTIAL -> ladder progression
            learner_answers["learner-eng-facts-v1"],
            learner_answers["learner-eng-facts-v1"],
            learner_answers["learner-eng-facts-v1"],
            learner_answers["learner-eng-facts-v1"],
            learner_answers["learner-eng-facts-v1"],
        ],
    )
    return {
        "learners": [learner_a, learner_b],
        "jd_versions": [learner_a["jd_version"], learner_b["jd_version"]],
        "paths_differ": learner_a["probe_sequence"] != learner_b["probe_sequence"],
        "shared_journal": "one canonical database; per-learner seq/event log",
        "learner_input_source": "teacher-visible vertical/interview/learner_scripts/answers.json (synthetic MOCK; not hidden reference answers)",
        "learner_script_sha256": script_digest,
        "full_solution_emitted": any(
            reason == "INTERVIEW_HINT_LEVEL_4"
            for learner in (learner_a, learner_b)
            for reason in [obs["action_reason"] for obs in learner["observations"]]
        ),
    }


def _run_freshness_gate(db_path: Path, fixtures_root: Path) -> dict[str, Any]:
    from .contracts.errors import ValidationError

    service = KnowledgeFreshnessService(fixtures_root)
    decisions = service.classify_all_scenarios()
    adapter = InterviewDomainAdapter(fixtures_root)
    graph = KnowledgeGraph(adapter.knowledge_nodes(), adapter.prerequisite_edges())
    judge = InterviewRubricJudge(fixtures_root)
    objective = _objective(adapter, INTERVIEW_QUESTION_A)
    repository = SqliteRepository(db_path)
    blocked = [decision for decision in decisions if decision.recheck_required]
    eligible = [decision for decision in decisions if decision.curriculum_eligible]
    rejected: list[dict[str, Any]] = []
    for index, decision in enumerate(blocked):
        learner_id = f"b4.freshness.blocked.{index}"
        policy = InterviewVerticalPolicy(
            adapter, judge, service,
            question_id=INTERVIEW_QUESTION_A,
            knowledge_decisions=[decision],
        )
        history = LearningHistory(repository)
        engine = TeachingSessionEngine(
            adapter, graph, repository, history=history,
            scorer=InterviewJudgeScorer(judge), vertical_policy=policy,
        )
        try:
            engine.start_session(
                learner_id,
                _goal(learner_id, objective),
                objective,
                session_id=f"b4.freshness.session.{index}",
            )
        except ValidationError as exc:
            rejected.append(
                {
                    "source_id": decision.source_id,
                    "change_kind": decision.change_kind,
                    "reason_code": decision.reason_code,
                    "map_code": decision.map_code,
                    "error_code": exc.code,
                    "details_map_code": exc.details.get("map_code"),
                    "events_written": len(repository.list_events(learner_id)),
                }
            )
    counts: dict[str, int] = {}
    for decision in decisions:
        counts[decision.change_kind] = counts.get(decision.change_kind, 0) + 1
    return {
        "decision_counts": dict(sorted(counts.items())),
        "eligible_sources": sorted({decision.source_id for decision in eligible}),
        "blocked_sources": sorted({decision.source_id for decision in blocked}),
        "rejected_starts": rejected,
        "silent_imports": sum(item["events_written"] for item in rejected),
    }


def run_demo(db_root: str | Path | None = None) -> dict[str, Any]:
    """Run the deterministic B4 demo and return the JSON-serialisable summary."""

    fixtures_root = Path(__file__).resolve().parents[1] / "fixtures" / "m1_teacher"
    if db_root is None:
        workdir = Path(tempfile.mkdtemp(prefix="m1b_b4_demo_"))
    else:
        workdir = Path(db_root)
        workdir.mkdir(parents=True, exist_ok=True)
    cf_db = workdir / "b4_cf.sqlite"
    interview_db = workdir / "b4_interview.sqlite"
    freshness_db = workdir / "b4_freshness.sqlite"

    demo = {
        "schema": B4_DEMO_SCHEMA,
        "boundary": dict(BOUNDARY),
        "b4_01_cf": _looks_like(_run_cf_learners(cf_db, fixtures_root)),
        "b4_02_interview": _looks_like(_run_interview_learners(interview_db, fixtures_root)),
        "b4_03_freshness": _looks_like(_run_freshness_gate(freshness_db, fixtures_root)),
        "notes": [
            "MOCK: synthetic learners/questions/JDs/knowledge only",
            "DETERMINISTIC: fixed ids/timestamps/scores where applicable; no wall clock in projections",
            "NOT_VERIFIED: no real learning effect, no real provider, no real resume/JD",
        ],
    }
    return json.loads(json.dumps(_looks_like(demo), ensure_ascii=False, sort_keys=True))


def _looks_like(value: Any) -> Any:
    """Recursively drop volatile metadata for reproducible output."""

    return _strip_volatile(value)


def render_json(demo: dict[str, Any]) -> str:
    return json.dumps(demo, ensure_ascii=False, indent=2, sort_keys=True)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Deterministic offline B4 closed-loop demo (MOCK/NOT_VERIFIED)"
    )
    parser.add_argument("--json", action="store_true", help="emit the machine-readable JSON summary")
    args = parser.parse_args(argv)
    summary = run_demo()
    if args.json:
        print(render_json(summary))
    else:
        print("B4 closed-loop demo (MOCK + DETERMINISTIC; real teaching effect NOT_VERIFIED)")
        print(render_json(summary))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main(sys.argv[1:]))
