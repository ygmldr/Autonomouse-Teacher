"""Launcher-level structural tests: deny before Broker, required mode, L2 cases."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


from admission_support import (
    L2_RUNNER, admission_document, begin, launcher_config, retime_authorization,
    run_launcher, write_admission, write_controller_config, write_launcher_config,
)
from autoteacher_m0.bridge import controller
from g4a_support import ROTATED_SEED


def test_launcher_dry_run_allows_and_records(trusted, tmp_path: Path) -> None:
    retime_authorization(trusted)
    config = launcher_config(trusted, tmp_path)
    path = write_launcher_config(tmp_path, config)
    completed = run_launcher(path)
    assert completed.returncode == 0, completed.stderr
    document = json.loads(completed.stdout)
    assert document["status"] == "ALLOW"
    assert document["consumed"] == "YES"
    assert Path(config["journal_path"]).is_file()
    use_log = Path(config["use_log_dir"])
    assert len(list(use_log.glob("*.json"))) == 1


def test_denied_launcher_never_creates_broker_or_attempt_db(
        trusted, tmp_path: Path) -> None:
    from g4a_support import KEY_ID
    retime_authorization(trusted)
    bad = trusted.sign(trusted.payload, seed=ROTATED_SEED, key_id=KEY_ID)
    trusted.authorization.write_text(json.dumps(bad))
    config = launcher_config(trusted, tmp_path)
    controller_path = write_controller_config(tmp_path, required=True)
    config["controller_config_path"] = str(controller_path)
    path = write_launcher_config(tmp_path, config)
    completed = run_launcher(path)
    assert completed.returncode == 20, completed.stderr
    document = json.loads(completed.stdout)
    assert document["status"] == "DENY"
    assert document["consumed"] == "NO"
    controller_config = json.loads(controller_path.read_text(encoding="utf-8"))
    assert not Path(controller_config["socket_path"]).exists()
    assert not Path(controller_config["attempt_db"]).exists()
    assert not Path(controller_config["receipt_dir"]).exists()
    assert list(Path(config["use_log_dir"]).glob("*.json")) == []


def test_launcher_config_validation_rejects_unknown_field(trusted, tmp_path: Path) -> None:
    config = launcher_config(trusted, tmp_path)
    config["unknown_field"] = True
    path = write_launcher_config(tmp_path, config)
    completed = run_launcher(path)
    assert completed.returncode == 21
    document = json.loads(completed.stdout)
    assert document["status"] == "CONFIG_INVALID"


def test_required_mode_without_context_refuses_before_start(tmp_path: Path) -> None:
    config_path = write_controller_config(tmp_path, required=True)
    code = controller.main(["--config", str(config_path)])
    assert code == controller.EXIT_RUN_ADMISSION_REQUIRED
    config = json.loads(config_path.read_text(encoding="utf-8"))
    assert not Path(config["socket_path"]).exists()
    assert not Path(config["attempt_db"]).exists()


def test_required_mode_with_inactive_context_refuses_before_start(
        trusted, tmp_path: Path) -> None:
    context = begin(trusted, tmp_path)
    context.close("inactive-for-test")
    config_path = write_controller_config(tmp_path, required=True)
    code = controller.main(["--config", str(config_path)], run_admission=context)
    assert code == controller.EXIT_RUN_ADMISSION_INACTIVE
    config = json.loads(config_path.read_text(encoding="utf-8"))
    assert not Path(config["socket_path"]).exists()
    assert not Path(config["attempt_db"]).exists()


def test_required_mode_rejects_foreign_object(tmp_path: Path) -> None:
    config_path = write_controller_config(tmp_path, required=True)
    code = controller.main(["--config", str(config_path)], run_admission=object())
    assert code == controller.EXIT_RUN_ADMISSION_INACTIVE


def test_l2_case_runner_host_synthetic(trusted, tmp_path: Path) -> None:
    retime_authorization(trusted)
    base = launcher_config(trusted, tmp_path, required=True)
    base_path = write_launcher_config(tmp_path, base, name="base-launcher.json")
    new_admission = tmp_path / "admission-run2.json"
    new_admission.write_text(json.dumps(admission_document(
        run_id="run-second", nonce="c" * 32, admission_id="d" * 32)))
    runner_config = {
        "launcher_config": str(base_path),
        "output_dir": str(tmp_path / "evidence"),
        "new_run": {"admission_path": str(new_admission)},
    }
    runner_path = tmp_path / "runner.json"
    runner_path.write_text(json.dumps(runner_config))
    completed = subprocess.run(
        [sys.executable, str(L2_RUNNER), "--config", str(runner_path)],
        capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr + completed.stdout
    evidence = (tmp_path / "evidence" / "a2-admission-cases.jsonl")
    rows = [json.loads(line) for line in
            evidence.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert [row["case_id"] for row in rows] == ["A2-01", "A2-02", "A2-03"]
    assert all(row["matched"] is True for row in rows), rows
    assert rows[0]["document"]["code"] == "RUN_ADMISSION_ALLOW"
    assert rows[1]["document"]["code"] == "RUN_ADMISSION_ALREADY_CONSUMED"
    assert rows[2]["document"]["code"] == "RUN_ADMISSION_EPOCH_MISMATCH"


def test_l2_case_runner_requires_fresh_a2_01_state(trusted, tmp_path: Path) -> None:
    retime_authorization(trusted)
    base = launcher_config(trusted, tmp_path, required=True)
    base_path = write_launcher_config(tmp_path, base, name="base-launcher.json")
    Path(base["use_log_dir"], "stale.json").write_text("{}", encoding="utf-8")
    runner_config = {
        "launcher_config": str(base_path),
        "output_dir": str(tmp_path / "evidence"),
        "new_run": {
            "admission_path": str(write_admission(tmp_path, nonce="c" * 32,
                                                  run_id="run-second")),
        },
    }
    runner_path = tmp_path / "runner.json"
    runner_path.write_text(json.dumps(runner_config))
    completed = subprocess.run(
        [sys.executable, str(L2_RUNNER), "--config", str(runner_path)],
        capture_output=True, text=True)
    assert completed.returncode != 0
    assert "fresh" in completed.stderr or "empty" in completed.stderr
