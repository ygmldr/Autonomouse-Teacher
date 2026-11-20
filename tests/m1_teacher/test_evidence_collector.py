"""Unit tests for the M1-B offline evidence collector (``scripts/m1b/collect_evidence.py``).

The collector is executed as a real subprocess (it is a CLI tool, not an
importable package).  The measured commands are synthetic, offline ``python``/
``printf`` invocations; every test writes into ``tmp_path`` and never touches
the repository or any network resource.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
COLLECTOR = REPO_ROOT / "scripts" / "m1b" / "collect_evidence.py"
PYTHON = sys.executable


def run_collector(
    *args: str,
    out: Path,
    case_id: str,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    command = [
        PYTHON,
        str(COLLECTOR),
        "--out",
        str(out),
        "--case-id",
        case_id,
        *args,
    ]
    return subprocess.run(
        command,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
        env=env if env is not None else {**os.environ},
    )


def shell_command(*argv: object) -> str:
    """Quote an argv list exactly as the collector's shlex parser expects."""

    return shlex.join([str(item) for item in argv])


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_entries(out: Path) -> list[dict]:
    index = out / "audit-index.jsonl"
    return [json.loads(line) for line in index.read_text(encoding="utf-8").splitlines()]


# ---------------------------------------------------------------------------
# Successful collection / index schema
# ---------------------------------------------------------------------------
def test_collects_executed_pass_with_full_index_entry(tmp_path: Path) -> None:
    out = tmp_path / "packet"
    command = shell_command(PYTHON, "-c", "print('evidence-ok')")
    completed = run_collector(
        "--command",
        command,
        "--limitation",
        "synthetic unit case",
        out=out,
        case_id="T-PASS-01",
    )

    assert completed.returncode == 0, completed.stderr
    entries = read_entries(out)
    assert len(entries) == 1
    entry = entries[0]

    required = (
        "case_id",
        "branch",
        "git_sha",
        "git_available",
        "git_sha_source",
        "tree_sha",
        "run_id",
        "command",
        "environment",
        "utc",
        "exit_code",
        "status",
        "raw_evidence_path",
        "sha256",
        "limitation",
    )
    for field in required:
        assert field in entry, field
    assert entry["case_id"] == "T-PASS-01"
    assert entry["status"] == "EXECUTED_PASS"
    assert entry["exit_code"] == 0
    assert entry["timed_out"] is False
    assert entry["expected_exit"] == 0
    assert entry["evidence_class"] == "NOT_VERIFIED"
    assert entry["limitation"] == "synthetic unit case"
    assert entry["collector"]["name"] == "m1b.collect-evidence"
    # P1-1: a git checkout records a real 40-hex SHA; a no-.git archive is
    # explicitly allowed to record git_sha=None (never invent a SHA).
    if entry["git_available"]:
        assert re.fullmatch(r"[0-9a-f]{40}", entry["git_sha"])
        assert entry["git_sha_source"] in {"git", "explicit"}
    else:
        assert entry["git_sha"] is None
        assert entry["git_sha_source"] == "unavailable"
    assert entry["branch"]
    assert re.fullmatch(r"[0-9a-f]{64}", entry["sha256"])

    raw_path = out / entry["raw_evidence_path"]
    assert raw_path.is_file()
    assert sha256_file(raw_path) == entry["sha256"]
    assert "T-PASS-01" in raw_path.read_text(encoding="utf-8")
    assert "evidence-ok" in entry["stdout"]["tail"]
    assert entry["stdout"]["bytes"] > 0
    assert entry["stderr"]["bytes"] == 0
    assert entry["stdout"]["truncated"] is False

    environment = entry["environment"]
    assert {"TZ", "PYTHONHASHSEED"} <= set(environment)
    assert environment["python_version"].startswith("3.")
    assert environment["cwd"] == str(REPO_ROOT)

    mirror = json.loads((out / "audit-index.json").read_text(encoding="utf-8"))
    assert mirror["schema_version"] == "m1b.audit-index.v0"
    assert mirror["entry_count"] == 1
    assert mirror["entries"] == entries


def test_nonzero_exit_is_executed_fail_not_product_pass(tmp_path: Path) -> None:
    out = tmp_path / "packet"
    command = shell_command(PYTHON, "-c", "import sys; sys.exit(3)")
    completed = run_collector("--command", command, out=out, case_id="T-FAIL-01")

    assert completed.returncode == 0, completed.stderr
    entry = read_entries(out)[0]
    assert entry["status"] == "EXECUTED_FAIL"
    assert entry["exit_code"] == 3
    assert "differs from --expected-exit" in (entry["limitation"] or "")
    assert entry["status"] != "EXECUTED_PASS"


