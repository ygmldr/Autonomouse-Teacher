"""Shared TEST_ONLY fixtures for A-NEXT run-admission tests (no key/network).

The signed authorization material is the same synthetic G4-A fixture reused by
``tests/integration/g4r_auth``: an Ed25519 ``TEST_ONLY_`` seed in a pytest
temporary directory, never a real key.  The trusted Broker/Fake subprocesses
come from the frozen G4-F3 harness.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

REPO = Path(__file__).resolve().parents[3]
for _entry in (REPO / "src", REPO / "tests" / "integration" / "g4_a",
               REPO / "tests" / "integration" / "g4_f3",
               REPO / "tests" / "integration" / "g4_c",
               REPO / "tests" / "integration" / "g4_f5"):
    if str(_entry) not in sys.path:
        sys.path.insert(0, str(_entry))

from autoteacher_m0.bridge.admission import load_admission  # noqa: E402
from autoteacher_m0.bridge import run_admission as ra  # noqa: E402
from autoteacher_m0.security.authorization import (  # noqa: E402
    ApprovedRoute,
)
from g4a_support import NOW, SCOPE, TrustedFixture  # noqa: E402
import g4f3_support as f3  # noqa: E402

LAUNCHER = REPO / "scripts" / "a_next" / "admission" / "trusted_launcher.py"
L2_RUNNER = REPO / "scripts" / "a_next" / "admission" / "l2_admission_cases.py"
APPROVED_ROUTE = ApprovedRoute(**{"route_id": "opencode-go",
                                  "provider": "opencode-go",
                                  "model": "deepseek-v4.1-flash"})
TOOL_DIGEST = hashlib.sha256(b"tool").hexdigest()
DEFAULT_NONCE = "b" * 32
DEFAULT_ADMISSION_ID = "a" * 32


def admission_document(*, run_id: str = "run-a2-host", nonce: str = DEFAULT_NONCE,
                       admission_id: str = DEFAULT_ADMISSION_ID,
                       scenario: str = "ok_usage", max_calls: int = 8,
                       max_attempts: int = 1, deadline_ms: int = 30000,
                       expiry: str = "2099-01-01T00:00:00Z") -> dict:
    document = f3.admission_document(scenario=scenario, max_calls=max_calls)
    document["admission_id"] = admission_id
    document["run_id"] = run_id
    document["limits"]["max_attempts"] = max_attempts
    document["limits"]["deadline_ms"] = deadline_ms
    document["expiry_utc"] = expiry
    document["launcher"] = {"uid": 65534, "container": True,
                            "admission_nonce": nonce}
    return document


def write_admission(tmp_path: Path, **overrides) -> Path:
    path = tmp_path / "admission.json"
    path.write_text(json.dumps(admission_document(**overrides)))
    return path


def write_state(tmp_path: Path, *, suffix: str = "") -> tuple[Path, Path]:
    state = tmp_path / f"state{suffix}"
    state.mkdir(mode=0o700, exist_ok=True)
    use_log = tmp_path / f"use-log{suffix}"
    use_log.mkdir(mode=0o700, exist_ok=True)
    return use_log, state / "run-admission.jsonl"


def tool_schemas_from(admission_path: Path) -> dict:
    admission = load_admission(admission_path, expected_uid=65534)
    return dict(admission.tool_schemas)


def identity_for(admission_path: Path, *, repo_root: Path) -> ra.RunIdentity:
    admission = load_admission(admission_path, expected_uid=65534)
    return ra.build_run_identity(admission, admission_path=admission_path,
                                 repo_root=repo_root)


def begin_kwargs(trusted: TrustedFixture, tmp_path: Path, *,
                 admission_path: Path | None = None,
                 use_log_dir: Path | None = None,
                 journal_path: Path | None = None,
                 identity: ra.RunIdentity | None = None,
                 **overrides) -> dict:
    admission_path = admission_path or write_admission(tmp_path)
    default_use_log, default_journal = write_state(tmp_path)
    identity = identity or identity_for(admission_path, repo_root=trusted.repo)
    admission = load_admission(admission_path, expected_uid=65534)
    kwargs = {
        "identity": identity,
        "admission_path": admission_path,
        "admission_limits": {"max_calls": admission.max_calls,
                             "max_attempts": admission.max_attempts,
                             "deadline_ms": admission.deadline_ms},
        "authorization_path": trusted.authorization,
        "trusted_keys_path": trusted.keys,
        "revocation_path": trusted.revocations,
        "repo_root": trusted.repo,
        "expected_bindings": trusted.bindings,
        "approved_route": APPROVED_ROUTE,
        "actual_tools": ("skill_lookup",),
        "admission_tool_schemas": tuple(admission.tool_schemas),
        "budget_scope": SCOPE,
        "use_log_dir": use_log_dir or default_use_log,
        "journal_path": journal_path or default_journal,
        "observed_bindings": lambda: trusted.bindings,
        "approved_tool_schemas": None,
        "now": NOW,
    }
    kwargs.update(overrides)
    return kwargs


def begin(trusted: TrustedFixture, tmp_path: Path, **overrides):
    return ra.begin_run_admission(**begin_kwargs(trusted, tmp_path, **overrides))


def journal_records(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def use_records(use_log: Path) -> list[Path]:
    return sorted(path for path in use_log.iterdir()
                  if path.is_file() and path.suffix == ".json")


def controller_config(tmp_path: Path, *, socket_name: str = "bridge.sock") -> dict:
    """A Controller config used only for required-mode/structural exit tests."""
    return {
        "admission_path": str(tmp_path / "admission.json"),
        "broker_config_path": str(tmp_path / "broker.json"),
        "fake_script": str(tmp_path / "fake.py"),
        "receipt_dir": str(tmp_path / "receipts"),
        "attempt_db": str(tmp_path / "attempts.sqlite3"),
        "socket_path": str(tmp_path / socket_name),
        "python": sys.executable,
        "expected_uid": 65534,
    }


def write_controller_config(tmp_path: Path, *, required: bool | None = None,
                            name: str = "controller.json", **extra) -> Path:
    config = controller_config(tmp_path, **extra)
    if required is not None:
        config["run_admission_required"] = required
    path = tmp_path / name
    path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n")
    return path


def launcher_config(trusted: TrustedFixture, tmp_path: Path, *,
                    admission_path: Path | None = None,
                    use_log_dir: Path | None = None,
                    journal_path: Path | None = None,
                    controller_path: Path | None = None,
                    observed: dict | None = None,
                    approved_tool_schemas: dict | None = None,
                    required: bool = False,
                    **overrides) -> dict:
    admission_path = admission_path or write_admission(tmp_path)
    default_use_log, default_journal = write_state(tmp_path)
    config = {
        "authorization_path": str(trusted.authorization),
        "trusted_keys_path": str(trusted.keys),
        "revocation_path": str(trusted.revocations),
        "repo_root": str(trusted.repo),
        "admission_path": str(admission_path),
        "use_log_dir": str(use_log_dir or default_use_log),
        "journal_path": str(journal_path or default_journal),
        "expected_bindings": trusted.bindings.as_dict(),
        "observed_bindings": observed or trusted.bindings.as_dict(),
        "approved_route": {"route_id": "opencode-go", "provider": "opencode-go",
                           "model": "deepseek-v4.1-flash"},
        "actual_tools": ["skill_lookup"],
        "admission_tool_schemas": [["skill_lookup", TOOL_DIGEST]],
        "budget_scope": SCOPE,
        "controller_config_path": str(controller_path
                                      or write_controller_config(tmp_path)),
        "run_admission_required": required,
    }
    if approved_tool_schemas is not None:
        config["approved_tool_schemas"] = approved_tool_schemas
    config.update(overrides)
    return config


def write_launcher_config(tmp_path: Path, config: dict,
                          name: str = "launcher.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n")
    return path


def retime_authorization(trusted: TrustedFixture, *, valid_for_hours: int = 2) -> None:
    """Re-sign the synthetic authorization with a window around the real clock.

    The launcher subprocess runs with the real clock (no test clock hook), so
    subprocess tests must present an authorization whose window covers "now".
    Only the synthetic TEST_ONLY fixture is re-signed; no key material changes.
    """
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc).replace(microsecond=0)
    payload = dict(trusted.payload)
    payload.update({
        "issued_utc": (now - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "not_before_utc": (now - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "expires_utc": (now + timedelta(hours=valid_for_hours)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"),
    })
    trusted.payload = payload
    trusted.write_signed(payload)


def run_launcher(config_path: Path, *, dry_run: bool = True,
                 cwd: Path | None = None) -> subprocess.CompletedProcess:
    args = [sys.executable, str(LAUNCHER), "--config", str(config_path)]
    if dry_run:
        args.append("--dry-run")
    return subprocess.run(args, capture_output=True, text=True, cwd=str(cwd or REPO),
                          env={**os.environ, "PYTHONPATH": str(REPO / "src"),
                               "PYTHONDONTWRITEBYTECODE": "1"})
