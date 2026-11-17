#!/usr/bin/env python3.11
"""G3-C review packet builder (host-side, read-only; no project imports).

Usage (never write host bytecode):
  PYTHONDONTWRITEBYTECODE=1 /root/.local/bin/python3.11 -B \
    scripts/g3c/build_packet.py --impl-sha e6fde1c --out <packet-dir>

The builder:
  * copies the committed docs and the G3-C evidence tree (copy, never move);
  * writes diff.patch from ``git diff --binary <base>..<impl>``;
  * writes manifest.json, hashes.sha256, packet-integrity-report.txt,
    reproduce/ and security-nonclaims.md;
  * never mutates src/, tests/, spikes/, docs/, artifacts/g3c/ or any existing
    packet; only writes inside the requested output directory;
  * never runs project pytest/Node, never uses a network, never reads keys.

The output directory must live under ``artifacts/`` and is named after the impl
SHA by default.  Packet sqlite copies are only hashed here; this builder never
opens them with sqlite3 (avoids the G3-B ``-shm`` byte-drift incident).
"""
from __future__ import annotations

import argparse
import csv
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
EVIDENCE = ARTIFACTS / "g3c"
STAGE = EVIDENCE / "stage"
ROOTFS = ARTIFACTS / "security/rootfs"
DEPS = ARTIFACTS / "foundation/deps"
DOCS = ROOT / "docs"
MATRIX_DOC = DOCS / "Autonomous_Teacher_M0_G3C_G3D_Test_Evidence_Matrix_v1.0.csv"
WORK_MATRIX = EVIDENCE / "evidence/evidence-matrix-g3c.csv"

DEFAULT_BASE = "bb5bd0bf83e22130ed0d81c54f54a4673654cfe3"
DEFAULT_G0 = "e107e22"
DEFAULT_IMPL = "e6fde1cdf0bec9e957e98d569b257c8f17dfa363"
MAX_PACKET_BYTES = 100 * 1024 * 1024

DSH_RUNTIME = DEPS / "deepseek_harness_runtime/runtime/deepseek-harness-sdk-runtime-linux-x64"
ROOTFS_CANON = "25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0"
DEPS_CANON = "e07729d7997944417b1c25531749b3e6e5e34aa4248f01dc8f370282082ecb98"
STAGE_EXPECTED = "fcdb0de442d455f89fe849c736679f831c15c50f76e3e4844d38f2963e3735b0"

DOC_SPECS = [
    ("M0_G3C_IMPLEMENTATION_REPORT.md", "IMPLEMENTATION_REPORT.md"),
    ("M0_G3C_REVIEW_REQUEST.md", "REVIEW_REQUEST.md"),
    ("M0_G3C_FINDINGS_AND_DISPOSITION.md", "FINDINGS_AND_DISPOSITION.md"),
]
DOC_BLOBS = [f"docs/{src}" for src, _ in DOC_SPECS] + [
    "docs/Autonomous_Teacher_M0_G3C_G3D_Test_Evidence_Matrix_v1.0.csv",
]

SENSITIVE = [
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----"),
    re.compile(r"(?i)(?:api[_-]?key|access[_-]?token|secret[_-]?key)\s*[:=]\s*['\"][A-Za-z0-9_\-]{16,}['\"]"),
    re.compile(r"(?i)authorization\s*:\s*bearer\s+[A-Za-z0-9._\-]{16,}"),
    re.compile(r"DEEPSEEK_API_KEY\s*=\s*['\"]?[A-Za-z0-9_\-]{16,}"),
]

EXCLUDE_HASH = {"hashes.sha256", "packet-integrity-report.txt"}


class BuildError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def git(*args: str, binary: bool = False):
    proc = subprocess.run(["git", *args], cwd=ROOT, capture_output=True)
    if proc.returncode != 0:
        raise BuildError(f"git {' '.join(args)} failed: "
                         f"{proc.stderr.decode('utf-8', 'replace')}")
    return proc.stdout if binary else proc.stdout.decode("utf-8", "replace")


