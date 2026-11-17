#!/usr/bin/env python3
"""D2-01: Candidate reads the Broker SQLite/WAL/SHM from its real mount tree."""
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
    "/work/state",
    "/work/state/receipts",
)
PROTECTED_NAMES = {"broker.sqlite3", "broker.sqlite3-wal", "broker.sqlite3-shm",
                   "attempts.sqlite3", "attempts.sqlite3-wal",
                   "attempts.sqlite3-shm", "admission.json", "broker.json",
                   "policy.json", "controller.json", "received-count.json"}


def main() -> int:
    document = {
        "probe": "d2-01",
        "identity": pc.identity(),
        "ops": [],
        "state_mounts": [],
        "protected_name_search": {},
        "work_listing": None,
    }
    document["state_mounts"] = [
        row for row in document["identity"]["mounts"]
        if row.get("mount_point") == "/work/state"
        or "/runs/" in str(row.get("source") or "") and
        str(row.get("source") or "").endswith("/state")
    ]
    for path in STATE_PATHS:
        document["ops"].append(pc.attempt("open_rdonly:" + path,
                                          lambda p=path: pc.open_read(p)))
    for op_id, callable_ in (
            ("listdir:/work/state", lambda: sorted(os.listdir("/work/state"))),
            ("listdir:/work", lambda: sorted(os.listdir("/work"))),
            ("stat:/work/state", lambda: pc.socket_stat("/work/state"))):
        document["ops"].append(pc.attempt(op_id, callable_))
    document["protected_name_search"] = pc.bounded_walk(
        ["/work", "/project", "/output"], PROTECTED_NAMES)
    document["work_listing"] = sorted(os.listdir("/work"))
    pc.emit(document)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
