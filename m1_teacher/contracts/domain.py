"""Domain adapter contract and registry for the frozen M1-A teacher (``m1a.v0``).

The teacher core is domain-agnostic: it only ever talks to a
:class:`DomainAdapter`.  Concrete domains (starting with
``cf_binary_search``) provide knowledge graphs, objectives, teacher-visible
assessment items and teaching content through this Protocol.

A domain adapter deliberately has **no grading or answer capability**.
Hidden evaluation material is owned by the independent assessment scorer
(added in a later PR) and is not reachable through this contract.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .errors import ConflictError, NotFoundError, ValidationError
from .types import AssessmentItem, KnowledgeNode, LearningObjective, PrerequisiteEdge

__all__ = ["DomainAdapter", "DomainRegistry"]


@runtime_checkable
class DomainAdapter(Protocol):
    """Structural contract implemented by every learning domain.

    Implementations must be deterministic, offline and side-effect free for
    the read methods below.  ``validate()`` checks cross-file consistency and
    must raise :class:`~m1_teacher.contracts.errors.ValidationError` on
    invalid domain data.
    """

    domain_id: str
    domain_version: str

    def knowledge_nodes(self) -> list[KnowledgeNode]:
        """All nodes of the domain knowledge graph (stable order)."""

    def prerequisite_edges(self) -> list[PrerequisiteEdge]:
        """All prerequisite edges of the domain knowledge graph (stable order)."""

    def objectives(self) -> list[LearningObjective]:
        """All learning objectives declared by the domain (stable order)."""

    def assessment_items(self, node_id: str | None = None) -> list[AssessmentItem]:
        """Teacher-visible assessment items, optionally filtered by node id."""

    def teaching_content(self, node_id: str, kind: str) -> str:
        """Return teaching content for ``node_id`` of the requested ``kind``.

        Supported kinds are ``EXPLAIN``, ``HINT_L1``, ``HINT_L2``, ``HINT_L3``,
        ``REVIEW`` and ``PRACTICE`` (the latter returns the practice item ids as
        a deterministic JSON string).  Unknown kinds fail closed with
        ``ValidationError``.
        """

    def validate(self) -> None:
        """Validate the loaded domain data; raise ``ValidationError`` if invalid."""


class DomainRegistry:
    """In-memory registry of domain adapters keyed by ``domain_id``.

    The registry never exposes grading or answer functionality: it only stores
    :class:`DomainAdapter` implementations.
    """

    def __init__(self) -> None:
        self._adapters: dict[str, DomainAdapter] = {}

    def register(self, adapter: DomainAdapter) -> None:
        """Register a domain adapter; duplicate ``domain_id`` -> ``ConflictError``."""

        if not isinstance(adapter, DomainAdapter):
            raise ValidationError(
                "DomainRegistry.register() expects a DomainAdapter implementation"
            )
        domain_id = getattr(adapter, "domain_id", None)
        if type(domain_id) is not str or not domain_id:
            raise ValidationError("DomainAdapter.domain_id must be a non-empty string")
        domain_version = getattr(adapter, "domain_version", None)
        if type(domain_version) is not str or not domain_version:
            raise ValidationError("DomainAdapter.domain_version must be a non-empty string")
        if domain_id in self._adapters:
            raise ConflictError(f"domain_id {domain_id!r} is already registered")
        self._adapters[domain_id] = adapter

    def get(self, domain_id: str) -> DomainAdapter:
        """Return the adapter registered under ``domain_id`` or raise ``NotFoundError``."""

        if type(domain_id) is not str or not domain_id:
            raise ValidationError("DomainRegistry.get() expects a non-empty domain_id string")
        try:
            return self._adapters[domain_id]
        except KeyError:
            raise NotFoundError(f"domain_id {domain_id!r} is not registered") from None

    def list_domains(self) -> list[str]:
        """Registered domain ids in deterministic (sorted) order."""

        return sorted(self._adapters)

    def __len__(self) -> int:
        return len(self._adapters)

    def __contains__(self, domain_id: object) -> bool:
        return domain_id in self._adapters
