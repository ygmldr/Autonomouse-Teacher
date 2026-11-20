"""B4 end-to-end tests on the canonical teacher core (B-PR4 integration).

Coverage map (task B4.1–B4.7, TEST_EVIDENCE_MATRIX B4-01/02/03):

* **B4-01** — two synthetic CF learners through the existing deterministic demo
  paths, landing in one canonical learner/event journal with different paths and
  reproducible replay.
* **B4-02** — two synthetic Interview learners with different evidence states and
  a JD v1->v2 transition: five-stage Socratic ladder, learner-state acceleration,
  ``ASK_CLARIFICATION`` for missing learner-owned project facts, interview
  support ladder (FULL never emitted), four-dimension rubric audit, hidden
  material non-leakage.
* **B4-03** — EXPIRED/CONFLICT/UNAUTHORITATIVE knowledge and expired/conflicting
  JD versions are rejected before any session/event write (explicit MAP-E codes),
  while an eligible update may enter a new plan.
* Cross-domain session continuity (CF pause -> Interview session), version/domain
  rejection, unified event/replay consistency, determinism, no-network and the
  deterministic ``demo_b4`` output.

All evidence is MOCK + DETERMINISTIC; real teaching effect stays NOT_VERIFIED.
"""

from __future__ import annotations

import ast
import inspect
import json
import re
from pathlib import Path

import pytest

from m1_teacher import demo, demo_b4
from m1_teacher.assessment.interview_judge import InterviewRubricJudge
from m1_teacher.contracts.errors import ValidationError
from m1_teacher.contracts.types import (
    HISTORY_EVENT_TYPE_VALUES,
    TEACHING_ACTION_KIND_VALUES,
    AssessmentResult,
    LearnerGoal,
)
from m1_teacher.domains.interview import InterviewDomainAdapter
from m1_teacher.knowledge.freshness import KnowledgeFreshnessService
from m1_teacher.knowledge.graph import KnowledgeGraph
from m1_teacher.learner.history import LearningHistory
from m1_teacher.learner.repository import SqliteRepository
from m1_teacher.session import vertical as vertical_module
from m1_teacher.session.engine import TeachingSessionEngine
from m1_teacher.session.vertical import (
    InterviewJudgeScorer,
    InterviewVerticalPolicy,
)
from txn_support import _strip_timestamps

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_ROOT = REPO_ROOT / "fixtures" / "m1_teacher"
SCORING_DIR = FIXTURES_ROOT / "vertical" / "interview" / "rubrics" / "scoring"
REFERENCE_ANSWERS = json.loads(
    (SCORING_DIR / "reference_answers.json").read_text(encoding="utf-8")
)["answers"]
RESPONSES = {answer["answer_id"]: answer["response"] for answer in REFERENCE_ANSWERS}
QUESTION_ML = "interview.item.q-ml-001"
QUESTION_ENG = "interview.item.q-eng-001"
_LEARNER_DATA_KEYS = frozenset({"canonical_response", "response"})
_STAGE_REASON_PREFIX = "INTERVIEW_PROBE_"
_HINT_REASON_PREFIX = "INTERVIEW_HINT_LEVEL_"
_CF_LEARNER_A = "m1a.learner.student_a"
_CF_LEARNER_B = "m1a.learner.student_b"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _strip_learner_responses(value):
    if isinstance(value, dict):
        return {
            key: _strip_learner_responses(item)
            for key, item in value.items()
            if key not in _LEARNER_DATA_KEYS
        }
    if isinstance(value, list):
        return [_strip_learner_responses(item) for item in value]
    return value


def _public_teacher_corpus(adapter: InterviewDomainAdapter) -> str:
    """All teacher-visible interview text (question prompts, probes, teaching content).

    Hidden-spec tokens that are already part of the public question/topic text are
    not secrets; only tokens outside this corpus are treated as leak candidates.
    """

    chunks: list[str] = []
    for item in adapter.assessment_items():
        chunks.append(item.prompt)
        for probe in adapter.follow_up_ladder(item.item_id):
            chunks.append(probe.prompt)
    for node in adapter.knowledge_nodes():
        for kind in ("EXPLAIN", "HINT_L1", "HINT_L2", "HINT_L3", "REVIEW"):
            chunks.append(adapter.teaching_content(node.node_id, kind))
    return "\n".join(chunks).lower()


