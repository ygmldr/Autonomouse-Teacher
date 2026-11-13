"""SQLite index for sanitized project RunRecord objects, independent of DSH."""
import json
import sqlite3
from dataclasses import asdict
from pathlib import Path

from autoteacher_m0.contracts import RunRecord
from autoteacher_m0.storage.artifacts import safe_id, sanitize

SCHEMA_VERSION = 1


class RunStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS runs (run_id TEXT PRIMARY KEY, "
            "session_id TEXT NOT NULL, route_id TEXT NOT NULL, record_json TEXT NOT NULL)"
        )
        self.connection.commit()

    def save(self, record: RunRecord) -> None:
        # Index columns and filenames are part of the export boundary too.
        # Reject sensitive identifiers instead of creating redacted collisions.
        for identifier in (record.run_id, record.session_id, record.route_id):
            safe_id(identifier)
        document = json.dumps(sanitize(asdict(record)), ensure_ascii=False, allow_nan=False)
        with self.connection:
            self.connection.execute(
                "INSERT INTO runs VALUES (?, ?, ?, ?)",
                (record.run_id, record.session_id, record.route_id, document),
            )

    def load(self, run_id: str) -> RunRecord:
        row = self.connection.execute(
            "SELECT record_json FROM runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        if row is None:
            raise KeyError(run_id)
        return RunRecord(**json.loads(row[0]))

    def close(self) -> None:
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