def test_no_command_records_not_run_and_never_pass(tmp_path: Path) -> None:
    out = tmp_path / "packet"
    completed = run_collector(out=out, case_id="T-NOCMD-01")

    assert completed.returncode == 2
    entry = read_entries(out)[0]
    assert entry["status"] == "NOT_RUN"
    assert entry["exit_code"] is None
    assert entry["command"] is None
    assert "no --command" in (entry["limitation"] or "")


# ---------------------------------------------------------------------------
# Preflight rejection / safety
# ---------------------------------------------------------------------------
def test_rejects_dangerous_commands_even_with_allow_any(tmp_path: Path) -> None:
    out = tmp_path / "packet"
    dangerous = (
        "rm -rf /tmp/m1b-would-not-run",
        "curl http://example.invalid/x",
        "ssh example.invalid",
        "git push origin main",
    )
    for index, command in enumerate(dangerous):
        completed = run_collector(
            "--command",
            command,
            "--allow-any-command",
            out=out,
            case_id=f"T-DANGER-{index}",
        )
        assert completed.returncode == 2, (command, completed.stderr)
        entry = read_entries(out)[-1]
        assert entry["status"] == "NOT_RUN"
        assert entry["exit_code"] is None
        assert "rejected by preflight" in (entry["limitation"] or "")


def test_unlisted_executable_requires_allow_any_command(tmp_path: Path) -> None:
    out = tmp_path / "packet"
    command = "printf collector-ok"
    rejected = run_collector("--command", command, out=out, case_id="T-ALLOWLIST-01")
    assert rejected.returncode == 2
    assert read_entries(out)[-1]["status"] == "NOT_RUN"

    allowed = run_collector(
        "--command",
        command,
        "--allow-any-command",
        out=out,
        case_id="T-ALLOWLIST-02",
    )
    assert allowed.returncode == 0, allowed.stderr
    entry = read_entries(out)[-1]
    assert entry["status"] == "EXECUTED_PASS"
    assert "collector-ok" in entry["stdout"]["tail"]


def test_cwd_must_resolve_inside_repository(tmp_path: Path) -> None:
    out = tmp_path / "packet"
    rejected = run_collector(
        "--command",
        shell_command(PYTHON, "-c", "print('cwd')"),
        "--cwd",
        str(tmp_path),
        out=out,
        case_id="T-CWD-01",
    )
    assert rejected.returncode == 2
    entry = read_entries(out)[-1]
    assert entry["status"] == "NOT_RUN"
    assert "inside the repository root" in (entry["limitation"] or "")

    accepted = run_collector(
        "--command",
        shell_command(PYTHON, "-c", "print('cwd')"),
        "--cwd",
        str(REPO_ROOT / "tests"),
        out=out,
        case_id="T-CWD-02",
    )
    assert accepted.returncode == 0, accepted.stderr
    assert read_entries(out)[-1]["cwd"] == str(REPO_ROOT / "tests")


# ---------------------------------------------------------------------------
# Artifacts, timeout, append-only, credential hygiene
# ---------------------------------------------------------------------------
def test_artifacts_are_hashed_and_missing_artifact_fails(tmp_path: Path) -> None:
    out = tmp_path / "packet"
    artifact = tmp_path / "artifact.txt"
    artifact.write_text("artifact-bytes", encoding="utf-8")
    command = shell_command(PYTHON, "-c", "print('artifact')")

    completed = run_collector(
        "--command", command, "--artifact", str(artifact), out=out, case_id="T-ART-01"
    )
    assert completed.returncode == 0, completed.stderr
    entry = read_entries(out)[-1]
    assert entry["status"] == "EXECUTED_PASS"
    assert len(entry["artifacts"]) == 1
    record = entry["artifacts"][0]
    assert record["exists"] is True
    assert record["sha256"] == sha256_file(artifact)
    assert record["bytes"] == len(b"artifact-bytes")

    missing = run_collector(
        "--command",
        command,
        "--artifact",
        str(tmp_path / "does-not-exist.bin"),
        out=out,
        case_id="T-ART-02",
    )
    assert missing.returncode == 0, missing.stderr
    missing_entry = read_entries(out)[-1]
    assert missing_entry["status"] == "EXECUTED_FAIL"
    assert "missing" in (missing_entry["limitation"] or "")


