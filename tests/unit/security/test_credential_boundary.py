"""Offline credential/mount/egress boundary tests (fake keys only, no network)."""
from __future__ import annotations

from pathlib import Path

import pytest

from autoteacher_m0.security.credential_boundary import (
    CANDIDATE_ENV_ALLOWLIST,
    OPENCODE_GO_EGRESS,
    CredentialBoundaryViolation,
    LauncherOnlySecret,
    assert_candidate_env_clean,
    assert_log_clean,
    redact_secrets,
    scrub_candidate_env,
    validate_candidate_argv,
    validate_candidate_mounts,
)
from autoteacher_m0.security.docker_runner import ContainerRunner

FAKE_OPENCODE_KEY = "oc_sk_FAKE000000000000000000000000000000000000000000000000000000"
IMAGE = ("localhost/autoteacher-local-oci@sha256:"
         "62d3569ec38e27ed16fa3147515c1c78d993bb7df831cc1fe29811f3fe64667b")


def test_candidate_env_is_rebuilt_from_allowlist() -> None:
    launcher_env = {
        "PATH": "/opt/python/bin:/usr/bin", "HOME": "/work", "LANG": "C",
        "OPENCODE_API_KEY": FAKE_OPENCODE_KEY, "DEEPSEEK_API_KEY": "fake-deepseek-key-value",
        "HTTPS_PROXY": "http://proxy.invalid:8080", "UNRELATED": "x",
        "ACCESS_TOKEN": "fake-token-value",
    }
    clean, violations = scrub_candidate_env(launcher_env, known_secret_values=[FAKE_OPENCODE_KEY])
    assert clean == {"PATH": "/opt/python/bin:/usr/bin", "HOME": "/work", "LANG": "C"}
    assert set(violations) == {"ENV_NOT_ALLOWED:OPENCODE_API_KEY",
                               "ENV_NOT_ALLOWED:DEEPSEEK_API_KEY",
                               "ENV_NOT_ALLOWED:HTTPS_PROXY",
                               "ENV_NOT_ALLOWED:UNRELATED",
                               "ENV_NOT_ALLOWED:ACCESS_TOKEN"}
    assert all(name in CANDIDATE_ENV_ALLOWLIST or name.startswith(("ENV_",))
               for name in violations)
    assert FAKE_OPENCODE_KEY not in repr(clean)
    with pytest.raises(CredentialBoundaryViolation):
        assert_candidate_env_clean(launcher_env, [FAKE_OPENCODE_KEY])


def test_secret_value_cannot_be_forwarded_through_allowed_variable() -> None:
    env = {"PATH": "/bin", "HOME": "/work", "LANG": "C"}
    env["TZ"] = "UTC" + FAKE_OPENCODE_KEY
    clean, violations = scrub_candidate_env(env, known_secret_values=[FAKE_OPENCODE_KEY])
    assert "ENV_SECRET_VALUE:TZ" in violations
    assert FAKE_OPENCODE_KEY not in repr(clean)


def test_redaction_covers_known_values_and_patterns() -> None:
    log = (f"launcher env OPENCODE_API_KEY={FAKE_OPENCODE_KEY}\n"
           "Authorization: Bearer abcdef0123456789\n"
           "key DEEPSEEK_API_KEY=sk-livefake0123456789\n")
    redacted = redact_secrets(log, [FAKE_OPENCODE_KEY])
    assert FAKE_OPENCODE_KEY not in redacted
    assert "oc_sk_" not in redacted
    assert "sk-livefake" not in redacted
    assert "Bearer abcdef0123456789" not in redacted
    assert redacted.count("[REDACTED]") >= 3
    assert_log_clean(redacted, [FAKE_OPENCODE_KEY])
    with pytest.raises(CredentialBoundaryViolation):
        assert_log_clean(log, [FAKE_OPENCODE_KEY])


def test_launcher_only_secret_repr_is_always_redacted() -> None:
    secret = LauncherOnlySecret("OPENCODE_API_KEY", FAKE_OPENCODE_KEY)
    assert FAKE_OPENCODE_KEY not in repr(secret)
    assert FAKE_OPENCODE_KEY not in str(secret)
    assert "[REDACTED:" in repr(secret)
    assert secret.for_launcher_env() == {"OPENCODE_API_KEY": FAKE_OPENCODE_KEY}
    with pytest.raises(ValueError):
        LauncherOnlySecret("UNLISTED_TOKEN", "value")


