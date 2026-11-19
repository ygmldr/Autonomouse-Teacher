"""Markdown/JSON report generation for M1 offline evaluation (stdlib only).

Reports are explicit about evidence levels:

* ``MEASURED``  – produced by a real local command in this worktree
* ``NOT_RUN``   – not executed (never rendered as PASS)
* ``UNVERIFIED``– depends on external systems / M0 runtime API
* ``PLAN``      – target coverage, not a result

Every report carries the offline-synthetic disclaimer and never claims real
teaching effectiveness.  Hidden fixture content is never included.
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[2]

MEASURED = "MEASURED"
NOT_RUN = "NOT_RUN"
UNVERIFIED = "UNVERIFIED"
PLAN = "PLAN"

DISCLAIMER = (
    "Offline synthetic evaluation only. These numbers describe a deterministic "
    "local simulator over synthetic fixtures; they are not real teaching "
    "effectiveness, not real learner outcomes and must not be extrapolated."
)


# ---------------------------------------------------------------------------
# Environment / provenance
# ---------------------------------------------------------------------------


def _git(root: Path, *args: str) -> str:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return "UNAVAILABLE"
    value = completed.stdout.strip()
    return value if completed.returncode == 0 and value else "UNAVAILABLE"


def environment_snapshot(root: Path | str = DEFAULT_REPO_ROOT) -> dict[str, Any]:
    """Local provenance: date, worktree SHA, python version, platform."""
    root = Path(root)
    return {
        "utc_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "utc_timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git_sha": _git(root, "rev-parse", "HEAD"),
        "git_branch": _git(root, "branch", "--show-current"),
        "python_version": platform.python_version(),
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "cwd": os.getcwd(),
    }


def pytest_version() -> str:
    try:
        import pytest  # noqa: PLC0415 - optional provenance detail
    except ImportError:  # pragma: no cover - pytest always present in dev env
        return "UNAVAILABLE"
    return getattr(pytest, "__version__", "UNAVAILABLE")


# ---------------------------------------------------------------------------
# Structured report
# ---------------------------------------------------------------------------


@dataclass
class Metric:
    """One measured/planned metric row."""

    name: str
    planned: str
    actual: str
    evidence: str = NOT_RUN
    source: str = ""
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "planned": self.planned,
            "actual": self.actual,
            "evidence": self.evidence,
            "source": self.source,
            "note": self.note,
        }


@dataclass
class RunReport:
    title: str
    command: str
    metrics: list[Metric] = field(default_factory=list)
    checks: list[dict[str, Any]] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    not_run: list[str] = field(default_factory=list)
    unverified: list[str] = field(default_factory=list)
    environment: dict[str, Any] = field(default_factory=dict)
    disclaimer: str = DISCLAIMER

    def add_metric(
        self,
        name: str,
        planned: str,
        actual: str,
        evidence: str = NOT_RUN,
        source: str = "",
        note: str = "",
    ) -> Metric:
        metric = Metric(name, planned, actual, evidence, source, note)
        self.metrics.append(metric)
        return metric

    def add_check(self, check_id: str, description: str, status: str, details: Any = None) -> None:
        self.checks.append(
            {
                "check_id": check_id,
                "description": description,
                "status": status,
                "details": details,
            }
        )

    def measured_count(self) -> int:
        return sum(1 for m in self.metrics if m.evidence == MEASURED)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "m1.eval_report.v0",
            "title": self.title,
            "command": self.command,
            "environment": self.environment,
            "metrics": [m.to_dict() for m in self.metrics],
            "checks": list(self.checks),
            "artifacts": list(self.artifacts),
            "notes": list(self.notes),
            "not_run": list(self.not_run),
            "unverified": list(self.unverified),
            "measured_metric_count": self.measured_count(),
            "disclaimer": self.disclaimer,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)


def render_markdown(report: RunReport) -> str:
    env = report.environment or {}
    lines: list[str] = []
    lines.append(f"# {report.title}")
    lines.append("")
    lines.append(f"> **Boundary:** {report.disclaimer}")
    lines.append("")
    lines.append("## Provenance")
    lines.append("")
    lines.append("| field | value |")
    lines.append("| --- | --- |")
    lines.append(f"| UTC date | `{env.get('utc_date', 'UNKNOWN')}` |")
    lines.append(f"| worktree SHA | `{env.get('git_sha', 'UNAVAILABLE')}` |")
    lines.append(f"| branch | `{env.get('git_branch', 'UNAVAILABLE')}` |")
    lines.append(f"| python | `{env.get('python_version', platform.python_version())}` |")
    lines.append(f"| pytest | `{pytest_version()}` |")
    lines.append(f"| command | `{report.command}` |")
    lines.append("")
    lines.append("## Metrics (planned vs measured)")
    lines.append("")
    lines.append("| metric | planned | actual | evidence | source |")
    lines.append("| --- | --- | --- | --- | --- |")
    for metric in report.metrics:
        actual = metric.actual if metric.evidence != NOT_RUN else "NOT_RUN"
        lines.append(
            f"| {metric.name} | {metric.planned} | {actual} | {metric.evidence} | "
            f"`{metric.source}` |"
        )
    if not report.metrics:
        lines.append("| (none) | - | NOT_RUN | NOT_RUN | - |")
    lines.append("")
    if report.checks:
        lines.append("## Checks")
        lines.append("")
        lines.append("| check | description | status |")
        lines.append("| --- | --- | --- |")
        for check in report.checks:
            lines.append(f"| {check['check_id']} | {check['description']} | {check['status']} |")
        lines.append("")
    if report.artifacts:
        lines.append("## Artifacts")
        lines.append("")
        for artifact in report.artifacts:
            lines.append(f"- `{artifact}`")
        lines.append("")
    if report.not_run:
        lines.append("## NOT_RUN")
        lines.append("")
        for item in report.not_run:
            lines.append(f"- {item}")
        lines.append("")
    if report.unverified:
        lines.append("## UNVERIFIED")
        lines.append("")
        for item in report.unverified:
            lines.append(f"- {item}")
        lines.append("")
    if report.notes:
        lines.append("## Notes")
        lines.append("")
        for note in report.notes:
            lines.append(f"- {note}")
        lines.append("")
    return "\n".join(lines)


def build_report(
    title: str,
    command: str,
    *,
    root: Path | str = DEFAULT_REPO_ROOT,
    metrics: Iterable[Metric] | None = None,
    checks: Iterable[dict[str, Any]] | None = None,
    artifacts: Iterable[str] = (),
    notes: Iterable[str] = (),
    not_run: Iterable[str] = (),
    unverified: Iterable[str] = (),
) -> RunReport:
    report = RunReport(
        title=title,
        command=command,
        metrics=list(metrics or []),
        checks=list(checks or []),
        artifacts=list(artifacts),
        notes=list(notes),
        not_run=list(not_run),
        unverified=list(unverified),
        environment=environment_snapshot(root),
    )
    return report


def write_report(
    report: RunReport,
    *,
    json_path: Path | str | None = None,
    markdown_path: Path | str | None = None,
    root: Path | str | None = None,
) -> tuple[Path | None, Path | None]:
    """Write JSON and/or markdown report; returns the written paths."""
    if root is not None:
        base = Path(root)
        json_path = base / json_path if json_path else None
        markdown_path = base / markdown_path if markdown_path else None
    written_json: Path | None = None
    written_md: Path | None = None
    if json_path is not None:
        path = Path(json_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(report.to_json() + "\n", encoding="utf-8")
        written_json = path
    if markdown_path is not None:
        path = Path(markdown_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_markdown(report) + "\n", encoding="utf-8")
        written_md = path
    return written_json, written_md


def summarize_metrics(report: RunReport) -> str:
    """Short human-readable summary used by the demo."""
    measured = report.measured_count()
    total = len(report.metrics)
    return (
        f"measured={measured}/{total} NOT_RUN={len(report.not_run)} "
        f"UNVERIFIED={len(report.unverified)} checks={len(report.checks)}"
    )
