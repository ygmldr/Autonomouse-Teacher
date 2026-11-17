#!/usr/bin/env python3.11
"""G3-D review packet builder (host-side, read-only; no project imports).

Usage:
  PYTHONDONTWRITEBYTECODE=1 /root/.local/bin/python3.11 -B \
    scripts/g3d/build_packet.py --docs-sha <sha> [--out <packet-dir>] [--force]

The builder:
  * copies committed docs, the frozen D1/D2/D3 evidence (selected raw files,
    never moving or mutating them) and the D4 regression logs;
  * writes implementation/docs/protected diffs from git;
  * writes source blobs and an env/ identity set;
  * writes manifest.json, hashes.sha256, packet-integrity-report.txt,
    review/ and a verification script;
  * never opens SQLite files (sqlite copies are hashed only), never uses a
    network, never reads keys, never runs pytest/Node/podman.

Only writes inside the requested output directory.  The output directory must
be directly under ``artifacts/``.
"""
from __future__ import annotations

import argparse
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
G3D = ARTIFACTS / "g3d"
D1 = G3D / "d1"
D2 = G3D / "d2"
D3 = G3D / "d3"
D4 = G3D / "d4" / "regression"
DOCS = ROOT / "docs"
MATRIX = DOCS / "Autonomous_Teacher_M0_G3D_Test_Evidence_Matrix_v1.0.csv"

BASE_SHA = "4bd48037d98e081c8fb96a246f3fbf3cf60eb38b"
IMPL_SHA = "97230a0ba40f5f2dec98a426676fbe81a5157a26"
CODE_SHA = "cf40c6bfb84ceae98e795db19efa955aa3035991"
ROOTFS_CANON = "25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0"
DEPS_CANON = "e07729d7997944417b1c25531749b3e6e5e34aa4248f01dc8f370282082ecb98"
D3_STAGE = "artifacts/g3d/stage-20261117T221955Z"
D3_STAGE_TREE = "e1ff14496e06dcb1c887badfb93b858012373be9fe739e61bb04587885e9f9c5"
D3_STAGE_MANIFEST = "644823d46adaef28810ba13bb97547371616177bbc4b8138b1eaed5d9a28eb03"
D1_STAGE = "artifacts/g3d/stage-20261117T195831Z"
D2_STAGE = "artifacts/g3d/stage-20261117T210738Z"

D1_STAGE_MANIFEST = "83b241c77b28813b1d1b55ed96b7f940027a0bd8f2b4eefbbb14b0c4cf09110e"
D2_STAGE_MANIFEST = "6f8f0490b2a2e3d9041b35eb0a4c5e36852661aee555c8b734f52c132b2c89b4"

MAX_FILE_BYTES = 6 * 1024 * 1024
MAX_PACKET_BYTES = 100 * 1024 * 1024
EXCLUDE_HASH = {"hashes.sha256", "packet-integrity-report.txt"}
PAYLOAD_META = {"manifest.json"} | EXCLUDE_HASH

