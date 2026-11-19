#!/usr/bin/env python3
"""G4-F5 evidence runner: revocation / timeout / in-flight failure matrix.

Each case is one independent ``launch_c.py`` run with a real trusted container,
a real Candidate (real DSH for the revocation/timeout/crash cases, hold-mode raw
UDS for the replay-after-crash cases), the real Broker and the real synthetic
Fake. Everything runs with ``--network none``, no Key, no model and no external
HTTP. Results stay under gitignored ``artifacts/g4f/f5/l2``.

Cases (``--only`` comma separated):
  revocation-pre-reserve        revoke before the DSH request; no ledger
  revocation-post-reserve       revoke between Reserve and the wire (real DSH)
  revocation-in-flight          revoke after the Fake receipt; settlement stands
  timeout-pre-send              real delay before Reserve > admission deadline
  timeout-post-send             Fake stalls after the receipt; deadline first
  crash-after-authorize         G4-F5 hook after gate authorize, before consume
  crash-after-consume           G4-F5 hook after gate consume, before the Fake
  crash-before-send (hold)      frozen G3-B hook before authorize + replay
  crash-after-receive (hold)    frozen G3-B hook after receipt + replay
  revocation-post-reserve-hold  same window + second request rejected
  revocation-in-flight-hold     in-flight revoke + second request rejected
  crash-after-authorize-hold    real controller crash + replay no-op
  crash-after-consume-hold      real controller crash + replay no-op
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "g3d"))
import lib_g4 as lib  # noqa: E402
import lib_g4c as libc  # noqa: E402
import lib_g3d as lib3d  # noqa: E402

LAUNCH = Path(__file__).resolve().parent / "launch_c.py"
RUNS = lib.ARTIFACTS / "g4f" / "f5"
PYTHON = sys.executable

CASES: dict[str, dict] = {
    "revocation-pre-reserve": {
        "covers": ["F5-REV-A", "F5-STOP"],
        "args": ["--case", "revocation-pre-reserve", "--candidate-mode", "dsh",
                 "--scenario", "echo", "--revocation", "--pre-revoke",
                 "--timeout", "180"],
    },
    "revocation-post-reserve": {
        "covers": ["F5-REV-B"],
        "args": ["--case", "revocation-post-reserve", "--candidate-mode", "dsh",
                 "--scenario", "echo", "--revocation",
                 "--test-delay-hook", "after_reserve_before_send",
                 "--test-delay-ms", "6000", "--watch-revocation",
                 "after_reserve", "--steps", "restart", "--timeout", "240"],
    },
    "revocation-in-flight": {
        "covers": ["F5-REV-C"],
        "args": ["--case", "revocation-in-flight", "--candidate-mode", "dsh",
                 "--scenario", "cancel", "--revocation", "--watch-revocation",
                 "in_flight", "--timeout", "180"],
    },
    "timeout-pre-send": {
        "covers": ["F5-TO-A"],
        "args": ["--case", "timeout-pre-send", "--candidate-mode", "dsh",
                 "--scenario", "deadline_stall", "--test-delay-hook",
                 "before_reserve", "--test-delay-ms", "2500",
                 "--timeout", "180"],
    },
    "timeout-post-send": {
        "covers": ["F5-TO-B"],
        "args": ["--case", "timeout-post-send", "--candidate-mode", "dsh",
                 "--scenario", "deadline_stall", "--steps", "restart",
                 "--timeout", "180"],
    },
    "crash-after-authorize": {
        "covers": ["F5-CR-AUTH"],
        "args": ["--case", "crash-after-authorize", "--candidate-mode", "dsh",
                 "--scenario", "echo", "--crash-hook",
                 "after_send_authorize_before_consume",
                 "--steps", "restart", "--timeout", "180"],
    },
    "crash-after-consume": {
        "covers": ["F5-CR-CONSUME"],
        "args": ["--case", "crash-after-consume", "--candidate-mode", "dsh",
                 "--scenario", "echo", "--crash-hook",
                 "after_send_consume_before_fake",
                 "--steps", "restart", "--timeout", "180"],
    },
    "crash-before-send": {
        "covers": ["F5-CR-PRE"],
        "args": ["--case", "crash-before-send", "--candidate-mode", "hold",
                 "--scenario", "echo", "--crash-hook",
                 "after_attempt_start_before_fake_send",
                 "--steps", "valid,restart,replay", "--timeout", "120"],
    },
    "crash-after-receive": {
        "covers": ["F5-CR-POST"],
        "args": ["--case", "crash-after-receive", "--candidate-mode", "hold",
                 "--scenario", "echo", "--crash-hook",
                 "after_fake_receive_before_response",
                 "--steps", "valid,restart,replay", "--timeout", "120"],
    },
    "revocation-post-reserve-hold": {
        "covers": ["F5-REV-B", "F5-REJECT"],
        "args": ["--case", "revocation-post-reserve", "--candidate-mode", "hold",
                 "--scenario", "echo", "--revocation", "--max-calls", "4",
                 "--test-delay-hook", "after_reserve_before_send",
                 "--test-delay-ms", "6000",
                 "--steps", "valid-revoke-after-reserve,valid2,restart",
                 "--timeout", "240"],
    },
    "revocation-in-flight-hold": {
        "covers": ["F5-REV-C", "F5-REJECT"],
        "args": ["--case", "revocation-in-flight", "--candidate-mode", "hold",
                 "--scenario", "cancel", "--revocation", "--max-calls", "4",
                 "--steps", "valid-revoke-in-flight,valid2",
                 "--timeout", "180"],
    },
    "crash-after-authorize-hold": {
        "covers": ["F5-CR-AUTH", "F5-REPLAY"],
        "args": ["--case", "crash-after-authorize", "--candidate-mode", "hold",
                 "--scenario", "echo", "--crash-hook",
                 "after_send_authorize_before_consume",
                 "--steps", "valid,restart,replay", "--timeout", "120"],
    },
    "crash-after-consume-hold": {
        "covers": ["F5-CR-CONSUME", "F5-REPLAY"],
        "args": ["--case", "crash-after-consume", "--candidate-mode", "hold",
                 "--scenario", "echo", "--crash-hook",
                 "after_send_consume_before_fake",
                 "--steps", "valid,restart,replay", "--timeout", "120"],
    },
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default=str(RUNS / "l2"))
    parser.add_argument("--stage", default=None)
    parser.add_argument("--only", default=None,
                        help="comma-separated case keys (default: all)")
    parser.add_argument("--timeout", type=float, default=1200.0)
    return parser.parse_args(argv)


def stage_path(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).resolve()
    candidates = sorted(path for path in libc.STAGE_ROOT.glob("stage-*")
                        if (path / "manifest.json").is_file())
    if not candidates:
        raise SystemExit("no G4-C stage; run scripts/g4/build_stage_c.py first")
    return candidates[-1]


def clean_env() -> dict[str, str]:
    return {
        "PATH": os.environ.get(
            "PATH", "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"),
        "HOME": "/root",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": f"{libc.REPO / 'src'}:{libc.REPO / 'artifacts' / 'foundation' / 'deps'}",
        "LC_ALL": "C",
        "TZ": "UTC",
    }


def containers() -> list[str]:
    proc = subprocess.run(["podman", "ps", "-a", "--format", "{{.Names}}"],
                          capture_output=True, text=True, timeout=60)
    return [line for line in proc.stdout.splitlines() if line.strip()]


def run_case(key: str, spec: dict, *, out_dir: Path, stage: Path,
             timeout: float) -> dict:
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    evidence = out_dir / "runs" / f"{key}-{stamp}"
    evidence.mkdir(parents=True, exist_ok=False)
    log_path = out_dir / "logs" / f"{key}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    argv = [PYTHON, "-B", str(LAUNCH), *spec["args"],
            "--stage", str(stage), "--evidence-dir", str(evidence),
            "--run-id", f"g4f5-{key}-{stamp}"]
    started = lib.utc_now()
    with open(log_path, "w", encoding="utf-8") as handle:
        handle.write("ARGV " + json.dumps(argv) + "\n")
        handle.flush()
        proc = subprocess.run(argv, cwd=str(libc.REPO), capture_output=True,
                              text=True, env=clean_env(), timeout=timeout)
        handle.write(proc.stdout)
        handle.write(proc.stderr)
    finished = lib.utc_now()
    summary_path = evidence / "summary.json"
    summary = None
    if summary_path.is_file():
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            summary = None
    checks = (summary or {}).get("checks") or []
    failed = [item["id"] for item in checks if not item.get("ok")]
    record = {
        "case": key,
        "covers": spec["covers"],
        "argv": argv,
        "utc_start": started,
        "utc_end": finished,
        "exit_code": proc.returncode,
        "evidence": str(evidence),
        "log": str(log_path),
        "summary": summary,
        "checks_total": len(checks),
        "checks_failed": failed,
        "containers_after": containers(),
        "stdout_tail": proc.stdout[-3000:],
        "stderr_tail": proc.stderr[-3000:],
    }
    record["ok"] = (proc.returncode == 0 and summary is not None
                    and not failed and not record["containers_after"])
    lib.write_json_atomic(evidence / "runner.json", record)
    return record


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if os.geteuid() != 0:
        sys.stderr.write("G4F5_RUN_NEEDS_HOST_ROOT\n")
        return lib3d.EXIT_BLOCKED_ENVIRONMENT
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stage = stage_path(args.stage)
    validation = libc.validate_stage_g4(stage, base_sha=lib3d.git_text(
        "rev-parse", "HEAD"), verify_git=True)
    selected = (args.only.split(",") if args.only else list(CASES))
    unknown = [key for key in selected if key not in CASES]
    if unknown:
        sys.stderr.write(f"unknown cases: {unknown}\n")
        return 2
    if containers():
        sys.stderr.write("containers already present; refusing to start\n")
        return lib3d.EXIT_BLOCKED_ENVIRONMENT
    if not validation["ok"]:
        sys.stderr.write("stage invalid: "
                         + json.dumps(validation["problems"][:10]) + "\n")
        return lib3d.EXIT_STAGE_INVALID
    report: dict = {
        "schema": "m0.g4f.f5.runner.v1",
        "utc_start": lib.utc_now(),
        "head": lib3d.git_text("rev-parse", "HEAD"),
        "stage": str(stage),
        "stage_manifest_sha256": validation["manifest_sha256"],
        "cases": {},
    }
    for key in selected:
        try:
            report["cases"][key] = run_case(key, CASES[key], out_dir=out_dir,
                                            stage=stage, timeout=args.timeout)
        except subprocess.TimeoutExpired as exc:
            report["cases"][key] = {"case": key, "ok": False,
                                    "error": f"TIMEOUT:{exc.timeout}"}
            subprocess.run(["podman", "ps", "-a", "--format", "{{.Names}}"],
                           capture_output=True, text=True, timeout=60)
        report.setdefault("commands", []).append({
            "case": key, "argv": report["cases"][key].get("argv"),
            "utc": lib.utc_now(),
            "exit": report["cases"][key].get("exit_code")})
        lib.write_json_atomic(out_dir / "summary.json", report)
    report["utc_end"] = lib.utc_now()
    report["containers_after"] = containers()
    report["rootfs_sha256"] = lib3d.sha256_tree(lib3d.ROOTFS)
    report["deps_sha256"] = lib3d.sha256_tree(lib3d.DEPS)
    report["rootfs_canonical"] = report["rootfs_sha256"] == lib3d.ROOTFS_CANON
    report["deps_canonical"] = report["deps_sha256"] == lib3d.DEPS_CANON
    report["stage_sha256_after"] = lib3d.sha256_tree(stage)
    report["real_model_calls"] = 0
    report["real_external_http_calls"] = 0
    report["provider_keys_seen"] = 0
    report["live_gate_status"] = "BLOCKED"
    report["ok"] = (all(record.get("ok") for record in report["cases"].values())
                    and not report["containers_after"]
                    and report["rootfs_canonical"] and report["deps_canonical"])
    written = lib.write_json_atomic(out_dir / "summary.json", report)
    print(json.dumps({"ok": report["ok"],
                      "cases": {key: value.get("ok")
                                for key, value in report["cases"].items()},
                      "containers_after": report["containers_after"],
                      "file": str(out_dir / "summary.json"),
                      "sha256": written["sha256"]}, sort_keys=True))
    return lib3d.EXIT_OK if report["ok"] else lib3d.EXIT_CASE_FAILED


if __name__ == "__main__":
    raise SystemExit(main())
