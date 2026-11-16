#!/usr/bin/env python3
"""G3-B B4 Review Packet builder (host-side, read-only git/fs; no project code).

Usage (always avoid host bytecode):
  PYTHONDONTWRITEBYTECODE=1 python3 -B scripts/g3b/build_packet.py \
    --base-sha 0876816 --impl-sha <final-B3-commit> --docs-sha <docs-commit> \
    --status-file /path/to/tests-status.json \
    --out artifacts/review-packet-g3b-<impl-sha> [--force]

The builder NEVER mutates src/, spikes/, tests/, plugins/, docs/ or the existing
evidence root. It only writes inside the requested --out directory (must live
under artifacts/). It does not run project pytest/Node, does not use a network,
does not read credentials, and does not fabricate PASS counts.

tests-status.json shape:
  {"tests_executed": ["case-id", ...],
   "blocked_cases": ["case-id", ...],
   "notes": "optional"}
If omitted, manifest records <<PENDING B3 PHASE2>> placeholders (dry-run only).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Iterable

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "artifacts"
BASE_DEFAULT = "0876816"
RUNTIME_VERSION = "0.2.2-rc.2"
SDK_VERSION = "0.2.2rc2"
NODE_VERSION = "v22.23.2"
PYTHON_VERSION = "3.11.15"
ROOTFS_DEFAULT = ROOT / "artifacts/security/rootfs"
DEPS_DEFAULT = ROOT / "artifacts/foundation/deps"
EVIDENCE_DEFAULT = ROOT / "artifacts/g3b-trusted-bridge"
STAGE_DEFAULT = EVIDENCE_DEFAULT / "stage-b3"
PENDING = "<<PENDING B3 PHASE2>>"
CORE_SOURCE_PATHS = [
    "src/autoteacher_m0/security/egress.py",
    "src/autoteacher_m0/security/gates.py",
    "src/autoteacher_m0/runtime/dsh_adapter.py",
    "scripts/run_live.sh",
    "src/autoteacher_m0/accounting/call_identity.py",
    "src/autoteacher_m0/accounting/broker.py",
    "src/autoteacher_m0/accounting/ledger.py",
    "src/autoteacher_m0/accounting/observation.py",
    "src/autoteacher_m0/accounting/broker_usage.py",
    "src/autoteacher_m0/accounting/budget.py",
    "plugins/runtime-budget-guard/src/index.ts",
    "plugins/skill-lookup/src/index.ts",
]
SENSITIVE_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{16,}"),
    re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----"),
    re.compile(r"(?i)(?:api[_-]?key|access[_-]?token|secret[_-]?key)\s*[:=]\s*['\"][A-Za-z0-9_\-]{16,}['\"]"),
    re.compile(r"(?i)authorization\s*:\s*bearer\s+[A-Za-z0-9._-]{16,}"),
]


def eprint(message: str) -> None:
    sys.stderr.write(message + "\n")


def run_git(*args: str, binary: bool = False) -> bytes:
    result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.decode('utf-8', 'replace')}")
    return result.stdout if binary else result.stdout


def git_text(*args: str) -> str:
    return run_git(*args).decode("utf-8", "replace")


def resolve_sha(name: str) -> str:
    return git_text("rev-parse", "--verify", f"{name}^{{commit}}").strip()


def git_show(sha: str, path: str) -> bytes:
    return run_git("show", f"{sha}:{path}", binary=True)


def git_paths(sha: str) -> set[str]:
    return set(git_text("ls-tree", "-r", "--name-only", sha).splitlines())


def git_blob_sha(sha: str, path: str) -> str:
    return git_text("rev-parse", f"{sha}:{path}").strip()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalized_tar_sha256(directory: Path) -> tuple[str, int, int]:
    """Canonical identity: sorted name/mtime=0/owner=0/group=0 mode as tar."""
    if not directory.exists():
        return PENDING, 0, 0
    digest = hashlib.sha256()
    process = subprocess.Popen(
        ["tar", "--sort=name", "--mtime=@0", "--owner=0", "--group=0",
         "--numeric-owner", "-cf", "-", "-C", str(directory), "."],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    assert process.stdout is not None
    for chunk in iter(lambda: process.stdout.read(1024 * 1024), b""):
        digest.update(chunk)
    stderr = process.stderr.read() if process.stderr else b""
    if process.wait() != 0:
        raise RuntimeError(f"tar failed for {directory}: {stderr.decode('utf-8', 'replace')}")
    files = sum(1 for p in directory.rglob("*") if p.is_file())
    size = sum(p.stat().st_size for p in directory.rglob("*") if p.is_file())
    return digest.hexdigest(), files, size


def copy_bytes(data: bytes, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)


def copy_tree_files(source: Path, target: Path) -> int:
    if not source.exists():
        return 0
    count = 0
    for item in source.rglob("*"):
        if item.is_file():
            relative = item.relative_to(source)
            (target / relative).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(item, target / relative)
            count += 1
    return count


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip("\n") + "\n", encoding="utf-8")


def load_status(path: str | None) -> tuple[object, object, str]:
    if not path:
        return [PENDING], [PENDING], "status file absent; placeholders written for dry-run"
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    executed = data.get("tests_executed")
    blocked = data.get("blocked_cases")
    if not isinstance(executed, list) or not isinstance(blocked, list):
        raise ValueError("status file must contain list fields tests_executed and blocked_cases")
    return executed, blocked, str(data.get("notes", ""))


def source_and_test_paths(base: str, impl: str) -> tuple[list[str], list[str], list[str]]:
    output = git_text("diff", "--name-status", "--find-renames", base, impl)
    changed: list[str] = []
    deleted: list[str] = []
    for line in output.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status, path = parts[0], parts[-1]
        if status.startswith("D"):
            deleted.append(path)
        else:
            changed.append(path)
    impl_paths = git_paths(impl)
    source = sorted({p for p in changed if p.startswith(("src/", "spikes/", "plugins/", "scripts/"))})
    source = sorted(set(source) | {p for p in CORE_SOURCE_PATHS if p in impl_paths})
    tests = sorted({p for p in changed if p.startswith("tests/")}
                   | {p for p in impl_paths if p.startswith("tests/integration/g3_bridge/")})
    return source, tests, deleted


def copy_git_files(impl: str, paths: Iterable[str], target_root: Path, list_name: str) -> tuple[int, list[dict]]:
    rows: list[dict] = []
    for path in paths:
        data = git_show(impl, path)
        target = target_root / path
        copy_bytes(data, target)
        rows.append({"path": path, "sha256": sha256_bytes(data), "git_blob": git_blob_sha(impl, path)})
    write_text(target_root / list_name,
               json.dumps({"implementation_sha": impl, "files": rows}, indent=2, sort_keys=True))
    return len(rows), rows


def evidence_tree_hash(root: Path) -> tuple[str, int]:
    if not root.exists():
        return PENDING, 0
    digest = hashlib.sha256()
    count = 0
    for item in sorted(p for p in root.rglob("*") if p.is_file()):
        digest.update(str(item.relative_to(root)).encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha256_file(item).encode("ascii"))
        digest.update(b"\n")
        count += 1
    return digest.hexdigest(), count


def build_readme(manifest: dict[str, object]) -> str:
    return f"""# G3-B Review Packet

