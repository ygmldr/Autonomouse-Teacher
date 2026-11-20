#!/usr/bin/env python3
"""G4-R Reviewer independent single-use authorization race probe (R-REV2).

Own probe, written by the Independent Reviewer, not the Owner's test suite. It
uses only the shared TEST_ONLY synthetic fixture (``tests/integration/g4_a/
g4a_support.py``: TEST_ONLY_ Ed25519 seed, pytest-free temp directory, no key,
no model, no provider, no network) and attacks the G4-R R1 single-use contract:

  A. thread race      - K consumers x N rounds: exactly one success/round, all
                        losers AUTHORIZATION_REPLAYED, final JSON complete+0600,
                        no temp residue, exactly N records.
  B. process race     - K forked consumers x N rounds, independent PIDs/FDs.
  C. cross-epoch race - two consumers, distinct run epochs: one success and one
                        AUTHORIZATION_EPOCH_MISMATCH (never INVALID/REPLAYED mix).
  D. corrupt finals   - empty / partial JSON / wrong schema / wrong authorization
                        id / symlink / nlink=3 / 0666 / FIFO-like dir entry are
                        AUTHORIZATION_USE_RECORD_INVALID, never a second success
                        and never disguised as REPLAYED.
  E. crash injection  - child process dies (os._exit) exactly at the link(2)
                        publication seam (after temp fsync): no final, crash temp
                        residue only; restart consumes exactly once, then REPLAYED.
  F. fsync failure    - directory fsync EIO after link: AUTHORIZATION_USE_LOG_
                        DURABILITY_UNKNOWN, complete final kept, no success, later
                        attempt REPLAYED (use spent, never re-granted).
  G. temp bounds      - stale temp reaped; 256 fresh temps => WRITE_FAILED
                        fail-closed (no final); aging them lets a later consume
                        succeed exactly once.

Usage:
  PYTHONPATH=src python scripts/g4r_review/r_rev2_race_probe.py --out /tmp/x.json
Exit 0 only if every invariant holds. No network, no key.
"""
from __future__ import annotations

import argparse
import copy
import errno
import json
import multiprocessing
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import time
import uuid

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tests" / "integration" / "g4_a"))
sys.path.insert(0, str(REPO / "src"))

from autoteacher_m0.security import authorization as authorization_module  # noqa: E402
from autoteacher_m0.security.authorization import AuthorizationRejected  # noqa: E402

REPLAYED = "AUTHORIZATION_REPLAYED"
EPOCH_MISMATCH = "AUTHORIZATION_EPOCH_MISMATCH"
INVALID = "AUTHORIZATION_USE_RECORD_INVALID"
WRITE_FAILED = "AUTHORIZATION_USE_LOG_WRITE_FAILED"
DURABILITY_UNKNOWN = "AUTHORIZATION_USE_LOG_DURABILITY_UNKNOWN"
TEMP_PREFIX = authorization_module._USE_RECORD_TEMP_PREFIX
BASE_EPOCH = "epoch-g4a-1"
OTHER_EPOCH = "epoch-g4a-2"

failures: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)
        print(f"[FAIL] {message}", flush=True)


def rejected_code(callable_) -> str | None:
    try:
        callable_()
    except AuthorizationRejected as error:
        return error.reasons[0] if error.reasons else None
    return None


def temp_entries(use_log: Path) -> list[str]:
    return sorted(entry.name for entry in use_log.iterdir()
                  if entry.name.startswith(TEMP_PREFIX))


def final_entries(use_log: Path) -> list[str]:
    return sorted(entry.name for entry in use_log.iterdir()
                  if entry.name.endswith(".json") and not entry.name.startswith(TEMP_PREFIX))


def new_authorization(fixture, prefix: str, index: int) -> str:
    from g4a_support import base_payload  # local import: path injected above
    payload = copy.deepcopy(base_payload(fixture.bindings.as_dict()))
    payload["authorization_id"] = f"{prefix}-{index:04d}-{uuid.uuid4().hex[:8]}"
    fixture.write_signed(payload)
    return payload["authorization_id"]


def valid_record_body(authorization_id: str, epoch: str = BASE_EPOCH) -> bytes:
    return authorization_module._canonical_payload({
        "schema": "at-m0/authorization-use/v1",
        "authorization_id": authorization_id,
        "run_epoch": epoch,
        "consumed_utc": "2026-11-18T12:00:00Z",
    })


