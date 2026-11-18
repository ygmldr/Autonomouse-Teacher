#!/usr/bin/env python3
"""G4-D hold-open launcher: real dual-principal run that an *external* watchdog kills.

This is a thin driver over the unmodified G4-C ``G4CLauncher``. It does the same
preflight/create/start sequence, optionally issues one real candidate probe, and
then deliberately **does not** run the in-process cleanup/evaluate path: the G4-D
external watchdog owns SIGTERM/SIGKILL, container removal, socket/run-dir
absence and conservative accounting. If this process cleaned up after itself,
the watchdog test would prove nothing.

No Key, no model, no external HTTP; containers use the frozen canonical rootfs
and ``--network none`` exactly as G4-C.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "g3d"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib_g3d as lib3d  # noqa: E402
import launch_c as base  # noqa: E402


def parse_args(argv: list[str] | None = None) -> tuple[argparse.Namespace, float, str | None]:
    parser = argparse.ArgumentParser(add_help=False, description=__doc__)
    parser.add_argument("--probe-delay", type=float, default=1.0)
    parser.add_argument("--probe-phase", default=None)
    extra, remaining = parser.parse_known_args(argv)
    return base.parse_args(remaining), extra.probe_delay, extra.probe_phase


def main(argv: list[str] | None = None) -> int:
    args, probe_delay, probe_phase = parse_args(argv)
    if os.geteuid() != 0:
        sys.stderr.write("G4D_LAUNCH_NEEDS_HOST_ROOT\n")
        return lib3d.EXIT_BLOCKED_ENVIRONMENT
    try:
        launcher = base.G4CLauncher(args)
    except lib3d.G3DError as error:
        sys.stderr.write(f"LAUNCH_D_FAILED {error.reason}: {error}\n")
        return error.exit_code
    try:
        launcher.preflight()
        launcher.create_run()
        launcher.write_configs()
        launcher.start_trusted()
        launcher.start_candidate()
    except lib3d.G3DError as error:
        sys.stderr.write(f"LAUNCH_D_FAILED {error.reason}: {error}\n")
        return error.exit_code
    launcher.write_evidence_json("run/hold-open.json", {
        "schema": "m0.g4d.hold-open.v1",
        "utc": lib3d.utc(),
        "run_id": launcher.run_id,
        "run_dir": str(launcher.run_dir),
        "trusted": launcher.trusted_name,
        "candidate": launcher.candidate_name,
        "mode": "hold-open: external watchdog owns teardown",
        "cleanup_owner": "external_watchdog",
        "evaluate_skipped": True,
        "probe_phase": probe_phase,
    })
    sys.stderr.write(json.dumps({"run_id": launcher.run_id,
                                 "run_dir": str(launcher.run_dir),
                                 "hold_open": True}) + "\n")
    if probe_phase:
        time.sleep(max(0.0, probe_delay))
        record = launcher.run_candidate_probe(probe_phase, timeout=20.0)
        launcher.write_evidence_json("run/hold-open-probe.json", record)
    while True:
        time.sleep(1.0)


if __name__ == "__main__":
    raise SystemExit(main())
