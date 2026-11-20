"""Tests for scripts/a_next/oci_guard.py (synthetic trees only)."""

from __future__ import annotations

import json
from pathlib import Path

from conftest import canonical_sha, make_tree, output_json, run_script


def _base_args(frozen: tuple[Path, str], evidence: Path) -> list[object]:
    frozen_path, frozen_sha = frozen
    return [
        "--frozen-rootfs",
        frozen_path,
        "--frozen-sha",
        frozen_sha,
        "--evidence-dir",
        evidence,
    ]


def test_check_rootfs_detects_frozen_by_path(frozen_tree):
    path, sha = frozen_tree
    proc = run_script("oci_guard.py", "check-rootfs", path, "--frozen-rootfs", path, "--frozen-sha", sha)
    assert proc.returncode == 10, proc.stderr
    document = output_json(proc)
    assert document["is_frozen"] is True
    assert document["verdict"] == "rootfs_is_the_frozen_tree"


def test_check_rootfs_detects_frozen_by_canonical_hash(frozen_tree, tmp_path):
    path, sha = frozen_tree
    copy = tmp_path / "lookalike"
    copy.parent.mkdir(exist_ok=True)
    import shutil

    shutil.copytree(path, copy)
    assert canonical_sha(copy) == sha
    proc = run_script("oci_guard.py", "check-rootfs", copy, "--frozen-sha", sha)
    assert proc.returncode == 10, proc.stderr
    assert output_json(proc)["verdict"] == "rootfs_canonical_hash_matches_frozen"


def test_check_rootfs_detects_marker(frozen_tree, tmp_path):
    path, sha = frozen_tree
    marked = make_tree(tmp_path / "marked", {"etc/a.txt": "x", ".a_next_frozen_rootfs": ""})
    proc = run_script("oci_guard.py", "check-rootfs", marked, "--frozen-sha", sha)
    assert proc.returncode == 10
    assert output_json(proc)["verdict"] == "rootfs_has_frozen_marker"


def test_check_rootfs_allows_working_copy(frozen_tree, working_tree, tmp_path):
    path, sha = frozen_tree
    proc = run_script(
        "oci_guard.py",
        "check-rootfs",
        working_tree,
        "--frozen-rootfs",
        path,
        "--frozen-sha",
        sha,
    )
    assert proc.returncode == 0, proc.stderr
    document = output_json(proc)
    assert document["is_frozen"] is False


def test_preflight_refuses_evidence_dir_already_exists(frozen_tree, working_tree, tmp_path):
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    proc = run_script(
        "oci_guard.py", "preflight", "--rootfs", working_tree, *_base_args(frozen_tree, evidence)
    )
    assert proc.returncode == 11
    assert output_json(proc)["refused"] == "evidence_dir_already_exists"


def test_preflight_refuses_evidence_under_frozen(frozen_tree, working_tree):
    frozen_path, _ = frozen_tree
    evidence = frozen_path / "nested-evidence"
    proc = run_script(
        "oci_guard.py", "preflight", "--rootfs", working_tree, *_base_args(frozen_tree, evidence)
    )
    assert proc.returncode == 11
    assert output_json(proc)["refused"] == "evidence_dir_under_frozen_tree"
    assert not evidence.exists()


def test_preflight_refuses_evidence_inside_rootfs(frozen_tree, working_tree):
    evidence = working_tree / "evidence"
    proc = run_script(
        "oci_guard.py", "preflight", "--rootfs", working_tree, *_base_args(frozen_tree, evidence)
    )
    assert proc.returncode == 11
    assert output_json(proc)["refused"] == "evidence_dir_inside_rootfs"


def test_run_refuses_frozen_rootfs(frozen_tree, tmp_path):
    frozen_path, sha = frozen_tree
    proc = run_script(
        "oci_guard.py",
        "run",
        "--rootfs",
        frozen_path,
        "--claim-id",
        "batch-1",
        *_base_args(frozen_tree, tmp_path / "evidence"),
        "--",
        "true",
    )
    assert proc.returncode == 10
    assert output_json(proc)["verdict"] == "rootfs_is_the_frozen_tree"


def test_run_refuses_lock_held(frozen_tree, working_tree, tmp_path):
    evidence = tmp_path / "evidence"
    lock = tmp_path / ".a_next.writer.lock"
    lock.write_text("{}")
    proc = run_script(
        "oci_guard.py",
        "run",
        "--rootfs",
        working_tree,
        "--claim-id",
        "batch-2",
        *_base_args(frozen_tree, evidence),
        "--",
        "true",
    )
    assert proc.returncode == 12
    assert output_json(proc)["refused"] == "writer_lock_held"


