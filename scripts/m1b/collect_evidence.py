#!/usr/bin/env python3
"""M1-B independent evidence collector (offline, stdlib only, append-only).

This tool is the *collector* of the M1-B evidence packet.  It executes one
pre-declared verification command, stores the raw evidence under
``<out>/raw/<run_id>/`` and appends exactly one entry to the append-only
``<out>/audit-index.jsonl`` (plus a materialised ``<out>/audit-index.json``
view).  The downstream consumer (Reviewer/Lead) is responsible for reading
the raw evidence and for assigning the evidence class (``MOCK`` /
``DETERMINISTIC`` / ``INDEPENDENTLY_REEXECUTED`` ...); the collector itself
must never turn an execution result into a product PASS claim.

Status semantics (deliberately narrow; see docs/M1_B_EVIDENCE_PACKET.md):

* ``EXECUTED_PASS``  - the command was executed and exited with code 0.
  This is an execution outcome only, **not** an evidence/product PASS.
* ``EXECUTED_FAIL``  - the command was executed but exited non-zero, timed
  out, or a requested artifact could not be hashed.
* ``NOT_RUN``        - the command was rejected by the preflight policy, the
  executable could not be found, no command was supplied, or the collector
  refused to write a partial record.  Never PASS.

The tool is intentionally conservative:

* stdlib only, no network imports, no shell (``shell=False``);
* commands are parsed with :mod:`shlex` and validated against a small
  allowlist (``--allow-any-command`` relaxes the allowlist for trusted
  Reviewer commands, but a hard deny list and git-subcommand deny list still
  apply);
* ``--cwd`` must resolve to a path inside the repository root;
* obvious credential environment variables are stripped from the child
  process environment before execution;
* the append-only index is never rewritten; malformed existing indexes are
  rejected instead of repaired.

Typical usage (Reviewer, from the repository root)::

    python scripts/m1b/collect_evidence.py \\
        --out /tmp/m1b_evidence/B1-05 \\
        --case-id B1-05 \\
        --command "python -m pytest tests/m1_teacher/test_assessment_scorer.py -q" \\
        --expected-exit 0 \\
        --artifact docs/m1a_evidence/e2e_summary.json \\
        --limitation "synthetic fixtures only"

The command is executed with ``shell=False``; every token is passed as a
separate argv entry.  The command never comes from a fixture/artifact file:
it is only supplied by the caller on the trusted command line.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

COLLECTOR_NAME = "m1b.collect-evidence"
COLLECTOR_VERSION = "m1b.collect-evidence.v0"
AUDIT_SCHEMA_VERSION = "m1b.audit-index.v0"
AUDIT_INDEX_JSONL = "audit-index.jsonl"
AUDIT_INDEX_JSON = "audit-index.json"
RAW_DIR = "raw"
MAX_LOG_BYTES = 2 * 1024 * 1024
TAIL_CHARS = 2000
DEFAULT_TIMEOUT_SECONDS = 1800.0

PACKET_README_FILENAME = "README.md"
PACKET_README_TEXT = """# M1-B evidence packet (offline, synthetic only)

This directory is an append-only evidence packet produced by
`scripts/m1b/collect_evidence.py`.

- `audit-index.jsonl` - authoritative append-only audit index (one JSON object per run).
- `audit-index.json` - materialised view of the same entries (rewritten atomically; entries
  are never dropped or altered).
- `raw/<run_id>/evidence.json` - the hashed raw evidence for one run (command, environment,
  exit code, stdout/stderr summaries, artifacts).
- `raw/<run_id>/stdout.log` / `stderr.log` - captured streams (capped at 2 MiB each).

