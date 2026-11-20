"""Single-case worker runner executed *inside* the bwrap sandbox (B-PR1).

This file is copied read-only into the per-case ``/worker`` bind mount and run
as ``/usr/bin/python3 /worker/worker_runner.py`` by
:class:`m1_teacher.assessment.judge.sandbox.BwrapSandbox`.

Contract
--------
* reads **one** JSON request from stdin (``function_name`` + ``args`` only; no
  expected/tests/verdict/paths are ever provided);
* imports ``/worker/solution.py`` once, calls the requested function once with
  the request arguments;
* reports only an *observation*: ``status`` + canonicalised actual value or an
  exception class name, plus bounded learner stdout/stderr excerpts;
* writes exactly one ``M1B_WORKER_RESPONSE``-equivalent protocol line to the
  dedicated protocol fd (the original stdout, duplicated before learner code can
  write anything) and then calls ``os._exit(0)`` so learner ``atexit``/``finally``
  handlers cannot rewrite the response;
* never emits a verdict/passed/score field and never sees hidden expectations.

The runner duplicates the frozen constants from
:mod:`m1_teacher.assessment.judge.protocol` because it must be self-contained
inside the sandbox (only the minimal read-only rootfs is mounted there).
"""

import json
import os
import re
import resource
import sys
import types

PROTOCOL_VERSION = "m1b.judge.worker.v1"

# Mirrors protocol.py (see the deviation note there): trusted supervisor only.
MAX_REQUEST_BYTES = 2 * 1024 * 1024
MAX_ARGS_BYTES = 1024 * 1024
MAX_ARGS_NODES = 1024 * 1024
MAX_ACTUAL_CANONICAL_BYTES = 64 * 1024
MAX_EXCERPT_BYTES = 4096
MIN_TIMEOUT_MS = 50
MAX_TIMEOUT_MS = 5000

REQUEST_FIELDS = frozenset(
    {
        "schema_version",
        "request_id",
        "function_name",
        "args",
        "timeout_ms",
        "stdout_limit",
        "stderr_limit",
    }
)

FUNCTION_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
EXCEPTION_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]{0,127}$")
REQUEST_ID_RE = re.compile(r"^[a-f0-9]{16,64}$")

# Effective per-sandbox process limit for learner code.  The host-side
# RLIMIT_NPROC must stay permissive (a tight value would break bwrap itself,
# since it counts processes of the *host* uid); inside the user/PID namespace we
# can enforce the intended limit.
RLIMIT_NPROC_INNER = 32

SOLUTION_PATH = "/worker/solution.py"


def _write_stdout_line(payload):
    line = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        allow_nan=False,
        separators=(",", ":"),
    )
    os.write(_PROTOCOL_FD, line.encode("utf-8") + b"\n")


def _no_duplicates(pairs):
    seen = set()
    for key, _value in pairs:
        if key in seen:
            raise ValueError("duplicate key")
        seen.add(key)
    return dict(pairs)


def _no_constants(value):
    raise ValueError("non-finite number")


def _canonical(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        allow_nan=False,
        separators=(",", ":"),
    )


def _validate_args(args):
    if not isinstance(args, list):
        raise ValueError("args must be a list")
    nodes = 0

    def walk(value, depth):
        nonlocal nodes
        nodes += 1
        if nodes > MAX_ARGS_NODES or depth > 4:
            raise ValueError("args budget exceeded")
        if isinstance(value, dict):
            for key, item in value.items():
                if not isinstance(key, str):
                    raise ValueError("bad object key")
                walk(item, depth + 1)
        elif isinstance(value, list):
            for item in value:
                walk(item, depth + 1)
        elif isinstance(value, bool) or value is None or isinstance(value, (str, int, float)):
            return
        else:
            raise ValueError("non-JSON argument")

    walk(args, 1)
    if len(_canonical(args).encode("utf-8")) > MAX_ARGS_BYTES:
        raise ValueError("args too large")


def _parse_request(raw):
    if len(raw) > MAX_REQUEST_BYTES:
        raise ValueError("request too large")
    text = raw.decode("utf-8")
    if not text.strip():
        raise ValueError("empty request")
    payload = json.loads(text, object_pairs_hook=_no_duplicates, parse_constant=_no_constants)
    if not isinstance(payload, dict):
        raise ValueError("request must be an object")
    if set(payload) != REQUEST_FIELDS:
        raise ValueError("request fields mismatch")
    if payload["schema_version"] != PROTOCOL_VERSION:
        raise ValueError("protocol version mismatch")
    if not isinstance(payload["request_id"], str) or not REQUEST_ID_RE.fullmatch(
        payload["request_id"]
    ):
        raise ValueError("bad request id")
    if not isinstance(payload["function_name"], str) or not FUNCTION_NAME_RE.fullmatch(
        payload["function_name"]
    ):
        raise ValueError("bad function name")
    _validate_args(payload["args"])
    timeout_ms = payload["timeout_ms"]
    if type(timeout_ms) is not int or not MIN_TIMEOUT_MS <= timeout_ms <= MAX_TIMEOUT_MS:
        raise ValueError("bad timeout")
    for key in ("stdout_limit", "stderr_limit"):
        limit = payload[key]
        if type(limit) is not int or not 0 <= limit <= MAX_EXCERPT_BYTES:
            raise ValueError("bad excerpt limit")
    return payload


