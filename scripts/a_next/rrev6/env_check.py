#!/usr/bin/env python3
"""A-NEXT R-REV6 preflight: identify the frozen environment without running OCI.

Read-only by default:

* worktree/branch/SHA and cleanliness;
* podman version, existing containers/images metadata (no run/pull);
* host node version and the frozen-rootfs node hash/version record;
* DSH SDK/runtime versions and the runtime binary SHA-256;
* frozen rootfs/deps path, size and canonical ``tar --sort=name`` tree hash;
* stage build prerequisites (G3-A/G3-C source stages, plugin node_modules);
* disk free vs the byte budget of the planned working copies;
* prior L2 evidence exists only as *historical reference* (never reused).

Optional ``--copy-test`` copies the frozen rootfs to a scratch directory,
recomputes the canonical hash and deletes the copy: this proves the "writable
copy" procedure before an OCI window without touching the frozen tree.

``--stage-artifacts`` (also no container) copies the frozen inputs needed by the
G4-C stage builder and launchers into this worktree's gitignored ``artifacts/``
tree so the window never depends on another worktree's writable paths.  The
frozen sources themselves are only ever read.

Exit codes: 0 = ready, 3 = blocked (environment/prerequisite problem),
2 = unexpected internal error.  This script never starts a container, never
uses the network and never reads credentials.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

WORKTREE = Path(__file__).resolve().parents[3]
MAIN_REPO = Path("/root/Autonomous Teacher")
# A second, independent copy of the frozen runtime exists in the historical
# G4-F implementation worktree.  The main-repo `artifacts/` tree was observed
# empty on 2026-11-20T19:53Z (external cleanup, not caused by this task), so the
# canonical constants below stay the identity check and this copy is a fallback
# provenance source.  Every candidate is hashed; only a canonical value is used.
FALLBACK_REPO = Path("/root/at-g4f-impl")
ROOTFS_CANDIDATES = (("main", MAIN_REPO / "artifacts" / "security" / "rootfs"),
                     ("g4f-impl", FALLBACK_REPO / "artifacts" / "security" / "rootfs"),
                     ("worktree-staged", WORKTREE / "artifacts" / "security" / "rootfs"))
DEPS_CANDIDATES = (("main", MAIN_REPO / "artifacts" / "foundation" / "deps"),
                   ("g4f-impl", FALLBACK_REPO / "artifacts" / "foundation" / "deps"),
                   ("worktree-staged", WORKTREE / "artifacts" / "foundation" / "deps"))
STAGE_G3A_CANDIDATES = (
    ("worktree-staged", WORKTREE / "artifacts" / "g3a-provider-bridge" / "stage"),
    ("main", MAIN_REPO / "artifacts" / "g3a-provider-bridge" / "stage"),
    ("g4f-impl", FALLBACK_REPO / "artifacts" / "g3a-provider-bridge" / "stage"))
STAGE_G3C_CANDIDATES = (
    ("worktree-staged", WORKTREE / "artifacts" / "g3c" / "stage"),
    ("main", MAIN_REPO / "artifacts" / "g3c" / "stage"),
    ("g4f-impl", FALLBACK_REPO / "artifacts" / "g3c" / "stage"))
PLUGIN_MODULE_CANDIDATES = (
    ("worktree-staged", WORKTREE / "plugins" / "offline-fixture" / "node_modules"),
    ("main", MAIN_REPO / "plugins" / "offline-fixture" / "node_modules"),
    ("g4f-impl", FALLBACK_REPO / "plugins" / "offline-fixture" / "node_modules"))
SOURCE_F5_L2 = MAIN_REPO / "artifacts" / "g4f" / "f5" / "l2"
SOURCE_F2_L2 = MAIN_REPO / "artifacts" / "g4f" / "f2"

ROOTFS_CANON = "25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0"
DEPS_CANON = "e07729d7997944417b1c25531749b3e6e5e34aa4248f01dc8f370282082ecb98"
DSH_RUNTIME_CANON = "1cc41d5a8745a5b9d47c8604e44f23eb8af2d8ca02b2afa0be101d5f71be6ea4"
EXPECTED_DSH_VERSION = "0.2.2-rc.2"
EXPECTED_PODMAN_MAJOR = "4.9"

EXIT_READY = 0
EXIT_INTERNAL = 2
EXIT_BLOCKED = 3


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run(argv: list[str], *, timeout: float = 60.0) -> dict:
    try:
        proc = subprocess.run(argv, capture_output=True, text=True,
                              timeout=timeout)
        return {"argv": argv, "exit": proc.returncode,
                "stdout": proc.stdout.strip(), "stderr": proc.stderr.strip()}
    except FileNotFoundError:
        return {"argv": argv, "exit": -1, "stdout": "", "stderr": "not found"}
    except subprocess.TimeoutExpired:
        return {"argv": argv, "exit": -2, "stdout": "", "stderr": "timeout"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_tree(path: Path) -> str:
    """Frozen canonicalisation recipe: tar --sort=name --mtime=@0 ... | sha256."""
    proc = subprocess.run(
        ["tar", "--sort=name", "--mtime=@0", "--owner=0", "--group=0",
         "--numeric-owner", "-cf", "-", "-C", str(path), "."],
        capture_output=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"tar failed for {path}: {proc.stderr[-300:]!r}")
    return hashlib.sha256(proc.stdout).hexdigest()


def git(*args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=str(WORKTREE), capture_output=True,
                          text=True)
    return proc.stdout.strip() if proc.returncode == 0 else ""


def tree_bytes(path: Path) -> int:
    total = 0
    for dirpath, _dirnames, filenames in os.walk(path, followlinks=False):
        for name in filenames:
            try:
                total += (Path(dirpath) / name).lstat().st_size
            except OSError:
                continue
    return total


def human(size: float) -> str:
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(size) < 1024.0:
            return f"{size:.1f}{unit}"
        size /= 1024.0
    return f"{size:.1f}PiB"


def disk_record() -> dict:
    usage = shutil.disk_usage(str(WORKTREE))
    return {"path": str(WORKTREE), "total_bytes": usage.total,
            "used_bytes": usage.used, "free_bytes": usage.free,
            "free_human": human(usage.free)}


def podman_record() -> dict:
    version = run(["podman", "--version"])
    ps = run(["podman", "ps", "-a", "--format", "{{.Names}}"])
    images = run(["podman", "images", "--format", "{{.Repository}}:{{.Tag}}"])
    running = [line for line in ps["stdout"].splitlines() if line.strip()]
    image_rows = [line for line in images["stdout"].splitlines() if line.strip()]
    version_text = version["stdout"] if version["exit"] == 0 else ""
    return {
        "version": version_text,
        "version_ok": EXPECTED_PODMAN_MAJOR in version_text,
        "containers": running,
        "containers_empty": not running,
        "image_count": len(image_rows),
        "images": image_rows[:20],
        "ps_exit": ps["exit"],
    }


def node_record() -> dict:
    host = run(["node", "--version"])
    rootfs = _first_existing(ROOTFS_CANDIDATES)
    frozen_node = ((rootfs / "usr" / "bin" / "node") if rootfs
                   else Path("/nonexistent"))
    record = {
        "host_version": host["stdout"] if host["exit"] == 0 else None,
        "frozen_path": str(frozen_node),
        "frozen_exists": frozen_node.is_file(),
    }
    if frozen_node.is_file():
        record["frozen_sha256"] = sha256_file(frozen_node)
        frozen = run([str(frozen_node), "--version"])
        record["frozen_version"] = frozen["stdout"] if frozen["exit"] == 0 else None
        record["frozen_run_exit"] = frozen["exit"]
    return record


def dsh_record() -> dict:
    deps = _first_existing(DEPS_CANDIDATES)
    runtime_json = (deps / "deepseek_harness_runtime" / "deepseek-harness-runtime.json"
                    if deps else Path("/nonexistent"))
    runtime_bin = ((deps / "deepseek_harness_runtime" / "runtime" /
                    "deepseek-harness-sdk-runtime-linux-x64") if deps
                   else Path("/nonexistent"))
    versions = {}
    for dist_name in ("deepseek_harness_sdk-0.2.2rc2.dist-info",
                      "deepseek_harness_runtime_bin-0.2.2rc2.dist-info"):
        metadata = deps / dist_name / "METADATA" if deps else Path("/nonexistent")
        if metadata.is_file():
            for line in metadata.read_text(encoding="utf-8").splitlines():
                if line.startswith(("Name:", "Version:")):
                    key, value = line.split(":", 1)
                    versions.setdefault(dist_name, {})[key.strip()] = value.strip()
    runtime_sha = sha256_file(runtime_bin) if runtime_bin.is_file() else None
    adapter_expected = _adapter_expected_js()
    adapter_meta = _adapter_build_meta()
    return {
        "sdk_version": (versions.get("deepseek_harness_sdk-0.2.2rc2.dist-info") or {}).get("Version"),
        "runtime_package": versions.get("deepseek_harness_runtime_bin-0.2.2rc2.dist-info"),
        "runtime_binary": str(runtime_bin),
        "runtime_binary_exists": runtime_bin.is_file(),
        "runtime_json_exists": runtime_json.is_file(),
        "runtime_sha256": runtime_sha,
        "runtime_canonical": runtime_sha == DSH_RUNTIME_CANON,
        "expected_version": EXPECTED_DSH_VERSION,
        "adapter_expected_js_sha256": adapter_expected,
        "adapter_build_meta": adapter_meta,
        "adapter_build_meta_ok": bool(adapter_meta),
    }


def _adapter_expected_js() -> str | None:
    path = WORKTREE / "scripts" / "g3d" / "build_stage.py"
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("ADAPTER_EXPECTED_JS = "):
            return line.split('"')[1] if '"' in line else None
    return None


def _adapter_build_meta() -> dict | None:
    """Locate the newest committed adapter build-meta under artifacts (read only)."""
    root = MAIN_REPO / "artifacts" / "g4" / "c" / "build"
    if not root.is_dir():
        return None
    candidates = sorted(root.glob("adapter-*/bridge/build-meta.json"),
                        key=lambda path: path.stat().st_mtime, reverse=True)
    if not candidates:
        return None
    try:
        document = json.loads(candidates[0].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return {"path": str(candidates[0]),
            "built_js_sha256": (document.get("builtJs") or {}).get("sha256"),
            "dsh_llm_version": document.get("dshLlmVersion")}


def _first_existing(candidates) -> Path | None:
    for _label, path in candidates:
        if path.is_dir():
            return path
    return None


def _scan_candidates(kind: str, candidates) -> dict:
    """Hash every existing provenance candidate (read-only, canonical recipe)."""
    rows = []
    for label, path in candidates:
        if not path.is_dir():
            rows.append({"label": label, "path": str(path), "exists": False,
                         "canonical": False, "sha256": None})
            continue
        started = time.time()
        digest = sha256_tree(path)
        expected = ROOTFS_CANON if kind == "rootfs" else DEPS_CANON
        rows.append({"label": label, "path": str(path), "exists": True,
                     "sha256": digest, "canonical": digest == expected,
                     "hash_seconds": round(time.time() - started, 3)})
    return {"kind": kind, "candidates": rows,
            "canonical_found": any(row["canonical"] for row in rows),
            "selected": next((row for row in rows if row["canonical"]), None)}


def frozen_record() -> dict:
    rootfs_candidates = _scan_candidates("rootfs", ROOTFS_CANDIDATES)
    deps_candidates = _scan_candidates("deps", DEPS_CANDIDATES)
    rootfs_path = Path(rootfs_candidates["selected"]["path"]) if rootfs_candidates["selected"] else None
    deps_path = Path(deps_candidates["selected"]["path"]) if deps_candidates["selected"] else None
    rootfs = {"path": str(rootfs_path) if rootfs_path else None,
              "exists": bool(rootfs_path and rootfs_path.is_dir()),
              "bytes": tree_bytes(rootfs_path) if rootfs_path else 0}
    deps = {"path": str(deps_path) if deps_path else None,
            "exists": bool(deps_path and deps_path.is_dir()),
            "bytes": tree_bytes(deps_path) if deps_path else 0}
    if rootfs_path is not None:
        rootfs["sha256"] = sha256_tree(rootfs_path)
        rootfs["canonical"] = rootfs["sha256"] == ROOTFS_CANON
    if deps_path is not None:
        deps["sha256"] = sha256_tree(deps_path)
        deps["canonical"] = deps["sha256"] == DEPS_CANON
    main_missing = not (MAIN_REPO / "artifacts" / "security" / "rootfs").is_dir()
    return {"rootfs": rootfs, "deps": deps,
            "rootfs_canon": ROOTFS_CANON, "deps_canon": DEPS_CANON,
            "rootfs_size": human(rootfs["bytes"]),
            "deps_size": human(deps["bytes"]),
            "candidates": {"rootfs": rootfs_candidates, "deps": deps_candidates},
            "source_event": {
                "main_frozen_sources_missing": main_missing,
                "detected_utc": utc_now() if main_missing else None,
                "note": ("main-repo artifacts/ was observed empty at "
                         "2026-11-20T19:53Z (external cleanup); canonical "
                         "constants remain the identity check and the staged / "
                         "g4f-impl copies are hashed per candidate")
                if main_missing else None}}


def _describe_source(candidates) -> dict:
    path = _first_existing(candidates)
    return {"path": str(path) if path else None,
            "exists": path is not None,
            "label": next((label for label, candidate in candidates
                           if candidate == path), None),
            "bytes": tree_bytes(path) if path else 0}


def prerequisites_record() -> dict:
    g3a = _describe_source(STAGE_G3A_CANDIDATES)
    g3c = _describe_source(STAGE_G3C_CANDIDATES)
    modules = _describe_source(PLUGIN_MODULE_CANDIDATES)
    spike = WORKTREE / "spikes" / "g3b-trusted-bridge"
    build_script = WORKTREE / "scripts" / "g3c" / "build-adapter.mjs"
    return {"g3a_stage": g3a, "g3c_stage": g3c,
            "plugin_node_modules": modules,
            "spike_source": {"path": str(spike), "exists": spike.is_dir()},
            "adapter_build_script": {"path": str(build_script),
                                     "exists": build_script.is_file()},
            "all_present": all(item.get("exists") for item in
                               (g3a, g3c, modules))
            and spike.is_dir() and build_script.is_file()}


def staging_record() -> dict:
    """Byte budget for making this worktree self-contained for the window."""
    files = [("rootfs", _first_existing(ROOTFS_CANDIDATES),
              "artifacts/security/rootfs"),
             ("deps", _first_existing(DEPS_CANDIDATES),
              "artifacts/foundation/deps"),
             ("g3a_stage", _first_existing(STAGE_G3A_CANDIDATES),
              "artifacts/g3a-provider-bridge/stage"),
             ("g3c_stage", _first_existing(STAGE_G3C_CANDIDATES),
              "artifacts/g3c/stage"),
             ("plugin_node_modules", _first_existing(PLUGIN_MODULE_CANDIDATES),
              "plugins/offline-fixture/node_modules")]
    rows = []
    total = 0
    for name, source, relative in files:
        size = tree_bytes(source) if source is not None and source.is_dir() else 0
        total += size
        rows.append({"name": name,
                     "source": str(source) if source is not None else None,
                     "target": str(WORKTREE / relative),
                     "bytes": size, "human": human(size),
                     "target_exists": (WORKTREE / relative).exists()})
    # The stage build output, one writable rootfs run-copy and one evidence tree.
    stage_bytes = 138 * 1024 * 1024
    run_copy_bytes = 291 * 1024 * 1024
    evidence_bytes = 300 * 1024 * 1024
    peak = total + stage_bytes + run_copy_bytes + evidence_bytes
    return {"rows": rows, "staged_bytes": total, "staged_human": human(total),
            "budget": {"stage_output_bytes": stage_bytes,
                       "rootfs_run_copy_bytes": run_copy_bytes,
                       "evidence_bytes": evidence_bytes,
                       "peak_total_bytes": peak, "peak_total_human": human(peak)},
            "all_targets_staged": all(row["target_exists"] for row in rows)}


def historical_reference() -> dict:
    """Only a timing/format reference; never copied into new evidence."""
    record: dict = {"f5_l2": None, "f2_l2": None, "note":
                    "historical, different Stage/base SHA; never counted as R-REV6 evidence"}
    if SOURCE_F5_L2.is_dir():
        summary = SOURCE_F5_L2 / "summary.json"
        timings = []
        if summary.is_file():
            try:
                document = json.loads(summary.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                document = {}
            for key, case in (document.get("cases") or {}).items():
                case_summary = case.get("summary") or {}
                timings.append({"case": key,
                                "exit": case.get("exit_code"),
                                "utc_start": case_summary.get("utc_start"),
                                "utc_end": case_summary.get("utc_end")})
        record["f5_l2"] = {"root": str(SOURCE_F5_L2),
                           "case_count": len(timings),
                           "runner_utc": [None, None],
                           "cases": timings}
    if SOURCE_F2_L2.is_dir():
        record["f2_l2"] = {"root": str(SOURCE_F2_L2), "exists": True}
    return record


def copy_test() -> dict:
    """Prove that a writable rootfs work copy keeps the canonical hash."""
    source = _first_existing(ROOTFS_CANDIDATES)
    if source is None:
        return {"ok": False, "reason": "no_canonical_rootfs_source"}
    scratch = Path("/tmp") / f"a-next-rrev6-rootfs-copy-{int(time.time())}"
    started = time.time()
    try:
        shutil.copytree(source, scratch, symlinks=True)
        copy_seconds = round(time.time() - started, 2)
        frozen_sha = sha256_tree(source)
        copy_sha = sha256_tree(scratch)
        bytes_copied = tree_bytes(scratch)
        return {"ok": frozen_sha == copy_sha == ROOTFS_CANON,
                "frozen_sha256": frozen_sha, "copy_sha256": copy_sha,
                "copy_seconds": copy_seconds,
                "bytes": bytes_copied, "scratch": str(scratch),
                "frozen_unchanged": frozen_sha == ROOTFS_CANON}
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def stage_artifacts(force: bool = False) -> dict:
    """Copy frozen inputs into the worktree (host-only, gitignored paths)."""
    plan = [("rootfs", _first_existing(ROOTFS_CANDIDATES),
             WORKTREE / "artifacts" / "security" / "rootfs"),
            ("deps", _first_existing(DEPS_CANDIDATES),
             WORKTREE / "artifacts" / "foundation" / "deps"),
            ("g3a_stage", _first_existing(STAGE_G3A_CANDIDATES),
             WORKTREE / "artifacts" / "g3a-provider-bridge" / "stage"),
            ("g3c_stage", _first_existing(STAGE_G3C_CANDIDATES),
             WORKTREE / "artifacts" / "g3c" / "stage"),
            ("plugin_node_modules", _first_existing(PLUGIN_MODULE_CANDIDATES),
             WORKTREE / "plugins" / "offline-fixture" / "node_modules")]
    rows = []
    for name, source, target in plan:
        if source is None:
            rows.append({"name": name, "ok": False, "reason": "source_missing",
                         "source": None})
            continue
        if target.exists() and not force:
            rows.append({"name": name, "ok": True, "action": "already_present",
                         "target": str(target)})
            continue
        if target.exists():
            shutil.rmtree(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        started = time.time()
        shutil.copytree(source, target, symlinks=True)
        rows.append({"name": name, "ok": True, "action": "copied",
                     "target": str(target), "seconds": round(time.time() - started, 2),
                     "bytes": tree_bytes(target)})
    return {"rows": rows, "ok": all(row["ok"] for row in rows)}


def build(worktree: Path = WORKTREE) -> dict:
    record = {
        "schema": "m0.a_next.rrev6.env-check.v1",
        "utc": utc_now(),
        "worktree": str(worktree),
        "git": {"head": git("rev-parse", "HEAD"),
                "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
                "clean": git("status", "--porcelain", "-uall") == "",
                "porcelain": git("status", "--porcelain", "-uall")},
        "main_repo_head": _git_at(MAIN_REPO, "rev-parse", "HEAD"),
        "disk": disk_record(),
        "podman": podman_record(),
        "node": node_record(),
        "dsh": dsh_record(),
        "frozen": frozen_record(),
        "prerequisites": prerequisites_record(),
        "staging": staging_record(),
        "historical_reference": historical_reference(),
        "oci_window_approved": False,
        "real_model_calls": 0,
        "real_external_http_calls": 0,
        "provider_keys_seen": 0,
        "limitations": [
            "L2 evidence is NOT produced by this preflight.",
            "Historical F2/F5 L2 evidence belongs to older Stage/base SHAs and "
            "must never be reused or counted as R-REV6 evidence.",
            "No container is started and no network is used here.",
        ],
    }
    problems = []
    if not record["git"]["clean"]:
        problems.append("worktree_not_clean")
    if not record["podman"]["version_ok"]:
        problems.append("podman_version_unexpected")
    if not record["podman"]["containers_empty"]:
        problems.append("containers_present")
    if not record["frozen"]["rootfs"].get("canonical"):
        problems.append("rootfs_not_canonical")
    if not record["frozen"]["deps"].get("canonical"):
        problems.append("deps_not_canonical")
    if not record["dsh"]["runtime_canonical"]:
        problems.append("dsh_runtime_not_canonical")
    if _normalise_version(record["dsh"]["sdk_version"]) != _normalise_version(
            record["dsh"]["expected_version"]):
        problems.append("dsh_sdk_version_unexpected")
    if not record["prerequisites"]["all_present"]:
        problems.append("stage_build_prerequisites_missing")
    if record["disk"]["free_bytes"] < record["staging"]["budget"]["peak_total_bytes"]:
        problems.append("insufficient_disk_for_peak_budget")
    record["problems"] = problems
    record["ready"] = not problems
    return record


def _normalise_version(value: object) -> str:
    """0.2.2rc2 / 0.2.2-rc.2 / 0.2.2-rc2 all normalise to 0.2.2rc2."""
    if not isinstance(value, str):
        return ""
    return value.replace("-", "").replace("rc.", "rc").replace("rc-", "rc").strip().lower()


def verify_staged() -> dict:
    """Re-hash the staged frozen copies against the canonical values."""
    rootfs = WORKTREE / "artifacts" / "security" / "rootfs"
    deps = WORKTREE / "artifacts" / "foundation" / "deps"
    rows = []
    if rootfs.is_dir():
        digest = sha256_tree(rootfs)
        rows.append({"name": "worktree_rootfs", "path": str(rootfs),
                     "sha256": digest, "canonical": digest == ROOTFS_CANON})
    if deps.is_dir():
        digest = sha256_tree(deps)
        rows.append({"name": "worktree_deps", "path": str(deps),
                     "sha256": digest, "canonical": digest == DEPS_CANON})
    return {"rows": rows, "ok": bool(rows) and all(row["canonical"] for row in rows)}


def _git_at(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=str(repo), capture_output=True,
                          text=True)
    return proc.stdout.strip() if proc.returncode == 0 else ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=None,
                        help="output JSON path (default: artifacts/a_next/rrev6/prep/)")
    parser.add_argument("--copy-test", action="store_true",
                        help="prove the writable rootfs copy procedure (host-only)")
    parser.add_argument("--stage-artifacts", action="store_true",
                        help="copy frozen inputs into this worktree (host-only)")
    parser.add_argument("--force", action="store_true",
                        help="overwrite already staged inputs")
    args = parser.parse_args(argv)
    try:
        record = build()
        if args.copy_test:
            record["copy_test"] = copy_test()
            if not record["copy_test"]["ok"]:
                record["problems"].append("rootfs_copy_test_failed")
                record["ready"] = False
        if args.stage_artifacts:
            staging = stage_artifacts(force=args.force)
            record["stage_artifacts"] = staging
            verification = verify_staged()
            record["stage_artifacts_verification"] = verification
            if not staging["ok"] or not verification["ok"]:
                record["problems"].append("stage_artifacts_failed")
                record["ready"] = False
        out = (Path(args.out) if args.out else
               WORKTREE / "artifacts" / "a_next" / "rrev6" / "prep" /
               f"env-check-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
        summary = {
            "ready": record["ready"],
            "problems": record["problems"],
            "head": record["git"]["head"],
            "rootfs_canonical": record["frozen"]["rootfs"].get("canonical"),
            "deps_canonical": record["frozen"]["deps"].get("canonical"),
            "dsh_runtime_canonical": record["dsh"]["runtime_canonical"],
            "dsh_sdk_version": record["dsh"]["sdk_version"],
            "podman": record["podman"]["version"],
            "node": record["node"].get("frozen_version") or record["node"].get("host_version"),
            "disk_free": record["disk"]["free_human"],
            "staged": record["staging"]["all_targets_staged"],
            "peak_budget": record["staging"]["budget"]["peak_total_human"],
            "copy_test": (record.get("copy_test") or {}).get("ok"),
            "out": str(out),
        }
        print(json.dumps(summary, indent=2, sort_keys=True))
        return EXIT_READY if record["ready"] else EXIT_BLOCKED
    except Exception as exc:  # noqa: BLE001 - preflight must report, not traceback
        sys.stderr.write(f"ENV_CHECK_FAILED {type(exc).__name__}: {exc}\n")
        return EXIT_INTERNAL


if __name__ == "__main__":
    raise SystemExit(main())
