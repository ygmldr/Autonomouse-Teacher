"""Sanitized JSON artifacts for public mock evidence, not private evaluation data."""
import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any

from autoteacher_m0.contracts import RunRecord

_SECRET_KEY = re.compile(r"(api.?key|authorization|password|secret|access.?token)", re.I)
_SECRET_TEXT = re.compile(
    r"(?i)(bearer\s+\S+|sk-[A-Za-z0-9_-]+|"
    r"(?:api[_-]?key|password|secret|access[_-]?token)[\"']?\s*[:=]\s*[\"']?[^\s\"',;}]+)"
)
_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")


def safe_id(value: str) -> str:
    if not _SAFE_ID.fullmatch(value) or sanitize(value) != value:
        raise ValueError("identifier must be a non-sensitive safe basename, not a path")
    return value


def sanitize(value: Any, *, sentinels: tuple[str, ...] = ()) -> Any:
    """Defense in depth; arbitrary unknown secrets cannot be perfectly detected.

    Credential exclusion at the process boundary remains mandatory. Never include
    actual keys in sentinels: tests use invented sentinel strings only.
    """
    if isinstance(value, dict):
        result = {}
        for index, (key, item) in enumerate(value.items()):
            original_key = str(key)
            clean_key = sanitize(original_key, sentinels=sentinels)
            if clean_key != original_key:
                # Preserve entries without exposing sensitive key material or
                # collapsing several secret dictionary keys into one slot.
                clean_key = f"[REDACTED_KEY_{index}]"
                while clean_key in value or clean_key in result:
                    clean_key += "_"
            result[clean_key] = (
                "[REDACTED]" if _SECRET_KEY.search(original_key)
                else sanitize(item, sentinels=sentinels)
            )
        return result
    if isinstance(value, (list, tuple)):
        return [sanitize(item, sentinels=sentinels) for item in value]
    if isinstance(value, str):
        for sentinel in sentinels:
            if sentinel:
                value = value.replace(sentinel, "[REDACTED]")
        return _SECRET_TEXT.sub("[REDACTED]", value)
    if value is None or isinstance(value, (int, float, bool)):
        return value
    raise TypeError("artifact contains an unsupported object; SDK objects must not cross ABI")


class ArtifactStore:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, record: RunRecord) -> Path:
        target = self.root / (safe_id(record.run_id) + ".json")
        # Exclusive creation avoids silently replacing evidence.
        with target.open("x", encoding="utf-8") as handle:
            json.dump(sanitize(asdict(record)), handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
        return target

    def load(self, run_id: str) -> RunRecord:
        data = json.loads((self.root / (safe_id(run_id) + ".json")).read_text(encoding="utf-8"))
        return RunRecord(**data)
