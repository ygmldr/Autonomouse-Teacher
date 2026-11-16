"""G3-B Offline Run Admission (B2-owned; fixed file, strict schema)."""
from __future__ import annotations
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

ADMISSION_PATH = Path("/work/g3b/admission.json")
ALLOWED_SCENARIOS = frozenset({"ok_usage", "partial_usage", "no_usage", "error", "eof",
                               "timeout", "cancel", "tool", "tool_once", "tool_final",
                               "usage_invalid", "receipt_conflict"})
ROUTE = ("offline-test-only-g3b", "fixture-bridge-v1")


class AdmissionError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _hex32(value: object) -> str:
    if not isinstance(value, str) or len(value) != 32 or any(c not in "0123456789abcdef" for c in value):
        raise AdmissionError("ADMISSION_INVALID")
    return value


def _no_extra(mapping: object, allowed: set[str]) -> Mapping:
    if not isinstance(mapping, Mapping) or set(mapping) != allowed:
        raise AdmissionError("ADMISSION_INVALID")
    return mapping


def _strict_int(value: object, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise AdmissionError("ADMISSION_INVALID")
    return value


@dataclass(frozen=True)
class Admission:
    schema: str
    admission_id: str
    scope_id: str
    run_id: str
    synthetic: bool
    route_id: str
    provider: str
    model: str
    tool_schemas: tuple[tuple[str, str], ...]
    max_calls: int
    max_attempts: int
    max_input_tokens: int
    max_output_tokens: int
    deadline_ms: int
    fake_scenario: str
    expiry_utc: datetime
    launcher_uid: int
    container: bool
    admission_nonce: str
    sha256: str


def load_admission(path: str | Path = ADMISSION_PATH, *, now_utc: datetime | None = None,
                   expected_uid: int = 65534) -> Admission:
    raw_path = Path(path)
    try:
        data = raw_path.read_bytes()
        doc = json.loads(data.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AdmissionError("ADMISSION_MISSING") from exc
    try:
        validate_admission_document(doc, now_utc=now_utc or datetime.now(timezone.utc),
                                    expected_uid=expected_uid)
    except AdmissionError:
        raise
    route = _no_extra(doc["route"], {"route_id", "provider", "model"})
    if (route["route_id"], route["model"]) != ROUTE or route["provider"] != ROUTE[0]:
        raise AdmissionError("ADMISSION_ROUTE_NOT_ALLOWED")
    limits = _no_extra(doc["limits"], {"max_calls", "max_attempts", "max_input_tokens",
                                       "max_output_tokens", "deadline_ms"})
    tool_schemas = []
    if not isinstance(doc["tool_schemas"], list):
        raise AdmissionError("ADMISSION_INVALID")
    for item in doc["tool_schemas"]:
        entry = _no_extra(item, {"name", "sha256"})
        if not isinstance(entry["name"], str) or not entry["name"]:
            raise AdmissionError("ADMISSION_INVALID")
        if not isinstance(entry["sha256"], str) or len(entry["sha256"]) != 64:
            raise AdmissionError("ADMISSION_INVALID")
        tool_schemas.append((entry["name"], entry["sha256"]))
    launcher = _no_extra(doc["launcher"], {"uid", "container", "admission_nonce"})
    if launcher["uid"] != expected_uid or launcher["container"] is not True:
        raise AdmissionError("ADMISSION_LAUNCHER_MISMATCH")
    expiry = doc["expiry_utc"]
    if not isinstance(expiry, str):
        raise AdmissionError("ADMISSION_INVALID")
    try:
        expiry_dt = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AdmissionError("ADMISSION_INVALID") from exc
    if expiry_dt <= (now_utc or datetime.now(timezone.utc)):
        raise AdmissionError("ADMISSION_EXPIRED")
    return Admission(
        schema=doc["schema"], admission_id=_hex32(doc["admission_id"]),
        scope_id=doc["scope_id"], run_id=doc["run_id"], synthetic=doc["synthetic"],
        route_id=ROUTE[0], provider=ROUTE[0], model=ROUTE[1],
        tool_schemas=tuple(tool_schemas),
        max_calls=_strict_int(limits["max_calls"], 1, 64),
        max_attempts=_strict_int(limits["max_attempts"], 1, 1),
        max_input_tokens=_strict_int(limits["max_input_tokens"], 1, 2500000),
        max_output_tokens=_strict_int(limits["max_output_tokens"], 1, 1024),
        deadline_ms=_strict_int(limits["deadline_ms"], 100, 30000),
        fake_scenario=str(doc["fake_scenario"]), expiry_utc=expiry_dt,
        launcher_uid=launcher["uid"], container=True,
        admission_nonce=_hex32(launcher["admission_nonce"]),
        sha256=hashlib.sha256(data).hexdigest())


def validate_admission_document(doc: object, *, now_utc: datetime | None = None,
                                expected_uid: int = 65534) -> None:
    required = {"schema", "admission_id", "scope_id", "run_id", "synthetic", "route",
                "tool_schemas", "limits", "fake_scenario", "expiry_utc", "launcher"}
    doc = _no_extra(doc, required)
    if doc["schema"] != "m0.g3b.admission.v1":
        raise AdmissionError("ADMISSION_INVALID")
    if not isinstance(doc["scope_id"], str) or doc["scope_id"] != "fixed-offline-scope":
        raise AdmissionError("ADMISSION_SCOPE_MISMATCH")
    run_id = doc["run_id"]
    if not isinstance(run_id, str) or not 1 <= len(run_id) <= 128 or any(ord(c) < 32 for c in run_id):
        raise AdmissionError("ADMISSION_INVALID")
    if doc["synthetic"] is not True:
        raise AdmissionError("ADMISSION_INVALID")
    if doc["fake_scenario"] not in ALLOWED_SCENARIOS:
        raise AdmissionError("ADMISSION_INVALID")
    if not isinstance(doc["expiry_utc"], str):
        raise AdmissionError("ADMISSION_INVALID")


def validate_request_payload(payload: Mapping[str, object]) -> None:
    """Reject candidate self-authorization/unknown fields."""
    allowed = {"sessionId", "provider", "model", "messages", "tools", "system",
               "maxTokens", "stream", "purpose"}
    if not isinstance(payload, Mapping) or set(payload) - allowed:
        raise AdmissionError("ADMISSION_SELF_AUTH_DENIED")