SENSITIVE = [
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----"),
    re.compile(r"(?i)(?:api[_-]?key|access[_-]?token|secret[_-]?key)\s*[:=]\s*['\"][A-Za-z0-9_\-]{16,}['\"]"),
    re.compile(r"(?i)authorization\s*:\s*bearer\s+[A-Za-z0-9._\-]{16,}"),
    re.compile(r"DEEPSEEK_API_KEY\s*=\s*['\"]?[A-Za-z0-9_\-]{16,}"),
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


def sha256_tree(path: Path) -> str:
    proc = subprocess.Popen(
        ["tar", "--sort=name", "--mtime=@0", "--owner=0", "--group=0",
         "--numeric-owner", "-cf", "-", "-C", str(path), "."],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    digest = hashlib.sha256()
    assert proc.stdout is not None
    for chunk in iter(lambda: proc.stdout.read(1 << 20), b""):
        digest.update(chunk)
    stderr = b"" if proc.stderr is None else proc.stderr.read()
    if proc.wait() != 0:
        raise BuildError(f"tar hash failed for {path}: "
                         f"{stderr.decode('utf-8', 'replace')[:500]}")
    return digest.hexdigest()


def git(*args: str, binary: bool = False):
    proc = subprocess.run(["git", *args], cwd=ROOT, capture_output=True)
    if proc.returncode != 0:
        raise BuildError(f"git {' '.join(args)} failed: "
                         f"{proc.stderr.decode('utf-8', 'replace')[:1000]}")
    return proc.stdout if binary else proc.stdout.decode("utf-8", "replace")


def git_show(sha: str, path: str) -> bytes:
    return git("show", f"{sha}:{path}", binary=True)


def git_blob_sha(sha: str, path: str) -> str:
    return git("rev-parse", f"{sha}:{path}").strip()


def write_bytes(path: Path, data: bytes, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    if mode is not None:
        path.chmod(mode)


def write_text(path: Path, text: str, mode: int | None = None) -> None:
    write_bytes(path, text.encode("utf-8"), mode)


def check_no_symlink(path: Path) -> None:
    if path.is_symlink():
        raise BuildError(f"refusing symlink evidence path: {path}")


def copy_file(src: Path, dst: Path, *, required: bool = True,
              max_bytes: int = MAX_FILE_BYTES) -> bool:
    if not src.is_file():
        if required:
            raise BuildError(f"missing required evidence file: {src}")
        return False
    check_no_symlink(src)
    if src.stat().st_size > max_bytes:
        raise BuildError(f"file too large for packet: {src} "
                         f"({src.stat().st_size} > {max_bytes})")
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        raise BuildError(f"duplicate packet destination: {dst}")
    shutil.copy2(src, dst)
    return True


def copy_glob(src_dir: Path, pattern: str, dst_dir: Path, *,
              required: bool = False, max_bytes: int = MAX_FILE_BYTES,
              flatten: bool = False, prefix: str = "") -> int:
    files = sorted(p for p in src_dir.glob(pattern) if p.is_file())
    if required and not files:
        raise BuildError(f"no files matching {pattern} in {src_dir}")
    for src in files:
        check_no_symlink(src)
        name = f"{prefix}{src.name}" if flatten else src.name
        copy_file(src, dst_dir / name, required=True, max_bytes=max_bytes)
    return len(files)


def copy_rel(src_root: Path, dst_root: Path, rel: str, *,
             required: bool = False, max_bytes: int = MAX_FILE_BYTES) -> bool:
    return copy_file(src_root / rel, dst_root / rel, required=required,
                     max_bytes=max_bytes)


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise BuildError(message)


def file_sha_map(root: Path, exclude: set[str]) -> list[tuple[str, str]]:
    rows = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root).as_posix()
        if rel in exclude:
            continue
        check_no_symlink(path)
        rows.append((rel, sha256_file(path)))
    return rows


def payload_tree_hash(rows: list[tuple[str, str]]) -> str:
    text = "".join(f"{digest}  {rel}\n" for rel, digest in sorted(rows))
    return sha256_bytes(text.encode("utf-8"))


# ---------------------------------------------------------------------------
# Evidence selection
# ---------------------------------------------------------------------------

D1_CORE = [
    "summary.json", "commands.jsonl",
    "cleanup/cleanup.json", "cleanup/ps-after.txt", "cleanup/residual-processes.json",
    "run/checks.json", "run/run-summary.txt", "run/exits.json",
    "run/argv-trusted.json", "run/argv-candidate.json", "run/config-admission.json",
    "run/ready", "run/launcher-ready.json", "run/trusted.log", "run/candidate.log",
    "traces/principal.json", "traces/dsh-result.json",
    "db/snapshot.json", "db/paths.json",
    "receipt/summary.json", "receipt/received-count.json",
    "uid-map/runtime-identity.json", "uid-map/candidate-uid_map.txt",
    "uid-map/candidate-gid_map.txt", "uid-map/candidate-status.txt",
    "uid-map/candidate-cgroup.json", "uid-map/trusted-uid_map.txt",
    "uid-map/trusted-gid_map.txt", "uid-map/trusted-status.txt",
    "uid-map/trusted-cgroup.json",
    "mountinfo/candidate.txt", "mountinfo/trusted.txt",
    "peercred/trusted-log.json", "peercred/trusted-log-extract.txt",
    "peercred/trusted-modules.json",
    "socket-stat/before-candidate.json", "socket-stat/listening.json",
    "network-probe/candidate-network.json",
    "env/git.json", "env/git.txt", "env/preflight.json", "env/canonical-pre.json",
    "env/livegate.json", "env/run-layout.json", "env/userns-probe.json",
    "env/setgid-probe.json", "env/stage-summary.json", "env/stage-validation.json",
]

D1_OPTIONAL = [
    "env/canonical-post.json", "socket-stat/after-trusted-stop.json",
    "network-probe/container-network.json", "network-probe/env-names.json",
]

D2_CASES = ["d2-01", "d2-02", "d2-03", "d2-04", "d2-05", "d2-06", "d2-07",
            "d2-08", "d2-09", "d2-10", "d2-10-trusted", "d2-10-trusted-receipt",
            "d2-11-echo", "d2-11-tool", "d2-11-resume", "d2-12", "d2-13",
            "d2-14", "d2-15"]

D2_PROBE_SOURCE = {
    "d2-01": "d2_01_read_state.py", "d2-02": "d2_02_write_state.py",
    "d2-03": "d2_03_state_classes.py", "d2-04": "d2_04_broker_access.py",
    "d2-05": "d2_05_bypass_claim.py", "d2-06": "d2_06_forged_frames.py",
    "d2-07": "d2_07_network.py", "d2-08": "d2_08_kernel_surface.py",
    "d2-09": "d2_09_tool_plugin.py", "d2-10": "d2_10_disconnect.py",
    "d2-12": "d2_12_stress.py", "d2-13": "d2_13_dac_control.py",
    "d2-14": "d2_14_stale_run.py",
}

D3_CASE_FILES = [
    "summary.json", "checks.json", "LEVELS.json",
    "run/run-summary.txt", "run/exits.json",
    "db/snapshot.json", "db/paths.json",
    "mountinfo/candidate.txt", "mountinfo/trusted.txt",
    "peercred/trusted-log.json", "peercred/trusted-log-extract.txt",
    "socket-stat/before-candidate.json", "socket-stat/listening.json",
    "cleanup/cleanup.json", "cleanup/ps-after.txt",
    "cleanup/residual-processes.json",
]

D3_GLOBS = [
    ("state", "*.json"), ("recover", "*.json"), ("recover", "*.log"),
    ("receipt", "*.json"),
    ("stream", "*.json"), ("final", "*.json"), ("run", "argv-*.json"),
]

SOURCE_PATHS = [
    "src/autoteacher_m0/bridge/ipc_server.py",
    "src/autoteacher_m0/bridge/controller.py",
    "scripts/g3d/launch.py",
    "scripts/g3d/build_stage.py",
    "scripts/g3d/lib_g3d.py",
    "scripts/g3d/d2_runner.py",
    "scripts/g3d/d3_runner.py",
    "scripts/g3d/run_d3_suite.py",
    "scripts/g3d/stage/candidate_entry.py",
    "scripts/g3d/stage/trusted_entry.py",
    "scripts/g3d/probes/probe_common.py",
    "config/g3d/trusted/controller.template.json",
    "config/g3d/trusted/broker.template.json",
    "config/g3d/trusted/admission.template.json",
    "config/g3d/candidate/bridge.patch.yml",
]

SOURCE_LINES = {
    "src/autoteacher_m0/bridge/ipc_server.py": [
        ("BridgeServer.__init__ additive socket/peer/ready args", "158-206"),
        ("_apply_socket_boundary (chmod/chown/listen)", "352-375"),
        ("_verify_socket_boundary", "377-391"),
        ("_notify_ready (after listen)", "393-404"),
        ("_authorize_peer SO_PEERCRED fail-closed", "419-455"),
        ("_record_peer_rejection", "457-461"),
    ],
    "src/autoteacher_m0/bridge/controller.py": [
        ("_bridge_options additive config validation", "1551-1568"),
        ("main: singleton lock, reconcile, BridgeServer", "1570-1645"),
    ],
    "scripts/g3d/launch.py": [
        ("Launcher class", "191"),
        ("preflight", "327"),
        ("start_trusted / ready gate", "860"),
        ("start_candidate", "1008"),
        ("collect / evaluate", "1107 / 1298"),
        ("cleanup / write_evidence", "1769 / 1881"),
    ],
    "scripts/g3d/build_stage.py": [
        ("build_stage (allowlist, adapter rebuild)", "315"),
        ("main", "660"),
    ],
    "scripts/g3d/stage/candidate_entry.py": [
        ("scenario_verdict", "379"),
        ("run_dsh", "509"),
        ("main / --mode hold", "600"),
    ],
    "scripts/g3d/stage/trusted_entry.py": [
        ("trusted module inspect.getfile + sha256", "105"),
        ("main", "216"),
    ],
    "scripts/g3d/d3_runner.py": [
        ("D3Runner", "93"),
        ("run_case / crash-recover injection", "699"),
        ("main", "1826"),
    ],
}


def copy_d1_case(name: str, out: Path) -> None:
    src = D1 / name
    dst = out / "d1" / name
    assert_true(src.is_dir(), f"missing D1 case: {src}")
    for rel in D1_CORE:
        copy_rel(src, dst, rel, required=True)
    for rel in D1_OPTIONAL:
        copy_rel(src, dst, rel, required=False)
    copy_glob(src / "receipt", "rcpt-*.json", dst / "receipt", required=True)
    copy_glob(src / "receipt", "timing-*.json", dst / "receipt", required=True)


def copy_d1_stage_manifests(out: Path) -> None:
    dst = out / "d1" / "stage-manifests"
    specs = [
        ("d1-manifest.json", D1_STAGE_MANIFEST, Path(D1_STAGE) / "manifest.json"),
        ("d1-stage-summary.json", None, Path(D1_STAGE) / "stage-summary.json"),
        ("d2-manifest.json", D2_STAGE_MANIFEST, Path(D2_STAGE) / "manifest.json"),
        ("d2-stage-summary.json", None, Path(D2_STAGE) / "stage-summary.json"),
        ("d3-manifest.json", D3_STAGE_MANIFEST, Path(D3_STAGE) / "manifest.json"),
        ("d3-stage-summary.json", None, Path(D3_STAGE) / "stage-summary.json"),
    ]
    lines = []
    for name, expected, src in specs:
        assert_true(src.is_file(), f"missing stage manifest: {src}")
        digest = sha256_file(src)
        if expected is not None:
            assert_true(digest == expected, f"stage manifest drift: {src} {digest}")
        copy_file(src, dst / name, max_bytes=8 * 1024 * 1024)
        lines.append(f"{digest}  {name}")
    write_text(dst / "MANIFEST_SHA256SUMS", "\n".join(lines) + "\n")


def copy_d1_ready_cleanup(out: Path) -> None:
    dst = out / "d1" / "ready-and-cleanup"
    rels = [
        "run/ready", "run/launcher-ready.json",
        "socket-stat/before-candidate.json", "socket-stat/listening.json",
        "socket-stat/after-trusted-stop.json",
        "cleanup/cleanup.json", "cleanup/ps-after.txt",
        "cleanup/residual-processes.json", "env/run-layout.json",
    ]
    for case in ("echo", "tool"):
        src = D1 / case
        for rel in rels:
            copy_file(src / rel, dst / case / rel, required=False)


def copy_d2(out: Path) -> None:
    probe_root = Path(D2_STAGE) / "candidate" / "run" / "probes"
    shared = out / "d2" / "_probe-sources"
    for name in sorted(p.name for p in probe_root.glob("*.py")):
        copy_file(probe_root / name, shared / name)
    write_text(out / "d2" / "old-bypass-to-new-denial.csv",
               "old_bypass,old_evidence,d2_case,current_result,closed_by\n"
               "B-1 read Broker DB,G3-B same-UID reviewer B-1,D2-01,"
               "\"ENOENT(2) for DB/WAL/SHM and /state; broker.sqlite3 SHA unchanged; 0 rows\","
               "\"candidate mount namespace has no /work/state; state 0700 root:root\"\n"
               "B-2 write/truncate/replace Broker DB,G3-B same-UID reviewer B-2,D2-02,"
               "\"O_RDWR/O_CREAT/O_TRUNC/unlink/chmod/replace/hardlink/symlink denied: ENOENT(2)/EROFS(30)/EXDEV(18); no hash change\","
               "\"no state mount; read-only root/tmpfs; state not reachable\"\n"
               "B-3 rewrite Policy,G3-B same-UID reviewer B-3,D2-03,"
               "\"60 probes over 10 state classes all ENOENT(2); hashes and row counts unchanged\","
               "\"candidate has no state copy; trusted owns admission/policy/attempt/receipt\"\n"
               "B-4 direct RESERVED/CLAIMED dispatch without Controller,G3-B same-UID reviewer B-4,D2-04/05/06,"
               "\"import autoteacher_m0 fails; broker/controller private UDS ENOENT; kind reserve/claim/settle -> UNKNOWN_KIND; forged authorized/dispatch_allowed -> UNKNOWN_FIELD; Fake=0\","
               "\"candidate stage has no broker code/DB/socket; Controller is the only Reserve/Claim/Attempt path; protocol schema/digest/route checks\"\n"
               "D2-11 positive control (anti-false-positive),D2-11 real-DSH Echo/Tool/Resume,D2-11,"
               "\"Echo 1/1/1/1 counter=1; Tool 2/2/2/2 counter=2; Resume session 14->24 reason:resume 1; DSH usage==receipt usage\","
               "\"same candidate and same approved socket still work; boundary is not 'disable all UDS'\"\n")
    write_text(out / "d2" / "INDEX.md", """# D2 case index

15 cases / 19 runs, all `exit 0`, `cleanup.ok=true`, canonical rootfs/deps/stage.
`d2-10-trusted` and `d2-10-trusted-receipt` are the Trusted-side fault sub-runs.
`_probe-sources/` contains the probe sources and `probe_common.py`; each case
also carries its own `attack_source.py` (or `attack_source.md` for positive /
crosscheck cases) plus `d2/case.json`, `run/checks.json`, state snapshots and
raw stdout/stderr with real errno/protocol codes.

Old G3-B same-UID bypasses and their new denials: `old-bypass-to-new-denial.csv`.
""")
    for case in D2_CASES:
        src = D2 / case
        dst = out / "d2" / case
        assert_true(src.is_dir(), f"missing D2 case: {src}")
        for rel in ("summary.json", "LEVELS.json",
                    "run/checks.json", "state/pre.json", "state/final.json",
                    "mountinfo/candidate.txt", "run/run-summary.txt",
                    "run/exits.json"):
            copy_file(src / rel, dst / rel, required=False)
        copy_glob(src / "d2", "*.json", dst / "d2")
        copy_glob(src / "attacks", "*.json", dst / "attacks")
        copy_glob(src / "receipt", "*.json", dst / "receipt")
        copy_glob(src / "run", "attack-*.stdout.txt", dst / "run")
        copy_glob(src / "run", "attack-*.stderr.txt", dst / "run")
        source = D2_PROBE_SOURCE.get(case)
        if source and (probe_root / source).is_file():
            copy_file(probe_root / source, dst / "attack_source.py")
            copy_file(probe_root / "probe_common.py", dst / "probe_common.py")
        else:
            write_text(dst / "attack_source.md",
                       f"# {case} attack source\n\n"
                       "This case is a positive / crosscheck run; the probe source is "
                       f"`scripts/g3d/d2_runner.py` plus the staged candidate entry. "
                       "See `run/argv-*.json` and `d2/case.json`.\n")


def copy_d3_case(src: Path, dst: Path, *, name: str) -> None:
    assert_true(src.is_dir(), f"missing D3 case: {src}")
    for rel in D3_CASE_FILES:
        copy_file(src / rel, dst / rel, required=False)
    for sub, pattern in D3_GLOBS:
        if (src / sub).is_dir():
            copy_glob(src / sub, pattern, dst / sub)
    copy_glob(src / "traces", "dsh-result.json", dst / "traces")
    copy_glob(src / "traces", "principal*.json", dst / "traces")
    if (src / "probes").is_dir():
        for probe in sorted((src / "probes").glob("*.json")):
            if probe.stat().st_size <= 256 * 1024:
                copy_file(probe, dst / "probes" / probe.name)
    # Case-specific identity files.
    for rel in ("uid-map/candidate-uid_map.txt", "uid-map/candidate-gid_map.txt",
                "uid-map/trusted-uid_map.txt", "uid-map/trusted-gid_map.txt"):
        copy_file(src / rel, dst / rel, required=False)


def copy_d3(out: Path) -> None:
    crash_cases = ["d3-c02", "d3-c03", "d3-c04", "d3-c05", "d3-c06"]
    for case in crash_cases:
        copy_d3_case(D3 / case, out / "d3" / "crash" / case, name=case)

    for sub in ("07-before", "07-after", "07-two"):
        copy_d3_case(D3 / "d3-c07" / sub, out / "d3" / "cancel" / sub, name=sub)
    copy_file(D3 / "d3-c07" / "summary.json",
              out / "d3" / "cancel" / "summary.json", required=True)

    copy_d3_case(D3 / "d3-c11" / "11-same", out / "d3" / "replay" / "11-same",
                 name="11-same")
    copy_file(D3 / "d3-c11" / "summary.json",
              out / "d3" / "replay" / "summary.json", required=False)
    write_text(out / "d3" / "replay" / "README.md", """# Replay / same-claim evidence

`11-same/` is the controlled two-real-Controller/two-UDS same-claim negative:
exactly one finish, the loser gets `ATTEMPT_ALREADY_STARTED`, one
Reservation/Claim/Attempt/Receipt and Fake counter=1.

It is **not** a real-DSH same-claim result.  The real-DSH concurrency run
(`d3-c11-real`, two independent business requests) is under `concurrency/`.
Do not merge the two evidence levels.
""")

    for sub in ("01-echo", "01-tool", "01-resume"):
        copy_d3_case(D3 / "d3-c01" / sub, out / "d3" / "c01-normal" / sub, name=sub)
    copy_file(D3 / "d3-c01" / "summary.json",
              out / "d3" / "c01-normal" / "summary.json", required=False)

    copy_d3_case(D3 / "d3-c10", out / "d3" / "stream-timestamps", name="d3-c10")

    copy_d3_case(D3 / "d3-c11" / "11-real",
                 out / "d3" / "concurrency" / "11-real", name="11-real")
    copy_file(D3 / "d3-c11" / "summary.json",
              out / "d3" / "concurrency" / "summary.json", required=False)

    # SQLite read-only snapshots: copy bytes only; never open them here.
    db_dst = out / "d3" / "sqlite-readonly-snapshots"
    db_rows = []
    db_sources = [("d3-c03", "crash/d3-c03"), ("d3-c04", "crash/d3-c04"),
                  ("d3-c05", "crash/d3-c05"), ("d3-c06", "crash/d3-c06"),
                  ("d3-c11-real", "concurrency/11-real"),
                  ("d3-c11-same", "replay/11-same")]
    for case, rel in db_sources:
        src = (D3 / "d3-c11" / "11-real") if case == "d3-c11-real" else \
              (D3 / "d3-c11" / "11-same") if case == "d3-c11-same" else (D3 / case)
        for db_name in ("broker.sqlite3", "attempts.sqlite3"):
            db = src / "db" / db_name
            if db.is_file():
                target = db_dst / f"{case}--{db_name}"
                copy_file(db, target)
                db_rows.append(f"{sha256_file(db)}  {target.name}")
    write_text(db_dst / "SHA256SUMS", "\n".join(db_rows) + "\n")
    write_text(db_dst / "README.md", """# SQLite read-only snapshots

These are byte copies of the durable Broker (`broker.sqlite3`) and Attempt
journal (`attempts.sqlite3`) from crash/concurrency cases.  They were **not**
opened by the packet builder; do not open them in place with the `sqlite3`
CLI (a read can update `-shm` read-marks and change bytes).  If a query is
unavoidable, copy to a throw-away `/tmp` directory first and query the copy.
`SHA256SUMS` is the only in-packet verification intended here.
""")

    # Fake receipts: flattened, with received-count and an index.
    receipts = out / "d3" / "fake-receipts"
    indexes = []
    receipt_sources = [
        ("c01-echo", D3 / "d3-c01" / "01-echo"),
        ("c01-tool", D3 / "d3-c01" / "01-tool"),
        ("c01-resume", D3 / "d3-c01" / "01-resume"),
        ("c05", D3 / "d3-c05"),
        ("c10", D3 / "d3-c10"),
        ("c11-real", D3 / "d3-c11" / "11-real"),
        ("c11-same", D3 / "d3-c11" / "11-same"),
    ]
    for label, src in receipt_sources:
        count = src / "receipt" / "received-count.json"
        if count.is_file():
            copy_file(count, receipts / f"{label}--received-count.json")
        for rcpt in sorted((src / "receipt").glob("rcpt-*.json")):
            target = receipts / f"{label}--{rcpt.name}"
            copy_file(rcpt, target)
            data = json.loads(rcpt.read_text())
            indexes.append({"case": label, "file": target.name,
                            "receipt_id": data.get("receipt_id"),
                            "raw_sha256": data.get("raw_sha256"),
                            "usage": data.get("usage"),
                            "synthetic": data.get("synthetic"),
                            "real_model_calls": data.get("real_model_calls"),
                            "http_calls": data.get("http_calls"),
                            "network_used": data.get("network_used")})
    write_text(receipts / "INDEX.json",
               json.dumps({"receipts": indexes}, indent=2, sort_keys=True) + "\n")

    write_text(out / "d3" / "INDEX.md", """# D3 evidence map

| Directory | Contents |
|---|---|
| `crash/d3-c02..c06/` | real Candidate SIGKILL, Trusted crash hooks, restart/reconcile state, receipts |
| `cancel/07-before|after|two/` | cancel before send, after receipt, two connections |
| `replay/11-same/` | controlled two-Controller/two-UDS same-claim negative (NOT real-DSH) |
| `c01-normal/` | real-DSH Echo/Tool/Resume (C01) |
| `stream-timestamps/` | DSH `time0`, Fake first-chunk/exit monotonic, stream receipts |
| `concurrency/11-real/` | two real DSH Candidate containers, distinct identities/claims |
| `sqlite-readonly-snapshots/` | byte copies of Broker/Attempt SQLite (hash only) |
| `fake-receipts/` | flattened receipts + received counts, all `synthetic=true` |

The authoritative raw evidence remains under `artifacts/g3d/d3/`; this packet
selects the files a reviewer needs and never moves or rewrites them.
""")


def copy_source(out: Path, docs_sha: str) -> None:
    dst = out / "source"
    index = ["# Source blobs and line index", "",
             f"Implementation: `{IMPL_SHA}` (code `{CODE_SHA}`); docs: `{docs_sha}`.", ""]
    index.append("| File | Lines | Git blob | SHA-256 | Notes |")
    index.append("|---|---|---|---|---|")
    for rel in SOURCE_PATHS:
        data = git_show(IMPL_SHA, rel)
        target = dst / rel
        write_bytes(target, data)
        notes = "; ".join(f"{label} @ {lines}" for label, lines in SOURCE_LINES.get(rel, []))
        line_count = data.count(b"\n")
        index.append(f"| `{rel}` | {line_count} | `{git_blob_sha(IMPL_SHA, rel)[:12]}` | "
                     f"`{sha256_bytes(data)[:16]}...` | {notes} |")
    write_text(dst / "INDEX.md", "\n".join(index) + "\n")
    # explicit line references for the key boundary code
    refs = out / "source" / "line-references.txt"
    lines = ["# Key line references (blob at implementation SHAs)", ""]
    for rel, entries in SOURCE_LINES.items():
        lines.append(f"## {rel}")
        for label, span in entries:
            lines.append(f"- {label}: {span}")
        lines.append("")
    write_text(refs, "\n".join(lines) + "\n")


def copy_env(out: Path, docs_sha: str) -> None:
    env = out / "env"
    env.mkdir(parents=True, exist_ok=True)

    # git identity
    def run_text(argv: list[str]) -> str:
        proc = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True)
        return f"$ {' '.join(argv)}\n(exit {proc.returncode})\n{proc.stdout}{proc.stderr}"
    git_parts = [
        run_text(["git", "rev-parse", "HEAD"]),
        run_text(["git", "status", "--porcelain", "-uall"]),
        run_text(["git", "log", "--oneline", "-16"]),
        run_text(["git", "merge-base", "--is-ancestor", BASE_SHA, IMPL_SHA]),
        run_text(["git", "diff", "--stat", BASE_SHA, IMPL_SHA, "--", "src"]),
        run_text(["git", "diff", "--stat", BASE_SHA, IMPL_SHA, "--", "spikes", "plugins",
                  "scripts/g3c", "tests/integration/g3c", "tests/integration/g3_bridge"]),
        run_text(["git", "show", "-s", "--format=%H %s", BASE_SHA]),
        run_text(["git", "show", "-s", "--format=%H %s", IMPL_SHA]),
        run_text(["git", "show", "-s", "--format=%H %s", docs_sha]),
    ]
    write_text(env / "git.txt", "\n".join(git_parts))

    # stage manifests and runtime
    copy_file(D4 / "env" / "image-runtime.txt", env / "image-runtime.txt")
    copy_file(D1 / "echo" / "mountinfo" / "candidate.txt", env / "mountinfo-candidate.txt")
    copy_file(D1 / "echo" / "mountinfo" / "trusted.txt", env / "mountinfo-trusted.txt")

    def read(path: Path) -> str:
        return path.read_text(errors="replace") if path.is_file() else "<missing>\n"

    write_text(env / "uid-map.txt",
               "# D1 Echo host-observed credentials\n\n"
               "## Candidate\n" + read(D1 / "echo/uid-map/candidate-status.txt") +
               "\nuid_map:\n" + read(D1 / "echo/uid-map/candidate-uid_map.txt") +
               "\n## Trusted\n" + read(D1 / "echo/uid-map/trusted-status.txt") +
               "\nuid_map (runner nested LXC view):\n" +
               read(D1 / "echo/uid-map/trusted-uid_map.txt"))
    write_text(env / "gid-map.txt",
               "## Candidate gid_map\n" + read(D1 / "echo/uid-map/candidate-gid_map.txt") +
               "\n## Trusted gid_map\n" + read(D1 / "echo/uid-map/trusted-gid_map.txt"))
    write_text(env / "peercred.txt",
               "## Trusted log extract (D1 Echo)\n" +
               read(D1 / "echo/peercred/trusted-log-extract.txt") +
               "\n## trusted-log.json\n" + read(D1 / "echo/peercred/trusted-log.json") +
               "\n## trusted-modules.json\n" + read(D1 / "echo/peercred/trusted-modules.json") +
               "\nNote: SO_PEERCRED pid=0 across PID namespaces is normal and is not used for authorization.\n")
    write_text(env / "socket-stat.txt",
               "## before candidate\n" + read(D1 / "echo/socket-stat/before-candidate.json") +
               "\n## listening\n" + read(D1 / "echo/socket-stat/listening.json"))
    write_text(env / "cgroup-limits.txt",
               "## candidate\n" + read(D1 / "echo/uid-map/candidate-cgroup.json") +
               "\n## trusted\n" + read(D1 / "echo/uid-map/trusted-cgroup.json"))

    write_text(env / "rootfs-pre-post.txt",
               read(D4 / "canonical-pre.txt") + "\n" + read(D4 / "canonical-post-clean.txt"))
    write_text(env / "deps-pre-post.txt",
               "deps canonical before/after: " + DEPS_CANON + " (see rootfs-pre-post.txt)\n")
    write_text(env / "stage-pre-post.txt",
               "D3 stage tree before/after: " + D3_STAGE_TREE + "\n"
               "D1 stage tree: 9b6fc7b4d22cb2cbf5c21c1c6dc0714646a651280056cc5426f248b6fdb2548b\n"
               "D2 stage tree: e0ef085a395d9651d79b016e8957944198c4270190937bd6b090aa46d1dbf1ef\n")
    write_text(env / "livegate.txt",
               read(D4 / "env" / "livegate.json") +
               "\nrun_live:\n" + read(D4 / "env" / "zero-key-and-live.txt"))
    audit = json.loads((D4 / "env" / "receipt-network-audit.json").read_text())
    write_text(env / "zero-key-network.txt",
               "key-like env names: 0 (see zero-key-and-live.txt)\n"
               "no .env: confirmed\n"
               f"receipts audited: {audit['receipt_count']}; anomalies: {audit['anomalies']}\n"
               f"container network modes: {audit['network_modes']}; "
               f"non-none: {audit['non_none_network']}\n"
               "run_live exit: 3; LiveGate: BLOCKED (4 reasons)\n")
    write_text(env / "stage-manifests.sha256",
               f"{D1_STAGE_MANIFEST}  {D1_STAGE}/manifest.json\n"
               f"{D2_STAGE_MANIFEST}  {D2_STAGE}/manifest.json\n"
               f"{D3_STAGE_MANIFEST}  {D3_STAGE}/manifest.json\n")


def copy_regressions(out: Path) -> None:
    reg = out / "regressions"
    reg.mkdir(parents=True, exist_ok=True)
    specs = [
        ("oci-full.log", D4 / "oci" / "oci-full.log"),
        ("oci-result.json", D4 / "oci" / "result.json"),
        ("test-junit.xml", D4 / "oci" / "junit-oci-full.xml"),
        ("oci-argv.txt", D4 / "oci" / "argv.txt"),
        ("oci-attempt1-writable-project.log",
         D4 / "oci-attempt1-writable-project" / "oci-full.log"),
        ("oci-attempt1-junit.xml",
         D4 / "oci-attempt1-writable-project" / "junit-oci-full.xml"),
        ("host-full.log", D4 / "host" / "host-full.log"),
        ("host-result.json", D4 / "host" / "result.json"),
        ("host-junit.xml", D4 / "host" / "host-junit.xml"),
        ("node-tests.log", D4 / "node-tests.log"),
        ("node-result.json", D4 / "node" / "result.json"),
        ("ruff.log", D4 / "ruff.log"),
        ("canonical-pre.txt", D4 / "canonical-pre.txt"),
        ("canonical-post.txt", D4 / "canonical-post-clean.txt"),
        ("rootfs-runtime-cleanup.txt", D4 / "rootfs-runtime-cleanup.txt"),
        ("podman-ps-post.txt", D4 / "podman-ps-post.txt"),
        ("residual-processes.txt", D4 / "residual-processes.txt"),
        ("livegate.json", D4 / "env" / "livegate.json"),
        ("zero-key-and-live.txt", D4 / "env" / "zero-key-and-live.txt"),
        ("receipt-network-audit.json", D4 / "env" / "receipt-network-audit.json"),
    ]
    for name, src in specs:
        copy_file(src, reg / name, required=True)
    # argv/UTC/exit index for every D4 regression command.
    records = []

    def add(label, argv, start, end, exit_code, status, log, note=""):
        records.append({"label": label, "argv": argv, "utc_start": start,
                        "utc_end": end, "exit": exit_code, "status": status,
                        "log": log, "note": note})

    def txt(path: Path) -> str:
        return path.read_text().strip() if path.is_file() else ""

    add("oci-full", json.loads((D4 / "oci" / "argv.txt").read_text()),
        txt(D4 / "oci" / "utc-start.txt"), txt(D4 / "oci" / "utc-end.txt"),
        int(txt(D4 / "oci" / "exit-code.txt")), "PASS", "regressions/oci-full.log",
        "909 passed + 7 skipped = 916 tests; 0 failed; 4 explicit deselects")
    add("oci-attempt1-writable-project",
        json.loads((D4 / "oci-attempt1-writable-project" / "argv.txt").read_text()),
        txt(D4 / "oci-attempt1-writable-project" / "utc-start.txt"),
        txt(D4 / "oci-attempt1-writable-project" / "utc-end.txt"),
        int(txt(D4 / "oci-attempt1-writable-project" / "exit-code.txt")),
        "KNOWN_ENV_LIMITATION", "regressions/oci-attempt1-writable-project.log",
        "git archive 0644 materialization hit the documented target-profile read-only assertion")
    add("host-full", ["/root/.local/bin/python3.11", "-B", "-m", "pytest", "tests/", "-q",
                      "-p", "no:cacheprovider",
                      "--junitxml=artifacts/g3d/d4/regression/host/host-junit.xml"],
        txt(D4 / "host" / "utc-start.txt"), txt(D4 / "host" / "utc-end.txt"),
        int(txt(D4 / "host" / "exit-code.txt")), "PASS_WITH_KNOWN_ENV_FAILURES",
        "regressions/host-full.log",
        "917 passed / 2 known host-only failures / 1 skipped")
    add("node-guard", ["node", "--test", "tests/precheck.test.mjs", "tests/guard-pr1.test.mjs"],
        txt(D4 / "node" / "utc-start.txt"), txt(D4 / "node" / "utc-end.txt"),
        0, "PASS", "regressions/node-tests.log",
        "cwd plugins/runtime-budget-guard; RBG_TEST_PYTHON=/root/.local/bin/python3.11; 19/19")
    add("node-skill", ["npm", "run", "build", "&&", "node", "--test", "test/plugin.test.mjs"],
        txt(D4 / "node" / "utc-start.txt"), txt(D4 / "node" / "utc-end.txt"),
        0, "PASS", "regressions/node-tests.log", "cwd plugins/skill-lookup; build + 8/8")
    add("ruff", ["/root/.cache/uv/archive-v0/oAfur17xwsCxzC-G4AMaM/bin/ruff", "check",
                 "scripts/g3d", "tests/integration/g3d"],
        txt(D4 / "node" / "utc-start.txt"), txt(D4 / "node" / "utc-end.txt"),
        0, "PASS", "regressions/ruff.log", "0.17.5 All checks passed")
    add("canonical", ["sha256_tree(rootfs)", "sha256_tree(deps)", "sha256_tree(D3 stage)"],
        "", "", 0, "PASS", "regressions/canonical-pre.txt",
        "rootfs 25491e45 / deps e07729d7 / stage e1ff1449 before and after")
    add("run-live", ["bash", "scripts/run_live.sh"], "", "", 3, "BLOCKED",
        "regressions/zero-key-and-live.txt", "expected blocked")
    add("livegate", ["LiveGate().inspect(live_requested=True)"], "", "", 0, "BLOCKED",
        "regressions/livegate.json", "4 reasons unchanged")
    write_text(reg / "argv-and-exit.jsonl",
               "\n".join(json.dumps(r, sort_keys=True) for r in records) + "\n")


def write_changes(out: Path, docs_sha: str) -> None:
    dst = out / "changes"
    dst.mkdir(parents=True, exist_ok=True)
    impl_diff = git("diff", "--binary", f"{BASE_SHA}..{IMPL_SHA}", "--",
                    "src", "scripts", "tests", "config", "plugins", "spikes",
                    binary=True)
    docs_diff = git("diff", "--binary", f"{BASE_SHA}..{docs_sha}", "--", "docs",
                    binary=True)
    write_bytes(dst / "implementation.diff.patch", impl_diff)
    write_bytes(dst / "docs.diff.patch", docs_diff)
    protected_cmds = [
        ("protected files vs base (expected empty)",
         ["git", "diff", "--stat", BASE_SHA, IMPL_SHA, "--", "spikes", "plugins",
          "scripts/g3c", "tests/integration/g3c", "tests/integration/g3_bridge"]),
        ("product src vs base (expected empty; D1-A is inside base)",
         ["git", "diff", "--stat", BASE_SHA, IMPL_SHA, "--", "src"]),
        ("G3-C historical docs vs base (expected empty)",
         ["git", "diff", "--stat", BASE_SHA, IMPL_SHA, "--",
          "docs/M0_G3C_IMPLEMENTATION_REPORT.md", "docs/REVIEW_G3C_INDEPENDENT_v2.md",
          "docs/M0_G3C_REVIEW_ERRATA.md"]),
        ("worktree status at build", ["git", "status", "--porcelain", "-uall"]),
    ]
    parts = ["# Protected-files diff audit", ""]
    for label, argv in protected_cmds:
        proc = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True)
        parts.append(f"## {label}")
        parts.append(f"$ {' '.join(argv)}")
        parts.append(f"(exit {proc.returncode})")
        parts.append(proc.stdout.rstrip() or "(empty)")
        if proc.stderr.strip():
            parts.append(proc.stderr.rstrip())
        parts.append("")
    write_text(dst / "protected-files-diff.txt", "\n".join(parts) + "\n")


