#!/usr/bin/env python3
"""A-PR3 / R-REV6 exclusive-window matrix runner (real DSH, Fake-only, no key).

Single writer, single writer evidence root.  For every selected case it creates
a fresh writable rootfs copy from the staged canonical rootfs, verifies the
hash, runs ``launch_case.py`` in its own subprocess (one process per case), then
checks that no container is left behind and removes the rootfs work copy.

Gates before the first case (all must pass):
  * head == expected run HEAD, worktree clean;
  * staged frozen rootfs/deps re-hash == canonical constants;
  * ``podman ps -a`` empty;
  * output/evidence roots do not exist yet;
  * the new Stage passes ``validate_stage_g4(base_sha=HEAD, verify_git=True)``.

The runner never modifies the stage, the frozen inputs or the source tree.
Results land in the gitignored ``artifacts/a_next/rrev6/l2/<run-id>/`` tree.

Fail-closed semantics (A-PR3 P2-A4-2/P2-A4-3):
  * before anything heavy, a fail-fast prerequisite check names every missing
    staged input (rootfs/deps/artifacts/g4/c incl. runs/plugin node_modules/
    stage/runner/audit/matrix) and exits non-zero with ``RUNNER_PREREQ_MISSING``;
  * after the audit, any non-PASS case status (INTERNAL/PARTIAL/FAIL/NOT_RUN/...)
    or an audit/summary mismatch makes the process exit non-zero.  ``ok=true``
    in the final JSON is never printed when a case failed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts" / "g3d"))
sys.path.insert(0, str(REPO / "scripts" / "g4"))
sys.path.insert(0, str(REPO / "scripts" / "a_next" / "rrev6"))

import lib_g3d as lib3d  # noqa: E402
import lib_g4c as libc  # noqa: E402

PYTHON = sys.executable
RUNNER = REPO / "scripts" / "a_next" / "rrev6" / "launch_case.py"
STAGED_ROOTFS = REPO / "artifacts" / "security" / "rootfs"
STAGED_DEPS = REPO / "artifacts" / "foundation" / "deps"

ECHO_PROMPT = "A_NEXT_RREV6 Echo nonce-echo-7c1f public synthetic prompt"
TOOL_PROMPT = "A_NEXT_RREV6 Tool round nonce-tool-9a2b public synthetic prompt"
RESUME_ALPHA = "A_NEXT_RREV6 resume alpha nonce-7f3a9c remember this string"
RESUME_BETA = "A_NEXT_RREV6 resume beta: what nonce did I ask you to remember?"
REPLAY_PROMPT = "A_NEXT_RREV6 replay nonce-replay-51d0 public synthetic prompt"

# case_id -> launch_case kwargs. Order deliberately runs the stable primary
# evidence first; conditional injections run after the core matrix is captured.
CASES: list[dict] = [
    {"id": "R6-01", "turns": [
        {"label": "t1", "scenario": "echo", "prompt": ECHO_PROMPT}],
     "session": "a-next-r6-01"},
    {"id": "R6-02", "turns": [
        {"label": "t1", "scenario": "tool", "prompt": TOOL_PROMPT}],
     "session": "a-next-r6-02", "args": ["--scenario", "tool",
                                         "--max-calls", "8"]},
    {"id": "R6-03", "turns": [
        {"label": "t1", "scenario": "echo", "prompt": RESUME_ALPHA},
        {"label": "t2", "scenario": "resume", "prompt": RESUME_BETA}],
     "session": "a-next-r6-03", "args": ["--max-calls", "8"]},
    {"id": "R6-04", "turns": [
        {"label": "t1", "scenario": "echo", "prompt": REPLAY_PROMPT},
        {"label": "t2", "scenario": "echo", "prompt": REPLAY_PROMPT}],
     "session": "a-next-r6-04"},
    {"id": "R6-04B", "args": ["--candidate-mode", "hold", "--scenario", "echo",
                              "--label", "r6-04b",
                              "--steps", "valid,replay", "--max-calls", "8"]},
    {"id": "R6-05", "args": ["--scenario", "echo", "--deadline-ms", "800",
                             "--test-delay-hook", "before_reserve",
                             "--test-delay-ms", "2500"]},
    {"id": "R6-06", "args": ["--scenario", "echo", "--revocation",
                             "--test-delay-hook", "after_reserve_before_send",
                             "--test-delay-ms", "6000",
                             "--watch-revocation", "after_reserve",
                             "--steps", "stop-trusted,restart"]},
    {"id": "R6-07", "args": ["--scenario", "stream", "--deadline-ms", "800",
                             "--steps", "stop-trusted,restart"]},
    {"id": "R6-08", "args": ["--scenario", "echo",
                             "--crash-hook", "after_attempt_start_before_fake_send",
                             "--steps", "restart"]},
    {"id": "R6-10", "args": ["--scenario", "echo", "--deadline-ms", "800",
                             "--test-delay-hook", "after_reserve_before_send",
                             "--test-delay-ms", "6000",
                             "--inject", "candidate-crash"]},
    {"id": "R6-09", "args": ["--scenario", "echo",
                             "--test-delay-hook", "after_reserve_before_send",
                             "--test-delay-ms", "6000",
                             "--inject", "trusted-kill", "--steps", "restart"]},
    {"id": "R6-11", "args": ["--scenario", "stream",
                             "--inject", "fake-crash-after-receipt",
                             "--steps", "stop-trusted,restart"]},
    {"id": "R6-12", "args": ["--scenario", "echo",
                             "--test-delay-hook", "after_reserve_before_send",
                             "--test-delay-ms", "6000",
                             "--inject", "broker-kill",
                             "--steps", "stop-trusted,restart"]},
    {"id": "R6-13", "audit_only": True},
]


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def sha256_tree(path: Path) -> str:
    proc = subprocess.run(
        ["tar", "--sort=name", "--mtime=@0", "--owner=0", "--group=0",
         "--numeric-owner", "-cf", "-", "-C", str(path), "."],
        capture_output=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"tar failed for {path}")
    return hashlib.sha256(proc.stdout).hexdigest()


def git(*args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=str(REPO), capture_output=True,
                          text=True)
    return proc.stdout.strip() if proc.returncode == 0 else ""


def containers() -> list[str]:
    proc = subprocess.run(["podman", "ps", "-a", "--format", "{{.Names}}"],
                          capture_output=True, text=True, timeout=60)
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def prerequisite_problems(
        *, stage: Path,
        rootfs: Path = STAGED_ROOTFS,
        deps: Path = STAGED_DEPS,
        g4c_root: Path = REPO / "artifacts" / "g4" / "c",
        plugin_modules: Path = REPO / "plugins" / "offline-fixture" / "node_modules",
        launch_case: Path = RUNNER,
        evidence_audit: Path | None = None,
        matrix_spec: Path | None = None,
        canonical_check: bool = True) -> dict:
    """Fail-fast prerequisites for an independent R-REV6 L2 rerun.

    Returns an explicit problem list (id/path/message/remediation); a missing
    prerequisite must stop the runner with a non-zero exit instead of failing
    every case as INTERNAL.  ``canonical_check=False`` exists only for host
    unit tests that use synthetic directories.
    """
    if evidence_audit is None:
        evidence_audit = REPO / "scripts" / "a_next" / "rrev6" / "evidence_audit.py"
    if matrix_spec is None:
        matrix_spec = REPO / "scripts" / "a_next" / "rrev6" / "case_matrix.json"
    problems: list[dict] = []

    def add(problem_id: str, path: Path, message: str, remediation: str) -> None:
        problems.append({"id": problem_id, "path": str(path),
                         "message": message, "remediation": remediation})

    if not rootfs.is_dir():
        add("staged_rootfs_missing", rootfs,
            "staged canonical rootfs is absent (fresh worktree not prepared)",
            "copy the hash-verified frozen rootfs to artifacts/security/rootfs")
    elif canonical_check:
        digest = sha256_tree(rootfs)
        if digest != lib3d.ROOTFS_CANON:
            add("staged_rootfs_not_canonical", rootfs,
                f"staged rootfs sha256 {digest} != {lib3d.ROOTFS_CANON}",
                "restore the canonical rootfs copy; never run containers on a drifted copy")
    if not deps.is_dir():
        add("staged_deps_missing", deps,
            "staged canonical deps are absent (fresh worktree not prepared)",
            "copy the hash-verified frozen deps to artifacts/foundation/deps")
    elif canonical_check:
        digest = sha256_tree(deps)
        if digest != lib3d.DEPS_CANON:
            add("staged_deps_not_canonical", deps,
                f"staged deps sha256 {digest} != {lib3d.DEPS_CANON}",
                "restore the canonical deps copy")
    if not g4c_root.is_dir():
        add("artifacts_g4c_missing", g4c_root,
            "artifacts/g4/c is absent; stage build/run dirs cannot be created",
            "stage the G4-C build root (artifacts/g4/c) before rerunning")
    elif not (g4c_root / "runs").is_dir():
        add("artifacts_g4c_runs_missing", g4c_root / "runs",
            "artifacts/g4/c/runs is absent; every case run dir would fail as INTERNAL",
            f"mkdir -p {g4c_root / 'runs'} (and keep it writable)")
    if not plugin_modules.is_dir():
        add("plugin_node_modules_missing", plugin_modules,
            "plugins/offline-fixture/node_modules is absent",
            "copy the plugin node_modules needed by the adapter build")
    if not stage.is_dir() or not (stage / "manifest.json").is_file():
        add("stage_manifest_missing", stage,
            "stage directory or manifest.json is missing",
            "build a fresh Stage at the run HEAD with scripts/a_next/rrev6/build_stage.py")
    if not launch_case.is_file():
        add("launch_case_missing", launch_case,
            "launch_case.py is missing", "check out scripts/a_next/rrev6")
    if not Path(evidence_audit).is_file():
        add("evidence_audit_missing", Path(evidence_audit),
            "evidence_audit.py is missing", "check out scripts/a_next/rrev6")
    if not Path(matrix_spec).is_file():
        add("case_matrix_missing", Path(matrix_spec),
            "case_matrix.json is missing", "check out scripts/a_next/rrev6")
    return {
        "schema": "m0.a_next.rrev6.prerequisites.v1",
        "utc": utc_now(), "ok": not problems, "problems": problems,
    }


def evaluate_audit(audit: object, *, expected_case_ids: list[str] | None = None) -> dict:
    """Fail-closed decision over the evidence audit.

    Any non-PASS status (INTERNAL/PARTIAL/FAIL/NOT_RUN/...) or a missing/partial
    audit makes the runner exit non-zero.  This is the P2-A4-2 fix: a failed
    matrix must never report ``ok=true`` / exit 0.
    """
    problems: list[dict] = []
    if not isinstance(audit, dict) or not audit.get("cases"):
        return {"ok": False, "problems": [
            {"id": "audit_missing", "message": "audit.json missing or empty"}]}
    cases = audit.get("cases") or {}
    counts = audit.get("counts") or {}
    statuses = {case_id: (row or {}).get("status")
                for case_id, row in cases.items()}
    failed = {case_id: status for case_id, status in statuses.items()
              if status != "PASS"}
    if failed:
        problems.append({"id": "audit_non_pass_cases", "cases": failed,
                         "message": "audit contains non-PASS case statuses"})
    if counts.get("total") != len(cases):
        problems.append({"id": "audit_counts_inconsistent",
                         "counts": counts, "cases": len(cases)})
    if counts.get("pass") != len(cases):
        problems.append({"id": "audit_pass_count_mismatch",
                         "counts": counts, "cases": len(cases)})
    for case_id in expected_case_ids or []:
        if case_id not in cases:
            problems.append({"id": "audit_case_missing", "case_id": case_id})
    return {"ok": not problems, "problems": problems,
            "statuses": statuses, "counts": counts}


def decide_run(*, containers_after: list[str], frozen_rootfs_unchanged: bool,
               frozen_deps_unchanged: bool, audit: object,
               expected_case_ids: list[str] | None = None) -> dict:
    """Pure fail-closed decision used by ``main`` and by the host unit tests.

    P2-A4-2: a matrix where any case audit is non-PASS (or audit is missing)
    must return ``ok=False`` with explicit ``failure_reasons``; callers map that
    to a non-zero process exit.
    """
    audit_decision = evaluate_audit(audit, expected_case_ids=expected_case_ids)
    reasons: list[str] = []
    if containers_after:
        reasons.append("containers_after_not_empty")
    if not frozen_rootfs_unchanged:
        reasons.append("frozen_rootfs_drift")
    if not frozen_deps_unchanged:
        reasons.append("frozen_deps_drift")
    for problem in audit_decision["problems"]:
        reasons.append(problem.get("id", "audit_problem"))
    return {"ok": not reasons, "failure_reasons": reasons,
            "audit_decision": audit_decision}


def write_json(path: Path, document: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")


def t0_record(stage: Path) -> dict:
    rootfs_sha = sha256_tree(STAGED_ROOTFS)
    deps_sha = sha256_tree(STAGED_DEPS)
    validation = libc.validate_stage_g4(stage, base_sha=git("rev-parse", "HEAD"),
                                        verify_git=True)
    return {
        "schema": "m0.a_next.rrev6.t0.v1", "utc": utc_now(),
        "head": git("rev-parse", "HEAD"),
        "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "worktree_clean": git("status", "--porcelain", "-uall") == "",
        "containers": containers(),
        "rootfs": {"path": str(STAGED_ROOTFS), "sha256": rootfs_sha,
                   "expected": lib3d.ROOTFS_CANON,
                   "canonical": rootfs_sha == lib3d.ROOTFS_CANON},
        "deps": {"path": str(STAGED_DEPS), "sha256": deps_sha,
                 "expected": lib3d.DEPS_CANON,
                 "canonical": deps_sha == lib3d.DEPS_CANON},
        "stage": {"path": str(stage),
                  "base_sha": validation.get("base_sha"),
                  "manifest_sha256": validation.get("manifest_sha256"),
                  "stage_tree_sha256": sha256_tree(stage),
                  "trusted_tree_sha256": validation.get("trusted_tree_sha256"),
                  "candidate_tree_sha256": validation.get("candidate_tree_sha256"),
                  "valid": validation.get("ok"),
                  "problems": validation.get("problems", [])[:20]},
        "note": ("frozen rootfs/deps came from hash-verified recovery copies "
                 "after the 2026-11-20 artifacts-loss event (see report)"),
        "real_model_calls": 0, "real_external_http_calls": 0,
        "provider_keys_seen": 0,
    }


def run_case(case: dict, *, stage: Path, out: Path, work_root: Path,
             stamp: str) -> dict:
    case_id = case["id"]
    evidence = out / "cases" / f"{case_id}-{stamp}"
    if evidence.exists():
        return {"case_id": case_id, "status": "BLOCKED",
                "reason": "evidence_dir_exists"}
    work = work_root / f"rootfs-{case_id}-{stamp}"
    work.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(STAGED_ROOTFS, work, symlinks=True)
    work_sha = sha256_tree(work)
    if work_sha != lib3d.ROOTFS_CANON:
        shutil.rmtree(work, ignore_errors=True)
        return {"case_id": case_id, "status": "BLOCKED",
                "reason": "work_copy_not_canonical"}
    run_id = f"anx-{case_id.lower()}-{stamp}"
    argv = [PYTHON, "-B", str(RUNNER), "--case", case_id,
            "--stage", str(stage), "--evidence-dir", str(evidence),
            "--run-id", run_id, "--rootfs-work", str(work),
            "--session", case.get("session", f"a-next-{case_id.lower()}")]
    if case.get("turns"):
        argv += ["--turns", json.dumps(case["turns"])]
    argv += case.get("args", [])
    log_dir = out / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{case_id}.log"
    started = utc_now()
    with log_path.open("w", encoding="utf-8") as handle:
        handle.write("ARGV " + json.dumps(argv) + "\n")
        handle.flush()
        proc = subprocess.run(argv, cwd=str(REPO), capture_output=True,
                              text=True, timeout=float(case.get("timeout", 240)),
                              env={**os.environ, "PYTHONPATH": str(REPO / "src")})
        handle.write(proc.stdout)
        handle.write(proc.stderr)
    finished = utc_now()
    leftovers = containers()
    for name in leftovers:
        subprocess.run(["podman", "rm", "-f", name], capture_output=True,
                       text=True, timeout=60)
    final_work_sha = sha256_tree(work)
    shutil.rmtree(work, ignore_errors=True)
    return {
        "case_id": case_id, "status": "RUN", "run_id": run_id,
        "argv": argv, "utc_start": started, "utc_end": finished,
        "exit_code": proc.returncode,
        "stdout_tail": proc.stdout[-3000:], "stderr_tail": proc.stderr[-3000:],
        "evidence": str(evidence), "log": str(log_path),
        "rootfs_work_sha256_before": work_sha,
        "rootfs_work_sha256_after": final_work_sha,
        "containers_after_runner": leftovers,
        "real_model_calls": 0, "real_external_http_calls": 0,
        "provider_keys_seen": 0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", required=True)
    parser.add_argument("--out", default=None)
    parser.add_argument("--only", default=None,
                        help="comma separated case ids (default: all)")
    parser.add_argument("--expected-head", default=None)
    parser.add_argument("--work-root", default=None)
    args = parser.parse_args(argv)
    stage = Path(args.stage).resolve()
    stamp = utc_compact()
    out = (Path(args.out) if args.out else
           REPO / "artifacts" / "a_next" / "rrev6" / "l2" / f"run-{stamp}")
    if out.exists():
        sys.stderr.write("RUNNER_OUT_EXISTS\n")
        return lib3d.EXIT_BLOCKED_ENVIRONMENT
    head = git("rev-parse", "HEAD")
    if args.expected_head and head != args.expected_head:
        sys.stderr.write("RUNNER_HEAD_MISMATCH\n")
        return lib3d.EXIT_PREFLIGHT_IDENTITY
    if containers():
        sys.stderr.write("RUNNER_CONTAINERS_PRESENT\n")
        return lib3d.EXIT_BLOCKED_ENVIRONMENT
    if git("status", "--porcelain", "-uall") != "":
        sys.stderr.write("RUNNER_WORKTREE_DIRTY\n")
        return lib3d.EXIT_PREFLIGHT_IDENTITY
    prerequisites = prerequisite_problems(stage=stage)
    if not prerequisites["ok"]:
        abort_path = out.parent / f"prereq-abort-{stamp}.json"
        write_json(abort_path, prerequisites)
        sys.stderr.write("RUNNER_PREREQ_MISSING "
                         + json.dumps(prerequisites["problems"], sort_keys=True)
                         + "\n")
        return lib3d.EXIT_BLOCKED_ENVIRONMENT
    out.mkdir(parents=True, exist_ok=False)
    t0 = t0_record(stage)
    write_json(out / "t0.json", t0)
    problems = []
    if not t0["rootfs"]["canonical"] or not t0["deps"]["canonical"]:
        problems.append("frozen_not_canonical")
    if not t0["worktree_clean"]:
        problems.append("worktree_dirty")
    if t0["containers"]:
        problems.append("containers_present")
    if not t0["stage"]["valid"]:
        problems.append("stage_invalid")
    if t0["stage"]["base_sha"] != head:
        problems.append("stage_base_not_head")
    if problems:
        write_json(out / "abort.json", {"problems": problems, "utc": utc_now()})
        sys.stderr.write("RUNNER_T0_BLOCKED " + json.dumps(problems) + "\n")
        return lib3d.EXIT_PREFLIGHT_IDENTITY
    selected = ([case for case in CASES if case["id"] in args.only.split(",")]
                if args.only else list(CASES))
    work_root = (Path(args.work_root) if args.work_root else
                 REPO / "artifacts" / "a_next" / "rrev6" / "work")
    matrix: dict = {"schema": "m0.a_next.rrev6.matrix.v1",
                    "utc_start": utc_now(), "head": head,
                    "stage": t0["stage"], "cases": {}, "t0": str(out / "t0.json")}
    for case in selected:
        case_started = utc_now()
        if case.get("audit_only"):
            matrix["cases"][case["id"]] = {"case_id": case["id"],
                                           "status": "AUDIT_ONLY",
                                           "utc_start": case_started}
            continue
        try:
            record = run_case(case, stage=stage, out=out, work_root=work_root,
                              stamp=stamp)
        except subprocess.TimeoutExpired as exc:
            record = {"case_id": case["id"], "status": "TIMEOUT",
                      "reason": f"timeout {exc.timeout}"}
        except BaseException as exc:  # noqa: BLE001
            record = {"case_id": case["id"], "status": "ERROR",
                      "reason": f"{type(exc).__name__}: {exc}"}
        matrix["cases"][case["id"]] = record
        write_json(out / "matrix.json", matrix)
        print(json.dumps({"case": case["id"],
                          "status": record.get("status"),
                          "exit": record.get("exit_code")}, sort_keys=True))
    # T1 gate: frozen inputs must be byte-identical to T0.
    t1 = t0_record(stage)
    t1["schema"] = "m0.a_next.rrev6.t1.v1"
    t1["t0_rootfs_sha256"] = t0["rootfs"]["sha256"]
    t1["t0_deps_sha256"] = t0["deps"]["sha256"]
    t1["rootfs_matches_t0"] = t1["rootfs"]["sha256"] == t0["rootfs"]["sha256"]
    t1["deps_matches_t0"] = t1["deps"]["sha256"] == t0["deps"]["sha256"]
    t1["containers"] = containers()
    write_json(out / "t1.json", t1)
    matrix["utc_end"] = utc_now()
    matrix["t1"] = str(out / "t1.json")
    matrix["containers_after"] = t1["containers"]
    matrix["frozen_rootfs_unchanged"] = t1["rootfs_matches_t0"]
    matrix["frozen_deps_unchanged"] = t1["deps_matches_t0"]
    write_json(out / "matrix.json", matrix)
    # Evidence audit over the per-case read-only snapshots.
    audit: dict = {}
    try:
        from evidence_audit import audit_run
        audit = audit_run(out, matrix=matrix, matrix_spec=REPO / "scripts" /
                          "a_next" / "rrev6" / "case_matrix.json")
        write_json(out / "audit.json", audit)
    except BaseException as exc:  # noqa: BLE001
        write_json(out / "audit-error.json",
                   {"error": f"{type(exc).__name__}: {exc}"})
    selected_case_ids = [case["id"] for case in selected]
    decision = decide_run(
        containers_after=t1["containers"],
        frozen_rootfs_unchanged=t1["rootfs_matches_t0"],
        frozen_deps_unchanged=t1["deps_matches_t0"],
        audit=audit, expected_case_ids=selected_case_ids)
    audit_decision = decision["audit_decision"]
    summary = {
        "run_root": str(out), "head": head, "utc_start": matrix["utc_start"],
        "utc_end": matrix["utc_end"],
        "stage_manifest_sha256": t0["stage"]["manifest_sha256"],
        "stage_tree_sha256": t0["stage"]["stage_tree_sha256"],
        "frozen_rootfs_t0": t0["rootfs"]["sha256"],
        "frozen_rootfs_t1": t1["rootfs"]["sha256"],
        "frozen_rootfs_unchanged": t1["rootfs_matches_t0"],
        "frozen_deps_unchanged": t1["deps_matches_t0"],
        "containers_after": t1["containers"],
        "cases": {case_id: (case.get("audit_status")
                            or case.get("status"))
                  for case_id, case in (audit.get("cases") or {}).items()}
        if audit else {case_id: record.get("status")
                       for case_id, record in matrix["cases"].items()},
        "abort_conditions_triggered": [],
        "audit_ok": audit_decision["ok"],
        "audit_problems": audit_decision["problems"],
        "prerequisites_ok": prerequisites["ok"],
        "fail_closed": True,
    }
    failure_reasons: list[str] = decision["failure_reasons"]
    ok = decision["ok"]
    summary["ok"] = ok
    summary["failure_reasons"] = failure_reasons
    write_json(out / "summary.json", summary)
    write_json(out / "run_status.json", {
        "schema": "m0.a_next.rrev6.run-status.v1", "utc": utc_now(),
        "ok": ok, "failure_reasons": failure_reasons,
        "audit_ok": audit_decision["ok"],
        "audit_problems": audit_decision["problems"],
        "prerequisites_ok": prerequisites["ok"],
    })
    print(json.dumps({"ok": ok, "run_root": str(out),
                      "failure_reasons": failure_reasons,
                      "summary": summary}, sort_keys=True))
    return 0 if ok else lib3d.EXIT_CASE_FAILED


if __name__ == "__main__":
    raise SystemExit(main())
