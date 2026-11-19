"""CF Judge -- isolated local execution of learner code against hidden tests.

Design contract (M1 Offline Teacher, CF Teacher line):

* ``CFJudge.evaluate(problem, hidden, code)`` executes learner ``code`` in a
  **separate local subprocess** (``sys.executable``) with a hard wall-clock
  timeout and a fresh temporary working directory.
* Grading uses **only** the ``hidden`` fixture passed by the caller.  Public
  tests (``problem["public_tests"]``) are never consulted, so tampering with a
  public test cannot change a verdict.
* Every abnormal condition fails closed (``passed=False``): syntax errors,
  import-time exceptions, a missing function, timeouts, a crashed runner or a
  malformed runner result all yield ``error`` set and ``cases_passed=0``.
* Results are deterministic for identical inputs: failure strings contain the
  case index/kind/args/expected/actual only (no timestamps, no paths) and the
  stdout excerpt is truncated deterministically.

Isolation limits (documented, not claimed as security): this is a local child
process with a timeout and temp dir, **not an OS security sandbox**.  It does
not restrict filesystem/network access of learner code; there is no container,
seccomp, namespace or user separation.  It is safe only for synthetic,
self-authored (CC0-1.0) fixtures in an offline evaluation.  See
``docs/m1/CF_TEACHER_SPEC.md``.

The judge never imports the M0 package and never calls a provider.  All fixtures
are synthetic.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from typing import Any

JUDGE_VERSION = "cf.hidden.judge.v0"

#: Default wall-clock budget for a single judged execution (contract: < 5 s).
DEFAULT_TIMEOUT_S = 3.0

#: Truncation budget for failure strings / stdout excerpts (deterministic).
_MAX_FAILURE_CHARS = 300
_MAX_STDOUT_CHARS = 400

#: Runner script executed inside the isolated subprocess.  It reads the hidden
#: test payload from stdin (so hidden expectations never sit in the temp dir),
#: imports the learner solution, executes every case and writes a JSON result
#: file.  Learner exceptions are captured **per case**; import/syntax failures
#: are fatal for the whole run (fail-closed).
_RUNNER_SOURCE = r'''
import importlib.util
import json
import sys


def canonical(value):
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)
    except (TypeError, ValueError):
        return None


def write_result(path, payload):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, sort_keys=True)


def main():
    result_path = sys.argv[1]
    try:
        payload = json.loads(sys.stdin.read())
    except Exception:
        write_result(result_path, {"status": "fatal", "fatal_error": {"type": "runner_error", "message": "unreadable stdin payload"}, "cases": []})
        return 0

    tests = payload.get("tests") or []
    function_name = payload.get("function_name") or ""
    result = {"status": "fatal", "fatal_error": None, "cases": []}

    try:
        spec = importlib.util.spec_from_file_location("m1_cf_learner_solution", "solution.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except SyntaxError as exc:
        result["fatal_error"] = {
            "type": "syntax_error",
            "message": "%s: %s (line %s)" % (type(exc).__name__, getattr(exc, "msg", exc), getattr(exc, "lineno", "?")),
        }
        write_result(result_path, result)
        return 0
    except BaseException as exc:
        result["fatal_error"] = {
            "type": "import_error",
            "message": "%s: %s" % (type(exc).__name__, str(exc)[:200]),
        }
        write_result(result_path, result)
        return 0

    function = getattr(module, function_name, None)
    if not callable(function):
        result["fatal_error"] = {
            "type": "missing_function",
            "message": "learner code does not define callable %r" % (function_name,),
        }
        write_result(result_path, result)
        return 0

    result["status"] = "ok"
    for index, case in enumerate(tests):
        kind = case.get("kind", "normal")
        args = case.get("args")
        expected = case.get("expected")
        entry = {
            "index": index,
            "kind": kind,
            "args_repr": repr(args)[:200],
            "expected_repr": repr(expected)[:200],
            "actual_repr": None,
            "exception": None,
            "passed": False,
        }
        try:
            call_args = list(args) if isinstance(args, list) else []
            actual = function(*call_args)
        except BaseException as exc:
            entry["exception"] = "%s: %s" % (type(exc).__name__, str(exc)[:200])
            result["cases"].append(entry)
            continue
        actual_json = canonical(actual)
        expected_json = canonical(expected)
        entry["actual_repr"] = repr(actual)[:200]
        entry["passed"] = actual_json is not None and expected_json is not None and actual_json == expected_json
        result["cases"].append(entry)

    write_result(result_path, result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


@dataclass
class JudgeResult:
    """Verdict of one isolated hidden-test execution.

    ``passed`` may only be true when every hidden case executed and matched.
    ``error`` is ``None`` for a completed run (even one with wrong answers) and
    one of ``syntax_error`` / ``import_error`` / ``missing_function`` /
    ``timeout`` / ``runner_error`` / ``invalid_input`` for fail-closed runs.
    """

    passed: bool
    cases_passed: int
    cases_total: int
    failures: list[str] = field(default_factory=list)
    error: str | None = None
    stdout_excerpt: str = ""


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _safe_float(value: Any, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number


class CFJudge:
    """Execute learner code in an isolated local subprocess against hidden tests."""

    def __init__(self, timeout_s: float = DEFAULT_TIMEOUT_S) -> None:
        timeout = _safe_float(timeout_s, DEFAULT_TIMEOUT_S)
        if timeout <= 0:
            raise ValueError("timeout_s must be > 0")
        self.timeout_s = timeout

    # -- public API ---------------------------------------------------------
    def evaluate(self, problem: dict, hidden: dict, code: str) -> JudgeResult:
        """Judge ``code`` against ``hidden["tests"]`` only.

        ``problem`` supplies ``function_name`` (and ``problem_id`` for a
        consistency check); ``problem["public_tests"]`` is deliberately never
        read.  Any malformed input fails closed with ``error="invalid_input"``.
        """

        tests_total, setup_error = self._validate_inputs(problem, hidden, code)
        if setup_error is not None:
            return JudgeResult(
                passed=False,
                cases_passed=0,
                cases_total=tests_total,
                failures=[],
                error=setup_error,
            )

        assert isinstance(code, str)  # narrowed by _validate_inputs
        tests: list[dict] = hidden["tests"]
        function_name: str = problem["function_name"]
        timeout = self._effective_timeout(hidden)

        work_dir = tempfile.mkdtemp(prefix="m1_cf_judge_")
        try:
            solution_path = os.path.join(work_dir, "solution.py")
            runner_path = os.path.join(work_dir, "judge_runner.py")
            result_path = os.path.join(work_dir, "judge_result.json")
            with open(solution_path, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(code)
            with open(runner_path, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(_RUNNER_SOURCE)

            payload = json.dumps(
                {"function_name": function_name, "tests": tests},
                ensure_ascii=False,
                sort_keys=True,
                allow_nan=False,
            )
            try:
                outcome = self._run_subprocess(
                    work_dir=work_dir,
                    runner_path=runner_path,
                    result_path=result_path,
                    payload=payload,
                    timeout=timeout,
                )
            except _Timeout as exc:
                return JudgeResult(
                    passed=False,
                    cases_passed=0,
                    cases_total=len(tests),
                    failures=[],
                    error="timeout",
                    stdout_excerpt=_truncate(str(exc), _MAX_STDOUT_CHARS),
                )
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

        return self._interpret(outcome, tests)

    # -- internals ----------------------------------------------------------
    @staticmethod
    def _validate_inputs(problem: dict, hidden: dict, code: str) -> tuple[int, str | None]:
        if not isinstance(problem, dict):
            return 0, "invalid_input"
        if not isinstance(hidden, dict):
            return 0, "invalid_input"
        tests = hidden.get("tests")
        if not isinstance(tests, list) or not tests:
            return 0, "invalid_input"
        if not isinstance(code, str):
            return 0, "invalid_input"
        function_name = problem.get("function_name")
        if not isinstance(function_name, str) or not function_name.strip():
            return len(tests), "invalid_input"
        problem_id = problem.get("problem_id")
        hidden_problem_id = hidden.get("problem_id")
        if (
            isinstance(problem_id, str)
            and isinstance(hidden_problem_id, str)
            and problem_id != hidden_problem_id
        ):
            return len(tests), "invalid_input"
        for case in tests:
            if not isinstance(case, dict) or "args" not in case or not isinstance(case["args"], list):
                return len(tests), "invalid_input"
        return len(tests), None

    def _effective_timeout(self, hidden: dict) -> float:
        """Per-run budget: judge ceiling, optionally lowered by the fixture."""

        hidden_timeout = _safe_float(hidden.get("timeout_s"), self.timeout_s)
        if hidden_timeout <= 0:
            hidden_timeout = self.timeout_s
        return max(0.05, min(self.timeout_s, hidden_timeout))

    @staticmethod
    def _minimal_env() -> dict[str, str]:
        env = {
            "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
            "PYTHONIOENCODING": "utf-8",
            "PYTHONHASHSEED": "0",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
        }
        for key in ("LANG", "LC_ALL", "TMPDIR"):
            if key in os.environ:
                env[key] = os.environ[key]
        return env

    def _run_subprocess(
        self,
        *,
        work_dir: str,
        runner_path: str,
        result_path: str,
        payload: str,
        timeout: float,
    ) -> "_Outcome":
        command = [sys.executable, "-I", "-B", runner_path, result_path]
        process = subprocess.Popen(
            command,
            cwd=work_dir,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=self._minimal_env(),
            start_new_session=True,
            text=True,
        )
        try:
            stdout, stderr = process.communicate(input=payload, timeout=timeout)
        except subprocess.TimeoutExpired:
            self._kill(process)
            try:
                stdout, stderr = process.communicate(timeout=1.0)
            except subprocess.TimeoutExpired:  # pragma: no cover - defensive
                stdout, stderr = "", ""
            excerpt = _truncate((stdout or "") + (stderr or ""), _MAX_STDOUT_CHARS)
            raise _Timeout(excerpt)
        excerpt = _truncate((stdout or "") + (stderr or ""), _MAX_STDOUT_CHARS)
        result_payload = None
        if os.path.exists(result_path):
            try:
                with open(result_path, encoding="utf-8") as handle:
                    result_payload = json.load(handle)
            except (OSError, json.JSONDecodeError):
                result_payload = None
        return _Outcome(
            returncode=process.returncode,
            stdout_excerpt=excerpt,
            result=result_payload,
        )

    @staticmethod
    def _kill(process: subprocess.Popen) -> None:
        try:
            if os.name == "posix":
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            else:  # pragma: no cover - POSIX is the evaluation target
                process.kill()
        except (ProcessLookupError, PermissionError):
            pass

    def _interpret(self, outcome: "_Outcome", tests: list[dict]) -> JudgeResult:
        total = len(tests)
        excerpt = outcome.stdout_excerpt
        if outcome.result is None:
            return JudgeResult(
                passed=False,
                cases_passed=0,
                cases_total=total,
                failures=[],
                error="runner_error",
                stdout_excerpt=excerpt,
            )
        payload = outcome.result
        fatal = payload.get("fatal_error")
        if isinstance(fatal, dict):
            error = str(fatal.get("type") or "runner_error")
            if error not in {"syntax_error", "import_error", "missing_function", "runner_error"}:
                error = "runner_error"
            return JudgeResult(
                passed=False,
                cases_passed=0,
                cases_total=total,
                failures=[_truncate(str(fatal.get("message", "")), _MAX_FAILURE_CHARS)],
                error=error,
                stdout_excerpt=excerpt,
            )
        cases = payload.get("cases")
        if not isinstance(cases, list) or len(cases) != total:
            return JudgeResult(
                passed=False,
                cases_passed=0,
                cases_total=total,
                failures=[],
                error="runner_error",
                stdout_excerpt=excerpt,
            )
        passed_count = 0
        failures: list[str] = []
        for position, case in enumerate(cases):
            if not isinstance(case, dict):
                failures.append(f"case-{position:02d} malformed-case")
                continue
            index = case.get("index", position)
            kind = str(case.get("kind", "normal"))
            if case.get("passed") is True:
                passed_count += 1
                continue
            prefix = f"case-{int(index) if isinstance(index, int) else position:02d} kind={kind}"
            exception = case.get("exception")
            if exception:
                message = f"{prefix} raised {exception}"
            else:
                message = (
                    f"{prefix} mismatch: args={case.get('args_repr')} "
                    f"expected={case.get('expected_repr')} actual={case.get('actual_repr')}"
                )
            failures.append(_truncate(message, _MAX_FAILURE_CHARS))
        return JudgeResult(
            passed=passed_count == total,
            cases_passed=passed_count,
            cases_total=total,
            failures=failures,
            error=None,
            stdout_excerpt=excerpt,
        )


class _Timeout(Exception):
    """Internal signal: the subprocess exceeded its wall-clock budget."""


@dataclass
class _Outcome:
    returncode: int
    stdout_excerpt: str
    result: dict | None


__all__ = ["CFJudge", "JudgeResult", "JUDGE_VERSION", "DEFAULT_TIMEOUT_S"]
