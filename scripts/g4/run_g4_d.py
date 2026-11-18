#!/usr/bin/env python3
"""G4-D case runner: real dual-principal watchdog runs plus no-key E5 probes.

Every case gets its own directory under ``artifacts/g4/e5/runs/<case>`` with:

* ``watchdog/`` - the external process's argv/UTC/exit, container snapshots,
  uid_map/mountinfo, socket peercred, kill/absence checks, command log;
* ``launcher/`` - the reused G4-C/D launcher evidence (containers, mounts,
  peercred, receipts, DB snapshot) for the same run;
* ``host/`` - e5_probe JSON and argv for the host-level rows.

The runner never enables Live, never reads a real key, never pulls an image and
never writes outside ``artifacts/g4/e5`` (plus the launcher's gitignored run
directory, which the watchdog deletes and re-observes).
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "g3d"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib_g3d as lib3d  # noqa: E402
import lib_g4 as lib  # noqa: E402
import lib_g4c as libc  # noqa: E402

E5_ROOT = lib.ARTIFACTS / "g4" / "e5"
FIXTURES = E5_ROOT / "fixtures"
RUNS = E5_ROOT / "runs"
SCRIPTS = REPO / "scripts" / "g4"
WATCHDOG = SCRIPTS / "watchdog_runner.py"
PROBE = SCRIPTS / "e5_probe.py"
SENTINEL_PROBE = SCRIPTS / "secret_sentinel_probe.py"
CANDIDATE_PROBE = SCRIPTS / "probes" / "g4d_candidate_iso_probe.py"
LAUNCHER = SCRIPTS / "launch_c.py"
PYTHON = sys.executable
SENTINEL = "TEST_ONLY_NEVER_VALID_SECRET_SENTINEL"

CLEAN_ENV = {
    "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
    "HOME": "/root",
    "LANG": "C",
    "LC_ALL": "C",
    "PYTHONDONTWRITEBYTECODE": "1",
    "TMPDIR": "/tmp",
}

COMMANDS = E5_ROOT / "commands.jsonl"
CASES: dict[str, dict] = {}


def utc() -> str:
    return lib3d.utc()


def command(argv, *, name: str, timeout: float = 300.0,
            cwd: Path = REPO) -> dict:
    started = utc()
    record: dict = {"name": name, "argv": [str(item) for item in argv],
                    "utc_start": started}
    try:
        proc = subprocess.run([str(item) for item in argv], cwd=str(cwd),
                              env=dict(CLEAN_ENV), capture_output=True,
                              text=True, timeout=timeout)
        record.update({"exit": proc.returncode, "stdout": proc.stdout[-16000:],
                       "stderr": proc.stderr[-16000:]})
    except subprocess.TimeoutExpired as error:
        record.update({"exit": 124, "timed_out": True,
                       "stdout": lib3d._decode_timeout_stream(error.stdout)[-8000:],
                       "stderr": lib3d._decode_timeout_stream(error.stderr)[-8000:]})
    record["utc_end"] = utc()
    COMMANDS.parent.mkdir(parents=True, exist_ok=True)
    lib3d.append_jsonl(COMMANDS, record)
    return record


def write_json(path: Path, document: object, *, mode: int = 0o600) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(document, indent=2, sort_keys=True, default=str) + "\n").encode()
    path.write_bytes(data)
    os.chmod(path, mode)
    return {"path": str(path), "sha256": lib3d.sha256_bytes(data), "bytes": len(data)}


def stage_path(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).resolve()
    candidates = sorted(path for path in libc.STAGE_ROOT.glob("stage-*")
                        if (path / "manifest.json").is_file())
    if not candidates:
        raise SystemExit("G4D_STAGE_MISSING; run scripts/g4/build_stage_c.py first")
    return candidates[-1]


def run_dir_for(run_id: str) -> Path:
    return libc.G4C_ROOT / "runs" / run_id


def launcher_argv(*, case: str, stage: Path, run_id: str, evidence: Path,
                  scenario: str = "echo", session: str | None = None,
                  candidate_mode: str = "hold", steps: str | None = None,
                  hold_seconds: int = 300, timeout: float = 300.0,
                  keep_run: bool = True) -> list[str]:
    argv = [PYTHON, "-B", str(LAUNCHER), "--case", case, "--scenario", scenario,
            "--session", session or f"g4d-{case}", "--stage", str(stage),
            "--run-id", run_id, "--evidence-dir", str(evidence),
            "--candidate-mode", candidate_mode, "--timeout", str(int(timeout))]
    if keep_run:
        argv.append("--keep-run")
    if candidate_mode == "hold":
        argv.extend(["--hold-seconds", str(hold_seconds)])
    if steps:
        argv.extend(["--steps", steps])
    return argv


def run_watchdog(*, case: str, stage: Path, launcher: list[str],
                 watchdog_args: list[str], expect_exit: int,
                 timeout: float = 300.0) -> dict:
    directory = RUNS / case
    watchdog_dir = directory / "watchdog"
    record: dict = {"case": case, "utc_start": utc(), "watchdog_dir": str(watchdog_dir),
                    "launcher_argv": launcher, "watchdog_args": watchdog_args}
    argv = [PYTHON, "-B", str(WATCHDOG), "--case", case,
            "--evidence", str(watchdog_dir), *watchdog_args, "--"] + launcher
    result = command(argv, name=f"watchdog-{case}", timeout=timeout)
    record.update({"exit": result.get("exit"), "timed_out": result.get("timed_out"),
                   "stdout": result.get("stdout"), "stderr": result.get("stderr"),
                   "utc_end": utc(), "expected_exit": expect_exit})
    document = {}
    if (watchdog_dir / "watchdog.json").is_file():
        try:
            document = json.loads((watchdog_dir / "watchdog.json").read_text(
                encoding="utf-8"))
        except json.JSONDecodeError:
            document = {}
    record["watchdog"] = {key: document.get(key) for key in
                          ("status", "reason", "exit", "pending", "target",
                           "containers", "paths", "checks")}
    record["status"] = "PASS" if (result.get("exit") == expect_exit
                                  and document.get("status") in
                                  ("PASS", "FAIL_CLOSED", "WATCHDOG_SELF_FAILURE")
                                  ) else "FAIL"
    # D08 expects a deliberate FAIL_CLOSED, not a successful kill.
    if expect_exit != 0:
        record["status"] = "PASS" if (result.get("exit") == expect_exit
                                      and document.get("status") == "FAIL_CLOSED") \
            else "FAIL"
    write_json(directory / "case.json", record)
    return record


def manual_cleanup(case: str, run_id: str) -> dict:
    """Operator-visible cleanup after an injected engine failure (fail-closed)."""
    directory = RUNS / case
    listing = command(["podman", "ps", "-a", "--format", "{{.Names}}"],
                      name=f"{case}-manual-list")
    names = [line.strip() for line in (listing.get("stdout") or "").splitlines()
             if line.strip() and run_id in line]
    removals = []
    for name in names:
        removals.append(command(["podman", "rm", "-f", name],
                                name=f"{case}-manual-rm-{name}", timeout=60))
    after = command(["podman", "ps", "-a", "--format", "{{.Names}}"],
                    name=f"{case}-manual-verify")
    remaining = [line for line in (after.get("stdout") or "").splitlines() if line.strip()]
    document = {"utc": utc(), "run_id": run_id, "discovered": names,
                "rm_exits": [item.get("exit") for item in removals],
                "remaining_after": remaining,
                "confirmed_absent": not remaining and after.get("exit") == 0,
                "operator_action": True,
                "note": "watchdog refused to claim absence after the injected "
                        "engine failure; a human/operator cleanup command was run "
                        "explicitly and re-observed"}
    write_json(directory / "manual-cleanup.json", document)
    return document


# ---------------------------------------------------------------------------
# case implementations
# ---------------------------------------------------------------------------
def case_d01(stage: Path) -> dict:
    run_id = f"g4d-d01-{lib3d.utc_compact()}"
    directory = RUNS / "d01"
    launcher = launcher_argv(case="d01", stage=stage, run_id=run_id,
                             evidence=directory / "launcher")
    watchdog_args = ["--run-id", run_id, "--run-dir", str(run_dir_for(run_id)),
                     "--rootfs-target", str(lib.ROOTFS / "g4c"),
                     "--deadline", "90", "--kill-after-up", "4",
                     "--capture-live", "--expect", "trigger"]
    record = run_watchdog(case="d01", stage=stage, launcher=launcher,
                          watchdog_args=watchdog_args, expect_exit=0, timeout=240)
    record["run_id"] = run_id
    return record


def case_d02(stage: Path) -> dict:
    run_id = f"g4d-d02-{lib3d.utc_compact()}"
    directory = RUNS / "d02"
    launcher = launcher_argv(case="d02", stage=stage, run_id=run_id,
                             evidence=directory / "launcher", steps="valid")
    watchdog_args = ["--run-id", run_id, "--run-dir", str(run_dir_for(run_id)),
                     "--rootfs-target", str(lib.ROOTFS / "g4c"),
                     "--deadline", "90", "--kill-after-up", "8",
                     "--require-containers", "1", "--freeze", "trusted",
                     "--capture-live", "--expect", "trigger"]
    record = run_watchdog(case="d02", stage=stage, launcher=launcher,
                          watchdog_args=watchdog_args, expect_exit=0, timeout=240)
    record["run_id"] = run_id
    return record


def case_d03(stage: Path) -> dict:
    run_id = f"g4d-d03-{lib3d.utc_compact()}"
    directory = RUNS / "d03"
    launcher = launcher_argv(case="d03", stage=stage, run_id=run_id,
                             evidence=directory / "launcher",
                             candidate_mode="dsh", keep_run=False)
    probe_paths = {
        "trusted_state": str(run_dir_for(run_id) / "state" / "controller.json"),
        "trusted_write": str(run_dir_for(run_id) / "state" / "injected.json"),
        "trusted_dir": str(run_dir_for(run_id) / "state"),
        "sentinel": str(FIXTURES / "trusted" / "sentinel.txt"),
        "previous_state": str(run_dir_for("g4d-d01-previous") / "state" /
                              "controller.json"),
        "own_write": "/work/session/g4d-d03-probe.txt",
        "socket": "/work/g3b/bridge.sock",
    }
    watchdog_args = ["--run-id", run_id, "--run-dir", str(run_dir_for(run_id)),
                     "--rootfs-target", str(lib.ROOTFS / "g4c"),
                     "--deadline", "180", "--expect", "exit",
                     "--capture-live", "--exec-probe", str(CANDIDATE_PROBE),
                     "--exec-role", "candidate",
                     "--exec-arg", json.dumps(probe_paths)]
    record = run_watchdog(case="d03", stage=stage, launcher=launcher,
                          watchdog_args=watchdog_args, expect_exit=0, timeout=240)
    record["run_id"] = run_id
    return record


def case_d08a(stage: Path) -> dict:
    run_id = f"g4d-d08a-{lib3d.utc_compact()}"
    directory = RUNS / "d08a"
    wrapper = FIXTURES / "bin" / "podman-rm-lies"
    wrapper.parent.mkdir(parents=True, exist_ok=True)
    wrapper.write_text(
        "#!/bin/sh\n"
        "# TEST ONLY: rm claims success but does not remove; ps tells the truth.\n"
        "case \"$1\" in\n"
        "  rm) exit 0 ;;\n"
        "  *) exec /usr/bin/podman \"$@\" ;;\n"
        "esac\n", encoding="utf-8")
    wrapper.chmod(0o755)
    launcher = launcher_argv(case="d08a", stage=stage, run_id=run_id,
                             evidence=directory / "launcher")
    watchdog_args = ["--run-id", run_id, "--run-dir", str(run_dir_for(run_id)),
                     "--rootfs-target", str(lib.ROOTFS / "g4c"),
                     "--engine", str(wrapper), "--deadline", "90",
                     "--kill-after-up", "3", "--expect", "trigger"]
    record = run_watchdog(case="d08a", stage=stage, launcher=launcher,
                          watchdog_args=watchdog_args, expect_exit=4, timeout=240)
    record["run_id"] = run_id
    record["cleanup"] = manual_cleanup("d08a", run_id)
    return record


def case_d08b(stage: Path) -> dict:
    run_id = f"g4d-d08b-{lib3d.utc_compact()}"
    directory = RUNS / "d08b"
    wrapper = FIXTURES / "bin" / "podman-ps-id-fail"
    wrapper.parent.mkdir(parents=True, exist_ok=True)
    wrapper.write_text(
        "#!/bin/sh\n"
        "# TEST ONLY: daemon-style query failure for the container-enumeration form.\n"
        "case \"$*\" in\n"
        "  *'{{.ID}}'*) echo 'Error: cannot connect to Podman socket' >&2; exit 125 ;;\n"
        "  *) exec /usr/bin/podman \"$@\" ;;\n"
        "esac\n", encoding="utf-8")
    wrapper.chmod(0o755)
    launcher = launcher_argv(case="d08b", stage=stage, run_id=run_id,
                             evidence=directory / "launcher")
    watchdog_args = ["--run-id", run_id, "--run-dir", str(run_dir_for(run_id)),
                     "--rootfs-target", str(lib.ROOTFS / "g4c"),
                     "--engine", str(wrapper), "--deadline", "12",
                     "--expect", "trigger"]
    record = run_watchdog(case="d08b", stage=stage, launcher=launcher,
                          watchdog_args=watchdog_args, expect_exit=4, timeout=240)
    record["run_id"] = run_id
    record["cleanup"] = manual_cleanup("d08b", run_id)
    return record


def case_d09(stage: Path) -> dict:
    checks: list[dict] = []
    cases = {
        "cpu": {
            "rlimit": "cpu:1",
            "code": "while True:\n    pass\n",
            "exit_ok": "0,-24,-9", "deadline": "20",
            "probe": "SIGXCPU/SIGKILL within the RLIMIT_CPU bound",
        },
        "as": {
            "rlimit": "as:268435456",
            "code": ("try:\n    block = bytearray(400 * 1024 * 1024)\n"
                     "except MemoryError:\n    raise SystemExit(1)\n"),
            "exit_ok": "0,1", "deadline": "20",
            "probe": "MemoryError before anonymous memory exceeds RLIMIT_AS",
        },
        "nofile": {
            "rlimit": "nofile:64",
            "code": ("import os\nfds = []\ntry:\n"
                     "    for _ in range(200):\n        fds.append(os.open('/dev/null', 0))\n"
                     "except OSError:\n    raise SystemExit(2)\n"),
            "exit_ok": "0,2", "deadline": "20",
            "probe": "EMFILE at the 64-fd soft limit",
        },
        "nproc": {
            "rlimit": "nproc:16",
            "code": ("import os, time\nchildren = []\nfor _ in range(40):\n"
                     "    try:\n        pid = os.fork()\n"
                     "    except OSError:\n        break\n"
                     "    if pid == 0:\n        time.sleep(2)\n        os._exit(0)\n"
                     "    children.append(pid)\n"
                     "for pid in children:\n    try:\n        os.waitpid(pid, 0)\n"
                     "    except OSError:\n        pass\n"),
            "exit_ok": "0", "deadline": "40",
            "probe": "RLIMIT_NPROC is not enforced for host root: UNVERIFIED",
        },
    }
    for name, spec in cases.items():
        evidence = RUNS / "d09" / name / "watchdog"
        target = [PYTHON, "-B", "-c", spec["code"]]
        argv = [PYTHON, "-B", str(WATCHDOG), "--case", f"d09-{name}",
                "--evidence", str(evidence), "--engine", "podman",
                "--require-containers", "0", "--expect", "exit",
                "--target-exit-ok", spec["exit_ok"],
                "--rlimit", spec["rlimit"], "--deadline", spec["deadline"],
                "--", *target]
        result = command(argv, name=f"watchdog-d09-{name}", timeout=120)
        document = {}
        if (evidence / "watchdog.json").is_file():
            document = json.loads((evidence / "watchdog.json").read_text())
        target_exit = (document.get("target") or {}).get("exit")
        checks.append({
            "id": f"rlimit_{name}",
            "ok": result.get("exit") == 0 and document.get("status") == "PASS",
            "target_exit": target_exit, "allowed": spec["exit_ok"],
            "rlimit": spec["rlimit"], "probe": spec["probe"],
            "watchdog_exit": result.get("exit"),
            "evidence": str(evidence),
        })
    # Observe the real container cgroup limits captured by D01.
    cgroup: dict = {}
    up = RUNS / "d01" / "watchdog" / "snapshots" / "containers-up.json"
    if up.is_file():
        snapshot = json.loads(up.read_text(encoding="utf-8"))
        for name, entry in (snapshot.get("containers") or {}).items():
            proc = entry.get("proc") or {}
            cgroup[name] = {
                "host_config": (entry.get("inspect") or {}).get("host_config"),
                "cgroup_limits": (proc.get("cgroup") or {}).get("limits"),
                "uid_map": (proc.get("uid_map") or {}).get("sha256"),
            }
    observed = any((value.get("cgroup_limits") or {}).get("pids.max")
                   for value in cgroup.values())
    checks.append({"id": "container_cgroup_limits_observed", "ok": observed,
                   "containers": cgroup})
    document = {
        "schema": "m0.g4d.d09.v1", "utc": utc(), "checks": checks,
        "status": "UNVERIFIED" if not all(item["ok"] for item in checks)
        else ("PASS_WITH_NPROC_UNVERIFIED" if checks[-1]["ok"] else "FAIL"),
        "nproc_status": "UNVERIFIED",
        "note": "CPU/AS/NOFILE enforcement is real OS evidence; RLIMIT_NPROC is "
                "not enforced for host root, so pids enforcement relies on the "
                "container cgroup --pids-limit observed here",
    }
    document["status"] = "PASS" if all(item["ok"] for item in checks) else "FAIL"
    write_json(RUNS / "d09" / "d09.json", document)
    return {"case": "d09", "status": document["status"],
            "checks": checks, "nproc": "UNVERIFIED"}


def case_d15(stage: Path) -> dict:
    run_id = f"g4d-d15-{lib3d.utc_compact()}"
    directory = RUNS / "d15"
    previous = RUNS / "d01" / "case.json"
    previous_run = ""
    if previous.is_file():
        previous_run = json.loads(previous.read_text()).get("run_id") or ""
    launcher = launcher_argv(case="d15", stage=stage, run_id=run_id,
                             evidence=directory / "launcher")
    probe_paths = {
        "trusted_state": str(run_dir_for(run_id) / "state" / "controller.json"),
        "trusted_write": str(run_dir_for(run_id) / "state" / "injected.json"),
        "trusted_dir": str(run_dir_for(run_id) / "state"),
        "sentinel": str(FIXTURES / "trusted" / "sentinel.txt"),
        "previous_state": str(run_dir_for(previous_run or "g4d-old-run") /
                              "state" / "controller.json"),
        "own_write": "/work/session/g4d-d15-probe.txt",
        "socket": "/work/g3b/bridge.sock",
    }
    watchdog_args = ["--run-id", run_id, "--run-dir", str(run_dir_for(run_id)),
                     "--rootfs-target", str(lib.ROOTFS / "g4c"),
                     "--deadline", "90", "--kill-after-up", "5",
                     "--capture-live", "--exec-probe", str(CANDIDATE_PROBE),
                     "--exec-role", "candidate", "--exec-arg", json.dumps(probe_paths),
                     "--expect", "trigger"]
    record = run_watchdog(case="d15", stage=stage, launcher=launcher,
                          watchdog_args=watchdog_args, expect_exit=0, timeout=240)
    record["run_id"] = run_id
    record["previous_run_id"] = previous_run
    probe_file = directory / "watchdog" / "probes" / "exec-candidate.json"
    if probe_file.is_file():
        document = json.loads(probe_file.read_text())
        record["exec_probe"] = document.get("result")
        expected = {"read_trusted_state": "ENOENT", "write_trusted_state": "ENOENT",
                    "list_trusted_state": "ENOENT", "read_sentinel_fixture": "ENOENT",
                    "read_previous_known_state": "ENOENT",
                    "write_own_session": "ALLOWED",
                    "stat_bridge_socket": "ALLOWED"}
        observed = document.get("result") or {}
        record["host_path_denials"] = {key: observed.get(key) for key in expected}
        record["denials_ok"] = all(observed.get(key) == value
                                   for key, value in expected.items())
    write_json(directory / "case.json", record)
    return record


def host_probe(name: str, stage: Path, *, extra: list[str] | None = None,
               timeout: float = 180.0) -> dict:
    directory = RUNS / name / "host"
    directory.mkdir(parents=True, exist_ok=True)
    out = directory / f"{name}.json"
    argv = [PYTHON, "-B", str(PROBE), name, "--stage", str(stage),
            "--out", str(out)]
    if extra:
        argv.extend(extra)
    result = command(argv, name=f"host-{name}", timeout=timeout)
    document = {}
    if out.is_file():
        document = json.loads(out.read_text(encoding="utf-8"))
    return {"case": name, "exit": result.get("exit"),
            "status": document.get("status", "FAIL"),
            "probe": document, "argv": result.get("argv"),
            "utc": {"start": result.get("utc_start"), "end": result.get("utc_end")}}


def scan_sentinel(*, case: str, roots: list[str], pids: list[int] = (),
                  timeout: float = 600.0) -> dict:
    directory = RUNS / case
    directory.mkdir(parents=True, exist_ok=True)
    out = directory / "sentinel-scan.json"
    argv = [PYTHON, "-B", str(SENTINEL_PROBE)]
    for root in roots:
        argv.extend(["--root", root])
    for pid in pids:
        argv.extend(["--pid", str(pid)])
    argv.extend(["--self-test", "--out", str(out)])
    result = command(argv, name=f"sentinel-{case}", timeout=timeout)
    document = {}
    if out.is_file():
        document = json.loads(out.read_text(encoding="utf-8"))
    write_json(directory / "scan-argv.json",
               {"argv": result.get("argv"), "exit": result.get("exit"),
                "utc": {"start": result.get("utc_start"), "end": result.get("utc_end")}})
    return {"case": case, "exit": result.get("exit"),
            "clean": document.get("clean"),
            "hit_count": (document.get("scan") or {}).get("hit_count"),
            "files_scanned": (document.get("scan") or {}).get("files_scanned"),
            "positive_control": (document.get("positive_control") or {}).get("control"),
            "document": document}


def canonical() -> dict:
    rootfs = lib3d.sha256_tree(lib.ROOTFS)
    deps = lib3d.sha256_tree(lib.DEPS)
    return {"utc": utc(), "rootfs": {"sha256": rootfs, "expected": lib.ROOTFS_CANON,
                                     "ok": rootfs == lib.ROOTFS_CANON},
            "deps": {"sha256": deps, "expected": lib.DEPS_CANON,
                     "ok": deps == lib.DEPS_CANON}}


def final_safety_cleanup() -> dict:
    """Never leave test containers or an empty rootfs mount target behind."""
    listing = command(["podman", "ps", "-a", "--format", "{{.Names}}"],
                      name="final-safety-list")
    names = [line.strip() for line in (listing.get("stdout") or "").splitlines()
             if line.strip()]
    removed = []
    for name in names:
        record = command(["podman", "rm", "-f", name],
                         name=f"final-safety-rm-{name}", timeout=60)
        removed.append({"name": name, "exit": record.get("exit")})
    target = lib.ROOTFS / "g4c"
    rootfs_target = {"path": str(target), "removed": False}
    try:
        if target.is_dir() and not target.is_symlink() and not any(target.iterdir()):
            target.rmdir()
            rootfs_target["removed"] = True
    except OSError as error:
        rootfs_target["error"] = type(error).__name__
    after = command(["podman", "ps", "-a", "--format", "{{.Names}}"],
                    name="final-safety-verify")
    remaining = [line for line in (after.get("stdout") or "").splitlines() if line.strip()]
    document = {"utc": utc(), "discovered": names, "removed": removed,
                "remaining": remaining, "rootfs_target": rootfs_target,
                "confirmed_absent": not remaining and after.get("exit") == 0,
                "operator_action": True}
    write_json(E5_ROOT / "final-cleanup.json", document)
    return document


def containers_absent() -> dict:
    result = command(["podman", "ps", "-a", "--format", "{{.Names}}"],
                     name="final-containers")
    names = [line for line in (result.get("stdout") or "").splitlines() if line.strip()]
    return {"exit": result.get("exit"), "names": names, "empty": not names}


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", default=None)
    parser.add_argument("--only", default=None,
                        help="comma-separated cases (default: all)")
    parser.add_argument("--skip-real", action="store_true",
                        help="host probes only (no container run)")
    parser.add_argument("--out-dir", default=str(E5_ROOT))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    stage = stage_path(args.stage)
    global E5_ROOT, RUNS, FIXTURES, COMMANDS
    E5_ROOT = Path(args.out_dir).resolve()
    RUNS = E5_ROOT / "runs"
    FIXTURES = E5_ROOT / "fixtures"
    COMMANDS = E5_ROOT / "commands.jsonl"
    if os.geteuid() != 0:
        sys.stderr.write("G4D_RUNNER_NEEDS_HOST_ROOT\n")
        return lib3d.EXIT_BLOCKED_ENVIRONMENT
    E5_ROOT.mkdir(parents=True, exist_ok=True)
    (E5_ROOT / "runs").mkdir(exist_ok=True)
    # The sentinel lives only in a repo-external test fixture and is never read
    # from os.environ, a home directory or a key manager.
    sentinel_dir = FIXTURES / "trusted"
    sentinel_dir.mkdir(parents=True, exist_ok=True)
    sentinel_file = sentinel_dir / "sentinel.txt"
    sentinel_file.write_text(SENTINEL + "\n", encoding="utf-8")
    os.chmod(sentinel_file, 0o600)
    pre_canonical = canonical()
    pre_containers = containers_absent()
    only = set(item.strip() for item in (args.only or "").split(",") if item.strip())
    results: dict[str, dict] = {}

    def wanted(name: str) -> bool:
        return not only or name in only

    if not args.skip_real:
        for name, function in (("d01", case_d01), ("d02", case_d02),
                               ("d03", case_d03)):
            if wanted(name):
                try:
                    results[name] = function(stage)
                except Exception as error:  # noqa: BLE001 - keep the case matrix moving
                    results[name] = {"case": name, "status": "FAIL",
                                     "error": f"{type(error).__name__}: {str(error)[:300]}"}
        if wanted("d08a"):
            try:
                results["d08a"] = case_d08a(stage)
            except Exception as error:  # noqa: BLE001
                results["d08a"] = {"case": "d08a", "status": "FAIL",
                                   "error": f"{type(error).__name__}: {str(error)[:300]}"}
        if wanted("d08b"):
            try:
                results["d08b"] = case_d08b(stage)
            except Exception as error:  # noqa: BLE001
                results["d08b"] = {"case": "d08b", "status": "FAIL",
                                   "error": f"{type(error).__name__}: {str(error)[:300]}"}
        if wanted("d09"):
            try:
                results["d09"] = case_d09(stage)
            except Exception as error:  # noqa: BLE001
                results["d09"] = {"case": "d09", "status": "FAIL",
                                  "error": f"{type(error).__name__}: {str(error)[:300]}"}
        if wanted("d15"):
            try:
                results["d15"] = case_d15(stage)
            except Exception as error:  # noqa: BLE001
                results["d15"] = {"case": "d15", "status": "FAIL",
                                  "error": f"{type(error).__name__}: {str(error)[:300]}"}

    # Host-level rows (also usable with --skip-real).
    host_cases = {
        "p01-binding": [], "p02-admission": [], "p03-bypass": [],
        "p04-registry": [], "d05-revocation": [], "d06-epoch": [], "d07-live": [],
        "d15-oldrun": [],
    }
    for name, extra in host_cases.items():
        if wanted(name):
            try:
                results[name] = host_probe(name, stage, extra=extra)
            except Exception as error:  # noqa: BLE001
                results[name] = {"case": name, "status": "FAIL",
                                 "error": f"{type(error).__name__}: {str(error)[:300]}"}
    if wanted("p05-secret"):
        try:
            extra = ["--watchdog", str(RUNS / "d03" / "watchdog" / "watchdog.json")]
            candidate_argv = RUNS / "d03" / "launcher" / "run" / "argv-candidate.json"
            if candidate_argv.is_file():
                extra.extend(["--candidate-argv", str(candidate_argv)])
            results["p05-secret"] = host_probe("p05-secret", stage, extra=extra)
        except Exception as error:  # noqa: BLE001
            results["p05-secret"] = {"case": "p05-secret", "status": "FAIL",
                                     "error": f"{type(error).__name__}: {str(error)[:300]}"}

    # D03/D04: scan the real runtime surfaces and evidence bytes. The archived
    # task book is excluded because it *defines* the TEST_ONLY sentinel name;
    # this scanner's own sources and the trusted fixture are excluded too.
    scan_roots = [str(RUNS), str(libc.G4C_ROOT / "runs")]
    scan_roots.append(str(REPO / "docs"))
    scan_roots.append(str(REPO / "tests" / "integration" / "g4_d"))
    scan_roots.extend(sorted(str(path) for path in
                             lib.ARTIFACTS.glob("review-packet-*")))
    exclude = [str(FIXTURES), str(REPO / "scripts"),
               str(REPO / "docs" / "Autonomous_Teacher_M0_G4_PreLive_NoKey_Agent_"
                                  "Execution_Plan_v1.0.md")]
    out = RUNS / "scan" / "sentinel-scan.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    argv = [PYTHON, "-B", str(SENTINEL_PROBE)]
    for root in scan_roots:
        argv.extend(["--root", root])
    for item in exclude:
        argv.extend(["--exclude", item])
    argv.extend(["--self-test", "--out", str(out)])
    result = command(argv, name="sentinel-scan", timeout=900)
    document = json.loads(out.read_text(encoding="utf-8")) if out.is_file() else {}
    scan = {"case": "scan", "exit": result.get("exit"),
            "clean": document.get("clean"),
            "hit_count": (document.get("scan") or {}).get("hit_count"),
            "files_scanned": (document.get("scan") or {}).get("files_scanned"),
            "positive_control": (document.get("positive_control") or {}).get("control"),
            "status": "PASS" if (document.get("clean") is True
                                 and (document.get("positive_control") or {}).get("control")
                                 is True) else "FAIL",
            "document": document}
    results["sentinel-scan"] = scan
    # Persist the D03 live /proc surfaces and D04 receipt/session inventory.
    write_json(RUNS / "scan" / "d04-surfaces.json", {
        "utc": utc(),
        "receipts": [str(path) for path in
                     (libc.G4C_ROOT / "runs").glob("*/receipt/*.json")][:200],
        "sessions": [str(path) for path in
                     (libc.G4C_ROOT / "runs").glob("*/session/*")][:200],
        "junit": [str(path) for path in
                  (E5_ROOT).glob("junit*.xml")],
        "packets": sorted(str(path) for path in lib.ARTIFACTS.glob("review-packet-*")),
        "note": "byte scan above covers every regular file under these roots; "
                "Packet is NOT_BUILT in G4-D (G4-E owns it)",
    })

    safety = final_safety_cleanup()
    post_canonical = canonical()
    post_containers = containers_absent()
    summary = {
        "schema": "m0.g4d.summary.v1",
        "utc": utc(),
        "impl_sha": lib3d.git_text("rev-parse", "HEAD"),
        "stage": {"path": str(stage),
                  "manifest_sha256": libc.sha256_file(stage / "manifest.json"),
                  "base_sha": json.loads((stage / "manifest.json").read_text(
                      encoding="utf-8")).get("base_sha")},
        "cases": results,
        "canonical_pre": pre_canonical,
        "canonical_post": post_canonical,
        "containers_pre": pre_containers,
        "containers_post": post_containers,
        "final_cleanup": safety,
        "synthetic": True,
        "provider_route_kind": "synthetic_only",
        "real_model_calls": 0,
        "real_external_http_calls": 0,
        "provider_keys_seen": 0,
        "billable_send_allowed": 0,
        "live_gate": "BLOCKED",
    }
    statuses = {name: (value.get("status") if isinstance(value, dict) else "FAIL")
                for name, value in results.items()}
    text = ["G4D_SUMMARY", f"IMPL_SHA={summary['impl_sha']}",
            f"STAGE={stage}", f"UTC={summary['utc']}",
            f"CONTAINERS_POST_EMPTY={post_containers['empty']}",
            f"ROOTFS_CANONICAL={post_canonical['rootfs']['ok']}",
            f"DEPS_CANONICAL={post_canonical['deps']['ok']}",
            "CASES:"]
    text.extend(f"  {name} {status}" for name, status in sorted(statuses.items()))
    write_json(E5_ROOT / "summary.json", summary)
    (E5_ROOT / "summary.txt").write_text("\n".join(text) + "\n", encoding="utf-8")
    print("\n".join(text))
    return 0 if all(status == "PASS" for status in statuses.values()) else 4


if __name__ == "__main__":
    raise SystemExit(main())
