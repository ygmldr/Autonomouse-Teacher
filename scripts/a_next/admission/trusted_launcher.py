#!/usr/bin/env python3
"""A-NEXT test-only trusted launcher with run-level authorization admission.

This is the **test-only / no-key** Trusted Run Admission harness.  It performs
the trusted order that the production deployment will eventually use:

1. load the trusted Admission document and derive the Run identity/epoch;
2. verify and consume the single ``ExecutionAuthorization`` use
   (``begin_run_admission``) **before** any Broker/Fake/Controller is started;
3. only on success, start the trusted Controller (which starts the local
   synthetic Broker/Fake subprocesses) and serve.

It never reads a Key, never contacts a Provider/network, and never unlocks
``LiveGate``.  A denied admission exits non-zero with a stable JSON result on
stdout; no Broker process, socket, reservation, attempt or Fake byte exists in
that path (the Controller is never invoked).

Usage (test-only):

    python scripts/a_next/admission/trusted_launcher.py \
        --config /path/to/launcher-config.json [--dry-run]

Config schema (strict, absolute paths only):

    {
      "authorization_path": "/trusted/authorization.json",
      "trusted_keys_path": "/trusted/trusted-keys.json",
      "revocation_path": "/trusted/revocations.json",
      "repo_root": "/project",
      "admission_path": "/work/g3b/admission.json",
      "use_log_dir": "/work/state/use-log",
      "journal_path": "/work/state/run-admission.jsonl",
      "expected_bindings": {"code_sha256": "...", ... five roots ...},
      "observed_bindings": {"code_sha256": "...", ...}   # optional; defaults to expected
      "approved_route": {"route_id": "...", "provider": "...", "model": "..."},
      "actual_tools": ["skill_lookup"],
      "admission_tool_schemas": [["skill_lookup", "<sha256>"]],  # optional
      "budget_scope": "g4a-synthetic-rehearsal",
      "controller_config_path": "/work/state/controller.json",
      "run_admission_required": true,
      "launcher_uid": 0                                  # optional override
    }

Exit codes: 0 = serve/allow, 20 = admission denied, 21 = config invalid,
other = Controller startup code (3/4/5/6/7) passed through.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[3]
SRC = REPO / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autoteacher_m0.bridge.admission import (  # noqa: E402
    AdmissionError, load_admission,
)
from autoteacher_m0.bridge.controller import main as controller_main  # noqa: E402
from autoteacher_m0.bridge.run_admission import (  # noqa: E402
    RunAdmissionError, begin_run_admission, build_run_identity,
)
from autoteacher_m0.security.authorization import (  # noqa: E402
    ApprovedRoute, BINDING_NAMES, ExpectedBindings,
)

EXIT_ADMISSION_DENIED = 20
EXIT_CONFIG_INVALID = 21

_REQUIRED = {
    "authorization_path", "trusted_keys_path", "revocation_path", "repo_root",
    "admission_path", "use_log_dir", "journal_path", "expected_bindings",
    "approved_route", "actual_tools", "budget_scope",
    "controller_config_path",
}
_OPTIONAL = {
    "observed_bindings", "admission_tool_schemas", "approved_tool_schemas",
    "run_admission_required", "launcher_uid", "launcher_instance_id",
}


def _result(status: str, code: str = "", *, reasons: tuple[str, ...] = (),
             consumed: str = "NO", detail: dict | None = None) -> dict:
    payload: dict[str, object] = {
        "schema": "m0.g4r.admission-test-result.v1",
        "status": status,
        "code": code,
        "reasons": list(reasons),
        "consumed": consumed,
        "external_network_calls": 0,
        "provider_keys_seen": 0,
    }
    if detail:
        payload.update(detail)
    return payload


def _bindings(document: object, *, label: str) -> ExpectedBindings:
    if not isinstance(document, dict) or set(document) != set(BINDING_NAMES):
        raise ValueError(f"{label} must contain exactly {sorted(BINDING_NAMES)}")
    return ExpectedBindings(**{name: document[name] for name in BINDING_NAMES})


def _load_config(path: Path) -> dict:
    if not path.is_absolute():
        raise ValueError("config path must be absolute")
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError("config must be a JSON object")
    if set(document) - (_REQUIRED | _OPTIONAL):
        raise ValueError("config has unknown fields")
    if _REQUIRED - set(document):
        raise ValueError("config is missing required fields")
    for key in ("authorization_path", "trusted_keys_path", "revocation_path",
                "repo_root", "admission_path", "use_log_dir", "journal_path",
                "controller_config_path"):
        value = document[key]
        if not isinstance(value, str) or not value.startswith("/"):
            raise ValueError(f"{key} must be an absolute path")
    if not isinstance(document["budget_scope"], str) or not document["budget_scope"]:
        raise ValueError("budget_scope must be a nonempty string")
    if not isinstance(document["actual_tools"], list) or not all(
            isinstance(item, str) for item in document["actual_tools"]):
        raise ValueError("actual_tools must be a list of strings")
    if document.get("run_admission_required") not in (None, True, False):
        raise ValueError("run_admission_required must be a boolean")
    return document


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--dry-run", action="store_true",
                        help="only run the admission; never start the Controller")
    args = parser.parse_args(argv)
    try:
        config = _load_config(Path(args.config))
        expected = _bindings(config["expected_bindings"], label="expected_bindings")
        observed = _bindings(config.get("observed_bindings",
                                        config["expected_bindings"]),
                             label="observed_bindings")
        route_document = config["approved_route"]
        if not isinstance(route_document, dict) or set(route_document) != {
                "route_id", "provider", "model"}:
            raise ValueError("approved_route fields are invalid")
        approved_route = ApprovedRoute(**route_document)
    except (OSError, ValueError, TypeError) as error:
        print(json.dumps(_result("CONFIG_INVALID", "CONFIG_INVALID",
                                 reasons=(type(error).__name__,)),
                         sort_keys=True))
        return EXIT_CONFIG_INVALID

    identity = None
    try:
        admission = load_admission(config["admission_path"], expected_uid=65534)
        identity = build_run_identity(
            admission, admission_path=Path(config["admission_path"]),
            repo_root=Path(config["repo_root"]))
        tool_schemas = config.get("admission_tool_schemas")
        if tool_schemas is None:
            tool_schemas = list(admission.tool_schemas)
        approved_tool_schemas = config.get("approved_tool_schemas")
        if approved_tool_schemas is not None and not isinstance(
                approved_tool_schemas, dict):
            raise ValueError("approved_tool_schemas must be an object")
        context = begin_run_admission(
            identity=identity,
            admission_path=Path(config["admission_path"]),
            admission_limits={
                "max_calls": admission.max_calls,
                "max_attempts": admission.max_attempts,
                "deadline_ms": admission.deadline_ms,
            },
            authorization_path=Path(config["authorization_path"]),
            trusted_keys_path=Path(config["trusted_keys_path"]),
            revocation_path=Path(config["revocation_path"]),
            repo_root=Path(config["repo_root"]),
            expected_bindings=expected,
            approved_route=approved_route,
            actual_tools=tuple(config["actual_tools"]),
            admission_tool_schemas=tuple(
                (name, digest) for name, digest in tool_schemas),
            budget_scope=config["budget_scope"],
            approved_tool_schemas=approved_tool_schemas,
            use_log_dir=Path(config["use_log_dir"]),
            journal_path=Path(config["journal_path"]),
            observed_bindings=lambda: observed,
            launcher_uid=config.get("launcher_uid", os.getuid()),
            launcher_instance_id=config.get("launcher_instance_id"),
        )
    except RunAdmissionError as error:
        print(json.dumps(_result("DENY", error.code, reasons=error.reasons,
                                 consumed=error.consumed,
                                 detail={"run_epoch": getattr(
                                     identity, "run_epoch", "")}),
                         sort_keys=True))
        sys.stderr.write(f"RUN_ADMISSION_DENIED:{error.code}\n")
        return EXIT_ADMISSION_DENIED
    except (AdmissionError, OSError, ValueError, TypeError) as error:
        print(json.dumps(_result("CONFIG_INVALID", "CONFIG_INVALID",
                                 reasons=(type(error).__name__,)),
                         sort_keys=True))
        return EXIT_CONFIG_INVALID

    detail = {
        "run_id": context.run_id,
        "run_epoch": context.run_epoch,
        "authorization_id": context.authorization_id,
        "effective_max_calls": context.effective_max_calls,
        "use_record_sha256": context.use_record_sha256,
    }
    if args.dry_run:
        print(json.dumps(_result("ALLOW", "RUN_ADMISSION_ALLOW", consumed="YES",
                                 detail=detail), sort_keys=True))
        context.close("dry-run")
        return 0
    print(json.dumps(_result("ALLOW", "RUN_ADMISSION_ALLOW", consumed="YES",
                             detail=detail), sort_keys=True), flush=True)
    try:
        return controller_main(
            ["--config", config["controller_config_path"]],
            run_admission=context,
            run_admission_required=bool(config.get("run_admission_required", False)))
    finally:
        context.close("controller_exit")


if __name__ == "__main__":
    raise SystemExit(main())
