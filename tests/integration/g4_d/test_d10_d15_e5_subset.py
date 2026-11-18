"""D10-D14 / D15: E5 no-key subset probes over the real stage bytes."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import e5_probe
import lib_g4c


def stage_or_skip() -> Path:
    candidates = sorted(path for path in lib_g4c.STAGE_ROOT.glob("stage-*")
                        if (path / "manifest.json").is_file())
    if not candidates:
        pytest.skip("no built G4-C/D stage in this checkout")
    return candidates[-1]


def test_p01_frozen_bindings_are_signed_and_mutations_denied() -> None:
    document = e5_probe.probe_p01(stage_or_skip())
    assert document["status"] == "PASS", document["checks"]
    ids = {item["id"]: item["ok"] for item in document["checks"]}
    assert ids["synthetic_signature_accepted"] is True
    assert ids["signed_bindings_equal_frozen_bytes"] is True
    assert ids["changed_runtime_digest_reports_drift"] is True
    assert ids["changed_runtime_digest_denied"] is True


def test_p02_artefact_policy_and_tool_drift_are_denied_pre_dispatch() -> None:
    document = e5_probe.probe_p02(stage_or_skip())
    assert document["status"] == "PASS", document["checks"]
    for check_id in ("runtime_sha256_drift_denied", "lock_sha256_drift_denied",
                     "code_sha256_drift_denied", "merged_profile_sha256_drift_denied",
                     "plugin_sha256_drift_denied", "policy_route_change_denied",
                     "tool_schema_change_denied"):
        assert {item["id"]: item["ok"] for item in document["checks"]}[check_id] is True


def test_p04_captured_tool_schema_matches_allowlist_registry_unverified() -> None:
    document = e5_probe.probe_p04(stage_or_skip())
    assert document["status"] == "PASS", document["checks"]
    assert document["extra"]["registry_export_api"] == "UNVERIFIED"


def test_p05_scanner_positive_control_and_env_scrub(tmp_path: Path) -> None:
    argv = tmp_path / "argv-candidate.json"
    argv.write_text(json.dumps({"argv": ["podman", "run", "--network", "none",
                                         "--mount", "type=bind,src=/srv/x,dst=/x"]}))
    document = e5_probe.probe_p05(stage=tmp_path, candidate_argv=str(argv),
                                  watchdog=None)
    ids = {item["id"]: item["ok"] for item in document["checks"]}
    assert ids["scanner_detects_planted_sentinel"] is True
    assert ids["candidate_env_scrub_drops_secret"] is True
    assert ids["candidate_network_none"] is True


def test_d15_same_uid_known_path_is_denied_by_mode_not_name(tmp_path: Path) -> None:
    import os
    if os.geteuid() != 0:
        pytest.skip("same-UID probe requires host root to drop to 65534")
    document = e5_probe.probe_d15()
    assert document["status"] == "PASS", document["checks"]
    ids = {item["id"]: item["ok"] for item in document["checks"]}
    for check_id in ("denied_read_new_state", "denied_write_new_state",
                     "denied_list_new_state", "denied_read_old_state",
                     "denied_connect_socket", "candidate_own_session_writable"):
        assert ids[check_id] is True
    assert "P2-RUN-IDENTITY" in document["extra"]["residual"]