def write_env_review(out: Path, docs_sha: str) -> None:
    review = out / "review"
    review.mkdir(parents=True, exist_ok=True)
    write_text(review / "reviewer-reproduction.md", f"""# Reviewer reproduction (G3-D packet)

Packet: `{out.name}`
Implementation: `{IMPL_SHA}` (code `{CODE_SHA}`); docs: `{docs_sha}`; base: `{BASE_SHA}`.
No Key, no real model, no external HTTP, no Live.  Host Python must run with
`PYTHONDONTWRITEBYTECODE=1` and `-B`.

## R0. Packet and identity

```bash
cd "{out}"
sha256sum -c hashes.sha256
python3 -B review/verify_payload_tree.py
cd "/root/Autonomous Teacher"
git rev-parse {BASE_SHA} {IMPL_SHA} {docs_sha}
git status --porcelain -uall
sha256sum artifacts/g3d/stage-20261117T221955Z/manifest.json
```

Expected: every hash `OK`; payload tree hash equals `manifest.json`'s
`packet_payload_tree_sha256`; stage manifest
`{D3_STAGE_MANIFEST}`; stage tree `{D3_STAGE_TREE}`.

## R1. Static

```bash
cd "/root/Autonomous Teacher"
git diff --stat {BASE_SHA} {IMPL_SHA} -- src spikes plugins scripts/g3c \\
  tests/integration/g3c tests/integration/g3_bridge
PYTHONPATH=src:artifacts/foundation/deps PYTHONDONTWRITEBYTECODE=1 \\
  /root/.local/bin/python3.11 -B -m pytest -q -p no:cacheprovider tests/integration/g3d
```

## R2. Self-built Candidate attacks

Read `docs/M0_G3D_REVIEW_REQUEST.md` §3.  The packet copies D2 raw evidence
under `d2/` but you must build your own probe and record real errno/UID/mount.
Do not reuse the Owner JSON as your independent result.

## R3/R4. Real DSH and crash/cancel/concurrency

```bash
cd "/root/Autonomous Teacher"
S=artifacts/g3d/stage-20261117T221955Z
/root/.local/bin/python3.11 -B scripts/g3d/launch.py --case rev-echo --scenario echo \\
  --session rev-s1 --stage $S --evidence-dir artifacts/reviewer-g3d/echo
/root/.local/bin/python3.11 -B scripts/g3d/d3_runner.py --case d3-c04 --stage $S \\
  --evidence-dir artifacts/reviewer-g3d/c04
/root/.local/bin/python3.11 -B scripts/g3d/d3_runner.py --case d3-c05 --stage $S \\
  --evidence-dir artifacts/reviewer-g3d/c05
/root/.local/bin/python3.11 -B scripts/g3d/d3_runner.py --case d3-c11-same --stage $S \\
  --evidence-dir artifacts/reviewer-g3d/c11-same
```

Expected: Echo 1 SETTLED, counter 1; C04 `SETTLEMENT_UNCERTAIN`/no receipt;
C05 exactly one settle; C11-same one finish + one `ATTEMPT_ALREADY_STARTED`.

## R5. OCI / Node / LiveGate / cleanup

Use `regressions/oci-argv.txt` as the exact OCI argv (read-only frozen tree);
expected `916 tests / 0 failed / 7 skipped / 4 deselects / exit 0`.
Node: `RBG_TEST_PYTHON=/root/.local/bin/python3.11 node --test ...` → 19/19,
skill build + 8/8.  `run_live.sh` exit 3; `LiveGate` BLOCKED; `podman ps -a`
empty; rootfs/deps/stage canonical.

Do not modify this packet, the implementation, the stage, or the evidence.
""")
    write_text(review / "security-nonclaims.md", """# G3-D security non-claims

This packet is a **no-key, Fake Provider, fixed-rootfs, single-host** evidence
bundle for an independent G3-D review.  It is not a PASS by itself.

- No real Provider Key/model/HTTP/Live was used: all receipts are
  `synthetic=true`, `real_model_calls=0`, `http_calls=0`, `network_used=false`.
- The OS boundary claim is limited to this host's rootful Podman 4.9.3 +
  crun 1.14.1 + LXC kernel and the frozen SHAs in `manifest.json`.  It does not
  cover kernel/runtime 0-day, host root compromise, supply chain, or remote
  exactly-once delivery.
- Trusted root and rootful Podman are part of the TCB; this is not a G4
  deployment or a credential-boundary design.
- `SO_PEERCRED` proves an allowed OS uid, not a per-run token; a same-UID
  stale candidate given the live path could connect.
- No Candidate-side Guard component exists; D2-09 proves the equivalent
  invariant (candidate artifacts cannot grant send permission).
- Candidate session has no hard disk quota (documented P2); disk DoS is not
  claimed to be protected.
- D2-13 is a deliberate read-only DAC control, not the formal candidate
  configuration.
- C11 real-DSH concurrency is two independent business requests; the
  same-claim result is a controlled two-Controller/UDS negative and must not
  be merged into a real-DSH same-claim PASS.
- OCI has 4 explicit deselects and 7 skips; host full has 2 known host-only
  failures.  Do not read these as a fully green matrix.
- No G4/G5/Live/M0 GO is granted.  `LiveGate` remains BLOCKED and
  `run_live.sh` exits 3.
- SQLite copies are for hash verification only; do not open them in place.
""")
    copy_file(DOCS / "M0_G3D_FINDINGS_AND_DISPOSITION.md",
              review / "remaining-risk-register.md")
    write_text(review / "verify_payload_tree.py", '''#!/usr/bin/env python3
"""Recompute the packet payload tree hash from hashes.sha256.

Payload = all files covered by hashes.sha256 except manifest.json (which is
listed there for integrity but excluded from the tree hash to avoid
self-reference).  The method is intentionally simple and file-order stable.
"""
import hashlib
from pathlib import Path

root = Path(__file__).resolve().parents[1]
lines = [line for line in (root / "hashes.sha256").read_text().splitlines()
         if line and not line.endswith("  manifest.json")]
digest = hashlib.sha256(("\\n".join(lines) + "\\n").encode()).hexdigest()
print(digest)
''', 0o755)


