"""G4-A-13: runtime mutation after approval is caught at start/Reserve/Dispatch."""
from __future__ import annotations

import pytest

from autoteacher_m0.security.authorization import (
    TOCTOU_CHECKPOINTS,
    AuthorizationRejected,
    ExpectedBindings,
    binding_drift,
)
from g4a_support import NOW


def _drifted(trusted) -> ExpectedBindings:
    trusted.rewrite("src/autoteacher_m0/security/live_controller.py",
                    b"# unapproved mutation after approval\n")
    return trusted.compute_now()


def test_a13_exactly_three_checkpoints_are_required() -> None:
    assert TOCTOU_CHECKPOINTS == ("pre_start", "pre_reserve", "pre_dispatch")


@pytest.mark.parametrize("checkpoint", TOCTOU_CHECKPOINTS)
def test_a13_drift_is_reported_at_every_checkpoint(trusted, checkpoint: str) -> None:
    observed = _drifted(trusted)
    reasons = binding_drift(checkpoint, approved=trusted.bindings, observed=observed)
    assert reasons == (f"BINDING_DRIFT:{checkpoint.upper()}:CODE_SHA256_MISMATCH",)


@pytest.mark.parametrize("checkpoint", TOCTOU_CHECKPOINTS)
def test_a13_no_drift_is_silent(trusted, checkpoint: str) -> None:
    assert binding_drift(checkpoint, approved=trusted.bindings,
                         observed=trusted.bindings) == ()


def test_a13_invalid_checkpoint_or_types_are_rejected(trusted) -> None:
    with pytest.raises(ValueError):
        binding_drift("after_send", approved=trusted.bindings, observed=trusted.bindings)
    with pytest.raises(TypeError):
        binding_drift("pre_start", approved=trusted.bindings, observed=None)  # type: ignore[arg-type]


def test_a13_controller_exposes_checkpoint_and_marks_drift(trusted) -> None:
    controller = trusted.controller()
    assert controller.binding_checkpoint(
        "pre_dispatch", observed=trusted.bindings) == ()
    observed = _drifted(trusted)
    assert controller.binding_checkpoint("pre_reserve", observed=observed) == (
        "BINDING_DRIFT:PRE_RESERVE:CODE_SHA256_MISMATCH",)
    decision = controller.inspect(now=NOW, observed=observed)
    assert decision.status == "BLOCKED"
    assert "BINDING_DRIFT:PRE_START:CODE_SHA256_MISMATCH" in decision.reasons
    assert decision.signature_valid is True
    assert decision.billable_send_authorized is False


def test_a13_sequence_start_reserve_then_mutate_before_dispatch(trusted) -> None:
    controller = trusted.controller()
    approved = trusted.compute_now()
    # pre_start and pre_reserve observe the approved closure ...
    assert controller.binding_checkpoint("pre_start", observed=approved) == ()
    assert controller.binding_checkpoint("pre_reserve", observed=approved) == ()
    # ... then an unapproved edit happens while the run is in flight.
    observed = _drifted(trusted)
    dispatch_reasons = controller.binding_checkpoint("pre_dispatch", observed=observed)
    assert dispatch_reasons == ("BINDING_DRIFT:PRE_DISPATCH:CODE_SHA256_MISMATCH",)
    # A failed dispatch checkpoint is a hard deny, never a retry with new bytes.
    assert any(reason.startswith("BINDING_DRIFT:PRE_DISPATCH:")
               for reason in dispatch_reasons)


def test_a13_mutation_before_reserve_blocks_consumption(trusted) -> None:
    observed = _drifted(trusted)
    with pytest.raises(AuthorizationRejected) as error:
        trusted.consume(observed=observed)
    assert "BINDING_DRIFT:PRE_RESERVE:CODE_SHA256_MISMATCH" in error.value.reasons, \
        error.value.reasons
    assert trusted.use_records() == []


def test_a13_drift_of_any_root_blocks_new_dispatch(trusted) -> None:
    for component, root in (
        ("budget_policy", "merged_profile_sha256"),
        ("plugin_tree", "plugin_sha256"),
        ("runtime_dependencies", "lock_sha256"),
        ("candidate_stage", "runtime_sha256"),
    ):
        mutated = dict(trusted.components)
        mutated[component] = "d" * 64
        observed = ExpectedBindings.from_closure(mutated)
        reasons = binding_drift("pre_dispatch", approved=trusted.bindings, observed=observed)
        assert reasons == (f"BINDING_DRIFT:PRE_DISPATCH:{root.upper()}_MISMATCH",)
        assert trusted.bindings.mismatches(observed) == (f"{root.upper()}_MISMATCH",)


def test_a13_mutation_never_creates_a_use_record(trusted) -> None:
    _drifted(trusted)
    with pytest.raises(AuthorizationRejected):
        trusted.consume(observed=trusted.compute_now(), now=NOW)
    assert trusted.use_records() == []
