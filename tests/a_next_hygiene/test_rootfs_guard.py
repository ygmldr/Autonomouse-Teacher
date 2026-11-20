"""Tests for scripts/a_next/rootfs_guard.py (synthetic trees only)."""

from __future__ import annotations

import os
from conftest import canonical_sha, make_tree, output_json, run_script


def test_missing_path_exits_33(tmp_path):
    proc = run_script("rootfs_guard.py", "--rootfs", tmp_path / "missing", "--skip-sha")
    assert proc.returncode == 33
    assert output_json(proc)["verdict"] == "PATH_MISSING"


def test_clean_tree_passes_with_expected_sha(tmp_path):
    tree = make_tree(tmp_path / "rootfs", {"etc/a.txt": "alpha\n", "usr/bin/tool": "T"})
    (tree / "usr" / "bin" / "tool").chmod(0o755)
    os.chmod(tree, 0o755)
    sha = canonical_sha(tree)
    proc = run_script("rootfs_guard.py", "--rootfs", tree, "--expected-sha", sha)
    assert proc.returncode == 0, proc.stderr
    document = output_json(proc)
    assert document["verdict"] == "OK"
    assert document["permissions"]["violation_count"] == 0
    assert document["sha_matches_expected"] is True


def test_world_writable_violation(tmp_path):
    tree = make_tree(tmp_path / "rootfs", {"etc/a.txt": "alpha\n"})
    (tree / "etc").chmod(0o777)
    proc = run_script("rootfs_guard.py", "--rootfs", tree, "--skip-sha")
    assert proc.returncode == 30
    document = output_json(proc)
    assert document["verdict"] == "PERMISSION_VIOLATION"
    reasons = {item["reason"] for item in document["permissions"]["violations"]}
    assert "group_or_other_writable" in reasons


def test_test_uid_owner_writable_violation(tmp_path):
    tree = make_tree(tmp_path / "rootfs", {"etc/a.txt": "alpha\n"})
    # --test-uid 0 + root-owned u+w file = writable by the test uid
    proc = run_script("rootfs_guard.py", "--rootfs", tree, "--skip-sha", "--test-uid", "0")
    assert proc.returncode == 30
    reasons = {item["reason"] for item in output_json(proc)["permissions"]["violations"]}
    assert "test_uid_writable" in reasons


def test_sha_mismatch_exits_31(tmp_path):
    tree = make_tree(tmp_path / "rootfs", {"etc/a.txt": "alpha\n"})
    proc = run_script(
        "rootfs_guard.py", "--rootfs", tree, "--expected-sha", "0" * 64
    )
    assert proc.returncode == 31
    assert output_json(proc)["verdict"] == "SHA_MISMATCH"


def test_require_ro_mount_fails_on_writable_tmp(tmp_path):
    tree = make_tree(tmp_path / "rootfs", {"etc/a.txt": "alpha\n"})
    sha = canonical_sha(tree)
    proc = run_script(
        "rootfs_guard.py", "--rootfs", tree, "--expected-sha", sha, "--require-ro-mount"
    )
    assert proc.returncode == 32
    assert output_json(proc)["verdict"] == "NOT_READ_ONLY_MOUNT"


def test_emit_commands_and_read_only_behavior(tmp_path):
    tree = make_tree(tmp_path / "rootfs", {"etc/a.txt": "alpha\n"})
    before = canonical_sha(tree)
    proc = run_script("rootfs_guard.py", "--rootfs", tree, "--skip-sha", "--emit-commands")
    assert proc.returncode == 0, proc.stderr
    document = output_json(proc)
    assert document["verification_commands"]
    assert any(str(tree) in command for command in document["verification_commands"])
    assert canonical_sha(tree) == before  # guard must never modify the checked tree


def test_json_out_written(tmp_path):
    tree = make_tree(tmp_path / "rootfs", {"etc/a.txt": "alpha\n"})
    sha = canonical_sha(tree)
    json_out = tmp_path / "report.json"
    proc = run_script(
        "rootfs_guard.py", "--rootfs", tree, "--expected-sha", sha, "--json-out", json_out
    )
    assert proc.returncode == 0
    assert json_out.is_file()
    assert json_out.read_text().startswith("{")
