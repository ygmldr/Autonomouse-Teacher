#!/usr/bin/env python3
"""P2-03 stress: two-process concurrent consume of one single-use authorization.

TEST_ONLY synthetic fixture (``tests/integration/g4_a/g4a_support.py``): a
``TEST_ONLY_`` Ed25519 seed mints rehearsal authorizations. No real key, no
model, no provider request, no network; every file lives under a fresh ``/tmp``
directory that is removed on exit.

Each round publishes one freshly signed authorization and then two forked
consumer processes race to consume it. For every round the script records which
side won and which stable code the loser got, then aggregates the P2-03
contract invariants:

* exactly one winner per round (``double_consume == 0``);
* loser code is the same-epoch replay code (``AUTHORIZATION_REPLAYED``);
* ``*.json`` use-record count equals the completed round count;
* no residual temporary/non-record files in the trusted use-log directory;
* every published record is mode ``0600``.

``--widen-write-ms`` injects a TEST_ONLY delay into each consumer's record-body
``os.write`` syscall so the pre-fix "record created but body not yet written"
window is observable. It never modifies the authorization implementation: on
the fixed code the delayed bytes only go to the private temporary file that is
linked into place after the complete, fsynced body exists.

Exit code 0 iff every invariant holds for every round.
"""
from __future__ import annotations

import argparse
import copy
import json
import multiprocessing
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
import traceback
import uuid

_SCRIPT_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_SCRIPT_REPO_ROOT / "tests" / "integration" / "g4_a"))
sys.path.insert(0, str(_SCRIPT_REPO_ROOT / "src"))

from autoteacher_m0.security import authorization as authorization_module  # noqa: E402
from autoteacher_m0.security.authorization import AuthorizationRejected  # noqa: E402

TEMP_PREFIX = getattr(authorization_module, "_USE_RECORD_TEMP_PREFIX", ".use-record-tmp-")


class _DelayedWriteOS:
    """os proxy: TEST_ONLY race amplifier around the record-body write syscall."""

    def __init__(self, delay_seconds: float) -> None:
        self._delay = delay_seconds

    def __getattr__(self, name: str):
        return getattr(os, name)

    def write(self, descriptor: int, data: bytes) -> int:
        time.sleep(self._delay)
        return os.write(descriptor, data)


def _consumer(fixture, barrier, result_path_text: str, widen_write_ms: float,
              run_epoch: str) -> None:
    """One competing consumer process; always writes its outcome to a JSON file."""
    result_path = Path(result_path_text)
    if widen_write_ms > 0:
        authorization_module.os = _DelayedWriteOS(widen_write_ms / 1000.0)
    outcome: dict = {"status": "error", "code": None, "detail": None}
    try:
        barrier.wait(timeout=120)
        use = fixture.consume(run_epoch=run_epoch)
        outcome = {"status": "ok", "code": None, "record_path": str(use.record_path)}
    except AuthorizationRejected as error:
        outcome = {"status": "rejected", "code": error.reasons[0] if error.reasons else None,
                   "detail": list(error.reasons)}
    except BaseException as error:  # noqa: BLE001 - evidence must capture everything
        outcome = {"status": "error", "code": type(error).__name__,
                   "detail": traceback.format_exc(limit=3)}
    result_path.write_text(json.dumps(outcome, sort_keys=True), encoding="utf-8")


