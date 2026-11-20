"""G4-R R3 registry probe tests.

These tests exercise the *host-side* probe harness only. They never contact a
network, never read a key and never modify the frozen Stage or runtime binary.

The runtime integration test is skipped unless all of the following are set:

    G4R_RUN_RUNTIME=1
    G4R_STAGE=/path/to/candidate-stage   # must contain runtime/{bridge,skill}/lib/index.js
    G4R_RUNTIME=/path/to/deepseek-harness-sdk-runtime-linux-x64 (optional)

Otherwise the case is reported as BLOCKED (skip), never as PASS.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PROBE_DIR = REPO_ROOT / "scripts" / "g4r" / "registry_probe"
RUNNER_PATH = PROBE_DIR / "run_host_probe.py"
PLUGIN_PATH = PROBE_DIR / "probe_plugin" / "lib" / "index.js"
SCHEMA_PATH = PROBE_DIR / "snapshot.schema.json"
POLICY_PATH = REPO_ROOT / "config" / "g4" / "runtime-policy.json"
FROZEN_PATCH_PATH = REPO_ROOT / "config" / "g3d" / "candidate" / "bridge.patch.yml"


def _load_runner():
    spec = importlib.util.spec_from_file_location("g4r_registry_run_host_probe", RUNNER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_approved_digest_is_bound_to_frozen_policy() -> None:
    """The probe's approved digest must equal the frozen runtime-policy entry."""
    runner = _load_runner()
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    approved = policy["approved_tools"]
    assert approved == [{"name": runner.APPROVED_TOOL_NAME, "sha256": runner.APPROVED_TOOL_SHA256}]
    # The freeze stays UNVERIFIED: this probe must never flip the policy status.
    assert policy["registry_status"] == "UNVERIFIED_NO_AUTHORITATIVE_MERGED_EXPORT"


def test_probe_plugin_uses_only_public_plugin_surface_and_node_builtins() -> None:
    """The probe must be a plain Cordis plugin with no network/dependency imports."""
    source = PLUGIN_PATH.read_text(encoding="utf-8")
    assert "export const name = 'g4r-registry-probe'" in source
    assert "export const inject = ['tools', 'llm']" in source
    assert "export function apply(ctx, config = {})" in source
    imports = re.findall(r"^import\s+.*?from\s+'([^']+)'", source, re.MULTILINE)
    assert imports, "probe plugin must import from node builtins"
    for specifier in imports:
        assert specifier.startswith("node:"), f"unexpected non-builtin import: {specifier}"
    for forbidden in ("node:http", "node:https", "node:net", "node:tls", "node:dgram", "node:child_process"):
        assert forbidden not in imports, f"network/process import is not allowed: {forbidden}"
    # No prompt/argument/secret capture in the emitted records.
    for forbidden_key in ('"prompt"', '"args"', '"apiKey"', '"messages"'):
        assert forbidden_key not in source


def test_snapshot_schema_is_strict_and_contains_no_content_fields() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert schema["additionalProperties"] is False
    allowed = set(schema["properties"])
    for forbidden in ("prompt", "messages", "args", "content", "apiKey", "secret", "sessionText"):
        assert forbidden not in allowed
    digest = schema["$defs"]["toolDigest"]["properties"]["sha256"]
    assert digest["pattern"] == "^[0-9a-f]{64}$"
    assert "L1-INSTRUMENTED-OBSERVATION" in json.dumps(schema)


def test_frozen_patch_rewrites_to_test_copy_stage_paths(tmp_path: Path) -> None:
    """Path rewriting is the only mutation of the frozen overlay (test copy)."""
    runner = _load_runner()
    stage = tmp_path / "stage"
    (stage / "runtime" / "bridge" / "lib").mkdir(parents=True)
    (stage / "runtime" / "skill" / "lib").mkdir(parents=True)
    (stage / "runtime" / "bridge" / "lib" / "index.js").write_text("export {}\n", encoding="utf-8")
    (stage / "runtime" / "skill" / "lib" / "index.js").write_text("export {}\n", encoding="utf-8")
    frozen = FROZEN_PATCH_PATH.read_text(encoding="utf-8")
    rewritten = runner.rewrite_frozen_patch(frozen, stage)
    assert "/project/runtime/bridge/lib/index.js" not in rewritten
    assert "/project/runtime/skill/lib/index.js" not in rewritten
    assert (stage / "runtime" / "bridge" / "lib" / "index.js").as_uri() in rewritten
    assert (stage / "runtime" / "skill" / "lib" / "index.js").as_uri() in rewritten
    # The disabled-tool entries from the frozen overlay are preserved verbatim.
    assert "disabled: true" in rewritten
    assert "id: g3b-trusted-bridge-provider" in rewritten
    assert "id: offline-public-skill" in rewritten


def test_probe_patch_composes_probe_entry_only(tmp_path: Path) -> None:
    runner = _load_runner()
    plugin = tmp_path / "probe.js"
    plugin.write_text("export {}\n", encoding="utf-8")
    text = runner.probe_patch_yml(plugin, {"mode": "observe", "approved": []})
    assert "- id: g4r-registry-probe" in text
    assert plugin.as_uri() in text
    assert text.startswith("# G4-R R3 instrumented probe overlay")


@pytest.mark.skipif(
    os.environ.get("G4R_RUN_RUNTIME") != "1" or not os.environ.get("G4R_STAGE"),
    reason="BLOCKED: set G4R_RUN_RUNTIME=1 and G4R_STAGE to run the frozen-runtime probe",
)
def test_frozen_runtime_observe_probe(tmp_path: Path) -> None:
    """Integration: complete registry == approved set on the frozen runtime."""
    runner = _load_runner()
    stage = Path(os.environ["G4R_STAGE"])
    runtime = os.environ.get("G4R_RUNTIME", "")
    runner.main([  # type: ignore[arg-type]
        "--stage", str(stage),
        "--out", str(tmp_path),
        "--mode", "observe",
        "--prompt-wait", "5",
        *(["--runtime", runtime] if runtime else []),
    ])
    run_dirs = sorted(tmp_path.glob("*observe"))
    assert run_dirs, "probe run directory missing"
    summary = json.loads((run_dirs[-1] / "run-summary.json").read_text(encoding="utf-8"))
    analysis = summary["analysis"]
    assert summary["probe_records"] > 0
    assert analysis["dispatch_count"] >= 1, "effective provider-facing tool face was not observed"
    assert analysis["registry_union_names"] == [runner.APPROVED_TOOL_NAME]
    assert analysis["dispatch_face_approved"] is True
    assert analysis["dispatch_registry_approved"] is True
    assert analysis["face_equals_registry"] is True
