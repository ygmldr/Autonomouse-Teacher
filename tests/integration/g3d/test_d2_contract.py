"""D2 contract tests (host-only; no container, no kernel claim).

These tests exercise the pure/D2 policy surface:

* the audited Candidate probe allow-list and Candidate-stage Python contract;
* the auxiliary container argv contract for D2-13 CONTROL / D2-14 stale Run /
  D2-12 stress, including the refusal to mount Trusted state read-write;
* the trusted fault-injection env is opt-in and validated;
* the case judge *logic* (pass and fail) on synthetic probe documents;
* the nested live/DB snapshot count parser and digest pair checks.

Real kernel/container evidence for D2-01..15 is produced by
``scripts/g3d/d2_runner.py`` under ``artifacts/g3d/d2/``; pytest passing here is
not a substitute for it.
"""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import sys

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
G3D_SCRIPTS = REPO_ROOT / "scripts" / "g3d"
if str(G3D_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(G3D_SCRIPTS))

import d2_runner  # noqa: E402
import lib_g3d as lib  # noqa: E402

RUN_DIR = "/run/g3d-d2-contract"


# ---------------------------------------------------------------------------
# Probe allow-list / stage contract
# ---------------------------------------------------------------------------
def test_probe_allowlist_matches_repository_files() -> None:
    probe_dir = REPO_ROOT / "scripts" / "g3d" / "probes"
    files = {path.name for path in probe_dir.glob("*.py")}
    assert files == set(lib.D2_PROBE_FILES)
    assert len(files) == 14
    for path in probe_dir.glob("*.py"):
        assert path.is_file() and not path.is_symlink()
        assert path.read_text(encoding="utf-8").startswith("#!/usr/bin/env python3")


def test_candidate_stage_allows_exactly_the_audited_probes() -> None:
    allowed = [f"run/probes/{name}" for name in sorted(lib.D2_PROBE_FILES)]
    assert lib.forbidden_candidate_reasons(allowed) == []
    assert lib.forbidden_candidate_reasons(["run/candidate_entry.py"]) == []
    for relative in ("run/probes/evil.py", "run/probes/../trusted_entry.py",
                     "run/broker.py"):
        assert lib.forbidden_candidate_reasons([relative]), relative


def test_probes_do_not_import_the_trusted_package() -> None:
    import ast

    for name in lib.D2_PROBE_FILES:
        source = (REPO_ROOT / "scripts" / "g3d" / "probes" / name).read_text(
            encoding="utf-8")
        tree = ast.parse(source)
        modules = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module)
        assert not [module for module in modules
                    if module.split(".")[0] == "autoteacher_m0"], (name, modules)


# ---------------------------------------------------------------------------
# Auxiliary argv contracts
# ---------------------------------------------------------------------------
def _aux(role: str, probe: str, **kwargs) -> list[str]:
    return lib.aux_run_argv(
        podman="podman", rootfs="/rootfs", stage_candidate="/stage",
        deps="/deps", run_dir=RUN_DIR, name=f"at-g3d-{role}-contract",
        role=role, probe=probe, probe_args=kwargs.pop("probe_args", ()),
        **kwargs)


def test_control_aux_argv_has_exact_read_only_state_mount() -> None:
    argv = _aux("control", "d2_13_dac_control.py")
    assert lib.aux_argv_contract_problems(
        argv, role="control", run_dir=RUN_DIR, stage_dir="/stage",
        probe="d2_13_dac_control.py") == []
    mounts = lib.argv_mounts(argv)
    expected = f"type=bind,src={Path(RUN_DIR) / 'state'},dst=/work/state,ro=true"
    assert mounts.count(expected) == 1
    assert "rw=true" not in expected


def test_stress_aux_argv_uses_frozen_lower_limits() -> None:
    argv = _aux("stress", "d2_12_stress.py", pids_limit=8, memory="128m")
    assert lib.aux_argv_contract_problems(
        argv, role="stress", run_dir=RUN_DIR, stage_dir="/stage",
        probe="d2_12_stress.py") == []
    assert argv[argv.index("--pids-limit") + 1] == "8"
    assert argv[argv.index("--memory") + 1] == "128m"
    assert not any("dst=/work/state" in mount for mount in lib.argv_mounts(argv))


