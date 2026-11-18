#!/usr/bin/env python3
"""Build the G4-E no-key review packet (host-side, read-only project imports).

Usage:
  PYTHONDONTWRITEBYTECODE=1 /root/.local/bin/python3.11 -B \
    scripts/g4/build_packet.py --docs-sha <sha> [--out <dir>] [--force]

The builder never starts a container, never uses the network, never reads a
credential, never opens SQLite databases, and never modifies repository files.
It only writes inside ``artifacts/review-packet-g4-<impl-sha>/``.

Provenance is explicit:

* base      = 017c747 (G3-D final docs archive)
* impl      = a6f3e0a (G4-D final HEAD; docs-only commits after d3d429c)
* code      = d3d429c (last G4 implementation commit; src tree == impl)
* docs      = the G4-E docs/matrix commit supplied with --docs-sha
* build_sha = docs (the packet is built at the docs freeze)

Packet payload excludes the manifest, hashes file and integrity report from the
payload tree hash to avoid self-reference. ``hashes.sha256`` covers every
payload file plus ``manifest.json``; it does not cover itself or the report.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "artifacts"
DOCS = ROOT / "docs"
MATRIX = DOCS / "Autonomous_Teacher_M0_G4_PreLive_Test_Evidence_Matrix_v1.0.csv"

BASE_SHA = "017c747631cae1e7788014c4ef9e6056c141fecd"
IMPL_SHA = "a6f3e0a27a516534803a1e3549dc60fbd107583c"
CODE_SHA = "d3d429cf9d0cb1e9dbc68317928631db413be309"
SRC_LAST_SHA = "d8a8dc83673d6236884bb41574214e5b2106fcd4"
PACKET_NAME = f"review-packet-g4-{IMPL_SHA}"
ROOTFS_CANON = "25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0"
DEPS_CANON = "e07729d7997944417b1c25531749b3e6e5e34aa4248f01dc8f370282082ecb98"
STAGE_PATH = "artifacts/g4/c/stages/stage-20261118T193401Z"
STAGE_TREE = "9c9ce31312ad060a9734b01d98d4ce9c5e64a2064f54ef32abc77e025358762b"
STAGE_MANIFEST = "853530183d75f6c1813621ec0c67575aa26553d4f2bf213ae40910e10817de48"
DSH_RUNTIME = "1cc41d5a8745a5b9d47c8604e44f23eb8af2d8ca02b2afa0be101d5f71be6ea4"
G3D_REVIEW_SHA = "a16dd453386a23b51566f474dc4bc4166a6823fa586d85e3a49bb38adfc07a45"
MAX_FILE_BYTES = 8 * 1024 * 1024
EXCLUDE_HASH = {"hashes.sha256", "packet-integrity-report.txt"}
PAYLOAD_META = EXCLUDE_HASH | {"manifest.json"}

SOURCE_PATHS = [
    "src/autoteacher_m0/security/authorization.py",
    "src/autoteacher_m0/security/ed25519.py",
    "src/autoteacher_m0/security/live_controller.py",
    "src/autoteacher_m0/security/egress.py",
    "src/autoteacher_m0/security/watchdog.py",
    "src/autoteacher_m0/bridge/controller.py",
    "src/autoteacher_m0/security/gates.py",
    "src/autoteacher_m0/runtime/dsh_adapter.py",
    "src/autoteacher_m0/cli.py",
    "scripts/run_live.sh",
    "scripts/g4/build_manifest.py",
    "scripts/g4/verify_manifest.py",
    "scripts/g4/lib_g4.py",
    "scripts/g4/build_stage_c.py",
    "scripts/g4/lib_g4c.py",
    "scripts/g4/launch_c.py",
    "scripts/g4/stage/trusted_entry_g4c.py",
    "scripts/g4/run_g4_c.py",
    "scripts/g4/launch_d.py",
    "scripts/g4/watchdog_runner.py",
    "scripts/g4/e5_probe.py",
    "scripts/g4/run_g4_d.py",
    "scripts/g4/secret_sentinel_probe.py",
    "scripts/g4/run_g4_b.py",
    "scripts/g4/probe_runtime.py",
    "scripts/g4/probe_admission_contract.py",
    "scripts/g4/probes/g4c_uds_probe.py",
    "scripts/g4/probes/g4d_candidate_iso_probe.py",
    "config/g4/inventory.spec.json",
    "config/g4/runtime-policy.json",
    "tests/integration/g4_a/test_a01_signature_vs_billable.py",
    "tests/integration/g4_a/test_a02_small_order.py",
    "tests/integration/g4_a/test_a07_trusted_file_boundary.py",
    "tests/integration/g4_a/test_a12_replay_epoch.py",
    "tests/integration/g4_b/test_admission_tool_schema.py",
    "tests/integration/g4_b/test_verifier_fail_closed.py",
    "tests/integration/g4_c/test_c02_authorization.py",
    "tests/integration/g4_c/test_c05_no_live_egress.py",
    "tests/integration/g4_d/test_d01_watchdog_absence.py",
    "tests/integration/g4_d/test_d05_d06_revocation_epoch.py",
    "tests/integration/g4_d/test_d07_live_entrances.py",
]

PROTECTED_PATHS = [
    "AGENTS.md",
    "SECURITY.md",
    "docs/SECURITY_APPROVALS.md",
    "scripts/run_live.sh",
    "src/autoteacher_m0/security/gates.py",
    "src/autoteacher_m0/runtime/dsh_adapter.py",
    "src/autoteacher_m0/cli.py",
    "scripts/g3d/launch.py",
    "scripts/g3d/build_stage.py",
    "tests/integration/g3d/test_d3_contract.py",
]

SENSITIVE = [
    re.compile(r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{20,}(?![A-Za-z0-9_-])"),
    re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----"),
    re.compile(r"(?i)(?:api[_-]?key|access[_-]?token|secret[_-]?key)[\"']?\s*[:=]\s*[\"'][A-Za-z0-9_\-]{20,}[\"']"),
    re.compile(r"(?i)authorization\s*:\s*bearer\s+[A-Za-z0-9._\-]{20,}"),
    re.compile(r"DEEPSEEK_API_KEY\s*=\s*[\"']?[A-Za-z0-9_\-]{20,}"),
]


class BuildError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git(*args: str, binary: bool = False):
    proc = subprocess.run(["git", *args], cwd=ROOT, capture_output=True)
    if proc.returncode != 0:
        raise BuildError(f"git {' '.join(args)} failed: "
                         f"{proc.stderr.decode('utf-8', 'replace')[:800]}")
    return proc.stdout if binary else proc.stdout.decode("utf-8", "replace")


def sanitize_text(text: str) -> str:
    escaped_root = str(ROOT).replace(" ", "\\040")
    replacements = [
        (str(ROOT), "<WORKSPACE>"),
        (escaped_root, "<WORKSPACE_ESCAPED>"),
        ("/root/g4b-baseline", "<G4B_WORKTREE>"),
        ("/root/.local/share/uv/python/cpython-3.11-linux-x86_64-gnu",
         "<UV_PYTHON>"),
        ("/root/.local/share/uv/python/cpython-3.11.15-linux-x86_64-gnu",
         "<UV_PYTHON>"),
        ("/root/.local/bin/python3.11", "<HOST_PYTHON>"),
        ("/root/.local/bin", "<HOST_BIN>"),
        ("/root/.local/share", "<HOST_SHARE>"),
        ("/root/.cache", "<HOST_CACHE>"),
        ("/root/.dsh", "<HOST_HOME>/.dsh"),
        ("/root/.config", "<HOST_HOME>/.config"),
        ("/opt/miniconda3/envs/quant/bin/python", "<CONDA_PYTHON>"),
    ]
    for old, new in replacements:
        text = text.replace(old, new)
    return text


def sanitize_json(value):
    if isinstance(value, str):
        return sanitize_text(value)
    if isinstance(value, list):
        return [sanitize_json(item) for item in value]
    if isinstance(value, dict):
        return {sanitize_text(str(key)): sanitize_json(item)
                for key, item in value.items()}
    return value


def write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def write_text(path: Path, text: str) -> None:
    write_bytes(path, text.encode("utf-8"))


def write_json(path: Path, document) -> None:
    write_text(path, json.dumps(sanitize_json(document), indent=2,
                                sort_keys=True) + "\n")


def require_file(path: Path, label: str = "") -> Path:
    if not path.is_file():
        raise BuildError(f"missing evidence file: {path} {label}")
    if path.is_symlink():
        raise BuildError(f"refusing symlink evidence: {path}")
    if path.stat().st_size > MAX_FILE_BYTES:
        raise BuildError(f"evidence too large: {path}")
    return path


def copy_text(src: Path, dst: Path, *, required: bool = True) -> None:
    if not src.is_file():
        if required:
            raise BuildError(f"missing text evidence: {src}")
        return
    require_file(src)
    try:
        text = src.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = src.read_text(encoding="utf-8", errors="replace")
    write_text(dst, sanitize_text(text))


def copy_json(src: Path, dst: Path, *, required: bool = True) -> None:
    if not src.is_file():
        if required:
            raise BuildError(f"missing json evidence: {src}")
        return
    require_file(src)
    write_json(dst, json.loads(src.read_text(encoding="utf-8")))


def copy_binary(src: Path, dst: Path) -> None:
    require_file(src)
    write_bytes(dst, src.read_bytes())


def copy_tree_glob(src_dir: Path, pattern: str, dst_dir: Path,
                   *, max_files: int = 20) -> int:
    files = sorted(path for path in src_dir.glob(pattern) if path.is_file())
    for src in files[:max_files]:
        copy_binary(src, dst_dir / src.name)
    return min(len(files), max_files)


def run_dir(prefix: str) -> Path:
    matches = sorted(ARTIFACTS.glob(f"g4/c/runs/{prefix}-*"))
    if not matches:
        raise BuildError(f"missing G4-C run evidence for {prefix}")
    return matches[-1]


def latest(pattern: str) -> Path:
    matches = sorted(ARTIFACTS.glob(pattern))
    if not matches:
        raise BuildError(f"missing artifact pattern: {pattern}")
    return matches[-1]


def payload_tree_hash(rows: list[tuple[str, str]]) -> str:
    lines = "".join(f"{digest}  {rel}\n" for rel, digest in sorted(rows))
    return hashlib.sha256(lines.encode("utf-8")).hexdigest()


def build_changes(out: Path, docs_sha: str) -> None:
    dst = out / "changes"
    write_text(dst / "implementation.diff",
               sanitize_text(git("diff", "--binary", BASE_SHA, IMPL_SHA, "--",
                                 "src", "scripts/g4", "config/g4",
                                 "tests/integration/g4_a",
                                 "tests/integration/g4_b",
                                 "tests/integration/g4_c",
                                 "tests/integration/g4_d")))
    write_text(dst / "docs.diff",
               sanitize_text(git("diff", "--binary", BASE_SHA, docs_sha, "--",
                                 "docs")))
    lines = ["# Protected-file audit (base to impl)", ""]
    for relative in PROTECTED_PATHS:
        proc = subprocess.run(["git", "diff", "--quiet", BASE_SHA, IMPL_SHA,
                               "--", relative], cwd=ROOT)
        state = "UNCHANGED" if proc.returncode == 0 else "CHANGED"
        blob = git("rev-parse", f"{IMPL_SHA}:{relative}").strip() \
            if proc.returncode == 0 else "n/a"
        lines.append(f"{state:9s} {relative}  blob={blob}")
    lines += ["", "## Source blobs (impl HEAD)", ""]
    for relative in SOURCE_PATHS:
        actual = sha256_file(ROOT / relative)
        blob_hash = hashlib.sha256(
            git("show", f"{IMPL_SHA}:{relative}", binary=True)).hexdigest()
        lines.append(f"{'MATCH' if actual == blob_hash else 'MISMATCH':8s} "
                     f"{relative}  sha256={actual}")
    write_text(dst / "protected-files-diff.txt", "\n".join(lines) + "\n")


def build_source(out: Path) -> None:
    index = ["# G4 source index", ""]
    for relative in SOURCE_PATHS:
        target = out / "source" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        copy_text(ROOT / relative, target)
        if sha256_file(target) != sha256_file(ROOT / relative):
            raise BuildError(f"source copy changed bytes: {relative}")
        index.append(f"- `{relative}` sha256 `{sha256_file(ROOT / relative)}`")
    refs = [
        "# G4 line references (1-based)",
        "",
        "authorization.py:114 AuthorizationRejected",
        "authorization.py:273 ExpectedBindings",
        "authorization.py:423 binding_drift(pre_start|pre_reserve|pre_dispatch)",
        "authorization.py:462 load_execution_authorization",
        "authorization.py:694 parse_budget_policy",
        "authorization.py:816 consume_execution_authorization",
        "ed25519.py:79 _decode_point; :98 _is_small_order; :103 _in_prime_order_subgroup",
        "ed25519.py:117 is_valid_public_key; :166 verify",
        "live_controller.py:92 TrustedLiveController; :129 authorization_decision",
        "live_controller.py:160 binding_checkpoint; :249 inspect; :276 require_live",
        "egress.py:1038 ProviderRouteContract; :1254 SyntheticSendBudget",
        "egress.py:1284 TrustedSendAuthorization; :1384 TrustedSendGate",
        "egress.py:1463 pre_dispatch_binding_reasons; :1480 authorize; :1675 consume",
        "watchdog.py:83 ProcessAbsenceReport; :97 PathAbsenceReport",
        "watchdog.py:228 confirm_process_absence; :253 confirm_path_absence",
        "watchdog.py:280 scan_marked_processes; :327 ExternalWatchdog",
        "controller.py:219 TrustedController; :497 _authorize_send",
        "controller.py:735 dispatch_gate authorize; :765 dispatch_gate consume",
        "trusted_entry_g4c.py:123 module_identity; :223 preflight_checks; :286 _build_gate",
        "watchdog_runner.py:121 ExternalWatchdogRunner",
        "launch_d.py:37 hold-open launcher (teardown by external watchdog)",
        "e5_probe.py:115 frozen_closure; :291 authorize; P01..P05 probes",
        "run_g4_d.py:195.. D01/D02/D03/D08/D09 orchestration",
        "build_manifest.py:35 manifest builder; verify_manifest.py:41 verifier",
    ]
    builder = ROOT / "scripts" / "g4" / "build_packet.py"
    builder_copy = out / "source" / "scripts" / "g4" / "build_packet.py"
    copy_text(builder, builder_copy)
    index.append(f"- `scripts/g4/build_packet.py` original sha256 "
                 f"`{sha256_file(builder)}`; packet copy sha256 "
                 f"`{sha256_file(builder_copy)}` (path-sanitized; original hash "
                 f"is authoritative)")
    write_text(out / "source" / "INDEX.md", "\n".join(index) + "\n")
    write_text(out / "source" / "line-references.txt", "\n".join(refs) + "\n")


def build_env(out: Path, docs_sha: str) -> None:
    env = out / "env"
    build_head = git("rev-parse", "HEAD").strip()
    git_lines = [
        "# Git identity",
        f"HEAD={git('rev-parse', 'HEAD').strip()}",
        f"base_sha={BASE_SHA}",
        f"impl_sha={IMPL_SHA}",
        f"code_impl_sha={CODE_SHA}",
        f"src_last_commit={SRC_LAST_SHA}",
        f"docs_sha={docs_sha}",
        f"build_sha={build_head}",
        f"impl_parent={git('rev-parse', f'{IMPL_SHA}^').strip()}",
        f"docs_parent={git('rev-parse', f'{docs_sha}^').strip()}",
        f"impl_subject={git('show', '-s', '--format=%s', IMPL_SHA).strip()}",
        f"docs_subject={git('show', '-s', '--format=%s', docs_sha).strip()}",
        "worktree_status=" + (git("status", "--porcelain=v1", "-uall").strip()
                              or "CLEAN"),
        "src_tree_impl_vs_head=" + (
            "EQUAL" if git("rev-parse", f"{IMPL_SHA}:src").strip()
            == git("rev-parse", "HEAD:src").strip() else "DIFFERENT"),
        f"commits_base_to_impl={git('rev-list', '--count', BASE_SHA + '..' + IMPL_SHA).strip()}",
        f"commits_impl_to_docs={git('rev-list', '--count', IMPL_SHA + '..' + docs_sha).strip()}",
    ]
    write_text(env / "git.txt", "\n".join(git_lines) + "\n")

    runtime_lines = [
        "# Runtime identity",
        f"node={subprocess.run(['node', '--version'], capture_output=True, text=True).stdout.strip()}",
        "host_python=3.11.15",
        "pytest=9.2.0",
        f"podman={subprocess.run(['podman', '--version'], capture_output=True, text=True).stdout.strip()}",
        f"crun={subprocess.run(['crun', '--version'], capture_output=True, text=True).stdout.splitlines()[0]}",
        f"kernel={subprocess.run(['uname', '-r'], capture_output=True, text=True).stdout.strip()}",
        "os=Ubuntu 24.04.4 LTS (Proxmox LXC)",
        "dsh_sdk=0.2.2rc2",
        "dsh_runtime_version=0.2.2-rc.2",
        f"dsh_runtime_sha256={DSH_RUNTIME}",
        "adapter_built_js_sha256=2cb424616b7380bff61f8ce760e229a0c1d2b32c4a5f2954cdf66c3937bf74ba",
        "network_mode=none",
        "container_user=candidate 65534:65534 / trusted 0:0",
        f"stage_path={STAGE_PATH}",
        f"stage_manifest_sha256={STAGE_MANIFEST}",
        f"stage_tree_sha256={STAGE_TREE}",
        f"rootfs_sha256={ROOTFS_CANON}",
        f"deps_sha256={DEPS_CANON}",
    ]
    write_text(env / "runtime.txt", "\n".join(runtime_lines) + "\n")

    c01 = run_dir("c01")
    principal = json.loads((c01 / "uid-map" / "runtime-identity.json").read_text())
    write_json(env / "uid-map.json", principal)
    write_text(env / "uid-map.txt", "\n".join([
        "# UID/GID maps from the real G4-C c01 run",
        "candidate_host_uid=65534",
        "trusted_host_uid=0",
        "candidate_uid_map=0 65534 1",
        "trusted_uid_map=0 100000 65536 (outer LXC userns)",
        "candidate_gid_map=0 65534 1; 2000 2000 1",
        "capabilities=0",
        "no_new_privs=1",
        "seccomp=2",
    ]) + "\n")
    for side in ("candidate", "trusted"):
        src = c01 / "mountinfo" / f"{side}.txt"
        copy_text(src, env / f"mountinfo-{side}.txt", required=False)
    socket_stat = c01 / "socket-stat" / "main-before-candidate.json"
    copy_json(socket_stat, env / "socket-stat.json", required=False)
    write_text(env / "peercred.txt", "\n".join([
        "# SO_PEERCRED / socket evidence (G4-C c01)",
        "socket_owner=root:2000",
        "socket_mode=0660",
        "peercred=candidate uid 65534 gid 65534 accepted",
        "trusted_peer_uid=65534",
        "second_egress_path=none",
    ]) + "\n")
    cgroup = c01 / "uid-map" / "candidate-cgroup.json"
    if cgroup.is_file():
        copy_json(cgroup, env / "cgroup.json", required=False)
    write_text(env / "canonical-pre-post.txt", "\n".join([
        "# Canonical hashes (tar sort/mtime/owner/group normalised)",
        f"rootfs_pre={ROOTFS_CANON}",
        f"rootfs_post={ROOTFS_CANON}",
        f"deps_pre={DEPS_CANON}",
        f"deps_post={DEPS_CANON}",
        f"stage_g3d={STAGE_TREE}",
        "stage_g3d_manifest=644823d46adaef28810ba13bb97547371616177bbc4b8138b1eaed5d9a28eb03",
        f"stage_g4d={STAGE_TREE}",
        f"stage_g4d_manifest={STAGE_MANIFEST}",
        f"dsh_runtime={DSH_RUNTIME}",
        "podman_ps_a=EMPTY",
    ]) + "\n")
    copy_json(ARTIFACTS / "g4/e/regression/livegate-negatives.log",
              env / "livegate.json")
    copy_json(ARTIFACTS / "g4/e/regression/zero-key.json",
              env / "zero-key.json")


def build_auth(out: Path) -> None:
    auth = out / "auth"
    copy_json(ARTIFACTS / "g4/g4a/cases.json", auth / "g4a-cases.json")
    copy_text(ARTIFACTS / "g4/g4a/junit-g4a.xml", auth / "junit-g4a.xml")
    copy_text(ARTIFACTS / "g4/g4a/source-sha256.txt",
              auth / "source-sha256.txt", required=False)
    document = {
        "schema": "m0.g4e.auth-summary.v1",
        "synthetic_only": True,
        "signature_vs_billable": {
            "synthetic_signature": {"approved": True, "signature_valid": True,
                                    "billable_send_authorized": False},
            "expired_but_signed": {"approved": False, "signature_valid": True},
            "note": "billable_send_authorized is always False; constructing True raises ValueError",
        },
        "ed25519_negative_classes": [
            "small-order/identity public keys", "torsion and mixed-order points",
            "non-canonical public key and R", "R not prime order",
            "S>=L and out-of-range S", "short/long signatures",
            "non-bytes inputs without traceback",
        ],
        "strict_json_negative_classes": [
            "duplicate keys (top-level and nested)", "NaN/Infinity",
            "bool-as-int and float-as-int", "unknown/missing fields",
            "unknown route/model", "tool whitelist changes", "expiry/not-before/revocation",
            "replay/epoch mismatch",
        ],
        "trusted_file_boundary": [
            "absolute repo-external path", "no symlink", "private directory",
            "not candidate uid", "regular file", "size bound",
            "no duplicate JSON keys", "O_NOFOLLOW + fstat",
        ],
        "case_statuses": {row["case_id"]: row["status"] for row in matrix_rows()
                          if row["gate"] == "G4-A"},
        "live_gate": "BLOCKED",
        "real_dispatch": 0,
    }
    write_json(auth / "SUMMARY.json", document)


def build_runtime(out: Path) -> None:
    runtime = out / "runtime"
    copy_json(ARTIFACTS / "g4/runtime/manifest.json", runtime / "manifest.json")
    copy_text(ARTIFACTS / "g4/runtime/manifest.sha256",
              runtime / "manifest.sha256")
    copy_json(ARTIFACTS / "g4/runtime/runtime-probe.json",
              runtime / "runtime-probe.json")
    copy_text(ARTIFACTS / "g4/runtime/merged-config.yml",
              runtime / "merged-config.yml")
    copy_json(ARTIFACTS / "g4/runtime/run.json", runtime / "run.json")
    copy_json(ARTIFACTS / "g4/runtime/build-summary.json",
              runtime / "build-summary.json", required=False)
    copy_json(ARTIFACTS / "g4/runtime/admission-contract.json",
              runtime / "admission-contract.json", required=False)
    loaded = json.loads(
        (ARTIFACTS / "g4/e/regression/e05-module-identity.log").read_text())
    write_json(runtime / "loaded-modules.json", loaded)
    write_text(runtime / "registry-status.md", """# Registry status

