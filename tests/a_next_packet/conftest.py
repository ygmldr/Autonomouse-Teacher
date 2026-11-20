"""Shared helpers for A-NEXT packet v3 tests (synthetic trees only).

Tests never touch the real frozen rootfs, the real Packet v1/v2 bytes or any
repository evidence.  All packets are built from temporary synthetic payloads.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

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


@pytest.fixture()
def staging(tmp_path: Path) -> Path:
    return make_tree(
        tmp_path / "staging",
        {
            "README.txt": "packet payload\n",
            "cases/r1/index.json": '{"case":"r1"}\n',
            "review/summary.md": "summary\n",
        },
    )


@pytest.fixture()
def frozen_rootfs(tmp_path: Path) -> Path:
    return make_tree(tmp_path / "frozen-rootfs", {"etc/os-release": "ID=test\n"})


@pytest.fixture()
def built_packet(tmp_path: Path, staging: Path, frozen_rootfs: Path) -> dict:
    """Build a final-phase synthetic packet and return paths/identity."""
    expected = canonical_sha(frozen_rootfs)
    impl = IMPL
    out = tmp_path / "artifacts" / f"review-packet-a-next-v3-{impl}"
    proc = run_script(
        "build_packet_v3.py",
        "--staging-dir",
        staging,
        "--impl-sha",
        impl,
        "--no-git-check",
        "--out-dir",
        out,
        "--frozen-rootfs",
        frozen_rootfs,
        "--expected-rootfs-sha",
        expected,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    summary = output_json(proc)
    return {
        "packet": out,
        "staging": staging,
        "frozen": frozen_rootfs,
        "frozen_sha": expected,
        "impl": impl,
        "summary": summary,
        "manifest": __import__("json").loads((out / "manifest.json").read_text()),
    }


def write_mutated_packet(packet: Path, target: Path) -> Path:
    copy_packet(packet, target)
    return target


def mutate_file(path: Path, writer) -> None:
    os.chmod(path, 0o644)
    writer(path)
    os.chmod(path, 0o444)


@pytest.fixture(autouse=True)
def _no_real_env_leak() -> None:
    for name in list(os.environ):
        if any(part in name.upper() for part in ("API_KEY", "TOKEN", "SECRET")):
            os.environ.pop(name, None)
    yield
