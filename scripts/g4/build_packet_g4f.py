#!/usr/bin/env python3
"""Build the G4-F no-key review packet (host-side, read-only imports).

Usage:
  PYTHONDONTWRITEBYTECODE=1 /root/.local/bin/python3.11 -B \
    scripts/g4/build_packet_g4f.py --docs-sha <docs commit> \
    [--impl-sha e7d9296...] [--out DIR] [--force] [--allow-dirty]

The builder never starts a container, never uses the network, never reads a
credential, never opens a SQLite database in place (copies are byte copies) and
never modifies repository files.  It writes only inside
``artifacts/review-packet-g4f-<impl_sha>/``.

Provenance:

* base      = bb2e914 (G4-E closeout)
* impl      = e7d9296 (final G4-F evidence HEAD; F1-F5 + F6 compatibility fix)
* code      = dbacb76 (last commit touching ``src/``)
* docs      = --docs-sha (the closeout docs/matrix commit)
* build_sha = HEAD at packet build (docs + packet-builder commits)

All text payload is path-sanitized (workspace -> ``<WORKSPACE>``, host python ->
``<HOST_PYTHON>``, bare ``/root`` -> ``<HOST_HOME>``).  ``hashes.sha256`` covers
every payload file plus ``manifest.json``; it does not cover itself or the
integrity report.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "artifacts"
DOCS = ROOT / "docs"
F6 = ARTIFACTS / "g4f" / "f6"
I = F6 / "integration"

BASE_SHA = "bb2e9142a4e96e2b8fbe65bb99f1b4c045260251"
IMPL_SHA = "e7d92967ec0ece80de4a1a3705f637e8eb9bde99"
CODE_SHA = "dbacb76f98a1a91559ff70e02bf544ace76ed7b5"
STAGE_PATH = "artifacts/g4/c/stages/stage-20261119T142828Z"
STAGE_MANIFEST = "82e10c6ffe37e401a58730e9abcaa691f19d6702a7276c03df625d5b4636e501"
STAGE_TREE = "7d32ec1d8b02726ba52ef8303e8677b46384e9954559e838b31bb8c58f222068"
ROOTFS_CANON = "25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0"
DEPS_CANON = "e07729d7997944417b1c25531749b3e6e5e34aa4248f01dc8f370282082ecb98"
DSH_RUNTIME = "1cc41d5a8745a5b9d47c8604e44f23eb8af2d8ca02b2afa0be101d5f71be6ea4"
NODE_VERSION = "v22.23.2"
ADAPTER_JS = "2cb424616b7380bff61f8ce760e229a0c1d2b32c4a5f2954cdf66c3937bf74ba"
MATRIX = DOCS / "Autonomous_Teacher_M0_G4F_Closeout_Test_Evidence_Matrix_v1.0.csv"
PACKET_REPORT = "packet-integrity-report.txt"
HASHES = "hashes.sha256"
MANIFEST = "manifest.json"

SOURCE_PATHS: list[str] = []
for pattern_dir in ("src/autoteacher_m0", "scripts/g4", "tests/integration/g4_f2",
                    "tests/integration/g4_f3", "tests/integration/g4_f5",
                    "tests/security", "config/g4"):
    for path in sorted((ROOT / pattern_dir).rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        if path.suffix in (".pyc", ".pyo"):
            continue
        relative = path.relative_to(ROOT).as_posix()
        if relative == "scripts/g4/build_packet_g4f.py":
            continue
        SOURCE_PATHS.append(relative)
SOURCE_PATHS += ["scripts/security/scan_git_secrets.py", "scripts/run_live.sh",
                 "AGENTS.md", "SECURITY.md", "docs/SECURITY_APPROVALS.md"]

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

TEXT_SUFFIXES = {".py", ".json", ".jsonl", ".md", ".txt", ".csv", ".log", ".xml",
                 ".mjs", ".js", ".sh", ".yml", ".yaml", ".toml", ".cfg", ".ini"}


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
    proc = subprocess.run(["git", *args], cwd=str(ROOT), capture_output=True)
    if proc.returncode != 0:
        raise BuildError(f"git {' '.join(args)} failed: "
                         f"{proc.stderr.decode('utf-8', 'replace')[:800]}")
    return proc.stdout if binary else proc.stdout.decode("utf-8", "replace")


def sanitize_text(text: str) -> str:
    escaped_root = str(ROOT).replace(" ", "\\040")
    replacements = [
        (str(ROOT), "<WORKSPACE>"),
        (escaped_root, "<WORKSPACE_ESCAPED>"),
        ("/root/.local/share/uv/python/cpython-3.11-linux-x86_64-gnu", "<UV_PYTHON>"),
        ("/root/.local/share/uv/python/cpython-3.11.15-linux-x86_64-gnu", "<UV_PYTHON>"),
        ("/root/.local/bin/python3.11", "<HOST_PYTHON>"),
        ("/root/.local/bin", "<HOST_BIN>"),
        ("/root/.local/share", "<HOST_SHARE>"),
        ("/root/.cache", "<HOST_CACHE>"),
        ("/root/.dsh", "<HOST_HOME>/.dsh"),
        ("/root/.config", "<HOST_HOME>/.config"),
        ("/opt/miniconda3/envs/quant/bin/python", "<CONDA_PYTHON>"),
        ("/root", "<HOST_HOME>"),
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


def copy_text(source: Path, target: Path) -> None:
    write_text(target, sanitize_text(source.read_text(encoding="utf-8",
                                                      errors="replace")))


def copy_json(source: Path, target: Path) -> None:
    write_json(target, json.loads(source.read_text(encoding="utf-8")))


def copy_bytes(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    os.chmod(target, 0o444)


def require_file(path: Path, label: str = "") -> Path:
    if not path.is_file():
        raise BuildError(f"missing input {label or path}: {path}")
    return path


def read_json(path: Path) -> dict:
    require_file(path)
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# build steps
# ---------------------------------------------------------------------------
def validate(args: argparse.Namespace) -> dict:
    if args.impl_sha != IMPL_SHA:
        raise BuildError("impl sha differs from the frozen G4-F evidence HEAD")
    docs_sha = git("rev-parse", f"{args.docs_sha}^{{commit}}").strip()
    for sha in (BASE_SHA, IMPL_SHA, CODE_SHA):
        git("cat-file", "-e", f"{sha}^{{commit}}")
    git("merge-base", "--is-ancestor", IMPL_SHA, docs_sha)
    diff = git("diff", "--name-only", IMPL_SHA, docs_sha).splitlines()
    disallowed = [line for line in diff
                  if not line.startswith("docs/")
                  and line != "scripts/g4/build_packet_g4f.py"]
    if disallowed:
        raise BuildError(f"commits after impl change non-docs paths: {disallowed[:10]}")
    if git("diff", IMPL_SHA, docs_sha, "--", "src"):
        raise BuildError("src changed after impl sha")
    last_docs = git("log", "-1", "--format=%H", "--", "docs").strip()
    if last_docs != docs_sha:
        raise BuildError(f"docs_sha is not the last docs commit: {last_docs}")
    status = [line for line in git("status", "--porcelain=v1", "-uall").splitlines()
              if line.strip()]
    if status and not args.allow_dirty:
        raise BuildError(f"worktree not clean: {status[:10]}")
    stage = ROOT / STAGE_PATH
    manifest = read_json(stage / "manifest.json")
    summary = read_json(stage / "stage-summary.json")
    if manifest.get("head_at_build") != IMPL_SHA:
        raise BuildError("stage base is not the impl sha")
    if summary.get("manifest_sha256") != STAGE_MANIFEST:
        raise BuildError("stage manifest sha mismatch")
    if summary.get("rootfs_sha256") != ROOTFS_CANON or summary.get("deps_sha256") != DEPS_CANON:
        raise BuildError("rootfs/deps not canonical in stage summary")
    loaded = read_json(I / "f4-resume" / "loaded-modules.json")
    if not (loaded.get("all_from_project_src") and loaded.get("all_match_head")
            and loaded.get("all_match_stage")):
        raise BuildError("loaded module identity failed")
    return {"docs_sha": docs_sha, "stage_manifest": manifest, "stage_summary": summary,
            "loaded": loaded, "build_sha": git("rev-parse", "HEAD").strip(),
            "worktree_clean": not status}


def build_changes(out: Path, docs_sha: str) -> None:
    dst = out / "changes"
    write_text(dst / "implementation.diff", sanitize_text(git(
        "diff", "--binary", BASE_SHA, IMPL_SHA, "--", "src", "scripts/g4",
        "scripts/security", "config/g4", "tests/integration/g4_f2",
        "tests/integration/g4_f3", "tests/integration/g4_f5",
        "tests/security")))
    write_text(dst / "docs.diff", sanitize_text(git(
        "diff", "--binary", BASE_SHA, docs_sha, "--", "docs")))
    lines = ["# Protected-file audit (base -> impl)", ""]
    for relative in PROTECTED_PATHS:
        proc = subprocess.run(["git", "diff", "--quiet", BASE_SHA, IMPL_SHA,
                               "--", relative], cwd=str(ROOT))
        unchanged = proc.returncode == 0
        blob = (hashlib.sha256(git("show", f"{IMPL_SHA}:{relative}",
                                   binary=True)).hexdigest()
                if unchanged else "n/a")
        lines.append(f"{'UNCHANGED' if unchanged else 'CHANGED':9s} {relative}  "
                     f"blob={blob}")
    lines += ["", "## Source blobs (impl HEAD)", ""]
    for relative in SOURCE_PATHS:
        working = sha256_file(ROOT / relative)
        blob = hashlib.sha256(git("show", f"{IMPL_SHA}:{relative}",
                                  binary=True)).hexdigest()
        state = "MATCH" if working == blob else "MISMATCH"
        lines.append(f"{state:8s} {relative}  sha256={working}")
    write_text(dst / "protected-files-diff.txt", "\n".join(lines) + "\n")


def build_source(out: Path) -> None:
    index = ["# G4-F source index (impl HEAD)", ""]
    manifest_rows = []
    for relative in SOURCE_PATHS:
        source = require_file(ROOT / relative, "source")
        target = out / "source" / relative
        raw = source.read_bytes()
        if source.suffix.lower() in TEXT_SUFFIXES or relative.endswith(".sh"):
            write_text(target, sanitize_text(raw.decode("utf-8", "replace")))
        else:
            copy_bytes(source, target)
        blob = hashlib.sha256(git("show", f"{IMPL_SHA}:{relative}",
                                  binary=True)).hexdigest()
        manifest_rows.append({"path": relative, "bytes": len(raw),
                              "sha256": sha256_bytes(raw),
                              "impl_blob_sha256": blob,
                              "matches_impl_blob": sha256_bytes(raw) == blob})
        index.append(f"- `{relative}` sha256 `{sha256_bytes(raw)}`")
    write_json(out / "source" / "manifest.json", {
        "schema": "m0.g4f6.source-manifest.v1",
        "impl_sha": IMPL_SHA, "count": len(manifest_rows),
        "all_match_impl_blob": all(row["matches_impl_blob"] for row in manifest_rows),
        "files": manifest_rows})
    builder = ROOT / "scripts" / "g4" / "build_packet_g4f.py"
    builder_copy = out / "source" / "scripts" / "g4" / "build_packet_g4f.py"
    copy_text(builder, builder_copy)
    index.append(f"- packet builder original sha256 `{sha256_file(builder)}`; "
                 f"packet copy is path-sanitized")
    write_text(out / "source" / "INDEX.md", "\n".join(index) + "\n")


def build_env(out: Path, identity: argparse.Namespace, docs_sha: str) -> None:
    env = out / "env"
    stage_summary = identity["stage_summary"]
    write_json(env / "identity.json", {
        "schema": "m0.g4f6.identity.v1",
        "created_utc": utc_now(),
        "base_sha": BASE_SHA,
        "impl_sha": IMPL_SHA,
        "code_sha": CODE_SHA,
        "docs_sha": docs_sha,
        "build_sha": identity["build_sha"],
        "head_at_packet": git("rev-parse", "HEAD").strip(),
        "worktree_clean": identity["worktree_clean"],
        "impl_subject": git("show", "-s", "--format=%s", IMPL_SHA).strip(),
        "docs_subject": git("show", "-s", "--format=%s", docs_sha).strip(),
        "code_subject": git("show", "-s", "--format=%s", CODE_SHA).strip(),
        "chain": git("log", "--format=%H %s", f"{BASE_SHA}..{IMPL_SHA}").splitlines(),
    })
    write_json(env / "canonical.json", {
        "schema": "m0.g4f6.canonical.v1",
        "rootfs_sha256": ROOTFS_CANON,
        "deps_sha256": DEPS_CANON,
        "dsh_runtime_sha256": DSH_RUNTIME,
        "dsh_sdk_version": "0.2.2rc2",
        "node_version": NODE_VERSION,
        "adapter_built_js_sha256": ADAPTER_JS,
        "stage_path": STAGE_PATH,
        "stage_manifest_sha256": STAGE_MANIFEST,
        "stage_tree_sha256": STAGE_TREE,
        "stage_base_sha": stage_summary.get("base_sha"),
        "stage_trusted_tree_sha256": stage_summary.get("trusted_tree_sha256"),
        "stage_candidate_tree_sha256": stage_summary.get("candidate_tree_sha256"),
        "synthetic": True,
    })
    copy_json(ROOT / STAGE_PATH / "manifest.json", env / "stage-manifest.json")
    copy_json(ROOT / STAGE_PATH / "stage-summary.json", env / "stage-summary.json")
    copy_json(I / "f4-resume" / "loaded-modules.json", env / "loaded-modules.json")
    livegate = read_json(I / "livegate" / "livegate.json")
    write_json(env / "zero-key.json", {
        "schema": "m0.g4f6.zero-key.v1",
        "provider_route_kind": "synthetic_only",
        "synthetic_route": "offline-test-only-g3b/fixture-bridge-v1",
        "real_route": "BLOCKED_REQUIRES_HUMAN_VERIFICATION",
        "real_model_calls": 0,
        "real_external_http_calls": 0,
        "provider_keys_seen": 0,
        "key_present": False,
        "billable_send_allowed": 0,
        "live_gate": "BLOCKED",
        "run_live_exit": livegate.get("run_live_sh", {}).get("exit"),
        "live_gate_reasons": livegate.get("gate_all_evidence", {}).get("reasons"),
        "external_socket_attempts": livegate.get("external_socket_attempts"),
        "key_like_env_names": livegate.get("key_like_env_names"),
        "podman_pull": 0,
        "containers_after": [],
    })


def build_f1(out: Path) -> None:
    dst = out / "f1"
    summary = read_json(I / "SUMMARY.json")
    write_json(dst / "scanner-audits.json", {
        "schema": "m0.g4f6.scanner-audits.v1",
        "final_head_scan": summary.get("scanner"),
        "archived_f1": {
            "report": "docs/M0_G4F_F1_REPORT.md",
            "full_history_json": "artifacts/g4f/f1/full-history-scan.json",
            "latest_commits_audit": "artifacts/g4f/f1/latest-commits-audit.json",
            "history_audit": "artifacts/g4f/f1/history-audit.json",
            "selftest": "artifacts/g4f/f1/selftest.txt",
        },
    })
    for name in ("selftest.log", "history.log", "nohistory.log",
                 "pytest-security.log"):
        copy_text(I / "scanner" / name, dst / "logs" / name)
    for name in ("selftest.txt", "full-history-scan.json", "history-audit.json",
                 "latest-commits-audit.json"):
        source = ARTIFACTS / "g4f" / "f1" / name
        if source.is_file():
            copy_text(source, dst / "archived" / name)


def build_f2(out: Path) -> None:
    dst = out / "f2"
    summary = read_json(I / "f2" / "summary.json")
    write_json(dst / "summary.json", summary)
    for case in ("echo", "tool"):
        candidates = sorted((I / "f2" / "runs").glob(f"{case}-*"))
        dirs = [path for path in candidates if path.is_dir()]
        if not dirs:
            continue
        evidence = dirs[-1]
        copy_bytes(evidence / "run" / "dispatch-window.jsonl",
                   dst / f"dispatch-window-{case}.jsonl")
        copy_json(evidence / "db" / "snapshot.json",
                  dst / f"db-snapshot-{case}.json")
    raw = summary.get("raw_uds") or {}
    write_json(dst / "raw-matrix.json", raw)
    tool_window = I / "f2" / "tool-window.json"
    if tool_window.is_file():
        copy_json(tool_window, dst / "tool-window.json")
    write_json(dst / "auxiliary.json", summary.get("auxiliary"))


def build_f3(out: Path) -> None:
    dst = out / "f3"
    copy_json(I / "f3-host" / "cases.json", dst / "host-cases.json")
    l2 = read_json(I / "f3-l2" / "summary.json")
    cases = []
    for key, record in (l2.get("cases") or {}).items():
        evidence = Path(record.get("evidence") or "")
        snapshot = (read_json(evidence / "db" / "snapshot.json")
                    if evidence.is_dir() else {})
        egress = {}
        for name in ("g4c-egress.json", "g4c-egress-before-restart.json",
                     "g4c-egress-recovery.json"):
            path = evidence / "run" / name
            if path.is_file():
                document = read_json(path)
                egress[name] = {key2: document.get(key2) for key2 in
                                ("known_cost_usd", "worst_case_held_usd",
                                 "sends_authorized", "consumed")}
        cases.append({"case": key, "ok": record.get("ok"),
                      "exit": record.get("exit_code"),
                      "checks": record.get("checks_total"),
                      "failed": record.get("checks_failed"),
                      "argv": record.get("argv"),
                      "reservations": [{k: row.get(k) for k in
                                        ("status", "cost", "reservation_id")}
                                       for row in snapshot.get("reservations") or []],
                      "attempts": [{k: row.get(k) for k in
                                    ("state", "reason", "attempt_id")}
                                   for row in snapshot.get("attempts") or []],
                      "fake_counter": snapshot.get("fake_counter"),
                      "egress": egress})
    write_json(dst / "l2-matrix.json", {
        "schema": "m0.g4f6.f3-l2.v1", "utc": [l2.get("utc_start"), l2.get("utc_end")],
        "cases": cases, "containers_after": l2.get("containers_after"),
        "rootfs_canonical": l2.get("rootfs_canonical"),
        "deps_canonical": l2.get("deps_canonical")})
    for key, name in (("crash-before-send", "crash-before-send"),
                      ("c01", "c01")):
        source = next((p for p in (I / "f3-l2" / "runs").glob(f"{key}-*")), None)
        if source is None:
            continue
        for file in ("broker.sqlite3", "attempts.sqlite3"):
            path = source / "db" / file
            if path.is_file():
                copy_bytes(path, dst / "sqlite-readonly" / f"{name}-{file}")


def build_f4(out: Path) -> None:
    dst = out / "f4"
    summary = read_json(I / "f4-resume" / "summary.json")
    write_json(dst / "summary.json", summary)
    copy_json(I / "f4-resume" / "audit.json", dst / "audit.json")
    for phase in ("resume", "crash-resume"):
        evidence = Path(((summary.get("phases") or {}).get(phase) or {}).get(
            "evidence") or "")
        if not evidence.is_dir():
            continue
        per_request = evidence / "per-request.json"
        if per_request.is_file():
            copy_json(per_request, dst / f"per-request-{phase}.json")
        for file in ("broker.sqlite3", "attempts.sqlite3"):
            path = evidence / "db" / file
            if path.is_file():
                copy_bytes(path, dst / "sqlite-readonly" / f"{phase}-{file}")
        session = evidence / "phases" / "turn2" / "session.json"
        if session.is_file():
            document = read_json(session)
            write_json(dst / f"session-metadata-{phase}.json", document)
    copy_json(I / "f4-resume" / "loaded-modules.json", dst / "loaded-modules.json")


def build_f5(out: Path) -> None:
    dst = out / "f5"
    matrix = read_json(I / "f5" / "matrix.json")
    write_json(dst / "matrix.json", matrix)
    for case in ("revocation-post-reserve", "timeout-post-send",
                 "crash-before-send"):
        source = next((p for p in (I / "f5" / "runs").glob(f"{case}-*")), None)
        if source is None:
            continue
        for file in ("broker.sqlite3", "attempts.sqlite3"):
            path = source / "db" / file
            if path.is_file():
                copy_bytes(path, dst / "sqlite-readonly" / f"{case}-{file}")


def junit_summary(path: Path) -> dict:
    import xml.etree.ElementTree as ET
    root = ET.parse(path).getroot()
    tests = failures = errors = skipped = 0
    failing = []
    for suite in root.iter("testsuite"):
        tests += int(suite.get("tests", 0))
        failures += int(suite.get("failures", 0))
        errors += int(suite.get("errors", 0))
        skipped += int(suite.get("skipped", 0))
    for testcase in root.iter("testcase"):
        if testcase.find("failure") is not None or testcase.find("error") is not None:
            failing.append(f"{testcase.get('classname')}::{testcase.get('name')}")
    return {"collected": tests, "passed": tests - failures - errors - skipped,
            "failed": failures + errors, "skipped": skipped, "failing": failing}


def build_regressions(out: Path) -> None:
    dst = out / "regressions"
    for name in ("full-pytest.log", "junit-host-full.xml"):
        copy_text(I / "host" / name, dst / "host" / name)
    write_json(dst / "host" / "junit-summary.json",
               junit_summary(I / "host" / "junit-host-full.xml"))
    for name in ("oci-raw.log", "oci-filtered.log",
                 "oci-root-replay-filtered.log", "oci-env-deselects.json",
                 "junit-oci-filtered.xml", "junit-oci-root-filtered.xml"):
        copy_text(I / "oci" / name, dst / "oci" / name)
    for name in ("adapter.log", "guard.log", "skill.log"):
        copy_text(I / "node" / name, dst / "node" / name)
    for name in ("scoped-parity.log", "repo.log", "scoped.log"):
        copy_text(I / "ruff" / name, dst / "ruff" / name)
    command_rows = [json.loads(line) for line in
                    (I / "commands.jsonl").read_text(encoding="utf-8").splitlines()
                    if line.strip()]
    write_json(dst / "commands.json", command_rows)


def build_review(out: Path) -> None:
    dst = out / "review"
    for name in ("M0_G4F_REVIEW_REQUEST.md", "M0_G4F_FINDINGS_AND_DISPOSITION.md",
                 "M0_G4F_HUMAN_HANDOFF.md", "M0_G4F_IMPLEMENTATION_REPORT.md"):
        copy_text(DOCS / name, dst / name)
    copy_json(I / "livegate" / "livegate.json", dst / "livegate.json")
    write_text(dst / "REPRODUCE.md", sanitize_text("""# Reproduce G4-F6 evidence