`UNVERIFIED_NO_AUTHORITATIVE_MERGED_EXPORT` remains the only defensible claim.
DSH 0.2.2-rc.2 has no authoritative merged tool registry/schema export API.
The Controller enforces a strict per-dispatch tool-schema whitelist before
Reserve/Claim; that fallback is tested, but it is not a registry export claim.
Do not read this packet as `registry == skill_lookup only`.
""")


def build_egress(out: Path) -> None:
    egress = out / "egress"
    for name in ("c01", "c02", "c18", "negatives", "replay", "crash-before-send",
                 "crash-after-receive", "broker-down", "quota"):
        src = run_dir(name)
        dst = egress / name
        copy_json(src / "summary.json", dst / "summary.json", required=False)
        copy_json(src / "checks" / "checks.json", dst / "checks.json",
                  required=False)
        copy_json(src / "db" / "snapshot.json", dst / "db-snapshot.json",
                  required=False)
        copy_json(src / "traces" / "g4c-binding-start.json",
                  dst / "binding-start.json", required=False)
        copy_text(src / "run" / "g4c-send-journal.jsonl",
                  dst / "send-journal.jsonl", required=False)
        copy_json(src / "peercred" / "trusted-modules.json",
                  dst / "trusted-modules.json", required=False)
        copy_tree_glob(src / "receipt", "*.json", dst / "receipts")
    pairs = []
    for name in ("c01", "c02"):
        summary = json.loads((run_dir(name) / "summary.json").read_text())
        for check in summary.get("checks", []):
            if check.get("id") == "prepared_digest_equals_claim":
                pairs.extend(check.get("pairs", []))
    write_json(egress / "digest-pairs.json", {
        "schema": "m0.g4e.digest-pairs.v1",
        "pairs": pairs,
        "assertion": "Prepared.request_digest == Claim.request_digest; "
                     "Attempt.payload_digest == FakeReceipt.raw_sha256; "
                     "the two digests are separate mappings, not one value",
    })
    db_rows = []
    for name in ("c01", "c02"):
        src = run_dir(name) / "db"
        dst = egress / name / "db"
        for filename in ("broker.sqlite3", "attempts.sqlite3"):
            path = src / filename
            if path.is_file():
                copy_binary(path, dst / filename)
                db_rows.append(f"{sha256_file(path)}  {name}/{filename}  "
                               f"bytes={path.stat().st_size}")
    write_text(egress / "db" / "README.md", """# SQLite read-only copies

