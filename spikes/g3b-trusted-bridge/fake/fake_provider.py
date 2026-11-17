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
    if mode in {"ok_usage", "tool_once", "tool_final", "slow_usage", "usage_conflict",
                "usage_after_finish", "multi_usage", "stream_slow", "many_chunks",
                "big_output", "truncated_stream"}:
        return {"inputTokens": 11, "cacheReadTokens": 2, "cacheWriteTokens": 0,
                "outputTokens": 5, "reasoningTokens": 0, "totalTokens": 18}
    if mode == "partial_usage":
        return {"inputTokens": 11}
    if mode == "usage_invalid":
        return {"inputTokens": "bad"}
    return None


def timing_mark(nonce: str, name: str, **extra: object) -> None:
    """Append one fsynced wall/monotonic mark for streaming T1<T2 evidence.

    The sidecar lives next to the receipt files so the Controller evidence copy
    carries it; it never participates in receipt validation.
    """
    import time as _time
    path = RECEIPT_DIR / f"timing-{nonce}.json"
    try:
        document = json.loads(path.read_text()) if path.exists() else {"marks": []}
    except (OSError, ValueError):
        document = {"marks": []}
    document.setdefault("marks", []).append({
        "name": name, "epoch_ms": int(_time.time() * 1000),
        "monotonic": _time.monotonic(), **extra})
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(document, handle, sort_keys=True, separators=(",", ":"))
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def stream_mode(mode: str, nonce: str) -> int:
    """Incremental G3-C modes; the receipt is already durable before this runs."""
    import time as _time

    def emit(frame: dict) -> None:
        print(json.dumps(frame, sort_keys=True, separators=(",", ":")), flush=True)

    timing_mark(nonce, "frames_start", mode=mode)
    if mode == "stream_slow":
        emit({"kind": "chunk", "chunk": {"type": "text-delta", "index": 0,
                                         "text": "early"}})
        timing_mark(nonce, "first_chunk_flushed")
        _time.sleep(2.0)
        emit({"kind": "usage", "usage": usage_for(mode)})
        emit({"kind": "finish", "reason": {"kind": "stop"}})
    elif mode == "truncated_stream":
        emit({"kind": "chunk", "chunk": {"type": "text-delta", "index": 0,
                                         "text": "partial"}})
        timing_mark(nonce, "first_chunk_flushed")
        timing_mark(nonce, "exit_without_finish")
        return 3
    elif mode == "many_chunks":
        for index in range(300):
            emit({"kind": "chunk", "chunk": {"type": "text-delta", "index": index,
                                             "text": "x"}})
        timing_mark(nonce, "chunks_flushed", count=300)
        emit({"kind": "usage", "usage": usage_for(mode)})
        emit({"kind": "finish", "reason": {"kind": "stop"}})
    elif mode == "big_output":
        block = "y" * 60000
        for index in range(20):
            emit({"kind": "chunk", "chunk": {"type": "text-delta", "index": index,
                                             "text": block}})
        timing_mark(nonce, "chunks_flushed", count=20)
        emit({"kind": "usage", "usage": usage_for(mode)})
        emit({"kind": "finish", "reason": {"kind": "stop"}})
    else:
        raise SystemExit("UNKNOWN_STREAM_MODE")
    timing_mark(nonce, "exit_after_finish")
    return 0


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
    if not isinstance(nonce, str) or len(nonce) != 32 or any(c not in "0123456789abcdef" for c in nonce):
        return 2
    path = RECEIPT_DIR / f"rcpt-{nonce}.json"
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
    if mode == "eof":
        timing_mark(nonce, "exit_without_frames")
        return 0
    if mode == "timeout":
        import time as _time
        timing_mark(nonce, "stall_after_receipt")
        _time.sleep(35)
        return 2
    if mode in {"stream_slow", "many_chunks", "big_output", "truncated_stream"}:
        return stream_mode(mode, nonce)
    frames = []
    if mode == "ok_usage":
        frames = [{"kind": "chunk", "chunk": {"type": "text-delta", "index": 0, "text": "ok"}},
                  {"kind": "usage", "usage": receipt["usage"]},
                  {"kind": "finish", "reason": {"kind": "stop"}}]
    elif mode == "partial_usage":
        frames = [{"kind": "usage", "usage": receipt["usage"]},
                  {"kind": "finish", "reason": {"kind": "stop"}}]
    elif mode == "no_usage":
        frames = [{"kind": "finish", "reason": {"kind": "stop"}}]
    elif mode == "tool_once":
        # Same public StreamChunk ordering as the G3-A tool-turn fixture: an
        # explicit tool-call block is required for DSH to execute the tool.
        call_id = "call-skill-lookup-1"
        arguments = '{"skill_id":"binary_search"}'
        frames = [
            {"kind": "chunk", "chunk": {"type": "block-start", "index": 0,
                                        "blockType": "tool-call"}},
            {"kind": "chunk", "chunk": {"type": "tool-call-delta", "index": 0,
                                        "id": call_id, "name": "skill_lookup",
                                        "argumentsDelta": arguments}},
            {"kind": "chunk", "chunk": {"type": "block-end", "index": 0,
                                        "block": {"type": "tool-call", "id": call_id,
                                                  "name": "skill_lookup",
                                                  "arguments": arguments}}},
            {"kind": "usage", "usage": receipt["usage"]},
            {"kind": "finish", "reason": {"kind": "tool-calls"}},
        ]
    elif mode == "slow_usage":
        # Used only by deterministic deadline/cancel tests: the receipt is
        # already durable (receipt-first) before this bounded synthetic delay.
        import time as _time
        _time.sleep(1.2)
        frames = [{"kind": "chunk", "chunk": {"type": "text-delta", "index": 0, "text": "slow"}},
                  {"kind": "usage", "usage": receipt["usage"]},
                  {"kind": "finish", "reason": {"kind": "stop"}}]
    elif mode == "usage_conflict":
        conflicting = dict(receipt["usage"])
        conflicting["outputTokens"] = 999
        frames = [{"kind": "usage", "usage": conflicting},
                  {"kind": "finish", "reason": {"kind": "stop"}}]
    elif mode == "multi_usage":
        frames = [{"kind": "usage", "usage": receipt["usage"]},
                  {"kind": "usage", "usage": receipt["usage"]},
                  {"kind": "finish", "reason": {"kind": "stop"}}]
    elif mode == "tool_final":
        frames = [{"kind": "chunk", "chunk": {"type": "text-delta", "index": 0,
                                              "text": "ok"}},
                  {"kind": "usage", "usage": receipt["usage"]},
                  {"kind": "finish", "reason": {"kind": "stop"}}]
    elif mode == "usage_after_finish":
        frames = [{"kind": "finish", "reason": {"kind": "stop"}},
                  {"kind": "usage", "usage": receipt["usage"]}]
    elif mode == "error":
        frames = [{"kind": "finish", "reason": {"kind": "error"}}]
    else:
        frames = [{"kind": "usage", "usage": receipt["usage"]},
                  {"kind": "finish", "reason": {"kind": "stop"}}]
    for frame in frames:
        print(json.dumps(frame, sort_keys=True, separators=(",", ":")), flush=True)
    timing_mark(nonce, "exit_after_frames", frames=len(frames))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
