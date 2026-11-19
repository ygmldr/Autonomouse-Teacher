"""G4-F2 per-dispatch tool/purpose/origin observability (no Key, no network).

The trusted Controller is the only place where the *actual* provider request is
known: the DSH candidate adapter is candidate-side code and the DSH runtime has
no authoritative merged tool-registry export (G4-B B03).  This module records,
for every request that reaches the Controller, a bounded, content-free
description of:

* the requested tool identities and their canonical JSON Schema SHA-256;
* the approved schema SHA-256 from the trusted Admission document;
* tool references embedded in message blocks (``tool-call`` /
  ``tool-addition`` / ``tool-removal``);
* the request ``purpose`` and the kernel-reported AF_UNIX peer (origin);
* the per-dispatch outcome and error code, so a rejection can be attributed to
  the pre-Reserve/Claim tool-surface gate rather than inferred from a log line.

The journal never contains prompts, message text, tool arguments or credentials.
Its only consumer is trusted evidence collection; a write failure is counted but
does not change dispatch semantics (the allowlist check itself is independent).
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

DISPATCH_AUDIT_SCHEMA = "m0.g4f.dispatch-window.v1"
MAX_AUDIT_TOOLS = 16
MAX_AUDIT_MESSAGE_REFS = 16
MAX_AUDIT_NAME = 128
MAX_AUDIT_TRANSPORT = 128
DEFAULT_AUDIT_FILENAME = "dispatch-window.jsonl"

_TOOL_BLOCK_TYPES = frozenset({"tool-call", "tool-addition", "tool-removal"})


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sanitize_name(value: object, *, maximum: int = MAX_AUDIT_NAME) -> str | None:
    """Return a bounded printable name, or ``None`` for a non-string value.

    JSON encoding already escapes newlines, but a bounded printable view keeps
    the evidence readable and prevents a hostile candidate from choosing a huge
    or control-character-only journal field.
    """
    if not isinstance(value, str) or not value:
        return None
    cleaned = "".join(
        char if ord(char) >= 0x20 and ord(char) != 0x7F else "?" for char in value)
    return cleaned[:maximum] or None


def canonical_tool_digest(tool: object) -> str | None:
    """Canonical SHA-256 of one tool schema (the Admission allowlist key)."""
    try:
        raw = json.dumps(tool, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError):
        return None
    return hashlib.sha256(raw).hexdigest()


def approved_set_digest(approved: Mapping[str, str]) -> str:
    """Digest of the approved ``(name, schema_sha256)`` set actually loaded."""
    material = sorted([str(name), str(digest)] for name, digest in approved.items())
    raw = json.dumps(material, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _purpose_view(payload: object) -> object:
    if not isinstance(payload, Mapping):
        return "<not_an_object>"
    value = payload.get("purpose")
    if "purpose" not in payload:
        return "<missing>"
    if value is None or isinstance(value, str):
        return sanitize_name(value) if isinstance(value, str) else None
    return "<invalid:" + type(value).__name__ + ">"


def describe_request(payload: object, *, approved: Mapping[str, str],
                     origin: Mapping[str, object] | None = None,
                     transport_id: object = None) -> dict:
    """Build one content-free dispatch record from an untrusted request payload.

    This function never raises for malformed input; it is an observation, not
    the enforcement gate.  The Controller validates independently and records
    the stable rejection code on the returned record.
    """
    tools = payload.get("tools") if isinstance(payload, Mapping) else None
    tools = tools if isinstance(tools, list) else []
    tool_rows: list[dict] = []
    for index, tool in enumerate(tools[:MAX_AUDIT_TOOLS]):
        if isinstance(tool, Mapping):
            name = sanitize_name(tool.get("name"))
            observed = canonical_tool_digest(tool)
            expected = approved.get(name) if name is not None else None
            tool_rows.append({
                "origin": "request.tools",
                "index": index,
                "name": name,
                "schema_sha256": observed,
                "approved_sha256": expected,
                "approved": expected is not None and expected == observed,
            })
        else:
            tool_rows.append({
                "origin": "request.tools", "index": index, "name": None,
                "schema_sha256": None, "approved_sha256": None,
                "approved": False, "malformed": True,
            })
    refs: list[dict] = []
    ref_count = 0
    messages = payload.get("messages") if isinstance(payload, Mapping) else None
    if isinstance(messages, list):
        for message_index, message in enumerate(messages):
            if not isinstance(message, Mapping):
                continue
            content = message.get("content")
            if not isinstance(content, list):
                continue
            for block_index, block in enumerate(content):
                if not isinstance(block, Mapping):
                    continue
                kind = block.get("type")
                if kind not in _TOOL_BLOCK_TYPES:
                    continue
                ref_count += 1
                if len(refs) >= MAX_AUDIT_MESSAGE_REFS:
                    continue
                name = sanitize_name(
                    block.get("toolName") if kind in {"tool-addition", "tool-removal"}
                    else block.get("name"))
                refs.append({
                    "origin": f"messages[{message_index}].content[{block_index}]",
                    "kind": kind,
                    "name": name,
                    "approved": name is not None and name in approved,
                })
    record = {
        "schema": DISPATCH_AUDIT_SCHEMA,
        "utc": utc_now(),
        "transport_id": (sanitize_name(transport_id, maximum=MAX_AUDIT_TRANSPORT)
                         if isinstance(transport_id, str) else None),
        "origin": dict(origin) if isinstance(origin, Mapping) else {"kind": "in_process"},
        "purpose": _purpose_view(payload),
        "tools": tool_rows,
        "tool_count": len(tools),
        "tools_truncated": len(tools) > MAX_AUDIT_TOOLS,
        "message_tool_refs": refs,
        "message_tool_ref_count": ref_count,
        "message_tool_refs_truncated": ref_count > MAX_AUDIT_MESSAGE_REFS,
        "approved_tool_set_sha256": approved_set_digest(approved),
        "outcome": "received",
        "reserved": False,
        "dispatched": False,
        "settled": False,
        "error_code": None,
    }
    return record


class DispatchAudit:
    """Append-only JSONL writer for per-dispatch records (best effort).

    ``errors`` / ``written`` are diagnostics for the trusted launcher; a write
    failure never opens or closes an allowlist decision.
    """

    def __init__(self, path: str | os.PathLike[str] | None = None) -> None:
        self.path = Path(path) if path is not None else None
        if self.path is not None and not self.path.is_absolute():
            raise ValueError("dispatch journal path must be absolute")
        self._lock = threading.Lock()
        self.written = 0
        self.errors = 0

    def append(self, record: Mapping[str, object]) -> bool:
        if self.path is None:
            return False
        try:
            data = (json.dumps(record, sort_keys=True, separators=(",", ":"),
                               ensure_ascii=True, allow_nan=False) + "\n").encode("utf-8")
        except (TypeError, ValueError):
            with self._lock:
                self.errors += 1
            return False
        flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            fd = os.open(self.path, flags, 0o600)
        except OSError:
            with self._lock:
                self.errors += 1
            return False
        try:
            os.write(fd, data)
            os.fsync(fd)
        except OSError:
            with self._lock:
                self.errors += 1
            return False
        finally:
            os.close(fd)
        with self._lock:
            self.written += 1
        return True


def default_journal_path(attempt_db: str | os.PathLike[str]) -> Path:
    """Journal lives beside the trusted Attempt DB (same 0700 state dir)."""
    return Path(attempt_db).with_name(DEFAULT_AUDIT_FILENAME)