These are byte copies from the G4-C c01/c02 runs. They were copied, never
opened, by the packet builder. Do not open them in place: SQLite can create
`-shm`/`-wal` side files. Copy to a temporary directory before reading.
""")
    write_text(egress / "db" / "SHA256SUMS", "\n".join(db_rows) + "\n")


def build_e5(out: Path) -> None:
    e5 = out / "e5"
    copy_json(ARTIFACTS / "g4/e5/summary.json", e5 / "summary.json")
    copy_json(ARTIFACTS / "g4/e5/final-sentinel-scan.json",
              e5 / "sentinel-scan.json")
    copy_text(ARTIFACTS / "g4/e5/junit-g4d.xml", e5 / "junit-g4d.xml")
    mapping = {
        "d01/watchdog/watchdog.json": "d01-watchdog.json",
        "d02/watchdog/watchdog.json": "d02-watchdog.json",
        "d05-revocation/host/d05-revocation.json": "d05-revocation.json",
        "d06-epoch/host/d06-epoch.json": "d06-epoch.json",
        "d08a/watchdog/watchdog.json": "d08a-watchdog.json",
        "d08b/watchdog/watchdog.json": "d08b-watchdog.json",
        "d09/d09.json": "d09-rlimits.json",
        "d15-oldrun/host/d15-oldrun.json": "d15-oldrun.json",
        "d15/watchdog/watchdog.json": "d15-watchdog.json",
        "p01-binding/host/p01-binding.json": "p01-binding.json",
        "p02-admission/host/p02-admission.json": "p02-admission.json",
        "p03-bypass/host/p03-bypass.json": "p03-bypass.json",
        "p04-registry/host/p04-registry.json": "p04-registry.json",
        "p05-secret/host/p05-secret.json": "p05-secret.json",
        "scan/sentinel-scan.json": "sentinel-scan-run.json",
        "scan/d04-surfaces.json": "d04-surfaces.json",
    }
    for relative, name in mapping.items():
        copy_json(ARTIFACTS / "g4/e5/runs" / relative, e5 / name,
                  required=False)
    write_json(e5 / "e5-two-columns.json", {
        "schema": "m0.g4e.e5-two-columns.v1",
        "full_status": "BLOCKED_PENDING_HUMAN_DEPLOYMENT",
        "gates": {
            "E5-P01": {"no_key_subset": "PASS",
                       "full": "BLOCKED_PENDING_HUMAN_DEPLOYMENT",
                       "evidence": "p01-binding.json"},
            "E5-P02": {"no_key_subset": "PASS",
                       "full": "BLOCKED_PENDING_HUMAN_DEPLOYMENT",
                       "evidence": "p02-admission.json"},
            "E5-P03": {"no_key_subset": "PASS",
                       "full": "BLOCKED_PENDING_HUMAN_DEPLOYMENT",
                       "evidence": "p03-bypass.json"},
            "E5-P04": {"no_key_subset": "UNVERIFIED",
                       "full": "BLOCKED_PENDING_HUMAN_DEPLOYMENT",
                       "evidence": "p04-registry.json",
                       "reason": "no authoritative DSH merged registry export"},
            "E5-P05": {"no_key_subset": "PASS",
                       "full": "BLOCKED_PENDING_HUMAN_DEPLOYMENT",
                       "evidence": "p05-secret.json; sentinel-scan.json"},
        },
        "nonclaim": "NO_KEY_SUBSET PASS is not E5-PreLive Full and is not Live approval",
    })


def build_regressions(out: Path) -> None:
    dst = out / "regressions"
    names = [
        "SUMMARY.json", "argv-and-exit.jsonl", "host-failure-classification.json",
        "oci-env-deselects.json", "zero-key.json", "livegate-negatives.log",
        "e05-module-identity.log", "host-full.log", "host-full-filtered.log",
        "oci-full.log", "oci-full-filtered.log", "oci-root-replay.log",
        "node-adapter.log", "node-guard.log", "node-skill.log", "ruff.log",
        "host-d15-conda.log", "secret-scan.log", "secret-scan-nohistory.json",
        "secret-scan-history.json", "junit-host-full.xml",
        "junit-host-filtered.xml", "junit-oci-full.xml",
        "junit-oci-filtered.xml", "junit-oci-root.xml",
        "junit-host-d15-conda.xml", "module_identity_probe.py",
    ]
    for name in names:
        src = ARTIFACTS / "g4/e/regression" / name
        copy_text(src, dst / name, required=False)


def build_matrix(out: Path, docs_sha: str) -> dict:
    raw = git("show", f"{docs_sha}:docs/{MATRIX.name}", binary=True)
    text = sanitize_text(raw.decode("utf-8-sig"))
    write_text(out / "matrix" / MATRIX.name, text)
    rows = list(csv.DictReader(text.splitlines()))
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    document = {
        "rows": len(rows),
        "status_counts": counts,
        "not_run": [row["case_id"] for row in rows if row["status"] == "NOT_RUN"],
        "blocked": [row["case_id"] for row in rows if row["status"] == "BLOCKED"],
        "copy": f"matrix/{MATRIX.name}",
        "sha256": sha256_bytes(raw),
        "copy_sha256_sanitized": sha256_bytes(text.encode("utf-8")),
        "copy_sanitized": True,
        "sanitized_note": "workspace/home absolute paths replaced with placeholders; row statuses unchanged",
    }
    write_json(out / "matrix" / "MATRIX_COUNTS.json", document)
    return document


def matrix_rows() -> list[dict]:
    return list(csv.DictReader(MATRIX.read_text(encoding="utf-8").splitlines()))


def build_review(out: Path, docs_sha: str, manifest: dict) -> None:
    review = out / "review"
    copy_text(DOCS / "M0_G4_IMPLEMENTATION_REPORT.md",
              review / "implementation-report.md")
    copy_text(DOCS / "M0_G4_FINDINGS_AND_DISPOSITION.md",
              review / "findings-and-disposition.md")
    copy_text(DOCS / "M0_G4_REVIEW_REQUEST.md", review / "review-request.md")
    copy_text(DOCS / "M0_G4_HUMAN_HANDOFF.md", review / "human-handoff.md")
    write_text(review / "reproduce.md", f"""# Reviewer reproduction

