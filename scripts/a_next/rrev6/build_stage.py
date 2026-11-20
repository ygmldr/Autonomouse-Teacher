#!/usr/bin/env python3
"""Window wrapper: rebuild the G4-C Stage at HEAD using a writable rootfs copy.

The frozen ``artifacts/security/rootfs`` is never handed to ``podman --rootfs``.
This wrapper copies the canonical staged rootfs to a fresh work directory,
rebinds ``lib_g3d.ROOTFS`` process-locally (so the adapter-build container and
every stage-build hash check use the copy), runs the unchanged G4-C stage
builder, then validates the result with ``validate_stage_g4(base_sha=HEAD,
verify_git=True)``.

Outputs (gitignored): the Stage under ``artifacts/g4/c/stages/stage-<utc>/``
plus ``artifacts/a_next/rrev6/prep/stage-build-<utc>.json`` with the identity
(stage path, manifest/tree/trusted/candidate SHA, rootfs work-copy and frozen
hashes).  Exits non-zero on any identity/drift problem.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts" / "g3d"))
sys.path.insert(0, str(REPO / "scripts" / "g4"))

import lib_g3d as lib3d  # noqa: E402
import lib_g4c as libc  # noqa: E402

ROOTFS_CANON = lib3d.ROOTFS_CANON
DEPS_CANON = lib3d.DEPS_CANON


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def sha256_tree(path: Path) -> str:
    proc = subprocess.run(
        ["tar", "--sort=name", "--mtime=@0", "--owner=0", "--group=0",
         "--numeric-owner", "-cf", "-", "-C", str(path), "."],
        capture_output=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"tar failed for {path}: {proc.stderr[-300:]!r}")
    return hashlib.sha256(proc.stdout).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git(*args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=str(REPO), capture_output=True,
                          text=True)
    return proc.stdout.strip() if proc.returncode == 0 else ""


def containers() -> list[str]:
    proc = subprocess.run(["podman", "ps", "-a", "--format", "{{.Names}}"],
                          capture_output=True, text=True, timeout=60)
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default=None,
                        help="committed implementation SHA (default: HEAD)")
    parser.add_argument("--work-root", default=None,
                        help="rootfs work-copy parent (default artifacts/a_next/rrev6/work)")
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)
    try:
        if os.geteuid() != 0:
            raise SystemExit("BUILD_NEEDS_HOST_ROOT")
        head = git("rev-parse", "HEAD")
        base = args.base or head
        if base != head:
            raise SystemExit("BUILD_BASE_NOT_HEAD")
        dirty = [line for line in git("status", "--porcelain", "-uall").splitlines()
                 if line.strip()]
        if dirty:
            raise SystemExit("BUILD_WORKTREE_DIRTY " + json.dumps(dirty[:5]))
        if containers():
            raise SystemExit("BUILD_CONTAINERS_PRESENT")
        staged_rootfs = REPO / "artifacts" / "security" / "rootfs"
        staged_deps = REPO / "artifacts" / "foundation" / "deps"
        frozen_sha = sha256_tree(staged_rootfs)
        deps_sha = sha256_tree(staged_deps)
        if frozen_sha != ROOTFS_CANON or deps_sha != DEPS_CANON:
            raise SystemExit("BUILD_STAGED_FROZEN_NOT_CANONICAL")
        work_parent = (Path(args.work_root) if args.work_root else
                       REPO / "artifacts" / "a_next" / "rrev6" / "work")
        work_parent.mkdir(parents=True, exist_ok=True)
        work_rootfs = work_parent / f"rootfs-stage-{utc_compact()}"
        started = time.time()
        shutil.copytree(staged_rootfs, work_rootfs, symlinks=True)
        copy_seconds = round(time.time() - started, 2)
        work_sha = sha256_tree(work_rootfs)
        if work_sha != ROOTFS_CANON:
            raise SystemExit("BUILD_ROOTFS_COPY_NOT_CANONICAL")
        # Process-local rebinding: the adapter-build container uses the work copy.
        lib3d.ROOTFS = work_rootfs
        lib3d.DEPS = staged_deps
        stage_root = libc.STAGE_ROOT / f"stage-{utc_compact()}"
        builder = _load_module(REPO / "scripts" / "g4" / "build_stage_c.py",
                               "a_next_build_stage_c")
        builder_argv = ["--base", base, "--stage-root", str(stage_root),
                        "--out-dir", str(libc.G4C_ROOT)]
        rc = builder.main(builder_argv)
        if rc != 0:
            raise SystemExit(f"BUILD_STAGE_FAILED exit={rc}")
        stage = stage_root
        if not (stage / "manifest.json").is_file():
            candidates = sorted(libc.STAGE_ROOT.glob("stage-*"),
                                key=lambda path: path.stat().st_mtime)
            stage = candidates[-1]
        validation = libc.validate_stage_g4(stage, base_sha=head, verify_git=True)
        reference = libc.load_reference(stage)
        work_after = sha256_tree(work_rootfs)
        record = {
            "schema": "m0.a_next.rrev6.stage-build.v1",
            "utc": utc_now(),
            "head": head,
            "base": base,
            "stage_dir": str(stage),
            "stage_tree_sha256": sha256_tree(stage),
            "manifest_sha256": validation.get("manifest_sha256"),
            "base_sha": validation.get("base_sha"),
            "trusted_tree_sha256": validation.get("trusted_tree_sha256"),
            "candidate_tree_sha256": validation.get("candidate_tree_sha256"),
            "trusted_file_count": validation.get("trusted_file_count"),
            "candidate_file_count": validation.get("candidate_file_count"),
            "validation_ok": validation.get("ok"),
            "problems": validation.get("problems", [])[:20],
            "rootfs": {"frozen_staged_sha256": frozen_sha,
                       "expected": ROOTFS_CANON,
                       "work_copy": str(work_rootfs),
                       "work_copy_sha256_before": work_sha,
                       "work_copy_sha256_after": work_after,
                       "work_copy_copy_seconds": copy_seconds},
            "deps": {"sha256": deps_sha, "expected": DEPS_CANON,
                     "path": str(staged_deps)},
            "adapter_build": reference.get("adapter_build"),
            "dsh": reference.get("dsh"),
            "reference_rootfs": reference.get("rootfs"),
            "containers_after": containers(),
            "note": ("rootfs used only as a writable work copy; frozen staged "
                     "copy is the hash-verified recovery copy from the "
                     "2026-11-20 artifacts event"),
        }
        out = (Path(args.out) if args.out else
               REPO / "artifacts" / "a_next" / "rrev6" / "prep" /
               f"stage-build-{utc_compact()}.json")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
        print(json.dumps({"ok": validation.get("ok"),
                          "stage": str(stage),
                          "record": str(out),
                          "manifest_sha256": record["manifest_sha256"],
                          "stage_tree_sha256": record["stage_tree_sha256"],
                          "rootfs_work_copy": str(work_rootfs)}, sort_keys=True))
        return 0 if validation.get("ok") else lib3d.EXIT_EVIDENCE_INTEGRITY
    except SystemExit:
        raise
    except BaseException as exc:  # noqa: BLE001 - window runner reports, no traceback
        sys.stderr.write(f"BUILD_STAGE_FAILED {type(exc).__name__}: {exc}\n")
        return lib3d.EXIT_CASE_FAILED


if __name__ == "__main__":
    raise SystemExit(main())