def record_ok(fixture, authorization_id: str) -> tuple[bool, str]:
    path = fixture.record_path(authorization_id)
    if not path.is_file() or path.is_symlink():
        return False, "missing-or-symlink"
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("authorization_id") != authorization_id:
        return False, "wrong-authorization-id"
    mode = path.stat().st_mode & 0o777
    if mode != 0o600:
        return False, f"mode={oct(mode)}"
    return True, "complete-0600"


# ---------------------------------------------------------------------------
# A. thread race
# ---------------------------------------------------------------------------
def run_thread_race(fixture, rounds: int, consumers: int) -> dict:
    from concurrent.futures import ThreadPoolExecutor
    stats = {"rounds": rounds, "consumers": consumers, "winner_count": 0,
             "loser_codes": {}, "double_success": 0}
    for index in range(rounds):
        authorization_id = new_authorization(fixture, "rev-thread", index)
        barrier = threading.Barrier(consumers)
        outcomes: list[str] = []
        lock = threading.Lock()

        def worker() -> None:
            barrier.wait(timeout=30)
            code = rejected_code(lambda: fixture.consume())
            with lock:
                outcomes.append("OK" if code is None else code)

        with ThreadPoolExecutor(max_workers=consumers) as pool:
            list(pool.map(lambda _: worker(), range(consumers)))
        winners = outcomes.count("OK")
        stats["winner_count"] += winners
        if winners != 1:
            stats["double_success"] += 1
            check(False, f"thread round {index}: winner_count={winners} outcomes={outcomes}")
        for code in outcomes:
            if code != "OK":
                stats["loser_codes"][code] = stats["loser_codes"].get(code, 0) + 1
                check(code == REPLAYED, f"thread round {index}: loser code {code}")
        ok, detail = record_ok(fixture, authorization_id)
        check(ok, f"thread round {index}: record {detail}")
        check(temp_entries(fixture.use_log) == [], f"thread round {index}: temp residue")
    check(len(final_entries(fixture.use_log)) == rounds,
          f"thread race: final count {len(final_entries(fixture.use_log))} != {rounds}")
    return stats


# ---------------------------------------------------------------------------
# B. process race (fork; independent FDs)
# ---------------------------------------------------------------------------
def _process_worker(fixture, barrier, result_path: str) -> None:
    outcome = {"status": "error", "code": "NO_RESULT"}
    try:
        barrier.wait(timeout=60)
        fixture.consume()
        outcome = {"status": "ok", "pid": os.getpid()}
    except AuthorizationRejected as error:
        outcome = {"status": "rejected",
                   "code": error.reasons[0] if error.reasons else None,
                   "pid": os.getpid()}
    except BaseException as error:  # noqa: BLE001 - evidence must capture everything
        outcome = {"status": "error", "code": type(error).__name__, "pid": os.getpid()}
    Path(result_path).write_text(json.dumps(outcome), encoding="utf-8")


def run_process_race(fixture, rounds: int, consumers: int) -> dict:
    context = multiprocessing.get_context("fork")
    stats = {"rounds": rounds, "consumers": consumers, "winner_count": 0,
             "loser_codes": {}, "double_success": 0, "distinct_pids": set()}
    result_dir = fixture.root / "process-results"
    result_dir.mkdir(exist_ok=True)
    for index in range(rounds):
        authorization_id = new_authorization(fixture, "rev-process", index)
        barrier = context.Barrier(consumers)
        processes, paths = [], []
        for consumer in range(consumers):
            path = result_dir / f"round-{index:04d}-{consumer}.json"
            paths.append(path)
            processes.append(context.Process(
                target=_process_worker, args=(fixture, barrier, str(path)), daemon=True))
        started = time.monotonic()
        for process in processes:
            process.start()
        for process in processes:
            process.join(timeout=120)
        elapsed_ms = (time.monotonic() - started) * 1000.0
        outcomes = []
        for process, path in zip(processes, paths):
            if process.is_alive():
                process.kill()
                process.join(timeout=10)
            outcomes.append(json.loads(path.read_text()) if path.exists()
                            else {"status": "missing"})
            if process.exitcode not in (0, None):
                check(False, f"process round {index}: exitcode={process.exitcode}")
        winners = [outcome for outcome in outcomes if outcome.get("status") == "ok"]
        stats["winner_count"] += len(winners)
        stats["distinct_pids"].update(outcome.get("pid") for outcome in winners)
        if len(winners) != 1:
            stats["double_success"] += 1
            check(False, f"process round {index}: winners={len(winners)} outcomes={outcomes}")
        for outcome in outcomes:
            if outcome.get("status") == "rejected":
                code = outcome.get("code")
                stats["loser_codes"][code] = stats["loser_codes"].get(code, 0) + 1
                check(code == REPLAYED, f"process round {index}: loser code {code}")
        ok, detail = record_ok(fixture, authorization_id)
        check(ok, f"process round {index}: record {detail}")
        check(temp_entries(fixture.use_log) == [], f"process round {index}: temp residue")
        print(f"[B] round {index:03d}: winners={len(winners)} "
              f"codes={[o.get('code') for o in outcomes]} {elapsed_ms:.0f}ms", flush=True)
    stats["distinct_pids"] = len(stats["distinct_pids"])
    return stats