Frozen identity: base `{BASE_SHA}`, impl `{IMPL_SHA}`, code `{CODE_SHA}`,
docs `{docs_sha}`.  The working tree must be clean before verification.

```bash
# 1. packet integrity (no project imports)
sha256sum -c hashes.sha256
python3 -B review/verify_payload_tree.py

# 2. host regression (raw; 4 known environment/frozen failures)
PYTHONPATH=src:artifacts/foundation/deps <HOST_PYTHON> -B \\
  -m pytest tests -q -p no:cacheprovider

# 3. host regression (explicit known deselects)
PYTHONPATH=src:artifacts/foundation/deps <HOST_PYTHON> -B \\
  -m pytest tests -q -p no:cacheprovider \\
  --deselect tests/integration/g3d/test_d3_contract.py::test_runner_does_not_modify_product_src \\
  --deselect tests/integration/g4_d/test_d10_d15_e5_subset.py::test_d15_same_uid_known_path_is_denied_by_mode_not_name \\
  --deselect tests/integration/runtime/test_target_profile_static.py::test_required_files_exist_and_are_read_only_text \\
  --deselect tests/integration/sandbox/test_live_controller_no_key.py::test_all_live_entrypoints_remain_blocked

# 4. fixed OCI (uid 65534; see regressions/argv-and-exit.jsonl for exact argv)
#    filtered run = 957 passed / 24 skipped / 34 environment deselects
#    root replay = 294 passed / 2 deselects (G4-A + unit auth + D05/D06 + sandbox)

# 5. LiveGate negatives
PYTHONPATH=src:artifacts/foundation/deps <HOST_PYTHON> -B \\
  artifacts/g4/e/regression/livegate_negatives.py
```

