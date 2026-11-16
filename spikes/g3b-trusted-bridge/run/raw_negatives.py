"""B1/B2/B0/B3 raw-UDS negatives against a real Controller (no DSH)."""
from __future__ import annotations
import json
import os
from pathlib import Path
import socket
import sqlite3
import sys
import time

sys.path.insert(0, "/probe/src")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
from autoteacher_m0.bridge.protocol import Envelope, encode_envelope, parse_envelope

EVIDENCE = Path("/evidence")


def payload(**over):
    base = {"sessionId": "g3b-b3-raw-session", "provider": "offline-test-only-g3b",
            "model": "fixture-bridge-v1",
            "messages": [{"role": "user", "content": [{"type": "text", "text": "G3B_RAW"}]}],
            "tools": [], "system": None, "maxTokens": 256, "stream": True, "purpose": None}
    base.update(over)
    return base


def tools():
    p = EVIDENCE / "capture-tools.json"
    return [{"name": i["name"], "sha256": i["sha256"]} for i in json.loads(p.read_text())["tools"]] if p.exists() else []


def send_raw(raw: bytes, *, newline: bool = True) -> dict:
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(10)
    sock.connect(str(common.BASE / "bridge.sock"))
    try:
        sock.sendall(raw + (b"\n" if newline else b""))
        buffer = b""
        lines = []
        while len(lines) < 4:
            try:
                part = sock.recv(65536)
            except socket.timeout:
                break
            if not part:
                break
            buffer += part
            while b"\n" in buffer:
                line, _, buffer = buffer.partition(b"\n")
                if not line:
                    continue
                try:
                    lines.append(parse_envelope(line + b"\n").kind)
                except Exception as exc:
                    lines.append({"parse_error": getattr(exc, "code", str(exc))})
        return {"frames": lines, "closed": not part if 'part' in locals() else False}
    finally:
        sock.close()


def valid(p=None, seq=0):
    return encode_envelope(Envelope(1, "request", "tr-" + os.urandom(16).hex(), seq, p or payload(), None))


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    common.write_configs(run_id="g3b-b3-raw-negatives", tool_schemas=tools())
    controller = common.start_controller()
    results = {}
    try:
        common.wait_socket()
        cases = {
            "B1-oversize": lambda: send_raw(b"x" * (256 * 1024 + 1)),
            "B1-no-newline": lambda: send_raw(b"x" * (256 * 1024), newline=False),
            "B1-bad-utf8": lambda: send_raw(b'{"v":1,"kind":"request","transport_id":"tr-'+b"0"*32+b'","seq":0,"payload":{"sessionId":"\xff"},"hash":null}'),
            "B1-nan": lambda: send_raw(valid().replace(b'"maxTokens":256', b'"maxTokens":NaN')),
            "B1-duplicate-key": lambda: send_raw(b'{"v":1,"v":1,"kind":"request","transport_id":"tr-'+b"0"*32+b'","seq":0,"payload":{},"hash":null}'),
            "B1-wrong-v": lambda: send_raw(encode_envelope(Envelope(2, "request", "tr-"+"a"*32, 0, payload(), None))),
            "B1-wrong-kind": lambda: send_raw(encode_envelope(Envelope(1, "bogus", "tr-"+"a"*32, 0, {}, None))),
            "B1-seq": lambda: send_raw(valid(seq=1)),
            "B0-04-auth-fields": lambda: send_raw(valid(payload(authorized=True, admission="x", scope_id="y", override=True))),
            "B2-03-route-B": lambda: send_raw(valid(payload(provider="route-b", model="model-b"))),
            "B2-02-tools": lambda: send_raw(valid(payload(tools=[{"name": "shell", "parameters": {}}]))),
            "B3-12-unapproved-tool": lambda: send_raw(valid(payload(tools=[{"name": "shell", "description": "x", "parameters": {}}]))),
            "B3-12-image-block": lambda: send_raw(valid(payload(messages=[{"role": "user", "content": [{"type": "image", "mimeType": "image/png", "data": "x"}]}]))),
            "B3-12-file-block": lambda: send_raw(valid(payload(messages=[{"role": "user", "content": [{"type": "file", "name": "x"}]}]))),
            "B3-12-attachment-block": lambda: send_raw(valid(payload(messages=[{"role": "user", "content": [{"type": "attachment", "name": "x"}]}]))),
            "B3-12-store-field": lambda: send_raw(valid(payload(store=True))),
        }
        for name, fn in cases.items():
            try:
                results[name] = fn()
            except Exception as exc:
                results[name] = {"exception": type(exc).__name__, "message": str(exc)}
            time.sleep(0.02)
    finally:
        common.stop_controller(controller)
    counter_file = common.BASE / "receipts" / "received-count.json"
    counter = json.loads(counter_file.read_text())["count"] if counter_file.exists() else 0
    receipts = len(list((common.BASE / "receipts").glob("rcpt-*.json")))
    broker = common.BASE / "broker.sqlite3"
    claims = []
    reservations = []
    if broker.exists():
        con = sqlite3.connect(f"file:{broker}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        try:
            claims = [dict(r) for r in con.execute("select * from budget_dispatch_claims")]
        except Exception:
            pass
        try:
            reservations = [dict(r) for r in con.execute("select * from budget_reservations")]
        except Exception:
            pass
        con.close()
    no_success = all(not (isinstance(v.get("frames"), list) and "finish" in v["frames"]) for v in results.values())
    output = {"utc": common.utc(), "cases": results, "counter": counter,
              "receipts": receipts, "claims": len(claims), "reservations": len(reservations),
              "assertions": {"no_success_finish": no_success, "fake_counter_zero": counter == 0,
                             "no_receipts": receipts == 0, "no_claims": len(claims) == 0}}
    common.collect_evidence(EVIDENCE, label="b3-raw-negatives")
    (EVIDENCE / "raw-negatives-result.json").write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"kind": "raw-negatives", **output}, sort_keys=True), flush=True)
    return 0 if all(output["assertions"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
