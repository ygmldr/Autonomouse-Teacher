"""Isolation tests: ``m1_offline`` must not depend on M0 or the network.

Two layers of defence:
1. Static scan of every ``m1_offline/**/*.py`` source file with ``ast``:
   no ``autoteacher_m0`` / ``src`` imports, no network stack imports.
2. Runtime check in a fresh subprocess: importing the whole package must not
   import M0 or network modules into ``sys.modules``.
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from pathlib import Path

import m1_offline

M1_DIR = Path(m1_offline.__file__).resolve().parent
REPO_ROOT = M1_DIR.parent

FORBIDDEN_ROOTS = {
    "autoteacher_m0",
    "src",
    "httpx",
    "httpcore",
    "requests",
    "aiohttp",
    "urllib",
    "urllib3",
    "socket",
    "http",
    "ssl",
    "ftplib",
    "smtplib",
    "telnetlib",
    "xmlrpc",
    "websockets",
    "websocket",
    "grpc",
    "boto3",
    "openai",
    "anthropic",
    "deepseek_harness",
}


def _python_files() -> list[Path]:
    return sorted(M1_DIR.rglob("*.py"))


def test_package_has_python_files():
    files = _python_files()
    assert files, "m1_offline package is empty"
    assert any(path.name == "types.py" for path in files)


def test_no_forbidden_imports_in_ast():
    violations: list[str] = []
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    if root in FORBIDDEN_ROOTS:
                        violations.append(f"{path.name}:{node.lineno} import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                if node.level:  # relative import inside the package is fine
                    continue
                if node.module is None:
                    continue
                root = node.module.split(".")[0]
                if root in FORBIDDEN_ROOTS:
                    violations.append(f"{path.name}:{node.lineno} from {node.module} import ...")
    assert not violations, "forbidden imports found:\n" + "\n".join(violations)


def test_no_m0_or_src_import_statements_in_source_text():
    """Docstrings may explain the isolation boundary; actual imports may not."""

    patterns = (
        re.compile(r"(?m)^\s*(?:import|from)\s+autoteacher_m0\b"),
        re.compile(r"(?m)^\s*(?:import|from)\s+src\b"),
    )
    for path in _python_files():
        text = path.read_text(encoding="utf-8")
        for pattern in patterns:
            assert not pattern.search(text), f"{path} has a forbidden import statement"


def test_no_network_calls_in_source_text():
    """Cheap belt-and-braces scan for obvious network calls (not a full audit)."""

    needles = (
        "socket.socket",
        "socket.create_connection",
        "requests.get",
        "requests.post",
        "httpx.get",
        "httpx.post",
        "urllib.request",
        "urlopen(",
    )
    for path in _python_files():
        text = path.read_text(encoding="utf-8")
        for needle in needles:
            assert needle not in text, f"{path} contains {needle}"


# Runtime check considers M0/third-party client stacks only.  The stdlib
# ``urllib`` module is not a client here: ``pathlib`` imports ``urllib.parse``
# on CPython 3.11, so stdlib-parse must not be reported as egress.
RUNTIME_FORBIDDEN_ROOTS = frozenset(
    {
        "autoteacher_m0",
        "src",
        "httpx",
        "httpcore",
        "requests",
        "aiohttp",
        "urllib3",
        "websockets",
        "websocket",
        "grpc",
        "boto3",
        "openai",
        "anthropic",
        "deepseek_harness",
    }
)


def test_fresh_subprocess_import_is_isolated():
    script = """
import json
import sys

import m1_offline
import m1_offline.types as types
import m1_offline.runtime_port  # noqa: F401
import m1_offline.learner_model  # noqa: F401
import m1_offline.teaching_policy  # noqa: F401
import m1_offline.curriculum_planner  # noqa: F401
import m1_offline.memory  # noqa: F401
import m1_offline.diagnostics  # noqa: F401

forbidden_roots = %r
loaded = sorted({
    name.split(".")[0]
    for name in sys.modules
    if name.split(".")[0] in forbidden_roots
})
print(json.dumps({"forbidden": loaded, "schema": types.SCHEMA_VERSION}))
""" % (
        sorted(RUNTIME_FORBIDDEN_ROOTS),
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout.strip().splitlines()[-1])
    assert payload["forbidden"] == [], payload
    assert payload["schema"] == "m1.offline.v0"


def test_package_exports_required_helpers():
    assert m1_offline.REPO_ROOT == REPO_ROOT
    assert m1_offline.FIXTURES_DIR == REPO_ROOT / "fixtures" / "m1"
    assert callable(m1_offline.load_json)
    assert callable(m1_offline.now_utc)
    assert m1_offline.SCHEMA_VERSION == "m1.offline.v0"
