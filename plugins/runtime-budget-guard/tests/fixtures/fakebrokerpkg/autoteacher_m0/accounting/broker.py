"""Test-scope fake NDJSON broker for committed PR1 guard tests.

No network, no credentials, no model. This module intentionally shadows
``autoteacher_m0.accounting.broker`` only when the test launcher puts this
fixture package first on the broker child's PYTHONPATH. Behaviour is selected by
the broker policy ``db_path`` segment ``/mode-<mode>/``.
"""
import json
import re
import sys

MODE = re.compile(r"/mode-([a-z-]+)/")


def main(argv):
    try:
        index = argv.index("--config")
        with open(argv[index + 1], "rb") as stream:
            policy = json.load(stream)
    except (ValueError, IndexError, OSError, json.JSONDecodeError):
        return 2
    db_path = str(policy.get("db_path", ""))
    match = MODE.search(db_path + "/")
    mode = match.group(1) if match else "normal"
    counter = 0

    def record(message):
        with open(db_path + ".requests.log", "a", encoding="utf-8") as stream:
            stream.write(json.dumps(message, sort_keys=True) + "\n")

    def send(value):
        sys.stdout.write(json.dumps(value, sort_keys=True) + "\n")
        sys.stdout.flush()

    def envelope(request, overrides=None):
        value = {"v": 1, "id": request.get("id"), "ok": True, "code": "X",
                 "dispatch_allowed": False, "duplicate": False}
        value.update(overrides or {})
        return value

    for line in sys.stdin:
        if not line.endswith("\n"):
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(request, dict):
            continue
        record(request)
        op = request.get("op")
        if op == "snapshot":
            send(envelope(request, {"code": "SNAPSHOT", "snapshot": {"pending": 0}}))
            continue
        if op == "reserve":
            if mode == "reserve-deny":
                send(envelope(request, {"ok": False, "code": "BUDGET_EXCEEDED"}))
                continue
            if mode == "reserve-die":
                sys.stderr.write("fake broker traceback: sk-FAKE-SECRET-STDERR\n")
                sys.stderr.flush()
                return 3
            counter += 1
            send(envelope(request, {
                "code": "RESERVED", "dispatch_allowed": True,
                "reservation_id": "fake-reservation-%d" % counter,
                "reservation": {"cost_usd": "0.001013",
                                "input_tokens": request.get("input_tokens"),
                                "output_tokens": request.get("output_tokens")},
            }))
            continue
        if op in ("settle", "fail"):
            if mode in ("settle-die", "settle-die-secret"):
                if mode == "settle-die-secret":
                    sys.stderr.write("fake broker stderr: sk-FAKE-SECRET-STDERR\n")
                    sys.stderr.flush()
                return 0
            if mode == "settle-hang":
                continue
            send(envelope(request, {
                "code": "SETTLED" if op == "settle" else "FAILED",
                "settlement": {"status": "OK" if op == "settle" else "FAILED",
                               "cost_usd": "0.001013", "estimated": False,
                               "reservation_exceeded": False},
            }))
            continue
        send(envelope(request, {"ok": False, "code": "INVALID_MESSAGE"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
