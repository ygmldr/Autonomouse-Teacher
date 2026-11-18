"""G4-B frozen runtime inventory: canonicalisation, manifest build and verify.

Scope and honesty rules (G4 plan §5, matrix G4-B-01..11):

* this module is **host-side only**: no model, no key, no network, no container
  start. It hashes bytes that are already on disk and re-reads the frozen
  G3-D stage manifest instead of inventing a second source of truth;
* the manifest is deterministic: every list is sorted by POSIX relative path,
  every mapping is serialised with ``sort_keys`` and compact separators, and
  the only non-deterministic material (wall clock, host, podman digest) lives
  in a ``provenance`` block that is **excluded** from the digest;
* the manifest never contains its own digest and never lists itself, so the
  digest can always be recomputed (``manifest_self_excluded``);
* verification is fail-closed: a missing file, an extra file inside a declared
  root, a changed byte, a changed mode, a changed tree digest or a changed
  provenance blob is reported as a problem and the caller must refuse.

Nothing here decides security on its own. The frozen LiveGate stays BLOCKED;
this module only answers "are the bytes the same bytes".
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = REPO_ROOT / "artifacts"
G4_RUNTIME = ARTIFACTS / "g4" / "runtime"
G3D_ROOT = ARTIFACTS / "g3d"
STAGE_DEFAULT = G3D_ROOT / "stage-20261117T221955Z"
ROOTFS = ARTIFACTS / "security" / "rootfs"
DEPS = ARTIFACTS / "foundation" / "deps"
DSH_RUNTIME = (DEPS / "deepseek_harness_runtime" / "runtime" /
               "deepseek-harness-sdk-runtime-linux-x64")
SPEC_PATH = REPO_ROOT / "config" / "g4" / "inventory.spec.json"
POLICY_PATH = REPO_ROOT / "config" / "g4" / "runtime-policy.json"

SCHEMA = "m0.g4b.inventory.v1"
SPEC_SCHEMA = "m0.g4b.inventory.spec.v1"
POLICY_SCHEMA = "m0.g4b.runtime.policy.v1"
PRODUCT_BASE = "cf40c6bfb84ceae98e795db19efa955aa3035991"
# Canonical values recomputed by G4-00 (docs/M0_G4_00_BASELINE.md §2.1).
ROOTFS_CANON = "25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0"
DEPS_CANON = "e07729d7997944417b1c25531749b3e6e5e34aa4248f01dc8f370282082ecb98"
STAGE_TREE_CANON = "e1ff14496e06dcb1c887badfb93b858012373be9fe739e61bb04587885e9f9c5"
STAGE_MANIFEST_CANON = "644823d46adaef28810ba13bb97547371616177bbc4b8138b1eaed5d9a28eb03"
DSH_RUNTIME_CANON = "1cc41d5a8745a5b9d47c8604e44f23eb8af2d8ca02b2afa0be101d5f71be6ea4"

EXIT_OK = 0
EXIT_DRIFT = 4
EXIT_SELF_DIGEST = 5
EXIT_SPEC_INVALID = 6
EXIT_ENVIRONMENT = 7

# Digest-covered top-level keys.  ``provenance`` is deliberately absent.
DIGEST_KEYS = ("schema", "canonicalization", "anchor", "inputs", "derived")


class G4Error(RuntimeError):
    def __init__(self, message: str, *, exit_code: int = EXIT_DRIFT,
                 detail: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.exit_code = exit_code
        self.detail = dict(detail or {})


# ---------------------------------------------------------------------------
# primitive hashing / canonical JSON
# ---------------------------------------------------------------------------
def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str | os.PathLike[str]) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_bytes(value: object) -> bytes:
    """The one canonical JSON encoding used for every digest in G4-B."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def canonical_document(value: object) -> bytes:
    return canonical_json_bytes(value) + b"\n"


def digest_of(content: Mapping[str, Any]) -> str:
    """sha256 over the canonical digest-covered projection of the manifest."""
    payload = {key: content[key] for key in DIGEST_KEYS if key in content}
    return sha256_bytes(canonical_json_bytes(payload))


def manifest_bytes(content: Mapping[str, Any]) -> bytes:
    """Pretty manifest for humans; the digest is computed over the projection.

    The pretty form sorts keys and uses a fixed indent, so two builds with the
    same digest-covered content are byte-identical.
    """
    return (json.dumps(content, sort_keys=True, indent=2, ensure_ascii=False,
                       allow_nan=False) + "\n").encode("utf-8")


def mode_octal(path: str | os.PathLike[str]) -> str:
    return format(stat.S_IMODE(os.lstat(path).st_mode), "04o")


def is_regular(path: str | os.PathLike[str]) -> bool:
    try:
        return stat.S_ISREG(os.lstat(path).st_mode)
    except OSError:
        return False


