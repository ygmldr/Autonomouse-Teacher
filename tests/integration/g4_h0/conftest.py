"""G4-H0 P2-03 fixtures: synthetic only, no key, no model, no network.

Reuses the TEST_ONLY G4-A trusted-file fixture (``g4a_support``) so the P2-03
concurrency regressions exercise exactly the deployed authorization contract and
nothing else. Everything lives in a pytest temporary directory; the synthetic
Ed25519 seed never leaves the test process.
"""
from __future__ import annotations

from pathlib import Path
import socket
import sys

import pytest

_G4A_SUPPORT_DIR = Path(__file__).resolve().parents[1] / "g4_a"
if str(_G4A_SUPPORT_DIR) not in sys.path:
    sys.path.insert(0, str(_G4A_SUPPORT_DIR))

from g4a_support import TrustedFixture  # noqa: E402  (path inserted above)


@pytest.fixture()
def trusted(tmp_path: Path) -> TrustedFixture:
    return TrustedFixture(tmp_path)


@pytest.fixture(autouse=True)
def no_external_network(monkeypatch: pytest.MonkeyPatch):
    """Fail the whole G4-H0 suite if anything attempts an IP socket connection."""
    attempts: list[object] = []
    real_socket = socket.socket

    class GuardedSocket(real_socket):
        def connect(self, address):  # type: ignore[override]
            if self.family in (socket.AF_INET, socket.AF_INET6):
                attempts.append(address)
                raise AssertionError("external network is forbidden in G4-H0")
            return super().connect(address)

        def connect_ex(self, address):  # type: ignore[override]
            if self.family in (socket.AF_INET, socket.AF_INET6):
                attempts.append(address)
                raise AssertionError("external network is forbidden in G4-H0")
            return super().connect_ex(address)

    def guarded_create_connection(address, *args, **kwargs):
        attempts.append(address)
        raise AssertionError("external network is forbidden in G4-H0")

    monkeypatch.setattr(socket, "socket", GuardedSocket)
    monkeypatch.setattr(socket, "create_connection", guarded_create_connection)
    yield attempts
    assert attempts == [], f"external network attempts: {attempts}"
