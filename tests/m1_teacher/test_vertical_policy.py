"""Tests for the B-PR4 additive vertical policy seam and interview vertical policy.

Covers: additive action-kind values (D12), engine/vertical protocol validation,
five-stage interview sessions over the canonical event log, learner-state
acceleration, project-fact clarification (no fabrication), the separate
interview support ladder with FULL disabled by default, four-dimension rubric
audit payloads without hidden-material leakage, NEEDS_REVIEW/EVAL_ERROR mastery
neutrality, JD/freshness gates that fail closed before any write, event/replay
consistency and offline/no-writer isolation.
"""

from __future__ import annotations

import ast
import inspect
import json
import re
import shutil
from pathlib import Path

import pytest

from m1_teacher.assessment.interview_judge import InterviewRubricJudge
from m1_teacher.contracts.errors import ValidationError
from m1_teacher.contracts.types import (
    TEACHING_ACTION_KIND_VALUES,
    AssessmentResult,
    LearnerGoal,
)
from m1_teacher.domains.interview import FOLLOW_UP_STAGES, InterviewDomainAdapter
from m1_teacher.knowledge.freshness import KnowledgeFreshnessService
from m1_teacher.knowledge.graph import KnowledgeGraph
from m1_teacher.learner.history import LearningHistory
from m1_teacher.learner.repository import SqliteRepository
from m1_teacher.session import vertical as vertical_module
from m1_teacher.session.engine import TeachingSessionEngine
from m1_teacher.session.vertical import (
    ACCELERATED_MASTERY_THRESHOLD,
    INTERVIEW_HINT_LADDER,
    MAX_INTERVIEW_HINT_LEVEL,
    InterviewJudgeScorer,
    InterviewVerticalPolicy,
    VerticalPolicy,
)
from txn_support import _strip_timestamps  # local test support helper

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_ROOT = REPO_ROOT / "fixtures" / "m1_teacher"
SCORING_DIR = FIXTURES_ROOT / "vertical" / "interview" / "rubrics" / "scoring"
REFERENCE_ANSWERS = json.loads(
    (SCORING_DIR / "reference_answers.json").read_text(encoding="utf-8")
)["answers"]
RESPONSES = {answer["answer_id"]: answer["response"] for answer in REFERENCE_ANSWERS}
QUESTION_ML = "interview.item.q-ml-001"
QUESTION_ENG = "interview.item.q-eng-001"

CLAIM_RE = re.compile(r"(?:提升|增长|提高|降低|下降)\s*\d+(?:\.\d+)?\s*(?:%|％|倍)")


@pytest.fixture(scope="module")
def adapter() -> InterviewDomainAdapter:
    instance = InterviewDomainAdapter(FIXTURES_ROOT)
    instance.validate()
    return instance


@pytest.fixture(scope="module")
def graph(adapter: InterviewDomainAdapter) -> KnowledgeGraph:
    return KnowledgeGraph(adapter.knowledge_nodes(), adapter.prerequisite_edges())


@pytest.fixture(scope="module")
def freshness() -> KnowledgeFreshnessService:
    return KnowledgeFreshnessService(FIXTURES_ROOT)


@pytest.fixture(scope="module")
def judge() -> InterviewRubricJudge:
    return InterviewRubricJudge(FIXTURES_ROOT)


def _objective(adapter: InterviewDomainAdapter, track: str):
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


def _seed_correct(
    history: LearningHistory,
    item,
    learner_id: str,
    *,
    count: int = 3,
    session_id: str = "seed:interview",
) -> None:
    for index in range(count):
        result = AssessmentResult(
            result_id=f"seed:{learner_id}:{index}",
            item_id=item.item_id,
            learner_id=learner_id,
            status="CORRECT",
            score=1.0,
            max_score=1.0,
            scorer_id="synthetic.seed",
            created_at="2026-11-20T00:00:00Z",
        )
        history.apply_assessment(learner_id, session_id, item, result)


