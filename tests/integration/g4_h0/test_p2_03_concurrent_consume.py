"""G4-H0 P2-03: authorization use records are published atomically.

Background (``docs/REVIEW_G4F_INDEPENDENT.md`` P2-03, ``docs/M0_G4F_REVIEW_ERRATA.md``
§4.3): the old implementation created the use record with ``O_CREAT|O_EXCL`` and
wrote its body afterwards. A concurrent loser could observe the created-but-still
empty record and fail with ``AUTHORIZATION_USE_RECORD_INVALID`` instead of the
stable ``AUTHORIZATION_REPLAYED`` replay code (2/30 standalone reproductions).

These tests pin the new contract deterministically, without touching the frozen
``tests/integration/g4_a/test_a12_replay_epoch.py`` historical reproduction:

* exactly one consumer can publish a use record, even when both rendezvous inside
  ``os.link`` or the body write is deliberately delayed;
* a loser always reads a complete record and gets the correct replay/epoch code;
* a half-written/legacy record is retried only within a bounded window and still
  fails closed afterwards;
* a failed atomic publication never consumes the authorization;
* temporary files are private (0600, ``O_EXCL|O_NOFOLLOW|O_CLOEXEC``), never
  counted as uses, and cleaned up;
* symlinked records are never followed.

All fixtures are TEST_ONLY synthetic; no key, provider, network or model call.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import copy
import errno
import json
import os
import threading
import time
import uuid

import pytest

from autoteacher_m0.security import authorization as authorization_module
from autoteacher_m0.security.authorization import AuthorizationRejected
from g4a_support import RUN_EPOCH, base_payload

RECORD_SUFFIX = ".json"


# ---------------------------------------------------------------------------
# deterministic OS fault-injection proxies (only the authorization module's
# ``os`` binding is replaced; pytest/threading keep the real module)
# ---------------------------------------------------------------------------
class _BarrierLinkOS:
    """Rendezvous both publishers inside ``link(2)``, then let them race for real."""

    def __init__(self, barrier: threading.Barrier) -> None:
        self._barrier = barrier

    def __getattr__(self, name: str):
        return getattr(os, name)

    def link(self, source, target):
        self._barrier.wait(timeout=10)
        return os.link(source, target)


class _SlowWriteOS:
    """Delay every record-body write, widening any partial-visibility window."""

    def __init__(self, delay_seconds: float) -> None:
        self._delay = delay_seconds

    def __getattr__(self, name: str):
        return getattr(os, name)

    def write(self, descriptor: int, data: bytes) -> int:
        time.sleep(self._delay)
        return os.write(descriptor, data)


class _ShortWriteOS:
    """Force the writer loop to issue several short writes for one body."""

    def __getattr__(self, name: str):
        return getattr(os, name)

    def write(self, descriptor: int, data: bytes) -> int:
        return os.write(descriptor, data[:8])


class _FailingLinkOS:
    """Make atomic publication impossible on this filesystem."""

    def __getattr__(self, name: str):
        return getattr(os, name)

    def link(self, source, target):
        raise OSError(errno.EPERM, "link not permitted by this filesystem")


class _PrepublishedLinkOS:
    """Complete record appears from 'another consumer' before link(2) reports EEXIST."""

    def __init__(self, body: bytes) -> None:
        self._body = body

    def __getattr__(self, name: str):
        return getattr(os, name)

    def link(self, source, target):
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                             | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        try:
            written = 0
            while written < len(self._body):
                written += os.write(descriptor, self._body[written:])
        finally:
            os.close(descriptor)
        raise FileExistsError(errno.EEXIST, "record already published", str(target))


class _RecordingOpenOS:
    """Record every open flags/mode the authorization module uses."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, int, int]] = []

    def __getattr__(self, name: str):
        return getattr(os, name)

    def open(self, path, flags, mode=0o777):  # noqa: A003 - deliberate proxy
        self.calls.append((str(path), flags, mode))
        return os.open(path, flags, mode)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _set_authorization(trusted, authorization_id: str) -> str:
    payload = copy.deepcopy(base_payload(trusted.bindings.as_dict()))
    payload["authorization_id"] = authorization_id
    trusted.write_signed(payload)
    return authorization_id


def _new_authorization_id(label: str) -> str:
    return f"auth-p2-03-{label}-{uuid.uuid4().hex}"


def _use_record_body(authorization_id: str, run_epoch: str = RUN_EPOCH) -> bytes:
    return authorization_module._canonical_payload({
        "schema": authorization_module._USE_LOG_SCHEMA,
        "authorization_id": authorization_id,
        "run_epoch": run_epoch,
        "consumed_utc": "2026-11-18T12:00:00Z",
    })


