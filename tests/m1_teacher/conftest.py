"""Shared pytest fixtures for the M1-A teacher test suite.

Owned by ``B-PR1a`` (m1a-contracts). This conftest guarantees that the
repository root is importable as ``m1_teacher`` regardless of how pytest is
invoked (``python -m pytest`` already adds the CWD, but running a bare
``pytest`` binary does not) and exposes the stable fixture locations used by
both the contract tests and the B-PR1b fixture-validation tests.

The fixtures tree itself is authored by ``B-PR1b`` (m1a-fixtures) and lives at
``<repo>/fixtures/m1_teacher``.  It may be relocated with the environment
variable ``M1_TEACHER_FIXTURES`` (the production adapter honours the same
variable through :func:`m1_teacher.domains.build_default_registry`).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_DEFAULT_FIXTURES_DIR = REPO_ROOT / "fixtures" / "m1_teacher"
_ENV_FIXTURES_DIR = os.environ.get("M1_TEACHER_FIXTURES")
FIXTURES_DIR = (
    Path(_ENV_FIXTURES_DIR).expanduser().resolve()
    if _ENV_FIXTURES_DIR
    else _DEFAULT_FIXTURES_DIR
)


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """Absolute path of the worktree/repository root."""

    return REPO_ROOT


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    """Root of the M1-A fixtures tree (``fixtures/m1_teacher``)."""

    return FIXTURES_DIR


@pytest.fixture(scope="session")
def cf_domain_dir(fixtures_dir: Path) -> Path:
    """Fixture directory of the ``cf_binary_search`` domain adapter."""

    return fixtures_dir / "domains" / "cf_binary_search"


@pytest.fixture(scope="session")
def cf_domain_fixtures_available(cf_domain_dir: Path) -> bool:
    """True once B-PR1b has landed the CF domain fixture files."""

    return (cf_domain_dir / "knowledge_graph.json").is_file()
