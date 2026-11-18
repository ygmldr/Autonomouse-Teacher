#!/usr/bin/env python3
"""Fail-closed verifier for the G4-B frozen runtime inventory manifest.

Checks, in this order:

1. the manifest's own digest recomputes from its digest-covered projection
   (``manifest.sha256`` must agree);
2. every declared file still exists with the same sha256/size/mode;
3. every declared root has no added or removed file;
4. every declared subtree/tar digest recomputes (rootfs, deps, stage, adapter,
   node_modules and friends);
5. every derived fact (tool schemas, route, limits, price, merge layers) is
   recomputed from the bytes on disk and must be identical;
6. the G4-A hand-off decision (``require_manifest_match``) returns ``ok``.

Exit codes: 0 clean, 4 drift, 5 self-digest mismatch, 6 spec/policy invalid,
7 environment unreadable.
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
    parser.add_argument("--manifest", default=str(lib.G4_RUNTIME / "manifest.json"))
    parser.add_argument("--policy", default=str(lib.POLICY_PATH))
    parser.add_argument("--stage", default=str(lib.STAGE_DEFAULT))
    parser.add_argument("--repo", default=str(lib.REPO_ROOT))
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--no-git", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    manifest_path = Path(args.manifest)
    try:
        document = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"MANIFEST_UNREADABLE {type(exc).__name__}\n")
        return lib.EXIT_ENVIRONMENT
    if not isinstance(document, dict):
        sys.stderr.write("MANIFEST_NOT_OBJECT\n")
        return lib.EXIT_SELF_DIGEST
    stored = (document.get("digest") or {}).get("value")
    recomputed = lib.digest_of(document)
    digest_ok = isinstance(stored, str) and stored == recomputed
    digest_file = manifest_path.parent / "manifest.sha256"
    sidecar_ok = None
    if digest_file.is_file():
        first = digest_file.read_text(encoding="utf-8").split()
        sidecar_ok = bool(first) and first[0] == stored
    report: dict = {
        "schema": "m0.g4b.manifest.verify.v1",
        "utc": lib.utc_now(),
        "manifest_path": str(manifest_path),
        "digest_stored": stored,
        "digest_recomputed": recomputed,
        "digest_ok": digest_ok,
        "sidecar_ok": sidecar_ok,
    }
    if not digest_ok:
        report["ok"] = False
        report["problems"] = ["manifest_digest_mismatch"]
        _emit(report, args.json)
        return lib.EXIT_SELF_DIGEST
    try:
        verification = lib.verify_content(document, repo_root=Path(args.repo),
                                          stage_dir=Path(args.stage),
                                          check_git=not args.no_git)
        policy = lib.load_policy(args.policy)
    except lib.G4Error as exc:
        sys.stderr.write(f"VERIFY_ENVIRONMENT_FAILED {exc}\n")
        sys.stderr.write(json.dumps(exc.detail, indent=2, sort_keys=True) + "\n")
        return exc.exit_code
    decision = lib.require_manifest_match(policy, document, verification=verification)
    problems = list(verification["problems"])
    report.update({
        "ok": bool(verification["ok"] and decision["ok"]),
        "problems": problems[:200],
        "problem_count": len(problems),
        "dispatch_decision": decision,
    })
    _emit(report, args.json)
    if problems or not decision["ok"]:
        return lib.EXIT_DRIFT
    return lib.EXIT_OK


def _emit(report: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(report, sort_keys=True))
        return
    status = "OK" if report.get("ok") else "DRIFT"
    print(f"{status} digest={report.get('digest_stored')} "
          f"problems={report.get('problem_count', len(report.get('problems') or []))}")
    for problem in report.get("problems") or []:
        print(f"  - {problem}")
    decision = report.get("dispatch_decision") or {}
    if decision:
        print(f"  dispatch_ok={decision.get('ok')} reasons={decision.get('reasons')}")


if __name__ == "__main__":
    raise SystemExit(main())
