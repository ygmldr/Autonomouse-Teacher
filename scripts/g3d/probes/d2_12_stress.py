#!/usr/bin/env python3
"""D2-12: concurrency, slowloris, oversized frames, fork/fd/memory pressure."""
from __future__ import annotations

import os
import resource
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import probe_common as pc  # noqa: E402


def arg(name: str, default: str | None = None) -> str | None:
    for index, token in enumerate(sys.argv):
        if token == name and index + 1 < len(sys.argv):
            return sys.argv[index + 1]
    return default


def mode_fork() -> dict:
    children: list[int] = []
    error = None
    for _ in range(48):
        try:
            pid = os.fork()
        except OSError as exc:
            error = pc.errno_doc(exc)
            break
        if pid == 0:
            time.sleep(1.0)
            os._exit(0)
        children.append(pid)
    for pid in children:
        try:
            os.waitpid(pid, 0)
        except OSError:
            pass
    return {"children": len(children), "error": error,
            "pids_max_observed": len(pc.proc_pids())}


def mode_memory() -> dict:
    chunks = []
    error = None
    for index in range(32):
        try:
            block = bytearray(8 << 20)
            for offset in range(0, len(block), 4096):
                block[offset] = 1
            chunks.append(block)
            print(f"D2_12 MEMORY_ALLOC_MB={(index + 1) * 8}", flush=True)
        except MemoryError as exc:
            error = {"type": type(exc).__name__, "after_mb": index * 8}
            break
    return {"allocated_mb": len(chunks) * 8, "error": error}


def mode_fd() -> dict:
    fds = []
    error = None
    try:
        while len(fds) < 8192:
            try:
                fds.append(os.open("/dev/null", os.O_RDONLY))
            except OSError as exc:
                error = pc.errno_doc(exc)
                break
    finally:
        for fd in fds:
            try:
                os.close(fd)
            except OSError:
                pass
    return {"opened": len(fds), "error": error,
            "nofile": resource.getrlimit(resource.RLIMIT_NOFILE)}


def mode_connections(count: int) -> dict:
    socks = []
    opened = []
    for index in range(count):
        try:
            sock = pc.connect_unix(pc.SOCKET_PATH, timeout=2.0)
            socks.append(sock)
            opened.append(index)
        except BaseException as exc:  # noqa: BLE001
            opened.append({"index": index, "error": pc.errno_doc(exc)})
            break
    overload = pc.exchange(
        pc.envelope_bytes(pc.request_payload(session="g3d-d2-12-overload"),
                          transport_id="tr-" + "c" * 32), timeout=4.0)
    slowloris = []
    for sock in socks:
        try:
            sock.sendall(b'{"v":1,"kind":"request"')
            slowloris.append({"connected": True, "partial_bytes": 22})
        except OSError as exc:
            slowloris.append({"connected": False, "error": pc.errno_doc(exc)})
    time.sleep(1.0)
    for sock in socks:
        try:
            sock.close()
        except OSError:
            pass
    return {"requested": count, "opened": len(opened),
            "opened_detail": opened, "overload": overload,
            "slowloris": slowloris}


def mode_flood(count: int) -> dict:
    results = []
    for index in range(count):
        try:
            sock = pc.connect_unix(pc.SOCKET_PATH, timeout=1.0)
            try:
                sock.sendall(b'{"v":1,"kind":"request","pad":"' +
                             b"x" * 300000 + b'"}\n')
                results.append(pc.read_frames(sock, timeout=2.0)
                               .get("error_code"))
            finally:
                sock.close()
        except BaseException as exc:  # noqa: BLE001
            results.append(pc.errno_doc(exc))
    return {"connections": count,
            "codes": {str(code): results.count(code) for code in set(map(str, results))}}


def mode_valid() -> dict:
    return pc.exchange(
        pc.envelope_bytes(pc.request_payload(session="g3d-d2-12-valid"),
                          transport_id="tr-" + "d" * 32), timeout=8.0)


def main() -> int:
    mode = arg("--mode", "fork") or "fork"
    count = int(arg("--count", "8") or "8")
    document = {"probe": "d2-12", "mode": mode, "identity": pc.identity(),
                "ops": {}, "limits": {
                    "nofile": resource.getrlimit(resource.RLIMIT_NOFILE),
                    "pids_max": None, "memory_max": None}}
    for path in ("/sys/fs/cgroup/pids.max", "/sys/fs/cgroup/memory.max",
                 "/sys/fs/cgroup/cpu.max", "/sys/fs/cgroup/memory.events",
                 "/sys/fs/cgroup/pids.current", "/sys/fs/cgroup/memory.current"):
        try:
            document["limits"][path] = open(path, encoding="utf-8").read().strip()
        except OSError as exc:
            document["limits"][path] = pc.errno_doc(exc)
    started = time.monotonic()
    if mode == "fork":
        document["ops"] = mode_fork()
    elif mode == "memory":
        document["ops"] = mode_memory()
    elif mode == "fd":
        document["ops"] = mode_fd()
    elif mode == "connections":
        document["ops"] = mode_connections(count)
    elif mode == "flood":
        document["ops"] = mode_flood(count)
    elif mode == "valid":
        document["ops"] = mode_valid()
    else:
        document["ops"] = {"error": f"unknown mode {mode}"}
    document["wall_seconds"] = round(time.monotonic() - started, 3)
    for path in ("/sys/fs/cgroup/memory.events", "/sys/fs/cgroup/pids.current"):
        try:
            document["limits_after:" + path] = open(path, encoding="utf-8").read().strip()
        except OSError as exc:
            document["limits_after:" + path] = pc.errno_doc(exc)
    pc.emit(document)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
