"""A-NEXT run-admission host tests: synthetic only, no key, no external network."""
from __future__ import annotations

import socket
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
for _entry in (REPO / "src", REPO / "tests" / "integration" / "g4_a",
               REPO / "tests" / "integration" / "g4_f3",
               REPO / "tests" / "integration" / "g4_c",
               REPO / "tests" / "integration" / "g4_f5"):
    if str(_entry) not in sys.path:
        sys.path.insert(0, str(_entry))

from g4a_support import TrustedFixture  # noqa: E402


@pytest.fixture()
def trusted(tmp_path: Path) -> TrustedFixture:
    return TrustedFixture(tmp_path)


@pytest.fixture(autouse=True)
def no_external_network(monkeypatch: pytest.MonkeyPatch):
    """Any AF_INET/AF_INET6 connect attempt fails the A-NEXT suite."""
    attempts: list[object] = []
    real_socket = socket.socket

    class GuardedSocket(real_socket):
        def connect(self, address):  # type: ignore[override]
            if self.family in (socket.AF_INET, socket.AF_INET6):
                attempts.append(address)
                raise AssertionError("external network is forbidden in A-NEXT")
            return super().connect(address)

        def connect_ex(self, address):  # type: ignore[override]
            if self.family in (socket.AF_INET, socket.AF_INET6):
                attempts.append(address)
                raise AssertionError("external network is forbidden in A-NEXT")
            return super().connect_ex(address)

    def guarded_create_connection(address, *args, **kwargs):
        attempts.append(address)
        raise AssertionError("external network is forbidden in A-NEXT")

    monkeypatch.setattr(socket, "socket", GuardedSocket)
    monkeypatch.setattr(socket, "create_connection", guarded_create_connection)
    yield attempts
    assert attempts == [], f"external network attempts: {attempts}"
