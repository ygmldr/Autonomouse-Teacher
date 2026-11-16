"""G3-B B1 bridge protocol package.

Wire protocol: one UTF-8 JSON Envelope per line over AF_UNIX.
This package is transport/parser only; it never starts a provider, reads a Key,
opens a network socket or grants Live permission.
"""
from __future__ import annotations

PROTOCOL = "at-m0/g3b-bridge/v1"
MAX_REQUEST_BYTES = 262_144
MAX_RESPONSE_BYTES = 65_536
MAX_TOTAL_REQUEST_BYTES = 1_048_576
MAX_JSON_DEPTH = 32
MAX_STREAM_CHUNKS = 256
REQUEST_DEADLINE_SECONDS = 30.0
CLEANUP_GRACE_SECONDS = 1.0


class BridgeError(Exception):
    """Sanitized bridge failure; ``code`` is one of protocol.ERROR_CODES."""

    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        self.message = message
        super().__init__(code if not message else f"{code}: {message}")


__all__ = [
    "CLEANUP_GRACE_SECONDS",
    "MAX_JSON_DEPTH",
    "MAX_REQUEST_BYTES",
    "MAX_RESPONSE_BYTES",
    "MAX_STREAM_CHUNKS",
    "MAX_TOTAL_REQUEST_BYTES",
    "PROTOCOL",
    "REQUEST_DEADLINE_SECONDS",
    "BridgeError",
]