def test_stale_aux_argv_mounts_only_the_stale_ipc_directory() -> None:
    argv = _aux("stale", "d2_14_stale_run.py")
    mounts = lib.argv_mounts(argv)
    expected = f"type=bind,src={Path(RUN_DIR) / 'stale-ipc'},dst=/work/g3b,ro=true"
    assert mounts.count(expected) == 1
    assert not any("dst=/work/state" in mount for mount in mounts)
    assert lib.aux_argv_contract_problems(
        argv, role="stale", run_dir=RUN_DIR, stage_dir="/stage",
        probe="d2_14_stale_run.py") == []


def test_aux_rejects_unlisted_probe() -> None:
    with pytest.raises(lib.G3DError):
        _aux("stress", "evil.py")


def test_aux_contract_rejects_state_write_and_extra_state_mounts() -> None:
    control = _aux("control", "d2_13_dac_control.py")
    tampered = [token.replace("dst=/work/state,ro=true", "dst=/work/state,rw=true")
                if isinstance(token, str) else token for token in control]
    assert lib.aux_argv_contract_problems(
        tampered, role="control", run_dir=RUN_DIR, stage_dir="/stage",
        probe="d2_13_dac_control.py")
    stress = _aux("stress", "d2_12_stress.py", pids_limit=8, memory="128m")
    injected = list(stress)
    index = injected.index("--mount")
    injected.insert(index + 1,
                    f"type=bind,src={Path(RUN_DIR) / 'state'},dst=/work/state,ro=true")
    assert "forbidden:stress_state_mount" in lib.aux_argv_contract_problems(
        injected, role="stress", run_dir=RUN_DIR, stage_dir="/stage",
        probe="d2_12_stress.py")


def test_aux_contract_rejects_privileged_and_wrong_uidmap() -> None:
    argv = _aux("control", "d2_13_dac_control.py")
    privileged = argv + ["--privileged"]
    assert any("forbidden:--privileged" in item for item in
               lib.aux_argv_contract_problems(
                   privileged, role="control", run_dir=RUN_DIR,
                   stage_dir="/stage", probe="d2_13_dac_control.py"))
    wrong = list(argv)
    wrong[wrong.index("0:65534:1")] = "0:0:1"
    assert any("missing:--uidmap 0:65534:1" in item for item in
               lib.aux_argv_contract_problems(
                   wrong, role="control", run_dir=RUN_DIR, stage_dir="/stage",
                   probe="d2_13_dac_control.py"))


# ---------------------------------------------------------------------------
# Trusted crash hook / candidate modes
# ---------------------------------------------------------------------------
def _trusted(**kwargs) -> list[str]:
    return lib.trusted_run_argv(
        podman="podman", rootfs="/rootfs", stage_trusted="/stage",
        deps="/deps", run_dir=RUN_DIR, name="at-g3d-trusted-contract",
        **kwargs)


def test_trusted_crash_hook_is_opt_in_and_validated() -> None:
    base = _trusted()
    assert not any("G3B_TEST_MODE" in token for token in base)
    hooked = _trusted(crash_hook="after_attempt_start_before_fake_send")
    assert hooked[hooked.index("G3B_TEST_MODE=1") - 0] == "G3B_TEST_MODE=1"
    assert "G3B_CRASH_HOOK=after_attempt_start_before_fake_send" in hooked
    with pytest.raises(lib.G3DError):
        _trusted(crash_hook="arbitrary_hook")


def test_candidate_hold_and_resume_argv_contract() -> None:
    hold = lib.candidate_run_argv(
        podman="podman", rootfs="/rootfs", stage_candidate="/stage",
        deps="/deps", run_dir=RUN_DIR, name="at-g3d-candidate-hold",
        mode="hold", label="hold", hold_seconds=900)
    assert hold[hold.index("--mode") + 1] == "hold"
    assert hold[hold.index("--hold-seconds") + 1] == "900"
    assert "--scenario" not in hold
    assert lib.argv_contract_problems(
        hold, role="candidate", run_dir=RUN_DIR, stage_dir="/stage") == []
    resume = lib.candidate_run_argv(
        podman="podman", rootfs="/rootfs", stage_candidate="/stage",
        deps="/deps", run_dir=RUN_DIR, name="at-g3d-candidate-resume",
        scenario="resume", session="s", prompt="p", label="turn2")
    assert resume[resume.index("--scenario") + 1] == "resume"
    assert resume[resume.index("--label") + 1] == "turn2"
    assert lib.argv_contract_problems(
        resume, role="candidate", run_dir=RUN_DIR, stage_dir="/stage") == []


