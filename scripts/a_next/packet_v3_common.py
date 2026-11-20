"""A-NEXT review packet v3: shared constants and strict-inventory helpers.

The v3 packet is a *new identity* (``review-packet-a-next-v3-<impl_sha>``).
It deliberately does not reuse or overwrite the frozen v1/v2 packet bytes.

Three layers
------------
1. ``payload/**``   — the evidence payload, regular files only, mode 0444.
2. ``hashes.sha256`` — sha256 of every payload file plus ``README.md`` and
   ``manifest.json`` (self excluded; fixed exception set).
3. ``manifest.json`` — schema/identity/inventory/frozen/incident declarations.
   The manifest never contains its own hash; layer identities are recorded in
   ``layers`` and re-derived by the verifier.

Identity separation
-------------------
``identity.impl_sha`` is the frozen git commit (40 hex, authoritative).
``identity.content_sha256`` is the *payload content digest* (64 hex) computed
over the payload inventory only — it changes with payload bytes and is NOT the
impl commit.  The two fields must never be conflated.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
from pathlib import Path
from typing import Any

SCHEMA = "m0.a-next.review-packet.v3"
VERIFICATION_SCHEMA = "m0.a-next.packet-verification.v3"
REPORT_SCHEMA = "m0.a-next.packet-integrity-report.v3"
IDENTITY_ROOT_PREFIX = "review-packet-a-next-v3-"
PHASE_FINAL = "final"
PHASE_TOOLING = "phase-1-tooling"

MANIFEST = "manifest.json"
HASHES = "hashes.sha256"
README = "README.md"
PAYLOAD_DIR = "payload"

FROZEN_ROOTFS_SHA256 = (
    "25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0"
)
FROZEN_DEPS_SHA256 = (
    "e07729d7997944417b1c25531749b3e6e5e34aa4248f01dc8f370282082ecb98"
)
FROZEN_DSH_RUNTIME_SHA256 = (
    "1cc41d5a8745a5b9d47c8604e44f23eb8af2d8ca02b2afa0be101d5f71be6ea4"
)
FROZEN_ADAPTER_JS_SHA256 = (
    "2cb424616b7380bff61f8ce760e229a0c1d2b32c4a5f2954cdf66c3937bf74ba"
)
BACKUP_TAR_SHA256 = (
    "11172f0268cdf2dc2bde08e90d9d93c0a444b134f8eaab9a712057c9d5159d42"
)
BACKUP_TAR_DEFAULT_PATH = "/root/a-next-artifacts-restored-20261121.tar"
V1_PACKET_PATH = (
    "artifacts/review-packet-g4f-e7d92967ec0ece80de4a1a3705f637e8eb9bde99"
)
V2_PACKET_DIR_PREFIX = "review-packet-g4r-v2-d33e0aabd1714a486325b745c436cb59855d6539"

FILE_MODE = 0o444
DIR_MODE = 0o555

IMPL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
REL_PATH_RE = re.compile(r"^[A-Za-z0-9._+@=,-][A-Za-z0-9._+@=,/\-]*$")

SIDECAR_NAMES = {".DS_Store", "Thumbs.db", "__MACOSX", "desktop.ini"}
SIDECAR_SUFFIXES = (".swp", ".swo", ".tmp", ".temp", "~", ".orig")

INCIDENT = {
    "id": "INCIDENT_20261121",
    "reported_utc": "2026-11-20T19:53Z",
    "summary": (
        "Repository artifacts were accidentally deleted around 19:53Z and restored "
        "from a hash-verified copy; frozen rootfs/deps canonical hashes were re-verified "
        "after restoration."
    ),
    "deleted_scope": "artifacts/ (frozen rootfs copy, foundation/deps, g4r evidence directories)",
    "restoration": {
        "source_backup_tar": BACKUP_TAR_DEFAULT_PATH,
        "source_backup_tar_sha256": BACKUP_TAR_SHA256,
        "restored_rootfs_sha256": FROZEN_ROOTFS_SHA256,
        "restored_deps_sha256": FROZEN_DEPS_SHA256,
        "verification_method": (
            "sha256 of canonical tar-normalized trees compared with pre-incident frozen identities"
        ),
        "tar_verified_in_this_run": False,
    },
    "lost": {
        "v1_packet": {
            "status": "LOST_ORIGINAL_BYTES_UNVERIFIABLE",
            "path_before_incident": V1_PACKET_PATH,
            "consequence": (
                "v1 packet original bytes cannot be re-verified or compared; only "
                "SHA-only historical references remain"
            ),
        }
    },
    "historical": {
        "v2_packet": {
            "dir_basename": V2_PACKET_DIR_PREFIX,
            "status": "HISTORICAL_REFERENCE_ONLY",
            "modified_by_v3": False,
        }
    },
    "claims_allowed": {
        "global_no_drift": False,
        "evidence_completeness": False,
    },
    "disclosure": (
        "MUST NOT claim full evidence completeness or continuous/global NO_DRIFT. "
        "v1 packet bytes are LOST; v2 is a historical reference only and its bytes are not modified."
    ),
}


class PacketError(RuntimeError):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


def utc_now() -> str:
    import time

    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str | os.PathLike[str]) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def canonical_tree_sha256(path: str | os.PathLike[str]) -> str:
    """Canonical tar-normalized tree hash (same recipe as G4-R/rootfs guards)."""
    argv = [
        "tar",
        "--sort=name",
        "--mtime=@0",
        "--owner=0",
        "--group=0",
        "--numeric-owner",
        "-cf",
        "-",
        "-C",
        str(Path(path).resolve()),
        ".",
    ]
    proc = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        raise PacketError("TREE_HASH_FAILED", proc.stderr.decode("utf-8", "replace")[:400])
    return sha256_bytes(proc.stdout)


def payload_content_sha256(records: dict[str, dict]) -> str:
    """Payload-only content digest, independent of the git impl commit."""
    lines = []
    for relpath in sorted(records):
        record = records[relpath]
        lines.append(
            f"{relpath}\0{record['sha256']}\0{record['bytes']}\0{record['mode']}\n"
        )
    blob = ("m0.a-next.payload-content/v3\n" + "".join(lines)).encode("utf-8")
    return sha256_bytes(blob)


def payload_tree_sha256(records: dict[str, dict]) -> str:
    lines = [f"{records[rel]['sha256']}  {rel}\n" for rel in sorted(records)]
    return sha256_bytes("".join(lines).encode("utf-8"))


def mode_of(path: str | os.PathLike[str]) -> str:
    info = os.lstat(path)
    return oct(stat.S_IMODE(info.st_mode))


def validate_relative_path(relpath: str) -> str:
    if not isinstance(relpath, str) or not relpath:
        raise PacketError("BAD_PATH", "empty path")
    if "\\" in relpath or relpath.startswith("/") or relpath.endswith("/"):
        raise PacketError("BAD_PATH", relpath)
    parts = relpath.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise PacketError("BAD_PATH", relpath)
    if not REL_PATH_RE.match(relpath):
        raise PacketError("BAD_PATH", relpath)
    return relpath


def is_sidecar_name(name: str) -> bool:
    if name in SIDECAR_NAMES:
        return True
    return any(name.endswith(suffix) for suffix in SIDECAR_SUFFIXES)


def scan_strict_tree(root: str | os.PathLike[str]) -> dict[str, dict]:
    """Strict inventory of a staging/storage tree: regular files only.

    Rejects symlinks, hardlinks (nlink > 1), special files, unsafe relative
    paths, duplicate/confusable paths and sidecar junk names.  Read-only.
    """
    base = Path(root)
    if not base.is_dir():
        raise PacketError("STAGING_MISSING", str(base))
    records: dict[str, dict] = {}
    seen_lower: dict[str, str] = {}
    stack: list[Path] = [base]
    while stack:
        current = stack.pop()
        try:
            entries = list(os.scandir(current))
        except OSError as exc:  # pragma: no cover - defensive
            raise PacketError("SCAN_FAILED", f"{current}: {exc}") from exc
        for entry in entries:
            path = Path(entry.path)
            relpath = str(path.relative_to(base)).replace(os.sep, "/")
            validate_relative_path(relpath)
            info = os.lstat(path)
            if stat.S_ISLNK(info.st_mode):
                raise PacketError("SYMLINK_REFUSED", relpath)
            if stat.S_ISDIR(info.st_mode):
                stack.append(path)
                continue
            if not stat.S_ISREG(info.st_mode):
                raise PacketError("SPECIAL_FILE_REFUSED", relpath)
            if info.st_nlink != 1:
                raise PacketError("HARDLINK_REFUSED", relpath)
            if is_sidecar_name(path.name):
                raise PacketError("SIDECAR_REFUSED", relpath)
            lower = relpath.lower()
            if lower in seen_lower:
                raise PacketError("DUPLICATE_PATH", f"{relpath} vs {seen_lower[lower]}")
            seen_lower[lower] = relpath
            records[relpath] = {
                "sha256": sha256_file(path),
                "bytes": info.st_size,
                # packet payload files are frozen read-only by the builder
                "mode": oct(FILE_MODE),
            }
    if not records:
        raise PacketError("EMPTY_STAGING", str(base))
    return records


def read_json_strict(path: str | os.PathLike[str], *, max_bytes: int = 1 << 20) -> dict:
    """Read a JSON object rejecting duplicate keys and oversized input."""

    def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict:
        seen: set[str] = set()
        for key, _value in pairs:
            if key in seen:
                raise PacketError("DUPLICATE_JSON_KEY", key)
            seen.add(key)
        return dict(pairs)

    data = Path(path).read_bytes()
    if len(data) > max_bytes:
        raise PacketError("JSON_TOO_LARGE", str(path))
    try:
        document = json.loads(data.decode("utf-8"), object_pairs_hook=_reject_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PacketError("JSON_INVALID", f"{path}: {exc}") from exc
    if not isinstance(document, dict):
        raise PacketError("JSON_INVALID", "top-level value is not an object")
    return document


def parse_hashes(data: bytes) -> dict[str, str]:
    """Parse ``<sha256>  <relpath>`` lines; rejects duplicates/malformed entries."""
    entries: dict[str, str] = {}
    text = data.decode("utf-8", "replace")
    for index, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            raise PacketError("HASHES_MALFORMED", f"blank line {index}")
        match = re.match(r"^([0-9a-f]{64})  (.+)$", line)
        if not match:
            raise PacketError("HASHES_MALFORMED", f"line {index}")
        digest, relpath = match.groups()
        validate_relative_path(relpath)
        if relpath in entries:
            raise PacketError("HASHES_DUPLICATE", relpath)
        entries[relpath] = digest
    return entries
