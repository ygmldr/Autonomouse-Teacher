#!/usr/bin/env python3
"""Build the G4-C trusted/candidate stage from a committed G4 implementation SHA.

The G3-D frozen builder requires ``git diff <PRODUCT_BASE> -- src`` to be empty
and hardcodes ``base_sha=4bd4803`` in the manifest.  G4-A/C authorised source
changes make that false by construction, so this G4-C builder calls the same
G3-D assembly code with the *module-level* ``PRODUCT_BASE``/``G3D_ROOT``
rebound (no file under ``scripts/g3d`` is edited) and writes all build output
under ``artifacts/g4/c``.

Provenance: ``base_sha``/``head_at_build`` are the current committed G4 HEAD and
every trusted ``src/`` file is a ``git_blob`` row verified against that commit.
The G4-C launcher re-validates the manifest with its own preflight
(``lib_g4c.validate_stage_g4``) and binds the actual loaded modules.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "g3d"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib_g3d as lib3d  # noqa: E402
import build_stage as g3d_build  # noqa: E402
import lib_g4 as lib  # noqa: E402
import lib_g4c as libc  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default=None,
                        help="committed implementation SHA (default: HEAD)")
    parser.add_argument("--stage-root", default=None)
    parser.add_argument("--out-dir", default=str(libc.G4C_ROOT))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if os.geteuid() != 0:
        sys.stderr.write("G4C_BUILD_NEEDS_HOST_ROOT\n")
        return lib3d.EXIT_BLOCKED_ENVIRONMENT
    head = lib3d.git_text("rev-parse", "HEAD")
    base = args.base or head
    if lib3d.git_text("rev-parse", f"{base}^{{commit}}") != base:
        sys.stderr.write("G4C_BASE_NOT_A_COMMIT\n")
        return lib3d.EXIT_PREFLIGHT_IDENTITY
    if base != head:
        sys.stderr.write("G4C_BASE_NOT_HEAD\n")
        return lib3d.EXIT_PREFLIGHT_IDENTITY
    status = lib3d.git_text("status", "--porcelain=v1", "-uall")
    dirty = [line for line in status.splitlines() if line.strip()]
    disallowed = [line for line in dirty
                  if not line[3:].startswith("docs/")]
    if disallowed:
        sys.stderr.write("G4C_WORKTREE_DIRTY " + json.dumps(disallowed[:10]) + "\n")
        return lib3d.EXIT_PREFLIGHT_IDENTITY

    stage_root = Path(args.stage_root) if args.stage_root else None
    if stage_root is None:
        stamp = lib3d.utc_compact()
        stage_root = libc.STAGE_ROOT / f"stage-{stamp}"
    stage_root = stage_root.resolve()
    if not str(stage_root).startswith(str(libc.G4C_ROOT.resolve()) + os.sep):
        sys.stderr.write("G4C_STAGE_OUTSIDE_G4C_ROOT\n")
        return lib3d.EXIT_STAGE_INVALID

    # Process-local provenance rebinding; no repository file is modified.
    lib3d.PRODUCT_BASE = base
    lib3d.G3D_ROOT = libc.BUILD_ROOT
    libc.G4C_ROOT.mkdir(parents=True, exist_ok=True)
    lib3d.G3D_ROOT.mkdir(parents=True, exist_ok=True)
    stage = g3d_build.build_stage(base, stage_root=stage_root)

    validation = libc.validate_stage_g4(stage, base_sha=base, verify_git=True)
    if not validation["ok"]:
        sys.stderr.write("G4C_STAGE_INVALID " + json.dumps(
            validation["problems"][:20]) + "\n")
        return lib3d.EXIT_STAGE_INVALID
    reference = libc.load_reference(stage)
    external = libc.stage_external_inputs(stage)
    closure = libc.closure_for(libc.REPO, external=external)
    bindings = libc.expected_bindings(closure)
    out_dir = Path(args.out_dir)
    summary = {
        "schema": "m0.g4c.stage-summary.v1",
        "utc": libc.utc(),
        "stage_dir": str(stage),
        "base_sha": base,
        "head": head,
        "manifest_sha256": validation["manifest_sha256"],
        "trusted_tree_sha256": validation["trusted_tree_sha256"],
        "candidate_tree_sha256": validation["candidate_tree_sha256"],
        "stage_tree_sha256": lib3d.sha256_tree(stage),
        "rootfs_sha256": reference["rootfs"]["sha256"],
        "deps_sha256": reference["deps"]["sha256"],
        "dsh_runtime_sha256": reference["dsh"]["runtime_sha256"],
        "dsh_sdk_version": reference["dsh"]["sdk_version"],
        "adapter_built_js_sha256": reference["adapter_build"]["built_js_sha256"],
        "component_digests": closure["component_digests"],
        "bindings": bindings,
        "synthetic": True,
        "real_model_calls": 0,
        "real_external_http_calls": 0,
        "has_real_key": False,
    }
    written = lib.write_json_atomic(out_dir / "stage-summary.json", summary)
    sys.stderr.write("G4C_STAGE_READY " + json.dumps(
        {"stage": str(stage), "base": base,
         "manifest_sha256": validation["manifest_sha256"],
         "summary_sha256": written["sha256"]}, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return lib3d.EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