Boundary: **offline synthetic only, not real teaching effect**. `EXECUTED_PASS` is an
execution outcome and is NOT a product/evidence PASS. Evidence classes (`MOCK`,
`DETERMINISTIC`, `INDEPENDENTLY_REEXECUTED`, ...) must be assigned by the Reviewer; the
collector never upgrades an execution result into a product PASS claim. No real API key,
network access, real learner data or real provider is used. `utc` timestamps in the index
are wall-clock audit metadata and must not be treated as deterministic artifact content.
A packet without a command, without a hash, or without Reviewer re-execution cannot be
used as PASS evidence.
"""

EVIDENCE_CLASSES = frozenset(
    {
        "MOCK",
        "DETERMINISTIC",
        "HUMAN_REVIEWED",
        "NOT_VERIFIED",
        "UNVERIFIED",
        "BLOCKED",
        "NOT_RUN",
        "INDEPENDENTLY_REEXECUTED",
    }
)

EXIT_OK = 0
EXIT_REJECTED = 2

CASE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")

TZ_KEYS = ("TZ",)
EXTRA_ENV_KEYS = ("PYTHONHASHSEED",)

# Executables accepted without --allow-any-command.  The check uses the
# basename, so /root/.../.venv/bin/python is accepted as ``python``.
DEFAULT_ALLOWED_EXECUTABLES = frozenset(
    {
        "python",
        "python3",
        "python3.11",
        "python3.12",
        "pytest",
        "ruff",
        "echo",
        "git",
    }
)

# Never allowed, not even with --allow-any-command.
HARD_DENIED_EXECUTABLES = frozenset(
    {
        "bash",
        "sh",
        "zsh",
        "csh",
        "ksh",
        "fish",
        "eval",
        "exec",
        "rm",
        "rmdir",
        "shred",
        "dd",
        "mkfs",
        "mkfs.ext4",
        "mkfs.xfs",
        "sudo",
        "su",
        "curl",
        "wget",
        "ssh",
        "scp",
        "sftp",
        "nc",
        "ncat",
        "telnet",
        "ftp",
        "kill",
        "pkill",
        "killall",
        "chmod",
        "chown",
        "chgrp",
        "systemctl",
        "service",
        "mount",
        "umount",
        "apt",
        "apt-get",
        "yum",
        "dnf",
        "pacman",
        "pip",
        "pip3",
        "uv",
        "npm",
        "npx",
        "yarn",
        "docker",
        "podman",
    }
)

SAFE_GIT_SUBCOMMANDS = frozenset(
    {
        "diff",
        "log",
        "show",
        "rev-parse",
        "status",
        "ls-files",
        "cat-file",
        "grep",
    }
)

SHELL_METACHARACTERS = frozenset({";", "&&", "||", "|", "&", "<", ">", ">>", "`", "$("})

SENSITIVE_ENV_KEY_RE = re.compile(
    r"(api[_-]?key|token|secret|password|credential|provider)", re.IGNORECASE
)

FORBIDDEN_IMPORTS = frozenset(
    {
        "socket",
        "ssl",
        "http",
        "urllib",
        "urllib2",
        "urllib3",
        "requests",
        "httpx",
        "aiohttp",
        "ftplib",
        "smtplib",
        "telnetlib",
    }
)


class EvidenceError(Exception):
    """Raised when a record cannot be written safely (preflight rejection)."""


def utc_now() -> str:
    """Return the current wall-clock UTC time in ISO-8601 with ``Z`` suffix."""

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_bytes(data: bytes) -> str:
    """Return the hex SHA-256 of ``data``."""

    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    """Return the hex SHA-256 of a file."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _basename(token: str) -> str:
    return Path(token).name


def _git_value(repo_root: Path, *args: str) -> str | None:
    """Best-effort read-only git query; never raises."""

    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            capture_output=True,
            text=True,
            timeout=10,
            shell=False,
            check=False,
            env=_child_env(),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = completed.stdout.strip()
    if completed.returncode != 0 or not value:
        return None
    return value


def _child_env() -> dict[str, str]:
    """Return a copy of the environment with obvious credentials removed."""

    env = {key: value for key, value in os.environ.items()}
    for key in list(env):
        if SENSITIVE_ENV_KEY_RE.search(key):
            env.pop(key, None)
    return env


def _resolve_executable(token: str) -> str | None:
    """Return the executable path if it can be resolved, else ``None``."""

    if os.sep in token or (os.altsep and os.altsep in token):
        candidate = Path(token)
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
        return None
    return shutil.which(token)


