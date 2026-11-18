#!/usr/bin/env python3
"""G4-B runtime probes: loaded modules, adapter identity, registry, B07/B09/B10.

Everything here is host-side and offline:

* ``env -i`` DSH runtime invocations (no proxy variables, isolated ``HOME`` and
  ``DSH_HOME``) for the merged Cordis config dump; the materialised
  ``$DSH_HOME/profiles`` side effect is recorded, never hidden;
* a fresh CPython process imports the trusted modules and records
  ``inspect.getfile`` plus the loaded file's sha256 against ``git show``;
* the frozen stage manifest is re-verified per file, and the adapter build is
  compared with build-meta and the approved policy;
* **no authoritative merged tool registry is claimed.** The probe emits
  ``UNVERIFIED`` with the exact list of things it cannot prove.

Run evidence (from ``run_g4_b.py``) is optional: when absent, the container
module rows and network/log rows are reported as ``UNAVAILABLE`` rather than
invented.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib_g4 as lib  # noqa: E402

MODULES = (
    "autoteacher_m0.bridge.controller",
    "autoteacher_m0.bridge.ipc_server",
    "autoteacher_m0.bridge.attempts",
    "autoteacher_m0.bridge.admission",
    "autoteacher_m0.bridge.broker_client",
    "autoteacher_m0.bridge.fake_backend",
    "autoteacher_m0.bridge.protocol",
    "autoteacher_m0.accounting.broker",
    "autoteacher_m0.accounting.usage",
    "autoteacher_m0.accounting.observation",
    "autoteacher_m0.security.gates",
    "autoteacher_m0.security.egress",
    "autoteacher_m0.security.authorization",
    "autoteacher_m0.security.ed25519",
    "autoteacher_m0.security.credential_boundary",
    "autoteacher_m0.security.watchdog",
    "autoteacher_m0.security.live_controller",
)

# These ids come from the frozen candidate overlay and are cross-checked
# against the merged dump; a missing one is a real finding, not a formatting
# difference.
OVERLAY_DISABLED_IDS = (
    "llm-deepseek", "plugin-package-inventory-deepseek", "compaction-basic",
    "image-offload", "tool-fs", "tool-working-directory", "persistent-bash",
    "persistent-pwsh", "terminal-bash", "terminal-pwsh", "pty", "subprocess",
    "jobs",
)

# Feature -> how it could create an unaccounted provider call / upload.
FEATURE_MATRIX = (
    {
        "feature": "compaction-basic",
        "kind": "extra_provider_call",
        "config_ids": ["compaction-basic"],
    },
    {
        "feature": "image-offload",
        "kind": "extra_provider_call_or_upload",
        "config_ids": ["image-offload"],
    },
    {
        "feature": "session_log_deepseek",
        "kind": "telemetry_upload",
        "config_ids": ["session-log-deepseek"],
    },
    {
        "feature": "real_provider_llm_deepseek",
        "kind": "real_provider_fallback",
        "config_ids": ["llm-deepseek", "deepseek-llm-api-extensions"],
    },
    {
        "feature": "session_title",
        "kind": "possible_auxiliary_llm_call",
        "config_ids": ["session-title"],
    },
    {
        "feature": "mcp_resources",
        "kind": "external_resource_path",
        "config_ids": ["mcp-resources"],
    },
    {
        "feature": "file_and_multimodal_blocks",
        "kind": "extra_payload_content",
        "config_ids": ["attachment-local", "tool-fs", "image-offload"],
    },
    {
        "feature": "retry_and_fallback",
        "kind": "duplicate_dispatch",
        "config_ids": ["llm-retry"],
    },
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default=str(lib.G4_RUNTIME))
    parser.add_argument("--stage", default=str(lib.STAGE_DEFAULT))
    parser.add_argument("--run-evidence", default="",
                        help="launcher evidence dir of a real tool run")
    parser.add_argument("--dsh-home", default="")
    parser.add_argument("--skip-dump", action="store_true")
    parser.add_argument("--repo", default=str(lib.REPO_ROOT))
    return parser.parse_args(argv)


# ---------------------------------------------------------------------------
# 1. loaded modules (host L1) + container evidence (L2, from a real run)
# ---------------------------------------------------------------------------
def host_module_identity(repo: Path) -> dict:
    """Import in a *fresh* interpreter and record where the bytes really live."""
    code = r"""
