"""Offline command-line interface for the M1-A teacher (B-PR5).

The CLI is a thin, offline wrapper over the frozen PR1-PR4 components and the
B-PR5 demo helpers:

* ``--demo`` runs the deterministic two-student closed-loop demonstration
  (identical to ``python -m m1_teacher.demo``);
* ``--student a|b|both`` runs one/both synthetic Student paths against a SQLite
  database (``--db`` or a temporary one) and prints the deterministic summary;
* ``--json`` prints machine-readable JSON, ``--write-evidence`` writes the
  reproducible JSONL evidence files.

Hard boundaries: no network, no API key, no provider call, no real learner
data; all students/outcomes are synthetic fixtures (MOCK) and the demo makes no
real teaching-effectiveness claim.
"""

# B-PR1 judge-policy note: the CLI is a demo/offline wrapper and deliberately
# exposes no flag that enables learner CODE execution.  Code-grading policy
# (trusted_fixture_only) is a trusted construction/deployment decision in
# repository tests/CI only -- never a CLI argument or request field.  The
# default remains UNTRUSTED_CODE_EXECUTION_BLOCKED.

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Sequence

from m1_teacher import demo

__all__ = ["build_parser", "main"]

_DEFAULT_PROG = "python -m m1_teacher.cli"


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""

    parser = argparse.ArgumentParser(
        prog=_DEFAULT_PROG,
        description=(
            "M1-A Offline Adaptive Teacher MVP: deterministic local demo/CLI over "
            "synthetic fixtures (no network, no API key)."
        ),
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="run the deterministic two-student closed-loop demo",
    )
    parser.add_argument(
        "--student",
        choices=("a", "b", "both"),
        default=None,
        help="run one synthetic student path (or both) instead of the full demo",
    )
    parser.add_argument(
        "--db",
        default=None,
        help="SQLite database path (default: temporary file; never printed)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print machine-readable JSON instead of the text transcript",
    )
    parser.add_argument(
        "--write-evidence",
        nargs="?",
        const=str(demo.EVIDENCE_DIR),
        default=None,
        help=(
            "write reproducible JSONL evidence under docs/m1a_evidence/ (or the given directory)"
        ),
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=demo.DEFAULT_MAX_TURNS,
        help=f"turn budget per student path (default: {demo.DEFAULT_MAX_TURNS})",
    )
    parser.add_argument(
        "--pause-after-turns",
        type=int,
        default=demo.DEFAULT_PAUSE_AFTER_TURNS,
        help=f"pause/restart turn (default: {demo.DEFAULT_PAUSE_AFTER_TURNS})",
    )
    parser.add_argument(
        "--fixtures",
        default=None,
        help="fixtures/m1_teacher root (default: repository fixtures)",
    )
    return parser


def _demo_argv(args: argparse.Namespace) -> list[str]:
    argv = [
        "--max-turns",
        str(args.max_turns),
        "--pause-after-turns",
        str(args.pause_after_turns),
    ]
    if args.json:
        argv.append("--json")
    if args.write_evidence is not None:
        argv.extend(["--write-evidence", args.write_evidence])
    if args.fixtures is not None:
        argv.extend(["--fixtures", args.fixtures])
    return argv


def _run_students(args: argparse.Namespace, students: Sequence[str]) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="m1a_cli_") as tmp:
        db_path = Path(args.db).expanduser() if args.db else Path(tmp) / "m1a_cli.sqlite"
        summaries: dict[str, Any] = {}
        for student in students:
            summaries[student] = demo.run_student_path(
                student,
                db_path=db_path,
                fixtures_root=args.fixtures,
                max_turns=args.max_turns,
                pause_after_turns=args.pause_after_turns,
            )
    scenario: dict[str, Any] = {
        "schema": "m1a.cli_run.v0",
        "contract_version": demo.CONTRACT_VERSION,
        "command": _DEFAULT_PROG,
        "fixed_timestamp": demo.FIXED_TIMESTAMP,
        "max_turns": args.max_turns,
        "pause_after_turns": args.pause_after_turns,
        "students": summaries,
        "path_differences": demo._path_differences(summaries)
        if set(summaries) == {"a", "b"}
        else None,
        "disclaimer": demo.DISCLAIMER,
    }
    return scenario


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point: returns a process exit code (0 = success)."""

    parser = build_parser()
    args = parser.parse_args(argv)
    if args.max_turns < 1 or args.pause_after_turns < 1:
        parser.error("--max-turns/--pause-after-turns must be >= 1")
    if args.pause_after_turns >= args.max_turns:
        parser.error("--pause-after-turns must be < --max-turns")

    demo_mode = args.demo or (args.student is None and args.write_evidence is not None)
    if args.demo and args.student is not None:
        parser.error("--demo and --student are mutually exclusive")
    if demo_mode:
        return demo.main(_demo_argv(args))
    if args.student is None:
        parser.print_help()
        return 0

    students = ("a", "b") if args.student == "both" else (str(args.student),)
    scenario = _run_students(args, students)
    if args.write_evidence is not None:
        evidence = demo.write_evidence(scenario, args.write_evidence)
        scenario["evidence"] = evidence
        print(f"[evidence] wrote {evidence['out_dir']}")
        for name in evidence["files"]:
            print(f"[evidence] {name} sha256={evidence['hashes'][Path(name).name]}")
    if args.json:
        print(
            json.dumps(
                demo._public_scenario(scenario), ensure_ascii=False, indent=2, sort_keys=True
            )
        )
    else:
        print(demo.render_text(scenario))
    return 0


if __name__ == "__main__":
    sys.exit(main())
