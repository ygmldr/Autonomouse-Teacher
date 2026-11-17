#!/usr/bin/env python3
"""D3 recovery/regression Gate runner (real D1 dual containers, 0 Key/network).

Each single case creates one independent ``$RUN`` and starts the reviewed D1
Trusted container.  Crash cases use the product's test-only crash hook, then a
**real new Trusted process** is started against the same state directory and
its ``reconcile_on_startup`` effects are measured.  Candidate-side probes run
inside a real Candidate container (hold + ``podman exec``) or as a real
Candidate-identity DSH container.  Nothing is mocked: every SIGKILL/SIGSTOP,
receipt, Broker row and reconciliation result comes from the real process.

Suites (C01/C07/C08/C09/C11 and D3-01) are orchestrated by
``scripts/g3d/run_d3_suite.py``; this file executes one run at a time.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import sqlite3
import stat
import subprocess
import sys
import time
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib_g3d as lib  # noqa: E402
import launch as launch_mod  # noqa: E402

D3_PROBE_PREFIX = "/project/run/d3-probes"
D2_PROBE_PREFIX = "/project/run/probes"

CASES: dict[str, dict] = {
    "d3-c01-echo": {"kind": "positive", "scenario": "echo"},
    "d3-c01-tool": {"kind": "positive", "scenario": "tool"},
    "d3-c01-resume": {"kind": "resume", "scenario": "resume"},
    "d3-c02": {"kind": "c02", "scenario": "echo"},
    "d3-c03": {"kind": "crash", "scenario": "recover",
               "crash_hook": "after_claim_before_attempt_start"},
    "d3-c04": {"kind": "crash", "scenario": "recover",
               "crash_hook": "after_attempt_start_before_fake_send"},
    "d3-c05": {"kind": "crash", "scenario": "recover",
               "crash_hook": "after_response_before_settlement",
               "restarts": 2},
    "d3-c06": {"kind": "crash", "scenario": "recover",
               "crash_hook": "after_broker_settle_before_journal_mark",
               "restarts": 2},
    "d3-c07-before": {"kind": "cancel", "scenario": "cancel",
                      "cancel_phase": "before_send"},
    "d3-c07-after": {"kind": "cancel", "scenario": "cancel",
                     "cancel_phase": "after_send"},
    "d3-c07-two": {"kind": "cancel", "scenario": "cancel",
                   "cancel_phase": "two_streams"},
    "d3-c08-half": {"kind": "c08", "scenario": "cancel",
                    "c08_phase": "half_close"},
    "d3-c08-disconnect": {"kind": "c08", "scenario": "cancel",
                          "c08_phase": "disconnect_mid_stream"},
    "d3-c08-sigterm": {"kind": "c08", "scenario": "cancel",
                       "c08_phase": "sigterm"},
    "d3-c09-broker": {"kind": "deadline", "scenario": "deadline_broker",
                      "deadline_phase": "broker"},
    "d3-c09-fake": {"kind": "deadline", "scenario": "deadline_fake",
                    "deadline_phase": "fake"},
    "d3-c09-stall": {"kind": "deadline", "scenario": "deadline_stall",
                     "deadline_phase": "stall"},
    "d3-c10": {"kind": "positive", "scenario": "stream"},
    "d3-c11-real": {"kind": "c11_real", "scenario": "c11"},
    "d3-c11-same": {"kind": "c11_same", "scenario": "same_claim"},
    "d3-c12": {"kind": "c12", "scenario": "echo"},
}

ERROR_CODES = {
    "ATTEMPT_ALREADY_STARTED", "CANCELLED", "DEADLINE_EXCEEDED",
    "BROKER_TIMEOUT", "BROKER_ERROR", "SETTLEMENT_UNCERTAIN",
    "FAKE_IO_ERROR", "INTERNAL", "REQUEST_INVALID",
}


def utc() -> str:
    return lib.utc()


def _json_load(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None


class D3Runner(launch_mod.Launcher):
    def __init__(self, args: argparse.Namespace) -> None:
        spec = CASES[args.case]
        args.scenario = spec["scenario"]
        if args.prompt is None:
            args.prompt = launch_mod.scenario_prompt(args.scenario)
        super().__init__(args)
        self.spec = spec
        self.kind = spec["kind"]
        self.crash_hook = spec.get("crash_hook")
        self.candidate_started = False
        self.snapshots: dict[str, dict] = {}
        self.probe_records: dict[str, dict] = {}
        self.extra_checks: list[dict] = []
        self.restart_records: list[dict] = []
        self.trusted_pid: int | None = None
        self.second_controller: subprocess.Popen | None = None
        self.recover_name = f"{self.trusted_name}-recover"
        self.started_utc = lib.utc()

    # -- evidence -----------------------------------------------------
    def _ensure_evidence(self) -> None:
        super()._ensure_evidence()
        for relative in ("state", "recover", "stream", "reconcile", "stress",
                         "probes", "final"):
            (self.evidence / relative).mkdir(parents=True, exist_ok=True)
        lib.write_json_atomic(self.evidence / "LEVELS.json", {
            "real_candidate_os": True,
            "real_dsh_positive": self.kind in {"positive", "resume", "c01"},
            "trusted_controller": True,
            "trusted_fault_injection": bool(self.crash_hook) or self.kind in {
                "deadline", "cancel", "c08"},
            "host_reconcile": True,
            "levels": {
                "kernel_os": "A",
                "real_dsh_protocol_positive": "B" if self.kind in {
                    "positive", "resume"} else "n/a",
                "trusted_controller_uds": "B",
                "host_reconcile": "C",
            },
            "note": "Artifact of one D3 run; the Host judge asserts invariants.",
        }, mode=0o444)

    def check(self, check_id: str, ok: bool, **detail: object) -> None:
        self.checks.append({"id": check_id, "ok": bool(ok), **detail})

    # -- run discovery helpers ---------------------------------------
    def _state_path(self, name: str) -> Path:
        return self.run_dir / "state" / name

    def _query(self, path: Path, statement: str) -> list[dict]:
        if not path.is_file():
            return []
        uri = f"file:{path}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        try:
            return [dict(row) for row in connection.execute(statement).fetchall()]
        finally:
            connection.close()

    def _safe_query(self, path: Path, statement: str) -> list[dict]:
        try:
            return self._query(path, statement)
        except sqlite3.Error:
            return []

    # -- snapshots ----------------------------------------------------
    def _receipt_rows(self) -> dict:
        folder = self.run_dir / "state" / "receipts"
        rows: list[dict] = []
        if folder.is_dir():
            for path in sorted(folder.glob("rcpt-*.json")):
                document = _json_load(path)
                if document is None:
                    rows.append({"name": path.name, "invalid": True})
                    continue
                rows.append({
                    "name": path.name, "sha256": lib.sha256_file(path),
                    "receipt_id": document.get("receipt_id"),
                    "raw_sha256": document.get("raw_sha256"),
                    "mode": document.get("mode"), "usage": document.get("usage"),
                    "nonce": document.get("nonce"),
                    "real_model_calls": document.get("real_model_calls"),
                    "http_calls": document.get("http_calls"),
                    "network_used": document.get("network_used"),
                })
        counter = None
        counter_path = folder / "received-count.json"
        if counter_path.is_file():
            counter = _json_load(counter_path)
        return {"receipts": rows, "counter": counter, "count": len(rows)}

    def _state_tree(self) -> dict:
        state = self.run_dir / "state"
        files: list[dict] = []
        problems: list[str] = []
        if state.is_dir():
            for dirpath, dirnames, filenames in os.walk(state, followlinks=False):
                dirnames[:] = [name for name in dirnames if name != "receipts"]
                for name in sorted(filenames):
                    path = Path(dirpath) / name
                    relative = str(path.relative_to(state))
                    try:
                        info = os.lstat(path)
                    except OSError as exc:
                        problems.append(f"{relative}:{type(exc).__name__}")
                        continue
                    if stat.S_ISLNK(info.st_mode):
                        files.append({"path": relative, "symlink": True})
                        continue
                    if not stat.S_ISREG(info.st_mode):
                        files.append({"path": relative, "type": "special"})
                        continue
                    try:
                        digest = lib.sha256_file(path)
                    except OSError as exc:
                        problems.append(f"{relative}:{type(exc).__name__}")
                        continue
                    files.append({"path": relative, "sha256": digest,
                                  "bytes": info.st_size,
                                  "mode": format(stat.S_IMODE(info.st_mode), "04o")})
        return {"files": files, "problems": problems, "tree_sha256": lib.sha256_bytes(
            json.dumps(files, sort_keys=True, separators=(",", ":")).encode())}

    def _snapshot(self, label: str) -> dict:
        broker = self._state_path("broker.sqlite3")
        attempts = self._state_path("attempts.sqlite3")
        document = {
            "schema": "m0.g3d.d3.snapshot.v1",
            "label": label,
            "utc": utc(),
            "state": self._state_tree(),
            "receipt": self._receipt_rows(),
            "reservations": self._safe_query(
                broker,
                "SELECT reservation_id,status,input_bound,output_bound,input_used,"
                "output_used,cost,estimated,settlement_json FROM budget_reservations "
                "ORDER BY rowid"),
            "claims": self._safe_query(
                broker,
                "SELECT call_id,reservation_id,request_digest,status "
                "FROM budget_dispatch_claims ORDER BY rowid"),
            "broker_messages": self._safe_query(
                broker, "SELECT COUNT(*) AS n FROM budget_broker_messages")[0]["n"]
            if broker.is_file() else 0,
            "attempts": self._safe_query(
                attempts,
                "SELECT attempt_id,call_id,reservation_id,state,receipt_id,reason,"
                "prepared_digest,payload_digest,run_id,logical_step,mode,"
                "input_bound_kind,input_bound_tokens,settlement_json,created_utc,"
                "updated_utc FROM g3b_attempts ORDER BY created_utc, call_id"),
            "intents": self._safe_query(
                attempts,
                "SELECT intent_id,call_id,reservation_id,state,reason "
                "FROM g3b_send_intents ORDER BY created_utc"),
            "identities": self._safe_query(
                attempts,
                "SELECT scope_id,identity_digest,call_id,logical_step "
                "FROM g3b_request_identities ORDER BY created_utc"),
            "admissions": self._safe_query(
                attempts,
                "SELECT admission_id,run_id,consumed_utc,controller_instance_id "
                "FROM g3b_admissions ORDER BY consumed_utc"),
        }
        document["counts"] = {
            "reservations": len(document["reservations"]),
            "claims": len(document["claims"]),
            "attempts": len(document["attempts"]),
            "intents": len(document["intents"]),
            "identities": len(document["identities"]),
            "receipts": document["receipt"]["count"],
            "admissions": len(document["admissions"]),
            "broker_messages": document["broker_messages"],
        }
        self.snapshots[label] = document
        lib.write_json_atomic(self.evidence / "state" / f"{label}.json", document,
                              mode=0o444)
        return document

    # -- candidate / probe helpers -----------------------------------
    def _start_candidate_hold(self) -> None:
        name = self.candidate_name
        argv = lib.candidate_run_argv(
            podman="podman", rootfs=str(lib.ROOTFS),
            stage_candidate=str(self.stage_dir / "candidate"), deps=str(lib.DEPS),
            run_dir=str(self.run_dir), name=name, mode="hold",
            label="hold", hold_seconds=900,
            timeout_s=int(self.args.timeout) + 120)
        problems = lib.argv_contract_problems(
            argv, role="candidate", run_dir=str(self.run_dir),
            stage_dir=str(self.stage_dir / "candidate"))
        if problems:
            self.fail(lib.EXIT_STAGE_INVALID,
                      "candidate hold argv violates contract", problems=problems)
        self._write_argv("candidate", argv)
        self.records["candidate_utc_start"] = lib.utc()
        record = self.cmd(argv, name="podman-run-candidate", timeout=90)
        if record["exit"] != 0:
            self.fail(lib.EXIT_CANDIDATE_START_FAILED,
                      "podman run for candidate hold failed",
                      exit=record["exit"], stderr=record["stderr"][-2000:])
        document = self.podman_inspect(name, label="inspect-candidate")
        if document is None or document["State"]["Status"] != "running":
            self.fail(lib.EXIT_CANDIDATE_START_FAILED,
                      "candidate hold container not running",
                      status=None if document is None else document["State"]["Status"])
        pid = int(document["State"].get("Pid") or 0)
        if pid > 0:
            self.runtime_identity["candidate"] = self._capture_identity(pid, "candidate")
        self.container_records["candidate"] = {
            "name": name, "container_id": document.get("Id"), "pid": pid,
            "status": document["State"]["Status"], "argv": argv,
            "env_names": self._container_env_names(document),
            "network_mode": (document.get("HostConfig") or {}).get("NetworkMode"),
            "read_only": (document.get("HostConfig") or {}).get("ReadonlyRootfs"),
            "uid_maps": (document.get("HostConfig") or {}).get("IDMappings"),
            "cap_drop": (document.get("HostConfig") or {}).get("CapDrop"),
            "security_opts": (document.get("HostConfig") or {}).get("SecurityOpt"),
        }
        self.write_evidence_json("run/inspect-candidate.json", document)
        principal_path = (self.run_dir / "candidate-session" / "evidence" /
                          "principal-hold.json")
        deadline = time.monotonic() + 25.0
        while time.monotonic() < deadline:
            if principal_path.is_file():
                break
            if self.podman_status(name) in {"exited", "stopped"}:
                logs = self._container_logs(name, "candidate-hold-failure")
                self.fail(lib.EXIT_CANDIDATE_START_FAILED,
                          "candidate hold exited before principal evidence",
                          log_tail=logs[-2000:])
            time.sleep(0.1)
        if not principal_path.is_file():
            logs = self._container_logs(name, "candidate-hold-timeout")
            self.fail(lib.EXIT_CANDIDATE_START_FAILED,
                      "candidate hold principal evidence missing",
                      log_tail=logs[-2000:])
        self.candidate_started = True
        self.socket_records["after_candidate_start"] = lib.lstat_record(
            self.run_dir / "ipc" / "bridge.sock")
        self.write_evidence_json("socket-stat/after-candidate-start.json",
                                 self.socket_records["after_candidate_start"])
        self.records["candidate_utc_start"] = lib.utc()
        self.trusted_pid = self._trusted_pid()

    def _trusted_pid(self) -> int | None:
        document = self.podman_inspect(self.trusted_name, label="inspect-trusted-pid")
        if document is None:
            return None
        return int(document["State"].get("Pid") or 0) or None

    def _exec_probe(self, name: str, filename: str, args: list[str] | None = None,
                    *, timeout: float = 60.0, expect_exit: int = 0,
                    snapshot_after: str | None = None) -> dict:
        argv = ["podman", "exec", self.candidate_name,
                "/opt/python/bin/python3.11", "-B",
                f"{D3_PROBE_PREFIX}/{filename}",
                *(args or [])]
        record = self.cmd(argv, name=f"probe-{name}", timeout=timeout)
        document = self._parse_probe(record)
        entry = {"name": name, "argv": argv, "exit": record["exit"],
                 "expect_exit": expect_exit,
                 "utc_start": record["utc_start"], "utc_end": record["utc_end"],
                 "document_present": document is not None,
                 "stderr_tail": (record.get("stderr") or "")[-1000:]}
        self.probe_records[name] = entry
        lib.write_json_atomic(self.evidence / "probes" / f"{name}.json",
                              {"record": entry, "document": document}, mode=0o444)
        self.check(f"probe_exit:{name}", record["exit"] == expect_exit,
                   exit=record["exit"], expected=expect_exit)
        if document is not None:
            lib.write_json_atomic(self.evidence / "probes" / f"{name}-document.json",
                                  document, mode=0o444)
        if snapshot_after:
            self._snapshot(snapshot_after)
        return {"record": record, "document": document}

    @staticmethod
    def _parse_probe(record: dict) -> dict | None:
        for line in reversed((record.get("stdout") or "").splitlines()):
            if line.startswith("PROBE "):
                try:
                    return json.loads(line[len("PROBE "):])
                except json.JSONDecodeError:
                    return None
        return None

    # -- trusted lifecycle -------------------------------------------
    def _stop_container(self, name: str, *, remove: bool = True) -> int | None:
        status = self.podman_status(name)
        if status == "running":
            lib.terminate_container(name, signal_fn=self._signal_container,
                                    wait_exit=self._wait_exit, grace_s=3.0)
        exit_code = self.podman_exit_code(name)
        if remove and status is not None:
            self.cmd(["podman", "rm", "-f", name], name=f"rm-{name}", timeout=60)
        return exit_code

    def _capture_trusted(self, label: str, name: str | None = None) -> dict:
        name = name or self.trusted_name
        document = self.podman_inspect(name, label=f"inspect-{label}")
        logs = self._container_logs(name, f"trusted-log-{label}")
        target = self.evidence / "recover" / f"trusted-{label}.log"
        lib.write_bytes_atomic(target, logs.encode(), mode=0o444)
        exit_code = None
        if document is not None:
            exit_code = int(document["State"].get("ExitCode", -1))
            self.write_evidence_json(f"recover/inspect-{label}.json", document)
            lib.write_bytes_atomic(
                self.evidence / "recover" / f"inspect-{label}.stdout.txt",
                ("\n".join(line for line in logs.splitlines()
                           if line.startswith(("G3D_", "bridge ")))
                 + "\n").encode(), mode=0o444)
        return {"label": label, "name": name, "exit_code": exit_code,
                "status": None if document is None else document["State"].get("Status"),
                "log_path": str(target), "log_sha256": lib.sha256_file(target)
                if target.is_file() else None}

    def _restart_trusted(self, label: str) -> dict:
        name = f"{self.recover_name}-{label}"
        argv = lib.trusted_run_argv(
            podman="podman", rootfs=str(lib.ROOTFS),
            stage_trusted=str(self.stage_dir / "trusted"), deps=str(lib.DEPS),
            run_dir=str(self.run_dir), name=name,
            timeout_s=int(self.args.timeout) + 60)
        problems = lib.argv_contract_problems(
            argv, role="trusted", run_dir=str(self.run_dir),
            stage_dir=str(self.stage_dir / "trusted"))
        if problems:
            self.fail(lib.EXIT_STAGE_INVALID,
                      "recover trusted argv violates contract", problems=problems)
        self._write_argv(f"trusted-recover-{label}", argv)
        run_record = self.cmd(argv, name=f"recover-run-{label}", timeout=90)
        if run_record["exit"] != 0:
            self.fail(lib.EXIT_TRUSTED_START_FAILED,
                      "recover trusted podman run failed",
                      exit=run_record["exit"],
                      stderr=run_record["stderr"][-2000:])
        wait_record = self.cmd(["podman", "wait", "--interval", "150ms", name],
                               name=f"recover-wait-{label}",
                               timeout=float(self.args.timeout) + 60)
        if wait_record["timed_out"]:
            self.cmd(["podman", "kill", "-s", "KILL", name],
                     name=f"recover-kill-{label}", timeout=30)
            self.cmd(["podman", "wait", "--interval", "150ms", name],
                     name=f"recover-wait-killed-{label}", timeout=30)
        captured = self._capture_trusted(f"recover-{label}", name=name)
        self.cmd(["podman", "rm", "-f", name], name=f"recover-rm-{label}",
                 timeout=60)
        self.restart_records.append(captured)
        self._snapshot(f"restart-{label}")
        return captured

    def _reconcile_state_checks(self, label: str, *, expect_settle: bool,
                                settle_delta: int, expect_state: str | None = None) -> None:
        before = self.snapshots.get("crash")
        after = self.snapshots.get(f"restart-{label}")
        if before is None or after is None:
            self.check(f"{label}:snapshots_present", False)
            return
        self.check(f"{label}:restart_exit_admission_replayed",
                   self.restart_records[-1].get("exit_code") == 3,
                   exit=self.restart_records[-1].get("exit_code"),
                   expected=3)
        self.check(f"{label}:receipt_count_unchanged",
                   before["receipt"]["count"] == after["receipt"]["count"],
                   before=before["receipt"]["count"], after=after["receipt"]["count"])
        self.check(f"{label}:fake_counter_unchanged",
                   (before["receipt"].get("counter") or {}).get("count")
                   == (after["receipt"].get("counter") or {}).get("count"),
                   before=before["receipt"].get("counter"),
                   after=after["receipt"].get("counter"))
        self.check(f"{label}:attempt_count_not_increased",
                   len(after["attempts"]) <= len(before["attempts"]),
                   before=len(before["attempts"]), after=len(after["attempts"]))
        self.check(f"{label}:reservation_count_unchanged",
                   len(after["reservations"]) == len(before["reservations"]),
                   before=len(before["reservations"]),
                   after=len(after["reservations"]))
        delta = after["broker_messages"] - before["broker_messages"]
        self.check(f"{label}:settle_message_delta",
                   delta == settle_delta, delta=delta, expected=settle_delta)
        if expect_state:
            states = [row.get("state") for row in after["attempts"]]
            self.check(f"{label}:attempt_state", expect_state in states,
                       states=states, expected=expect_state)
        if expect_settle:
            statuses = [row.get("status") for row in after["reservations"]]
            self.check(f"{label}:broker_ok", statuses and all(
                status == "OK" for status in statuses), statuses=statuses)
        self.check(f"{label}:no_free_or_zero",
                   all(float(row.get("cost") or 0) > 0 for row in after["reservations"]
                       if row.get("status") in {"OK", "FAILED"}),
                   reservations=[(row.get("status"), row.get("cost"))
                                 for row in after["reservations"]])

    # -- real DSH helper ---------------------------------------------
    def _candidate_argv(self, name: str, scenario: str, session: str,
                        prompt: str, label: str) -> list[str]:
        argv = lib.candidate_run_argv(
            podman="podman", rootfs=str(lib.ROOTFS),
            stage_candidate=str(self.stage_dir / "candidate"), deps=str(lib.DEPS),
            run_dir=str(self.run_dir), name=name, scenario=scenario,
            session=session, prompt=prompt, label=label,
            timeout_s=int(self.args.timeout) + 90)
        problems = lib.argv_contract_problems(
            argv, role="candidate", run_dir=str(self.run_dir),
            stage_dir=str(self.stage_dir / "candidate"))
        if problems:
            self.fail(lib.EXIT_STAGE_INVALID,
                      "D3 candidate argv violates contract", problems=problems)
        self._write_argv(f"candidate-{label}", argv)
        return argv

    def _finish_candidate(self, name: str, label: str, argv: list[str],
                          wait_record: dict | None = None) -> dict:
        if wait_record is None:
            wait_record = self.cmd(["podman", "wait", "--interval", "150ms", name],
                                   name=f"wait-candidate-{label}",
                                   timeout=float(self.args.timeout))
        if wait_record.get("timed_out"):
            self.cmd(["podman", "kill", "-s", "KILL", name],
                     name=f"kill-candidate-{label}", timeout=30)
            self.cmd(["podman", "wait", "--interval", "150ms", name],
                     name=f"wait-killed-{label}", timeout=30)
        final = self.podman_inspect(name, label=f"inspect-candidate-{label}-final")
        exit_code = None
        if final is not None:
            exit_code = int(final["State"].get("ExitCode", -1))
        logs = self._container_logs(name, f"candidate-log-{label}")
        lib.write_bytes_atomic(self.evidence / "run" / f"candidate-{label}.log",
                               logs.encode(), mode=0o444)
        self.cmd(["podman", "rm", "-f", name], name=f"rm-candidate-{label}",
                 timeout=60)
        result_path = (self.run_dir / "candidate-session" / "evidence" /
                       f"dsh-result-{label}.json")
        result = _json_load(result_path)
        if result is not None:
            lib.write_bytes_atomic(
                self.evidence / "traces" / f"dsh-result-{label}.json",
                lib.json_bytes(result), mode=0o444)
        record = {"label": label, "container": name, "argv": argv,
                  "utc_end": utc(), "exit_code": exit_code, "result": result}
        self.candidate_started = True
        self.records.setdefault("candidate_runs", []).append(record)
        return record

    def _run_real_candidate(self, label: str, scenario: str, session: str,
                            prompt: str, *, start_delay: float = 0.0) -> dict:
        name = f"{self.candidate_name}-{label}"
        argv = self._candidate_argv(name, scenario, session, prompt, label)
        started = lib.utc()
        record = self.cmd(argv, name=f"run-candidate-{label}", timeout=90)
        if record["exit"] != 0:
            self.fail(lib.EXIT_CANDIDATE_START_FAILED,
                      "podman run for D3 candidate failed",
                      exit=record["exit"], stderr=record["stderr"][-2000:])
        if start_delay:
            time.sleep(start_delay)
        result = self._finish_candidate(name, label, argv)
        result["utc_start"] = started
        return result

    def _run_resume_pair(self) -> None:
        turn1 = self._run_real_candidate(
            "resume-turn1", "echo", self.args.session,
            "G3D_RESUME_ALPHA nonce-7f3a9c remember this")
        if not turn1.get("result") or turn1["result"].get("final_response") != "ok":
            self.fail(lib.EXIT_CASE_FAILED,
                      "resume turn1 real DSH did not finish ok",
                      exit_code=turn1.get("exit_code"))
        turn2 = self._run_real_candidate(
            "resume-turn2", "resume", self.args.session,
            "G3D_RESUME_BETA what nonce did I ask you to remember?")
        self.records["candidate_exit_code"] = turn2.get("exit_code")
        self.records["resume_pair"] = [turn1, turn2]
        self._snapshot("final")

    # -- broker/process helpers --------------------------------------
    @staticmethod
    def _all_pids() -> list[int]:
        try:
            return sorted(int(name) for name in os.listdir("/proc")
                          if name.isdigit())
        except OSError:
            return []

    def _descendant_pids(self, root_pid: int) -> list[int]:
        parents: dict[int, int] = {}
        for pid in self._all_pids():
            try:
                text = Path(f"/proc/{pid}/status").read_text(encoding="utf-8",
                                                             errors="replace")
            except OSError:
                continue
            for line in text.splitlines():
                if line.startswith("PPid:"):
                    try:
                        parents[pid] = int(line.split(":", 1)[1].strip())
                    except ValueError:
                        pass
                    break
        result = []
        for pid in parents:
            current = pid
            seen = set()
            while current in parents and current not in seen:
                seen.add(current)
                if parents[current] == root_pid:
                    result.append(pid)
                    break
                current = parents[current]
        return sorted(result)

    def _find_broker_pid(self) -> int | None:
        if self.trusted_pid is None:
            return None
        for pid in self._descendant_pids(self.trusted_pid):
            try:
                raw = Path(f"/proc/{pid}/cmdline").read_bytes()
            except OSError:
                continue
            if b"autoteacher_m0.accounting.broker" in raw:
                return pid
        return None

    def _signal_pid(self, pid: int, signum: int) -> dict:
        try:
            os.kill(pid, signum)
            return {"pid": pid, "signal": signum, "ok": True}
        except OSError as exc:
            return {"pid": pid, "signal": signum, "ok": False,
                    "errno": exc.errno}

    def _exec_probe_async(self, name: str, filename: str,
                          args: list[str] | None = None, *,
                          timeout: float = 60.0) -> subprocess.Popen:
        argv = ["podman", "exec", self.candidate_name,
                "/opt/python/bin/python3.11", "-B",
                f"{D3_PROBE_PREFIX}/{filename}", *(args or [])]
        stdout_path = self.evidence / "probes" / f"{name}.stdout.txt"
        stderr_path = self.evidence / "probes" / f"{name}.stderr.txt"
        stdout = open(stdout_path, "wb")
        stderr = open(stderr_path, "wb")
        process = subprocess.Popen(argv, stdout=stdout, stderr=stderr,
                                   stdin=subprocess.DEVNULL, close_fds=True)
        self.probe_records[name] = {
            "name": name, "argv": argv, "async": True,
            "stdout_path": str(stdout_path), "stderr_path": str(stderr_path),
            "started_utc": utc(), "process": process, "timeout": timeout,
        }
        return process

    def _finish_async_probe(self, name: str, process: subprocess.Popen,
                            *, timeout: float = 60.0) -> dict:
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
        entry = self.probe_records[name]
        stdout = Path(entry["stdout_path"]).read_text(encoding="utf-8",
                                                      errors="replace")
        stderr = Path(entry["stderr_path"]).read_text(encoding="utf-8",
                                                      errors="replace")
        record = {"exit": process.returncode, "stdout": stdout, "stderr": stderr,
                  "utc_end": utc()}
        document = self._parse_probe(record)
        entry.update({"exit": process.returncode, "finished_utc": utc(),
                      "document_present": document is not None})
        entry.pop("process", None)
        lib.write_json_atomic(self.evidence / "probes" / f"{name}.json",
                              {"record": entry, "document": document}, mode=0o444)
        if document is not None:
            lib.write_json_atomic(
                self.evidence / "probes" / f"{name}-document.json", document,
                mode=0o444)
        return {"record": record, "document": document}

    # -- cleanup ------------------------------------------------------
    def cleanup(self) -> None:
        if self.second_controller is not None:
            try:
                self.second_controller.terminate()
                self.second_controller.wait(timeout=5)
            except BaseException:
                try:
                    self.second_controller.kill()
                except BaseException:
                    pass
        if self.kind == "c11_same":
            ipc = self.run_dir / "ipc"
            for name, kind in (("bridge2.sock", "socket"),
                               ("bridge2.sock.lock", "regular")):
                path = ipc / name
                try:
                    if kind == "socket":
                        lib.unlink_socket(path)
                    else:
                        lib.unlink_regular(path)
                except lib.G3DError:
                    pass
        super().cleanup()

    # -- case execution ----------------------------------------------
    def run_case(self) -> None:
        self.preflight()
        self.create_run()
        self.write_configs()
        if self.kind == "c11_same":
            self._write_second_controller_configs()
        self.start_trusted()
        self.trusted_pid = self._trusted_pid()
        try:
            self._dispatch()
        except lib.G3DError as exc:
            self.failure = {"reason": exc.reason, "message": str(exc),
                            "detail": exc.detail}
            self.exit_code = exc.exit_code
            self.record_error(exc.reason, str(exc), **exc.detail)
        except Exception as exc:  # noqa: BLE001
            self.failure = {"reason": "INTERNAL", "message": str(exc),
                            "traceback": traceback.format_exc()[-4000:]}
            self.exit_code = lib.EXIT_CASE_FAILED
            self.record_error("INTERNAL", f"{type(exc).__name__}: {exc}")

    def _dispatch(self) -> None:
        kind = self.kind
        if kind == "positive":
            self._run_positive()
        elif kind == "resume":
            self._run_resume_pair()
            self._snapshot("final")
            self.collect()
            self._judge_resume()
        elif kind == "c02":
            self._run_c02()
        elif kind == "crash":
            self._run_crash()
        elif kind == "cancel":
            self._run_cancel()
        elif kind == "c08":
            self._run_c08()
        elif kind == "deadline":
            self._run_deadline()
        elif kind == "c11_real":
            self._run_c11_real()
        elif kind == "c11_same":
            self._run_c11_same()
        elif kind == "c12":
            self._run_c12()
        else:
            self.fail(lib.EXIT_CASE_FAILED, f"unknown D3 kind {kind}")

    # -- positive ------------------------------------------------------
    def _run_positive(self) -> None:
        self.start_candidate()
        self._snapshot("final")
        self.collect()
        self._judge_positive()

    # -- C02 -----------------------------------------------------------
    def _run_c02(self) -> None:
        self._start_candidate_hold()
        self._snapshot("pre")
        result = self._exec_probe("c02-kill-before-send",
                                  "d3_kill_before_send.py", [],
                                  timeout=30, expect_exit=137,
                                  snapshot_after="kill")
        self.check("c02_process_sigkilled",
                   result["record"]["exit"] == 137,
                   exit=result["record"]["exit"])
        crash = self.snapshots["kill"]
        self.check("c02_no_reservation", crash["counts"]["reservations"] == 0,
                   counts=crash["counts"])
        self.check("c02_no_claim", crash["counts"]["claims"] == 0)
        self.check("c02_no_attempt", crash["counts"]["attempts"] == 0)
        self.check("c02_no_receipt", crash["counts"]["receipts"] == 0,
                   receipt=crash["receipt"])
        self.check("c02_no_fake_counter", not crash["receipt"].get("counter"),
                   counter=crash["receipt"].get("counter"))
        self.check("c02_trusted_alive",
                   self.podman_status(self.trusted_name) == "running",
                   status=self.podman_status(self.trusted_name))
        # The same Trusted process must still serve a normal real-DSH Echo.
        self.cmd(["podman", "rm", "-f", self.candidate_name],
                 name="rm-candidate-hold", timeout=60)
        echo = self._run_real_candidate("c02-echo", "echo", "g3d-d3-c02-echo",
                                        "G3D_ECHO")
        self.records["c02_echo"] = {key: value for key, value in echo.items()
                                    if key != "result"}
        self._snapshot("final")
        self.collect()
        self.check("c02_echo_exit_zero", echo.get("exit_code") == 0,
                   exit=echo.get("exit_code"))
        final = self.snapshots["final"]
        self.check("c02_positive_after_crash",
                   final["counts"]["reservations"] == 1
                   and final["counts"]["claims"] == 1
                   and final["counts"]["attempts"] == 1
                   and final["counts"]["receipts"] == 1,
                   counts=final["counts"])
        self.check("c02_no_extra_free", all(
            float(row.get("cost") or 0) > 0 for row in final["reservations"]),
            reservations=[(row.get("status"), row.get("cost"))
                          for row in final["reservations"]])

    # -- crash/reconcile ----------------------------------------------
    def _run_crash(self) -> None:
        self._start_candidate_hold()
        self._snapshot("pre")
        result = self._exec_probe(
            "crash-request", "d3_request_once.py",
            ["--session", f"g3d-{self.case}", "--label", "crash"],
            timeout=25, expect_exit=0)
        self.check("crash_probe_sent", bool(
            (result["document"] or {}).get("sent")),
            document=result["document"])
        self._wait_trusted_exit()
        self._capture_trusted("crash")
        self._stop_container(self.trusted_name)
        self._snapshot("crash")
        crash = self.snapshots["crash"]
        self.check("crash_no_fake_receipt_duplicate",
                   crash["receipt"]["count"] <= 1,
                   receipts=crash["receipt"]["count"])
        self.check("crash_no_auto_send_after_trusted_gone",
                   crash["counts"]["receipts"] == crash["receipt"]["count"])
        restarts = int(self.spec.get("restarts", 1))
        for index in range(restarts):
            self._restart_trusted(str(index))
            if index == 0:
                self._judge_crash_first_restart(crash)
            else:
                previous = self.snapshots[f"restart-{index - 1}"]
                current = self.snapshots[f"restart-{index}"]
                self.check(f"restart{index}:receipts_stable",
                           previous["receipt"]["count"]
                           == current["receipt"]["count"],
                           before=previous["receipt"]["count"],
                           after=current["receipt"]["count"])
                self.check(f"restart{index}:messages_stable",
                           previous["broker_messages"] == current["broker_messages"],
                           before=previous["broker_messages"],
                           after=current["broker_messages"])
                self.check(f"restart{index}:attempts_stable",
                           len(previous["attempts"]) == len(current["attempts"]))
        self._snapshot("final")
        self.collect()
        self._judge_crash_final()

    def _wait_trusted_exit(self) -> int | None:
        record = self.cmd(["podman", "wait", "--interval", "150ms",
                           self.trusted_name],
                          name="wait-trusted-crash", timeout=60)
        if record.get("timed_out"):
            self.cmd(["podman", "kill", "-s", "KILL", self.trusted_name],
                     name="kill-trusted-timeout", timeout=30)
        return self.podman_exit_code(self.trusted_name)

    def _judge_crash_first_restart(self, crash: dict) -> None:
        case = self.case
        after = self.snapshots["restart-0"]
        self.check("crash:restart_exit_admission_replayed",
                   self.restart_records[-1].get("exit_code") == 3,
                   exit=self.restart_records[-1].get("exit_code"))
        self.check("crash:receipt_count_unchanged",
                   crash["receipt"]["count"] == after["receipt"]["count"],
                   before=crash["receipt"]["count"],
                   after=after["receipt"]["count"])
        self.check("crash:fake_counter_unchanged",
                   (crash["receipt"].get("counter") or {}).get("count")
                   == (after["receipt"].get("counter") or {}).get("count"),
                   before=crash["receipt"].get("counter"),
                   after=after["receipt"].get("counter"))
        self.check("crash:attempt_count_not_increased",
                   len(after["attempts"]) <= len(crash["attempts"]),
                   before=len(crash["attempts"]), after=len(after["attempts"]))
        self.check("crash:reservation_count_unchanged",
                   len(after["reservations"]) == len(crash["reservations"]))
        self.check("crash:no_free_or_zero",
                   all(float(row.get("cost") or 0) > 0
                       for row in after["reservations"]
                       if row.get("status") in {"OK", "FAILED"}),
                   reservations=[(row.get("status"), row.get("cost"))
                                 for row in after["reservations"]])
        if case == "d3-c03":
            self.check("c03:no_attempt_before_restart", not crash["attempts"],
                       attempts=crash["attempts"])
            self.check("c03:no_receipt", crash["receipt"]["count"] == 0,
                       receipts=crash["receipt"])
            self.check("c03:no_attempt_after_restart", not after["attempts"],
                       attempts=after["attempts"])
            self.check("c03:intent_held", bool(after["intents"]) and all(
                row.get("state") == "HELD_UNCERTAIN" for row in after["intents"]),
                intents=after["intents"])
            self.check("c03:reservation_pending", bool(after["reservations"]) and all(
                row.get("status") == "PENDING" for row in after["reservations"]),
                reservations=after["reservations"])
        elif case == "d3-c04":
            states = [row.get("state") for row in crash["attempts"]]
            self.check("c04:attempt_started_before_crash",
                       states == ["ATTEMPT_STARTED"], states=states)
            self.check("c04:no_receipt", crash["receipt"]["count"] == 0)
            self.check("c04:uncertain_after_restart", any(
                row.get("state") == "SETTLEMENT_UNCERTAIN"
                for row in after["attempts"]),
                attempts=after["attempts"])
            self.check("c04:reservation_pending",
                       bool(after["reservations"]) and all(
                           row.get("status") == "PENDING"
                           for row in after["reservations"]),
                       reservations=after["reservations"])
            self.check("c04:no_auto_send",
                       len(after["attempts"]) == len(crash["attempts"])
                       and after["receipt"]["count"] == crash["receipt"]["count"],
                       attempts_before=len(crash["attempts"]),
                       attempts_after=len(after["attempts"]),
                       receipts_before=crash["receipt"]["count"],
                       receipts_after=after["receipt"]["count"])
        elif case == "d3-c05":
            self.check("c05:receipt_durable_before_restart",
                       crash["receipt"]["count"] == 1,
                       receipts=crash["receipt"])
            self.check("c05:attempt_response_observed", any(
                row.get("state") == "RESPONSE_OBSERVED"
                for row in crash["attempts"]), attempts=crash["attempts"])
            self.check("c05:broker_pending_before_restart",
                       bool(crash["reservations"]) and all(
                           row.get("status") == "PENDING"
                           for row in crash["reservations"]),
                       reservations=crash["reservations"])
            self.check("c05:attempt_settled_after_restart", any(
                row.get("state") == "SETTLED" for row in after["attempts"]),
                attempts=after["attempts"])
            self.check("c05:broker_ok_after_restart",
                       bool(after["reservations"]) and all(
                           row.get("status") == "OK"
                           for row in after["reservations"]),
                       reservations=after["reservations"])
            self.check("c05:settle_delta_one",
                       after["broker_messages"] - crash["broker_messages"] == 1,
                       before=crash["broker_messages"],
                       after=after["broker_messages"])
        elif case == "d3-c06":
            self.check("c06:broker_ok_before_restart",
                       bool(crash["reservations"]) and all(
                           row.get("status") == "OK"
                           for row in crash["reservations"]),
                       reservations=crash["reservations"])
            self.check("c06:attempt_not_yet_settled", any(
                row.get("state") == "RESPONSE_OBSERVED"
                for row in crash["attempts"]), attempts=crash["attempts"])
            self.check("c06:attempt_settled_after_restart", any(
                row.get("state") == "SETTLED" for row in after["attempts"]),
                attempts=after["attempts"])
            self.check("c06:not_downgraded_to_held", not any(
                row.get("state") == "WORST_CASE_HELD"
                for row in after["attempts"]), attempts=after["attempts"])
            self.check("c06:no_second_settle_message",
                       after["broker_messages"] == crash["broker_messages"],
                       before=crash["broker_messages"],
                       after=after["broker_messages"])

    def _judge_crash_final(self) -> None:
        final = self.snapshots.get("final") or {}
        self.check("crash:final_cleanup_snapshot_present", bool(final))
        self.check("crash:no_receipt_growth_in_final",
                   final.get("receipt", {}).get("count", 0)
                   <= self.snapshots["crash"]["receipt"]["count"] + 1)
        for check in self.checks:
            if not check.get("ok"):
                self.record_error("CHECK_FAILED", check["id"],
                                  detail={key: value for key, value in check.items()
                                          if key not in {"id", "ok"}})
                if self.exit_code == lib.EXIT_OK:
                    self.exit_code = lib.EXIT_CASE_FAILED

    # -- C07 cancel ----------------------------------------------------
    def _run_cancel(self) -> None:
        self._start_candidate_hold()
        self._snapshot("pre")
        phase = self.spec["cancel_phase"]
        if phase == "before_send":
            broker = self._find_broker_pid()
            self.check("c07:broker_pid_found", broker is not None, pid=broker)
            if broker is None:
                self.fail(lib.EXIT_CASE_FAILED, "broker child not found")
            stop = self._signal_pid(broker, signal.SIGSTOP)
            self.write_evidence_json("recover/broker-sigstop.json", stop)
            self.check("c07:broker_sigstop", stop.get("ok") is True, stop=stop)
            marker = (self.run_dir / "candidate-session" / "evidence" /
                      "d3-cancel-before-send.marker")
            if marker.exists():
                marker.unlink()
            process = self._exec_probe_async(
                "c07-before-send", "d3_cancel.py",
                ["--phase", "before_send", "--session", "g3d-d3-c07-before",
                 "--sync-dir", "/work/session/evidence"], timeout=20)
            deadline = time.monotonic() + 10.0
            while time.monotonic() < deadline and not marker.is_file():
                time.sleep(0.05)
            self.check("c07:cancel_marker_observed", marker.is_file(),
                       marker=str(marker))
            cont = self._signal_pid(broker, signal.SIGCONT)
            self.write_evidence_json("recover/broker-sigcont.json", cont)
            self.check("c07:broker_sigcont", cont.get("ok") is True, cont=cont)
            fetched = self._finish_async_probe("c07-before-send", process,
                                               timeout=20)
            self._snapshot("before")
            document = fetched.get("document") or {}
            terminal = ((document.get("read") or {}).get("terminal"))
            code = ((document.get("read") or {}).get("error_code"))
            self.check("c07:before_send_cancelled_terminal",
                       terminal == "error" and code == "CANCELLED",
                       terminal=terminal, code=code)
            before = self.snapshots["before"]
            self.check("c07:before_send_no_attempt", not before["attempts"],
                       attempts=before["attempts"])
            self.check("c07:before_send_no_fake", before["receipt"]["count"] == 0,
                       receipt=before["receipt"])
            self.check("c07:before_send_reservation_held",
                       bool(before["reservations"]) and all(
                           row.get("status") == "PENDING"
                           for row in before["reservations"]),
                       reservations=before["reservations"])
        elif phase == "after_send":
            fetched = self._exec_probe(
                "c07-after-send", "d3_cancel.py",
                ["--phase", "after_send", "--session", "g3d-d3-c07-after"],
                timeout=25, expect_exit=0)
            self._snapshot("after")
            document = fetched.get("document") or {}
            read = document.get("read") or {}
            self.check("c07:after_send_cancelled_terminal",
                       read.get("terminal") == "error"
                       and read.get("error_code") == "CANCELLED",
                       terminal=read.get("terminal"), code=read.get("error_code"))
            after = self.snapshots["after"]
            self.check("c07:after_send_receipt", after["receipt"]["count"] == 1,
                       receipt=after["receipt"])
            self.check("c07:after_send_conservative_cost",
                       bool(after["reservations"]) and all(
                           float(row.get("cost") or 0) > 0
                           for row in after["reservations"]
                           if row.get("status") in {"OK", "FAILED"}),
                       reservations=after["reservations"])
            self.check("c07:after_send_attempt_not_free", all(
                row.get("state") in {"SETTLED", "SETTLEMENT_UNCERTAIN",
                                     "WORST_CASE_HELD", "RESPONSE_OBSERVED"}
                for row in after["attempts"]), attempts=after["attempts"])
        else:
            fetched = self._exec_probe(
                "c07-two-streams", "d3_cancel.py",
                ["--phase", "two_streams", "--session", "g3d-d3-c07-two"],
                timeout=40, expect_exit=0)
            self._snapshot("two")
            document = fetched.get("document") or {}
            read_a = document.get("read_a") or {}
            read_b = document.get("read_b") or {}
            self.check("c07:two_cancelled_stream_error",
                       read_a.get("terminal") == "error"
                       and read_a.get("error_code") == "CANCELLED",
                       terminal=read_a.get("terminal"), code=read_a.get("error_code"))
            self.check("c07:two_other_stream_finish",
                       read_b.get("terminal") == "finish",
                       terminal=read_b.get("terminal"))
            two = self.snapshots["two"]
            self.check("c07:two_receipts", two["receipt"]["count"] == 2,
                       receipt=two["receipt"])
            self.check("c07:two_claims", two["counts"]["claims"] == 2,
                       counts=two["counts"])
            self.check("c07:two_no_free", all(
                float(row.get("cost") or 0) > 0
                for row in two["reservations"]
                if row.get("status") in {"OK", "FAILED"}),
                reservations=[(row.get("status"), row.get("cost"))
                              for row in two["reservations"]])
        self._snapshot("final")
        self.collect()

    # -- C08 disconnect / SIGTERM -------------------------------------
    def _run_c08(self) -> None:
        phase = self.spec["c08_phase"]
        if phase == "sigterm":
            self._start_candidate_hold()
            self._snapshot("pre")
            process = self._exec_probe_async(
                "c08-sigterm", "d3_half_close.py",
                ["--phase", "half_close", "--session", "g3d-d3-c08-sigterm"],
                timeout=30)
            # Wait until the Fake receipt is durable or the stream is active.
            deadline = time.monotonic() + 6.0
            while time.monotonic() < deadline:
                if self._receipt_rows()["count"] >= 1:
                    break
                time.sleep(0.05)
            stop = lib.terminate_container(
                self.trusted_name, signal_fn=self._signal_container,
                wait_exit=self._wait_exit, grace_s=5.0, kill_wait_s=5.0)
            self.write_evidence_json("recover/trusted-sigterm.json", stop)
            self._capture_trusted("sigterm")
            self._stop_container(self.trusted_name)
            fetched = self._finish_async_probe("c08-sigterm", process, timeout=30)
            self._snapshot("final")
            socket_record = lib.lstat_record(self.run_dir / "ipc" / "bridge.sock")
            self.write_evidence_json("socket-stat/after-sigterm.json", socket_record)
            self.check("c08:sigterm_socket_gone", socket_record is None,
                       socket=socket_record)
            residual = self._residual_trusted_processes()
            self.write_evidence_json("recover/residual-after-sigterm.json", residual)
            self.check("c08:sigterm_no_orphan", not residual, residual=residual)
            final = self.snapshots["final"]
            self.check("c08:sigterm_conservative_state",
                       all(row.get("state") in {
                           "ATTEMPT_STARTED", "RESPONSE_OBSERVED",
                           "SETTLEMENT_UNCERTAIN", "SETTLED", "WORST_CASE_HELD"}
                           for row in final["attempts"]),
                       attempts=final["attempts"])
            self.check("c08:sigterm_no_free", all(
                float(row.get("cost") or 0) > 0
                for row in final["reservations"]
                if row.get("status") in {"OK", "FAILED"}),
                reservations=[(row.get("status"), row.get("cost"))
                              for row in final["reservations"]])
            self.collect()
            return
        self._start_candidate_hold()
        self._snapshot("pre")
        fetched = self._exec_probe(
            f"c08-{phase}", "d3_half_close.py",
            ["--phase", phase, "--session", f"g3d-d3-c08-{phase}"],
            timeout=25, expect_exit=0)
        # Give the Controller a bounded moment to observe the close/cancel.
        time.sleep(1.0)
        self._snapshot("final")
        document = fetched.get("document") or {}
        self.write_evidence_json("recover/disconnect-document.json", document)
        self.check("c08:probe_connected", document.get("connected") is True)
        final = self.snapshots["final"]
        self.check("c08:no_fake_success_forged", not any(
            row.get("status") == "FAILED" and float(row.get("cost") or 0) == 0
            for row in final["reservations"]),
            reservations=final["reservations"])
        self.check("c08:no_free", all(
            float(row.get("cost") or 0) > 0 for row in final["reservations"]
            if row.get("status") in {"OK", "FAILED"}),
            reservations=[(row.get("status"), row.get("cost"))
                          for row in final["reservations"]])
        self.check("c08:attempt_conservative", all(
            row.get("state") in {"ATTEMPT_STARTED", "RESPONSE_OBSERVED",
                                 "SETTLEMENT_UNCERTAIN", "SETTLED",
                                 "WORST_CASE_HELD"}
            for row in final["attempts"]), attempts=final["attempts"])
        self.collect()

    def _residual_trusted_processes(self) -> list[dict]:
        markers = ["autoteacher_m0.accounting.broker", "fake_provider.py",
                   "autoteacher_m0.bridge.controller"]
        rows = []
        for pid in self._all_pids():
            try:
                raw = Path(f"/proc/{pid}/cmdline").read_bytes()
            except OSError:
                continue
            if any(marker.encode() in raw for marker in markers):
                if pid != os.getpid():
                    rows.append({"pid": pid, "cmdline": raw[:300].decode(
                        "utf-8", "replace")})
        return rows

    # -- C09 deadline/watchdog ----------------------------------------
    def _run_deadline(self) -> None:
        self._start_candidate_hold()
        self._snapshot("pre")
        phase = self.spec["deadline_phase"]
        broker_pid = None
        if phase == "broker":
            broker_pid = self._find_broker_pid()
            self.check("c09:broker_pid_found", broker_pid is not None,
                       pid=broker_pid)
            if broker_pid is None:
                self.fail(lib.EXIT_CASE_FAILED, "broker child not found")
            stop = self._signal_pid(broker_pid, signal.SIGSTOP)
            self.write_evidence_json("recover/broker-sigstop.json", stop)
            self.check("c09:broker_sigstop", stop.get("ok") is True, stop=stop)
        fetched = self._exec_probe(
            f"c09-{phase}", "d3_deadline.py",
            ["--session", f"g3d-d3-c09-{phase}", "--timeout", "10"],
            timeout=20, expect_exit=0)
        document = fetched.get("document") or {}
        read = document.get("read") or {}
        elapsed = document.get("elapsed_seconds")
        self.write_evidence_json(f"recover/deadline-{phase}.json", document)
        if phase == "broker":
            # The Broker stays SIGSTOPped: the Controller must still return a
            # bounded error, and the stopped child is reaped with the container.
            self.check("c09:broker_elapsed_bounded",
                       isinstance(elapsed, (int, float)) and elapsed < 8.0,
                       elapsed=elapsed)
            self.check("c09:broker_precise_code",
                       read.get("error_code") in {"BROKER_TIMEOUT",
                                                  "DEADLINE_EXCEEDED"},
                       code=read.get("error_code"))
            self.check("c09:broker_trusted_still_alive",
                       self.podman_status(self.trusted_name) == "running",
                       status=self.podman_status(self.trusted_name))
            self._snapshot("final")
            final = self.snapshots["final"]
            self.check("c09:broker_no_reservation", not final["reservations"],
                       reservations=final["reservations"])
            self.check("c09:broker_no_attempt", not final["attempts"],
                       attempts=final["attempts"])
            self.collect()
            return
        self.check("c09:deadline_elapsed_bounded",
                   isinstance(elapsed, (int, float)) and elapsed < 8.0,
                   elapsed=elapsed)
        self.check("c09:deadline_precise_code",
                   read.get("error_code") in {"DEADLINE_EXCEEDED",
                                              "SETTLEMENT_UNCERTAIN"},
                   code=read.get("error_code"))
        self._snapshot("final")
        final = self.snapshots["final"]
        self.check("c09:deadline_uncertain",
                   any(row.get("state") == "SETTLEMENT_UNCERTAIN"
                       for row in final["attempts"]),
                   attempts=final["attempts"])
        self.check("c09:deadline_receipt_present",
                   final["receipt"]["count"] >= 1,
                   receipt=final["receipt"])
        self.check("c09:deadline_no_settle",
                   all(row.get("status") == "PENDING"
                       for row in final["reservations"]),
                   reservations=final["reservations"])
        self.check("c09:deadline_no_free", all(
            float(row.get("cost") or 0) > 0 for row in final["reservations"]
            if row.get("status") in {"OK", "FAILED"}),
            reservations=[(row.get("status"), row.get("cost"))
                          for row in final["reservations"]])
        self.collect()

    # -- C11 real concurrency ----------------------------------------
    def _run_c11_real(self) -> None:
        name_a = f"{self.candidate_name}-c11a"
        argv_a = self._candidate_argv(name_a, "echo", "g3d-d3-c11-a",
                                      launch_mod.scenario_prompt("c11"), "c11a")
        a_started = self.cmd(argv_a, name="run-c11-a", timeout=90)
        if a_started["exit"] != 0:
            self.fail(lib.EXIT_CANDIDATE_START_FAILED,
                      "candidate A failed to start", exit=a_started["exit"])
        time.sleep(0.5)
        name_b = f"{self.candidate_name}-c11b"
        argv_b = self._candidate_argv(name_b, "echo", "g3d-d3-c11-b",
                                      launch_mod.scenario_prompt("c11"), "c11b")
        b_started = self.cmd(argv_b, name="run-c11-b", timeout=90)
        if b_started["exit"] != 0:
            self.fail(lib.EXIT_CANDIDATE_START_FAILED,
                      "candidate B failed to start", exit=b_started["exit"])
        # Both containers are running at this instant: record the real fact.
        status_a = self.podman_status(name_a)
        status_b = self.podman_status(name_b)
        self.write_evidence_json("stream/c11-concurrent.json", {
            "utc": utc(), "a": {"name": name_a, "status": status_a},
            "b": {"name": name_b, "status": status_b},
            "both_running": status_a == "running" and status_b == "running"})
        self.check("c11:both_candidates_running",
                   status_a == "running" and status_b == "running",
                   a=status_a, b=status_b)
        record_a = self._finish_candidate(name_a, "c11a", argv_a)
        record_b = self._finish_candidate(name_b, "c11b", argv_b)
        self.records["c11_runs"] = [
            {key: value for key, value in record.items() if key != "result"}
            for record in (record_a, record_b)]
        self._snapshot("final")
        self.collect()
        self._judge_c11_real(record_a, record_b)

    def _judge_c11_real(self, record_a: dict, record_b: dict) -> None:
        final = self.snapshots["final"]
        result_a = record_a.get("result") or {}
        result_b = record_b.get("result") or {}
        for label, result in (("a", result_a), ("b", result_b)):
            self.check(f"c11:real_dsh_{label}_ok",
                       result.get("final_response") == "ok"
                       and result.get("finish_reason") == "completed",
                       final_response=result.get("final_response"),
                       finish_reason=result.get("finish_reason"),
                       error=result.get("error"))
            self.check(f"c11:real_dsh_{label}_exit_zero",
                       record_a.get("exit_code") == 0 if label == "a"
                       else record_b.get("exit_code") == 0)
        self.check("c11:two_reservations", final["counts"]["reservations"] == 2,
                   counts=final["counts"])
        self.check("c11:two_claims", final["counts"]["claims"] == 2)
        self.check("c11:two_attempts", final["counts"]["attempts"] == 2)
        self.check("c11:two_receipts", final["counts"]["receipts"] == 2)
        self.check("c11:two_identities", final["counts"]["identities"] == 2)
        self.check("c11:counter_two",
                   (final["receipt"].get("counter") or {}).get("count") == 2,
                   counter=final["receipt"].get("counter"))
        identities = final["identities"]
        self.check("c11:distinct_business_digest",
                   len(identities) == 2
                   and len({row.get("identity_digest") for row in identities}) == 2,
                   identities=identities)
        self.check("c11:distinct_call_ids",
                   len({row.get("call_id") for row in final["claims"]}) == 2,
                   claims=final["claims"])
        self.check("c11:distinct_steps",
                   sorted(row.get("logical_step") for row in identities) == [0, 1],
                   identities=identities)
        self.check("c11:two_settled",
                   len(final["attempts"]) == 2 and all(
                       row.get("state") == "SETTLED" for row in final["attempts"]),
                   attempts=final["attempts"])
        self.check("c11:no_free", all(
            float(row.get("cost") or 0) > 0 for row in final["reservations"]),
            reservations=final["reservations"])
        self.write_evidence_json("stream/c11-ledger.json", {
            "identities": final["identities"],
            "claims": final["claims"],
            "reservations": final["reservations"],
            "attempts": final["attempts"],
            "receipts": final["receipt"]["receipts"],
            "interpretation":
                "two independently authorized real-DSH requests; business "
                "digest differs because sessionId is part of the digest, so "
                "this is NOT a same-claim replay. The same-claim negative is "
                "run separately in d3-c11-same.",
        })

    # -- C11 same claim -----------------------------------------------
    def _write_second_controller_configs(self) -> None:
        admission = _json_load(self._state_path("admission.json"))
        controller = _json_load(self._state_path("controller.json"))
        if not admission or not controller:
            self.fail(lib.EXIT_STAGE_INVALID, "base config missing for controller2")
        import secrets
        admission["admission_id"] = secrets.token_hex(16)
        admission["launcher"]["admission_nonce"] = secrets.token_hex(16)
        controller["admission_path"] = "/work/state/admission2.json"
        controller["socket_path"] = "/work/g3b/bridge2.sock"
        lib.write_json_atomic(self._state_path("admission2.json"), admission,
                              mode=0o400, uid=0, gid=0)
        lib.write_json_atomic(self._state_path("controller2.json"), controller,
                              mode=0o400, uid=0, gid=0)
        self.records["controller2"] = {
            "admission_path": "/work/state/admission2.json",
            "socket_path": "/work/g3b/bridge2.sock",
            "admission_id": admission["admission_id"]}

    def _start_second_controller(self) -> None:
        stdout_path = self.evidence / "recover" / "controller2.stdout.txt"
        stderr_path = self.evidence / "recover" / "controller2.stderr.txt"
        stdout = open(stdout_path, "wb")
        stderr = open(stderr_path, "wb")
        argv = ["podman", "exec", self.trusted_name,
                "/opt/python/bin/python3.11", "-B", "-m",
                "autoteacher_m0.bridge.controller",
                "--config", "/work/state/controller2.json"]
        process = subprocess.Popen(argv, stdout=stdout, stderr=stderr,
                                   stdin=subprocess.DEVNULL, close_fds=True)
        self.second_controller = process
        self.records["controller2"]["argv"] = argv
        deadline = time.monotonic() + 25.0
        listening = []
        while time.monotonic() < deadline:
            if process.poll() is not None:
                break
            listening = [entry for entry in lib.parse_proc_net_unix(
                self.trusted_pid or 0)
                if entry.get("path") == "/work/g3b/bridge2.sock"
                and entry.get("listening")]
            if listening:
                break
            time.sleep(0.1)
        self.records["controller2"]["listening"] = listening
        self.check("c11same:controller2_listening", bool(listening),
                   listening=listening, exit=process.poll())
        if not listening:
            tail = stderr_path.read_text(encoding="utf-8", errors="replace")[-2000:]
            self.fail(lib.EXIT_TRUSTED_START_FAILED,
                      "second Controller did not listen", stderr=tail)

    def _run_c11_same(self) -> None:
        self._start_second_controller()
        self._start_candidate_hold()
        self._snapshot("pre")
        fetched = self._exec_probe(
            "c11-same-claim", "d3_same_claim.py",
            ["--socket-a", "/work/g3b/bridge.sock",
             "--socket-b", "/work/g3b/bridge2.sock",
             "--session", "g3d-d3-same-claim"],
            timeout=40, expect_exit=0, snapshot_after="final")
        document = fetched.get("document") or {}
        self.write_evidence_json("recover/same-claim-document.json", document)
        self.collect()
        self._judge_c11_same(document)

    def _judge_c11_same(self, document: dict) -> None:
        final = self.snapshots["final"]
        results = document.get("results") or {}
        self.check("c11same:both_clients_connected",
                   len(results) == 2 and all(
                       item.get("connected") is True for item in results.values()),
                   results={key: item.get("connected")
                            for key, item in results.items()})
        terminals = {key: ((item.get("read") or {}).get("terminal"),
                           (item.get("read") or {}).get("error_code"))
                     for key, item in results.items()}
        self.write_evidence_json("recover/same-claim-terminals.json", terminals)
        winners = [key for key, (terminal, _code) in terminals.items()
                   if terminal == "finish"]
        losers = [key for key, (terminal, code) in terminals.items()
                  if terminal == "error" and code == "ATTEMPT_ALREADY_STARTED"]
        self.check("c11same:exactly_one_winner", len(winners) == 1,
                   terminals=terminals)
        self.check("c11same:exactly_one_loser_precise", len(losers) == 1,
                   terminals=terminals)
        self.check("c11same:one_reservation",
                   final["counts"]["reservations"] == 1,
                   counts=final["counts"])
        self.check("c11same:one_claim", final["counts"]["claims"] == 1)
        self.check("c11same:one_attempt", final["counts"]["attempts"] == 1)
        self.check("c11same:one_identity", final["counts"]["identities"] == 1)
        self.check("c11same:one_receipt", final["counts"]["receipts"] == 1)
        self.check("c11same:fake_counter_one",
                   (final["receipt"].get("counter") or {}).get("count") == 1,
                   counter=final["receipt"].get("counter"))
        self.check("c11same:two_admissions_tried",
                   final["counts"]["admissions"] == 2,
                   admissions=final["admissions"])
        self.check("c11same:winner_settled", any(
            row.get("state") == "SETTLED" for row in final["attempts"]),
            attempts=final["attempts"])
        self.check("c11same:no_free", all(
            float(row.get("cost") or 0) > 0 for row in final["reservations"]),
            reservations=final["reservations"])
        self.write_evidence_json("recover/same-claim-ledger.json", {
            "interpretation":
                "controlled trusted-side same-identity race: two real "
                "Controller processes on two audited UDS sockets, identical "
                "sessionId/messages/tools and logical_step 0, shared attempt "
                "journal. Exactly one wins; loser gets ATTEMPT_ALREADY_STARTED.",
            "identities": final["identities"],
            "claims": final["claims"],
            "reservations": final["reservations"],
            "attempts": final["attempts"],
            "receipts": final["receipt"]["receipts"],
            "terminals": terminals,
        })

    # -- C12 bootstrap/cleanup cycles ---------------------------------
    def _run_c12(self) -> None:
        self._run_real_candidate("c12-echo", "echo", "g3d-d3-c12",
                                 "G3D_ECHO")
        self._snapshot("after_echo")
        stress = self._run_stress()
        self.records["stress"] = stress
        self._stop_container(self.trusted_name)
        base = self.snapshots["after_echo"]
        for index in range(10):
            captured = self._restart_trusted(f"c12-{index}")
            current = self.snapshots[f"restart-c12-{index}"]
            self.check(f"c12:{index}:exit_admission_replayed",
                       captured.get("exit_code") == 3,
                       exit=captured.get("exit_code"))
            self.check(f"c12:{index}:receipts_stable",
                       current["receipt"]["count"] == base["receipt"]["count"],
                       before=base["receipt"]["count"],
                       after=current["receipt"]["count"])
            self.check(f"c12:{index}:claims_stable",
                       current["counts"]["claims"] == base["counts"]["claims"])
            self.check(f"c12:{index}:attempts_stable",
                       current["counts"]["attempts"] == base["counts"]["attempts"])
            self.check(f"c12:{index}:no_new_reservation",
                       current["counts"]["reservations"]
                       == base["counts"]["reservations"])
            ps = self.cmd(["podman", "ps", "-a", "--format", "{{.Names}}"],
                          name=f"c12-ps-{index}", timeout=30)
            names = [line for line in ps["stdout"].splitlines() if line.strip()]
            self.check(f"c12:{index}:no_residual_container", not names,
                       names=names)
        self._snapshot("final")
        self.collect()
        self.check("c12:stress_cgroup_limits",
                   stress.get("limits_ok") is True, stress=stress)
        self.check("c12:stress_fork_bounded",
                   stress.get("fork_eagain") is True, stress=stress)

    def _run_stress(self) -> dict:
        name = f"{lib.CONTAINER_PREFIX}stress-{self.run_id}-d3c12"
        argv = lib.aux_run_argv(
            podman="podman", rootfs=str(lib.ROOTFS),
            stage_candidate=str(self.stage_dir / "candidate"), deps=str(lib.DEPS),
            run_dir=str(self.run_dir), name=name, role="stress",
            probe="d2_12_stress.py", probe_args=["--mode", "fork"],
            timeout_s=120, pids_limit=8, memory="128m")
        problems = lib.aux_argv_contract_problems(
            argv, role="stress", run_dir=str(self.run_dir),
            stage_dir=str(self.stage_dir / "candidate"),
            probe="d2_12_stress.py")
        if problems:
            self.fail(lib.EXIT_STAGE_INVALID, "stress argv invalid",
                      problems=problems)
        self._write_argv("stress-c12", argv)
        record = lib.run_command(argv, log_dir=self.evidence / "run",
                                 name="stress-c12", timeout=90,
                                 cwd=str(self.run_dir),
                                 commands_path=self.commands_path)
        document = self._parse_probe(record)
        lib.write_json_atomic(self.evidence / "stress" / "c12.json",
                              {"record": {key: value for key, value in record.items()
                                          if key not in {"stdout", "stderr"}},
                               "document": document}, mode=0o444)
        if self.podman_status(name) is not None:
            self.cmd(["podman", "rm", "-f", name], name="rm-stress-c12",
                     timeout=60)
        limits = (document or {}).get("limits") or {}
        pids_max = (limits.get("/sys/fs/cgroup/pids.max")
                    or limits.get("pids.max") or limits.get("pids_max"))
        memory_max = (limits.get("/sys/fs/cgroup/memory.max")
                      or limits.get("memory.max") or limits.get("memory_max"))
        ops = (document or {}).get("ops") or {}
        fork_error = ops.get("error") if isinstance(ops, dict) else None
        fork_eagain = (isinstance(fork_error, dict)
                       and fork_error.get("errno") == 11)
        return {"exit": record["exit"], "document": document,
                "limits": limits, "pids_max": pids_max,
                "memory_max": memory_max, "fork_eagain": fork_eagain,
                "limits_ok": str(pids_max) == "8"
                and str(memory_max) in {"134217728", "134217728\n"}}

    # -- positive judges ----------------------------------------------
    def _candidate_result(self, label: str | None = None) -> dict | None:
        if label:
            return _json_load(self.evidence / "traces" /
                              f"dsh-result-{label}.json")
        return _json_load(self.evidence / "traces" / "dsh-result.json")

    @staticmethod
    def _usage(message: dict) -> dict | None:
        if not isinstance(message, dict):
            return None
        usage = message.get("data_usage")
        return usage if isinstance(usage, dict) else message.get("usage")

    def _judge_positive(self) -> None:
        scenario = self.spec["scenario"]
        final = self.snapshots["final"]
        result = self._candidate_result()
        self.check("positive:candidate_exit_zero",
                   self.records.get("candidate_exit_code") == 0,
                   exit=self.records.get("candidate_exit_code"))
        if scenario == "stream":
            self._judge_c10(result, final)
            return
        if scenario == "echo":
            self.check("echo:result_ok",
                       isinstance(result, dict)
                       and result.get("final_response") == "ok"
                       and result.get("finish_reason") == "completed",
                       result=None if not result else {
                           "final": result.get("final_response"),
                           "reason": result.get("finish_reason"),
                           "error": result.get("error")})
            self.check("echo:one_each",
                       final["counts"]["reservations"] == 1
                       and final["counts"]["claims"] == 1
                       and final["counts"]["attempts"] == 1
                       and final["counts"]["receipts"] == 1,
                       counts=final["counts"])
            self.check("echo:counter_one",
                       (final["receipt"].get("counter") or {}).get("count") == 1,
                       counter=final["receipt"].get("counter"))
            self._judge_ledger_usage(final, result, expected_calls=1)
            return
        if scenario == "tool":
            self.check("tool:result_ok",
                       isinstance(result, dict)
                       and result.get("final_response") == "ok"
                       and result.get("finish_reason") == "completed",
                       result=None if not result else {
                           "final": result.get("final_response"),
                           "reason": result.get("finish_reason"),
                           "error": result.get("error")})
            self.check("tool:two_each",
                       final["counts"]["reservations"] == 2
                       and final["counts"]["claims"] == 2
                       and final["counts"]["attempts"] == 2
                       and final["counts"]["receipts"] == 2,
                       counts=final["counts"])
            self.check("tool:counter_two",
                       (final["receipt"].get("counter") or {}).get("count") == 2,
                       counter=final["receipt"].get("counter"))
            modes = sorted(row.get("mode") for row in final["attempts"])
            self.check("tool:modes", modes == ["tool_final", "tool_once"],
                       modes=modes)
            self._judge_ledger_usage(final, result, expected_calls=2)
            return

    def _judge_ledger_usage(self, final: dict, result: dict | None,
                            *, expected_calls: int) -> None:
        summary = (result or {}).get("event_summary") or {}
        messages = [item for item in summary.get("assistant_messages") or []
                    if isinstance(item, dict)]
        usages = [self._usage(item) for item in messages]
        receipts = final["receipt"]["receipts"]
        self.check("ledger:usage_count_matches",
                   len([usage for usage in usages if usage]) == expected_calls
                   and len(receipts) == expected_calls,
                   usage_count=len([usage for usage in usages if usage]),
                   receipt_count=len(receipts))
        for index, receipt in enumerate(receipts):
            receipt_usage = receipt.get("usage")
            matched = any(usage == receipt_usage for usage in usages)
            self.check(f"ledger:receipt_usage_match:{index}", matched,
                       receipt_usage=receipt_usage, dsh_usages=usages)
        claims_by_call = {row.get("call_id"): row for row in final["claims"]}
        receipts_by_id = {row.get("receipt_id"): row for row in receipts}
        for row in final["attempts"]:
            claim = claims_by_call.get(row.get("call_id"))
            receipt = receipts_by_id.get(row.get("receipt_id"))
            self.check(f"ledger:prepared_digest:{row.get('attempt_id')}",
                       bool(claim) and claim.get("request_digest")
                       == row.get("prepared_digest"))
            self.check(f"ledger:payload_digest:{row.get('attempt_id')}",
                       bool(receipt) and receipt.get("raw_sha256")
                       == row.get("payload_digest"))
            self.check(f"ledger:settled:{row.get('attempt_id')}",
                       row.get("state") == "SETTLED",
                       state=row.get("state"))
        self.check("ledger:all_reservations_ok", all(
            row.get("status") == "OK" for row in final["reservations"]),
            reservations=final["reservations"])
        self.check("ledger:positive_cost", all(
            float(row.get("cost") or 0) > 0 for row in final["reservations"]),
            reservations=[row.get("cost") for row in final["reservations"]])
        self.check("ledger:two_digests_distinct",
                   len({row.get("prepared_digest") for row in final["attempts"]})
                   == len(final["attempts"])
                   and all(
                       row.get("prepared_digest") != row.get("payload_digest")
                       for row in final["attempts"]),
                   attempts=[(row.get("prepared_digest"),
                              row.get("payload_digest"))
                             for row in final["attempts"]])
        self.check("ledger:receipt_synthetic_no_network", all(
            row.get("real_model_calls") == 0 and row.get("http_calls") == 0
            and row.get("network_used") is False for row in receipts),
            receipts=receipts)
        self.check("ledger:no_free", all(
            row.get("status") != "OK" or float(row.get("cost") or 0) > 0
            for row in final["reservations"]))

    def _judge_resume(self) -> None:
        final = self.snapshots["final"]
        pair = self.records.get("resume_pair") or []
        self.check("resume:two_turns", len(pair) == 2)
        if len(pair) == 2:
            for index, turn in enumerate(pair):
                result = turn.get("result") or {}
                self.check(f"resume:turn{index + 1}:ok",
                           result.get("final_response") == "ok"
                           and result.get("finish_reason") == "completed",
                           final=result.get("final_response"),
                           reason=result.get("finish_reason"),
                           error=result.get("error"))
                self.check(f"resume:turn{index + 1}:exit_zero",
                           turn.get("exit_code") == 0,
                           exit=turn.get("exit_code"))
            turn2 = pair[1].get("result") or {}
            resume = turn2.get("resume") or {}
            sessions = resume.get("sessions") or {}
            self.check("resume:sdk_resume_used", resume.get("used") is True,
                       resume=resume)
            self.check("resume:marker_present",
                       int(sessions.get("resume_marker_count") or 0) >= 1,
                       sessions=sessions)
            self.check("resume:history_grew",
                       int(sessions.get("total_lines") or 0) > 14,
                       sessions=sessions)
        self.check("resume:two_each",
                   final["counts"]["reservations"] == 2
                   and final["counts"]["claims"] == 2
                   and final["counts"]["attempts"] == 2
                   and final["counts"]["receipts"] == 2,
                   counts=final["counts"])
        self.check("resume:counter_two",
                   (final["receipt"].get("counter") or {}).get("count") == 2,
                   counter=final["receipt"].get("counter"))
        self.check("resume:no_replay_of_old_attempt",
                   len({row.get("call_id") for row in final["claims"]}) == 2
                   and len({row.get("attempt_id") for row in final["attempts"]}) == 2,
                   claims=final["claims"], attempts=final["attempts"])
        usages = []
        for turn in pair:
            result = turn.get("result") or {}
            summary = result.get("event_summary") or {}
            messages = [item for item in summary.get("assistant_messages") or []
                        if isinstance(item, dict)]
            usages.extend(self._usage(item) for item in messages)
        usages = [usage for usage in usages if usage]
        receipts = final["receipt"]["receipts"]
        self.check("resume:usage_receipt_correspondence",
                   len(usages) == 2 and len(receipts) == 2 and all(
                       any(usage == receipt.get("usage") for usage in usages)
                       for receipt in receipts),
                   usages=usages,
                   receipt_usages=[receipt.get("usage") for receipt in receipts])
        self.check("resume:settled", all(
            row.get("state") == "SETTLED" for row in final["attempts"]),
            attempts=final["attempts"])

    # -- C10 streaming timing -----------------------------------------
    def _judge_c10(self, result: dict | None, final: dict) -> None:
        self.check("c10:result_ok",
                   isinstance(result, dict)
                   and result.get("final_response") == "early"
                   and result.get("finish_reason") == "completed",
                   result=None if not result else {
                       "final": result.get("final_response"),
                       "reason": result.get("finish_reason"),
                       "error": result.get("error")})
        receipts = final["receipt"]["receipts"]
        self.check("c10:one_each",
                   final["counts"]["reservations"] == 1
                   and final["counts"]["claims"] == 1
                   and final["counts"]["attempts"] == 1
                   and final["counts"]["receipts"] == 1,
                   counts=final["counts"])
        self.check("c10:mode_stream_slow",
                   bool(receipts) and receipts[0].get("mode") == "stream_slow",
                   modes=[row.get("mode") for row in receipts])
        self._judge_ledger_usage(final, result, expected_calls=1)
        events = (result or {}).get("events") or []
        stream_times = []
        for event in events:
            if not isinstance(event, dict):
                continue
            if isinstance(event.get("stream_time0"), list):
                stream_times.extend(value for value in event["stream_time0"]
                                    if isinstance(value, int))
            data = event.get("data")
            if isinstance(data, dict) and isinstance(data.get("stream"), list):
                for item in data["stream"]:
                    if isinstance(item, dict) and isinstance(item.get("time0"), int):
                        stream_times.append(item["time0"])
        if not stream_times:
            self.check("c10:first_chunk_timestamp", False,
                       reason="stream_time0 missing")
            return
        t1_ms = stream_times[0]
        timing_path = None
        for path in sorted((self.run_dir / "state" / "receipts").glob("timing-*.json")):
            timing_path = path
            break
        marks: dict = {}
        if timing_path is not None:
            document = _json_load(timing_path) or {}
            for mark in document.get("marks") or []:
                if isinstance(mark, dict) and isinstance(mark.get("name"), str):
                    marks[mark["name"]] = mark
            lib.write_bytes_atomic(
                self.evidence / "stream" / timing_path.name,
                timing_path.read_bytes(), mode=0o444)
        self.check("c10:timing_marks_present",
                   "first_chunk_flushed" in marks and
                   ("exit_after_finish" in marks or "exit_after_frames" in marks),
                   marks=sorted(marks))
        if "exit_after_finish" in marks:
            t2 = marks["exit_after_finish"].get("monotonic")
        else:
            t2 = marks.get("exit_after_frames", {}).get("monotonic")
        first = marks.get("first_chunk_flushed", {})
        fake_first = first.get("monotonic")
        # CLOCK_MONOTONIC is host-wide on Linux; DSH reports the runtime's
        # realtime time0 in epoch milliseconds. Convert with a host clock pair
        # sampled by the Host judge (no container clock is trusted for logic).
        mono_sample = time.monotonic()
        epoch_sample = time.time()
        t1_monotonic = (t1_ms / 1000.0) + (mono_sample - epoch_sample)
        if isinstance(t2, (int, float)):
            self.check("c10:first_dsh_chunk_before_fake_exit",
                       t1_monotonic < float(t2),
                       t1_dsh_monotonic=round(t1_monotonic, 6),
                       t2_fake_exit_monotonic=round(float(t2), 6),
                       delta_seconds=round(float(t2) - t1_monotonic, 6),
                       dsh_stream_time0_ms=t1_ms,
                       fake_exit_epoch_ms=marks.get(
                           "exit_after_finish", marks.get("exit_after_frames", {})
                       ).get("epoch_ms"))
        else:
            self.check("c10:first_dsh_chunk_before_fake_exit", False,
                       reason="fake exit monotonic missing")
        if isinstance(fake_first, (int, float)) and isinstance(t2, (int, float)):
            self.check("c10:fake_first_chunk_before_exit",
                       float(fake_first) < float(t2),
                       first=round(float(fake_first), 6),
                       exit=round(float(t2), 6))
        else:
            self.check("c10:fake_first_chunk_before_exit", False)
        self.write_evidence_json("stream/timing.json", {
            "dsh_stream_time0_ms": t1_ms,
            "dsh_first_chunk_monotonic_estimate": t1_monotonic,
            "fake_first_chunk_monotonic": fake_first,
            "fake_exit_monotonic": t2,
            "host_clock_pair": {"monotonic": mono_sample, "epoch": epoch_sample},
            "marks": marks,
            "not_buffered_replay": bool(
                isinstance(t2, (int, float)) and t1_monotonic < float(t2)),
        })


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True, choices=sorted(CASES))
    parser.add_argument("--sub", default="")
    parser.add_argument("--scenario", default=None)
    parser.add_argument("--session", default="g3d-d3-s1")
    parser.add_argument("--prompt", default=None)
    parser.add_argument("--stage", default=None)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--evidence-dir", default=None)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--ready-timeout", type=float, default=25.0)
    parser.add_argument("--stop-grace", type=float, default=5.0)
    parser.add_argument("--keep-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if os.geteuid() != 0:
        sys.stderr.write("BLOCKED_NEEDS_HOST_ROOT\n")
        return lib.EXIT_BLOCKED_ENVIRONMENT
    try:
        runner = D3Runner(args)
    except lib.G3DError as exc:
        sys.stderr.write(f"D3_INIT_FAILED {exc.reason}: {exc}\n")
        return exc.exit_code
    try:
        runner.run_case()
    except lib.G3DError as exc:
        runner.failure = {"reason": exc.reason, "message": str(exc),
                          "detail": exc.detail}
        runner.exit_code = exc.exit_code
        runner.record_error(exc.reason, str(exc), **exc.detail)
        try:
            runner.collect()
        except Exception:  # noqa: BLE001
            pass
    except Exception as exc:  # noqa: BLE001
        runner.failure = {"reason": "INTERNAL", "message": str(exc),
                          "traceback": traceback.format_exc()[-4000:]}
        runner.exit_code = lib.EXIT_CASE_FAILED
        runner.record_error("INTERNAL", f"{type(exc).__name__}: {exc}")
    if runner.second_controller is not None:
        try:
            runner.second_controller.terminate()
            runner.second_controller.wait(timeout=10)
        except BaseException:
            try:
                runner.second_controller.kill()
            except BaseException:
                pass
    try:
        runner.cleanup()
    except Exception as exc:  # noqa: BLE001
        runner.record_error("CLEANUP_EXCEPTION", f"{type(exc).__name__}: {exc}")
        if runner.exit_code == lib.EXIT_OK:
            runner.exit_code = lib.EXIT_CLEANUP_RESIDUAL
    # A failed invariant is a failed case even when every process exited cleanly.
    failed = [item["id"] for item in runner.checks if not item.get("ok")]
    if failed and runner.exit_code == lib.EXIT_OK:
        runner.exit_code = lib.EXIT_CASE_FAILED
        runner.failure = {"reason": "CHECK_FAILED", "message": "D3 invariants failed",
                          "detail": {"checks": failed[:40]}}
    try:
        runner.write_evidence()
        lib.write_json_atomic(runner.evidence / "checks.json", {
            "case": args.case, "utc": lib.utc(),
            "checks": runner.checks,
            "failures": failed,
            "snapshots": {label: snapshot.get("counts", {})
                          for label, snapshot in runner.snapshots.items()},
            "restarts": runner.restart_records,
        }, mode=0o444)
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"EVIDENCE_WRITE_FAILED {type(exc).__name__}: {exc}\n")
        if runner.exit_code == lib.EXIT_OK:
            runner.exit_code = lib.EXIT_EVIDENCE_INTEGRITY
    summary_path = runner.evidence / "summary.json"
    if summary_path.is_file():
        document = _json_load(summary_path) or {}
        document["case_checks"] = {
            "total": len(runner.checks),
            "failures": failed,
        }
        document["d3"] = {
            "kind": runner.kind,
            "snapshots": {label: snapshot.get("counts", {})
                          for label, snapshot in runner.snapshots.items()},
            "restarts": runner.restart_records,
            "second_controller": runner.records.get("controller2"),
        }
        lib.write_json_atomic(summary_path, document, mode=0o444)
    print(json.dumps({"case": args.case,
                      "run_id": runner.run_id,
                      "status": "PASS" if runner.exit_code == 0 else "FAIL",
                      "exit": runner.exit_code,
                      "checks": len(runner.checks),
                      "failed": failed,
                      "evidence": str(runner.evidence)},
                     sort_keys=True))
    return runner.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
