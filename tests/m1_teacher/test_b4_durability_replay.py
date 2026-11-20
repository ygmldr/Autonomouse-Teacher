"""B-PR4 P1-1 persistence/durability + P1-3 replay/version tests (B4-04/B4-05).

Covers the independent-review P1 actions:

* **P1-1** — the selected interview stage plan (accelerated/fixed five stages) and
  the JD content snapshot are persisted in the unified event log; a *fresh*
  engine/policy instance on the same database restores the exact plan (restart
  after COMPLEXITY continues with EXPERIMENT_DESIGN; a completed accelerated
  session never re-opens ONLINE_TRIAGE); an expired JD in a new policy still uses
  the session snapshot (never ``jd_ref=jd:rec@None``); pause/resume and
  event-derived replay agree with the persisted plan.
* **P1-3** — ``replay_session_state``/``verify_session_replay`` rebuild and check
  phase/turn/pending/last action/plan/completion from events only, across CF,
  Interview and cross-domain sessions; MAP-E12/MAP-E13 version incompatibility is
  rejected on continue/resume with zero writes.
* **B4-05** — domain_version / session-policy / vertical-policy mismatches are
  rejected explicitly (MAP-E12/MAP-E13) and never partially applied.

All data is synthetic MOCK (teacher-visible learner script); no hidden scoring
material is read by this module. Real teaching effect stays NOT_VERIFIED.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from m1_teacher import demo
from m1_teacher.assessment.interview_judge import InterviewRubricJudge
from m1_teacher.contracts.errors import ValidationError
from m1_teacher.contracts.types import HistoryEvent, LearnerGoal
from m1_teacher.domains.interview import FOLLOW_UP_STAGES, InterviewDomainAdapter
from m1_teacher.idempotency import canonical_response  # noqa: F401 - used in assertions context
from m1_teacher.knowledge.freshness import KnowledgeFreshnessService
from m1_teacher.knowledge.graph import KnowledgeGraph
from m1_teacher.learner.history import LearningHistory
from m1_teacher.learner.repository import SqliteRepository
from m1_teacher.session.engine import SessionPolicy, TeachingSessionEngine
from m1_teacher.session.vertical import (
    InterviewJudgeScorer,
    InterviewVerticalPolicy,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_ROOT = REPO_ROOT / "fixtures" / "m1_teacher"
LEARNER_SCRIPT = json.loads(
    (
        FIXTURES_ROOT
        / "vertical"
        / "interview"
        / "learner_scripts"
        / "answers.json"
    ).read_text(encoding="utf-8")
)
LEARNER_ANSWERS = {
    answer["answer_id"]: answer["response"] for answer in LEARNER_SCRIPT["answers"]
}
QUESTION_ML = "interview.item.q-ml-001"
QUESTION_ENG = "interview.item.q-eng-001"
FIXED_TS = "2026-11-20T00:00:00Z"
NOW_V2 = "2026-10-15T00:00:00Z"  # jd:rec v2 window
NOW_V1 = "2026-07-01T00:00:00Z"  # jd:rec v1 window
NOW_EXPIRED = "2027-05-01T00:00:00Z"


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
        created_at=FIXED_TS,
    )


def _seed_correct(history: LearningHistory, item, learner_id: str, count: int = 3) -> None:
    from m1_teacher.contracts.types import AssessmentResult

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
                created_at=FIXED_TS,
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
    question_id: str = QUESTION_ML,
    now: str = NOW_V2,
    seed_correct: int = 0,
):
    history = LearningHistory(repository)
    if seed_correct:
        item = next(i for i in adapter.assessment_items() if i.item_id == question_id)
        _seed_correct(history, item, learner_id, count=seed_correct)
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
    return engine, history, policy


def _start(engine, adapter, learner_id, question_id=QUESTION_ML, session_id="iv:session"):
    objective = _objective(adapter, question_id)
    engine.start_session(
        learner_id, _goal(learner_id, objective), objective, session_id=session_id
    )
    return objective


def _answer(next_engine, repository, session_id, answer):
    state = repository.load_session(session_id)
    assert state.pending_item_id is not None
    return next_engine.submit_response(session_id, state.pending_item_id, answer)


def _started_event(repository, learner_id, session_id):
    return next(
        event
        for event in repository.list_events(learner_id)
        if event.session_id == session_id and event.event_type == "SESSION_STARTED"
    )


# ---------------------------------------------------------------------------
# P1-1: persisted plan / JD snapshot survive restart
# ---------------------------------------------------------------------------


def test_accelerated_plan_survives_restart_after_complexity(
    tmp_path: Path,
    adapter: InterviewDomainAdapter,
    graph: KnowledgeGraph,
    freshness: KnowledgeFreshnessService,
    judge: InterviewRubricJudge,
) -> None:
    repository = SqliteRepository(tmp_path / "restart.sqlite")
    try:
        learner_id = "b4.restart.accelerated"
        engine, _history, _policy = _make_engine(
            repository, adapter, graph, freshness, judge,
            learner_id=learner_id, seed_correct=3,
        )
        _start(engine, adapter, learner_id)
        answer = LEARNER_ANSWERS["learner-ml-overfit-v1"]
        _answer(engine, repository, "iv:session", answer)  # main -> HYPOTHESIS
        _answer(engine, repository, "iv:session", answer)  # hypothesis -> COMPLEXITY
        state = repository.load_session("iv:session")
        assert state.phase == "ASSESS"
        assert state.turn_index == 2

        started = _started_event(repository, learner_id, "iv:session")
        plan = started.payload["vertical"]["plan"]
        assert plan["stages"] == ["hypothesis", "complexity", "experiment_design", "online_triage"]
        assert plan["accelerated"] is True
        jd_snapshot = started.payload["vertical"]["jd_snapshot"]
        assert jd_snapshot["jd_id"] == "jd:rec"
        assert jd_snapshot["version"] == "v2"
        assert len(jd_snapshot["content_digest"]) == 64

        # Fresh engine + fresh policy instance on the same database.
        engine2, _history2, _policy2 = _make_engine(
            repository, adapter, graph, freshness, judge, learner_id=learner_id
        )
        resumed = engine2.start_session(
            learner_id,
            _goal(learner_id, _objective(adapter, QUESTION_ML)),
            _objective(adapter, QUESTION_ML),
            session_id="iv:session",
        )
        assert resumed.turn_index == 2
        action = engine2.current_action("iv:session")
        assert action.reason.code == "INTERVIEW_PROBE_COMPLEXITY", (
            "restart must continue the persisted accelerated plan, not reset to HYPOTHESIS"
        )
        replay = engine2.replay_session_state("iv:session")
        assert replay["plan"]["vertical_plan"]["stages"] == plan["stages"]
        assert replay["plan"]["vertical_plan"]["next_stage"] == "complexity"
        verification = engine2.verify_session_replay("iv:session")
        assert verification["match"] is True, verification["differences"]
    finally:
        repository.close()


def test_completed_accelerated_session_restart_does_not_reopen_online_triage(
    tmp_path: Path,
    adapter: InterviewDomainAdapter,
    graph: KnowledgeGraph,
    freshness: KnowledgeFreshnessService,
    judge: InterviewRubricJudge,
) -> None:
    repository = SqliteRepository(tmp_path / "completed.sqlite")
    try:
        learner_id = "b4.restart.completed"
        engine, _history, _policy = _make_engine(
            repository, adapter, graph, freshness, judge,
            learner_id=learner_id, seed_correct=3,
        )
        _start(engine, adapter, learner_id)
        answer = LEARNER_ANSWERS["learner-ml-overfit-v1"]
        for _ in range(8):
            state = repository.load_session("iv:session")
            if state.pending_item_id is None:
                break
            engine.current_action("iv:session")
            _answer(engine, repository, "iv:session", answer)
        state = repository.load_session("iv:session")
        assert state.phase == "REVIEW"
        assert state.pending_item_id is None

        engine2, _history2, _policy2 = _make_engine(
            repository, adapter, graph, freshness, judge, learner_id=learner_id
        )
        replay = engine2.replay_session_state("iv:session")
        assert replay["plan"]["vertical_plan"]["ladder_completed"] is True
        assert replay["plan"]["vertical_plan"]["next_stage"] is None
        assert engine2.verify_session_replay("iv:session")["match"] is True
        resumed = engine2.start_session(
            learner_id,
            _goal(learner_id, _objective(adapter, QUESTION_ML)),
            _objective(adapter, QUESTION_ML),
            session_id="iv:session",
        )
        assert resumed.turn_index == state.turn_index
        action = engine2.current_action("iv:session")
        assert action.reason is None or action.reason.code != "INTERVIEW_PROBE_ONLINE_TRIAGE", (
            "completed accelerated session must not re-open the ONLINE_TRIAGE probe"
        )
        # No new probe action was appended after the completed turn.
        probes = [
            event.payload.get("vertical", {}).get("reason_code")
            for event in repository.list_events(learner_id)
            if event.event_type == "ACTION_TAKEN"
        ]
        assert probes.count("INTERVIEW_PROBE_ONLINE_TRIAGE") == 1
    finally:
        repository.close()


def test_interview_pause_resume_restores_persisted_stage_plan(
    tmp_path: Path,
    adapter: InterviewDomainAdapter,
    graph: KnowledgeGraph,
    freshness: KnowledgeFreshnessService,
    judge: InterviewRubricJudge,
) -> None:
    repository = SqliteRepository(tmp_path / "pause.sqlite")
    try:
        learner_id = "b4.restart.pause"
        engine, _history, _policy = _make_engine(
            repository, adapter, graph, freshness, judge,
            learner_id=learner_id, seed_correct=3,
        )
        _start(engine, adapter, learner_id)
        answer = LEARNER_ANSWERS["learner-ml-overfit-v1"]
        _answer(engine, repository, "iv:session", answer)  # main -> HYPOTHESIS
        _answer(engine, repository, "iv:session", answer)  # hypothesis -> COMPLEXITY
        paused = engine.pause_session("iv:session")
        assert paused.phase == "PAUSED"
        engine2, _history2, _policy2 = _make_engine(
            repository, adapter, graph, freshness, judge, learner_id=learner_id
        )
        assert engine2.verify_session_replay("iv:session")["match"] is True
        resumed = engine2.resume_session("iv:session")
        assert resumed.phase == "ASSESS"
        action = engine2.current_action("iv:session")
        assert action.reason.code == "INTERVIEW_PROBE_COMPLEXITY"
        assert engine2.verify_session_replay("iv:session")["match"] is True
    finally:
        repository.close()


def test_expired_jd_restart_uses_session_snapshot_and_never_writes_none_ref(
    tmp_path: Path,
    adapter: InterviewDomainAdapter,
    graph: KnowledgeGraph,
    freshness: KnowledgeFreshnessService,
    judge: InterviewRubricJudge,
) -> None:
    repository = SqliteRepository(tmp_path / "expired.sqlite")
    try:
        learner_id = "b4.restart.expiredjd"
        engine, _history, _policy = _make_engine(
            repository, adapter, graph, freshness, judge,
            learner_id=learner_id, question_id=QUESTION_ENG, now=NOW_V1,
        )
        _start(engine, adapter, learner_id, QUESTION_ENG)
        _answer(engine, repository, "iv:session", LEARNER_ANSWERS["learner-eng-missing-facts-v1"])
        # New policy constructed *after* the JD window has expired.
        engine_expired, _history2, policy_expired = _make_engine(
            repository, adapter, graph, freshness, judge,
            learner_id=learner_id, question_id=QUESTION_ENG, now=NOW_EXPIRED,
        )
        engine_expired.start_session(
            learner_id,
            _goal(learner_id, _objective(adapter, QUESTION_ENG)),
            _objective(adapter, QUESTION_ENG),
            session_id="iv:session",
        )
        action = engine_expired.current_action("iv:session")
        assert action.reason.code == "PROJECT_FACTS_REQUIRED"
        assert action.reason.detail  # non-empty; no bogus jd ref in reason
        # All persisted vertical jd_refs use the session snapshot, never @None.
        for event in repository.list_events(learner_id):
            vertical = event.payload.get("vertical")
            if isinstance(vertical, dict) and "jd_ref" in vertical:
                assert vertical["jd_ref"] == "jd:rec@v1", vertical["jd_ref"]
        assert policy_expired.active_jd_version == "v1"
        assert engine_expired.verify_session_replay("iv:session")["match"] is True
    finally:
        repository.close()


def _fake_started_event(vertical: dict | None) -> HistoryEvent:
    payload = {
        "learner_id": "b4.fake.learner",
        "goal_id": "goal:b4.fake.learner",
        "objective_id": "obj.interview.ml_fundamentals.mastery",
        "domain_id": "interview_coach",
        "domain_version": "m1b.interview.v0",
        "phase": "ASSESS",
        "snapshot_revision": 0,
        "session_policy_version": "m1a.session.v0",
    }
    if vertical is not None:
        payload["vertical"] = vertical
    return HistoryEvent(
        event_id="evt.fake.started",
        learner_id="b4.fake.learner",
        session_id="iv:fake",
        seq=0,
        event_type="SESSION_STARTED",
        payload=payload,
        created_at=FIXED_TS,
    )


def test_missing_or_corrupt_plan_snapshot_fails_closed(
    tmp_path: Path,
    adapter: InterviewDomainAdapter,
    freshness: KnowledgeFreshnessService,
    judge: InterviewRubricJudge,
) -> None:
    snapshot = LearningHistory(
        SqliteRepository(tmp_path / "fake.sqlite")
    ).model.initial_snapshot("b4.fake.learner")
    objective = _objective(adapter, QUESTION_ML)
    policy = InterviewVerticalPolicy(adapter, judge, freshness, question_id=QUESTION_ML)

    with pytest.raises(ValidationError) as excinfo:
        policy.restore_session(
            session_id="iv:fake",
            events=(_fake_started_event(None),),
            objective=objective,
            snapshot=snapshot,
        )
    assert excinfo.value.code == "VERTICAL_PLAN_SNAPSHOT_MISSING"

    valid_plan = {
        "policy_version": policy.policy_version,
        "question_id": QUESTION_ML,
        "objective_id": objective.objective_id,
        "target_node_id": item_node(adapter, QUESTION_ML),
        "stages": list(FOLLOW_UP_STAGES),
        "accelerated": False,
        "calibration_status": "UNCALIBRATED_HEURISTIC",
        "thresholds": {},
    }
    with pytest.raises(ValidationError) as excinfo:
        policy.restore_session(
            session_id="iv:fake",
            events=(
                _fake_started_event(
                    {
                        "domain_id": "interview_coach",
                        "policy_version": policy.policy_version,
                        "plan": valid_plan,
                        "jd_snapshot": {
                            "jd_id": "jd:rec",
                            "version": None,
                            "content_digest": "0" * 16,
                        },
                    }
                ),
            ),
            objective=objective,
            snapshot=snapshot,
        )
    assert excinfo.value.code == "VERTICAL_JD_SNAPSHOT_UNAVAILABLE"

    corrupt_plan = dict(valid_plan)
    corrupt_plan["stages"] = ["concept", "bogus_stage"]
    with pytest.raises(ValidationError) as excinfo:
        policy.restore_session(
            session_id="iv:fake",
            events=(
                _fake_started_event(
                    {
                        "domain_id": "interview_coach",
                        "policy_version": policy.policy_version,
                        "plan": corrupt_plan,
                        "jd_snapshot": {
                            "jd_id": "jd:rec",
                            "version": "v2",
                            "content_digest": "e" * 64,
                        },
                    }
                ),
            ),
            objective=objective,
            snapshot=snapshot,
        )
    assert excinfo.value.code == "VERTICAL_PLAN_SNAPSHOT_CORRUPT"


def item_node(adapter: InterviewDomainAdapter, question_id: str) -> str:
    return next(
        item.node_ids[0]
        for item in adapter.assessment_items()
        if item.item_id == question_id
    )


# ---------------------------------------------------------------------------
# P1-3: session replay (CF + Interview + cross-domain) and version rejection
# ---------------------------------------------------------------------------


def test_replay_session_state_rebuilds_cf_and_interview_sessions(
    tmp_path: Path, adapter, graph, freshness, judge
) -> None:
    # CF: run the existing deterministic student path (real engine/SQLite/pause).
    db_path = tmp_path / "cf_replay.sqlite"
    summary = demo.run_student_path(
        "student_a", db_path=db_path, fixtures_root=FIXTURES_ROOT
    )
    repository = SqliteRepository(db_path)
    student = demo.load_student_fixture(FIXTURES_ROOT, "student_a")
    components = demo.build_components(FIXTURES_ROOT)
    try:
        cf_engine = TeachingSessionEngine(
            components.adapter,
            components.graph,
            repository,
            history=LearningHistory(repository),
            scorer=demo.MockStudentScorer(student),
        )
        sessions = repository.list_sessions(summary["learner_id"])
        assert sessions
        for session in sessions:
            verification = cf_engine.verify_session_replay(session.session_id)
            assert verification["match"] is True, verification["differences"]
            assert verification["replay"]["phase"] == session.phase
            event_types = {
                event.event_type
                for event in repository.list_events(summary["learner_id"])
                if event.session_id == session.session_id
            }
            if "TURN_ADVANCED" in event_types:
                assert verification["events_consumed"] > 0
        # A content-action acknowledgement marker must exist for exact replay.
        assert any(
            event.event_type == "TURN_ADVANCED"
            for event in repository.list_events(summary["learner_id"])
        )
    finally:
        repository.close()


def test_replay_cross_domain_sessions_have_consistent_state(
    tmp_path: Path, adapter, graph, freshness, judge
) -> None:
    repository = SqliteRepository(tmp_path / "cross_replay.sqlite")
    components = demo.build_components(FIXTURES_ROOT)
    student = demo.load_student_fixture(FIXTURES_ROOT, "student_a")
    try:
        learner_id = "b4.cross.replay"
        demo.seed_prior_evidence(repository, components, student, learner_id=learner_id)
        cf_engine = TeachingSessionEngine(
            components.adapter,
            components.graph,
            repository,
            history=LearningHistory(repository),
            scorer=demo.MockStudentScorer(student),
        )
        objective_cf = components.objective
        cf_state = cf_engine.start_session(
            learner_id,
            LearnerGoal(
                goal_id=f"goal:{learner_id}:cf",
                learner_id=learner_id,
                objective_id=objective_cf.objective_id,
                created_at=FIXED_TS,
            ),
            objective_cf,
        )
        cf_engine.current_action(cf_state.session_id)
        cf_engine.pause_session(cf_state.session_id)

        engine_iv, _history_iv, _policy_iv = _make_engine(
            repository, adapter, graph, freshness, judge, learner_id=learner_id
        )
        objective_iv = _objective(adapter, QUESTION_ML)
        iv_state = engine_iv.start_session(
            learner_id,
            LearnerGoal(
                goal_id=f"goal:{learner_id}:iv",
                learner_id=learner_id,
                objective_id=objective_iv.objective_id,
                created_at=FIXED_TS,
            ),
            objective_iv,
            session_id="iv:cross",
        )
        engine_iv.current_action("iv:cross")
        engine_iv.submit_response(
            "iv:cross", QUESTION_ML, LEARNER_ANSWERS["learner-ml-overfit-v1"]
        )
        for session_id, replay_engine in (
            (cf_state.session_id, cf_engine),
            (iv_state.session_id, engine_iv),
        ):
            verification = replay_engine.verify_session_replay(session_id)
            assert verification["match"] is True, verification["differences"]
        cf_engine.resume_session(cf_state.session_id)
        assert cf_engine.verify_session_replay(cf_state.session_id)["match"] is True
    finally:
        repository.close()


def test_verify_session_replay_detects_tampered_persisted_state(
    tmp_path: Path, adapter, graph, freshness, judge
) -> None:
    repository = SqliteRepository(tmp_path / "tamper.sqlite")
    try:
        learner_id = "b4.tamper.learner"
        engine, _history, _policy = _make_engine(
            repository, adapter, graph, freshness, judge, learner_id=learner_id
        )
        _start(engine, adapter, learner_id)
        state = repository.load_session("iv:session")
        tampered = type(state)(
            session_id=state.session_id,
            learner_id=state.learner_id,
            goal_id=state.goal_id,
            objective_id=state.objective_id,
            phase="REVIEW",
            turn_index=state.turn_index + 9,
            pending_item_id=None,
            created_at=state.created_at,
            updated_at=state.updated_at,
        )
        repository.save_session(tampered)
        verification = engine.verify_session_replay("iv:session")
        assert verification["match"] is False
        assert set(verification["differences"]) == {"phase", "turn_index", "pending_item_id"}
        repository.save_session(state)
        assert engine.verify_session_replay("iv:session")["match"] is True
    finally:
        repository.close()


def test_version_incompatibility_rejected_with_zero_writes(
    tmp_path: Path, adapter, graph, freshness, judge, monkeypatch
) -> None:
    repository = SqliteRepository(tmp_path / "versions.sqlite")
    try:
        learner_id = "b4.version.learner"
        engine, _history, _policy = _make_engine(
            repository, adapter, graph, freshness, judge, learner_id=learner_id
        )
        objective = _objective(adapter, QUESTION_ML)
        engine.start_session(
            learner_id, _goal(learner_id, objective), objective, session_id="iv:version"
        )
        engine.current_action("iv:version")
        baseline_events = len(repository.list_events(learner_id))
        baseline_session = repository.load_session("iv:version").to_dict()
        baseline_goal = repository.get_goal(f"goal:{learner_id}").to_dict()

        # MAP-E13: session policy version mismatch.
        versioned_policy = SessionPolicy(policy_version="m1a.session.policy.v2")
        engine_bad_policy = TeachingSessionEngine(
            adapter,
            graph,
            repository,
            history=LearningHistory(repository),
            scorer=InterviewJudgeScorer(judge),
            policy=versioned_policy,
            vertical_policy=policy_for(adapter, judge, freshness, learner_id, repository),
        )
        with pytest.raises(ValidationError) as excinfo:
            engine_bad_policy.start_session(
                learner_id, _goal(learner_id, objective), objective, session_id="iv:version"
            )
        assert excinfo.value.code == "MAP-E13_EVENT_VERSION_INCOMPATIBLE"
        assert len(repository.list_events(learner_id)) == baseline_events
        assert repository.load_session("iv:version").to_dict() == baseline_session
        assert repository.get_goal(f"goal:{learner_id}").to_dict() == baseline_goal

        # MAP-E13: vertical policy version mismatch (class-level version bump).
        monkeypatch.setattr(InterviewVerticalPolicy, "policy_version", "b4.interview.policy.v2")
        engine_bad_vertical, _h, bad_policy = _make_engine(
            repository, adapter, graph, freshness, judge, learner_id=learner_id
        )
        with pytest.raises(ValidationError) as excinfo:
            engine_bad_vertical.start_session(
                learner_id, _goal(learner_id, objective), objective, session_id="iv:version"
            )
        assert excinfo.value.code == "MAP-E13_EVENT_VERSION_INCOMPATIBLE"
        assert bad_policy.policy_version == "b4.interview.policy.v2"
        assert len(repository.list_events(learner_id)) == baseline_events
        assert repository.load_session("iv:version").to_dict() == baseline_session
        monkeypatch.undo()

        # MAP-E12: domain_version mismatch (requires pause + new session).
        engine_domain, _h2, _p2 = _make_engine(
            repository, adapter, graph, freshness, judge, learner_id=learner_id
        )
        original_version = adapter._domain_version  # noqa: SLF001 - test seam
        try:
            adapter._domain_version = "m1b.interview.v999"  # noqa: SLF001
            engine_bad_domain = TeachingSessionEngine(
                adapter,
                graph,
                repository,
                history=LearningHistory(repository),
                scorer=InterviewJudgeScorer(judge),
                vertical_policy=policy_for(adapter, judge, freshness, learner_id, repository),
            )
            with pytest.raises(ValidationError) as excinfo:
                engine_bad_domain.start_session(
                    learner_id,
                    _goal(learner_id, objective),
                    objective,
                    session_id="iv:version",
                )
            assert excinfo.value.code == "MAP-E12_DOMAIN_VERSION_MISMATCH"
            assert len(repository.list_events(learner_id)) == baseline_events
            assert repository.load_session("iv:version").to_dict() == baseline_session
        finally:
            adapter._domain_version = original_version  # noqa: SLF001
    finally:
        repository.close()


def policy_for(adapter, judge, freshness, learner_id, repository):
    """Build a vertical policy instance for the session owner (fresh instance)."""

    return InterviewVerticalPolicy(
        adapter, judge, freshness, question_id=QUESTION_ML, now=NOW_V2
    )
