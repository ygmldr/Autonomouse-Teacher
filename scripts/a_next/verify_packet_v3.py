"""Verify the A-NEXT review packet v3 with strict full-tree inventory.

Rejections (non-zero exit, machine-readable reason codes):
* unlisted/extra file or directory, missing payload file -> EXTRA_ENTRY / MISSING_ENTRY (45)
* sidecar/hidden junk names -> SIDECAR_REFUSED (46)
* symlink / hardlink / special file -> SYMLINK_REFUSED / HARDLINK_REFUSED / SPECIAL_REFUSED (47)
* file or directory mode differs -> MODE_MISMATCH (48)
* payload/manifest/hashes hash mismatch -> HASH_MISMATCH (41)
* payload tree/content sha mismatch -> PAYLOAD_TREE_MISMATCH / CONTENT_SHA_MISMATCH (42)
* schema/identity/manifest tamper (incl duplicate JSON keys) -> *_ (43)
* frozen declaration or incident disclosure invalid/prohibited claims -> (44)

The verifier is read-only and never writes to the packet or to any frozen tree.
"""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from pathlib import Path
from typing import Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))
import packet_v3_common as common  # noqa: E402

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_HASH = 41
EXIT_CONTENT = 42
EXIT_MANIFEST = 43
EXIT_FROZEN_INCIDENT = 44
EXIT_INVENTORY = 45
EXIT_SIDECAR = 46
EXIT_UNSAFE = 47
EXIT_MODE = 48

EXIT_PRIORITY = [
    EXIT_MANIFEST,
    EXIT_FROZEN_INCIDENT,
    EXIT_SIDECAR,
    EXIT_UNSAFE,
    EXIT_MODE,
    EXIT_INVENTORY,
    EXIT_CONTENT,
    EXIT_HASH,
]

ALLOWED_STATUS = {
    "CANDIDATE_PENDING_LEAD_FREEZE",
    "PENDING_INDEPENDENT_REVIEW",
    "FROZEN",
}


class Result:
    def __init__(self, packet_root: Path):
        self.packet_root = packet_root
        self.failures: list[dict] = []
        self.checked = 0

    def fail(self, code: str, detail: str = "") -> None:
        self.failures.append({"code": code, "detail": detail})

    @property
    def exit_code(self) -> int:
        codes = {failure_exit(failure["code"]) for failure in self.failures}
        for candidate in EXIT_PRIORITY:
            if candidate in codes:
                return candidate
        return EXIT_OK

    def document(self) -> dict:
        return {
            "schema": common.VERIFICATION_SCHEMA,
            "packet_root": str(self.packet_root),
            "utc": common.utc_now(),
            "verdict": "PASS" if not self.failures else "FAIL",
            "checks": self.checked,
            "failures": self.failures,
            "reasons": sorted({failure["code"] for failure in self.failures}),
            "exit_code": self.exit_code,
        }


def failure_exit(code: str) -> int:
    if code.startswith(("SYMLINK", "HARDLINK", "SPECIAL", "UNSAFE")):
        return EXIT_UNSAFE
    if code in ("EXTRA_ENTRY", "MISSING_ENTRY", "EMPTY_DIRECTORY"):
        return EXIT_INVENTORY
    if code == "SIDECAR_REFUSED":
        return EXIT_SIDECAR
    if code == "MODE_MISMATCH":
        return EXIT_MODE
    if code in ("HASH_MISMATCH", "HASHES_COVERAGE_MISMATCH", "HASHES_MALFORMED", "HASHES_DUPLICATE"):
        return EXIT_HASH
    if code in ("PAYLOAD_TREE_MISMATCH", "CONTENT_SHA_MISMATCH",
                "CONTENT_SHA_MISMATCH_EXPECTED"):
        return EXIT_CONTENT
    if code.startswith(("FROZEN", "INCIDENT", "CLAIM", "V1_CLAIM")):
        return EXIT_FROZEN_INCIDENT
    return EXIT_MANIFEST


