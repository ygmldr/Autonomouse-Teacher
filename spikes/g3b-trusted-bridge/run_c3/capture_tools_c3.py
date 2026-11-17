"""Capture the real DSH ``GenerateOptions.tools`` over the frozen bridge wire.

Container only. Starts a throwaway raw AF_UNIX server at the frozen socket path,
runs one real DeepSeekHarness prompt with the bridge patch, records the first
request payload, replies ack+error and exits. No Controller/Broker/Fake is
involved. Output: ``/evidence/capture-tools.json`` (host stage fixture).
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import socket
import sys
import threading
import time

sys.path.insert(0, "/probe/src")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import common_c3 as common  # noqa: E402
from autoteacher_m0.bridge.protocol import (  # noqa: E402
    Envelope, encode_envelope, parse_envelope,
)

EVIDENCE = Path("/evidence")
SOCKET = common.BASE / "bridge.sock"
BASE = common.BASE
captured: dict = {}


def server() -> None:
    SOCKET.parent.mkdir(parents=True, exist_ok=True)
    if SOCKET.exists():
        SOCKET.unlink()
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(SOCKET))
    listener.listen(2)
    listener.settimeout(40)
    try:
        conn, _ = listener.accept()
    except socket.timeout:
        return
    try:
        data = b""
        while b"\n" not in data:
            part = conn.recv(65536)
            if not part:
                break
            data += part
        line, _, _ = data.partition(b"\n")
        captured["raw_sha256"] = hashlib.sha256(line).hexdigest()
        captured["raw_length"] = len(line)
        captured["raw_json"] = json.loads(line.decode("utf-8"))
        env = parse_envelope(line + b"\n")
        captured["request"] = {"kind": env.kind, "transport_id": env.transport_id,
                               "seq": env.seq, "payload": env.payload,
                               "raw_sha256": captured["raw_sha256"]}
        transport = env.transport_id
        ack = Envelope(1, "ack", transport, 1,
                       {"request_id": transport, "accepted": True, "code": None}, None)
        error = Envelope(1, "error", transport, 2,
                         {"code": "REQUEST_INVALID", "message": "capture complete",
                          "retryable": False}, None)
        conn.sendall(encode_envelope(ack) + b"\n")
        conn.sendall(encode_envelope(error) + b"\n")
    finally:
        try:
            conn.close()
        except OSError:
            pass
        listener.close()


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


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (BASE / "dsh-home").mkdir(parents=True, exist_ok=True)
    (BASE / "workspace").mkdir(parents=True, exist_ok=True)
    thread = threading.Thread(target=server, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not SOCKET.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    from deepseek_harness import DeepSeekHarness  # noqa: E402
    harness = DeepSeekHarness(
        provider="offline-test-only-g3b", model="fixture-bridge-v1", max_tokens=256,
        profile="sdk-minimal", patches=("/probe/config/bridge.patch.yml",),
        dsh_home=str(BASE / "dsh-home"), cwd=str(BASE / "workspace"),
        runtime_cwd=str(BASE / "workspace"), env=dsh_env(),
        initialize_timeout_seconds=25, request_timeout_seconds=20,
        shutdown_timeout_seconds=3,
    )
    error = None
    try:
        harness.start()
        harness.run("G3C_CAPTURE", session_id="g3c-capture-session")
    except Exception as exc:  # noqa: BLE001 - synthetic error terminal is expected
        error = {"type": type(exc).__name__, "message": str(exc)}
    finally:
        try:
            harness.close()
        except Exception:
            pass
    thread.join(timeout=5)
    tools = []
    if "request" in captured:
        for tool in captured["request"]["payload"].get("tools", []):
            raw = json.dumps(tool, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode("utf-8")
            tools.append({"name": tool.get("name"),
                          "sha256": hashlib.sha256(raw).hexdigest(),
                          "canonical_json": json.dumps(tool, sort_keys=True,
                                                       ensure_ascii=False)})
    result = {"utc": common.utc(), "socket": str(SOCKET), "captured": captured,
              "tools": tools, "dsh_error": error, "env_names": sorted(os.environ)}
    common.write_json(EVIDENCE / "capture-tools.json", result)
    print(json.dumps({"kind": "capture", "tool_count": len(tools),
                      "tool_names": [tool["name"] for tool in tools],
                      "tool_hashes": [tool["sha256"] for tool in tools],
                      "dsh_error": error}, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
