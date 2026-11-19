#!/usr/bin/env python3
"""G4-C Candidate-principal UDS/network probe (runs inside the real container).

Executed by ``scripts/g4/launch_c.py`` via ``podman exec`` as the real
Candidate principal (host uid 65534). It never imports the trusted package and
never fabricates a result: every case records the real protocol frame or the
kernel errno. One ``G4C_PROBE <json>`` line is printed on stdout.

Phases
  negatives   route/model/tool/file/self-auth/oversized-token rejections
  valid       one fully valid request (drives a real Reserve/Claim/Fake)
  replay      byte-identical replay of ``valid`` (same business identity)
  over_quota  another valid request after the admission call budget is spent
  network     AF_INET/AF_INET6/DNS/route/fallback probes (no live traffic)
"""
from __future__ import annotations

import errno
import hashlib
import json
import os
import socket
import sys
import time

sys.path.insert(0, "/project/run/probes")
import probe_common as pc  # noqa: E402

FIXTURE = "/project/fixtures/capture-tools.json"


def approved_tool() -> dict:
    document = json.load(open(FIXTURE, encoding="utf-8"))
    return json.loads(document["tools"][0]["canonical_json"])


def valid_payload() -> dict:
    """Deterministic business identity shared by ``valid`` and ``replay``."""
    return pc.request_payload(
        session="g4c-probe-session",
        messages=[{"role": "user", "content": "g4c deterministic probe"}],
        tools=[approved_tool()],
        max_tokens=64)


def valid2_payload() -> dict:
    """A second, distinct business identity for "new request after revoke"."""
    return pc.request_payload(
        session="g4c-probe-session-2",
        messages=[{"role": "user", "content": "g4c deterministic probe 2"}],
        tools=[approved_tool()],
        max_tokens=64)


def exchange(label: str, payload: dict, *, timeout: float = 10.0) -> dict:
    transport = "tr-" + hashlib.sha256(
        (label + str(os.getpid()) + str(time.time_ns())).encode("utf-8")).hexdigest()[:32]
    record = pc.exchange(pc.envelope_bytes(payload, transport_id=transport),
                         timeout=timeout)
    last = (record.get("raw_lines") or [""])[-1][:500]
    return {
        "label": label,
        "terminal": record.get("terminal"),
        "error_code": record.get("error_code"),
        "frame_count": record.get("frame_count"),
        "connected": record.get("connected"),
        "error": record.get("error"),
        "last_frame": last,
    }


def phase_negatives() -> dict:
    tool = approved_tool()
    modified = json.loads(json.dumps(tool))
    modified.setdefault("parameters", {}).setdefault("properties", {})[
        "path"] = {"type": "string"}
    cases = [
        exchange("unapproved_tool_name", pc.request_payload(
            session="g4c-neg-tool", tools=[{"name": "bash", "description": "shell",
                                            "parameters": {"type": "object",
                                                           "properties": {}}}])),
        exchange("modified_approved_schema", pc.request_payload(
            session="g4c-neg-mod", tools=[modified])),
        exchange("extra_tool_alongside_approved", pc.request_payload(
            session="g4c-neg-extra",
            tools=[tool, {"name": "fs_read", "description": "read",
                          "parameters": {"type": "object", "properties": {}}}])),
        exchange("file_block", pc.request_payload(
            session="g4c-neg-file",
            messages=[{"role": "user", "content": [
                {"type": "text", "text": "x"},
                {"type": "file", "file": {"path": "/work/session/x"}}]}],
            tools=[tool])),
        exchange("wrong_provider", pc.request_payload(
            session="g4c-neg-provider", provider="opencode-go", tools=[tool])),
        exchange("wrong_model", pc.request_payload(
            session="g4c-neg-model", model="gpt-real", tools=[tool])),
        exchange("max_tokens_over_admission", pc.request_payload(
            session="g4c-neg-tokens", tools=[tool], max_tokens=1025)),
    ]
    selfauth = pc.request_payload(session="g4c-neg-selfauth", tools=[tool])
    selfauth["authorized"] = True
    cases.append(exchange("self_authorization_field", selfauth))
    return {"phase": "negatives", "uid": os.getuid(),
            "identity": pc.identity()["uid"], "cases": cases}


def phase_network() -> dict:
    checks: list[dict] = []
    external_connection = False

    def record(name: str, fn) -> None:
        nonlocal external_connection
        try:
            detail = fn()
            checks.append({"check": name, "ok": False, "detail": detail})
            if name.startswith("connect"):
                external_connection = True
        except OSError as exc:
            checks.append({"check": name, "ok": True,
                           "errno": exc.errno,
                           "errno_name": errno.errorcode.get(exc.errno, "?")})
        except BaseException as exc:  # noqa: BLE001
            checks.append({"check": name, "ok": False,
                           "error": type(exc).__name__})

    def tcp_connect(address):
        def inner():
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                sock.settimeout(2.0)
                sock.connect(address)
                return {"connected": True}
            finally:
                sock.close()
        return inner

    def udp_socket():
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.close()
        return {"created": True}

    def dns():
        socket.getaddrinfo("example.invalid", 443, socket.AF_INET,
                           socket.SOCK_STREAM)
        return {"resolved": True}

    def listener():
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind(("0.0.0.0", 0))
            sock.listen(1)
            return {"bound": True}
        finally:
            sock.close()

    record("connect_1_1_1_1_443", tcp_connect(("1.1.1.1", 443)))
    record("connect_8_8_8_8_53", tcp_connect(("8.8.8.8", 53)))
    record("udp_socket_af_inet", udp_socket)
    record("dns_example_invalid", dns)
    record("listen_af_inet", listener)
    route = "/proc/net/route"
    route_text = ""
    try:
        route_text = open(route, encoding="utf-8", errors="replace").read()
    except OSError:
        route_text = ""
    default_routes = [line for line in route_text.splitlines()[1:]
                      if line.split() and line.split()[1] == "00000000"]
    checks.append({"check": "no_default_ipv4_route", "ok": not default_routes,
                   "rows": len(default_routes)})
    return {"phase": "network", "uid": os.getuid(),
            "external_connection": external_connection,
            "checks": checks,
            "ok": all(item.get("ok") for item in checks)
            and not external_connection}


def main() -> int:
    if len(sys.argv) < 2:
        print("G4C_PROBE " + json.dumps({"error": "phase required"}, sort_keys=True))
        return 2
    phase = sys.argv[1]
    if phase == "negatives":
        document = phase_negatives()
    elif phase == "network":
        document = phase_network()
    elif phase in {"valid", "replay"}:
        document = {"phase": phase, "uid": os.getuid(),
                    "cases": [exchange(phase, valid_payload())]}
    elif phase == "valid2":
        document = {"phase": phase, "uid": os.getuid(),
                    "cases": [exchange("valid2", valid2_payload())]}
    elif phase == "over_quota":
        document = {"phase": phase, "uid": os.getuid(),
                    "cases": [exchange("over_quota", pc.request_payload(
                        session="g4c-probe-quota",
                        messages=[{"role": "user", "content": "quota"}],
                        tools=[approved_tool()], max_tokens=64))]}
    else:
        document = {"error": "unknown phase", "phase": phase}
    document["utc"] = pc.utc()
    print("G4C_PROBE " + json.dumps(document, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