def validate_command(command: str, *, allow_any_command: bool) -> list[str]:
    """Parse and validate a command string; return the argv list.

    Raises :class:`EvidenceError` with a human-readable reason when the
    command must not be executed.
    """

    if not command or not command.strip():
        raise EvidenceError("empty command")
    if "\x00" in command:
        raise EvidenceError("command contains NUL byte")
    if "\n" in command or "\r" in command:
        raise EvidenceError("command contains a newline; pass a single command")
    try:
        argv = shlex.split(command, posix=True)
    except ValueError as exc:
        raise EvidenceError(f"cannot parse command: {exc}") from exc
    if not argv:
        raise EvidenceError("command parsed to an empty argv")

    for token in argv:
        if token in SHELL_METACHARACTERS or token.startswith("$(") or token.startswith("`"):
            raise EvidenceError(
                "shell metacharacters are not supported (shell=False); pass a plain argv command"
            )

    executable = _basename(argv[0])
    if executable in HARD_DENIED_EXECUTABLES:
        raise EvidenceError(f"executable is hard-denied: {executable}")
    if executable == "git":
        if len(argv) < 2 or argv[1] not in SAFE_GIT_SUBCOMMANDS:
            raise EvidenceError(
                "git commands are limited to safe read-only subcommands: "
                + ", ".join(sorted(SAFE_GIT_SUBCOMMANDS))
            )
    if executable not in DEFAULT_ALLOWED_EXECUTABLES and not allow_any_command:
        raise EvidenceError(
            f"executable is not on the default allowlist: {executable}; "
            "use --allow-any-command for a trusted Reviewer command"
        )

    resolved = _resolve_executable(argv[0])
    if resolved is None:
        raise EvidenceError(f"executable cannot be resolved: {argv[0]}")
    return argv


def validate_cwd(cwd: Path, repo_root: Path) -> Path:
    """Resolve ``cwd`` and require it to live inside ``repo_root``."""

    try:
        resolved_cwd = cwd.resolve(strict=True)
    except OSError as exc:
        raise EvidenceError(f"cwd does not exist: {cwd} ({exc})") from exc
    if not resolved_cwd.is_dir():
        raise EvidenceError(f"cwd is not a directory: {cwd}")
    try:
        resolved_cwd.relative_to(repo_root.resolve())
    except ValueError as exc:
        raise EvidenceError(
            f"cwd must stay inside the repository root {repo_root}: {resolved_cwd}"
        ) from exc
    return resolved_cwd


def resolve_artifact(path_token: str, cwd: Path, repo_root: Path) -> dict[str, Any]:
    """Return an artifact record with sha256/bytes when the path exists."""

    candidate = Path(path_token)
    if not candidate.is_absolute():
        candidate = cwd / candidate
    resolved = candidate.resolve()
    if not resolved.is_file():
        return {
            "requested": path_token,
            "path": str(resolved),
            "exists": False,
            "error": "artifact does not exist or is not a regular file",
        }
    record: dict[str, Any] = {
        "requested": path_token,
        "path": str(resolved),
        "exists": True,
        "sha256": sha256_file(resolved),
        "bytes": resolved.stat().st_size,
    }
    try:
        record["repo_relative"] = str(resolved.relative_to(repo_root.resolve()))
    except ValueError:
        record["repo_relative"] = None
    return record


def summarize_stream(data: bytes, *, limit: int = MAX_LOG_BYTES) -> dict[str, Any]:
    """Return a deterministic summary of a captured stdout/stderr stream."""

    truncated = len(data) > limit
    kept = data[:limit]
    text = kept.decode("utf-8", errors="replace")
    return {
        "bytes": len(data),
        "sha256": sha256_bytes(data),
        "truncated": truncated,
        "tail": text[-TAIL_CHARS:],
    }


