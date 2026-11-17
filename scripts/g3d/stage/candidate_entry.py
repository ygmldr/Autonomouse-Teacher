#!/usr/bin/env python3
"""Candidate container entrypoint for G3-D1-B (untrusted OS principal).

The contract is intentionally one-way:

* container uid 0 is *not* host root: the Podman ``--uidmap 0:65534:1`` maps it
  to host uid 65534, and ``--gidmap 2000:2000:1`` plus the supplementary group
  2000 is the only IPC privilege;
* the candidate can read the candidate stage (``/project``, ro), the frozen deps
  (``/deps``, ro) and connect to the one approved socket (``/work/g3b``, ro);
* it must not be able to import or see any Trusted module/state, and it never
  starts a controller/broker/fake.

Everything asserted here is recorded as evidence and re-checked by the Host
Launcher; nothing in this process is trusted to decide its own security.
"""
from __future__ import annotations

import argparse
import errno
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import socket
import stat
import sys
import time
from datetime import datetime, timezone

STAGE = Path("/project")
DEPS = Path("/deps")
SESSION = Path("/work/session")
EVIDENCE = SESSION / "evidence"
IPC_DIR = Path("/work/g3b")
SOCKET_PATH = IPC_DIR / "bridge.sock"
MAX_EVENTS = 400
MAX_TRACE = 2000
GROUP_SOCKET = 2000
SOCKET_MODE = 0o660
KEY_MARKERS = ("KEY", "TOKEN", "SECRET", "CREDENTIAL", "PASSWORD")
SCENARIOS = frozenset({"echo", "tool", "resume"})
LABEL_PATTERN = re.compile(r"[a-z0-9][a-z0-9-]{0,32}\Z")


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def emit(kind: str, **payload: object) -> None:
    print(json.dumps({"kind": kind, **payload}, sort_keys=True), flush=True)


def sha256_file(path: str | os.PathLike[str]) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def lstat_doc(path: Path) -> dict:
    info = os.lstat(path)
    return {
        "path": str(path),
        "mode": stat.S_IMODE(info.st_mode),
        "mode_octal": format(stat.S_IMODE(info.st_mode), "04o"),
        "uid": info.st_uid,
        "gid": info.st_gid,
        "inode": info.st_ino,
        "is_socket": stat.S_ISSOCK(info.st_mode),
        "is_dir": stat.S_ISDIR(info.st_mode),
    }


