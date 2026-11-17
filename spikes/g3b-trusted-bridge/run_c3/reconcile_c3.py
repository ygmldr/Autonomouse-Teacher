"""G3-C crash/reconcile helper (container only).

Copies a crashed controller's ``/seed/work`` back into ``/work/g3b``, optionally
tampers with the durable evidence to exercise C2-02D, starts a *new* Controller
process (which runs the frozen recovery order: recover attempts before consuming
the new admission), then snapshots the result without ever sending a Provider
call.
"""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import sys
import time

sys.path.insert(0, "/probe/src")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import common_c3 as common  # noqa: E402

SEED = Path("/seed/work")
EVIDENCE = Path("/evidence")
ATTEMPTS = common.BASE / "attempts.sqlite3"
RECEIPTS = common.BASE / "receipts"
TAMPER_MARKER = EVIDENCE / "tamper.json"


def _state() -> dict:
    return {
        "attempts": common.query_ro(
            ATTEMPTS,
            "SELECT attempt_id,call_id,reservation_id,state,reason,receipt_id "
            "FROM g3b_attempts ORDER BY created_utc"),
        "intents": common.query_ro(
            ATTEMPTS,
            "SELECT intent_id,call_id,reservation_id,state,reason "
            "FROM g3b_send_intents ORDER BY created_utc"),
        "admissions": common.query_ro(
            ATTEMPTS,
            "SELECT admission_id,run_id FROM g3b_admissions ORDER BY consumed_utc"),
        "receipts": sorted(path.name for path in RECEIPTS.glob("rcpt-*.json")),
        "counter": _counter(),
    }


def _counter() -> int:
    path = RECEIPTS / "received-count.json"
    try:
        return int(json.loads(path.read_text())["count"])
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        return 0


def _tamper(mode: str) -> dict:
    """Alter durable evidence after a crash, before the recovery process starts."""
    detail: dict = {"mode": mode, "changes": []}
    receipts = sorted(RECEIPTS.glob("rcpt-*.json"))
    if mode in {"receipt_usage", "receipt_nonce", "receipt_digest"}:
        if not receipts:
            detail["error"] = "NO_RECEIPT"
            return detail
        path = receipts[0]
        document = json.loads(path.read_text())
        if mode == "receipt_usage":
            usage = dict(document.get("usage") or {})
            usage["outputTokens"] = 999
            document["usage"] = usage
        elif mode == "receipt_nonce":
            document["nonce"] = "0" * 32
        else:
            document["raw_sha256"] = "f" * 64
        path.write_text(json.dumps(document, sort_keys=True, separators=(",", ":")))
        detail["changes"].append(f"{path.name}:{mode}")
        return detail
    if mode in {"journal_usage", "journal_digest"}:
        conn = sqlite3.connect(str(ATTEMPTS))
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT attempt_id,receipt_json FROM g3b_attempts "
                "WHERE receipt_json IS NOT NULL ORDER BY created_utc LIMIT 1").fetchone()
            if row is None:
                detail["error"] = "NO_RECEIPT_DOCUMENT"
                return detail
            document = json.loads(row["receipt_json"])
            if mode == "journal_usage":
                usage = dict(document.get("usage") or {})
                usage["outputTokens"] = 777
                document["usage"] = usage
            else:
                document["receipt"] = dict(document.get("receipt") or {})
                document["receipt"]["raw_sha256"] = "e" * 64
            conn.execute("UPDATE g3b_attempts SET receipt_json=? WHERE attempt_id=?",
                         (json.dumps(document, sort_keys=True), row["attempt_id"]))
            conn.commit()
            detail["changes"].append(f"{row['attempt_id']}:{mode}")
        finally:
            conn.close()
        return detail
    raise ValueError("UNKNOWN_TAMPER_MODE")


def main() -> int:
    global EVIDENCE, SEED
    mode = "none"
    run_id = "g3c-reconcile"
    limits = None
    args = sys.argv[1:]
    while args:
        arg = args.pop(0)
        if arg == "--evidence":
            EVIDENCE = Path(args.pop(0))
            common.EVIDENCE = EVIDENCE
        elif arg == "--seed":
            SEED = Path(args.pop(0))
        elif arg == "--tamper":
            mode = args.pop(0)
        elif arg == "--run-id":
            run_id = args.pop(0)
        elif arg == "--limits":
            limits = json.loads(args.pop(0))
        else:
            raise SystemExit(f"UNKNOWN_ARG:{arg}")
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    common.BASE.mkdir(parents=True, exist_ok=True)
    for path in SEED.rglob("*"):
        if path.is_file():
            target = common.BASE / path.relative_to(SEED)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(path.read_bytes())
    before = _state()
    tamper = {"mode": mode, "changes": []}
    if mode != "none":
        tamper = _tamper(mode)
    common.write_json(TAMPER_MARKER, tamper)
    # A fresh admission id is required for the new trusted recovery process; the
    # old admission is intentionally kept and must not be consumed twice.
    config = common.write_configs(run_id=run_id, scenario="ok_usage", limits=limits)
    snapshot_before_start = common.broker_and_attempts_snapshot()
    controller = common.start_controller(log_name="controller-reconcile.log")
    startup_error = None
    try:
        common.wait_socket(timeout=25)
        time.sleep(1.0)
    except Exception as exc:  # noqa: BLE001 - terminal evidence
        startup_error = {"type": type(exc).__name__, "message": str(exc)}
    finally:
        common.stop_controller(controller)
    after = _state()
    snapshot_after = common.broker_and_attempts_snapshot()
    result = {
        "utc": common.utc(), "mode": mode, "tamper": tamper,
        "run_id": run_id, "admission_id": config["admission_id"],
        "startup_error": startup_error,
        "controller_exit": controller.poll(),
        "before": before, "after": after,
        "snapshot_before_start": snapshot_before_start,
        "snapshot_after": snapshot_after,
        "receipts_after": len(list(RECEIPTS.glob("rcpt-*.json"))),
        "counter_after": _counter(),
        "correlation": common.correlation_rows(),
        "controller_log": common.trace_controller_log(EVIDENCE),
        "env": common.env_snapshot(),
    }
    common.write_json(EVIDENCE / "reconcile-result.json", result)
    common.collect_work(EVIDENCE, label="reconcile")
    print(json.dumps({"kind": "reconcile", "before": before, "after": after,
                      "tamper": tamper, "startup_error": startup_error,
                      "counter_after": result["counter_after"]}, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
