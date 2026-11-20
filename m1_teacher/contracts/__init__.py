"""Public contract surface of the M1-A teacher core (schema ``m1a.v0``)."""

from __future__ import annotations

from .domain import DomainAdapter, DomainRegistry
from .errors import (
    ConflictError,
    M1AError,
    NotFoundError,
    UnsupportedOperationError,
    ValidationError,
)
from .repository import LearnerRepository, SessionRepository
from .types import *  # noqa: F401,F403 - re-export frozen records/enums
from .types import __all__ as _types_all

__all__ = [
    "M1AError",
    "ValidationError",
    "NotFoundError",
    "ConflictError",
    "UnsupportedOperationError",
    "DomainAdapter",
    "DomainRegistry",
    "LearnerRepository",
    "SessionRepository",
    *_types_all,
]
