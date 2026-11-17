"""AF_UNIX line-framed Envelope server for G3-B/G3-C.

The DSH candidate adapter connects to one fixed path. This module enforces
bounded framing (byte limits before JSON), first-frame ack semantics, response
frame/total limits, chunk/finish ordering, duplicate-finish rejection, a real
monotonic deadline (including a watchdog for synchronous Controller work),
an active-connection cap and fail-closed cleanup. It only forwards validated
Envelope objects produced by a Controller; it never forwards raw subprocess
JSON and never spawns a provider.
"""
from __future__ import annotations

import logging
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
DEFAULT_MAX_CONNECTIONS = 8
_READ_CHUNK = 65_536
_ACCEPT_TIMEOUT = 0.25
_POLL_INTERVAL = 0.25
_ZERO_TRANSPORT = "tr-" + "0" * 32
_LOGGER = logging.getLogger(__name__)


class FrameReader:
    """Bounded newline reader: never buffers beyond ``max_bytes``.

    Every blocking ``recv`` is bounded by a small poll slice and re-checks the
    caller's monotonic deadline/stop event. ``socket.timeout`` is never an
    unbounded "continue": an expired deadline or a stopped reader returns or
    raises deterministically.
    """

    def __init__(self, sock: socket.socket, *, max_bytes: int = MAX_REQUEST_BYTES) -> None:
        self._socket = sock
        self._max_bytes = max_bytes
        self._buffer = bytearray()

    def readline(self, *, deadline_monotonic: float | None = None,
                 stop_event: threading.Event | None = None,
                 poll_interval: float = _POLL_INTERVAL) -> bytes | None:
        if poll_interval <= 0:
            raise ValueError("poll_interval must be positive")
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
            if stop_event is not None and stop_event.is_set():
                return None
            if deadline_monotonic is not None:
                remaining = deadline_monotonic - time.monotonic()
                if remaining <= 0:
                    raise BridgeError("DEADLINE_EXCEEDED")
                timeout = min(poll_interval, max(remaining, 0.001))
            else:
                timeout = poll_interval
            try:
                self._socket.settimeout(timeout)
                chunk = self._socket.recv(_READ_CHUNK)
            except socket.timeout:
                # Bounded by the deadline/stop checks above; never infinite.
                continue
            except OSError as exc:
                if stop_event is not None and stop_event.is_set():
                    return None
                raise BridgeError("REQUEST_INVALID", "socket closed") from exc
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


class _ConnectionContext:
    """Per-connection mutable state (never shared across connections)."""

    __slots__ = ("sock", "lock", "done", "expired", "transport_id", "seq",
                 "total_bytes", "chunk_count")

    def __init__(self, sock: socket.socket) -> None:
        self.sock = sock
        self.lock = threading.Lock()
        self.done = threading.Event()
        self.expired = threading.Event()
        self.transport_id: str | None = None
        self.seq = 1
        self.total_bytes = 0
        self.chunk_count = 0


