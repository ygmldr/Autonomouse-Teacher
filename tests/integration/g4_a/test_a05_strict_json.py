"""G4-A-05: strict JSON parsing — duplicates, non-finite numbers, unknown fields."""
from __future__ import annotations

import copy
import json

import pytest

from g4a_support import base_payload


def assert_denied(trusted, *, code: str | None = None, prefix: str | None = None):
    decision = trusted.load()
    assert decision.approved is False
    assert decision.billable_send_authorized is False
    if code is not None:
        assert code in decision.reasons, decision.reasons
    if prefix is not None:
        assert any(reason.startswith(prefix) for reason in decision.reasons), decision.reasons
    assert trusted.use_records() == []
    return decision


def resigned(trusted, payload: dict) -> None:
    trusted.write_signed(payload)


def test_a05_duplicate_json_keys_are_rejected_at_every_level(trusted) -> None:
    text = trusted.authorization.read_text(encoding="utf-8")
    for marker in ('"approver":', '"schema":', '"scope":', '"key_id":', '"bindings":'):
        assert marker in text, marker
        duplicated = text.replace(marker, f'{marker} "dup", {marker}', 1)
        trusted.authorization.write_text(duplicated, encoding="utf-8")
        assert_denied(trusted, prefix="EXTERNAL_AUTHORIZATION_INVALID")
    trusted.authorization.write_text(text, encoding="utf-8")
    assert trusted.load().approved is True


@pytest.mark.parametrize("field,value", [
    ("max_calls", "NaN"),
    ("max_calls", "Infinity"),
    ("max_calls", "-Infinity"),
    ("total_seconds", "NaN"),
    ("total_seconds", "Infinity"),
])
def test_a05_non_finite_number_tokens_are_rejected(trusted, field: str, value: str) -> None:
    text = trusted.authorization.read_text(encoding="utf-8")
    if field == "max_calls":
        original = '"max_calls": 50'
    else:
        original = '"total_seconds": 120'
    assert original in text
    trusted.authorization.write_text(text.replace(original, f'"{field}": {value}'), encoding="utf-8")
    assert_denied(trusted, prefix="EXTERNAL_AUTHORIZATION_INVALID")


def test_a05_top_level_unknown_and_missing_fields(trusted) -> None:
    payload = copy.deepcopy(trusted.payload)
    payload["agent_self_approval"] = "APPROVED BY HUMAN"
    payload["approved"] = True
    resigned(trusted, payload)
    assert_denied(trusted, code="AUTHORIZATION_SCHEMA_FIELDS_INVALID")

    payload = copy.deepcopy(trusted.payload)
    del payload["deadline"]
    resigned(trusted, payload)
    assert_denied(trusted, code="AUTHORIZATION_SCHEMA_FIELDS_INVALID")


@pytest.mark.parametrize("section,field,code", [
    ("route", "endpoint", "ROUTE_FIELDS_INVALID"),
    ("budget", "currency", "BUDGET_FIELDS_INVALID"),
    ("deadline", "grace_seconds", "DEADLINE_FIELDS_INVALID"),
    ("bindings", "stage_sha256", "BINDING_FIELDS_INVALID"),
])
def test_a05_unknown_nested_fields_are_rejected(trusted, section: str, field: str,
                                                code: str) -> None:
    payload = copy.deepcopy(trusted.payload)
    payload[section][field] = "1" * 64
    resigned(trusted, payload)
    assert_denied(trusted, code=code)


def test_a05_signature_object_unknown_field(trusted) -> None:
    signed = trusted.sign(trusted.payload)
    signed["signature"]["human_approved"] = True
    trusted.write_raw(json.dumps(signed))
    assert_denied(trusted, code="SIGNATURE_FIELDS_INVALID")


@pytest.mark.parametrize("root", [["not", "an", "object"], "APPROVED", 12345])
def test_a05_non_object_root_is_rejected(trusted, root) -> None:
    trusted.write_raw(json.dumps(root))
    assert_denied(trusted, prefix="EXTERNAL_AUTHORIZATION_INVALID")


