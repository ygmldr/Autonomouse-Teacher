"""E1-02 dedicated local-Mock lifecycle, strict validation and bounded retry.

No provider/SDK process is started and this does not change real E1-02 BLOCKED.
"""
from dataclasses import replace
import json
import traceback

import pytest

from autoteacher_m0.contracts import RuntimeFailure
from autoteacher_m0.runtime import structured_output as structured

GOOD = '{"skill_id":"binary_search","ready":true}'
BAD = '{"skill_id":"binary_search","ready":"true","api_key":"sk-FAKE_ONLY"}'


def spy_on_mock(monkeypatch):
    original = structured.MockRuntime.run
    calls = []

    def watched(runtime, request):
        calls.append(request)
        return original(runtime, request)

    monkeypatch.setattr(structured.MockRuntime, "run", watched)
    return calls


def test_default_e1_02_uses_real_existing_mock_json_branch_and_pydantic(monkeypatch):
    calls = spy_on_mock(monkeypatch)
    result = structured.run_e1_mock_validation()
    assert result.status == "SUCCESS" and result.error_code is None
    assert isinstance(result.output, structured.E1Output)
    assert result.output.model_dump() == {"skill_id": "binary_search", "ready": True}
    assert len(result.attempts) == len(calls) == 1
    assert calls[0].case_id == "E1-02" and calls[0].route_id == calls[0].provider == "mock"
    assert calls[0].model == "deepseek-flash"
    assert result.to_dict()["real_sdk_e1_02"] == "BLOCKED"


def test_default_is_no_retry_and_preserves_failure_without_raw_response(monkeypatch):
    calls = spy_on_mock(monkeypatch)
    result = structured.run_e1_mock_validation(responses=(BAD,))
    assert result.status == "ERROR" and result.output is None
    assert result.error_code == "INVALID_OUTPUT"
    assert len(result.attempts) == len(calls) == 1
    assert result.attempts[0].error_code == "INVALID_OUTPUT"
    assert "sk-FAKE_ONLY" not in json.dumps(result.to_dict())
    assert "sk-FAKE_ONLY" not in repr(result)


def test_one_retry_failure_then_success_keeps_both_attempts_and_unique_ids(monkeypatch):
    calls = spy_on_mock(monkeypatch)
    result = structured.run_e1_mock_validation(responses=(BAD, GOOD), max_retries=1)
    assert result.status == "SUCCESS" and result.output.ready is True
    assert [attempt.number for attempt in result.attempts] == [1, 2]
    assert [attempt.status for attempt in result.attempts] == ["ERROR", "SUCCESS"]
    assert [attempt.error_code for attempt in result.attempts] == ["INVALID_OUTPUT", None]
    assert len({attempt.run_id for attempt in result.attempts}) == 2
    assert len(calls) == 2 and len({request.session_id for request in calls}) == 2
    assert "sk-FAKE_ONLY" not in json.dumps(result.to_dict())


def test_exhausted_retry_is_error_not_silent_success_or_third_attempt(monkeypatch):
    calls = spy_on_mock(monkeypatch)
    result = structured.run_e1_mock_validation(responses=(BAD, "not JSON"), max_retries=1)
    assert result.status == "ERROR" and result.output is None
    assert result.error_code == "INVALID_OUTPUT"
    assert len(result.attempts) == len(calls) == 2
    assert len({attempt.run_id for attempt in result.attempts}) == 2
    assert all(attempt.status == "ERROR" for attempt in result.attempts)


def test_success_never_uses_the_permitted_retry(monkeypatch):
    calls = spy_on_mock(monkeypatch)
    result = structured.run_e1_mock_validation(responses=(GOOD, BAD), max_retries=1)
    assert result.status == "SUCCESS"
    assert len(result.attempts) == len(calls) == 1


@pytest.mark.parametrize("limit", [True, False, -1, 2, 8, 1.0, "1", None])
def test_bad_retry_policy_rejected_before_any_mock_dispatch(limit, monkeypatch):
    calls = spy_on_mock(monkeypatch)
    with pytest.raises(ValueError):
        structured.run_e1_mock_validation(max_retries=limit)
    assert calls == []


