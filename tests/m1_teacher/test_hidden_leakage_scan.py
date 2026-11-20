"""Hidden-material leakage scan for the trusted judge boundary (B-PR1 / B1-06).

Runtime evidence (not an AST-only check) that hidden expected values, synthetic
sentinel values, host-side sentinel content and hidden scoring paths do **not**
reach teacher-visible surfaces:

* default policy: CODE submissions are blocked, learner code is not executed and
  the session emits only an ``ERROR`` event with ``mastery_unchanged``;
* the trusted scorer's ``AssessmentResult`` / ``JudgeVerdict`` / failure reasons
  contain only aggregate classification counts;
* ``LearningHistory`` event payloads reconstructed from such results do not
  contain sentinel values;
* synthetic attack templates from ``fixtures/m1_teacher/judge/sentinels`` do not
  produce ``PASS`` and their outputs do not leak sentinel/secret/host content;
* the shipped CLI ``--demo --json`` output (teacher-visible) is scanned as an
  end-to-end export.

All sentinel values are synthetic placeholders from the certification corpus;
tests compare them by equality and never print them.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from m1_teacher import demo

from m1_teacher.assessment.scorer import DeterministicScorer
from m1_teacher.assessment.judge.supervisor import (
    STATUS_PASS,
    TrustedJudgeSupervisor,
)
from m1_teacher.contracts.types import AssessmentItem, LearnerGoal, LearningObjective
from m1_teacher.learner.history import LearningHistory
from m1_teacher.learner.repository import SqliteRepository

from judge_os_gate import require_os_sandbox

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "fixtures" / "m1_teacher"
CASES_PATH = FIXTURES / "judge" / "certification" / "cases.json"
SENTINELS_PATH = FIXTURES / "judge" / "sentinels" / "sentinels.json"
LEARNER = "m1b.leakage.learner"
SESSION = "session.m1b.leakage.0001"
TS = demo.FIXED_TIMESTAMP


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


SENTINELS = _load_json(SENTINELS_PATH)
ATTACK_TEMPLATES = SENTINELS["attack_templates"]
CASES = _load_json(CASES_PATH)["cases"]

SENTINEL_VALUES = (
    SENTINELS["sentinel_expected"],
    SENTINELS["sentinel_secret_token"],
    SENTINELS["host_sentinel_content"],
)


def _assert_no_sentinels(payload: str, *, surface: str) -> None:
    """No hidden corpus content/sentinels on a teacher-visible surface.

    ``AssessmentItem.scoring_spec_ref`` is a *relative metadata locator* that is
    intentionally part of the frozen ``m1a.v0`` teacher-visible item payload
    (see docs/M1_B_JUDGE_IMPLEMENTATION.md, P2-13): it names a file relative to
    the hidden scoring directory but carries none of its content.  The scan
    therefore forbids hidden corpus paths/content, not the stable relative ref
    field itself; ``_assert_scoring_spec_refs_are_safe_metadata`` pins the field
    to a safe relative locator and the sentinel scan proves no spec contents
    leak through it.
    """

    for sentinel in SENTINEL_VALUES:
        assert sentinel not in payload, f"sentinel leaked into teacher-visible surface: {surface}"
    hidden_judge_dir = str((FIXTURES / "judge").resolve())
    for forbidden in (
        "judge/certification",
        "judge/sentinels",
        "fixtures/m1_teacher/judge",
        hidden_judge_dir,
    ):
        assert forbidden not in payload, f"hidden path leaked into {surface}: {forbidden}"


def _assert_scoring_spec_refs_are_safe_metadata(payload: Any) -> None:
    """P2-13: teacher-visible ``scoring_spec_ref`` must stay a safe relative ref."""

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            ref = node.get("scoring_spec_ref")
            if ref is not None:
                assert isinstance(ref, str) and ref.strip(), "scoring_spec_ref must be a string"
                pure = Path(ref)
                assert not pure.is_absolute(), "scoring_spec_ref must be relative"
                assert ".." not in pure.parts, "scoring_spec_ref must not traverse"
                assert ref == node.get("scoring_spec_ref")
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(payload)


# ---------------------------------------------------------------------------
# Synthetic spec / item helpers
# ---------------------------------------------------------------------------
def _make_synthetic_spec(root: Path, *, expected: Any, args: list[Any]) -> None:
    domain_dir = root / "domains" / "cf_binary_search"
    scoring_dir = domain_dir / "scoring"
    scoring_dir.mkdir(parents=True, exist_ok=True)
    spec = {
        "kind": "PYTHON_FUNCTION",
        "function_name": "target",
        "tests": [{"args": args, "expected": expected}],
        "timeout_s": 1.0,
    }
    (scoring_dir / "leak.json").write_text(json.dumps(spec), encoding="utf-8")


def _synthetic_item() -> AssessmentItem:
    base = next(item for item in demo.build_components(FIXTURES).adapter.assessment_items()
                if item.item_type == "CODE")
    return dataclasses.replace(
        base,
        item_id="item.m1b.leak.code.001",
        scoring_spec_ref="scoring/leak.json",
        created_at=TS,
    )


def _wrong_worker(actual: str = "0") -> SimpleNamespace:
    """Worker double whose COMPLETED actual never matches the sentinel expected."""

    class _Worker:
        def sandbox_available(self) -> bool:
            return True

        def run_case(self, code, function_name, args, timeout_s=None):
            return SimpleNamespace(
                status="COMPLETED", actual_canonical=actual, exception_type=None
            )

    return _Worker()


class _CodeOnlyAdapter:
    """Adapter wrapper that exposes only CODE items (so a session reaches CODE)."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def assessment_items(self, node_id: str | None = None):
        items = self._inner.assessment_items(node_id)
        return [item for item in items if item.item_type == "CODE"]

    def teaching_content(self, node_id: str, kind: str) -> str:
        if kind == "PRACTICE":
            ids = [item.item_id for item in self.assessment_items(node_id)]
            return json.dumps(ids)
        return self._inner.teaching_content(node_id, kind)


