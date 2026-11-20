"""Build the A-NEXT review packet v3 (strict full-tree inventory, no key).

New identity: ``artifacts/review-packet-a-next-v3-<impl_sha>``.  Never reuses or
overwrites the frozen G4-R v1/v2 packet paths.

The builder:
1. validates identity inputs (impl SHA 40-hex; optional git verification;
   content-SHA attestation separated from impl SHA);
2. strictly inventories the staging payload (regular files only; refuses
   symlinks, hardlinks, special files, sidecars, unsafe paths);
3. snapshots the frozen rootfs canonical SHA (T0) when ``--frozen-rootfs`` is
   given, copies the payload, writes README/manifest/hashes, and snapshots T1;
   T0 != T1 or T0 != expected => refuse (STOP);
4. self-verifies the temporary packet with the v3 verifier, then atomically
   renames it to the new output directory.

Incident disclosure (INCIDENT_20261121, v1 packet bytes LOST) is embedded in the
manifest and README; the builder never claims global NO_DRIFT or completeness.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))
import packet_v3_common as common  # noqa: E402

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_BUILD_ERROR = 40

PHASE_FINAL = "final"
PHASE_TOOLING = "phase-1-tooling"


def build_readme(manifest: dict) -> str:
    identity = manifest["identity"]
    frozen = manifest["frozen_identity"]
    incident = manifest["environment_incident"]
    lines = [
        "# A-NEXT review packet v3",
        "",
        f"- Packet: `{manifest['packet']['name']}` (schema `{common.SCHEMA}`)",
        f"- Frozen impl git commit: `{identity['impl_sha']}`"
        f" (git verified: `{identity['git_commit_verified']}`)",
        f"- Payload content sha256 (payload-only digest): `{identity['content_sha256']}`",
        "- Identity separation: ``impl_sha`` is the frozen git commit; "
        "``content_sha256`` is the payload content digest. They are distinct values.",
        "",
        "## Layers",
        "",
        f"- `payload/` — {manifest['inventory']['payload_count']} regular files, mode 0444",
        f"- `hashes.sha256` — {manifest['layers']['hashes']['entry_count']} entries "
        "(payload + README.md + manifest.json; self excluded)",
        f"- `manifest.json` — schema `{manifest['layers']['manifest']['schema']}`",
        f"- payload tree sha256: `{manifest['layers']['payload']['tree_sha256']}`",
        f"- payload content sha256: `{manifest['layers']['payload']['content_sha256']}`",
        "",
        "## Frozen declaration (T0/T1)",
        "",
        f"- frozen snapshot provided: `{frozen['rootfs_snapshot']}`",
        f"- expected frozen rootfs sha256: `{frozen['rootfs_sha256_expected']}`",
        f"- rootfs canonical T0: `{frozen['rootfs_canonical_t0']}`",
        f"- rootfs canonical T1: `{frozen['rootfs_canonical_t1']}`",
        f"- T0 == T1: `{frozen['t0_t1_equal']}`",
        f"- deps sha256: `{frozen['deps_sha256']}`",
        f"- DSH runtime sha256: `{frozen['dsh_runtime_sha256']}`",
        f"- Stage manifest sha256: `{frozen['stage_manifest_sha256']}`",
        "",
        "## ENVIRONMENT INCIDENT — INCIDENT_20261121 (MANDATORY DISCLOSURE)",
        "",
        f"- Reported UTC: `{incident['reported_utc']}`",
        f"- Summary: {incident['summary']}",
        f"- Deleted scope: {incident['deleted_scope']}",
        f"- Restoration source tar: `{incident['restoration']['source_backup_tar']}`",
        f"- Restoration tar sha256: `{incident['restoration']['source_backup_tar_sha256']}`",
        f"- Restored rootfs sha256: `{incident['restoration']['restored_rootfs_sha256']}`",
        f"- Restored deps sha256: `{incident['restoration']['restored_deps_sha256']}`",
        f"- Tar re-verified in this run: `{incident['restoration']['tar_verified_in_this_run']}`",
        f"- **v1 packet: `{incident['lost']['v1_packet']['status']}`** "
        f"(former path: `{incident['lost']['v1_packet']['path_before_incident']}`)",
        f"- v2 packet: `{incident['historical']['v2_packet']['status']}` "
        f"(bytes not modified by v3)",
        f"- Claims allowed: global_no_drift=`{incident['claims_allowed']['global_no_drift']}`, "
        f"evidence_completeness=`{incident['claims_allowed']['evidence_completeness']}`",
        "- NOT allowed: claiming full evidence completeness or continuous/global NO_DRIFT. "
        "v1 packet original bytes are LOST and cannot be independently re-verified.",
        "",
        "## Verification",
        "",
        "```bash",
        f"python scripts/a_next/verify_packet_v3.py --packet-root {manifest['packet']['name']}",
        "```",
        "",
        f"- Packet status: `{manifest['status']}`",
        f"- Real model calls: `{manifest['no_key']['real_model_calls']}`; "
        f"external network calls: `{manifest['no_key']['external_network_calls']}`; "
        f"provider keys seen: `{manifest['no_key']['provider_keys_seen']}`; "
        f"LiveGate: `{manifest['no_key']['live_gate']}`",
    ]
    return "\n".join(lines) + "\n"


def build_manifest(
    *,
    packet_name: str,
    impl_sha: str,
    content_sha256: str,
    builder_sha256: str,
    payload: dict[str, dict],
    frozen: dict,
    phase: str,
    incident_tar_verified: bool,
    stage_manifest: str | None,
) -> dict:
    incident = json.loads(json.dumps(common.INCIDENT))
    incident["restoration"]["tar_verified_in_this_run"] = incident_tar_verified
    file_modes = {rel: record["mode"] for rel, record in payload.items()}
    file_modes[common.MANIFEST] = oct(common.FILE_MODE)
    file_modes[common.README] = oct(common.FILE_MODE)
    return {
        "schema": common.SCHEMA,
        "packet": {
            "name": packet_name,
            "format": "a-next-v3",
            "identity_root_prefix": common.IDENTITY_ROOT_PREFIX,
            "phase": phase,
            "directory_policy": (
                "new identity only; never reuse/overwrite review-packet-g4f (v1, LOST) "
                "or review-packet-g4r (v2, historical)"
            ),
        },
        "status": "CANDIDATE_PENDING_LEAD_FREEZE",
        "identity": {
            "impl_sha": impl_sha,
            "impl_sha_kind": "frozen_git_commit_40hex",
            "git_commit_verified": frozen.get("git_commit_verified", False),
            "content_sha256": content_sha256,
            "content_sha256_kind": "payload_only_content_digest",
            "identity_separation": "impl_sha != content_sha256 by construction (different identity types)",
            "builder_sha256": builder_sha256,
        },
        "frozen_identity": frozen,
        "layers": {
            "payload": {
                "root": common.PAYLOAD_DIR + "/",
                "file_count": len(payload),
                "tree_sha256": common.payload_tree_sha256(payload),
                "content_sha256": common.payload_content_sha256(payload),
            },
            "hashes": {
                "path": common.HASHES,
                "entry_count": len(payload) + 2,
                "coverage": "payload/** + README.md + manifest.json (self excluded)",
            },
            "manifest": {
                "path": common.MANIFEST,
                "schema": common.SCHEMA,
            },
        },
        "inventory": {
            "payload_files": payload,
            "payload_count": len(payload),
            "content_sha256": content_sha256,
            "payload_tree_sha256": common.payload_tree_sha256(payload),
            "metadata_files": [common.README],
            "file_modes": dict(sorted(file_modes.items())),
            "hash_manifest_entry_count": len(payload) + 2,
            "total_regular_files": len(payload) + 3,
            "stage_manifest": stage_manifest,
        },
        "environment_incident": incident,
        "no_key": {
            "real_model_calls": 0,
            "external_network_calls": 0,
            "provider_keys_seen": 0,
            "live_gate": "BLOCKED",
        },
        "limitations": [
            "Packet v3 is a new identity; review-packet-g4f (v1) is LOST and not recoverable "
            "from this packet; review-packet-g4r (v2) is a historical reference only.",
            "INCIDENT_20261121 disclosure is mandatory: artifacts were deleted and restored from a "
            "hash-verified backup; no global NO_DRIFT or completeness claim is made.",
            "Frozen rootfs/deps identities are declared, not re-measured by the verifier; "
            "T0/T1 applies only to the build window when a frozen snapshot is provided.",
            "Phase-1 tooling packets may be built without a frozen snapshot; the final packet "
            "must be built with the Lead-frozen integration SHA and frozen identities.",
        ],
    }


def write_packet(
    out_dir: Path,
    staging: Path,
    payload: dict[str, dict],
    packet_name: str,
    *,
    impl_sha: str,
    content_sha256: str,
    phase: str,
    frozen: dict,
    incident_tar_verified: bool,
    stage_manifest: str | None,
) -> dict:
    """Copy payload, then write manifest (final), README and hashes layers."""
    builder_sha256 = common.sha256_file(__file__)
    payload_root = out_dir / common.PAYLOAD_DIR
    payload_root.mkdir(parents=True)
    for relpath, record in payload.items():
        source = staging / relpath
        target = out_dir / common.PAYLOAD_DIR / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        if common.sha256_file(target) != record["sha256"]:
            raise common.PacketError("COPY_HASH_MISMATCH", relpath)
        os.chmod(target, common.FILE_MODE)
    manifest = build_manifest(
        packet_name=packet_name,
        impl_sha=impl_sha,
        content_sha256=content_sha256,
        builder_sha256=builder_sha256,
        payload=payload,
        frozen=frozen,
        phase=phase,
        incident_tar_verified=incident_tar_verified,
        stage_manifest=stage_manifest,
    )
    readme_path = out_dir / common.README
    readme_path.write_bytes(build_readme(manifest).encode("utf-8"))
    os.chmod(readme_path, common.FILE_MODE)
    manifest_path = out_dir / common.MANIFEST
    manifest_path.write_bytes(common.canonical_json_bytes(manifest))
    os.chmod(manifest_path, common.FILE_MODE)
    hash_entries: dict[str, str] = {}
    for relpath in sorted(payload):
        hash_entries[common.PAYLOAD_DIR + "/" + relpath] = payload[relpath]["sha256"]
    hash_entries[common.README] = common.sha256_file(readme_path)
    hash_entries[common.MANIFEST] = common.sha256_file(manifest_path)
    hashes_path = out_dir / common.HASHES
    lines = [f"{digest}  {relpath}\n" for relpath, digest in sorted(hash_entries.items())]
    hashes_path.write_bytes("".join(lines).encode("utf-8"))
    os.chmod(hashes_path, common.FILE_MODE)
    for path in sorted((p for p in out_dir.rglob("*") if p.is_dir()), key=lambda p: -len(p.parts)):
        os.chmod(path, common.DIR_MODE)
    return manifest


def _git_verify(repo: str, impl_sha: str) -> bool:
    proc = common.subprocess.run(
        ["git", "-C", repo, "cat-file", "-e", f"{impl_sha}^{{commit}}"],
        stdout=common.subprocess.PIPE,
        stderr=common.subprocess.PIPE,
    )
    return proc.returncode == 0


def build(args: argparse.Namespace) -> int:
    staging = Path(args.staging_dir).resolve()
    if not common.IMPL_SHA_RE.match(args.impl_sha):
        raise common.PacketError("IMPL_SHA_INVALID", args.impl_sha)
    if args.content_sha is not None and not common.SHA256_RE.match(args.content_sha):
        raise common.PacketError("CONTENT_SHA_INVALID", args.content_sha)
    git_verified = False
    if args.repo and not args.no_git_check:
        git_verified = _git_verify(str(Path(args.repo).resolve()), args.impl_sha)
        if not git_verified:
            raise common.PacketError("IMPL_SHA_NOT_IN_REPO", args.impl_sha)

    frozen: dict = {
        "rootfs_snapshot": "NOT_PROVIDED",
        "rootfs_sha256_expected": common.FROZEN_ROOTFS_SHA256,
        "rootfs_canonical_t0": None,
        "rootfs_canonical_t1": None,
        "t0_t1_equal": None,
        "deps_sha256": args.deps_sha or common.FROZEN_DEPS_SHA256,
        "dsh_runtime_sha256": common.FROZEN_DSH_RUNTIME_SHA256,
        "stage_manifest_sha256": args.stage_manifest_sha or None,
        "git_commit_verified": git_verified,
    }
    frozen_rootfs = Path(args.frozen_rootfs).resolve() if args.frozen_rootfs else None
    if frozen_rootfs is not None:
        if not frozen_rootfs.is_dir():
            raise common.PacketError("FROZEN_ROOTFS_MISSING", str(frozen_rootfs))
        expected = args.expected_rootfs_sha or common.FROZEN_ROOTFS_SHA256
        if not common.SHA256_RE.match(expected):
            raise common.PacketError("ROOTFS_SHA_INVALID", expected)
        t0 = common.canonical_tree_sha256(frozen_rootfs)
        if t0 != expected:
            raise common.PacketError("ROOTFS_T0_MISMATCH", f"{t0} != {expected}")
        frozen.update(
            {
                "rootfs_snapshot": "PROVIDED",
                "rootfs_sha256_expected": expected,
                "rootfs_canonical_t0": t0,
            }
        )

    incident_tar_verified = False
    if args.incident_source_tar:
        tar_path = Path(args.incident_source_tar).resolve()
        if not tar_path.is_file():
            raise common.PacketError("INCIDENT_TAR_MISSING", str(tar_path))
        digest = common.sha256_file(tar_path)
        if digest != common.BACKUP_TAR_SHA256:
            raise common.PacketError("INCIDENT_TAR_SHA_MISMATCH", f"{digest} != {common.BACKUP_TAR_SHA256}")
        incident_tar_verified = True

    payload = common.scan_strict_tree(staging)
    content_sha256 = common.payload_content_sha256(payload)
    if args.content_sha is not None and args.content_sha != content_sha256:
        raise common.PacketError("CONTENT_SHA_ATTESTATION_MISMATCH", content_sha256)

    out_dir = (
        Path(args.out_dir).resolve()
        if args.out_dir
        else Path(args.repo or ".").resolve() / "artifacts" / (common.IDENTITY_ROOT_PREFIX + args.impl_sha)
    )
    if not out_dir.name.startswith(common.IDENTITY_ROOT_PREFIX) or args.impl_sha not in out_dir.name:
        raise common.PacketError("OUT_DIR_NOT_NEW_IDENTITY", str(out_dir))
    if out_dir.exists() or out_dir.is_symlink():
        raise common.PacketError("OUT_DIR_EXISTS", str(out_dir))
    out_dir.parent.mkdir(parents=True, exist_ok=True)

    tmp_dir = out_dir.parent / f".{out_dir.name}.build-{os.getpid()}"
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    phase = PHASE_FINAL if frozen_rootfs is not None else PHASE_TOOLING
    try:
        tmp_dir.mkdir()
        if frozen_rootfs is not None:
            t1 = common.canonical_tree_sha256(frozen_rootfs)
            if t1 != frozen["rootfs_canonical_t0"]:
                raise common.PacketError(
                    "ROOTFS_T0_T1_DRIFT", f"T0={frozen['rootfs_canonical_t0']} T1={t1}"
                )
            frozen["rootfs_canonical_t1"] = t1
            frozen["t0_t1_equal"] = True
        manifest = write_packet(
            tmp_dir,
            staging,
            payload,
            packet_name=out_dir.name,
            impl_sha=args.impl_sha,
            content_sha256=content_sha256,
            phase=phase,
            frozen=frozen,
            incident_tar_verified=incident_tar_verified,
            stage_manifest=args.stage_manifest_sha,
        )
        # builder-side strict self-check before publishing the new identity
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import verify_packet_v3  # noqa: E402

        result = verify_packet_v3.verify(tmp_dir, allow_phase1=True, allow_build_tmp_name=True)
        if result["verdict"] != "PASS":
            raise common.PacketError("SELF_CHECK_FAILED", json.dumps(result["failures"])[:600])
        os.replace(str(tmp_dir), str(out_dir))
        final = verify_packet_v3.verify(out_dir, allow_phase1=True)
        if final["verdict"] != "PASS":
            raise common.PacketError("FINAL_VERIFY_FAILED", json.dumps(final["failures"])[:600])
    except Exception:
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)
        raise

    summary = {
        "schema": common.REPORT_SCHEMA,
        "packet": out_dir.name,
        "out_dir": str(out_dir),
        "impl_sha": args.impl_sha,
        "content_sha256": content_sha256,
        "phase": phase,
        "manifest_sha256": common.sha256_file(out_dir / common.MANIFEST),
        "hashes_sha256": common.sha256_file(out_dir / common.HASHES),
        "payload_tree_sha256": manifest["layers"]["payload"]["tree_sha256"],
        "payload_count": len(payload),
        "hash_manifest_entry_count": len(payload) + 2,
        "total_regular_files": len(payload) + 3,
        "frozen_rootfs_t0": frozen["rootfs_canonical_t0"],
        "frozen_rootfs_t1": frozen["rootfs_canonical_t1"],
        "t0_t1_equal": frozen["t0_t1_equal"],
        "git_commit_verified": git_verified,
        "incident_tar_verified_in_run": incident_tar_verified,
        "verdict": "PASS",
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build A-NEXT review packet v3")
    parser.add_argument("--staging-dir", required=True, help="payload staging tree")
    parser.add_argument("--impl-sha", required=True, help="frozen git commit (40 hex)")
    parser.add_argument(
        "--content-sha",
        default=None,
        help="optional expected payload content sha256 attestation (64 hex)",
    )
    parser.add_argument("--repo", default=None, help="git repo to verify --impl-sha")
    parser.add_argument("--no-git-check", action="store_true")
    parser.add_argument("--out-dir", default=None, help="new v3 identity directory")
    parser.add_argument("--frozen-rootfs", default=None)
    parser.add_argument("--expected-rootfs-sha", default=None)
    parser.add_argument("--deps-sha", default=None)
    parser.add_argument("--stage-manifest-sha", default=None)
    parser.add_argument("--incident-source-tar", default=None)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else EXIT_USAGE
    try:
        return build(args)
    except common.PacketError as exc:
        print(json.dumps({"verdict": "BUILD_REFUSED", "code": exc.code, "detail": exc.detail}))
        return EXIT_BUILD_ERROR


if __name__ == "__main__":
    sys.exit(main())
