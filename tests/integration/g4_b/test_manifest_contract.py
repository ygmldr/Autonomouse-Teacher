"""G4-B manifest canonicalisation contract (host-only, no container, no network).

These tests exercise the deterministic closure itself:

* the checked-in spec is valid and declares every required root;
* two builds of unchanged bytes produce the same digest **and** the same bytes;
* wall-clock provenance is excluded from the digest but still written;
* list order is fixed by POSIX relative path, and modes/sizes are recorded;
* the manifest never contains or lists itself, so its digest is recomputable;
* on the real repo the derived facts (tool schema sha, route, limits, price)
  match the checked-in policy — this is the B03/B04 binding, not a registry
  claim.

Nothing here starts a container or touches the network.
"""
from __future__ import annotations

from pathlib import Path
import sys

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
G4_SCRIPTS = REPO_ROOT / "scripts" / "g4"
if str(G4_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(G4_SCRIPTS))

import lib_g4 as lib  # noqa: E402


def _mini_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "src" / "pkg").mkdir(parents=True)
    (root / "src" / "pkg" / "b.py").write_text("B = 2\n", encoding="utf-8")
    (root / "src" / "pkg" / "a.py").write_text("A = 1\n", encoding="utf-8")
    (root / "src" / "pkg" / "notes.txt").write_text("not python\n", encoding="utf-8")
    (root / "config").mkdir()
    (root / "config" / "policy.json").write_text('{"x": 1}\n', encoding="utf-8")
    (root / "tree").mkdir()
    (root / "tree" / "one.txt").write_text("one\n", encoding="utf-8")
    return root


def _mini_spec() -> dict:
    return {
        "schema": lib.SPEC_SCHEMA,
        "canonicalization": {
            "json_sort_keys": True,
            "json_separators": [",", ":"],
            "json_ensure_ascii": False,
            "trailing_newline": True,
            "path_sort": "unicode-codepoint-ascending on POSIX relative path",
            "mode_format": "4-digit octal",
            "digest": "sha256 over canonical JSON of the digest-covered keys",
        },
        "roots": [
            {"root_id": "trusted_src", "kind": "worktree_tree",
             "root": "src/pkg", "suffixes": [".py"], "exclude_dirs": []},
            {"root_id": "policy", "kind": "file_set",
             "paths": ["config/policy.json"]},
            {"root_id": "mini_tree", "kind": "tree", "path": "tree"},
        ],
    }


def test_checked_in_spec_is_valid_and_complete() -> None:
    spec = lib.load_spec()
    assert lib.spec_problems(spec) == []
    root_ids = {root["root_id"] for root in spec["roots"]}
    for required in lib.REQUIRED_ROOT_IDS:
        assert required in root_ids
    kinds = {root["root_id"]: root["kind"] for root in spec["roots"]}
    assert kinds["trusted_src"] == "worktree_tree"
    assert kinds["candidate_stage"] == "stage_section"
    assert kinds["runtime_rootfs"] == "canonical_tree"
    assert kinds["runtime_dsh"] == "file"
    # the stage the spec pins is the frozen G3-D stage
    candidate = next(root for root in spec["roots"]
                     if root["root_id"] == "candidate_stage")
    assert candidate["section"] == "candidate"
    assert set(candidate["tree_prefixes"]) == {"node_modules", "native-cache",
                                               "pkg-cache"}


def test_build_is_deterministic_and_excludes_provenance(tmp_path: Path) -> None:
    root = _mini_repo(tmp_path)
    spec = _mini_spec()
    first = lib.build_manifest(spec, repo_root=root, anchor_mode="none",
                               provenance={"utc": "2026-01-01T00:00:00Z"})
    second = lib.build_manifest(spec, repo_root=root, anchor_mode="none",
                                provenance={"utc": "2026-02-02T00:00:00Z"})
    assert first["digest"]["value"] == second["digest"]["value"]
    assert lib.digest_of(first) == lib.digest_of(second)
    # provenance is written but never digested
    assert first["provenance"]["utc"] != second["provenance"]["utc"]
    assert lib.manifest_bytes(first) != lib.manifest_bytes(second)
    assert lib.digest_of({**first, "provenance": {"utc": "other"}}) == \
        first["digest"]["value"]
    # the digest itself is not part of the coverage
    assert "digest" in first["digest"]["excludes"]
    assert "provenance" in first["digest"]["excludes"]


