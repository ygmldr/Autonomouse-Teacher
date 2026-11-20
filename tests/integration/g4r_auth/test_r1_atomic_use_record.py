"""G4-R R1: atomic no-replace single-use authorization records (P2-03).

This suite covers the G4-R acceptance cases R1-01..R1-06 and R1-08 support:

* R1-01 two-thread barrier convergence over >= 200 rounds,
* R1-02 two-process convergence with independent file descriptors over >= 50
  rounds (forked children; no shared Python objects for the race),
* R1-03 cross-epoch racing consumers: exactly one success, loser EPOCH_MISMATCH,
* R1-04 a persisted corrupt/zero-byte final is still INVALID (never REPLAYED)
  and the module has no Reserve/Claim/Broker path at all,
* R1-05 publisher crash injection before write / after fsync before link / after
  link before directory fsync: restart never double-authorizes and no failed
  call reports success,
* R1-06 unsupported link / cross-device / permission denied / symlink /
  hardlink anomaly / directory fsync failure all fail closed with no fallback
  to direct final-name writes.

Everything is synthetic: TEST_ONLY_ Ed25519 fixtures in a pytest temporary
directory, no key, no model, no provider, no external socket.
"""
from __future__ import annotations

import ast
import copy
from concurrent.futures import ThreadPoolExecutor
import errno
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import threading

import pytest

from autoteacher_m0.security import authorization as authorization_module
from autoteacher_m0.security.authorization import (
    AuthorizationRejected,
    consume_execution_authorization,
)
from g4a_support import RUN_EPOCH, base_payload

THREAD_ROUNDS = int(os.environ.get("G4R_R1_THREAD_ROUNDS", "200"))
PROCESS_ROUNDS = int(os.environ.get("G4R_R1_PROCESS_ROUNDS", "50"))
CROSS_EPOCH_ROUNDS = int(os.environ.get("G4R_R1_EPOCH_ROUNDS", "20"))

AUTH_ID = "auth-g4a-synthetic-1"
TEMP_PREFIX = authorization_module._USE_RECORD_TEMP_PREFIX


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _record_path_for(fixture, authorization_id: str) -> Path:
    digest = hashlib.sha256(authorization_id.encode("ascii")).hexdigest()
    return fixture.use_log / (digest + ".json")


def _round_authorization(fixture, *, prefix: str, index: int) -> str:
    payload = copy.deepcopy(base_payload(fixture.bindings.as_dict()))
    payload["authorization_id"] = f"{prefix}-{index}"
    fixture.write_signed(payload)
    return payload["authorization_id"]


def _final_names(fixture) -> list[str]:
    return sorted(path.name for path in fixture.use_log.iterdir()
                  if path.is_file() and not path.name.startswith(TEMP_PREFIX))


def _temp_names(fixture) -> list[str]:
    return sorted(path.name for path in fixture.use_log.iterdir()
                  if path.name.startswith(TEMP_PREFIX))


def _expect_rejected(call, code: str) -> AuthorizationRejected:
    with pytest.raises(AuthorizationRejected) as info:
        call()
    assert info.value.reasons == (code,), info.value.reasons
    return info.value


def _race_threads(fixture, *, epochs: tuple[str, str]):
    barrier = threading.Barrier(2)
    accepted: list[object] = []
    rejected: list[AuthorizationRejected] = []
    lock = threading.Lock()

    def worker(epoch: str) -> None:
        barrier.wait(timeout=120)
        try:
            use = fixture.consume(run_epoch=epoch)
        except AuthorizationRejected as error:
            with lock:
                rejected.append(error)
        else:
            with lock:
                accepted.append(use)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(worker, epoch) for epoch in epochs]
        for future in futures:
            future.result(timeout=180)
    return accepted, rejected


def _race_processes(fixture, *, epochs: tuple[str, str]):
    """Race two independent forked processes: separate PIDs and separate FDs."""
    context = multiprocessing.get_context("fork")
    barrier = context.Barrier(2)
    queue = context.Queue()
    load_kwargs = fixture.load_kwargs()

    def worker(epoch: str) -> None:
        try:
            barrier.wait(timeout=300)
            use = consume_execution_authorization(
                use_log_dir=fixture.use_log, run_epoch=epoch, **load_kwargs)
        except AuthorizationRejected as error:
            queue.put(("rejected", error.reasons))
        except BaseException as error:  # noqa: BLE001 - report child failures
            queue.put(("error", type(error).__name__))
        else:
            queue.put(("accepted", use.authorization_id))

    processes = [context.Process(target=worker, args=(epoch,)) for epoch in epochs]
    for process in processes:
        process.start()
    try:
        results = [queue.get(timeout=600) for _ in processes]
    finally:
        for process in processes:
            process.join(timeout=120)
        queue.close()
        queue.join_thread()
    assert [process.exitcode for process in processes] == [0, 0]
    return results


