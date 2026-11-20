"""OS confinement tests for the B-PR1 bwrap sandbox (M1-B).

These tests exercise the real :class:`~m1_teacher.assessment.judge.sandbox.BwrapSandbox`
on the host.  They never touch the network: the only "network" probe is the
loopback-only interface assertion, and the host sentinel used here is a
temporary synthetic file under the host temp dir (never committed).

Evidence class: MOCK / LOCAL (the OS sandbox is real, but all payloads are
synthetic).  Dynamic tests skip with a clear reason on hosts where bwrap or
user namespaces are unavailable; the fail-closed tests still run everywhere.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

import pytest

from m1_teacher.assessment.judge.protocol import JUDGE_SANDBOX_UNAVAILABLE
from m1_teacher.assessment.judge.sandbox import (
    BWRAP_BINARY,
    BwrapSandbox,
    SandboxLaunchError,
    SandboxResult,
    SandboxUnavailable,
    WORKER_PYTHON,
)


def _write_work_script(work_dir: Path, name: str, source: str) -> Path:
    script = work_dir / name
    script.write_text(source, encoding="utf-8")
    script.chmod(0o444)
    return script


def _make_sandbox(**kwargs) -> BwrapSandbox:
    sandbox = BwrapSandbox(**kwargs)
    if not sandbox.available():
        pytest.skip(f"bwrap sandbox unavailable on this host: {sandbox.probe_failure_reason()}")
    return sandbox


def _run_script(sandbox: BwrapSandbox, source: str, *, timeout_s: float = 10.0, **kwargs) -> dict:
    work_dir = Path(tempfile.mkdtemp(prefix="m1b_sandbox_test_"))
    try:
        script = _write_work_script(work_dir, "check.py", source)
        result = sandbox.run(
            work_dir,
            [WORKER_PYTHON, f"/worker/{script.name}"],
            timeout_s,
            **kwargs,
        )
        assert not result.timed_out, "sandbox script unexpectedly timed out"
        assert result.exit_code == 0, "sandbox script exited non-zero"
        return json.loads(result.stdout.decode("utf-8"))
    finally:
        for child in work_dir.iterdir():
            try:
                child.chmod(0o600)
            except OSError:
                pass
        shutil.rmtree(work_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Static command construction
# ---------------------------------------------------------------------------


def test_frozen_bwrap_command_contains_all_confinement_flags():
    work_dir = Path(tempfile.mkdtemp(prefix="m1b_sandbox_cmd_"))
    try:
        sandbox = BwrapSandbox()
        command = sandbox.command(work_dir, [WORKER_PYTHON, "/worker/worker_runner.py"])
    finally:
        work_dir.rmdir()
    assert command[0] == BWRAP_BINARY
    for flag in (
        "--unshare-all",
        "--die-with-parent",
        "--new-session",
        "--clearenv",
        "--cap-drop",
        "ALL",
        "--proc",
        "--dev",
        "--tmpfs",
        "--uid",
        "65534",
        "--gid",
        "65534",
        "--hostname",
        "m1b-worker",
    ):
        assert flag in command, f"missing frozen bwrap flag {flag!r}"
    joined = " ".join(command)
    assert "--share-net" not in command
    assert "--dev-bind" not in command
    assert "--as-pid-1" not in command
    # Only the per-case work dir and the minimal read-only system paths are
    # bind-mounted from the host; no fixture/DB/home/root paths may appear.
    bind_targets = {
        command[index + 2]
        for index, token in enumerate(command)
        if token in {"--ro-bind", "--bind", "--dev-bind"} and index + 2 < len(command)
    }
    assert bind_targets == {"/usr", "/lib", "/lib64", "/bin", "/worker"}, bind_targets
    assert "/root" not in joined and "/home" not in joined
    # bwrap 0.9 requires --size to precede the --tmpfs it configures.
    assert command.index("--size") < command.index("--tmpfs")
    # The worker dir is the resolved absolute path of the private work dir.
    assert str(work_dir.resolve()) in command
    assert command[-2:] == [WORKER_PYTHON, "/worker/worker_runner.py"]


# ---------------------------------------------------------------------------
# Fail-closed paths (run even without bwrap)
# ---------------------------------------------------------------------------


def test_missing_bwrap_is_unavailable_and_never_falls_back():
    sandbox = BwrapSandbox(bwrap_path="/nonexistent/m1b-bwrap-does-not-exist")
    assert sandbox.available() is False
    assert sandbox.probe_failure_reason()
    work_dir = Path(tempfile.mkdtemp(prefix="m1b_sandbox_missing_"))
    try:
        with pytest.raises(SandboxUnavailable) as captured:
            sandbox.run(work_dir, [WORKER_PYTHON, "/worker/worker_runner.py"], 1.0)
        assert getattr(captured.value, "code", None) == JUDGE_SANDBOX_UNAVAILABLE
    finally:
        work_dir.rmdir()


def test_failed_canary_probe_is_unavailable_and_never_falls_back(monkeypatch):
    sandbox = BwrapSandbox()
    monkeypatch.setattr(
        sandbox,
        "_run_probe",
        lambda: (_ for _ in ()).throw(SandboxUnavailable("synthetic canary failure")),
    )
    assert sandbox.available() is False
    assert sandbox.probe_failure_reason() == "synthetic canary failure"
    work_dir = Path(tempfile.mkdtemp(prefix="m1b_sandbox_probe_fail_"))
    try:
        with pytest.raises(SandboxUnavailable):
            sandbox.run(work_dir, [WORKER_PYTHON, "/worker/worker_runner.py"], 1.0)
    finally:
        work_dir.rmdir()


def test_probe_is_cached_between_available_checks(monkeypatch):
    sandbox = BwrapSandbox()
    if not sandbox.available():
        pytest.skip(f"bwrap sandbox unavailable: {sandbox.probe_failure_reason()}")
    calls = {"count": 0}
    original = sandbox._run_probe

    def counting_probe() -> None:
        calls["count"] += 1
        original()

    monkeypatch.setattr(sandbox, "_run_probe", counting_probe)
    assert sandbox.available() is True
    assert sandbox.available() is True
    assert calls["count"] == 0, "cached availability must not re-probe"
    sandbox.refresh_availability()
    assert calls["count"] == 1


# ---------------------------------------------------------------------------
# Real confinement canaries
# ---------------------------------------------------------------------------


# Keep the canary ASCII-only and self-contained: define the helper before use.
CANARY_SOURCE = r"""
import json
import os
import socket


