"""Small offline entry points for foundation's CLI. No live flag can open Live."""
from pathlib import Path
from .paired import run_mock_pairs
from .report import render_existing, write_report


def run_paired(*, artifact_dir: Path) -> Path:
    """Run 20x2 public Mock executions and return their artifact directory."""
    return write_report(run_mock_pairs(), artifact_dir)


def render_report(*, artifact_dir: Path, experiment: str = "latest") -> Path:
    """Return the generated comparison.md path, never re-execute a candidate."""
    return render_existing(artifact_dir, experiment)
