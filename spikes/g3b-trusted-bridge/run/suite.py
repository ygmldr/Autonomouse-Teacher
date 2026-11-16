"""G3-B B3-prep suite: container-only orchestration.

Default mode `smoke` proves the *integration plumbing* with an explicitly
non-DSH Python UDS stub client:
  stub client -> BridgeServer(B1) -> B2 Controller -> Broker(SQLite) -> Fake -> frames
It is NOT evidence that real DSH/SDK works and is NOT G3-B PASS.

Mode `dsh` is the B1-01 skeleton; it launches run/worker.py (real
DeepSeekHarness) but is expected to be run only after B2 is finally frozen.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
from typing import Any

sys.path.insert(0, "/probe/src")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from autoteacher_m0.bridge.protocol import Envelope, encode_envelope, parse_envelope  # noqa: E402
import common  # noqa: E402


SCENARIOS = {
    "b1-01-real-dsh-echo": {
        "status": "SKELETON_GATED",
        "owner": "task-91 (B3)",
        "requires": ["B2 final freeze", "real DSH SDK in fixed rootfs"],
        "assertions": ["ack != grant", "text/usage chunks whitelist", "one finish",
                       "Fake counter == 1", "Broker reservation+claim settled",
                       "attempt journal SETTLED", "no Key/HTTP/network"],
        "mode": "dsh",
    },
    "b1-02-tool-skill-lookup": {
        "status": "TODO",
        "requires": ["b1-01", "captured tool_schemas canonical sha256", "skill-lookup fixture"],
        "notes": "Use run/README capture procedure; never guess schema hash.",
    },
    "b2-crash-reconcile": {
        "status": "TODO",
        "requires": ["B2 crash hooks/final freeze"],
        "assertions": ["no automatic resend", "SETTLEMENT_UNCERTAIN or WORST_CASE_HELD",
                       "restart reconcile evidence", "no double fake receipt"],
        "notes": "Use B2 G3B_TEST_MODE/G3B_CRASH_HOOK only in throwaway /work DBs.",
    },
    "b2-concurrency": {
        "status": "TODO",
        "requires": ["b2 thread-safe fix", "two independent UDS clients"],
        "assertions": ["serialized journal/ledger updates", "no duplicate reservation",
                       "per-stream finish exactly once", "no cross-stream data"],
    },
    "b2-resource-limits": {
        "status": "TODO",
        "requires": ["B1 limits tests already committed"],
        "assertions": ["oversized request/response/total fail closed",
                       "depth/chunk/deadline fail closed", "no billable success"],
        "notes": "Stub UDS client only; keep B1 protocol tests as canonical unit evidence.",
    },
    "b2-guard-separate-evidence": {
        "status": "BLOCKED_ON_LEAD_APPROVAL",
        "requires": ["Lead-approved minimal reserveMode:precheck spec (O-4)"],
        "notes": "No Guard code change in B3-prep; config/guard-precheck.patch.template.yml is a placeholder.",
    },
    "b3-negative-isolation": {
        "status": "TODO",
        "requires": ["final B3"],
        "assertions": ["no Key in env/files", "no AF_INET/HTTP", "no child_process from adapter",
                       "rootfs hash restored"],
    },
}

ALLOWED_ENV = {"PATH", "HOME", "PYTHONPATH", "PYTHONDONTWRITEBYTECODE", "TMPDIR", "HOSTNAME"}
EVIDENCE = Path(os.environ.get("G3B_EVIDENCE", "/evidence"))


def emit(kind: str, **data: Any) -> None:
    print(json.dumps({"kind": kind, **data}, sort_keys=True), flush=True)


def assert_isolation() -> dict:
    extra = sorted(set(os.environ) - ALLOWED_ENV)
    assert not extra, f"unexpected env: {extra}"
    key_names = [name for name in os.environ if any(token in name.upper() for token in ("KEY", "TOKEN", "SECRET", "PASSWORD"))]
    assert key_names == [], key_names
    assert os.getuid() == 65534, os.getuid()
    assert Path("/probe").is_dir() and Path("/probe/src").is_dir() and Path("/deps").is_dir()
    return {"uid": os.getuid(), "env_names": sorted(os.environ), "key_env": key_names,
            "readonly_rootfs": "ro" in Path("/proc/mounts").read_text()}


def request_payload() -> dict:
    return {
        "sessionId": "g3b-b3prep-session-001",
        "provider": "offline-test-only-g3b",
        "model": "fixture-bridge-v1",
        "messages": [{"role": "user", "content": [{"type": "text", "text": "G3B_B3PREP_ECHO"}]}],
        "tools": [],
        "system": None,
        "maxTokens": 256,
        "stream": True,
        "purpose": None,
    }


def query_db(path: Path, query: str) -> list[dict]:
    if not path.exists():
        return []
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in conn.execute(query).fetchall()]
    finally:
        conn.close()


def smoke() -> dict:
    iso = assert_isolation()
    emitted = {"mode": "smoke", "transport": "stub UDS client (NOT real DSH)",
               "started_utc": common.utc(), "isolation": iso}
    common.write_configs(scenario="ok_usage")
    controller = common.start_controller()
    frames: list[dict] = []
    try:
        common.wait_socket()
        sock = common.socket_client()
        transport = "tr-" + os.urandom(16).hex()
        env = Envelope(1, "request", transport, 0, request_payload(), None)
        wire = encode_envelope(env) + b"\n"
        sock.sendall(wire)
        raw_frames = common.read_frames(sock)
        sock.close()
        envelopes = [parse_envelope(line) for line in raw_frames]
        frames = [{"kind": item.kind, "seq": item.seq, "payload": item.payload} for item in envelopes]
        if not envelopes or envelopes[0].kind != "ack":
            raise AssertionError("ACK_MISSING")
        error_frames = [{"kind": item.kind, "seq": item.seq, "payload": item.payload}
                        for item in envelopes if item.kind == "error"]
        if error_frames:
            raise AssertionError("CONTROLLER_ERROR:" + json.dumps(error_frames, sort_keys=True))
        ack = envelopes[0].payload
        assert ack["accepted"] is True and ack["request_id"] == transport, ack
        kinds = [item.kind for item in envelopes]
        assert "chunk" in kinds, kinds
        assert kinds.count("finish") == 1, kinds
        assert kinds[-1] == "finish", kinds
        assert all(envelopes[index].seq < envelopes[index + 1].seq for index in range(len(envelopes) - 1))
        finish = envelopes[-1].payload
        assert finish["reason"]["kind"] == "stop", finish
        emitted.update({"transport_id": transport, "frames": frames, "ack": ack,
                        "finish": finish})
    finally:
        common.stop_controller(controller)

    time.sleep(0.1)
    broker_db = common.BASE / "broker.sqlite3"
    attempts_db = common.BASE / "attempts.sqlite3"
    counter_path = common.BASE / "receipts" / "received-count.json"
    receipt_files = sorted((common.BASE / "receipts").glob("rcpt-*.json"))
    counter = json.loads(counter_path.read_text())["count"] if counter_path.exists() else 0
    receipts = [json.loads(path.read_text()) for path in receipt_files]
    attempts = query_db(attempts_db, "SELECT attempt_id,call_id,reservation_id,state,receipt_id,payload_digest FROM g3b_attempts ORDER BY created_utc")
    reservations = query_db(broker_db, "SELECT reservation_id,status,route_id,model,cost FROM budget_reservations ORDER BY rowid")
    claims = query_db(broker_db, "SELECT call_id,reservation_id,request_digest,status FROM budget_dispatch_claims ORDER BY rowid")
    assertions = {
        "fake_counter_exactly_one": counter == 1,
        "receipt_count_matches_counter": len(receipts) == counter,
        "attempt_state_settled": len(attempts) == 1 and attempts[0]["state"] == "SETTLED",
        "reservation_present": len(reservations) >= 1,
        "reservation_settled": any(row["status"] in {"OK", "SETTLED"} for row in reservations),
        "claim_present": len(claims) >= 1,
        "claim_completed": any(row["status"] == "COMPLETED" for row in claims),
        "ack_before_finish": bool(frames) and frames[0]["kind"] == "ack" and frames[-1]["kind"] == "finish",
        "no_key_env": iso["key_env"] == [],
    }
    for name, ok in assertions.items():
        if not ok:
            raise AssertionError(f"{name} failed: {name}")
    emitted.update({
        "finished_utc": common.utc(), "assertions": assertions,
        "fake_counter": counter, "receipt_count": len(receipts), "receipts": receipts,
        "attempts": attempts, "reservations": reservations, "claims": claims,
        "controller_exit": controller.poll(),
        "controller_log_bytes": (common.BASE / "controller.log").stat().st_size
        if (common.BASE / "controller.log").exists() else 0,
        "note": "stub UDS client; NOT real DSH evidence; G3-B integration plumbing only",
    })
    evidence = common.collect_evidence(EVIDENCE, label="b3prep-smoke")
    emitted["evidence"] = evidence
    (EVIDENCE / "smoke-result.json").write_text(json.dumps(emitted, indent=2, sort_keys=True) + "\n")
    return emitted


def dsh() -> dict:
    """B1-01 real-DSH skeleton. Runs only after B2 is frozen."""
    if os.environ.get("G3B_ENABLE_DSH") != "1":
        raise SystemExit("DSH_MODE_DISABLED: set G3B_ENABLE_DSH=1 only after B2 final freeze")
    proc = subprocess.run(
        [sys.executable, "/probe/run/worker.py", "--mode", "dsh",
         "--evidence", str(EVIDENCE)],
        cwd="/work", env=dict(os.environ), capture_output=True, text=True, timeout=120)
    (EVIDENCE / "dsh-worker.stdout.log").write_text(proc.stdout, encoding="utf-8")
    (EVIDENCE / "dsh-worker.stderr.log").write_text(proc.stderr, encoding="utf-8")
    parsed = [json.loads(line) for line in proc.stdout.splitlines() if line.startswith("{")]
    result = next((item for item in parsed if item.get("kind") == "result"), None)
    assert result is not None, {"worker_exit": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}
    assert result.get("error") is None, result.get("error")
    assert result.get("final_response"), result
    assert result.get("finish_reason") in {"completed", "stop", "tool-calls", "max-tokens"}, result.get("finish_reason")
    return {"mode": "dsh", "worker_exit": proc.returncode, "result": result,
            "stderr_tail": proc.stderr[-4000:],
            "note": "B1-01 real-DSH path; evidence in /evidence/dsh-result.json + work/"}


def main() -> int:
    global EVIDENCE
    mode = "smoke"
    args = sys.argv[1:]
    while args:
        arg = args.pop(0)
        if arg == "--mode":
            mode = args.pop(0)
        elif arg == "--evidence":
            EVIDENCE = Path(args.pop(0))  # noqa: F811
        else:
            raise SystemExit(f"UNKNOWN_ARG:{arg}")
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    try:
        if mode == "list":
            emit("result", kind="scenario-registry", scenarios=SCENARIOS)
            return 0
        result = smoke() if mode == "smoke" else dsh()
        emit("result", **result)
        return 0
    except BaseException as error:  # noqa: BLE001 - preserve evidence before failing
        failure = {"kind": "error", "type": type(error).__name__, "message": str(error),
                   "utc": common.utc()}
        try:
            failure["frames"] = locals().get("frames")
        except Exception:
            pass
        try:
            common.collect_evidence(EVIDENCE, label="b3prep-failure")
        except BaseException:
            pass
        (EVIDENCE / "failure.json").write_text(json.dumps(failure, indent=2) + "\n")
        emit("error", failure=failure)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