def _goal(objective: LearningObjective) -> LearnerGoal:
    return LearnerGoal(
        goal_id=f"goal.{LEARNER}",
        learner_id=LEARNER,
        objective_id=objective.objective_id,
        created_at=TS,
    )


# ---------------------------------------------------------------------------
# 1. Default policy: blocked CODE is not executed and mutates no mastery
# ---------------------------------------------------------------------------
def test_default_blocked_code_is_not_executed_and_never_evidence(
    tmp_path: Path,
) -> None:
    components = demo.build_components(FIXTURES)
    adapter = _CodeOnlyAdapter(components.adapter)
    patched = demo.Components(
        fixtures_root=components.fixtures_root,
        adapter=adapter,
        graph=components.graph,
        objective=components.objective,
    )
    repository = SqliteRepository(tmp_path / "blocked.sqlite")
    marker = tmp_path / "learner_code_executed.marker"
    try:
        engine, history = demo._make_engine(
            patched,
            repository,
            # explicit default-policy scorer: CODE execution stays blocked
            DeterministicScorer(FIXTURES),
        )
        state = engine.start_session(
            LEARNER, _goal(components.objective), components.objective
        )
        action = engine.current_action(state.session_id)
        assert action.item_id is not None
        item = next(
            item
            for item in adapter.assessment_items()
            if item.item_id == action.item_id
        )
        assert item.item_type == "CODE"
        response = (
            "from pathlib import Path\n"
            f"Path({str(marker)!r}).write_text('executed')\n"
            "def target(*args):\n"
            "    return 0\n"
        )
        result = engine.submit_response(state.session_id, action.item_id, response)

        assert result.status == "EVAL_ERROR"
        assert result.failure_reason == "UNTRUSTED_CODE_EXECUTION_BLOCKED"
        assert result.score is None
        assert not marker.exists(), "learner code must not be executed when blocked"

        snapshot = repository.get_snapshot(LEARNER)
        assert snapshot is None
        events = repository.list_events(LEARNER)
        assert not any(event.event_type == "ASSESSED" for event in events)
        errors = [event for event in events if event.event_type == "ERROR"]
        assert errors
        assert errors[-1].payload["mastery_unchanged"] is True
        assert history.verify_rebuild(LEARNER) is True

        rendered = json.dumps([event.to_dict() for event in events], ensure_ascii=False)
        _assert_no_sentinels(rendered, surface="engine history events")
        # P2-13: the frozen m1a.v0 item payload is teacher-visible and carries a
        # relative scoring_spec_ref; it must never be absolute/traversing and the
        # hidden spec content (sentinels) must not be embedded next to it.
        _assert_scoring_spec_refs_are_safe_metadata(
            [event.payload for event in events]
        )
        _assert_no_sentinels(
            json.dumps(result.to_dict(), ensure_ascii=False),
            surface="AssessmentResult",
        )
    finally:
        repository.close()


