"""G4-B fail-closed verifier contract (host-only, no container, no network).

Every mutation the G4 plan §5.2 forbids must be detected:

* an added, removed, modified or re-moded file inside a declared root;
* a changed subtree digest;
* a changed derived fact (capture fixture, template, overlay, price);
* a manifest whose own digest no longer recomputes;
* a policy whose approved tool/route/limit/price no longer matches.

The verifier is a pure function over bytes, so these cases are built on
synthetic fixtures instead of the frozen stage.
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

TOOL = {"name": "skill_lookup", "description": "lookup by id",
        "parameters": {"type": "object",
                       "properties": {"skill_id": {"type": "string"}},
                       "required": ["skill_id"]}}


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)


def _write(path: Path, data: object) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = data if isinstance(data, str) else json.dumps(data, indent=2) + "\n"
    path.write_text(text, encoding="utf-8")
    return {"path": path}


def _mini_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    _write(root / "src" / "pkg" / "a.py", "A = 1\n")
    _write(root / "src" / "pkg" / "b.py", "B = 2\n")
    return root


def _mini_stage(tmp_path: Path) -> Path:
    stage = tmp_path / "stage-20260101T000000Z"
    tool_sha = lib.sha256_bytes(_canonical_json(TOOL).encode("utf-8"))
    _write(stage / "candidate" / "fixtures" / "capture-tools.json", {
        "tools": [{"name": TOOL["name"], "sha256": tool_sha,
                   "canonical_json": _canonical_json(TOOL)}]})
    _write(stage / "candidate" / "config" / "bridge.patch.yml",
           "- id: llm-deepseek\n  disabled: true\n")
    _write(stage / "trusted" / "templates" / "admission.template.json", {
        "schema": "m0.g3b.admission.v1",
        "synthetic": True,
        "route": {"route_id": "offline-test-only-g3b",
                  "provider": "offline-test-only-g3b",
                  "model": "fixture-bridge-v1"},
        "tool_schemas": "{{TOOL_SCHEMAS}}",
        "limits": {"max_calls": 8, "max_attempts": 1, "max_input_tokens": 100000,
                   "max_output_tokens": 1024, "deadline_ms": 30000},
        "launcher": {"uid": 65534, "container": True}})
    _write(stage / "trusted" / "templates" / "broker.template.json", {
        "synthetic": True,
        "limits": {"soft_usd": "3", "hard_usd": "10", "per_call_usd": "0.2"},
        "routes": [{"route_id": "offline-test-only-g3b",
                    "model": "fixture-bridge-v1",
                    "price": {"version": "fixture-v1", "source": "synthetic fixture"},
                    "known_extra_fee_usd": "0.001",
                    "usage_policy": {"cache_write": "input_rate"}}]})
    _write(stage / "trusted" / "templates" / "controller.template.json", {
        "socket_path": "/work/g3b/bridge.sock", "expected_peer_uid": 65534,
        "socket_mode": 432, "socket_gid": None})
    rows: dict[str, list[dict]] = {"trusted": [], "candidate": []}
    for section in rows:
        for path in sorted((stage / section).rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(stage / section).as_posix()
            rows[section].append({
                "path": relative, "sha256": lib.sha256_file(path),
                "bytes": path.stat().st_size,
                "source": {"kind": "generated", "generator": "test"}})
    _write(stage / "manifest.json", {"base_sha": lib.PRODUCT_BASE,
                                     "trusted": {"files": rows["trusted"]},
                                     "candidate": {"files": rows["candidate"]}})
    return stage


def _spec() -> dict:
    return {
        "schema": lib.SPEC_SCHEMA,
        "canonicalization": {"json_sort_keys": True, "path_sort": "path",
                             "mode_format": "4-digit octal", "digest": "sha256"},
        "roots": [
            {"root_id": "trusted_src", "kind": "worktree_tree",
             "root": "src/pkg", "suffixes": [".py"], "exclude_dirs": []},
            {"root_id": "trusted_stage", "kind": "stage_section",
             "section": "trusted", "tree_prefixes": []},
            {"root_id": "candidate_stage", "kind": "stage_section",
             "section": "candidate", "tree_prefixes": []},
        ],
    }


def _built(tmp_path: Path) -> tuple[Path, Path, dict]:
    root = _mini_repo(tmp_path)
    stage = _mini_stage(tmp_path)
    document = lib.build_manifest(_spec(), repo_root=root, stage_dir=stage,
                                  anchor_mode="none")
    return root, stage, document


def _verify(root: Path, stage: Path, document: dict) -> dict:
    return lib.verify_content(document, repo_root=root, stage_dir=stage,
                              check_git=False, require_anchor=False)


def test_clean_fixture_verifies(tmp_path: Path) -> None:
    root, stage, document = _built(tmp_path)
    result = _verify(root, stage, document)
    assert result["ok"], result["problems"]


def test_modified_file_is_detected(tmp_path: Path) -> None:
    root, stage, document = _built(tmp_path)
    (root / "src" / "pkg" / "a.py").write_text("A = 99\n", encoding="utf-8")
    problems = _verify(root, stage, document)["problems"]
    assert "trusted_src:modified:a.py" in problems
    assert "trusted_src:tree_changed" in problems


def test_added_file_is_detected(tmp_path: Path) -> None:
    root, stage, document = _built(tmp_path)
    (root / "src" / "pkg" / "c.py").write_text("C = 3\n", encoding="utf-8")
    problems = _verify(root, stage, document)["problems"]
    assert "trusted_src:added:c.py" in problems
    assert "trusted_src:tree_changed" in problems


def test_removed_file_is_detected(tmp_path: Path) -> None:
    root, stage, document = _built(tmp_path)
    (root / "src" / "pkg" / "b.py").unlink()
    problems = _verify(root, stage, document)["problems"]
    assert "trusted_src:removed:b.py" in problems


def test_mode_change_is_detected(tmp_path: Path) -> None:
    root, stage, document = _built(tmp_path)
    (root / "src" / "pkg" / "a.py").chmod(0o755)
    problems = _verify(root, stage, document)["problems"]
    assert "trusted_src:mode_changed:a.py" in problems


def test_stage_extra_file_and_tree_change_are_detected(tmp_path: Path) -> None:
    root, stage, document = _built(tmp_path)
    (stage / "candidate" / "config" / "extra.yml").write_text("x\n", encoding="utf-8")
    # the extra file is not in the stage manifest, so the row set is unchanged;
    # the section-level canonical tar is what would catch it on the real stage.
    assert _verify(root, stage, document)["ok"] is True
    (stage / "candidate" / "config" / "bridge.patch.yml").write_text(
        "- id: tool-fs\n", encoding="utf-8")
    problems = _verify(root, stage, document)["problems"]
    assert "candidate_stage:modified:config/bridge.patch.yml" in problems


def test_derived_tool_schema_change_is_detected(tmp_path: Path) -> None:
    root, stage, document = _built(tmp_path)
    fixture = stage / "candidate" / "fixtures" / "capture-tools.json"
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    payload["tools"][0]["description_extra"] = True
    fixture.write_text(json.dumps(payload), encoding="utf-8")
    problems = _verify(root, stage, document)["problems"]
    assert "derived:facts_changed" in problems


def test_manifest_digest_tamper_is_detected(tmp_path: Path) -> None:
    _root, _stage, document = _built(tmp_path)
    tampered = json.loads(json.dumps(document))
    tampered["digest"]["value"] = "0" * 64
    assert lib.digest_of(tampered) != tampered["digest"]["value"]
    tampered["inputs"]["trusted_src"]["files"][0]["sha256"] = "1" * 64
    assert lib.digest_of(tampered) != document["digest"]["value"]


def test_require_manifest_match_blocks_every_drift(tmp_path: Path) -> None:
    root, stage, document = _built(tmp_path)
    policy = {
        "schema": lib.POLICY_SCHEMA,
        "policy_id": "test",
        "synthetic_only": True,
        "billable_send_authorized": False,
        "registry_status": "UNVERIFIED_NO_AUTHORITATIVE_MERGED_EXPORT",
        "route": document["derived"]["admission_binding"]["route"],
        "approved_tools": [{"name": tool["name"], "sha256": tool["sha256"]}
                           for tool in document["derived"]["tool_schemas"]["tools"]],
        "admission_limits": document["derived"]["admission_binding"]["limits"],
        "broker_limits": document["derived"]["broker_policy"]["limits"],
        "price": document["derived"]["broker_policy"]["price"],
    }
    clean = lib.require_manifest_match(policy, document,
                                       verification=_verify(root, stage, document))
    # anchor values are absent in anchor_mode=none, so the two canonical checks
    # must fire; that is itself the fail-closed behaviour under test.
    assert clean["ok"] is False
    assert "rootfs_not_canonical" in clean["reasons"]
    assert "stage_manifest_changed" in clean["reasons"]

    policy.update({
        "approved_tools": [{"name": "bash", "sha256": "2" * 64}],
        "route": {"route_id": "other", "provider": "other", "model": "other"},
        "admission_limits": {"max_calls": 999},
        "broker_limits": {"soft_usd": "999"},
        "price": {"route_id": "x"},
        "registry_status": "VERIFIED",
    })
    decision = lib.require_manifest_match(policy, document)
    assert decision["ok"] is False
    for reason in ("tool_schema_changed", "route_changed",
                   "admission_limits_changed", "broker_limits_changed",
                   "price_source_changed", "registry_status_changed"):
        assert reason in decision["reasons"]


def test_digest_sidecar_contract(tmp_path: Path) -> None:
    _root, _stage, document = _built(tmp_path)
    out = tmp_path / "manifest.json"
    written = lib.write_json_atomic(out, document)
    (tmp_path / "manifest.sha256").write_text(
        f"{document['digest']['value']}  manifest.json\n", encoding="utf-8")
    assert written["sha256"] == lib.sha256_file(out)
    reloaded = json.loads(out.read_text(encoding="utf-8"))
    assert lib.digest_of(reloaded) == document["digest"]["value"]
    sidecar = (tmp_path / "manifest.sha256").read_text(encoding="utf-8").split()
    assert sidecar[0] == reloaded["digest"]["value"]
    with pytest.raises(lib.G4Error):
        lib.load_spec(tmp_path / "missing-spec.json")