All commands are run from the workspace root with `PYTHONDONTWRITEBYTECODE=1`
and never use a Key, a real model or the external network.

## Environment

```text
rootfs 25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0
deps   e07729d7997944417b1c25531749b3e6e5e34aa4248f01dc8f370282082ecb98
stage  artifacts/g4/c/stages/stage-20261119T142828Z (manifest 82e10c6f...)
```

## Build the frozen stage (requires clean worktree, host root)

```text
python3 -B scripts/g4/build_stage_c.py
```

## Real dual-principal evidence

```text
python3 -B scripts/g4/run_g4_f4.py --stage artifacts/g4/c/stages/stage-20261119T142828Z --out-dir <dir>/f4
python3 -B tests/integration/g4_f2/run_f2_evidence.py --stage artifacts/g4/c/stages/stage-20261119T142828Z --out-dir <dir>/f2
python3 -B scripts/g4/run_g4_c.py --stage artifacts/g4/c/stages/stage-20261119T142828Z --out-dir <dir>/f3 --only c01,c02,replay,crash-before-send,crash-after-receive,quota,broker-down
python3 -B scripts/g4/run_g4_f5.py --stage artifacts/g4/c/stages/stage-20261119T142828Z --out-dir <dir>/f5
```

## Host / OCI / Node / static

