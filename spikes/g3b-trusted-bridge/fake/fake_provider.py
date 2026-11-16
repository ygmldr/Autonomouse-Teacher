"""G3-B synthetic Fake Provider (B2-owned). stdin one JSON line; receipt first."""
from __future__ import annotations
import hashlib
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

MAX = 256 * 1024
RECEIPT_DIR = Path(os.environ.get("G3B_RECEIPT_DIR", "/work/g3b/receipts"))
MODE = os.environ.get("G3B_FAKE_MODE", "ok_usage")


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def usage_for(mode: str) -> dict | None:
    if mode == "ok_usage":
        return {"inputTokens": 11, "cacheReadTokens": 2, "cacheWriteTokens": 0,
                "outputTokens": 5, "reasoningTokens": 0, "totalTokens": 18}
    if mode == "partial_usage":
        return {"inputTokens": 11}
    if mode == "usage_invalid":
        return {"inputTokens": "bad"}
    return None


def main() -> int:
    data = sys.stdin.buffer.readline(MAX + 1)
    if len(data) > MAX or not data.endswith(b"\n"):
        return 2
    raw = data[:-1]
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return 2
    mode = payload.get("mode", MODE)
    nonce = payload.get("nonce", "")
    RECEIPT_DIR.mkdir(parents=True, exist_ok=True)
    receipt = {
        "schema": "m0.g3b.fake.receipt.v1", "receipt_id": "rcpt-" + uuid.uuid4().hex[:32],
        "raw_sha256": hashlib.sha256(raw).hexdigest(), "raw_length": len(raw),
        "transport_encoding": "utf-8+lf", "mode": mode, "usage": usage_for(mode),
        "nonce": nonce, "utc_start": utc(), "utc_end": utc(), "pid": os.getpid(),
        "synthetic": True, "real_model_calls": 0, "http_calls": 0, "network_used": False,
    }
    path = RECEIPT_DIR / f"{receipt['receipt_id']}.json"
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(receipt, handle, sort_keys=True, separators=(",", ":"))
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)
    try:
        dfd = os.open(RECEIPT_DIR, os.O_RDONLY)
        os.fsync(dfd)
        os.close(dfd)
    except OSError:
        pass
    counter = RECEIPT_DIR / "received-count.json"
    count = 1
    if counter.exists():
        try:
            count = int(json.loads(counter.read_text())["count"]) + 1
        except Exception:
            count = 1
    tmpc = counter.with_suffix(".tmp")
    tmpc.write_text(json.dumps({"count": count}), encoding="utf-8")
    os.replace(tmpc, counter)
    frames = []
    if mode == "ok_usage":
        frames = [{"kind": "chunk", "chunk": {"type": "text-delta", "text": "ok"}},
                  {"kind": "usage", "usage": receipt["usage"]},
                  {"kind": "finish", "reason": {"kind": "stop"}}]
    elif mode == "partial_usage":
        frames = [{"kind": "usage", "usage": receipt["usage"]},
                  {"kind": "finish", "reason": {"kind": "stop"}}]
    elif mode == "no_usage":
        frames = [{"kind": "finish", "reason": {"kind": "stop"}}]
    elif mode == "tool_once":
        frames = [{"kind": "chunk", "chunk": {"type": "tool-call-delta",
                  "toolName": "skill_lookup", "arguments": "{}"}},
                  {"kind": "finish", "reason": {"kind": "tool-calls"}}]
    elif mode == "error":
        frames = [{"kind": "finish", "reason": {"kind": "error"}}]
    else:
        frames = [{"kind": "finish", "reason": {"kind": "stop"}}]
    for frame in frames:
        print(json.dumps(frame, sort_keys=True, separators=(",", ":")), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