def _read_existing_entries(index_path: Path) -> list[dict[str, Any]]:
    """Read and validate the existing append-only JSONL index."""

    if not index_path.exists():
        return []
    entries: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(
        index_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not raw_line.strip():
            continue
        try:
            entry = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            raise EvidenceError(
                f"existing {AUDIT_INDEX_JSONL} is malformed at line {line_number}: {exc}"
            ) from exc
        if not isinstance(entry, dict):
            raise EvidenceError(
                f"existing {AUDIT_INDEX_JSONL} line {line_number} is not a JSON object"
            )
        entries.append(entry)
    return entries


def _write_json_atomic(path: Path, payload: Any) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    temp_path = path.with_name(path.name + ".tmp")
    temp_path.write_text(text, encoding="utf-8")
    os.replace(temp_path, path)


def _append_jsonl(path: Path, entry: dict[str, Any]) -> None:
    line = json.dumps(entry, ensure_ascii=False, sort_keys=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def _materialize_index_json(index_path_json: Path, entries: Sequence[dict[str, Any]]) -> None:
    _write_json_atomic(
        index_path_json,
        {
            "schema_version": AUDIT_SCHEMA_VERSION,
            "entry_count": len(entries),
            "entries": list(entries),
        },
    )


def _ensure_packet_readme(out_dir: Path) -> None:
    """Create the packet boundary README once; never overwrite an existing one."""

    readme = out_dir / PACKET_README_FILENAME
    if not readme.exists():
        readme.write_text(PACKET_README_TEXT, encoding="utf-8")


def _new_run_id(case_id: str) -> str:
    compact = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    token = hashlib.sha256(f"{case_id}:{compact}:{os.getpid()}".encode()).hexdigest()[:8]
    return f"{case_id}-{compact}-{token}"


def _environment_payload(repo_root: Path, cwd: Path) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "system": platform.system(),
        "machine": platform.machine(),
        "cwd": str(cwd),
        "repo_root": str(repo_root.resolve()),
    }
    for key in TZ_KEYS:
        payload[key] = os.environ.get(key)
    for key in EXTRA_ENV_KEYS:
        payload[key] = os.environ.get(key)
    return payload


def _tool_metadata() -> dict[str, str]:
    try:
        source = Path(__file__).read_text(encoding="utf-8")
    except OSError:  # pragma: no cover - defensive
        source = ""
    return {
        "name": COLLECTOR_NAME,
        "version": COLLECTOR_VERSION,
        "sha256": sha256_bytes(source.encode("utf-8")) if source else "",
    }


def _build_entry(
    *,
    case_id: str,
    run_id: str,
    branch: str,
    git_sha: str | None,
    git_available: bool,
    git_sha_source: str,
    tree_sha: str | None,
    command: str | None,
    command_argv: list[str] | None,
    cwd: Path,
    expected_exit: int,
    evidence_class: str,
    limitation: str | None,
    status: str,
    exit_code: int | None,
    timed_out: bool,
    artifacts: list[dict[str, Any]],
    stdout_summary: dict[str, Any] | None,
    stderr_summary: dict[str, Any] | None,
    raw_evidence_path: str | None,
    raw_evidence_sha256: str | None,
    utc: str,
    environment: dict[str, Any],
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "case_id": case_id,
        "run_id": run_id,
        "branch": branch,
        "git_sha": git_sha,
        "git_available": git_available,
        "git_sha_source": git_sha_source,
        "tree_sha": tree_sha,
        "command": command,
        "command_argv": command_argv,
        "cwd": str(cwd),
        "environment": environment,
        "utc": utc,
        "expected_exit": expected_exit,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "status": status,
        "evidence_class": evidence_class,
        "artifacts": artifacts,
        "stdout": stdout_summary,
        "stderr": stderr_summary,
        "raw_evidence_path": raw_evidence_path,
        "sha256": raw_evidence_sha256,
        "limitation": limitation,
        "collector": _tool_metadata(),
    }
    return entry


def _write_raw_evidence(
    *,
    out_dir: Path,
    run_id: str,
    payload: dict[str, Any],
    stdout_bytes: bytes,
    stderr_bytes: bytes,
) -> tuple[str, str]:
    """Write ``raw/<run_id>/`` and return (relative path, sha256)."""

    raw_run_dir = out_dir / RAW_DIR / run_id
    raw_run_dir.mkdir(parents=True, exist_ok=False)
    (raw_run_dir / "stdout.log").write_bytes(stdout_bytes[:MAX_LOG_BYTES])
    (raw_run_dir / "stderr.log").write_bytes(stderr_bytes[:MAX_LOG_BYTES])
    evidence_path = raw_run_dir / "evidence.json"
    evidence_bytes = (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    evidence_path.write_bytes(evidence_bytes)
    return f"{RAW_DIR}/{run_id}/evidence.json", sha256_bytes(evidence_bytes)


def run(args: argparse.Namespace) -> int:
    repo_root = (
        Path(args.repo_root).resolve() if args.repo_root else Path(__file__).resolve().parents[2]
    )
    out_dir = Path(args.out).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    _ensure_packet_readme(out_dir)

    case_id = args.case_id
    if not CASE_ID_RE.match(case_id):
        raise EvidenceError(f"invalid --case-id: {case_id!r}")
    expected_exit = args.expected_exit
    if args.timeout <= 0:
        raise EvidenceError("--timeout must be positive")
    if args.evidence_class not in EVIDENCE_CLASSES:
        raise EvidenceError(
            f"invalid --evidence-class: {args.evidence_class!r}; "
            "allowed: " + ", ".join(sorted(EVIDENCE_CLASSES))
        )

    if args.run_id:
        run_id = args.run_id
        if not RUN_ID_RE.match(run_id):
            raise EvidenceError(f"invalid --run-id: {run_id!r}")
    else:
        run_id = _new_run_id(case_id)

    index_jsonl = out_dir / AUDIT_INDEX_JSONL
    index_json = out_dir / AUDIT_INDEX_JSON
    existing_entries = _read_existing_entries(index_jsonl)
    existing_run_ids = {entry.get("run_id") for entry in existing_entries}
    if run_id in existing_run_ids:
        raise EvidenceError(
            f"run_id {run_id!r} already exists in {AUDIT_INDEX_JSONL}; "
            "append-only evidence requires a unique run_id"
        )

    git_probe = _git_value(repo_root, "rev-parse", "HEAD")
    git_available = git_probe is not None
    tree_sha = args.tree_sha or (
        _git_value(repo_root, "rev-parse", "HEAD^{tree}") if git_available else None
    )
    if args.tree_sha is not None and not GIT_SHA_RE.match(args.tree_sha):
        raise EvidenceError("--tree-sha must be a 40-hex git object id")
    if args.git_sha is not None:
        if not GIT_SHA_RE.match(args.git_sha):
            raise EvidenceError("--git-sha must be a 40-hex git commit id")
        git_sha: str | None = args.git_sha
        git_sha_source = "explicit"
    elif git_available:
        git_sha = git_probe
        git_sha_source = "git"
    else:
        git_sha = None
        git_sha_source = "unavailable"
    branch = args.branch or _git_value(repo_root, "rev-parse", "--abbrev-ref", "HEAD") or "UNKNOWN"
    environment = _environment_payload(repo_root, repo_root)
    utc = utc_now()
    limitations: list[str] = list(args.limitation or [])
    artifacts: list[dict[str, Any]] = []
    stdout_summary: dict[str, Any] | None = None
    stderr_summary: dict[str, Any] | None = None
    command = args.command
    command_argv: list[str] | None = None
    exit_code: int | None = None
    timed_out = False

    def write_not_run_entry(reason: str, *, cwd: Path, status: str = "NOT_RUN") -> int:
        payload = {
            "collector": _tool_metadata(),
            "case_id": case_id,
            "run_id": run_id,
            "uc": utc,
            "reason": reason,
            "command": command,
            "cwd": str(cwd),
            "status": status,
        }
        raw_path, raw_sha = _write_raw_evidence(
            out_dir=out_dir,
            run_id=run_id,
            payload=payload,
            stdout_bytes=b"",
            stderr_bytes=reason.encode("utf-8"),
        )
        entry = _build_entry(
            case_id=case_id,
            run_id=run_id,
            branch=branch,
            git_sha=git_sha,
            git_available=git_available,
            git_sha_source=git_sha_source,
            tree_sha=tree_sha,
            command=command,
            command_argv=None,
            cwd=cwd,
            expected_exit=expected_exit,
            evidence_class=args.evidence_class,
            limitation="; ".join(limitations + [reason]),
            status=status,
            exit_code=None,
            timed_out=False,
            artifacts=[],
            stdout_summary=None,
            stderr_summary=None,
            raw_evidence_path=raw_path,
            raw_evidence_sha256=raw_sha,
            utc=utc,
            environment=environment,
        )
        _append_jsonl(index_jsonl, entry)
        _materialize_index_json(index_json, existing_entries + [entry])
        print(
            f"[evidence] status={status} case_id={case_id} run_id={run_id} "
            f"reason={reason} out={out_dir}"
        )
        return EXIT_REJECTED

    # -- cwd -----------------------------------------------------------------
    if args.cwd:
        try:
            cwd = validate_cwd(Path(args.cwd), repo_root)
        except EvidenceError as exc:
            return write_not_run_entry(str(exc), cwd=Path(args.cwd))
        limitations.append("cwd provided by caller")
    else:
        try:
            cwd = validate_cwd(repo_root, repo_root)
        except EvidenceError as exc:  # pragma: no cover - defensive
            return write_not_run_entry(str(exc), cwd=repo_root)

    environment["cwd"] = str(cwd)

    # -- no command -> NOT_RUN (never PASS) ----------------------------------
    if not command:
        return write_not_run_entry(
            "no --command was supplied; a result without a command can never be PASS",
            cwd=cwd,
        )

    # -- command preflight ----------------------------------------------------
    try:
        command_argv = validate_command(command, allow_any_command=bool(args.allow_any_command))
    except EvidenceError as exc:
        return write_not_run_entry(f"command rejected by preflight: {exc}", cwd=cwd)

    # -- execute --------------------------------------------------------------
    try:
        completed = subprocess.run(
            command_argv,
            cwd=str(cwd),
            capture_output=True,
            timeout=args.timeout,
            check=False,
            shell=False,
            env=_child_env(),
        )
        stdout_bytes = completed.stdout or b""
        stderr_bytes = completed.stderr or b""
        exit_code = completed.returncode
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        stdout_bytes = exc.stdout or b""
        stderr_bytes = exc.stderr or b""
        limitations.append(f"command timed out after {args.timeout} seconds")
    except FileNotFoundError as exc:
        return write_not_run_entry(f"executable could not be started: {exc}", cwd=cwd)
    except OSError as exc:  # pragma: no cover - defensive
        return write_not_run_entry(f"command could not be executed: {exc}", cwd=cwd)

    stdout_summary = summarize_stream(stdout_bytes)
    stderr_summary = summarize_stream(stderr_bytes)
    if stdout_summary["truncated"]:
        limitations.append(f"stdout truncated to {MAX_LOG_BYTES} bytes")
    if stderr_summary["truncated"]:
        limitations.append(f"stderr truncated to {MAX_LOG_BYTES} bytes")

    for artifact_token in args.artifact or []:
        artifacts.append(resolve_artifact(artifact_token, cwd, repo_root))
    missing_artifacts = [item["requested"] for item in artifacts if not item["exists"]]
    if missing_artifacts:
        limitations.append("requested artifact(s) missing: " + ", ".join(missing_artifacts))

    status = "EXECUTED_PASS" if exit_code == 0 else "EXECUTED_FAIL"
    if timed_out or missing_artifacts:
        status = "EXECUTED_FAIL"
    if exit_code is not None and exit_code != expected_exit and not timed_out:
        limitations.append(f"exit code {exit_code} differs from --expected-exit {expected_exit}")
    limitation = "; ".join(limitations) if limitations else None

    payload = {
        "collector": _tool_metadata(),
        "case_id": case_id,
        "run_id": run_id,
        "branch": branch,
        "git_sha": git_sha,
        "git_available": git_available,
        "git_sha_source": git_sha_source,
        "tree_sha": tree_sha,
        "command": command,
        "command_argv": command_argv,
        "cwd": str(cwd),
        "utc": utc,
        "expected_exit": expected_exit,
        "status": status,
        "evidence_class": args.evidence_class,
        "limitation": limitation,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "environment": environment,
        "stdout": stdout_summary,
        "stderr": stderr_summary,
        "artifacts": artifacts,
    }
    raw_path, raw_sha = _write_raw_evidence(
        out_dir=out_dir,
        run_id=run_id,
        payload=payload,
        stdout_bytes=stdout_bytes,
        stderr_bytes=stderr_bytes,
    )
    entry = _build_entry(
        case_id=case_id,
        run_id=run_id,
        branch=branch,
        git_sha=git_sha,
        git_available=git_available,
        git_sha_source=git_sha_source,
        tree_sha=tree_sha,
        command=command,
        command_argv=command_argv,
        cwd=cwd,
        expected_exit=expected_exit,
        evidence_class=args.evidence_class,
        limitation=limitation,
        status=status,
        exit_code=exit_code,
        timed_out=timed_out,
        artifacts=artifacts,
        stdout_summary=stdout_summary,
        stderr_summary=stderr_summary,
        raw_evidence_path=raw_path,
        raw_evidence_sha256=raw_sha,
        utc=utc,
        environment=environment,
    )
    _append_jsonl(index_jsonl, entry)
    _materialize_index_json(index_json, existing_entries + [entry])
    print(
        f"[evidence] status={status} case_id={case_id} run_id={run_id} "
        f"exit_code={exit_code} sha256={raw_sha} out={out_dir}"
    )
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "M1-B offline evidence collector: execute one trusted command and append "
            "its hashed evidence to an append-only audit index."
        )
    )
    parser.add_argument("--out", required=True, help="output directory for the evidence packet")
    parser.add_argument("--case-id", required=True, help="evidence case id, e.g. B1-05")
    parser.add_argument(
        "--command",
        default=None,
        help="command string to execute with shell=False (omitting it records NOT_RUN)",
    )
    parser.add_argument(
        "--cwd",
        default=None,
        help="working directory (must resolve inside the repository root; default repo root)",
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help="repository root used for cwd validation and git provenance (default: script repo)",
    )
    parser.add_argument(
        "--expected-exit", type=int, default=0, help="expected exit code (default 0)"
    )
    parser.add_argument(
        "--artifact",
        action="append",
        default=None,
        help="artifact path to hash (repeatable; relative to --cwd)",
    )
    parser.add_argument(
        "--limitation",
        action="append",
        default=None,
        help="limitation note recorded with the evidence entry (repeatable)",
    )
    parser.add_argument("--run-id", default=None, help="explicit run id (default: generated)")
    parser.add_argument(
        "--git-sha",
        default=None,
        help=(
            "explicit 40-hex frozen commit id for archives without .git "
            "(recorded as git_sha_source=explicit; never invented from a branch name)"
        ),
    )
    parser.add_argument(
        "--tree-sha",
        default=None,
        help="explicit 40-hex tree id (default: git rev-parse HEAD^{tree} when git is available)",
    )
    parser.add_argument(
        "--branch",
        default=None,
        help="branch override (default: git rev-parse --abbrev-ref HEAD, else UNKNOWN)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"command timeout in seconds (default {DEFAULT_TIMEOUT_SECONDS:g})",
    )
    parser.add_argument(
        "--evidence-class",
        default="NOT_VERIFIED",
        help=(
            "label recorded for the Reviewer (default NOT_VERIFIED); the collector never "
            "infers an evidence class automatically"
        ),
    )
    parser.add_argument(
        "--allow-any-command",
        action="store_true",
        help="relax the executable allowlist for a trusted Reviewer command (hard denies stay)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return run(args)
    except EvidenceError as exc:
        print(f"[evidence] rejected: {exc}", file=sys.stderr)
        return EXIT_REJECTED
    except OSError as exc:  # pragma: no cover - defensive
        print(f"[evidence] I/O error: {exc}", file=sys.stderr)
        return EXIT_REJECTED


if __name__ == "__main__":
    raise SystemExit(main())
