#!/usr/bin/env python3
"""G4-C case runner: one independent G4-C launch per C-case, then aggregate.

Each case runs ``scripts/g4/launch_c.py`` in its own evidence directory under
``artifacts/g4/c/runs/<case>-<stamp>`` (the launcher refuses a non-empty
evidence directory). Results, raw logs and the aggregate ``cases.json`` are
kept under gitignored ``artifacts/g4/c``. No Key, no model, no external HTTP.

Cases:
  c01                 real DSH Echo, one provider call
  c02                 real DSH Tool, two independent provider calls
  negatives           raw-UDS route/tool/file rejections + network probes +
                      one valid send + byte-identical replay
  crash-before-send   G3B crash hook after ATTEMPT_STARTED, restart, replay
  crash-after-receive G3B crash hook after Fake receipt, restart, replay
  broker-down         kill the trusted Broker subprocess, then one request
  quota               admission max_calls=1, second valid request denied
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
RUNS = libc.G4C_ROOT / "runs"
PYTHON = sys.executable

CASES: dict[str, dict] = {
    "c01": {
        "covers": ["G4-C-01", "G4-C-17", "G4-C-18"],
        "args": ["--case", "c01", "--scenario", "echo", "--session", "g4c-c01",
                 "--timeout", "180"],
    },
    "c02": {
        "covers": ["G4-C-02", "G4-C-17"],
        "args": ["--case", "c02", "--scenario", "tool", "--session", "g4c-c02",
                 "--timeout", "180"],
    },
    "c18": {
        "covers": ["G4-C-18"],
        "args": ["--case", "c18", "--scenario", "stream", "--session",
                 "g4c-c18", "--timeout", "180"],
    },
    "negatives": {
        "covers": ["G4-C-06", "G4-C-13"],
        "args": ["--case", "negatives", "--candidate-mode", "hold",
                 "--scenario", "echo", "--steps", "negatives,network",
                 "--timeout", "120"],
    },
    "replay": {
        "covers": ["G4-C-03", "G4-C-12"],
        "args": ["--case", "replay", "--candidate-mode", "hold",
                 "--scenario", "echo", "--max-calls", "3", "--steps",
                 "valid,replay", "--timeout", "120"],
    },
    "crash-before-send": {
        "covers": ["G4-C-07", "G4-C-12"],
        "args": ["--case", "crash-before-send", "--candidate-mode", "hold",
                 "--scenario", "echo",
                 "--crash-hook", "after_attempt_start_before_fake_send",
                 "--steps", "valid,restart,replay", "--timeout", "120"],
    },
    "crash-after-receive": {
        "covers": ["G4-C-08"],
        "args": ["--case", "crash-after-receive", "--candidate-mode", "hold",
                 "--scenario", "echo",
                 "--crash-hook", "after_fake_receive_before_response",
                 "--steps", "valid,restart,replay", "--timeout", "120"],
    },
    "broker-down": {
        "covers": ["G4-C-03", "G4-C-09"],
        "args": ["--case", "broker-down", "--candidate-mode", "hold",
                 "--scenario", "echo", "--steps", "kill-broker,valid",
                 "--timeout", "120"],
    },
    "quota": {
        "covers": ["G4-C-14"],
        "args": ["--case", "quota", "--candidate-mode", "hold",
                 "--scenario", "echo", "--max-calls", "1",
                 "--steps", "valid,over_quota", "--timeout", "120"],
    },
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default=str(libc.G4C_ROOT))
    parser.add_argument("--stage", default=None)
    parser.add_argument("--only", default=None,
                        help="comma-separated case keys (default: all)")
    parser.add_argument("--timeout", type=float, default=900.0)
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
        "PATH": os.environ.get("PATH", "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"),
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
            "--run-id", f"g4c-{key}-{stamp}"]
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
        sys.stderr.write("G4C_RUN_NEEDS_HOST_ROOT\n")
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
        "schema": "m0.g4c.runner.v1",
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
