"""AF_UNIX line-framed Envelope server for G3-B/G3-C and the D1-A boundary.

The DSH candidate adapter connects to one fixed path. This module enforces
bounded framing (byte limits before JSON), first-frame ack semantics, response
frame/total limits, chunk/finish ordering, duplicate-finish rejection, a real
monotonic deadline (including a watchdog for synchronous Controller work),
an active-connection cap and fail-closed cleanup. It only forwards validated
Envelope objects produced by a Controller; it never forwards raw subprocess
JSON and never spawns a provider.

D1-A adds an additive OS boundary around the same transport:
* configurable socket mode (only ``0o600``/``0o660``) and optional group;
* stale-socket cleanup restricted to the configured path, with ``lstat``
  type/owner/symlink checks that fail closed on anything unexpected;
* ``SO_PEERCRED`` verification of every accepted connection before the first
  frame is read or any ack is emitted (PID is evidence only, never identity);
* ``on_ready`` fired only after ``listen()`` and permission verification.
Legacy callers keep the 0600/root/no-peer-check behaviour.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
import socket
import stat
import struct
import threading
import time
from typing import Callable

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
# D1-A: local, sanitized rejection codes. They are diagnostics only and are
# deliberately NOT added to the frozen protocol ERROR_CODES set; a rejected
# peer receives no frame at all (no ack, no protocol error).
PEER_UID_DENIED = "PEER_UID_DENIED"
PEERCRED_UNAVAILABLE = "PEERCRED_UNAVAILABLE"
_ALLOWED_SOCKET_MODES = frozenset({0o600, 0o660})
_IDENTIFIER_MAX = 0xFFFFFFFE  # uid_t/gid_t reserve 0xFFFFFFFF as the -1 sentinel
_PEERCRED_FORMAT = "3i"
_PEERCRED_SIZE = struct.calcsize(_PEERCRED_FORMAT)
_PEER_DIAGNOSTIC_LIMIT = 64
_READ_CHUNK = 65_536
_ACCEPT_TIMEOUT = 0.25
_POLL_INTERVAL = 0.25
_ZERO_TRANSPORT = "tr-" + "0" * 32
_LOGGER = logging.getLogger(__name__)


def _validate_identifier(value: int | None, name: str) -> int | None:
    """Accept only a plain int in the uid_t/gid_t range (never ``bool``)."""
    if value is None:
        return None
    if type(value) is not int or not 0 <= value <= _IDENTIFIER_MAX:
        raise ValueError(f"{name} must be a non-bool int in [0, {_IDENTIFIER_MAX}]")
    return value


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
                 accept_timeout_s: float = _ACCEPT_TIMEOUT,
                 socket_mode: int = 0o600,
                 socket_gid: int | None = None,
                 expected_peer_uid: int | None = None,
                 on_ready: Callable[[], None] | None = None) -> None:
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
        # D1-A boundary options. Defaults preserve the legacy 0600/root policy.
        if type(socket_mode) is not int:
            raise ValueError("socket_mode must be an int (never bool)")
        if socket_mode not in _ALLOWED_SOCKET_MODES:
            raise ValueError("socket_mode must be 0o600 or 0o660")
        socket_gid = _validate_identifier(socket_gid, "socket_gid")
        expected_peer_uid = _validate_identifier(expected_peer_uid, "expected_peer_uid")
        if socket_gid is not None and not socket_mode & 0o060:
            raise ValueError("socket_gid conflicts with a socket_mode without group access")
        if on_ready is not None and not callable(on_ready):
            raise ValueError("on_ready must be callable")
        if expected_peer_uid is not None and getattr(socket, "SO_PEERCRED", None) is None:
            # A peer check that cannot ever be evaluated must not start.
            raise ValueError("expected_peer_uid requires SO_PEERCRED support")
        self.controller = controller
        self.socket_path = socket_path
        self.first_frame_deadline_s = float(first_frame_deadline_s)
        self.request_deadline_s = float(request_deadline_s)
        self.max_connections = max_connections
        self.accept_timeout_s = float(accept_timeout_s)
        self.socket_mode = socket_mode
        self.socket_gid = socket_gid
        self.expected_peer_uid = expected_peer_uid
        self.on_ready = on_ready
        self._ready_fired = False
        self._stop = threading.Event()
        self._server: socket.socket | None = None
        self._lock = threading.Lock()
        self._active: set[_ConnectionContext] = set()
        self._threads: set[threading.Thread] = set()
        # Observable, sanitized diagnostics (no prompt/usage/key material).
        self.cancel_failures: list[str] = []
        self.connection_failures: list[str] = []
        # D1-A evidence: rejection codes and actual kernel-reported credentials.
        self.peer_rejections: list[str] = []
        self.peer_credentials: list[tuple[int, int, int]] = []

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
        self._prepare_socket_directory(parent)
        self._remove_stale_socket()
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server = server
        try:
            server.bind(self.socket_path)
            self._apply_socket_boundary()
            server.listen(max(2, self.max_connections))
            server.settimeout(self.accept_timeout_s)
            self._notify_ready()
            while not self._stop.is_set():
                try:
                    conn, _ = server.accept()
                except socket.timeout:
                    continue
                except OSError:
                    if self._stop.is_set():
                        break
                    raise
                # D1-A: authorize the kernel-reported peer before any frame is
                # read, before the connection cap decision and before any ack.
                if not self._authorize_peer(conn):
                    self._close_socket(conn)
                    continue
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
                self._unlink_owned_socket()

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

    # -- D1-A OS boundary ----------------------------------------------
    @staticmethod
    def _prepare_socket_directory(parent: Path) -> None:
        """Create the configured parent and require a real (non-symlink) dir.

        The socket's parent is owned by the Launcher in D1. This method never
        changes an existing directory's mode/owner: the Host Launcher is the
        only principal allowed to create the ``root:2000`` setgid IPC dir.
        """
        try:
            parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            info = os.lstat(parent)
        except OSError as exc:
            raise RuntimeError("bridge socket directory is unavailable") from exc
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise RuntimeError("bridge socket parent must be a real directory")

    def _remove_stale_socket(self) -> None:
        """Remove only a verified stale AF_UNIX socket at the configured path.

        Strictly scoped to ``self.socket_path``: no globbing, no recursion and
        no traversal. A symlink, regular file, directory, foreign-owned socket
        or cross-run file is rejected instead of being deleted. If the verified
        stale socket cannot be unlinked, startup aborts rather than guessing.
        """
        try:
            info = os.lstat(self.socket_path)
        except FileNotFoundError:
            return
        except OSError as exc:
            raise RuntimeError("bridge socket path cannot be inspected") from exc
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISSOCK(info.st_mode):
            raise RuntimeError("bridge socket path exists but is not a socket")
        if info.st_uid != os.geteuid():
            raise RuntimeError("bridge socket path owner mismatch")
        try:
            os.unlink(self.socket_path)
        except OSError as exc:
            raise RuntimeError("stale bridge socket could not be removed") from exc

    def _apply_socket_boundary(self) -> None:
        """Apply and verify mode/gid *before* listen; any failure aborts."""
        try:
            os.chmod(self.socket_path, self.socket_mode)
        except OSError as exc:
            raise RuntimeError("bridge socket chmod failed") from exc
        # No CAP_CHOWN deployment: socket_gid stays None and the Host Launcher
        # supplies a setgid ``root:2000`` directory; the socket inherits the
        # group. Never silently widen the mode when chown is impossible.
        if self.socket_gid is not None:
            try:
                os.chown(self.socket_path, -1, self.socket_gid)
            except OSError as exc:
                raise RuntimeError("bridge socket chown failed") from exc
        self._verify_socket_boundary()

    def _expected_socket_gid(self, parent_mode: int, parent_gid: int) -> int:
        if self.socket_gid is not None:
            return self.socket_gid
        # Without an explicit chown the kernel either inherits the setgid
        # directory's group or uses the process effective gid.
        if parent_mode & stat.S_ISGID:
            return parent_gid
        return os.getegid()

    def _verify_socket_boundary(self) -> None:
        try:
            info = os.lstat(self.socket_path)
            parent_info = os.lstat(Path(self.socket_path).parent)
        except OSError as exc:
            raise RuntimeError("bridge socket permission check failed") from exc
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISSOCK(info.st_mode):
            raise RuntimeError("bridge socket file type mismatch")
        if info.st_uid != os.geteuid():
            raise RuntimeError("bridge socket uid mismatch")
        expected_gid = self._expected_socket_gid(parent_info.st_mode, parent_info.st_gid)
        if info.st_gid != expected_gid:
            raise RuntimeError("bridge socket gid mismatch")
        if stat.S_IMODE(info.st_mode) != self.socket_mode:
            raise RuntimeError("bridge socket mode mismatch")

    def _notify_ready(self) -> None:
        """Fire ``on_ready`` at most once, after listen + permission checks."""
        if self.on_ready is None or self._ready_fired:
            return
        self._ready_fired = True
        info = os.lstat(self.socket_path)
        _LOGGER.info(
            "bridge socket ready mode=%04o gid=%d uid=%d peer_uid=%s",
            stat.S_IMODE(info.st_mode), info.st_gid, info.st_uid,
            self.expected_peer_uid)
        callback = self.on_ready
        callback()

    def _unlink_owned_socket(self) -> None:
        """Remove only a socket this principal owns; never follow a symlink."""
        try:
            info = os.lstat(self.socket_path)
        except OSError:
            return
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.geteuid():
            return
        try:
            os.unlink(self.socket_path)
        except OSError:
            _LOGGER.warning("bridge socket cleanup failed")

    def _authorize_peer(self, conn: socket.socket) -> bool:
        """Verify the accepted peer via SO_PEERCRED before any read/ack.

        PID is recorded as evidence only: across PID namespaces the kernel may
        report ``pid=0``, so identity is decided solely by the peer UID. Any
        missing option, short read or exception fails closed; there is no
        path-only trust fallback.
        """
        option = getattr(socket, "SO_PEERCRED", None)
        if option is None:
            self._record_peer_rejection(PEERCRED_UNAVAILABLE)
            _LOGGER.warning("bridge peercred unavailable: SO_PEERCRED missing")
            return False
        try:
            raw = conn.getsockopt(socket.SOL_SOCKET, option, _PEERCRED_SIZE)
        except Exception as exc:  # noqa: BLE001 - any credential error fails closed
            self._record_peer_rejection(PEERCRED_UNAVAILABLE)
            _LOGGER.warning("bridge peercred unavailable type=%s", type(exc).__name__)
            return False
        if not isinstance(raw, (bytes, bytearray)) or len(raw) != _PEERCRED_SIZE:
            self._record_peer_rejection(PEERCRED_UNAVAILABLE)
            _LOGGER.warning("bridge peercred invalid length")
            return False
        pid, uid, gid = struct.unpack(_PEERCRED_FORMAT, raw)
        uid &= 0xFFFFFFFF
        gid &= 0xFFFFFFFF
        with self._lock:
            if len(self.peer_credentials) < _PEER_DIAGNOSTIC_LIMIT:
                self.peer_credentials.append((uid, gid, pid))
        if self.expected_peer_uid is not None and uid != self.expected_peer_uid:
            self._record_peer_rejection(PEER_UID_DENIED)
            _LOGGER.warning(
                "bridge peer rejected code=%s uid=%d gid=%d expected_uid=%d",
                PEER_UID_DENIED, uid, gid, self.expected_peer_uid)
            return False
        _LOGGER.debug("bridge peer accepted uid=%d gid=%d pid=%d", uid, gid, pid)
        return True

    def _record_peer_rejection(self, code: str) -> None:
        with self._lock:
            if len(self.peer_rejections) < _PEER_DIAGNOSTIC_LIMIT:
                self.peer_rejections.append(code)

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
