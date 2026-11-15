"""Composition of the trusted Live Controller; intentionally has no run path.

The controller can *inspect* a prospective execution (authorization, candidate
command, credential/mount/egress policy, gate state) and always returns
``BLOCKED`` until a separately deployed human authorization boundary, credential
broker/egress proxy and external watchdog exist. There is deliberately no method
that launches a model, SDK, candidate container or billable request.

This is PR3 design code; completing PR3 does not approve Live and cannot change
``LiveGate``, ``scripts/run_live.sh`` or the Runtime adapter's blocked entries.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from autoteacher_m0.contracts import ErrorCode, RuntimeFailure

from .authorization import (
    ApprovedRoute,
    AuthorizationDecision,
    BudgetLimits,
    ExpectedBindings,
    load_execution_authorization,
)
from .credential_boundary import (
    LauncherOnlySecret,
    assert_candidate_env_clean,
    validate_candidate_argv,
    validate_candidate_mounts,
)
from .docker_runner import ContainerRunner
from .egress import EgressPolicy
from .gates import LiveGate, SecurityBlocked
from .watchdog import WatchdogPolicy

EXPECTED_EGRESS_POLICY = EgressPolicy()

# Aligned with the approved M0 policy in config/budgets.yaml:
#   hard_call_usd=0.20, hard_total_usd=10.0, max_live_requests=50
# (v0.6 §9.5: US$3 soft / US$10 hard / <=50 calls). These are fixed policy
# inputs, never taken from the candidate authorization itself.
M0_APPROVED_BUDGET_PER_CALL_CAP_USD = Decimal("0.20")
M0_APPROVED_BUDGET_TOTAL_CAP_USD = Decimal("10.00")
M0_APPROVED_BUDGET_MAX_CALLS = 50
BUDGET_POLICY_FIELDS = ("scope", "per_call_cap_usd", "total_cap_usd", "max_calls")

EGRESS_POLICY_FIELDS = (
    "host_ports", "methods", "path_prefix", "approved_routes", "max_tokens",
    "max_attempts", "require_reservation", "allow_files", "allow_images", "allow_store",
)

ALWAYS_BLOCKED_REASONS = (
    "EXTERNAL_HUMAN_AUTHORIZATION_BOUNDARY_NOT_DEPLOYED",
    "EXTERNAL_CREDENTIAL_BROKER_NOT_DEPLOYED",
    "EXTERNAL_EGRESS_PROXY_NOT_DEPLOYED",
    "EXTERNAL_WATCHDOG_NOT_DEPLOYED_REHEARSAL_ONLY",
    "LIVE_GATE_CLOSED",
)


@dataclass(frozen=True)
class ControllerDecision:
    status: str
    reasons: tuple[str, ...]
    authorization_approved: bool
    gate_status: str
    candidate_command_checked: bool
    candidate_credentials_checked: bool
    boundary_deployed: bool = False


class TrustedLiveController:
    """Inspection-only composition; never provides an execution/approval method."""

    def __init__(self, *, repo_root: Path, authorization_path: Path,
                 trusted_keys_path: Path, revocation_path: Path,
                 expected: ExpectedBindings, approved_route: ApprovedRoute,
                 actual_tools: tuple[str, ...], budget_scope: str,
                 candidate_stage: Path, candidate_engine: str = "podman",
                 image: str = "localhost/autoteacher-local-oci@sha256:"
                 "62d3569ec38e27ed16fa3147515c1c78d993bb7df831cc1fe29811f3fe64667b",
                 launcher_secret: LauncherOnlySecret | None = None,
                 egress: EgressPolicy | None = None,
                 expected_budget: BudgetLimits | None = None,
                 watchdog_policy: WatchdogPolicy | None = None) -> None:
        if not candidate_stage.is_dir():
            raise ValueError("candidate stage must be a controller-created directory")
        self.repo_root = repo_root
        self.authorization_path = authorization_path
        self.trusted_keys_path = trusted_keys_path
        self.revocation_path = revocation_path
        self.expected = expected
        self.approved_route = approved_route
        self.actual_tools = tuple(actual_tools)
        self.budget_scope = budget_scope
        self.candidate_stage = candidate_stage
        self.candidate_engine = candidate_engine
        self.image = image
        self.launcher_secret = launcher_secret
        self.egress = egress or EgressPolicy()
        self.expected_budget = expected_budget or BudgetLimits(
            budget_scope,
            M0_APPROVED_BUDGET_PER_CALL_CAP_USD,
            M0_APPROVED_BUDGET_TOTAL_CAP_USD,
            M0_APPROVED_BUDGET_MAX_CALLS,
        )
        self.watchdog_policy = watchdog_policy or WatchdogPolicy()

    def authorization_decision(self, *, now: datetime | None = None
                                ) -> AuthorizationDecision:
        decision = load_execution_authorization(
            authorization_path=self.authorization_path,
            trusted_keys_path=self.trusted_keys_path,
            revocation_path=self.revocation_path,
            repo_root=self.repo_root,
            expected=self.expected,
            approved_route=self.approved_route,
            actual_tools=self.actual_tools,
            budget_scope=self.budget_scope,
            now=now,
        )
        if decision.authorization is None:
            return decision
        mismatches = tuple(
            f"BUDGET_POLICY_MISMATCH:{field}"
            for field in BUDGET_POLICY_FIELDS
            if getattr(decision.authorization.budget, field)
            != getattr(self.expected_budget, field)
        )
        if not mismatches:
            return decision
        # A validly signed authorization for different budget caps is still a
        # policy violation: deny it explicitly instead of relying on the
        # controller's generic BLOCKED state.
        return AuthorizationDecision(False, decision.reasons + mismatches, None)

    def candidate_command(self) -> list[str]:
        return ContainerRunner(image=self.image, engine=self.candidate_engine).command(
            stage=self.candidate_stage, name="at-m0-live-candidate")

    def _candidate_violations(self) -> tuple[str, ...]:
        command = self.candidate_command()
        mounts = [command[index + 1] for index, token in enumerate(command)
                  if token == "--mount" and index + 1 < len(command)]
        reasons = list(validate_candidate_argv(command))
        reasons += list(validate_candidate_mounts(
            mounts, allowed_stage_root=self.candidate_stage.parent))
        if self.launcher_secret is not None:
            # The candidate command carries no --env from the launcher; assert it
            # cannot leak the secret and that a secret-free env still passes.
            assert_candidate_env_clean(
                {"PATH": "/opt/python/bin:/usr/bin", "HOME": "/work"},
                known_secrets=[self.launcher_secret.for_launcher_env()[
                    self.launcher_secret.env_name]])
            if self.launcher_secret.env_name in " ".join(command):
                reasons.append("LAUNCHER_SECRET_NAME_IN_CANDIDATE_COMMAND")
            if self.launcher_secret.for_launcher_env()[self.launcher_secret.env_name] in " ".join(command):
                reasons.append("LAUNCHER_SECRET_VALUE_IN_CANDIDATE_COMMAND")
        for field in EGRESS_POLICY_FIELDS:
            if getattr(self.egress, field) != getattr(EXPECTED_EGRESS_POLICY, field):
                reasons.append(f"EGRESS_POLICY_FIELD_MISMATCH:{field}")
        return tuple(dict.fromkeys(reasons))

    def inspect(self, *, now: datetime | None = None) -> ControllerDecision:
        """Always BLOCKED; reports every currently missing external prerequisite."""
        authorization = self.authorization_decision(now=now)
        reasons = list(authorization.reasons)
        gate = LiveGate().inspect(live_requested=True, actual=None, reviewed=None,
                                  actual_tools=self.actual_tools,
                                  session_log_disabled=False)
        reasons.extend(gate.reasons)
        candidate_reasons = self._candidate_violations()
        reasons.extend(candidate_reasons)
        reasons.extend(ALWAYS_BLOCKED_REASONS)
        return ControllerDecision(
            status="BLOCKED",
            reasons=tuple(dict.fromkeys(reasons)),
            authorization_approved=authorization.approved,
            gate_status=gate.status,
            candidate_command_checked=not candidate_reasons,
            candidate_credentials_checked=not candidate_reasons,
            boundary_deployed=False,
        )

    def require_live(self, *, now: datetime | None = None) -> None:
        decision = self.inspect(now=now)
        raise SecurityBlocked("; ".join(decision.reasons) or "LIVE_CONTROLLER_BLOCKED")


def assert_live_entrypoints_blocked(repo_root: Path) -> tuple[str, ...]:
    """Read-only audit of the known Live entries; returns blocking reasons.

    Callers must also execute the actual CLI/script/adapter negatives (done by
    the integration test inside the locked OCI container). This function never
    imports or calls the SDK and never inspects a credential.
    """
    reasons: list[str] = []
    script = repo_root / "scripts" / "run_live.sh"
    adapter = repo_root / "src" / "autoteacher_m0" / "runtime" / "dsh_adapter.py"
    cli = repo_root / "src" / "autoteacher_m0" / "cli.py"
    if not script.is_file() or "exit 3" not in script.read_text(encoding="utf-8"):
        reasons.append("RUN_LIVE_SCRIPT_NOT_HARD_STOPPED")
    text = adapter.read_text(encoding="utf-8") if adapter.is_file() else ""
    if "_require_live_authorization" not in text or "SECURITY_BLOCKED" not in text:
        reasons.append("RUNTIME_ADAPTER_LIVE_ENTRY_NOT_BLOCKED")
    cli_text = cli.read_text(encoding="utf-8") if cli.is_file() else ""
    if "LiveGate().require_live" not in cli_text:
        reasons.append("CLI_LIVE_FLAG_NOT_GATED_BEFORE_EXECUTION")
    gate = LiveGate()
    if gate.inspect(live_requested=True, actual_tools=("skill_lookup",),
                    session_log_disabled=False).status != "BLOCKED":
        raise RuntimeFailure(ErrorCode.SECURITY_BLOCKED, "LiveGate unexpectedly open")
    return tuple(reasons)
