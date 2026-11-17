"""Host-only D3 contract tests (no container, no Key, no network).

These assert the *runner contract*: the case table, scenario/admission
overrides, audited probe allow-list, real fault-injection primitives and the
same-claim negative topology. They are supplementary to the real Level A/B
evidence in artifacts/g3d/d3/ and never substitute for it.
"""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "g3d"))

import lib_g3d as lib  # noqa: E402
import launch as launcher  # noqa: E402
import d3_runner as d3  # noqa: E402


def test_case_table_matches_matrix_scope() -> None:
    assert set(d3.CASES) == {
        "d3-c01-echo", "d3-c01-tool", "d3-c01-resume",
        "d3-c02", "d3-c03", "d3-c04", "d3-c05", "d3-c06",
        "d3-c07-before", "d3-c07-after", "d3-c07-two",
        "d3-c08-half", "d3-c08-disconnect", "d3-c08-sigterm",
        "d3-c09-broker", "d3-c09-fake", "d3-c09-stall",
        "d3-c10", "d3-c11-real", "d3-c11-same", "d3-c12",
    }
    for case, spec in d3.CASES.items():
        assert spec["scenario"] in launcher.SCENARIO_PROMPT, case
        assert spec["scenario"] in launcher.SCENARIO_ADMISSION, case


def test_deadline_overrides_are_stricter_and_bounded() -> None:
    for scenario in ("deadline_broker", "deadline_fake", "deadline_stall"):
        override = launcher.SCENARIO_ADMISSION[scenario]
        assert 100 <= override["deadline_ms"] <= 30000
        assert override["deadline_ms"] < 30000
    assert launcher.SCENARIO_ADMISSION["deadline_stall"]["deadline_ms"] == 800
    assert launcher.SCENARIO_ADMISSION["deadline_fake"]["fake_scenario"] == "timeout"


def test_stream_scenario_is_real_fake_mode() -> None:
    assert launcher.SCENARIO_ADMISSION["stream"] == {
        "fake_scenario": "stream_slow", "max_calls": 1}
    source = (REPO_ROOT / "scripts" / "g3d" / "stage" /
              "candidate_entry.py").read_text(encoding="utf-8")
    assert '"stream"' in source
    assert "monotonic_ms" in source
    assert "STREAM_TIMING_MISSING" in source


def test_d3_probe_allowlist_exact_and_no_new_d2_probe() -> None:
    found = {path.name for path in
             (REPO_ROOT / "scripts" / "g3d" / "d3_probes").glob("*.py")}
    assert found == set(lib.D3_PROBE_FILES)
    assert not (found & set(lib.D2_PROBE_FILES))
    assert lib.D3_PROBE_PATHS == frozenset(
        f"run/d3-probes/{name}" for name in lib.D3_PROBE_FILES)


def test_probes_are_candidate_side_and_use_real_uds() -> None:
    root = REPO_ROOT / "scripts" / "g3d" / "d3_probes"
    for name in lib.D3_PROBE_FILES:
        source = (root / name).read_text(encoding="utf-8")
        assert "autoteacher_m0" not in source
        assert "/work/state" not in source
        assert "/project/run/probes" in source
    assert "SOCKET_PATH" in (root / "d3_cancel.py").read_text()
    assert "SIGKILL" in (root / "d3_kill_before_send.py").read_text()
    assert "Barrier(2)" in (root / "d3_same_claim.py").read_text()


def test_settle_crash_hook_is_explicitly_allowlisted() -> None:
    assert "after_broker_settle_before_journal_mark" in lib.TRUSTED_CRASH_HOOKS
    assert "after_response_before_settlement" in lib.TRUSTED_CRASH_HOOKS


def test_runner_uses_real_sigstop_and_real_restart() -> None:
    source = (REPO_ROOT / "scripts" / "g3d" / "d3_runner.py").read_text(
        encoding="utf-8")
    assert "signal.SIGSTOP" in source
    assert "signal.SIGCONT" in source
    assert "lib.trusted_run_argv(" in source
    assert '"podman", "wait"' in source
    assert "reconcile_on_startup" in source  # documented recovery path
    assert "os._exit(97)" not in source


def test_restart_does_not_reuse_crash_hook() -> None:
    source = (REPO_ROOT / "scripts" / "g3d" / "d3_runner.py").read_text(
        encoding="utf-8")
    start = source.index("def _restart_trusted")
    end = source.index("def _reconcile_state_checks")
    block = source[start:end]
    assert "crash_hook" not in block
    assert "G3B_CRASH_HOOK" not in block


def test_same_claim_topology_is_two_controllers_two_sockets() -> None:
    source = (REPO_ROOT / "scripts" / "g3d" / "d3_runner.py").read_text(
        encoding="utf-8")
    assert '"/work/g3b/bridge2.sock"' in source
    assert "controller2.json" in source
    assert "/work/state/admission2.json" in source
    assert "ATTEMPT_ALREADY_STARTED" in source
    probe = (REPO_ROOT / "scripts" / "g3d" / "d3_probes" /
             "d3_same_claim.py").read_text(encoding="utf-8")
    assert "--socket-a" in probe and "--socket-b" in probe


def test_real_dsh_concurrency_uses_two_sessions_and_same_prompt() -> None:
    source = (REPO_ROOT / "scripts" / "g3d" / "d3_runner.py").read_text(
        encoding="utf-8")
    assert "g3d-d3-c11-a" in source and "g3d-d3-c11-b" in source
    assert 'scenario_prompt("c11")' in source
    assert "both_running" in source
    assert "distinct_business_digest" in source


def test_restart_before_attempt_and_after_attempt_are_distinct() -> None:
    assert d3.CASES["d3-c03"]["crash_hook"] == "after_claim_before_attempt_start"
    assert d3.CASES["d3-c04"]["crash_hook"] == "after_attempt_start_before_fake_send"
    assert d3.CASES["d3-c05"]["restarts"] == 2
    assert d3.CASES["d3-c06"]["restarts"] == 2


def test_runner_does_not_modify_product_src() -> None:
    diff = subprocess.run(
        ["git", "diff", "--quiet", lib.PRODUCT_BASE, "--", "src"],
        cwd=str(REPO_ROOT))
    assert diff.returncode == 0
    diff = subprocess.run(
        ["git", "diff", "--quiet", lib.PRODUCT_BASE, "--", "spikes", "plugins"],
        cwd=str(REPO_ROOT))
    assert diff.returncode == 0


def test_build_stage_copies_d3_probes() -> None:
    source = (REPO_ROOT / "scripts" / "g3d" / "build_stage.py").read_text(
        encoding="utf-8")
    assert "run/d3-probes" in source
    assert "D3_PROBE_FILES" in source
    assert "D3 probe set does not match the allow-list" in source


def test_levels_file_marks_real_candidate_and_dsh() -> None:
    source = (REPO_ROOT / "scripts" / "g3d" / "d3_runner.py").read_text(
        encoding="utf-8")
    assert '"real_candidate_os": True' in source
    assert '"real_dsh_positive"' in source
    assert '"trusted_fault_injection"' in source
