#!/usr/bin/env python3
"""Host Launcher for G3-D1-B: two real OS principals over one approved UDS.

Run as host root. The launcher is the only component allowed to create ``$RUN``,
generate synthetic Admission/Broker/Controller config, start/stop Podman
containers and write Launcher readiness. It never acts as the Candidate and
never connects to the socket as a business client.

Sequence (D0 §3.3 / D1 plan §3.6):

    preflight (identity, canonical hashes, stage manifest, env probes, no Key,
               LiveGate BLOCKED, no stale run/socket/container)
    -> create $RUN layout (state 0700, ipc 2750 root:2000, session 0700 65534)
    -> start Trusted, wait for Trusted ready + real socket 0660 root:2000 +
       /proc/<pid>/net/unix LISTEN, then the *launcher* writes launcher-ready
    -> start Candidate (uidmap 0:65534, gidmap 2000:2000, group-add 2000)
    -> collect DSH usage / Fake receipt / Broker / Attempt / uid maps / mounts
    -> stop candidate then trusted (TERM -> bounded KILL), remove containers,
       unlink only the verified socket/lock, delete only $RUN
    -> re-check podman ps -a empty and rootfs/deps/stage canonical.

Any missing/environment-mismatched prerequisite exits BLOCKED without weakening
the boundary. There is no Key, no external network and no LiveGate unlock.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import re
import secrets
import socket
import sqlite3
import stat
import subprocess
import sys
import time
import traceback
import uuid
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib_g3d as lib  # noqa: E402

USERNS_PROBE_CODE = r"""
import errno, json, os, socket