# ---------------------------------------------------------------------------
# 2. Synthetic hidden expected/sentinel never reaches result or history exports
# ---------------------------------------------------------------------------
def test_scorer_result_and_history_payloads_do_not_leak_hidden_material(
    tmp_path: Path,
) -> None:
    fixture_root = tmp_path / "fixtures"
    _make_synthetic_spec(
        fixture_root,
        expected=SENTINELS["sentinel_expected"],
        args=[SENTINELS["sentinel_secret_token"]],
    )
    item = _synthetic_item()
    scorer = DeterministicScorer(
        fixture_root,
        clock=lambda: TS,
        trusted_fixture_only=True,
        judge_worker=_wrong_worker(),
    )
    result = scorer.score(
        item, LEARNER, "def target(*args):\n    return 0\n", result_id="result.leak.001"
    )
    assert result.status == "INCORRECT"
    rendered_result = json.dumps(result.to_dict(), ensure_ascii=False)
    _assert_no_sentinels(rendered_result, surface="AssessmentResult")
    assert SENTINELS["sentinel_expected"] not in result.failure_reason
    assert SENTINELS["sentinel_secret_token"] not in result.failure_reason
    assert "expected" not in result.failure_reason
    assert "args" not in result.failure_reason

    repository = SqliteRepository(tmp_path / "leak.sqlite")
    history = LearningHistory(repository)
    try:
        history.apply_assessment(LEARNER, SESSION, item, result, snapshot=None)
        events = repository.list_events(LEARNER)
        assert events
        rendered_history = json.dumps(
            [event.to_dict() for event in events], ensure_ascii=False
        )
        _assert_no_sentinels(rendered_history, surface="LearningHistory event payloads")
        # The hidden spec content (expected/args sentinels) is not embedded; only
        # the item's stable relative locator metadata may appear (P2-13).
        _assert_scoring_spec_refs_are_safe_metadata(
            [event.payload for event in events]
        )
    finally:
        repository.close()


# ---------------------------------------------------------------------------
# 3. Forged worker response cannot forge a verdict or leak hidden material
# ---------------------------------------------------------------------------
def test_forged_worker_response_fails_closed_without_leakage(tmp_path: Path) -> None:
    fixture_root = tmp_path / "fixtures"
    _make_synthetic_spec(
        fixture_root,
        expected=SENTINELS["sentinel_expected"],
        args=[SENTINELS["sentinel_secret_token"]],
    )
    item = _synthetic_item()

    class _ForgedWorker:
        def sandbox_available(self) -> bool:
            return True

        def run_case(self, code, function_name, args, timeout_s=None):
            return {
                "status": "COMPLETED",
                "actual_canonical": json.dumps(SENTINELS["sentinel_expected"]),
                "passed": True,
                "verdict": "PASS",
            }

    scorer = DeterministicScorer(
        fixture_root,
        clock=lambda: TS,
        trusted_fixture_only=True,
        judge_worker=_ForgedWorker(),
    )
    result = scorer.score(item, LEARNER, "def target(*args):\n    return 0\n")
    assert result.status == "EVAL_ERROR"
    assert result.failure_reason.startswith("JUDGE_INFRA_ERROR:")
    rendered = json.dumps(result.to_dict(), ensure_ascii=False)
    _assert_no_sentinels(rendered, surface="AssessmentResult (forged response)")
    assert SENTINELS["sentinel_expected"] not in result.failure_reason


