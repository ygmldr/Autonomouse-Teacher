"""Controller wiring: opt-in run admission, deny-before-Reserve, default path.

All broker/fake subprocesses are the frozen synthetic G4-F3 fixtures; nothing
contacts a network, Key or Provider.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys


from admission_support import (
    begin, write_admission,
)
from autoteacher_m0.bridge import run_admission as ra
from autoteacher_m0.bridge.admission import load_admission
from autoteacher_m0.bridge.attempts import AttemptJournal
from autoteacher_m0.bridge.controller import TrustedController
from autoteacher_m0.bridge.dispatch_audit import default_journal_path
from autoteacher_m0.bridge.fake_backend import FakeBackend
import g4f3_support as f3

DIGEST = "a" * 64


class _DenyingAdmission:
    run_id = "run-denied"
    run_epoch = "run-denied-epoch"
    authorization_id = "auth-denied"

    def __init__(self, denial: str | None = None,
                 error: ra.RunAdmissionError | None = None) -> None:
        self.denial = denial
        self.error = error

    def begin_dispatch(self, **kwargs):
        if self.error is not None:
            raise self.error
        return object()

    def consume_dispatch(self, token, **kwargs):
        return self.denial


def _broker_state(broker) -> dict:
    reply = broker.snapshot()
    assert reply.get("ok") is True, reply
    return reply["snapshot"]


def _controller(tmp_path: Path, *, run_admission=None, broker_options=None,
                gate=None):
    admission_path = write_admission(tmp_path)
    admission = load_admission(admission_path, expected_uid=65534)
    broker = f3.start_broker(tmp_path, **(broker_options or {}))
    fake = FakeBackend(script=str(f3.FAKE), receipt_dir=str(tmp_path / "receipts"),
                       python=sys.executable, mode="ok_usage")
    attempts = AttemptJournal(tmp_path / "attempts.sqlite3")
    journal_path = default_journal_path(tmp_path / "attempts.sqlite3")
    controller = TrustedController(
        admission, broker=broker, fake=fake, attempts=attempts,
        expected_uid=65534, dispatch_gate=gate or f3.make_gate(),
        dispatch_journal=journal_path, run_admission=run_admission)
    return controller, broker, fake, attempts, journal_path


def _dispatch_journal(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def test_opt_in_success_consumes_one_token_per_dispatch(trusted, tmp_path: Path) -> None:
    admission_path = write_admission(tmp_path)
    context = begin(trusted, tmp_path, admission_path=admission_path)
    controller, broker, fake, attempts, journal_path = _controller(
        tmp_path, run_admission=context)
    try:
        frames = f3.collect(controller, f3.request_payload())
        assert f3.call_error(frames) is None
        assert _broker_state(broker)["requests"] == 1
        assert len(attempts.attempts()) == 1
        assert context._consumed_ordinals == {1}
        record = _dispatch_journal(journal_path)[-1]
        run_audit = record["run_admission"]
        assert run_audit["token_consumed"] is True
        assert run_audit["denial"] is None
        assert run_audit["run_epoch"] == context.run_epoch
        assert run_audit["dispatch_ordinal"] == 1
    finally:
        f3.close_all(controller, broker, fake, attempts)
        context.close("test")


def test_r19_token_denial_creates_zero_ledger_traces(trusted, tmp_path: Path) -> None:
    controller, broker, fake, attempts, journal_path = _controller(
        tmp_path, run_admission=_DenyingAdmission(ra.ADMISSION_TOKEN_REPLAYED))
    try:
        frames = f3.collect(controller, f3.request_payload())
        assert f3.call_error(frames) == "ADMISSION_SELF_AUTH_DENIED"
        snapshot = _broker_state(broker)
        assert snapshot["requests"] == 0
        assert snapshot.get("reservations", []) == []
        assert attempts.attempts() == []
        assert attempts.pending_intents() == []
        assert not list((tmp_path / "receipts").glob("*"))
        record = _dispatch_journal(journal_path)[-1]
        assert record["error_code"] == "ADMISSION_SELF_AUTH_DENIED"
        assert record["run_admission"]["denial"] == ra.ADMISSION_TOKEN_REPLAYED
        assert record["run_admission"]["token_consumed"] is False
    finally:
        f3.close_all(controller, broker, fake, attempts)


def test_inactive_run_admission_denies_before_reserve(trusted, tmp_path: Path) -> None:
    denial = _DenyingAdmission(
        error=ra.RunAdmissionError(ra.RUN_ADMISSION_INACTIVE, ("closed",)))
    controller, broker, fake, attempts, _ = _controller(
        tmp_path, run_admission=denial)
    try:
        frames = f3.collect(controller, f3.request_payload())
        assert f3.call_error(frames) == "ADMISSION_SELF_AUTH_DENIED"
        assert _broker_state(broker)["requests"] == 0
        assert attempts.attempts() == []
    finally:
        f3.close_all(controller, broker, fake, attempts)


def test_r21_token_ok_but_broker_reserve_denied(trusted, tmp_path: Path) -> None:
    admission_path = write_admission(tmp_path)
    context = begin(trusted, tmp_path, admission_path=admission_path)
    controller, broker, fake, attempts, _ = _controller(
        tmp_path, run_admission=context, broker_options={"max_requests": 1})
    try:
        first = f3.collect(controller, f3.request_payload())
        assert f3.call_error(first) is None
        assert len(attempts.attempts()) == 1
        # The second dispatch consumes a second token but the Broker refuses
        # the Reserve: no new attempt may exist and no Fake bytes may be sent.
        second = f3.collect(controller, f3.request_payload(
            messages=[{"role": "user", "content": "hello again"}]))
        assert f3.call_error(second) is not None
        assert _broker_state(broker)["requests"] == 1
        assert len(attempts.attempts()) == 1
        assert context._consumed_ordinals == {1, 2}
    finally:
        f3.close_all(controller, broker, fake, attempts)
        context.close("test")


def test_c5_one_token_per_payload_payload_count(trusted, tmp_path: Path) -> None:
    # C5: an internal max_attempts retry must not consume another token. The
    # frozen Admission contract fixes max_attempts=1, so the structural proof
    # is: one payload -> exactly one consumed ordinal, independent of the
    # attempt count recorded by the Controller.
    admission_path = write_admission(tmp_path)
    context = begin(trusted, tmp_path, admission_path=admission_path)
    controller, broker, fake, attempts, journal_path = _controller(
        tmp_path, run_admission=context)
    try:
        frames = f3.collect(controller, f3.request_payload())
        assert f3.call_error(frames) is None
        assert len(context._consumed_ordinals) == 1
        assert attempts.attempts()[0]["state"] in {"RESPONSE_OBSERVED", "SETTLED"}
        record = _dispatch_journal(journal_path)[-1]
        assert record["run_admission"]["dispatch_ordinal"] == 1
    finally:
        f3.close_all(controller, broker, fake, attempts)
        context.close("test")


def test_default_path_without_run_admission_is_unchanged(trusted, tmp_path: Path) -> None:
    controller, broker, fake, attempts, journal_path = _controller(tmp_path)
    try:
        frames = f3.collect(controller, f3.request_payload())
        assert f3.call_error(frames) is None
        assert _broker_state(broker)["requests"] == 1
        record = _dispatch_journal(journal_path)[-1]
        assert "run_admission" not in record
        assert record["reserved"] is True
    finally:
        f3.close_all(controller, broker, fake, attempts)