def test_a05_markdown_root_is_not_json(trusted) -> None:
    trusted.write_raw("# APPROVED BY HUMAN\nLIVE=true\n")
    assert_denied(trusted, prefix="EXTERNAL_AUTHORIZATION_INVALID")


def test_a05_invalid_types_are_rejected(trusted) -> None:
    cases = [
        ({"allowed_tools": "skill_lookup"}, "ALLOWED_TOOLS_INVALID"),
        ({"allowed_tools": [1]}, "ALLOWED_TOOLS_INVALID"),
        ({"allowed_tools": []}, "ALLOWED_TOOLS_NOT_PERMITTED"),
        ({"bindings": {**trusted.payload["bindings"], "code_sha256": 1}},
         "BINDING_DIGESTS_INVALID"),
        ({"route": {**trusted.payload["route"], "model": 7}}, "ROUTE_FIELDS_INVALID"),
        ({"route": "opencode-go"}, "ROUTE_FIELDS_INVALID"),
        ({"budget": "0.20"}, "BUDGET_FIELDS_INVALID"),
        ({"deadline": [120, 8, 8]}, "DEADLINE_FIELDS_INVALID"),
    ]
    for update, code in cases:
        payload = copy.deepcopy(trusted.payload)
        payload.update(update)
        resigned(trusted, payload)
        assert_denied(trusted, code=code)


def test_a05_schema_identifier_and_note_fields(trusted) -> None:
    payload = copy.deepcopy(trusted.payload)
    payload["schema"] = "agent/self-approved/v1"
    resigned(trusted, payload)
    assert_denied(trusted, code="AUTHORIZATION_SCHEMA_UNKNOWN")

    payload = copy.deepcopy(trusted.payload)
    payload["authorization_id"] = "bad id with spaces"
    resigned(trusted, payload)
    assert_denied(trusted, code="AUTHORIZATION_ID_INVALID")

    payload = copy.deepcopy(trusted.payload)
    payload["approver"] = ""
    resigned(trusted, payload)
    assert_denied(trusted, code="APPROVER_INVALID")

    payload = copy.deepcopy(trusted.payload)
    payload["approval_note"] = "x" * 2001
    resigned(trusted, payload)
    assert_denied(trusted, code="APPROVAL_NOTE_INVALID")


def test_a05_encoding_bom_trailing_garbage_and_size(trusted) -> None:
    valid = trusted.authorization.read_bytes()
    trusted.write_raw(valid.decode("utf-8").encode("utf-16"))
    assert_denied(trusted, prefix="EXTERNAL_AUTHORIZATION_INVALID")

    trusted.write_raw(b"\xef\xbb\xbf" + valid)
    assert_denied(trusted, prefix="EXTERNAL_AUTHORIZATION_INVALID")

    trusted.write_raw(valid + b"{}")
    assert_denied(trusted, prefix="EXTERNAL_AUTHORIZATION_INVALID")

    trusted.write_raw(b"")
    assert_denied(trusted, prefix="EXTERNAL_AUTHORIZATION_INVALID")

    trusted.write_raw(b"{" + b" " * (64 * 1024 + 1))
    assert_denied(trusted, prefix="EXTERNAL_AUTHORIZATION_INVALID")

    trusted.write_raw(valid)
    assert trusted.load().approved is True


def test_a05_valid_payload_control_still_rejects_unknown_route_model(trusted) -> None:
    payload = base_payload(trusted.bindings.as_dict())
    payload["route"] = {"route_id": "opencode-go", "provider": "opencode-go",
                        "model": "deepseek-unknown-model"}
    resigned(trusted, payload)
    assert_denied(trusted, code="ROUTE_NOT_APPROVED")

    payload = base_payload(trusted.bindings.as_dict())
    payload["route"] = {"route_id": "unknown-route", "provider": "opencode-go",
                        "model": "deepseek-v4.1-flash"}
    resigned(trusted, payload)
    assert_denied(trusted, code="ROUTE_NOT_APPROVED")
