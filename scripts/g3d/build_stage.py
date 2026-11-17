#!/usr/bin/env python3
"""Build the independent G3-D1-B ``trusted`` and ``candidate`` stages.

Design rules (D0 §4, D1 plan §2.4, task brief):

* the product tree comes from ``git archive 4bd4803`` (never the old G3-C
  stage, whose ``src`` is the pre-PR1 ``e6fde1c`` batch);
* the candidate side is an **explicit allow-list** copied file by file, never
  "copy the repo then delete";
* the adapter is rebuilt from the reviewed spike source inside the fixed
  read-only rootfs with ``--network none`` and its output must match the frozen
  G3-C build-meta hash (determinism cross-check);
* a machine-readable manifest records path/sha256/bytes/mode/source/build
  command for every file, and the tree is re-verified before the stage is
  announced;
* the canonical rootfs/deps hashes are asserted before and after.

Only host ``tar``/``sha256``/``podman``/``git``/``cp`` style operations run on
the host; Node/TypeScript compilation runs only inside the fixed rootfs.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tarfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib_g3d as lib  # noqa: E402

G3A_STAGE = lib.ARTIFACTS / "g3a-provider-bridge" / "stage"
G3C_STAGE = lib.ARTIFACTS / "g3c" / "stage"
NPM = lib.REPO_ROOT / "plugins" / "offline-fixture" / "node_modules"
SPIKE = lib.REPO_ROOT / "spikes" / "g3b-trusted-bridge"
BUILDER = lib.REPO_ROOT / "scripts" / "g3c" / "build-adapter.mjs"
CONFIG_ROOT = lib.REPO_ROOT / "config" / "g3d"
STAGE_SRC = lib.REPO_ROOT / "scripts" / "g3d" / "stage"

# Frozen G3-C adapter build output. The spike ``index.ts`` at PRODUCT_BASE is
# byte-identical to the G3-C input, so a deterministic rebuild must reproduce it.
ADAPTER_EXPECTED_JS = "2cb424616b7380bff61f8ce760e229a0c1d2b32c4a5f2954cdf66c3937bf74ba"

PASSWD = """root:x:0:0:root:/root:/bin/sh
nobody:x:65534:65534:nobody:/nonexistent:/usr/sbin/nologin
"""
GROUP = """root:x:0:
nobody:x:65534:
g3d-socket:x:2000:
"""

SKILL_FILES = ("index.js", "index.d.ts", "skills.json", "fixture.sha256")
CANDIDATE_NODE_MODULES_EXCLUDE = (".bin",)
TRUSTED_TEMPLATES = ("controller.template.json", "admission.template.json",
                     "broker.template.json")


def fail(code: int, message: str, **detail: object) -> None:
    raise lib.G3DError(message, exit_code=code, detail=detail)


ROOTFS_TRANSIENT_TARGETS = ("src", "npm", "out", "var", "build-src", "evidence",
                            "seed", "debug")


def cleanup_rootfs_mount_targets(rootfs: Path) -> dict:
    """Remove only empty mount-target dirs crun created for the build mounts.

    The fixed rootfs hash is part of the frozen baseline; ``crun`` materialises
    bind-mount target directories inside ``--rootfs`` when they are absent. This
    helper removes *only* those empty transient directories (G3-C used the same
    recipe) and never touches a non-empty directory.
    """
    removed, kept = [], []
    for name in ROOTFS_TRANSIENT_TARGETS:
        path = rootfs / name
        try:
            if path.is_dir() and not path.is_symlink() and not any(path.iterdir()):
                path.rmdir()
                removed.append(name)
            elif path.exists():
                kept.append(name)
        except OSError:
            kept.append(name)
    resolv = rootfs / "etc" / "resolv.conf"
    try:
        if resolv.is_file() and resolv.stat().st_size == 0:
            resolv.unlink()
            removed.append("etc/resolv.conf")
    except OSError:
        pass
    return {"removed": removed, "kept": kept}


def product_identity(base: str) -> dict:
    head = lib.git_text("rev-parse", "HEAD")
    status = lib.git_text("status", "--porcelain=v1")
    src_diff = lib.git_text("diff", "--stat", base, "--", "src")
    upstream_diff = lib.git_text("diff", "--stat", base, "--", "spikes", "plugins",
                                 "scripts/g3c", "tests/integration/g3c",
                                 "tests/integration/g3_bridge")
    if src_diff:
        fail(lib.EXIT_PREFLIGHT_IDENTITY, "working tree src/ differs from product base",
             base=base, diff=src_diff)
    if upstream_diff:
        fail(lib.EXIT_PREFLIGHT_IDENTITY, "spikes/plugins differ from product base",
             base=base, diff=upstream_diff)
    lib.git_bytes("cat-file", "-e", f"{base}^{{commit}}")
    return {"head": head, "base": base, "status": status,
            "src_identical_to_base": True,
            "spikes_plugins_identical_to_base": True}


def extract_product_files(base: str) -> dict[str, bytes]:
    """Stream ``git archive <base>`` and keep only the trusted package/fake."""
    proc = subprocess.Popen(["git", "archive", "--format=tar", base],
                            cwd=str(lib.REPO_ROOT), stdout=subprocess.PIPE)
    assert proc.stdout is not None
    kept: dict[str, bytes] = {}
    try:
        with tarfile.open(fileobj=proc.stdout, mode="r|") as archive:
            for member in archive:
                name = member.name
                if member.isdir():
                    continue
                if not member.isfile():
                    fail(lib.EXIT_STAGE_INVALID,
                         "git archive contains a non-regular product file",
                         member=name)
                keep = name.startswith("src/autoteacher_m0/") or \
                    name == "spikes/g3b-trusted-bridge/fake/fake_provider.py" or \
                    name == "spikes/g3b-trusted-bridge/src/index.ts"
                if not keep:
                    continue
                handle = archive.extractfile(member)
                if handle is None:
                    fail(lib.EXIT_STAGE_INVALID, "archive member unreadable", member=name)
                kept[name] = handle.read()
    finally:
        code = proc.wait()
    if code != 0:
        fail(lib.EXIT_STAGE_INVALID, "git archive failed", exit=code)
    if "src/autoteacher_m0/bridge/controller.py" not in kept:
        fail(lib.EXIT_STAGE_INVALID, "controller.py missing from product archive")
    return kept


def _write_stage_file(path: Path, data: bytes) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    info = os.lstat(path)
    return {"sha256": lib.sha256_bytes(data), "bytes": info.st_size,
            "mode": stat.S_IMODE(info.st_mode)}


def _copy_regular(src: Path, dst: Path) -> dict:
    if not src.is_file() or src.is_symlink():
        fail(lib.EXIT_STAGE_INVALID, "source is not a regular file", source=str(src))
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    info = os.lstat(dst)
    return {"sha256": lib.sha256_file(dst), "bytes": info.st_size,
            "mode": stat.S_IMODE(info.st_mode)}


def _copy_tree(src: Path, dst: Path, *, exclude: tuple[str, ...] = ()) -> list[dict]:
    """Copy only regular files/dirs; symlinks and special files are refused."""
    if not src.is_dir():
        fail(lib.EXIT_STAGE_INVALID, "source tree missing", source=str(src))
    rows: list[dict] = []
    for dirpath, dirnames, filenames in os.walk(src, followlinks=False):
        current = Path(dirpath)
        relative_dir = current.relative_to(src)
        for name in list(dirnames):
            path = current / name
            if name in exclude and relative_dir == Path("."):
                dirnames.remove(name)
                continue
            if path.is_symlink():
                fail(lib.EXIT_STAGE_INVALID, "symlinked directory in source tree",
                     path=str(path))
        for name in filenames:
            path = current / name
            if path.is_symlink():
                fail(lib.EXIT_STAGE_INVALID, "symlinked file in source tree",
                     path=str(path))
            info = os.lstat(path)
            if not stat.S_ISREG(info.st_mode):
                fail(lib.EXIT_STAGE_INVALID, "special file in source tree",
                     path=str(path))
            target = dst / path.relative_to(src)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
            rows.append({
                "path": str(target.relative_to(dst.parent)),
                "sha256": lib.sha256_file(target),
                "bytes": os.lstat(target).st_size,
                "source": {"kind": "artifact", "source_path": str(path),
                           "source_sha256": lib.sha256_file(path)},
            })
    return rows


def build_adapter(*, rootfs: Path, deps: Path, build_root: Path,
                  commands_path: Path) -> dict:
    build_id = f"adapter-{lib.utc_compact()}"
    out = build_root / build_id / "bridge"
    out.mkdir(parents=True)
    os.chmod(out, 0o777)
    argv = [
        "podman", "run", "--rm",
        "--name", f"at-g3d-agent-build-{build_id}",
        "--network", "none", "--http-proxy=false", "--unsetenv-all",
        "--env", "PATH=/usr/bin", "--env", "HOME=/work",
        "--env", "G3C_BUILD_IN_CONTAINER=1",
        "--read-only", "--read-only-tmpfs=false",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--user", "65534:65534", "--pids-limit", "32",
        "--memory", "1g", "--memory-swap", "1g", "--cpus", "1",
        "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=32m,mode=1777",
        "--tmpfs", "/work:rw,noexec,nosuid,nodev,size=256m,mode=1777",
        "--workdir", "/work", "--timeout", "180", "--systemd=false",
        "--mount", f"type=bind,src={SPIKE},dst=/src,ro=true",
        "--mount", f"type=bind,src={NPM},dst=/npm,ro=true",
        "--mount", f"type=bind,src={lib.REPO_ROOT / 'scripts' / 'g3c'},dst=/build-src,ro=true",
        "--mount", f"type=bind,src={out},dst=/out,rw=true",
        "--rootfs", str(rootfs),
        "/usr/bin/node", "/build-src/build-adapter.mjs",
    ]
    record = lib.run_command(argv, log_dir=out.parent, name="build-adapter",
                             timeout=240, commands_path=commands_path)
    if record["exit"] != 0:
        fail(lib.EXIT_STAGE_INVALID, "adapter build failed",
             exit=record["exit"], log=record["stdout_path"])
    meta_path = out / "build-meta.json"
    if not meta_path.is_file():
        fail(lib.EXIT_STAGE_INVALID, "adapter build-meta missing")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    lib_js = out / "lib" / "index.js"
    if not lib_js.is_file():
        fail(lib.EXIT_STAGE_INVALID, "adapter lib/index.js missing")
    actual_js = lib.sha256_file(lib_js)
    if meta.get("builtJs", {}).get("sha256") != actual_js:
        fail(lib.EXIT_STAGE_INVALID, "adapter build-meta hash mismatch")
    if actual_js != ADAPTER_EXPECTED_JS:
        fail(lib.EXIT_STAGE_INVALID,
             "adapter rebuild does not match the frozen G3-C artifact",
             expected=ADAPTER_EXPECTED_JS, actual=actual_js)
    if meta.get("dshLlmVersion") != "0.2.2-rc.2":
        fail(lib.EXIT_STAGE_INVALID, "adapter built against unexpected DSH version",
             version=meta.get("dshLlmVersion"))
    return {"build_id": build_id, "build_dir": str(out), "command": argv,
            "build_meta_path": str(meta_path),
            "build_meta_sha256": lib.sha256_file(meta_path),
            "build_meta": meta,
            "deterministic_match": True,
            "expected_built_js_sha256": ADAPTER_EXPECTED_JS}


def node_version(rootfs: Path, commands_path: Path, log_dir: Path) -> dict:
    record = lib.run_command([str(rootfs / "usr" / "bin" / "node"), "--version"],
                             log_dir=log_dir, name="node-version", timeout=30,
                             commands_path=commands_path)
    if record["exit"] != 0:
        fail(lib.EXIT_BLOCKED_ENVIRONMENT, "fixed rootfs node --version failed",
             exit=record["exit"])
    return {"path": str(rootfs / "usr" / "bin" / "node"),
            "version": record["stdout"].strip(),
            "sha256": lib.sha256_file(rootfs / "usr" / "bin" / "node")}


def dsh_reference(deps: Path) -> dict:
    dist = deps / "deepseek_harness_sdk-0.2.2rc2.dist-info"
    meta = deps / "deepseek_harness_runtime" / "deepseek-harness-runtime.json"
    runtime_bin = deps / "deepseek_harness_runtime" / "runtime" / \
        "deepseek-harness-sdk-runtime-linux-x64"
    if not dist.is_dir() or not runtime_bin.is_file():
        fail(lib.EXIT_STAGE_INVALID, "DSH runtime package missing from deps")
    version = None
    for line in (dist / "METADATA").read_text(encoding="utf-8").splitlines():
        if line.startswith("Version:"):
            version = line.split(":", 1)[1].strip()
            break
    return {"sdk_version": version,
            "dist_info": str(dist),
            "runtime_json": str(meta),
            "runtime_sha256": lib.sha256_file(runtime_bin),
            "runtime_path": str(runtime_bin)}


def _mode_tree(root: Path) -> None:
    for dirpath, dirnames, filenames in os.walk(root):
        for name in dirnames:
            os.chmod(Path(dirpath) / name, 0o555)
        for name in filenames:
            os.chmod(Path(dirpath) / name, 0o444)
    os.chmod(root, 0o555)


def _source_worktree(relative: str) -> dict:
    path = lib.REPO_ROOT / relative
    if not path.is_file():
        fail(lib.EXIT_STAGE_INVALID, "worktree source missing", path=relative)
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", relative], cwd=str(lib.REPO_ROOT),
        capture_output=True, text=True).returncode == 0
    return {"kind": "worktree", "path": relative,
            "sha256": lib.sha256_file(path), "tracked_at_head": tracked}


def build_stage(base: str, *, stage_root: Path | None = None) -> Path:
    identity = product_identity(base)
    rootfs = lib.ROOTFS
    deps = lib.DEPS
    if not rootfs.is_dir() or not deps.is_dir():
        fail(lib.EXIT_BLOCKED_ENVIRONMENT, "fixed rootfs/deps missing")

    stamp = lib.utc_compact()
    stage_dir = stage_root or (lib.G3D_ROOT / f"stage-{stamp}")
    if stage_dir.exists():
        stage_dir = stage_dir.with_name(f"{stage_dir.name}-{os.getpid()}")
    commands_path = lib.G3D_ROOT / "commands.jsonl"
    lib.G3D_ROOT.mkdir(parents=True, exist_ok=True)

    rootfs_before = lib.sha256_tree(rootfs)
    deps_before = lib.sha256_tree(deps)
    if rootfs_before != lib.ROOTFS_CANON:
        fail(lib.EXIT_EVIDENCE_INTEGRITY, "rootfs is not canonical before build",
             expected=lib.ROOTFS_CANON, actual=rootfs_before)
    if deps_before != lib.DEPS_CANON:
        fail(lib.EXIT_EVIDENCE_INTEGRITY, "deps are not canonical before build",
             expected=lib.DEPS_CANON, actual=deps_before)

    stage_dir.mkdir(parents=True)
    try:
        stage_dir = _assemble_stage(
            base=base, stage_dir=stage_dir, identity=identity,
            rootfs=rootfs, deps=deps, rootfs_before=rootfs_before,
            deps_before=deps_before, commands_path=commands_path)
    except BaseException:
        try:
            lib.safe_delete_tree(lib.G3D_ROOT, stage_dir)
        except Exception:  # noqa: BLE001 - keep the original failure
            pass
        raise
    finally:
        cleanup_rootfs_mount_targets(rootfs)
    rootfs_after = lib.sha256_tree(rootfs)
    deps_after = lib.sha256_tree(deps)
    if rootfs_after != rootfs_before or deps_after != deps_before:
        fail(lib.EXIT_EVIDENCE_INTEGRITY, "rootfs/deps drifted during stage build",
             rootfs_before=rootfs_before, rootfs_after=rootfs_after,
             deps_before=deps_before, deps_after=deps_after)
    return stage_dir


def _assemble_stage(*, base: str, stage_dir: Path, identity: dict,
                    rootfs: Path, deps: Path, rootfs_before: str,
                    deps_before: str, commands_path: Path) -> Path:
    trusted = stage_dir / "trusted"
    candidate = stage_dir / "candidate"
    trusted.mkdir()
    candidate.mkdir()

    adapter = build_adapter(rootfs=rootfs, deps=deps,
                            build_root=lib.G3D_ROOT / "build",
                            commands_path=commands_path)
    cleanup_rootfs_mount_targets(rootfs)
    node = node_version(rootfs, commands_path,
                        lib.G3D_ROOT / "build" / adapter["build_id"])
    dsh = dsh_reference(deps)

    product = extract_product_files(base)
    trusted_rows: list[dict] = []
    for name in sorted(product):
        if not name.startswith("src/autoteacher_m0/"):
            continue
        relative = name
        data = product[name]
        written = _write_stage_file(trusted / relative, data)
        trusted_rows.append({
            "path": relative,
            "sha256": written["sha256"],
            "bytes": written["bytes"],
            "source": {"kind": "git_blob", "commit": base, "path": name,
                       "git_blob": lib.git_blob_hash(base, name)},
        })
    # Trusted Fake provider (product-reviewed spike file, not candidate code).
    fake_name = "spikes/g3b-trusted-bridge/fake/fake_provider.py"
    fake_data = product[fake_name]
    written = _write_stage_file(trusted / "fake" / "fake_provider.py", fake_data)
    trusted_rows.append({
        "path": "fake/fake_provider.py",
        "sha256": written["sha256"], "bytes": written["bytes"],
        "source": {"kind": "git_blob", "commit": base, "path": fake_name,
                   "git_blob": lib.git_blob_hash(base, fake_name)},
    })
    # Trusted entrypoint and read-only config templates come from this commit's
    # worktree files; their sha256 is recorded so a reviewer can re-hash the
    # committed implementation.
    entry_source = "scripts/g3d/stage/trusted_entry.py"
    written = _write_stage_file(trusted / "run" / "trusted_entry.py",
                               (lib.REPO_ROOT / entry_source).read_bytes())
    trusted_rows.append({
        "path": "run/trusted_entry.py", "sha256": written["sha256"],
        "bytes": written["bytes"],
        "source": {**_source_worktree(entry_source), "path": entry_source},
    })
    for name in TRUSTED_TEMPLATES:
        source_relative = f"config/g3d/trusted/{name}"
        written = _write_stage_file(trusted / "templates" / name,
                                   (lib.REPO_ROOT / source_relative).read_bytes())
        trusted_rows.append({
            "path": f"templates/{name}", "sha256": written["sha256"],
            "bytes": written["bytes"],
            "source": {**_source_worktree(source_relative),
                       "path": source_relative},
        })
    written = _write_stage_file(trusted / "etc" / "passwd", PASSWD.encode())
    trusted_rows.append({"path": "etc/passwd", "sha256": written["sha256"],
                         "bytes": written["bytes"],
                         "source": {"kind": "generated",
                                    "generator": "scripts/g3d/build_stage.py",
                                    "description": "trusted synthetic passwd"}})
    written = _write_stage_file(trusted / "etc" / "group", GROUP.encode())
    trusted_rows.append({"path": "etc/group", "sha256": written["sha256"],
                         "bytes": written["bytes"],
                         "source": {"kind": "generated",
                                    "generator": "scripts/g3d/build_stage.py",
                                    "description": "trusted synthetic group"}})

    candidate_rows: list[dict] = []
    # --- candidate: explicit allow-list -------------------------------------
    entry_source = "scripts/g3d/stage/candidate_entry.py"
    written = _write_stage_file(candidate / "run" / "candidate_entry.py",
                               (lib.REPO_ROOT / entry_source).read_bytes())
    candidate_rows.append({
        "path": "run/candidate_entry.py", "sha256": written["sha256"],
        "bytes": written["bytes"],
        "source": {**_source_worktree(entry_source), "path": entry_source},
    })
    patch_source = "config/g3d/candidate/bridge.patch.yml"
    patch_bytes = (lib.REPO_ROOT / patch_source).read_bytes()
    if b"/probe/" in patch_bytes or b"/work/state" in patch_bytes:
        fail(lib.EXIT_STAGE_INVALID, "candidate patch references a forbidden path",
             source=patch_source)
    written = _write_stage_file(candidate / "config" / "bridge.patch.yml",
                               patch_bytes)
    candidate_rows.append({
        "path": "config/bridge.patch.yml", "sha256": written["sha256"],
        "bytes": written["bytes"],
        "source": {**_source_worktree(patch_source), "path": patch_source},
    })
    adapter_dir = Path(adapter["build_dir"])
    for name in ("lib/index.js", "lib/index.d.ts", "build-meta.json"):
        source_path = adapter_dir / name
        written = _copy_regular(source_path, candidate / "runtime" / "bridge" / name)
        candidate_rows.append({
            "path": f"runtime/bridge/{name}", "sha256": written["sha256"],
            "bytes": written["bytes"],
            "source": {"kind": "build_artifact", "build_id": adapter["build_id"],
                       "build_command": adapter["command"],
                       "source_blob": {
                           "commit": base,
                           "path": "spikes/g3b-trusted-bridge/src/index.ts",
                           "sha256": lib.sha256_bytes(product[
                               "spikes/g3b-trusted-bridge/src/index.ts"])},
                       "build_meta_sha256": adapter["build_meta_sha256"]},
        })
    for name in SKILL_FILES:
        source_path = G3A_STAGE / "runtime" / "skill" / "lib" / name
        written = _copy_regular(source_path, candidate / "runtime" / "skill" / "lib" / name)
        candidate_rows.append({
            "path": f"runtime/skill/lib/{name}", "sha256": written["sha256"],
            "bytes": written["bytes"],
            "source": {"kind": "artifact", "source_path": str(source_path),
                       "source_sha256": lib.sha256_file(source_path)},
        })
    candidate_rows.extend(_copy_tree(
        G3A_STAGE / "runtime" / "node_modules",
        candidate / "node_modules",
        exclude=CANDIDATE_NODE_MODULES_EXCLUDE))
    candidate_rows.extend(_copy_tree(G3A_STAGE / "native-cache",
                                     candidate / "native-cache"))
    candidate_rows.extend(_copy_tree(G3A_STAGE / "pkg-cache",
                                     candidate / "pkg-cache"))
    fixture_sources = {
        "fixtures/skills.json": G3A_STAGE / "fixtures" / "skills.json",
        "fixtures/capture-tools.json": G3C_STAGE / "fixtures" / "capture-tools.json",
    }
    for relative, source_path in fixture_sources.items():
        written = _copy_regular(source_path, candidate / relative)
        candidate_rows.append({
            "path": relative, "sha256": written["sha256"],
            "bytes": written["bytes"],
            "source": {"kind": "artifact", "source_path": str(source_path),
                       "source_sha256": lib.sha256_file(source_path)},
        })
    written = _write_stage_file(candidate / "etc" / "passwd", PASSWD.encode())
    candidate_rows.append({"path": "etc/passwd", "sha256": written["sha256"],
                           "bytes": written["bytes"],
                           "source": {"kind": "generated",
                                      "generator": "scripts/g3d/build_stage.py",
                                      "description": "candidate synthetic passwd"}})
    written = _write_stage_file(candidate / "etc" / "group", GROUP.encode())
    candidate_rows.append({"path": "etc/group", "sha256": written["sha256"],
                           "bytes": written["bytes"],
                           "source": {"kind": "generated",
                                      "generator": "scripts/g3d/build_stage.py",
                                      "description": "candidate synthetic group"}})

    reference = {
        "schema": "m0.g3d.stage.reference.v1",
        "base_sha": base,
        "synthetic": True,
        "real_model_calls": 0,
        "real_external_http_calls": 0,
        "has_real_key": False,
        "rootfs": {"path": str(rootfs), "sha256": rootfs_before},
        "deps": {"path": str(deps), "sha256": deps_before},
        "node": node,
        "dsh": dsh,
        "adapter_build": {"build_id": adapter["build_id"],
                          "built_js_sha256": adapter["build_meta"]["builtJs"]["sha256"],
                          "dsh_llm_version": adapter["build_meta"]["dshLlmVersion"]},
    }
    for section, root in (("trusted", trusted), ("candidate", candidate)):
        written = _write_stage_file(root / "REFERENCE.json",
                                   lib.json_bytes(reference))
        (trusted_rows if section == "trusted" else candidate_rows).append({
            "path": "REFERENCE.json", "sha256": written["sha256"],
            "bytes": written["bytes"],
            "source": {"kind": "generated",
                       "generator": "scripts/g3d/build_stage.py",
                       "description": f"{section} runtime references"},
        })

    _mode_tree(trusted)
    _mode_tree(candidate)
    for row in trusted_rows + candidate_rows:
        row["mode"] = 0o444
    os.chmod(stage_dir, 0o755)

    manifest = {
        "schema": lib.STAGE_SCHEMA,
        "created_utc": lib.utc(),
        "base_sha": base,
        "head_at_build": identity["head"],
        "product_src_identical_to_base": True,
        "status_line_at_build": identity["status"],
        "rootfs": {"path": str(rootfs), "sha256": rootfs_before,
                   "canonical": lib.ROOTFS_CANON},
        "deps": {"path": str(deps), "sha256": deps_before,
                 "canonical": lib.DEPS_CANON},
        "node": node,
        "dsh": dsh,
        "adapter_build": {
            "build_id": adapter["build_id"],
            "command": adapter["command"],
            "build_meta_path": adapter["build_meta_path"],
            "build_meta_sha256": adapter["build_meta_sha256"],
            "build_meta": adapter["build_meta"],
            "deterministic_match": adapter["deterministic_match"],
            "expected_built_js_sha256": adapter["expected_built_js_sha256"],
        },
        "trusted": {"tree_sha256": lib.sha256_tree(trusted),
                    "files": sorted(trusted_rows, key=lambda row: row["path"])},
        "candidate": {"tree_sha256": lib.sha256_tree(candidate),
                      "files": sorted(candidate_rows, key=lambda row: row["path"])},
        "excluded": {
            "candidate_node_modules": list(CANDIDATE_NODE_MODULES_EXCLUDE),
            "candidate": ["autoteacher_m0", "bridge/controller.py", "accounting/",
                          "admission.json", "broker.json", "policy.json",
                          "*.sqlite3*", "receipts/", "fake/fake_provider.py",
                          "run/trusted_entry.py", "scripts/g3d/launch.py",
                          "launcher scripts", "full repo", ".git"],
            "trusted": ["candidate-session", "candidate stage", "repo", ".git",
                        "Key/credential values", "receipts", "broker DB",
                        "admission/policy values"],
        },
    }
    manifest_bytes = lib.json_bytes(manifest)
    (stage_dir / "manifest.json").write_bytes(manifest_bytes)
    (stage_dir / "manifest.sha256").write_text(
        f"{lib.sha256_bytes(manifest_bytes)}  manifest.json\n", encoding="utf-8")

    validation = lib.validate_stage(stage_dir, verify_git=True)
    if not validation["ok"]:
        fail(lib.EXIT_STAGE_INVALID, "stage validation failed",
             problems=validation["problems"][:40])

    summary = {
        "ok": True,
        "utc": lib.utc(),
        "stage_dir": str(stage_dir),
        "manifest_sha256": lib.sha256_bytes(manifest_bytes),
        "base_sha": base,
        "head": identity["head"],
        "trusted_tree_sha256": manifest["trusted"]["tree_sha256"],
        "candidate_tree_sha256": manifest["candidate"]["tree_sha256"],
        "trusted_files": len(manifest["trusted"]["files"]),
        "candidate_files": len(manifest["candidate"]["files"]),
        "adapter_built_js_sha256": adapter["build_meta"]["builtJs"]["sha256"],
        "adapter_deterministic_match": True,
        "node_version": node["version"],
        "dsh_sdk_version": dsh["sdk_version"],
        "dsh_runtime_sha256": dsh["runtime_sha256"],
        "rootfs_sha256": rootfs_before,
        "deps_sha256": deps_before,
        "rootfs_canonical": True,
        "deps_canonical": True,
    }
    lib.write_json_atomic(stage_dir / "stage-summary.json", summary, mode=0o444)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return stage_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default=lib.PRODUCT_BASE,
                        help="product commit to build the trusted stage from")
    parser.add_argument("--stage-root", default=None,
                        help="explicit stage directory (must not exist)")
    args = parser.parse_args(argv)
    stage_root = Path(args.stage_root) if args.stage_root else None
    try:
        build_stage(args.base, stage_root=stage_root)
    except lib.G3DError as exc:
        sys.stderr.write(f"BUILD_STAGE_FAILED {exc.reason}: {exc}\n")
        sys.stderr.write(json.dumps(exc.detail, indent=2, sort_keys=True) + "\n")
        return exc.exit_code
    return lib.EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