def _make_interview_engine(
    tmp_path: Path,
    adapter: InterviewDomainAdapter,
    graph: KnowledgeGraph,
    freshness: KnowledgeFreshnessService,
    judge: InterviewRubricJudge,
    *,
    learner_id: str,
    question_id: str,
    now: str = "2026-10-15T00:00:00Z",
    knowledge_decisions=(),
    seed_correct: int = 0,
    corrupt_spec: bool = False,
):
    if corrupt_spec:
        fixtures_root = tmp_path / "fixtures" / "m1_teacher"
        fixtures_root.mkdir(parents=True)
        shutil.copytree(FIXTURES_ROOT / "vertical", fixtures_root / "vertical")
        spec = (
            fixtures_root
            / "vertical"
            / "interview"
            / "rubrics"
            / "scoring"
            / f"{question_id.split('interview.item.')[1]}.json"
        )
        spec.write_text("{corrupt", encoding="utf-8")
        local_adapter = InterviewDomainAdapter(fixtures_root)
        local_graph = KnowledgeGraph(
            local_adapter.knowledge_nodes(), local_adapter.prerequisite_edges()
        )
        local_freshness = KnowledgeFreshnessService(fixtures_root)
        local_judge = InterviewRubricJudge(fixtures_root)
        adapter, graph, freshness, judge = (
            local_adapter,
            local_graph,
            local_freshness,
            local_judge,
        )
    repository = SqliteRepository(tmp_path / "vertical.sqlite")
    history = LearningHistory(repository)
    if seed_correct:
        item = next(
            candidate
            for candidate in adapter.assessment_items()
            if candidate.item_id == question_id
        )
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
    return engine, repository, history, policy


def _run_flow(
    engine: TeachingSessionEngine,
    repository: SqliteRepository,
    *,
    learner_id: str,
    objective,
    session_id: str,
    responses: dict[int, dict],
    max_steps: int = 16,
) -> tuple[list[dict], str]:
    state = engine.start_session(learner_id, _goal(learner_id, objective), objective, session_id=session_id)
    observations: list[dict] = []
    for step in range(max_steps):
        state = repository.load_session(session_id)
        if state.pending_item_id is None:
            break
        action = engine.current_action(session_id)
        response = responses.get(step)
        if response is None:
            break
        result = engine.submit_response(session_id, state.pending_item_id, response)
        observations.append(
            {
                "action_kind": action.kind,
                "action_reason": action.reason.code if action.reason else None,
                "action_content": action.content,
                "status": result.status,
                "score": result.score,
                "failure_reason": result.failure_reason,
                "turn": state.turn_index,
                "phase": state.phase,
            }
        )
    final_state = repository.load_session(session_id)
    return observations, final_state.phase


_LEARNER_DATA_KEYS = frozenset({"canonical_response", "response"})


def _strip_learner_responses(value):
    """Drop learner-owned response text so leak scans target teacher-visible data only."""

    if isinstance(value, dict):
        return {
            key: _strip_learner_responses(item)
            for key, item in value.items()
            if key not in _LEARNER_DATA_KEYS
        }
    if isinstance(value, list):
        return [_strip_learner_responses(item) for item in value]
    return value


def _teacher_visible_event_blob(repository: SqliteRepository, learner_id: str) -> str:
    events = [event.to_dict() for event in repository.list_events(learner_id)]
    return json.dumps(_strip_learner_responses(events), ensure_ascii=False)


def _public_teacher_corpus(adapter: InterviewDomainAdapter) -> str:
    chunks: list[str] = []
    for item in adapter.assessment_items():
        chunks.append(item.prompt)
        for probe in adapter.follow_up_ladder(item.item_id):
            chunks.append(probe.prompt)
    for node in adapter.knowledge_nodes():
        for kind in ("EXPLAIN", "HINT_L1", "HINT_L2", "HINT_L3", "REVIEW"):
            chunks.append(adapter.teaching_content(node.node_id, kind))
    return "\n".join(chunks).lower()


def _event_payloads(repository: SqliteRepository, learner_id: str) -> list[dict]:
    return [event.to_dict() for event in repository.list_events(learner_id)]


# ---------------------------------------------------------------------------
# Contract / protocol / adapter
# ---------------------------------------------------------------------------


def test_additive_action_kind_values_are_appended_only() -> None:
    assert "SOCRATIC_QUESTION" in TEACHING_ACTION_KIND_VALUES
    assert "ASK_CLARIFICATION" in TEACHING_ACTION_KIND_VALUES
    assert TEACHING_ACTION_KIND_VALUES[-2:] == ("SOCRATIC_QUESTION", "ASK_CLARIFICATION")
    # Existing frozen values are untouched.
    assert TEACHING_ACTION_KIND_VALUES[:10] == (
        "DIAGNOSE",
        "EXPLAIN",
        "HINT",
        "PRACTICE",
        "REVIEW",
        "RETEACH",
        "REASSESS",
        "GOAL_COMPLETE",
        "SESSION_PAUSE",
        "SESSION_RESUME",
    )


