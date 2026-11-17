"""G3-C C3-05 (P1-2): deterministic two-Controller cold start.

Before the P1-2 fix, two Controllers started against one cold AttemptJournal
could race ``PRAGMA journal_mode=WAL`` and one child died with an unhandled
``sqlite3.OperationalError: database is locked`` (3/6 in the independent
review). The frozen contract now is:

* WAL/DDL initialisation installs ``busy_timeout`` first and retries transient
  locks for a bounded ~10 s, then raises ``AttemptJournalUnavailable``;
* one Controller per socket path owns an explicit ``flock`` singleton; a
  concurrent second cold start exits with a stable code and a fixed non-zero
  exit status *before* it starts a Broker/Fake or touches the socket;
* no traceback, no second Fake send, exactly one durable Attempt/Receipt.

``test_c3_05c`` also covers the journal-unavailable controlled-exit path; the
20-round matrix records exit codes, error codes and per-round timings.
"""
from __future__ import annotations

import json
import os
import signal
import socket
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

import autoteacher_m0.bridge.controller as controller_module
from autoteacher_m0.bridge.attempts import (
    AttemptJournal, AttemptJournalUnavailable,
)
from autoteacher_m0.bridge.protocol import (
    Envelope, canonical_payload_bytes, encode_envelope, parse_envelope,
    payload_digest,
)
from test_c1_03_admission import (
    FAKE, payload, write_admission, write_broker_config,
)

ROUNDS = 20
SINGLETON_CODE = "CONTROLLER_SINGLETON_LOCKED"
JOURNAL_CODE = "ATTEMPT_JOURNAL_UNAVAILABLE"
REPLAYED_CODE = "ADMISSION_REPLAYED_AFTER_RECOVERY"
CONTROLLED_CODES = {SINGLETON_CODE: 5, REPLAYED_CODE: 3}


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _controller_config(root: Path) -> Path:
    document = {
        "admission_path": str(root / "admission.json"),
        "broker_config_path": str(root / "broker.json"),
        "fake_script": str(FAKE),
        "receipt_dir": str(root / "receipts"),
        "attempt_db": str(root / "attempts.sqlite3"),
        "socket_path": str(root / "bridge.sock"),
        "python": sys.executable,
        "expected_uid": 65534,
    }
    path = root / "controller.json"
    path.write_text(json.dumps(document))
    return path