# ---------------------------------------------------------------------------
# git provenance (never required for synthetic fixtures)
# ---------------------------------------------------------------------------
def git_text(*args: str, cwd: Path | None = None) -> str:
    proc = subprocess.run(["git", *args], cwd=str(cwd or REPO_ROOT),
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise G4Error("git command failed", exit_code=EXIT_ENVIRONMENT,
                      detail={"args": list(args), "stderr": proc.stderr[-500:]})
    return proc.stdout.strip()


def git_optional(*args: str, cwd: Path | None = None) -> str | None:
    try:
        return git_text(*args, cwd=cwd)
    except G4Error:
        return None


def git_blob_sha256(commit: str, path: str) -> str:
    proc = subprocess.run(["git", "show", f"{commit}:{path}"], cwd=str(REPO_ROOT),
                          capture_output=True)
    if proc.returncode != 0:
        raise G4Error("git blob unreadable", exit_code=EXIT_ENVIRONMENT,
                      detail={"commit": commit, "path": path})
    return sha256_bytes(proc.stdout)


def git_blob_hash(commit: str, path: str) -> str:
    return git_text("rev-parse", f"{commit}:{path}")


def git_last_commit(path: str, *, cwd: Path | None = None) -> str | None:
    out = git_optional("log", "-1", "--format=%H", "--", path, cwd=cwd)
    return out or None


def git_head() -> str:
    return git_text("rev-parse", "HEAD")


# ---------------------------------------------------------------------------
# file / tree collection
# ---------------------------------------------------------------------------
def _sorted_relpaths(root: Path, suffixes: Sequence[str] | None,
                     exclude_dirs: Sequence[str]) -> list[str]:
    excluded = set(exclude_dirs)
    rows: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(name for name in dirnames if name not in excluded)
        for name in sorted(filenames):
            if suffixes and not name.endswith(tuple(suffixes)):
                continue
            full = Path(dirpath) / name
            if not is_regular(full):
                continue
            rows.append(full.relative_to(root).as_posix())
    return sorted(rows)


def file_record(path: Path, relative: str, *, source: Mapping[str, Any]) -> dict:
    info = os.lstat(path)
    return {
        "path": relative,
        "sha256": sha256_file(path),
        "bytes": info.st_size,
        "mode": format(stat.S_IMODE(info.st_mode), "04o"),
        "source": dict(source),
    }


def tree_digest(root: Path, *, suffixes: Sequence[str] | None = None,
                exclude_dirs: Sequence[str] = ("__pycache__", ".git")) -> dict:
    """Deterministic digest over ``path\\0sha256\\0mode`` lines of one subtree.

    Additions, deletions, byte edits and mode changes all change the digest,
    which is what a fail-closed "next dispatch" check needs.  It is not a tar
    digest: the canonical G3-D recipe is used for rootfs/deps/stage instead.
    """
    rows = _sorted_relpaths(root, suffixes, exclude_dirs)
    digest = hashlib.sha256()
    total = 0
    for relative in rows:
        full = root / relative
        data = full.read_bytes()
        total += len(data)
        digest.update(relative.encode("utf-8") + b"\0")
        digest.update(sha256_bytes(data).encode() + b"\0")
        digest.update(mode_octal(full).encode() + b"\n")
    return {"sha256": digest.hexdigest(), "files": len(rows), "bytes": total}


def canonical_tar_sha256(path: Path) -> str:
    """The frozen G3-D canonicalisation recipe, byte for byte."""
    proc = subprocess.run(
        ["tar", "--sort=name", "--mtime=@0", "--owner=0", "--group=0",
         "--numeric-owner", "-cf", "-", "-C", str(path), "."],
        capture_output=True, check=False)
    if proc.returncode != 0:
        raise G4Error("tar failed", exit_code=EXIT_ENVIRONMENT,
                      detail={"path": str(path), "stderr": proc.stderr[-500:]})
    return sha256_bytes(proc.stdout)


# ---------------------------------------------------------------------------
# stage manifest reuse (one source of truth for what the stage contains)
# ---------------------------------------------------------------------------
def load_stage_manifest(stage_dir: Path) -> dict:
    path = stage_dir / "manifest.json"
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise G4Error("stage manifest unreadable", exit_code=EXIT_SPEC_INVALID,
                      detail={"path": str(path), "error": type(exc).__name__}) from exc
    document = json.loads(raw.decode("utf-8"))
    if not isinstance(document, dict):
        raise G4Error("stage manifest is not an object", exit_code=EXIT_SPEC_INVALID)
    document["_manifest_sha256"] = sha256_bytes(raw)
    return document


def stage_rows(manifest: Mapping[str, Any], section: str) -> dict[str, dict]:
    rows = ((manifest.get(section) or {}).get("files") or [])
    out: dict[str, dict] = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("path"), str):
            continue
        out[row["path"]] = row
    return out


