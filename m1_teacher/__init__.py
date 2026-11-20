"""M1-A offline teacher core (frozen public contract version ``m1a.v0``).

This package is self-contained and offline by design: it never imports the
M0 package, never opens a network connection, never reads API
keys/provider configuration and never invokes a LiveGate.  It exposes the
frozen domain contracts, the validated knowledge graph, the domain registry
and the CF binary-search domain adapter that later PRs build upon.
"""

from __future__ import annotations

from .contracts import *  # noqa: F401,F403 - re-export the frozen contract surface
from .contracts import __all__ as _contracts_all
from .domains import (
    CFBinarySearchDomainAdapter as CFBinarySearchDomainAdapter,
    build_default_registry as build_default_registry,
    default_fixtures_root as default_fixtures_root,
)
from .knowledge import KnowledgeGraph as KnowledgeGraph

CONTRACT_VERSION = "m1a.v0"
"""Frozen public contract version implemented by this package."""

__all__ = list(
    dict.fromkeys(
        [
            "CONTRACT_VERSION",
            *_contracts_all,
            "KnowledgeGraph",
            "CFBinarySearchDomainAdapter",
            "build_default_registry",
            "default_fixtures_root",
        ]
    )
)
