"""Security negative tests for the B-PR1 untrusted execution worker (M1-B).

Every payload here is synthetic and harmless (see
``fixtures/m1_teacher/judge/sentinels/sentinels.json`` and
``certification/negatives.json``); the only place these payloads ever run is
inside the real bwrap sandbox with a bounded wall clock and process-group kill.
No real network traffic is initiated, no real credentials exist and the host
sentinel is a temporary synthetic file created under the host temp dir.

Assertions are written as fail-closed invariants: no attack can yield a PASS
(the worker only reports observations), no hidden sentinel value may appear in
any observation, and INFRA vs TIMEOUT vs STUDENT_TLE classification is explicit.
"""

from __future__ import annotations

import dataclasses
import json
import os
import shutil
import tempfile
import time
from pathlib import Path

import pytest

from m1_teacher.assessment.judge.protocol import (

    REQUEST_FIELDS,
    WORKER_STATUS_COMPLETED,
    WORKER_STATUS_IMPORT_ERROR,
    WORKER_STATUS_INFRA_ERROR,
    WORKER_STATUS_MISSING_FUNCTION,
    WORKER_STATUS_RAISED,
    WORKER_STATUS_SYNTAX_ERROR,
    WORKER_STATUS_TIMEOUT,
    canonical_json,
)
from m1_teacher.assessment.judge.sandbox import BwrapSandbox
from m1_teacher.assessment.judge.worker import WORK_DIR_PREFIX, UntrustedExecutionWorker

from judge_os_gate import require_os_sandbox

REPO_ROOT = Path(__file__).resolve().parents[2]
JUDGE_DIR = REPO_ROOT / "fixtures" / "m1_teacher" / "judge"

SENTINELS = json.loads((JUDGE_DIR / "sentinels" / "sentinels.json").read_text(encoding="utf-8"))
NEGATIVES = json.loads(
    (JUDGE_DIR / "certification" / "negatives.json").read_text(encoding="utf-8")
)["negatives"]
CASES = {
    case["case_id"]: case
    for case in json.loads(
        (JUDGE_DIR / "certification" / "cases.json").read_text(encoding="utf-8")
    )["cases"]
}

SENTINEL_VALUES = [
    SENTINELS["sentinel_expected"],
    SENTINELS["sentinel_secret_token"],
    SENTINELS["host_sentinel_content"],
]
SENTINEL_EXPECTED_CANONICAL = canonical_json(SENTINELS["sentinel_expected"])

CLASSIFICATION_STATUSES = {
    "WA": {WORKER_STATUS_COMPLETED},
    "RE": {
        WORKER_STATUS_RAISED,
        WORKER_STATUS_SYNTAX_ERROR,
        WORKER_STATUS_IMPORT_ERROR,
        WORKER_STATUS_MISSING_FUNCTION,
        WORKER_STATUS_INFRA_ERROR,
    },
    "TLE": {WORKER_STATUS_TIMEOUT, WORKER_STATUS_INFRA_ERROR},
    "PASS": {WORKER_STATUS_COMPLETED},
}



def _observation_text(observation) -> str:
    return json.dumps(dataclasses.asdict(observation), ensure_ascii=False)


def _contains_any_sentinel(text: str) -> bool:
    """Existence-only helper: never echo a sentinel value in a message."""

    return any(value in text for value in SENTINEL_VALUES)


def _classify(observation) -> str:
    if observation.status == WORKER_STATUS_TIMEOUT:
        return "STUDENT_TLE"
    if observation.status == WORKER_STATUS_INFRA_ERROR:
        return "JUDGE_INFRA_ERROR"
    if observation.status in {
        WORKER_STATUS_RAISED,
        WORKER_STATUS_SYNTAX_ERROR,
        WORKER_STATUS_IMPORT_ERROR,
        WORKER_STATUS_MISSING_FUNCTION,
    }:
        return "RE"
    return "COMPLETED_OBSERVATION"


def _temp_worker_dirs() -> set:
    return {
        entry.name
        for entry in Path(tempfile.gettempdir()).iterdir()
        if entry.name.startswith(WORK_DIR_PREFIX)
    }


