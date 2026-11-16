"""G3-A real-DSH provider-bridge suite. Execute ONLY inside the fixed no-Key container.

Runs the locked 0.2.2-rc.2 Node SEA runtime through the real Python SDK against a
public Cordis LlmAdapter that forwards over stdio to an independent Python
fake-provider process. Synthetic fixture only: no Key, no HTTP, no model.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import yaml

ENV = {
    "PATH": "/opt/python/bin:/usr/bin",
    "HOME": "/work/user-home",
    "PYTHONPATH": "/deps",
    "PYTHONDONTWRITEBYTECODE": "1",
    "TMPDIR": "/tmp",
}
assert set(os.environ) <= set(ENV) | {"HOSTNAME"}, sorted(os.environ)
os.environ.clear()
os.environ.update(ENV)
Path("/work/user-home").mkdir(parents=True, exist_ok=True)
Path("/work/config-inspection").mkdir(parents=True, exist_ok=True)

RESULTS = []


def emit(kind: str, **data: object) -> None:
    print(json.dumps({"kind": kind, **data}, sort_keys=True), flush=True)


def utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def check_isolation() -> dict:
    mounts = {}
    for line in Path("/proc/self/mountinfo").read_text().splitlines():
        parts = line.split()
        if parts[4] in ("/", "/probe", "/deps", "/tmp", "/work"):
            mounts[parts[4]] = parts[5].split(",")
    assert os.getuid() == 65534, os.getuid()
    assert all("ro" in mounts[path] for path in ("/", "/probe", "/deps")), mounts
    assert all("noexec" in mounts[path] for path in ("/tmp", "/work")), mounts
    binary = Path("/deps/deepseek_harness_runtime/runtime/deepseek-harness-sdk-runtime-linux-x64")
    binary_sha = sha256(binary.read_bytes())
    assert binary_sha == "1cc41d5a8745a5b9d47c8604e44f23eb8af2d8ca02b2afa0be101d5f71be6ea4", binary_sha
    native = Path("/probe/native-cache/node-addon-require-builtin-linux-x64-gnu/0.1.9/linux-x64-gnu/linux-x64-gnu-napi-v9.node")
    assert sha256(native.read_bytes()) == "40c34d27d8339e246a8f7415a06152935496cdc06555ea8fce0e052011acc70f"
    assert native.stat().st_mode & 0o222 == 0
    pkg = Path("/probe/pkg-cache/pkg/dfa6d5861f51ddb5112a7c92e560752d79c2a89362c0634c8d4f0fc888b21487/@deepseek-ai/node-addon-system-linux-x64/bin/glibc/system.node")
    assert sha256(pkg.read_bytes()) == "dfa6d5861f51ddb5112a7c92e560752d79c2a89362c0634c8d4f0fc888b21487"
    node_version = subprocess.run(["/usr/bin/node", "--version"], capture_output=True, text=True, timeout=10)
    runtime_version = subprocess.run([str(binary), "--version"], capture_output=True, text=True, timeout=10)
    assert node_version.returncode == 0 and node_version.stdout.strip() == "v22.23.2", node_version
    assert runtime_version.returncode == 0 and runtime_version.stdout.strip() == "0.2.2-rc.2", runtime_version
    assert not Path("/var").exists(), "canonical rootfs must not contain an injected /var tree"
    return {
        "uid": os.getuid(),
        "mounts": mounts,
        "binary_sha256": binary_sha,
        "native_cache_sha256": sha256(native.read_bytes()),
        "pkg_cache_sha256": sha256(pkg.read_bytes()),
        "node_version": node_version.stdout.strip(),
        "runtime_version": runtime_version.stdout.strip(),
        "pkg_cache_file_count": sum(1 for path in Path("/probe/pkg-cache").rglob("*") if path.is_file()),
        "rootfs_var_absent": True,
        "environment_names": sorted(os.environ),
        "memory_max": Path("/sys/fs/cgroup/memory.max").read_text().strip(),
        "pids_max": Path("/sys/fs/cgroup/pids.max").read_text().strip(),
        "cpu_max": Path("/sys/fs/cgroup/cpu.max").read_text().strip(),
    }


def parse_worker(stdout: str) -> tuple[list[dict], dict | None]:
    parsed = []
    final = None
    for line in stdout.splitlines():
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        parsed.append(item)
        if item.get("kind") == "result":
            final = item
    return parsed, final


def run_case(name: str, *, interrupt: bool = False) -> dict:
    argv = [sys.executable, "/probe/run/worker.py", json.dumps({"case": name}, sort_keys=True)]
    start = utc()
    started = time.monotonic()
    if not interrupt:
        proc = subprocess.run(argv, env=dict(ENV), cwd="/work", capture_output=True, text=True, timeout=35)
        stdout, stderr, status = proc.stdout, proc.stderr, proc.returncode
    else:
        child = subprocess.Popen(
            argv, env=dict(ENV), cwd="/work", stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1,
        )
        prefix: list[str] = []
        killed = False
        try:
            while True:
                line = child.stdout.readline()
                if not line:
                    raise AssertionError(f"{name}: worker exited before cancel-ready")
                prefix.append(line)
                item = json.loads(line)
                if item.get("kind") == "cancel-ready":
                    assert isinstance(item.get("runtime_pid"), int)
                    os.kill(item["runtime_pid"], signal.SIGTERM)
                    killed = True
                    break
            rest, stderr = child.communicate(timeout=20)
            stdout = "".join(prefix) + rest
            status = child.returncode
        finally:
            if child.poll() is None:
                child.kill()
                child.wait()
        assert killed, f"{name}: never reached a genuine active bridge request"
    parsed, final = parse_worker(stdout)
    record = {
        "name": name,
        "argv": argv,
        "started_utc": start,
        "finished_utc": utc(),
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "exit_code": status,
        "stdout": stdout,
        "stderr": stderr,
        "data": final,
    }
    RESULTS.append(record)
    emit("case", **record)
    assert status == 0 and final is not None, f"{name}: exit={status} final={final}"
    return final


def events(data: dict) -> list[dict]:
    return data["result"]["events"]


def request_headers(data: dict) -> list[dict]:
    return [event["data"]["header"] for event in events(data) if event["type"] == "request/header"]


def receipts(data: dict) -> list[dict]:
    return [item["json"] for item in data["fake_receipt_files"] if item["path"].endswith(".json") and "json" in item]


def trace_events(data: dict) -> list[list[dict]]:
    traces = []
    for item in data["bridge_trace_files"]:
        raw = base64.b64decode(item["base64"]).decode("utf-8")
        traces.append([json.loads(line) for line in raw.splitlines() if line])
    return traces


def assistant_messages(data: dict) -> list[dict]:
    return [event for event in events(data) if event["type"] == "assistant/message"]


def tool_events(data: dict, kind: str) -> list[dict]:
    return [event for event in events(data) if event["type"] == kind]


def assert_identity(data: dict) -> None:
    trace_sets = trace_events(data)
    receipt_list = receipts(data)
    assert len(trace_sets) == len(receipt_list), (len(trace_sets), len(receipt_list))
    for trace, receipt in zip(trace_sets, receipt_list):
        request = next(item for item in trace if item["event"] == "request")
        ack = next(item for item in trace if item["event"] == "ack")
        assert request["requestId"] == receipt["requestId"] == ack["requestId"]
        assert request["requestSha256"] == receipt["rawRequestSha256"] == ack["rawRequestSha256"]
        assert receipt["realModelCalls"] == 0 and receipt["httpCalls"] == 0 and receipt["networkUsed"] is False
        assert request["realModelCalls"] == 0 and request["httpCalls"] == 0


def assert_usage(data: dict, expected: dict) -> None:
    assistant = assistant_messages(data)[-1]
    assert assistant["data"]["usage"] == expected, assistant["data"]["usage"]
    assert assistant["data"]["message"]["source"]["provider"] == "g3a-bridge-test"
    assert assistant["data"]["message"]["source"]["model"] == "bridge-v1"


isolation = check_isolation()
emit("isolation", **isolation)

# 1. Prompt -> public adapter -> real Python child -> streaming chunks -> DSH.
echo = run_case("echo")
assert echo["error"] is None and echo["close_error"] is None
assert echo["result"]["final_response"] == "G3A_BRIDGE_ECHO:G3A_PUBLIC_ECHO_a7f3", echo["result"]["final_response"]
assert echo["result"]["finish_reason"] == "completed", echo["result"]["finish_reason"]
headers = request_headers(echo)
assert headers and all(header["config"] == {"provider": "g3a-bridge-test", "model": "bridge-v1", "maxTokens": 256} for header in headers)
assert headers[-1]["tools"][0]["name"] == "skill_lookup"
assert_usage(echo, {"inputTokens": 11, "outputTokens": 5, "cacheReadTokens": 2, "cacheWriteTokens": 0, "reasoningTokens": 0, "totalTokens": 18})
assert_identity(echo)
assert len(receipts(echo)) == 1 and receipts(echo)[0]["mode"] == "echo"
echo_trace = trace_events(echo)[0]
assert any(item["event"] == "finish" and item["reason"]["kind"] == "stop" for item in echo_trace)
assert echo_trace[-1]["event"] == "cleanup" and echo_trace[-1]["exitCode"] == 0, echo_trace[-1]
assert len([item for item in echo_trace if item["event"] == "chunk" and item["chunk"]["type"] == "text-delta"]) == 2

# 2. A new worker process resumes the real Session; the prior user nonce is in the
# assembled history sent over the bridge, and the external fake recalls it.
recall = run_case("recall")
assert recall["error"] is None and recall["close_error"] is None
assert recall["result"]["final_response"] == "G3A_BRIDGE_RECALL:G3A_PUBLIC_ECHO_a7f3", recall["result"]["final_response"]
assert recall["result"]["finish_reason"] == "completed"
assert_identity(recall)
assert len(receipts(recall)) == 1
receipt = receipts(recall)[0]
assert receipt["mode"] == "recall"
assert "G3A_RECALL" in receipt["userTexts"] and any("G3A_PUBLIC_ECHO_a7f3" in text for text in receipt["userTexts"])
roles = receipt["roles"]
assert "assistant" in roles and roles.count("user") >= 2, roles

# 3. Real tool schema crosses the bridge; fake emits a tool-call; real DSH executes
# the reviewed skill_lookup; a second bridge request carries the real tool result.
tool = run_case("tool")
assert tool["error"] is None and tool["close_error"] is None
assert tool["result"]["final_response"] == "G3A_TOOL_RESULT:binary_search:3:false", tool["result"]["final_response"]
assert tool["result"]["finish_reason"] == "completed"
assert len(request_headers(tool)) == 1, request_headers(tool)
calls = tool_events(tool, "tool/call")
results = tool_events(tool, "tool/result")
assert len(calls) == 1 and calls[0]["data"]["name"] == "skill_lookup"
assert len(results) == 1 and results[0]["data"]["message"]["isError"] is False
assert results[0]["data"]["message"]["toolCallId"] == calls[0]["data"]["callId"]
assert_usage(tool, {"inputTokens": 11, "outputTokens": 5, "cacheReadTokens": 2, "cacheWriteTokens": 0, "reasoningTokens": 0, "totalTokens": 18})
assert_identity(tool)
tool_receipts = receipts(tool)
assert len(tool_receipts) == 2 and [item["mode"] for item in tool_receipts] == ["tool", "tool-final"]
assert tool_receipts[0]["tools"][0]["name"] == "skill_lookup"
second_roles = tool_receipts[1]["roles"]
assert "tool" in second_roles, second_roles
tool_message = next(message for message in reversed(tool_receipts[1]["messages"]) if message.get("role") == "tool")
rendered = "".join(block.get("text", "") for block in tool_message["content"] if block.get("type") == "text")
assert json.loads(rendered)["prerequisites"] == ["ordered_search_space", "monotonicity", "loop_invariants"]
assert tool_message.get("isError") is False
for trace in trace_events(tool):
    assert trace[-1]["event"] == "cleanup" and trace[-1]["exitCode"] == 0, trace[-1]

# 4. External child EOF before a finish chunk must not become a successful turn.
eof = run_case("eof")
assert eof["error"] is not None or eof["result"]["finish_reason"] in ("error", "aborted", "blocked"), eof["error"]
assert eof["result"]["final_response"] == "" or eof["result"]["final_response"] is None
assert len(receipts(eof)) == 1 and receipts(eof)[0]["mode"] == "eof"
eof_trace = trace_events(eof)[0]
assert not any(item["event"] == "finish" for item in eof_trace)
assert eof_trace[-1]["event"] == "cleanup" and eof_trace[-1]["exitCode"] == 0, eof_trace[-1]
assert_identity(eof)

# 5. An external synthetic error finish is surfaced as error, not success.
failure = run_case("error")
assert failure["result"]["finish_reason"] == "error" or failure["error"] is not None
assert failure["result"]["final_response"] == "" or failure["result"]["final_response"] is None or failure["error"] is not None
assert len(receipts(failure)) == 1 and receipts(failure)[0]["mode"] == "error"
failure_trace = trace_events(failure)[0]
assert any(item["event"] == "finish" and item["reason"]["kind"] == "error" for item in failure_trace)

# 6. SIGTERM the real runtime during an active bridge stream. The external child
# must not survive its parent. This is runtime termination, not a DSH AbortSignal API.
cancel = run_case("cancel", interrupt=True)
assert cancel["cancel_ready"] is True
assert cancel["error"] is not None, cancel.get("error")
assert cancel["error"]["type"] in ("TransportClosedError", "SdkProtocolError"), cancel["error"]
assert cancel["fake_pid"] is not None
assert cancel["fake_alive_after_runtime_term"] is False, cancel["fake_alive_after_runtime_term"]
assert len(receipts(cancel)) == 1 and receipts(cancel)[0]["mode"] == "slow"
cancel_trace = trace_events(cancel)[0]
assert any(item["event"] == "spawn" for item in cancel_trace)
assert any(item["event"] == "ack" for item in cancel_trace)
assert not any(item["event"] == "finish" for item in cancel_trace)

# 7. The true merged config of the launched runtime disables every real provider.
class Inert(yaml.SafeLoader):
    pass


Inert.add_constructor("tag:yaml.org,2002:js", lambda loader, node: loader.construct_scalar(node))
binary = "/deps/deepseek_harness_runtime/runtime/deepseek-harness-sdk-runtime-linux-x64"
dump = subprocess.run(
    [binary, "--profile", "sdk-minimal", "--patch", "/probe/config/bridge.patch.yml", "--dump-config"],
    env={**ENV, "DSH_HOME": "/work/config-inspection", "NO_COLOR": "1"},
    cwd="/work", capture_output=True, text=True, timeout=25,
)
emit("merged-config", argv=dump.args, exit_code=dump.returncode, stdout=dump.stdout, stderr=dump.stderr, utc=utc())
assert dump.returncode == 0, dump.stderr
rows = {row["id"]: row for row in yaml.load(dump.stdout, Loader=Inert)}
assert rows["llm-deepseek"]["disabled"] is True
assert rows["session-log-deepseek"]["config"]["enabled"] is False
assert rows["plugin-package-inventory-deepseek"]["disabled"] is True
assert rows["g3a-bridge-provider"]["name"] in ("/probe/runtime/bridge/lib/index.js", "file:///probe/runtime/bridge/lib/index.js")
assert rows["offline-public-skill"]["name"] in ("/probe/runtime/skill/lib/index.js", "file:///probe/runtime/skill/lib/index.js")
assert "runtime-budget-guard" not in rows or rows["runtime-budget-guard"].get("disabled") is True
assert "llm-pi-ai" not in rows or rows.get("llm-pi-ai", {}).get("disabled") is True

requests = sum(len(receipts(item["data"])) for item in RESULTS)
traces = sum(len(trace_events(item["data"])) for item in RESULTS)
emit(
    "summary",
    status="PASS-real-dsh-sdk-public-provider-bridge-synthetic-only",
    cases=len(RESULTS),
    bridge_requests=requests,
    bridge_traces=traces,
    echo_streaming_deltas=2,
    tool_roundtrip=True,
    session_resume=True,
    eof_failure_surfaced=True,
    error_finish_surfaced=True,
    runtime_sigterm_child_reaped=True,
    tool_schema_seen=True,
    usage_synthetic={"inputTokens": 11, "outputTokens": 5, "cacheReadTokens": 2, "cacheWriteTokens": 0, "reasoningTokens": 0, "totalTokens": 18},
    guard_in_profile=False,
    real_model_calls=0,
    http_calls=0,
    network_enabled=False,
    production_adapter_used=False,
)
