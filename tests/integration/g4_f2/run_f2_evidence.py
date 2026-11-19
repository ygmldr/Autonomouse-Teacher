#!/usr/bin/env python3
"""G4-F2 L2 evidence runner: real DSH two-round runs + raw-UDS matrix.

What it does (all no-key / no-model / ``--network none`` / synthetic Fake):

1. runs ``scripts/g4/launch_c.py`` twice against one freshly built G4-C stage:
   ``echo`` (one provider request) and ``tool`` (two provider requests with the
   approved ``skill_lookup`` schema);
2. starts one hold Candidate + trusted Controller through the same G4-C
   launcher and drives the real ``SOCKET /work/g3b/bridge.sock`` from the real
   Candidate UID (65534) with the G4-F2 negative matrix (unapproved tool,
   nested schema change, extra/duplicate tool, message tool-call/addition,
   auxiliary purpose and its replay) and one approved request;
3. snapshots the Broker/Attempt ledger after the negative phase, after the
   approved phase and after the auxiliary replay, then removes every container;
4. probes the frozen built adapter for its purpose guard;
5. writes a summary under ``artifacts/g4f/f2/`` that separates what was
   observed (per-dispatch journal + ledger + DSH trace + adapter probe) from
   what remains UNVERIFIED (no authoritative merged tool registry export).

It never reads a Key, never calls a real provider and never opens a network
socket. The launcher's own checks are recorded but not trusted for the ledger;
the numbers below are recomputed from read-only SQLite copies.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
G4_SCRIPTS = REPO / "scripts" / "g4"
for entry in (REPO / "src", G4_SCRIPTS):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

import lib_g4 as lib  # noqa: E402
import lib_g4c as libc  # noqa: E402
import lib_g3d as lib3d  # noqa: E402

OUT = REPO / "artifacts" / "g4f" / "f2"
PYTHON = sys.executable
LAUNCH = G4_SCRIPTS / "launch_c.py"
ADAPTER_PROBE = REPO / "tests/integration/g4_f2/adapter_purpose_probe.mjs"
EXPECTED_CASES = {
    "unapproved_tool_name": "ADMISSION_TOOL_SCHEMA_MISMATCH",
    "modified_approved_schema": "ADMISSION_TOOL_SCHEMA_MISMATCH",
    "extra_tool_alongside_approved": "ADMISSION_TOOL_SCHEMA_MISMATCH",
    "duplicate_approved_tool": "ADMISSION_TOOL_SCHEMA_MISMATCH",
    "message_tool_call_bash": "ADMISSION_TOOL_SCHEMA_MISMATCH",
    "message_tool_addition_bash": "ADMISSION_TOOL_SCHEMA_MISMATCH",
    "message_tool_removal_bash": "ADMISSION_TOOL_SCHEMA_MISMATCH",
}
AUXILIARY_CASES = {
    "auxiliary_purpose_title": "BAD_TYPE",
    "auxiliary_purpose_title_replay": "BAD_TYPE",
}

RAW_PROBE = r'''
import hashlib, json, os, socket, sys

SOCKET = "/work/g3b/bridge.sock"
PHASE = sys.argv[1]
out = {"phase": PHASE, "uid": os.getuid(), "gid": os.getgid(), "cases": []}
fixture = json.load(open("/project/fixtures/capture-tools.json"))
approved = json.loads(fixture["tools"][0]["canonical_json"])
approved_name = fixture["tools"][0]["name"]


def payload(session, tools, purpose="conversation", messages=None):
    return {"sessionId": session, "provider": "offline-test-only-g3b",
            "model": "fixture-bridge-v1",
            "messages": messages or [
                {"role": "user", "content": [{"type": "text", "text": "G4F2_RAW"}]}],
            "tools": tools, "system": None, "maxTokens": 256,
            "stream": True, "purpose": purpose}


def exchange(label, body):
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False, allow_nan=False).encode()
    transport = "tr-" + hashlib.sha256(label.encode()).hexdigest()[:32]
    document = {"v": 1, "kind": "request", "transport_id": transport,
                "seq": 0, "payload": body,
                "hash": hashlib.sha256(canonical).hexdigest()}
    line = json.dumps(document, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(20.0)
    frames = []
    try:
        sock.connect(SOCKET)
        sock.sendall(line)
        buffer = b""
        while True:
            data = sock.recv(65536)
            if not data:
                break
            buffer += data
            while b"\n" in buffer:
                raw, buffer = buffer.split(b"\n", 1)
                if not raw:
                    continue
                frame = json.loads(raw)
                frames.append(frame)
                if frame.get("kind") in ("error", "finish"):
                    code = (frame.get("payload") or {}).get("code")
                    out["cases"].append({"label": label, "transport": transport,
                                         "terminal": frame.get("kind"),
                                         "code": code,
                                         "frame_kinds": [f.get("kind") for f in frames]})
                    return
        out["cases"].append({"label": label, "transport": transport,
                             "terminal": "eof", "code": None,
                             "frame_kinds": [f.get("kind") for f in frames]})
    finally:
        sock.close()


def run_negatives():
    bash = {"name": "bash", "description": "run shell",
            "parameters": {"type": "object",
                           "properties": {"command": {"type": "string"}}}}
    modified = json.loads(json.dumps(approved))
    modified["parameters"]["properties"]["path"] = {"type": "string"}
    extra = {"name": "fs_read", "description": "read files",
             "parameters": {"type": "object", "properties": {}}}
    exchange("unapproved_tool_name", payload("g4f2-raw-1", [bash]))
    exchange("modified_approved_schema", payload("g4f2-raw-2", [modified]))
    exchange("extra_tool_alongside_approved", payload("g4f2-raw-3", [approved, extra]))
    exchange("duplicate_approved_tool", payload("g4f2-raw-4",
                                                [approved, approved]))
    exchange("message_tool_call_bash", payload(
        "g4f2-raw-5", [approved],
        messages=[{"role": "assistant", "content": [
            {"type": "tool-call", "id": "call-raw-1", "name": "bash",
             "arguments": "{}"}]}]))
    exchange("message_tool_addition_bash", payload(
        "g4f2-raw-6", [approved],
        messages=[{"role": "developer", "content": [
            {"type": "tool-addition", "toolName": "bash"}]}]))
    exchange("message_tool_removal_bash", payload(
        "g4f2-raw-7", [approved],
        messages=[{"role": "developer", "content": [
            {"type": "tool-removal", "toolName": "bash"}]}]))


def run_positive():
    exchange("approved_tool", payload("g4f2-raw-positive", [approved]))


def run_auxiliary():
    exchange("auxiliary_purpose_title", payload("g4f2-raw-title", [approved],
                                                purpose="title"))
    exchange("auxiliary_purpose_title_replay", payload("g4f2-raw-title", [approved],
                                                       purpose="title"))


if PHASE == "negatives":
    run_negatives()
elif PHASE == "positive":
    run_positive()
elif PHASE == "auxiliary":
    run_auxiliary()
else:
    raise SystemExit("unknown phase")
print("G4F2_RAW " + json.dumps(out, sort_keys=True))
'''


def utc() -> str:
    return lib.utc_now()


def write_json(path: Path, document: object) -> dict:
    return lib.write_json_atomic(path, document, mode=0o444)


def read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def podman(*args: str, timeout: float = 60.0) -> dict:
    proc = subprocess.run(["podman", *args], capture_output=True, text=True,
                          timeout=timeout)
    return {"argv": ["podman", *args], "exit": proc.returncode,
            "stdout": proc.stdout, "stderr": proc.stderr}


def containers_all() -> list[str]:
    record = podman("ps", "-a", "--format", "{{.Names}}")
    return [line for line in record["stdout"].splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# real DSH runs
# ---------------------------------------------------------------------------
def run_dsh_case(*, case: str, scenario: str, stage: Path, stamp: str) -> dict:
    evidence = OUT / "runs" / f"{case}-{stamp}"
    if evidence.exists() and any(evidence.iterdir()):
        raise SystemExit(f"evidence directory is not empty: {evidence}")
    run_id = f"g4f2-{case}-{stamp}"
    argv = [PYTHON, "-B", str(LAUNCH), "--case", f"f2-{case}",
            "--scenario", scenario, "--session", f"g4f2-{case}",
            "--stage", str(stage), "--run-id", run_id,
            "--evidence-dir", str(evidence), "--timeout", "180"]
    started = utc()
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=600)
    record = {
        "schema": "m0.g4f2.runner.v1", "case": case, "scenario": scenario,
        "run_id": run_id, "argv": argv, "utc_start": started,
        "utc_end": utc(), "exit": proc.returncode,
        "stdout_tail": proc.stdout[-4000:], "stderr_tail": proc.stderr[-4000:],
        "evidence": str(evidence),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    write_json(OUT / "runs" / f"{case}-{stamp}.runner.json", record)
    return record


def analyze_dsh_run(case: str, evidence: Path) -> dict:
    snapshot_path = evidence / "db" / "snapshot.json"
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8")) if \
        snapshot_path.is_file() else {}
    journal = read_jsonl(evidence / "run" / "dispatch-window.jsonl")
    trace_path = evidence / "traces" / "dsh-result.json"
    trace = json.loads(trace_path.read_text(encoding="utf-8")) if \
        trace_path.is_file() else {}
    counter_path = evidence / "receipt" / "received-count.json"
    counter = (json.loads(counter_path.read_text(encoding="utf-8")).get("count")
               if counter_path.is_file() else None)
    receipts = sorted((evidence / "receipt").glob("rcpt-*.json"))
    checks_path = evidence / "checks" / "checks.json"
    checks = json.loads(checks_path.read_text(encoding="utf-8")) if \
        checks_path.is_file() else {}
    events = trace.get("events") or []
    title_events = [event for event in events if event.get("type") == "session/title"]
    assistant = [event for event in events
                 if event.get("type") == "assistant/message"]
    request_headers = [event for event in events
                       if event.get("type") == "request/header"]
    stderr_markers = trace.get("stderr_markers") or []
    completed = [row for row in journal if row.get("outcome") == "completed"]
    rejected = [row for row in journal if row.get("outcome") == "rejected"]
    tool_rows = [tool for row in completed for tool in (row.get("tools") or [])]
    approved_rows = [tool for tool in tool_rows if tool.get("approved")]

    def _tool_digest(tool: object) -> str | None:
        if not isinstance(tool, dict):
            return None
        try:
            raw = json.dumps(tool, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode("utf-8")
        except (TypeError, ValueError):
            return None
        return hashlib.sha256(raw).hexdigest()

    # The DSH candidate session log is the candidate-side view of the assembled
    # request header. Comparing it with the trusted Controller journal closes the
    # loop: the tool surface is observed on both sides of the same adapter call.
    header_tools = []
    for event in request_headers:
        header = ((event.get("data") or {}).get("header") or {})
        header_tools.append([
            {"name": tool.get("name"), "sha256": _tool_digest(tool)}
            for tool in (header.get("tools") or []) if isinstance(tool, dict)])
    journal_tools = [[
        {"name": tool.get("name"), "sha256": tool.get("schema_sha256")}
        for tool in (row.get("tools") or [])] for row in completed]
    summary = {
        "case": case,
        "launcher_exit": None,
        "checks_failures": checks.get("failures"),
        "checks_count": len(checks.get("checks") or []),
        "ledger": {
            "reservations": len(snapshot.get("reservations") or []),
            "claims": len(snapshot.get("claims") or []),
            "attempts": len(snapshot.get("attempts") or []),
            "intents": len(snapshot.get("intents") or []),
            "admissions": len(snapshot.get("admissions") or []),
            "fake_counter": snapshot.get("fake_counter"),
            "receipt_files": len(receipts),
            "counter_file": counter,
        },
        "dispatch": {
            "records": len(journal),
            "completed": len(completed),
            "rejected": len(rejected),
            "purposes": [row.get("purpose") for row in journal],
            "outcomes": [row.get("outcome") for row in journal],
            "origins": [row.get("origin") for row in journal],
            "tool_names": [tool.get("name") for tool in tool_rows],
            "tools_all_approved": bool(tool_rows) == bool(approved_rows)
            and len(tool_rows) == len(approved_rows),
            "tool_schema_sha256": [tool.get("schema_sha256") for tool in tool_rows],
            "approved_sha256": [tool.get("approved_sha256") for tool in tool_rows],
            "call_ids": [row.get("call_id") for row in completed],
            "reservation_ids": [row.get("reservation_id") for row in completed],
        },
        "dsh": {
            "event_count": trace.get("event_count"),
            "assistant_messages": len(assistant),
            "request_headers": len(request_headers),
            "title_events": len(title_events),
            "title_sources": [((event.get("data") or {}).get("source") or {}).get("kind")
                              for event in title_events],
            "tool_calls": len((trace.get("event_summary") or {}).get("tool_calls") or []),
            "request_header_tools": header_tools,
            "stderr_markers": stderr_markers,
            "final_response": trace.get("final_response"),
            "finish_reason": trace.get("finish_reason"),
        },
    }
    # Cross-source equality: the actual tool surface observed at the Controller
    # must match the DSH provider-request count and the Fake receipts.
    summary["consistency"] = {
        "dispatches_equal_assistant_messages":
            len(completed) == len(assistant),
        "receipts_equal_dispatches": len(receipts) == len(completed),
        "fake_counter_equal_dispatches": (counter if counter is not None else
                                          snapshot.get("fake_counter")) == len(completed),
        "no_rejected_dispatch": not rejected,
        "no_auxiliary_dispatch": all(row.get("purpose") in (None, "conversation")
                                     for row in journal),
        "every_completed_has_reservation":
            all(row.get("reservation_id") for row in completed),
        "dsh_request_header_matches_dispatch": header_tools == journal_tools,
    }
    return summary


# ---------------------------------------------------------------------------
# raw UDS (real candidate UID) matrix
# ---------------------------------------------------------------------------
def _copy_state(state: Path, dest: Path) -> dict:
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, mode=0o700)
    copied = []
    for name in ("broker.sqlite3", "broker.sqlite3-wal", "broker.sqlite3-shm",
                 "attempts.sqlite3", "attempts.sqlite3-wal",
                 "attempts.sqlite3-shm", "dispatch-window.jsonl"):
        source = state / name
        if not source.is_file():
            continue
        target = dest / name
        shutil.copy2(source, target)
        copied.append({"name": name, "bytes": target.stat().st_size,
                       "sha256": lib.sha256_file(target)})
    receipts = state / "receipts"
    receipt_rows = []
    if receipts.is_dir():
        for entry in sorted(receipts.iterdir()):
            if entry.is_file():
                target = dest / "receipts"
                target.mkdir(exist_ok=True, mode=0o700)
                shutil.copy2(entry, target / entry.name)
                receipt_rows.append(entry.name)
    return {"files": copied, "receipts": receipt_rows}


def _wait_journal(state: Path, expected: int, *, timeout: float = 10.0) -> int:
    """Wait until the Controller has fsynced the expected dispatch records.

    The terminal frame can reach the client before the worker's finally writes
    the last record; evidence must not race the journal.
    """
    deadline = time.monotonic() + timeout
    path = state / "dispatch-window.jsonl"
    while time.monotonic() < deadline:
        rows = read_jsonl(path)
        if len(rows) >= expected:
            return len(rows)
        time.sleep(0.05)
    return len(read_jsonl(path))


def _counts(dest: Path) -> dict:
    def query(path: Path, sql: str) -> int:
        try:
            conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        except sqlite3.Error:
            return -1
        try:
            return int(conn.execute(sql).fetchone()[0])
        except sqlite3.Error:
            return -1
        finally:
            conn.close()
    return {
        "reservations": query(dest / "broker.sqlite3",
                              "SELECT COUNT(*) FROM budget_reservations"),
        "claims": query(dest / "broker.sqlite3",
                        "SELECT COUNT(*) FROM budget_dispatch_claims"),
        "attempts": query(dest / "attempts.sqlite3",
                          "SELECT COUNT(*) FROM g3b_attempts"),
        "intents": query(dest / "attempts.sqlite3",
                          "SELECT COUNT(*) FROM g3b_send_intents"),
        "receipt_files": len(list((dest / "receipts").glob("rcpt-*.json"))),
        "journal_records": len(read_jsonl(dest / "dispatch-window.jsonl")),
    }


def run_raw_uds(*, stage: Path, stamp: str) -> dict:
    import argparse as _argparse
    import launch_c  # noqa: E402  (G4-C launcher, imported only)

    evidence = OUT / f"raw-uds-{stamp}"
    if evidence.exists():
        raise SystemExit(f"raw evidence directory exists: {evidence}")
    run_id = f"g4f2-raw-{stamp}"
    args = _argparse.Namespace(
        case="f2-raw", sub="", scenario="echo", session="g4f2-raw",
        prompt="G4F2_RAW", stage=str(stage), run_id=run_id,
        evidence_dir=str(evidence), timeout=180.0, ready_timeout=30.0,
        stop_grace=5.0, keep_run=False, candidate_mode="hold",
        hold_seconds=600, label="f2raw", crash_hook=None, max_calls=None,
        steps=None)
    launcher = launch_c.G4CLauncher(args)
    run_dir = launcher.run_dir
    hold_name = launcher.candidate_name
    report: dict = {"schema": "m0.g4f2.raw-uds.v1", "run_id": run_id,
                    "evidence": str(evidence), "utc_start": utc(),
                    "phases": [], "problems": []}
    started = False
    try:
        launcher.preflight()
        launcher.create_run()
        launcher.write_configs()
        launcher.start_trusted()
        started = True
        argv = lib3d.candidate_run_argv(
            podman="podman", rootfs=str(lib3d.ROOTFS),
            stage_candidate=str(launcher.stage_dir / "candidate"),
            deps=str(lib3d.DEPS), run_dir=str(run_dir),
            name=hold_name, mode="hold", label="f2raw", hold_seconds=600)
        record = launcher.cmd(argv, name="podman-run-candidate-hold", timeout=60)
        report["start_hold"] = {"exit": record["exit"]}
        if record["exit"] != 0:
            report["problems"].append("hold_start_failed")
        else:
            deadline = time.monotonic() + 30.0
            while time.monotonic() < deadline:
                status = launcher.podman_status(hold_name)
                if status == "running":
                    break
                time.sleep(0.2)
            else:
                report["problems"].append("hold_container_not_running")
            expected_records = {"negatives": 7, "positive": 8, "auxiliary": 8}
            for phase in ("negatives", "positive", "auxiliary"):
                exec_argv = ["podman", "exec", hold_name,
                             "/opt/python/bin/python3.11", "-B", "-c",
                             RAW_PROBE, phase]
                exec_record = launcher.cmd(exec_argv, name=f"probe-{phase}",
                                           timeout=180)
                _wait_journal(run_dir / "state", expected_records[phase])
                payload = None
                for line in (exec_record.get("stdout") or "").splitlines():
                    if line.startswith("G4F2_RAW "):
                        payload = json.loads(line[len("G4F2_RAW "):])
                        break
                snap_dir = evidence / f"snapshot-after-{phase}"
                copied = _copy_state(run_dir / "state", snap_dir)
                counts = _counts(snap_dir)
                report["phases"].append({
                    "phase": phase, "exec_exit": exec_record.get("exit"),
                    "payload": payload, "snapshot": copied, "counts": counts,
                    "stderr_tail": (exec_record.get("stderr") or "")[-2000:],
                })
                if payload is None:
                    report["problems"].append(f"{phase}_probe_output_missing")
        report["journal"] = read_jsonl(run_dir / "state" / "dispatch-window.jsonl")
    finally:
        try:
            if started:
                launcher._copy_state_assets()
        except Exception as exc:  # noqa: BLE001 - evidence collection is best effort
            report["problems"].append(f"copy_state_assets:{type(exc).__name__}")
        try:
            launcher.cleanup()
        except Exception as exc:  # noqa: BLE001 - cleanup must be attempted
            report["problems"].append(f"cleanup:{type(exc).__name__}")
        report["utc_end"] = utc()
        report["containers_after"] = containers_all()
        if report["containers_after"]:
            report["problems"].append("containers_not_empty")
    report["verdict"] = judge_raw(report)
    write_json(OUT / f"raw-uds-{stamp}.json", report)
    return report


def judge_raw(report: dict) -> dict:
    phases = {phase["phase"]: phase for phase in report.get("phases") or []}
    negative_rows = []
    for case in (phases.get("negatives", {}).get("payload") or {}).get("cases") or []:
        expected = EXPECTED_CASES.get(case.get("label"))
        if expected is None:
            continue
        negative_rows.append({
            "label": case.get("label"), "expected": expected,
            "actual": case.get("code"), "terminal": case.get("terminal"),
            "ok": case.get("terminal") == "error" and case.get("code") == expected,
        })
    auxiliary_rows = []
    for case in (phases.get("auxiliary", {}).get("payload") or {}).get("cases") or []:
        expected = AUXILIARY_CASES.get(case.get("label"))
        if expected is None:
            continue
        auxiliary_rows.append({
            "label": case.get("label"), "expected": expected,
            "actual": case.get("code"), "terminal": case.get("terminal"),
            "ok": case.get("terminal") == "error" and case.get("code") == expected,
        })
    positive = ((phases.get("positive", {}).get("payload") or {}).get("cases") or [{}])[0]
    counts = {name: phase.get("counts") for name, phase in phases.items()}
    zero = {"reservations": 0, "claims": 0, "attempts": 0, "intents": 0,
            "receipt_files": 0}
    after_negative = counts.get("negatives") or {}
    after_positive = counts.get("positive") or {}
    after_auxiliary = counts.get("auxiliary") or {}
    verdict = {
        "negative_matrix_all_rejected": bool(negative_rows)
        and all(row["ok"] for row in negative_rows),
        "negatives_left_ledger_at_zero": all(
            after_negative.get(key) == value for key, value in zero.items()),
        "positive_accounted": (
            positive.get("terminal") == "finish"
            and after_positive.get("reservations") == 1
            and after_positive.get("claims") == 1
            and after_positive.get("attempts") == 1
            and after_positive.get("receipt_files") == 1),
        "auxiliary_rejected_at_protocol": bool(auxiliary_rows)
        and all(row["ok"] for row in auxiliary_rows),
        "auxiliary_left_ledger_unchanged": after_auxiliary == after_positive,
        "no_auxiliary_journal_record":
            after_auxiliary.get("journal_records") == after_positive.get("journal_records"),
        "containers_empty": report.get("containers_after") == [],
    }
    return {"negative_cases": negative_rows,
            "auxiliary_cases": auxiliary_rows,
            "positive_case": positive,
            "counts": counts,
            "checks": verdict,
            "ok": all(verdict.values())}


# ---------------------------------------------------------------------------
# adapter probe + merged entry list
# ---------------------------------------------------------------------------
def run_adapter_probe(stage: Path) -> dict:
    adapter = stage / "candidate/runtime/bridge/lib/index.js"
    node = shutil.which("node")
    if node is None or not adapter.is_file():
        return {"ok": False, "problems": ["node_or_adapter_missing"]}
    proc = subprocess.run([node, str(ADAPTER_PROBE), str(adapter)],
                          capture_output=True, text=True, timeout=120)
    lines = [line for line in proc.stdout.splitlines() if line.startswith("{")]
    report = json.loads(lines[-1]) if lines else {"ok": False}
    report["probe_exit"] = proc.returncode
    report["ok"] = (
        proc.returncode == 0
        and report.get("title", {}).get("message") == "G3B_BRIDGE_PURPOSE"
        and report.get("conversation", {}).get("message") == "G3B_BRIDGE_CONNECT_FAILED")
    return report


def merged_entry_ids() -> dict:
    path = REPO / "artifacts/g4/runtime/merged-config.yml"
    if not path.is_file():
        return {"available": False}
    import re
    text = path.read_text(encoding="utf-8")
    ids = re.findall(r"^- id: (\S+)", text, re.M)
    return {
        "available": True, "path": str(path),
        "sha256": lib.sha256_file(path), "count": len(ids), "ids": ids,
        "note": ("merged Cordis entry list from G4-B; NOT an authoritative "
                 "registry and NOT a per-run tool export"),
    }


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", default=None)
    parser.add_argument("--only", default=None,
                        help="comma-separated: echo,tool,raw,adapter")
    args = parser.parse_args(argv)
    if os.geteuid() != 0:
        sys.stderr.write("G4F2_EVIDENCE_NEEDS_HOST_ROOT\n")
        return lib.EXIT_ENVIRONMENT
    stage = Path(args.stage).resolve() if args.stage else \
        sorted(path for path in libc.STAGE_ROOT.glob("stage-*")
               if (path / "manifest.json").is_file())[-1]
    if not stage.is_dir():
        sys.stderr.write("G4F2_STAGE_MISSING\n")
        return lib3d.EXIT_STAGE_INVALID
    only = set((args.only or "echo,tool,raw,adapter").split(","))
    OUT.mkdir(parents=True, exist_ok=True)
    stamp = utc().replace("-", "").replace(":", "").replace("T", "").replace("Z", "")
    summary: dict = {
        "schema": "m0.g4f2.evidence.v1", "utc_start": utc(),
        "head": lib.git_head(),
        "worktree_status": (lib.git_optional("status", "--porcelain=v1", "-uall")
                            or "").splitlines(),
        "stage": {
            "path": str(stage),
            "manifest_sha256": lib.sha256_file(stage / "manifest.json"),
            "stage_tree_sha256": lib3d.sha256_tree(stage),
            "base_sha": json.loads((stage / "manifest.json").read_text()).get("head_at_build"),
        },
        "environment": {
            "euid": os.geteuid(), "python": sys.version.split()[0],
            "node": subprocess.run(["node", "--version"], capture_output=True,
                                   text=True).stdout.strip(),
            "containers_before": containers_all(),
            "network": "none (launcher argv + container inspect)",
            "provider_route": "offline-test-only-g3b / fixture-bridge-v1 (synthetic Fake)",
        },
        "runs": [], "raw_uds": None, "adapter": None,
        "merged_entry_list": merged_entry_ids(),
    }
    try:
        for case, scenario in (("echo", "echo"), ("tool", "tool")):
            if case not in only:
                continue
            record = run_dsh_case(case=case, scenario=scenario, stage=stage,
                                  stamp=stamp)
            analysis = analyze_dsh_run(case, Path(record["evidence"]))
            analysis["launcher_exit"] = record["exit"]
            summary["runs"].append(analysis)
        if "raw" in only:
            summary["raw_uds"] = run_raw_uds(stage=stage, stamp=stamp)
        if "adapter" in only:
            summary["adapter"] = run_adapter_probe(stage)
    finally:
        summary["utc_end"] = utc()
        summary["containers_after"] = containers_all()
        summary["rootfs_sha256"] = lib3d.sha256_tree(lib3d.ROOTFS)
        summary["deps_sha256"] = lib3d.sha256_tree(lib3d.DEPS)
        summary["rootfs_canonical"] = summary["rootfs_sha256"] == lib3d.ROOTFS_CANON
        summary["deps_canonical"] = summary["deps_sha256"] == lib3d.DEPS_CANON
        summary["real_model_calls"] = 0
        summary["real_external_http_calls"] = 0
        summary["provider_keys_seen"] = 0
        summary["live_gate"] = "BLOCKED"
        summary["registry_authority"] = "UNVERIFIED_NO_AUTHORITATIVE_MERGED_REGISTRY"
        summary["actual_tool_surface_source"] = (
            "controller.per-dispatch dispatch-window journal + Admission approved "
            "schema SHA-256 + DSH session trace request/header")
        write_json(OUT / f"summary-{stamp}.json", summary)
        link = OUT / "summary.json"
        if not link.is_file():
            write_json(link, summary)
        else:
            write_json(link, summary)
    problems = []
    for run in summary["runs"]:
        if run["launcher_exit"] != 0:
            problems.append(f"{run['case']}_launcher_exit")
        if not all(run["consistency"].values()):
            problems.append(f"{run['case']}_consistency")
    if summary["raw_uds"] is not None and not summary["raw_uds"]["verdict"]["ok"]:
        problems.append("raw_uds_verdict")
    if summary["adapter"] is not None and not summary["adapter"].get("ok"):
        problems.append("adapter_probe")
    if summary["containers_after"]:
        problems.append("containers_not_empty")
    if not summary["rootfs_canonical"] or not summary["deps_canonical"]:
        problems.append("canonical_drift")
    summary["problems"] = problems
    summary["ok"] = not problems
    write_json(OUT / "summary.json", summary)
    print(json.dumps({"ok": summary["ok"], "problems": problems,
                      "summary": str(OUT / "summary.json")}, sort_keys=True))
    return 0 if summary["ok"] else lib3d.EXIT_CASE_FAILED


if __name__ == "__main__":
    raise SystemExit(main())
