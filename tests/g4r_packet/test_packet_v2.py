"""R4-01..R4-06: strict-inventory packet v2 builder/verifier tests.

The verifier must FAIL for every form of out-of-inventory change: new sqlite
sidecars, hidden/unknown files, deleted files, byte/mode tampering, symlinks,
hardlink anomalies, and manifest/hashes edits. Mutation is only ever applied to
a temporary *copy*; the original build output is left untouched.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys

import pytest

import support

MANIFEST = "manifest.json"
HASHES = "hashes.sha256"
REPORT = "packet-integrity-report.txt"
EXCEPTIONS = {MANIFEST, HASHES, REPORT}


def _issue_codes(document: dict) -> set[str]:
    return {issue["code"] for issue in document.get("issues", [])}


def _payload_file(packet: Path) -> Path:
    for entry in sorted(packet.rglob("*")):
        if (entry.is_file() and not entry.is_symlink()
                and entry.relative_to(packet).as_posix() not in EXCEPTIONS):
            return entry
    raise AssertionError("packet has no payload file")


# ---------------------------------------------------------------------------
# R4-01: pristine packet verifies, counts/tree/modes consistent, owner and
# independent traversals agree, and the builder refuses to destroy a packet.
# ---------------------------------------------------------------------------
def test_r4_01_pristine_packet_verifies_and_counts_are_consistent(tmp_path) -> None:
    packet, build_summary = support.build_packet(tmp_path)
    exit_code, document = support.verify_packet(packet)
    assert exit_code == 0, document
    assert document["status"] == "PASS"
    assert document["issues"] == []
    assert document["symlink_count"] == 0
    assert document["unlisted_count"] == 0
    assert document["mismatched_count"] == 0

    manifest = support.read_json(packet / MANIFEST)
    files = support.walk_files(packet)
    payload = set(files) - EXCEPTIONS
    assert manifest["inventory"]["payload_count"] == len(payload)
    assert manifest["inventory"]["total_regular_files"] == len(files)
    assert manifest["inventory"]["hash_manifest_entry_count"] == len(payload) + 1
    assert manifest["inventory"]["metadata_exceptions"] == sorted(EXCEPTIONS)
    independent_tree = support.payload_tree(files, EXCEPTIONS)
    assert manifest["inventory"]["payload_tree_sha256"] == independent_tree
    assert document["payload_tree_sha256"] == independent_tree
    assert build_summary["payload_count"] == len(payload)
    assert build_summary["total_regular_files"] == len(files)
    # Every payload file plus manifest is hashed; metadata modes are 0444.
    hashes_lines = (packet / HASHES).read_text(encoding="utf-8").splitlines()
    assert len(hashes_lines) == len(payload) + 1
    hashed_paths = {line.partition("  ")[2] for line in hashes_lines}
    assert hashed_paths == payload | {MANIFEST}
    for relative, record in files.items():
        if relative in payload or relative == MANIFEST:
            assert record["mode"] == 0o444, relative
    assert not [name for name in files if name.endswith(("-wal", "-shm", "-journal"))]


def test_r4_01_builder_refuses_existing_root_and_bad_staging(tmp_path) -> None:
    packet, _ = support.build_packet(tmp_path)
    metadata = tmp_path / "metadata.json"
    livegate = tmp_path / "livegate.json"
    staging = support.staging_tree(tmp_path / "second")
    second_root = tmp_path / "review-packet-g4r-v2-test"
    completed = support.run([
        sys.executable, str(support.BUILDER),
        "--impl-sha", support.IMPL_SHA, "--staging", str(staging),
        "--metadata", str(metadata), "--livegate-snapshot", str(livegate),
        "--packet-root", str(second_root), "--frozen-utc", support.FROZEN_UTC,
    ])
    assert completed.returncode == 1
    assert json.loads(completed.stdout)["code"] == "PACKET_ROOT_EXISTS"
    # The existing packet was not modified by the refused rebuild.
    assert support.verify_packet(packet)[0] == 0

    symlink_staging = support.staging_tree(tmp_path / "symlink")
    os.symlink(symlink_staging / "README.md", symlink_staging / "linked.md")
    source = tmp_path / "source-refusal.sqlite3"
    support.make_sqlite_source(source)
    third = support.run([
        sys.executable, str(support.BUILDER),
        "--impl-sha", support.IMPL_SHA, "--staging", str(symlink_staging),
        "--metadata", str(metadata), "--livegate-snapshot", str(livegate),
        "--sqlite", f"cases/r4-packet/ledger.sqlite3={source}",
        "--packet-root", str(tmp_path / "third-packet"),
        "--frozen-utc", support.FROZEN_UTC,
    ])
    assert third.returncode == 1
    assert json.loads(third.stdout)["code"] == "SYMLINK_PATH"

    hidden_staging = support.staging_tree(tmp_path / "hidden")
    (hidden_staging / ".hidden").write_text("x", encoding="utf-8")
    hidden = support.run([
        sys.executable, str(support.BUILDER),
        "--impl-sha", support.IMPL_SHA, "--staging", str(hidden_staging),
        "--metadata", str(metadata), "--livegate-snapshot", str(livegate),
        "--sqlite", f"cases/r4-packet/ledger.sqlite3={source}",
        "--packet-root", str(tmp_path / "hidden-packet"),
        "--frozen-utc", support.FROZEN_UTC,
    ])
    assert hidden.returncode == 1
    assert json.loads(hidden.stdout)["code"] == "HIDDEN_PATH"


# ---------------------------------------------------------------------------
# R4-02: unlisted sqlite sidecars / hidden / unknown files are rejected.
# ---------------------------------------------------------------------------
def test_r4_02_unlisted_sidecar_hidden_and_unknown_files_fail(tmp_path) -> None:
    packet, _ = support.build_packet(tmp_path)
    copy = support.copy_packet(packet, tmp_path / "copy")
    (copy / "cases" / "r4-packet" / "ledger.sqlite3-wal").write_bytes(b"")
    (copy / "cases" / "r4-packet" / "ledger.sqlite3-shm").write_bytes(b"")
    (copy / ".hidden-note.txt").write_text("hidden", encoding="utf-8")
    (copy / "cases" / "unknown.json").write_text("{}", encoding="utf-8")
    exit_code, document = support.verify_packet(copy)
    assert exit_code == 1
    codes = _issue_codes(document)
    assert "SQLITE_SIDECAR_PRESENT" in codes, codes
    assert "HIDDEN_PATH" in codes, codes
    assert "UNLISTED_PATH" in codes, codes
    paths = {issue.get("path") for issue in document["issues"]}
    assert "cases/unknown.json" in paths
    assert "cases/r4-packet/ledger.sqlite3-wal" in paths


# ---------------------------------------------------------------------------
# R4-03: delete / byte / mode / symlink / hardlink tampering is rejected.
# ---------------------------------------------------------------------------
def test_r4_03_delete_change_byte_mode_symlink_hardlink_fail(tmp_path) -> None:
    packet, _ = support.build_packet(tmp_path)

    deleted_copy = support.copy_packet(packet, tmp_path / "deleted")
    target = _payload_file(deleted_copy)
    relative = target.relative_to(deleted_copy).as_posix()
    target.unlink()
    exit_code, document = support.verify_packet(deleted_copy)
    assert exit_code == 1
    assert "MISSING_PATH" in _issue_codes(document)
    assert any(issue.get("path") == relative for issue in document["issues"])

    bytes_copy = support.copy_packet(packet, tmp_path / "bytes")
    target = _payload_file(bytes_copy)
    original = target.read_bytes()
    support.force_write(target, original + b"tamper")
    exit_code, document = support.verify_packet(bytes_copy)
    assert exit_code == 1
    assert "HASH_MISMATCH" in _issue_codes(document)

    mode_copy = support.copy_packet(packet, tmp_path / "mode")
    target = _payload_file(mode_copy)
    target.chmod(0o644)
    exit_code, document = support.verify_packet(mode_copy)
    assert exit_code == 1
    assert "MODE_MISMATCH" in _issue_codes(document)

    symlink_copy = support.copy_packet(packet, tmp_path / "symlink")
    target = _payload_file(symlink_copy)
    elsewhere = tmp_path / "elsewhere.bin"
    elsewhere.write_bytes(target.read_bytes())
    target.unlink()
    os.symlink(elsewhere, target)
    exit_code, document = support.verify_packet(symlink_copy)
    assert exit_code == 1
    assert "SYMLINK_PATH" in _issue_codes(document)

    hardlink_copy = support.copy_packet(packet, tmp_path / "hardlink")
    target = _payload_file(hardlink_copy)
    os.link(target, tmp_path / "external-hardlink.bin")
    try:
        exit_code, document = support.verify_packet(hardlink_copy)
        assert exit_code == 1
        assert "HARDLINK_ANOMALY" in _issue_codes(document)
    finally:
        (tmp_path / "external-hardlink.bin").unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# R4-04: manifest / hashes tampering is rejected (self-consistency is not a
# license to bypass the full-tree check).
# ---------------------------------------------------------------------------
def test_r4_04_manifest_and_hashes_tamper_fail(tmp_path) -> None:
    packet, _ = support.build_packet(tmp_path)

    manifest_copy = support.copy_packet(packet, tmp_path / "manifest-tamper")
    manifest = support.read_json(manifest_copy / MANIFEST)
    manifest["inventory"]["payload_count"] += 1
    support.force_write(manifest_copy / MANIFEST,
                        json.dumps(manifest, indent=2, sort_keys=True).encode() + b"\n")
    exit_code, document = support.verify_packet(manifest_copy)
    assert exit_code == 1
    codes = _issue_codes(document)
    assert "HASH_MISMATCH" in codes or "COUNT_MISMATCH" in codes, codes

    hashes_copy = support.copy_packet(packet, tmp_path / "hashes-tamper")
    hashes_path = hashes_copy / HASHES
    lines = hashes_path.read_text(encoding="utf-8").splitlines()
    victim = next(index for index, line in enumerate(lines)
                  if not line.endswith(MANIFEST))
    digest, _, relative = lines[victim].partition("  ")
    lines[victim] = f"{'0' * 64}  {relative}"
    support.force_write(hashes_path, ("\n".join(lines) + "\n").encode())
    exit_code, document = support.verify_packet(hashes_copy)
    assert exit_code == 1
    assert "HASH_MISMATCH" in _issue_codes(document)

    missing_copy = support.copy_packet(packet, tmp_path / "hashes-missing-line")
    hashes_path = missing_copy / HASHES
    lines = hashes_path.read_text(encoding="utf-8").splitlines()
    support.force_write(hashes_path, ("\n".join(lines[:-1]) + "\n").encode())
    exit_code, document = support.verify_packet(missing_copy)
    assert exit_code == 1
    codes = _issue_codes(document)
    assert "HASHES_ENTRY_MISSING" in codes or "COUNT_MISMATCH" in codes, codes

    extra_copy = support.copy_packet(packet, tmp_path / "hashes-extra-line")
    hashes_path = extra_copy / HASHES
    lines = hashes_path.read_text(encoding="utf-8").splitlines()
    lines.append(f"{'0' * 64}  cases/forged.json")
    support.force_write(hashes_path, ("\n".join(sorted(lines)) + "\n").encode())
    exit_code, document = support.verify_packet(extra_copy)
    assert exit_code == 1
    assert "MISSING_PATH" in _issue_codes(document)

    metadata_copy = support.copy_packet(packet, tmp_path / "hashes-covers-metadata")
    hashes_path = metadata_copy / HASHES
    lines = hashes_path.read_text(encoding="utf-8").splitlines()
    lines.append(f"{'0' * 64}  {REPORT}")
    support.force_write(hashes_path, ("\n".join(sorted(lines)) + "\n").encode())
    exit_code, document = support.verify_packet(metadata_copy)
    assert exit_code == 1
    assert "HASHES_ENTRY_EXTRA" in _issue_codes(document)


# ---------------------------------------------------------------------------
# R4-05: SQLite snapshots are consistent and read-only copies cannot silently
# gain sidecars without verification failing.
# ---------------------------------------------------------------------------
def test_r4_05_sqlite_snapshot_consistent_and_read_sidecars_detected(tmp_path) -> None:
    source = tmp_path / "source-refusal.sqlite3"
    support.make_sqlite_source(source)
    # Uncommitted work in a second connection must never leak into the snapshot.
    uncommitted = sqlite3.connect(str(source))
    try:
        uncommitted.execute("BEGIN")
        uncommitted.execute("INSERT INTO reservations VALUES ('r-2', '0.000001')")
        packet, build_summary = support.build_packet(
            tmp_path, sqlite_source=source)
        snapshot_relative = "cases/r4-packet/ledger.sqlite3"
        assert snapshot_relative in build_summary["sqlite_snapshots"]
        snapshot = packet / snapshot_relative
        assert snapshot.is_file()
        assert not (packet / (snapshot_relative + "-wal")).exists()
        assert not (packet / (snapshot_relative + "-shm")).exists()
        connection = sqlite3.connect(f"file:{snapshot}?mode=ro&immutable=1", uri=True)
        try:
            rows = connection.execute(
                "SELECT id, cost FROM reservations ORDER BY id").fetchall()
        finally:
            connection.close()
        assert rows == [("r-1", "0.002684")]
        assert support.verify_packet(packet)[0] == 0
    finally:
        uncommitted.rollback()
        uncommitted.close()

    # A plain (non-immutable) read that creates sidecars must be visible to the
    # verifier; verification itself must never open SQLite / create sidecars.
    copy = support.copy_packet(packet, tmp_path / "sqlite-read-copy")
    reader = sqlite3.connect(str(copy / snapshot_relative))
    try:
        reader.execute("PRAGMA journal_mode=WAL")
        reader.execute("SELECT COUNT(*) FROM reservations").fetchone()
        sidecars = [path.name for path in copy.rglob("*-wal")] + \
            [path.name for path in copy.rglob("*-shm")]
        assert sidecars, "expected sqlite read to create sidecars for the probe"
        exit_code, document = support.verify_packet(copy)
        assert exit_code == 1
        codes = _issue_codes(document)
        assert "SQLITE_SIDECAR_PRESENT" in codes or "UNLISTED_PATH" in codes, codes
    finally:
        reader.close()
    before = sorted(support.walk_files(packet))
    assert support.verify_packet(packet)[0] == 0
    assert sorted(support.walk_files(packet)) == before


# ---------------------------------------------------------------------------
# R4-06: an independent traversal (not importing the owner verifier) recomputes
# the same set/hash/tree, and the builder refuses sidecar/db sources.
# ---------------------------------------------------------------------------
def test_r4_06_independent_traversal_and_source_guards(tmp_path) -> None:
    packet, _ = support.build_packet(tmp_path)
    manifest = support.read_json(packet / MANIFEST)
    files = support.walk_files(packet)
    payload = set(files) - EXCEPTIONS
    assert set(manifest["inventory"]["file_modes"]) == payload | {MANIFEST}
    assert manifest["inventory"]["payload_tree_sha256"] == support.payload_tree(
        files, EXCEPTIONS)
    hashes = {}
    for line in (packet / HASHES).read_text(encoding="utf-8").splitlines():
        digest, _, relative = line.partition("  ")
        hashes[relative] = digest
    for relative in payload | {MANIFEST}:
        assert hashlib.sha256((packet / relative).read_bytes()).hexdigest() == \
            hashes[relative]
    # A source that is itself a sidecar/symlink cannot become a snapshot.
    sidecar = tmp_path / "source.sqlite3-wal"
    sidecar.write_bytes(b"")
    metadata = tmp_path / "metadata.json"
    livegate = tmp_path / "livegate.json"
    support.write_json(metadata, support.metadata_document())
    support.write_json(livegate, support.livegate_document())
    staging = support.staging_tree(tmp_path / "staging-2")
    refused = support.run([
        sys.executable, str(support.BUILDER),
        "--impl-sha", support.IMPL_SHA, "--staging", str(staging),
        "--metadata", str(metadata), "--livegate-snapshot", str(livegate),
        "--sqlite", f"cases/r4-packet/ledger.sqlite3={sidecar}",
        "--packet-root", str(tmp_path / "refused-packet"),
        "--frozen-utc", support.FROZEN_UTC,
    ])
    assert refused.returncode == 1
    assert json.loads(refused.stdout)["code"] == "SQLITE_SOURCE_INVALID"
    assert not (tmp_path / "refused-packet").exists()


# ---------------------------------------------------------------------------
# Evidence-consistency helper (R4-12/R4-13 prep): LiveGate reasons cross-ref.
# ---------------------------------------------------------------------------
def test_livegate_snapshot_crossref_mismatch_fails(tmp_path) -> None:
    packet, _ = support.build_packet(tmp_path)
    assert support.verify_packet(packet)[0] == 0

    ref_copy = support.copy_packet(packet, tmp_path / "xref-tamper")
    document = support.read_json(ref_copy / "review" / "livegate.json")
    document["snapshot_ref"] = "review/not-the-snapshot.json"
    support.force_write(ref_copy / "review" / "livegate.json",
                        json.dumps(document, sort_keys=True).encode() + b"\n")
    exit_code, result = support.verify_packet(ref_copy)
    assert exit_code == 1
    assert "LIVEGATE_CROSSREF_MISMATCH" in _issue_codes(result)

    # The manifest never hardcodes the reason count: it must equal the single
    # snapshot's actual reason list, element-wise via the shared digest.
    snapshot_copy = support.copy_packet(packet, tmp_path / "snapshot-tamper")
    snapshot = support.read_json(snapshot_copy / "identity" / "livegate.json")
    snapshot["reasons"] = list(snapshot["reasons"]) + ["EXTRA_REASON"]
    support.force_write(snapshot_copy / "identity" / "livegate.json",
                        json.dumps(snapshot, sort_keys=True, indent=2).encode() + b"\n")
    exit_code, result = support.verify_packet(snapshot_copy)
    assert exit_code == 1
    codes = _issue_codes(result)
    assert "LIVEGATE_CROSSREF_MISMATCH" in codes, codes


def test_v1_packet_is_untouched_by_v2_build(tmp_path) -> None:
    if not support.V1_PACKET.is_dir():
        pytest.skip("v1 packet is not present on this host")
    hashes_before = hashlib.sha256(
        (support.V1_PACKET / "hashes.sha256").read_bytes()).hexdigest()
    support.build_packet(tmp_path)
    hashes_after = hashlib.sha256(
        (support.V1_PACKET / "hashes.sha256").read_bytes()).hexdigest()
    assert hashes_after == hashes_before
