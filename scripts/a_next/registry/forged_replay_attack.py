#!/usr/bin/env python3
"""A-NEXT A-PR2 forged / replayed / suppressed self-report attack (offline).

Takes a *genuine* probe run directory (the instrumented L1 JSONL produced by
``run_matrix.py``) and demonstrates that a naive verifier which only reads that
self-reported JSONL can be made to accept a forged, replayed or truncated
evidence set:

1. **forge**   — rewrite the offending dispatch/registry records so the tool
   face looks approved; no signature or trusted channel exists to notice.
2. **replay**  — move another run's events into this run with the run label
   rewritten; records carry only a candidate-editable ``run_label``.
3. **suppress** — delete the dispatch records that show the extra tool; an
   "absence of bad records" check passes even though the run dispatched it.

The script also runs the same check on the genuine records to prove the naive
verifier is not simply broken. Nothing here touches the network, a key or the
frozen runtime; it is pure evidence analysis. The conclusion is used in
``docs/A_NEXT_REGISTRY_DECISION.md``: L1 self-report can never be attestation.

Usage:
    python3 forged_replay_attack.py --attack-run <run-dir> [--baseline-run <dir>] \
        [--out artifacts/a_next/registry/<utc>-forged-replay]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

APPROVED_NAME = "skill_lookup"
APPROVED_SHA256 = "c984bef0ae31771da16a12ef2e7972b289cde6014b7f8ad12349f16c4f77b704"
APPROVED = [{"name": APPROVED_NAME, "sha256": APPROVED_SHA256}]


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_jsonl(path: Path) -> list[dict]:
    records: list[dict] = []
    if not path.is_file():
        return records
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        records.append(json.loads(line))
    return records


def write_jsonl(path: Path, records: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def naive_verifier(events: list[dict]) -> dict:
    """A consumer that trusts the self-reported JSONL without any trust root."""
    dispatches = [event for event in events if event.get("kind") == "dispatch_tool_face"]
    if not dispatches:
        return {"accepted": False, "reason": "NO_DISPATCH_RECORD",
                "dispatch_count": 0, "unapproved": []}
    unapproved: list[str] = []
    for dispatch in dispatches:
        for item in dispatch.get("tool_digests") or []:
            if not any(allow["name"] == item.get("name")
                       and allow["sha256"] == item.get("sha256") for allow in APPROVED):
                unapproved.append(str(item.get("name")))
    return {"accepted": not unapproved, "reason": "ACCEPTED" if not unapproved else "UNAPPROVED_TOOL",
            "dispatch_count": len(dispatches), "unapproved": sorted(set(unapproved))}


def forge_events(events: list[dict]) -> list[dict]:
    """Make every dispatch/registry record claim exactly the approved tool set."""
    forged: list[dict] = []
    for event in events:
        clone = json.loads(json.dumps(event))
        if clone.get("kind") == "dispatch_tool_face":
            clone["tool_names"] = [APPROVED_NAME]
            clone["tool_digests"] = list(APPROVED)
            clone["registry_names"] = [APPROVED_NAME]
            clone["registry_digests"] = list(APPROVED)
            clone["face_equals_registry"] = True
            clone["approved_face"] = True
            clone["approved_registry"] = True
            clone["unknown"] = []
            clone["registry_unknown"] = []
        elif clone.get("kind") == "registry_snapshot":
            clone["definitions"] = [APPROVED_NAME]
            clone["schemas"] = list(APPROVED)
        forged.append(clone)
    return forged


def replay_events(source_events: list[dict], target_label: str) -> list[dict]:
    """Move a clean run's records into this run; only the label is rewritten."""
    replayed: list[dict] = []
    for event in source_events:
        clone = json.loads(json.dumps(event))
        if "run_label" in clone:
            clone["run_label"] = target_label
        replayed.append(clone)
    return replayed


def suppress_events(events: list[dict], clean_events: list[dict],
                   target_label: str) -> list[dict]:
    """Drop the records that show the unapproved tool; keep one clean dispatch.

    Real observer loss can omit exactly the offending dispatch: a verifier that
    only looks at the records that exist cannot tell "clean" from "dropped".
    """
    clean_dispatch = next((json.loads(json.dumps(event)) for event in clean_events
                           if event.get("kind") == "dispatch_tool_face"), None)
    if clean_dispatch is not None and "run_label" in clean_dispatch:
        clean_dispatch["run_label"] = target_label
    kept = [event for event in events
            if not (event.get("kind") == "dispatch_tool_face"
                    and (event.get("unknown") or event.get("registry_unknown")))]
    if clean_dispatch is not None:
        kept.append(clean_dispatch)
    return kept


