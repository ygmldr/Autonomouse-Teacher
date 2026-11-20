"""B-PR5 E2E tests: Student A vs Student B paths, policy compliance and evidence.

The two synthetic students are driven by their fixture ``response_script``
through a deterministic MOCK scorer; the prior knowledge is seeded as real
``ASSESSED`` history events through the learner model (so the snapshot stays
rebuildable), but the evidence itself is ``MOCK`` (synthetic, not real learner
behaviour).  Nothing here claims real teaching effectiveness.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from m1_teacher import demo
from m1_teacher.contracts.types import (
    HistoryEvent,
    LearnerGoal,
    LearnerSnapshot,
    LearningObjective,
    MasteryEstimate,
    PlanStep,
    Reason,
)
from m1_teacher.diagnostic.engine import DiagnosticEngine
from m1_teacher.planner.planner import (
    CurriculumPlanner,
    PlannerPolicy,
    REASON_GOAL_COMPLETE,
    REASON_REASSESS_STUCK_NODE,
    REASON_REVIEW_DUE,
    REASON_REVIEW_REPEATED_ERRORS,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "fixtures" / "m1_teacher"
TS = demo.FIXED_TIMESTAMP
LEARNER = "m1a.test.learner"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def components() -> demo.Components:
    return demo.build_components(FIXTURES)


@pytest.fixture(scope="module")
def objective(components: demo.Components) -> LearningObjective:
    return components.objective


@pytest.fixture(scope="module")
def scenario() -> dict:
    return demo.run_scenario(fixtures_root=FIXTURES)


@pytest.fixture(scope="module")
def summaries(scenario: dict) -> dict:
    return scenario["students"]


def components_item_nodes(summary: dict) -> list[dict]:
    """Resolve item->node mappings from the public domain adapter (teacher-visible)."""

    components = demo.build_components(FIXTURES)
    items = components.adapter.assessment_items()
    return [{"item_id": item.item_id, "node_ids": list(item.node_ids)} for item in items]


def make_goal(objective: LearningObjective) -> LearnerGoal:
    return LearnerGoal(
        goal_id=f"goal.{LEARNER}",
        learner_id=LEARNER,
        objective_id=objective.objective_id,
        created_at=TS,
    )


def make_snapshot(
    spec: dict[str, tuple[float, int, float]],
    *,
    error_counts: dict[str, int] | None = None,
    updated_at: str = TS,
    learner_id: str = LEARNER,
) -> LearnerSnapshot:
    return LearnerSnapshot(
        learner_id=learner_id,
        masteries={
            node_id: MasteryEstimate(
                node_id=node_id,
                value=value,
                confidence=confidence,
                evidence_count=evidence,
                created_at=TS,
                updated_at=updated_at,
            )
            for node_id, (value, evidence, confidence) in spec.items()
        },
        error_counts=dict(error_counts or {}),
        revision=1,
        created_at=TS,
        updated_at=updated_at,
    )


def make_event(
    seq: int,
    event_type: str,
    payload: dict,
    *,
    learner_id: str = LEARNER,
    session_id: str = "session.test",
) -> HistoryEvent:
    return HistoryEvent(
        event_id=f"evt.test.{seq}",
        learner_id=learner_id,
        session_id=session_id,
        seq=seq,
        event_type=event_type,
        payload=payload,
        created_at=TS,
    )


def planner(components: demo.Components, **policy_overrides) -> CurriculumPlanner:
    policy = PlannerPolicy(**policy_overrides)
    return CurriculumPlanner(components.adapter, components.graph, policy)


# ---------------------------------------------------------------------------
# 1) Student A and Student B produce different, explainable paths
# ---------------------------------------------------------------------------
def test_student_a_and_b_first_actions_differ(summaries: dict) -> None:
    first_a = summaries["a"]["first_action"]
    first_b = summaries["b"]["first_action"]
    key_a = (first_a["action_kind"], first_a["item_id"], tuple(first_a["node_ids"]))
    key_b = (first_b["action_kind"], first_b["item_id"], tuple(first_b["node_ids"]))
    assert key_a != key_b
    assert first_a["item_id"] is not None and first_b["item_id"] is not None


def test_student_a_and_b_plans_differ_and_explain_why(summaries: dict) -> None:
    steps_a = summaries["a"]["initial_plan"]["steps"]
    steps_b = summaries["b"]["initial_plan"]["steps"]

    def sequence(steps):
        return [(s["action_kind"], tuple(s["node_ids"])) for s in steps]

    assert sequence(steps_a) != sequence(steps_b)

    # Student A: boundary knowledge is weak, but prerequisites are complete, so
    # the first plan step teaches an objective target (no remediation step).
    assert steps_a[0]["action_kind"] == "EXPLAIN"
    assert set(steps_a[0]["node_ids"]) & {"cf.search.binary"}
    assert not any(step["action_kind"] in {"RETEACH", "REASSESS"} for step in steps_a)

    # Student B: sortedness is a missing HARD prerequisite, so remediation comes
    # before teaching the binary-search target nodes.
    assert steps_b[0]["action_kind"] == "RETEACH"
    assert steps_b[0]["node_ids"] == ["cf.sort.sortedness"]
    assert steps_b[0]["reason_code"] == "REMEDIATE_HARD_PREREQUISITE"
    sortedness_index = next(
        step["ordinal"] for step in steps_b if "cf.sort.sortedness" in step["node_ids"]
    )
    binary_teach_index = next(
        step["ordinal"]
        for step in steps_b
        if "cf.search.binary" in step["node_ids"] and step["action_kind"] in {"EXPLAIN", "RETEACH"}
    )
    assert sortedness_index < binary_teach_index


def test_student_a_and_b_phase_trajectories_differ(summaries: dict) -> None:
    phases_a = summaries["a"]["phase_sequence"]
    phases_b = summaries["b"]["phase_sequence"]
    assert phases_a and phases_b
    assert phases_a != phases_b
    # Both run the full teaching loop with assessment/update/review phases.
    for phases in (phases_a, phases_b):
        for phase in ("DIAGNOSE", "ASSESS", "UPDATE", "REVIEW", "PAUSED"):
            assert phase in phases


def test_diagnoses_are_structured_and_explain_the_difference(summaries: dict) -> None:
    diagnosis_a = summaries["a"]["diagnosis"]
    diagnosis_b = summaries["b"]["diagnosis"]
    assert diagnosis_a["status"] == "READY" and diagnosis_b["status"] == "READY"
    assert diagnosis_a["reason_code"] != diagnosis_b["reason_code"]
    # A shows a target evidence gap; B shows a hard-prerequisite gap.
    assert diagnosis_a["reason_code"] == "TARGET_EVIDENCE_GAP"
    assert diagnosis_b["reason_code"] == "HARD_PREREQUISITE_GAP"
    for diagnosis in (diagnosis_a, diagnosis_b):
        assert diagnosis["target_node_id"]
        assert diagnosis["selected_item_id"]
        assert diagnosis["hypothesis"]
        assert diagnosis["reason_detail"]
        assert diagnosis["policy_version"]


def test_review_recommendations_differ(summaries: dict) -> None:
    recommendation_a = summaries["a"]["next_recommendation"]
    recommendation_b = summaries["b"]["next_recommendation"]

    def key(rec):
        return [(step["action_kind"], tuple(step["node_ids"])) for step in rec["steps"][:3]]

    assert key(recommendation_a) != key(recommendation_b)
    # B's recommendation still targets the unresolved prerequisite/weak node.
    first_b = recommendation_b["steps"][0]
    assert set(first_b["node_ids"]) & {"cf.sort.sortedness", "cf.search.binary"}


def test_mastery_changes_are_evidence_driven(summaries: dict) -> None:
    summary_a = summaries["a"]
    binary_before = summary_a["seed"]["mastery_before"]["cf.search.binary"]["value"]
    binary_after = summary_a["mastery_after"]["cf.search.binary"]["value"]
    assert binary_after > binary_before, "correct synthetic answers must raise mastery"
    # Bound the claim: the increase comes from observed CORRECT assessments only.
    assert summary_a["assessment_status_counts"].get("CORRECT", 0) >= 3
    binary_item_ids = {
        item["item_id"]
        for item in components_item_nodes(summary_a)
        if "cf.search.binary" in item["node_ids"]
    }
    correct_binary = [
        assessment
        for assessment in summary_a["assessments"]
        if assessment["status"] == "CORRECT" and assessment["item_id"] in binary_item_ids
    ]
    assert correct_binary

    summary_b = summaries["b"]
    binary_b = summary_b["mastery_after"].get("cf.search.binary")
    sortedness_b = summary_b["mastery_after"].get("cf.sort.sortedness")
    assert binary_b is not None and binary_b["value"] == 0.0
    assert sortedness_b is not None and sortedness_b["value"] == 0.0
    assert summary_b["assessment_status_counts"].get("INCORRECT", 0) >= 1


def test_interrupt_resume_is_consistent_for_both_paths(summaries: dict) -> None:
    for key in ("a", "b"):
        resume = summaries[key]["interrupt_resume"]
        assert resume["snapshot_equal"] is True
        assert resume["plan_equal"] is True
        assert resume["paused_plan_equal"] is True
        assert resume["pending_equal"] is True
        assert resume["verify_rebuild_before_restart"] is True
        assert resume["verify_rebuild_after_restart"] is True
        assert summaries[key]["verify_rebuild"] is True


# ---------------------------------------------------------------------------
# 2) Reproducibility: same inputs/state -> identical plan and transcript
# ---------------------------------------------------------------------------
def test_scenario_is_reproducible_in_process() -> None:
    first = demo.run_scenario(fixtures_root=FIXTURES)
    second = demo.run_scenario(fixtures_root=FIXTURES)
    public_first = demo._public_scenario(first)
    public_second = demo._public_scenario(second)
    assert public_first["students"] == public_second["students"]
    assert first["path_differences"] == second["path_differences"]
    assert first["policy_checks"] == second["policy_checks"]
    assert demo.render_text(first) == demo.render_text(second)
    assert demo.render_text(first).count("not real teaching effect") >= 1


def test_same_state_reproduces_identical_plan(components: demo.Components) -> None:
    planner_instance = planner(components)
    snapshot = make_snapshot(
        {
            "cf.array.basics": (0.3, 2, 0.75),
            "cf.sort.sortedness": (0.3, 2, 0.75),
            "cf.search.linear": (0.3, 2, 0.75),
            "cf.search.binary": (0.3, 2, 0.75),
            "cf.search.boundary": (0.0, 1, 0.25),
        }
    )
    goal = make_goal(components.objective)
    first = planner_instance.plan(goal, components.objective, snapshot, [])
    second = planner_instance.plan(goal, components.objective, snapshot, [])
    assert first.to_dict() == second.to_dict()
    assert first.plan_id == second.plan_id


# ---------------------------------------------------------------------------
# 3) Evidence JSONL: reproducible, complete and leak-free
# ---------------------------------------------------------------------------
def test_evidence_jsonl_is_reproducible_and_complete(scenario: dict, tmp_path: Path) -> None:
    first_dir = tmp_path / "ev1"
    second_dir = tmp_path / "ev2"
    demo.write_evidence(scenario, first_dir)
    demo.write_evidence(scenario, second_dir)
    # P1-1: every artifact (including the summary) must be byte-identical.
    for name in ("e2e_student_a.jsonl", "e2e_student_b.jsonl", "e2e_summary.json"):
        first_bytes = (first_dir / name).read_bytes()
        second_bytes = (second_dir / name).read_bytes()
        assert first_bytes == second_bytes, f"{name} must be byte-identical across runs"

    for name in ("e2e_student_a.jsonl", "e2e_student_b.jsonl"):
        first_bytes = (first_dir / name).read_bytes()
        lines = [json.loads(line) for line in first_bytes.decode("utf-8").splitlines()]
        event_types = {line["event"] for line in lines}
        assert {
            "seeded_prior_evidence",
            "diagnosis",
            "plan",
            "action",
            "assessed",
            "mastery_updated",
            "paused",
            "resumed",
            "mastery_after",
        } <= event_types
        for line in lines:
            assert line["schema"] == "m1a.evidence.v0"
            assert "MOCK" in line["evidence_classes"]
            assert "DETERMINISTIC" in line["evidence_classes"]
            # No hidden scoring material / answer keys may appear in evidence.
            for forbidden in ("expected", "correct_option", "scoring/", "hidden/"):
                assert forbidden not in json.dumps(line, ensure_ascii=False)
            # No wall-clock timestamps: every timestamp-like string is the fixed one.
            for match in re.findall(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", json.dumps(line)):
                assert match == TS
        # The evidence narrates an observed mastery change for Student A.
        mastery_lines = [line for line in lines if line["event"] == "mastery_updated"]
        assert mastery_lines
        assert any(line.get("applied") is True for line in mastery_lines)

    # P1-1: the summary is content-tree deterministic and carries only a fixed
    # provenance manifest (no wall-clock timestamp, no dynamically read git SHA).
    summary_payload = json.loads((first_dir / "e2e_summary.json").read_text(encoding="utf-8"))
    assert "generated_at_utc_date" not in summary_payload
    assert "base_commit" not in summary_payload
    manifest = summary_payload["artifact_manifest"]
    assert manifest["manifest_version"] == demo.ARTIFACT_MANIFEST_VERSION
    assert manifest["generated_at"] == demo.FIXED_TIMESTAMP
    assert manifest["base_sha"] == demo.BASE_COMMIT_SHA
    assert manifest["implementation_commit"] == demo.REVIEWED_IMPLEMENTATION_COMMIT
    assert summary_payload["fixed_timestamp"] == demo.FIXED_TIMESTAMP
    assert summary_payload["evidence_files"] == [
        "e2e_student_a.jsonl",
        "e2e_student_b.jsonl",
    ]


def test_evidence_summary_is_identical_in_a_no_git_copy(scenario: dict, tmp_path: Path) -> None:
    """P1-1: same content tree -> same summary bytes even without a .git directory."""

    repo_summary = tmp_path / "repo_state"
    demo.write_evidence(scenario, repo_summary)

    clean_tree = tmp_path / "clean_tree"
    clean_tree.mkdir()
    shutil.copytree(
        REPO_ROOT / "m1_teacher",
        clean_tree / "m1_teacher",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    shutil.copytree(FIXTURES, clean_tree / "fixtures" / "m1_teacher")
    assert not (clean_tree / ".git").exists()
    clean_out = tmp_path / "clean_out"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "m1_teacher.demo",
            "--write-evidence",
            str(clean_out),
        ],
        cwd=str(clean_tree),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert completed.returncode == 0, completed.stderr
    for name in ("e2e_student_a.jsonl", "e2e_student_b.jsonl", "e2e_summary.json"):
        assert (clean_out / name).read_bytes() == (repo_summary / name).read_bytes(), name


def test_demo_has_no_wall_clock_or_dynamic_git_provenance() -> None:
    """P1-1 regression guard: provenance must be fixed constants, not dynamic reads."""

    source = Path(demo.__file__).read_text(encoding="utf-8")
    for forbidden in ("datetime.now", "datetime.utcnow", "rev-parse", '"base_commit"'):
        assert forbidden not in source, f"demo.py still contains dynamic provenance: {forbidden}"
    manifest = demo.artifact_manifest()
    assert manifest["generated_at"] == demo.FIXED_TIMESTAMP
    assert manifest["base_sha"] == demo.BASE_COMMIT_SHA
    assert manifest["implementation_commit"] == demo.REVIEWED_IMPLEMENTATION_COMMIT


# ---------------------------------------------------------------------------
# 4) Independent teacher-policy tests (rules, not just "it runs")
# ---------------------------------------------------------------------------
def test_planner_prioritises_hard_prerequisite_remediation(
    components: demo.Components,
) -> None:
    planner_instance = planner(components, prerequisite_mastery_threshold=0.25)
    snapshot = make_snapshot(
        {
            "cf.array.basics": (0.3, 2, 0.75),
            "cf.search.linear": (0.3, 2, 0.75),
            "cf.sort.sortedness": (0.0, 1, 0.25),
            "cf.search.binary": (0.0, 1, 0.25),
        }
    )
    plan = planner_instance.plan(
        make_goal(components.objective), components.objective, snapshot, []
    )
    first_three = plan.steps[:3]
    assert any(
        step.action_kind == "RETEACH" and step.node_ids == ["cf.sort.sortedness"]
        for step in first_three
    ), [step.to_dict() for step in first_three]
    target_teach = next(
        step
        for step in plan.steps
        if step.action_kind == "EXPLAIN"
        and set(step.node_ids)
        & {"cf.search.boundary", "cf.search.lower_upper", "cf.complexity.log"}
    )
    remediation_indices = [
        step.ordinal
        for step in plan.steps
        if set(step.node_ids) & {"cf.sort.sortedness", "cf.search.binary"}
        and step.action_kind in {"RETEACH", "PRACTICE", "REASSESS"}
    ]
    assert remediation_indices and min(remediation_indices) < target_teach.ordinal


def test_planner_reassesses_after_consecutive_failures(components: demo.Components) -> None:
    planner_instance = planner(components, prerequisite_mastery_threshold=0.0)
    snapshot = make_snapshot({"cf.search.boundary": (0.0, 1, 0.25)})
    history = [
        make_event(0, "ASSESSED", {"item_id": "item.bs.mcq.005", "status": "INCORRECT"}),
        make_event(1, "ASSESSED", {"item_id": "item.bs.code.003", "status": "INCORRECT"}),
    ]
    plan = planner_instance.plan(
        make_goal(components.objective), components.objective, snapshot, history
    )
    reassess = [step for step in plan.steps if step.action_kind == "REASSESS"]
    assert reassess, [step.to_dict() for step in plan.steps]
    assert reassess[0].rationale.code == REASON_REASSESS_STUCK_NODE
    assert "cf.search.boundary" in reassess[0].node_ids


def test_planner_spaced_review_only_when_due(components: demo.Components) -> None:
    planner_instance = planner(components, max_steps=20)
    mastered_prerequisites = {
        "cf.array.basics": (0.9, 3, 0.9),
        "cf.sort.sortedness": (0.9, 3, 0.9),
        "cf.search.linear": (0.9, 3, 0.9),
    }
    snapshot = make_snapshot(
        {
            "cf.search.binary": (0.8, 3, 0.9),
            "cf.search.boundary": (0.0, 1, 0.25),
            **mastered_prerequisites,
        }
    )
    goal = make_goal(components.objective)
    not_due = planner_instance.plan(goal, components.objective, snapshot, [])
    assert not any(step.action_kind == "REVIEW" for step in not_due.steps)

    history = [
        make_event(0, "ASSESSED", {"item_id": "item.bs.code.001", "status": "CORRECT"}),
        make_event(1, "ACTION_TAKEN", {"action_kind": "PRACTICE", "node_ids": []}),
        make_event(2, "ACTION_TAKEN", {"action_kind": "PRACTICE", "node_ids": []}),
        make_event(3, "ACTION_TAKEN", {"action_kind": "PRACTICE", "node_ids": []}),
    ]
    due = planner_instance.plan(goal, components.objective, snapshot, history)
    reviews = [step for step in due.steps if step.action_kind == "REVIEW"]
    assert reviews, [step.to_dict() for step in due.steps]
    assert reviews[0].node_ids == ["cf.search.binary"]
    assert reviews[0].rationale.code == REASON_REVIEW_DUE

    error_snapshot = make_snapshot(
        {
            "cf.search.boundary": (0.75, 3, 0.9),
            "cf.search.binary": (0.0, 1, 0.25),
            **mastered_prerequisites,
        },
        error_counts={"cf.search.boundary": 2},
    )
    errors_plan = planner_instance.plan(goal, components.objective, error_snapshot, [])
    error_reviews = [step for step in errors_plan.steps if step.action_kind == "REVIEW"]
    assert error_reviews
    assert error_reviews[0].rationale.code == REASON_REVIEW_REPEATED_ERRORS


def test_planner_goal_completion_requires_observed_evidence(
    components: demo.Components,
) -> None:
    planner_instance = planner(components)
    goal = make_goal(components.objective)
    complete_snapshot = make_snapshot(
        {
            "cf.search.binary": (0.8, 3, 0.9),
            "cf.search.boundary": (0.8, 3, 0.9),
        }
    )
    complete_plan = planner_instance.plan(goal, components.objective, complete_snapshot, [])
    assert [step.action_kind for step in complete_plan.steps] == ["GOAL_COMPLETE"]
    assert complete_plan.steps[0].rationale.code == REASON_GOAL_COMPLETE

    empty_plan = planner_instance.plan(goal, components.objective, make_snapshot({}), [])
    assert "GOAL_COMPLETE" not in {step.action_kind for step in empty_plan.steps}


def test_plan_steps_carry_structured_reasons(components: demo.Components) -> None:
    planner_instance = planner(components)
    snapshot = make_snapshot(
        {
            "cf.search.binary": (0.3, 2, 0.75),
            "cf.search.boundary": (0.0, 1, 0.25),
        }
    )
    plan = planner_instance.plan(
        make_goal(components.objective), components.objective, snapshot, []
    )
    assert plan.steps
    for step in plan.steps:
        assert isinstance(step, PlanStep)
        reason = step.rationale
        assert isinstance(reason, Reason)
        assert reason.code and reason.code.isupper()
        assert reason.detail
        assert reason.policy_version == planner_instance._policy.policy_version
        assert isinstance(reason.node_ids, list)


def test_diagnostic_engine_emits_structured_hard_prerequisite_gap(
    components: demo.Components,
) -> None:
    diagnostic = DiagnosticEngine(components.adapter, components.graph)
    snapshot = make_snapshot(
        {
            "cf.array.basics": (0.3, 2, 0.75),
            "cf.search.linear": (0.3, 2, 0.75),
            "cf.sort.sortedness": (0.0, 1, 0.25),
            "cf.search.binary": (0.0, 1, 0.25),
        }
    )
    result = diagnostic.select_next_item(
        make_goal(components.objective), components.objective, snapshot
    )
    assert result.status == "READY"
    assert result.selected_item_id
    assert result.reason is not None
    assert result.reason.code == "HARD_PREREQUISITE_GAP"
    assert result.reason.policy_version == "m1a.diagnostic.v0"
    assert result.evidence_refs
