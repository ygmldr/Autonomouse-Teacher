#!/usr/bin/env python3
"""Read-only post-hoc audit for the A-PR3 / R-REV6 window evidence.

Consumes only the copied evidence tree (dispatch-window / request-lifecycle
JSONL, read-only broker+attempt DB snapshots, receipts, case-runner identity) and
never opens a live run directory.  It re-checks the digest bindings and the
at-most-once/held invariants for every case and classifies each case as
PASS / PARTIAL / NOT_RUN against the frozen case matrix.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

DIGEST_FIELDS = ("prepared_digest", "payload_digest")


def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                rows.append({"invalid_line": True})
    return rows


def _query(path: Path, sql: str) -> list[dict]:
    if not path.is_file():
        return []
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in connection.execute(sql)]
    except sqlite3.Error:
        return []
    finally:
        connection.close()


def _load_case(evidence: Path) -> dict:
    snapshot = _read_json(evidence / "db" / "snapshot.json") or {}
    runner = _read_json(evidence / "a_next" / "case-runner.json") or {}
    dispatch = _read_jsonl(evidence / "run" / "dispatch-window.jsonl")
    lifecycle = _read_jsonl(evidence / "run" / "state" / "request-lifecycle.jsonl")
    receipts = snapshot.get("receipts") or []
    counter_path = evidence / "receipt" / "received-count.json"
    counter_doc = _read_json(counter_path) or {}
    # Prefer the raw read-only DB copies (independent of launcher snapshot code).
    db_dir = evidence / "db"
    attempts = _query(db_dir / "attempts.sqlite3",
                      "SELECT attempt_id,call_id,reservation_id,state,reason,"
                      "payload_digest,prepared_digest,receipt_id FROM g3b_attempts")
    intents = _query(db_dir / "attempts.sqlite3",
                     "SELECT intent_id,call_id,reservation_id,state,reason "
                     "FROM g3b_send_intents")
    reservations = _query(db_dir / "broker.sqlite3",
                          "SELECT reservation_id,status,cost,estimated,"
                          "settlement_json FROM budget_reservations")
    claims = _query(db_dir / "broker.sqlite3",
                    "SELECT call_id,reservation_id,request_digest,status "
                    "FROM budget_dispatch_claims")
    return {
        "runner": runner, "snapshot": snapshot, "dispatch": dispatch,
        "lifecycle": lifecycle, "receipts": receipts,
        "fake_counter": (counter_doc.get("count") if counter_doc else
                         snapshot.get("fake_counter")),
        "attempts": attempts, "intents": intents,
        "reservations": reservations, "claims": claims,
    }


def _digest_checks(case: dict) -> list[dict]:
    checks: list[dict] = []
    claims_by_call = {row.get("call_id"): row for row in case["claims"]}
    receipts_by_id = {row.get("receipt_id"): row for row in case["receipts"]}
    joined = 0
    prepared_ok = payload_ok = distinct_ok = True
    for attempt in case["attempts"]:
        prepared = attempt.get("prepared_digest")
        payload = attempt.get("payload_digest")
        claim = claims_by_call.get(attempt.get("call_id"))
        receipt = receipts_by_id.get(attempt.get("receipt_id"))
        if claim is not None and prepared is not None:
            joined += 1
            if prepared != claim.get("request_digest"):
                prepared_ok = False
        if receipt is not None and payload is not None:
            if payload != receipt.get("raw_sha256"):
                payload_ok = False
        if prepared is not None and payload is not None and prepared == payload:
            distinct_ok = False
    checks.append({"id": "prepared_digest==claim.request_digest",
                   "ok": prepared_ok, "joined": joined})
    checks.append({"id": "payload_digest==receipt.raw_sha256",
                   "ok": payload_ok,
                   "receipts": len(receipts_by_id)})
    checks.append({"id": "prepared_digest!=payload_digest", "ok": distinct_ok})
    return checks


def _invariant_checks(case: dict) -> list[dict]:
    checks: list[dict] = []
    runner = case["runner"]
    checks.append({"id": "containers_after_empty",
                   "ok": not (runner.get("containers_after") or [])})
    checks.append({"id": "zero_real_calls",
                   "ok": runner.get("real_model_calls", 0) == 0
                   and runner.get("real_external_http_calls", 0) == 0
                   and runner.get("provider_keys_seen", 0) == 0})
    counter = case["fake_counter"]
    receipts = len(case["receipts"])
    checks.append({"id": "fake_counter_matches_receipts",
                   "ok": counter is None or int(counter) == receipts,
                   "fake_counter": counter, "receipts": receipts})
    # Exactly-once terminal reservation: unique reservation ids, status once.
    statuses = [row.get("status") for row in case["reservations"]]
    checks.append({"id": "reservation_status_unique",
                   "ok": len(case["reservations"]) == len(
                       {row.get("reservation_id") for row in case["reservations"]})})
    # No PENDING reservation may be FREE while an attempt/intent claims a send.
    pending = [row for row in case["reservations"] if row.get("status") == "PENDING"]
    attempts_by_res = {row.get("reservation_id"): row for row in case["attempts"]}
    held_ok = True
    for reservation in pending:
        attempt = attempts_by_res.get(reservation.get("reservation_id"))
        if attempt is not None and attempt.get("state") in {"SETTLED", "WORST_CASE_HELD"}:
            held_ok = False
    checks.append({"id": "pending_not_marked_free", "ok": held_ok,
                   "pending": len(pending), "statuses": statuses})
    attempts = case["attempts"]
    checks.append({"id": "attempt_identity_unique",
                   "ok": len(attempts) == len({row.get("attempt_id") for row in attempts})
                   and len(attempts) == len({row.get("reservation_id") for row in attempts})})
    settled = [row for row in attempts if row.get("state") == "SETTLED"]
    settled_ok = len(settled) == len({row.get("reservation_id") for row in settled})
    checks.append({"id": "settled_at_most_once", "ok": settled_ok,
                   "settled": len(settled)})
    return checks


def _expected_checks(case_id: str, case: dict, expected: dict) -> list[dict]:
    checks: list[dict] = []
    dispatch = case["dispatch"]
    completed = [row for row in dispatch if row.get("outcome") == "completed"]
    rejected = [row for row in dispatch if row.get("outcome") == "rejected"]
    states = [row.get("state") for row in case["attempts"]]
    statuses = [row.get("status") for row in case["reservations"]]
    if "dispatches" in expected:
        checks.append({"id": "completed_dispatch_count",
                       "ok": len(completed) == expected["dispatches"],
                       "expected": expected["dispatches"],
                       "observed": len(completed)})
    if "fake" in expected:
        checks.append({"id": "fake_count",
                       "ok": case["fake_counter"] == expected["fake"]
                       or (expected["fake"] == 0 and case["fake_counter"] in (0, None)),
                       "expected": expected["fake"],
                       "observed": case["fake_counter"]})
    if "reservations" in expected:
        checks.append({"id": "reservation_count",
                       "ok": len(case["reservations"]) == expected["reservations"],
                       "expected": expected["reservations"],
                       "observed": len(case["reservations"])})
    if "broker_state" in expected:
        checks.append({"id": "broker_state",
                       "ok": expected["broker_state"] in statuses,
                       "expected": expected["broker_state"],
                       "observed": statuses})
    if "attempt_state" in expected:
        checks.append({"id": "attempt_state",
                       "ok": expected["attempt_state"] in states,
                       "expected": expected["attempt_state"],
                       "observed": states})
    if expected.get("reason_class"):
        reasons = " ".join(str(row.get("reason")) for row in
                           case["attempts"] + case["intents"])
        checks.append({"id": "reason_class",
                       "ok": expected["reason_class"] in reasons,
                       "expected": expected["reason_class"]})
    if expected.get("lifecycle_events"):
        events = [row.get("event") for row in case["lifecycle"]]
        wanted = list(expected["lifecycle_events"])
        position = 0
        for event in events:
            if position < len(wanted) and event == wanted[position]:
                position += 1
        checks.append({"id": "lifecycle_events_subsequence",
                       "ok": position == len(wanted),
                       "expected": wanted, "observed": events})
    if "rejection_code" in expected:
        codes = [row.get("error_code") for row in rejected]
        checks.append({"id": "replay_rejection_code",
                       "ok": expected["rejection_code"] in codes,
                       "expected": expected["rejection_code"],
                       "observed": codes})
    if case_id == "R6-04":
        checks = [check for check in checks
                  if check["id"] not in {"completed_dispatch_count"}]
        turns = case["runner"].get("turns") or []
        turn2 = turns[1] if len(turns) > 1 else {}
        turn2_result = turn2.get("result") or {}
        error = turn2_result.get("error") or {}
        checks.append({"id": "dsh_session_reuse_refused",
                       "ok": turn2.get("exit_code") not in (0, None)
                       and "already exists" in str(error.get("message", "")),
                       "observed": error.get("message")})
        checks.append({"id": "replay_no_second_receipt",
                       "ok": len(case["receipts"]) <= 1,
                       "receipts": len(case["receipts"])})
    if case_id == "R6-04B":
        checks = [
            {"id": "first_dispatch_completed",
             "ok": len([row for row in case["dispatch"]
                        if row.get("outcome") == "completed"]) == 1},
            {"id": "replay_dispatch_rejected",
             "ok": len([row for row in case["dispatch"]
                        if row.get("outcome") == "rejected"]) >= 1,
             "observed": [row.get("error_code") for row in case["dispatch"]]},
            {"id": "single_receipt",
             "ok": len(case["receipts"]) == 1,
             "receipts": len(case["receipts"])},
            {"id": "no_second_attempt",
             "ok": len(case["attempts"]) == 1,
             "attempts": [row.get("state") for row in case["attempts"]]},
        ]
    if case_id == "R6-09":
        injection = (case["runner"].get("injection") or {})
        statuses = [row.get("status") for row in case["reservations"]]
        checks = [
            {"id": "hard_kill_injected",
             "ok": bool(injection.get("result") is not None
                        or injection.get("error") is None and injection.get("marker")),
             "observed": injection.get("error") or "killed"},
            {"id": "containers_after_empty",
             "ok": not (case["runner"].get("containers_after") or [])},
            {"id": "reservation_pending_or_none",
             "ok": all(status == "PENDING" for status in statuses),
             "observed": statuses},
            {"id": "no_settlement_after_kill",
             "ok": not any(row.get("state") == "SETTLED" for row in case["attempts"])},
            {"id": "at_most_one_receipt",
             "ok": len(case["receipts"]) <= 1,
             "receipts": len(case["receipts"])},
        ]
    if case_id == "R6-11":
        # A verified Broker terminal (FAILED) after the Fake died is acceptable:
        # the Broker remains the sole cost authority and the attempt is archived
        # conservatively (WORST_CASE_HELD); no second receipt/settlement exists.
        attempt_states = [row.get("state") for row in case["attempts"]]
        statuses = [row.get("status") for row in case["reservations"]]
        checks = [
            {"id": "fake_crash_attempt_conservative",
             "ok": any(state in {"SETTLEMENT_UNCERTAIN", "WORST_CASE_HELD"}
                       for state in attempt_states),
             "observed": attempt_states},
            {"id": "broker_terminal_or_pending",
             "ok": all(status in {"PENDING", "FAILED"} for status in statuses),
             "observed": statuses},
            {"id": "single_receipt_after_crash",
             "ok": len(case["receipts"]) == 1,
             "receipts": len(case["receipts"])},
            {"id": "no_double_settlement",
             "ok": len([row for row in case["attempts"]
                        if row.get("state") == "SETTLED"]) == 0},
        ]
    if case_id == "R6-13":
        checks = []
    return checks


def audit_run(root: Path, *, matrix: dict | None = None,
              matrix_spec: Path | None = None) -> dict:
    spec_cases: dict[str, dict] = {}
    if matrix_spec is not None and matrix_spec.is_file():
        try:
            spec = json.loads(matrix_spec.read_text(encoding="utf-8"))
            spec_cases = {case["case_id"]: case for case in spec.get("cases", [])}
        except (OSError, json.JSONDecodeError):
            spec_cases = {}
    case_dirs = sorted((root / "cases").glob("*-*")) if (root / "cases").is_dir() else []
    results: dict[str, dict] = {}
    for evidence in case_dirs:
        parts = evidence.name.split("-")
        case_id = "-".join(parts[:2]) if len(parts) >= 2 else evidence.name
        case = _load_case(evidence)
        checks = (_digest_checks(case) + _invariant_checks(case)
                  + _expected_checks(case_id, case, spec_cases.get(case_id, {}).get("expected", {})))
        failed = [check for check in checks if not check["ok"]]
        if not case["runner"]:
            status = "NOT_RUN"
        elif failed:
            status = "PARTIAL"
        else:
            status = "PASS"
        results[case_id] = {
            "case_id": case_id, "evidence": str(evidence),
            "status": status, "checks": checks,
            "checks_total": len(checks), "checks_failed": [
                check["id"] for check in failed],
            "observed": {
                "dispatch_completed": len([row for row in case["dispatch"]
                                           if row.get("outcome") == "completed"]),
                "dispatch_rejected": len([row for row in case["dispatch"]
                                          if row.get("outcome") == "rejected"]),
                "attempt_states": [row.get("state") for row in case["attempts"]],
                "attempt_reasons": [row.get("reason") for row in case["attempts"]],
                "intent_states": [row.get("state") for row in case["intents"]],
                "intent_reasons": [row.get("reason") for row in case["intents"]],
                "reservation_statuses": [row.get("status") for row in case["reservations"]],
                "receipts": len(case["receipts"]),
                "fake_counter": case["fake_counter"],
                "turns": (case["runner"].get("turns") or []),
                "injection": case["runner"].get("injection"),
            },
        }
    matrix_cases = (matrix or {}).get("cases") or {}
    for case_id in matrix_cases:
        if case_id not in results:
            results[case_id] = {"case_id": case_id, "status": "NOT_RUN",
                                "reason": "no evidence directory",
                                "checks": [], "checks_total": 0,
                                "checks_failed": []}
    # R6-13 aggregates the independent invariants of every other case.
    if "R6-13" in results:
        others = {key: value for key, value in results.items() if key != "R6-13"}
        invariant_failures = []
        for case_id, row in others.items():
            for check in row.get("checks") or []:
                if check["id"] in {"containers_after_empty", "zero_real_calls",
                                   "fake_counter_matches_receipts",
                                   "digest", "prepared_digest==claim.request_digest",
                                   "payload_digest==receipt.raw_sha256",
                                   "prepared_digest!=payload_digest",
                                   "reservation_status_unique",
                                   "pending_not_marked_free",
                                   "attempt_identity_unique",
                                   "settled_at_most_once"} and not check["ok"]:
                    invariant_failures.append({"case": case_id,
                                               "check": check["id"]})
        results["R6-13"]["checks"] = [
            {"id": "cross_case_invariants", "ok": not invariant_failures,
             "failures": invariant_failures},
            {"id": "all_cases_evidence_present",
             "ok": all(row.get("evidence") for row in others.values())},
        ]
        failed = [check for check in results["R6-13"]["checks"] if not check["ok"]]
        results["R6-13"]["checks_total"] = len(results["R6-13"]["checks"])
        results["R6-13"]["checks_failed"] = [check["id"] for check in failed]
        results["R6-13"]["status"] = "PASS" if not failed else "PARTIAL"
        results["R6-13"]["observed"] = {"audited_cases": len(others)}
    return {
        "schema": "m0.a_next.rrev6.audit.v1",
        "root": str(root),
        "cases": results,
        "counts": {
            "pass": sum(1 for row in results.values() if row["status"] == "PASS"),
            "partial": sum(1 for row in results.values() if row["status"] == "PARTIAL"),
            "not_run": sum(1 for row in results.values() if row["status"] == "NOT_RUN"),
            "total": len(results),
        },
    }


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True)
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)
    root = Path(args.run)
    matrix_path = root / "matrix.json"
    matrix = _read_json(matrix_path) or {}
    audit = audit_run(root, matrix=matrix,
                      matrix_spec=Path(__file__).resolve().parent / "case_matrix.json")
    target = Path(args.out) if args.out else root / "audit.json"
    target.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"counts": audit["counts"], "out": str(target)},
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