def test_judge_scorer_adapter_matches_direct_judge(
    adapter: InterviewDomainAdapter, judge: InterviewRubricJudge
) -> None:
    item = next(i for i in adapter.assessment_items() if i.item_id == QUESTION_ML)
    scorer = InterviewJudgeScorer(judge)
    response = RESPONSES["a-correct-001"]
    result = scorer.score(item, "learner:adapter", response)
    direct = judge.assess(item, "learner:adapter", response, result_id=result.result_id)
    assert result.to_dict() == direct.to_dict()
    assert scorer.scorer_id == judge.scorer_id
    assert scorer.detail(result.result_id) is not None
    with pytest.raises(ValidationError):
        InterviewJudgeScorer("not-a-judge")  # type: ignore[arg-type]


def test_engine_without_vertical_policy_keeps_classic_cf_paths(tmp_path: Path) -> None:
    from m1_teacher import demo

    components = demo.build_components(FIXTURES_ROOT)
    student = demo.load_student_fixture(FIXTURES_ROOT, "student_a")
    repository = SqliteRepository(tmp_path / "cf.sqlite")
    history = LearningHistory(repository)
    engine = TeachingSessionEngine(
        components.adapter,
        components.graph,
        repository,
        history=history,
        scorer=demo.MockStudentScorer(student),
    )
    assert engine.vertical_policy is None
    learner_id = "learner:cf:compat"
    goal = LearnerGoal(
        goal_id=f"goal:{learner_id}",
        learner_id=learner_id,
        objective_id=components.objective.objective_id,
        created_at="2026-11-20T00:00:00Z",
    )
    state = engine.start_session(learner_id, goal, components.objective)
    engine.current_action(state.session_id)
    events = [event.to_dict() for event in repository.list_events(learner_id)]
    session_started = next(event for event in events if event["event_type"] == "SESSION_STARTED")
    action_taken = next(event for event in events if event["event_type"] == "ACTION_TAKEN")
    assert "vertical" not in session_started["payload"]
    assert "vertical" not in action_taken["payload"]


def test_engine_rejects_cross_domain_vertical_policy(
    tmp_path: Path,
    adapter: InterviewDomainAdapter,
    graph: KnowledgeGraph,
    freshness: KnowledgeFreshnessService,
    judge: InterviewRubricJudge,
) -> None:
    from m1_teacher import demo

    components = demo.build_components(FIXTURES_ROOT)
    repository = SqliteRepository(tmp_path / "cross.sqlite")
    policy = InterviewVerticalPolicy(
        adapter, judge, freshness, question_id=QUESTION_ML
    )
    with pytest.raises(ValidationError) as excinfo:
        TeachingSessionEngine(
            components.adapter,
            components.graph,
            repository,
            scorer=InterviewJudgeScorer(judge),
            vertical_policy=policy,
        )
    assert excinfo.value.code == "VERTICAL_DOMAIN_MISMATCH"
    assert isinstance(policy, VerticalPolicy)


# ---------------------------------------------------------------------------
# Multi-turn five-stage interview
# ---------------------------------------------------------------------------


def test_interview_five_stage_sequence_and_replay(
    tmp_path: Path,
    adapter: InterviewDomainAdapter,
    graph: KnowledgeGraph,
    freshness: KnowledgeFreshnessService,
    judge: InterviewRubricJudge,
) -> None:
    learner_id = "learner:iv:five"
    engine, repository, history, _policy = _make_interview_engine(
        tmp_path, adapter, graph, freshness, judge,
        learner_id=learner_id, question_id=QUESTION_ML,
    )
    objective = _objective(adapter, "ml_fundamentals")
    responses = {step: RESPONSES["a-correct-001"] for step in range(10)}
    observations, phase = _run_flow(
        engine, repository,
        learner_id=learner_id, objective=objective,
        session_id="iv:five", responses=responses,
    )
    reasons = [obs["action_reason"] for obs in observations]
    assert reasons[0] == "INTERVIEW_MAIN_QUESTION"
    probe_reasons = [
        reason for reason in reasons if reason and reason.startswith("INTERVIEW_PROBE_")
    ]
    assert probe_reasons == [
        f"INTERVIEW_PROBE_{stage.upper()}" for stage in FOLLOW_UP_STAGES
    ]
    assert all(obs["action_kind"] == "SOCRATIC_QUESTION" for obs in observations)
    assert len(observations) == 1 + len(FOLLOW_UP_STAGES)
    assert phase == "REVIEW"
    assert repository.load_session("iv:five").pending_item_id is None
    assert history.verify_rebuild(learner_id) is True

    events = [event.to_dict() for event in repository.list_events(learner_id)]
    allowed_event_types = {
        "SESSION_STARTED", "PLAN_CREATED", "DIAGNOSIS_COMPLETED", "ITEM_PRESENTED",
        "RESPONSE_SUBMITTED", "ASSESSED", "ASSESSMENT_PREPARED", "MASTERY_UPDATED",
        "ACTION_TAKEN", "SESSION_PAUSED", "SESSION_RESUMED", "GOAL_COMPLETED", "ERROR",
    }
    assert {event["event_type"] for event in events} <= allowed_event_types
    session_events = [event for event in events if event["session_id"] == "iv:five"]
    seqs = [event["seq"] for event in session_events]
    assert seqs == list(range(seqs[0], seqs[0] + len(seqs)))
    assert [event["payload"].get("turn_index") for event in session_events if event["event_type"] == "ACTION_TAKEN"] == list(range(0, len(observations), 1))


