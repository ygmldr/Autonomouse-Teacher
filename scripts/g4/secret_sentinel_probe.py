#!/usr/bin/env python3
"""Scan explicit runtime surfaces for the TEST_ONLY credential sentinel.

The only secret value this repository is allowed to use in a no-key rehearsal is
the obviously invalid marker ``TEST_ONLY_NEVER_VALID_SECRET_SENTINEL``. It is
never read from ``os.environ``, a home directory, a key manager or a provider;
the G4-D fixtures write it into a repo-external trusted test file only. This
probe answers one question: **do the named runtime surfaces contain those bytes
verbatim?**

Design rules:

* only scan roots/pids that the caller names explicitly (never ``/root`` or the
  whole host filesystem), so the probe cannot ingest a real host secret;
* compare raw bytes (JSON/JSONL/SQLite pages/JUnit/logs), never print the
  surroundings of a hit - only path, offset and count;
* a missing root is reported, not silently treated as clean;
* ``--self-test`` writes the sentinel into a temporary file and requires the
  scanner to detect it, so a "clean" result cannot come from a broken matcher.

This is evidence tooling, not a credential boundary. It adds no Live allow path.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

SENTINEL = "TEST_ONLY_NEVER_VALID_SECRET_SENTINEL"
SENTINEL_BYTES = SENTINEL.encode("ascii")
SCHEMA = "m0.g4d.sentinel-scan.v1"
SKIP_SUFFIXES = {".sock", ".socket", ".fifo", ".lock"}
MAX_FILE_BYTES = 64 << 20


def utc() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def iter_regular_files(root: Path, *, exclude: tuple[str, ...]) -> tuple[list[Path], list[str]]:
    files: list[Path] = []
    skipped: list[str] = []
    if root.is_file():
        return [root], skipped
    if not root.is_dir():
        return [], [str(root)]
    for entry in sorted(root.rglob("*")):
        text = str(entry)
        if any(text == item or text.startswith(item.rstrip("/") + os.sep)
               for item in exclude):
            continue
        try:
            info = entry.lstat()
        except OSError:
            skipped.append(f"{text}:lstat_error")
            continue
        if os.path.islink(text) or not os.path.isfile(text):
            skipped.append(f"{text}:not_regular")
            continue
        if entry.suffix in SKIP_SUFFIXES:
            skipped.append(f"{text}:special")
            continue
        if info.st_size > MAX_FILE_BYTES:
            skipped.append(f"{text}:too_large:{info.st_size}")
            continue
        files.append(entry)
    return files, skipped


def scan_file(path: Path) -> dict | None:
    try:
        data = path.read_bytes()
    except OSError as error:
        return {"path": str(path), "error": type(error).__name__, "count": 0}
    count = data.count(SENTINEL_BYTES)
    if not count:
        return None
    offsets = []
    start = 0
    while len(offsets) < 8:
        found = data.find(SENTINEL_BYTES, start)
        if found < 0:
            break
        offsets.append(found)
        start = found + 1
    return {"path": str(path), "count": count, "offsets": offsets,
            "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def scan_roots(roots: list[str], *, exclude: tuple[str, ...] = ()) -> dict:
    files: list[Path] = []
    skipped: list[str] = []
    missing: list[str] = []
    for raw in roots:
        root = Path(raw).resolve()
        if not root.exists():
            missing.append(str(root))
            continue
        found, notes = iter_regular_files(root, exclude=exclude)
        files.extend(found)
        skipped.extend(notes)
        if root.is_file():
            # A named file is scanned even if a suffix rule would skip it.
            pass
    unique: dict[str, Path] = {}
    for path in files:
        unique[str(path)] = path
    hits: list[dict] = []
    errors: list[dict] = []
    scanned = 0
    for path in sorted(unique.values(), key=lambda item: str(item)):
        record = scan_file(path)
        if record is None:
            scanned += 1
            continue
        if "error" in record:
            errors.append(record)
            continue
        hits.append(record)
        scanned += 1
    return {
        "schema": SCHEMA,
        "utc": utc(),
        "sentinel_name": SENTINEL,
        "roots": [str(Path(item).resolve()) for item in roots],
        "excluded": list(exclude),
        "files_scanned": scanned,
        "files_present": len(unique),
        "missing_roots": missing,
        "skipped": skipped[:200],
        "skipped_total": len(skipped),
        "errors": errors,
        "hits": hits,
        "hit_count": sum(hit["count"] for hit in hits),
        "clean": not hits and not errors and not missing,
    }


def scan_proc(pid: int) -> dict:
    """Capture the three candidate-visible /proc surfaces for one live pid."""
    root = Path("/proc") / str(pid)
    surfaces: dict[str, dict] = {}
    for name, limit in (("environ", 1 << 20), ("cmdline", 1 << 16),
                        ("mountinfo", 1 << 22), ("status", 1 << 16)):
        path = root / name
        try:
            data = path.read_bytes()[:limit]
        except OSError as error:
            surfaces[name] = {"present": False, "error": type(error).__name__}
            continue
        text = data.decode("utf-8", "replace")
        surfaces[name] = {
            "present": True,
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "sentinel_count": text.count(SENTINEL),
            # Show the key names only for environ; values are never emitted.
            "entries": (sorted({line.split("=", 1)[0] for line in text.splitlines()
                                if "=" in line})[:200] if name == "environ" else None),
        }
    return {"schema": "m0.g4d.sentinel-proc.v1", "utc": utc(), "pid": pid,
            "surfaces": surfaces,
            "clean": all(not item.get("sentinel_count") for item in surfaces.values())}


def positive_control() -> dict:
    with tempfile.TemporaryDirectory(prefix="g4d-sentinel-") as directory:
        root = Path(directory)
        (root / "clean.txt").write_text("nothing to see here\n", encoding="utf-8")
        (root / "leak.jsonl").write_text(
            json.dumps({"event": "test", "value": SENTINEL}) + "\n", encoding="utf-8")
        record = scan_roots([str(root)])
    return {"control": record["hit_count"] >= 1, "hits": len(record["hits"]),
            "clean_flag_false": record["clean"] is False, "record": record}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", action="append", default=[],
                        help="file or directory to scan (repeatable)")
    parser.add_argument("--exclude", action="append", default=[],
                        help="path prefix to exclude (repeatable)")
    parser.add_argument("--pid", action="append", type=int, default=[],
                        help="live pid whose /proc env/argv/mountinfo is recorded")
    parser.add_argument("--self-test", action="store_true",
                        help="require the scanner to find the sentinel in a temp file")
    parser.add_argument("--out", default=None, help="write the JSON document here")
    parser.add_argument("--fail-on-hit", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    document: dict = {
        "schema": SCHEMA,
        "utc": utc(),
        "sentinel_name": SENTINEL,
        "proc": [scan_proc(pid) for pid in args.pid],
    }
    scan = scan_roots(args.root, exclude=tuple(args.exclude)) if args.root else None
    if scan is not None:
        document["scan"] = scan
    if args.self_test:
        document["positive_control"] = positive_control()
    clean = True
    if scan is not None:
        clean = clean and scan["clean"]
    for proc in document["proc"]:
        clean = clean and proc["clean"]
    if args.self_test:
        clean = clean and document["positive_control"]["control"]
    document["clean"] = clean
    text = json.dumps(document, indent=2, sort_keys=True) + "\n"
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8")
    sys.stdout.write(text)
    return 0 if clean or not args.fail_on_hit else 4


if __name__ == "__main__":
    raise SystemExit(main())
