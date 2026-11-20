"""Shared fixtures/helpers for A-NEXT hygiene tests.

All tests operate on temporary directories and synthetic trees only.  They must
never read or modify the real frozen rootfs, Packet v1/v2 or repository evidence.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

WORKTREE = Path(__file__).resolve().parents[2]
SCRIPTS = WORKTREE / "scripts" / "a_next"
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


def canonical_sha(path: Path) -> str:
    proc = subprocess.run([*TAR_ARGV, str(path), "."], stdout=subprocess.PIPE, check=True)
    return hashlib.sha256(proc.stdout).hexdigest()


def run_script(
    script: str,
    *args: object,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / script), *[str(arg) for arg in args]],
        capture_output=True,
        text=True,
        cwd=str(cwd or WORKTREE),
        env=env,
    )


def output_json(proc: subprocess.CompletedProcess) -> dict:
    import json

    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:  # pragma: no cover - helper diagnostics
        raise AssertionError(f"not JSON: stdout={proc.stdout!r} stderr={proc.stderr!r}") from exc


def make_tree(root: Path, files: dict[str, str]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for relative, content in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    return root


def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )


def commit(repo: Path, message: str) -> str:
    git(repo, "add", "-A")
    git(
        repo,
        "-c",
        "user.name=a-next-test",
        "-c",
        "user.email=a-next-test@invalid",
        "commit",
        "-m",
        message,
    )
    return git(repo, "rev-parse", "HEAD").stdout.strip()


@pytest.fixture()
def frozen_tree(tmp_path: Path) -> tuple[Path, str]:
    """Synthetic frozen rootfs; returns (path, canonical sha)."""
    tree = make_tree(tmp_path / "frozen", {"etc/a.txt": "alpha\n", "usr/b.txt": "beta\n"})
    return tree, canonical_sha(tree)


@pytest.fixture()
def working_tree(tmp_path: Path) -> Path:
    return make_tree(tmp_path / "work-rootfs", {"etc/a.txt": "alpha\n"})


@pytest.fixture()
def git_repo(tmp_path: Path) -> dict:
    """Small repository with ``main`` branch and one base commit."""
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    make_tree(repo, {"README.md": "base\n"})
    base = commit(repo, "base")
    return {"repo": repo, "base": base}


@pytest.fixture(autouse=True)
def _no_real_env_leak() -> None:
    """Ensure tests never inherit a real provider key into subprocess probes."""
    for name in list(os.environ):
        if any(part in name.upper() for part in ("API_KEY", "TOKEN", "SECRET")):
            os.environ.pop(name, None)
    yield