def test_case_registry_has_every_judge_and_probe_pair() -> None:
    for case in d2_runner.CASES:
        key = case.replace("-", "_")
        if key == "d2_10_trusted_receipt":
            key = "d2_10_trusted"
        assert hasattr(d2_runner.D2Runner, "_judge_" + key), case
    for case, spec in d2_runner.CASES.items():
        for probe in spec.get("probes", []):
            assert probe["file"] in lib.D2_PROBE_FILES
        for aux in spec.get("aux", []):
            assert aux["file"] in lib.D2_PROBE_FILES
            assert aux["role"] in lib.AUX_ROLES


# ---------------------------------------------------------------------------
# Snapshot count parser / judge logic
# ---------------------------------------------------------------------------
def _snapshot(*, reservations: int = 0, claims: int = 0, attempts: int = 0,
              admissions: int = 0, receipts: int = 0,
              counter: dict | None = None, data_digest: str = "d") -> dict:
    return {
        "data_digest": data_digest,
        "files": [{"path": "broker.sqlite3", "sha256": "broker-" + data_digest}],
        "db": {
            "broker": {"rows": {
                "reservations": [{"reservation_id": f"r{i}"}
                                 for i in range(reservations)],
                "claims": [{"call_id": f"c{i}"} for i in range(claims)],
            }},
            "attempts": {"rows": {
                "attempts": [{"attempt_id": f"a{i}"} for i in range(attempts)],
                "admissions": [{"admission_id": f"ad{i}"}
                               for i in range(admissions)],
            }},
        },
        "receipts": {"count": receipts, "counter": counter, "receipts": []},
    }


def _fake_runner(**attributes):
    runner = d2_runner.D2Runner.__new__(d2_runner.D2Runner)
    runner.case_key = attributes.pop("case_key", "d2-01")
    runner.spec = attributes.pop("spec", {})
    runner.probes = attributes.pop("probes", {})
    runner.probe_records = attributes.pop("probe_records", {})
    runner.snapshots = attributes.pop("snapshots", {})
    runner.records = attributes.pop("records", {})
    runner.candidate_runs = attributes.pop("candidate_runs", [])
    runner.aux_records = attributes.pop("aux_records", [])
    for name, value in attributes.items():
        setattr(runner, name, value)
    return runner


def test_snapshot_counts_understand_nested_live_documents() -> None:
    counts = d2_runner.D2Runner._snapshot_counts(
        _snapshot(reservations=1, claims=1, attempts=1, admissions=1,
                  receipts=1, counter={"count": 1}))
    assert counts["reservations"] == counts["claims"] == 1
    assert counts["attempts"] == counts["admissions"] == 1
    assert counts["receipts"] == 1
    assert counts["counter"] == {"count": 1}


def _d2_01_document(*, visible: bool = False) -> dict:
    ops = []
    for path in ("/work/state/broker.sqlite3", "/work/state/broker.sqlite3-wal",
                 "/work/state/broker.sqlite3-shm", "/state/broker.sqlite3",
                 "/output/broker.sqlite3", "/work/state",
                 "/work/state/receipts"):
        ops.append({"id": "open_rdonly:" + path,
                    "ok": visible, "errno": None if visible else 2,
                    "errno_name": None if visible else "ENOENT"})
    ops.extend([
        {"id": "listdir:/work/state", "ok": False, "errno": 2},
        {"id": "listdir:/work", "ok": True, "result": ["g3b", "session"]},
        {"id": "stat:/work/state", "ok": False, "errno": 2},
    ])
    return {"probe": "d2-01", "ops": ops, "state_mounts": [],
            "protected_name_search": {"name_matches": [],
                                      "entries_visited": 10}}


