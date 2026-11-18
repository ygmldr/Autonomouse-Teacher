#!/usr/bin/env python3
"""Repository secret scanner for the M0 public-release guard.

Standard library only, no network. Scans:
  1. current tracked files (git ls-files),
  2. every historical blob reachable from all refs,
  3. all commit messages.

Findings are reported as masked values only. Exit 1 on findings, 0 when clean.
This is a defense-in-depth heuristic, not a substitute for human review or a
hosted secret-scanning service.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from typing import Iterable

MAX_TEXT_BYTES = 4 * 1024 * 1024
PLACEHOLDER_MARKERS = (
    "fake", "invented", "livefake", "example", "placeholder", "dummy",
    "sample", "redacted", "changeme", "your_", "your-", "xxxx", "todo",
    "none", "null", "not-a-real", "notreal",
)

# Explicit test-only sentinels for env-secret assignments.
#
# This exception is intentionally narrow: it applies only to the value side of
# the env-assignment regexes below, only at the start of the value, and only for
# obvious synthetic markers. It must not be reused for raw sk-/AWS/GCP/GitHub/
# PEM/JWT matches. Only obvious test sentinels are allowed here; every other
# non-empty value -- including random or real-looking 32+ character values --
# is still reported.
ENV_SENTINEL_PREFIXES = (
    "sentinel", "test_only", "test-only", "testonly", "fake", "placeholder",
    "example", "not_a_real", "not-a-real", "notareal", "invalid", "dummy",
    "mock", "sample",
)

OPENAI_RE = re.compile(
    r"(?<![A-Za-z0-9_-])(sk-(?:proj-|svcacct-|admin-)?[A-Za-z0-9_-]{20,})(?![A-Za-z0-9_-])",
    re.IGNORECASE,
)
AWS_RE = re.compile(r"(?<![A-Z0-9])(AKIA[0-9A-Z]{16})(?![A-Z0-9])")
GCP_RE = re.compile(r"(?<![A-Za-z0-9_-])(AIza[0-9A-Za-z_-]{35})(?![A-Za-z0-9_-])")
SLACK_RE = re.compile(r"(?<![A-Za-z0-9])(xox[baprs]-[A-Za-z0-9-]{10,})")
GITHUB_RE = re.compile(
    r"(?<![A-Za-z0-9_])((?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}))"
)
JWT_RE = re.compile(
    r"(?<![A-Za-z0-9_-])(eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,})"
)
# Built without a contiguous PEM marker literal so this scanner does not flag itself.
PEM_RE = re.compile(
    r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?" + "PRIVATE KEY" + r"-----"
)
BEARER_RE = re.compile(
    r"(?i)\bAuthorization\s*:\s*Bearer\s+([A-Za-z0-9._~+/=-]{20,})"
)
# Environment-key assignments for known provider credentials. The explicit
# synthetic-sentinel exception is applied at the shared env-assignment sites
# below; raw sk-/AWS/GCP/GitHub/PEM/JWT matches are not affected.
KNOWN_ENV_NAMES = {"DEEPSEEK_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"}
ENV_RE = re.compile(
    r"(?i)\b(DEEPSEEK_API_KEY|OPENAI_API_KEY|ANTHROPIC_API_KEY)\b\s*[:=]\s*[\"']?([^\s\"'#]{6,})"
)
# Generic env-secret assignment names. Only 32+ character values are considered
# here, so a plausible random/real secret is covered while short benign values
# (for example a type annotation such as ``TOKEN: string``) are not flagged.
# The same explicit test-sentinel allowlist applies.
GENERIC_ENV_RE = re.compile(
    r"\b((?:[A-Z][A-Z0-9_]*_)?(?:API_KEY|ACCESS_KEY|SECRET_KEY|PRIVATE_KEY|TOKEN|"
    r"SECRET|PASSWORD|PASSWD|CREDENTIALS?))\b\s*[:=]\s*[\"']?([^\s\"'#]{32,})"
)
DB_URL_RE = re.compile(
    r"(?i)\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp)://([^/\s:@]+):([^@\s]{3,})@"
)

SENSITIVE_NAMES = {
    "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519", "id_rsa.pub",
    "git-credentials", ".git-credentials", ".npmrc", ".pypirc", ".netrc",
    "credentials", "secrets.json", "secrets.yaml", "secrets.yml",
}
SENSITIVE_SUFFIXES = (".pem", ".p12", ".pfx", ".key")
ENV_EXCEPTIONS = {".env.example", ".env.sample", ".env.template", ".env.dist"}


@dataclass(frozen=True)
class Finding:
    kind: str
    source: str
    path: str
    line: int
    masked: str
    commit: str = ""


def _is_placeholder(value: str) -> bool:
    low = value.lower()
    if not low or any(marker in low for marker in PLACEHOLDER_MARKERS):
        return True
    if low.startswith(("${", "<", "$(", "{{")) or low.endswith((">", "}")):
        return True
    if "..." in low or "***" in low or low.startswith("abc"):
        return True
    return False


def _is_env_test_sentinel(value: str) -> bool:
    """True only for an explicit synthetic sentinel env-assignment value."""
    candidate = value.strip().strip("\"'`").lower()
    return candidate.startswith(ENV_SENTINEL_PREFIXES)


def _mask(value: str, prefix: int = 6) -> str:
    if not value:
        return "***"
    visible = value[:prefix]
    return f"{visible}…(len {len(value)})"


def _sensitive_path(path: str) -> bool:
    name = path.rsplit("/", 1)[-1].lower()
    if name.startswith(".env"):
        return name not in ENV_EXCEPTIONS
    if name in SENSITIVE_NAMES:
        return True
    return name.endswith(SENSITIVE_SUFFIXES)


def _scan_text(text: str, path: str, source: str, commit: str = "") -> list[Finding]:
    findings: list[Finding] = []
    for line_no, line in enumerate(text.splitlines(), 1):
        for match in OPENAI_RE.finditer(line):
            token = match.group(1)
            if not _is_placeholder(token):
                findings.append(Finding("openai-key", source, path, line_no, _mask(token), commit))
        for match in AWS_RE.finditer(line):
            token = match.group(1)
            if not _is_placeholder(token):
                findings.append(Finding("aws-access-key", source, path, line_no, _mask(token), commit))
        for match in GCP_RE.finditer(line):
            token = match.group(1)
            if not _is_placeholder(token):
                findings.append(Finding("gcp-api-key", source, path, line_no, _mask(token), commit))
        for match in SLACK_RE.finditer(line):
            token = match.group(1)
            if not _is_placeholder(token):
                findings.append(Finding("slack-token", source, path, line_no, _mask(token), commit))
        for match in GITHUB_RE.finditer(line):
            token = match.group(1)
            if not _is_placeholder(token):
                findings.append(Finding("github-token", source, path, line_no, _mask(token), commit))
        for match in JWT_RE.finditer(line):
            token = match.group(1)
            if not _is_placeholder(token):
                findings.append(Finding("jwt", source, path, line_no, _mask(token), commit))
        if PEM_RE.search(line):
            findings.append(Finding("private-key-header", source, path, line_no, "PRIVATE KEY header", commit))
        for match in BEARER_RE.finditer(line):
            token = match.group(1)
            if not _is_placeholder(token) and not token.lower().startswith("abc"):
                findings.append(Finding("bearer-token", source, path, line_no, _mask(token), commit))
        for match in ENV_RE.finditer(line):
            value = match.group(2).strip().strip("\"'")
            if not _is_placeholder(value) and not _is_env_test_sentinel(value):
                findings.append(Finding("env-key-assignment", source, path, line_no,
                                         f"{match.group(1).upper()}={_mask(value)}", commit))
        for match in GENERIC_ENV_RE.finditer(line):
            name = match.group(1).upper()
            if name in KNOWN_ENV_NAMES:
                continue
            value = match.group(2).strip().strip("\"'")
            if not _is_placeholder(value) and not _is_env_test_sentinel(value):
                findings.append(Finding("env-key-assignment", source, path, line_no,
                                         f"{name}={_mask(value)}", commit))
        for match in DB_URL_RE.finditer(line):
            password = match.group(2)
            if not _is_placeholder(password):
                findings.append(Finding("db-url-password", source, path, line_no,
                                         f"password {_mask(password, 2)}", commit))
    return findings


def _git(root: Path, *args: str, stdin: bytes | None = None) -> subprocess.CompletedProcess:
    kwargs = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE, "check": False}
    if stdin is None:
        kwargs["stdin"] = subprocess.DEVNULL
    else:
        kwargs["input"] = stdin
    return subprocess.run(
        ["git", "-C", str(root), "-c", "core.quotepath=false", *args], **kwargs,
    )


def _git_out(root: Path, *args: str) -> str:
    proc = _git(root, *args)
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.decode('utf-8', 'replace')[:300]}")
    return proc.stdout.decode("utf-8", "replace")


def _tracked_files(root: Path) -> list[str]:
    raw = _git(root, "ls-files", "-z").stdout
    return [item.decode("utf-8", "replace") for item in raw.split(b"\0") if item]


def _history_blobs(root: Path) -> list[tuple[str, str]]:
    output = _git_out(root, "rev-list", "--objects", "--all")
    objects: list[tuple[str, str]] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        sha, _, path = line.partition(" ")
        objects.append((sha, path))
    if not objects:
        return []
    check_input = ("\n".join(sha for sha, _ in objects) + "\n").encode()
    check = _git(root, "cat-file", "--batch-check=%(objecttype) %(objectname) %(objectsize)",
                 stdin=check_input)
    if check.returncode != 0:
        raise RuntimeError("git cat-file --batch-check failed")
    lines = check.stdout.decode("utf-8", "replace").splitlines()
    blobs: list[tuple[str, str]] = []
    for line, (sha, path) in zip(lines, objects):
        parts = line.split()
        if len(parts) >= 3 and parts[0] == "blob":
            blobs.append((sha, path))
    return blobs


def _batch_contents(root: Path, blobs: list[tuple[str, str]]) -> Iterable[tuple[str, bytes]]:
    if not blobs:
        return []
    proc = _git(root, "cat-file", "--batch", stdin=("\n".join(sha for sha, _ in blobs) + "\n").encode())
    if proc.returncode != 0:
        raise RuntimeError("git cat-file --batch failed")
    data = proc.stdout
    pos = 0
    results: list[tuple[str, bytes]] = []
    for sha, _path in blobs:
        header_end = data.find(b"\n", pos)
        if header_end < 0:
            break
        header = data[pos:header_end].decode("utf-8", "replace").split()
        pos = header_end + 1
        if len(header) < 3 or header[1] != "blob":
            continue
        try:
            size = int(header[2])
        except ValueError:
            break
        content = data[pos:pos + size]
        pos += size + 1
        results.append((sha, content))
    return results


def scan(root: Path, *, include_history: bool = True) -> tuple[list[Finding], dict]:
    findings: list[Finding] = []
    stats = {"files": 0, "blobs": 0, "commits": 0}

    files = _tracked_files(root)
    stats["files"] = len(files)
    for rel in files:
        if _sensitive_path(rel):
            findings.append(Finding("sensitive-filename", "worktree", rel, 0, "tracked sensitive filename"))
        full = root / rel
        try:
            if not full.is_file() or full.stat().st_size > MAX_TEXT_BYTES:
                continue
            data = full.read_bytes()
        except OSError:
            continue
        if b"\0" in data[:8192]:
            continue
        findings.extend(_scan_text(data.decode("utf-8", "replace"), rel, "worktree"))

    if include_history:
        blobs = _history_blobs(root)
        stats["blobs"] = len(blobs)
        histories: dict[str, bytes] = {}
        for sha, content in _batch_contents(root, blobs):
            histories[sha] = content
        for sha, path in blobs:
            if _sensitive_path(path):
                findings.append(Finding("sensitive-filename-history", "history", path or sha[:12],
                                        0, "historical sensitive filename", commit=sha[:12]))
            content = histories.get(sha)
            if content is None or len(content) > MAX_TEXT_BYTES or b"\0" in content[:8192]:
                continue
            findings.extend(_scan_text(content.decode("utf-8", "replace"),
                                       path or sha[:12], "history", commit=sha[:12]))
        log = _git_out(root, "log", "--all", "--format=%H%x00%B%x00")
        parts = log.split("\x00")
        for index in range(0, len(parts) - 1, 2):
            commit = parts[index].strip()
            message = parts[index + 1]
            if not commit:
                continue
            stats["commits"] += 1
            findings.extend(_scan_text(message, "commit-message", "commit", commit[:12]))
    # History repeats the same path/line across many commits; keep one record per
    # (kind, location, masked) triple while preserving commit evidence.
    deduped: dict[tuple[str, str, int, str], Finding] = {}
    for finding in findings:
        key = (finding.kind, finding.path, finding.line, finding.masked)
        if key not in deduped:
            deduped[key] = finding
    return list(deduped.values()), stats


def self_test() -> int:
    temp = tempfile.mkdtemp(prefix="secret-scan-selftest-")
    failures: list[str] = []
    # Synthetic high-entropy look-alike: it must still be reported, proving that
    # the sentinel allowlist does not suppress arbitrary values. Not a credential.
    high_entropy = hashlib.sha256(b"secret-scanner-selftest-not-a-credential").hexdigest()
    fake_openai = "sk-" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6"
    fake_aws = "AKIA" + "ABCDEFGHIJKLMNOP"
    fake_gcp = "AIza" + "A" * 35
    fake_slack = "xoxb-" + "1" * 20
    fake_github = "ghp_" + "a" * 36
    fake_pem = "-----BEGIN " + "RSA PRIVATE KEY" + "-----"
    fake_jwt = "eyJ" + "a" * 20 + "." + "b" * 20 + "." + "c" * 20
    # Real key shapes and synthetic look-alikes must still be detected.
    cases = [
        (fake_openai, "openai-key"),
        (fake_aws, "aws-access-key"),
        (fake_gcp, "gcp-api-key"),
        (fake_slack, "slack-token"),
        (fake_github, "github-token"),
        (fake_pem, "private-key-header"),
        (fake_jwt, "jwt"),
        ("Authorization: Bearer " + "Z" * 40, "bearer-token"),
        ("OPENAI_API_KEY=" + fake_openai, "env-key-assignment"),
        ("DEEPSEEK_API_KEY=" + high_entropy, "env-key-assignment"),
        ("MY_SERVICE_TOKEN=" + high_entropy, "env-key-assignment"),
        ("TOKEN=" + high_entropy, "env-key-assignment"),
        ("DEEPSEEK_API_KEY=" + "ZzSENTINEL" + "A" * 24, "env-key-assignment"),
        ("postgresql://user:" + "S3cret" + "Pass@db.example/x", "db-url-password"),
    ]
    for index, (text, expected) in enumerate(cases):
        path = os.path.join(temp, f"case-{index}.txt")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")
        kinds = {finding.kind for finding in _scan_text(text, path, "selftest")}
        if expected not in kinds:
            failures.append(f"missing {expected} for case {index}")
    clean = "sk-" + "FAKE-" + "A" * 32
    if _scan_text("key=" + clean + "\n", "clean.txt", "selftest"):
        failures.append("sentinel sk-FAKE was flagged")
    if _scan_text("OPENAI_API_KEY=" + clean + "\n", "clean.txt", "selftest"):
        failures.append("sentinel sk-FAKE env assignment was flagged")
    # Every documented sentinel prefix, plus the literal symbol/value shapes used
    # by tracked tests/docs (including trailing punctuation), is exempt.
    for prefix in ENV_SENTINEL_PREFIXES:
        line = "DEEPSEEK_API_KEY=" + prefix.upper() + "_SELFTEST_VALUE"
        if _scan_text(line + "\n", "sentinel.txt", "selftest"):
            failures.append(f"sentinel prefix was flagged: {prefix}")
    for value in ("SENTINEL", "SENTINEL)", "SENTINEL" + "`",
                  "TEST_ONLY_NEVER_VALID_SECRET_SENTINEL"):
        line = f"DEEPSEEK_API_KEY={value}"
        if _scan_text(line + "\n", "sentinel.txt", "selftest"):
            failures.append(f"explicit env sentinel was flagged: {value}")
    if _scan_text("deepseek_api_key=SENTINEL\n", "sentinel.txt", "selftest"):
        failures.append("case-insensitive env name sentinel was flagged")
    if _scan_text("MY_SERVICE_TOKEN=TEST_ONLY_NEVER_VALID_SECRET_SENTINEL\n",
                  "sentinel.txt", "selftest"):
        failures.append("generic env sentinel was flagged")
    if _scan_text("Authorization: Bearer abc...\n", "clean.txt", "selftest"):
        failures.append("bearer sentinel was flagged")
    if _sensitive_path("docs/readme.md") or not _sensitive_path(".env") or _sensitive_path(".env.example") or not _sensitive_path("keys/id_rsa") or not _sensitive_path("server.pem"):
        failures.append("sensitive filename classifier failed")
    if failures:
        for failure in failures:
            print(f"SELFTEST FAIL: {failure}")
        return 1
    print("SELFTEST PASS: detectors, env-sentinel exclusions, filename classifier")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scan git worktree, history and commit messages for probable secrets.")
    parser.add_argument("--root", default=".", help="git repository root (default: current directory)")
    parser.add_argument("--no-history", action="store_true", help="scan only currently tracked worktree files")
    parser.add_argument("--json", action="store_true", help="machine-readable findings (still masked)")
    parser.add_argument("--self-test", action="store_true", help="run detector self-tests in a temporary directory")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    root = Path(args.root).resolve()
    try:
        findings, stats = scan(root, include_history=not args.no_history)
    except Exception as error:  # noqa: BLE001 - fail closed with a safe message
        print(f"SECRET SCAN ERROR: {type(error).__name__}: {error}", file=sys.stderr)
        return 2
    payload = {"ok": not findings, "scanned": stats,
               "findings": [asdict(finding) for finding in findings]}
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        for finding in findings:
            location = f"{finding.path}:{finding.line}" if finding.line else finding.path
            print(f"FINDING [{finding.kind}] {finding.source} {location} masked={finding.masked}"
                  + (f" commit={finding.commit}" if finding.commit else ""))
        print(f"SECRET SCAN: scanned_files={stats['files']} scanned_blobs={stats['blobs']} "
              f"scanned_commits={stats['commits']} findings={len(findings)}")
        if findings:
            print("SECRET SCAN FAILED: probable secret material detected (values masked)", file=sys.stderr)
        else:
            print("SECRET SCAN OK: no probable secret material detected")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
