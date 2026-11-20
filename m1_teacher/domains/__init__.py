"""Learning-domain adapters for the M1-A teacher core."""

from __future__ import annotations

from .cf_binary_search import (
    CFBinarySearchDomainAdapter,
    build_default_registry,
    default_fixtures_root,
)

__all__ = [
    "CFBinarySearchDomainAdapter",
    "build_default_registry",
    "default_fixtures_root",
]
