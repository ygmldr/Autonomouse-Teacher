#!/usr/bin/env python3
"""D2-02: Candidate writes/truncates/replaces the Broker DB and state files."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import probe_common as pc  # noqa: E402

STATE_PATHS = (
    "/work/state/broker.sqlite3",
    "/work/state/broker.sqlite3-wal",
    "/work/state/broker.sqlite3-shm",
    "/state/broker.sqlite3",
    "/output/broker.sqlite3",
)
SOURCE = "/work/session/d2-write-source"
LINKS = "/work/session/d2-write-link"


def main() -> int:
    document = {
        "probe": "d2-02",
        "identity": pc.identity(),
        "ops": [],
        "local_source": {},
    }
    try:
        with open(SOURCE, "wb") as handle:
            handle.write(b"candidate-forged-broker-bytes\n")
        document["local_source"] = {"path": SOURCE,
                                    "sha256": pc.sha256_file(SOURCE)}
    except OSError as exc:
        document["local_source"] = {"error": pc.errno_doc(exc)}
    for path in STATE_PATHS:
        document["ops"].append(pc.attempt(
            "open_rdwr:" + path,
            lambda p=path: pc.open_flags(p, os.O_RDWR)))
        document["ops"].append(pc.attempt(
            "open_create:" + path,
            lambda p=path: pc.open_flags(p, os.O_WRONLY | os.O_CREAT, mode=0o600,
                                         write=b"x")))
        document["ops"].append(pc.attempt(
            "open_truncate:" + path,
            lambda p=path: pc.open_flags(p, os.O_WRONLY | os.O_TRUNC)))
        document["ops"].append(pc.attempt(
            "unlink:" + path, lambda p=path: os.unlink(p)))
        document["ops"].append(pc.attempt(
            "chmod:" + path, lambda p=path: os.chmod(p, 0o666)))
        document["ops"].append(pc.attempt(
            "replace:" + path, lambda p=path: os.replace(SOURCE, p)))
        document["ops"].append(pc.attempt(
            "hardlink:" + path, lambda p=path: os.link(SOURCE, p)))
        document["ops"].append(pc.attempt(
            "symlink:" + path, lambda p=path: os.symlink(SOURCE, p)))
    document["ops"].append(pc.attempt(
        "open_dir_rdwr:/work/state",
        lambda: pc.open_flags("/work/state", os.O_RDWR | os.O_DIRECTORY)))
    document["ops"].append(pc.attempt(
        "create_dir:/work/state/candidate",
        lambda: os.mkdir("/work/state/candidate", 0o700)))
    pc.emit(document)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
