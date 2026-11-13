"""Offline-first CLI. Execute this generated controller only in reviewed isolation."""
import argparse
import importlib.metadata
import json
import sys
from pathlib import Path
from uuid import uuid4

from autoteacher_m0.contracts import CONTRACT_VERSION, ErrorCode, RunRequest
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
        command.add_argument("--budget-usd", type=float, default=1.0)
        command.add_argument("--artifact-dir", type=Path, default=Path("artifacts") / name)
    report = sub.add_parser("report")
    report.add_argument("--experiment", default="latest")
    report.add_argument("--artifact-dir", type=Path, default=Path("artifacts") / "paired")
    return parser


def inspect_runtime() -> dict:
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
        "warning": "metadata inspection is not SDK lifecycle verification",
    }


def smoke_mock(artifact_dir: Path) -> dict:
    store = ArtifactStore(artifact_dir)
    with MockRuntime(artifact_dir / "mock-home") as runtime:
        records = []
        for index in range(3):
            request = RunRequest(
                case_id=f"E1-01-mock-{index}", prompt="Reply with M0_SMOKE_OK.",
                candidate_id="smoke-mock", session_id=f"smoke-{uuid4().hex}",
                provider=PRIMARY_ROUTE, model=MODEL, route_id=PRIMARY_ROUTE,
            )
            record = runtime.run(request)
            store.save(record)
            records.append(record)
    passed = all(record.status == "SUCCESS" and record.text == "M0_SMOKE_OK" for record in records)
    return {"mode": "mock", "mock_smoke": "PASS" if passed else "FAIL", "count": len(records),
            "real_sdk_smoke": "NOT_EXECUTED", "E1": "BLOCKED",
            "run_ids": [record.run_id for record in records]}


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if getattr(args, "live", False):
        # Reject before SDK import, directory creation, evaluation module import,
        # credential inspection or parsing agent-editable approval documents.
        print(json.dumps({"status": "BLOCKED", "error_code": str(ErrorCode.SECURITY_BLOCKED),
                          "reason": "independent human approval and safe controller boundary required"}))
        return 3
    if args.command == "inspect-runtime":
        print(json.dumps(inspect_runtime(), indent=2))
        return 0
    if args.command == "smoke":
        result = smoke_mock(args.artifact_dir)
        print(json.dumps(result, indent=2))
        return 0 if result["mock_smoke"] == "PASS" else 1
    # Cross-module execution is intentionally deferred to dependent task-5.
    print(json.dumps({"status": "BLOCKED", "command": args.command,
                      "reason": "cross-module CLI integration pending task-5"}))
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