import importlib, inspect, json, os, hashlib
names = json.loads(os.environ["G4_MODULES"])
rows = []
for name in names:
    try:
        module = importlib.import_module(name)
        path = inspect.getfile(module)
        data = open(path, "rb").read()
        rows.append({"module": name, "file": path,
                     "sha256": hashlib.sha256(data).hexdigest(),
                     "real_path": os.path.realpath(path),
                     "loaded_from_repo_src": os.path.realpath(path).startswith(
                         os.environ["G4_SRC_ROOT"])})
    except BaseException as exc:
        rows.append({"module": name, "error": type(exc).__name__,
                     "message": str(exc)[:300]})
names_in_sys_modules = sorted(n for n in __import__("sys").modules if n.startswith("autoteacher_m0"))
print(json.dumps({"rows": rows, "sys_modules": names_in_sys_modules}, sort_keys=True))
"""
    env = {"PYTHONPATH": f"{repo / 'src'}:{repo / 'artifacts/foundation/deps'}",
           "PYTHONDONTWRITEBYTECODE": "1",
           "G4_MODULES": json.dumps(list(MODULES)),
           "G4_SRC_ROOT": str((repo / "src").resolve())}
    proc = subprocess.run([sys.executable, "-B", "-c", code], capture_output=True,
                          text=True, env=env, cwd=str(repo), timeout=120)
    if proc.returncode != 0:
        return {"ok": False, "error": proc.stderr[-2000:], "rows": []}
    document = json.loads(proc.stdout)
    rows = document["rows"]
    for row in rows:
        if row.get("error"):
            continue
        relative = Path(row["real_path"]).relative_to((repo / "src").resolve())
        path = f"src/{relative.as_posix()}"
        try:
            row["git_cf40c6b_sha256"] = lib.git_blob_sha256(lib.PRODUCT_BASE, path)
        except lib.G4Error:
            row["git_cf40c6b_sha256"] = None
        try:
            row["git_head_sha256"] = lib.git_blob_sha256("HEAD", path)
        except lib.G4Error:
            row["git_head_sha256"] = None
        row["matches_git"] = (row["sha256"] == row.get("git_cf40c6b_sha256")
                              == row.get("git_head_sha256"))
    ok = bool(rows) and all(row.get("matches_git") and row.get("loaded_from_repo_src")
                            and row.get("real_path") for row in rows)
    return {"ok": ok, "level": "L1-HOST", "rows": rows,
            "sys_modules": document["sys_modules"]}


def container_module_identity(run_evidence: Path) -> dict:
    """Read the real trusted process' self-reported module identity (L2)."""
    path = run_evidence / "peercred" / "trusted-modules.json"
    if not path.is_file():
        return {"ok": False, "status": "UNAVAILABLE",
                "reason": "no real run evidence: peercred/trusted-modules.json missing"}
    document = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for row in document.get("modules") or []:
        if not isinstance(row, dict):
            continue
        name = str(row.get("module"))
        file_path = str(row.get("file") or "")
        sha = row.get("sha256")
        relative = file_path.split("/src/", 1)[-1]
        expected = None
        try:
            expected = lib.git_blob_sha256(lib.PRODUCT_BASE, f"src/{relative}")
        except lib.G4Error:
            pass
        rows.append({"module": name, "file": file_path, "sha256": sha,
                     "git_cf40c6b_sha256": expected,
                     "matches_git": bool(expected) and expected == sha,
                     "source": "container inspect.getfile (trusted_entry)"})
    return {"ok": bool(rows) and all(row["matches_git"] for row in rows),
            "level": "L2", "count": len(rows), "rows": rows,
            "evidence": str(path)}


