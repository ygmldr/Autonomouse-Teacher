#!/usr/bin/env python3
"""Independent reviewer timing probe for the g4_h0 legacy-record retry test.

Replicates ``test_retry_bound_stays_fail_closed_for_a_late_publisher`` outside
pytest and measures the baseline ``consume_execution_authorization`` latency
(pure-Python Ed25519 verification) versus the test's hard-coded 300 ms
late-writer delay. TEST_ONLY synthetic fixture from tests/integration/g4_a;
no key, model, provider or network.

Usage:
  PYTHONPATH=src python scripts/g4h0-review/probe_retry_bound_timing.py
"""
from __future__ import annotations

import importlib.util
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tests" / "integration" / "g4_a"))
sys.path.insert(0, str(REPO / "src"))

from g4a_support import TrustedFixture  # noqa: E402
from autoteacher_m0.security import authorization as authorization_module  # noqa: E402
from autoteacher_m0.security.authorization import AuthorizationRejected  # noqa: E402

spec = importlib.util.spec_from_file_location(
    "g4h0_tests", REPO / "tests" / "integration" / "g4_h0"
    / "test_p2_03_concurrent_consume.py")
test_helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(test_helpers)


def main() -> int:
    work = Path(tempfile.mkdtemp(prefix="review-retry-probe-"))
    try:
        fixture = TrustedFixture(work)
        print("baseline consume_execution_authorization latency (no collision):")
        for index in range(3):
            auth_id = test_helpers._set_authorization(
                fixture, test_helpers._new_authorization_id(f"baseline-{index}"))
            started = time.monotonic()
            fixture.consume()
            print(f"  baseline {index}: {(time.monotonic() - started) * 1000:.1f} ms")
        authorization_module._USE_RECORD_READ_ATTEMPTS = 3
        authorization_module._USE_RECORD_READ_DELAY_SECONDS = 0.005
        print("late-publisher scenario (test uses a fixed 300 ms writer delay):")
        for trial in range(10):
            auth_id = test_helpers._set_authorization(
                fixture, test_helpers._new_authorization_id("late-publisher"))
            record = fixture.record_path(auth_id)
            test_helpers._write_record(record, b"")
            body = test_helpers._use_record_body(auth_id)
            writer = threading.Thread(
                target=lambda: (time.sleep(0.3), record.write_bytes(body)), daemon=True)
            writer.start()
            started = time.monotonic()
            try:
                fixture.consume()
                outcome = "CONSUMED(FAIL)"
            except AuthorizationRejected as error:
                outcome = error.reasons
            elapsed = (time.monotonic() - started) * 1000
            print(f"  trial {trial}: elapsed={elapsed:.1f} ms reasons={outcome}")
            writer.join(timeout=2)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
