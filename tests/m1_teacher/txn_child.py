"""Test-only child process helpers for B-NEXT transaction/crash evidence.

This module is **not** a pytest test module (it does not start with ``test_``);
it is executed as a separate OS process by
``tests/m1_teacher/test_crash_recovery.py`` and
``tests/m1_teacher/test_concurrency.py`` so that crashes are produced by a real
``SIGKILL`` and so that "restart" evidence really comes from a new process
opening the same SQLite file.

Modes
-----
``submit``
    Run ``TeachingSessionEngine.submit_response`` for one pending item.
``recover``
    Run ``TeachingSessionEngine.recover_session`` for one session.
``recover-all``
    Run ``TeachingSessionEngine.recover_pending_turns`` for one learner.

Crash injection
---------------
* ``M1B_CRASH_FAILPOINT`` is passed through to the repository (see
  :mod:`m1_teacher.learner.repository`); a matching write point kills this
  process with ``SIGKILL`` (exit status ``-9`` in the parent).
* ``--kill-in-scorer`` makes the child's scorer kill itself before returning,
  which produces a real process crash in the external-scoring window between
  transaction A and transaction B (never a mock Python exception).

All data is the repository's synthetic CF fixtures; no network, no credentials,
no wall-clock assumptions are used for assertions.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import signal
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from m1_teacher import demo  # noqa: E402
from m1_teacher.contracts.types import LearnerGoal  # noqa: E402
from m1_teacher.learner.repository import SqliteRepository  # noqa: E402

_FIXTURES = _REPO_ROOT / "fixtures" / "m1_teacher"


class KillInScorer(demo.MockStudentScorer):
    """Mock scorer that kills the process before scoring (crash window B)."""

    def score(self, item, learner_id, response, *, result_id=None):  # noqa: ANN001
        os.kill(os.getpid(), signal.SIGKILL)
        raise AssertionError("unreachable: the process is killed before scoring")  # pragma: no cover


def _build_engine(db_path: Path, learner_id: str, student: str, kill_in_scorer: bool):
    components = demo.build_components(_FIXTURES)
    student_fixture = demo.load_student_fixture(components.fixtures_root, student)
    scorer = KillInScorer(student_fixture) if kill_in_scorer else demo.MockStudentScorer(student_fixture)
    repository = SqliteRepository(db_path)
    engine, history = demo._make_engine(components, repository, scorer)
    goal = LearnerGoal(
        goal_id=f"goal.{learner_id}.{components.objective.objective_id}",
        learner_id=learner_id,
        objective_id=components.objective.objective_id,
        created_at=demo.FIXED_TIMESTAMP,
    )
    return components, repository, engine, history, goal


def _wait_for_start(path: str | None, timeout_s: float = 30.0) -> None:
    if not path:
        return
    target = Path(path)
    deadline = time.monotonic() + timeout_s
    while not target.exists():
        if time.monotonic() > deadline:
            raise SystemExit("timed out waiting for the start barrier")
        time.sleep(0.005)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True)
    parser.add_argument("--learner", required=True)
    parser.add_argument("--session", required=True)
    parser.add_argument("--item", default="")
    parser.add_argument("--response", default="A")
    parser.add_argument("--result-id", default=None)
    parser.add_argument("--student", default="student_a")
    parser.add_argument(
        "--mode", choices=("submit", "recover", "recover-all"), default="submit"
    )
    parser.add_argument("--kill-in-scorer", action="store_true")
    parser.add_argument("--wait-file", default=None)
    args = parser.parse_args(argv)

    db_path = Path(args.db)
    try:
        components, repository, engine, history, goal = _build_engine(
            db_path, args.learner, args.student, args.kill_in_scorer
        )
        try:
            _wait_for_start(args.wait_file)
            if args.mode == "submit":
                result = engine.submit_response(
                    args.session,
                    args.item,
                    args.response,
                    result_id=args.result_id,
                )
                payload = {
                    "mode": "submit",
                    "result": result.to_dict(),
                    "supports_transactional_turns": engine.supports_transactional_turns,
                    "verify_rebuild": history.verify_rebuild(args.learner),
                }
            elif args.mode == "recover":
                report = engine.recover_session(args.session)
                payload = {"mode": "recover", "report": dataclasses.asdict(report)}
            else:
                reports = engine.recover_pending_turns(args.learner)
                payload = {
                    "mode": "recover-all",
                    "reports": [dataclasses.asdict(report) for report in reports],
                }
        finally:
            repository.close()
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 0
    except BaseException as exc:  # noqa: BLE001 - report a structured child failure
        code = getattr(exc, "code", type(exc).__name__)
        print(
            json.dumps(
                {"error": type(exc).__name__, "code": code, "message": str(exc)},
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 3


if __name__ == "__main__":
    sys.exit(main())
