"""bwrap-based OS confinement for untrusted learner code (B-PR1).

This module implements the frozen sandbox boundary from the B-PR1 threat model:
one containerised ``python3`` process per case, no network, no host files, a
read-only minimal root filesystem, a private tmpfs, non-root uid/gid, rlimits
and a supervisor wall clock with whole-process-group kill.

Fail-closed rule
----------------
If ``bwrap`` is missing, cannot create the namespaces, lacks a required option,
or the canary self-check fails, :meth:`BwrapSandbox.available` returns ``False``
and :meth:`BwrapSandbox.run` raises :class:`SandboxUnavailable`.  There is **no
fallback** to a bare ``subprocess.run``: callers must map this to
``JUDGE_SANDBOX_UNAVAILABLE`` / blocked and must not execute learner code.
"""

from __future__ import annotations

import json
import math
import os
import resource
import selectors
import shutil
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Mapping, Sequence

from .protocol import JUDGE_SANDBOX_UNAVAILABLE

__all__ = [
    "BWRAP_BINARY",
    "WORKER_PYTHON",
    "SANDBOX_UID",
    "SANDBOX_GID",
    "SANDBOX_HOSTNAME",
    "SandboxResult",
    "SandboxUnavailable",
    "SandboxLaunchError",
    "BwrapSandbox",
]

BWRAP_BINARY = "/usr/bin/bwrap"
WORKER_PYTHON = "/usr/bin/python3"
SANDBOX_UID = 65534
SANDBOX_GID = 65534
SANDBOX_HOSTNAME = "m1b-worker"

#: Minimal read-only host filesystem exposed to the sandbox.
READ_ONLY_HOST_PATHS: tuple[str, ...] = ("/usr", "/lib", "/lib64", "/bin")

TMPFS_SIZE_BYTES = 16 * 1024 * 1024

#: Extra wall-clock grace on top of the request timeout used by the worker.
DEFAULT_RUN_GRACE_S = 0.5

#: Host-side rlimits (applied in ``preexec_fn`` before exec'ing bwrap).  The
#: effective per-sandbox ``RLIMIT_NPROC`` for learner code is set to 32 inside
#: ``worker_runner.py``: on the host, ``RLIMIT_NPROC`` counts processes of the
#: host uid and a tight value would break bwrap itself (verified on this host).
RLIMIT_AS_BYTES = 256 * 1024 * 1024
#: CPU-time rlimit must never fire before the supervisor wall clock (review
#: P1-1): it is set per run to ``max(10, ceil(wall_s) + 2)``, so the wall timer
#: (which classifies TLE) fires first.  A positive ``128+SIGKILL`` /
#: ``128+SIGXCPU`` / ``124`` exit is still classified as a student timeout by
#: :meth:`UntrustedExecutionWorker._interpret` as a defensive backstop.
RLIMIT_CPU_MIN_SECONDS = 10
RLIMIT_CPU_GRACE_SECONDS = 2

#: Deployment gate (review P1-2): when set to a truthy value, the sandbox
#: canary must verify a real non-root host principal; otherwise it fails closed
#: (``SandboxUnavailable`` -> blocked, no learner code executes).  Unset (the
#: local synthetic default) keeps ``LOCAL_ONLY`` usable but reports the gap.
REQUIRE_NONROOT_SANDBOX_ENV = "M1B_REQUIRE_NONROOT_SANDBOX"
_NONROOT_TRUTHY = frozenset({"1", "true", "yes", "on"})
RLIMIT_FSIZE_BYTES = 1024 * 1024
RLIMIT_NOFILE = 64
RLIMIT_NPROC_HOST_FLOOR = 4096
RLIMIT_CORE_BYTES = 0

SANDBOX_MAX_STDOUT_BYTES = 128 * 1024
SANDBOX_MAX_STDERR_BYTES = 16 * 1024

PROBE_SENTINEL_ENV = "M1B_SANDBOX_PROBE_SENTINEL"
PROBE_TIMEOUT_S = 10.0

