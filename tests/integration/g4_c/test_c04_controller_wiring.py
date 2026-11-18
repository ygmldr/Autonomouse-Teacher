"""G4-C controller wiring: the gate is optional, and denial precedes the Fake."""
from __future__ import annotations

import inspect
import types

import pytest

from autoteacher_m0.bridge import controller as controller_module
from autoteacher_m0.bridge.controller import BridgeError, TrustedController
from autoteacher_m0.security.egress import (
    ClaimResult,
    EgressViolation,
)
from g4c_support import (
    RESERVATION, claim_digest, make_claim, make_payload, make_prepared,
    make_request,
)


class AttemptsStub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def mark_settlement_uncertain(self, attempt_id, *, reason):
        self.calls.append((attempt_id, reason))


def _controller_stub(gate, attempts=None) -> TrustedController:
    controller = object.__new__(TrustedController)
    controller.dispatch_gate = gate
    controller.attempts = attempts or AttemptsStub()
    controller.send_authorizations = []
    return controller


def _decision(prepared):
    claim = make_claim(prepared)
    return types.SimpleNamespace(
        claim=ClaimResult(True, "CLAIMED", (), claim),
        permission="permission")


def test_c04_controller_main_accepts_an_optional_dispatch_gate() -> None:
    signature = inspect.signature(controller_module.main)
    assert "dispatch_gate" in signature.parameters
    assert signature.parameters["dispatch_gate"].default is None
    init = inspect.signature(TrustedController.__init__)
    assert init.parameters["dispatch_gate"].default is None


def test_c04_gate_denial_is_converted_before_any_provider_call() -> None:
    prepared = make_prepared()
    request = make_request(prepared)

    class DenyingGate:
        def __init__(self):
            self.calls = 0
            self.consumed = 0

        def authorize(self, **kwargs):
            self.calls += 1
            raise EgressViolation(("PAYLOAD_DIGEST_MISMATCH",))

        def consume(self, *args, **kwargs):
            self.consumed += 1
            return "never"

    gate = DenyingGate()
    attempts = AttemptsStub()
    controller = _controller_stub(gate, attempts)
    with pytest.raises(BridgeError) as exc:
        controller._authorize_send(
            prepared=prepared, request=request, decision=_decision(prepared),
            payload_bytes=make_payload(prepared),
            payload_digest=__import__("hashlib").sha256(
                make_payload(prepared)).hexdigest(),
            reservation_id=RESERVATION, attempt_id="attempt-1")
    assert exc.value.code == "EGRESS_DENIED"
    assert gate.calls == 1
    assert gate.consumed == 0
    assert attempts.calls == [("attempt-1", "EGRESS_DENIED:PAYLOAD_DIGEST_MISMATCH")]
    assert controller.send_authorizations == []


def test_c04_invalid_claim_is_denied_before_the_gate() -> None:
    prepared = make_prepared()
    request = make_request(prepared)

    class Gate:
        def __init__(self):
            self.calls = 0

        def authorize(self, **kwargs):
            self.calls += 1
            raise AssertionError("gate must not be called without a claim")

    gate = Gate()
    attempts = AttemptsStub()
    controller = _controller_stub(gate, attempts)
    decision = types.SimpleNamespace(claim=None, permission=None)
    with pytest.raises(BridgeError) as exc:
        controller._authorize_send(
            prepared=prepared, request=request, decision=decision,
            payload_bytes=make_payload(prepared),
            payload_digest="0" * 64, reservation_id=RESERVATION,
            attempt_id="attempt-2")
    assert exc.value.code == "EGRESS_DENIED"
    assert gate.calls == 0
    assert attempts.calls == [("attempt-2", "EGRESS_DENIED:BROKER_CLAIM_INVALID")]


def test_c04_authorized_send_records_audit_binding() -> None:
    prepared = make_prepared()
    request = make_request(prepared)

    class Auth:
        def to_audit_dict(self):
            return {"authorization_id": "send-" + "a" * 32,
                    "call_id": prepared.call_id}

    class AllowGate:
        def authorize(self, **kwargs):
            assert kwargs["payload_length"] == len(make_payload(prepared))
            assert kwargs["broker_claim_digest"] == claim_digest(make_claim(prepared))
            return Auth()

    controller = _controller_stub(AllowGate())
    authorization = controller._authorize_send(
        prepared=prepared, request=request, decision=_decision(prepared),
        payload_bytes=make_payload(prepared),
        payload_digest=__import__("hashlib").sha256(
            make_payload(prepared)).hexdigest(),
        reservation_id=RESERVATION, attempt_id="attempt-3")
    assert isinstance(authorization, Auth)
    assert controller.send_authorizations == [
        {"authorization_id": "send-" + "a" * 32, "call_id": prepared.call_id}]


def test_c04_consume_runs_before_the_fake_is_entered() -> None:
    source = inspect.getsource(controller_module)
    provider = source[source.index("def provider(_req):"):]
    provider = provider[:provider.index("self.transport.dispatch(")]
    consume_at = provider.index("self.dispatch_gate.consume(")
    invoke_at = provider.index("self._invoke_fake(")
    assert consume_at < invoke_at
    assert "raise BridgeError(\"EGRESS_DENIED\")" in provider


def test_c04_gate_is_only_consulted_when_configured() -> None:
    source = inspect.getsource(controller_module)
    provider = source[source.index("def provider(_req):"):]
    provider = provider[:provider.index("self.transport.dispatch(")]
    assert provider.index("if send_authorization is not None:") < \
        provider.index("self.dispatch_gate.consume(")
    # G3-C/G3-D default remains: dispatch_gate defaults to None.
    assert "dispatch_gate=dispatch_gate" in source
