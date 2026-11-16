"""Guard standalone reserve evidence: real DSH + B1 adapter + fixed raw UDS stub.

The stub is NOT the B2 controller. It proves guard's reserve-before-next /
settle-in-finally ordering and log redaction only; it is not a Guard+Bridge
combination PASS.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import socket
import sys
import threading
import time

sys.path.insert(0, "/probe/src")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
from autoteacher_m0.bridge.protocol import Envelope, encode_envelope, parse_envelope

EVIDENCE = Path("/evidence")
SOCKET = Path("/work/g3b/bridge.sock")
BASE = Path("/work/g3b")


def server() -> None:
    if SOCKET.exists():
        SOCKET.unlink()
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(SOCKET)); listener.listen(1); listener.settimeout(30)
    try:
        conn, _ = listener.accept()
    except socket.timeout:
        return
    try:
        data = b""
        while b"\n" not in data:
            part = conn.recv(65536)
            if not part:
                return
            data += part
        line, _, _ = data.partition(b"\n")
        req = parse_envelope(line + b"\n")
        transport = req.transport_id
        conn.sendall(encode_envelope(Envelope(1, "ack", transport, 1,
            {"request_id": transport, "accepted": True, "code": None}, None)) + b"\n")
        conn.sendall(encode_envelope(Envelope(1, "chunk", transport, 2,
            {"chunk": {"type": "text-delta", "index": 0, "text": "GUARD_SEPARATE_OK"}}, None)) + b"\n")
        conn.sendall(encode_envelope(Envelope(1, "chunk", transport, 3,
            {"chunk": {"type": "usage", "usage": {"inputTokens": 7, "outputTokens": 3,
             "cacheReadTokens": 0, "cacheWriteTokens": 0, "reasoningTokens": 0, "totalTokens": 10}}}, None)) + b"\n")
        conn.sendall(encode_envelope(Envelope(1, "finish", transport, 4,
            {"reason": {"kind": "stop"}}, None)) + b"\n")
    finally:
        try: conn.close()
        except Exception: pass
        listener.close()


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (BASE / "dsh-home").mkdir(parents=True, exist_ok=True)
    (BASE / "workspace").mkdir(parents=True, exist_ok=True)
    thread = threading.Thread(target=server, daemon=True); thread.start()
    deadline = time.monotonic() + 10
    while not SOCKET.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    from deepseek_harness import DeepSeekHarness  # noqa: E402
    env = {
        "PATH": "/opt/python/bin:/usr/bin", "HOME": str(BASE / "dsh-home"),
        "PYTHONPATH": "/deps", "PYTHONDONTWRITEBYTECODE": "1", "TMPDIR": "/tmp",
        "DSH_RUNTIME_MODE": "exe", "DSH_RESOURCE_CACHE": "/work/resources",
        "NARB_NATIVE_CACHE_DIR": "/probe/native-cache",
        "PKG_NATIVE_CACHE_PATH": "/probe/pkg-cache", "NO_COLOR": "1",
    }
    harness = DeepSeekHarness(
        provider="offline-test-only-g3b", model="fixture-bridge-v1", max_tokens=256,
        profile="sdk-minimal",
        patches=("/probe/config/bridge.patch.yml", "/probe/config/guard.reserve.patch.yml"),
        dsh_home=str(BASE / "dsh-home"), cwd=str(BASE / "workspace"),
        runtime_cwd=str(BASE / "workspace"), env=env,
        initialize_timeout_seconds=20, request_timeout_seconds=20,
        shutdown_timeout_seconds=3)
    result = None; error = None
    try:
        harness.start()
        result = harness.run("GUARD_SEPARATE", session_id="g3b-guard-separate")
    except Exception as exc:  # noqa: BLE001
        error = {"type": type(exc).__name__, "message": str(exc)}
    finally:
        stderr = list(harness.client._stderr_lines) if harness.client is not None else []
        try: harness.close()
        except Exception: pass
    thread.join(timeout=5)
    import sqlite3
    bro = BASE / "guard-broker.sqlite3"; snap = {}
    if bro.exists():
        con = sqlite3.connect(f"file:{bro}?mode=ro", uri=True); con.row_factory = sqlite3.Row
        for table in ("budget_reservations", "budget_dispatch_claims"):
            try: snap[table] = [dict(r) for r in con.execute(f"select * from {table}")]
            except Exception: snap[table] = []
        con.close()
    rbg = [line for line in stderr if line.startswith("RBG_")]
    output = {"utc": common.utc(), "final_response": None if result is None else result.final_response,
              "finish_reason": None if result is None else result.finish_reason,
              "error": error, "rbg": rbg, "broker": snap,
              "assertions": {"boot_reserve": any('"reserve_mode"' not in x and x.startswith("RBG_BOOT ") for x in rbg),
                             "has_reserve": any(x.startswith("RBG_RESERVE ") for x in rbg),
                             "has_settle": any(x.startswith("RBG_SETTLE ") for x in rbg),
                             "no_plain_key": not any("sk-" in x for x in stderr)}}
    common.collect_evidence(EVIDENCE, label="b3-guard-separate")
    (EVIDENCE / "guard-separate-result.json").write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"kind": "guard-separate", **output}, sort_keys=True), flush=True)
    return 0 if all(output["assertions"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
