"""Offline watchdog tests: hung mock subprocesses only, no model/network calls."""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import time

import pytest

from autoteacher_m0.security.watchdog import (
    ExternalWatchdog,
    PendingConservative,
    RunStatus,
    WatchdogPolicy,
    WatchdogViolation,
    confirm_container_absence,
    kill_process_tree,
)


def _live_pids() -> set[int]:
    live: set[int] = set()
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            stat = (entry / "stat").read_text(encoding="ascii")
        except (OSError, UnicodeError):
            continue
        if "] " in stat and not stat[stat.rindex(")") + 2:].startswith("Z"):
            live.add(int(entry.name))
    return live


def spawn_hung(*, grandchild: bool = False) -> subprocess.Popen[bytes]:
    if grandchild:
        code = (
            "import subprocess, sys, time\n"
            "child = subprocess.Popen([sys.executable, '-c', "
            "'import time; time.sleep(30)'])\n"
            "print(child.pid, flush=True)\n"
            "time.sleep(30)\n"
        )
    else:
        code = "import time; time.sleep(30)\n"
    return subprocess.Popen([sys.executable, "-c", code], stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            start_new_session=True)


def test_watchdog_policy_bounds() -> None:
    assert WatchdogPolicy().max_steps == 30
    for kwargs in ({"total_seconds": 0}, {"total_seconds": 3601}, {"max_steps": 0},
                   {"max_steps": 201}, {"max_dispatch_attempts": 0},
                   {"max_dispatch_attempts": 51}, {"termination_grace_seconds": 0}):
        with pytest.raises(ValueError):
            WatchdogPolicy(**kwargs)


def test_step_and_dispatch_limits_latch() -> None:
    watchdog = ExternalWatchdog(WatchdogPolicy(max_steps=2, max_dispatch_attempts=1))
    watchdog.start()
    watchdog.record_step()
    watchdog.record_step()
    assert watchdog.exceeded() is None
    watchdog.record_step()
    assert watchdog.exceeded() is RunStatus.STEP_LIMIT_KILLED
    watchdog.record_dispatch_attempt()
    assert watchdog.exceeded() is RunStatus.STEP_LIMIT_KILLED  # first latch wins
    other = ExternalWatchdog(WatchdogPolicy(max_dispatch_attempts=1))
    other.start()
    other.record_dispatch_attempt()
    other.record_dispatch_attempt()
    assert other.exceeded() is RunStatus.DISPATCH_LIMIT_KILLED


def test_timeout_kills_hung_process_and_reserves_pending() -> None:
    process = spawn_hung()
    cleanup_calls: list[str] = []
    watchdog = ExternalWatchdog(WatchdogPolicy(total_seconds=0.3, max_steps=5,
                                               termination_grace_seconds=0.2))
    outcome = watchdog.supervise(process, cleanup=lambda: cleanup_calls.append("cleanup") or
                                 {"container": "at-m0-fake", "confirmed": True})
    assert outcome.status is RunStatus.TIMEOUT_KILLED
    assert outcome.detail == "TOTAL_DEADLINE_EXCEEDED"
    assert outcome.pending == PendingConservative(reason="TOTAL_DEADLINE_EXCEEDED")
    assert outcome.pending.retry_allowed is False
    assert outcome.pending.worst_case_reserved is True
    assert outcome.kill_result is not None and outcome.kill_result.confirmed_absent
    assert cleanup_calls == ["cleanup"]
    assert outcome.cleanup["confirmed"] is True
    assert process.poll() is not None


def test_process_tree_kills_descendants() -> None:
    process = spawn_hung(grandchild=True)
    assert process.stdout is not None
    child_pid = int(process.stdout.readline().decode().strip())
    result = kill_process_tree(process, grace_seconds=0.3)
    assert result.confirmed_absent
    assert child_pid not in _live_pids()
    assert child_pid in result.signaled or not Path(f"/proc/{child_pid}").exists()


def test_nonzero_exit_is_failed_and_pending() -> None:
    process = subprocess.Popen([sys.executable, "-c", "raise SystemExit(7)"],
                               stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, start_new_session=True)
    watchdog = ExternalWatchdog(WatchdogPolicy(total_seconds=5))
    outcome = watchdog.supervise(process)
    assert outcome.status is RunStatus.FAILED
    assert outcome.pending is not None
    assert outcome.pending.retry_allowed is False


