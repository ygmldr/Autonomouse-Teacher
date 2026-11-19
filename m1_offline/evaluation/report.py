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

import hashlib
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

#: Worktree baseline commit (work/m1-offline-design was created from this SHA;
#: it is NOT necessarily the current HEAD -- see ``environment_snapshot``).
BASE_COMMIT_SHA = "3e7afee077845a071cd364e93ab209cac20b2d5f"

#: Files covered by the reproducible dependency fingerprint.  The frozen
#: b-core/b-cf/b-interview modules + fixtures are what evaluation numbers depend
#: on; evaluation/ and demo.py are covered too so a changed simulator is visible.
FINGERPRINT_GLOBS: tuple[str, ...] = ("m1_offline/**/*.py", "fixtures/m1/**/*")

#: Note recorded next to the implementation commit in reports/artifacts.
IMPLEMENTATION_COMMIT_NOTE = (
    "frozen reviewed implementation commit; post-review report/doc fixes were "
    "generated on top of it -- the final commit SHA is recorded in "
    "docs/parallel/STATUS.md (Lead-owned), never implied to be this base SHA"
)

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


def _git_is_dirty(root: Path) -> bool | None:
    """True when the worktree has uncommitted changes (None when git is unavailable)."""

    try:
        completed = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return bool(completed.stdout.strip())


def dependency_manifest(root: Path | str = DEFAULT_REPO_ROOT) -> list[str]:
    """Reproducible dependency manifest lines, sorted by relative POSIX path.

    Each line is ``"<sha256-of-file-bytes>  <relative/POSIX/path>"`` (two spaces
    between digest and path, exactly like ``sha256sum`` output).  Only files
    matched by :data:`FINGERPRINT_GLOBS` are included; bytecode caches are
    excluded.  The function is deterministic and filesystem-relative.
    """

    root = Path(root)
    covered: dict[str, str] = {}
    for pattern in FINGERPRINT_GLOBS:
        for path in root.glob(pattern):
            if not path.is_file():
                continue
            parts = set(path.relative_to(root).parts)
            if "__pycache__" in parts or path.suffix == ".pyc":
                continue
            relative = path.relative_to(root).as_posix()
            covered[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return [f"{covered[relative]}  {relative}" for relative in sorted(covered)]


def dependency_fingerprint(root: Path | str = DEFAULT_REPO_ROOT) -> str:
    """SHA-256 over the reproducible dependency manifest.

    Algorithm (documented for reviewers; one-line command in
    ``docs/m1/EXPERIMENT_BASELINE.md``):

    1. collect files from :data:`FINGERPRINT_GLOBS` (``m1_offline/**/*.py``,
       ``fixtures/m1/**/*``), excluding ``__pycache__``/``*.pyc``;
    2. for each file compute ``sha256(file_bytes)``;
    3. sort lines ``"<file_sha256>  <relative/POSIX/path>"`` by path;
    4. fingerprint = ``sha256("\n".join(lines) + "\n")`` (UTF-8).

    The old ad-hoc digest ``b4bb2931...`` was produced by an undocumented
    script and is **superseded** by this algorithm.
    """

    manifest = dependency_manifest(root)
    payload = "\n".join(manifest) + "\n"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def environment_snapshot(root: Path | str = DEFAULT_REPO_ROOT) -> dict[str, Any]:
    """Local provenance: dates, base/reviewed commits, dirty state, fingerprint.

    ``base_sha`` is always the worktree baseline commit; ``implementation_commit``
    is the commit the measured artifact was generated from (reports never imply
    that the base SHA is HEAD).
    """

    root = Path(root)
    return {
        "utc_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "utc_timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "base_sha": BASE_COMMIT_SHA,
        "implementation_commit": _git(root, "rev-parse", "HEAD"),
        "implementation_commit_note": IMPLEMENTATION_COMMIT_NOTE,
        "working_tree_dirty": _git_is_dirty(root),
        "git_branch": _git(root, "branch", "--show-current"),
        "dependency_fingerprint": dependency_fingerprint(root),
        "dependency_fingerprint_algorithm": (
            "sorted '<sha256(file bytes)>  <relative/POSIX path>' lines over "
            "m1_offline/**/*.py + fixtures/m1/**/* (no __pycache__/.pyc), "
            "joined with '\n' + trailing '\n', then sha256 of UTF-8 bytes"
        ),
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
    sections: dict[str, Any] = field(default_factory=dict)
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

    def add_section(self, name: str, payload: Any) -> None:
        """Attach a structured top-level section (e.g. full comparison details)."""

        if not isinstance(name, str) or not name.strip():
            raise ValueError("section name must be a non-empty str")
        if name in {"schema", "title", "command", "environment", "metrics", "checks"}:
            raise ValueError(f"section name collides with a reserved report key: {name}")
        self.sections[name] = payload

    def measured_count(self) -> int:
        return sum(1 for m in self.metrics if m.evidence == MEASURED)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
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
        for name, payload in self.sections.items():
            data[name] = payload
        return data

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
    lines.append(f"| base commit (worktree baseline) | `{env.get('base_sha', BASE_COMMIT_SHA)}` |")
    lines.append(
        f"| implementation commit (reviewed, artifact generated on top) | "
        f"`{env.get('implementation_commit', 'UNAVAILABLE')}` |"
    )
    lines.append(
        f"| working tree dirty at generation | `{env.get('working_tree_dirty', 'UNKNOWN')}` |"
    )
    lines.append(f"| branch | `{env.get('git_branch', 'UNAVAILABLE')}` |")
    lines.append(
        f"| dependency fingerprint | `{env.get('dependency_fingerprint', 'UNAVAILABLE')}` |"
    )
    lines.append(f"| python | `{env.get('python_version', platform.python_version())}` |")
    lines.append(f"| pytest | `{pytest_version()}` |")
    lines.append(f"| command | `{report.command}` |")
    if env.get("implementation_commit_note"):
        lines.append("")
        lines.append(f"> Note: {env['implementation_commit_note']}")
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
    if report.sections:
        lines.append("## Structured sections")
        lines.append("")
        for name, payload in report.sections.items():
            lines.append(f"### {name}")
            lines.append("")
            lines.append("```json")
            lines.append(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
            lines.append("```")
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
