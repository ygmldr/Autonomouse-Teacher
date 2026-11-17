"""Minimal trusted stdio Broker client for G3-B/G3-C (no network, no retry).

Every request uses a real bounded read/write: ``select`` on the subprocess pipe
with the remaining monotonic deadline (capped by ``timeout_s``). A timeout is
terminal for this channel: the controller is told ``BROKER_TIMEOUT`` and the
client never re-sends the in-flight Reserve/Claim/Settle/Fail message.
"""
from __future__ import annotations

import json
import os
import select
import subprocess
import threading
import time
import uuid
from typing import Mapping

MAX_BROKER_REPLY_BYTES = 65_536
_READ_CHUNK = 65_536
_WRITE_CHUNK = 65_536


class BrokerClientError(RuntimeError):
    """Channel/protocol failure; ``code`` is safe to surface through IPC."""

    code = "BROKER_ERROR"

    def __init__(self, message: str) -> None:
        super().__init__(message)


class BrokerTimeoutError(BrokerClientError):
    """The Broker stayed alive but did not answer before the deadline."""

    code = "BROKER_TIMEOUT"


class BrokerClient:
    def __init__(self, *, config_path: str, python: str,
                 timeout_s: float = 15.0):
        self.config_path = str(config_path)
        self.python = python
        self.timeout_s = float(timeout_s)
        if not 0 < self.timeout_s < 1_000:
            raise ValueError("timeout_s must be positive and bounded")
        self.proc: subprocess.Popen | None = None
        self._seq = 0
        # Durable broker journal outlives one controller process. Sequence-only
        # ids (b2-reserve-1) collide with an earlier process's journal row and
        # produce IDEMPOTENCY_CONFLICT on resume/restart; instance-scoped ids
        # keep idempotency semantics without weakening broker checks.
        self._instance = uuid.uuid4().hex[:16]
        self._lock = threading.RLock()
        self._read_buffer = bytearray()
        self._broken = False

    def start(self) -> None:
        with self._lock:
            if self.proc is not None:
                return
            self._read_buffer.clear()
            self._broken = False
            self.proc = subprocess.Popen(
                [self.python, "-B", "-m", "autoteacher_m0.accounting.broker",
                 "--config", self.config_path],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                bufsize=0, close_fds=True)

    # -- public API -----------------------------------------------------
    def request(self, op: str, fields: dict, *,
                deadline_monotonic: float | None = None) -> dict:
        """Send one bounded request and read exactly one bounded reply line.

        The call is serialized. After any timeout/protocol corruption the
        channel is marked untrusted and every later call fails closed; there is
        no implicit re-send.
        """
        if not isinstance(op, str) or not op:
            raise BrokerClientError("BROKER_INVALID_OP")
        if not isinstance(fields, Mapping):
            raise BrokerClientError("BROKER_INVALID_FIELDS")
        deadline = self._coerce_deadline(deadline_monotonic)
        with self._lock:
            return self._request_locked(op, dict(fields), deadline)

    def reserve(self, *, task_id: str, route_id: str, model: str,
                input_tokens: int, output_tokens: int, call_id: str,
                deadline_monotonic: float | None = None) -> dict:
        return self.request(
            "reserve",
            {"task_id": task_id, "route_id": route_id, "model": model,
             "purpose": "conversation", "input_tokens": input_tokens,
             "output_tokens": output_tokens, "retry": False,
             "call_id": call_id},
            deadline_monotonic=deadline_monotonic)

    def claim(self, *, call_id: str, reservation_id: str, request_digest: str,
              expected_route_id: str, expected_model: str,
              deadline_monotonic: float | None = None) -> dict:
        return self.request(
            "claim",
            {"call_id": call_id, "reservation_id": reservation_id,
             "request_digest": request_digest,
             "expected_route_id": expected_route_id,
             "expected_model": expected_model},
            deadline_monotonic=deadline_monotonic)

    def settle(self, *, reservation_id: str, usage: dict | None,
               deadline_monotonic: float | None = None) -> dict:
        return self.request("settle", {"reservation_id": reservation_id,
                                       "usage": usage},
                            deadline_monotonic=deadline_monotonic)

    def fail(self, *, reservation_id: str, usage: dict | None,
             deadline_monotonic: float | None = None) -> dict:
        return self.request("fail", {"reservation_id": reservation_id,
                                     "usage": usage},
                            deadline_monotonic=deadline_monotonic)

    def snapshot(self, *, deadline_monotonic: float | None = None) -> dict:
        return self.request("snapshot", {}, deadline_monotonic=deadline_monotonic)

    def reservation_status(self, reservation_id: str, *,
                           deadline_monotonic: float | None = None) -> dict:
        """Read-only reservation status op (implemented by the trusted broker)."""
        return self.request("reservation_status",
                            {"reservation_id": reservation_id},
                            deadline_monotonic=deadline_monotonic)

    def _request(self, op: str, **fields) -> dict:
        """Compatibility shim for pre-G3-C call sites; delegates to request()."""
        return self.request(op, fields)

    def close(self) -> None:
        with self._lock:
            self._read_buffer.clear()
            if self.proc is None:
                return
            proc = self.proc
            self.proc = None
            self._broken = True
            try:
                if proc.stdin:
                    proc.stdin.close()
                proc.wait(timeout=5)
            except BaseException:
                try:
                    proc.kill()
                except OSError:
                    pass
                try:
                    proc.wait(timeout=5)
                except BaseException:
                    pass
            finally:
                for stream in (proc.stdout, proc.stderr):
                    if stream:
                        try:
                            stream.close()
                        except OSError:
                            pass

    # -- internals ------------------------------------------------------
    @staticmethod
    def _coerce_deadline(deadline_monotonic: float | None) -> float | None:
        if deadline_monotonic is None:
            return None
        if not isinstance(deadline_monotonic, (int, float)):
            raise BrokerClientError("BROKER_INVALID_DEADLINE")
        value = float(deadline_monotonic)
        if value != value or value in (float("inf"), float("-inf")):
            raise BrokerClientError("BROKER_INVALID_DEADLINE")
        return value

    def _remaining(self, deadline: float | None) -> float:
        """Remaining budget for one blocking edge, capped by ``timeout_s``."""
        if deadline is None:
            return self.timeout_s
        return min(self.timeout_s, deadline - time.monotonic())

    def _mark_untrusted(self, reason: str) -> None:
        """Stop trusting (and using) this channel; never auto-resend."""
        self._broken = True
        self._read_buffer.clear()
        proc = self.proc
        if proc is None:
            return
        try:
            if proc.stdin:
                proc.stdin.close()
        except OSError:
            pass
        if proc.poll() is None:
            try:
                proc.terminate()
            except OSError:
                pass
            try:
                proc.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                try:
                    proc.kill()
                except OSError:
                    pass
                try:
                    proc.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    pass

    def _ensure_usable(self) -> subprocess.Popen:
        if self._broken:
            raise BrokerClientError("BROKER_CHANNEL_UNTRUSTED")
        proc = self.proc
        if proc is None:
            raise BrokerClientError("BROKER_UNAVAILABLE")
        if proc.poll() is not None:
            self._mark_untrusted("BROKER_EXITED")
            raise BrokerClientError("BROKER_EXITED")
        return proc

    def _request_locked(self, op: str, fields: dict, deadline: float | None) -> dict:
        proc = self._ensure_usable()
        if deadline is not None and deadline - time.monotonic() <= 0:
            self._mark_untrusted("BROKER_TIMEOUT")
            raise BrokerTimeoutError("BROKER_TIMEOUT")
        self._seq += 1
        message = {"v": 1, "id": f"b2-{op}-{self._instance}-{self._seq}",
                   "op": op, **fields}
        try:
            raw = (json.dumps(message, separators=(",", ":")) + "\n").encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise BrokerClientError("BROKER_IO_ERROR") from exc
        self._write_all(proc, raw, deadline)
        line = self._read_line(proc, deadline)
        try:
            reply = json.loads(line.decode("utf-8", errors="strict"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self._mark_untrusted("BROKER_BAD_REPLY")
            raise BrokerClientError("BROKER_BAD_REPLY") from exc
        if not isinstance(reply, dict) or reply.get("v") != 1:
            self._mark_untrusted("BROKER_BAD_REPLY")
            raise BrokerClientError("BROKER_BAD_REPLY")
        # Raw Broker codes are preserved here: the trusted Controller owns the
        # finite Broker->IPC mapping table (single authority, no UNKNOWN_FIELD).
        return reply

    def _write_all(self, proc: subprocess.Popen, data: bytes,
                   deadline: float | None) -> None:
        if proc.stdin is None:
            self._mark_untrusted("BROKER_IO_ERROR")
            raise BrokerClientError("BROKER_IO_ERROR")
        try:
            fd = proc.stdin.fileno()
        except (OSError, ValueError) as exc:
            self._mark_untrusted("BROKER_IO_ERROR")
            raise BrokerClientError("BROKER_IO_ERROR") from exc
        view = memoryview(data)
        while view:
            remaining = self._remaining(deadline)
            if remaining <= 0:
                self._mark_untrusted("BROKER_TIMEOUT")
                raise BrokerTimeoutError("BROKER_TIMEOUT")
            try:
                _, writable, _ = select.select([], [fd], [], remaining)
            except (OSError, ValueError) as exc:
                self._mark_untrusted("BROKER_IO_ERROR")
                raise BrokerClientError("BROKER_IO_ERROR") from exc
            if not writable:
                self._mark_untrusted("BROKER_TIMEOUT")
                raise BrokerTimeoutError("BROKER_TIMEOUT")
            try:
                written = os.write(fd, view[:_WRITE_CHUNK])
            except (BrokenPipeError, OSError) as exc:
                self._mark_untrusted("BROKER_IO_ERROR")
                raise BrokerClientError("BROKER_IO_ERROR") from exc
            if written <= 0:
                self._mark_untrusted("BROKER_IO_ERROR")
                raise BrokerClientError("BROKER_IO_ERROR")
            view = view[written:]

    def _read_line(self, proc: subprocess.Popen, deadline: float | None) -> bytes:
        if proc.stdout is None:
            self._mark_untrusted("BROKER_IO_ERROR")
            raise BrokerClientError("BROKER_IO_ERROR")
        try:
            fd = proc.stdout.fileno()
        except (OSError, ValueError) as exc:
            self._mark_untrusted("BROKER_IO_ERROR")
            raise BrokerClientError("BROKER_IO_ERROR") from exc
        while True:
            index = self._read_buffer.find(b"\n")
            if index >= 0:
                line = bytes(self._read_buffer[:index])
                del self._read_buffer[:index + 1]
                return line
            if len(self._read_buffer) > MAX_BROKER_REPLY_BYTES:
                self._mark_untrusted("BROKER_BAD_REPLY")
                raise BrokerClientError("BROKER_BAD_REPLY")
            remaining = self._remaining(deadline)
            if remaining <= 0:
                self._mark_untrusted("BROKER_TIMEOUT")
                raise BrokerTimeoutError("BROKER_TIMEOUT")
            try:
                ready, _, _ = select.select([fd], [], [], remaining)
            except (OSError, ValueError) as exc:
                self._mark_untrusted("BROKER_IO_ERROR")
                raise BrokerClientError("BROKER_IO_ERROR") from exc
            if not ready:
                self._mark_untrusted("BROKER_TIMEOUT")
                raise BrokerTimeoutError("BROKER_TIMEOUT")
            try:
                chunk = os.read(fd, _READ_CHUNK)
            except OSError as exc:
                self._mark_untrusted("BROKER_IO_ERROR")
                raise BrokerClientError("BROKER_IO_ERROR") from exc
            if not chunk:
                returncode = proc.poll()
                self._mark_untrusted("BROKER_EOF")
                if returncode is None:
                    raise BrokerClientError("BROKER_EOF")
                raise BrokerClientError("BROKER_EXITED")
            self._read_buffer.extend(chunk)
