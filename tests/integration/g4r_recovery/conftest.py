"""G4-R R2 host-contract tests: no key, no model, no external network.

These tests drive the real in-process Controller with either the real local
Broker/Fake subprocess fixture (G4-F3 harness, synthetic only) or a bounded
in-process stub Broker for recovery-state-machine scenarios.  The real
DSH/container half (L2) is recorded separately under ``artifacts/g4r/r2`` and is
never substituted by these host tests.
"""
from __future__ import annotations

import socket
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
for entry in (REPO / "src", REPO / "tests" / "integration" / "g4_f3",
              REPO / "tests" / "integration" / "g4_c",
              REPO / "tests" / "integration" / "g4_f5"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))


@pytest.fixture(autouse=True)
def no_external_network(monkeypatch: pytest.MonkeyPatch):
    """Any AF_INET/AF_INET6 connect attempt fails the G4-R R2 suite."""
    attempts: list[object] = []
    real_socket = socket.socket

    class GuardedSocket(real_socket):
        def connect(self, address):  # type: ignore[override]
            if self.family in (socket.AF_INET, socket.AF_INET6):
                attempts.append(address)
                raise AssertionError("external network is forbidden in G4-R R2")
            return super().connect(address)

        def connect_ex(self, address):  # type: ignore[override]
            if self.family in (socket.AF_INET, socket.AF_INET6):
                attempts.append(address)
                raise AssertionError("external network is forbidden in G4-R R2")
            return super().connect_ex(address)

    def guarded_create_connection(address, *args, **kwargs):
        attempts.append(address)
        raise AssertionError("external network is forbidden in G4-R R2")

    monkeypatch.setattr(socket, "socket", GuardedSocket)
    monkeypatch.setattr(socket, "create_connection", guarded_create_connection)
    yield attempts
    assert attempts == [], f"external network attempts: {attempts}"
