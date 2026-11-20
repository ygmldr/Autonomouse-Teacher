#!/usr/bin/env python3
"""Build the G4-R strict-inventory review packet v2 (host-side, no key/network).

Design goals (G4-R P2-01 / R4-01..R4-06):

* New schema and a brand-new output root ``artifacts/review-packet-g4r-v2-<impl_sha>``;
  the frozen G4-F packet is never read-modify-written.
* SQLite payload entries are produced only through ``Connection.backup()`` from a
  read-only working copy into a temporary snapshot file. All source/destination
  connections are closed *before* the snapshot bytes are copied into the packet
  build tree. The builder never opens SQLite inside the build/packet directory.
* After the payload is assembled the builder walks the whole tree with
  ``lstat``-based traversal, rejects hidden paths, symlinks, non-regular files and
  duplicate-path hazards, and derives every count/tree from that traversal.
* ``hashes.sha256`` covers payload files **plus** ``manifest.json``; it excludes
  only itself and ``packet-integrity-report.txt``. The manifest's
  ``payload_tree_sha256`` covers payload only. Those three metadata files are a
  fixed exception set (never an allow-list for arbitrary files).
* The build is staged in a private temporary directory and atomically renamed to
  the final root only after the builder's own strict inventory self-check passes.

Usage (example):

  PYTHONPATH=src python scripts/g4r/build_packet_g4r.py \
    --impl-sha <impl-sha> --staging <staging-dir> --metadata <metadata.json> \
    --livegate-snapshot <livegate.json> \
    --sqlite cases/r2-recovery/attempts.sqlite3=<work-copy>/attempts.sqlite3 \
    --packet-root artifacts/review-packet-g4r-v2-<impl-sha> --frozen-utc 2026-11-20T00:00:00Z

The staging directory is input only: it must already contain the payload files
(README/identity/source/cases/regressions/matrix/review) as regular files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import stat
import tempfile
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = "m0.g4r.packet.manifest/v2"
LIVEGATE_SCHEMA = "m0.g4r.livegate-snapshot/v1"
MANIFEST = "manifest.json"
HASHES = "hashes.sha256"
REPORT = "packet-integrity-report.txt"
FIXED_METADATA_EXCEPTIONS = (MANIFEST, HASHES, REPORT)
PACKET_FORMAT = "g4r-v2"
FILE_MODE = 0o444
# The canonical payload-tree digest is: sha256 of the sorted canonical JSON list
# of [relative_path, sha256] pairs. verify_packet_g4r.py re-implements this
# independently (it must not import the builder).
LIVEGATE_SNAPSHOT_PATH = "identity/livegate.json"
REQUIRED_METADATA = (
    "base_sha", "stage", "rootfs_sha256", "deps_sha256", "runtime",
    "environment", "tests", "limitations",
)
SHA_FIELDS = ("rootfs_sha256", "deps_sha256")
_GIT_COMMIT = re.compile(r"[a-f0-9]{40}\Z")
_SHA256 = re.compile(r"[a-f0-9]{64}\Z")


class BuildError(RuntimeError):
    """A fail-closed build refusal with an explicit reason code."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(1 << 20)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("utf-8")


def _normalized_relative(value: str) -> str:
    if not isinstance(value, str) or not value or value.startswith("/"):
        raise BuildError("BAD_RELATIVE_PATH", repr(value))
    if "\\" in value or ".." in value.split("/"):
        raise BuildError("BAD_RELATIVE_PATH", value)
    parts = value.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise BuildError("BAD_RELATIVE_PATH", value)
    return value


def _is_fixed_metadata(relative: str) -> bool:
    return relative in FIXED_METADATA_EXCEPTIONS


def _is_sidecar_name(name: str) -> bool:
    return name.endswith(("-wal", "-shm", "-journal"))


def _scan_tree(root: Path) -> dict[str, dict]:
    """Strict recursive inventory of a build tree; raises on unsafe entries."""
    inventory: dict[str, dict] = {}
    stack: list[tuple[str, Path]] = [("", root)]
    while stack:
        prefix, directory = stack.pop()
        try:
            entries = sorted(os.scandir(directory), key=lambda item: item.name)
        except OSError as error:
            raise BuildError("TREE_UNREADABLE", f"{prefix}{error.strerror}") from None
        for entry in entries:
            name = entry.name
            relative = f"{prefix}{name}"
            _normalized_relative(relative)
            if name.startswith("."):
                raise BuildError("HIDDEN_PATH", relative)
            info = entry.stat(follow_symlinks=False)
            mode = info.st_mode
            if stat.S_ISLNK(mode):
                raise BuildError("SYMLINK_PATH", relative)
            if stat.S_ISDIR(mode):
                stack.append((relative + "/", Path(entry.path)))
                continue
            if not stat.S_ISREG(mode):
                raise BuildError("NOT_REGULAR_FILE", relative)
            if info.st_nlink != 1:
                raise BuildError("HARDLINK_ANOMALY", relative)
            inventory[relative] = {"sha256": sha256_file(Path(entry.path)),
                                   "size": info.st_size, "mode": mode & 0o777,
                                   "path": Path(entry.path)}
    return inventory


