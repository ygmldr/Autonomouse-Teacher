#!/usr/bin/env python3
"""D3 suite orchestrator: child real-container runs, REG-01..04, gate rollup.

The suite never weakens a single-case judge.  A suite passes only when every
child exits 0; REG-01..04 are evaluated independently and left as their own
matrix rows.  All commands/argv/UTC/exit/stdout/stderr are stored under
``artifacts/g3d/d3/``.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib_g3d as lib  # noqa: E402

REPO = lib.REPO_ROOT
PYTHON = "/root/.local/bin/python3.11"
SUITES: dict[str, list[str]] = {
    "d3-01": ["d3-c01-echo", "d3-c04", "d3-c05"],
    "d3-c01": ["d3-c01-echo", "d3-c01-tool", "d3-c01-resume"],
    "d3-c07": ["d3-c07-before", "d3-c07-after", "d3-c07-two"],
    "d3-c08": ["d3-c08-half", "d3-c08-disconnect", "d3-c08-sigterm"],
    "d3-c09": ["d3-c09-broker", "d3-c09-fake", "d3-c09-stall"],
    "d3-c11": ["d3-c11-real", "d3-c11-same"],
}
SINGLES = [
    "d3-c02", "d3-c03", "d3-c04", "d3-c05", "d3-c06", "d3-c10", "d3-c12",
]


def utc() -> str:
    return lib.utc()


def write_json(path: Path, document: object) -> None:
    lib.write_json_atomic(path, document, mode=0o444)


def run_process(argv: list[str], *, log_dir: Path, name: str,
                timeout: float = 900, env: dict | None = None,
                cwd: str | None = None) -> dict:
    log_dir.mkdir(parents=True, exist_ok=True)
    record = lib.run_command(argv, log_dir=log_dir, name=name, timeout=timeout,
                             env=env, cwd=cwd)
    record.pop("stdout", None)
    record.pop("stderr", None)
    return record


def case_evidence(root: Path, suite: str, child: str) -> Path:
    short = child.replace("d3-c", "").replace("d3-", "")
    return root / suite / short


def run_case(root: Path, stage: str, case: str, evidence: Path) -> dict:
    argv = [PYTHON, "-B", str(REPO / "scripts" / "g3d" / "d3_runner.py"),
            "--case", case, "--stage", stage, "--evidence-dir", str(evidence)]
    started = utc()
    record = run_process(argv, log_dir=evidence.parent / "logs",
                         name=f"{case}", timeout=1200)
    summary_path = evidence / "summary.json"
    summary = None
    if summary_path.is_file():
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            summary = None
    return {
        "case": case, "argv": argv, "utc_start": started,
        "utc_end": utc(), "exit": record["exit"],
        "status": "PASS" if record["exit"] == 0 else "FAIL",
        "evidence": str(evidence),
        "summary_sha256": lib.sha256_file(summary_path)
        if summary_path.is_file() else None,
        "checks": None if summary is None else (summary.get("case_checks") or {}),
        "failure": None if summary is None else summary.get("failure"),
        "stdout_path": record.get("stdout_path"),
        "stderr_path": record.get("stderr_path"),
    }


def suite(root: Path, stage: str, name: str, children: list[str]) -> dict:
    folder = root / name
    folder.mkdir(parents=True, exist_ok=True)
    results = []
    for child in children:
        evidence = case_evidence(root, name, child)
        if evidence.exists():
            shutil.rmtree(evidence)
        results.append(run_case(root, stage, child, evidence))
    ok = all(item["exit"] == 0 for item in results)
    document = {
        "schema": "m0.g3d.d3.suite.v1", "suite": name,
        "utc_start": results[0]["utc_start"] if results else utc(),
        "utc_end": utc(), "status": "PASS" if ok else "FAIL",
        "children": results, "synthetic": True, "real_model_calls": 0,
    }
    write_json(folder / "summary.json", document)
    with (folder / "results.jsonl").open("w", encoding="utf-8") as handle:
        for item in results:
            handle.write(json.dumps(item, sort_keys=True) + "\n")
    return document


def canonical() -> dict:
    return {
        "utc": utc(),
        "rootfs": {"sha256": lib.sha256_tree(lib.ROOTFS),
                   "expected": lib.ROOTFS_CANON,
                   "ok": lib.sha256_tree(lib.ROOTFS) == lib.ROOTFS_CANON},
        "deps": {"sha256": lib.sha256_tree(lib.DEPS),
                 "expected": lib.DEPS_CANON,
                 "ok": lib.sha256_tree(lib.DEPS) == lib.DEPS_CANON},
        "stage": {"sha256": lib.sha256_tree(Path(os.environ["D3_STAGE"]))
                  if os.environ.get("D3_STAGE") else None},
    }


def ps_snapshot() -> list[str]:
    record = lib.run_command(["podman", "ps", "-a", "--format", "{{.Names}}"],
                             log_dir=Path("/tmp"), name="d3-ps", timeout=30)
    return [line for line in record["stdout"].splitlines() if line.strip()]


def residual_processes() -> list[dict]:
    markers = ("autoteacher_m0.bridge.controller", "fake_provider.py",
               "candidate_entry.py", "trusted_entry.py",
               "deepseek-harness-sdk-runtime")
    rows = []
    for name in os.listdir("/proc"):
        if not name.isdigit():
            continue
        pid = int(name)
        if pid == os.getpid():
            continue
        try:
            raw = Path(f"/proc/{pid}/cmdline").read_bytes()
        except OSError:
            continue
        text = raw.decode("utf-8", "replace")
        if any(marker in text for marker in markers):
            rows.append({"pid": pid, "cmdline": text[:300]})
    return rows


def key_snapshot() -> dict:
    snapshot = lib.env_snapshot()
    live_path = REPO / "scripts" / "run_live.sh"
    record = lib.run_command(["bash", str(live_path)], log_dir=Path("/tmp"),
                             name="d3-reg-livegate", timeout=30)
    gate = lib.run_command(
        [PYTHON, "-B", "-c",
         "import json;from autoteacher_m0.security.gates import LiveGate;"
         "d=LiveGate().inspect(live_requested=True);"
         "print(json.dumps({'status':d.status,'reasons':list(d.reasons)}))"],
        log_dir=Path("/tmp"), name="d3-reg-livegate-inspect", timeout=30,
        env={**os.environ, "PYTHONPATH": str(REPO / "src"),
             "PYTHONDONTWRITEBYTECODE": "1"})
    decision = None
    for line in reversed(gate["stdout"].splitlines()):
        try:
            decision = json.loads(line)
            break
        except json.JSONDecodeError:
            continue
    return {"env": snapshot, "run_live_exit": record["exit"],
            "livegate": decision}


def reg01(root: Path) -> dict:
    folder = root / "reg-01"
    folder.mkdir(parents=True, exist_ok=True)
    project = folder / "project"
    if project.exists():
        shutil.rmtree(project)
    project.mkdir()
    archive = subprocess.run(["git", "archive", "--format=tar", "HEAD"],
                             cwd=str(REPO), stdout=subprocess.PIPE, check=True)
    subprocess.run(["tar", "-x", "-C", str(project)], input=archive.stdout,
                   check=True)
    evidence = folder / "oci"
    evidence.mkdir(mode=0o777, exist_ok=True)
    os.chmod(evidence, 0o777)
    name = f"at-g3d-oci-d3reg-{lib.utc_compact()}"
    junit = evidence / "junit-oci-full.xml"
    argv = [
        "podman", "run", "--rm", "--name", name,
        "--network", "none", "--http-proxy=false", "--unsetenv-all",
        "--env", "PATH=/opt/python/bin:/usr/bin", "--env", "HOME=/work",
        "--env", "PYTHONPATH=/project/src:/deps",
        "--env", "PYTHONDONTWRITEBYTECODE=1", "--env", "TMPDIR=/tmp",
        "--read-only", "--read-only-tmpfs=false",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--user", "65534:65534",
        "--pids-limit", "192", "--memory", "1500m", "--memory-swap", "1500m",
        "--cpus", "1",
        "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=256m,mode=1777",
        "--tmpfs", "/work:rw,noexec,nosuid,nodev,size=64m,mode=1777",
        "--workdir", "/project", "--timeout", "900", "--systemd=false",
        "--mount", f"type=bind,src={project},dst=/project,rw=true",
        "--mount", f"type=bind,src={lib.DEPS},dst=/deps,ro=true",
        "--mount", f"type=bind,src={lib.DEPS},dst=/project/artifacts/foundation/deps,ro=true",
        "--mount", f"type=bind,src={evidence},dst=/evidence,rw=true",
        "--rootfs", str(lib.ROOTFS),
        "/opt/python/bin/python3.11", "-B", "-m", "pytest", "tests/", "-q",
        "-p", "no:cacheprovider", f"--junitxml=/evidence/{junit.name}",
    ]
    started = utc()
    record = lib.run_command(argv, log_dir=folder, name="oci-full", timeout=1200)
    counts = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    failed_cases = []
    if junit.is_file():
        tree = ET.parse(junit)
        root_element = tree.getroot()
        counts = {
            "tests": int(root_element.get("tests") or 0),
            "failures": int(root_element.get("failures") or 0),
            "errors": int(root_element.get("errors") or 0),
            "skipped": int(root_element.get("skipped") or 0),
        }
        for case in root_element.iter("testcase"):
            for kind in ("failure", "error"):
                node = case.find(kind)
                if node is not None:
                    failed_cases.append({
                        "classname": case.get("classname"),
                        "name": case.get("name"),
                        "kind": kind,
                        "message": (node.get("message") or "")[:800],
                    })
    document = {
        "schema": "m0.g3d.d3.reg01.v1", "argv": argv,
        "utc_start": started, "utc_end": utc(), "exit": record["exit"],
        "counts": counts, "failed_cases": failed_cases,
        "unexpected_failures": counts["failures"] + counts["errors"],
        "status": "PASS" if record["exit"] == 0 and counts["failures"] == 0
        and counts["errors"] == 0 else "FAIL",
        "stdout_path": record.get("stdout_path"),
        "stderr_path": record.get("stderr_path"),
        "junit": str(junit), "junit_sha256": lib.sha256_file(junit)
        if junit.is_file() else None,
    }
    write_json(folder / "result.json", document)
    return document


def reg02(root: Path) -> dict:
    folder = root / "reg-02"
    folder.mkdir(parents=True, exist_ok=True)
    guard = REPO / "plugins" / "runtime-budget-guard"
    skill = REPO / "plugins" / "skill-lookup"
    build = lib.run_command(
        ["npm", "run", "build"], log_dir=folder, name="skill-build", timeout=300,
        cwd=str(skill))
    guard_record = lib.run_command(
        ["node", "--test", "tests/precheck.test.mjs", "tests/guard-pr1.test.mjs"],
        log_dir=folder, name="guard-tests", timeout=300, cwd=str(guard),
        env={**os.environ, "RBG_TEST_PYTHON": PYTHON})
    skill_record = lib.run_command(
        ["node", "--test", "test/plugin.test.mjs"], log_dir=folder,
        name="skill-tests", timeout=300, cwd=str(skill))
    document = {
        "schema": "m0.g3d.d3.reg02.v1",
        "utc_start": guard_record["utc_start"], "utc_end": utc(),
        "node_version": subprocess.run(["node", "-v"], capture_output=True,
                                       text=True).stdout.strip(),
        "build": {"argv": ["npm", "run", "build"], "exit": build["exit"]},
        "guard": {"argv": ["node", "--test", "tests/precheck.test.mjs",
                           "tests/guard-pr1.test.mjs"],
                  "exit": guard_record["exit"],
                  "stdout_path": guard_record.get("stdout_path")},
        "skill": {"argv": ["node", "--test", "test/plugin.test.mjs"],
                  "exit": skill_record["exit"],
                  "stdout_path": skill_record.get("stdout_path")},
        "status": "PASS" if build["exit"] == 0 and guard_record["exit"] == 0
        and skill_record["exit"] == 0 else "FAIL",
        "classification": "host Node plugin/adapter regression; real DSH "
                          "adapter execution is separately Level B in C01/C10/C11",
    }
    write_json(folder / "result.json", document)
    return document


def reg03(root: Path, pre: dict, stage: Path) -> dict:
    folder = root / "reg-03"
    folder.mkdir(parents=True, exist_ok=True)
    names = ps_snapshot()
    residual = residual_processes()
    post = {
        "utc": utc(),
        "rootfs": {"sha256": lib.sha256_tree(lib.ROOTFS),
                   "expected": lib.ROOTFS_CANON},
        "deps": {"sha256": lib.sha256_tree(lib.DEPS),
                 "expected": lib.DEPS_CANON},
        "stage": {"sha256": lib.sha256_tree(stage)},
    }
    post["rootfs"]["ok"] = post["rootfs"]["sha256"] == post["rootfs"]["expected"]
    post["deps"]["ok"] = post["deps"]["sha256"] == post["deps"]["expected"]
    post["stage"]["ok"] = post["stage"]["sha256"] == pre["stage"]["sha256"]
    key = key_snapshot()
    document = {
        "schema": "m0.g3d.d3.reg03.v1", "utc": utc(),
        "pre": pre, "post": post,
        "containers": names,
        "no_at_g3d_containers": not any(n.startswith(lib.CONTAINER_PREFIX)
                                        for n in names),
        "residual_processes": residual,
        "rootfs_stable": post["rootfs"]["ok"],
        "deps_stable": post["deps"]["ok"],
        "stage_stable": post["stage"]["ok"],
        "zero_key": not key["env"]["key_like_names"],
        "run_live_exit": key["run_live_exit"],
        "livegate": key["livegate"],
        "status": "PASS" if (not any(n.startswith(lib.CONTAINER_PREFIX)
                                     for n in names)
                             and not residual and post["rootfs"]["ok"]
                             and post["deps"]["ok"] and post["stage"]["ok"]
                             and not key["env"]["key_like_names"]
                             and key["run_live_exit"] == 3
                             and (key["livegate"] or {}).get("status") == "BLOCKED")
        else "FAIL",
    }
    write_json(folder / "result.json", document)
    return document


def reg04(root: Path, case_dirs: list[Path]) -> dict:
    folder = root / "reg-04"
    folder.mkdir(parents=True, exist_ok=True)
    reconciled = []
    problems = []
    for evidence in case_dirs:
        final_path = evidence / "state" / "final.json"
        if not final_path.is_file():
            continue
        snapshot = json.loads(final_path.read_text(encoding="utf-8"))
        receipts = snapshot.get("receipt", {}).get("receipts") or []
        receipts_by_id = {row.get("receipt_id"): row for row in receipts}
        attempts = snapshot.get("attempts") or []
        claims = {row.get("call_id"): row for row in snapshot.get("claims") or []}
        reservations = {row.get("reservation_id"): row
                        for row in snapshot.get("reservations") or []}
        settled = 0
        for attempt in attempts:
            claim = claims.get(attempt.get("call_id"))
            receipt = receipts_by_id.get(attempt.get("receipt_id"))
            reservation = reservations.get(attempt.get("reservation_id"))
            pair = {
                "case": evidence.name,
                "attempt_id": attempt.get("attempt_id"),
                "state": attempt.get("state"),
                "prepared_digest": attempt.get("prepared_digest"),
                "payload_digest": attempt.get("payload_digest"),
                "claim_request_digest": None if claim is None else claim.get("request_digest"),
                "receipt_raw_sha256": None if receipt is None else receipt.get("raw_sha256"),
                "receipt_usage": None if receipt is None else receipt.get("usage"),
                "reservation_status": None if reservation is None else reservation.get("status"),
                "cost": None if reservation is None else reservation.get("cost"),
            }
            pair["prepared_matches_claim"] = (
                pair["claim_request_digest"] == pair["prepared_digest"])
            pair["payload_matches_receipt"] = (
                pair["receipt_raw_sha256"] == pair["payload_digest"])
            pair["digests_separate"] = (
                pair["prepared_digest"] != pair["payload_digest"])
            if attempt.get("state") == "SETTLED":
                settled += 1
                if not (pair["prepared_matches_claim"]
                        and pair["payload_matches_receipt"]
                        and pair["digests_separate"]
                        and pair["reservation_status"] == "OK"
                        and float(pair["cost"] or 0) > 0):
                    problems.append(pair)
            reconciled.append(pair)
        if evidence.name == "dev-stream":
            continue
    document = {
        "schema": "m0.g3d.d3.reg04.v1", "utc": utc(),
        "case_count": len(case_dirs),
        "pairs": reconciled,
        "problems": problems,
        "status": "PASS" if not problems else "FAIL",
        "note": "Host read-only ledger crosscheck; per-case Level A/B evidence "
                "remains authoritative.",
    }
    write_json(folder / "result.json", document)
    return document


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", required=True)
    parser.add_argument("--root", default=str(lib.G3D_ROOT / "d3"))
    parser.add_argument("--skip-reg01", action="store_true")
    parser.add_argument("--only-suites", action="store_true")
    args = parser.parse_args(argv)
    stage = str(Path(args.stage).resolve())
    os.environ["D3_STAGE"] = stage
    root = Path(args.root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    pre = {"utc": utc(), "rootfs": {"sha256": lib.sha256_tree(lib.ROOTFS)},
           "deps": {"sha256": lib.sha256_tree(lib.DEPS)},
           "stage": {"sha256": lib.sha256_tree(stage)}}
    write_json(root / "canonical-pre.json", pre)
    summaries = []
    for name, children in SUITES.items():
        if (root / name / "summary.json").is_file():
            continue
        summaries.append(suite(root, stage, name, children))
    if not args.only_suites:
        for case in SINGLES:
            evidence = root / case
            if evidence.exists():
                shutil.rmtree(evidence)
            summaries.append(run_case(root, stage, case, evidence))
    results = {"suites": summaries, "utc_end": utc()}
    write_json(root / "cases.json", results)
    statuses = {item.get("suite") or item.get("case"): item.get("status")
                for item in summaries}
    if not args.skip_reg01:
        reg_results = {"reg-01": reg01(root), "reg-02": reg02(root)}
    else:
        reg_results = {}
    reg_results["reg-03"] = reg03(root, pre, Path(stage))
    case_dirs = [root / case for case in SINGLES if (root / case).is_dir()]
    for suite_name, children in SUITES.items():
        for child in children:
            path = case_evidence(root, suite_name, child)
            if path.is_dir():
                case_dirs.append(path)
    reg_results["reg-04"] = reg04(root, case_dirs)
    final = {
        "schema": "m0.g3d.d3.final.v1", "utc": utc(),
        "stage": stage, "stage_sha256": lib.sha256_tree(stage),
        "cases": statuses,
        "reg": {key: value.get("status") for key, value in reg_results.items()},
        "checks": {key: value for key, value in reg_results.items()},
        "all_cases_pass": all(status == "PASS" for status in statuses.values()),
        "all_reg_pass": all(value.get("status") == "PASS"
                            for value in reg_results.values()),
    }
    final["status"] = "PASS" if (final["all_cases_pass"]
                                 and final["all_reg_pass"]) else "FAIL"
    write_json(root / "final.json", final)
    print(json.dumps(final, sort_keys=True))
    return 0 if final["status"] == "PASS" else 7


if __name__ == "__main__":
    raise SystemExit(main())
