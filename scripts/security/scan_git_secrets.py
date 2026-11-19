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
import base64
import binascii
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
# the secret assignment regexes below, and the *whole* value must be sentinel
# shaped (prefix plus only recognised sentinel words / separators / placeholder
# runs). ``SENTINEL<high-entropy-token>``, ``SENTINELsk-...`` and
# ``TEST_ONLY_<base64 secret>`` are therefore still reported. The exception must
# not be reused for raw sk-/AWS/GCP/GitHub/PEM/JWT/Bearer/DB matches.
ENV_SENTINEL_PREFIXES = (
    "sentinel", "test_only", "test-only", "testonly", "fake", "placeholder",
    "example", "not_a_real", "not-a-real", "notareal", "invalid", "dummy",
    "mock", "sample",
)
# Words that may follow a sentinel prefix and still describe an obvious test
# marker. Anything else -- including a random-looking token -- is reported.
ENV_SENTINEL_TAIL_WORDS = frozenset({
    "sentinel", "test", "tests", "testonly", "only", "never", "valid", "invalid",
    "secret", "secrets", "value", "values", "selftest", "self", "fake",
    "invented", "placeholder", "example", "dummy", "mock", "sample", "redacted",
    "changeme", "change", "me", "not", "real", "notreal", "none", "null",
    "todo", "xyz", "abc", "key", "keys", "token", "tokens", "password",
    "passwd", "pass", "credential", "credentials", "api", "auth", "marker",
    "probe", "canary", "synthetic", "local", "dev", "demo", "prod",
    "production", "staging", "stage", "sandbox", "deepseek", "openai",
    "anthropic", "opencode", "aws", "gcp", "azure", "hf", "huggingface",
    "gitlab", "npm", "slack", "github", "db", "database", "replace", "insert",
    "here", "your", "this", "fill", "string", "body", "for", "please",
})
_SENTINEL_PREFIXES_NORMALIZED = tuple(sorted(
    {prefix.lower().replace("-", "_") for prefix in ENV_SENTINEL_PREFIXES},
    key=len, reverse=True,
))
# Values are read only up to ASCII whitespace / quotes / comments; non-ASCII
# prose (for example a Chinese explanation after a code span) is cut off.
_NON_ASCII_RE = re.compile(r"[^\x21-\x7e]")
_SECRET_VALUE_CHARS_RE = re.compile(r"[A-Za-z0-9_./+=:@%!$&*~^?\-]+")