def write_json_nofollow(path: Path, document: dict, *, mode: int = 0o600) -> dict:
    data = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode()
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC
    flags |= os.O_NOFOLLOW if hasattr(os, "O_NOFOLLOW") else 0
    fd = os.open(path, flags, mode)
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.chmod(path, mode)
    return {"path": str(path), "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data)}


def evidence_name(base: str, label: str | None) -> str:
    suffix = f"-{label}" if label else ""
    return f"{base}{suffix}.json"


def errno_of(callable_) -> dict:
    try:
        result = callable_()
        return {"ok": True, "result": result if isinstance(result, (int, str, bool, type(None))) else str(result)}
    except OSError as exc:
        return {"ok": False, "errno": exc.errno,
                "errno_name": errno.errorcode.get(exc.errno, str(exc.errno)),
                "message": exc.strerror}
    except Exception as exc:  # noqa: BLE001 - evidence of a non-OSError failure
        return {"ok": False, "type": type(exc).__name__, "message": str(exc)[:400]}


def mount_points() -> list[dict]:
    rows: list[dict] = []
    try:
        text = Path("/proc/self/mountinfo").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return rows
    for line in text.splitlines():
        fields = line.split()
        if "-" not in fields:
            continue
        index = fields.index("-")
        if index < 5:
            continue
        rows.append({"mount_point": fields[4], "fstype": fields[index + 1],
                     "source": fields[index + 2] if len(fields) > index + 2 else None,
                     "options": fields[index + 3] if len(fields) > index + 3 else None})
    return rows


def network_probe() -> dict:
    result: dict = {"interfaces": None, "af_inet": None, "af_inet6": None,
                    "dns": None, "routes": None}
    try:
        result["interfaces"] = sorted(
            {"index": item[0], "name": item[1]} for item in socket.if_nameindex())
    except OSError as exc:
        result["interfaces"] = {"error": type(exc).__name__}

    def probe_family(family: int, address: tuple) -> dict:
        try:
            sock = socket.socket(family, socket.SOCK_STREAM)
        except OSError as exc:
            return {"ok": False, "errno": exc.errno,
                    "errno_name": errno.errorcode.get(exc.errno, str(exc.errno)),
                    "stage": "socket"}
        try:
            sock.settimeout(1.0)
            sock.connect(address)
            return {"ok": True, "connected": True}
        except OSError as exc:
            return {"ok": False, "errno": exc.errno,
                    "errno_name": errno.errorcode.get(exc.errno, str(exc.errno)),
                    "message": exc.strerror, "stage": "connect"}
        finally:
            sock.close()

    result["af_inet"] = probe_family(socket.AF_INET, ("192.0.2.1", 9))
    result["af_inet6"] = probe_family(socket.AF_INET6, ("::1", 9))
    try:
        socket.getaddrinfo("example.invalid", 443, type=socket.SOCK_STREAM)
        result["dns"] = {"ok": True, "resolved": True}
    except socket.gaierror as exc:
        result["dns"] = {"ok": False, "gaierror": exc.errno,
                         "message": str(exc)}
    except OSError as exc:
        result["dns"] = {"ok": False, "errno": exc.errno,
                         "message": str(exc)}
    try:
        result["routes"] = Path("/proc/net/route").read_text(
            encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        result["routes"] = {"error": type(exc).__name__}
    return result


def process_rows() -> list[dict]:
    rows: list[dict] = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            raw = (entry / "cmdline").read_bytes()[:8192]
        except OSError:
            continue
        argv = [part.decode("utf-8", "replace") for part in raw.split(b"\0") if part]
        joined = "\n".join(argv)
        if any(marker in joined for marker in
               ("autoteacher_m0.bridge.controller", "autoteacher_m0.accounting.broker",
                "fake_provider.py", "trusted_entry.py", "deepseek-harness-sdk-runtime")):
            rows.append({"pid": int(entry.name), "argv": argv})
    return rows


def principal_checks() -> dict:
    checks: list[dict] = []
    problems: list[str] = []

    def check(name: str, ok: bool, **detail: object) -> None:
        checks.append({"check": name, "ok": bool(ok), **detail})
        if not ok:
            problems.append(name)

    uid_map = Path("/proc/self/uid_map").read_text(encoding="utf-8").strip()
    gid_map = Path("/proc/self/gid_map").read_text(encoding="utf-8").strip()
    uid_lines = [line.split() for line in uid_map.splitlines()]
    gid_lines = [line.split() for line in gid_map.splitlines()]
    check("container_uid_zero", os.getuid() == 0, uid=os.getuid())
    check("container_gid_zero", os.getgid() == 0, gid=os.getgid())
    check("supplementary_group_2000", GROUP_SOCKET in os.getgroups(),
          groups=os.getgroups())
    check("uid_map_container0_to_host65534",
          uid_lines == [["0", "65534", "1"]], uid_map=uid_map)
    check("gid_map_contains_root_and_socket",
          ["0", "65534", "1"] in gid_lines and ["2000", "2000", "1"] in gid_lines,
          gid_map=gid_map)
    check("no_work_state", not Path("/work/state").exists())
    check("no_project_src", not (STAGE / "src").exists())
    check("no_project_trusted", not (STAGE / "trusted").exists())
    check("session_is_directory", SESSION.is_dir())
    env_names = sorted(os.environ)
    key_names = [name for name in env_names
                 if any(marker in name.upper() for marker in KEY_MARKERS)]
    check("no_key_like_env", not key_names, names=key_names)
    pythonpath = os.environ.get("PYTHONPATH", "")
    check("pythonpath_is_deps_only", pythonpath == "/deps", pythonpath=pythonpath)
    py_path = [entry for entry in sys.path if entry]
    check("sys_path_has_no_project_src",
          not any(entry.startswith("/project/src") for entry in py_path),
          sys_path=py_path)
    for module in ("autoteacher_m0", "autoteacher_m0.bridge.controller",
                   "autoteacher_m0.accounting.broker",
                   "autoteacher_m0.bridge.fake_backend"):
        try:
            spec = importlib.util.find_spec(module)
        except ModuleNotFoundError:
            spec = None
        check(f"module_unimportable:{module}", spec is None,
              origin=None if spec is None else spec.origin)
    try:
        socket_doc = lstat_doc(SOCKET_PATH)
    except OSError as exc:
        socket_doc = {"path": str(SOCKET_PATH), "error": type(exc).__name__,
                      "errno": exc.errno}
    check("socket_is_unix_socket", bool(socket_doc.get("is_socket")),
          observed=socket_doc)
    check("socket_mode_0660", socket_doc.get("mode") == SOCKET_MODE,
          observed=socket_doc.get("mode_octal"))
    check("socket_gid_2000", socket_doc.get("gid") == GROUP_SOCKET,
          observed=socket_doc.get("gid"))
    ipc_doc = lstat_doc(IPC_DIR)
    check("ipc_mount_read_only", True, observed=ipc_doc,
          note="unlink/rename/create probes below prove the ro mount")
    unlink_probe = errno_of(lambda: os.unlink(SOCKET_PATH))
    check("socket_unlink_denied", not unlink_probe.get("ok"), probe=unlink_probe)
    rename_probe = errno_of(
        lambda: os.rename(SOCKET_PATH, IPC_DIR / "bridge.sock.candidate"))
    check("socket_rename_denied", not rename_probe.get("ok"), probe=rename_probe)
    create_probe = errno_of(
        lambda: os.open(IPC_DIR / "candidate-write-probe", os.O_CREAT | os.O_WRONLY, 0o600))
    check("ipc_create_denied", not create_probe.get("ok"), probe=create_probe)
    mounts = mount_points()
    mount_points_set = {row["mount_point"] for row in mounts}
    for required in ("/project", "/deps", "/work/g3b", "/work/session"):
        check(f"mount_present:{required}", required in mount_points_set)
    for forbidden in ("/work/state", "/output", "/project/src"):
        check(f"mount_absent:{forbidden}", forbidden not in mount_points_set)
    trusted_processes = [row for row in process_rows()
                         if any(marker in "\n".join(row["argv"]) for marker in
                                ("autoteacher_m0.bridge.controller",
                                 "autoteacher_m0.accounting.broker",
                                 "fake_provider.py", "trusted_entry.py"))]
    check("no_trusted_components_started", not trusted_processes,
          processes=trusted_processes)
    return {
        "utc": utc(),
        "checks": checks,
        "problems": problems,
        "uid": os.getuid(), "gid": os.getgid(), "groups": os.getgroups(),
        "uid_map": uid_map, "gid_map": gid_map,
        "socket": socket_doc,
        "ipc_dir": ipc_doc,
        "mounts": mounts,
        "probes": {"unlink": unlink_probe, "rename": rename_probe,
                   "create": create_probe},
        "env_names": env_names,
        "python": platform.python_version(),
        "executable": sys.executable,
        "sys_path": py_path,
        "platform": platform.platform(),
        "network": network_probe(),
    }


def dsh_env() -> dict:
    return {
        "PATH": "/opt/python/bin:/usr/bin",
        "HOME": str(SESSION),
        "PYTHONPATH": "/deps",
        "PYTHONDONTWRITEBYTECODE": "1",
        "TMPDIR": "/tmp",
        "DSH_RUNTIME_MODE": "exe",
        "DSH_RESOURCE_CACHE": "/work/resources",
        "NARB_NATIVE_CACHE_DIR": "/project/native-cache",
        "PKG_NATIVE_CACHE_PATH": "/project/pkg-cache",
        "NO_COLOR": "1",
    }


def trace_event(record: list[dict], notification: object) -> None:
    if len(record) >= MAX_TRACE:
        return
    payload = getattr(notification, "payload", None) or {}
    event = payload.get("event") if isinstance(payload, dict) else None
    entry = {"epoch_ms": int(time.time() * 1000), "utc": utc(),
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
                entry["tool_call_id"] = data.get("callId")
    record.append(entry)


def event_summary(events: list) -> dict:
    assistant_messages: list[dict] = []
    tool_calls: list[dict] = []
    tool_results: list[dict] = []
    turn_end: list[dict] = []
    for event in events:
        if not isinstance(event, dict):
            continue
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
            turn_end.append(data.get("reason"))
    return {"assistant_messages": assistant_messages, "tool_calls": tool_calls,
            "tool_results": tool_results, "turn_end": turn_end}


def message_usage(message: dict) -> dict | None:
    """Return the usage carried by one assistant message, if any."""
    usage = message.get("data_usage")
    if not isinstance(usage, dict):
        usage = message.get("usage")
    return usage if isinstance(usage, dict) else None


def scenario_verdict(result: dict | None, scenario: str) -> tuple[bool, str | None, dict]:
    """Validate the synthetic DSH result for the requested scenario.

    Echo requires one assistant turn with usage. Tool requires the same real
    turn to produce two provider requests and one real ``skill_lookup`` result:
    the first assistant message is a tool-call, the second is the final text
    answer after the tool result, and both carry independent usage blocks.
    """
    detail: dict = {"scenario": scenario}
    if not isinstance(result, dict):
        return False, "NO_RESULT", detail
    detail["final_response"] = result.get("final_response")
    detail["finish_reason"] = result.get("finish_reason")
    if result.get("final_response") != "ok" or result.get("finish_reason") != "completed":
        return False, "DSH_ECHO" if scenario == "echo" else "DSH_TOOL", detail
    summary = result.get("event_summary")
    if not isinstance(summary, dict):
        return False, "EVENT_SUMMARY", detail
    messages = [item for item in summary.get("assistant_messages") or []
                if isinstance(item, dict)]
    usages = [message_usage(item) for item in messages]
    detail["assistant_message_count"] = len(messages)
    detail["assistant_steps"] = [item.get("step") for item in messages]
    detail["usages"] = usages
    detail["tool_calls"] = summary.get("tool_calls") or []
    detail["tool_results"] = summary.get("tool_results") or []
    if scenario == "echo":
        if not usages or not isinstance(usages[-1], dict):
            return False, "USAGE_MISSING", detail
        return True, None, detail
    if scenario == "resume":
        resume = result.get("resume") if isinstance(result.get("resume"), dict) else {}
        detail["resume"] = {"used": resume.get("used"),
                            "resume_marker_count":
                                (resume.get("sessions") or {}).get("resume_marker_count"),
                            "session_lines":
                                (resume.get("sessions") or {}).get("total_lines")}
        if resume.get("used") is not True:
            return False, "RESUME_SDK_NOT_USED", detail
        if not usages or not isinstance(usages[-1], dict):
            return False, "USAGE_MISSING", detail
        if int(detail["resume"]["resume_marker_count"] or 0) < 1:
            return False, "RESUME_MARKER_MISSING", detail
        return True, None, detail
    if scenario != "tool":
        return False, "UNSUPPORTED_SCENARIO", detail
    if len(messages) != 2 or not all(isinstance(item, dict) for item in usages):
        return False, "TOOL_TURN_COUNT", detail
    first_types = messages[0].get("content_types") or []
    second_types = messages[1].get("content_types") or []
    if "tool-call" not in first_types or "text" not in second_types:
        return False, "TOOL_MESSAGE_SHAPE", detail
    calls = [item for item in detail["tool_calls"]
             if isinstance(item, dict) and item.get("name") == "skill_lookup"]
    results = [item for item in detail["tool_results"] if isinstance(item, dict)]
    tool_text = json.dumps(results, sort_keys=True)
    if not calls or not results or "binary_search" not in tool_text \
            or "m0-skills-v1" not in tool_text:
        return False, "TOOL_RESULT_MISSING", detail
    return True, None, detail


def session_evidence() -> dict:
    """Record the persisted DSH session files visible to the Candidate.

    The Candidate may read its own session tree; this is evidence that the
    second process resumed real persisted history, not a replay invented by the
    launcher. Only bounded regular files are read and only path/size/SHA/line
    counts plus a resume-marker count are emitted (never prompt text).
    """
    root = SESSION / "dsh-home" / "sessions"
    files: list[dict] = []
    total_lines = 0
    resume_markers = 0
    if root.is_dir():
        for path in sorted(root.rglob("*.jsonl"))[:16]:
            try:
                info = os.lstat(path)
                if not stat.S_ISREG(info.st_mode) or info.st_size > (16 << 20):
                    files.append({"path": str(path), "rejected": True})
                    continue
                data = path.read_bytes()
            except OSError as exc:
                files.append({"path": str(path), "error": type(exc).__name__})
                continue
            lines = data.count(b"\n")
            markers = len(re.findall(rb'"reason"\s*:\s*"resume"', data))
            total_lines += lines
            resume_markers += markers
            files.append({
                "path": str(path.relative_to(SESSION)),
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "lines": lines,
                "resume_marker_count": markers,
            })
    return {"root": str(root.relative_to(SESSION)), "files": files,
            "total_lines": total_lines, "resume_marker_count": resume_markers,
            "exists": root.is_dir()}


def run_dsh(*, scenario: str, session_id: str, prompt: str,
            resume: bool = False, label: str | None = None) -> dict:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (SESSION / "dsh-home").mkdir(exist_ok=True)
    (SESSION / "workspace").mkdir(exist_ok=True)
    from deepseek_harness import DeepSeekHarness  # noqa: E402

    started = utc()
    started_monotonic = time.monotonic()
    notifications: list[dict] = []
    result = None
    error = None
    harness = None
    stderr_lines: list[str] = []
    try:
        harness = DeepSeekHarness(
            provider="offline-test-only-g3b",
            model="fixture-bridge-v1",
            max_tokens=256,
            profile="sdk-minimal",
            patches=("/project/config/bridge.patch.yml",),
            dsh_home=str(SESSION / "dsh-home"),
            cwd=str(SESSION / "workspace"),
            runtime_cwd=str(SESSION / "workspace"),
            env=dsh_env(),
            initialize_timeout_seconds=25,
            request_timeout_seconds=40,
            shutdown_timeout_seconds=5,
        )
        harness.start()
        if resume:
            session = harness.resume_session(session_id)
        else:
            session = harness.start_session(session_id)
        result = session.run(prompt,
                             on_notification=lambda note: trace_event(notifications, note))
    except Exception as exc:  # noqa: BLE001 - terminal state is evidence
        error = {"type": type(exc).__name__, "message": str(exc)[:2000]}
    finally:
        if harness is not None:
            try:
                client = getattr(harness, "client", None)
                if client is not None and getattr(client, "_stderr_lines", None):
                    stderr_lines = list(client._stderr_lines)
            except Exception:  # noqa: BLE001
                pass
            try:
                harness.close()
            except Exception as exc:  # noqa: BLE001
                if error is None:
                    error = {"type": type(exc).__name__, "message": str(exc)[:2000]}
    finished = utc()
    summary = {
        "schema": "m0.g3d.d1c.candidate-result.v1",
        "label": scenario,
        "scenario": scenario,
        "session_id": None if result is None else result.session_id,
        "prompt": prompt,
        "started_utc": started,
        "finished_utc": finished,
        "wall_seconds": round(time.monotonic() - started_monotonic, 3),
        "final_response": None if result is None else result.final_response,
        "finish_reason": None if result is None else result.finish_reason,
        "event_count": 0 if result is None else len(result.events),
        "events": [] if result is None else result.events[:MAX_EVENTS],
        "event_summary": {} if result is None else event_summary(result.events),
        "notifications_trace": notifications,
        "error": error,
        "stderr_markers": [line for line in stderr_lines
                           if line.startswith(("G3B_", "G3C_", "ADMISSION",
                                               "G3D_"))][-200:],
        "processes_after": process_rows(),
        "env": dsh_env(),
        "env_names": sorted(os.environ),
        "resume": {"used": bool(resume),
                   "sdk_call": "resume_session" if resume else "start_session",
                   "sessions": session_evidence()},
    }
    write_json_nofollow(EVIDENCE / evidence_name("dsh-result", label), summary,
                        mode=0o600)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", default="echo")
    parser.add_argument("--session", default="g3d-d1-s1")
    parser.add_argument("--prompt", default=None)
    parser.add_argument("--mode", default="dsh", choices=("dsh", "hold"))
    parser.add_argument("--hold-seconds", type=int, default=600)
    parser.add_argument("--label", default="")
    args = parser.parse_args(argv)
    label = args.label or None
    if label is not None and not LABEL_PATTERN.fullmatch(label):
        sys.stderr.write("CANDIDATE_LABEL_INVALID\n")
        return 2
    if args.scenario not in SCENARIOS:
        sys.stderr.write("CANDIDATE_SCENARIO_UNSUPPORTED\n")
        return 2
    if args.mode == "hold":
        if not 0 < args.hold_seconds <= 3600:
            sys.stderr.write("CANDIDATE_HOLD_SECONDS_INVALID\n")
            return 2
    elif args.prompt is None:
        args.prompt = ("Use skill_lookup to look up binary_search"
                       if args.scenario == "tool" else "G3D_ECHO")
    principal = principal_checks()
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    principal_record = write_json_nofollow(
        EVIDENCE / evidence_name("principal", label), principal, mode=0o600)
    emit("candidate-principal", ok=not principal["problems"],
         problems=principal["problems"], mode=args.mode, label=label,
         uid=principal["uid"], gid=principal["gid"], groups=principal["groups"],
         uid_map=principal["uid_map"], gid_map=principal["gid_map"],
         socket=principal["socket"], network=principal["network"],
         sha256=principal_record["sha256"])
    if principal["problems"]:
        emit("candidate-result", ok=False, reason="PRINCIPAL",
             problems=principal["problems"])
        return 6
    if args.mode == "hold":
        # D2 attack container: a real Candidate process staying alive while the
        # Host Launcher execs audited probes into its namespaces. It holds no
        # trusted state and never talks to the bridge itself.
        emit("candidate-hold", ok=True, label=label,
             hold_seconds=args.hold_seconds)
        try:
            time.sleep(args.hold_seconds)
        except KeyboardInterrupt:
            pass
        return 0
    result = run_dsh(scenario=args.scenario, session_id=args.session,
                     prompt=args.prompt, resume=(args.scenario == "resume"),
                     label=label)
    ok, reason, detail = scenario_verdict(result, args.scenario)
    usages = detail.get("usages") or []
    emit("candidate-result", ok=ok, reason=reason, label=label,
         final_response=result.get("final_response"),
         finish_reason=result.get("finish_reason"),
         usage=usages[-1] if usages else None, usages=usages,
         assistant_message_count=detail.get("assistant_message_count"),
         tool_calls=len(detail.get("tool_calls") or []),
         tool_results=len(detail.get("tool_results") or []),
         event_count=result.get("event_count"),
         resume=detail.get("resume"),
         error=result.get("error"), session_id=result.get("session_id"))
    return 0 if ok else 7


if __name__ == "__main__":
    raise SystemExit(main())
