from __future__ import annotations
import socket
import threading
from pathlib import Path

from autoteacher_m0.bridge.ipc_server import BridgeServer
from autoteacher_m0.bridge.protocol import (
    Envelope, canonical_payload_bytes, encode_envelope, parse_envelope, payload_digest,
)
from test_controller import _controller, _payload


def test_b2_uds_smoke_real_server(tmp_path: Path) -> None:
    controller, broker, fake, attempts = _controller(tmp_path)
    socket_path = str(tmp_path / "bridge.sock")
    server = BridgeServer(controller, socket_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    import time
    deadline = time.monotonic() + 5
    while not Path(socket_path).exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert Path(socket_path).exists(), "server socket not created"
    try:
        payload = _payload()
        request = Envelope(v=1, kind="request", transport_id="tr-" + "a" * 32,
                           seq=0, payload=payload,
                           hash=payload_digest(canonical_payload_bytes(payload)))
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.settimeout(15)
        try:
            client.connect(socket_path)
            client.sendall(encode_envelope(request) + b"\n")
            received = []
            buffer = b""
            while True:
                buffer += client.recv(65536)
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    if line:
                        received.append(parse_envelope(line))
                if received and received[-1].kind in {"finish", "error"}:
                    break
        finally:
            client.close()
        kinds = [env.kind for env in received]
        assert kinds[0] == "ack"
        assert received[0].payload["accepted"] is True
        assert "finish" in kinds or "error" in kinds, kinds
        assert "error" not in kinds, [env.payload for env in received if env.kind == "error"]
        assert "chunk" in kinds
        assert received[-1].kind == "finish"
        assert attempts.conn.execute("SELECT state FROM g3b_attempts").fetchone()[0] == "SETTLED"
        assert fake.received_count() == 1
        assert broker.snapshot()["snapshot"]["claims"]["total"] == 1
    finally:
        server.shutdown()
        thread.join(timeout=5)
        broker.close()
        fake.close()
        attempts.close()
    assert not Path(socket_path).exists()