def scan_packet_tree(root: Path, result: Result) -> tuple[set[str], set[str], dict[str, dict]]:
    """Read-only strict scan. Returns (files, dirs, records)."""
    files: set[str] = set()
    dirs: set[str] = {"."}
    records: dict[str, dict] = {}
    stack: list[Path] = [root]
    while stack:
        current = stack.pop()
        try:
            entries = list(os.scandir(current))
        except OSError as exc:  # pragma: no cover - defensive
            result.fail("SCAN_FAILED", f"{current}: {exc}")
            continue
        for entry in entries:
            path = Path(entry.path)
            relpath = str(path.relative_to(root)).replace(os.sep, "/")
            try:
                common.validate_relative_path(relpath)
            except common.PacketError:
                result.fail("UNSAFE_PATH", relpath)
                continue
            info = os.lstat(path)
            result.checked += 1
            if stat.S_ISLNK(info.st_mode):
                result.fail("SYMLINK_REFUSED", relpath)
                continue
            if stat.S_ISDIR(info.st_mode):
                dirs.add(relpath)
                stack.append(path)
                continue
            if not stat.S_ISREG(info.st_mode):
                result.fail("SPECIAL_REFUSED", relpath)
                continue
            if info.st_nlink != 1:
                result.fail("HARDLINK_REFUSED", f"{relpath} nlink={info.st_nlink}")
                continue
            if common.is_sidecar_name(path.name):
                result.fail("SIDECAR_REFUSED", relpath)
                continue
            files.add(relpath)
            records[relpath] = {
                "sha256": common.sha256_file(path),
                "bytes": info.st_size,
                "mode": oct(stat.S_IMODE(info.st_mode)),
            }
    return files, dirs, records


def _require(condition: bool, result: Result, code: str, detail: str = "") -> bool:
    if not condition:
        result.fail(code, detail)
    return condition


def verify_frozen(manifest: dict, result: Result, allow_phase1: bool) -> None:
    frozen = manifest.get("frozen_identity")
    if not isinstance(frozen, dict):
        result.fail("FROZEN_DECLARATION_MISSING")
        return
    packet = manifest.get("packet") if isinstance(manifest.get("packet"), dict) else {}
    snapshot = frozen.get("rootfs_snapshot")
    if snapshot == "NOT_PROVIDED":
        if not (allow_phase1 and packet.get("phase") == "phase-1-tooling"):
            result.fail(
                "FROZEN_SNAPSHOT_REQUIRED",
                "phase-1-tooling packet without frozen T0/T1 (use --allow-phase1 for tooling packets)",
            )
        return
    _require(snapshot == "PROVIDED", result, "FROZEN_SNAPSHOT_INVALID", str(snapshot))
    for field in ("rootfs_sha256_expected", "rootfs_canonical_t0", "rootfs_canonical_t1"):
        value = frozen.get(field)
        _require(
            isinstance(value, str) and bool(common.SHA256_RE.match(value)),
            result,
            "FROZEN_SHA_INVALID",
            field,
        )
    if frozen.get("rootfs_canonical_t0") != frozen.get("rootfs_canonical_t1"):
        result.fail(
            "ROOTFS_T0_T1_DRIFT",
            f"T0={frozen.get('rootfs_canonical_t0')} T1={frozen.get('rootfs_canonical_t1')}",
        )
    if frozen.get("t0_t1_equal") is not True:
        result.fail("ROOTFS_T0_T1_NOT_EQUAL")
    if frozen.get("rootfs_canonical_t0") != frozen.get("rootfs_sha256_expected"):
        result.fail("ROOTFS_T0_EXPECTED_MISMATCH")
    for field in ("deps_sha256", "dsh_runtime_sha256"):
        value = frozen.get(field)
        if value is not None:
            _require(
                isinstance(value, str) and bool(common.SHA256_RE.match(value)),
                result,
                "FROZEN_SHA_INVALID",
                field,
            )