def test_timeout_is_executed_fail_with_timed_out_flag(tmp_path: Path) -> None:
    out = tmp_path / "packet"
    command = shell_command(PYTHON, "-c", "import time; time.sleep(5)")
    completed = run_collector(
        "--command", command, "--timeout", "0.2", out=out, case_id="T-TIMEOUT-01"
    )
    assert completed.returncode == 0, completed.stderr
    entry = read_entries(out)[-1]
    assert entry["status"] == "EXECUTED_FAIL"
    assert entry["timed_out"] is True
    assert entry["exit_code"] is None
    assert "timed out" in (entry["limitation"] or "")


def test_index_is_append_only_across_runs(tmp_path: Path) -> None:
    out = tmp_path / "packet"
    first = run_collector(
        "--command", shell_command(PYTHON, "-c", "print('one')"), out=out, case_id="T-APP-01"
    )
    assert first.returncode == 0, first.stderr
    index_path = out / "audit-index.jsonl"
    before = index_path.read_bytes()
    first_line = before.splitlines()[0]

    second = run_collector(
        "--command", shell_command(PYTHON, "-c", "print('two')"), out=out, case_id="T-APP-02"
    )
    assert second.returncode == 0, second.stderr
    after = index_path.read_bytes()
    assert after.startswith(before)
    assert after.splitlines()[0] == first_line
    entries = read_entries(out)
    assert [entry["case_id"] for entry in entries] == ["T-APP-01", "T-APP-02"]
    assert len({entry["run_id"] for entry in entries}) == 2
    mirror = json.loads((out / "audit-index.json").read_text(encoding="utf-8"))
    assert mirror["entry_count"] == 2


def test_malformed_index_is_rejected_without_rewrite(tmp_path: Path) -> None:
    out = tmp_path / "packet"
    out.mkdir()
    index_path = out / "audit-index.jsonl"
    index_path.write_text("this is not json\n", encoding="utf-8")
    before = index_path.read_bytes()

    completed = run_collector(
        "--command", shell_command(PYTHON, "-c", "print('x')"), out=out, case_id="T-BAD-01"
    )
    assert completed.returncode == 2
    assert index_path.read_bytes() == before
    assert not (out / "audit-index.json").exists()


def test_duplicate_run_id_is_rejected(tmp_path: Path) -> None:
    out = tmp_path / "packet"
    first = run_collector(
        "--command",
        shell_command(PYTHON, "-c", "print('one')"),
        "--run-id",
        "fixed-run-id",
        out=out,
        case_id="T-DUP-01",
    )
    assert first.returncode == 0, first.stderr
    second = run_collector(
        "--command",
        shell_command(PYTHON, "-c", "print('two')"),
        "--run-id",
        "fixed-run-id",
        out=out,
        case_id="T-DUP-01",
    )
    assert second.returncode == 2
    assert "already exists" in second.stderr
    assert len(read_entries(out)) == 1


def test_credential_environment_never_lands_in_packet(tmp_path: Path) -> None:
    out = tmp_path / "packet"
    secret = "super-secret-value-for-test-only"
    env = {**os.environ, "M1B_TEST_API_KEY": secret}
    completed = run_collector(
        "--command",
        shell_command(PYTHON, "-c", "print('no-secret')"),
        out=out,
        case_id="T-SECRET-01",
        env=env,
    )
    assert completed.returncode == 0, completed.stderr
    for path in out.rglob("*"):
        if path.is_file():
            assert secret.encode() not in path.read_bytes(), path
    entry = read_entries(out)[-1]
    assert "M1B_TEST_API_KEY" not in entry["environment"]
    assert "super-secret-value" not in json.dumps(entry)


