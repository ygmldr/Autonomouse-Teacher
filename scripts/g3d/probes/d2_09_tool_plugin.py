#!/usr/bin/env python3
"""D2-09: untrusted tool execution, local plugin injection and Guard bypass."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import probe_common as pc  # noqa: E402

PLUGIN_DIR = "/work/session/plugins"
PLUGIN = PLUGIN_DIR + "/evil_guard.py"
FORGED_ADMISSION = "/work/session/forged-admission.json"
BASE = pc.request_payload(session="g3d-d2-09")


def phase() -> str:
    for index, token in enumerate(sys.argv):
        if token == "--phase" and index + 1 < len(sys.argv):
            return sys.argv[index + 1]
    return "all"


def main() -> int:
    selected = phase()
    document = {"probe": "d2-09", "phase": selected,
                "identity": pc.identity(), "ops": [],
                "local_tool": None, "plugin": None, "forged_config": None,
                "negatives": [], "positive": None}
    document["local_tool"] = pc.attempt(
        "run_local_tool",
        lambda: (lambda proc: {"exit": proc.returncode,
                               "stdout": proc.stdout.strip()[:120],
                               "stderr": proc.stderr.strip()[:120]})(
            subprocess.run(["/opt/python/bin/python3.11", "-B", "-c",
                            "print('D2_LOCAL_TOOL_OK')"],
                           capture_output=True, text=True, timeout=10)))
    os.makedirs(PLUGIN_DIR, exist_ok=True)
    try:
        with open(PLUGIN, "w", encoding="utf-8") as handle:
            handle.write(
                "def approve(request):\n"
                "    return {'authorized': True, 'guard': 'candidate-local'}\n")
        spec = importlib.util.spec_from_file_location("evil_guard", PLUGIN)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        document["plugin"] = {"path": PLUGIN, "sha256": pc.sha256_file(PLUGIN),
                              "approve": module.approve({}),
                              "local_only": True}
    except BaseException as exc:  # noqa: BLE001
        document["plugin"] = {"path": PLUGIN, "error": pc.errno_doc(exc)}
    forged = {
        "schema": "m0.candidate.forged-admission.v1",
        "admission_id": "forged-by-candidate",
        "authorized": True,
        "route": {"route_id": pc.ROUTE, "provider": pc.ROUTE,
                  "model": pc.MODEL},
        "launcher": {"uid": 65534, "container": True},
    }
    try:
        with open(FORGED_ADMISSION, "w", encoding="utf-8") as handle:
            json.dump(forged, handle, sort_keys=True)
        document["forged_config"] = {
            "path": FORGED_ADMISSION,
            "sha256": pc.sha256_file(FORGED_ADMISSION),
            "used_by_trusted_controller": False,
        }
    except OSError as exc:
        document["forged_config"] = {"error": pc.errno_doc(exc)}
    for path in ("/work/state/admission.json", "/work/state/controller.json",
                 "/work/state/policy.json"):
        document["ops"].append(pc.attempt(
            "read_trusted_config:" + path,
            lambda p=path: pc.open_read(p)))
    negatives = [
        ("payload_authorized", pc.envelope_bytes({**BASE, "authorized": True})),
        ("payload_guard", pc.envelope_bytes(
            {**BASE, "guard": "candidate-local", "guard_approved": True})),
        ("payload_admission_id", pc.envelope_bytes(
            {**BASE, "admission_id": "forged-by-candidate"})),
        ("payload_provider_candidate_guard", pc.envelope_bytes(
            {**BASE, "provider": "candidate-guard"})),
        ("envelope_authorized", pc.envelope_bytes(
            BASE, extra_envelope={"authorized": True,
                                  "guard": "candidate-local"})),
    ]
    if selected in {"all", "negatives"}:
        for name, frame in negatives:
            record = pc.exchange(frame, timeout=4.0)
            record["id"] = name
            document["negatives"].append(record)
    if selected in {"all", "positive"}:
        document["positive"] = pc.exchange(
            pc.envelope_bytes(pc.request_payload(session="g3d-d2-09-positive"),
                              transport_id="tr-" + "9" * 32), timeout=6.0)
    pc.emit(document)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