# ---------------------------------------------------------------------------
# inventory construction
# ---------------------------------------------------------------------------
def _root_record_file_set(root: Path, paths: Sequence[str], *,
                          source_commit: str | None) -> dict:
    rows: list[dict] = []
    problems: list[str] = []
    for relative in sorted(paths):
        full = root / relative
        if not is_regular(full):
            problems.append(f"missing:{relative}")
            continue
        commit = source_commit or git_last_commit(relative, cwd=root)
        source: dict[str, Any] = {"kind": "worktree_file", "commit": commit,
                                  "path": relative}
        if commit:
            blob = git_optional("rev-parse", f"{commit}:{relative}", cwd=root)
            if blob:
                source["git_blob"] = blob
        rows.append(file_record(full, relative, source=source))
    return {"kind": "file_set", "root": ".", "files": rows,
            "problems": problems}


def _root_record_worktree_tree(root: Path, relative_root: str, *,
                               suffixes: Sequence[str] | None,
                               exclude_dirs: Sequence[str],
                               source_commit: str | None) -> dict:
    base = root / relative_root
    declared_suffixes = list(suffixes or [])
    declared_excludes = list(exclude_dirs or [])
    if not base.is_dir():
        return {"kind": "worktree_tree", "root": relative_root, "files": [],
                "suffixes": declared_suffixes,
                "exclude_dirs": declared_excludes,
                "tree": None, "problems": [f"root_missing:{relative_root}"]}
    names = _sorted_relpaths(base, suffixes, exclude_dirs)
    rows = []
    for name in names:
        full = base / name
        commit = source_commit or git_last_commit(f"{relative_root}/{name}",
                                                  cwd=root)
        source: dict[str, Any] = {"kind": "git_blob", "commit": commit,
                                  "path": f"{relative_root}/{name}"}
        if commit:
            blob = git_optional("rev-parse", f"{commit}:{relative_root}/{name}",
                                cwd=root)
            if blob:
                source["git_blob"] = blob
        rows.append(file_record(full, name, source=source))
    return {"kind": "worktree_tree", "root": relative_root, "files": rows,
            "suffixes": declared_suffixes, "exclude_dirs": declared_excludes,
            "tree": tree_digest(base, suffixes=suffixes,
                                exclude_dirs=exclude_dirs),
            "problems": []}


def _stage_section(manifest: Mapping[str, Any], stage_dir: Path, section: str,
                   *, tree_prefixes: Sequence[str]) -> dict:
    """Per-file rows for control files; explicit subtree digests for big trees.

    The stage manifest is the single source of truth for what the stage holds:
    each row is re-hashed on disk and compared with the stage manifest itself,
    so "stage manifest says X, disk says Y" is impossible to hide.  The big
    dependency trees (``node_modules``/``native-cache``/``pkg-cache``) keep a
    deterministic subtree digest plus the stage-manifest row count, and the
    stage's own canonical tar hash (``anchor.stage.tree_sha256``) covers any
    other addition/removal.
    """
    rows = stage_rows(manifest, section)
    root = stage_dir / section
    tree_roots = [prefix.rstrip("/") for prefix in tree_prefixes]
    files: list[dict] = []
    trees: list[dict] = []
    problems: list[str] = []
    for relative, row in sorted(rows.items()):
        if any(relative == tree_root or relative.startswith(tree_root + "/")
               for tree_root in tree_roots):
            continue
        full = root / relative
        if not is_regular(full):
            problems.append(f"missing:{relative}")
            continue
        record = file_record(full, relative, source=row.get("source") or {})
        if record["sha256"] != row.get("sha256"):
            problems.append(f"stage_manifest_sha_mismatch:{relative}")
        if record["bytes"] != row.get("bytes"):
            problems.append(f"stage_manifest_bytes_mismatch:{relative}")
        files.append(record)
    for tree_root in tree_roots:
        digest = tree_digest(root / tree_root)
        declared = [relative for relative in rows
                    if relative == tree_root or relative.startswith(tree_root + "/")]
        if digest["files"] != len(declared):
            problems.append(f"tree_row_count_mismatch:{tree_root}:"
                            f"{digest['files']}!={len(declared)}")
        trees.append({"path": tree_root, **digest,
                      "stage_manifest_rows": len(declared)})
    return {"kind": "stage_section", "section": section,
            "root": f"{stage_dir.name}/{section}",
            "stage_manifest_sha256": manifest.get("_manifest_sha256"),
            "per_file_count": len(files), "stage_manifest_rows": len(rows),
            "files": files, "trees": trees, "problems": problems}


