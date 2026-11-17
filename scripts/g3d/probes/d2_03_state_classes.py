#!/usr/bin/env python3
"""D2-03: Candidate read/write attempts against every protected state class."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import probe_common as pc  # noqa: E402

STATE_CLASSES = (
    ("policy", "/work/state/policy.json"),
    ("admission", "/work/state/admission.json"),
    ("broker_config", "/work/state/broker.json"),
    ("controller_config", "/work/state/controller.json"),
    ("attempt_journal", "/work/state/attempts.sqlite3"),
    ("attempt_wal", "/work/state/attempts.sqlite3-wal"),
    ("receipt", "/work/state/receipts"),
    ("fake_counter", "/work/state/received-count.json"),
    ("ready", "/work/state/ready"),
    ("launcher_ready", "/work/state/launcher-ready.json"),
)


def main() -> int:
    document = {"probe": "d2-03", "identity": pc.identity(), "ops": [],
                "classes": []}
    for label, path in STATE_CLASSES:
        entry = {"class": label, "path": path, "ops": []}
        entry["ops"].append(pc.attempt("read:" + label,
                                       lambda p=path: pc.open_read(p)))
        entry["ops"].append(pc.attempt(
            "append:" + label,
            lambda p=path: pc.open_flags(p, os.O_WRONLY | os.O_APPEND,
                                         write=b"x")))
        entry["ops"].append(pc.attempt(
            "truncate:" + label,
            lambda p=path: pc.open_flags(p, os.O_WRONLY | os.O_TRUNC)))
        entry["ops"].append(pc.attempt(
            "stat:" + label, lambda p=path: pc.socket_stat(p)))
        entry["ops"].append(pc.attempt(
            "listdir:" + label, lambda p=path: sorted(os.listdir(p))))
        entry["ops"].append(pc.attempt(
            "unlink:" + label, lambda p=path: os.unlink(p)))
        document["ops"].extend(entry["ops"])
        document["classes"].append(entry)
    pc.emit(document)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
