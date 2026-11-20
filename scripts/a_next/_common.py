"""Shared helpers for A-NEXT hygiene tooling (stdlib only, read-only by design).

All helpers are intentionally small and side-effect free unless the caller asks for
an explicit write.  Nothing in this module ever writes inside a path handed to it
as ``frozen`` or ``rootfs``; the guards only read/hash such trees.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote

# Frozen no-key G4-R environment identity (read-only detection target).
FROZEN_ROOTFS_SHA256 = (
    "25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0"
)
FROZEN_MARKER_NAMES = (
    ".a_next_frozen_rootfs",
    ".frozen-rootfs",
    "FROZEN_ROOTFS",
)
DEFAULT_FROZEN_MARKER = ".a_next_frozen_rootfs"

TAR_NORMALIZE_ARGV = [
    "tar",
    "--sort=name",
    "--mtime=@0",
    "--owner=0",
    "--group=0",
    "--numeric-owner",
    "-cf",
    "-",
    "-C",
]


class GuardError(RuntimeError):
    """Raised for tool-level failures that are not part of a refusal verdict."""


def canonical_tree_sha256(path: str | os.PathLike[str]) -> str:
    """Canonical tree hash frozen by docs/M0_G3B_BASELINE.md:209-211."""
    root = Path(path)
    if not root.is_dir():
        raise GuardError(f"not a directory: {root}")
    argv = [*TAR_NORMALIZE_ARGV, str(root), "."]
    proc = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace")[:800]
        raise GuardError(f"tar failed for {root} (exit {proc.returncode}): {detail}")
    return hashlib.sha256(proc.stdout).hexdigest()


def sha256_file(path: str | os.PathLike[str]) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def resolved(path: str | os.PathLike[str]) -> Path:
    return Path(path).expanduser().resolve()


def is_under(candidate: str | os.PathLike[str], parent: str | os.PathLike[str]) -> bool:
    """True when ``candidate`` lives inside ``parent`` (or equals it)."""
    try:
        candidate_r = resolved(candidate)
        parent_r = resolved(parent)
    except OSError:
        return False
    if candidate_r == parent_r:
        return True
    try:
        candidate_r.relative_to(parent_r)
    except ValueError:
        return False
    return True


def find_marker(rootfs: str | os.PathLike[str]) -> str | None:
    """Return the first frozen-marker filename present in ``rootfs`` (read-only)."""
    root = Path(rootfs)
    if not root.is_dir():
        return None
    for name in FROZEN_MARKER_NAMES:
        candidate = root / name
        try:
            if candidate.is_file() and not candidate.is_symlink():
                return name
        except OSError:
            continue
    return None


def frozen_match(rootfs: str | os.PathLike[str]) -> dict[str, Any]:
    """Read-only frozen-rootfs detection.

    Detection rules (any match => frozen):
    * path equals the configured frozen path;
    * a frozen marker file exists in the tree;
    * the canonical tree hash equals the frozen hash.
    """
    root = Path(rootfs)
    result: dict[str, Any] = {
        "path": str(root),
        "exists": root.is_dir(),
        "canonical_sha256": None,
        "marker": None,
        "matches_frozen_sha": False,
        "error": None,
    }
    if not result["exists"]:
        result["error"] = "not_a_directory"
        return result
    result["marker"] = find_marker(root)
    try:
        result["canonical_sha256"] = canonical_tree_sha256(root)
    except GuardError as exc:  # pragma: no cover - defensive
        result["error"] = str(exc)
    result["matches_frozen_sha"] = (
        result["canonical_sha256"] == FROZEN_ROOTFS_SHA256
    )
    return result


def write_json(path: str | os.PathLike[str], document: Any) -> None:
    target = Path(path)
    if not target.parent.exists():
        raise GuardError(f"parent directory missing: {target.parent}")
    tmp_fd, tmp_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent)
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as handle:
            json.dump(document, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(tmp_name, target)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def sanitize_env(
    env: dict[str, str] | None = None,
) -> tuple[dict[str, str], list[str]]:
    """Drop key-like environment variables; return (env, removed_names).

    Only names matching the key-like pattern are removed; values are never
    printed or stored.  Secret *values* are not inspected (avoid accidental
    leakage through logs).
    """
    source = dict(os.environ if env is None else env)
    key_like = (
        "KEY",
        "TOKEN",
        "SECRET",
        "PASSWORD",
        "CREDENTIAL",
        "AUTHORIZATION",
    )
    removed = sorted(
        name for name in source if any(part in name.upper() for part in key_like)
    )
    for name in removed:
        del source[name]
    return source, removed


def git(
    repo: str | os.PathLike[str],
    *args: str,
    check: bool = True,
) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if check and proc.returncode != 0:
        raise GuardError(
            f"git {' '.join(args)} failed in {repo}: "
            f"{proc.stderr.strip() or proc.stdout.strip()}"
        )
    return proc


def git_ok(repo: str | os.PathLike[str], *args: str) -> bool:
    return git(repo, *args, check=False).returncode == 0


def git_lines(repo: str | os.PathLike[str], *args: str) -> list[str]:
    proc = git(repo, *args, check=False)
    if proc.returncode != 0:
        raise GuardError(proc.stderr.strip() or f"git {' '.join(args)} failed")
    return [line for line in proc.stdout.splitlines() if line.strip()]


def path_url(path: str | os.PathLike[str]) -> str:
    """Tiny helper reused by docs/tests to render paths; never used for writes."""
    return "file://" + quote(str(resolved(path)))


def ensure_new_dir(path: str | os.PathLike[str]) -> Path:
    """Create a brand-new empty directory; refuse if anything exists."""
    target = Path(path)
    if target.exists() or target.is_symlink():
        raise GuardError(f"output already exists: {target}")
    target.mkdir(parents=True)
    return target


def iter_tree_entries(root: str | os.PathLike[str]) -> Iterable[tuple[Path, os.stat_result]]:
    """Yield ``(path, lstat)`` for every entry under ``root`` without following links."""
    base = Path(root)
    stack = [base]
    while stack:
        current = stack.pop()
        with os.scandir(current) as entries:
            for entry in entries:
                try:
                    info = entry.stat(follow_symlinks=False)
                except OSError:
                    continue
                yield Path(entry.path), info
                if entry.is_dir(follow_symlinks=False):
                    stack.append(Path(entry.path))
