"""A-NEXT A-PR2 registry attack-matrix tests.

Unit tests are host-only and never contact a network or a key. The runtime
integration test is gated: it is skipped (reported BLOCKED, never PASS) unless

    G4R_RUN_RUNTIME=1
    G4R_STAGE=/path/to/candidate-stage   # has runtime/{bridge,skill}/lib/index.js

The unit tests also re-run the forged/replay attack on synthetic records, so the
"self-report is forgeable" conclusion is executable, not just prose.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_DIR = REPO_ROOT / "scripts" / "a_next" / "registry"
RUNNER_PATH = REGISTRY_DIR / "run_matrix.py"
FORGERY_PATH = REGISTRY_DIR / "forged_replay_attack.py"
FAKE_BRIDGE_PATH = REGISTRY_DIR / "fake_bridge.py"
PLUGIN_PATH = REGISTRY_DIR / "probe_plugin" / "lib" / "index.js"
POLICY_PATH = REPO_ROOT / "config" / "g4" / "runtime-policy.json"
FROZEN_PATCH_PATH = REPO_ROOT / "config" / "g3d" / "candidate" / "bridge.patch.yml"


def _load(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_approved_digest_bound_to_frozen_policy_and_policy_unchanged() -> None:
    runner = _load(RUNNER_PATH, "a_next_run_matrix")
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    assert policy["approved_tools"] == [{"name": runner.APPROVED_NAME,
                                         "sha256": runner.APPROVED_SHA256}]
    # A-PR2 never resolves the frozen registry status.
    assert policy["registry_status"] == "UNVERIFIED_NO_AUTHORITATIVE_MERGED_EXPORT"


def test_attack_matrix_covers_required_cases() -> None:
    runner = _load(RUNNER_PATH, "a_next_run_matrix_modes")
    modes = set(runner.MODES)
    required = {
        "register-unregister", "schema-drift", "duplicate-name", "internal-execute",
        "observer-loss", "late-bash-before-dispatch", "two-turn-bash",
        "two-turn-internal-execute", "two-turn-title", "resume", "baseline",
    }
    assert required <= modes
    assert runner.MODES["two-turn-bash"]["turns"] == 2
    assert runner.MODES["two-turn-bash"]["probe_mode"] == "enforce"
    assert runner.MODES["resume"]["resume"] is True
    assert runner.FAKE_BRIDGE_MODES == {"two-turn-bash", "two-turn-internal-execute",
                                        "two-turn-title", "resume"}


def test_probe_plugin_is_same_trust_domain_diagnostic_only() -> None:
    source = PLUGIN_PATH.read_text(encoding="utf-8")
    assert "export const inject = ['tools', 'llm']" in source
    imports = re.findall(r"^import\s+.*?from\s+'([^']+)'", source, re.MULTILINE)
    assert imports, "probe must import from Node builtins"
    for specifier in imports:
        assert specifier.startswith("node:"), f"unexpected import: {specifier}"
    for forbidden in ("node:http", "node:https", "node:net", "node:dgram", "node:child_process"):
        assert forbidden not in imports
    # The plugin must self-describe as an L1 diagnostic, not an attestation.
    assert "L1 DIAGNOSTIC" in source
    assert "NOT\n * an attestation" in source or "NOT an attestation" in source.replace("\n", " ")
    for forbidden_key in ('"prompt"', '"apiKey"', '"secret"'):
        assert forbidden_key not in source


def test_frozen_patch_rewrite_preserves_disabled_entries(tmp_path: Path) -> None:
    runner = _load(RUNNER_PATH, "a_next_run_matrix_patch")
    stage = tmp_path / "stage"
    (stage / "runtime" / "bridge" / "lib").mkdir(parents=True)
    (stage / "runtime" / "skill" / "lib").mkdir(parents=True)
    (stage / "runtime" / "bridge" / "lib" / "index.js").write_text("export {}\n")
    (stage / "runtime" / "skill" / "lib" / "index.js").write_text("export {}\n")
    rewritten = runner.rewrite_frozen_patch(FROZEN_PATCH_PATH.read_text(encoding="utf-8"), stage)
    assert "/project/runtime/bridge/lib/index.js" not in rewritten
    assert "/project/runtime/skill/lib/index.js" not in rewritten
    assert (stage / "runtime" / "bridge" / "lib" / "index.js").as_uri() in rewritten
    assert (stage / "runtime" / "skill" / "lib" / "index.js").as_uri() in rewritten
    for disabled in ("llm-deepseek", "compaction-basic", "image-offload", "tool-fs",
                     "subprocess", "terminal-bash"):
        assert f"id: {disabled}" in rewritten
    assert rewritten.count("disabled: true") == FROZEN_PATCH_PATH.read_text(
        encoding="utf-8").count("disabled: true")


def test_forgery_replay_suppression_are_accepted_by_naive_verifier(tmp_path: Path) -> None:
    attack = _load(FORGERY_PATH, "a_next_forgery")
    genuine = [
        {"kind": "registry_snapshot", "epoch": 0, "definitions": [], "schemas": []},
        {"kind": "dispatch_tool_face", "epoch": 1, "tool_names": ["bash", "skill_lookup"],
         "tool_digests": [{"name": "bash", "sha256": "0" * 64},
                          {"name": attack.APPROVED_NAME, "sha256": attack.APPROVED_SHA256}],
         "registry_names": ["bash", "skill_lookup"], "unknown": [{"name": "bash"}],
         "registry_unknown": [{"name": "bash"}], "run_label": "run-a"},
    ]
    assert attack.naive_verifier(genuine)["accepted"] is False
    forged = attack.forge_events(genuine)
    assert attack.naive_verifier(forged)["accepted"] is True
    clean = [{"kind": "dispatch_tool_face", "epoch": 1, "run_label": "run-b",
              "tool_names": [attack.APPROVED_NAME],
              "tool_digests": list(attack.APPROVED),
              "registry_names": [attack.APPROVED_NAME],
              "unknown": [], "registry_unknown": []}]
    replayed = attack.replay_events(clean, "run-a")
    assert attack.naive_verifier(replayed)["accepted"] is True
    suppressed = attack.suppress_events(genuine, clean, "run-a")
    assert attack.naive_verifier(suppressed)["accepted"] is True


def test_fake_bridge_frames_are_hash_bound_and_ordered() -> None:
    fake = _load(FAKE_BRIDGE_PATH, "a_next_fake_bridge")
    transport = "tr-" + "a" * 32
    frames = fake.reply_text(transport)
    decoded = [json.loads(frame) for frame in frames]
    assert [frame["kind"] for frame in decoded] == [
        "ack", "chunk", "chunk", "chunk", "chunk", "finish"]
    assert [frame["seq"] for frame in decoded] == [1, 2, 3, 4, 5, 6]
    for frame in decoded:
        expected = fake.hashlib.sha256(fake.canonical_json(frame["payload"]).encode()).hexdigest()
        assert frame["hash"] == expected
        assert frame["transport_id"] == transport


@pytest.mark.skipif(
    os.environ.get("G4R_RUN_RUNTIME") != "1" or not os.environ.get("G4R_STAGE"),
    reason="BLOCKED: set G4R_RUN_RUNTIME=1 and G4R_STAGE for the frozen-runtime attacks",
)
def test_runtime_attack_matrix_two_turn_and_internal_execute(tmp_path: Path) -> None:
    runner = _load(RUNNER_PATH, "a_next_run_matrix_integration")
    stage = Path(os.environ["G4R_STAGE"])
    results = {}
    for mode in ("baseline", "two-turn-bash", "internal-execute"):
        results[mode] = runner.run_mode(mode, type("Args", (), {  # noqa: SLF001
            "stage": str(stage), "runtime": "", "out": str(tmp_path),
            "prompt_wait": 3.0, "turn_gap": 3.0, "keep_workdir": False,
        })())
    baseline = results["baseline"]["analysis"]
    assert baseline["verdicts"]["complete-registry-baseline"] == "MEASURED_PASS"
    two_turn = results["two-turn-bash"]["analysis"]
    assert two_turn["verdicts"]["second-turn-deny-after-late-register"] == "MEASURED_PASS"
    assert two_turn["fake_bridge_request_count"] == 1
    internal = results["internal-execute"]["analysis"]
    assert internal["internal_execute_sentinel_written"] is True
    assert "g4r_internal_marker" not in internal["dispatch_faces_union"]