class _BoundedSink:
    """Bounded text sink so learner output cannot amplify memory/log volume."""

    encoding = "utf-8"
    errors = "replace"

    def __init__(self, limit):
        self._limit = int(limit)
        self._chunks = []
        self._size = 0
        self._closed = False
        self.buffer = _BoundedBuffer(self)

    def write(self, text):
        if self._closed:
            return 0
        if not isinstance(text, str):
            text = str(text)
        encoded = text.encode("utf-8", "replace")
        if self._size < self._limit and encoded:
            take = encoded[: self._limit - self._size]
            self._chunks.append(take)
            self._size += len(take)
        return len(text)

    def flush(self):
        return None

    def close(self):
        self._closed = True

    def writable(self):
        return True

    def fileno(self):
        return 1

    def isatty(self):
        return False

    def getvalue(self):
        return b"".join(self._chunks).decode("utf-8", "replace")


class _BoundedBuffer:
    def __init__(self, sink):
        self._sink = sink

    def write(self, data):
        if isinstance(data, (bytes, bytearray)):
            data = bytes(data).decode("utf-8", "replace")
        self._sink.write(data)
        return len(data)

    def flush(self):
        return None


def _apply_inner_limits():
    for limit, soft, hard in (
        (resource.RLIMIT_NPROC, RLIMIT_NPROC_INNER, RLIMIT_NPROC_INNER),
        (resource.RLIMIT_CORE, 0, 0),
    ):
        resource.setrlimit(limit, (soft, hard))


def _safe_exception_name(exc):
    name = type(exc).__name__
    if isinstance(name, str) and EXCEPTION_NAME_RE.fullmatch(name):
        return name
    return "Exception"


def _execute(payload):
    """Execute the single case and return ``(status, actual_canonical, exception_type)``."""

    function_name = payload["function_name"]
    try:
        with open(SOLUTION_PATH, "r", encoding="utf-8") as handle:
            source = handle.read()
    except OSError:
        return "IMPORT_ERROR", None, "OSError"

    try:
        compiled = compile(source, "solution.py", "exec")
    except SyntaxError:
        return "SYNTAX_ERROR", None, "SyntaxError"

    module = types.ModuleType("solution")
    module.__dict__["__file__"] = SOLUTION_PATH
    try:
        exec(compiled, module.__dict__)
    except BaseException as exc:  # learner import-time failure is student evidence
        return "IMPORT_ERROR", None, _safe_exception_name(exc)

    function = module.__dict__.get(function_name)
    if not callable(function):
        return "MISSING_FUNCTION", None, None

    try:
        value = function(*payload["args"])
    except BaseException as exc:  # SystemExit/KeyboardInterrupt are learner evidence too
        return "RAISED", None, _safe_exception_name(exc)

    try:
        actual = _canonical(value)
    except (TypeError, ValueError):
        return "RAISED", None, "UnserializableActual"
    if len(actual.encode("utf-8")) > MAX_ACTUAL_CANONICAL_BYTES:
        return "RAISED", None, "UnserializableActual"
    return "COMPLETED", actual, None


_PROTOCOL_FD = -1


def _open_protocol_channel():
    """Duplicate the protocol fd and redirect learner-visible stdout/stderr.

    Done inside ``main`` (never at import time) so importing this module in a
    host test process has no side effects.  Learner code runs only after this
    redirection, so its prints cannot reach the protocol channel.
    """

    global _PROTOCOL_FD, _DEVNULL_FD
    _PROTOCOL_FD = os.dup(1)
    _DEVNULL_FD = os.open(os.devnull, os.O_WRONLY)
    os.dup2(_DEVNULL_FD, 1)
    os.dup2(_DEVNULL_FD, 2)


def main():
    request_id = ""
    _open_protocol_channel()
    try:
        payload = _parse_request(sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1))
    except BaseException:
        _write_stdout_line(
            {
                "schema_version": PROTOCOL_VERSION,
                "request_id": request_id,
                "status": "INFRA_ERROR",
                "actual_canonical": None,
                "exception_type": None,
                "stdout_excerpt": "",
                "stderr_excerpt": "",
            }
        )
        os._exit(0)

    request_id = payload["request_id"]
    stdout_sink = _BoundedSink(payload["stdout_limit"])
    stderr_sink = _BoundedSink(payload["stderr_limit"])
    sys.stdout = stdout_sink
    sys.stderr = stderr_sink

    try:
        _apply_inner_limits()
    except (OSError, ValueError):
        status, actual, exception_type = "INFRA_ERROR", None, None
    else:
        status, actual, exception_type = _execute(payload)

    response = {
        "schema_version": PROTOCOL_VERSION,
        "request_id": request_id,
        "status": status,
        "actual_canonical": actual,
        "exception_type": exception_type,
        "stdout_excerpt": stdout_sink.getvalue(),
        "stderr_excerpt": stderr_sink.getvalue(),
    }
    try:
        _write_stdout_line(response)
    except BaseException:
        os._exit(1)
    os._exit(0)


if __name__ == "__main__":
    try:
        main()
    except BaseException:
        os._exit(1)
