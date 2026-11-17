"""G3-C raw-UDS probe runner (container only).

These probes use the *real* Controller/Broker/Fake children but a deterministic
raw AF_UNIX client (not DSH). They are labelled as protocol/integration evidence,
never as real-DSH evidence.
"""
from __future__ import annotations

import json
from pathlib import Path
import socket
import sys
import time

sys.path.insert(0, "/probe/src")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import common_c3 as common  # noqa: E402
from autoteacher_m0.bridge.protocol import Envelope, encode_envelope, parse_envelope  # noqa: E402

EVIDENCE = Path("/evidence")
ROUTE = "offline-test-only-g3b"
MODEL = "fixture-bridge-v1"
TRANSPORT = "tr-" + "c" * 32


def payload(session: str = "g3c-probe") -> dict:
    return {
        "sessionId": session, "provider": ROUTE, "model": MODEL,
        "messages": [{"role": "user", "content": "G3C_PROBE"}], "tools": [],
        "system": None, "maxTokens": 64, "stream": True, "purpose": "conversation",
    }


def decode(lines: list[bytes]) -> list[dict]:
    frames = []
    for line in lines:
        try:
            env = parse_envelope(line)
        except Exception as exc:  # noqa: BLE001
            frames.append({"parse_error": type(exc).__name__,
                           "code": getattr(exc, "code", None),
                           "raw": line.decode("utf-8", "replace")[:500]})
            continue
        frames.append({"kind": env.kind, "seq": env.seq, "payload": env.payload})
    return frames


def request_frame(transport: str, doc: dict, seq: int = 0) -> bytes:
    return encode_envelope(Envelope(1, "request", transport, seq, doc, None)) + b"\n"


def cancel_frame(transport: str, seq: int, reason: str = "aborted") -> bytes:
    return encode_envelope(Envelope(
        1, "cancel", transport, seq,
        {"request_id": transport, "reason": reason}, None)) + b"\n"


def first_frame(sock: socket.socket, seconds: float = 10.0) -> bytes | None:
    return common.readline_timeout(sock, seconds=seconds)


def _counter(snapshot: dict) -> int:
    for row in snapshot.get("receipts", []):
        if isinstance(row, dict) and isinstance(row.get("counter"), dict):
            return int(row["counter"].get("count", 0))
    return 0


def _run_roundtrip(sock: socket.socket, transport: str, doc: dict) -> list[dict]:
    sock.sendall(request_frame(transport, doc))
    return decode(common.read_frames(sock))


def _result(name: str, **data: object) -> dict:
    document = {"probe": name, "utc": common.utc(), **data}
    common.write_json(EVIDENCE / "probe-result.json", document)
    common.collect_work(EVIDENCE, label=name, extra={"probe": name})
    print(json.dumps({"kind": "probe", "probe": name, "ok": data.get("ok"),
                      "summary": {key: value for key, value in data.items()
                                  if key in {"ok", "elapsed_seconds", "counter",
                                             "error_codes", "frames_kinds"}}},
                     sort_keys=True), flush=True)
    return document


def probe_replay() -> dict:
    common.write_configs(scenario="ok_usage", run_id="g3c-probe-replay")
    controller = common.start_controller()
    transport = TRANSPORT
    try:
        common.wait_socket()
        first_sock = common.socket_client()
        first = _run_roundtrip(first_sock, transport, payload("g3c-replay"))
        first_sock.close()
        time.sleep(0.2)
        replay_sock = common.socket_client()
        replay = _run_roundtrip(replay_sock, "tr-" + "d" * 32, payload("g3c-replay"))
        replay_sock.close()
    finally:
        common.stop_controller(controller)
    snapshot = common.broker_and_attempts_snapshot()
    counter = _counter(snapshot)
    kinds_first = [frame.get("kind") for frame in first]
    kinds_replay = [frame.get("kind") for frame in replay]
    codes = [frame.get("payload", {}).get("code") for frame in replay
             if frame.get("kind") == "error"]
    # Protocol v1 always acknowledges a schema-valid request before the
    # Controller outcome, so a replay is [ack, error] (never error-only).
    ok = (kinds_first[-1:] == ["finish"] and kinds_replay[-1:] == ["error"]
          and "ATTEMPT_ALREADY_STARTED" in codes and counter == 1
          and len(snapshot["attempts"]) == 1 and len(snapshot["reservations"]) == 1)
    return _result("replay", ok=ok, first=frames_json(first), replay=frames_json(replay),
                   error_codes=codes, frames_kinds={"first": kinds_first,
                                                    "replay": kinds_replay},
                   counter=counter, db=snapshot, correlation=common.correlation_rows(),
                   env=common.env_snapshot())


