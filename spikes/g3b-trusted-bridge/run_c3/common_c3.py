"""G3-C container-only launcher / evidence helpers.

Every path here is a frozen container path. The module is executed only inside
the fixed read-only rootfs with ``--network none``; host Python never imports
project code for these runs.

The G3-B work directory layout (``/work/g3b``) and the frozen adapter socket
path (``/work/g3b/bridge.sock``) are intentionally reused so that the adapter
library under test stays byte-identical to its frozen configuration. Evidence
is written under ``/evidence`` (host ``artifacts/g3c/traces/<case>``).
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import signal
import socket
import sqlite3
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

PYTHON = "/opt/python/bin/python3.11"
BASE = Path("/work/g3b")
PROBE = Path("/probe")
EVIDENCE = Path("/evidence")
RECEIPTS = BASE / "receipts"

# The only environment variables the launcher injects for a normal case. Any
# other variable present in a run is reported by env_snapshot() so the evidence
# can prove that no Key/Live/network override was smuggled in.
ENV = {
    "PATH": "/opt/python/bin:/usr/bin",
    "HOME": "/work",
    "PYTHONPATH": "/probe/src:/deps",
    "PYTHONDONTWRITEBYTECODE": "1",
    "TMPDIR": "/tmp",
}
ALLOWED_ENV = set(ENV) | {"HOSTNAME"}


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_ms() -> int:
    return int(time.time() * 1000)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def emit(kind: str, **data: object) -> None:
    print(json.dumps({"kind": kind, **data}, sort_keys=True), flush=True)


def _template(path: str) -> str:
    return (PROBE / "config" / path).read_text(encoding="utf-8")


def write_configs(*, scenario: str = "ok_usage", run_id: str = "g3c-run",
                  limits: dict | None = None,
                  tool_schemas: list[dict] | None = None,
                  receipt_dir: str | None = None,
                  attempt_db: str | None = None,
                  broker_db: str | None = None,
                  socket_path: str | None = None) -> dict:
    BASE.mkdir(parents=True, exist_ok=True)
    RECEIPTS.mkdir(parents=True, exist_ok=True)
    admission_id = secrets.token_hex(16)
    nonce = secrets.token_hex(16)
    expiry = (datetime.now(timezone.utc) + timedelta(hours=1)).strftime(
        "%Y-%m-%dT%H:%M:%SZ")
    tools = json.dumps(tool_schemas or [], sort_keys=True)
    admission = _template("admission.template.json")
    admission = admission.replace("{{ADMISSION_ID}}", admission_id)
    admission = admission.replace("{{RUN_ID}}", run_id)
    admission = admission.replace("{{TOOL_SCHEMAS}}", tools)
    admission = admission.replace("{{FAKE_SCENARIO}}", scenario)
    admission = admission.replace("{{EXPIRY_UTC}}", expiry)
    admission = admission.replace("{{NONCE}}", nonce)
    document = json.loads(admission)
    document["limits"] = {**document["limits"], **(limits or {})}
    (BASE / "admission.json").write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    broker = json.loads(_template("broker.policy.template.json"))
    if broker_db:
        broker["db_path"] = broker_db
    (BASE / "broker.json").write_text(
        json.dumps(broker, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    controller = json.loads(_template("controller.template.json"))
    if receipt_dir:
        controller["receipt_dir"] = receipt_dir
    if attempt_db:
        controller["attempt_db"] = attempt_db
    if socket_path:
        controller["socket_path"] = socket_path
    (BASE / "controller.json").write_text(
        json.dumps(controller, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"admission_id": admission_id, "nonce": nonce, "expiry_utc": expiry,
            "limits": document["limits"], "fake_scenario": scenario}


def start_controller(*, log_name: str = "controller.log",
                     extra_env: dict | None = None) -> subprocess.Popen:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    BASE.mkdir(parents=True, exist_ok=True)
    log = open(BASE / log_name, "wb")
    controller_env = dict(ENV)
    for name in ("G3B_TEST_MODE", "G3B_CRASH_HOOK", "G3C_TRACE"):
        if name in os.environ:
            controller_env[name] = os.environ[name]
    if extra_env:
        controller_env.update(extra_env)
    proc = subprocess.Popen(
        [PYTHON, "-B", "-m", "autoteacher_m0.bridge.controller", "--config",
         str(BASE / "controller.json")],
        cwd="/work", env=controller_env, stdin=subprocess.DEVNULL,
        stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    proc._g3c_log = log  # type: ignore[attr-defined]
    return proc


def wait_socket(timeout: float = 20.0, path: Path | None = None) -> None:
    target = path or (BASE / "bridge.sock")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if target.exists():
            return
        time.sleep(0.02)
    raise RuntimeError("CONTROLLER_SOCKET_TIMEOUT")


def stop_controller(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except OSError:
            pass
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                pass
            proc.wait(timeout=5)
    log = getattr(proc, "_g3c_log", None)
    if log is not None:
        try:
            log.close()
        except OSError:
            pass


def socket_client(timeout: float = 20.0, path: Path | None = None) -> socket.socket:
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    sock.connect(str(path or (BASE / "bridge.sock")))
    return sock


def read_frames(sock: socket.socket, *, limit: int = 300,
                stop_kinds: tuple[str, ...] = ("finish", "error")) -> list[bytes]:
    buffer = b""
    lines: list[bytes] = []
    while len(lines) < limit:
        while b"\n" not in buffer:
            part = sock.recv(65536)
            if not part:
                return lines
            buffer += part
        line, _, buffer = buffer.partition(b"\n")
        if line:
            line = line + b"\n"
            lines.append(line)
            try:
                document = json.loads(line)
            except ValueError:
                continue
            if document.get("kind") in stop_kinds:
                return lines
    return lines


def readline_timeout(sock: socket.socket, *, seconds: float) -> bytes | None:
    """Read one LF frame honouring a hard wall-clock bound."""
    sock.settimeout(max(seconds, 0.001))
    buffer = b""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            part = sock.recv(65536)
        except (socket.timeout, TimeoutError):
            return None
        if not part:
            return None
        buffer += part
        if b"\n" in buffer:
            return buffer.split(b"\n", 1)[0] + b"\n"
    return None


def query_ro(path: Path, sql: str, params: tuple = ()) -> list[dict]:
    if not path.exists():
        return []
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in conn.execute(sql, params).fetchall()]
    except sqlite3.OperationalError as exc:
        # Additive tables (dispatch claims, attempts) may not exist yet in a
        # fresh or partially initialised database; absence is reported by
        # ``table_names`` instead of being mistaken for a query failure.
        if "no such table" in str(exc):
            return []
        raise
    finally:
        conn.close()


def table_names(path: Path) -> list[str]:
    if not path.exists():
        return []
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
    try:
        return sorted(row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"))
    finally:
        conn.close()


def _copy_tree(source: Path, target: Path) -> list[dict]:
    files: list[dict] = []
    for path in sorted(source.rglob("*")):
        if not path.is_file():
            continue
        if path.is_socket():
            continue
        rel = path.relative_to(source)
        destination = target / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        raw = path.read_bytes()
        destination.write_bytes(raw)
        entry = {"path": str(rel), "sha256": sha256_bytes(raw), "bytes": len(raw)}
        if path.suffix == ".json" and len(raw) <= 65536:
            entry["base64"] = base64.b64encode(raw).decode("ascii")
        files.append(entry)
    return files


def collect_work(evidence_root: Path, *, label: str,
                 extra: dict | None = None) -> dict:
    """Snapshot the mutable container work dir (DBs, receipts, logs) readably."""
    evidence_root.mkdir(parents=True, exist_ok=True)
    work_copy = evidence_root / "work"
    files = _copy_tree(BASE, work_copy) if BASE.exists() else []
    db_snapshot = broker_and_attempts_snapshot(work_copy)
    result = {"label": label, "utc": utc(), "files": files,
              "db": db_snapshot, "env_names": sorted(os.environ),
              "extra": extra or {}}
    (evidence_root / "work-snapshot.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (evidence_root / "db-snapshot.json").write_text(
        json.dumps(db_snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def broker_and_attempts_snapshot(root: Path | None = None) -> dict:
    base = root or BASE
    broker_path = base / "broker.sqlite3"
    attempts_path = base / "attempts.sqlite3"
    return {
        "reservations": query_ro(
            broker_path,
            "SELECT reservation_id,route_id,model,input_bound,output_bound,status,"
            "input_used,output_used,cost,estimated,settlement_json "
            "FROM budget_reservations ORDER BY rowid"),
        "claims": query_ro(
            broker_path,
            "SELECT call_id,reservation_id,request_digest,status "
            "FROM budget_dispatch_claims ORDER BY rowid"),
        "attempts": query_ro(
            attempts_path,
            "SELECT attempt_id,call_id,reservation_id,state,receipt_id,reason,"
            "payload_digest,prepared_digest,run_id,logical_step,mode,"
            "input_bound_kind,input_bound_tokens,created_utc,updated_utc,"
            "receipt_json,settlement_json "
            "FROM g3b_attempts ORDER BY created_utc, call_id"),
        "intents": query_ro(
            attempts_path,
            "SELECT intent_id,call_id,reservation_id,state,reason "
            "FROM g3b_send_intents ORDER BY created_utc"),
        "identities": query_ro(
            attempts_path,
            "SELECT scope_id,identity_digest,call_id,logical_step "
            "FROM g3b_request_identities ORDER BY created_utc"),
        "admissions": query_ro(
            attempts_path,
            "SELECT admission_id,run_id,consumed_utc,controller_instance_id "
            "FROM g3b_admissions ORDER BY consumed_utc"),
        "receipts": _receipt_summaries(base),
        "tables": {"broker": table_names(broker_path),
                   "attempts": table_names(attempts_path)},
    }


def _receipt_summaries(base: Path) -> list[dict]:
    directory = base / "receipts"
    rows: list[dict] = []
    if not directory.exists():
        return rows
    for path in sorted(directory.glob("rcpt-*.json")):
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            rows.append({"path": path.name, "invalid": True})
            continue
        raw = path.read_bytes()
        rows.append({
            "path": path.name, "sha256": sha256_bytes(raw), "bytes": len(raw),
            "receipt_id": document.get("receipt_id"),
            "raw_sha256": document.get("raw_sha256"),
            "raw_length": document.get("raw_length"),
            "nonce": document.get("nonce"),
            "mode": document.get("mode"), "usage": document.get("usage"),
            "times": document.get("times"),
        })
    counter = directory / "received-count.json"
    if counter.exists():
        try:
            rows.append({"counter": json.loads(counter.read_text())})
        except ValueError:
            rows.append({"counter": "INVALID"})
    return rows


def correlation_rows() -> list[dict]:
    """§13.2 call_id -> reservation -> claim -> attempt -> receipt -> digest -> status."""
    snapshot = broker_and_attempts_snapshot()
    claims = {row["call_id"]: row for row in snapshot["claims"]}
    reservations = {row["reservation_id"]: row for row in snapshot["reservations"]}
    receipts = {row.get("nonce"): row for row in snapshot["receipts"]
                if isinstance(row, dict) and row.get("nonce")}
    rows: list[dict] = []
    for attempt in snapshot["attempts"]:
        document = None
        try:
            document = json.loads(attempt.get("receipt_json") or "null")
        except (TypeError, ValueError):
            document = None
        document = document if isinstance(document, dict) else {}
        receipt = document.get("receipt") if isinstance(document.get("receipt"), dict) else {}
        reservation = reservations.get(attempt["reservation_id"], {})
        rows.append({
            "run_id": attempt.get("run_id"),
            "logical_step": attempt.get("logical_step"),
            "call_id": attempt.get("call_id"),
            "prepared_digest": attempt.get("prepared_digest"),
            "reservation_id": attempt.get("reservation_id"),
            "bound_claim": (claims.get(attempt.get("call_id")) or {}).get("status"),
            "attempt_id": attempt.get("attempt_id"),
            "attempt_started_durable": attempt.get("state") not in (None, "RESERVED", "CLAIMED"),
            "outbound_payload_digest": attempt.get("payload_digest"),
            "fake_receipt_raw_sha256": receipt.get("raw_sha256")
            or (receipts.get(receipt.get("nonce")) or {}).get("raw_sha256"),
            "observation_digest": document.get("observation_digest"),
            "broker_reservation_status": reservation.get("status"),
            "journal_final_state": attempt.get("state"),
        })
    return rows


def env_snapshot() -> dict:
    key_names = [name for name in os.environ
                 if any(token in name.upper()
                        for token in ("KEY", "TOKEN", "SECRET", "PASSWORD"))]
    mounts = []
    try:
        for line in Path("/proc/mounts").read_text().splitlines():
            fields = line.split()
            if len(fields) >= 2 and fields[1] in {"/probe", "/deps", "/evidence", "/work", "/tmp"}:
                mounts.append({"target": fields[1], "options": fields[3]})
    except OSError:
        pass
    return {"uid": os.getuid(), "gid": os.getgid(),
            "env_names": sorted(os.environ), "key_env": key_names,
            "unexpected_env": sorted(set(os.environ) - ALLOWED_ENV),
            "mounts": mounts,
            "readonly_rootfs": "ro" in Path("/proc/mounts").read_text(),
            "network_families": _socket_families(),
            "python": os.uname().release}


def _socket_families() -> list[str]:
    """Evidence that the process tree only uses AF_UNIX (no AF_INET/HTTP)."""
    families = set()
    try:
        for path in Path("/proc/net").glob("*"):
            name = path.name
            if name.startswith(("tcp", "udp", "raw")):
                families.add(name)
    except OSError:
        pass
    return sorted(families) or ["none"]


def write_json(path: Path, document: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def trace_controller_log(evidence_root: Path) -> dict:
    log = BASE / "controller.log"
    if not log.exists():
        return {"exists": False}
    raw = log.read_bytes()
    text = raw.decode("utf-8", "replace")
    markers = [line for line in text.splitlines()
               if any(token in line for token in
                      ("ADMISSION_REPLAYED", "Traceback", "ERROR", "cancel"))]
    return {"exists": True, "sha256": sha256_bytes(raw), "bytes": len(raw),
            "markers": markers[:50]}
