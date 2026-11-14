#!/usr/bin/env python3
"""Read-only target DSH Runtime/Profile verifier (PR2). Never a Live switch.

Runs the locked runtime's ``--dump-config`` with the reviewed target profile patch
(inside the caller's no-Key isolated OCI only) and fails non-zero unless:

* the merged config contains the guard row with the fixed synthetic broker policy,
  the public synthetic fixture provider, and the public skill_lookup entry;
* the real DeepSeek route and every dangerous tool/terminal/compaction row stay
  disabled, and session-log upload stays disabled;
* no unexpected enabled provider route or key field is present;
* the guard emitted ``RBG_BOOT`` and not ``RBG_BOOT_INVALID``;
* when requested, the STATIC OpenCode Go route shape is present with
  ``apiKeyEnv: OPENCODE_API_KEY`` (placeholder only), no ``baseURL``,
  ``reasoning: max`` and ``retryPolicy.maxRetries: 0``.

The script never reads a credential, never inspects the host home, and never
performs a model/network request. ``OPENCODE_API_KEY`` is *not* added to the
runtime environment; the route stays keyless and unusable.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

import yaml

DISABLED_ROWS = (
    "llm-deepseek", "plugin-package-inventory-deepseek", "compaction-basic",
    "image-offload", "tool-fs", "tool-working-directory", "persistent-bash",
    "persistent-pwsh", "terminal-bash", "terminal-pwsh", "pty", "subprocess", "jobs",
)
REQUIRED_ROWS = ("runtime-budget-guard", "offline-test-only-provider", "offline-public-skill")
EXPECTED_BASE_ROWS = (
    "sdk-app-startup", "sdk-jsonrpc-server", "deepseek-llm-api-extensions",
    "session-log-deepseek", "plugin-package-inventory-deepseek", "llm-deepseek",
    "sandbox", "filesystem", "attachment-local", "tool-fs", "working-directory",
    "tool-working-directory", "session-projection", "token-meter", "compaction-basic",
    "image-offload", "sandbox-policy", "subprocess", "pty", "terminal-bash",
    "terminal-pwsh", "timer", "llm", "session", "session-title", "system-prompt",
    "tools", "tool-executor-native", "mcp-resources", "agent", "llm-retry", "jobs",
    "agent-loop", "persistent-bash", "persistent-pwsh", "sessions",
    "session-checkpoint-policy",
)
INSERTED_ROWS = ("runtime-budget-guard", "offline-test-only-provider", "offline-public-skill")
KEY_NAME_FRAGMENTS = ("API_KEY", "SECRET", "PASSWORD", "CREDENTIAL")
CONTROLLED_ENV = {
    "PATH": "/opt/python/bin:/usr/bin",
    "PYTHONDONTWRITEBYTECODE": "1",
    "TMPDIR": "/tmp",
    "DSH_RUNTIME_MODE": "exe",
    "DSH_RESOURCE_CACHE": "/target/resources",
    "NARB_NATIVE_CACHE_DIR": "/target/native-cache",
    "PKG_NATIVE_CACHE_PATH": "/target/pkg-cache",
    "NO_COLOR": "1",
}


class InertLoader(yaml.SafeLoader):
    pass


InertLoader.add_constructor("tag:yaml.org,2002:js",
                            lambda loader, node: loader.construct_scalar(node))


def _fail(reasons: list[str], message: str) -> None:
    reasons.append(message)


def _guard_marker(stderr: str) -> tuple[bool, bool]:
    return "RBG_BOOT " in stderr or "RBG_BOOT {" in stderr, "RBG_BOOT_INVALID" in stderr


def _find_key_fields(node: object, path: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            text = str(key)
            upper = text.upper()
            if (any(fragment in upper for fragment in KEY_NAME_FRAGMENTS)
                    or upper.endswith("TOKEN") or "TOKEN_" in upper or "_TOKEN" in upper):
                found.append(f"{path}.{text}".lstrip("."))
            found.extend(_find_key_fields(value, f"{path}.{text}".lstrip(".")))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            found.extend(_find_key_fields(value, f"{path}[{index}]"))
    return found


def verify(*, binary: Path, profile: str, patches: list[Path], target_root: Path,
           dsh_home: Path, require_opencode_go: bool, dump_file: Path | None,
           runtime_stderr: Path | None = None, require_boot: bool = False,
           timeout_seconds: int = 20) -> dict:
    reasons: list[str] = []
    checks: dict[str, object] = {}
    start = time.monotonic()
    if binary is None or not binary.is_file():
        return {"status": "FAIL", "reasons": ["DSH_BINARY_MISSING"], "checks": checks}
    env = dict(CONTROLLED_ENV)
    env["HOME"] = str(dsh_home.parent)
    env["DSH_HOME"] = str(dsh_home)
    if dump_file is not None:
        stdout = dump_file.read_text(encoding="utf-8")
        stderr = runtime_stderr.read_text(encoding="utf-8") if runtime_stderr else ""
        code = 0
    else:
        argv = [str(binary), "--profile", profile]
        for patch in patches:
            argv += ["--patch", str(patch)]
        argv.append("--dump-config")
        completed = subprocess.run(argv, env=env, cwd=tempfile.gettempdir(),
                                   stdin=subprocess.DEVNULL, capture_output=True,
                                   text=True, timeout=timeout_seconds, check=False)
        stdout, stderr, code = completed.stdout, completed.stderr, completed.returncode
    checks["dump_exit_code"] = code
    checks["stderr_bytes"] = len(stderr.encode())
    checks["elapsed_seconds"] = round(time.monotonic() - start, 3)
    if code != 0:
        _fail(reasons, f"DUMP_CONFIG_EXIT_{code}")
    try:
        parsed = yaml.load(stdout, Loader=InertLoader)
        rows = {row["id"]: row for row in parsed} if isinstance(parsed, list) else None
    except (yaml.YAMLError, KeyError, TypeError):
        rows = None
    if not isinstance(rows, dict):
        _fail(reasons, "MERGED_CONFIG_NOT_A_ROW_LIST")
        return {"status": "FAIL", "reasons": reasons, "checks": checks}
    checks["row_ids"] = sorted(rows)
    for row_id in REQUIRED_ROWS:
        if row_id not in rows:
            _fail(reasons, f"MISSING_REQUIRED_ROW:{row_id}")
    for row_id in DISABLED_ROWS:
        row = rows.get(row_id)
        if row is not None and row.get("disabled") is not True:
            _fail(reasons, f"REAL_ROUTE_OR_DANGEROUS_ROW_ENABLED:{row_id}")
    session_log = rows.get("session-log-deepseek") or {}
    if (session_log.get("config") or {}).get("enabled") is not False:
        _fail(reasons, "SESSION_LOG_UPLOAD_NOT_DISABLED")
    guard = rows.get("runtime-budget-guard") or {}
    config = guard.get("config") or {}
    policy = config.get("policy") or {}
    broker = config.get("broker") or {}
    checks["guard_policy"] = {
        "provider": policy.get("provider"), "model": policy.get("model"),
        "maxProviderRetries": policy.get("maxProviderRetries"),
        "brokerScopeId": policy.get("brokerScopeId"),
    }
    if (policy.get("provider"), policy.get("model")) != ("offline-test-only", "fixture-v1"):
        _fail(reasons, "GUARD_POLICY_ROUTE_MISMATCH")
    if policy.get("maxProviderRetries") != 0:
        _fail(reasons, "GUARD_PROVIDER_RETRY_NOT_DISABLED")
    config_path = broker.get("configPath")
    if not isinstance(config_path, str) or not config_path.startswith(str(target_root) + "/"):
        _fail(reasons, "GUARD_BROKER_POLICY_PATH_OUTSIDE_TARGET_ROOT")
    else:
        try:
            payload = Path(config_path).read_bytes()
        except OSError:
            _fail(reasons, "GUARD_BROKER_POLICY_UNREADABLE")
        else:
            actual = hashlib.sha256(payload).hexdigest()
            checks["broker_policy_sha256"] = actual
            if actual != broker.get("configSha256"):
                _fail(reasons, "GUARD_BROKER_POLICY_HASH_MISMATCH")
    if not isinstance(broker.get("python"), str) or not broker["python"].startswith("/"):
        _fail(reasons, "GUARD_BROKER_PYTHON_NOT_FIXED_ABSOLUTE")
    if not isinstance(broker.get("pythonPath"), str):
        _fail(reasons, "GUARD_BROKER_PYTHONPATH_MISSING")
    key_fields = _find_key_fields(rows)
    checks["key_name_fields"] = key_fields
    if key_fields:
        _fail(reasons, f"UNEXPECTED_KEY_FIELD:{key_fields[0]}")
    allowed_rows = set(EXPECTED_BASE_ROWS) | set(INSERTED_ROWS)
    if require_opencode_go:
        allowed_rows.add("llm-pi-ai")
    for row_id in sorted(set(rows) - allowed_rows):
        _fail(reasons, f"UNEXPECTED_PROVIDER_ROW:{row_id}")
    for row_id in sorted(allowed_rows - set(rows)):
        _fail(reasons, f"MISSING_REQUIRED_ROW:{row_id}")
    boot, boot_invalid = _guard_marker(stderr)
    checks["guard_boot_marker"] = boot
    checks["guard_boot_invalid_marker"] = boot_invalid
    if boot_invalid:
        _fail(reasons, "GUARD_BOOT_INVALID_DENY_ALL")
    elif not boot:
        if require_boot:
            _fail(reasons, "GUARD_RBG_BOOT_MARKER_MISSING")
        else:
            checks["guard_boot_marker"] = "NOT_OBSERVED_DUMP_CONFIG_ONLY"
    if require_opencode_go:
        pi_ai = rows.get("llm-pi-ai") or {}
        providers = ((pi_ai.get("config") or {}).get("providers") or {})
        route = providers.get("opencode-go") if isinstance(providers, dict) else None
        checks["opencode_go_present"] = route is not None
        if route is None:
            _fail(reasons, "OPENCODE_GO_ROUTE_MISSING")
        else:
            checks["opencode_go"] = {
                "apiKeyEnv": route.get("apiKeyEnv"),
                "baseURL": route.get("baseURL"),
                "reasoning": route.get("reasoning"),
                "retryPolicy": route.get("retryPolicy"),
            }
            if route.get("apiKeyEnv") != "OPENCODE_API_KEY":
                _fail(reasons, "OPENCODE_GO_API_KEY_ENV_NOT_PLACEHOLDER")
            if "baseURL" in route:
                _fail(reasons, "OPENCODE_GO_BASEURL_OVERRIDE_FORBIDDEN")
            if route.get("reasoning") != "max":
                _fail(reasons, "OPENCODE_GO_REASONING_NOT_MAX")
            retry = route.get("retryPolicy") or {}
            if retry.get("maxRetries") != 0:
                _fail(reasons, "OPENCODE_GO_RETRY_NOT_ZERO")
    status = "PASS" if not reasons else "FAIL"
    return {"status": status, "reasons": reasons, "checks": checks,
            "dump_stdout_sha256": hashlib.sha256(stdout.encode()).hexdigest(),
            "dump_stderr_sha256": hashlib.sha256(stderr.encode()).hexdigest()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only PR2 target profile verifier")
    parser.add_argument("--binary", type=Path,
                        default=Path(os.environ.get("DSH_BIN", "/deps/deepseek_harness_runtime/"
                                                    "runtime/deepseek-harness-sdk-runtime-linux-x64")))
    parser.add_argument("--profile", default="sdk-minimal")
    parser.add_argument("--patch", action="append", type=Path, default=[])
    parser.add_argument("--target-root", type=Path, default=Path("/target"))
    parser.add_argument("--dsh-home", type=Path, default=Path("/work/at-m0-pr2-verify"))
    parser.add_argument("--require-opencode-go", action="store_true")
    parser.add_argument("--dump-file", type=Path)
    parser.add_argument("--runtime-stderr", type=Path)
    parser.add_argument("--require-boot", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=20)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    result = verify(binary=args.binary, profile=args.profile, patches=args.patch,
                    target_root=args.target_root, dsh_home=args.dsh_home,
                    require_opencode_go=args.require_opencode_go, dump_file=args.dump_file,
                    runtime_stderr=args.runtime_stderr, require_boot=args.require_boot,
                    timeout_seconds=args.timeout_seconds)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 20


if __name__ == "__main__":
    raise SystemExit(main())
