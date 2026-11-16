"""AF_UNIX line-framed Envelope server for G3-B B1.

The DSH candidate adapter connects to one fixed path. This module enforces
bounded framing (byte limits before JSON), first-frame ack semantics, response
frame/total limits, chunk/finish ordering, duplicate-finish rejection, a
per-request deadline and fail-closed cleanup. It only forwards validated
Envelope objects produced by a Controller; it never forwards raw subprocess
JSON and never spawns a provider.
"""
from __future__ import annotations

import os
from pathlib import Path
import socket
import threading
import time

from . import (
    BridgeError,
    CLEANUP_GRACE_SECONDS,
    MAX_REQUEST_BYTES,
    MAX_RESPONSE_BYTES,
    MAX_STREAM_CHUNKS,
    MAX_TOTAL_REQUEST_BYTES,
    REQUEST_DEADLINE_SECONDS,
)
from .protocol import (
    Envelope,
    encode_envelope,
    parse_envelope,
    validate_error_payload,
)

DEFAULT_SOCKET_PATH = "/work/g3b/bridge.sock"
_READ_CHUNK = 65_536
_ACCEPT_TIMEOUT = 0.5


class FrameReader:
    """Bounded newline reader: never buffers beyond ``max_bytes``."""

    def __init__(self, sock: socket.socket, *, max_bytes: int = MAX_REQUEST_BYTES) -> None:
        self._socket = sock
        self._max_bytes = max_bytes
        self._buffer = bytearray()

    def readline(self) -> bytes | None:
        while True:
            index = self._buffer.find(b"\n")
            if index >= 0:
                line = bytes(self._buffer[: index + 1])
                del self._buffer[: index + 1]
                if len(line) > self._max_bytes:
                    raise BridgeError("FRAME_TOO_LARGE")
                return line
            if len(self._buffer) >= self._max_bytes:
                raise BridgeError("FRAME_TOO_LARGE")
            try:
                chunk = self._socket.recv(_READ_CHUNK)
            except socket.timeout:
                # Caller owns the deadline; keep waiting without growing memory.
                continue
            if not chunk:
                if self._buffer:
                    raise BridgeError("REQUEST_INVALID", "truncated frame at EOF")
                return None
            self._buffer.extend(chunk)
            if len(self._buffer) > self._max_bytes:
                # Drop the over-limit tail before failing so memory stays bounded.
                del self._buffer[self._max_bytes:]
                raise BridgeError("FRAME_TOO_LARGE")

    def buffered_bytes(self) -> int:
        return len(self._buffer)