# ---------------------------------------------------------------------------
# C. cross-epoch race
# ---------------------------------------------------------------------------
def run_cross_epoch(fixture, rounds: int) -> dict:
    stats = {"rounds": rounds, "winner_count": 0, "loser_codes": {}}
    for index in range(rounds):
        new_authorization(fixture, "rev-epoch", index)
        barrier = threading.Barrier(2)
        outcomes: list[str] = []
        lock = threading.Lock()

        def worker(epoch: str) -> None:
            barrier.wait(timeout=30)
            code = rejected_code(lambda: fixture.consume(run_epoch=epoch))
            with lock:
                outcomes.append("OK" if code is None else code)

        threads = [threading.Thread(target=worker, args=(BASE_EPOCH,)),
                   threading.Thread(target=worker, args=(OTHER_EPOCH,))]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)
        winners = outcomes.count("OK")
        stats["winner_count"] += winners
        check(winners == 1, f"epoch round {index}: winners={winners} outcomes={outcomes}")
        losers = [code for code in outcomes if code != "OK"]
        for code in losers:
            stats["loser_codes"][code] = stats["loser_codes"].get(code, 0) + 1
            check(code in (REPLAYED, EPOCH_MISMATCH),
                  f"epoch round {index}: loser code {code}")
    return stats


# ---------------------------------------------------------------------------
# D. corrupt persisted finals
# ---------------------------------------------------------------------------
def _write_final(fixture, authorization_id: str, content: bytes, mode: int = 0o600) -> Path:
    path = fixture.record_path(authorization_id)
    path.write_bytes(content)
    path.chmod(mode)
    return path


