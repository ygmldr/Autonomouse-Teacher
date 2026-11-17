#!/usr/bin/env python3
"""D2-13 CONTROL: deliberate read-only state mount, never a Candidate config.

The Launcher mounts this run's ``state`` directory *read-only* into this extra
control container (same UID map as the Candidate) to exercise the DAC
counterfactual that the D0 design requires be reported separately. A denial
here is ``CONTROL`` evidence, not proof of the formal Candidate mount tree.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import probe_common as pc  # noqa: E402

PATHS = (
    "/work/state",
    "/work/state/admission.json",
    "/work/state/broker.json",
    "/work/state/controller.json",
    "/work/state/policy.json",
    "/work/state/broker.sqlite3",
    "/work/state/attempts.sqlite3",
    "/work/state/receipts",
    "/work/state/received-count.json",
    "/work/state/ready",
)


def main() -> int:
    document = {"probe": "d2-13", "label": "CONTROL",
                "identity": pc.identity(), "state_mounts": [], "ops": []}
    document["state_mounts"] = [
        row for row in document["identity"]["mounts"]
        if row.get("mount_point") == "/work/state"]
    for path in PATHS:
        document["ops"].append(pc.attempt("read:" + path,
                                          lambda p=path: pc.open_read(p)))
        document["ops"].append(pc.attempt(
            "append:" + path,
            lambda p=path: pc.open_flags(p, os.O_WRONLY | os.O_APPEND,
                                         write=b"x")))
        document["ops"].append(pc.attempt(
            "truncate:" + path,
            lambda p=path: pc.open_flags(p, os.O_WRONLY | os.O_TRUNC)))
        document["ops"].append(pc.attempt(
            "stat:" + path, lambda p=path: pc.socket_stat(p)))
        document["ops"].append(pc.attempt(
            "unlink:" + path, lambda p=path: os.unlink(p)))
    document["ops"].append(pc.attempt(
        "listdir_state", lambda: sorted(os.listdir("/work/state"))))
    document["ops"].append(pc.attempt(
        "open_state_dir_rdonly",
        lambda: pc.open_flags("/work/state", os.O_RDONLY | os.O_DIRECTORY)))
    document["uid_map_same_as_candidate"] = True
    pc.emit(document)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
