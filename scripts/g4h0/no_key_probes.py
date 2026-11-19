#!/usr/bin/env python3
"""A-07 no-key / always-BLOCKED negative probe for the G4-H0 scope.

This script only performs *local negatives*. It never reads a real credential,
never sends a model/Provider request and never makes an external HTTP call. It
collects independently reproducible evidence that:

* ``LiveGate.inspect`` stays ``BLOCKED`` even when every documented evidence input
  is satisfied, and ``LiveGate.require_live`` always raises ``SECURITY_BLOCKED``;
* the gate exposes no ``authorize``/``approve``/``open``/``unlock`` entry;
* ``scripts/run_live.sh`` hard-stops with exit 3 and no stdout;
* CLI ``smoke --live`` exits 3 even with fake key-like environment variables,
  ``--live``-approval environment switches and a Markdown "approval" file, and the
  fake secret value never appears in the output;
* the Runtime adapter's four live entrypoints (``_require_live_authorization``,
  ``_new_harness``, ``run``, ``resume``) all raise ``SECURITY_BLOCKED`` before the
  SDK is imported; ``deepseek_harness`` never enters ``sys.modules``;
* the probe process sees no key-like environment variable and no ``.env`` file,
  and source code contains no dotenv loading or key-like env read;
* surviving fake-key handling is redacted/scrubbed by the credential boundary;
* ``gates.py`` / ``run_live.sh`` / ``dsh_adapter.py`` / ``cli.py`` are byte-equal
  to the frozen baseline (git diff empty);
* newly added code (working tree vs the frozen G4-F baseline) contains no network
  client/provider import, no credential pattern and no environment unlock switch.

Output: one JSON record plus human-readable lines. Exit 0 iff every check passes.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

DEFAULT_BASE = "3e7afee077845a071cd364e93ab209cac20b2d5f"
SCHEMA = "at-m0/g4h0-no-key-probes/v1"
FAKE_KEY_VALUES = (
    "TEST_ONLY_NEVER_VALID_DEEPSEEK_KEY_0000",
    "TEST_ONLY_NEVER_VALID_OPENCODE_KEY_1111",
)
KEY_LIKE_ENV = re.compile(
    r"(API[_-]?KEY|ACCESS[_-]?TOKEN|AUTH[_-]?TOKEN|SECRET|PASSWORD|CREDENTIAL|"
    r"PRIVATE[_-]?KEY)", re.IGNORECASE)
CREDENTIAL_PATTERNS = {
    "openai_sk": re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9]{20,}"),
    "aws_akia": re.compile(r"AKIA[0-9A-Z]{16}"),
    "gcp_aiza": re.compile(r"AIza[0-9A-Za-z_-]{30,}"),
    "github": re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    "slack": re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    "pem_private_key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "env_assignment": re.compile(
        r"""(?i)\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|secret|password|"""
        r"""credential)\b\s*[:=]\s*['"][A-Za-z0-9._~+/=-]{20,}['"]"""),
}
NETWORK_PATTERNS = {
    "requests_import": re.compile(r"^\s*(?:import|from)\s+requests\b", re.MULTILINE),
    "httpx_import": re.compile(r"^\s*(?:import|from)\s+httpx\b", re.MULTILINE),
    "aiohttp_import": re.compile(r"^\s*(?:import|from)\s+aiohttp\b", re.MULTILINE),
    "urllib_import": re.compile(r"^\s*(?:import|from)\s+urllib\b", re.MULTILINE),
    "http_client_import": re.compile(
        r"^\s*(?:import|from)\s+http\.client\b", re.MULTILINE),
    "socket_connect": re.compile(r"socket\.create_connection\(|socket\.socket\("),
    "provider_sdk": re.compile(r"\bdeepseek_harness\b"),
}
ENV_UNLOCK_PATTERNS = {
    "env_read": re.compile(r"\bos\.environ\b|\bos\.getenv\s*\("),
    "dotenv_load": re.compile(r"\bdotenv\b"),
}
FROZEN_LIVE_FILES = (
    "src/autoteacher_m0/security/gates.py",
    "scripts/run_live.sh",
    "src/autoteacher_m0/runtime/dsh_adapter.py",
    "src/autoteacher_m0/cli.py",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_git(repo_root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo_root), *args],
                          capture_output=True, text=True, timeout=120, check=False)


