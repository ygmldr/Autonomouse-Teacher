#!/usr/bin/env python3
"""Independent reviewer check of the frozen G4-F packet v1 and rebuilt packet v2.

Read-only. Recomputes, from actual bytes:
  * file / symlink counts;
  * every ``hashes.sha256`` entry (payload + manifest);
  * payload tree sha256 via the documented build method
    (sha256 over sorted "<sha256>  <relpath>\\n" lines for the 172 hashed
    payload files, excluding manifest.json);
  * v1 sidecar drift (2 post-build SQLite ``-shm``/``-wal`` files) and tree
    with / without those sidecars;
  * v2 sidecar count (expect 0) and manifest tree agreement.

Usage:
  PYTHONPATH=src python scripts/g4h0-review/verify_packet_integrity.py
No network, no writes; exit 0 only if every expected invariant holds.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

V1 = Path("/root/Autonomous Teacher/artifacts/review-packet-g4f-e7d92967ec0ece80de4a1a3705f637e8eb9bde99")
V2 = Path("/root/Autonomous Teacher/worktrees/m0-g4h0/artifacts/g4h0/packet-v2")
MANIFEST = "manifest.json"
HASHES = "hashes.sha256"
REPORT = "packet-integrity-report.txt"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def payload_tree(root: Path, entries: list[tuple[str, str]]) -> str:
    lines = sorted(f"{digest}  {relative}\n"
                   for digest, relative in entries if relative != MANIFEST)
    return hashlib.sha256("".join(lines).encode("utf-8")).hexdigest()


def hashed_entries(root: Path) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for line in (root / HASHES).read_text(encoding="utf-8").splitlines():
        if line.strip():
            digest, relative = line.split("  ", 1)
            rows.append((digest, relative))
    return rows


def check(label: str, root: Path, expected_sidecars: list[str]) -> list[str]:
    problems: list[str] = []
    entries = hashed_entries(root)
    hashed_files = [relative for _, relative in entries]
    mismatched = [relative for digest, relative in entries
                  if not (root / relative).is_file()
                  or (root / relative).is_symlink()
                  or sha256_file(root / relative) != digest]
    manifest = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    manifest_tree = manifest["files"]["payload_tree_sha256"]
    manifest_count = manifest["files"]["count"]
    tree = payload_tree(root, entries)
    files = sorted(p.relative_to(root).as_posix() for p in root.rglob("*")
                   if p.is_file() and not p.is_symlink())
    symlinks = [p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_symlink()]
    sidecars = sorted(f for f in files if f.endswith(("-shm", "-wal", "-journal")))
    unhashed = sorted(set(files) - set(hashed_files) - {HASHES, REPORT})
    payload_hashed = [f for f in hashed_files if f != MANIFEST]

    print(f"[{label}] root={root}")
    print(f"  exists={root.exists()} files={len(files)} symlinks={len(symlinks)} "
          f"sidecars={sidecars} unhashed_beyond_hashes_report={unhashed}")
    print(f"  hashes_entries={len(entries)} payload_hashed={len(payload_hashed)} "
          f"manifest_files_count={manifest_count}")
    print(f"  recomputed_payload_tree={tree}")
    print(f"  manifest_payload_tree  ={manifest_tree} match={tree == manifest_tree}")
    print(f"  per-file hash mismatches={mismatched}")

    if root.exists() is False:
        problems.append(f"{label}: packet missing")
    if mismatched:
        problems.append(f"{label}: {len(mismatched)} hash mismatches")
    if tree != manifest_tree:
        problems.append(f"{label}: payload tree mismatch")
    if len(payload_hashed) != manifest_count:
        problems.append(f"{label}: payload hash count != manifest count")
    if len(entries) != manifest_count + 1:
        problems.append(f"{label}: hashes lines != payload+manifest")
    if sidecars != sorted(expected_sidecars):
        problems.append(f"{label}: sidecars {sidecars} != expected {sorted(expected_sidecars)}")
    if label == "v1":
        # The 2 post-build sidecars are the only un-hashed payload files and the
        # only reason the current full tree drifts from the frozen manifest.
        if unhashed != sorted(expected_sidecars):
            problems.append(f"v1: unhashed files unexpected: {unhashed}")
        tree_excl = payload_tree(
            root, [(d, r) for d, r in entries if r not in expected_sidecars])
        print(f"  v1_tree_excluding_2_sidecars={tree_excl} match={tree_excl == manifest_tree}")
        if tree_excl != manifest_tree:
            problems.append("v1: tree excluding sidecars != manifest tree")
    else:
        if sidecars:
            problems.append("v2: expected 0 sidecars")
        if unhashed:
            problems.append(f"v2: unexpected unhashed files {unhashed}")
    return problems


def main() -> int:
    problems = check("v1", V1, ["f4/sqlite-readonly/resume-attempts.sqlite3-shm",
                                "f4/sqlite-readonly/resume-attempts.sqlite3-wal"])
    problems += check("v2", V2, [])
    print()
    if problems:
        print("FAIL:")
        for problem in problems:
            print("  -", problem)
        return 1
    print("PACKET INTEGRITY OK: v1 immutable+sidecar drift documented, "
          "v2 manifest tree agrees and has 0 sidecars")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
