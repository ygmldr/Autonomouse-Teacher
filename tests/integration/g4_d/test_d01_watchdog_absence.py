"""D01/D08: a signal or rc=0 is not absence; only an independent re-check is."""
from __future__ import annotations

import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest

from autoteacher_m0.security.watchdog import (
    ExternalWatchdog,
    WatchdogPolicy,
    WatchdogViolation,
    confirm_container_absence,
    confirm_path_absence,
    confirm_process_absence,
    scan_marked_processes,
)

NAME = "at-g3d-candidate-g4d-d01"


def fake_engine(root: Path, *, rm_exit: int = 0, ps_exit: int = 0,
                names: str = "") -> list[str]:
    """A stand-in engine that can lie about rm, fail ps or hang ps."""
    script = root / "engine.py"
    script.write_text(
        "import os, sys, time\n"
        "base = os.path.dirname(os.path.abspath(__file__))\n"
        "if sys.argv[1] == 'rm':\n"
        "    sys.exit(int(open(os.path.join(base, 'rm_exit.txt')).read()))\n"
        "if sys.argv[1] == 'ps':\n"
        "    if os.path.exists(os.path.join(base, 'ps_hang')):\n"
        "        time.sleep(10)\n"
        "    if os.path.exists(os.path.join(base, 'ps_names.txt')):\n"
        "        sys.stdout.write(open(os.path.join(base, 'ps_names.txt')).read())\n"
        "    sys.exit(int(open(os.path.join(base, 'ps_exit.txt')).read()))\n"
        "sys.exit(9)\n", encoding="utf-8")
    (root / "rm_exit.txt").write_text(str(rm_exit), encoding="utf-8")
    (root / "ps_exit.txt").write_text(str(ps_exit), encoding="utf-8")
    if names:
        (root / "ps_names.txt").write_text(names, encoding="utf-8")
    return [sys.executable, str(script)]


def test_rm_rc_zero_is_not_absence_without_ps_recheck(tmp_path: Path) -> None:
    engine = fake_engine(tmp_path, rm_exit=0, ps_exit=0)
    evidence = confirm_container_absence(engine, NAME)
    assert evidence["remove_returncode"] == 0
    assert evidence["names_after"] == ""
    # rm still says 0, but ps now reports the name: that is NOT absence.
    (tmp_path / "ps_names.txt").write_text(NAME + "\n", encoding="utf-8")
    with pytest.raises(WatchdogViolation) as error:
        confirm_container_absence(engine, NAME)
    assert "CONTAINER_CLEANUP_NOT_CONFIRMED" in error.value.reasons
    # A generic rm rc=1 does not prove anything either; ps is still the proof.
    (tmp_path / "ps_names.txt").unlink()
    (tmp_path / "rm_exit.txt").write_text("1", encoding="utf-8")
    evidence = confirm_container_absence(engine, NAME)
    assert evidence["remove_returncode"] == 1
    assert evidence["absence_returncode"] == 0


def test_ps_failure_and_hang_never_become_absence(tmp_path: Path) -> None:
    engine = fake_engine(tmp_path, ps_exit=2)
    with pytest.raises(WatchdogViolation):
        confirm_container_absence(engine, NAME)
    (tmp_path / "ps_exit.txt").write_text("0", encoding="utf-8")
    (tmp_path / "ps_hang").write_text("1", encoding="utf-8")
    with pytest.raises(WatchdogViolation) as error:
        confirm_container_absence(engine, NAME)
    assert any("CONTAINER_QUERY_UNAVAILABLE" in reason
               for reason in error.value.reasons)


def test_orphan_found_by_marker_not_parent_edge() -> None:
    """A controller that dies after spawning a detached child escapes the tree."""
    import uuid
    marker = "G4D_DETACHED_" + uuid.uuid4().hex
    child_code = ("import os, signal, time\n"
                  "os.setsid()\n"
                  "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
                  "time.sleep(30)\n")
    code = ("import os, subprocess, sys\n"
            "child = subprocess.Popen([sys.executable, '-c', "
            + repr(child_code) + "],\n"
            "    env={**os.environ, 'G4D_MARKER': " + repr(marker) + "})\n"
            "print(child.pid, flush=True)\n")
    process = subprocess.Popen([sys.executable, "-c", code],
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               start_new_session=True)
    assert process.stdout is not None
    child_pid = int(process.stdout.readline().strip())
    process.wait(timeout=10)
    time.sleep(0.3)
    # The root is gone, so a parent-edge walk finds nothing; the run-specific
    # marker still identifies the escaped process that must be killed.
    found = scan_marked_processes([marker])
    assert any(row["pid"] == child_pid for row in found), found
    for row in found:
        try:
            os.kill(row["pid"], signal.SIGKILL)
        except ProcessLookupError:
            pass
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and scan_marked_processes([marker]):
        time.sleep(0.05)
    assert scan_marked_processes([marker]) == []
    assert confirm_process_absence([child_pid]).confirmed


def test_path_absence_reobserves_socket(tmp_path: Path) -> None:
    socket_path = tmp_path / "bridge.sock"
    socket_path.write_text("placeholder", encoding="utf-8")
    report = confirm_path_absence([socket_path])
    assert not report.confirmed and str(socket_path) in report.present
    socket_path.unlink()
    assert confirm_path_absence([socket_path]).confirmed


def test_cleanup_exception_and_timeout_are_fail_closed() -> None:
    process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"],
                               stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, start_new_session=True)
    watchdog = ExternalWatchdog(WatchdogPolicy(total_seconds=0.3,
                                               termination_grace_seconds=0.2))
    with pytest.raises(WatchdogViolation):
        watchdog.supervise(process, cleanup=lambda: (_ for _ in ()).throw(
            TimeoutError("cleanup hung")))
    assert process.poll() is not None


def test_pending_conservative_never_retries() -> None:
    process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"],
                               stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, start_new_session=True)
    outcome = ExternalWatchdog(WatchdogPolicy(total_seconds=0.2,
                                              termination_grace_seconds=0.2)
                               ).supervise(process)
    assert outcome.pending is not None
    assert outcome.pending.retry_allowed is False
    assert outcome.pending.worst_case_reserved is True
    assert outcome.kill_result is not None and outcome.kill_result.confirmed_absent