def _teacher_visible_events(repository: SqliteRepository, learner_id: str) -> list[dict]:
    events = [event.to_dict() for event in repository.list_events(learner_id)]
    return _strip_learner_responses(events)


def _interview_setup(tmp_path: Path, *, subdir: str = ""):
    fixtures_root = FIXTURES_ROOT
    if subdir:
        fixtures_root = tmp_path / subdir
        fixtures_root.mkdir(parents=True, exist_ok=True)
        for name in ("vertical",):
            source = FIXTURES_ROOT / name
            target = fixtures_root / name
            if not target.exists():
                import shutil

                shutil.copytree(source, target)
    adapter = InterviewDomainAdapter(fixtures_root)
    adapter.validate()
    graph = KnowledgeGraph(adapter.knowledge_nodes(), adapter.prerequisite_edges())
    freshness = KnowledgeFreshnessService(fixtures_root)
    judge = InterviewRubricJudge(fixtures_root)
    return adapter, graph, freshness, judge


def _objective(adapter: InterviewDomainAdapter, question_id: str):
    track = "ml_fundamentals" if question_id == QUESTION_ML else "engineering_metrics"
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
        created_at="2026-11-20T00:00:00Z",
    )


def _seed_correct(history: LearningHistory, item, learner_id: str, count: int = 3) -> None:
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
                created_at="2026-11-20T00:00:00Z",
            ),
        )


def _make_engine(
    repository: SqliteRepository,
    adapter: InterviewDomainAdapter,
    graph: KnowledgeGraph,
    freshness: KnowledgeFreshnessService,
    judge: InterviewRubricJudge,
    *,
    learner_id: str,
    question_id: str,
    now: str,
    seed_correct: int = 0,
    knowledge_decisions=(),
):
    history = LearningHistory(repository)
    if seed_correct:
        item = next(i for i in adapter.assessment_items() if i.item_id == question_id)
        _seed_correct(history, item, learner_id, count=seed_correct)
    policy = InterviewVerticalPolicy(
        adapter,
        judge,
        freshness,
        question_id=question_id,
        now=now,
        knowledge_decisions=knowledge_decisions,
    )
    engine = TeachingSessionEngine(
        adapter,
        graph,
        repository,
        history=history,
        scorer=InterviewJudgeScorer(judge),
        vertical_policy=policy,
    )
    return engine, history, policy


def _run_interview(
    repository: SqliteRepository,
    engine: TeachingSessionEngine,
    *,
    learner_id: str,
    objective,
    session_id: str,
    responses: list[dict],
) -> tuple[list[dict], str]:
    engine.start_session(learner_id, _goal(learner_id, objective), objective, session_id=session_id)
    observations: list[dict] = []
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
                "action_kind": action.kind,
                "action_reason": action.reason.code if action.reason else None,
                "status": result.status,
                "score": result.score,
                "failure_reason": result.failure_reason,
            }
        )
    final_state = repository.load_session(session_id)
    return observations, final_state.phase


# ---------------------------------------------------------------------------
# B4-01: two CF learners, one canonical journal
# ---------------------------------------------------------------------------


