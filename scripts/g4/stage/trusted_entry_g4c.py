#!/usr/bin/env python3
"""G4-C trusted container entrypoint (runs as container/host uid 0).

Differences from the frozen G3-D ``trusted_entry.py`` (which is **not** modified):

1. records the full actual import closure, including ``security.egress`` and
   ``security.authorization`` (the G3-D list is a hardcoded 10-module subset);
2. loads the trusted launcher-owned G4-C dispatch policy, recomputes the 15
   component binding closure from ``/project`` files plus declared inputs,
   and refuses to start on ``pre_start`` drift;
3. constructs ``TrustedSendGate`` with the frozen ``SYNTHETIC_ROUTE_CONTRACT``
   and the G4-A ``binding_drift("pre_dispatch", ...)`` check, passes it to
   ``controller.main(dispatch_gate=...)``, and writes the egress snapshot to
   ``/output/g4c-egress.json`` after the Controller shuts down.

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
from decimal import Decimal

STATE_DIR = Path("/work/state")
IPC_DIR = Path("/work/g3b")
OUT_DIR = Path("/output")
SOCKET_PATH = IPC_DIR / "bridge.sock"
READY_PATH = STATE_DIR / "ready"
CONFIG_PATH = STATE_DIR / "controller.json"
POLICY_PATH = STATE_DIR / "g4c-policy.json"
JOURNAL_PATH = STATE_DIR / "g4c-send-journal.jsonl"
PROJECT_ROOT = Path("/project")
EXPECTED_PEER_UID = 65534
SOCKET_MODE = 0o660
SOCKET_GID = 2000
POLICY_SCHEMA = "m0.g4c.dispatch-policy.v1"
MODULES = (
    "autoteacher_m0.bridge.controller",
    "autoteacher_m0.bridge.dispatch_audit",
    "autoteacher_m0.bridge.ipc_server",
    "autoteacher_m0.bridge.attempts",
    "autoteacher_m0.bridge.admission",
    "autoteacher_m0.bridge.broker_client",
    "autoteacher_m0.bridge.fake_backend",
    "autoteacher_m0.bridge.protocol",
    "autoteacher_m0.accounting.broker",
    "autoteacher_m0.accounting.usage",
    "autoteacher_m0.accounting.observation",
    "autoteacher_m0.security.egress",
    "autoteacher_m0.security.authorization",
    "autoteacher_m0.security.ed25519",
    "autoteacher_m0.security.gates",
    "autoteacher_m0.security.live_controller",
    "autoteacher_m0.security.credential_boundary",
    "autoteacher_m0.security.watchdog",
)
KEY_MARKERS = ("KEY", "TOKEN", "SECRET", "CREDENTIAL", "PASSWORD")


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str | os.PathLike[str]) -> str:
    return sha256_bytes(Path(path).read_bytes())


def canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


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
    return {"path": str(path), "sha256": sha256_bytes(data),
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


def _read_policy() -> dict:
    if POLICY_PATH.is_symlink():
        raise SystemExit("G4C_POLICY_SYMLINKED")
    info = os.lstat(POLICY_PATH)
    if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o022:
        raise SystemExit("G4C_POLICY_PERMISSIONS_INVALID")
    if info.st_uid != 0 or not 0 < info.st_size <= 1 << 20:
        raise SystemExit("G4C_POLICY_INVALID")
    try:
        document = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise SystemExit("G4C_POLICY_INVALID")
    if not isinstance(document, dict) or document.get("schema") != POLICY_SCHEMA:
        raise SystemExit("G4C_POLICY_SCHEMA_INVALID")
    return document


def _component_digest(entries: list[list[str]]) -> str:
    return sha256_bytes(canonical_json(sorted(entries)))


def _closure_components(policy: dict) -> tuple[dict[str, str], list[dict]]:
    """Recompute all 15 component digests from /project plus declared inputs."""
    closure = policy["binding"]["closure"]
    components = closure.get("components")
    if not isinstance(components, dict):
        raise SystemExit("G4C_POLICY_CLOSURE_INVALID")
    digests: dict[str, str] = {}
    audit: list[dict] = []
    for name, entry in components.items():
        if not isinstance(entry, dict):
            raise SystemExit("G4C_POLICY_CLOSURE_INVALID")
        files = entry.get("files") or []
        entries: list[list[str]] = []
        modes = []
        for item in files:
            path = item.get("path")
            declared = item.get("sha256")
            if not isinstance(path, str) or not isinstance(declared, str):
                raise SystemExit("G4C_POLICY_CLOSURE_INVALID")
            container_path = item.get("container_path")
            actual = declared
            if container_path is not None:
                target = PROJECT_ROOT / container_path
                if target.is_symlink() or not target.is_file():
                    raise SystemExit(f"G4C_OBSERVED_FILE_MISSING:{container_path}")
                actual = sha256_file(target)
                if actual != declared:
                    raise SystemExit(
                        f"G4C_PRE_START_BINDING_DRIFT:{name}:{path}")
                modes.append("recomputed")
            else:
                modes.append("declared")
            entries.append([path, actual])
        if files:
            digest = _component_digest(entries)
        else:
            external = entry["external"]
            content = canonical_json(external["document"])
            if sha256_bytes(content) != external["sha256"]:
                raise SystemExit(f"G4C_EXTERNAL_DOCUMENT_INVALID:{name}")
            digest = _component_digest([["EXTERNAL.json", external["sha256"]]])
            modes.append("declared-external")
        digests[name] = digest
        audit.append({"component": name, "digest": digest,
                      "modes": sorted(set(modes)),
                      "files": len(files)})
    return digests, audit


def _bindings_from(components: dict[str, str]):
    from autoteacher_m0.security.authorization import ExpectedBindings
    return ExpectedBindings.from_closure(components)


def _observed_bindings(policy: dict):
    digests, _audit = _closure_components(policy)
    return _bindings_from(digests)


def preflight_checks(config: dict, policy: dict) -> dict:
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
    check("state_is_writable", os.access(STATE_DIR, os.W_OK | os.X_OK))
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
    check("project_src_present", (PROJECT_ROOT / "src" / "autoteacher_m0").is_dir())
    check("output_writable", os.access(OUT_DIR, os.W_OK | os.X_OK))
    check("policy_present", POLICY_PATH.is_file() and not POLICY_PATH.is_symlink())
    check("policy_synthetic", policy.get("synthetic") is True)
    check("policy_route_kind",
          policy.get("route_contract", {}).get("route_kind") == "synthetic_fixture",
          observed=policy.get("route_contract", {}).get("route_kind"))
    check("policy_no_real_calls",
          policy.get("real_model_calls") == 0
          and policy.get("real_external_http_calls") == 0)
    check("policy_binding_checkpoint",
          policy.get("binding", {}).get("checkpoint") == "pre_dispatch")
    check("work_state_not_candidate_visible", True,
          note="state is only mounted into the Trusted container")
    return {"utc": utc(), "checks": checks, "problems": problems,
            "state": state, "ipc": ipc, "env_names": sorted(os.environ)}


def _build_gate(policy: dict):
    from autoteacher_m0.security.authorization import binding_drift
    from autoteacher_m0.security.egress import (
        ProviderRouteContract, SyntheticSendBudget, TrustedSendGate,
    )

    contract = ProviderRouteContract.from_mapping(policy["route_contract"])
    budget_raw = policy["budget"]
    budget = SyntheticSendBudget(
        soft_total_usd=Decimal(budget_raw["soft_total_usd"]),
        hard_total_usd=Decimal(budget_raw["hard_total_usd"]),
        soft_call_usd=Decimal(budget_raw["soft_call_usd"]),
        hard_call_usd=Decimal(budget_raw["hard_call_usd"]),
        max_sends=int(budget_raw["max_sends"]))
    approved_raw = policy["binding"]["approved"]
    from autoteacher_m0.security.authorization import BINDING_NAMES, ExpectedBindings
    if set(approved_raw) != set(BINDING_NAMES):
        raise SystemExit("G4C_APPROVED_BINDING_FIELDS_INVALID")
    approved = ExpectedBindings(**{name: approved_raw[name]
                                   for name in BINDING_NAMES})
    observed_start = _observed_bindings(policy)
    drift = binding_drift("pre_start", approved=approved, observed=observed_start)
    if drift:
        raise SystemExit("G4C_PRE_START_BINDING_DRIFT:" + ",".join(drift))

    def observer():
        return _observed_bindings(policy)

    gate = TrustedSendGate(
        contract, budget=budget, auth_epoch=policy["auth_epoch"],
        journal_path=policy.get("journal_path") or str(JOURNAL_PATH),
        binding_approved=approved, binding_observer=observer,
        binding_checkpoint="pre_dispatch")
    return gate, contract, approved, observed_start


def build_on_ready(config_sha256: str, instance: str, policy_sha256: str,
                   contract: object):
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
            "schema": "m0.g4c.trusted.ready.v1",
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
            "g4c_policy_sha256": policy_sha256,
            "route_contract": contract.to_mapping(),
            "state_dir": str(STATE_DIR),
            "synthetic": True,
        }
        record = write_json_nofollow(READY_PATH, document, mode=0o600, exclusive=True)
        print("G4C_TRUSTED_READY " + json.dumps(
            {"utc": document["utc"], "socket": document["socket"],
             "sha256": record["sha256"], "instance": instance,
             "route_id": contract.route_id}, sort_keys=True), flush=True)
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
    policy = _read_policy()
    preflight = preflight_checks(config, policy)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    write_json_nofollow(OUT_DIR / "trusted-preflight.json", preflight,
                        mode=0o644, exclusive=False)
    modules = module_identity()
    write_json_nofollow(OUT_DIR / "trusted-modules.json", modules,
                        mode=0o644, exclusive=False)
    if preflight["problems"]:
        sys.stderr.write("TRUSTED_PREFLIGHT_FAILED " + json.dumps(
            preflight["problems"]) + "\n")
        print("G4C_TRUSTED_RESULT " + json.dumps(
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
    policy_sha256 = sha256_file(POLICY_PATH)
    try:
        gate, contract, approved, observed = _build_gate(policy)
    except SystemExit as exc:
        sys.stderr.write(str(exc) + "\n")
        print("G4C_TRUSTED_RESULT " + json.dumps(
            {"ok": False, "reason": "G4C_POLICY", "detail": str(exc)},
            sort_keys=True), flush=True)
        return 5
    except (TypeError, ValueError, KeyError) as exc:
        sys.stderr.write(f"G4C_POLICY_INVALID {type(exc).__name__}: {exc}\n")
        print("G4C_TRUSTED_RESULT " + json.dumps(
            {"ok": False, "reason": "G4C_POLICY",
             "detail": f"{type(exc).__name__}: {exc}"}, sort_keys=True), flush=True)
        return 5
    write_json_nofollow(OUT_DIR / "g4c-binding-start.json", {
        "schema": "m0.g4c.binding-check.v1",
        "utc": utc(),
        "checkpoint": "pre_start",
        "approved": approved.as_dict(),
        "observed": observed.as_dict(),
        "route_contract": contract.to_mapping(),
        "policy_sha256": policy_sha256,
    }, mode=0o644, exclusive=False)
    on_ready = build_on_ready(config_sha256, instance, policy_sha256, contract)
    print("G4C_TRUSTED_START " + json.dumps(
        {"utc": utc(), "instance": instance, "config_sha256": config_sha256,
         "policy_sha256": policy_sha256,
         "expected_peer_uid": EXPECTED_PEER_UID, "socket_mode": SOCKET_MODE,
         "socket_gid": SOCKET_GID, "route_id": contract.route_id}, sort_keys=True),
        flush=True)
    from autoteacher_m0.bridge import controller as controller_module
    return_code = 0
    try:
        return_code = controller_module.main(
            ["--config", args.config], on_ready=on_ready, dispatch_gate=gate)
    finally:
        snapshot = gate.snapshot()
        snapshot["utc"] = utc()
        snapshot["instance"] = instance
        write_json_nofollow(OUT_DIR / "g4c-egress.json", snapshot,
                            mode=0o644, exclusive=False)
        print("G4C_TRUSTED_EXIT " + json.dumps(
            {"utc": utc(), "exit": return_code, "instance": instance,
             "sends_authorized": snapshot["sends_authorized"],
             "sends_consumed": snapshot["consumed"]}, sort_keys=True), flush=True)
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
