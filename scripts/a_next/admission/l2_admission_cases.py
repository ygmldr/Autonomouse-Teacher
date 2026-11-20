#!/usr/bin/env python3
"""A-NEXT A2 L2 admission-case runner (test-only; invoked by the A-PR3 window).

This script does **not** start a container, a DSH process, a Provider or a
network connection.  It is the admission-layer case driver that the A-PR3
R-REV6 exclusive-window runner can call to produce the ``A2-01..A2-03``
evidence with real trusted files.  Each case is executed through
``trusted_launcher.py --dry-run`` in a subprocess (so the Run admission is
consumed/denied by a real launcher process, and no Controller/Broker is
started).

Cases (expected statuses are fixed and asserted):

* ``A2-01`` first use on a fresh Run state -> ``ALLOW`` and ``consumed=YES``;
* ``A2-02`` restart of the same Run (same Admission, same use log) ->
  ``DENY`` with ``RUN_ADMISSION_ALREADY_CONSUMED`` and ``consumed=NO``;
* ``A2-03`` a different Run (different Admission document) reusing the same
  authorization -> ``DENY`` with ``RUN_ADMISSION_EPOCH_MISMATCH``.

Config (absolute paths only):

    {
      "launcher_config": "/abs/launcher-config.json",
      "output_dir": "/abs/evidence-dir",
      "new_run": {
        "admission_path": "/abs/admission-run2.json"
      }
    }

A-PR3 should invoke this from inside its exclusive-window runner and keep the
written ``a2-admission-cases.jsonl`` in the run evidence root.  In this PR the
script is only executed by host tests with synthetic fixtures; the real L2
evidence remains ``NOT_RUN`` until the A-PR3 window runs it.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

REPO = Path(__file__).resolve().parents[3]
LAUNCHER = REPO / "scripts" / "a_next" / "admission" / "trusted_launcher.py"

CASES = ("A2-01", "A2-02", "A2-03")


def _load_config(path: Path) -> dict:
    if not path.is_absolute():
        raise SystemExit("config path must be absolute")
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or set(document) != {
            "launcher_config", "output_dir", "new_run"}:
        raise SystemExit("config fields are invalid")
    for key in ("launcher_config", "output_dir"):
        value = document[key]
        if not isinstance(value, str) or not value.startswith("/"):
            raise SystemExit(f"{key} must be an absolute path")
    new_run = document["new_run"]
    if not isinstance(new_run, dict) or set(new_run) != {"admission_path"}:
        raise SystemExit("new_run fields are invalid")
    if not isinstance(new_run["admission_path"], str) or not new_run[
            "admission_path"].startswith("/"):
        raise SystemExit("new_run.admission_path must be an absolute path")
    return document


def _launcher_config(base: dict, override: dict | None) -> dict:
    config = dict(base)
    if override:
        config.update(override)
    return config


def _run_case(name: str, config: dict, output_dir: Path) -> dict:
    config_path = output_dir / f"{name.lower()}-launcher.json"
    config_path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    completed = subprocess.run(
        [sys.executable, str(LAUNCHER), "--config", str(config_path), "--dry-run"],
        capture_output=True, text=True)
    result: dict[str, object] = {
        "case_id": name,
        "exit_code": completed.returncode,
        "stdout": completed.stdout.strip()[:2000],
        "stderr": completed.stderr.strip()[:2000],
    }
    try:
        result["document"] = json.loads(completed.stdout)
    except json.JSONDecodeError:
        result["document"] = None
    return result


def _check(name: str, result: dict) -> tuple[bool, str]:
    document = result.get("document") or {}
    status = document.get("status")
    code = document.get("code")
    consumed = document.get("consumed")
    if name == "A2-01":
        ok = result["exit_code"] == 0 and status == "ALLOW" and consumed == "YES"
        return ok, f"expected ALLOW/YES, got {status}/{consumed}/{code}"
    if name == "A2-02":
        ok = (result["exit_code"] == 20 and status == "DENY"
              and code == "RUN_ADMISSION_ALREADY_CONSUMED" and consumed == "NO")
        return ok, f"expected ALREADY_CONSUMED, got {status}/{consumed}/{code}"
    if name == "A2-03":
        ok = (result["exit_code"] == 20 and status == "DENY"
              and code == "RUN_ADMISSION_EPOCH_MISMATCH" and consumed == "NO")
        return ok, f"expected EPOCH_MISMATCH, got {status}/{consumed}/{code}"
    return False, f"unknown case {name}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--case", choices=(*CASES, "all"), default="all")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args(argv)
    if args.list:
        for name in CASES:
            print(name)
        return 0
    document = _load_config(Path(args.config))
    output_dir = Path(document["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    base = json.loads(Path(document["launcher_config"]).read_text(encoding="utf-8"))
    selected = CASES if args.case == "all" else (args.case,)
    evidence_path = output_dir / "a2-admission-cases.jsonl"
    failures = 0
    with evidence_path.open("w", encoding="utf-8") as evidence:
        for name in selected:
            override = None
            if name == "A2-02":
                override = {}
            elif name == "A2-03":
                override = dict(document["new_run"])
            elif name == "A2-01":
                use_log = Path(base["use_log_dir"])
                if use_log.exists() and any(use_log.iterdir()):
                    raise SystemExit("A2-01 requires an empty use_log_dir")
                if Path(base["journal_path"]).exists():
                    raise SystemExit("A2-01 requires a fresh journal_path")
            result = _run_case(name, _launcher_config(base, override), output_dir)
            ok, note = _check(name, result)
            result["expected"] = note
            result["matched"] = ok
            evidence.write(json.dumps(result, sort_keys=True) + "\n")
            print(json.dumps({"case_id": name, "matched": ok, "note": note,
                              "exit_code": result["exit_code"]}, sort_keys=True))
            if not ok:
                failures += 1
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