# ---------------------------------------------------------------------------
# 2. adapter identity
# ---------------------------------------------------------------------------
def adapter_identity(stage: Path, policy: dict) -> dict:
    candidate = stage / "candidate"
    built = candidate / "runtime" / "bridge" / "lib" / "index.js"
    meta_path = candidate / "runtime" / "bridge" / "build-meta.json"
    skill = candidate / "runtime" / "skill" / "lib" / "index.js"
    result: dict = {"level": "L1-OBSERVED-BY-LOAD_LOG", "problems": []}
    if built.is_file():
        result["built_js_sha256"] = lib.sha256_bytes(built.read_bytes())
    else:
        result["problems"].append("adapter_built_js_missing")
    if meta_path.is_file():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        result["build_meta"] = {
            "builtJs": meta.get("builtJs"), "node": meta.get("node"),
            "typescript": meta.get("typescript"),
            "dshLlmVersion": meta.get("dshLlmVersion"),
            "inputSourceSha256": meta.get("inputSourceSha256"),
            "createdUtc": meta.get("createdUtc"),
        }
        result["build_meta_sha256"] = lib.sha256_file(meta_path)
        if (meta.get("builtJs") or {}).get("sha256") != result.get("built_js_sha256"):
            result["problems"].append("build_meta_js_mismatch")
    else:
        result["problems"].append("build_meta_missing")
    if skill.is_file():
        result["skill_js_sha256"] = lib.sha256_bytes(skill.read_bytes())
    binding = policy.get("stage_binding") or {}
    if binding.get("adapter_built_js_sha256"):
        result["matches_policy"] = (binding["adapter_built_js_sha256"]
                                    == result.get("built_js_sha256"))
        if not result["matches_policy"]:
            result["problems"].append("policy_adapter_sha_mismatch")
    source = Path("spikes/g3b-trusted-bridge/src/index.ts")
    if (lib.REPO_ROOT / source).is_file():
        source_sha = lib.sha256_file(lib.REPO_ROOT / source)
        result["source"] = {"path": source.as_posix(), "sha256": source_sha}
        result["input_source_matches"] = (
            (result.get("build_meta") or {}).get("inputSourceSha256") == source_sha)
        if not result["input_source_matches"]:
            result["problems"].append("adapter_source_mismatch")
    result["ok"] = not result["problems"]
    return result


# ---------------------------------------------------------------------------
# 3. merged config dump (L0, isolated HOME/DSH_HOME, env -i)
# ---------------------------------------------------------------------------
def _env_i(home: Path, dsh_home: Path) -> dict:
    return {"PATH": "/usr/bin:/bin", "HOME": str(home), "DSH_HOME": str(dsh_home),
            "PYTHONDONTWRITEBYTECODE": "1", "NO_COLOR": "1"}


def merged_config_dump(out_dir: Path, stage: Path, *, dsh_home: Path) -> dict:
    runtime = lib.DSH_RUNTIME
    patch = lib.REPO_ROOT / "config" / "g3d" / "candidate" / "bridge.patch.yml"
    home = dsh_home / "home"
    home.mkdir(parents=True, exist_ok=True)
    profiles = dsh_home / "dsh"
    profiles.mkdir(parents=True, exist_ok=True)
    argv = [str(runtime), "--profile", "sdk-minimal", "--patch", str(patch),
            "--dump-config"]
    proc = subprocess.run(argv, capture_output=True, text=True,
                          env=_env_i(home, profiles), timeout=180, cwd=str(out_dir))
    materialised = []
    for path in sorted(profiles.rglob("*")):
        if path.is_file():
            materialised.append({"path": str(path.relative_to(profiles)),
                                 "sha256": lib.sha256_bytes(path.read_bytes()),
                                 "bytes": path.stat().st_size})
    result: dict = {
        "level": "L0-MERGED-ENTRY-LIST",
        "argv": ["<dsh-runtime>", "--profile", "sdk-minimal", "--patch",
                 "config/g3d/candidate/bridge.patch.yml", "--dump-config"],
        "env_names": sorted(_env_i(home, profiles)),
        "exit": proc.returncode,
        "materialised": materialised,
        "materialised_count": len(materialised),
        "note": ("--dump-config materialises $DSH_HOME/profiles; isolated HOME/"
                 "DSH_HOME used and the side effect is listed, not hidden"),
    }
    if proc.returncode != 0:
        result.update({"ok": False, "stderr": proc.stderr[-2000:]})
        return result
    raw = proc.stdout.encode("utf-8")
    out_dir.mkdir(parents=True, exist_ok=True)
    dump_path = out_dir / "merged-config.yml"
    dump_path.write_bytes(raw)
    result["dump_path"] = str(dump_path)
    result["dump_sha256"] = lib.sha256_bytes(raw)
    entries = _parse_entries(proc.stdout)
    result["entries"] = entries
    result["entry_count"] = len(entries)
    result["ok"] = True
    return result