class _InjectedCrash(BaseException):
    """Stands in for the publisher process dying at a chosen instruction point."""


def _inject_crash(monkeypatch: pytest.MonkeyPatch, seam: str) -> None:
    def crash(*args, **kwargs):
        raise _InjectedCrash(seam)

    monkeypatch.setattr(authorization_module, seam, crash)


# ---------------------------------------------------------------------------
# R1-01: two threads with a barrier, >= 200 rounds: exactly one success + replay
# ---------------------------------------------------------------------------
def test_r1_01_two_thread_barrier_rounds_exactly_one_success(trusted) -> None:
    assert THREAD_ROUNDS >= 200, "R1-01 requires >= 200 rounds"
    accepted_count = 0
    replay_count = 0
    for index in range(THREAD_ROUNDS):
        authorization_id = _round_authorization(
            trusted, prefix="auth-r1-01", index=index)
        accepted, rejected = _race_threads(trusted, epochs=(RUN_EPOCH, RUN_EPOCH))
        assert len(accepted) == 1, (index, [error.reasons for error in rejected])
        assert len(rejected) == 1, (index, len(accepted))
        assert rejected[0].reasons == ("AUTHORIZATION_REPLAYED",), (
            index, rejected[0].reasons)
        assert accepted[0].authorization_id == authorization_id
        assert accepted[0].run_epoch == RUN_EPOCH
        record = _record_path_for(trusted, authorization_id)
        assert record.is_file()
        parsed = json.loads(record.read_text(encoding="utf-8"))
        assert parsed == {"schema": "at-m0/authorization-use/v1",
                          "authorization_id": authorization_id,
                          "run_epoch": RUN_EPOCH,
                          "consumed_utc": "2026-11-18T12:00:00Z"}
        assert (record.stat().st_mode & 0o777) == 0o600
        accepted_count += 1
        replay_count += 1
    assert accepted_count == THREAD_ROUNDS
    assert replay_count == THREAD_ROUNDS
    assert _final_names(trusted) == sorted(
        _record_path_for(trusted, f"auth-r1-01-{index}").name
        for index in range(THREAD_ROUNDS))
    assert _temp_names(trusted) == []


# ---------------------------------------------------------------------------
# R1-02: two independent processes, >= 50 rounds: exactly one success + replay
# ---------------------------------------------------------------------------
def test_r1_02_two_process_rounds_exactly_one_success(trusted) -> None:
    if not hasattr(os, "fork"):  # pragma: no cover - POSIX only
        pytest.skip("fork start method is unavailable")
    assert PROCESS_ROUNDS >= 50, "R1-02 requires >= 50 rounds"
    for index in range(PROCESS_ROUNDS):
        authorization_id = _round_authorization(
            trusted, prefix="auth-r1-02", index=index)
        results = _race_processes(trusted, epochs=(RUN_EPOCH, RUN_EPOCH))
        kinds = sorted(result[0] for result in results)
        assert kinds == ["accepted", "rejected"], (index, results)
        accepted = [result for result in results if result[0] == "accepted"]
        rejected = [result for result in results if result[0] == "rejected"]
        assert accepted[0][1] == authorization_id
        assert rejected[0][1] == ("AUTHORIZATION_REPLAYED",), (index, rejected)
        record = _record_path_for(trusted, authorization_id)
        assert record.is_file()
        assert json.loads(record.read_text(encoding="utf-8"))["run_epoch"] == RUN_EPOCH
        assert len(_final_names(trusted)) == index + 1
    assert _temp_names(trusted) == []


