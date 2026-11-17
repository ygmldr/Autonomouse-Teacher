#!/usr/bin/env python3
"""D2 adversarial Gate runner (real Candidate container, 0 Key / 0 network).

This runner reuses the reviewed D1 launcher for the two-principal setup and
adds the D2 attack phase:

* one independent ``$RUN`` per case; no case shares a container name;
* a real long-lived Candidate container (``candidate_entry.py --mode hold``)
  and ``podman exec`` of audited probes that live in the Candidate stage;
* auxiliary containers with the *same* Candidate UID/GID map for D2-13
  (deliberate read-only state DAC CONTROL), D2-14 (stale Run IPC) and D2-12
  (lower cgroup stress limits);
* host-side before/after state hashes, Broker/Attempt/Receipt/Claim/Counter
  row snapshots and a case judge that re-checks raw errno/protocol codes.

The Candidate never decides its own security result: probes only report real
syscall/protocol outcomes and this host runner asserts the invariants.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import socket
import sqlite3
import stat
import sys
import time
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib_g3d as lib  # noqa: E402
import launch as launch_mod  # noqa: E402

PROBE_DIR = "run/probes"

# case -> scenario / mode / probes. Placeholders are filled from host facts.
CASES: dict[str, dict] = {
    "d2-01": {
        "scenario": "attack", "kind": "attack", "hold": True,
        "probes": [{"name": "d2_01", "file": "d2_01_read_state.py",
                    "args": ["--trusted-pid", "{trusted_pid}"]}],
        "snapshot_after_all": "final",
    },
    "d2-02": {
        "scenario": "attack", "kind": "attack", "hold": True,
        "probes": [{"name": "d2_02", "file": "d2_02_write_state.py", "args": []}],
        "snapshot_after_all": "final",
    },
    "d2-03": {
        "scenario": "attack", "kind": "attack", "hold": True,
        "probes": [{"name": "d2_03", "file": "d2_03_state_classes.py", "args": []}],
        "snapshot_after_all": "final",
    },
    "d2-04": {
        "scenario": "attack", "kind": "attack", "hold": True,
        "probes": [{"name": "d2_04", "file": "d2_04_broker_access.py",
                    "args": ["--trusted-pid", "{trusted_pid}"]}],
        "snapshot_after_all": "final",
    },
    "d2-05": {
        "scenario": "attack", "kind": "attack", "hold": True,
        "probes": [
            {"name": "d2_05_negatives", "file": "d2_05_bypass_claim.py",
             "args": ["--phase", "negatives"], "snapshot_after": "negatives"},
            {"name": "d2_05_positive", "file": "d2_05_bypass_claim.py",
             "args": ["--phase", "positive"], "snapshot_after": "positive"},
        ],
        "snapshot_after_all": "final",
    },
    "d2-06": {
        "scenario": "attack", "kind": "attack", "hold": True,
        "probes": [
            {"name": "d2_06_negatives", "file": "d2_06_forged_frames.py",
             "args": ["--phase", "negatives"], "snapshot_after": "negatives"},
            {"name": "d2_06_positive", "file": "d2_06_forged_frames.py",
             "args": ["--phase", "positive"], "snapshot_after": "positive"},
        ],
        "snapshot_after_all": "final",
    },
    "d2-07": {
        "scenario": "attack", "kind": "attack", "hold": True,
        "probes": [{"name": "d2_07", "file": "d2_07_network.py", "args": []}],
        "snapshot_after_all": "final",
    },
    "d2-08": {
        "scenario": "attack", "kind": "attack", "hold": True,
        "probes": [{"name": "d2_08", "file": "d2_08_kernel_surface.py",
                    "args": ["--trusted-pid", "{trusted_pid}"]}],
        "snapshot_after_all": "final",
    },
    "d2-09": {
        "scenario": "attack", "kind": "attack", "hold": True,
        "probes": [
            {"name": "d2_09_negatives", "file": "d2_09_tool_plugin.py",
             "args": ["--phase", "negatives"], "snapshot_after": "negatives"},
            {"name": "d2_09_positive", "file": "d2_09_tool_plugin.py",
             "args": ["--phase", "positive"], "snapshot_after": "positive"},
        ],
        "snapshot_after_all": "final",
    },
    "d2-10": {
        "scenario": "attack", "kind": "attack", "hold": True,
        "probes": [
            {"name": "d2_10_before_send", "file": "d2_10_disconnect.py",
             "args": ["--window", "before_send"], "expect_exit": 137},
            {"name": "d2_10_half_close", "file": "d2_10_disconnect.py",
             "args": ["--window", "half_close"], "snapshot_after": "half_close"},
            {"name": "d2_10_after_send", "file": "d2_10_disconnect.py",
             "args": ["--window", "after_send",
                      "--session", "g3d-d2-10-aftersend"], "expect_exit": 137},
            {"name": "d2_10_after_ack", "file": "d2_10_disconnect.py",
             "args": ["--window", "after_ack",
                      "--session", "g3d-d2-10-afterack"], "expect_exit": 137},
            {"name": "d2_10_after_chunk", "file": "d2_10_disconnect.py",
             "args": ["--window", "after_chunk",
                      "--session", "g3d-d2-10-afterchunk"],
             "snapshot_after": "after_chunk"},
            {"name": "d2_10_reconnect", "file": "d2_10_disconnect.py",
             "args": ["--window", "reconnect",
                      "--session", "g3d-d2-10-afterchunk"],
             "snapshot_after": "reconnect"},
        ],
        "snapshot_after_all": "final",
    },
    "d2-10-trusted": {
        "scenario": "attack", "kind": "attack", "hold": True,
        "crash_hook": "after_attempt_start_before_fake_send",
        "probes": [
            {"name": "d2_10_trusted", "file": "d2_10_disconnect.py",
             "args": ["--window", "trusted_crash"], "snapshot_after": "final"},
        ],
        "allow_trusted_exit": 97,
    },
    "d2-10-trusted-receipt": {
        "scenario": "attack", "kind": "attack", "hold": True,
        "crash_hook": "after_response_before_settlement",
        "probes": [
            {"name": "d2_10_trusted", "file": "d2_10_disconnect.py",
             "args": ["--window", "trusted_crash"], "snapshot_after": "final"},
        ],
        "allow_trusted_exit": 97,
    },
    "d2-11-echo": {"scenario": "echo", "kind": "positive"},
    "d2-11-tool": {"scenario": "tool", "kind": "positive"},
    "d2-11-resume": {"scenario": "resume", "kind": "resume"},
    "d2-12": {
        "scenario": "attack", "kind": "attack", "hold": True,
        "aux": [
            {"role": "stress", "name": "fork", "file": "d2_12_stress.py",
             "args": ["--mode", "fork"], "pids_limit": 8, "memory": "128m",
             "timeout": 90},
            {"role": "stress", "name": "memory", "file": "d2_12_stress.py",
             "args": ["--mode", "memory"], "pids_limit": 8, "memory": "128m",
             "timeout": 90},
            {"role": "stress", "name": "fd", "file": "d2_12_stress.py",
             "args": ["--mode", "fd"], "pids_limit": 8, "memory": "128m",
             "timeout": 90},
            {"role": "stress", "name": "connections", "file": "d2_12_stress.py",
             "args": ["--mode", "connections", "--count", "8"],
             "pids_limit": 8, "memory": "128m", "timeout": 90},
            {"role": "stress", "name": "flood", "file": "d2_12_stress.py",
             "args": ["--mode", "flood", "--count", "16"],
             "pids_limit": 8, "memory": "128m", "timeout": 90},
        ],
        "aux_first": True,
        "probes": [
            {"name": "d2_12_valid", "file": "d2_12_stress.py",
             "args": ["--mode", "valid"], "snapshot_after": "positive"},
        ],
        "snapshot_after_all": "final",
    },
    "d2-13": {
        "scenario": "attack", "kind": "attack", "hold": False,
        "aux": [{"role": "control", "name": "control",
                 "file": "d2_13_dac_control.py", "args": [],
                 "pids_limit": 256, "memory": "1g", "timeout": 90}],
        "snapshot_after_all": "final",
    },
    "d2-14": {
        "scenario": "attack", "kind": "attack", "hold": False,
        "prepare_stale_ipc": True,
        "aux": [{"role": "stale", "name": "stale", "file": "d2_14_stale_run.py",
                 "args": ["--live-socket", "{live_socket}",
                          "--trusted-pid", "{trusted_pid}"],
                 "pids_limit": 256, "memory": "1g", "timeout": 90}],
        "snapshot_after_all": "final",
    },
    "d2-15": {"scenario": "echo", "kind": "positive", "digest_case": True},
}

ERRNO_NAMES = {
    1: "EPERM", 2: "ENOENT", 9: "EBADF", 13: "EACCES", 17: "EEXIST",
    18: "EXDEV", 20: "ENOTDIR", 21: "EISDIR", 22: "EINVAL", 30: "EROFS",
    98: "EADDRINUSE", 101: "ENETUNREACH", 111: "ECONNREFUSED",
    24: "EMFILE", 11: "EAGAIN", 3: "ESRCH", 12: "ENOMEM",
}
DENY_ALL = frozenset({1, 2, 13, 30})


def utc() -> str:
    return lib.utc()


def describe_errno(op: dict) -> str:
    if op.get("ok"):
        return "OK"
    value = op.get("errno")
    return f"ERRNO={value}:{op.get('errno_name') or ERRNO_NAMES.get(value)}"


def find_op(document: dict | None, op_id: str,
            key: str = "ops") -> dict | None:
    if not isinstance(document, dict):
        return None
    for op in document.get(key) or []:
        if isinstance(op, dict) and op.get("id") == op_id:
            return op
    return None


class CaseChecks:
    """Accumulates one case's judge checks (host-verified, not self-reported)."""

    def __init__(self, case: str) -> None:
        self.case = case
        self.items: list[dict] = []

    def add(self, check_id: str, ok: bool, **detail: object) -> None:
        self.items.append({"id": check_id, "ok": bool(ok), **detail})

    @property
    def failures(self) -> list[str]:
        return [item["id"] for item in self.items if not item["ok"]]

    def denied(self, document: dict | None, op_id: str, *,
               allowed: frozenset[int] = frozenset({2}), key: str = "ops",
               cid: str | None = None) -> dict | None:
        op = find_op(document, op_id, key)
        if op is None:
            self.add(cid or ("missing:" + op_id), False, op_id=op_id)
            return None
        ok = op.get("ok") is False and op.get("errno") in allowed
        self.add(cid or op_id, ok, observed=describe_errno(op),
                 errno=op.get("errno"), allowed=sorted(allowed))
        return op

    def succeeded(self, document: dict | None, op_id: str, *,
                  key: str = "ops", cid: str | None = None) -> dict | None:
        op = find_op(document, op_id, key)
        if op is None:
            self.add(cid or ("missing:" + op_id), False, op_id=op_id)
            return None
        self.add(cid or op_id, op.get("ok") is True, observed=describe_errno(op),
                 result=op.get("result"))
        return op


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
class D2Runner(launch_mod.Launcher):
    def __init__(self, args: argparse.Namespace) -> None:
        spec = CASES[args.case]
        args.scenario = spec["scenario"]
        args.prompt = launch_mod.scenario_prompt(args.scenario)
        super().__init__(args)
        self.case_key = args.case
        self.spec = spec
        self.crash_hook = spec.get("crash_hook")
        self.candidate_started = False
        self.aux_records: list[dict] = []
        self.aux_containers: list[str] = []
        self.probes: dict[str, dict | None] = {}
        self.probe_records: dict[str, dict] = {}
        self.snapshots: dict[str, dict] = {}
        self.candidate_runs: list[dict] = []
        self.trusted_pid: int | None = None
        self.extra_checks: list[dict] = []

    # -- evidence directories ------------------------------------------
    def _ensure_evidence(self) -> None:
        super()._ensure_evidence()
        for relative in ("state", "attacks", "d2"):
            (self.evidence / relative).mkdir(parents=True, exist_ok=True)

    # -- phase dispatch -------------------------------------------------
    def run_d2(self) -> None:
        kind = self.spec["kind"]
        if kind == "positive":
            self.candidate_started = True
            super().start_candidate()
            return
        if kind == "resume":
            self._run_resume_pair()
            return
        self._snapshot("pre", query_first=True)
        if self.spec.get("prepare_stale_ipc"):
            self._prepare_stale_ipc()
        if self.spec.get("hold"):
            self._start_candidate_hold()
        routines = []
        if self.spec.get("aux_first"):
            routines = [("aux", item) for item in self.spec.get("aux", [])] + \
                       [("probe", item) for item in self.spec.get("probes", [])]
        else:
            routines = [("probe", item) for item in self.spec.get("probes", [])] + \
                       [("aux", item) for item in self.spec.get("aux", [])]
        for kind, item in routines:
            if kind == "probe":
                self._run_exec_probe(item)
                label = item.get("snapshot_after")
                if label:
                    self._snapshot(label, query_first=False)
            else:
                self._run_aux(item)
        final_label = self.spec.get("snapshot_after_all")
        if final_label and final_label not in self.snapshots:
            self._snapshot(final_label, query_first=False)

    # -- Candidate hold -------------------------------------------------
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
        self.records["candidate_run_exit"] = record["exit"]
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

    # -- probes ---------------------------------------------------------
    def _format_args(self, values: list[str]) -> list[str]:
        mapping = {
            "trusted_pid": str(self.trusted_pid or 0),
            "live_socket": str(self.run_dir / "ipc" / "bridge.sock"),
            "run_id": self.run_id,
        }
        return [str(value).format(**mapping) for value in values]

    def _parse_probe(self, record: dict, name: str) -> dict | None:
        document = None
        for line in reversed((record.get("stdout") or "").splitlines()):
            if line.startswith("PROBE "):
                try:
                    document = json.loads(line[len("PROBE "):])
                except json.JSONDecodeError:
                    document = None
                break
        return document

    def _record_probe(self, name: str, record: dict, probe: dict) -> dict | None:
        document = self._parse_probe(record, name)
        entry = {
            "name": name, "argv": record.get("argv"),
            "utc_start": record.get("utc_start"), "utc_end": record.get("utc_end"),
            "exit": record.get("exit"), "expect_exit": probe.get("expect_exit", 0),
            "stdout_sha256": lib.sha256_bytes((record.get("stdout") or "").encode()),
            "stderr_tail": (record.get("stderr") or "")[-1000:],
            "document_present": document is not None,
        }
        self.probe_records[name] = entry
        self.probes[name] = document
        target = self.evidence / "attacks" / f"{name}.json"
        lib.write_json_atomic(target, {"record": entry, "document": document},
                              mode=0o444)
        if document is not None:
            self.write_evidence_json(f"d2/probe-{name}.json", document)
        return document

    def _run_exec_probe(self, probe: dict) -> None:
        name = probe["name"]
        argv = ["podman", "exec", self.candidate_name,
                "/opt/python/bin/python3.11", "-B",
                f"/project/run/probes/{probe['file']}",
                *self._format_args(probe.get("args") or [])]
        timeout = float(probe.get("timeout", 60))
        record = self.cmd(argv, name=f"attack-{name}", timeout=timeout)
        self._record_probe(name, record, probe)

    def _run_aux(self, aux: dict) -> None:
        role = aux["role"]
        name = aux["name"]
        container = f"{lib.CONTAINER_PREFIX}{role}-{self.run_id}-{name}"
        timeout = int(aux.get("timeout", 120))
        argv = lib.aux_run_argv(
            podman="podman", rootfs=str(lib.ROOTFS),
            stage_candidate=str(self.stage_dir / "candidate"), deps=str(lib.DEPS),
            run_dir=str(self.run_dir), name=container, role=role,
            probe=aux["file"], probe_args=self._format_args(aux.get("args") or []),
            timeout_s=timeout + 30,
            pids_limit=int(aux.get("pids_limit", 256)),
            memory=str(aux.get("memory", "1g")))
        problems = lib.aux_argv_contract_problems(
            argv, role=role, run_dir=str(self.run_dir),
            stage_dir=str(self.stage_dir / "candidate"), probe=aux["file"])
        if problems:
            self.fail(lib.EXIT_STAGE_INVALID,
                      f"auxiliary {role} argv violates contract",
                      problems=problems)
        self._write_argv(f"aux-{role}-{name}", argv)
        self.aux_containers.append(container)
        # Run podman from $RUN: the container runtime may write an ``oom``
        # marker in its cwd when a cgroup OOM kill happens; keeping it inside
        # the disposable Run directory prevents worktree pollution.
        record = lib.run_command(argv, log_dir=self.evidence / "run",
                                 name=f"aux-{role}-{name}", timeout=timeout,
                                 cwd=str(self.run_dir),
                                 commands_path=self.commands_path)
        document = self._parse_probe(record, f"{role}:{name}")
        entry = {
            "role": role, "name": name, "container": container,
            "argv": record.get("argv"), "exit": record.get("exit"),
            "utc_start": record.get("utc_start"), "utc_end": record.get("utc_end"),
            "document_present": document is not None,
            "stderr_tail": (record.get("stderr") or "")[-1500:],
            "limits": {"pids_limit": aux.get("pids_limit"),
                       "memory": aux.get("memory")},
            "control_label": "CONTROL" if role == "control" else None,
        }
        self.aux_records.append(entry)
        self.probes[f"{role}:{name}"] = document
        self.probe_records[f"{role}:{name}"] = entry
        lib.write_json_atomic(self.evidence / "attacks" / f"{role}-{name}.json",
                              {"record": entry, "document": document}, mode=0o444)
        if document is not None:
            self.write_evidence_json(f"d2/probe-{role}-{name}.json", document)

    def _stop_aux(self) -> None:
        if not self.aux_containers:
            return
        names = self.cmd(["podman", "ps", "-a", "--format", "{{.Names}}"],
                         name="aux-ps", timeout=30)
        present = {line for line in names["stdout"].splitlines() if line.strip()}
        for container in self.aux_containers:
            if container in present:
                cleanup = self.cmd(["podman", "rm", "-f", container],
                                   name=f"aux-rm-{container}", timeout=60)
                self.records.setdefault("aux_cleanup", []).append(
                    {"container": container, "exit": cleanup["exit"]})
        residual = sorted(name for name in present
                          if name.startswith(f"{lib.CONTAINER_PREFIX}stress-{self.run_id}")
                          or name.startswith(f"{lib.CONTAINER_PREFIX}control-{self.run_id}")
                          or name.startswith(f"{lib.CONTAINER_PREFIX}stale-{self.run_id}"))
        self.records["aux_residual"] = residual
        if residual:
            self.record_error("AUX_RESIDUAL", "auxiliary containers remained",
                              containers=residual)

    def _capture_live_socket(self) -> None:
        stat_record = lib.lstat_record(self.run_dir / "ipc" / "bridge.sock")
        listening = [entry for entry in lib.parse_proc_net_unix(self.trusted_pid or 0)
                     if entry.get("path") == lib.SOCKET_PATH and entry.get("listening")]
        document = {
            "utc": utc(), "stat": stat_record,
            "listening": bool(listening), "listening_entries": listening,
            "trusted_pid": self.trusted_pid,
        }
        self.records["live_socket"] = document
        self.write_evidence_json("d2/live-socket.json", document)

    # -- stale IPC for D2-14 -------------------------------------------
    def _prepare_stale_ipc(self) -> None:
        stale = self.run_dir / "stale-ipc"
        stale.mkdir(mode=0o700)
        os.chown(stale, 0, 0)
        os.chmod(stale, 0o2750)
        os.chown(stale, 0, lib.GROUP_SOCKET)
        socket_path = stale / "bridge.sock"
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.bind(str(socket_path))
        finally:
            sock.close()
        os.chmod(socket_path, lib.SOCKET_MODE)
        os.chown(socket_path, 0, lib.GROUP_SOCKET)
        record = {
            "utc": lib.utc(), "stale_dir": lib.lstat_record(stale),
            "stale_socket": lib.lstat_record(socket_path),
            "note": "different Run IPC directory; no listener (stale socket file)",
        }
        self.write_evidence_json("socket-stat/stale-ipc.json", record)
        self.records["stale_ipc"] = record

    # -- real DSH resume pair ------------------------------------------
    def _run_dsh_candidate(self, *, label: str, scenario: str, prompt: str,
                           suffix: str) -> dict:
        name = f"{self.candidate_name}-{suffix}"
        argv = lib.candidate_run_argv(
            podman="podman", rootfs=str(lib.ROOTFS),
            stage_candidate=str(self.stage_dir / "candidate"), deps=str(lib.DEPS),
            run_dir=str(self.run_dir), name=name, scenario=scenario,
            session=self.args.session, prompt=prompt, label=label,
            timeout_s=int(self.args.timeout) + 60)
        problems = lib.argv_contract_problems(
            argv, role="candidate", run_dir=str(self.run_dir),
            stage_dir=str(self.stage_dir / "candidate"))
        if problems:
            self.fail(lib.EXIT_STAGE_INVALID,
                      "resume candidate argv violates contract", problems=problems)
        self._write_argv(f"candidate-{suffix}", argv)
        started = lib.utc()
        run_record = self.cmd(argv, name=f"podman-run-candidate-{suffix}", timeout=90)
        if run_record["exit"] != 0:
            self.fail(lib.EXIT_CANDIDATE_START_FAILED,
                      "podman run for resume candidate failed",
                      exit=run_record["exit"], stderr=run_record["stderr"][-2000:])
        document = self.podman_inspect(name, label=f"inspect-candidate-{suffix}")
        if document is None:
            self.fail(lib.EXIT_CANDIDATE_START_FAILED,
                      "resume candidate inspect failed")
        pid = int(document["State"].get("Pid") or 0)
        if pid > 0 and "candidate" not in self.runtime_identity:
            self.runtime_identity["candidate"] = self._capture_identity(pid, "candidate")
        self.write_evidence_json(f"run/inspect-candidate-{suffix}.json", document)
        wait_record = self.cmd(["podman", "wait", "--interval", "200ms", name],
                               name=f"podman-wait-candidate-{suffix}",
                               timeout=float(self.args.timeout))
        if wait_record["timed_out"]:
            self.cmd(["podman", "kill", "-s", "KILL", name],
                     name=f"kill-candidate-{suffix}", timeout=30)
        final = self.podman_inspect(name, label=f"inspect-candidate-{suffix}-final")
        exit_code = None
        if final is not None:
            exit_code = int(final["State"].get("ExitCode", -1))
            self.write_evidence_json(f"run/inspect-candidate-{suffix}-final.json",
                                     final)
        logs = self._container_logs(name, f"candidate-log-{suffix}")
        lib.write_bytes_atomic(self.evidence / "run" / f"candidate-{suffix}.log",
                               logs.encode(), mode=0o444)
        self.cmd(["podman", "rm", "-f", name], name=f"rm-candidate-{suffix}",
                 timeout=60)
        result_path = (self.run_dir / "candidate-session" / "evidence" /
                       f"dsh-result-{label}.json")
        result = None
        if result_path.is_file():
            try:
                result = json.loads(lib.read_regular_bytes(
                    result_path, max_bytes=8 << 20).decode("utf-8"))
            except (lib.G3DError, OSError, UnicodeDecodeError,
                    json.JSONDecodeError) as exc:
                self.record_error("RESUME_RESULT_UNREADABLE",
                                  type(exc).__name__, label=label)
        record = {
            "label": label, "scenario": scenario, "container": name,
            "argv": argv, "utc_start": started, "utc_end": lib.utc(),
            "exit_code": exit_code, "result": result,
            "result_path": str(result_path),
        }
        self.candidate_runs.append(record)
        self.candidate_started = True
        return record

    def _run_resume_pair(self) -> None:
        turn1 = self._run_dsh_candidate(
            label="turn1", scenario="echo", suffix="turn1",
            prompt="G3D_RESUME_ALPHA nonce-7f3a9c remember this")
        if not turn1.get("result") or turn1["result"].get("final_response") != "ok":
            self.fail(lib.EXIT_CASE_FAILED,
                      "resume turn1 real DSH did not finish ok",
                      exit_code=turn1.get("exit_code"))
        turn2 = self._run_dsh_candidate(
            label="turn2", scenario="resume", suffix="turn2",
            prompt="G3D_RESUME_BETA what nonce did I ask you to remember?")
        self.container_records["candidate"] = {
            "runs": [{key: value for key, value in item.items()
                      if key != "result"} for item in self.candidate_runs],
            "name": turn2["container"], "exit_code": turn2.get("exit_code"),
        }
        self.records["candidate_exit_code"] = turn2.get("exit_code")
        self.socket_records["after_candidate_exit"] = lib.lstat_record(
            self.run_dir / "ipc" / "bridge.sock")
        self.write_evidence_json("socket-stat/after-candidate-exit.json",
                                 self.socket_records["after_candidate_exit"])

    # -- state snapshots ------------------------------------------------
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
                        files.append({"path": relative, "special": True})
                        continue
                    files.append({
                        "path": relative,
                        "sha256": lib.sha256_file(path),
                        "bytes": info.st_size,
                        "mode": format(stat.S_IMODE(info.st_mode), "04o"),
                        "uid": info.st_uid, "gid": info.st_gid,
                    })
            receipts = state / "receipts"
            if receipts.is_dir():
                for path in sorted(receipts.iterdir()):
                    try:
                        info = os.lstat(path)
                    except OSError as exc:
                        problems.append(f"receipts/{path.name}:{type(exc).__name__}")
                        continue
                    if not stat.S_ISREG(info.st_mode):
                        files.append({"path": f"receipts/{path.name}", "special": True})
                        continue
                    files.append({
                        "path": f"receipts/{path.name}",
                        "sha256": lib.sha256_file(path),
                        "bytes": info.st_size,
                        "mode": format(stat.S_IMODE(info.st_mode), "04o"),
                        "uid": info.st_uid, "gid": info.st_gid,
                    })
        digest = lib.sha256_bytes("\n".join(
            f"{row['path']}:{row.get('sha256', 'special')}"
            for row in sorted(files, key=lambda item: item["path"])).encode())
        data_digest = lib.sha256_bytes("\n".join(
            f"{row['path']}:{row.get('sha256', 'special')}"
            for row in sorted(files, key=lambda item: item["path"])
            if not row["path"].endswith("-shm")).encode())
        return {"root": str(state), "files": files, "tree_digest": digest,
                "data_digest": data_digest, "problems": problems}

    def _live_db_rows(self) -> dict:
        state = self.run_dir / "state"
        return {
            "broker": self._safe_query(state / "broker.sqlite3", {
                "reservations":
                    "SELECT reservation_id,route_id,model,status,input_used,"
                    "output_used,cost,estimated,settlement_json "
                    "FROM budget_reservations ORDER BY rowid",
                "claims":
                    "SELECT call_id,reservation_id,request_digest,status "
                    "FROM budget_dispatch_claims ORDER BY rowid",
                "messages":
                    "SELECT COUNT(*) AS n FROM budget_broker_messages",
            }),
            "attempts": self._safe_query(state / "attempts.sqlite3", {
                "attempts":
                    "SELECT attempt_id,call_id,reservation_id,state,receipt_id,"
                    "reason,prepared_digest,payload_digest,logical_step,mode,"
                    "input_bound_tokens FROM g3b_attempts "
                    "ORDER BY created_utc, call_id",
                "admissions":
                    "SELECT admission_id,run_id,consumed_utc "
                    "FROM g3b_admissions ORDER BY consumed_utc",
                "intents":
                    "SELECT intent_id,call_id,reservation_id,state,reason "
                    "FROM g3b_send_intents ORDER BY created_utc",
                "identities":
                    "SELECT scope_id,identity_digest,call_id,logical_step "
                    "FROM g3b_request_identities ORDER BY created_utc",
            }),
        }

    @staticmethod
    def _safe_query(path: Path, statements: dict) -> dict:
        if not path.is_file():
            return {"error": "missing", "rows": {}}
        rows: dict = {}
        errors: list[str] = []
        try:
            # Live WAL reads need a read/write handle to attach the existing
            # -shm; it never writes DB/WAL pages, and -shm is excluded from the
            # data digest compared by D2-01/02/03.
            connection = sqlite3.connect(f"file:{path}?mode=rw", uri=True,
                                         timeout=5)
            connection.row_factory = sqlite3.Row
            try:
                for name, sql in statements.items():
                    try:
                        rows[name] = [dict(row) for row in
                                      connection.execute(sql).fetchall()]
                    except sqlite3.Error as exc:
                        errors.append(f"{name}:{type(exc).__name__}")
            finally:
                connection.close()
        except sqlite3.Error as exc:
            return {"error": f"{type(exc).__name__}", "rows": rows,
                    "errors": errors}
        return {"rows": rows, "errors": errors}

    def _snapshot(self, label: str, *, query_first: bool) -> dict:
        if query_first:
            db = self._live_db_rows()
            tree = self._state_tree()
        else:
            tree = self._state_tree()
            db = self._live_db_rows()
        receipts = self._state_receipts()
        document = {
            "schema": "m0.g3d.d2.state-snapshot.v1",
            "utc": utc(), "label": label, "case": self.case_key,
            "tree_digest": tree["tree_digest"],
            "data_digest": tree["data_digest"], "files": tree["files"],
            "tree_problems": tree["problems"],
            "db": db, "receipts": receipts,
        }
        self.snapshots[label] = document
        self.write_evidence_json(f"state/{label}.json", document)
        return document

    def _state_receipts(self) -> dict:
        state = self.run_dir / "state"
        receipts: list[dict] = []
        counter = None
        errors: list[str] = []
        folder = state / "receipts"
        if folder.is_dir():
            for path in sorted(folder.glob("rcpt-*.json"))[:64]:
                try:
                    data = lib.read_regular_bytes(path, max_bytes=4 << 20)
                    document = json.loads(data.decode("utf-8"))
                except (lib.G3DError, OSError, UnicodeDecodeError,
                        json.JSONDecodeError) as exc:
                    errors.append(f"{path.name}:{type(exc).__name__}")
                    continue
                receipts.append({
                    "name": path.name, "sha256": lib.sha256_bytes(data),
                    "receipt_id": document.get("receipt_id"),
                    "raw_sha256": document.get("raw_sha256"),
                    "mode": document.get("mode"),
                    "usage": document.get("usage"),
                    "nonce": document.get("nonce"),
                    "synthetic": document.get("synthetic"),
                })
        counter_path = folder / "received-count.json"
        if counter_path.is_file():
            try:
                counter = json.loads(lib.read_regular_bytes(
                    counter_path, max_bytes=1 << 16).decode("utf-8"))
            except (lib.G3DError, OSError, UnicodeDecodeError,
                    json.JSONDecodeError) as exc:
                counter = {"error": type(exc).__name__}
        return {"receipts": receipts, "counter": counter,
                "count": len(receipts), "errors": errors}

    # -- collect / evaluate --------------------------------------------
    def _copy_candidate_evidence(self) -> None:
        if not self.candidate_started:
            self.records["candidate_evidence"] = {"skipped": True,
                                                  "reason": "no candidate run"}
            return
        super()._copy_candidate_evidence()

    def collect(self) -> None:
        self._stop_aux()
        super().collect()

    def cleanup(self) -> None:
        try:
            self._stop_aux()
        finally:
            super().cleanup()

    def _copy_runtime_identity_files(self) -> None:
        super()._copy_runtime_identity_files()

    # -- evaluation -----------------------------------------------------
    def evaluate_d2(self) -> None:
        checks: list[dict] = []
        common = CaseChecks("common")
        trusted = self.container_records.get("trusted") or {}
        trusted_exit = trusted.get("exit_code")
        allowed_trusted_exit = self.spec.get("allow_trusted_exit")
        if allowed_trusted_exit is None:
            allowed_trusted_exit = 0
        common.add("trusted_exit_expected", trusted_exit == allowed_trusted_exit,
                   observed=trusted_exit, expected=allowed_trusted_exit)
        socket_before = self.socket_records.get("before_candidate") or {}
        common.add("socket_stat_0660_root_2000",
                   socket_before.get("type") == "socket"
                   and socket_before.get("mode") == lib.SOCKET_MODE
                   and socket_before.get("uid") == 0
                   and socket_before.get("gid") == lib.GROUP_SOCKET,
                   socket=socket_before)
        peercred = self._read_json_evidence("peercred/trusted-log.json") or {}
        candidate_identity = self.runtime_identity.get("candidate") or {}
        if not candidate_identity:
            candidate_identity = self._probe_identity()
        credentials = candidate_identity.get("credentials") or {}
        status = candidate_identity.get("status") or {}
        host_uid = credentials.get("uid") or status.get("Uid") or ""
        host_gid = credentials.get("gid") or status.get("Gid") or ""
        cap_eff = credentials.get("cap_eff") or status.get("CapEff") or ""
        if credentials:
            uid_ok = (str(host_uid).split()[:1] == ["65534"]
                      and str(host_gid).split()[:1] == ["65534"])
            uid_source = "host /proc/<candidate_pid>/status"
        else:
            uid_ok = ((candidate_identity.get("uid_map") or "").split() ==
                      ["0", "65534", "1"]
                      and ["0", "65534", "1"] in
                      [line.split() for line in
                       (candidate_identity.get("gid_map") or "").splitlines()])
            uid_source = "aux container /proc/self/uid_map (kernel uid_map)"
        common.add("candidate_host_uid_65534", uid_ok,
                   source=uid_source, credentials=credentials,
                   uid_map=candidate_identity.get("uid_map"))
        common.add("candidate_cap_eff_zero",
                   cap_eff == "0000000000000000",
                   cap_eff=cap_eff)
        common.add("candidate_uid_map",
                   (candidate_identity.get("uid_map") or "").split() == ["0", "65534", "1"],
                   uid_map=candidate_identity.get("uid_map"))
        mountinfo = candidate_identity.get("mountinfo") or ""
        points = {}
        for line in mountinfo.splitlines():
            fields = line.split()
            if len(fields) > 4:
                points[fields[4]] = fields[5]
        if self.case_key == "d2-13":
            common.add("control_state_mount_is_the_control_variable", True,
                       control_only=True)
        else:
            common.add("candidate_no_state_mount",
                       "/work/state" not in points and "/output" not in points,
                       mount_points=sorted(points))
        rootfs_now = lib.sha256_tree(lib.ROOTFS)
        deps_now = lib.sha256_tree(lib.DEPS)
        stage_now = lib.sha256_tree(self.stage_dir)
        stage_expected = (self.records.get("stage") or {}).get("sha256")
        common.add("canonical_rootfs_deps",
                   rootfs_now == lib.ROOTFS_CANON and deps_now == lib.DEPS_CANON,
                   rootfs={"sha256": rootfs_now, "expected": lib.ROOTFS_CANON},
                   deps={"sha256": deps_now, "expected": lib.DEPS_CANON})
        common.add("stage_tree_unchanged",
                   stage_expected is not None and stage_now == stage_expected,
                   sha256=stage_now, expected=stage_expected)
        case = self._judge_case(peercred=peercred, socket_before=socket_before,
                                candidate_identity=candidate_identity)
        checks.extend(common.items)
        checks.extend(case.items)
        ledger = self._final_ledger()
        self.write_evidence_json("db/final.json", ledger)
        self.write_evidence_json("receipt/final-summary.json", {
            "receipts": ledger["receipts"], "counter": ledger["counter"],
            "count": len(ledger["receipts"])})
        self.checks = checks
        failures = [item["id"] for item in checks if not item["ok"]]
        self.records["checks"] = checks
        self.records["evaluation_failures"] = failures
        self.write_evidence_json("run/checks.json",
                                 {"checks": checks, "failures": failures})
        case_document = {
            "schema": "m0.g3d.d2.case.v1",
            "case": self.case_key, "utc": utc(),
            "status": "PASS" if not failures else "FAIL",
            "failure_count": len(failures), "failures": failures,
            "checks": checks,
            "snapshots": {name: {"tree_digest": value["tree_digest"],
                                 "receipts": value["receipts"]["count"],
                                 "counter": value["receipts"]["counter"],
                                 "rows": self._snapshot_counts(value)}
                          for name, value in self.snapshots.items()},
            "probes": self.probes,
            "probe_records": self.probe_records,
            "aux_records": self.aux_records,
            "candidate_runs": [{key: value for key, value in run.items()
                                if key != "result"} for run in self.candidate_runs],
            "peercred": peercred,
            "final_ledger_counts": {
                "reservations": len(ledger["reservations"]),
                "claims": len(ledger["claims"]),
                "attempts": len(ledger["attempts"]),
                "admissions": len(ledger["admissions"]),
                "receipts": len(ledger["receipts"]),
                "counter": ledger["counter"],
            },
        }
        self.write_evidence_json("d2/case.json", case_document)
        if failures and self.exit_code == lib.EXIT_OK:
            self.exit_code = lib.EXIT_CASE_FAILED
            self.failure = {"reason": "CASE_FAILED",
                            "message": f"D2 {self.case_key} assertions failed",
                            "detail": {"failures": failures}}

    def _probe_identity(self) -> dict:
        for name in ("control:control", "stale:stale"):
            document = self._probe(name) or {}
            identity = document.get("identity")
            if isinstance(identity, dict) and identity:
                return identity
        return {}

    @staticmethod
    def _snapshot_counts(snapshot: dict) -> dict:
        db = snapshot.get("db") or {}
        broker = (db.get("broker") or {}).get("rows") or {}
        attempts = (db.get("attempts") or {}).get("rows") or {}
        receipts = snapshot.get("receipts") or {}
        return {
            "reservations": len(broker.get("reservations") or []),
            "claims": len(broker.get("claims") or []),
            "attempts": len(attempts.get("attempts") or []),
            "admissions": len(attempts.get("admissions") or []),
            "identities": len(attempts.get("identities") or []),
            "receipts": receipts.get("count"),
            "counter": receipts.get("counter"),
        }

    # -- judges ---------------------------------------------------------
    def _judge_case(self, **context) -> CaseChecks:
        checks = CaseChecks(self.case_key)
        key = self.case_key.replace("-", "_")
        if key == "d2_10_trusted_receipt":
            key = "d2_10_trusted"
        judge = getattr(self, "_judge_" + key, None)
        if judge is None:
            checks.add("judge_implemented", False, case=self.case_key)
            return checks
        judge(checks, **context)
        return checks

    def _probe(self, name: str) -> dict | None:
        return self.probes.get(name)

    def _probe_exit_ok(self, checks: CaseChecks, name: str) -> None:
        record = self.probe_records.get(name) or {}
        expected = record.get("expect_exit", 0)
        checks.add(f"probe_exit:{name}", record.get("exit") == expected,
                   exit=record.get("exit"), expected=expected,
                   document_present=record.get("document_present"))

    def _deny_probe_ops(self, checks: CaseChecks, name: str,
                        op_ids: list[str], *,
                        allowed: frozenset[int] = frozenset({2})) -> None:
        document = self._probe(name)
        for op_id in op_ids:
            checks.denied(document, op_id, allowed=allowed,
                          cid=f"{name}:{op_id}")

    def _frames_finish(self, checks: CaseChecks, cid: str,
                       exchange: dict | None) -> None:
        document = exchange or {}
        frames = document.get("frames") or []
        kinds = [frame.get("kind") for frame in frames if isinstance(frame, dict)]
        error_code = document.get("error_code")
        checks.add(cid, document.get("terminal") == "finish"
                   and error_code is None and "ack" in kinds,
                   terminal=document.get("terminal"), error_code=error_code,
                   kinds=kinds[:12])

    def _negative_codes(self, checks: CaseChecks, name: str,
                        expected: dict[str, str]) -> None:
        document = self._probe(name) or {}
        observed = {item.get("id"): item for item in document.get("negatives") or []}
        for neg_id, code in expected.items():
            item = observed.get(neg_id) or {}
            checks.add(f"{name}:neg:{neg_id}", item.get("error_code") == code,
                       observed=item.get("error_code"), expected=code,
                       terminal=item.get("terminal"))

    def _snapshot_unchanged(self, checks: CaseChecks, first: str = "pre",
                            second: str = "final") -> None:
        pre = self.snapshots.get(first) or {}
        post = self.snapshots.get(second) or {}
        checks.add(f"state_hash_unchanged:{first}->{second}",
                   bool(pre) and bool(post)
                   and pre.get("data_digest") == post.get("data_digest"),
                   pre=pre.get("data_digest"), post=post.get("data_digest"),
                   note="excludes SQLite -shm read-mark churn; DB/WAL data included")
        pre_broker = self._file_hash(pre, "broker.sqlite3")
        post_broker = self._file_hash(post, "broker.sqlite3")
        checks.add(f"broker_db_hash_unchanged:{first}->{second}",
                   pre_broker is not None and pre_broker == post_broker,
                   pre=pre_broker, post=post_broker)
        pre_counts = self._snapshot_counts(pre) if pre else {}
        post_counts = self._snapshot_counts(post) if post else {}
        checks.add(f"ledger_rows_unchanged:{first}->{second}",
                   bool(pre) and bool(post) and pre_counts == post_counts,
                   pre=pre_counts, post=post_counts)

    @staticmethod
    def _file_hash(snapshot: dict, suffix: str) -> str | None:
        for row in (snapshot or {}).get("files") or []:
            if str(row.get("path", "")).endswith(suffix):
                return row.get("sha256")
        return None

    def _snapshot_counts_check(self, checks: CaseChecks, label: str,
                               expected: dict) -> None:
        snapshot = self.snapshots.get(label) or {}
        counts = self._snapshot_counts(snapshot) if snapshot else {}
        checks.add(f"snapshot_counts:{label}",
                   all(counts.get(key) == value for key, value in expected.items()),
                   observed=counts, expected=expected)

    # -- D2-01 ----------------------------------------------------------
    def _judge_d2_01(self, checks: CaseChecks, **_context) -> None:
        self._probe_exit_ok(checks, "d2_01")
        document = self._probe("d2_01")
        checks.add("no_state_mount", (document or {}).get("state_mounts") == [],
                   mounts=(document or {}).get("state_mounts"))
        op_ids = [f"open_rdonly:{path}" for path in (
            "/work/state/broker.sqlite3", "/work/state/broker.sqlite3-wal",
            "/work/state/broker.sqlite3-shm", "/state/broker.sqlite3",
            "/output/broker.sqlite3", "/work/state", "/work/state/receipts")]
        self._deny_probe_ops(checks, "d2_01", op_ids)
        search = (document or {}).get("protected_name_search") or {}
        checks.add("no_protected_name_in_candidate_tree",
                   search.get("name_matches") == [],
                   matches=search.get("name_matches"),
                   entries=search.get("entries_visited"))
        self._snapshot_unchanged(checks)

    # -- D2-02 ----------------------------------------------------------
    def _judge_d2_02(self, checks: CaseChecks, **_context) -> None:
        self._probe_exit_ok(checks, "d2_02")
        document = self._probe("d2_02")
        state_paths = ("/work/state/broker.sqlite3",
                       "/work/state/broker.sqlite3-wal",
                       "/work/state/broker.sqlite3-shm",
                       "/state/broker.sqlite3", "/output/broker.sqlite3")
        for path in state_paths:
            for op_id in (f"open_rdwr:{path}", f"open_create:{path}",
                          f"open_truncate:{path}", f"unlink:{path}",
                          f"chmod:{path}", f"replace:{path}",
                          f"hardlink:{path}", f"symlink:{path}"):
                checks.denied(document, op_id,
                              allowed=frozenset({2, 13, 18, 30}),
                              cid=f"d2_02:{op_id}")
        checks.denied(document, "open_dir_rdwr:/work/state",
                      allowed=frozenset({2, 13}), cid="d2_02:open_state_dir")
        checks.denied(document, "create_dir:/work/state/candidate",
                      allowed=frozenset({2, 13, 30}),
                      cid="d2_02:create_state_dir")
        self._snapshot_unchanged(checks)

    # -- D2-03 ----------------------------------------------------------
    def _judge_d2_03(self, checks: CaseChecks, **_context) -> None:
        self._probe_exit_ok(checks, "d2_03")
        document = self._probe("d2_03")
        for entry in (document or {}).get("classes") or []:
            label = entry.get("class")
            for op in entry.get("ops") or []:
                checks.add(f"d2_03:{label}:{op.get('id')}",
                           op.get("ok") is False
                           and op.get("errno") in {2, 13, 30},
                           observed=describe_errno(op))
        checks.add("d2_03:class_count",
                   len((document or {}).get("classes") or []) >= 10,
                   count=len((document or {}).get("classes") or []))
        self._snapshot_unchanged(checks)

    # -- D2-04 ----------------------------------------------------------
    def _judge_d2_04(self, checks: CaseChecks, **_context) -> None:
        self._probe_exit_ok(checks, "d2_04")
        document = self._probe("d2_04") or {}
        imports = document.get("imports") or []
        checks.add("d2_04:no_trusted_module_import",
                   bool(imports) and all(item.get("imported") is False
                                         and item.get("find_spec") is None
                                         for item in imports),
                   imports=[{"module": item.get("module"),
                             "imported": item.get("imported"),
                             "find_spec": item.get("find_spec")}
                            for item in imports])
        for op_id in ("open:/project/src/autoteacher_m0/accounting/broker.py",
                      "open:/project/src/autoteacher_m0/bridge/controller.py",
                      "open:/project/trusted/run/trusted_entry.py",
                      "open:/project/run/trusted_entry.py",
                      "open:/project/fake/fake_provider.py",
                      "open:/work/state/broker.sqlite3"):
            checks.denied(document, op_id, cid="d2_04:" + op_id)
        for op_id in ("connect:/work/g3b/broker.sock",
                      "connect:/work/g3b/controller.sock",
                      "connect:/work/private/controller.sock",
                      "connect:/work/state/controller.sock"):
            checks.denied(document, op_id, cid="d2_04:" + op_id)
        subprocess_op = find_op(document, "import_via_subprocess")
        checks.add("d2_04:subprocess_import_fails",
                   bool(subprocess_op) and subprocess_op.get("ok") is True
                   and (subprocess_op.get("result") or {}).get("exit") != 0,
                   observed=subprocess_op)
        checks.add("d2_04:no_broker_code_in_stage",
                   (document.get("code_search") or {}).get("name_matches") == [],
                   matches=(document.get("code_search") or {}).get("name_matches"))
        proc = document.get("proc") or {}
        checks.add("d2_04:only_own_process_visible",
                   len(proc) <= 3 and all(item.get("cmdline") for item in proc.values()),
                   pids=sorted(proc))
        fd_targets = [row.get("target") or "" for row in
                      document.get("fd_targets") or []]
        checks.add("d2_04:no_trusted_fd_visible",
                   not any("/work/state" in target or "/output" in target
                           for target in fd_targets),
                   fd_targets=fd_targets)
        for op_id in ("read_trusted_environ", "read_trusted_fd",
                      "read_trusted_root", "read_trusted_cwd",
                      "read_trusted_cmdline", "read_trusted_status"):
            if find_op(document, op_id) is not None:
                checks.denied(document, op_id, cid="d2_04:" + op_id)
        self._snapshot_unchanged(checks)

    # -- D2-05 ----------------------------------------------------------
    def _judge_d2_05(self, checks: CaseChecks, **_context) -> None:
        self._probe_exit_ok(checks, "d2_05_negatives")
        self._probe_exit_ok(checks, "d2_05_positive")
        self._negative_codes(checks, "d2_05_negatives", {
            "broker_kind_reserve": "UNKNOWN_KIND",
            "broker_kind_claim": "UNKNOWN_KIND",
            "broker_kind_settle": "UNKNOWN_KIND",
            "payload_reservation_id": "UNKNOWN_FIELD",
            "payload_claim_id": "UNKNOWN_FIELD",
            "payload_authorized": "UNKNOWN_FIELD",
            "payload_dispatch_allowed": "UNKNOWN_FIELD",
            "envelope_dispatch_allowed": "UNKNOWN_FIELD",
        })
        document = self._probe("d2_05_negatives") or {}
        for op_id in (f"connect_broker:{path}" for path in (
                "/work/g3b/broker.sock", "/work/g3b/controller.sock",
                "/work/private/controller.sock", "/work/state/broker.sock")):
            checks.denied(document, op_id, cid="d2_05:" + op_id)
        unlink = (document.get("socket_unlink") or {})
        checks.add("d2_05:unlink_bridge",
                   unlink.get("ok") is False
                   and unlink.get("errno") in {30, 13},
                   observed=describe_errno(unlink))
        self._snapshot_counts_check(checks, "negatives",
                                    {"reservations": 0, "claims": 0,
                                     "attempts": 0, "receipts": 0})
        positive = self._probe("d2_05_positive") or {}
        self._frames_finish(checks, "d2_05:positive_finish",
                            positive.get("positive"))
        self._snapshot_counts_check(checks, "positive",
                                    {"reservations": 1, "claims": 1,
                                     "attempts": 1, "receipts": 1})
        checks.add("d2_05:counter_one_after_positive",
                   ((self.snapshots.get("positive") or {}).get("receipts") or {})
                   .get("counter") == {"count": 1},
                   counter=((self.snapshots.get("positive") or {}).get("receipts") or {})
                   .get("counter"))

    # -- D2-06 ----------------------------------------------------------
    def _judge_d2_06(self, checks: CaseChecks, **_context) -> None:
        self._probe_exit_ok(checks, "d2_06_negatives")
        self._probe_exit_ok(checks, "d2_06_positive")
        expected = {
            "envelope_authorized": "UNKNOWN_FIELD",
            "envelope_admission": "UNKNOWN_FIELD",
            "payload_call_id": "UNKNOWN_FIELD",
            "payload_reservation_id": "UNKNOWN_FIELD",
            "payload_admission_id": "UNKNOWN_FIELD",
            "payload_authorized": "UNKNOWN_FIELD",
            "payload_approved_payload": "UNKNOWN_FIELD",
            "payload_request_digest": "UNKNOWN_FIELD",
            "payload_route_provider": "ROUTE_MISMATCH",
            "payload_route_model": "ROUTE_MISMATCH",
            "payload_tools_forged": "ADMISSION_TOOL_SCHEMA_MISMATCH",
            "payload_bad_hash": "PREPARED_DIGEST_MISMATCH",
            "payload_seq_out_of_order": "SEQ_OUT_OF_ORDER",
            "payload_bad_json": "REQUEST_INVALID",
            "payload_duplicate_key": "DUPLICATE_KEY",
            "payload_deep_nesting": "DEPTH_EXCEEDED",
            "payload_oversized": "FRAME_TOO_LARGE",
            "payload_half_frame": "REQUEST_INVALID",
        }
        self._negative_codes(checks, "d2_06_negatives", expected)
        document = self._probe("d2_06_negatives") or {}
        for op in document.get("socket_ops") or []:
            checks.add("d2_06:" + str(op.get("id")),
                       op.get("ok") is False
                       and op.get("errno") in {30, 13, 98, 18},
                       observed=describe_errno(op))
        self._snapshot_counts_check(checks, "negatives",
                                    {"reservations": 0, "claims": 0,
                                     "attempts": 0, "receipts": 0})
        positive = self._probe("d2_06_positive") or {}
        self._frames_finish(checks, "d2_06:positive_finish",
                            positive.get("positive"))
        self._snapshot_counts_check(checks, "positive",
                                    {"reservations": 1, "claims": 1,
                                     "attempts": 1, "receipts": 1})
        stat = positive.get("ipc_stat") or {}
        checks.add("d2_06:bridge_socket_unchanged",
                   stat.get("ok") is True
                   and (stat.get("result") or {}).get("mode") == 0o660
                   and (stat.get("result") or {}).get("gid") == 2000,
                   observed=stat)

    # -- D2-07 ----------------------------------------------------------
    def _judge_d2_07(self, checks: CaseChecks, **_context) -> None:
        self._probe_exit_ok(checks, "d2_07")
        document = self._probe("d2_07") or {}
        for op_id in ("socket_af_inet", "socket_af_inet6",
                      "socket_af_inet_udp"):
            checks.denied(document, op_id, allowed=frozenset({1, 13}),
                          cid="d2_07:" + op_id)
        # AF_NETLINK is a local kernel interface inside the Candidate's own net
        # namespace; record the real result but do not conflate it with egress.
        netlink = find_op(document, "socket_af_netlink")
        checks.add("d2_07:netlink_local_only",
                   netlink is not None,
                   observed=describe_errno(netlink or {}),
                   note="no external route/interface besides lo")
        for op in document.get("ops") or []:
            if op.get("id", "").startswith("connect_"):
                checks.add("d2_07:" + op["id"],
                           op.get("ok") is False
                           and op.get("errno") in {1, 13, 101, 2, 111},
                           observed=describe_errno(op))
        dns = [op for op in document.get("ops") or []
               if op.get("id", "").startswith("dns_")]
        checks.add("d2_07:dns_denied",
                   bool(dns) and all(op.get("ok") is False for op in dns),
                   dns=[{"id": op.get("id"), "observed": describe_errno(op)}
                        for op in dns])
        interfaces = document.get("interfaces")
        checks.add("d2_07:only_loopback",
                   interfaces == ["lo"], interfaces=interfaces)
        routes = document.get("routes") or []
        default_routes = []
        for line in routes:
            if not isinstance(line, str):
                continue
            fields = line.split()
            if len(fields) >= 3 and fields[1:3] == ["00000000", "00000000"]:
                default_routes.append(line)
        checks.add("d2_07:no_default_route", not default_routes,
                   default_routes=default_routes)
        unix = {item.get("id"): item for item in document.get("unix") or []}
        for name in ("connect:podman", "connect:docker", "connect:systemd_private",
                     "connect:dbus"):
            item = unix.get(name) or {}
            checks.add("d2_07:" + name,
                       item.get("ok") is False
                       and item.get("errno") in {2, 13, 30, 111},
                       observed=describe_errno(item))
        checks.succeeded(document, "connect:bridge", key="unix",
                         cid="d2_07:approved_socket_only")
        for name in ("connect:podman_abstract", "connect:docker_abstract"):
            item = next((row for row in document.get("abstract") or []
                         if row.get("id") == name), None) or {}
            checks.add("d2_07:" + name,
                       item.get("ok") is False
                       and item.get("errno") in {2, 13, 111},
                       observed=describe_errno(item))
        self._snapshot_unchanged(checks)

    # -- D2-08 ----------------------------------------------------------
    def _judge_d2_08(self, checks: CaseChecks, **_context) -> None:
        self._probe_exit_ok(checks, "d2_08")
        document = self._probe("d2_08") or {}
        pre = document.get("pre_unshare_status") or {}
        checks.add("d2_08:cap_eff_zero", pre.get("CapEff") == "0" * 16,
                   cap_eff=pre.get("CapEff"))
        checks.add("d2_08:no_new_privs", pre.get("NoNewPrivs") == "1",
                   no_new_privs=pre.get("NoNewPrivs"))
        checks.add("d2_08:seccomp_enforced", pre.get("Seccomp") == "2",
                   seccomp=pre.get("Seccomp"))
        checks.denied(document, "mount_tmpfs_original_ns",
                      allowed=frozenset({1, 13}), cid="d2_08:mount_denied")
        checks.denied(document, "ptrace_self_init",
                      allowed=frozenset({1, 13}), cid="d2_08:ptrace_self_denied")
        checks.denied(document, "ptrace_trusted_host_pid",
                      allowed=frozenset({3, 1, 2}), cid="d2_08:ptrace_trusted_denied")
        for op_id in ("read_trusted_environ", "read_trusted_fd",
                      "read_trusted_root", "read_trusted_cwd",
                      "read_trusted_cmdline", "read_trusted_status",
                      "read_trusted_maps", "read_trusted_mountinfo"):
            if find_op(document, op_id) is not None:
                checks.denied(document, op_id, cid="d2_08:" + op_id)
        checks.denied(document, "read_proc_kcore",
                      allowed=frozenset({1, 13, 2}), cid="d2_08:kcore_denied")
        keys = find_op(document, "read_proc_keys")
        checks.add("d2_08:no_trusted_keys",
                   keys is not None and (keys.get("ok") is False
                                         or (keys.get("result") or {}).get(
                                             "bytes_read") == 0),
                   observed=keys)
        checks.denied(document, "write_core_pattern",
                      allowed=frozenset({13, 30}), cid="d2_08:core_pattern_denied")
        checks.denied(document, "write_hostname",
                      allowed=frozenset({13, 30}), cid="d2_08:hostname_denied")
        checks.denied(document, "write_sys_kernel_uevent",
                      allowed=frozenset({13, 30}), cid="d2_08:sys_write_denied")
        checks.denied(document, "read_dev_mem",
                      allowed=frozenset({2, 13}), cid="d2_08:dev_mem_denied")
        checks.denied(document, "read_dev_kmsg",
                      allowed=frozenset({2, 13, 30}), cid="d2_08:dev_kmsg_denied")
        checks.denied(document, "write_dev_kmsg",
                      allowed=frozenset({2, 13, 30}),
                      cid="d2_08:dev_kmsg_write_denied")
        checks.denied(document, "read_work_state",
                      allowed=frozenset({2}), cid="d2_08:state_invisible")
        checks.denied(document, "list_work_state",
                      allowed=frozenset({2}), cid="d2_08:state_dir_invisible")
        # /proc/1/environ must only carry the Candidate's own whitelist.
        environ_op = find_op(document, "read_proc_environ_self")
        checks.add("d2_08:proc1_environ_is_candidate_only",
                   environ_op is not None and environ_op.get("ok") is True,
                   observed=environ_op)
        # Nested userns is an observed kernel feature; it must not grant state.
        userns = document.get("userns") or {}
        checks.add("d2_08:nested_userns_observed",
                   isinstance(userns.get("nested_unshare_ok"), bool),
                   userns=userns)
        checks.denied(document, "read_trusted_after_userns",
                      allowed=frozenset({2, 3, 13}),
                      cid="d2_08:userns_no_trusted_gain")
        checks.denied(document, "read_work_state_after_userns",
                      allowed=frozenset({2}), cid="d2_08:userns_no_state_gain")
        checks.denied(document, "setuid_0",
                      allowed=frozenset({1, 13, 22}), cid="d2_08:setuid_denied")
        identity = document.get("identity") or {}
        checks.add("d2_08:uid_map_host_65534",
                   (identity.get("uid_map") or "").split() ==
                   ["0", "65534", "1"], uid_map=identity.get("uid_map"))
        post = document.get("post_unshare_status") or {}
        checks.add("d2_08:nested_userns_never_becomes_host_root",
                   str(post.get("Uid", "")).split()[:1] == ["65534"]
                   and str(post.get("Gid", "")).split()[:1] == ["65534"],
                   post_status={"Uid": post.get("Uid"), "Gid": post.get("Gid"),
                                "CapEff": post.get("CapEff")},
                   note="full caps in the child userspace namespace; host UID "
                        "remains 65534 and CapBnd is the nested namespace bound")

    # -- D2-09 ----------------------------------------------------------
    def _judge_d2_09(self, checks: CaseChecks, **_context) -> None:
        self._probe_exit_ok(checks, "d2_09_negatives")
        self._probe_exit_ok(checks, "d2_09_positive")
        document = self._probe("d2_09_negatives") or {}
        tool = document.get("local_tool") or {}
        checks.add("d2_09:local_tool_allowed_inside_sandbox",
                   tool.get("ok") is True
                   and (tool.get("result") or {}).get("exit") == 0
                   and "D2_LOCAL_TOOL_OK" in str((tool.get("result") or {}).get("stdout")),
                   tool=tool)
        plugin = document.get("plugin") or {}
        checks.add("d2_09:local_plugin_injection_is_local_only",
                   plugin.get("local_only") is True
                   and (plugin.get("approve") or {}).get("authorized") is True,
                   plugin=plugin)
        forged = document.get("forged_config") or {}
        checks.add("d2_09:forged_admission_file_not_consumed",
                   forged.get("used_by_trusted_controller") is False
                   and bool(forged.get("sha256")),
                   forged=forged)
        for op_id in ("read_trusted_config:/work/state/admission.json",
                      "read_trusted_config:/work/state/controller.json",
                      "read_trusted_config:/work/state/policy.json"):
            checks.denied(document, op_id, cid="d2_09:" + op_id)
        self._negative_codes(checks, "d2_09_negatives", {
            "payload_authorized": "UNKNOWN_FIELD",
            "payload_guard": "UNKNOWN_FIELD",
            "payload_admission_id": "UNKNOWN_FIELD",
            "payload_provider_candidate_guard": "ROUTE_MISMATCH",
            "envelope_authorized": "UNKNOWN_FIELD",
        })
        self._snapshot_counts_check(checks, "negatives",
                                    {"reservations": 0, "claims": 0,
                                     "attempts": 0, "receipts": 0})
        positive = self._probe("d2_09_positive") or {}
        self._frames_finish(checks, "d2_09:positive_finish",
                            positive.get("positive"))
        self._snapshot_counts_check(checks, "positive",
                                    {"reservations": 1, "claims": 1,
                                     "attempts": 1, "receipts": 1})
        checks.add("d2_09:trusted_admission_hash_unchanged",
                   (self.snapshots.get("negatives") or {}).get("tree_digest")
                   == (self.snapshots.get("pre") or {}).get("tree_digest"),
                   pre=(self.snapshots.get("pre") or {}).get("tree_digest"),
                   post=(self.snapshots.get("negatives") or {}).get("tree_digest"))

    # -- D2-10 ----------------------------------------------------------
    def _judge_d2_10(self, checks: CaseChecks, **_context) -> None:
        before_send = self.probe_records.get("d2_10_before_send") or {}
        after_send = self.probe_records.get("d2_10_after_send") or {}
        checks.add("d2_10:self_kill_before_send_is_sigkill",
                   before_send.get("exit") == 137, exit=before_send.get("exit"))
        checks.add("d2_10:self_kill_after_send_is_sigkill",
                   after_send.get("exit") == 137, exit=after_send.get("exit"))
        after_ack = self.probe_records.get("d2_10_after_ack") or {}
        checks.add("d2_10:self_kill_after_ack_is_sigkill",
                   after_ack.get("exit") == 137, exit=after_ack.get("exit"))
        half = self._probe("d2_10_half_close") or {}
        half_read = (half.get("ops") or {}).get("read") or {}
        checks.add("d2_10:half_close_rejected",
                   half.get("window") == "half_close"
                   and half_read.get("error_code") == "REQUEST_INVALID",
                   observed=half_read)
        after_chunk = self._probe("d2_10_after_chunk") or {}
        ops = after_chunk.get("ops") or {}
        checks.add("d2_10:disconnect_after_chunk",
                   bool(ops.get("first_chunk"))
                   and ops.get("closed_without_finish") is True,
                   first_chunk=ops.get("first_chunk"))
        reconnect = self._probe("d2_10_reconnect") or {}
        reconnect_read = (reconnect.get("ops") or {}).get("read") or {}
        checks.add("d2_10:resend_same_call_rejected",
                   reconnect_read.get("error_code") in {
                       "ATTEMPT_ALREADY_STARTED", "BROKER_CALL_ID_CONFLICT",
                       "CLAIM_DENIED", "BROKER_IDEMPOTENCY_CONFLICT"},
                   error_code=reconnect_read.get("error_code"))
        self._snapshot_counts_check(checks, "half_close",
                                    {"reservations": 0, "claims": 0,
                                     "attempts": 0, "receipts": 0})
        final = self.snapshots.get("final") or {}
        counts = self._snapshot_counts(final) if final else {}
        reservations = counts.get("reservations")
        checks.add("d2_10:calls_receipts_consistent",
                   isinstance(reservations, int) and 1 <= reservations <= 3
                   and counts.get("claims") == reservations
                   and counts.get("attempts") == reservations
                   and counts.get("receipts") == reservations,
                   counts=counts)
        counter = (final.get("receipts") or {}).get("counter") or {}
        checks.add("d2_10:counter_matches_receipts",
                   counter.get("count") == counts.get("receipts"),
                   counter=counter, receipts=counts.get("receipts"))
        self._assert_no_free_or_duplicate(checks, final)
        self._snapshot_unchanged(checks, "after_chunk", "final")

    def _assert_no_free_or_duplicate(self, checks: CaseChecks,
                                     snapshot: dict) -> None:
        db = snapshot.get("db") or {}
        broker = (db.get("broker") or {}).get("rows") or {}
        attempt_rows = (db.get("attempts") or {}).get("rows") or {}
        reservations = broker.get("reservations") or []
        claims = broker.get("claims") or []
        attempts = attempt_rows.get("attempts") or []
        checks.add("d2_no_duplicate_call_ids",
                   len({row.get("call_id") for row in claims}) == len(claims),
                   call_ids=[row.get("call_id") for row in claims])
        checks.add("d2_no_duplicate_reservations",
                   len({row.get("reservation_id") for row in reservations}) ==
                   len(reservations),
                   reservation_ids=[row.get("reservation_id")
                                    for row in reservations])
        free = [row for row in reservations
                if str(row.get("status")).upper() in {"FREE", "NOT_DISPATCHED"}
                or (row.get("status") == "OK" and float(row.get("cost") or 0) <= 0)]
        checks.add("d2_no_free_or_zero_cost_reservation", not free, rows=free)
        states = [row.get("state") for row in attempts]
        checks.add("d2_attempt_states_conservative_or_settled",
                   all(state in {"ATTEMPT_STARTED", "RESPONSE_OBSERVED",
                                 "SETTLED", "WORST_CASE_HELD",
                                 "SETTLEMENT_UNCERTAIN"} for state in states),
                   states=states)

    # -- D2-10 trusted crash -------------------------------------------
    def _judge_d2_10_trusted(self, checks: CaseChecks, **_context) -> None:
        record = self.probe_records.get("d2_10_trusted") or {}
        checks.add("d2_10_trusted:probe_exit", record.get("exit") == 0,
                   exit=record.get("exit"))
        document = self._probe("d2_10_trusted") or {}
        ops = document.get("ops") or {}
        read = ops.get("read") or {}
        checks.add("d2_10_trusted:eof_without_finish",
                   read.get("terminal") not in {"finish", "error"}
                   and ops.get("eof_without_finish") is True,
                   read=read, eof=ops.get("eof_without_finish"))
        reconnect = ops.get("reconnect") or {}
        checks.add("d2_10_trusted:no_reconnect_resend",
                   reconnect.get("ok") is False
                   and reconnect.get("errno") in {2, 111, 32, 104},
                   reconnect=reconnect)
        final = self.snapshots.get("final") or {}
        counts = self._snapshot_counts(final) if final else {}
        checks.add("d2_10_trusted:single_reservation_attempt",
                   counts.get("reservations") == 1
                   and counts.get("attempts") == 1,
                   counts=counts)
        final_db = final.get("db") or {}
        broker = (final_db.get("broker") or {}).get("rows") or {}
        attempt_rows = (final_db.get("attempts") or {}).get("rows") or {}
        attempts = attempt_rows.get("attempts") or []
        reservations = broker.get("reservations") or []
        states = [row.get("state") for row in attempts]
        checks.add("d2_10_trusted:conservative_attempt_state",
                   bool(states) and all(state in {
                       "ATTEMPT_STARTED", "RESPONSE_OBSERVED",
                       "SETTLEMENT_UNCERTAIN", "WORST_CASE_HELD"}
                       for state in states), states=states)
        checks.add("d2_10_trusted:reservation_not_settled",
                   bool(reservations) and all(
                       str(row.get("status")).upper() not in {"OK", "FREE",
                                                              "NOT_DISPATCHED"}
                       for row in reservations),
                   statuses=[row.get("status") for row in reservations])
        receipts = (final.get("receipts") or {})
        if self.spec.get("crash_hook") == "after_response_before_settlement":
            checks.add("d2_10_trusted:receipt_preserved",
                       receipts.get("count") == 1
                       and (receipts.get("counter") or {}).get("count") == 1,
                       receipts=receipts)
        else:
            checks.add("d2_10_trusted:no_fake_send",
                       receipts.get("count") == 0,
                       receipts=receipts)

    # -- D2-11 Echo / Tool ---------------------------------------------
    def _judge_d2_11_echo(self, checks: CaseChecks, **_context) -> None:
        super().evaluate()
        checks.items.extend(self.checks)
        checks.add("d2_11_echo:ledger_complete",
                   len(self.checks) >= 29 and not [item for item in self.checks
                                                    if not item["ok"]],
                   check_count=len(self.checks),
                   failures=[item["id"] for item in self.checks if not item["ok"]])

    def _judge_d2_11_tool(self, checks: CaseChecks, **_context) -> None:
        super().evaluate()
        checks.items.extend(self.checks)
        checks.add("d2_11_tool:ledger_complete",
                   len(self.checks) >= 33 and not [item for item in self.checks
                                                    if not item["ok"]],
                   check_count=len(self.checks),
                   failures=[item["id"] for item in self.checks if not item["ok"]])

    # -- D2-11 Resume ---------------------------------------------------
    def _judge_d2_11_resume(self, checks: CaseChecks, **_context) -> None:
        turns = {run["label"]: run for run in self.candidate_runs}
        turn1 = turns.get("turn1") or {}
        turn2 = turns.get("turn2") or {}
        result1 = turn1.get("result") or {}
        result2 = turn2.get("result") or {}
        for label, run in (("turn1", turn1), ("turn2", turn2)):
            checks.add(f"d2_11_resume:{label}_exit",
                       run.get("exit_code") == 0, exit=run.get("exit_code"))
            checks.add(f"d2_11_resume:{label}_final_ok",
                       run.get("result", {}).get("final_response") == "ok"
                       and run.get("result", {}).get("finish_reason") == "completed",
                       final_response=run.get("result", {}).get("final_response"),
                       finish_reason=run.get("result", {}).get("finish_reason"))
        resume = result2.get("resume") or {}
        sessions = resume.get("sessions") or {}
        checks.add("d2_11_resume:sdk_resume_used",
                   resume.get("used") is True
                   and resume.get("sdk_call") == "resume_session",
                   resume=resume)
        checks.add("d2_11_resume:persisted_session_marker",
                   int(sessions.get("resume_marker_count") or 0) >= 1,
                   marker_count=sessions.get("resume_marker_count"),
                   files=sessions.get("files"))
        lines1 = ((result1.get("resume") or {}).get("sessions") or {}).get(
            "total_lines", 0)
        lines2 = sessions.get("total_lines", 0)
        checks.add("d2_11_resume:session_grew_across_processes",
                   int(lines2) > int(lines1), lines_turn1=lines1,
                   lines_turn2=lines2)
        checks.add("d2_11_resume:new_process",
                   bool(turn1.get("container"))
                   and turn1.get("container") != turn2.get("container"),
                   containers=[turn1.get("container"), turn2.get("container")])
        ledger = self._final_ledger()
        reservations = ledger["reservations"]
        claims = ledger["claims"]
        attempts = ledger["attempts"]
        receipts = ledger["receipts"]
        checks.add("d2_11_resume:two_of_each",
                   len(reservations) == 2 and len(claims) == 2
                   and len(attempts) == 2 and len(receipts) == 2
                   and len(ledger["admissions"]) == 1,
                   reservations=len(reservations), claims=len(claims),
                   attempts=len(attempts), receipts=len(receipts),
                   admissions=len(ledger["admissions"]))
        checks.add("d2_11_resume:no_replay_of_old_attempt",
                   len({row.get("call_id") for row in attempts}) == 2
                   and len({row.get("attempt_id") for row in attempts}) == 2,
                   call_ids=[row.get("call_id") for row in attempts])
        checks.add("d2_11_resume:counter_two",
                   ledger["counter"] == {"count": 2}, counter=ledger["counter"])
        checks.add("d2_11_resume:all_settled_positive_cost",
                   all(row.get("state") == "SETTLED" for row in attempts)
                   and all(row.get("status") == "OK" for row in reservations),
                   reservation_status=[row.get("status") for row in reservations],
                   attempt_state=[row.get("state") for row in attempts])
        usages = []
        for attempt in attempts:
            receipt = next((item for item in receipts
                            if item.get("receipt_id") == attempt.get("receipt_id")),
                           None)
            usages.append((attempt.get("logical_step"),
                           None if receipt is None else receipt.get("usage")))
        checks.add("d2_11_resume:distinct_receipts",
                   len({item.get("receipt_id") for item in receipts}) == 2,
                   receipt_ids=[item.get("receipt_id") for item in receipts])
        by_step = {step: usage for step, usage in usages}
        checks.add("d2_11_resume:both_usages_present",
                   isinstance(by_step.get(0), dict)
                   and isinstance(by_step.get(1), dict), usages=usages)
        inputs = {row.get("logical_step"): row.get("input_bound_tokens")
                  for row in attempts}
        checks.add("d2_11_resume:second_request_includes_history",
                   int(inputs.get(1) or 0) > int(inputs.get(0) or 0),
                   input_bounds=inputs)
        self._digest_checks(checks, ledger, receipts, prefix="d2_11_resume")

    # -- D2-12 ----------------------------------------------------------
    def _judge_d2_12(self, checks: CaseChecks, **_context) -> None:
        fork = self._probe("stress:fork") or {}
        ops = fork.get("ops") or {}
        checks.add("d2_12:pids_limit_eagain",
                   isinstance(ops.get("children"), int)
                   and 0 < ops["children"] < 48
                   and (ops.get("error") or {}).get("errno") == 11,
                   children=ops.get("children"), error=ops.get("error"))
        limits = fork.get("limits") or {}
        checks.add("d2_12:cgroup_pids_max_eight",
                   str(limits.get("/sys/fs/cgroup/pids.max")) == "8",
                   pids_max=limits.get("/sys/fs/cgroup/pids.max"))
        checks.add("d2_12:cgroup_memory_max_128m",
                   str(limits.get("/sys/fs/cgroup/memory.max")) == "134217728",
                   memory_max=limits.get("/sys/fs/cgroup/memory.max"))
        checks.add("d2_12:cgroup_cpu_max_present",
                   isinstance(limits.get("/sys/fs/cgroup/cpu.max"), str)
                   and len(limits.get("/sys/fs/cgroup/cpu.max").split()) == 2,
                   cpu_max=limits.get("/sys/fs/cgroup/cpu.max"))
        memory_record = self.probe_records.get("stress:memory") or {}
        memory_doc = self._probe("stress:memory") or {}
        memory_ops = memory_doc.get("ops") or {}
        checks.add("d2_12:memory_limit_enforced",
                   memory_record.get("exit") == 137
                   or isinstance(memory_ops.get("error"), dict)
                   or (memory_ops.get("allocated_mb") or 0) >= 128,
                   exit=memory_record.get("exit"),
                   allocated_mb=memory_ops.get("allocated_mb"),
                   error=memory_ops.get("error"))
        fd_doc = self._probe("stress:fd") or {}
        fd_ops = fd_doc.get("ops") or {}
        checks.add("d2_12:fd_limit_emfile",
                   (fd_ops.get("error") or {}).get("errno") == 24
                   and 64 < int(fd_ops.get("opened") or 0) <= 8192,
                   opened=fd_ops.get("opened"), error=fd_ops.get("error"))
        conn_doc = self._probe("stress:connections") or {}
        conn_ops = conn_doc.get("ops") or {}
        overload = conn_ops.get("overload") or {}
        checks.add("d2_12:connection_cap_too_many",
                   overload.get("error_code") == "TOO_MANY_CONNECTIONS",
                   observed=overload.get("error_code"))
        checks.add("d2_12:slowloris_held_without_calls",
                   len(conn_ops.get("slowloris") or []) == 8,
                   slowloris=conn_ops.get("slowloris"))
        flood_doc = self._probe("stress:flood") or {}
        flood_ops = flood_doc.get("ops") or {}
        checks.add("d2_12:oversized_frame_rejected",
                   "FRAME_TOO_LARGE" in (flood_ops.get("codes") or {}),
                   codes=flood_ops.get("codes"))
        valid = self._probe("d2_12_valid") or {}
        self._frames_finish(checks, "d2_12:valid_after_stress",
                            valid.get("ops") or {})
        counts = self._snapshot_counts(self.snapshots.get("final") or {})
        checks.add("d2_12:only_valid_request_recorded",
                   counts.get("reservations") == 1
                   and counts.get("attempts") == 1
                   and counts.get("receipts") == 1, counts=counts)
        before = self.records.get("trusted_resources_before") or {}
        after = self.records.get("trusted_resources_after") or {}
        checks.add("d2_12:trusted_fd_threads_released",
                   bool(before) and bool(after)
                   and int(after.get("fds", 0)) <= int(before.get("fds", 0)) + 4
                   and int(after.get("threads", 0)) <= int(before.get("threads", 0)) + 4,
                   before=before, after=after)
        residual = self.records.get("aux_residual") or []
        checks.add("d2_12:no_stress_container_residual", residual == [],
                   residual=residual)

    # -- D2-13 ----------------------------------------------------------
    def _judge_d2_13(self, checks: CaseChecks, **_context) -> None:
        record = self.probe_records.get("control:control") or {}
        checks.add("d2_13:control_container_exit", record.get("exit") == 0,
                   exit=record.get("exit"))
        document = self._probe("control:control") or {}
        checks.add("d2_13:labeled_control",
                   document.get("label") == "CONTROL"
                   and record.get("control_label") == "CONTROL",
                   label=document.get("label"))
        mounts = document.get("state_mounts") or []
        checks.add("d2_13:state_mount_present_read_only",
                   bool(mounts) and all("ro" in str(row.get("mount_options"))
                                        for row in mounts),
                   mounts=mounts)
        for op in document.get("ops") or []:
            op_id = str(op.get("id"))
            if op_id == "stat:/work/state":
                result = op.get("result") or {}
                checks.add("d2_13:" + op_id,
                           op.get("ok") is True
                           and result.get("mode") == 0o700
                           and result.get("is_socket") is False,
                           observed=result,
                           note="metadata is visible; content/listing is denied")
            elif op_id.split(":", 1)[-1] == "/work/state":
                checks.add("d2_13:" + op_id,
                           op.get("ok") is False
                           and op.get("errno") in {13, 21, 30},
                           observed=describe_errno(op))
            else:
                checks.add("d2_13:" + op_id,
                           op.get("ok") is False
                           and op.get("errno") in {13, 30, 2},
                           observed=describe_errno(op))
        self._snapshot_unchanged(checks)

    # -- D2-14 ----------------------------------------------------------
    def _judge_d2_14(self, checks: CaseChecks, **_context) -> None:
        record = self.probe_records.get("stale:stale") or {}
        checks.add("d2_14:stale_container_exit", record.get("exit") == 0,
                   exit=record.get("exit"))
        document = self._probe("stale:stale") or {}
        identity = document.get("identity") or {}
        checks.add("d2_14:same_uid_as_candidate",
                   (identity.get("uid_map") or "").split() == ["0", "65534", "1"]
                   and 2000 in (identity.get("groups") or []),
                   uid_map=identity.get("uid_map"), groups=identity.get("groups"))
        mounts = document.get("ipc_mounts") or []
        stale_record = (self.records.get("stale_ipc") or {}).get("stale_socket") or {}
        stale_stat = find_op(document, "stat_stale_socket") or {}
        observed = stale_stat.get("result") or {}
        checks.add("d2_14:stale_ipc_mount_only",
                   len(mounts) == 1
                   and mounts[0].get("mount_point") == "/work/g3b"
                   and "ro" in str(mounts[0].get("mount_options"))
                   and observed.get("inode") == stale_record.get("inode")
                   and observed.get("mode") == 0o660
                   and observed.get("gid") == 2000,
                   mounts=mounts, observed_socket=observed,
                   host_stale_socket=stale_record["inode"]
                   if stale_record else None)
        checks.denied(document, "connect_stale_socket",
                      allowed=frozenset({111, 2}), cid="d2_14:stale_socket_refused")
        checks.denied(document, "connect_live_host_path",
                      allowed=frozenset({2}), cid="d2_14:live_socket_invisible")
        checks.denied(document, "stat_live_host_path",
                      allowed=frozenset({2}), cid="d2_14:live_socket_stat_invisible")
        checks.denied(document, "connect_live_via_proc_root",
                      allowed=frozenset({2}), cid="d2_14:proc_root_escape_denied")
        checks.denied(document, "connect_relative_escape",
                      allowed=frozenset({2}), cid="d2_14:relative_escape_denied")
        checks.denied(document, "read_trusted_proc",
                      allowed=frozenset({2, 3}), cid="d2_14:trusted_proc_invisible")
        checks.denied(document, "read_work_state",
                      allowed=frozenset({2}), cid="d2_14:state_invisible")
        stale = (self.records.get("stale_ipc") or {}).get("stale_socket") or {}
        checks.add("d2_14:stale_socket_contract",
                   stale.get("type") == "socket" and stale.get("mode") == 0o660
                   and stale.get("gid") == 2000, stale=stale)
        live = (self.records.get("live_socket") or {})
        checks.add("d2_14:live_socket_still_listening",
                   (live.get("stat") or {}).get("type") == "socket"
                   and live.get("listening") is True,
                   live=live)
        live_inode = (live.get("stat") or {}).get("inode")
        checks.add("d2_14:stale_mount_is_not_live_socket",
                   live_inode is not None
                   and observed.get("inode") != live_inode,
                   stale_inode=observed.get("inode"), live_inode=live_inode)
        self._snapshot_unchanged(checks)

    # -- D2-15 ----------------------------------------------------------
    def _judge_d2_15(self, checks: CaseChecks, **_context) -> None:
        super().evaluate()
        checks.items.extend(self.checks)
        checks.add("d2_15:echo_ledger_ok",
                   len(self.checks) >= 29
                   and not [item for item in self.checks if not item["ok"]],
                   check_count=len(self.checks),
                   failures=[item["id"] for item in self.checks if not item["ok"]])
        ledger = self._final_ledger()
        self._digest_checks(checks, ledger, ledger["receipts"], prefix="d2_15")

    # -- shared digest cross-check -------------------------------------
    def _digest_checks(self, checks: CaseChecks, ledger: dict,
                       receipts: list[dict], *, prefix: str) -> None:
        attempts = ledger.get("attempts") or []
        claims = ledger.get("claims") or []
        claims_by_call = {row.get("call_id"): row for row in claims}
        receipts_by_id = {row.get("receipt_id"): row for row in receipts}
        pairs = []
        for attempt in attempts:
            claim = claims_by_call.get(attempt.get("call_id"))
            receipt = receipts_by_id.get(attempt.get("receipt_id"))
            prepared_ok = (claim is not None
                           and claim.get("request_digest") == attempt.get("prepared_digest"))
            payload_ok = (receipt is not None
                          and receipt.get("raw_sha256") == attempt.get("payload_digest"))
            pairs.append({"attempt": attempt.get("attempt_id"),
                          "prepared_ok": prepared_ok, "payload_ok": payload_ok,
                          "prepared": attempt.get("prepared_digest"),
                          "claim_digest": None if claim is None else claim.get("request_digest"),
                          "payload": attempt.get("payload_digest"),
                          "receipt_sha": None if receipt is None else receipt.get("raw_sha256"),
                          "different": attempt.get("prepared_digest") != attempt.get("payload_digest")})
        checks.add(prefix + ":prepared_digest_equals_claim",
                   bool(pairs) and all(item["prepared_ok"] for item in pairs),
                   pairs=pairs)
        checks.add(prefix + ":payload_digest_equals_receipt",
                   bool(pairs) and all(item["payload_ok"] for item in pairs),
                   pairs=pairs)
        hexes = [item["prepared"] for item in pairs] + \
                [item["payload"] for item in pairs]
        checks.add(prefix + ":digest_shape",
                   all(isinstance(value, str) and len(value) == 64
                       and re.fullmatch(r"[0-9a-f]{64}", value)
                       for value in hexes), digests=hexes)
        checks.add(prefix + ":two_pairs_not_merged",
                   all(item["prepared"] != item["payload"] for item in pairs),
                   pairs=[{"prepared": item["prepared"], "payload": item["payload"]}
                          for item in pairs])

    # -- final ledger ---------------------------------------------------
    def _query_file(self, path: Path, sql: str) -> list[dict]:
        if not path.is_file():
            return []
        try:
            connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            connection.row_factory = sqlite3.Row
            try:
                return [dict(row) for row in connection.execute(sql).fetchall()]
            finally:
                connection.close()
        except sqlite3.Error:
            return []

    def _final_ledger(self) -> dict:
        db = self.evidence / "db"
        broker = db / "broker.sqlite3"
        attempts_db = db / "attempts.sqlite3"
        reservations = self._query_file(
            broker, "SELECT reservation_id,route_id,model,status,input_used,"
                    "output_used,cost,estimated,settlement_json "
                    "FROM budget_reservations ORDER BY rowid")
        claims = self._query_file(
            broker, "SELECT call_id,reservation_id,request_digest,status "
                    "FROM budget_dispatch_claims ORDER BY rowid")
        attempts = self._query_file(
            attempts_db, "SELECT attempt_id,call_id,reservation_id,state,receipt_id,"
                         "reason,prepared_digest,payload_digest,run_id,logical_step,"
                         "mode,input_bound_tokens,settlement_json FROM g3b_attempts "
                         "ORDER BY created_utc, call_id")
        admissions = self._query_file(
            attempts_db, "SELECT admission_id,run_id,consumed_utc "
                         "FROM g3b_admissions ORDER BY consumed_utc")
        receipts: list[dict] = []
        receipt_dir = self.evidence / "receipt"
        if receipt_dir.is_dir():
            for path in sorted(receipt_dir.glob("rcpt-*.json")):
                try:
                    document = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                receipts.append({
                    "receipt_id": document.get("receipt_id"),
                    "raw_sha256": document.get("raw_sha256"),
                    "usage": document.get("usage"),
                    "nonce": document.get("nonce"),
                    "name": path.name,
                })
        counter = None
        counter_path = receipt_dir / "received-count.json"
        if counter_path.is_file():
            try:
                counter = json.loads(counter_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                counter = None
        return {"reservations": reservations, "claims": claims,
                "attempts": attempts, "admissions": admissions,
                "receipts": receipts, "counter": counter}

    # -- trusted resource snapshot (D2-12) ------------------------------
    def _trusted_resources(self, label: str) -> dict:
        pid = self.trusted_pid or 0
        record = {"utc": utc(), "trusted_pid": pid}
        try:
            record["fds"] = len(os.listdir(f"/proc/{pid}/fd"))
        except OSError as exc:
            record["fds_error"] = type(exc).__name__
        try:
            record["threads"] = len(os.listdir(f"/proc/{pid}/task"))
        except OSError as exc:
            record["threads_error"] = type(exc).__name__
        self.write_evidence_json(f"d2/trusted-resources-{label}.json", record)
        self.records[f"trusted_resources_{label}"] = record
        return record

    # -- evidence summary ----------------------------------------------
    def write_evidence(self) -> None:
        if not self.evidence_ready:
            return
        cleanup = self.records.get("cleanup") or {}
        canonical = cleanup.get("canonical") or {}
        checks = self.checks
        failures = [item["id"] for item in checks if not item["ok"]]
        summary = {
            "schema": "m0.g3d.d2.summary.v1",
            "utc_start": self.started_utc,
            "utc_end": utc(),
            "run_id": self.run_id,
            "case": self.case_key,
            "scenario": self.args.scenario,
            "kind": self.spec.get("kind"),
            "status": "PASS" if self.exit_code == lib.EXIT_OK and not failures
            else "FAIL",
            "exit_code": self.exit_code,
            "failures": failures,
            "failure": self.failure,
            "errors": self.errors,
            "stage": self.records.get("stage"),
            "configs": self.records.get("configs"),
            "containers": self.container_records,
            "candidate_runs": [{key: value for key, value in run.items()
                                if key != "result"} for run in self.candidate_runs],
            "probe_records": self.probe_records,
            "aux_records": self.aux_records,
            "snapshots": {name: {"tree_digest": value.get("tree_digest"),
                                 "counts": self._snapshot_counts(value)}
                          for name, value in self.snapshots.items()},
            "socket": self.socket_records,
            "checks": checks,
            "cleanup": {"ok": cleanup.get("ok"),
                        "problems": cleanup.get("problems"),
                        "utc_end": cleanup.get("utc_end")},
            "canonical": canonical,
            "synthetic": True,
            "real_model_calls": 0,
            "real_external_http_calls": 0,
            "has_real_key": False,
            "live_gate_status": "BLOCKED",
            "os_boundary_status": "D2_GATE_" + ("PASS" if not failures else "FAIL"),
        }
        self.write_evidence_json("summary.json", summary)
        text = [
            f"RUN_ID={self.run_id}",
            f"CASE={self.case_key}",
            f"STATUS={summary['status']}",
            f"EXIT={self.exit_code}",
            f"UTC_START={self.started_utc}",
            f"UTC_END={summary['utc_end']}",
            "CHECKS:",
            *[f"  {'PASS' if item['ok'] else 'FAIL'} {item['id']}"
              for item in checks],
            f"CHECK_FAILURES={failures}",
            f"CLEANUP_OK={cleanup.get('ok')}",
            f"CLEANUP_PROBLEMS={cleanup.get('problems')}",
        ]
        lib.write_bytes_atomic(self.evidence / "run" / "run-summary.txt",
                               ("\n".join(text) + "\n").encode(), mode=0o444)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True, choices=sorted(CASES))
    parser.add_argument("--sub", default="")
    parser.add_argument("--session", default="g3d-d2-s1")
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
        runner = D2Runner(args)
    except lib.G3DError as exc:
        sys.stderr.write(f"LAUNCH_FAILED {exc.reason}: {exc}\n")
        sys.stderr.write(json.dumps(exc.detail, indent=2, sort_keys=True) + "\n")
        return exc.exit_code
    try:
        runner.preflight()
        runner.create_run()
        runner.write_configs()
        runner.start_trusted()
        if runner.trusted_name:
            trusted_record = runner.container_records.get("trusted") or {}
            runner.trusted_pid = int(trusted_record.get("pid") or 0) or None
        runner._capture_live_socket()
        if runner.spec.get("kind") == "attack":
            runner._trusted_resources("before")
        try:
            runner.run_d2()
            if runner.spec.get("kind") == "attack":
                runner._trusted_resources("after")
            runner.collect()
            runner.evaluate_d2()
        except lib.G3DError as exc:
            runner.failure = {"reason": exc.reason, "message": str(exc),
                              "detail": exc.detail}
            runner.exit_code = exc.exit_code
            runner.record_error(exc.reason, str(exc), **exc.detail)
            try:
                runner.collect()
            except Exception as collect_exc:  # noqa: BLE001
                runner.record_error("COLLECT_FAILED",
                                    f"{type(collect_exc).__name__}: {collect_exc}")
            runner.evaluate_d2()
    except lib.G3DError as exc:
        runner.failure = {"reason": exc.reason, "message": str(exc),
                          "detail": exc.detail}
        runner.exit_code = exc.exit_code
        runner.record_error(exc.reason, str(exc), **exc.detail)
        try:
            runner.collect()
        except Exception as collect_exc:  # noqa: BLE001
            runner.record_error("COLLECT_FAILED",
                                f"{type(collect_exc).__name__}: {collect_exc}")
        try:
            runner.evaluate_d2()
        except Exception as eval_exc:  # noqa: BLE001
            runner.record_error("EVALUATE_FAILED",
                                f"{type(eval_exc).__name__}: {eval_exc}")
    except Exception as exc:  # noqa: BLE001 - never lose evidence
        runner.failure = {"reason": "INTERNAL", "message": str(exc),
                          "traceback": traceback.format_exc()[-4000:]}
        runner.exit_code = lib.EXIT_CASE_FAILED
        runner.record_error("INTERNAL", f"{type(exc).__name__}: {exc}")
        try:
            runner.collect()
        except Exception as collect_exc:  # noqa: BLE001
            runner.record_error("COLLECT_FAILED",
                                f"{type(collect_exc).__name__}: {collect_exc}")
    try:
        runner.cleanup()
    except Exception as exc:  # noqa: BLE001
        runner.record_error("CLEANUP_EXCEPTION", f"{type(exc).__name__}: {exc}")
        if runner.exit_code == lib.EXIT_OK:
            runner.exit_code = lib.EXIT_CLEANUP_RESIDUAL
    try:
        runner.write_evidence()
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"EVIDENCE_WRITE_FAILED {type(exc).__name__}: {exc}\n")
        if runner.exit_code == lib.EXIT_OK:
            runner.exit_code = lib.EXIT_EVIDENCE_INTEGRITY
    print(json.dumps({"run_id": runner.run_id, "case": runner.case_key,
                      "status": "PASS" if runner.exit_code == 0 else "FAIL",
                      "exit": runner.exit_code,
                      "evidence": str(runner.evidence),
                      "failure": runner.failure}, sort_keys=True))
    return runner.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
