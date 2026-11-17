"""D1-A additive UDS boundary: mode/GID, SO_PEERCRED, ready and stale cleanup.

These are host pytest tests (``raw-UDS``/``host pytest`` evidence class). They
use real AF_UNIX sockets and, for the denied-UID case, a real forked process
with a different kernel UID; they never mock a successful peer credential.

Frozen G3-C behaviour (framing/deadline/cancel/streaming/error codes) is not
re-tested here and remains covered by ``tests/integration/g3c`` and
``tests/integration/g3_bridge``.
"""
from __future__ import annotations

import errno
import json
import os
import select
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from autoteacher_m0.bridge import controller as controller_module
from autoteacher_m0.bridge import ipc_server
from autoteacher_m0.bridge.admission import AdmissionError, load_admission
from autoteacher_m0.bridge.ipc_server import (
    PEER_UID_DENIED,
    PEERCRED_UNAVAILABLE,
    BridgeServer,
)
from autoteacher_m0.bridge.protocol import (
    Envelope,
    canonical_payload_bytes,
    encode_envelope,
    parse_envelope,
    payload_digest,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
# Reuse the frozen G3-B real Broker/Fake/Admission fixtures instead of
# duplicating that business setup. That directory has no __init__.py, so add
# it explicitly for standalone runs of this file.
_G3B_TEST_DIR = Path(__file__).resolve().parents[1] / "g3_bridge"
if str(_G3B_TEST_DIR) not in sys.path:
    sys.path.insert(0, str(_G3B_TEST_DIR))
from test_controller import _controller, _payload  # noqa: E402

TRANSPORT_ID = "tr-" + "d" * 32


class _StubController:
    """Minimal real protocol peer: one finish per request, no business state."""

    def __init__(self) -> None:
        self.requests = 0
        self.cancel_calls: list[tuple[str, str]] = []

    def handle_envelope(self, env):
        self.requests += 1
        yield Envelope(1, "finish", env.transport_id, 2,
                       {"reason": {"kind": "stop"}}, None)

    def cancel(self, *, transport_id: str, reason: str) -> None:
        self.cancel_calls.append((transport_id, reason))


def _request_bytes() -> bytes:
    payload = _payload()
    envelope = Envelope(v=1, kind="request", transport_id=TRANSPORT_ID, seq=0,
                        payload=payload,
                        hash=payload_digest(canonical_payload_bytes(payload)))
    return encode_envelope(envelope) + b"\n"


def _wait_until(predicate, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return bool(predicate())


def _read_frames(client: socket.socket, timeout: float = 10.0) -> list[Envelope]:
    client.settimeout(timeout)
    buffer = b""
    frames: list[Envelope] = []
    while True:
        chunk = client.recv(65_536)
        if not chunk:
            break
        buffer += chunk
        while b"\n" in buffer:
            line, buffer = buffer.split(b"\n", 1)
            if line:
                frames.append(parse_envelope(line))
        if frames and frames[-1].kind in {"finish", "error"}:
            break
    return frames


def _read_until_closed(client: socket.socket, timeout: float = 5.0) -> bytes:
    """Return any bytes before EOF; ECONNRESET counts as an empty EOF."""
    client.settimeout(timeout)
    data = b""
    while True:
        try:
            chunk = client.recv(65_536)
        except ConnectionResetError:
            return data
        if not chunk:
            return data
        data += chunk


class _RunningServer:
    def __init__(self, socket_path: Path | str, controller=None, **kwargs) -> None:
        self.path = str(socket_path)
        self.controller = controller  # None keeps the stub for simple cases
        self.server = BridgeServer(controller or _StubController(), self.path, **kwargs)
        self.error: BaseException | None = None
        self.thread = threading.Thread(target=self._run, name="d1a-test-server",
                                       daemon=True)
        self.thread.start()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if self.error is not None:
                break
            if os.path.exists(self.path) and self._listening():
                break
            time.sleep(0.01)
        if self.error is not None:
            raise self.error
        assert os.path.exists(self.path), "server did not bind"
        assert self._listening(), "server did not listen"

    def _run(self) -> None:
        try:
            self.server.serve_forever()
        except BaseException as exc:  # surfaced to the test thread
            self.error = exc

    def _listening(self) -> bool:
        server_sock = self.server._server
        if server_sock is None:
            return False
        try:
            return bool(server_sock.getsockopt(socket.SOL_SOCKET,
                                               socket.SO_ACCEPTCONN))
        except OSError:
            return False

    def connect(self, timeout: float = 5.0) -> socket.socket:
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.settimeout(timeout)
        client.connect(self.path)
        return client

    def request(self) -> list[Envelope]:
        client = self.connect()
        try:
            client.sendall(_request_bytes())
            return _read_frames(client)
        finally:
            client.close()

    def stop(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=5)
        assert not self.thread.is_alive(), "server thread did not stop"


def _make_stale_socket(path: Path) -> None:
    stale = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        stale.bind(str(path))
    finally:
        stale.close()
    assert stat.S_ISSOCK(os.lstat(path).st_mode)


# -- default compatibility ------------------------------------------------
def test_default_is_0600_legacy_behaviour(tmp_path: Path) -> None:
    runner = _RunningServer(tmp_path / "bridge.sock")
    try:
        info = os.lstat(runner.path)
        assert stat.S_ISSOCK(info.st_mode)
        assert stat.S_IMODE(info.st_mode) == 0o600
        assert info.st_uid == os.geteuid()
        assert runner.server.socket_mode == 0o600
        assert runner.server.socket_gid is None
        assert runner.server.expected_peer_uid is None
        assert runner.server.on_ready is None
        frames = runner.request()
        assert [frame.kind for frame in frames] == ["ack", "finish"]
        assert runner.server.peer_rejections == []
    finally:
        runner.stop()
    assert not os.path.exists(runner.path)


# -- mode / gid -----------------------------------------------------------
@pytest.mark.skipif(os.geteuid() != 0,
                    reason="requires root to chown a socket to gid 65534")
def test_0660_with_explicit_gid_has_exact_stat(tmp_path: Path) -> None:
    runner = _RunningServer(tmp_path / "bridge.sock", socket_mode=0o660,
                            socket_gid=65534)
    try:
        info = os.lstat(runner.path)
        assert stat.S_IMODE(info.st_mode) == 0o660
        assert info.st_uid == 0
        assert info.st_gid == 65534
        assert [frame.kind for frame in runner.request()] == ["ack", "finish"]
    finally:
        runner.stop()


@pytest.mark.skipif(os.geteuid() != 0,
                    reason="requires root to build a root:2000 setgid IPC dir")
def test_0660_inherits_setgid_directory_without_chown(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """CAP_CHOWN-free deployment: group comes from a 2750 root:2000 parent."""
    ipc_dir = tmp_path / "ipc"
    ipc_dir.mkdir()
    os.chown(ipc_dir, 0, 2000)
    os.chmod(ipc_dir, 0o2750)
    calls: list[tuple] = []
    real_chown = os.chown

    def recording_chown(*args, **kwargs):
        calls.append(args)
        return real_chown(*args, **kwargs)

    monkeypatch.setattr(ipc_server.os, "chown", recording_chown)
    runner = _RunningServer(ipc_dir / "bridge.sock", socket_mode=0o660)
    try:
        info = os.lstat(runner.path)
        assert stat.S_IMODE(info.st_mode) == 0o660
        assert info.st_gid == 2000
        assert calls == [], "socket_gid=None must not call chown"
        assert stat.S_IMODE(os.lstat(ipc_dir).st_mode) == 0o2750
    finally:
        runner.stop()


@pytest.mark.parametrize("mode", [
    0o666, 0o777, 0o770, 0o640, 0o400, 0, True, False, 600.0, "600", None,
])
def test_unsafe_or_unknown_socket_mode_is_rejected(tmp_path: Path, mode) -> None:
    with pytest.raises(ValueError):
        BridgeServer(_StubController(), str(tmp_path / "bridge.sock"),
                     socket_mode=mode)


@pytest.mark.parametrize("value", [True, False, -1, 0xFFFFFFFF, 2**32, "0", 1.0])
@pytest.mark.parametrize("field", ["socket_gid", "expected_peer_uid"])
def test_invalid_uid_or_gid_is_rejected(tmp_path: Path, field: str, value) -> None:
    with pytest.raises(ValueError):
        BridgeServer(_StubController(), str(tmp_path / "bridge.sock"),
                     **{field: value})


def test_boundary_identifier_limits_accepted(tmp_path: Path) -> None:
    for value in (0, 1, 65534, 0xFFFFFFFE):
        server = BridgeServer(_StubController(), str(tmp_path / f"{value}.sock"),
                              socket_mode=0o660, socket_gid=value,
                              expected_peer_uid=value)
        assert server.socket_gid == value
        assert server.expected_peer_uid == value


def test_contradictory_boundary_config_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        # A group with no group permission bits is incoherent.
        BridgeServer(_StubController(), str(tmp_path / "bridge.sock"),
                     socket_mode=0o600, socket_gid=0)
    with pytest.raises(ValueError):
        BridgeServer(_StubController(), str(tmp_path / "bridge.sock"),
                     on_ready=object())  # type: ignore[arg-type]


# -- peer credentials -----------------------------------------------------
def test_matching_peer_uid_allows_roundtrip_and_records_credentials(
        tmp_path: Path) -> None:
    controller = _StubController()
    # The host pytest process is root here; 0 is the real current peer UID.
    runner = _RunningServer(tmp_path / "bridge.sock", controller,
                            expected_peer_uid=os.geteuid())
    try:
        frames = runner.request()
        assert [frame.kind for frame in frames] == ["ack", "finish"]
        assert _wait_until(lambda: bool(runner.server.peer_credentials))
        uid, gid, pid = runner.server.peer_credentials[0]
        assert uid == os.geteuid()
        assert gid == os.getegid()
        assert isinstance(pid, int)  # evidence only; never used for identity
        assert runner.server.peer_rejections == []
    finally:
        runner.stop()


@pytest.mark.skipif(os.geteuid() != 0,
                    reason="requires root to fork a real UID-65534 peer")
def test_foreign_peer_uid_is_denied_without_ack_and_without_business_calls(
        tmp_path: Path) -> None:
    """Real kernel credential (fork + setuid 65534), not a mocked UID."""
    controller, broker, fake, attempts = _controller(tmp_path)
    socket_dir = Path(tempfile.mkdtemp(prefix="at-d1a-peer-", dir="/tmp"))
    os.chmod(socket_dir, 0o755)
    socket_path = socket_dir / "bridge.sock"
    server = BridgeServer(controller, str(socket_path), socket_mode=0o660,
                          socket_gid=65534, expected_peer_uid=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    child_pid = -1
    try:
        assert _wait_until(lambda: os.path.exists(socket_path))

        read_fd, write_fd = os.pipe()
        child_pid = os.fork()
        if child_pid == 0:  # child: real foreign-uid client, no pytest cleanup
            try:
                os.close(read_fd)
                os.setgroups([65534])
                os.setgid(65534)
                os.setuid(65534)
                child = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                child.settimeout(5)
                child.connect(str(socket_path))
                try:
                    child.sendall(_request_bytes())
                except (BrokenPipeError, ConnectionResetError):
                    pass
                data = _read_until_closed(child)
                os.write(write_fd, b"DATA" if data else b"EOF")
                os._exit(0)
            except BaseException:  # noqa: BLE001 - child reports, never raises
                try:
                    os.write(write_fd, b"ERROR")
                except OSError:
                    pass
                os._exit(1)
        os.close(write_fd)
        try:
            ready, _, _ = select.select([read_fd], [], [], 10)
            result = os.read(read_fd, 64) if ready else b""
        finally:
            os.close(read_fd)
        _reap_child(child_pid)
        child_pid = -1

        assert result == b"EOF", result  # no ack, no protocol error frame
        assert server.peer_rejections == [PEER_UID_DENIED]
        assert server.peer_credentials
        assert server.peer_credentials[0][:2] == (65534, 65534)
        assert broker.snapshot()["snapshot"]["requests"] == 0
        assert fake.received_count() == 0
        assert attempts.conn.execute(
            "SELECT COUNT(*) FROM g3b_attempts").fetchone()[0] == 0
    finally:
        if child_pid > 0:
            try:
                os.kill(child_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                os.waitpid(child_pid, 0)
            except ChildProcessError:
                pass
        server.shutdown()
        thread.join(timeout=5)
        broker.close()
        fake.close()
        attempts.close()
        shutil.rmtree(socket_dir, ignore_errors=True)


def _reap_child(pid: int, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        reaped, _ = os.waitpid(pid, os.WNOHANG)
        if reaped == pid:
            return
        time.sleep(0.01)
    os.kill(pid, signal.SIGKILL)
    os.waitpid(pid, 0)
    raise AssertionError("foreign-uid probe did not exit")


def _patch_peercred(monkeypatch: pytest.MonkeyPatch, behaviour) -> None:
    original = socket.socket.getsockopt

    def fake_getsockopt(self, level, optname, *args):
        if level == socket.SOL_SOCKET and optname == socket.SO_PEERCRED:
            return behaviour()
        return original(self, level, optname, *args)

    monkeypatch.setattr(socket.socket, "getsockopt", fake_getsockopt)


@pytest.mark.parametrize("failure", ["oserror", "short", "exception"])
def test_peercred_failure_fails_closed(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str) -> None:
    controller = _StubController()
    runner = _RunningServer(tmp_path / "bridge.sock", controller,
                            expected_peer_uid=0)
    try:
        if failure == "oserror":
            _patch_peercred(monkeypatch, lambda: (_ for _ in ()).throw(
                OSError(errno.ENOTSUP, "peercred unsupported")))
        elif failure == "short":
            _patch_peercred(monkeypatch, lambda: b"\x00" * 4)
        else:
            _patch_peercred(monkeypatch, lambda: (_ for _ in ()).throw(
                RuntimeError("peercred exploded")))

        client = runner.connect()
        try:
            try:
                client.sendall(_request_bytes())
            except (BrokenPipeError, ConnectionResetError):
                pass
            assert _read_until_closed(client) == b""
        finally:
            client.close()
        assert _wait_until(lambda: bool(runner.server.peer_rejections))
        assert runner.server.peer_rejections == [PEERCRED_UNAVAILABLE]
        assert controller.requests == 0
    finally:
        runner.stop()


# -- ready callback -------------------------------------------------------
def test_on_ready_fires_after_listen_and_permissions_exactly_once(
        tmp_path: Path) -> None:
    socket_path = tmp_path / "bridge.sock"
    calls: list[tuple[int, int, int, int]] = []
    holder: list[BridgeServer] = []

    def on_ready() -> None:
        info = os.lstat(socket_path)
        accepting = holder[0]._server.getsockopt(socket.SOL_SOCKET,
                                                 socket.SO_ACCEPTCONN)
        calls.append((stat.S_IMODE(info.st_mode), info.st_uid, info.st_gid,
                      accepting))

    server = BridgeServer(_StubController(), str(socket_path), on_ready=on_ready)
    holder.append(server)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        assert _wait_until(lambda: bool(calls))
        assert calls == [(0o600, os.geteuid(), os.getegid(), 1)]
        for _ in range(2):
            client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client.settimeout(5)
            client.connect(str(socket_path))
            client.sendall(_request_bytes())
            assert [frame.kind for frame in _read_frames(client)] == [
                "ack", "finish"]
            client.close()
        assert len(calls) == 1
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_on_ready_is_not_called_when_boundary_rejects(tmp_path: Path) -> None:
    target = tmp_path / "outside.txt"
    target.write_text("keep", encoding="utf-8")
    socket_path = tmp_path / "bridge.sock"
    socket_path.symlink_to(target)
    calls: list[int] = []
    server = BridgeServer(_StubController(), str(socket_path),
                          on_ready=lambda: calls.append(1))
    with pytest.raises(RuntimeError):
        server.serve_forever()
    assert calls == []


# -- stale socket cleanup -------------------------------------------------
def test_stale_socket_is_replaced(tmp_path: Path) -> None:
    socket_path = tmp_path / "bridge.sock"
    _make_stale_socket(socket_path)
    runner = _RunningServer(socket_path)
    try:
        # The verified stale inode was unlinked and this server listens on the
        # same configured path (inode numbers may be reused by the kernel).
        assert os.path.exists(runner.path)
        assert runner._listening()
        frames = runner.request()
        assert frames[0].kind == "ack"
        assert frames[-1].kind == "finish"
        assert "error" not in [frame.kind for frame in frames]
    finally:
        runner.stop()


def test_stale_symlink_is_rejected_and_preserved(tmp_path: Path) -> None:
    target = tmp_path / "outside.txt"
    target.write_text("keep", encoding="utf-8")
    socket_path = tmp_path / "bridge.sock"
    socket_path.symlink_to(target)
    server = BridgeServer(_StubController(), str(socket_path))
    with pytest.raises(RuntimeError):
        server.serve_forever()
    assert socket_path.is_symlink()
    assert target.read_text(encoding="utf-8") == "keep"


def test_stale_regular_file_is_rejected_and_preserved(tmp_path: Path) -> None:
    socket_path = tmp_path / "bridge.sock"
    socket_path.write_text("not a socket", encoding="utf-8")
    server = BridgeServer(_StubController(), str(socket_path))
    with pytest.raises(RuntimeError):
        server.serve_forever()
    assert socket_path.read_text(encoding="utf-8") == "not a socket"


@pytest.mark.skipif(os.geteuid() != 0,
                    reason="requires root to chown a stale socket to uid 65534")
def test_stale_socket_with_foreign_owner_is_rejected(tmp_path: Path) -> None:
    socket_path = tmp_path / "bridge.sock"
    _make_stale_socket(socket_path)
    os.chown(socket_path, 65534, 65534)
    server = BridgeServer(_StubController(), str(socket_path))
    with pytest.raises(RuntimeError):
        server.serve_forever()
    info = os.lstat(socket_path)
    assert stat.S_ISSOCK(info.st_mode)
    assert info.st_uid == 65534


def test_stale_unlink_failure_aborts_startup(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    socket_path = tmp_path / "bridge.sock"
    _make_stale_socket(socket_path)
    real_unlink = os.unlink

    def failing_unlink(target, *args, **kwargs):
        if os.fspath(target) == str(socket_path):
            raise OSError(errno.EACCES, "denied")
        return real_unlink(target, *args, **kwargs)

    monkeypatch.setattr(ipc_server.os, "unlink", failing_unlink)
    calls: list[int] = []
    server = BridgeServer(_StubController(), str(socket_path),
                          on_ready=lambda: calls.append(1))
    with pytest.raises(RuntimeError):
        server.serve_forever()
    assert calls == []
    assert stat.S_ISSOCK(os.lstat(socket_path).st_mode)
    probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    probe.settimeout(1)
    with pytest.raises(ConnectionRefusedError):
        probe.connect(str(socket_path))
    probe.close()
    monkeypatch.setattr(ipc_server.os, "unlink", real_unlink)


# -- controller.main plumbing --------------------------------------------
class _FakeBroker:
    def __init__(self, *args, **kwargs) -> None:
        pass

    def start(self) -> None:
        pass

    def close(self) -> None:
        pass


class _FakeFakeBackend:
    def __init__(self, *args, **kwargs) -> None:
        pass

    def close(self) -> None:
        pass


class _FakeAttempts:
    def __init__(self, *args, **kwargs) -> None:
        self.registered: list[tuple] = []

    def register_admission(self, *args) -> None:
        self.registered.append(args)

    def close(self) -> None:
        pass


class _FakeTrustedController:
    def __init__(self, admission, **kwargs) -> None:
        self.admission = admission
        self.instance_id = "ctl-d1a-test"
        self.expected_uid = kwargs.get("expected_uid")

    def reconcile_on_startup(self, receipt_dir) -> None:
        pass


class _RecordingBridgeServer:
    instances: list["_RecordingBridgeServer"] = []

    def __init__(self, controller, socket_path, **kwargs) -> None:
        self.controller = controller
        self.socket_path = socket_path
        self.kwargs = kwargs
        self.served = False
        _RecordingBridgeServer.instances.append(self)

    def serve_forever(self) -> None:
        self.served = True

    def shutdown(self) -> None:
        pass


def _write_main_config(tmp_path: Path, **overrides) -> Path:
    config = {
        "admission_path": str(tmp_path / "admission.json"),
        "broker_config_path": str(tmp_path / "broker.json"),
        "fake_script": str(tmp_path / "fake.py"),
        "receipt_dir": str(tmp_path / "receipts"),
        "attempt_db": str(tmp_path / "attempts.sqlite3"),
        "socket_path": str(tmp_path / "bridge.sock"),
        "python": sys.executable,
        "expected_uid": 65534,
    }
    config.update(overrides)
    path = tmp_path / "controller.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


def _install_main_fakes(monkeypatch: pytest.MonkeyPatch) -> None:
    admission = SimpleNamespace(admission_id="a" * 32, sha256="b" * 64,
                                run_id="run-d1a", fake_scenario="ok_usage")
    monkeypatch.setattr(controller_module, "load_admission",
                        lambda *args, **kwargs: admission)
    monkeypatch.setattr(controller_module, "BrokerClient", _FakeBroker)
    monkeypatch.setattr(controller_module, "FakeBackend", _FakeFakeBackend)
    monkeypatch.setattr(controller_module, "AttemptJournal", _FakeAttempts)
    monkeypatch.setattr(controller_module, "TrustedController", _FakeTrustedController)
    monkeypatch.setattr(controller_module, "BridgeServer", _RecordingBridgeServer)
    _RecordingBridgeServer.instances.clear()


def _run_main(path: Path, *, on_ready=None) -> int:
    old_term = signal.getsignal(signal.SIGTERM)
    old_int = signal.getsignal(signal.SIGINT)
    try:
        return controller_module.main(["--config", str(path)], on_ready=on_ready)
    finally:
        signal.signal(signal.SIGTERM, old_term)
        signal.signal(signal.SIGINT, old_int)


def test_controller_main_defaults_to_legacy_socket_options(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _install_main_fakes(monkeypatch)
    assert _run_main(_write_main_config(tmp_path)) == 0
    instance = _RecordingBridgeServer.instances[-1]
    assert instance.socket_path == str(tmp_path / "bridge.sock")
    assert instance.kwargs["socket_mode"] == 0o600
    assert instance.kwargs["socket_gid"] is None
    assert instance.kwargs["expected_peer_uid"] is None
    assert instance.kwargs["on_ready"] is None
    assert instance.served is True


def test_controller_main_passes_additive_socket_options(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _install_main_fakes(monkeypatch)
    ready_calls: list[int] = []
    config = _write_main_config(tmp_path, socket_mode=0o660, socket_gid=65534,
                                expected_peer_uid=0)
    assert _run_main(config, on_ready=lambda: ready_calls.append(1)) == 0
    instance = _RecordingBridgeServer.instances[-1]
    assert instance.kwargs["socket_mode"] == 0o660
    assert instance.kwargs["socket_gid"] == 65534
    assert instance.kwargs["expected_peer_uid"] == 0
    # The business Admission expected_uid stays a separate field at 65534.
    assert instance.controller.expected_uid == 65534
    instance.kwargs["on_ready"]()
    assert ready_calls == [1]


@pytest.mark.parametrize("overrides", [
    {"socket_mode": 0o666},
    {"socket_mode": 0o777},
    {"socket_mode": True},
    {"socket_gid": True},
    {"socket_gid": -1},
    {"expected_peer_uid": 2**32},
    {"socket_mode": 0o600, "socket_gid": 0},
])
def test_controller_main_rejects_invalid_socket_config(
        tmp_path: Path, overrides: dict) -> None:
    path = _write_main_config(tmp_path, **overrides)
    with pytest.raises(SystemExit) as excinfo:
        controller_module.main(["--config", str(path)])
    assert excinfo.value.code == "CONFIG_INVALID"


# -- business vs OS peer UID separation -----------------------------------
@pytest.mark.skipif(os.geteuid() != 0,
                    reason="expected_peer_uid=0 is only a valid acceptance case for a host-root test process")
def test_admission_launcher_uid_is_not_the_socket_peer_uid(
        tmp_path: Path) -> None:
    controller, broker, fake, attempts = _controller(tmp_path)
    try:
        admission = controller.admission
        assert admission.launcher_uid == 65534
        assert controller.expected_uid == 65534
        runner = _RunningServer(tmp_path / "bridge.sock", controller,
                                expected_peer_uid=0)
        try:
            assert runner.server.expected_peer_uid == 0
            frames = runner.request()
            assert frames[0].kind == "ack"
            assert frames[-1].kind == "finish"
            assert "error" not in [frame.kind for frame in frames]
            # The OS check did not rewrite the business UID contract.
            assert controller.expected_uid == 65534
            with pytest.raises(AdmissionError) as excinfo:
                load_admission(tmp_path / "admission.json", expected_uid=0)
            assert excinfo.value.code == "ADMISSION_LAUNCHER_MISMATCH"
        finally:
            runner.stop()
    finally:
        broker.close()
        fake.close()
        attempts.close()


# -- SIGTERM cleanup ------------------------------------------------------
_CHILD_SERVER = r"""
import os
import signal
import sys

from autoteacher_m0.bridge.ipc_server import BridgeServer


class _Controller:
    def handle_envelope(self, env):
        return iter(())


def main() -> int:
    socket_path = sys.argv[1]
    ready_path = sys.argv[2]

    def _ready() -> None:
        with open(ready_path, "w", encoding="ascii") as handle:
            handle.write(f"{os.getpid()}\n")

    server = BridgeServer(_Controller(), socket_path, on_ready=_ready)
    signal.signal(signal.SIGTERM, lambda *_: server.shutdown())
    signal.signal(signal.SIGINT, lambda *_: server.shutdown())
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
"""


def test_sigterm_cleans_up_socket_and_exits_zero(tmp_path: Path) -> None:
    socket_path = tmp_path / "bridge.sock"
    ready_path = tmp_path / "ready"
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    parts = [str(REPO_ROOT / "src"), str(REPO_ROOT / "artifacts/foundation/deps")]
    if env.get("PYTHONPATH"):
        parts.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(parts)
    proc = subprocess.Popen(
        [sys.executable, "-B", "-c", _CHILD_SERVER, str(socket_path),
         str(ready_path)],
        cwd=str(REPO_ROOT), env=env, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True)
    try:
        assert _wait_until(lambda: ready_path.exists() and socket_path.exists(),
                           15), (proc.poll(), proc.stdout, proc.stderr)
        assert proc.poll() is None
        proc.send_signal(signal.SIGTERM)
        stdout, stderr = proc.communicate(timeout=15)
        returncode = proc.returncode
    finally:
        if proc.poll() is None:
            proc.kill()
            stdout, stderr = proc.communicate()
            returncode = proc.returncode
    assert returncode == 0, (returncode, stdout, stderr)
    assert not os.path.exists(socket_path), "SIGTERM left the socket behind"
