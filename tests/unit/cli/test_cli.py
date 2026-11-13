import json

from autoteacher_m0.cli import main


def test_inspection_does_not_construct_sdk(capsys):
    assert main(["inspect-runtime"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["sdk_initialized"] is False
    assert output["live_status"] == "BLOCKED"


def test_live_denied_without_artifact_creation(tmp_path, capsys):
    target = tmp_path / "must-not-exist"
    assert main(["smoke", "--live", "--artifact-dir", str(target)]) == 3
    assert not target.exists()
    assert json.loads(capsys.readouterr().out)["error_code"] == "SECURITY_BLOCKED"


def test_mock_smoke_is_not_E1_pass(tmp_path, capsys):
    assert main(["smoke", "--mock", "--artifact-dir", str(tmp_path)]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["mock_smoke"] == "PASS"
    assert output["count"] == 3
    assert output["real_sdk_smoke"] == "NOT_EXECUTED"
    assert output["E1"] == "BLOCKED"
