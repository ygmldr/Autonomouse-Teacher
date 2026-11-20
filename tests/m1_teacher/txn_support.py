"""Shared helpers for the B-NEXT real-process crash/concurrency tests.

This module is deliberately **not** named ``test_*``: it holds the child-process
runner, deterministic pre-crash setup, DB summary projection and invariant
assertions shared by ``test_crash_recovery.py`` and ``test_concurrency.py``.
All data is the synthetic CF fixtures; no network/credentials/wall-clock fields
are used in assertions.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from m1_teacher import demo
from m1_teacher.contracts.types import LearnerGoal
from m1_teacher.learner.history import LearningHistory
from m1_teacher.learner.repository import SqliteRepository, session_version

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "fixtures" / "m1_teacher"
CHILD = Path(__file__).with_name("txn_child.py")
LEARNER = "m1b.crash.learner"
STUDENT = "student_a"
FIXED_TS = demo.FIXED_TIMESTAMP
SIGKILL_RETURNCODE = -9


@dataclass(frozen=True)
class PendingSetup:
    """Deterministic pre-crash state: one session waiting for one item."""

    session_id: str
    item_id: str
    turn_index: int
    phase: str
    session_version: str


def components() -> demo.Components:
    return demo.build_components(FIXTURES)


def child_env(failpoint: str | None = None) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if not key.startswith("M1B_")}
    if failpoint is not None:
        env["M1B_CRASH_FAILPOINT"] = failpoint
    return env


def child_command(
    *,
    db_path: Path,
    session_id: str,
    item_id: str = "",
    response: str = "A",
    mode: str = "submit",
    result_id: str | None = None,
    kill_in_scorer: bool = False,
    wait_file: Path | None = None,
    student: str = STUDENT,
    learner_id: str = LEARNER,
) -> list[str]:
    """Build the argv for one child process (used by ``run_child``/Popen tests)."""

    command = [
        sys.executable,
        str(CHILD),
        "--db",
        str(db_path),
        "--learner",
        learner_id,
        "--session",
        session_id,
        "--item",
        item_id,
        "--response",
        response,
        "--mode",
        mode,
        "--student",
        student,
    ]
    if result_id is not None:
        command.extend(["--result-id", result_id])
    if kill_in_scorer:
        command.append("--kill-in-scorer")
    if wait_file is not None:
        command.extend(["--wait-file", str(wait_file)])
    return command


def run_child(
    *,
    db_path: Path,
    session_id: str,
    item_id: str = "",
    response: str = "A",
    mode: str = "submit",
    result_id: str | None = None,
    failpoint: str | None = None,
    kill_in_scorer: bool = False,
    wait_file: Path | None = None,
    student: str = STUDENT,
    learner_id: str = LEARNER,
    timeout: float = 120.0,
) -> subprocess.CompletedProcess[str]:
    command = child_command(
        db_path=db_path,
        session_id=session_id,
        item_id=item_id,
        response=response,
        mode=mode,
        result_id=result_id,
        kill_in_scorer=kill_in_scorer,
        wait_file=wait_file,
        student=student,
        learner_id=learner_id,
    )
    return subprocess.run(
        command,
        cwd=str(REPO_ROOT),
        env=child_env(failpoint),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def setup_pending(
    db_path: Path,
    *,
    learner_id: str = LEARNER,
    session_suffix: str = "",
    explicit_session_id: str | None = None,
) -> PendingSetup:
    """Create one session on ``db_path`` and drive it to a pending item."""

    components_ = components()
    student = demo.load_student_fixture(components_.fixtures_root, STUDENT)
    repository = SqliteRepository(db_path)
    try:
        engine, _history = demo._make_engine(  # noqa: SLF001 - deterministic test wiring
            components_, repository, demo.MockStudentScorer(student)
        )
        goal = LearnerGoal(
            goal_id=f"goal.{learner_id}.{components_.objective.objective_id}{session_suffix}",
            learner_id=learner_id,
            objective_id=components_.objective.objective_id,
            created_at=FIXED_TS,
        )
        state = engine.start_session(
            learner_id,
            goal,
            components_.objective,
            session_id=explicit_session_id,
        )
        session_id = state.session_id
        for _ in range(40):
            state = repository.load_session(session_id)
            if state.pending_item_id is not None:
                break
            if state.phase in {"COMPLETE", "PAUSED"}:
                raise AssertionError(f"session reached {state.phase} before a pending item")
            action = engine.current_action(session_id)
            if action.item_id is None:
                engine.advance_session(session_id)
        assert state.pending_item_id is not None, "session did not reach a pending item"
        return PendingSetup(
            session_id=session_id,
            item_id=state.pending_item_id,
            turn_index=state.turn_index,
            phase=state.phase,
            session_version=session_version(state),
        )
    finally:
        repository.close()


_VOLATILE_KEYS = frozenset({"created_at", "updated_at", "session_version"})


def _strip_timestamps(value):  # noqa: ANN001, ANN202 - recursive JSON value
    """Drop wall-clock / content-digest metadata so the hash is reproducible.

    ``created_at``/``updated_at`` are wall-clock fields, and payload
    ``session_version`` values are content digests that include those wall-clock
    fields (the CAS version).  Everything else — ids, statuses, payload content,
    sequence numbers — is included, so two runs that reach the same logical
    crash state hash identically.
    """

    if isinstance(value, dict):
        return {
            key: _strip_timestamps(item)
            for key, item in value.items()
            if key not in _VOLATILE_KEYS
        }
    if isinstance(value, list):
        return [_strip_timestamps(item) for item in value]
    return value


def _content_hash(events) -> str:  # noqa: ANN001 - HistoryEvent list
    """Reproducible content hash of the persisted event log.

    Event/record ``created_at``/``updated_at`` wall-clock fields are excluded;
    everything else (ids, statuses, payloads, sequence numbers) is included, so
    two runs that reach the same logical crash state hash identically.
    """

    projected = [
        [
            event.seq,
            event.event_type,
            event.session_id,
            _strip_timestamps(dict(event.payload)),
        ]
        for event in events
    ]
    payload = json.dumps(projected, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _event_type_counts(events) -> dict[str, int]:  # noqa: ANN001
    counts: dict[str, int] = {}
    for event in events:
        counts[event.event_type] = counts.get(event.event_type, 0) + 1
    return dict(sorted(counts.items()))


def db_summary(db_path: Path, session_id: str, *, learner_id: str = LEARNER) -> dict:
    """Deterministic DB summary used in test assertions and crash-matrix docs."""

    repository = SqliteRepository(db_path)
    try:
        state = repository.load_session(session_id)
        assert state is not None, f"session {session_id!r} disappeared"
        events = repository.list_events(learner_id)
        snapshot = repository.get_snapshot(learner_id)
        prepared = [event for event in events if event.event_type == "ASSESSMENT_PREPARED"]
        terminal_ids: set[str] = set()
        for event in events:
            if event.event_type in {"ASSESSED", "ERROR"}:
                result_id = event.payload.get("result_id")
                if type(result_id) is str:
                    terminal_ids.add(result_id)
        unresolved = [
            event for event in prepared if event.payload.get("result_id") not in terminal_ids
        ]
        assessed = [event for event in events if event.event_type == "ASSESSED"]
        mutating = [
            event
            for event in assessed
            if event.payload.get("status") in {"CORRECT", "INCORRECT", "PARTIAL"}
        ]
        accepted = [
            {
                "item_id": event.payload.get("item_id"),
                "status": event.payload.get("status"),
            }
            for event in assessed
        ]
        verify_rebuild = LearningHistory(repository).verify_rebuild(learner_id)
        return {
            "session_id": session_id,
            "phase": state.phase,
            "turn_index": state.turn_index,
            "pending_item_id": state.pending_item_id,
            "session_version": session_version(state),
            "event_count": len(events),
            "event_types": _event_type_counts(events),
            "seqs": [event.seq for event in events],
            "prepared_total": len(prepared),
            "prepared_unresolved": len(unresolved),
            "prepared_result_ids": [
                event.payload.get("result_id") for event in prepared
            ],
            "terminal_results": len(terminal_ids),
            "assessed": len(assessed),
            "mutating_assessed": len(mutating),
            "_assessed_payloads": accepted,
            "snapshot_revision": None if snapshot is None else snapshot.revision,
            "masteries": (
                {}
                if snapshot is None
                else {
                    node_id: round(estimate.value, 6)
                    for node_id, estimate in sorted(snapshot.masteries.items())
                }
            ),
            "evidence_counts": (
                {}
                if snapshot is None
                else {
                    node_id: estimate.evidence_count
                    for node_id, estimate in sorted(snapshot.masteries.items())
                }
            ),
            "snapshot_learner": None if snapshot is None else snapshot.learner_id,
            "learners": repository.list_learners(),
            "sessions": [item.session_id for item in repository.list_sessions(learner_id)],
            "verify_rebuild": verify_rebuild,
            "content_hash": _content_hash(events),
        }
    finally:
        repository.close()


def record_matrix(case_id: str, failpoint: str | None, summary: dict) -> None:
    """Append one case summary to ``$M1B_MATRIX_OUT`` when explicitly set."""

    out = os.environ.get("M1B_MATRIX_OUT")
    if not out:
        return
    line = {
        "case_id": case_id,
        "failpoint": failpoint,
        "phase": summary["phase"],
        "turn_index": summary["turn_index"],
        "pending_item_id": summary["pending_item_id"],
        "prepared_total": summary["prepared_total"],
        "prepared_unresolved": summary["prepared_unresolved"],
        "terminal_results": summary["terminal_results"],
        "event_count": summary["event_count"],
        "event_types": summary["event_types"],
        "snapshot_revision": summary["snapshot_revision"],
        "masteries": summary["masteries"],
        "content_hash": summary["content_hash"],
    }
    path = Path(out)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(line, ensure_ascii=False, sort_keys=True) + "\n")


def item_node_ids() -> dict[str, tuple[str, ...]]:
    adapter = components().adapter
    return {item.item_id: tuple(item.node_ids) for item in adapter.assessment_items()}


def assert_common_invariants(summary: dict, setup: PendingSetup) -> None:
    """Invariants that must hold after *any* crash/recovery state."""

    seqs = summary["seqs"]
    assert seqs == sorted(seqs), "event seq order must be strictly ascending"
    assert len(seqs) == len(set(seqs)), "event seq values must be unique per learner"
    assert summary["event_count"] == len(seqs)
    assert summary["learners"] == [LEARNER], "no other learner row may appear"
    assert summary["sessions"] == [setup.session_id], "no other session may appear"
    assert summary["snapshot_learner"] in (None, LEARNER)
    assert summary["verify_rebuild"] is True, (
        "the persisted snapshot must equal the snapshot rebuilt from the event log"
    )
    assert summary["turn_index"] >= setup.turn_index, "turn_index must never go backwards"
    if summary["pending_item_id"] is None:
        assert summary["prepared_unresolved"] == 0, (
            "no unresolved PREPARED attempt may exist once the session has no pending item"
        )
    assert summary["mutating_assessed"] <= summary["assessed"]
    if summary["snapshot_revision"] is not None:
        assert summary["snapshot_revision"] <= summary["mutating_assessed"], (
            "snapshot revision cannot exceed the number of mutating assessments"
        )
        node_evidence: dict[str, int] = {}
        items = item_node_ids()
        for event in summary["_assessed_payloads"]:
            if event["status"] not in {"CORRECT", "INCORRECT", "PARTIAL"}:
                continue
            for node_id in items[event["item_id"]]:
                node_evidence[node_id] = node_evidence.get(node_id, 0) + 1
        assert summary["evidence_counts"] == dict(sorted(node_evidence.items())), (
            "each result_id must have updated mastery evidence exactly once"
        )


def finalize_after_recovery(db_path: Path, setup: PendingSetup) -> dict:
    """Assert the fully recovered/committed state and idempotent retry."""

    summary = db_summary(db_path, setup.session_id)
    assert_common_invariants(summary, setup)
    assert summary["terminal_results"] == 1, "exactly one terminal assessment event"
    assert summary["prepared_unresolved"] == 0
    assert summary["pending_item_id"] is None
    assert summary["turn_index"] == setup.turn_index + 1
    assert summary["snapshot_revision"] == 1
    assert summary["phase"] in {"REVIEW", "COMPLETE"}
    result_id = summary["prepared_result_ids"][0]
    before = summary["event_count"]
    retry = run_child(
        db_path=db_path,
        session_id=setup.session_id,
        item_id=setup.item_id,
        response="A",
        mode="submit",
        result_id=result_id,
    )
    assert retry.returncode == 0, retry.stdout + retry.stderr
    payload = json.loads(retry.stdout)
    assert payload["result"]["result_id"] == result_id
    after = db_summary(db_path, setup.session_id)
    assert after["event_count"] == before, "idempotent retry must append zero events"
    assert after["masteries"] == summary["masteries"], "no duplicate mastery application"
    return summary


def recover_and_assert(
    db_path: Path,
    setup: PendingSetup,
    *,
    expected_status: str = "RECOVERED",
) -> dict:
    """Run recovery in a new process, then prove it is a zero-event no-op."""

    result = run_child(db_path=db_path, session_id=setup.session_id, mode="recover")
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)["report"]
    assert report["status"] == expected_status, report
    summary = db_summary(db_path, setup.session_id)
    assert_common_invariants(summary, setup)
    assert summary["prepared_unresolved"] == 0
    before_count = summary["event_count"]
    before_hash = summary["content_hash"]
    repeat = run_child(db_path=db_path, session_id=setup.session_id, mode="recover")
    assert repeat.returncode == 0, repeat.stdout + repeat.stderr
    repeat_report = json.loads(repeat.stdout)["report"]
    assert repeat_report["status"] == "ALREADY_CONSISTENT", repeat_report
    assert repeat_report["events_appended"] == 0
    after = db_summary(db_path, setup.session_id)
    assert after["event_count"] == before_count
    assert after["content_hash"] == before_hash
    return report
