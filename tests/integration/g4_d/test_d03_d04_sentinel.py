"""D03/D04/E5-P05: the sentinel scanner must be sensitive and byte-exact."""
from __future__ import annotations

import json
from pathlib import Path


import secret_sentinel_probe as probe
import e5_probe


def test_scanner_detects_the_exact_bytes_and_reports_clean_roots(
        tmp_path: Path) -> None:
    clean = tmp_path / "clean"
    clean.mkdir()
    (clean / "receipt.json").write_text(json.dumps({"status": "OK"}) + "\n")
    (clean / "junit.xml").write_text("<testsuite tests='1'/>\n")
    record = probe.scan_roots([str(clean)])
    assert record["clean"] is True and record["hit_count"] == 0
    assert record["files_scanned"] == 2

    leak = clean / "broker.log"
    leak.write_text(f"credential={probe.SENTINEL}\n")
    record = probe.scan_roots([str(clean)])
    assert record["clean"] is False
    assert record["hit_count"] == 1
    assert record["hits"][0]["path"] == str(leak)
    assert probe.SENTINEL not in json.dumps(record["hits"])  # never echo bytes


def test_scanner_does_not_silently_ignore_a_missing_root(tmp_path: Path) -> None:
    missing = tmp_path / "gone"
    record = probe.scan_roots([str(missing)])
    assert record["clean"] is False
    assert record["missing_roots"] == [str(missing)]


def test_proc_surface_capture_records_names_not_values(tmp_path: Path) -> None:
    record = probe.scan_proc(__import__("os").getpid())
    assert record["surfaces"]["environ"]["present"] is True
    assert record["surfaces"]["cmdline"]["sentinel_count"] == 0
    assert isinstance(record["surfaces"]["environ"]["entries"], list)


def test_candidate_env_scrub_removes_the_sentinel_value() -> None:
    scrubbed, violations = _scrub()
    assert scrubbed == {"PATH": "/usr/bin", "HOME": "/work"}
    assert any("DEEPSEEK_API_KEY" in item for item in violations)
    assert probe.SENTINEL not in json.dumps(scrubbed)


def _scrub():
    from autoteacher_m0.security.credential_boundary import scrub_candidate_env
    return scrub_candidate_env(
        {"PATH": "/usr/bin", "HOME": "/work",
         "DEEPSEEK_API_KEY": probe.SENTINEL,
         "OPENCODE_API_KEY": probe.SENTINEL},
        known_secret_values=[probe.SENTINEL])


def test_candidate_argv_mounts_and_env_never_reference_the_fixture(
        tmp_path: Path) -> None:
    argv = {
        "argv": ["podman", "run", "--network", "none",
                 "--mount", "type=bind,src=/srv/candidate,dst=/project,ro=true",
                 "--mount", "type=bind,src=/srv/deps,dst=/deps,ro=true",
                 "--env", "PATH=/opt/python/bin:/usr/bin",
                 "--env", "PYTHONPATH=/deps"],
        "env": ["PATH=/opt/python/bin:/usr/bin", "PYTHONPATH=/deps"],
    }
    path = tmp_path / "argv-candidate.json"
    path.write_text(json.dumps(argv), encoding="utf-8")
    document = e5_probe.probe_p05(
        stage=tmp_path, candidate_argv=str(path), watchdog=None)
    assert document["status"] == "FAIL"  # no watchdog evidence supplied
    ids = {item["id"]: item["ok"] for item in document["checks"]}
    assert ids["candidate_argv_has_no_sentinel"] is True
    assert ids["candidate_mounts_exclude_trusted_fixture"] is True
    assert ids["candidate_network_none"] is True
    assert ids["watchdog_cleanup_confirmed"] is False
