#!/usr/bin/env python3
"""G4-R Reviewer independent G4-R Packet v2 verifier (R-REV5).

Reviewer-authored, self-contained: it does NOT import or reuse
``scripts/g4r/verify_packet_g4r.py`` or the builder. It walks the packet with
its own logic and enforces:

  * only regular files, mode 0444, nlink==1, no symlinks/hardlinks/specials;
  * fixed allow-list: payload files + manifest.json + hashes.sha256 +
    packet-integrity-report.txt; no hidden entries, no unknown files, no
    ``-wal/-shm/-journal`` residue;
  * manifest schema/identity (40-hex git commit or 64-hex id; impl_git_commit
    agreement; expected impl sha membership), inventory counts/modes and
    payload tree sha256 recomputed independently (canonical JSON list of
    ``[relative, sha256]`` pairs, sorted by relative path);
  * hashes.sha256 covers exactly payload+manifest, every digest recomputed;
  * integrity report anchors manifest/hashes/tree digests consistently;
  * live gate snapshot BLOCKED, reason list/count/digest agree, no real
    key/model/network calls recorded;
  * SQLite snapshots readable read-only with ``immutable=1`` and quick_check OK,
    and the packet tree is unchanged after opening them (no -wal/-shm created);
  * optional old v1 Packet immutable check (frozen manifest/hashes digests,
    177 regular files, 0 symlinks);
  * mutation injections on a /tmp copy: adding -wal / hidden / unknown files,
    symlink replacement, byte tamper, manifest identity tamper, file removal and
    mode change must each be detected (nonzero failure set). Exit 0 only if the
    packet is clean AND every mutation is detected.

Usage:
  PYTHONPATH=src python scripts/g4r_review/r_rev5_packet_verifier.py \
      --packet <packet-dir> --expected-impl-sha <sha> \
      [--v1-packet <dir>] [--out report.json] [--skip-mutations]

No network, no key, no writes to the packet (mutations are exercised on copies).
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
from pathlib import Path

MANIFEST = "manifest.json"
HASHES = "hashes.sha256"
REPORT = "packet-integrity-report.txt"
METADATA = {MANIFEST, HASHES, REPORT}
VELOCITY_SUFFIXES = ("-wal", "-shm", "-journal")
MANIFEST_SCHEMA = "m0.g4r.packet.manifest/v2"
FILE_MODE = 0o444
GIT_COMMIT = re.compile(r"[a-f0-9]{40}\Z")
SHA256 = re.compile(r"[a-f0-9]{64}\Z")
V1_FROZEN = {
    "manifest_sha256": "4aed2a923ea3fae52ed3eac9d0c5838077242ed32045804d687dcef703a1d7f2",
    "hashes_sha256": "421b07ae3ad0eac2d36c032cd384d252dfda4ac521e193577aed56fc60ca9d3d",
    "files": 177,
    "symlinks": 0,
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def issues_add(issues: list[str], code: str, detail: str = "") -> None:
    issues.append(f"{code}:{detail}" if detail else code)


def _walk(packet: Path):
    """Yield (relative, kind, info) for every entry without following links."""
    for root, dirs, names in os.walk(packet, followlinks=False):
        dirs.sort()
        for name in sorted(dirs):
            path = Path(root) / name
            yield path.relative_to(packet).as_posix(), "dir", path.lstat()
        for name in sorted(names):
            path = Path(root) / name
            yield path.relative_to(packet).as_posix(), "file", path.lstat()


def _load_strict_json(path: Path, issues: list[str], label: str):
    try:
        raw = path.read_bytes()
        if not raw or len(raw) > 1 << 20:
            issues_add(issues, "MANIFEST_INVALID", f"{label} size")
            return None
        return json.loads(raw)
    except (OSError, ValueError) as error:
        issues_add(issues, "MANIFEST_INVALID", f"{label} unreadable: {error}")
        return None


def payload_tree(entries: dict[str, str]) -> str:
    pairs = sorted([[relative, digest] for relative, digest in entries.items()])
    return sha256_bytes(canonical_json(pairs))


def verify(packet: Path, *, expected_impl_sha: str | None = None,
           v1_packet: Path | None = None, check_sqlite: bool = True) -> list[str]:
    issues: list[str] = []
    if not packet.is_dir():
        return [f"PACKET_MISSING:{packet}"]
    entries: dict[str, tuple[str, os.stat_result]] = {}
    dirs: list[str] = []
    for relative, kind, info in _walk(packet):
        if kind == "dir":
            dirs.append(relative)
            continue
        entries[relative] = (kind, info)
        if stat.S_ISLNK(info.st_mode):
            issues_add(issues, "SYMLINK_PRESENT", relative)
        elif not stat.S_ISREG(info.st_mode):
            issues_add(issues, "NOT_REGULAR_FILE", relative)
        if info.st_nlink != 1:
            issues_add(issues, "HARDLINK_ANOMALY", relative)
        if info.st_mode & 0o777 != FILE_MODE:
            issues_add(issues, "FILE_MODE", f"{relative}={oct(info.st_mode & 0o777)}")
        if relative.startswith(".") or "/." in relative:
            issues_add(issues, "HIDDEN_ENTRY", relative)
        if relative.endswith(VELOCITY_SUFFIXES):
            issues_add(issues, "SQLITE_SIDECAR_PRESENT", relative)
    for relative in dirs:
        if relative.startswith(".") or "/." in relative:
            issues_add(issues, "HIDDEN_DIR", relative)
    if not entries:
        return issues + ["NO_FILES"]

    manifest_path = packet / MANIFEST
    hashes_path = packet / HASHES
    report_path = packet / REPORT
    for required in METADATA:
        if required not in entries:
            issues_add(issues, "METADATA_MISSING", required)
    if issues and any(code.startswith(("METADATA_MISSING", "NOT_REGULAR_FILE",
                                       "SYMLINK_PRESENT")) for code in issues):
        return issues
    manifest = _load_strict_json(manifest_path, issues, MANIFEST)
    if manifest is None:
        return issues
    if not isinstance(manifest, dict) or manifest.get("schema") != MANIFEST_SCHEMA:
        issues_add(issues, "MANIFEST_INVALID", "schema")
    # -- identity ---------------------------------------------------------
    identity = manifest.get("identity")
    if not isinstance(identity, dict):
        identity = {}
        issues_add(issues, "MANIFEST_INVALID", "identity")
    impl_sha = identity.get("impl_sha")
    impl_git = identity.get("impl_git_commit")
    impl_content = identity.get("impl_content_sha256")
    if not (isinstance(impl_sha, str) and (GIT_COMMIT.fullmatch(impl_sha)
                                           or SHA256.fullmatch(impl_sha))):
        issues_add(issues, "MANIFEST_INVALID", "identity.impl_sha format")
    if isinstance(impl_sha, str) and GIT_COMMIT.fullmatch(impl_sha) and impl_git != impl_sha:
        issues_add(issues, "MANIFEST_INVALID", "impl_git_commit != 40-hex impl_sha")
    if impl_git is not None and not (isinstance(impl_git, str)
                                     and GIT_COMMIT.fullmatch(impl_git)):
        issues_add(issues, "MANIFEST_INVALID", "impl_git_commit format")
    if impl_content is not None and not (isinstance(impl_content, str)
                                         and SHA256.fullmatch(impl_content)):
        issues_add(issues, "MANIFEST_INVALID", "impl_content_sha256 format")
    if expected_impl_sha is not None:
        candidates = {value for value in (impl_sha, impl_git, impl_content)
                      if isinstance(value, str)}
        if expected_impl_sha not in candidates:
            issues_add(issues, "IMPL_SHA_MISMATCH", f"expected {expected_impl_sha!r}")
    if manifest.get("live_gate", {}).get("status") != "BLOCKED":
        issues_add(issues, "LIVEGATE_NOT_BLOCKED", str(manifest.get("live_gate")))
    for field in ("external_network_calls", "real_model_calls", "provider_keys_seen"):
        if manifest.get(field) not in (0, None):
            issues_add(issues, "NONZERO_SAFETY_COUNTER", f"{field}={manifest.get(field)}")

    # -- inventory / tree / modes ----------------------------------------
    payload = {relative: sha256_file(Path(str(packet / relative)))
               for relative in entries if relative not in METADATA}
    inventory = manifest.get("inventory")
    if not isinstance(inventory, dict):
        inventory = {}
        issues_add(issues, "MANIFEST_INVALID", "inventory")
    if inventory.get("payload_count") != len(payload):
        issues_add(issues, "PAYLOAD_COUNT", f"{inventory.get('payload_count')}!={len(payload)}")
    if inventory.get("hash_manifest_entry_count") != len(payload) + 1:
        issues_add(issues, "HASH_ENTRY_COUNT")
    if inventory.get("total_regular_files") != len(entries):
        issues_add(issues, "TOTAL_FILES", f"{inventory.get('total_regular_files')}!={len(entries)}")
    if inventory.get("metadata_exceptions") != sorted(METADATA):
        issues_add(issues, "METADATA_EXCEPTIONS")
    tree = payload_tree(payload)
    if inventory.get("payload_tree_sha256") != tree:
        issues_add(issues, "PAYLOAD_TREE_MISMATCH", f"{inventory.get('payload_tree_sha256')}!={tree}")
    declared_modes = inventory.get("file_modes") or {}
    expected_modes = {relative: oct(FILE_MODE) for relative in sorted(payload)}
    expected_modes[MANIFEST] = oct(FILE_MODE)
    if declared_modes != expected_modes:
        issues_add(issues, "FILE_MODES_MANIFEST_MISMATCH")

    # -- hashes.sha256 ----------------------------------------------------
    hashes: dict[str, str] = {}
    for line in hashes_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        parts = line.split("  ", 1)
        if len(parts) != 2 or not SHA256.fullmatch(parts[0]):
            issues_add(issues, "HASHES_LINE_INVALID", line[:80])
            continue
        if parts[1] in hashes:
            issues_add(issues, "HASHES_DUPLICATE", parts[1])
        hashes[parts[1]] = parts[0]
    expected_covered = set(payload) | {MANIFEST}
    if set(hashes) != expected_covered:
        issues_add(issues, "HASHES_COVERAGE",
                   f"missing={sorted(expected_covered - set(hashes))[:5]} "
                   f"extra={sorted(set(hashes) - expected_covered)[:5]}")
    for relative, digest in hashes.items():
        if relative not in entries:
            issues_add(issues, "HASHES_UNKNOWN_FILE", relative)
            continue
        actual = sha256_file(packet / relative)
        if actual != digest:
            issues_add(issues, "HASHES_MISMATCH", relative)

    # -- integrity report consistency ------------------------------------
    report_text = report_path.read_text(encoding="utf-8")
    report_values = {}
    for line in report_text.splitlines():
        while line.startswith("#"):
            line = line[1:]
        separator = "=" if "=" in line else (":" if ":" in line else None)
        if separator is None:
            continue
        key, value = line.split(separator, 1)
        report_values[key.strip()] = value.strip()
    for label, actual in (("manifest_sha256", sha256_file(manifest_path)),
                          ("hashes_sha256", sha256_file(hashes_path)),
                          ("payload_tree_sha256", tree)):
        if report_values.get(label) != actual:
            issues_add(issues, "REPORT_DIGEST_MISMATCH", label)

    # -- live gate snapshot ----------------------------------------------
    snapshot_rel = manifest.get("live_gate", {}).get("snapshot_path")
    if isinstance(snapshot_rel, str):
        snapshot_path = packet / snapshot_rel
        if not snapshot_path.is_file():
            issues_add(issues, "LIVEGATE_SNAPSHOT_MISSING", snapshot_rel)
        else:
            snapshot = _load_strict_json(snapshot_path, issues, "livegate snapshot")
            if isinstance(snapshot, dict):
                reasons = snapshot.get("reasons")
                status = snapshot.get("status")
                if status is not None and status != "BLOCKED":
                    issues_add(issues, "LIVEGATE_SNAPSHOT_NOT_BLOCKED", str(status))
                if status is None and snapshot.get("live_gate") not in (None, "BLOCKED"):
                    issues_add(issues, "LIVEGATE_SNAPSHOT_NOT_BLOCKED", str(snapshot.get("live_gate")))
                if not isinstance(reasons, list) or not all(isinstance(r, str) for r in reasons):
                    issues_add(issues, "LIVEGATE_REASONS_INVALID")
                else:
                    live_gate = manifest.get("live_gate", {})
                    if live_gate.get("reason_count") != len(reasons):
                        issues_add(issues, "LIVEGATE_REASON_COUNT")
                    if live_gate.get("reasons_sha256") != sha256_bytes(canonical_json(reasons)):
                        issues_add(issues, "LIVEGATE_REASONS_DIGEST")

    # -- SQLite snapshots: read-only, immutable, no sidecars -----------------
    if check_sqlite:
        before = {relative: (info.st_size, info.st_mtime_ns)
                  for relative, (kind, info) in entries.items()}
        for relative in sorted(payload):
            if not relative.endswith((".sqlite3", ".sqlite", ".db")):
                continue
            uri = f"file:{packet / relative}?mode=ro&immutable=1"
            try:
                connection = sqlite3.connect(uri, uri=True)
                try:
                    connection.execute("PRAGMA quick_check").fetchone()
                    connection.execute("SELECT count(*) FROM sqlite_master").fetchone()
                finally:
                    connection.close()
            except sqlite3.Error as error:
                issues_add(issues, "SQLITE_UNREADABLE", f"{relative}: {error}")
        after = {}
        for relative, kind, info in _walk(packet):
            if kind == "file":
                after[relative] = (info.st_size, info.st_mtime_ns)
        if after != before:
            issues_add(issues, "PACKET_MUTATED_BY_READ")

    # -- old v1 packet immutability --------------------------------------
    if v1_packet is not None:
        files = [p for p in v1_packet.rglob("*") if p.is_file() and not p.is_symlink()]
        symlinks = [p for p in v1_packet.rglob("*") if p.is_symlink()]
        if len(files) != V1_FROZEN["files"]:
            issues_add(issues, "V1_FILE_COUNT", f"{len(files)}")
        if len(symlinks) != V1_FROZEN["symlinks"]:
            issues_add(issues, "V1_SYMLINK_COUNT", f"{len(symlinks)}")
        for name, expected in (("manifest.json", V1_FROZEN["manifest_sha256"]),
                               ("hashes.sha256", V1_FROZEN["hashes_sha256"])):
            if sha256_file(v1_packet / name) != expected:
                issues_add(issues, "V1_FROZEN_BYTE_CHANGED", name)
    return issues


def _run_mutations(packet: Path, expected_impl_sha: str | None) -> list[str]:
    """Every mutation on a /tmp copy must be detected. Returns undetected list."""
    temp_dir = Path(tempfile.mkdtemp(prefix="g4r-packet-mutations-"))
    undetected: list[str] = []
    payload_names = sorted(relative for relative in
                           (p.relative_to(packet).as_posix() for p in packet.rglob("*")
                            if p.is_file()) if relative not in METADATA)
    if not payload_names:
        shutil.rmtree(temp_dir, ignore_errors=True)
        return ["no payload files to mutate"]
    target = payload_names[0]
    manifest_target = payload_names[len(payload_names) // 2]

    def prepare(name: str) -> Path:
        copy = temp_dir / name
        shutil.copytree(packet, copy)
        return copy

    def expect_failure(label: str, mutate) -> None:
        copy = prepare(label)
        try:
            mutate(copy)
            found = verify(copy, expected_impl_sha=expected_impl_sha,
                           check_sqlite=False)
            if not found:
                undetected.append(label)
        finally:
            shutil.rmtree(copy, ignore_errors=True)

    expect_failure("add-wal", lambda copy: _write_extra(copy, "cases/x.sqlite3-wal"))
    expect_failure("add-shm", lambda copy: _write_extra(copy, "cases/x.sqlite3-shm"))
    expect_failure("add-hidden", lambda copy: (copy / ".hidden").write_bytes(b"x"))
    expect_failure("add-unknown", lambda copy: (copy / "unknown-extra.txt").write_bytes(b"x"))
    expect_failure("symlink-swap", lambda copy: _swap_with_symlink(copy, target))
    expect_failure("byte-tamper", lambda copy: _tamper(copy / target))
    expect_failure("manifest-identity-tamper",
                   lambda copy: _tamper_manifest(copy / MANIFEST))
    expect_failure("file-removal", lambda copy: (copy / manifest_target).unlink())
    expect_failure("mode-change", lambda copy: (copy / target).chmod(0o644))
    expect_failure("hardlink-anomaly", lambda copy: _add_hardlink(copy, target))
    expect_failure("livegate-tamper", lambda copy: _tamper_livegate(copy))
    shutil.rmtree(temp_dir, ignore_errors=True)
    return undetected


def _write_extra(copy: Path, relative: str) -> None:
    path = copy / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")


def _add_hardlink(copy: Path, relative: str) -> None:
    source = copy / relative
    os.link(source, copy / "hardlink-anomaly.copy")


def _tamper_livegate(copy: Path) -> None:
    for path in copy.rglob("*.json"):
        document = json.loads(path.read_bytes())
        if isinstance(document, dict) and "reasons" in document:
            document["reasons"] = ["FORGED_REASON"]
            path.write_bytes(canonical_json(document) + b"\n")
            return
    raise AssertionError("no livegate snapshot found")


def _swap_with_symlink(copy: Path, relative: str) -> None:
    target = copy / relative
    content = target.read_bytes()
    side = copy / (relative + ".side")
    side.write_bytes(content)
    target.unlink()
    target.symlink_to(side.name)


def _tamper(path: Path) -> None:
    data = bytearray(path.read_bytes())
    data[0] = data[0] ^ 0xFF if data else 0
    path.write_bytes(bytes(data))


def _tamper_manifest(path: Path) -> None:
    manifest = json.loads(path.read_bytes())
    manifest["identity"]["impl_sha"] = "0" * 40
    manifest["identity"]["impl_git_commit"] = "0" * 40
    path.write_bytes(canonical_json(manifest) + b"\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", required=True, type=Path)
    parser.add_argument("--expected-impl-sha", default=None)
    parser.add_argument("--v1-packet", default=None, type=Path)
    parser.add_argument("--out", default=None, type=Path)
    parser.add_argument("--skip-mutations", action="store_true")
    args = parser.parse_args(argv)

    issues = verify(args.packet, expected_impl_sha=args.expected_impl_sha,
                    v1_packet=args.v1_packet)
    undetected = [] if args.skip_mutations else _run_mutations(
        args.packet, args.expected_impl_sha)
    report = {
        "packet": str(args.packet),
        "expected_impl_sha": args.expected_impl_sha,
        "issues": issues,
        "mutation_undetected": undetected,
        "status": "PASS" if not issues and not undetected else "FAIL",
    }
    print(json.dumps(report, indent=1, sort_keys=True))
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    if issues:
        print("PACKET ISSUES:", issues)
        return 1
    if undetected:
        print("UNDETECTED MUTATIONS:", undetected)
        return 1
    print("R-REV5 PACKET OK: clean tree + all mutation injections detected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