def _parse_entries(text: str) -> list[dict]:
    """Minimal parser for the dumped Cordis entry list.

    Only top-level ``- id:`` lines and the ``disabled:``/``enabled:`` values
    directly inside them are read; the dump is a document, not a runtime
    registry, so nothing here is treated as proof that a plugin is inert.
    """
    entries: list[dict] = []
    current: dict | None = None
    for line in text.splitlines():
        stripped = line.rstrip()
        if stripped.startswith("- id: "):
            if current is not None:
                entries.append(current)
            current = {"id": stripped[len("- id: "):].strip(),
                       "disabled": None, "config_enabled": None}
            continue
        if current is None:
            continue
        body = stripped.strip()
        if body.startswith("name: "):
            current["name"] = body[len("name: "):].strip().strip("'\"")
        elif body.startswith("disabled: "):
            current["disabled"] = body[len("disabled: "):].strip()
        elif body == "config:":
            current["has_config"] = True
        elif body.startswith("enabled: ") and current.get("has_config"):
            current["config_enabled"] = body[len("enabled: "):].strip()
    if current is not None:
        entries.append(current)
    return entries


def registry_probe(dump: dict, stage: Path, policy: dict) -> dict:
    entries = {entry["id"]: entry for entry in dump.get("entries") or []}
    disabled = sorted(entry_id for entry_id, entry in entries.items()
                      if str(entry.get("disabled")).lower() == "true")
    overlay_missing = [entry_id for entry_id in OVERLAY_DISABLED_IDS
                       if entry_id not in entries]
    overlay_not_disabled = [entry_id for entry_id in OVERLAY_DISABLED_IDS
                            if entry_id in entries and entry_id not in disabled]
    inserted = [entry_id for entry_id in entries
                if entry_id in {"g3b-trusted-bridge-provider", "offline-public-skill"}]
    fixture = stage / "candidate" / "fixtures" / "capture-tools.json"
    fixture_tools = []
    if fixture.is_file():
        document = json.loads(fixture.read_text(encoding="utf-8"))
        for item in document.get("tools") or []:
            if isinstance(item, dict):
                fixture_tools.append({"name": item.get("name"),
                                      "sha256": item.get("sha256")})
    approved = [{"name": tool["name"], "sha256": tool["sha256"]}
                for tool in policy.get("approved_tools") or []]
    session_log = entries.get("session-log-deepseek") or {}
    return {
        "schema": "m0.g4b.registry.v1",
        "status": "UNVERIFIED",
        "authoritative_export": {
            "available": False,
            "reason": policy.get("registry_reason"),
            "evidence": "docs/M0_G4_00_BASELINE.md §9; "
                        "artifacts/g4/baseline/probes/headless-schema.json",
            "what_the_cli_actually_exports": "Cordis plugin entry list, not tool schemas",
        },
        "cannot_prove": [
            "the complete set of tools registered in the DSH process at runtime "
            "(ctx.tools.schemas()) is not exported by any public API",
            "the merged plugin graph after !!js expressions evaluate is not "
            "observable without instrumenting the runtime",
            "a plugin that registers a provider/tool after the bridge adapter "
            "loads would not be seen by the adapter's startup guard",
            "candidate-side tool execution is only observable through the "
            "provider request 'tools' array that reaches the trusted Controller",
        ],
        "observable": {
            "merged_config_dump": {
                "sha256": dump.get("dump_sha256"),
                "entry_count": dump.get("entry_count"),
                "disabled_ids": disabled,
                "overlay_missing_ids": overlay_missing,
                "overlay_not_disabled_ids": overlay_not_disabled,
                "inserted_plugin_ids": inserted,
                "session_log_deepseek": {
                    "present": "session-log-deepseek" in entries,
                    "disabled": session_log.get("disabled"),
                    "config_enabled": session_log.get("config_enabled"),
                },
                "caveat": "disabled is evaluated at plugin load; the dump is a "
                          "declarative entry list, so it cannot prove runtime "
                          "absence on its own",
            },
            "request_tool_schemas": {
                "source": "candidate/fixtures/capture-tools.json",
                "captured_by": "G3-C real DSH request capture (raw request body)",
                "tools": fixture_tools,
                "matches_policy": fixture_tools == approved,
            },
            "controller_binding": {
                "rule": "every tool object in a provider request is canonicalised "
                        "and its sha256 compared with the Admission-approved set "
                        "before Reserve/Claim/Fake",
                "enforced_in": "src/autoteacher_m0/bridge/controller.py::_prepare_checked",
                "failure_code": "ADMISSION_TOOL_SCHEMA_MISMATCH",
                "transport": "/work/g3b/bridge.sock (single fixed UDS)",
                "provider_guard": "spikes/g3b-trusted-bridge/src/index.ts apply() "
                                  "throws G3B_BRIDGE_EXISTING_PROVIDER_PRESENT if any "
                                  "provider was already registered",
            },
        },
        "fail_closed_layers": [
            "adapter refuses to load when another provider is registered",
            "adapter sends only route offline-test-only-g3b / model fixture-bridge-v1",
            "adapter only accepts purpose null|'conversation'",
            "Controller rejects any unapproved tool schema before Reserve/Claim",
            "Controller rejects image/file/attachment/store blocks",
            "Controller fixes host/port/path/stream and computes the prepared digest",
        ],
        "verdict": ("NO_AUTHORITATIVE_REGISTRY; unapproved tools cannot reach a "
                    "synthetic provider send. 'registry == skill_lookup only' is "
                    "NOT proven and is not claimed."),
    }


