"""PR3 no-key rehearsal: controller, credentials, watchdog, blocked Live entries.

Runs only inside the fixed-digest, no-network OCI test container. It mints a
*rehearsal* Ed25519 authorization with a test-only seed, uses fake credentials,
and a hung local subprocess; it never contacts a provider, SDK or real key.
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import pytest

from autoteacher_m0.security import ed25519
from autoteacher_m0.security.authorization import (
    ApprovedRoute,
    ExpectedBindings,
)
from autoteacher_m0.security.credential_boundary import (
    LauncherOnlySecret,
    assert_log_clean,
    redact_secrets,
    scrub_candidate_env,
)
from autoteacher_m0.security.live_controller import (
    ALWAYS_BLOCKED_REASONS,
    TrustedLiveController,
    assert_live_entrypoints_blocked,
)
from autoteacher_m0.security.watchdog import (
    ExternalWatchdog,
    RunStatus,
    WatchdogPolicy,
    confirm_container_absence,
)

REPO = Path(__file__).resolve().parents[3]
NOW = datetime(2026, 11, 14, 12, 0, 0, tzinfo=timezone.utc)
SEED = bytes.fromhex("41" * 32)
KEY_ID = "human-maintainer-rehearsal"
BINDINGS = {name: char * 64 for name, char in zip(
    ("code_sha256", "lock_sha256", "runtime_sha256", "plugin_sha256", "merged_profile_sha256"),
    "67890")}
ROUTE = {"route_id": "opencode-go", "provider": "opencode-go", "model": "deepseek-v4.1-flash"}
SCOPE = "live-m0-pr3-rehearsal"
FAKE_KEY = "oc_sk_FAKE_REHEARSAL_000000000000000000000000000000000000000000000000"


def canonical(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("utf-8")


def external_fixture(root: Path) -> dict[str, Path]:
    repo = root / "repo"
    repo.mkdir()
    external = root / "external"
    external.mkdir()
    keys = external / "trusted-keys.json"
    keys.write_text(json.dumps({"schema": "at-m0/trusted-approver-keys/v1",
                                "keys": {KEY_ID: ed25519.public_key(SEED).hex()}}),
                    encoding="utf-8")
    revoked = external / "revoked.json"
    revoked.write_text(json.dumps({"schema": "at-m0/revocation/v1",
                                   "revoked_ids": []}), encoding="utf-8")
    payload = {
        "schema": "at-m0/execution-authorization/v1",
        "authorization_id": "auth-pr3-integration-rehearsal",
        "approver": "maintainer@example.invalid",
        "approval_note": "Offline PR3 rehearsal only; no key, no model call",
        "issued_utc": "2026-11-14T11:50:00Z",
        "not_before_utc": "2026-11-14T11:55:00Z",
        "expires_utc": "2026-11-14T12:30:00Z",
        "bindings": dict(BINDINGS),
        "route": dict(ROUTE),
        "allowed_tools": ["skill_lookup"],
        "budget": {"scope": SCOPE, "per_call_cap_usd": "0.10",
                   "total_cap_usd": "1.00", "max_calls": 10},
        "deadline": {"total_seconds": 120, "max_steps": 8, "max_dispatch_attempts": 8},
    }
    signed = copy.deepcopy(payload)
    signed["signature"] = {"algorithm": "ed25519", "key_id": KEY_ID,
                           "value": ed25519.sign(canonical(payload), SEED).hex()}
    authorization = external / "authorization.json"
    authorization.write_text(json.dumps(signed), encoding="utf-8")
    stage = root / "stage"
    stage.mkdir()
    return {"repo": repo, "keys": keys, "revoked": revoked, "auth": authorization,
            "stage": stage}


def controller(fixture: dict[str, Path], *, launcher_secret: LauncherOnlySecret | None = None,
               repo_root: Path = REPO) -> TrustedLiveController:
    return TrustedLiveController(
        repo_root=repo_root, authorization_path=fixture["auth"],
        trusted_keys_path=fixture["keys"], revocation_path=fixture["revoked"],
        expected=ExpectedBindings(**BINDINGS), approved_route=ApprovedRoute(**ROUTE),
        actual_tools=("skill_lookup",), budget_scope=SCOPE,
        candidate_stage=fixture["stage"], launcher_secret=launcher_secret)


def test_signed_authorization_is_valid_but_controller_still_blocked() -> None:
    with tempfile.TemporaryDirectory() as directory:
        fixture = external_fixture(Path(directory))
        decision = controller(fixture).inspect(now=NOW)
        assert decision.status == "BLOCKED"
        assert decision.authorization_approved is True
        assert decision.gate_status == "BLOCKED"
        assert decision.candidate_command_checked is True
        assert decision.boundary_deployed is False
        for reason in ALWAYS_BLOCKED_REASONS:
            assert reason in decision.reasons
        with pytest.raises(Exception) as error:
            controller(fixture).require_live(now=NOW)
        assert "BLOCKED" in str(error.value) or "EXTERNAL" in str(error.value)


def test_in_repo_authorization_and_markdown_are_rejected() -> None:
    with tempfile.TemporaryDirectory() as directory:
        fixture = external_fixture(Path(directory))
        repo_auth = fixture["repo"] / "authorization.json"
        repo_auth.write_text(fixture["auth"].read_text(encoding="utf-8"), encoding="utf-8")
        fixture["auth"] = repo_auth
        decision = controller(fixture, repo_root=fixture["repo"]).inspect(now=NOW)
        assert decision.authorization_approved is False
        assert any(reason.startswith("EXTERNAL_AUTHORIZATION_INVALID")
                   for reason in decision.reasons)
        markdown = fixture["auth"].parent / "APPROVED.md"
        markdown.write_text("# HUMAN APPROVED live=true\n", encoding="utf-8")
        fixture["auth"] = markdown
        assert controller(fixture, repo_root=fixture["repo"]).inspect(
            now=NOW).authorization_approved is False


def test_all_live_entrypoints_remain_blocked() -> None:
    assert assert_live_entrypoints_blocked(REPO) == ()
    cli = subprocess.run([sys.executable, "-c",
                          "from autoteacher_m0.cli import main; raise SystemExit(main(['smoke', '--live']))"],
                         env={"PATH": "/opt/python/bin:/usr/bin", "HOME": "/work",
                              "PYTHONPATH": "/project/src:/deps", "LANG": "C"},
                         stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, timeout=30, check=False)
    assert cli.returncode == 3
    output = json.loads(cli.stdout.decode())
    assert output["status"] == "BLOCKED"
    # The fixed OCI image intentionally has no shell, so the hard-stop script is
    # audited statically here (content/exit) and the same blocked branch is
    # exercised dynamically through the Python CLI above.
    script_text = (REPO / "scripts" / "run_live.sh").read_text(encoding="utf-8")
    assert "exit 3" in script_text
    assert "BLOCKED" in script_text
    assert "DEEPSEEK_API_KEY" not in script_text
    assert "OPENCODE_API_KEY" not in script_text
    from autoteacher_m0.contracts import RuntimeFailure
    from autoteacher_m0.runtime.dsh_adapter import HarnessAdapter
    with pytest.raises(RuntimeFailure) as error:
        HarnessAdapter._require_live_authorization()
    assert error.value.code == "SECURITY_BLOCKED"


def test_hung_mock_process_killed_and_container_absence_confirmed() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        engine = root / "fake-engine"
        engine.write_text(
            "#!/opt/python/bin/python3.11\nimport sys\n"
            "if sys.argv[1] == 'rm':\n    sys.exit(0)\n"
            "if sys.argv[1] == 'ps':\n    sys.exit(0)\n"
            "sys.exit(9)\n", encoding="utf-8")
        engine.chmod(0o755)
        process = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            start_new_session=True)
        watchdog = ExternalWatchdog(WatchdogPolicy(total_seconds=0.3, max_steps=4,
                                                   termination_grace_seconds=0.2))
        outcome = watchdog.supervise(
            process, cleanup=lambda: confirm_container_absence(
                [sys.executable, str(engine)], "at-m0-live-candidate"))
        assert outcome.status is RunStatus.TIMEOUT_KILLED
        assert outcome.kill_result is not None and outcome.kill_result.confirmed_absent
        assert outcome.pending is not None and outcome.pending.retry_allowed is False
        assert outcome.cleanup["names_after"] == ""
        assert outcome.cleanup["absence_returncode"] == 0
        assert process.poll() is not None


def test_fake_launcher_key_never_reaches_candidate_or_audit_log() -> None:
    with tempfile.TemporaryDirectory() as directory:
        fixture = external_fixture(Path(directory))
        secret = LauncherOnlySecret("OPENCODE_API_KEY", FAKE_KEY)
        decision = controller(fixture, launcher_secret=secret).inspect(now=NOW)
        audit = redact_secrets(
            f"launcher={secret!r} candidate_status={decision.status} "
            f"reasons={decision.reasons} fake={FAKE_KEY}", [FAKE_KEY])
        assert FAKE_KEY not in audit
        assert "oc_sk_" not in audit
        assert_log_clean(audit, [FAKE_KEY])
        candidate_env, violations = scrub_candidate_env(
            {"PATH": "/opt/python/bin:/usr/bin", "HOME": "/work",
             "OPENCODE_API_KEY": FAKE_KEY}, known_secret_values=[FAKE_KEY])
        assert violations and "OPENCODE_API_KEY" not in candidate_env
        assert FAKE_KEY not in repr(candidate_env)
        assert os.environ.get("OPENCODE_API_KEY") in (None, "")
        assert decision.authorization_approved is True
        assert decision.status == "BLOCKED"
