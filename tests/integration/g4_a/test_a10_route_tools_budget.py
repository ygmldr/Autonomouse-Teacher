"""G4-A-10: route/model/tools/budget/deadline mismatches and budget authority drift."""
from __future__ import annotations

import copy
from decimal import Decimal

import pytest

from autoteacher_m0.security.authorization import (
    BUDGET_POLICY_KEYS,
    ApprovedRoute,
    BudgetLimits,
    budget_policy_drift_reasons,
    parse_budget_policy,
)
from autoteacher_m0.security.live_controller import (
    M0_APPROVED_BUDGET_MAX_CALLS,
    M0_APPROVED_BUDGET_PER_CALL_CAP_USD,
    M0_APPROVED_BUDGET_SOFT_CALL_CAP_USD,
    M0_APPROVED_BUDGET_SOFT_TOTAL_CAP_USD,
    M0_APPROVED_BUDGET_TOTAL_CAP_USD,
)
from g4a_support import NOW, ROUTE, SCOPE, base_payload


def _write_payload(trusted, payload: dict) -> None:
    trusted.write_signed(payload)


def _deny_with(trusted, code: str) -> None:
    decision = trusted.load()
    assert decision.approved is False
    assert decision.billable_send_authorized is False
    assert code in decision.reasons, decision.reasons
    assert trusted.use_records() == []


def test_a10_unknown_route_and_model_are_denied(trusted) -> None:
    payload = copy.deepcopy(trusted.payload)
    payload["route"]["model"] = "deepseek-unknown-model"
    _write_payload(trusted, payload)
    _deny_with(trusted, "ROUTE_NOT_APPROVED")

    payload = copy.deepcopy(trusted.payload)
    payload["route"]["route_id"] = "unknown-route"
    _write_payload(trusted, payload)
    _deny_with(trusted, "ROUTE_NOT_APPROVED")

    payload = copy.deepcopy(trusted.payload)
    payload["route"]["provider"] = "unknown-provider"
    _write_payload(trusted, payload)
    _deny_with(trusted, "ROUTE_NOT_APPROVED")


def test_a10_controller_rejects_route_outside_frozen_egress_allowlist(trusted) -> None:
    unknown = ApprovedRoute(route_id="deepseek-official", provider="deepseek-official",
                            model="deepseek-flash")
    payload = copy.deepcopy(trusted.payload)
    payload["route"] = {"route_id": unknown.route_id, "provider": unknown.provider,
                        "model": unknown.model}
    _write_payload(trusted, payload)
    decision = trusted.controller(route=unknown).inspect(now=NOW)
    assert decision.status == "BLOCKED"
    assert decision.authorization_approved is True
    assert "ROUTE_NOT_IN_FROZEN_EGRESS_ALLOWLIST" in decision.reasons, decision.reasons
    assert decision.signature_valid is True
    assert decision.billable_send_authorized is False


def test_a10_tool_registry_changes_are_denied(trusted) -> None:
    assert "ACTUAL_TOOL_REGISTRY_NOT_APPROVED" in trusted.load(
        actual_tools=("skill_lookup", "shell")).reasons
    payload = copy.deepcopy(trusted.payload)
    payload["allowed_tools"] = ["skill_lookup", "shell"]
    _write_payload(trusted, payload)
    _deny_with(trusted, "ALLOWED_TOOLS_NOT_PERMITTED")
    payload["allowed_tools"] = ["skill_lookup", "skill_lookup"]
    _write_payload(trusted, payload)
    _deny_with(trusted, "ALLOWED_TOOLS_INVALID")
    payload["allowed_tools"] = []
    _write_payload(trusted, payload)
    _deny_with(trusted, "ALLOWED_TOOLS_NOT_PERMITTED")