def build_content(spec: Mapping[str, Any], *, repo_root: Path | None = None,
                  stage_dir: Path | None = None, anchor_mode: str = "full") -> dict:
    """Build the digest-covered content of a G4-B inventory manifest."""
    repo = Path(repo_root or REPO_ROOT)
    stage = Path(stage_dir or STAGE_DEFAULT)
    canonicalization = spec.get("canonicalization") or {}
    if canonicalization.get("json_sort_keys") is not True:
        raise G4Error("spec must declare canonical json_sort_keys",
                      exit_code=EXIT_SPEC_INVALID)
    stage_manifest = load_stage_manifest(stage)
    inputs: dict[str, dict] = {}
    for root_spec in spec.get("roots") or []:
        root_id = root_spec.get("root_id")
        kind = root_spec.get("kind")
        if not isinstance(root_id, str) or not isinstance(kind, str):
            raise G4Error("root spec needs root_id/kind", exit_code=EXIT_SPEC_INVALID)
        if kind == "worktree_tree":
            inputs[root_id] = _root_record_worktree_tree(
                repo, str(root_spec.get("root") or "."),
                suffixes=root_spec.get("suffixes"),
                exclude_dirs=root_spec.get("exclude_dirs") or (),
                source_commit=root_spec.get("source_commit"))
        elif kind == "file_set":
            inputs[root_id] = _root_record_file_set(
                repo, list(root_spec.get("paths") or []),
                source_commit=root_spec.get("source_commit"))
        elif kind == "stage_section":
            inputs[root_id] = _stage_section(
                stage_manifest, stage, str(root_spec.get("section")),
                tree_prefixes=tuple(root_spec.get("tree_prefixes") or ()))
        elif kind == "stage_file":
            relative = str(root_spec.get("path"))
            full = stage / relative
            if not is_regular(full):
                inputs[root_id] = {"kind": "stage_file", "path": relative,
                                   "file": None, "problems": ["missing"]}
            else:
                row = (stage_rows(stage_manifest, "trusted").get(relative)
                       or stage_rows(stage_manifest, "candidate").get(relative)
                       or {})
                inputs[root_id] = {
                    "kind": "stage_file", "path": relative,
                    "file": file_record(full, relative,
                                        source=row.get("source") or {}),
                    "problems": []}
        elif kind == "canonical_tree":
            path = repo / str(root_spec.get("path"))
            inputs[root_id] = {
                "kind": "canonical_tree", "path": str(root_spec.get("path")),
                "sha256": canonical_tar_sha256(path),
                "expected": root_spec.get("expected"), "problems": []}
        elif kind == "file":
            relative = str(root_spec.get("path"))
            full = repo / relative
            if not is_regular(full):
                inputs[root_id] = {"kind": "file", "path": relative,
                                   "file": None, "problems": ["missing"]}
            else:
                inputs[root_id] = {
                    "kind": "file", "path": relative,
                    "file": file_record(
                        full, relative,
                        source={"kind": "runtime_artifact", "path": relative,
                                "commit": root_spec.get("source_commit")}),
                    "problems": []}
        elif kind == "tree":
            relative = str(root_spec.get("path"))
            inputs[root_id] = {
                "kind": "tree", "path": relative,
                "tree": tree_digest(repo / relative,
                                    exclude_dirs=root_spec.get("exclude_dirs") or ()),
                "problems": []}
        else:
            raise G4Error(f"unknown root kind {kind!r}", exit_code=EXIT_SPEC_INVALID,
                          detail={"root_id": root_id})
    derived = derive_facts(stage, stage_manifest)
    anchor = {
        "product_commit": PRODUCT_BASE,
        "repo_head_at_build": git_optional("rev-parse", "HEAD"),
        "stage": {
            "dir": stage.name,
            "manifest_sha256": stage_manifest.get("_manifest_sha256"),
            "tree_sha256": canonical_tar_sha256(stage),
            "base_sha": stage_manifest.get("base_sha"),
        },
    }
    if anchor_mode == "full":
        anchor["rootfs"] = {"path": ROOTFS.relative_to(repo).as_posix(),
                            "sha256": canonical_tar_sha256(ROOTFS),
                            "expected": ROOTFS_CANON}
        anchor["deps"] = {"path": DEPS.relative_to(repo).as_posix(),
                          "sha256": canonical_tar_sha256(DEPS),
                          "expected": DEPS_CANON}
        anchor["dsh_runtime"] = {
            "path": DSH_RUNTIME.relative_to(repo).as_posix(),
            "sha256": sha256_file(DSH_RUNTIME), "expected": DSH_RUNTIME_CANON}
    return {"schema": SCHEMA, "canonicalization": canonicalization,
            "anchor": anchor, "inputs": inputs, "derived": derived}