def test_requires_project_facts_triggers_ask_clarification_without_fabrication(
    tmp_path: Path,
    adapter: InterviewDomainAdapter,
    graph: KnowledgeGraph,
    freshness: KnowledgeFreshnessService,
    judge: InterviewRubricJudge,
) -> None:
    learner_id = "learner:iv:clarify"
    engine, repository, history, _policy = _make_interview_engine(
        tmp_path, adapter, graph, freshness, judge,
        learner_id=learner_id, question_id=QUESTION_ENG,
    )
    objective = _objective(adapter, "engineering_metrics")
    response_with_facts = dict(RESPONSES["a-missingfacts-004"])
    response_with_facts["project_facts"] = [
        "合成项目：负责推荐延迟优化，P99 从 800ms 降到 200ms（合成数据，仅演示）"
    ]
    responses = {
        0: RESPONSES["a-missingfacts-004"],
        1: response_with_facts,
        **{step: response_with_facts for step in range(2, 12)},
    }
    observations, phase = _run_flow(
        engine, repository,
        learner_id=learner_id, objective=objective,
        session_id="iv:clarify", responses=responses,
    )
    assert observations[0]["status"] == "NEEDS_REVIEW"
    assert observations[0]["failure_reason"] == "NEEDS_REVIEW:PROJECT_FACTS_REQUIRED"
    assert observations[1]["action_kind"] == "ASK_CLARIFICATION"
    assert observations[1]["action_reason"] == "PROJECT_FACTS_REQUIRED"
    clarify_content = observations[1]["action_content"]
    assert "不会替你编造" in clarify_content
    assert CLAIM_RE.search(clarify_content) is None, "clarification must not invent metrics"
    # After the learner supplies facts, the ladder continues.
    assert observations[2]["action_reason"] == "INTERVIEW_PROBE_CONCEPT"
    assert phase == "REVIEW"
    assert history.verify_rebuild(learner_id) is True


def test_non_project_needs_review_does_not_ask_for_project_facts(
    tmp_path: Path,
    adapter: InterviewDomainAdapter,
    graph: KnowledgeGraph,
    freshness: KnowledgeFreshnessService,
    judge: InterviewRubricJudge,
) -> None:
    learner_id = "learner:iv:short"
    engine, repository, _history, _policy = _make_interview_engine(
        tmp_path, adapter, graph, freshness, judge,
        learner_id=learner_id, question_id=QUESTION_ML,
    )
    objective = _objective(adapter, "ml_fundamentals")
    observations, _phase = _run_flow(
        engine, repository,
        learner_id=learner_id, objective=objective,
        session_id="iv:short",
        responses={0: {"text": "不知道"}},
        max_steps=2,
    )
    assert observations[0]["status"] == "NEEDS_REVIEW"
    assert all(obs["action_kind"] != "ASK_CLARIFICATION" for obs in observations)