def _write(path):
    try:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("x")
        return True
    except OSError:
        return False


payload = {
    "uid": os.getuid(),
    "gid": os.getgid(),
    "pid": os.getpid(),
    "hostname": socket.gethostname(),
    "root_visible": os.path.exists("/root"),
    "etc_visible": os.path.exists("/etc/passwd"),
    "host_sentinel_visible": os.path.exists(os.environ.get("M1B_TEST_HOST_SENTINEL", "/none")),
    "interfaces": sorted(name for _index, name in socket.if_nameindex()),
    "usr_write": "allowed" if _write("/usr/m1b_test_probe") else "denied",
    "worker_write": "allowed" if _write("/worker/m1b_test_probe") else "denied",
    "tmp_write": "allowed" if _write("/tmp/m1b_test_probe") else "denied",
}
print(json.dumps(payload, sort_keys=True))
"""


def test_real_sandbox_confines_identity_filesystem_and_network():
    sandbox = _make_sandbox()
    host_dir = Path(tempfile.mkdtemp(prefix="m1b_sandbox_host_"))
    sentinel = host_dir / "host_sentinel.txt"
    sentinel.write_text("SENTINEL_SANDBOX_TEST_DO_NOT_LEAK\n", encoding="utf-8")
    try:
        payload = _run_script(
            sandbox,
            CANARY_SOURCE,
            extra_env={"M1B_TEST_HOST_SENTINEL": str(sentinel)},
        )
    finally:
        sentinel.unlink(missing_ok=True)
        host_dir.rmdir()
    assert payload["uid"] == 65534
    assert payload["gid"] == 65534
    assert payload["hostname"] == "m1b-worker"
    assert payload["pid"] >= 2
    assert payload["root_visible"] is False
    assert payload["etc_visible"] is False
    assert payload["host_sentinel_visible"] is False
    assert payload["interfaces"] == ["lo"]
    assert payload["usr_write"] == "denied"
    assert payload["worker_write"] == "denied"
    assert payload["tmp_write"] == "allowed"


def test_real_sandbox_has_loopback_only_network():
    sandbox = _make_sandbox()
    payload = _run_script(
        sandbox,
        r"""
import json
import socket