def derive_facts(stage: Path, stage_manifest: Mapping[str, Any]) -> dict:
    """Facts that must be *derived*, never typed by hand.

    Every value here is recomputed from a file that is itself in the manifest,
    so a change to the fixture, the templates or the stage changes the fact.
    """
    fixture = stage / "candidate" / "fixtures" / "capture-tools.json"
    tool_rows: list[dict] = []
    fixture_sha = None
    if is_regular(fixture):
        raw = fixture.read_bytes()
        fixture_sha = sha256_bytes(raw)
        document = json.loads(raw.decode("utf-8"))
        for item in document.get("tools") or []:
            if not isinstance(item, dict):
                continue
            canonical = item.get("canonical_json")
            name = item.get("name")
            if not isinstance(canonical, str) or not isinstance(name, str):
                continue
            computed = sha256_bytes(canonical_json_bytes(json.loads(canonical)))
            tool_rows.append({
                "name": name,
                "sha256": computed,
                "declared_sha256": item.get("sha256"),
                "canonical_bytes": len(canonical.encode("utf-8")),
            })
    tool_rows.sort(key=lambda row: row["name"])
    admission = _load_json(stage / "trusted" / "templates" / "admission.template.json")
    broker = _load_json(stage / "trusted" / "templates" / "broker.template.json")
    controller = _load_json(stage / "trusted" / "templates" / "controller.template.json")
    route = admission.get("route") or {}
    limits = admission.get("limits") or {}
    broker_limits = broker.get("limits") or {}
    routes = [row for row in (broker.get("routes") or []) if isinstance(row, dict)]
    price = {}
    if routes:
        price = {"route_id": routes[0].get("route_id"),
                 "model": routes[0].get("model"),
                 "price": routes[0].get("price"),
                 "known_extra_fee_usd": routes[0].get("known_extra_fee_usd"),
                 "usage_policy": routes[0].get("usage_policy")}
    merge_layers = [
        {"order": 1, "layer": "dsh_runtime_profile", "id": "sdk-minimal",
         "source": "deps/deepseek_harness/client.py launch args (--profile)",
         "evidence": "merged config dump probe"},
        {"order": 2, "layer": "cordis_patch",
         "path": "candidate/config/bridge.patch.yml",
         "sha256": _sha_or_none(stage / "candidate" / "config" / "bridge.patch.yml"),
         "source": "candidate_entry.py DeepSeekHarness(patches=(...)) -> --patch"},
        {"order": 3, "layer": "candidate_env",
         "source": "scripts/g3d/stage/candidate_entry.py dsh_env()",
         "keys": ["PATH", "HOME", "PYTHONPATH", "PYTHONDONTWRITEBYTECODE",
                  "TMPDIR", "DSH_RUNTIME_MODE", "DSH_RESOURCE_CACHE",
                  "NARB_NATIVE_CACHE_DIR", "PKG_NATIVE_CACHE_PATH", "NO_COLOR"]},
        {"order": 4, "layer": "trusted_controller_configs",
         "source": "stage/trusted/templates/{admission,broker,controller}.template.json",
         "sha256": {
             "admission": _sha_or_none(
                 stage / "trusted" / "templates" / "admission.template.json"),
             "broker": _sha_or_none(
                 stage / "trusted" / "templates" / "broker.template.json"),
             "controller": _sha_or_none(
                 stage / "trusted" / "templates" / "controller.template.json"),
         }},
    ]
    return {
        "tool_schemas": {
            "source": "candidate/fixtures/capture-tools.json",
            "source_sha256": fixture_sha,
            "tools": tool_rows,
            "approved_tool_count": len(tool_rows),
        },
        "admission_binding": {
            "admission_template_sha256": _sha_or_none(
                stage / "trusted" / "templates" / "admission.template.json"),
            "route": {"route_id": route.get("route_id"),
                      "provider": route.get("provider"),
                      "model": route.get("model")},
            "limits": {key: limits.get(key) for key in
                       ("max_calls", "max_attempts", "max_input_tokens",
                        "max_output_tokens", "deadline_ms")},
            "launcher_uid": (admission.get("launcher") or {}).get("uid"),
            "synthetic": admission.get("synthetic"),
        },
        "controller_binding": {
            "controller_template_sha256": _sha_or_none(
                stage / "trusted" / "templates" / "controller.template.json"),
            "socket_path": controller.get("socket_path"),
            "expected_peer_uid": controller.get("expected_peer_uid"),
            "socket_mode": controller.get("socket_mode"),
            "socket_gid": controller.get("socket_gid"),
        },
        "broker_policy": {
            "broker_template_sha256": _sha_or_none(
                stage / "trusted" / "templates" / "broker.template.json"),
            "limits": broker_limits,
            "price": price,
            "synthetic": broker.get("synthetic"),
        },
        "config_merge_layers": merge_layers,
        "registry_status": "UNVERIFIED_NO_AUTHORITATIVE_MERGED_EXPORT",
    }


def _sha_or_none(path: Path) -> str | None:
    return sha256_file(path) if is_regular(path) else None


def _load_json(path: Path) -> dict:
    """Parse a stage template that may still contain ``{{PLACEHOLDER}}`` values.

    The template bytes are hashed raw; only the placeholder substitution for
    parsing is done here, and ``null`` is the least committal replacement.
    """
    if not is_regular(path):
        return {}
    text = path.read_text(encoding="utf-8")
    import re as _re
    substituted = _re.sub(r"\{\{[A-Z0-9_]+\}\}", "null", text)
    document = json.loads(substituted)
    return document if isinstance(document, dict) else {}