def _payload_tree(inventory: dict[str, dict]) -> str:
    entries = [[relative, record["sha256"]]
               for relative, record in inventory.items()
               if not _is_fixed_metadata(relative)]
    entries.sort(key=lambda item: item[0])
    return sha256_bytes(canonical_json_bytes(entries))


def _file_modes(inventory: dict[str, dict]) -> dict[str, str]:
    return {relative: oct(record["mode"])
            for relative, record in sorted(inventory.items())
            if relative == MANIFEST or not _is_fixed_metadata(relative)}


def _read_json_strict(path: Path, *, code: str, max_bytes: int = 1 << 20) -> dict:
    try:
        info = path.lstat()
    except OSError:
        raise BuildError(code, f"{path} is missing") from None
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise BuildError(code, f"{path} is not a regular file")
    if info.st_size <= 0 or info.st_size > max_bytes:
        raise BuildError(code, f"{path} size outside permitted range")
    raw = path.read_bytes()
    try:
        value = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
    except (ValueError, UnicodeDecodeError) as error:
        raise BuildError(code, f"{path} is not strict JSON: {error}") from None
    if not isinstance(value, dict):
        raise BuildError(code, f"{path} must be a JSON object")
    return value


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    seen: dict = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError(f"duplicate key: {key}")
        seen[key] = value
    return seen


def _require_sha(value: object, *, field: str) -> str:
    if (not isinstance(value, str) or len(value) != 64
            or any(char not in "0123456789abcdef" for char in value)):
        raise BuildError("METADATA_INVALID", f"{field} must be a lowercase sha256 digest")
    return value


def _require_impl_id(value: object, *, field: str) -> str:
    """Accept the authoritative 40-hex git commit or a 64-hex impl identity.

    The frozen policy convention is a lowercase 40-hex git commit; a 64-hex
    value stays accepted for synthetic/testing packets. Anything else (length,
    uppercase, non-hex) is refused.
    """
    if not isinstance(value, str) or not (_GIT_COMMIT.fullmatch(value)
                                          or _SHA256.fullmatch(value)):
        raise BuildError("METADATA_INVALID",
                         f"{field} must be a lowercase 40-hex git commit or 64-hex sha256")
    return value


