"""Strict Envelope codec and per-kind payload validators for G3-B IPC v1.

Every frame is one UTF-8 JSON object on its own line. Parsing checks the byte
budget BEFORE JSON decoding, rejects duplicate keys/NaN/Infinity/bad UTF-8,
unknown or missing fields, bool-as-int confusion, control characters, excessive
depth and malformed hashes. Validation never forwards arbitrary subprocess JSON
to DSH.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Mapping

from . import (
    BridgeError,
    MAX_JSON_DEPTH,
    MAX_REQUEST_BYTES,
)

KINDS = frozenset({"request", "ack", "chunk", "finish", "error", "cancel", "receipt"})
DIRECTIONS = frozenset({"in", "out"})

ERROR_CODES = frozenset({
    "PROTOCOL_VERSION", "UNKNOWN_KIND", "UNKNOWN_FIELD", "DUPLICATE_KEY",
    "BAD_TYPE", "NAN_OR_INF", "FRAME_TOO_LARGE", "RESPONSE_FRAME_TOO_LARGE",
    "TOTAL_BYTES_EXCEEDED", "DEPTH_EXCEEDED", "SEQ_OUT_OF_ORDER",
    "REQUEST_INVALID", "ADMISSION_MISSING", "ADMISSION_INVALID",
    "ADMISSION_EXPIRED", "ADMISSION_SCOPE_MISMATCH",
    "ADMISSION_ROUTE_NOT_ALLOWED", "ADMISSION_TOOL_SCHEMA_MISMATCH",
    "ADMISSION_LAUNCHER_MISMATCH", "ADMISSION_REPLAYED",
    "ADMISSION_SELF_AUTH_DENIED", "PREPARED_SCHEMA_INVALID",
    "PREPARED_DIGEST_MISMATCH", "BUDGET_DENIED", "ROUTE_MISMATCH",
    "CLAIM_DENIED", "CLAIM_BINDING_UNSUPPORTED", "ATTEMPT_JOURNAL_UNAVAILABLE",
    "ATTEMPT_ALREADY_STARTED", "FAKE_UNAVAILABLE", "FAKE_IO_ERROR",
    "FAKE_RECEIPT_MISMATCH", "USAGE_INVALID", "SETTLEMENT_UNCERTAIN",
    "CANCELLED", "INTERNAL",
    # G3-C additive, frozen Broker abstraction codes (raw Broker codes such as
    # CALL_ID_CONFLICT must never surface as a generic client UNKNOWN_FIELD).
    "BROKER_CALL_ID_CONFLICT", "BROKER_IDEMPOTENCY_CONFLICT",
    "BROKER_ALREADY_SETTLED", "BROKER_ALREADY_FAILED", "BROKER_INVALID_USAGE",
    "BROKER_ERROR", "BROKER_TIMEOUT", "DEADLINE_EXCEEDED",
    "TOO_MANY_CONNECTIONS",
})

# Deliberately finite: raw Broker protocol codes are implementation details.
# They are mapped to the frozen IPC abstraction before an Envelope is built.
BROKER_ERROR_CODE_MAP = {
    "CALL_ID_CONFLICT": "BROKER_CALL_ID_CONFLICT",
    "IDEMPOTENCY_CONFLICT": "BROKER_IDEMPOTENCY_CONFLICT",
    "ALREADY_SETTLED": "BROKER_ALREADY_SETTLED",
    "ALREADY_FAILED": "BROKER_ALREADY_FAILED",
    "INVALID_USAGE": "BROKER_INVALID_USAGE",
    "INTERNAL_ERROR": "BROKER_ERROR",
}


def normalize_broker_error_code(code: object) -> str:
    """Map one raw Broker code to a frozen IPC code (unknown -> BROKER_ERROR).

    Fail-closed by construction: no raw/unknown Broker string can become a
    success or a client-side UNKNOWN_FIELD. Codes that are already valid IPC
    codes are preserved so an additive Broker-side code can be surfaced.
    """
    if not isinstance(code, str):
        return "BROKER_ERROR"
    mapped = BROKER_ERROR_CODE_MAP.get(code)
    if mapped is not None:
        return mapped
    if code in ERROR_CODES:
        return code
    return "BROKER_ERROR"

_TRANSPORT_ID = re.compile(r"tr-[0-9a-f]{32}\Z", re.ASCII)
_HEX64 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_BLOCK_TYPES = frozenset({"text", "reasoning", "image", "file", "tool-call",
                          "tool-addition", "tool-removal"})
_CHUNK_TYPES = frozenset({"block-start", "text-delta", "reasoning-delta",
                          "tool-call-delta", "block-end", "usage"})
_FINISH_KINDS = frozenset({"stop", "tool-calls", "max-tokens", "aborted", "error", "blocked"})
_CANCEL_REASONS = frozenset({"aborted", "timeout", "controller_shutdown"})
_REQUEST_KEYS = frozenset({"sessionId", "provider", "model", "messages", "tools",
                           "system", "maxTokens", "stream", "purpose"})
_USAGE_REQUIRED = ("inputTokens", "outputTokens")
_USAGE_OPTIONAL = ("totalTokens", "cacheReadTokens", "cacheWriteTokens", "reasoningTokens")


def _fail(code: str, message: str = "") -> None:
    raise BridgeError(code, message)


def _is_int(value: object) -> bool:
    return type(value) is int


def _is_bool(value: object) -> bool:
    return type(value) is bool


def _bounded_text(value: object, *, field: str, maximum: int = 512) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= maximum:
        _fail("BAD_TYPE", field)
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in value):
        _fail("BAD_TYPE", f"{field}:control")
    return value


def _require_int(value: object, *, field: str, minimum: int = 0,
                 maximum: int | None = None) -> int:
    if not _is_int(value) or value < minimum or (maximum is not None and value > maximum):
        _fail("BAD_TYPE", field)
    return value


def _reject_constant(token: str) -> None:
    _fail("NAN_OR_INF", token)


class _DuplicateKey(ValueError):
    pass


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKey(key)
        result[key] = value
    return result


def _check_tree(value: object, depth: int = 0) -> None:
    if depth > MAX_JSON_DEPTH:
        _fail("DEPTH_EXCEEDED")
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                _fail("BAD_TYPE", "non-string object key")
            if any(ord(char) < 0x20 and char not in "\t\n\r" or ord(char) == 0x7F
                   for char in key):
                _fail("BAD_TYPE", "control character in key")
            _check_tree(item, depth + 1)
    elif isinstance(value, list):
        for item in value:
            _check_tree(item, depth + 1)
    elif isinstance(value, str):
        # JSON framing is one physical line; escaped tab/LF/CR inside a JSON
        # string are legal payload (DSH system-reminders contain newlines) and
        # cannot break the wire frame. NUL/other C0 controls stay rejected.
        if any((ord(char) < 0x20 and char not in "\t\n\r") or ord(char) == 0x7F
               for char in value):
            _fail("BAD_TYPE", "control character in string")
    elif isinstance(value, (int, float, bool)) or value is None:
        if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
            _fail("NAN_OR_INF")
    else:
        _fail("BAD_TYPE", "unsupported JSON value")


def _strict_json(raw: bytes) -> object:
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        _fail("BAD_TYPE", "invalid utf-8")
    try:
        value = json.loads(text, object_pairs_hook=_pairs,
                           parse_constant=_reject_constant)
    except _DuplicateKey:
        _fail("DUPLICATE_KEY")
    except BridgeError:
        raise
    except (ValueError, json.JSONDecodeError):
        _fail("REQUEST_INVALID", "invalid json")
    return value


def canonical_payload_bytes(payload: Mapping[str, Any]) -> bytes:
    if not isinstance(payload, dict):
        _fail("BAD_TYPE", "payload")
    _check_tree(payload)
    try:
        return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError):
        _fail("REQUEST_INVALID", "payload not canonicalizable")


def payload_digest(payload_bytes: bytes) -> str:
    if not isinstance(payload_bytes, (bytes, bytearray)):
        _fail("BAD_TYPE", "payload_bytes")
    return hashlib.sha256(bytes(payload_bytes)).hexdigest()


@dataclass(frozen=True)
class Envelope:
    v: int
    kind: str
    transport_id: str
    seq: int
    payload: dict[str, Any]
    hash: str | None


def _validate_usage(usage: object) -> None:
    if not isinstance(usage, dict):
        _fail("BAD_TYPE", "usage")
    keys = set(usage)
    if not set(_USAGE_REQUIRED) <= keys or keys - set(_USAGE_REQUIRED) - set(_USAGE_OPTIONAL):
        _fail("UNKNOWN_FIELD", "usage")
    for name in _USAGE_REQUIRED + _USAGE_OPTIONAL:
        if name in usage:
            _require_int(usage[name], field=f"usage.{name}")


def validate_request_payload(payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        _fail("BAD_TYPE", "request payload")
    keys = set(payload)
    if keys - _REQUEST_KEYS:
        _fail("UNKNOWN_FIELD", sorted(keys - _REQUEST_KEYS)[0])
    if _REQUEST_KEYS - keys:
        _fail("REQUEST_INVALID", sorted(_REQUEST_KEYS - keys)[0])
    session = _bounded_text(payload["sessionId"], field="sessionId")
    if not 1 <= len(session) <= 512:
        _fail("BAD_TYPE", "sessionId")
    _bounded_text(payload["provider"], field="provider", maximum=128)
    _bounded_text(payload["model"], field="model", maximum=128)
    if not isinstance(payload["messages"], list) or len(payload["messages"]) > 256:
        _fail("BAD_TYPE", "messages")
    if not isinstance(payload["tools"], list) or len(payload["tools"]) > 64:
        _fail("BAD_TYPE", "tools")
    if payload["system"] is not None:
        if not isinstance(payload["system"], str) or len(payload["system"]) > 131_072:
            _fail("BAD_TYPE", "system")
    _require_int(payload["maxTokens"], field="maxTokens", minimum=1, maximum=1024)
    if not _is_bool(payload["stream"]) or payload["stream"] is not True:
        _fail("BAD_TYPE", "stream")
    if payload["purpose"] not in (None, "conversation"):
        _fail("BAD_TYPE", "purpose")
    _check_tree(payload)
    if len(canonical_payload_bytes(payload)) > MAX_REQUEST_BYTES:
        _fail("FRAME_TOO_LARGE", "request payload")


def validate_chunk_payload(payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict) or set(payload) != {"chunk"}:
        _fail("UNKNOWN_FIELD", "chunk payload")
    chunk = payload["chunk"]
    if not isinstance(chunk, dict) or not isinstance(chunk.get("type"), str):
        _fail("BAD_TYPE", "chunk")
    kind = chunk["type"]
    if kind not in _CHUNK_TYPES:
        _fail("UNKNOWN_FIELD", f"chunk.{kind}")
    if kind == "block-start":
        expected = {"type", "index", "blockType"}
        if set(chunk) != expected:
            _fail("UNKNOWN_FIELD", "chunk block-start")
        _require_int(chunk["index"], field="chunk.index")
        if chunk["blockType"] not in _BLOCK_TYPES:
            _fail("BAD_TYPE", "chunk.blockType")
    elif kind in {"text-delta", "reasoning-delta"}:
        if set(chunk) != {"type", "index", "text"}:
            _fail("UNKNOWN_FIELD", kind)
        _require_int(chunk["index"], field="chunk.index")
        if not isinstance(chunk["text"], str):
            _fail("BAD_TYPE", "chunk.text")
    elif kind == "tool-call-delta":
        if set(chunk) - {"type", "index", "id", "name", "argumentsDelta"} or \
                not {"type", "index", "id", "argumentsDelta"} <= set(chunk):
            _fail("UNKNOWN_FIELD", "chunk tool-call-delta")
        _require_int(chunk["index"], field="chunk.index")
        _bounded_text(chunk["id"], field="chunk.id", maximum=256)
        if "name" in chunk:
            _bounded_text(chunk["name"], field="chunk.name", maximum=256)
        if not isinstance(chunk["argumentsDelta"], str):
            _fail("BAD_TYPE", "chunk.argumentsDelta")
    elif kind == "block-end":
        if set(chunk) != {"type", "index", "block"}:
            _fail("UNKNOWN_FIELD", "chunk block-end")
        _require_int(chunk["index"], field="chunk.index")
        block = chunk["block"]
        if not isinstance(block, dict) or block.get("type") not in _BLOCK_TYPES:
            _fail("BAD_TYPE", "chunk.block")
    else:  # usage
        if set(chunk) != {"type", "usage"}:
            _fail("UNKNOWN_FIELD", "chunk usage")
        _validate_usage(chunk["usage"])
    _check_tree(payload)
    if len(canonical_payload_bytes(payload)) > 65_536:
        _fail("RESPONSE_FRAME_TOO_LARGE", "chunk")


def _validate_ack(payload: dict[str, Any]) -> None:
    if set(payload) != {"request_id", "accepted", "code"}:
        _fail("UNKNOWN_FIELD", "ack")
    _bounded_text(payload["request_id"], field="ack.request_id")
    if payload["accepted"] is not True:
        _fail("BAD_TYPE", "ack.accepted")
    if payload["code"] is not None:
        _fail("BAD_TYPE", "ack.code")


def validate_finish_payload(payload: dict[str, Any]) -> None:
    """Validate the terminal finish schema (error/aborted require failure)."""
    if set(payload) != {"reason"}:
        _fail("UNKNOWN_FIELD", "finish")
    reason = payload["reason"]
    if not isinstance(reason, dict) or reason.get("kind") not in _FINISH_KINDS:
        _fail("BAD_TYPE", "finish.reason")
    kind = reason["kind"]
    expected = {"kind"} if kind in {"stop", "tool-calls", "max-tokens", "blocked"} \
        else {"kind", "failure"}
    if set(reason) != expected:
        _fail("UNKNOWN_FIELD", "finish.reason")
    if "failure" in reason:
        failure = reason["failure"]
        if not isinstance(failure, dict) or set(failure) != {"message", "code"}:
            _fail("UNKNOWN_FIELD", "finish.failure")
        _bounded_text(failure["message"], field="finish.message")
        _bounded_text(failure["code"], field="finish.code")


def _validate_error(payload: dict[str, Any]) -> None:
    if set(payload) != {"code", "message", "retryable"}:
        _fail("UNKNOWN_FIELD", "error")
    if payload["code"] not in ERROR_CODES:
        _fail("UNKNOWN_FIELD", "error.code")
    _bounded_text(payload["message"], field="error.message")
    if payload["retryable"] is not False:
        _fail("BAD_TYPE", "error.retryable")


def _validate_cancel(payload: dict[str, Any]) -> None:
    if set(payload) != {"request_id", "reason"}:
        _fail("UNKNOWN_FIELD", "cancel")
    _bounded_text(payload["request_id"], field="cancel.request_id")
    if payload["reason"] not in _CANCEL_REASONS:
        _fail("BAD_TYPE", "cancel.reason")


def _validate_receipt(payload: dict[str, Any]) -> None:
    required = {"receipt_id", "raw_sha256", "raw_length", "mode", "usage", "nonce", "utc"}
    if set(payload) != required:
        _fail("UNKNOWN_FIELD", "receipt")
    _bounded_text(payload["receipt_id"], field="receipt.receipt_id")
    if not isinstance(payload["raw_sha256"], str) or not _HEX64.fullmatch(payload["raw_sha256"]):
        _fail("BAD_TYPE", "receipt.raw_sha256")
    _require_int(payload["raw_length"], field="receipt.raw_length")
    _bounded_text(payload["mode"], field="receipt.mode", maximum=64)
    if payload["usage"] is not None:
        _validate_usage(payload["usage"])
    if not isinstance(payload["nonce"], str) or not re.fullmatch(r"[0-9a-f]{32}", payload["nonce"]):
        _fail("BAD_TYPE", "receipt.nonce")
    _bounded_text(payload["utc"], field="receipt.utc", maximum=64)


_VALIDATORS = {
    "request": validate_request_payload,
    "ack": _validate_ack,
    "chunk": validate_chunk_payload,
    "finish": validate_finish_payload,
    "error": _validate_error,
    "cancel": _validate_cancel,
    "receipt": _validate_receipt,
}


def parse_envelope(line: bytes) -> Envelope:
    """Parse one bounded frame; byte limit is enforced before JSON decoding."""
    if not isinstance(line, (bytes, bytearray)):
        _fail("BAD_TYPE", "frame")
    raw = bytes(line)
    if len(raw) > MAX_REQUEST_BYTES:
        _fail("FRAME_TOO_LARGE")
    if b"\r" in raw:
        _fail("REQUEST_INVALID", "CR")
    if raw.endswith(b"\n"):
        raw = raw[:-1]
    if b"\n" in raw or not raw:
        _fail("REQUEST_INVALID", "frame must be exactly one line")
    value = _strict_json(raw)
    if not isinstance(value, dict):
        _fail("BAD_TYPE", "envelope")
    keys = set(value)
    allowed = {"v", "kind", "transport_id", "seq", "payload", "hash"}
    if keys - allowed:
        _fail("UNKNOWN_FIELD", sorted(keys - allowed)[0])
    if not {"v", "kind", "transport_id", "seq", "payload"} <= keys:
        _fail("REQUEST_INVALID", "missing envelope field")
    v = value["v"]
    if not _is_int(v) or v != 1:
        _fail("PROTOCOL_VERSION")
    kind = value["kind"]
    if not isinstance(kind, str) or kind not in KINDS:
        _fail("UNKNOWN_KIND")
    transport_id = value["transport_id"]
    if not isinstance(transport_id, str) or not _TRANSPORT_ID.fullmatch(transport_id):
        _fail("BAD_TYPE", "transport_id")
    seq = value["seq"]
    if not _is_int(seq) or seq < 0:
        _fail("BAD_TYPE", "seq")
    payload = value["payload"]
    if not isinstance(payload, dict):
        _fail("BAD_TYPE", "payload")
    _check_tree(value)
    expected_hash = payload_digest(canonical_payload_bytes(payload))
    recorded_hash = value.get("hash")
    if recorded_hash is not None:
        if not isinstance(recorded_hash, str) or not _HEX64.fullmatch(recorded_hash):
            _fail("BAD_TYPE", "hash")
        if recorded_hash != expected_hash:
            _fail("PREPARED_DIGEST_MISMATCH", "envelope hash")
    _VALIDATORS[kind](payload)
    return Envelope(v=v, kind=kind, transport_id=transport_id, seq=seq,
                    payload=dict(payload), hash=recorded_hash)


def encode_envelope(env: Envelope) -> bytes:
    if not isinstance(env, Envelope):
        _fail("BAD_TYPE", "envelope")
    if env.v != 1:
        _fail("PROTOCOL_VERSION")
    if env.kind not in KINDS:
        _fail("UNKNOWN_KIND")
    if not isinstance(env.transport_id, str) or not _TRANSPORT_ID.fullmatch(env.transport_id):
        _fail("BAD_TYPE", "transport_id")
    if not _is_int(env.seq) or env.seq < 0:
        _fail("BAD_TYPE", "seq")
    _VALIDATORS[env.kind](env.payload)
    digest = payload_digest(canonical_payload_bytes(env.payload))
    recorded = env.hash if env.hash is not None else digest
    if recorded != digest:
        _fail("PREPARED_DIGEST_MISMATCH", "envelope hash")
    value = {"v": 1, "kind": env.kind, "transport_id": env.transport_id,
             "seq": env.seq, "payload": env.payload, "hash": recorded}
    _check_tree(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def validate_error_payload(code: str, message: str = "") -> dict[str, Any]:
    if code not in ERROR_CODES:
        _fail("UNKNOWN_FIELD", code)
    return {"code": code, "message": message or code, "retryable": False}


__all__ = [
    "BROKER_ERROR_CODE_MAP", "ERROR_CODES", "Envelope",
    "canonical_payload_bytes", "encode_envelope", "normalize_broker_error_code",
    "parse_envelope", "payload_digest", "validate_chunk_payload",
    "validate_error_payload", "validate_finish_payload",
    "validate_request_payload",
]
