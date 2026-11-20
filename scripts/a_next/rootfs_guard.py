"""A-NEXT frozen-rootfs physical write-protection checks (read-only).

This script never modifies the tree it checks: it hashes (read-only), reads
``stat`` metadata, consults ``findmnt`` when available, and prints commands the
operator can run.  It fails non-zero when the frozen rootfs would be writable by
a non-privileged test uid.

Checks
------
1. canonical sha256 (tar-normalized recipe) equals the expected frozen identity;
2. no group/other write bits anywhere under the tree;
3. test uid (default 65534) cannot write: no path owned by that uid with the
   user-write bit set, and no writable path reachable through a writable parent
   (root-owned paths are reported, not treated as writable by the test uid);
4. mount point is read-only (``findmnt -no OPTIONS``) when ``--require-ro-mount``
   is given; otherwise the mount state is reported as informational.

Exit codes
----------
0  OK
2  usage error
30 permission violation (world/group writable or test-uid writable)
31 canonical sha mismatch
32 required read-only mount not satisfied
33 path missing / not a directory
"""

from __future__ import annotations

import argparse
import json
import stat
import subprocess
import sys
from pathlib import Path
from typing import Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _common as common  # noqa: E402

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_PERMISSION_VIOLATION = 30
EXIT_SHA_MISMATCH = 31
EXIT_NOT_READ_ONLY_MOUNT = 32
EXIT_PATH_MISSING = 33

WRITE_BITS = stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH


def utc_now() -> str:
    import time

    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def mount_options(path: Path) -> dict:
    """Return ``{"target","options","read_only"}`` from findmnt when available."""
    try:
        proc = subprocess.run(
            ["findmnt", "-T", str(path), "-no", "TARGET,OPTIONS"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except FileNotFoundError:
        return {"available": False, "error": "findmnt_not_found"}
    if proc.returncode != 0:
        return {"available": False, "error": proc.stderr.strip()[:200]}
    line = proc.stdout.strip().splitlines()[0] if proc.stdout.strip() else ""
    parts = line.split(None, 1)
    target = parts[0] if parts else ""
    options = parts[1] if len(parts) > 1 else ""
    return {
        "available": True,
        "target": target,
        "options": options,
        "read_only": "ro" in {item.strip() for item in options.split(",")},
    }


def scan_permissions(
    rootfs: Path, test_uid: int, max_entries: int
) -> dict:
    violations: list[dict] = []
    warnings: list[dict] = []
    scanned = 0
    truncated = False
    for path, info in common.iter_tree_entries(rootfs):
        if scanned >= max_entries:
            truncated = True
            break
        scanned += 1
        mode = info.st_mode
        if not stat.S_ISDIR(mode) and not stat.S_ISREG(mode):
            if stat.S_ISLNK(mode):
                continue
            warnings.append({"path": str(path), "reason": "special_file", "mode": oct(mode)})
            continue
        if mode & (stat.S_IWGRP | stat.S_IWOTH):
            violations.append(
                {
                    "path": str(path),
                    "reason": "group_or_other_writable",
                    "mode": oct(mode & 0o7777),
                }
            )
        if info.st_uid == test_uid and (mode & stat.S_IWUSR):
            violations.append(
                {
                    "path": str(path),
                    "reason": "test_uid_writable",
                    "mode": oct(mode & 0o7777),
                    "uid": info.st_uid,
                }
            )
        if info.st_uid not in (0, test_uid):
            warnings.append(
                {
                    "path": str(path),
                    "reason": "owner_not_root",
                    "uid": info.st_uid,
                    "mode": oct(mode & 0o7777),
                }
            )
    return {
        "scanned_entries": scanned,
        "truncated": truncated,
        "violations": violations[:200],
        "violation_count": len(violations),
        "warnings": warnings[:200],
        "warning_count": len(warnings),
    }


def verification_commands(rootfs: Path, test_uid: int) -> list[str]:
    """Executable commands an operator can run to independently check protection."""
    return [
        f"findmnt -T {rootfs} -no TARGET,OPTIONS",
        f"find {rootfs} \\( -type d -o -type f \\) -perm /022 -print | head -20",
        f"find {rootfs} -uid {test_uid} -perm /200 -print | head -20",
        f"setpriv --reuid={test_uid} --regid={test_uid} --clear-groups "
        f"test -w {rootfs} ; echo exit=$?   # expect non-zero",
        f"podman run --rm --network none --read-only "
        f"-v {rootfs}:{rootfs}:ro --user {test_uid}:{test_uid} "
        f"/bin/sh -c 'touch {rootfs}/.a_next_write_probe' ; echo exit=$?   # expect EROFS",
    ]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="A-NEXT frozen-rootfs write-protection check")
    parser.add_argument("--rootfs", required=True)
    parser.add_argument(
        "--expected-sha", default=common.FROZEN_ROOTFS_SHA256, help="expected canonical sha256"
    )
    parser.add_argument("--test-uid", type=int, default=65534)
    parser.add_argument("--max-entries", type=int, default=200000)
    parser.add_argument("--skip-sha", action="store_true")
    parser.add_argument("--skip-permissions", action="store_true")
    parser.add_argument(
        "--require-ro-mount",
        action="store_true",
        help="fail when the mount point is not read-only",
    )
    parser.add_argument("--emit-commands", action="store_true")
    parser.add_argument("--json-out", default=None)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    rootfs = common.resolved(args.rootfs)
    document: dict = {
        "utc": utc_now(),
        "rootfs": str(rootfs),
        "test_uid": args.test_uid,
        "expected_sha256": args.expected_sha,
    }
    if not rootfs.is_dir():
        document["verdict"] = "PATH_MISSING"
        if args.json_out:
            Path(args.json_out).write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
        json.dump(document, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return EXIT_PATH_MISSING

    exit_code = EXIT_OK
    if not args.skip_sha:
        actual = common.canonical_tree_sha256(rootfs)
        document["canonical_sha256"] = actual
        document["sha_matches_expected"] = actual == args.expected_sha
        if actual != args.expected_sha:
            exit_code = EXIT_SHA_MISMATCH
    document["mount"] = mount_options(rootfs)
    if args.require_ro_mount and not document["mount"].get("read_only", False):
        if exit_code == EXIT_OK:
            exit_code = EXIT_NOT_READ_ONLY_MOUNT
    if not args.skip_permissions:
        document["permissions"] = scan_permissions(rootfs, args.test_uid, args.max_entries)
        if document["permissions"]["violation_count"] > 0 and exit_code == EXIT_OK:
            exit_code = EXIT_PERMISSION_VIOLATION
    if args.emit_commands:
        document["verification_commands"] = verification_commands(rootfs, args.test_uid)
    document["verdict"] = {
        EXIT_OK: "OK",
        EXIT_PERMISSION_VIOLATION: "PERMISSION_VIOLATION",
        EXIT_SHA_MISMATCH: "SHA_MISMATCH",
        EXIT_NOT_READ_ONLY_MOUNT: "NOT_READ_ONLY_MOUNT",
    }[exit_code]
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    json.dump(document, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