def test_successful_exit_has_no_pending() -> None:
    process = subprocess.Popen([sys.executable, "-c", "raise SystemExit(0)"],
                               stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, start_new_session=True)
    outcome = ExternalWatchdog(WatchdogPolicy(total_seconds=5)).supervise(process)
    assert outcome.status is RunStatus.COMPLETED
    assert outcome.pending is None


def fake_engine(tmp_path: Path) -> Path:
    engine = tmp_path / "fake-engine"
    engine.write_text(
        "#!/opt/python/bin/python3.11\n"
        "import os, sys\n"
        "base = os.path.dirname(os.path.abspath(__file__))\n"
        "if sys.argv[1] == 'rm':\n"
        "    code_file = os.path.join(base, 'rm_code.txt')\n"
        "    sys.exit(int(open(code_file).read()) if os.path.exists(code_file) else 0)\n"
        "if sys.argv[1] == 'ps':\n"
        "    if os.path.exists(os.path.join(base, 'ps_fail')):\n"
        "        sys.exit(2)\n"
        "    names = os.path.join(base, 'ps_names.txt')\n"
        "    if os.path.exists(names):\n"
        "        sys.stdout.write(open(names).read())\n"
        "    sys.exit(0)\n"
        "sys.exit(9)\n", encoding="utf-8")
    engine.chmod(0o755)
    return engine


def test_container_cleanup_requires_observed_absence(tmp_path: Path) -> None:
    engine = fake_engine(tmp_path)
    prefix = [sys.executable, str(engine)]
    evidence = confirm_container_absence(prefix, "at-m0-live-candidate")
    assert evidence["names_after"] == ""
    (tmp_path / "ps_names.txt").write_text("at-m0-live-candidate\n", encoding="utf-8")
    with pytest.raises(WatchdogViolation):
        confirm_container_absence(prefix, "at-m0-live-candidate")
    (tmp_path / "ps_names.txt").unlink()
    (tmp_path / "ps_fail").write_text("1", encoding="utf-8")
    with pytest.raises(WatchdogViolation):
        confirm_container_absence(prefix, "at-m0-live-candidate")
    (tmp_path / "ps_fail").unlink()
    (tmp_path / "rm_code.txt").write_text("1", encoding="utf-8")
    evidence = confirm_container_absence(prefix, "at-m0-live-candidate")
    assert evidence["remove_returncode"] == 1  # generic rm rc=1 is not proof of absence
    assert evidence["absence_returncode"] == 0


def test_wd03_cleanup_failure_after_exception_is_security_blocked() -> None:
    process = spawn_hung()
    watchdog = ExternalWatchdog(WatchdogPolicy(total_seconds=5,
                                               termination_grace_seconds=0.2))
    with pytest.raises(WatchdogViolation) as error:
        watchdog.supervise(process, cleanup=lambda: (_ for _ in ()).throw(
            RuntimeError("boom")))
    assert "CLEANUP" in str(error.value) or any(
        "CLEANUP" in reason for reason in error.value.reasons)
    assert process.poll() is not None
    time.sleep(0.05)
    assert not Path(f"/proc/{process.pid}").exists() or process.poll() is not None


def test_wd03_exception_path_still_runs_cleanup_and_kills_tree() -> None:
    process = spawn_hung()
    cleanup_calls: list[str] = []

    class ControllerCrash(ExternalWatchdog):
        def exceeded(self):
            raise RuntimeError("controller crashed")

    watchdog = ControllerCrash(WatchdogPolicy(total_seconds=5,
                                              termination_grace_seconds=0.2))
    with pytest.raises(RuntimeError):
        watchdog.supervise(process, cleanup=lambda: cleanup_calls.append("cleanup")
                           or {"container": "at-m0-fake", "confirmed": True})
    assert cleanup_calls == ["cleanup"], "cleanup must run before re-raising"
    assert process.poll() is not None


def test_wd04_cleanup_failure_on_normal_completion_is_not_success() -> None:
    process = subprocess.Popen([sys.executable, "-c", "raise SystemExit(0)"],
                               stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, start_new_session=True)
    watchdog = ExternalWatchdog(WatchdogPolicy(total_seconds=5))
    with pytest.raises(WatchdogViolation):
        watchdog.supervise(process, cleanup=lambda: (_ for _ in ()).throw(
            TimeoutError("cleanup timed out")))
    assert process.poll() is not None