@pytest.fixture(scope="module")
def real_sandbox() -> BwrapSandbox:
    sandbox = BwrapSandbox()
    require_os_sandbox(sandbox.available())
    return sandbox


@pytest.fixture(scope="module")
def real_worker(real_sandbox: BwrapSandbox) -> UntrustedExecutionWorker:
    return UntrustedExecutionWorker(real_sandbox)


# ---------------------------------------------------------------------------
# Negative submissions: declared classification matches real sandbox run
# ---------------------------------------------------------------------------


def test_negative_fixtures_match_declared_classification(real_worker):
    case_ids = {negative["negative_id"]: negative for negative in NEGATIVES}
    assert case_ids, "negative fixtures are missing"
    for negative in NEGATIVES:
        negative_id = negative["negative_id"]
        case = CASES[negative["case_id"]]
        function_name = case["function_name"]
        expected_classification = negative["expected_classification"]
        allowed_statuses = CLASSIFICATION_STATUSES[expected_classification]

        if negative["failure_mode"] == "infinite_loop":
            # Executed only inside the sandbox with a bounded wall clock; the
            # sandbox kills the whole process group (verified again below).
            observation = real_worker.run_case(
                negative["code"], function_name, case["tests"][0]["args"], timeout_s=0.3
            )
            assert observation.status in allowed_statuses, (
                f"{negative_id}: unexpected status for declared classification"
            )
            assert _classify(observation) == "STUDENT_TLE"
            continue

        if negative["failure_mode"] == "edge_correct":
            for index, test in enumerate(case["tests"]):
                observation = real_worker.run_case(
                    negative["code"], function_name, test["args"]
                )
                assert observation.status == WORKER_STATUS_COMPLETED, (
                    f"{negative_id}: edge-correct solution did not complete at test {index}"
                )
                assert observation.actual_canonical == canonical_json(test["expected"]), (
                    f"{negative_id}: edge-correct solution did not pass hidden test {index}"
                )
            continue

        test = case["tests"][0]
        observation = real_worker.run_case(negative["code"], function_name, test["args"])
        assert observation.status in allowed_statuses, (
            f"{negative_id}: unexpected status for declared classification"
        )
        text = _observation_text(observation)
        assert not _contains_any_sentinel(text), f"{negative_id}: observation leaked a sentinel value"
        if expected_classification == "WA":
            assert observation.actual_canonical is not None
            assert observation.actual_canonical != canonical_json(test["expected"]), (
                f"{negative_id}: wrong solution unexpectedly matched the hidden expected value"
            )


# ---------------------------------------------------------------------------
# Attack templates: never PASS, never leak sentinels, bounded resources
# ---------------------------------------------------------------------------


def test_attack_templates_never_pass_and_never_leak_sentinels(real_worker):
    attacks = SENTINELS["attack_templates"]
    assert attacks, "attack templates are missing"
    before_dirs = _temp_worker_dirs()
    for attack in attacks:
        attack_id = attack["attack_id"]
        family = attack["attack_family"]
        timeout_s = 0.4 if family in {"fork_subprocess", "infinite_loop"} else 2.0
        started = time.monotonic()
        observation = real_worker.run_case(attack["code"], "target", [], timeout_s=timeout_s)
        elapsed = time.monotonic() - started
        assert elapsed < 8.0, f"{attack_id}: sandbox run exceeded the local bound"

        text = _observation_text(observation)
        assert not _contains_any_sentinel(text), f"{attack_id}: observation leaked a sentinel value"
        expected_classification = attack["expected_classification"]
        assert observation.status in CLASSIFICATION_STATUSES[expected_classification], (
            f"{attack_id}: attack was not observed with the declared fail-closed status"
        )
        if attack["expected_blocked"]:
            assert observation.status != WORKER_STATUS_COMPLETED or (
                observation.actual_canonical != SENTINEL_EXPECTED_CANONICAL
            )
        else:
            # Explicitly declared as *not blocked*: writing into the sandbox's
            # ephemeral root tmpfs may succeed, but it must still be only a
            # non-PASS observation and have no host effect (separate test).
            assert observation.status == WORKER_STATUS_COMPLETED, (
                f"{attack_id}: declared unblocked attack expected a COMPLETED observation"
            )
        # A blocked attack can never produce the synthetic hidden expected value.
        if observation.actual_canonical is not None:
            assert observation.actual_canonical != SENTINEL_EXPECTED_CANONICAL, (
                f"{attack_id}: attack reproduced the hidden expected value"
            )
        # The worker observation surface never grows a verdict field.
        field_names = {field.name for field in dataclasses.fields(observation)}
        assert not field_names & {"passed", "verdict", "score", "expected", "tests"}
    after_dirs = _temp_worker_dirs()
    assert before_dirs == after_dirs, "attack runs left worker temp directories behind"


