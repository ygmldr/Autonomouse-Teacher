#!/usr/bin/env python3
"""Build the G4-B frozen runtime inventory manifest (host-only, no key/network).

Usage::

    python3.11 -B scripts/g4/build_manifest.py \
        --out artifacts/g4/runtime/manifest.json

The output is deterministic: two builds of unchanged bytes produce identical
``manifest.json`` and identical ``manifest.sha256``.  Wall-clock/observer facts
go into ``provenance`` which is excluded from the digest.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib_g4 as lib  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(lib.G4_RUNTIME / "manifest.json"))
    parser.add_argument("--spec", default=str(lib.SPEC_PATH))
    parser.add_argument("--stage", default=str(lib.STAGE_DEFAULT))
    parser.add_argument("--repo", default=str(lib.REPO_ROOT))
    parser.add_argument("--no-git", action="store_true",
                        help="skip git provenance (synthetic fixtures only)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    out = Path(args.out)
    spec = lib.load_spec(args.spec)
    provenance = {
        "utc": lib.utc_now(),
        "host": "no-key offline host",
        "tool": "scripts/g4/build_manifest.py",
        "argv": ["scripts/g4/build_manifest.py", "--out", str(out),
                 "--spec", args.spec, "--stage", args.stage],
        "invariants": {"real_keys": 0, "real_model_calls": 0,
                       "real_external_http_calls": 0, "container_starts": 0,
                       "podman_pull": 0},
    }
    try:
        document = lib.build_manifest(spec, repo_root=Path(args.repo),
                                      stage_dir=Path(args.stage),
                                      provenance=provenance)
    except lib.G4Error as exc:
        sys.stderr.write(f"MANIFEST_BUILD_FAILED {exc}\n")
        sys.stderr.write(json.dumps(exc.detail, indent=2, sort_keys=True) + "\n")
        return exc.exit_code
    verification = lib.verify_content(document, repo_root=Path(args.repo),
                                      stage_dir=Path(args.stage),
                                      check_git=not args.no_git)
    out.parent.mkdir(parents=True, exist_ok=True)
    written = lib.write_json_atomic(out, document)
    digest = document["digest"]["value"]
    (out.parent / "manifest.sha256").write_text(
        f"{digest}  manifest.json\n", encoding="utf-8")
    summary = {
        "schema": "m0.g4b.manifest.build.v1",
        "utc": lib.utc_now(),
        "manifest_path": str(out),
        "manifest_sha256": written["sha256"],
        "manifest_bytes": written["bytes"],
        "digest": digest,
        "self_verified": verification["ok"],
        "self_problems": verification["problems"][:40],
        "roots": {root_id: _root_summary(section)
                  for root_id, section in sorted(document["inputs"].items())},
        "anchor": {"product_commit": document["anchor"]["product_commit"],
                   "stage": document["anchor"]["stage"],
                   "rootfs": document["anchor"]["rootfs"]["sha256"],
                   "deps": document["anchor"]["deps"]["sha256"],
                   "dsh_runtime": document["anchor"]["dsh_runtime"]["sha256"]},
    }
    lib.write_json_atomic(out.parent / "build-summary.json", summary)
    print(json.dumps({"ok": verification["ok"], "digest": digest,
                      "manifest_sha256": written["sha256"],
                      "problems": verification["problems"][:20],
                      "out": str(out)}, sort_keys=True))
    return lib.EXIT_OK if verification["ok"] else lib.EXIT_DRIFT


def _root_summary(section: dict) -> dict:
    if section.get("kind") in {"worktree_tree", "file_set"}:
        rows = section.get("files") or []
        return {"kind": section["kind"], "files": len(rows),
                "bytes": sum(int(row.get("bytes") or 0) for row in rows),
                "tree": (section.get("tree") or {}).get("sha256")}
    if section.get("kind") == "stage_section":
        rows = section.get("files") or []
        return {"kind": "stage_section", "section": section.get("section"),
                "per_file": len(rows), "stage_manifest_rows":
                    section.get("stage_manifest_rows"),
                "trees": {tree["path"]: tree["sha256"]
                          for tree in section.get("trees") or []}}
    if section.get("kind") == "canonical_tree":
        return {"kind": "canonical_tree", "sha256": section.get("sha256")}
    if section.get("kind") in {"file", "stage_file"}:
        row = section.get("file") or {}
        return {"kind": section["kind"], "path": section.get("path"),
                "sha256": row.get("sha256"), "bytes": row.get("bytes")}
    if section.get("kind") == "tree":
        return {"kind": "tree", "sha256": (section.get("tree") or {}).get("sha256")}
    return {"kind": section.get("kind")}


if __name__ == "__main__":
    raise SystemExit(main())
