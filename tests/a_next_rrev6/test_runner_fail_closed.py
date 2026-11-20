"""Host-only unit tests for the A-PR3 runner fail-closed contract (P2-A4-2).

These tests never start a container and never touch the network.  They pin the
Reviewer finding that a failed matrix must never report ``ok=true`` / exit 0
just because the T0/T1 frozen gates passed, and that a fresh worktree with
missing staged inputs must fail fast with an explicit prerequisite message.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
RUNNER_PATH = REPO / "scripts" / "a_next" / "rrev6" / "run_l2_matrix.py"
AUDIT_PATH = REPO / "scripts" / "a_next" / "rrev6" / "evidence_audit.py"

CASE_IDS = [f"R6-{index:02d}" for index in range(1, 13)] + ["R6-04B", "R6-13"]
# R6-13 is the audit-only aggregate row; it is part of the 14 Owner status rows.
AUDIT_CASE_IDS = [case_id for case_id in CASE_IDS if case_id != "R6-13"] + ["R6-13"]


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def runner():
    return _load_module("a_next_rrev6_run_l2_matrix_tests", RUNNER_PATH)


@pytest.fixture(scope="module")
def audit_cli():
    return _load_module("a_next_rrev6_evidence_audit_tests", AUDIT_PATH)


def _audit(*, statuses: dict[str, str] | None = None) -> dict:
    statuses = statuses or {case_id: "PASS" for case_id in AUDIT_CASE_IDS}
    cases = {case_id: {"status": status} for case_id, status in statuses.items()}
    return {
        "schema": "m0.a_next.rrev6.audit.v1",
        "cases": cases,
        "counts": {
            "pass": sum(1 for value in statuses.values() if value == "PASS"),
            "partial": sum(1 for value in statuses.values() if value == "PARTIAL"),
            "not_run": sum(1 for value in statuses.values() if value == "NOT_RUN"),
            "total": len(statuses),
        },
    }


def test_all_pass_audit_is_ok(runner) -> None:
    decision = runner.decide_run(
        containers_after=[], frozen_rootfs_unchanged=True,
        frozen_deps_unchanged=True, audit=_audit(),
        expected_case_ids=AUDIT_CASE_IDS)
    assert decision["ok"] is True
    assert decision["failure_reasons"] == []


@pytest.mark.parametrize("status", ["INTERNAL", "PARTIAL", "FAIL", "NOT_RUN",
                                    "TIMEOUT", "BLOCKED", "ERROR"])
def test_any_non_pass_case_status_fails_closed(runner, status: str) -> None:
    statuses = {case_id: "PASS" for case_id in AUDIT_CASE_IDS}
    statuses["R6-05"] = status
    decision = runner.decide_run(
        containers_after=[], frozen_rootfs_unchanged=True,
        frozen_deps_unchanged=True, audit=_audit(statuses=statuses),
        expected_case_ids=AUDIT_CASE_IDS)
    assert decision["ok"] is False
    assert "audit_non_pass_cases" in decision["failure_reasons"]
    assert decision["audit_decision"]["problems"][0]["cases"] == {"R6-05": status}


def test_missing_audit_fails_closed(runner) -> None:
    for audit in (None, {}, {"cases": {}}):
        decision = runner.decide_run(
            containers_after=[], frozen_rootfs_unchanged=True,
            frozen_deps_unchanged=True, audit=audit,
            expected_case_ids=AUDIT_CASE_IDS)
        assert decision["ok"] is False
        assert "audit_missing" in decision["failure_reasons"]


def test_missing_expected_case_fails_closed(runner) -> None:
    statuses = {case_id: "PASS" for case_id in AUDIT_CASE_IDS if case_id != "R6-13"}
    decision = runner.decide_run(
        containers_after=[], frozen_rootfs_unchanged=True,
        frozen_deps_unchanged=True, audit=_audit(statuses=statuses),
        expected_case_ids=AUDIT_CASE_IDS)
    assert decision["ok"] is False
    assert "audit_case_missing" in decision["failure_reasons"]


def test_counts_mismatch_fails_closed(runner) -> None:
    audit = _audit()
    audit["counts"]["pass"] = len(AUDIT_CASE_IDS) - 1  # inconsistent summary
    decision = runner.decide_run(
        containers_after=[], frozen_rootfs_unchanged=True,
        frozen_deps_unchanged=True, audit=audit,
        expected_case_ids=AUDIT_CASE_IDS)
    assert decision["ok"] is False
    assert "audit_pass_count_mismatch" in decision["failure_reasons"]


def test_frozen_drift_or_container_residual_fails_closed(runner) -> None:
    base = dict(audit=_audit(), expected_case_ids=AUDIT_CASE_IDS)
    assert runner.decide_run(containers_after=["leftover"],
                             frozen_rootfs_unchanged=True,
                             frozen_deps_unchanged=True, **base)["ok"] is False
    assert runner.decide_run(containers_after=[],
                             frozen_rootfs_unchanged=False,
                             frozen_deps_unchanged=True, **base)["ok"] is False
    assert runner.decide_run(containers_after=[],
                             frozen_rootfs_unchanged=True,
                             frozen_deps_unchanged=False, **base)["ok"] is False


def _prereq_kwargs(tmp_path: Path) -> dict:
    return {
        "stage": tmp_path / "stage",
        "rootfs": tmp_path / "rootfs",
        "deps": tmp_path / "deps",
        "g4c_root": tmp_path / "g4c",
        "plugin_modules": tmp_path / "node_modules",
        "launch_case": RUNNER_PATH.with_name("launch_case.py"),
        "evidence_audit": AUDIT_PATH,
        "matrix_spec": RUNNER_PATH.with_name("case_matrix.json"),
        "canonical_check": False,
    }


def test_prerequisites_missing_each_input_is_named(runner, tmp_path: Path) -> None:
    result = runner.prerequisite_problems(**_prereq_kwargs(tmp_path))
    assert result["ok"] is False
    problem_ids = {problem["id"] for problem in result["problems"]}
    assert {
        "staged_rootfs_missing",
        "staged_deps_missing",
        "artifacts_g4c_missing",
        "plugin_node_modules_missing",
        "stage_manifest_missing",
    } <= problem_ids
    for problem in result["problems"]:
        assert problem["remediation"], problem
        assert problem["path"], problem


def test_prerequisites_missing_runs_dir_is_explicit(runner, tmp_path: Path) -> None:
    kwargs = _prereq_kwargs(tmp_path)
    for key in ("rootfs", "deps", "g4c_root", "plugin_modules"):
        Path(kwargs[key]).mkdir(parents=True)
    kwargs["stage"].mkdir()
    (kwargs["stage"] / "manifest.json").write_text("{}\n", encoding="utf-8")
    result = runner.prerequisite_problems(**kwargs)
    assert result["ok"] is False
    problem_ids = {problem["id"] for problem in result["problems"]}
    assert problem_ids == {"artifacts_g4c_runs_missing"}
    remediation = result["problems"][0]["remediation"]
    assert "mkdir -p" in remediation and "runs" in remediation


def test_prerequisites_ok_when_staged_inputs_present(runner, tmp_path: Path) -> None:
    kwargs = _prereq_kwargs(tmp_path)
    for key in ("rootfs", "deps", "g4c_root", "plugin_modules"):
        Path(kwargs[key]).mkdir(parents=True)
    (kwargs["g4c_root"] / "runs").mkdir()
    kwargs["stage"].mkdir()
    (kwargs["stage"] / "manifest.json").write_text("{}\n", encoding="utf-8")
    result = runner.prerequisite_problems(**kwargs)
    assert result["ok"] is True, result["problems"]
    assert result["problems"] == []


def test_real_worktree_prerequisites_are_present(runner) -> None:
    """The committed worktree must itself satisfy the documented prerequisites."""
    stages = sorted((REPO / "artifacts" / "g4" / "c" / "stages").glob("stage-*"),
                    key=lambda path: path.stat().st_mtime)
    if not stages:
        pytest.skip("no Stage in this worktree (fresh checkout)")
    result = runner.prerequisite_problems(stage=stages[-1], canonical_check=True)
    assert result["ok"] is True, result["problems"]


def test_standalone_audit_cli_fails_closed_on_empty_run(audit_cli,
                                                       tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    run_root.mkdir()
    out = tmp_path / "audit.json"
    exit_code = audit_cli.main(["--run", str(run_root), "--out", str(out)])
    assert exit_code != 0
    document = json.loads(out.read_text(encoding="utf-8"))
    assert document["ok"] is False
    assert document["failure_reasons"]


def test_run_status_file_contract_is_documented() -> None:
    """The runner writes summary.json with fail_closed/ok fields (static guard)."""
    source = RUNNER_PATH.read_text(encoding="utf-8")
    for marker in ('"audit_ok"', '"fail_closed"', '"failure_reasons"',
                   "RUNNER_PREREQ_MISSING", "prerequisite_problems",
                   "decide_run"):
        assert marker in source, f"runner contract marker missing: {marker}"
