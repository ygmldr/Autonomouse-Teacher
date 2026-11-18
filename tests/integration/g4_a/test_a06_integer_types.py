"""G4-A-06: bool/float/string counts and limits are never coerced to integers."""
from __future__ import annotations

import copy

import pytest

from g4a_support import base_payload


@pytest.mark.parametrize("field,bad", [
    ("max_calls", True),
    ("max_calls", False),
    ("max_calls", 10.0),
    ("max_calls", 10.5),
    ("max_calls", "10"),
    ("max_calls", None),
    ("max_calls", [10]),
    ("max_calls", {"value": 10}),
])
def test_a06_budget_max_calls_is_a_strict_json_integer(trusted, field: str, bad) -> None:
    payload = copy.deepcopy(trusted.payload)
    payload["budget"][field] = bad
    trusted.write_signed(payload)
    decision = trusted.load()
    assert decision.approved is False
    assert "BUDGET_VALUES_INVALID" in decision.reasons, decision.reasons
    assert trusted.use_records() == []


@pytest.mark.parametrize("field,bad", [
    ("total_seconds", True),
    ("total_seconds", 120.0),
    ("total_seconds", "120"),
    ("total_seconds", None),
    ("max_steps", False),
    ("max_steps", 8.5),
    ("max_steps", "8"),
    ("max_dispatch_attempts", True),
    ("max_dispatch_attempts", 8.0),
    ("max_dispatch_attempts", "8"),
])
def test_a06_deadline_values_are_strict_integers(trusted, field: str, bad) -> None:
    payload = copy.deepcopy(trusted.payload)
    payload["deadline"][field] = bad
    trusted.write_signed(payload)
    decision = trusted.load()
    assert decision.approved is False
    assert "DEADLINE_VALUES_INVALID" in decision.reasons, decision.reasons
    assert trusted.use_records() == []


@pytest.mark.parametrize("bad", [0.20, 0.1, True, None, 3, " 0.20", "0.2e1", "-1",
                                 "0", "10.0000001", "+0.20", "0.2000001"])
def test_a06_budget_usd_accepts_only_plain_decimal_strings(trusted, bad) -> None:
    payload = copy.deepcopy(trusted.payload)
    payload["budget"]["per_call_cap_usd"] = bad
    trusted.write_signed(payload)
    decision = trusted.load()
    assert decision.approved is False
    assert "BUDGET_VALUES_INVALID" in decision.reasons, decision.reasons


def test_a06_out_of_range_counts_are_rejected(trusted) -> None:
    for max_calls, reason in ((0, "MAX_CALLS_OUT_OF_RANGE"),
                              (51, "MAX_CALLS_OUT_OF_RANGE"),
                              (-1, "MAX_CALLS_OUT_OF_RANGE")):
        payload = copy.deepcopy(trusted.payload)
        payload["budget"]["max_calls"] = max_calls
        trusted.write_signed(payload)
        decision = trusted.load()
        assert reason in decision.reasons, decision.reasons
    for total_seconds, reason in ((0, "DEADLINE_OUT_OF_RANGE"),
                                  (3601, "DEADLINE_OUT_OF_RANGE")):
        payload = copy.deepcopy(trusted.payload)
        payload["deadline"]["total_seconds"] = total_seconds
        trusted.write_signed(payload)
        decision = trusted.load()
        assert reason in decision.reasons, decision.reasons


def test_a06_approved_strict_payload_is_the_control(trusted) -> None:
    decision = trusted.load()
    assert decision.approved is True
    assert decision.signature_valid is True
    assert base_payload(trusted.bindings.as_dict())["budget"]["max_calls"] == 50