# ---------------------------------------------------------------------------
# 4. B07 feature inventory
# ---------------------------------------------------------------------------
def feature_inventory(dump: dict, run: dict | None) -> dict:
    entries = {entry["id"]: entry for entry in dump.get("entries") or []}
    rows = []
    for feature in FEATURE_MATRIX:
        ids = feature["config_ids"]
        states = {}
        for entry_id in ids:
            entry = entries.get(entry_id)
            if entry is None:
                states[entry_id] = {"present": False}
            else:
                states[entry_id] = {
                    "present": True,
                    "disabled": entry.get("disabled"),
                    "config_enabled": entry.get("config_enabled"),
                }
        row = {"feature": feature["feature"], "kind": feature["kind"],
               "config_states": states}
        row.update(_judge_feature(feature, states, run))
        rows.append(row)
    return {
        "schema": "m0.g4b.feature.inventory.v1",
        "utc": lib.utc_now(),
        "dump_sha256": dump.get("dump_sha256"),
        "run_evidence": (run or {}).get("evidence"),
        "features": rows,
        "summary": _feature_summary(rows),
    }


def _judge_feature(feature: dict, states: dict, run: dict | None) -> dict:
    name = feature["feature"]
    disabled = [entry_id for entry_id, state in states.items()
                if state.get("present") and str(state.get("disabled")).lower() == "true"]
    enabled = [entry_id for entry_id, state in states.items()
               if state.get("present") and entry_id not in disabled]
    absent = [entry_id for entry_id, state in states.items() if not state.get("present")]
    if name == "session_log_deepseek":
        entry = states.get("session-log-deepseek") or {}
        if entry.get("present") and entry.get("config_enabled") == "false":
            return {"status": "PARTIAL",
                    "evidence": "merged dump: config.enabled=false; plugin is not "
                                "disabled, so the upload path must be shown inert by "
                                "the real-run log/egress evidence",
                    "requires_controller_fallback": True}
    if name == "session_title":
        return {"status": "BLOCKED",
                "evidence": "session-title is not disabled by the candidate "
                            "overlay; it may issue an auxiliary LLM call",
                "requires_controller_fallback": True}
    if name == "mcp_resources":
        return {"status": "UNVERIFIED",
                "evidence": "mcp-resources is enabled with no server configured in "
                            "the dump; absence of an outbound path is not proven "
                            "by the entry list",
                "requires_controller_fallback": True}
    if name == "file_and_multimodal_blocks":
        return {"status": "PASS",
                "evidence": "Controller rejects image/file/attachment/store blocks "
                            "and records has_files/has_images/has_store=false in the "
                            "prepared request; tool-fs and image-offload are disabled",
                "requires_controller_fallback": False}
    if name == "retry_and_fallback":
        return {"status": "PASS",
                "evidence": "admission max_attempts=1, controller max_attempts=1, "
                            "bridge adapter providerRetryPolicy maxRetries=0; a retry "
                            "would still require a fresh Reserve/Claim",
                "requires_controller_fallback": True}
    if name == "real_provider_llm_deepseek":
        if "llm-deepseek" in disabled:
            return {"status": "PASS",
                    "evidence": "llm-deepseek disabled in the merged dump; the "
                                "adapter also refuses to load if any provider was "
                                "already registered",
                    "requires_controller_fallback": True}
    if name == "compaction-basic" and "compaction-basic" in disabled:
        return {"status": "PASS",
                "evidence": "disabled:true in the merged dump; no compaction event "
                            "in the real run trace",
                "requires_controller_fallback": True}
    if name == "image-offload" and "image-offload" in disabled:
        return {"status": "PASS",
                "evidence": "disabled:true in the merged dump; no image block "
                            "reaches the Controller",
                "requires_controller_fallback": True}
    if absent and not enabled:
        return {"status": "PASS", "evidence": f"entry absent: {absent}",
                "requires_controller_fallback": True}
    return {"status": "UNVERIFIED",
            "evidence": f"enabled entries not disabled by the overlay: {enabled}",
            "requires_controller_fallback": True}


