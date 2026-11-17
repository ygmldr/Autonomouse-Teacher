"""G3-D1-B host-side shared library (stage/layout/argv/cleanup contract).

This module is *host only*: it never starts a container by itself. ``launch.py``
uses it for the executable path and ``tests/integration/g3d/test_d1_launcher_contract.py``
uses the pure functions to assert the launcher contract without a kernel.

The design keeps every decision auditable:

* permissions are planned as data (``RUN_LAYOUT``) and then applied/verified;
* container argv is produced by pure functions so it can be asserted in tests;
* readiness is decided by the *host launcher* from kernel facts (socket stat and
  ``/proc/<pid>/net/unix`` listening state), never from candidate-controlled
  files;
* cleanup is scoped to one absolute ``$RUN`` root and never follows symlinks.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import time
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = REPO_ROOT / "artifacts"
G3D_ROOT = ARTIFACTS / "g3d"
ROOTFS = ARTIFACTS / "security" / "rootfs"
DEPS = ARTIFACTS / "foundation" / "deps"

PRODUCT_BASE = "4bd48037d98e081c8fb96a246f3fbf3cf60eb38b"
ROOTFS_CANON = "25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0"
DEPS_CANON = "e07729d7997944417b1c25531749b3e6e5e34aa4248f01dc8f370282082ecb98"

CONTAINER_PREFIX = "at-g3d-"
SOCKET_PATH = "/work/g3b/bridge.sock"
CONTROLLER_CONFIG_PATH = "/work/state/controller.json"
EXPECTED_PEER_UID = 65534
SOCKET_MODE = 0o660
SOCKET_UID = 0
SOCKET_GID = 2000
GROUP_SOCKET = 2000
NOBODY_UID = 65534
NOBODY_GID = 65534

# Exit codes frozen by docs/M0_G3D_D1_IMPLEMENTATION_PLAN.md §3.7.
EXIT_OK = 0
EXIT_PREFLIGHT_IDENTITY = 2
EXIT_BLOCKED_ENVIRONMENT = 3
EXIT_STAGE_INVALID = 4
EXIT_TRUSTED_START_FAILED = 5
EXIT_CANDIDATE_START_FAILED = 6
EXIT_CASE_FAILED = 7
EXIT_CLEANUP_RESIDUAL = 8
EXIT_EVIDENCE_INTEGRITY = 9
EXIT_NO_LIVE_VIOLATION = 10

KEY_MARKERS = ("KEY", "TOKEN", "SECRET", "CREDENTIAL", "PASSWORD")

# $RUN layout from D0 §2.4. ``ipc`` is setgid so the Trusted Controller
# (which runs with --cap-drop ALL and therefore no CAP_CHOWN) inherits
# gid 2000 when it binds the socket.
RUN_LAYOUT: tuple[dict[str, Any], ...] = (
    {"relpath": "state", "mode": 0o700, "uid": 0, "gid": 0,
     "reason": "Broker DB/WAL, admission, policy, attempts, receipts, logs"},
    {"relpath": "ipc", "mode": 0o2750, "uid": 0, "gid": GROUP_SOCKET,
     "reason": "setgid root:2000 directory; only the bridge socket lives here"},
    {"relpath": "candidate-session", "mode": 0o700, "uid": NOBODY_UID,
     "gid": NOBODY_GID, "reason": "Candidate-only writable session"},
    {"relpath": "evidence", "mode": 0o700, "uid": 0, "gid": 0,
     "reason": "Trusted-only evidence mount"},
    {"relpath": "logs", "mode": 0o700, "uid": 0, "gid": 0,
     "reason": "Launcher logs"},
)

# Paths this agent is allowed to leave dirty in the worktree while running the
# pre-commit canonical evidence pass. Product ``src/`` is *never* allowed.
ALLOWED_DIRTY_PREFIXES = (
    "scripts/g3d/",
    "config/g3d/",
    "tests/integration/g3d/test_d1_launcher_contract.py",
    "tests/integration/g3d/test_d2_",
    "docs/M0_G3D_D1B_REPORT.md",
    "docs/M0_G3D_D2",
)

# D2 adversarial probes are audited candidate-stage Python files. They are the
# only Python files (besides run/candidate_entry.py) the candidate stage may
# carry; the allow-list is exact so a mistyped/extra probe fails the stage.
D2_PROBE_DIR = "run/probes"
D2_PROBE_FILES = frozenset({
    "probe_common.py",
    "d2_01_read_state.py",
    "d2_02_write_state.py",
    "d2_03_state_classes.py",
    "d2_04_broker_access.py",
    "d2_05_bypass_claim.py",
    "d2_06_forged_frames.py",
    "d2_07_network.py",
    "d2_08_kernel_surface.py",
    "d2_09_tool_plugin.py",
    "d2_10_disconnect.py",
    "d2_12_stress.py",
    "d2_13_dac_control.py",
    "d2_14_stale_run.py",
})
D2_PROBE_PATHS = frozenset(f"{D2_PROBE_DIR}/{name}" for name in D2_PROBE_FILES)
AUX_ROLES = frozenset({"control", "stale", "stress"})
TRUSTED_CRASH_HOOKS = frozenset({
    "after_reserve_before_claim",
    "after_claim_before_attempt_start",
    "after_attempt_start_before_fake_send",
    "after_fake_receive_before_response",
    "after_response_before_settlement",
})

FAIL_REASONS = {
    EXIT_PREFLIGHT_IDENTITY: "PREFLIGHT_IDENTITY",
    EXIT_BLOCKED_ENVIRONMENT: "BLOCKED_NEEDS_ENVIRONMENT",
    EXIT_STAGE_INVALID: "STAGE_INVALID",
    EXIT_TRUSTED_START_FAILED: "TRUSTED_START_FAILED",
    EXIT_CANDIDATE_START_FAILED: "CANDIDATE_START_FAILED",
    EXIT_CASE_FAILED: "CASE_FAILED",
    EXIT_CLEANUP_RESIDUAL: "CLEANUP_RESIDUAL",
    EXIT_EVIDENCE_INTEGRITY: "EVIDENCE_INTEGRITY",
    EXIT_NO_LIVE_VIOLATION: "NO_LIVE_VIOLATION",
}


class G3DError(RuntimeError):
    """Terminal launcher/build error carrying a stable exit code."""

    def __init__(self, message: str, *, exit_code: int = 1,
                 detail: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.exit_code = int(exit_code)
        self.detail = dict(detail or {})

    @property
    def reason(self) -> str:
        return FAIL_REASONS.get(self.exit_code, f"EXIT_{self.exit_code}")


# ---------------------------------------------------------------------------
# Time / hashing / process helpers
# ---------------------------------------------------------------------------
def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: str | os.PathLike[str]) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_tree(path: str | os.PathLike[str]) -> str:
    """Canonical tree hash: identical to the frozen ``tar | sha256sum`` recipe."""
    argv = ["tar", "--sort=name", "--mtime=@0", "--owner=0", "--group=0",
            "--numeric-owner", "-cf", "-", "-C", str(path), "."]
    proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    digest = hashlib.sha256()
    assert proc.stdout is not None
    for chunk in iter(lambda: proc.stdout.read(1 << 20), b""):
        digest.update(chunk)
    stderr = b"" if proc.stderr is None else proc.stderr.read()
    code = proc.wait()
    if code != 0:
        raise G3DError(f"tar failed for {path}",
                       detail={"exit": code,
                               "stderr": stderr.decode("utf-8", "replace")[:2000]})
    return digest.hexdigest()


def git_bytes(*args: str, cwd: Path | None = None) -> bytes:
    proc = subprocess.run(["git", *args], cwd=str(cwd or REPO_ROOT),
                          capture_output=True)
    if proc.returncode != 0:
        raise G3DError(
            f"git {' '.join(args)} failed",
            detail={"exit": proc.returncode,
                    "stderr": proc.stderr.decode("utf-8", "replace")[:2000]})
    return proc.stdout


def git_text(*args: str, cwd: Path | None = None) -> str:
    return git_bytes(*args, cwd=cwd).decode("utf-8", "replace").strip()


def git_blob_sha256(commit: str, path: str) -> str:
    return sha256_bytes(git_bytes("show", f"{commit}:{path}"))


def git_blob_hash(commit: str, path: str) -> str:
    return git_text("rev-parse", f"{commit}:{path}")


def run_command(argv: Sequence[str], *, log_dir: str | os.PathLike[str],
                name: str, timeout: float | None = 120,
                env: Mapping[str, str] | None = None,
                cwd: str | os.PathLike[str] | None = None,
                commands_path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    """Run one bounded host command and persist argv/UTC/exit/stdout/stderr."""
    directory = Path(log_dir)
    directory.mkdir(parents=True, exist_ok=True)
    started = utc()
    timed_out = False
    try:
        proc = subprocess.run([str(part) for part in argv], cwd=None if cwd is None else str(cwd),
                              env=None if env is None else dict(env),
                              capture_output=True, text=True, timeout=timeout)
        code, stdout, stderr = proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        code = 124
        stdout = _decode_timeout_stream(exc.stdout)
        stderr = _decode_timeout_stream(exc.stderr)
    ended = utc()
    stdout_path = directory / f"{name}.stdout.txt"
    stderr_path = directory / f"{name}.stderr.txt"
    stdout_path.write_text(stdout or "", encoding="utf-8")
    stderr_path.write_text(stderr or "", encoding="utf-8")
    record = {
        "name": name,
        "argv": [str(part) for part in argv],
        "utc_start": started,
        "utc_end": ended,
        "exit": code,
        "timed_out": timed_out,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
    }
    if commands_path is not None:
        append_jsonl(commands_path, {**record, "kind": "host_command"})
    return {**record, "stdout": stdout or "", "stderr": stderr or ""}


def _decode_timeout_stream(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)


def append_jsonl(path: str | os.PathLike[str], record: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(record), sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def json_bytes(document: Any) -> bytes:
    return (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")


def write_bytes_atomic(path: str | os.PathLike[str], data: bytes, *,
                       mode: int = 0o444, uid: int | None = None,
                       gid: int | None = None) -> dict[str, Any]:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{os.getpid()}.{time.monotonic_ns()}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(temporary, flags, 0o600)
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.chmod(temporary, mode)
    if uid is not None or gid is not None:
        os.chown(temporary, -1 if uid is None else uid, -1 if gid is None else gid)
    os.replace(temporary, target)
    try:
        dfd = os.open(target.parent, os.O_RDONLY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    except OSError:
        pass
    record = lstat_record(target)
    record["sha256"] = sha256_bytes(data)
    record["bytes"] = len(data)
    return record


def write_json_atomic(path: str | os.PathLike[str], document: Any, *,
                      mode: int = 0o444, uid: int | None = None,
                      gid: int | None = None) -> dict[str, Any]:
    return write_bytes_atomic(path, json_bytes(document), mode=mode, uid=uid, gid=gid)


# ---------------------------------------------------------------------------
# Environment hygiene (record names only, never values)
# ---------------------------------------------------------------------------
def env_names(env: Mapping[str, str] | None = None) -> list[str]:
    source = os.environ if env is None else env
    return sorted(source)


def key_like_names(names: Iterable[str]) -> list[str]:
    hits = []
    for name in names:
        upper = name.upper()
        if any(marker in upper for marker in KEY_MARKERS):
            hits.append(name)
    return sorted(set(hits))


def env_snapshot(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    source = os.environ if env is None else env
    names = env_names(source)
    return {"count": len(names), "names": names,
            "key_like_names": key_like_names(names)}


# ---------------------------------------------------------------------------
# Permissions / inode records
# ---------------------------------------------------------------------------
def _type_name(mode: int) -> str:
    if stat.S_ISSOCK(mode):
        return "socket"
    if stat.S_ISDIR(mode):
        return "directory"
    if stat.S_ISREG(mode):
        return "regular"
    if stat.S_ISLNK(mode):
        return "symlink"
    if stat.S_ISFIFO(mode):
        return "fifo"
    if stat.S_ISCHR(mode):
        return "char_device"
    if stat.S_ISBLK(mode):
        return "block_device"
    return "unknown"


def lstat_record(path: str | os.PathLike[str]) -> dict[str, Any] | None:
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return None
    except OSError as exc:
        return {"path": str(path), "error": type(exc).__name__}
    return {
        "path": str(path),
        "type": _type_name(info.st_mode),
        "mode": stat.S_IMODE(info.st_mode),
        "mode_octal": format(stat.S_IMODE(info.st_mode), "04o"),
        "setgid": bool(info.st_mode & stat.S_ISGID),
        "uid": info.st_uid,
        "gid": info.st_gid,
        "size": info.st_size,
        "inode": info.st_ino,
        "nlink": info.st_nlink,
    }


def plan_run_layout() -> list[dict[str, Any]]:
    return [dict(item) for item in RUN_LAYOUT]


def create_run_layout(run_dir: str | os.PathLike[str]) -> list[dict[str, Any]]:
    """Create the frozen $RUN layout with exact modes/uids/gids (root only)."""
    if os.geteuid() != 0:
        raise G3DError("launcher requires host root to create $RUN",
                       exit_code=EXIT_BLOCKED_ENVIRONMENT)
    root = Path(run_dir)
    if root.exists():
        raise G3DError("run directory already exists", exit_code=EXIT_PREFLIGHT_IDENTITY,
                       detail={"path": str(root)})
    root.mkdir(mode=0o700)
    os.chown(root, 0, 0)
    os.chmod(root, 0o700)
    created = []
    for item in RUN_LAYOUT:
        target = root / item["relpath"]
        target.mkdir(mode=0o700)
        os.chown(target, item["uid"], item["gid"])
        os.chmod(target, item["mode"])
        record = lstat_record(target)
        problems = layout_permission_problems(record, item)
        if problems:
            raise G3DError("run layout permission mismatch",
                           exit_code=EXIT_EVIDENCE_INTEGRITY,
                           detail={"path": str(target), "problems": problems})
        created.append({"relpath": item["relpath"], "reason": item["reason"],
                        "expected": {k: item[k] for k in ("mode", "uid", "gid")},
                        "actual": record})
    return created


def layout_permission_problems(record: Mapping[str, Any] | None,
                               expected: Mapping[str, Any]) -> list[str]:
    problems: list[str] = []
    if record is None or record.get("error"):
        return ["missing_or_unreadable"]
    if record.get("type") != "directory":
        problems.append(f"not_directory:{record.get('type')}")
    if record.get("mode") != expected["mode"]:
        problems.append(f"mode:{record.get('mode_octal')}!= {format(expected['mode'], '04o')}")
    if record.get("uid") != expected["uid"]:
        problems.append(f"uid:{record.get('uid')}!= {expected['uid']}")
    if record.get("gid") != expected["gid"]:
        problems.append(f"gid:{record.get('gid')}!= {expected['gid']}")
    if expected["mode"] & stat.S_ISGID and not record.get("setgid"):
        problems.append("setgid_missing")
    return problems


def socket_contract_problems(record: Mapping[str, Any] | None, *,
                             mode: int = SOCKET_MODE, uid: int = SOCKET_UID,
                             gid: int = SOCKET_GID) -> list[str]:
    problems: list[str] = []
    if record is None:
        return ["socket_absent"]
    if record.get("error"):
        return [f"socket_lstat_error:{record['error']}"]
    if record.get("type") != "socket":
        problems.append(f"not_socket:{record.get('type')}")
    if record.get("mode") != mode:
        problems.append(f"mode:{record.get('mode_octal')}!= {format(mode, '04o')}")
    if record.get("uid") != uid:
        problems.append(f"uid:{record.get('uid')}!= {uid}")
    if record.get("gid") != gid:
        problems.append(f"gid:{record.get('gid')}!= {gid}")
    return problems


# ---------------------------------------------------------------------------
# Bounded reads / readiness gate
# ---------------------------------------------------------------------------
def read_regular_bytes(path: str | os.PathLike[str], *, max_bytes: int = 1 << 20) -> bytes:
    """Read a regular file with O_NOFOLLOW; symlinks/FIFOs are refused."""
    flags = os.O_RDONLY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise G3DError("refusing non-regular file", exit_code=EXIT_EVIDENCE_INTEGRITY,
                           detail={"path": str(path), "mode": info.st_mode})
        if info.st_size > max_bytes:
            raise G3DError("file exceeds evidence cap", exit_code=EXIT_EVIDENCE_INTEGRITY,
                           detail={"path": str(path), "size": info.st_size})
        chunks = []
        total = 0
        while True:
            chunk = os.read(fd, 1 << 20)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise G3DError("file grew beyond evidence cap",
                               exit_code=EXIT_EVIDENCE_INTEGRITY,
                               detail={"path": str(path)})
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(fd)


def parse_ready_document(raw: bytes) -> tuple[dict[str, Any] | None, list[str]]:
    problems: list[str] = []
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, ["ready_not_json"]
    if not isinstance(document, dict):
        return None, ["ready_not_object"]
    if document.get("schema") != "m0.g3d.trusted.ready.v1":
        problems.append("ready_schema")
    if document.get("expected_peer_uid") != EXPECTED_PEER_UID:
        problems.append("ready_peer_uid")
    socket_doc = document.get("socket")
    if not isinstance(socket_doc, dict):
        problems.append("ready_socket_missing")
    else:
        if socket_doc.get("mode") != SOCKET_MODE:
            problems.append("ready_socket_mode")
        if socket_doc.get("gid") != GROUP_SOCKET:
            problems.append("ready_socket_gid")
        if socket_doc.get("uid") != SOCKET_UID:
            problems.append("ready_socket_uid")
        if not isinstance(socket_doc.get("inode"), int):
            problems.append("ready_socket_inode")
    if not isinstance(document.get("pid"), int) or document["pid"] <= 0:
        problems.append("ready_pid")
    if not isinstance(document.get("utc"), str) or "T" not in document["utc"]:
        problems.append("ready_utc")
    return document, problems


def evaluate_ready(*, socket_record: Mapping[str, Any] | None,
                   ready_document: Mapping[str, Any] | None,
                   ready_problems: Sequence[str] | None,
                   listening_entries: Sequence[Mapping[str, Any]] | None,
                   container_running: bool,
                   socket_path: str = SOCKET_PATH) -> dict[str, Any]:
    """Host-side admission gate before the Candidate is allowed to start.

    All inputs are kernel/host facts or the Trusted-written ready file; nothing
    here is produced by the Candidate.
    """
    problems: list[str] = []
    if not container_running:
        problems.append("trusted_container_not_running")
    if ready_document is None:
        problems.append("ready_absent")
    problems.extend(ready_problems or [])
    problems.extend(f"socket:{item}" for item in
                    socket_contract_problems(socket_record))
    if socket_record is not None and ready_document is not None:
        ready_socket = ready_document.get("socket")
        if isinstance(ready_socket, dict):
            if ready_socket.get("inode") != socket_record.get("inode"):
                problems.append("ready_inode_mismatch")
    listening = [entry for entry in (listening_entries or [])
                 if entry.get("path") == socket_path and entry.get("listening")]
    if not listening:
        problems.append("socket_not_listening")
    return {"ok": not problems, "problems": problems,
            "listening_entries": list(listening)}


def ready_allows_candidate(evaluation: Mapping[str, Any]) -> bool:
    return bool(evaluation.get("ok"))


def parse_proc_net_unix(pid: int) -> list[dict[str, Any]]:
    """Parse ``/proc/<pid>/net/unix`` (trusted net namespace, host read)."""
    rows: list[dict[str, Any]] = []
    try:
        text = Path(f"/proc/{int(pid)}/net/unix").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return rows
    for line in text.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 7:
            continue
        try:
            flags = int(parts[3], 16)
            inode = int(parts[6])
        except ValueError:
            continue
        path = parts[7] if len(parts) > 7 else ""
        rows.append({"num": parts[0].rstrip(":"), "flags": flags,
                     "listening": bool(flags & 0x10000), "type": parts[4],
                     "st": parts[5], "inode": inode, "path": path})
    return rows


def proc_credentials(pid: int) -> dict[str, Any]:
    """Read real/effective uid/gid, caps and seccomp from /proc/<pid>/status."""
    result: dict[str, Any] = {"pid": int(pid)}
    try:
        text = Path(f"/proc/{int(pid)}/status").read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        result["error"] = type(exc).__name__
        return result
    wanted = {"Uid": "uid", "Gid": "gid", "CapEff": "cap_eff", "CapPrm": "cap_prm",
              "CapBnd": "cap_bnd", "NoNewPrivs": "no_new_privs",
              "Seccomp": "seccomp"}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        if key in wanted:
            result[wanted[key]] = value.strip()
    return result


def cgroup_limits(pid: int) -> dict[str, Any]:
    result: dict[str, Any] = {"pid": int(pid)}
    try:
        cgroup = Path(f"/proc/{int(pid)}/cgroup").read_text(encoding="utf-8").strip()
    except OSError as exc:
        result["error"] = type(exc).__name__
        return result
    result["cgroup"] = cgroup
    relative = None
    for line in cgroup.splitlines():
        fields = line.split(":", 2)
        if len(fields) == 3 and fields[0] == "0":
            relative = fields[2]
            break
    if relative is None:
        result["limits"] = {}
        return result
    base = Path("/sys/fs/cgroup") / relative.lstrip("/")
    limits: dict[str, Any] = {}
    for name in ("pids.max", "pids.current", "memory.max", "memory.current",
                 "cpu.max", "cgroup.freeze"):
        try:
            limits[name] = (base / name).read_text(encoding="utf-8").strip()
        except OSError:
            limits[name] = None
    result["path"] = str(base)
    result["limits"] = limits
    return result


def find_residual_processes(markers: Sequence[str], *,
                            exclude_pids: Sequence[int] = ()) -> list[dict[str, Any]]:
    """Scan host /proc for argv markers (launcher cleanup evidence)."""
    excluded = {int(pid) for pid in exclude_pids}
    rows: list[dict[str, Any]] = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        if pid in excluded:
            continue
        try:
            raw = (entry / "cmdline").read_bytes()[:8192]
        except OSError:
            continue
        argv = [part.decode("utf-8", "replace") for part in raw.split(b"\0") if part]
        joined = "\n".join(argv)
        hits = [marker for marker in markers if marker in joined]
        if hits:
            rows.append({"pid": pid, "argv": argv, "markers": hits})
    return rows


# ---------------------------------------------------------------------------
# Container argv (pure; tests assert this exact contract)
# ---------------------------------------------------------------------------
def container_name(run_id: str, role: str) -> str:
    return f"{CONTAINER_PREFIX}{role}-{run_id}"


def _base_security_flags(*, pids_limit: int = 256, memory: str = "1g",
                         cpus: str = "1") -> list[str]:
    return [
        "--network", "none",
        "--http-proxy=false",
        "--unsetenv-all",
        "--no-hosts",
        "--read-only",
        "--read-only-tmpfs=false",
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "--pids-limit", str(int(pids_limit)),
        "--memory", memory,
        "--memory-swap", memory,
        "--cpus", cpus,
        "--ulimit", "nofile=4096:4096",
    ]


def trusted_run_argv(*, podman: str, rootfs: str, stage_trusted: str, deps: str,
                     run_dir: str, name: str,
                     config_path: str = CONTROLLER_CONFIG_PATH,
                     timeout_s: int = 300,
                     evidence_dir: str | None = None,
                     crash_hook: str | None = None) -> list[str]:
    evidence = evidence_dir or str(Path(run_dir) / "evidence")
    extra_env: list[str] = []
    if crash_hook is not None:
        if crash_hook not in TRUSTED_CRASH_HOOKS:
            raise G3DError("unknown trusted crash hook",
                           exit_code=EXIT_STAGE_INVALID,
                           detail={"crash_hook": crash_hook})
        # Product test-only hook: requires *both* env vars and is used only for
        # trusted fault injection, never for a candidate attack observation.
        extra_env = ["--env", "G3B_TEST_MODE=1", "--env", f"G3B_CRASH_HOOK={crash_hook}"]
    argv = [podman, "run", "-d", "--name", name, "--rootfs",
            "--timeout", str(int(timeout_s)),
            "--userns=host", "--user", "0:0",
            *_base_security_flags(),
            "--env", "PATH=/opt/python/bin:/usr/bin",
            "--env", "HOME=/work",
            "--env", "PYTHONPATH=/project/src:/deps",
            "--env", "PYTHONDONTWRITEBYTECODE=1",
            "--env", "TMPDIR=/tmp",
            *extra_env,
            "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=64m,mode=1777",
            "--tmpfs", "/work:rw,noexec,nosuid,nodev,size=256m,mode=1777",
            "--mount", f"type=bind,src={stage_trusted},dst=/project,ro=true",
            "--mount", f"type=bind,src={deps},dst=/deps,ro=true",
            "--mount", f"type=bind,src={stage_trusted}/etc/passwd,dst=/etc/passwd,ro=true",
            "--mount", f"type=bind,src={stage_trusted}/etc/group,dst=/etc/group,ro=true",
            "--mount", f"type=bind,src={Path(run_dir) / 'state'},dst=/work/state,rw=true",
            "--mount", f"type=bind,src={Path(run_dir) / 'ipc'},dst=/work/g3b,rw=true",
            "--mount", f"type=bind,src={evidence},dst=/output,rw=true",
            "--workdir", "/project",
            "--systemd=false",
            rootfs, "/opt/python/bin/python3.11", "-B",
            "/project/run/trusted_entry.py", "--config", config_path]
    return argv


def candidate_run_argv(*, podman: str, rootfs: str, stage_candidate: str, deps: str,
                       run_dir: str, name: str, scenario: str = "echo",
                       session: str = "g3d-d1-s1", prompt: str = "G3D_ECHO",
                       timeout_s: int = 300, mode: str = "dsh",
                       label: str | None = None,
                       hold_seconds: int = 600) -> list[str]:
    argv = [podman, "run", "-d", "--name", name, "--rootfs",
            "--timeout", str(int(timeout_s)),
            "--uidmap", "0:65534:1",
            "--gidmap", "0:65534:1",
            "--gidmap", "2000:2000:1",
            "--user", "0:0",
            "--group-add", str(GROUP_SOCKET),
            *_base_security_flags(),
            "--env", "PATH=/opt/python/bin:/usr/bin",
            "--env", "HOME=/work/session",
            "--env", "PYTHONPATH=/deps",
            "--env", "PYTHONDONTWRITEBYTECODE=1",
            "--env", "TMPDIR=/tmp",
            "--env", "DSH_RUNTIME_MODE=exe",
            "--env", "DSH_RESOURCE_CACHE=/work/resources",
            "--env", "NARB_NATIVE_CACHE_DIR=/project/native-cache",
            "--env", "PKG_NATIVE_CACHE_PATH=/project/pkg-cache",
            "--env", "NO_COLOR=1",
            "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=128m,mode=1777",
            "--tmpfs", "/work:rw,noexec,nosuid,nodev,size=512m,mode=1777",
            "--mount", f"type=bind,src={stage_candidate},dst=/project,ro=true",
            "--mount", f"type=bind,src={deps},dst=/deps,ro=true",
            "--mount", f"type=bind,src={stage_candidate}/etc/passwd,dst=/etc/passwd,ro=true",
            "--mount", f"type=bind,src={stage_candidate}/etc/group,dst=/etc/group,ro=true",
            "--mount", f"type=bind,src={Path(run_dir) / 'candidate-session'},dst=/work/session,rw=true",
            "--mount", f"type=bind,src={Path(run_dir) / 'ipc'},dst=/work/g3b,ro=true",
            "--workdir", "/work/session",
            "--systemd=false",
            rootfs, "/opt/python/bin/python3.11", "-B",
            "/project/run/candidate_entry.py"]
    if mode == "hold":
        argv.extend(["--mode", "hold", "--hold-seconds", str(int(hold_seconds)),
                     "--label", str(label or "hold")])
    elif mode == "dsh":
        argv.extend(["--scenario", scenario, "--session", session,
                     "--prompt", prompt])
        if label:
            argv.extend(["--label", str(label)])
    else:
        raise G3DError("unknown candidate mode", exit_code=EXIT_STAGE_INVALID,
                       detail={"mode": mode})
    return argv


def aux_run_argv(*, podman: str, rootfs: str, stage_candidate: str, deps: str,
                 run_dir: str, name: str, role: str, probe: str,
                 probe_args: Sequence[str] = (), timeout_s: int = 300,
                 pids_limit: int = 256, memory: str = "1g",
                 cpus: str = "1") -> list[str]:
    """Build a Candidate-identity auxiliary container for one D2 probe.

    Every auxiliary container keeps the Candidate UID/GID map, private
    namespaces, ``--network none``, ``--cap-drop ALL`` and read-only rootfs.
    The only differences are auditable:
    * ``control`` gets an extra *read-only* state mount (D2-13 CONTROL, never a
      positive Candidate configuration);
    * ``stale`` mounts a different (empty/stale) IPC directory, not this run's;
    * ``stress`` uses the frozen lower cgroup limits (8 pids / 128 MiB).
    """
    if role not in AUX_ROLES:
        raise G3DError("unknown auxiliary role", exit_code=EXIT_STAGE_INVALID,
                       detail={"role": role})
    if probe not in D2_PROBE_FILES:
        raise G3DError("probe is not in the audited D2 allow-list",
                       exit_code=EXIT_STAGE_INVALID, detail={"probe": probe})
    stale_ipc = Path(run_dir) / "stale-ipc"
    ipc_source = stale_ipc if role == "stale" else Path(run_dir) / "ipc"
    argv = [podman, "run", "--rm", "--name", name, "--rootfs",
            "--timeout", str(int(timeout_s)),
            "--uidmap", "0:65534:1",
            "--gidmap", "0:65534:1",
            "--gidmap", "2000:2000:1",
            "--user", "0:0",
            "--group-add", str(GROUP_SOCKET),
            *_base_security_flags(pids_limit=pids_limit, memory=memory, cpus=cpus),
            "--env", "PATH=/opt/python/bin:/usr/bin",
            "--env", "HOME=/work/session",
            "--env", "PYTHONPATH=/deps",
            "--env", "PYTHONDONTWRITEBYTECODE=1",
            "--env", "TMPDIR=/tmp",
            "--env", "NO_COLOR=1",
            "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=128m,mode=1777",
            "--tmpfs", "/work:rw,noexec,nosuid,nodev,size=512m,mode=1777",
            "--mount", f"type=bind,src={stage_candidate},dst=/project,ro=true",
            "--mount", f"type=bind,src={deps},dst=/deps,ro=true",
            "--mount", f"type=bind,src={stage_candidate}/etc/passwd,dst=/etc/passwd,ro=true",
            "--mount", f"type=bind,src={stage_candidate}/etc/group,dst=/etc/group,ro=true",
            "--mount", f"type=bind,src={Path(run_dir) / 'candidate-session'},dst=/work/session,rw=true",
            "--mount", f"type=bind,src={ipc_source},dst=/work/g3b,ro=true"]
    if role == "control":
        argv.extend(["--mount",
                     f"type=bind,src={Path(run_dir) / 'state'},dst=/work/state,ro=true"])
    argv.extend([
        "--workdir", "/work/session",
        "--systemd=false",
        rootfs, "/opt/python/bin/python3.11", "-B",
        f"/project/run/probes/{probe}",
        *[str(value) for value in probe_args],
    ])
    return argv


def aux_argv_contract_problems(argv: Sequence[str], *, role: str,
                               run_dir: str, stage_dir: str,
                               probe: str) -> list[str]:
    """Assert the D2 auxiliary container contract (fail closed on any drift)."""
    if role not in AUX_ROLES:
        return [f"unknown_role:{role}"]
    problems: list[str] = []
    tokens = [str(token) for token in argv]
    joined = "\n".join(tokens)

    def require_pair(first: str, second: str) -> None:
        for index, token in enumerate(tokens[:-1]):
            if token == first and tokens[index + 1] == second:
                return
        problems.append(f"missing:{first} {second}")

    require_pair("--network", "none")
    require_pair("--cap-drop", "ALL")
    require_pair("--security-opt", "no-new-privileges")
    require_pair("--uidmap", "0:65534:1")
    require_pair("--gidmap", "0:65534:1")
    require_pair("--gidmap", "2000:2000:1")
    require_pair("--group-add", str(GROUP_SOCKET))
    require_pair("--user", "0:0")
    if "--read-only" not in tokens:
        problems.append("missing:--read-only")
    for forbidden in ("--privileged", "--userns=host", "--pid=host", "--ipc=host",
                      "--net=host", "-v", "--volume", "--device"):
        if forbidden in tokens:
            problems.append(f"forbidden:{forbidden}")
    if "podman.sock" in joined or "/var/run/docker.sock" in joined:
        problems.append("forbidden:engine_socket")
    for value in argv_env(argv):
        name = value.split("=", 1)[0]
        if key_like_names([name]):
            problems.append(f"forbidden:key_like_env:{name}")
    if probe not in D2_PROBE_FILES:
        problems.append(f"probe_not_allowlisted:{probe}")
    if not any(token.endswith(f"/project/run/probes/{probe}") for token in tokens):
        problems.append("missing:probe_entrypoint")
    mounts = argv_mounts(argv)
    if not any(mount.endswith("dst=/project,ro=true") for mount in mounts):
        problems.append("missing:project_ro_mount")
    if not any(mount.endswith("dst=/deps,ro=true") for mount in mounts):
        problems.append("missing:deps_ro_mount")
    if any("dst=/output" in mount for mount in mounts):
        problems.append("forbidden:evidence_mount")
    state_mounts = [mount for mount in mounts if "dst=/work/state" in mount]
    ipc_mounts = [mount for mount in mounts if "dst=/work/g3b" in mount]
    if len(ipc_mounts) != 1:
        problems.append(f"ipc_mount_count:{len(ipc_mounts)}")
    if role == "control":
        if state_mounts != [f"type=bind,src={Path(run_dir) / 'state'},"
                            "dst=/work/state,ro=true"]:
            problems.append("control_missing_exact_state_ro_mount")
        if not all(mount.endswith(",ro=true") for mount in state_mounts):
            problems.append("control_state_not_read_only")
        if ipc_mounts and not ipc_mounts[0].endswith(",ro=true"):
            problems.append("control_ipc_not_read_only")
    elif state_mounts:
        problems.append(f"forbidden:{role}_state_mount")
    if role == "stale":
        expected = f"type=bind,src={Path(run_dir) / 'stale-ipc'},dst=/work/g3b,ro=true"
        if ipc_mounts != [expected]:
            problems.append("stale_ipc_mount_not_isolated")
    elif role in {"control", "stress"}:
        expected = f"type=bind,src={Path(run_dir) / 'ipc'},dst=/work/g3b,ro=true"
        if ipc_mounts != [expected]:
            problems.append(f"{role}_ipc_mount_wrong")
    if role == "stress":
        require_pair("--pids-limit", "8")
        require_pair("--memory", "128m")
        require_pair("--memory-swap", "128m")
    if role in {"control", "stale"}:
        require_pair("--pids-limit", "256")
        require_pair("--memory", "1g")
    if any(b"stage_candidate" in mount.encode() for mount in mounts):
        problems.append("forbidden:candidate_stage_placeholder")
    return problems

def argv_mounts(argv: Sequence[str]) -> list[str]:
    values: list[str] = []
    for index, token in enumerate(argv):
        if token == "--mount" and index + 1 < len(argv):
            values.append(str(argv[index + 1]))
    return values


def argv_env(argv: Sequence[str]) -> list[str]:
    values: list[str] = []
    for index, token in enumerate(argv):
        if token == "--env" and index + 1 < len(argv):
            values.append(str(argv[index + 1]))
    return values


def argv_contract_problems(argv: Sequence[str], *, role: str,
                           run_dir: str, stage_dir: str) -> list[str]:
    """Assert the launcher contract for a generated container argv."""
    problems: list[str] = []
    tokens = [str(token) for token in argv]
    joined = "\n".join(tokens)

    def require_pair(first: str, second: str) -> None:
        for index, token in enumerate(tokens[:-1]):
            if token == first and tokens[index + 1] == second:
                return
        problems.append(f"missing:{first} {second}")

    require_pair("--network", "none")
    require_pair("--cap-drop", "ALL")
    require_pair("--security-opt", "no-new-privileges")
    if "--read-only" not in tokens:
        problems.append("missing:--read-only")
    if "--privileged" in tokens:
        problems.append("forbidden:--privileged")
    for forbidden in ("--pid=host", "--ipc=host", "--uts=host", "--net=host",
                      "--privileged", "--volume", "-v", "--device"):
        if forbidden in tokens:
            problems.append(f"forbidden:{forbidden}")
    if any(token.startswith("--pid=host") for token in tokens):
        problems.append("forbidden:--pid=host")
    if "podman.sock" in joined or "/var/run/docker.sock" in joined:
        problems.append("forbidden:engine_socket")
    for value in argv_env(argv):
        name = value.split("=", 1)[0]
        if key_like_names([name]):
            problems.append(f"forbidden:key_like_env:{name}")

    mounts = argv_mounts(argv)
    if not any(mount.endswith("dst=/project,ro=true") for mount in mounts):
        problems.append("missing:project_ro_mount")
    if not any(mount.endswith("dst=/deps,ro=true") for mount in mounts):
        problems.append("missing:deps_ro_mount")
    if not any(f"src={stage_dir}/etc/passwd" in mount for mount in mounts):
        problems.append("missing:synthetic_passwd_mount")
    if not any(f"src={stage_dir}/etc/group" in mount for mount in mounts):
        problems.append("missing:synthetic_group_mount")

    if role == "trusted":
        if "--userns=host" not in tokens:
            problems.append("missing:--userns=host")
        require_pair("--user", "0:0")
        if not any(f"src={Path(run_dir) / 'state'},dst=/work/state,rw=true" in mount
                   for mount in mounts):
            problems.append("missing:state_rw_mount")
        if not any(f"src={Path(run_dir) / 'ipc'},dst=/work/g3b,rw=true" in mount
                   for mount in mounts):
            problems.append("missing:ipc_rw_mount")
        if any("candidate-session" in mount for mount in mounts):
            problems.append("forbidden:candidate_session_mount")
        if any("stage_candidate" in mount for mount in mounts):
            problems.append("forbidden:candidate_stage_mount")
        if "/work/state" in "".join(argv_env(argv)):
            problems.append("forbidden:state_in_env")
    elif role == "candidate":
        require_pair("--uidmap", "0:65534:1")
        require_pair("--gidmap", "0:65534:1")
        require_pair("--gidmap", "2000:2000:1")
        require_pair("--group-add", str(GROUP_SOCKET))
        if "--userns=host" in tokens:
            problems.append("forbidden:candidate_userns_host")
        if not any(f"src={Path(run_dir) / 'ipc'},dst=/work/g3b,ro=true" in mount
                   for mount in mounts):
            problems.append("missing:ipc_ro_mount")
        if any("dst=/work/state" in mount for mount in mounts):
            problems.append("forbidden:candidate_state_mount")
        if any("dst=/output" in mount for mount in mounts):
            problems.append("forbidden:candidate_evidence_mount")
        if any(f"src={Path(run_dir) / 'evidence'}" in mount for mount in mounts):
            problems.append("forbidden:candidate_evidence_mount")
        if any(f"src={stage_dir}/run/trusted_entry.py" in mount for mount in mounts):
            problems.append("forbidden:trusted_entry_mount")
        env_text = "\n".join(argv_env(argv))
        if "/project/src" in env_text:
            problems.append("forbidden:trusted_pythonpath")
    else:
        problems.append(f"unknown_role:{role}")
    return problems


# ---------------------------------------------------------------------------
# Bounded SIGTERM -> SIGKILL stop sequence (injectable for host tests)
# ---------------------------------------------------------------------------
def terminate_container(name: str, *, signal_fn: Callable[[str, str], Any],
                        wait_exit: Callable[[str, float], int | None],
                        grace_s: float = 5.0, kill_wait_s: float = 5.0,
                        poll_s: float = 0.1,
                        clock: Callable[[], float] = time.monotonic) -> dict[str, Any]:
    """Send TERM, wait bounded, then KILL; never blocks forever."""
    started = clock()
    signal_fn(name, "TERM")
    deadline = started + max(0.0, grace_s)
    code = None
    while True:
        code = wait_exit(name, 0.0)
        if code is not None:
            break
        if clock() >= deadline:
            break
        time.sleep(min(poll_s, max(0.0, deadline - clock())))
    escalated = False
    if code is None:
        escalated = True
        signal_fn(name, "KILL")
        kill_deadline = clock() + max(0.0, kill_wait_s)
        while True:
            code = wait_exit(name, 0.0)
            if code is not None or clock() >= kill_deadline:
                break
            time.sleep(min(poll_s, max(0.0, kill_deadline - clock())))
    return {"container": name, "sigterm": True, "sigkill": escalated,
            "exit_code": code, "waited_s": round(clock() - started, 3),
            "stopped": code is not None}


# ---------------------------------------------------------------------------
# Symlink-safe deletion / socket unlink
# ---------------------------------------------------------------------------
def _is_within(root: Path, target: Path) -> bool:
    root_text = os.path.abspath(str(root))
    target_text = os.path.abspath(str(target))
    try:
        return os.path.commonpath([root_text, target_text]) == root_text
    except ValueError:
        return False


def safe_delete_tree(allowed_root: str | os.PathLike[str],
                     target: str | os.PathLike[str]) -> dict[str, Any]:
    """Delete ``target`` without ever following symlinks; scoped to root."""
    root = Path(os.path.abspath(str(allowed_root)))
    victim = Path(os.path.abspath(str(target)))
    if victim == root:
        raise G3DError("refusing to delete the allowed root itself",
                       exit_code=EXIT_CLEANUP_RESIDUAL)
    if not _is_within(root, victim):
        raise G3DError("delete target escapes the allowed root",
                       exit_code=EXIT_CLEANUP_RESIDUAL,
                       detail={"root": str(root), "target": str(victim)})
    stats: dict[str, Any] = {"root": str(root), "target": str(victim),
                             "removed_files": 0, "removed_dirs": 0,
                             "removed_symlinks": 0, "errors": []}
    if not victim.exists() and not victim.is_symlink():
        stats["absent"] = True
        stats["removed"] = False
        return stats
    if victim.is_symlink():
        raise G3DError("refusing to delete a symlink root",
                       exit_code=EXIT_CLEANUP_RESIDUAL,
                       detail={"target": str(victim)})
    directories: list[Path] = [victim]
    stack: list[Path] = [victim]
    while stack:
        current = stack.pop()
        try:
            entries = list(os.scandir(current))
        except OSError as exc:
            stats["errors"].append({"path": str(current), "error": type(exc).__name__})
            continue
        for entry in entries:
            path = Path(entry.path)
            try:
                info = entry.stat(follow_symlinks=False)
            except OSError as exc:
                stats["errors"].append({"path": str(path), "error": type(exc).__name__})
                continue
            if stat.S_ISDIR(info.st_mode):
                directories.append(path)
                stack.append(path)
            elif stat.S_ISLNK(info.st_mode):
                try:
                    os.unlink(path)
                    stats["removed_symlinks"] += 1
                except OSError as exc:
                    stats["errors"].append({"path": str(path),
                                            "error": type(exc).__name__})
            else:
                try:
                    os.unlink(path)
                    stats["removed_files"] += 1
                except OSError as exc:
                    stats["errors"].append({"path": str(path),
                                            "error": type(exc).__name__})
    for directory in reversed(directories):
        try:
            os.rmdir(directory)
            stats["removed_dirs"] += 1
        except OSError as exc:
            stats["errors"].append({"path": str(directory),
                                    "error": type(exc).__name__})
    stats["removed"] = not victim.exists()
    return stats


def unlink_socket(path: str | os.PathLike[str], *, expected_uid: int = 0,
                  expected_gid: int = GROUP_SOCKET) -> dict[str, Any]:
    target = Path(path)
    record = lstat_record(target)
    if record is None:
        return {"path": str(target), "removed": False, "reason": "absent"}
    if record.get("error"):
        return {"path": str(target), "removed": False, "reason": "lstat_error",
                "record": record}
    if record["type"] != "socket":
        return {"path": str(target), "removed": False, "reason": "not_socket",
                "record": record}
    if record["uid"] != expected_uid or record["gid"] != expected_gid:
        return {"path": str(target), "removed": False, "reason": "foreign_owner",
                "record": record}
    try:
        os.unlink(target)
    except OSError as exc:
        return {"path": str(target), "removed": False, "reason": "unlink_failed",
                "error": type(exc).__name__, "record": record}
    return {"path": str(target), "removed": True, "record": record}


def unlink_regular(path: str | os.PathLike[str], *, expected_uid: int = 0) -> dict[str, Any]:
    target = Path(path)
    record = lstat_record(target)
    if record is None:
        return {"path": str(target), "removed": False, "reason": "absent"}
    if record.get("error") or record["type"] != "regular":
        return {"path": str(target), "removed": False, "reason": "not_regular",
                "record": record}
    if record["uid"] != expected_uid:
        return {"path": str(target), "removed": False, "reason": "foreign_owner",
                "record": record}
    try:
        os.unlink(target)
    except OSError as exc:
        return {"path": str(target), "removed": False, "reason": "unlink_failed",
                "error": type(exc).__name__}
    return {"path": str(target), "removed": True, "record": record}


# ---------------------------------------------------------------------------
# Evidence inventory helpers
# ---------------------------------------------------------------------------
def inventory_files(root: str | os.PathLike[str]) -> tuple[dict[str, dict[str, Any]],
                                                           list[str]]:
    """Return ``{relpath: {sha256,bytes,mode}}`` plus structural problems.

    Symlinked directories are never descended into; symlinks/special files are
    reported as problems (stage trees and evidence trees must be plain).
    """
    base = Path(root)
    files: dict[str, dict[str, Any]] = {}
    problems: list[str] = []
    if not base.exists():
        return files, ["root_absent"]
    for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
        current = Path(dirpath)
        for name in list(dirnames):
            path = current / name
            if path.is_symlink():
                problems.append(f"symlink_dir:{path.relative_to(base)}")
                dirnames.remove(name)
        for name in filenames:
            path = current / name
            relative = str(path.relative_to(base))
            try:
                info = os.lstat(path)
            except OSError as exc:
                problems.append(f"lstat_error:{relative}:{type(exc).__name__}")
                continue
            if stat.S_ISLNK(info.st_mode):
                problems.append(f"symlink:{relative}")
                continue
            if not stat.S_ISREG(info.st_mode):
                problems.append(f"special_file:{relative}")
                continue
            files[relative] = {
                "sha256": sha256_file(path),
                "bytes": info.st_size,
                "mode": stat.S_IMODE(info.st_mode),
            }
    return files, problems


def dir_tree_sha256(root: str | os.PathLike[str]) -> str:
    return sha256_tree(root)


# ---------------------------------------------------------------------------
# Stage manifest contract (also used by launch.py before any container starts)
# ---------------------------------------------------------------------------
STAGE_SCHEMA = "m0.g3d.stage.manifest.v1"

CANDIDATE_TOP_LEVEL_ALLOW = frozenset({
    "run", "config", "runtime", "node_modules", "native-cache", "pkg-cache",
    "fixtures", "etc", "REFERENCE.json",
})
TRUSTED_TOP_LEVEL_ALLOW = frozenset({
    "run", "src", "fake", "templates", "etc", "REFERENCE.json",
})
FORBIDDEN_CANDIDATE_SEGMENTS = frozenset({"autoteacher_m0", ".git"})
FORBIDDEN_CANDIDATE_TOP_LEVEL = frozenset({
    "src", "artifacts", "docs", "tests", "scripts", "evidence", "state",
    "receipts", "logs", "candidate-session",
})
FORBIDDEN_CANDIDATE_BASENAMES = frozenset({
    "admission.json", "broker.json", "policy.json", "controller.json",
    "admission.template.json", "broker.template.json", "controller.template.json",
    "broker.sqlite3", "attempts.sqlite3", "received-count.json",
    "controller.py", "attempts.py", "admission.py", "broker.py", "broker_client.py",
    "fake_backend.py", "fake_provider.py", "ipc_server.py", "protocol.py",
    "launch.py", "build_stage.py", "lib_g3d.py", "trusted_entry.py",
})
FORBIDDEN_CANDIDATE_SUFFIXES = (".sqlite3", ".sqlite3-wal", ".sqlite3-shm",
                                "-wal", "-shm")


def forbidden_candidate_reasons(relpaths: Iterable[str]) -> list[str]:
    reasons: list[str] = []
    for raw in relpaths:
        relative = str(raw).replace("\\", "/").lstrip("./")
        if not relative:
            continue
        parts = [part for part in relative.split("/") if part]
        if not parts:
            continue
        if parts[0] in CANDIDATE_TOP_LEVEL_ALLOW:
            pass
        else:
            reasons.append(f"top_level_not_allowed:{parts[0]}")
        if any(part in FORBIDDEN_CANDIDATE_SEGMENTS for part in parts):
            reasons.append(f"forbidden_segment:{relative}")
        if parts[0] in FORBIDDEN_CANDIDATE_TOP_LEVEL:
            reasons.append(f"forbidden_top_level:{relative}")
        name = parts[-1]
        if name in FORBIDDEN_CANDIDATE_BASENAMES:
            reasons.append(f"forbidden_basename:{relative}")
        lower = name.lower()
        if lower.startswith("rcpt-") and lower.endswith(".json"):
            reasons.append(f"forbidden_receipt:{relative}")
        if name.endswith(FORBIDDEN_CANDIDATE_SUFFIXES):
            reasons.append(f"forbidden_suffix:{relative}")
        if name.endswith(".py") and "site-packages" not in relative:
            # The candidate stage carries exactly one audited entrypoint plus
            # the exact D2 probe allow-list; anything else fails the stage.
            if relative != "run/candidate_entry.py" and relative not in D2_PROBE_PATHS:
                reasons.append(f"unexpected_python:{relative}")
    return sorted(set(reasons))


def validate_manifest_tree(stage_dir: str | os.PathLike[str],
                           manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Recompute hashes for both sections; detect unknown/extra/symlinked files."""
    base = Path(stage_dir)
    problems: list[str] = []
    summary: dict[str, Any] = {"stage_dir": str(base), "sections": {}}
    if manifest.get("schema") != STAGE_SCHEMA:
        problems.append("manifest_schema")
    for section in ("trusted", "candidate"):
        section_root = base / section
        expected_rows = (manifest.get(section) or {}).get("files")
        if not isinstance(expected_rows, list):
            problems.append(f"{section}:files_missing")
            continue
        expected = {}
        for row in expected_rows:
            if not isinstance(row, dict) or not isinstance(row.get("path"), str) \
                    or not isinstance(row.get("sha256"), str):
                problems.append(f"{section}:bad_row")
                continue
            expected[row["path"]] = row
        actual, structural = inventory_files(section_root)
        problems.extend(f"{section}:{item}" for item in structural)
        if set(actual) != set(expected):
            missing = sorted(set(expected) - set(actual))
            unknown = sorted(set(actual) - set(expected))
            problems.extend(f"{section}:missing:{item}" for item in missing[:20])
            problems.extend(f"{section}:unknown:{item}" for item in unknown[:20])
        for relative, info in actual.items():
            row = expected.get(relative)
            if row is None:
                continue
            if row.get("sha256") != info["sha256"]:
                problems.append(f"{section}:sha_mismatch:{relative}")
            if row.get("bytes") is not None and row["bytes"] != info["bytes"]:
                problems.append(f"{section}:bytes_mismatch:{relative}")
            if row.get("mode") is not None and row["mode"] != info["mode"]:
                problems.append(f"{section}:mode_mismatch:{relative}")
        declared_tree = (manifest.get(section) or {}).get("tree_sha256")
        if declared_tree:
            actual_tree = sha256_tree(section_root)
            if actual_tree != declared_tree:
                problems.append(f"{section}:tree_sha256_mismatch")
            summary["sections"][section] = {
                "tree_sha256": actual_tree, "file_count": len(actual),
            }
        else:
            problems.append(f"{section}:tree_sha256_missing")
        summary["sections"].setdefault(section, {})["files"] = len(actual)
    candidate_paths = [row["path"] for row in
                       (manifest.get("candidate") or {}).get("files", [])
                       if isinstance(row, dict) and isinstance(row.get("path"), str)]
    forbidden = forbidden_candidate_reasons(candidate_paths)
    problems.extend(f"candidate:{item}" for item in forbidden)
    summary["problems"] = problems
    summary["ok"] = not problems
    return summary


