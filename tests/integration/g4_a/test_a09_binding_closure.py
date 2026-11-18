"""G4-A-09: the five v1 roots bind a complete runtime input closure, drift denies.

The authorization document keeps exactly the existing ``ExpectedBindings``
fields; the closure defines which runtime inputs aggregate into each root.
"""
from __future__ import annotations

import copy

import pytest

from autoteacher_m0.security.authorization import (
    BINDING_CLOSURE,
    BINDING_COMPONENTS,
    BINDING_NAMES,
    ExpectedBindings,
    closure_digests,
    inventory_digest,
)
from g4a_support import COMPONENT_FILES, NOW, SYNTHETIC_COMPONENTS


def test_a09_closure_is_complete_and_disjoint() -> None:
    assert set(BINDING_CLOSURE) == set(BINDING_NAMES)
    assert len(BINDING_COMPONENTS) == len(set(BINDING_COMPONENTS)) == 15
    seen = [component for root in BINDING_NAMES for component in BINDING_CLOSURE[root]]
    assert sorted(seen) == sorted(BINDING_COMPONENTS)
    assert set(COMPONENT_FILES) | set(SYNTHETIC_COMPONENTS) == set(BINDING_COMPONENTS)
    required = {
        "trusted_controller", "trusted_broker", "egress_boundary", "candidate_adapter",
        "security_primitives", "dependency_lock", "runtime_dependencies", "runtime_binary",
        "plugin_tree", "tool_registry_schema", "merged_profile", "route_policy",
        "budget_policy", "price_snapshot", "candidate_stage",
    }
    assert set(BINDING_COMPONENTS) == required
    flattened = {relative for entries in COMPONENT_FILES.values() for relative in entries}
    for relative in (
        "src/autoteacher_m0/security/authorization.py",
        "src/autoteacher_m0/security/ed25519.py",
        "src/autoteacher_m0/security/gates.py",
        "src/autoteacher_m0/security/live_controller.py",
        "src/autoteacher_m0/security/credential_boundary.py",
        "src/autoteacher_m0/security/watchdog.py",
        "src/autoteacher_m0/security/egress.py",
        "src/autoteacher_m0/cli.py",
        "src/autoteacher_m0/runtime/dsh_adapter.py",
        "src/autoteacher_m0/bridge/controller.py",
        "src/autoteacher_m0/accounting/broker.py",
        "config/budgets.yaml",
    ):
        assert relative in flattened, relative


def test_a09_partial_or_extra_inventory_is_rejected(trusted) -> None:
    components = dict(trusted.components)
    missing = dict(components)
    missing.pop("budget_policy")
    with pytest.raises(ValueError, match="missing"):
        closure_digests(missing)
    extra = dict(components)
    extra["agent_chosen_extra"] = "a" * 64
    with pytest.raises(ValueError, match="extra"):
        closure_digests(extra)
    invalid = dict(components)
    invalid["route_policy"] = "not-a-digest"
    with pytest.raises(ValueError):
        closure_digests(invalid)
    with pytest.raises(TypeError):
        closure_digests(["not", "a", "mapping"])  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        ExpectedBindings.from_closure(missing)


def test_a09_each_component_changes_exactly_its_root(trusted) -> None:
    baseline = trusted.bindings.as_dict()
    for component in BINDING_COMPONENTS:
        mutated = dict(trusted.components)
        mutated[component] = "f" * 64
        roots = closure_digests(mutated)
        changed = {root for root in BINDING_NAMES if roots[root] != baseline[root]}
        expected_root = next(root for root in BINDING_NAMES
                             if component in BINDING_CLOSURE[root])
        assert changed == {expected_root}, (component, changed)
        observed = ExpectedBindings(**roots)
        assert trusted.bindings.mismatches(observed) == (
            f"{expected_root.upper()}_MISMATCH",)


def test_a09_signed_authorization_with_drifted_root_denies(trusted) -> None:
    baseline = trusted.bindings.as_dict()
    for root in BINDING_NAMES:
        component = BINDING_CLOSURE[root][0]
        mutated = dict(trusted.components)
        mutated[component] = "e" * 64
        drifted = ExpectedBindings.from_closure(mutated)
        payload = copy.deepcopy(trusted.payload)
        payload["bindings"] = drifted.as_dict()
        trusted.write_signed(payload)
        decision = trusted.load()
        assert decision.approved is False, root
        assert decision.signature_valid is True
        assert f"{root.upper()}_MISMATCH" in decision.reasons, decision.reasons
        assert trusted.use_records() == []
        assert drifted.as_dict() != baseline
    trusted.write_signed(trusted.payload)
    assert trusted.load().approved is True


def test_a09_repo_file_drift_changes_component_and_is_reported(trusted) -> None:
    relative = "src/autoteacher_m0/security/authorization.py"
    original = (trusted.repo / relative).read_bytes()
    trusted.rewrite(relative, original + b"\n# unapproved drift\n")
    recomputed = trusted.recompute()
    assert recomputed != trusted.bindings
    assert recomputed.code_sha256 != trusted.bindings.code_sha256
    controller = trusted.controller()
    decision = controller.inspect(now=NOW, observed=recomputed)
    assert decision.status == "BLOCKED"
    assert "BINDING_DRIFT:PRE_START:CODE_SHA256_MISMATCH" in decision.reasons, decision.reasons
    assert decision.signature_valid is True
    # The signed document itself still verifies, but the drift denies the decision.
    assert decision.authorization_approved is False
    # Rewriting the file back restores the approved closure.
    trusted.rewrite(relative, original)
    assert trusted.recompute() == trusted.bindings
    assert controller.inspect(now=NOW, observed=trusted.compute_now()).reasons.count(
        "BINDING_DRIFT:PRE_START:CODE_SHA256_MISMATCH") == 0


def test_a09_inventory_digest_is_deterministic_and_path_strict() -> None:
    files = {"b.py": b"beta", "a.py": b"alpha"}
    assert inventory_digest(files) == inventory_digest({"a.py": b"alpha", "b.py": b"beta"})
    assert inventory_digest(files) != inventory_digest({"a.py": b"alpha", "b.py": b"BETA"})
    with pytest.raises(ValueError):
        inventory_digest({"/etc/passwd": b"x"})
    with pytest.raises(ValueError):
        inventory_digest({"../escape": b"x"})
    with pytest.raises(ValueError):
        inventory_digest({"a\\b": b"x"})
    with pytest.raises(ValueError):
        inventory_digest({})
    with pytest.raises(TypeError):
        inventory_digest({"a.py": "text"})  # type: ignore[dict-item]
