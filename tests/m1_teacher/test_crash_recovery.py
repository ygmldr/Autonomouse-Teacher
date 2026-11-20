"""Real-process crash matrix for the B-NEXT transactional teaching turn (B2-01/02).

Every crash in this module is produced by a **real** ``SIGKILL`` of a child OS
process (``tests/m1_teacher/txn_child.py``) at a named repository write point
(``M1B_CRASH_FAILPOINT``) or inside the external scorer (``--kill-in-scorer``).
No mock Python exception is ever used as crash evidence.  A fresh process (the
pytest process) then opens the same SQLite file and asserts the persisted state
invariants; recovery is executed by a *third* process and idempotency is proven
by a *fourth*.

Coverage (B-Q2 / B2-01 / B2-02):

* transaction A (``RESPONSE_SUBMITTED`` + ``ASSESSMENT_PREPARED``): after BEGIN,
  after the session CAS check, before/after every event insert, before/after
  the session write, before commit and **after commit**;
* crash in the external-scoring window between A and B (real SIGKILL by the
  scorer);
* transaction B (terminal events + snapshot + session): before/after every event
  insert, before/after snapshot, before/after session, before commit and after
  commit;
* recovery itself is crashed before/after its own writes, then re-run: the
  second run must be a zero-event no-op (never a duplicate mastery update).

Set ``M1B_MATRIX_OUT=/path/matrix.jsonl`` when running pytest to dump the
per-case DB summary (pending/turn/mastery/event count/content hash) used in
``docs/M1_B_TXN_RECOVERY.md``; the file is advisory evidence only.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from txn_support import (  # noqa: F401 - local test support module
    LEARNER,
    SIGKILL_RETURNCODE,
    assert_common_invariants,
    db_summary,
    finalize_after_recovery,
    record_matrix,
    recover_and_assert,
    run_child,
    setup_pending,
)

_PREPARE_POINTS = (
    "prepare:after_begin",
    "prepare:after_session_check",
    "prepare:before_event_insert_1",
    "prepare:after_event_insert_1",
    "prepare:before_event_insert_2",
    "prepare:after_event_insert_2",
    "prepare:before_session",
    "prepare:after_session",
    "prepare:before_commit",
    "prepare:after_commit",
)

_COMMIT_POINTS = (
    "commit:after_begin",
    "commit:after_session_check",
    "commit:before_event_insert_1",
    "commit:after_event_insert_1",
    "commit:before_event_insert_2",
    "commit:after_event_insert_2",
    "commit:before_snapshot",
    "commit:after_snapshot",
    "commit:before_session",
    "commit:after_session",
    "commit:before_commit",
    "commit:after_commit",
)

_RECOVERY_POINTS = (
    "commit:after_begin",
    "commit:after_session_check",
    "commit:before_event_insert_1",
    "commit:before_snapshot",
    "commit:after_snapshot",
    "commit:before_session",
    "commit:after_session",
    "commit:before_commit",
    "commit:after_commit",
)


# ---------------------------------------------------------------------------
# Crash matrix: transaction A (durable prepared attempt)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("failpoint", _PREPARE_POINTS)
def test_crash_during_transaction_a(tmp_path: Path, failpoint: str) -> None:
    db_path = tmp_path / "crash_a.db"
    setup = setup_pending(db_path)
    child = run_child(
        db_path=db_path,
        session_id=setup.session_id,
        item_id=setup.item_id,
        response="A",
        failpoint=failpoint,
    )
    assert child.returncode == SIGKILL_RETURNCODE, (
        f"failpoint {failpoint!r} did not kill the child process: "
        f"rc={child.returncode} out={child.stdout!r} err={child.stderr!r}"
    )
    summary = db_summary(db_path, setup.session_id)
    assert_common_invariants(summary, setup)
    record_matrix(f"A-{failpoint}", failpoint, summary)
    committed = failpoint.endswith("after_commit")
    if committed:
        # The A transaction committed: prepared attempt persisted, nothing scored.
        assert summary["prepared_total"] == 1
        assert summary["prepared_unresolved"] == 1
        assert summary["terminal_results"] == 0
        assert summary["pending_item_id"] == setup.item_id
        assert summary["turn_index"] == setup.turn_index
        assert summary["session_version"] != setup.session_version
        recover_and_assert(db_path, setup)
        finalize_after_recovery(db_path, setup)
    else:
        # The A transaction rolled back: no trace, still the same pending turn.
        assert summary["prepared_total"] == 0
        assert summary["prepared_unresolved"] == 0
        assert summary["terminal_results"] == 0
        assert summary["pending_item_id"] == setup.item_id
        assert summary["turn_index"] == setup.turn_index
        assert summary["session_version"] == setup.session_version
        recover_and_assert(db_path, setup, expected_status="ALREADY_CONSISTENT")
        # A fresh submit after the rollback must succeed normally.
        retry = run_child(
            db_path=db_path,
            session_id=setup.session_id,
            item_id=setup.item_id,
            response="A",
        )
        assert retry.returncode == 0, retry.stdout + retry.stderr
        finalize_after_recovery(db_path, setup)


# ---------------------------------------------------------------------------
# Crash matrix: external-scoring window between A and B (real SIGKILL by scorer)
# ---------------------------------------------------------------------------


def test_crash_in_external_scoring_window(tmp_path: Path) -> None:
    db_path = tmp_path / "crash_b.db"
    setup = setup_pending(db_path)
    child = run_child(
        db_path=db_path,
        session_id=setup.session_id,
        item_id=setup.item_id,
        response="A",
        kill_in_scorer=True,
    )
    assert child.returncode == SIGKILL_RETURNCODE, child.stdout + child.stderr
    summary = db_summary(db_path, setup.session_id)
    assert_common_invariants(summary, setup)
    record_matrix("B-scoring-window", "kill-in-scorer", summary)
    assert summary["prepared_total"] == 1
    assert summary["prepared_unresolved"] == 1
    assert summary["terminal_results"] == 0
    assert summary["pending_item_id"] == setup.item_id
    assert summary["turn_index"] == setup.turn_index
    recover_and_assert(db_path, setup)
    finalize_after_recovery(db_path, setup)


# ---------------------------------------------------------------------------
# Crash matrix: transaction B (terminal events + snapshot + session)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("failpoint", _COMMIT_POINTS)
def test_crash_during_transaction_b(tmp_path: Path, failpoint: str) -> None:
    db_path = tmp_path / "crash_c.db"
    setup = setup_pending(db_path)
    child = run_child(
        db_path=db_path,
        session_id=setup.session_id,
        item_id=setup.item_id,
        response="A",
        failpoint=failpoint,
    )
    assert child.returncode == SIGKILL_RETURNCODE, (
        f"failpoint {failpoint!r} did not kill the child process: "
        f"rc={child.returncode} out={child.stdout!r} err={child.stderr!r}"
    )
    summary = db_summary(db_path, setup.session_id)
    assert_common_invariants(summary, setup)
    record_matrix(f"C-{failpoint}", failpoint, summary)
    committed = failpoint.endswith("after_commit")
    assert summary["prepared_total"] == 1
    if committed:
        assert summary["prepared_unresolved"] == 0
        assert summary["terminal_results"] == 1
        assert summary["pending_item_id"] is None
        assert summary["turn_index"] == setup.turn_index + 1
        assert summary["snapshot_revision"] == 1
        recover_and_assert(db_path, setup, expected_status="ALREADY_CONSISTENT")
        finalize_after_recovery(db_path, setup)
    else:
        assert summary["prepared_unresolved"] == 1
        assert summary["terminal_results"] == 0
        assert summary["pending_item_id"] == setup.item_id
        assert summary["turn_index"] == setup.turn_index
        assert summary["snapshot_revision"] is None
        recover_and_assert(db_path, setup)
        finalize_after_recovery(db_path, setup)


# ---------------------------------------------------------------------------
# Crash matrix: recovery itself is crashed, then re-run (idempotent recovery)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("recovery_failpoint", _RECOVERY_POINTS)
def test_crash_during_recovery_then_idempotent_rerun(
    tmp_path: Path, recovery_failpoint: str
) -> None:
    db_path = tmp_path / "crash_recovery.db"
    setup = setup_pending(db_path)
    # Crash in the scoring window, leaving a prepared-but-uncommitted attempt.
    crashed = run_child(
        db_path=db_path,
        session_id=setup.session_id,
        item_id=setup.item_id,
        response="A",
        kill_in_scorer=True,
    )
    assert crashed.returncode == SIGKILL_RETURNCODE
    # Recovery process itself is killed at a write point.
    recovery_crash = run_child(
        db_path=db_path,
        session_id=setup.session_id,
        mode="recover",
        failpoint=recovery_failpoint,
    )
    assert recovery_crash.returncode == SIGKILL_RETURNCODE, (
        f"recovery failpoint {recovery_failpoint!r} did not kill the child: "
        f"rc={recovery_crash.returncode} out={recovery_crash.stdout!r}"
    )
    summary = db_summary(db_path, setup.session_id)
    assert_common_invariants(summary, setup)
    record_matrix(f"R-{recovery_failpoint}", recovery_failpoint, summary)
    if recovery_failpoint.endswith("after_commit"):
        # Recovery committed before the crash: the retry must be a no-op.
        assert summary["terminal_results"] == 1
        assert summary["pending_item_id"] is None
        recover_and_assert(db_path, setup, expected_status="ALREADY_CONSISTENT")
        finalize_after_recovery(db_path, setup)
    else:
        assert summary["prepared_unresolved"] == 1
        assert summary["terminal_results"] == 0
        assert summary["pending_item_id"] == setup.item_id
        recover_and_assert(db_path, setup)
        finalize_after_recovery(db_path, setup)


# ---------------------------------------------------------------------------
# Invariant: every crash point collapses to one of three explainable states
# ---------------------------------------------------------------------------


def test_crash_states_collapse_to_three_explainable_logical_states(tmp_path: Path) -> None:
    """Any kill point leaves one of exactly three persisted logical states.

    * ``rolled_back``: transaction A never committed (no prepared attempt);
    * ``prepared``: transaction A committed, transaction B did not (recoverable);
    * ``committed``: transaction B committed (terminal event + snapshot + session).

    The state hash is reproducible (wall-clock/CAS-digest fields excluded), so
    every case that lands in the same logical state hashes identically.  The
    committed state produced by crash-then-recover equals the committed state
    produced by an uninterrupted submit with the same request.
    """

    cases = (
        "prepare:after_event_insert_1",
        "prepare:before_commit",
        "prepare:after_commit",
        "commit:after_event_insert_1",
        "commit:after_snapshot",
        "commit:after_commit",
        "kill-in-scorer",
    )
    states: dict[tuple, set[str]] = {}
    committed_hashes: list[str] = []
    prepared_db: Path | None = None
    prepared_setup = None
    for index, case in enumerate(cases):
        db_path = tmp_path / f"collapse_{index}.db"
        setup = setup_pending(db_path)
        if case == "kill-in-scorer":
            child = run_child(
                db_path=db_path,
                session_id=setup.session_id,
                item_id=setup.item_id,
                response="A",
                kill_in_scorer=True,
            )
        else:
            child = run_child(
                db_path=db_path,
                session_id=setup.session_id,
                item_id=setup.item_id,
                response="A",
                failpoint=case,
            )
        assert child.returncode == SIGKILL_RETURNCODE, (case, child.stdout)
        summary = db_summary(db_path, setup.session_id)
        assert_common_invariants(summary, setup)
        key = (
            summary["prepared_total"],
            summary["terminal_results"],
            summary["snapshot_revision"],
            summary["pending_item_id"] is None,
        )
        states.setdefault(key, set()).add(summary["content_hash"])
        if key == (1, 1, 1, True):
            committed_hashes.append(summary["content_hash"])
        if case == "kill-in-scorer":
            prepared_db = db_path
            prepared_setup = setup
    # Exactly three logical states, each with one reproducible content hash.
    assert set(states) == {(0, 0, None, False), (1, 0, None, False), (1, 1, 1, True)}, states
    for key, hashes in states.items():
        assert len(hashes) == 1, f"state {key} has non-reproducible hashes {hashes}"
    assert len(committed_hashes) == 1
    # Crash + recovery converges to the exact committed state of an uninterrupted turn.
    assert prepared_db is not None and prepared_setup is not None
    recover = run_child(db_path=prepared_db, session_id=prepared_setup.session_id, mode="recover")
    assert recover.returncode == 0, recover.stdout + recover.stderr
    recovered = db_summary(prepared_db, prepared_setup.session_id)
    assert (
        recovered["prepared_total"],
        recovered["terminal_results"],
        recovered["snapshot_revision"],
        recovered["pending_item_id"] is None,
    ) == (1, 1, 1, True)
    assert recovered["content_hash"] == committed_hashes[0], (
        "recovery must converge to the same logical state as an uninterrupted commit"
    )
