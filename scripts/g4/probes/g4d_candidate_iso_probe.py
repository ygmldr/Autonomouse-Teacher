#!/usr/bin/env python3
"""Candidate-principal known-path probe (runs *inside* the candidate container).

Invoked by the external watchdog through ``podman exec`` with one JSON argument
of absolute paths. It only uses the standard library and never prints file
contents: each entry is ALLOWED / EACCES / ENOENT / another errno name. The
result proves whether the newer run's trusted state and the sentinel fixture are
reachable from the candidate principal by *known absolute path* - not whether a
random directory name is hard to guess.
"""
from __future__ import annotations

import json
import os
import socket
import sys


def attempt(name: str, action) -> None:
    try:
        action()
    except PermissionError:
        result[name] = "EACCES"
    except FileNotFoundError:
        result[name] = "ENOENT"
    except OSError as error:
        result[name] = type(error).__name__
    else:
        result[name] = "ALLOWED"


result: dict[str, str] = {}
paths = json.loads(sys.argv[1])

attempt("read_trusted_state", lambda: open(paths["trusted_state"], "rb").read(16))
attempt("write_trusted_state", lambda: open(paths["trusted_write"], "wb").write(b"x"))
attempt("list_trusted_state", lambda: os.listdir(paths["trusted_dir"]))
attempt("read_sentinel_fixture", lambda: open(paths["sentinel"], "rb").read(1))
attempt("read_previous_known_state",
        lambda: open(paths["previous_state"], "rb").read(16))
attempt("write_own_session",
        lambda: open(paths["own_write"], "wb").write(b"g4d-probe"))
attempt("stat_bridge_socket", lambda: os.stat(paths["socket"]))


def _connect() -> None:
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(0.5)
    client.connect(paths["socket"])
    client.close()


attempt("connect_bridge_socket", _connect)
print("G4D_ISO_PROBE " + json.dumps(result, sort_keys=True))
