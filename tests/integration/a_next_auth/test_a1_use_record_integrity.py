"""A-NEXT A1 / P2-01: use-record body ``authorization_id`` integrity.

Before this change ``_read_use_record`` validated the record schema and
``run_epoch`` only. A schema-valid record whose body ``authorization_id`` was
another authorization (or not the one the caller verified) was classified as a
real ``AUTHORIZATION_REPLAYED``: conservative for admission, but an audit lie
and an unvalidated data-integrity gap (G4-R P2-01).

The tests below pin the new contract:

* body ``authorization_id`` must be a valid identifier (same ``_IDENTIFIER``
  rule as the signed authorization), must hash to the record file name
  (``sha256(id) + ".json"``), and must equal the expected authorization id the
  caller verified;
* any mismatch is a *stable* ``AUTHORIZATION_USE_RECORD_INVALID`` and is never
  reported as a replay/epoch classification;
* path/file-type/permission checks, ``O_NOFOLLOW``, ``nlink`` and directory
  ``fsync`` stay fail-closed, with no fallback to writing the final name
  directly;
* concurrency (2/10/50 threads) and crash windows (before link / after link
  before directory fsync / before write) keep exactly one success and never a
  second consumption -- this module has no Broker/Fake path at all.

Three outcome states are distinguished in the assertions and the report:

* ``REJECTED_NO_CONSUMPTION`` -- rejected, no use record published by us;
* ``CONSUMED_DURABILITY_UNKNOWN`` -- final visible, use spent, no success
  returned (``AUTHORIZATION_USE_LOG_DURABILITY_UNKNOWN``);
* ``NO_CONSUMPTION`` -- nothing published, a restart may consume exactly once.

All fixtures are synthetic (``TEST_ONLY_`` Ed25519 seed, pytest temporary
directory); no key, model, provider or external socket is used.
"""
from __future__ import annotations

import ast
import copy
from concurrent.futures import ThreadPoolExecutor
import errno
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

AUTH_ID = "auth-g4a-synthetic-1"
USE_SCHEMA = "at-m0/authorization-use/v1"
CONSUMED_UTC = "2026-11-18T12:00:00Z"
TEMP_PREFIX = authorization_module._USE_RECORD_TEMP_PREFIX
DURABILITY_UNKNOWN = "AUTHORIZATION_USE_LOG_DURABILITY_UNKNOWN"

_UNSET = object()
# pytest marks for behaviour that the current baseline does not implement yet;
# the implementation commit removes these markers (reviewable in the diff).
PENDING_A1 = pytest.mark.xfail(
    strict=True,
    reason="A-NEXT A1/P2-01: body authorization_id cross-check not implemented yet")


# ---------------------------------------------------------------------------
# synthetic fixture helpers
# ---------------------------------------------------------------------------
def _record_path_for(fixture, authorization_id: str) -> Path:
    return fixture.record_path(authorization_id)


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


def _round_authorization(fixture, *, prefix: str, index: int) -> str:
    payload = copy.deepcopy(base_payload(fixture.bindings.as_dict()))
    payload["authorization_id"] = f"{prefix}-{index}"
    fixture.write_signed(payload)
    return payload["authorization_id"]


def _write_use_record(fixture, record_authorization_id: str, *,
                      body_authorization_id=_UNSET,
                      run_epoch: str = RUN_EPOCH,
                      consumed_utc: str = CONSUMED_UTC,
                      extra: dict | None = None) -> Path:
    body: dict = {
        "schema": USE_SCHEMA,
        "authorization_id": (record_authorization_id
                             if body_authorization_id is _UNSET
                             else body_authorization_id),
        "run_epoch": run_epoch,
        "consumed_utc": consumed_utc,
    }
    if extra is not None:
        body.update(extra)
    path = _record_path_for(fixture, record_authorization_id)
    path.write_text(json.dumps(body), encoding="utf-8")
    return path


def _write_raw_record(fixture, record_authorization_id: str, raw: bytes) -> Path:
    path = _record_path_for(fixture, record_authorization_id)
    path.write_bytes(raw)
    return path


def _signed_authorization(fixture, authorization_id: str) -> None:
    payload = copy.deepcopy(base_payload(fixture.bindings.as_dict()))
    payload["authorization_id"] = authorization_id
    fixture.write_signed(payload)


