"""G4-B registry status contract: UNVERIFIED plus a fail-closed Controller.

The plan forbids claiming ``registry == skill_lookup only``.  These tests pin
that refusal down in executable form:

* the policy must declare ``UNVERIFIED_NO_AUTHORITATIVE_MERGED_EXPORT``;
* the probe output lists what cannot be proven and never claims a full registry;
* the merged ``--dump-config`` (if the probe artifact exists) shows the overlay
  ids disabled and the bridge/skill entries inserted;
* the captured real-DSH request fixture and the approved policy agree on the
  ``skill_lookup`` schema sha — that is the binding the Controller enforces;
* a *different* tool schema always hashes differently, so the whitelist rejects
  it before any Reserve/Claim.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
G4_SCRIPTS = REPO_ROOT / "scripts" / "g4"
if str(G4_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(G4_SCRIPTS))

import lib_g4 as lib  # noqa: E402
import probe_runtime  # noqa: E402

RUNTIME_ARTIFACTS = lib.G4_RUNTIME


def test_policy_declares_unverified_registry() -> None:
    policy = lib.load_policy()
    assert policy["registry_status"] == "UNVERIFIED_NO_AUTHORITATIVE_MERGED_EXPORT"
    assert policy["synthetic_only"] is True
    assert policy["billable_send_authorized"] is False
    assert policy["live_gate_effect"] == "NONE_BLOCKED"
    assert "skill_lookup only" not in json.dumps(policy).lower()
    assert [tool["name"] for tool in policy["approved_tools"]] == ["skill_lookup"]


def test_registry_probe_refuses_to_claim_a_full_registry(tmp_path: Path) -> None:
    policy = lib.load_policy()
    dump = {
        "entries": [
            {"id": "llm-deepseek", "disabled": "true", "config_enabled": None},
            {"id": "session-log-deepseek", "disabled": None,
             "config_enabled": "false"},
            {"id": "compaction-basic", "disabled": "true", "config_enabled": None},
            {"id": "tool-fs", "disabled": "true", "config_enabled": None},
            {"id": "g3b-trusted-bridge-provider", "disabled": None,
             "config_enabled": None},
            {"id": "offline-public-skill", "disabled": None, "config_enabled": None},
        ],
        "dump_sha256": "a" * 64,
        "entry_count": 6,
    }
    report = probe_runtime.registry_probe(dump, tmp_path, policy)
    assert report["status"] == "UNVERIFIED"
    assert report["authoritative_export"]["available"] is False
    assert len(report["cannot_prove"]) >= 4
    assert "NOT proven" in report["verdict"]
    assert "is not claimed" in report["verdict"]
    observable = report["observable"]
    assert "llm-deepseek" in observable["merged_config_dump"]["disabled_ids"]
    assert observable["merged_config_dump"]["inserted_plugin_ids"] == [
        "g3b-trusted-bridge-provider", "offline-public-skill"]
    assert observable["merged_config_dump"]["session_log_deepseek"] == {
        "present": True, "disabled": None, "config_enabled": "false"}
    assert report["fail_closed_layers"]


def test_overlay_ids_are_the_frozen_disable_list() -> None:
    assert probe_runtime.OVERLAY_DISABLED_IDS == (
        "llm-deepseek", "plugin-package-inventory-deepseek", "compaction-basic",
        "image-offload", "tool-fs", "tool-working-directory", "persistent-bash",
        "persistent-pwsh", "terminal-bash", "terminal-pwsh", "pty", "subprocess",
        "jobs",
    )
    overlay = (REPO_ROOT / "config" / "g3d" / "candidate" /
               "bridge.patch.yml").read_text(encoding="utf-8")
    for entry_id in probe_runtime.OVERLAY_DISABLED_IDS:
        assert f"- id: {entry_id}" in overlay
    for inserted in ("g3b-trusted-bridge-provider", "offline-public-skill"):
        assert inserted in overlay
    # the overlay may never point the candidate at trusted state
    assert "/work/state" not in overlay


def test_entry_parser_reads_the_real_merged_dump() -> None:
    dump_path = RUNTIME_ARTIFACTS / "merged-config.yml"
    if not dump_path.is_file():
        pytest.skip("merged --dump-config artifact not produced in this environment")
    entries = {entry["id"]: entry
               for entry in probe_runtime._parse_entries(
                   dump_path.read_text(encoding="utf-8"))}
    assert entries["llm-deepseek"]["disabled"] == "true"
    assert entries["tool-fs"]["disabled"] == "true"
    assert entries["compaction-basic"]["disabled"] == "true"
    assert entries["image-offload"]["disabled"] == "true"
    assert entries["jobs"]["disabled"] == "true"
    assert entries["session-log-deepseek"]["config_enabled"] == "false"
    assert "offline-public-skill" in entries


def test_captured_tool_schema_equals_approved_policy() -> None:
    if not lib.STAGE_DEFAULT.is_dir():
        pytest.skip("frozen G3-D stage not present in this environment")
    policy = lib.load_policy()
    fixture = (lib.STAGE_DEFAULT / "candidate" / "fixtures" /
               "capture-tools.json")
    document = json.loads(fixture.read_text(encoding="utf-8"))
    tools = document["tools"]
    assert [tool["name"] for tool in tools] == ["skill_lookup"]
    canonical = json.loads(tools[0]["canonical_json"])
    digest = lib.sha256_bytes(lib.canonical_json_bytes(canonical))
    assert digest == tools[0]["sha256"] == policy["approved_tools"][0]["sha256"]
    # the capture is a *raw request* captured from a real DSH SDK session, not a
    # hand-written schema: it carries the assembled message list too.
    raw = document["captured"]["raw_json"]["payload"]
    assert raw["provider"] == policy["route"]["provider"]
    assert raw["model"] == policy["route"]["model"]
    assert raw["tools"] == [canonical]


def test_any_schema_difference_changes_the_digest() -> None:
    if not lib.STAGE_DEFAULT.is_dir():
        pytest.skip("frozen G3-D stage not present in this environment")
    fixture = (lib.STAGE_DEFAULT / "candidate" / "fixtures" /
               "capture-tools.json")
    document = json.loads(fixture.read_text(encoding="utf-8"))
    approved = json.loads(document["tools"][0]["canonical_json"])
    approved_sha = lib.sha256_bytes(lib.canonical_json_bytes(approved))
    variants = []
    extra_property = json.loads(json.dumps(approved))
    extra_property["parameters"]["properties"]["path"] = {"type": "string"}
    variants.append(extra_property)
    renamed = json.loads(json.dumps(approved))
    renamed["name"] = "skill_lookup_shadow"
    variants.append(renamed)
    extra_desc = json.loads(json.dumps(approved))
    extra_desc["description"] += " "
    variants.append(extra_desc)
    for variant in variants:
        assert lib.sha256_bytes(lib.canonical_json_bytes(variant)) != approved_sha