def build_manifest(spec: Mapping[str, Any], *, repo_root: Path | None = None,
                   stage_dir: Path | None = None,
                   provenance: Mapping[str, Any] | None = None,
                   anchor_mode: str = "full") -> dict:
    content = build_content(spec, repo_root=repo_root, stage_dir=stage_dir,
                            anchor_mode=anchor_mode)
    digest = digest_of(content)
    document = dict(content)
    document["digest"] = {"algorithm": "sha256", "value": digest,
                          "covers": list(DIGEST_KEYS),
                          "excludes": ["provenance", "digest"]}
    document["provenance"] = dict(provenance or {})
    document["provenance"].setdefault("canonical_recipe",
                                      "sha256(canonical_json(inputs+anchor))")
    return document


# ---------------------------------------------------------------------------
# verification
# ---------------------------------------------------------------------------
def verify_content(content: Mapping[str, Any], *, repo_root: Path | None = None,
                   stage_dir: Path | None = None, check_git: bool = True,
                   require_anchor: bool = True) -> dict:
    repo = Path(repo_root or REPO_ROOT)
    stage = Path(stage_dir or STAGE_DEFAULT)
    problems: list[str] = []
    details: dict[str, Any] = {}
    if content.get("schema") != SCHEMA:
        problems.append(f"schema:{content.get('schema')}")
    inputs = content.get("inputs")
    if not isinstance(inputs, Mapping):
        return {"ok": False, "problems": ["inputs_missing"], "details": details}
    for root_id, section in sorted(inputs.items()):
        if not isinstance(section, Mapping):
            problems.append(f"{root_id}:not_object")
            continue
        for problem in section.get("problems") or []:
            problems.append(f"{root_id}:{problem}")
        kind = section.get("kind")
        if kind == "worktree_tree":
            base = repo / str(section.get("root"))
            suffixes = section.get("suffixes") or None
            excludes = tuple(section.get("exclude_dirs") or ())
            declared = {row["path"]: row for row in section.get("files") or []}
            actual = (set(_sorted_relpaths(base, suffixes, excludes))
                      if base.is_dir() else set())
            for missing in sorted(set(declared) - actual):
                problems.append(f"{root_id}:removed:{missing}")
            for extra in sorted(actual - set(declared)):
                problems.append(f"{root_id}:added:{extra}")
            for relative in sorted(set(declared) & actual):
                _compare_file(base / relative, declared[relative], root_id,
                              problems, check_git)
            digest = tree_digest(base, suffixes=suffixes, exclude_dirs=excludes)
            if digest["sha256"] != (section.get("tree") or {}).get("sha256"):
                problems.append(f"{root_id}:tree_changed")
            details[root_id] = digest
        elif kind == "file_set":
            declared = {row["path"]: row for row in section.get("files") or []}
            for relative, row in sorted(declared.items()):
                full = repo / relative
                if not is_regular(full):
                    problems.append(f"{root_id}:removed:{relative}")
                    continue
                _compare_file(full, row, root_id, problems, check_git)
        elif kind == "stage_section":
            root = stage / str(section.get("section"))
            declared = {row["path"]: row for row in section.get("files") or []}
            for relative, row in sorted(declared.items()):
                full = root / relative
                if not is_regular(full):
                    problems.append(f"{root_id}:removed:{relative}")
                    continue
                _compare_file(full, row, root_id, problems, check_git=False)
            if check_git:
                _verify_stage_git_provenance(declared, root_id, problems)
            for tree in section.get("trees") or []:
                digest = tree_digest(root / str(tree.get("path")))
                if digest["sha256"] != tree.get("sha256"):
                    problems.append(f"{root_id}:tree_changed:{tree.get('path')}")
                details[f"{root_id}:{tree.get('path')}"] = digest
        elif kind == "stage_file":
            relative = section.get("path")
            full = stage / str(relative)
            row = section.get("file") or {}
            if not is_regular(full):
                problems.append(f"{root_id}:removed:{relative}")
            elif row:
                _compare_file(full, row, root_id, problems, check_git=False)
        elif kind in {"canonical_tree", "tree"}:
            if kind == "canonical_tree":
                actual = canonical_tar_sha256(repo / str(section.get("path")))
                if actual != section.get("sha256"):
                    problems.append(f"{root_id}:tree_changed")
                expected = section.get("expected")
                if expected and actual != expected:
                    problems.append(f"{root_id}:not_canonical")
            else:
                base = repo / str(section.get("path"))
                actual = tree_digest(base)["sha256"]
                if actual != (section.get("tree") or {}).get("sha256"):
                    problems.append(f"{root_id}:tree_changed")
            details[root_id] = {"sha256": actual}
        elif kind == "file":
            relative = section.get("path")
            full = repo / str(relative)
            row = section.get("file") or {}
            if not is_regular(full):
                problems.append(f"{root_id}:removed:{relative}")
            elif row:
                _compare_file(full, row, root_id, problems, check_git=False)
        else:
            problems.append(f"{root_id}:unknown_kind:{kind}")
    # anchor re-checks (independent of the per-root rows)
    anchor = content.get("anchor") or {}
    if require_anchor:
        if (anchor.get("rootfs") or {}).get("sha256") != ROOTFS_CANON:
            problems.append("anchor:rootfs_not_canonical")
        if (anchor.get("deps") or {}).get("sha256") != DEPS_CANON:
            problems.append("anchor:deps_not_canonical")
        if (anchor.get("stage") or {}).get("tree_sha256") != STAGE_TREE_CANON:
            problems.append("anchor:stage_tree_not_canonical")
        if (anchor.get("stage") or {}).get("manifest_sha256") != STAGE_MANIFEST_CANON:
            problems.append("anchor:stage_manifest_not_canonical")
        if (anchor.get("dsh_runtime") or {}).get("sha256") != DSH_RUNTIME_CANON:
            problems.append("anchor:dsh_runtime_not_canonical")
    derived = content.get("derived") or {}
    recomputed = derive_facts(stage, load_stage_manifest(stage))
    if canonical_json_bytes(derived) != canonical_json_bytes(recomputed):
        problems.append("derived:facts_changed")
    return {"ok": not problems, "problems": problems, "details": details}


