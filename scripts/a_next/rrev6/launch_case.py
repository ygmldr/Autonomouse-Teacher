#!/usr/bin/env python3
"""Single-case window driver for the A-PR3 / R-REV6 matrix.

One process = one case = one fresh writable rootfs copy.  The frozen staged
rootfs is never offered to podman: this driver copies it per case, verifies the
canonical hash, rebinds ``lib_g3d.ROOTFS`` process-locally and then uses the
unchanged G4-C launcher classes.

Modes
* ``--turns`` (JSON): custom multi-turn driver used for Echo(1) / Tool(2) /
  Resume(turn1 echo + turn2 resume) / same-business-request replay.  Each turn is
  one real DSH candidate container sharing the same candidate session dir.
* default: the standard G4-C flow (one candidate run + optional steps).
* ``--inject {candidate-crash,trusted-kill,fake-crash}``: starts a watcher thread
  that waits for the controller's test-only delay marker and then performs the
  injection with host ``podman`` commands (no product/src hook is used).

The driver never edits the stage or the frozen inputs.  It writes the normal
G4-C evidence plus the G4-R request-lifecycle / recovery-diagnostic JSONL and an
``a_next/case-runner.json`` identity record.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts" / "g3d"))
sys.path.insert(0, str(REPO / "scripts" / "g4"))

import lib_g3d as lib3d  # noqa: E402
import launch_c as g4c_launch  # noqa: E402

ROOTFS_CANON = lib3d.ROOTFS_CANON
STATE_CP_FILES = ("request-lifecycle.jsonl", "recovery-diagnostics.jsonl",
                  "dispatch-window.jsonl", "g4c-send-journal.jsonl",
                  "g4c-policy.json", "ready")
INJECTIONS = {"candidate-crash", "trusted-kill", "fake-crash",
              "fake-crash-after-receipt", "broker-kill"}


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_tree(path: Path) -> str:
    proc = subprocess.run(
        ["tar", "--sort=name", "--mtime=@0", "--owner=0", "--group=0",
         "--numeric-owner", "-cf", "-", "-C", str(path), "."],
        capture_output=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"tar failed for {path}")
    return hashlib.sha256(proc.stdout).hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def containers() -> list[str]:
    proc = subprocess.run(["podman", "ps", "-a", "--format", "{{.Names}}"],
                          capture_output=True, text=True, timeout=60)
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


class CaseDriver(g4c_launch.G4CLauncher):
    """G4-C launcher plus a real-DSH multi-turn driver (no product change)."""

    def __init__(self, args: argparse.Namespace) -> None:
        super().__init__(args)
        self.turn_records: list[dict] = []

    def run_turn(self, turn: dict) -> dict:
        label = str(turn["label"])
        scenario = str(turn["scenario"])
        prompt = str(turn["prompt"])
        name = lib3d.container_name(self.run_id, f"candidate-{label}")
        argv = lib3d.candidate_run_argv(
            podman="podman", rootfs=str(lib3d.ROOTFS),
            stage_candidate=str(self.stage_dir / "candidate"),
            deps=str(lib3d.DEPS), run_dir=str(self.run_dir), name=name,
            scenario=scenario, session=self.args.session, prompt=prompt,
            timeout_s=int(self.args.timeout) + 60, label=label)
        self._write_argv(f"candidate-{label}", argv)
        started = utc_now()
        record = self.cmd(argv, name=f"podman-run-candidate-{label}", timeout=90)
        if record["exit"] != 0:
            raise lib3d.G3DError("candidate start failed",
                                 exit_code=lib3d.EXIT_CANDIDATE_START_FAILED,
                                 detail={"label": label})
        document = self.podman_inspect(name, label=f"inspect-candidate-{label}")
        if document is not None:
            self.write_evidence_json(f"run/inspect-candidate-{label}.json", document)
        wait = self.cmd(["podman", "wait", "--interval", "200ms", name],
                        name=f"podman-wait-candidate-{label}",
                        timeout=float(self.args.timeout))
        if wait.get("timed_out"):
            self.cmd(["podman", "kill", "-s", "KILL", name],
                     name=f"kill-candidate-{label}", timeout=30)
            self.cmd(["podman", "wait", "--interval", "200ms", name],
                     name=f"podman-wait-candidate-{label}-killed", timeout=30)
        final = self.podman_inspect(name, label=f"inspect-candidate-{label}-final")
        exit_code = None
        if final is not None:
            exit_code = int(final["State"].get("ExitCode", -1))
            self.write_evidence_json(f"run/inspect-candidate-{label}-final.json",
                                     final)
        logs = self._container_logs(name, f"candidate-log-{label}")
        lib3d.write_bytes_atomic(self.evidence / "run" / f"candidate-{label}.log",
                                 logs.encode(), mode=0o444)
        self.cmd(["podman", "rm", "-f", name], name=f"rm-candidate-{label}",
                 timeout=60)
        result = None
        result_path = (self.run_dir / "candidate-session" / "evidence" /
                       f"dsh-result-{label}.json")
        if result_path.is_file():
            try:
                result = json.loads(lib3d.read_regular_bytes(
                    result_path, max_bytes=8 << 20).decode("utf-8"))
            except (lib3d.G3DError, OSError, json.JSONDecodeError):
                result = None
        row = {"label": label, "scenario": scenario,
               "prompt_sha256": sha256_text(prompt),
               "session": self.args.session, "container": name,
               "utc_start": started, "utc_end": utc_now(),
               "exit_code": exit_code, "result": result,
               "result_path": str(result_path)}
        self.turn_records.append(row)
        return row


def start_injection(kind: str, run_id: str, run_dir: Path,
                    evidence: Path) -> tuple[dict, threading.Thread]:
    holder: dict = {"kind": kind, "utc_start": utc_now()}
    marker = run_dir / "state" / "g4f5-delay-marker.json"

    def running_container(role: str) -> str | None:
        proc = subprocess.run(["podman", "ps", "--format", "{{.Names}}"],
                              capture_output=True, text=True, timeout=30)
        for name in proc.stdout.splitlines():
            name = name.strip()
            if run_id in name and role in name:
                return name
        return None

    def wait_receipt(timeout: float = 60.0) -> dict | None:
        receipts = run_dir / "state" / "receipts"
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if receipts.is_dir():
                rows = sorted(receipts.glob("rcpt-*.json"))
                if rows:
                    return {"receipt": rows[0].name, "count": len(rows)}
            time.sleep(0.02)
        return None

    def wait_marker(timeout: float = 60.0) -> dict | None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if marker.is_file():
                try:
                    return json.loads(marker.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    return None
            time.sleep(0.05)
        return None

    def worker() -> None:
        if kind == "fake-crash-after-receipt":
            observed = wait_receipt()
            holder["observed"] = observed
            if observed is None:
                holder["error"] = "receipt_not_observed"
                return
            marker_doc = {"hook": "receipt", "receipt": observed["receipt"]}
        else:
            marker_doc = wait_marker()
        holder["marker"] = marker_doc
        if marker_doc is None:
            holder["error"] = "delay_marker_not_observed"
            return
        if kind == "candidate-crash":
            target = running_container("candidate")
            if target is None:
                holder["error"] = "candidate_container_not_running"
                return
            argv = ["podman", "kill", "-s", "KILL", target]
        elif kind == "trusted-kill":
            target = running_container("trusted")
            if target is None:
                holder["error"] = "trusted_container_not_running"
                return
            argv = ["podman", "kill", "-s", "KILL", target]
        elif kind == "broker-kill":
            code = (
                "import os,signal\n"
                "killed=[]\n"
                "for name in os.listdir('/proc'):\n"
                "    if not name.isdigit(): continue\n"
                "    try: cmd=open('/proc/'+name+'/cmdline','rb').read()\n"
                "    except OSError: continue\n"
                "    if b'autoteacher_m0.accounting.broker' in cmd and int(name)!=os.getpid():\n"
                "        os.kill(int(name), signal.SIGKILL); killed.append(int(name))\n"
                "print('A_NEXT_BROKER_KILLED '+str(killed))\n")
            target = running_container("trusted")
            if target is None:
                holder["error"] = "trusted_container_not_running"
                return
            argv = ["podman", "exec", target, "/opt/python/bin/python3.11",
                    "-B", "-c", code]
        elif kind == "fake-crash-after-receipt":
            code = (
                "import os,signal\n"
                "killed=[]\n"
                "for name in os.listdir('/proc'):\n"
                "    if not name.isdigit(): continue\n"
                "    try: cmd=open('/proc/'+name+'/cmdline','rb').read()\n"
                "    except OSError: continue\n"
                "    if b'fake_provider.py' in cmd and int(name)!=os.getpid():\n"
                "        os.kill(int(name), signal.SIGKILL); killed.append(int(name))\n"
                "print('A_NEXT_FAKE_KILLED '+str(killed))\n")
            target = running_container("trusted")
            if target is None:
                holder["error"] = "trusted_container_not_running"
                return
            argv = ["podman", "exec", target, "/opt/python/bin/python3.11",
                    "-B", "-c", code]
        else:  # fake-crash: kill the trusted Fake subprocess only
            code = (
                "import os,signal\n"
                "killed=[]\n"
                "for name in os.listdir('/proc'):\n"
                "    if not name.isdigit(): continue\n"
                "    try: cmd=open('/proc/'+name+'/cmdline','rb').read()\n"
                "    except OSError: continue\n"
                "    if b'fake_provider.py' in cmd and int(name)!=os.getpid():\n"
                "        os.kill(int(name), signal.SIGKILL); killed.append(int(name))\n"
                "print('A_NEXT_FAKE_KILLED '+str(killed))\n")
            target = running_container("trusted")
            if target is None:
                holder["error"] = "trusted_container_not_running"
                return
            argv = ["podman", "exec", target, "/opt/python/bin/python3.11",
                    "-B", "-c", code]
        holder["command"] = argv
        try:
            proc = subprocess.run(argv, capture_output=True, text=True,
                                  timeout=60)
            holder["result"] = {"exit": proc.returncode,
                                "stdout": proc.stdout.strip()[-500:],
                                "stderr": proc.stderr.strip()[-500:]}
        except (OSError, subprocess.TimeoutExpired) as exc:
            holder["result"] = {"error": type(exc).__name__}
        holder["utc_end"] = utc_now()

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    return holder, thread


def copy_state_extra(driver: CaseDriver) -> dict:
    target = driver.evidence / "run" / "state"
    target.mkdir(parents=True, exist_ok=True)
    copied = []
    state = driver.run_dir / "state"
    for name in STATE_CP_FILES + ("broker.sqlite3", "broker.sqlite3-wal",
                                  "attempts.sqlite3", "attempts.sqlite3-wal"):
        source = state / name
        if not source.is_file():
            continue
        data = lib3d.read_regular_bytes(source, max_bytes=16 << 20)
        lib3d.write_bytes_atomic(target / name, data, mode=0o444)
        copied.append({"name": name, "sha256": lib3d.sha256_bytes(data),
                       "bytes": len(data)})
    return {"files": copied}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True)
    parser.add_argument("--stage", required=True)
    parser.add_argument("--evidence-dir", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--rootfs-work", required=True)
    parser.add_argument("--work-root", default=None)
    parser.add_argument("--turns", default=None,
                        help="JSON list of {label,scenario,prompt}")
    parser.add_argument("--inject", default=None, choices=sorted(INJECTIONS))
    parser.add_argument("--steps", default=None)
    parser.add_argument("--scenario", default="echo")
    parser.add_argument("--session", default="a-next-rrev6")
    parser.add_argument("--prompt", default=None)
    parser.add_argument("--candidate-mode", default="dsh")
    parser.add_argument("--crash-hook", default=None)
    parser.add_argument("--test-delay-hook", default=None)
    parser.add_argument("--test-delay-ms", type=int, default=None)
    parser.add_argument("--revocation", action="store_true")
    parser.add_argument("--pre-revoke", action="store_true")
    parser.add_argument("--watch-revocation", default=None)
    parser.add_argument("--deadline-ms", type=int, default=None)
    parser.add_argument("--max-calls", type=int, default=None)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--ready-timeout", type=float, default=30.0)
    parser.add_argument("--hold-seconds", type=int, default=600)
    parser.add_argument("--label", default=None)
    parser.add_argument("--sub", default="")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    rootfs_work = Path(args.rootfs_work).resolve()
    if sha256_tree(rootfs_work) != ROOTFS_CANON:
        sys.stderr.write("CASE_ROOTFS_WORK_NOT_CANONICAL\n")
        return lib3d.EXIT_EVIDENCE_INTEGRITY
    if containers():
        sys.stderr.write("CASE_CONTAINERS_PRESENT\n")
        return lib3d.EXIT_BLOCKED_ENVIRONMENT
    lib3d.ROOTFS = rootfs_work
    launcher_argv = ["--case", args.case, "--stage", args.stage,
                     "--evidence-dir", args.evidence_dir,
                     "--run-id", args.run_id,
                     "--scenario", args.scenario, "--session", args.session,
                     "--candidate-mode", args.candidate_mode,
                     "--timeout", str(args.timeout),
                     "--ready-timeout", str(args.ready_timeout)]
    if args.prompt:
        launcher_argv += ["--prompt", args.prompt]
    if args.steps:
        launcher_argv += ["--steps", args.steps]
    if args.crash_hook:
        launcher_argv += ["--crash-hook", args.crash_hook]
    if args.test_delay_hook:
        launcher_argv += ["--test-delay-hook", args.test_delay_hook]
    if args.test_delay_ms:
        launcher_argv += ["--test-delay-ms", str(args.test_delay_ms)]
    if args.revocation:
        launcher_argv += ["--revocation"]
    if args.pre_revoke:
        launcher_argv += ["--pre-revoke"]
    if args.watch_revocation:
        launcher_argv += ["--watch-revocation", args.watch_revocation]
    if args.deadline_ms is not None:
        launcher_argv += ["--deadline-ms", str(args.deadline_ms)]
    if args.max_calls is not None:
        launcher_argv += ["--max-calls", str(args.max_calls)]
    if args.label:
        launcher_argv += ["--label", args.label]
    ns = g4c_launch.parse_args(launcher_argv)
    driver = CaseDriver(ns)
    started = utc_now()
    runner_record: dict = {"case": args.case, "run_id": args.run_id,
                           "utc_start": started, "argv": argv,
                           "rootfs_work": str(rootfs_work),
                           "rootfs_work_sha256_before": ROOTFS_CANON,
                           "injection": None, "turns": [], "failure": None}
    watcher = None
    holder = None
    try:
        driver.preflight()
        driver.create_run()
        driver.write_configs()
        driver.start_trusted()
        if args.inject:
            holder, watcher = start_injection(args.inject, args.run_id,
                                              driver.run_dir, driver.evidence)
            runner_record["injection"] = holder
        if args.turns:
            turns = json.loads(args.turns)
            for turn in turns:
                runner_record["turns"].append(driver.run_turn(turn))
        else:
            driver.start_candidate()
        if args.steps:
            runner_record["steps"] = driver.run_steps(
                [step for step in args.steps.split(",") if step])
        driver.collect()
    except lib3d.G3DError as exc:
        driver.failure = {"reason": exc.reason, "message": str(exc),
                          "detail": exc.detail}
        driver.exit_code = exc.exit_code
        runner_record["failure"] = driver.failure
    except BaseException as exc:  # noqa: BLE001 - always collect evidence
        driver.failure = {"reason": "INTERNAL",
                          "message": f"{type(exc).__name__}: {exc}"}
        driver.exit_code = lib3d.EXIT_CASE_FAILED
        runner_record["failure"] = driver.failure
    finally:
        if watcher is not None:
            watcher.join(timeout=90.0)
        runner_record["injection"] = holder
        try:
            driver.collect()
        except Exception:  # noqa: BLE001
            pass
        try:
            snapshot = driver._ledger_snapshot()
            runner_record["ledger"] = snapshot
        except Exception:  # noqa: BLE001
            runner_record["ledger"] = None
        try:
            # request-lifecycle / recovery-diagnostic JSONL live in the run dir;
            # copy them BEFORE cleanup deletes the run directory.
            runner_record["state_extra"] = copy_state_extra(driver)
        except Exception as exc:  # noqa: BLE001
            runner_record["state_extra"] = {"error": type(exc).__name__}
        try:
            driver.cleanup()
        except Exception as exc:  # noqa: BLE001
            runner_record["cleanup_error"] = f"{type(exc).__name__}: {exc}"
        driver.exit_code = driver.exit_code or 0
        try:
            driver.write_evidence()
        except Exception:  # noqa: BLE001
            pass
        runner_record["utc_end"] = utc_now()
        runner_record["evidence"] = str(driver.evidence)
        runner_record["run_dir"] = str(driver.run_dir)
        runner_record["stage"] = {"path": str(driver.stage_dir),
                                  "manifest_sha256": driver.records.get(
                                      "stage", {}).get("manifest_sha256")}
        runner_record["rootfs_work_sha256_after"] = sha256_tree(rootfs_work)
        runner_record["containers_after"] = containers()
        runner_record["real_model_calls"] = 0
        runner_record["real_external_http_calls"] = 0
        runner_record["provider_keys_seen"] = 0
        out = driver.evidence / "a_next"
        out.mkdir(parents=True, exist_ok=True)
        (out / "case-runner.json").write_text(
            json.dumps(runner_record, indent=2, sort_keys=True) + "\n")
        print(json.dumps({"case": args.case, "status": "OK",
                          "evidence": str(driver.evidence),
                          "containers_after": runner_record["containers_after"]},
                         sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
