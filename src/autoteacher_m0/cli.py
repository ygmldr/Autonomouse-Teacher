"""Offline-first CLI. Execute this generated controller only in reviewed isolation."""
import argparse
import importlib.metadata
import json
import sys
from pathlib import Path
from uuid import uuid4

from autoteacher_m0.contracts import CONTRACT_VERSION, RunRequest, RuntimeFailure
from autoteacher_m0.runtime.mock_adapter import MockRuntime
from autoteacher_m0.settings import MODEL, PRIMARY_ROUTE
from autoteacher_m0.storage.artifacts import ArtifactStore


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="at-m0")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("inspect-runtime", help="metadata only; does not initialize SDK")
    for name in ("smoke", "paired"):
        command = sub.add_parser(name)
        mode = command.add_mutually_exclusive_group(required=True)
        mode.add_argument("--mock", action="store_true")
        mode.add_argument("--live", action="store_true")
        command.add_argument("--budget-usd", type=float, default=1.0,
                             help="reserved for future approved live controller; never unlocks Live")
        command.add_argument("--artifact-dir", type=Path, default=Path("artifacts") / name)
    report = sub.add_parser("report")
    report.add_argument("--experiment", default="latest")
    report.add_argument("--artifact-dir", type=Path, default=Path("artifacts") / "paired")
    return parser


def inspect_runtime() -> dict:
    from autoteacher_m0.security.gates import LiveGate

    packages = {}
    for package in ("deepseek-harness-sdk", "deepseek-harness-runtime-bin", "pydantic"):
        try:
            packages[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            packages[package] = "NOT_INSTALLED"
    return {
        "contract_version": CONTRACT_VERSION, "python": sys.version.split()[0],
        "packages": packages, "profile": "sdk-minimal",
        "primary_route": PRIMARY_ROUTE, "model": MODEL,
        "live_status": "BLOCKED", "sdk_initialized": False,
        "merged_profile": "NOT_INSPECTED", "sdk_smoke": "NOT_EXECUTED",
        "gate_reasons": list(LiveGate().inspect().reasons),
        "plugin": {"name": "autoteacher-skill-lookup", "tool": "skill_lookup",
                   "pinned_dsh_abi": "0.2.1-rc.2", "profile_install": "NOT_TESTED",
                   "model_originated_tool_calls": "BLOCKED"},
        "accounting": {"persistent_ledger": "AVAILABLE_NOT_WIRED_TO_LIVE",
                       "internal_sdk_steps": "UNVERIFIED"},
        "warning": "metadata inspection is not SDK lifecycle verification",
    }


def smoke_mock(artifact_dir: Path) -> dict:
    from autoteacher_m0.accounting import BudgetGuard, conservative_input_bound, mock_prices, normalize_usage

    guard = BudgetGuard(mock_prices())
    store = ArtifactStore(artifact_dir)
    with MockRuntime(artifact_dir / "mock-home") as runtime:
        records = []
        for index in range(3):
            request = RunRequest(
                case_id=f"E1-01-mock-{index}", prompt="Reply with M0_SMOKE_OK.",
                candidate_id="smoke-mock", session_id=f"smoke-{uuid4().hex}",
                provider="mock", model=MODEL, route_id="mock",
            )
            reservation = guard.reserve(
                task_id=request.session_id, route_id=request.route_id, model=request.model,
                input_tokens=conservative_input_bound(request.prompt), output_tokens=1024,
            )
            try:
                record = runtime.run(request)
            except Exception:
                guard.fail(reservation)
                raise
            guard.settle(reservation, normalize_usage(
                record.input_tokens, record.output_tokens,
                reserved_input=reservation.input_tokens, reserved_output=reservation.output_tokens,
            ), status=record.status)
            store.save(record)
            records.append(record)
    passed = all(record.status == "SUCCESS" and record.text == "M0_SMOKE_OK" for record in records)
    return {"mode": "mock", "mock_smoke": "PASS" if passed else "FAIL", "count": len(records),
            "real_sdk_smoke": "NOT_EXECUTED", "E1": "BLOCKED",
            "billable_cost_usd": "0", "synthetic_accounting": guard.snapshot(),
            "run_ids": [record.run_id for record in records]}


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if getattr(args, "live", False):
        # Reject before SDK import, directory creation, evaluation module import,
        # credential inspection or parsing agent-editable approval documents.
        from autoteacher_m0.security.gates import LiveGate
        try:
            LiveGate().require_live(live_requested=True)
        except RuntimeFailure as exc:
            print(json.dumps({"status": "BLOCKED", "error_code": exc.code, "reason": str(exc)}))
            return 3
        # No current gate can return, but unexpected future changes stay closed.
        print(json.dumps({"status": "BLOCKED", "error_code": "SECURITY_BLOCKED"}))
        return 3
    if args.command == "inspect-runtime":
        print(json.dumps(inspect_runtime(), indent=2))
        return 0
    if args.command == "smoke":
        result = smoke_mock(args.artifact_dir)
        print(json.dumps(result, indent=2))
        return 0 if result["mock_smoke"] == "PASS" else 1
    from autoteacher_m0.experiments.cli import render_report, run_paired
    try:
        if args.command == "paired":
            target = run_paired(artifact_dir=args.artifact_dir)
            print(json.dumps({"status": "SUCCESS", "mode": "mock",
                              "experiment_id": target.name, "artifact_dir": str(target),
                              "report": str(target / "comparison.md"),
                              "live_status": "BLOCKED", "private_eval": "NOT_RUN"}, indent=2))
        else:
            target = render_report(artifact_dir=args.artifact_dir, experiment=args.experiment)
            print(json.dumps({"status": "SUCCESS", "report": str(target),
                              "mode": "mock", "live_status": "BLOCKED"}, indent=2))
    except (OSError, ValueError, KeyError):
        # Do not disclose raw filesystem paths/provider diagnostics from errors.
        print(json.dumps({"status": "ERROR", "error_code": "ARTIFACT_ERROR",
                          "reason": "missing or invalid public experiment artifacts"}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
