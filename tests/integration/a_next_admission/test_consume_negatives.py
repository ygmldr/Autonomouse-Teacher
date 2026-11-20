"""Consume-level negatives: replay/epoch/record integrity/fault injection (R-05..R-13)."""
from __future__ import annotations

import concurrent.futures
import errno
import hashlib
import json
import os
from pathlib import Path
import threading

import pytest

from admission_support import (
    begin_kwargs, use_records, write_admission,
    write_state,
)
from autoteacher_m0.bridge import run_admission as ra
from autoteacher_m0.security import authorization as authorization_module
from autoteacher_m0.security.authorization import AuthorizationUse


def _record_path(use_log: Path, authorization_id: str) -> Path:
    return use_log / (hashlib.sha256(authorization_id.encode("ascii")).hexdigest() + ".json")


def _consume(kwargs: dict):
    return ra.begin_run_admission(**kwargs)


def test_r05_same_run_restart_is_replay(trusted, tmp_path: Path) -> None:
    use_log, journal_path = write_state(tmp_path)
    kwargs = begin_kwargs(trusted, tmp_path, use_log_dir=use_log,
                          journal_path=journal_path)
    context = ra.begin_run_admission(**kwargs)
    context.close("crash-after-consume-before-broker")
    with pytest.raises(ra.RunAdmissionError) as error:
        ra.begin_run_admission(**kwargs)
    assert error.value.code == ra.RUN_ADMISSION_ALREADY_CONSUMED
    assert error.value.consumed == "NO"
    # The final use record is never cleaned up or rewritten by a restart.
    records = use_records(use_log)
    assert len(records) == 1
    body = json.loads(records[0].read_text(encoding="utf-8"))
    assert body["run_epoch"] == context.run_epoch


def test_r06_other_run_epoch_mismatch(trusted, tmp_path: Path) -> None:
    use_log, journal_path = write_state(tmp_path)
    first = begin_kwargs(trusted, tmp_path, use_log_dir=use_log,
                         journal_path=journal_path)
    ra.begin_run_admission(**first).close("first-run")
    second_admission = write_admission(tmp_path, nonce="c" * 32,
                                       run_id="run-other")
    second = begin_kwargs(trusted, tmp_path, admission_path=second_admission,
                          use_log_dir=use_log, journal_path=journal_path)
    with pytest.raises(ra.RunAdmissionError) as error:
        ra.begin_run_admission(**second)
    assert error.value.code == ra.RUN_ADMISSION_EPOCH_MISMATCH
    assert error.value.consumed == "NO"
    assert len(use_records(use_log)) == 1


@pytest.mark.parametrize("bad_payload", [
    b"",
    b"not-json",
    b'{"schema": "at-m0/authorization-use/v1"}',
    json.dumps({"schema": "at-m0/authorization-use/v1",
                "authorization_id": "auth-g4a-synthetic-1",
                "run_epoch": "epoch-g4a-1",
                "consumed_utc": "2026-11-18T12:00:00Z",
                "extra": True}).encode(),
])
def test_r07_r08_invalid_or_replaced_use_record(trusted, tmp_path: Path,
                                                bad_payload: bytes) -> None:
    use_log, journal_path = write_state(tmp_path)
    _record_path(use_log, trusted.payload["authorization_id"]).write_bytes(bad_payload)
    kwargs = begin_kwargs(trusted, tmp_path, use_log_dir=use_log,
                          journal_path=journal_path)
    with pytest.raises(ra.RunAdmissionError) as error:
        ra.begin_run_admission(**kwargs)
    assert error.value.code == ra.RUN_ADMISSION_RECORD_INVALID
    assert error.value.consumed == "NO"


def test_r09_symlink_and_hardlinked_use_record(trusted, tmp_path: Path) -> None:
    use_log, journal_path = write_state(tmp_path)
    target = tmp_path / "target.json"
    target.write_text(json.dumps({"schema": "at-m0/authorization-use/v1",
                                  "authorization_id":
                                      trusted.payload["authorization_id"],
                                  "run_epoch": "run-x",
                                  "consumed_utc": "2026-11-18T12:00:00Z"}))
    record = _record_path(use_log, trusted.payload["authorization_id"])
    os.symlink(target, record)
    kwargs = begin_kwargs(trusted, tmp_path, use_log_dir=use_log,
                          journal_path=journal_path)
    with pytest.raises(ra.RunAdmissionError) as error:
        ra.begin_run_admission(**kwargs)
    assert error.value.code == ra.RUN_ADMISSION_RECORD_INVALID
    record.unlink()
    record.write_bytes(target.read_bytes())
    os.link(record, tmp_path / "extra1.json")
    os.link(record, tmp_path / "extra2.json")
    with pytest.raises(ra.RunAdmissionError) as error:
        ra.begin_run_admission(**kwargs)
    assert error.value.code == ra.RUN_ADMISSION_RECORD_INVALID


def test_r10_concurrent_consumers_exactly_one_wins(trusted, tmp_path: Path) -> None:
    use_log, _ = write_state(tmp_path)
    base = begin_kwargs(trusted, tmp_path, use_log_dir=use_log)
    journals = [tmp_path / f"journal-{index}.jsonl" for index in range(8)]
    barrier = threading.Barrier(len(journals))
    results: list[object] = []
    lock = threading.Lock()

    def worker(journal_path: Path) -> None:
        kwargs = dict(base)
        kwargs["journal_path"] = journal_path
        barrier.wait()
        try:
            context = ra.begin_run_admission(**kwargs)
        except ra.RunAdmissionError as error:
            with lock:
                results.append(error.code)
            return
        context.close("winner")
        with lock:
            results.append("ALLOW")

    with concurrent.futures.ThreadPoolExecutor(len(journals)) as pool:
        futures = [pool.submit(worker, path) for path in journals]
        for future in futures:
            future.result()
    assert results.count("ALLOW") == 1
    assert results.count(ra.RUN_ADMISSION_ALREADY_CONSUMED) == 7
    assert len(use_records(use_log)) == 1


