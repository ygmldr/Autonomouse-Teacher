"""G4-D host-contract tests: no key, no model, no network, no real container.

The external-process/container rows are exercised by ``scripts/g4/run_g4_d.py``
under ``artifacts/g4/e5``. These tests pin the invariants that make those runs
meaningful: observed absence is required, revocation/epoch deny, and every Live
entrance stays BLOCKED.
"""
from __future__ import annotations

import socket
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
for entry in (REPO / "src", REPO / "scripts" / "g4", REPO / "scripts" / "g3d",
              REPO / "tests" / "integration" / "g4_a",
              REPO / "tests" / "integration" / "g4_c"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))


@pytest.fixture(autouse=True)
def no_external_network(monkeypatch: pytest.MonkeyPatch):
    """Any AF_INET/AF_INET6 connect attempt fails the G4-D suite."""
    attempts: list[object] = []
    real_socket = socket.socket

    class GuardedSocket(real_socket):
        def connect(self, address):  # type: ignore[override]
            if self.family in (socket.AF_INET, socket.AF_INET6):
                attempts.append(address)
                raise AssertionError("external network is forbidden in G4-D")
            return super().connect(address)

        def connect_ex(self, address):  # type: ignore[override]
            if self.family in (socket.AF_INET, socket.AF_INET6):
                attempts.append(address)
                raise AssertionError("external network is forbidden in G4-D")
            return super().connect_ex(address)

    def guarded_create_connection(address, *args, **kwargs):
        attempts.append(address)
        raise AssertionError("external network is forbidden in G4-D")

    monkeypatch.setattr(socket, "socket", GuardedSocket)
    monkeypatch.setattr(socket, "create_connection", guarded_create_connection)
    yield attempts
    assert attempts == [], f"external network attempts: {attempts}"
