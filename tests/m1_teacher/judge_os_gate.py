"""Shared OS-sandbox gate for the B-PR1 judge tests (review P1-3).

Dynamic sandbox tests may skip on a host without ``bwrap`` (ordinary unit-test
CI), but the **security** CI job must never silently lose its OS evidence.  Set
``M1B_REQUIRE_OS_SANDBOX=1`` to turn "sandbox unavailable" into a hard failure
instead of a skip::

    M1B_REQUIRE_OS_SANDBOX=1 pytest tests/m1_teacher -q -rs   # expect 0 skipped

The helper is deliberately import-light (no sandbox construction on import) and
can be told the availability explicitly, which also makes its own behaviour
unit-testable without depending on the host.
"""

from __future__ import annotations

import os

import pytest

REQUIRE_OS_SANDBOX_ENV = "M1B_REQUIRE_OS_SANDBOX"
_TRUTHY = frozenset({"1", "true", "yes", "on"})

SKIP_REASON = (
    "OS sandbox (bwrap) is unavailable on this host; "
    "fail-closed blocked policy is covered without bwrap"
)


def os_sandbox_required() -> bool:
    """True when the environment demands real OS-sandbox evidence."""

    return os.environ.get(REQUIRE_OS_SANDBOX_ENV, "").strip().casefold() in _TRUTHY


def os_sandbox_available() -> bool:
    """Probe the real ``BwrapSandbox`` availability (never raises)."""

    try:
        from m1_teacher.assessment.judge.sandbox import BwrapSandbox

        return bool(BwrapSandbox().available())
    except Exception:  # noqa: BLE001 - missing sandbox module/binary = unavailable
        return False


def require_os_sandbox(available: bool | None = None) -> None:
    """Skip when the sandbox is unavailable, unless the security CI demands it.

    With ``M1B_REQUIRE_OS_SANDBOX=1`` the same condition becomes ``pytest.fail``
    so a security job cannot be green with zero dynamic isolation evidence.
    """

    if available is None:
        available = os_sandbox_available()
    if available:
        return
    if os_sandbox_required():
        pytest.fail(
            f"{SKIP_REASON}; {REQUIRE_OS_SANDBOX_ENV}=1 requires OS sandbox "
            "evidence and refuses to skip"
        )
    pytest.skip(SKIP_REASON)
