#!/usr/bin/env python3
"""D2-04: Candidate tries to execute/import the Broker, Trusted entry or FD."""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import probe_common as pc  # noqa: E402

MODULES = (
    "autoteacher_m0",
    "autoteacher_m0.accounting.broker",
    "autoteacher_m0.bridge.controller",
    "autoteacher_m0.bridge.fake_backend",
)
TRUSTED_PATHS = (
    "/project/src/autoteacher_m0/accounting/broker.py",
    "/project/src/autoteacher_m0/bridge/controller.py",
    "/project/trusted/run/trusted_entry.py",
    "/project/run/trusted_entry.py",
    "/project/fake/fake_provider.py",
    "/work/state/broker.sqlite3",
)
SOCKETS = (
    "/work/g3b/broker.sock",
    "/work/g3b/controller.sock",
    "/work/private/controller.sock",
    "/work/state/controller.sock",
)


def main() -> int:
    document = {"probe": "d2-04", "identity": pc.identity(), "ops": [],
                "imports": [], "fd_targets": pc.fd_targets(),
                "code_search": {}, "proc": {}}
    for module in MODULES:
        record = {"module": module}
        try:
            spec = importlib.util.find_spec(module)
            record["find_spec"] = None if spec is None else spec.origin
        except BaseException as exc:  # noqa: BLE001
            record["find_spec_error"] = pc.errno_doc(exc)
        try:
            __import__(module)
            record["imported"] = True
        except BaseException as exc:  # noqa: BLE001
            record["imported"] = False
            record["import_error"] = type(exc).__name__
            record["import_message"] = str(exc)[:200]
        document["imports"].append(record)
    for path in TRUSTED_PATHS:
        document["ops"].append(pc.attempt("open:" + path,
                                          lambda p=path: pc.open_read(p)))
    for path in SOCKETS:
        document["ops"].append(pc.attempt(
            "connect:" + path,
            lambda p=path: (lambda sock: (sock.close(), {"connected": True}))(
                pc.connect_unix(p, timeout=1.0))))
    document["ops"].append(pc.attempt(
        "exec_trusted_entry",
        lambda: subprocess.run(
            ["/opt/python/bin/python3.11", "-B", "/project/run/trusted_entry.py",
             "--config", "/work/state/controller.json"],
            capture_output=True, text=True, timeout=10).returncode))
    document["ops"].append(pc.attempt(
        "import_via_subprocess",
        lambda: (lambda proc: {"exit": proc.returncode,
                               "stderr": proc.stderr.strip().splitlines()[-1][:200]
                               if proc.stderr.strip() else ""})(
            subprocess.run(
                ["/opt/python/bin/python3.11", "-B", "-c",
                 "import autoteacher_m0.accounting.broker as b; print(b.__file__)"],
                capture_output=True, text=True, timeout=10))))
    document["code_search"] = pc.bounded_walk(
        ["/project"], {"broker.py", "controller.py", "fake_provider.py",
                       "attempts.py", "admission.py", "ipc_server.py",
                       "trusted_entry.py"},
        max_entries=20000)
    for pid in pc.proc_pids():
        record = {"pid": pid}
        try:
            raw = open(f"/proc/{pid}/cmdline", "rb").read()[:4096]
            record["cmdline"] = [part.decode("utf-8", "replace")
                                 for part in raw.split(b"\0") if part]
        except OSError as exc:
            record["cmdline_error"] = pc.errno_doc(exc)
        try:
            record["fds"] = sorted(os.listdir(f"/proc/{pid}/fd"))
        except OSError as exc:
            record["fds_error"] = pc.errno_doc(exc)
        document["proc"][str(pid)] = record
    trusted_pid = None
    for index, token in enumerate(sys.argv):
        if token == "--trusted-pid" and index + 1 < len(sys.argv):
            trusted_pid = int(sys.argv[index + 1])
    if trusted_pid:
        document["trusted_pid"] = trusted_pid
        for suffix in ("environ", "fd", "root", "cwd", "cmdline", "status", "maps"):
            document["ops"].append(pc.attempt(
                f"read_trusted_{suffix}",
                lambda s=suffix: pc.open_read(f"/proc/{trusted_pid}/{s}")))
    document["sys_path"] = [entry for entry in sys.path if entry]
    document["pythonpath"] = os.environ.get("PYTHONPATH")
    pc.emit(document)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