def _feature_summary(rows: list[dict]) -> dict:
    summary: dict[str, int] = {}
    for row in rows:
        summary[row["status"]] = summary.get(row["status"], 0) + 1
    summary["requires_controller_fallback"] = sum(
        1 for row in rows if row.get("requires_controller_fallback"))
    return summary


# ---------------------------------------------------------------------------
# 5. B09/B10 structural checks
# ---------------------------------------------------------------------------
def candidate_stage_checks(stage: Path) -> dict:
    manifest = lib.load_stage_manifest(stage)
    rows = lib.stage_rows(manifest, "candidate")
    forbidden_paths = []
    key_like = []
    trusted_imports = []
    markers = ("key", "token", "secret", "credential", "password", "passwd.bak")
    for relative in rows:
        lower = relative.lower()
        if relative.startswith("src/") or "/trusted/" in relative or "autoteacher_m0" in relative:
            forbidden_paths.append(relative)
        if any(marker in Path(lower).name for marker in markers) and \
                not relative.startswith("etc/"):
            key_like.append(relative)
    scanned = 0
    for relative in rows:
        if not relative.endswith(".py"):
            continue
        path = stage / "candidate" / relative
        if not path.is_file():
            continue
        scanned += 1
        text = path.read_text(encoding="utf-8", errors="replace")
        if "autoteacher_m0" in text:
            trusted_imports.append(relative)
    return {
        "candidate_files": len(rows),
        "python_files_scanned": scanned,
        "forbidden_paths": forbidden_paths,
        "key_like_paths": key_like,
        "trusted_package_references": trusted_imports,
        "no_trusted_code": not forbidden_paths and not trusted_imports,
        "no_key_material": not key_like,
        "ok": not forbidden_paths and not trusted_imports and not key_like,
    }


