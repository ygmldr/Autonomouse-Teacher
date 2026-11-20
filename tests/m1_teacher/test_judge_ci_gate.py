"""Behaviour tests for the OS-sandbox CI gate (review P1-3).

The security CI job must not lose its dynamic OS/isolation evidence when bwrap
is missing.  ``judge_os_gate.require_os_sandbox`` therefore skips by default
(ordinary unit-test CI) but hard-fails with ``M1B_REQUIRE_OS_SANDBOX=1``.
These tests pin that behaviour without needing the real sandbox.
"""

from __future__ import annotations

import pytest

from judge_os_gate import (
    REQUIRE_OS_SANDBOX_ENV,
    os_sandbox_required,
    require_os_sandbox,
)


def test_gate_passes_when_sandbox_is_available() -> None:
    require_os_sandbox(available=True)  # no exception


def test_gate_skips_when_sandbox_unavailable_by_default(monkeypatch) -> None:
    monkeypatch.delenv(REQUIRE_OS_SANDBOX_ENV, raising=False)
    with pytest.raises(pytest.skip.Exception):
        require_os_sandbox(available=False)


def test_gate_fails_when_security_ci_requires_os_sandbox(monkeypatch) -> None:
    monkeypatch.setenv(REQUIRE_OS_SANDBOX_ENV, "1")
    with pytest.raises(pytest.fail.Exception) as excinfo:
        require_os_sandbox(available=False)
    message = str(excinfo.value)
    assert REQUIRE_OS_SANDBOX_ENV in message
    assert "refuses to skip" in message


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on", " On "])
def test_require_env_truthy_values(monkeypatch, value: str) -> None:
    monkeypatch.setenv(REQUIRE_OS_SANDBOX_ENV, value)
    assert os_sandbox_required() is True


@pytest.mark.parametrize("value", ["", "0", "false", "no", "off", "random"])
def test_require_env_falsey_values(monkeypatch, value: str) -> None:
    monkeypatch.setenv(REQUIRE_OS_SANDBOX_ENV, value)
    assert os_sandbox_required() is False


def test_unset_require_env_is_not_required(monkeypatch) -> None:
    monkeypatch.delenv(REQUIRE_OS_SANDBOX_ENV, raising=False)
    assert os_sandbox_required() is False


# ---------------------------------------------------------------------------
# Review P1-4: documentation must not claim an environment toggle enables the
# trusted-fixture execution path (implementation reads no such variable).
# ---------------------------------------------------------------------------
def test_docs_do_not_claim_env_can_enable_trusted_fixture() -> None:
    from pathlib import Path

    docs_dir = Path(__file__).resolve().parents[2] / "docs"
    for doc_path in sorted(docs_dir.glob("*.md")):
        text = doc_path.read_text(encoding="utf-8")
        assert "代码内显式参数/环境变量开启" not in text, doc_path.name
        assert "环境变量开启" not in text, doc_path.name
    threat_model = (docs_dir / "M1_B_THREAT_MODEL_JUDGE.md").read_text(
        encoding="utf-8"
    )
    assert "由可信构造/部署参数开启" in threat_model


# ---------------------------------------------------------------------------
# Review addendum P1-3: repository safety-CI entry-point wiring
# ---------------------------------------------------------------------------
def test_safety_ci_script_is_present_and_wired() -> None:
    from pathlib import Path

    script = (
        Path(__file__).resolve().parents[2] / "scripts" / "m1b" / "run_safety_ci.sh"
    )
    assert script.is_file()
    assert script.stat().st_mode & 0o111, "script must be executable"
    text = script.read_text(encoding="utf-8")
    for required in (
        "set -euo pipefail",
        "M1B_REQUIRE_OS_SANDBOX=1",
        "M1B_REQUIRE_NONROOT_SANDBOX",
        "pytest tests/m1_teacher -q -rs",
        "--allow-root-synthetic",
        "skipped",
    ):
        assert required in text, required
    for forbidden in ("curl ", "wget ", "git push", "npm install"):
        assert forbidden not in text