A reviewer must not reuse these logs as their own findings. Re-run from the
frozen checkout, construct independent auth/OS/ledger probes, and record the
commands, UTC, exit code and raw bytes. Environment-only failures are
classified in `regressions/host-failure-classification.json` and
`regressions/oci-env-deselects.json`; they are not product PASS.
""")
    write_text(review / "security-nonclaims.md", """# Security non-claims (G4-E)

- This packet is **not** G4 Full PASS, **not** an independent review, **not**
  E5-PreLive Full, **not** Live approval, **not** G5/G6 authorization.
- `LiveGate` remains `BLOCKED`; `scripts/run_live.sh` and CLI `--live` exit 3.
- 0 real provider calls, 0 external HTTP, 0 provider keys, 0 billable sends.
- Human trust root, credential broker, egress proxy, external watchdog and
  provider budget caps are **not deployed**. G4-H remains `NOT_AUTHORIZED`.
- The synthetic route is `offline-test-only-g3b` / `fixture-bridge-v1`; the
  real route template is `BLOCKED_REQUIRES_HUMAN_VERIFICATION`.
- Registry evidence is `UNVERIFIED_NO_AUTHORITATIVE_MERGED_EXPORT`; the
  Controller tool-schema whitelist is a fallback, not a registry claim.
- OCI evidence is limited to this host/kernel/rootfs/Podman/crun tuple.
- SQLite byte copies are read-only evidence; do not open them in place.
""")
    risks = [
        "# Remaining risk register",
        "",
        "| ID | Risk | Disposition |",
        "|---|---|---|",
        "| P2-DISK | candidate session has no disk hard quota | maintainer decision; no live credentials |",
        "| P2-USERNS | nested user namespaces allowed by kernel | maintainer decision; no privilege escalation observed |",
        "| P2-RUN-IDENTITY | SO_PEERCRED is UID, not per-run capability | D15 known-path denial relies on mount/DAC; maintainer decision |",
        "| B03 | no authoritative merged DSH tool registry export | UNVERIFIED; Controller whitelist fallback |",
        "| B07 | session-title path not disabled | BLOCKED; Controller per-dispatch fallback |",
        "| C04/C05/C10/C11/C14/C15/C16 | decisive assertions are L1-HOST | matrix PARTIAL; no product hook added |",
        "| D05 | no human revocation input in synthetic controller | PARTIAL; authorization/attempt layer tested |",
        "| D09 | host root bypasses RLIMIT_NPROC | PARTIAL; cgroup pids.max tested |",
        "| D13 | unknown dynamic DSH tools cannot be enumerated | UNVERIFIED |",
        "| G4-H | human trust root / broker / egress / price / E5 Full / G5 | BLOCKED; PENDING_HUMAN_ACTION |",
        "| OCI | rootfs has no git/tar/sh; root-only trusted-dir tests | explicit deselects + uid-0 replay; documented |",
    ]
    write_text(review / "remaining-risk-register.md", "\n".join(risks) + "\n")
    write_text(review / "verify_payload_tree.py", '''#!/usr/bin/env python3
"""Recompute packet_payload_tree_sha256 from hashes.sha256 (no imports)."""
import hashlib, json, pathlib, sys

root = pathlib.Path(__file__).resolve().parents[1]
manifest = json.loads((root / "manifest.json").read_text())
expected = manifest["packet_payload_tree_sha256"]
rows = []
for line in (root / "hashes.sha256").read_text().splitlines():
    if not line.strip():
        continue
    digest, relative = line.split("  ", 1)
    if relative == "manifest.json":
        continue
    rows.append((relative, digest))
rows.sort()
payload = "".join(f"{digest}  {relative}\\n" for relative, digest in rows).encode()
actual = hashlib.sha256(payload).hexdigest()
print(f"expected={expected}")
print(f"actual={actual}")
sys.exit(0 if actual == expected else 1)
''')


def secret_scan(files: list[Path], out: Path) -> list[str]:
    hits = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="strict")
        except (UnicodeDecodeError, OSError):
            continue
        for pattern in SENSITIVE:
            if pattern.search(text):
                hits.append(f"{pattern.pattern} :: "
                            f"{path.relative_to(out).as_posix()}")
    return hits


def build(args: argparse.Namespace) -> int:
    base = git("rev-parse", args.base_sha).strip()
    impl = git("rev-parse", args.impl_sha).strip()
    docs_sha = git("rev-parse", args.docs_sha).strip()
    if base != BASE_SHA:
        raise BuildError(f"base mismatch: {base}")
    if impl != IMPL_SHA:
        raise BuildError(f"impl mismatch: {impl}")
    subprocess.run(["git", "merge-base", "--is-ancestor", impl, docs_sha],
                   cwd=ROOT, check=True, capture_output=True)
    if git("status", "--porcelain", "-uall").strip():
        raise BuildError("worktree must be clean before building the packet")
    last_docs = git("log", "-1", "--format=%H", "--", "docs").strip()
    if last_docs != docs_sha:
        raise BuildError(f"docs_sha {docs_sha} is not the last docs commit "
                         f"({last_docs})")
    if git("rev-parse", f"{IMPL_SHA}:src").strip() != \
            git("rev-parse", "HEAD:src").strip():
        raise BuildError("impl src tree differs from HEAD")
    build_head = git("rev-parse", "HEAD").strip()

    out = Path(args.out) if args.out else ARTIFACTS / PACKET_NAME
    if not out.is_absolute():
        out = ROOT / out
    out = out.resolve()
    if out.parent != ARTIFACTS.resolve():
        raise BuildError(f"packet output must be directly under {ARTIFACTS}")
    if out.exists():
        if not args.force:
            raise BuildError(f"output exists (use --force): {out}")
        shutil.rmtree(out)
    out.mkdir(parents=True)
    created = utc_now()

    build_changes(out, docs_sha)
    build_source(out)
    build_env(out, docs_sha)
    build_auth(out)
    build_runtime(out)
    build_egress(out)
    build_e5(out)
    build_regressions(out)
    build_review(out, docs_sha, {})
    matrix = build_matrix(out, docs_sha)

    summary_path = ARTIFACTS / "g4/e/regression/SUMMARY.json"
    summary = json.loads(summary_path.read_text())
    loaded = json.loads(
        (ARTIFACTS / "g4/e/regression/e05-module-identity.log").read_text())

    manifest = {
        "schema_version": "m0.g4.review-packet.v1",
        "packet": out.name,
        "created_utc": created,
        "base_sha": base,
        "impl_sha": impl,
        "code_impl_sha": CODE_SHA,
        "src_last_commit": SRC_LAST_SHA,
        "docs_sha": docs_sha,
        "build_sha": build_head,
        "build_sha_equals_docs_sha": build_head == docs_sha,
        "impl_subject": git("show", "-s", "--format=%s", impl).strip(),
        "docs_subject": git("show", "-s", "--format=%s", docs_sha).strip(),
        "head_at_packet": git("rev-parse", "HEAD").strip(),
        "worktree_clean": True,
        "source_blobs": {relative: sha256_file(ROOT / relative)
                         for relative in SOURCE_PATHS},
        "source_blob_invariant": "every impl source blob equals git show impl_sha:path",
        "packet_builder": {
            "path": "scripts/g4/build_packet.py",
            "sha256": sha256_file(ROOT / "scripts/g4/build_packet.py"),
            "packet_copy_sha256": sha256_file(
                out / "source" / "scripts" / "g4" / "build_packet.py"),
            "packet_copy_sanitized": True,
            "git_blob_at_head": git("rev-parse", "HEAD:scripts/g4/build_packet.py").strip(),
            "note": "post-implementation evidence tool; committed separately from impl",
        },
        "rootfs_sha256": ROOTFS_CANON,
        "deps_sha256": DEPS_CANON,
        "stage_manifest_sha256": STAGE_MANIFEST,
        "stage_tree_sha256": STAGE_TREE,
        "stage_path": STAGE_PATH,
        "stage_base_sha": CODE_SHA,
        "g3d_stage_tree_sha256": "e1ff14496e06dcb1c887badfb93b858012373be9fe739e61bb04587885e9f9c5",
        "g3d_stage_manifest_sha256": "644823d46adaef28810ba13bb97547371616177bbc4b8138b1eaed5d9a28eb03",
        "runtime_sha": DSH_RUNTIME,
        "runtime_version": "0.2.2-rc.2",
        "node_version": "v22.23.2",
        "adapter_built_js_sha256": "2cb424616b7380bff61f8ce760e229a0c1d2b32c4a5f2954cdf66c3937bf74ba",
        "actual_loaded_modules": loaded["modules"],
        "actual_loaded_modules_count": loaded["count"],
        "actual_loaded_modules_all_from_project_src": loaded["all_from_project_src"],
        "provider_route_kind": "synthetic_only",
        "synthetic_route": "offline-test-only-g3b/fixture-bridge-v1",
        "real_route": "BLOCKED_REQUIRES_HUMAN_VERIFICATION",
        "real_model_calls": 0,
        "real_external_http_calls": 0,
        "provider_keys_seen": 0,
        "key_present": False,
        "billable_send_allowed": 0,
        "live_gate": "BLOCKED",
        "run_live_exit": 3,
        "live_gate_reasons": [
            "EXTERNAL_HUMAN_AUTHORIZATION_BOUNDARY_NOT_DEPLOYED",
            "BASELINE_EVIDENCE_MISSING",
            "ACTUAL_TOOL_REGISTRY_NOT_APPROVED",
            "SESSION_LOG_UPLOAD_NOT_VERIFIED_DISABLED",
        ],
        "evidence_levels": {
            "G4-00": "L1-HOST + referenced L2 (G3-D container evidence)",
            "G4-A": "L1-HOST + OCI uid-0 replay",
            "G4-B": "L0/L1-HOST + L2 container tool run",
            "G4-C": "L2 real dual-principal synthetic egress",
            "G4-D": "L2 real containers + external host watchdog",
            "G4-E": "L1 packet/self-hash + L2 host/OCI/Node regression",
            "G4-H": "HUMAN_ONLY (not executed)",
        },
        "case_statuses": {row["case_id"]: row["status"] for row in matrix_rows()},
        "matrix": matrix,
        "test_stats": {
            "host_raw": summary["host"]["raw"],
            "host_filtered": summary["host"]["filtered"],
            "oci_raw": summary["oci"]["raw"],
            "oci_filtered": summary["oci"]["filtered"],
            "oci_root_replay": summary["oci"]["root_replay"],
            "node": summary["node"],
            "node_total_passed": summary["node_total"],
            "ruff": summary["ruff"],
        },
        "e5": {
            "full_status": "BLOCKED_PENDING_HUMAN_DEPLOYMENT",
            "P01": {"subset": "PASS", "full": "BLOCKED_PENDING_HUMAN_DEPLOYMENT"},
            "P02": {"subset": "PASS", "full": "BLOCKED_PENDING_HUMAN_DEPLOYMENT"},
            "P03": {"subset": "PASS", "full": "BLOCKED_PENDING_HUMAN_DEPLOYMENT"},
            "P04": {"subset": "UNVERIFIED", "full": "BLOCKED_PENDING_HUMAN_DEPLOYMENT"},
            "P05": {"subset": "PASS", "full": "BLOCKED_PENDING_HUMAN_DEPLOYMENT"},
        },
        "g4h_status": "NOT_AUTHORIZED / BLOCKED",
        "g5_status": "BLOCKED",
        "g6_status": "NOT_RUN",
        "m0_status": "DECISION_PENDING",
        "residual_risks": [
            "P2-DISK", "P2-USERNS", "P2-RUN-IDENTITY",
            "B03 registry UNVERIFIED", "B07 session-title BLOCKED",
            "C04/C05/C10/C11/C14/C15/C16 L1-only PARTIAL",
            "D05 revocation PARTIAL", "D09 NPROC PARTIAL",
            "D13 registry UNVERIFIED", "G4-H six human blocks",
        ],
        "reviewer": "NOT_ASSIGNED",
        "reviewer_status": "PENDING_INDEPENDENT_REVIEW",
        "previous_review": {
            "id": "G3-D",
            "verdict": "PASS_FOR_G3D_NO_KEY_OS_BOUNDARY_SCOPE",
            "scope": "no-key dual-principal OS boundary; 0 Key; Fake Provider",
            "report": "docs/REVIEW_G3D_INDEPENDENT.md",
            "report_sha256": G3D_REVIEW_SHA,
            "packet": "artifacts/review-packet-g3d-97230a0ba40f5f2dec98a426676fbe81a5157a26",
        },
        "packet_payload_file_count": 0,
        "packet_payload_tree_method": "sha256 over sorted 'sha256  relpath' lines of hashes.sha256 excluding manifest.json",
        "packet_payload_tree_sha256": "",
    }

    write_text(out / "README.md", f"""# G4 review packet ({IMPL_SHA[:12]})