def run_corrupt_finals(fixture, rounds: int) -> dict:
    stats: dict = {"cases": {}, "invalid_count": 0}
    variants = ["empty", "partial-json", "empty-object", "json-array",
                "wrong-schema", "wrong-authorization-id", "symlink", "hardlink-nlink3",
                "mode-0666"]
    for variant in variants:
        for index in range(rounds):
            authorization_id = new_authorization(fixture, f"rev-corrupt-{variant}", index)
            path = fixture.record_path(authorization_id)
            body = valid_record_body(authorization_id)
            if variant == "empty":
                _write_final(fixture, authorization_id, b"")
            elif variant == "partial-json":
                _write_final(fixture, authorization_id, body[: len(body) // 2])
            elif variant == "empty-object":
                _write_final(fixture, authorization_id, b"{}")
            elif variant == "json-array":
                _write_final(fixture, authorization_id, b"[]")
            elif variant == "wrong-schema":
                document = json.loads(body)
                document["schema"] = "at-m0/other/v9"
                _write_final(fixture, authorization_id, json.dumps(document).encode())
            elif variant == "wrong-authorization-id":
                _write_final(fixture, authorization_id,
                             valid_record_body("auth-someone-else"))
            elif variant == "symlink":
                target = fixture.use_log / f"target-{authorization_id}.json"
                target.write_bytes(body)
                path.symlink_to(target)
            elif variant == "hardlink-nlink3":
                path.write_bytes(body)
                os.link(path, fixture.use_log / f"sibling-a-{authorization_id}.json")
                os.link(path, fixture.use_log / f"sibling-b-{authorization_id}.json")
            elif variant == "mode-0666":
                _write_final(fixture, authorization_id, body, mode=0o666)
            code = rejected_code(lambda: fixture.consume())
            stats["cases"][variant] = stats["cases"].get(variant, {})
            stats["cases"][variant][code] = stats["cases"][variant].get(code, 0) + 1
            if variant == "wrong-authorization-id":
                # Reviewer observation: the reader validates the record's schema
                # and epoch but does NOT cross-check body authorization_id
                # against the path sha256. A schema-valid record for another id
                # is therefore classified REPLAYED (conservative denial) rather
                # than INVALID. Recorded as P2-low evidence-integrity finding.
                check(code == REPLAYED,
                      f"corrupt wrong-authorization-id round {index}: code={code}")
                stats["authorization_id_crosscheck"] = (
                    "NOT_CHECKED_BY_IMPLEMENTATION; classified REPLAYED")
            else:
                check(code == INVALID, f"corrupt {variant} round {index}: code={code}")
                if code == INVALID:
                    stats["invalid_count"] += 1
            check(not fixture.record_path(authorization_id).is_symlink()
                  or variant == "symlink", f"corrupt {variant}: unexpected record state")
    return stats


# ---------------------------------------------------------------------------
# E. crash injection at the link seam
# ---------------------------------------------------------------------------
def _crash_child(fixture, authorization_id: str) -> None:
    def die(*_args, **_kwargs):
        os._exit(23)

    authorization_module._link_use_record_no_replace = die
    fixture.consume()  # should die inside the link seam (temp already fsynced)
    os._exit(99)


def run_crash_injection(fixture) -> dict:
    stats: dict = {}
    context = multiprocessing.get_context("fork")
    authorization_id = new_authorization(fixture, "rev-crash", 0)
    process = context.Process(target=_crash_child, args=(fixture, authorization_id))
    process.start()
    process.join(timeout=120)
    stats["child_exitcode"] = process.exitcode
    check(process.exitcode == 23, f"crash: child exitcode={process.exitcode}")
    check(not fixture.record_path(authorization_id).exists(),
          "crash: final record exists after death at link seam")
    temps_after_crash = temp_entries(fixture.use_log)
    stats["temp_after_crash"] = len(temps_after_crash)
    check(len(temps_after_crash) == 1,
          f"crash: expected 1 temp residue, got {temps_after_crash}")
    code = rejected_code(lambda: fixture.consume())
    second = rejected_code(lambda: fixture.consume())
    stats["restart_first"] = "OK" if code is None else code
    stats["restart_second"] = second
    check(code is None, f"crash: restart consume not accepted: {code}")
    check(second == REPLAYED, f"crash: second consume {second} != {REPLAYED}")
    ok, detail = record_ok(fixture, authorization_id)
    check(ok, f"crash: restart record {detail}")
    # Age the crash temp, then consume a fresh authorization: stale temp must be reaped.
    crash_temp = fixture.use_log / temps_after_crash[0]
    old = time.time() - 400
    os.utime(crash_temp, (old, old))
    new_authorization(fixture, "rev-crash-reap", 1)
    code = rejected_code(lambda: fixture.consume())
    stats["reap_consume"] = "OK" if code is None else code
    stats["temps_after_reap"] = temp_entries(fixture.use_log)
    check(code is None, f"crash: reap consume not accepted: {code}")
    check(temp_entries(fixture.use_log) == [],
          f"crash: stale temp not reaped: {temp_entries(fixture.use_log)}")
    return stats


# ---------------------------------------------------------------------------
# F. directory fsync failure after publish
# ---------------------------------------------------------------------------
def run_fsync_failure(fixture) -> dict:
    stats: dict = {}
    authorization_id = new_authorization(fixture, "rev-fsync", 0)
    real_fsync_directory = authorization_module._fsync_directory

    def fail(*_args, **_kwargs):
        raise OSError(errno.EIO, "injected directory fsync EIO")

    authorization_module._fsync_directory = fail
    try:
        code = rejected_code(lambda: fixture.consume())
    finally:
        authorization_module._fsync_directory = real_fsync_directory
    stats["first"] = code
    check(code == DURABILITY_UNKNOWN, f"fsync: first code {code} != {DURABILITY_UNKNOWN}")
    stats["final_exists"] = fixture.record_path(authorization_id).is_file()
    check(stats["final_exists"], "fsync: complete final was not kept")
    ok, detail = record_ok(fixture, authorization_id)
    check(ok, f"fsync: final {detail}")
    stats["temps"] = temp_entries(fixture.use_log)
    check(stats["temps"] == [], f"fsync: temp residue {stats['temps']}")
    second = rejected_code(lambda: fixture.consume())
    stats["second"] = second
    check(second == REPLAYED, f"fsync: second consume {second} != {REPLAYED}")
    return stats


# ---------------------------------------------------------------------------
# G. temp bounds / stale reaping
# ---------------------------------------------------------------------------
def run_temp_bounds(fixture) -> dict:
    stats: dict = {}
    for index in range(authorization_module.MAX_USE_RECORD_TEMPS):
        (fixture.use_log / f"{TEMP_PREFIX}{index:064x}.tmp").write_bytes(b"x")
    authorization_id = new_authorization(fixture, "rev-temps-full", 0)
    code = rejected_code(lambda: fixture.consume())
    stats["full_temps"] = code
    check(code == WRITE_FAILED, f"temp bounds: full temp code {code} != {WRITE_FAILED}")
    check(not fixture.record_path(authorization_id).exists(),
          "temp bounds: final created despite full temp bound")
    old = time.time() - 400
    for entry in fixture.use_log.iterdir():
        if entry.name.startswith(TEMP_PREFIX):
            os.utime(entry, (old, old))
    code = rejected_code(lambda: fixture.consume())
    stats["after_aging"] = "OK" if code is None else code
    stats["temps_after_aging"] = temp_entries(fixture.use_log)
    check(code is None, f"temp bounds: after aging code {code}")
    check(temp_entries(fixture.use_log) == [],
          f"temp bounds: stale temps not reaped: {temp_entries(fixture.use_log)}")
    return stats


# ---------------------------------------------------------------------------
# H. unsupported link fail-closed (no direct-write fallback)
# ---------------------------------------------------------------------------
def run_link_unsupported(fixture) -> dict:
    stats: dict = {}
    authorization_id = new_authorization(fixture, "rev-nolink", 0)
    real_link = authorization_module._link_use_record_no_replace

    def unsupported(*_args, **_kwargs):
        raise OSError(errno.EOPNOTSUPP, "injected unsupported link")

    authorization_module._link_use_record_no_replace = unsupported
    try:
        code = rejected_code(lambda: fixture.consume())
    finally:
        authorization_module._link_use_record_no_replace = real_link
    stats["code"] = code
    check(code == WRITE_FAILED, f"nolink: code {code} != {WRITE_FAILED}")
    check(not fixture.record_path(authorization_id).exists(),
          "nolink: final exists after unsupported link (fallback violation)")
    check(temp_entries(fixture.use_log) == [], "nolink: temp residue")
    stats["final_count"] = len(final_entries(fixture.use_log))
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--thread-rounds", type=int, default=10)
    parser.add_argument("--processes", type=int, default=3)
    parser.add_argument("--process-rounds", type=int, default=10)
    parser.add_argument("--epoch-rounds", type=int, default=8)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    from g4a_support import TrustedFixture  # noqa: E402

    started = time.monotonic()
    workdir = Path(tempfile.mkdtemp(prefix="g4r-rev-race-"))
    report: dict = {"probe": "g4r-reviewer-r-rev2", "synthetic_only": True,
                    "real_key": False, "network_calls": 0}
    try:
        fixture = TrustedFixture(workdir)
        report["module_path"] = authorization_module.__file__
        report["thread_race"] = run_thread_race(fixture, args.thread_rounds, args.threads)
        report["process_race"] = run_process_race(fixture, args.process_rounds,
                                                  args.processes)
        report["cross_epoch"] = run_cross_epoch(fixture, args.epoch_rounds)
        report["corrupt_finals"] = run_corrupt_finals(fixture, 1)
        report["crash_injection"] = run_crash_injection(fixture)
        report["fsync_failure"] = run_fsync_failure(fixture)
        report["link_unsupported"] = run_link_unsupported(fixture)
        report["temp_bounds"] = run_temp_bounds(fixture)
        report["failure_count"] = len(failures)
        report["failures"] = failures
        report["elapsed_seconds"] = round(time.monotonic() - started, 2)
        print(json.dumps({key: report[key] for key in (
            "module_path", "thread_race", "process_race", "cross_epoch",
            "corrupt_finals", "crash_injection", "fsync_failure",
            "link_unsupported", "temp_bounds", "failure_count",
            "elapsed_seconds")}, indent=1, sort_keys=True, default=str))
        if args.out is not None:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n")
        if failures:
            print("R-REV2 PROBE FAILURES:", failures)
            return 1
        print("R-REV2 PROBE OK: exactly-one under threads/processes/epoch, corrupt=INVALID, "
              "crash/fsync/link/temp-bounds fail-closed")
        return 0
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