# ---------------------------------------------------------------------------
# Offline / stdlib-only guarantees
# ---------------------------------------------------------------------------
def test_collector_is_stdlib_only_and_offline(tmp_path: Path) -> None:
    source = COLLECTOR.read_text(encoding="utf-8")
    tree = ast.parse(source)

    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".")[0])

    forbidden = {
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
    assert not (imported_roots & forbidden), imported_roots & forbidden
    assert "autoteacher_m0" not in source
    assert "shell=True" not in source
    for token in ("eval(", "exec("):
        assert token not in source, token

    # The collector still works with socket blocked at interpreter start-up
    # (sitecustomize) - proving it does not rely on network availability.
    no_net = tmp_path / "no-net"
    no_net.mkdir()
    (no_net / "sitecustomize.py").write_text(
        "import socket\n"
        "def _deny(*args, **kwargs):\n"
        "    raise OSError('M1B_NO_NETWORK')\n"
        "socket.socket = _deny\n"
        "socket.create_connection = _deny\n"
        "socket.getaddrinfo = _deny\n",
        encoding="utf-8",
    )
    out = tmp_path / "packet"
    env = {**os.environ, "PYTHONPATH": str(no_net)}
    completed = run_collector(
        "--command",
        shell_command(PYTHON, "-c", "print('offline-ok')"),
        out=out,
        case_id="T-NONET-01",
        env=env,
    )
    assert completed.returncode == 0, completed.stderr
    entry = read_entries(out)[-1]
    assert entry["status"] == "EXECUTED_PASS"
    assert "offline-ok" in entry["stdout"]["tail"]


def test_evidence_class_label_is_recorded_and_validated(tmp_path: Path) -> None:
    out = tmp_path / "packet"
    command = shell_command(PYTHON, "-c", "print('class')")
    completed = run_collector(
        "--command",
        command,
        "--evidence-class",
        "DETERMINISTIC",
        out=out,
        case_id="T-CLASS-01",
    )
    assert completed.returncode == 0, completed.stderr
    assert read_entries(out)[-1]["evidence_class"] == "DETERMINISTIC"

    rejected = run_collector(
        "--command",
        command,
        "--evidence-class",
        "REAL_LEARNING_GAIN",
        out=out,
        case_id="T-CLASS-02",
    )
    assert rejected.returncode == 2
    assert "invalid --evidence-class" in rejected.stderr
    assert len(read_entries(out)) == 1


def _run_collector_in(
    script: Path,
    cwd: Path,
    *args: str,
    out: Path,
    case_id: str,
) -> subprocess.CompletedProcess[str]:
    command = [
        PYTHON,
        str(script),
        "--out",
        str(out),
        "--case-id",
        case_id,
        *args,
    ]
    return subprocess.run(
        command,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=120,
        env={**os.environ},
    )


def test_collector_is_portable_in_a_no_git_archive_copy(tmp_path: Path) -> None:
    """P1-1 regression: no-.git archive records git_sha=None instead of inventing one."""

    archive = tmp_path / "archive"
    (archive / "scripts" / "m1b").mkdir(parents=True)
    shutil.copy2(COLLECTOR, archive / "scripts" / "m1b" / "collect_evidence.py")
    assert not (archive / ".git").exists()
    command = shell_command(PYTHON, "-c", "print('no-git-ok')")

    out = tmp_path / "packet"
    completed = _run_collector_in(
        archive / "scripts" / "m1b" / "collect_evidence.py",
        archive,
        "--command",
        command,
        out=out,
        case_id="T-NOGIT-01",
    )
    assert completed.returncode == 0, completed.stderr
    entry = read_entries(out)[0]
    assert entry["status"] == "EXECUTED_PASS"
    assert entry["git_available"] is False
    assert entry["git_sha"] is None
    assert entry["git_sha_source"] == "unavailable"
    assert entry["tree_sha"] is None
    assert entry["branch"] == "UNKNOWN"
    assert "no-git-ok" in entry["stdout"]["tail"]
    raw_path = out / entry["raw_evidence_path"]
    assert sha256_file(raw_path) == entry["sha256"]

    # Archives that know their frozen SHA may pass it explicitly; the source is
    # recorded so it can never be confused with a live git read.
    explicit_sha = "0123456789abcdef0123456789abcdef01234567"
    explicit_tree = "89abcdef0123456789abcdef0123456789abcdef"
    out_two = tmp_path / "packet_explicit"
    completed = _run_collector_in(
        archive / "scripts" / "m1b" / "collect_evidence.py",
        archive,
        "--command",
        command,
        "--git-sha",
        explicit_sha,
        "--tree-sha",
        explicit_tree,
        out=out_two,
        case_id="T-NOGIT-02",
    )
    assert completed.returncode == 0, completed.stderr
    explicit_entry = read_entries(out_two)[0]
    assert explicit_entry["git_available"] is False
    assert explicit_entry["git_sha"] == explicit_sha
    assert explicit_entry["git_sha_source"] == "explicit"
    assert explicit_entry["tree_sha"] == explicit_tree
