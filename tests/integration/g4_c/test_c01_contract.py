"""G4-C contract freeze: ProviderRouteContract field semantics and fail-closed parsing."""
from __future__ import annotations

from dataclasses import replace

import pytest

from autoteacher_m0.security.egress import (
    ACTIVATION_BLOCKED,
    G4C_CONTRACT_SCHEMA,
    REAL_ROUTE_TEMPLATE,
    ROUTE_KIND_REAL,
    SKILL_LOOKUP_SCHEMA_DIGEST,
    SYNTHETIC_ROUTE_CONTRACT,
    ProviderRouteContract,
    tool_schema_digest,
)
from g4c_support import approved_tool


def test_c01_synthetic_route_is_active_and_complete() -> None:
    contract = SYNTHETIC_ROUTE_CONTRACT
    assert contract.contract_problems() == ()
    assert contract.send_problems() == ()
    assert contract.route_kind == "synthetic_fixture"
    assert contract.activation == "ACTIVE_SYNTHETIC_ONLY"
    assert contract.retry_policy == "no_retry"
    assert contract.endpoint_host == "g3b-fake.local"
    assert contract.port == 9000
    assert contract.method == "POST"
    assert contract.exact_path == "/v1/g3b/chat"
    assert contract.max_output_tokens == 1024
    assert contract.allowed_tool_schema_digests == frozenset({SKILL_LOOKUP_SCHEMA_DIGEST})
    assert tool_schema_digest(approved_tool()) == SKILL_LOOKUP_SCHEMA_DIGEST


def test_c01_real_route_is_blocked_and_has_no_endpoint() -> None:
    contract = REAL_ROUTE_TEMPLATE
    assert contract.route_kind == ROUTE_KIND_REAL
    assert contract.activation == ACTIVATION_BLOCKED
    assert contract.endpoint_host is None and contract.port is None
    assert contract.exact_path is None
    assert contract.price_source == "REQUIRES_VERIFICATION"
    assert contract.contract_problems() == ()
    reasons = contract.send_problems()
    assert "REAL_ROUTE_BLOCKED_REQUIRES_HUMAN_VERIFICATION" in reasons
    assert "ROUTE_ACTIVATION_NOT_SYNTHETIC_ONLY" in reasons
    assert "PRICING_SOURCE_UNVERIFIED" in reasons


def test_c01_mapping_round_trip_is_exact() -> None:
    mapping = SYNTHETIC_ROUTE_CONTRACT.to_mapping()
    assert mapping["schema"] == G4C_CONTRACT_SCHEMA
    assert ProviderRouteContract.from_mapping(mapping) == SYNTHETIC_ROUTE_CONTRACT
    assert ProviderRouteContract.from_mapping(
        REAL_ROUTE_TEMPLATE.to_mapping()) == REAL_ROUTE_TEMPLATE


@pytest.mark.parametrize("mutation", [
    {"route_id": ""},
    {"provider": "OpenCode Go"},
    {"model_id": "x "},
    {"endpoint_host": "*.example.com"},
    {"port": True},
    {"port": 70000},
    {"method": "GET"},
    {"exact_path": "/v1/../etc"},
    {"exact_path": "relative"},
    {"exact_path": "/x%2e%2e/y"},
    {"retry_policy": "retry3"},
    {"max_output_tokens": 0},
    {"max_output_tokens": 4096},
    {"allow_files": 0},
    {"price_source": "vendor_list_price"},
    {"activation": "ENABLED"},
    {"allowed_tool_schema_digests": ["not-a-digest"]},
])
def test_c01_contract_rejects_tampered_fields(mutation) -> None:
    mapping = SYNTHETIC_ROUTE_CONTRACT.to_mapping()
    mapping.update(mutation)
    if mutation.get("port") is True:
        # bool is not an int for this contract (strict type check)
        with pytest.raises(ValueError):
            ProviderRouteContract.from_mapping(mapping)
        return
    with pytest.raises(ValueError):
        ProviderRouteContract.from_mapping(mapping)


def test_c01_mapping_rejects_unknown_and_missing_fields() -> None:
    mapping = SYNTHETIC_ROUTE_CONTRACT.to_mapping()
    mapping["extra"] = "x"
    with pytest.raises(ValueError):
        ProviderRouteContract.from_mapping(mapping)
    missing = SYNTHETIC_ROUTE_CONTRACT.to_mapping()
    missing.pop("activation")
    with pytest.raises(ValueError):
        ProviderRouteContract.from_mapping(missing)
    bad_schema = SYNTHETIC_ROUTE_CONTRACT.to_mapping()
    bad_schema["schema"] = "m0.g4c.other"
    with pytest.raises(ValueError):
        ProviderRouteContract.from_mapping(bad_schema)


def test_c01_real_route_cannot_carry_an_endpoint() -> None:
    mapping = REAL_ROUTE_TEMPLATE.to_mapping()
    mapping["endpoint_host"] = "api.deepseek.com"
    with pytest.raises(ValueError):
        ProviderRouteContract.from_mapping(mapping)


def test_c01_send_problems_when_activation_downgraded() -> None:
    blocked_synthetic = replace(SYNTHETIC_ROUTE_CONTRACT,
                                activation=ACTIVATION_BLOCKED,
                                endpoint_host=None, port=None, method=None,
                                exact_path=None, request_format_version=None,
                                streaming_contract=None,
                                tokenizer_price_source_version=None,
                                price_source="REQUIRES_VERIFICATION")
    assert blocked_synthetic.contract_problems() == ()
    assert "ROUTE_ACTIVATION_NOT_SYNTHETIC_ONLY" in blocked_synthetic.send_problems()
    assert "PRICING_SOURCE_UNVERIFIED" in blocked_synthetic.send_problems()