- Base: `{manifest['base_sha']}`
- Implementation: `{manifest['implementation_sha']}`
- Docs: `{manifest['docs_sha']}`
- Packet generated UTC: `{manifest['generated_utc']}`
- Scope: G3-B no-key trusted bridge / Fake Provider / real SQLite Broker integration.
- **No final verdict is encoded here.** Reviewer must independently verify.

This packet contains source/tests/protocol copies tied to Git blobs, raw evidence
copies, `diff.patch` (binary), `hashes.sha256`, and `packet-integrity-report.txt`.

Layout: `source/` and `tests/` preserve the repository-relative path (e.g.
`source/src/...`, `tests/tests/integration/...`) so each file can be compared
directly with `git show <impl-sha>:<path>`; `source/source-file-list.txt` and
`tests/test-file-list.txt` record the expected path/SHA-256/blob.

Purposes/limits: synthetic Fake Provider only; no real API key/model/HTTP/Live.
Local claim is not remote exactly-once; OS trust boundary is `BLOCKED` (same
container/uid). Do not treat this packet as a GO/Live authorization.

See `manifest.json`, `security-nonclaims.md`, `reviewer-reproduction.md`.
"""


def build_nonclaims() -> str:
    return """# G3-B Security Non-claims

- No real API key was present or read; `key_present=false`, `real_model_calls=0`, `external_http_calls=0`.
- Fake Provider is synthetic; its usage/receipt is NOT real supplier usage or invoice evidence.
- Local SQLite claim/attempt provides local at-most-one-send authorization, not remote exactly-once.
- Same-container/same-uid execution cannot prove the OS trust boundary; B0-02 remains BLOCKED.
- No LiveGate/Adapter/run_live unlock; no GO/Live authorization is implied.
- Guard+Bridge combination results must be read only from the final matrix; native Guard
  tests alone do not constitute combination PASS.