def test_learner_state_acceleration_skips_concept_probe(
    tmp_path: Path,
    adapter: InterviewDomainAdapter,
    graph: KnowledgeGraph,
    freshness: KnowledgeFreshnessService,
    judge: InterviewRubricJudge,
) -> None:
    item = next(i for i in adapter.assessment_items() if i.item_id == QUESTION_ML)
    responses = {step: RESPONSES["a-correct-001"] for step in range(10)}

    accelerated_root = tmp_path / "accelerated"
    accelerated_root.mkdir()
    engine_a, repo_a, _history_a, _policy_a = _make_interview_engine(
        accelerated_root, adapter, graph, freshness, judge,
        learner_id="learner:iv:advanced", question_id=QUESTION_ML, seed_correct=3,
    )
    snapshot = repo_a.get_snapshot("learner:iv:advanced")
    assert snapshot is not None
    estimate = snapshot.masteries[item.node_ids[0]]
    assert estimate.value >= ACCELERATED_MASTERY_THRESHOLD
    observations_a, _phase = _run_flow(
        engine_a, repo_a,
        learner_id="learner:iv:advanced", objective=_objective(adapter, "ml_fundamentals"),
        session_id="iv:advanced", responses=responses,
    )
    probe_reasons_a = [
        obs["action_reason"]
        for obs in observations_a
        if obs["action_reason"] and obs["action_reason"].startswith("INTERVIEW_PROBE_")
    ]
    assert probe_reasons_a[0] == "INTERVIEW_PROBE_HYPOTHESIS"
    assert "INTERVIEW_PROBE_CONCEPT" not in probe_reasons_a
    assert len(probe_reasons_a) == len(FOLLOW_UP_STAGES) - 1

    fresh_root = tmp_path / "fresh"
    fresh_root.mkdir()
    engine_b, repo_b, _history_b, _policy_b = _make_interview_engine(
        fresh_root, adapter, graph, freshness, judge,
        learner_id="learner:iv:fresh", question_id=QUESTION_ML,
    )
    observations_b, _phase = _run_flow(
        engine_b, repo_b,
        learner_id="learner:iv:fresh", objective=_objective(adapter, "ml_fundamentals"),
        session_id="iv:fresh", responses=responses,
    )
    probe_reasons_b = [
        obs["action_reason"]
        for obs in observations_b
        if obs["action_reason"] and obs["action_reason"].startswith("INTERVIEW_PROBE_")
    ]
    assert probe_reasons_b[0] == "INTERVIEW_PROBE_CONCEPT"
    assert len(probe_reasons_b) == len(FOLLOW_UP_STAGES)

    # Determinism: identical seeded learner + responses -> identical projection.
    accel_second_root = tmp_path / "accelerated_second"
    accel_second_root.mkdir()
    engine_c, repo_c, _history_c, _policy_c = _make_interview_engine(
        accel_second_root, adapter, graph, freshness, judge,
        learner_id="learner:iv:advanced", question_id=QUESTION_ML, seed_correct=3,
    )
    observations_c, _phase = _run_flow(
        engine_c, repo_c,
        learner_id="learner:iv:advanced", objective=_objective(adapter, "ml_fundamentals"),
        session_id="iv:advanced", responses=responses,
    )
    assert _strip_timestamps(observations_a) == _strip_timestamps(observations_c)


# ---------------------------------------------------------------------------
# Interview support ladder / FULL solution gate
# ---------------------------------------------------------------------------


def test_interview_support_ladder_escalates_but_never_full(
    tmp_path: Path,
    adapter: InterviewDomainAdapter,
    graph: KnowledgeGraph,
    freshness: KnowledgeFreshnessService,
    judge: InterviewRubricJudge,
) -> None:
    learner_id = "learner:iv:hint"
    engine, repository, history, policy = _make_interview_engine(
        tmp_path, adapter, graph, freshness, judge,
        learner_id=learner_id, question_id=QUESTION_ML,
    )
    objective = _objective(adapter, "ml_fundamentals")
    vague = RESPONSES["a-vague-002"]
    responses = {0: vague, 1: vague, 2: vague, **{step: RESPONSES["a-correct-001"] for step in range(3, 12)}}
    observations, _phase = _run_flow(
        engine, repository,
        learner_id=learner_id, objective=objective,
        session_id="iv:hint", responses=responses,
    )
    hint_reasons = [
        obs["action_reason"]
        for obs in observations
        if obs["action_reason"] and obs["action_reason"].startswith("INTERVIEW_HINT_LEVEL_")
    ]
    assert hint_reasons[0] == "INTERVIEW_HINT_LEVEL_1"
    assert hint_reasons[1] == "INTERVIEW_HINT_LEVEL_2"
    assert hint_reasons[2] == "INTERVIEW_HINT_LEVEL_3"
    assert all(reason != "INTERVIEW_HINT_LEVEL_4" for reason in hint_reasons)
    assert all(int(reason.rsplit("_", 1)[1]) <= MAX_INTERVIEW_HINT_LEVEL for reason in hint_reasons)
    # The support ladder is separate from the CF ladder and its content never
    # contains a worked solution.
    hint_actions = [
        event for event in repository.list_events(learner_id)
        if event.event_type == "ACTION_TAKEN"
        and event.payload.get("vertical", {}).get("hint_level") is not None
    ]
    assert hint_actions
    for event in hint_actions:
        vertical = event.payload["vertical"]
        assert vertical["cf_hint_ladder_shared"] is False
        assert vertical["hint_level"] <= 3
        assert "FULL" not in (event.payload["action"]["content"] or "")
    snapshot = repository.get_snapshot(learner_id)
    assert snapshot is not None
    assert policy.full_solution_allowed(snapshot) is False
    with pytest.raises(ValidationError) as excinfo:
        policy.request_full_solution(snapshot)
    assert excinfo.value.code == "MAP-E11_FULL_SOLUTION_FORBIDDEN"
    assert INTERVIEW_HINT_LADDER == ("LIGHT", "INVARIANT", "STRUCTURE", "FULL")
    with pytest.raises(ValidationError):
        InterviewVerticalPolicy(
            adapter, judge, freshness, question_id=QUESTION_ML, human_approved_full=True
        )
    assert history.verify_rebuild(learner_id) is True


