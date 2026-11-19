"""G4-F2 adapter-boundary evidence: auxiliary purpose never opens the bridge.

The candidate adapter is the only DSH provider in the G4 overlay. Its purpose
guard runs before the AF_UNIX connect, so an auxiliary (session-title style)
provider call cannot reach the trusted Controller/Reserve/Claim at all. The
probe runs the real built adapter from the newest G4-C stage (read-only); it
never starts DSH, a container, a provider or a network connection.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
PROBE = Path(__file__).resolve().parent / "adapter_purpose_probe.mjs"
STAGE_ROOT = REPO / "artifacts" / "g4" / "c" / "stages"


def _adapter() -> Path | None:
    if not STAGE_ROOT.is_dir():
        return None
    candidates = sorted(
        (path for path in STAGE_ROOT.glob("stage-*")
         if (path / "candidate/runtime/bridge/lib/index.js").is_file()),
        key=lambda path: path.stat().st_mtime)
    if not candidates:
        return None
    return candidates[-1] / "candidate/runtime/bridge/lib/index.js"


def test_adapter_rejects_auxiliary_purpose_before_the_socket() -> None:
    node = shutil.which("node")
    adapter = _adapter()
    if node is None or adapter is None:
        pytest.skip("node or a G4-C stage adapter is unavailable")
    proc = subprocess.run([node, str(PROBE), str(adapter)], capture_output=True,
                          text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr[-2000:]
    lines = [line for line in proc.stdout.splitlines() if line.startswith("{")]
    assert lines, proc.stdout[-2000:]
    report = json.loads(lines[-1])
    assert report["provider"] == "offline-test-only-g3b"
    assert report["model"] == "fixture-bridge-v1"
    assert report["bridge_socket"] == "/work/g3b/bridge.sock"
    # Auxiliary purpose: rejected by the adapter guard, before any connect.
    assert report["title"]["outcome"] == "error"
    assert report["title"]["message"] == "G3B_BRIDGE_PURPOSE"
    assert report["title"]["code"] == "INVALID_REQUEST"
    # Conversation purpose: passes the guard and only then misses the socket.
    assert report["conversation"]["outcome"] == "error"
    assert report["conversation"]["message"] == "G3B_BRIDGE_CONNECT_FAILED"
