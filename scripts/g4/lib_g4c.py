#!/usr/bin/env python3
"""G4-C shared host helpers: frozen stage validation, closure, policy and argv.

This module is *only* imported by G4-C scripts (``build_stage_c.py``,
``launch_c.py``, ``run_g4_c.py``). It reuses ``scripts/g3d`` helpers for the
run layout, UID/mount flags, evidence primitives and canonical hashing, but it
never edits ``scripts/g3d/**`` and never writes ``artifacts/g3d/**``.

Provenance: the G4-C stage is built from a committed G4 implementation SHA
(``git rev-parse HEAD`` at build time), so the trusted stage files are exactly
the committed ``src/`` blobs. The G3-D frozen launcher hardcodes
``PRODUCT_BASE=4bd4803`` and rejects ``git diff cf40c6b -- src``; G4-A/C
authorised source changes make that assertion false by construction. The G4-C
launcher therefore performs its own preflight against the G4 base (documented
in ``docs/M0_G4_C_EGRESS_CONTRACT.md`` §5).
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Iterable, Mapping, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "g3d"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib_g3d as lib3d  # noqa: E402
import lib_g4 as lib  # noqa: E402

REPO = lib.REPO_ROOT
if str(REPO / "src") not in sys.path:
    sys.path.insert(0, str(REPO / "src"))
from autoteacher_m0.security.authorization import BINDING_COMPONENTS  # noqa: E402

G4C_ROOT = lib.ARTIFACTS / "g4" / "c"
STAGE_ROOT = G4C_ROOT / "stages"
BUILD_ROOT = G4C_ROOT / "build-root"
TRUSTED_ENTRY = REPO / "scripts" / "g4" / "stage" / "trusted_entry_g4c.py"
PROBE_SOURCE = REPO / "scripts" / "g4" / "probes" / "g4c_uds_probe.py"

# Complete runtime-relevant closure used for the G4-C pre_start/pre_dispatch
# binding check. The twelve repository components are the G4-A closure; the
# three external build artefacts are represented by canonical manifest entries
# (their tree/binary digests) instead of the G4-A TEST_ONLY placeholders.
COMPONENT_FILES: dict[str, tuple[str, ...]] = {
    "trusted_controller": (
        "src/autoteacher_m0/bridge/controller.py",
        "src/autoteacher_m0/bridge/ipc_server.py",
        "src/autoteacher_m0/bridge/admission.py",
        "src/autoteacher_m0/bridge/attempts.py",
        "src/autoteacher_m0/bridge/protocol.py",
        "src/autoteacher_m0/bridge/broker_client.py",
    ),
    "trusted_broker": (
        "src/autoteacher_m0/accounting/broker.py",
        "src/autoteacher_m0/accounting/broker_usage.py",
        "src/autoteacher_m0/accounting/budget.py",
        "src/autoteacher_m0/accounting/call_identity.py",
        "src/autoteacher_m0/accounting/ledger.py",
        "src/autoteacher_m0/accounting/observation.py",
        "src/autoteacher_m0/accounting/pricing.py",
        "src/autoteacher_m0/accounting/usage.py",
    ),
    "egress_boundary": (
        "src/autoteacher_m0/security/egress.py",
        "config/dsh/target-broker-policy.json",
    ),
    "candidate_adapter": (
        "src/autoteacher_m0/runtime/dsh_adapter.py",
        "src/autoteacher_m0/cli.py",
    ),
    "security_primitives": (
        "src/autoteacher_m0/security/__init__.py",
        "src/autoteacher_m0/security/authorization.py",
        "src/autoteacher_m0/security/credential_boundary.py",
        "src/autoteacher_m0/security/ed25519.py",
        "src/autoteacher_m0/security/gates.py",
        "src/autoteacher_m0/security/live_controller.py",
        "src/autoteacher_m0/security/watchdog.py",
    ),
    "dependency_lock": (
        "pyproject.toml",
        "uv.lock",
    ),
    "plugin_tree": (
        "plugins/offline-fixture/cordis.patch.yml",
        "plugins/offline-fixture/package-lock.json",
        "plugins/offline-fixture/package.json",
        "plugins/offline-fixture/src/index.ts",
        "plugins/offline-fixture/tsconfig.json",
        "plugins/runtime-budget-guard/package-lock.json",
        "plugins/runtime-budget-guard/package.json",
        "plugins/runtime-budget-guard/src/index.ts",
        "plugins/runtime-budget-guard/tsconfig.json",
        "plugins/skill-lookup/cordis.patch.yml",
        "plugins/skill-lookup/package-lock.json",
        "plugins/skill-lookup/package.json",
        "plugins/skill-lookup/src/index.ts",
        "plugins/skill-lookup/tsconfig.json",
    ),
    "tool_registry_schema": (
        "config/dsh/target-runtime.patch.yml",
    ),
    "merged_profile": (
        "config/dsh/sdk-minimal.patch.yml",
        "config/dsh/target-runtime.patch.yml",
        "config/dsh/target-runtime-opencode-go.patch.yml",
    ),
    "route_policy": (
        "config/dsh/target-runtime-opencode-go.patch.yml",
        "src/autoteacher_m0/settings.py",
    ),
    "budget_policy": (
        "config/budgets.yaml",
    ),
    "price_snapshot": (
        "config/models.example.yaml",
    ),
}
EXTERNAL_COMPONENTS = ("candidate_stage", "runtime_binary", "runtime_dependencies")
assert set(COMPONENT_FILES) | set(EXTERNAL_COMPONENTS) == set(BINDING_COMPONENTS)

CONTAINER_PATH_OVERRIDES = {
    "spikes/g3b-trusted-bridge/fake/fake_provider.py": "fake/fake_provider.py",
}
REQUIRED_STAGE_FILES = (
    "trusted/run/trusted_entry.py",
    "trusted/src/autoteacher_m0/bridge/controller.py",
    "trusted/src/autoteacher_m0/security/egress.py",
    "trusted/fake/fake_provider.py",
    "trusted/templates/controller.template.json",
    "trusted/templates/admission.template.json",
    "trusted/templates/broker.template.json",
    "trusted/REFERENCE.json",
    "candidate/run/candidate_entry.py",
    "candidate/config/bridge.patch.yml",
    "candidate/runtime/bridge/lib/index.js",
    "candidate/etc/passwd",
    "candidate/etc/group",
)


def utc() -> str:
    return lib.utc_now()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str | os.PathLike[str]) -> str:
    return sha256_bytes(Path(path).read_bytes())


def canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def component_digest(entries: Sequence[tuple[str, str]]) -> str:
    """Same formula as G4-A ``inventory_digest``: sha256 of sorted [path, sha]."""
    return sha256_bytes(canonical_json(
        sorted([[path, digest] for path, digest in entries])))


def container_relative(relpath: str) -> str | None:
    """Stage-relative path of a closure file visible inside the trusted container."""
    if relpath in CONTAINER_PATH_OVERRIDES:
        return CONTAINER_PATH_OVERRIDES[relpath]
    if relpath.startswith("src/"):
        return relpath
    return None


def closure_for(repo_root: Path, *, external: Mapping[str, str]) -> dict:
    """Build the full 15-component closure from the repository worktree.

    ``external`` carries the three build-artefact documents as
    ``{component: {"kind", "sha256"}}``. Returns the policy-side table with every
    file's expected sha and whether the trusted container can recompute it.
    """
    components: dict[str, dict] = {}
    for name, relatives in COMPONENT_FILES.items():
        files = []
        for relative in relatives:
            source = repo_root / relative
            if not source.is_file() or source.is_symlink():
                raise lib.G4Error(f"closure source missing: {relative}")
            files.append({
                "path": relative,
                "sha256": sha256_file(source),
                "container_path": container_relative(relative),
            })
        components[name] = {"files": files}
    for name in EXTERNAL_COMPONENTS:
        document = {"component": name, "kind": "external_artifact", **external[name]}
        content = canonical_json(document)
        components[name] = {"files": [], "external": {
            "document": document, "sha256": sha256_bytes(content)}}
    digests = {}
    for name, entry in components.items():
        if entry["files"]:
            entries = [(item["path"], item["sha256"]) for item in entry["files"]]
            digests[name] = component_digest(entries)
        else:
            digests[name] = component_digest([("EXTERNAL.json",
                                               entry["external"]["sha256"])])
    return {"schema": "m0.g4c.binding-closure.v1",
            "components": components, "component_digests": digests}


def expected_bindings(closure: Mapping[str, object]) -> dict[str, str]:
    from autoteacher_m0.security.authorization import ExpectedBindings
    return ExpectedBindings.from_closure(dict(closure["component_digests"])).as_dict()


def load_reference(stage: Path) -> dict:
    raw = lib3d.read_regular_bytes(stage / "trusted" / "REFERENCE.json")
    return json.loads(raw.decode("utf-8"))


def stage_external_inputs(stage: Path) -> dict[str, dict]:
    reference = load_reference(stage)
    stage_tree = lib3d.sha256_tree(stage)
    return {
        "runtime_dependencies": {"sha256": reference["deps"]["sha256"],
                                 "path": "deps"},
        "runtime_binary": {"sha256": reference["dsh"]["runtime_sha256"],
                           "path": "deepseek-harness-sdk-runtime-linux-x64"},
        "candidate_stage": {"sha256": stage_tree, "path": "stage"},
    }


# ---------------------------------------------------------------------------
# stage validation
# ---------------------------------------------------------------------------
def _rows_for(section: Mapping[str, object]) -> dict[str, dict]:
    rows = section.get("files") if isinstance(section, Mapping) else None
    if not isinstance(rows, list):
        raise lib.G4Error("stage manifest section rows missing")
    result = {}
    for row in rows:
        if not isinstance(row, Mapping) or not isinstance(row.get("path"), str):
            raise lib.G4Error("stage manifest row invalid")
        if row["path"] in result:
            raise lib.G4Error(f"duplicate stage manifest row: {row['path']}")
        result[row["path"]] = dict(row)
    return result


def _walk_files(root: Path) -> dict[str, Path]:
    found: dict[str, Path] = {}
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        current = Path(dirpath)
        for name in dirnames:
            if (current / name).is_symlink():
                raise lib.G4Error(f"symlinked directory in stage: {current / name}")
        for name in filenames:
            path = current / name
            if path.is_symlink() or not path.is_file():
                raise lib.G4Error(f"non-regular stage file: {path}")
            found[path.relative_to(root).as_posix()] = path
    return found


def validate_stage_g4(stage_dir: str | os.PathLike[str], *, base_sha: str,
                      verify_git: bool = True) -> dict:
    """Independent G4 manifest validation (does not reuse the frozen base check)."""
    stage = Path(stage_dir)
    problems: list[str] = []
    try:
        raw = lib3d.read_regular_bytes(stage / "manifest.json", max_bytes=128 << 20)
        manifest = json.loads(raw.decode("utf-8"))
    except (OSError, lib3d.G3DError, json.JSONDecodeError) as exc:
        raise lib.G4Error(f"stage manifest unreadable: {type(exc).__name__}")
    if not isinstance(manifest, dict):
        raise lib.G4Error("stage manifest is not an object")
    if manifest.get("schema") != lib3d.STAGE_SCHEMA:
        problems.append("manifest_schema_mismatch")
    if manifest.get("base_sha") != base_sha:
        problems.append(f"base_sha:{manifest.get('base_sha')}")
    if manifest.get("head_at_build") != base_sha:
        problems.append(f"head_at_build:{manifest.get('head_at_build')}")
    if manifest.get("product_src_identical_to_base") is not True:
        problems.append("product_src_identical_not_true")
    for section_name in ("trusted", "candidate"):
        section = manifest.get(section_name)
        if not isinstance(section, Mapping):
            problems.append(f"{section_name}:section_missing")
            continue
        section_root = stage / section_name
        try:
            files = _walk_files(section_root)
        except lib.G4Error as exc:
            problems.append(f"{section_name}:{exc}")
            continue
        try:
            rows = _rows_for(section)
        except lib.G4Error as exc:
            problems.append(f"{section_name}:{exc}")
            continue
        if set(files) != set(rows):
            missing = sorted(set(files) - set(rows))
            extra = sorted(set(rows) - set(files))
            problems.append(f"{section_name}:file_set_mismatch missing={missing[:5]}"
                            f" extra={extra[:5]}")
        for relative, path in files.items():
            row = rows.get(relative)
            if row is None:
                continue
            actual = sha256_file(path)
            if actual != row.get("sha256"):
                problems.append(f"{section_name}:sha_mismatch:{relative}")
            info = os.lstat(path)
            if info.st_size != row.get("bytes"):
                problems.append(f"{section_name}:bytes_mismatch:{relative}")
            if row.get("mode") is not None and (info.st_mode & 0o777) != row["mode"]:
                problems.append(f"{section_name}:mode_mismatch:{relative}")
        tree = lib3d.sha256_tree(section_root)
        if tree != section.get("tree_sha256"):
            problems.append(f"{section_name}:tree_sha_mismatch")
    for required in REQUIRED_STAGE_FILES:
        if not (stage / required).is_file():
            problems.append(f"required_missing:{required}")
    if verify_git:
        for relative, row in _rows_for(manifest.get("trusted") or {}).items():
            source = row.get("source") or {}
            if source.get("kind") != "git_blob":
                continue
            blob_path = source.get("path")
            try:
                actual = lib3d.git_blob_sha256(base_sha, blob_path)
            except lib3d.G3DError:
                problems.append(f"git_source_unreadable:{relative}")
                continue
            if actual != row.get("sha256"):
                problems.append(f"git_blob_mismatch:{relative}")
    manifest_sha256 = sha256_bytes(raw)
    summary_path = stage / "stage-summary.json"
    summary = None
    if summary_path.is_file():
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            problems.append("stage_summary_invalid")
    else:
        problems.append("stage_summary_missing")
    return {"ok": not problems, "problems": problems, "stage_dir": str(stage),
            "manifest_sha256": manifest_sha256, "base_sha": manifest.get("base_sha"),
            "manifest": manifest, "summary": summary,
            "trusted_tree_sha256": (manifest.get("trusted") or {}).get("tree_sha256"),
            "candidate_tree_sha256": (manifest.get("candidate") or {}).get("tree_sha256")}


# ---------------------------------------------------------------------------
# trusted argv + contract
# ---------------------------------------------------------------------------
# G4-F5 adds two test-only crash windows inside the existing test-hook
# mechanism (authorize -> consume -> Fake). They are listed here, not in the
# frozen G3-D hook set, because they are G4-F5 evidence hooks.
G4F5_CRASH_HOOKS = frozenset({
    "after_send_authorize_before_consume",
    "after_send_consume_before_fake",
})
G4F5_DELAY_HOOKS = frozenset({"before_reserve", "after_reserve_before_send"})


def trusted_argv(*, podman: str, rootfs: str, stage_trusted: str, deps: str,
                 run_dir: str, entry_dir: str, name: str,
                 config_path: str = lib3d.CONTROLLER_CONFIG_PATH,
                 evidence_dir: str | None = None,
                 crash_hook: str | None = None,
                 test_delay_hook: str | None = None,
                 test_delay_ms: int | None = None,
                 timeout_s: int = 300) -> list[str]:
    evidence = evidence_dir or str(Path(run_dir) / "evidence")
    extra_env: list[str] = []
    if crash_hook is not None:
        if (crash_hook not in lib3d.TRUSTED_CRASH_HOOKS
                and crash_hook not in G4F5_CRASH_HOOKS):
            raise lib.G4Error(f"unknown trusted crash hook: {crash_hook}")
        extra_env = ["--env", "G3B_TEST_MODE=1",
                     "--env", f"G3B_CRASH_HOOK={crash_hook}"]
    if test_delay_hook is not None:
        if test_delay_hook not in G4F5_DELAY_HOOKS:
            raise lib.G4Error(f"unknown test delay hook: {test_delay_hook}")
        if type(test_delay_ms) is not int or not 1 <= test_delay_ms <= 10000:
            raise lib.G4Error("test delay ms must be 1..10000")
        if "--env" not in extra_env:
            extra_env += ["--env", "G3B_TEST_MODE=1"]
        extra_env += [
            "--env", f"G3B_TEST_DELAY_HOOK={test_delay_hook}",
            "--env", f"G3B_TEST_DELAY_MS={test_delay_ms}",
            "--env", "G3B_TEST_DELAY_MARKER=/work/state/g4f5-delay-marker.json",
        ]
    return [
        podman, "run", "-d", "--name", name, "--rootfs",
        "--timeout", str(int(timeout_s)),
        "--userns=host", "--user", "0:0",
        *lib3d._base_security_flags(),
        "--env", "PATH=/opt/python/bin:/usr/bin",
        "--env", "HOME=/work",
        "--env", "PYTHONPATH=/project/src:/deps",
        "--env", "PYTHONDONTWRITEBYTECODE=1",
        "--env", "TMPDIR=/tmp",
        *extra_env,
        "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=64m,mode=1777",
        "--tmpfs", "/work:rw,noexec,nosuid,nodev,size=256m,mode=1777",
        "--mount", f"type=bind,src={stage_trusted},dst=/project,ro=true",
        "--mount", f"type=bind,src={deps},dst=/deps,ro=true",
        "--mount", f"type=bind,src={stage_trusted}/etc/passwd,dst=/etc/passwd,ro=true",
        "--mount", f"type=bind,src={stage_trusted}/etc/group,dst=/etc/group,ro=true",
        "--mount", f"type=bind,src={Path(run_dir) / 'state'},dst=/work/state,rw=true",
        "--mount", f"type=bind,src={Path(run_dir) / 'ipc'},dst=/work/g3b,rw=true",
        "--mount", f"type=bind,src={evidence},dst=/output,rw=true",
        # G4-C trusted entrypoint (a run-dir copy of scripts/g4/stage/...).
        "--mount", f"type=bind,src={entry_dir},dst=/g4c,ro=true",
        "--workdir", "/project",
        "--systemd=false",
        rootfs, "/opt/python/bin/python3.11", "-B",
        "/g4c/trusted_entry.py", "--config", config_path,
    ]


def trusted_argv_problems(argv: Sequence[str], *, run_dir: str,
                          stage_dir: str) -> list[str]:
    problems: list[str] = []
    text = list(argv)
    if "--network" not in text or text[text.index("--network") + 1] != "none":
        problems.append("network_not_none")
    for flag in ("--read-only", "--cap-drop", "--security-opt", "--userns=host"):
        if flag == "--read-only":
            if "--read-only" not in text:
                problems.append("read_only_missing")
        elif flag == "--cap-drop":
            if not any(text[index] == "--cap-drop" and text[index + 1] == "ALL"
                       for index in range(len(text) - 1)):
                problems.append("cap_drop_missing")
        elif flag == "--security-opt":
            if not any(text[index] == "--security-opt"
                       and text[index + 1] == "no-new-privileges"
                       for index in range(len(text) - 1)):
                problems.append("no_new_privs_missing")
        elif flag not in text:
            problems.append("userns_host_missing")
    mounts = [text[index + 1] for index in range(len(text) - 1) if text[index] == "--mount"]
    for mount in mounts:
        if "dst=/output" in mount or "dst=/work/state" in mount \
                or "dst=/work/g3b" in mount or "dst=/g4c" in mount:
            continue
        if "dst=/project" in mount or "dst=/deps" in mount \
                or "dst=/etc/passwd" in mount or "dst=/etc/group" in mount:
            continue
        problems.append(f"unexpected_mount:{mount[:120]}")
    if str(Path(run_dir) / "g4c-run") not in " ".join(mounts):
        problems.append("g4c_entry_mount_missing")
    return problems


# ---------------------------------------------------------------------------
# G4-C policy document
# ---------------------------------------------------------------------------
def build_policy(*, contract: Mapping[str, object], closure: Mapping[str, object],
                 approved: Mapping[str, str], auth_epoch: str,
                 run_id: str, revocation: Mapping[str, object] | None = None) -> dict:
    document = {
        "schema": "m0.g4c.dispatch-policy.v1",
        "run_id": run_id,
        "auth_epoch": auth_epoch,
        "synthetic": True,
        "real_model_calls": 0,
        "real_external_http_calls": 0,
        "provider_route_kind": "synthetic_only",
        "route_contract": dict(contract),
        "budget": {
            "soft_total_usd": "3.00",
            "hard_total_usd": "10.00",
            "soft_call_usd": "0.10",
            "hard_call_usd": "0.20",
            "max_sends": 50,
        },
        "binding": {
            "checkpoint": "pre_dispatch",
            "approved": dict(approved),
            "closure": closure,
        },
        "journal_path": "/work/state/g4c-send-journal.jsonl",
    }
    if revocation is not None:
        document["revocation"] = dict(revocation)
    return document


def policy_bytes(document: Mapping[str, object]) -> bytes:
    return (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")


def write_policy(path: Path, document: Mapping[str, object]) -> dict:
    return lib3d.write_bytes_atomic(path, policy_bytes(document), mode=0o400,
                                    uid=0, gid=0)


def verify_stage_tool_schema(stage: Path, allowed: Iterable[str]) -> dict:
    """Cross-check the frozen capture-tools fixture against the contract digests."""
    from autoteacher_m0.accounting.call_identity import canonical_json as product_canonical
    fixture = stage / "candidate" / "fixtures" / "capture-tools.json"
    raw = lib3d.read_regular_bytes(fixture, max_bytes=1 << 20)
    document = json.loads(raw.decode("utf-8"))
    rows = []
    for item in document.get("tools") or []:
        canonical = item.get("canonical_json")
        digest = sha256_bytes(product_canonical(json.loads(canonical)).encode("utf-8"))
        rows.append({"name": item.get("name"), "digest": digest,
                     "fixture_sha256": item.get("sha256")})
    return {"rows": rows, "allowed": sorted(allowed),
            "ok": bool(rows) and all(row["digest"] in set(allowed)
                                     and row["digest"] == row["fixture_sha256"]
                                     for row in rows)}


def parse_ready_g4c(raw: bytes) -> tuple[dict | None, list[str]]:
    """Parse the G4-C trusted ready document (same kernel-bound checks as G3-D)."""
    problems: list[str] = []
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, ["ready_not_json"]
    if not isinstance(document, dict):
        return None, ["ready_not_object"]
    if document.get("schema") != "m0.g4c.trusted.ready.v1":
        problems.append("ready_schema")
    if document.get("expected_peer_uid") != lib3d.EXPECTED_PEER_UID:
        problems.append("ready_peer_uid")
    socket_doc = document.get("socket")
    if not isinstance(socket_doc, dict):
        problems.append("ready_socket_missing")
    else:
        if socket_doc.get("mode") != lib3d.SOCKET_MODE:
            problems.append("ready_socket_mode")
        if socket_doc.get("gid") != lib3d.GROUP_SOCKET:
            problems.append("ready_socket_gid")
        if socket_doc.get("uid") != lib3d.SOCKET_UID:
            problems.append("ready_socket_uid")
        if not isinstance(socket_doc.get("inode"), int):
            problems.append("ready_socket_inode")
    if not isinstance(document.get("pid"), int) or document["pid"] <= 0:
        problems.append("ready_pid")
    if not isinstance(document.get("utc"), str) or "T" not in document["utc"]:
        problems.append("ready_utc")
    if not isinstance(document.get("g4c_policy_sha256"), str):
        problems.append("ready_policy_sha")
    return document, problems