def _spawn(config_path: Path) -> subprocess.Popen:
    env = {**os.environ,
           "PYTHONPATH": os.environ.get("PYTHONPATH", "src:artifacts/foundation/deps")}
    return subprocess.Popen(
        [sys.executable, "-B", "-m", "autoteacher_m0.bridge.controller",
         "--config", str(config_path)],
        cwd=str(Path(__file__).resolve().parents[3]), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def _wait_for_socket(socket_path: Path, procs: list[subprocess.Popen],
                     timeout: float = 25.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if socket_path.exists():
            return
        if all(proc.poll() is not None for proc in procs):
            raise AssertionError(
                "both Controllers exited before binding: "
                + repr([(proc.returncode, _stderr(proc)) for proc in procs]))
        time.sleep(0.01)
    raise AssertionError(
        "Controller socket did not appear: "
        + repr([proc.poll() for proc in procs]))


def _wait_one_exit(procs: list[subprocess.Popen], timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if any(proc.poll() is not None for proc in procs):
            return
        time.sleep(0.01)
    raise AssertionError(
        "neither Controller exited: " + repr([proc.poll() for proc in procs]))


def _stderr(proc: subprocess.Popen) -> str:
    try:
        return proc.stderr.read() if proc.stderr is not None else ""
    except (OSError, ValueError):
        return ""


def _uds_request(socket_path: Path, timeout: float = 20.0) -> list[dict]:
    deadline = time.monotonic() + timeout
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(5)
    while True:
        try:
            client.connect(str(socket_path))
            break
        except (FileNotFoundError, ConnectionRefusedError):
            if time.monotonic() >= deadline:
                client.close()
                raise
            time.sleep(0.01)
    try:
        document = payload()
        env = Envelope(v=1, kind="request", transport_id="tr-" + "e" * 32,
                       seq=0, payload=document,
                       hash=payload_digest(canonical_payload_bytes(document)))
        client.sendall(encode_envelope(env) + b"\n")
        buffer = b""
        frames: list[dict] = []
        while time.monotonic() < deadline:
            chunk = client.recv(65_536)
            if not chunk:
                break
            buffer += chunk
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                if not line:
                    continue
                parsed = parse_envelope(line + b"\n")
                frames.append({"kind": parsed.kind, "payload": parsed.payload})
            if frames and frames[-1]["kind"] in {"finish", "error"}:
                break
        return frames
    finally:
        client.close()


def _read_db(root: Path) -> dict:
    attempts = sqlite3.connect(root / "attempts.sqlite3")
    broker = sqlite3.connect(root / "broker.sqlite3")
    try:
        attempts.row_factory = sqlite3.Row
        broker.row_factory = sqlite3.Row
        attempt_rows = [dict(row) for row in attempts.execute(
            "SELECT attempt_id, call_id, reservation_id, state FROM g3b_attempts")]
        admissions = attempts.execute(
            "SELECT COUNT(*) FROM g3b_admissions").fetchone()[0]
        reservations = [dict(row) for row in broker.execute(
            "SELECT reservation_id, status, cost FROM budget_reservations")]
        claims = [dict(row) for row in broker.execute(
            "SELECT call_id, reservation_id, status FROM budget_dispatch_claims")]
    finally:
        attempts.close()
        broker.close()
    counter_path = root / "receipts" / "received-count.json"
    counter = (json.loads(counter_path.read_text())["count"]
               if counter_path.exists() else 0)
    receipt_files = sorted((root / "receipts").glob("rcpt-*.json"))
    return {
        "attempts": attempt_rows,
        "admissions": admissions,
        "reservations": reservations,
        "claims": claims,
        "fake_counter": counter,
        "receipt_files": len(receipt_files),
    }


def _write_evidence(payload_document: dict) -> None:
    target = os.environ.get("G3C_COLDSTART_EVIDENCE")
    if target:
        path = Path(target)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload_document, indent=2, sort_keys=True) + "\n")


def _write_round_log(log_dir: str | None, index: int, label: str, text: str) -> None:
    if not log_dir:
        return
    path = Path(log_dir)
    path.mkdir(parents=True, exist_ok=True)
    (path / f"round-{index:02d}-{label}.stderr.txt").write_text(text)


def test_c3_05_twocontroller_coldstart_is_deterministic(tmp_path: Path) -> None:
    """20 simultaneous cold starts: 1 winner, 1 auditable rejection, 1 Fake."""
    log_dir = os.environ.get("G3C_COLDSTART_LOG_DIR")
    started_utc = _utc()
    matrix_started = time.monotonic()
    rounds: list[dict] = []
    failures: list[str] = []
    for index in range(1, ROUNDS + 1):
        root = tmp_path / f"round-{index:02d}"
        root.mkdir()
        write_admission(root)
        write_broker_config(root)
        config_path = _controller_config(root)
        socket_path = root / "bridge.sock"
        round_started = time.monotonic()
        first, second = _spawn(config_path), _spawn(config_path)
        procs = [first, second]
        record: dict = {"round": index}
        try:
            _wait_for_socket(socket_path, procs)
            frames = _uds_request(socket_path)
            record["frames"] = [frame["kind"] for frame in frames]
            record["error_codes"] = [frame["payload"].get("code")
                                     for frame in frames if frame["kind"] == "error"]
            assert record["error_codes"] == [], frames
            assert frames[-1]["kind"] == "finish", frames

            _wait_one_exit(procs)
            alive = [proc for proc in procs if proc.poll() is None]
            exited = [proc for proc in procs if proc.poll() is not None]
            assert len(alive) == 1 and len(exited) == 1, (
                [proc.poll() for proc in procs])
            winner, loser = alive[0], exited[0]
            record["winner"] = "first" if winner is first else "second"
            assert loser.wait(timeout=10) == CONTROLLED_CODES[SINGLETON_CODE], (
                loser.returncode, _stderr(loser))
            loser_text = _stderr(loser)
            record["loser_exit"] = loser.returncode
            record["loser_code"] = SINGLETON_CODE
            record["loser_stderr"] = loser_text.strip()
            assert SINGLETON_CODE in loser_text
            assert "Traceback" not in loser_text

            winner.send_signal(signal.SIGTERM)
            record["winner_exit"] = winner.wait(timeout=20)
            winner_text = _stderr(winner)
            record["winner_stderr"] = winner_text.strip()
            assert record["winner_exit"] == 0, (record["winner_exit"], winner_text)
            assert "Traceback" not in winner_text
            assert not socket_path.exists()

            db = _read_db(root)
            record.update(db)
            assert db["fake_counter"] == 1, db
            assert db["receipt_files"] == 1, db
            assert len(db["attempts"]) == 1, db
            assert db["attempts"][0]["state"] == "SETTLED", db
            assert db["admissions"] == 1, db
            assert len(db["reservations"]) == 1, db
            assert db["reservations"][0]["status"] == "OK", db
            assert len(db["claims"]) == 1, db
            assert db["claims"][0]["status"] == "COMPLETED", db
            _write_round_log(log_dir, index, record["winner"], winner_text)
            _write_round_log(log_dir, index, "loser", loser_text)
        except BaseException as exc:  # record every round before failing the test
            record["failure"] = f"{type(exc).__name__}: {exc}"
            failures.append(f"round {index}: {record['failure']}")
            _write_round_log(log_dir, index, "first", _stderr(first))
            _write_round_log(log_dir, index, "second", _stderr(second))
            raise
        finally:
            for proc in procs:
                if proc.poll() is None:
                    proc.kill()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
                for stream in (proc.stdout, proc.stderr):
                    if stream is not None:
                        stream.close()
            record["duration_ms"] = int((time.monotonic() - round_started) * 1000)
            record["finished_utc"] = _utc()
            rounds.append(record)
    assert not failures, failures
    _write_evidence({
        "schema": "m0.g3c.concurrency-coldstart.v1",
        "started_utc": started_utc,
        "finished_utc": _utc(),
        "duration_ms": int((time.monotonic() - matrix_started) * 1000),
        "rounds_requested": ROUNDS,
        "rounds_completed": len(rounds),
        "contract": {
            "winner_count": 1,
            "controlled_exit_codes": CONTROLLED_CODES,
            "fake_counter": 1,
            "no_traceback": True,
        },
        "summary": {
            "controlled_singleton": sum(
                1 for item in rounds if item.get("loser_code") == SINGLETON_CODE),
            "controlled_admission_replay": sum(
                1 for item in rounds if item.get("loser_code") == REPLAYED_CODE),
            "tracebacks": sum(
                1 for item in rounds
                if "Traceback" in item.get("loser_stderr", "")
                or "Traceback" in item.get("winner_stderr", "")),
            "fake_counters": sorted({item.get("fake_counter") for item in rounds}),
            "attempt_states": sorted(
                {item["attempts"][0]["state"] for item in rounds
                 if item.get("attempts")}),
        },
        "rounds": rounds,
    })


# -- journal initialisation (P1-2 root cause) --------------------------

def _blank_delete_mode_db(path: Path) -> None:
    conn = sqlite3.connect(path, isolation_level=None)
    try:
        conn.execute("PRAGMA journal_mode=DELETE")
        conn.execute("CREATE TABLE IF NOT EXISTS seed (value TEXT)")
    finally:
        conn.close()


def test_c3_05a_journal_wal_lock_is_retried_then_succeeds(tmp_path: Path) -> None:
    db = tmp_path / "attempts.sqlite3"
    _blank_delete_mode_db(db)
    blocker = sqlite3.connect(db, isolation_level=None, check_same_thread=False)
    blocker.execute("BEGIN EXCLUSIVE")
    released = threading.Event()

    def release() -> None:
        time.sleep(0.3)
        blocker.execute("COMMIT")
        released.set()

    thread = threading.Thread(target=release, name="g3c-release-wal-lock")
    thread.start()
    journal = None
    try:
        journal = AttemptJournal(db, init_retry_seconds=5.0,
                                 init_retry_interval=0.02)
        assert released.is_set()
        assert journal.init_attempts >= 2, journal.init_attempts
        mode = journal.conn.execute("PRAGMA journal_mode").fetchone()[0]
        busy = journal.conn.execute("PRAGMA busy_timeout").fetchone()[0]
        assert mode == "wal", mode
        assert busy == 10_000, busy
    finally:
        if journal is not None:
            journal.close()
        thread.join(timeout=5)
        blocker.close()


def test_c3_05b_journal_exhausted_lock_is_a_stable_unavailable_error(
        tmp_path: Path) -> None:
    db = tmp_path / "attempts.sqlite3"
    _blank_delete_mode_db(db)
    blocker = sqlite3.connect(db, isolation_level=None)
    blocker.execute("BEGIN EXCLUSIVE")
    started = time.monotonic()
    try:
        with pytest.raises(AttemptJournalUnavailable) as excinfo:
            AttemptJournal(db, init_retry_seconds=0.35, init_retry_interval=0.02)
        elapsed = time.monotonic() - started
        assert excinfo.value.code == JOURNAL_CODE
        assert isinstance(excinfo.value.__cause__, sqlite3.OperationalError)
        assert "locked" in str(excinfo.value.__cause__).lower()
        assert elapsed < 2.0, elapsed
    finally:
        blocker.execute("COMMIT")
        blocker.close()


def test_c3_05c_journal_unavailable_exits_4_and_cleans_up(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]) -> None:
    write_admission(tmp_path)
    write_broker_config(tmp_path)
    config_path = _controller_config(tmp_path)
    created: dict = {}
    real_broker = controller_module.BrokerClient
    real_fake = controller_module.FakeBackend

    class RecordingBroker(real_broker):  # type: ignore[misc, valid-type]
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            created["broker"] = self

    class RecordingFake(real_fake):  # type: ignore[misc, valid-type]
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            created["fake"] = self

    class UnavailableJournal:
        def __init__(self, *args, **kwargs):
            raise AttemptJournalUnavailable()

    monkeypatch.setattr(controller_module, "BrokerClient", RecordingBroker)
    monkeypatch.setattr(controller_module, "FakeBackend", RecordingFake)
    monkeypatch.setattr(controller_module, "AttemptJournal", UnavailableJournal)

    assert controller_module.main(["--config", str(config_path)]) == 4
    first = capsys.readouterr()
    assert JOURNAL_CODE in first.err
    assert "Traceback" not in first.err
    assert created["broker"].proc is None, "Broker child must be reaped"
    assert getattr(created["fake"], "_active_proc", None) is None
    assert not (tmp_path / "bridge.sock").exists()
    # The singleton lock must be released on the controlled-exit path.
    assert controller_module.main(["--config", str(config_path)]) == 4
    second = capsys.readouterr()
    assert JOURNAL_CODE in second.err
    assert SINGLETON_CODE not in second.err


