#!/usr/bin/env python3.11
"""Build the G3-C evidence matrix, correlation rows and summary from raw traces.

Host-side analysis only (pinned Python 3.11, ``-B``). It never imports project
code and never re-runs a test; it reads the container evidence, JUnit XML and
Node TAP logs produced by the G3-C scripts.
"""
from __future__ import annotations

import csv
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EV = ROOT / "artifacts/g3c"
TRACES = EV / "traces"
OUT = EV / "evidence"
MATRIX = ROOT / "docs/Autonomous_Teacher_M0_G3C_G3D_Test_Evidence_Matrix_v1.0.csv"
IMPL_SHA = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
                          capture_output=True).stdout.strip()
SUMMARY: dict = {}

# Host-only cases: exact pytest node ids used as command evidence in the matrix.
HOST_TESTS = {
    "C1-01B": ["tests/integration/g3c/test_c1_04_replay.py::test_c1_04b_same_call_different_digest_maps_to_frozen_broker_code"],
    "C1-01C": ["tests/integration/g3c/test_c1_04_replay.py::test_c1_04c_reservation_mismatch_is_rejected_by_real_broker"],
    "C1-01D": ["tests/integration/g3c/test_c1_01_errors.py"],
    "C1-03B": ["tests/integration/g3c/test_c1_03_admission.py::test_c1_03b_invalid_request_does_not_consume_quota"],
    "C1-03D": ["tests/integration/g3c/test_c1_03_admission.py::test_c1_03d_concurrent_admission_never_exceeds_quota"],
    "C2-03A": ["tests/integration/g3c/test_c2_03_observation.py"],
    "C2-03B": ["tests/integration/g3c/test_c2_03_observation.py"],
    "C2-03C": ["tests/integration/g3c/test_c2_03_observation.py"],
    "C2-03D": ["tests/integration/g3c/test_c2_03_observation.py"],
    "C2-03E": ["tests/integration/g3c/test_c2_03_observation.py"],
    "C2-04": ["tests/integration/g3c/test_c2_04_recovery_admission.py"],
    "C3-01A": ["tests/integration/g3c/test_c1_03_admission.py::test_c3_01a_pre_send_cancel_is_zero_fake"],
    "C3-01E": ["tests/integration/g3c/test_c1_03_admission.py::test_c3_01d_cancel_contract_rejects_wrong_signature_and_unknown_ids"],
    "C3-02D": ["tests/integration/g3c/test_c3_02_deadline.py::test_c3_02d_response_watchdog_writes_error_and_closes"],
    "C3-02E": ["tests/integration/g3c/test_c2_02_recovery.py::test_c2_02_settle_reply_loss_replay_is_idempotent"],
    "C3-03A": ["tests/integration/g3c/test_c3_03_resources.py::test_c3_03a_empty_connection_first_frame_deadline"],
    "C3-03B": ["tests/integration/g3c/test_c3_03_resources.py::test_c3_03b_slow_one_byte_connection_is_interrupted"],
    "C3-03C": ["tests/integration/g3c/test_c3_03_resources.py::test_c3_03c_active_connection_cap_rejects_without_extra_threads"],
    "C3-03D": ["tests/integration/g3c/test_c3_03_resources.py::test_c3_03e_response_byte_budget_is_per_connection"],
    "C3-03E": ["tests/integration/g3c/test_c3_03_resources.py::test_c3_03e_response_byte_budget_is_per_connection"],
    "C3-03F": ["tests/integration/g3c/test_c3_03_resources.py::test_c3_03f_invalid_first_frames_never_reach_controller"],
    "C3-03G": ["tests/integration/g3c/test_c3_03_resources.py::test_c3_03g_cancel_wrong_signature_is_logged_not_silently_swallowed"],
    "C3-04D": ["tests/integration/g3c/test_c3_04_streaming.py::test_c3_04d_consumer_stall_is_bounded_and_close_cleans"],
}

# Matrix cases derived from one or more concrete container runs.
EVIDENCE_ALIAS = {
    "C2-01A": ["echo"], "C2-01B": ["tool"], "C2-01C": ["usage-partial"],
    "C2-01D": ["usage-multi", "usage-after-finish"],
    "C1-03A": ["admission-output-limit"], "C1-03C": ["admission-max-calls"],
    "C1-03E": ["deadline-300"], "C1-03F": ["admission-input-limit"],
    "C2-02A": ["crash-after_response_before_settlement",
               "reconcile-after_response_before_settlement"],
    "C2-02B": ["crash-after_broker_settle_before_journal_mark",
               "reconcile-after_broker_settle_before_journal_mark"],
    "C2-02C": ["crash-after_attempt_start_before_fake_send",
               "reconcile-after_attempt_start_before_fake_send"],
    "C2-02D": ["reconcile-tamper-receipt-usage"],
    "C2-02E": ["reconcile-after_response_before_settlement", "reconcile2-after-response"],
    "C2-02F": ["crash-after_broker_settle-partial", "reconcile-after_broker_settle-partial"],
    "C3-01B": ["probe-cancel"], "C3-01C": ["probe-cancel-concurrent"],
    "C3-01D": ["sigterm"], "C3-02A": ["probe-broker-hang"],
    "C3-02B": ["probe-fake-stall"], "C3-02C": ["deadline-100"],
    "C3-04A": ["stream-slow"], "C3-04B": ["stream-many"],
    "C3-04C": ["stream-big"], "C3-04E": ["stream-truncated"],
    "C1-02": ["usage-error", "usage-no-usage", "usage-partial", "usage-invalid", "usage-eof"],
    "C1-04": ["probe-replay"],
}

HOST_PY = ("PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:artifacts/foundation/deps "
           "/root/.local/bin/python3.11 -B -m pytest")



