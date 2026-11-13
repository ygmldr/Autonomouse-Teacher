"""Dedicated E1-02 JSON/Pydantic assertions, NOT report JSON or SDK smoke."""
import json
import traceback

import pytest
from pydantic import ValidationError

from autoteacher_m0.contracts import RuntimeFailure
from autoteacher_m0.runtime.structured_output import (
    E1Output, INVALID_OUTPUT_MESSAGE, MAX_E1_JSON_BYTES, validate_e1_json,
)

GOOD = '{"skill_id":"binary_search","ready":true}'


@pytest.mark.parametrize("text", [
    GOOD, ' \n\t' + GOOD + '\r\n ',
    '{"ready":true,"skill_id":"binary_search"}',
    '{"skill_id":"binary_\\u0073earch","ready":true}',
])
def test_e1_02_valid_json_is_actually_validated_by_pydantic(text):
    output = validate_e1_json(text)
    assert isinstance(output, E1Output)
    assert output.model_dump() == {"skill_id": "binary_search", "ready": True}
    assert type(output.ready) is bool
    assert E1Output.model_validate_json(output.model_dump_json()) == output


@pytest.mark.parametrize("text", [
    "", " \t\r\n", "not JSON", "{", "[]", "null", "1", "true", '"JSON string"',
    "```json\n" + GOOD + "\n```", "prefix " + GOOD, GOOD + " suffix", GOOD + GOOD,
    '{}', '{"skill_id":"binary_search"}', '{"ready":true}',
    '{"skill_id":"other_skill","ready":true}',
    '{"skill_id":"","ready":true}', '{"skill_id":" binary_search","ready":true}',
    '{"skill_id":1,"ready":true}', '{"skill_id":true,"ready":true}',
    '{"skill_id":["binary_search"],"ready":true}',
    '{"skill_id":"binary_search","ready":true,"extra":"not permitted"}',
    '{"skill_id":"binary_search","ready":true,"api_key":"sk-INVENTED_ONLY"}',
    '{"skill_id":"binary_search","ready":NaN}',
    '{"skill_id":"binary_search","ready":Infinity}',
    '{"skill_id":"binary_search","ready":-Infinity}',
    '{"skill_id":"binary_search","ready":1e9999}',
    '{"skill_id":"binary_search","skill_id":"binary_search","ready":true}',
    '{"skill_id":"wrong","skill_id":"binary_search","ready":true}',
    '{"skill_id":"binary_search","ready":true,"ready":true}',
    '\ufeff' + GOOD, GOOD + '\x00',
    '{"skill_id":"\ud800","ready":true}',
    '[' * 1500 + '0' + ']' * 1500,
])
def test_e1_02_invalid_json_shape_fields_or_boundaries_have_one_safe_error(text):
    with pytest.raises(RuntimeFailure) as caught:
        validate_e1_json(text)
    failure = caught.value
    assert failure.code == "INVALID_OUTPUT"
    assert str(failure) == INVALID_OUTPUT_MESSAGE
    assert failure.__cause__ is None and failure.__context__ is None
    formatted = "".join(traceback.format_exception(failure))
    assert "sk-INVENTED_ONLY" not in formatted
    assert "ValidationError" not in formatted and "JSONDecodeError" not in formatted


@pytest.mark.parametrize("value", [1, 0, 1.0, 0.0, "true", "false", False, None, [], {}, "yes"])
def test_ready_never_coerces_integer_string_or_false_to_true(value):
    with pytest.raises(RuntimeFailure) as caught:
        validate_e1_json(json.dumps({"skill_id": "binary_search", "ready": value}))
    assert caught.value.code == "INVALID_OUTPUT"
    with pytest.raises(ValidationError):
        E1Output.model_validate({"skill_id": "binary_search", "ready": value})


def test_e1_output_is_frozen_extra_forbidden_and_required():
    output = validate_e1_json(GOOD)
    with pytest.raises(ValidationError):
        output.ready = False
    schema = E1Output.model_json_schema()
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"skill_id", "ready"}


@pytest.mark.parametrize("value", [None, True, 1, b'{"skill_id":"binary_search","ready":true}',
                                  {"skill_id": "binary_search", "ready": True}, []])
def test_only_text_input_is_accepted(value):
    with pytest.raises(RuntimeFailure) as caught:
        validate_e1_json(value)
    assert caught.value.code == "INVALID_OUTPUT"
    assert caught.value.__context__ is None


def test_exact_byte_limit_is_inclusive_and_oversize_is_rejected():
    padded = GOOD + " " * (MAX_E1_JSON_BYTES - len(GOOD.encode("utf-8")))
    assert len(padded.encode("utf-8")) == MAX_E1_JSON_BYTES
    assert validate_e1_json(padded).ready is True
    with pytest.raises(RuntimeFailure):
        validate_e1_json(padded + " ")
    with pytest.raises(RuntimeFailure):
        validate_e1_json(GOOD + " " * (MAX_E1_JSON_BYTES * 2))


def test_utf8_byte_guard_not_just_character_guard():
    # This valid-JSON extra field is intentionally rejected; its multibyte body
    # also exceeds the byte guard despite staying below the character guard.
    text = '{"skill_id":"binary_search","ready":true,"extra":"' + "界" * 1400 + '"}'
    assert len(text) < MAX_E1_JSON_BYTES < len(text.encode("utf-8"))
    with pytest.raises(RuntimeFailure) as caught:
        validate_e1_json(text)
    assert caught.value.__context__ is None


def test_sensitive_field_names_values_and_malformed_text_never_enter_error_chain():
    for text in ('{"api_key":"sk-FAKE_SECRET_ONLY","ready":"true"}',
                 'sk-FAKE_SECRET_ONLY { malformed',
                 '{"skill_id":"sk-FAKE_SECRET_ONLY","ready":true}'):
        with pytest.raises(RuntimeFailure) as caught:
            validate_e1_json(text)
        failure = caught.value
        assert failure.__cause__ is None and failure.__context__ is None
        assert "sk-FAKE_SECRET_ONLY" not in str(failure)
        assert "sk-FAKE_SECRET_ONLY" not in repr(failure.__dict__)
        assert "sk-FAKE_SECRET_ONLY" not in "".join(traceback.format_exception(failure))