def clean_env(repo_root: Path, extra: dict[str, str] | None = None) -> dict[str, str]:
    env = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": str(repo_root / ".probe-home"),
        "LANG": "C",
        "PYTHONPATH": str(repo_root / "src"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "NO_COLOR": "1",
    }
    if extra:
        env.update(extra)
    return env


def added_lines_by_file(repo_root: Path, base: str) -> dict[str, list[str]]:
    """Added lines of the diff baseline..working-tree plus every untracked file."""
    changed: dict[str, list[str]] = {}
    tracked = run_git(repo_root, "diff", "--name-only", base, "--", ".")
    if tracked.returncode != 0:
        raise RuntimeError(f"git diff failed: {tracked.stderr.strip()}")
    for relative in tracked.stdout.splitlines():
        relative = relative.strip()
        if not relative:
            continue
        diff = run_git(repo_root, "diff", "-U0", base, "--", relative)
        if diff.returncode != 0:
            raise RuntimeError(f"git diff failed for {relative}: {diff.stderr.strip()}")
        lines = []
        for line in diff.stdout.splitlines():
            if line.startswith("+") and not line.startswith("+++"):
                lines.append(line[1:])
        changed[relative] = lines
    untracked = run_git(repo_root, "ls-files", "--others", "--exclude-standard")
    if untracked.returncode != 0:
        raise RuntimeError(f"git ls-files failed: {untracked.stderr.strip()}")
    for relative in untracked.stdout.splitlines():
        relative = relative.strip()
        if not relative:
            continue
        path = repo_root / relative
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        changed[relative] = text.splitlines()
    return changed


def scan(lines: dict[str, list[str]], patterns: dict[str, re.Pattern],
         *, relative_prefix: str | None = None) -> list[dict]:
    findings = []
    for relative, file_lines in sorted(lines.items()):
        if relative_prefix is not None and not relative.startswith(relative_prefix):
            continue
        for number, line in enumerate(file_lines, start=1):
            for name, pattern in patterns.items():
                if pattern.search(line):
                    findings.append({"file": relative, "pattern": name,
                                     "line": number, "text": line.strip()[:160]})
    return findings