def _write_record(path, body: bytes, mode: int = 0o600) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                         | os.O_NOFOLLOW | os.O_CLOEXEC, mode)
    try:
        written = 0
        while written < len(body):
            written += os.write(descriptor, body[written:])
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _temp_entries(trusted) -> list:
    prefix = authorization_module._USE_RECORD_TEMP_PREFIX
    return sorted(path for path in trusted.use_log.iterdir()
                  if path.name.startswith(prefix))


def _json_records(trusted) -> list:
    return sorted(path for path in trusted.use_log.iterdir()
                  if path.name.endswith(RECORD_SUFFIX))


def _race_consume(trusted, *, run_epoch: str = RUN_EPOCH):
    """Two threads consume the same authorization after a common start barrier."""
    barrier = threading.Barrier(2)
    guard = threading.Lock()
    results: list[object] = []
    errors: list[AuthorizationRejected] = []

    def worker() -> None:
        barrier.wait(timeout=10)
        try:
            use = trusted.consume(run_epoch=run_epoch)
        except AuthorizationRejected as error:
            with guard:
                errors.append(error)
        else:
            with guard:
                results.append(use)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(worker) for _ in range(2)]
        for future in futures:
            future.result(timeout=60)
    return results, errors


def _assert_single_winner(trusted, results, errors, *, expected_loser: str) -> None:
    assert len(results) == 1, f"expected exactly one consumer to win, got {results!r}"
    assert len(errors) == 1, f"expected exactly one rejected consumer, got {errors!r}"
    assert errors[0].reasons == (expected_loser,), errors[0].reasons
    records = _json_records(trusted)
    assert len(records) == 1, [path.name for path in records]
    assert (records[0].stat().st_mode & 0o777) == 0o600
    assert _temp_entries(trusted) == []


# ---------------------------------------------------------------------------
# atomic publication under a forced link(2) collision
# ---------------------------------------------------------------------------
def test_link_race_publishes_exactly_one_complete_record(
        trusted, monkeypatch: pytest.MonkeyPatch) -> None:
    auth_id = _set_authorization(trusted, _new_authorization_id("link-race"))
    monkeypatch.setattr(authorization_module, "os",
                        _BarrierLinkOS(threading.Barrier(2)))
    results, errors = _race_consume(trusted)
    _assert_single_winner(trusted, results, errors, expected_loser="AUTHORIZATION_REPLAYED")
    assert json.loads(results[0].record_path.read_text(encoding="utf-8")) == {
        "schema": authorization_module._USE_LOG_SCHEMA,
        "authorization_id": auth_id,
        "run_epoch": RUN_EPOCH,
        "consumed_utc": "2026-11-18T12:00:00Z",
    }


def test_slow_body_write_never_exposes_a_partial_record(
        trusted, monkeypatch: pytest.MonkeyPatch) -> None:
    """P2-03 regression shape: delayed body write must not leak an empty record."""
    auth_id = _set_authorization(trusted, _new_authorization_id("slow-write"))
    monkeypatch.setattr(authorization_module, "os", _SlowWriteOS(0.08))
    results, errors = _race_consume(trusted)
    _assert_single_winner(trusted, results, errors, expected_loser="AUTHORIZATION_REPLAYED")
    record = results[0].record_path
    payload = json.loads(record.read_text(encoding="utf-8"))
    assert payload["authorization_id"] == auth_id
    assert payload["run_epoch"] == RUN_EPOCH


def test_short_writes_are_looped_until_the_body_is_complete(
        trusted, monkeypatch: pytest.MonkeyPatch) -> None:
    auth_id = _set_authorization(trusted, _new_authorization_id("short-write"))
    monkeypatch.setattr(authorization_module, "os", _ShortWriteOS())
    use = trusted.consume()
    assert json.loads(use.record_path.read_text(encoding="utf-8")) == {
        "schema": authorization_module._USE_LOG_SCHEMA,
        "authorization_id": auth_id,
        "run_epoch": RUN_EPOCH,
        "consumed_utc": "2026-11-18T12:00:00Z",
    }
    assert _temp_entries(trusted) == []


# ---------------------------------------------------------------------------
# loser classification when another publisher wins the link
# ---------------------------------------------------------------------------
def test_link_eexist_after_another_publisher_replays(
        trusted, monkeypatch: pytest.MonkeyPatch) -> None:
    auth_id = _set_authorization(trusted, _new_authorization_id("preexisting"))
    body = _use_record_body(auth_id)
    monkeypatch.setattr(authorization_module, "os", _PrepublishedLinkOS(body))
    with pytest.raises(AuthorizationRejected) as error:
        trusted.consume()
    assert error.value.reasons == ("AUTHORIZATION_REPLAYED",)
    record = trusted.record_path(auth_id)
    assert record.read_bytes() == body
    assert _temp_entries(trusted) == []


