#!/usr/bin/env python3
"""B04/B06 controlled Controller probe: unapproved tool schemas and extra requests.

This runs the **real** trusted components in one host process — ``load_admission``
with the frozen stage template, a real ``Broker`` subprocess, a real
``AttemptJournal``, the real ``FakeBackend`` and the real ``TrustedController``
— and sends provider payloads that a candidate could have sent over the UDS.

It answers two questions with a ledger, not with prose:

B04  does an unapproved tool / modified tool schema / extra tool get rejected
     *before* Reserve/Claim, with Fake counter 0 and zero attempts?
B06  does an additional provider request always take an independent
     Reserve/Claim/Attempt/Receipt, or get denied with zero sends?

It is **not** a container run and not a substitute for the raw-UDS negatives in
``run_g4_b.py``; the two are deliberately separate evidence levels.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import secrets
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib_g4 as lib  # noqa: E402

sys.path.insert(0, str(lib.REPO_ROOT / "src"))
sys.path.insert(0, str(lib.REPO_ROOT / "artifacts" / "foundation" / "deps"))

ROUTE = "offline-test-only-g3b"
MODEL = "fixture-bridge-v1"
SCOPE = "fixed-offline-scope"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(lib.G4_RUNTIME / "admission-contract.json"))
    parser.add_argument("--work-dir", default="")
    parser.add_argument("--stage", default=str(lib.STAGE_DEFAULT))
    return parser.parse_args(argv)


def _stage_tools(stage: Path) -> list[dict]:
    """The exact approved tool objects captured from a real DSH request."""
    document = json.loads((stage / "candidate" / "fixtures" /
                           "capture-tools.json").read_text(encoding="utf-8"))
    tools = []
    for item in document.get("tools") or []:
        if not isinstance(item, dict):
            continue
        tools.append({"name": item["name"], "sha256": item["sha256"],
                      "tool": json.loads(item["canonical_json"])})
    return tools


def _admission_document(stage: Path, tools: list[dict], *, max_calls: int) -> dict:
    route = {"route_id": ROUTE, "provider": ROUTE, "model": MODEL}
    return {
        "schema": "m0.g3b.admission.v1",
        "admission_id": secrets.token_hex(16),
        "scope_id": SCOPE,
        "run_id": "g4b-contract-" + secrets.token_hex(6),
        "synthetic": True,
        "route": route,
        "tool_schemas": [{"name": tool["name"], "sha256": tool["sha256"]}
                         for tool in tools],
        "limits": {"max_calls": max_calls, "max_attempts": 1,
                   "max_input_tokens": 100000, "max_output_tokens": 1024,
                   "deadline_ms": 30000},
        "fake_scenario": "ok_usage",
        "expiry_utc": "2099-01-01T00:00:00Z",
        "launcher": {"uid": 65534, "container": True,
                     "admission_nonce": secrets.token_hex(16)},
    }


def _broker_document(stage: Path, db_path: Path) -> dict:
    template = json.loads((stage / "trusted" / "templates" /
                           "broker.template.json").read_text(encoding="utf-8"))
    template["db_path"] = str(db_path)
    return template


def build_harness(stage: Path, work: Path, *, max_calls: int = 8) -> dict:
    """Import the product lazily so ``--help`` works without PYTHONPATH."""
    from autoteacher_m0.bridge.admission import load_admission
    from autoteacher_m0.bridge.attempts import AttemptJournal
    from autoteacher_m0.bridge.broker_client import BrokerClient
    from autoteacher_m0.bridge.controller import TrustedController
    from autoteacher_m0.bridge.fake_backend import FakeBackend

    if work.exists():
        # A leftover journal would make a fresh identical request look like a
        # duplicate (ATTEMPT_ALREADY_STARTED) and silently invalidate the run.
        shutil.rmtree(work)
    work.mkdir(parents=True, exist_ok=True)
    receipts = work / "receipts"
    receipts.mkdir(exist_ok=True)
    tools = _stage_tools(stage)
    admission_path = work / "admission.json"
    admission_path.write_text(json.dumps(_admission_document(stage, tools,
                                                             max_calls=max_calls)),
                              encoding="utf-8")
    broker_config = work / "broker.json"
    broker_config.write_text(json.dumps(_broker_document(
        stage, work / "broker.sqlite3")), encoding="utf-8")
    admission = load_admission(admission_path, expected_uid=65534)
    broker = BrokerClient(config_path=str(broker_config), python=sys.executable)
    broker.start()
    fake = FakeBackend(script=str(stage / "trusted" / "fake" / "fake_provider.py"),
                       receipt_dir=str(receipts), python=sys.executable,
                       mode="ok_usage")
    attempts = AttemptJournal(work / "attempts.sqlite3")
    controller = TrustedController(admission, broker=broker, fake=fake,
                                   attempts=attempts, expected_uid=65534)
    return {"controller": controller, "broker": broker, "fake": fake,
            "attempts": attempts, "tools": tools, "admission": admission}


def close_harness(harness: dict) -> None:
    for key in ("broker", "fake", "attempts"):
        try:
            harness[key].close()
        except Exception:  # noqa: BLE001 - teardown must not mask results
            pass


def _envelope(payload: dict):
    from autoteacher_m0.bridge.protocol import Envelope
    return Envelope(v=1, kind="request", transport_id="tr-" + "b" * 32,
                    seq=1, payload=payload, hash=None)


def _frames(controller, payload: dict) -> list[dict]:
    frames = []
    for env in controller.handle_envelope(_envelope(payload)):
        frames.append({"kind": env.kind, "payload": env.payload})
    return frames


def _payload(*, tools: list, messages: list | None = None,
             purpose: object = "conversation", extra: dict | None = None,
             session: str = "g4b-contract") -> dict:
    document = {"sessionId": session, "provider": ROUTE, "model": MODEL,
                "messages": messages if messages is not None else
                [{"role": "user", "content": [{"type": "text", "text": "G4B_PROBE"}]}],
                "tools": tools, "system": None, "maxTokens": 256,
                "stream": True, "purpose": purpose}
    if extra:
        document.update(extra)
    return document


def _ledger(harness: dict) -> dict:
    attempts = harness["attempts"].conn.execute(
        "SELECT COUNT(*) FROM g3b_attempts").fetchone()[0]
    snapshot = harness["broker"].snapshot()["snapshot"]
    return {"attempts": int(attempts),
            "reservations": snapshot["requests"],
            "claims_total": snapshot["claims"]["total"],
            "fake_received": harness["fake"].received_count()}


def _case(name: str, expected: str, payload: dict, harness: dict,
          before: dict, after_hook=None) -> dict:
    frames = _frames(harness["controller"], payload)
    after = _ledger(harness)
    terminal = frames[-1] if frames else {"kind": None, "payload": {}}
    code = None
    if isinstance(terminal.get("payload"), dict):
        code = terminal["payload"].get("code")
    record = {
        "case": name,
        "expected": expected,
        "frame_kinds": [frame["kind"] for frame in frames],
        "error_code": code,
        "ledger_before": before,
        "ledger_after": after,
        "ledger_delta": {key: after[key] - before[key] for key in after},
    }
    if after_hook is not None:
        record["extra"] = after_hook(frames)
    if expected == "REJECT":
        record["ok"] = (terminal.get("kind") == "error"
                        and bool(code)
                        and after == before)
    else:
        record["ok"] = (terminal.get("kind") == "finish"
                        and after["fake_received"] == before["fake_received"] + 1
                        and after["reservations"] == before["reservations"] + 1
                        and after["claims_total"] == before["claims_total"] + 1)
    return record


def run_cases(work: Path, stage: Path) -> dict:
    harness = build_harness(stage, work, max_calls=8)
    cases: list[dict] = []
    try:
        approved = harness["tools"][0]["tool"]
        before = _ledger(harness)
        cases.append(_case(
            "B04-unapproved-tool-name", "REJECT",
            _payload(tools=[{"name": "bash", "description": "run commands",
                             "parameters": {"type": "object",
                                            "properties": {"command":
                                                           {"type": "string"}}}}]),
            harness, before))
        modified = json.loads(json.dumps(approved))
        modified["parameters"]["properties"]["path"] = {"type": "string"}
        cases.append(_case("B04-modified-approved-schema", "REJECT",
                           _payload(tools=[modified]), harness, _ledger(harness)))
        cases.append(_case(
            "B04-extra-tool-alongside-approved", "REJECT",
            _payload(tools=[approved, {"name": "fs_read", "description": "read",
                                       "parameters": {"type": "object",
                                                      "properties": {}}}]),
            harness, _ledger(harness)))
        cases.append(_case(
            "B04-renamed-identical-schema", "REJECT",
            _payload(tools=[{**approved, "name": "skill_lookup_shadow"}]),
            harness, _ledger(harness)))
        cases.append(_case(
            "B04-file-block", "REJECT",
            _payload(tools=[approved], messages=[{"role": "user", "content": [
                {"type": "text", "text": "x"},
                {"type": "file", "file": {"path": "/work/session/x"}}]}]),
            harness, _ledger(harness)))
        cases.append(_case(
            "B04-image-block", "REJECT",
            _payload(tools=[approved], messages=[{"role": "user", "content": [
                {"type": "image", "image": {"data": "AAAA"}}]}]),
            harness, _ledger(harness)))
        cases.append(_case(
            "B04-self-authorization-field", "REJECT",
            _payload(tools=[approved], extra={"authorized": True}),
            harness, _ledger(harness)))
        cases.append(_case(
            "B05-positive-approved-tool", "ACCEPT",
            _payload(tools=[approved]), harness, _ledger(harness)))
        cases.append(_case(
            "B06-second-independent-request", "ACCEPT",
            _payload(tools=[approved], purpose=None,
                     session="g4b-contract-2"), harness, _ledger(harness)))
        # Auxiliary llm purpose ("title"): rejected by the protocol validator
        # before Reserve/Claim, so an auxiliary llm path cannot even reach the
        # accounting layer with a non-conversation purpose.
        cases.append(_case(
            "B06-auxiliary-purpose-rejected", "REJECT",
            _payload(tools=[approved], purpose="title"), harness, _ledger(harness)))
    finally:
        close_harness(harness)
    # A second, tighter admission proves the "extra request -> 0 send" branch.
    tight = build_harness(stage, work / "tight", max_calls=2)
    tight_cases: list[dict] = []
    try:
        approved = tight["tools"][0]["tool"]
        for index in (1, 2):
            tight_cases.append(_case(
                f"B06-within-quota-{index}", "ACCEPT",
                _payload(tools=[approved], session=f"g4b-tight-{index}"),
                tight, _ledger(tight)))
        tight_cases.append(_case(
            "B06-over-quota-extra-request", "REJECT",
            _payload(tools=[approved], session="g4b-tight-3"),
            tight, _ledger(tight)))
        tight_cases[-1]["error_code_expected"] = "BUDGET_DENIED"
        tight_cases[-1]["ok"] = (tight_cases[-1]["ok"]
                                 and tight_cases[-1]["error_code"] == "BUDGET_DENIED")
    finally:
        close_harness(tight)
    return {"schema": "m0.g4b.admission.contract.v1",
            "utc": lib.utc_now(),
            "level": "HOST-IN-PROCESS (real Controller/Broker/AttemptJournal/Fake)",
            "route": {"route_id": ROUTE, "model": MODEL},
            "approved_tool": {"name": harness["tools"][0]["name"],
                              "sha256": harness["tools"][0]["sha256"]},
            "max_calls_default": 8,
            "cases": cases,
            "quota_cases": tight_cases,
            "ok": all(case["ok"] for case in cases + tight_cases)}


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    stage = Path(args.stage)
    work = Path(args.work_dir) if args.work_dir else (lib.G4_RUNTIME / "admission-work")
    document = run_cases(work, stage)
    document["approved_tool_count"] = 1
    written = lib.write_json_atomic(Path(args.out), document)
    print(json.dumps({"ok": document["ok"],
                      "cases": len(document["cases"]) + len(document["quota_cases"]),
                      "failed": [case["case"] for case in
                                 document["cases"] + document["quota_cases"]
                                 if not case["ok"]],
                      "file": args.out, "sha256": written["sha256"]},
                     sort_keys=True))
    return lib.EXIT_OK if document["ok"] else lib.EXIT_DRIFT


if __name__ == "__main__":
    raise SystemExit(main())