def _verify_stage_git_provenance(declared: Mapping[str, Mapping[str, Any]],
                                 root_id: str, problems: list[str]) -> None:
    """A stage row claimed from ``git_blob`` must equal that commit's bytes."""
    for relative, row in sorted(declared.items()):
        source = row.get("source") or {}
        if source.get("kind") != "git_blob":
            continue
        commit = source.get("commit")
        path = source.get("path")
        if not isinstance(commit, str) or not isinstance(path, str):
            continue
        try:
            actual = git_blob_sha256(commit, path)
        except G4Error:
            problems.append(f"{root_id}:stage_git_blob_unreadable:{relative}")
            continue
        if actual != row.get("sha256"):
            problems.append(f"{root_id}:stage_git_blob_mismatch:{relative}")


def _compare_file(full: Path, row: Mapping[str, Any], root_id: str,
                  problems: list[str], check_git: bool) -> None:
    relative = row.get("path", str(full))
    if sha256_file(full) != row.get("sha256"):
        problems.append(f"{root_id}:modified:{relative}")
        return
    if os.lstat(full).st_size != row.get("bytes"):
        problems.append(f"{root_id}:size_changed:{relative}")
    if mode_octal(full) != row.get("mode"):
        problems.append(f"{root_id}:mode_changed:{relative}")
    source = row.get("source") or {}
    commit = source.get("commit")
    if check_git and isinstance(commit, str) and source.get("kind") == "git_blob":
        try:
            if git_blob_sha256(commit, str(source.get("path"))) != row.get("sha256"):
                problems.append(f"{root_id}:git_blob_mismatch:{relative}")
        except G4Error:
            problems.append(f"{root_id}:git_blob_unreadable:{relative}")


# ---------------------------------------------------------------------------
# policy binding (the G4-A hand-off surface; not a live authorization)
# ---------------------------------------------------------------------------
def load_policy(path: Path | str = POLICY_PATH) -> dict:
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise G4Error("policy unreadable", exit_code=EXIT_SPEC_INVALID,
                      detail={"path": str(path),
                              "error": type(exc).__name__}) from exc
    if not isinstance(document, dict):
        raise G4Error("policy is not an object", exit_code=EXIT_SPEC_INVALID)
    return document


def policy_problems(policy: Mapping[str, Any]) -> list[str]:
    problems: list[str] = []
    if policy.get("schema") != POLICY_SCHEMA:
        problems.append(f"schema:{policy.get('schema')}")
    if policy.get("registry_status") != "UNVERIFIED_NO_AUTHORITATIVE_MERGED_EXPORT":
        problems.append("registry_status_must_stay_unverified")
    if policy.get("synthetic_only") is not True:
        problems.append("policy_must_be_synthetic_only")
    route = policy.get("route") or {}
    if set(route) != {"route_id", "provider", "model"}:
        problems.append("route_shape")
    tools = policy.get("approved_tools") or []
    if not isinstance(tools, list) or not tools:
        problems.append("approved_tools_missing")
    for tool in tools:
        if not isinstance(tool, Mapping) or set(tool) != {"name", "sha256"}:
            problems.append("approved_tool_shape")
            continue
        if len(str(tool["sha256"])) != 64:
            problems.append("approved_tool_sha256")
    forbidden = policy.get("forbidden_tool_names",
                           policy.get("forbidden_tool_prefixes"))
    if not isinstance(forbidden, list) or not forbidden:
        problems.append("forbidden_tool_names_missing")
    if policy.get("billable_send_authorized") is not False:
        problems.append("billable_send_must_be_false")
    return problems