class BridgeServer:
    """One-connection-per-thread UDS server; Controller owns send permission."""

    def __init__(self, controller, socket_path: str = DEFAULT_SOCKET_PATH) -> None:
        if not isinstance(socket_path, str) or not socket_path.startswith("/"):
            raise ValueError("socket_path must be absolute")
        if not hasattr(controller, "handle_envelope"):
            raise ValueError("controller must expose handle_envelope(env)")
        self.controller = controller
        self.socket_path = socket_path
        self._stop = threading.Event()
        self._server: socket.socket | None = None
        self._threads: list[threading.Thread] = []

    # -- lifecycle -----------------------------------------------------
    def serve_forever(self) -> None:
        parent = Path(self.socket_path).parent
        parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if os.path.lexists(self.socket_path):
            raise RuntimeError("bridge socket path already exists")
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server = server
        try:
            server.bind(self.socket_path)
            os.chmod(self.socket_path, 0o600)
            server.listen(2)
            server.settimeout(_ACCEPT_TIMEOUT)
            while not self._stop.is_set():
                try:
                    conn, _ = server.accept()
                except socket.timeout:
                    continue
                except OSError:
                    if self._stop.is_set():
                        break
                    raise
                thread = threading.Thread(target=self._connection_thread,
                                          args=(conn,), daemon=True)
                self._threads.append(thread)
                thread.start()
        finally:
            try:
                server.close()
            finally:
                if os.path.exists(self.socket_path):
                    try:
                        os.unlink(self.socket_path)
                    except OSError:
                        pass

    def shutdown(self) -> None:
        self._stop.set()
        if self._server is not None:
            try:
                self._server.close()
            except OSError:
                pass

    def _connection_thread(self, conn: socket.socket) -> None:
        try:
            self.handle_connection(conn)
        except BaseException:
            # Connection errors are per-connection; never kill the accept loop.
            pass
        finally:
            try:
                conn.close()
            except OSError:
                pass

    # -- framing / protocol -------------------------------------------
    def handle_connection(self, conn: socket.socket) -> None:
        conn.settimeout(1.0)
        reader = FrameReader(conn)
        try:
            line = reader.readline()
        except BridgeError as error:
            self._try_send_error(conn, None, 1, error.code)
            return
        if line is None:
            return
        try:
            request = parse_envelope(line)
        except BridgeError as error:
            self._try_send_error(conn, None, 1, error.code)
            return
        if request.kind != "request":
            self._try_send_error(conn, request.transport_id, 1, "UNKNOWN_KIND")
            return
        if request.seq != 0:
            self._try_send_error(conn, request.transport_id, 1, "SEQ_OUT_OF_ORDER")
            return
        transport_id = request.transport_id
        deadline = time.monotonic() + REQUEST_DEADLINE_SECONDS
        cancel_event = threading.Event()
        cancel_reason: list[str] = []
        cancel_reader = threading.Thread(
            target=self._cancel_reader,
            args=(conn, reader, transport_id, request.seq, cancel_event, cancel_reason),
            daemon=True)
        cancel_reader.start()
        try:
            # §5.2 v1.1: ack is emitted after schema-valid request, BEFORE any
            # controller/admission/budget/claim output. ack != grant.
            self._send(conn, Envelope(v=1, kind="ack", transport_id=transport_id, seq=1,
                                      payload={"request_id": transport_id, "accepted": True,
                                               "code": None}, hash=None))
            seq = 2
            total_bytes = self._last_frame_bytes
            chunk_count = 0
            finish_seen = False
            try:
                responses = iter(self.controller.handle_envelope(request))
            except TypeError:
                self._send_error(conn, transport_id, seq, "INTERNAL")
                return
            try:
                while not finish_seen:
                    if time.monotonic() > deadline:
                        self._send_error(conn, transport_id, seq, "SETTLEMENT_UNCERTAIN")
                        return
                    if self._stop.is_set():
                        return
                    try:
                        response = next(responses)
                    except StopIteration:
                        break
                    except BridgeError as error:
                        self._send_error(conn, transport_id, seq, error.code)
                        return
                    except BaseException:
                        self._send_error(conn, transport_id, seq, "INTERNAL")
                        return
                    if not isinstance(response, Envelope):
                        self._send_error(conn, transport_id, seq, "BAD_TYPE")
                        return
                    if response.kind == "ack":
                        # Server already emitted the only ack; tolerate a
                        # controller passthrough but never duplicate it.
                        continue
                    if response.kind == "chunk":
                        chunk_count += 1
                        if chunk_count > MAX_STREAM_CHUNKS:
                            self._send_error(conn, transport_id, seq, "INTERNAL")
                            return
                    elif response.kind == "finish":
                        if finish_seen:
                            self._send_error(conn, transport_id, seq, "INTERNAL")
                            return
                    elif response.kind not in {"error"}:
                        self._send_error(conn, transport_id, seq, "UNKNOWN_KIND")
                        return
                    try:
                        frame = encode_envelope(Envelope(
                            v=1, kind=response.kind, transport_id=transport_id,
                            seq=seq, payload=dict(response.payload), hash=None))
                    except BridgeError as error:
                        self._send_error(conn, transport_id, seq, error.code)
                        return
                    frame += b"\n"
                    if len(frame) > MAX_RESPONSE_BYTES:
                        self._send_error(conn, transport_id, seq,
                                         "RESPONSE_FRAME_TOO_LARGE")
                        return
                    if total_bytes + len(frame) > MAX_TOTAL_REQUEST_BYTES:
                        self._send_error(conn, transport_id, seq, "TOTAL_BYTES_EXCEEDED")
                        return
                    conn.sendall(frame)
                    total_bytes += len(frame)
                    self._last_frame_bytes = len(frame)
                    seq += 1
                    if response.kind == "finish":
                        finish_seen = True
                    elif response.kind == "error":
                        return
                if not finish_seen:
                    # EOF before finish: adapter must see a failure, never a
                    # synthetic success. Unknown send state is conservative.
                    self._send_error(conn, transport_id, seq, "SETTLEMENT_UNCERTAIN")
            finally:
                try:
                    close = getattr(responses, "close", None)
                    if callable(close):
                        close()
                except BaseException:
                    pass
        finally:
            cancel_event.set()
            cancel_reader.join(timeout=CLEANUP_GRACE_SECONDS)

    # -- internals -----------------------------------------------------
    _last_frame_bytes = 0

    def _cancel_reader(self, conn: socket.socket, reader: FrameReader,
                       transport_id: str, request_seq: int,
                       cancel_event: threading.Event, reason_sink: list[str]) -> None:
        last_seq = request_seq
        try:
            while not cancel_event.is_set():
                try:
                    line = reader.readline()
                except BridgeError:
                    return
                except OSError:
                    return
                if line is None:
                    return
                try:
                    env = parse_envelope(line)
                except BridgeError:
                    continue
                if env.kind != "cancel" or env.seq <= last_seq:
                    continue
                last_seq = env.seq
                reason = str(env.payload["reason"])
                reason_sink.append(reason)
                handler = getattr(self.controller, "cancel", None)
                if callable(handler):
                    try:
                        handler(transport_id=transport_id, reason=reason)
                    except BaseException:
                        pass
        finally:
            cancel_event.set()

    def _send(self, conn: socket.socket, env: Envelope) -> None:
        frame = encode_envelope(env) + b"\n"
        if len(frame) > MAX_RESPONSE_BYTES:
            raise BridgeError("RESPONSE_FRAME_TOO_LARGE")
        conn.sendall(frame)
        self._last_frame_bytes = len(frame)

    def _send_error(self, conn: socket.socket, transport_id: str | None, seq: int,
                    code: str) -> None:
        try:
            payload = validate_error_payload(code)
            self._send(conn, Envelope(v=1, kind="error",
                                      transport_id=transport_id or "tr-" + "0" * 32,
                                      seq=seq, payload=payload, hash=None))
        except (BridgeError, OSError):
            pass

    def _try_send_error(self, conn: socket.socket, transport_id: str | None,
                        seq: int, code: str) -> None:
        self._send_error(conn, transport_id, seq, code)