# ---------------------------------------------------------------------------
# R1-03: cross-epoch racing consumers: one success, loser EPOCH_MISMATCH
# ---------------------------------------------------------------------------
def test_r1_03_cross_epoch_race_loser_is_epoch_mismatch(trusted) -> None:
    for index in range(CROSS_EPOCH_ROUNDS):
        authorization_id = _round_authorization(
            trusted, prefix="auth-r1-03", index=index)
        epochs = ("epoch-r1-03-a", "epoch-r1-03-b")
        accepted, rejected = _race_threads(trusted, epochs=epochs)
        assert len(accepted) == 1, (index, [error.reasons for error in rejected])
        assert len(rejected) == 1, (index, len(accepted))
        assert rejected[0].reasons == ("AUTHORIZATION_EPOCH_MISMATCH",), (
            index, rejected[0].reasons)
        winner = accepted[0]
        assert winner.run_epoch in epochs
        assert winner.authorization_id == authorization_id
        record = _record_path_for(trusted, authorization_id)
        assert json.loads(record.read_text(encoding="utf-8"))["run_epoch"] == winner.run_epoch


# ---------------------------------------------------------------------------
# R1-04: a persisted corrupt/zero-byte final is INVALID, never REPLAYED
# ---------------------------------------------------------------------------
_CORRUPT_FINALS = [
    pytest.param(b"", id="zero-byte"),
    pytest.param(b"not json", id="bad-json"),
    pytest.param(b"{}", id="empty-object"),
    pytest.param(b"[]", id="json-array"),
    pytest.param(b'{"schema":"at-m0/authorization-use/v1"}', id="missing-fields"),
    pytest.param(b'{"schema":"other/v1","authorization_id":"auth-g4a-synthetic-1",'
                 b'"run_epoch":"epoch-g4a-1","consumed_utc":"x"}', id="wrong-schema"),
]


@pytest.mark.parametrize("content", _CORRUPT_FINALS)
def test_r1_04_persisted_corrupt_final_is_invalid_not_replay(trusted,
                                                             content: bytes) -> None:
    record = _record_path_for(trusted, AUTH_ID)
    record.write_bytes(content)
    _expect_rejected(trusted.consume, "AUTHORIZATION_USE_RECORD_INVALID")
    # Repeatedly corrupt must stay INVALID (persistent, not a transient race).
    _expect_rejected(trusted.consume, "AUTHORIZATION_USE_RECORD_INVALID")
    # No new use record was published over/next to the corrupt final.
    assert _final_names(trusted) == [record.name]
    assert _temp_names(trusted) == []


