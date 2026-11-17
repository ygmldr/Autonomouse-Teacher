#!/usr/bin/env python3.11 -B
"""In-container G3-C two-Controller cold-start probe (P2-1 helper).

This file is copied by ``scripts/g3c/reproduce-coldstart-with-src-overlay.sh``
into the temporary stage copy as ``/probe/run_c3/coldstart_overlay_probe.py``.
It is **not** product code: the repository copy is only a helper that the
wrapper copies into a throw-away overlay, and the in-container copy writes
only to ``/tmp`` and the bind-mounted ``/evidence`` directory.

It starts two real Controller processes against one cold ``AttemptJournal``
and one socket path, at the same instant, then checks the frozen P1-2
behaviour:

  * exactly one winner and one controlled loser (exit 5,
    ``CONTROLLER_SINGLETON_LOCKED``);
  * no Python traceback from either process;
  * one valid request finishes (no error frame);
  * Fake counter == 1, one receipt, one durable Attempt in ``SETTLED``,
    one reservation ``OK``, one claim ``COMPLETED``, one admission;
  * winner exits 0 after SIGTERM and its socket is removed.

No network is used.  The Controller/Broker/Fake children are the same ones
used by the frozen ``run_c3`` harness; only the imported ``src`` tree comes
from the overlay (``/probe/src``), not from the stale frozen stage.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

PROBE_DIR = Path(__file__).resolve().parent
PROBE_ROOT = Path(os.environ.get("G3C_PROBE_ROOT", PROBE_DIR.parent))
sys.path.insert(0, str(PROBE_ROOT / "src"))
sys.path.insert(0, "/deps")
sys.path.insert(0, str(PROBE_DIR))

from autoteacher_m0.bridge.protocol import (  # noqa: E402
    Envelope,
    canonical_payload_bytes,
    encode_envelope,
    parse_envelope,
    payload_digest,
)

ROUTE = "offline-test-only-g3b"
MODEL = "fixture-bridge-v1"
SCOPE = "fixed-offline-scope"
EXPECTED_UID = 65534
SINGLETON_CODE = "CONTROLLER_SINGLETON_LOCKED"
SINGLETON_EXIT = 5
HARD_LIMITS = {
    "soft_usd": "3",
    "hard_usd": "10",
    "per_call_usd": "0.20",
    "max_requests": 50,
    "max_input_tokens": 2500000,
    "max_output_tokens": 600000,
    "max_steps": 8,
    "max_retries": 1,
}
ADMISSION_LIMITS = {
    "max_calls": 8,
    "max_attempts": 1,
    "max_input_tokens": 2500000,
    "max_output_tokens": 1024,
    "deadline_ms": 30000,
}


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_inputs(root: Path, fake_script: Path) -> Path:
    """Write one round's admission/Broker/Controller config (Fake, no key)."""
    admission = {
        "schema": "m0.g3b.admission.v1",
        "admission_id": "a" * 32,
        "scope_id": SCOPE,
        "run_id": "g3c-coldstart-overlay",
        "synthetic": True,
        "route": {"route_id": ROUTE, "provider": ROUTE, "model": MODEL},
        "tool_schemas": [
            {"name": "skill_lookup", "sha256": "1" * 64},
        ],
        "limits": dict(ADMISSION_LIMITS),
        "fake_scenario": "ok_usage",
        "expiry_utc": "2099-01-01T00:00:00Z",
        "launcher": {
            "uid": EXPECTED_UID,
            "container": True,
            "admission_nonce": "b" * 32,
        },
    }
    (root / "admission.json").write_text(json.dumps(admission), encoding="utf-8")
    broker = {
        "v": 1,
        "synthetic": True,
        "db_path": str(root / "broker.sqlite3"),
        "scope_id": SCOPE,
        "max_messages": 64,
        "limits": dict(HARD_LIMITS),
        "routes": [
            {
                "route_id": ROUTE,
                "model": MODEL,
                "price": {
                    "version": "fixture-v1",
                    "input_per_million": "1",
                    "output_per_million": "2",
                    "cached_input_per_million": "0.5",
                    "source": "synthetic fixture",
                    "captured_at": "2026-11-16",
                },
                "known_extra_fee_usd": "0.001",
                "usage_policy": {
                    "cache_write": "input_rate",
                    "reasoning": "included_in_output",
                },
            }
        ],
    }
    (root / "broker.json").write_text(json.dumps(broker), encoding="utf-8")
    receipts = root / "receipts"
    receipts.mkdir()
    config = {
        "admission_path": str(root / "admission.json"),
        "broker_config_path": str(root / "broker.json"),
        "fake_script": str(fake_script),
        "receipt_dir": str(receipts),
        "attempt_db": str(root / "attempts.sqlite3"),
        "socket_path": str(root / "bridge.sock"),
        "python": sys.executable,
        "expected_uid": EXPECTED_UID,
    }
    config_path = root / "controller.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    return config_path


