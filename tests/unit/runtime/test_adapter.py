from pathlib import Path
from types import SimpleNamespace

import pytest

from autoteacher_m0.contracts import RunRequest, RuntimeFailure
from autoteacher_m0.runtime.dsh_adapter import HarnessAdapter, classify_error, normalize_result, sdk_options
from autoteacher_m0.settings import RuntimeSettings


def settings():
    return RuntimeSettings(Path("/work/public"), Path("/work/home"), Path("/input/privacy.yml"))


def request():
    return RunRequest("case", "prompt", "teacher_v0", "session-a",
                      "deepseek-official", "deepseek-flash", "deepseek-official")


def test_pure_sdk_mapping_uses_explicit_paths_and_current_alias():
    options = sdk_options(settings())
    assert options["profile"] == "sdk-minimal"
    assert options["model"] == "deepseek-flash"
    assert options["dsh_home"] != options["cwd"]
    assert options["patches"] == ("/input/privacy.yml",)
    assert options["approval_requests"] is False
    assert "api_key" not in options


@pytest.mark.parametrize("entry", ["run", "resume", "_new_harness"])
def test_live_unconditionally_blocked_before_sdk_import(entry, monkeypatch):
    import builtins
    original = builtins.__import__
    touched = []

    def watched(name, *args, **kwargs):
        if name == "deepseek_harness":
            touched.append(name)
            raise AssertionError("SDK import must not occur")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", watched)
    monkeypatch.setenv("AT_M0_LIVE_APPROVED", "true")  # invented switch must have no effect
    adapter = HarnessAdapter(settings())
    with pytest.raises(RuntimeFailure) as caught:
        if entry == "run":
            adapter.run(request())
        elif entry == "resume":
            adapter.resume("session-a", "continue")
        else:
            adapter._new_harness()
    assert caught.value.code == "SECURITY_BLOCKED"
    assert touched == []


@pytest.mark.parametrize("reason,status,error", [
    ("completed", "SUCCESS", None), ("aborted", "INTERRUPTED", "INTERRUPTED"),
    ("max-tokens", "ERROR", "INVALID_OUTPUT"), ("error", "ERROR", "PROVIDER_ERROR"),
    (None, "ERROR", "PROVIDER_ERROR"),
])
def test_fake_result_mapping_is_not_real_sdk_verification(reason, status, error):
    fake = SimpleNamespace(session_id="session-a", final_response="text", finish_reason=reason,
                           events=[{"type": "tool/call", "data": {"name": "skill_lookup"}}])
    record = normalize_result(request(), fake)
    assert (record.status, record.error_code) == (status, error)
    assert record.events[0]["data"]["name"] == "skill_lookup"
    assert record.input_tokens is None and record.estimated_cost_usd is None
    assert record.route_id == "deepseek-official"


@pytest.mark.parametrize("status,code", [(401, "AUTH_ERROR"), (429, "RATE_LIMIT"),
                                       (503, "PROVIDER_ERROR")])
def test_http_shaped_failure_classification(status, code):
    exc = RuntimeError("sk-INVENTED_TEST_ONLY")
    exc.status_code = status
    assert classify_error(exc) == code
    assert classify_error(TimeoutError()) == "TIMEOUT"


def test_bad_path_or_route_rejected():
    with pytest.raises(ValueError):
        RuntimeSettings(Path("relative"), Path("/home-a"), Path("/patch.yml"))
    with pytest.raises(ValueError):
        RuntimeSettings(Path("/work"), Path("/work/home"), Path("/patch.yml"))
    with pytest.raises(ValueError):
        RuntimeSettings(Path("/work"), Path("/home-a"), Path("/patch.yml"), model="other")
