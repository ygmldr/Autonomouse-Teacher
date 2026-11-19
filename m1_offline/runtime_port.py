"""Mock-only runtime port for the M1 Offline Teacher.

Design goals
------------
* **Zero network.**  Nothing in this module imports an HTTP/socket stack.  The
  port exists so the Teacher Core can be exercised end-to-end without a real
  provider.
* **Deterministic.**  For a fixed ``seed`` and the same request bytes the mock
  returns byte-identical responses (text/usage/tool_events).  Replay is a
  matter of re-sending the same :class:`~m1_offline.types.RuntimeRequest`.
* **Error injection.**  Scripted entries may carry ``"error"`` (an error
  response is returned) or ``"raise": true`` (a transport-level failure is
  raised) so failure-mode handling can be tested.
* **Simulated marker.**  Every response sets ``simulated=True``; consumers must
  never mistake mock output for a real model call.  M0/live runtime
  capabilities remain UNVERIFIED; this port does not claim any.

Script format
-------------
``script`` is an optional dict with any of::

    {
      "responses": {request_id: entry},   # exact-match replay
      "queue":     [entry, ...],          # popped in order after responses miss
      "default":   entry,                 # fallback entry
      "error":     "message",             # global error injection (entry-level wins)
      "raise":     true | "message",      # simulate transport failure
    }

where ``entry`` is a dict with optional keys ``text`` (str), ``tool_events``
(list[dict]), ``usage`` (dict), ``error`` (str), ``raise`` (bool).

Resolution order: ``responses[request_id]`` -> next ``queue`` entry ->
``default`` -> generated deterministic reply.  When no entry defines ``text``
the text is generated from ``sha256(seed, request_id, last user content)`` so
it is reproducible and clearly synthetic.
"""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Protocol, runtime_checkable

from .types import RuntimeRequest, RuntimeResponse

__all__ = ["RuntimePort", "MockRuntimePort"]


@runtime_checkable
class RuntimePort(Protocol):
    """Abstract, provider-agnostic runtime boundary.

    The port only ever receives a :class:`RuntimeRequest` and returns a
    :class:`RuntimeResponse`; transport, credentials, retries, egress policy
    and accounting are explicitly *out of scope* for the M1 offline package.
    Any future live adapter must stay behind the same ``send`` boundary.
    """

    def send(self, request: RuntimeRequest) -> RuntimeResponse:
        """Send one request and return one response (never touches the network here)."""


def _stable_digest(*parts: Any) -> str:
    payload = "\x1f".join(str(part) for part in parts).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _last_user_content(messages: list[dict]) -> str:
    for message in reversed(messages):
        if isinstance(message, dict) and message.get("role") == "user":
            content = message.get("content", "")
            return content if isinstance(content, str) else json.dumps(content, sort_keys=True)
    return ""


class MockRuntimePort:
    """Deterministic, scriptable, network-free :class:`RuntimePort` implementation."""

    def __init__(self, script: dict | None = None, seed: int = 0):
        if script is not None and not isinstance(script, dict):
            raise TypeError(f"script must be dict | None, got {type(script).__name__}")
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise TypeError(f"seed must be int, got {type(seed).__name__}")
        self._script: dict = copy.deepcopy(script or {})
        self._seed = seed
        self._calls = 0
        self._queue_index = 0
        self._served: list[str] = []

    # -- introspection -----------------------------------------------------
    @property
    def simulated(self) -> bool:
        """Always ``True``: this port is a mock, never a real provider call."""

        return True

    @property
    def calls(self) -> int:
        """Number of ``send`` calls served so far (useful for audit/tests)."""

        return self._calls

    @property
    def served_request_ids(self) -> list[str]:
        """Request ids served so far, in order (a minimal mock trace)."""

        return list(self._served)

    @property
    def seed(self) -> int:
        return self._seed

    # -- resolution --------------------------------------------------------
    def _resolve_entry(self, request: RuntimeRequest) -> dict:
        responses = self._script.get("responses")
        if isinstance(responses, dict) and request.request_id in responses:
            entry = responses[request.request_id]
            if not isinstance(entry, dict):
                raise TypeError("script['responses'] entries must be dicts")
            return copy.deepcopy(entry)
        queue = self._script.get("queue")
        if isinstance(queue, list) and self._queue_index < len(queue):
            entry = queue[self._queue_index]
            self._queue_index += 1
            if not isinstance(entry, dict):
                raise TypeError("script['queue'] entries must be dicts")
            return copy.deepcopy(entry)
        default = self._script.get("default")
        if isinstance(default, dict):
            return copy.deepcopy(default)
        return {}

    def _build_response(self, request: RuntimeRequest, entry: dict) -> RuntimeResponse:
        raise_mode = entry.get("raise", self._script.get("raise"))
        if raise_mode:
            message = raise_mode if isinstance(raise_mode, str) else "scripted mock transport failure"
            raise RuntimeError(f"MockRuntimePort: {message}")

        error = entry.get("error", self._script.get("error"))
        if error is not None and not isinstance(error, str):
            raise TypeError("scripted 'error' must be str")
        if error is not None:
            return RuntimeResponse(
                request_id=request.request_id,
                session_id=request.session_id,
                text="",
                tool_events=[],
                usage={},
                error=error,
                simulated=True,
            )

        digest = _stable_digest(self._seed, request.request_id, _last_user_content(request.messages))
        text = entry.get("text")
        if text is None:
            text = (
                f"[mock-runtime seed={self._seed} request={request.request_id}] "
                f"synthetic reply digest={digest[:12]}"
            )
        if not isinstance(text, str):
            raise TypeError("scripted 'text' must be str")

        tool_events = entry.get("tool_events", [])
        if not isinstance(tool_events, list) or not all(
            isinstance(event, dict) for event in tool_events
        ):
            raise TypeError("scripted 'tool_events' must be list[dict]")

        usage = entry.get("usage")
        if usage is None:
            prompt_tokens = len(_last_user_content(request.messages)) // 4 + 1
            usage = {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": len(text) // 4 + 1,
                "total_tokens": prompt_tokens + len(text) // 4 + 1,
                "source": "mock",
            }
        if not isinstance(usage, dict):
            raise TypeError("scripted 'usage' must be dict")

        return RuntimeResponse(
            request_id=request.request_id,
            session_id=request.session_id,
            text=text,
            tool_events=copy.deepcopy(tool_events),
            usage=copy.deepcopy(usage),
            error=None,
            simulated=True,
        )

    # -- RuntimePort -------------------------------------------------------
    def send(self, request: RuntimeRequest) -> RuntimeResponse:
        if not isinstance(request, RuntimeRequest):
            raise TypeError(f"send expects RuntimeRequest, got {type(request).__name__}")
        self._calls += 1
        self._served.append(request.request_id)
        entry = self._resolve_entry(request)
        return self._build_response(request, entry)
