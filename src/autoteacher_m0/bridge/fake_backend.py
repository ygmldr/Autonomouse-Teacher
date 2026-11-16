"""B2-owned trusted Fake subprocess backend (no shell/network)."""
from __future__ import annotations
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class FakeReceipt:
    receipt_id: str
    raw_sha256: str
    raw_length: int
    mode: str
    usage: Mapping[str, object] | None
    nonce: str
    path: Path
    frames: tuple[dict, ...]


class FakeBackend:
    def __init__(self, *, script: str, receipt_dir: str, python: str | None = None,
                 timeout_s: float = 10.0, mode: str = "ok_usage"):
        self.script = str(script)
        self.receipt_dir = Path(receipt_dir)
        self.python = python or sys.executable
        self.timeout_s = timeout_s
        self.mode = mode
        self.frames: list[dict] = []
        self.sent_payload_digest: str | None = None
        self.last_receipt: FakeReceipt | None = None

    def received_count(self) -> int:
        path = self.receipt_dir / "received-count.json"
        try:
            return int(json.loads(path.read_text())["count"])
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            return 0

    def send_exact_bytes(self, payload_bytes: bytes) -> FakeReceipt:
        import hashlib
        if len(payload_bytes) > 256 * 1024:
            raise ValueError("FAKE_PAYLOAD_TOO_LARGE")
        self.receipt_dir.mkdir(parents=True, exist_ok=True)
        env = {"PATH": "/usr/bin:/bin", "HOME": str(self.receipt_dir),
               "G3B_RECEIPT_DIR": str(self.receipt_dir),
               "G3B_FAKE_MODE": self.mode}
        proc = subprocess.run([self.python, "-B", self.script], input=payload_bytes + b"\n",
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              env=env, timeout=self.timeout_s, check=False)
        if proc.returncode != 0:
            raise ValueError("FAKE_IO_ERROR")
        self.sent_payload_digest = hashlib.sha256(payload_bytes).hexdigest()
        receipt_path = None
        for path in sorted(self.receipt_dir.glob("rcpt-*.json"), key=lambda p: p.stat().st_mtime):
            try:
                doc = json.loads(path.read_text())
            except Exception:
                continue
            if doc.get("raw_sha256") == self.sent_payload_digest:
                receipt_path = path
                break
        if receipt_path is None:
            raise ValueError("FAKE_RECEIPT_MISMATCH")
        doc = json.loads(receipt_path.read_text())
        frames = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
        receipt = FakeReceipt(doc["receipt_id"], doc["raw_sha256"], doc["raw_length"],
                              doc["mode"], doc.get("usage"), doc["nonce"],
                              receipt_path, tuple(frames))
        self.last_receipt = receipt
        self.frames = frames
        return receipt

    def close(self) -> None:
        self.frames = []