_PROBE_SCRIPT = r"""
import json
import os
import socket
import sys


def _check():
    result = {
        "uid": os.getuid(),
        "gid": os.getgid(),
        "pid": os.getpid(),
        "hostname": socket.gethostname(),
        "root_visible": os.path.exists("/root"),
        "etc_visible": os.path.exists("/etc/passwd"),
        "host_sentinel_visible": os.path.exists(
            os.environ.get("M1B_SANDBOX_PROBE_SENTINEL", "/nonexistent-probe-sentinel")
        ),
        "python_version": sys.version.split()[0],
    }
    try:
        with open("/proc/self/uid_map", "r", encoding="utf-8") as handle:
            result["uid_map"] = " ".join(handle.read().split())
    except OSError:
        result["uid_map"] = ""
    try:
        result["interfaces"] = sorted(name for _index, name in socket.if_nameindex())
    except OSError:
        result["interfaces"] = ["<error>"]
    try:
        with open("/usr/m1b_sandbox_probe_write", "w", encoding="utf-8") as handle:
            handle.write("x")
        result["usr_write"] = "allowed"
    except OSError:
        result["usr_write"] = "denied"
    try:
        with open("/worker/m1b_sandbox_probe_write", "w", encoding="utf-8") as handle:
            handle.write("x")
        result["worker_write"] = "allowed"
    except OSError:
        result["worker_write"] = "denied"
    try:
        with open("/tmp/m1b_sandbox_probe_write", "w", encoding="utf-8") as handle:
            handle.write("x")
        result["tmp_write"] = "allowed"
    except OSError:
        result["tmp_write"] = "denied"
    try:
        with open("/proc/net/dev", "r", encoding="utf-8") as handle:
            interfaces_lines = [
                line.split(":")[0].strip()
                for line in handle.read().splitlines()[2:]
                if ":" in line
            ]
        result["proc_net_dev_interfaces"] = sorted(interfaces_lines)
    except OSError:
        result["proc_net_dev_interfaces"] = []
    return result


print(json.dumps(_check(), ensure_ascii=False, sort_keys=True))
"""


def require_nonroot_sandbox() -> bool:
    """True when the deployment demands a verified non-root host principal."""

    return (
        os.environ.get(REQUIRE_NONROOT_SANDBOX_ENV, "").strip().casefold()
        in _NONROOT_TRUTHY
    )


class SandboxUnavailable(RuntimeError):
    """The OS sandbox cannot be established; learner code must not be executed."""

    code = JUDGE_SANDBOX_UNAVAILABLE

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class SandboxLaunchError(RuntimeError):
    """The sandbox process could not be launched/observed (infrastructure error)."""


@dataclass(frozen=True)
class SandboxResult:
    """Raw, untrusted observation of one sandboxed process run."""

    exit_code: int | None
    stdout: bytes
    stderr: bytes
    timed_out: bool
    elapsed_s: float
    stdout_truncated: bool
    stderr_truncated: bool


def _count_processes_for_current_uid() -> int:
    uid = os.getuid()
    count = 0
    try:
        entries = os.listdir("/proc")
    except OSError:  # pragma: no cover - non-procfs hosts
        return RLIMIT_NPROC_HOST_FLOOR
    for entry in entries:
        if not entry.isdigit():
            continue
        try:
            if os.stat(f"/proc/{entry}").st_uid == uid:
                count += 1
        except OSError:
            continue
    return count


