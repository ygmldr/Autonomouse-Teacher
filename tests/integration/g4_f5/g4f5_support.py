"""G4-F5 host support: revocation input + real Broker/Fake controller chain.

Reuses the G4-F3 real-subprocess harness (Broker/Fake) and adds the G4-F5
synthetic run-authorization revocation document plus deterministic gate
wrappers that write it at the exact authorize/consume windows.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from autoteacher_m0.bridge.attempts import AttemptJournal
from autoteacher_m0.bridge.controller import TrustedController
from autoteacher_m0.security.egress import (
    SYNTHETIC_ROUTE_CONTRACT,
    TrustedSendGate,
)

import g4f3_support as f3
from g4c_support import same_bindings

REVOCATION_SCHEMA = "m0.g4c.revocation.v1"
AUTHORIZATION_ID = "auth-g4f5-host"


def write_revocation(path: Path, *, revoked: bool, epoch: str = f3.AUTH_EPOCH,
                     authorization_id: str = AUTHORIZATION_ID,
                     reason: str = "host-test") -> dict:
    document = {
        "schema": REVOCATION_SCHEMA,
        "authorization_id": authorization_id,
        "auth_epoch": epoch,
        "revoked": bool(revoked),
        "revoked_utc": "2026-11-19T00:00:00Z",
        "reason": reason,
    }
    path.write_text(json.dumps(document, sort_keys=True), encoding="utf-8")
    return document


def revocation_path(tmp_path: Path) -> Path:
    return tmp_path / "revocation.json"


def make_gate(*, revocation: Path | None = None,
              epoch: str = f3.AUTH_EPOCH,
              authorization_id: str = AUTHORIZATION_ID):
    bindings = same_bindings()
    return TrustedSendGate(
        SYNTHETIC_ROUTE_CONTRACT, auth_epoch=epoch,
        binding_approved=bindings, binding_observer=lambda: bindings,
        authorization_id=authorization_id, revocation_path=revocation)


class RevokeOnAuthorizeGate(f3.RecordingGate):
    """Writes a real revocation document immediately before the gate mints."""

    def __init__(self, path: Path, **kwargs) -> None:
        kwargs.setdefault("auth_epoch", f3.AUTH_EPOCH)
        kwargs.setdefault("authorization_id", AUTHORIZATION_ID)
        kwargs.setdefault("revocation_path", path)
        bindings = same_bindings()
        kwargs.setdefault("binding_approved", bindings)
        kwargs.setdefault("binding_observer", lambda: bindings)
        super().__init__(SYNTHETIC_ROUTE_CONTRACT, **kwargs)
        self.revocation_writes: list[dict] = []

    def authorize(self, **kwargs):  # type: ignore[override]
        self.revocation_writes.append(write_revocation(
            Path(self.revocation_path), revoked=True,
            epoch=self.auth_epoch,
            authorization_id=self.authorization_id,
            reason="revoke-at-authorize"))
        return super().authorize(**kwargs)


class RevokeOnConsumeGate(f3.RecordingGate):
    """Writes the real revocation document at the consume (pre-wire) window."""

    def __init__(self, path: Path, **kwargs) -> None:
        kwargs.setdefault("auth_epoch", f3.AUTH_EPOCH)
        kwargs.setdefault("authorization_id", AUTHORIZATION_ID)
        kwargs.setdefault("revocation_path", path)
        bindings = same_bindings()
        kwargs.setdefault("binding_approved", bindings)
        kwargs.setdefault("binding_observer", lambda: bindings)
        super().__init__(SYNTHETIC_ROUTE_CONTRACT, **kwargs)

    def consume(self, *args, **kwargs):  # type: ignore[override]
        write_revocation(Path(self.revocation_path), revoked=True,
                         epoch=self.auth_epoch,
                         authorization_id=self.authorization_id,
                         reason="revoke-at-consume")
        return super().consume(*args, **kwargs)


class CrashAfterAuthorizeGate(f3.RecordingGate):
    """Hard-interrupt immediately after the capability is minted.

    ``SystemExit`` is the same class the real crash hook uses (``os._exit``);
    in-process it exercises the durable state a process death would leave
    behind: Broker PENDING, a consumed/issued capability and no Fake bytes.
    """

    def __init__(self, **kwargs) -> None:
        kwargs.setdefault("auth_epoch", f3.AUTH_EPOCH)
        bindings = same_bindings()
        kwargs.setdefault("binding_approved", bindings)
        kwargs.setdefault("binding_observer", lambda: bindings)
        super().__init__(SYNTHETIC_ROUTE_CONTRACT, **kwargs)

    def authorize(self, **kwargs):  # type: ignore[override]
        super().authorize(**kwargs)
        raise SystemExit(97)


class CrashAfterConsumeGate(f3.RecordingGate):
    """Hard-interrupt after consume, before any bytes reach the Fake."""

    def __init__(self, **kwargs) -> None:
        kwargs.setdefault("auth_epoch", f3.AUTH_EPOCH)
        bindings = same_bindings()
        kwargs.setdefault("binding_approved", bindings)
        kwargs.setdefault("binding_observer", lambda: bindings)
        super().__init__(SYNTHETIC_ROUTE_CONTRACT, **kwargs)

    def consume(self, *args, **kwargs):  # type: ignore[override]
        denial = super().consume(*args, **kwargs)
        if denial is None:
            raise SystemExit(97)
        return denial


class RevokeAfterSendGate(f3.RecordingGate):
    """Revokes *after* the capability is consumed and the Fake is entered."""

    def __init__(self, path: Path, **kwargs) -> None:
        kwargs.setdefault("auth_epoch", f3.AUTH_EPOCH)
        kwargs.setdefault("authorization_id", AUTHORIZATION_ID)
        kwargs.setdefault("revocation_path", path)
        bindings = same_bindings()
        kwargs.setdefault("binding_approved", bindings)
        kwargs.setdefault("binding_observer", lambda: bindings)
        super().__init__(SYNTHETIC_ROUTE_CONTRACT, **kwargs)
        self.consumed_count = 0

    def consume(self, *args, **kwargs):  # type: ignore[override]
        denial = super().consume(*args, **kwargs)
        if denial is None:
            self.consumed_count += 1
            write_revocation(Path(self.revocation_path), revoked=True,
                             epoch=self.auth_epoch,
                             authorization_id=self.authorization_id,
                             reason="revoke-after-send")
        return denial


def admission_document(*, scenario: str = "ok_usage", deadline_ms: int = 30000,
                       max_calls: int = 8) -> dict:
    document = f3.admission_document(scenario=scenario, max_calls=max_calls)
    document["limits"]["deadline_ms"] = deadline_ms
    return document


def start_controller(tmp_path: Path, *, gate: TrustedSendGate,
                     scenario: str = "ok_usage", deadline_ms: int = 30000,
                     max_calls: int = 8, attempts: AttemptJournal | None = None,
                     broker=None, fake=None, dispatch_journal=None):
    admission_path = tmp_path / "admission.json"
    admission_path.write_text(json.dumps(admission_document(
        scenario=scenario, deadline_ms=deadline_ms, max_calls=max_calls)),
        encoding="utf-8")
    from autoteacher_m0.bridge.admission import load_admission
    admission = load_admission(admission_path, expected_uid=65534)
    broker = broker or f3.start_broker(tmp_path)
    if fake is None:
        from autoteacher_m0.bridge.fake_backend import FakeBackend
        fake = FakeBackend(script=str(f3.FAKE),
                           receipt_dir=str(tmp_path / "receipts"),
                           python=sys.executable, mode=scenario)
    attempts = attempts or AttemptJournal(tmp_path / "attempts.sqlite3")
    controller = TrustedController(admission, broker=broker, fake=fake,
                                   attempts=attempts, expected_uid=65534,
                                   register_admission=False,
                                   dispatch_gate=gate,
                                   dispatch_journal=dispatch_journal)
    return controller, broker, fake, attempts, gate


def second_payload() -> dict:
    return f3.request_payload(
        messages=[{"role": "user", "content": "second business identity"}])
