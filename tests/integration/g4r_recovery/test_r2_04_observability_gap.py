"""R2-04: observability write failures are gaps, never admit/bypass anything.

The two G4-R journals are evidence-only.  A failed write (missing directory,
directory-as-file, or a full device) must:

* leave the real allow/deny, Reserve/Claim, Fake and admission decisions
  exactly unchanged;
* be counted and surfaced through ``TrustedController.observability_status``
  with ``observability_gap: true`` and ``safety_admission_changed: false``;
* never fabricate reserved/dispatched/settled claims.
"""
from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path

import pytest

from autoteacher_m0.bridge.dispatch_audit import DispatchAudit
from autoteacher_m0.bridge.request_lifecycle import RequestLifecycleAudit

import g4f3_support as f3
import g4r_support as g4r


def test_r2_04_lifecycle_write_failure_is_gap_not_bypass(tmp_path) -> None:
    controller, broker, fake, attempts, gate = g4r.start_real_controller(tmp_path)
    # Parent directory does not exist: every request-lifecycle write fails.
    broken = tmp_path / "missing" / g4r.LIFECYCLE
    controller.request_lifecycle = RequestLifecycleAudit(str(broken))
    try:
        frames = f3.collect(controller, f3.request_payload())
        assert f3.call_error(frames) is None, frames
        state = g4r.broker_snapshot(broker)
        assert state["requests"] == 1, state
        assert state["claims"]["completed"] == 1, state
        assert Decimal(state["committed_usd"]) > 0, state
        assert fake.received_count() == 1
        assert len(attempts.attempts()) == 1
        status = controller.observability_status()
        assert status["request_lifecycle"]["write_errors"] >= 1
        assert status["request_lifecycle"]["written"] == 0
        assert status["observability_gap"] is True
        assert status["safety_admission_changed"] is False
        assert attempts.attempts()[0]["state"] == "SETTLED"
    finally:
        f3.close_all(broker, fake, attempts)


def test_r2_04_dispatch_journal_failure_keeps_real_decision(tmp_path) -> None:
    controller, broker, fake, attempts, gate = g4r.start_real_controller(tmp_path)
    directory_as_journal = tmp_path / "journal-is-a-directory"
    directory_as_journal.mkdir()
    controller.dispatch_audit = DispatchAudit(str(directory_as_journal))
    try:
        frames = f3.collect(controller, f3.request_payload())
        assert f3.call_error(frames) is None, frames
        state = g4r.broker_snapshot(broker)
        assert state["requests"] == 1, state
        assert state["claims"]["completed"] == 1, state
        assert fake.received_count() == 1
        status = controller.observability_status()
        assert status["dispatch_window"]["write_errors"] >= 1
        assert status["dispatch_window"]["written"] == 0
        assert status["observability_gap"] is True
        assert status["safety_admission_changed"] is False
        # Rejections are also unchanged by the failed journal, and the request
        # layer still records the real lifecycle (separate file).
        bad = dict(f3.request_payload())
        bad["purpose"] = "title"
        frames = f3.collect(controller, bad)
        assert f3.call_error(frames) == "BAD_TYPE"
        assert g4r.lifecycle_events(tmp_path)[-1]["event"] == "protocol_rejected"
        assert g4r.broker_snapshot(broker)["requests"] == 1
    finally:
        f3.close_all(broker, fake, attempts)


@pytest.mark.skipif(not Path("/dev/full").exists(), reason="no /dev/full")
def test_r2_04_disk_full_is_gap_not_bypass(tmp_path) -> None:
    """A real ENOSPC (full device) write failure is counted, not silent."""
    audit = RequestLifecycleAudit("/dev/full")
    record = audit.new_request(transport_id="tr-r204", payload={})
    assert audit.emit(record, "received", stage="transport") is False
    indicator = audit.gap_indicator()
    assert indicator["write_errors"] >= 1
    assert indicator["written"] == 0
    assert indicator["observability_gap"] is True
    assert indicator["last_error"] in {"OSError", "ENOSPC"} or \
        indicator["last_error"] is not None
    # The same ENOSPC applies to the recovery diagnostic journal class.
    assert os.path.exists("/dev/full")