def probe_cancel(delay_ms: int = 300, concurrent: bool = False) -> dict:
    common.write_configs(scenario="slow_usage", run_id="g3c-probe-cancel")
    controller = common.start_controller()
    started = time.monotonic()
    try:
        common.wait_socket()
        sock_a = common.socket_client()
        transport_a = "tr-" + "a" * 32
        sock_b = None
        sock_a.sendall(request_frame(transport_a, payload("g3c-cancel-a")))
        ack = first_frame(sock_a, 10)
        if concurrent:
            sock_b = common.socket_client()
            transport_b = "tr-" + "b" * 32
            sock_b.sendall(request_frame(transport_b, payload("g3c-cancel-b")))
            b_ack = first_frame(sock_b, 10)
        else:
            b_ack = None
        time.sleep(max(delay_ms, 1) / 1000.0)
        cancelled_at = time.monotonic() - started
        sock_a.sendall(cancel_frame(transport_a, 1))
        frames_a = decode(common.read_frames(sock_a, limit=300))
        frames_b = [] if sock_b is None else decode(common.read_frames(sock_b, limit=300))
    finally:
        common.stop_controller(controller)
    snapshot = common.broker_and_attempts_snapshot()
    counter = _counter(snapshot)
    ack_kind = "ack" if ack else "none"
    b_ack_kind = "ack" if b_ack else "none"
    a_kinds = [frame.get("kind") for frame in frames_a]
    b_kinds = [frame.get("kind") for frame in frames_b]
    a_codes = [frame.get("payload", {}).get("code") for frame in frames_a
               if frame.get("kind") == "error"]
    ok = (ack_kind == "ack" and a_kinds[:1] == ["error"] and "CANCELLED" in a_codes
          and counter >= 1)
    if concurrent:
        ok = ok and b_kinds[-1:] == ["finish"] and len(snapshot["attempts"]) == 2
    return _result("cancel_concurrent" if concurrent else "cancel",
                   ok=ok, concurrent=concurrent,
                   ack_kind=ack_kind, b_ack_kind=b_ack_kind,
                   a_frames=frames_json(frames_a), b_frames=frames_json(frames_b),
                   frames_kinds={"a": a_kinds, "b": b_kinds}, error_codes=a_codes,
                   cancelled_at_seconds=round(cancelled_at, 3),
                   counter=counter, db=snapshot,
                   correlation=common.correlation_rows(), env=common.env_snapshot())


def probe_deadline(deadline_ms: int, scenario: str = "slow_usage") -> dict:
    common.write_configs(scenario=scenario, run_id=f"g3c-probe-deadline-{deadline_ms}",
                         limits={"deadline_ms": deadline_ms})
    controller = common.start_controller()
    started = time.monotonic()
    try:
        common.wait_socket()
        sock = common.socket_client(timeout=60)
        sock.sendall(request_frame(TRANSPORT, payload("g3c-deadline")))
        frames = decode(common.read_frames(sock, limit=300))
        sock.close()
    finally:
        common.stop_controller(controller)
    elapsed = time.monotonic() - started
    snapshot = common.broker_and_attempts_snapshot()
    counter = _counter(snapshot)
    kinds = [frame.get("kind") for frame in frames]
    codes = [frame.get("payload", {}).get("code") for frame in frames
             if frame.get("kind") == "error"]
    finishes = [frame.get("payload", {}).get("reason") for frame in frames
                if frame.get("kind") == "finish"]
    states = [row["state"] for row in snapshot["attempts"]]
    upper = deadline_ms / 1000.0 + 2.5
    ok = (kinds[-1:] == ["error"] and "DEADLINE_EXCEEDED" in codes
          and not any(isinstance(reason, dict) and reason.get("kind") == "stop"
                      for reason in finishes)
          and elapsed <= upper and counter <= 1)
    return _result("deadline", ok=ok, deadline_ms=deadline_ms, scenario=scenario,
                   elapsed_seconds=round(elapsed, 3), upper_bound_seconds=upper,
                   frames=frames_json(frames), frames_kinds=kinds,
                   error_codes=codes, finish_reasons=finishes,
                   attempt_states=states, counter=counter, db=snapshot,
                   correlation=common.correlation_rows(), env=common.env_snapshot())


def probe_broker_hang(deadline_ms: int = 1500) -> dict:
    """C3-02A: Broker alive, never writes stdout, bounded timeout, no re-send."""
    common.write_configs(scenario="ok_usage", run_id="g3c-probe-broker-hang",
                         limits={"deadline_ms": deadline_ms})
    config_path = common.BASE / "controller.json"
    config = json.loads(config_path.read_text())
    config["python"] = "/probe/fixtures/slow_broker.py"
    config_path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n")
    controller = common.start_controller()
    started = time.monotonic()
    try:
        common.wait_socket()
        sock = common.socket_client(timeout=30)
        sock.sendall(request_frame(TRANSPORT, payload("g3c-broker-hang")))
        frames = decode(common.read_frames(sock, limit=300))
        sock.close()
    finally:
        common.stop_controller(controller)
    elapsed = time.monotonic() - started
    log = common.BASE / "broker-hang.log"
    log_text = log.read_text() if log.exists() else ""
    counter = _counter(common.broker_and_attempts_snapshot())
    codes = [frame.get("payload", {}).get("code") for frame in frames
             if frame.get("kind") == "error"]
    ok = (log_text.count("REQ ") == 1 and elapsed <= deadline_ms / 1000.0 + 2.5
          and codes and codes[0] in {"BROKER_TIMEOUT", "DEADLINE_EXCEEDED"}
          and counter == 0)
    return _result("broker_hang", ok=ok, deadline_ms=deadline_ms,
                   elapsed_seconds=round(elapsed, 3),
                   broker_requests=log_text.count("REQ "), broker_log=log_text[-2000:],
                   frames=frames_json(frames), error_codes=codes, counter=counter,
                   db=common.broker_and_attempts_snapshot(),
                   correlation=common.correlation_rows(), env=common.env_snapshot())