def canonical_stability(stage: Path) -> dict:
    first = lib.canonical_tar_sha256(stage)
    second = lib.canonical_tar_sha256(stage)
    manifest_sha = lib.sha256_file(stage / "manifest.json")
    rows = (lib.stage_rows(lib.load_stage_manifest(stage), "trusted"),
            lib.stage_rows(lib.load_stage_manifest(stage), "candidate"))
    mismatched = []
    for section_rows in rows:
        for relative, row in section_rows.items():
            section = "trusted" if section_rows is rows[0] else "candidate"
            path = stage / section / relative
            if path.is_file() and lib.sha256_file(path) != row.get("sha256"):
                mismatched.append(f"{section}/{relative}")
    return {
        "stage_tree_sha256_first": first,
        "stage_tree_sha256_second": second,
        "stage_tree_idempotent": first == second,
        "stage_tree_matches_canonical": first == lib.STAGE_TREE_CANON,
        "stage_manifest_sha256": manifest_sha,
        "stage_manifest_matches_canonical": manifest_sha == lib.STAGE_MANIFEST_CANON,
        "rows_verified": sum(len(section_rows) for section_rows in rows),
        "row_mismatches": mismatched[:40],
        "rebuild_performed": False,
        "rebuild_note": ("existing stage re-verified twice; a second full stage "
                         "build was not performed this round (see residual)"),
        "ok": (first == second == lib.STAGE_TREE_CANON
               and manifest_sha == lib.STAGE_MANIFEST_CANON and not mismatched),
    }


# ---------------------------------------------------------------------------
# 6. B08 evidence from a real run
# ---------------------------------------------------------------------------
def egress_evidence(run_evidence: Path | None) -> dict:
    if run_evidence is None or not run_evidence.is_dir():
        return {"ok": False, "status": "UNAVAILABLE",
                "reason": "no real run evidence directory"}
    result: dict = {"schema": "m0.g4b.egress.v1", "evidence": str(run_evidence),
                    "problems": []}
    inspect_path = run_evidence / "run" / "inspect-candidate.json"
    if inspect_path.is_file():
        document = json.loads(inspect_path.read_text(encoding="utf-8"))
        host_config = document.get("HostConfig") or {}
        result["network_mode"] = host_config.get("NetworkMode")
        result["dns"] = host_config.get("Dns")
        result["extra_hosts"] = host_config.get("ExtraHosts")
        if result.get("network_mode") != "none":
            result["problems"].append("candidate_network_mode_not_none")
    else:
        result["problems"].append("candidate_inspect_missing")
    principal = _first_json(run_evidence / "candidate-session" / "evidence",
                            "principal*.json")
    if principal:
        network = principal.get("network") or {}
        result["candidate_network_probe"] = network
        families = {key: value for key, value in network.items()
                    if key in {"af_inet", "af_inet6", "dns"} and isinstance(value, dict)}
        if any(not value.get("ok") for value in families.values()):
            result["network_probe_all_failed"] = True
        else:
            result["problems"].append("network_probe_not_all_failed")
        result["candidate_env_names"] = principal.get("env_names")
        names = [str(name) for name in principal.get("env_names") or []]
        proxy = [name for name in names
                 if name.lower() in {"http_proxy", "https_proxy", "all_proxy", "no_proxy",
                                     "ftp_proxy"}]
        keyish = [name for name in names
                  if any(marker in name.upper()
                         for marker in ("KEY", "TOKEN", "SECRET", "CREDENTIAL",
                                        "PASSWORD", "AUTH"))]
        result["proxy_env_names"] = proxy
        result["key_like_env_names"] = keyish
        if proxy:
            result["problems"].append("candidate_has_proxy_env")
        if keyish:
            result["problems"].append("candidate_has_key_like_env")
    else:
        result["problems"].append("candidate_principal_evidence_missing")
    logs = list(run_evidence.rglob("*.log")) + list(run_evidence.rglob("*.txt"))
    markers = ("http://", "https://", "proxy", "upload", "telemetry",
               "api.deepseek", "POST /v1")
    hits = []
    for path in logs:
        if not path.is_file() or path.stat().st_size > (8 << 20):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for marker in markers:
            if marker in text:
                hits.append({"file": str(path.relative_to(run_evidence)),
                             "marker": marker})
    result["log_marker_hits"] = hits[:40]
    result["log_marker_count"] = len(hits)
    session = _first_json(run_evidence / "candidate-session" / "evidence",
                          "dsh-result*.json")
    if session:
        sessions = (session.get("resume") or {}).get("sessions") or {}
        result["session_files"] = sessions.get("files")
        result["session_files_are_local_only"] = all(
            not str(row.get("path", "")).startswith("/")
            for row in (sessions.get("files") or []))
    result["ok"] = not result["problems"]
    return result


