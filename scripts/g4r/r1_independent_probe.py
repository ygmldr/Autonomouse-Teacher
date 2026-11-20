#!/usr/bin/env python3
"""G4-R R1-08: independent multiprocessing probe for single-use authorization.

This probe is deliberately *not* a pytest test: each round forks two genuinely
independent processes (separate PIDs, separate file descriptors) that race to
consume the same synthetic authorization. It reuses the ``TEST_ONLY_`` synthetic
trust fixture from ``tests/integration/g4_a/g4a_support.py`` (Ed25519 rehearsal
keys in a temporary directory); it never touches a real key, provider, model or
network. It is meant to be re-run by an independent Reviewer as its own
evidence, not as the only evidence for R1-02.

Usage (from the repository root or this worktree)::

    .venv/bin/python scripts/g4r/r1_independent_probe.py --rounds 50
    .venv/bin/python scripts/g4r/r1_independent_probe.py --rounds 50 --cross-epoch
    .venv/bin/python scripts/g4r/r1_independent_probe.py --rounds 1 --json

Exit codes: 0 = PASS (every round exactly one accepted consumer), 1 = FAIL,
2 = BLOCKED (fork unavailable / environment cannot run the probe).
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

REPO_ROOT = Path(__file__).resolve().parents[2]
G4A_SUPPORT_DIR = REPO_ROOT / "tests" / "integration" / "g4_a"
for entry in (str(REPO_ROOT / "src"), str(G4A_SUPPORT_DIR)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from autoteacher_m0.security.authorization import (  # noqa: E402
    AuthorizationRejected,
    consume_execution_authorization,
)
from g4a_support import RUN_EPOCH, TrustedFixture, base_payload  # noqa: E402

PROBE_NAME = "g4r-r1-independent-multiprocessing-probe"
SAME_EPOCH = RUN_EPOCH
CROSS_EPOCHS = ("epoch-g4r-probe-a", "epoch-g4r-probe-b")


def _round_fixture(root: Path, index: int) -> TrustedFixture:
    round_dir = root / f"round-{index:04d}"
    round_dir.mkdir()
    return TrustedFixture(round_dir)


def _round_authorization(fixture: TrustedFixture, index: int) -> str:
    payload = copy.deepcopy(base_payload(fixture.bindings.as_dict()))
    payload["authorization_id"] = f"auth-g4r-probe-{index:04d}"
    fixture.write_signed(payload)
    return payload["authorization_id"]


def _race(context, fixture: TrustedFixture, epochs: tuple[str, ...]) -> list[dict]:
    barrier = context.Barrier(len(epochs))
    queue = context.Queue()
    load_kwargs = fixture.load_kwargs()

    def worker(epoch: str) -> None:
        try:
            barrier.wait(timeout=300)
            use = consume_execution_authorization(
                use_log_dir=fixture.use_log, run_epoch=epoch, **load_kwargs)
        except AuthorizationRejected as error:
            queue.put({"kind": "rejected", "reasons": list(error.reasons),
                       "pid": os.getpid()})
        except BaseException as error:  # noqa: BLE001 - report child failures
            queue.put({"kind": "error", "error": type(error).__name__,
                       "pid": os.getpid()})
        else:
            queue.put({"kind": "accepted", "authorization_id": use.authorization_id,
                       "run_epoch": use.run_epoch, "pid": os.getpid()})

    processes = [context.Process(target=worker, args=(epoch,)) for epoch in epochs]
    for process in processes:
        process.start()
    try:
        results = [queue.get(timeout=600) for _ in processes]
    finally:
        for process in processes:
            process.join(timeout=120)
        queue.close()
        queue.join_thread()
    for process, result in zip(processes, results):
        if process.exitcode != 0:
            result["kind"] = result.get("kind", "error")
            result["exitcode"] = process.exitcode
    return results


def run_probe(rounds: int, cross_epoch: bool) -> dict:
    if not hasattr(os, "fork"):
        return {"probe": PROBE_NAME, "verdict": "BLOCKED",
                "blocked_reason": "fork start method unavailable"}
    context = multiprocessing.get_context("fork")
    epochs = CROSS_EPOCHS if cross_epoch else (SAME_EPOCH, SAME_EPOCH)
    expected_loser = ("AUTHORIZATION_EPOCH_MISMATCH" if cross_epoch
                      else "AUTHORIZATION_REPLAYED")
    root = Path(tempfile.mkdtemp(prefix="g4r-r1-probe-", dir=tempfile.gettempdir()))
    summary = {
        "probe": PROBE_NAME,
        "mode": "cross-epoch" if cross_epoch else "same-epoch",
        "rounds": rounds,
        "expected_loser_reason": expected_loser,
        "accepted_total": 0,
        "loser_expected_total": 0,
        "loser_other_total": 0,
        "errors": 0,
        "double_authorization_rounds": 0,
        "rounds_with_record": 0,
        "temp_residue_total": 0,
        "distinct_worker_pids": set(),
        "max_accepted_per_round": 0,
        "failures": [],
    }
    try:
        for index in range(rounds):
            fixture = _round_fixture(root, index)
            authorization_id = _round_authorization(fixture, index)
            results = _race(context, fixture, epochs)
            accepted = [result for result in results if result["kind"] == "accepted"]
            rejected = [result for result in results if result["kind"] == "rejected"]
            errors = [result for result in results if result["kind"] == "error"]
            summary["accepted_total"] += len(accepted)
            summary["errors"] += len(errors)
            summary["max_accepted_per_round"] = max(
                summary["max_accepted_per_round"], len(accepted))
            for result in results:
                if "pid" in result:
                    summary["distinct_worker_pids"].add(result["pid"])
            if len(accepted) != 1:
                summary["double_authorization_rounds"] += int(len(accepted) > 1)
                summary["failures"].append(
                    {"round": index, "failure": "not-exactly-one-accepted",
                     "results": results})
                continue
            loser_reasons = [tuple(result["reasons"]) for result in rejected]
            if loser_reasons == [(expected_loser,)] and not errors:
                summary["loser_expected_total"] += 1
            else:
                summary["loser_other_total"] += 1
                summary["failures"].append(
                    {"round": index, "failure": "unexpected-loser-classification",
                     "results": results})
            record = fixture.record_path(authorization_id)
            if record.is_file():
                summary["rounds_with_record"] += 1
                try:
                    parsed = json.loads(record.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    parsed = None
                if (not isinstance(parsed, dict)
                        or parsed.get("authorization_id") != authorization_id):
                    summary["failures"].append(
                        {"round": index, "failure": "corrupt-published-record"})
            summary["temp_residue_total"] += sum(
                1 for path in fixture.use_log.iterdir()
                if path.name.startswith(".use-record-tmp-"))
    finally:
        shutil.rmtree(root, ignore_errors=True)
    summary["distinct_worker_pids"] = len(summary["distinct_worker_pids"])
    pass_conditions = (
        summary["accepted_total"] == rounds
        and summary["loser_expected_total"] == rounds
        and summary["double_authorization_rounds"] == 0
        and summary["rounds_with_record"] == rounds
        and not summary["failures"]
    )
    summary["verdict"] = "PASS" if pass_conditions else "FAIL"
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rounds", type=int, default=50,
                        help="independent fork rounds (default: 50)")
    parser.add_argument("--cross-epoch", action="store_true",
                        help="each round races two different run epochs")
    parser.add_argument("--json", action="store_true",
                        help="print only the JSON summary")
    arguments = parser.parse_args(argv)
    if arguments.rounds < 1:
        parser.error("--rounds must be >= 1")
    summary = run_probe(arguments.rounds, arguments.cross_epoch)
    print(json.dumps(summary, indent=2, sort_keys=True))
    if not arguments.json:
        print(f"\nG4-R R1-08 probe verdict: {summary['verdict']}")
    return 0 if summary["verdict"] == "PASS" else (
        2 if summary["verdict"] == "BLOCKED" else 1)


if __name__ == "__main__":
    raise SystemExit(main())