def test_run_success_writes_report_and_releases_lock(frozen_tree, working_tree, tmp_path):
    evidence = tmp_path / "evidence"
    out_note = evidence / "note.txt"
    proc = run_script(
        "oci_guard.py",
        "run",
        "--rootfs",
        working_tree,
        "--claim-id",
        "batch-3",
        *_base_args(frozen_tree, evidence),
        "--",
        "/bin/sh",
        "-c",
        'echo ok > "$1"',
        "sh",
        str(out_note),
    )
    assert proc.returncode == 0, proc.stderr
    document = output_json(proc)
    assert document["verdict"] == "OK"
    assert document["drift"]["frozen_rootfs_changed"] is False
    assert (evidence / "guard-report.json").is_file()
    assert (evidence / "stdout.txt").is_file()
    assert not (tmp_path / ".a_next.writer.lock").exists()
    report = json.loads((evidence / "guard-report.json").read_text())
    assert report["claim_id"] == "batch-3"


def test_run_detects_frozen_drift(frozen_tree, working_tree, tmp_path):
    frozen_path, _ = frozen_tree
    evidence = tmp_path / "evidence"
    proc = run_script(
        "oci_guard.py",
        "run",
        "--rootfs",
        working_tree,
        "--claim-id",
        "batch-drift",
        *_base_args(frozen_tree, evidence),
        "--",
        "/bin/sh",
        "-c",
        'echo pollution > "$1/drift.txt"',
        "sh",
        str(frozen_path),
    )
    assert proc.returncode == 20, proc.stderr
    document = output_json(proc)
    assert document["verdict"] == "DRIFT"
    assert document["drift"]["frozen_rootfs_changed"] is True
    assert (frozen_path / "drift.txt").is_file()  # synthetic tmp tree, not real frozen data


def test_run_detects_preexisting_drift(frozen_tree, working_tree, tmp_path):
    frozen_path, sha = frozen_tree
    (frozen_path / "etc" / "a.txt").write_text("mutated\n")
    proc = run_script(
        "oci_guard.py",
        "run",
        "--rootfs",
        working_tree,
        "--claim-id",
        "batch-pre",
        *_base_args(frozen_tree, tmp_path / "evidence"),
        "--",
        "true",
    )
    assert proc.returncode == 23
    assert output_json(proc)["refused"] == "frozen_rootfs_not_at_expected_sha_before_run"


def test_run_reports_wrapped_command_failure(frozen_tree, working_tree, tmp_path):
    evidence = tmp_path / "evidence"
    proc = run_script(
        "oci_guard.py",
        "run",
        "--rootfs",
        working_tree,
        "--claim-id",
        "batch-fail",
        *_base_args(frozen_tree, evidence),
        "--",
        "/bin/sh",
        "-c",
        "exit 7",
    )
    assert proc.returncode == 21
    document = output_json(proc)
    assert document["verdict"] == "COMMAND_FAILED"
    assert document["wrapped"]["exit_code"] == 7
    assert document["drift"]["frozen_rootfs_changed"] is False


def test_run_scrubs_key_like_env(frozen_tree, working_tree, tmp_path):
    import os

    evidence = tmp_path / "evidence"
    env_out = evidence / "env_out.txt"
    env = dict(os.environ)
    env["A_NEXT_FAKE_API_KEY"] = "sentinel-value-should-not-be-used"
    proc = run_script(
        "oci_guard.py",
        "run",
        "--rootfs",
        working_tree,
        "--claim-id",
        "batch-env",
        *_base_args(frozen_tree, evidence),
        "--",
        "/bin/sh",
        "-c",
        'printenv A_NEXT_FAKE_API_KEY > "$1" 2>/dev/null || echo UNSET > "$1"',
        "sh",
        str(env_out),
        env=env,
    )
    assert proc.returncode == 0, proc.stderr
    assert env_out.read_text().strip() == "UNSET"
    document = output_json(proc)
    assert "A_NEXT_FAKE_API_KEY" in document["env_scrubbed_names"]


def test_run_requires_frozen_snapshot(frozen_tree, working_tree, tmp_path):
    proc = run_script(
        "oci_guard.py",
        "run",
        "--rootfs",
        working_tree,
        "--evidence-dir",
        tmp_path / "evidence",
        "--claim-id",
        "batch-nosnap",
        "--",
        "true",
    )
    assert proc.returncode == 2
    assert output_json(proc)["refused"] == "frozen_rootfs_required_for_T0_T1_snapshot"


def test_preflight_refusal_does_not_create_evidence(frozen_tree, working_tree, tmp_path):
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    proc = run_script(
        "oci_guard.py", "run", "--rootfs", working_tree, "--claim-id", "x", *_base_args(frozen_tree, evidence), "--", "true"
    )
    assert proc.returncode == 11
    assert list(evidence.iterdir()) == []
