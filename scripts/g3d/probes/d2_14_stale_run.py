#!/usr/bin/env python3
"""D2-14: a stale-run Candidate cannot see or connect to this Run's UDS.

The stale Candidate keeps the same host UID map (container 0 -> host 65534) and
the same supplementary group 2000. Its ``/work/g3b`` is a different, stale IPC
mount; the live Run's socket path is not in its mount namespace. This proves
that the per-Run path -- not the shared UID -- is the isolation boundary.
"""
from __future__ import annotations

import os
import socket
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import probe_common as pc  # noqa: E402


def arg(name: str, default: str | None = None) -> str | None:
    for index, token in enumerate(sys.argv):
        if token == name and index + 1 < len(sys.argv):
            return sys.argv[index + 1]
    return default


def connect(path: str) -> dict:
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(2.0)
    try:
        sock.connect(path)
        return {"connected": True}
    finally:
        sock.close()


def main() -> int:
    live_socket = arg("--live-socket", "") or ""
    trusted_pid = arg("--trusted-pid", "") or ""
    document = {"probe": "d2-14", "identity": pc.identity(),
                "live_socket": live_socket, "trusted_pid": trusted_pid,
                "ipc_mounts": [], "ops": []}
    document["ipc_mounts"] = [
        row for row in document["identity"]["mounts"]
        if row.get("mount_point") == "/work/g3b"]
    document["ops"].append(pc.attempt(
        "listdir_ipc", lambda: sorted(os.listdir("/work/g3b"))))
    document["ops"].append(pc.attempt(
        "stat_stale_socket", lambda: pc.socket_stat("/work/g3b/bridge.sock")))
    document["ops"].append(pc.attempt(
        "connect_stale_socket", lambda: connect("/work/g3b/bridge.sock")))
    if live_socket:
        document["ops"].append(pc.attempt(
            "connect_live_host_path", lambda: connect(live_socket)))
        document["ops"].append(pc.attempt(
            "stat_live_host_path", lambda: pc.socket_stat(live_socket)))
        document["ops"].append(pc.attempt(
            "connect_live_via_proc_root",
            lambda: connect("/proc/1/root" + live_socket)))
        document["ops"].append(pc.attempt(
            "connect_relative_escape",
            lambda: connect("/work/g3b/../../" + live_socket.lstrip("/"))))
    if trusted_pid:
        document["ops"].append(pc.attempt(
            "read_trusted_proc",
            lambda: pc.open_read(f"/proc/{trusted_pid}/environ")))
    document["ops"].append(pc.attempt(
        "read_work_state", lambda: pc.open_read("/work/state/broker.sqlite3")))
    document["ops"].append(pc.attempt(
        "list_work", lambda: sorted(os.listdir("/work"))))
    pc.emit(document)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
