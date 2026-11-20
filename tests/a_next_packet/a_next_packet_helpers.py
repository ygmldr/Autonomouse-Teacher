"""Shared helpers for A-NEXT packet v3 tests (synthetic trees only).

Unique module name (not ``conftest``) so a combined ``pytest tests`` collection
cannot import another suite's conftest helpers by accident.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

WORKTREE = Path(__file__).resolve().parents[2]
SCRIPTS = WORKTREE / "scripts" / "a_next"
IMPL = "a" * 40
TAR_ARGV = [
    "tar",
    "--sort=name",
    "--mtime=@0",
    "--owner=0",
    "--group=0",
    "--numeric-owner",
    "-cf",
    "-",
    "-C",
]


def run_script(script: str, *args: object) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / script), *[str(arg) for arg in args]],
        capture_output=True,
        text=True,
        cwd=str(WORKTREE),
    )


def output_json(proc: subprocess.CompletedProcess) -> dict:
    import json

    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:  # pragma: no cover
        raise AssertionError(f"not JSON: {proc.stdout!r} {proc.stderr!r}") from exc


def make_tree(root: Path, files: dict[str, str]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for relative, content in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    return root


def canonical_sha(path: Path) -> str:
    proc = subprocess.run([*TAR_ARGV, str(path), "."], stdout=subprocess.PIPE, check=True)
    return hashlib.sha256(proc.stdout).hexdigest()


def make_readonly(packet: Path) -> None:
    for root, _dirs, files in os.walk(packet):
        os.chmod(root, 0o755)
        for name in files:
            os.chmod(os.path.join(root, name), 0o444)


def make_writable(packet: Path) -> None:
    for root, dirs, files in os.walk(packet):
        os.chmod(root, 0o755)
        for name in dirs:
            os.chmod(os.path.join(root, name), 0o755)
        for name in files:
            os.chmod(os.path.join(root, name), 0o644)


def copy_packet(source: Path, target: Path) -> Path:
    shutil.copytree(source, target)
    make_writable(target)
    return target


def normalize_modes(packet: Path) -> None:
    """Restore canonical packet modes after a mutation that had to write."""
    dirs: list[Path] = [packet]
    files: list[Path] = []
    for root, subdirs, names in os.walk(packet):
        dirs.extend(Path(root) / name for name in subdirs)
        files.extend(Path(root) / name for name in names)
    for directory in dirs:
        os.chmod(directory, 0o755)
    for file_path in files:
        os.chmod(file_path, 0o444)
    for directory in sorted(dirs, key=lambda p: -len(p.parts)):
        os.chmod(directory, 0o555)


def write_mutated_packet(packet: Path, target: Path) -> Path:
    copy_packet(packet, target)
    return target


def mutate_file(path: Path, writer) -> None:
    os.chmod(path, 0o644)
    writer(path)
    os.chmod(path, 0o444)