def test_r1_04_consume_has_no_reserve_claim_or_broker_path() -> None:
    """The consumption module cannot Reserve/Claim/send: no such call exists."""
    source = Path(authorization_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    forbidden_modules = ("autoteacher_m0.accounting", "autoteacher_m0.bridge",
                         "socket", "subprocess", "http", "urllib", "requests")
    assert not [name for name in imported
                if any(name == module or name.startswith(module + ".")
                       for module in forbidden_modules)], imported
    forbidden_calls = {"reserve", "claim", "settle", "release", "dispatch", "send",
                       "send_request", "connect"}
    called: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            called.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            called.add(node.func.attr)
    assert not (called & forbidden_calls), called & forbidden_calls


# ---------------------------------------------------------------------------
# R1-05: crash injection before write / after fsync before link / after link
# before directory fsync: restart never double-authorizes, failed call is never
# reported as consumed and never lets a dispatch proceed.
# ---------------------------------------------------------------------------
def test_r1_05_crash_before_write_restart_consumes_exactly_once(trusted,
                                                                monkeypatch) -> None:
    with monkeypatch.context() as patch:
        _inject_crash(patch, "_open_use_record_temp")
        with pytest.raises(_InjectedCrash):
            trusted.consume()
    assert _final_names(trusted) == []
    assert _temp_names(trusted) == []
    use = trusted.consume()
    assert use.authorization_id == AUTH_ID
    _expect_rejected(trusted.consume, "AUTHORIZATION_REPLAYED")
    assert _final_names(trusted) == [_record_path_for(trusted, AUTH_ID).name]


def test_r1_05_crash_after_fsync_before_link_restart_consumes_once(trusted,
                                                                   monkeypatch) -> None:
    with monkeypatch.context() as patch:
        _inject_crash(patch, "_link_use_record_no_replace")
        with pytest.raises(_InjectedCrash):
            trusted.consume()
    assert _final_names(trusted) == []
    temps = _temp_names(trusted)
    assert len(temps) == 1
    # The residue is a complete, fsynced temporary body, never a final name.
    staged = json.loads((trusted.use_log / temps[0]).read_text(encoding="utf-8"))
    assert staged["authorization_id"] == AUTH_ID
    assert staged["run_epoch"] == RUN_EPOCH
    use = trusted.consume()
    assert use.authorization_id == AUTH_ID
    _expect_rejected(trusted.consume, "AUTHORIZATION_REPLAYED")
    # One published final, one orphan temp residue; the temp is not capacity.
    assert len(_final_names(trusted)) == 1
    assert len(_temp_names(trusted)) == 1
    assert authorization_module._count_use_log_entries(trusted.use_log) == (1, 1)


def test_r1_05_crash_after_link_before_dir_fsync_never_double_authorizes(
        trusted, monkeypatch) -> None:
    with monkeypatch.context() as patch:
        _inject_crash(patch, "_fsync_directory")
        with pytest.raises(_InjectedCrash):
            trusted.consume()
    record = _record_path_for(trusted, AUTH_ID)
    # The atomic link already published a complete final: the use is spent.
    assert record.is_file()
    parsed = json.loads(record.read_text(encoding="utf-8"))
    assert parsed == {"schema": "at-m0/authorization-use/v1",
                      "authorization_id": AUTH_ID, "run_epoch": RUN_EPOCH,
                      "consumed_utc": "2026-11-18T12:00:00Z"}
    # Restart: replay classification, never a second success.
    _expect_rejected(trusted.consume, "AUTHORIZATION_REPLAYED")
    assert len(_final_names(trusted)) == 1
    assert len(_temp_names(trusted)) == 1  # unresolved residue, not a record


def test_r1_05_dir_fsync_failure_is_fail_closed_not_success(trusted,
                                                            monkeypatch) -> None:
    def failing_fsync(directory: Path) -> None:
        raise OSError(errno.EIO, "injected directory fsync failure")

    with monkeypatch.context() as patch:
        patch.setattr(authorization_module, "_fsync_directory", failing_fsync)
        _expect_rejected(trusted.consume, "AUTHORIZATION_USE_LOG_DURABILITY_UNKNOWN")
    # Durability is unknown / the use is spent: the final stays and a restart
    # observes a complete record instead of authorizing a second time.
    record = _record_path_for(trusted, AUTH_ID)
    assert record.is_file()
    _expect_rejected(trusted.consume, "AUTHORIZATION_REPLAYED")
    assert len(_final_names(trusted)) == 1


def _hard_crash_worker(use_log: Path, load_kwargs: dict, seam: str) -> None:
    """Die in a forked child without any cleanup: a real crash, not an exception."""

    def die(*args, **kwargs):
        os._exit(23)

    setattr(authorization_module, seam, die)
    consume_execution_authorization(use_log_dir=use_log, run_epoch=RUN_EPOCH,
                                    **load_kwargs)
    os._exit(24)  # pragma: no cover - the injected seam must terminate first


def _hard_crash_at(trusted, seam: str) -> None:
    context = multiprocessing.get_context("fork")
    process = context.Process(target=_hard_crash_worker,
                              args=(trusted.use_log, trusted.load_kwargs(), seam))
    process.start()
    process.join(timeout=300)
    assert process.exitcode == 23, process.exitcode


@pytest.mark.parametrize("seam", [
    pytest.param("_open_use_record_temp", id="before-write"),
    pytest.param("_link_use_record_no_replace", id="after-fsync-before-link"),
    pytest.param("_fsync_directory", id="after-link-before-dir-fsync"),
])
def test_r1_05_hard_process_death_each_stage_never_double_authorizes(
        trusted, seam: str) -> None:
    """os._exit() at each stage: no Python cleanup runs, then a restart recovers."""
    if not hasattr(os, "fork"):  # pragma: no cover - POSIX only
        pytest.skip("fork start method is unavailable")
    _hard_crash_at(trusted, seam)
    record = _record_path_for(trusted, AUTH_ID)
    if seam == "_fsync_directory":
        # The publish already happened: the use is spent and the record is complete.
        assert record.is_file()
        parsed = json.loads(record.read_text(encoding="utf-8"))
        assert parsed["authorization_id"] == AUTH_ID
        _expect_rejected(trusted.consume, "AUTHORIZATION_REPLAYED")
    else:
        # Nothing was published: the restart consumes exactly once.
        assert not record.exists()
        use = trusted.consume()
        assert use.authorization_id == AUTH_ID
        _expect_rejected(trusted.consume, "AUTHORIZATION_REPLAYED")
    assert len(_final_names(trusted)) == 1


# ---------------------------------------------------------------------------
# R1-06: unsupported link, cross-device, permission, symlink, hardlink anomaly
# and directory fsync failure all fail closed (no direct-final-write fallback)
# ---------------------------------------------------------------------------
def _fake_link(failure: BaseException):
    def link(source, destination, *, follow_symlinks=True):
        raise failure

    return link


@pytest.mark.parametrize("failure", [
    pytest.param(OSError(errno.EOPNOTSUPP, "link unsupported"), id="link-unsupported"),
    pytest.param(OSError(errno.ENOSYS, "link not implemented"), id="link-enosys"),
    pytest.param(OSError(errno.EXDEV, "cross-device link"), id="cross-device"),
    pytest.param(OSError(errno.EACCES, "permission denied"), id="permission-denied"),
])
def test_r1_06_unusable_link_fails_closed_without_fallback(trusted, monkeypatch,
                                                           failure: BaseException) -> None:
    with monkeypatch.context() as patch:
        patch.setattr(authorization_module.os, "link", _fake_link(failure))
        _expect_rejected(trusted.consume, "AUTHORIZATION_USE_LOG_WRITE_FAILED")
    # Fail closed: no final was created by a fallback direct write and no temp
    # was left in a state that could be mistaken for a record.
    assert _final_names(trusted) == []
    assert _temp_names(trusted) == []
    # The same fixture can still consume once when link works again.
    use = trusted.consume()
    assert use.authorization_id == AUTH_ID
    _expect_rejected(trusted.consume, "AUTHORIZATION_REPLAYED")


def test_r1_06_link_notimplemented_fails_closed(trusted, monkeypatch) -> None:
    with monkeypatch.context() as patch:
        patch.setattr(authorization_module.os, "link",
                      _fake_link(NotImplementedError("follow_symlinks unsupported")))
        _expect_rejected(trusted.consume, "AUTHORIZATION_USE_LOG_WRITE_FAILED")
    assert _final_names(trusted) == []


def test_r1_06_permission_denied_on_temp_creation_fails_closed(trusted,
                                                               monkeypatch) -> None:
    def denied(temporary: Path) -> int:
        raise PermissionError(errno.EACCES, "injected permission denial")

    with monkeypatch.context() as patch:
        patch.setattr(authorization_module, "_open_use_record_temp", denied)
        _expect_rejected(trusted.consume, "AUTHORIZATION_USE_LOG_WRITE_FAILED")
    assert _final_names(trusted) == []
    assert _temp_names(trusted) == []


def test_r1_06_symlinked_final_fails_closed(trusted, tmp_path) -> None:
    record = _record_path_for(trusted, AUTH_ID)
    target = tmp_path / "elsewhere.json"
    target.write_text("not a use record", encoding="utf-8")
    record.symlink_to(target)
    _expect_rejected(trusted.consume, "AUTHORIZATION_USE_RECORD_INVALID")
    assert record.is_symlink()
    assert target.read_text(encoding="utf-8") == "not a use record"


def test_r1_06_hardlink_anomaly_fails_closed(trusted) -> None:
    record = _record_path_for(trusted, AUTH_ID)
    body = json.dumps({"schema": "at-m0/authorization-use/v1",
                       "authorization_id": AUTH_ID, "run_epoch": RUN_EPOCH,
                       "consumed_utc": "2026-11-18T12:00:00Z"}).encode()
    staged = trusted.use_log / "staged.json"
    staged.write_bytes(body)
    os.link(staged, record)
    os.link(staged, trusted.use_log / "third-alias.json")
    assert record.stat().st_nlink == 3
    _expect_rejected(trusted.consume, "AUTHORIZATION_USE_RECORD_INVALID")


def test_r1_06_directory_fsync_failure_fails_closed(trusted, monkeypatch) -> None:
    def failing_fsync(directory: Path) -> None:
        raise OSError(errno.EIO, "injected directory fsync failure")

    with monkeypatch.context() as patch:
        patch.setattr(authorization_module, "_fsync_directory", failing_fsync)
        _expect_rejected(trusted.consume, "AUTHORIZATION_USE_LOG_DURABILITY_UNKNOWN")
    assert _final_names(trusted) == [_record_path_for(trusted, AUTH_ID).name]
    _expect_rejected(trusted.consume, "AUTHORIZATION_REPLAYED")
