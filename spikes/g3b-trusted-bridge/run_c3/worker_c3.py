"""G3-C real-DSH worker (container only, fixed rootfs, no Key/network).

Real ``DeepSeekHarness`` (profile ``sdk-minimal``) receives the third-party
Cordis bridge adapter built from ``spikes/g3b-trusted-bridge/src``. The worker
starts a real Controller/Broker/Fake child tree over the frozen AF_UNIX path,
runs one Echo / Tool / Resume turn (or a negative scenario), and records SDK
events, notification timings, stderr markers, Controller/Fake/Broker/Attempt
evidence.

This file is *not* evidence that the host-side integration works; it runs only
inside the fixed rootfs with ``--network none``.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import threading
import time
from typing import Any

sys.path.insert(0, "/probe/src")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import common_c3 as common  # noqa: E402

EVIDENCE = Path("/evidence")
BASE = Path("/work/g3b")
MAX_EVENTS = 400
MAX_TRACE = 2000


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
    path = Path("/probe/fixtures/capture-tools.json")
    if not path.exists():
        return []
    try:
        document = json.loads(path.read_text())
    except Exception:
        return []
    return [{"name": item["name"], "sha256": item["sha256"]}
            for item in document.get("tools", [])
            if item.get("name") and item.get("sha256")]


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
        if any("autoteacher_m0.accounting.broker" in arg for arg in argv) or \
                any("fake_provider.py" in arg for arg in argv) or \
                any("deepseek-harness-sdk-runtime" in arg for arg in argv):
            rows.append({"pid": int(proc.name), "ppid": ppid, "argv": argv})
    return rows


def dsh_processes() -> list[dict]:
    rows = []
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        try:
            raw = (proc / "cmdline").read_bytes()
        except OSError:
            continue
        argv = [part.decode("utf-8", "replace") for part in raw.split(b"\0") if part]
        if any("deepseek-harness-sdk-runtime" in arg for arg in argv):
            rows.append({"pid": int(proc.name), "argv": argv})
    return rows


def trace_event(record: list[dict], notification: Any) -> None:
    if len(record) >= MAX_TRACE:
        return
    payload = getattr(notification, "payload", None) or {}
    event = payload.get("event") if isinstance(payload, dict) else None
    entry = {"epoch_ms": int(time.time() * 1000), "utc": common.utc(),
             "method": getattr(notification, "method", None)}
    if isinstance(event, dict):
        entry["event_type"] = event.get("type")
        data = event.get("data")
        if isinstance(data, dict):
            if event.get("type") == "assistant/message":
                message = data.get("message")
                if isinstance(message, dict) and isinstance(message.get("usage"), dict):
                    entry["usage"] = message["usage"]
                stream = data.get("stream")
                if isinstance(stream, list):
                    entry["stream_time0"] = [
                        item.get("time0") for item in stream
                        if isinstance(item, dict) and item.get("time0") is not None]
            if event.get("type") == "tool/result":
                message = data.get("message")
                entry["tool_call_id"] = data.get("callId")
                if isinstance(message, dict):
                    entry["tool_content"] = str(message.get("content"))[:500]
    record.append(entry)


def dsh_events_summary(events: list[dict]) -> dict:
    usages = []
    assistant_messages = []
    tool_calls = []
    tool_results = []
    for event in events:
        kind = event.get("type")
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        if kind == "assistant/message":
            message = data.get("message") if isinstance(data.get("message"), dict) else {}
            record = {"step": data.get("step"), "turn": data.get("turn"),
                      "content_types": [block.get("type") for block in
                                        (message.get("content") or [])
                                        if isinstance(block, dict)]}
            if isinstance(message.get("usage"), dict):
                record["usage"] = message["usage"]
            if isinstance(data.get("usage"), dict):
                record["data_usage"] = data["usage"]
            assistant_messages.append(record)
            for block in message.get("content") or []:
                if isinstance(block, dict) and block.get("type") == "tool-call":
                    tool_calls.append({"step": data.get("step"),
                                       "id": block.get("id"), "name": block.get("name"),
                                       "arguments": block.get("arguments")})
        elif kind == "tool/result":
            message = data.get("message") if isinstance(data.get("message"), dict) else {}
            tool_results.append({"step": data.get("step"), "callId": data.get("callId"),
                                 "content": message.get("content")})
        elif kind == "turn/end":
            usages.append({"turn_end": data.get("reason")})
    return {"assistant_messages": assistant_messages, "tool_calls": tool_calls,
            "tool_results": tool_results, "turn_end": usages}


def run_dsh(*, label: str, prompt: str = "G3C_ECHO", session_id: str = "g3c-session-001",
            resume: bool = False, scenario: str = "ok_usage", guard: bool = False,
            guard_invalid: bool = False, controller_required: bool = True,
            bad_admission: bool = False, seed: str | None = None,
            run_id: str | None = None, limits: dict | None = None,
            kill_after_ms: int | None = None, trace: bool = True) -> dict:
    assert os.getuid() == 65534, os.getuid()
    assert not [name for name in os.environ
                if any(token in name.upper() for token in ("KEY", "TOKEN", "SECRET"))]
    common.EVIDENCE.mkdir(parents=True, exist_ok=True)
    if seed:
        seed_path = Path(seed)
        for path in seed_path.rglob("*"):
            if path.is_file():
                target = common.BASE / path.relative_to(seed_path)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(path.read_bytes())
    config = common.write_configs(run_id=run_id or label, scenario=scenario,
                                  limits=limits, tool_schemas=captured_tool_schemas())
    if bad_admission:
        (common.BASE / "admission.json").unlink(missing_ok=True)
    (BASE / "dsh-home").mkdir(parents=True, exist_ok=True)
    (BASE / "workspace").mkdir(parents=True, exist_ok=True)
    controller = common.start_controller() if controller_required else None
    started = common.utc()
    started_monotonic = time.monotonic()
    notifications_trace: list[dict] = []
    stderr_monitor: list[dict] = []
    killed: dict = {}
    result = None
    error = None
    harness = None
    try:
        if controller is not None and not bad_admission:
            try:
                common.wait_socket()
            except Exception as exc:  # controller failed to start (bad admission)
                error = {"type": type(exc).__name__, "message": str(exc)}
        from deepseek_harness import DeepSeekHarness  # noqa: E402
        patches = ("/probe/config/bridge.patch.yml",)
        if guard or guard_invalid:
            patches = ("/probe/config/bridge.patch.yml",
                       "/probe/config/guard.invalid.patch.yml" if guard_invalid
                       else "/probe/config/guard.precheck.patch.yml")
        harness = DeepSeekHarness(
            provider="offline-test-only-g3b", model="fixture-bridge-v1",
            max_tokens=256, profile="sdk-minimal", patches=patches,
            dsh_home=str(BASE / "dsh-home"), cwd=str(BASE / "workspace"),
            runtime_cwd=str(BASE / "workspace"), env=dsh_env(),
            initialize_timeout_seconds=25, request_timeout_seconds=40,
            shutdown_timeout_seconds=5,
        )
        if error is None:
            try:
                harness.start()
                callback = ((lambda notification: trace_event(notifications_trace, notification))
                        if trace else None)
                if kill_after_ms is not None:
                    client = harness.client
                    proc = getattr(client, "_proc", None)
                    pid = None if proc is None else proc.pid

                    def _kill() -> None:
                        time.sleep(max(kill_after_ms, 1) / 1000.0)
                        if pid is not None:
                            killed["pid"] = pid
                            killed["utc"] = common.utc()
                            killed["epoch_ms"] = int(time.time() * 1000)
                            try:
                                os.kill(pid, 15)
                            except OSError as exc:
                                killed["error"] = type(exc).__name__

                    thread = threading.Thread(target=_kill, name="g3c-sigterm", daemon=True)
                    thread.start()
                if resume:
                    session = harness.resume_session(session_id)
                    result = session.run(prompt, on_notification=callback)
                else:
                    result = harness.run(prompt, session_id=session_id,
                                         on_notification=callback)
            except Exception as exc:  # noqa: BLE001 - terminal state is evidence
                error = {"type": type(exc).__name__, "message": str(exc)[:2000]}
            finally:
                try:
                    harness.close()
                except Exception as exc:  # noqa: BLE001
                    if error is None:
                        error = {"type": type(exc).__name__, "message": str(exc)[:2000]}
        if harness is not None and harness.client is not None:
            stderr_monitor = list(harness.client._stderr_lines)
    finally:
        if controller is not None:
            common.stop_controller(controller)
    finished = common.utc()
    wall = round(time.monotonic() - started_monotonic, 3)
    snapshot = common.broker_and_attempts_snapshot()
    log_info = common.trace_controller_log(EVIDENCE)
    summary = {
        "label": label, "mode": "resume" if resume else "run",
        "prompt": prompt, "session_id": session_id if result is None else result.session_id,
        "scenario": scenario, "guard": guard, "guard_invalid": guard_invalid,
        "controller_required": controller_required, "bad_admission": bad_admission,
        "run_id": run_id or label, "limits": config.get("limits"),
        "admission_id": config.get("admission_id"),
        "started_utc": started, "finished_utc": finished, "wall_seconds": wall,
        "started_epoch_ms": int(time.time() * 1000 - wall * 1000),
        "killed": killed,
        "controller_exit": None if controller is None else controller.poll(),
        "controller_log": log_info,
        "dsh_processes_after": dsh_processes(),
        "broker_processes_after": process_snapshot(),
        "stderr_markers": [line for line in stderr_monitor
                           if line.startswith(("G3B_", "G3C_", "ADMISSION"))][-200:],
        "final_response": None if result is None else result.final_response,
        "finish_reason": None if result is None else result.finish_reason,
        "result_session_id": None if result is None else result.session_id,
        "error": error,
        "events": [] if result is None else result.events[:MAX_EVENTS],
        "event_count": 0 if result is None else len(result.events),
        "event_summary": {} if result is None else dsh_events_summary(result.events),
        "notifications_trace": notifications_trace,
        "db": snapshot,
        "correlation": common.correlation_rows(),
        "env": common.env_snapshot(),
    }
    common.write_json(EVIDENCE / "dsh-result.json", summary)
    evidence = common.collect_work(EVIDENCE, label=label,
                                   extra={"dsh_result": "dsh-result.json"})
    summary["evidence"] = {"files": len(evidence["files"]),
                           "db": evidence["db"]}
    emit("result", **summary)
    return summary


def parse_limits(value: str | None) -> dict | None:
    if not value:
        return None
    document = json.loads(value)
    if not isinstance(document, dict):
        raise SystemExit("LIMITS_INVALID")
    return document


def main() -> int:
    global EVIDENCE
    options = {"label": "echo", "prompt": "G3C_ECHO", "session_id": "g3c-session-001",
               "scenario": "ok_usage", "guard": False, "guard_invalid": False,
               "controller_required": True, "bad_admission": False, "seed": None,
               "resume": False, "run_id": None, "limits": None,
               "kill_after_ms": None, "trace": True}
    args = sys.argv[1:]
    while args:
        arg = args.pop(0)
        if arg == "--label":
            options["label"] = args.pop(0)
        elif arg == "--evidence":
            EVIDENCE = Path(args.pop(0))
            common.EVIDENCE = EVIDENCE
        elif arg == "--prompt":
            options["prompt"] = args.pop(0)
        elif arg == "--scenario":
            options["scenario"] = args.pop(0)
        elif arg == "--session":
            options["session_id"] = args.pop(0)
        elif arg == "--guard":
            options["guard"] = True
        elif arg == "--guard-invalid":
            options["guard_invalid"] = True
        elif arg == "--no-controller":
            options["controller_required"] = False
        elif arg == "--bad-admission":
            options["bad_admission"] = True
        elif arg == "--seed":
            options["seed"] = args.pop(0)
        elif arg == "--resume":
            options["resume"] = True
        elif arg == "--run-id":
            options["run_id"] = args.pop(0)
        elif arg == "--limits":
            options["limits"] = parse_limits(args.pop(0))
        elif arg == "--kill-after-ms":
            options["kill_after_ms"] = int(args.pop(0))
        elif arg == "--no-trace":
            options["trace"] = False
        else:
            raise SystemExit(f"UNKNOWN_ARG:{arg}")
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    run_dsh(**options)
    return 0 if (EVIDENCE / "dsh-result.json").exists() else 1


if __name__ == "__main__":
    raise SystemExit(main())