def test_rows_are_sorted_and_record_mode_and_size(tmp_path: Path) -> None:
    root = _mini_repo(tmp_path)
    content = lib.build_content(_mini_spec(), repo_root=root, anchor_mode="none")
    src_rows = content["inputs"]["trusted_src"]["files"]
    assert [row["path"] for row in src_rows] == ["a.py", "b.py"]
    for row in src_rows:
        assert row["mode"] == "0644"
        assert row["bytes"] == len((root / "src" / "pkg" / row["path"]).read_bytes())
        assert len(row["sha256"]) == 64
    # non-matching suffixes are not silently included
    assert "notes.txt" not in {row["path"] for row in src_rows}


def test_manifest_does_not_reference_itself(tmp_path: Path) -> None:
    root = _mini_repo(tmp_path)
    document = lib.build_manifest(_mini_spec(), repo_root=root, anchor_mode="none")
    serialised = lib.manifest_bytes(document).decode("utf-8")
    assert "manifest.json" not in serialised
    assert "manifest.sha256" not in serialised
    assert lib.digest_of(document) == document["digest"]["value"]


def test_real_spec_derived_facts_match_policy() -> None:
    """B03/B04 binding: the captured tool schema equals the approved policy."""
    if not lib.STAGE_DEFAULT.is_dir():
        pytest.skip("frozen G3-D stage not present in this environment")
    policy = lib.load_policy()
    assert lib.policy_problems(policy) == []
    content = lib.build_content(lib.load_spec(), anchor_mode="full")
    derived = content["derived"]
    approved = [(tool["name"], tool["sha256"]) for tool in policy["approved_tools"]]
    captured = [(tool["name"], tool["sha256"])
                for tool in derived["tool_schemas"]["tools"]]
    assert captured == approved
    assert derived["tool_schemas"]["source_sha256"] == lib.sha256_file(
        lib.STAGE_DEFAULT / "candidate" / "fixtures" / "capture-tools.json")
    assert derived["admission_binding"]["route"] == policy["route"]
    assert derived["admission_binding"]["limits"] == policy["admission_limits"]
    assert derived["broker_policy"]["limits"] == policy["broker_limits"]
    assert derived["broker_policy"]["price"] == policy["price"]
    assert derived["registry_status"] == policy["registry_status"]
    # the merged config layers are facts, not prose
    layers = derived["config_merge_layers"]
    assert [layer["order"] for layer in layers] == [1, 2, 3, 4]
    assert layers[1]["path"] == "candidate/config/bridge.patch.yml"
    assert layers[1]["sha256"] == lib.sha256_file(
        lib.STAGE_DEFAULT / "candidate" / "config" / "bridge.patch.yml")


def test_real_anchor_is_the_frozen_baseline() -> None:
    if not lib.STAGE_DEFAULT.is_dir():
        pytest.skip("frozen G3-D stage not present in this environment")
    content = lib.build_content(lib.load_spec(), anchor_mode="full")
    anchor = content["anchor"]
    assert anchor["product_commit"] == lib.PRODUCT_BASE
    assert anchor["rootfs"]["sha256"] == lib.ROOTFS_CANON
    assert anchor["deps"]["sha256"] == lib.DEPS_CANON
    assert anchor["stage"]["tree_sha256"] == lib.STAGE_TREE_CANON
    assert anchor["stage"]["manifest_sha256"] == lib.STAGE_MANIFEST_CANON
    assert anchor["dsh_runtime"]["sha256"] == lib.DSH_RUNTIME_CANON
    # stage rows claim git_blob provenance and are byte-identical to it
    trusted = content["inputs"]["trusted_stage"]
    claimed = [row for row in trusted["files"]
               if (row.get("source") or {}).get("kind") == "git_blob"]
    assert claimed
    for row in claimed:
        assert row["sha256"] == lib.git_blob_sha256(
            row["source"]["commit"], row["source"]["path"])
    # the old G3-C stage must not be what this manifest describes
    assert "fcdb0de442d455f89fe849c736679f831c15c50f76e3e4844d38f2963e3735b0" \
        != anchor["stage"]["tree_sha256"]
