#!/usr/bin/env python3
"""G4-F4 real DSH session resume under the G4 dual-principal stage (no-key).

This runner does **not** modify the G3-C/G3-D scripts, the product source, the
trusted entrypoint or the ledger semantics.  It imports the reviewed G4-C
launcher and drives two real Candidate containers against one live Trusted
Controller:

``resume`` (positive)
    turn 1: a real DSH ``start_session`` Echo request; the DSH session tree and
    the provider request are persisted by the real DSH process.
    turn 2: a *new* Candidate container resumes the same session with
    ``resume_session`` and issues a second prompt.

``crash-resume`` (negative)
    turn 1: the product test-only crash hook ``after_attempt_start_before_fake_send``
    leaves one durable Attempt ``SETTLEMENT_UNCERTAIN`` and a PENDING
    Reservation, then a real recovery Controller starts against the same state
    (``ADMISSION_REPLAYED``).
    turn 2: a new Candidate resumes the same DSH session while no serving
    Controller exists; no provider request may be sent and the ledger must stay
    conservative.

Every phase gets its own argv/UTC/exit/identity/mountinfo/socket/peercred/DSH
trace/session snapshot/DB copy/receipts/Fake counter under
``artifacts/g4f/f4``.  The Host runner never trusts the Candidate or the
Controller's own check summary: it re-queries the SQLite files and re-reads the
DSH session JSONL.

No Key, no model, no external network, ``--network none`` throughout.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets
import sqlite3
import subprocess
import sys
from decimal import Decimal, InvalidOperation
from typing import Mapping, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "g3d"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib_g3d as lib3d  # noqa: E402
import lib_g4 as lib  # noqa: E402
import lib_g4c as libc  # noqa: E402
from launch_c import G4CLauncher  # noqa: E402

F4_ROOT = lib.ARTIFACTS / "g4f" / "f4"
PHASES = ("resume", "crash-resume")
CRASH_HOOK = "after_attempt_start_before_fake_send"
SESSION_ID = "g4f-f4-s1"


def utc() -> str:
    return lib3d.utc()


def sha256_file(path: str | os.PathLike[str]) -> str:
    return libc.sha256_file(path)


def json_bytes(document: object) -> bytes:
    return lib3d.json_bytes(document)


def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _safe_query(path: Path, statement: str) -> list[dict]:
    if not path.is_file():
        return []
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
    except sqlite3.Error:
        return []
    try:
        return [dict(row) for row in connection.execute(statement).fetchall()]
    except sqlite3.Error:
        return []
    finally:
        connection.close()


def containers() -> list[str]:
    proc = subprocess.run(["podman", "ps", "-a", "--format", "{{.Names}}"],
                          capture_output=True, text=True, timeout=60)
    return [line for line in proc.stdout.splitlines() if line.strip()]


def _decimal(value: object) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _parse_json_text(value: object) -> dict | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _jsonable(value: object) -> object:
    """Recursively make check details JSON-safe (sets are audit-only)."""
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted((_jsonable(item) for item in value),
                      key=lambda item: json.dumps(item, sort_keys=True, default=str))
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (Path, bytes)):
        return str(value) if isinstance(value, Path) else value.hex()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


# ---------------------------------------------------------------------------
# launcher
# ---------------------------------------------------------------------------
class F4Launcher(G4CLauncher):
    """One F4 phase: ``resume`` or ``crash-resume``."""

    def __init__(self, args: argparse.Namespace) -> None:
        super().__init__(args)
        self.f4_kind: str = args.f4_kind
        self.phase_records: dict[str, dict] = {}
        self.phase_containers: list[str] = []
        self.phase_checks: list[dict] = []
        self.nonce = secrets.token_hex(8)
        self.prompts = {
            "turn1": f"G4F_F4_ALPHA nonce-{self.nonce} remember this token",
            "turn2": "G4F_F4_BETA what nonce did I ask you to remember?",
        }
        self.reconciliation: dict = {}

    # -- evidence helpers ------------------------------------------------
    def write_evidence_json(self, relative: str, document: object, *,
                            mode: int = 0o444) -> dict:
        return super().write_evidence_json(relative, _jsonable(document), mode=mode)

    def _phase_dir(self, key: str) -> Path:
        path = self.evidence / "phases" / key
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _phase_write(self, key: str, name: str, document: object) -> dict:
        return self.write_evidence_json(f"phases/{key}/{name}", document)

    # -- phase runner ----------------------------------------------------
    def start_candidate(self) -> None:
        if self.f4_kind == "resume":
            self._run_phase("turn1", "echo", self.prompts["turn1"], "turn1")
            self._snapshot_phase("turn1")
            self._run_phase("turn2", "resume", self.prompts["turn2"], "turn2")
            self._snapshot_phase("turn2")
            return
        self._run_phase("turn1", "echo", self.prompts["turn1"], "turn1")
        self._snapshot_phase("turn1")
        self.restart_trusted(reason="f4-crash-resume")
        self._run_phase("turn2", "resume", self.prompts["turn2"], "turn2")
        self._snapshot_phase("turn2")

    def _run_phase(self, key: str, scenario: str, prompt: str,
                   label: str) -> dict:
        name = f"{self.candidate_name}-{key}"
        self.phase_containers.append(name)
        self.cmd(["podman", "rm", "-f", name], name=f"rm-stale-candidate-{key}",
                 timeout=60)
        argv = lib3d.candidate_run_argv(
            podman="podman", rootfs=str(lib3d.ROOTFS),
            stage_candidate=str(self.stage_dir / "candidate"), deps=str(lib3d.DEPS),
            run_dir=str(self.run_dir), name=name, scenario=scenario,
            session=self.args.session, prompt=prompt, mode="dsh",
            label=label, timeout_s=int(self.args.timeout))
        problems = lib3d.argv_contract_problems(
            argv, role="candidate", run_dir=str(self.run_dir),
            stage_dir=str(self.stage_dir / "candidate"))
        if problems:
            self.fail(lib3d.EXIT_STAGE_INVALID, "F4 candidate argv invalid",
                      problems=problems)
        self._write_argv(f"candidate-{key}", argv)
        self._phase_write(key, "argv.json", {
            "argv": argv, "scenario": scenario, "session": self.args.session,
            "label": label, "prompt_sha256": libc.sha256_bytes(prompt.encode()),
            "prompt": prompt, "resume": scenario == "resume"})
        started = utc()
        run = self.cmd(argv, name=f"podman-run-candidate-{key}", timeout=90)
        record: dict = {
            "key": key, "scenario": scenario, "label": label,
            "container": name, "argv": argv, "utc_start": started,
            "podman_run_exit": run["exit"],
            "podman_run_stderr": (run["stderr"] or "")[-2000:],
        }
        document = self.podman_inspect(name, label=f"inspect-candidate-{key}")
        if document is None:
            record["state"] = "inspect_failed"
            record["utc_end"] = utc()
            self.phase_records[key] = record
            self.records.setdefault("candidate_phases", {})[key] = record
            self.fail(lib3d.EXIT_CANDIDATE_START_FAILED,
                      f"F4 {key} candidate inspect failed")
        pid = int(document["State"].get("Pid") or 0)
        identity = None
        if pid > 0:
            identity = self._capture_identity(pid, f"candidate-{key}")
            self.runtime_identity[f"candidate-{key}"] = identity
            self._phase_write(key, "identity.json", identity)
            (self._phase_dir(key) / "uid-map.txt").write_text(
                identity.get("uid_map") or "", encoding="utf-8")
            (self._phase_dir(key) / "mountinfo.txt").write_text(
                identity.get("mountinfo") or "", encoding="utf-8")
        socket_before = lib3d.lstat_record(self.run_dir / "ipc" / "bridge.sock")
        self.write_evidence_json(f"socket-stat/{key}-before.json", socket_before)
        status = document["State"]["Status"]
        wait_timed_out = False
        if status == "running":
            wait = self.cmd(["podman", "wait", "--interval", "200ms", name],
                            name=f"podman-wait-candidate-{key}",
                            timeout=float(self.args.timeout))
            wait_timed_out = bool(wait["timed_out"])
            if wait_timed_out:
                self.record_error("CANDIDATE_TIMEOUT", f"F4 {key} candidate timeout",
                                  timeout=self.args.timeout)
                self.cmd(["podman", "kill", "-s", "KILL", name],
                         name=f"kill-candidate-{key}", timeout=30)
                self.cmd(["podman", "wait", "--interval", "200ms", name],
                         name=f"podman-wait-candidate-killed-{key}", timeout=30)
        final = self.podman_inspect(name, label=f"inspect-candidate-final-{key}")
        exit_code = None
        if final is not None:
            exit_code = int(final["State"].get("ExitCode", -1))
            record["container_status"] = final["State"].get("Status")
            record["container_started_at"] = final["State"].get("StartedAt")
            record["container_finished_at"] = final["State"].get("FinishedAt")
            record["network_mode"] = (final.get("HostConfig") or {}).get(
                "NetworkMode")
            record["read_only"] = (final.get("HostConfig") or {}).get(
                "ReadonlyRootfs")
            record["uid_maps"] = (final.get("HostConfig") or {}).get("IDMappings")
            self.write_evidence_json(
                f"run/inspect-candidate-final-{key}.json", final)
        record["exit_code"] = exit_code
        record["timeout"] = wait_timed_out
        logs = self._container_logs(name, f"candidate-log-{key}")
        lib3d.write_bytes_atomic(self.evidence / "run" / f"candidate-{key}.log",
                                 logs.encode(), mode=0o444)
        lib3d.write_bytes_atomic(self._phase_dir(key) / "candidate.log",
                                 logs.encode(), mode=0o444)
        self._copy_candidate_evidence()
        record["socket_after"] = lib3d.lstat_record(
            self.run_dir / "ipc" / "bridge.sock")
        self.write_evidence_json(f"socket-stat/{key}-after.json",
                                 record["socket_after"])
        record["utc_end"] = utc()
        self.phase_records[key] = record
        self.records.setdefault("candidate_phases", {})[key] = record
        self.records["candidate_exit_code"] = exit_code
        self.records["candidate_utc_end"] = record["utc_end"]
        self._phase_write(key, "phase.json", record)
        remove = self.cmd(["podman", "rm", "-f", name],
                          name=f"rm-candidate-{key}", timeout=60)
        record["removed"] = remove["exit"] == 0
        return record

    # -- phase snapshot --------------------------------------------------
    def _snapshot_phase(self, key: str) -> dict:
        phase_dir = self._phase_dir(key)
        ledger = self._live_ledger()
        self._phase_write(key, "db-query.json", ledger)
        backups = {}
        for source_name in ("broker.sqlite3", "attempts.sqlite3"):
            source = self.run_dir / "state" / source_name
            target = phase_dir / "db" / source_name
            backup = self._backup_sqlite(source, target)
            if backup is not None:
                backups[source_name] = backup
            for suffix in ("", "-wal", "-shm"):
                raw = source.with_name(source.name + suffix)
                if raw.is_file():
                    data = lib3d.read_regular_bytes(raw, max_bytes=128 << 20)
                    lib3d.write_bytes_atomic(
                        phase_dir / "db" / raw.name, data, mode=0o444)
        receipts = self._copy_receipts(phase_dir)
        session = self._session_snapshot(phase_dir)
        trace = self._trace_snapshot(key, phase_dir)
        peercred = self._peercred_snapshot(key, phase_dir)
        phase = self.phase_records.get(key) or {}
        summary = {
            "key": key,
            "utc_snapshot": utc(),
            "phase": phase,
            "counts": {
                "reservations": len(ledger["reservations"]),
                "claims": len(ledger["claims"]),
                "attempts": len(ledger["attempts"]),
                "intents": len(ledger["intents"]),
                "messages": len(ledger["messages"]),
                "receipts": len(ledger["receipts"]),
                "fake_counter": ledger["fake_counter"],
            },
            "totals": ledger["totals"],
            "db_backups": backups,
            "receipts": receipts,
            "session": session,
            "trace": trace,
            "peercred": peercred,
            "socket": {
                "before": phase.get("socket_before"),
                "after": phase.get("socket_after"),
                "after_snapshot": lib3d.lstat_record(
                    self.run_dir / "ipc" / "bridge.sock"),
            },
        }
        self._phase_write(key, "phase-summary.json", summary)
        return summary

    def _backup_sqlite(self, source: Path, target: Path) -> dict | None:
        if not source.is_file():
            return None
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            target.unlink()
        try:
            src = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
        except sqlite3.Error:
            return None
        try:
            dst = sqlite3.connect(str(target))
            try:
                src.backup(dst)
            finally:
                dst.close()
        except sqlite3.Error:
            return None
        finally:
            src.close()
        os.chmod(target, 0o444)
        return {"path": target.name, "sha256": sha256_file(target),
                "bytes": target.stat().st_size}

    def _copy_receipts(self, phase_dir: Path) -> dict:
        source = self.run_dir / "state" / "receipts"
        target = phase_dir / "receipt"
        target.mkdir(parents=True, exist_ok=True)
        rows = []
        if source.is_dir():
            for path in sorted(source.iterdir(), key=lambda item: item.name):
                record = lib3d.lstat_record(path)
                if record is None or record.get("type") != "regular":
                    rows.append({"name": path.name, "rejected": True})
                    continue
                data = lib3d.read_regular_bytes(path, max_bytes=4 << 20)
                lib3d.write_bytes_atomic(target / path.name, data, mode=0o444)
                rows.append({"name": path.name, "bytes": len(data),
                             "sha256": libc.sha256_bytes(data)})
        return {"files": rows, "count": sum(
            1 for row in rows if row.get("name", "").startswith("rcpt-"))}

    def _live_ledger(self) -> dict:
        broker = self.run_dir / "state" / "broker.sqlite3"
        attempts = self.run_dir / "state" / "attempts.sqlite3"
        ledger: dict = {
            "reservations": _safe_query(
                broker,
                "SELECT reservation_id,route_id,model,input_bound,output_bound,"
                "status,input_used,output_used,cost,estimated,settlement_json "
                "FROM budget_reservations ORDER BY rowid"),
            "claims": _safe_query(
                broker,
                "SELECT call_id,reservation_id,request_digest,status "
                "FROM budget_dispatch_claims ORDER BY rowid"),
            "call_links": _safe_query(
                broker,
                "SELECT call_id,reservation_id FROM budget_call_links ORDER BY rowid"),
            "messages": _safe_query(
                broker,
                "SELECT message_id,response_json FROM budget_broker_messages "
                "ORDER BY rowid"),
            "observations": _safe_query(
                broker,
                "SELECT * FROM budget_provider_observations ORDER BY rowid"),
            "scopes": _safe_query(
                broker, "SELECT scope_id,blocked FROM budget_scopes ORDER BY rowid"),
            "attempts": _safe_query(
                attempts,
                "SELECT attempt_id,call_id,reservation_id,state,receipt_id,reason,"
                "payload_digest,prepared_digest,run_id,logical_step,input_bound_tokens,"
                "created_utc,updated_utc,settlement_json FROM g3b_attempts "
                "ORDER BY created_utc, call_id"),
            "admissions": _safe_query(
                attempts,
                "SELECT admission_id,run_id,consumed_utc FROM g3b_admissions "
                "ORDER BY consumed_utc"),
            "intents": _safe_query(
                attempts,
                "SELECT intent_id,call_id,reservation_id,state,reason "
                "FROM g3b_send_intents ORDER BY created_utc"),
            "identities": _safe_query(
                attempts,
                "SELECT scope_id,identity_digest,call_id,logical_step "
                "FROM g3b_request_identities ORDER BY created_utc"),
        }
        ledger["receipts"] = self._receipt_rows()
        ledger["fake_counter"] = self._fake_counter()
        ledger["integrity"] = {
            "broker": _safe_query(broker, "PRAGMA integrity_check"),
            "attempts": _safe_query(attempts, "PRAGMA integrity_check"),
        }
        ledger["totals"] = self._totals(ledger["reservations"])
        return ledger

    def _receipt_rows(self) -> list[dict]:
        folder = self.run_dir / "state" / "receipts"
        rows: list[dict] = []
        if not folder.is_dir():
            return rows
        for path in sorted(folder.glob("rcpt-*.json")):
            document = _read_json(path)
            if document is None:
                rows.append({"name": path.name, "invalid": True})
                continue
            rows.append({
                "name": path.name, "sha256": sha256_file(path),
                "receipt_id": document.get("receipt_id"),
                "raw_sha256": document.get("raw_sha256"),
                "raw_length": document.get("raw_length"),
                "nonce": document.get("nonce"), "mode": document.get("mode"),
                "usage": document.get("usage"),
                "utc_start": document.get("utc_start"),
                "utc_end": document.get("utc_end"),
                "synthetic": document.get("synthetic"),
                "real_model_calls": document.get("real_model_calls"),
                "http_calls": document.get("http_calls"),
                "network_used": document.get("network_used"),
            })
        return rows

    def _fake_counter(self) -> int | None:
        counter = self.run_dir / "state" / "receipts" / "received-count.json"
        if not counter.is_file():
            return 0 if not list(
                (self.run_dir / "state" / "receipts").glob("rcpt-*.json")) else None
        document = _read_json(counter)
        return None if document is None else document.get("count")

    @staticmethod
    def _totals(reservations: Sequence[Mapping[str, object]]) -> dict:
        committed = Decimal(0)
        reserved = Decimal(0)
        pending = 0
        costs = {}
        for row in reservations:
            cost = _decimal(row.get("cost"))
            if cost is None:
                continue
            committed += cost
            costs[str(row.get("reservation_id"))] = format(cost, "f")
            if row.get("status") == "PENDING":
                reserved += cost
                pending += 1
        return {
            "requests": len(reservations),
            "pending": pending,
            "committed_usd": format(committed, "f"),
            "reserved_usd": format(reserved, "f"),
            "spent_usd": format(committed - reserved, "f"),
            "costs": costs,
        }

    # -- session/trace snapshots ----------------------------------------
    def _session_snapshot(self, phase_dir: Path) -> dict:
        root = self.run_dir / "candidate-session" / "dsh-home" / "sessions"
        files: list[dict] = []
        if root.is_dir():
            for path in sorted(root.rglob("session.v4.jsonl")):
                if path.is_symlink() or not path.is_file():
                    continue
                data = lib3d.read_regular_bytes(path, max_bytes=32 << 20)
                relative = path.relative_to(root).as_posix()
                target = phase_dir / "session" / relative
                lib3d.write_bytes_atomic(target, data, mode=0o444)
                parsed = self._parse_session(data)
                files.append({
                    "path": relative, "bytes": len(data),
                    "sha256": libc.sha256_bytes(data),
                    "lines": data.count(b"\n"), **parsed})
        summary = {
            "root": str(root), "exists": root.is_dir(), "files": files,
            "total_lines": sum(item["lines"] for item in files),
            "resume_markers": sum(item["resume_markers"] for item in files),
            "request_headers": [header for item in files
                                for header in item["request_headers"]],
            "assistant_messages": [message for item in files
                                   for message in item["assistant_messages"]],
            "user_messages": [message for item in files
                              for message in item["user_messages"]],
        }
        self._phase_write(phase_dir.name, "session.json", summary)
        return summary

    @staticmethod
    def _parse_session(data: bytes) -> dict:
        headers: list[dict] = []
        assistants: list[dict] = []
        users: list[dict] = []
        turns: list[dict] = []
        event_types: dict[str, int] = {}
        for line in data.splitlines():
            try:
                event = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if not isinstance(event, dict):
                continue
            kind = event.get("type")
            if isinstance(kind, str):
                event_types[kind] = event_types.get(kind, 0) + 1
            payload = event.get("data") if isinstance(event.get("data"), dict) else {}
            if kind == "request/header":
                headers.append({"seq": event.get("seq"),
                                "reason": payload.get("reason")})
            elif kind == "turn/start":
                turns.append({"turn": payload.get("turn"), "start_seq": event.get("seq")})
            elif kind == "turn/end":
                turns.append({"turn": payload.get("turn"), "end_seq": event.get("seq"),
                              "reason": payload.get("reason")})
            elif kind == "assistant/message":
                message = payload.get("message") if isinstance(
                    payload.get("message"), dict) else {}
                assistants.append({
                    "seq": event.get("seq"), "turn": payload.get("turn"),
                    "step": payload.get("step"),
                    "usage": payload.get("usage"),
                    "content_types": sorted({block.get("type") for block in
                                             message.get("content") or []
                                             if isinstance(block, dict)}),
                })
            elif kind == "user/message":
                content = payload.get("content") or []
                texts = [block.get("text") for block in content
                         if isinstance(block, dict) and isinstance(block.get("text"), str)]
                users.append({
                    "seq": event.get("seq"),
                    "source": (payload.get("source") or {}).get("kind"),
                    "text": " ".join(texts)[:200],
                    "text_sha256": libc.sha256_bytes(" ".join(texts).encode()),
                })
        return {
            "request_headers": headers,
            "assistant_messages": assistants,
            "user_messages": users,
            "turns": turns,
            "resume_markers": sum(1 for header in headers
                                  if header.get("reason") == "resume"),
            "event_types": event_types,
        }

    def _trace_snapshot(self, key: str, phase_dir: Path) -> dict:
        label = (self.phase_records.get(key) or {}).get("label") or key
        source = (self.run_dir / "candidate-session" / "evidence" /
                  f"dsh-result-{label}.json")
        document = _read_json(source)
        if document is None:
            return {"present": False, "path": str(source)}
        lib3d.write_bytes_atomic(phase_dir / "dsh-result.json",
                                 source.read_bytes(), mode=0o444)
        principal = (self.run_dir / "candidate-session" / "evidence" /
                     f"principal-{label}.json")
        if principal.is_file():
            lib3d.write_bytes_atomic(phase_dir / "principal.json",
                                     principal.read_bytes(), mode=0o444)
        events = document.get("events") or []
        return {
            "present": True,
            "path": str(source),
            "final_response": document.get("final_response"),
            "finish_reason": document.get("finish_reason"),
            "error": document.get("error"),
            "session_id": document.get("session_id"),
            "event_count": document.get("event_count"),
            "event_types": sorted({str(event.get("type")) for event in events
                                   if isinstance(event, dict)}),
            "event_summary": document.get("event_summary"),
            "resume": document.get("resume"),
            "notifications": len(document.get("notifications_trace") or []),
        }

    def _peercred_snapshot(self, key: str, phase_dir: Path) -> dict:
        logs = self._container_logs(self.trusted_name, f"trusted-log-{key}")
        accepted = [line for line in logs.splitlines()
                    if "bridge peer accepted" in line]
        denied = [line for line in logs.splitlines()
                  if "bridge peer rejected" in line]
        document = {
            "accepted_count": len(accepted),
            "denied_count": len(denied),
            "accepted_uid_65534": any("uid=65534" in line for line in accepted),
            "accepted_gid_65534": any("gid=65534" in line for line in accepted),
            "accepted_lines": accepted[-10:],
            "denied_lines": denied[-10:],
        }
        self._phase_write(key, "peercred.json", document)
        return document

    # -- evaluation ------------------------------------------------------
    def evaluate(self) -> None:
        if self.f4_kind == "resume":
            self._evaluate_resume()
        else:
            self._evaluate_crash_resume()
        self.checks = self.phase_checks
        self.write_evidence_json("checks/checks.json", {"checks": self.checks})
        if not all(item["ok"] for item in self.checks):
            if self.exit_code == lib3d.EXIT_OK:
                self.exit_code = lib3d.EXIT_CASE_FAILED
            self.failure = {"reason": "CHECK_FAILED",
                            "message": "one or more G4-F4 checks failed",
                            "detail": {"failed": [item["id"] for item in self.checks
                                                  if not item["ok"]]}}

    def _check(self, check_id: str, ok: bool, **detail: object) -> None:
        self.phase_checks.append({"id": check_id, "ok": bool(ok), **detail})

    def _final(self) -> tuple[dict, dict]:
        snapshot = self._ledger_snapshot()
        broker = self.evidence / "db" / "broker.sqlite3"
        extra = {
            "messages": _safe_query(
                broker,
                "SELECT message_id,response_json FROM budget_broker_messages "
                "ORDER BY rowid"),
            "scopes": _safe_query(
                broker, "SELECT scope_id,blocked FROM budget_scopes ORDER BY rowid"),
        }
        return snapshot, extra

    def _phase_doc(self, key: str, name: str) -> dict:
        return self._read_json_evidence(f"phases/{key}/{name}") or {}

    def _phase_ledger(self, key: str) -> dict:
        return self._phase_doc(key, "db-query.json")

    def _settlement_rows(self, messages: Sequence[Mapping[str, object]]) -> dict:
        reserves = []
        settles = []
        failed = []
        for row in messages:
            document = _parse_json_text(row.get("response_json")) or {}
            code = document.get("code")
            item = {"message_id": row.get("message_id"), "code": code,
                    "reservation_id": document.get("reservation_id")}
            if code == "RESERVED":
                reserves.append(item)
            elif code == "SETTLED":
                settles.append(item)
            elif code in {"FAILED", "RELEASED"}:
                failed.append(item)
        return {"reserved": reserves, "settled": settles, "failed": failed}

    def _evaluate_resume(self) -> None:
        snapshot, extra = self._final()
        phase1 = self._phase_ledger("turn1")
        phase2 = self._phase_ledger("turn2")
        p1_summary = self._phase_doc("turn1", "phase-summary.json")
        p2_summary = self._phase_doc("turn2", "phase-summary.json")
        reservations = snapshot["reservations"]
        claims = snapshot["claims"]
        attempts = snapshot["attempts"]
        receipts = snapshot["receipts"]
        counter = snapshot["fake_counter"]
        gate = self._gate_evidence()
        modules = self._modules_evidence()
        t1 = (self.phase_records.get("turn1") or {})
        t2 = (self.phase_records.get("turn2") or {})
        r1 = self._read_json_evidence("traces/dsh-result-turn1.json") or {}
        r2 = self._read_json_evidence("traces/dsh-result-turn2.json") or {}
        session1 = p1_summary.get("session") or {}
        session2 = p2_summary.get("session") or {}
        messages = self._settlement_rows(extra["messages"])

        self._check("modules_loaded_from_g4_head", modules["ok"],
                    problems=modules["problems"])
        self._check("phase1_exit_zero", t1.get("exit_code") == 0,
                    exit=t1.get("exit_code"))
        self._check("phase2_exit_zero", t2.get("exit_code") == 0,
                    exit=t2.get("exit_code"))
        self._check("turn1_echo_finished",
                    r1.get("final_response") == "ok"
                    and r1.get("finish_reason") == "completed"
                    and not r1.get("error"),
                    result={key: r1.get(key) for key in
                            ("final_response", "finish_reason", "error")})
        self._check("turn2_echo_finished",
                    r2.get("final_response") == "ok"
                    and r2.get("finish_reason") == "completed"
                    and not r2.get("error"),
                    result={key: r2.get(key) for key in
                            ("final_response", "finish_reason", "error")})
        resume = r2.get("resume") or {}
        sessions = resume.get("sessions") or {}
        self._check("turn2_used_real_resume",
                    resume.get("used") is True
                    and resume.get("sdk_call") == "resume_session",
                    resume={key: resume.get(key) for key in ("used", "sdk_call")})
        self._check("resume_marker_present",
                    int(sessions.get("resume_marker_count") or 0) >= 1,
                    marker_count=sessions.get("resume_marker_count"))
        self._check("session_grew_across_processes",
                    int(sessions.get("total_lines") or 0)
                    > int(session1.get("total_lines") or 0),
                    turn1_lines=session1.get("total_lines"),
                    turn2_lines=sessions.get("total_lines"))
        self._check("new_candidate_process_per_turn",
                    t1.get("container") != t2.get("container")
                    and t1.get("container") and t2.get("container"),
                    turn1=t1.get("container"), turn2=t2.get("container"))

        counts_ok = (len(reservations) == 2 and len(claims) == 2
                     and len(attempts) == 2 and len(receipts) == 2
                     and counter == 2)
        self._check("two_requests_two_ledger_sets", counts_ok,
                    reservations=len(reservations), claims=len(claims),
                    attempts=len(attempts), receipts=len(receipts),
                    fake_counter=counter)
        self._check("phase1_single_request",
                    len(phase1.get("reservations") or []) == 1
                    and len(phase1.get("claims") or []) == 1
                    and len(phase1.get("attempts") or []) == 1
                    and len(phase1.get("receipts") or []) == 1
                    and phase1.get("fake_counter") == 1,
                    counts=self._counts(phase1))
        self._check("phase2_second_request_only",
                    len(phase2.get("reservations") or []) == 2
                    and len(phase2.get("claims") or []) == 2
                    and len(phase2.get("attempts") or []) == 2
                    and len(phase2.get("receipts") or []) == 2
                    and phase2.get("fake_counter") == 2,
                    counts=self._counts(phase2))

        ordered = sorted((row for row in attempts if isinstance(row, dict)),
                         key=lambda row: int(row.get("logical_step") or 0))
        steps = [int(row.get("logical_step") or 0) for row in ordered]
        self._check("logical_steps_are_zero_one", steps == [0, 1], steps=steps)
        distinct = {
            "call_ids": {row.get("call_id") for row in attempts},
            "attempt_ids": {row.get("attempt_id") for row in attempts},
            "reservation_ids": {row.get("reservation_id") for row in attempts},
            "receipt_ids": {row.get("receipt_id") for row in attempts},
        }
        self._check("distinct_call_and_attempt_ids",
                    all(len(values) == 2 for values in distinct.values()),
                    **{key: sorted(value for value in values if value)
                       for key, values in distinct.items()})

        phase1_attempts = phase1.get("attempts") or []
        old_attempt = phase1_attempts[0] if len(phase1_attempts) == 1 else {}
        new_attempt = ordered[1] if len(ordered) == 2 else {}
        final_old = next((row for row in attempts
                          if row.get("attempt_id") == old_attempt.get("attempt_id")),
                         {})
        old_unchanged = bool(old_attempt) and final_old == old_attempt
        self._check("old_attempt_not_rewritten", old_unchanged,
                    old=old_attempt, final=final_old)
        self._check("resume_uses_new_attempt",
                    bool(old_attempt) and bool(new_attempt)
                    and new_attempt.get("attempt_id") != old_attempt.get("attempt_id")
                    and new_attempt.get("call_id") != old_attempt.get("call_id"),
                    old_call_id=old_attempt.get("call_id"),
                    new_call_id=new_attempt.get("call_id"))
        self._check("old_call_id_not_replayed",
                    sum(1 for row in attempts
                        if row.get("call_id") == old_attempt.get("call_id")) == 1,
                    old_call_id=old_attempt.get("call_id"))
        phase1_receipts = phase1.get("receipts") or []
        phase1_receipt_ids = {row.get("receipt_id") for row in phase1_receipts}
        self._check("old_receipt_not_replaced",
                    len(phase1_receipt_ids) == 1
                    and phase1_receipt_ids.issubset(
                        {row.get("receipt_id") for row in receipts}),
                    old=phase1_receipt_ids,
                    final=sorted(str(row.get("receipt_id")) for row in receipts))
        self._check("no_attempt_rejected_replay",
                    not any("ATTEMPT_ALREADY_STARTED" in line
                            for line in self._trusted_log().splitlines()),
                    trusted_log_lines=len(self._trusted_log().splitlines()))
        self._check("gate_two_authorizations_no_denials",
                    len(gate["authorized"]) == 2 and len(gate["consumed"]) == 2
                    and not gate["denied"],
                    authorized=len(gate["authorized"]),
                    consumed=len(gate["consumed"]),
                    denied=len(gate["denied"]))

        by_call = {row.get("call_id"): row for row in gate["authorized"]}
        gate_pair = [by_call.get(old_attempt.get("call_id")),
                     by_call.get(new_attempt.get("call_id"))]
        auth_ok = all(item is not None for item in gate_pair)
        if auth_ok:
            auth_ok = (gate_pair[0].get("reservation_id")
                       == old_attempt.get("reservation_id")
                       and gate_pair[1].get("reservation_id")
                       == new_attempt.get("reservation_id")
                       and gate_pair[0].get("payload_digest")
                       == old_attempt.get("payload_digest")
                       and gate_pair[1].get("payload_digest")
                       == new_attempt.get("payload_digest"))
        self._check("gate_binds_each_provider_request", auth_ok, pair=gate_pair)
        growth = None
        if auth_ok:
            growth = {
                "turn1_payload_length": gate_pair[0].get("payload_length"),
                "turn2_payload_length": gate_pair[1].get("payload_length"),
                "turn1_payload_digest": gate_pair[0].get("payload_digest"),
                "turn2_payload_digest": gate_pair[1].get("payload_digest"),
                "turn1_prepared_digest": gate_pair[0].get("prepared_digest"),
                "turn2_prepared_digest": gate_pair[1].get("prepared_digest"),
            }
        self._check("turn2_provider_payload_differs_and_grows",
                    bool(growth)
                    and int(growth["turn2_payload_length"])
                    > int(growth["turn1_payload_length"])
                    and growth["turn1_payload_digest"]
                    != growth["turn2_payload_digest"],
                    growth=growth)
        headers = session2.get("request_headers") or []
        header_reasons = [item.get("reason") for item in headers]
        self._check("session_trace_initial_then_resume",
                    header_reasons == ["initial", "resume"],
                    request_headers=headers)
        assistants = session2.get("assistant_messages") or []
        self._check("session_trace_two_assistant_messages",
                    sorted(item.get("turn") for item in assistants) == [1, 2],
                    assistant_messages=assistants)
        users = session2.get("user_messages") or []
        prompt_hashes = {libc.sha256_bytes(self.prompts["turn1"].encode()),
                         libc.sha256_bytes(self.prompts["turn2"].encode())}
        self._check("session_trace_both_prompts",
                    prompt_hashes.issubset(
                        {item.get("text_sha256") for item in users}),
                    user_hashes=[item.get("text_sha256") for item in users])

        prepared_ok = True
        payload_ok = True
        usage_rows = []
        receipt_by_sha = {row.get("raw_sha256"): row for row in receipts
                          if row.get("raw_sha256")}
        claim_by_call = {row.get("call_id"): row for row in claims}
        for attempt, result in zip(ordered, (r1, r2)):
            claim = claim_by_call.get(attempt.get("call_id")) or {}
            receipt = receipt_by_sha.get(attempt.get("payload_digest")) or {}
            prepared_ok = prepared_ok and (
                claim.get("request_digest") == attempt.get("prepared_digest"))
            payload_ok = payload_ok and (
                receipt.get("raw_sha256") == attempt.get("payload_digest"))
            dsh_usage = self._result_usage(result)
            usage_rows.append({
                "logical_step": attempt.get("logical_step"),
                "call_id": attempt.get("call_id"),
                "dsh_usage": dsh_usage,
                "receipt_usage": receipt.get("usage"),
                "equal": dsh_usage is not None and dsh_usage == receipt.get("usage"),
            })
        self._check("prepared_digest_equals_claim", prepared_ok)
        self._check("payload_digest_equals_receipt", payload_ok)
        self._check("dsh_usage_equals_receipt_usage",
                    len(usage_rows) == 2 and all(row["equal"] for row in usage_rows),
                    rows=usage_rows)

        reservations_ok = True
        usage_totals = []
        for attempt in ordered:
            reservation = next((row for row in reservations
                                if row.get("reservation_id")
                                == attempt.get("reservation_id")), {})
            receipt = receipt_by_sha.get(attempt.get("payload_digest")) or {}
            usage = receipt.get("usage") if isinstance(receipt.get("usage"), dict) else {}
            settlement = _parse_json_text(reservation.get("settlement_json")) or {}
            mapped_input = (int(usage.get("inputTokens") or 0)
                            + int(usage.get("cacheReadTokens") or 0)
                            + int(usage.get("cacheWriteTokens") or 0))
            reservation_ok = (
                reservation.get("status") == "OK"
                and reservation.get("cost") is not None
                and (_decimal(reservation.get("cost")) or Decimal(0)) > 0
                and reservation.get("input_used") == mapped_input
                and reservation.get("output_used") == usage.get("outputTokens")
                and settlement.get("cost_usd") == reservation.get("cost")
                and (attempt.get("state") == "SETTLED"))
            reservations_ok = reservations_ok and reservation_ok
            usage_totals.append({
                "logical_step": attempt.get("logical_step"),
                "reservation_id": reservation.get("reservation_id"),
                "status": reservation.get("status"),
                "cost": reservation.get("cost"),
                "settlement_cost_usd": settlement.get("cost_usd"),
                "input_used": reservation.get("input_used"),
                "mapped_input": mapped_input,
                "output_used": reservation.get("output_used"),
                "attempt_state": attempt.get("state"),
            })
        self._check("each_request_has_settled_reservation", reservations_ok,
                    rows=usage_totals)
        self._check("all_attempts_settled",
                    all(row.get("state") == "SETTLED" for row in attempts),
                    states=[row.get("state") for row in attempts])
        self._check("no_pending_reservation",
                    all(row.get("status") != "PENDING" for row in reservations),
                    statuses=[row.get("status") for row in reservations])
        ledger = self._totals(reservations)
        committed = _decimal(ledger["committed_usd"]) or Decimal(0)
        expected = sum((_decimal(row.get("cost")) or Decimal(0)
                        for row in reservations), Decimal(0))
        self._check("ledger_totals_reconcile",
                    committed == expected
                    and ledger["reserved_usd"] == "0"
                    and ledger["spent_usd"] == ledger["committed_usd"]
                    and committed > 0,
                    totals=ledger)
        self._check("single_settlement_per_reservation",
                    len(messages["reserved"]) == 2
                    and len(messages["settled"]) == 2
                    and not messages["failed"]
                    and len({row.get("reservation_id")
                             for row in messages["settled"]}) == 2,
                    settlements=messages)
        self._check("all_receipts_synthetic_no_network",
                    all(row.get("synthetic") is True
                        and row.get("real_model_calls") == 0
                        and row.get("http_calls") == 0
                        and row.get("network_used") is False
                        for row in receipts),
                    rows=receipts)
        self._check("fake_counter_matches_receipts",
                    counter == len(receipts), counter=counter,
                    receipts=len(receipts))
        self._check("binding_start_evidence",
                    bool(self._read_json_evidence("traces/g4c-binding-start.json")))
        self._check("no_candidate_timeout",
                    not t1.get("timeout") and not t2.get("timeout"))
        self._check("containers_removed", not containers(),
                    names=containers())

        flags = {
            "old_attempt_unchanged": bool(old_unchanged),
            "new_attempt_per_request": (
                len(ordered) == 2
                and len(distinct["call_ids"]) == 2
                and len(distinct["attempt_ids"]) == 2),
            "no_old_call_id_replay": (
                sum(1 for row in attempts
                    if row.get("call_id") == old_attempt.get("call_id")) == 1),
            "no_double_settlement": (
                len(messages["settled"]) == 2 and not messages["failed"]
                and len({row.get("reservation_id")
                         for row in messages["settled"]}) == 2),
            "usage_receipt_equal": (
                len(usage_rows) == 2 and all(row["equal"] for row in usage_rows)),
        }
        self.reconciliation = self._build_reconciliation(
            ordered, claims, reservations, receipts, gate, snapshot, extra,
            phase1=phase1, session1=session1, session2=session2,
            results={"turn1": r1, "turn2": r2}, flags=flags, mode="resume")
        self.write_evidence_json("per-request.json",
                                 self.reconciliation["per_request"])
        self.write_evidence_json("reconciliation.json", self.reconciliation)

    def _evaluate_crash_resume(self) -> None:
        snapshot, extra = self._final()
        phase1 = self._phase_ledger("turn1")
        phase2 = self._phase_ledger("turn2")
        p1_summary = self._phase_doc("turn1", "phase-summary.json")
        p2_summary = self._phase_doc("turn2", "phase-summary.json")
        attempts = snapshot["attempts"]
        reservations = snapshot["reservations"]
        claims = snapshot["claims"]
        receipts = snapshot["receipts"]
        counter = snapshot["fake_counter"]
        gate = self._gate_evidence()
        modules = self._modules_evidence()
        t1 = self.phase_records.get("turn1") or {}
        t2 = self.phase_records.get("turn2") or {}
        r2 = self._read_json_evidence("traces/dsh-result-turn2.json") or {}
        session1 = p1_summary.get("session") or {}
        session2 = p2_summary.get("session") or {}
        messages = self._settlement_rows(extra["messages"])
        restart = (self.restart_records or [{}])[0]
        phase1_attempt = (phase1.get("attempts") or [{}])[0]
        phase2_attempt = (phase2.get("attempts") or [{}])[0]
        final_attempt = attempts[0] if len(attempts) == 1 else {}
        # The recovery Controller's reconcile pass legitimately annotates the
        # durable ATTEMPT_STARTED row as SETTLEMENT_UNCERTAIN.  Remove the
        # exited recovery container after collect() has copied its logs so the
        # end-of-run "no containers" assertion is evaluated truthfully.
        for record in self.restart_records:
            name = record.get("container")
            if name and self.podman_status(name) is not None:
                self.cmd(["podman", "rm", "-f", name],
                         name=f"rm-recovery-{name}", timeout=60)

        self._check("modules_loaded_from_g4_head", modules["ok"],
                    problems=modules["problems"])
        self._check("turn1_candidate_exit_nonzero",
                    t1.get("exit_code") not in (None, 0),
                    exit=t1.get("exit_code"))
        self._check("trusted_crash_exit_97",
                    ((self.container_records.get("trusted") or {}).get("exit_code")
                     in (97, -1))
                    or (t1.get("podman_run_exit") == 0
                        and (self.records.get("trusted_stop") or {}).get(
                            "exit_code") == 97),
                    trusted=(self.container_records.get("trusted") or {}).get(
                        "exit_code"),
                    trusted_stop=(self.records.get("trusted_stop") or {}).get(
                        "exit_code"))
        self._check("recovery_admission_replayed",
                    bool(restart.get("admission_replayed_exit"))
                    and restart.get("exit_code") == 3,
                    restart={key: restart.get(key) for key in
                             ("exit_code", "admission_replayed_exit", "state")})
        self._check("old_attempt_durable_and_uncertain",
                    len(attempts) == 1
                    and final_attempt.get("state") == "SETTLEMENT_UNCERTAIN"
                    and final_attempt.get("receipt_id") is None
                    and final_attempt.get("reason") == "NO_RECEIPT_AFTER_CRASH",
                    attempt=final_attempt)
        self._check("old_reservation_pending_conservative",
                    len(reservations) == 1
                    and reservations[0].get("status") == "PENDING"
                    and (_decimal(reservations[0].get("cost")) or Decimal(0)) > 0
                    and reservations[0].get("settlement_json") is None,
                    reservation=reservations[0] if reservations else {})
        self._check("no_fake_no_receipt",
                    counter == 0 and not receipts,
                    fake_counter=counter, receipts=len(receipts))
        self._check("resume_turn2_exit_nonzero",
                    t2.get("exit_code") not in (None, 0),
                    exit=t2.get("exit_code"))
        resume2 = r2.get("resume") or {}
        turn_end = (r2.get("event_summary") or {}).get("turn_end") or []
        resume_error = ((turn_end[0] or {}).get("error")
                        if turn_end and isinstance(turn_end[0], dict) else None)
        self._check("resume_attempted_and_failed",
                    resume2.get("used") is True
                    and resume2.get("sdk_call") == "resume_session"
                    and (bool(r2.get("error")) or r2.get("finish_reason") == "error"
                         or bool(resume_error)),
                    resume={key: resume2.get(key) for key in ("used", "sdk_call")},
                    finish_reason=r2.get("finish_reason"),
                    error=r2.get("error") or resume_error)
        self._check("resume_no_new_provider_request",
                    r2.get("event_count") == 0
                    or not (r2.get("event_summary") or {}).get("assistant_messages"),
                    event_count=r2.get("event_count"),
                    summary=r2.get("event_summary"))
        self._check("recovery_annotates_durable_attempt",
                    bool(phase1_attempt) and bool(phase2_attempt)
                    and phase1_attempt.get("attempt_id")
                    == phase2_attempt.get("attempt_id")
                    and phase1_attempt.get("call_id") == phase2_attempt.get("call_id")
                    and phase1_attempt.get("state") == "ATTEMPT_STARTED"
                    and phase2_attempt.get("state") == "SETTLEMENT_UNCERTAIN"
                    and phase2_attempt.get("reason") == "NO_RECEIPT_AFTER_CRASH",
                    turn1_after_crash=phase1_attempt,
                    turn2_after_recovery=phase2_attempt)
        self._check("old_attempt_not_rewritten_by_resume",
                    bool(phase2_attempt) and phase2_attempt == final_attempt,
                    after_recovery=phase2_attempt, final=final_attempt)
        self._check("no_new_attempt_after_resume",
                    len(attempts) == 1 and len(claims) == 1
                    and len(reservations) == 1,
                    attempts=len(attempts), claims=len(claims),
                    reservations=len(reservations))
        self._check("old_call_id_single",
                    len({row.get("call_id") for row in attempts}) == 1,
                    call_ids=[row.get("call_id") for row in attempts])
        self._check("resume_sent_no_fake",
                    snapshot["fake_counter"] == 0 and not receipts,
                    fake_counter=snapshot["fake_counter"], receipts=len(receipts))
        ledger = self._totals(reservations)
        spent = _decimal(ledger["spent_usd"]) or Decimal(0)
        committed = _decimal(ledger["committed_usd"]) or Decimal(0)
        reserved = _decimal(ledger["reserved_usd"]) or Decimal(0)
        self._check("conservative_ledger_pending",
                    ledger["pending"] == 1
                    and reserved > 0
                    and spent == 0
                    and committed == reserved,
                    totals=ledger)
        self._check("no_settlement_messages",
                    len(messages["settled"]) == 0 and not messages["failed"],
                    settlements=messages)
        self._check("gate_no_authorization_before_crash",
                    not gate["authorized"], authorized=len(gate["authorized"]))
        self._check("session_persisted_before_crash",
                    session1.get("total_lines", 0) > 0,
                    session1=session1)
        self._check("resume_turn2_no_new_session_request",
                    len(session2.get("assistant_messages") or [])
                    <= len(session1.get("assistant_messages") or []),
                    turn1_assistants=len(session1.get("assistant_messages") or []),
                    turn2_assistants=len(session2.get("assistant_messages") or []))
        self._check("binding_start_evidence",
                    bool(self._read_json_evidence("traces/g4c-binding-start.json")))
        self._check("containers_removed", not containers(),
                    names=containers())

        self.reconciliation = {
            "schema": "m0.g4f.f4.reconciliation.v1",
            "mode": "crash-resume",
            "old_attempt": final_attempt,
            "old_reservation": reservations[0] if reservations else {},
            "resume_result": r2,
            "counts": {
                "attempts": len(attempts), "claims": len(claims),
                "reservations": len(reservations), "receipts": len(receipts),
                "fake_counter": snapshot["fake_counter"],
            },
            "totals": ledger,
            "settlements": messages,
            "gate_authorized": len(gate["authorized"]),
            "restart": {key: restart.get(key) for key in
                        ("exit_code", "admission_replayed_exit", "state")},
            "session_before_crash": session1,
            "session_after_resume": session2,
            "no_resend": (
                len(attempts) == 1 and len(claims) == 1
                and len(reservations) == 1 and not receipts
                and snapshot["fake_counter"] == 0
                and bool(phase2_attempt) and phase2_attempt == final_attempt
                and not messages["settled"]),
            "conservative": (
                ledger["pending"] == 1 and reserved > 0
                and spent == 0 and committed == reserved
                and not messages["settled"]),
        }
        self.write_evidence_json("per-request.json",
                                 [{"phase": "turn1-crash", "attempt": final_attempt,
                                   "reservation": reservations[0] if reservations else {},
                                   "receipt": None}])
        self.write_evidence_json("reconciliation.json", self.reconciliation)

    # -- reconciliation --------------------------------------------------
    def _build_reconciliation(self, ordered, claims, reservations, receipts,
                              gate, snapshot, extra, *, phase1, session1,
                              session2, results, flags, mode) -> dict:
        claim_by_call = {row.get("call_id"): row for row in claims}
        receipt_by_sha = {row.get("raw_sha256"): row for row in receipts
                          if row.get("raw_sha256")}
        gate_by_call = {row.get("call_id"): row for row in gate["authorized"]}
        rows = []
        for index, attempt in enumerate(ordered):
            receipt = receipt_by_sha.get(attempt.get("payload_digest")) or {}
            reservation = next((row for row in reservations
                                if row.get("reservation_id")
                                == attempt.get("reservation_id")), {})
            auth = gate_by_call.get(attempt.get("call_id")) or {}
            result = results["turn1"] if index == 0 else results["turn2"]
            settlement = _parse_json_text(reservation.get("settlement_json")) or {}
            rows.append({
                "phase": "turn1" if index == 0 else "turn2",
                "logical_step": attempt.get("logical_step"),
                "call_id": attempt.get("call_id"),
                "prepared_digest": attempt.get("prepared_digest"),
                "payload_digest": attempt.get("payload_digest"),
                "claim": {
                    "status": (claim_by_call.get(attempt.get("call_id")) or {}).get(
                        "status"),
                    "request_digest": (claim_by_call.get(
                        attempt.get("call_id")) or {}).get("request_digest"),
                },
                "attempt": {
                    "attempt_id": attempt.get("attempt_id"),
                    "state": attempt.get("state"),
                    "receipt_id": attempt.get("receipt_id"),
                },
                "reservation": {
                    "reservation_id": reservation.get("reservation_id"),
                    "status": reservation.get("status"),
                    "cost": reservation.get("cost"),
                    "input_used": reservation.get("input_used"),
                    "output_used": reservation.get("output_used"),
                    "settlement_status": settlement.get("status"),
                    "settlement_cost_usd": settlement.get("cost_usd"),
                },
                "receipt": {
                    "name": receipt.get("name"),
                    "receipt_id": receipt.get("receipt_id"),
                    "raw_sha256": receipt.get("raw_sha256"),
                    "raw_length": receipt.get("raw_length"),
                    "nonce": receipt.get("nonce"),
                    "usage": receipt.get("usage"),
                },
                "gate": {
                    "authorization_id": auth.get("authorization_id"),
                    "payload_digest": auth.get("payload_digest"),
                    "payload_length": auth.get("payload_length"),
                },
                "dsh": {
                    "final_response": result.get("final_response"),
                    "finish_reason": result.get("finish_reason"),
                    "usage": self._result_usage(result),
                    "resume": result.get("resume"),
                },
            })
        return {
            "schema": "m0.g4f.f4.reconciliation.v1",
            "mode": mode,
            "per_request": rows,
            "counts": {
                "requests": len(ordered), "reservations": len(reservations),
                "claims": len(claims), "attempts": len(ordered),
                "receipts": len(receipts),
                "fake_counter": snapshot["fake_counter"],
                "gate_authorized": len(gate["authorized"]),
                "gate_consumed": len(gate["consumed"]),
            },
            "totals": self._totals(reservations),
            "settlements": self._settlement_rows(extra["messages"]),
            "phase1_counts": self._counts(phase1),
            "session": {
                "turn1": {key: session1.get(key) for key in
                          ("total_lines", "resume_markers", "request_headers")},
                "turn2": {key: session2.get(key) for key in
                          ("total_lines", "resume_markers", "request_headers")},
            },
            **flags,
        }

    @staticmethod
    def _counts(ledger: Mapping[str, object]) -> dict:
        return {
            "reservations": len(ledger.get("reservations") or []),
            "claims": len(ledger.get("claims") or []),
            "attempts": len(ledger.get("attempts") or []),
            "receipts": len(ledger.get("receipts") or []),
            "fake_counter": ledger.get("fake_counter"),
        }

    @staticmethod
    def _result_usage(result: Mapping[str, object]) -> dict | None:
        summary = result.get("event_summary")
        if not isinstance(summary, dict):
            return None
        messages = summary.get("assistant_messages")
        if isinstance(messages, list) and messages and isinstance(messages[0], dict):
            usage = messages[0].get("data_usage") or messages[0].get("usage")
            return usage if isinstance(usage, dict) else None
        return None

    def _trusted_log(self) -> str:
        path = self.evidence / "run" / "trusted.log"
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""

    # -- cleanup / evidence ---------------------------------------------
    def cleanup(self) -> None:
        for name in self.phase_containers:
            status = self.podman_status(name)
            if status is not None:
                self.cmd(["podman", "rm", "-f", name],
                         name=f"cleanup-rm-phase-{name}", timeout=60)
        super().cleanup()
        # The frozen G3-D cleanup scans the whole host for process markers.  A
        # concurrent host pytest from another workstream is not this run's
        # residual; keep it as an observation and scope the failure decision to
        # processes that name this run or its containers.
        cleanup = self.records.get("cleanup") or {}
        residual_path = self.evidence / "cleanup" / "residual-processes.json"
        rows = _read_json(residual_path) or []
        markers = (self.run_id, self.trusted_name, self.candidate_name, "g4f4-")
        own: list[dict] = []
        foreign: list[dict] = []
        for row in rows if isinstance(rows, list) else []:
            text = " ".join(str(item) for item in (row.get("argv") or []))
            if any(marker in text for marker in markers):
                own.append(row)
            else:
                foreign.append(row)
        if foreign:
            self.write_evidence_json("cleanup/unrelated-host-processes.json",
                                     foreign)
            self.write_evidence_json("cleanup/residual-processes.json", own)
            cleanup["unrelated_host_processes"] = len(foreign)
            cleanup["unrelated_scope_note"] = (
                "host processes matching generic G3-D markers but not this run; "
                "not started or owned by this run")
            problems = [problem for problem in cleanup.get("problems", [])
                        if problem != "residual_processes"]
            if own:
                problems.append("residual_processes")
            cleanup["problems"] = problems
            cleanup["ok"] = not problems
            self.records["cleanup"] = cleanup
            self.write_evidence_json("cleanup/cleanup.json", cleanup)
            if not problems and self.exit_code == lib3d.EXIT_CLEANUP_RESIDUAL:
                self.exit_code = lib3d.EXIT_OK
                self.failure = None

    def write_evidence(self) -> None:
        super().write_evidence()
        path = self.evidence / "summary.json"
        summary = _read_json(path)
        if summary is None:
            return
        summary["f4"] = {
            "kind": self.f4_kind,
            "session_id": self.args.session,
            "runner_sha256": sha256_file(Path(__file__).resolve()),
            "stage_tree_sha256": lib3d.sha256_tree(self.stage_dir),
            "nonce_sha256": libc.sha256_bytes(self.nonce.encode()),
            "prompt_sha256": {
                key: libc.sha256_bytes(value.encode())
                for key, value in self.prompts.items()
            },
            "phases": {
                key: {
                    "container": record.get("container"),
                    "exit_code": record.get("exit_code"),
                    "utc_start": record.get("utc_start"),
                    "utc_end": record.get("utc_end"),
                }
                for key, record in self.phase_records.items()
            },
            "reconciliation": "reconciliation.json",
            "per_request": "per-request.json",
        }
        self.write_evidence_json("summary.json", summary)


# ---------------------------------------------------------------------------
# phase / orchestrator entrypoints
# ---------------------------------------------------------------------------
def _launcher_args(args: argparse.Namespace, *, kind: str) -> argparse.Namespace:
    case = "f4-resume" if kind == "resume" else "f4-crash-resume"
    run_id = f"g4f4-{kind}-{lib3d.utc_compact()}-{secrets.token_hex(3)}"
    evidence = Path(args.out_dir) / "runs" / f"{kind}-{lib3d.utc_compact()}"
    if evidence.exists():
        evidence = evidence.with_name(evidence.name + "-" + secrets.token_hex(2))
    namespace = argparse.Namespace(
        case=case, sub="", scenario="resume",
        session=SESSION_ID, prompt="G4F_F4_BETA",
        stage=str(args.stage) if args.stage else None,
        run_id=run_id, evidence_dir=str(evidence),
        keep_run=bool(args.keep_run), timeout=float(args.timeout),
        ready_timeout=float(args.ready_timeout), stop_grace=5.0,
        candidate_mode="dsh", hold_seconds=600,
        crash_hook=CRASH_HOOK if kind == "crash-resume" else None,
        max_calls=None, steps=None, label=None,
        f4_kind=kind)
    return namespace


def run_phase(args: argparse.Namespace) -> int:
    namespace = _launcher_args(args, kind=args.phase)
    if os.geteuid() != 0:
        sys.stderr.write("G4F4_NEEDS_HOST_ROOT\n")
        return lib3d.EXIT_BLOCKED_ENVIRONMENT
    try:
        launcher = F4Launcher(namespace)
    except lib3d.G3DError as exc:
        sys.stderr.write(f"F4_LAUNCH_FAILED {exc.reason}: {exc}\n")
        return exc.exit_code
    try:
        launcher.preflight()
        launcher.create_run()
        launcher.write_configs()
        launcher.start_trusted()
        try:
            launcher.start_candidate()
            launcher.collect()
            launcher.evaluate()
        except lib3d.G3DError as exc:
            launcher.failure = {"reason": exc.reason, "message": str(exc),
                                "detail": exc.detail}
            launcher.exit_code = exc.exit_code
            try:
                launcher.collect()
                launcher.evaluate()
            except Exception as eval_exc:  # noqa: BLE001 - keep evidence
                launcher.record_error("EVALUATE_FAILED",
                                      f"{type(eval_exc).__name__}: {eval_exc}")
    except lib3d.G3DError as exc:
        launcher.failure = {"reason": exc.reason, "message": str(exc),
                            "detail": exc.detail}
        launcher.exit_code = exc.exit_code
        launcher.record_error(exc.reason, str(exc), **exc.detail)
        try:
            launcher.collect()
        except Exception:  # noqa: BLE001
            pass
    except Exception as exc:  # noqa: BLE001
        launcher.failure = {"reason": "INTERNAL",
                            "message": f"{type(exc).__name__}: {exc}"}
        launcher.exit_code = lib3d.EXIT_CASE_FAILED
        launcher.record_error("INTERNAL", f"{type(exc).__name__}: {exc}")
    try:
        launcher.cleanup()
    except Exception as exc:  # noqa: BLE001
        launcher.record_error("CLEANUP_EXCEPTION", f"{type(exc).__name__}: {exc}")
        if launcher.exit_code == lib3d.EXIT_OK:
            launcher.exit_code = lib3d.EXIT_CLEANUP_RESIDUAL
    try:
        launcher.write_evidence()
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"EVIDENCE_WRITE_FAILED {type(exc).__name__}: {exc}\n")
        if launcher.exit_code == lib3d.EXIT_OK:
            launcher.exit_code = lib3d.EXIT_EVIDENCE_INTEGRITY
    print(json.dumps({"phase": args.phase, "run_id": launcher.run_id,
                      "status": "PASS" if launcher.exit_code == 0 else "FAIL",
                      "exit": launcher.exit_code,
                      "evidence": str(launcher.evidence),
                      "failure": launcher.failure}, sort_keys=True))
    return launcher.exit_code


def _run_child(phase: str, args: argparse.Namespace) -> dict:
    stamp = lib3d.utc_compact()
    log_path = Path(args.out_dir) / "logs" / f"{phase}-{stamp}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "-B", str(Path(__file__).resolve()),
            "--phase", phase, "--out-dir", str(args.out_dir),
            "--timeout", str(args.timeout),
            "--ready-timeout", str(args.ready_timeout)]
    if args.stage:
        argv.extend(["--stage", str(args.stage)])
    if args.keep_run:
        argv.append("--keep-run")
    started = utc()
    with open(log_path, "w", encoding="utf-8") as handle:
        handle.write("ARGV " + json.dumps(argv) + "\n")
        handle.flush()
        proc = subprocess.run(argv, cwd=str(lib.REPO_ROOT), capture_output=True,
                              text=True, timeout=float(args.timeout) * 6 + 300)
        handle.write(proc.stdout)
        handle.write(proc.stderr)
    finished = utc()
    evidence = None
    status_line = None
    for line in reversed(proc.stdout.splitlines()):
        try:
            document = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(document, dict) and document.get("phase") == phase:
            evidence = document.get("evidence")
            status_line = document
            break
    summary = None
    if evidence:
        summary = _read_json(Path(evidence) / "summary.json")
    checks = (summary or {}).get("checks") or []
    failed = [item["id"] for item in checks if not item.get("ok")]
    return {
        "phase": phase, "argv": argv, "utc_start": started, "utc_end": finished,
        "exit_code": proc.returncode, "log": str(log_path),
        "evidence": evidence, "status_line": status_line,
        "summary": summary, "checks_total": len(checks),
        "checks_failed": failed,
        "ok": proc.returncode == 0 and summary is not None and not failed,
        "stdout_tail": proc.stdout[-2000:], "stderr_tail": proc.stderr[-2000:],
    }


def stage_path(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).resolve()
    candidates = sorted(path for path in libc.STAGE_ROOT.glob("stage-*")
                        if (path / "manifest.json").is_file())
    if not candidates:
        raise SystemExit("no G4 stage; run scripts/g4/build_stage_c.py first")
    return candidates[-1]


def _evidence_index(run: Path) -> dict:
    def rel(*patterns: str) -> list[str]:
        found = []
        for pattern in patterns:
            found.extend(sorted(
                str(path.relative_to(run)) for path in run.glob(pattern)
                if path.is_file()))
        return sorted(set(found))

    return {
        "argv": rel("phases/*/argv.json", "run/argv-candidate-*.json"),
        "utc_and_exit": rel("phases/*/phase.json"),
        "identity": rel("phases/*/identity.json", "phases/*/uid-map.txt",
                        "phases/*/mountinfo.txt", "uid-map/*",
                        "mountinfo/*"),
        "peercred": rel("phases/*/peercred.json", "peercred/*",
                        "socket-stat/*"),
        "dsh_trace": rel("phases/*/dsh-result.json", "traces/dsh-result-*.json"),
        "session": rel("phases/*/session.json", "phases/*/session/**/*.jsonl"),
        "db": rel("db/*", "phases/*/db/*"),
        "receipt": rel("receipt/*", "phases/*/receipt/*"),
        "fake_counter": rel("db/snapshot.json",
                            "phases/*/receipt/received-count.json"),
        "reconciliation": rel("reconciliation.json", "per-request.json",
                              "checks/checks.json"),
        "cleanup": rel("cleanup/*", "env/canonical-post.json"),
    }


def orchestrate(args: argparse.Namespace) -> int:
    if os.geteuid() != 0:
        sys.stderr.write("G4F4_NEEDS_HOST_ROOT\n")
        return lib3d.EXIT_BLOCKED_ENVIRONMENT
    stage = stage_path(args.stage)
    head = lib3d.git_text("rev-parse", "HEAD")
    validation = libc.validate_stage_g4(stage, base_sha=head, verify_git=True)
    if not validation["ok"]:
        sys.stderr.write("G4F4_STAGE_INVALID "
                         + json.dumps(validation["problems"][:20]) + "\n")
        return lib3d.EXIT_STAGE_INVALID
    if containers():
        sys.stderr.write("containers already present; refusing to start\n")
        return lib3d.EXIT_BLOCKED_ENVIRONMENT
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    report: dict = {
        "schema": "m0.g4f.f4.runner.v1",
        "utc_start": utc(), "head": head, "stage": str(stage),
        "stage_manifest_sha256": validation["manifest_sha256"],
        "stage_base_sha": validation["base_sha"],
        "stage_tree_sha256": lib3d.sha256_tree(stage),
        "rootfs_sha256_before": lib3d.sha256_tree(lib3d.ROOTFS),
        "deps_sha256_before": lib3d.sha256_tree(lib3d.DEPS),
        "stage_sha256_before": lib3d.sha256_tree(stage),
        "phases": {},
    }
    report["evidence_index"] = {}
    for phase in PHASES:
        report["phases"][phase] = _run_child(phase, args)
        evidence = report["phases"][phase].get("evidence")
        if evidence:
            report["evidence_index"][phase] = _evidence_index(Path(evidence))
        lib.write_json_atomic(out_dir / "summary.json", report)
    report["utc_end"] = utc()
    report["containers_after"] = containers()
    report["rootfs_sha256"] = lib3d.sha256_tree(lib3d.ROOTFS)
    report["deps_sha256"] = lib3d.sha256_tree(lib3d.DEPS)
    report["rootfs_canonical"] = report["rootfs_sha256"] == lib3d.ROOTFS_CANON
    report["deps_canonical"] = report["deps_sha256"] == lib3d.DEPS_CANON
    report["stage_sha256_after"] = lib3d.sha256_tree(stage)
    report["stage_unchanged"] = (
        report["stage_sha256_after"] == report["stage_sha256_before"])
    report["real_model_calls"] = 0
    report["real_external_http_calls"] = 0
    report["provider_keys_seen"] = 0
    report["live_gate_status"] = "BLOCKED"
    report["ok"] = (
        all(record.get("ok") for record in report["phases"].values())
        and not report["containers_after"]
        and report["rootfs_canonical"] and report["deps_canonical"])
    report["conclusion"] = ("RESUME_L2_VERIFIED" if report["ok"]
                            else "RESUME_L2_NOT_VERIFIED")
    written = lib.write_json_atomic(out_dir / "summary.json", report)
    print(json.dumps({"ok": report["ok"],
                      "phases": {key: value.get("ok")
                                 for key, value in report["phases"].items()},
                      "containers_after": report["containers_after"],
                      "rootfs_canonical": report["rootfs_canonical"],
                      "deps_canonical": report["deps_canonical"],
                      "file": str(out_dir / "summary.json"),
                      "sha256": written["sha256"]}, sort_keys=True))
    return lib3d.EXIT_OK if report["ok"] else lib3d.EXIT_CASE_FAILED


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=PHASES, default=None,
                        help="run one phase (default: orchestrate both)")
    parser.add_argument("--stage", default=None)
    parser.add_argument("--out-dir", default=str(F4_ROOT))
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--ready-timeout", type=float, default=30.0)
    parser.add_argument("--keep-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.phase is None:
        return orchestrate(args)
    return run_phase(args)


if __name__ == "__main__":
    raise SystemExit(main())