def test_attack_timeout_and_fork_are_killed_without_host_leftovers(real_worker):
    marker = "M1B_PR1_FORK_LEFTOVER_7d41c9a2"
    fork_payload = (
        "def target(*_args, **_kwargs):\n"
        "    import subprocess\n"
        "    import sys\n"
        "    subprocess.Popen(\n"
        "        [sys.executable, '-c', 'import time; time.sleep(60)  # %s']\n"
        "    )\n"
        "    while True:\n"
        "        pass\n"
    ) % marker
    before_dirs = _temp_worker_dirs()
    observation = real_worker.run_case(fork_payload, "target", [], timeout_s=0.4)
    after_dirs = _temp_worker_dirs()
    assert observation.status in {WORKER_STATUS_TIMEOUT, WORKER_STATUS_INFRA_ERROR}
    assert _classify(observation) in {"STUDENT_TLE", "JUDGE_INFRA_ERROR"}
    assert before_dirs == after_dirs

    leftovers = []
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            cmdline = Path(f"/proc/{entry}/cmdline").read_bytes().decode("utf-8", "replace")
        except OSError:
            continue
        if marker in cmdline:
            leftovers.append(entry)
    assert leftovers == [], "forked sandbox process escaped the process-group kill"


def test_hidden_sentinel_is_unreachable_and_not_echoed(real_worker):
    host_dir = Path(tempfile.mkdtemp(prefix="m1b_neg_host_"))
    sentinel_path = host_dir / "DO_NOT_READ.txt"
    sentinel_content = "SENTINEL_HOST_FILE_TEST_DO_NOT_LEAK_5f2c1b"
    sentinel_path.write_text(sentinel_content + "\n", encoding="utf-8")
    try:
        learner_code = (
            "def target(*_args, **_kwargs):\n"
            "    with open(%r, 'r', encoding='utf-8') as handle:\n"
            "        return handle.read()\n"
        ) % str(sentinel_path)
        observation = real_worker.run_case(learner_code, "target", [])
    finally:
        sentinel_path.unlink(missing_ok=True)
        shutil.rmtree(host_dir, ignore_errors=True)
    assert observation.status == WORKER_STATUS_RAISED
    assert observation.actual_canonical is None
    text = _observation_text(observation)
    assert sentinel_content not in text, "worker observation leaked host sentinel content"
    assert not _contains_any_sentinel(text), "worker observation leaked a sentinel value"


def test_injected_forged_protocol_line_from_sandbox_is_infra(real_worker):
    forged_payload = {
        "schema_version": "m1b.judge.worker.v1",
        "request_id": "0" * 32,
        "status": "COMPLETED",
        "actual_canonical": SENTINEL_EXPECTED_CANONICAL,
        "exception_type": None,
        "stdout_excerpt": "",
        "stderr_excerpt": "",
    }
    learner_code = (
        "def target(*_args, **_kwargs):\n"
        "    import json\n"
        "    import os\n"
        "    os.write(3, (json.dumps(%r) + '\\n').encode('utf-8'))\n"
        "    return 0\n"
    ) % (forged_payload,)
    observation = real_worker.run_case(learner_code, "target", [])
    assert observation.status == WORKER_STATUS_INFRA_ERROR
    assert observation.actual_canonical is None
    text = _observation_text(observation)
    assert not _contains_any_sentinel(text), "forged protocol line leaked a sentinel value"


