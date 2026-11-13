import json
import sqlite3

import pytest

from autoteacher_m0.experiments.cli import render_report, run_paired
from autoteacher_m0.experiments.fixtures import load_cases
from autoteacher_m0.experiments.paired import run_mock_pairs
from autoteacher_m0.experiments.report import write_report


def test_fixture_rejects_truncated_or_relabelled_public_data(tmp_path):
    source = tmp_path / "cases.jsonl"
    source.write_text("{}\n", encoding="utf-8")
    with pytest.raises((ValueError, KeyError, TypeError)):
        load_cases(source)


def test_grader_fault_does_not_become_zero_pair_delta():
    def broken(*args):
        raise ValueError("deliberate")
    experiment = run_mock_pairs(grader=broken)
    assert len(experiment["runs"]) == 40
    assert all(item["evaluation"]["status"] == "EVAL_ERROR" for item in experiment["runs"])
    assert all(pair["delta_v1_minus_v0"] is None for pair in experiment["pairs"])
    assert all(pair["comparison_status"] == "INCOMPLETE" for pair in experiment["pairs"])


def test_faulty_runtime_still_accounts_failed_calls_and_continues():
    class Broken:
        def run(self, request):
            raise TimeoutError("do not log arbitrary payload")
    document = run_mock_pairs(runtime_factory=Broken)
    assert all(item["record"]["status"] == "ERROR" for item in document["runs"])
    assert all(item["accounting"]["estimated"] for item in document["runs"])
    assert document["budget"]["requests"] == 40
    assert document["budget"]["pending"] == 0


def test_sanitize_before_all_three_formats(tmp_path):
    document = run_mock_pairs(experiment_id="redaction")
    sentinel = "FAKE_E4_SENTINEL_001"
    document["runs"][0]["record"]["text"] += sentinel
    document["runs"][0]["evaluation"]["reasons"] = [sentinel]
    document["runs"][0]["record"]["metadata"]["api_key"] = "sk-fake-key"
    output = write_report(document, tmp_path, sentinels=(sentinel,))
    for name in ("experiment.json", "comparison.md"):
        text = (output / name).read_text()
        assert sentinel not in text and "sk-fake-key" not in text
    with sqlite3.connect(output / "experiment.sqlite3") as database:
        rows = database.execute("SELECT payload FROM runs").fetchall()
    assert sentinel not in str(rows) and "sk-fake-key" not in str(rows)


def test_cli_entrypoints_write_and_render_without_rerun(tmp_path):
    output = run_paired(artifact_dir=tmp_path)
    document = json.loads((output / "experiment.json").read_text())
    assert len(document["runs"]) == 40
    report = render_report(artifact_dir=tmp_path)
    assert report == output / "comparison.md"
    assert "Public Mock" in report.read_text()
    with sqlite3.connect(output / "experiment.sqlite3") as database:
        assert database.execute("SELECT COUNT(*) FROM runs").fetchone() == (40,)
        assert database.execute("SELECT COUNT(DISTINCT session_id) FROM runs").fetchone() == (40,)
        assert database.execute("SELECT COUNT(*) FROM pairs").fetchone() == (20,)
    with pytest.raises(FileExistsError):
        write_report(document, tmp_path)


def test_report_identifier_traversal_rejected(tmp_path):
    with pytest.raises(ValueError):
        render_report(artifact_dir=tmp_path, experiment="../outside")