def _race_threads(fixture, threads: int, *, epochs: tuple[str, ...]):
    barrier = threading.Barrier(threads)
    accepted: list[object] = []
    rejected: list[AuthorizationRejected] = []
    lock = threading.Lock()

    def worker(epoch: str) -> None:
        barrier.wait(timeout=180)
        try:
            use = fixture.consume(run_epoch=epoch)
        except AuthorizationRejected as error:
            with lock:
                rejected.append(error)
        else:
            with lock:
                accepted.append(use)

    with ThreadPoolExecutor(max_workers=threads) as pool:
        futures = [pool.submit(worker, epoch) for epoch in epochs]
        for future in futures:
            future.result(timeout=600)
    return accepted, rejected


def _fork_consume(trusted, *, timeout: float = 30.0) -> tuple[str, tuple]:
    """Run one consume in a forked child so a FIFO/blocking read cannot hang pytest."""
    result_file = trusted.root / "a1-child-result.json"
    context = multiprocessing.get_context("fork")
    load_kwargs = trusted.load_kwargs()

    def worker() -> None:
        try:
            use = consume_execution_authorization(
                use_log_dir=trusted.use_log, run_epoch=RUN_EPOCH, **load_kwargs)
        except AuthorizationRejected as error:
            outcome = ["rejected", list(error.reasons)]
        except BaseException as error:  # noqa: BLE001 - report child failures
            outcome = ["error", [type(error).__name__]]
        else:
            outcome = ["accepted", [use.authorization_id]]
        result_file.write_text(json.dumps(outcome), encoding="utf-8")
        os._exit(0)

    process = context.Process(target=worker)
    process.start()
    process.join(timeout)
    if process.is_alive():
        process.terminate()
        process.join(30)
        return "hung", ()
    if process.exitcode != 0:
        return "error", (f"child-exit-{process.exitcode}",)
    if not result_file.exists():
        return "no-result", ()
    kind, detail = json.loads(result_file.read_text(encoding="utf-8"))
    return kind, tuple(detail)


class _InjectedCrash(BaseException):
    """Stands in for the publisher process dying at a chosen instruction point."""


def _hard_crash_at(trusted, seam: str) -> int:
    """Kill a forked child at ``seam`` with os._exit: a real crash, no cleanup."""
    context = multiprocessing.get_context("fork")
    load_kwargs = trusted.load_kwargs()

    def worker() -> None:
        def die(*args, **kwargs):
            os._exit(23)

        setattr(authorization_module, seam, die)
        consume_execution_authorization(use_log_dir=trusted.use_log,
                                        run_epoch=RUN_EPOCH, **load_kwargs)
        os._exit(24)  # pragma: no cover - the injected seam must terminate first

    process = context.Process(target=worker)
    process.start()
    process.join(timeout=300)
    if process.is_alive():  # pragma: no cover - defensive
        process.terminate()
        process.join(30)
    return process.exitcode


def _inject_crash(monkeypatch: pytest.MonkeyPatch, seam: str) -> None:
    def crash(*args, **kwargs):
        raise _InjectedCrash(seam)

    monkeypatch.setattr(authorization_module, seam, crash)


# ---------------------------------------------------------------------------
# valid replays stay real replays (same and cross epoch)
# ---------------------------------------------------------------------------
def test_a1_01_valid_replay_same_epoch(trusted) -> None:
    first = trusted.consume()
    record = first.record_path
    before = record.read_bytes()
    _expect_rejected(trusted.consume, "AUTHORIZATION_REPLAYED")
    assert record.read_bytes() == before
    assert _final_names(trusted) == [record.name]
    assert _temp_names(trusted) == []


def test_a1_01_valid_replay_different_epoch(trusted) -> None:
    trusted.consume()
    _expect_rejected(lambda: trusted.consume(run_epoch="epoch-a1-other"),
                     "AUTHORIZATION_EPOCH_MISMATCH")
    assert len(_final_names(trusted)) == 1


# ---------------------------------------------------------------------------
# body authorization_id vs record path / expected authorization id
# ---------------------------------------------------------------------------
@PENDING_A1
def test_a1_01_body_id_a_in_record_file_of_b_is_invalid_not_replay(trusted) -> None:
    """The Reviewer P2-01 probe: a schema-valid record for A stored under B."""
    id_a = "auth-a1-body-a"
    id_b = "auth-a1-body-b"
    _signed_authorization(trusted, id_b)
    _write_use_record(trusted, id_b, body_authorization_id=id_a, run_epoch=RUN_EPOCH)
    error = _expect_rejected(trusted.consume, "AUTHORIZATION_USE_RECORD_INVALID")
    assert "AUTHORIZATION_REPLAYED" not in error.reasons
    assert "AUTHORIZATION_EPOCH_MISMATCH" not in error.reasons
    # The foreign record is not rewritten and no second record appears.
    assert _final_names(trusted) == [_record_path_for(trusted, id_b).name]
    assert _temp_names(trusted) == []


