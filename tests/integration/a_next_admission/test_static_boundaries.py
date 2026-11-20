"""Static / structural / no-key boundaries for the A-NEXT implementation (C7/C6)."""
from __future__ import annotations

import ast
from pathlib import Path
import subprocess
import sys


REPO = Path(__file__).resolve().parents[3]
NEW_FILES = (
    REPO / "src" / "autoteacher_m0" / "bridge" / "run_admission.py",
    REPO / "scripts" / "a_next" / "admission" / "trusted_launcher.py",
    REPO / "scripts" / "a_next" / "admission" / "l2_admission_cases.py",
)
PROTECTED = (
    "src/autoteacher_m0/security/gates.py",
    "scripts/run_live.sh",
    "src/autoteacher_m0/cli.py",
    "src/autoteacher_m0/runtime/dsh_adapter.py",
    "src/autoteacher_m0/security/authorization.py",
)
FORBIDDEN_SOURCE_TOKENS = (
    "import socket", "import requests", "import urllib", "http.client",
    "deepseek_harness", "os.environ", "getenv(", "API_KEY", "api_key",
)


def _git(*args: str) -> str:
    completed = subprocess.run(["git", "-C", str(REPO), *args],
                               capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    return completed.stdout


def test_c7_protected_files_have_zero_diff() -> None:
    changed = [line for line in _git("diff", "--name-only", "fd1d3a6", "--",
                                     *PROTECTED).splitlines() if line.strip()]
    assert changed == []


def test_c7_new_code_has_no_network_or_key_env() -> None:
    for path in NEW_FILES:
        source = path.read_text(encoding="utf-8")
        for token in FORBIDDEN_SOURCE_TOKENS:
            assert token not in source, f"{token} found in {path.name}"
        tree = ast.parse(source)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        assert not ({"socket", "requests", "urllib", "http", "httpx"} & imported)


def test_c7_controller_diff_has_no_new_bypass_or_network() -> None:
    diff = _git("diff", "fd1d3a6", "--",
                "src/autoteacher_m0/bridge/controller.py")
    added = [line[1:] for line in diff.splitlines()
             if line.startswith("+") and not line.startswith("+++")]
    joined = "\n".join(added)
    for token in FORBIDDEN_SOURCE_TOKENS:
        assert token not in joined, token
    # The only token-consume call is in the dispatch serial path, and it is
    # before the sole Broker Reserve call: an unconsumed dispatch cannot
    # create a Reservation through a second code path.
    source = (REPO / "src" / "autoteacher_m0" / "bridge" / "controller.py").read_text(
        encoding="utf-8")
    assert source.count("consume_dispatch(") == 1
    assert source.count("begin_dispatch(") == 1
    assert source.index("consume_dispatch(") < source.index(
        "_broker_reserve(task_id=")


def test_c7_live_gate_is_blocked() -> None:
    sys.path.insert(0, str(REPO / "src"))
    from autoteacher_m0.security.gates import LiveGate, fingerprint
    reviewed = fingerprint({"controller.py": b"x", "profile.yml": b"y"},
                           {"profile": "sdk-minimal"})
    decision = LiveGate().inspect(live_requested=True, actual=reviewed,
                                  reviewed=reviewed,
                                  actual_tools=("skill_lookup",),
                                  session_log_disabled=True)
    assert decision.status == "BLOCKED"


def test_c7_cli_smoke_live_still_exits_3(tmp_path: Path) -> None:
    sys.path.insert(0, str(REPO / "src"))
    from autoteacher_m0 import cli
    assert cli.main(["smoke", "--live",
                     "--artifact-dir", str(tmp_path / "artifacts")]) == 3


def test_c7_run_live_script_unchanged_and_closed() -> None:
    script = (REPO / "scripts" / "run_live.sh").read_text(encoding="utf-8")
    assert "exit 3" in script
    assert "BLOCKED" in script
    assert "key" not in script.lower().replace("key-reading", "")