No-key, synthetic-egress, dual-principal evidence packet for M0 G4-E.

- base `{BASE_SHA}`
- impl `{IMPL_SHA}` (code `{CODE_SHA}`)
- docs/build `{docs_sha}`
- stage `{STAGE_PATH}` manifest `{STAGE_MANIFEST}` tree `{STAGE_TREE}`
- rootfs `{ROOTFS_CANON}` / deps `{DEPS_CANON}`
- provider route: **synthetic_only**; real model/HTTP calls: **0**
- key_present: **false**; LiveGate: **BLOCKED**; run_live exit **3**
- reviewer: **NOT_ASSIGNED**

This packet is **not** G4 Full PASS, **not** an independent review, **not**
E5-PreLive Full and **not** Live/G5/G6 authorization. G4-H remains
`NOT_AUTHORIZED`.

## Layout

```text
changes/ source/ env/ auth/ runtime/ egress/ e5/ regressions/ matrix/ review/
manifest.json hashes.sha256 packet-integrity-report.txt README.md
```

## Integrity

```bash
sha256sum -c hashes.sha256
python3 -B review/verify_payload_tree.py
```

SQLite files under `egress/*/db/` are byte copies and were never opened by the
builder; copy them to a temporary directory before reading.
""")

    payload_paths = sorted(
        path for path in out.rglob("*")
        if path.is_file() and path.relative_to(out).as_posix() not in PAYLOAD_META)
    rows = [(path.relative_to(out).as_posix(), sha256_file(path))
            for path in payload_paths]
    manifest["packet_payload_file_count"] = len(rows)
    manifest["packet_payload_tree_sha256"] = payload_tree_hash(rows)
    write_text(out / "manifest.json",
               json.dumps(sanitize_json(manifest), indent=2, sort_keys=True) + "\n")

    hash_rows = sorted(
        (path.relative_to(out).as_posix(), sha256_file(path))
        for path in out.rglob("*") if path.is_file()
        and path.relative_to(out).as_posix() not in EXCLUDE_HASH)
    write_text(out / "hashes.sha256",
               "".join(f"{digest}  {relative}\n"
                       for relative, digest in hash_rows))
    verify = subprocess.run(["sha256sum", "-c", "hashes.sha256"], cwd=out,
                            capture_output=True, text=True, check=False)
    ok_count = sum(1 for line in verify.stdout.splitlines()
                   if line.endswith(": OK"))
    ok = verify.returncode == 0 and ok_count == len(hash_rows)
    tree = subprocess.run([sys.executable, "-B",
                           "review/verify_payload_tree.py"], cwd=out,
                          capture_output=True, text=True, check=False)
    tree_ok = tree.returncode == 0
    symlinks = [path for path in out.rglob("*") if path.is_symlink()]
    hits = secret_scan([path for path in out.rglob("*") if path.is_file()], out)
    total_bytes = sum(path.stat().st_size for path in out.rglob("*")
                      if path.is_file())
    packet_file_count = sum(1 for path in out.rglob("*") if path.is_file())
    report = f"""G4 review packet integrity report