```text
env PYTHONPATH=src:artifacts/foundation/deps /root/.local/bin/python3.11 -B -m pytest tests -q
podman run ... (see env/canonical.json; 43 explicit --deselect args in regressions/oci/oci-env-deselects.json)
node --test-reporter=tap --test <adapter/guard/skill tests>
artifacts/foundation/deps/bin/ruff check --no-cache <scoped>
/root/.local/bin/python3.11 -B scripts/security/scan_git_secrets.py
```

After any OCI run, remove the engine-created `rootfs/var` and mount-point
directories and re-check the canonical rootfs hash.  `podman ps -a` must be
empty.
"""))
    write_text(dst / "NO-KEY-DECLARATION.md", sanitize_text("""# No-key declaration

- 0 real provider keys read, injected or printed.
- 0 real model calls; all provider traffic is the synthetic Fake.
- 0 external HTTP/TCP; containers run with `--network none`; the LiveGate probe
  guards AF_INET sockets and records `external_socket_attempts=[]`.
- 0 `podman pull`.
- LiveGate = BLOCKED; G4-H = NOT_AUTHORIZED; G5 = BLOCKED; G6 = NOT_RUN;
  M0 = DECISION_PENDING; E5_PRELIVE_FULL = BLOCKED_PENDING_HUMAN_DEPLOYMENT.