OPENAI_RE = re.compile(
    r"(?<![A-Za-z0-9_-])(sk-(?:proj-|svcacct-|admin-)?[A-Za-z0-9_-]{20,})(?![A-Za-z0-9_-])",
    re.IGNORECASE,
)
AWS_RE = re.compile(r"(?<![A-Z0-9])(AKIA[0-9A-Z]{16})(?![A-Z0-9])")
GCP_RE = re.compile(r"(?<![A-Za-z0-9_-])(AIza[0-9A-Za-z_-]{35})(?![A-Za-z0-9_-])")
SLACK_RE = re.compile(r"(?<![A-Za-z0-9])(xox[baprs]-[A-Za-z0-9-]{10,})")
SLACK_WEBHOOK_RE = re.compile(
    r"(https://hooks\.slack\.com/services/[A-Za-z0-9/_-]{20,})"
)
GITHUB_RE = re.compile(
    r"(?<![A-Za-z0-9_])((?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}))"
)
GITLAB_RE = re.compile(r"(?<![A-Za-z0-9_-])(glpat-[A-Za-z0-9_-]{20,})(?![A-Za-z0-9_-])")
NPM_RE = re.compile(r"(?<![A-Za-z0-9_])(npm_[A-Za-z0-9]{30,})(?![A-Za-z0-9_])")
HF_RE = re.compile(r"(?<![A-Za-z0-9_])(hf_[A-Za-z0-9]{30,})(?![A-Za-z0-9_])")
AZURE_ACCOUNT_KEY_RE = re.compile(r"(?i)\bAccountKey\s*=\s*([A-Za-z0-9+/=]{40,})")
JWT_RE = re.compile(
    r"(?<![A-Za-z0-9_-])(eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,})"
    r"(?![A-Za-z0-9_-]|\.[A-Za-z0-9_-]{8,})"
)
JWE_RE = re.compile(
    r"(?<![A-Za-z0-9_-])(eyJ[A-Za-z0-9_-]{8,}(?:\.[A-Za-z0-9_-]{8,}){4})"
    r"(?![A-Za-z0-9_-])"
)
# Built without a contiguous PEM marker literal so this scanner does not flag
# itself. Covers RSA/EC/DSA/OPENSSH/ENCRYPTED/PGP private-key headers.
PEM_RE = re.compile(
    r"-----BEGIN (?:(?:RSA|EC|DSA|OPENSSH|ENCRYPTED) )?(?:PGP )?"
    + "PRIVATE KEY" + r"(?: BLOCK)?-----"
)
BEARER_RE = re.compile(
    r"(?i)\b(?:Proxy-)?Authorization\s*:\s*Bearer\s+([A-Za-z0-9._~+/=-]{20,})"
)
BASIC_RE = re.compile(
    r"(?i)\b(?:Proxy-)?Authorization\s*:\s*Basic\s+([A-Za-z0-9+/=_-]{16,})"
)
# Environment-key assignments for known provider credentials. The explicit
# synthetic-sentinel exception is applied at the shared assignment sites below;
# raw sk-/AWS/GCP/GitHub/PEM/JWT matches are not affected.
KNOWN_ENV_NAMES = {
    "DEEPSEEK_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
    "AZURE_OPENAI_API_KEY", "OPENCODE_API_KEY", "HF_TOKEN",
    "HUGGINGFACE_TOKEN", "GITLAB_TOKEN", "NPM_TOKEN", "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN", "SLACK_BOT_TOKEN",
    "SLACK_USER_TOKEN", "SLACK_WEBHOOK_URL", "GITHUB_TOKEN", "GH_TOKEN",
    "AZURE_CLIENT_SECRET", "AZURE_STORAGE_KEY", "GCP_API_KEY",
    "GOOGLE_API_KEY", "GCP_SERVICE_ACCOUNT_KEY", "DATABASE_URL",
}
_ENV_NAME_PATTERN = "|".join(sorted(KNOWN_ENV_NAMES, key=len, reverse=True))
ENV_RE = re.compile(
    rf"(?i)\b({_ENV_NAME_PATTERN})\b\s*[:=]\s*[\"'`]?([^\s\"'#`]{{6,}})"
)
# Generic secret assignment names, including env vars, YAML/JSON keys and
# .env-style entries. Values are validated by ``_looks_like_secret_value`` so
# short type annotations and code expressions are not flagged. The same strict
# test-sentinel exception applies.
_SECRET_ENV_NAME = (
    r"(?:API_?KEY|ACCESS_KEY(?:_ID)?|SECRET_ACCESS_KEY|SECRET_KEY|PRIVATE_KEY|"
    r"AUTH_KEY|SIGNING_KEY|ENCRYPTION_KEY|STORAGE_KEY|SERVICE_ACCOUNT_KEY|"
    r"ACCOUNT_KEY|CLIENT_SECRET|TOKEN|SECRET|PASSWORD|PASSWD|PWD|PASS|"
    r"CREDENTIALS?)"
)
GENERIC_ENV_RE = re.compile(
    r"(?i)(?P<q>[\"']?)\b(?P<name>(?:[A-Za-z][A-Za-z0-9]*_)*" + _SECRET_ENV_NAME
    + r")\b(?P=q)\s*[:=]\s*[\"'`]?(?P<value>[^\s\"'#`]{16,})"
)
DB_URL_RE = re.compile(
    r"(?i)\b(?:postgres(?:ql)?|mysql|mariadb|mongodb(?:\+srv)?|redis|rediss|"
    r"amqp|amqps|mssql|sqlserver|oracle|cockroachdb|clickhouse)://"
    r"([^/\s:@]+):([^@\s]{3,})@"
)
CONN_CONTEXT_RE = re.compile(r"(?i)\b(?:Server|Data Source|Host|Initial Catalog|Database)\s*=")
CONN_PASSWORD_RE = re.compile(r"(?i)\b(?:Password|Pwd)\s*=\s*([^;\s\"']{6,})")
URL_QUERY_RE = re.compile(
    r"(?i)\bhttps?://[^\s\"'<>]*?[?&]"
    r"(?:api[_-]?key|access[_-]?token|auth[_-]?token|token|secret|password|passwd|"
    r"key|sig|signature)=([^&\s\"'#<>]{16,})"
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


def _clean_assignment_value(value: str) -> str:
    """Trim quoting/escapes/prose around an assignment value.

    This only normalises the value for classification and masking; it never
    turns a real-looking token into a sentinel.
    """
    value = value.strip()
    while value[:1] in "\"'`":
        value = value[1:]
    while value[-1:] in "\"'`":
        value = value[:-1]
    value = _NON_ASCII_RE.split(value, 1)[0]
    value = re.sub(r"(?:\\[nrt])+$", "", value)
    return value.rstrip(").,;:!?")


def _is_sentinel_tail_token(token: str) -> bool:
    if token in ENV_SENTINEL_TAIL_WORDS:
        return True
    if token.isdigit():
        # Short numeric suffixes (``SENTINEL_123``) are sentinel shaped; long
        # numeric runs are treated as potential key material.
        return len(token) <= 6
    # A run of one repeated character (``xxxx``, ``0000``) is not key material.
    return len(token) >= 2 and len(set(token)) == 1


def _is_env_test_sentinel(value: str) -> bool:
    """True only for an explicit synthetic sentinel env/config value.

    The whole value must be a recognised sentinel prefix followed by separator
    characters and sentinel words/placeholder runs. A prefix followed by a
    random-looking token (including ``sk-...`` or base64/hex material) is not a
    sentinel and is reported.
    """
    candidate = _clean_assignment_value(value)
    if not candidate:
        return False
    low = candidate.lower().replace("-", "_")
    for prefix in _SENTINEL_PREFIXES_NORMALIZED:
        if not low.startswith(prefix):
            continue
        rest = low[len(prefix):]
        tokens = [token for token in re.split(r"[_.:]+", rest) if token]
        if not tokens:
            return True
        return all(_is_sentinel_tail_token(token) for token in tokens)
    return False


def _looks_like_secret_value(value: str) -> bool:
    """Heuristic for generic assignment values (env, YAML, JSON, .env)."""
    if len(value) < 20 or not _SECRET_VALUE_CHARS_RE.fullmatch(value):
        return False
    has_alpha = re.search(r"[A-Za-z]", value) is not None
    has_digit = re.search(r"\d", value) is not None
    if has_alpha and has_digit:
        return True
    # Long single-class tokens (for example an all-letter base64 body) are only
    # reported when they are diverse enough to look generated.
    return len(value) >= 32 and len(set(value)) >= 8


def _looks_like_basic_credentials(token: str) -> bool:
    """True for a Basic auth value that decodes to ``user:password``."""
    if len(token) < 16:
        return False
    padded = token + "=" * (-len(token) % 4)
    try:
        decoded = base64.b64decode(padded, validate=True)
    except (binascii.Error, ValueError):
        return False
    return b":" in decoded and len(decoded) >= 8


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
        for match in SLACK_WEBHOOK_RE.finditer(line):
            token = match.group(1)
            if not _is_placeholder(token):
                findings.append(Finding("slack-webhook", source, path, line_no, _mask(token), commit))
        for match in GITHUB_RE.finditer(line):
            token = match.group(1)
            if not _is_placeholder(token):
                findings.append(Finding("github-token", source, path, line_no, _mask(token), commit))
        for match in GITLAB_RE.finditer(line):
            token = match.group(1)
            if not _is_placeholder(token):
                findings.append(Finding("gitlab-token", source, path, line_no, _mask(token), commit))
        for match in NPM_RE.finditer(line):
            token = match.group(1)
            if not _is_placeholder(token):
                findings.append(Finding("npm-token", source, path, line_no, _mask(token), commit))
        for match in HF_RE.finditer(line):
            token = match.group(1)
            if not _is_placeholder(token):
                findings.append(Finding("huggingface-token", source, path, line_no, _mask(token), commit))
        for match in AZURE_ACCOUNT_KEY_RE.finditer(line):
            token = match.group(1)
            if not _is_placeholder(token):
                findings.append(Finding("azure-account-key", source, path, line_no, _mask(token), commit))
        for match in JWE_RE.finditer(line):
            token = match.group(1)
            if not _is_placeholder(token):
                findings.append(Finding("jwe", source, path, line_no, _mask(token), commit))
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
        for match in BASIC_RE.finditer(line):
            token = match.group(1)
            if not _is_placeholder(token) and _looks_like_basic_credentials(token):
                findings.append(Finding("basic-auth", source, path, line_no, _mask(token), commit))
        for match in ENV_RE.finditer(line):
            value = _clean_assignment_value(match.group(2))
            if not value or _is_placeholder(value) or _is_env_test_sentinel(value):
                continue
            findings.append(Finding("env-key-assignment", source, path, line_no,
                                     f"{match.group(1).upper()}={_mask(value)}", commit))
        for match in GENERIC_ENV_RE.finditer(line):
            name = match.group("name").upper()
            if name in KNOWN_ENV_NAMES:
                continue
            value = _clean_assignment_value(match.group("value"))
            if not value or _is_placeholder(value) or _is_env_test_sentinel(value):
                continue
            if not _looks_like_secret_value(value):
                continue
            findings.append(Finding("env-key-assignment", source, path, line_no,
                                     f"{name}={_mask(value)}", commit))
        for match in DB_URL_RE.finditer(line):
            password = match.group(2)
            if not _is_placeholder(password):
                findings.append(Finding("db-url-password", source, path, line_no,
                                         f"password {_mask(password, 2)}", commit))
        if CONN_CONTEXT_RE.search(line):
            for match in CONN_PASSWORD_RE.finditer(line):
                value = _clean_assignment_value(match.group(1))
                if value and not _is_placeholder(value):
                    findings.append(Finding("connection-string-password", source, path, line_no,
                                             f"password {_mask(value, 2)}", commit))
        for match in URL_QUERY_RE.finditer(line):
            value = match.group(1)
            if _is_placeholder(value) or not _looks_like_secret_value(value):
                continue
            findings.append(Finding("url-query-secret", source, path, line_no,
                                     f"query {_mask(value)}", commit))
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
    # Synthetic high-entropy look-alikes: they must still be reported, proving
    # that the sentinel allowlist does not suppress arbitrary values. None of
    # these are credentials.
    high_entropy = hashlib.sha256(b"secret-scanner-selftest-not-a-credential").hexdigest()
    high_entropy_b64 = base64.b64encode(
        hashlib.sha256(b"secret-scanner-selftest-b64-not-a-credential").digest()
    ).decode()
    fake_openai = "sk-" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6"
    fake_aws = "AKIA" + "ABCDEFGHIJKLMNOP"
    fake_gcp = "AIza" + "A" * 35
    fake_slack = "xoxb-" + "1" * 20
    fake_slack_webhook = ("https://hooks.slack.com/services/" + "T" * 9 + "/"
                          + "B" * 9 + "/" + "Z" * 24)
    fake_github = "ghp_" + "a" * 36
    fake_gitlab = "glpat-" + "a" * 24
    fake_npm = "npm_" + "a" * 36
    fake_hf = "hf_" + "a" * 34
    fake_azure_account_key = "AccountKey=" + "A" * 44 + "=="
    fake_jwt = "eyJ" + "a" * 20 + "." + "b" * 20 + "." + "c" * 20
    fake_jwe = "eyJ" + "a" * 20 + ("." + "b" * 20) * 4
    basic_value = base64.b64encode(("scanner-user:" + high_entropy).encode()).decode()
    pem_headers = [
        "-----BEGIN " + label + "PRIVATE KEY" + "-----"
        for label in ("", "RSA ", "EC ", "DSA ", "OPENSSH ", "ENCRYPTED ")
    ]
    pem_headers.append("-----BEGIN " + "PGP " + "PRIVATE KEY" + " BLOCK" + "-----")
    # Real key shapes and synthetic look-alikes must still be detected.
    cases = [
        (fake_openai, "openai-key"),
        (fake_aws, "aws-access-key"),
        (fake_gcp, "gcp-api-key"),
        (fake_slack, "slack-token"),
        (fake_slack_webhook, "slack-webhook"),
        (fake_github, "github-token"),
        (fake_gitlab, "gitlab-token"),
        (fake_npm, "npm-token"),
        (fake_hf, "huggingface-token"),
        (fake_azure_account_key, "azure-account-key"),
        (fake_jwt, "jwt"),
        (fake_jwe, "jwe"),
        ("Authorization: Bearer " + "Z" * 40, "bearer-token"),
        ("Authorization: Basic " + basic_value, "basic-auth"),
        ("Proxy-Authorization: Basic " + basic_value, "basic-auth"),
        ("OPENAI_API_KEY=" + fake_openai, "env-key-assignment"),
        ("DEEPSEEK_API_KEY=" + high_entropy, "env-key-assignment"),
        ("AWS_SECRET_ACCESS_KEY=" + high_entropy, "env-key-assignment"),
        ("AZURE_CLIENT_SECRET=" + high_entropy, "env-key-assignment"),
        ("GCP_API_KEY=" + high_entropy, "env-key-assignment"),
        ("HF_TOKEN=" + high_entropy, "env-key-assignment"),
        ("GITLAB_TOKEN=" + high_entropy, "env-key-assignment"),
        ("NPM_TOKEN=" + high_entropy, "env-key-assignment"),
        ("SLACK_BOT_TOKEN=" + high_entropy, "env-key-assignment"),
        ("DATABASE_PASSWORD=" + high_entropy, "env-key-assignment"),
        ("MY_SERVICE_TOKEN=" + high_entropy, "env-key-assignment"),
        ("TOKEN=" + high_entropy, "env-key-assignment"),
        ("SIGNING_KEY=" + high_entropy, "env-key-assignment"),
        ("DEEPSEEK_API_KEY=" + "ZzSENTINEL" + "A" * 24, "env-key-assignment"),
        ("DEEPSEEK_API_KEY=" + "SENTINEL" + high_entropy, "env-key-assignment"),
        ("DEEPSEEK_API_KEY=" + "SENTINEL" + "sk-" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6",
         "env-key-assignment"),
        ("MY_SERVICE_TOKEN=" + "TEST_ONLY_" + high_entropy, "env-key-assignment"),
        ("MY_SERVICE_TOKEN=" + "TEST_ONLY_" + high_entropy_b64, "env-key-assignment"),
        ("password: \"" + high_entropy + "\"", "env-key-assignment"),
        ("\"api_key\": \"" + high_entropy_b64 + "\"", "env-key-assignment"),
        ("client_secret: " + high_entropy_b64, "env-key-assignment"),
        ("postgresql://user:" + "S3cret" + "Pass@db.example/x", "db-url-password"),
        ("mysql://app:" + high_entropy + "@db.internal:3306/app", "db-url-password"),
        ("mongodb+srv://app:" + high_entropy + "@cluster.example/app", "db-url-password"),
        ("Server=db.internal;Database=app;User Id=app;Password=" + high_entropy + ";",
         "connection-string-password"),
        ("https://203.0.113.10/v1/resource?token=" + high_entropy, "url-query-secret"),
        ("https://203.0.113.10/cb?api_key=" + high_entropy + "&x=1", "url-query-secret"),
    ]
    for header in pem_headers:
        cases.append((header, "private-key-header"))
    for index, (text, expected) in enumerate(cases):
        path = os.path.join(temp, f"case-{index}.txt")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")
        kinds = {finding.kind for finding in _scan_text(text, path, "selftest")}
        if expected not in kinds:
            failures.append(f"missing {expected} for case {index}: {text[:40]!r}")
    clean = "sk-" + "FAKE-" + "A" * 32
    if _scan_text("key=" + clean + "\n", "clean.txt", "selftest"):
        failures.append("sentinel sk-FAKE was flagged")
    if _scan_text("OPENAI_API_KEY=" + clean + "\n", "clean.txt", "selftest"):
        failures.append("sentinel sk-FAKE env assignment was flagged")
    # Every documented sentinel prefix, plus the literal symbol/value shapes used
    # by tracked tests/docs (including trailing punctuation and escapes), is
    # exempt only when the full tail is sentinel shaped.
    for prefix in ENV_SENTINEL_PREFIXES:
        line = "DEEPSEEK_API_KEY=" + prefix.upper() + "_SELFTEST_VALUE"
        if _scan_text(line + "\n", "sentinel.txt", "selftest"):
            failures.append(f"sentinel prefix was flagged: {prefix}")
    for value in ("SENTINEL", "SENTINEL)", "SENTINEL" + "`",
                  "SENTINEL" + "\\n", "sentinel_fake_value", "SENTINEL_" + "x" * 8,
                  "TEST_ONLY_NEVER_VALID_SECRET_SENTINEL"):
        line = f"DEEPSEEK_API_KEY={value}"
        if _scan_text(line + "\n", "sentinel.txt", "selftest"):
            failures.append(f"explicit env sentinel was flagged: {value}")
    if _scan_text("deepseek_api_key=SENTINEL\n", "sentinel.txt", "selftest"):
        failures.append("case-insensitive env name sentinel was flagged")
    if _scan_text("MY_SERVICE_TOKEN=TEST_ONLY_NEVER_VALID_SECRET_SENTINEL\n",
                  "sentinel.txt", "selftest"):
        failures.append("generic env sentinel was flagged")
    if _scan_text("password: \"SENTINEL\"\n", "sentinel.txt", "selftest"):
        failures.append("yaml env sentinel was flagged")
    if _scan_text("Authorization: Bearer abc...\n", "clean.txt", "selftest"):
        failures.append("bearer sentinel was flagged")
    if _scan_text("token = \"session-token\"\n", "clean.txt", "selftest"):
        failures.append("short non-secret assignment was flagged")
    # Strict sentinel shape: these obvious look-alikes must not be whitelisted.
    for value in ("SENTINEL" + high_entropy,
                  "SENTINEL" + "sk-" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6",
                  "TEST_ONLY_" + high_entropy,
                  "TEST_ONLY_" + high_entropy_b64,
                  "sentinel_abc123"):
        if _is_env_test_sentinel(value):
            failures.append(f"real-looking value was treated as sentinel: {value[:18]}")
    if _sensitive_path("docs/readme.md") or not _sensitive_path(".env") or _sensitive_path(".env.example") or not _sensitive_path("keys/id_rsa") or not _sensitive_path("server.pem"):
        failures.append("sensitive filename classifier failed")
    if failures:
        for failure in failures:
            print(f"SELFTEST FAIL: {failure}")
        return 1
    print("SELFTEST PASS: detectors, strict env-sentinel exclusions, filename classifier")
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