def test_candidate_mount_policy(tmp_path: Path) -> None:
    stage = tmp_path / "stage"
    stage.mkdir()
    allowed = validate_candidate_mounts(
        [f"type=bind,src={stage},dst=/input,readonly"], allowed_stage_root=tmp_path)
    assert allowed == ()
    bad_rw = validate_candidate_mounts(
        [f"type=bind,src={stage},dst=/input"], allowed_stage_root=tmp_path)
    assert "MOUNT_NOT_READ_ONLY" in bad_rw
    int_ = Path("/") / "root" / ".config"
    bad_paths = validate_candidate_mounts(
        [f"type=bind,src={int_},dst=/input,readonly"], allowed_stage_root=tmp_path)
    assert "MOUNT_FORBIDDEN_SOURCE" in bad_paths
    outside = tmp_path / "outside"
    outside.mkdir()
    assert "MOUNT_OUTSIDE_PUBLIC_STAGE" in validate_candidate_mounts(
        [f"type=bind,src={outside},dst=/input,readonly"], allowed_stage_root=stage)
    assert "MOUNT_DESTINATION_NOT_INPUT" in validate_candidate_mounts(
        [f"type=bind,src={stage},dst=/project,readonly"], allowed_stage_root=tmp_path)


def test_container_runner_command_passes_candidate_policy(tmp_path: Path) -> None:
    stage = tmp_path / "stage"
    stage.mkdir()
    runner = ContainerRunner(image=IMAGE, engine="podman")
    command = runner.command(stage=stage, name="at-m0-policy-test")
    assert validate_candidate_argv(command) == ()
    mounts = [command[i + 1] for i, token in enumerate(command) if token == "--mount"]
    assert validate_candidate_mounts(mounts, allowed_stage_root=tmp_path) == ()
    assert command[command.index("--network=none")] == "--network=none"


@pytest.mark.parametrize("mutator,reason", [
    (lambda c: ["--privileged", *c], "PRIVILEGED_CONTAINER"),
    (lambda c: [*c, "-p", "8080:80"], "CANDIDATE_PORT_PUBLISHED"),
    (lambda c: [*c, "--env", "DEEPSEEK_API_KEY=fake"], "CANDIDATE_ENV_FORBIDDEN:DEEPSEEK_API_KEY"),
    (lambda c: [*c, "--env", "OPENCODE_API_KEY=fake"], "CANDIDATE_ENV_FORBIDDEN:OPENCODE_API_KEY"),
    (lambda c: [*c, "--mount", "type=bind,src=/root,dst=/input,readonly"],
     "CANDIDATE_MOUNT_FORBIDDEN"),
])
def test_candidate_argv_rejects_key_or_egress_leaks(tmp_path: Path, mutator, reason: str) -> None:
    stage = tmp_path / "stage"
    stage.mkdir()
    command = ContainerRunner(image=IMAGE, engine="podman").command(
        stage=stage, name="at-m0-policy-test")
    assert reason in validate_candidate_argv(mutator(list(command)))


def test_candidate_argv_requires_isolation_flags(tmp_path: Path) -> None:
    stage = tmp_path / "stage"
    stage.mkdir()
    command = ContainerRunner(image=IMAGE, engine="podman").command(
        stage=stage, name="at-m0-policy-test")
    stripped = [token for token in command if token != "--network=none"]
    assert "REQUIRED_ISOLATION_FLAG_MISSING:--network=none" in validate_candidate_argv(stripped)
    unstripped_env = [token for token in command if token != "--unsetenv-all"]
    assert "REQUIRED_ISOLATION_FLAG_MISSING:--unsetenv-all" in validate_candidate_argv(
        unstripped_env)


def test_opencode_go_egress_design_is_host_restricted() -> None:
    assert OPENCODE_GO_EGRESS.violations(
        host="opencode.ai", port=443, method="POST",
        path="/inference/go/openai/v1/chat/completions") == ()
    assert "EGRESS_HOST_PORT_NOT_ALLOWED" in OPENCODE_GO_EGRESS.violations(
        host="api.deepseek.com", port=443, method="POST", path="/chat/completions")
    assert "EGRESS_HOST_PORT_NOT_ALLOWED" in OPENCODE_GO_EGRESS.violations(
        host="opencode.ai", port=80, method="POST", path="/inference/go/openai/v1/chat/completions")
    assert "EGRESS_PATH_NOT_ALLOWED" in OPENCODE_GO_EGRESS.violations(
        host="opencode.ai", port=443, method="POST", path="/v1/chat/completions")
    assert "EGRESS_METHOD_NOT_ALLOWED" in OPENCODE_GO_EGRESS.violations(
        host="opencode.ai", port=443, method="GET", path="/inference/go/models")