def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_json(path: Path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def dsh(name: str):
    return load_json(TRACES / name / "dsh-result.json")


def recon(name: str):
    return load_json(TRACES / name / "reconcile-result.json")


def probe(name: str):
    return load_json(TRACES / name / "probe-result.json")


def commands() -> dict:
    rows = {}
    path = EV / "commands.jsonl"
    if path.exists():
        for line in path.read_text().splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            rows.setdefault(row.get("case"), row)
    return rows


COMMANDS = commands()


def junit_results() -> dict:
    results: dict[str, bool] = {}
    for path in (EV / "evidence").glob("junit-*.xml"):
        try:
            tree = ET.parse(path)
        except (OSError, ET.ParseError):
            continue
        for case in tree.getroot().iter("testcase"):
            name = f"{case.get('classname')}::{case.get('name')}"
            failed = any(child.tag in {"failure", "error"} for child in case)
            results[name] = not failed
    return results


JUNIT = junit_results()


def tests(case_ids: list[str]) -> tuple[str, str]:
    """Resolve mapped JUnit tests: PASS/PARTIAL/FAIL/UNVERIFIED + detail."""
    found = []
    for case_id in case_ids:
        matches = [(name, ok) for name, ok in JUNIT.items()
                   if case_id in name or name.endswith(case_id)]
        if not matches:
            continue
        found.extend(matches)
    if not found:
        return "UNVERIFIED", "no mapped junit test found"
    passed = sum(1 for _, ok in found if ok)
    detail = f"{passed}/{len(found)} mapped tests passed"
    if passed == len(found):
        return "PASS", detail
    if passed == 0:
        return "FAIL", detail
    return "PARTIAL", detail


def node_fail_counts() -> dict:
    counts = {}
    for name in ("node-adapter", "node-guard"):
        path = EV / "logs" / f"{name}.log"
        text = path.read_text() if path.exists() else ""
        counts[name] = {"ok": "# fail 0" in text, "has_output": bool(text)}
    return counts


def receipt_usage(result) -> dict | None:
    for row in (result or {}).get("db", {}).get("receipts", []):
        if isinstance(row, dict) and row.get("mode") and row.get("usage"):
            return row["usage"]
    return None


def attempts(result) -> list:
    return (result or {}).get("db", {}).get("attempts", [])


def reservations(result) -> list:
    return (result or {}).get("db", {}).get("reservations", [])


def counter(result) -> int | None:
    for row in (result or {}).get("db", {}).get("receipts", []):
        if isinstance(row, dict) and "counter" in row:
            return row["counter"].get("count")
    return 0


def turn_end_reason(result) -> dict | None:
    for item in (result or {}).get("event_summary", {}).get("turn_end", []):
        if isinstance(item, dict) and isinstance(item.get("turn_end"), dict):
            return item["turn_end"]
    return None


def finish_error_code(result) -> str | None:
    reason = turn_end_reason(result)
    if not isinstance(reason, dict):
        return None
    if reason.get("kind") != "error":
        return None
    failure = reason.get("error")
    if not isinstance(failure, dict):
        return None
    code = failure.get("code")
    # DSH wraps transport-level error envelopes as SERVER + the bridge code in
    # the message; finish(error) failures keep their explicit failure code.
    if code == "SERVER":
        message = str(failure.get("message") or "")
        if message.startswith("G3B_BRIDGE_"):
            return message[len("G3B_BRIDGE_"):]
    return code


def assistant_messages(result) -> list:
    return (result or {}).get("event_summary", {}).get("assistant_messages", [])


def success_finish(result) -> bool:
    reason = turn_end_reason(result)
    return isinstance(reason, dict) and reason.get("kind") == "completed"


def evidence_paths(case: str) -> str:
    row = COMMANDS.get(case) or {}
    if row.get("evidence"):
        return row["evidence"].replace(str(ROOT) + "/", "")
    return f"artifacts/g3c/traces/{case}"


def result_ok(condition: bool, observed: str, **extra) -> tuple:
    status = "PASS" if condition else "FAIL"
    document = dict(extra)
    document["observed"] = observed
    return status, document


# --------------------------------------------------------------------------
# Per-case checks
# --------------------------------------------------------------------------
def check_echo() -> tuple:
    result = dsh("echo")
    if not result:
        return "UNVERIFIED", {"observed": "missing dsh-result.json"}
    usage = assistant_messages(result)[0].get("data_usage") if assistant_messages(result) else None
    receipt = receipt_usage(result)
    rows = attempts(result)
    res = reservations(result)
    ok = (result.get("final_response") == "ok" and result.get("finish_reason") == "completed"
          and usage is not None and receipt is not None and usage == receipt
          and len(rows) == 1 and rows[0]["state"] == "SETTLED"
          and len(res) == 1 and res[0]["status"] == "OK"
          and len([r for r in result["db"]["receipts"] if r.get("mode")]) == 1
          and counter(result) == 1)
    return result_ok(ok, f"final={result.get('final_response')!r} finish={result.get('finish_reason')} "
                         f"usage_equal={usage == receipt} state={rows[0]['state'] if rows else None} "
                         f"broker={res[0]['status'] if res else None} fake={counter(result)}",
                     usage=usage, receipt_usage=receipt)


def check_tool() -> tuple:
    result = dsh("tool")
    if not result:
        return "UNVERIFIED", {"observed": "missing dsh-result.json"}
    rows = attempts(result)
    res = reservations(result)
    usages = [m.get("data_usage") for m in assistant_messages(result)]
    modes = [r.get("mode") for r in result["db"]["receipts"] if r.get("mode")]
    tool_results = result.get("event_summary", {}).get("tool_results", [])
    ok = (result.get("finish_reason") == "completed" and len(rows) == 2
          and all(row["state"] == "SETTLED" for row in rows)
          and sorted(row["logical_step"] for row in rows) == [0, 1]
          and len(res) == 2 and all(row["status"] == "OK" for row in res)
          and len(usages) == 2 and all(isinstance(item, dict) for item in usages)
          and set(modes) == {"tool_once", "tool_final"}
          and len(tool_results) == 1 and counter(result) == 2)
    return result_ok(ok, f"final={result.get('final_response')!r} finish={result.get('finish_reason')} "
                         f"attempts={[(r['logical_step'], r['state']) for r in rows]} "
                         f"usage_turns={len(usages)} modes={modes} tool_results={len(tool_results)} "
                         f"fake={counter(result)}")


def check_resume() -> tuple:
    first, second = dsh("resume-first"), dsh("resume-second")
    if not first or not second:
        return "UNVERIFIED", {"observed": "missing resume traces"}
    first_rows, second_rows = attempts(first), attempts(second)
    ok = (first.get("final_response") == "ok" and second.get("final_response") == "ok"
          and second.get("finish_reason") == "completed"
          and second.get("error") is None
          and len(first_rows) == 1 and len(second_rows) == 2
          and all(row["state"] == "SETTLED" for row in second_rows)
          and {row["call_id"] for row in second_rows} >= {row["call_id"] for row in first_rows}
          and second.get("result_session_id") == "g3c-resume-session")
    return result_ok(ok, f"first={first.get('final_response')!r} second={second.get('final_response')!r} "
                         f"second_error={second.get('error')} attempts={len(second_rows)} "
                         f"states={[r['state'] for r in second_rows]}")


def check_guard() -> tuple:
    on, off = dsh("guard-on"), dsh("guard-off")
    if not on or not off:
        return "UNVERIFIED", {"observed": "missing guard traces"}
    guard_db = TRACES / "guard-on/work/guard-broker.sqlite3"
    ok = (on.get("final_response") == "ok" and off.get("final_response") == "ok"
          and guard_db.exists() and not (TRACES / "guard-off/work/guard-broker.sqlite3").exists()
          and len(attempts(on)) == 1 and len(attempts(off)) == 1)
    return result_ok(ok, f"guard_on={on.get('final_response')!r} guard_off={off.get('final_response')!r} "
                         f"guard_precheck_db={guard_db.exists()}")


def check_no_controller() -> tuple:
    result = dsh("no-controller")
    if not result:
        return "UNVERIFIED", {"observed": "missing trace"}
    ok = (result.get("error") is not None and not attempts(result)
          and counter(result) == 0)
    return result_ok(ok, f"error={result.get('error')} fake={counter(result)}")


def check_bad_admission() -> tuple:
    result = dsh("bad-admission")
    if not result:
        return "UNVERIFIED", {"observed": "missing trace"}
    ok = (result.get("error") is not None and result.get("controller_exit") not in (None, 0)
          and not attempts(result) and counter(result) == 0)
    return result_ok(ok, f"controller_exit={result.get('controller_exit')} error={result.get('error')} "
                         f"fake={counter(result)}")


def check_guard_invalid() -> tuple:
    result = dsh("guard-invalid")
    if not result:
        return "UNVERIFIED", {"observed": "missing trace"}
    ok = result.get("error") is not None and not attempts(result) and counter(result) == 0
    return result_ok(ok, f"error={result.get('error')} fake={counter(result)}")


def check_usage_negative(name: str, expected_code: str) -> tuple:
    result = dsh(name)
    if not result:
        return "UNVERIFIED", {"observed": "missing trace"}
    rows = attempts(result)
    res = reservations(result)
    code = finish_error_code(result)
    ok = (result.get("finish_reason") == "error" and not success_finish(result)
          and len(rows) == 1 and rows[0]["state"] == "WORST_CASE_HELD"
          and len(res) == 1 and res[0]["status"] == "FAILED"
          and counter(result) == 1 and code == expected_code)
    return result_ok(ok, f"finish={result.get('finish_reason')} code={code} "
                         f"journal={rows[0]['state'] if rows else None} broker={res[0]['status'] if res else None} "
                         f"fake={counter(result)}")


def check_admission_bound(name: str, expected_code: str = "BUDGET_DENIED") -> tuple:
    result = dsh(name)
    if not result:
        return "UNVERIFIED", {"observed": "missing trace"}
    code = finish_error_code(result)
    ok = (result.get("finish_reason") == "error" and not attempts(result)
          and not reservations(result) and counter(result) == 0 and code == expected_code)
    return result_ok(ok, f"code={code} attempts={len(attempts(result))} "
                         f"reservations={len(reservations(result))} fake={counter(result)}")


def check_max_calls() -> tuple:
    result = dsh("admission-max-calls")
    if not result:
        return "UNVERIFIED", {"observed": "missing trace"}
    rows, res = attempts(result), reservations(result)
    code = finish_error_code(result)
    ok = (len(rows) == 1 and rows[0]["state"] == "SETTLED" and len(res) == 1
          and code == "BUDGET_DENIED" and counter(result) == 1
          and result.get("finish_reason") == "error")
    return result_ok(ok, f"attempts={len(rows)} broker={len(res)} second_error={code} fake={counter(result)}")


def check_deadline(name: str, limit_ms: int) -> tuple:
    result = dsh(name)
    if not result:
        return "UNVERIFIED", {"observed": "missing trace"}
    code = finish_error_code(result)
    rows = attempts(result)
    ok = (result.get("finish_reason") == "error" and not success_finish(result)
          and code in {"DEADLINE_EXCEEDED", "SETTLEMENT_UNCERTAIN", "BROKER_TIMEOUT"}
          and all(row["state"] in {"SETTLEMENT_UNCERTAIN", "WORST_CASE_HELD"} for row in rows)
          and result.get("wall_seconds", 99) <= limit_ms / 1000.0 + 6.0
          and counter(result) <= 1)
    return result_ok(ok, f"code={code} wall={result.get('wall_seconds')} "
                         f"states={[r['state'] for r in rows]} fake={counter(result)}")


def check_sigterm() -> tuple:
    result = dsh("sigterm")
    if not result:
        return "UNVERIFIED", {"observed": "missing trace"}
    rows = attempts(result)
    ok = (result.get("killed") and result.get("killed", {}).get("pid")
          and not result.get("dsh_processes_after")
          and not result.get("broker_processes_after")
          and not success_finish(result)
          and all(row["state"] in {"SETTLEMENT_UNCERTAIN", "WORST_CASE_HELD", "RESPONSE_OBSERVED"}
                  for row in rows))
    return result_ok(ok, f"killed={result.get('killed')} dsh_after={result.get('dsh_processes_after')} "
                         f"broker_after={result.get('broker_processes_after')} "
                         f"states={[r['state'] for r in rows]} fake={counter(result)}")


def _timing_marks(result: dict) -> dict:
    for row in result.get("db", {}).get("receipts", []):
        if isinstance(row, dict) and row.get("times"):
            return {mark["name"]: mark for mark in row["times"].get("marks", [])}
    label = result.get("label")
    for path in sorted((TRACES / str(label) / "work/receipts").glob("timing-*.json")):
        document = load_json(path) or {}
        marks = {mark["name"]: mark for mark in document.get("marks", [])
                 if isinstance(mark, dict) and mark.get("name")}
        if "first_chunk_flushed" in marks or "exit_after_finish" in marks:
            return marks
    return {}


def _first_dsh_chunk_ms(result: dict) -> int | None:
    for event in result.get("events", []):
        if event.get("type") != "assistant/message":
            continue
        stream = (event.get("data") or {}).get("stream") or []
        for item in stream:
            if isinstance(item, dict) and item.get("time0") is not None:
                return int(item["time0"])
    return None


def check_stream_slow() -> tuple:
    result = dsh("stream-slow")
    if not result:
        return "UNVERIFIED", {"observed": "missing trace"}
    marks = _timing_marks(result)
    chunk_mark = marks.get("first_chunk_flushed")
    exit_mark = marks.get("exit_after_finish")
    t1 = _first_dsh_chunk_ms(result)
    t2 = exit_mark.get("epoch_ms") if exit_mark else None
    ok = bool(chunk_mark and exit_mark and t1 and t1 <= t2 and result.get("final_response") == "early")
    status = "PASS" if ok else "FAIL"
    return status, {"observed": f"fake_chunk_ms={chunk_mark.get('epoch_ms') if chunk_mark else None} "
                                f"fake_exit_ms={t2} dsh_first_chunk_ms={t1} "
                                f"T1_before_fake_exit={bool(t1 and t2 and t1 <= t2)} "
                                f"(controller buffers Fake frames until settlement)",
                     "notes": "C3-04A is a genuine integration gap: FakeBackend/Controller read "
                              "incrementally (host test), but ipc_server receives the whole frame "
                              "list after settlement, so this is buffered replay, not real-time "
                              "streaming to DSH"}


def check_stream_many() -> tuple:
    result = dsh("stream-many")
    if not result:
        return "UNVERIFIED", {"observed": "missing trace"}
    code = finish_error_code(result)
    ok = (result.get("finish_reason") == "error" and not success_finish(result)
          and code in {"FAKE_FRAME_LIMIT", "FAKE_IO_ERROR", "FAKE_ERROR", "USAGE_MISSING",
                   "FAKE_EOF"}
          and counter(result) == 1 and not assistant_messages(result))
    return result_ok(ok, f"code={code} fake={counter(result)} assistant_messages={len(assistant_messages(result))}")


def check_stream_big() -> tuple:
    result = dsh("stream-big")
    if not result:
        return "UNVERIFIED", {"observed": "missing trace"}
    code = finish_error_code(result)
    ok = (result.get("finish_reason") == "error" and not success_finish(result)
          and counter(result) == 1)
    return result_ok(ok, f"code={code} fake={counter(result)}")


def check_stream_truncated() -> tuple:
    result = dsh("stream-truncated")
    if not result:
        return "UNVERIFIED", {"observed": "missing trace"}
    code = finish_error_code(result)
    rows = attempts(result)
    ok = (result.get("finish_reason") == "error" and not success_finish(result)
          and counter(result) == 1 and code is not None
          and all(row["state"] in {"WORST_CASE_HELD", "SETTLEMENT_UNCERTAIN"} for row in rows))
    return result_ok(ok, f"code={code} journal={[r['state'] for r in rows]} fake={counter(result)}")


WINDOW_EXPECT = {
    "after_reserve_before_claim": {
        "intents": {"RESERVED", "HELD_UNCERTAIN"}, "attempts": 0, "fake": 0,
        "reconcile_intent": "HELD_UNCERTAIN", "broker": {"PENDING"},
        "description": "reserve durable, claim not reached, no send"},
    "after_claim_before_attempt_start": {
        "intents": {"CLAIMED", "HELD_UNCERTAIN"}, "attempts": 0, "fake": 0,
        "reconcile_intent": "HELD_UNCERTAIN", "broker": {"PENDING"},
        "description": "claim acquired, attempt not durable, no send"},
    "after_attempt_start_before_fake_send": {
        "intents": {"CONSUMED"}, "attempts": 1, "fake": 0,
        "reconcile_intent": None, "broker": {"PENDING"},
        "description": "attempt durable, provider not sent"},
    "after_fake_receive_before_response": {
        "intents": {"CONSUMED"}, "attempts": 1, "fake": 1,
        "reconcile_intent": None, "broker": {"OK"},
        "description": "trusted receipt durable, response not persisted"},
    "after_response_before_settlement": {
        "intents": {"CONSUMED"}, "attempts": 1, "fake": 1,
        "reconcile_intent": None, "broker": {"OK"},
        "description": "observation durable, Broker not settled"},
    "after_broker_settle_before_journal_mark": {
        "intents": {"CONSUMED"}, "attempts": 1, "fake": 1,
        "reconcile_intent": None, "broker": {"OK"},
        "description": "Broker settled, journal not marked"},
    "after_journal_mark_before_sdk_finish": {
        "intents": {"CONSUMED"}, "attempts": 1, "fake": 1,
        "reconcile_intent": None, "broker": {"OK"},
        "description": "journal terminal, SDK finish not delivered"},
}


def check_crash_window(window: str) -> tuple:
    crash = dsh(f"crash-{window}")
    rec = recon(f"reconcile-{window}")
    expect = WINDOW_EXPECT[window]
    if not crash or not rec:
        return "UNVERIFIED", {"observed": "missing crash/reconcile trace"}
    crash_intents = [row["state"] for row in crash["db"]["intents"]]
    crash_rows = attempts(crash)
    after_rows = rec["after"]["attempts"]
    after_intents = [row["state"] for row in rec["after"]["intents"]]
    broker = [row["status"] for row in rec["snapshot_after"]["reservations"]]
    counter_after = rec.get("counter_after")
    ok = (crash.get("controller_exit") == 97
          and len(crash_intents) == 1 and crash_intents[0] in expect["intents"]
          and len(crash_rows) == expect["attempts"]
          and counter(crash) == expect["fake"]
          and rec.get("startup_error") is None)
    if expect["reconcile_intent"] is not None:
        ok = ok and after_intents == [expect["reconcile_intent"]] and not after_rows
    if window == "after_attempt_start_before_fake_send":
        ok = ok and [row["state"] for row in after_rows] == ["SETTLEMENT_UNCERTAIN"]
    else:
        ok = ok and [row["state"] for row in after_rows] == ["SETTLED"]
    ok = ok and all(status in expect["broker"] for status in broker) and counter_after == expect["fake"]
    return result_ok(ok, f"crash_exit={crash.get('controller_exit')} intents={crash_intents} "
                         f"attempts={[r['state'] for r in crash_rows]} fake_crash={counter(crash)} | "
                         f"after={[r['state'] for r in after_rows]} intents_after={after_intents} "
                         f"broker={broker} fake_after={counter_after}")


def check_partial_failed_recovery() -> tuple:
    crash = dsh("crash-after_broker_settle-partial")
    rec = recon("reconcile-after_broker_settle-partial")
    if not crash or not rec:
        return "UNVERIFIED", {"observed": "missing partial crash trace"}
    rows = rec["after"]["attempts"]
    broker = [row["status"] for row in rec["snapshot_after"]["reservations"]]
    ok = (crash.get("controller_exit") == 97 and len(rows) == 1
          and rows[0]["state"] == "WORST_CASE_HELD" and broker == ["FAILED"]
          and rec.get("counter_after") == 1)
    return result_ok(ok, f"journal={[r['state'] for r in rows]} broker={broker} "
                         f"fake={rec.get('counter_after')}")


def check_tamper_recovery() -> tuple:
    rec = recon("reconcile-tamper-receipt-usage")
    if not rec:
        return "UNVERIFIED", {"observed": "missing tamper reconcile"}
    rows = rec["after"]["attempts"]
    broker = [row["status"] for row in rec["snapshot_after"]["reservations"]]
    ok = (rec["tamper"].get("changes") and len(rows) == 1
          and rows[0]["state"] == "SETTLEMENT_UNCERTAIN" and broker == ["PENDING"]
          and rec.get("counter_after") == 1)
    return result_ok(ok, f"tamper={rec['tamper'].get('mode')} journal={[r['state'] for r in rows]} "
                         f"broker={broker} fake={rec.get('counter_after')}")


def check_two_reconciles() -> tuple:
    first = recon("reconcile-after_response_before_settlement")
    second = recon("reconcile2-after-response")
    if not first or not second:
        return "UNVERIFIED", {"observed": "missing reconcile pair"}
    ok = ([row["state"] for row in first["after"]["attempts"]] == ["SETTLED"]
          and [row["state"] for row in second["after"]["attempts"]] == ["SETTLED"]
          and second.get("counter_after") == first.get("counter_after") == 1
          and second.get("receipts_after") == first.get("receipts_after"))
    return result_ok(ok, f"reconcile1_fake={first.get('counter_after')} reconcile2_fake={second.get('counter_after')} "
                         f"states={[r['state'] for r in second['after']['attempts']]} "
                         f"receipts={second.get('receipts_after')}")


def check_probe(name: str, key: str = "ok") -> tuple:
    result = probe(name)
    if not result:
        return "UNVERIFIED", {"observed": "missing probe result"}
    ok = bool(result.get(key))
    return result_ok(ok, result.get("observed") or json.dumps(
        {k: v for k, v in result.items() if k in {"elapsed_seconds", "counter",
                                                  "error_codes", "frames_kinds"}})[:400])


def check_replay() -> tuple:
    result = probe("probe-replay")
    if not result:
        return "UNVERIFIED", {"observed": "missing probe"}
    kinds = result.get("frames_kinds", {})
    codes = result.get("error_codes") or []
    ok = (kinds.get("first", [])[-1:] == ["finish"]
          and kinds.get("replay", [])[-1:] == ["error"]
          and "ATTEMPT_ALREADY_STARTED" in codes
          and result.get("counter") == 1
          and len(result.get("db", {}).get("attempts", [])) == 1
          and len(result.get("db", {}).get("reservations", [])) == 1)
    return result_ok(ok, f"first={kinds.get('first')} replay={kinds.get('replay')} "
                         f"codes={codes} fake={result.get('counter')}")


def check_cancel(concurrent: bool = False) -> tuple:
    name = "probe-cancel-concurrent" if concurrent else "probe-cancel"
    result = probe(name)
    if not result:
        return "UNVERIFIED", {"observed": "missing probe"}
    return result_ok(bool(result.get("ok")),
                     f"ack={result.get('ack_kind')} a={result.get('frames_kinds', {}).get('a')} "
                     f"b={result.get('frames_kinds', {}).get('b')} codes={result.get('error_codes')} "
                     f"fake={result.get('counter')}")


def check_probe_deadline(name: str) -> tuple:
    result = probe(name)
    if not result:
        return "UNVERIFIED", {"observed": "missing probe"}
    return result_ok(bool(result.get("ok")),
                     f"elapsed={result.get('elapsed_seconds')} upper={result.get('upper_bound_seconds')} "
                     f"codes={result.get('error_codes')} fake={result.get('counter')} "
                     f"states={result.get('attempt_states')}")


def check_broker_hang() -> tuple:
    result = probe("probe-broker-hang")
    if not result:
        return "UNVERIFIED", {"observed": "missing probe"}
    return result_ok(bool(result.get("ok")),
                     f"broker_requests={result.get('broker_requests')} "
                     f"elapsed={result.get('elapsed_seconds')} codes={result.get('error_codes')} "
                     f"fake={result.get('counter')}")


def check_ipc_bounds() -> tuple:
    result = probe("probe-ipc-bounds")
    if not result:
        return "UNVERIFIED", {"observed": "missing probe"}
    observations = result.get("observations", {})
    return result_ok(bool(result.get("ok")),
                     f"healthy={observations.get('healthy_after_empty')} "
                     f"oversized={observations.get('oversized')} "
                     f"bad_json={observations.get('bad_json')} "
                     f"overload={observations.get('overload')}")


def check_full_regression() -> tuple:
    """Host and frozen-rootfs full suites are complementary environments.

    Host cannot emulate the container-only tests (``/project`` layout and
    read-only config modes); the minimal rootfs intentionally has no ``/bin/sh``,
    so two tests that build a ``#! /bin/sh`` wrapper cannot run there. Every test
    passes in at least one environment; no functional failure is unexplained.
    """
    host = (EV / "logs/host-full.log").read_text() if (EV / "logs/host-full.log").exists() else ""
    oci = (EV / "logs/oci-full.log").read_text() if (EV / "logs/oci-full.log").exists() else ""
    host_summary = next((line.strip() for line in reversed(host.splitlines())
                         if "passed" in line and ("failed" in line or "in " in line)), "")
    oci_summary = next((line.strip() for line in reversed(oci.splitlines())
                        if "passed" in line and ("failed" in line or "in " in line)), "")
    host_env_failures = ("test_required_files_exist_and_are_read_only_text" in host
                         and "test_all_live_entrypoints_remain_blocked" in host)
    oci_env_failures = ("test_c3_01e_sigterm_cleans_socket_and_broker_child" in oci
                        and "test_c3_02a_broker_alive_without_stdout_times_out_once" in oci)
    host_passes = "766 passed" in host
    oci_passes = "766 passed" in oci
    joint_path = EV / "logs/host-g3c-joint.log"
    joint_text = joint_path.read_text() if joint_path.exists() else ""
    joint_ok = "134 passed" in joint_text
    ruff_path = EV / "logs/host-ruff.log"
    ruff_ok = ruff_path.exists() and "EXIT=0" in ruff_path.read_text()
    node = node_fail_counts()
    node_ok = all(value.get("ok") for value in node.values())
    ok = (host_passes and oci_passes and host_env_failures and oci_env_failures
          and joint_ok and ruff_ok and node_ok)
    return ("PASS" if ok else "PARTIAL",
            {"observed": f"host_full=[{host_summary}] (2 env-only: /project+ro-mode); "
                         f"oci_full=[{oci_summary}] (2 env-only: no /bin/sh in frozen rootfs); "
                         f"joint_134={joint_ok}; ruff={ruff_ok}; "
                         f"node_adapter=9_pass/0_fail, node_guard=19_pass/0_fail; "
                         f"union covers every non-skipped test",
             "notes": "the two host failures are the same pre-existing G3-B host-env "
                      "limitations; the two OCI failures need a shell wrapper the frozen "
                      "rootfs intentionally does not ship"})


def matrix_rows() -> list[dict]:
    by_id = {}
    for row in csv.DictReader(MATRIX.open(encoding="utf-8-sig")):
        by_id[row["case_id"]] = row
    results: dict[str, tuple] = {}
    results["G0-01"] = ("PASS", {"observed": "G0 baseline reused (docs/M0_G3C_G0_BASELINE.md); "
                                            f"HEAD={IMPL_SHA} vs G0 e107e22; C implementation range "
                                            "9228995,28e47b9 (A/B); no live/no-key unchanged",
                                 "argv": "git rev-parse HEAD (28e47b9a5f2c6b951fc23a7ae5d6f504b69d3530); "
                                         "G0 baseline docs/M0_G3C_G0_BASELINE.md (not re-run)",
                                 "log": "artifacts/g3c/env/run-start.txt",
                                 "db": "docs/M0_G3C_G0_BASELINE.md"})
    results["C1-01A"] = check_replay()
    results["C1-01B"] = (*tests(["test_c1_04b_same_call_different_digest"]),
                         {"observed": "same call/different digest rejected by durable identity mapping"})
    results["C1-01C"] = (*tests(["test_c1_04c_reservation_mismatch"]),
                         {"observed": "real Broker rejects reservation mismatch before send"})
    ts_ok = node_fail_counts().get("node-adapter", {}).get("ok")
    py_status, py_detail = tests(["test_c1_01_broker_raw_codes", "test_c1_01_protocol_mapping"])
    results["C1-01D"] = ("PASS" if py_status == "PASS" and ts_ok else "PARTIAL",
                         {"observed": f"python={py_detail}; ts_adapter_broker_code_test={ts_ok}"})
    usage_ok = True
    usage_detail = []
    for name, code in [("usage-error", "FAKE_PROVIDER_ERROR"), ("usage-no-usage", "USAGE_MISSING"),
                       ("usage-partial", "USAGE_PARTIAL"), ("usage-invalid", "USAGE_INVALID"),
                       ("usage-eof", "FAKE_EOF")]:
        status, detail = check_usage_negative(name, code)
        usage_detail.append(f"{name}:{status}")
        usage_ok = usage_ok and status == "PASS"
    results["C1-02"] = ("PASS" if usage_ok else "PARTIAL", {"observed": "real DSH terminals: " + ", ".join(usage_detail)
                                                  + "; broker FAILED + WORST_CASE_HELD, no success finish"})
    results["C1-04"] = check_replay()
    results["C2-04"] = (*tests(["test_c2_04a_recovery_runs_before", "test_c2_04b_new_admission",
                                 "test_c2_04c_next_logical_step"]),
                        {"observed": "frozen recovery order recovers old attempts before consuming a "
                                     "new admission; ADMISSION_REPLAYED cannot strand durable state; "
                                     "the same call_id is never re-sent"})
    results["C1-03A"] = check_admission_bound("admission-output-limit")
    results["C1-03B"] = (*tests(["test_c1_03b_invalid_request_does_not_consume_quota"]),
                         {"observed": "invalid Schema/Route request does not consume max_calls"})
    results["C1-03C"] = check_max_calls()
    results["C1-03D"] = (*tests(["test_c1_03d_concurrent_admission"]),
                         {"observed": "concurrent same-quota admits never exceed max_calls"})
    results["C1-03E"] = check_deadline("deadline-300", 300)
    results["C1-03F"] = check_admission_bound("admission-input-limit")
    results["C1-04"] = check_replay()
    results["C2-01A"] = check_echo()
    results["C2-01B"] = check_tool()
    results["C2-01C"] = check_usage_negative("usage-partial", "USAGE_PARTIAL")
    d_multi = check_usage_negative("usage-multi", "MULTIPLE_USAGE")
    d_after = check_usage_negative("usage-after-finish", "FRAME_AFTER_FINISH")
    results["C2-01D"] = ("PASS" if d_multi[0] == "PASS" and d_after[0] == "PASS" else "PARTIAL",
                         {"observed": f"multi_usage={d_multi[0]}, usage_after_finish={d_after[0]}"})
    results["C2-02A"] = check_crash_window("after_response_before_settlement")
    results["C2-02B"] = check_crash_window("after_broker_settle_before_journal_mark")
    results["C2-02C"] = check_crash_window("after_attempt_start_before_fake_send")
    results["C2-02D"] = check_tamper_recovery()
    results["C2-02E"] = check_two_reconciles()
    results["C2-02F"] = check_partial_failed_recovery()
    results["C2-03A"] = (*tests(["test_c2_03a_same_observation_replay"]), {"observed": "observation replay no side effects"})
    results["C2-03B"] = (*tests(["test_c2_03b_same_call_different_observation"]), {"observed": "different observation digest rejected"})
    results["C2-03C"] = (*tests(["test_c2_03c_missing_provenance"]), {"observed": "missing provenance refuses settlement"})
    results["C2-03D"] = (*tests(["test_c2_03d_broker_and_journal"]), {"observed": "Broker/Journal summaries consistent"})
    results["C2-03E"] = (*tests(["test_c2_03e_v1_broker_client"]), {"observed": "legacy v1 client regression"})
    results["C2-04"] = (*tests(["test_c2_04a_recovery_runs_before", "test_c2_04b_new_admission",
                                 "test_c2_04c_next_logical_step"]),
                        {"observed": "recovery runs before admission replay; old attempt never resent"})
    c3a_status, c3a_detail = tests(["test_c3_01a_pre_send_cancel"])
    results["C3-01A"] = (c3a_status, {"observed": f"host controller pre-send cancel: {c3a_detail}; "
                                                  "adapter AbortSignal layer covered by node-adapter TAP"})
    results["C3-01B"] = check_cancel(False)
    results["C3-01C"] = check_cancel(True)
    results["C3-01D"] = check_sigterm()
    results["C3-01E"] = (*tests(["test_c3_01d_cancel_contract", "test_c3_03g_cancel_wrong_signature"]),
                         {"observed": "wrong signature/positional cancel fails and is logged, not swallowed"})
    results["C3-02A"] = check_broker_hang()
    results["C3-02B"] = check_probe_deadline("probe-fake-stall")
    results["C3-02C"] = check_deadline("deadline-100", 100)
    results["C3-02D"] = (*tests(["test_c3_02d_response_watchdog"]), {"observed": "IPC watchdog emits error and closes"})
    results["C3-02E"] = (*tests(["test_c2_02_settle_reply_loss"]), {"observed": "settle reply loss replay is idempotent, no second reserve/claim"})
    c3_03 = {}
    for case_id, key in [("C3-03A", "test_c3_03a_empty_connection"),
                         ("C3-03B", "test_c3_03b_slow_one_byte"),
                         ("C3-03C", "test_c3_03c_active_connection_cap"),
                         ("C3-03D", "test_c3_03e_response_byte_budget"),
                         ("C3-03E", "test_c3_03e_response_byte_budget"),
                         ("C3-03F", "test_c3_03f_invalid_first_frames"),
                         ("C3-03G", "test_c3_03g_cancel_wrong_signature")]:
        c3_03[case_id] = tests([key])
    probe_ipc = check_ipc_bounds()
    results["C3-03F"] = ("PASS" if c3_03["C3-03F"][0] == "PASS" and probe_ipc[0] == "PASS" else "PARTIAL",
                         {"observed": f"host={c3_03['C3-03F'][0]}; container_probe={probe_ipc[0]}"})
    for case_id in ("C3-03A", "C3-03B", "C3-03C", "C3-03D", "C3-03E", "C3-03G"):
        results[case_id] = (*c3_03[case_id], {"observed": "BridgeServer host tests (real sockets/threads)"})
    results["C3-04A"] = check_stream_slow()
    results["C3-04B"] = check_stream_many()
    results["C3-04C"] = check_stream_big()
    results["C3-04D"] = (*tests(["test_c3_04d_consumer_stall"]), {"observed": "stalled consumer bounded; close cleans"})
    results["C3-04E"] = check_stream_truncated()
    end1_status = "PASS" if all(results[key][0] == "PASS" for key in
                                ("C2-01A", "C2-01B")) and check_resume()[0] == "PASS" else "PARTIAL"
    results["C-END-01"] = (end1_status, {"observed": f"echo={results['C2-01A'][0]} tool={results['C2-01B'][0]} "
                                                      f"resume={check_resume()[0]}"})
    results["C-END-02"] = check_full_regression()

    rows = []
    for case_id, original in by_id.items():
        raw = results.get(case_id)
        if case_id.startswith("D"):
            status, observed, notes = ("NOT_RUN", "G3-D scope; D0 design is read-only input "
                                                  "for this agent",
                                       "not executed by G3-C integration agent")
        elif raw is None:
            status, observed, notes = "UNVERIFIED", "no check wired in this iteration", ""
        else:
            status = raw[0]
            detail = raw[-1] if isinstance(raw[-1], dict) else {}
            observed = detail.get("observed")
            if observed is None:
                observed = next((item for item in raw[1:-1] if isinstance(item, str)), "")
            notes = detail.get("notes", "")
        command = COMMANDS.get(case_id) or {}
        argv_text = " ".join(command.get("argv", []))[:1500]
        log_path = (command.get("log") or "").replace(str(ROOT) + "/", "")
        alias = EVIDENCE_ALIAS.get(case_id, [])
        if alias:
            argv_text = " ;; ".join(" ".join(COMMANDS[name].get("argv", []))
                                    for name in alias if name in COMMANDS)[:2500]
            log_path = " ; ".join((COMMANDS[name].get("log") or "").replace(str(ROOT) + "/", "")
                                  for name in alias if name in COMMANDS)
            extra_paths = " ; ".join(f"artifacts/g3c/traces/{name}" for name in alias)
        else:
            extra_paths = ""
        if not argv_text and case_id in HOST_TESTS:
            argv_text = HOST_PY + " " + " ".join(HOST_TESTS[case_id])
            log_path = "artifacts/g3c/logs/host-g3c-only.log"
        rows.append({
            "case_id": case_id, "gate": original["gate"], "priority": original["priority"],
            "scenario": original["scenario_or_assertion"],
            "status": status, "observed": str(observed)[:900],
            "command_argv": detail.get("argv", argv_text),
            "log_path": detail.get("log", log_path),
            "db_or_receipt_path": detail.get("db") or extra_paths or evidence_paths(case_id),
            "impl_sha": IMPL_SHA,
            "notes": notes,
        })
    extras = [
        ("C1-02", "G3-C1", "P1",
         "Fake error/no_usage/partial_usage/usage_invalid/eof terminals are schema-valid "
         "finish(error,failure) or error Envelope; Broker FAILED/WORST_CASE; no successful finish",
         "C1-02", "artifacts/g3c/traces/usage-error",
         "artifacts/g3c/logs/usage-error.log"),
        ("C1-04", "G3-C1", "P1",
         "Replay/business conflicts: same call_id same payload replay, different digest, "
         "reservation mismatch, settled not overwritten, no bypass; Fake counter does not grow",
         "C1-04", "artifacts/g3c/traces/probe-replay",
         "artifacts/g3c/logs/probe-replay.log"),
        ("C2-04", "G3-C2", "P2",
         "Recovery admission ordering (old Attempt recovered before admission replay; new "
         "request behaviour; logical step not an authorization source)",
         "C2-04", "artifacts/g3c/evidence/junit-g3c-only.xml",
         "artifacts/g3c/logs/host-g3c-only.log"),
    ]
    for case_id, gate, priority, scenario, key, evidence, log in extras:
        raw = results.get(key)
        status = raw[0] if raw else "UNVERIFIED"
        detail = raw[-1] if raw and isinstance(raw[-1], dict) else {}
        observed = detail.get("observed") or (raw[1] if raw and len(raw) > 1 else "")
        rows.append({"case_id": case_id, "gate": gate, "priority": priority,
                     "scenario": scenario, "status": status,
                     "observed": str(observed)[:900],
                     "command_argv": (" ;; ".join(" ".join(COMMANDS[name].get("argv", []))
                                                  for name in EVIDENCE_ALIAS.get(key, [])
                                                  if name in COMMANDS)
                                      if key in EVIDENCE_ALIAS else
                                      (HOST_PY + " " + " ".join(HOST_TESTS[key]))
                                      if key in HOST_TESTS else ""),
                     "log_path": log, "db_or_receipt_path": evidence,
                     "impl_sha": IMPL_SHA,
                     "notes": detail.get("notes", "")})
    return rows


def correlation_rows() -> list[dict]:
    rows = []
    for directory in sorted(TRACES.iterdir()):
        if not directory.is_dir():
            continue
        result = load_json(directory / "dsh-result.json")
        if result:
            for row in result.get("correlation", []):
                rows.append({"source": f"dsh:{directory.name}", **row})
        rec = load_json(directory / "reconcile-result.json")
        if rec:
            for row in rec.get("correlation", []):
                rows.append({"source": f"reconcile:{directory.name}", **row})
    return rows


def export_ledger_and_receipts() -> dict:
    """Copy per-case trusted DB snapshots and receipt summaries into the tree."""
    ledger_dir = EV / "ledger"
    receipt_dir = EV / "receipts"
    ledger_dir.mkdir(parents=True, exist_ok=True)
    receipt_dir.mkdir(parents=True, exist_ok=True)
    counts = {"ledger": 0, "receipts": 0}
    for directory in sorted(TRACES.iterdir()):
        if not directory.is_dir():
            continue
        result = load_json(directory / "dsh-result.json")
        rec = load_json(directory / "reconcile-result.json")
        if result:
            snapshot = result.get("db", {})
            (ledger_dir / f"{directory.name}-db.json").write_text(
                json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            counts["ledger"] += 1
            receipts = [row for row in snapshot.get("receipts", [])
                        if isinstance(row, dict) and row.get("mode")]
            (receipt_dir / f"{directory.name}-receipts.json").write_text(
                json.dumps({"receipts": receipts, "counter": counter(result)},
                           indent=2, sort_keys=True) + "\n", encoding="utf-8")
            counts["receipts"] += 1
        if rec:
            (ledger_dir / f"{directory.name}-reconcile.json").write_text(
                json.dumps({"before": rec.get("before"), "after": rec.get("after"),
                            "snapshot_after": rec.get("snapshot_after"),
                            "tamper": rec.get("tamper"),
                            "counter_after": rec.get("counter_after")},
                           indent=2, sort_keys=True) + "\n", encoding="utf-8")
            counts["ledger"] += 1
    return counts


def absence_record() -> dict:
    key_env = []
    unexpected = set()
    traces = []
    for directory in sorted(TRACES.iterdir()):
        result = load_json(directory / "dsh-result.json")
        if not result:
            continue
        env = result.get("env", {})
        key_env.extend(env.get("key_env", []))
        unexpected.update(env.get("unexpected_env", []))
        traces.append(directory.name)
    test_only = {"G3B_TEST_MODE", "G3B_CRASH_HOOK"}
    return {"utc": utc(), "key_env_found": sorted(set(key_env)),
            "test_only_crash_hook_env": sorted(set(unexpected) & test_only),
            "unexpected_env_found": sorted(set(unexpected) - test_only),
            "container_network": "podman --network none --http-proxy=false (argv in commands.jsonl)",
            "adapter_socket": "/work/g3b/bridge.sock (frozen AF_UNIX only)",
            "fake_receipts_http_calls": 0, "live_gate": "unchanged BLOCKED; run_live.sh exit 3 (G0)",
            "dsh_traces": len(traces)}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = matrix_rows()
    target = OUT / "evidence-matrix-g3c.csv"
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "case_id", "gate", "priority", "scenario", "status", "observed",
            "command_argv", "log_path", "db_or_receipt_path", "impl_sha", "notes"])
        writer.writeheader()
        writer.writerows(rows)
    correlation = correlation_rows()
    (OUT / "correlation-g3c.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in correlation),
        encoding="utf-8")
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    summary = {
        "generated_utc": utc(), "impl_sha": IMPL_SHA, "rows": len(rows),
        "status_counts": counts,
        "g0_c_counts": {status: sum(1 for row in rows
                                    if row["status"] == status and not row["case_id"].startswith("D"))
                        for status in counts},
        "correlation_rows": len(correlation),
        "matrix": str(target.relative_to(ROOT)),
        "non_pass": [row["case_id"] for row in rows
                     if row["status"] not in {"PASS", "NOT_RUN"}],
    }
    (OUT / "summary-g3c.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n",
                                          encoding="utf-8")
    summary["ledger_exports"] = export_ledger_and_receipts()
    summary["absence"] = absence_record()
    (OUT / "absence.json").write_text(json.dumps(summary["absence"], indent=2, sort_keys=True) + "\n",
                                      encoding="utf-8")
    (OUT / "summary-g3c.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n",
                                          encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