def test_link_eexist_with_other_epoch_is_epoch_mismatch(
        trusted, monkeypatch: pytest.MonkeyPatch) -> None:
    auth_id = _set_authorization(trusted, _new_authorization_id("preexisting-epoch"))
    body = _use_record_body(auth_id, run_epoch="epoch-g4h0-other")
    monkeypatch.setattr(authorization_module, "os", _PrepublishedLinkOS(body))
    with pytest.raises(AuthorizationRejected) as error:
        trusted.consume(run_epoch=RUN_EPOCH)
    assert error.value.reasons == ("AUTHORIZATION_EPOCH_MISMATCH",)
    assert _temp_entries(trusted) == []


# ---------------------------------------------------------------------------
# fail-closed publication
# ---------------------------------------------------------------------------
def test_link_failure_fails_closed_without_consuming(
        trusted, monkeypatch: pytest.MonkeyPatch) -> None:
    auth_id = _set_authorization(trusted, _new_authorization_id("link-failure"))
    monkeypatch.setattr(authorization_module, "os", _FailingLinkOS())
    with pytest.raises(AuthorizationRejected) as error:
        trusted.consume()
    assert error.value.reasons == ("AUTHORIZATION_USE_LOG_WRITE_FAILED",)
    assert not trusted.record_path(auth_id).exists()
    assert _json_records(trusted) == []
    assert _temp_entries(trusted) == []
    # Restoring a working filesystem shows the authorization was not consumed.
    monkeypatch.setattr(authorization_module, "os", os)
    use = trusted.consume()
    assert use.authorization_id == auth_id
    assert len(_json_records(trusted)) == 1