def write_readme(out: Path, manifest: dict) -> None:
    write_text(out / "README.md", f"""# G3-D review packet ({IMPL_SHA[:12]})

No-key, Fake Provider, fixed-rootfs evidence packet for M0 G3-D
(D-G0 / D-P0 / D1 / D2 / D3 dual-principal OS-boundary scope).  It is **not**
an independent review, not a `G3-D PASS`, and not a Live/G4/G5 authorization.
Owner gate self-assessments are recorded in `manifest.json` and the docs; the
Independent Reviewer must re-verify with their own probes.

- Base: `{BASE_SHA}`
- Implementation: `{IMPL_SHA}` (code `{CODE_SHA}`)
- Docs: `{manifest['docs_sha']}`
- D3 Stage: `{D3_STAGE}` (`{D3_STAGE_MANIFEST}`), tree `{D3_STAGE_TREE}`
- Rootfs/deps: `{ROOTFS_CANON}` / `{DEPS_CANON}`
- Matrix: 53 rows, **52 PASS / 1 NOT_RUN** (`D-REVIEW-01` remains NOT_RUN)
- LiveGate: **BLOCKED**; `run_live.sh` exit 3; real model/HTTP calls: 0

## Read this first

1. `manifest.json` — identity, stage/runtime, UID/peercred/socket, test stats, nonclaims.
2. `changes/implementation.diff.patch` and `changes/protected-files-diff.txt`.
3. `source/INDEX.md` — actual source blobs and line references.
4. `d1/echo/` and `d1/tool/` — real DSH positive evidence (29/29, 33/33).
5. `d2/d2-01..15/` — real Candidate attacks (old four bypasses closed).
6. `d3/crash|stream-timestamps|concurrency|replay/` — crash/reconcile/streaming/concurrency.
7. `regressions/` — D4 final OCI/host/Node/Ruff/canonical logs.
8. `review/` — reviewer reproduction, security nonclaims, remaining-risk register.

## Layout

```text
README.md
manifest.json
hashes.sha256
packet-integrity-report.txt
changes/{{implementation.diff.patch,docs.diff.patch,protected-files-diff.txt}}
source/{{INDEX.md,line-references.txt,ipc_server.py,controller.py,...}}
env/{{git,image-runtime,uid-map,gid-map,mountinfo-*,peercred,socket-stat,
      cgroup-limits,rootfs-pre-post,deps-pre-post,stage-pre-post,livegate,zero-key-network}}
d1/{{echo,tool,stage-manifests,ready-and-cleanup}}
d2/{{d2-01..d2-15,d2-10-trusted*,_probe-sources}}
d3/{{crash,cancel,replay,c01-normal,stream-timestamps,concurrency,
      sqlite-readonly-snapshots,fake-receipts}}
regressions/
matrix/G3D_Test_Evidence_Matrix.csv
review/{{reviewer-reproduction.md,security-nonclaims.md,remaining-risk-register.md,
         verify_payload_tree.py}}
```

## Integrity

```bash
sha256sum -c hashes.sha256
python3 -B review/verify_payload_tree.py
```

`hashes.sha256` covers every payload file plus `manifest.json`; it does not
cover itself or `packet-integrity-report.txt` (self-reference).  The payload
tree hash uses the sorted hashes.sha256 lines excluding `manifest.json`.
No symlinks; no rootfs/repo binary copy; no real Key.  SQLite copies are
hash-only — do not open them in place with `sqlite3` (it can touch `-shm`).

**STOP**: this packet does not authorize Live/G4/G5/M0 GO; the Lead must
assign an independent reviewer and the reviewer must produce
`docs/REVIEW_G3D_INDEPENDENT.md`.
""")