@PENDING_A1
def test_a1_01_foreign_body_id_under_matching_path_is_invalid(trusted) -> None:
    _write_use_record(trusted, AUTH_ID, body_authorization_id="auth-a1-other-id",
                      run_epoch=RUN_EPOCH)
    error = _expect_rejected(trusted.consume, "AUTHORIZATION_USE_RECORD_INVALID")
    assert "AUTHORIZATION_REPLAYED" not in error.reasons
    assert _temp_names(trusted) == []


@PENDING_A1
def test_a1_01_reader_rejects_expected_id_mismatch(trusted) -> None:
    """Unit level: path body matches, but the caller expected another id."""
    id_a = "auth-a1-reader-a"
    id_b = "auth-a1-reader-b"
    path = _write_use_record(trusted, id_a, body_authorization_id=id_a)
    with pytest.raises(AuthorizationRejected) as info:
        authorization_module._read_use_record(
            path, expected_authorization_id=id_b)
    assert info.value.reasons == ("AUTHORIZATION_USE_RECORD_INVALID",)
    assert authorization_module._read_use_record(
        path, expected_authorization_id=id_a) == (id_a, RUN_EPOCH)


@PENDING_A1
@pytest.mark.parametrize("bad_id", [
    pytest.param(None, id="null"),
    pytest.param(True, id="bool"),
    pytest.param(123, id="int"),
    pytest.param([], id="list"),
    pytest.param({}, id="object"),
    pytest.param("", id="empty"),
    pytest.param("bad id", id="space"),
    pytest.param("x" * 129, id="too-long"),
    pytest.param("授权", id="non-ascii"),
    pytest.param("auth-a1\n", id="newline"),
])
def test_a1_01_body_id_format_invalid_is_invalid(trusted, bad_id) -> None:
    _write_use_record(trusted, AUTH_ID, body_authorization_id=bad_id)
    _expect_rejected(trusted.consume, "AUTHORIZATION_USE_RECORD_INVALID")


@PENDING_A1
def test_a1_01_body_consumed_utc_invalid_is_invalid(trusted) -> None:
    """Writing side always emits one fixed UTC form; anything else is corrupt."""
    _write_use_record(trusted, AUTH_ID, consumed_utc="not-a-utc-timestamp")
    _expect_rejected(trusted.consume, "AUTHORIZATION_USE_RECORD_INVALID")


# ---------------------------------------------------------------------------
# corrupt / truncated / duplicate-key / illegal-schema records stay INVALID
# ---------------------------------------------------------------------------
_CORRUPT_RECORDS = [
    pytest.param(b"", id="zero-byte"),
    pytest.param(b"not json", id="not-json"),
    pytest.param(b"[]", id="json-array"),
    pytest.param(b"\xff\xfe\x00", id="invalid-utf8"),
    pytest.param(b'{"schema":"at-m0/authorization-use/v1","authorization_id":'
                 b'"auth-g4a-synthetic-1","run_epoch":"epoch-g4a-1"', id="truncated"),
    pytest.param(b'{"schema":"at-m0/authorization-use/v1","authorization_id":'
                 b'"auth-g4a-synthetic-1","run_epoch":"epoch-g4a-1",'
                 b'"consumed_utc":"2026-11-18T12:00:00Z","extra":1}', id="extra-key"),
    pytest.param(b'{"schema":"other/v1","authorization_id":"auth-g4a-synthetic-1",'
                 b'"run_epoch":"epoch-g4a-1","consumed_utc":"2026-11-18T12:00:00Z"}',
                 id="wrong-schema"),
    pytest.param(b'{"schema":"at-m0/authorization-use/v1","authorization_id":'
                 b'"auth-g4a-synthetic-1","run_epoch":"epoch-g4a-1",'
                 b'"consumed_utc":NaN}', id="nan-field"),
    pytest.param(b'{"schema":"at-m0/authorization-use/v1","authorization_id":'
                 b'"auth-g4a-synthetic-1","authorization_id":"auth-other",'
                 b'"run_epoch":"epoch-g4a-1","consumed_utc":"2026-11-18T12:00:00Z"}',
                 id="duplicate-key"),
]


@pytest.mark.parametrize("raw", _CORRUPT_RECORDS)
def test_a1_01_corrupt_record_is_invalid_not_replay(trusted, raw: bytes) -> None:
    path = _write_raw_record(trusted, AUTH_ID, raw)
    error = _expect_rejected(trusted.consume, "AUTHORIZATION_USE_RECORD_INVALID")
    assert "AUTHORIZATION_REPLAYED" not in error.reasons
    assert path.read_bytes() == raw
    assert _final_names(trusted) == [path.name]
    assert _temp_names(trusted) == []