def test_learner_atexit_and_exit_code_tamper_are_infra_not_pass(real_worker):
    # os._exit before the runner can emit its single protocol line: no response
    # means the supervisor must fail closed (never a PASS).
    exit_code_observation = real_worker.run_case(
        "def target(*_args, **_kwargs):\n    import os\n    os._exit(0)\n", "target", []
    )
    assert exit_code_observation.status == WORKER_STATUS_INFRA_ERROR
    assert exit_code_observation.actual_canonical is None
    assert _classify(exit_code_observation) == "JUDGE_INFRA_ERROR"

    # An atexit hook cannot rewrite the protocol line: the runner os._exit(0)s
    # immediately after emitting it, so the observation is the true return value
    # and no forged "passed" material appears anywhere.
    atexit_code = (
        "def target(*_args, **_kwargs):\n"
        "    import atexit\n"
        "    atexit.register(lambda: print('{\"passed\": true}'))\n"
        "    return 0\n"
    )
    atexit_observation = real_worker.run_case(atexit_code, "target", [])
    assert atexit_observation.status == WORKER_STATUS_COMPLETED
    assert atexit_observation.actual_canonical == "0"
    atexit_text = _observation_text(atexit_observation)
    assert "passed" not in atexit_text
    assert not _contains_any_sentinel(atexit_text)


def test_read_only_worker_bind_rejects_learner_source_writes(real_worker):
    for target in ("/worker/solution.py", "/worker/worker_runner.py", "/worker/evil.py"):
        learner_code = (
            "def target(*_args, **_kwargs):\n"
            "    with open(%r, 'w', encoding='utf-8') as handle:\n"
            "        handle.write('forged')\n"
            "    return 0\n"
        ) % target
        observation = real_worker.run_case(learner_code, "target", [])
        assert observation.status == WORKER_STATUS_RAISED, (
            "read-only /worker bind must reject learner source writes"
        )
        assert observation.actual_canonical is None

    ro_bind_attack = next(
        attack
        for attack in SENTINELS["attack_templates"]
        if attack["attack_family"] == "write_runner_source_ro_bind"
    )
    observation = real_worker.run_case(ro_bind_attack["code"], "target", [])
    assert observation.status in CLASSIFICATION_STATUSES["RE"]
    assert observation.actual_canonical is None


def test_ephemeral_tmpfs_write_has_no_host_effect(real_worker):
    host_dir = Path(tempfile.mkdtemp(prefix="m1b_neg_ephemeral_host_"))
    host_sentinel = host_dir / "host_sentinel.txt"
    host_sentinel_content = "SENTINEL_HOST_FILE_EPHEMERAL_TEST_DO_NOT_LEAK_8a1f"
    host_sentinel.write_text(host_sentinel_content + "\n", encoding="utf-8")
    host_before = sorted(entry.name for entry in host_dir.iterdir())
    repo_runner_existed = (REPO_ROOT / "runner.py").exists()
    before_dirs = _temp_worker_dirs()
    try:
        attack = next(
            attack
            for attack in SENTINELS["attack_templates"]
            if attack["attack_family"] == "write_runner_source_ephemeral_tmpfs"
        )
        assert attack["expected_blocked"] is False
        assert attack["expected_observation"] == "ephemeral_write_no_host_effect"
        observation = real_worker.run_case(attack["code"], "target", [])
    finally:
        after_host = sorted(entry.name for entry in host_dir.iterdir())
        host_after_content = host_sentinel.read_text(encoding="utf-8")
        shutil.rmtree(host_dir, ignore_errors=True)
    after_dirs = _temp_worker_dirs()

    # The write may succeed inside the sandbox tmpfs, but it is only an
    # observation (never the hidden expected) and the host is untouched.
    assert observation.status == WORKER_STATUS_COMPLETED
    assert observation.actual_canonical == "0"
    assert observation.actual_canonical != SENTINEL_EXPECTED_CANONICAL
    assert host_before == after_host, "ephemeral sandbox write modified host files"
    assert host_after_content == host_sentinel_content + "\n"
    assert (REPO_ROOT / "runner.py").exists() is repo_runner_existed
    assert before_dirs == after_dirs, "ephemeral attack left worker temp directories behind"
    text = _observation_text(observation)
    assert not _contains_any_sentinel(text)
    assert "SENTINEL_HOST_FILE_EPHEMERAL_TEST_DO_NOT_LEAK" not in text


