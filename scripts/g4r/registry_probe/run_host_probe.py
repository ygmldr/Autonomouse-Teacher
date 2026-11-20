#!/usr/bin/env python3
"""G4-R R3 host-side registry probe runner (test-only, no key, no network).

Runs the *frozen* DSH 0.2.2-rc.2 runtime binary against a **test copy** of the
frozen candidate patch (paths rewritten into a temporary directory) plus an
instrumented public Cordis plugin and an SDK JSON-RPC driver. No runtime patch,
no dependency install, no network namespace, no credentials, no model.

What it records (all tool names + canonical schema digests only):

* complete `tools` registry snapshots at plugin-apply and on every
  `tools/change` (registration epoch counter),
* the effective provider-facing `tools` array observed on every `llm/stream`
  waterfall call (per-dispatch tool face),
* optional negative attacks: late extra `bash` tool, duplicate name,
  schema/description drift, unknown-tool face enforcement.

Usage (offline host):
    python3 scripts/g4r/registry_probe/run_host_probe.py \
        --stage /path/to/candidate-stage --mode observe --out /tmp/g4r-registry-evidence

The Stage directory must contain `runtime/bridge/lib/index.js` and
`runtime/skill/lib/index.js` (the built candidate plugins) plus `node_modules`
(0.2.2-rc.2 packages). The script never writes into the Stage.

Exit codes: 0 = probe ran and summary written; 3 = environment/prerequisite
missing (BLOCKED, no fabricated PASS); 4 = probe ran but registry evidence
incomplete.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PROBE_DIR = Path(__file__).resolve().parent
PROBE_PLUGIN = PROBE_DIR / "probe_plugin" / "lib" / "index.js"
FROZEN_PATCH = REPO_ROOT / "config" / "g3d" / "candidate" / "bridge.patch.yml"
FROZEN_DSH_HOME = REPO_ROOT / "artifacts" / "g4" / "runtime" / "dsh-home" / "dsh"
RUNTIME_CANDIDATES = (
    REPO_ROOT / "artifacts" / "foundation" / "deps" / "deepseek_harness_runtime"
    / "runtime" / "deepseek-harness-sdk-runtime-linux-x64",
    Path("/root/Autonomous Teacher/artifacts/foundation/deps/deepseek_harness_runtime")
    / "runtime" / "deepseek-harness-sdk-runtime-linux-x64",
)
APPROVED_TOOL_NAME = "skill_lookup"
APPROVED_TOOL_SHA256 = "c984bef0ae31771da16a12ef2e7972b289cde6014b7f8ad12349f16c4f77b704"
APPROVED_TOOLS = [{"name": APPROVED_TOOL_NAME, "sha256": APPROVED_TOOL_SHA256}]


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def locate_runtime(explicit: str = "") -> Path:
    if explicit:
        path = Path(explicit).resolve()
        if path.is_file():
            return path
        raise FileNotFoundError(f"runtime binary not found: {path}")
    for candidate in RUNTIME_CANDIDATES:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("frozen DSH 0.2.2-rc.2 runtime binary not found")


def locate_stage(explicit: str) -> Path:
    stage = Path(explicit).resolve()
    for required in ("runtime/bridge/lib/index.js", "runtime/skill/lib/index.js"):
        if not (stage / required).is_file():
            raise FileNotFoundError(f"stage is missing {required}: {stage}")
    return stage


def rewrite_frozen_patch(frozen_text: str, stage: Path) -> str:
    """Rewrite the frozen patch insert paths into the test-copy Stage paths."""
    bridge = (stage / "runtime" / "bridge" / "lib" / "index.js").as_uri()
    skill = (stage / "runtime" / "skill" / "lib" / "index.js").as_uri()
    text = frozen_text.replace("name: /project/runtime/bridge/lib/index.js", f"name: {bridge}")
    text = text.replace("name: /project/runtime/skill/lib/index.js", f"name: {skill}")
    if text == frozen_text:
        raise ValueError("frozen patch insert paths were not found; refusing an unrewritten probe run")
    return "# G4-R R3 TEST-COPY overlay: insert paths rewritten into a temporary Stage.\n" + text


def probe_patch_yml(plugin_path: Path, config: dict) -> str:
    """Compose the probe overlay; JSON is valid YAML flow style for the config."""
    return (
        "# G4-R R3 instrumented probe overlay (test copy only; no key, no network).\n"
        "- insert:\n"
        "    - id: g4r-registry-probe\n"
        f"      name: {plugin_path.as_uri()}\n"
        f"      config: {json.dumps(config, sort_keys=True)}\n"
    )


def prepare_dsh_home(home_root: Path) -> tuple[Path, str]:
    """Prepare an isolated DSH_HOME; reuse the frozen materialised profile if present."""
    dsh_home = home_root / "dshhome"
    dsh_home.mkdir(parents=True)
    if FROZEN_DSH_HOME.is_dir():
        shutil.copytree(FROZEN_DSH_HOME, dsh_home / "dsh", symlinks=False)
        return dsh_home, "copied-from-artifacts/g4/runtime/dsh-home"
    return dsh_home, "fresh-materialised-by-runtime"


def _reader_lines(proc: subprocess.Popen[str], path: Path) -> None:
    assert proc.stdout is not None
    with path.open("w", encoding="utf-8") as handle:
        for line in proc.stdout:
            handle.write(line)
            handle.flush()


def drive_sdk_session(proc: subprocess.Popen[str], prompt_wait_seconds: float,
                      turns: int = 1, turn_gap_seconds: float = 3.0) -> dict:
    """Send initialize plus one or more prompts over newline-delimited JSON-RPC."""
    assert proc.stdin is not None
    session_id = f"session-{uuid.uuid4().hex}"
    initialize = {
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {
            "cwd": os.getcwd(),
            "provider": "offline-test-only-g3b",
            "model": "fixture-bridge-v1",
        },
    }
    sent = []
    proc.stdin.write(json.dumps(initialize) + "\n")
    proc.stdin.flush()
    sent.append("initialize")
    time.sleep(1.0)
    prompt_sessions = [session_id]
    for turn in range(1, turns + 1):
        if turn > 1:
            # A fresh Session per turn keeps the two-dispatch probe independent
            # of any post-error Session state in the SDK app.
            prompt_sessions.append(f"session-{uuid.uuid4().hex}")
        prompt = {
            "jsonrpc": "2.0", "id": 1 + turn, "method": "session/prompt",
            "params": {
                "sessionId": prompt_sessions[turn - 1],
                "contentBlocks": [{"type": "text", "text": f"G4-R registry probe: no-op turn {turn}"}],
            },
        }
        proc.stdin.write(json.dumps(prompt) + "\n")
        proc.stdin.flush()
        sent.append(f"session/prompt:{turn}")
        time.sleep(prompt_wait_seconds if turn == turns else turn_gap_seconds)
    return {"session_id": session_id, "sessions": prompt_sessions, "sent": sent}


def analyse_probe_records(records: list[dict]) -> dict:
    snapshots = [r for r in records if r.get("kind") == "registry_snapshot"]
    dispatches = [r for r in records if r.get("kind") == "dispatch_tool_face"]
    attacks = [r for r in records if r.get("kind") == "attack_result"]
    max_epoch = max((int(r.get("epoch") or 0) for r in records), default=0)
    union_names = set()
    for snapshot in snapshots:
        union_names.update(snapshot.get("definitions") or [])
    last_dispatch = dispatches[-1] if dispatches else None
    unknown_face = sorted({
        item["name"] for dispatch in dispatches for item in (dispatch.get("unknown") or [])
    })
    unknown_registry = sorted({
        item["name"] for dispatch in dispatches for item in (dispatch.get("registry_unknown") or [])
    })
    return {
        "snapshot_count": len(snapshots),
        "dispatch_count": len(dispatches),
        "attack_count": len(attacks),
        "max_epoch": max_epoch,
        "registry_union_names": sorted(union_names),
        "final_snapshot": snapshots[-1] if snapshots else None,
        "last_dispatch": last_dispatch,
        "attacks": attacks,
        "dispatch_face_approved": bool(last_dispatch and last_dispatch.get("approved_face")),
        "dispatch_registry_approved": bool(last_dispatch and last_dispatch.get("approved_registry")),
        "face_equals_registry": bool(last_dispatch and last_dispatch.get("face_equals_registry")),
        "unknown_tool_face_observed": unknown_face,
        "unknown_registry_observed": unknown_registry,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", required=True, help="candidate Stage directory (read-only)")
    parser.add_argument("--runtime", default="", help="explicit frozen DSH runtime binary")
    parser.add_argument("--out", default="", help="evidence output root (default: artifacts/g4r/registry)")
    parser.add_argument("--mode", default="observe",
                        choices=["observe", "enforce", "attack-late-extra-bash",
                                 "attack-duplicate-name", "attack-schema-drift",
                                 "attack-two-turn"])
    parser.add_argument("--prompt-wait", type=float, default=8.0,
                        help="seconds to wait for the prompted turn before terminating")
    parser.add_argument("--turns", type=int, default=1,
                        help="number of prompted turns (2 = registration-between-turns probe)")
    parser.add_argument("--turn-gap", type=float, default=3.0,
                        help="seconds between prompted turns")
    parser.add_argument("--probe-out-name", default="probe-events.jsonl")
    parser.add_argument("--drop-probe-output", action="store_true",
                        help="RG-11 observer-failure probe: point the probe output at an unwritable path")
    parser.add_argument("--skip-frozen-patch", action="store_true",
                        help="hidden-tool risk probe: boot the default sdk-minimal profile without the frozen overlay")
    parser.add_argument("--keep-workdir", action="store_true")
    return parser.parse_args(argv)


def attack_config(mode: str) -> dict:
    approved = list(APPROVED_TOOLS)
    if mode == "attack-late-extra-bash":
        # Register an extra `bash` tool after the startup snapshot but before
        # the first provider dispatch; enforce at llm/stream must deny it.
        return {"mode": "enforce", "attack": "late_extra_bash",
                "attackDelayMs": 300, "approved": approved}
    if mode == "attack-duplicate-name":
        return {"mode": "observe", "attack": "duplicate_name",
                "attackDelayMs": 300, "approved": approved}
    if mode == "attack-schema-drift":
        return {"mode": "observe", "attack": "schema_drift",
                "attackDelayMs": 300, "approved": approved}
    if mode == "attack-two-turn":
        # First turn is clean; an extra tool is registered between turn 1 and
        # turn 2; the enforced second dispatch must be denied (no first-turn-only check).
        return {"mode": "enforce", "attack": "late_extra_bash",
                "attackDelayMs": 2200, "approved": approved}
    return {"mode": mode, "attack": "none", "approved": approved}


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    runtime = locate_runtime(args.runtime)
    stage = locate_stage(args.stage)
    run_utc = utc_now()
    run_id = run_utc.replace(":", "").replace("-", "")
    out_root = Path(args.out).resolve() if args.out else REPO_ROOT / "artifacts" / "g4r" / "registry"
    run_dir = out_root / f"{run_id}-{args.mode}"
    run_dir.mkdir(parents=True, exist_ok=True)

    workdir = Path(tempfile.mkdtemp(prefix="g4r-registry-probe-"))
    probe_out = workdir / args.probe_out_name
    if args.drop_probe_output:
        # RG-11: the observer cannot write. Observation failure must not change
        # runtime admission; it only produces an evidence gap.
        probe_out = Path("/nonexistent-g4r-observer-dir") / "probe-events.jsonl"
    summary: dict = {
        "schema": "g4r.registry.probe.run.v1",
        "run_id": f"{run_id}-{args.mode}",
        "utc": run_utc,
        "mode": args.mode,
        "runtime_sha256": sha256_file(runtime),
        "stage_dir": str(stage),
        "stage_bridge_sha256": sha256_file(stage / "runtime" / "bridge" / "lib" / "index.js"),
        "stage_skill_sha256": sha256_file(stage / "runtime" / "skill" / "lib" / "index.js"),
        "probe_plugin_sha256": sha256_file(PROBE_PLUGIN),
        "frozen_patch_sha256": sha256_file(FROZEN_PATCH),
        "network": "unshare -n (no network namespace)",
        "real_key_present": False,
        "real_provider_calls": 0,
    }
    exit_code = 3
    proc: subprocess.Popen[str] | None = None
    try:
        frozen_text = FROZEN_PATCH.read_text(encoding="utf-8")
        effective_patch = workdir / "frozen-effective.patch.yml"
        effective_patch.write_text(rewrite_frozen_patch(frozen_text, stage), encoding="utf-8")
        probe_patch = workdir / "probe.patch.yml"
        probe_patch.write_text(probe_patch_yml(PROBE_PLUGIN, attack_config(args.mode)),
                               encoding="utf-8")
        home = workdir / "home"
        home.mkdir()
        dsh_home, dsh_home_source = prepare_dsh_home(workdir)
        summary["dsh_home_source"] = dsh_home_source
        patch_args = ["--patch", str(probe_patch)]
        summary["patches"] = {
            "frozen_effective_sha256": None if args.skip_frozen_patch else sha256_file(effective_patch),
            "probe_sha256": sha256_file(probe_patch),
            "frozen_patch_applied": not args.skip_frozen_patch,
        }
        if not args.skip_frozen_patch:
            patch_args = ["--patch", str(effective_patch)] + patch_args
        summary["command"] = [
            "unshare", "-n", "env", "-i",
            f"HOME={home}", f"DSH_HOME={dsh_home}", "PATH=/usr/bin:/bin", "TERM=dumb",
            f"G4R_PROBE_OUT={probe_out}",
            str(runtime), "--profile", "sdk-minimal",
        ] + patch_args
        stdout_log = run_dir / "runtime-stdout.log"
        stderr_log = run_dir / "runtime-stderr.log"
        with stdout_log.open("w", encoding="utf-8") as out_handle, \
                stderr_log.open("w", encoding="utf-8") as err_handle:
            proc = subprocess.Popen(
                summary["command"], cwd=str(home),
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=err_handle,
                text=True, bufsize=1,
            )
            # Read stdout on this thread: the SDK app's replies are newline JSON.
            reply_lines: list[str] = []
            try:
                drive = drive_sdk_session(proc, args.prompt_wait, args.turns, args.turn_gap)
                reply_lines.append(json.dumps(drive))
            except (BrokenPipeError, OSError) as error:
                reply_lines.append(json.dumps({"drive_error": str(error)}))
            finally:
                if proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait()
            assert proc.stdout is not None
            out_handle.write(proc.stdout.read())
            out_handle.flush()
            summary["reply_drive"] = json.loads(reply_lines[0])
            summary["runtime_exit_code"] = proc.returncode
        records = []
        if probe_out.is_file():
            for line in probe_out.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
            shutil.copy2(probe_out, run_dir / "probe-events.jsonl")
        summary["probe_records"] = len(records)
        summary["analysis"] = analyse_probe_records(records)
        stdout_text = (run_dir / "runtime-stdout.log").read_text(encoding="utf-8", errors="replace")
        stderr_text = (run_dir / "runtime-stderr.log").read_text(encoding="utf-8", errors="replace")
        summary["streams"] = {
            "stdout_bytes": len(stdout_text),
            "stderr_bytes": len(stderr_text),
            "enforcement_denial_observed": "G4R_REGISTRY_TOOL_FACE_DENIED" in stdout_text
                                          or "G4R_REGISTRY_TOOL_FACE_DENIED" in stderr_text,
            "stdout_tail": stdout_text[-4000:],
            "stderr_tail": stderr_text[-4000:],
        }
        summary["probe_events_sha256"] = (
            sha256_file(run_dir / "probe-events.jsonl") if (run_dir / "probe-events.jsonl").is_file() else None
        )
        summary["probe_observed"] = bool(records)
        if not records and args.drop_probe_output:
            summary["observation_gap"] = "observer output unwritable; runtime unaffected (RG-11 mechanism probe)"
            exit_code = 4
        elif not records:
            summary["blocked_reason"] = "probe plugin did not run or wrote no records"
            exit_code = 4
        else:
            exit_code = 0
    except (FileNotFoundError, ValueError) as error:
        summary["blocked_reason"] = str(error)
        exit_code = 3
    finally:
        if proc is not None and proc.poll() is None:
            proc.kill()
            proc.wait()
        summary["completed_utc"] = utc_now()
        summary_path = run_dir / "run-summary.json"
        summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if not args.keep_workdir:
            shutil.rmtree(workdir, ignore_errors=True)
        else:
            summary["workdir"] = str(workdir)
        print(json.dumps({
            "run_dir": str(run_dir),
            "exit_code": exit_code,
            "probe_records": summary.get("probe_records", 0),
            "analysis": summary.get("analysis", {}),
        }, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
