from dataclasses import replace

import pytest

from autoteacher_m0.contracts import RunRequest, RuntimeFailure
from autoteacher_m0.runtime.mock_adapter import MockRuntime


def request(prompt="Reply with M0_SMOKE_OK.", session_id="session-a"):
    return RunRequest("case-a", prompt, "teacher_v0", session_id,
                      "deepseek-official", "deepseek-flash", "deepseek-official")


def test_same_input_same_output_independent_run_ids():
    runtime = MockRuntime()
    left, right = runtime.run(request()), runtime.run(request())
    assert left.text == right.text == "M0_SMOKE_OK"
    assert left.run_id != right.run_id
    assert left.metadata["mode"] == "mock"
    assert left.estimated_cost_usd == 0.0


def test_explicit_unknown_session_does_not_create():
    with pytest.raises(RuntimeFailure) as caught:
        MockRuntime().resume("missing", "continue")
    assert caught.value.code == "SESSION_NOT_FOUND"


@pytest.mark.parametrize("code", ["AUTH_ERROR", "RATE_LIMIT", "PROVIDER_ERROR", "TIMEOUT",
                                  "INVALID_MODEL", "INTERRUPTED", "SESSION_BUSY"])
def test_injected_failure_is_explicit(code):
    result = MockRuntime(fail_with=code).run(request())
    assert result.status == "ERROR"
    assert result.error_code == code
    assert result.text == ""


def test_identifier_is_not_a_path(tmp_path):
    with pytest.raises(ValueError):
        MockRuntime(tmp_path).run(replace(request(), session_id="../../escape"))
