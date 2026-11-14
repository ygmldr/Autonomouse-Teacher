"""Static consistency checks for the PR2 target profile (no runtime, no key).

These assertions run inside the fixed no-Key OCI test container as part of the
project test suite; they never start the runtime, read a credential or call a
model. Runtime/dump-config evidence lives under artifacts/m0-runtime-integration.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[3]
PATCH = REPO / "config/dsh/target-runtime.patch.yml"
OPENCODE = REPO / "config/dsh/target-runtime-opencode-go.patch.yml"
POLICY = REPO / "config/dsh/target-broker-policy.json"
VERIFY = REPO / "scripts/verify_runtime_profile.py"


def test_required_files_exist_and_are_read_only_text() -> None:
    for path in (PATCH, OPENCODE, POLICY, VERIFY):
        assert path.is_file(), path
        assert path.stat().st_mode & 0o222 == 0, path


def test_target_patch_has_guard_fixture_and_disabled_real_routes() -> None:
    text = PATCH.read_text(encoding="utf-8")
    for row in ("runtime-budget-guard", "offline-test-only-provider", "offline-public-skill"):
        assert f"id: {row}" in text, row
    for row in ("llm-deepseek", "tool-fs", "subprocess", "terminal-bash"):
        assert f"- id: {row}\n  disabled: true" in text, row
    rows = yaml.load(text, Loader=yaml.SafeLoader)
    inserted = [row for row in rows if "insert" in row][0]["insert"]
    guard = next(row for row in inserted if row["id"] == "runtime-budget-guard")
    assert guard["config"]["policy"] == {
        "provider": "offline-test-only", "model": "fixture-v1",
        "brokerScopeId": "fixed-offline-scope", "maxOutputTokens": 1024,
        "maxInputTokens": 2500000, "maxProviderRetries": 0, "purposes": ["conversation"],
    }
    broker = guard["config"]["broker"]
    assert broker["configPath"] == "/target/runtime/broker-policy.json"
    assert broker["configSha256"] == hashlib.sha256(POLICY.read_bytes()).hexdigest()
    assert broker["python"].startswith("/") and broker["pythonPath"] == "/project/src:/deps"


def test_broker_policy_is_synthetic_single_route() -> None:
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    assert policy["v"] == 1 and policy["synthetic"] is True
    assert len(policy["routes"]) == 1
    route = policy["routes"][0]
    assert (route["route_id"], route["model"]) == ("offline-test-only", "fixture-v1")
    assert route["usage_policy"] == {"cache_write": "input_rate", "reasoning": "included_in_output"}


def test_opencode_go_overlay_is_static_placeholder_only() -> None:
    rows = yaml.load(OPENCODE.read_text(encoding="utf-8"), Loader=yaml.SafeLoader)
    inserted = [row for row in rows if "insert" in row][0]["insert"]
    route = inserted[0]["config"]["providers"]["opencode-go"]
    assert route == {"apiKeyEnv": "OPENCODE_API_KEY", "reasoning": "max",
                     "retryPolicy": {"mode": "normal", "maxRetries": 0}}
    assert "baseURL" not in route
