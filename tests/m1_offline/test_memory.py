"""Learning memory tests: append/replay order, JSONL roundtrip, learner-scoped delete."""

from __future__ import annotations

import json

import pytest

from m1_offline.memory import LearningMemory, TRACE_EVENT_KINDS
from m1_offline.types import TraceEvent


def _event(
    event_id: str,
    loop_id: str = "loop-001",
    round_number: int = 0,
    step: str = "plan",
    payload: dict | None = None,
) -> TraceEvent:
    return TraceEvent(
        event_id=event_id,
        loop_id=loop_id,
        round=round_number,
        step=step,
        payload=payload if payload is not None else {"kind": "FACT", "source": "synthetic"},
    )


def test_append_and_replay_preserve_order():
    memory = LearningMemory()
    events = [_event("e1", round_number=0), _event("e2", round_number=1), _event("e3", round_number=2)]
    for event in events:
        memory.append(event)
    assert len(memory) == 3
    replayed = memory.replay("loop-001")
    assert [event.event_id for event in replayed] == ["e1", "e2", "e3"]
    assert [event.round for event in replayed] == [0, 1, 2]


def test_replay_filters_by_loop_and_keeps_interleaved_order():
    memory = LearningMemory()
    memory.append(_event("a1", loop_id="loop-a", payload={"kind": "FACT", "source": "x"}))
    memory.append(_event("b1", loop_id="loop-b", payload={"kind": "FACT", "source": "x"}))
    memory.append(_event("a2", loop_id="loop-a", payload={"kind": "INFERENCE", "source": "y"}))
    assert [event.event_id for event in memory.replay("loop-a")] == ["a1", "a2"]
    assert [event.event_id for event in memory.replay("loop-b")] == ["b1"]
    assert memory.replay("missing-loop") == []
    assert memory.loop_ids() == ["loop-a", "loop-b"]


def test_replay_preserves_fact_and_inference_distinction():
    memory = LearningMemory()
    memory.append(
        _event("fact", payload={"kind": "FACT", "source": "fixture", "learner_id": "L1"})
    )
    memory.append(
        _event("inference", payload={"kind": "INFERENCE", "source": "learner_model", "learner_id": "L1"})
    )
    replayed = memory.replay("loop-001")
    assert replayed[0].payload["kind"] == "FACT"
    assert replayed[0].payload["source"] == "fixture"
    assert replayed[1].payload["kind"] == "INFERENCE"
    assert replayed[1].payload["source"] == "learner_model"


def test_jsonl_roundtrip_is_lossless(tmp_path):
    memory = LearningMemory()
    original = [
        _event("e1", payload={"kind": "FACT", "source": "synthetic", "learner_id": "L1"}),
        _event("e2", round_number=3, payload={"kind": "INFERENCE", "source": "model", "n": 2}),
    ]
    for event in original:
        memory.append(event)
    path = tmp_path / "memory.jsonl"
    written = memory.to_jsonl(path)
    assert written == 2
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["event_id"] == "e1"

    restored = LearningMemory.from_jsonl(path)
    assert len(restored) == 2
    assert [event.to_dict() for event in restored.events()] == [
        event.to_dict() for event in memory.events()
    ]
    # And re-serializing produces the same JSONL content.
    second_path = tmp_path / "memory2.jsonl"
    restored.to_jsonl(second_path)
    assert second_path.read_text(encoding="utf-8") == path.read_text(encoding="utf-8")


def test_delete_removes_only_that_learners_events_and_returns_count():
    memory = LearningMemory()
    memory.append(_event("f1", payload={"kind": "FACT", "source": "fixture", "learner_id": "L1"}))
    memory.append(
        _event("i1", payload={"kind": "INFERENCE", "source": "model", "learner_id": "L1"})
    )
    memory.append(_event("f2", payload={"kind": "FACT", "source": "fixture", "learner_id": "L2"}))
    memory.append(_event("x1", payload={"kind": "FACT", "source": "fixture"}))
    removed = memory.delete("L1")
    assert removed == 2
    assert len(memory) == 2
    assert [event.event_id for event in memory.events()] == ["f2", "x1"]


def test_delete_matches_learner_ids_list_and_nested_learner():
    memory = LearningMemory()
    memory.append(
        _event("many", payload={"kind": "FACT", "source": "x", "learner_ids": ["L3", "L4"]})
    )
    memory.append(
        _event("nested", payload={"kind": "FACT", "source": "x", "learner": {"learner_id": "L5"}})
    )
    memory.append(_event("other", payload={"kind": "FACT", "source": "x", "learner_id": "L6"}))
    assert memory.delete("L4") == 1
    assert memory.delete("L5") == 1
    assert len(memory) == 1
    assert memory.events()[0].event_id == "other"


def test_delete_unknown_learner_is_noop():
    memory = LearningMemory()
    memory.append(_event("e1", payload={"kind": "FACT", "source": "x", "learner_id": "L1"}))
    assert memory.delete("nobody") == 0
    assert len(memory) == 1


def test_delete_requires_non_empty_learner_id():
    memory = LearningMemory()
    with pytest.raises(ValueError):
        memory.delete("")
    with pytest.raises(ValueError):
        memory.delete(None)  # type: ignore[arg-type]


def test_invalid_payload_kind_fails_closed():
    memory = LearningMemory()
    with pytest.raises(ValueError):
        memory.append(_event("bad", payload={"kind": "GUESS", "source": "x"}))
    with pytest.raises(ValueError):
        memory.append(_event("bad", payload={"kind": "FACT", "source": 42}))
    with pytest.raises(TypeError):
        memory.append({"event_id": "e"})  # type: ignore[arg-type]
    assert len(memory) == 0
    assert "FACT" in TRACE_EVENT_KINDS


def test_events_returns_copy():
    memory = LearningMemory()
    memory.append(_event("e1"))
    copy = memory.events()
    copy.clear()
    assert len(memory) == 1


def test_from_jsonl_fails_closed_on_malformed_lines(tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_text('{"event_id": "e1"\n', encoding="utf-8")
    with pytest.raises(ValueError):
        LearningMemory.from_jsonl(path)
    path.write_text('["not", "an", "object"]\n', encoding="utf-8")
    with pytest.raises(ValueError):
        LearningMemory.from_jsonl(path)


def test_from_jsonl_rejects_unknown_fields(tmp_path):
    path = tmp_path / "unknown.jsonl"
    path.write_text(
        json.dumps(
            {
                "schema_version": "m1.offline.v0",
                "event_id": "e1",
                "loop_id": "loop-001",
                "round": 0,
                "step": "plan",
                "payload": {},
                "timestamp": "2026-01-01T00:00:00Z",
                "surprise": 1,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        LearningMemory.from_jsonl(path)


def test_blank_lines_in_jsonl_are_ignored(tmp_path):
    memory = LearningMemory()
    memory.append(_event("e1"))
    path = tmp_path / "blank.jsonl"
    path.write_text("\n" + memory.events()[0].to_json() + "\n\n", encoding="utf-8")
    restored = LearningMemory.from_jsonl(path)
    assert [event.event_id for event in restored.events()] == ["e1"]