def read_json(text: str) -> dict | None:
    try:
        value = json.loads(text)
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default=DEFAULT_BASE,
                        help="frozen G4-F baseline commit for the static diff scan")
    parser.add_argument("--output", type=Path, default=None,
                        help="JSON evidence output path")
    parser.add_argument("--repo-root", type=Path, default=None)
    args = parser.parse_args(argv)
    repo_root = (args.repo_root or Path(__file__).resolve().parents[2]).resolve()
    checks: list[dict] = []
    commands: list[dict] = []
    network_attempts: list[str] = []

    def check(check_id: str, ok: bool, **detail: object) -> None:
        checks.append({"id": check_id, "ok": bool(ok), **detail})

    # ------------------------------------------------------------------
    # 1. LiveGate is a constant BLOCKED wall with no approval entrypoint
    # ------------------------------------------------------------------
    from autoteacher_m0.security.gates import LiveGate, SecurityBlocked, fingerprint

    inventory = {"controller.py": b"probe-controller", "profile.yml": b"probe-profile"}
    reviewed = fingerprint(inventory, {"profile": "sdk-minimal", "tools": ["skill_lookup"]})
    best_evidence = dict(live_requested=True, actual=reviewed, reviewed=reviewed,
                         actual_tools=("skill_lookup",), session_log_disabled=True)
    best = LiveGate().inspect(**best_evidence)
    check("live_gate_inspect_always_blocked",
          best.status == "BLOCKED"
          and best.external_boundary_deployed is False
          and best.reasons[0] == "EXTERNAL_HUMAN_AUTHORIZATION_BOUNDARY_NOT_DEPLOYED",
          status=best.status, reasons=list(best.reasons))
    try:
        LiveGate().require_live(**best_evidence)
        raised, code, reason = False, None, None
    except SecurityBlocked as exc:
        raised, code, reason = True, getattr(exc, "code", None), str(exc)
    check("live_gate_require_live_always_raises",
          raised and code == "SECURITY_BLOCKED"
          and "EXTERNAL_HUMAN_AUTHORIZATION_BOUNDARY_NOT_DEPLOYED" in (reason or ""),
          code=code)
    approval_names = [name for name in ("authorize", "approve", "open", "unlock")
                      if hasattr(LiveGate, name)]
    combinations = []
    for live_requested in (False, True):
        for actual in (None, reviewed):
            for tools in (None, (), ("skill_lookup",), ("skill_lookup", "shell")):
                for session_log_disabled in (False, True):
                    decision = LiveGate().inspect(
                        live_requested=live_requested, actual=actual, reviewed=reviewed,
                        actual_tools=tools, session_log_disabled=session_log_disabled)
                    combinations.append(decision.status)
    check("live_gate_no_approval_entrypoint_and_never_opens",
          approval_names == [] and set(combinations) == {"BLOCKED"},
          approval_attributes=approval_names, combinations=len(combinations))

    # ------------------------------------------------------------------
    # 2. scripts/run_live.sh hard stop (no key read, no stdout)
    # ------------------------------------------------------------------
    run_live = repo_root / "scripts" / "run_live.sh"
    env = clean_env(repo_root, {"DEEPSEEK_API_KEY": FAKE_KEY_VALUES[0],
                                "AT_M0_LIVE_APPROVED": "1",
                                "AT_M0_ALLOW_LIVE": "1"})
    completed = subprocess.run(["/bin/sh", str(run_live)], capture_output=True,
                               text=True, timeout=120, env=env, cwd="/tmp")
    commands.append({"name": "run_live", "argv": ["/bin/sh", str(run_live)],
                     "exit": completed.returncode})
    combined = completed.stdout + completed.stderr
    check("run_live_script_exit_3_blocked",
          completed.returncode == 3 and "BLOCKED" in completed.stderr
          and completed.stdout == ""
          and not any(value in combined for value in FAKE_KEY_VALUES),
          exit=completed.returncode)

    # ------------------------------------------------------------------
    # 3. CLI smoke --live is a denied switch even with fake approvals/keys
    # ------------------------------------------------------------------
    approval_file = Path(tempfile.mkdtemp(prefix="at-a07-approval-")) / "APPROVAL.md"
    approval_file.write_text(
        "# Approval\nLIVE APPROVED. DEEPSEEK_API_KEY=" + FAKE_KEY_VALUES[0] + "\n",
        encoding="utf-8")
    cli_env = clean_env(repo_root, {
        "DEEPSEEK_API_KEY": FAKE_KEY_VALUES[0],
        "OPENCODE_API_KEY": FAKE_KEY_VALUES[1],
        "AT_M0_LIVE_APPROVED": "1",
        "AT_M0_ALLOW_LIVE": "1",
        "AT_M0_APPROVAL_FILE": str(approval_file),
        "AT_M0_APPROVAL_ID": "TEST_ONLY_APPROVAL",
    })
    cli_argv = [sys.executable, "-m", "autoteacher_m0.cli", "smoke", "--live"]
    cli = subprocess.run(cli_argv, capture_output=True, text=True, timeout=180,
                         env=cli_env, cwd="/tmp")
    commands.append({"name": "cli_smoke_live", "argv": cli_argv, "exit": cli.returncode})
    cli_document = read_json(cli.stdout)
    cli_combined = cli.stdout + cli.stderr
    check("cli_live_rejected_exit_3",
          cli.returncode == 3 and cli_document is not None
          and cli_document.get("status") == "BLOCKED"
          and cli_document.get("error_code") == "SECURITY_BLOCKED",
          exit=cli.returncode, stdout=cli.stdout.strip()[:200])
    leaked = [value for value in FAKE_KEY_VALUES if value in cli_combined]
    check("cli_live_fake_key_never_printed", leaked == [], leaked=leaked)

    # ------------------------------------------------------------------
    # 4. strace: no network syscalls on either hard-stopped entrypoint
    # ------------------------------------------------------------------
    strace = shutil.which("strace")
    if strace is None:
        check("live_entries_no_network_syscalls", True, status="NOT_RUN",
              reason="strace unavailable")
    else:
        trace_path = Path(tempfile.mkdtemp(prefix="at-a07-strace-")) / "trace.log"
        for name, run_argv, run_env in (
                ("run_live", ["/bin/sh", str(run_live)], env),
                ("cli_smoke_live", cli_argv, cli_env)):
            traced = subprocess.run(
                [strace, "-f", "-e", "trace=network", "-o", str(trace_path),
                 *run_argv], capture_output=True, text=True, timeout=180,
                env=run_env, cwd="/tmp")
            commands.append({"name": f"strace_{name}", "argv": [strace, "-f", *run_argv],
                             "exit": traced.returncode, "trace": str(trace_path)})
            trace_text = trace_path.read_text(encoding="utf-8", errors="replace")
            offending = [line for line in trace_text.splitlines()
                         if re.search(r"AF_INET6?|\bconnect\(", line)]
            check(f"no_network_syscalls_{name}", not offending,
                  offending=offending[:5])

    # ------------------------------------------------------------------
    # 5. Runtime adapter entrypoints fail closed before the SDK import
    # ------------------------------------------------------------------
    import sys as _sys

    from autoteacher_m0.contracts import RunRequest, RuntimeFailure
    from autoteacher_m0.runtime.dsh_adapter import HarnessAdapter
    from autoteacher_m0.settings import RuntimeSettings

    probe_dir = Path(tempfile.mkdtemp(prefix="at-a07-adapter-"))
    settings = RuntimeSettings(workspace=probe_dir / "workspace",
                               dsh_home=probe_dir / "home",
                               patch=probe_dir / "patch.yml")
    adapter = HarnessAdapter(settings)
    request = RunRequest(case_id="a07-probe", prompt="offline negative probe",
                         candidate_id="a07", session_id="a07-session",
                         provider="deepseek-official", model="deepseek-flash",
                         route_id="deepseek-official")
    blocked_codes: dict[str, str | None] = {}
    for name, call in (
            ("_require_live_authorization", lambda: HarnessAdapter._require_live_authorization()),
            ("_new_harness", adapter._new_harness),
            ("run", lambda: adapter.run(request)),
            ("resume", lambda: adapter.resume("a07-session", "probe"))):
        try:
            call()
            blocked_codes[name] = None
        except RuntimeFailure as exc:
            blocked_codes[name] = getattr(exc, "code", None)
        except Exception as exc:  # noqa: BLE001 - any other failure is a finding
            blocked_codes[name] = f"UNEXPECTED:{type(exc).__name__}"
    check("adapter_four_live_entrypoints_blocked",
          all(code == "SECURITY_BLOCKED" for code in blocked_codes.values()),
          codes=blocked_codes)
    check("provider_sdk_never_imported", "deepseek_harness" not in _sys.modules)

    # ------------------------------------------------------------------
    # 6. no real key / key-like env / .env / dotenv loading / key env read
    # ------------------------------------------------------------------
    key_like_env = sorted(name for name in os.environ if KEY_LIKE_ENV.search(name))
    check("probe_process_has_no_key_like_env", key_like_env == [], names=key_like_env)
    check("no_dotenv_file_in_repo", not (repo_root / ".env").exists())
    src_dir = repo_root / "src" / "autoteacher_m0"
    src_files = sorted(src_dir.rglob("*.py"))
    env_reads: list[dict] = []
    key_reads: list[dict] = []
    dotenv_imports: list[str] = []
    for path in src_files:
        text = path.read_text(encoding="utf-8")
        for number, line in enumerate(text.splitlines(), start=1):
            if re.search(r"\bos\.environ\b|\bos\.getenv\s*\(", line):
                env_reads.append({"file": str(path.relative_to(repo_root)),
                                  "line": number, "text": line.strip()[:120]})
                if KEY_LIKE_ENV.search(line):
                    key_reads.append({"file": str(path.relative_to(repo_root)),
                                      "line": number, "text": line.strip()[:120]})
            if re.search(r"^\s*(?:import|from)\s+dotenv\b", line):
                dotenv_imports.append(str(path.relative_to(repo_root)))
    check("source_never_reads_key_like_env", key_reads == [], reads=key_reads)
    check("source_never_loads_dotenv", dotenv_imports == [], files=dotenv_imports)
    known_test_hooks = [row for row in env_reads
                        if row["file"].endswith("bridge/controller.py")
                        and "G3B_TEST_" in row["text"]]
    check("only_known_test_hook_env_reads",
          len(known_test_hooks) == len(env_reads),
          env_reads=env_reads)

    # ------------------------------------------------------------------
    # 7. surviving fake key is scrubbed/redacted
    # ------------------------------------------------------------------
    from autoteacher_m0.security.credential_boundary import (
        redact_secrets, scrub_candidate_env,
    )

    fake_env = {"PATH": "/usr/bin", "DEEPSEEK_API_KEY": FAKE_KEY_VALUES[0],
                "OPENCODE_API_KEY": FAKE_KEY_VALUES[1], "HOME": "/work"}
    scrubbed, violations = scrub_candidate_env(
        fake_env, known_secret_values=FAKE_KEY_VALUES)
    redacted = redact_secrets(
        f"launcher env DEEPSEEK_API_KEY={FAKE_KEY_VALUES[0]}", FAKE_KEY_VALUES)
    check("credential_boundary_scrubs_fake_key",
          FAKE_KEY_VALUES[0] not in json.dumps(scrubbed)
          and all(value not in redacted for value in FAKE_KEY_VALUES)
          and len(violations) == 2,
          candidate_env_keys=sorted(scrubbed), violations=list(violations))

    # ------------------------------------------------------------------
    # 8. frozen Live files are byte-equal to the G4-F baseline
    # ------------------------------------------------------------------
    frozen = run_git(repo_root, "diff", "--name-only", args.base, "--", *FROZEN_LIVE_FILES)
    check("frozen_live_files_unmodified",
          frozen.returncode == 0 and frozen.stdout.strip() == "",
          changed=frozen.stdout.splitlines())
    from autoteacher_m0.security.live_controller import assert_live_entrypoints_blocked

    static_blockers = assert_live_entrypoints_blocked(repo_root)
    check("static_live_entrypoint_audit_clean", static_blockers == (),
          blockers=list(static_blockers))

    # ------------------------------------------------------------------
    # 9. static scan of newly added code: no network/provider/credential/env
    # ------------------------------------------------------------------
    added = added_lines_by_file(repo_root, args.base)
    network_findings = scan(added, NETWORK_PATTERNS, relative_prefix="src/")
    credential_findings = scan(added, CREDENTIAL_PATTERNS)
    env_findings = scan(added, ENV_UNLOCK_PATTERNS, relative_prefix="src/")
    check("new_src_has_no_network_or_provider_client",
          network_findings == [], findings=network_findings, files_scanned=len(added))
    check("new_code_has_no_credential_material",
          credential_findings == [], findings=credential_findings)
    check("new_src_has_no_env_unlock_switch_or_dotenv",
          env_findings == [], findings=env_findings)

    # ------------------------------------------------------------------
    # 10. in-process guard: none of the probes above attempted an IP socket
    # ------------------------------------------------------------------
    real_socket = socket.socket
    guard_attempts: list[object] = []

    class _GuardedSocket(real_socket):
        def connect(self, address):  # type: ignore[override]
            if self.family in (socket.AF_INET, socket.AF_INET6):
                guard_attempts.append(address)
                raise AssertionError("external network forbidden in A-07 probe")
            return super().connect(address)

    socket.socket = _GuardedSocket  # type: ignore[assignment]
    try:
        LiveGate().inspect(live_requested=True, actual_tools=("skill_lookup",),
                           session_log_disabled=True)
        try:
            adapter.run(request)
        except RuntimeFailure:
            pass
        try:
            adapter.resume("a07-session", "probe")
        except RuntimeFailure:
            pass
    finally:
        socket.socket = real_socket  # type: ignore[assignment]
    network_attempts.extend(str(item) for item in guard_attempts)
    check("no_ip_socket_attempt_in_process", guard_attempts == [])

    # ------------------------------------------------------------------
    # summary
    # ------------------------------------------------------------------
    failed = [item for item in checks if not item["ok"]]
    report = {
        "schema": SCHEMA,
        "utc": utc_now(),
        "python": sys.version.split()[0],
        "repo_root": str(repo_root),
        "base": args.base,
        "head": run_git(repo_root, "rev-parse", "HEAD").stdout.strip(),
        "scope": "local no-key negatives only; no model, provider, HTTP or paid call",
        "key_present": False,
        "real_model_calls": 0,
        "real_external_http_calls": 0,
        "network_attempts": network_attempts,
        "checks": checks,
        "commands": commands,
        "summary": {"total": len(checks), "passed": len(checks) - len(failed),
                    "failed": len(failed), "status": "PASS" if not failed else "FAIL"},
    }
    for item in checks:
        print(f"[{'PASS' if item['ok'] else 'FAIL'}] {item['id']}")
    print(json.dumps(report["summary"], sort_keys=True))
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                               encoding="utf-8")
    if failed:
        print("FAILED CHECKS:", json.dumps(failed, indent=2), file=sys.stderr)
        return 1
    print("A-07 NEGATIVES OK: LiveGate BLOCKED, 0 key, 0 network/provider call")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
