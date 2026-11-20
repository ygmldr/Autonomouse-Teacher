"""Fixtures for A-NEXT hygiene tests.

Helper functions live in ``a_next_hygiene_helpers`` (unique module name) so a
combined ``pytest tests`` collection cannot confuse this suite's conftest with
another suite's conftest.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from a_next_hygiene_helpers import canonical_sha, commit, git, make_tree


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