def test_r11_link_failure_is_not_consumed_then_retry_succeeds(
        trusted, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    use_log, journal_path = write_state(tmp_path)
    kwargs = begin_kwargs(trusted, tmp_path, use_log_dir=use_log,
                          journal_path=journal_path)
    real_link = authorization_module.os.link

    def failing_link(*args, **kwargs_):
        raise OSError(errno.EXDEV, "synthetic cross-device failure")

    authorization_module.os.link = failing_link
    try:
        with pytest.raises(ra.RunAdmissionError) as error:
            ra.begin_run_admission(**kwargs)
    finally:
        authorization_module.os.link = real_link
    assert error.value.code == ra.RUN_ADMISSION_LOG_UNAVAILABLE
    assert error.value.consumed == "NO"
    assert use_records(use_log) == []
    context = ra.begin_run_admission(**kwargs)
    assert context.state == ra.RUN_ADMISSION_ACTIVE
    context.close("test")
    assert len(use_records(use_log)) == 1


def test_r12_crash_before_link_leaves_no_record_then_retry_succeeds(
        trusted, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    use_log, journal_path = write_state(tmp_path)
    kwargs = begin_kwargs(trusted, tmp_path, use_log_dir=use_log,
                          journal_path=journal_path)
    real_link = authorization_module._link_use_record_no_replace

    def crash(*args, **kwargs_):
        raise SystemExit(97)

    authorization_module._link_use_record_no_replace = crash
    try:
        with pytest.raises(SystemExit):
            ra.begin_run_admission(**kwargs)
    finally:
        authorization_module._link_use_record_no_replace = real_link
    assert use_records(use_log) == []
    context = ra.begin_run_admission(**kwargs)
    context.close("test")
    assert len(use_records(use_log)) == 1


def test_r13_durability_unknown_is_tri_state_and_replay_afterwards(
        trusted, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    use_log, journal_path = write_state(tmp_path)
    kwargs = begin_kwargs(trusted, tmp_path, use_log_dir=use_log,
                          journal_path=journal_path)
    real_fsync = authorization_module._fsync_directory

    def failing_fsync(directory: Path) -> None:
        raise OSError(errno.EIO, "synthetic directory fsync failure")

    authorization_module._fsync_directory = failing_fsync
    try:
        with pytest.raises(ra.RunAdmissionError) as error:
            ra.begin_run_admission(**kwargs)
    finally:
        authorization_module._fsync_directory = real_fsync
    assert error.value.code == ra.RUN_ADMISSION_DURABILITY_UNKNOWN
    assert error.value.consumed == "UNKNOWN"
    assert len(use_records(use_log)) == 1
    with pytest.raises(ra.RunAdmissionError) as error:
        ra.begin_run_admission(**kwargs)
    assert error.value.code == ra.RUN_ADMISSION_ALREADY_CONSUMED


def test_c2_post_consume_authorization_id_drift(
        trusted, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    use_log, journal_path = write_state(tmp_path)
    kwargs = begin_kwargs(trusted, tmp_path, use_log_dir=use_log,
                          journal_path=journal_path)
    real_consume = ra.consume_execution_authorization

    def drifting_consume(*args, **kwargs_):
        use = real_consume(*args, **kwargs_)
        return AuthorizationUse("auth-some-other-id", use.run_epoch,
                                use.consumed_utc, use.record_path)

    monkeypatch.setattr(ra, "consume_execution_authorization", drifting_consume)
    with pytest.raises(ra.RunAdmissionError) as error:
        ra.begin_run_admission(**kwargs)
    assert error.value.code == ra.RUN_ADMISSION_AUTHORIZATION_DRIFT
    assert error.value.consumed == "UNKNOWN"
    assert error.value.record["authorization_file_sha256"]
    records = use_records(use_log)
    assert len(records) == 1


def test_c2_post_consume_epoch_drift_detected(
        trusted, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    use_log, journal_path = write_state(tmp_path)
    kwargs = begin_kwargs(trusted, tmp_path, use_log_dir=use_log,
                          journal_path=journal_path)
    real_consume = ra.consume_execution_authorization

    def drifting_consume(*args, **kwargs_):
        use = real_consume(*args, **kwargs_)
        return AuthorizationUse(use.authorization_id, "run-other-epoch",
                                use.consumed_utc, use.record_path)

    monkeypatch.setattr(ra, "consume_execution_authorization", drifting_consume)
    with pytest.raises(ra.RunAdmissionError) as error:
        ra.begin_run_admission(**kwargs)
    assert error.value.code == ra.RUN_ADMISSION_AUTHORIZATION_DRIFT


def test_c2_authorization_file_changed_after_consume(
        trusted, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    use_log, journal_path = write_state(tmp_path)
    kwargs = begin_kwargs(trusted, tmp_path, use_log_dir=use_log,
                          journal_path=journal_path)
    real_consume = ra.consume_execution_authorization
    changed = dict(trusted.payload)

    def mutating_consume(*args, **kwargs_):
        use = real_consume(*args, **kwargs_)
        trusted.authorization.write_text(json.dumps(changed))
        return use

    monkeypatch.setattr(ra, "consume_execution_authorization", mutating_consume)
    with pytest.raises(ra.RunAdmissionError) as error:
        ra.begin_run_admission(**kwargs)
    assert error.value.code == ra.RUN_ADMISSION_AUTHORIZATION_DRIFT
    assert any("changed_after_consume" in reason for reason in error.value.reasons)