class BwrapSandbox:
    """Frozen bwrap confinement used by :class:`UntrustedExecutionWorker`."""

    def __init__(
        self,
        *,
        bwrap_path: str | Path = BWRAP_BINARY,
        worker_python: str | Path = WORKER_PYTHON,
        uid: int = SANDBOX_UID,
        gid: int = SANDBOX_GID,
        hostname: str = SANDBOX_HOSTNAME,
        tmpfs_size_bytes: int = TMPFS_SIZE_BYTES,
        max_stdout_bytes: int = SANDBOX_MAX_STDOUT_BYTES,
        max_stderr_bytes: int = SANDBOX_MAX_STDERR_BYTES,
        probe_timeout_s: float = PROBE_TIMEOUT_S,
        nproc_host_floor: int = RLIMIT_NPROC_HOST_FLOOR,
    ) -> None:
        self._bwrap = str(Path(bwrap_path))
        self._worker_python = str(Path(worker_python))
        self._uid = int(uid)
        self._gid = int(gid)
        self._hostname = hostname
        self._tmpfs_size_bytes = int(tmpfs_size_bytes)
        self._max_stdout_bytes = int(max_stdout_bytes)
        self._max_stderr_bytes = int(max_stderr_bytes)
        self._probe_timeout_s = float(probe_timeout_s)
        self._host_nproc_limit = max(
            int(nproc_host_floor), _count_processes_for_current_uid() + 1024
        )
        self._available: bool | None = None
        self._probe_failure: str | None = None
        self._probe_payload: dict[str, object] | None = None

    # -- availability ---------------------------------------------------------

    def available(self) -> bool:
        """Return whether the frozen sandbox passes its canary self-check.

        The result is cached for the lifetime of the sandbox object; a failed
        probe is never retried implicitly (call :meth:`refresh_availability` to
        re-probe explicitly).  A ``False`` result means callers must fail
        closed and must not execute learner code.
        """

        if self._available is None:
            self._probe()
        return bool(self._available)

    def probe_failure_reason(self) -> str | None:
        """Human-readable reason of the last failed probe (or ``None``)."""

        return self._probe_failure

    def refresh_availability(self) -> bool:
        self._available = None
        self._probe_failure = None
        self._probe_payload = None
        return self.available()

    # -- security profile (review P1-2) ------------------------------------

    @staticmethod
    def _non_root_principal_verified(host_euid: int, uid_map: str) -> bool:
        """True iff the host principal and every uid-map target are non-root.

        ``/proc/self/uid_map`` lines are ``inside outside length``; on a root
        host bwrap commonly maps inside 65534 to host uid 0 (``65534 0 1``),
        which must **not** count as a non-root principal.
        """

        if host_euid == 0:
            return False
        outside_uids: list[int] = []
        for line in uid_map.splitlines():
            parts = line.split()
            if len(parts) >= 3:
                try:
                    outside_uids.append(int(parts[1]))
                except ValueError:
                    continue
        return bool(outside_uids) and all(uid != 0 for uid in outside_uids)

    def security_profile(self) -> dict[str, object]:
        """Report whether this run has a real non-root host principal.

        The local worktree runs bwrap as **root** on this host, so inside-uid
        65534 may map to host uid 0 (``/proc/self/uid_map`` = ``65534 0 1``).
        Namespace uid 65534 is therefore **not** proof of an independent
        non-root OS principal.  The profile records host euid, uid_map and a
        ``non_root_principal_verified`` flag.  B1-04 must be verified on a
        deployment running as a non-root service account (or a separately
        reviewed setuid bwrap setup); the local result is ``LOCAL_ONLY``.
        """

        available = bool(self.available())
        payload = self._probe_payload or {}
        uid_map = str(payload.get("uid_map") or "")
        host_euid = os.geteuid()
        mapped_host_uids: list[int] = []
        for line in uid_map.splitlines():
            parts = line.split()
            if len(parts) >= 3:
                try:
                    mapped_host_uids.append(int(parts[1]))
                except ValueError:
                    continue
        non_root_verified = bool(
            available
            and self._non_root_principal_verified(host_euid, uid_map)
        )
        return {
            "profile": "NON_ROOT_PRINCIPAL" if non_root_verified else "LOCAL_ONLY",
            "host_euid": host_euid,
            "host_is_root": host_euid == 0,
            "sandbox_uid": self._uid,
            "sandbox_gid": self._gid,
            "uid_map": uid_map,
            "mapped_host_uids": mapped_host_uids,
            "sandbox_python_version": str(payload.get("python_version") or ""),
            "non_root_principal_verified": non_root_verified,
            "non_root_requirement_enforced": require_nonroot_sandbox(),
            "non_root_requirement_satisfied": bool(
                non_root_verified or not require_nonroot_sandbox()
            ),
            "sandbox_available": available,
            "limitation": (
                "local bwrap runs as root; sandbox uid 65534 may map to host uid 0. "
                "B1-04 requires a target deployment running as a non-root principal "
                "(or separately reviewed setuid bwrap) and is NOT satisfied locally."
            ),
        }

    def _probe(self) -> None:
        try:
            self._run_probe()
        except SandboxUnavailable as exc:
            self._available = False
            self._probe_failure = exc.reason
        except Exception as exc:  # noqa: BLE001 - fail closed on any probe error
            self._available = False
            self._probe_failure = f"canary self-check failed: {type(exc).__name__}"
        else:
            self._available = True
            self._probe_failure = None

    def _run_probe(self) -> None:
        bwrap = Path(self._bwrap)
        if not bwrap.is_file():
            raise SandboxUnavailable("bwrap binary is missing")
        if not os.access(bwrap, os.X_OK):
            raise SandboxUnavailable("bwrap binary is not executable")

        work_dir = Path(tempfile.mkdtemp(prefix="m1b_sandbox_probe_"))
        sentinel_dir = Path(tempfile.mkdtemp(prefix="m1b_sandbox_probe_host_"))
        try:
            script = work_dir / "probe.py"
            script.write_text(_PROBE_SCRIPT, encoding="utf-8")
            script.chmod(0o444)
            sentinel = sentinel_dir / "host_sentinel.txt"
            sentinel.write_text("SENTINEL_SANDBOX_PROBE\n", encoding="utf-8")

            result = self._spawn(
                work_dir,
                [self._worker_python, "/worker/probe.py"],
                timeout_s=self._probe_timeout_s,
                stdin_data=b"",
                extra_env={PROBE_SENTINEL_ENV: str(sentinel)},
            )
            if result.timed_out:
                raise SandboxUnavailable("canary self-check timed out")
            if result.exit_code != 0:
                raise SandboxUnavailable("canary self-check exited non-zero")
            try:
                payload = json.loads(result.stdout.decode("utf-8").strip())
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise SandboxUnavailable("canary self-check produced no valid JSON") from exc
            if not isinstance(payload, dict):
                raise SandboxUnavailable("canary self-check produced an unexpected payload")
            self._verify_probe_payload(payload)
            self._probe_payload = dict(payload)
            self._enforce_nonroot_requirement(payload)
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)
            shutil.rmtree(sentinel_dir, ignore_errors=True)

    def _enforce_nonroot_requirement(self, payload: Mapping[str, object]) -> None:
        """Fail closed at startup when a non-root principal is required (P1-2).

        The local synthetic default does not set the environment gate and keeps
        working as ``LOCAL_ONLY``; a deployment that sets
        ``M1B_REQUIRE_NONROOT_SANDBOX=1`` on a root host (or with a uid_map that
        maps inside-uid 65534 to host 0) gets ``SandboxUnavailable`` from the
        canary, so no learner code is ever executed.
        """

        if not require_nonroot_sandbox():
            return
        uid_map = str(payload.get("uid_map") or "")
        host_euid = os.geteuid()
        if not self._non_root_principal_verified(host_euid, uid_map):
            raise SandboxUnavailable(
                "non-root sandbox required but not verified: "
                f"host_euid={host_euid}, uid_map={uid_map!r}; refusing to run "
                "learner code (set M1B_REQUIRE_NONROOT_SANDBOX=0 only for "
                "local synthetic evaluation)"
            )

    def _verify_probe_payload(self, payload: Mapping[str, object]) -> None:
        if payload.get("uid") != self._uid or payload.get("gid") != self._gid:
            raise SandboxUnavailable("canary self-check: uid/gid confinement failed")
        if payload.get("hostname") != self._hostname:
            raise SandboxUnavailable("canary self-check: UTS confinement failed")
        if payload.get("root_visible") is not False:
            raise SandboxUnavailable("canary self-check: host /root is visible")
        if payload.get("etc_visible") is not False:
            raise SandboxUnavailable("canary self-check: host /etc is visible")
        if payload.get("host_sentinel_visible") is not False:
            raise SandboxUnavailable("canary self-check: host sentinel file is visible")
        if payload.get("interfaces") != ["lo"]:
            raise SandboxUnavailable("canary self-check: network isolation failed")
        if payload.get("proc_net_dev_interfaces") not in (["lo"], []):
            raise SandboxUnavailable("canary self-check: /proc/net/dev is not loopback-only")
        if payload.get("usr_write") != "denied":
            raise SandboxUnavailable("canary self-check: /usr is writable")
        if payload.get("worker_write") != "denied":
            raise SandboxUnavailable("canary self-check: /worker is writable")
        if payload.get("tmp_write") != "allowed":
            raise SandboxUnavailable("canary self-check: /tmp is not writable")
        pid = payload.get("pid")
        if not isinstance(pid, int) or pid < 2:
            raise SandboxUnavailable("canary self-check: PID namespace isolation failed")

    # -- command construction -------------------------------------------------

    def command(
        self,
        work_dir: str | Path,
        argv: Sequence[str],
        *,
        extra_env: Mapping[str, str] | None = None,
    ) -> list[str]:
        """Return the frozen bwrap command line for one run.

        Only ``work_dir`` is bind-mounted from the host (read-only, at
        ``/worker``); everything else is either a read-only system path, a
        fresh procfs/devtmpfs/tmpfs, or denied.  ``extra_env`` is only used by
        the internal canary probe; normal worker runs pass no host environment.
        """

        if not argv:
            raise SandboxLaunchError("sandbox argv must not be empty")
        command = [
            self._bwrap,
            "--unshare-all",
            "--die-with-parent",
            "--new-session",
            "--clearenv",
            "--cap-drop",
            "ALL",
        ]
        for host_path in READ_ONLY_HOST_PATHS:
            if os.path.exists(host_path):
                command.extend(["--ro-bind", host_path, host_path])
        command.extend(
            [
                "--ro-bind",
                str(Path(work_dir).resolve()),
                "/worker",
                "--proc",
                "/proc",
                "--dev",
                "/dev",
                # bwrap 0.9 requires --size *before* the --tmpfs it configures.
                "--size",
                str(self._tmpfs_size_bytes),
                "--tmpfs",
                "/tmp",
                "--uid",
                str(self._uid),
                "--gid",
                str(self._gid),
                "--hostname",
                self._hostname,
            ]
        )
        for key, value in (extra_env or {}).items():
            command.extend(["--setenv", str(key), str(value)])
        command.extend([str(part) for part in argv])
        return command

    # -- execution ------------------------------------------------------------

    def run(
        self,
        work_dir: str | Path,
        argv: Sequence[str],
        timeout_s: float,
        *,
        stdin_data: bytes | str = b"",
        extra_env: Mapping[str, str] | None = None,
    ) -> SandboxResult:
        """Run ``argv`` inside the sandbox and return the raw observation.

        Raises :class:`SandboxUnavailable` when the sandbox has not passed its
        canary self-check: no learner code may run in that case.  There is no
        degraded/non-sandboxed fallback path.
        """

        if not self.available():
            raise SandboxUnavailable(
                self._probe_failure or "OS sandbox is unavailable"
            )
        if timeout_s <= 0:
            raise SandboxLaunchError("timeout_s must be positive")
        directory = Path(work_dir)
        if not directory.is_dir():
            raise SandboxLaunchError("work_dir is not a directory")
        data = stdin_data.encode("utf-8") if isinstance(stdin_data, str) else stdin_data
        if not isinstance(data, bytes):
            raise SandboxLaunchError("stdin_data must be bytes or str")
        return self._spawn(directory, argv, timeout_s=float(timeout_s), stdin_data=data, extra_env=extra_env)

    @staticmethod
    def _cpu_limit_for_timeout(timeout_s: float) -> int:
        """CPU rlimit for one run; keeps the wall timeout as the primary limit."""

        return max(
            RLIMIT_CPU_MIN_SECONDS,
            int(math.ceil(max(0.0, float(timeout_s)))) + RLIMIT_CPU_GRACE_SECONDS,
        )

    def _apply_host_limits(self, cpu_seconds: int) -> None:  # pragma: no cover - child
        for limit, soft, hard in (
            (resource.RLIMIT_AS, RLIMIT_AS_BYTES, RLIMIT_AS_BYTES),
            (resource.RLIMIT_CPU, cpu_seconds, cpu_seconds),
            (resource.RLIMIT_FSIZE, RLIMIT_FSIZE_BYTES, RLIMIT_FSIZE_BYTES),
            (resource.RLIMIT_NOFILE, RLIMIT_NOFILE, RLIMIT_NOFILE),
            (resource.RLIMIT_NPROC, self._host_nproc_limit, self._host_nproc_limit),
            (resource.RLIMIT_CORE, RLIMIT_CORE_BYTES, RLIMIT_CORE_BYTES),
        ):
            resource.setrlimit(limit, (soft, hard))

    def _spawn(
        self,
        work_dir: Path,
        argv: Sequence[str],
        *,
        timeout_s: float,
        stdin_data: bytes = b"",
        extra_env: Mapping[str, str] | None = None,
    ) -> SandboxResult:
        command = self.command(work_dir, argv, extra_env=extra_env)
        cpu_limit = self._cpu_limit_for_timeout(timeout_s)
        started = time.monotonic()
        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
                env={},
                start_new_session=True,
                preexec_fn=partial(self._apply_host_limits, cpu_limit),
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise SandboxLaunchError(f"cannot launch bwrap: {type(exc).__name__}") from exc

        timed_out = False
        try:
            self._write_stdin(process, stdin_data)
            stdout, stderr, timed_out, stdout_truncated, stderr_truncated = self._drain(
                process, timeout_s
            )
            if timed_out:
                self._kill_process_group(process)
                self._drain_after_kill(process)
                stdout, stderr = b"", b""
                stdout_truncated = stderr_truncated = False
        finally:
            if process.poll() is None:
                self._kill_process_group(process)
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None:
                    try:
                        stream.close()
                    except OSError:  # pragma: no cover - defensive
                        pass
            try:
                process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:  # pragma: no cover - defensive
                process.kill()
                process.wait(timeout=5.0)

        elapsed = time.monotonic() - started
        return SandboxResult(
            exit_code=process.returncode,
            stdout=stdout,
            stderr=stderr,
            timed_out=timed_out,
            elapsed_s=elapsed,
            stdout_truncated=stdout_truncated,
            stderr_truncated=stderr_truncated,
        )

    @staticmethod
    def _write_stdin(process: subprocess.Popen, data: bytes) -> None:
        if process.stdin is None:  # pragma: no cover - defensive
            return
        try:
            remaining = memoryview(data)
            while remaining:
                written = process.stdin.write(remaining)
                if not written:  # pragma: no cover - defensive
                    break
                remaining = remaining[written:]
            process.stdin.close()
        except (BrokenPipeError, OSError):
            pass

    def _drain(
        self, process: subprocess.Popen, timeout_s: float
    ) -> tuple[bytes, bytes, bool, bool, bool]:
        """Read stdout/stderr with hard byte caps and a wall-clock deadline."""

        assert process.stdout is not None and process.stderr is not None
        deadline = time.monotonic() + timeout_s
        selector = selectors.DefaultSelector()
        selector.register(process.stdout.fileno(), selectors.EVENT_READ, "stdout")
        selector.register(process.stderr.fileno(), selectors.EVENT_READ, "stderr")
        buffers: dict[str, bytearray] = {"stdout": bytearray(), "stderr": bytearray()}
        caps = {"stdout": self._max_stdout_bytes, "stderr": self._max_stderr_bytes}
        truncated = {"stdout": False, "stderr": False}
        open_streams = 2
        timed_out = False
        try:
            while open_streams:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    timed_out = True
                    break
                events = selector.select(min(remaining, 0.1))
                for key, _mask in events:
                    name = key.data
                    try:
                        chunk = os.read(key.fd, 65536)
                    except OSError:
                        chunk = b""
                    if not chunk:
                        selector.unregister(key.fd)
                        open_streams -= 1
                        continue
                    buffer = buffers[name]
                    cap = caps[name]
                    if len(buffer) < cap:
                        remaining_capacity = cap - len(buffer)
                        buffer.extend(chunk[:remaining_capacity])
                        if len(chunk) > remaining_capacity:
                            truncated[name] = True
                    else:
                        truncated[name] = True
            # EOF reached for both streams: let the process finish.
            if not timed_out and process.poll() is None:
                try:
                    process.wait(timeout=min(2.0, max(0.1, deadline - time.monotonic())))
                except subprocess.TimeoutExpired:
                    timed_out = True
        finally:
            selector.close()
        return (
            bytes(buffers["stdout"]),
            bytes(buffers["stderr"]),
            timed_out,
            truncated["stdout"],
            truncated["stderr"],
        )

    @staticmethod
    def _kill_process_group(process: subprocess.Popen) -> None:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            try:
                process.kill()
            except (ProcessLookupError, OSError):
                pass

    def _drain_after_kill(self, process: subprocess.Popen) -> None:
        """Best-effort drain of already-buffered output after killing the group."""

        deadline = time.monotonic() + 1.0
        for stream in (process.stdout, process.stderr):
            if stream is None:  # pragma: no cover - defensive
                continue
            try:
                os.set_blocking(stream.fileno(), False)
            except (OSError, AttributeError):  # pragma: no cover - defensive
                continue
        while time.monotonic() < deadline:
            if process.poll() is not None:
                break
            time.sleep(0.01)
        for stream in (process.stdout, process.stderr):
            if stream is None:  # pragma: no cover - defensive
                continue
            try:
                while True:
                    chunk = os.read(stream.fileno(), 65536)
                    if not chunk:
                        break
            except (BlockingIOError, OSError):
                break

    def describe(self) -> dict:
        """Return a non-sensitive summary used by tests/diagnostics."""

        return {
            "bwrap": self._bwrap,
            "worker_python": self._worker_python,
            "uid": self._uid,
            "gid": self._gid,
            "hostname": self._hostname,
            "available": self._available,
            "probe_failure": self._probe_failure,
        }
