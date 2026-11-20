"""B5 unified end-to-end tests (B-PR5 integration, TEST_EVIDENCE_MATRIX B4/B5).

Coverage map:

* **B4-01** — two synthetic CF learners through the canonical closed loop, one
  SQLite learner/event journal, different paths, evidence-driven mastery.
* **B4-02** — two synthetic interview learners with different learner states;
  five-stage Socratic ladder (accelerated learner skips the concept probe),
  ``ASK_CLARIFICATION`` for missing project facts, four-dimension rubric,
  ``FULL`` never emitted, and a JD ``v1 -> v2`` transition that only affects
  new plans.
* **B4-03** — EXPIRED / CONFLICT / UNAUTHORITATIVE knowledge and expired /
  conflicting / not-yet-active JD windows rejected before any write (zero
  events), eligible updates allowed into new plans.
* **Cross-domain** — same learner pauses CF -> interview session -> resumes CF;
  one unified event table/seq, replay verified.
* **B5-01 support** — deterministic evidence JSONL/summary (byte-identical
  double runs), fixed artifact manifest, MOCK/DETERMINISTIC/NOT_VERIFIED
  classification, no wall clock/git/hidden leakage, offline stdlib-only module.

All outcomes are synthetic (``MOCK``); state machine/ids/replay are
``DETERMINISTIC``; real teaching effect is ``NOT_VERIFIED``.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from m1_teacher import e2e_b5

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_ROOT = REPO_ROOT / "fixtures" / "m1_teacher"
PYTHON = sys.executable
EVIDENCE_NAMES = (
    "e2e_b5_cf.jsonl",
    "e2e_b5_cross_domain.jsonl",
    "e2e_b5_freshness.jsonl",
    "e2e_b5_interview.jsonl",
    "e2e_b5_summary.json",
)


@pytest.fixture(scope="module")
def scenario() -> dict:
    return e2e_b5.run_scenario()


def _public_json(value: dict) -> str:
    return json.dumps(e2e_b5._public(value), ensure_ascii=False, sort_keys=True)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [PYTHON, "-m", "m1_teacher.e2e_b5", *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=300,
        env={**os.environ},
    )


# ---------------------------------------------------------------------------
# B4-01: CF learners / shared canonical journal
# ---------------------------------------------------------------------------
def test_b5_cf_two_learners_share_journal_and_differ(scenario: dict) -> None:
    cf = scenario["cf"]
    assert len(cf["learners"]) == 2
    learner_a, learner_b = cf["learners"]
    assert learner_a["student_fixture"] == "student_a"
    assert learner_b["student_fixture"] == "student_b"
    assert learner_a["learner_id"] != learner_b["learner_id"]
    assert learner_a["session_id"] != learner_b["session_id"]
    assert cf["paths_differ"] is True
    assert learner_a["first_action"] != learner_b["first_action"]
    assert learner_a["mastery_after"] != learner_b["mastery_after"]
    # Evidence-driven mastery: only the learner with observed CORRECT answers rises.
    assert learner_a["assessment_status_counts"].get("CORRECT", 0) >= 1
    assert learner_a["mastery_after"]["cf.search.binary"] > 0.0
    assert learner_b["mastery_after"]["cf.search.binary"] == 0.0
    for learner in cf["learners"]:
        assert learner["verify_rebuild"] is True
        assert learner["event_count"] > 0


def test_b5_unified_journal_replay_and_seq(scenario: dict) -> None:
    journal = scenario["unified_journal"]
    assert journal["one_sqlite_file"] is True
    assert journal["all_verify_rebuild"] is True
    learners = journal["learners"]
    assert len(learners) == 5  # 2 CF + 2 interview + 1 cross-domain learner
    required_types = {
        "SESSION_STARTED",
        "PLAN_CREATED",
        "ACTION_TAKEN",
        "RESPONSE_SUBMITTED",
        "ASSESSED",
        "MASTERY_UPDATED",
    }
    for learner in learners:
        assert learner["seq_contiguous"] is True
        assert learner["verify_rebuild"] is True
        assert required_types <= set(learner["event_types"]), learner["learner_id"]
        assert learner["session_count"] >= 1


# ---------------------------------------------------------------------------
# B4-02: interview learners / five stages / rubric / JD transition
# ---------------------------------------------------------------------------
def test_b5_interview_two_learners_and_five_stage_ladder(scenario: dict) -> None:
    interview = scenario["interview"]
    assert len(interview["learners"]) == 2
    seeded, novice = interview["learners"]
    assert seeded["learner_id"] == e2e_b5.INTERVIEW_LEARNER_A
    assert novice["learner_id"] == e2e_b5.INTERVIEW_LEARNER_B
    assert seeded["sessions"] and novice["sessions"]

    seeded_v1 = seeded["sessions"][0]
    novice_session = novice["sessions"][0]
    # Accelerated learner (3 seeded CORRECT observations) skips the concept probe.
    assert [e2e_b5._probe_stage(reason) for reason in seeded_v1["probe_sequence"]] == [
        "hypothesis",
        "complexity",
        "experiment_design",
        "online_triage",
    ]
    assert seeded_v1["hint_levels"] == []
    # Novice learner walks the complete five-stage ladder and gets clarification.
    assert [e2e_b5._probe_stage(reason) for reason in novice_session["probe_sequence"]] == [
        "concept",
        "hypothesis",
        "complexity",
        "experiment_design",
        "online_triage",
    ]
    assert novice_session["clarification_count"] >= 1
    assert novice_session["hint_levels"] and max(novice_session["hint_levels"]) <= 3
    # Four-dimension rubric audit is always present; FULL support never emitted.
    for learner in (seeded, novice):
        for session in learner["sessions"]:
            assert session["rubric_audit_dimensions"] == [
                "engineering_feasibility",
                "evidence_sufficiency",
                "explanation_clarity",
                "factual_correctness",
            ]
            assert session["rubric_spec_digests"] >= 1
    assert interview["full_solution_emitted"] is False
    assert interview["paths_differ"] is True


def test_b5_jd_v1_to_v2_affects_new_plans_only(scenario: dict) -> None:
    interview = scenario["interview"]
    change = interview["jd_change"]
    assert interview["jd_versions"] == ["v1", "v2", "v2"]
    assert change["old_version"] == "v1"
    assert change["new_version"] == "v2"
    assert change["affects_running_sessions"] is False
    assert change["affects_new_plans"] is True
    assert change["reason_code"] == "JD_CHANGE_NEW_PLANS_ONLY"
    assert change["old_session_before"] == change["old_session_after"]
    old = change["old_session_before"]
    new = change["new_session"]
    assert old["journal_sha256"] == change["old_session_after"]["journal_sha256"]
    assert old["phase"] == change["old_session_after"]["phase"]
    assert new["journal_sha256"] != old["journal_sha256"]
    seeded = interview["learners"][0]
    assert [session["jd_version"] for session in seeded["sessions"]] == ["v1", "v2"]


# ---------------------------------------------------------------------------
# Cross-domain continuity
# ---------------------------------------------------------------------------
def test_b5_cross_domain_pause_interview_resume(scenario: dict) -> None:
    cross = scenario["cross_domain"]
    assert cross["cf_session_id"] != cross["interview_session_id"]
    assert cross["session_count"] == 2
    assert cross["pause_turn"] >= 1
    assert cross["resumed_phase"] != "PAUSED"
    assert cross["seq_contiguous"] is True
    assert cross["unified_domains"] == ["cf_binary_search", "interview_coach"]
    assert cross["verify_rebuild"] is True
    assert cross["interview_jd_version"] == "v2"
    assert cross["interview_clarifications"] >= 1
    # Starting the interview session does not itself mutate the CF snapshot
    # (only subsequent assessments can add evidence); the final snapshot carries
    # both CF and interview nodes in the same canonical snapshot.
    assert cross["snapshot_before_pause"]["revision"] >= 0
    assert (
        cross["snapshot_after_interview"]["revision"] >= cross["snapshot_before_pause"]["revision"]
    )
    final_nodes = set(cross["snapshot_final"]["masteries"])
    assert any(node.startswith("cf.") for node in final_nodes)
    assert any(node.startswith("interview.") for node in final_nodes)


# ---------------------------------------------------------------------------
# B4-03: freshness gates
# ---------------------------------------------------------------------------
def test_b5_freshness_gates_reject_before_write(scenario: dict) -> None:
    freshness = scenario["freshness"]
    assert freshness["decision_counts"] == {"KEEP": 2, "RECHECK": 5, "UPDATE": 2}
    assert len(freshness["blocked_knowledge"]) == 5
    assert len(freshness["blocked_jd"]) == 3
    assert len(freshness["eligible_updates"]) == 2
    knowledge_reasons = {record["reason_code"] for record in freshness["blocked_knowledge"]}
    assert {
        "RECHECK_EXPIRED",
        "RECHECK_CONFLICT",
        "RECHECK_UNAUTHORITATIVE_SOURCE",
    } <= knowledge_reasons
    for record in freshness["blocked_knowledge"]:
        assert record["rejected"] is True
        assert record["events_written"] == 0
        assert record["error_code"] == "FRESHNESS_KNOWLEDGE_GATE_BLOCKED"
    jd_reasons = {record["reason_code"] for record in freshness["blocked_jd"]}
    assert {
        "RECHECK_JD_EXPIRED",
        "RECHECK_JD_NOT_YET_ACTIVE",
        "RECHECK_JD_CONFLICT",
    } <= jd_reasons
    for record in freshness["blocked_jd"]:
        assert record["rejected"] is True
        assert record["events_written"] == 0
        assert record["error_code"] == "FRESHNESS_JD_GATE_BLOCKED"
        assert record["map_code"] == "MAP-E10_JD_EXPIRED_OR_CONFLICT"
    for record in freshness["eligible_updates"]:
        assert record["change_kind"] == "UPDATE"
        assert record["events_written"] > 0
    assert freshness["silent_imports"] == 0
    assert freshness["gate_enforced"] is True


# ---------------------------------------------------------------------------
# B5-01: deterministic evidence / classification / boundary
# ---------------------------------------------------------------------------
def test_b5_summary_is_deterministic_and_classified(scenario: dict) -> None:
    other = e2e_b5.run_scenario()
    assert _public_json(scenario) == _public_json(other)
    manifest = scenario["artifact_manifest"]
    assert manifest["manifest_version"] == e2e_b5.ARTIFACT_MANIFEST_VERSION
    assert manifest["generated_at"] == e2e_b5.FIXED_TIMESTAMP
    assert manifest["base_sha"] == e2e_b5.BASE_SHA
    assert manifest["implementation_commit"] == e2e_b5.IMPLEMENTATION_COMMIT
    assert "generated_at_utc_date" not in scenario
    assert "base_commit" not in scenario
    assert scenario["fixed_timestamp"] == e2e_b5.FIXED_TIMESTAMP
    assert scenario["boundary"]["scope"] == "offline synthetic only, not real teaching effect"
    assert scenario["classification"]["MOCK"]
    assert scenario["classification"]["DETERMINISTIC"]
    assert scenario["classification"]["NOT_VERIFIED"]


def test_b5_evidence_files_are_reproducible(tmp_path: Path) -> None:
    first_scenario = e2e_b5.run_scenario()
    second_scenario = e2e_b5.run_scenario()
    first_dir = tmp_path / "evidence_one"
    second_dir = tmp_path / "evidence_two"
    first = e2e_b5.write_evidence(first_scenario, first_dir)
    second = e2e_b5.write_evidence(second_scenario, second_dir)
    assert first["hashes"] == second["hashes"]
    for name in EVIDENCE_NAMES:
        assert (first_dir / name).read_bytes() == (second_dir / name).read_bytes(), name
    for name in EVIDENCE_NAMES[:-1]:
        assert first["hashes"][name] == _sha256(first_dir / name)
    summary = json.loads((first_dir / "e2e_b5_summary.json").read_text(encoding="utf-8"))
    assert summary["artifact_manifest"] == first_scenario["artifact_manifest"]
    assert summary["evidence_files"] == sorted(EVIDENCE_NAMES[:-1])
    assert summary["evidence_hashes"] == first["hashes"]
    assert summary["schema"] == e2e_b5.B5_SCHEMA


def test_b5_evidence_records_are_classified_and_wall_clock_free(tmp_path: Path) -> None:
    scenario = e2e_b5.run_scenario()
    out = tmp_path / "evidence"
    e2e_b5.write_evidence(scenario, out)
    for name in EVIDENCE_NAMES[:-1]:
        lines = (out / name).read_text(encoding="utf-8").splitlines()
        assert lines
        for line in lines:
            record = json.loads(line)
            assert record["schema"] == e2e_b5.EVIDENCE_SCHEMA
            assert "MOCK" in record["evidence_classes"]
            assert "DETERMINISTIC" in record["evidence_classes"]
            rendered = json.dumps(record, ensure_ascii=False)
            # No hidden scoring material or learner response text in evidence.
            for forbidden in ("scoring/", "correct_option", "expected", "reference_answers"):
                assert forbidden not in rendered.lower(), (name, forbidden)
            assert "大概加一些缓存" not in rendered
    summary_text = (out / "e2e_b5_summary.json").read_text(encoding="utf-8")
    assert "offline synthetic only, not real teaching effect" in summary_text
    assert "NOT_VERIFIED" in summary_text
    assert '"_evidence"' not in summary_text


def test_b5_cli_double_run_is_byte_identical(tmp_path: Path) -> None:
    first = run_cli("--write-evidence", str(tmp_path / "one"))
    second = run_cli("--write-evidence", str(tmp_path / "two"))
    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert first.stdout == second.stdout
    for name in EVIDENCE_NAMES:
        assert (tmp_path / "one" / name).read_bytes() == (tmp_path / "two" / name).read_bytes(), (
            name
        )
    plain_one = run_cli()
    plain_two = run_cli()
    assert plain_one.returncode == 0 and plain_two.returncode == 0
    assert plain_one.stdout == plain_two.stdout
    assert "offline synthetic only, not real teaching effect" in plain_one.stdout
    assert "MOCK" in plain_one.stdout and "DETERMINISTIC" in plain_one.stdout


def test_b5_module_is_offline_stdlib_only() -> None:
    source = Path(e2e_b5.__file__).read_text(encoding="utf-8")
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
    assert not (imported_roots & forbidden)
    assert "autoteacher_m0" not in source
    assert "shell=True" not in source
    # The runtime works with sockets blocked at interpreter start-up.
    no_net = REPO_ROOT / "tests" / "m1_teacher" / "_b5_no_net"
    no_net.mkdir(exist_ok=True)
    try:
        (no_net / "sitecustomize.py").write_text(
            "import socket\n"
            "def _deny(*args, **kwargs):\n"
            "    raise OSError('M1B_NO_NETWORK')\n"
            "socket.socket = _deny\n"
            "socket.create_connection = _deny\n"
            "socket.getaddrinfo = _deny\n",
            encoding="utf-8",
        )
        env = {**os.environ, "PYTHONPATH": str(no_net)}
        completed = subprocess.run(
            [
                PYTHON,
                "-c",
                "from m1_teacher import e2e_b5; print(e2e_b5.run_scenario()['schema'])",
            ],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=300,
            env=env,
        )
        assert completed.returncode == 0, completed.stderr
        assert completed.stdout.strip() == e2e_b5.B5_SCHEMA
    finally:
        import shutil

        shutil.rmtree(no_net, ignore_errors=True)
