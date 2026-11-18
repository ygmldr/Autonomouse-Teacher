"""G4-B-09/B10: the candidate stage carries no trusted code or key material.

The candidate stage is the only code the untrusted principal can read.  These
checks are structural and read-only:

* no candidate path lives under ``src/`` or contains the trusted package name;
* no candidate ``.py`` file mentions ``autoteacher_m0`` (so it cannot import it);
* no key-like filename is shipped (``etc/passwd``/``etc/group`` are synthetic);
* the candidate overlay never references trusted state (``/work/state``);
* the built adapter and skill bytes equal the frozen build metadata and policy;
* the stage tree/manifest re-hash to the G4-00 canonical values, and the stage
  is *not* the old G3-C stage (``attempts.py`` differs from the ``e6fde1c``
  batch hash).
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
G4_SCRIPTS = REPO_ROOT / "scripts" / "g4"
if str(G4_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(G4_SCRIPTS))

import lib_g4 as lib  # noqa: E402

STAGE = lib.STAGE_DEFAULT
OLD_G3C_ATTEMPTS = "33017e75871714f8d97d409ff6f26f4848c9d22de4b0bc002c9e6bb39de99167"
OLD_G3C_STAGE_TREE = "fcdb0de442d455f89fe849c736679f831c15c50f76e3e4844d38f2963e3735b0"

pytestmark = pytest.mark.skipif(not STAGE.is_dir(),
                                reason="frozen G3-D stage not present")


def _rows() -> dict[str, dict]:
    manifest = lib.load_stage_manifest(STAGE)
    return lib.stage_rows(manifest, "candidate")


def test_candidate_stage_has_no_trusted_paths() -> None:
    rows = _rows()
    assert rows
    forbidden = [path for path in rows
                 if path.startswith("src/") or "autoteacher_m0" in path
                 or path.startswith("trusted/")]
    assert forbidden == []
    # the only python files are the entrypoint and the audited probe allow-list
    python_files = sorted(path for path in rows if path.endswith(".py"))
    assert python_files
    for path in python_files:
        assert path == "run/candidate_entry.py" or path.startswith(
            ("run/probes/", "run/d3-probes/")), path


IMPORT_PATTERN = re.compile(
    r"^\s*(?:from\s+autoteacher_m0(?:\.[\w.]+)?\s+import|import\s+autoteacher_m0)",
    re.MULTILINE)


def test_candidate_python_never_imports_the_trusted_package() -> None:
    """Module *names* may appear only inside negative import probes."""
    rows = _rows()
    statements = []
    for path in rows:
        if not path.endswith(".py"):
            continue
        text = (STAGE / "candidate" / path).read_text(encoding="utf-8",
                                                      errors="replace")
        statements.extend(f"{path}: {match.group(0).strip()}"
                          for match in IMPORT_PATTERN.finditer(text))
    assert statements == []
    # every mention is inside an explicit "must fail to import" probe
    entry = (STAGE / "candidate" / "run" / "candidate_entry.py").read_text(
        encoding="utf-8")
    assert "principal_checks" in entry
    probes = sorted(path for path in rows
                    if path.endswith(".py") and "autoteacher_m0" in
                    (STAGE / "candidate" / path).read_text(encoding="utf-8",
                                                           errors="replace"))
    allowed_mentions = ("run/probes/", "run/d3-probes/")
    assert all(path == "run/candidate_entry.py"
               or path.startswith(allowed_mentions) for path in probes), probes


DEPENDENCY_PREFIXES = ("node_modules/", "pkg-cache/", "native-cache/")


def test_candidate_stage_has_no_key_like_files() -> None:
    """Candidate-controlled files only; vendored bundles are tree-digested."""
    rows = _rows()
    allowed = {"etc/passwd", "etc/group"}
    suspicious = []
    for path in rows:
        if path in allowed or path.startswith(DEPENDENCY_PREFIXES):
            continue
        name = Path(path).name.lower()
        if any(marker in name for marker in ("key", "secret", "token",
                                             "credential", "password", ".pem",
                                             ".p12", ".pfx")):
            suspicious.append(path)
    assert suspicious == []
    # and no private-key material or key sentinel inside those files
    leaks = []
    for path in rows:
        if path.startswith(DEPENDENCY_PREFIXES) or not path.endswith(
                (".py", ".yml", ".yaml", ".json")):
            continue
        text = (STAGE / "candidate" / path).read_text(encoding="utf-8",
                                                      errors="replace")
        # Runtime-built markers: the G4-A static source scan must not match
        # this test's own literal (the scan semantics below are unchanged).
        pem_markers = ("BEGIN RSA " + "PRIVATE KEY", "BEGIN " + "PRIVATE KEY")
        if any(marker in text for marker in pem_markers):
            leaks.append(path)
        if re.search(r"sk-[A-Za-z0-9]{16,}", text):
            leaks.append(path)
    assert leaks == []
    passwd = (STAGE / "candidate" / "etc" / "passwd").read_text(encoding="utf-8")
    assert "nobody" in passwd and "x:" in passwd
    assert "BEGIN" not in passwd


def test_candidate_overlay_never_references_trusted_state() -> None:
    raw = (STAGE / "candidate" / "config" / "bridge.patch.yml").read_text(
        encoding="utf-8")
    overlay = "\n".join(line for line in raw.splitlines()
                        if not line.lstrip().startswith("#"))
    assert "/work/state" not in overlay
    assert "/project/src" not in overlay
    assert "admission" not in overlay.lower()
    assert "broker" not in overlay.lower()
    assert "sk-" not in overlay
    # the only inserted code is the fixed bridge provider and the skill plugin
    inserts = [line.strip() for line in overlay.splitlines()
               if line.strip().startswith(("name:", "      name:"))]
    assert inserts
    for line in inserts:
        assert "/project/runtime/" in line, line


def test_built_adapter_matches_build_meta_and_policy() -> None:
    policy = lib.load_policy()
    candidate = STAGE / "candidate"
    built = candidate / "runtime" / "bridge" / "lib" / "index.js"
    meta = json.loads((candidate / "runtime" / "bridge" /
                       "build-meta.json").read_text(encoding="utf-8"))
    built_sha = lib.sha256_file(built)
    assert built_sha == meta["builtJs"]["sha256"]
    assert built_sha == policy["stage_binding"]["adapter_built_js_sha256"]
    assert meta["builtJs"]["path"] == "lib/index.js"
    assert meta["node"] == policy["environment_binding"]["node_version"]
    assert meta["dshLlmVersion"] == policy["environment_binding"]["dsh_runtime_version"]
    source = candidate / "runtime" / "bridge" / "index.ts"
    assert not source.exists()
    # the source blob that produced those bytes is the frozen spike file
    assert meta["inputSourceSha256"] == lib.sha256_file(
        REPO_ROOT / "spikes" / "g3b-trusted-bridge" / "src" / "index.ts")


def test_skill_artifact_and_schema_are_the_frozen_ones() -> None:
    skill_root = STAGE / "candidate" / "runtime" / "skill" / "lib"
    for name in ("index.js", "index.d.ts", "skills.json", "fixture.sha256"):
        assert (skill_root / name).is_file()
    skills = json.loads((skill_root / "skills.json").read_text(encoding="utf-8"))
    ids = {entry["id"] for entry in skills["skills"]}
    assert {"binary_search", "monotonicity", "loop_invariants"} <= ids
    fixture = json.loads((STAGE / "candidate" / "fixtures" /
                          "capture-tools.json").read_text(encoding="utf-8"))
    assert [tool["name"] for tool in fixture["tools"]] == ["skill_lookup"]


def test_stage_manifest_rows_match_disk() -> None:
    for section in ("trusted", "candidate"):
        rows = lib.stage_rows(lib.load_stage_manifest(STAGE), section)
        assert rows
        mismatched = []
        for relative, row in rows.items():
            path = STAGE / section / relative
            if not path.is_file() or lib.sha256_file(path) != row.get("sha256"):
                mismatched.append(f"{section}/{relative}")
        assert mismatched == []


def test_stage_is_canonical_and_not_the_old_g3c_stage() -> None:
    manifest = lib.load_stage_manifest(STAGE)
    assert manifest["_manifest_sha256"] == lib.STAGE_MANIFEST_CANON
    first = lib.canonical_tar_sha256(STAGE)
    second = lib.canonical_tar_sha256(STAGE)
    assert first == second == lib.STAGE_TREE_CANON
    assert first != OLD_G3C_STAGE_TREE
    attempts = STAGE / "trusted" / "src" / "autoteacher_m0" / "bridge" / "attempts.py"
    assert lib.sha256_file(attempts) != OLD_G3C_ATTEMPTS
    assert lib.sha256_file(attempts) == lib.git_blob_sha256(
        lib.PRODUCT_BASE, "src/autoteacher_m0/bridge/attempts.py")


def test_admission_and_controller_templates_pin_the_sandbox() -> None:
    policy = lib.load_policy()
    admission = lib._load_json(STAGE / "trusted" / "templates" /
                               "admission.template.json")
    controller = lib._load_json(STAGE / "trusted" / "templates" /
                                "controller.template.json")
    assert admission["route"] == policy["route"]
    assert admission["limits"] == policy["admission_limits"]
    assert admission["synthetic"] is True
    assert admission["launcher"]["uid"] == 65534
    assert controller["socket_path"] == "/work/g3b/bridge.sock"
    assert controller["expected_peer_uid"] == 65534
    assert controller["socket_mode"] == 0o660
    assert controller["socket_gid"] is None