"""))


def build_matrix(out: Path) -> dict:
    import csv
    rows = list(csv.DictReader(MATRIX.open(encoding="utf-8")))
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    target = out / "matrix" / MATRIX.name
    target.parent.mkdir(parents=True, exist_ok=True)
    copy_text(MATRIX, target)
    return {"rows": len(rows), "counts": counts, "path": str(target.relative_to(out))}


def payload_files(out: Path) -> list[Path]:
    files = []
    for root, dirs, names in os.walk(out):
        dirs.sort()
        for name in sorted(names):
            path = Path(root) / name
            relative = path.relative_to(out).as_posix()
            if relative in (HASHES, PACKET_REPORT):
                continue
            files.append(path)
    return sorted(files)


def verify_packet(out: Path) -> dict:
    payload = payload_files(out)
    symlinks = []
    sensitive_hits = []
    host_paths = []
    for path in payload:
        if path.is_symlink():
            symlinks.append(str(path.relative_to(out)))
        if path.suffix.lower() in TEXT_SUFFIXES or path.name in ("Dockerfile",):
            text = path.read_text(encoding="utf-8", errors="replace")
            relative = path.relative_to(out).as_posix()
            for pattern in SENSITIVE:
                for match in pattern.finditer(text):
                    value = match.group(0)
                    sensitive_hits.append({"path": relative,
                                           "pattern": pattern.pattern[:40],
                                           "masked": value[:6] + "..."})
            if re.search(r"/root(?:/|$)", text) and "REPRODUCE.md" not in relative:
                host_paths.append(relative)
    manifest = json.loads((out / MANIFEST).read_text(encoding="utf-8"))
    hashes = []
    for line in (out / HASHES).read_text(encoding="utf-8").splitlines():
        if line.strip():
            digest, relative = line.split("  ", 1)
            hashes.append((digest, relative))
    mismatched = []
    for digest, relative in hashes:
        path = out / relative
        if not path.is_file() or sha256_file(path) != digest:
            mismatched.append(relative)
    tree_lines = []
    payload_tree = []
    for path in payload:
        relative = path.relative_to(out).as_posix()
        if relative == MANIFEST:
            continue
        payload_tree.append(relative)
        tree_lines.append(f"{sha256_file(path)}  {relative}\n")
    tree_hash = sha256_bytes("".join(sorted(tree_lines)).encode("utf-8"))
    report = {
        "uploaded_payload_files": len(payload),
        "payload_files_excluding_manifest": len(payload_tree),
        "manifest_file_count": manifest.get("files", {}).get("count"),
        "hashed_files": len(hashes),
        "mismatched_hashes": mismatched,
        "symlinks": symlinks,
        "sensitive_hits": sensitive_hits,
        "host_home_paths": host_paths,
        "payload_tree_sha256": tree_hash,
        "ok": (not mismatched and not symlinks and not sensitive_hits
               and not host_paths
               and manifest.get("files", {}).get("count") == len(payload_tree)
               and manifest.get("files", {}).get("payload_tree_sha256") == tree_hash),
    }
    return report


def build(args: argparse.Namespace) -> int:
    identity = validate(args)
    out = (Path(args.out) if args.out else
           ARTIFACTS / f"review-packet-g4f-{IMPL_SHA}")
    if out.exists() and any(out.iterdir()):
        if not args.force:
            raise BuildError(f"packet directory not empty: {out}")
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    build_changes(out, identity["docs_sha"])
    build_source(out)
    build_env(out, identity, identity["docs_sha"])
    build_f1(out)
    build_f2(out)
    build_f3(out)
    build_f4(out)
    build_f5(out)
    build_regressions(out)
    build_matrix_summary = build_matrix(out)
    build_review(out)
    summary = read_json(I / "SUMMARY.json")
    loaded = identity["loaded"]
    manifest = {
        "schema_version": "m0.g4f.review-packet.v1",
        "packet": out.name,
        "created_utc": utc_now(),
        "base_sha": BASE_SHA,
        "impl_sha": IMPL_SHA,
        "code_sha": CODE_SHA,
        "docs_sha": identity["docs_sha"],
        "build_sha": identity["build_sha"],
        "head_at_packet": git("rev-parse", "HEAD").strip(),
        "worktree_clean": identity["worktree_clean"],
        "impl_subject": git("show", "-s", "--format=%s", IMPL_SHA).strip(),
        "docs_subject": git("show", "-s", "--format=%s", identity["docs_sha"]).strip(),
        "contract": {
            "schema": "m0.g4f.contract.v1",
            "base": BASE_SHA,
            "impl": IMPL_SHA,
            "code": CODE_SHA,
            "previous_review": {
                "gate": "G4",
                "verdict": "PASS_FOR_G4_NO_KEY_PRELIVE_ENGINEERING_SCOPE",
                "document": "docs/REVIEW_G4_INDEPENDENT.md",
            },
            "reviewer": "NOT_ASSIGNED",
            "reviewer_status": "PENDING_INDEPENDENT_REVIEW",
            "review_enumerations": [
                "PASS_FOR_G4F_NO_KEY_CLOSEOUT_SCOPE",
                "PARTIAL_FOR_G4F_NO_KEY_CLOSEOUT_SCOPE",
                "FAIL_FOR_G4F_NO_KEY_CLOSEOUT_SCOPE",
                "BLOCKED_NEEDS_ENVIRONMENT",
            ],
            "state_constants": {
                "G4-H": "NOT_AUTHORIZED", "G5": "BLOCKED", "G6": "NOT_RUN",
                "LiveGate": "BLOCKED", "M0": "DECISION_PENDING",
                "E5_PRELIVE_FULL": "BLOCKED_PENDING_HUMAN_DEPLOYMENT",
            },
        },
        "stage": {
            "path": STAGE_PATH,
            "base_sha": identity["stage_summary"].get("base_sha"),
            "manifest_sha256": STAGE_MANIFEST,
            "tree_sha256": STAGE_TREE,
            "trusted_tree_sha256": identity["stage_summary"].get("trusted_tree_sha256"),
            "candidate_tree_sha256": identity["stage_summary"].get("candidate_tree_sha256"),
            "trusted_files": 58,
        },
        "rootfs_sha256": ROOTFS_CANON,
        "deps_sha256": DEPS_CANON,
        "runtime_sha": DSH_RUNTIME,
        "runtime_version": "0.2.2-rc.2",
        "node_version": NODE_VERSION,
        "adapter_built_js_sha256": ADAPTER_JS,
        "actual_loaded_modules": loaded.get("modules"),
        "actual_loaded_modules_count": loaded.get("count"),
        "actual_loaded_modules_all_from_project_src": loaded.get("all_from_project_src"),
        "actual_loaded_modules_all_match_head": loaded.get("all_match_head"),
        "actual_loaded_modules_all_match_stage": loaded.get("all_match_stage"),
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
            "F1": "L1-STATIC + L1-HOST",
            "F2": "L2-REAL-DSH + L2-RAW-UDS + L1-HOST",
            "F3": "L1-HOST + L2-REAL-DSH",
            "F4": "L2-REAL-DSH",
            "F5": "L2-REAL-DSH + L2-RAW-UDS",
            "F6": "L1-PACKET + L2 (joint re-run) + L1-HOST + L2-OS",
            "B03/E5-P04": "UNVERIFIED",
            "E5-FULL": "HUMAN-REQUIRED (BLOCKED)",
        },
        "case_statuses": {},
        "matrix": build_matrix_summary,
        "test_stats": {
            "host": summary.get("host"),
            "oci": summary.get("oci"),
            "node": summary.get("node"),
            "scanner": summary.get("scanner"),
            "ruff": summary.get("ruff"),
        },
        "residual_risks": [
            "B03/E5-P04: no authoritative merged tool registry export (UNVERIFIED)",
            "B07: session-title is fallback-only for the frozen config only",
            "F4-R1: context replay is semantic (digest/length), not byte containment",
            "F4-R2: candidate-crash with live Controller sub-case UNVERIFIED",
            "F5-R2: revocation document has no independent signature chain",
            "F5-R6: external SIGKILL windows not enumerated",
            "F3-R1: L2 unknown-cost limited to crash -> PENDING",
            "F6-02: OCI --rootfs creates mount-point dirs; cleaned and re-verified",
            "F6-03: F2/F5 same-batch flake not reproduced in 6 clean batches",
            "F6-06: one pre-existing F841 lint finding in the F1 scanner test",
        ],
        "privacy": {
            "raw_dsh_session_jsonl": "excluded (synthetic prompts only; metadata kept)",
            "real_user_session": False,
            "host_home_paths": "sanitized to <WORKSPACE>/<HOST_PYTHON>/<HOST_HOME>",
        },
        "sqlite": {
            "copies": "read-only byte copies; never opened in place",
            "files": sorted(path.relative_to(out).as_posix()
                            for path in out.rglob("*.sqlite3")),
        },
        "packet_builder": {
            "path": "scripts/g4/build_packet_g4f.py",
            "sha256": sha256_file(ROOT / "scripts/g4/build_packet_g4f.py"),
        },
        "files": {},
    }
    matrix_status = {}
    import csv as _csv
    for row in _csv.DictReader(MATRIX.open(encoding="utf-8")):
        matrix_status[row["case_id"]] = row["status"]
    manifest["case_statuses"] = matrix_status
    write_json(out / MANIFEST, manifest)
    # hashes over payload + manifest
    hashed = []
    for path in payload_files(out):
        hashed.append((sha256_file(path), path.relative_to(out).as_posix()))
    hashed.sort(key=lambda item: item[1])
    write_text(out / HASHES, "".join(f"{digest}  {relative}\n"
                                     for digest, relative in hashed))
    # fill files{} with counts/tree hash, then rewrite manifest and hashes
    payload_tree = []
    tree_lines = []
    for path in payload_files(out):
        relative = path.relative_to(out).as_posix()
        if relative == MANIFEST:
            continue
        payload_tree.append(relative)
        tree_lines.append(f"{sha256_file(path)}  {relative}\n")
    tree_hash = sha256_bytes("".join(sorted(tree_lines)).encode("utf-8"))
    manifest["files"] = {"count": len(payload_tree),
                         "payload_tree_sha256": tree_hash,
                         "hashes_file": HASHES,
                         "integrity_report": PACKET_REPORT}
    write_json(out / MANIFEST, manifest)
    hashed = []
    for path in payload_files(out):
        hashed.append((sha256_file(path), path.relative_to(out).as_posix()))
    hashed.sort(key=lambda item: item[1])
    write_text(out / HASHES, "".join(f"{digest}  {relative}\n"
                                     for digest, relative in hashed))
    report = verify_packet(out)
    lines = [
        "# G4-F review packet integrity report",
        "",
        f"created_utc: {utc_now()}",
        f"packet: {out.name}",
        f"impl_sha: {IMPL_SHA}",
        f"docs_sha: {identity['docs_sha']}",
        f"build_sha: {identity['build_sha']}",
        "",
        f"payload files (excluding manifest/hashes/report): {report['payload_files_excluding_manifest']}",
        f"manifest file count: {report['manifest_file_count']}",
        f"hashed files (payload + manifest): {report['hashed_files']}",
        f"sha256 mismatches: {len(report['mismatched_hashes'])}",
        f"symlinks: {len(report['symlinks'])}",
        f"sensitive pattern hits: {len(report['sensitive_hits'])}",
        f"host home paths: {len(report['host_home_paths'])}",
        f"payload tree sha256: {report['payload_tree_sha256']}",
        "",
        "sha256sum -c: all hashed files were recomputed from disk and match "
        "hashes.sha256." if not report["mismatched_hashes"] else
        "sha256sum -c: MISMATCH",
        "",
        f"result: {'PASS' if report['ok'] else 'FAIL'}",
    ]
    if report["sensitive_hits"]:
        lines += ["", "## Sensitive pattern hits", ""]
        lines += [f"- {hit['path']}: {hit['masked']} ({hit['pattern']})"
                  for hit in report["sensitive_hits"]]
    if report["host_home_paths"]:
        lines += ["", "## Host path files", ""] + [
            f"- {path}" for path in report["host_home_paths"]]
    write_text(out / PACKET_REPORT, "\n".join(lines) + "\n")
    if not report["ok"]:
        raise BuildError(f"packet integrity failed: {json.dumps(report)[:1500]}")
    print(json.dumps({"ok": True, "packet": str(out),
                      "payload_files": report["payload_files_excluding_manifest"],
                      "hashed_files": report["hashed_files"],
                      "payload_tree_sha256": report["payload_tree_sha256"],
                      "sha256_file": sha256_file(out / MANIFEST)}, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docs-sha", required=True)
    parser.add_argument("--impl-sha", default=IMPL_SHA)
    parser.add_argument("--out", default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--allow-dirty", action="store_true")
    args = parser.parse_args(argv)
    try:
        return build(args)
    except BuildError as exc:
        sys.stderr.write(f"PACKET_BUILD_FAILED {exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