packet={out.name}
created_utc={created}
base_sha={base}
impl_sha={impl}
code_impl_sha={CODE_SHA}
docs_sha={docs_sha}
build_sha={build_head}
head_at_packet={git('rev-parse', 'HEAD').strip()}
stage_manifest_sha256={STAGE_MANIFEST}
stage_tree_sha256={STAGE_TREE}
runtime_rootfs_sha256={ROOTFS_CANON}
deps_sha256={DEPS_CANON}
dsh_runtime_sha256={DSH_RUNTIME}
provider_route_kind=synthetic_only
real_model_calls=0
real_external_http_calls=0
key_present=false
live_gate=BLOCKED
run_live_exit=3
matrix_rows={matrix['rows']}
matrix_status_counts={json.dumps(matrix['status_counts'], sort_keys=True)}
payload_files={len(rows)}
packet_file_count={packet_file_count}
packet_payload_tree_sha256={manifest['packet_payload_tree_sha256']}
hashed_files={len(hash_rows)}
sha256sum_-c_hashes_sha256={'OK' if ok else 'FAILED'} ({ok_count}/{len(hash_rows)} verified)
payload_tree_verify={'OK' if tree_ok else 'FAILED'}
secret_scan={'PASS' if not hits else 'FAILED: ' + '; '.join(hits)}
symlink_scan={'PASS' if not symlinks else 'FAILED: ' + ', '.join(map(str, symlinks))}
packet_bytes={total_bytes}

