"""Minimal trusted stdio Broker client for G3-B B2 (no network, no retry)."""
from __future__ import annotations
import json
import subprocess
import threading
import uuid


class BrokerClientError(RuntimeError):
    pass


class BrokerClient:
    def __init__(self, *, config_path: str, python: str,
                 timeout_s: float = 15.0):
        self.config_path = str(config_path)
        self.python = python
        self.timeout_s = timeout_s
        self.proc: subprocess.Popen | None = None
        self._seq = 0
        # Durable broker journal outlives one controller process. Sequence-only
        # ids (b2-reserve-1) collide with an earlier process's journal row and
        # produce IDEMPOTENCY_CONFLICT on resume/restart; instance-scoped ids
        # keep idempotency semantics without weakening broker checks.
        self._instance = uuid.uuid4().hex[:16]
        self._lock = threading.RLock()

    def start(self) -> None:
        with self._lock:
            if self.proc is not None:
                return
            self.proc = subprocess.Popen(
                [self.python, "-B", "-m", "autoteacher_m0.accounting.broker",
                 "--config", self.config_path],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, close_fds=True)

    def _request(self, op: str, **fields) -> dict:
        with self._lock:
            return self._request_locked(op, **fields)

    def _request_locked(self, op: str, **fields) -> dict:
        if self.proc is None:
            raise BrokerClientError("BROKER_UNAVAILABLE")
        self._seq += 1
        message = {"v": 1, "id": f"b2-{op}-{self._instance}-{self._seq}", "op": op, **fields}
        if self.proc.poll() is not None:
            raise BrokerClientError("BROKER_EXITED")
        try:
            self.proc.stdin.write(json.dumps(message, separators=(",", ":")) + "\n")
            self.proc.stdin.flush()
            line = self.proc.stdout.readline()
        except (OSError, ValueError) as exc:
            raise BrokerClientError("BROKER_IO_ERROR") from exc
        if not line:
            raise BrokerClientError("BROKER_EOF")
        try:
            reply = json.loads(line)
        except json.JSONDecodeError as exc:
            raise BrokerClientError("BROKER_BAD_REPLY") from exc
        if not isinstance(reply, dict) or reply.get("v") != 1:
            raise BrokerClientError("BROKER_BAD_REPLY")
        return reply

    def reserve(self, *, task_id: str, route_id: str, model: str,
                input_tokens: int, output_tokens: int, call_id: str) -> dict:
        return self._request("reserve", task_id=task_id, route_id=route_id,
                             model=model, purpose="conversation",
                             input_tokens=input_tokens, output_tokens=output_tokens,
                             retry=False, call_id=call_id)

    def claim(self, *, call_id: str, reservation_id: str, request_digest: str,
              expected_route_id: str, expected_model: str) -> dict:
        return self._request("claim", call_id=call_id, reservation_id=reservation_id,
                             request_digest=request_digest,
                             expected_route_id=expected_route_id,
                             expected_model=expected_model)

    def settle(self, *, reservation_id: str, usage: dict | None) -> dict:
        return self._request("settle", reservation_id=reservation_id, usage=usage)

    def fail(self, *, reservation_id: str, usage: dict | None) -> dict:
        return self._request("fail", reservation_id=reservation_id, usage=usage)

    def snapshot(self) -> dict:
        return self._request("snapshot")

    def close(self) -> None:
        with self._lock:
            if self.proc is None:
                return
            proc = self.proc
            self.proc = None
            try:
                if proc.stdin:
                    proc.stdin.close()
                proc.wait(timeout=5)
            except BaseException:
                proc.kill()
                proc.wait(timeout=5)
            finally:
                for stream in (proc.stdout, proc.stderr):
                    if stream:
                        stream.close()
