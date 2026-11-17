"""G3-C C3-04 host tests: incremental Fake streaming, bounds and cleanup.

The real Fake writes its atomic receipt before any frame. These tests prove the
first frame is observable while the Fake process is still alive (T1 < T2), that
the 256-frame / 64 KiB / 1 MiB bounds fail closed, that a stalled consumer does
not accumulate an unbounded queue, and that ``send_exact_bytes`` remains
backward compatible without ``subprocess.run``/``communicate`` buffering.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

import pytest

from autoteacher_m0.bridge.fake_backend import (
    FakeBackend, FakeCancelled, FakeError, FakeReceipt,
)

FAKE = Path(__file__).resolve().parents[3] / "spikes/g3b-trusted-bridge/fake/fake_provider.py"

_PREAMBLE = '''\
import hashlib, json, os, sys, time
from pathlib import Path
MAX = 256 * 1024
data = sys.stdin.buffer.readline(MAX + 1)
if len(data) > MAX or not data.endswith(b"\\n"):
    raise SystemExit(2)
raw = data[:-1]
try:
    document = json.loads(raw.decode("utf-8"))
except Exception:
    raise SystemExit(2)
receipt_dir = Path(os.environ["G3B_RECEIPT_DIR"])
receipt_dir.mkdir(parents=True, exist_ok=True)
nonce = document["nonce"]
receipt = {
    "schema": "m0.g3b.fake.receipt.v1",
    "receipt_id": "rcpt-" + "0" * 32,
    "raw_sha256": hashlib.sha256(raw).hexdigest(),
    "raw_length": len(raw),
    "transport_encoding": "utf-8+lf",
    "mode": document.get("mode", "ok_usage"),
    "usage": {"inputTokens": 11, "cacheReadTokens": 2,
              "cacheWriteTokens": 0, "outputTokens": 5},
    "nonce": nonce,
    "synthetic": True,
}
(receipt_dir / ("rcpt-" + nonce + ".json")).write_text(
    json.dumps(receipt, sort_keys=True), encoding="utf-8")
(receipt_dir / "received-count.json").write_text(
    json.dumps({"count": 1}), encoding="utf-8")
def emit(value):
    print(json.dumps(value, sort_keys=True), flush=True)
'''


def _payload(mode: str, nonce: str) -> bytes:
    return json.dumps({
        "schema": "m0.g3b.fake.v1", "call_id": "call-" + "0" * 48,
        "prepared_digest": "b" * 64, "route_id": "offline-test-only-g3b",
        "model": "fixture-bridge-v1", "messages": [], "tools": [],
        "system": "", "max_output_tokens": 64, "stream": True,
        "mode": mode, "nonce": nonce,
    }, sort_keys=True, separators=(",", ":")).encode()


def _fake_script(tmp_path: Path, body: str, name: str = "fake_stream.py") -> Path:
    path = tmp_path / name
    path.write_text(_PREAMBLE + body, encoding="utf-8")
    return path


def _chunk(text: str) -> dict:
    return {"kind": "chunk",
            "chunk": {"type": "text-delta", "index": 0, "text": text}}


def _finish() -> dict:
    return {"kind": "finish", "reason": {"kind": "stop"}}


def _backend(script: Path, tmp_path: Path, timeout_s: float = 10.0) -> FakeBackend:
    return FakeBackend(script=str(script), receipt_dir=str(tmp_path / "receipts"),
                       python=sys.executable, timeout_s=timeout_s)


def test_c3_04a_first_frame_before_fake_process_exit(tmp_path: Path) -> None:
    script = _fake_script(tmp_path, '''
emit({"kind": "chunk", "chunk": {"type": "text-delta", "index": 0, "text": "first"}})
(receipt_dir / "first-frame.marker").write_text("1")
time.sleep(0.8)
emit({"kind": "finish", "reason": {"kind": "stop"}})
(receipt_dir / "exit.marker").write_text("1")
''')
    nonce = "e" * 32
    payload = _payload("slow", nonce)
    fake = _backend(script, tmp_path)
    marker_dir = tmp_path / "receipts"
    try:
        iterator = iter(fake.stream(payload,
                                    deadline_monotonic=time.monotonic() + 10))
        first_at = time.monotonic()
        first = next(iterator)
        assert first["kind"] == "chunk"
        assert first["chunk"]["text"] == "first"
        assert fake.last_receipt is not None
        assert fake.last_receipt.nonce == nonce
        assert (marker_dir / "first-frame.marker").exists()
        assert not (marker_dir / "exit.marker").exists()
        rest = list(iterator)
        finished_at = time.monotonic()
        assert rest[-1]["kind"] == "finish"
        assert (marker_dir / "exit.marker").exists()
        assert first_at < finished_at
        assert finished_at - first_at >= 0.5
        assert fake.received_count() == 1
        assert fake._active_proc is None
    finally:
        fake.close()


@pytest.mark.parametrize(("count", "expected"), [
    (257, "FAKE_FRAME_LIMIT"),
])
def test_c3_04b_frame_count_limit(tmp_path: Path, count: int,
                                  expected: str) -> None:
    script = _fake_script(tmp_path, f'''
for _ in range({count}):
    emit({{"kind": "chunk", "chunk": {{"type": "text-delta", "index": 0, "text": "x"}}}})
emit({{"kind": "finish", "reason": {{"kind": "stop"}}}})
''')
    fake = _backend(script, tmp_path)
    try:
        with pytest.raises(FakeError) as exc:
            for _frame in fake.stream(_payload("ok_usage", "f" * 32),
                                      deadline_monotonic=time.monotonic() + 10):
                pass
        assert exc.value.code == expected
        assert len(fake.frames) == 256
        assert fake._active_proc is None
        assert fake.received_count() == 1
    finally:
        fake.close()


def test_c3_04c_total_output_limit(tmp_path: Path) -> None:
    script = _fake_script(tmp_path, '''
for _ in range(20):
    emit({"kind": "chunk",
          "chunk": {"type": "text-delta", "index": 0, "text": "x" * 60000}})
emit({"kind": "finish", "reason": {"kind": "stop"}})
''')
    fake = _backend(script, tmp_path)
    try:
        with pytest.raises(FakeError) as exc:
            for _frame in fake.stream(_payload("ok_usage", "a" * 32),
                                      deadline_monotonic=time.monotonic() + 10):
                pass
        assert exc.value.code == "FAKE_OUTPUT_TOO_LARGE"
        assert fake._active_proc is None
    finally:
        fake.close()


def test_c3_04c_single_frame_limit(tmp_path: Path) -> None:
    script = _fake_script(tmp_path, '''
emit({"kind": "chunk",
      "chunk": {"type": "text-delta", "index": 0, "text": "x" * 70000}})
emit({"kind": "finish", "reason": {"kind": "stop"}})
''')
    fake = _backend(script, tmp_path)
    try:
        with pytest.raises(FakeError) as exc:
            for _frame in fake.stream(_payload("ok_usage", "b" * 32),
                                      deadline_monotonic=time.monotonic() + 10):
                pass
        assert exc.value.code == "FAKE_FRAME_TOO_LARGE"
        assert fake._active_proc is None
    finally:
        fake.close()


def test_c3_04d_consumer_stall_is_bounded_and_close_cleans(tmp_path: Path) -> None:
    script = _fake_script(tmp_path, '''
for _ in range(300):
    emit({"kind": "chunk", "chunk": {"type": "text-delta", "index": 0, "text": "z"}})
emit({"kind": "finish", "reason": {"kind": "stop"}})
''')
    fake = _backend(script, tmp_path)
    try:
        iterator = iter(fake.stream(_payload("ok_usage", "c" * 32),
                                    deadline_monotonic=time.monotonic() + 10))
        first = next(iterator)
        assert first["kind"] == "chunk"
        time.sleep(0.2)
        # Only pulled frames are materialized; the child may block on the pipe.
        assert len(fake.frames) == 1
        fake.close()
        with pytest.raises(FakeCancelled):
            next(iterator)
        assert fake._active_proc is None
        assert fake.frames == []
    finally:
        fake.close()


def test_c3_04e_bad_frame_and_nonzero_exit_fail_closed(tmp_path: Path) -> None:
    bad = _fake_script(tmp_path, '''
print("this is not json", flush=True)
''', name="fake_bad.py")
    fake = _backend(bad, tmp_path)
    try:
        with pytest.raises(FakeError) as exc:
            for _frame in fake.stream(_payload("ok_usage", "d" * 32),
                                      deadline_monotonic=time.monotonic() + 10):
                pass
        assert exc.value.code == "FAKE_BAD_FRAME"
        assert fake._active_proc is None
    finally:
        fake.close()

    exit_script = _fake_script(tmp_path, '''
raise SystemExit(3)
''', name="fake_exit.py")
    fake2 = _backend(exit_script, tmp_path)
    try:
        with pytest.raises(FakeError) as exc2:
            for _frame in fake2.stream(_payload("ok_usage", "e" * 32),
                                       deadline_monotonic=time.monotonic() + 10):
                pass
        assert exc2.value.code == "FAKE_IO_ERROR"
        assert exc2.value.receipt is not None
        assert fake2._active_proc is None
    finally:
        fake2.close()


def test_c3_04e_send_exact_bytes_compatibility_without_subprocess_run(
        tmp_path: Path, monkeypatch) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError("subprocess.run must not be used for streaming")

    monkeypatch.setattr(subprocess, "run", forbidden)
    nonce = "f" * 32
    payload = _payload("ok_usage", nonce)
    fake = FakeBackend(script=str(FAKE), receipt_dir=str(tmp_path / "receipts"),
                       python=sys.executable, timeout_s=10.0)
    try:
        receipt = fake.send_exact_bytes(payload, nonce)
        assert isinstance(receipt, FakeReceipt)
        assert receipt.nonce == nonce
        assert receipt.raw_sha256 == hashlib.sha256(payload).hexdigest()
        assert receipt.raw_length == len(payload)
        assert fake.sent_payload_digest == receipt.raw_sha256
        assert [frame["kind"] for frame in receipt.frames] == [
            "chunk", "usage", "finish"]
        assert fake.received_count() == 1
        assert fake._active_proc is None
    finally:
        fake.close()


def test_c3_04e_stream_does_not_buffer_with_communicate() -> None:
    source = Path(__file__).resolve().parents[3] / "src/autoteacher_m0/bridge/fake_backend.py"
    text = source.read_text(encoding="utf-8")
    assert "communicate(" not in text
    assert "subprocess.run(" not in text
    assert "MAX_FAKE_FRAMES = 256" in text
    assert "MAX_FAKE_TOTAL_BYTES = 1024 * 1024" in text
    assert "MAX_FAKE_FRAME_BYTES = 64 * 1024" in text
