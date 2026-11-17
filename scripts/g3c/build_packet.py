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
DEFAULT_IMPL = "b2f6af054555705192c4e1ae3019a68078764736"
MAX_PACKET_BYTES = 100 * 1024 * 1024

REVIEW_REPORT = "docs/REVIEW_G3C_INDEPENDENT.md"
REVIEW_REPORT_SHA = "4744c61f1561c6f92634b29ef9a6a0f7ca82c4627aef31ba3d0163e4886d23b1"
REVIEW_REPORT_BYTES = 32720
REVIEW_RUN_INDEX = ARTIFACTS / "reviewer-g3c/RUN_INDEX.md"
REVIEW_PACKET_V1 = "review-packet-g3c-e6fde1cdf0bec9e957e98d569b257c8f17dfa363"
MATRIX_AUDIT = EVIDENCE / "evidence/matrix-path-audit-pr1.txt"
PR1_REGRESSION = EVIDENCE / "regression/pr1-summary-regression.json"

DSH_RUNTIME = DEPS / "deepseek_harness_runtime/runtime/deepseek-harness-sdk-runtime-linux-x64"
ROOTFS_CANON = "25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0"
DEPS_CANON = "e07729d7997944417b1c25531749b3e6e5e34aa4248f01dc8f370282082ecb98"
STAGE_EXPECTED = "fcdb0de442d455f89fe849c736679f831c15c50f76e3e4844d38f2963e3735b0"

