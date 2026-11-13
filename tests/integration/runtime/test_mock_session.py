import json
from dataclasses import replace

import pytest

from autoteacher_m0.contracts import RunRequest, RuntimeFailure
from autoteacher_m0.runtime.mock_adapter import MockRuntime


def request(nonce):
    return RunRequest("mock-session-case", nonce, "teacher_v0", "same-session",
                      "deepseek-official", "deepseek-flash", "deepseek-official")


def test_mock_only_restart_and_home_namespace(tmp_path):
    home_a, home_b = tmp_path / "a", tmp_path / "b"
    for nonce, home in (("PUBLIC_NONCE_A", home_a), ("PUBLIC_NONCE_B", home_b)):
        with MockRuntime(home) as runtime:
            runtime.run(request(nonce))
    # Three independent mock-controller restarts, NOT DSH E3 verification.
    for _ in range(3):
        with MockRuntime(home_a) as a, MockRuntime(home_b) as b:
            text_a = a.resume("same-session", "MOCK_RECALL").text
            text_b = b.resume("same-session", "MOCK_RECALL").text
            assert "PUBLIC_NONCE_A" in text_a and "PUBLIC_NONCE_B" not in text_a
            assert "PUBLIC_NONCE_B" in text_b and "PUBLIC_NONCE_A" not in text_b
    for home in (home_a, home_b):
        rows = [json.loads(line) for line in (home / "sessions/same-session.jsonl").read_text().splitlines()]
        assert [row["record"]["events"][0]["sequence"] for row in rows] == list(range(4))


def test_corrupt_mock_session_never_silently_recreated(tmp_path):
    directory = tmp_path / "sessions"
    directory.mkdir()
    (directory / "same-session.jsonl").write_text("{broken json")
    with pytest.raises(RuntimeFailure) as caught:
        MockRuntime(tmp_path).resume("same-session", "continue")
    assert caught.value.code == "SESSION_CORRUPT"


def test_persisted_mock_trace_redacts_fake_credentials(tmp_path):
    with MockRuntime(tmp_path) as runtime:
        runtime.run(replace(request(""), prompt="sk-FAKE_SENTINEL_ONLY"))
    assert "sk-FAKE_SENTINEL_ONLY" not in (tmp_path / "sessions/same-session.jsonl").read_text()