def test_a10_budget_and_scope_mismatches_are_denied(trusted) -> None:
    assert "BUDGET_SCOPE_MISMATCH" in trusted.load(scope="another-scope").reasons
    for budget, code in (
        ({"scope": SCOPE, "per_call_cap_usd": "2.00", "total_cap_usd": "1.00",
          "max_calls": 1}, "PER_CALL_CAP_EXCEEDS_TOTAL_CAP"),
        ({"scope": SCOPE, "per_call_cap_usd": "0.20", "total_cap_usd": "10.01",
          "max_calls": 1}, "TOTAL_CAP_EXCEEDS_HARD_BUDGET"),
    ):
        payload = copy.deepcopy(trusted.payload)
        payload["budget"] = budget
        _write_payload(trusted, payload)
        _deny_with(trusted, code)


def test_a10_deadline_out_of_range_is_denied(trusted) -> None:
    for deadline in (
        {"total_seconds": 0, "max_steps": 8, "max_dispatch_attempts": 8},
        {"total_seconds": 3601, "max_steps": 8, "max_dispatch_attempts": 8},
        {"total_seconds": 60, "max_steps": 201, "max_dispatch_attempts": 8},
        {"total_seconds": 60, "max_steps": 8, "max_dispatch_attempts": 51},
    ):
        payload = copy.deepcopy(trusted.payload)
        payload["deadline"] = deadline
        _write_payload(trusted, payload)
        _deny_with(trusted, "DEADLINE_OUT_OF_RANGE")


def test_a10_authorization_budget_must_match_frozen_constants(trusted) -> None:
    payload = copy.deepcopy(trusted.payload)
    payload["budget"] = {"scope": SCOPE, "per_call_cap_usd": "0.10",
                         "total_cap_usd": "1.00", "max_calls": 10}
    _write_payload(trusted, payload)
    decision = trusted.controller().inspect(now=NOW)
    assert decision.authorization_approved is False
    assert decision.status == "BLOCKED"
    for field in ("per_call_cap_usd", "total_cap_usd", "max_calls"):
        assert f"BUDGET_POLICY_MISMATCH:{field}" in decision.reasons, decision.reasons
    assert decision.signature_valid is True


def test_a10_controller_expected_budget_must_be_m0_policy(trusted) -> None:
    expected = BudgetLimits(SCOPE, Decimal("0.20"), Decimal("5.00"), 50)
    decision = trusted.controller(expected_budget=expected).inspect(now=NOW)
    assert decision.authorization_approved is False
    assert "CONTROLLER_BUDGET_NOT_M0_POLICY" in decision.reasons
    assert "BUDGET_POLICY_MISMATCH:total_cap_usd" in decision.reasons


def test_a10_budget_policy_file_matches_frozen_constants(trusted) -> None:
    raw = (trusted.repo / "config" / "budgets.yaml").read_bytes()
    policy = parse_budget_policy(raw)
    assert tuple(policy) == BUDGET_POLICY_KEYS
    limits = BudgetLimits(SCOPE, M0_APPROVED_BUDGET_PER_CALL_CAP_USD,
                          M0_APPROVED_BUDGET_TOTAL_CAP_USD, M0_APPROVED_BUDGET_MAX_CALLS)
    reasons = budget_policy_drift_reasons(
        policy, expected=limits, soft_call_cap_usd=M0_APPROVED_BUDGET_SOFT_CALL_CAP_USD,
        soft_total_cap_usd=M0_APPROVED_BUDGET_SOFT_TOTAL_CAP_USD)
    assert reasons == ("LIVE_PRICING_SNAPSHOT_UNVERIFIED",)
    decision = trusted.controller().inspect(now=NOW)
    assert "BUDGET_POLICY_DRIFT:hard_call_usd" not in decision.reasons
    assert "LIVE_PRICING_SNAPSHOT_UNVERIFIED" in decision.reasons