def find_latest_run(root: Path, mode_hint: str) -> Path:
    candidates = sorted(root.glob(f"*{mode_hint}*"))
    if not candidates:
        raise SystemExit(f"no run directory matching {mode_hint} under {root}")
    for candidate in reversed(candidates):
        if (candidate / "probe-events.jsonl").is_file():
            return candidate
    raise SystemExit(f"no probe-events.jsonl in {mode_hint} runs under {root}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attack-run", default="",
                        help="genuine run dir that contains an unapproved tool (default: latest *late-bash*)")
    parser.add_argument("--baseline-run", default="",
                        help="genuine clean run dir used for replay (default: latest *baseline*)")
    parser.add_argument("--root", default="artifacts/a_next/registry")
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)
    root = Path(args.root)
    attack_dir = Path(args.attack_run) if args.attack_run else find_latest_run(root, "late-bash")
    baseline_dir = Path(args.baseline_run) if args.baseline_run else find_latest_run(root, "baseline")
    out_dir = Path(args.out) if args.out else root / f"{utc_now().replace(':', '').replace('-', '')}-forged-replay"
    out_dir.mkdir(parents=True, exist_ok=True)
    genuine = read_jsonl(attack_dir / "probe-events.jsonl")
    clean = read_jsonl(baseline_dir / "probe-events.jsonl")
    genuine_result = naive_verifier(genuine)
    forged = forge_events(genuine)
    write_jsonl(out_dir / "forged-approved-events.jsonl", forged)
    forged_result = naive_verifier(forged)
    replayed = replay_events(clean, target_label=attack_dir.name)
    write_jsonl(out_dir / "replayed-clean-events.jsonl", replayed)
    replayed_result = naive_verifier(replayed)
    suppressed = suppress_events(genuine, clean, target_label=attack_dir.name)
    write_jsonl(out_dir / "suppressed-events.jsonl", suppressed)
    suppressed_result = naive_verifier(suppressed)
    report = {
        "schema": "a_next.registry.forgery_attack.v1",
        "utc": utc_now(),
        "attack_run": str(attack_dir),
        "baseline_run": str(baseline_dir),
        "genuine_records": len(genuine),
        "genuine_self_report_verdict": genuine_result,
        "attacks": [
            {
                "attack": "forge_digest_and_registry",
                "forged_file": str(out_dir / "forged-approved-events.jsonl"),
                "naive_verifier": forged_result,
                "attack_succeeded": forged_result["accepted"],
                "why": "records carry no MAC/signature/trusted-channel binding; any editor can rewrite tool digests and epochs",
            },
            {
                "attack": "replay_clean_run_events",
                "replayed_file": str(out_dir / "replayed-clean-events.jsonl"),
                "naive_verifier": replayed_result,
                "attack_succeeded": replayed_result["accepted"],
                "why": "run_label/epoch/utc are plain JSON fields chosen by the Candidate; no cross-run secret or Controller-issued nonce binds them",
            },
            {
                "attack": "suppress_offending_records",
                "suppressed_file": str(out_dir / "suppressed-events.jsonl"),
                "naive_verifier": suppressed_result,
                "attack_succeeded": suppressed_result["accepted"],
                "why": "an absence-only verifier cannot distinguish deleted evidence from clean evidence; observer loss is indistinguishable from clean in JSONL alone",
            },
        ],
        "conclusion": ("L1 self-report JSONL is forgeable/replayable/suppressible; it must not be "
                       "promoted to attestation. A trusted out-of-band measurement channel is required "
                       "for option A and is not provided by the frozen DSH SDK."),
        "trust_boundary": ("Candidate process is the producer of the file; no MAC, no signature, "
                           "no Controller nonce, no OS measurement is bound to these records."),
    }
    (out_dir / "attack-report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "out_dir": str(out_dir),
        "genuine_verdict": genuine_result,
        "forge_accepted": forged_result["accepted"],
        "replay_accepted": replayed_result["accepted"],
        "suppress_accepted": suppressed_result["accepted"],
    }, indent=2, sort_keys=True))
    return 0 if all([genuine_result["accepted"],
                     forged_result["accepted"],
                     replayed_result["accepted"],
                     suppressed_result["accepted"]]) else 1


if __name__ == "__main__":
    sys.exit(main())