# ---------------------------------------------------------------------------
# node-type anomalies: symlink, hardlink, FIFO
# ---------------------------------------------------------------------------
def test_a1_01_symlinked_record_is_invalid(trusted, tmp_path) -> None:
    target = tmp_path / "elsewhere.json"
    target.write_bytes(b"{}")
    record = _record_path_for(trusted, AUTH_ID)
    record.symlink_to(target)
    _expect_rejected(trusted.consume, "AUTHORIZATION_USE_RECORD_INVALID")
    assert record.is_symlink() and target.read_bytes() == b"{}"


def test_a1_01_hardlinked_record_anomaly_is_invalid(trusted) -> None:
    record = _record_path_for(trusted, AUTH_ID)
    staged = trusted.use_log / "staged.json"
    staged.write_text(json.dumps({"schema": USE_SCHEMA,
                                  "authorization_id": AUTH_ID,
                                  "run_epoch": RUN_EPOCH,
                                  "consumed_utc": CONSUMED_UTC}), encoding="utf-8")
    os.link(staged, record)
    os.link(staged, trusted.use_log / "third-alias.json")
    assert record.stat().st_nlink == 3
    _expect_rejected(trusted.consume, "AUTHORIZATION_USE_RECORD_INVALID")


def test_a1_01_single_crash_residue_hardlink_is_tolerated_as_replay(trusted) -> None:
    """nlink == 2 is the documented crash residue (final + uncollected temp)."""
    record = _record_path_for(trusted, AUTH_ID)
    staged = trusted.use_log / "residue.json"
    staged.write_text(json.dumps({"schema": USE_SCHEMA,
                                  "authorization_id": AUTH_ID,
                                  "run_epoch": RUN_EPOCH,
                                  "consumed_utc": CONSUMED_UTC}), encoding="utf-8")
    os.link(staged, record)
    assert record.stat().st_nlink == 2
    _expect_rejected(trusted.consume, "AUTHORIZATION_REPLAYED")


@PENDING_A1
def test_a1_01_fifo_record_rejected_without_blocking(trusted) -> None:
    """A FIFO must be rejected as INVALID, never opened blocking forever."""
    record = _record_path_for(trusted, AUTH_ID)
    os.mkfifo(record, 0o600)
    kind, detail = _fork_consume(trusted, timeout=20)
    assert kind == "rejected", (kind, detail)
    assert detail == ("AUTHORIZATION_USE_RECORD_INVALID",), detail


# ---------------------------------------------------------------------------
# concurrency: 2 / 10 / 50 threads, exactly one success, stable replay losers
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("threads,rounds", [
    pytest.param(2, 10, id="two-threads"),
    pytest.param(10, 3, id="ten-threads"),
    pytest.param(50, 1, id="fifty-threads"),
])
def test_a1_02_concurrent_consume_admits_exactly_one(trusted, threads: int,
                                                     rounds: int) -> None:
    for index in range(rounds):
        authorization_id = _round_authorization(
            trusted, prefix=f"auth-a1-conc-{threads}", index=index)
        accepted, rejected = _race_threads(
            trusted, threads, epochs=(RUN_EPOCH,) * threads)
        assert len(accepted) == 1, (threads, index, [e.reasons for e in rejected])
        assert len(rejected) == threads - 1, (threads, index, len(accepted))
        for error in rejected:
            assert error.reasons == ("AUTHORIZATION_REPLAYED",), (
                threads, index, error.reasons)
        assert accepted[0].authorization_id == authorization_id
        record = _record_path_for(trusted, authorization_id)
        assert json.loads(record.read_text(encoding="utf-8"))["authorization_id"] == \
            authorization_id
        assert _temp_names(trusted) == []
    assert len(_final_names(trusted)) == rounds


def test_a1_02_consumption_module_has_no_broker_or_fake_path() -> None:
    """No second Reserve/Fake is possible: the module has no such call at all."""
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
                       "fake", "connect"}
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
# crash windows: before write / before link / after link before directory fsync
# ---------------------------------------------------------------------------
def test_a1_02_crash_before_write_has_no_consumption(trusted, monkeypatch) -> None:
    with monkeypatch.context() as patch:
        _inject_crash(patch, "_open_use_record_temp")
        with pytest.raises(_InjectedCrash):
            trusted.consume()
    assert _final_names(trusted) == []
    assert _temp_names(trusted) == []
    first = trusted.consume()
    assert first.authorization_id == AUTH_ID
    _expect_rejected(trusted.consume, "AUTHORIZATION_REPLAYED")
    assert len(_final_names(trusted)) == 1