def _optional_sha256(value: object, *, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise BuildError("METADATA_INVALID", f"{field} must be a lowercase sha256 digest")
    return value


def _load_metadata(path: Path, impl_sha: str, impl_content_sha256: str | None) -> dict:
    document = _read_json_strict(path, code="METADATA_INVALID")
    for key in REQUIRED_METADATA:
        if key not in document:
            raise BuildError("METADATA_INVALID", f"missing field {key}")
    for key in SHA_FIELDS:
        _require_sha(document[key], field=key)
    for key in ("base_sha",):
        _require_sha(document[key], field=key)
    for key in ("parent_sha", "code_sha", "docs_sha", "build_sha"):
        if key in document and document[key] is not None:
            _require_sha(document[key], field=key)
    if not isinstance(document["stage"], dict) or not document["stage"]:
        raise BuildError("METADATA_INVALID", "stage must be a non-empty object")
    if not isinstance(document["runtime"], dict) or not document["runtime"]:
        raise BuildError("METADATA_INVALID", "runtime must be a non-empty object")
    if not isinstance(document["environment"], dict) or not document["environment"]:
        raise BuildError("METADATA_INVALID", "environment must be a non-empty object")
    if not isinstance(document["tests"], dict) or not isinstance(
            document["tests"].get("summary"), dict):
        raise BuildError("METADATA_INVALID", "tests.summary must be an object")
    if not isinstance(document["limitations"], list) or not document["limitations"]:
        raise BuildError("METADATA_INVALID", "limitations must be a non-empty list")
    if document.get("external_network_calls") != 0:
        raise BuildError("METADATA_INVALID", "external_network_calls must be 0")
    if document.get("live_gate") not in (None, "BLOCKED"):
        raise BuildError("METADATA_INVALID", "live_gate must be BLOCKED")
    metadata_impl = document.get("impl_sha")
    if metadata_impl is not None:
        _require_impl_id(metadata_impl, field="metadata.impl_sha")
        if metadata_impl != impl_sha:
            raise BuildError("IMPL_SHA_MISMATCH",
                             "metadata impl_sha differs from --impl-sha")
    metadata_git = document.get("impl_git_commit")
    if metadata_git is not None:
        if not isinstance(metadata_git, str) or not _GIT_COMMIT.fullmatch(metadata_git):
            raise BuildError("METADATA_INVALID",
                             "metadata.impl_git_commit must be a 40-hex git commit")
        if _GIT_COMMIT.fullmatch(impl_sha) and metadata_git != impl_sha:
            raise BuildError("IMPL_SHA_MISMATCH",
                             "metadata impl_git_commit differs from --impl-sha")
    metadata_content = _optional_sha256(document.get("impl_content_sha256"),
                                        field="metadata.impl_content_sha256")
    if (metadata_content is not None and impl_content_sha256 is not None
            and metadata_content != impl_content_sha256):
        raise BuildError("IMPL_SHA_MISMATCH",
                         "metadata impl_content_sha256 differs from CLI value")
    return document


def _load_livegate_snapshot(path: Path) -> dict:
    document = _read_json_strict(path, code="LIVEGATE_SNAPSHOT_INVALID", max_bytes=256 * 1024)
    reasons = document.get("reasons")
    if (document.get("schema") != LIVEGATE_SCHEMA
            or document.get("live_gate") != "BLOCKED"
            or not isinstance(reasons, list) or not reasons
            or any(not isinstance(item, str) or not item for item in reasons)):
        raise BuildError("LIVEGATE_SNAPSHOT_INVALID",
                         "must be a BLOCKED snapshot with a non-empty reasons list")
    snapshot = dict(document)
    snapshot["reasons"] = list(reasons)
    return snapshot


def _copy_staging_payload(staging: Path, build: Path) -> dict[str, dict]:
    """Copy the staged payload tree into the build dir; returns the staging inventory."""
    if not staging.is_dir() or staging.is_symlink():
        raise BuildError("STAGING_INVALID", "staging must be a real directory")
    inventory = _scan_tree(staging)
    if not inventory:
        raise BuildError("STAGING_INVALID", "staging has no payload files")
    for relative in inventory:
        if _is_fixed_metadata(relative):
            raise BuildError("STAGING_INVALID",
                             f"staging may not predefine metadata file {relative}")
    for relative, record in inventory.items():
        target = build / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(record["path"], target)
        os.chmod(target, FILE_MODE)
    return inventory


def _snapshot_sqlite(spec: str, build: Path, scratch: Path) -> str:
    """Create one consistent SQLite snapshot via Connection.backup(), then copy it."""
    destination_relative, separator, source_text = spec.partition("=")
    if not separator:
        raise BuildError("SQLITE_SPEC_INVALID", spec)
    destination_relative = _normalized_relative(destination_relative)
    if _is_fixed_metadata(destination_relative):
        raise BuildError("SQLITE_SPEC_INVALID", "snapshot may not replace metadata")
    if not destination_relative.endswith(".sqlite3"):
        raise BuildError("SQLITE_SPEC_INVALID", "snapshot path must end with .sqlite3")
    source = Path(source_text)
    if not source.is_absolute() or source.is_symlink() or not source.is_file():
        raise BuildError("SQLITE_SOURCE_INVALID", str(source))
    if source.name.endswith(("-wal", "-shm", "-journal")):
        raise BuildError("SQLITE_SOURCE_INVALID", "source must be the database itself")
    scratch.mkdir(parents=True, exist_ok=True)
    snapshot = scratch / (hashlib.sha256(destination_relative.encode()).hexdigest()
                          + ".sqlite3")
    if snapshot.exists():
        snapshot.unlink()
    try:
        source_connection = sqlite3.connect(f"file:{source}?mode=ro", uri=True, timeout=30)
    except sqlite3.Error as error:
        raise BuildError("SQLITE_SOURCE_INVALID", f"{source}: {error}") from None
    try:
        destination_connection = sqlite3.connect(str(snapshot), timeout=30)
        try:
            source_connection.backup(destination_connection)
            destination_connection.commit()
        finally:
            destination_connection.close()
    except sqlite3.Error as error:
        raise BuildError("SQLITE_BACKUP_FAILED", f"{source}: {error}") from None
    finally:
        source_connection.close()
    # All connections are closed here; only now do the snapshot bytes enter the
    # build tree, so no -wal/-shm/-journal can appear inside the packet.
    if not snapshot.is_file() or snapshot.stat().st_size <= 0:
        raise BuildError("SQLITE_BACKUP_FAILED", f"{source}: empty snapshot")
    target = build / destination_relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(snapshot, target)
    os.chmod(target, FILE_MODE)
    snapshot.unlink()
    return destination_relative


def _write_file(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(path, FILE_MODE)


def _write_hashes(build: Path, inventory: dict[str, dict]) -> str:
    lines = []
    for relative in sorted(inventory):
        if relative == HASHES or relative == REPORT:
            continue  # the only two files excluded from hash coverage
        lines.append(f"{inventory[relative]['sha256']}  {relative}\n")
    data = "".join(lines).encode("utf-8")
    _write_file(build / HASHES, data)
    return sha256_bytes(data)


def _write_report(build: Path, manifest: dict, manifest_sha: str,
                  hashes_sha: str) -> None:
    lines = [
        "schema=m0.g4r.packet-integrity-report/v2",
        f"packet={manifest['packet']['name']}",
        f"impl_sha={manifest['identity']['impl_sha']}",
        f"frozen_utc={manifest['packet']['frozen_utc']}",
        f"payload_count={manifest['inventory']['payload_count']}",
        f"hash_manifest_entry_count={manifest['inventory']['hash_manifest_entry_count']}",
        f"total_regular_files={manifest['inventory']['total_regular_files']}",
        f"payload_tree_sha256={manifest['inventory']['payload_tree_sha256']}",
        f"manifest_sha256={manifest_sha}",
        f"hashes_sha256={hashes_sha}",
        "metadata_exceptions=" + ",".join(sorted(FIXED_METADATA_EXCEPTIONS)),
        "external_network_calls=0",
        "live_gate=BLOCKED",
        "",
    ]
    _write_file(build / REPORT, "\n".join(lines).encode("utf-8"))


def _self_check(build: Path, manifest: dict) -> None:
    """Builder-side strict re-derivation of every declared inventory property."""
    inventory = _scan_tree(build)
    on_disk = set(inventory)
    expected = set(inventory)
    if on_disk != expected:  # pragma: no cover - _scan_tree returns the disk set
        raise BuildError("SELF_CHECK_FAILED", "inventory mismatch")
    payload = {relative for relative in on_disk if not _is_fixed_metadata(relative)}
    exceptions = {relative for relative in on_disk if _is_fixed_metadata(relative)}
    if exceptions != set(FIXED_METADATA_EXCEPTIONS):
        raise BuildError("SELF_CHECK_FAILED",
                         f"metadata exception set is {sorted(exceptions)}")
    if (manifest["inventory"]["metadata_exceptions"]
            != sorted(FIXED_METADATA_EXCEPTIONS)):
        raise BuildError("SELF_CHECK_FAILED", "manifest exceptions are not fixed")
    if manifest["inventory"]["payload_count"] != len(payload):
        raise BuildError("SELF_CHECK_FAILED", "payload_count mismatch")
    if manifest["inventory"]["hash_manifest_entry_count"] != len(payload) + 1:
        raise BuildError("SELF_CHECK_FAILED", "hash_manifest_entry_count mismatch")
    if manifest["inventory"]["total_regular_files"] != len(on_disk):
        raise BuildError("SELF_CHECK_FAILED", "total_regular_files mismatch")
    if manifest["inventory"]["payload_tree_sha256"] != _payload_tree(inventory):
        raise BuildError("SELF_CHECK_FAILED", "payload tree mismatch")
    if _file_modes(inventory) != manifest["inventory"]["file_modes"]:
        raise BuildError("SELF_CHECK_FAILED", "file mode map mismatch")
    hashes_data = (build / HASHES).read_bytes()
    report_values = {}
    for line in (build / REPORT).read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition("=")
        if separator:
            report_values[key] = value
    if report_values.get("hashes_sha256") != sha256_bytes(hashes_data):
        raise BuildError("SELF_CHECK_FAILED", "report hashes digest mismatch")
    if report_values.get("manifest_sha256") != sha256_file(build / MANIFEST):
        raise BuildError("SELF_CHECK_FAILED", "report manifest digest mismatch")
    if report_values.get("payload_tree_sha256") != manifest["inventory"]["payload_tree_sha256"]:
        raise BuildError("SELF_CHECK_FAILED", "report payload tree mismatch")
    covered = set()
    for line in hashes_data.decode("utf-8").splitlines():
        digest, separator, relative = line.partition("  ")
        if not separator or relative not in on_disk:
            raise BuildError("SELF_CHECK_FAILED", "hashes line does not resolve")
        if sha256_file(build / relative) != digest:
            raise BuildError("SELF_CHECK_FAILED", f"hash mismatch for {relative}")
        covered.add(relative)
    if covered != payload | {MANIFEST}:
        raise BuildError("SELF_CHECK_FAILED", "hashes coverage is not payload+manifest")


def build(args: argparse.Namespace) -> dict:
    impl_sha = args.impl_sha
    _require_impl_id(impl_sha, field="--impl-sha")
    impl_content_sha256 = _optional_sha256(args.impl_content_sha256,
                                           field="--impl-content-sha256")
    packet_root = Path(args.packet_root).resolve()
    if packet_root.exists():
        raise BuildError("PACKET_ROOT_EXISTS",
                         "refusing to modify an existing packet directory")
    frozen_utc = args.frozen_utc or utc_now()
    metadata = _load_metadata(Path(args.metadata), impl_sha, impl_content_sha256)
    impl_git_commit = impl_sha if _GIT_COMMIT.fullmatch(impl_sha) else None
    if impl_git_commit is None:
        impl_git_commit = metadata.get("impl_git_commit")
    impl_content_sha256 = impl_content_sha256 or metadata.get("impl_content_sha256")
    snapshot = _load_livegate_snapshot(Path(args.livegate_snapshot))
    staging = Path(args.staging).resolve()
    if not staging.is_dir():
        raise BuildError("STAGING_INVALID", str(staging))

    packet_root.parent.mkdir(parents=True, exist_ok=True)
    build_dir = Path(tempfile.mkdtemp(prefix=".tmp-g4r-build-", dir=packet_root.parent))
    scratch = Path(tempfile.mkdtemp(prefix=".tmp-g4r-sqlite-"))
    try:
        _copy_staging_payload(staging, build_dir)
        for spec in args.sqlite:
            _snapshot_sqlite(spec, build_dir, scratch)
        snapshot_path = build_dir / LIVEGATE_SNAPSHOT_PATH
        if snapshot_path.exists():
            raise BuildError("STAGING_INVALID",
                             f"staging may not predefine {LIVEGATE_SNAPSHOT_PATH}")
        _write_file(snapshot_path, canonical_json_bytes(snapshot))

        inventory = _scan_tree(build_dir)
        payload = set(inventory)  # metadata files are written after this scan
        if any(_is_fixed_metadata(relative) for relative in payload):  # pragma: no cover
            raise BuildError("STAGING_INVALID", "staging predefines metadata files")
        manifest = {
            "schema": SCHEMA,
            "packet": {
                "name": packet_root.name,
                "format": PACKET_FORMAT,
                "frozen_utc": frozen_utc,
            },
            "identity": {
                # ``impl_sha`` is the CLI packet impl id (40-hex git commit or
                # 64-hex synthetic id); the two semantic fields below are kept
                # explicit so a git commit can never be confused with a content
                # digest.
                "impl_sha": impl_sha,
                "impl_git_commit": impl_git_commit,
                "impl_content_sha256": impl_content_sha256,
                "base_sha": metadata["base_sha"],
                "parent_sha": metadata.get("parent_sha"),
                "code_sha": metadata.get("code_sha"),
                "docs_sha": metadata.get("docs_sha"),
                "build_sha": metadata.get("build_sha"),
                "git_head_at_build": args.git_head,
            },
            "stage": metadata["stage"],
            "rootfs_sha256": metadata["rootfs_sha256"],
            "deps_sha256": metadata["deps_sha256"],
            "runtime": metadata["runtime"],
            "environment": metadata["environment"],
            "tests": metadata["tests"],
            "inventory": {
                "payload_count": len(payload),
                "hash_manifest_entry_count": len(payload) + 1,
                "total_regular_files": len(payload) + len(FIXED_METADATA_EXCEPTIONS),
                "payload_tree_sha256": _payload_tree(inventory),
                "file_modes": {relative: oct(FILE_MODE)
                               for relative in sorted(payload | {MANIFEST})},
                "metadata_exceptions": sorted(FIXED_METADATA_EXCEPTIONS),
                "file_mode": oct(FILE_MODE),
            },
            "live_gate": {
                "status": "BLOCKED",
                "snapshot_path": LIVEGATE_SNAPSHOT_PATH,
                "inspect_utc": snapshot.get("inspect_utc"),
                "reason_count": len(snapshot["reasons"]),
                "reasons_sha256": sha256_bytes(canonical_json_bytes(snapshot["reasons"])),
            },
            "status": metadata.get("status", "PENDING_INDEPENDENT_REVIEW"),
            "external_network_calls": 0,
            "real_model_calls": 0,
            "provider_keys_seen": 0,
            "limitations": metadata["limitations"],
        }
        # The manifest never stores the hashes-file digest (that would be a
        # circular dependency): hashes.sha256 covers payload+manifest, and the
        # unhashed integrity report anchors both digests for human/reviewer use.
        _write_file(build_dir / MANIFEST, canonical_json_bytes(manifest) + b"\n")
        manifest_sha = sha256_file(build_dir / MANIFEST)
        hashes_sha = _write_hashes(build_dir, _scan_tree(build_dir))
        manifest = _read_json_strict(build_dir / MANIFEST, code="SELF_CHECK_FAILED")
        _write_report(build_dir, manifest, manifest_sha, hashes_sha)

        # Re-read the final manifest (its bytes are covered by hashes.sha256).
        manifest = _read_json_strict(build_dir / MANIFEST, code="SELF_CHECK_FAILED")
        _self_check(build_dir, manifest)
        expected_files = _scan_tree(build_dir)
        if sha256_bytes(canonical_json_bytes(manifest) + b"\n") != manifest_sha:  # pragma: no cover
            raise BuildError("SELF_CHECK_FAILED", "manifest changed after hashing")
        os.rename(build_dir, packet_root)
        summary = {
            "schema": "m0.g4r.packet-build-result/v2",
            "status": "BUILT_AND_SELF_CHECKED",
            "packet_root": str(packet_root),
            "impl_sha": impl_sha,
            "impl_git_commit": impl_git_commit,
            "impl_content_sha256": impl_content_sha256,
            "frozen_utc": frozen_utc,
            "payload_count": manifest["inventory"]["payload_count"],
            "total_regular_files": manifest["inventory"]["total_regular_files"],
            "payload_tree_sha256": manifest["inventory"]["payload_tree_sha256"],
            "manifest_sha256": manifest_sha,
            "hashes_sha256": hashes_sha,
            "sqlite_snapshots": sorted(
                relative for relative in expected_files
                if relative.endswith(".sqlite3")),
            "live_gate_reason_count": manifest["live_gate"]["reason_count"],
            "external_network_calls": 0,
        }
        if args.json_out:
            Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
            Path(args.json_out).write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n",
                                           encoding="utf-8")
        return summary
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
        if build_dir.exists():
            for path in sorted(build_dir.rglob("*"), reverse=True):
                try:
                    if path.is_file():
                        path.chmod(0o600)
                except OSError:
                    pass
            shutil.rmtree(build_dir, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--impl-sha", required=True,
                        help="frozen 40-hex git commit (or 64-hex synthetic id)")
    parser.add_argument("--impl-content-sha256", default=None,
                        help="optional 64-hex sha256 of the canonical impl source tree")
    parser.add_argument("--staging", required=True, help="input payload tree")
    parser.add_argument("--metadata", required=True, help="identity/test metadata JSON")
    parser.add_argument("--livegate-snapshot", required=True,
                        help="single LiveGate.inspect JSON snapshot (reasons cross-referenced)")
    parser.add_argument("--sqlite", action="append", default=[],
                        help="repeatable 'dest/relative.sqlite3=source/db.sqlite3'")
    parser.add_argument("--packet-root",
                        default=None,
                        help="default artifacts/review-packet-g4r-v2-<impl_sha>")
    parser.add_argument("--frozen-utc", default=None,
                        help="explicit frozen UTC timestamp for reproducible manifests")
    parser.add_argument("--git-head", default=None)
    parser.add_argument("--json-out", default=None)
    args = parser.parse_args(argv)
    if args.packet_root is None:
        repo_root = Path(__file__).resolve().parents[2]
        args.packet_root = str(repo_root / "artifacts"
                               / f"review-packet-g4r-v2-{args.impl_sha}")
    try:
        summary = build(args)
    except BuildError as error:
        print(json.dumps({"status": "BUILD_REFUSED", "code": error.code,
                          "detail": error.detail}, sort_keys=True))
        return 1
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
