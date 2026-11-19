"""G4-H0 P2-05: a pre-send deadline is visible in the dispatch-window journal.

``docs/REVIEW_G4F_INDEPENDENT.md`` P2-05: the F5 ``timeout-pre-send`` case had
**no** dispatch-window record. The per-dispatch record is emitted by the worker
thread's ``finally``; the trusted launcher stops the process while that thread
is still inside the injected pre-Reserve delay, so the record never reaches the
journal. The request was still fail-closed (0 reservation/attempt/Fake), but the
window was unobservable.

The fix adds an observation-only record written by the client-facing stream at
the moment the deadline is observed. These tests pin that it:

* exists even while the worker is still delayed (before any final emit);
* reports ``reserved``/``dispatched`` progress honestly instead of claiming a
  pre-send state (``False`` here, ``True`` in the direct flag test);
* consumes no dispatch sequence and changes no allow/deny outcome;
* leaves the fail-closed evidence untouched (no reservation/attempt/Fake).

Synthetic Broker/Fake subprocesses only; no Key, model, provider or network.
"""
from __future__ import annotations

import json
import time

from autoteacher_m0.bridge.controller import _CancelState

import g4f3_support as f3
import g4f5_support as f5


def _journal_rows(path) -> list[dict]:
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _start(tmp_path, *, deadline_ms: int = 300):
    journal = tmp_path / "state" / "dispatch-window.jsonl"
    journal.parent.mkdir()
    gate = f5.make_gate()
    controller, broker, fake, attempts, gate = f5.start_controller(
        tmp_path, gate=gate, deadline_ms=deadline_ms, dispatch_journal=journal)
    return controller, broker, fake, attempts, journal


def test_pre_send_deadline_observation_exists_before_worker_finishes(
        tmp_path, monkeypatch) -> None:
    controller, broker, fake, attempts, journal = _start(tmp_path, deadline_ms=300)
    real_prepare = controller._prepare_checked

    def slow_prepare(payload, step):
        time.sleep(1.2)  # worker still here when the envelope deadline fires
        return real_prepare(payload, step)

    monkeypatch.setattr(controller, "_prepare_checked", slow_prepare)
    generator = controller.handle_envelope(f3.envelope(f3.request_payload()))
    try:
        frames: list = []
        for env in generator:
            frames.append(env)
            if env.kind == "error":
                break
        assert [frame.kind for frame in frames] == ["error"]
        assert frames[0].payload.get("code") == "DEADLINE_EXCEEDED"

        # The worker is still inside slow_prepare: only the observation can be here.
        rows = _journal_rows(journal)
        observations = [row for row in rows if row.get("observation_only") is True]
        assert len(observations) == 1, rows
        observation = observations[0]
        assert observation["schema"] == "m0.g4f.dispatch-window.v1"
        assert observation["observation_phase"] == "envelope_deadline_no_terminal_frame"
        assert observation["error_code"] == "DEADLINE_EXCEEDED"
        assert observation["outcome"] == "deadline_observed"
        assert observation["reserved"] is False
        assert observation["dispatched"] is False
        assert observation["settled"] is False
        assert observation["dispatch_seq"] is None  # never a dispatch identity

        generator.close()  # let the delayed worker unwind and emit its own record

        rows = _journal_rows(journal)
        assert len(rows) == 2, rows  # one observation + one normal per-dispatch record
        normal = [row for row in rows if row.get("observation_only") is not True]
        assert len(normal) == 1
        assert normal[0]["dispatch_seq"] == 1  # the worker's own record is unchanged
        assert normal[0]["reserved"] is False
        assert normal[0]["dispatched"] is False
        # Fail-closed evidence is unchanged: the timeout produced no ledger/Fake row.
        assert attempts.attempts() == []
        assert attempts.pending_intents() == []
        assert fake.received_count() == 0
        assert broker.snapshot()["snapshot"]["requests"] == 0
    finally:
        f3.close_all(broker, fake, attempts)


def test_observation_reports_worker_progress_flags(tmp_path) -> None:
    controller, broker, fake, attempts, journal = _start(tmp_path)
    try:
        state = controller._state_for_start("tr-" + "b" * 32)
        assert isinstance(state, _CancelState)
        state.reserved = True
        state.dispatched = True
        sequence_before = controller._dispatch_seq
        controller._observe_envelope_deadline(
            f3.envelope(f3.request_payload()), state, "DEADLINE_EXCEEDED")
        rows = _journal_rows(journal)
        assert len(rows) == 1
        observation = rows[0]
        assert observation["observation_only"] is True
        assert observation["reserved"] is True
        assert observation["dispatched"] is True
        assert observation["settled"] is False
        assert observation["dispatch_seq"] is None
        assert controller._dispatch_seq == sequence_before  # observation consumes no sequence
    finally:
        f3.close_all(broker, fake, attempts)
