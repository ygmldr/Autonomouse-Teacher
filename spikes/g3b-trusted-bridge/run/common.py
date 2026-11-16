"""B3-prep shared launcher/evidence helpers (container-only paths)."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import time
from datetime import datetime, timedelta, timezone

PYTHON = "/opt/python/bin/python3.11"
BASE = Path("/work/g3b")
PROBE = Path("/probe")
ENV = {
    "PATH": "/opt/python/bin:/usr/bin",
    "HOME": "/work",
    "PYTHONPATH": "/probe/src:/deps",
    "PYTHONDONTWRITEBYTECODE": "1",
    "TMPDIR": "/tmp",
}


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _template(name: str) -> str:
    return (PROBE / "config" / name).read_text(encoding="utf-8")


def write_configs(*, scenario: str = "ok_usage", run_id: str = "g3b-b3prep-smoke",
                  tool_schemas: list[dict] | None = None) -> dict:
    BASE.mkdir(parents=True, exist_ok=True)
    (BASE / "receipts").mkdir(parents=True, exist_ok=True)
    admission_id = secrets.token_hex(16)
    nonce = secrets.token_hex(16)
    expiry = (datetime.now(timezone.utc) + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    tools = json.dumps(tool_schemas if tool_schemas is not None else [], sort_keys=True)
    admission = _template("admission.template.json")
    admission = admission.replace("{{ADMISSION_ID}}", admission_id)
    admission = admission.replace("{{RUN_ID}}", run_id)
    admission = admission.replace("{{TOOL_SCHEMAS}}", tools)
    admission = admission.replace("{{FAKE_SCENARIO}}", scenario)
    admission = admission.replace("{{EXPIRY_UTC}}", expiry)
    admission = admission.replace("{{NONCE}}", nonce)
    (BASE / "admission.json").write_text(admission + "\n", encoding="utf-8")
    broker = _template("broker.policy.template.json")
    (BASE / "broker.json").write_text(broker, encoding="utf-8")
    controller = _template("controller.template.json")
    (BASE / "controller.json").write_text(controller, encoding="utf-8")
    return {"admission_id": admission_id, "nonce": nonce, "expiry_utc": expiry}


def start_controller() -> subprocess.Popen:
    log = open(BASE / "controller.log", "wb")
    controller_env = dict(ENV)
    for name in ("G3B_TEST_MODE", "G3B_CRASH_HOOK"):
        if name in os.environ:
            controller_env[name] = os.environ[name]
    proc = subprocess.Popen(
        [PYTHON, "-B", "-m", "autoteacher_m0.bridge.controller", "--config",
         str(BASE / "controller.json")],
        cwd="/work", env=controller_env, stdin=subprocess.DEVNULL,
        stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    proc._b3_log = log  # type: ignore[attr-defined]
    return proc


def wait_socket(timeout: float = 15.0) -> None:
    path = BASE / "bridge.sock"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return
        time.sleep(0.02)
    raise RuntimeError("CONTROLLER_SOCKET_TIMEOUT")


def stop_controller(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except OSError:
            pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                pass
            proc.wait(timeout=5)
    log = getattr(proc, "_b3_log", None)
    if log is not None:
        try:
            log.close()
        except OSError:
            pass


def socket_client(timeout: float = 10.0) -> socket.socket:
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    sock.connect(str(BASE / "bridge.sock"))
    return sock


def read_frames(sock: socket.socket, *, limit: int = 300) -> list[bytes]:
    buffer = b""
    lines: list[bytes] = []
    while len(lines) < limit:
        while b"\n" not in buffer:
            part = sock.recv(65536)
            if not part:
                return lines
            buffer += part
        line, _, buffer = buffer.partition(b"\n")
        if line:
            lines.append(line + b"\n")
        if lines and (b'"kind":"finish"' in lines[-1] or b'"kind":"error"' in lines[-1]):
            return lines
    return lines


def collect_evidence(evidence_root: Path, *, label: str) -> dict:
    evidence_root.mkdir(parents=True, exist_ok=True)
    work_copy = evidence_root / "work"
    files: list[dict] = []
    if BASE.exists():
        for path in sorted(BASE.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(BASE)
            if path.is_socket() if hasattr(path, "is_socket") else False:
                continue
            target = work_copy / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(path.read_bytes())
            files.append({"path": f"work/{rel}", "sha256": sha256_file(path),
                          "bytes": path.stat().st_size})
    result = {"label": label, "utc": utc(), "files": files,
              "env_names": sorted(os.environ)}
    (evidence_root / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result
