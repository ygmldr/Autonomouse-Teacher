"""G3-C C2-04: deterministic recovery/admission ordering.

The frozen order is: recover every old durable Attempt first, then consume the
(possibly replayed) Admission. A new Admission may finish old recovery, but it
can never authorize a second send for the same call/business request.
"""
from __future__ import annotations
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from test_c1_03_admission import (
    FAKE, collect, error_code, make_harness, payload, write_admission,
)
from test_c2_02_recovery import _broker_message_ids, _crash, _prepare_root


def _config(root: Path) -> Path:
    document = {
        "admission_path": str(root / "admission.json"),
        "broker_config_path": str(root / "broker.json"),
        "fake_script": str(FAKE),
        "receipt_dir": str(root / "receipts"),
        "attempt_db": str(root / "attempts.sqlite3"),
        "socket_path": str(root / "bridge.sock"),
        "python": sys.executable,
        "expected_uid": 65534,
    }
    path = root / "controller.json"
    path.write_text(json.dumps(document))
    return path


def _run_main(root: Path, timeout: float = 30.0):
    env = {**os.environ, "PYTHONPATH": os.environ.get("PYTHONPATH",
                                                     "src:artifacts/foundation/deps")}
    return subprocess.run(
        [sys.executable, "-B", "-m", "autoteacher_m0.bridge.controller",
         "--config", str(_config(root))],
        cwd=str(Path(__file__).resolve().parents[3]), env=env,
        capture_output=True, text=True, timeout=timeout)


def _state(root: Path) -> list[str]:
    conn = sqlite3.connect(root / "attempts.sqlite3")
    try:
        return [row[0] for row in conn.execute("SELECT state FROM g3b_attempts")]
    finally:
        conn.close()


def test_c2_04a_recovery_runs_before_admission_replay_is_refused(
        tmp_path: Path) -> None:
    _prepare_root(tmp_path)
    _crash(tmp_path, "after_response_before_settlement")
    proc = _run_main(tmp_path)
    assert proc.returncode == 3, (proc.returncode, proc.stdout, proc.stderr)
    assert "ADMISSION_REPLAYED_AFTER_RECOVERY" in proc.stderr
    # The old Attempt was recovered/settled before the replay was refused.
    assert _state(tmp_path) == ["SETTLED"]
    assert (tmp_path / "receipts" / "received-count.json").exists()
    count = json.loads((tmp_path / "receipts" / "received-count.json").read_text())["count"]
    assert count == 1
    assert not (tmp_path / "bridge.sock").exists()
    assert any("-settle-" in mid for mid in _broker_message_ids(tmp_path))


def test_c2_04b_new_admission_recovers_old_attempt_but_cannot_resend_it(
        tmp_path: Path) -> None:
    _prepare_root(tmp_path)
    _crash(tmp_path, "after_response_before_settlement")
    # New launcher Admission (new id) for the same synthetic run.
    write_admission(tmp_path, admission_id="c" * 32, run_id="run-g3c-test")
    harness = make_harness(tmp_path, register=True, write_configs=False)
    try:
        harness.controller.reconcile_on_startup(str(tmp_path / "receipts"))
        rows = harness.attempts_rows()
        assert [row["state"] for row in rows] == ["SETTLED"]
        assert harness.receipt_count() == 1
        # Same business request (same step/call id after restart) is blocked.
        replay = collect(harness.controller, payload())
        assert error_code(replay) == "ATTEMPT_ALREADY_STARTED", replay
        assert harness.receipt_count() == 1
        # A genuinely new request is still possible under the new admission.
        fresh = collect(harness.controller, payload(
            messages=[{"role": "user", "content": "fresh after recovery"}],
        ), transport_id="tr-" + "1" * 32)
        assert error_code(fresh) is None, fresh
        assert harness.receipt_count() == 2
        assert harness.snapshot()["requests"] == 2
    finally:
        harness.close()


def test_c2_04c_next_logical_step_is_not_in_the_runtime_path(tmp_path: Path) -> None:
    harness = make_harness(tmp_path)
    try:
        def boom(_run_id):
            raise AssertionError("next_logical_step must not be used at runtime")

        harness.attempts.next_logical_step = boom
        frames = collect(harness.controller, payload())
        assert error_code(frames) is None, frames
        harness.controller.reconcile_on_startup(str(tmp_path / "receipts"))
        assert harness.attempts_rows()[0]["state"] == "SETTLED"
        assert harness.receipt_count() == 1
    finally:
        harness.close()