# ---------------------------------------------------------------------------
# Rubric audit payload / hidden-material isolation
# ---------------------------------------------------------------------------


def test_rubric_audit_in_assessment_events_without_hidden_leak(
    tmp_path: Path,
    adapter: InterviewDomainAdapter,
    graph: KnowledgeGraph,
    freshness: KnowledgeFreshnessService,
    judge: InterviewRubricJudge,
) -> None:
    learner_id = "learner:iv:audit"
    engine, repository, _history, _policy = _make_interview_engine(
        tmp_path, adapter, graph, freshness, judge,
        learner_id=learner_id, question_id=QUESTION_ML,
    )
    objective = _objective(adapter, "ml_fundamentals")
    _run_flow(
        engine, repository, learner_id=learner_id, objective=objective,
        session_id="iv:audit", responses={0: RESPONSES["a-correct-001"]}, max_steps=1,
    )
    events = [event.to_dict() for event in repository.list_events(learner_id)]
    assessed = [event for event in events if event["event_type"] == "ASSESSED"]
    assert assessed
    audit = assessed[0]["payload"]["rubric_audit"]
    assert set(audit["dimensions"]) == {
        "factual_correctness",
        "explanation_clarity",
        "engineering_feasibility",
        "evidence_sufficiency",
    }
    assert all(0.0 <= value <= 1.0 for value in audit["dimensions"].values())
    assert len(audit["spec_digest"]) == 64
    assert audit["scorer_id"] == judge.scorer_id
    mastery_event = next(event for event in events if event["event_type"] == "MASTERY_UPDATED")
    assert mastery_event["payload"]["rubric_audit"]["spec_digest"] == audit["spec_digest"]

    spec = json.loads((SCORING_DIR / "q-ml-001.json").read_text(encoding="utf-8"))
    blob = _teacher_visible_event_blob(repository, learner_id).lower()
    scrubbed = re.sub(r"[0-9a-f]{16,}", "", blob)
    for dimension, groups in spec["expectations"].items():
        for group in groups:
            assert json.dumps(group, ensure_ascii=False).lower() not in scrubbed, (
                f"hidden {dimension} expectation group leaked"
            )
    for hidden_key in ("clarity_connectors", "vague_words", "infeasible_markers",
                       "unsourced_claim_patterns", "misconception_penalty"):
        assert hidden_key not in blob, f"hidden spec field leaked: {hidden_key!r}"
    for answer in REFERENCE_ANSWERS:
        if answer["question_id"] == "q-ml-001":
            assert answer["response"]["text"] not in _teacher_visible_event_blob(
                repository, learner_id
            )
    assert "rubrics/" not in blob
    assert "reference_answers" not in blob


# ---------------------------------------------------------------------------
# NEEDS_REVIEW / EVAL_ERROR neutrality
# ---------------------------------------------------------------------------