class BridgeServer:
    """One-connection-per-thread UDS server; Controller owns send permission."""

    def __init__(self, controller, socket_path: str = DEFAULT_SOCKET_PATH, *,
                 first_frame_deadline_s: float = REQUEST_DEADLINE_SECONDS,
                 request_deadline_s: float = REQUEST_DEADLINE_SECONDS,
                 max_connections: int = DEFAULT_MAX_CONNECTIONS,
                 accept_timeout_s: float = _ACCEPT_TIMEOUT) -> None:
        if not isinstance(socket_path, str) or not socket_path.startswith("/"):
            raise ValueError("socket_path must be absolute")
        if not hasattr(controller, "handle_envelope"):
            raise ValueError("controller must expose handle_envelope(env)")
        if not 0 < float(first_frame_deadline_s) < 3_600:
            raise ValueError("first_frame_deadline_s out of range")
        if not 0 < float(request_deadline_s) < 3_600:
            raise ValueError("request_deadline_s out of range")
        if type(max_connections) is not int or max_connections < 1:
            raise ValueError("max_connections must be a positive int")
        if not 0 < float(accept_timeout_s) < 60:
            raise ValueError("accept_timeout_s out of range")
        self.controller = controller
        self.socket_path = socket_path
        self.first_frame_deadline_s = float(first_frame_deadline_s)
        self.request_deadline_s = float(request_deadline_s)
        self.max_connections = max_connections
        self.accept_timeout_s = float(accept_timeout_s)
        self._stop = threading.Event()
        self._server: socket.socket | None = None
        self._lock = threading.Lock()
        self._active: set[_ConnectionContext] = set()
        self._threads: set[threading.Thread] = set()
        # Observable, sanitized diagnostics (no prompt/usage/key material).
        self.cancel_failures: list[str] = []
        self.connection_failures: list[str] = []

    # -- lifecycle -----------------------------------------------------
    @property
    def active_connections(self) -> int:
        with self._lock:
            return len(self._active)

    @property
    def thread_count(self) -> int:
        with self._lock:
            return len(self._threads)

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
            server.listen(max(2, self.max_connections))
            server.settimeout(self.accept_timeout_s)
            while not self._stop.is_set():
                try:
                    conn, _ = server.accept()
                except socket.timeout:
                    continue
                except OSError:
                    if self._stop.is_set():
                        break
                    raise
                accepted_at = time.monotonic()
                first_deadline = accepted_at + self.first_frame_deadline_s
                request_deadline = accepted_at + self.request_deadline_s
                context = _ConnectionContext(conn)
                thread = threading.Thread(
                    target=self._connection_thread,
                    args=(context, first_deadline, request_deadline),
                    name="g3c-bridge-connection", daemon=True)
                with self._lock:
                    if len(self._active) >= self.max_connections:
                        overloaded = True
                    else:
                        overloaded = False
                        self._active.add(context)
                        self._threads.add(thread)
                if overloaded:
                    self._reject_overloaded(context)
                    continue
                try:
                    thread.start()
                except BaseException:
                    with self._lock:
                        self._active.discard(context)
                        self._threads.discard(thread)
                    self._close_socket(conn)
                    raise
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
        with self._lock:
            contexts = list(self._active)
            threads = list(self._threads)
        for context in contexts:
            context.done.set()
            try:
                context.sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self._close_socket(context.sock)
        current = threading.current_thread()
        join_deadline = time.monotonic() + CLEANUP_GRACE_SECONDS
        for thread in threads:
            if thread is current:
                continue
            remaining = join_deadline - time.monotonic()
            if remaining <= 0:
                break
            thread.join(timeout=remaining)

    # -- per-connection -------------------------------------------------
    def _connection_thread(self, context: _ConnectionContext,
                           first_deadline: float, request_deadline: float) -> None:
        try:
            self.handle_connection(context, first_deadline, request_deadline)
        except BaseException as exc:  # keep the accept loop alive; log sanitized
            self._record_connection_failure(type(exc).__name__)
            _LOGGER.warning("bridge connection failed transport=%s type=%s",
                            context.transport_id, type(exc).__name__)
        finally:
            context.done.set()
            self._close_socket(context.sock)
            with self._lock:
                self._active.discard(context)
                self._threads.discard(threading.current_thread())

    def _reject_overloaded(self, context: _ConnectionContext) -> None:
        _LOGGER.warning("bridge connection rejected: max_connections=%d",
                        self.max_connections)
        try:
            context.transport_id = _ZERO_TRANSPORT
            context.seq = 1
            self._send_error_ctx(context, "TOO_MANY_CONNECTIONS")
        finally:
            self._close_socket(context.sock)

    def _record_connection_failure(self, name: str) -> None:
        with self._lock:
            if len(self.connection_failures) < 64:
                self.connection_failures.append(name)

    # -- framing / protocol -------------------------------------------
    def handle_connection(self, context: _ConnectionContext,
                          first_deadline: float,
                          request_deadline: float) -> None:
        conn = context.sock
        reader = FrameReader(conn)
        try:
            line = reader.readline(deadline_monotonic=first_deadline)
        except BridgeError as exc:
            self._send_error_ctx(context, exc.code)
            return
        except OSError:
            return
        if line is None:
            return
        try:
            request = parse_envelope(line)
        except BridgeError as exc:
            self._send_error_ctx(context, exc.code)
            return
        context.transport_id = request.transport_id
        context.seq = 1
        if request.kind != "request":
            self._send_error_ctx(context, "UNKNOWN_KIND")
            return
        if request.seq != 0:
            self._send_error_ctx(context, "SEQ_OUT_OF_ORDER")
            return
        transport_id = request.transport_id
        cancel_event = threading.Event()
        cancel_reason: list[str] = []
        cancel_reader = threading.Thread(
            target=self._cancel_reader,
            args=(context, reader, cancel_event, cancel_reason),
            name="g3c-bridge-cancel", daemon=True)
        cancel_reader.start()
        watchdog = threading.Thread(
            target=self._response_watchdog,
            args=(context, request_deadline),
            name="g3c-bridge-watchdog", daemon=True)
        watchdog.start()
        responses = None
        finish_seen = False
        try:
            # §5.2 v1.1: ack is emitted after schema-valid request, BEFORE any
            # controller/admission/budget/claim output. ack != grant.
            self._send_response(context, "ack",
                                {"request_id": transport_id, "accepted": True,
                                 "code": None})
            try:
                responses = iter(self.controller.handle_envelope(request))
            except TypeError:
                self._send_error_ctx(context, "INTERNAL")
                return
            while not finish_seen:
                if context.done.is_set() or context.expired.is_set():
                    return
                if self._stop.is_set():
                    return
                if time.monotonic() >= request_deadline:
                    self._send_error_ctx(context, "DEADLINE_EXCEEDED")
                    return
                try:
                    response = next(responses)
                except StopIteration:
                    break
                except BridgeError as exc:
                    self._send_error_ctx(context, exc.code)
                    return
                except BaseException:
                    self._send_error_ctx(context, "INTERNAL")
                    return
                if context.done.is_set() or context.expired.is_set():
                    return
                if not isinstance(response, Envelope):
                    self._send_error_ctx(context, "BAD_TYPE")
                    return
                if response.kind == "ack":
                    # Server already emitted the only ack; tolerate a
                    # controller passthrough but never duplicate it.
                    continue
                if response.kind == "chunk":
                    context.chunk_count += 1
                    if context.chunk_count > MAX_STREAM_CHUNKS:
                        self._send_error_ctx(context, "INTERNAL")
                        return
                elif response.kind == "finish":
                    if finish_seen:
                        self._send_error_ctx(context, "INTERNAL")
                        return
                elif response.kind not in {"error"}:
                    self._send_error_ctx(context, "UNKNOWN_KIND")
                    return
                try:
                    self._send_response(context, response.kind,
                                        dict(response.payload),
                                        terminal=response.kind in {"finish", "error"})
                except BridgeError as exc:
                    self._send_error_ctx(context, exc.code)
                    return
                if response.kind == "finish":
                    finish_seen = True
                elif response.kind == "error":
                    return
            if not finish_seen:
                # EOF before finish: adapter must see a failure, never a
                # synthetic success. Unknown send state is conservative.
                self._send_error_ctx(context, "SETTLEMENT_UNCERTAIN")
        finally:
            context.done.set()
            cancel_event.set()
            watchdog.join(timeout=CLEANUP_GRACE_SECONDS)
            cancel_reader.join(timeout=CLEANUP_GRACE_SECONDS)
            if responses is not None:
                try:
                    close = getattr(responses, "close", None)
                    if callable(close):
                        close()
                except BaseException:
                    pass

    # -- internals -----------------------------------------------------
    def _response_watchdog(self, context: _ConnectionContext,
                           deadline: float) -> None:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            if context.done.wait(min(remaining, _POLL_INTERVAL)):
                return
        if context.done.is_set():
            return
        _LOGGER.warning("bridge response deadline exceeded transport=%s",
                        context.transport_id)
        context.expired.set()
        self._send_error_ctx(context, "DEADLINE_EXCEEDED", allow_expired=True)
        try:
            context.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self._close_socket(context.sock)

    def _send_response(self, context: _ConnectionContext, kind: str,
                       payload: dict, *, terminal: bool = False,
                       enforce_total: bool = True,
                       allow_expired: bool = False) -> None:
        if context.transport_id is None:
            raise BridgeError("REQUEST_INVALID")
        frame = encode_envelope(Envelope(
            v=1, kind=kind, transport_id=context.transport_id,
            seq=context.seq, payload=payload, hash=None)) + b"\n"
        if len(frame) > MAX_RESPONSE_BYTES:
            raise BridgeError("RESPONSE_FRAME_TOO_LARGE")
        with context.lock:
            if context.done.is_set() or (context.expired.is_set() and not allow_expired):
                raise BridgeError("DEADLINE_EXCEEDED")
            if enforce_total and context.total_bytes + len(frame) > MAX_TOTAL_REQUEST_BYTES:
                raise BridgeError("TOTAL_BYTES_EXCEEDED")
            context.sock.sendall(frame)
            context.total_bytes += len(frame)
            context.seq += 1
            if terminal:
                context.done.set()

    def _send_error_ctx(self, context: _ConnectionContext, code: str, *,
                        allow_expired: bool = False) -> None:
        try:
            with context.lock:
                if context.transport_id is None:
                    context.transport_id = _ZERO_TRANSPORT
            payload = validate_error_payload(code)
            self._send_response(context, "error", payload, terminal=True,
                                enforce_total=False, allow_expired=allow_expired)
        except (BridgeError, OSError, ValueError) as exc:
            self._record_connection_failure(type(exc).__name__)

    def _fail_client_protocol(self, context: _ConnectionContext, code: str) -> None:
        _LOGGER.warning("bridge client protocol violation transport=%s code=%s",
                        context.transport_id, code)
        context.expired.set()
        self._send_error_ctx(context, code, allow_expired=True)
        try:
            context.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass

    def _cancel_reader(self, context: _ConnectionContext, reader: FrameReader,
                       cancel_event: threading.Event,
                       reason_sink: list[str]) -> None:
        last_seq = 0
        try:
            while not cancel_event.is_set():
                try:
                    line = reader.readline(stop_event=cancel_event)
                except BridgeError as exc:
                    self._fail_client_protocol(context, exc.code)
                    return
                except OSError:
                    return
                if line is None:
                    return
                try:
                    env = parse_envelope(line)
                except BridgeError as exc:
                    self._fail_client_protocol(context, exc.code)
                    return
                if env.kind != "cancel":
                    self._fail_client_protocol(context, "UNKNOWN_KIND")
                    return
                if env.seq <= last_seq:
                    self._fail_client_protocol(context, "SEQ_OUT_OF_ORDER")
                    return
                last_seq = env.seq
                reason = str(env.payload["reason"])
                reason_sink.append(reason)
                handler = getattr(self.controller, "cancel", None)
                if callable(handler):
                    try:
                        handler(transport_id=context.transport_id, reason=reason)
                    except BaseException as exc:
                        # Never a silent no-op: fail-closed and keep a sanitized
                        # diagnostic. Cancellation is best-effort by contract.
                        _LOGGER.warning(
                            "controller.cancel failed transport=%s type=%s",
                            context.transport_id, type(exc).__name__)
                        with self._lock:
                            if len(self.cancel_failures) < 64:
                                self.cancel_failures.append(type(exc).__name__)
        finally:
            cancel_event.set()

    @staticmethod
    def _close_socket(sock: socket.socket) -> None:
        try:
            sock.close()
        except OSError:
            pass