def probe_ipc_bounds() -> dict:
    """C3-03 A/C/F at container level: empty conn, overload, oversized/bad frame."""
    common.write_configs(scenario="ok_usage", run_id="g3c-probe-ipc")
    controller = common.start_controller()
    observations: dict = {}
    try:
        common.wait_socket()
        empty = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        empty.settimeout(5)
        empty.connect(str(common.BASE / "bridge.sock"))
        empty.close()
        observations["empty_connection_closed"] = True
        # One valid request after the empty connection proves the server is alive.
        sock = common.socket_client()
        sock.sendall(request_frame("tr-" + "f" * 32, payload("g3c-ipc-healthy")))
        ok_frames = decode(common.read_frames(sock, limit=30))
        observations["healthy_after_empty"] = bool(ok_frames)
        sock.close()
        # Oversized request frame (> MAX_REQUEST_BYTES).
        big = common.socket_client(timeout=20)
        big.sendall(b'{"v":1,"kind":"request","transport_id":"tr-' + b"0" * 32
                    + b'","seq":0,"payload":{"x":"' + b"a" * 300000 + b'"}}\n')
        big_frames = decode(common.read_frames(big, limit=10, stop_kinds=("error",)))
        observations["oversized"] = {
            "kinds": [frame.get("kind") for frame in big_frames],
            "codes": [frame.get("payload", {}).get("code") for frame in big_frames
                      if frame.get("kind") == "error"]}
        big.close()
        # Bad JSON frame.
        bad = common.socket_client(timeout=20)
        bad.sendall(b"{not json}\n")
        bad_frames = decode(common.read_frames(bad, limit=10, stop_kinds=("error",)))
        observations["bad_json"] = {
            "kinds": [frame.get("kind") for frame in bad_frames],
            "codes": [frame.get("payload", {}).get("code") for frame in bad_frames
                      if frame.get("kind") == "error"]}
        bad.close()
        # Connection overload: 9 simultaneous idle connections (server max is 8).
        # The rejected one receives TOO_MANY_CONNECTIONS without any request.
        held = []
        for _ in range(9):
            conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            conn.settimeout(2)
            try:
                conn.connect(str(common.BASE / "bridge.sock"))
                held.append(conn)
            except OSError as exc:
                observations["connect_error"] = type(exc).__name__
        frames_overload = []
        for conn in held:
            try:
                frames_overload.extend(decode(common.read_frames(
                    conn, limit=3, stop_kinds=("error", "finish"))))
            except OSError:
                pass
        observations["overload"] = {
            "connections": len(held),
            "codes": [frame.get("payload", {}).get("code")
                      for frame in frames_overload if frame.get("kind") == "error"]}
        for conn in held:
            conn.close()
    finally:
        common.stop_controller(controller)
    codes = (observations.get("oversized", {}).get("codes", [])
             + observations.get("bad_json", {}).get("codes", []))
    ok = (observations["healthy_after_empty"]
          and "FRAME_TOO_LARGE" in observations.get("oversized", {}).get("codes", [])
          and observations.get("bad_json", {}).get("codes")
          and observations.get("overload", {}).get("codes"))
    return _result("ipc_bounds", ok=ok, observations=observations,
                   error_codes=codes,
                   db=common.broker_and_attempts_snapshot(), env=common.env_snapshot())


def frames_json(frames: list[dict]) -> list[dict]:
    return frames[:300]


def main() -> int:
    global EVIDENCE
    probe = "replay"
    deadline_ms = 300
    delay_ms = 300
    args = sys.argv[1:]
    while args:
        arg = args.pop(0)
        if arg == "--probe":
            probe = args.pop(0)
        elif arg == "--evidence":
            EVIDENCE = Path(args.pop(0))
            common.EVIDENCE = EVIDENCE
        elif arg == "--deadline-ms":
            deadline_ms = int(args.pop(0))
        elif arg == "--delay-ms":
            delay_ms = int(args.pop(0))
        else:
            raise SystemExit(f"UNKNOWN_ARG:{arg}")
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    if probe == "replay":
        probe_replay()
    elif probe == "cancel":
        probe_cancel(delay_ms=delay_ms)
    elif probe == "cancel_concurrent":
        probe_cancel(delay_ms=delay_ms, concurrent=True)
    elif probe == "deadline":
        probe_deadline(deadline_ms)
    elif probe == "fake_stall":
        probe_deadline(deadline_ms, scenario="timeout")
    elif probe == "broker_hang":
        probe_broker_hang(deadline_ms)
    elif probe == "ipc_bounds":
        probe_ipc_bounds()
    else:
        raise SystemExit(f"UNKNOWN_PROBE:{probe}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