def verify_incident(manifest: dict, result: Result) -> None:
    incident = manifest.get("environment_incident")
    if not isinstance(incident, dict):
        result.fail("INCIDENT_DISCLOSURE_MISSING")
        return
    _require(incident.get("id") == "INCIDENT_20261121", result, "INCIDENT_ID_INVALID")
    restoration = incident.get("restoration")
    if not isinstance(restoration, dict):
        result.fail("INCIDENT_RESTORATION_MISSING")
        restoration = {}
    _require(
        restoration.get("source_backup_tar_sha256") == common.BACKUP_TAR_SHA256,
        result,
        "INCIDENT_BACKUP_TAR_SHA_MISMATCH",
    )
    _require(
        restoration.get("restored_rootfs_sha256") == common.FROZEN_ROOTFS_SHA256,
        result,
        "INCIDENT_ROOTFS_RESTORE_SHA_MISMATCH",
    )
    _require(
        restoration.get("restored_deps_sha256") == common.FROZEN_DEPS_SHA256,
        result,
        "INCIDENT_DEPS_RESTORE_SHA_MISMATCH",
    )
    lost = incident.get("lost")
    if not isinstance(lost, dict) or not isinstance(lost.get("v1_packet"), dict):
        result.fail("INCIDENT_V1_LOSS_UNDISCLOSED")
    else:
        v1 = lost["v1_packet"]
        _require(
            v1.get("status") == "LOST_ORIGINAL_BYTES_UNVERIFIABLE",
            result,
            "V1_CLAIM_INVALID",
            str(v1.get("status")),
        )
        _require(
            v1.get("consequence") not in (None, ""),
            result,
            "INCIDENT_V1_LOSS_UNDISCLOSED",
        )
    historical = incident.get("historical")
    if isinstance(historical, dict) and isinstance(historical.get("v2_packet"), dict):
        _require(
            historical["v2_packet"].get("modified_by_v3") is False,
            result,
            "V2_MODIFICATION_CLAIM_INVALID",
        )
    claims = incident.get("claims_allowed")
    if not isinstance(claims, dict):
        result.fail("INCIDENT_CLAIMS_BLOCK_MISSING")
    else:
        _require(claims.get("global_no_drift") is False, result, "CLAIM_GLOBAL_NO_DRIFT_FORBIDDEN")
        _require(
            claims.get("evidence_completeness") is False,
            result,
            "CLAIM_EVIDENCE_COMPLETENESS_FORBIDDEN",
        )
    disclosure = incident.get("disclosure")
    _require(
        isinstance(disclosure, str) and "MUST NOT" in disclosure,
        result,
        "INCIDENT_DISCLOSURE_MISSING",
    )


def verify_identity(manifest: dict, result: Result, expected_impl: str | None, expected_content: str | None) -> None:
    identity = manifest.get("identity")
    if not isinstance(identity, dict):
        result.fail("IDENTITY_MISSING")
        return
    impl_sha = identity.get("impl_sha")
    content_sha = identity.get("content_sha256")
    if not (isinstance(impl_sha, str) and common.IMPL_SHA_RE.match(impl_sha)):
        result.fail("IMPL_SHA_INVALID", str(impl_sha))
    if not (isinstance(content_sha, str) and common.SHA256_RE.match(content_sha)):
        result.fail("CONTENT_SHA_INVALID", str(content_sha))
    if impl_sha == content_sha:
        result.fail("IDENTITY_CONFLATED", "content_sha256 equals impl_sha")
    builder_sha = identity.get("builder_sha256")
    _require(
        isinstance(builder_sha, str) and bool(common.SHA256_RE.match(builder_sha)),
        result,
        "BUILDER_SHA_INVALID",
    )
    if expected_impl is not None and impl_sha != expected_impl:
        result.fail("IMPL_SHA_MISMATCH", f"{impl_sha} != {expected_impl}")
    if expected_content is not None and content_sha != expected_content:
        result.fail("CONTENT_SHA_MISMATCH_EXPECTED", f"{content_sha} != {expected_content}")


def verify_hashes(root: Path, manifest: dict, payload: dict[str, dict], result: Result) -> None:
    hashes_path = root / common.HASHES
    if not hashes_path.is_file():
        result.fail("MISSING_ENTRY", common.HASHES)
        return
    data = hashes_path.read_bytes()
    try:
        entries = common.parse_hashes(data)
    except common.PacketError as exc:
        result.fail(exc.code, exc.detail)
        return
    expected_cover = {common.PAYLOAD_DIR + "/" + rel for rel in payload} | {
        common.MANIFEST,
        common.README,
    }
    if set(entries) != expected_cover:
        result.fail(
            "HASHES_COVERAGE_MISMATCH",
            f"missing={sorted(expected_cover - set(entries))[:5]} "
            f"extra={sorted(set(entries) - expected_cover)[:5]}",
        )
        return
    for relpath, digest in entries.items():
        path = root / relpath
        if not path.is_file():
            result.fail("MISSING_ENTRY", relpath)
            continue
        disk_sha = common.sha256_file(path)
        if disk_sha != digest:
            result.fail("HASH_MISMATCH", f"{relpath}: {disk_sha} != {digest}")
    expected_count = len(payload) + 2
    if len(entries) != expected_count:
        result.fail("HASHES_COUNT_MISMATCH", f"{len(entries)} != {expected_count}")
    layers = manifest.get("layers") if isinstance(manifest.get("layers"), dict) else {}
    hashes_layer = layers.get("hashes") if isinstance(layers.get("hashes"), dict) else {}
    if hashes_layer.get("entry_count") != expected_count:
        result.fail("HASHES_COUNT_MISMATCH", "layers.hashes.entry_count")
    inventory = manifest.get("inventory") if isinstance(manifest.get("inventory"), dict) else {}
    if inventory.get("hash_manifest_entry_count") != expected_count:
        result.fail("HASHES_COUNT_MISMATCH", "inventory.hash_manifest_entry_count")
    if inventory.get("total_regular_files") != len(payload) + 3:
        result.fail("INVENTORY_COUNT_MISMATCH", "inventory.total_regular_files")


