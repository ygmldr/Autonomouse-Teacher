"""Deterministic public-fixture runtime. This is NOT a DSH SDK test.

An optional home persists mock-only JSONL. Different homes test project mock
namespaces only, never prove DSH recovery or malicious-code filesystem isolation.
"""
import hashlib
import json
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from autoteacher_m0.contracts import ErrorCode, RunRecord, RunRequest, RuntimeFailure
from autoteacher_m0.storage.artifacts import safe_id, sanitize


class MockRuntime:
    def __init__(self, home: Path | None = None, *, fail_with: str | None = None):
        self.home = home
        self.fail_with = fail_with
        self._sessions: dict[str, list[dict]] = {}
        if home is not None:
            (home / "sessions").mkdir(parents=True, exist_ok=True)

    def _path(self, session_id: str) -> Path:
        assert self.home is not None
        return self.home / "sessions" / (safe_id(session_id) + ".jsonl")

    def _load(self, session_id: str) -> list[dict]:
        safe_id(session_id)
        if session_id in self._sessions:
            return self._sessions[session_id]
        if self.home is None or not self._path(session_id).is_file():
            raise RuntimeFailure(ErrorCode.SESSION_NOT_FOUND, "mock session does not exist")
        try:
            rows = [json.loads(line) for line in self._path(session_id).read_text().splitlines()]
            if not rows or any(
                not isinstance(row, dict) or not isinstance(row.get("request"), dict)
                or not isinstance(row.get("record"), dict)
                or row["request"].get("session_id") != session_id for row in rows
            ):
                raise ValueError("invalid mock session rows")
            for row in rows:
                RunRequest(**row["request"])
                RunRecord(**row["record"])
        except (ValueError, TypeError, KeyError, OSError) as exc:
            raise RuntimeFailure(ErrorCode.SESSION_CORRUPT, "invalid mock session") from exc
        self._sessions[session_id] = rows
        return rows

    def run(self, request: RunRequest) -> RunRecord:
        safe_id(request.session_id)
        if request.session_id not in self._sessions:
            if self.home is not None and self._path(request.session_id).exists():
                self._load(request.session_id)
            else:
                self._sessions[request.session_id] = []
        history = self._sessions[request.session_id]
        fingerprint = hashlib.sha256(request.prompt.encode()).hexdigest()
        if self.fail_with:
            text, status, error = "", "ERROR", self.fail_with
        elif "M0_SMOKE_OK" in request.prompt:
            text, status, error = "M0_SMOKE_OK", "SUCCESS", None
        elif "skill_id" in request.prompt and "ready" in request.prompt:
            text, status, error = '{"skill_id":"binary_search","ready":true}', "SUCCESS", None
        elif request.prompt == "MOCK_RECALL":
            # Deliberate test-only command, never an assertion about model memory.
            text = "\n".join(row["request"]["prompt"] for row in history)
            status, error = "SUCCESS", None
        else:
            text = f"MOCK[{request.candidate_id}] {fingerprint[:16]}"
            status, error = "SUCCESS", None
        record = RunRecord(
            run_id=uuid4().hex, case_id=request.case_id, candidate_id=request.candidate_id,
            session_id=request.session_id, route_id=request.route_id, text=text,
            status=status, events=[{
                "type": "mock/turn", "sequence": len(history),
                "data": {"prompt_sha256": fingerprint, "mode": "mock"},
            }], input_tokens=len(request.prompt.split()), output_tokens=len(text.split()),
            estimated_cost_usd=0.0, error_code=error,
            metadata={"mode": "mock", "provider": request.provider, "model": request.model,
                      "created_at": datetime.now(timezone.utc).isoformat(),
                      "usage_kind": "synthetic", "cost_kind": "mock_no_billable_request"},
        )
        row = sanitize({"request": asdict(request), "record": asdict(record)})
        if self.home is not None:
            with self._path(request.session_id).open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
        history.append(row)
        return record

    def resume(self, session_id: str, prompt: str) -> RunRecord:
        rows = self._load(session_id)
        original = RunRequest(**rows[-1]["request"])
        return self.run(replace(original, prompt=prompt))

    def close(self) -> None:
        self._sessions.clear()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