def validate_stage(stage_dir: str | os.PathLike[str], *,
                   verify_git: bool = True) -> dict[str, Any]:
    base = Path(stage_dir)
    manifest_path = base / "manifest.json"
    problems: list[str] = []
    try:
        raw = read_regular_bytes(manifest_path, max_bytes=128 << 20)
        manifest = json.loads(raw.decode("utf-8"))
    except (G3DError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise G3DError("stage manifest unreadable", exit_code=EXIT_STAGE_INVALID,
                       detail={"stage": str(base), "error": type(exc).__name__})
    if not isinstance(manifest, dict):
        raise G3DError("stage manifest is not an object",
                       exit_code=EXIT_STAGE_INVALID)
    validation = validate_manifest_tree(base, manifest)
    problems.extend(validation["problems"])
    if manifest.get("base_sha") != PRODUCT_BASE:
        problems.append(f"base_sha:{manifest.get('base_sha')}")
    for section in ("trusted", "candidate"):
        if not (base / section).is_dir():
            problems.append(f"{section}:root_missing")
    for required in ("trusted/run/trusted_entry.py",
                     "trusted/src/autoteacher_m0/bridge/controller.py",
                     "trusted/src/autoteacher_m0/bridge/ipc_server.py",
                     "trusted/fake/fake_provider.py",
                     "trusted/templates/controller.template.json",
                     "candidate/run/candidate_entry.py",
                     "candidate/config/bridge.patch.yml",
                     "candidate/runtime/bridge/lib/index.js",
                     "candidate/etc/passwd", "candidate/etc/group"):
        if not (base / required).is_file():
            problems.append(f"required_missing:{required}")
    if verify_git:
        base_sha = manifest.get("base_sha") or PRODUCT_BASE
        for row in (manifest.get("trusted") or {}).get("files", []):
            source = row.get("source") or {}
            if source.get("kind") != "git_blob":
                continue
            path = row.get("path")
            blob_path = source.get("path")
            try:
                actual = git_blob_sha256(base_sha, blob_path)
            except G3DError as exc:
                problems.append(f"git_source_unreadable:{path}:{exc}")
                continue
            if actual != row.get("sha256"):
                problems.append(f"git_blob_mismatch:{path}")
    result = {"ok": not problems, "problems": problems,
              "stage_dir": str(base),
              "manifest_sha256": sha256_bytes(raw),
              "base_sha": manifest.get("base_sha"),
              "sections": validation["sections"],
              "candidate_file_count":
                  len((manifest.get("candidate") or {}).get("files", [])),
              "trusted_file_count":
                  len((manifest.get("trusted") or {}).get("files", [])),
              "manifest": manifest}
    return result
