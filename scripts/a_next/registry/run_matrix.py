#!/usr/bin/env python3
"""A-NEXT A-PR2 registry attack matrix runner (test-only, offline, no key).

Runs the frozen DSH 0.2.2-rc.2 runtime on the host with a **test-copy** of the
frozen candidate overlay (insert paths rewritten to a temporary Stage) plus the
A-PR2 instrumented public Cordis probe, and — for multi-turn / resume cases — a
minimal synthetic trusted-bridge UDS provider (`fake_bridge.py`) so a real DSH
turn can complete without a model, key or network.

Everything is offline: `unshare -n` (empty network namespace), `env -i`, no
downloads, no dependency install, no container, no real Provider, no Key. The
frozen runtime binary, Stage, deps and repo configs are read-only.

Recorded evidence (per mode) in `artifacts/a_next/registry/<utc>-<mode>/`:
`probe-events.jsonl`, `fake-bridge-requests.jsonl`, `runtime-stdout.log`,
`runtime-stderr.log`, `run-summary.json` (command/UTC/exit/SHA/analysis).

This is an L1 diagnostic. Probe output is same-trust-domain self-report and is
never treated as OS attestation.
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

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[2]
PROBE_PLUGIN = SCRIPT_DIR / "probe_plugin" / "lib" / "index.js"
FAKE_BRIDGE = SCRIPT_DIR / "fake_bridge.py"
FROZEN_PATCH = REPO_ROOT / "config" / "g3d" / "candidate" / "bridge.patch.yml"
FROZEN_DSH_HOME = REPO_ROOT / "artifacts" / "g4" / "runtime" / "dsh-home" / "dsh"
# The original evidence Stage (/tmp/at-f4-clean/artifacts/g3c/stage) was lost in
# INCIDENT_20261121. These candidates are hash-verified recovered copies; if none
# is present, the runner FAILS CLOSED and requires an explicit --stage.
DEFAULT_STAGE_CANDIDATES = (
    REPO_ROOT / "artifacts" / "g3c" / "stage",
    Path("/root/Autonomous Teacher/worktrees/a-next-rrev6/artifacts/g3c/stage"),
)
STAGE_RECOVERY_NOTE = (
    "stage recovered from hash-verified copy (a-next-rrev6 worktree, "
    "INCIDENT_20261121); expected SHAs verified at run start"
)
EXPECTED_STAGE_SHA256 = {
    "runtime/bridge/lib/index.js":
        "2cb424616b7380bff61f8ce760e229a0c1d2b32c4a5f2954cdf66c3937bf74ba",
    "runtime/skill/lib/index.js":
        "521bc0f1126d895de84ebe61fd58c978a5bcae9b4c334f1fd417faee88483b0b",
    "node_modules/@deepseek-ai/dsh-tools/src/index.ts":
        "5d95d7f47781ba001a0116feb61a87bf436f2ca587c01fb4ce517258710b7537",
    "node_modules/@deepseek-ai/dsh-llm/src/index.ts":
        "45f7d934bedb3d72474a384ba75dca7ea2ae4c4439c164b91c87da313ec8970f",
    "node_modules/@deepseek-ai/cordis/package.json":
        "70be1056619663339433309474b1e6a2307088097af3cb082afe4b5ca2021b26",
}
BRIDGE_SOCKET = Path("/work/g3b/bridge.sock")
RUNTIME_CANDIDATES = (
    REPO_ROOT / "artifacts" / "foundation" / "deps" / "deepseek_harness_runtime"
    / "runtime" / "deepseek-harness-sdk-runtime-linux-x64",
    Path("/root/Autonomous Teacher/artifacts/foundation/deps/deepseek_harness_runtime")
    / "runtime" / "deepseek-harness-sdk-runtime-linux-x64",
)
APPROVED_NAME = "skill_lookup"
APPROVED_SHA256 = "c984bef0ae31771da16a12ef2e7972b289cde6014b7f8ad12349f16c4f77b704"
APPROVED = [{"name": APPROVED_NAME, "sha256": APPROVED_SHA256}]

# mode -> (attack, probe mode, attackDelayMs, failAfterRecords, turns, resume)
MODES = {
    "baseline": {"attack": "none", "probe_mode": "observe", "delay": 250,
                 "fail_after": 0, "turns": 1, "resume": False},
    "register-unregister": {"attack": "register_then_unregister", "probe_mode": "observe",
                            "delay": 250, "fail_after": 0, "turns": 1, "resume": False},
    "schema-drift": {"attack": "schema_drift", "probe_mode": "observe",
                     "delay": 250, "fail_after": 0, "turns": 1, "resume": False},
    "duplicate-name": {"attack": "duplicate_name", "probe_mode": "observe",
                       "delay": 250, "fail_after": 0, "turns": 1, "resume": False},
    "internal-execute": {"attack": "internal_execute", "probe_mode": "observe",
                         "delay": 200, "fail_after": 0, "turns": 1, "resume": False},
    "observer-loss": {"attack": "none", "probe_mode": "observe",
                      "delay": 250, "fail_after": 2, "turns": 1, "resume": False},
    "late-bash-before-dispatch": {"attack": "late_extra_bash", "probe_mode": "enforce",
                                  "delay": 250, "fail_after": 0, "turns": 1, "resume": False},
    "two-turn-bash": {"attack": "late_extra_bash_between_turns", "probe_mode": "enforce",
                      "delay": 3000, "fail_after": 0, "turns": 2, "resume": False},
    "two-turn-internal-execute": {"attack": "internal_execute_between_turns",
                                  "probe_mode": "observe", "delay": 3000,
                                  "fail_after": 0, "turns": 2, "resume": False},
    "two-turn-title": {"attack": "none", "probe_mode": "observe",
                       "delay": 250, "fail_after": 0, "turns": 2, "resume": False},
    "resume": {"attack": "none", "probe_mode": "observe",
               "delay": 250, "fail_after": 0, "turns": 1, "resume": True},
}
FAKE_BRIDGE_MODES = {
    "two-turn-bash", "two-turn-internal-execute", "two-turn-title", "resume",
}


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
        if not path.is_file():
            raise FileNotFoundError(f"runtime binary not found: {path}")
        return path
    for candidate in RUNTIME_CANDIDATES:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("frozen DSH 0.2.2-rc.2 runtime binary not found")


def locate_stage(explicit: str = "") -> tuple[Path, dict]:
    """Locate a Stage and verify the frozen build SHAs (fail closed).

    Returns ``(stage, verification)``. A Stage whose bridge/skill/dsh-tools/
    dsh-llm/cordis bytes do not match the frozen evidence SHAs is rejected:
    a recovered copy must be proven, not assumed.
    """
    candidates = [Path(explicit).resolve()] if explicit else [
        candidate.resolve() for candidate in DEFAULT_STAGE_CANDIDATES]
    errors: list[str] = []
    stage: Path | None = None
    for candidate in candidates:
        missing = [required for required in ("runtime/bridge/lib/index.js",
                                             "runtime/skill/lib/index.js")
                   if not (candidate / required).is_file()]
        if missing:
            errors.append(f"{candidate}: missing {missing}")
            continue
        stage = candidate
        break
    if stage is None:
        detail = "; ".join(errors) if errors else "no default candidate"
        raise FileNotFoundError(
            "STAGE_MISSING: no usable Stage found (the original evidence Stage was "
            f"lost in INCIDENT_20261121). Rationale: {detail}. Pass --stage pointing "
            "at a hash-verified recovered copy (expected SHAs are checked).")
    verification = {"stage": str(stage), "expected_sha256": dict(EXPECTED_STAGE_SHA256),
                    "observed_sha256": {}, "verified": True}
    for relative, expected in EXPECTED_STAGE_SHA256.items():
        path = stage / relative
        if not path.is_file():
            raise FileNotFoundError(f"STAGE_INCOMPLETE: missing {relative} in {stage}")
        observed = sha256_file(path)
        verification["observed_sha256"][relative] = observed
        if observed != expected:
            raise ValueError(
                f"STAGE_SHA_MISMATCH: {relative} observed {observed} != frozen {expected} "
                f"in {stage}; refusing to run (fail closed). Recover a hash-verified Stage.")
    verification["stage_recovery_note"] = STAGE_RECOVERY_NOTE
    return stage, verification


def rewrite_frozen_patch(frozen_text: str, stage: Path) -> str:
    bridge = (stage / "runtime" / "bridge" / "lib" / "index.js").as_uri()
    skill = (stage / "runtime" / "skill" / "lib" / "index.js").as_uri()
    text = frozen_text.replace("name: /project/runtime/bridge/lib/index.js", f"name: {bridge}")
    text = text.replace("name: /project/runtime/skill/lib/index.js", f"name: {skill}")
    if text == frozen_text:
        raise ValueError("frozen patch insert paths not found; refusing an unrewritten run")
    return "# A-NEXT A-PR2 TEST-COPY overlay: insert paths rewritten into a temporary Stage.\n" + text


def probe_patch(plugin_path: Path, config: dict) -> str:
    return (
        "# A-NEXT A-PR2 instrumented probe overlay (test copy only; no key, no network).\n"
        "- insert:\n"
        "    - id: a-next-registry-probe\n"
        f"      name: {plugin_path.as_uri()}\n"
        f"      config: {json.dumps(config, sort_keys=True)}\n"
    )


def _ensure_work_dir() -> tuple[Path, bool]:
    """Create /work/g3b for the fixed frozen UDS path; report whether we created /work."""
    if BRIDGE_SOCKET.exists():
        raise RuntimeError(f"refusing to clobber existing {BRIDGE_SOCKET}")
    created_work = False
    if not BRIDGE_SOCKET.parent.parent.exists():
        BRIDGE_SOCKET.parent.parent.mkdir(parents=True)
        created_work = True
    elif not BRIDGE_SOCKET.parent.parent.is_dir():
        raise RuntimeError("/work exists but is not a directory")
    BRIDGE_SOCKET.parent.mkdir(parents=True, exist_ok=True)
    return BRIDGE_SOCKET.parent.parent, created_work


def _cleanup_work_dir(created_work: bool) -> None:
    for path in (BRIDGE_SOCKET, BRIDGE_SOCKET.parent, BRIDGE_SOCKET.parent.parent if created_work else None):
        if path is None:
            continue
        try:
            if path.is_socket() or path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
        except OSError:
            pass


def prepare_dsh_home(workdir: Path) -> tuple[Path, str]:
    dsh_home = workdir / "dshhome"
    dsh_home.mkdir(parents=True, exist_ok=True)
    if FROZEN_DSH_HOME.is_dir() and not (dsh_home / "dsh").is_dir():
        shutil.copytree(FROZEN_DSH_HOME, dsh_home / "dsh", symlinks=False)
        return dsh_home, "copied-from-artifacts/g4/runtime/dsh-home"
    return dsh_home, "fresh-materialised-by-runtime"


def spawn_runtime(command: list[str], cwd: Path, stdout_path: Path, stderr_path: Path,
                  extra_env: dict[str, str]) -> subprocess.Popen[str]:
    env = {"HOME": extra_env["home"], "DSH_HOME": extra_env["dsh_home"],
           "PATH": "/usr/bin:/bin", "TERM": "dumb",
           "G4R_PROBE_OUT": extra_env["probe_out"],
           "G4R_RUN_LABEL": extra_env["run_label"]}
    env.update({key: value for key, value in extra_env.items()
                if key not in ("home", "dsh_home", "probe_out", "run_label")})
    base = ["unshare", "-n", "env", "-i"] + [f"{k}={v}" for k, v in sorted(env.items())]
    return subprocess.Popen(base + command, cwd=str(cwd), stdin=subprocess.PIPE,
                            stdout=stdout_path.open("w", encoding="utf-8"),
                            stderr=stderr_path.open("w", encoding="utf-8"),
                            text=True, bufsize=1)


def send_jsonrpc(proc: subprocess.Popen[str], message: dict) -> None:
    assert proc.stdin is not None
    proc.stdin.write(json.dumps(message) + "\n")
    proc.stdin.flush()


def shutdown_runtime(proc: subprocess.Popen[str], request_id: int = 99) -> None:
    try:
        send_jsonrpc(proc, {"jsonrpc": "2.0", "id": request_id,
                            "method": "shutdown", "params": {}})
        time.sleep(0.3)
    except (BrokenPipeError, OSError):
        pass


def drive_turns(proc: subprocess.Popen[str], turns: int, session_id: str,
                prompt_wait: float, turn_gap: float) -> dict:
    assert proc.stdin is not None
    send_jsonrpc(proc, {
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"cwd": os.getcwd(), "provider": "offline-test-only-g3b",
                   "model": "fixture-bridge-v1"},
    })
    time.sleep(1.2)
    for turn in range(1, turns + 1):
        send_jsonrpc(proc, {
            "jsonrpc": "2.0", "id": 1 + turn, "method": "session/prompt",
            "params": {"sessionId": session_id,
                       "contentBlocks": [{"type": "text",
                                          "text": f"A-NEXT registry attack probe turn {turn}"}]},
        })
        time.sleep(prompt_wait if turn == turns else turn_gap)
    return {"session_id": session_id, "turns": turns}


def drive_resume(proc: subprocess.Popen[str], session_id: str, prompt_wait: float) -> dict:
    assert proc.stdin is not None
    send_jsonrpc(proc, {
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"cwd": os.getcwd(), "provider": "offline-test-only-g3b",
                   "model": "fixture-bridge-v1"},
    })
    time.sleep(1.2)
    send_jsonrpc(proc, {"jsonrpc": "2.0", "id": 2, "method": "session/resume",
                        "params": {"sessionId": session_id}})
    time.sleep(1.0)
    send_jsonrpc(proc, {
        "jsonrpc": "2.0", "id": 3, "method": "session/prompt",
        "params": {"sessionId": session_id,
                   "contentBlocks": [{"type": "text",
                                      "text": "A-NEXT registry attack probe after resume"}]},
    })
    time.sleep(prompt_wait)
    return {"session_id": session_id, "resumed": True}


def read_jsonl(path: Path) -> list[dict]:
    records: list[dict] = []
    if not path.is_file():
        return records
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def parse_stdout_events(stdout_path: Path) -> dict:
    title_sources: list = []
    turn_end_reasons: list = []
    dispatch_denials = 0
    prompt_responses = 0
    if not stdout_path.is_file():
        return {"title_sources": title_sources, "turn_end_reasons": turn_end_reasons}
    for line in stdout_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if '"method":"session.event"' not in line and '"method": "session.event"' not in line:
            if '"id":' in line and '"result"' in line:
                prompt_responses += 1
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        event = ((message.get("params") or {}).get("event") or {})
        if event.get("type") == "session/title":
            data = event.get("data") or {}
            title_sources.append(((data.get("source") or {}).get("kind")))
        if event.get("type") == "turn/end":
            reason = (event.get("data") or {}).get("reason") or {}
            turn_end_reasons.append(reason.get("kind") or reason.get("error", {}).get("message"))
            if "A_NEXT_REGISTRY_TOOL_FACE_DENIED" in json.dumps(reason):
                dispatch_denials += 1
    return {"title_sources": title_sources, "turn_end_reasons": turn_end_reasons,
            "dispatch_denials": dispatch_denials, "prompt_responses": prompt_responses}


def analyse(mode: str, records: list[dict], bridge_records: list[dict],
            sentinel: Path, events: dict, runtime_exit: int, turns: int,
            resume_second: list[dict] | None = None) -> dict:
    snapshots = [r for r in records if r.get("kind") == "registry_snapshot"]
    dispatches = [r for r in records if r.get("kind") == "dispatch_tool_face"]
    attacks = [r for r in records if r.get("kind") == "attack_result"]
    requests = [r for r in bridge_records if r.get("kind") == "request"]
    face_at_dispatch = [d.get("tool_names") for d in dispatches]
    registry_at_dispatch = [d.get("registry_names") for d in dispatches]
    bridge_tool_faces = [request.get("tool_names") for request in requests]
    bridge_has_marker = any("g4r_internal_marker" in (face or []) for face in bridge_tool_faces)
    analyse_result = {
        "runtime_exit_code": runtime_exit,
        "probe_records": len(records),
        "snapshot_count": len(snapshots),
        "dispatch_count": len(dispatches),
        "attack_count": len(attacks),
        "max_epoch": max((int(r.get("epoch") or 0) for r in records), default=0),
        "snapshot_timeline": [
            {"why": snapshot.get("why"), "epoch": snapshot.get("epoch"),
             "definitions": snapshot.get("definitions"),
             "schemas": snapshot.get("schemas")}
            for snapshot in snapshots
        ],
        "dispatch_faces": [
            {"purpose": dispatch.get("purpose"),
             "tool_names": dispatch.get("tool_names"),
             "registry_names": dispatch.get("registry_names"),
             "face_equals_registry": dispatch.get("face_equals_registry"),
             "approved_face": dispatch.get("approved_face"),
             "approved_registry": dispatch.get("approved_registry"),
             "unknown": [item.get("name") for item in dispatch.get("unknown") or []],
             "registry_unknown": [item.get("name") for item in dispatch.get("registry_unknown") or []]}
            for dispatch in dispatches
        ],
        "dispatch_faces_union": sorted({name for face in face_at_dispatch for name in (face or [])}),
        "registry_at_dispatch_union": sorted({name for face in registry_at_dispatch for name in (face or [])}),
        "attacks": [{"step": item.get("step"), "tool": item.get("tool"),
                     "digest": item.get("digest"), "message": item.get("message"),
                     "sentinel_written": item.get("sentinel_written")}
                    for item in attacks],
        "fake_bridge_request_count": len(requests),
        "fake_bridge_tool_faces": bridge_tool_faces,
        "fake_bridge_purposes": [request.get("purpose") for request in requests],
        "fake_bridge_internal_marker_seen": bridge_has_marker,
        "internal_execute_sentinel_written": sentinel.is_file(),
        "internal_execute_sentinel_content": (
            sentinel.read_text(encoding="utf-8").strip() if sentinel.is_file() else None),
        "session_title_sources": events.get("title_sources"),
        "turn_end_reasons": events.get("turn_end_reasons"),
        "enforcement_denial_observed": bool(events.get("dispatch_denials")),
        "prompt_responses": events.get("prompt_responses"),
        "turns_requested": turns,
        "probe_observer_limited": mode == "observer-loss",
        "resume_second_process": resume_second,
    }
    analyse_result["verdicts"] = _matrix_verdicts(mode, analyse_result)
    return analyse_result


def _matrix_verdicts(mode: str, analysis: dict) -> dict:
    """Per-case honest classification derived only from measured facts."""
    dispatch_count = analysis["dispatch_count"]
    if mode == "baseline":
        approved = (dispatch_count >= 1
                    and analysis["dispatch_faces_union"] == [APPROVED_NAME]
                    and all(face.get("approved_face") and face.get("face_equals_registry")
                            for face in analysis["dispatch_faces"]))
        return {"complete-registry-baseline": "MEASURED_PASS" if approved else "FAIL"}
    if mode == "register-unregister":
        appeared = any("g4r_ephemeral" in (snapshot["definitions"] or [])
                       for snapshot in analysis["snapshot_timeline"])
        disappeared = any("g4r_ephemeral" not in (snapshot["definitions"] or [])
                         for snapshot in analysis["snapshot_timeline"])
        clean_face = analysis["dispatch_faces_union"] == [APPROVED_NAME]
        return {"register-then-unregister": "MEASURED_PASS" if (appeared and disappeared and clean_face)
                else "PARTIAL", "revocation-before-dispatch": "MEASURED_PASS" if clean_face else "FAIL"}
    if mode == "schema-drift":
        digests = [item.get("digest") for item in analysis["attacks"] if item.get("digest")]
        return {"schema-required-drift-digest-changed": "MEASURED_PASS" if len(set(digests)) >= 2
                else "UNVERIFIED",
                "schema-description-drift-digest-changed": "MEASURED_PASS" if len(set(digests)) >= 2
                else "UNVERIFIED"}
    if mode == "duplicate-name":
        rejected = any("rejected" in (item.get("step") or "") for item in analysis["attacks"])
        return {"same-name-duplicate": "MEASURED_PASS" if rejected else "FAIL",
                "same-name-shadow": "UNVERIFIED"}
    if mode == "internal-execute":
        executed = analysis["internal_execute_sentinel_written"]
        hidden = "g4r_internal_marker" not in analysis["dispatch_faces_union"]
        not_in_bridge = not analysis["fake_bridge_internal_marker_seen"]
        return {"internal-execute-outside-provider-request":
                "MEASURED_PASS" if (executed and hidden) else "PARTIAL",
                "internal-execute-not-in-bridge-request":
                "MEASURED_PASS" if (executed and not_in_bridge) else "UNVERIFIED"}
    if mode == "observer-loss":
        gap = analysis["probe_records"] <= 2 and analysis["runtime_exit_code"] == 0
        return {"observer-loss-runtime-unaffected": "MEASURED_PASS" if gap else "FAIL",
                "observer-loss-evidence-gap": "MEASURED_PASS" if gap else "PARTIAL"}
    if mode == "late-bash-before-dispatch":
        denied = analysis["enforcement_denial_observed"]
        extra = "bash" in analysis["dispatch_faces_union"]
        return {"late-register-before-dispatch-deny": "MEASURED_PASS" if (denied and extra)
                else "PARTIAL"}
    if mode == "two-turn-bash":
        denied = analysis["enforcement_denial_observed"]
        first_clean = bool(analysis["dispatch_faces"]) and analysis["dispatch_faces"][0].get("approved_face")
        second_has_bash = any("bash" in (face.get("tool_names") or [])
                              for face in analysis["dispatch_faces"][1:])
        bridge_once = analysis["fake_bridge_request_count"] == 1
        return {"second-turn-deny-after-late-register":
                "MEASURED_PASS" if (denied and second_has_bash and first_clean and bridge_once)
                else "PARTIAL",
                "first-turn-only-check-avoided": "MEASURED_PASS" if (first_clean and denied)
                else "PARTIAL"}
    if mode == "two-turn-internal-execute":
        executed = analysis["internal_execute_sentinel_written"]
        faces_clean = all("g4r_internal_marker" not in (face or [])
                          for face in analysis["fake_bridge_tool_faces"])
        return {"late-tool-execute-not-in-provider-request":
                "MEASURED_PASS" if (executed and faces_clean and analysis["dispatch_count"] >= 1)
                else "PARTIAL",
                "two-turn-dispatch-continued": "MEASURED_PASS" if analysis["dispatch_count"] >= 2
                else "PARTIAL"}
    if mode == "two-turn-title":
        title_fallback = "fallback" in (analysis["session_title_sources"] or [])
        no_extra = analysis["dispatch_count"] == analysis["turns_requested"]
        return {"title-no-extra-provider-stream": "MEASURED_PASS" if (title_fallback and no_extra)
                else "PARTIAL",
                "compaction-effective-registry": "UNVERIFIED"}
    if mode == "resume":
        resumed = analysis["resume_second_process"] or {}
        return {"resume-registry-and-dispatch":
                "MEASURED_PASS" if (resumed.get("dispatch_count", 0) >= 1
                                    and analysis["dispatch_faces_union"] == [APPROVED_NAME])
                else "UNVERIFIED"}
    return {mode: "UNVERIFIED"}


def run_mode(mode: str, args: argparse.Namespace) -> dict:
    config = MODES[mode]
    runtime = locate_runtime(args.runtime)
    stage, stage_verification = locate_stage(args.stage)
    run_utc = utc_now()
    run_id = f"{run_utc.replace(':', '').replace('-', '')}-{mode}"
    out_root = Path(args.out).resolve() if args.out else REPO_ROOT / "artifacts" / "a_next" / "registry"
    run_dir = out_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    workdir = Path(tempfile.mkdtemp(prefix="a-next-registry-"))
    probe_out = workdir / "probe-events.jsonl"
    sentinel = workdir / "internal-execute.sentinel"
    home = workdir / "home"
    home.mkdir()
    dsh_home, dsh_home_source = prepare_dsh_home(workdir)
    frozen_text = FROZEN_PATCH.read_text(encoding="utf-8")
    effective_patch = workdir / "frozen-effective.patch.yml"
    effective_patch.write_text(rewrite_frozen_patch(frozen_text, stage), encoding="utf-8")
    plugin_config = {
        "mode": config["probe_mode"], "attack": config["attack"],
        "approved": APPROVED, "attackDelayMs": config["delay"],
        "failAfterRecords": config["fail_after"], "sentinelPath": str(sentinel),
    }
    probe_patch_path = workdir / "probe.patch.yml"
    probe_patch_path.write_text(probe_patch(PROBE_PLUGIN, plugin_config), encoding="utf-8")
    session_id = f"session-{uuid.uuid4().hex}"
    summary: dict = {
        "schema": "a_next.registry.attack.run.v1",
        "run_id": run_id, "mode": mode, "utc": run_utc,
        "runtime_sha256": sha256_file(runtime),
        "stage_dir": str(stage),
        "stage_verification": stage_verification,
        "stage_recovery_note": STAGE_RECOVERY_NOTE,
        "stage_bridge_sha256": sha256_file(stage / "runtime" / "bridge" / "lib" / "index.js"),
        "stage_skill_sha256": sha256_file(stage / "runtime" / "skill" / "lib" / "index.js"),
        "probe_plugin_sha256": sha256_file(PROBE_PLUGIN),
        "frozen_patch_sha256": sha256_file(FROZEN_PATCH),
        "probe_config": plugin_config,
        "network_isolation": "unshare -n (empty network namespace)",
        "key_and_provider_nonuse": {
            "claim": "guaranteed by structural isolation design, not a runtime measurement",
            "guarantees": [
                "env -i with an explicit minimal environment (no inherited secrets)",
                "unshare -n (empty network namespace; no external HTTP/TCP path)",
                "only the synthetic fake_bridge UDS provider is reachable",
                "the runtime is started without any key/credential injection",
            ],
        },
        "fake_bridge": mode in FAKE_BRIDGE_MODES,
        "turns_requested": config["turns"],
        "resume": config["resume"],
        "dsh_home_source": dsh_home_source,
        "session_id": session_id,
    }
    created_work = False
    fake_bridge_proc: subprocess.Popen[str] | None = None
    runtime_proc: subprocess.Popen[str] | None = None
    exit_code = 3
    try:
        bridge_log = run_dir / "fake-bridge-requests.jsonl"
        if summary["fake_bridge"]:
            _work_root, created_work = _ensure_work_dir()
            fake_bridge_proc = subprocess.Popen(
                [sys.executable, str(FAKE_BRIDGE), "--socket", str(BRIDGE_SOCKET),
                 "--out", str(bridge_log)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            for _ in range(100):
                if BRIDGE_SOCKET.exists():
                    break
                time.sleep(0.05)
            if not BRIDGE_SOCKET.exists():
                raise RuntimeError("fake bridge socket was not created")
        common = ["--profile", "sdk-minimal", "--patch", str(effective_patch),
                  "--patch", str(probe_patch_path)]
        stdout_path = run_dir / "runtime-stdout.log"
        stderr_path = run_dir / "runtime-stderr.log"
        env = {"home": str(home), "dsh_home": str(dsh_home),
               "probe_out": str(probe_out), "run_label": run_id}
        summary["command"] = ["unshare", "-n", "env", "-i", "HOME=<tmp>", "DSH_HOME=<tmp>",
                              "PATH=/usr/bin:/bin", "TERM=dumb", f"G4R_PROBE_OUT={probe_out}",
                              f"G4R_RUN_LABEL={run_id}", str(runtime)] + common
        runtime_proc = spawn_runtime([str(runtime)] + common, home, stdout_path, stderr_path, env)
        first_drive = drive_turns(runtime_proc, config["turns"], session_id,
                                  args.prompt_wait, args.turn_gap)
        shutdown_runtime(runtime_proc, request_id=90)
        try:
            runtime_proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            runtime_proc.terminate()
            runtime_proc.wait(timeout=10)
        summary["runtime_exit_code"] = runtime_proc.returncode
        summary["first_process"] = first_drive
        if config["resume"]:
            first_records = read_jsonl(probe_out)
            if first_records:
                shutil.copy2(probe_out, run_dir / "probe-events-process1.jsonl")
                summary["first_process_dispatch_count"] = len(
                    [r for r in first_records if r.get("kind") == "dispatch_tool_face"])
            probe_out.unlink(missing_ok=True)
        resume_second: dict | None = None
        if config["resume"]:
            second_stdout = run_dir / "runtime2-stdout.log"
            second_stderr = run_dir / "runtime2-stderr.log"
            runtime_proc = spawn_runtime([str(runtime)] + common, home, second_stdout,
                                         second_stderr, env)
            second_drive = drive_resume(runtime_proc, session_id, args.prompt_wait)
            shutdown_runtime(runtime_proc, request_id=91)
            try:
                runtime_proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                runtime_proc.terminate()
                runtime_proc.wait(timeout=10)
            second_records = read_jsonl(probe_out)
            second_dispatches = [r for r in second_records if r.get("kind") == "dispatch_tool_face"]
            resume_second = {
                "drive": second_drive,
                "runtime_exit_code": runtime_proc.returncode,
                "probe_records": len(second_records),
                "dispatch_count": len(second_dispatches),
                "dispatch_faces": [d.get("tool_names") for d in second_dispatches],
                "registry_names": [d.get("registry_names") for d in second_dispatches],
            }
            shutil.copy2(probe_out, run_dir / "probe-events-process2.jsonl")
            if second_stdout.is_file():
                shutil.copy2(second_stdout, run_dir / "runtime2-stdout.process2.log")
        if runtime_proc.poll() is None:
            runtime_proc.kill()
            runtime_proc.wait()
        records = read_jsonl(probe_out)
        if records:
            shutil.copy2(probe_out, run_dir / "probe-events.jsonl")
        events = parse_stdout_events(stdout_path)
        if config["resume"] and (run_dir / "runtime2-stdout.log").is_file():
            second_events = parse_stdout_events(run_dir / "runtime2-stdout.log")
            for key, value in second_events.items():
                if isinstance(events.get(key), list):
                    events[key] = (events.get(key) or []) + (value or [])
                elif isinstance(value, int):
                    events[key] = (events.get(key) or 0) + value
        bridge_records = read_jsonl(bridge_log) if summary["fake_bridge"] else []
        analysis = analyse(mode, records, bridge_records, sentinel, events,
                           summary.get("runtime_exit_code", -1), config["turns"],
                           resume_second)
        summary["analysis"] = analysis
        summary["probe_observed"] = bool(records)
        summary["completed_utc"] = utc_now()
        exit_code = 0 if records else 4
    except (FileNotFoundError, ValueError, RuntimeError) as error:
        summary["blocked_reason"] = str(error)
        exit_code = 3
    finally:
        if runtime_proc is not None and runtime_proc.poll() is None:
            runtime_proc.kill()
            runtime_proc.wait()
        if fake_bridge_proc is not None and fake_bridge_proc.poll() is None:
            fake_bridge_proc.terminate()
            try:
                fake_bridge_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                fake_bridge_proc.kill()
        if summary["fake_bridge"]:
            _cleanup_work_dir(created_work)
        summary["exit_code"] = exit_code
        summary["completed_utc"] = utc_now()
        (run_dir / "run-summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if not args.keep_workdir:
            shutil.rmtree(workdir, ignore_errors=True)
    return {"run_dir": str(run_dir), "mode": mode, "exit_code": exit_code,
            "analysis": summary.get("analysis", {}), "summary": summary}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", default="",
                        help="hash-verified recovered candidate Stage (fail closed when omitted and no default candidate exists)")
    parser.add_argument("--runtime", default="")
    parser.add_argument("--mode", default="baseline", choices=sorted(MODES))
    parser.add_argument("--all", action="store_true", help="run the whole matrix sequentially")
    parser.add_argument("--out", default="")
    parser.add_argument("--prompt-wait", type=float, default=3.5)
    parser.add_argument("--turn-gap", type=float, default=3.5)
    parser.add_argument("--keep-workdir", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    modes = list(MODES) if args.all else [args.mode]
    worst = 0
    for mode in modes:
        result = run_mode(mode, args)
        worst = max(worst, result["exit_code"])
        analysis = result.get("analysis") or {}
        print(json.dumps({
            "mode": mode,
            "run_dir": result["run_dir"].split("/")[-1],
            "exit_code": result["exit_code"],
            "probe_records": analysis.get("probe_records"),
            "dispatch_count": analysis.get("dispatch_count"),
            "dispatch_faces_union": analysis.get("dispatch_faces_union"),
            "enforcement_denial": analysis.get("enforcement_denial_observed"),
            "fake_bridge_requests": analysis.get("fake_bridge_request_count"),
            "sentinel_written": analysis.get("internal_execute_sentinel_written"),
            "verdicts": analysis.get("verdicts"),
        }, sort_keys=True))
    return worst


if __name__ == "__main__":
    sys.exit(main())
