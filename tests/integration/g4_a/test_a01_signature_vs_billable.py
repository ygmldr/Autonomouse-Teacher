"""G4-A-01: a valid synthetic signature is not a billable-send permission.

The verifier may accept the synthetic document (``signature_valid=True``) while
``billable_send_authorized`` stays false and every Live entry stays BLOCKED.
"""
from __future__ import annotations

import json
import subprocess
import sys

import pytest

from autoteacher_m0.contracts import RuntimeFailure
from autoteacher_m0.security.authorization import AuthorizationDecision
from autoteacher_m0.security.gates import LiveGate
from autoteacher_m0.security.live_controller import (
    ALWAYS_BLOCKED_REASONS,
    ControllerDecision,
    TrustedLiveController,
    assert_live_entrypoints_blocked,
)
from g4a_support import NOW, REPO_ROOT, clean_subprocess_env


def test_a01_signature_validity_is_separate_from_billable_dispatch(trusted) -> None:
    decision = trusted.load()
    assert decision.approved is True, decision.reasons
    assert decision.signature_valid is True
    assert decision.billable_send_authorized is False
    authorization = decision.require()
    assert authorization.allowed_tools == ("skill_lookup",)
    assert authorization.budget.max_calls == 50
    # The verified payload carries no private key / seed material.
    assert b"5a5a5a5a" not in authorization.payload_bytes
    assert b"seed" not in authorization.payload_bytes.lower()
    # Inspection never consumes the single authorization use.
    assert trusted.use_records() == []


def test_a01_controller_reports_split_and_cannot_run(trusted) -> None:
    controller = trusted.controller()
    decision = controller.inspect(now=NOW)
    assert decision.status == "BLOCKED"
    assert decision.authorization_approved is True
    assert decision.signature_valid is True
    assert decision.billable_send_authorized is False
    assert decision.boundary_deployed is False
    assert decision.gate_status == "BLOCKED"
    for reason in ALWAYS_BLOCKED_REASONS:
        assert reason in decision.reasons
    for attribute in ("run", "dispatch", "send", "execute", "approve", "sign"):
        assert not hasattr(controller, attribute)
    with pytest.raises(Exception) as raised:
        controller.require_live()
    assert "EXTERNAL" in str(raised.value) or "BLOCKED" in str(raised.value)


def test_a01_flags_are_immune_to_construction() -> None:
    with pytest.raises(ValueError):
        AuthorizationDecision(True, (), None, True, True)
    with pytest.raises(ValueError):
        ControllerDecision("BLOCKED", (), True, "BLOCKED", True, True,
                           False, True, True)


def test_a01_live_gate_cli_adapter_and_script_stay_blocked(trusted) -> None:
    gate = LiveGate().inspect(live_requested=True)
    assert gate.status == "BLOCKED"
    assert "EXTERNAL_HUMAN_AUTHORIZATION_BOUNDARY_NOT_DEPLOYED" in gate.reasons
    assert gate.external_boundary_deployed is False

    completed = subprocess.run(
        [sys.executable, "-B", "-c",
         "from autoteacher_m0.cli import main; "
         "raise SystemExit(main(['smoke', '--live']))"],
        env=clean_subprocess_env(), stdin=subprocess.DEVNULL, capture_output=True,
        timeout=60, check=False)
    assert completed.returncode == 3, completed.stderr.decode(errors="replace")
    payload = json.loads(completed.stdout.decode())
    assert payload["status"] == "BLOCKED"
    assert payload["error_code"] == "SECURITY_BLOCKED"

    script = subprocess.run(["/bin/sh", str(REPO_ROOT / "scripts" / "run_live.sh")],
                            env=clean_subprocess_env(), stdin=subprocess.DEVNULL,
                            capture_output=True, timeout=60, check=False)
    assert script.returncode == 3
    assert "BLOCKED" in script.stderr.decode()
    assert "SECURITY_BLOCKED" in script.stderr.decode()

    from autoteacher_m0.runtime.dsh_adapter import HarnessAdapter
    with pytest.raises(RuntimeFailure) as raised:
        HarnessAdapter._require_live_authorization()
    assert raised.value.code == "SECURITY_BLOCKED"
    assert "deepseek_harness" not in sys.modules
    # The static audit is auxiliary evidence only; it agrees with the behaviour.
    assert assert_live_entrypoints_blocked(REPO_ROOT) == ()


def test_a01_real_dispatch_counters_are_zero(trusted) -> None:
    """No dispatch counter exists: the only state a verification can create is a
    single-use consumption record, and inspection creates none."""
    trusted.controller().inspect(now=NOW)
    trusted.load()
    assert trusted.use_records() == []
    assert TrustedLiveController.__module__.endswith("live_controller")
    source = (REPO_ROOT / "src" / "autoteacher_m0" / "security" / "live_controller.py")
    text = source.read_text(encoding="utf-8")
    for marker in ("def run(", "subprocess.Popen", "deepseek_harness", "socket."):
        assert marker not in text
