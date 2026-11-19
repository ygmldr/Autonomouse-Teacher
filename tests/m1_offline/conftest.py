"""Pytest bootstrap for the M1 Offline Teacher test package.

The M1 package lives at the worktree root (``m1_offline/``), while the root
``pyproject.toml`` only puts ``src`` on ``pythonpath``.  This conftest inserts
the worktree root into ``sys.path`` so ``import m1_offline`` works regardless
of how pytest is invoked (from the worktree root or elsewhere), and exposes a
few path fixtures shared by the M1 tests.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """Absolute path of the worktree root that contains ``m1_offline/``."""

    return REPO_ROOT


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    """Absolute path of ``fixtures/m1`` (synthetic fixtures; may be absent)."""

    return REPO_ROOT / "fixtures" / "m1"