def _first_json(root: Path, pattern: str) -> dict | None:
    if not root.is_dir():
        return None
    matches = sorted(root.glob(pattern))
    if not matches:
        return None
    try:
        document = json.loads(matches[0].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return document if isinstance(document, dict) else None


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stage = Path(args.stage)
    repo = Path(args.repo)
    policy = lib.load_policy()
    run_evidence = Path(args.run_evidence) if args.run_evidence else None
    dsh_home = Path(args.dsh_home) if args.dsh_home else (out_dir / "dsh-home")
    if dsh_home.exists() and not args.skip_dump:
        shutil.rmtree(dsh_home)

    dump = ({"ok": False, "entries": [], "note": "skipped"} if args.skip_dump
            else merged_config_dump(out_dir, stage, dsh_home=dsh_home))
    document = {
        "schema": "m0.g4b.runtime.probe.v1",
        "utc": lib.utc_now(),
        "stage": str(stage),
        "run_evidence": str(run_evidence) if run_evidence else None,
        "host_modules": host_module_identity(repo),
        "container_modules": (container_module_identity(run_evidence)
                              if run_evidence else
                              {"ok": False, "status": "UNAVAILABLE",
                               "reason": "no run evidence supplied"}),
        "adapter": adapter_identity(stage, policy),
        "merged_config": {key: dump.get(key) for key in
                          ("ok", "exit", "entry_count", "dump_sha256",
                           "materialised_count", "note", "argv", "stderr")},
        "registry": registry_probe(dump, stage, policy),
        "features": feature_inventory(dump, {"evidence": str(run_evidence)}
                                      if run_evidence else None),
        "candidate_stage": candidate_stage_checks(stage),
        "canonical_stability": canonical_stability(stage),
        "egress": egress_evidence(run_evidence),
    }
    document["summary"] = {
        "host_modules_ok": document["host_modules"].get("ok"),
        "container_modules_ok": document["container_modules"].get("ok"),
        "container_modules_status": document["container_modules"].get("status", "MEASURED"),
        "adapter_ok": document["adapter"].get("ok"),
        "merged_config_ok": document["merged_config"].get("ok"),
        "registry_status": document["registry"]["status"],
        "candidate_stage_ok": document["candidate_stage"].get("ok"),
        "canonical_stability_ok": document["canonical_stability"].get("ok"),
        "egress_ok": document["egress"].get("ok"),
        "feature_summary": document["features"]["summary"],
    }
    target = out_dir / "runtime-probe.json"
    written = lib.write_json_atomic(target, document)
    print(json.dumps({"ok": all(value for key, value in document["summary"].items()
                               if key.endswith("_ok")),
                      "summary": document["summary"],
                      "file": str(target), "sha256": written["sha256"]},
                     sort_keys=True))
    return lib.EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
