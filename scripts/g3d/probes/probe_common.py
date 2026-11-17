#!/usr/bin/env python3
"""Shared helpers for the D2 Candidate-side adversarial probes.

These probes run **inside the real Candidate container** (``podman exec`` or as
the container entrypoint) and use only real syscalls/sockets. They never import
the trusted package, never read a Key and never fabricate a "denied" result:
every operation records the kernel errno or the real protocol frame it got.

Evidence is one line ``PROBE <json>`` on stdout. The Host Launcher parses the
raw document and re-checks the expected errno/codes; nothing here is trusted to
decide the Gate.
"""
from __future__ import annotations

import errno
import hashlib
import json
import os
from pathlib import Path
import socket
import stat
import sys
import time
from datetime import datetime, timezone

SOCKET_PATH = "/work/g3b/bridge.sock"
IPC_DIR = "/work/g3b"
STATE_DIR = "/work/state"
SESSION_DIR = "/work/session"
ROUTE = "offline-test-only-g3b"
MODEL = "fixture-bridge-v1"
MAX_TRACE_BYTES = 4096


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str | os.PathLike[str]) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def status_fields() -> dict:
    wanted = {"Uid", "Gid", "Groups", "CapEff", "CapBnd", "CapPrm", "NoNewPrivs",
              "Seccomp", "Pid", "NSpid", "Threads"}
    result: dict = {}
    try:
        text = Path("/proc/self/status").read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {"error": type(exc).__name__}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        if key in wanted:
            result[key] = value.strip()
    return result


def mount_rows() -> list[dict]:
    rows: list[dict] = []
    try:
        text = Path("/proc/self/mountinfo").read_text(encoding="utf-8",
                                                      errors="replace")
    except OSError:
        return rows
    for line in text.splitlines():
        fields = line.split()
        if "-" not in fields or fields.index("-") < 5:
            continue
        index = fields.index("-")
        rows.append({
            "mount_point": fields[4],
            "mount_options": fields[5],
            "fstype": fields[index + 1] if len(fields) > index + 1 else None,
            "source": fields[index + 2] if len(fields) > index + 2 else None,
            "super_options": fields[index + 3] if len(fields) > index + 3 else None,
        })
    return rows


def proc_pids() -> list[int]:
    try:
        return sorted(int(name) for name in os.listdir("/proc") if name.isdigit())
    except OSError:
        return []


def identity() -> dict:
    uid_map = gid_map = None
    try:
        uid_map = Path("/proc/self/uid_map").read_text(encoding="utf-8").strip()
        gid_map = Path("/proc/self/gid_map").read_text(encoding="utf-8").strip()
    except OSError:
        pass
    return {
        "utc": utc(),
        "uid": os.getuid(),
        "gid": os.getgid(),
        "groups": os.getgroups(),
        "uid_map": uid_map,
        "gid_map": gid_map,
        "status": status_fields(),
        "pid": os.getpid(),
        "ppid": os.getppid(),
        "argv": list(sys.argv),
        "cwd": os.getcwd(),
        "env_names": sorted(os.environ),
        "pids_visible": proc_pids(),
        "mounts": mount_rows(),
        "python": sys.version.split()[0],
    }


def errno_doc(exc: BaseException) -> dict:
    if isinstance(exc, OSError):
        return {"errno": exc.errno,
                "errno_name": errno.errorcode.get(exc.errno, str(exc.errno)),
                "message": exc.strerror}
    return {"type": type(exc).__name__, "message": str(exc)[:400]}


def attempt(op_id: str, callable_, **detail: object) -> dict:
    """Run one real syscall and return a stable evidence record."""
    record: dict = {"id": op_id, **detail}
    try:
        result = callable_()
        record["ok"] = True
        if isinstance(result, (bool, int, str, type(None))):
            record["result"] = result
        elif isinstance(result, (dict, list, tuple)):
            record["result"] = result
        elif isinstance(result, (bytes, bytearray)):
            record["result"] = {"bytes": len(result),
                                "sha256": sha256_bytes(bytes(result))}
        else:
            record["result"] = str(result)[:400]
    except BaseException as exc:  # noqa: BLE001 - the failure is the evidence
        record["ok"] = False
        record.update(errno_doc(exc))
    return record


def open_read(path: str, limit: int = 64) -> dict:
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC)
    try:
        data = os.read(fd, limit)
        return {"bytes_read": len(data), "sha256_prefix": sha256_bytes(data)}
    finally:
        os.close(fd)


def open_flags(path: str, flags: int, *, mode: int = 0o600,
               write: bytes | None = None) -> dict:
    fd = os.open(path, flags | os.O_CLOEXEC, mode)
    try:
        if write is not None:
            os.write(fd, write)
        return {"opened": True}
    finally:
        os.close(fd)


def readlink(path: str) -> str:
    return os.readlink(path)


def fd_targets() -> list[dict]:
    rows: list[dict] = []
    for name in sorted(os.listdir("/proc/self/fd"), key=lambda value: int(value)):
        path = f"/proc/self/fd/{name}"
        try:
            rows.append({"fd": int(name), "target": os.readlink(path)})
        except OSError as exc:
            rows.append({"fd": int(name), **errno_doc(exc)})
    return rows


