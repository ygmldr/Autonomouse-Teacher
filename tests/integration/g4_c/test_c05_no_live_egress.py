"""G4-C: no second egress path, no live unlock, gates/run_live remain frozen."""
from __future__ import annotations

import ast
import os
from pathlib import Path
import subprocess
import sys

from autoteacher_m0.security.egress import (
    SYNTHETIC_ROUTE_CONTRACT,
    TrustedSendAuthorization,
)
from autoteacher_m0.security.gates import LiveGate, SecurityBlocked

REPO = Path(__file__).resolve().parents[3]
SRC = REPO / "src" / "autoteacher_m0"


def _python_files() -> list[Path]:
    return sorted(path for path in SRC.rglob("*.py"))


def test_c05_no_http_client_imports_in_product_src() -> None:
    forbidden = ("requests", "httpx", "aiohttp", "urllib.request",
                 "urllib3", "http.client", "websockets")
    offenders = []
    for path in _python_files():
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                if any(name == item or name.startswith(item + ".")
                       for item in forbidden):
                    offenders.append((path.relative_to(REPO).as_posix(), name))
    assert offenders == []


def test_c05_only_uds_socket_user_is_the_bridge_ipc() -> None:
    socket_users = []
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import) and any(
                    alias.name == "socket" for alias in node.names):
                socket_users.append(path.relative_to(REPO).as_posix())
            if isinstance(node, ast.ImportFrom) and node.module == "socket":
                socket_users.append(path.relative_to(REPO).as_posix())
    assert socket_users == ["src/autoteacher_m0/bridge/ipc_server.py"]


def test_c05_only_the_trusted_gate_mints_send_authorizations() -> None:
    offenders = []
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                    and node.func.id == "TrustedSendAuthorization":
                if path.name != "egress.py":
                    offenders.append(path.relative_to(REPO).as_posix())
    assert offenders == []
    for name in ("from_json", "from_dict", "parse", "load", "from_mapping"):
        assert not hasattr(TrustedSendAuthorization, name)


def test_c05_synthetic_route_is_the_only_active_route() -> None:
    assert SYNTHETIC_ROUTE_CONTRACT.activation == "ACTIVE_SYNTHETIC_ONLY"
    from autoteacher_m0.security.egress import REAL_ROUTE_TEMPLATE
    assert REAL_ROUTE_TEMPLATE.activation == (
        "BLOCKED_REQUIRES_HUMAN_VERIFICATION")


def test_c05_run_live_script_still_exits_three() -> None:
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
           "PYTHONDONTWRITEBYTECODE": "1",
           "PYTHONPATH": str(REPO / "src")}
    proc = subprocess.run(["bash", str(REPO / "scripts" / "run_live.sh")],
                          cwd=str(REPO), capture_output=True, text=True,
                          env=env, timeout=60)
    assert proc.returncode == 3, (proc.returncode, proc.stdout, proc.stderr)
    assert "BLOCKED" in (proc.stdout + proc.stderr)


def test_c05_gates_remain_blocked() -> None:
    decision = LiveGate().inspect(live_requested=True)
    assert decision.status == "BLOCKED"
    assert decision.external_boundary_deployed is False
    try:
        LiveGate().require_live(live_requested=True)
    except SecurityBlocked as exc:
        assert exc.code == "SECURITY_BLOCKED"
    else:  # pragma: no cover - fail if a live unlock ever appears
        raise AssertionError("LiveGate allowed a live request")


def test_c05_gates_and_run_live_are_unchanged_from_g4_baseline() -> None:
    baseline = "795c263c06de1a4bbfde9392a6b32f3ab4f489be"
    for relative in ("src/autoteacher_m0/security/gates.py", "scripts/run_live.sh",
                     "src/autoteacher_m0/runtime/dsh_adapter.py",
                     "src/autoteacher_m0/cli.py"):
        proc = subprocess.run(
            ["git", "diff", "--quiet", baseline, "--", relative],
            cwd=str(REPO))
        assert proc.returncode == 0, relative


def test_c05_cli_live_entrypoint_still_exit_three() -> None:
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
           "PYTHONDONTWRITEBYTECODE": "1",
           "PYTHONPATH": str(REPO / "src"),
           "HOME": "/tmp"}
    proc = subprocess.run([sys.executable, "-B", "-m", "autoteacher_m0.cli",
                           "smoke", "--live"],
                          cwd=str(REPO), capture_output=True, text=True,
                          env=env, timeout=60)
    assert proc.returncode == 3, (proc.returncode, proc.stdout, proc.stderr)
    assert "SECURITY_BLOCKED" in (proc.stdout + proc.stderr)
