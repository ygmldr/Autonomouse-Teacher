#!/usr/bin/env python3
"""Independent audit of G4-F4 evidence (SQLite + DSH session JSONL).

This script deliberately does **not** import product code and does not trust
``checks/checks.json``.  It re-opens the evidence copies of ``broker.sqlite3``
and ``attempts.sqlite3`` read-only, re-reads the Fake receipts, parses the raw
``session.v4.jsonl`` files and cross-checks the per-request reconciliation.

Usage:
    python3 -B scripts/g4/audit_g4_f4.py \
        --run artifacts/g4f/f4/runs/resume-... \
        --run artifacts/g4f/f4/runs/crash-resume-... \
        --out artifacts/g4f/f4/audit.json
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path: str | os.PathLike[str]) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def query(path: Path, statement: str) -> list[dict]:
    if not path.is_file():
        return []
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in connection.execute(statement).fetchall()]
    finally:
        connection.close()


def decimal(value: object) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def parse_json_text(value: object) -> dict | None:
    if not isinstance(value, str):
        return None
    try:
        document = json.loads(value)
    except json.JSONDecodeError:
        return None
    return document if isinstance(document, dict) else None


def receipt_rows(folder: Path) -> list[dict]:
    rows = []
    if not folder.is_dir():
        return rows
    for path in sorted(folder.glob("rcpt-*.json")):
        document = read_json(path)
        if not isinstance(document, dict):
            rows.append({"name": path.name, "invalid": True})
            continue
        rows.append({
            "name": path.name, "sha256": sha256_file(path),
            "receipt_id": document.get("receipt_id"),
            "raw_sha256": document.get("raw_sha256"),
            "raw_length": document.get("raw_length"),
            "nonce": document.get("nonce"),
            "usage": document.get("usage"),
            "synthetic": document.get("synthetic"),
            "real_model_calls": document.get("real_model_calls"),
            "http_calls": document.get("http_calls"),
            "network_used": document.get("network_used"),
        })
    return rows


def parse_session_files(folder: Path) -> dict:
    files = []
    if not folder.is_dir():
        return {"files": files}
    for path in sorted(folder.rglob("session.v4.jsonl")):
        headers, assistants, users = [], [], []
        event_types: dict[str, int] = {}
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            kind = event.get("type")
            if isinstance(kind, str):
                event_types[kind] = event_types.get(kind, 0) + 1
            data = event.get("data") if isinstance(event.get("data"), dict) else {}
            if kind == "request/header":
                headers.append({"seq": event.get("seq"), "reason": data.get("reason")})
            elif kind == "assistant/message":
                assistants.append({"seq": event.get("seq"), "turn": data.get("turn"),
                                   "usage": data.get("usage")})
            elif kind == "user/message":
                content = data.get("content") or []
                text = " ".join(
                    block.get("text") for block in content
                    if isinstance(block, dict) and isinstance(block.get("text"), str))
                users.append({"seq": event.get("seq"),
                              "source": (data.get("source") or {}).get("kind"),
                              "text": text})
        files.append({"path": path.name, "sha256": sha256_file(path),
                      "lines": len(path.read_text(encoding="utf-8").splitlines()),
                      "headers": headers, "assistants": assistants, "users": users,
                      "event_types": event_types})
    return {"files": files}


def gate_rows(path: Path) -> dict:
    result = {"authorized": [], "consumed": [], "denied": []}
    if not path.is_file():
        return result
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            document = json.loads(line)
        except json.JSONDecodeError:
            continue
        decision = document.get("decision")
        if decision == "AUTHORIZED":
            result["authorized"].append(document)
        elif decision == "CONSUMED":
            result["consumed"].append(document)
        else:
            result["denied"].append(document)
    return result


class Audit:
    def __init__(self, run: Path) -> None:
        self.run = run
        self.checks: list[dict] = []
        self.problems: list[str] = []
        summary = read_json(run / "summary.json") or {}
        self.kind = ((summary.get("f4") or {}).get("kind") or
                     ("crash-resume" if "crash-resume" in run.name else "resume"))
        self.summary = summary

    def check(self, name: str, ok: bool, **detail: object) -> None:
        self.checks.append({"id": name, "ok": bool(ok),
                            **json.loads(json.dumps(detail, default=str))})
        if not ok:
            self.problems.append(name)

    def broker(self, name: str, statement: str) -> list[dict]:
        return query(self.run / "db" / name, statement)

    def audit(self) -> dict:
        if self.kind == "resume":
            self._audit_resume()
        else:
            self._audit_crash_resume()
        return {
            "schema": "m0.g4f.f4.audit.v1",
            "utc": utc(),
            "run": str(self.run),
            "kind": self.kind,
            "ok": not self.problems,
            "problems": self.problems,
            "checks": self.checks,
            "db_sha256": {
                "broker": sha256_file(self.run / "db" / "broker.sqlite3")
                if (self.run / "db" / "broker.sqlite3").is_file() else None,
                "attempts": sha256_file(self.run / "db" / "attempts.sqlite3")
                if (self.run / "db" / "attempts.sqlite3").is_file() else None,
            },
        }

    # -- shared DB helpers ------------------------------------------------
    def _state(self) -> dict:
        return {
            "reservations": self.broker(
                "broker.sqlite3",
                "SELECT * FROM budget_reservations ORDER BY rowid"),
            "claims": self.broker(
                "broker.sqlite3",
                "SELECT * FROM budget_dispatch_claims ORDER BY rowid"),
            "messages": self.broker(
                "broker.sqlite3",
                "SELECT * FROM budget_broker_messages ORDER BY rowid"),
            "attempts": self.broker(
                "attempts.sqlite3",
                "SELECT * FROM g3b_attempts ORDER BY logical_step"),
        }

    @staticmethod
    def _settlements(messages: Sequence[Mapping[str, object]]) -> dict:
        result = {"reserved": [], "settled": [], "failed": []}
        for row in messages:
            document = parse_json_text(row.get("response_json")) or {}
            item = {"code": document.get("code"),
                    "reservation_id": document.get("reservation_id"),
                    "cost_usd": (document.get("settlement") or {}).get("cost_usd")}
            if item["code"] == "RESERVED":
                result["reserved"].append(item)
            elif item["code"] == "SETTLED":
                result["settled"].append(item)
            elif item["code"] in {"FAILED", "RELEASED"}:
                result["failed"].append(item)
        return result

    @staticmethod
    def _totals(reservations: Sequence[Mapping[str, object]]) -> dict:
        committed = Decimal(0)
        reserved = Decimal(0)
        pending = 0
        for row in reservations:
            cost = decimal(row.get("cost"))
            if cost is None:
                continue
            committed += cost
            if row.get("status") == "PENDING":
                reserved += cost
                pending += 1
        return {"committed": format(committed, "f"),
                "reserved": format(reserved, "f"),
                "spent": format(committed - reserved, "f"),
                "pending": pending}

    def _audit_resume(self) -> None:
        state = self._state()
        receipts = receipt_rows(self.run / "receipt")
        gate = gate_rows(self.run / "run" / "g4c-send-journal.jsonl")
        counters = read_json(self.run / "receipt" / "received-count.json") or {}
        counter = counters.get("count")
        reservations = state["reservations"]
        claims = state["claims"]
        attempts = state["attempts"]
        messages = self._settlements(state["messages"])

        self.check("counts_two_each",
                   len(reservations) == 2 and len(claims) == 2
                   and len(attempts) == 2 and len(receipts) == 2 and counter == 2,
                   reservations=len(reservations), claims=len(claims),
                   attempts=len(attempts), receipts=len(receipts), counter=counter)
        self.check("all_reservations_ok",
                   all(row.get("status") == "OK" for row in reservations),
                   statuses=[row.get("status") for row in reservations])
        self.check("all_attempts_settled",
                   all(row.get("state") == "SETTLED" for row in attempts),
                   states=[row.get("state") for row in attempts])
        self.check("two_distinct_call_ids",
                   len({row.get("call_id") for row in attempts}) == 2,
                   call_ids=sorted(str(row.get("call_id")) for row in attempts))

        ordered = sorted(attempts, key=lambda row: int(row.get("logical_step") or 0))
        receipt_by_sha = {row.get("raw_sha256"): row for row in receipts}
        claim_by_call = {row.get("call_id"): row for row in claims}
        digests_ok = True
        usage_ok = True
        mapping_ok = True
        usage_rows = []
        for index, attempt in enumerate(ordered):
            claim = claim_by_call.get(attempt.get("call_id")) or {}
            receipt = receipt_by_sha.get(attempt.get("payload_digest")) or {}
            result = read_json(
                self.run / "traces" / f"dsh-result-turn{index + 1}.json") or {}
            usage = None
            summary = result.get("event_summary") or {}
            if (summary.get("assistant_messages") or []):
                usage = (summary["assistant_messages"][0].get("data_usage")
                         or summary["assistant_messages"][0].get("usage"))
            reservation = next((row for row in reservations
                                if row.get("reservation_id")
                                == attempt.get("reservation_id")), {})
            settlement = parse_json_text(reservation.get("settlement_json")) or {}
            mapped_input = (int((usage or {}).get("inputTokens") or 0)
                            + int((usage or {}).get("cacheReadTokens") or 0)
                            + int((usage or {}).get("cacheWriteTokens") or 0))
            digests_ok = digests_ok and (
                claim.get("request_digest") == attempt.get("prepared_digest")
                and receipt.get("raw_sha256") == attempt.get("payload_digest"))
            usage_ok = usage_ok and (
                isinstance(usage, dict) and usage == receipt.get("usage"))
            mapping_ok = mapping_ok and (
                reservation.get("input_used") == mapped_input
                and reservation.get("output_used") == (usage or {}).get("outputTokens")
                and settlement.get("cost_usd") == reservation.get("cost")
                and reservation.get("status") == "OK")
            usage_rows.append({
                "step": attempt.get("logical_step"),
                "call_id": attempt.get("call_id"),
                "receipt_usage": receipt.get("usage"),
                "dsh_usage": usage,
                "cost": reservation.get("cost"),
                "settlement_cost": settlement.get("cost_usd"),
                "input_used": reservation.get("input_used"),
                "mapped_input": mapped_input,
            })
        self.check("prepared_payload_digests", digests_ok)
        self.check("usage_equals_receipt", usage_ok, rows=usage_rows)
        self.check("reservation_usage_and_cost_mapping", mapping_ok)

        old_attempt = ordered[0] if ordered else {}
        phase1_db = self.run / "phases" / "turn1" / "db" / "attempts.sqlite3"
        phase1_attempts = query(phase1_db, "SELECT * FROM g3b_attempts ORDER BY logical_step")
        phase1_attempt = phase1_attempts[0] if phase1_attempts else {}
        unchanged = bool(phase1_attempt) and all(
            old_attempt.get(key) == value for key, value in phase1_attempt.items())
        self.check("old_attempt_unchanged_after_resume", unchanged,
                   phase1=phase1_attempt, final=old_attempt)
        phase1_broker = self.run / "phases" / "turn1" / "db" / "broker.sqlite3"
        phase1_res = query(phase1_broker, "SELECT * FROM budget_reservations ORDER BY rowid")
        old_res = next((row for row in reservations
                        if row.get("reservation_id")
                        == (phase1_res[0].get("reservation_id") if phase1_res else None)),
                       {})
        old_res_unchanged = bool(phase1_res) and all(
            old_res.get(key) == value for key, value in phase1_res[0].items())
        self.check("old_reservation_unchanged", old_res_unchanged,
                   phase1=phase1_res[0] if phase1_res else {}, final=old_res)
        phase1_receipts = receipt_rows(self.run / "phases" / "turn1" / "receipt")
        old_receipt = phase1_receipts[0] if phase1_receipts else {}
        final_receipt = next((row for row in receipts
                              if row.get("receipt_id") == old_receipt.get("receipt_id")),
                             {})
        self.check("old_receipt_unchanged",
                   bool(old_receipt) and old_receipt.get("sha256")
                   == final_receipt.get("sha256"),
                   old=old_receipt, final=final_receipt)

        lengths = [row.get("payload_length") for row in gate["authorized"]]
        self.check("gate_two_bindings",
                   len(gate["authorized"]) == 2 and len(gate["consumed"]) == 2
                   and not gate["denied"], authorized=len(gate["authorized"]),
                   consumed=len(gate["consumed"]), denied=len(gate["denied"]))
        self.check("gate_payload_grows",
                   len(lengths) == 2 and all(isinstance(value, int) for value in lengths)
                   and lengths[1] > lengths[0],
                   payload_lengths=lengths)
        gate_calls = {row.get("call_id") for row in gate["authorized"]}
        self.check("gate_calls_match_attempts",
                   gate_calls == {row.get("call_id") for row in attempts},
                   gate_calls=sorted(str(value) for value in gate_calls))

        session = parse_session_files(self.run / "phases" / "turn2" / "session")
        files = session.get("files") or []
        headers = [header for item in files for header in item["headers"]]
        assistants = [message for item in files for message in item["assistants"]]
        reasons = [header.get("reason") for header in headers]
        self.check("session_initial_then_resume", reasons == ["initial", "resume"],
                   reasons=reasons)
        self.check("session_two_assistant_turns",
                   sorted(message.get("turn") for message in assistants) == [1, 2],
                   turns=[message.get("turn") for message in assistants])
        session1 = parse_session_files(self.run / "phases" / "turn1" / "session")
        lines1 = sum(item["lines"] for item in session1.get("files") or [])
        lines2 = sum(item["lines"] for item in files)
        self.check("session_grew", lines2 > lines1, turn1_lines=lines1,
                   turn2_lines=lines2)

        totals = self._totals(reservations)
        committed = decimal(totals["committed"]) or Decimal(0)
        sum_cost = sum((decimal(row.get("cost")) or Decimal(0)
                        for row in reservations), Decimal(0))
        self.check("ledger_totals",
                   committed == sum_cost and totals["pending"] == 0
                   and totals["reserved"] == "0"
                   and decimal(totals["spent"]) == committed and committed > 0,
                   totals=totals)
        self.check("single_settlement_each",
                   len(messages["reserved"]) == 2 and len(messages["settled"]) == 2
                   and not messages["failed"]
                   and {row["reservation_id"] for row in messages["settled"]}
                   == {row.get("reservation_id") for row in reservations},
                   settlements=messages)
        self.check("receipts_synthetic_no_network",
                   all(row.get("synthetic") is True
                       and row.get("real_model_calls") == 0
                       and row.get("http_calls") == 0
                       and row.get("network_used") is False for row in receipts),
                   receipts=receipts)

    def _audit_crash_resume(self) -> None:
        state = self._state()
        receipts = receipt_rows(self.run / "receipt")
        gate = gate_rows(self.run / "run" / "g4c-send-journal.jsonl")
        counters = read_json(self.run / "receipt" / "received-count.json") or {}
        counter = counters.get("count") or 0
        reservations = state["reservations"]
        claims = state["claims"]
        attempts = state["attempts"]
        messages = self._settlements(state["messages"])
        self.check("counts_single_attempt_no_receipt",
                   len(attempts) == 1 and len(claims) == 1
                   and len(reservations) == 1 and not receipts and counter == 0,
                   attempts=len(attempts), claims=len(claims),
                   reservations=len(reservations), receipts=len(receipts),
                   counter=counter)
        attempt = attempts[0] if attempts else {}
        reservation = reservations[0] if reservations else {}
        self.check("attempt_uncertain_no_receipt",
                   attempt.get("state") == "SETTLEMENT_UNCERTAIN"
                   and attempt.get("receipt_id") is None
                   and attempt.get("reason") == "NO_RECEIPT_AFTER_CRASH",
                   attempt=attempt)
        self.check("reservation_pending",
                   reservation.get("status") == "PENDING"
                   and (decimal(reservation.get("cost")) or Decimal(0)) > 0
                   and reservation.get("settlement_json") is None,
                   reservation=reservation)
        phase1_db = self.run / "phases" / "turn1" / "db" / "attempts.sqlite3"
        phase1_attempts = query(phase1_db, "SELECT * FROM g3b_attempts ORDER BY logical_step")
        phase1_attempt = phase1_attempts[0] if phase1_attempts else {}
        self.check("recovery_annotated_durable_attempt",
                   bool(phase1_attempt)
                   and phase1_attempt.get("attempt_id") == attempt.get("attempt_id")
                   and phase1_attempt.get("call_id") == attempt.get("call_id")
                   and phase1_attempt.get("state") == "ATTEMPT_STARTED"
                   and attempt.get("state") == "SETTLEMENT_UNCERTAIN",
                   phase1=phase1_attempt, final=attempt)
        phase2_db = self.run / "phases" / "turn2" / "db" / "attempts.sqlite3"
        phase2_attempts = query(phase2_db, "SELECT * FROM g3b_attempts ORDER BY logical_step")
        phase2_attempt = phase2_attempts[0] if phase2_attempts else {}
        self.check("resume_did_not_rewrite_attempt",
                   bool(phase2_attempt) and all(
                       attempt.get(key) == value for key, value in phase2_attempt.items()),
                   after_recovery=phase2_attempt, final=attempt)
        self.check("one_reserve_no_settle",
                   len(messages["reserved"]) == 1
                   and not messages["settled"] and not messages["failed"],
                   settlements=messages)
        self.check("gate_no_authorization", not gate["authorized"],
                   authorized=len(gate["authorized"]))
        result = read_json(self.run / "traces" / "dsh-result-turn2.json") or {}
        resume = result.get("resume") or {}
        turn_end = (result.get("event_summary") or {}).get("turn_end") or []
        error = (turn_end[0] or {}).get("error") if turn_end else None
        self.check("resume_used_and_failed",
                   resume.get("used") is True
                   and resume.get("sdk_call") == "resume_session"
                   and result.get("finish_reason") == "error"
                   and isinstance(error, dict)
                   and error.get("message") == "G3B_BRIDGE_CONNECT_FAILED",
                   resume=resume, finish_reason=result.get("finish_reason"),
                   error=error)
        self.check("resume_no_assistant_message",
                   not ((result.get("event_summary") or {}).get("assistant_messages")),
                   summary=result.get("event_summary"))
        session_before = parse_session_files(self.run / "phases" / "turn1" / "session")
        session_after = parse_session_files(self.run / "phases" / "turn2" / "session")
        before_files = session_before.get("files") or []
        after_files = session_after.get("files") or []
        self.check("session_persisted_before_crash",
                   bool(before_files)
                   and any(user.get("source") == "user"
                           for item in before_files for user in item["users"]),
                   files=before_files)
        self.check("resume_added_no_assistant",
                   not any(message for item in after_files
                           for message in item["assistants"]),
                   files=after_files)
        totals = self._totals(reservations)
        reserved = decimal(totals["reserved"]) or Decimal(0)
        committed = decimal(totals["committed"]) or Decimal(0)
        spent = decimal(totals["spent"]) or Decimal(0)
        self.check("conservative_totals",
                   totals["pending"] == 1 and reserved > 0 and spent == 0
                   and committed == reserved and not messages["settled"],
                   totals=totals)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="append", required=True,
                        help="evidence run directory (repeatable)")
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)
    runs = [Path(item).resolve() for item in args.run]
    documents = [Audit(run).audit() for run in runs]
    document = {"schema": "m0.g4f.f4.audit-set.v1", "utc": utc(),
                "ok": all(item["ok"] for item in documents),
                "runs": documents}
    payload = json.dumps(document, indent=2, sort_keys=True) + "\n"
    if args.out:
        target = Path(args.out)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(payload, encoding="utf-8")
    else:
        sys.stdout.write(payload)
    print(json.dumps({"ok": document["ok"],
                      "runs": [{"run": item["run"], "ok": item["ok"],
                                "problems": item["problems"]}
                               for item in documents]}, sort_keys=True))
    return 0 if document["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
