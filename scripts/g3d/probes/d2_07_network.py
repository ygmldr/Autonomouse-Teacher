#!/usr/bin/env python3
"""D2-07: Candidate external network / DNS / other Unix socket probes."""
from __future__ import annotations

import os
import socket
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import probe_common as pc  # noqa: E402

TARGETS = (
    ("podman", "/run/podman/podman.sock"),
    ("docker", "/var/run/docker.sock"),
    ("systemd_private", "/run/systemd/private"),
    ("dbus", "/run/dbus/system_bus_socket"),
    ("host_bridge", "/root/Autonomous Teacher/artifacts/g3d/runs"),
    ("bridge", pc.SOCKET_PATH),
)
ABSTRACT_TARGETS = (
    ("podman_abstract", "\0/run/podman/podman.sock"),
    ("docker_abstract", "\0/var/run/docker.sock"),
)


def main() -> int:
    document = {"probe": "d2-07", "identity": pc.identity(), "ops": [],
                "unix": [], "abstract": [], "interfaces": None,
                "routes": None, "net_unix": None}

    def probe_family(family: int, address: tuple) -> dict:
        def run() -> dict:
            sock = socket.socket(family, socket.SOCK_STREAM)
            try:
                sock.settimeout(1.0)
                sock.connect(address)
                return {"connected": True}
            finally:
                sock.close()
        return pc.attempt(f"connect_{family}_{address[0]}", run)

    document["ops"].append(pc.attempt(
        "socket_af_inet", lambda: socket.socket(socket.AF_INET,
                                                socket.SOCK_STREAM).close()))
    document["ops"].append(pc.attempt(
        "socket_af_inet6", lambda: socket.socket(socket.AF_INET6,
                                                 socket.SOCK_STREAM).close()))
    document["ops"].append(probe_family(socket.AF_INET, ("192.0.2.1", 9)))
    document["ops"].append(probe_family(socket.AF_INET6, ("::1", 9)))
    document["ops"].append(pc.attempt(
        "socket_af_inet_udp", lambda: socket.socket(socket.AF_INET,
                                                    socket.SOCK_DGRAM).close()))
    document["ops"].append(pc.attempt(
        "socket_af_netlink", lambda: socket.socket(socket.AF_NETLINK,
                                                   socket.SOCK_RAW, 0).close()))
    document["ops"].append(pc.attempt(
        "dns_example_invalid",
        lambda: socket.getaddrinfo("example.invalid", 443,
                                   type=socket.SOCK_STREAM)))
    document["ops"].append(pc.attempt(
        "dns_public_name",
        lambda: socket.getaddrinfo("pypi.org", 443, type=socket.SOCK_STREAM)))
    try:
        document["interfaces"] = [name for _, name in socket.if_nameindex()]
    except OSError as exc:
        document["interfaces"] = {"error": pc.errno_doc(exc)}
    try:
        document["routes"] = open("/proc/net/route", encoding="utf-8",
                                  errors="replace").read().splitlines()
    except OSError as exc:
        document["routes"] = {"error": pc.errno_doc(exc)}
    for name, path in TARGETS:
        def connect(path: str = path) -> dict:
            sock = pc.connect_unix(path, timeout=1.0)
            try:
                return {"connected": True}
            finally:
                sock.close()
        document["unix"].append({**pc.attempt("connect:" + name, connect),
                                 "path": path})
    for name, path in ABSTRACT_TARGETS:
        def connect(path: str = path) -> dict:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(1.0)
            try:
                sock.connect(path)
                return {"connected": True}
            finally:
                sock.close()
        document["abstract"].append({**pc.attempt("connect:" + name, connect),
                                     "path": path})
    try:
        document["net_unix"] = open("/proc/net/unix", encoding="utf-8",
                                    errors="replace").read().splitlines()[:40]
    except OSError as exc:
        document["net_unix"] = {"error": pc.errno_doc(exc)}
    pc.emit(document)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
