"""Diagnostic-engine package of the M1-A teacher core (B3).

Public surface: :class:`DiagnosticEngine` (select the next diagnostic
assessment item with a structured :class:`~m1_teacher.contracts.types.Reason`)
and :class:`DiagnosticPolicy` (deterministic, injectable thresholds).
"""

from __future__ import annotations

from .engine import (
    INSUFFICIENT_EVIDENCE,
    POLICY_VERSION,
    READY,
    DiagnosticEngine,
    DiagnosticPolicy,
)

__all__ = [
    "DiagnosticEngine",
    "DiagnosticPolicy",
    "POLICY_VERSION",
    "READY",
    "INSUFFICIENT_EVIDENCE",
]