def verify_manifest_layers(manifest: dict, payload: dict[str, dict], result: Result) -> None:
    layers = manifest.get("layers")
    if not isinstance(layers, dict):
        result.fail("LAYERS_MISSING")
        return
    payload_layer = layers.get("payload") if isinstance(layers.get("payload"), dict) else {}
    tree_sha = common.payload_tree_sha256(payload)
    content_sha = common.payload_content_sha256(payload)
    if payload_layer.get("tree_sha256") != tree_sha:
        result.fail("PAYLOAD_TREE_MISMATCH", "layers.payload.tree_sha256")
    if payload_layer.get("content_sha256") != content_sha:
        result.fail("CONTENT_SHA_MISMATCH", "layers.payload.content_sha256")
    if payload_layer.get("file_count") != len(payload):
        result.fail("INVENTORY_COUNT_MISMATCH", "layers.payload.file_count")
    inventory = manifest.get("inventory") if isinstance(manifest.get("inventory"), dict) else {}
    if inventory.get("content_sha256") != content_sha:
        result.fail("CONTENT_SHA_MISMATCH", "inventory.content_sha256")
    if inventory.get("payload_tree_sha256") != tree_sha:
        result.fail("PAYLOAD_TREE_MISMATCH", "inventory.payload_tree_sha256")
    if inventory.get("payload_count") != len(payload):
        result.fail("INVENTORY_COUNT_MISMATCH", "inventory.payload_count")
    identity = manifest.get("identity") if isinstance(manifest.get("identity"), dict) else {}
    if identity.get("content_sha256") != content_sha:
        result.fail("CONTENT_SHA_MISMATCH", "identity.content_sha256")
    if inventory.get("metadata_files") != [common.README]:
        result.fail("INVENTORY_METADATA_INVALID", str(inventory.get("metadata_files")))


def verify_layout(files: set[str], dirs: set[str], payload: dict[str, dict], result: Result) -> None:
    allowed_root_files = {common.MANIFEST, common.HASHES, common.README}
    allowed_dirs = {"."} | {common.PAYLOAD_DIR}
    allowed_payload_dirs = {common.PAYLOAD_DIR}
    for relpath in payload:
        parts = relpath.split("/")
        for index in range(1, len(parts)):
            allowed_payload_dirs.add(common.PAYLOAD_DIR + "/" + "/".join(parts[:index]))
    allowed_dirs |= allowed_payload_dirs
    for relpath in sorted(files):
        if relpath in allowed_root_files:
            continue
        if relpath.startswith(common.PAYLOAD_DIR + "/"):
            continue
        result.fail("EXTRA_ENTRY", relpath)
    for relpath in sorted(dirs):
        if relpath not in allowed_dirs:
            result.fail("EMPTY_DIRECTORY", relpath)
    for relpath in payload:
        if common.PAYLOAD_DIR + "/" + relpath not in files:
            result.fail("MISSING_ENTRY", relpath)
    for required in (common.MANIFEST, common.HASHES, common.README):
        if required not in files:
            result.fail("MISSING_ENTRY", required)


