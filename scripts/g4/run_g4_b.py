#!/usr/bin/env python3
"""G4-B runner: one real DSH tool run plus one raw-UDS Controller run.

Two independent, containerised, no-key/no-network runs:

``tool``    the frozen G3-D launcher (``scripts/g3d/launch.py --scenario tool``)
            is invoked unchanged, so the real DSH runtime performs one real
            turn with two provider requests.  The ledger is read back from the
            Broker/Attempt SQLite files, the Fake receipts and the candidate
            stderr markers (B02/B05/B08).

``raw-uds`` a **hold** candidate container (the same stage, UID map, mounts and
            ``--network none``) is started against a live trusted Controller and
            ``podman exec`` sends provider payloads from the real candidate
            principal: unapproved/modified/extra tool schemas (B04), then a
            valid request and one request over the admission quota (B06).
            Rejections must leave the ledger at zero; accepted requests must
            each take an independent Reserve/Claim/Attempt/Receipt.

The launcher is only *called*; ``scripts/g3d/**`` is never modified.  Every
container is removed at the end and ``podman ps -a`` is re-checked empty.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "g3d"))
import lib_g4 as lib  # noqa: E402
import lib_g3d as lib3d  # noqa: E402

REPO = lib.REPO_ROOT
LAUNCH = REPO / "scripts" / "g3d" / "launch.py"
PYTHON = sys.executable

RAW_UDS_CODE = r'''
import json, sys
sys.path.insert(0, "/project/run/probes")
import probe_common as pc

phase = sys.argv[1]
fixture = json.load(open("/project/fixtures/capture-tools.json"))
approved = fixture["tools"][0]["canonical_json"]
approved = json.loads(approved)
name = fixture["tools"][0]["name"]
out = {"phase": phase, "uid": __import__("os").getuid(),
       "identity": pc.identity()["uid"], "cases": []}


def send(label, payload):
    # the protocol requires exactly tr-<32 lowercase hex>
    import hashlib
    transport = "tr-" + hashlib.sha256(label.encode("utf-8")).hexdigest()[:32]
    record = pc.exchange(pc.envelope_bytes(payload, transport_id=transport),
                         timeout=8.0)
    out["cases"].append({
        "label": label,
        "terminal": record.get("terminal"),
        "error_code": record.get("error_code"),
        "frame_count": record.get("frame_count"),
        "connected": record.get("connected"),
        "last_frame": (record.get("raw_lines") or [""])[-1][:400],
    })


if phase == "negatives":
    send("unapproved_tool_name", pc.request_payload(
        session="g4b-raw-unapproved",
        tools=[{"name": "bash", "description": "run shell",
                "parameters": {"type": "object",
                               "properties": {"command": {"type": "string"}}}}]))
    modified = json.loads(json.dumps(approved))
    modified["parameters"]["properties"]["path"] = {"type": "string"}
    send("modified_approved_schema", pc.request_payload(
        session="g4b-raw-modified", tools=[modified]))
    send("extra_tool_alongside_approved", pc.request_payload(
        session="g4b-raw-extra",
        tools=[approved, {"name": "fs_read", "description": "read files",
                          "parameters": {"type": "object", "properties": {}}}]))
    send("file_block", pc.request_payload(
        session="g4b-raw-file",
        messages=[{"role": "user", "content": [
            {"type": "text", "text": "x"},
            {"type": "file", "file": {"path": "/work/session/x"}}]}],
        tools=[approved]))
    selfauth = pc.request_payload(session="g4b-raw-selfauth", tools=[approved])
    selfauth["authorized"] = True
    send("self_authorization_field", selfauth)
    send("auxiliary_purpose_title", pc.request_payload(
        session="g4b-raw-title", tools=[approved], purpose="title"))
elif phase == "positive":
    send("valid_request_1", pc.request_payload(
        session="g4b-raw-valid-1", tools=[approved]))
elif phase == "quota":
    send("valid_request_over_quota", pc.request_payload(
        session="g4b-raw-valid-2", tools=[approved]))
else:
    out["error"] = "unknown phase"

print("G4B_RAW_UDS " + json.dumps(out, sort_keys=True))
'''


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default=str(lib.G4_RUNTIME))
    parser.add_argument("--stage", default=str(lib.STAGE_DEFAULT))
    parser.add_argument("--skip-tool", action="store_true")
    parser.add_argument("--skip-raw-uds", action="store_true")
    parser.add_argument("--tool-timeout", type=float, default=240.0)
    parser.add_argument("--keep-containers", action="store_true")
    return parser.parse_args(argv)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def run_command(argv: list[str], *, timeout: float, log_path: Path,
                env: dict | None = None) -> dict:
    started = time.monotonic()
    proc = subprocess.run(argv, cwd=str(REPO), capture_output=True, text=True,
                          timeout=timeout, env=env)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        f"$ {' '.join(argv)}\nexit={proc.returncode}\n--- stdout ---\n"
        f"{proc.stdout}\n--- stderr ---\n{proc.stderr}\n", encoding="utf-8")
    return {"argv": argv, "exit": proc.returncode, "stdout": proc.stdout[-8000:],
            "stderr": proc.stderr[-8000:], "seconds": round(time.monotonic() - started, 2),
            "log": str(log_path)}


def podman(argv: list[str], *, timeout: float = 120.0) -> dict:
    proc = subprocess.run(["podman", *argv], capture_output=True, text=True,
                          timeout=timeout)
    return {"argv": ["podman", *argv], "exit": proc.returncode,
            "stdout": proc.stdout.strip(), "stderr": proc.stderr.strip()[-2000:]}


def containers_all() -> list[str]:
    record = podman(["ps", "-a", "--format", "{{.Names}}"])
    if record["exit"] != 0:
        return [f"podman_ps_failed:{record['stderr']}"]
    return [line for line in record["stdout"].splitlines() if line.strip()]


def snapshot_state(run_dir: Path, dest: Path, tag: str) -> dict:
    """Copy and read the live Broker/Attempt ledgers at one instant."""
    return snapshot_from_files(run_dir / "state" / "broker.sqlite3",
                               run_dir / "state" / "attempts.sqlite3",
                               run_dir / "state" / "receipts",
                               dest, tag)


def snapshot_from_files(broker_source: Path, attempts_source: Path,
                        receipt_source: Path, dest: Path, tag: str) -> dict:
    dest.mkdir(parents=True, exist_ok=True)
    copied = []
    for source in (broker_source, Path(str(broker_source) + "-wal"),
                   Path(str(broker_source) + "-shm"), attempts_source,
                   Path(str(attempts_source) + "-wal"),
                   Path(str(attempts_source) + "-shm")):
        if source.is_file():
            target = dest / f"{tag}-{source.name}"
            shutil.copyfile(source, target)
            copied.append({"name": source.name, "bytes": target.stat().st_size,
                           "sha256": lib.sha256_file(target)})
    result: dict = {"tag": tag, "utc": lib.utc_now(), "files": copied}
    # The Broker creates ``budget_dispatch_claims`` lazily on the first claim,
    # so a pre-send snapshot legitimately has no such table.  A missing table is
    # reported as an empty list plus ``missing_tables``; it is not an error.
    broker = dest / f"{tag}-broker.sqlite3"
    if broker.is_file():
        with sqlite3.connect(f"file:{broker}?mode=ro", uri=True) as conn:
            result["reservations"] = _query(
                conn, "SELECT reservation_id,route_id,model,status,cost,estimated "
                      "FROM budget_reservations ORDER BY rowid")
            result["claims"] = _query(
                conn, "SELECT call_id,reservation_id,request_digest,status "
                      "FROM budget_dispatch_claims ORDER BY rowid")
            result["missing_tables"] = _missing_tables(
                conn, ("budget_reservations", "budget_dispatch_claims"))
    attempts = dest / f"{tag}-attempts.sqlite3"
    if attempts.is_file():
        with sqlite3.connect(f"file:{attempts}?mode=ro", uri=True) as conn:
            result["attempts"] = _query(
                conn, "SELECT attempt_id,call_id,reservation_id,state,receipt_id,"
                      "payload_digest,prepared_digest,logical_step,settlement_json "
                      "FROM g3b_attempts ORDER BY created_utc")
            result["intents"] = _query(
                conn, "SELECT intent_id,call_id,reservation_id,state,reason "
                      "FROM g3b_send_intents ORDER BY created_utc")
            result.setdefault("missing_tables", []).extend(
                _missing_tables(conn, ("g3b_attempts", "g3b_send_intents")))
    result["counts"] = {
        "reservations": len(result.get("reservations") or []),
        "claims": len(result.get("claims") or []),
        "attempts": len(result.get("attempts") or []),
        "intents": len(result.get("intents") or []),
    }
    counter = receipt_source / "received-count.json"
    if counter.is_file():
        try:
            result["fake_counter"] = int(json.loads(
                counter.read_text(encoding="utf-8")).get("count", 0))
        except (OSError, ValueError, json.JSONDecodeError):
            result["fake_counter"] = None
    else:
        result["fake_counter"] = 0
    return result


def _missing_tables(conn: sqlite3.Connection, names: tuple[str, ...]) -> list[str]:
    present = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    return sorted(name for name in names if name not in present)


def _query(conn: sqlite3.Connection, sql: str) -> list[dict]:
    try:
        cursor = conn.execute(sql)
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc):
            return []
        raise
    columns = [column[0] for column in cursor.description or ()]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def receipts(root: Path) -> list[dict]:
    rows = []
    if not root.is_dir():
        return rows
    for path in sorted(root.glob("rcpt-*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        rows.append({"file": path.name,
                     "receipt_id": document.get("receipt_id"),
                     "raw_sha256": document.get("raw_sha256"),
                     "raw_length": document.get("raw_length"),
                     "mode": document.get("mode"),
                     "nonce": document.get("nonce"),
                     "usage": document.get("usage")})
    return rows


# ---------------------------------------------------------------------------
# run 1: the real DSH tool turn
# ---------------------------------------------------------------------------
def tool_run(out_dir: Path, stage: Path, timeout: float) -> dict:
    evidence = out_dir / "run-tool"
    if evidence.exists():
        shutil.rmtree(evidence)
    run_id = "g4b-tool-" + lib.utc_now().replace("-", "").replace(":", "").replace("T", "").replace("Z", "")
    argv = [PYTHON, "-B", str(LAUNCH), "--case", "g4b-tool", "--scenario", "tool",
            "--session", "g4b-tool-session", "--run-id", run_id,
            "--stage", str(stage), "--evidence-dir", str(evidence),
            "--timeout", "180"]
    env = {"PATH": os.environ.get("PATH", "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"),
           "HOME": "/root", "PYTHONDONTWRITEBYTECODE": "1"}
    record = run_command(argv, timeout=timeout, log_path=out_dir / "logs" / "tool-run.log",
                         env=env)
    report: dict = {"run_id": run_id, "evidence": str(evidence),
                    "command": record, "launcher_exit": record["exit"]}
    parsed = None
    for line in reversed(record["stdout"].splitlines()):
        try:
            candidate = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict) and "run_id" in candidate:
            parsed = candidate
            break
    report["launcher"] = parsed
    report["ledger"] = analyse_tool_evidence(evidence, run_id)
    return report


def analyse_tool_evidence(evidence: Path, run_id: str) -> dict:
    """Read the durable copies the launcher wrote before deleting ``$RUN``.

    ``cleanup()`` removes the run directory by design, so the authoritative
    post-run artifacts are ``<evidence>/db/*.sqlite3``, ``<evidence>/receipt/``
    and ``<evidence>/peercred/``.
    """
    db_dir = evidence / "db"
    receipt_dir = evidence / "receipt"
    zero = {"reservations": [], "claims": [], "attempts": [], "intents": [],
            "counts": {"reservations": 0, "claims": 0, "attempts": 0, "intents": 0},
            "fake_counter": 0}
    result: dict = {"run_id": run_id, "problems": []}
    if not (db_dir / "broker.sqlite3").is_file():
        result["problems"].append("evidence_db_missing")
        result["ledger"] = zero
        return result
    snapshot = snapshot_from_files(db_dir / "broker.sqlite3",
                                   db_dir / "attempts.sqlite3",
                                   receipt_dir,
                                   evidence / "state-snapshot", "final")
    receipts_rows = receipts(receipt_dir)
    module_evidence = evidence / "peercred" / "trusted-modules.json"
    result["ledger"] = {
        "reservations": snapshot.get("reservations"),
        "claims": snapshot.get("claims"),
        "attempts": snapshot.get("attempts"),
        "intents": snapshot.get("intents"),
        "counts": snapshot.get("counts"),
        "fake_counter": snapshot.get("fake_counter"),
    }
    result["receipts"] = receipts_rows
    result["fake_received_counter"] = snapshot.get("fake_counter")
    # Two-provider-request ledger: two independent Reserve/Claim/Attempt/Receipt.
    two_cycle = _two_cycle(result["ledger"], receipts_rows)
    result["two_cycle"] = two_cycle
    result["container_modules"] = _module_rows(module_evidence)
    markers, marker_sources = _marker_lines(evidence)
    result["candidate_markers"] = markers
    result["marker_sources"] = marker_sources
    result["registry_markers"] = markers.get("G3B_BRIDGE_REGISTRY")
    if len(two_cycle["cycles"]) != 2:
        result["problems"].append(f"expected_2_cycles_got_{len(two_cycle['cycles'])}")
    if not two_cycle["all_ok"]:
        result["problems"].append("cycle_mapping_failed")
    if not result["container_modules"]["ok"]:
        result["problems"].append("container_modules_not_matching_git")
    if not markers.get("G3B_BRIDGE_REGISTRY"):
        result["problems"].append("adapter_registry_marker_missing")
    if snapshot.get("fake_counter") != len(receipts_rows):
        result["problems"].append("fake_counter_receipt_mismatch")
    return result


def _two_cycle(ledger: dict, receipts_rows: list[dict]) -> dict:
    attempts = sorted(ledger.get("attempts") or [],
                      key=lambda row: int(row.get("logical_step") or 0))
    claims = {(row.get("call_id")): row for row in ledger.get("claims") or []}
    # join on receipt_id: the Fake receipt's ``nonce`` is the send nonce, not a id
    received = {row.get("receipt_id"): row for row in receipts_rows}
    cycles = []
    for attempt in attempts:
        claim = claims.get(attempt.get("call_id")) or {}
        receipt = received.get(attempt.get("receipt_id")) or {}
        cycles.append({
            "logical_step": attempt.get("logical_step"),
            "call_id": attempt.get("call_id"),
            "reservation_id": attempt.get("reservation_id"),
            "receipt_id": attempt.get("receipt_id"),
            "state": attempt.get("state"),
            "prepared_digest": attempt.get("prepared_digest"),
            "payload_digest": attempt.get("payload_digest"),
            "claim_request_digest": claim.get("request_digest"),
            "claim_reservation_id": claim.get("reservation_id"),
            "receipt_raw_sha256": receipt.get("raw_sha256"),
            "prepared_matches_claim": (claim.get("request_digest")
                                       == attempt.get("prepared_digest")),
            "payload_matches_receipt": (receipt.get("raw_sha256")
                                        == attempt.get("payload_digest")),
            "reservation_link_ok": (claim.get("reservation_id")
                                    == attempt.get("reservation_id")
                                    == _reservation_for(ledger, attempt)),
        })
    distinct_calls = len({cycle["call_id"] for cycle in cycles})
    distinct_reservations = len({cycle["reservation_id"] for cycle in cycles})
    distinct_receipts = len({cycle["receipt_id"] for cycle in cycles})
    all_ok = bool(cycles) and all(
        cycle["prepared_matches_claim"] and cycle["payload_matches_receipt"]
        and cycle["reservation_link_ok"] for cycle in cycles)
    return {"cycles": cycles,
            "distinct_call_ids": distinct_calls,
            "distinct_reservation_ids": distinct_reservations,
            "distinct_receipt_ids": distinct_receipts,
            "all_ok": all_ok and distinct_calls == len(cycles)
            and distinct_reservations == len(cycles)
            and distinct_receipts == len(cycles)}


def _reservation_for(ledger: dict, attempt: dict) -> str | None:
    for row in ledger.get("reservations") or []:
        if row.get("reservation_id") == attempt.get("reservation_id"):
            return row.get("reservation_id")
    return None


def _module_rows(path: Path) -> dict:
    if not path.is_file():
        return {"ok": False, "rows": [], "reason": "trusted-modules.json missing"}
    document = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for row in document.get("modules") or []:
        if not isinstance(row, dict):
            continue
        file_path = str(row.get("file") or "")
        relative = file_path.split("/src/", 1)[-1]
        try:
            expected = lib.git_blob_sha256(lib.PRODUCT_BASE, f"src/{relative}")
        except lib.G4Error:
            expected = None
        rows.append({"module": row.get("module"), "file": file_path,
                     "sha256": row.get("sha256"), "git_cf40c6b_sha256": expected,
                     "matches_git": bool(expected) and expected == row.get("sha256")})
    return {"ok": bool(rows) and all(row["matches_git"] for row in rows),
            "count": len(rows), "rows": rows}


MARKER_PREFIXES = ("G3B_", "G3C_", "G3D_", "ADMISSION", "CANDIDATE_")


def _marker_lines(evidence: Path) -> tuple[dict, list[str]]:
    """Collect the adapter/runtime self-report lines from the real run.

    The candidate container's stderr is not always part of ``candidate.log``;
    the SDK trace (``traces/dsh-result*.json``) stores the filtered
    ``stderr_markers`` list.  Both sources are read and the source is recorded.
    """
    markers: dict[str, list[str]] = {}
    sources: list[str] = []

    def add(line: str) -> None:
        for prefix in MARKER_PREFIXES:
            if line.startswith(prefix):
                markers.setdefault(line.split(" ", 1)[0], []).append(line[:400])
                return

    log_path = evidence / "run" / "candidate.log"
    if log_path.is_file():
        sources.append("run/candidate.log")
        for line in log_path.read_text(encoding="utf-8",
                                       errors="replace").splitlines():
            add(line)
    traces = evidence / "traces"
    if traces.is_dir():
        for path in sorted(traces.glob("*.json")):
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            lines = document.get("stderr_markers") if isinstance(document, dict) else None
            if not isinstance(lines, list):
                continue
            sources.append(f"traces/{path.name}")
            for line in lines:
                if isinstance(line, str):
                    add(line)
    return markers, sorted(set(sources))


# ---------------------------------------------------------------------------
# run 2: raw UDS from the real candidate principal
# ---------------------------------------------------------------------------
def raw_uds_run(out_dir: Path, stage: Path, *, keep: bool = False) -> dict:
    import launch as launcher_mod  # noqa: E402  (frozen G3-D launcher, imported only)

    evidence = out_dir / "raw-uds"
    if evidence.exists():
        shutil.rmtree(evidence)
    run_id = "g4b-raw-" + lib.utc_now().replace("-", "").replace(":", "").replace("T", "").replace("Z", "")
    args = argparse.Namespace(
        case="g4b-raw", sub="", scenario="echo", session="g4b-raw-session",
        prompt="G4B_RAW_UDS", stage=str(stage), run_id=run_id,
        evidence_dir=str(evidence), timeout=180.0, ready_timeout=30.0,
        stop_grace=5.0, keep_run=False)
    report: dict = {"run_id": run_id, "evidence": str(evidence), "steps": [],
                    "problems": []}
    _ExecState.snapshots = {}
    launcher = launcher_mod.Launcher(args)
    run_dir = launcher.run_dir
    hold_name = launcher.candidate_name
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
            deps=str(lib3d.DEPS), run_dir=str(run_dir), name=hold_name,
            mode="hold", label="hold", hold_seconds=600)
        record = launcher.cmd(argv, name="podman-run-candidate-hold", timeout=60)
        report["steps"].append({"step": "start_hold", "exit": record["exit"]})
        if record["exit"] != 0:
            report["problems"].append("hold_start_failed")
        else:
            if not _wait_running(hold_name, timeout=30.0):
                report["problems"].append("hold_container_not_running")
            for phase in ("negatives", "positive", "quota"):
                phase_record = _exec_probe(launcher, hold_name, phase)
                report["steps"].append(phase_record["step"])
                if phase_record["payload"] is None:
                    report["problems"].append(f"{phase}_probe_failed")
                setattr(_ExecState, phase, phase_record["payload"])
            report["negatives"] = getattr(_ExecState, "negatives", None)
            report["positive"] = getattr(_ExecState, "positive", None)
            report["quota"] = getattr(_ExecState, "quota", None)
        report["ledger_after_negatives"] = _ExecState.snapshots.get("negatives")
        report["ledger_after_positive"] = _ExecState.snapshots.get("positive")
        report["ledger_after_quota"] = _ExecState.snapshots.get("quota")
        report["judgement"] = _judge_raw_uds(report)
    finally:
        if not keep:
            _remove_container(hold_name)
            if started:
                launcher.records["cleanup_after_raw"] = True
                try:
                    launcher._copy_state_assets()
                except Exception as exc:  # noqa: BLE001
                    report["problems"].append(f"state_assets:{type(exc).__name__}")
                launcher.cleanup()
            else:
                launcher.cleanup()
        report["containers_after"] = containers_all()
        if report["containers_after"]:
            report["problems"].append("containers_not_empty_after_run")
    return report


class _ExecState:
    snapshots: dict[str, dict] = {}


def _wait_running(name: str, *, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        record = podman(["inspect", "--format", "{{.State.Running}}", name],
                        timeout=30)
        if record["exit"] == 0 and record["stdout"].strip() == "true":
            return True
        time.sleep(0.2)
    return False


def _exec_probe(launcher, container: str, phase: str) -> dict:
    argv = ["podman", "exec", container, "/opt/python/bin/python3.11", "-B",
            "-c", RAW_UDS_CODE, phase]
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=120)
    payload = None
    for line in proc.stdout.splitlines():
        if line.startswith("G4B_RAW_UDS "):
            payload = json.loads(line[len("G4B_RAW_UDS "):])
    step = {"step": f"probe_{phase}", "phase": phase, "exit": proc.returncode,
            "payload": payload, "stderr": proc.stderr[-1000:]}
    launcher.records.setdefault("g4b_probes", []).append(step)
    # Snapshot the ledger immediately after the probe returns.
    _ExecState.snapshots[phase] = snapshot_state(
        launcher.run_dir, launcher.evidence / "db-snapshots", phase)
    return step


def _judge_raw_uds(report: dict) -> dict:
    negatives = report.get("negatives") or {}
    positive = report.get("positive") or {}
    quota = report.get("quota") or {}
    ledger = {
        "negatives": report.get("ledger_after_negatives") or {},
        "positive": report.get("ledger_after_positive") or {},
        "quota": report.get("ledger_after_quota") or {},
    }
    expected_negative_codes = {
        "unapproved_tool_name": ("ADMISSION_TOOL_SCHEMA_MISMATCH",),
        "modified_approved_schema": ("ADMISSION_TOOL_SCHEMA_MISMATCH",),
        "extra_tool_alongside_approved": ("ADMISSION_TOOL_SCHEMA_MISMATCH",),
        "file_block": ("REQUEST_INVALID",),
        "self_authorization_field": ("ADMISSION_SELF_AUTH_DENIED", "UNKNOWN_FIELD"),
        "auxiliary_purpose_title": ("BAD_TYPE",),
    }
    negative_rows = []
    for case in negatives.get("cases") or []:
        code = case.get("error_code")
        expected = expected_negative_codes.get(case.get("label"), ())
        negative_rows.append({
            "label": case.get("label"),
            "expected_code": list(expected),
            "actual_code": code,
            "terminal": case.get("terminal"),
            "last_frame": case.get("last_frame"),
            "ok": case.get("terminal") == "error" and code in expected,
        })
    before = (ledger["negatives"].get("counts") or {})
    positive_row = (positive.get("cases") or [{}])[0]
    after_positive = ledger["positive"].get("counts") or {}
    quota_row = (quota.get("cases") or [{}])[0]
    after_quota = ledger["quota"].get("counts") or {}
    fake = {"negatives": ledger["negatives"].get("fake_counter"),
            "positive": ledger["positive"].get("fake_counter"),
            "quota": ledger["quota"].get("fake_counter")}
    verdict = {
        "negatives_all_rejected": all(row["ok"] for row in negative_rows) and bool(negative_rows),
        "negatives_left_ledger_at_zero": (before.get("reservations") == 0
                                          and before.get("attempts") == 0
                                          and fake["negatives"] in {0, None}),
        "positive_accounted": (positive_row.get("terminal") == "finish"
                               and after_positive.get("reservations") == 1
                               and after_positive.get("claims") == 1
                               and after_positive.get("attempts") == 1
                               and fake["positive"] == 1),
        "over_quota_denied_zero_send": (quota_row.get("terminal") == "error"
                                        and quota_row.get("error_code") == "BUDGET_DENIED"
                                        and after_quota == after_positive
                                        and fake["quota"] == fake["positive"]),
    }
    return {"negative_cases": negative_rows,
            "ledger_counts": ledger["negatives"].get("counts"),
            "counts_after_positive": after_positive,
            "counts_after_quota": after_quota,
            "fake_counter": fake,
            "verdict": verdict,
            "ok": all(verdict.values())}


def _remove_container(name: str) -> None:
    podman(["rm", "-f", name], timeout=120)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stage = Path(args.stage)
    if os.geteuid() != 0:
        sys.stderr.write("G4B_RUN_NEEDS_HOST_ROOT\n")
        return lib.EXIT_ENVIRONMENT
    status = lib.git_optional("status", "--porcelain=v1", "-uall") or ""
    report: dict = {"schema": "m0.g4b.run.v1", "utc": lib.utc_now(),
                    "stage": str(stage), "head": lib.git_head(),
                    "worktree_clean": not status.strip(),
                    "containers_before": containers_all()}
    if status.strip():
        report["refused"] = ("worktree must be clean: the frozen G3-D launcher "
                             "preflight rejects unexpected changes")
    elif report["containers_before"]:
        report["refused"] = "containers already present; refusing to start"
    if report.get("refused"):
        lib.write_json_atomic(out_dir / "run.json", report)
        print(json.dumps({"ok": False, "refused": report["refused"]}, sort_keys=True))
        return lib.EXIT_ENVIRONMENT
    if not args.skip_tool:
        report["tool_run"] = tool_run(out_dir, stage, args.tool_timeout)
    if not args.skip_raw_uds:
        report["raw_uds_run"] = raw_uds_run(
            out_dir, stage, keep=bool(args.keep_containers))
    report["containers_after"] = containers_all()
    tool_ok = bool((report.get("tool_run") or {}).get("ledger", {}).get("two_cycle", {})
                   .get("all_ok")) if not args.skip_tool else None
    raw_ok = (report.get("raw_uds_run") or {}).get("judgement", {}).get("ok") \
        if not args.skip_raw_uds else None
    report["summary"] = {
        "tool_launcher_exit": (report.get("tool_run") or {}).get("launcher_exit"),
        "tool_ledger_ok": tool_ok,
        "raw_uds_ok": raw_ok,
        "containers_empty": not report["containers_after"],
        "tool_problems": (report.get("tool_run") or {}).get("ledger", {}).get("problems"),
        "raw_uds_problems": (report.get("raw_uds_run") or {}).get("problems"),
    }
    written = lib.write_json_atomic(out_dir / "run.json", report)
    ok = (report["summary"]["containers_empty"]
          and (tool_ok is not False) and (raw_ok is not False))
    print(json.dumps({"ok": ok, "summary": report["summary"],
                      "file": str(out_dir / "run.json"),
                      "sha256": written["sha256"]}, sort_keys=True))
    return lib.EXIT_OK if ok else lib.EXIT_DRIFT


if __name__ == "__main__":
    raise SystemExit(main())