def test_c3_05d_concurrent_journal_init_has_no_unhandled_lock(
        tmp_path: Path) -> None:
    """The original P1-2 race, without the controller singleton in the way.

    Two *processes* construct an AttemptJournal against one cold DB at the same
    time. Both must either initialise or retry to success; neither may leak an
    unhandled ``sqlite3.OperationalError``.
    """
    script = (
        "import sys\n"
        "sys.path.insert(0, 'src')\n"
        "from autoteacher_m0.bridge.attempts import AttemptJournal\n"
        "journal = AttemptJournal(sys.argv[1], init_retry_seconds=5.0,\n"
        "                         init_retry_interval=0.02)\n"
        "mode = journal.conn.execute('PRAGMA journal_mode').fetchone()[0]\n"
        "print(f'{journal.init_attempts} {mode}')\n"
        "journal.close()\n"
    )
    env = {**os.environ,
           "PYTHONPATH": os.environ.get("PYTHONPATH", "src:artifacts/foundation/deps")}
    failures: list[str] = []
    for index in range(ROUNDS):
        db = tmp_path / f"journal-race-{index:02d}.sqlite3"
        procs = [subprocess.Popen(
            [sys.executable, "-B", "-c", script, str(db)],
            cwd=str(Path(__file__).resolve().parents[3]), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            for _ in range(2)]
        outputs = [proc.communicate(timeout=30) for proc in procs]
        for proc, (stdout, stderr) in zip(procs, outputs):
            if proc.returncode != 0 or "Traceback" in stderr:
                failures.append(
                    f"round {index}: rc={proc.returncode} "
                    f"stdout={stdout!r} stderr={stderr[-400:]!r}")
            else:
                attempts, mode = stdout.split()
                assert int(attempts) >= 1
                assert mode == "wal", (attempts, mode)
    assert not failures, failures
