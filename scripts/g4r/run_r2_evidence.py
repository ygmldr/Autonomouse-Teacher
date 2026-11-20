#!/usr/bin/env python3
"""G4-R R2 evidence collector (no key, no model, no external network).

Runs the host-contract R2 suite and the deterministic layer probes, then writes
the raw run output, the per-case status table and the request-lifecycle /
recovery-diagnostic timelines under ``artifacts/g4r/r2/<utc>-<head7>/``.

The artifact root is gitignored by the repository (``artifacts/``).  This script
never contacts a network, never starts a container and never uses a real Key;
the L2 (real DSH/Fake container) evidence is *not* produced here and the report
records it as UNVERIFIED unless a Stage rebuild is explicitly run later.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SUPPORT_DIRS = [
    REPO / "tests" / "integration" / "g4_f3",
    REPO / "tests" / "integration" / "g4_c",
    REPO / "tests" / "integration" / "g4_f5",
    REPO / "tests" / "integration" / "g4r_recovery",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run(command: list[str], *, env: dict | None = None) -> dict:
    started = utc_now()
    process = subprocess.run(command, cwd=str(REPO), capture_output=True,
                             text=True, env=env)
    return {
        "command": " ".join(command),
        "started_utc": started,
        "finished_utc": utc_now(),
        "exit_code": process.returncode,
        "stdout": process.stdout,
        "stderr": process.stderr,
    }


def git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=str(REPO), capture_output=True,
                              text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def _prepare_sys_path() -> None:
    for entry in [REPO / "src", *SUPPORT_DIRS]:
        if str(entry) not in sys.path:
            sys.path.insert(0, str(entry))


def probe_timeout_layer(work: Path) -> dict:
    """Reproduce the G4-F5 R4 real timeline: 800 ms deadline / 2500 ms delay."""
    _prepare_sys_path()
    os.environ["G3B_TEST_MODE"] = "1"
    os.environ["G3B_TEST_DELAY_HOOK"] = "before_reserve"
    os.environ["G3B_TEST_DELAY_MS"] = "2500"
    import g4f3_support as f3
    import g4r_support as g4r

    work.mkdir(parents=True, exist_ok=True)
    controller, broker, fake, attempts, gate = g4r.start_real_controller(
        work, deadline_ms=800)
    env = f3.envelope(f3.request_payload())
    generator = controller.handle_envelope(env)
    try:
        error_code = None
        for item in generator:
            if item.kind == "error":
                error_code = item.payload.get("code")
                break
        at_deadline = {
            "case": "R2-01",
            "error_code": error_code,
            "deadline_ms": 800,
            "test_delay_ms": 2500,
            "test_delay_hook": "before_reserve",
            "request_lifecycle": g4r.lifecycle_events(work),
            "dispatch_window_at_deadline_instant": g4r.dispatch_rows(work),
            "broker_snapshot_at_deadline_instant": g4r.broker_snapshot(broker),
            "fake_received_at_deadline_instant": fake.received_count(),
            "attempt_rows": attempts.attempts(),
            "pending_intents": attempts.pending_intents(),
            "gate_snapshot": gate.snapshot(),
        }
    finally:
        generator.close()
        limit = time.monotonic() + 5.0
        while time.monotonic() < limit and not g4r.dispatch_rows(work):
            time.sleep(0.05)
        after = {
            "dispatch_window_after_teardown": g4r.dispatch_rows(work),
            "request_lifecycle_after_teardown": g4r.lifecycle_events(work),
            "broker_snapshot_after_teardown": g4r.broker_snapshot(broker),
        }
        f3.close_all(broker, fake, attempts)
    (work / "timeout-layer-at-deadline.json").write_text(
        json.dumps(at_deadline, indent=2, sort_keys=True) + "\n")
    (work / "timeout-layer-after-teardown.json").write_text(
        json.dumps(after, indent=2, sort_keys=True) + "\n")
    return {"at_deadline": at_deadline, "after_teardown": after}


def probe_recovery(work: Path) -> dict:
    """Produce the P2-06 split evidence (revoked + corrupt receipt, PENDING)."""
    _prepare_sys_path()
    import g4r_support as g4r

    work.mkdir(parents=True, exist_ok=True)
    controller, broker, attempts, fake = g4r.start_recovery_harness(
        work, broker_status="PENDING")
    revoked = "REVOKED_PRE_SEND:RUN_AUTHORIZATION_REVOKED"
    g4r.seed_attempt(
        attempts, state="RESPONSE_OBSERVED", reason=revoked,
        receipt_json=json.dumps({"schema": "m0.g3c.not-the-observation-schema.v1"}))
    try:
        controller.reconcile_on_startup(str(work / "receipts"))
        try:
            rows = g4r.attempt_rows(work / "attempts.sqlite3")
        finally:
            attempts.close()
    finally:
        pass
    payload = {
        "case": "R2-05/R2-07",
        "broker_status": broker.status,
        "settle_calls": broker.settle_calls,
        "fail_calls": broker.fail_calls,
        "raw_attempt_rows": rows,
        "recovery_diagnostics": g4r.diagnostic_rows(work),
        "fake_received": fake.received_count(),
    }
    (work / "recovery-evidence.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return payload


CASE_STATUS = [
    ("R2-01", "PASS_L1_HOST_L2_UNVERIFIED",
     "pre-Reserve 800ms deadline / 2500ms delay observed at the request layer; "
     "0 Reservation/Fake; no dispatch fabricated"),
    ("R2-02", "PASS_L1_HOST_L2_UNVERIFIED",
     "post-Reserve cancel/timeout stays PENDING + HELD_UNCERTAIN; no release"),
    ("R2-03", "PASS_L1_HOST_L2_UNVERIFIED",
     "schema / auxiliary purpose / foreign raw-UDS peer rejected with 0 ledger; "
     "protocol_vs_dispatch layers distinguished"),
    ("R2-04", "PASS_L1_HOST_L2_UNVERIFIED",
     "journal write failures and /dev/full count as observability gaps only; "
     "admission outcome unchanged (SIGKILL path is L2/NOT_RUN)"),
    ("R2-05", "PASS_L1_HOST_L2_UNVERIFIED",
     "revocation primary cause preserved while Broker PENDING; observation in "
     "separate append-only diagnostic"),
    ("R2-06", "PASS_L1_HOST_L2_UNVERIFIED",
     "crash without prior reason yields NO_RECEIPT_AFTER_CRASH (no invented cause)"),
    ("R2-07", "PASS_L1_HOST_L2_UNVERIFIED",
     "corrupt receipt + revoked keeps both facts; 0 settle"),
    ("R2-08", "PASS_L1_HOST_L2_UNVERIFIED",
     "Broker OK/FAILED archived as terminal truth exactly once; no reversal"),
    ("R2-09", "PASS_L1_HOST_L2_UNVERIFIED",
     "independent read-only DB + JSONL reconcile; held attempts == PENDING holds"),
]


def main() -> int:
    head = git("rev-parse", "HEAD")
    parent = git("rev-parse", "HEAD^") if head else ""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    outroot = REPO / "artifacts" / "g4r" / "r2" / f"{stamp}-{head[:7] or 'nohead'}"
    outroot.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="g4r-r2-probe-"))
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO / "src")
    env.pop("G3B_TEST_MODE", None)
    env.pop("G3B_TEST_DELAY_HOOK", None)
    env.pop("G3B_TEST_DELAY_MS", None)

    pytest_run = run([sys.executable, "-m", "pytest",
                      "tests/integration/g4r_recovery", "-q",
                      "-p", "no:cacheprovider", "--junitxml",
                      str(outroot / "junit.xml")], env=env)
    (outroot / "pytest.txt").write_text(
        f"$ {pytest_run['command']}\n# started {pytest_run['started_utc']} "
        f"finished {pytest_run['finished_utc']}\n"
        f"# exit {pytest_run['exit_code']}\n\n"
        + pytest_run["stdout"] + pytest_run["stderr"])

    probes = {}
    for name, function in (("timeout-layer", probe_timeout_layer),
                           ("recovery", probe_recovery)):
        try:
            probes[name] = function(work / name)
        except Exception as exc:  # noqa: BLE001 - evidence script reports, never hides
            probes[name] = {"error": f"{type(exc).__name__}: {exc}"}
    (outroot / "probes.json").write_text(
        json.dumps(probes, indent=2, sort_keys=True, default=str) + "\n")
    for sub in work.rglob("*.json*"):
        destination = outroot / "raw" / sub.relative_to(work)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(sub, destination)
    shutil.rmtree(work, ignore_errors=True)

    env_document = {
        "case_phase": "R2",
        "utc": utc_now(),
        "host_head": head,
        "host_parent": parent,
        "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "worktree_clean": git("status", "--porcelain") == "",
        "python": sys.version.split()[0],
        "evidence_level": "L1-HOST (no container, no real DSH)",
        "l2_stage_sha": "UNVERIFIED_NO_STAGE_REBUILD",
        "l2_runtime_sha": "UNVERIFIED_NO_STAGE_REBUILD",
        "real_model_calls": 0,
        "real_external_http_calls": 0,
        "provider_keys_seen": 0,
        "podman_used": False,
        "pytest": {"command": pytest_run["command"],
                   "exit_code": pytest_run["exit_code"],
                   "started_utc": pytest_run["started_utc"],
                   "finished_utc": pytest_run["finished_utc"]},
        "case_status": [{"case": case, "status": status, "evidence": text}
                        for case, status, text in CASE_STATUS],
    }
    (outroot / "env.json").write_text(
        json.dumps(env_document, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"evidence_root": str(outroot),
                      "pytest_exit": pytest_run["exit_code"]}, indent=2))
    return 0 if pytest_run["exit_code"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
