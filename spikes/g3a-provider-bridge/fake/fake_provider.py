#!/usr/bin/env python3
"""Independent synthetic provider process for the G3-A stdio bridge spike.

The locked DSH runtime never executes this file directly. A public Cordis
`LlmAdapter` plugin (compiled JS) spawns it as a separate OS process, writes one
newline-delimited canonical request, and relays the newline-delimited synthetic
chunk frames back to DSH.

No HTTP client, no network, no API key, no model and no DSH import exist here.
The process is deliberately bounded: it writes a receipt, emits a finite frame
sequence, and exits. It also arms Linux PR_SET_PDEATHSIG so a killed DSH
runtime cannot leave an orphan bridge child during the cancellation probe.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import select
import signal
import sys
import time
from datetime import datetime, timezone

USAGE = {
    "inputTokens": 11,
    "outputTokens": 5,
    "cacheReadTokens": 2,
    "cacheWriteTokens": 0,
    "reasoningTokens": 0,
    "totalTokens": 18,
}
NONCE = re.compile(r"G3A_ECHO nonce=([A-Za-z0-9_-]{8,48})")
MAX_LIFETIME_SECONDS = 30.0


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def emit(value: dict) -> None:
    sys.stdout.write(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def event(path: str, kind: str, **data: object) -> None:
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps({"ts": utc(), "kind": kind, **data}, sort_keys=True) + "\n")
            handle.flush()
    except OSError:
        pass


def arm_parent_death() -> bool:
    """Best-effort Linux parent-death signal; the spike records whether it armed."""
    try:
        import ctypes

        libc = ctypes.CDLL(None, use_errno=True)
        PR_SET_PDEATHSIG = 1
        if libc.prctl(PR_SET_PDEATHSIG, signal.SIGTERM, 0, 0, 0) != 0:
            return False
        # Close the race where the parent died before prctl was armed.
        if os.getppid() == 1:
            os._exit(0)
        return True
    except Exception:
        return False


def chunk(value: dict) -> None:
    emit({"v": 1, "type": "chunk", "requestId": REQUEST_ID, "chunk": value})


def usage() -> None:
    chunk({"type": "usage", "usage": USAGE})


def finish(kind: str, failure: dict | None = None) -> None:
    reason: dict = {"kind": kind}
    if failure is not None:
        reason["failure"] = failure
    chunk({"type": "finish", "reason": reason})


def emit_text(text: str) -> None:
    # Two deltas prove incremental streaming rather than one coalesced frame.
    head, tail = text[: len("G3A_BRIDGE_")], text[len("G3A_BRIDGE_"):]
    chunk({"type": "block-start", "index": 0, "blockType": "text"})
    chunk({"type": "text-delta", "index": 0, "text": head})
    chunk({"type": "text-delta", "index": 0, "text": tail})
    chunk({"type": "block-end", "index": 0, "block": {"type": "text", "text": text}})
    usage()
    finish("stop")


def text_blocks(message: dict) -> str:
    return "".join(block.get("text", "") for block in message.get("content", []) if block.get("type") == "text")


def real_user_texts(messages: list[dict]) -> list[str]:
    values: list[str] = []
    for message in messages:
        source = message.get("source") or {}
        if message.get("role") == "user" and source.get("kind") == "user":
            values.append(text_blocks(message))
    return values


def find_nonce(messages: list[dict], *, last_only: bool) -> str | None:
    found: list[str] = []
    for text in real_user_texts(messages):
        match = NONCE.search(text)
        if match:
            found.append(match.group(1))
    if not found:
        return None
    return found[-1] if last_only else found[0]


def write_receipt(path: str, raw: bytes, request: dict, *, parent_death_armed: bool) -> str:
    digest = hashlib.sha256(raw).hexdigest()
    receipt = {
        "v": 1,
        "synthetic": True,
        "pid": os.getpid(),
        "ppid": os.getppid(),
        "requestId": request.get("requestId"),
        "rawRequestSha256": digest,
        "mode": request.get("mode"),
        "provider": request.get("provider"),
        "model": request.get("model"),
        "sessionId": request.get("sessionId"),
        "purpose": request.get("purpose"),
        "maxTokens": request.get("maxTokens"),
        "messageCount": len(request.get("messages") or []),
        "roles": [message.get("role") for message in request.get("messages") or []],
        "toolNames": [tool.get("name") for tool in request.get("tools") or []],
        "userTexts": real_user_texts(request.get("messages") or []),
        "tools": request.get("tools"),
        "messages": request.get("messages"),
        "system": request.get("system"),
        "startedUtc": utc(),
        "python": sys.version,
        "cwd": os.getcwd(),
        "parentDeathSignalArmed": parent_death_armed,
        "realModelCalls": 0,
        "httpCalls": 0,
        "networkUsed": False,
    }
    if path:
        temporary = f"{path}.tmp.{os.getpid()}"
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(receipt, handle, sort_keys=True, indent=2)
            handle.write("\n")
        os.replace(temporary, path)
    return digest


raw_line = sys.stdin.buffer.readline()
if not raw_line:
    sys.exit(3)
request = json.loads(raw_line)
REQUEST_ID = request.get("requestId") or "missing-request-id"
receipt_path = request.get("receiptPath") or ""
events_path = request.get("eventsPath") or ""
parent_death = arm_parent_death()
request_sha = write_receipt(receipt_path, raw_line, request, parent_death_armed=parent_death)
event(events_path, "request-received", requestId=REQUEST_ID, rawRequestSha256=request_sha, pid=os.getpid())

messages = request.get("messages") or []
tool_names = [tool.get("name") for tool in request.get("tools") or []]
emit({
    "v": 1,
    "type": "ack",
    "requestId": REQUEST_ID,
    "pid": os.getpid(),
    "rawRequestSha256": request_sha,
    "messageCount": len(messages),
    "toolNames": tool_names,
    "userTexts": real_user_texts(messages),
    "parentDeathSignalArmed": parent_death,
    "startedUtc": utc(),
})
event(events_path, "ack-sent", requestId=REQUEST_ID, mode=request.get("mode"))

mode = request.get("mode")
if mode == "eof":
    chunk({"type": "block-start", "index": 0, "blockType": "text"})
    chunk({"type": "text-delta", "index": 0, "text": "G3A_BRIDGE_PARTIAL_WITHOUT_FINISH"})
    event(events_path, "eof-without-finish", requestId=REQUEST_ID)
    sys.exit(0)

if mode == "error":
    finish("error", {"message": "G3A_FAKE_PROVIDER_ERROR", "code": "SERVER"})
    emit({"v": 1, "type": "done", "requestId": REQUEST_ID, "exitReason": "error-finish"})
    sys.exit(0)

if mode == "slow":
    chunk({"type": "block-start", "index": 0, "blockType": "text"})
    chunk({"type": "text-delta", "index": 0, "text": "G3A_BRIDGE_SLOW_"})
    sys.stderr.write(f"G3A_FAKE_STREAMING {REQUEST_ID} {os.getpid()}\n")
    sys.stderr.flush()
    event(events_path, "slow-streaming", requestId=REQUEST_ID)
    deadline = time.monotonic() + MAX_LIFETIME_SECONDS
    cancelled = False
    while time.monotonic() < deadline:
        ready, _, _ = select.select([sys.stdin], [], [], 0.2)
        if not ready:
            continue
        line = sys.stdin.buffer.readline()
        if not line:
            break
        try:
            control = json.loads(line)
        except json.JSONDecodeError:
            continue
        if control.get("type") == "cancel":
            cancelled = True
            emit({"v": 1, "type": "cancelled", "requestId": REQUEST_ID})
            event(events_path, "cancel-ack", requestId=REQUEST_ID)
            break
    if not cancelled:
        event(events_path, "slow-timeout", requestId=REQUEST_ID)
        sys.exit(4)
    sys.exit(0)

if mode == "tool":
    call_id = "g3a-tool-1"
    arguments = '{"skill_id":"binary_search"}'
    chunk({"type": "block-start", "index": 0, "blockType": "tool-call"})
    chunk({"type": "tool-call-delta", "index": 0, "id": call_id, "name": "skill_lookup", "argumentsDelta": arguments})
    chunk({"type": "block-end", "index": 0, "block": {"type": "tool-call", "id": call_id, "name": "skill_lookup", "arguments": arguments}})
    usage()
    finish("tool-calls")
    emit({"v": 1, "type": "done", "requestId": REQUEST_ID, "exitReason": "tool-calls"})
    sys.exit(0)

if mode == "tool-final":
    tool_message = next((message for message in reversed(messages) if message.get("role") == "tool"), None)
    rendered = text_blocks(tool_message or {})
    try:
        value = json.loads(rendered)
    except json.JSONDecodeError:
        value = {}
    prerequisites = value.get("prerequisites") if isinstance(value, dict) else None
    count = len(prerequisites) if isinstance(prerequisites, list) else -1
    is_error = bool((tool_message or {}).get("isError", False))
    emit_text(f"G3A_TOOL_RESULT:binary_search:{count}:{str(is_error).lower()}")
    emit({"v": 1, "type": "done", "requestId": REQUEST_ID, "exitReason": "tool-final"})
    sys.exit(0)

if mode == "echo":
    nonce = find_nonce(messages, last_only=True) or "NO_NONCE"
    emit_text(f"G3A_BRIDGE_ECHO:{nonce}")
    emit({"v": 1, "type": "done", "requestId": REQUEST_ID, "exitReason": "echo"})
    sys.exit(0)

# Recall selects the earliest genuine user nonce from the assembled history.
nonce = find_nonce(messages, last_only=False) or "NO_NONCE"
emit_text(f"G3A_BRIDGE_RECALL:{nonce}")
emit({"v": 1, "type": "done", "requestId": REQUEST_ID, "exitReason": "recall"})
sys.exit(0)