@pytest.mark.parametrize("old,new,code", [
    ("hard_call_usd: 0.20", "hard_call_usd: 0.25", "BUDGET_POLICY_DRIFT:hard_call_usd"),
    ("hard_total_usd: 10.0", "hard_total_usd: 11.0", "BUDGET_POLICY_DRIFT:hard_total_usd"),
    ("soft_total_usd: 3.0", "soft_total_usd: 5.0", "BUDGET_POLICY_DRIFT:soft_total_usd"),
    ("soft_call_usd: 0.10", "soft_call_usd: 0.30", "BUDGET_POLICY_DRIFT:soft_call_usd"),
    ("max_live_requests: 50", "max_live_requests: 49",
     "BUDGET_POLICY_DRIFT:max_live_requests"),
    ("max_live_requests: 50", "max_live_requests: 50.0",
     "BUDGET_POLICY_VALUE_INVALID:max_live_requests"),
])
def test_a10_budget_policy_drift_is_reported(trusted, old: str, new: str, code: str) -> None:
    path = trusted.repo / "config" / "budgets.yaml"
    text = path.read_text(encoding="utf-8")
    assert old in text
    trusted.rewrite("config/budgets.yaml", text.replace(old, new).encode("utf-8"))
    decision = trusted.controller().inspect(now=NOW)
    assert code in decision.reasons, decision.reasons
    assert decision.status == "BLOCKED"
    assert decision.billable_send_authorized is False


@pytest.mark.parametrize("mutation,code", [
    (lambda text: text + "unknown_policy: 1\n", "BUDGET_POLICY_FILE_INVALID"),
    (lambda text: text.replace("max_retries_per_task: 1\n", ""),
     "BUDGET_POLICY_FILE_INVALID"),
    (lambda text: text + "hard_call_usd: 0.20\n", "BUDGET_POLICY_FILE_INVALID"),
    (lambda text: text.replace("live_pricing_snapshot: REQUIRED_UNVERIFIED",
                               "live_pricing_snapshot: " + "a" * 64),
     "BUDGET_POLICY_PRICE_SNAPSHOT_UNSUPPORTED"),
])
def test_a10_budget_policy_parse_failures_fail_closed(trusted, mutation, code: str) -> None:
    path = trusted.repo / "config" / "budgets.yaml"
    text = path.read_text(encoding="utf-8")
    mutated = mutation(text)
    assert mutated != text
    trusted.rewrite("config/budgets.yaml", mutated.encode("utf-8"))
    decision = trusted.controller().inspect(now=NOW)
    assert any(reason.startswith(code) for reason in decision.reasons), decision.reasons
    assert decision.status == "BLOCKED"


def test_a10_budget_policy_symlink_and_missing_file(trusted) -> None:
    path = trusted.repo / "config" / "budgets.yaml"
    backup = path.read_bytes()
    path.unlink()
    path.symlink_to(trusted.repo / "config" / "models.example.yaml")
    try:
        assert "BUDGET_POLICY_FILE_SYMLINKED" in trusted.controller().inspect(now=NOW).reasons
    finally:
        path.unlink()
        path.write_bytes(backup)
    path.unlink()
    try:
        assert "BUDGET_POLICY_FILE_UNREADABLE" in trusted.controller().inspect(now=NOW).reasons
    finally:
        path.write_bytes(backup)
    assert "BUDGET_POLICY_DRIFT:hard_call_usd" not in trusted.controller().inspect(now=NOW).reasons


def test_a10_budget_policy_is_part_of_the_signed_closure(trusted) -> None:
    path = trusted.repo / "config" / "budgets.yaml"
    trusted.rewrite("config/budgets.yaml", path.read_bytes() + b"\n# drift\n")
    recomputed = trusted.compute_now()
    assert recomputed.merged_profile_sha256 != trusted.bindings.merged_profile_sha256
    decision = trusted.controller().inspect(now=NOW, observed=recomputed)
    assert "BINDING_DRIFT:PRE_START:MERGED_PROFILE_SHA256_MISMATCH" in decision.reasons


def test_a10_payload_route_matches_frozen_route_fixture(trusted) -> None:
    assert ROUTE["route_id"] == "opencode-go"
    assert "opencode-go" in (trusted.repo / "config" / "dsh" /
                             "target-runtime-opencode-go.patch.yml").read_text(
        encoding="utf-8")
    assert base_payload(trusted.bindings.as_dict())["budget"]["scope"] == SCOPE
