"""Unit + integration tests for the B-PR1 untrusted execution worker (M1-B).

The unit tests use fake sandboxes to prove the worker never accepts hidden
expectations and always fails closed on malformed protocol output.  The
integration tests run real synthetic Python solutions inside the real bwrap
sandbox (skipped with an explicit reason when the host cannot provide it; they
never touch the network).

Evidence class: MOCK / LOCAL.
"""

from __future__ import annotations

import dataclasses
import inspect
import json
import shutil
import tempfile
import time
from pathlib import Path

import pytest

from m1_teacher.assessment.judge.protocol import (

    PROTOCOL_VERSION,
    REQUEST_FIELDS,
    WORKER_STATUS_COMPLETED,
    WORKER_STATUS_IMPORT_ERROR,
    WORKER_STATUS_INFRA_ERROR,
    WORKER_STATUS_MISSING_FUNCTION,
    WORKER_STATUS_RAISED,
    WORKER_STATUS_SYNTAX_ERROR,
    WORKER_STATUS_TIMEOUT,
    WorkerObservation,
    WorkerProtocolError,
    build_request,
    canonical_json,
    parse_worker_response,
)
from m1_teacher.assessment.judge.sandbox import (
    BwrapSandbox,
    SandboxLaunchError,
    SandboxResult,
    SandboxUnavailable,
    WORKER_PYTHON,
)
from m1_teacher.assessment.judge.worker import (
    WORK_DIR_PREFIX,
    SOLUTION_FILENAME,
    WORKER_RUNNER_FILENAME,
    UntrustedExecutionWorker,
)

from judge_os_gate import require_os_sandbox

REPO_ROOT = Path(__file__).resolve().parents[2]
CASES_PATH = REPO_ROOT / "fixtures" / "m1_teacher" / "judge" / "certification" / "cases.json"


def _load_cases() -> list:
    return json.loads(CASES_PATH.read_text(encoding="utf-8"))["cases"]


CASES = _load_cases()


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


def _sandbox_result(
    stdout: bytes = b"",
    *,
    exit_code: int | None = 0,
    timed_out: bool = False,
) -> SandboxResult:
    return SandboxResult(
        exit_code=exit_code,
        stdout=stdout,
        stderr=b"",
        timed_out=timed_out,
        elapsed_s=0.01,
        stdout_truncated=False,
        stderr_truncated=False,
    )


def _response_line(
    request_id: str,
    *,
    status: str = "COMPLETED",
    actual: str | None = "0",
    exception_type: str | None = None,
    extra: dict | None = None,
) -> bytes:
    payload = {
        "schema_version": PROTOCOL_VERSION,
        "request_id": request_id,
        "status": status,
        "actual_canonical": actual,
        "exception_type": exception_type,
        "stdout_excerpt": "",
        "stderr_excerpt": "",
    }
    if extra:
        payload.update(extra)
    return (json.dumps(payload) + "\n").encode("utf-8")


class _EchoSandbox:
    """Fake sandbox that echoes a well-formed response for the given request."""

    def __init__(self, actual: str = "0", *, exit_code: int = 0) -> None:
        self.available_calls = 0
        self.runs: list[dict] = []
        self._actual = actual
        self._exit_code = exit_code
        self.work_dir_entries: list[dict] = []
        self.work_dir_contents: list[str] = []

    def available(self) -> bool:
        self.available_calls += 1
        return True

    def run(self, work_dir, argv, timeout_s, *, stdin_data=b"", extra_env=None):
        work_path = Path(work_dir)
        self.work_dir_entries = [
            {"name": child.name, "mode": child.stat().st_mode & 0o777}
            for child in work_path.iterdir()
        ]
        self.work_dir_contents = [
            child.read_text(encoding="utf-8") for child in work_path.iterdir() if child.suffix == ".py"
        ]
        request = json.loads(bytes(stdin_data).decode("utf-8"))
        self.runs.append(
            {
                "work_dir": str(work_path),
                "exists_during_run": work_path.is_dir(),
                "argv": list(argv),
                "timeout_s": timeout_s,
                "stdin": bytes(stdin_data),
                "extra_env": extra_env,
            }
        )
        return _sandbox_result(
            _response_line(request["request_id"], actual=self._actual),
            exit_code=self._exit_code,
        )


