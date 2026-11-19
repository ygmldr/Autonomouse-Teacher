"""G4-H0 P2-06: startup recovery must not rewrite the original failure reason.

``docs/REVIEW_G4F_INDEPENDENT.md`` P2-06: in the F5 ``revocation-post-reserve``
window recovery marked the attempt ``SETTLEMENT_UNCERTAIN`` with
``RECEIPT_DOCUMENT_SCHEMA_INVALID``, overwriting the original
``REVOKED_PRE_SEND:RUN_AUTHORIZATION_REVOKED`` classification. The conservative
state, held cost and no-resend/no-FREE behaviour were already correct; only the
evidence label was lost.

These tests replay the same host windows and pin the fixed contract:

* the recovery row stays ``SETTLEMENT_UNCERTAIN`` with the same held semantics;
* the original window reason stays the primary label, including
  ``RUN_AUTHORIZATION_REVOKED`` for revocation windows;
* the recovery evidence is appended (``|RECOVERY_EVIDENCE:...``), never a
  replacement;
* no Fake bytes, no settlement, no second ledger row (fail-closed unchanged).

Synthetic Broker/Fake subprocesses only; no Key, model, provider or network.
"""
from __future__ import annotations

from decimal import Decimal

from autoteacher_m0.bridge.attempts import AttemptJournal
from autoteacher_m0.bridge.controller import TrustedController

import g4f3_support as f3
import g4f5_support as f5


def _broker_snapshot(broker) -> dict:
    reply = broker.snapshot()
    assert reply.get("ok") is True, reply
    return reply["snapshot"]


def _recover(controller, tmp_path, *, gate):
    """Restart recovery with a fresh trusted Controller over the same durable state."""
    attempts2 = AttemptJournal(tmp_path / "attempts.sqlite3")
    controller2 = TrustedController(
        controller.admission, broker=controller.broker, fake=controller.fake,
        attempts=attempts2, expected_uid=65534, register_admission=False,
        dispatch_gate=gate)
    controller2.reconcile_on_startup(str(tmp_path / "receipts"))
    return controller2, attempts2


def test_recovery_preserves_post_reserve_revocation_reason(tmp_path) -> None:
    path = f5.revocation_path(tmp_path)
    f5.write_revocation(path, revoked=False)
    gate = f5.RevokeOnAuthorizeGate(path)
    controller, broker, fake, attempts, gate = f5.start_controller(
        tmp_path, gate=gate, max_calls=8)
    try:
        frames = f3.collect(controller, f3.request_payload())
        assert f3.call_error(frames) == "ADMISSION_SELF_AUTH_DENIED", frames
        assert fake.received_count() == 0
        original = attempts.attempts()[0]
        assert original["state"] == "SETTLEMENT_UNCERTAIN"
        assert original["reason"].startswith("REVOKED_PRE_SEND:")
        assert "RUN_AUTHORIZATION_REVOKED" in original["reason"]

        before = _broker_snapshot(broker)
        assert before["requests"] == 1 and before["pending"] == 1
        assert Decimal(before["spent_usd"]) == 0

        recovery_gate = f5.make_gate(revocation=path)
        _, attempts2 = _recover(controller, tmp_path, gate=recovery_gate)
        rows = attempts2.attempts()
        assert len(rows) == 1
        recovered = rows[0]
        # The conservative state and held cost are unchanged ...
        assert recovered["state"] == "SETTLEMENT_UNCERTAIN"
        snapshot = recovery_gate.snapshot()
        assert snapshot["worst_case_held_usd"] == before["reserved_usd"]
        assert snapshot["known_cost_usd"] == "0"
        # ... and the original revocation classification is still primary.
        assert recovered["reason"].startswith("REVOKED_PRE_SEND:")
        assert "RUN_AUTHORIZATION_REVOKED" in recovered["reason"]
        assert "|RECOVERY_EVIDENCE:" in recovered["reason"]
        assert recovered["reason"].startswith(original["reason"])
        assert fake.received_count() == 0
        assert _broker_snapshot(broker)["requests"] == 1
    finally:
        f3.close_all(broker, fake, attempts)


def test_recovery_preserves_consume_window_revocation_reason(tmp_path) -> None:
    path = f5.revocation_path(tmp_path)
    f5.write_revocation(path, revoked=False)
    gate = f5.RevokeOnConsumeGate(path)
    controller, broker, fake, attempts, gate = f5.start_controller(
        tmp_path, gate=gate, max_calls=8)
    try:
        frames = f3.collect(controller, f3.request_payload())
        assert f3.call_error(frames) == "ADMISSION_SELF_AUTH_DENIED", frames
        assert fake.received_count() == 0
        original = attempts.attempts()[0]
        assert original["state"] == "SETTLEMENT_UNCERTAIN"
        assert "RUN_AUTHORIZATION_REVOKED" in original["reason"]

        recovery_gate = f5.make_gate(revocation=path)
        _, attempts2 = _recover(controller, tmp_path, gate=recovery_gate)
        recovered = attempts2.attempts()[0]
        assert recovered["state"] == "SETTLEMENT_UNCERTAIN"
        assert "RUN_AUTHORIZATION_REVOKED" in recovered["reason"]
        assert recovered["reason"].startswith(original["reason"])
        assert fake.received_count() == 0
        assert _broker_snapshot(broker)["requests"] == 1
    finally:
        f3.close_all(broker, fake, attempts)


def test_recovery_preserves_non_revocation_window_reason(tmp_path) -> None:
    """The same preservation applies to a pre-send deadline window, not just revocation."""
    gate = f5.make_gate()
    controller, broker, fake, attempts, gate = f5.start_controller(
        tmp_path, gate=gate, scenario="slow_usage", deadline_ms=800, max_calls=8)
    try:
        frames = f3.collect(controller, f3.request_payload())
        assert f3.call_error(frames) == "DEADLINE_EXCEEDED", frames
        original = attempts.attempts()[0]
        assert original["state"] == "SETTLEMENT_UNCERTAIN"
        assert original["reason"]
        received = fake.received_count()

        recovery_gate = f5.make_gate()
        _, attempts2 = _recover(controller, tmp_path, gate=recovery_gate)
        recovered = attempts2.attempts()[0]
        assert recovered["state"] == "SETTLEMENT_UNCERTAIN"
        assert recovered["reason"].startswith(original["reason"])
        assert "|RECOVERY_EVIDENCE:" in recovered["reason"]
        assert fake.received_count() == received  # never resent by recovery
        assert _broker_snapshot(broker)["requests"] == 1
    finally:
        f3.close_all(broker, fake, attempts)