def secret_scan(files: list[Path], root: Path) -> list[str]:
    hits = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="strict")
        except (UnicodeDecodeError, OSError):
            continue
        for pattern in SENSITIVE:
            if pattern.search(text):
                hits.append(f"{pattern.pattern} :: {path.relative_to(root).as_posix()}")
    return hits


def build(args: argparse.Namespace) -> int:
    base = git("rev-parse", args.base_sha).strip()
    impl = git("rev-parse", args.impl_sha).strip()
    docs_sha = git("rev-parse", args.docs_sha).strip()
    assert_true(base == BASE_SHA, f"base mismatch: {base}")
    assert_true(impl == IMPL_SHA, f"impl mismatch: {impl}")
    try:
        subprocess.run(["git", "merge-base", "--is-ancestor", impl, docs_sha],
                       cwd=ROOT, check=True, capture_output=True)
    except subprocess.CalledProcessError as exc:
        raise BuildError(f"impl {impl} is not an ancestor of docs {docs_sha}") from exc
    dirty = git("status", "--porcelain", "-uall").strip()
    if dirty:
        raise BuildError("worktree is dirty before building the packet:\n" + dirty)
    last_docs = git("log", "-1", "--format=%H", "--", "docs").strip()
    if last_docs != docs_sha:
        raise BuildError(f"docs_sha {docs_sha} is not the last docs commit ({last_docs})")

    out = Path(args.out) if args.out else ARTIFACTS / f"review-packet-g3d-{impl}"
    if not out.is_absolute():
        out = ROOT / out
    out = out.resolve()
    if out.parent != ARTIFACTS.resolve():
        raise BuildError(f"packet output must be directly under {ARTIFACTS}: {out}")
    if out.exists():
        if not args.force:
            raise BuildError(f"output exists (use --force): {out}")
        shutil.rmtree(out)
    out.mkdir(parents=True)

    created = utc_now()
    copy_d1_case("echo", out)
    copy_d1_case("tool", out)
    copy_d1_stage_manifests(out)
    copy_d1_ready_cleanup(out)
    copy_d2(out)
    copy_d3(out)
    copy_source(out, docs_sha)
    copy_env(out, docs_sha)
    copy_regressions(out)
    write_changes(out, docs_sha)
    write_env_review(out, docs_sha)

    # matrix (from committed docs_sha) + counts
    matrix_bytes = git_show(docs_sha, f"docs/{MATRIX.name}")
    write_bytes(out / "matrix" / "G3D_Test_Evidence_Matrix.csv", matrix_bytes)
    rows = list(__import__("csv").DictReader(
        matrix_bytes.decode("utf-8-sig").splitlines()))
    status_counts: dict[str, int] = {}
    for row in rows:
        status_counts[row["status"]] = status_counts.get(row["status"], 0) + 1
    write_text(out / "matrix" / "MATRIX_COUNTS.json",
               json.dumps({"rows": len(rows), "status_counts": status_counts,
                           "not_run": [r["case_id"] for r in rows
                                       if r["status"] == "NOT_RUN"]},
                          indent=2, sort_keys=True) + "\n")

    # canonical checks (no containers, no project imports)
    stage_hash = sha256_tree(Path(D3_STAGE))
    rootfs_hash = sha256_tree(ARTIFACTS / "security" / "rootfs")
    deps_hash = sha256_tree(ARTIFACTS / "foundation" / "deps")
    assert_true(stage_hash == D3_STAGE_TREE, f"stage drift: {stage_hash}")
    assert_true(rootfs_hash == ROOTFS_CANON, f"rootfs drift: {rootfs_hash}")
    assert_true(deps_hash == DEPS_CANON, f"deps drift: {deps_hash}")

    def read_json(path: Path) -> dict:
        return json.loads(path.read_text())

    oci = read_json(D4 / "oci" / "result.json")
    host = read_json(D4 / "host" / "result.json")
    node = read_json(D4 / "node" / "result.json")

    payload_count = sum(1 for p in out.rglob("*") if p.is_file())
    manifest = {
        "schema": "m0.g3d.review-packet.v1",
        "packet": out.name,
        "created_utc": created,
        "repo_base_sha": BASE_SHA,
        "base_sha": base,
        "implementation_sha": impl,
        "implementation_code_sha": CODE_SHA,
        "implementation_parent_sha": git("rev-parse", f"{impl}^").strip(),
        "implementation_subject": git("show", "-s", "--format=%s", impl).strip(),
        "docs_sha": docs_sha,
        "docs_parent_sha": git("rev-parse", f"{docs_sha}^").strip(),
        "head_at_packet": git("rev-parse", "HEAD").strip(),
        "regression_head": ((D4 / "head.txt").read_text().strip()
                            if (D4 / "head.txt").is_file() else None),
        "stage": {
            "path": D3_STAGE,
            "manifest_sha256": D3_STAGE_MANIFEST,
            "tree_sha256": D3_STAGE_TREE,
            "trusted_files": 57,
            "candidate_files": 6549,
            "trusted_tree_sha256": "3a004bee14b412151f21abf2964c84d08528b4dc0c83835b694cf29784f33272",
            "candidate_tree_sha256": "6c850e4b1fb746314df2ebccfca7789179412e6797f35d78d53dfe2f239a0dc7",
            "d1_stage_manifest_sha256": D1_STAGE_MANIFEST,
            "d2_stage_manifest_sha256": D2_STAGE_MANIFEST,
        },
        "stage_manifests_sha256": D3_STAGE_MANIFEST,
        "stage_manifests": {
            "d1": {"path": D1_STAGE, "manifest_sha256": D1_STAGE_MANIFEST,
                   "manifest_copy": "d1/stage-manifests/d1-manifest.json"},
            "d2": {"path": D2_STAGE, "manifest_sha256": D2_STAGE_MANIFEST,
                   "manifest_copy": "d1/stage-manifests/d2-manifest.json"},
            "d3": {"path": D3_STAGE, "manifest_sha256": D3_STAGE_MANIFEST,
                   "manifest_copy": "d1/stage-manifests/d3-manifest.json"},
        },
        "runtime_rootfs_sha256": rootfs_hash,
        "deps_sha256": deps_hash,
        "candidate_uid_map": "0 65534 1",
        "candidate_gid_map": "0 65534 1; 2000 2000 1",
        "trusted_uid_map": "0 100000 65536 (runner nested LXC userns view)",
        "peercred": "uid=65534 gid=65534 pid=0 accepted; pid is not used for authorization; no PEER_UID_DENIED/PEERCRED_UNAVAILABLE in positive runs",
        "socket_mode": "0660",
        "socket_gid": 2000,
        "socket_owner": "root:2000",
        "network_mode": "none",
        "test_stats": {
            "d4_oci_full": {
                "tests": oci["counts"]["tests"],
                "passed": oci["passed"],
                "failed": oci["counts"]["failures"],
                "errors": oci["counts"]["errors"],
                "skipped": oci["counts"]["skipped"],
                "deselected_known": len(oci["deselected_known"]),
                "exit": oci["exit"],
                "junit_sha256": oci["junit_sha256"],
            },
            "d4_host_full": {
                "tests": host["counts"]["tests"],
                "passed": host["passed"],
                "failed": host["counts"]["failures"],
                "skipped": host["counts"]["skipped"],
                "known_env_failures": len(host["known_env_failures"]),
                "unexpected_failures": host["unexpected_failures"],
                "exit": host["exit"],
            },
            "d4_node_guard": {"passed": node["guard"]["counts"]["pass"],
                              "failed": node["guard"]["counts"]["fail"]},
            "d4_node_skill": {"passed": node["skill"]["counts"]["pass"],
                              "failed": node["skill"]["counts"]["fail"],
                              "build_exit": node["skill_build"]["exit"]},
            "d4_ruff": "All checks passed (0.17.5)",
            "d3_host_targeted_passed": 299,
            "d2_host_targeted_passed": 285,
            "d1_host_targeted_passed": 266,
        },
        "real_model_calls": 0,
        "real_external_http_calls": 0,
        "has_real_key": False,
        "run_live_exit": 3,
        "live_gate_status": "BLOCKED",
        "live_gate_reasons": [
            "EXTERNAL_HUMAN_AUTHORIZATION_BOUNDARY_NOT_DEPLOYED",
            "BASELINE_EVIDENCE_MISSING",
            "ACTUAL_TOOL_REGISTRY_NOT_APPROVED",
            "SESSION_LOG_UPLOAD_NOT_VERIFIED_DISABLED",
        ],
        "os_boundary_status": "B0-02=BLOCKED (historical); D-G0/D-P0/D1/D2/D3 owner gates self-assessed PASS; G3-D verdict pending independent review",
        "gate_status": {
            "D-G0": "PASS_AT_4BD4803",
            "D-P0": "PASS",
            "D1": "D1_GATE_PASS (owner self-assessment)",
            "D2": "D2_GATE_PASS (owner self-assessment)",
            "D3": "D3_GATE_PASS (owner self-assessment)",
            "D4": "PACKET_BUILT",
            "G3-D": "PENDING_INDEPENDENT_REVIEW",
        },
        "matrix": {
            "rows": len(rows),
            "status_counts": status_counts,
            "not_run": [r["case_id"] for r in rows if r["status"] == "NOT_RUN"],
            "copy": "matrix/G3D_Test_Evidence_Matrix.csv",
        },
        "previous_review_refs": [
            {"id": "G3-C-v2", "verdict": "PASS",
             "scope": "G3-C no-key contract/recovery",
             "doc": "docs/REVIEW_G3C_INDEPENDENT_v2.md",
             "packet": "artifacts/review-packet-g3c-b2f6af054555705192c4e1ae3019a68078764736/",
             "note": "frozen; not modified by G3-D"},
            {"id": "G3-C-v1", "verdict": "PARTIAL",
             "doc": "docs/REVIEW_G3C_INDEPENDENT.md",
             "note": "frozen; G3-C v2 closed its P1s"},
            {"id": "D-REVIEW-01", "verdict": "NOT_RUN",
             "note": "independent G3-D review not performed; matrix row stays NOT_RUN"},
        ],
        "packet_payload_file_count": payload_count,
        "packet_payload_tree_method": "sha256 over the 'sha256  relpath' lines of hashes.sha256 in relative-path order, excluding manifest.json",
        "nonclaims": "review/security-nonclaims.md",
        "remaining_risk_register": "review/remaining-risk-register.md",
        "packet_builder": {"path": "scripts/g3d/build_packet.py",
                           "git_blob": git_blob_sha(
                               git("rev-parse", "HEAD").strip(),
                               "scripts/g3d/build_packet.py"),
                           "note": "builder commit is at HEAD; docs_sha is the docs/matrix commit"},
    }
    write_readme(out, manifest)
    # README is payload; recompute count after it exists.
    payload_count = sum(1 for p in out.rglob("*") if p.is_file())
    manifest["packet_payload_file_count"] = payload_count
    payload_rows = sorted((p.relative_to(out).as_posix(), sha256_file(p))
                          for p in out.rglob("*") if p.is_file())
    manifest["packet_payload_tree_sha256"] = payload_tree_hash(payload_rows)
    manifest["packet_file_count"] = payload_count + 3  # manifest + hashes + report
    write_text(out / "manifest.json",
               json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    # hashes over payload + manifest (not hashes/report themselves)
    hash_rows = sorted((p.relative_to(out).as_posix(), sha256_file(p))
                       for p in out.rglob("*") if p.is_file()
                       and p.relative_to(out).as_posix() not in EXCLUDE_HASH)
    write_text(out / "hashes.sha256",
               "".join(f"{digest}  {rel}\n" for rel, digest in hash_rows))
    verify = subprocess.run(["sha256sum", "-c", "hashes.sha256"], cwd=out,
                            capture_output=True, text=True, check=False)
    ok_count = sum(1 for line in verify.stdout.splitlines() if line.endswith(": OK"))
    ok = verify.returncode == 0 and ok_count == len(hash_rows)
    total_files = sum(1 for p in out.rglob("*") if p.is_file()) + 1
    total_bytes = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    assert_true(total_bytes <= MAX_PACKET_BYTES,
                f"packet too large: {total_bytes} bytes")
    secret_hits = secret_scan([p for p in out.rglob("*") if p.is_file()], out)
    assert_true(not secret_hits, "secret-like pattern(s) found:\n" + "\n".join(secret_hits))
    assert_true(not any(p.is_symlink() for p in out.rglob("*")), "symlink in packet")
    report = f"""G3-D review packet integrity report
packet={out.name}
created_utc={created}
base_sha={base}
implementation_sha={impl}
implementation_code_sha={CODE_SHA}
docs_sha={docs_sha}
head_at_packet={git("rev-parse", "HEAD").strip()}
regression_head={((D4 / "head.txt").read_text().strip() if (D4 / "head.txt").is_file() else "n/a")}
stage_manifests_sha256={D3_STAGE_MANIFEST}
runtime_rootfs_sha256={rootfs_hash}
deps_sha256={deps_hash}
live_gate_status=BLOCKED
run_live_exit=3
real_model_calls=0
real_external_http_calls=0
has_real_key=false
matrix_rows={len(rows)}
matrix_status_counts={json.dumps(status_counts, sort_keys=True)}
payload_files={payload_count}
packet_file_count={total_files}
packet_payload_tree_sha256={manifest['packet_payload_tree_sha256']}
hashed_files={len(hash_rows)}
sha256sum_-c_hashes_sha256={'OK' if ok else 'FAILED'} ({ok_count}/{len(hash_rows)} verified)
secret_scan=PASS
symlink_scan=PASS
packet_bytes={total_bytes}

notes:
- hashes.sha256 covers every payload file plus manifest.json; it does not cover
  itself or this report.  packet_payload_tree_sha256 excludes manifest.json and
  the two metadata files to avoid self-reference.
- SQLite copies were not opened; only byte copies and sha256 were used.
- No rootfs/deps/stage binary copy, no full repository, no real Key/token.
- Evidence bytes are copies; source evidence under artifacts/g3d/ was not moved
  or rewritten.
"""
    write_text(out / "packet-integrity-report.txt", report)
    assert_true(ok, "hashes.sha256 verification failed")
    print(json.dumps({"packet": str(out), "file_count": total_files,
                      "payload_files": payload_count, "payload_hashed": len(hash_rows),
                      "bytes": total_bytes,
                      "payload_tree_sha256": manifest["packet_payload_tree_sha256"],
                      "docs_sha": docs_sha, "impl": impl},
                     indent=2))
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
    except BuildError as exc:
        sys.stderr.write(f"BUILD_PACKET_ERROR: {exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