def probe(family, address, timeout=0.5):
    sock = None
    try:
        sock = socket.socket(family, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect(address)
        return {"ok": True, "connected": True}
    except OSError as exc:
        return {"ok": False, "errno": exc.errno,
                "name": errno.errorcode.get(exc.errno, str(exc.errno))}
    finally:
        if sock is not None:
            sock.close()

status = {}
with open("/proc/self/status", "r", encoding="utf-8") as handle:
    for line in handle:
        if ":" in line:
            key, value = line.split(":", 1)
            status[key] = value.strip()
result = {
    "uid": os.getuid(),
    "gid": os.getgid(),
    "groups": os.getgroups(),
    "uid_map": open("/proc/self/uid_map").read().strip(),
    "gid_map": open("/proc/self/gid_map").read().strip(),
    "cap_eff": status.get("CapEff"),
    "no_new_privs": status.get("NoNewPrivs"),
    "seccomp": status.get("Seccomp"),
    "af_inet": probe(socket.AF_INET, ("192.0.2.1", 9)),
    "af_inet6": probe(socket.AF_INET6, ("::1", 9)),
    "so_peercred": hasattr(socket, "SO_PEERCRED"),
    "ifaces": sorted(name for _, name in socket.if_nameindex()),
}
print("G3D_USERNS_PROBE " + json.dumps(result, sort_keys=True))
"""

LIVEGATE_CODE = (
    "import json;"
    "from autoteacher_m0.security.gates import LiveGate;"
    "decision = LiveGate().inspect(live_requested=True);"
    "print(json.dumps({'status': decision.status,"
    " 'reasons': list(decision.reasons)}, sort_keys=True))"
)

KEY_MARKER = re.compile(r"(KEY|TOKEN|SECRET|CREDENTIAL|PASSWORD|AUTH)", re.IGNORECASE)
RUN_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,80}\Z", re.ASCII)
SCENARIO_ADMISSION = {
    "echo": {"fake_scenario": "ok_usage", "max_calls": 1},
    "tool": {"fake_scenario": "tool", "max_calls": 2},
    # D2 attack probes are raw-UDS negative/positive clients inside the real
    # Candidate container; they need several independent calls per Run.
    "attack": {"fake_scenario": "ok_usage", "max_calls": 8},
    # D2-11 Resume is exactly two real DSH turns in one persisted session.
    "resume": {"fake_scenario": "ok_usage", "max_calls": 2},
    # D3 recovery/cancel/deadline scenarios. Each one is an explicit synthetic
    # admission override; no product default or protocol field is changed.
    "stream": {"fake_scenario": "stream_slow", "max_calls": 1},
    "cancel": {"fake_scenario": "slow_usage", "max_calls": 8,
               "deadline_ms": 15000},
    "deadline_broker": {"fake_scenario": "ok_usage", "max_calls": 2,
                        "deadline_ms": 2500},
    "deadline_fake": {"fake_scenario": "timeout", "max_calls": 1,
                      "deadline_ms": 3500},
    "deadline_stall": {"fake_scenario": "slow_usage", "max_calls": 1,
                       "deadline_ms": 800},
    "recover": {"fake_scenario": "ok_usage", "max_calls": 2},
    "same_claim": {"fake_scenario": "ok_usage", "max_calls": 2},
    "c11": {"fake_scenario": "ok_usage", "max_calls": 2},
}
SCENARIO_PROMPT = {
    "echo": "G3D_ECHO",
    "tool": "Use skill_lookup to look up binary_search",
    "attack": "G3D_D2_ATTACK",
    "resume": "G3D_RESUME_ALPHA 7f3a9c",
    "stream": "G3D_STREAM_EARLY_CHUNK",
    "cancel": "G3D_CANCEL_STREAM",
    "deadline_broker": "G3D_DEADLINE_BROKER",
    "deadline_fake": "G3D_DEADLINE_FAKE",
    "deadline_stall": "G3D_DEADLINE_STALL",
    "recover": "G3D_RECOVER_REQUEST",
    "same_claim": "G3D_SAME_CLAIM",
    "c11": "G3D_C11_SAME_REQUEST_7c1e",
}
REQUIRED_CONTROLLER_KEYS = {
    "admission_path", "broker_config_path", "fake_script", "receipt_dir",
    "attempt_db", "socket_path", "python", "expected_uid",
}


def scenario_admission(scenario: str) -> dict:
    """Return the frozen per-scenario admission overrides.

    Echo keeps one provider request; Tool needs exactly two independent
    provider requests inside one real Turn (tool_once -> tool_final).
    """
    if scenario not in SCENARIO_ADMISSION:
        raise lib.G3DError("unsupported scenario", exit_code=lib.EXIT_PREFLIGHT_IDENTITY,
                           detail={"scenario": scenario})
    return dict(SCENARIO_ADMISSION[scenario])


def scenario_prompt(scenario: str) -> str:
    if scenario not in SCENARIO_PROMPT:
        raise lib.G3DError("unsupported scenario", exit_code=lib.EXIT_PREFLIGHT_IDENTITY,
                           detail={"scenario": scenario})
    return SCENARIO_PROMPT[scenario]


def pair_tool_ledger(attempts: list[dict], claims: list[dict],
                     receipts: list[dict]) -> list[dict]:
    """Join Tool attempts to their Claim and Fake receipt by durable ids.

    The join is deliberately by ``call_id``/``receipt_id`` rather than list
    position, so a missing, duplicated or mis-associated row is visible.
    """
    claims_by_call = {row.get("call_id"): row for row in claims
                      if isinstance(row, dict) and row.get("call_id")}
    receipts_by_id = {row.get("receipt_id"): row for row in receipts
                      if isinstance(row, dict) and row.get("receipt_id")}
    paired: list[dict] = []
    ordered = sorted((row for row in attempts if isinstance(row, dict)),
                     key=lambda row: int(row.get("logical_step") or 0))
    for attempt in ordered:
        claim = claims_by_call.get(attempt.get("call_id"))
        receipt = receipts_by_id.get(attempt.get("receipt_id"))
        paired.append({
            "step": int(attempt.get("logical_step") or 0),
            "attempt": attempt,
            "claim": claim,
            "receipt": receipt,
            "prepared_ok": bool(claim) and
            claim.get("request_digest") == attempt.get("prepared_digest"),
            "payload_ok": bool(receipt) and
            receipt.get("raw_sha256") == attempt.get("payload_digest"),
            "reservation_link_ok": bool(claim) and
            claim.get("reservation_id") == attempt.get("reservation_id"),
        })
    return paired


class Launcher:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.case = args.case
        self.sub = args.sub or ""
        self.exit_code = lib.EXIT_OK
        self.failure: dict | None = None
        self.errors: list[dict] = []
        self.checks: list[dict] = []
        self.records: dict = {}
        self.container_records: dict = {}
        self.runtime_identity: dict = {}
        self.socket_records: dict = {}
        self.preflight_record: dict = {}
        self.started_utc = lib.utc()
        self.stage_dir = self._resolve_stage(args.stage)
        suffix = f"-{args.sub}" if args.sub else ""
        run_id = args.run_id or f"{lib.utc_compact()}-{args.case}{suffix}-{uuid.uuid4().hex[:8]}"
        if not RUN_ID_PATTERN.fullmatch(run_id):
            raise lib.G3DError("invalid run id", exit_code=lib.EXIT_PREFLIGHT_IDENTITY,
                               detail={"run_id": run_id})
        self.run_id = run_id
        self.run_dir = lib.G3D_ROOT / "runs" / run_id
        self.evidence = Path(args.evidence_dir).resolve() if args.evidence_dir else \
            (lib.G3D_ROOT / "d1b")
        self.keep_run = bool(args.keep_run)
        self.trusted_name = lib.container_name(run_id, "trusted")
        self.candidate_name = lib.container_name(run_id, "candidate")
        self.commands_path = self.evidence / "commands.jsonl"
        self.evidence_ready = False

    # -- helpers --------------------------------------------------------
    def _resolve_stage(self, explicit: str | None) -> Path:
        if explicit:
            path = Path(explicit).resolve()
            if not path.is_dir():
                raise lib.G3DError("stage directory missing",
                                   exit_code=lib.EXIT_STAGE_INVALID,
                                   detail={"stage": str(path)})
            return path
        candidates = sorted(
            path for path in lib.G3D_ROOT.glob("stage-*")
            if path.is_dir() and (path / "manifest.json").is_file())
        if not candidates:
            raise lib.G3DError("no built stage found; run scripts/g3d/build_stage.py first",
                               exit_code=lib.EXIT_STAGE_INVALID)
        return candidates[-1]

    def cmd(self, argv, *, name: str, timeout: float | None = 120,
            env: dict[str, str] | None = None) -> dict:
        record = lib.run_command(argv, log_dir=self.evidence / "run", name=name,
                                 timeout=timeout, env=env,
                                 commands_path=self.commands_path)
        return record

    def podman_inspect(self, name: str, *, label: str | None = None) -> dict | None:
        record = self.cmd(["podman", "inspect", name], name=label or f"inspect-{name}",
                          timeout=30)
        if record["exit"] != 0:
            return None
        try:
            document = json.loads(record["stdout"])
        except json.JSONDecodeError:
            return None
        if not isinstance(document, list) or not document:
            return None
        return document[0]

    def podman_status(self, name: str) -> str | None:
        record = self.cmd(["podman", "inspect", "-f", "{{.State.Status}}", name],
                          name=f"status-{name}", timeout=20)
        if record["exit"] != 0:
            return None
        return record["stdout"].strip() or None

    def podman_exit_code(self, name: str) -> int | None:
        document = self.podman_inspect(name, label=f"exit-inspect-{name}")
        if document is None:
            return None
        state = document.get("State") or {}
        if state.get("Status") in {"exited", "stopped"}:
            try:
                return int(state.get("ExitCode"))
            except (TypeError, ValueError):
                return None
        return None

    def write_evidence_json(self, relative: str, document: object, *,
                            mode: int = 0o444) -> dict:
        path = self.evidence / relative
        return lib.write_json_atomic(path, document, mode=mode, uid=0, gid=0)

    def write_evidence_bytes(self, relative: str, data: bytes, *,
                             mode: int = 0o444) -> dict:
        return lib.write_bytes_atomic(self.evidence / relative, data,
                                      mode=mode, uid=0, gid=0)

    def record_error(self, code: str, message: str, **detail: object) -> None:
        entry = {"utc": lib.utc(), "code": code, "message": message,
                 "detail": detail}
        self.errors.append(entry)
        lib.append_jsonl(self.evidence / "errors.jsonl", entry)

    def fail(self, exit_code: int, message: str, **detail: object) -> None:
        raise lib.G3DError(message, exit_code=exit_code, detail=detail)

    # -- preflight ------------------------------------------------------
    def _ensure_evidence(self) -> None:
        if self.evidence.exists() and any(self.evidence.iterdir()):
            raise lib.G3DError(
                "evidence directory already contains data; use a new --evidence-dir",
                exit_code=lib.EXIT_PREFLIGHT_IDENTITY,
                detail={"evidence": str(self.evidence)})
        for relative in ("env", "run", "traces", "db", "receipt", "uid-map",
                         "mountinfo", "socket-stat", "peercred", "network-probe",
                         "cleanup"):
            (self.evidence / relative).mkdir(parents=True, exist_ok=True)
        (self.evidence / "commands.jsonl").touch()
        self.evidence_ready = True

    def _status_entries(self) -> list[dict]:
        raw = lib.git_bytes("status", "--porcelain=v1", "-z", "-uall")
        parts = raw.split(b"\0")
        rows: list[dict] = []
        index = 0
        while index < len(parts):
            part = parts[index].decode("utf-8", "replace")
            index += 1
            if not part:
                continue
            xy, path = part[:2], part[3:]
            if xy and xy[0] in {"R", "C"}:
                index += 1
            rows.append({"xy": xy, "path": path})
        return rows

    def preflight(self) -> None:
        self._ensure_evidence()
        problems: list[str] = []
        head = lib.git_text("rev-parse", "HEAD")
        base = lib.PRODUCT_BASE
        status_entries = self._status_entries()
        dirty_allowed, dirty_other = [], []
        for row in status_entries:
            if any(row["path"].startswith(prefix)
                   for prefix in lib.ALLOWED_DIRTY_PREFIXES):
                dirty_allowed.append(row)
            else:
                dirty_other.append(row)
        if dirty_other:
            problems.append("unexpected_worktree_changes")
        def git_diff_empty(*paths: str) -> bool:
            proc = subprocess.run(["git", "diff", "--quiet", base, "--", *paths],
                                  cwd=str(lib.REPO_ROOT))
            return proc.returncode == 0
        src_clean = git_diff_empty("src")
        if not src_clean:
            problems.append("src_differs_from_base")
        if not git_diff_empty("spikes", "plugins"):
            problems.append("spikes_plugins_differ_from_base")
        if not git_diff_empty("tests/integration/g3c", "tests/integration/g3_bridge"):
            problems.append("frozen_tests_modified")
        if not git_diff_empty("tests/integration/g3d/test_d1_socket_boundary.py"):
            problems.append("d1a_tests_modified")
        if head != base:
            ancestor = subprocess.run(
                ["git", "merge-base", "--is-ancestor", base, head],
                cwd=str(lib.REPO_ROOT)).returncode == 0
            if not ancestor:
                problems.append("head_not_descended_from_base")
        git_info = {
            "utc": lib.utc(), "head": head, "base": base,
            "head_is_base": head == base,
            "status_entries": status_entries,
            "allowed_dirty": dirty_allowed,
            "unexpected_dirty": dirty_other,
            "src_identical_to_base": src_clean,
            "log": lib.git_text("log", "-5", "--format=%H %s").splitlines(),
        }
        self.write_evidence_json("env/git.json", git_info)
        git_text = [
            f"HEAD={head}", f"BASE={base}",
            f"HEAD_IS_BASE={head == base}",
            f"SRC_IDENTICAL_TO_BASE={src_clean}",
            "STATUS_PORCELAIN:",
            *[f"  {row['xy']} {row['path']}" for row in status_entries],
            "ALLOWED_DIRTY:",
            *[f"  {row['xy']} {row['path']}" for row in dirty_allowed],
            "LOG:",
            *[f"  {line}" for line in git_info["log"]],
        ]
        self.write_evidence_bytes("env/git.txt",
                                  ("\n".join(git_text) + "\n").encode())

        rootfs_before = lib.sha256_tree(lib.ROOTFS)
        deps_before = lib.sha256_tree(lib.DEPS)
        stage_before = lib.sha256_tree(self.stage_dir)
        canonical = {
            "utc": lib.utc(),
            "rootfs": {"path": str(lib.ROOTFS), "sha256": rootfs_before,
                       "expected": lib.ROOTFS_CANON,
                       "ok": rootfs_before == lib.ROOTFS_CANON},
            "deps": {"path": str(lib.DEPS), "sha256": deps_before,
                     "expected": lib.DEPS_CANON,
                     "ok": deps_before == lib.DEPS_CANON},
            "stage": {"path": str(self.stage_dir), "sha256": stage_before},
        }
        if not canonical["rootfs"]["ok"]:
            problems.append("rootfs_not_canonical")
        if not canonical["deps"]["ok"]:
            problems.append("deps_not_canonical")
        self.records["canonical_pre"] = canonical
        self.write_evidence_json("env/canonical-pre.json", canonical)

        stage_validation = lib.validate_stage(self.stage_dir, verify_git=True)
        self.write_evidence_json("env/stage-validation.json", {
            key: value for key, value in stage_validation.items() if key != "manifest"})
        if not stage_validation["ok"]:
            problems.append("stage_manifest_invalid")
            self.record_error("STAGE_INVALID", "stage manifest validation failed",
                              problems=stage_validation["problems"][:40])
        (self.evidence / "env" / "stage-manifest.json").write_bytes(
            (self.stage_dir / "manifest.json").read_bytes())
        summary_path = self.stage_dir / "stage-summary.json"
        if summary_path.is_file():
            lib.write_bytes_atomic(self.evidence / "env" / "stage-summary.json",
                                   summary_path.read_bytes(), mode=0o444)
        self.records["stage"] = {
            "path": str(self.stage_dir), "sha256": stage_before,
            "manifest_sha256": stage_validation.get("manifest_sha256"),
            "base_sha": stage_validation.get("base_sha"),
            "trusted_files": stage_validation.get("trusted_file_count"),
            "candidate_files": stage_validation.get("candidate_file_count"),
        }

        podman_info_record = self.cmd(["podman", "info", "--format", "json"],
                                      name="podman-info", timeout=60)
        podman_info = None
        if podman_info_record["exit"] == 0:
            try:
                podman_info = json.loads(podman_info_record["stdout"])
            except json.JSONDecodeError:
                podman_info = None
        if podman_info is None:
            problems.append("podman_info_unavailable")
        else:
            version = (podman_info.get("version") or {}).get("Version")
            host = podman_info.get("host") or {}
            oci = host.get("ociRuntime") or {}
            security = host.get("security") or {}
            condensed = {
                "version": version,
                "cgroup_version": host.get("cgroupVersion"),
                "cgroup_controllers": host.get("cgroupControllers"),
                "rootless": security.get("rootless"),
                "oci_runtime": oci.get("name"),
                "oci_runtime_version": (oci.get("version") or "").splitlines()[:1],
                "distribution": host.get("distribution"),
                "kernel": host.get("kernel"),
            }
            self.write_evidence_json("env/podman-info.json", condensed)
            self.records["podman"] = condensed
            if version != "4.9.3":
                problems.append("podman_version_not_frozen")
            if condensed["cgroup_version"] != "v2":
                problems.append("cgroup_v2_required")
            if condensed["rootless"] is not False:
                problems.append("rootful_podman_required")
            if condensed["oci_runtime"] != "crun":
                problems.append("crun_required")

        ps_record = self.cmd(["podman", "ps", "-a", "--format", "{{.Names}}"],
                             name="ps-preflight", timeout=30)
        names = [line for line in ps_record["stdout"].splitlines() if line.strip()]
        self.write_evidence_bytes("env/ps-preflight.txt",
                                  ("\n".join(names) + "\n").encode())
        if ps_record["exit"] != 0 or names:
            problems.append("podman_ps_not_empty")
        if any(name.startswith(lib.CONTAINER_PREFIX) for name in names):
            problems.append("stale_at_g3d_container")

        stale_sockets = []
        stale_runs = []
        runs_root = lib.G3D_ROOT / "runs"
        if runs_root.is_dir():
            stale_sockets = [str(path) for path in runs_root.glob("*/ipc/bridge.sock")]
            stale_runs = [str(path) for path in runs_root.iterdir()
                          if path.is_dir() and path.name == self.run_id]
        if self.run_dir.exists():
            problems.append("run_id_already_exists")
        if stale_sockets:
            problems.append("stale_bridge_socket")
        if stale_runs:
            problems.append("stale_run_directory")

        env_snapshot = lib.env_snapshot()
        if env_snapshot["key_like_names"]:
            problems.append("key_like_env_present")
        dotenv = sorted(path.name for path in lib.REPO_ROOT.glob(".env*"))
        if ".env" in dotenv:
            problems.append("dotenv_file_present")
        self.write_evidence_json("network-probe/env-names.json", env_snapshot)

        livegate_record = self.cmd(
            [sys.executable, "-B", "-c", LIVEGATE_CODE], name="livegate",
            timeout=30, env={**os.environ,
                             "PYTHONPATH": str(lib.REPO_ROOT / "src"),
                             "PYTHONDONTWRITEBYTECODE": "1"})
        livegate = None
        if livegate_record["exit"] == 0:
            for line in reversed(livegate_record["stdout"].splitlines()):
                try:
                    candidate = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(candidate, dict):
                    livegate = candidate
                    break
        if not livegate or livegate.get("status") != "BLOCKED":
            problems.append("livegate_not_blocked")
        self.write_evidence_json("env/livegate.json",
                                 {"utc": lib.utc(), "decision": livegate,
                                  "expected": "BLOCKED"})
        live_script = self.cmd(["bash", str(lib.REPO_ROOT / "scripts" / "run_live.sh")],
                               name="run-live-hard-stop", timeout=30)
        if live_script["exit"] != 3:
            problems.append("run_live_not_exit_3")

        setgid = self._setgid_probe()
        if not setgid["ok"]:
            problems.append("setgid_group_2000_unavailable")
        userns = self._userns_probe()
        if not userns["ok"]:
            problems.append("userns_probe_failed")
        ps_after = self.cmd(["podman", "ps", "-a", "--format", "{{.Names}}"],
                            name="ps-after-probes", timeout=30)
        if ps_after["stdout"].strip():
            problems.append("probe_container_residual")

        host_identity = {
            "utc": lib.utc(),
            "euid": os.geteuid(), "egid": os.getegid(),
            "uid_map": Path("/proc/self/uid_map").read_text(
                encoding="utf-8").strip(),
            "gid_map": Path("/proc/self/gid_map").read_text(
                encoding="utf-8").strip(),
            "kernel": platform.release(),
            "machine": platform.machine(),
            "hostname": socket.gethostname(),
            "note": "runner may be a nested LXC userns; Trusted uid_map is "
                    "relative to this namespace",
        }
        self.write_evidence_json("env/host-identity.json", host_identity)
        self.preflight_record = {
            "utc": lib.utc(), "head": head, "base": base,
            "host_identity": host_identity,
            "git_clean_relative_to_base": not dirty_other,
            "allowed_dirty": dirty_allowed,
            "rootfs": canonical["rootfs"], "deps": canonical["deps"],
            "stage": self.records["stage"],
            "podman": self.records.get("podman", {}),
            "livegate": livegate, "run_live_exit": live_script["exit"],
            "env": env_snapshot, "dotenv_files": dotenv,
            "setgid_probe": setgid, "userns_probe": userns,
            "problems": sorted(set(problems)),
        }
        self.write_evidence_json("env/preflight.json", self.preflight_record)
        if problems:
            self.fail(lib.EXIT_BLOCKED_ENVIRONMENT if
                      any(item in {"rootfs_not_canonical", "deps_not_canonical",
                                   "podman_info_unavailable", "podman_version_not_frozen",
                                   "cgroup_v2_required", "rootful_podman_required",
                                   "crun_required", "userns_probe_failed",
                                   "setgid_group_2000_unavailable",
                                   "key_like_env_present", "livegate_not_blocked",
                                   "run_live_not_exit_3"}
                          for item in problems)
                      else lib.EXIT_PREFLIGHT_IDENTITY,
                      "preflight failed", problems=problems)

    def _setgid_probe(self) -> dict:
        probe_dir = lib.G3D_ROOT / f"env-probe-{os.getpid()}-{uuid.uuid4().hex[:6]}"
        result: dict = {"utc": lib.utc(), "ok": False, "problems": []}
        try:
            probe_dir.mkdir(mode=0o700)
            os.chown(probe_dir, 0, 0)
            os.chmod(probe_dir, 0o2750)
            os.chown(probe_dir, 0, lib.GROUP_SOCKET)
            directory = lib.lstat_record(probe_dir)
            result["directory"] = directory
            if directory["gid"] != lib.GROUP_SOCKET or not directory["setgid"]:
                result["problems"].append("directory_gid_or_setgid")
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                sock.bind(str(probe_dir / "probe.sock"))
                info = os.lstat(probe_dir / "probe.sock")
                result["socket"] = {"gid": info.st_gid,
                                    "mode": format(stat.S_IMODE(info.st_mode), "04o"),
                                    "is_socket": stat.S_ISSOCK(info.st_mode)}
                if info.st_gid != lib.GROUP_SOCKET:
                    result["problems"].append("socket_did_not_inherit_gid_2000")
            finally:
                sock.close()
                try:
                    os.unlink(probe_dir / "probe.sock")
                except OSError:
                    pass
            result["ok"] = not result["problems"]
        except OSError as exc:
            result["problems"].append(f"probe_error:{type(exc).__name__}")
        finally:
            try:
                if probe_dir.exists():
                    press = lib.safe_delete_tree(lib.G3D_ROOT, probe_dir)
                    result["cleanup"] = press
            except lib.G3DError:
                pass
            self.write_evidence_json("env/setgid-probe.json", result)
        return result

    def _userns_probe(self) -> dict:
        name = f"{lib.CONTAINER_PREFIX}envprobe-{self.run_id}"
        argv = [
            "podman", "run", "--rm", "--name", name, "--rootfs",
            "--timeout", "90",
            "--uidmap", "0:65534:1",
            "--gidmap", "0:65534:1", "--gidmap", "2000:2000:1",
            "--user", "0:0", "--group-add", str(lib.GROUP_SOCKET),
            "--network", "none", "--http-proxy=false", "--unsetenv-all",
            "--no-hosts", "--read-only", "--read-only-tmpfs=false",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--pids-limit", "32", "--memory", "128m", "--memory-swap", "128m",
            "--cpus", "1",
            "--env", "PATH=/opt/python/bin:/usr/bin", "--env", "TMPDIR=/tmp",
            "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=16m,mode=1777",
            "--workdir", "/", "--systemd=false",
            str(lib.ROOTFS), "/opt/python/bin/python3.11", "-B", "-c",
            USERNS_PROBE_CODE,
        ]
        record = self.cmd(argv, name="userns-probe", timeout=120)
        lib.write_bytes_atomic(self.evidence / "env" / "userns-probe.stdout.txt",
                               (record["stdout"] + record["stderr"]).encode(),
                               mode=0o444)
        result: dict = {"utc": lib.utc(), "argv": argv, "exit": record["exit"],
                        "problems": [], "probe": None, "ok": False}
        probe = None
        for line in record["stdout"].splitlines():
            if line.startswith("G3D_USERNS_PROBE "):
                try:
                    probe = json.loads(line[len("G3D_USERNS_PROBE "):])
                except json.JSONDecodeError:
                    probe = None
        result["probe"] = probe
        if record["exit"] != 0:
            result["problems"].append(f"probe_exit:{record['exit']}")
        if not isinstance(probe, dict):
            result["problems"].append("probe_output_missing")
        else:
            compact_uid = [line.split() for line in probe.get("uid_map", "").splitlines()]
            compact_gid = [line.split() for line in probe.get("gid_map", "").splitlines()]
            if compact_uid != [["0", "65534", "1"]]:
                result["problems"].append("uid_map")
            if ["0", "65534", "1"] not in compact_gid or \
                    ["2000", "2000", "1"] not in compact_gid:
                result["problems"].append("gid_map")
            if set(probe.get("groups") or []) != {0, lib.GROUP_SOCKET}:
                result["problems"].append("groups")
            if probe.get("cap_eff") != "0000000000000000":
                result["problems"].append("cap_eff")
            if probe.get("no_new_privs") != "1":
                result["problems"].append("no_new_privs")
            if (probe.get("af_inet") or {}).get("ok"):
                result["problems"].append("af_inet_unexpectedly_connected")
            if not probe.get("so_peercred"):
                result["problems"].append("so_peercred_missing")
        result["ok"] = not result["problems"]
        self.write_evidence_json("env/userns-probe.json", result)
        return result

    # -- run construction ----------------------------------------------
    def create_run(self) -> None:
        runs_root = lib.G3D_ROOT / "runs"
        runs_root.mkdir(mode=0o700, exist_ok=True)
        os.chown(runs_root, 0, 0)
        os.chmod(runs_root, 0o700)
        layout = lib.create_run_layout(self.run_dir)
        receipts = self.run_dir / "state" / "receipts"
        receipts.mkdir(mode=0o700)
        os.chown(receipts, 0, 0)
        os.chmod(receipts, 0o700)
        self.records["run_layout"] = layout
        self.write_evidence_json("env/run-layout.json",
                                 {"run_dir": str(self.run_dir), "layout": layout})
        (self.run_dir / "logs").mkdir(exist_ok=True)

    def _load_stage_template(self, name: str) -> dict:
        path = self.stage_dir / "trusted" / "templates" / name
        raw = lib.read_regular_bytes(path, max_bytes=1 << 20)
        document = json.loads(raw.decode("utf-8"))
        if not isinstance(document, dict):
            self.fail(lib.EXIT_STAGE_INVALID, "stage template is not an object",
                      template=name)
        return document

    def write_configs(self) -> None:
        controller = self._load_stage_template("controller.template.json")
        allowed_controller = REQUIRED_CONTROLLER_KEYS | {
            "fake_python", "socket_mode", "socket_gid", "expected_peer_uid"}
        if set(controller) - allowed_controller or REQUIRED_CONTROLLER_KEYS - set(controller):
            self.fail(lib.EXIT_STAGE_INVALID, "controller template key set invalid",
                      keys=sorted(controller))
        if controller.get("socket_mode") != 0o660:
            self.fail(lib.EXIT_STAGE_INVALID, "controller template socket_mode must be 432")
        if controller.get("socket_gid") is not None:
            self.fail(lib.EXIT_STAGE_INVALID, "controller template socket_gid must be null")
        if controller.get("expected_peer_uid") != lib.EXPECTED_PEER_UID:
            self.fail(lib.EXIT_STAGE_INVALID, "controller template expected_peer_uid")
        if controller.get("expected_uid") != lib.NOBODY_UID:
            self.fail(lib.EXIT_STAGE_INVALID, "controller template expected_uid")
        if controller.get("socket_path") != lib.SOCKET_PATH:
            self.fail(lib.EXIT_STAGE_INVALID, "controller template socket_path")
        controller_sha = lib.write_json_atomic(
            self.run_dir / "state" / "controller.json", controller,
            mode=0o400, uid=0, gid=0)

        admission_template = (self.stage_dir / "trusted" / "templates" /
                              "admission.template.json").read_text(encoding="utf-8")
        admission_id = secrets.token_hex(16)
        nonce = secrets.token_hex(16)
        expiry = (datetime.now(timezone.utc) + timedelta(hours=1)).strftime(
            "%Y-%m-%dT%H:%M:%SZ")
        overrides = scenario_admission(self.args.scenario)
        rendered = admission_template
        rendered = rendered.replace("{{ADMISSION_ID}}", admission_id)
        rendered = rendered.replace("{{RUN_ID}}", self.run_id)
        tool_schemas = self._capture_tool_schemas()
        rendered = rendered.replace("{{TOOL_SCHEMAS}}",
                                    json.dumps(tool_schemas, sort_keys=True))
        rendered = rendered.replace("{{FAKE_SCENARIO}}",
                                    overrides["fake_scenario"])
        rendered = rendered.replace("{{EXPIRY_UTC}}", expiry)
        rendered = rendered.replace("{{NONCE}}", nonce)
        admission = json.loads(rendered)
        # D1-C scenario limits are applied on the parsed document so the frozen
        # template stays byte-identical; no protocol field is added or removed.
        admission["limits"]["max_calls"] = overrides["max_calls"]
        if "deadline_ms" in overrides:
            # Shorter than the frozen 30s default: a stricter deadline for the
            # bounded D3 watchdog cases. It is still inside the admission
            # schema bounds (100..30000).
            admission["limits"]["deadline_ms"] = overrides["deadline_ms"]
        if admission.get("launcher", {}).get("uid") != lib.NOBODY_UID:
            self.fail(lib.EXIT_STAGE_INVALID, "admission launcher uid must be 65534")
        if admission.get("synthetic") is not True:
            self.fail(lib.EXIT_STAGE_INVALID, "admission must be synthetic")
        if admission.get("fake_scenario") != overrides["fake_scenario"]:
            self.fail(lib.EXIT_STAGE_INVALID, "admission fake_scenario mismatch")
        if admission.get("limits", {}).get("max_calls") != overrides["max_calls"]:
            self.fail(lib.EXIT_STAGE_INVALID, "admission max_calls mismatch")
        if "deadline_ms" in overrides and admission.get("limits", {}).get(
                "deadline_ms") != overrides["deadline_ms"]:
            self.fail(lib.EXIT_STAGE_INVALID, "admission deadline_ms mismatch")
        if admission.get("route") != {"route_id": "offline-test-only-g3b",
                                       "provider": "offline-test-only-g3b",
                                       "model": "fixture-bridge-v1"}:
            self.fail(lib.EXIT_STAGE_INVALID, "admission route is not the frozen fixture")
        admission_sha = lib.write_json_atomic(
            self.run_dir / "state" / "admission.json", admission,
            mode=0o400, uid=0, gid=0)

        broker = self._load_stage_template("broker.template.json")
        if broker.get("synthetic") is not True:
            self.fail(lib.EXIT_STAGE_INVALID, "broker config must be synthetic")
        if broker.get("db_path") != "/work/state/broker.sqlite3":
            self.fail(lib.EXIT_STAGE_INVALID, "broker db_path must be in $RUN/state")
        broker_sha = lib.write_json_atomic(
            self.run_dir / "state" / "broker.json", broker, mode=0o400, uid=0, gid=0)

        configs = {"controller": controller, "admission": admission, "broker": broker}
        for name, document in configs.items():
            key_problems = self._config_key_problems(document)
            if key_problems:
                self.fail(lib.EXIT_NO_LIVE_VIOLATION,
                          f"key-like content in generated {name} config",
                          problems=key_problems)
        self.records["configs"] = {
            "controller": {"path": str(self.run_dir / "state" / "controller.json"),
                           "sha256": controller_sha["sha256"]},
            "admission": {"path": str(self.run_dir / "state" / "admission.json"),
                          "sha256": admission_sha["sha256"]},
            "broker": {"path": str(self.run_dir / "state" / "broker.json"),
                       "sha256": broker_sha["sha256"]},
        }
        for name in ("controller", "admission", "broker"):
            lib.write_bytes_atomic(self.evidence / "run" / f"config-{name}.json",
                                   lib.json_bytes(configs[name]), mode=0o444)

    @staticmethod
    def _config_key_problems(document: object) -> list[str]:
        problems: list[str] = []
        forbidden_keys = {"api_key", "apikey", "token", "secret", "password",
                          "credential", "credentials", "authorization",
                          "access_token", "session_token", "api_secret"}
        def walk(value: object, path: str) -> None:
            if isinstance(value, dict):
                for key, child in value.items():
                    lower = str(key).lower()
                    if lower in forbidden_keys:
                        problems.append(f"{path}.{key}")
                    walk(child, f"{path}.{key}")
            elif isinstance(value, list):
                for index, child in enumerate(value):
                    walk(child, f"{path}[{index}]")
            elif isinstance(value, str):
                if value.startswith(("sk-", "Bearer ", "Bearer_")):
                    problems.append(path)
        walk(document, "$")
        return problems

    def _capture_tool_schemas(self) -> list[dict]:
        """Load the frozen synthetic tool-schema fixture from the stage.

        The DSH session advertises ``skill_lookup`` from the candidate-side
        offline skill plugin. Admission must list the exact canonical hash or
        the Controller correctly fails closed; the fixture is part of the stage
        manifest and is re-hashed by ``validate_stage`` before use.
        """
        path = self.stage_dir / "candidate" / "fixtures" / "capture-tools.json"
        raw = lib.read_regular_bytes(path, max_bytes=1 << 20)
        document = json.loads(raw.decode("utf-8"))
        tools = document.get("tools")
        if not isinstance(tools, list) or not tools:
            self.fail(lib.EXIT_STAGE_INVALID, "capture-tools fixture has no tools")
        result: list[dict] = []
        for item in tools:
            if not isinstance(item, dict):
                self.fail(lib.EXIT_STAGE_INVALID, "capture-tools item is not an object")
            name = item.get("name")
            digest = item.get("sha256")
            canonical = item.get("canonical_json")
            if not isinstance(name, str) or not name:
                self.fail(lib.EXIT_STAGE_INVALID, "capture-tools name invalid")
            if not isinstance(digest, str) or len(digest) != 64:
                self.fail(lib.EXIT_STAGE_INVALID, "capture-tools hash invalid")
            if not isinstance(canonical, str):
                self.fail(lib.EXIT_STAGE_INVALID,
                          "capture-tools canonical_json missing", name=name)
            tool_document = json.loads(canonical)
            compact = json.dumps(tool_document, sort_keys=True,
                                 separators=(",", ":"), ensure_ascii=False).encode()
            if lib.sha256_bytes(compact) != digest:
                self.fail(lib.EXIT_STAGE_INVALID,
                          "capture-tools canonical hash mismatch", name=name)
            result.append({"name": name, "sha256": digest})
        if len(result) > 8:
            self.fail(lib.EXIT_STAGE_INVALID, "too many tool schemas")
        self.records["tool_schemas"] = result
        return result

    # -- containers -----------------------------------------------------
    def _write_argv(self, role: str, argv: list[str]) -> None:
        self.write_evidence_json(f"run/argv-{role}.json", {"argv": argv})

    def _container_env_names(self, inspect_document: dict | None) -> list[str]:
        if not inspect_document:
            return []
        env = ((inspect_document.get("Config") or {}).get("Env") or [])
        return sorted(str(item).split("=", 1)[0] for item in env)

    def start_trusted(self) -> None:
        argv = lib.trusted_run_argv(
            podman="podman", rootfs=str(lib.ROOTFS),
            stage_trusted=str(self.stage_dir / "trusted"), deps=str(lib.DEPS),
            run_dir=str(self.run_dir), name=self.trusted_name,
            crash_hook=getattr(self, "crash_hook", None))
        problems = lib.argv_contract_problems(
            argv, role="trusted", run_dir=str(self.run_dir),
            stage_dir=str(self.stage_dir / "trusted"))
        if problems:
            self.fail(lib.EXIT_STAGE_INVALID, "trusted argv violates contract",
                      problems=problems)
        self._write_argv("trusted", argv)
        self.records["trusted_utc_start"] = lib.utc()
        record = self.cmd(argv, name="podman-run-trusted", timeout=90)
        self.records["trusted_run_exit"] = record["exit"]
        if record["exit"] != 0:
            self.fail(lib.EXIT_TRUSTED_START_FAILED,
                      "podman run for trusted failed",
                      exit=record["exit"], stderr=record["stderr"][-2000:])
        document = self.podman_inspect(self.trusted_name, label="inspect-trusted")
        if document is None:
            self.fail(lib.EXIT_TRUSTED_START_FAILED, "trusted inspect failed")
        if document["State"]["Status"] not in {"running", "created"}:
            self.fail(lib.EXIT_TRUSTED_START_FAILED,
                      "trusted container not running",
                      status=document["State"]["Status"])
        ready_path = self.run_dir / "state" / "ready"
        deadline = time.monotonic() + float(self.args.ready_timeout)
        ready_raw = None
        ready_document = None
        ready_problems = ["ready_absent"]
        last_status = None
        while time.monotonic() < deadline:
            if ready_path.exists():
                ready_raw = lib.read_regular_bytes(ready_path, max_bytes=1 << 14)
                ready_document, ready_problems = lib.parse_ready_document(ready_raw)
                break
            last_status = self.podman_status(self.trusted_name)
            if last_status in {"exited", "stopped"}:
                break
            time.sleep(0.1)
        if ready_document is None:
            logs = self._container_logs(self.trusted_name, "trusted-failure")
            self.fail(lib.EXIT_TRUSTED_START_FAILED,
                      "trusted ready file not observed before timeout",
                      ready_problems=ready_problems,
                      container_status=last_status or self.podman_status(self.trusted_name),
                      log_tail=logs[-3000:])
        document = self.podman_inspect(self.trusted_name, label="inspect-trusted-ready")
        assert document is not None
        trusted_pid = int(document["State"]["Pid"])
        socket_record = lib.lstat_record(lib.SOCKET_PATH.replace(
            "/work/g3b", str(self.run_dir / "ipc")))
        listening = lib.parse_proc_net_unix(trusted_pid)
        evaluation = lib.evaluate_ready(
            socket_record=socket_record, ready_document=ready_document,
            ready_problems=ready_problems, listening_entries=listening,
            container_running=document["State"]["Status"] == "running")
        self.socket_records["before_candidate"] = socket_record
        self.write_evidence_json("socket-stat/before-candidate.json", socket_record)
        self.write_evidence_json("socket-stat/listening.json", {
            "trusted_pid": trusted_pid, "entries": listening,
            "evaluation": evaluation})
        if not lib.ready_allows_candidate(evaluation):
            logs = self._container_logs(self.trusted_name, "trusted-failure")
            self.fail(lib.EXIT_TRUSTED_START_FAILED,
                      "trusted readiness gate failed",
                      evaluation=evaluation, log_tail=logs[-3000:])
        launcher_ready = {
            "schema": "m0.g3d.launcher.ready.v1",
            "utc": lib.utc(),
            "run_id": self.run_id,
            "trusted_container": self.trusted_name,
            "trusted_pid": trusted_pid,
            "trusted_ready_sha256":
                lib.sha256_bytes(lib.read_regular_bytes(ready_path, max_bytes=1 << 14)),
            "socket": socket_record,
            "listening": [entry for entry in listening
                          if entry.get("path") == lib.SOCKET_PATH and entry.get("listening")],
            "candidate_started": False,
            "synthetic": True,
        }
        lib.write_json_atomic(self.run_dir / "state" / "launcher-ready.json",
                              launcher_ready, mode=0o600, uid=0, gid=0)
        self.runtime_identity["trusted"] = self._capture_identity(
            trusted_pid, "trusted")
        self.container_records["trusted"] = {
            "name": self.trusted_name, "container_id": document.get("Id"),
            "pid": trusted_pid, "status": document["State"]["Status"],
            "started_at": document["State"].get("StartedAt"),
            "argv": argv,
            "env_names": self._container_env_names(document),
            "network_mode": (document.get("HostConfig") or {}).get("NetworkMode"),
            "read_only": (document.get("HostConfig") or {}).get("ReadonlyRootfs"),
            "cap_drop": (document.get("HostConfig") or {}).get("CapDrop"),
            "security_opts": (document.get("HostConfig") or {}).get("SecurityOpt"),
        }
        self.write_evidence_json("run/inspect-trusted.json", document)
        for source, name in ((self.run_dir / "state" / "ready", "trusted-ready.json"),
                             (self.run_dir / "state" / "launcher-ready.json",
                              "launcher-ready.json")):
            data = lib.read_regular_bytes(source, max_bytes=1 << 14)
            lib.write_bytes_atomic(self.evidence / "run" / name, data, mode=0o444)

    def _capture_identity(self, pid: int, role: str) -> dict:
        if not isinstance(pid, int) or pid <= 0:
            return {"role": role, "error": "invalid_pid"}
        identity = {
            "role": role, "pid": pid, "utc": lib.utc(),
            "credentials": lib.proc_credentials(pid),
            "uid_map": self._read_proc_text(pid, "uid_map"),
            "gid_map": self._read_proc_text(pid, "gid_map"),
            "mountinfo": self._read_proc_text(pid, "mountinfo"),
            "cgroup": lib.cgroup_limits(pid),
            "cmdline": self._read_proc_cmdline(pid),
        }
        directory = "uid-map" if role != "trusted" else "uid-map"
        (self.evidence / directory).mkdir(parents=True, exist_ok=True)
        for key in ("uid_map", "gid_map"):
            (self.evidence / directory / f"{role}-{key}.txt").write_text(
                identity[key] or "", encoding="utf-8")
        (self.evidence / "mountinfo" / f"{role}.txt").write_text(
            identity["mountinfo"] or "", encoding="utf-8")
        status_text = self._read_proc_text(pid, "status")
        (self.evidence / "uid-map" / f"{role}-status.txt").write_text(
            status_text or "", encoding="utf-8")
        self.write_evidence_json(f"uid-map/{role}-cgroup.json", identity["cgroup"])
        return identity

    def _read_proc_text(self, pid: int, name: str) -> str | None:
        try:
            return (Path("/proc") / str(pid) / name).read_text(
                encoding="utf-8", errors="replace")
        except OSError:
            return None

    def _read_proc_cmdline(self, pid: int) -> list[str]:
        try:
            raw = (Path("/proc") / str(pid) / "cmdline").read_bytes()
        except OSError:
            return []
        return [part.decode("utf-8", "replace") for part in raw.split(b"\0") if part]

    def _container_logs(self, name: str, label: str) -> str:
        record = self.cmd(["podman", "logs", name], name=label, timeout=30)
        return (record["stdout"] or "") + (record["stderr"] or "")

    def start_candidate(self) -> None:
        argv = lib.candidate_run_argv(
            podman="podman", rootfs=str(lib.ROOTFS),
            stage_candidate=str(self.stage_dir / "candidate"), deps=str(lib.DEPS),
            run_dir=str(self.run_dir), name=self.candidate_name,
            scenario=self.args.scenario, session=self.args.session,
            prompt=self.args.prompt)
        problems = lib.argv_contract_problems(
            argv, role="candidate", run_dir=str(self.run_dir),
            stage_dir=str(self.stage_dir / "candidate"))
        if problems:
            self.fail(lib.EXIT_STAGE_INVALID, "candidate argv violates contract",
                      problems=problems)
        self._write_argv("candidate", argv)
        self.records["candidate_utc_start"] = lib.utc()
        record = self.cmd(argv, name="podman-run-candidate", timeout=90)
        self.records["candidate_run_exit"] = record["exit"]
        if record["exit"] != 0:
            self.fail(lib.EXIT_CANDIDATE_START_FAILED,
                      "podman run for candidate failed",
                      exit=record["exit"], stderr=record["stderr"][-2000:])
        document = self.podman_inspect(self.candidate_name, label="inspect-candidate")
        if document is None:
            self.fail(lib.EXIT_CANDIDATE_START_FAILED, "candidate inspect failed")
        pid = int(document["State"].get("Pid") or 0)
        if pid > 0:
            self.runtime_identity["candidate"] = self._capture_identity(pid, "candidate")
        socket_record = lib.lstat_record(self.run_dir / "ipc" / "bridge.sock")
        self.socket_records["after_candidate_start"] = socket_record
        self.write_evidence_json("socket-stat/after-candidate-start.json",
                                 socket_record)
        if document["State"]["Status"] == "running":
            wait_record = self.cmd(
                ["podman", "wait", "--interval", "200ms", self.candidate_name],
                name="podman-wait-candidate", timeout=float(self.args.timeout))
            if wait_record["timed_out"]:
                self.records["candidate_timeout"] = True
                self.record_error("CANDIDATE_TIMEOUT", "candidate exceeded timeout",
                                  timeout=self.args.timeout)
                self.cmd(["podman", "kill", "-s", "KILL", self.candidate_name],
                         name="kill-candidate-timeout", timeout=30)
                self.cmd(["podman", "wait", "--interval", "200ms",
                          self.candidate_name],
                         name="podman-wait-candidate-killed", timeout=30)
        final = self.podman_inspect(self.candidate_name, label="inspect-candidate-final")
        exit_code = None
        if final is not None:
            exit_code = int(final["State"].get("ExitCode", -1))
            self.container_records["candidate"] = {
                "name": self.candidate_name, "container_id": final.get("Id"),
                "pid": int(final["State"].get("Pid") or 0),
                "status": final["State"]["Status"],
                "exit_code": exit_code,
                "started_at": final["State"].get("StartedAt"),
                "finished_at": final["State"].get("FinishedAt"),
                "argv": argv,
                "env_names": self._container_env_names(final),
                "network_mode": (final.get("HostConfig") or {}).get("NetworkMode"),
                "read_only": (final.get("HostConfig") or {}).get("ReadonlyRootfs"),
                "uid_maps": (final.get("HostConfig") or {}).get("IDMappings"),
                "cap_drop": (final.get("HostConfig") or {}).get("CapDrop"),
                "security_opts": (final.get("HostConfig") or {}).get("SecurityOpt"),
            }
            self.write_evidence_json("run/inspect-candidate.json", final)
        self.records["candidate_exit_code"] = exit_code
        self.records["candidate_utc_end"] = lib.utc()
        logs = self._container_logs(self.candidate_name, "candidate-log")
        lib.write_bytes_atomic(self.evidence / "run" / "candidate.log",
                               logs.encode(), mode=0o444)
        self.socket_records["after_candidate_exit"] = lib.lstat_record(
            self.run_dir / "ipc" / "bridge.sock")
        self.write_evidence_json("socket-stat/after-candidate-exit.json",
                                 self.socket_records["after_candidate_exit"])
        self._copy_candidate_evidence()

    def _copy_candidate_evidence(self) -> None:
        session_evidence = self.run_dir / "candidate-session" / "evidence"
        copied: list[dict] = []
        if not session_evidence.is_dir():
            self.record_error("CANDIDATE_EVIDENCE_MISSING",
                              "candidate evidence directory missing")
            self.records["candidate_evidence"] = copied
            return
        names = sorted(path.name for path in session_evidence.iterdir()
                       if path.is_file() or path.is_symlink())
        for name in names[:20]:
            source = session_evidence / name
            try:
                data = lib.read_regular_bytes(source, max_bytes=16 << 20)
            except (lib.G3DError, OSError) as exc:
                copied.append({"name": name, "error": type(exc).__name__})
                continue
            target = self.evidence / "traces" / name
            lib.write_bytes_atomic(target, data, mode=0o444)
            copied.append({"name": name, "bytes": len(data),
                           "sha256": lib.sha256_bytes(data)})
        self.records["candidate_evidence"] = copied

    # -- collect / evaluate --------------------------------------------
    def collect(self) -> None:
        try:
            if self.container_records.get("trusted") is None and \
                    self.podman_status(self.trusted_name) is None:
                return
            candidate_status = self.podman_status(self.candidate_name)
            if candidate_status is not None:
                if candidate_status == "running" and \
                        self.records.get("candidate_exit_code") is None:
                    self.records["candidate_exit_code"] = self.podman_exit_code(
                        self.candidate_name)
                self.cmd(["podman", "rm", "-f", self.candidate_name],
                         name="rm-candidate", timeout=60)
            trusted_logs_before = self._container_logs(self.trusted_name,
                                                       "trusted-log-before-stop")
            lib.write_bytes_atomic(self.evidence / "run" / "trusted.log",
                                   trusted_logs_before.encode(), mode=0o444)
            if self.podman_status(self.trusted_name) == "running":
                stop_record = lib.terminate_container(
                    self.trusted_name,
                    signal_fn=self._signal_container,
                    wait_exit=self._wait_exit,
                    grace_s=float(self.args.stop_grace), kill_wait_s=5.0)
            else:
                stop_record = {"container": self.trusted_name, "sigterm": False,
                               "sigkill": False,
                               "exit_code": self.podman_exit_code(self.trusted_name),
                               "stopped": True}
            self.records["trusted_stop"] = stop_record
            final = self.podman_inspect(self.trusted_name,
                                        label="inspect-trusted-final")
            if final is not None:
                trusted_entry = self.container_records.setdefault(
                    "trusted", {"name": self.trusted_name})
                trusted_entry["status"] = final["State"]["Status"]
                trusted_entry["exit_code"] = int(final["State"].get("ExitCode", -1))
                trusted_entry["finished_at"] = final["State"].get("FinishedAt")
                self.write_evidence_json("run/inspect-trusted-final.json", final)
            trusted_logs = self._container_logs(self.trusted_name, "trusted-log")
            if trusted_logs:
                lib.write_bytes_atomic(self.evidence / "run" / "trusted.log",
                                       trusted_logs.encode(), mode=0o444)
            if self.podman_status(self.trusted_name) is not None:
                self.cmd(["podman", "rm", "-f", self.trusted_name],
                         name="rm-trusted", timeout=60)
            self.socket_records["after_trusted_stop"] = lib.lstat_record(
                self.run_dir / "ipc" / "bridge.sock")
            self.write_evidence_json("socket-stat/after-trusted-stop.json",
                                     self.socket_records["after_trusted_stop"])
            if self.records.get("candidate_evidence") is None:
                self._copy_candidate_evidence()
            self._copy_state_assets()
            self._analyse_logs()
            self._copy_runtime_identity_files()
        except lib.G3DError as exc:
            self.record_error(exc.reason, str(exc), **exc.detail)
            if self.exit_code == lib.EXIT_OK:
                self.exit_code = exc.exit_code
        except Exception as exc:  # noqa: BLE001 - collection must not crash cleanup
            self.record_error("COLLECT_FAILED", f"{type(exc).__name__}: {exc}")
            if self.exit_code == lib.EXIT_OK:
                self.exit_code = lib.EXIT_CASE_FAILED

    def _signal_container(self, name: str, signum: str) -> None:
        self.cmd(["podman", "kill", "-s", signum, name],
                 name=f"kill-{signum.lower()}-{name}", timeout=30)

    def _wait_exit(self, name: str, _timeout: float) -> int | None:
        return self.podman_exit_code(name)

    def _copy_state_assets(self) -> None:
        state = self.run_dir / "state"
        copied: dict = {"files": [], "receipts": [], "errors": []}
        names = ("admission.json", "broker.json", "controller.json",
                 "launcher-ready.json", "ready")
        for name in names:
            source = state / name
            record = lib.lstat_record(source)
            if record is None:
                continue
            if record.get("type") != "regular":
                copied["errors"].append({"name": name, "reason": "not_regular",
                                         "record": record})
                continue
            data = lib.read_regular_bytes(source, max_bytes=1 << 20)
            lib.write_bytes_atomic(self.evidence / "run" / name, data, mode=0o444)
            copied["files"].append({"name": name, "sha256": lib.sha256_bytes(data),
                                    "mode": record["mode_octal"]})
        db_dir = self.evidence / "db"
        for name in ("broker.sqlite3", "broker.sqlite3-wal", "broker.sqlite3-shm",
                     "attempts.sqlite3", "attempts.sqlite3-wal",
                     "attempts.sqlite3-shm"):
            source = state / name
            record = lib.lstat_record(source)
            if record is None:
                continue
            if record.get("type") != "regular":
                copied["errors"].append({"name": name, "reason": "not_regular"})
                continue
            data = lib.read_regular_bytes(source, max_bytes=64 << 20)
            lib.write_bytes_atomic(db_dir / name, data, mode=0o444)
            copied.setdefault("databases", []).append(
                {"name": name, "sha256": lib.sha256_bytes(data),
                 "bytes": len(data)})
        receipts_src = state / "receipts"
        if receipts_src.is_dir():
            for entry in sorted(receipts_src.iterdir(), key=lambda p: p.name):
                record = lib.lstat_record(entry)
                if record is None or record.get("type") != "regular":
                    copied["errors"].append({"name": entry.name,
                                             "reason": "not_regular"})
                    continue
                if len(copied["receipts"]) >= 64:
                    copied["errors"].append({"name": entry.name,
                                             "reason": "receipt_cap"})
                    continue
                data = lib.read_regular_bytes(entry, max_bytes=4 << 20)
                lib.write_bytes_atomic(self.evidence / "receipt" / entry.name,
                                       data, mode=0o444)
                copied["receipts"].append({"name": entry.name,
                                           "sha256": lib.sha256_bytes(data),
                                           "bytes": len(data)})
        self.records["state_assets"] = copied
        self.write_evidence_json("run/state-assets.json", copied)

    def _analyse_logs(self) -> None:
        trusted_log = (self.evidence / "run" / "trusted.log")
        text = trusted_log.read_text(encoding="utf-8", errors="replace") \
            if trusted_log.is_file() else ""
        interesting = [line for line in text.splitlines()
                       if any(marker in line for marker in
                              ("bridge peer accepted", "bridge peer rejected",
                               "bridge socket ready", "PEER_UID_DENIED",
                               "PEERCRED_UNAVAILABLE", "G3D_TRUSTED_READY",
                               "G3D_TRUSTED_START", "G3D_TRUSTED_EXIT",
                               "Traceback", "CONFIG_INVALID"))]
        (self.evidence / "peercred" / "trusted-log-extract.txt").write_text(
            "\n".join(interesting) + "\n", encoding="utf-8")
        accepted = [line for line in interesting if "bridge peer accepted" in line]
        denied = [line for line in interesting if "bridge peer rejected" in line]
        ready_lines = [line for line in interesting if "bridge socket ready" in line]
        extract = {
            "utc": lib.utc(),
            "accepted_lines": accepted,
            "rejected_lines": denied,
            "ready_lines": ready_lines,
            "accepted_uid_65534": any("uid=65534" in line for line in accepted),
            "accepted_gid_65534": any("gid=65534" in line for line in accepted),
            "peer_rejected_absent": not denied,
            "ready_mode_0660": any("mode=0660" in line for line in ready_lines),
            "ready_gid_2000": any("gid=2000" in line for line in ready_lines),
            "trusted_start_seen": any("G3D_TRUSTED_START" in line for line in interesting),
            "trusted_ready_seen": any("G3D_TRUSTED_READY" in line for line in interesting),
            "trusted_exit_seen": any("G3D_TRUSTED_EXIT" in line for line in interesting),
        }
        self.write_evidence_json("peercred/trusted-log.json", extract)
        modules_path = self.run_dir / "evidence" / "trusted-modules.json"
        if modules_path.is_file():
            data = lib.read_regular_bytes(modules_path, max_bytes=1 << 20)
            lib.write_bytes_atomic(self.evidence / "peercred" / "trusted-modules.json",
                                   data, mode=0o444)
        preflight_path = self.run_dir / "evidence" / "trusted-preflight.json"
        if preflight_path.is_file():
            data = lib.read_regular_bytes(preflight_path, max_bytes=1 << 20)
            lib.write_bytes_atomic(self.evidence / "run" / "trusted-preflight.json",
                                   data, mode=0o444)

    def _copy_runtime_identity_files(self) -> None:
        if not self.runtime_identity:
            return
        self.write_evidence_json("uid-map/runtime-identity.json",
                                 self.runtime_identity)

    def _read_json_evidence(self, relative: str) -> dict | None:
        path = self.evidence / relative
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def _query(self, db_path: Path, sql: str) -> list[dict]:
        uri = f"file:{db_path}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        try:
            return [dict(row) for row in connection.execute(sql).fetchall()]
        finally:
            connection.close()

    def evaluate(self) -> None:
        checks: list[dict] = []

        def check(check_id: str, ok: bool, **detail: object) -> None:
            checks.append({"id": check_id, "ok": bool(ok), **detail})

        db_dir = self.evidence / "db"
        broker_path = db_dir / "broker.sqlite3"
        attempts_path = db_dir / "attempts.sqlite3"
        snapshot: dict = {"reservations": [], "claims": [], "attempts": [],
                          "admissions": [], "intents": [], "identities": [],
                          "integrity": {}}
        try:
            if broker_path.is_file():
                snapshot["reservations"] = self._query(
                    broker_path,
                    "SELECT reservation_id,route_id,model,input_bound,output_bound,"
                    "status,input_used,output_used,cost,estimated,settlement_json "
                    "FROM budget_reservations ORDER BY rowid")
                snapshot["claims"] = self._query(
                    broker_path,
                    "SELECT call_id,reservation_id,request_digest,status "
                    "FROM budget_dispatch_claims ORDER BY rowid")
                snapshot["integrity"]["broker"] = self._query(
                    broker_path, "PRAGMA integrity_check")
                snapshot["message_count"] = self._query(
                    broker_path, "SELECT COUNT(*) AS n FROM budget_broker_messages")[0]["n"]
            if attempts_path.is_file():
                snapshot["attempts"] = self._query(
                    attempts_path,
                    "SELECT attempt_id,call_id,reservation_id,state,receipt_id,reason,"
                    "payload_digest,prepared_digest,run_id,logical_step,mode,"
                    "input_bound_kind,input_bound_tokens,created_utc,updated_utc,"
                    "settlement_json "
                    "FROM g3b_attempts ORDER BY created_utc, call_id")
                snapshot["admissions"] = self._query(
                    attempts_path,
                    "SELECT admission_id,run_id,consumed_utc,controller_instance_id "
                    "FROM g3b_admissions ORDER BY consumed_utc")
                snapshot["intents"] = self._query(
                    attempts_path,
                    "SELECT intent_id,call_id,reservation_id,state,reason "
                    "FROM g3b_send_intents ORDER BY created_utc")
                snapshot["identities"] = self._query(
                    attempts_path,
                    "SELECT scope_id,identity_digest,call_id,logical_step "
                    "FROM g3b_request_identities ORDER BY created_utc")
                snapshot["integrity"]["attempts"] = self._query(
                    attempts_path, "PRAGMA integrity_check")
        except sqlite3.Error as exc:
            self.record_error("DB_QUERY_FAILED", f"{type(exc).__name__}: {exc}")
        self.write_evidence_json("db/snapshot.json", snapshot)

        receipts = []
        receipt_dir = self.evidence / "receipt"
        if receipt_dir.is_dir():
            for path in sorted(receipt_dir.glob("rcpt-*.json")):
                try:
                    document = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    receipts.append({"name": path.name, "invalid": True})
                    continue
                receipts.append({
                    "name": path.name, "sha256": lib.sha256_file(path),
                    "receipt_id": document.get("receipt_id"),
                    "raw_sha256": document.get("raw_sha256"),
                    "mode": document.get("mode"), "usage": document.get("usage"),
                    "nonce": document.get("nonce"),
                    "synthetic": document.get("synthetic"),
                    "real_model_calls": document.get("real_model_calls"),
                    "http_calls": document.get("http_calls"),
                    "network_used": document.get("network_used"),
                })
        counter = None
        counter_path = receipt_dir / "received-count.json"
        if counter_path.is_file():
            try:
                counter = json.loads(counter_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                counter = {"invalid": True}
        receipt_summary = {"receipts": receipts, "counter": counter,
                           "count": len(receipts)}
        self.write_evidence_json("receipt/summary.json", receipt_summary)

        candidate_result = self._read_json_evidence("traces/dsh-result.json")
        principal = self._read_json_evidence("traces/principal.json")
        peercred = self._read_json_evidence("peercred/trusted-log.json") or {}
        modules = self._read_json_evidence("peercred/trusted-modules.json") or {}
        candidate_identity = self.runtime_identity.get("candidate") or {}
        trusted_record = self.container_records.get("trusted") or {}
        candidate_record = self.container_records.get("candidate") or {}

        candidate_exit = self.records.get("candidate_exit_code")
        check("candidate_exit_zero", candidate_exit == 0, exit=candidate_exit)
        scenario = self.args.scenario
        reservations = snapshot["reservations"]
        claims = snapshot["claims"]
        attempts = snapshot["attempts"]
        admissions = snapshot["admissions"]
        messages = ((candidate_result or {}).get("event_summary") or {}).get(
            "assistant_messages") or []
        messages = sorted((item for item in messages if isinstance(item, dict)),
                          key=lambda item: int(item.get("step") or 0))
        dsh_usages = [item.get("data_usage") or item.get("usage")
                      for item in messages]
        result_ok = isinstance(candidate_result, dict) and \
            candidate_result.get("final_response") == "ok" and \
            candidate_result.get("finish_reason") == "completed"
        if scenario == "echo":
            check("candidate_result_echo_ok", result_ok,
                  final_response=None if not candidate_result else
                  candidate_result.get("final_response"),
                  finish_reason=None if not candidate_result else
                  candidate_result.get("finish_reason"),
                  error=None if not candidate_result else candidate_result.get("error"))
            dsh_usage = dsh_usages[-1] if dsh_usages else None
            check("dsh_usage_present", isinstance(dsh_usage, dict), usage=dsh_usage)
            receipt_usage = receipts[0].get("usage") if receipts else None
            check("dsh_usage_equals_fake_receipt_usage",
                  isinstance(dsh_usage, dict) and dsh_usage == receipt_usage,
                  dsh_usage=dsh_usage, receipt_usage=receipt_usage)
            check("one_reservation_ok",
                  len(reservations) == 1 and reservations[0].get("status") == "OK",
                  rows=reservations)
            check("one_bound_claim_completed",
                  len(claims) == 1 and claims[0].get("status") == "COMPLETED",
                  rows=claims)
            check("one_attempt_settled",
                  len(attempts) == 1 and attempts[0].get("state") == "SETTLED",
                  rows=[{key: row.get(key) for key in
                         ("attempt_id", "state", "call_id", "reservation_id",
                          "receipt_id")} for row in attempts])
            check("one_admission_consumed", len(admissions) == 1, rows=admissions)
            check("one_receipt_and_counter_one",
                  len(receipts) == 1 and isinstance(counter, dict) and
                  counter.get("count") == 1, receipts=len(receipts), counter=counter)
            claim_digest = claims[0].get("request_digest") if claims else None
            attempt_prepared = attempts[0].get("prepared_digest") if attempts else None
            check("prepared_digest_matches_claim",
                  claim_digest is not None and claim_digest == attempt_prepared,
                  claim_request_digest=claim_digest,
                  attempt_prepared_digest=attempt_prepared)
            receipt_raw = receipts[0].get("raw_sha256") if receipts else None
            attempt_payload = attempts[0].get("payload_digest") if attempts else None
            check("payload_digest_matches_receipt",
                  receipt_raw is not None and receipt_raw == attempt_payload,
                  receipt_raw_sha256=receipt_raw,
                  attempt_payload_digest=attempt_payload)
            settlement = None
            attempt_settlement = None
            if reservations:
                try:
                    settlement = json.loads(
                        reservations[0].get("settlement_json") or "null")
                except (TypeError, json.JSONDecodeError):
                    settlement = None
            if attempts:
                try:
                    attempt_settlement = json.loads(
                        attempts[0].get("settlement_json") or "null")
                except (TypeError, json.JSONDecodeError):
                    attempt_settlement = None
            settlement_ok = (
                isinstance(settlement, dict)
                and settlement.get("status") == "OK"
                and settlement.get("reservation_exceeded") is False
                and float(settlement.get("cost_usd", "0")) > 0
                and ((isinstance(attempt_settlement, dict)
                      and attempt_settlement.get("code") == "SETTLED")
                     or (attempts and attempts[0].get("state") == "SETTLED")))
            check("settlement_ok_positive_cost", bool(settlement_ok),
                  reservation_settlement=settlement,
                  attempt_settlement=attempt_settlement)
            check("receipt_synthetic_no_network",
                  bool(receipts) and receipts[0].get("synthetic") is True
                  and receipts[0].get("real_model_calls") == 0
                  and receipts[0].get("http_calls") == 0
                  and receipts[0].get("network_used") is False,
                  receipt=receipts[0] if receipts else None)
        else:
            paired = pair_tool_ledger(attempts, claims, receipts)
            summary = (candidate_result or {}).get("event_summary") or {}
            tool_calls = [item for item in summary.get("tool_calls") or []
                          if isinstance(item, dict)]
            tool_results = [item for item in summary.get("tool_results") or []
                            if isinstance(item, dict)]
            tool_result_text = json.dumps(tool_results, sort_keys=True)
            reservations_by_id = {row.get("reservation_id"): row
                                  for row in reservations if isinstance(row, dict)}
            claim_ids = {row.get("call_id") for row in claims}
            attempt_ids = {row.get("attempt_id") for row in attempts}
            receipt_ids = {row.get("receipt_id") for row in receipts}
            reservation_ids = {row.get("reservation_id") for row in reservations}
            usages_ok = (len(paired) == 2 and len(dsh_usages) == 2
                         and all(isinstance(item, dict) for item in dsh_usages))
            if usages_ok:
                usages_ok = all(
                    paired[index]["receipt"] is not None
                    and dsh_usages[index] == paired[index]["receipt"].get("usage")
                    for index in (0, 1))
            check("candidate_result_tool_ok", result_ok,
                  final_response=None if not candidate_result else
                  candidate_result.get("final_response"),
                  finish_reason=None if not candidate_result else
                  candidate_result.get("finish_reason"),
                  error=None if not candidate_result else candidate_result.get("error"))
            check("dsh_tool_two_turns",
                  len(messages) == 2
                  and (messages[0].get("content_types") or [])
                  and "tool-call" in messages[0]["content_types"]
                  and (messages[1].get("content_types") or [])
                  and "text" in messages[1]["content_types"],
                  messages=[{"step": item.get("step"),
                             "content_types": item.get("content_types")}
                            for item in messages])
            check("dsh_tool_skill_lookup_result",
                  any(item.get("name") == "skill_lookup" for item in tool_calls)
                  and bool(tool_results)
                  and "binary_search" in tool_result_text
                  and "m0-skills-v1" in tool_result_text,
                  tool_calls=tool_calls, tool_results=tool_results)
            check("dsh_usages_equal_two_receipt_usages", bool(usages_ok),
                  dsh_usages=dsh_usages,
                  receipt_usages=[(item["receipt"] or {}).get("usage")
                                  for item in paired])
            check("two_reservations_ok",
                  len(reservations) == 2 and len(reservation_ids) == 2
                  and all(row.get("status") == "OK" for row in reservations),
                  rows=reservations)
            check("two_bound_claims_completed",
                  len(claims) == 2 and len(claim_ids) == 2
                  and all(row.get("status") == "COMPLETED" for row in claims),
                  rows=claims)
            check("two_attempts_settled",
                  len(attempts) == 2 and len(attempt_ids) == 2
                  and all(row.get("state") == "SETTLED" for row in attempts),
                  rows=[{key: row.get(key) for key in
                         ("attempt_id", "state", "call_id", "reservation_id",
                          "receipt_id", "logical_step", "mode")}
                        for row in attempts])
            check("two_attempt_modes_tool_once_tool_final",
                  {row.get("mode") for row in attempts} == {"tool_once", "tool_final"},
                  modes=[row.get("mode") for row in attempts])
            check("one_admission_consumed", len(admissions) == 1, rows=admissions)
            check("two_receipts_counter_two",
                  len(receipts) == 2 and len(receipt_ids) == 2
                  and isinstance(counter, dict) and counter.get("count") == 2,
                  receipts=len(receipts), counter=counter)
            check("two_prepared_digests_match_claims",
                  len(paired) == 2
                  and all(item["prepared_ok"] for item in paired)
                  and len({item["attempt"].get("prepared_digest")
                           for item in paired}) == 2,
                  paired=[{"step": item["step"],
                           "prepared_ok": item["prepared_ok"]} for item in paired])
            check("two_payload_digests_match_receipts",
                  len(paired) == 2
                  and all(item["payload_ok"] for item in paired)
                  and len({item["attempt"].get("payload_digest")
                           for item in paired}) == 2,
                  paired=[{"step": item["step"],
                           "payload_ok": item["payload_ok"]} for item in paired])
            check("two_reservation_links_ok",
                  len(paired) == 2
                  and all(item["reservation_link_ok"] for item in paired),
                  paired=[{"step": item["step"],
                           "reservation_link_ok": item["reservation_link_ok"]}
                          for item in paired])
            second_larger = (len(paired) == 2
                             and int(paired[0]["attempt"].get("input_bound_tokens") or 0)
                             < int(paired[1]["attempt"].get("input_bound_tokens") or 0))
            check("tool_second_request_includes_result",
                  bool(usages_ok and second_larger and tool_results),
                  input_bounds=[item["attempt"].get("input_bound_tokens")
                                for item in paired],
                  tool_results=len(tool_results))
            settlements = []
            settlements_ok = len(paired) == 2
            for item in paired:
                reservation = reservations_by_id.get(
                    item["attempt"].get("reservation_id"))
                settlement = None
                attempt_settlement = None
                if reservation:
                    try:
                        settlement = json.loads(
                            reservation.get("settlement_json") or "null")
                    except (TypeError, json.JSONDecodeError):
                        settlement = None
                try:
                    attempt_settlement = json.loads(
                        item["attempt"].get("settlement_json") or "null")
                except (TypeError, json.JSONDecodeError):
                    attempt_settlement = None
                settlements.append({"step": item["step"],
                                    "reservation": settlement,
                                    "attempt": attempt_settlement})
                settlements_ok = settlements_ok and (
                    isinstance(settlement, dict)
                    and settlement.get("status") == "OK"
                    and settlement.get("reservation_exceeded") is False
                    and float(settlement.get("cost_usd", "0")) > 0
                    and ((isinstance(attempt_settlement, dict)
                          and attempt_settlement.get("code") == "SETTLED")
                         or item["attempt"].get("state") == "SETTLED"))
            check("two_settlements_ok_positive_cost", bool(settlements_ok),
                  settlements=settlements)
            check("tool_receipts_synthetic_no_network",
                  len(receipts) == 2
                  and all(item.get("synthetic") is True
                          and item.get("real_model_calls") == 0
                          and item.get("http_calls") == 0
                          and item.get("network_used") is False
                          for item in receipts),
                  receipts=receipts)
        trusted_exit = trusted_record.get("exit_code")
        check("trusted_exit_zero", trusted_exit == 0, exit=trusted_exit)
        socket_before = self.socket_records.get("before_candidate") or {}
        check("socket_mode_0660_root_2000",
              socket_before.get("type") == "socket"
              and socket_before.get("mode") == lib.SOCKET_MODE
              and socket_before.get("uid") == 0
              and socket_before.get("gid") == lib.GROUP_SOCKET,
              socket=socket_before)
        check("trusted_peercred_uid_65534", peercred.get("accepted_uid_65534") is True
              and peercred.get("accepted_gid_65534") is True
              and peercred.get("peer_rejected_absent") is True,
              accepted_lines=peercred.get("accepted_lines"),
              rejected_lines=peercred.get("rejected_lines"))
        check("trusted_socket_ready_log_0660_gid2000",
              peercred.get("ready_mode_0660") is True
              and peercred.get("ready_gid_2000") is True,
              ready_lines=peercred.get("ready_lines"))
        check("trusted_ready_and_exit_markers",
              peercred.get("trusted_ready_seen") is True
              and peercred.get("trusted_exit_seen") is True)
        candidate_status = ((candidate_identity.get("credentials") or {}))
        uid_map = (candidate_identity.get("uid_map") or "").split()
        gid_map = (candidate_identity.get("gid_map") or "").split()
        check("candidate_host_uid_65534",
              candidate_status.get("uid", "").split()[:1] == ["65534"]
              and candidate_status.get("gid", "").split()[:1] == ["65534"],
              status=candidate_status)
        check("candidate_uid_map_0_65534_1", uid_map == ["0", "65534", "1"],
              uid_map=candidate_identity.get("uid_map"))
        check("candidate_gid_map_root_and_socket",
              gid_map == ["0", "65534", "1", "2000", "2000", "1"],
              gid_map=candidate_identity.get("gid_map"))
        check("candidate_cap_eff_zero",
              candidate_status.get("cap_eff") == "0000000000000000",
              cap_eff=candidate_status.get("cap_eff"))
        check("candidate_no_new_privs", candidate_status.get("no_new_privs") == "1",
              no_new_privs=candidate_status.get("no_new_privs"))
        mountinfo = candidate_identity.get("mountinfo") or ""
        mount_entries = []
        for line in mountinfo.splitlines():
            fields = line.split()
            if len(fields) > 4:
                mount_entries.append({"mount_point": fields[4],
                                      "options": fields[5]})
        points = {entry["mount_point"]: entry["options"] for entry in mount_entries}
        isolation_ok = (
            "/project" in points and "/deps" in points
            and "/work/g3b" in points and "/work/session" in points
            and "/work/state" not in points and "/output" not in points
            and "/project/src" not in points
            and "ro" in points.get("/work/g3b", ""))
        check("candidate_mount_isolation", isolation_ok,
              mount_points=sorted(points))
        module_ok = False
        module_detail: list[dict] = []
        manifest = json.loads((self.stage_dir / "manifest.json").read_text(
            encoding="utf-8"))
        trusted_shas = {row["path"]: row["sha256"]
                        for row in manifest["trusted"]["files"]}
        for row in modules.get("modules") or []:
            module = row.get("module")
            file_path = row.get("file") or ""
            expected_prefix = "/project/src/"
            relative = file_path[len(expected_prefix):] if file_path.startswith(
                expected_prefix) else None
            expected = trusted_shas.get("src/" + relative) if relative else None
            ok = (relative is not None and expected is not None
                  and row.get("sha256") == expected
                  and (row.get("real_path") or "").startswith(
                      "/project/src/autoteacher_m0/"))
            module_detail.append({"module": module, "file": file_path,
                                  "sha256": row.get("sha256"),
                                  "expected": expected, "ok": ok})
        module_ok = bool(module_detail) and all(item["ok"] for item in module_detail)
        check("trusted_modules_from_stage_and_git_blobs", module_ok,
              modules=module_detail)
        principal_checks = (principal or {}).get("checks") or []
        principal_problems = (principal or {}).get("problems")
        check("candidate_principal_selfchecks",
              isinstance(principal, dict) and principal_problems == []
              and len(principal_checks) > 0,
              problems=principal_problems)
        network = (principal or {}).get("network") or {}
        check("candidate_network_isolated",
              isinstance(network, dict)
              and (network.get("af_inet") or {}).get("ok") is False
              and (network.get("af_inet6") or {}).get("ok") is False
              and (network.get("dns") or {}).get("ok") is False,
              network=network)
        candidate_network_mode = candidate_record.get("network_mode")
        trusted_network_mode = trusted_record.get("network_mode")
        check("container_network_none",
              candidate_network_mode == "none" and trusted_network_mode == "none",
              candidate=candidate_network_mode, trusted=trusted_network_mode)
        env_names_all = []
        for record in (trusted_record, candidate_record):
            env_names_all.extend(record.get("env_names") or [])
        check("no_key_like_env_in_containers",
              not lib.key_like_names(env_names_all), names=env_names_all)
        principal_network = (principal or {}).get("network")
        if principal_network is not None:
            self.write_evidence_json("network-probe/candidate-network.json", {
                "utc": lib.utc(),
                "source": "candidate container self-report (Level C) + host uid map",
                "network": principal_network,
                "socket": (principal or {}).get("socket"),
            })
        self.write_evidence_json("network-probe/container-network.json", {
            "utc": lib.utc(),
            "trusted": {
                "network_mode": trusted_record.get("network_mode"),
                "env_names": trusted_record.get("env_names"),
            },
            "candidate": {
                "network_mode": candidate_record.get("network_mode"),
                "env_names": candidate_record.get("env_names"),
            },
            "expected": "none",
        })
        self.write_evidence_json("run/exits.json", {
            "utc": lib.utc(),
            "trusted": {"exit_code": trusted_record.get("exit_code"),
                        "status": trusted_record.get("status"),
                        "started_at": trusted_record.get("started_at"),
                        "finished_at": trusted_record.get("finished_at"),
                        "stop": self.records.get("trusted_stop")},
            "candidate": {"exit_code": candidate_record.get("exit_code"),
                          "status": candidate_record.get("status"),
                          "started_at": candidate_record.get("started_at"),
                          "finished_at": candidate_record.get("finished_at")},
            "host_utc": {"start": self.started_utc, "end": lib.utc()},
        })
        self.write_evidence_json("db/paths.json", {
            "run_id": self.run_id,
            "original_state_dir": str(self.run_dir / "state"),
            "copies": {
                "broker": str(self.evidence / "db" / "broker.sqlite3"),
                "attempts": str(self.evidence / "db" / "attempts.sqlite3"),
                "snapshot": str(self.evidence / "db" / "snapshot.json"),
            },
            "note": "copied after the Trusted container stopped; queried read-only",
        })
        self.checks = checks
        failures = [item for item in checks if not item["ok"]]
        self.records["checks"] = checks
        self.records["evaluation_failures"] = [item["id"] for item in failures]
        self.write_evidence_json("run/checks.json", {"checks": checks,
                                                     "failures": [item["id"] for item in failures]})
        if failures and self.exit_code == lib.EXIT_OK:
            self.exit_code = lib.EXIT_CASE_FAILED
            self.failure = {"reason": "CASE_FAILED",
                            "message": f"D1-C {self.args.scenario} assertions failed",
                            "detail": {"failures": [item["id"] for item in failures]}}

    # -- cleanup --------------------------------------------------------
    def cleanup(self) -> None:
        cleanup: dict = {"utc_start": lib.utc(), "steps": [], "problems": []}
        if not self.evidence_ready:
            return

        def step(name: str, record: dict) -> None:
            cleanup["steps"].append({"step": name, "utc": lib.utc(),
                                     "record": record})

        for role in ("candidate", "trusted"):
            name = self.candidate_name if role == "candidate" else self.trusted_name
            status = self.podman_status(name)
            if status is None:
                step(f"{role}-absent", {"present": False})
            if status is not None:
                if status == "running" and role == "trusted":
                    record = lib.terminate_container(
                        name, signal_fn=self._signal_container,
                        wait_exit=self._wait_exit,
                        grace_s=float(self.args.stop_grace), kill_wait_s=5.0)
                    step(f"stop-{role}", record)
                remove = self.cmd(["podman", "rm", "-f", name],
                                  name=f"cleanup-rm-{role}", timeout=60)
                step(f"rm-{role}", {"exit": remove["exit"]})
                if remove["exit"] != 0:
                    cleanup["problems"].append(f"rm_{role}_failed")
        socket_path = self.run_dir / "ipc" / "bridge.sock"
        step("unlink-socket", lib.unlink_socket(socket_path))
        lock_path = self.run_dir / "ipc" / "bridge.sock.lock"
        step("unlink-lock", lib.unlink_regular(lock_path, expected_uid=0))
        ipc_dir = self.run_dir / "ipc"
        try:
            if ipc_dir.is_dir() and not any(ipc_dir.iterdir()):
                ipc_dir.rmdir()
                step("rmdir-ipc", {"removed": True})
            else:
                step("rmdir-ipc", {"removed": False,
                                   "entries": sorted(p.name for p in ipc_dir.iterdir())
                                   if ipc_dir.is_dir() else []})
                if ipc_dir.is_dir():
                    cleanup["problems"].append("ipc_dir_not_empty")
        except OSError as exc:
            step("rmdir-ipc", {"removed": False, "error": type(exc).__name__})
            cleanup["problems"].append("rmdir_ipc_failed")
        if self.keep_run:
            step("run-dir", {"kept": True})
        else:
            try:
                delete_root = lib.G3D_ROOT / "runs"
                deletion = lib.safe_delete_tree(delete_root, self.run_dir)
                step("run-dir", deletion)
                if deletion.get("errors") or not deletion.get("removed"):
                    cleanup["problems"].append("run_dir_not_deleted")
            except lib.G3DError as exc:
                step("run-dir", {"error": str(exc)})
                cleanup["problems"].append("run_dir_delete_refused")
        ps = self.cmd(["podman", "ps", "-a", "--format", "{{.Names}}"],
                      name="cleanup-ps", timeout=30)
        names = [line for line in ps["stdout"].splitlines() if line.strip()]
        lib.write_bytes_atomic(self.evidence / "cleanup" / "ps-after.txt",
                               ("\n".join(names) + "\n").encode(), mode=0o444)
        if names:
            cleanup["problems"].append("podman_ps_not_empty")
        residual = lib.find_residual_processes(
            ["autoteacher_m0.bridge.controller", "fake_provider.py",
             "candidate_entry.py", "trusted_entry.py",
             "deepseek-harness-sdk-runtime", self.trusted_name, self.candidate_name],
            exclude_pids=[os.getpid()])
        self.write_evidence_json("cleanup/residual-processes.json", residual)
        if residual:
            cleanup["problems"].append("residual_processes")
        socket_record = lib.lstat_record(socket_path)
        run_dir_record = lib.lstat_record(self.run_dir)
        if socket_record is not None:
            cleanup["problems"].append("socket_still_present")
        if not self.keep_run and run_dir_record is not None:
            cleanup["problems"].append("run_dir_still_present")
        rootfs_after = lib.sha256_tree(lib.ROOTFS)
        deps_after = lib.sha256_tree(lib.DEPS)
        stage_after = lib.sha256_tree(self.stage_dir)
        canonical = {
            "utc": lib.utc(),
            "rootfs": {"sha256": rootfs_after, "expected": lib.ROOTFS_CANON,
                       "ok": rootfs_after == lib.ROOTFS_CANON},
            "deps": {"sha256": deps_after, "expected": lib.DEPS_CANON,
                     "ok": deps_after == lib.DEPS_CANON},
            "stage": {"sha256": stage_after,
                      "before": (self.records.get("stage") or {}).get("sha256"),
                      "ok": stage_after == (self.records.get("stage") or {}).get("sha256")},
        }
        cleanup["canonical"] = canonical
        self.write_evidence_json("env/canonical-post.json", canonical)
        if not canonical["rootfs"]["ok"] or not canonical["deps"]["ok"]:
            cleanup["problems"].append("canonical_drift")
        if not canonical["stage"]["ok"]:
            cleanup["problems"].append("stage_drift")
        cleanup["utc_end"] = lib.utc()
        cleanup["ok"] = not cleanup["problems"]
        self.records["cleanup"] = cleanup
        self.write_evidence_json("cleanup/cleanup.json", cleanup)
        if cleanup["problems"]:
            if any(problem in {"canonical_drift", "stage_drift"}
                   for problem in cleanup["problems"]) and self.exit_code == lib.EXIT_OK:
                self.exit_code = lib.EXIT_EVIDENCE_INTEGRITY
            elif self.exit_code == lib.EXIT_OK:
                self.exit_code = lib.EXIT_CLEANUP_RESIDUAL
            if self.failure is None:
                self.failure = {"reason": lib.FAIL_REASONS.get(self.exit_code, "CLEANUP"),
                                "message": "cleanup residual",
                                "detail": {"problems": cleanup["problems"]}}

    # -- evidence summary ----------------------------------------------
    def write_evidence(self) -> None:
        if not self.evidence_ready:
            return
        cleanup = self.records.get("cleanup") or {}
        canonical = cleanup.get("canonical") or {}
        summary = {
            "schema": "m0.g3d.d1c.summary.v1",
            "utc_start": self.started_utc,
            "utc_end": lib.utc(),
            "run_id": self.run_id,
            "case": self.case,
            "scenario": self.args.scenario,
            "sub": self.sub or None,
            "status": "PASS" if self.exit_code == lib.EXIT_OK else "FAIL",
            "exit_code": self.exit_code,
            "reason": None if self.exit_code == lib.EXIT_OK else
            (self.failure or {}).get("reason", lib.FAIL_REASONS.get(self.exit_code)),
            "failure": self.failure,
            "errors": self.errors,
            "stage": self.records.get("stage"),
            "configs": self.records.get("configs"),
            "containers": self.container_records,
            "candidate_exit_code": self.records.get("candidate_exit_code"),
            "trusted_stop": self.records.get("trusted_stop"),
            "socket": self.socket_records,
            "checks": self.checks,
            "cleanup": {"ok": cleanup.get("ok"), "problems": cleanup.get("problems"),
                        "utc_end": cleanup.get("utc_end")},
            "canonical": canonical,
            "synthetic": True,
            "real_model_calls": 0,
            "real_external_http_calls": 0,
            "has_real_key": False,
            "live_gate_status": "BLOCKED",
            "os_boundary_status": ("D1C_DUAL_PRINCIPAL_TOOL"
                                   if self.args.scenario == "tool"
                                   else "D1C_DUAL_PRINCIPAL_ECHO"),
        }
        self.write_evidence_json("summary.json", summary)
        cleanup_path = self.evidence / "cleanup" / "cleanup.json"
        if cleanup_path.is_file():
            lib.write_bytes_atomic(self.evidence / "cleanup.json",
                                   cleanup_path.read_bytes(), mode=0o444)
        text = [
            f"RUN_ID={self.run_id}",
            f"CASE={self.case}",
            f"STATUS={summary['status']}",
            f"EXIT={self.exit_code}",
            f"REASON={summary['reason']}",
            f"UTC_START={self.started_utc}",
            f"UTC_END={summary['utc_end']}",
            "CHECKS:",
            *[f"  {'PASS' if item['ok'] else 'FAIL'} {item['id']}"
              for item in self.checks],
            f"CHECK_FAILURES={[item['id'] for item in self.checks if not item['ok']]}",
            f"CLEANUP_OK={cleanup.get('ok')}",
            f"CLEANUP_PROBLEMS={cleanup.get('problems')}",
        ]
        lib.write_bytes_atomic(self.evidence / "run" / "run-summary.txt",
                               ("\n".join(text) + "\n").encode(), mode=0o444)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", default="d1-echo")
    parser.add_argument("--sub", default="", help="optional run-id suffix")
    parser.add_argument("--scenario", default="echo", choices=sorted(SCENARIO_PROMPT))
    parser.add_argument("--session", default="g3d-d1-s1")
    parser.add_argument("--prompt", default=None)
    parser.add_argument("--stage", default=None)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--evidence-dir", default=None)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--ready-timeout", type=float, default=25.0)
    parser.add_argument("--stop-grace", type=float, default=5.0)
    parser.add_argument("--keep-run", action="store_true")
    args = parser.parse_args(argv)
    if args.prompt is None:
        args.prompt = scenario_prompt(args.scenario)
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if os.geteuid() != 0:
        sys.stderr.write("BLOCKED_NEEDS_HOST_ROOT\n")
        return lib.EXIT_BLOCKED_ENVIRONMENT
    try:
        launcher = Launcher(args)
    except lib.G3DError as exc:
        sys.stderr.write(f"LAUNCH_FAILED {exc.reason}: {exc}\n")
        sys.stderr.write(json.dumps(exc.detail, indent=2, sort_keys=True) + "\n")
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
        except lib.G3DError as exc:
            launcher.failure = {"reason": exc.reason, "message": str(exc),
                                "detail": exc.detail}
            launcher.exit_code = exc.exit_code
            launcher.collect()
            launcher.evaluate()
    except lib.G3DError as exc:
        launcher.failure = {"reason": exc.reason, "message": str(exc),
                            "detail": exc.detail}
        launcher.exit_code = exc.exit_code
        launcher.record_error(exc.reason, str(exc), **exc.detail)
        try:
            launcher.collect()
        except Exception as collect_exc:  # noqa: BLE001
            launcher.record_error("COLLECT_FAILED",
                                  f"{type(collect_exc).__name__}: {collect_exc}")
    except Exception as exc:  # noqa: BLE001 - never lose evidence
        launcher.failure = {"reason": "INTERNAL", "message": str(exc),
                            "traceback": traceback.format_exc()[-4000:]}
        launcher.exit_code = lib.EXIT_CASE_FAILED
        launcher.record_error("INTERNAL", f"{type(exc).__name__}: {exc}")
    try:
        launcher.cleanup()
    except Exception as exc:  # noqa: BLE001
        launcher.record_error("CLEANUP_EXCEPTION", f"{type(exc).__name__}: {exc}")
        if launcher.exit_code == lib.EXIT_OK:
            launcher.exit_code = lib.EXIT_CLEANUP_RESIDUAL
    try:
        launcher.write_evidence()
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"EVIDENCE_WRITE_FAILED {type(exc).__name__}: {exc}\n")
        if launcher.exit_code == lib.EXIT_OK:
            launcher.exit_code = lib.EXIT_EVIDENCE_INTEGRITY
    print(json.dumps({"run_id": launcher.run_id,
                      "status": "PASS" if launcher.exit_code == 0 else "FAIL",
                      "exit": launcher.exit_code,
                      "evidence": str(launcher.evidence),
                      "failure": launcher.failure}, sort_keys=True))
    return launcher.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