def _non_record_entries(use_log: Path) -> list[str]:
    return sorted(entry.name for entry in use_log.iterdir()
                  if not entry.name.endswith(".json"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rounds", type=int, default=30,
                        help="number of concurrent consume rounds (default 30)")
    parser.add_argument("--widen-write-ms", type=float, default=0.0,
                        help="TEST_ONLY delay injected into the record-body write")
    parser.add_argument("--output", type=Path, default=None,
                        help="optional JSON report path")
    parser.add_argument("--label", default="p2-03", help="label embedded in auth ids")
    args = parser.parse_args(argv)
    if args.rounds < 1:
        parser.error("--rounds must be >= 1")

    from g4a_support import NOW, RUN_EPOCH, TrustedFixture, base_payload  # noqa: E402

    started = time.monotonic()
    workdir = Path(tempfile.mkdtemp(prefix="at-p2-03-stress-"))
    fixture = TrustedFixture(workdir)
    result_dir = workdir / "results"
    result_dir.mkdir()
    context = multiprocessing.get_context("fork")
    rounds: list[dict] = []
    failures: list[str] = []

    try:
        for index in range(args.rounds):
            authorization_id = (f"auth-{args.label}-{index:03d}-"
                                f"{uuid.uuid4().hex[:12]}")
            payload = copy.deepcopy(base_payload(fixture.bindings.as_dict()))
            payload["authorization_id"] = authorization_id
            fixture.write_signed(payload)

            barrier = context.Barrier(2)
            processes: list[multiprocessing.Process] = []
            result_paths: list[Path] = []
            for consumer_index in range(2):
                result_path = result_dir / f"round-{index:03d}-consumer-{consumer_index}.json"
                result_paths.append(result_path)
                process = context.Process(
                    target=_consumer,
                    args=(fixture, barrier, str(result_path),
                          args.widen_write_ms, RUN_EPOCH),
                    daemon=True,
                )
                processes.append(process)

            round_started = time.monotonic()
            for process in processes:
                process.start()
            for process in processes:
                process.join(timeout=180)
            round_elapsed_ms = (time.monotonic() - round_started) * 1000.0

            outcomes: list[dict] = []
            for process, result_path in zip(processes, result_paths):
                if process.is_alive():
                    process.kill()
                    process.join(timeout=10)
                if result_path.exists():
                    outcomes.append(json.loads(result_path.read_text(encoding="utf-8")))
                else:
                    outcomes.append({"status": "missing", "code": "NO_RESULT",
                                     "exitcode": process.exitcode})
            winners = [outcome for outcome in outcomes if outcome.get("status") == "ok"]
            losers = [outcome for outcome in outcomes
                      if outcome.get("status") == "rejected"]
            loser_codes = sorted(outcome.get("code") for outcome in losers)
            record_path = fixture.record_path(authorization_id)
            record_mode = None
            record_valid = False
            if record_path.is_file() and not record_path.is_symlink():
                record_mode = record_path.stat().st_mode & 0o777
                try:
                    document = json.loads(record_path.read_text(encoding="utf-8"))
                    record_valid = document.get("authorization_id") == authorization_id
                except (OSError, ValueError):
                    record_valid = False
            temp_entries = sorted(entry.name for entry in fixture.use_log.iterdir()
                                  if entry.name.startswith(TEMP_PREFIX))
            json_records = sorted(entry.name for entry in fixture.use_log.iterdir()
                                  if entry.name.endswith(".json"))
            failures_before = len(failures)
            if len(winners) != 1:
                failures.append(f"round {index}: winner_count={len(winners)} "
                                f"outcomes={[o.get('status') for o in outcomes]}")
            if len(losers) != 1:
                failures.append(f"round {index}: loser_count={len(losers)}")
            if loser_codes != ["AUTHORIZATION_REPLAYED"]:
                failures.append(f"round {index}: loser_codes={loser_codes}")
            if not record_valid:
                failures.append(f"round {index}: record_missing_or_invalid")
            if record_mode is not None and record_mode != 0o600:
                failures.append(f"round {index}: record_mode={oct(record_mode)}")
            if temp_entries:
                failures.append(f"round {index}: residual_temp={temp_entries}")
            if len(json_records) != index + 1:
                failures.append(f"round {index}: json_record_count={len(json_records)}"
                                f" expected {index + 1}")
            rounds.append({
                "round": index,
                "authorization_id": authorization_id,
                "winner_count": len(winners),
                "loser_codes": loser_codes,
                "record_valid": record_valid,
                "record_mode": None if record_mode is None else oct(record_mode),
                "temporary_files": temp_entries,
                "json_record_count": len(json_records),
                "elapsed_ms": round(round_elapsed_ms, 1),
                "ok": len(failures) == failures_before,
            })
            print(f"round {index:03d}: winners={len(winners)} loser_codes={loser_codes} "
                  f"records={len(json_records)} temp={len(temp_entries)} "
                  f"mode={oct(record_mode) if record_mode is not None else None} "
                  f"{round_elapsed_ms:.0f}ms", flush=True)

        all_records = sorted(entry for entry in fixture.use_log.iterdir()
                             if entry.name.endswith(".json"))
        modes = sorted({entry.stat().st_mode & 0o777 for entry in all_records})
        residual = _non_record_entries(fixture.use_log)
        loser_histogram: dict[str, int] = {}
        for round_entry in rounds:
            for code in round_entry["loser_codes"]:
                loser_histogram[str(code)] = loser_histogram.get(str(code), 0) + 1
        double_consume = sum(1 for round_entry in rounds
                             if round_entry["winner_count"] > 1)
        invalid_losers = sum(1 for round_entry in rounds
                             if "AUTHORIZATION_USE_RECORD_INVALID"
                             in round_entry["loser_codes"])
        report = {
            "schema": "at-m0/g4h0-p2-03-stress/v1",
            "test_only_synthetic": True,
            "real_key": False,
            "network_calls": 0,
            "utc_started": NOW.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "label": args.label,
            "rounds": args.rounds,
            "widen_write_ms": args.widen_write_ms,
            "python": sys.version.split()[0],
            "module_path": authorization_module.__file__,
            "elapsed_seconds": round(time.monotonic() - started, 2),
            "double_consume": double_consume,
            "loser_code_histogram": loser_histogram,
            "loser_invalid_count": invalid_losers,
            "record_count": len(all_records),
            "record_modes": [oct(mode) for mode in modes],
            "residual_non_record_files": residual,
            "failure_count": len(failures),
            "failures": failures,
            "rounds_detail": rounds,
        }
        print(json.dumps({key: report[key] for key in (
            "label", "rounds", "widen_write_ms", "double_consume",
            "loser_code_histogram", "loser_invalid_count", "record_count",
            "record_modes", "residual_non_record_files", "failure_count",
            "elapsed_seconds")}, sort_keys=True), flush=True)
        if args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                                   encoding="utf-8")
        if failures:
            print("FAILURES:", flush=True)
            for failure in failures:
                print("  -", failure, flush=True)
            return 1
        print("P2-03 CONTRACT OK: exactly one winner, stable replay loser, "
              "no double consume, no residual temporary files", flush=True)
        return 0
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