def test_judge_d2_01_passes_expected_document() -> None:
    runner = _fake_runner(
        probes={"d2_01": _d2_01_document()},
        probe_records={"d2_01": {"exit": 0, "expect_exit": 0}},
        snapshots={"pre": _snapshot(data_digest="same"),
                   "final": _snapshot(data_digest="same")})
    checks = d2_runner.CaseChecks("d2-01")
    runner._judge_d2_01(checks)
    assert checks.failures == [], checks.failures


def test_judge_d2_01_rejects_visible_or_mutated_state() -> None:
    document = _d2_01_document(visible=True)
    runner = _fake_runner(
        probes={"d2_01": document},
        probe_records={"d2_01": {"exit": 0, "expect_exit": 0}},
        snapshots={"pre": _snapshot(data_digest="aaa"),
                   "final": _snapshot(data_digest="bbb")})
    checks = d2_runner.CaseChecks("d2-01")
    runner._judge_d2_01(checks)
    assert "d2_01:open_rdonly:/work/state/broker.sqlite3" in checks.failures
    assert "state_hash_unchanged:pre->final" in checks.failures
    assert "broker_db_hash_unchanged:pre->final" in checks.failures


def _d2_05_documents() -> tuple[dict, dict]:
    negatives = {
        "probe": "d2-05", "phase": "negatives",
        "ops": [{"id": f"connect_broker:{path}", "ok": False, "errno": 2,
                 "errno_name": "ENOENT"} for path in (
                     "/work/g3b/broker.sock", "/work/g3b/controller.sock",
                     "/work/private/controller.sock", "/work/state/broker.sock")],
        "negatives": [
            {"id": "broker_kind_reserve", "error_code": "UNKNOWN_KIND"},
            {"id": "broker_kind_claim", "error_code": "UNKNOWN_KIND"},
            {"id": "broker_kind_settle", "error_code": "UNKNOWN_KIND"},
            {"id": "payload_reservation_id", "error_code": "UNKNOWN_FIELD"},
            {"id": "payload_claim_id", "error_code": "UNKNOWN_FIELD"},
            {"id": "payload_authorized", "error_code": "UNKNOWN_FIELD"},
            {"id": "payload_dispatch_allowed", "error_code": "UNKNOWN_FIELD"},
            {"id": "envelope_dispatch_allowed", "error_code": "UNKNOWN_FIELD"},
        ],
        "socket_unlink": {"id": "unlink_bridge", "ok": False, "errno": 30},
    }
    positive = {"probe": "d2-05", "phase": "positive",
                "positive": {"terminal": "finish", "error_code": None,
                             "frames": [{"kind": "ack"}, {"kind": "chunk"},
                                        {"kind": "finish"}]}}
    return negatives, positive


def test_judge_d2_05_accepts_expected_negative_and_positive() -> None:
    negatives, positive = _d2_05_documents()
    runner = _fake_runner(
        case_key="d2-05",
        probes={"d2_05_negatives": negatives, "d2_05_positive": positive},
        probe_records={"d2_05_negatives": {"exit": 0, "expect_exit": 0},
                       "d2_05_positive": {"exit": 0, "expect_exit": 0}},
        snapshots={"negatives": _snapshot(data_digest="n0"),
                   "positive": _snapshot(reservations=1, claims=1, attempts=1,
                                         receipts=1, counter={"count": 1},
                                         data_digest="n1")})
    checks = d2_runner.CaseChecks("d2-05")
    runner._judge_d2_05(checks)
    assert checks.failures == [], checks.failures


def test_judge_d2_05_detects_wrong_protocol_code() -> None:
    negatives, positive = _d2_05_documents()
    negatives["negatives"][0]["error_code"] = "UNKNOWN_FIELD"
    runner = _fake_runner(
        case_key="d2-05",
        probes={"d2_05_negatives": negatives, "d2_05_positive": positive},
        probe_records={"d2_05_negatives": {"exit": 0, "expect_exit": 0},
                       "d2_05_positive": {"exit": 0, "expect_exit": 0}},
        snapshots={"negatives": _snapshot(data_digest="n0"),
                   "positive": _snapshot(reservations=1, claims=1, attempts=1,
                                         receipts=1, counter={"count": 1},
                                         data_digest="n1")})
    checks = d2_runner.CaseChecks("d2-05")
    runner._judge_d2_05(checks)
    assert "d2_05_negatives:neg:broker_kind_reserve" in checks.failures