class _StubSandbox:
    def __init__(self, *, available: bool, result=None, error: Exception | None = None) -> None:
        self._available = available
        self._result = result
        self._error = error
        self.run_calls = 0

    def available(self) -> bool:
        return self._available

    def run(self, work_dir, argv, timeout_s, *, stdin_data=b"", extra_env=None):
        self.run_calls += 1
        if self._error is not None:
            raise self._error
        return self._result


@pytest.fixture(scope="module")
def real_sandbox() -> BwrapSandbox:
    sandbox = BwrapSandbox()
    require_os_sandbox(sandbox.available())
    return sandbox


@pytest.fixture(scope="module")
def real_worker(real_sandbox: BwrapSandbox) -> UntrustedExecutionWorker:
    return UntrustedExecutionWorker(real_sandbox)


# ---------------------------------------------------------------------------
# Trust boundary: request contents
# ---------------------------------------------------------------------------


def test_worker_request_carries_only_the_single_case_input():
    sandbox = _EchoSandbox(actual="-1")
    worker = UntrustedExecutionWorker(sandbox)
    observation = worker.run_case(
        "def first_index(nums, target):\n    return -1\n",
        "first_index",
        [[1, 2, 2, 3], 2],
    )
    assert observation.status == WORKER_STATUS_COMPLETED
    assert len(sandbox.runs) == 1
    run = sandbox.runs[0]
    payload = json.loads(run["stdin"].decode("utf-8"))
    assert set(payload) == set(REQUEST_FIELDS)
    assert payload["schema_version"] == PROTOCOL_VERSION
    assert payload["function_name"] == "first_index"
    assert payload["args"] == [[1, 2, 2, 3], 2]
    assert len(run["stdin"]) <= 16 * 1024
    lowered = run["stdin"].decode("utf-8").lower()
    for forbidden in ("expected", "tests", "hidden", "verdict", "passed", "score", "result_path"):
        assert forbidden not in lowered
    assert run["argv"] == [WORKER_PYTHON, "/worker/worker_runner.py"]
    # P2-3: only fixed interpreter env under --clearenv; no host environment.
    assert run["extra_env"] == {
        "PYTHONHASHSEED": "0",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    # The private work dir must contain only the read-only runner + solution.
    entry_names = {entry["name"] for entry in sandbox.work_dir_entries}
    assert entry_names == {SOLUTION_FILENAME, WORKER_RUNNER_FILENAME}
    for entry in sandbox.work_dir_entries:
        assert entry["mode"] == 0o444
    assert any("m1b.judge.worker.v1" in content for content in sandbox.work_dir_contents)
    # Hidden expected material is never written into the worker directory.
    for content in sandbox.work_dir_contents:
        assert "SENTINEL_DO_NOT_LEAK" not in content


def test_worker_request_does_not_embed_caller_expected_values():
    sandbox = _EchoSandbox(actual="-1")
    worker = UntrustedExecutionWorker(sandbox)
    sentinel_expected = "SENTINEL_DO_NOT_LEAK_worker_request_probe"
    worker.run_case("def f():\n    return 1\n", "f", [])
    recorded = sandbox.runs[0]["stdin"].decode("utf-8")
    assert sentinel_expected not in recorded
    assert "expected" not in recorded.lower()


def test_worker_api_and_observation_have_no_verdict_surface():
    signature = inspect.signature(UntrustedExecutionWorker.run_case)
    parameter_names = set(signature.parameters)
    assert parameter_names == {"self", "code", "function_name", "args", "timeout_s"}
    for forbidden in ("expected", "tests", "hidden", "verdict", "passed", "score"):
        assert forbidden not in parameter_names
    field_names = {field.name for field in dataclasses.fields(WorkerObservation)}
    assert field_names == {
        "status",
        "actual_canonical",
        "exception_type",
        "stdout_excerpt",
        "stderr_excerpt",
        "request_id",
    }
    for forbidden in ("passed", "verdict", "score", "expected", "tests"):
        assert forbidden not in field_names


# ---------------------------------------------------------------------------
# Fail-closed behaviour
# ---------------------------------------------------------------------------


def _temp_worker_dirs() -> set:
    return {entry.name for entry in Path(tempfile.gettempdir()).iterdir() if entry.name.startswith(WORK_DIR_PREFIX)}


def test_unavailable_sandbox_returns_infra_without_executing_code():
    sandbox = _StubSandbox(available=False, error=AssertionError("must not run"))
    worker = UntrustedExecutionWorker(sandbox)
    before = _temp_worker_dirs()
    observation = worker.run_case("raise AssertionError('must not execute')\n", "f", [])
    after = _temp_worker_dirs()
    assert observation.status == WORKER_STATUS_INFRA_ERROR
    assert observation.actual_canonical is None
    assert sandbox.run_calls == 0
    assert before == after


def test_sandbox_launch_error_maps_to_infra():
    sandbox = _StubSandbox(available=True, error=SandboxLaunchError("synthetic launch failure"))
    worker = UntrustedExecutionWorker(sandbox)
    observation = worker.run_case("def f():\n    return 1\n", "f", [])
    assert observation.status == WORKER_STATUS_INFRA_ERROR
    assert sandbox.run_calls == 1


def test_sandbox_unavailable_during_run_maps_to_infra():
    sandbox = _StubSandbox(available=True, error=SandboxUnavailable("synthetic unavailable"))
    worker = UntrustedExecutionWorker(sandbox)
    observation = worker.run_case("def f():\n    return 1\n", "f", [])
    assert observation.status == WORKER_STATUS_INFRA_ERROR


def test_invalid_request_arguments_fail_closed_without_running():
    sandbox = _StubSandbox(available=True, result=_sandbox_result(_response_line("0" * 32)))
    worker = UntrustedExecutionWorker(sandbox)
    invalid_calls = [
        ("bad function name", "def f():\n    pass\n", "not a name", []),
        ("nan argument", "def f():\n    return 1\n", "f", [float("nan")]),
        ("too deep", "def f():\n    return 1\n", "f", [[[[[[1]]]]]]),
        ("bad timeout", "def f():\n    return 1\n", "f", []),
    ]
    for label, code, function_name, args in invalid_calls:
        timeout_s = 0.001 if label == "bad timeout" else None
        observation = worker.run_case(code, function_name, args, timeout_s=timeout_s)
        assert observation.status == WORKER_STATUS_INFRA_ERROR, label
    assert sandbox.run_calls == 0


def test_forged_worker_responses_map_to_infra_error():
    valid_outputs: list[bytes] = []
    wrong_id = "0" * 32
    valid_outputs.append(_response_line(wrong_id))  # request_id mismatch
    valid_outputs.append(_response_line("a" * 32, extra={"passed": True}))  # extra verdict
    valid_outputs.append(_response_line("a" * 32, extra={"verdict": "PASS"}))
    valid_outputs.append(_response_line("a" * 32, status="PASS", actual="0"))
    valid_outputs.append(_response_line("a" * 32, status="COMPLETED", actual=None))
    valid_outputs.append(_response_line("a" * 32, actual=" 0"))  # non-canonical
    valid_outputs.append(_response_line("a" * 32, status="TIMEOUT"))  # lying timeout
    valid_outputs.append(b'{"schema_version":"m1b.judge.worker.v1","schema_version":"x"}\n')
    valid_outputs.append(_response_line("a" * 32) + _response_line("a" * 32))  # multi-line
    valid_outputs.append(b"not-json\n")
    valid_outputs.append(b"")
    valid_outputs.append(b"x" * (20 * 1024))
    valid_outputs.append(_response_line("a" * 32, actual=json.dumps({"nested": [1]})))  # non-canonical
    for index, output in enumerate(valid_outputs):
        sandbox = _StubSandbox(available=True, result=_sandbox_result(output))
        worker = UntrustedExecutionWorker(sandbox)
        observation = worker.run_case("def f():\n    return 0\n", "f", [])
        assert observation.status == WORKER_STATUS_INFRA_ERROR, f"forged response {index} not rejected"
        assert observation.actual_canonical is None


def test_supervisor_timeout_kill_maps_to_timeout_observation():
    sandbox = _StubSandbox(available=True, result=_sandbox_result(b"", exit_code=-9, timed_out=True))
    worker = UntrustedExecutionWorker(sandbox)
    observation = worker.run_case("def f():\n    return 0\n", "f", [], timeout_s=0.3)
    assert observation.status == WORKER_STATUS_TIMEOUT
    assert observation.actual_canonical is None


def test_killed_process_without_protocol_output_maps_to_timeout():
    sandbox = _StubSandbox(available=True, result=_sandbox_result(b"", exit_code=-9))
    worker = UntrustedExecutionWorker(sandbox)
    observation = worker.run_case("def f():\n    return 0\n", "f", [])
    assert observation.status == WORKER_STATUS_TIMEOUT


def test_valid_line_with_nonzero_exit_code_is_infra():
    sandbox = _EchoSandbox(actual="0", exit_code=1)
    worker = UntrustedExecutionWorker(sandbox)
    observation = worker.run_case("def f():\n    return 0\n", "f", [])
    assert observation.status == WORKER_STATUS_INFRA_ERROR


# ---------------------------------------------------------------------------
# Real sandbox integration: reference solutions and student failure classes
# ---------------------------------------------------------------------------


def _run_reference_tests(worker: UntrustedExecutionWorker, case: dict, tests: list) -> int:
    executed = 0
    for index, test in enumerate(tests):
        observation = worker.run_case(
            case["reference_solution"], case["function_name"], test["args"]
        )
        assert observation.status == WORKER_STATUS_COMPLETED, (
            f"{case['case_id']} test[{index}]: reference solution did not complete"
        )
        assert observation.actual_canonical == canonical_json(test["expected"]), (
            f"{case['case_id']} test[{index}]: observed actual differs from hidden expected"
        )
        executed += 1
    return executed


def test_worker_reference_observations_match_hidden_expected(real_worker):
    """All 14 reference solutions must complete every hidden case in-sandbox.

    This is the worker-side half of B1-05: 112/112 hidden cases observed as
    COMPLETED with actual == expected (the trusted supervisor does the final
    comparison).  It also exercises the 11 ``large`` cases whose args exceed the
    threat-model 4096-byte default and require the Lead-approved 1 MiB budget.
    """
    executed = 0
    elapsed_started = time.monotonic()
    for case in CASES:
        executed += _run_reference_tests(real_worker, case, case["tests"])
    elapsed = time.monotonic() - elapsed_started
    assert executed == 112
    assert elapsed < 60.0


def test_worker_student_failure_statuses(real_worker):
    syntax = real_worker.run_case(
        "def first_index(nums, target)\n    return 0\n", "first_index", [[1], 1]
    )
    assert syntax.status == WORKER_STATUS_SYNTAX_ERROR
    assert syntax.exception_type == "SyntaxError"

    import_error = real_worker.run_case(
        "raise RuntimeError('import-time synthetic failure')\n", "first_index", [[1], 1]
    )
    assert import_error.status == WORKER_STATUS_IMPORT_ERROR

    raised = real_worker.run_case(
        "def first_index(nums, target):\n    raise ValueError('synthetic')\n", "first_index", [[1], 1]
    )
    assert raised.status == WORKER_STATUS_RAISED
    assert raised.exception_type == "ValueError"

    missing = real_worker.run_case(
        "def other_function(nums, target):\n    return 0\n", "first_index", [[1], 1]
    )
    assert missing.status == WORKER_STATUS_MISSING_FUNCTION


def test_worker_wrong_answer_is_observation_not_verdict(real_worker):
    case = next(case for case in CASES if case["case_id"] == "cf_bs_search_insert")
    test = next(test for test in case["tests"] if test["kind"] == "edge")
    wrong_solution = (
        "def search_insert(nums, target):\n"
        "    low = 0\n"
        "    high = len(nums)\n"
        "    while low < high:\n"
        "        mid = (low + high) // 2\n"
        "        if nums[mid] < target:\n"
        "            low = mid + 1\n"
        "        else:\n"
        "            high = mid\n"
        "    return low + 1\n"
    )
    observation = real_worker.run_case(wrong_solution, "search_insert", test["args"])
    assert observation.status == WORKER_STATUS_COMPLETED
    assert observation.actual_canonical is not None
    assert observation.actual_canonical != canonical_json(test["expected"])
    assert not hasattr(observation, "passed")


def test_worker_timeout_is_bounded_and_cleaned_up(real_worker):
    before = _temp_worker_dirs()
    started = time.monotonic()
    observation = real_worker.run_case(
        "def first_index(nums, target):\n    while True:\n        pass\n",
        "first_index",
        [[1], 1],
        timeout_s=0.3,
    )
    elapsed = time.monotonic() - started
    after = _temp_worker_dirs()
    assert observation.status == WORKER_STATUS_TIMEOUT
    assert elapsed < 5.0
    assert before == after, "worker temp directories were not cleaned up"


def test_worker_output_excerpts_are_bounded(real_worker):
    observation = real_worker.run_case(
        "def first_index(nums, target):\n"
        "    print('x' * 10000)\n"
        "    import sys\n"
        "    sys.stderr.write('y' * 10000)\n"
        "    return -1\n",
        "first_index",
        [[1], 1],
    )
    assert observation.status == WORKER_STATUS_COMPLETED
    assert observation.actual_canonical == "-1"
    assert len(observation.stdout_excerpt.encode("utf-8")) <= 512
    assert len(observation.stderr_excerpt.encode("utf-8")) <= 512


def test_worker_is_deterministic_for_the_same_case(real_worker):
    case = next(case for case in CASES if case["case_id"] == "cf_tp_pair_sum_sorted")
    test = case["tests"][0]
    first = real_worker.run_case(case["reference_solution"], case["function_name"], test["args"])
    second = real_worker.run_case(case["reference_solution"], case["function_name"], test["args"])
    assert first.request_id != second.request_id
    assert dataclasses.replace(first, request_id="") == dataclasses.replace(second, request_id="")
    assert first.actual_canonical == canonical_json(test["expected"])


def test_worker_unserializable_actual_is_raised_not_pass(real_worker):
    for code in (
        "def first_index(nums, target):\n    return {1, 2, 3}\n",
        "def first_index(nums, target):\n    return float('nan')\n",
        "def first_index(nums, target):\n    return object()\n",
    ):
        observation = real_worker.run_case(code, "first_index", [[1], 1])
        assert observation.status == WORKER_STATUS_RAISED
        assert observation.exception_type == "UnserializableActual"
        assert observation.actual_canonical is None


def test_worker_observation_carries_no_hidden_material(real_worker):
    case = next(case for case in CASES if case["case_id"] == "cf_array_max_subarray")
    test = case["tests"][0]
    observation = real_worker.run_case(case["reference_solution"], case["function_name"], test["args"])
    serialized = json.dumps(dataclasses.asdict(observation), ensure_ascii=False)
    for forbidden in ("expected", "tests", "hidden", "verdict", "passed", "SENTINEL_DO_NOT_LEAK"):
        assert forbidden not in serialized
    assert observation.status == WORKER_STATUS_COMPLETED


# ---------------------------------------------------------------------------
# Protocol parser cross-checks
# ---------------------------------------------------------------------------


def test_sandbox_runner_constants_match_protocol():
    import ast

    from m1_teacher.assessment.judge import protocol

    runner_path = Path(protocol.__file__).with_name("worker_runner.py")
    tree = ast.parse(runner_path.read_text(encoding="utf-8"))
    def _constant(node):
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return -_constant(node.operand)
        if isinstance(node, ast.BinOp):
            left = _constant(node.left)
            right = _constant(node.right)
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
        raise ValueError("not a simple constant")

    constants = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                try:
                    constants[target.id] = _constant(node.value)
                except (ValueError, TypeError):
                    continue
    assert constants["PROTOCOL_VERSION"] == protocol.PROTOCOL_VERSION
    assert constants["MAX_REQUEST_BYTES"] == protocol.MAX_REQUEST_BYTES
    assert constants["MAX_ARGS_BYTES"] == protocol.MAX_ARGS_BYTES
    assert constants["MAX_ARGS_NODES"] == protocol.MAX_ARGS_NODES
    assert constants["MAX_ACTUAL_CANONICAL_BYTES"] == protocol.MAX_ACTUAL_CANONICAL_BYTES
    assert constants["MAX_EXCERPT_BYTES"] == protocol.MAX_EXCERPT_BYTES
    assert constants["MIN_TIMEOUT_MS"] == protocol.MIN_TIMEOUT_MS
    assert constants["MAX_TIMEOUT_MS"] == protocol.MAX_TIMEOUT_MS


def test_oversized_request_is_fail_closed_and_never_executed():
    from m1_teacher.assessment.judge import protocol
    from m1_teacher.assessment.judge import worker_runner as runner_module

    over_request = b" " * (protocol.MAX_REQUEST_BYTES + 1)
    with pytest.raises(protocol.WorkerProtocolError):
        protocol.parse_request(over_request)
    with pytest.raises(ValueError):
        runner_module._parse_request(over_request)

    huge_args = [list(range(200000))]  # canonical JSON well above 1 MiB
    assert len(protocol.canonical_json(huge_args).encode("utf-8")) > protocol.MAX_ARGS_BYTES
    with pytest.raises(protocol.WorkerProtocolError):
        protocol.build_request("f", huge_args)

    sandbox = _StubSandbox(available=True, result=_sandbox_result(_response_line("0" * 32)))
    worker = UntrustedExecutionWorker(sandbox)
    observation = worker.run_case("def f():\n    return 0\n", "f", huge_args)
    assert observation.status == WORKER_STATUS_INFRA_ERROR
    assert sandbox.run_calls == 0


def test_oversized_request_is_rejected_inside_the_sandbox_before_learner_code(real_sandbox):
    work_dir = Path(tempfile.mkdtemp(prefix="m1b_worker_oversized_"))
    try:
        solution = work_dir / SOLUTION_FILENAME
        solution.write_text("import time\nwhile True:\n    time.sleep(5)\n", encoding="utf-8")
        solution.chmod(0o444)
        runner_copy = work_dir / WORKER_RUNNER_FILENAME
        shutil.copyfile(Path(__file__).resolve().parents[2] / "m1_teacher" / "assessment" / "judge" / "worker_runner.py", runner_copy)
        runner_copy.chmod(0o444)
        oversized = b"{" + b" " * (2 * 1024 * 1024 + 16) + b"}"
        started = time.monotonic()
        result = real_sandbox.run(
            work_dir,
            [WORKER_PYTHON, "/worker/worker_runner.py"],
            2.0,
            stdin_data=oversized,
        )
        elapsed = time.monotonic() - started
    finally:
        for child in work_dir.iterdir():
            try:
                child.chmod(0o600)
            except OSError:
                pass
        shutil.rmtree(work_dir, ignore_errors=True)
    assert result.timed_out is False
    payload = json.loads(result.stdout.decode("utf-8").strip())
    assert payload["status"] == WORKER_STATUS_INFRA_ERROR
    assert payload["actual_canonical"] is None
    assert elapsed < 1.5, "oversized request should be rejected before learner code runs"


def test_protocol_round_trip_and_strict_parsing():
    request_id = "c" * 32
    request_text = build_request(
        "max_subarray_sum", [[-2, 1, -3]], request_id=request_id, timeout_ms=1500
    )
    assert "expected" not in request_text.lower()
    response = _response_line(request_id, actual="1")
    observation = parse_worker_response(response)
    assert observation.status == WORKER_STATUS_COMPLETED
    assert observation.actual_canonical == "1"
    assert observation.request_id == request_id
    for bad in (b"", b"{", _response_line(request_id) + b"\n" + _response_line(request_id)):
        with pytest.raises(WorkerProtocolError):
            parse_worker_response(bad)


# ---------------------------------------------------------------------------
# Review P1-1: timeout classification must not treat resource kills as INFRA
# ---------------------------------------------------------------------------
def _timeout_sandbox_result(
    exit_code, elapsed_s, *, timed_out=False, stdout=b"", stderr=b""
):
    return SandboxResult(
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        timed_out=timed_out,
        elapsed_s=elapsed_s,
        stdout_truncated=False,
        stderr_truncated=False,
    )


def test_timeout_kill_classification_positive_signal_codes():
    is_timeout = UntrustedExecutionWorker._is_timeout_kill
    assert is_timeout(_timeout_sandbox_result(137, 1.9), 2.0) is True   # 128+SIGKILL
    assert is_timeout(_timeout_sandbox_result(152, 1.85), 2.0) is True  # 128+SIGXCPU
    assert is_timeout(_timeout_sandbox_result(124, 0.46), 0.5) is True  # timeout(1) code
    assert is_timeout(_timeout_sandbox_result(-9, 0.2), 2.0) is True    # supervisor group kill
    assert is_timeout(_timeout_sandbox_result(137, 0.2), 2.0) is False  # early failure != TLE
    assert is_timeout(_timeout_sandbox_result(1, 2.0), 2.0) is False
    assert is_timeout(_timeout_sandbox_result(None, 2.0), 2.0) is False
    assert is_timeout(_timeout_sandbox_result(137, 2.0), 0.0) is False


def test_interpret_positive_cpu_kill_after_budget_is_timeout():
    observation = UntrustedExecutionWorker._interpret(
        _timeout_sandbox_result(137, 2.0), "req", 2.0
    )
    assert observation.status == WORKER_STATUS_TIMEOUT


def test_interpret_positive_cpu_kill_too_early_is_infra():
    observation = UntrustedExecutionWorker._interpret(
        _timeout_sandbox_result(137, 0.3), "req", 2.0
    )
    assert observation.status == WORKER_STATUS_INFRA_ERROR


# ---------------------------------------------------------------------------
# Review addendum P1-2: startup non-root enforcement blocks worker execution
# ---------------------------------------------------------------------------
def test_nonroot_requirement_blocks_worker_before_any_execution(monkeypatch):
    probe = UntrustedExecutionWorker()
    if not probe.sandbox_available():  # pragma: no cover - non-bwrap host
        require_os_sandbox(available=False)
    monkeypatch.setenv("M1B_REQUIRE_NONROOT_SANDBOX", "1")
    worker = UntrustedExecutionWorker()
    assert worker.sandbox_available() is False
    before_dirs = _temp_worker_dirs()
    observation = worker.run_case(
        "from pathlib import Path\n"
        "Path('/tmp/m1b_p1_2_should_not_run').write_text('x')\n"
        "def target(*_args, **_kwargs):\n"
        "    return 0\n",
        "target",
        [],
    )
    after_dirs = _temp_worker_dirs()
    assert observation.status == WORKER_STATUS_INFRA_ERROR
    assert before_dirs == after_dirs