def test_needs_review_keeps_mastery_unchanged(
    tmp_path: Path,
    adapter: InterviewDomainAdapter,
    graph: KnowledgeGraph,
    freshness: KnowledgeFreshnessService,
    judge: InterviewRubricJudge,
) -> None:
    learner_id = "learner:iv:needsreview"
    engine, repository, _history, _policy = _make_interview_engine(
        tmp_path, adapter, graph, freshness, judge,
        learner_id=learner_id, question_id=QUESTION_ENG,
    )
    objective = _objective(adapter, "engineering_metrics")
    engine.start_session(learner_id, _goal(learner_id, objective), objective, session_id="iv:nr")
    engine.current_action("iv:nr")
    before = repository.get_snapshot(learner_id)
    result = engine.submit_response("iv:nr", QUESTION_ENG, RESPONSES["a-missingfacts-004"])
    after = repository.get_snapshot(learner_id)
    assert result.status == "NEEDS_REVIEW"
    assert (before is None and after is None) or before.to_dict() == after.to_dict()
    mastery_event = next(
        event for event in repository.list_events(learner_id) if event.event_type == "MASTERY_UPDATED"
    )
    assert mastery_event.payload["applied"] is False


def test_eval_error_does_not_update_mastery(
    tmp_path: Path,
    adapter: InterviewDomainAdapter,
    graph: KnowledgeGraph,
    freshness: KnowledgeFreshnessService,
    judge: InterviewRubricJudge,
) -> None:
    learner_id = "learner:iv:evalerror"
    engine, repository, _history, _policy = _make_interview_engine(
        tmp_path, adapter, graph, freshness, judge,
        learner_id=learner_id, question_id=QUESTION_ML, corrupt_spec=True,
    )
    objective = _objective(adapter, "ml_fundamentals")
    engine.start_session(learner_id, _goal(learner_id, objective), objective, session_id="iv:ee")
    engine.current_action("iv:ee")
    before = repository.get_snapshot(learner_id)
    result = engine.submit_response("iv:ee", QUESTION_ML, "x" * 80)
    after = repository.get_snapshot(learner_id)
    assert result.status == "EVAL_ERROR"
    assert (before is None and after is None) or before.to_dict() == after.to_dict()
    error_events = [event for event in repository.list_events(learner_id) if event.event_type == "ERROR"]
    assert error_events and error_events[0].payload["mastery_unchanged"] is True


# ---------------------------------------------------------------------------
# JD / freshness gates before writes
# ---------------------------------------------------------------------------


def test_jd_gate_blocks_expired_and_conflicting_versions_before_writes(
    tmp_path: Path,
    adapter: InterviewDomainAdapter,
    graph: KnowledgeGraph,
    freshness: KnowledgeFreshnessService,
    judge: InterviewRubricJudge,
) -> None:
    objective = _objective(adapter, "ml_fundamentals")
    for now, reason in (
        ("2027-05-01T00:00:00Z", "RECHECK_JD_EXPIRED"),
        ("2026-05-01T00:00:00Z", "RECHECK_JD_NOT_YET_ACTIVE"),
    ):
        engine, repository, _history, _policy = _make_interview_engine(
            tmp_path / now.replace(":", ""),
            adapter, graph, freshness, judge,
            learner_id="learner:iv:jd", question_id=QUESTION_ML, now=now,
        )
        with pytest.raises(ValidationError) as excinfo:
            engine.start_session(
                "learner:iv:jd", _goal("learner:iv:jd", objective), objective, session_id="iv:jd"
            )
        assert excinfo.value.code == "FRESHNESS_JD_GATE_BLOCKED"
        assert excinfo.value.details["reason_code"] == reason
        assert excinfo.value.details["map_code"] == "MAP-E10_JD_EXPIRED_OR_CONFLICT"
        assert repository.list_events("learner:iv:jd") == []
        assert repository.load_session("iv:jd") is None

    # Conflict scenario: overlapping JD windows.
    engine_conflict, repository_conflict, _h, _p = _make_interview_engine(
        tmp_path / "conflict", adapter, graph, freshness, judge,
        learner_id="learner:iv:jd", question_id=QUESTION_ML,
    )
    policy_conflict = InterviewVerticalPolicy(
        adapter, judge, freshness, question_id=QUESTION_ML,
        jd_id="jd:demo-overlap", now="2026-10-01T00:00:00Z",
    )
    engine_conflict._vertical = policy_conflict  # noqa: SLF001 - test seam for conflict scenario
    with pytest.raises(ValidationError) as excinfo:
        engine_conflict.start_session(
            "learner:iv:jd", _goal("learner:iv:jd", objective), objective, session_id="iv:jd"
        )
    assert excinfo.value.code == "FRESHNESS_JD_GATE_BLOCKED"
    assert excinfo.value.details["reason_code"] == "RECHECK_JD_CONFLICT"
    assert repository_conflict.list_events("learner:iv:jd") == []


