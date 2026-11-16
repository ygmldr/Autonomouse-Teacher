"""B3-05: two real Controller processes race the same durable call_id.

Both controllers use the same broker/attempt SQLite files but distinct
admission ids and socket paths; a file fence releases two stub UDS clients at the
same instant. SQLite must grant at most one dispatch claim and one Fake attempt.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time

sys.path.insert(0, "/probe/src")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
from autoteacher_m0.bridge.protocol import Envelope, encode_envelope, parse_envelope

EVIDENCE = Path("/evidence")
BASE = Path("/work/g3b")
RUN_ID = "g3b-b3-concurrency-run"
TOOL_SHA = None
TOOL_NAME = "skill_lookup"


def utc() -> str:
    return common.utc()


def captured_tools() -> list[dict]:
    path = EVIDENCE / "capture-tools.json"
    if not path.exists():
        return []
    doc = json.loads(path.read_text())
    return [{"name": item["name"], "sha256": item["sha256"]} for item in doc.get("tools", [])]


def admission(tag: str) -> Path:
    template = Path("/probe/config/admission.template.json").read_text()
    target = BASE / tag / "admission.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    import secrets
    from datetime import datetime, timedelta, timezone
    text = template.replace("{{ADMISSION_ID}}", secrets.token_hex(16))
    text = text.replace("{{RUN_ID}}", RUN_ID)
    text = text.replace("{{TOOL_SCHEMAS}}", json.dumps(captured_tools(), sort_keys=True))
    text = text.replace("{{FAKE_SCENARIO}}", "ok_usage")
    text = text.replace("{{EXPIRY_UTC}}", (datetime.now(timezone.utc) + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"))
    text = text.replace("{{NONCE}}", secrets.token_hex(16))
    target.write_text(text + "\n", encoding="utf-8")
    return target


def config(tag: str, sock: str) -> Path:
    doc = json.loads(Path("/probe/config/controller.template.json").read_text())
    doc["admission_path"] = str(BASE / tag / "admission.json")
    doc["socket_path"] = sock
    target = BASE / tag / "controller.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
    (BASE / "broker.json").write_text(Path("/probe/config/broker.policy.template.json").read_text())
    return target


def start(tag: str, cfg: Path) -> subprocess.Popen:
    log = open(BASE / tag / "controller.log", "wb")
    env = dict(common.ENV)
    proc = subprocess.Popen(["/opt/python/bin/python3.11", "-B", "-m",
                             "autoteacher_m0.bridge.controller", "--config", str(cfg)],
                            cwd="/work", env=env, stdin=subprocess.DEVNULL,
                            stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    proc._log = log  # type: ignore[attr-defined]
    return proc


def wait(sock: str) -> None:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if Path(sock).exists():
            return
        time.sleep(0.01)
    raise RuntimeError("SOCKET_TIMEOUT")


def request() -> dict:
    return {"sessionId": "g3b-b3-concurrency-session",
            "provider": "offline-test-only-g3b", "model": "fixture-bridge-v1",
            "messages": [{"role": "user", "content": [{"type": "text", "text": "G3B_CONCURRENCY"}]}],
            "tools": [], "system": None, "maxTokens": 256, "stream": True, "purpose": None}


def client(sock_path: str, barrier: threading.Barrier, result: dict) -> None:
    payload = request()
    transport = "tr-" + os.urandom(16).hex()
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(15)
    sock.connect(sock_path)
    barrier.wait()
    sock.sendall(encode_envelope(Envelope(1, "request", transport, 0, payload, None)) + b"\n")
    frames = []
    buffer = b""
    while True:
        while b"\n" not in buffer:
            part = sock.recv(65536)
            if not part:
                result["frames"] = frames
                sock.close()
                return
            buffer += part
        line, _, buffer = buffer.partition(b"\n")
        if not line:
            continue
        env = parse_envelope(line + b"\n")
        frames.append({"kind": env.kind, "seq": env.seq, "payload": env.payload})
        if env.kind in {"finish", "error"}:
            result["frames"] = frames
            sock.close()
            return


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (BASE / "receipts").mkdir(parents=True, exist_ok=True)
    requirements = captured_tools()
    if not requirements:
        raise RuntimeError("capture-tools.json with skill_lookup required")
    cfg_a = config("a", "/work/g3b/bridge-a.sock")
    cfg_b = config("b", "/work/g3b/bridge-b.sock")
    adm_a = admission("a"); adm_b = admission("b")
    # Distinct admission ids but the same run_id, request bytes and step => same call_id.
    assert json.loads(adm_a.read_text())["admission_id"] != json.loads(adm_b.read_text())["admission_id"]
    a = start("a", cfg_a); b = start("b", cfg_b)
    try:
        wait("/work/g3b/bridge-a.sock"); wait("/work/g3b/bridge-b.sock")
        barrier = threading.Barrier(2)
        results = {"a": {}, "b": {}}
        threads = [threading.Thread(target=client, args=("/work/g3b/bridge-a.sock", barrier, results["a"])),
                   threading.Thread(target=client, args=("/work/g3b/bridge-b.sock", barrier, results["b"]))]
        for thread in threads: thread.start()
        for thread in threads: thread.join(timeout=20)
    finally:
        for proc in (a, b):
            if proc.poll() is None:
                try: os.killpg(proc.pid, 15)
                except OSError: pass
                try: proc.wait(timeout=5)
                except subprocess.TimeoutExpired: os.killpg(proc.pid, 9)
            log = getattr(proc, "_log", None)
            if log: log.close()
    time.sleep(0.2)
    import sqlite3
    counter_path = BASE / "receipts" / "received-count.json"
    counter = json.loads(counter_path.read_text())["count"] if counter_path.exists() else 0
    db = BASE / "broker.sqlite3"; adb = BASE / "attempts.sqlite3"
    def rows(path, table):
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True); con.row_factory = sqlite3.Row
        try: return [dict(r) for r in con.execute(f"select * from {table}")]
        except Exception: return []
        finally: con.close()
    claims = rows(db, "budget_dispatch_claims")
    reservations = rows(db, "budget_reservations")
    attempts = rows(adb, "g3b_attempts")
    outputs = {"a": results["a"], "b": results["b"]}
    kinds = {tag: [frame["kind"] for frame in outputs[tag].get("frames", [])] for tag in outputs}
    errors = {tag: next((frame["payload"] for frame in outputs[tag].get("frames", [])
                         if frame["kind"] == "error"), None) for tag in outputs}
    result = {"utc": utc(), "run_id": RUN_ID, "admission_ids": [json.loads(adm_a.read_text())["admission_id"],
                                                                 json.loads(adm_b.read_text())["admission_id"]],
              "frames": kinds, "errors": errors,
              "counter": counter, "reservations": reservations,
              "claims": claims, "attempts": attempts,
              "assertions": {"fake_counter_one": counter == 1,
                             "at_most_one_completed_claim": sum(1 for row in claims if row.get("status") == "COMPLETED") <= 1,
                             "claims_total_at_most_one": len(claims) <= 1,
                             "one_fake_attempt": len(attempts) <= 1,
                             "one_success_one_deterministic_error": sum(1 for tag in kinds if "finish" in kinds[tag] and "error" not in kinds[tag]) == 1}}
    common.collect_evidence(EVIDENCE, label="b3-05-concurrency")
    (EVIDENCE / "concurrency-result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"kind": "concurrency", **result}, sort_keys=True), flush=True)
    return 0 if all(result["assertions"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
