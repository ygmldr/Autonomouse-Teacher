"""Shared TEST_ONLY helpers for the G4-R packet v2 builder/verifier tests.

Everything is synthetic: a temporary staging tree, a tiny SQLite database and a
synthetic LiveGate snapshot. No key, provider, network or container is used.
Build/verify are invoked as subprocesses exactly as a reviewer would invoke them.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
BUILDER = REPO_ROOT / "scripts" / "g4r" / "build_packet_g4r.py"
VERIFIER = REPO_ROOT / "scripts" / "g4r" / "verify_packet_g4r.py"
V1_PACKET = (Path("/root/Autonomous Teacher/artifacts")
             / "review-packet-g4f-e7d92967ec0ece80de4a1a3705f637e8eb9bde99")
IMPL_SHA = "a" * 64
FROZEN_UTC = "2026-11-20T00:00:00Z"
GIT_HEAD = "3e7afee0" + "0" * 56  # TEST_ONLY 64-hex stand-in for the frozen base commit
LIVEGATE_REASONS = [
    "EXTERNAL_HUMAN_AUTHORIZATION_BOUNDARY_NOT_DEPLOYED",
    "EXTERNAL_CREDENTIAL_BROKER_NOT_DEPLOYED",
    "LIVE_GATE_CLOSED",
]


def clean_env() -> dict[str, str]:
    return {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": "/tmp",
        "LANG": "C",
        "PYTHONDONTWRITEBYTECODE": "1",
        "NO_COLOR": "1",
    }


def run(argv: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(argv, capture_output=True, text=True, timeout=180,
                          env=clean_env(), cwd="/tmp")


def write_json(path: Path, document: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def metadata_document() -> dict:
    return {
        "impl_sha": IMPL_SHA,
        "base_sha": GIT_HEAD,
        "parent_sha": GIT_HEAD,
        "code_sha": "b" * 64,
        "docs_sha": "c" * 64,
        "build_sha": "d" * 64,
        "stage": {"manifest_sha256": "e" * 64, "tree_sha256": "f" * 64,
                  "base_sha": GIT_HEAD},
        "rootfs_sha256": "1" * 64,
        "deps_sha256": "2" * 64,
        "runtime": {"name": "deepseek-harness-sdk", "version": "0.2.2rc2",
                    "sha256": "3" * 64},
        "environment": {"python": "3.11.15", "podman": "4.9.3", "node": "v22.23.2"},
        "tests": {"summary": {"total": 1, "pass": 1, "unverified": 0,
                              "not_run": 0, "blocked": 0}},
        "status": "PENDING_INDEPENDENT_REVIEW",
        "external_network_calls": 0,
        "live_gate": "BLOCKED",
        "limitations": ["TEST_ONLY synthetic packet; no key/provider/network"],
    }


def livegate_document() -> dict:
    return {
        "schema": "m0.g4r.livegate-snapshot/v1",
        "inspect_utc": FROZEN_UTC,
        "live_gate": "BLOCKED",
        "reasons": list(LIVEGATE_REASONS),
    }


def make_sqlite_source(path: Path) -> None:
    """Committed WAL database with one deterministic row."""
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path))
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("CREATE TABLE reservations (id TEXT PRIMARY KEY, cost TEXT)")
        connection.execute("INSERT INTO reservations VALUES ('r-1', '0.002684')")
        connection.commit()
    finally:
        connection.close()


def staging_tree(root: Path) -> Path:
    staging = root / "staging"
    write_json(staging / "identity" / "git.json",
               {"head": GIT_HEAD, "clean": True, "synthetic": True})
    write_json(staging / "identity" / "stage.json",
               {"manifest_sha256": "e" * 64, "base_sha": GIT_HEAD})
    write_json(staging / "identity" / "runtime.json",
               {"name": "deepseek-harness-sdk", "version": "0.2.2rc2",
                "sha256": "3" * 64})
    write_json(staging / "env" / "zero-key.json",
               {"schema": "m0.g4r.env-zero-key/v1", "key_present": False,
                "snapshot_ref": "identity/livegate.json"})
    write_json(staging / "review" / "livegate.json",
               {"schema": "m0.g4r.review-livegate/v1", "status": "BLOCKED",
                "snapshot_ref": "identity/livegate.json"})
    write_json(staging / "cases" / "r4-packet" / "full-inventory.json",
               {"schema": "m0.g4r.case/v1", "case": "R4-01", "status": "NOT_RUN"})
    write_json(staging / "regressions" / "ruff" / "report.json",
               {"schema": "m0.g4r.ruff/v1", "findings": 0})
    (staging / "matrix").mkdir(parents=True, exist_ok=True)
    (staging / "matrix" / "G4R_Test_Evidence_Matrix.csv").write_text(
        "case_id,phase,status\nR4-01,R4,NOT_RUN\n", encoding="utf-8")
    (staging / "review").mkdir(parents=True, exist_ok=True)
    (staging / "review" / "request.md").write_text(
        "# Packet v2 review request (TEST_ONLY)\n", encoding="utf-8")
    (staging / "README.md").write_text(
        "# G4-R review packet v2 (TEST_ONLY synthetic)\n", encoding="utf-8")
    return staging


def build_packet(tmp_path: Path, *, packet_name: str = "review-packet-g4r-v2-test",
                 staging: Path | None = None,
                 metadata: dict | None = None,
                 livegate: dict | None = None,
                 sqlite_source: Path | None = None,
                 extra_args: list[str] | None = None) -> tuple[Path, dict]:
    root = tmp_path / packet_name
    staging = staging or staging_tree(tmp_path)
    metadata_path = tmp_path / "metadata.json"
    write_json(metadata_path, metadata or metadata_document())
    livegate_path = tmp_path / "livegate.json"
    write_json(livegate_path, livegate or livegate_document())
    sqlite_path = sqlite_source or (tmp_path / "source.sqlite3")
    if sqlite_source is None:
        make_sqlite_source(sqlite_path)
    argv = [
        sys.executable, str(BUILDER),
        "--impl-sha", IMPL_SHA,
        "--staging", str(staging),
        "--metadata", str(metadata_path),
        "--livegate-snapshot", str(livegate_path),
        "--sqlite", f"cases/r4-packet/ledger.sqlite3={sqlite_path}",
        "--packet-root", str(root),
        "--frozen-utc", FROZEN_UTC,
        "--git-head", GIT_HEAD,
    ]
    argv.extend(extra_args or [])
    completed = run(argv)
    assert completed.returncode == 0, (completed.stdout, completed.stderr)
    return root, json.loads(completed.stdout)


def verify_packet(packet_root: Path, *, expected_impl_sha: str | None = IMPL_SHA
                  ) -> tuple[int, dict]:
    argv = [sys.executable, str(VERIFIER), "--packet-root", str(packet_root)]
    if expected_impl_sha is not None:
        argv.extend(["--expected-impl-sha", expected_impl_sha])
    completed = run(argv)
    payload = json.loads(completed.stdout) if completed.stdout.strip() else {}
    return completed.returncode, payload


def copy_packet(source: Path, destination: Path) -> Path:
    shutil.copytree(source, destination)
    return destination


def force_write(path: Path, data: bytes) -> None:
    path.chmod(0o644)
    path.write_bytes(data)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def walk_files(root: Path) -> dict[str, dict]:
    """Independent TEST_ONLY traversal used by R4-06 recomputation tests."""
    import hashlib
    import stat as stat_module

    files: dict[str, dict] = {}
    stack = [("", root)]
    while stack:
        prefix, directory = stack.pop()
        for entry in sorted(os.scandir(directory), key=lambda item: item.name):
            relative = f"{prefix}{entry.name}"
            info = entry.stat(follow_symlinks=False)
            if stat_module.S_ISDIR(info.st_mode):
                stack.append((relative + "/", Path(entry.path)))
            else:
                digest = hashlib.sha256(Path(entry.path).read_bytes()).hexdigest()
                files[relative] = {"sha256": digest, "mode": info.st_mode & 0o777,
                                   "size": info.st_size}
    return files


def payload_tree(files: dict[str, dict], exceptions: set[str]) -> str:
    import hashlib

    entries = [[relative, record["sha256"]] for relative, record in files.items()
               if relative not in exceptions]
    entries.sort(key=lambda item: item[0])
    canonical = json.dumps(entries, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()
