"""G4-A-12: one authorization = one run epoch; replay and cross-run reuse deny."""
from __future__ import annotations

import copy
from concurrent.futures import ThreadPoolExecutor
import json
import threading

import pytest

from autoteacher_m0.security import authorization as authorization_module
from autoteacher_m0.security.authorization import AuthorizationRejected
from g4a_support import NOW, RUN_EPOCH, base_payload

AUTH_ID = "auth-g4a-synthetic-1"
NEW_AUTH_ID = "auth-g4a-synthetic-2"


def _rejected(trusted, *, run_epoch: str = RUN_EPOCH, code: str, **kwargs):
    with pytest.raises(AuthorizationRejected) as error:
        trusted.consume(run_epoch=run_epoch, **kwargs)
    assert code in error.value.reasons, error.value.reasons
    return error.value


def test_a12_first_consumption_writes_one_private_use_record(trusted) -> None:
    use = trusted.consume()
    assert use.authorization_id == AUTH_ID
    assert use.run_epoch == RUN_EPOCH
    assert use.consumed_utc == "2026-11-18T12:00:00Z"
    assert use.record_path == trusted.record_path(AUTH_ID)
    assert use.record_path.is_file()
    assert (use.record_path.stat().st_mode & 0o777) == 0o600
    payload = json.loads(use.record_path.read_text(encoding="utf-8"))
    assert payload == {"schema": "at-m0/authorization-use/v1",
                       "authorization_id": AUTH_ID, "run_epoch": RUN_EPOCH,
                       "consumed_utc": "2026-11-18T12:00:00Z"}
    assert trusted.use_records() == [use.record_path]


def test_a12_same_epoch_replay_is_rejected(trusted) -> None:
    trusted.consume()
    _rejected(trusted, code="AUTHORIZATION_REPLAYED")
    assert len(trusted.use_records()) == 1


def test_a12_new_run_with_old_authorization_id_is_rejected(trusted) -> None:
    trusted.consume()
    _rejected(trusted, run_epoch="epoch-g4a-2", code="AUTHORIZATION_EPOCH_MISMATCH")
    assert len(trusted.use_records()) == 1


def test_a12_new_epoch_requires_a_new_signed_authorization_id(trusted) -> None:
    trusted.consume()
    payload = copy.deepcopy(base_payload(trusted.bindings.as_dict()))
    payload["authorization_id"] = NEW_AUTH_ID
    trusted.write_signed(payload)
    use = trusted.consume(run_epoch="epoch-g4a-2")
    assert use.authorization_id == NEW_AUTH_ID
    assert use.run_epoch == "epoch-g4a-2"
    assert len(trusted.use_records()) == 2
    _rejected(trusted, run_epoch="epoch-g4a-3", code="AUTHORIZATION_EPOCH_MISMATCH")


def test_a12_concurrent_consumption_admits_exactly_one(trusted) -> None:
    barrier = threading.Barrier(2)
    results: list[object] = []
    errors: list[AuthorizationRejected] = []

    def worker() -> None:
        barrier.wait(timeout=30)
        try:
            results.append(trusted.consume())
        except AuthorizationRejected as error:
            errors.append(error)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(worker) for _ in range(2)]
        for future in futures:
            future.result(timeout=60)
    assert len(results) == 1
    assert len(errors) == 1
    assert "AUTHORIZATION_REPLAYED" in errors[0].reasons
    assert len(trusted.use_records()) == 1


def test_a12_denied_verification_never_consumes(trusted) -> None:
    _rejected(trusted, code="AUTHORIZATION_NOT_CURRENT",
              now=NOW.replace(day=19))  # type: ignore[attr-defined]
    assert trusted.use_records() == []


def test_a12_use_log_location_must_be_trusted(trusted, tmp_path) -> None:
    in_repo = trusted.repo / "use-log"
    in_repo.mkdir()
    with pytest.raises(AuthorizationRejected) as error:
        trusted.consume(use_log_dir=in_repo)
    assert error.value.reasons[0].startswith("AUTHORIZATION_USE_LOG_INVALID")
    assert "outside the repository" in error.value.reasons[0]

    link = tmp_path / "log-link"
    link.symlink_to(trusted.use_log)
    with pytest.raises(AuthorizationRejected) as error:
        trusted.consume(use_log_dir=link)
    assert error.value.reasons[0].startswith("AUTHORIZATION_USE_LOG_INVALID")

    writable = tmp_path / "log-world-writable"
    writable.mkdir()
    writable.chmod(0o777)
    try:
        with pytest.raises(AuthorizationRejected) as error:
            trusted.consume(use_log_dir=writable)
        assert "group/world writable" in error.value.reasons[0]
    finally:
        writable.chmod(0o755)

    with pytest.raises(AuthorizationRejected) as error:
        trusted.consume(use_log_dir=tmp_path / "missing-log")
    assert error.value.reasons[0].startswith("AUTHORIZATION_USE_LOG_INVALID")
    assert trusted.use_records() == []


@pytest.mark.parametrize("content", ["not json", "{}", "[]",
                                     json.dumps({"schema": "other/v1",
                                                 "authorization_id": AUTH_ID,
                                                 "run_epoch": RUN_EPOCH,
                                                 "consumed_utc": "x"})])
def test_a12_corrupt_use_record_fails_closed(trusted, content: str) -> None:
    trusted.consume()
    trusted.record_path(AUTH_ID).write_text(content, encoding="utf-8")
    _rejected(trusted, code="AUTHORIZATION_USE_RECORD_INVALID")
    assert len(trusted.use_records()) == 1


def test_a12_symlinked_use_record_fails_closed(trusted, tmp_path) -> None:
    trusted.consume()
    record = trusted.record_path(AUTH_ID)
    target = tmp_path / "elsewhere.json"
    target.write_text("{}", encoding="utf-8")
    record.unlink()
    record.symlink_to(target)
    _rejected(trusted, code="AUTHORIZATION_USE_RECORD_INVALID")


def test_a12_use_log_capacity_is_bounded(trusted,
                                         monkeypatch: pytest.MonkeyPatch) -> None:
    trusted.consume()
    monkeypatch.setattr(authorization_module, "MAX_AUTHORIZATION_USES", 1)
    payload = copy.deepcopy(base_payload(trusted.bindings.as_dict()))
    payload["authorization_id"] = NEW_AUTH_ID
    trusted.write_signed(payload)
    _rejected(trusted, code="AUTHORIZATION_USE_LOG_FULL")
    assert len(trusted.use_records()) == 1


@pytest.mark.parametrize("epoch", ["", "bad epoch", "x" * 129, 1, None])
def test_a12_run_epoch_must_be_a_strict_identifier(trusted, epoch) -> None:
    with pytest.raises(AuthorizationRejected) as error:
        trusted.consume(run_epoch=epoch)
    assert "RUN_EPOCH_INVALID" in error.value.reasons
    assert trusted.use_records() == []


def test_a12_expired_authorization_cannot_be_consumed(trusted) -> None:
    trusted.set_revocations([])
    with pytest.raises(AuthorizationRejected) as error:
        trusted.consume(now=NOW.replace(day=19))
    assert "AUTHORIZATION_NOT_CURRENT" in error.value.reasons
    assert trusted.use_records() == []
