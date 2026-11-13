"""Fail-closed diagnostics, NOT an independently deployed authorization boundary.

No file, environment variable, CLI flag, injected Python object or signed-looking
JSON can enable Live. A maintainer must deploy a separately protected launcher /
credential broker and re-review this implementation before adding an allow path.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import PurePosixPath
from typing import Mapping, Any

from autoteacher_m0.contracts import ErrorCode, RuntimeFailure


class SecurityBlocked(RuntimeFailure):
    def __init__(self, message: str = "Independent human authorization boundary not deployed"):
        super().__init__(ErrorCode.SECURITY_BLOCKED, message)


@dataclass(frozen=True)
class Baseline:
    """A diagnostic fingerprint, never an approval token.

    The external maintainer must independently supply a COMPLETE inventory of
    controller, plugin, dependency locks, profile/tools and policy inputs. This
    pure function accepts bytes; it never searches home directories or reads keys.
    """
    inventory_sha256: str
    configuration_sha256: str


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def fingerprint(files: Mapping[str, bytes], configuration: Mapping[str, Any]) -> Baseline:
    if not files:
        raise ValueError("A baseline requires an explicit, nonempty inventory")
    inventory = {}
    for name, content in files.items():
        path = PurePosixPath(name)
        if (not name or path.is_absolute() or ".." in path.parts
                or "\\" in name or path.as_posix() != name):
            raise ValueError("Inventory paths must be normalized relative POSIX paths")
        if not isinstance(content, bytes):
            raise TypeError("Inventory values must be explicit file bytes")
        inventory[name] = hashlib.sha256(content).hexdigest()
    return Baseline(hashlib.sha256(_canonical(inventory)).hexdigest(),
                    hashlib.sha256(_canonical(dict(configuration))).hexdigest())


@dataclass(frozen=True)
class GateDecision:
    status: str
    reasons: tuple[str, ...]
    external_boundary_deployed: bool = False


class LiveGate:
    """Intentionally no authorize()/approve() and no credential injection path."""

    def inspect(self, *, live_requested: bool = False,
                actual: Baseline | None = None, reviewed: Baseline | None = None,
                actual_tools: tuple[str, ...] | None = None,
                session_log_disabled: bool = False) -> GateDecision:
        reasons = ["EXTERNAL_HUMAN_AUTHORIZATION_BOUNDARY_NOT_DEPLOYED"]
        if not live_requested:
            reasons.append("LIVE_NOT_EXPLICITLY_REQUESTED")
        if actual is None or reviewed is None:
            reasons.append("BASELINE_EVIDENCE_MISSING")
        elif actual != reviewed:
            reasons.append("BASELINE_OR_CONFIGURATION_CHANGED")
        # Exact actual registry evidence, not a list parsed from an approval MD.
        if actual_tools is None or set(actual_tools) != {"skill_lookup"}:
            reasons.append("ACTUAL_TOOL_REGISTRY_NOT_APPROVED")
        if not session_log_disabled:
            reasons.append("SESSION_LOG_UPLOAD_NOT_VERIFIED_DISABLED")
        return GateDecision("BLOCKED", tuple(reasons))

    def require_live(self, **evidence: Any) -> None:
        decision = self.inspect(**evidence)
        raise SecurityBlocked("; ".join(decision.reasons))
