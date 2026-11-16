"""B3 crash-reconcile helper: reopen a crashed Controller /work DB in a new process."""
from __future__ import annotations
import json
from pathlib import Path
import sqlite3
import sys
import time

sys.path.insert(0, "/probe/src")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

SEED = Path("/seed/work")
EVIDENCE = Path("/evidence")


def query(path: Path) -> dict:
    if not path.exists():
        return {}
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        rows = [dict(row) for row in con.execute(
            "SELECT attempt_id,call_id,reservation_id,state,reason,receipt_id FROM g3b_attempts")]
        return {"attempts": rows, "states": [row["state"] for row in rows]}
    finally:
        con.close()


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    target_root = Path("/work") / "g3b"
    target_root.mkdir(parents=True, exist_ok=True)
    for path in SEED.rglob("*"):
        if path.is_file():
            rel = path.relative_to(SEED)
            target = target_root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(path.read_bytes())
    # Fresh admission for the restarted process; the persisted old admission,
    # attempts and broker DB are intentionally kept.
    common.write_configs(run_id="g3b-b3prep-reconcile")
    before = query(common.BASE / "attempts.sqlite3")
    controller = common.start_controller()
    try:
        common.wait_socket()
        time.sleep(0.6)
    finally:
        common.stop_controller(controller)
    after = query(common.BASE / "attempts.sqlite3")
    receipts = len(list((common.BASE / "receipts").glob("rcpt-*.json")))
    counter = (common.BASE / "receipts" / "received-count.json")
    output = {
        "utc": common.utc(),
        "before": before,
        "after": after,
        "receipts": receipts,
        "counter": json.loads(counter.read_text())["count"] if counter.exists() else 0,
        "controller_exit": controller.poll(),
    }
    common.collect_evidence(EVIDENCE, label="b3prep-reconcile")
    (EVIDENCE / "reconcile-result.json").write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"kind": "reconcile", **output}, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