print(json.dumps({
    "interfaces": sorted(name for _index, name in socket.if_nameindex()),
    "proc_net_dev": [
        line.split(":")[0].strip()
        for line in open("/proc/net/dev", encoding="utf-8").read().splitlines()[2:]
        if ":" in line
    ],
}, sort_keys=True))
""",
    )
    assert payload["interfaces"] == ["lo"]
    assert payload["proc_net_dev"] == ["lo"]


def test_real_sandbox_timeout_kills_process_group_without_leftovers():
    sandbox = _make_sandbox()
    work_dir = Path(tempfile.mkdtemp(prefix="m1b_sandbox_tle_"))
    try:
        _write_work_script(
            work_dir,
            "hang.py",
            "import time\nwhile True:\n    time.sleep(30)\n",
        )
        result = sandbox.run(
            work_dir,
            [WORKER_PYTHON, "/worker/hang.py"],
            0.3,
        )
    finally:
        for child in work_dir.iterdir():
            try:
                child.chmod(0o600)
            except OSError:
                pass
        shutil.rmtree(work_dir, ignore_errors=True)
    assert result.timed_out is True
    assert result.elapsed_s < 5.0
    assert result.exit_code is not None and result.exit_code < 0
    # No bwrap/worker process may survive the kill: scan the host /proc for the
    # unique work-dir path recorded in the bwrap command line.
    marker = work_dir.name
    leftovers = []
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            cmdline = Path(f"/proc/{entry}/cmdline").read_bytes().decode("utf-8", "replace")
        except OSError:
            continue
        if marker in cmdline:
            leftovers.append(entry)
    assert leftovers == []


def test_real_sandbox_enforces_resource_limits():
    sandbox = _make_sandbox()
    memory_payload = _run_script(
        sandbox,
        r"""
import json
try:
    bytearray(400 * 1024 * 1024)
    print(json.dumps({"outcome": "allocated"}))
except MemoryError:
    print(json.dumps({"outcome": "MemoryError"}))
""",
    )
    assert memory_payload["outcome"] == "MemoryError"

    fsize_payload = _run_script(
        sandbox,
        r"""
import json
try:
    with open("/tmp/m1b_big.bin", "wb") as handle:
        handle.write(b"x" * (5 * 1024 * 1024))
    print(json.dumps({"outcome": "written"}))
except OSError:
    print(json.dumps({"outcome": "OSError"}))
""",
    )
    assert fsize_payload["outcome"] == "OSError"

    nofile_payload = _run_script(
        sandbox,
        r"""
import json
handles = []
try:
    for index in range(200):
        handles.append(open("/tmp/m1b_fd_%d" % index, "w"))
    print(json.dumps({"outcome": "opened"}))
except OSError:
    print(json.dumps({"outcome": "OSError"}))
finally:
    for handle in handles:
        try:
            handle.close()
        except OSError:
            pass
""",
    )
    assert nofile_payload["outcome"] == "OSError"


def test_real_sandbox_bounds_stdout_and_continues_draining():
    sandbox = BwrapSandbox(max_stdout_bytes=1024, max_stderr_bytes=1024)
    if not sandbox.available():
        pytest.skip(f"bwrap sandbox unavailable: {sandbox.probe_failure_reason()}")
    work_dir = Path(tempfile.mkdtemp(prefix="m1b_sandbox_output_"))
    try:
        _write_work_script(
            work_dir,
            "flood.py",
            "import sys\nsys.stdout.write('x' * 200000)\nsys.stdout.flush()\n",
        )
        result = sandbox.run(work_dir, [WORKER_PYTHON, "/worker/flood.py"], 10.0)
    finally:
        for child in work_dir.iterdir():
            try:
                child.chmod(0o600)
            except OSError:
                pass
        shutil.rmtree(work_dir, ignore_errors=True)
    assert result.timed_out is False
    assert result.exit_code == 0
    assert len(result.stdout) <= 1024
    assert result.stdout_truncated is True


def test_real_sandbox_rejects_invalid_work_dir():
    sandbox = _make_sandbox()
    with pytest.raises(SandboxLaunchError):
        sandbox.run(Path("/nonexistent/m1b-work-dir"), [WORKER_PYTHON, "/worker/x.py"], 1.0)


def test_sandbox_result_shape_is_plain_data():
    result = SandboxResult(
        exit_code=0,
        stdout=b"",
        stderr=b"",
        timed_out=False,
        elapsed_s=0.01,
        stdout_truncated=False,
        stderr_truncated=False,
    )
    assert result.exit_code == 0
    assert result.timed_out is False