@pytest.mark.parametrize("responses", [GOOD, [GOOD], (), (GOOD, GOOD), (None,), (1,), object()])
def test_fixture_api_is_data_only_and_bounded_before_dispatch(responses, monkeypatch):
    calls = spy_on_mock(monkeypatch)
    with pytest.raises(ValueError):
        structured.run_e1_mock_validation(responses=responses)
    assert calls == []


@pytest.mark.parametrize("code", ["SECURITY_BLOCKED", "TIMEOUT", "AUTH_ERROR", "PROVIDER_ERROR"])
def test_runtime_failures_terminal_sanitized_and_never_retried(code, monkeypatch):
    calls = []

    def fail(_runtime, _request):
        calls.append(1)
        raise RuntimeFailure(code, "sk-FAKE_ONLY")

    monkeypatch.setattr(structured.MockRuntime, "run", fail)
    with pytest.raises(RuntimeFailure) as caught:
        structured.run_e1_mock_validation(max_retries=1)
    assert calls == [1]
    assert caught.value.code == code
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert "sk-FAKE_ONLY" not in "".join(traceback.format_exception(caught.value))


def test_security_failure_from_validator_is_not_retried_or_reclassified(monkeypatch):
    calls = spy_on_mock(monkeypatch)

    def blocked(_text):
        raise RuntimeFailure("SECURITY_BLOCKED", "sk-FAKE_ONLY")

    monkeypatch.setattr(structured, "validate_e1_json", blocked)
    with pytest.raises(RuntimeFailure) as caught:
        structured.run_e1_mock_validation(max_retries=1)
    assert caught.value.code == "SECURITY_BLOCKED" and len(calls) == 1
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert "sk-FAKE_ONLY" not in "".join(traceback.format_exception(caught.value))


def test_wrong_provenance_or_unsuccessful_run_cannot_reach_json_retry(monkeypatch):
    original = structured.MockRuntime.run
    calls = []

    def wrong(runtime, request):
        calls.append(1)
        return replace(original(runtime, request), route_id="deepseek-official")

    monkeypatch.setattr(structured.MockRuntime, "run", wrong)
    with pytest.raises(RuntimeFailure) as caught:
        structured.run_e1_mock_validation(max_retries=1)
    assert caught.value.code == "SECURITY_BLOCKED" and len(calls) == 1

    for code in ("SECURITY_BLOCKED", "INVALID_OUTPUT", "TIMEOUT"):
        calls.clear()

        def unsuccessful(runtime, request):
            calls.append(1)
            return replace(original(runtime, request), status="ERROR", error_code=code)

        monkeypatch.setattr(structured.MockRuntime, "run", unsuccessful)
        with pytest.raises(RuntimeFailure) as caught:
            structured.run_e1_mock_validation(max_retries=1)
        assert caught.value.code == code and len(calls) == 1


def test_unexpected_mock_exception_is_terminal_without_original_detail(monkeypatch):
    calls = []

    def fail(_runtime, _request):
        calls.append(1)
        raise ValueError("sk-FAKE_ONLY")

    monkeypatch.setattr(structured.MockRuntime, "run", fail)
    with pytest.raises(RuntimeFailure) as caught:
        structured.run_e1_mock_validation(max_retries=1)
    assert caught.value.code == "SDK_ERROR" and calls == [1]
    assert caught.value.__context__ is None and caught.value.__cause__ is None
    assert "sk-FAKE_ONLY" not in "".join(traceback.format_exception(caught.value))


def test_dedicated_mock_probe_never_imports_or_constructs_sdk(monkeypatch):
    import builtins
    original = builtins.__import__
    touched = []

    def watched(name, *args, **kwargs):
        if name.startswith("deepseek_harness"):
            touched.append(name)
            raise AssertionError("SDK import forbidden in E1-02 Mock probe")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", watched)
    assert structured.run_e1_mock_validation().status == "SUCCESS"
    assert structured.run_e1_mock_validation(responses=(BAD, GOOD), max_retries=1).status == "SUCCESS"
    assert touched == []


def test_no_public_injected_runtime_or_production_record_entrypoint():
    with pytest.raises(TypeError):
        structured.run_e1_mock_validation(runtime=object())
    with pytest.raises(TypeError):
        structured.run_e1_mock_validation(request=object())
    with pytest.raises(TypeError):
        structured.run_e1_mock_validation(record=object())
