"""A-NEXT OCI run guard: never point ``podman --rootfs`` at the frozen rootfs.

Why
---
During G4-R, repeated ``podman run --rootfs <frozen rootfs>`` invocations
materialised empty mount-target directories inside the 291 MB frozen rootfs and
changed its canonical hash (``25491e45…`` -> ``0340fb78…``/``a6737150…``).  The
frozen tree is evidence; container runs must use a writable copy.

What this script enforces
-------------------------
* Refuses a ``--rootfs`` that IS the frozen rootfs (same path / frozen marker /
  canonical hash match) — detection is read-only, the frozen tree is only
  hashed, never written.
* Refuses output/evidence directories that already exist, are under a frozen
  tree, or live inside the requested ``--rootfs``.
* Refuses to start a batch unless it owns the single-writer lock for its
  evidence parent; evidence directories are exclusive to one batch.
* Snapshots the frozen rootfs canonical hash (T0), runs the wrapped command,
  snapshots again (T1), and exits non-zero on drift.
* Scrubs key-like environment variables from the wrapped command by default
  (names only are recorded; values are never read/logged).

Exit codes
----------
0  OK
2  usage error (argparse also exits 2)
10 rootfs refused: frozen tree
11 output/evidence directory refused
12 single-writer lock held by another batch
13 rootfs refused: not a usable working directory
20 T0/T1 drift detected (or frozen sha mismatch after run)
21 wrapped command exited non-zero
23 pre-existing drift on the frozen rootfs before the run
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _common as common  # noqa: E402

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_REFUSED_FROZEN_ROOTFS = 10
EXIT_REFUSED_OUTPUT = 11
EXIT_REFUSED_LOCK = 12
EXIT_REFUSED_ROOTFS = 13
EXIT_DRIFT = 20
EXIT_COMMAND_FAILED = 21
EXIT_PREEXISTING_DRIFT = 23

LOCK_NAME = ".a_next.writer.lock"


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class Refusal(Exception):
    def __init__(self, code: int, reason: str, detail: dict | None = None):
        super().__init__(reason)
        self.code = code
        self.reason = reason
        self.detail = detail or {}


def _emit(document: dict) -> None:
    json.dump(document, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")


def _check_frozen_rootfs(
    path: Path,
    frozen_path: Path | None,
    frozen_sha: str,
    *,
    hash_target: bool = True,
) -> dict:
    """Read-only frozen detection for the requested rootfs path."""
    if not path.is_dir():
        raise Refusal(EXIT_REFUSED_ROOTFS, "rootfs_not_a_directory", {"path": str(path)})
    if frozen_path is not None and path.resolve() == frozen_path.resolve():
        raise Refusal(
            EXIT_REFUSED_FROZEN_ROOTFS,
            "rootfs_is_the_frozen_tree",
            {"rootfs": str(path), "frozen": str(frozen_path)},
        )
    marker = common.find_marker(path)
    if marker is not None:
        raise Refusal(
            EXIT_REFUSED_FROZEN_ROOTFS,
            "rootfs_has_frozen_marker",
            {"rootfs": str(path), "marker": marker},
        )
    if hash_target:
        sha = common.canonical_tree_sha256(path)
        if sha == frozen_sha:
            raise Refusal(
                EXIT_REFUSED_FROZEN_ROOTFS,
                "rootfs_canonical_hash_matches_frozen",
                {"rootfs": str(path), "sha256": sha, "frozen_sha256": frozen_sha},
            )
        return {"rootfs_sha256": sha, "frozen_marker": marker}
    return {"rootfs_sha256": None, "frozen_marker": marker}


def _check_new_output(path: Path | None, label: str, rootfs: Path, frozen_paths: list[Path]) -> None:
    if path is None:
        return
    if path.exists() or path.is_symlink():
        raise Refusal(
            EXIT_REFUSED_OUTPUT, f"{label}_already_exists", {"path": str(path)}
        )
    parent = path.parent
    if not parent.is_dir():
        raise Refusal(EXIT_REFUSED_OUTPUT, f"{label}_parent_missing", {"path": str(path)})
    if not os.access(parent, os.W_OK):
        raise Refusal(EXIT_REFUSED_OUTPUT, f"{label}_parent_not_writable", {"path": str(path)})
    for frozen in frozen_paths:
        if common.is_under(path, frozen):
            raise Refusal(
                EXIT_REFUSED_OUTPUT,
                f"{label}_under_frozen_tree",
                {"path": str(path), "frozen": str(frozen)},
            )
    if common.is_under(path, rootfs):
        raise Refusal(
            EXIT_REFUSED_OUTPUT,
            f"{label}_inside_rootfs",
            {"path": str(path), "rootfs": str(rootfs)},
        )


def _snapshot(
    frozen_path: Path | None,
    rootfs: Path,
    deps: Path | None,
    runtime: Path | None,
    stage_manifest: Path | None,
) -> dict:
    snapshot: dict = {"utc": utc_now()}
    if frozen_path is not None and frozen_path.is_dir():
        snapshot["frozen_rootfs_sha256"] = common.canonical_tree_sha256(frozen_path)
    else:
        snapshot["frozen_rootfs_sha256"] = None
    snapshot["work_rootfs_sha256"] = common.canonical_tree_sha256(rootfs)
    if deps is not None and deps.is_dir():
        snapshot["deps_sha256"] = common.canonical_tree_sha256(deps)
    if runtime is not None and runtime.is_file():
        snapshot["runtime_sha256"] = common.sha256_file(runtime)
    if stage_manifest is not None and stage_manifest.is_file():
        snapshot["stage_manifest_sha256"] = common.sha256_file(stage_manifest)
    return snapshot


def _acquire_lock(parent: Path, claim_id: str, claim: dict) -> Path:
    lock = parent / LOCK_NAME
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise Refusal(
            EXIT_REFUSED_LOCK,
            "writer_lock_held",
            {"lock": str(lock), "claim_id": claim_id},
        ) from None
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(claim, handle, indent=2, sort_keys=True)
    return lock


def _release_lock(lock: Path) -> None:
    try:
        lock.unlink()
    except FileNotFoundError:
        pass


def build_parser() -> argparse.ArgumentParser:
    def add_frozen_options(sub_parser: argparse.ArgumentParser) -> None:
        sub_parser.add_argument(
            "--frozen-rootfs",
            default=os.environ.get("A_NEXT_FROZEN_ROOTFS", ""),
            help="path to the frozen rootfs (default: $A_NEXT_FROZEN_ROOTFS)",
        )
        sub_parser.add_argument(
            "--frozen-sha",
            default=common.FROZEN_ROOTFS_SHA256,
            help="expected canonical sha256 of the frozen rootfs",
        )
        sub_parser.add_argument(
            "--skip-sha-detection",
            action="store_true",
            help="skip canonical-hash based frozen detection (marker/path checks remain)",
        )

    parser = argparse.ArgumentParser(description="A-NEXT OCI/rootfs run guard")
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check-rootfs", help="read-only frozen-rootfs detection")
    add_frozen_options(check)
    check.add_argument("path")
    check.add_argument("--json-out", default=None)

    pre = sub.add_parser("preflight", help="validate paths without running anything")
    add_frozen_options(pre)
    pre.add_argument("--rootfs", required=True)
    pre.add_argument("--evidence-dir", required=True)
    pre.add_argument("--output-dir", default=None)
    pre.add_argument("--claim-id", default="preflight")
    pre.add_argument("--json-out", default=None)

    run = sub.add_parser("run", help="guarded run: T0 snapshot, command, T1 snapshot")
    add_frozen_options(run)
    run.add_argument("--rootfs", required=True, help="writable working copy (never frozen)")
    run.add_argument("--evidence-dir", required=True, help="new directory for this batch")
    run.add_argument("--output-dir", default=None, help="optional new output directory")
    run.add_argument("--claim-id", required=True, help="unique batch/claim identifier")
    run.add_argument("--deps", default=None)
    run.add_argument("--runtime", default=None)
    run.add_argument("--stage-manifest", default=None)
    run.add_argument("--timeout", type=float, default=1800.0)
    run.add_argument(
        "--keep-env",
        action="store_true",
        help="do not scrub key-like env names from the wrapped command",
    )
    run.add_argument("--podman-check", action="store_true", help="record podman ps -a")
    run.add_argument(
        "--no-frozen-snapshot",
        action="store_true",
        help="explicitly run without a frozen rootfs T0/T1 snapshot (not for evidence runs)",
    )
    run.add_argument("--json-out", default=None)
    run.add_argument("--keep-lock", action="store_true")
    run.add_argument("wrapped", nargs=argparse.REMAINDER)

    return parser


def cmd_check_rootfs(args: argparse.Namespace, frozen_path: Path | None) -> int:
    path = common.resolved(args.path)
    document: dict = {"utc": utc_now(), "path": str(path)}
    try:
        result = _check_frozen_rootfs(
            path, frozen_path, args.frozen_sha, hash_target=not args.skip_sha_detection
        )
        document.update(result)
        document["is_frozen"] = False
        document["verdict"] = "NOT_FROZEN"
        code = EXIT_OK
    except Refusal as refusal:
        document.update(
            {"is_frozen": True, "verdict": refusal.reason, "detail": refusal.detail}
        )
        code = refusal.code
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    _emit(document)
    return code


def _resolve_frozen(args: argparse.Namespace) -> Path | None:
    return common.resolved(args.frozen_rootfs) if args.frozen_rootfs else None


def _preflight(
    args: argparse.Namespace, frozen_path: Path | None
) -> tuple[Path, Path, Path | None, dict]:
    rootfs = common.resolved(args.rootfs)
    evidence = common.resolved(args.evidence_dir)
    output = common.resolved(args.output_dir) if args.output_dir else None
    frozen_paths = [p for p in (frozen_path,) if p is not None]
    info = _check_frozen_rootfs(
        rootfs, frozen_path, args.frozen_sha, hash_target=not args.skip_sha_detection
    )
    _check_new_output(evidence, "evidence_dir", rootfs, frozen_paths)
    _check_new_output(output, "output_dir", rootfs, frozen_paths)
    if frozen_path is not None and frozen_path.is_dir():
        sha = common.canonical_tree_sha256(frozen_path)
        if sha != args.frozen_sha:
            raise Refusal(
                EXIT_PREEXISTING_DRIFT,
                "frozen_rootfs_not_at_expected_sha_before_run",
                {"frozen_rootfs": str(frozen_path), "actual": sha, "expected": args.frozen_sha},
            )
        info["frozen_rootfs_sha256"] = sha
    return rootfs, evidence, output, info


def cmd_preflight(args: argparse.Namespace, frozen_path: Path | None) -> int:
    document: dict = {"utc": utc_now(), "command": "preflight"}
    try:
        rootfs, evidence, output, info = _preflight(args, frozen_path)
        document.update(
            {
                "ok": True,
                "rootfs": str(rootfs),
                "evidence_dir": str(evidence),
                "output_dir": str(output) if output else None,
                "rootfs_sha256": info.get("rootfs_sha256"),
                "frozen_rootfs_sha256": info.get("frozen_rootfs_sha256"),
                "claim_id": args.claim_id,
            }
        )
        code = EXIT_OK
    except Refusal as refusal:
        document.update({"ok": False, "refused": refusal.reason, "detail": refusal.detail})
        code = refusal.code
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    _emit(document)
    return code


def cmd_run(args: argparse.Namespace, frozen_path: Path | None) -> int:
    document: dict = {
        "utc": utc_now(),
        "command": "run",
        "claim_id": args.claim_id,
        "argv": list(args.wrapped),
    }
    lock: Path | None = None
    evidence: Path | None = None
    exit_code = EXIT_OK
    try:
        if args.no_frozen_snapshot and frozen_path is None:
            pass
        elif frozen_path is None:
            raise Refusal(
                EXIT_USAGE,
                "frozen_rootfs_required_for_T0_T1_snapshot",
                {"hint": "set --frozen-rootfs/env A_NEXT_FROZEN_ROOTFS or pass --no-frozen-snapshot"},
            )
        rootfs, evidence, output, info = _preflight(args, frozen_path)
        evidence_parent = evidence.parent
        lock = _acquire_lock(
            evidence_parent,
            args.claim_id,
            {
                "claim_id": args.claim_id,
                "pid": os.getpid(),
                "utc": utc_now(),
                "rootfs": str(rootfs),
                "evidence_dir": str(evidence),
            },
        )
        document["lock"] = str(lock)
        evidence.mkdir(parents=False)
        if output is not None:
            output.mkdir(parents=False)
        document["evidence_dir"] = str(evidence)
        document["output_dir"] = str(output) if output else None
        document["rootfs"] = str(rootfs)
        document["rootfs_t0_sha256"] = info.get("rootfs_sha256")
        document["frozen_rootfs_t0"] = _snapshot(
            frozen_path,
            rootfs,
            Path(args.deps).resolve() if args.deps else None,
            Path(args.runtime).resolve() if args.runtime else None,
            Path(args.stage_manifest).resolve() if args.stage_manifest else None,
        )
        if not args.keep_env:
            env, removed = common.sanitize_env()
            document["env_scrubbed_names"] = removed
        else:
            env, removed = dict(os.environ), []
            document["env_scrubbed_names"] = []
        wrapped = list(args.wrapped)
        while wrapped and wrapped[0] == "--":
            wrapped.pop(0)
        if not wrapped:
            raise Refusal(EXIT_USAGE, "no_wrapped_command")
        document["argv"] = wrapped
        started = utc_now()
        with open(evidence / "stdout.txt", "wb") as out, open(
            evidence / "stderr.txt", "wb"
        ) as err:
            proc = subprocess.run(
                wrapped,
                cwd=str(rootfs),
                env=env,
                stdout=out,
                stderr=err,
            )
        finished = utc_now()
        document["wrapped"] = {
            "started_utc": started,
            "finished_utc": finished,
            "exit_code": proc.returncode,
        }
        document["frozen_rootfs_t1"] = _snapshot(
            frozen_path,
            rootfs,
            Path(args.deps).resolve() if args.deps else None,
            Path(args.runtime).resolve() if args.runtime else None,
            Path(args.stage_manifest).resolve() if args.stage_manifest else None,
        )
        t0 = document["frozen_rootfs_t0"].get("frozen_rootfs_sha256")
        t1 = document["frozen_rootfs_t1"].get("frozen_rootfs_sha256")
        drift = bool(t0 is not None and t1 is not None and t0 != t1)
        rootfs_drift = (
            document["frozen_rootfs_t0"].get("work_rootfs_sha256")
            != document["frozen_rootfs_t1"].get("work_rootfs_sha256")
        )
        document["drift"] = {
            "frozen_rootfs_changed": drift,
            "work_rootfs_changed": rootfs_drift,
            "t0": t0,
            "t1": t1,
        }
        if args.podman_check:
            podman = subprocess.run(
                ["podman", "ps", "-a"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            lines = [line for line in podman.stdout.splitlines() if line.strip()]
            document["podman_ps_a_lines"] = len(lines)
            document["podman_ps_a_raw"] = podman.stdout
        if drift or (t1 is not None and t1 != args.frozen_sha):
            document["verdict"] = "DRIFT"
            exit_code = EXIT_DRIFT
        elif proc.returncode != 0:
            document["verdict"] = "COMMAND_FAILED"
            exit_code = EXIT_COMMAND_FAILED
        else:
            document["verdict"] = "OK"
            exit_code = EXIT_OK
    except Refusal as refusal:
        document.update({"verdict": refusal.reason, "refused": refusal.reason, "detail": refusal.detail})
        exit_code = refusal.code
        evidence = None
    finally:
        if document.get("evidence_dir"):
            try:
                common.write_json(
                    Path(document["evidence_dir"]) / "guard-report.json", document
                )
            except OSError:
                pass
        if lock is not None and not args.keep_lock:
            _release_lock(lock)
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    _emit(document)
    return exit_code


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    frozen_path = _resolve_frozen(args)
    if args.command == "check-rootfs":
        return cmd_check_rootfs(args, frozen_path)
    if args.command == "preflight":
        return cmd_preflight(args, frozen_path)
    if args.command == "run":
        return cmd_run(args, frozen_path)
    return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