# ---------------------------------------------------------------------------
# 4. Synthetic attack templates: no PASS, no sentinel leak (real sandbox)
# ---------------------------------------------------------------------------
def _real_worker():
    try:
        from m1_teacher.assessment.judge.worker import UntrustedExecutionWorker
    except ImportError:  # pragma: no cover - merged branch always has it
        return None
    candidate = UntrustedExecutionWorker()
    return candidate if candidate.sandbox_available() else None


REAL_WORKER = _real_worker()


@pytest.fixture(scope="module")
def attack_worker():
    require_os_sandbox(REAL_WORKER is not None)
    return REAL_WORKER


@pytest.mark.parametrize(
    "template", ATTACK_TEMPLATES, ids=[item["attack_id"] for item in ATTACK_TEMPLATES]
)
def test_attack_templates_never_pass_and_never_leak(
    template: dict[str, Any], attack_worker
) -> None:
    timeout = 0.5 if template["attack_family"] in {"infinite_loop", "fork_subprocess"} else 1.5
    supervisor = TrustedJudgeSupervisor(
        attack_worker, trusted_fixture_only=True, timeout_s=timeout
    )
    verdict = supervisor.evaluate(
        template["code"],
        "target",
        [{"args": [SENTINELS["sentinel_secret_token"]], "expected": SENTINELS["sentinel_expected"]}],
        timeout_s=timeout,
    )
    assert verdict.status != STATUS_PASS, template["attack_id"]
    rendered = json.dumps(verdict.to_dict(), ensure_ascii=False)
    _assert_no_sentinels(rendered, surface=f"JudgeVerdict for {template['attack_id']}")
    if template["expected_blocked"]:
        assert verdict.infra_error or verdict.status in {
            "WA",
            "RE",
            "TLE",
            "JUDGE_INFRA_ERROR",
        }
    assert verdict.cases_passed == 0


# ---------------------------------------------------------------------------
# 5. End-to-end teacher-visible CLI export scan
# ---------------------------------------------------------------------------
def test_cli_demo_json_export_contains_no_hidden_material(tmp_path: Path) -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "m1_teacher.cli", "--demo", "--json"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=300,
        env={**os.environ, "PYTHONHASHSEED": "0"},
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip(), "CLI --json produced no output"
    _assert_no_sentinels(completed.stdout, surface="CLI --demo --json")
    # also scan the human-readable demo run
    text_run = subprocess.run(
        [sys.executable, "-m", "m1_teacher.demo"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=300,
        env={**os.environ, "PYTHONHASHSEED": "0"},
    )
    assert text_run.returncode == 0, text_run.stderr
    _assert_no_sentinels(text_run.stdout, surface="demo stdout")


# ---------------------------------------------------------------------------
# Review P2-12: fingerprint scan for *all* certification expected values
# ---------------------------------------------------------------------------
def _canonical_expected(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        allow_nan=False,
        separators=(",", ":"),
    )


def test_certification_expected_fingerprints_do_not_appear_in_teacher_exports() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "m1_teacher.cli", "--demo", "--json"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=300,
        env={**os.environ, "PYTHONHASHSEED": "0"},
    )
    assert completed.returncode == 0, completed.stderr
    payload = completed.stdout
    expected_fingerprints = {
        hashlib.sha256(_canonical_expected(test["expected"]).encode("utf-8")).hexdigest()
        for case in CASES
        for test in case["tests"]
    }
    assert expected_fingerprints, "certification corpus has no expected values"
    for fingerprint in expected_fingerprints:
        assert fingerprint not in payload, "hidden expected fingerprint leaked into CLI export"
