"""Append-only-ish, deletable learning memory (M1 Teacher Core).

:class:`LearningMemory` stores :class:`~m1_offline.types.TraceEvent` records for
replay and audit:

* ``append`` preserves the exact order of events (the loop trace order).
* ``replay(loop_id)`` returns that loop's events in append order; replay is the
  only way consumers should reconstruct a loop, never ad-hoc filtering.
* ``to_jsonl`` / ``from_jsonl`` round-trip losslessly (one JSON object per
  line); the loader is strict and fails closed on malformed lines.
* ``delete(learner_id)`` removes every event belonging to that learner (facts
  *and* inferences) and returns the number of removed events -- a synthetic
  right-to-be-forgotten primitive.

Facts vs inferences are kept distinguishable through the event payload: a
well-formed payload carries ``kind`` (``"FACT"`` or ``"INFERENCE"``) and
``source`` (where the event came from, e.g. ``"synthetic-fixture"``,
``"learner_model"``).  Memory does not rewrite payloads: it stores exactly what
the producer wrote, so a replay consumer can re-check provenance.  ``append``
does not require those keys (some loop events are structural), but when a
payload *does* declare ``kind`` it must be one of the known kinds.
"""

from __future__ import annotations

import json
from pathlib import Path

from .types import TraceEvent

__all__ = ["LearningMemory", "TRACE_EVENT_KINDS"]

#: Allowed payload ``kind`` values when a payload declares one.
TRACE_EVENT_KINDS = frozenset({"FACT", "INFERENCE", "ACTION", "OBSERVATION", "ERROR"})


def _learner_ids_in(event: TraceEvent) -> set[str]:
    payload = event.payload
    found: set[str] = set()
    single = payload.get("learner_id")
    if isinstance(single, str):
        found.add(single)
    many = payload.get("learner_ids")
    if isinstance(many, list):
        found.update(item for item in many if isinstance(item, str))
    nested = payload.get("learner")
    if isinstance(nested, dict) and isinstance(nested.get("learner_id"), str):
        found.add(nested["learner_id"])
    return found


class LearningMemory:
    """In-memory trace store with JSONL persistence and learner-scoped deletion."""

    def __init__(self) -> None:
        self._events: list[TraceEvent] = []

    # -- basic collection protocol ----------------------------------------
    def __len__(self) -> int:
        return len(self._events)

    def events(self) -> list[TraceEvent]:
        """Return a shallow copy of all stored events in append order."""

        return list(self._events)

    def loop_ids(self) -> list[str]:
        """Distinct loop ids in first-seen order."""

        seen: list[str] = []
        for event in self._events:
            if event.loop_id not in seen:
                seen.append(event.loop_id)
        return seen

    # -- contract API ------------------------------------------------------
    def append(self, event: TraceEvent) -> None:
        if not isinstance(event, TraceEvent):
            raise TypeError(f"append expects TraceEvent, got {type(event).__name__}")
        kind = event.payload.get("kind")
        if kind is not None:
            if not isinstance(kind, str) or kind not in TRACE_EVENT_KINDS:
                raise ValueError(
                    f"event {event.event_id}: payload.kind={kind!r} must be one of "
                    f"{sorted(TRACE_EVENT_KINDS)}"
                )
        source = event.payload.get("source")
        if source is not None and not isinstance(source, str):
            raise ValueError(f"event {event.event_id}: payload.source must be str")
        self._events.append(event)

    def replay(self, loop_id: str) -> list[TraceEvent]:
        if not isinstance(loop_id, str) or not loop_id.strip():
            raise ValueError("loop_id must be a non-empty str")
        return [event for event in self._events if event.loop_id == loop_id]

    def to_jsonl(self, path: str | Path) -> int:
        """Write all events as JSONL and return the number of lines written."""

        target = Path(path)
        lines = [event.to_json() for event in self._events]
        target.write_text(
            "".join(line + "\n" for line in lines),
            encoding="utf-8",
        )
        return len(lines)

    @classmethod
    def from_jsonl(cls, path: str | Path) -> "LearningMemory":
        """Load events from JSONL; fail closed on malformed or empty content."""

        source = Path(path)
        memory = cls()
        for line_number, raw in enumerate(source.read_text(encoding="utf-8").splitlines(), start=1):
            if not raw.strip():
                continue
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{source}: line {line_number}: invalid JSON: {exc}") from exc
            if not isinstance(data, dict):
                raise ValueError(f"{source}: line {line_number}: expected JSON object")
            memory.append(TraceEvent.from_dict(data))
        return memory

    def delete(self, learner_id: str) -> int:
        """Delete all events belonging to ``learner_id``; return removed count.

        Events are matched by ``payload.learner_id``, membership in
        ``payload.learner_ids``, or ``payload.learner.learner_id``.  Both facts
        and inferences are deleted together: memory must not retain inferred
        data about a learner whose data was removed (synthetic erasure test).
        """

        if not isinstance(learner_id, str) or not learner_id.strip():
            raise ValueError("learner_id must be a non-empty str")
        kept: list[TraceEvent] = []
        removed = 0
        for event in self._events:
            if learner_id in _learner_ids_in(event):
                removed += 1
            else:
                kept.append(event)
        self._events = kept
        return removed
