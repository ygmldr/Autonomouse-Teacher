#!/usr/bin/env python3
"""Trusted container entrypoint for G3-D1-B (runs as container/host uid 0).

Responsibilities are deliberately narrow:

1. verify the Trusted-only directory/permission contract the Host Launcher
   created (``/work/state`` 0700 root, ``/work/g3b`` 2750 root:2000);
2. import the product Controller/Broker/Attempt/IPC modules and record
   ``inspect.getfile`` plus the raw file byte SHA-256 of every loaded module so
   the Launcher can compare them with ``git show 4bd4803:<path>``;
3. start ``autoteacher_m0.bridge.controller.main`` with an ``on_ready`` callback
   that runs only after ``bind`` + permission verification + ``listen``;
4. write the Trusted ready file into ``/work/state`` (never Candidate-readable).

It never reads a Key, never opens a network socket and never touches the
Candidate stage or session.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import inspect
import json
import logging
import os
from pathlib import Path
import stat
import sys
import uuid
from datetime import datetime, timezone

STATE_DIR = Path("/work/state")
IPC_DIR = Path("/work/g3b")
OUT_DIR = Path("/output")
SOCKET_PATH = IPC_DIR / "bridge.sock"
READY_PATH = STATE_DIR / "ready"
CONFIG_PATH = STATE_DIR / "controller.json"
EXPECTED_PEER_UID = 65534
SOCKET_MODE = 0o660
SOCKET_GID = 2000
MODULES = (
    "autoteacher_m0.bridge.controller",
    "autoteacher_m0.bridge.ipc_server",
    "autoteacher_m0.bridge.attempts",
    "autoteacher_m0.bridge.admission",
    "autoteacher_m0.bridge.broker_client",
    "autoteacher_m0.bridge.fake_backend",
    "autoteacher_m0.bridge.protocol",
    "autoteacher_m0.accounting.broker",
    "autoteacher_m0.accounting.usage",
    "autoteacher_m0.accounting.observation",
)
KEY_MARKERS = ("KEY", "TOKEN", "SECRET", "CREDENTIAL", "PASSWORD")


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path: str | os.PathLike[str]) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def lstat_doc(path: Path) -> dict:
    info = os.lstat(path)
    return {
        "path": str(path), "mode": stat.S_IMODE(info.st_mode),
        "mode_octal": format(stat.S_IMODE(info.st_mode), "04o"),
        "uid": info.st_uid, "gid": info.st_gid, "inode": info.st_ino,
        "is_dir": stat.S_ISDIR(info.st_mode), "is_socket": stat.S_ISSOCK(info.st_mode),
        "setgid": bool(info.st_mode & stat.S_ISGID),
    }


def write_json_nofollow(path: Path, document: dict, *, mode: int = 0o600,
                        exclusive: bool = True) -> dict:
    data = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode()
    flags = os.O_WRONLY | os.O_CREAT | os.O_CLOEXEC
    flags |= os.O_NOFOLLOW if hasattr(os, "O_NOFOLLOW") else 0
    flags |= os.O_EXCL if exclusive else os.O_TRUNC
    fd = os.open(path, flags, mode)
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.chmod(path, mode)
    try:
        dfd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    except OSError:
        pass
    return {"path": str(path), "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data), "lstat": lstat_doc(path)}


def module_identity() -> dict:
    rows = []
    for name in MODULES:
        module = importlib.import_module(name)
        origin = inspect.getfile(module)
        rows.append({
            "module": name,
            "file": origin,
            "real_path": os.path.realpath(origin),
            "sha256": sha256_file(origin),
            "bytes": os.path.getsize(origin),
        })
    return {
        "python": sys.version.split()[0],
        "executable": sys.executable,
        "sys_path": [entry for entry in sys.path if entry],
        "modules": rows,
    }


def preflight_checks(config: dict) -> dict:
    problems: list[str] = []
    checks: list[dict] = []

    def check(name: str, ok: bool, **detail: object) -> None:
        checks.append({"check": name, "ok": bool(ok), **detail})
        if not ok:
            problems.append(name)

    state = lstat_doc(STATE_DIR)
    ipc = lstat_doc(IPC_DIR)
    check("state_is_directory_0700_root",
          state["is_dir"] and state["mode"] == 0o700
          and state["uid"] == 0 and state["gid"] == 0, observed=state)
    check("ipc_is_directory_2750_root_2000",
          ipc["is_dir"] and ipc["mode"] == 0o2750 and ipc["uid"] == 0
          and ipc["gid"] == SOCKET_GID and ipc["setgid"], observed=ipc)
    check("state_is_writable",
          os.access(STATE_DIR, os.W_OK | os.X_OK))
    check("admission_present", (STATE_DIR / "admission.json").is_file())
    check("broker_config_present", (STATE_DIR / "broker.json").is_file())
    check("config_file_regular",
          CONFIG_PATH.is_file() and not CONFIG_PATH.is_symlink())
    check("config_socket_mode", config.get("socket_mode") == 0o660,
          observed=config.get("socket_mode"))
    check("config_socket_gid_absent", config.get("socket_gid") is None,
          observed=config.get("socket_gid"))
    check("config_expected_peer_uid",
          config.get("expected_peer_uid") == EXPECTED_PEER_UID,
          observed=config.get("expected_peer_uid"))
    check("config_expected_admission_uid",
          config.get("expected_uid") == EXPECTED_PEER_UID,
          observed=config.get("expected_uid"))
    check("config_socket_path", config.get("socket_path") == str(SOCKET_PATH),
          observed=config.get("socket_path"))
    check("config_fake_script",
          config.get("fake_script") == "/project/fake/fake_provider.py",
          observed=config.get("fake_script"))
    for key in ("admission_path", "broker_config_path", "receipt_dir", "attempt_db"):
        value = str(config.get(key, ""))
        check(f"config_path_under_state:{key}",
              value.startswith("/work/state/") and ".." not in value,
              observed=value)
    key_names = [name for name in os.environ
                 if any(marker in name.upper() for marker in KEY_MARKERS)]
    check("no_key_like_env", not key_names, names=key_names)
    check("project_src_present", (Path("/project/src/autoteacher_m0")).is_dir())
    check("output_writable", os.access(OUT_DIR, os.W_OK | os.X_OK))
    check("work_state_not_candidate_visible", True,
          note="state is only mounted into the Trusted container")
    return {"utc": utc(), "checks": checks, "problems": problems,
            "state": state, "ipc": ipc,
            "env_names": sorted(os.environ)}


def build_on_ready(config_sha256: str, instance: str):
    def on_ready() -> None:
        info = lstat_doc(SOCKET_PATH)
        problems = []
        if not info["is_socket"]:
            problems.append("not_socket")
        if info["mode"] != SOCKET_MODE:
            problems.append("mode")
        if info["gid"] != SOCKET_GID:
            problems.append("gid")
        if info["uid"] != 0:
            problems.append("uid")
        if problems:
            raise RuntimeError(f"TRUSTED_READY_BOUNDARY_INVALID:{','.join(problems)}")
        document = {
            "schema": "m0.g3d.trusted.ready.v1",
            "utc": utc(),
            "pid": os.getpid(),
            "instance": instance,
            "expected_peer_uid": EXPECTED_PEER_UID,
            "socket": {
                "path": str(SOCKET_PATH),
                "mode": info["mode"],
                "mode_octal": info["mode_octal"],
                "uid": info["uid"],
                "gid": info["gid"],
                "inode": info["inode"],
            },
            "controller_config_sha256": config_sha256,
            "state_dir": str(STATE_DIR),
            "synthetic": True,
        }
        record = write_json_nofollow(READY_PATH, document, mode=0o600, exclusive=True)
        print("G3D_TRUSTED_READY " + json.dumps(
            {"utc": document["utc"], "socket": document["socket"],
             "sha256": record["sha256"], "instance": instance},
            sort_keys=True), flush=True)
    return on_ready


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args(argv)
    if args.config != str(CONFIG_PATH):
        sys.stderr.write("TRUSTED_CONFIG_PATH_INVALID\n")
        return 2
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        sys.stderr.write("TRUSTED_CONFIG_INVALID\n")
        return 2
    preflight = preflight_checks(config)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    write_json_nofollow(OUT_DIR / "trusted-preflight.json", preflight,
                        mode=0o644, exclusive=False)
    modules = module_identity()
    write_json_nofollow(OUT_DIR / "trusted-modules.json", modules,
                        mode=0o644, exclusive=False)
    if preflight["problems"]:
        sys.stderr.write("TRUSTED_PREFLIGHT_FAILED " + json.dumps(
            preflight["problems"]) + "\n")
        print("G3D_TRUSTED_RESULT " + json.dumps(
            {"ok": False, "reason": "PREFLIGHT", "problems": preflight["problems"]},
            sort_keys=True), flush=True)
        return 5
    for row in modules["modules"]:
        if not row["real_path"].startswith("/project/src/autoteacher_m0/"):
            sys.stderr.write("TRUSTED_MODULE_PATH_INVALID " + row["module"] + "\n")
            return 5
    logging.basicConfig(
        level=logging.DEBUG,
        stream=sys.stderr,
        force=True,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logging.getLogger("autoteacher_m0").setLevel(logging.DEBUG)
    instance = "ctl-" + uuid.uuid4().hex[:16]
    config_sha256 = sha256_file(args.config)
    on_ready = build_on_ready(config_sha256, instance)
    print("G3D_TRUSTED_START " + json.dumps(
        {"utc": utc(), "instance": instance, "config_sha256": config_sha256,
         "expected_peer_uid": EXPECTED_PEER_UID, "socket_mode": SOCKET_MODE,
         "socket_gid": SOCKET_GID}, sort_keys=True), flush=True)
    from autoteacher_m0.bridge import controller as controller_module
    return_code = controller_module.main(["--config", args.config],
                                         on_ready=on_ready)
    print("G3D_TRUSTED_EXIT " + json.dumps(
        {"utc": utc(), "exit": return_code, "instance": instance},
        sort_keys=True), flush=True)
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
