"""Host-only contract tests for the A-PR3 / R-REV6 preparation artifacts.

These tests never start a container and never touch the network.  They pin the
shape of the execution matrix and the environment preflight so that the
exclusive OCI window cannot start with an incomplete or silently-degraded plan.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MATRIX_PATH = REPO / "scripts" / "a_next" / "rrev6" / "case_matrix.json"
ENV_CHECK_PATH = REPO / "scripts" / "a_next" / "rrev6" / "env_check.py"
MAIN_REPO = Path("/root/Autonomous Teacher")

INJECTION_STABILITY = {"STABLE", "CONDITIONAL"}
REQUIRED_CASE_KEYS = {
    "case_id", "goal", "covers", "method", "injection",
    "injection_stability", "expected", "checks",
}


def _matrix() -> dict:
    return json.loads(MATRIX_PATH.read_text(encoding="utf-8"))


def _load_env_check():
    spec = importlib.util.spec_from_file_location("a_next_rrev6_env_check",
                                                  ENV_CHECK_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_matrix_declares_all_required_cases() -> None:
    document = _matrix()
    assert document["schema"] == "m0.a_next.rrev6.case-matrix.v1"
    assert document["evidence_level_target"] == "L2-REAL-DSH-FAKE"
    cases = document["cases"]
    ids = [case["case_id"] for case in cases]
    assert len(ids) == len(set(ids)), "duplicate case ids"
    # The A4 instruction requires Echo/Tool/Resume/Replay plus crash/restart/lost
    # and timeout/revocation coverage.
    required_prefixes = ("R6-01", "R6-02", "R6-03", "R6-04", "R6-05",
                         "R6-06", "R6-07", "R6-08", "R6-10", "R6-12", "R6-13")
    for prefix in required_prefixes:
        assert prefix in ids, f"missing case {prefix}"
    goals = " ".join(case["goal"].lower() for case in cases)
    for keyword in ("echo", "tool", "resume", "replay", "timeout",
                    "revocation", "candidate crash", "broker"):
        assert keyword in goals, f"matrix does not cover {keyword}"


def test_every_case_is_explicitly_classified() -> None:
    document = _matrix()
    for case in document["cases"]:
        assert REQUIRED_CASE_KEYS <= set(case), (case.get("case_id"), "keys")
        assert case["injection_stability"] in INJECTION_STABILITY, case
        assert case["expected"], case["case_id"]
        assert case["checks"], case["case_id"]
        assert isinstance(case["checks"], list)
        assert case["covers"], case["case_id"]


def test_evidence_contract_never_conflates_the_two_digests() -> None:
    contract = _matrix()["evidence_contract"]
    names = [row["name"] for row in contract["digest_bindings"]]
    assert "prepared_digest==claim.request_digest" in names
    assert "payload_digest==receipt.raw_sha256" in names
    note = " ".join(row["note"] for row in contract["digest_bindings"]).lower()
    assert "never asserted equal" in note, "digest conflation guard missing"
    assert contract["per_case_required"], "per-case evidence list missing"


def test_window_request_is_bounded_and_has_abort_conditions() -> None:
    window = _matrix()["window"]
    requested = window["requested_duration_minutes"]
    expected = window["expected_duration_minutes"]
    assert isinstance(requested, int) and requested >= expected
    assert 0 < requested <= 60
    assert len(window["abort_conditions"]) >= 4
    assert any("drift" in item.lower() for item in window["abort_conditions"])
    assert any("key" in item.lower() or "http" in item.lower()
               for item in window["abort_conditions"])


def test_not_run_predictions_are_explicit() -> None:
    predictions = _matrix()["not_run_predictions"]
    assert len(predictions) >= 4
    ids = [row["id"] for row in predictions]
    assert len(ids) == len(set(ids))
    assert any("provider" in row["item"].lower() for row in predictions)
    assert any("sigkill" in row["item"].lower() for row in predictions)


def test_env_check_module_is_importable_and_named_paths_exist() -> None:
    module = _load_env_check()
    assert module.ROOTFS_CANON.startswith("25491e45")
    assert module.DEPS_CANON.startswith("e07729d7")
    # Frozen reference sources are resolved through a read-only candidate list
    # (main repo tree may be restored from verified copies after the 19:53Z
    # environment event); never copied by this test.
    if MAIN_REPO.is_dir():
        assert all(path.is_absolute() for _label, path in module.ROOTFS_CANDIDATES)
        assert all(path.is_absolute() for _label, path in module.DEPS_CANDIDATES)
        assert module.WORKTREE == REPO


def test_env_check_reports_canonical_frozen_inputs() -> None:
    module = _load_env_check()
    rootfs = module._first_existing(module.ROOTFS_CANDIDATES)
    deps = module._first_existing(module.DEPS_CANDIDATES)
    if rootfs is None or deps is None:
        import pytest
        pytest.skip("no frozen rootfs/deps candidate present on this host")
    record = module.frozen_record()
    assert record["rootfs"]["sha256"] == module.ROOTFS_CANON
    assert record["deps"]["sha256"] == module.DEPS_CANON
    assert record["rootfs"]["canonical"] is True
    assert record["deps"]["canonical"] is True


def test_env_check_reports_no_containers_and_versions() -> None:
    module = _load_env_check()
    podman = module.podman_record()
    if not podman["version_ok"]:
        import pytest
        pytest.skip("podman unavailable in this environment")
    assert podman["version"].startswith("podman version 4.9")
    assert podman["containers_empty"] is True, podman["containers"]
    dsh = module.dsh_record()
    assert module._normalise_version(dsh["sdk_version"]) == "0.2.2rc2"
    assert dsh["runtime_canonical"] is True


def test_prep_files_do_not_modify_frozen_matrices() -> None:
    """The frozen G4-R matrix and old reports must be byte-identical to the base."""
    frozen = [
        "docs/Autonomous_Teacher_M0_G4R_Test_Evidence_Matrix_v1.0.csv",
        "docs/REVIEW_G4R_INDEPENDENT.md",
    ]
    for relative in frozen:
        diff = subprocess.run(
            ["git", "diff", "--quiet", "fd1d3a6d101f17e6a86d7c43f06c630326e3e3af",
             "--", relative], cwd=str(REPO), capture_output=True)
        assert diff.returncode == 0, f"frozen file changed: {relative}"


def test_prep_sources_are_present() -> None:
    assert MATRIX_PATH.is_file()
    assert ENV_CHECK_PATH.is_file()
    # The exclusive-window runner is committed before the Lead-approved window
    # opens; it is intentionally not required by the preparation commit.
    runner = REPO / "scripts" / "a_next" / "rrev6" / "run_l2_matrix.py"
    assert runner.parent.is_dir()