- Any missing/blocked case must remain BLOCKED/UNVERIFIED; never infer PASS from absence.
"""


def build_reproduction(manifest: dict[str, object]) -> str:
    return f"""# Reviewer Reproduction (template)

Verify identity first (host, read-only):

```bash
cd "/root/Autonomous Teacher"
git rev-parse HEAD ^{{tree}} 2>/dev/null || true
git diff --check {manifest['base_sha']} {manifest['implementation_sha']}
git diff --binary {manifest['base_sha']} {manifest['implementation_sha']} | sha256sum
# compare with manifest.diff_sha256 and diff.patch
```

Minimal host tests (avoid host bytecode / deps drift):

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -B -m pytest tests/integration/g3_bridge -q
PYTHONDONTWRITEBYTECODE=1 python3 -B -m pytest tests/ -q
PYTHONDONTWRITEBYTECODE=1 python3 -B -m ruff check src tests
```

Real-DSH/Fake matrix (fixed rootfs; see repository's G3-B scripts; do not use
host Node/Python project code outside the fixed OCI):

```bash
# Run the frozen B3 suite script from the implementation commit:
bash spikes/g3b-trusted-bridge/scripts/run-suite.sh
# Reviewer must replace any truncated argv with the real commands recorded in
# logs/commands.jsonl and must check container absence after the run.
```

Reviewers must independently confirm source hashes, Fake received-counter, Broker
SQLite rows, and that no unapproved send occurs. Do not copy owner PASS claims.
"""


def sensitive_findings(packet: Path) -> list[str]:
    findings: list[str] = []
    for item in sorted(p for p in packet.rglob("*") if p.is_file()):
        if item.name in {"hashes.sha256", "packet-integrity-report.txt"}:
            continue
        try:
            text = item.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for pattern in SENSITIVE_PATTERNS:
            if pattern.search(text):
                findings.append(f"{item.relative_to(packet)}: matched {pattern.pattern[:40]}")
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-sha", default=BASE_DEFAULT)
    parser.add_argument("--impl-sha", required=True)
    parser.add_argument("--docs-sha", default=None)
    parser.add_argument("--out", required=True)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--status-file", default=None)
    parser.add_argument("--evidence-root", default=str(EVIDENCE_DEFAULT))
    parser.add_argument("--stage-dir", default=str(STAGE_DEFAULT))
    parser.add_argument("--rootfs-dir", default=str(ROOTFS_DEFAULT))
    parser.add_argument("--deps-dir", default=str(DEPS_DEFAULT))
    parser.add_argument("--runtime-version", default=RUNTIME_VERSION)
    parser.add_argument("--sdk-version", default=SDK_VERSION)
    parser.add_argument("--node-version", default=NODE_VERSION)
    parser.add_argument("--python-version", default=PYTHON_VERSION)
    parser.add_argument("--isolation-probe-file", default=None)
    parser.add_argument("--container-absence-file", default=None)
    parser.add_argument("--matrix-file", default=None,
                        help="final docs matrix CSV; defaults to docs/Autonomous_Teacher_M0_G3B_Review_Evidence_Matrix_v1.0.csv")
    parser.add_argument("--identity-file", default=None,
                        help="final B4 identity JSON; defaults to evidence/env/b4-identity.json when present")
    args = parser.parse_args()

    base = resolve_sha(args.base_sha)
    impl = resolve_sha(args.impl_sha)
    docs = resolve_sha(args.docs_sha) if args.docs_sha else impl
    out = Path(args.out)
    if not out.is_absolute():
        out = ROOT / out
    out = out.resolve()
    artifacts = ARTIFACTS.resolve()
    if artifacts not in [out, *out.parents]:
        raise SystemExit("--out must be inside the repository artifacts/ directory")
    if out.exists() and any(out.iterdir()) and not args.force:
        raise SystemExit(f"output directory exists and is non-empty: {out} (use --force only for a deliberate rebuild)")
    if out == EVIDENCE_DEFAULT.resolve():
        raise SystemExit("refusing to overwrite the existing evidence root")
    evidence_root = Path(args.evidence_root)
    if not evidence_root.is_absolute():
        evidence_root = ROOT / evidence_root
    evidence_root = evidence_root.resolve()
    stage_dir = Path(args.stage_dir)
    if not stage_dir.is_absolute():
        stage_dir = ROOT / stage_dir
    matrix_path = Path(args.matrix_file) if args.matrix_file else ROOT / "docs/Autonomous_Teacher_M0_G3B_Review_Evidence_Matrix_v1.0.csv"
    if not matrix_path.is_absolute():
        matrix_path = ROOT / matrix_path
    identity_path = Path(args.identity_file) if args.identity_file else evidence_root / "env" / "b4-identity.json"
    if not identity_path.is_absolute():
        identity_path = ROOT / identity_path
    rootfs_dir = Path(args.rootfs_dir)
    if not rootfs_dir.is_absolute():
        rootfs_dir = ROOT / rootfs_dir
    deps_dir = Path(args.deps_dir)
    if not deps_dir.is_absolute():
        deps_dir = ROOT / deps_dir

    evidence_before, evidence_files_before = evidence_tree_hash(evidence_root)
    tests_executed, blocked_cases, status_notes = load_status(args.status_file)

    if args.force and out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    for name in ("source", "tests", "protocols", "traces", "ledger", "logs", "env"):
        (out / name).mkdir(exist_ok=True)

    # diff.patch must be byte-identical to git diff --binary base..impl.
    diff_bytes = run_git("diff", "--binary", base, impl, binary=True)
    copy_bytes(diff_bytes, out / "diff.patch")
    diff_sha = sha256_bytes(diff_bytes)

    source_paths, test_paths, deleted_paths = source_and_test_paths(base, impl)
    source_count, source_rows = copy_git_files(impl, source_paths, out / "source", "source-file-list.txt")
    test_count, test_rows = copy_git_files(impl, test_paths, out / "tests", "test-file-list.txt")
    # Protocol docs are part of docs freeze; fall back to impl for dry-run.
    protocols = [
        "docs/M0_G3B_IPC_PROTOCOL.md",
        "docs/M0_G3B_SECURITY_AND_ACCOUNTING_CONTRACT.md",
    ]
    for path in protocols:
        try:
            data = git_show(docs, path)
        except RuntimeError:
            data = git_show(impl, path)
        copy_bytes(data, out / "protocols" / path.split("/")[-1])

    copy_tree_files(evidence_root / "traces", out / "traces")
    copy_tree_files(evidence_root / "ledger", out / "ledger")
    copy_tree_files(evidence_root / "logs", out / "logs")
    if (evidence_root / "commands.jsonl").exists():
        shutil.copyfile(evidence_root / "commands.jsonl", out / "logs" / "commands.jsonl")
    else:
        write_text(out / "logs" / "commands.jsonl", json.dumps({"PENDING": "commands.jsonl missing"}, ensure_ascii=False) + "\n")
    b3_matrix = evidence_root / "evidence" / "evidence-matrix-b3.csv"
    if matrix_path.exists():
        shutil.copyfile(matrix_path, out / "evidence-matrix.csv")
    elif b3_matrix.exists():
        shutil.copyfile(b3_matrix, out / "evidence-matrix.csv")
    else:
        write_text(out / "evidence-matrix.csv", "case_id,status\nPENDING,<<PENDING B3 PHASE2>>\n")
    if b3_matrix.exists() and matrix_path != b3_matrix:
        shutil.copyfile(b3_matrix, out / "evidence-matrix-b3.csv")
    env_count = copy_tree_files(evidence_root / "env", out / "env")
    if not env_count:
        write_text(out / "env" / "evidence-identity.json", json.dumps({"PENDING": PENDING}, indent=2) + "\n")

    rootfs_sha, rootfs_files, rootfs_size = normalized_tar_sha256(rootfs_dir)
    deps_sha, deps_files, deps_size = normalized_tar_sha256(deps_dir)
    stage_sha, stage_files, stage_size = normalized_tar_sha256(stage_dir)
    runtime_binary = deps_dir / "deepseek_harness_runtime/runtime/deepseek-harness-sdk-runtime-linux-x64"
    node_binary = rootfs_dir / "usr/bin/node"
    python_binary = rootfs_dir / "opt/python/bin/python3.11"
    runtime_hashes = {
        "dsh_runtime_binary": {"path": str(runtime_binary), "sha256": sha256_file(runtime_binary)} if runtime_binary.exists() else {"path": str(runtime_binary), "sha256": PENDING},
        "node_binary": {"path": str(node_binary), "sha256": sha256_file(node_binary)} if node_binary.exists() else {"path": str(node_binary), "sha256": PENDING},
        "python_binary": {"path": str(python_binary), "sha256": sha256_file(python_binary)} if python_binary.exists() else {"path": str(python_binary), "sha256": PENDING},
        "runtime_version": args.runtime_version,
        "sdk_version": args.sdk_version,
        "node_version": args.node_version,
        "python_version": args.python_version,
    }
    write_text(out / "env" / "runtime-hashes.txt", json.dumps(runtime_hashes, indent=2, sort_keys=True))
    write_text(out / "env" / "code-tree.txt", "\n".join([
        f"base_sha={base}", f"implementation_sha={impl}", f"docs_sha={docs}",
        "base_tree=" + git_text("rev-parse", f"{base}^{{tree}}").strip(),
        "implementation_tree=" + git_text("rev-parse", f"{impl}^{{tree}}").strip(),
        "ls_tree_sha256=" + sha256_bytes(git_text("ls-tree", "-r", impl).encode("utf-8")),
        "archive_sha256=" + sha256_bytes(run_git("archive", "--format=tar", impl, binary=True)),
        "git_status_worktree_clean=" + ("true" if not git_text("status", "--porcelain").strip() else "false"),
    ]) + "\n")
    write_text(out / "env" / "image-and-deps.txt", json.dumps({
        "rootfs": {"path": str(rootfs_dir), "normalized_tar_sha256": rootfs_sha, "files": rootfs_files, "bytes": rootfs_size},
        "deps": {"path": str(deps_dir), "normalized_tar_sha256": deps_sha, "files": deps_files, "bytes": deps_size},
        "stage": {"path": str(stage_dir), "normalized_tar_sha256": stage_sha, "files": stage_files, "bytes": stage_size},
    }, indent=2, sort_keys=True) + "\n")
    if args.isolation_probe_file:
        shutil.copyfile(args.isolation_probe_file, out / "env" / "isolation-probes.txt")
    else:
        write_text(out / "env" / "isolation-probes.txt", "NOT INCLUDED: B4 must supply raw isolation probes before final packet.\n")
    if args.container_absence_file:
        shutil.copyfile(args.container_absence_file, out / "env" / "container-absence.txt")
    else:
        write_text(out / "env" / "container-absence.txt", "NOT INCLUDED: B4 must supply post-run container/process absence evidence.\n")

    write_text(out / "security-nonclaims.md", build_nonclaims())
    write_text(out / "reviewer-reproduction.md", build_reproduction({"base_sha": base, "implementation_sha": impl}))

    manifest = {
        "schema": "autoteacher/m0-g3b-review-packet/v1",
        "generated_utc": subprocess.check_output(["date", "-u", "+%Y-%m-%dT%H:%M:%SZ"], text=True).strip(),
        "base_sha": base,
        "implementation_sha": impl,
        "docs_sha": docs,
        "runtime_version": args.runtime_version,
        "sdk_version": args.sdk_version,
        "node_version": args.node_version,
        "python_version": args.python_version,
        "image_or_rootfs_sha": rootfs_sha,
        "deps_sha": deps_sha,
        "stage_sha": stage_sha,
        "tests_executed": tests_executed,
        "blocked_cases": blocked_cases,
        "status_notes": status_notes,
        "real_model_calls": 0,
        "external_http_calls": 0,
        "key_present": False,
        "evidence_root": {"path": str(evidence_root.relative_to(ROOT)) if evidence_root.is_relative_to(ROOT) else str(evidence_root),
                          "snapshot_tree_sha256": evidence_before, "snapshot_file_count": evidence_files_before},
        "source_files": source_count,
        "test_files": test_count,
        "evidence_matrix_path": str(matrix_path.relative_to(ROOT)) if matrix_path.is_relative_to(ROOT) else str(matrix_path),
        "identity_source": str(identity_path.relative_to(ROOT)) if identity_path.is_relative_to(ROOT) else str(identity_path),
        "deleted_paths": deleted_paths,
        "diff_sha256": diff_sha,
        "diff_bytes": len(diff_bytes),
        "packet": {"hashes_file": "hashes.sha256", "integrity_report": "packet-integrity-report.txt", "tar": None},
        "notes": (
            ["Draft/dry-run fields may contain <<PENDING B3 PHASE2>> until B3 final freeze."]
            if (tests_executed == [PENDING] or blocked_cases == [PENDING])
            else ["Final B4 packet; do not infer PASS from this packet; Reviewer verdict is separate."]
        ),
    }
    manifest_path = out / "manifest.json"
    write_text(manifest_path, json.dumps(manifest, indent=2, sort_keys=True))
    write_text(out / "README.md", build_readme(manifest))

    all_packet_files = sorted(p for p in out.rglob("*") if p.is_file())
    hash_lines: list[str] = []
    for item in all_packet_files:
        relative = item.relative_to(out).as_posix()
        if relative in {"hashes.sha256", "packet-integrity-report.txt"}:
            continue
        hash_lines.append(f"{sha256_file(item)}  {relative}")
    write_text(out / "hashes.sha256", "\n".join(hash_lines))

    # Integrity checks (exclude self references).
    failures: list[str] = []
    warnings: list[str] = []
    if sha256_file(out / "diff.patch") != diff_sha:
        failures.append("diff.patch hash differs from manifest.diff_sha256")
    if sha256_bytes(run_git("diff", "--binary", base, impl, binary=True)) != diff_sha:
        failures.append("diff.patch is not byte-identical to git diff --binary base..impl")
    source_failures = []
    for row in source_rows:
        target = out / "source" / row["path"]
        if not target.exists() or sha256_file(target) != row["sha256"]:
            source_failures.append(row["path"])
        elif sha256_bytes(git_show(impl, row["path"])) != sha256_file(target):
            source_failures.append(row["path"])
    if source_failures:
        failures.append("source blob mismatch: " + ", ".join(source_failures))
    test_failures = []
    for row in test_rows:
        target = out / "tests" / row["path"]
        if not target.exists() or sha256_file(target) != row["sha256"]:
            test_failures.append(row["path"])
        elif sha256_bytes(git_show(impl, row["path"])) != sha256_file(target):
            test_failures.append(row["path"])
    if test_failures:
        failures.append("test blob mismatch: " + ", ".join(test_failures))
    hash_failures = []
    for line in (out / "hashes.sha256").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, relative = line.split("  ", 1)
        target = out / relative
        if not target.exists() or sha256_file(target) != digest:
            hash_failures.append(relative)
    if hash_failures:
        failures.append("hashes.sha256 entries failed: " + ", ".join(hash_failures))
    sensitive = sensitive_findings(out)
    if sensitive:
        failures.append("sensitive pattern scan: " + "; ".join(sensitive))
    diff_check = subprocess.run(["git", "diff", "--check", base, impl], cwd=ROOT, capture_output=True, text=True)
    if diff_check.returncode != 0:
        failures.append("git diff --check base..impl reported whitespace errors")
    evidence_after, evidence_files_after = evidence_tree_hash(evidence_root)
    if evidence_before != evidence_after or evidence_files_before != evidence_files_after:
        warnings.append(f"evidence root changed during packet build: before={evidence_before}/{evidence_files_before} after={evidence_after}/{evidence_files_after}")
    if not identity_path.exists():
        identity_path = evidence_root / "env" / "identity.json"
    if identity_path.exists():
        identity = json.loads(identity_path.read_text(encoding="utf-8"))
        if identity.get("deps_sha256") != deps_sha:
            warnings.append(f"evidence identity deps_sha256={identity.get('deps_sha256')} differs from canonical deps_sha={deps_sha}")
        if identity.get("rootfs_sha256") not in (None, rootfs_sha):
            warnings.append(f"evidence identity rootfs_sha256={identity.get('rootfs_sha256')} differs from canonical={rootfs_sha}")
        if identity.get("head") not in (None, impl):
            warnings.append(f"evidence identity head={identity.get('head')} differs from implementation_sha={impl}")
    matrix_rows = 0
    if (out / "evidence-matrix.csv").exists():
        matrix_rows = max(0, len((out / "evidence-matrix.csv").read_text(encoding="utf-8").splitlines()) - 1)
    if tests_executed == [PENDING] or blocked_cases == [PENDING]:
        warnings.append("tests_executed/blocked_cases contain <<PENDING B3 PHASE2>> placeholders (dry-run only)")
    if args.isolation_probe_file is None:
        warnings.append("env/isolation-probes.txt is a placeholder")
    if args.container_absence_file is None:
        warnings.append("env/container-absence.txt is a placeholder")
    pending_lines = []
    if tests_executed == [PENDING] or blocked_cases == [PENDING]:
        pending_lines.append("- Fill tests_executed/blocked_cases from B3 final matrix input.")
    if args.isolation_probe_file is None:
        pending_lines.append("- Provide raw isolation probes.")
    if args.container_absence_file is None:
        pending_lines.append("- Provide container-absence evidence.")
    if not pending_lines:
        pending_lines.append("- None: final inputs supplied.")
    report_lines = [
        "# Packet Integrity Report (generated, no self-reference)",
        f"generated_utc={subprocess.check_output(['date', '-u', '+%Y-%m-%dT%H:%M:%SZ'], text=True).strip()}",
        f"base_sha={base}",
        f"implementation_sha={impl}",
        f"docs_sha={docs}",
        f"diff_sha256={diff_sha} (recomputed twice; match={'yes' if not any('diff.patch' in f for f in failures) else 'no'})",
        f"source_files={source_count} (blob_compare_OK={'yes' if not source_failures else 'no'})",
        f"test_files={test_count} (blob_compare_OK={'yes' if not test_failures else 'no'})",
        f"hash_lines={len(hash_lines)} (verify_failures={len(hash_failures)})",
        f"sensitive_findings={len(sensitive)}",
        f"git_diff_check_exit={diff_check.returncode}",
        f"evidence_matrix_rows={matrix_rows}",
        f"implementation_sha={impl} (source/tests blobs verified against Git)",
        f"tar_generated=false",
        f"excluded_self_reference=hashes.sha256,packet-integrity-report.txt",
        f"overall={'SELF_CHECK_PASS' if not failures else 'SELF_CHECK_FAIL_WITH_PENDING' if warnings else 'SELF_CHECK_FAIL'}",
        "",
        "## Warnings",
        *(f"- {w}" for w in warnings),
        "",
        "## Failures",
        *(f"- {f}" for f in failures),
        "",
        "## Pending before final B4",
        *pending_lines,
    ]
    write_text(out / "packet-integrity-report.txt", "\n".join(report_lines))
    summary = {
        "out": str(out.relative_to(ROOT) if out.is_relative_to(ROOT) else out),
        "base_sha": base,
        "implementation_sha": impl,
        "docs_sha": docs,
        "diff_sha256": diff_sha,
        "source_files": source_count,
        "test_files": test_count,
        "evidence_matrix_path": str(matrix_path.relative_to(ROOT)) if matrix_path.is_relative_to(ROOT) else str(matrix_path),
        "identity_source": str(identity_path.relative_to(ROOT)) if identity_path.is_relative_to(ROOT) else str(identity_path),
        "hash_lines": len(hash_lines),
        "matrix_rows": matrix_rows,
        "warnings": warnings,
        "failures": failures,
        "integrity_report": str((out / "packet-integrity-report.txt").relative_to(ROOT)),
        "manifest_sha256": sha256_file(manifest_path),
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
