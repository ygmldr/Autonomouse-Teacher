"""Offline deterministic demo for the M1 Offline Teacher evaluation line.

Run with::

    cd /root/at-m1-offline
    "/root/Autonomous Teacher/.venv/bin/python" -m m1_offline.demo

The demo is fully local: no network, no API key, no real provider, no real
personal data.  It exercises:

1. a 3-round replayable teaching closed loop with the adaptive policy (v1),
2. a 3-round fixed-policy loop (v0) for contrast,
3. trace replay verification (state rebuilt from JSONL events),
4. the fixed-case / fixed-seed / blind-rubric v0-v1 comparison,
5. the public/hidden contamination scan,

and prints an explicit "offline synthetic, not real teaching effect" boundary.
Two consecutive runs produce byte-identical stdout; the loop traces use a
deterministic clock, so the JSONL artifacts are reproducible too.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from m1_offline import REPO_ROOT
from m1_offline.evaluation.compare import DISCLAIMER, SCORER_MODULE_ID, run_comparison
from m1_offline.evaluation.contamination import (
    FAIL,
    NOT_RUN,
    ContaminationReport,
    load_injection_texts,
    run_contamination_suite,
)
from m1_offline.evaluation.harness import (
    replay_trace,
    run_closed_loop,
    trace_digest,
)
from m1_offline.evaluation.report import (
    DEFAULT_REPO_ROOT,
    MEASURED,
    RunReport,
    environment_snapshot,
    write_report,
)
from m1_offline.teaching_policy import AdaptivePolicy, FixedPolicy
from m1_offline.types import LearnerProfile

DEMO_TRACE_V1 = Path("docs/m1/traces/loop_v1_3rounds.jsonl")
DEMO_TRACE_V0 = Path("docs/m1/traces/loop_v0_3rounds.jsonl")
DEMO_REPORT_JSON = Path("docs/m1/reports/eval_baseline_v1.json")


def _load_profile(learner_id: str) -> LearnerProfile:
    return LearnerProfile(learner_id=learner_id)


def _run_loop(policy, *, trace_path: Path | None):
    return run_closed_loop(
        policy=policy,
        seed=0,
        max_rounds=3,
        loop_id=f"loop_{policy.policy_version}_seed0",
        trace_path=trace_path,
    )


def _print_loop_summary(result) -> None:
    print(
        f"[closed-loop] loop_id={result.loop_id} policy={result.policy_version} seed={result.seed}"
    )
    print(
        f"[closed-loop] rounds={result.completed_rounds} passed_rounds={result.passed_rounds} "
        f"events={len(result.events)} halt={result.halt_reason or 'max_rounds'}"
    )
    print(f"[closed-loop] trace_digest={trace_digest(result.events)}")
    for record in result.rounds:
        assessment = record.assessment
        passed = "PASS" if assessment and assessment.passed else "FAIL"
        cases = (
            f"{assessment.hidden_cases_passed}/{assessment.hidden_cases_total}"
            if assessment
            else "n/a"
        )
        print(
            f"[round] n={record.round} task={record.task_id} action={record.action.kind} "
            f"hint_level={record.action.hint_level} assessment={passed} hidden_cases={cases} "
            f"mastery={json.dumps(record.state_after['mastery'], sort_keys=True)}"
        )
    print(f"[closed-loop] failure_markers={result.failure_markers}")


def _verify_determinism() -> bool:
    """Run the same loop twice in-process and compare byte-level trace renderings."""

    first = run_closed_loop(policy=AdaptivePolicy(), seed=0, max_rounds=3)
    second = run_closed_loop(policy=AdaptivePolicy(), seed=0, max_rounds=3)
    digest_match = trace_digest(first.events) == trace_digest(second.events)
    bytes_match = first.to_jsonl() == second.to_jsonl()
    state_match = first.final_state.mastery == second.final_state.mastery
    ok = digest_match and bytes_match and state_match
    print(
        f"[determinism] trace_bytes_identical={bytes_match} digest_match={digest_match} "
        f"state_match={state_match} -> {'PASS' if ok else 'FAIL'}"
    )
    return ok


def _verify_replay(result) -> bool:
    profile = _load_profile(result.final_state.learner_id)
    replay = replay_trace(result.events, learner_profile=profile)
    ok = (
        replay.assessment_ids() == result.assessment_ids
        and replay.evidence_ids() == result.evidence_ids
        and replay.final_state is not None
        and replay.final_state.mastery == result.final_state.mastery
        and replay.step_sequence == result.step_sequence()
    )
    print(
        f"[replay] assessments_match={replay.assessment_ids() == result.assessment_ids} "
        f"evidence_match={replay.evidence_ids() == result.evidence_ids} "
        f"state_match={replay.final_state is not None and replay.final_state.mastery == result.final_state.mastery} "
        f"steps_match={replay.step_sequence == result.step_sequence()} -> {'PASS' if ok else 'FAIL'}"
    )
    return ok


def _run_contamination() -> ContaminationReport:
    injection_texts = load_injection_texts(REPO_ROOT)
    system_instructions: list[str] = []
    coach_path = REPO_ROOT / "m1_offline/interview/coach.py"
    if coach_path.is_file():
        system_instructions.append(coach_path.read_text(encoding="utf-8"))
    return run_contamination_suite(
        REPO_ROOT, injection_texts=injection_texts, system_instructions=system_instructions
    )


def _contamination_counts(details: dict) -> dict:
    """Only aggregate counts are printed; hidden fixture paths are never echoed."""

    keep = {
        "hidden_file_count",
        "public_file_count",
        "scanned_public_files",
        "scanned_files",
        "substring_hits",
        "hash_window_hits",
        "needles_checked",
        "injection_documents",
        "system_instruction_chunks",
        "findings",
    }
    return {key: details[key] for key in sorted(keep) if key in details}


def _print_contamination(report: ContaminationReport) -> None:
    print("[contamination] public/hidden separation and leakage scan")
    for check in report.checks:
        print(
            f"[contamination] {check.check_id}: {check.status} "
            f"details={json.dumps(_contamination_counts(check.details), sort_keys=True)}"
        )
    print(
        "[contamination] overall_ok="
        f"{report.ok} status_counts={json.dumps(report.status_counts, sort_keys=True)}"
    )


def _print_comparison(result) -> None:
    payload = result.to_dict()
    print("[compare] teacher_v0 (FixedPolicy) vs teacher_v1 (AdaptivePolicy)")
    print(
        f"[compare] cases={payload['case_catalog_size']} seeds={payload['seeds']} "
        f"max_rounds={payload['max_rounds']} rounds={payload['total_rounds_measured']} "
        f"trajectories={payload['policies']['teacher_v0']['trajectories'] * 2} "
        f"blind_rubric={SCORER_MODULE_ID}"
    )
    print(
        f"[compare] cases_assessed={len(payload['cases_assessed'])} "
        f"failure_cases={payload['failure_case_count']}"
    )
    print("[compare] dimension | v0 mean | v0 var | v1 mean | v1 var | delta(v1-v0)")
    for dimension, delta in payload["delta_v1_minus_v0"].items():
        v0 = payload["policies"]["teacher_v0"]["statistics"][dimension]
        v1 = payload["policies"]["teacher_v1"]["statistics"][dimension]
        print(
            f"[compare] {dimension} | {v0['mean']:.6f} | {v0['variance']:.6f} | "
            f"{v1['mean']:.6f} | {v1['variance']:.6f} | {delta:+.6f}"
        )
    print(f"[compare] conclusion: {payload['conclusion']}")


def build_demo_report(loop_v1, replay_ok: bool, determinism_ok: bool, comparison, contamination):
    """Build a JSON/Markdown run report capturing the measured demo numbers."""

    comparison_payload = comparison.to_dict()
    run = RunReport(
        title="M1 offline evaluation baseline (demo run)",
        command='cd /root/at-m1-offline && "/root/Autonomous Teacher/.venv/bin/python" -m m1_offline.demo',
        environment=environment_snapshot(DEFAULT_REPO_ROOT),
    )
    run.add_metric(
        "closed_loop_rounds_v1",
        ">=3",
        str(loop_v1.completed_rounds),
        MEASURED,
        "m1_offline.demo",
    )
    run.add_metric(
        "closed_loop_trace_events",
        ">=19 (4 baseline + 5 steps x 3 rounds)",
        str(len(loop_v1.events)),
        MEASURED,
        "m1_offline.demo",
    )
    run.add_metric(
        "replay_equivalence",
        "100%",
        "PASS" if replay_ok else "FAIL",
        MEASURED,
        "m1_offline.demo",
    )
    run.add_metric(
        "v0v1_cases_assessed",
        "fixed catalog >=12 cases",
        f"{len(comparison_payload['cases_assessed'])} assessed / "
        f"{comparison_payload['case_catalog_size']} catalog",
        MEASURED,
        "m1_offline.demo",
    )
    run.add_metric(
        "v0v1_rounds",
        ">=12",
        str(comparison_payload["total_rounds_measured"]),
        MEASURED,
        "m1_offline.demo",
    )
    run.add_metric(
        "v0v1_failure_cases",
        ">=1",
        str(comparison_payload["failure_case_count"]),
        MEASURED,
        "m1_offline.demo",
    )
    run.add_metric(
        "contamination_status",
        "all PASS",
        json.dumps(contamination.status_counts, sort_keys=True),
        MEASURED,
        "m1_offline.demo",
    )
    run.add_metric(
        "demo_determinism",
        "byte-identical trace across two runs",
        "PASS" if determinism_ok else "FAIL",
        MEASURED,
        "m1_offline.demo (in-process double run)",
    )
    for policy_name in ("teacher_v0", "teacher_v1"):
        for dimension in (
            "correctness",
            "rounds_to_first_success",
            "hint_efficiency",
            "independence",
        ):
            stats = comparison_payload["policies"][policy_name]["statistics"][dimension]
            run.add_metric(
                f"{policy_name}_{dimension}",
                "record mean/variance",
                f"mean={stats['mean']} var={stats['variance']}",
                MEASURED,
                "m1_offline.demo",
            )
    for check in contamination.checks:
        run.add_check(check.check_id, check.description, check.status)
    run.add_section(
        "comparison",
        {
            "protocol": comparison_payload["protocol"],
            "run_digest": comparison_payload["run_digest"],
            "case_catalog_size": comparison_payload["case_catalog_size"],
            "cases_assessed": comparison_payload["cases_assessed"],
            "seeds": comparison_payload["seeds"],
            "max_rounds": comparison_payload["max_rounds"],
            "total_rounds_measured": comparison_payload["total_rounds_measured"],
            "failure_case_count": comparison_payload["failure_case_count"],
            "failure_cases": comparison_payload["failure_cases"],
            "statistics": {
                policy: comparison_payload["policies"][policy]["statistics"]
                for policy in ("teacher_v0", "teacher_v1")
            },
            "runs": {
                policy: comparison_payload["policies"][policy]["runs"]
                for policy in ("teacher_v0", "teacher_v1")
            },
            "delta_v1_minus_v0": comparison_payload["delta_v1_minus_v0"],
            "conclusion": comparison_payload["conclusion"],
            "disclaimer": comparison_payload["disclaimer"],
        },
    )
    run.add_section(
        "contamination",
        {
            "overall_ok": contamination.ok,
            "status_counts": contamination.status_counts,
            "checks": [
                {
                    "check_id": check.check_id,
                    "description": check.description,
                    "status": check.status,
                    "counts": _contamination_counts(check.details),
                }
                for check in contamination.checks
            ],
        },
    )
    run.artifacts = [
        "docs/m1/traces/loop_v1_3rounds.jsonl",
        "docs/m1/traces/loop_v0_3rounds.jsonl",
        "docs/m1/reports/contamination_v1.json",
    ]
    run.not_run = [
        "real provider / live runtime evaluation (out of scope: offline synthetic only)",
        "real learner outcomes (impossible offline; not claimed)",
    ]
    run.unverified = [
        "M0 Runtime API capabilities (UNVERIFIED; RuntimePort is a mock abstraction)",
        "real teaching effectiveness (not measured; no extrapolation allowed)",
    ]
    run.notes = [
        "Numbers come from a deterministic local simulator over synthetic fixtures.",
        comparison_payload["conclusion"],
    ]
    return run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Deterministic offline M1 evaluation demo (no network, no API key)."
    )
    parser.add_argument(
        "--write-artifacts",
        action="store_true",
        help="write deterministic loop traces + a baseline report under docs/m1/",
    )
    parser.add_argument(
        "--compare-seeds",
        default="0,1,2",
        help="comma separated fixed seeds for the v0/v1 comparison (default: 0,1,2)",
    )
    parser.add_argument(
        "--max-rounds",
        type=int,
        default=12,
        help="rounds per comparison trajectory (default: 12)",
    )
    args = parser.parse_args(argv)

    trace_v1 = DEMO_TRACE_V1 if args.write_artifacts else None
    trace_v0 = DEMO_TRACE_V0 if args.write_artifacts else None

    print("== M1 Offline Teacher evaluation demo ==")
    print("[boundary] offline synthetic simulation; not real teaching effect")
    print("[boundary] no network / no API key / no real provider / no real personal data")

    loop_v1 = _run_loop(AdaptivePolicy(), trace_path=trace_v1)
    _print_loop_summary(loop_v1)
    replay_ok = _verify_replay(loop_v1)
    determinism_ok = _verify_determinism()

    loop_v0 = _run_loop(FixedPolicy(), trace_path=trace_v0)
    _print_loop_summary(loop_v0)
    replay_ok = _verify_replay(loop_v0) and replay_ok

    seeds = tuple(int(part) for part in args.compare_seeds.split(",") if part.strip())
    comparison = run_comparison(seeds=seeds or (0, 1, 2), max_rounds=args.max_rounds)
    _print_comparison(comparison)

    contamination = _run_contamination()
    _print_contamination(contamination)

    if args.write_artifacts:
        run_report = build_demo_report(
            loop_v1, replay_ok, determinism_ok, comparison, contamination
        )
        json_path, markdown_path = write_report(
            run_report,
            json_path=DEMO_REPORT_JSON,
            markdown_path=DEMO_REPORT_JSON.with_suffix(".md"),
            root=DEFAULT_REPO_ROOT,
        )
        print(f"[artifacts] trace_v1={DEMO_TRACE_V1} trace_v0={DEMO_TRACE_V0}")
        print(f"[artifacts] report_json={json_path} report_md={markdown_path}")

    failures = contamination.status_counts.get(FAIL, 0)
    not_run = contamination.status_counts.get(NOT_RUN, 0)
    verdict = (
        loop_v1.completed_rounds >= 3
        and loop_v0.completed_rounds >= 3
        and replay_ok
        and determinism_ok
        and failures == 0
    )
    print(
        f"[result] closed_loop={'PASS' if loop_v1.completed_rounds >= 3 and loop_v0.completed_rounds >= 3 else 'FAIL'} "
        f"replay={'PASS' if replay_ok else 'FAIL'} "
        f"determinism={'PASS' if determinism_ok else 'FAIL'} "
        f"comparison={'PASS' if comparison.run_digest else 'FAIL'} "
        f"contamination={'PASS' if failures == 0 else 'FAIL'}"
        + (f" contamination_not_run={not_run}" if not_run else "")
    )
    print(
        f"[result] deterministic_output=true (see tests for byte-level check) -> {'PASS' if verdict else 'FAIL'}"
    )
    print(f"[boundary] {DISCLAIMER}")
    return 0 if verdict else 1


if __name__ == "__main__":
    sys.exit(main())
