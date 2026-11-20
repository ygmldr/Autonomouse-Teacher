"""Per-dispatch admission token verification (R-19/R-20, design §4)."""
from __future__ import annotations

import dataclasses

import pytest

from admission_support import begin_kwargs, write_admission
from autoteacher_m0.bridge import run_admission as ra

CALL_ID = "call-a2-dispatch-1"
DIGEST = "a" * 64


def _mint(context, *, call_id: str = CALL_ID):
    return context.begin_dispatch(call_id=call_id, prepared_digest=DIGEST,
                                  payload_digest=DIGEST, scope_id="fixed-offline-scope",
                                  route_id="offline-test-only-g3b",
                                  model_id="fixture-bridge-v1")


def test_token_happy_path_and_replay(trusted, tmp_path) -> None:
    context = ra.begin_run_admission(**begin_kwargs(trusted, tmp_path))
    try:
        token = _mint(context)
        assert token.dispatch_ordinal == 1
        assert token.run_epoch == context.run_epoch
        assert context.consume_dispatch(token, call_id=CALL_ID,
                                        prepared_digest=DIGEST,
                                        payload_digest=DIGEST) is None
        assert context.consume_dispatch(token, call_id=CALL_ID,
                                        prepared_digest=DIGEST,
                                        payload_digest=DIGEST) == \
            ra.ADMISSION_TOKEN_REPLAYED
    finally:
        context.close("test")


def test_r19_candidate_json_and_copied_token_are_unknown(trusted, tmp_path) -> None:
    context = ra.begin_run_admission(**begin_kwargs(trusted, tmp_path))
    try:
        token = _mint(context)
        assert context.consume_dispatch(
            {"schema_version": ra.DISPATCH_TOKEN_SCHEMA},
            call_id=CALL_ID, prepared_digest=DIGEST,
            payload_digest=DIGEST) == ra.ADMISSION_TOKEN_UNKNOWN
        copied = dataclasses.replace(token)
        assert context.consume_dispatch(
            copied, call_id=CALL_ID, prepared_digest=DIGEST,
            payload_digest=DIGEST) == ra.ADMISSION_TOKEN_UNKNOWN
        assert context.consume_dispatch(
            None, call_id=CALL_ID, prepared_digest=DIGEST,
            payload_digest=DIGEST) == ra.ADMISSION_TOKEN_UNKNOWN
    finally:
        context.close("test")


def test_r19_token_from_another_context_is_unknown(trusted, tmp_path) -> None:
    first = ra.begin_run_admission(**begin_kwargs(trusted, tmp_path))
    from admission_support import write_state
    second_use_log, second_journal = write_state(tmp_path, suffix="-second")
    second = ra.begin_run_admission(**begin_kwargs(
        trusted, tmp_path, admission_path=write_admission(
            tmp_path, run_id="run-second", nonce="c" * 32,
            admission_id="d" * 32),
        use_log_dir=second_use_log, journal_path=second_journal))
    try:
        foreign = _mint(first)
        assert second.consume_dispatch(
            foreign, call_id=CALL_ID, prepared_digest=DIGEST,
            payload_digest=DIGEST) == ra.ADMISSION_TOKEN_UNKNOWN
    finally:
        first.close("test")
        second.close("test")


def test_r20_binding_mismatch_is_denied(trusted, tmp_path) -> None:
    context = ra.begin_run_admission(**begin_kwargs(trusted, tmp_path))
    try:
        token = _mint(context)
        assert context.consume_dispatch(
            token, call_id="call-other", prepared_digest=DIGEST,
            payload_digest=DIGEST) == ra.ADMISSION_TOKEN_BINDING_MISMATCH
        assert context.consume_dispatch(
            token, call_id=CALL_ID, prepared_digest="b" * 64,
            payload_digest=DIGEST) == ra.ADMISSION_TOKEN_BINDING_MISMATCH
        assert context.consume_dispatch(
            token, call_id=CALL_ID, prepared_digest=DIGEST,
            payload_digest="b" * 64) == ra.ADMISSION_TOKEN_BINDING_MISMATCH
    finally:
        context.close("test")


def test_r20_expired_token_is_denied(trusted, tmp_path) -> None:
    context = ra.begin_run_admission(**begin_kwargs(trusted, tmp_path))
    try:
        token = _mint(context)
        context._issued_deadline[id(token)] = 0.0
        assert context.consume_dispatch(
            token, call_id=CALL_ID, prepared_digest=DIGEST,
            payload_digest=DIGEST) == ra.ADMISSION_TOKEN_EXPIRED
    finally:
        context.close("test")


def test_r20_closed_context_cannot_mint_or_consume(trusted, tmp_path) -> None:
    context = ra.begin_run_admission(**begin_kwargs(trusted, tmp_path))
    token = _mint(context)
    context.close("closed")
    with pytest.raises(ra.RunAdmissionError) as error:
        context.begin_dispatch(call_id=CALL_ID, prepared_digest=DIGEST,
                               payload_digest=DIGEST)
    assert error.value.code == ra.RUN_ADMISSION_INACTIVE
    assert context.consume_dispatch(
        token, call_id=CALL_ID, prepared_digest=DIGEST,
        payload_digest=DIGEST) == ra.RUN_ADMISSION_INACTIVE


def test_r20_ordinal_budget_bound(trusted, tmp_path) -> None:
    context = ra.begin_run_admission(**begin_kwargs(
        trusted, tmp_path,
        admission_path=write_admission(tmp_path, max_calls=2,
                                       run_id="run-budget", nonce="c" * 32,
                                       admission_id="d" * 32)))
    try:
        for _ in range(2):
            token = _mint(context)
            assert context.consume_dispatch(
                token, call_id=CALL_ID, prepared_digest=DIGEST,
                payload_digest=DIGEST) is None
        with pytest.raises(ra.RunAdmissionError) as error:
            _mint(context)
        assert error.value.code == ra.RUN_BUDGET_CALLS_EXCEEDED
    finally:
        context.close("test")


def test_r20_foreign_process_context_is_not_startable(trusted, tmp_path) -> None:
    context = ra.begin_run_admission(**begin_kwargs(trusted, tmp_path))
    try:
        context.owner_pid = context.owner_pid + 1
        with pytest.raises(ra.RunAdmissionError) as error:
            context.ensure_startable()
        assert error.value.code == ra.RUN_ADMISSION_NOT_ACTIVE
    finally:
        context.close("test")