DOC_SPECS = [
    ("M0_G3C_IMPLEMENTATION_REPORT.md", "IMPLEMENTATION_REPORT.md"),
    ("M0_G3C_REVIEW_REQUEST.md", "REVIEW_REQUEST.md"),
    ("M0_G3C_FINDINGS_AND_DISPOSITION.md", "FINDINGS_AND_DISPOSITION.md"),
    ("M0_G3C_REVIEW_ERRATA.md", "REVIEW_ERRATA.md"),
]
DOC_BLOBS = [f"docs/{src}" for src, _ in DOC_SPECS] + [
    "docs/Autonomous_Teacher_M0_G3C_G3D_Test_Evidence_Matrix_v1.0.csv",
    REVIEW_REPORT,
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
    dirty = git("status", "--porcelain", "-uall", "--", "docs").strip()
    if dirty:
        raise BuildError("docs files are dirty; commit them before building the "
                         f"packet:\n{dirty}")
    head_docs = git("log", "-1", "--format=%H", "--", "docs").strip()
    if head_docs != docs_sha:
        raise BuildError(f"docs_sha {docs_sha} is not the last commit touching "
                         f"docs/ ({head_docs}); pass the right --docs-sha")


def write_readme(out: Path, manifest: dict) -> None:
    previous = manifest["previous_review"]
    text = f"""# G3-C review packet v2 ({manifest['impl_sha'][:12]})

No-key, Fake-provider, fixed-rootfs evidence packet for M0 G3-C
(contract / recovery / cancel / deadline / IPC-resource / streaming scope).
It is **not** a G3-D OS-boundary packet and **not** a Live/GO authorization.
This is the PR1 packet after the independent v1 review returned `PARTIAL`
(no P0; P1-1/P1-2/P1-3).  It does not itself claim a PASS; the second review
must re-verify the P1 fixes independently.

- Base: `{manifest['base_sha']}`
- G0: `{manifest['g0_sha']}`
- Impl: `{manifest['impl_sha']}` (parent `{manifest['impl_parent_sha']}`)
- Docs: `{manifest['docs_sha']}` (parent `{manifest['docs_parent_sha']}`)
- Previous review: `{previous['verdict']}`, P0={previous['p0_count']}, P1={len(previous['p1'])}
- Matrix: `{manifest['matrix']['rows']}` rows, `{manifest['matrix']['status_counts']}`
- Rootfs: `{manifest['rootfs_hash']}`
- Deps: `{manifest['deps_hash']}`
- Stage: `{manifest['stage_hash']}`

Layout:

```text
README.md
manifest.json                  # identity + previous_review/P1 index
diff.patch                     # git diff --binary base..impl
docs-diff.patch                # git diff --binary base..docs (includes docs)
hashes.sha256                  # all payload files + manifest.json
packet-integrity-report.txt    # counts + sha256sum -c result (not self-hashed)
review/                        # v1 report original bytes, errata, run index
matrix/                        # docs matrix + work matrix + P1-3 path audit
docs/                          # IMPLEMENTATION_REPORT / REVIEW_REQUEST / FINDINGS / ERRATA
evidence/
  env/ commands.jsonl traces/ logs/ ledger/ receipts/ evidence/ regression/ pr1/
reproduce/                     # R0-R5, P1-specific and DSH commands
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
    readme = f"""# G3-C packet v2 reproduction (R0-R5 + P1 checks)

Packet: `{packet}`
Impl: `{manifest['impl_sha']}`
Docs: `{manifest['docs_sha']}`
Base: `{manifest['base_sha']}`
Previous independent verdict: `{manifest['previous_review']['verdict']}` (P0 none; P1-1/P1-2/P1-3)

All commands are host-side and must not use real keys, a real model, external
HTTP or Live.  Host Python **must** be run with `PYTHONDONTWRITEBYTECODE=1` and
`-B` so the frozen deps tree is not modified.  Node/DSH run only inside the
fixed rootfs.

## R0. Packet integrity and identity

```bash
sha256sum -c hashes.sha256
python3 - <<'PY'
import json
m=json.load(open('manifest.json'))
print(m['impl_sha'], m['docs_sha'], m['file_count'])
print(m['previous_review']['verdict'], m['previous_review']['p1'])
PY
cd "/root/Autonomous Teacher"
git rev-parse {manifest['impl_sha']} {manifest['docs_sha']}
git diff --binary {manifest['base_sha']}..{manifest['impl_sha']} | sha256sum
# compare to manifest.diff_sha256
git diff --binary {manifest['base_sha']}..{manifest['docs_sha']} | sha256sum
# compare to manifest.docs_diff_sha256
git status --porcelain -uall
```

Expected: every line ends with `OK`; `manifest.file_count` equals the disk file
count; `diff.patch` and `docs-diff.patch` hashes match the manifest.
`hashes.sha256` covers every payload file plus `manifest.json`;
`hashes.sha256` and `packet-integrity-report.txt` are metadata and are not
self-hashed.

## R1. Static / host regression

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

Expected: **110 / 31 / 14 / 280** pass; host full **773 passed / 2 failed / 1
skipped** (the 2 failures are the documented writable-config and hard-coded
`/project` host-env limits); Ruff `All checks passed!`.

## R2. P1-2: two-controller simultaneous cold start (>=20 rounds)

```bash
cd "/root/Autonomous Teacher"
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="src:artifacts/foundation/deps"
UTC=$(date -u +%Y%m%dT%H%M%SZ)
G3C_COLDSTART_EVIDENCE=artifacts/reviewer-g3c/coldstart-$UTC.json \
G3C_COLDSTART_LOG_DIR=artifacts/reviewer-g3c/coldstart-$UTC \
/root/.local/bin/python3.11 -B -m pytest \
  tests/integration/g3c/test_c3_05_twocontroller_coldstart.py -q -p no:cacheprovider
```

Expected: 20/20 rounds with one winner and one controlled rejection
(`CONTROLLER_SINGLETON_LOCKED` exit 5; a replay loser may use exit 3 and a
journal failure exit 4), **0 traceback**, Fake counter=1, Attempt `SETTLED`.
Do not reuse the Owner JSON as a substitute for your own run.

## R3. P1-1: real-DSH label verification

```bash
cd "/root/Autonomous Teacher"
python3 reproduce/check_p1_labels.py "/root/Autonomous Teacher"
# C1-01A must be raw-UDS, not DSH:
test -f artifacts/g3c/traces/probe-replay/probe-result.json
test ! -f artifacts/g3c/traces/probe-replay/dsh-result.json
grep -E 'C1-01A|C1-04|C2-02D|C2-02E|C3-01B|C3-01C|C3-02A|C3-02B|C-END-01' \
  matrix/Autonomous_Teacher_M0_G3C_G3D_Test_Evidence_Matrix_v1.0.csv
```

Expected: the 8 corrected rows are labelled raw-UDS/container reconcile/summary;
real DSH rows have a `dsh-result.json` under their trace directory; host pytest
rows say `host-level (not DSH)`.

## R4. P1-3: matrix path audit

```bash
cd "/root/Autonomous Teacher"
python3 reproduce/check_matrix_paths.py "/root/Autonomous Teacher"
```

Expected: both the docs matrix and the working matrix report `missing=0` for
`db_or_receipt_path`/`log_path`; the 16 D rows are still `NOT_RUN` and their raw
row hashes are unchanged from the v1 freeze (`matrix/matrix-path-audit-pr1.txt`
records the Owner before/after audit: 25 -> 0).

## R5. Real DSH Echo / Tool / Stream / Crash / reconcile (fixed rootfs)

```bash
cd "/root/Autonomous Teacher"
STAGE=$PWD/artifacts/g3c/stage
DEPS=$PWD/artifacts/foundation/deps
ROOTFS=$PWD/artifacts/security/rootfs
run_dsh() {{
  name=$1; prompt=$2; shift 2
  ev=$PWD/artifacts/g3c/traces/reviewer-$name
  mkdir -p "$ev"; chmod 0777 "$ev"
  podman run --rm --name "reviewer-$name" \
    --network none --http-proxy=false --unsetenv-all \
    --env PATH=/opt/python/bin:/usr/bin --env HOME=/work \
    --env PYTHONPATH=/probe/src:/deps --env PYTHONDONTWRITEBYTECODE=1 --env TMPDIR=/tmp \
    --read-only --read-only-tmpfs=false --cap-drop ALL --security-opt no-new-privileges \
    --user 65534:65534 --pids-limit 160 --memory 1g --memory-swap 1g --cpus 1 \
    --tmpfs /tmp:rw,noexec,nosuid,nodev,size=64m,mode=1777 \
    --tmpfs /work:rw,noexec,nosuid,nodev,size=512m,mode=1777 \
    --workdir /work --timeout 180 --systemd=false \
    --mount "type=bind,src=$STAGE,dst=/probe,ro=true" \
    --mount "type=bind,src=$DEPS,dst=/deps,ro=true" \
    --mount "type=bind,src=$ev,dst=/evidence,rw=true" \
    --rootfs "$ROOTFS" /opt/python/bin/python3.11 -B /probe/run_c3/worker_c3.py \
    --label "reviewer-$name" --prompt "$prompt" "$@" --evidence /evidence
}}
run_dsh echo "G3C_ECHO"
run_dsh tool "Use skill_lookup to look up binary_search" --scenario tool
run_dsh stream-slow "G3C_STREAM" --scenario stream_slow
```

Crash (then reconcile the same trace directory; the seed used by the Owner is
`traces/crash-after_response_before_settlement-fixed`, copy it to a Reviewer
directory and mount it read-only as `/seed`):

```bash
# crash: provider response observed, controller exits before settlement
podman run --rm --name reviewer-crash \
  --network none --http-proxy=false --unsetenv-all \
  --env PATH=/opt/python/bin:/usr/bin --env HOME=/work \
  --env PYTHONPATH=/probe/src:/deps --env PYTHONDONTWRITEBYTECODE=1 --env TMPDIR=/tmp \
  --env G3B_TEST_MODE=1 --env G3B_CRASH_HOOK=after_response_before_settlement \
  --read-only --read-only-tmpfs=false --cap-drop ALL --security-opt no-new-privileges \
  --user 65534:65534 --pids-limit 160 --memory 1g --memory-swap 1g --cpus 1 \
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=64m,mode=1777 \
  --tmpfs /work:rw,noexec,nosuid,nodev,size=512m,mode=1777 \
  --workdir /work --timeout 150 --systemd=false \
  --mount "type=bind,src=$STAGE,dst=/probe,ro=true" \
  --mount "type=bind,src=$DEPS,dst=/deps,ro=true" \
  --mount "type=bind,src=$PWD/artifacts/g3c/traces/reviewer-crash,dst=/evidence,rw=true" \
  --rootfs "$ROOTFS" /opt/python/bin/python3.11 -B /probe/run_c3/worker_c3.py \
  --label reviewer-crash --prompt G3C_CRASH --evidence /evidence
# reconcile: seed is a copy of the crash work dir, never the live trace
podman run --rm --name reviewer-reconcile \
  --network none --http-proxy=false --unsetenv-all \
  --env PATH=/opt/python/bin:/usr/bin --env HOME=/work \
  --env PYTHONPATH=/probe/src:/deps --env PYTHONDONTWRITEBYTECODE=1 --env TMPDIR=/tmp \
  --read-only --read-only-tmpfs=false --cap-drop ALL --security-opt no-new-privileges \
  --user 65534:65534 --pids-limit 160 --memory 1g --memory-swap 1g --cpus 1 \
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=64m,mode=1777 \
  --tmpfs /work:rw,noexec,nosuid,nodev,size=512m,mode=1777 \
  --workdir /work --timeout 120 --systemd=false \
  --mount "type=bind,src=$STAGE,dst=/probe,ro=true" \
  --mount "type=bind,src=$DEPS,dst=/deps,ro=true" \
  --mount "type=bind,src=$PWD/artifacts/g3c/traces/reviewer-reconcile,dst=/evidence,rw=true" \
  --mount "type=bind,src=$PWD/artifacts/g3c/traces/reviewer-crash/work,dst=/seed,ro=true" \
  --rootfs "$ROOTFS" /opt/python/bin/python3.11 -B /probe/run_c3/reconcile_c3.py \
  --seed /seed --run-id reviewer-reconcile --evidence /evidence
```

Expected: Echo 1 Attempt/Claim/Receipt/SETTLED; Tool 2 independent Attempts
(SETTLED); Stream first chunk before Fake exit; Crash has no successful finish
and no resend; reconcile is conservative (`SETTLEMENT_UNCERTAIN` without a
receipt, settle once with a receipt).  Real-DSH runs still use the Fake provider,
not a model.

## R6. Node / Guard / OCI full

```bash
cd "/root/Autonomous Teacher"
bash scripts/g3c/run-node-tests.sh   # 9/9 adapter, 19/19 guard
bash scripts/g3c/run-oci-full.sh     # 773 passed / 2 env-only failed / 1 skipped
```

Expected: the OCI 2 failures are the documented no-`pgrep` and `/tmp` noexec
wrapper limits, not product assertion failures.

## R7. Canonical / absence / LiveGate

```bash
cd "/root/Autonomous Teacher"
tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner -cf - -C artifacts/security/rootfs . | sha256sum
tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner -cf - -C artifacts/foundation/deps . | sha256sum
tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner -cf - -C artifacts/g3c/stage . | sha256sum
podman ps -a --format '{{{{.Names}}}}'
bash scripts/run_live.sh; echo RUN_LIVE_EXIT=$?
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /root/.local/bin/python3.11 -B -c \
  "from autoteacher_m0.security.gates import LiveGate; print(LiveGate().inspect(live_requested=True))"
```

Expected: `{manifest['rootfs_hash']}`, `{manifest['deps_hash']}`,
`{manifest['stage_hash']}`, empty `podman ps -a`, `RUN_LIVE_EXIT=3`,
`GateDecision(status='BLOCKED', ...)`, no Key env and no `.env`.

## R8. Evidence and sqlite safety

`evidence/commands.jsonl` records argv/UTC/exit/rootfs/deps/stage for every
container case; `evidence/traces/` holds raw per-case JSON; `evidence/logs/`
holds raw stdout; `evidence/regression/` holds this round's full regression
logs and JUnit XML; `evidence/pr1/` holds the PR1 traces/logs/src snapshot.
**Do not** open copied sqlite files with the `sqlite3` CLI (it can touch `-shm`
and change bytes).  Copy to `/tmp` first if a query is unavoidable, or use
`sha256sum` only.
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
print("previous_review=", m["previous_review"]["verdict"])
PY
"""
    write_text(out / "reproduce/verify_packet.sh", verify, 0o755)

    matrix_check = '''#!/usr/bin/env python3
"""Check every matrix db_or_receipt_path/log_path exists in the repo.

Usage: python3 reproduce/check_matrix_paths.py "/root/Autonomous Teacher"
Read-only; no sqlite is opened.
"""
import csv
import sys
from pathlib import Path

root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
matrices = [
    root / "docs/Autonomous_Teacher_M0_G3C_G3D_Test_Evidence_Matrix_v1.0.csv",
    root / "artifacts/g3c/evidence/evidence-matrix-g3c.csv",
]
failed = False
for matrix in matrices:
    if not matrix.is_file():
        print("MISSING_MATRIX", matrix)
        failed = True
        continue
    missing = []
    rows = 0
    with matrix.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows += 1
            if row.get("status") != "PASS":
                continue
            for field in ("db_or_receipt_path", "log_path"):
                value = (row.get(field) or "").strip()
                if not value:
                    continue
                for part in value.split(";"):
                    part = part.strip()
                    if not part or not part.startswith("artifacts/"):
                        continue
                    if not (root / part).exists():
                        missing.append((row.get("case_id"), field, part))
    print(f"{matrix.name}: rows={rows} missing={len(missing)}")
    for case, field, value in missing:
        print("  MISSING", case, field, value)
    if missing:
        failed = True
sys.exit(1 if failed else 0)
'''
    write_text(out / "reproduce/check_matrix_paths.py", matrix_check, 0o755)

    label_check = '''#!/usr/bin/env python3
"""Spot-check the P1-1 real-DSH labels and evidence types.

Usage: python3 reproduce/check_p1_labels.py "/root/Autonomous Teacher"
Read-only; does not run DSH or open sqlite.
"""
import csv
import re
import sys
from pathlib import Path

root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
matrix = root / "docs/Autonomous_Teacher_M0_G3C_G3D_Test_Evidence_Matrix_v1.0.csv"
expected = {
    "C1-01A": "raw-UDS",
    "C1-04": "raw-UDS",
    "C3-01B": "raw-UDS",
    "C3-01C": "raw-UDS",
    "C3-02A": "raw-UDS",
    "C3-02B": "raw-UDS",
    "C2-02D": "container reconcile",
    "C2-02E": "container reconcile",
    "C1-01D": "host-level",
    "C2-04": "host-level",
}
rows = {}
with matrix.open(encoding="utf-8-sig", newline="") as handle:
    for row in csv.DictReader(handle):
        rows[row["case_id"]] = row
failed = False
for case, needle in expected.items():
    row = rows.get(case)
    if row is None:
        print("MISSING_ROW", case); failed = True; continue
    observed = row.get("observed", "")
    if needle not in observed:
        print("BAD_LABEL", case, "expected", needle, "observed", observed[:160])
        failed = True
    else:
        print("OK_LABEL", case, needle)

# Every matrix row that is claimed real DSH must link a trace with dsh-result.
for case, row in rows.items():
    if row.get("status") != "PASS" or case == "C-END-02":
        continue
    observed = row.get("observed", "")
    if "real DSH" not in observed or "raw-UDS" in observed:
        continue
    value = (row.get("db_or_receipt_path") or "").strip()
    if not value:
        continue
    found = False
    for part in value.split(";"):
        part = part.strip()
        if not part.startswith("artifacts/"):
            continue
        target = root / part
        if target.is_dir():
            target = target / "dsh-result.json"
        if target.exists():
            found = True
            break
    if not found:
        print("MISSING_DSH_RESULT", case, value)
        failed = True
print("P1_1_LABEL_CHECK", "FAILED" if failed else "OK")
sys.exit(1 if failed else 0)
'''
    write_text(out / "reproduce/check_p1_labels.py", label_check, 0o755)


def write_review(out: Path, docs_sha: str, manifest: dict) -> None:
    """Archive the v1 report byte-for-byte plus errata and evidence pointers."""
    report = git_show(docs_sha, REVIEW_REPORT)
    if sha256_bytes(report) != REVIEW_REPORT_SHA:
        raise BuildError("archived v1 review report hash mismatch: "
                         f"{sha256_bytes(report)} != {REVIEW_REPORT_SHA}")
    if len(report) != REVIEW_REPORT_BYTES:
        raise BuildError(f"archived v1 review report size mismatch: {len(report)}")
    write_bytes(out / "review/REVIEW_G3C_INDEPENDENT.md", report)
    write_bytes(out / "review/REVIEW_ERRATA.md",
                git_show(docs_sha, "docs/M0_G3C_REVIEW_ERRATA.md"))
    copy_file(REVIEW_RUN_INDEX, out / "review/RUN_INDEX.md")
    index = f"""# v1 Reviewer evidence index (pointer only)

The full 13 MB / 748-file Reviewer evidence tree is **not** copied into this
packet.  The paths below are relative to the repository root and remain at
`artifacts/reviewer-g3c/` (Git-ignored; Lead must archive it explicitly if
needed).

- Report (original bytes): `docs/REVIEW_G3C_INDEPENDENT.md` (339 lines,
  sha256 `{REVIEW_REPORT_SHA}`); packet copy `review/REVIEW_G3C_INDEPENDENT.md`.
- Errata: `docs/M0_G3C_REVIEW_ERRATA.md`; packet copy `review/REVIEW_ERRATA.md`.
- Run index: `artifacts/reviewer-g3c/RUN_INDEX.md`; packet copy `review/RUN_INDEX.md`.

| v1 finding | Reviewer evidence (repo path) | Packet counterpart |
|---|---|---|
| R0 identity / packet / matrix | `artifacts/reviewer-g3c/r0-identity/identity.txt`, `matrix-protected.txt`, `final-canonical.txt`, `livegate.txt`, `network-key-scan.txt` | `matrix/`, `evidence/regression/pr1-canonical-after.log` |
| P1-1 real-DSH labels | `artifacts/reviewer-g3c/r1-static/matrix-label-audit.txt`; `r3-dsh/commands.jsonl`, `r3-dsh/traces/reviewer-*/` | `docs/M0_G3C_FINDINGS_AND_DISPOSITION.md` §4; `matrix/` |
| P1-2 cold start | `artifacts/reviewer-g3c/r2/p2c-startup-lock.log`, `r2/summary.json`, `r2/p2c-session-identity.log` | `evidence/evidence/concurrency-coldstart-*.json`, `evidence/logs/coldstart-*`, `evidence/regression/pr1-coldstart.log` |
| P1-3 matrix paths | `artifacts/reviewer-g3c/r1-static/matrix-path-audit.txt` | `matrix/matrix-path-audit-pr1.txt`, `evidence/evidence/matrix-path-audit-pr1.txt` |
| R2 probes | `artifacts/reviewer-g3c/r2/probe_suite.py`, `r2/work/<case>/case.json`, `r2/probe-suite.log` | not copied; run from `artifacts/reviewer-g3c/` |
| R3 real DSH | `artifacts/reviewer-g3c/r3-dsh/{{commands.jsonl,traces,env,summary.txt}}` | `evidence/traces/`, `evidence/pr1/traces/` |
| R4 cross-check | `artifacts/reviewer-g3c/r4-crosscheck/crosscheck.json`, `crosscheck.log` | `evidence/ledger/`, `evidence/receipts/` |

Packet v1 (frozen, for the v1 identity only):
`artifacts/{REVIEW_PACKET_V1}/` (docs_sha `78be77c`, 1713/1713 hashes OK).
"""
    write_text(out / "review/V1_EVIDENCE_INDEX.md", index)


def write_nonclaims(out: Path, manifest: dict) -> None:
    text = f"""# G3-C packet v2 security non-claims

This packet is a **no-key, Fake Provider, fixed-rootfs** evidence bundle for
G3-C contract/recovery review after the v1 independent `PARTIAL`.  It is
**not** an authorization, a PASS, or a security proof beyond its stated scope.

- v1 independent review is archived unchanged (`review/REVIEW_G3C_INDEPENDENT.md`,
  sha256 `{REVIEW_REPORT_SHA}`); its last verdict is `PARTIAL`.  This packet
  records Owner fixes and evidence for a **second** review; it does not replace
  that review and does not change the v1 text.
- P1-1 is a **label/claim correction**, not a new real-DSH replay.  C1-01A is
  raw-UDS; C1-04/C3-01B/C/C3-02A/B are raw-UDS; C2-02D/E are container
  reconcile; host rows are host pytest.  No real Provider/model was used.
- P1-2 is a code fix for two Controller cold starts (busy_timeout before WAL,
  bounded retries, per-socket `flock` singleton, controlled exits 5/4/3).  It
  does **not** cover two real DSH clients competing for the same Claim.
- P1-3 is a matrix path-index correction (25 missing -> 0); it does not prove
  every row's assertion was independently re-run by this packet.
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
`{manifest['docs_sha']}`; previous review `{manifest['previous_review']['verdict']}`.
"""
    write_text(out / "security-nonclaims.md", text)


def build(args: argparse.Namespace) -> int:
    base = resolve(args.base_sha)
    g0 = resolve(args.g0_sha)
    impl = resolve(args.impl_sha)
    docs_sha = resolve(args.docs_sha) if args.docs_sha else \
        git("log", "-1", "--format=%H", "--", "docs").strip()

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
    # 1) diff.patch (impl) + docs-diff.patch (impl + docs)
    diff = git("diff", "--binary", f"{base}..{impl}", binary=True)
    write_bytes(out / "diff.patch", diff)
    docs_diff = git("diff", "--binary", f"{base}..{docs_sha}", binary=True)
    write_bytes(out / "docs-diff.patch", docs_diff)

    # 2) docs from the committed docs_sha (byte-exact)
    for src, dst in DOC_SPECS:
        write_bytes(out / "docs" / dst, git_show(docs_sha, f"docs/{src}"))
    write_bytes(out / "matrix" / MATRIX_DOC.name,
                git_show(docs_sha, f"docs/{MATRIX_DOC.name}"))
    copy_file(WORK_MATRIX, out / "matrix" / WORK_MATRIX.name)
    copy_file(MATRIX_AUDIT, out / "matrix" / MATRIX_AUDIT.name)
    write_review(out, docs_sha, {"impl_sha": impl, "docs_sha": docs_sha})

    # 3) evidence tree (copy only; never move)
    copy_tree(EVIDENCE / "env", out / "evidence/env")
    copy_file(EVIDENCE / "commands.jsonl", out / "evidence/commands.jsonl")
    copy_tree(EVIDENCE / "traces", out / "evidence/traces")
    copy_tree(EVIDENCE / "logs", out / "evidence/logs")
    copy_tree(EVIDENCE / "ledger", out / "evidence/ledger")
    copy_tree(EVIDENCE / "receipts", out / "evidence/receipts")
    copy_tree(EVIDENCE / "evidence", out / "evidence/evidence")
    copy_tree(EVIDENCE / "regression", out / "evidence/regression")
    copy_tree(EVIDENCE / "pr1", out / "evidence/pr1")

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
    regression_path = PR1_REGRESSION if PR1_REGRESSION.is_file() else \
        EVIDENCE / "regression/summary-regression.json"
    regression = json.loads(regression_path.read_text()) if regression_path.is_file() else None
    coldstart_evidence = sorted(EVIDENCE.glob("evidence/concurrency-coldstart-*.json"))
    latest_coldstart = coldstart_evidence[-1].name if coldstart_evidence else None
    previous_review = {
        "verdict": "PARTIAL",
        "p0_count": 0,
        "report": REVIEW_REPORT,
        "report_sha256": REVIEW_REPORT_SHA,
        "report_lines": 339,
        "errata": "docs/M0_G3C_REVIEW_ERRATA.md",
        "reviewer_evidence_root": "artifacts/reviewer-g3c/",
        "packet_v1": REVIEW_PACKET_V1,
        "packet_v1_docs_sha": "78be77c3c63fce62527dccd7ec8c1458047d81bf",
        "p1": [
            {"id": "P1-1", "summary": "real-DSH coverage over-claimed; C1-01A was raw-UDS",
             "fix": "docs relabel (9ffa0b1/bea0fc3); no new real-DSH replay claimed"},
            {"id": "P1-2", "summary": "two-controller cold start raised database is locked",
             "fix": "impl b2f6af0 + 20-round controlled coldstart evidence"},
            {"id": "P1-3", "summary": "25/53 matrix evidence paths did not exist",
             "fix": "matrix paths + audit (25 -> 0); D rows byte-identical"},
        ],
        "second_review": "NOT_PERFORMED (Lead must assign; this packet does not claim PASS)",
        "coldstart_evidence": latest_coldstart,
    }

    # 4b) manifest/readme (README is payload; counts include all metadata)
    manifest = {
        "schema": "m0.g3c.review-packet.v2",
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
        "docs_diff_sha256": sha256_bytes(docs_diff),
        "previous_review": previous_review,
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
    report = f"""G3-C review packet v2 integrity report
packet={out.name}
created_utc={created}
impl_sha={impl}
docs_sha={docs_sha}
diff_sha256={manifest['diff_sha256']}
docs_diff_sha256={manifest['docs_diff_sha256']}
previous_review_verdict={manifest['previous_review']['verdict']}
previous_review_p0={manifest['previous_review']['p0_count']}
previous_review_p1={','.join(p['id'] for p in manifest['previous_review']['p1'])}
second_review={manifest['previous_review']['second_review']}

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