def resolve(sha: str) -> str:
    return git("rev-parse", "--verify", f"{sha}^{{commit}}").strip()


def git_subject(sha: str) -> str:
    return git("show", "-s", "--format=%s", sha).strip()


def git_parent(sha: str) -> str:
    return git("rev-parse", f"{sha}^").strip()


def git_show(sha: str, path: str) -> bytes:
    return git("show", f"{sha}:{path}", binary=True)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tar_hash(directory: Path) -> str:
    """Streaming canonical tar hash (never buffers the whole tree in memory)."""
    if not directory.is_dir():
        raise BuildError(f"missing directory for canonical hash: {directory}")
    proc = subprocess.Popen(
        ["tar", "--sort=name", "--mtime=@0", "--owner=0", "--group=0",
         "--numeric-owner", "-cf", "-", "-C", str(directory), "."],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    digest = hashlib.sha256()
    assert proc.stdout is not None
    for chunk in iter(lambda: proc.stdout.read(1024 * 1024), b""):
        digest.update(chunk)
    stderr = proc.stderr.read() if proc.stderr is not None else b""
    if proc.wait() != 0:
        raise BuildError(f"tar hash failed for {directory}: "
                         f"{stderr.decode('utf-8', 'replace')[:500]}")
    return digest.hexdigest()


def write_bytes(path: Path, data: bytes, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    if mode is not None:
        path.chmod(mode)


def write_text(path: Path, text: str, mode: int | None = None) -> None:
    write_bytes(path, text.encode("utf-8"), mode)


def copy_tree(src: Path, dst: Path) -> None:
    if not src.exists():
        raise BuildError(f"missing evidence path: {src}")
    for path in src.rglob("*"):
        if path.is_symlink():
            raise BuildError(f"refusing symlink in evidence: {path}")
    shutil.copytree(src, dst, dirs_exist_ok=True)


def copy_file(src: Path, dst: Path) -> None:
    if not src.is_file():
        raise BuildError(f"missing file: {src}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def matrix_summary() -> dict:
    if not MATRIX_DOC.is_file():
        raise BuildError(f"missing docs matrix: {MATRIX_DOC}")
    with MATRIX_DOC.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    return {"rows": len(rows), "status_counts": counts,
            "d_rows_not_run": sum(1 for row in rows
                                  if row["case_id"].startswith("D")
                                  and row["status"] == "NOT_RUN")}


def secret_scan(files: list[Path], out: Path) -> list[str]:
    hits: list[str] = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="strict")
        except (UnicodeDecodeError, OSError):
            continue
        for pattern in SENSITIVE:
            if pattern.search(text):
                hits.append(f"{pattern.pattern} :: {path.relative_to(out).as_posix()}")
    return hits


def check_docs_committed(docs_sha: str) -> None:
    dirty = git("status", "--porcelain", "--", *DOC_BLOBS).strip()
    if dirty:
        raise BuildError("docs files are dirty; commit them before building the "
                         f"packet:\n{dirty}")
    head_docs = git("log", "-1", "--format=%H", "--", *DOC_BLOBS).strip()
    if head_docs != docs_sha:
        raise BuildError(f"docs_sha {docs_sha} is not the last commit touching the "
                         f"docs files ({head_docs}); pass the right --docs-sha")


def write_readme(out: Path, manifest: dict) -> None:
    text = f"""# G3-C review packet ({manifest['impl_sha'][:12]})

No-key, Fake-provider, fixed-rootfs evidence packet for M0 G3-C
(contract / recovery / cancel / deadline / IPC-resource / streaming scope).
It is **not** a G3-D OS-boundary packet and **not** a Live/GO authorization.

- Base: `{manifest['base_sha']}`
- G0: `{manifest['g0_sha']}`
- Impl: `{manifest['impl_sha']}`
- Docs: `{manifest['docs_sha']}`
- Matrix: `{manifest['matrix']['rows']}` rows, `{manifest['matrix']['status_counts']}`
- Rootfs: `{manifest['rootfs_hash']}`
- Deps: `{manifest['deps_hash']}`
- Stage: `{manifest['stage_hash']}`

Layout:

```text
README.md
manifest.json
diff.patch                  # git diff --binary base..impl
hashes.sha256               # all payload files + manifest.json
packet-integrity-report.txt # counts + sha256sum -c result (not self-hashed)
matrix/                     # docs matrix (69 rows) + work matrix
docs/                       # IMPLEMENTATION_REPORT / REVIEW_REQUEST / FINDINGS
evidence/
  env/ commands.jsonl traces/ logs/ ledger/ receipts/ evidence/ regression/
reproduce/                  # commands + expected results
security-nonclaims.md
```

Verify from this directory:

```bash
sha256sum -c hashes.sha256
sh reproduce/verify_packet.sh
```

Do not use the `sqlite3` CLI on copied sqlite files; verify bytes with
`sha256sum` only.  Real DSH runs used the Fake provider; see
`security-nonclaims.md`.
"""
    write_text(out / "README.md", text)


def write_reproduce(out: Path, manifest: dict) -> None:
    packet = out.name
    readme = f"""# G3-C packet reproduction

Packet: `{packet}`
Impl: `{manifest['impl_sha']}`
Docs: `{manifest['docs_sha']}`
Base: `{manifest['base_sha']}`

All commands are host-side and must not use real keys, a real model, external
HTTP or Live.  Host Python **must** be run with `PYTHONDONTWRITEBYTECODE=1` and
`-B` so the frozen deps tree is not modified.  Node/DSH run only inside the
fixed rootfs.

## 1. Packet integrity (from the packet root)

```bash
sha256sum -c hashes.sha256
python3 - <<'PY'
import json
m=json.load(open('manifest.json'))
print(m['impl_sha'], m['docs_sha'], m['file_count'])
PY
```

Expected: every line ends with `OK`.  `hashes.sha256` covers every payload file
plus `manifest.json`; `hashes.sha256` and `packet-integrity-report.txt` are
metadata and are not self-hashed.  See `manifest.file_count`.

## 2. Identity / diff

```bash
cd "/root/Autonomous Teacher"
git rev-parse {manifest['impl_sha'][:12]}
git diff --binary {manifest['base_sha'][:12]}..{manifest['impl_sha'][:12]} | sha256sum
# compare to manifest.diff_sha256
git status --porcelain -uall
```

## 3. Host Python (no bytecode)

```bash
cd "/root/Autonomous Teacher"
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="src:artifacts/foundation/deps"
/root/.local/bin/python3.11 -B -m pytest tests/integration/g3c -q -p no:cacheprovider
/root/.local/bin/python3.11 -B -m pytest tests/integration/g3_bridge -q -p no:cacheprovider
/root/.local/bin/python3.11 -B -m pytest tests/unit/security/test_gates.py -q -p no:cacheprovider
/root/.local/bin/python3.11 -B -m pytest tests/unit/accounting tests/integration/g2_closure -q -p no:cacheprovider
/root/.local/bin/python3.11 -B -m pytest tests/ -q -p no:cacheprovider
/root/.local/bin/python3.11 -B -m ruff check src tests spikes/g3b-trusted-bridge/run_c3
```

Expected: 105 / 31 / 14 / 280 pass; host full 768 passed + 2 known host-env
failures + 1 skipped; Ruff pass.

## 4. Fixed rootfs

```bash
bash scripts/g3c/run-node-tests.sh   # 9/9 adapter, 19/19 guard
bash scripts/g3c/run-oci-full.sh     # 768 passed / 2 env-only failed / 1 skipped
```

## 5. Canonical identity / absence

```bash
tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner -cf - -C artifacts/security/rootfs . | sha256sum
tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner -cf - -C artifacts/foundation/deps . | sha256sum
podman ps -a --format '{{{{.Names}}}}'
```

Expected: `{manifest['rootfs_hash']}`, `{manifest['deps_hash']}`, empty.

## 6. Evidence

`evidence/commands.jsonl` records argv/UTC/exit/rootfs/deps/stage for every
container case; `evidence/traces/` holds raw per-case JSON; `evidence/logs/`
holds raw stdout; `evidence/regression/` holds this round's full regression
logs and JUnit XML.  Do **not** open copied sqlite files with the `sqlite3` CLI;
use `sha256sum` only (G3-B `-shm` drift lesson).
"""
    write_text(out / "reproduce/README.md", readme)
    verify = """#!/bin/sh
# Verify this G3-C packet without modifying it.
set -eu
cd "$(dirname "$0")/.."
sha256sum -c hashes.sha256
python3 -B - <<'PY'
import json
m = json.load(open("manifest.json"))
print("impl_sha=", m["impl_sha"])
print("docs_sha=", m["docs_sha"])
print("file_count=", m["file_count"])
PY
"""
    write_text(out / "reproduce/verify_packet.sh", verify, 0o755)


def write_nonclaims(out: Path, manifest: dict) -> None:
    text = f"""# G3-C security non-claims

This packet is a **no-key, Fake Provider, fixed-rootfs** evidence bundle for
G3-C contract/recovery review.  It is **not** an authorization or a security
proof beyond its stated scope.

- OS trust boundary: `BLOCKED` (`B0-02`).  No G3-D isolation, candidate attack,
  different OS principal, namespace or kernel-deny evidence exists here.  The
  16 G3-D rows in the matrix are `NOT_RUN`.
- No real Key, real model, real provider HTTP, external network or Live run was
  used.  `run_live.sh` exits 3 and `LiveGate.inspect(live_requested=True)`
  remains `BLOCKED`.  Do not add credentials to reproduce this packet.
- Fake provider usage/cost is synthetic (`synthetic_fixture_only=true`); it is
  not a provider token count, invoice, price or settlement proof.
- A local bound Claim / durable Attempt is **at-most-one-send** evidence, not a
  proof of remote exactly-once, provider idempotency, rate-limit behaviour or
  billing accuracy.
- Host-level pytest rows are not real-DSH runs; the matrix labels them
  explicitly.  The real-DSH rows still use the Fake Provider, not a model.
- No claim about the DSH runtime, plugins, kernel, container runtime or supply
  chain being secure or audited.
- No G4/G5/Live/M0 GO.  No push was performed by the owner.
- Packet sqlite copies must not be opened by the `sqlite3` CLI (`mode=ro` can
  touch `-shm` and change bytes); verify with `sha256sum` only.

Packet: `{manifest['packet']}`; impl `{manifest['impl_sha']}`; docs
`{manifest['docs_sha']}`.
"""
    write_text(out / "security-nonclaims.md", text)


def build(args: argparse.Namespace) -> int:
    base = resolve(args.base_sha)
    g0 = resolve(args.g0_sha)
    impl = resolve(args.impl_sha)
    docs_sha = resolve(args.docs_sha) if args.docs_sha else \
        git("log", "-1", "--format=%H", "--", *DOC_BLOBS).strip()

    if not docs_sha:
        raise BuildError("cannot resolve docs_sha; commit the docs first")
    try:
        subprocess.run(["git", "merge-base", "--is-ancestor", impl, docs_sha],
                       cwd=ROOT, check=True, capture_output=True)
    except subprocess.CalledProcessError as exc:
        raise BuildError(f"impl {impl} is not an ancestor of docs {docs_sha}") from exc
    check_docs_committed(docs_sha)

    if args.out:
        out = Path(args.out)
        if not out.is_absolute():
            out = ROOT / out
    else:
        out = ARTIFACTS / f"review-packet-g3c-{impl}"
    out = out.resolve()
    if out.parent != ARTIFACTS.resolve():
        raise BuildError(f"packet output must be directly under {ARTIFACTS}: {out}")
    if out.exists():
        if not args.force:
            raise BuildError(f"output exists (use --force): {out}")
        shutil.rmtree(out)
    out.mkdir(parents=True)

    created = utc_now()
    # 1) diff.patch (new files included; binary-safe)
    diff = git("diff", "--binary", f"{base}..{impl}", binary=True)
    write_bytes(out / "diff.patch", diff)

    # 2) docs from the committed docs_sha (byte-exact)
    for src, dst in DOC_SPECS:
        write_bytes(out / "docs" / dst, git_show(docs_sha, f"docs/{src}"))
    write_bytes(out / "matrix" / MATRIX_DOC.name,
                git_show(docs_sha, f"docs/{MATRIX_DOC.name}"))
    copy_file(WORK_MATRIX, out / "matrix" / WORK_MATRIX.name)

    # 3) evidence tree (copy only; never move)
    copy_tree(EVIDENCE / "env", out / "evidence/env")
    copy_file(EVIDENCE / "commands.jsonl", out / "evidence/commands.jsonl")
    copy_tree(EVIDENCE / "traces", out / "evidence/traces")
    copy_tree(EVIDENCE / "logs", out / "evidence/logs")
    copy_tree(EVIDENCE / "ledger", out / "evidence/ledger")
    copy_tree(EVIDENCE / "receipts", out / "evidence/receipts")
    copy_tree(EVIDENCE / "evidence", out / "evidence/evidence")
    copy_tree(EVIDENCE / "regression", out / "evidence/regression")

    # 4) stable local metadata for the manifest
    stage_hash = tar_hash(STAGE)
    rootfs_hash = tar_hash(ROOTFS)
    deps_hash = tar_hash(DEPS)
    if rootfs_hash != ROOTFS_CANON or deps_hash != DEPS_CANON:
        raise BuildError(f"canonical drift: rootfs={rootfs_hash} deps={deps_hash}")
    if stage_hash != STAGE_EXPECTED:
        raise BuildError(f"stage hash drift: {stage_hash} != {STAGE_EXPECTED}")
    runtime_sha = sha256_file(DSH_RUNTIME) if DSH_RUNTIME.is_file() else "MISSING"
    runtime_size = DSH_RUNTIME.stat().st_size if DSH_RUNTIME.is_file() else 0
    matrix = matrix_summary()
    regression_path = EVIDENCE / "regression/summary-regression.json"
    regression = json.loads(regression_path.read_text()) if regression_path.is_file() else None

    # 4b) manifest/readme (README is payload; counts include all metadata)
    manifest = {
        "schema": "m0.g3c.review-packet.v1",
        "packet": out.name,
        "created_utc": created,
        "base_sha": base,
        "g0_sha": g0,
        "impl_sha": impl,
        "impl_parent_sha": git_parent(impl),
        "impl_subject": git_subject(impl),
        "docs_sha": docs_sha,
        "docs_parent_sha": git_parent(docs_sha),
        "diff_sha256": sha256_bytes(diff),
        "rootfs_hash": rootfs_hash,
        "deps_hash": deps_hash,
        "stage_hash": stage_hash,
        "stage_json_note": ("env/stage.json records the 13:40 build-time hash "
                            "981737...; the post-fix run refreshed "
                            "stage/fixtures/capture-tools.json, so the final stage "
                            "hash is fcdb0de... (see env/fix-run-start.txt STAGE_AFTER)"),
        "dsh_runtime": {"sha256": runtime_sha, "bytes": runtime_size,
                        "version": "0.2.2-rc.2", "sdk": "0.2.2rc2"},
        "python": "3.11.15",
        "node": "v22.23.2",
        "podman": "4.9.3",
        "matrix": {"rows": matrix["rows"],
                   "status_counts": matrix["status_counts"],
                   "d_rows_not_run": matrix["d_rows_not_run"]},
        "regression": regression,
        "excluded_from_hashes": sorted(EXCLUDE_HASH),
        "no_real_key": True,
        "no_real_model": True,
        "no_external_http": True,
        "live_gate": "BLOCKED",
        "scope": "G3-C no-key contract/recovery/integration evidence; G3-D is NOT_RUN",
        "security_nonclaims": "security-nonclaims.md",
    }
    write_reproduce(out, manifest)
    write_nonclaims(out, manifest)
    base_payload = sum(1 for path in out.rglob("*") if path.is_file())
    manifest["file_count"] = base_payload + 4  # README + manifest + hashes + report
    manifest["payload_hash_count"] = base_payload + 2  # README + manifest
    write_readme(out, manifest)
    write_text(out / "manifest.json",
               json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    # 5) secret scan over payload + manifest before hashing
    all_files = [path for path in out.rglob("*") if path.is_file()]
    hits = secret_scan(all_files, out)
    if hits:
        raise BuildError("secret-like pattern(s) found in packet:\n" + "\n".join(hits))

    # 6) hashes.sha256 over every payload file + manifest (not self/report)
    lines = []
    for path in sorted(all_files):
        rel = path.relative_to(out).as_posix()
        if rel in EXCLUDE_HASH:
            continue
        lines.append(f"{sha256_file(path)}  {rel}")
    write_text(out / "hashes.sha256", "\n".join(lines) + "\n")
    hashed = len(lines)

    # 7) integrity report (not self-hashed)
    verify = subprocess.run(["sha256sum", "-c", "hashes.sha256"], cwd=out,
                            capture_output=True, text=True, check=False)
    ok = verify.returncode == 0
    ok_count = sum(1 for line in verify.stdout.splitlines() if line.endswith(": OK"))
    total_files = sum(1 for path in out.rglob("*") if path.is_file()) + 1  # + this report
    total_bytes = sum(path.stat().st_size for path in out.rglob("*") if path.is_file())
    if total_bytes > MAX_PACKET_BYTES:
        raise BuildError(f"packet too large: {total_bytes} bytes")
    report = f"""G3-C review packet integrity report
packet={out.name}
created_utc={created}
impl_sha={impl}
docs_sha={docs_sha}
diff_sha256={manifest['diff_sha256']}

file_count_total={total_files}
manifest_file_count={manifest['file_count']}
payload_hashed={hashed}
metadata_not_self_hashed={', '.join(sorted(EXCLUDE_HASH))}
sha256sum -c hashes.sha256: {'OK' if ok else 'FAILED'} ({ok_count}/{hashed} verified)
secret_scan: PASS (patterns: sk-, private key, api key/token assignment, bearer, DEEPSEEK_API_KEY)
packet_bytes={total_bytes}
rootfs_hash={rootfs_hash}
deps_hash={deps_hash}
stage_hash={stage_hash}

notes:
- hashes.sha256 covers every payload file plus manifest.json; it does not cover
  itself or this report (self-reference is impossible).  packet-integrity-report.txt
  is therefore not self-hashed; all evidence/docs/diff bytes are covered.
- sqlite copies were not opened; only sha256sum/read-only file operations were used.
- No G3-B packet/artifacts, no G3-D implementation, no keys/PII are included.
"""
    write_text(out / "packet-integrity-report.txt", report)
    if not ok:
        raise BuildError("hashes.sha256 verification failed")

    # 8) root README (added after hashing would break hashes; write before next run)
    # The README is written before hashing in normal flow; here we only report.
    print(json.dumps({"packet": str(out), "file_count": total_files,
                      "payload_hashed": hashed, "bytes": total_bytes,
                      "diff_sha256": manifest["diff_sha256"],
                      "docs_sha": docs_sha, "impl_sha": impl}, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-sha", default=DEFAULT_BASE)
    parser.add_argument("--g0-sha", default=DEFAULT_G0)
    parser.add_argument("--impl-sha", default=DEFAULT_IMPL)
    parser.add_argument("--docs-sha", default=None,
                        help="docs commit; default = last commit touching docs")
    parser.add_argument("--out", default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    try:
        return build(args)
    except BuildError as exc:
        sys.stderr.write(f"BUILD_PACKET_ERROR: {exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
