"""B-PR5 CLI/demo smoke tests: offline execution, determinism and JSON output.

Every invocation is a real subprocess run of the shipped modules
(``python -m m1_teacher.demo`` / ``python -m m1_teacher.cli``) from the
repository root, with no network and no API key.  The demo's wall-clock-free
output makes two independent runs byte-identical (a different ``PYTHONHASHSEED``
is used per process by default, so this also covers hash-order independence).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO = "m1_teacher.demo"
CLI = "m1_teacher.cli"
WALL_CLOCK_RE = re.compile(r"\b(20\d{2}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)\b")
ALLOWED_TIMESTAMPS = {"2026-11-20T00:00:00Z"}


def run_module(module: str, *args: str, timeout: int = 180) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", module, *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
        env={**os.environ},
    )


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return run_module(CLI, *args)


# ---------------------------------------------------------------------------
# CLI surface
# ---------------------------------------------------------------------------
def test_cli_help_works() -> None:
    completed = run_cli("--help")
    assert completed.returncode == 0
    assert "usage:" in completed.stdout
    assert "M1-A" in completed.stdout
    for flag in ("--demo", "--student", "--db", "--json", "--write-evidence"):
        assert flag in completed.stdout


def test_cli_without_arguments_prints_help() -> None:
    completed = run_cli()
    assert completed.returncode == 0
    assert "usage:" in completed.stdout


def test_cli_rejects_invalid_turn_budget() -> None:
    completed = run_cli("--demo", "--max-turns", "3", "--pause-after-turns", "5")
    assert completed.returncode == 2
    assert "pause-after-turns" in completed.stderr


def test_cli_student_a_json_is_machine_readable() -> None:
    completed = run_cli("--student", "a", "--json")
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["schema"] == "m1a.cli_run.v0"
    assert payload["contract_version"] == "m1a.v0"
    assert set(payload["students"]) == {"a"}
    summary = payload["students"]["a"]
    assert summary["student_fixture"] == "student_a"
    assert summary["final"]["phase"] in {
        "DIAGNOSE",
        "TEACH",
        "PRACTICE",
        "ASSESS",
        "REVIEW",
        "COMPLETE",
    }
    assert summary["verify_rebuild"] is True
    assert payload["path_differences"] is None
    assert "_session_events" not in json.dumps(payload)


def test_cli_student_b_uses_given_database(tmp_path: Path) -> None:
    db_path = tmp_path / "student_b.sqlite"
    completed = run_cli("--student", "b", "--db", str(db_path))
    assert completed.returncode == 0, completed.stderr
    assert db_path.is_file() and db_path.stat().st_size > 0
    assert "Student B" in completed.stdout
    assert "[resume]" in completed.stdout
    assert "snapshot_equal=True" in completed.stdout
    assert "not real teaching effect" in completed.stdout


def test_cli_student_both_reports_different_paths() -> None:
    completed = run_cli("--student", "both")
    assert completed.returncode == 0, completed.stderr
    assert "Student A" in completed.stdout and "Student B" in completed.stdout
    path_line = next(line for line in completed.stdout.splitlines() if line.startswith("[paths]"))
    differences = json.loads(path_line.split(" ", 1)[1])
    assert all(differences.values()), differences


# ---------------------------------------------------------------------------
# Demo: offline and deterministic
# ---------------------------------------------------------------------------
def test_demo_is_deterministic_across_processes() -> None:
    first = run_module(DEMO)
    second = run_module(DEMO)
    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert first.stdout == second.stdout
    assert first.stderr == ""
    text = first.stdout
    for marker in (
        "Student A",
        "Student B",
        "not real teaching effect",
        "no network",
        "MOCK",
        "DETERMINISTIC",
        "NOT_VERIFIED",
        "offline demo PASS",
    ):
        assert marker in text, marker
    path_line = next(line for line in text.splitlines() if line.startswith("[paths]"))
    assert all(json.loads(path_line.split(" ", 1)[1]).values())
    resume_lines = [line for line in text.splitlines() if line.startswith("[resume]")]
    assert len(resume_lines) == 2
    for line in resume_lines:
        for flag in ("snapshot_equal=True", "plan_equal=True", "pending_equal=True"):
            assert flag in line


def test_demo_contains_no_wall_clock_timestamps() -> None:
    completed = run_module(DEMO)
    assert completed.returncode == 0, completed.stderr
    timestamps = set(WALL_CLOCK_RE.findall(completed.stdout))
    assert timestamps <= ALLOWED_TIMESTAMPS, timestamps


def test_cli_demo_matches_module_demo() -> None:
    module = run_module(DEMO)
    cli = run_cli("--demo")
    assert module.returncode == 0 and cli.returncode == 0
    assert cli.stdout == module.stdout


def test_cli_demo_json_mode() -> None:
    completed = run_cli("--demo", "--json")
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["schema"] == "m1a.e2e_scenario.v0"
    assert set(payload["students"]) == {"a", "b"}
    assert all(payload["path_differences"].values())
    assert payload["policy_checks"]["prerequisite_remediation_before_target"] is True
    assert payload["policy_checks"]["interrupt_resume_state_equal"] is True
    assert payload["policy_checks"]["history_verify_rebuild"] is True
    assert payload["fixed_timestamp"] == "2026-11-20T00:00:00Z"
    assert "_session_events" not in json.dumps(payload)


# ---------------------------------------------------------------------------
# Reproducible evidence through the CLI
# ---------------------------------------------------------------------------
def test_cli_write_evidence_is_reproducible(tmp_path: Path) -> None:
    first_dir = tmp_path / "evidence_one"
    second_dir = tmp_path / "evidence_two"
    first = run_cli("--demo", "--write-evidence", str(first_dir))
    second = run_cli("--demo", "--write-evidence", str(second_dir))
    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    for name in ("e2e_student_a.jsonl", "e2e_student_b.jsonl"):
        first_bytes = (first_dir / name).read_bytes()
        second_bytes = (second_dir / name).read_bytes()
        assert first_bytes == second_bytes
        lines = [json.loads(line) for line in first_bytes.decode("utf-8").splitlines()]
        assert lines
        assert all(line["evidence_classes"] == ["MOCK", "DETERMINISTIC"] for line in lines)
        for line in lines:
            rendered = json.dumps(line, ensure_ascii=False)
            assert "scoring/" not in rendered
            assert WALL_CLOCK_RE.findall(rendered) in ([], ["2026-11-20T00:00:00Z"])
    # P1-1: summary must be byte-identical across runs/directories too.
    first_summary_bytes = (first_dir / "e2e_summary.json").read_bytes()
    second_summary_bytes = (second_dir / "e2e_summary.json").read_bytes()
    assert first_summary_bytes == second_summary_bytes
    summary = json.loads(first_summary_bytes.decode("utf-8"))
    assert summary["schema"] == "m1a.e2e_scenario.v0"
    assert summary["students"]["a"]["student_fixture"] == "student_a"
    assert "generated_at_utc_date" not in summary and "base_commit" not in summary
    manifest = summary["artifact_manifest"]
    assert manifest["generated_at"] == "2026-11-20T00:00:00Z"
    assert manifest["base_sha"] == "3e7afee077845a071cd364e93ab209cac20b2d5f"
    for name, digest in summary["evidence_hashes"].items():
        actual = hashlib.sha256((first_dir / name).read_bytes()).hexdigest()
        assert actual == digest, name
    assert "[evidence] wrote" in first.stdout
    for name in ("e2e_student_a.jsonl", "e2e_student_b.jsonl"):
        assert name in first.stdout


def test_cli_evidence_summary_is_identical_in_a_no_git_copy(tmp_path: Path) -> None:
    """P1-1: CLI evidence regenerates identical summary bytes from a clean archive copy."""

    repo_out = tmp_path / "repo_out"
    repo_run = run_cli("--demo", "--write-evidence", str(repo_out))
    assert repo_run.returncode == 0, repo_run.stderr

    clean_tree = tmp_path / "clean_tree"
    clean_tree.mkdir()
    shutil.copytree(
        REPO_ROOT / "m1_teacher",
        clean_tree / "m1_teacher",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    shutil.copytree(REPO_ROOT / "fixtures" / "m1_teacher", clean_tree / "fixtures" / "m1_teacher")
    assert not (clean_tree / ".git").exists()
    clean_out = tmp_path / "clean_out"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "m1_teacher.cli",
            "--demo",
            "--write-evidence",
            str(clean_out),
        ],
        cwd=str(clean_tree),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert completed.returncode == 0, completed.stderr
    assert (clean_out / "e2e_summary.json").read_bytes() == (
        repo_out / "e2e_summary.json"
    ).read_bytes()
    for name in ("e2e_student_a.jsonl", "e2e_student_b.jsonl"):
        assert (clean_out / name).read_bytes() == (repo_out / name).read_bytes()