def verify(packet_root: Path, *, expected_impl_sha: str | None = None,
           expected_content_sha256: str | None = None, allow_phase1: bool = False) -> dict:
    root = Path(packet_root)
    result = Result(root)
    if not root.is_dir():
        result.fail("PACKET_MISSING", str(root))
        return result.document()
    files, dirs, disk = scan_packet_tree(root, result)
    manifest: dict = {}
    try:
        manifest = common.read_json_strict(root / common.MANIFEST) if (root / common.MANIFEST).is_file() else {}
    except common.PacketError as exc:
        result.fail(exc.code, exc.detail)
    if not manifest:
        if not any(failure["code"] == "MISSING_ENTRY" for failure in result.failures):
            result.fail("MANIFEST_INVALID", "manifest missing or empty")
        return result.document()
    if manifest.get("schema") != common.SCHEMA:
        result.fail("SCHEMA_MISMATCH", str(manifest.get("schema")))
    verify_identity(manifest, result, expected_impl_sha, expected_content_sha256)
    inventory = manifest.get("inventory") if isinstance(manifest.get("inventory"), dict) else {}
    payload = inventory.get("payload_files")
    if not isinstance(payload, dict):
        result.fail("INVENTORY_MISSING", "inventory.payload_files")
        payload = {}
    disk_payload = {
        relpath[len(common.PAYLOAD_DIR) + 1:]: record
        for relpath, record in disk.items()
        if relpath.startswith(common.PAYLOAD_DIR + "/")
    }
    for relpath in sorted(set(payload) - set(disk_payload)):
        result.fail("MISSING_ENTRY", relpath)
    for relpath in sorted(set(disk_payload) - set(payload)):
        result.fail("EXTRA_ENTRY", relpath)
    for relpath in sorted(set(payload) & set(disk_payload)):
        declared = payload[relpath] if isinstance(payload[relpath], dict) else {}
        actual = disk_payload[relpath]
        if declared.get("sha256") != actual["sha256"]:
            result.fail("HASH_MISMATCH", relpath)
        if declared.get("bytes") != actual["bytes"]:
            result.fail("HASH_MISMATCH", f"{relpath} bytes")
        if declared.get("mode") != actual["mode"]:
            result.fail("MODE_MISMATCH", f"{relpath}: {declared.get('mode')} != {actual['mode']}")
    for relpath, record in disk.items():
        if record["mode"] != oct(common.FILE_MODE):
            result.fail("MODE_MISMATCH", f"{relpath}: {record['mode']} != {oct(common.FILE_MODE)}")
    verify_layout(files, dirs, payload, result)
    verify_hashes(root, manifest, payload, result)
    verify_manifest_layers(manifest, payload, result)
    verify_frozen(manifest, result, allow_phase1)
    verify_incident(manifest, result)
    packet = manifest.get("packet") if isinstance(manifest.get("packet"), dict) else {}
    _require(
        isinstance(packet.get("name"), str) and packet["name"],
        result,
        "PACKET_NAME_INVALID",
    )
    _require(
        manifest.get("status") in ALLOWED_STATUS,
        result,
        "PACKET_STATUS_INVALID",
        str(manifest.get("status")),
    )
    document = result.document()
    document.update(
        {
            "identity": {
                "impl_sha": (manifest.get("identity") or {}).get("impl_sha"),
                "content_sha256": (manifest.get("identity") or {}).get("content_sha256"),
            },
            "manifest_sha256": common.sha256_file(root / common.MANIFEST)
            if (root / common.MANIFEST).is_file()
            else None,
            "hashes_sha256": common.sha256_file(root / common.HASHES)
            if (root / common.HASHES).is_file()
            else None,
            "payload_tree_sha256": common.payload_tree_sha256(payload),
            "content_sha256": common.payload_content_sha256(payload),
            "payload_count": len(payload),
        }
    )
    return document


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify A-NEXT review packet v3")
    parser.add_argument("--packet-root", required=True)
    parser.add_argument("--expected-impl-sha", default=None)
    parser.add_argument("--expected-content-sha", default=None)
    parser.add_argument(
        "--allow-phase1",
        action="store_true",
        help="allow phase-1 tooling packets without a frozen T0/T1 snapshot",
    )
    parser.add_argument("--json-out", default=None)
    return parser


def emit(document: dict, json_out: str | None) -> int:
    if json_out:
        Path(json_out).write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    json.dump(document, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return int(document["exit_code"])


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else EXIT_USAGE
    document = verify(
        Path(args.packet_root),
        expected_impl_sha=args.expected_impl_sha,
        expected_content_sha256=args.expected_content_sha,
        allow_phase1=args.allow_phase1,
    )
    return emit(document, args.json_out)


if __name__ == "__main__":
    sys.exit(main())
