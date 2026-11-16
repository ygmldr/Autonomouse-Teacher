"""G3-A bridge evidence worker. Execute ONLY inside the fixed no-Key container."""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
import time

CASE = json.loads(sys.argv[1])["case"]
BASE = f"/work/g3a/{'echo' if CASE == 'recall' else CASE}"
ENV = {
    "PATH": "/opt/python/bin:/usr/bin",
    "HOME": f"{BASE}/home",
    "PYTHONPATH": "/deps",
    "PYTHONDONTWRITEBYTECODE": "1",
    "TMPDIR": "/tmp",
    "DSH_RUNTIME_MODE": "exe",
    "DSH_RESOURCE_CACHE": "/work/resources",
    "NARB_NATIVE_CACHE_DIR": "/probe/native-cache",
    "PKG_NATIVE_CACHE_PATH": "/probe/pkg-cache",
    "NO_COLOR": "1",
    "AUTOTEACHER_G3A_BRIDGE": "1",
    "G3A_BRIDGE_PYTHON": "/opt/python/bin/python3.11",
    "G3A_BRIDGE_FAKE": "/probe/bridge/fake_provider.py",
    "G3A_BRIDGE_TRACE_DIR": f"{BASE}/bridge",
    "G3A_BRIDGE_RECEIPT_DIR": f"{BASE}/fake",
    "G3A_BRIDGE_TIMEOUT_MS": "15000",
}
assert set(os.environ) <= set(ENV) | {"HOSTNAME"}, sorted(os.environ)
os.environ.clear()
os.environ.update(ENV)
from deepseek_harness import DeepSeekHarness  # noqa: E402

Path(f"{BASE}/home").mkdir(parents=True, exist_ok=True)
Path(f"{BASE}/workspace").mkdir(parents=True, exist_ok=True)


def emit(kind: str, **data: object) -> None:
    print(json.dumps({"kind": kind, **data}, sort_keys=True), flush=True)


def utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def collect_tree(root: str) -> list[dict]:
    base = Path(root)
    if not base.exists():
        return []
    files = []
    for path in sorted(base.rglob("*")):
        if not path.is_file():
            continue
        payload = path.read_bytes()
        item = {
            "path": str(path),
            "sha256": sha256(payload),
            "bytes": len(payload),
            "base64": base64.b64encode(payload).decode(),
        }
        if path.suffix == ".json":
            try:
                item["json"] = json.loads(payload)
            except json.JSONDecodeError:
                pass
        files.append(item)
    return files


params = {"home": f"{BASE}/home", "workspace": f"{BASE}/workspace", "dsh_home": f"{BASE}/dsh-home"}
started = utc()
harness = DeepSeekHarness(
    provider="g3a-bridge-test",
    model="bridge-v1",
    max_tokens=256,
    profile="sdk-minimal",
    patches=("/probe/config/bridge.patch.yml",),
    dsh_home=params["dsh_home"],
    cwd=params["workspace"],
    runtime_cwd=params["workspace"],
    env=dict(ENV),
    initialize_timeout_seconds=15,
    request_timeout_seconds=10,
    shutdown_timeout_seconds=2,
)
result = None
error = None
cancel_ready = threading.Event()
runtime_pid = None
fake_pid = None
watch_stop = threading.Event()


def watch_bridge() -> None:
    global fake_pid
    deadline = time.monotonic() + 10
    while not watch_stop.wait(0.01) and time.monotonic() < deadline:
        for line in list(harness.client._stderr_lines):
            # READY only proves the child spawned; STREAMING proves the request
            # crossed the pipe and the external fake emitted its first chunk.
            if not line.startswith("G3A_BRIDGE_STREAMING "):
                continue
            try:
                marker = json.loads(line.split(" ", 1)[1])
            except (json.JSONDecodeError, IndexError):
                continue
            fake_pid = marker.get("childPid")
            emit("cancel-ready", runtime_pid=runtime_pid, fake_pid=fake_pid, request_id=marker.get("requestId"),
                 first_chunk=marker.get("firstChunk"))
            cancel_ready.set()
            return


