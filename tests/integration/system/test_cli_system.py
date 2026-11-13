"""Cross-module offline controller integration; run only in external isolation."""
import json
from pathlib import Path
import sqlite3
import tomllib

from autoteacher_m0.cli import main


def test_cli_end_to_end_public_mock_and_saved_report(tmp_path, capsys):
    assert main(["inspect-runtime"]) == 0
    inspection = json.loads(capsys.readouterr().out)
    assert inspection["sdk_initialized"] is False
    assert inspection["gate_reasons"]
    assert inspection["plugin"]["model_originated_tool_calls"] == "BLOCKED"

    assert main(["smoke", "--mock", "--artifact-dir", str(tmp_path / "smoke")]) == 0
    smoke = json.loads(capsys.readouterr().out)
    assert smoke["synthetic_accounting"]["requests"] == 3
    assert smoke["billable_cost_usd"] == "0" and smoke["E1"] == "BLOCKED"

    root = tmp_path / "paired"
    assert main(["paired", "--mock", "--artifact-dir", str(root)]) == 0
    paired = json.loads(capsys.readouterr().out)
    directory = Path(paired["artifact_dir"])
    document = json.loads((directory / "experiment.json").read_text())
    assert len(document["pairs"]) == 20 and len(document["runs"]) == 40
    assert document["budget"]["requests"] == 40
    assert document["price_snapshot"]["mock"] is True
    assert len({item["record"]["session_id"] for item in document["runs"]}) == 40
    with sqlite3.connect(directory / "experiment.sqlite3") as database:
        assert database.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 40
        assert database.execute("SELECT COUNT(*) FROM pairs").fetchone()[0] == 20
    for selector in ("latest", directory.name):
        assert main(["report", "--artifact-dir", str(root), "--experiment", selector]) == 0
        report = json.loads(capsys.readouterr().out)
        text = Path(report["report"]).read_text()
        assert "OFFLINE MOCK ONLY" in text
        assert "Live: BLOCKED" in text


def test_live_gate_blocks_all_cli_arms_before_output_creation(tmp_path, capsys):
    for command in ("smoke", "paired"):
        destination = tmp_path / command
        assert main([command, "--live", "--budget-usd", "10",
                     "--artifact-dir", str(destination)]) == 3
        message = json.loads(capsys.readouterr().out)
        assert message["error_code"] == "SECURITY_BLOCKED"
        assert "EXTERNAL_HUMAN_AUTHORIZATION_BOUNDARY_NOT_DEPLOYED" in message["reason"]
        assert not destination.exists()


def test_report_errors_are_explicit_not_fake_success(tmp_path, capsys):
    for selector in ("latest", "../escape"):
        assert main(["report", "--artifact-dir", str(tmp_path), "--experiment", selector]) == 1
        assert json.loads(capsys.readouterr().out)["error_code"] == "ARTIFACT_ERROR"


def test_only_public_fixture_is_explicitly_wheel_packaged():
    root = Path(__file__).resolve().parents[3]
    project = tomllib.loads((root / "pyproject.toml").read_text())
    include = project["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]
    assert include == {"fixtures/teacher_cases.jsonl": "autoteacher_m0/data/teacher_cases.jsonl"}
    assert not any("private" in source.lower() for source in include)