def test_record_and_temporary_open_flags_and_mode(
        trusted, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_authorization(trusted, _new_authorization_id("flags"))
    recorder = _RecordingOpenOS()
    monkeypatch.setattr(authorization_module, "os", recorder)
    use = trusted.consume()
    assert (use.record_path.stat().st_mode & 0o777) == 0o600
    temp_prefix = authorization_module._USE_RECORD_TEMP_PREFIX
    temp_opens = [call for call in recorder.calls
                  if os.path.basename(call[0]).startswith(temp_prefix)]
    assert len(temp_opens) == 1, recorder.calls
    _, flags, mode = temp_opens[0]
    for required in (os.O_WRONLY, os.O_CREAT, os.O_EXCL, os.O_NOFOLLOW, os.O_CLOEXEC):
        assert flags & required, (flags, required)
    assert mode == 0o600
    # The final record path is created by link(2) only, never opened for writing.
    record_opens = [call for call in recorder.calls
                    if call[0] == str(use.record_path)]
    assert all(not (call[1] & os.O_WRONLY) for call in record_opens), record_opens
    assert _temp_entries(trusted) == []


# ---------------------------------------------------------------------------
# legacy / partial record read retry boundary
# ---------------------------------------------------------------------------
def test_partial_legacy_record_is_retried_then_replayed(
        trusted, monkeypatch: pytest.MonkeyPatch) -> None:
    auth_id = _set_authorization(trusted, _new_authorization_id("legacy-partial"))
    record = trusted.record_path(auth_id)
    _write_record(record, b"")
    monkeypatch.setattr(authorization_module, "_USE_RECORD_READ_ATTEMPTS", 200)
    monkeypatch.setattr(authorization_module, "_USE_RECORD_READ_DELAY_SECONDS", 0.005)
    body = _use_record_body(auth_id)
    finished = threading.Event()

    def legacy_writer() -> None:
        time.sleep(0.05)
        with open(record, "wb") as handle:  # non-atomic legacy publisher
            handle.write(body[: len(body) // 2])
            handle.flush()
            time.sleep(0.02)
            handle.write(body[len(body) // 2:])
        finished.set()

    writer = threading.Thread(target=legacy_writer, daemon=True)
    writer.start()
    try:
        with pytest.raises(AuthorizationRejected) as error:
            trusted.consume()
    finally:
        writer.join(timeout=5)
    assert error.value.reasons == ("AUTHORIZATION_REPLAYED",)
    assert finished.is_set()
    assert len(_json_records(trusted)) == 1


def test_retry_bound_stays_fail_closed_for_a_late_publisher(
        trusted, monkeypatch: pytest.MonkeyPatch) -> None:
    auth_id = _set_authorization(trusted, _new_authorization_id("late-publisher"))
    record = trusted.record_path(auth_id)
    _write_record(record, b"")
    monkeypatch.setattr(authorization_module, "_USE_RECORD_READ_ATTEMPTS", 3)
    monkeypatch.setattr(authorization_module, "_USE_RECORD_READ_DELAY_SECONDS", 0.005)
    body = _use_record_body(auth_id)
    finished = threading.Event()

    def late_writer() -> None:
        time.sleep(0.3)
        record.write_bytes(body)
        finished.set()

    writer = threading.Thread(target=late_writer, daemon=True)
    writer.start()
    try:
        started = time.monotonic()
        with pytest.raises(AuthorizationRejected) as error:
            trusted.consume()
        elapsed = time.monotonic() - started
    finally:
        writer.join(timeout=5)
    assert error.value.reasons == ("AUTHORIZATION_USE_RECORD_INVALID",)
    assert elapsed < 0.3, elapsed  # the bound, not the writer, ended the wait
    assert finished.is_set()
    # The reader denied; it did not repair/consume the authorization itself.
    assert len(_json_records(trusted)) == 1
    assert _temp_entries(trusted) == []


def test_persistent_empty_record_fails_closed(
        trusted, monkeypatch: pytest.MonkeyPatch) -> None:
    auth_id = _set_authorization(trusted, _new_authorization_id("persistent-empty"))
    record = trusted.record_path(auth_id)
    _write_record(record, b"")
    monkeypatch.setattr(authorization_module, "_USE_RECORD_READ_ATTEMPTS", 3)
    monkeypatch.setattr(authorization_module, "_USE_RECORD_READ_DELAY_SECONDS", 0.005)
    with pytest.raises(AuthorizationRejected) as error:
        trusted.consume()
    assert error.value.reasons == ("AUTHORIZATION_USE_RECORD_INVALID",)
    assert record.stat().st_size == 0


# ---------------------------------------------------------------------------
# capacity accounting and symlink negatives
# ---------------------------------------------------------------------------
def test_stale_temporary_file_is_not_counted_as_a_use(
        trusted, monkeypatch: pytest.MonkeyPatch) -> None:
    prefix = authorization_module._USE_RECORD_TEMP_PREFIX
    stale = trusted.use_log / (prefix + "0123456789abcdef0123456789abcdef"
                               + authorization_module._USE_RECORD_TEMP_SUFFIX)
    stale.write_bytes(b"{}")
    monkeypatch.setattr(authorization_module, "MAX_AUTHORIZATION_USES", 1)
    _set_authorization(trusted, _new_authorization_id("temp-count"))
    use = trusted.consume()
    assert use.record_path.is_file()
    assert _temp_entries(trusted) == [stale]  # our own temporaries are cleaned up
    assert len(_json_records(trusted)) == 1
    _set_authorization(trusted, _new_authorization_id("temp-count-2"))
    with pytest.raises(AuthorizationRejected) as error:
        trusted.consume()
    assert error.value.reasons == ("AUTHORIZATION_USE_LOG_FULL",)


@pytest.mark.parametrize("dangling", [False, True])
def test_symlinked_use_record_is_never_followed(
        trusted, tmp_path, dangling: bool) -> None:
    auth_id = _set_authorization(trusted, _new_authorization_id("symlink"))
    record = trusted.record_path(auth_id)
    if dangling:
        record.symlink_to(tmp_path / "missing-record.json")
    else:
        target = tmp_path / "elsewhere-record.json"
        _write_record(target, _use_record_body(auth_id))
        record.symlink_to(target)
    with pytest.raises(AuthorizationRejected) as error:
        trusted.consume()
    assert error.value.reasons == ("AUTHORIZATION_USE_RECORD_INVALID",)
    if not dangling:
        assert record.is_symlink()


# ---------------------------------------------------------------------------
# repeated races (the old implementation flaked ~2/30 here)
# ---------------------------------------------------------------------------
def test_repeated_concurrent_rounds_are_stable(trusted) -> None:
    for round_index in range(8):
        _set_authorization(trusted, _new_authorization_id(f"round-{round_index:02d}"))
        results, errors = _race_consume(trusted)
        assert len(results) == 1
        assert len(errors) == 1
        assert errors[0].reasons == ("AUTHORIZATION_REPLAYED",)
        assert len(_json_records(trusted)) == round_index + 1
        assert _temp_entries(trusted) == []
        assert all(path.stat().st_size > 0 for path in _json_records(trusted))