try:
    harness.start()
    proc = harness.client._proc
    assert proc is not None and proc.poll() is None
    runtime_pid = proc.pid
    emit("ready", case=CASE, runtime_pid=runtime_pid, utc=started)
    prompts = {
        "echo": ("run", "g3a-echo", "G3A_ECHO nonce=G3A_PUBLIC_ECHO_a7f3"),
        "recall": ("resume", "g3a-echo", "G3A_RECALL"),
        "tool": ("run", "g3a-tool", "G3A_TOOL"),
        "eof": ("run", "g3a-eof", "G3A_EOF"),
        "error": ("run", "g3a-error", "G3A_ERROR"),
        "cancel": ("run", "g3a-cancel", "G3A_CANCEL"),
    }
    op, session_id, prompt = prompts[CASE]
    if CASE == "cancel":
        threading.Thread(target=watch_bridge, daemon=True).start()
    try:
        if op == "resume":
            session = harness.resume_session(session_id)
            result = session.run(prompt)
        else:
            result = harness.run(prompt, session_id=session_id)
    except Exception as exc:  # noqa: BLE001 - evidence records the real exception type
        error = {"type": type(exc).__name__, "message": str(exc), "phase": "active-input"}
    if CASE not in ("eof", "error", "cancel") and error is not None:
        raise AssertionError(("UNEXPECTED_SDK_ERROR", error))
    if CASE in ("eof", "error", "cancel"):
        assert error is not None or result is not None
except Exception as unexpected:  # noqa: BLE001
    emit(
        "unexpected-error",
        type=type(unexpected).__name__,
        message=str(unexpected),
        raw_result=None if result is None else {
            "final_response": result.final_response,
            "finish_reason": result.finish_reason,
            "events": result.events,
        },
        diagnostics=list(harness.client._stderr_lines),
    )
    raise
finally:
    watch_stop.set()
    close_error = None
    try:
        harness.close()
    except Exception as exc:  # noqa: BLE001
        close_error = {"type": type(exc).__name__, "message": str(exc)}

fake_alive_after_runtime_term = None
if CASE == "cancel" and fake_pid is not None:
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline and Path(f"/proc/{fake_pid}").exists():
        time.sleep(0.05)
    fake_alive_after_runtime_term = Path(f"/proc/{fake_pid}").exists()

markers = list(harness.client._stderr_lines)
request_ids = set()
for line in markers:
    if not line.startswith("G3A_BRIDGE_READY "):
        continue
    try:
        request_ids.add(json.loads(line.split(" ", 1)[1])["requestId"])
    except (json.JSONDecodeError, IndexError, KeyError):
        continue
bridge_files = [item for item in collect_tree(f"{BASE}/bridge") if any(rid in item["path"] for rid in request_ids)]
fake_files = [item for item in collect_tree(f"{BASE}/fake") if any(rid in item["path"] for rid in request_ids)]
session_files = collect_tree(f"{BASE}/dsh-home")
summary = {
    "final_response": None if result is None else result.final_response,
    "finish_reason": None if result is None else result.finish_reason,
    "session_id": None if result is None else result.session_id,
    "events": [] if result is None else result.events,
    "notifications": [] if result is None else [
        {"method": note.method, "payload": note.payload} for note in result.notifications
    ],
}
emit(
    "result",
    case=CASE,
    started_utc=started,
    finished_utc=utc(),
    worker_pid=os.getpid(),
    runtime_pid=runtime_pid,
    fake_pid=fake_pid,
    fake_alive_after_runtime_term=fake_alive_after_runtime_term,
    cancel_ready=cancel_ready.is_set(),
    error=error,
    close_error=close_error,
    runtime_exit_code=None if harness.client._proc is None else harness.client._proc.poll(),
    result=summary,
    stderr_markers=markers,
    bridge_trace_files=bridge_files,
    fake_receipt_files=fake_files,
    session_files=session_files,
    home=f"{BASE}/home",
)
