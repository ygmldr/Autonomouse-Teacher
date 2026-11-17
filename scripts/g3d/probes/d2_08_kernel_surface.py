#!/usr/bin/env python3
"""D2-08: /proc, FD, environ, /sys, /dev, mount, ptrace, cap, userns surface."""
from __future__ import annotations

import ctypes
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import probe_common as pc  # noqa: E402

LIBC = ctypes.CDLL(None, use_errno=True)


def _fail_errno() -> OSError:
    err = ctypes.get_errno()
    return OSError(err, os.strerror(err))


def do_mount(source: bytes, target: bytes, fstype: bytes, flags: int = 0,
             data: bytes = b"") -> str:
    ctypes.set_errno(0)
    if LIBC.mount(source, target, fstype, flags, data) != 0:
        raise _fail_errno()
    return "mounted"


def do_unshare(flags: int) -> str:
    ctypes.set_errno(0)
    if LIBC.unshare(flags) != 0:
        raise _fail_errno()
    return "unshared"


def do_ptrace(pid: int) -> str:
    ctypes.set_errno(0)
    if LIBC.ptrace(16, pid, None, None) != 0:  # PTRACE_ATTACH
        raise _fail_errno()
    return "attached"


def status_caps() -> dict:
    wanted = {"Uid", "Gid", "CapEff", "CapBnd", "CapPrm", "NoNewPrivs",
              "Seccomp", "Seccomp_filters"}
    result: dict = {}
    for line in open("/proc/self/status", encoding="utf-8").read().splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            if key in wanted:
                result[key] = value.strip()
    return result


def main() -> int:
    trusted_pid = None
    for index, token in enumerate(sys.argv):
        if token == "--trusted-pid" and index + 1 < len(sys.argv):
            trusted_pid = int(sys.argv[index + 1])
    document = {"probe": "d2-08", "identity": pc.identity(), "ops": [],
                "pre_unshare_status": status_caps(), "post_unshare_status": None,
                "userns": {}, "trusted_pid": trusted_pid}
    os.makedirs("/tmp/d2-mnt-a", exist_ok=True)
    os.makedirs("/tmp/d2-mnt-b", exist_ok=True)
    document["ops"].append(pc.attempt(
        "mount_tmpfs_original_ns",
        lambda: do_mount(b"none", b"/tmp/d2-mnt-a", b"tmpfs", 0, b"size=1m")))
    document["ops"].append(pc.attempt(
        "ptrace_self_init", lambda: do_ptrace(1)))
    if trusted_pid:
        document["ops"].append(pc.attempt(
            "ptrace_trusted_host_pid", lambda: do_ptrace(trusted_pid)))
        for suffix in ("environ", "fd", "root", "cwd", "cmdline", "status",
                       "maps", "mountinfo"):
            document["ops"].append(pc.attempt(
                "read_trusted_" + suffix,
                lambda s=suffix: pc.open_read(f"/proc/{trusted_pid}/{s}")))
    document["ops"].append(pc.attempt(
        "read_proc_environ_self",
        lambda: open("/proc/1/environ", "rb").read(4096)))
    document["ops"].append(pc.attempt(
        "read_proc_kcore", lambda: pc.open_read("/proc/kcore")))
    document["ops"].append(pc.attempt(
        "read_proc_keys", lambda: pc.open_read("/proc/keys")))
    document["ops"].append(pc.attempt(
        "read_proc_sysrq_trigger",
        lambda: pc.open_read("/proc/sysrq-trigger")))
    document["ops"].append(pc.attempt(
        "read_proc_1_fd", lambda: sorted(os.listdir("/proc/1/fd"))))
    document["ops"].append(pc.attempt(
        "read_proc_self_fd", lambda: sorted(os.listdir("/proc/self/fd"))))
    document["fd_targets"] = pc.fd_targets()
    document["ops"].append(pc.attempt(
        "write_core_pattern",
        lambda: pc.open_flags("/proc/sys/kernel/core_pattern",
                              os.O_WRONLY | os.O_TRUNC, write=b"|/tmp/x")))
    document["ops"].append(pc.attempt(
        "write_hostname",
        lambda: pc.open_flags("/proc/sys/kernel/hostname",
                              os.O_WRONLY | os.O_TRUNC, write=b"x")))
    document["ops"].append(pc.attempt(
        "write_sys_kernel_uevent",
        lambda: pc.open_flags("/sys/kernel/uevent_seqnum",
                              os.O_WRONLY | os.O_TRUNC, write=b"1")))
    document["ops"].append(pc.attempt(
        "read_dev_mem", lambda: pc.open_read("/dev/mem")))
    document["ops"].append(pc.attempt(
        "read_dev_kmsg", lambda: pc.open_read("/dev/kmsg")))
    document["ops"].append(pc.attempt(
        "write_dev_kmsg", lambda: pc.open_flags("/dev/kmsg",
                                                os.O_WRONLY | os.O_APPEND,
                                                write=b"x")))
    document["ops"].append(pc.attempt(
        "read_work_state", lambda: pc.open_read("/work/state/broker.sqlite3")))
    document["ops"].append(pc.attempt(
        "list_work_state", lambda: sorted(os.listdir("/work/state"))))
    document["ops"].append(pc.attempt(
        "unshare_user", lambda: do_unshare(0x10000000)))
    document["post_unshare_status"] = status_caps()
    document["ops"].append(pc.attempt(
        "unshare_mount", lambda: do_unshare(0x00020000)))
    document["ops"].append(pc.attempt(
        "mount_tmpfs_nested_userns",
        lambda: do_mount(b"none", b"/tmp/d2-mnt-b", b"tmpfs", 0, b"size=1m")))
    if trusted_pid:
        document["ops"].append(pc.attempt(
            "read_trusted_after_userns",
            lambda: pc.open_read(f"/proc/{trusted_pid}/environ")))
    document["ops"].append(pc.attempt(
        "read_work_state_after_userns",
        lambda: pc.open_read("/work/state/broker.sqlite3")))
    document["ops"].append(pc.attempt(
        "setuid_0", lambda: os.setuid(0)))
    document["uid_map_after"] = open("/proc/self/uid_map",
                                     encoding="utf-8").read().strip()
    document["gid_map_after"] = open("/proc/self/gid_map",
                                     encoding="utf-8").read().strip()
    document["userns"] = {
        "nested_unshare_ok": any(
            op["id"] == "unshare_user" and op["ok"] for op in document["ops"]),
        "nested_mount_ok": any(
            op["id"] == "mount_tmpfs_nested_userns" and op["ok"]
            for op in document["ops"]),
        "trusted_path_after": [op for op in document["ops"]
                               if op["id"] in {"read_trusted_after_userns",
                                               "read_work_state_after_userns"}],
        "note": "nested userns is an expected kernel feature for unprivileged "
                "processes; it never grants access to Trusted UID-0 0700 state",
    }
    pc.emit(document)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
