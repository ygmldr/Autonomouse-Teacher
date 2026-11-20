#!/usr/bin/env python3
"""Verify a G4-R review packet v2 by full-tree inventory (no SQLite, no network).

This is an *independent* checker: it intentionally re-implements the canonical
payload-tree digest and the strict inventory rules instead of importing
``build_packet_g4r.py``. It reads bytes only; it never calls ``sqlite3`` so
verification cannot create ``-wal``/``-shm`` sidecars inside the packet.

Failures (exit 1) carry explicit machine-readable reason codes, for example:

  UNLISTED_PATH / MISSING_PATH / HIDDEN_PATH / SYMLINK_PATH / NOT_REGULAR_FILE
  SQLITE_SIDECAR_PRESENT / HARDLINK_ANOMALY / HASH_MISMATCH / MODE_MISMATCH
  PAYLOAD_TREE_MISMATCH / COUNT_MISMATCH / HASHES_ENTRY_MISSING
  HASHES_ENTRY_EXTRA / HASH_MANIFEST_MISMATCH / INTEGRITY_REPORT_MISMATCH
  LIVEGATE_CROSSREF_MISMATCH / MANIFEST_INVALID / IMPL_SHA_MISMATCH

Expected layout:

  <packet>/manifest.json                 (hashed by hashes.sha256)
  <packet>/hashes.sha256                 (covers payload + manifest.json)
  <packet>/packet-integrity-report.txt   (unhashed anchor; content checked)
  <payload...>                           (everything else)

The three metadata files are a *fixed* exception set; no other unlisted file is
ever accepted, and the report itself is content-compared against recomputation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from pathlib import Path

SCHEMA = "m0.g4r.packet.manifest/v2"
LIVEGATE_SCHEMA = "m0.g4r.livegate-snapshot/v1"
MANIFEST = "manifest.json"
HASHES = "hashes.sha256"
REPORT = "packet-integrity-report.txt"
FIXED_METADATA_EXCEPTIONS = frozenset({MANIFEST, HASHES, REPORT})
FILE_MODE = 0o444
LIVEGATE_SNAPSHOT_PATH = "identity/livegate.json"
REPORT_KEYS = frozenset({
    "schema", "packet", "impl_sha", "frozen_utc", "payload_count",
    "hash_manifest_entry_count", "total_regular_files", "payload_tree_sha256",
    "manifest_sha256", "hashes_sha256", "metadata_exceptions",
    "external_network_calls", "live_gate",
})


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


def payload_tree_digest(entries: list[list[str]]) -> str:
    entries = sorted(entries, key=lambda item: item[0])
    return sha256_bytes(canonical_json_bytes(entries))


def _bad_relative(value: str) -> bool:
    if not isinstance(value, str) or not value or value.startswith("/"):
        return True
    if "\\" in value:
        return True
    parts = value.split("/")
    return any(part in ("", ".", "..") for part in parts)


def _is_sidecar(name: str) -> bool:
    return name.endswith(("-wal", "-shm", "-journal"))


class Verification:
    def __init__(self) -> None:
        self.issues: list[dict] = []

    def add(self, code: str, path: str | None = None, detail: str = "") -> None:
        issue = {"code": code}
        if path is not None:
            issue["path"] = path
        if detail:
            issue["detail"] = detail
        self.issues.append(issue)

    def fail(self) -> bool:
        return bool(self.issues)


def strict_inventory(root: Path, result: Verification) -> dict[str, dict]:
    """Independent lstat traversal: reject hidden/symlink/special/hardlink paths."""
    inventory: dict[str, dict] = {}
    stack: list[tuple[str, Path]] = [("", root)]
    while stack:
        prefix, directory = stack.pop()
        try:
            entries = sorted(os.scandir(directory), key=lambda item: item.name)
        except OSError as error:
            result.add("TREE_UNREADABLE", prefix or ".", str(error.strerror))
            continue
        for entry in entries:
            name = entry.name
            relative = f"{prefix}{name}"
            if _bad_relative(relative):
                result.add("PATH_NOT_NORMALIZED", relative)
                continue
            if name.startswith("."):
                result.add("HIDDEN_PATH", relative)
                continue
            info = entry.stat(follow_symlinks=False)
            mode = info.st_mode
            if stat.S_ISLNK(mode):
                result.add("SYMLINK_PATH", relative)
                continue
            if stat.S_ISDIR(mode):
                stack.append((relative + "/", Path(entry.path)))
                continue
            if not stat.S_ISREG(mode):
                result.add("NOT_REGULAR_FILE", relative)
                continue
            if info.st_nlink != 1:
                result.add("HARDLINK_ANOMALY", relative,
                           f"st_nlink={info.st_nlink}")
                continue
            if _is_sidecar(name):
                result.add("SQLITE_SIDECAR_PRESENT", relative)
            inventory[relative] = {
                "sha256": sha256_file(Path(entry.path)),
                "size": info.st_size,
                "mode": mode & 0o777,
            }
    return inventory


def read_json_strict(path: Path, result: Verification, *, code: str) -> dict | None:
    try:
        info = path.lstat()
    except OSError:
        result.add(code, path.name, "missing")
        return None
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        result.add(code, path.name, "not a regular file")
        return None
    if info.st_size <= 0 or info.st_size > 8 << 20:
        result.add(code, path.name, "size outside permitted range")
        return None
    try:
        value = json.loads(path.read_bytes(), object_pairs_hook=_reject_duplicate_keys)
    except (ValueError, UnicodeDecodeError) as error:
        result.add(code, path.name, f"not strict JSON: {error}")
        return None
    if not isinstance(value, dict):
        result.add(code, path.name, "must be a JSON object")
        return None
    return value


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    seen: dict = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError(f"duplicate key: {key}")
        seen[key] = value
    return seen


def parse_hashes(data: bytes, result: Verification) -> dict[str, str]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        result.add("HASHES_FILE_INVALID", HASHES, "not UTF-8")
        return {}
    entries: dict[str, str] = {}
    previous = None
    for number, line in enumerate(text.splitlines(), start=1):
        if not line:
            continue
        digest, separator, relative = line.partition("  ")
        if (not separator or len(digest) != 64
                or any(char not in "0123456789abcdef" for char in digest)
                or relative != relative.strip() or _bad_relative(relative)):
            result.add("HASHES_FILE_INVALID", HASHES, f"line {number}")
            continue
        if relative in entries:
            result.add("HASHES_FILE_INVALID", HASHES, f"duplicate line {relative}")
            continue
        if previous is not None and relative <= previous:
            result.add("HASHES_FILE_INVALID", HASHES, f"unsorted line {relative}")
        previous = relative
        entries[relative] = digest
    return entries


def parse_report(data: bytes, result: Verification) -> dict[str, str]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        result.add("INTEGRITY_REPORT_MISMATCH", REPORT, "not UTF-8")
        return {}
    values: dict[str, str] = {}
    for line in text.splitlines():
        if not line:
            continue
        key, separator, value = line.partition("=")
        if not separator or key in values:
            result.add("INTEGRITY_REPORT_MISMATCH", REPORT, f"bad line {line[:40]!r}")
            continue
        values[key] = value
    missing = REPORT_KEYS - set(values)
    if missing:
        result.add("INTEGRITY_REPORT_MISMATCH", REPORT, f"missing {sorted(missing)}")
    extra = set(values) - REPORT_KEYS
    if extra:
        result.add("INTEGRITY_REPORT_MISMATCH", REPORT, f"unexpected {sorted(extra)}")
    return values


def check_livegate(packet_root: Path, manifest: dict, inventory: dict[str, dict],
                   result: Verification, report_values: dict[str, str]) -> None:
    block = manifest.get("live_gate")
    if not isinstance(block, dict):
        result.add("MANIFEST_INVALID", MANIFEST, "missing live_gate object")
        return
    snapshot_path = block.get("snapshot_path")
    if snapshot_path != LIVEGATE_SNAPSHOT_PATH:
        result.add("LIVEGATE_CROSSREF_MISMATCH", MANIFEST,
                   f"snapshot_path {snapshot_path!r}")
        return
    if snapshot_path not in inventory:
        result.add("LIVEGATE_CROSSREF_MISMATCH", snapshot_path, "snapshot not in payload")
        return
    snapshot = read_json_strict(packet_root / snapshot_path, result,
                                code="LIVEGATE_CROSSREF_MISMATCH")
    if snapshot is None:
        return
    reasons = snapshot.get("reasons")
    if (snapshot.get("schema") != LIVEGATE_SCHEMA
            or snapshot.get("live_gate") != "BLOCKED"
            or not isinstance(reasons, list) or not reasons
            or any(not isinstance(item, str) or not item for item in reasons)):
        result.add("LIVEGATE_CROSSREF_MISMATCH", snapshot_path,
                   "snapshot is not a BLOCKED reasons document")
        return
    if block.get("status") != "BLOCKED" or block.get("reason_count") != len(reasons):
        result.add("LIVEGATE_CROSSREF_MISMATCH", MANIFEST,
                   "manifest live_gate status/count differs from snapshot")
    reasons_digest = sha256_bytes(canonical_json_bytes(reasons))
    if block.get("reasons_sha256") != reasons_digest:
        result.add("LIVEGATE_CROSSREF_MISMATCH", MANIFEST,
                   "manifest reasons_sha256 differs from snapshot reasons")
    # Every payload JSON document that references a snapshot must reference this
    # same single snapshot (manifest/env/review element-wise equality is enforced
    # through the shared digest above; count is never hardcoded).
    for relative in sorted(inventory):
        if not relative.endswith(".json") or relative == snapshot_path:
            continue
        if inventory[relative]["size"] > 1 << 20:
            continue
        raw = (packet_root / relative).read_bytes()
        if b'"snapshot_ref"' not in raw:
            continue
        document = read_json_strict(packet_root / relative, result,
                                    code="LIVEGATE_CROSSREF_MISMATCH")
        if document is None:
            continue
        if document.get("snapshot_ref") != snapshot_path:
            result.add("LIVEGATE_CROSSREF_MISMATCH", relative,
                       f"snapshot_ref {document.get('snapshot_ref')!r}")
    if report_values.get("live_gate") != "BLOCKED":
        result.add("INTEGRITY_REPORT_MISMATCH", REPORT, "live_gate is not BLOCKED")


def verify(packet_root: Path, *, expected_impl_sha: str | None = None) -> dict:
    result = Verification()
    if not packet_root.is_dir() or packet_root.is_symlink():
        result.add("PACKET_ROOT_INVALID", str(packet_root))
        return {"status": "FAIL", "issues": result.issues}
    inventory = strict_inventory(packet_root, result)
    on_disk = set(inventory)
    metadata = {relative for relative in on_disk if relative in FIXED_METADATA_EXCEPTIONS}
    for relative in sorted(FIXED_METADATA_EXCEPTIONS - metadata):
        result.add("MISSING_PATH", relative)

    manifest = read_json_strict(packet_root / MANIFEST, result, code="MANIFEST_INVALID")
    if manifest is None:
        manifest = {}
    if manifest and manifest.get("schema") != SCHEMA:
        result.add("MANIFEST_INVALID", MANIFEST, "unknown schema")
    identity = manifest.get("identity") if isinstance(manifest.get("identity"), dict) else {}
    if expected_impl_sha is not None and identity.get("impl_sha") != expected_impl_sha:
        result.add("IMPL_SHA_MISMATCH", MANIFEST,
                   f"impl_sha {identity.get('impl_sha')!r}")

    hashes = {}
    hashes_digest = None
    listed_payload: set[str] = set()
    if HASHES in metadata:
        hashes_data = (packet_root / HASHES).read_bytes()
        hashes_digest = sha256_bytes(hashes_data)
        hashes = parse_hashes(hashes_data, result)
        listed_payload = set(hashes) - {MANIFEST}
        # The hashes file is the declared file set: anything physical that it does
        # not list (and that is not a fixed metadata exception) is UNLISTED.
        for relative in sorted(on_disk - listed_payload - FIXED_METADATA_EXCEPTIONS):
            result.add("UNLISTED_PATH", relative)
        for relative in sorted(set(hashes) & (FIXED_METADATA_EXCEPTIONS - {MANIFEST})):
            result.add("HASHES_ENTRY_EXTRA", relative,
                       "metadata exception must not be hash-covered")
        for relative, digest in sorted(hashes.items()):
            record = inventory.get(relative)
            if record is None:
                result.add("MISSING_PATH", relative, "hashed path not on disk")
                continue
            if record["sha256"] != digest:
                result.add("HASH_MISMATCH", relative)

    payload = listed_payload
    inventory_block = (manifest.get("inventory")
                       if isinstance(manifest.get("inventory"), dict) else {})
    computed_tree = payload_tree_digest(
        [[relative, inventory[relative]["sha256"]]
         for relative in sorted(payload) if relative in inventory])
    if inventory_block.get("payload_tree_sha256") != computed_tree:
        result.add("PAYLOAD_TREE_MISMATCH", MANIFEST,
                   f"computed {computed_tree} declared "
                   f"{inventory_block.get('payload_tree_sha256')!r}")
    declared_payload = inventory_block.get("payload_count")
    if declared_payload != len(payload):
        result.add("COUNT_MISMATCH", MANIFEST,
                   f"payload_count {declared_payload!r} != {len(payload)}")
    declared_entries = inventory_block.get("hash_manifest_entry_count")
    expected_entry_count = len(payload) + 1
    if declared_entries != expected_entry_count or len(hashes) != expected_entry_count:
        result.add("COUNT_MISMATCH", MANIFEST,
                   f"hash_manifest_entry_count {declared_entries!r}/"
                   f"{len(hashes)} != {expected_entry_count}")
    declared_total = inventory_block.get("total_regular_files")
    if declared_total != len(on_disk):
        result.add("COUNT_MISMATCH", MANIFEST,
                   f"total_regular_files {declared_total!r} != {len(on_disk)}")
    exceptions = inventory_block.get("metadata_exceptions")
    if (not isinstance(exceptions, list)
            or set(exceptions) != FIXED_METADATA_EXCEPTIONS
            or len(exceptions) != len(FIXED_METADATA_EXCEPTIONS)):
        result.add("MANIFEST_INVALID", MANIFEST, "metadata_exceptions is not fixed")
    if inventory_block.get("file_mode") != oct(FILE_MODE):
        result.add("MANIFEST_INVALID", MANIFEST, "declared file_mode is not 0444")
    declared_modes = inventory_block.get("file_modes")
    if not isinstance(declared_modes, dict):
        result.add("MANIFEST_INVALID", MANIFEST, "file_modes must be an object")
    else:
        for relative in sorted(payload | {MANIFEST}):
            actual = oct(inventory.get(relative, {}).get("mode", -1))
            if declared_modes.get(relative) != actual:
                result.add("MODE_MISMATCH", relative,
                           f"declared {declared_modes.get(relative)!r} actual {actual}")
        for relative in sorted(set(declared_modes) - (payload | {MANIFEST})):
            result.add("MANIFEST_INVALID", MANIFEST,
                       f"file_modes lists non-hashed path {relative}")

    report_values: dict[str, str] = {}
    if REPORT in metadata:
        report_values = parse_report((packet_root / REPORT).read_bytes(), result)
        expected_report = {
            "schema": "m0.g4r.packet-integrity-report/v2",
            "packet": str((manifest.get("packet") or {}).get("name")),
            "impl_sha": str(identity.get("impl_sha")),
            "frozen_utc": str((manifest.get("packet") or {}).get("frozen_utc")),
            "payload_count": str(inventory_block.get("payload_count")),
            "hash_manifest_entry_count": str(
                inventory_block.get("hash_manifest_entry_count")),
            "total_regular_files": str(inventory_block.get("total_regular_files")),
            "payload_tree_sha256": computed_tree,
            "manifest_sha256": sha256_bytes((packet_root / MANIFEST).read_bytes())
            if MANIFEST in metadata else "",
            "hashes_sha256": hashes_digest or "",
            "metadata_exceptions": ",".join(sorted(FIXED_METADATA_EXCEPTIONS)),
            "external_network_calls": "0",
            "live_gate": "BLOCKED",
        }
        for key, expected in sorted(expected_report.items()):
            if report_values.get(key) != expected:
                result.add("INTEGRITY_REPORT_MISMATCH", REPORT,
                           f"{key}: {report_values.get(key)!r} != {expected!r}")
    check_livegate(packet_root, manifest, inventory, result, report_values)

    summary = {
        "schema": "m0.g4r.packet-verify-result/v2",
        "status": "PASS" if not result.fail() else "FAIL",
        "packet_root": str(packet_root),
        "payload_count": len(payload),
        "total_regular_files": len(on_disk),
        "hash_manifest_entry_count": len(hashes),
        "payload_tree_sha256": computed_tree,
        "manifest_sha256": (sha256_bytes((packet_root / MANIFEST).read_bytes())
                            if MANIFEST in metadata else None),
        "hashes_sha256": hashes_digest,
        "symlink_count": sum(1 for issue in result.issues
                             if issue["code"] == "SYMLINK_PATH"),
        "unlisted_count": sum(1 for issue in result.issues
                              if issue["code"] == "UNLISTED_PATH"),
        "mismatched_count": sum(1 for issue in result.issues
                                if issue["code"] == "HASH_MISMATCH"),
        "issues": result.issues,
    }
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet-root", required=True)
    parser.add_argument("--expected-impl-sha", default=None)
    parser.add_argument("--json-out", default=None)
    args = parser.parse_args(argv)
    summary = verify(Path(args.packet_root), expected_impl_sha=args.expected_impl_sha)
    if args.json_out:
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n",
                                       encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