def test_jd_version_metadata_and_new_plans_only(
    tmp_path: Path,
    adapter: InterviewDomainAdapter,
    graph: KnowledgeGraph,
    freshness: KnowledgeFreshnessService,
    judge: InterviewRubricJudge,
) -> None:
    objective = _objective(adapter, "ml_fundamentals")
    versions = []
    for index, now in enumerate(("2026-07-01T00:00:00Z", "2026-10-15T00:00:00Z")):
        root = tmp_path / f"jd{index}"
        root.mkdir()
        engine, repository, _history, _policy = _make_interview_engine(
            root, adapter, graph, freshness, judge,
            learner_id=f"learner:iv:jd{index}", question_id=QUESTION_ML, now=now,
        )
        engine.start_session(
            f"learner:iv:jd{index}",
            _goal(f"learner:iv:jd{index}", objective),
            objective,
            session_id=f"iv:jd{index}",
        )
        events = [event.to_dict() for event in repository.list_events(f"learner:iv:jd{index}")]
        started = next(event for event in events if event["event_type"] == "SESSION_STARTED")
        plan = next(event for event in events if event["event_type"] == "PLAN_CREATED")
        versions.append(started["payload"]["vertical"]["jd_version"])
        assert plan["payload"]["vertical"]["jd_ref"] == f"jd:rec@{started['payload']['vertical']['jd_version']}"
    assert versions == ["v1", "v2"]


def test_knowledge_gate_blocks_recheck_and_accepts_eligible_updates_before_writes(
    tmp_path: Path,
    adapter: InterviewDomainAdapter,
    graph: KnowledgeGraph,
    freshness: KnowledgeFreshnessService,
    judge: InterviewRubricJudge,
) -> None:
    objective = _objective(adapter, "ml_fundamentals")
    decisions = freshness.classify_all_scenarios()
    keep = next(decision for decision in decisions if decision.change_kind == "KEEP")
    update = next(decision for decision in decisions if decision.curriculum_eligible)
    blocked = [decision for decision in decisions if decision.recheck_required]
    assert blocked

    # Blocked decisions are rejected before any write.
    for index, decision in enumerate(blocked):
        root = tmp_path / f"blocked{index}"
        root.mkdir()
        engine, repository, _history, _policy = _make_interview_engine(
            root, adapter, graph, freshness, judge,
            learner_id=f"learner:kn:{index}", question_id=QUESTION_ML,
            knowledge_decisions=[decision],
        )
        with pytest.raises(ValidationError) as excinfo:
            engine.start_session(
                f"learner:kn:{index}",
                _goal(f"learner:kn:{index}", objective),
                objective,
                session_id=f"iv:kn:{index}",
            )
        assert excinfo.value.code == "FRESHNESS_KNOWLEDGE_GATE_BLOCKED"
        assert excinfo.value.details["map_code"] == decision.map_code
        assert excinfo.value.details["recheck_required"] is True
        assert repository.list_events(f"learner:kn:{index}") == []
        assert repository.load_session(f"iv:kn:{index}") is None

    # KEEP/eligible UPDATE decisions are benign and recorded as provenance refs.
    root = tmp_path / "allowed"
    root.mkdir()
    engine, repository, _history, _policy = _make_interview_engine(
        root, adapter, graph, freshness, judge,
        learner_id="learner:kn:allowed", question_id=QUESTION_ML,
        knowledge_decisions=[keep, update],
    )
    engine.start_session(
        "learner:kn:allowed",
        _goal("learner:kn:allowed", objective),
        objective,
        session_id="iv:kn:allowed",
    )
    events = [event.to_dict() for event in repository.list_events("learner:kn:allowed")]
    plan = next(event for event in events if event["event_type"] == "PLAN_CREATED")
    assert update.new_version_id in plan["payload"]["vertical"]["knowledge_refs"]


# ---------------------------------------------------------------------------
# Static isolation
# ---------------------------------------------------------------------------


def test_vertical_module_is_offline_and_has_no_learner_writer(tmp_path: Path) -> None:
    source = inspect.getsource(vertical_module)
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    forbidden = {"httpx", "requests", "urllib", "socket", "aiohttp", "autoteacher_m0"}
    assert imported.isdisjoint(forbidden)
    for forbidden_member in ("upsert_snapshot", "apply_assessment", "save_session", "append_event"):
        assert forbidden_member not in source
    assert "rubrics/" not in source
