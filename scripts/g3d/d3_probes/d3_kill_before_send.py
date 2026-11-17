#!/usr/bin/env python3
"""D3-C02: connect to the approved socket and SIGKILL before sending a byte.

The socket connect is real; no request bytes enter the Controller, so no
Reserve/Claim/Attempt/Fake can exist. The process death is a real SIGKILL.
"""
from __future__ import annotations

import os
import signal
import sys

sys.path.insert(0, "/project/run/probes")
import probe_common as pc  # noqa: E402


def main() -> int:
    document = {"probe": "d3-kill-before-send", "identity": pc.identity()}
    _sock = pc.connect_unix(pc.SOCKET_PATH, timeout=3.0)
    document["connected"] = True
    document["sent_bytes"] = 0
    print("D3_C02 CONNECTED_THEN_SIGKILL", flush=True)
    sys.stdout.flush()
    os.kill(os.getpid(), signal.SIGKILL)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
