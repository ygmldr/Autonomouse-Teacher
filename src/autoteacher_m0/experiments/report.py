"""Sanitize BEFORE persistence, consistently across JSON, SQLite and Markdown."""
import json
import sqlite3
from pathlib import Path
from autoteacher_m0.storage.artifacts import safe_id, sanitize


def comparison_markdown(document: dict) -> str:
    lines = ["# Public Mock paired comparison", "",
             "**OFFLINE MOCK ONLY. No API/model calls or real learning-gain evidence.**",
             "12 development + 8 public simulated holdout cases; neither split is private.",
             "True private evaluation remains outside the repository and was NOT RUN.", "",
             "Experiment: " + document["experiment_id"],
             "Route: mock; model label: deepseek-flash (not contacted).",
             "Live: BLOCKED pending human security approval and separate evidence.", "",
             "| Case | Public split | v0 | v1 | Delta | Status |",
             "|---|---|---:|---:|---:|---|"]
    for pair in document["pairs"]:
        def cell(value: object) -> str:
            return "—" if value is None else str(value)
        lines.append("| " + " | ".join(cell(pair[key]) for key in (
            "case_id", "split", "teacher_v0_score", "teacher_v1_score",
            "delta_v1_minus_v0", "comparison_status")) + " |")
    lines += ["", "## Separate public split summaries"]
    for split in ("development", "simulated_holdout"):
        subset = [pair for pair in document["pairs"] if pair["split"] == split]
        complete = [pair for pair in subset if pair["delta_v1_minus_v0"] is not None]
        mean = sum(pair["delta_v1_minus_v0"] for pair in complete) / len(complete) if complete else None
        lines.append(f"- {split}: {len(complete)}/{len(subset)} comparable, mean paired delta: {mean}.")
    counts: dict[str, int] = {}
    for entry in document["runs"]:
        status = entry["evaluation"]["status"]
        counts[status] = counts.get(status, 0) + 1
    lines += ["", "## Evaluation and costs", "- Status counts: " + json.dumps(counts, sort_keys=True),
              "- Billable API cost: $0 (Mock only; not a free live API claim).",
              "- Synthetic accounting estimate: $" + document["budget"]["spent_usd"]
              + "; version " + document["price_snapshot"]["version"] + ".",
              "- Scores are fixed rule-compliance plumbing checks; not teaching-effect measurements.",
              "- Errors and review cases have score=null and are excluded, never treated as zero.", "",
              "## Run-level failures and trace references"]
    for entry in document["runs"]:
        record, result = entry["record"], entry["evaluation"]
        lines.append(f"- {record['case_id']}/{record['candidate_id']}: {result['status']}; "
                     f"run={record['run_id']}; session={record['session_id']}; "
                     f"cost={entry['accounting']['cost_usd']}; "
                     f"reasons={','.join(result['reasons']) or 'none'}.")
    lines += ["", "## Limits and remaining evidence"] + ["- " + item for item in document["limitations"]]
    return "\n".join(lines) + "\n"


def write_report(document: dict, artifact_dir: Path, *, sentinels: tuple[str, ...] = ()) -> Path:
    clean = sanitize(document, sentinels=sentinels)
    target = Path(artifact_dir) / safe_id(clean["experiment_id"])
    target.mkdir(parents=True, exist_ok=False)
    (target / "experiment.json").write_text(json.dumps(clean, ensure_ascii=False, indent=2,
                                                       allow_nan=False) + "\n", encoding="utf-8")
    (target / "comparison.md").write_text(comparison_markdown(clean), encoding="utf-8")
    with sqlite3.connect(target / "experiment.sqlite3") as database:
        database.executescript("""
            CREATE TABLE experiments (experiment_id TEXT PRIMARY KEY, mode TEXT NOT NULL, payload TEXT NOT NULL);
            CREATE TABLE runs (run_id TEXT PRIMARY KEY, experiment_id TEXT NOT NULL, case_id TEXT NOT NULL,
              candidate_id TEXT NOT NULL, session_id TEXT UNIQUE NOT NULL, evaluation_status TEXT NOT NULL,
              score REAL, payload TEXT NOT NULL);
            CREATE TABLE pairs (case_id TEXT PRIMARY KEY, split TEXT NOT NULL, delta REAL, payload TEXT NOT NULL);
        """)
        database.execute("INSERT INTO experiments VALUES (?,?,?)", (
            clean["experiment_id"], clean["mode"], json.dumps(clean, allow_nan=False)))
        for entry in clean["runs"]:
            record, result = entry["record"], entry["evaluation"]
            database.execute("INSERT INTO runs VALUES (?,?,?,?,?,?,?,?)", (
                record["run_id"], clean["experiment_id"], record["case_id"], record["candidate_id"],
                record["session_id"], result["status"], result["score"], json.dumps(entry, allow_nan=False)))
        for pair in clean["pairs"]:
            database.execute("INSERT INTO pairs VALUES (?,?,?,?)", (
                pair["case_id"], pair["split"], pair["delta_v1_minus_v0"], json.dumps(pair, allow_nan=False)))
    return target


def render_existing(artifact_dir: Path, experiment: str = "latest") -> Path:
    root = Path(artifact_dir)
    if experiment == "latest":
        choices = [item for item in root.glob("*/experiment.json") if item.is_file()]
        if not choices:
            raise FileNotFoundError("no paired experiment artifacts")
        source = max(choices, key=lambda item: item.stat().st_mtime)
    else:
        source = root / safe_id(experiment) / "experiment.json"
    clean = sanitize(json.loads(source.read_text(encoding="utf-8")))
    destination = source.parent / "comparison.md"
    destination.write_text(comparison_markdown(clean), encoding="utf-8")
    return destination
