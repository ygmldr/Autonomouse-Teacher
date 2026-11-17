"""B2-owned trusted Fake subprocess backend (no shell/network).

G3-C replaces the buffered ``subprocess.run`` path with an incremental,
bounded and cancellable reader. The Fake still writes its atomic receipt
BEFORE any frame; ``last_receipt`` becomes available as soon as a valid receipt
is observed, which may be before the process exits.

Resource bounds (enforced per invocation): one frame <= 64 KiB, total stdout
<= 1 MiB, at most 256 frames, one child process, no background reader thread
(``select`` is used with a bounded poll slice so cancellation is observable).
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from typing import Iterator, Mapping

MAX_FAKE_PAYLOAD_BYTES = 256 * 1024
MAX_FAKE_FRAME_BYTES = 64 * 1024
MAX_FAKE_TOTAL_BYTES = 1024 * 1024
MAX_FAKE_FRAMES = 256
_READ_CHUNK = 65_536
_POLL_SLICE = 0.05
_FRAME_KINDS = frozenset({"chunk", "usage", "finish", "error", "receipt"})
_HEX64 = frozenset("0123456789abcdef")


@dataclass(frozen=True)
class FakeReceipt:
    receipt_id: str
    raw_sha256: str
    raw_length: int
    mode: str
    usage: Mapping[str, object] | None
    nonce: str
    path: Path
    frames: tuple[dict, ...]


class FakeError(ValueError):
    """Sanitized Fake failure; ``code`` is a frozen IPC error code."""

    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        self.receipt: FakeReceipt | None = None
        super().__init__(message or code)


class FakeTimeout(FakeError):
    """No usable answer before the deadline; carries the receipt if written."""

    def __init__(self, receipt: FakeReceipt | None = None) -> None:
        super().__init__("FAKE_IO_ERROR", "FAKE_TIMEOUT")
        self.receipt = receipt


class FakeCancelled(FakeError):
    """Cancellation after the send boundary is conservatively uncertain."""

    def __init__(self, receipt: FakeReceipt | None = None) -> None:
        super().__init__("SETTLEMENT_UNCERTAIN", "FAKE_CANCELLED")
        self.receipt = receipt


class FakeBackend:
    def __init__(self, *, script: str, receipt_dir: str, python: str | None = None,
                 timeout_s: float = 10.0, mode: str = "ok_usage"):
        self.script = str(script)
        self.receipt_dir = Path(receipt_dir)
        self.python = python or sys.executable
        self.timeout_s = float(timeout_s)
        if not 0 < self.timeout_s < 1_000:
            raise ValueError("timeout_s must be positive and bounded")
        self.mode = mode
        self.frames: list[dict] = []
        self.sent_payload_digest: str | None = None
        self.last_receipt: FakeReceipt | None = None
        self._lock = threading.RLock()
        self._busy = False
        self._active_close: threading.Event | None = None
        self._active_proc: subprocess.Popen | None = None

    # -- receipts / counters -------------------------------------------
    def received_count(self) -> int:
        with self._lock:
            return self._received_count_locked()

    def _received_count_locked(self) -> int:
        path = self.receipt_dir / "received-count.json"
        try:
            return int(json.loads(path.read_text())["count"])
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            return 0

    def _receipt_path(self, nonce: str) -> Path:
        return self.receipt_dir / f"rcpt-{nonce}.json"

    @staticmethod
    def _payload_nonce(payload_bytes: bytes) -> str:
        try:
            document = json.loads(payload_bytes.decode("utf-8", errors="strict"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise FakeError("FAKE_IO_ERROR", "FAKE_PAYLOAD_INVALID") from exc
        if not isinstance(document, dict):
            raise FakeError("FAKE_IO_ERROR", "FAKE_PAYLOAD_INVALID")
        nonce = document.get("nonce")
        if (not isinstance(nonce, str) or len(nonce) != 32
                or any(char not in _HEX64 for char in nonce)):
            raise FakeError("FAKE_RECEIPT_MISMATCH", "FAKE_NONCE_INVALID")
        return nonce

    def _load_receipt(self, nonce: str, payload_bytes: bytes,
                      frames: list[dict]) -> FakeReceipt | None:
        path = self._receipt_path(nonce)
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return None
        if not isinstance(document, dict):
            raise FakeError("FAKE_RECEIPT_MISMATCH")
        receipt_id = document.get("receipt_id")
        raw_sha256 = document.get("raw_sha256")
        raw_length = document.get("raw_length")
        mode = document.get("mode")
        recorded_nonce = document.get("nonce")
        usage = document.get("usage")
        if (not isinstance(receipt_id, str) or not receipt_id
                or not isinstance(raw_sha256, str) or len(raw_sha256) != 64
                or any(char not in _HEX64 for char in raw_sha256)
                or type(raw_length) is not int or raw_length < 0
                or not isinstance(mode, str) or not mode
                or recorded_nonce != nonce
                or (usage is not None and not isinstance(usage, Mapping))):
            raise FakeError("FAKE_RECEIPT_MISMATCH")
        expected = hashlib.sha256(payload_bytes).hexdigest()
        if raw_sha256 != expected or raw_length != len(payload_bytes):
            raise FakeError("FAKE_RECEIPT_MISMATCH")
        return FakeReceipt(receipt_id, raw_sha256, raw_length, mode,
                           usage, recorded_nonce, path, tuple(frames))

    # -- public API -----------------------------------------------------
    def stream(self, payload_bytes: bytes, *,
               deadline_monotonic: float | None = None,
               cancel_event: threading.Event | None = None) -> Iterator[dict]:
        """Yield Fake frames incrementally; receipt-first remains guaranteed."""
        self._begin()
        try:
            yield from self._stream_impl(payload_bytes, deadline_monotonic,
                                         cancel_event, self._active_close)
        finally:
            self._end()

    def send_exact_bytes(self, payload_bytes: bytes, nonce: str) -> FakeReceipt:
        """Backward-compatible bounded API: consume ``stream`` and return receipt."""
        if not isinstance(payload_bytes, (bytes, bytearray)):
            raise FakeError("FRAME_TOO_LARGE")
        payload_bytes = bytes(payload_bytes)
        if len(payload_bytes) > MAX_FAKE_PAYLOAD_BYTES:
            raise FakeError("FRAME_TOO_LARGE")
        if (not isinstance(nonce, str) or len(nonce) != 32
                or any(char not in _HEX64 for char in nonce)):
            raise FakeError("FAKE_RECEIPT_MISMATCH", "FAKE_NONCE_INVALID")
        self._begin()
        try:
            for _frame in self._stream_impl(
                    payload_bytes, time.monotonic() + self.timeout_s,
                    None, self._active_close):
                pass
            receipt = self.last_receipt
            if receipt is None:
                raise FakeError("FAKE_RECEIPT_MISMATCH")
            if receipt.nonce != nonce:
                raise FakeError("FAKE_RECEIPT_MISMATCH")
            if receipt.raw_length != len(payload_bytes):
                raise FakeError("FAKE_RECEIPT_MISMATCH")
            self.sent_payload_digest = receipt.raw_sha256
            return receipt
        finally:
            self._end()

    def close(self) -> None:
        """Cancel any active stream, reap the child and close every pipe."""
        with self._lock:
            close_event = self._active_close
            proc = self._active_proc
            self.frames = []
        if close_event is not None:
            close_event.set()
        if proc is not None:
            self._terminate(proc)

    # -- busy/active registration ---------------------------------------
    def _begin(self) -> None:
        with self._lock:
            if self._busy:
                raise FakeError("FAKE_IO_ERROR", "FAKE_BUSY")
            self._busy = True
            self._active_close = threading.Event()
            self._active_proc = None
            self.frames = []
            self.sent_payload_digest = None
            self.last_receipt = None

    def _end(self) -> None:
        with self._lock:
            self._busy = False
            self._active_close = None
            self._active_proc = None

    def _register_proc(self, proc: subprocess.Popen) -> None:
        with self._lock:
            self._active_proc = proc

    # -- incremental stream ---------------------------------------------
    def _stream_impl(self, payload_bytes: object,
                     deadline_monotonic: float | None,
                     cancel_event: threading.Event | None,
                     close_event: threading.Event | None) -> Iterator[dict]:
        if not isinstance(payload_bytes, (bytes, bytearray)):
            raise FakeError("FRAME_TOO_LARGE")
        payload = bytes(payload_bytes)
        if len(payload) > MAX_FAKE_PAYLOAD_BYTES:
            raise FakeError("FRAME_TOO_LARGE")
        if deadline_monotonic is not None and not isinstance(
                deadline_monotonic, (int, float)):
            raise FakeError("FAKE_IO_ERROR", "FAKE_DEADLINE_INVALID")
        nonce = self._payload_nonce(payload)
        now = time.monotonic()
        deadline = (float(deadline_monotonic) if deadline_monotonic is not None
                    else now + self.timeout_s)
        if deadline <= now:
            raise FakeTimeout(None)
        self.receipt_dir.mkdir(parents=True, exist_ok=True)
        env = {"PATH": "/usr/bin:/bin", "G3B_RECEIPT_DIR": str(self.receipt_dir)}
        proc = subprocess.Popen(
            [self.python, "-B", self.script], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
            bufsize=0, close_fds=True)
        self._register_proc(proc)
        writer_errors: list[BaseException] = []
        writer = threading.Thread(
            target=self._write_payload, args=(proc, payload, writer_errors),
            name="g3c-fake-stdin", daemon=True)
        writer.start()
        buffer = bytearray()
        frames: list[dict] = []
        total_bytes = 0
        stdout = proc.stdout
        try:
            if stdout is None:
                raise FakeError("FAKE_IO_ERROR")
            fd = stdout.fileno()
            while True:
                if close_event is not None and close_event.is_set():
                    raise FakeCancelled(self._safe_receipt(nonce, payload, frames))
                if cancel_event is not None and cancel_event.is_set():
                    raise FakeCancelled(self._safe_receipt(nonce, payload, frames))
                while True:
                    index = buffer.find(b"\n")
                    if index < 0:
                        break
                    line = bytes(buffer[:index])
                    del buffer[: index + 1]
                    frame = self._parse_frame(line, frames, total_bytes)
                    total_bytes += len(line) + 1
                    frames.append(frame)
                    with self._lock:
                        self.frames = frames
                    receipt = self._safe_receipt(nonce, payload, frames)
                    if receipt is not None:
                        self.last_receipt = receipt
                    yield frame
                    if close_event is not None and close_event.is_set():
                        raise FakeCancelled(self._safe_receipt(nonce, payload, frames))
                    if cancel_event is not None and cancel_event.is_set():
                        raise FakeCancelled(self._safe_receipt(nonce, payload, frames))
                if len(buffer) > MAX_FAKE_FRAME_BYTES:
                    raise FakeError("FAKE_FRAME_TOO_LARGE", "FAKE_FRAME_TOO_LARGE")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise FakeTimeout(self._safe_receipt(nonce, payload, frames))
                slice_seconds = min(_POLL_SLICE, remaining)
                try:
                    readable, _, _ = select.select([fd], [], [], slice_seconds)
                except (OSError, ValueError) as exc:
                    raise FakeError("FAKE_IO_ERROR", "FAKE_SELECT_FAILED") from exc
                if not readable:
                    continue
                try:
                    chunk = os.read(fd, _READ_CHUNK)
                except OSError as exc:
                    raise FakeError("FAKE_IO_ERROR", "FAKE_READ_FAILED") from exc
                if not chunk:
                    break
                buffer.extend(chunk)
            if buffer:
                raise FakeError("FAKE_BAD_FRAME", "FAKE_TRUNCATED_FRAME")
            remaining = max(deadline - time.monotonic(), 0.001)
            try:
                returncode = proc.wait(timeout=remaining)
            except subprocess.TimeoutExpired as exc:
                raise FakeTimeout(self._safe_receipt(nonce, payload, frames)) from exc
            if returncode != 0:
                raise FakeError("FAKE_IO_ERROR")
            receipt = self._load_receipt(nonce, payload, frames)
            if receipt is None:
                raise FakeError("FAKE_RECEIPT_MISMATCH")
            self.sent_payload_digest = receipt.raw_sha256
            self.last_receipt = receipt
            with self._lock:
                self.frames = frames
        except FakeError as exc:
            if getattr(exc, "receipt", None) is None:
                exc.receipt = self._safe_receipt(nonce, payload, frames)
            raise
        finally:
            self._terminate(proc)
            writer.join(timeout=1.0)
            for stream in (proc.stdout, proc.stderr):
                if stream:
                    try:
                        stream.close()
                    except OSError:
                        pass
            try:
                if proc.stdin:
                    proc.stdin.close()
            except OSError:
                pass

    def _parse_frame(self, line: bytes, frames: list[dict], total_bytes: int) -> dict:
        if len(line) > MAX_FAKE_FRAME_BYTES:
            raise FakeError("FAKE_FRAME_TOO_LARGE", "FAKE_FRAME_TOO_LARGE")
        if len(frames) >= MAX_FAKE_FRAMES:
            raise FakeError("FAKE_FRAME_LIMIT", "FAKE_FRAME_LIMIT")
        projected = total_bytes + len(line) + 1
        if projected > MAX_FAKE_TOTAL_BYTES:
            raise FakeError("FAKE_OUTPUT_TOO_LARGE", "FAKE_OUTPUT_TOO_LARGE")
        try:
            document = json.loads(line.decode("utf-8", errors="strict"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise FakeError("FAKE_BAD_FRAME", "FAKE_BAD_FRAME") from exc
        if not isinstance(document, dict) or document.get("kind") not in _FRAME_KINDS:
            raise FakeError("FAKE_BAD_FRAME", "FAKE_BAD_FRAME")
        return document

    def _safe_receipt(self, nonce: str, payload: bytes,
                      frames: list[dict]) -> FakeReceipt | None:
        try:
            return self._load_receipt(nonce, payload, frames)
        except FakeError:
            return None

    def _write_payload(self, proc: subprocess.Popen, payload: bytes,
                       errors: list[BaseException]) -> None:
        if proc.stdin is None:
            errors.append(FakeError("FAKE_IO_ERROR"))
            return
        try:
            fd = proc.stdin.fileno()
            view = memoryview(payload + b"\n")
            while view:
                written = os.write(fd, view[:_READ_CHUNK])
                if written <= 0:
                    raise OSError("short write")
                view = view[written:]
            proc.stdin.close()
        except (OSError, ValueError) as exc:
            errors.append(exc)

    def _terminate(self, proc: subprocess.Popen) -> None:
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
        try:
            proc.wait(timeout=0.1)
        except subprocess.TimeoutExpired:
            pass