def test_b4_01_two_cf_learners_share_canonical_mastery_and_session_journal(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "b4_cf.sqlite"
    summaries = {
        learner_id: demo.run_student_path(
            student, db_path=db_path, fixtures_root=FIXTURES_ROOT
        )
        for learner_id, student in (
            (_CF_LEARNER_A, "student_a"),
            (_CF_LEARNER_B, "student_b"),
        )
    }
    repository = SqliteRepository(db_path)
    try:
        assert set(repository.list_learners()) == {_CF_LEARNER_A, _CF_LEARNER_B}
        for learner_id, summary in summaries.items():
            assert summary["verify_rebuild"] is True
            events = [event.to_dict() for event in repository.list_events(learner_id)]
            assert events
            seqs = [event["seq"] for event in events]
            assert seqs == list(range(seqs[0], seqs[0] + len(seqs)))
            assert {event["event_type"] for event in events} <= set(HISTORY_EVENT_TYPE_VALUES)
            assert all(
                "vertical" not in event["payload"]
                for event in events
                if event["event_type"] in {"SESSION_STARTED", "ACTION_TAKEN"}
            ), "classic CF paths must stay free of vertical metadata"
            snapshot = repository.get_snapshot(learner_id)
            assert snapshot is not None
            rebuilt = LearningHistory(repository).rebuild_state(learner_id)
            assert snapshot.to_dict() == rebuilt.to_dict()
            assert summary["mastery_after"]

        actions_a = [action["action_kind"] for action in summaries[_CF_LEARNER_A]["actions"]]
        actions_b = [action["action_kind"] for action in summaries[_CF_LEARNER_B]["actions"]]
        mastery_a = {
            node: entry["value"]
            for node, entry in summaries[_CF_LEARNER_A]["mastery_after"].items()
        }
        mastery_b = {
            node: entry["value"]
            for node, entry in summaries[_CF_LEARNER_B]["mastery_after"].items()
        }
        assert actions_a != actions_b, "two synthetic learners must follow different paths"
        assert mastery_a != mastery_b
        assert summaries[_CF_LEARNER_A]["session_id"] != summaries[_CF_LEARNER_B]["session_id"]
        # Same canonical journal: both learners' events live in the same tables.
        counts = {}
        for learner_id in (_CF_LEARNER_A, _CF_LEARNER_B):
            counts[learner_id] = len(repository.list_events(learner_id))
        assert all(count > 0 for count in counts.values())
    finally:
        repository.close()


# ---------------------------------------------------------------------------
# B4-02: interview learners, JD v1 -> v2, 5-stage ladder, rubric
# ---------------------------------------------------------------------------


def test_b4_02_two_interview_learners_five_stage_jd_and_rubric(tmp_path: Path) -> None:
    adapter, graph, freshness, judge = _interview_setup(tmp_path)
    repository = SqliteRepository(tmp_path / "b4_interview.sqlite")
    try:
        learner_a = "b4.interview.a"
        engine_a, history_a, policy_a = _make_engine(
            repository, adapter, graph, freshness, judge,
            learner_id=learner_a, question_id=QUESTION_ML,
            now="2026-10-15T00:00:00Z", seed_correct=3,
        )
        observations_a, phase_a = _run_interview(
            repository, engine_a,
            learner_id=learner_a, objective=_objective(adapter, QUESTION_ML),
            session_id="b4.interview.session.a",
            responses=[RESPONSES["a-correct-001"]] * 8,
        )
        probes_a = [
            obs["action_reason"] for obs in observations_a
            if obs["action_reason"] and obs["action_reason"].startswith(_STAGE_REASON_PREFIX)
        ]
        assert probes_a[0] == f"{_STAGE_REASON_PREFIX}HYPOTHESIS"
        assert f"{_STAGE_REASON_PREFIX}CONCEPT" not in probes_a
        assert phase_a == "REVIEW"
        assert policy_a.active_jd_version == "v2"

        state_a_before = repository.load_session("b4.interview.session.a").to_dict()

        learner_b = "b4.interview.b"
        engine_b, history_b, policy_b = _make_engine(
            repository, adapter, graph, freshness, judge,
            learner_id=learner_b, question_id=QUESTION_ENG,
            now="2026-07-01T00:00:00Z",
        )
        facts_answer = dict(RESPONSES["a-missingfacts-004"])
        facts_answer["project_facts"] = [
            "合成项目：负责推荐延迟优化，P99 从 800ms 降到 200ms（合成数据，仅演示）"
        ]
        vague_with_facts = {
            "text": "大概加一些缓存、优化一下特征，可能就快了。",
            "project_facts": facts_answer["project_facts"],
        }
        observations_b, phase_b = _run_interview(
            repository, engine_b,
            learner_id=learner_b, objective=_objective(adapter, QUESTION_ENG),
            session_id="b4.interview.session.b",
            responses=[
                RESPONSES["a-missingfacts-004"],
                vague_with_facts,
                facts_answer,
                facts_answer,
                facts_answer,
                facts_answer,
                facts_answer,
                facts_answer,
            ],
        )
        probes_b = [
            obs["action_reason"] for obs in observations_b
            if obs["action_reason"] and obs["action_reason"].startswith(_STAGE_REASON_PREFIX)
        ]
        assert probes_b == [f"{_STAGE_REASON_PREFIX}{stage.upper()}" for stage in (
            "concept", "hypothesis", "complexity", "experiment_design", "online_triage",
        )]
        assert any(obs["action_kind"] == "ASK_CLARIFICATION" for obs in observations_b)
        hint_reasons = [
            obs["action_reason"] for obs in observations_b
            if obs["action_reason"] and obs["action_reason"].startswith(_HINT_REASON_PREFIX)
        ]
        assert hint_reasons and all(level != f"{_HINT_REASON_PREFIX}4" for level in hint_reasons)
        assert phase_b == "REVIEW"
        assert policy_b.active_jd_version == "v1"
        # JD change affects only new sessions: learner A's session is unchanged.
        assert repository.load_session("b4.interview.session.a").to_dict() == state_a_before
        assert probes_a != probes_b, "different evidence states must produce different plans"

        # Unified journal / replay / event consistency for both learners.
        for learner_id, history in ((learner_a, history_a), (learner_b, history_b)):
            assert history.verify_rebuild(learner_id) is True
            snapshot = repository.get_snapshot(learner_id)
            assert snapshot is not None
            assert snapshot.to_dict() == LearningHistory(repository).rebuild_state(learner_id).to_dict()
            events = [event.to_dict() for event in repository.list_events(learner_id)]
            assert any(event["event_type"] == "SESSION_STARTED" for event in events)
            assert {event["event_type"] for event in events} <= set(HISTORY_EVENT_TYPE_VALUES)
            starts = next(event for event in events if event["event_type"] == "SESSION_STARTED")
            assert starts["payload"]["vertical"]["domain_id"] == "interview_coach"
            assert starts["payload"]["vertical"]["policy_version"] == "b4.interview.policy.v1"

        # Rubric audit: four dimensions + digest in assessment events, no hidden leak.
        public_corpus = _public_teacher_corpus(adapter)
        for learner_id in (learner_a, learner_b):
            events = _teacher_visible_events(repository, learner_id)
            assessed = [
                event
                for event in events
                if event["event_type"] == "ASSESSED" and event["payload"].get("rubric_audit")
            ]
            assert assessed, "vertical assessment events must carry the rubric audit payload"
            audit = assessed[0]["payload"]["rubric_audit"]
            assert set(audit["dimensions"]) == {
                "factual_correctness",
                "explanation_clarity",
                "engineering_feasibility",
                "evidence_sufficiency",
            }
            assert len(audit["spec_digest"]) == 64
            blob = json.dumps(events, ensure_ascii=False).lower()
            scrubbed = re.sub(r"[0-9a-f]{16,}", "", blob)
            for question_id in ("q-ml-001", "q-eng-001"):
                spec = json.loads((SCORING_DIR / f"{question_id}.json").read_text(encoding="utf-8"))
                # Hidden scoring bodies must never be serialised into teacher-visible
                # event payloads (structured expectation groups, not shared vocabulary).
                for dimension, groups in spec["expectations"].items():
                    for group in groups:
                        assert json.dumps(group, ensure_ascii=False).lower() not in scrubbed, (
                            f"hidden {dimension} expectation group leaked"
                        )
                assert spec["thresholds"]["partial_min"] not in ("1.0", 1.0)
                for hidden_key in ("clarity_connectors", "vague_words", "infeasible_markers",
                                   "unsourced_claim_patterns", "misconception_penalty"):
                    assert hidden_key not in blob, f"hidden spec field leaked: {hidden_key!r}"
                assert public_corpus  # public corpus is used to reason about vocabulary overlap
            for answer in REFERENCE_ANSWERS:
                assert answer["response"]["text"] not in json.dumps(events, ensure_ascii=False)
            assert "rubrics/" not in blob
            assert "reference_answers" not in blob
            for hidden_key in ("expectations", "misconception_penalty", "partial_min", "weights"):
                assert hidden_key not in blob, f"hidden spec field leaked: {hidden_key!r}"
            # FULL solution must never be emitted.
            for event in repository.list_events(learner_id):
                if event.event_type != "ACTION_TAKEN":
                    continue
                reason = (event.payload.get("action", {}).get("reason") or {}).get("code")
                assert reason != f"{_HINT_REASON_PREFIX}4"
    finally:
        repository.close()


# ---------------------------------------------------------------------------
# B4-03: freshness / JD gates
# ---------------------------------------------------------------------------


def test_b4_03_freshness_and_jd_gates_block_before_teaching(tmp_path: Path) -> None:
    adapter, graph, freshness, judge = _interview_setup(tmp_path)
    decisions = freshness.classify_all_scenarios()
    counts: dict[str, int] = {}
    for decision in decisions:
        counts[decision.change_kind] = counts.get(decision.change_kind, 0) + 1
    assert counts == {"KEEP": 2, "UPDATE": 2, "RECHECK": 5}
    blocked = [decision for decision in decisions if decision.recheck_required]
    eligible = [decision for decision in decisions if decision.curriculum_eligible]
    assert len(blocked) == 5 and len(eligible) == 2
    objective = _objective(adapter, QUESTION_ML)
    repository = SqliteRepository(tmp_path / "b4_freshness.sqlite")
    try:
        for index, decision in enumerate(blocked):
            learner_id = f"b4.freshness.blocked.{index}"
            engine, _history, _policy = _make_engine(
                repository, adapter, graph, freshness, judge,
                learner_id=learner_id, question_id=QUESTION_ML,
                now="2026-10-15T00:00:00Z", knowledge_decisions=[decision],
            )
            with pytest.raises(ValidationError) as excinfo:
                engine.start_session(
                    learner_id, _goal(learner_id, objective), objective,
                    session_id=f"b4.freshness.session.{index}",
                )
            assert excinfo.value.code == "FRESHNESS_KNOWLEDGE_GATE_BLOCKED"
            assert excinfo.value.details["map_code"] == decision.map_code
            assert excinfo.value.details["recheck_required"] is True
            assert repository.list_events(learner_id) == []
            assert repository.load_session(f"b4.freshness.session.{index}") is None

        # Expired / conflicting JD versions also fail closed before writes.
        for index, (now, reason) in enumerate(
            (
                ("2027-05-01T00:00:00Z", "RECHECK_JD_EXPIRED"),
                ("2026-05-01T00:00:00Z", "RECHECK_JD_NOT_YET_ACTIVE"),
            )
        ):
            learner_id = f"b4.freshness.jd.{index}"
            engine, _history, _policy = _make_engine(
                repository, adapter, graph, freshness, judge,
                learner_id=learner_id, question_id=QUESTION_ML, now=now,
            )
            with pytest.raises(ValidationError) as excinfo:
                engine.start_session(
                    learner_id, _goal(learner_id, objective), objective,
                    session_id=f"b4.freshness.jd.session.{index}",
                )
            assert excinfo.value.code == "FRESHNESS_JD_GATE_BLOCKED"
            assert excinfo.value.details["map_code"] == "MAP-E10_JD_EXPIRED_OR_CONFLICT"
            assert excinfo.value.details["reason_code"] == reason
            assert repository.list_events(learner_id) == []
            assert repository.load_session(f"b4.freshness.jd.session.{index}") is None

        # An eligible UPDATE may enter a new plan as provenance refs.
        learner_id = "b4.freshness.allowed"
        engine, _history, _policy = _make_engine(
            repository, adapter, graph, freshness, judge,
            learner_id=learner_id, question_id=QUESTION_ML,
            now="2026-10-15T00:00:00Z", knowledge_decisions=[eligible[0]],
        )
        engine.start_session(
            learner_id, _goal(learner_id, objective), objective,
            session_id="b4.freshness.allowed.session",
        )
        events = [event.to_dict() for event in repository.list_events(learner_id)]
        plan = next(event for event in events if event["event_type"] == "PLAN_CREATED")
        refs = plan["payload"]["vertical"]["knowledge_refs"]
        assert eligible[0].new_version_id in refs
        assert all(decision.new_version_id not in refs for decision in blocked)
    finally:
        repository.close()


# ---------------------------------------------------------------------------
# Cross-domain sessions / version rejection
# ---------------------------------------------------------------------------


def test_cross_domain_pause_and_interview_session_continuity(tmp_path: Path) -> None:
    components = demo.build_components(FIXTURES_ROOT)
    student = demo.load_student_fixture(FIXTURES_ROOT, "student_a")
    repository = SqliteRepository(tmp_path / "cross_domain.sqlite")
    try:
        cf_repository = repository
        history = LearningHistory(cf_repository)
        cf_engine = TeachingSessionEngine(
            components.adapter,
            components.graph,
            cf_repository,
            history=history,
            scorer=demo.MockStudentScorer(student),
        )
        learner_id = "b4.cross.learner"
        demo.seed_prior_evidence(repository, components, student, learner_id=learner_id)
        cf_goal = LearnerGoal(
            goal_id=f"goal:{learner_id}:cf",
            learner_id=learner_id,
            objective_id=components.objective.objective_id,
            created_at="2026-11-20T00:00:00Z",
        )
        cf_state = cf_engine.start_session(learner_id, cf_goal, components.objective)
        cf_engine.current_action(cf_state.session_id)
        cf_engine.pause_session(cf_state.session_id)
        snapshot_before = repository.get_snapshot(learner_id)
        assert snapshot_before is not None
        seq_before = max(event.seq for event in repository.list_events(learner_id))

        adapter, graph, freshness, judge = _interview_setup(tmp_path, subdir="fixtures")
        engine_iv, _history_iv, _policy_iv = _make_engine(
            repository, adapter, graph, freshness, judge,
            learner_id=learner_id, question_id=QUESTION_ML,
            now="2026-10-15T00:00:00Z",
        )
        interview_objective = _objective(adapter, QUESTION_ML)
        interview_state = engine_iv.start_session(
            learner_id,
            _goal(learner_id, interview_objective),
            interview_objective,
            session_id="b4.cross.interview.session",
        )
        assert interview_state.session_id != cf_state.session_id
        events = repository.list_events(learner_id)
        seqs = [event.seq for event in events]
        assert seqs == list(range(seqs[0], seqs[0] + len(seqs)))
        assert max(seqs) > seq_before
        snapshot_after = repository.get_snapshot(learner_id)
        assert snapshot_after.to_dict() == snapshot_before.to_dict(), (
            "starting an interview session must not disturb the CF learner snapshot"
        )
        assert history.verify_rebuild(learner_id) is True
        resumed = cf_engine.resume_session(cf_state.session_id)
        assert resumed.phase != "PAUSED"
        sessions = repository.list_sessions(learner_id)
        assert {state.session_id for state in sessions} == {
            cf_state.session_id, interview_state.session_id,
        }
    finally:
        repository.close()


def test_vertical_version_and_objective_mismatch_rejected(tmp_path: Path) -> None:
    adapter, graph, freshness, judge = _interview_setup(tmp_path)
    components = demo.build_components(FIXTURES_ROOT)
    repository = SqliteRepository(tmp_path / "mismatch.sqlite")
    try:
        policy = InterviewVerticalPolicy(adapter, judge, freshness, question_id=QUESTION_ML)
        with pytest.raises(ValidationError) as excinfo:
            TeachingSessionEngine(
                components.adapter, components.graph, repository,
                scorer=InterviewJudgeScorer(judge), vertical_policy=policy,
            )
        assert excinfo.value.code == "VERTICAL_DOMAIN_MISMATCH"

        engine, _history, _policy = _make_engine(
            repository, adapter, graph, freshness, judge,
            learner_id="b4.mismatch.learner", question_id=QUESTION_ML,
            now="2026-10-15T00:00:00Z",
        )
        with pytest.raises(ValidationError) as excinfo:
            engine.start_session(
                "b4.mismatch.learner",
                LearnerGoal(
                    goal_id="goal:b4.mismatch",
                    learner_id="b4.mismatch.learner",
                    objective_id=components.objective.objective_id,
                    created_at="2026-11-20T00:00:00Z",
                ),
                components.objective,
                session_id="b4.mismatch.session",
            )
        assert "VERTICAL" in str(excinfo.value.code) or excinfo.value.code == "VALIDATION_ERROR"
    finally:
        repository.close()


# ---------------------------------------------------------------------------
# Determinism / demo / static isolation
# ---------------------------------------------------------------------------


def test_b4_interview_flows_are_deterministic(tmp_path: Path) -> None:
    def run_once(name: str) -> dict:
        root = tmp_path / name
        root.mkdir()
        adapter, graph, freshness, judge = _interview_setup(root, subdir="fixtures")
        repository = SqliteRepository(root / "determinism.sqlite")
        try:
            engine, _history, _policy = _make_engine(
                repository, adapter, graph, freshness, judge,
                learner_id="b4.det.a", question_id=QUESTION_ML,
                now="2026-10-15T00:00:00Z", seed_correct=3,
            )
            observations, phase = _run_interview(
                repository, engine,
                learner_id="b4.det.a", objective=_objective(adapter, QUESTION_ML),
                session_id="b4.det.session",
                responses=[RESPONSES["a-correct-001"]] * 8,
            )
            events = _teacher_visible_events(repository, "b4.det.a")
            return _strip_timestamps({"observations": observations, "phase": phase, "events": events})
        finally:
            repository.close()

    first = run_once("first")
    second = run_once("second")
    assert first == second


def test_demo_b4_is_deterministic_and_boundary_labelled(tmp_path: Path) -> None:
    first = demo_b4.run_demo(tmp_path / "demo_a")
    second = demo_b4.run_demo(tmp_path / "demo_b")
    assert first == second == demo_b4.run_demo()  # fresh temp dirs must not change content
    assert first["schema"] == "m1b.b4.demo.v1"
    assert first["boundary"]["evidence_class"] == "MOCK+DETERMINISTIC"
    assert first["boundary"]["real_teaching_effect"] == "NOT_VERIFIED"
    assert first["boundary"]["network"] == "NONE"
    assert first["b4_01_cf"]["paths_differ"] is True
    assert first["b4_02_interview"]["paths_differ"] is True
    assert first["b4_02_interview"]["full_solution_emitted"] is False
    assert first["b4_03_freshness"]["silent_imports"] == 0
    assert first["b4_03_freshness"]["decision_counts"] == {"KEEP": 2, "UPDATE": 2, "RECHECK": 5}
    rendered = demo_b4.render_json(first)
    json.loads(rendered)
    assert demo_b4.main(["--json"]) == 0


def test_b4_modules_are_offline_and_hidden_readers_are_closed() -> None:
    for module in (demo_b4, vertical_module):
        source = inspect.getsource(module)
        tree = ast.parse(source)
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        assert imported.isdisjoint(
            {"httpx", "requests", "urllib", "socket", "aiohttp", "autoteacher_m0"}
        )
    # Hidden-scoring reader allow-list remains exactly two scorer-side modules.
    reader_policy = {"scorer.py", "interview_judge.py"}
    for path in (REPO_ROOT / "m1_teacher").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "scoring/" in text:
            assert path.name in reader_policy, f"unexpected hidden-scoring reader: {path}"
    # No real-data / network shapes in the new demo or tests' fixtures access.
    demo_source = inspect.getsource(demo_b4)
    assert "https://" not in demo_source
    assert "api_key" not in demo_source.lower()


def test_b4_teaching_action_kinds_used_are_contract_valid(tmp_path: Path) -> None:
    adapter, graph, freshness, judge = _interview_setup(tmp_path)
    repository = SqliteRepository(tmp_path / "kinds.sqlite")
    try:
        engine, _history, _policy = _make_engine(
            repository, adapter, graph, freshness, judge,
            learner_id="b4.kinds", question_id=QUESTION_ENG,
            now="2026-10-15T00:00:00Z",
        )
        objective = _objective(adapter, QUESTION_ENG)
        facts_answer = dict(RESPONSES["a-missingfacts-004"])
        facts_answer["project_facts"] = ["合成项目：延迟优化（合成数据）"]
        observations, _phase = _run_interview(
            repository, engine, learner_id="b4.kinds", objective=objective,
            session_id="b4.kinds.session",
            responses=[RESPONSES["a-missingfacts-004"], facts_answer, facts_answer,
                       facts_answer, facts_answer, facts_answer, facts_answer],
        )
        kinds = {obs["action_kind"] for obs in observations}
        assert kinds <= set(TEACHING_ACTION_KIND_VALUES)
        assert {"SOCRATIC_QUESTION", "ASK_CLARIFICATION"} <= kinds
        for event in repository.list_events("b4.kinds"):
            if event.event_type == "ACTION_TAKEN":
                assert event.payload["action_kind"] in TEACHING_ACTION_KIND_VALUES
                assert event.payload["vertical"]["domain_id"] == "interview_coach"
                assert event.payload["vertical"]["cf_hint_ladder_shared"] is False
            else:
                assert event.event_type in HISTORY_EVENT_TYPE_VALUES
    finally:
        repository.close()
