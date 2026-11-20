"""Shared helpers for A-NEXT hygiene tests.

Helpers live in a uniquely named module (not ``conftest``) so that collecting
multiple new suites in one ``pytest tests`` run cannot shadow each other.
All tests operate on temporary directories and synthetic trees only.
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

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
