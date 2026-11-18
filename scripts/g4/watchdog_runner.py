#!/usr/bin/env python3
"""G4-D external watchdog: a trusted supervisor *outside* Candidate and Trusted.

The watchdog is a separate host process. It is not a thread inside the candidate
or the trusted controller, and it is not a read-only elapsed() diagnostic. It
owns one supervised target (the G4-C/D launcher, i.e. the Controller-of-record),
and on deadline / hang / injected failure it must:

1. snapshot the real container processes it will terminate (pid, uid_map,
   mountinfo, socket, cgroup limits);
2. SIGTERM the whole process tree, wait a bounded grace, then SIGKILL the tree
   *and* any process that detached from the tree (found by run-specific markers
   in argv/environ/cwd);
3. remove every container of this run and then re-observe absence with
   ``podman ps -a`` - a successful ``rm -f`` return code is never accepted as
   absence;
4. unlink/re-observe the UDS and delete/re-observe the run dir;
5. leave the reservation/attempt outcome conservative (PENDING/UNKNOWN,
   ``retry_allowed=false``) and never start a second attempt.

Failure of any observation step is fail-closed: the process exits non-zero and
records ``BLOCKED`` plus the manual cleanup command. It never claims success.

No Key, no model, no external HTTP, no ``podman pull``. Every command is recorded
in ``commands.jsonl``; no command output is treated as proof without an explicit
re-check.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import resource
import signal
import stat
import subprocess
import sys
import time
from typing import Mapping, Sequence

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "g3d"))
sys.path.insert(0, str(REPO / "src"))
import lib_g3d as lib3d  # noqa: E402

from autoteacher_m0.security.watchdog import (  # noqa: E402
    PendingConservative,
    confirm_path_absence,
    confirm_process_absence,
    kill_process_tree,
    scan_marked_processes,
)

SCHEMA = "m0.g4d.watchdog.v1"
EXIT_OK = 0
EXIT_TARGET_EARLY = 3
EXIT_ABSENCE = 4
EXIT_ENGINE = 5
EXIT_SELF_FAILURE = 6
EXIT_PREFLIGHT = 7

CLEAN_ENV = {
    "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
    "HOME": "/root",
    "LANG": "C",
    "LC_ALL": "C",
    "PYTHONDONTWRITEBYTECODE": "1",
    "TMPDIR": "/tmp",
}
RLIMITS = {
    "cpu": resource.RLIMIT_CPU,
    "as": resource.RLIMIT_AS,
    "nofile": resource.RLIMIT_NOFILE,
    "fsize": resource.RLIMIT_FSIZE,
    "nproc": resource.RLIMIT_NPROC,
    "core": resource.RLIMIT_CORE,
}


def utc() -> str:
    return lib3d.utc()


def ancestor_pids(pid: int | None = None) -> set[int]:
    """The shell/orchestrator that invoked the watchdog is not a runaway child."""
    ancestors: set[int] = set()
    current = int(pid if pid is not None else os.getpid())
    for _ in range(64):
        try:
            stat = Path(f"/proc/{current}/stat").read_text(encoding="ascii")
        except (OSError, UnicodeError):
            break
        try:
            current = int(stat[stat.rindex(")") + 2:].split()[1])
        except (ValueError, IndexError):
            break
        if current <= 1 or current in ancestors:
            break
        ancestors.add(current)
    return ancestors


def write_json(path: Path, document: object, *, mode: int = 0o600) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(document, indent=2, sort_keys=True, default=str) + "\n").encode()
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    os.chmod(tmp, mode)
    tmp.replace(path)
    return {"path": str(path), "sha256": lib3d.sha256_bytes(data), "bytes": len(data)}


def write_bytes(path: Path, data: bytes, *, mode: int = 0o600) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    os.chmod(path, mode)
    return {"path": str(path), "sha256": lib3d.sha256_bytes(data), "bytes": len(data)}


class ExternalWatchdogRunner:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.evidence = Path(args.evidence).resolve()
        self.run_dir = Path(args.run_dir).resolve() if args.run_dir else None
        self.run_root = self.run_dir.parent if self.run_dir else None
        self.socket_path = (self.run_dir / "ipc" / "bridge.sock") if self.run_dir else None
        self.lock_path = (self.run_dir / "ipc" / "bridge.sock.lock") if self.run_dir else None
        self.commands_path = self.evidence / "commands.jsonl"
        self.outcome: dict = {}
        self.checks: list[dict] = []
        self.target: subprocess.Popen[bytes] | None = None
        self.reason = ""
        self.trigger_utc = ""
        self.up_at: float | None = None
        self.injected = False
        self.watchdog_signal: int | None = None
        self.containers: dict[str, dict] = {}
        self.engine_failures: list[str] = []
        self.query_ok: dict[str, bool] = {}
        self._last_container_poll = 0.0
        self.start_monotonic = time.monotonic()
        self.utc_start = utc()
        self.target_logs: dict[str, object] = {}
        self.residual_after: list[dict] = []

    # -- evidence helpers -------------------------------------------------
    def check(self, check_id: str, ok: bool, **detail: object) -> None:
        if any(item["id"] == check_id for item in self.checks):
            return
        self.checks.append({"id": check_id, "ok": bool(ok), "detail": detail})
        if not ok:
            self.engine_failures.append(check_id)

    def cmd(self, argv: Sequence[str], *, name: str, timeout: float = 30.0,
            env: Mapping[str, str] | None = None) -> dict:
        started = utc()
        record: dict = {"name": name, "argv": [str(item) for item in argv],
                        "utc_start": started, "utc_end": None, "exit": None}
        try:
            proc = subprocess.run([str(item) for item in argv],
                                  env=dict(env or CLEAN_ENV), cwd=str(REPO),
                                  stdin=subprocess.DEVNULL, capture_output=True,
                                  text=True, timeout=timeout)
            record.update({"exit": proc.returncode, "stdout": proc.stdout[-8000:],
                           "stderr": proc.stderr[-8000:]})
        except subprocess.TimeoutExpired as error:
            record.update({"exit": 124, "timed_out": True,
                           "stdout": lib3d._decode_timeout_stream(error.stdout)[-8000:],
                           "stderr": lib3d._decode_timeout_stream(error.stderr)[-8000:]})
        except OSError as error:
            record.update({"exit": 127, "error": type(error).__name__})
        record["utc_end"] = utc()
        self.evidence.mkdir(parents=True, exist_ok=True)
        lib3d.append_jsonl(self.commands_path, record)
        return record

    # -- preflight --------------------------------------------------------
    def preflight(self) -> None:
        if self.evidence.exists() and any(self.evidence.iterdir()):
            raise SystemExit(f"G4D_EVIDENCE_NOT_EMPTY {self.evidence}")
        self.evidence.mkdir(parents=True, exist_ok=True)
        self.check("host_root", os.geteuid() == 0, euid=os.geteuid())
        if not self.target_argv:
            raise SystemExit("G4D_TARGET_ARGV_MISSING")
        if self.run_dir is not None:
            self.check("run_dir_absent_before_start", not self.run_dir.exists(),
                       run_dir=str(self.run_dir))
        pre = self.cmd([self.args.engine, "ps", "-a", "--format", "{{.Names}}"],
                       name="preflight-ps", timeout=30)
        names = [line.strip() for line in (pre.get("stdout") or "").splitlines()
                 if line.strip()]
        self.check("podman_ps_preflight_ok", pre.get("exit") == 0, exit=pre.get("exit"))
        self.check("containers_absent_preflight", not names, names=names[:20])
        write_json(self.evidence / "preflight.json", {
            "schema": SCHEMA, "utc": utc(), "argv": [str(item) for item in self.target_argv],
            "watchdog_argv": sys.argv, "engine": self.args.engine,
            "run_dir": str(self.run_dir) if self.run_dir else None,
            "run_id": self.args.run_id, "uid": os.geteuid(),
            "hostname": os.uname().nodename,
            "sandbox": {"network": "none (target containers)", "key_present": False,
                        "live_gate": "BLOCKED"},
        })
        if self.engine_failures:
            raise SystemExit(EXIT_PREFLIGHT)

    # -- target -----------------------------------------------------------
    @property
    def target_argv(self) -> list[str]:
        return list(self.args.target)

    def _preexec(self):
        limits = self.args.limit_specs

        def apply() -> None:
            for name, value in limits:
                which = RLIMITS[name]
                current = resource.getrlimit(which)
                hard = os.RLIM_INFINITY if current[1] == os.RLIM_INFINITY else current[1]
                soft = min(value, hard)
                resource.setrlimit(which, (soft, hard))

        return apply

    def start_target(self) -> None:
        stdout_path = self.evidence / "logs" / "target.stdout.txt"
        stderr_path = self.evidence / "logs" / "target.stderr.txt"
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        # Truncate before spawn; the file handles stay open for the child's life.
        stdout_path.write_bytes(b"")
        stderr_path.write_bytes(b"")
        with stdout_path.open("wb") as out, stderr_path.open("wb") as err:
            self.target = subprocess.Popen(
                [str(item) for item in self.target_argv],
                cwd=str(REPO), env=dict(CLEAN_ENV),
                stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                start_new_session=True,
                preexec_fn=self._preexec() if self.args.limit_specs else None)
        try:
            pgid = os.getpgid(self.target.pid)
        except ProcessLookupError:
            pgid = None
        self.target_logs = {
            "pid": self.target.pid,
            "pgid": pgid,
            "utc": utc(),
            "stdout": str(stdout_path), "stderr": str(stderr_path),
        }
        write_json(self.evidence / "target.json", self.target_logs)
        self.check("target_started", self.target.pid > 0, pid=self.target.pid)

    # -- container discovery ---------------------------------------------
    def list_containers(self, *, label: str) -> list[dict]:
        record = self.cmd([self.args.engine, "ps", "-a",
                           "--format", "{{.ID}}\t{{.Names}}\t{{.State}}"],
                          name=label, timeout=30)
        rows: list[dict] = []
        self.query_ok[label] = record.get("exit") == 0
        if record.get("exit") != 0:
            self.check(f"{label}_query_ok", False, exit=record.get("exit"))
            return rows
        self.check(f"{label}_query_ok", True)
        for line in (record.get("stdout") or "").splitlines():
            parts = line.split("\t")
            if len(parts) >= 3 and parts[1].strip():
                rows.append({"id": parts[0].strip(), "name": parts[1].strip(),
                             "state": parts[2].strip()})
        return rows

    def refresh_containers(self) -> None:
        now = time.monotonic()
        if now - self._last_container_poll < self.args.poll_containers:
            return
        self._last_container_poll = now
        rows = self.list_containers(label="poll-ps")
        mine = [row for row in rows if self.args.run_id and self.args.run_id in row["name"]]
        self.containers.update({row["name"]: row for row in mine})
        if self.args.require_containers:
            running = [row for row in mine
                       if row["state"].lower() in {"running", "paused", "created"}]
            if len(running) >= self.args.require_containers and self.up_at is None:
                self.up_at = time.monotonic()
                self.on_up()

    def inspect_container(self, name: str, *, label: str) -> dict | None:
        record = self.cmd([self.args.engine, "inspect", name], name=label, timeout=30)
        if record.get("exit") != 0:
            return None
        try:
            document = json.loads(record.get("stdout") or "null")
        except json.JSONDecodeError:
            return None
        if isinstance(document, list):
            return document[0] if document else None
        return document

    def snapshot_containers(self, *, tag: str) -> dict:
        snapshot: dict = {"schema": SCHEMA, "utc": utc(), "tag": tag, "containers": {}}
        for name, row in sorted(self.containers.items()):
            document = self.inspect_container(name, label=f"inspect-{tag}-{name}")
            entry: dict = {"row": row, "inspect": None, "proc": {}}
            if document:
                state = document.get("State") or {}
                config = document.get("Config") or {}
                host = document.get("HostConfig") or {}
                pid = state.get("Pid")
                entry["inspect"] = {
                    "id": document.get("Id"),
                    "name": document.get("Name"),
                    "state": {key: state.get(key) for key in
                              ("Status", "Running", "Paused", "Pid", "ExitCode")},
                    "image": document.get("Image"),
                    "mounts": [{key: mount.get(key) for key in
                                ("Source", "Destination", "RW", "Type")}
                               for mount in (document.get("Mounts") or [])],
                    "env_names": sorted({item.split("=", 1)[0] for item in
                                         (config.get("Env") or []) if "=" in item}),
                    "host_config": {key: host.get(key) for key in
                                    ("PidsLimit", "Memory", "MemorySwap", "NanoCpus",
                                     "Ulimits", "ReadonlyRootfs", "NetworkMode",
                                     "CapDrop", "SecurityOpt", "UsernsMode",
                                     "Tmpfs")},
                }
                if isinstance(pid, int) and pid > 0:
                    entry["proc"] = self.capture_proc(pid, tag=tag, name=name)
            snapshot["containers"][name] = entry
        return snapshot

    def capture_proc(self, pid: int, *, tag: str, name: str) -> dict:
        directory = self.evidence / "proc" / tag
        directory.mkdir(parents=True, exist_ok=True)
        surfaces: dict[str, object] = {"pid": pid}
        for surface, filename, limit in (("uid_map", "uid_map", 1 << 16),
                                         ("mountinfo", "mountinfo", 1 << 22),
                                         ("status", "status", 1 << 16),
                                         ("cgroup", "cgroup", 1 << 16),
                                         ("cmdline", "cmdline", 1 << 16)):
            try:
                data = (Path("/proc") / str(pid) / surface).read_bytes()[:limit]
            except OSError as error:
                surfaces[surface] = {"present": False, "error": type(error).__name__}
                continue
            stored = write_bytes(directory / f"{name}-{pid}-{filename}", data)
            text = data.decode("utf-8", "replace")
            item: dict = {"present": True, "sha256": stored["sha256"],
                          "bytes": stored["bytes"], "path": stored["path"]}
            if surface == "mountinfo":
                item["line_count"] = len(text.splitlines())
                item["g4_paths"] = [line for line in text.splitlines()
                                    if str(REPO) in line][:40]
            if surface == "cgroup":
                item["text"] = text.strip()[:2000]
                item["limits"] = self.cgroup_limits(pid)
            if surface == "status":
                item["uid_line"] = next((line for line in text.splitlines()
                                         if line.startswith("Uid:")), None)
            surfaces[surface] = item
        return surfaces

    @staticmethod
    def cgroup_limits(pid: int) -> dict:
        limits: dict[str, object] = {}
        try:
            cgroup = (Path("/proc") / str(pid) / "cgroup").read_text(encoding="utf-8")
        except OSError:
            return limits
        for line in cgroup.splitlines():
            parts = line.split(":", 2)
            if len(parts) != 3 or not parts[2].startswith("/"):
                continue
            base = Path("/sys/fs/cgroup") / parts[2].lstrip("/")
            for key in ("pids.max", "pids.current", "memory.max", "memory.current",
                        "cpu.max", "cpu.weight"):
                path = base / key
                try:
                    limits[key] = path.read_text(encoding="utf-8").strip()[:200]
                except OSError:
                    continue
        return limits

    def socket_record(self) -> dict:
        if self.socket_path is None:
            return {"present": False, "reason": "no run dir"}
        record: dict = {"path": str(self.socket_path)}
        try:
            info = os.lstat(self.socket_path)
        except FileNotFoundError:
            record["present"] = False
            return record
        record.update({"present": True, "mode": oct(info.st_mode & 0o7777),
                       "uid": info.st_uid, "gid": info.st_gid,
                       "inode": info.st_ino, "is_socket": stat.S_ISSOCK(info.st_mode)})
        if stat.S_ISSOCK(info.st_mode):
            record["peercred"] = self.peercred_probe()
        return record

    def peercred_probe(self) -> dict:
        """Client-observed SO_PEERCRED of the trusted server (not a secret)."""
        if self.socket_path is None:
            return {"ok": False, "reason": "no socket"}
        code = (
            "import json, socket, sys\n"
            "s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)\n"
            "s.settimeout(2)\n"
            "s.connect(sys.argv[1])\n"
            "cred = s.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)\n"
            "pid, uid, gid = (int.from_bytes(cred[0:4], 'little'),\n"
            "                 int.from_bytes(cred[4:8], 'little'),\n"
            "                 int.from_bytes(cred[8:12], 'little'))\n"
            "print(json.dumps({'pid': pid, 'uid': uid, 'gid': gid}))\n"
        )
        record = self.cmd([sys.executable, "-B", "-c", code, str(self.socket_path)],
                          name="peercred-probe", timeout=10)
        if record.get("exit") != 0:
            return {"ok": False, "exit": record.get("exit"),
                    "stderr": record.get("stderr")}
        try:
            document = json.loads((record.get("stdout") or "").strip().splitlines()[-1])
        except (json.JSONDecodeError, IndexError):
            return {"ok": False, "reason": "unparsable"}
        document["ok"] = True
        document["observed_by"] = "client (root); server-side candidate uid comes " \
                                  "from the trusted peercred evidence of the same run"
        return document

    # -- injection / trigger ---------------------------------------------
    def on_up(self) -> None:
        self.check("containers_up", True, names=sorted(self.containers))
        live = self.snapshot_containers(tag="up")
        write_json(self.evidence / "snapshots" / "containers-up.json", live)
        live_proc = {}
        for name, entry in live["containers"].items():
            pid = ((entry.get("inspect") or {}).get("state") or {}).get("Pid")
            if isinstance(pid, int) and pid > 0:
                live_proc[name] = pid
        write_json(self.evidence / "snapshots" / "live-pids.json", live_proc)
        write_json(self.evidence / "snapshots" / "socket-at-up.json", self.socket_record())
        if self.args.capture_live:
            self.capture_live_surfaces(live_proc)
        if self.args.exec_probe:
            self.run_exec_probe()
        if self.args.pause_role and not self.injected:
            self.inject_pause(self.args.pause_role)

    def capture_live_surfaces(self, pids: Mapping[str, int]) -> None:
        """D03/D15: live /proc surfaces of the real Candidate principal."""
        document: dict = {"schema": "m0.g4d.live-surfaces.v1", "utc": utc()}
        directory = self.evidence / "live"
        for role, pid in sorted(pids.items()):
            entry: dict = {"pid": pid}
            for surface, limit in (("environ", 1 << 20), ("cmdline", 1 << 16),
                                   ("mountinfo", 1 << 22)):
                try:
                    data = (Path("/proc") / str(pid) / surface).read_bytes()[:limit]
                except OSError as error:
                    entry[surface] = {"present": False, "error": type(error).__name__}
                    continue
                stored = write_bytes(directory / f"{role}-{pid}-{surface}.txt", data)
                text = data.decode("utf-8", "replace")
                entry[surface] = {
                    "present": True, "sha256": stored["sha256"],
                    "bytes": stored["bytes"], "path": stored["path"],
                    "sentinel_count": text.count("TEST_ONLY_NEVER_VALID_SECRET_SENTINEL"),
                    "env_names": (sorted({line.split("=", 1)[0] for line in text.splitlines()
                                          if "=" in line})[:200]
                                  if surface == "environ" else None),
                }
            document[role] = entry
        write_json(self.evidence / "live" / "surfaces.json", document)

    def run_exec_probe(self) -> None:
        """Run the candidate-principal known-path probe via ``podman exec``."""
        role = self.args.exec_role
        name = next((item for item in self.containers if role in item), None)
        if name is None:
            self.check("exec_probe_container_found", False, role=role,
                       known=sorted(self.containers))
            return
        source = Path(self.args.exec_probe).read_text(encoding="utf-8")
        argv = [self.args.engine, "exec", name, "/opt/python/bin/python3.11",
                "-B", "-c", source, self.args.exec_arg or "{}"]
        record = self.cmd(argv, name=f"exec-probe-{role}", timeout=60)
        document: dict = {"schema": "m0.g4d.exec-probe.v1", "utc": utc(),
                          "role": role, "container": name,
                          "exit": record.get("exit"),
                          "argv": record.get("argv"),
                          "stdout": record.get("stdout"),
                          "stderr": record.get("stderr"),
                          "result": None}
        for line in reversed((record.get("stdout") or "").splitlines()):
            if line.startswith("G4D_ISO_PROBE "):
                try:
                    document["result"] = json.loads(line[len("G4D_ISO_PROBE "):])
                except json.JSONDecodeError:
                    pass
                break
        write_json(self.evidence / "probes" / f"exec-{role}.json", document)
        self.check("exec_probe_ran", record.get("exit") == 0
                   and isinstance(document["result"], dict),
                   exit=record.get("exit"), role=role)

    def inject_pause(self, role: str) -> None:
        name = next((item for item in self.containers if role in item), None)
        if name is None:
            self.check("injection_container_found", False, role=role,
                       known=sorted(self.containers))
            return
        record = self.cmd([self.args.engine, "pause", name],
                          name=f"inject-pause-{role}", timeout=30)
        self.injected = True
        self.check("injection_pause_applied", record.get("exit") == 0,
                   container=name, exit=record.get("exit"))
        write_json(self.evidence / "cleanup" / "injection.json", {
            "kind": "podman-pause", "role": role, "container": name,
            "utc": utc(), "record": record,
        })

    def wait_for_target(self) -> None:
        assert self.target is not None
        deadline = self.args.deadline
        while True:
            now = time.monotonic()
            if self.watchdog_signal is not None:
                self.reason = f"WATCHDOG_SIGNALLED:{self.watchdog_signal}"
                self.trigger_utc = utc()
                return
            if self.args.self_fail_after is not None:
                if now - self.start_monotonic >= self.args.self_fail_after:
                    self.reason = "WATCHDOG_SELF_FAILURE"
                    self.trigger_utc = utc()
                    raise RuntimeError("injected watchdog monitor failure")
            self.refresh_containers()
            if self.up_at is not None and self.args.kill_after_up is not None:
                if now - self.up_at >= self.args.kill_after_up:
                    self.reason = "WATCHDOG_DEADLINE_AFTER_UP"
                    self.trigger_utc = utc()
                    return
            if now - self.start_monotonic >= deadline:
                self.reason = "WATCHDOG_TOTAL_DEADLINE"
                self.trigger_utc = utc()
                return
            if self.target.poll() is not None:
                self.reason = "TARGET_EXITED"
                self.trigger_utc = utc()
                return
            time.sleep(self.args.poll)

    # -- termination / absence -------------------------------------------
    def terminate(self) -> dict:
        assert self.target is not None
        pre_kill = self.snapshot_containers(tag="pre-kill")
        write_json(self.evidence / "snapshots" / "containers-pre-kill.json", pre_kill)
        write_json(self.evidence / "snapshots" / "socket-pre-kill.json",
                   self.socket_record())
        if self.target.poll() is None:
            try:
                result = kill_process_tree(
                    self.target, grace_seconds=self.args.term_grace)
            except BaseException as error:  # noqa: BLE001 - record, then fail closed
                write_json(self.evidence / "cleanup" / "kill-error.json",
                           {"error": type(error).__name__, "utc": utc()})
                return {"ok": False, "error": type(error).__name__}
            kill_record = {
                "root_pid": result.root_pid, "signaled": list(result.signaled),
                "survivors": list(result.survivors),
                "confirmed_absent": result.confirmed_absent, "utc": utc(),
            }
            write_json(self.evidence / "cleanup" / "kill.json", kill_record)
            self.check("process_tree_killed", result.confirmed_absent,
                       root_pid=result.root_pid, survivors=list(result.survivors))
        else:
            kill_record = {"root_pid": self.target.pid, "already_exited": True,
                           "utc": utc()}
            write_json(self.evidence / "cleanup" / "kill.json", kill_record)
            self.check("process_tree_killed", True, already_exited=True)
        # Detached/reparented children are not in the parent edge set.
        scanned: list[dict] = []
        killed: list[int] = []
        protected = {os.getpid()} | ancestor_pids()
        for _ in range(50):
            found = scan_marked_processes(self.markers, exclude_pids=sorted(protected))
            if not found:
                break
            scanned.extend(found)
            for row in found:
                try:
                    os.kill(row["pid"], signal.SIGKILL)
                    killed.append(row["pid"])
                except (ProcessLookupError, PermissionError):
                    continue
            time.sleep(0.02)
        write_json(self.evidence / "cleanup" / "escaped-processes.json",
                   {"scanned": scanned[-50:], "killed": sorted(set(killed))})
        self.check("no_escaped_processes", not scan_marked_processes(
            self.markers, exclude_pids=sorted(protected)))
        pids = {self.target.pid, *kill_record.get("signaled", []),
                *kill_record.get("survivors", [])}
        pids.update(row["pid"] for row in self.containers.values() if row.get("pid"))
        for entry in (pre_kill.get("containers") or {}).values():
            pid = (((entry.get("inspect") or {}).get("state") or {}).get("Pid"))
            if isinstance(pid, int) and pid > 0:
                pids.add(pid)
        report = confirm_process_absence(sorted(pids))
        write_json(self.evidence / "absence" / "processes.json", {
            "checked": list(report.checked), "absent": list(report.absent),
            "survivors": list(report.survivors),
            "proc_entries": list(report.proc_entries),
            "utc": utc(),
        })
        self.check("processes_absent", report.confirmed, survivors=list(report.survivors))
        return {"ok": report.confirmed, "kill": kill_record,
                "pids": sorted(pids), "report": report}

    @property
    def target_exit_ok(self) -> set[int]:
        allowed: set[int] = set()
        for item in str(self.args.target_exit_ok).split(","):
            item = item.strip()
            if item:
                allowed.add(int(item))
        return allowed

    @property
    def markers(self) -> list[str]:
        values = ["launch_c.py", "trusted_entry.py", "candidate_entry.py",
                  "fake_provider.py"]
        if self.args.run_id:
            values.append(self.args.run_id)
        if self.run_dir is not None:
            values.append(str(self.run_dir))
        values.extend(self.containers)
        return [value for value in dict.fromkeys(values) if value]

    def cleanup_containers(self) -> dict:
        rows = self.list_containers(label="cleanup-ps-before")
        before_ok = self.query_ok.get("cleanup-ps-before", False)
        names = sorted({row["name"] for row in rows
                        if self.args.run_id and self.args.run_id in row["name"]})
        for name in names:
            self.cmd([self.args.engine, "kill", "-s", "KILL", name],
                     name=f"kill-container-{name}", timeout=30)
            record = self.cmd([self.args.engine, "rm", "-f", name],
                              name=f"rm-container-{name}", timeout=60)
            self.check(f"rm_rc_{name}", record.get("exit") == 0, exit=record.get("exit"))
        after = self.list_containers(label="cleanup-ps-after")
        after_ok = self.query_ok.get("cleanup-ps-after", False)
        after_names = sorted({row["name"] for row in after
                              if self.args.run_id and self.args.run_id in row["name"]})
        write_bytes(self.evidence / "cleanup" / "ps-after.txt",
                    ("\n".join(after_names) + ("\n" if after_names else "")).encode())
        self.check("containers_absent_after_rm", after_ok and not after_names,
                   names=after_names, query_ok=after_ok, before_ok=before_ok)
        inspects = {}
        for name in names:
            record = self.cmd([self.args.engine, "inspect", name],
                              name=f"verify-absent-{name}", timeout=30)
            inspects[name] = {"exit": record.get("exit"),
                              "stdout_empty": not (record.get("stdout") or "").strip()}
            self.check(f"inspect_absent_{name}", record.get("exit") != 0,
                       exit=record.get("exit"))
        write_json(self.evidence / "cleanup" / "container-absence.json",
                   {"removed": names, "ps_after": after_names, "inspect": inspects,
                    "utc": utc()})
        return {"removed": names, "after": after_names, "inspect": inspects}

    def cleanup_paths(self) -> dict:
        result: dict = {"socket": None, "run_dir": None}
        if self.socket_path is not None:
            record = self.socket_record()
            write_json(self.evidence / "cleanup" / "socket-before-unlink.json", record)
            if record.get("present"):
                if record.get("is_socket") and record.get("uid") == 0:
                    try:
                        os.unlink(self.socket_path)
                    except OSError as error:
                        result["socket_unlink_error"] = type(error).__name__
                else:
                    self.check("socket_deletable", False,
                               reason="not a root-owned socket", record=record)
            if self.lock_path is not None:
                try:
                    if self.lock_path.is_file() and not self.lock_path.is_symlink():
                        reason = lib3d.unlink_regular(self.lock_path, expected_uid=0)
                        write_json(self.evidence / "cleanup" / "lock-unlink.json", reason)
                except (OSError, lib3d.G3DError) as error:
                    write_json(self.evidence / "cleanup" / "lock-unlink.json",
                               {"error": type(error).__name__})
            socket_absence = confirm_path_absence([self.socket_path])
            result["socket"] = {"present": list(socket_absence.present),
                                "details": {key: dict(value) for key, value
                                            in socket_absence.details.items()}}
            self.check("socket_absent", socket_absence.confirmed,
                       present=list(socket_absence.present))
        if self.run_dir is not None and self.run_root is not None:
            self.copy_run_evidence()
            if self.run_dir.exists():
                try:
                    deletion = lib3d.safe_delete_tree(self.run_root, self.run_dir)
                except lib3d.G3DError as error:
                    deletion = {"error": str(error)}
                result["run_dir"] = deletion
                write_json(self.evidence / "cleanup" / "run-dir-delete.json", deletion)
            run_absence = confirm_path_absence([self.run_dir])
            result["run_dir_present_after"] = list(run_absence.present)
            self.check("run_dir_absent", run_absence.confirmed,
                       present=list(run_absence.present))
        return result

    def copy_run_evidence(self) -> None:
        if self.run_dir is None or not self.run_dir.exists():
            return
        copied: list[dict] = []
        for relative in ("state", "evidence"):
            source_root = self.run_dir / relative
            if not source_root.is_dir():
                continue
            for path in sorted(source_root.rglob("*")):
                if not path.is_file() or path.is_symlink():
                    continue
                try:
                    info = path.stat()
                except OSError:
                    continue
                if info.st_size > (32 << 20):
                    continue
                data = path.read_bytes()
                target = self.evidence / "run-copy" / relative / path.relative_to(source_root)
                record = write_bytes(target, data)
                copied.append({"source": str(path), "stored": record["path"],
                               "sha256": record["sha256"], "bytes": record["bytes"]})
        write_json(self.evidence / "run-copy" / "manifest.json", {
            "utc": utc(), "run_dir": str(self.run_dir), "files": copied})
        ledger = self.ledger_summary()
        write_json(self.evidence / "run-copy" / "ledger-summary.json", ledger)

    def ledger_summary(self) -> dict:
        summary: dict = {"databases": {}, "send_journal": None, "utc": utc()}
        if self.run_dir is None:
            return summary
        import sqlite3
        for path in sorted((self.run_dir / "state").glob("*.sqlite3")):
            try:
                connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
                tables = [row[0] for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'")]
                counts = {}
                for table in tables:
                    try:
                        counts[table] = connection.execute(
                            f"SELECT COUNT(*) FROM '{table}'").fetchone()[0]
                    except sqlite3.Error:
                        counts[table] = None
                connection.close()
                summary["databases"][path.name] = {"tables": counts}
            except sqlite3.Error as error:
                summary["databases"][path.name] = {"error": str(error)[:200]}
        journal = self.run_dir / "state" / "g4c-send-journal.jsonl"
        if journal.is_file():
            decisions: dict[str, int] = {}
            for line in journal.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                decision = str(row.get("decision") or row.get("consume") or "UNKNOWN")
                decisions[decision] = decisions.get(decision, 0) + 1
            summary["send_journal"] = {"decisions": decisions}
        return summary

    # -- outcome ----------------------------------------------------------
    def run(self) -> int:
        try:
            self.preflight()
        except SystemExit as error:
            if isinstance(error.code, str):
                sys.stderr.write(error.code + "\n")
                return EXIT_PREFLIGHT
            return int(error.code or EXIT_PREFLIGHT)
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, self._on_signal)
        self.start_target()
        failure: BaseException | None = None
        try:
            self.wait_for_target()
        except BaseException as error:  # noqa: BLE001 - injected/local failure
            failure = error
            self.reason = self.reason or "WATCHDOG_SELF_FAILURE"
            self.trigger_utc = self.trigger_utc or utc()
        self.check("trigger_recorded", bool(self.reason), reason=self.reason)
        termination = self.terminate()
        containers = self.cleanup_containers()
        paths = self.cleanup_paths()
        target_exit = self.target.returncode if self.target is not None else None
        if target_exit is None and self.target is not None:
            try:
                target_exit = self.target.wait(timeout=5)
            except subprocess.TimeoutExpired:
                target_exit = None
        self.check("target_exit_recorded", target_exit is not None, exit=target_exit)
        pending = PendingConservative(
            reason=self.reason or "WATCHDOG_TERMINATED",
            retry_allowed=False, worst_case_reserved=True)
        write_json(self.evidence / "pending.json", {
            "schema": "m0.g4d.pending.v1", "utc": utc(),
            "status": pending.status, "reason": pending.reason,
            "retry_allowed": pending.retry_allowed,
            "worst_case_reserved": pending.worst_case_reserved,
            "reservation": "UNKNOWN_OR_PENDING", "attempt": "UNKNOWN_OR_PENDING",
        })
        self.check("retry_forbidden", pending.retry_allowed is False)
        if self.args.expect == "trigger":
            self.check("killed_by_watchdog", self.reason not in {"TARGET_EXITED", ""},
                       reason=self.reason)
        else:
            self.check("target_completed", self.reason == "TARGET_EXITED"
                       and target_exit in self.target_exit_ok,
                       reason=self.reason, exit=target_exit,
                       allowed=self.target_exit_ok)
        ok = all(item["ok"] for item in self.checks) and failure is None
        status = "PASS" if ok else ("WATCHDOG_SELF_FAILURE" if failure is not None
                                    else "FAIL_CLOSED")
        if failure is not None:
            exit_code = EXIT_SELF_FAILURE
        elif not ok:
            exit_code = EXIT_ABSENCE if any(
                not item["ok"] for item in self.checks
                if item["id"].startswith(("container", "socket", "run_dir", "process",
                                          "no_escaped", "rm_rc", "inspect_absent"))) \
                else EXIT_TARGET_EARLY
        else:
            exit_code = EXIT_OK
        outcome = {
            "schema": SCHEMA,
            "utc_start": self.utc_start,
            "utc_end": utc(),
            "argv": [str(item) for item in self.target_argv],
            "watchdog_argv": sys.argv,
            "engine": self.args.engine,
            "run_id": self.args.run_id,
            "run_dir": str(self.run_dir) if self.run_dir else None,
            "evidence": str(self.evidence),
            "reason": self.reason,
            "trigger_utc": self.trigger_utc,
            "target": {**self.target_logs, "exit": target_exit,
                       "log_stdout_sha256": lib3d.sha256_file(
                           self.evidence / "logs" / "target.stdout.txt")
                       if (self.evidence / "logs" / "target.stdout.txt").is_file() else None,
                       "log_stderr_sha256": lib3d.sha256_file(
                           self.evidence / "logs" / "target.stderr.txt")
                       if (self.evidence / "logs" / "target.stderr.txt").is_file() else None},
            "containers": containers,
            "termination": {"ok": bool(termination.get("ok")),
                            "pids": termination.get("pids") or [],
                            "kill": termination.get("kill")},
            "paths": paths,
            "pending": {"status": pending.status, "reason": pending.reason,
                        "retry_allowed": False, "worst_case_reserved": True},
            "failure": ({"type": type(failure).__name__, "message": str(failure)[:500]}
                        if failure is not None else None),
            "checks": self.checks,
            "status": status,
            "exit": exit_code,
            "synthetic": True,
            "real_model_calls": 0,
            "real_external_http_calls": 0,
            "provider_keys_seen": 0,
            "live_gate": "BLOCKED",
            "manual_cleanup": (f"{self.args.engine} ps -a; "
                               f"{self.args.engine} rm -f <container>"),
        }
        write_json(self.evidence / "watchdog.json", outcome)
        lines = [f"STATUS={status}", f"EXIT={exit_code}", f"REASON={self.reason}",
                 f"UTC_START={self.utc_start}", f"UTC_END={outcome['utc_end']}",
                 f"TARGET_EXIT={target_exit}",
                 "CHECKS:"]
        lines.extend(f"  {'PASS' if item['ok'] else 'FAIL'} {item['id']}"
                     for item in self.checks)
        lines.append("RETRY_ALLOWED=False")
        write_bytes(self.evidence / "watchdog.txt", ("\n".join(lines) + "\n").encode())
        return exit_code

    def _on_signal(self, signum, _frame) -> None:
        self.watchdog_signal = signum


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", default="d01")
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--run-dir", default=None)
    parser.add_argument("--engine", default="podman")
    parser.add_argument("--deadline", type=float, default=120.0)
    parser.add_argument("--kill-after-up", type=float, default=None)
    parser.add_argument("--term-grace", type=float, default=2.0)
    parser.add_argument("--poll", type=float, default=0.02)
    parser.add_argument("--poll-containers", type=float, default=0.25)
    parser.add_argument("--target-exit-ok", default="0")
    parser.add_argument("--require-containers", type=int, default=2)
    parser.add_argument("--pause", dest="pause_role", default=None,
                        choices=(None, "trusted", "candidate"))
    parser.add_argument("--self-fail-after", type=float, default=None)
    parser.add_argument("--expect", default="trigger", choices=("trigger", "exit"))
    parser.add_argument("--capture-live", action="store_true")
    parser.add_argument("--exec-probe", default=None,
                        help="candidate-principal probe source executed by podman exec")
    parser.add_argument("--exec-role", default="candidate")
    parser.add_argument("--exec-arg", default=None)
    parser.add_argument("--rlimit", action="append", default=[],
                        help="name:value applied to the supervised target")
    parser.add_argument("--timeout", type=float, default=600.0,
                        help="hard watchdog wall clock (safety net)")
    parser.add_argument("target", nargs=argparse.REMAINDER,
                        help="-- target argv (the launcher command)")
    args = parser.parse_args(argv)
    if args.target and args.target[0] == "--":
        args.target = args.target[1:]
    if not args.target:
        parser.error("target argv is required after --")
    args.evidence = str(Path(args.evidence).resolve())
    return args


def parse_rlimits(values: Sequence[str]) -> list[tuple[str, int]]:
    specs: list[tuple[str, int]] = []
    for raw in values:
        name, _, number = raw.partition(":")
        if name not in RLIMITS or not number.isdigit():
            raise SystemExit(f"G4D_RLIMIT_INVALID {raw}")
        specs.append((name, int(number)))
    return specs


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if os.geteuid() != 0:
        sys.stderr.write("G4D_WATCHDOG_NEEDS_HOST_ROOT\n")
        return EXIT_PREFLIGHT
    args.limit_specs = parse_rlimits(args.rlimit)
    runner = ExternalWatchdogRunner(args)
    sys.stderr.write(json.dumps({"case": args.case,
                                 "evidence": args.evidence,
                                 "run_id": args.run_id}) + "\n")
    return runner.run()


if __name__ == "__main__":
    raise SystemExit(main())