def test_a1_02_crash_before_link_restart_consumes_once(trusted, monkeypatch) -> None:
    with monkeypatch.context() as patch:
        _inject_crash(patch, "_link_use_record_no_replace")
        with pytest.raises(_InjectedCrash):
            trusted.consume()
    # No final: nothing was consumed yet (NO_CONSUMPTION state).
    assert _final_names(trusted) == []
    assert len(_temp_names(trusted)) == 1
    first = trusted.consume()
    assert first.authorization_id == AUTH_ID
    _expect_rejected(trusted.consume, "AUTHORIZATION_REPLAYED")
    assert len(_final_names(trusted)) == 1


def test_a1_02_crash_after_link_before_dir_fsync_is_consumed_unknown(
        trusted, monkeypatch) -> None:
    with monkeypatch.context() as patch:
        _inject_crash(patch, "_fsync_directory")
        with pytest.raises(_InjectedCrash):
            trusted.consume()
    # The atomic link published a complete final: the use is spent and the
    # failed call never returned success (no dispatch could follow it).
    record = _record_path_for(trusted, AUTH_ID)
    assert record.is_file()
    assert json.loads(record.read_text(encoding="utf-8")) == {
        "schema": USE_SCHEMA, "authorization_id": AUTH_ID,
        "run_epoch": RUN_EPOCH, "consumed_utc": CONSUMED_UTC}
    _expect_rejected(trusted.consume, "AUTHORIZATION_REPLAYED")
    assert len(_final_names(trusted)) == 1


def test_a1_02_hard_process_death_in_crash_windows(trusted) -> None:
    """os._exit at each window: no Python cleanup runs, restart stays correct."""
    for seam, final_expected in (
            ("_open_use_record_temp", False),
            ("_link_use_record_no_replace", False),
            ("_fsync_directory", True)):
        fixture = trusted
        exitcode = _hard_crash_at(fixture, seam)
        assert exitcode == 23, (seam, exitcode)
        record = _record_path_for(fixture, AUTH_ID)
        assert record.exists() is final_expected, (seam, record.exists())
        if final_expected:
            _expect_rejected(fixture.consume, "AUTHORIZATION_REPLAYED")
        else:
            use = fixture.consume()
            assert use.authorization_id == AUTH_ID
            _expect_rejected(fixture.consume, "AUTHORIZATION_REPLAYED")
        assert len(_final_names(fixture)) == 1
        # Reset the fixture for the next seam.
        for path in fixture.use_log.iterdir():
            path.unlink()


# ---------------------------------------------------------------------------
# durability-unknown classification and link-failure fail-closed
# ---------------------------------------------------------------------------
def test_a1_02_dir_fsync_failure_is_consumed_but_durability_unknown(
        trusted, monkeypatch) -> None:
    def failing_fsync(directory: Path) -> None:
        raise OSError(errno.EIO, "injected directory fsync failure")

    with monkeypatch.context() as patch:
        patch.setattr(authorization_module, "_fsync_directory", failing_fsync)
        error = _expect_rejected(trusted.consume, DURABILITY_UNKNOWN)
    assert "AUTHORIZATION_REPLAYED" not in error.reasons
    # State 2: the file is consumed, durability is unknown; a restart is a
    # replay and must never report a second success.
    record = _record_path_for(trusted, AUTH_ID)
    assert record.is_file()
    _expect_rejected(trusted.consume, "AUTHORIZATION_REPLAYED")
    assert len(_final_names(trusted)) == 1


def test_a1_02_link_failure_fails_closed_without_direct_write_fallback(
        trusted, monkeypatch) -> None:
    def unsupported_link(source, destination, *, follow_symlinks=True):
        raise OSError(errno.EOPNOTSUPP, "injected unsupported link")

    with monkeypatch.context() as patch:
        patch.setattr(authorization_module.os, "link", unsupported_link)
        _expect_rejected(trusted.consume, "AUTHORIZATION_USE_LOG_WRITE_FAILED")
    # Nothing published, no direct-write fallback, temp cleaned: retry consumes once.
    assert _final_names(trusted) == []
    assert _temp_names(trusted) == []
    use = trusted.consume()
    assert use.authorization_id == AUTH_ID
    _expect_rejected(trusted.consume, "AUTHORIZATION_REPLAYED")