def spawn(config_path: Path) -> subprocess.Popen:
    env = {
        **os.environ,
        "PYTHONPATH": f"{PROBE_ROOT / 'src'}:/deps",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    return subprocess.Popen(
        [
            sys.executable,
            "-B",
            "-m",
            "autoteacher_m0.bridge.controller",
            "--config",
            str(config_path),
        ],
        cwd=str(PROBE_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def read_stderr(proc: subprocess.Popen) -> str:
    try:
        return proc.stderr.read() if proc.stderr is not None else ""
    except (OSError, ValueError):
        return ""


def wait_socket(path: Path, procs: list[subprocess.Popen], timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return
        if all(proc.poll() is not None for proc in procs):
            raise RuntimeError(
                "both controllers exited before binding: "
                + repr([(proc.returncode, read_stderr(proc)) for proc in procs])
            )
        time.sleep(0.005)
    raise RuntimeError(
        "controller socket did not appear: " + repr([proc.poll() for proc in procs])
    )


def wait_one(procs: list[subprocess.Popen], timeout: float = 15.0) -> subprocess.Popen:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for proc in procs:
            if proc.poll() is not None:
                return proc
        time.sleep(0.005)
    raise RuntimeError("no controller exited: " + repr([proc.poll() for proc in procs]))


def request(socket_path: Path, timeout: float = 30.0) -> list[dict]:
    document = {
        "sessionId": "g3c-coldstart",
        "provider": ROUTE,
        "model": MODEL,
        "messages": [{"role": "user", "content": "hello g3c"}],
        "tools": [],
        "system": None,
        "maxTokens": 256,
        "stream": True,
        "purpose": "conversation",
    }
    envelope = Envelope(
        v=1,
        kind="request",
        transport_id="tr-" + "c" * 32,
        seq=0,
        payload=document,
        hash=payload_digest(canonical_payload_bytes(document)),
    )
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(5)
    deadline = time.monotonic() + timeout
    while True:
        try:
            client.connect(str(socket_path))
            break
        except (FileNotFoundError, ConnectionRefusedError):
            if time.monotonic() > deadline:
                client.close()
                raise
            time.sleep(0.005)
    frames: list[dict] = []
    buffer = b""
    try:
        client.sendall(encode_envelope(envelope) + b"\n")
        while time.monotonic() < deadline:
            try:
                chunk = client.recv(65536)
            except socket.timeout:
                break
            if not chunk:
                break
            buffer += chunk
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                if not line:
                    continue
                parsed = parse_envelope(line + b"\n")
                frames.append({"kind": parsed.kind, "payload": parsed.payload})
            if frames and frames[-1]["kind"] in {"finish", "error"}:
                break
    finally:
        client.close()
    return frames


def table_count(connection: sqlite3.Connection, table: str) -> int:
    try:
        return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    except sqlite3.Error:
        return 0


def state(root: Path) -> dict:
    attempts = sqlite3.connect(root / "attempts.sqlite3")
    broker = sqlite3.connect(root / "broker.sqlite3")
    attempts.row_factory = sqlite3.Row
    broker.row_factory = sqlite3.Row
    try:
        attempt_rows = [
            dict(row)
            for row in attempts.execute(
                "SELECT attempt_id, call_id, state FROM g3b_attempts"
            )
        ]
        admissions = table_count(attempts, "g3b_admissions")
        reservations = [
            dict(row)
            for row in broker.execute(
                "SELECT reservation_id, status, cost FROM budget_reservations"
            )
        ]
        claims = [
            dict(row)
            for row in broker.execute(
                "SELECT call_id, reservation_id, status FROM budget_dispatch_claims"
            )
        ]
    finally:
        attempts.close()
        broker.close()
    counter_path = root / "receipts" / "received-count.json"
    try:
        fake_counter = int(json.loads(counter_path.read_text())["count"])
    except (OSError, ValueError, KeyError, TypeError):
        fake_counter = 0
    receipt_files = sorted((root / "receipts").glob("rcpt-*.json"))
    return {
        "attempts": attempt_rows,
        "admissions": admissions,
        "reservations": reservations,
        "claims": claims,
        "fake_counter": fake_counter,
        "receipt_files": len(receipt_files),
    }


def one_round(index: int, fake_script: Path, log_dir: Path) -> dict:
    root = Path(tempfile.mkdtemp(prefix=f"g3c-coldstart-{index:02d}-"))
    started = time.monotonic()
    record: dict = {"round": index, "started_utc": utc()}
    procs: list[subprocess.Popen | None] = [None, None]
    try:
        config = write_inputs(root, fake_script)
        barrier = threading.Barrier(3)

        def launch(slot: int) -> None:
            barrier.wait()
            procs[slot] = spawn(config)

        threads = [threading.Thread(target=launch, args=(slot,)) for slot in (0, 1)]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join()
        first, second = procs[0], procs[1]
        assert first is not None and second is not None
        pair = [first, second]
        socket_path = root / "bridge.sock"
        wait_socket(socket_path, pair)
        frames = request(socket_path)
        record["frames"] = [frame["kind"] for frame in frames]
        record["error_codes"] = [
            frame["payload"].get("code")
            for frame in frames
            if frame["kind"] == "error"
        ]
        loser = wait_one(pair)
        winner = second if loser is first else first
        record["winner"] = "proc1" if winner is first else "proc2"
        record["loser_exit"] = loser.wait(timeout=15)
        loser_stderr = read_stderr(loser)
        record["loser_stderr"] = loser_stderr.strip()
        if winner.poll() is None:
            winner.send_signal(signal.SIGTERM)
        record["winner_exit"] = winner.wait(timeout=20)
        winner_stderr = read_stderr(winner)
        record["winner_stderr"] = winner_stderr.strip()
        record["state"] = state(root)
        record["socket_exists_after"] = socket_path.exists()
        record["checks"] = {
            "one_winner": winner.returncode == 0 and loser.returncode is not None,
            "loser_exit_5": record["loser_exit"] == SINGLETON_EXIT,
            "loser_code": SINGLETON_CODE in loser_stderr,
            "no_traceback": "Traceback" not in loser_stderr
            and "Traceback" not in winner_stderr,
            "request_finished": bool(frames)
            and frames[-1]["kind"] == "finish"
            and not record["error_codes"],
            "fake_one": record["state"]["fake_counter"] == 1,
            "receipt_one": record["state"]["receipt_files"] == 1,
            "attempt_settled": len(record["state"]["attempts"]) == 1
            and record["state"]["attempts"][0]["state"] == "SETTLED",
            "reservation_ok": len(record["state"]["reservations"]) == 1
            and record["state"]["reservations"][0]["status"] == "OK",
            "claim_completed": len(record["state"]["claims"]) == 1
            and record["state"]["claims"][0]["status"] == "COMPLETED",
            "admission_one": record["state"]["admissions"] == 1,
            "winner_clean": record["winner_exit"] == 0,
            "socket_cleaned": record["socket_exists_after"] is False,
        }
        record["pass"] = all(record["checks"].values())
    except BaseException as exc:  # noqa: BLE001 - a failed round is evidence
        record["exception"] = f"{type(exc).__name__}: {exc}"
        record["traceback"] = traceback.format_exc()
        record["pass"] = False
        for slot, proc in enumerate(procs):
            if proc is not None:
                record[f"proc{slot + 1}_stderr"] = read_stderr(proc)
    finally:
        for proc in procs:
            if proc is not None and proc.poll() is None:
                try:
                    proc.kill()
                except OSError:
                    pass
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
            if proc is not None:
                for stream in (proc.stdout, proc.stderr):
                    if stream is not None:
                        stream.close()
        record["duration_ms"] = int((time.monotonic() - started) * 1000)
        record["finished_utc"] = utc()
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / f"round-{index:02d}.json").write_text(
            json.dumps(record, indent=1, sort_keys=True) + "\n", encoding="utf-8"
        )
        for key in ("loser_stderr", "winner_stderr", "proc1_stderr", "proc2_stderr"):
            if key in record:
                (log_dir / f"round-{index:02d}-{key}.txt").write_text(
                    record.get(key) or "", encoding="utf-8"
                )
        shutil.rmtree(root, ignore_errors=True)
    return record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--label", default="src-overlay")
    parser.add_argument("--fake", default=str(PROBE_ROOT / "fake" / "fake_provider.py"))
    args = parser.parse_args()
    if args.rounds < 1 or args.rounds > 50:
        parser.error("--rounds must be between 1 and 50")
    label = "".join(
        char for char in args.label if char.isalnum() or char in "._-"
    ) or "src-overlay"
    evidence = Path(args.evidence).resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    log_dir = evidence / f"coldstart-{label}-logs"
    fake_script = Path(args.fake).resolve()
    if not fake_script.is_file():
        parser.error(f"fake script not found: {fake_script}")
    started_utc = utc()
    records = []
    for index in range(1, args.rounds + 1):
        record = one_round(index, fake_script, log_dir)
        records.append(record)
        print(
            json.dumps(
                {
                    "round": index,
                    "pass": record["pass"],
                    "loser_exit": record.get("loser_exit"),
                    "winner": record.get("winner"),
                    "duration_ms": record.get("duration_ms"),
                },
                sort_keys=True,
            )
        )
    summary = {
        "rounds_requested": args.rounds,
        "rounds_completed": len(records),
        "pass": sum(1 for record in records if record.get("pass")),
        "fail": sum(1 for record in records if not record.get("pass")),
        "loser_exits": sorted(
            {record.get("loser_exit") for record in records if record.get("loser_exit") is not None}
        ),
        "loser_codes": sorted(
            {record.get("loser_stderr", "").strip() for record in records}
        ),
        "fake_counters": sorted(
            {record.get("state", {}).get("fake_counter") for record in records
             if record.get("state")}
        ),
        "attempt_states": sorted(
            {
                record["state"]["attempts"][0]["state"]
                for record in records
                if record.get("state", {}).get("attempts")
            }
        ),
        "tracebacks": sum(
            1
            for record in records
            if "Traceback" in record.get("loser_stderr", "")
            or "Traceback" in record.get("winner_stderr", "")
        ),
        "durations_ms": [record.get("duration_ms") for record in records],
    }
    document = {
        "schema": "m0.g3c.repro.coldstart-overlay.v1",
        "argv": sys.argv,
        "label": label,
        "started_utc": started_utc,
        "finished_utc": utc(),
        "impl_sha": os.environ.get("G3C_IMPL", ""),
        "probe_root": str(PROBE_ROOT),
        "rounds": records,
        "summary": summary,
    }
    target = evidence / f"coldstart-{label}-{args.rounds}.json"
    target.write_text(json.dumps(document, indent=1, sort_keys=True) + "\n",
                      encoding="utf-8")
    print("SUMMARY " + json.dumps(summary, sort_keys=True))
    return 0 if summary["fail"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
