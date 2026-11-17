#!/opt/python/bin/python3.11
"""G3-C C3-02A hang fixture: a Broker process that stays alive but never answers.

It is started by the Controller exactly like the real Broker
(``<python> -B -m autoteacher_m0.accounting.broker --config <path>``). It records
the config path as READY and every inbound request line, then stalls without
writing stdout. No network, no Key; it never mutates the durable Broker DB.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

args = sys.argv[1:]
try:
    config = Path(args[args.index("--config") + 1])
except (ValueError, IndexError):
    sys.exit(2)
log = config.parent / "broker-hang.log"
log.write_text("READY\n", encoding="utf-8")
for line in sys.stdin:
    with open(log, "a", encoding="utf-8") as handle:
        handle.write("REQ " + line.strip() + "\n")
        handle.flush()
    time.sleep(30)
