"""Untrusted execution worker for a single learner CODE case (B-PR1).

Trust boundary
--------------
:class:`UntrustedExecutionWorker` receives learner code, a target function name
and the JSON arguments of **one** case.  It never receives ``expected`` values,
hidden tests, scoring specs, paths or result schemas.  It runs the code in a
:class:`~m1_teacher.assessment.judge.sandbox.BwrapSandbox` (one process per
case) and returns a :class:`~m1_teacher.assessment.judge.protocol.WorkerObservation`
that contains only *observations*: status, canonicalised actual value or
exception class, and bounded learner stdout/stderr excerpts.

The trusted supervisor alone compares the observed actual value against its own
hidden expected value and decides PASS/WA/RE/TLE.  Everything that comes back
from the worker is untrusted; malformed protocol output, forged JSON, killed
processes and sandbox failures are mapped to a fail-closed
``INFRA_ERROR``/``TIMEOUT`` observation -- never to a PASS.

Fail-closed
-----------
If the OS sandbox is unavailable (missing ``bwrap``, failed canary self-check),
:meth:`UntrustedExecutionWorker.run_case` returns ``INFRA_ERROR`` **without
executing the learner code**.  There is no bare-subprocess fallback.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any, Protocol, Sequence

from . import protocol
from .protocol import (
    DEFAULT_STDOUT_LIMIT,
    DEFAULT_STDERR_LIMIT,
    WorkerObservation,
    infra_observation,
    timeout_observation,
)
from .sandbox import (
    WORKER_PYTHON,
    BwrapSandbox,
    SandboxLaunchError,
    SandboxResult,
    SandboxUnavailable,
)

__all__ = [
    "DEFAULT_CASE_TIMEOUT_S",
    "MIN_CASE_TIMEOUT_S",
    "MAX_CASE_TIMEOUT_S",
    "WORKER_WALL_GRACE_S",
    "WORK_DIR_PREFIX",
    "SOLUTION_FILENAME",
    "WORKER_RUNNER_FILENAME",
    "SandboxLike",
    "UntrustedExecutionWorker",
]

DEFAULT_CASE_TIMEOUT_S = 1.5
MIN_CASE_TIMEOUT_S = 0.05
MAX_CASE_TIMEOUT_S = 5.0

#: Extra wall-clock grace on top of the request timeout before the supervisor
#: kills the whole sandbox process group.
WORKER_WALL_GRACE_S = 0.5

WORK_DIR_PREFIX = "m1b_judge_worker_"
SOLUTION_FILENAME = "solution.py"
WORKER_RUNNER_FILENAME = "worker_runner.py"


class SandboxLike(Protocol):
    """Structural protocol implemented by :class:`BwrapSandbox` (and fakes)."""

    def available(self) -> bool: ...

    def run(
        self,
        work_dir: str | Path,
        argv: Sequence[str],
        timeout_s: float,
        *,
        stdin_data: bytes | str = b"",
        extra_env: Any = None,
    ) -> SandboxResult: ...


class UntrustedExecutionWorker:
    """Execute one learner case inside the OS sandbox and observe the result."""

    def __init__(
        self,
        sandbox: SandboxLike | None = None,
        *,
        runner_path: str | Path | None = None,
        timeout_grace_s: float = WORKER_WALL_GRACE_S,
        stdout_limit: int = DEFAULT_STDOUT_LIMIT,
        stderr_limit: int = DEFAULT_STDERR_LIMIT,
    ) -> None:
        self._sandbox: SandboxLike = sandbox if sandbox is not None else BwrapSandbox()
        self._runner_path = (
            Path(runner_path)
            if runner_path is not None
            else Path(__file__).with_name(WORKER_RUNNER_FILENAME)
        )
        self._timeout_grace_s = float(timeout_grace_s)
        self._stdout_limit = int(stdout_limit)
        self._stderr_limit = int(stderr_limit)

    # -- introspection --------------------------------------------------------

    @property
    def sandbox(self) -> SandboxLike:
        return self._sandbox

    def sandbox_available(self) -> bool:
        return bool(self._sandbox.available())

    # -- public API -----------------------------------------------------------

    def run_case(
        self,
        code: str,
        function_name: str,
        args: Sequence[Any],
        timeout_s: float | None = None,
    ) -> WorkerObservation:
        """Run one case of learner ``code`` and return an untrusted observation.

        The worker never receives expected values or hidden tests: the request
        it builds carries only the target function name and the arguments of the
        single case.  ``expected``/``tests`` are not parameters of this API.
        """

        request_id = protocol.new_request_id()
        try:
            timeout_value = self._coerce_timeout(timeout_s)
            request_text = protocol.build_request(
                function_name,
                list(args),
                request_id=request_id,
                timeout_ms=int(round(timeout_value * 1000)),
                stdout_limit=self._stdout_limit,
                stderr_limit=self._stderr_limit,
            )
        except protocol.WorkerProtocolError:
            return infra_observation(request_id)
        if not isinstance(code, str):
            return infra_observation(request_id)

        # Fail closed *before* creating any executable artefact or spawning a
        # process when the OS sandbox is not available.
        if not self._sandbox.available():
            return infra_observation(request_id)

        try:
            work_dir = Path(tempfile.mkdtemp(prefix=WORK_DIR_PREFIX))
        except OSError:
            return infra_observation(request_id)

        try:
            try:
                self._prepare_work_dir(work_dir, code)
            except OSError:
                return infra_observation(request_id)
            try:
                result = self._sandbox.run(
                    work_dir,
                    [WORKER_PYTHON, f"/worker/{WORKER_RUNNER_FILENAME}"],
                    timeout_value + self._timeout_grace_s,
                    stdin_data=request_text.encode("utf-8"),
                )
            except (SandboxUnavailable, SandboxLaunchError, OSError):
                return infra_observation(request_id)
            return self._interpret(result, request_id)
        finally:
            self._cleanup_work_dir(work_dir)

    # -- internals ------------------------------------------------------------

    @staticmethod
    def _coerce_timeout(timeout_s: float | None) -> float:
        if timeout_s is None:
            return DEFAULT_CASE_TIMEOUT_S
        if isinstance(timeout_s, bool) or not isinstance(timeout_s, (int, float)):
            raise protocol.WorkerProtocolError("timeout_s must be a number")
        value = float(timeout_s)
        if not MIN_CASE_TIMEOUT_S <= value <= MAX_CASE_TIMEOUT_S:
            raise protocol.WorkerProtocolError("timeout_s is outside the allowed range")
        return value

    def _prepare_work_dir(self, work_dir: Path, code: str) -> None:
        """Create the private read-only ``/worker`` directory for one case."""

        work_dir.chmod(0o700)
        solution_path = work_dir / SOLUTION_FILENAME
        solution_path.write_bytes(code.encode("utf-8"))
        solution_path.chmod(0o444)
        runner_path = work_dir / WORKER_RUNNER_FILENAME
        shutil.copyfile(self._runner_path, runner_path)
        runner_path.chmod(0o444)

    @staticmethod
    def _cleanup_work_dir(work_dir: Path) -> None:
        # Files are read-only for the sandbox user; the private directory is
        # owner-writable, so a recursive delete is safe and required.
        try:
            for child in work_dir.iterdir():
                try:
                    child.chmod(0o600)
                except OSError:
                    pass
            shutil.rmtree(work_dir, ignore_errors=True)
        except OSError:
            shutil.rmtree(work_dir, ignore_errors=True)

    @staticmethod
    def _interpret(result: SandboxResult, request_id: str) -> WorkerObservation:
        """Map a raw sandbox run to a fail-closed untrusted observation."""

        if result.timed_out:
            return timeout_observation(request_id)

        if not result.stdout:
            # A killed process (SIGKILL/SIGXCPU, e.g. RLIMIT_CPU exhaustion)
            # never produced a protocol line; treat it as a student timeout.
            if result.exit_code is not None and result.exit_code < 0:
                return timeout_observation(request_id)
            return infra_observation(request_id)

        try:
            observation = protocol.parse_worker_response(result.stdout)
        except protocol.WorkerProtocolError:
            if result.exit_code is not None and result.exit_code < 0:
                return timeout_observation(request_id)
            return infra_observation(request_id)

        if observation.request_id != request_id:
            return infra_observation(request_id)
        if (
            observation.status == protocol.WORKER_STATUS_TIMEOUT
            and not result.timed_out
        ):
            # The worker must not be able to claim a timeout the supervisor did
            # not observe; only the supervisor's own wall clock can say TLE.
            return infra_observation(request_id)
        if observation.status == protocol.WORKER_STATUS_COMPLETED and result.exit_code != 0:
            # The runner always emits its single line and exits 0; a non-zero
            # exit with a valid COMPLETED line indicates tampering.
            return infra_observation(request_id)
        return observation