def test_digest_checks_require_both_pairs_and_do_not_merge_them() -> None:
    ledger = {
        "attempts": [{"attempt_id": "a1", "call_id": "c1",
                      "receipt_id": "r1",
                      "prepared_digest": "a" * 64,
                      "payload_digest": "b" * 64}],
        "claims": [{"call_id": "c1", "request_digest": "a" * 64}],
    }
    receipts = [{"receipt_id": "r1", "raw_sha256": "b" * 64}]
    checks = d2_runner.CaseChecks("d2-15")
    runner = _fake_runner(case_key="d2-15")
    runner._digest_checks(checks, ledger, receipts, prefix="d2_15")
    assert checks.failures == [], checks.failures
    merged = json.loads(json.dumps(ledger))
    merged["attempts"][0]["prepared_digest"] = "b" * 64
    checks2 = d2_runner.CaseChecks("d2-15")
    runner._digest_checks(checks2, merged, receipts, prefix="d2_15")
    assert "d2_15:prepared_digest_equals_claim" in checks2.failures
    assert "d2_15:two_pairs_not_merged" in checks2.failures


def test_final_ledger_reads_the_copied_databases(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence"
    (evidence / "db").mkdir(parents=True)
    (evidence / "receipt").mkdir(parents=True)
    broker = evidence / "db" / "broker.sqlite3"
    connection = sqlite3.connect(broker)
    connection.executescript(
        "CREATE TABLE budget_reservations (reservation_id TEXT, route_id TEXT,"
        " model TEXT, status TEXT, input_used INT, output_used INT, cost TEXT,"
        " estimated INT, settlement_json TEXT);"
        "CREATE TABLE budget_dispatch_claims (call_id TEXT, reservation_id TEXT,"
        " request_digest TEXT, status TEXT);")
    connection.execute("INSERT INTO budget_reservations VALUES "
                       "('r1','route','model','OK',1,1,'0.001',0,'{}')")
    connection.execute("INSERT INTO budget_dispatch_claims VALUES "
                       "('c1','r1','" + "a" * 64 + "','COMPLETED')")
    connection.commit()
    connection.close()
    attempts = evidence / "db" / "attempts.sqlite3"
    connection = sqlite3.connect(attempts)
    connection.executescript(
        "CREATE TABLE g3b_attempts (attempt_id TEXT, call_id TEXT,"
        " reservation_id TEXT, state TEXT, receipt_id TEXT, reason TEXT,"
        " prepared_digest TEXT, payload_digest TEXT, run_id TEXT,"
        " logical_step INT, mode TEXT, input_bound_tokens INT,"
        " settlement_json TEXT, created_utc TEXT);"
        "CREATE TABLE g3b_admissions (admission_id TEXT, run_id TEXT,"
        " consumed_utc TEXT);")
    connection.execute("INSERT INTO g3b_attempts VALUES "
                       "('a1','c1','r1','SETTLED','rcpt-1',NULL,'" + "a" * 64 +
                       "','" + "b" * 64 + "','run',0,'ok_usage',10,'{}','now')")
    connection.execute("INSERT INTO g3b_admissions VALUES ('ad1','run','now')")
    connection.commit()
    connection.close()
    (evidence / "receipt" / "rcpt-1.json").write_text(
        json.dumps({"receipt_id": "rcpt-1", "raw_sha256": "b" * 64,
                    "usage": {"inputTokens": 1, "outputTokens": 1},
                    "nonce": "0" * 32}), encoding="utf-8")
    (evidence / "receipt" / "received-count.json").write_text(
        json.dumps({"count": 1}), encoding="utf-8")
    runner = _fake_runner(case_key="d2-15")
    runner.evidence = evidence
    ledger = runner._final_ledger()
    assert len(ledger["reservations"]) == 1
    assert len(ledger["claims"]) == 1
    assert len(ledger["attempts"]) == 1
    assert len(ledger["admissions"]) == 1
    assert len(ledger["receipts"]) == 1
    assert ledger["counter"] == {"count": 1}
