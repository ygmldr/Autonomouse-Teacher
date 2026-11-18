"""External watchdog for one restricted Live run (no key, no model calls here).

The watchdog owns wall-clock deadline, step/dispatch caps, process-tree kill,
container cleanup confirmation and conservative PENDING accounting. It is
deliberately separate from the SDK: a hung/failed run must not depend on the
candidate process to stop itself, and an unknown outcome must never be retried.

Deployment of this module as the real Live watchdog is PR3 design work; this
task validates it only with hung mock subprocesses and a fake container engine.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import os
from pathlib import Path
import signal
import subprocess
import time
from typing import Callable, Mapping, Sequence

from autoteacher_m0.contracts import ErrorCode, RuntimeFailure

_WATCHDOG_MAX_SECONDS = 3600.0
_WATCHDOG_MAX_STEPS = 200
_WATCHDOG_MAX_DISPATCH = 50


class WatchdogViolation(RuntimeFailure):
    def __init__(self, reasons: Sequence[str]):
        super().__init__(ErrorCode.SECURITY_BLOCKED, "; ".join(reasons) or "WATCHDOG_FAILED")
        self.reasons = tuple(reasons)


class RunStatus(StrEnum):
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    TIMEOUT_KILLED = "TIMEOUT_KILLED"
    STEP_LIMIT_KILLED = "STEP_LIMIT_KILLED"
    DISPATCH_LIMIT_KILLED = "DISPATCH_LIMIT_KILLED"


@dataclass(frozen=True)
class WatchdogPolicy:
    total_seconds: float = 60.0
    max_steps: int = 30
    max_dispatch_attempts: int = 10
    termination_grace_seconds: float = 1.0
    poll_interval_seconds: float = 0.02

    def __post_init__(self) -> None:
        if not (0.1 <= self.total_seconds <= _WATCHDOG_MAX_SECONDS):
            raise ValueError("total_seconds exceeds the fixed M0 watchdog policy")
        if not (1 <= self.max_steps <= _WATCHDOG_MAX_STEPS):
            raise ValueError("max_steps exceeds the fixed M0 watchdog policy")
        if not (1 <= self.max_dispatch_attempts <= _WATCHDOG_MAX_DISPATCH):
            raise ValueError("max_dispatch_attempts exceeds the fixed M0 watchdog policy")
        if not (0.05 <= self.termination_grace_seconds <= 10):
            raise ValueError("termination grace is outside the fixed policy")
        if not (0.005 <= self.poll_interval_seconds <= 1):
            raise ValueError("poll interval is outside the fixed policy")


@dataclass(frozen=True)
class PendingConservative:
    """Unknown/timeout outcomes reserve worst case and forbid automatic retry."""

    status: str = "PENDING_CONSERVATIVE"
    reason: str = ""
    retry_allowed: bool = False
    worst_case_reserved: bool = True


@dataclass(frozen=True)
class ProcessTreeKillResult:
    root_pid: int
    signaled: tuple[int, ...]
    survivors: tuple[int, ...]
    confirmed_absent: bool


@dataclass(frozen=True)
class ProcessAbsenceReport:
    """Independent /proc re-check; a signal or ``kill()`` return is not absence."""

    checked: tuple[int, ...]
    absent: tuple[int, ...]
    survivors: tuple[int, ...]
    proc_entries: tuple[int, ...]

    @property
    def confirmed(self) -> bool:
        return not self.survivors


@dataclass(frozen=True)
class PathAbsenceReport:
    """``rm -f`` exit 0 is not proof; each path is re-observed with ``lstat``."""

    checked: tuple[str, ...]
    present: tuple[str, ...]
    details: Mapping[str, Mapping[str, object]]

    @property
    def confirmed(self) -> bool:
        return not self.present


@dataclass(frozen=True)
class WatchdogOutcome:
    status: RunStatus
    elapsed_seconds: float
    steps: int
    dispatch_attempts: int
    kill_result: ProcessTreeKillResult | None = None
    pending: PendingConservative | None = None
    cleanup: Mapping[str, object] = field(default_factory=dict)
    detail: str = ""


def _proc_ppid(pid: int) -> int | None:
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="ascii")
    except (OSError, UnicodeError):
        return None
    try:
        return int(stat[stat.rindex(")") + 2:].split()[1])
    except (ValueError, IndexError):
        return None


def _proc_alive(pid: int) -> bool:
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="ascii")
    except (OSError, UnicodeError):
        return False
    return "] " in stat and not stat[stat.rindex(")") + 2:].startswith("Z")


def _descendants(root_pid: int) -> set[int]:
    family: set[int] = set()
    frontier = {root_pid}
    while frontier:
        current = frontier.pop()
        for candidate in Path("/proc").iterdir():
            if not candidate.name.isdigit():
                continue
            child = int(candidate.name)
            if child in family or _proc_ppid(child) != current:
                continue
            family.add(child)
            frontier.add(child)
    return family


def kill_process_tree(process: subprocess.Popen[bytes], *,
                      grace_seconds: float = 1.0) -> ProcessTreeKillResult:
    """Terminate the root, its process group and descendants; verify absence."""
    root_pid = process.pid
    family = {root_pid} | _descendants(root_pid)
    signaled: set[int] = set()
    for pid in sorted(family):
        try:
            os.kill(pid, signal.SIGTERM)
            signaled.add(pid)
        except (ProcessLookupError, PermissionError):
            continue
    try:
        os.killpg(root_pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        pass
    deadline = time.monotonic() + grace_seconds
    while time.monotonic() < deadline and any(_proc_alive(pid) for pid in family):
        time.sleep(0.01)
    family |= _descendants(root_pid)
    for pid in sorted(family):
        if not _proc_alive(pid):
            continue
        try:
            os.kill(pid, signal.SIGKILL)
            signaled.add(pid)
        except (ProcessLookupError, PermissionError):
            continue
    try:
        os.killpg(root_pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass
    survivors = tuple(pid for pid in sorted(family) if _proc_alive(pid))
    return ProcessTreeKillResult(root_pid, tuple(sorted(signaled)), survivors, not survivors)


def confirm_container_absence(engine: str | Sequence[str], name: str, *,
                              runner: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
                              env: Mapping[str, str] | None = None) -> dict[str, object]:
    """Cleanup must be observed, not inferred from a generic rc=1 of ``rm``."""
    prefix = [engine] if isinstance(engine, str) else list(engine)
    if not prefix or any(not isinstance(item, str) or not item for item in prefix):
        raise ValueError("container engine prefix must be nonempty strings")
    safe_env = {"PATH": "/usr/bin:/bin", "LANG": "C", "HOME": "/work"}
    if env is not None:
        safe_env = dict(env)
    try:
        cleanup = runner([*prefix, "rm", "--force", name], env=safe_env,
                         stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL, timeout=5, check=False)
        absence = runner([*prefix, "ps", "--all", "--filter", f"name=^{name}$",
                          "--format", "{{.Names}}"], env=safe_env,
                         stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL, timeout=5, check=False)
    except (subprocess.TimeoutExpired, OSError) as error:
        # A hung or unavailable engine cannot be interpreted as absence.
        raise WatchdogViolation(
            (f"CONTAINER_QUERY_UNAVAILABLE:{type(error).__name__}",)) from error
    evidence: dict[str, object] = {
        "engine": prefix, "name": name, "remove_returncode": cleanup.returncode,
        "absence_returncode": absence.returncode, "names_after": absence.stdout.decode(
            encoding="utf-8", errors="replace").strip(),
    }
    if absence.returncode != 0 or evidence["names_after"]:
        raise WatchdogViolation(("CONTAINER_CLEANUP_NOT_CONFIRMED",))
    return evidence


def confirm_process_absence(pids: Sequence[int], *,
                            proc_root: str | os.PathLike[str] = "/proc",
                            ) -> ProcessAbsenceReport:
    """Re-read ``/proc`` for each pid; zombies count as absent (already exited)."""
    checked: list[int] = []
    absent: list[int] = []
    survivors: list[int] = []
    entries: list[int] = []
    for raw_pid in pids:
        pid = int(raw_pid)
        if pid in checked:
            continue
        checked.append(pid)
        if not Path(proc_root, str(pid)).exists():
            absent.append(pid)
            continue
        entries.append(pid)
        if _proc_alive(pid):
            survivors.append(pid)
        else:
            absent.append(pid)
    return ProcessAbsenceReport(tuple(sorted(checked)), tuple(sorted(absent)),
                                tuple(sorted(survivors)), tuple(sorted(entries)))


def confirm_path_absence(paths: Sequence[str | os.PathLike[str]]
                         ) -> PathAbsenceReport:
    """Observe socket/run-dir removal instead of trusting the unlink return code."""
    checked: list[str] = []
    present: list[str] = []
    details: dict[str, dict[str, object]] = {}
    for raw in paths:
        path = str(raw)
        if path in checked:
            continue
        checked.append(path)
        try:
            info = os.lstat(path)
        except FileNotFoundError:
            details[path] = {"present": False}
            continue
        except OSError as error:
            details[path] = {"present": True, "error": type(error).__name__}
            present.append(path)
            continue
        present.append(path)
        details[path] = {"present": True, "mode": info.st_mode,
                         "uid": info.st_uid, "gid": info.st_gid,
                         "inode": info.st_ino}
    return PathAbsenceReport(tuple(checked), tuple(present), details)


def scan_marked_processes(markers: Sequence[str], *,
                          exclude_pids: Sequence[int] = (),
                          proc_root: str | os.PathLike[str] = "/proc") -> list[dict]:
    """Find escaped/reparented processes by argv, environ or cwd marker.

    ``kill_process_tree`` follows parent/child and process-group edges. A child
    that double-forks and detaches from both is still observable through the
    run-specific markers (run id, run dir, container name); the external
    watchdog must kill those too before it may claim absence.
    """
    excluded = {int(pid) for pid in exclude_pids}
    raised: list[dict] = []
    root = Path(proc_root)
    for entry in root.iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        if pid in excluded:
            continue
        hits: list[str] = []
        argv: list[str] = []
        try:
            raw = (entry / "cmdline").read_bytes()[:8192]
        except OSError:
            continue
        argv = [part.decode("utf-8", "replace") for part in raw.split(b"\0") if part]
        joined = "\n".join(argv)
        hits.extend(marker for marker in markers if marker and marker in joined)
        if not hits:
            try:
                environ = (entry / "environ").read_bytes()[:65536]
            except OSError:
                environ = b""
            text = environ.decode("utf-8", "replace")
            hits.extend(marker for marker in markers if marker and marker in text)
        if not hits:
            try:
                cwd = os.readlink(entry / "cwd")
            except OSError:
                cwd = ""
            hits.extend(marker for marker in markers if marker and marker in cwd)
        if hits:
            raised.append({"pid": pid, "argv": argv[:16],
                           "markers": sorted(set(hits))[:8]})
    return raised


class ExternalWatchdog:
    """One run's deadline/step/dispatch state machine; never retries."""

    def __init__(self, policy: WatchdogPolicy,
                 clock: Callable[[], float] = time.monotonic):
        self.policy = policy
        self._clock = clock
        self._started_at: float | None = None
        self.steps = 0
        self.dispatch_attempts = 0
        self.latched: RunStatus | None = None
        self.latch_reason = ""

    def start(self) -> None:
        self._started_at = self._clock()

    def elapsed(self) -> float:
        if self._started_at is None:
            raise RuntimeError("watchdog has not started")
        return self._clock() - self._started_at

    def remaining(self) -> float:
        return self.policy.total_seconds - self.elapsed()

    def record_step(self) -> None:
        self.steps += 1
        if self.steps > self.policy.max_steps and self.latched is None:
            self.latched = RunStatus.STEP_LIMIT_KILLED
            self.latch_reason = "MAX_STEPS_EXCEEDED"

    def record_dispatch_attempt(self) -> None:
        self.dispatch_attempts += 1
        if self.dispatch_attempts > self.policy.max_dispatch_attempts and self.latched is None:
            self.latched = RunStatus.DISPATCH_LIMIT_KILLED
            self.latch_reason = "MAX_DISPATCH_ATTEMPTS_EXCEEDED"

    def exceeded(self) -> RunStatus | None:
        if self.latched is not None:
            return self.latched
        if self._started_at is None:
            raise RuntimeError("watchdog has not started")
        if self.remaining() <= 0 and self.latched is None:
            self.latched = RunStatus.TIMEOUT_KILLED
            self.latch_reason = "TOTAL_DEADLINE_EXCEEDED"
        return self.latched

    def supervise(self, process: subprocess.Popen[bytes], *,
                  cleanup: Callable[[], Mapping[str, object]] | None = None) -> WatchdogOutcome:
        """Poll the root; on ANY abnormal path kill the tree, run cleanup and fail closed.

        WD-03/WD-04: cleanup is not conditional on a happy path. Any exception,
        timeout, step/dispatch latch or cleanup failure is turned into a
        ``WatchdogViolation`` (``SECURITY_BLOCKED``) after the process tree has
        been killed and absence was attempted; no success outcome is returned and
        the caller must not start another billable attempt.
        """
        self.start()
        status: RunStatus | None = None
        root_error: BaseException | None = None
        try:
            while True:
                latch = self.exceeded()
                if latch is not None:
                    status = latch
                    break
                if process.poll() is not None:
                    status = RunStatus.COMPLETED if process.returncode == 0 else RunStatus.FAILED
                    break
                time.sleep(min(self.policy.poll_interval_seconds,
                               max(0.001, self.remaining())))
        except BaseException as error:  # controller-side crash must still clean up
            root_error = error

        kill_result: ProcessTreeKillResult | None = None
        pending: PendingConservative | None = None
        reasons: list[str] = []
        cleanup_evidence: dict[str, object] = {}
        try:
            if root_error is not None:
                if process.poll() is None:
                    kill_result = self._kill(process, reasons)
            elif status not in (RunStatus.COMPLETED, RunStatus.FAILED):
                kill_result = self._kill(process, reasons)
                pending = PendingConservative(reason=self.latch_reason or str(status))
            if cleanup is not None:
                try:
                    evidence = cleanup()
                except WatchdogViolation as error:
                    reasons.extend(error.reasons)
                except BaseException as error:  # timeout/absent/failed cleanup: BLOCKED
                    reasons.append(f"CLEANUP_FAILED:{type(error).__name__}")
                else:
                    if not isinstance(evidence, Mapping):
                        reasons.append("CLEANUP_EVIDENCE_INVALID")
                    else:
                        cleanup_evidence = dict(evidence)
            if reasons:
                raise WatchdogViolation(tuple(dict.fromkeys(reasons)))
            if root_error is not None:
                raise root_error
            if status is RunStatus.FAILED:
                pending = PendingConservative(reason="PROCESS_EXIT_NONZERO_UNKNOWN_EFFECTS")
            return WatchdogOutcome(
                status=status, elapsed_seconds=self.elapsed(), steps=self.steps,
                dispatch_attempts=self.dispatch_attempts, kill_result=kill_result,
                pending=pending, cleanup=cleanup_evidence, detail=self.latch_reason,
            )
        finally:
            # Safety net: never leave a live candidate tree behind any exit path.
            if process.poll() is None:
                try:
                    kill_process_tree(process,
                                      grace_seconds=self.policy.termination_grace_seconds)
                except BaseException:
                    pass

    def _kill(self, process: subprocess.Popen[bytes],
              reasons: list[str]) -> ProcessTreeKillResult | None:
        try:
            result = kill_process_tree(
                process, grace_seconds=self.policy.termination_grace_seconds)
        except BaseException:
            reasons.append("PROCESS_TREE_KILL_FAILED")
            return None
        if not result.confirmed_absent:
            reasons.append("PROCESS_TREE_NOT_CONFIRMED_ABSENT")
        return result