def connect_unix(path: str, timeout: float = 2.0) -> socket.socket:
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect(path)
    except BaseException:
        sock.close()
        raise
    return sock


def canonical(payload: object) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def payload_digest(payload: object) -> str:
    return sha256_bytes(canonical(payload))


def request_payload(*, session: str = "g3d-d2-attack",
                    provider: str = ROUTE, model: str = MODEL,
                    messages: list | None = None, tools: list | None = None,
                    system: object = None, max_tokens: int = 256,
                    purpose: object = None) -> dict:
    return {"sessionId": session, "provider": provider, "model": model,
            "messages": [] if messages is None else messages,
            "tools": [] if tools is None else tools,
            "system": system, "maxTokens": max_tokens, "stream": True,
            "purpose": purpose}


def envelope_bytes(payload: object, *, kind: str = "request",
                   transport_id: str = "tr-" + "a" * 32, seq: int = 0,
                   include_hash: bool = True,
                   extra_envelope: dict | None = None) -> bytes:
    document = {"v": 1, "kind": kind, "transport_id": transport_id,
                "seq": seq, "payload": payload}
    if include_hash:
        document["hash"] = payload_digest(payload)
    if extra_envelope:
        document.update(extra_envelope)
    return canonical(document) + b"\n"


def read_frames(sock: socket.socket, *, timeout: float = 5.0,
                max_frames: int = 64) -> dict:
    """Read newline JSON frames until EOF/terminal/timeout; never unbounded."""
    frames: list[dict] = []
    raw_lines: list[str] = []
    buffer = b""
    deadline = time.monotonic() + max(0.1, timeout)
    read_error = None
    eof = False
    while time.monotonic() < deadline and len(frames) < max_frames:
        remaining = max(0.1, deadline - time.monotonic())
        sock.settimeout(remaining)
        try:
            chunk = sock.recv(65536)
        except socket.timeout:
            break
        except OSError as exc:
            read_error = errno_doc(exc)
            break
        if not chunk:
            eof = True
            break
        buffer += chunk
        while b"\n" in buffer:
            line, buffer = buffer.split(b"\n", 1)
            text = line[:MAX_TRACE_BYTES].decode("utf-8", "replace")
            raw_lines.append(text)
            try:
                frames.append(json.loads(text))
            except json.JSONDecodeError:
                frames.append({"invalid_json": text[:256]})
        if frames and frames[-1].get("kind") in {"finish", "error"}:
            break
    terminal = None
    error_code = None
    if frames:
        terminal = frames[-1].get("kind")
        payload = frames[-1].get("payload")
        if isinstance(payload, dict):
            error_code = payload.get("code")
    return {"frames": frames, "frame_count": len(frames),
            "raw_lines": raw_lines, "terminal": terminal,
            "error_code": error_code, "eof": eof,
            "read_error": read_error, "partial_buffer_bytes": len(buffer)}


def exchange(frame: bytes, *, path: str = SOCKET_PATH, timeout: float = 6.0,
             shutdown_write: bool = False) -> dict:
    record: dict = {"path": path, "bytes_sent": len(frame)}
    sock = None
    try:
        sock = connect_unix(path, timeout=min(2.0, timeout))
        record["connected"] = True
        sock.sendall(frame)
        record["sent"] = True
        if shutdown_write:
            try:
                sock.shutdown(socket.SHUT_WR)
                record["half_closed_write"] = True
            except OSError as exc:
                record["half_closed_write"] = False
                record["shutdown_error"] = errno_doc(exc)
        record.update(read_frames(sock, timeout=timeout))
    except BaseException as exc:  # noqa: BLE001
        record["connected"] = record.get("connected", False)
        record["error"] = errno_doc(exc)
    finally:
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
    return record


def socket_stat(path: str) -> dict:
    info = os.lstat(path)
    return {"path": path, "mode": stat.S_IMODE(info.st_mode),
            "mode_octal": format(stat.S_IMODE(info.st_mode), "04o"),
            "uid": info.st_uid, "gid": info.st_gid, "inode": info.st_ino,
            "is_socket": stat.S_ISSOCK(info.st_mode)}


def bounded_walk(roots: list[str], names: set[str], *, max_entries: int = 20000,
                 skip: tuple[str, ...] = ("node_modules", "native-cache",
                                          "pkg-cache", ".git")) -> dict:
    """Bounded search for protected basenames; never follows symlinks."""
    matches: list[str] = []
    visited = 0
    truncated = False
    for root in roots:
        base = Path(root)
        if not base.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
            dirnames[:] = [name for name in dirnames if name not in skip]
            for name in filenames:
                visited += 1
                if visited > max_entries:
                    truncated = True
                    break
                if name in names:
                    matches.append(str(Path(dirpath) / name))
            if truncated:
                break
        if truncated:
            break
    return {"roots": roots, "entries_visited": visited,
            "name_matches": sorted(matches), "truncated": truncated,
            "names": sorted(names)}


def emit(document: dict) -> None:
    print("PROBE " + json.dumps(document, sort_keys=True, default=str),
          flush=True)


def main_guard(name: str) -> None:
    """Keep one probe per process; a missing/short argv fails closed."""
    if not name:
        raise SystemExit("probe name required")