def require_manifest_match(policy: Mapping[str, Any], manifest: Mapping[str, Any],
                           *, verification: Mapping[str, Any] | None = None) -> dict:
    """Fail-closed "may the next dispatch proceed?" decision.

    ``ok=true`` means only: the frozen bytes, tool schemas, route, budget and
    price source are the ones this policy was written for.  It is **not** a
    live authorization and never unlocks ``LiveGate``.
    """
    reasons: list[str] = list(policy_problems(policy))
    if verification is not None and not verification.get("ok", False):
        reasons.extend(f"manifest:{problem}"
                       for problem in (verification.get("problems") or [])[:64])
    digest = (manifest.get("digest") or {}).get("value")
    approved = policy.get("approved_manifest_digest")
    if approved and digest != approved:
        reasons.append("manifest_digest_changed")
    derived = manifest.get("derived") or {}
    policy_tools = sorted((tool["name"], tool["sha256"])
                          for tool in policy.get("approved_tools") or [])
    manifest_tools = sorted((tool["name"], tool["sha256"])
                            for tool in (derived.get("tool_schemas") or {}).get("tools") or [])
    if policy_tools != manifest_tools:
        reasons.append("tool_schema_changed")
    route = ((derived.get("admission_binding") or {}).get("route") or {})
    if dict(route) != dict(policy.get("route") or {}):
        reasons.append("route_changed")
    limits = ((derived.get("admission_binding") or {}).get("limits") or {})
    if limits != (policy.get("admission_limits") or {}):
        reasons.append("admission_limits_changed")
    broker = (derived.get("broker_policy") or {}).get("limits") or {}
    if broker != (policy.get("broker_limits") or {}):
        reasons.append("broker_limits_changed")
    price = (derived.get("broker_policy") or {}).get("price") or {}
    if canonical_json_bytes(price) != canonical_json_bytes(policy.get("price") or {}):
        reasons.append("price_source_changed")
    anchor = manifest.get("anchor") or {}
    for key, expected in (("rootfs", ROOTFS_CANON), ("deps", DEPS_CANON)):
        if (anchor.get(key) or {}).get("sha256") != expected:
            reasons.append(f"{key}_not_canonical")
    if (anchor.get("stage") or {}).get("manifest_sha256") != STAGE_MANIFEST_CANON:
        reasons.append("stage_manifest_changed")
    if (derived.get("registry_status") != policy.get("registry_status")):
        reasons.append("registry_status_changed")
    return {"ok": not reasons, "reasons": sorted(set(reasons)),
            "manifest_digest": digest, "policy_id": policy.get("policy_id")}


# ---------------------------------------------------------------------------
# spec validation / small CLI helpers
# ---------------------------------------------------------------------------
REQUIRED_ROOT_IDS = (
    "trusted_src",
    "trusted_stage",
    "candidate_stage",
    "adapter_build",
    "repo_config",
    "plugins",
    "harness",
    "policy",
    "runtime_rootfs",
    "runtime_deps",
    "runtime_dsh",
)


def spec_problems(spec: Mapping[str, Any]) -> list[str]:
    problems: list[str] = []
    if spec.get("schema") != SPEC_SCHEMA:
        problems.append(f"schema:{spec.get('schema')}")
    canonical = spec.get("canonicalization") or {}
    for key in ("json_sort_keys", "path_sort", "mode_format", "digest"):
        if not canonical.get(key):
            problems.append(f"canonicalization_missing:{key}")
    roots = spec.get("roots") or []
    ids = [root.get("root_id") for root in roots if isinstance(root, Mapping)]
    for required in REQUIRED_ROOT_IDS:
        if required not in ids:
            problems.append(f"root_missing:{required}")
    if len(ids) != len(set(ids)):
        problems.append("root_id_duplicate")
    return problems


def load_spec(path: Path | str = SPEC_PATH) -> dict:
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise G4Error("spec unreadable", exit_code=EXIT_SPEC_INVALID,
                      detail={"path": str(path),
                              "error": type(exc).__name__}) from exc
    if not isinstance(document, dict):
        raise G4Error("spec is not an object", exit_code=EXIT_SPEC_INVALID)
    problems = spec_problems(document)
    if problems:
        raise G4Error("spec invalid", exit_code=EXIT_SPEC_INVALID,
                      detail={"problems": problems})
    return document


def write_json_atomic(path: Path, document: object, *, mode: int = 0o444) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(document, sort_keys=True, indent=2,
                       ensure_ascii=False) + "\n").encode("utf-8")
    temporary = path.with_name(path.name + f".tmp.{os.getpid()}")
    temporary.write_bytes(data)
    os.chmod(temporary, mode)
    os.replace(temporary, path)
    return {"path": str(path), "sha256": sha256_bytes(data), "bytes": len(data)}


def utc_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main(argv: Sequence[str] | None = None) -> int:  # pragma: no cover - helper
    sys.stderr.write("lib_g4 is a library; use build_manifest/verify_manifest\n")
    return EXIT_SPEC_INVALID


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
