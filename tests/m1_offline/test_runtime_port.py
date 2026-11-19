"""Mock runtime port tests: determinism, simulated marker, error injection, no egress."""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

import m1_offline
from m1_offline.runtime_port import MockRuntimePort, RuntimePort
from m1_offline.types import RuntimeRequest, RuntimeResponse


def _request(request_id: str = "req-001", content: str = "synthetic prompt") -> RuntimeRequest:
    return RuntimeRequest(
        request_id=request_id,
        session_id="session-001",
        messages=[{"role": "user", "content": content}],
        tools=[],
        metadata={"mock": True},
    )


def test_mock_port_satisfies_protocol():
    assert isinstance(MockRuntimePort(), RuntimePort)


def test_mock_port_always_marks_simulated():
    port = MockRuntimePort()
    response = port.send(_request())
    assert response.simulated is True
    assert isinstance(response, RuntimeResponse)
    assert response.request_id == "req-001"
    assert response.session_id == "session-001"
    assert response.error is None
    assert port.simulated is True


def test_same_seed_same_output():
    first = MockRuntimePort(seed=42).send(_request())
    second = MockRuntimePort(seed=42).send(_request())
    assert first.to_dict() == second.to_dict()
    assert first.text.startswith("[mock-runtime")
    assert "seed=42" in first.text


def test_same_seed_is_stable_across_repeated_calls():
    port = MockRuntimePort(seed=7)
    outputs = [port.send(_request()).to_dict() for _ in range(3)]
    # Generated mock replies depend only on (seed, request), never on call count.
    assert outputs[0] == outputs[1] == outputs[2]
    assert port.calls == 3
    assert port.served_request_ids == ["req-001", "req-001", "req-001"]


def test_different_seed_changes_generated_output():
    first = MockRuntimePort(seed=1).send(_request())
    second = MockRuntimePort(seed=2).send(_request())
    assert first.text != second.text


def test_scripted_replay_by_request_id():
    script = {
        "responses": {
            "req-001": {
                "text": "scripted synthetic answer",
                "tool_events": [{"tool": "mock_calc", "status": "ok"}],
                "usage": {"total_tokens": 11, "source": "mock"},
            }
        }
    }
    port = MockRuntimePort(script=script)
    response = port.send(_request())
    assert response.text == "scripted synthetic answer"
    assert response.tool_events == [{"tool": "mock_calc", "status": "ok"}]
    assert response.usage == {"total_tokens": 11, "source": "mock"}
    assert response.simulated is True


def test_scripted_queue_is_consumed_in_order():
    script = {"queue": [{"text": "turn-1"}, {"text": "turn-2"}]}
    port = MockRuntimePort(script=script)
    assert port.send(_request("req-001")).text == "turn-1"
    assert port.send(_request("req-002")).text == "turn-2"
    # Queue exhausted -> deterministic generated reply.
    assert port.send(_request("req-003")).text.startswith("[mock-runtime")


def test_error_injection_top_level():
    port = MockRuntimePort(script={"error": "synthetic provider failure"})
    response = port.send(_request())
    assert response.error == "synthetic provider failure"
    assert response.text == ""
    assert response.simulated is True


def test_error_injection_per_request():
    script = {
        "responses": {"req-bad": {"error": "scripted error response"}},
        "default": {"text": "ok"},
    }
    port = MockRuntimePort(script=script)
    assert port.send(_request("req-bad")).error == "scripted error response"
    healthy = port.send(_request("req-ok"))
    assert healthy.error is None
    assert healthy.text == "ok"


def test_error_injection_can_raise_transport_failure():
    port = MockRuntimePort(script={"raise": True})
    with pytest.raises(RuntimeError, match="MockRuntimePort"):
        port.send(_request())


#: Network-stack modules the mock port must never import or load.
NETWORK_MODULES = frozenset(
    {"httpx", "requests", "urllib", "urllib3", "aiohttp", "socket", "ssl", "http"}
)
NETWORK_RUNTIME_MODULES = frozenset(
    {"socket", "ssl", "http", "http.client", "urllib.request", "httpx", "requests", "aiohttp"}
)


def test_mock_port_module_has_no_network_imports():
    """Static check: the mock port source never imports a network stack."""

    module_path = Path(m1_offline.runtime_port.__file__).resolve()
    tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            imported.add(node.module.split(".")[0])
    assert not (imported & NETWORK_MODULES), sorted(imported & NETWORK_MODULES)


def test_mock_port_does_no_network():
    """Runtime check in a fresh interpreter: using the mock loads no network stack."""

    script = """
import json
import sys

from m1_offline.runtime_port import MockRuntimePort
from m1_offline.types import RuntimeRequest

response = MockRuntimePort(seed=3).send(
    RuntimeRequest(
        request_id="req-net",
        session_id="session-001",
        messages=[{"role": "user", "content": "synthetic prompt"}],
    )
)
loaded = sorted(
    name for name in sys.modules if name in %r
)
print(json.dumps({
    "simulated": response.simulated,
    "error": response.error,
    "loaded": loaded,
}))
""" % (
        sorted(NETWORK_RUNTIME_MODULES),
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(Path(m1_offline.__file__).resolve().parents[1]),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout.strip().splitlines()[-1])
    assert payload["simulated"] is True
    assert payload["error"] is None
    assert payload["loaded"] == [], payload


def test_invalid_inputs_fail_closed():
    with pytest.raises(TypeError):
        MockRuntimePort(script="not-a-dict")
    with pytest.raises(TypeError):
        MockRuntimePort(seed="1")
    port = MockRuntimePort()
    with pytest.raises(TypeError):
        port.send({"request_id": "x"})  # type: ignore[arg-type]
    bad = MockRuntimePort(script={"responses": {"req-001": "oops"}})
    with pytest.raises(TypeError):
        bad.send(_request())


def test_response_roundtrips_as_record():
    response = MockRuntimePort(seed=5).send(_request())
    restored = RuntimeResponse.from_dict(response.to_dict())
    assert restored == response
    assert restored.simulated is True
