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
    cleanup = runner([*prefix, "rm", "--force", name], env=safe_env,
                     stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                     stderr=subprocess.DEVNULL, timeout=5, check=False)
    absence = runner([*prefix, "ps", "--all", "--filter", f"name=^{name}$",
                      "--format", "{{.Names}}"], env=safe_env,
                     stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                     stderr=subprocess.DEVNULL, timeout=5, check=False)
    evidence: dict[str, object] = {
        "engine": prefix, "name": name, "remove_returncode": cleanup.returncode,
        "absence_returncode": absence.returncode, "names_after": absence.stdout.decode(
            encoding="utf-8", errors="replace").strip(),
    }
    if absence.returncode != 0 or evidence["names_after"]:
        raise WatchdogViolation(("CONTAINER_CLEANUP_NOT_CONFIRMED",))
    return evidence


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
        """Poll the root process; on timeout/limit kill the tree and reserve pending."""
        self.start()
        try:
            while True:
                status = self.exceeded()
                if status is not None:
                    break
                if process.poll() is not None:
                    status = RunStatus.COMPLETED if process.returncode == 0 else RunStatus.FAILED
                    break
                time.sleep(min(self.policy.poll_interval_seconds,
                               max(0.001, self.remaining())))
        except BaseException:
            # Even controller-side crashes must not leave the candidate running.
            if process.poll() is None:
                kill_process_tree(process,
                                  grace_seconds=self.policy.termination_grace_seconds)
            raise
        cleanup_evidence: Mapping[str, object] = {}
        pending: PendingConservative | None = None
        kill_result: ProcessTreeKillResult | None = None
        if status is not None and status not in (RunStatus.COMPLETED, RunStatus.FAILED):
            kill_result = kill_process_tree(
                process, grace_seconds=self.policy.termination_grace_seconds)
            pending = PendingConservative(reason=self.latch_reason or status.value)
            if not kill_result.confirmed_absent:
                raise WatchdogViolation(("PROCESS_TREE_NOT_CONFIRMED_ABSENT",))
        if cleanup is not None:
            cleanup_evidence = dict(cleanup())
        if status is RunStatus.FAILED:
            pending = PendingConservative(reason="PROCESS_EXIT_NONZERO_UNKNOWN_EFFECTS")
        return WatchdogOutcome(
            status=status, elapsed_seconds=self.elapsed(), steps=self.steps,
            dispatch_attempts=self.dispatch_attempts, kill_result=kill_result,
            pending=pending, cleanup=cleanup_evidence, detail=self.latch_reason,
        )
