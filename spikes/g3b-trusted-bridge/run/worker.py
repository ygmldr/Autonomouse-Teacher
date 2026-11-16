"""G3-B real-DSH worker skeleton (container only; B1-01 path).

Launcher-side ordering: generate fixed configs -> start B2 Controller -> wait
fixed UDS -> start DeepSeekHarness(profile=sdk-minimal, patches=G3-B bridge
config) -> run/resume -> collect SDK events/stderr + Controller/Fake/Broker
evidence. No Key, no HTTP, no model.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import sys
from typing import Any

sys.path.insert(0, "/probe/src")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

EVIDENCE = Path("/evidence")
BASE = Path("/work/g3b")


def emit(kind: str, **data: Any) -> None:
    print(json.dumps({"kind": kind, **data}, sort_keys=True), flush=True)


def dsh_env() -> dict:
    return {
        "PATH": "/opt/python/bin:/usr/bin",
        "HOME": str(BASE / "dsh-home"),
        "PYTHONPATH": "/deps",
        "PYTHONDONTWRITEBYTECODE": "1",
        "TMPDIR": "/tmp",
        "DSH_RUNTIME_MODE": "exe",
        "DSH_RESOURCE_CACHE": "/work/resources",
        "NARB_NATIVE_CACHE_DIR": "/probe/native-cache",
        "PKG_NATIVE_CACHE_PATH": "/probe/pkg-cache",
        "NO_COLOR": "1",
    }


def captured_tool_schemas() -> list[dict]:
    path = EVIDENCE / "capture-tools.json"
    if not path.exists():
        return []
    try:
        doc = json.loads(path.read_text())
    except Exception:
        return []
    return [{"name": item["name"], "sha256": item["sha256"]}
            for item in doc.get("tools", []) if item.get("name") and item.get("sha256")]


def process_snapshot() -> list[dict]:
    rows = []
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        try:
            raw = (proc / "cmdline").read_bytes()
            stat = (proc / "stat").read_text()
            ppid = int(stat.rsplit(")", 1)[1].split()[1])
        except (OSError, ValueError, IndexError):
            continue
        argv = [part.decode("utf-8", "replace") for part in raw.split(b"\0") if part]
        if any("autoteacher_m0.accounting.broker" in arg for arg in argv):
            rows.append({"pid": int(proc.name), "ppid": ppid, "argv": argv})
    return rows


def run_dsh(*, prompt: str = "G3B_B3PREP_ECHO", session_id: str = "g3b-b3prep-session-001",
            resume: bool = False, scenario: str = "ok_usage", guard: bool = False,
            controller_required: bool = True, bad_admission: bool = False,
            guard_invalid: bool = False) -> dict:
    assert os.getuid() == 65534, os.getuid()
    assert not [name for name in os.environ if any(token in name.upper() for token in ("KEY", "TOKEN", "SECRET"))]
    common.write_configs(run_id="g3b-b3prep-" + session_id,
                         scenario=scenario,
                         tool_schemas=captured_tool_schemas())
    if bad_admission:
        (common.BASE / "admission.json").unlink(missing_ok=True)
    (BASE / "dsh-home").mkdir(parents=True, exist_ok=True)
    (BASE / "workspace").mkdir(parents=True, exist_ok=True)
    controller = common.start_controller() if controller_required else None
    started = common.utc()
    try:
        if controller is not None and not bad_admission:
            common.wait_socket()
        from deepseek_harness import DeepSeekHarness  # noqa: E402
        harness = DeepSeekHarness(
            provider="offline-test-only-g3b",
            model="fixture-bridge-v1",
            max_tokens=256,
            profile="sdk-minimal",
            patches=(("/probe/config/bridge.patch.yml", "/probe/config/guard.invalid.patch.yml")
                     if guard_invalid else
                     (("/probe/config/bridge.patch.yml", "/probe/config/guard.precheck.patch.yml")
                      if guard else ("/probe/config/bridge.patch.yml",))),
            dsh_home=str(BASE / "dsh-home"),
            cwd=str(BASE / "workspace"),
            runtime_cwd=str(BASE / "workspace"),
            env=dsh_env(),
            initialize_timeout_seconds=20,
            request_timeout_seconds=30,
            shutdown_timeout_seconds=3,
        )
        result = None
        error = None
        try:
            harness.start()
            if resume:
                session = harness.resume_session(session_id)
                result = session.run(prompt)
            else:
                result = harness.run(prompt, session_id=session_id)
        except Exception as exc:  # noqa: BLE001
            error = {"type": type(exc).__name__, "message": str(exc)}
        finally:
            try:
                harness.close()
            except Exception as exc:  # noqa: BLE001
                if error is None:
                    error = {"type": type(exc).__name__, "message": str(exc)}
        stderr_lines = list(harness.client._stderr_lines) if harness.client is not None else []
        broker_processes = process_snapshot()
        summary = {
            "controller_required": controller_required,
            "bad_admission": bad_admission,
            "stderr_markers": stderr_lines,
            "broker_processes": broker_processes,
            "controller_pid": None if controller is None else controller.pid,
            "final_response": None if result is None else result.final_response,
            "finish_reason": None if result is None else result.finish_reason,
            "session_id": None if result is None else result.session_id,
            "events": [] if result is None else result.events,
            "error": error,
            "started_utc": started,
            "finished_utc": common.utc(),
        }
        evidence = common.collect_evidence(EVIDENCE, label="b3prep-dsh")
        summary["evidence"] = evidence
        return summary
    finally:
        if controller is not None:
            common.stop_controller(controller)


def main() -> int:
    mode = "dsh"
    prompt = "G3B_B3PREP_ECHO"
    scenario = "ok_usage"
    session = "g3b-b3prep-session-001"
    guard = False
    controller_required = True
    bad_admission = False
    guard_invalid = False
    args = sys.argv[1:]
    while args:
        arg = args.pop(0)
        if arg == "--mode":
            mode = args.pop(0)
        elif arg == "--evidence":
            global EVIDENCE
            EVIDENCE = Path(args.pop(0))
        elif arg == "--prompt":
            prompt = args.pop(0)
        elif arg == "--scenario":
            scenario = args.pop(0)
        elif arg == "--session":
            session = args.pop(0)
        elif arg == "--guard":
            guard = True
        elif arg == "--no-controller":
            controller_required = False
        elif arg == "--bad-admission":
            bad_admission = True
        elif arg == "--guard-invalid":
            guard_invalid = True
        else:
            raise SystemExit(f"UNKNOWN_ARG:{arg}")
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    if mode != "dsh":
        raise SystemExit("worker supports only --mode dsh")
    result = run_dsh(prompt=prompt, session_id=session, scenario=scenario, guard=guard, controller_required=controller_required, bad_admission=bad_admission, guard_invalid=guard_invalid)
    (EVIDENCE / "dsh-result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    emit("result", **result)
    return 0 if result.get("error") is None and result.get("final_response") else 1


if __name__ == "__main__":
    raise SystemExit(main())