# ---------------------------------------------------------------------------
# Classification mapping: INFRA vs TIMEOUT vs STUDENT_TLE
# ---------------------------------------------------------------------------


class _UnavailableSandbox:
    def available(self) -> bool:
        return False

    def run(self, *args, **kwargs):  # pragma: no cover - must never be called
        raise AssertionError("unavailable sandbox must never execute")


class _ForgedSandbox:
    def available(self) -> bool:
        return True

    def run(self, *args, **kwargs):
        from m1_teacher.assessment.judge.sandbox import SandboxResult

        return SandboxResult(
            exit_code=0,
            stdout=b'{"passed": true}\n',
            stderr=b"",
            timed_out=False,
            elapsed_s=0.01,
            stdout_truncated=False,
            stderr_truncated=False,
        )


def test_infra_and_timeout_classifications_are_distinct():
    unavailable_worker = UntrustedExecutionWorker(_UnavailableSandbox())
    unavailable_observation = unavailable_worker.run_case("def f():\n    return 0\n", "f", [])
    assert unavailable_observation.status == WORKER_STATUS_INFRA_ERROR
    assert _classify(unavailable_observation) == "JUDGE_INFRA_ERROR"

    forged_worker = UntrustedExecutionWorker(_ForgedSandbox())
    forged_observation = forged_worker.run_case("def f():\n    return 0\n", "f", [])
    assert forged_observation.status == WORKER_STATUS_INFRA_ERROR
    assert _classify(forged_observation) == "JUDGE_INFRA_ERROR"


def test_student_tle_is_timeout_observation(real_worker):
    observation = real_worker.run_case(
        "def f():\n    while True:\n        pass\n", "f", [], timeout_s=0.3
    )
    assert observation.status == WORKER_STATUS_TIMEOUT
    assert _classify(observation) == "STUDENT_TLE"
    assert observation.actual_canonical is None


# ---------------------------------------------------------------------------
# Hidden expected isolation at the request boundary
# ---------------------------------------------------------------------------


class _CapturingSandbox:
    def __init__(self) -> None:
        self.stdin = b""
        self.argv: list[str] = []

    def available(self) -> bool:
        return True

    def run(self, work_dir, argv, timeout_s, *, stdin_data=b"", extra_env=None):
        from m1_teacher.assessment.judge.sandbox import SandboxResult

        self.stdin = bytes(stdin_data)
        self.argv = list(argv)
        request = json.loads(self.stdin.decode("utf-8"))
        response = {
            "schema_version": "m1b.judge.worker.v1",
            "request_id": request["request_id"],
            "status": "COMPLETED",
            "actual_canonical": "-1",
            "exception_type": None,
            "stdout_excerpt": "",
            "stderr_excerpt": "",
        }
        return SandboxResult(
            exit_code=0,
            stdout=(json.dumps(response) + "\n").encode("utf-8"),
            stderr=b"",
            timed_out=False,
            elapsed_s=0.01,
            stdout_truncated=False,
            stderr_truncated=False,
        )


def test_attack_request_contains_no_expected_paths_or_sentinel_values():
    sandbox = _CapturingSandbox()
    worker = UntrustedExecutionWorker(sandbox)
    attack = next(
        template
        for template in SENTINELS["attack_templates"]
        if template["attack_family"] == "stack_frame_probe"
    )
    worker.run_case(attack["code"], "target", [])
    request = json.loads(sandbox.stdin.decode("utf-8"))
    assert set(request) == set(REQUEST_FIELDS)
    lowered = sandbox.stdin.decode("utf-8").lower()
    for forbidden in ("expected", "tests", "hidden", "verdict", "passed", "result", "/worker"):
        assert forbidden not in lowered
    text = sandbox.stdin.decode("utf-8") + " ".join(sandbox.argv)
    assert not _contains_any_sentinel(text), "worker request/argv leaked a sentinel value"
    assert sandbox.argv == ["/usr/bin/python3", "/worker/worker_runner.py"]