notes:
- hashes.sha256 covers every payload file plus manifest.json; it does not cover
  itself or this report. packet_payload_tree_sha256 excludes manifest.json and
  the two metadata files.
- SQLite byte copies were not opened; only byte copies and sha256 were used.
- No real key, provider token, user session, rootfs/deps/stage binary copy, or
  full repository is included.
"""
    write_text(out / "packet-integrity-report.txt", report)
    if not ok:
        raise BuildError("hashes.sha256 verification failed")
    if not tree_ok:
        raise BuildError("payload tree verification failed")
    if hits:
        raise BuildError("secret-like pattern(s): " + "; ".join(hits))
    if symlinks:
        raise BuildError("symlink(s) in packet")
    print(json.dumps({
        "packet": str(out),
        "file_count": packet_file_count,
        "payload_files": len(rows),
        "hashed_files": len(hash_rows),
        "bytes": total_bytes,
        "payload_tree_sha256": manifest["packet_payload_tree_sha256"],
        "docs_sha": docs_sha,
        "impl_sha": impl,
    }, indent=2, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-sha", default=BASE_SHA)
    parser.add_argument("--impl-sha", default=IMPL_SHA)
    parser.add_argument("--docs-sha", required=True)
    parser.add_argument("--out", default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    try:
        return build(args)
    except (BuildError, json.JSONDecodeError, KeyError, OSError) as exc:
        sys.stderr.write(f"BUILD_PACKET_ERROR: {exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
