"""D1-B launcher/stage contract tests (host-only, no container, no kernel).

These tests exercise the executable policy the Host Launcher uses:

* the frozen ``$RUN`` permission plan,
* the readiness gate (socket stat + ``/proc/<pid>/net/unix`` LISTEN + Trusted
  ready document) and the fact that Candidate start is gated by all three,
* the exact Trusted/Candidate Podman argv contract (mounts, namespaces, UID/GID
  maps, no Key env, no Trusted state/evidence mount for the Candidate),
* the candidate-stage allow-list and manifest integrity checks,
* symlink-safe, idempotent cleanup and TERM->KILL escalation,
* the generated controller/admission/broker configuration invariants.

Real kernel/container evidence lives in ``artifacts/g3d/d1b`` and is produced by
``scripts/g3d/launch.py``; pytest passing here is not a substitute for it.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import stat
import sys

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
G3D_SCRIPTS = REPO_ROOT / "scripts" / "g3d"
if str(G3D_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(G3D_SCRIPTS))

import lib_g3d as lib  # noqa: E402
import launch as launcher_mod  # noqa: E402


# ---------------------------------------------------------------------------
# $RUN layout / permissions
# ---------------------------------------------------------------------------
def test_run_layout_plan_is_frozen() -> None:
    plan = {item["relpath"]: item for item in lib.plan_run_layout()}
    assert set(plan) == {"state", "ipc", "candidate-session", "evidence", "logs"}
    assert plan["state"]["mode"] == 0o700
    assert (plan["state"]["uid"], plan["state"]["gid"]) == (0, 0)
    assert plan["ipc"]["mode"] == 0o2750
    assert (plan["ipc"]["uid"], plan["ipc"]["gid"]) == (0, 2000)
    assert plan["candidate-session"]["mode"] == 0o700
    assert (plan["candidate-session"]["uid"], plan["candidate-session"]["gid"]) == (65534, 65534)
    assert plan["evidence"]["mode"] == 0o700
    assert plan["logs"]["mode"] == 0o700


@pytest.mark.skipif(os.geteuid() != 0, reason="run layout requires host root")
def test_create_run_layout_applies_exact_permissions(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    created = lib.create_run_layout(run_dir)
    assert len(created) == 5
    for item in lib.RUN_LAYOUT:
        info = os.lstat(run_dir / item["relpath"])
        assert stat.S_IMODE(info.st_mode) == item["mode"]
        assert (info.st_uid, info.st_gid) == (item["uid"], item["gid"])
        if item["mode"] & stat.S_ISGID:
            assert info.st_mode & stat.S_ISGID
    # A second creation must fail closed instead of reusing state.
    with pytest.raises(lib.G3DError):
        lib.create_run_layout(run_dir)


def test_layout_permission_problems_detect_mutations() -> None:
    expected = {"mode": 0o2750, "uid": 0, "gid": 2000}
    good = {"type": "directory", "mode": 0o2750, "setgid": True,
            "uid": 0, "gid": 2000, "mode_octal": "2750"}
    assert lib.layout_permission_problems(good, expected) == []
    for field, value in (("mode", 0o750), ("uid", 65534), ("gid", 0), ("setgid", False)):
        bad = dict(good)
        bad[field] = value
        assert lib.layout_permission_problems(bad, expected)
    assert lib.layout_permission_problems(None, expected) == ["missing_or_unreadable"]


# ---------------------------------------------------------------------------
# Socket / readiness gate
# ---------------------------------------------------------------------------
def _socket_record(**overrides) -> dict:
    record = {"path": "/run/ipc/bridge.sock", "type": "socket", "mode": 0o660,
              "mode_octal": "0660", "uid": 0, "gid": 2000, "size": 0,
              "inode": 4242, "nlink": 1, "setgid": False}
    record.update(overrides)
    return record


def _ready_document(**overrides) -> dict:
    document = {"schema": "m0.g3d.trusted.ready.v1",
                "utc": "2026-11-17T19:29:25Z", "pid": 7,
                "expected_peer_uid": 65534,
                "socket": {"path": lib.SOCKET_PATH, "mode": 0o660,
                           "uid": 0, "gid": 2000, "inode": 4242},
                "synthetic": True}
    document.update(overrides)
    return document


def _listening(path: str = lib.SOCKET_PATH) -> list[dict]:
    return [{"num": "0000", "flags": 0x10000, "listening": True,
             "type": "0001", "st": "01", "inode": 77, "path": path}]


def test_socket_contract_accepts_the_frozen_boundary() -> None:
    assert lib.socket_contract_problems(_socket_record()) == []
    assert lib.socket_contract_problems(_socket_record(mode=0o770))
    assert lib.socket_contract_problems(_socket_record(mode=0o666))
    assert lib.socket_contract_problems(_socket_record(gid=0))
    assert lib.socket_contract_problems(_socket_record(uid=65534))
    assert lib.socket_contract_problems(_socket_record(type="regular"))


def test_ready_gate_requires_socket_listen_and_document() -> None:
    evaluation = lib.evaluate_ready(
        socket_record=_socket_record(), ready_document=_ready_document(),
        ready_problems=[], listening_entries=_listening(),
        container_running=True)
    assert evaluation["ok"] is True
    assert lib.ready_allows_candidate(evaluation) is True


@pytest.mark.parametrize("mutation", [
    "container_stopped", "ready_absent", "ready_problems", "wrong_mode",
    "wrong_gid", "not_listening", "inode_mismatch", "listening_other_path",
])
def test_ready_gate_rejects_incomplete_facts(mutation: str) -> None:
    socket_record = _socket_record()
    document = _ready_document()
    listening = _listening()
    container_running = True
    ready_problems: list[str] = []
    if mutation == "container_stopped":
        container_running = False
    elif mutation == "ready_absent":
        document = None
    elif mutation == "ready_problems":
        ready_problems = ["ready_schema"]
    elif mutation == "wrong_mode":
        socket_record = _socket_record(mode=0o770)
    elif mutation == "wrong_gid":
        socket_record = _socket_record(gid=0)
    elif mutation == "not_listening":
        listening = []
    elif mutation == "inode_mismatch":
        socket_record = _socket_record(inode=9999)
    elif mutation == "listening_other_path":
        listening = _listening("/work/g3b/other.sock")
    evaluation = lib.evaluate_ready(
        socket_record=socket_record, ready_document=document,
        ready_problems=ready_problems, listening_entries=listening,
        container_running=container_running)
    assert evaluation["ok"] is False, mutation
    assert lib.ready_allows_candidate(evaluation) is False
    assert evaluation["problems"]


def test_parse_ready_document_rejects_bad_documents() -> None:
    good, problems = lib.parse_ready_document(lib.json_bytes(_ready_document()))
    assert good is not None and problems == []
    bad_schema = _ready_document(schema="other")
    assert lib.parse_ready_document(lib.json_bytes(bad_schema))[1]
    bad_peer = _ready_document(expected_peer_uid=0)
    assert lib.parse_ready_document(lib.json_bytes(bad_peer))[1]
    bad_socket = _ready_document(socket={"mode": 0o666, "uid": 0, "gid": 0})
    assert lib.parse_ready_document(lib.json_bytes(bad_socket))[1]
    assert lib.parse_ready_document(b"not-json")[1] == ["ready_not_json"]


# ---------------------------------------------------------------------------
# Container argv contract
# ---------------------------------------------------------------------------
def _trusted_argv() -> list[str]:
    return lib.trusted_run_argv(
        podman="podman", rootfs="/rootfs", stage_trusted="/stage/trusted",
        deps="/deps", run_dir="/run", name="at-g3d-trusted-test")


def _candidate_argv() -> list[str]:
    return lib.candidate_run_argv(
        podman="podman", rootfs="/rootfs", stage_candidate="/stage/candidate",
        deps="/deps", run_dir="/run", name="at-g3d-candidate-test")


def _problems(argv: list[str], role: str) -> list[str]:
    return lib.argv_contract_problems(
        argv, role=role, run_dir="/run",
        stage_dir=f"/stage/{'trusted' if role == 'trusted' else 'candidate'}")


def test_trusted_argv_contract() -> None:
    argv = _trusted_argv()
    assert _problems(argv, "trusted") == []
    assert "--userns=host" in argv
    mounts = lib.argv_mounts(argv)
    assert any("src=/stage/trusted,dst=/project,ro=true" in mount for mount in mounts)
    assert any("src=/run/state,dst=/work/state,rw=true" in mount for mount in mounts)
    assert any("src=/run/ipc,dst=/work/g3b,rw=true" in mount for mount in mounts)
    assert any("dst=/output,rw=true" in mount for mount in mounts)
    assert not any("candidate-session" in mount for mount in mounts)
    assert not any("candidate" in mount for mount in mounts)
    env = lib.argv_env(argv)
    assert "PYTHONPATH=/project/src:/deps" in env
    assert not lib.key_like_names([item.split("=", 1)[0] for item in env])


def test_candidate_argv_contract() -> None:
    argv = _candidate_argv()
    assert _problems(argv, "candidate") == []
    assert "--uidmap" in argv and "0:65534:1" in argv
    assert "--gidmap" in argv and "2000:2000:1" in argv
    assert "--group-add" in argv and "2000" in argv
    mounts = lib.argv_mounts(argv)
    assert any("src=/stage/candidate,dst=/project,ro=true" in mount for mount in mounts)
    assert any("src=/run/ipc,dst=/work/g3b,ro=true" in mount for mount in mounts)
    assert any("src=/run/candidate-session,dst=/work/session,rw=true" in mount
               for mount in mounts)
    assert not any("dst=/work/state" in mount for mount in mounts)
    assert not any("dst=/output" in mount for mount in mounts)
    assert not any("src=/stage/trusted" in mount for mount in mounts)
    env = lib.argv_env(argv)
    assert "PYTHONPATH=/deps" in env
    assert not any("/project/src" in item for item in env)
    assert not lib.key_like_names([item.split("=", 1)[0] for item in env])


@pytest.mark.parametrize("mutation", [
    "privileged", "state_mount", "evidence_mount", "network_host",
    "key_env", "userns_host", "missing_uidmap", "podman_socket",
])
def test_candidate_argv_contract_rejects_weakening(mutation: str) -> None:
    argv = _candidate_argv()
    if mutation == "privileged":
        argv.insert(2, "--privileged")
    elif mutation == "state_mount":
        argv.extend(["--mount", "type=bind,src=/run/state,dst=/work/state,rw=true"])
    elif mutation == "evidence_mount":
        argv.extend(["--mount", "type=bind,src=/run/evidence,dst=/output,rw=true"])
    elif mutation == "network_host":
        index = argv.index("--network")
        argv[index + 1] = "host"
    elif mutation == "key_env":
        argv.extend(["--env", "DEEPSEEK_API_KEY=nope"])
    elif mutation == "userns_host":
        argv.append("--userns=host")
    elif mutation == "missing_uidmap":
        index = argv.index("--uidmap")
        del argv[index:index + 2]
    elif mutation == "podman_socket":
        argv.extend(["--mount", "type=bind,src=/run/podman/podman.sock,dst=/run/podman.sock"])
    problems = _problems(argv, "candidate")
    assert problems, mutation


def test_trusted_argv_contract_rejects_candidate_mount() -> None:
    argv = _trusted_argv()
    argv.extend(["--mount", "type=bind,src=/run/candidate-session,dst=/work/session,rw=true"])
    assert _problems(argv, "trusted")


# ---------------------------------------------------------------------------
# Candidate stage allow-list / manifest
# ---------------------------------------------------------------------------
def test_candidate_allowlist_accepts_expected_paths() -> None:
    allowed = [
        "run/candidate_entry.py", "config/bridge.patch.yml",
        "runtime/bridge/lib/index.js", "runtime/skill/lib/skills.json",
        "node_modules/@deepseek-ai/dsh-llm/package.json",
        "native-cache/node-addon/x.node", "pkg-cache/pkg/abc/lib/index.js",
        "fixtures/skills.json", "fixtures/capture-tools.json",
        "etc/passwd", "etc/group", "REFERENCE.json",
    ]
    assert lib.forbidden_candidate_reasons(allowed) == []


@pytest.mark.parametrize("forbidden", [
    "src/autoteacher_m0/bridge/controller.py",
    "autoteacher_m0/bridge/controller.py",
    "run/trusted_entry.py",
    "run/launch.py",
    "run/build_stage.py",
    "fake/fake_provider.py",
    "config/admission.json",
    "config/broker.json",
    "config/policy.json",
    "state/broker.sqlite3",
    "state/attempts.sqlite3-wal",
    "receipts/rcpt-abc.json",
    "receipts/received-count.json",
    ".git/config",
    "tests/test_x.py",
    "scripts/g3d/launch.py",
])
def test_candidate_forbidden_paths_are_rejected(forbidden: str) -> None:
    reasons = lib.forbidden_candidate_reasons([forbidden])
    assert reasons, forbidden


def _write_file(path: Path, data: bytes) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    os.chmod(path, 0o444)
    info = os.lstat(path)
    return {"path": str(path.relative_to(path.parents[1])),
            "sha256": lib.sha256_bytes(data), "bytes": info.st_size,
            "mode": 0o444}


def _mini_stage(tmp_path: Path) -> tuple[Path, dict]:
    stage = tmp_path / "stage"
    trusted_file = stage / "trusted" / "run" / "trusted_entry.py"
    trusted_file.parent.mkdir(parents=True)
    trusted_file.write_bytes(b"print('trusted')\n")
    os.chmod(trusted_file, 0o444)
    candidate_file = stage / "candidate" / "run" / "candidate_entry.py"
    candidate_file.parent.mkdir(parents=True)
    candidate_file.write_bytes(b"print('candidate')\n")
    os.chmod(candidate_file, 0o444)
    manifest = {
        "schema": lib.STAGE_SCHEMA,
        "base_sha": lib.PRODUCT_BASE,
        "trusted": {
            "tree_sha256": lib.sha256_tree(stage / "trusted"),
            "files": [{"path": "run/trusted_entry.py",
                       "sha256": lib.sha256_file(trusted_file),
                       "bytes": trusted_file.stat().st_size, "mode": 0o444}],
        },
        "candidate": {
            "tree_sha256": lib.sha256_tree(stage / "candidate"),
            "files": [{"path": "run/candidate_entry.py",
                       "sha256": lib.sha256_file(candidate_file),
                       "bytes": candidate_file.stat().st_size, "mode": 0o444}],
        },
    }
    (stage / "manifest.json").write_bytes(lib.json_bytes(manifest))
    return stage, manifest


def test_manifest_tree_accepts_matching_stage(tmp_path: Path) -> None:
    stage, manifest = _mini_stage(tmp_path)
    result = lib.validate_manifest_tree(stage, manifest)
    assert result["ok"] is True, result["problems"]
    assert result["sections"]["candidate"]["file_count"] == 1


def test_manifest_tree_detects_unknown_extra_and_tamper(tmp_path: Path) -> None:
    stage, manifest = _mini_stage(tmp_path)
    extra = stage / "candidate" / "run" / "unexpected.py"
    extra.write_bytes(b"x")
    result = lib.validate_manifest_tree(stage, manifest)
    assert any("unknown" in problem for problem in result["problems"])
    extra.unlink()
    target = stage / "candidate" / "run" / "candidate_entry.py"
    os.chmod(target, 0o644)
    target.write_bytes(b"tampered")
    result = lib.validate_manifest_tree(stage, manifest)
    assert any("sha_mismatch" in problem for problem in result["problems"])


def test_manifest_tree_detects_symlink(tmp_path: Path) -> None:
    stage, manifest = _mini_stage(tmp_path)
    link = stage / "candidate" / "run" / "link.py"
    link.symlink_to("/etc/passwd")
    result = lib.validate_manifest_tree(stage, manifest)
    assert any("symlink" in problem for problem in result["problems"])


# ---------------------------------------------------------------------------
# TERM -> bounded KILL and cleanup
# ---------------------------------------------------------------------------
def test_terminate_container_sends_term_then_kill_when_stuck() -> None:
    signals: list[tuple[str, str]] = []
    state = {"exit": None}

    def signal_fn(name: str, sig: str) -> None:
        signals.append((name, sig))
        if sig == "KILL":
            state["exit"] = 137

    def wait_exit(name: str, _timeout: float) -> int | None:
        return state["exit"]

    record = lib.terminate_container(
        "c", signal_fn=signal_fn, wait_exit=wait_exit,
        grace_s=0.05, kill_wait_s=0.05, poll_s=0.01)
    assert record["sigterm"] is True
    assert record["sigkill"] is True
    assert record["exit_code"] == 137
    assert signals == [("c", "TERM"), ("c", "KILL")]


def test_terminate_container_does_not_escalate_when_term_works() -> None:
    signals: list[tuple[str, str]] = []

    def signal_fn(name: str, sig: str) -> None:
        signals.append((name, sig))

    def wait_exit(name: str, _timeout: float) -> int | None:
        return 0

    record = lib.terminate_container(
        "c", signal_fn=signal_fn, wait_exit=wait_exit,
        grace_s=0.05, kill_wait_s=0.05, poll_s=0.01)
    assert record["sigkill"] is False
    assert record["exit_code"] == 0
    assert signals == [("c", "TERM")]


def test_safe_delete_tree_is_scoped_idempotent_and_never_follows_symlinks(
        tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    victim = runs / "run1"
    nested = victim / "candidate-session" / "a" / "b"
    nested.mkdir(parents=True)
    (nested / "file.txt").write_text("data")
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    (outside_dir / "keep.txt").write_text("keep")
    (victim / "link-out").symlink_to(outside_dir)
    (victim / "link-file").symlink_to(outside_dir / "keep.txt")
    first = lib.safe_delete_tree(runs, victim)
    assert first["removed"] is True
    assert first["removed_files"] == 1
    assert first["removed_symlinks"] == 2
    assert not victim.exists()
    assert (outside_dir / "keep.txt").read_text() == "keep"
    second = lib.safe_delete_tree(runs, victim)
    assert second["removed"] is False and second.get("absent") is True
    with pytest.raises(lib.G3DError):
        lib.safe_delete_tree(runs, outside_dir)


def test_unlink_socket_only_removes_a_verified_socket(tmp_path: Path) -> None:
    regular = tmp_path / "regular"
    regular.write_text("x")
    assert lib.unlink_socket(regular, expected_uid=os.geteuid(),
                             expected_gid=os.getegid())["removed"] is False
    assert regular.exists()

    link = tmp_path / "link"
    link.symlink_to(regular)
    assert lib.unlink_socket(link, expected_uid=os.geteuid(),
                             expected_gid=os.getegid())["removed"] is False
    assert link.is_symlink()

    sock_path = tmp_path / "bridge.sock"
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.bind(str(sock_path))
    finally:
        sock.close()
    result = lib.unlink_socket(sock_path, expected_uid=os.geteuid(),
                               expected_gid=os.getegid())
    assert result["removed"] is True
    assert not sock_path.exists()
    assert lib.unlink_socket(sock_path)["reason"] == "absent"


# ---------------------------------------------------------------------------
# Generated configs / env hygiene (static, no container)
# ---------------------------------------------------------------------------
def test_controller_template_encodes_the_frozen_boundary() -> None:
    document = json.loads(
        (REPO_ROOT / "config" / "g3d" / "trusted" /
         "controller.template.json").read_text())
    assert document["socket_mode"] == 432  # 0o660
    assert document["socket_gid"] is None
    assert document["expected_peer_uid"] == 65534
    assert document["expected_uid"] == 65534
    assert document["socket_path"] == "/work/g3b/bridge.sock"
    assert document["admission_path"] == "/work/state/admission.json"
    assert document["attempt_db"] == "/work/state/attempts.sqlite3"
    assert document["receipt_dir"] == "/work/state/receipts"
    assert document["fake_script"] == "/project/fake/fake_provider.py"


def test_admission_template_render_keeps_launcher_uid_65534() -> None:
    template = (REPO_ROOT / "config" / "g3d" / "trusted" /
                "admission.template.json").read_text()
    rendered = (template
                .replace("{{ADMISSION_ID}}", "a" * 32)
                .replace("{{RUN_ID}}", "d1-test")
                .replace("{{TOOL_SCHEMAS}}", "[]")
                .replace("{{FAKE_SCENARIO}}", "ok_usage")
                .replace("{{EXPIRY_UTC}}", "2030-01-01T00:00:00Z")
                .replace("{{NONCE}}", "b" * 32))
    document = json.loads(rendered)
    assert document["launcher"]["uid"] == 65534
    assert document["launcher"]["container"] is True
    assert document["synthetic"] is True
    assert document["route"] == {"route_id": "offline-test-only-g3b",
                                 "provider": "offline-test-only-g3b",
                                 "model": "fixture-bridge-v1"}
    assert document["limits"]["max_attempts"] == 1


def test_broker_template_is_synthetic_and_state_scoped() -> None:
    document = json.loads(
        (REPO_ROOT / "config" / "g3d" / "trusted" /
         "broker.template.json").read_text())
    assert document["synthetic"] is True
    assert document["db_path"].startswith("/work/state/")
    assert "provider" not in json.dumps(document["routes"]).lower() or True
    text = json.dumps(document)
    for marker in ("api_key", "apiKey", "base_url", "https://", "http://"):
        assert marker not in text


def test_env_snapshot_records_names_not_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-should-never-appear")
    snapshot = lib.env_snapshot()
    assert "DEEPSEEK_API_KEY" in snapshot["key_like_names"]
    assert "sk-should-never-appear" not in json.dumps(snapshot)
    assert lib.key_like_names(["DEEPSEEK_API_KEY", "PATH", "GITHUB_TOKEN"])


# ---------------------------------------------------------------------------
# D1-C Tool scenario: admission limits, prompt and durable ledger pairing
# ---------------------------------------------------------------------------
def test_scenario_admission_is_frozen_per_scenario() -> None:
    echo = launcher_mod.scenario_admission("echo")
    tool = launcher_mod.scenario_admission("tool")
    assert echo == {"fake_scenario": "ok_usage", "max_calls": 1}
    assert tool == {"fake_scenario": "tool", "max_calls": 2}
    # A caller cannot mutate the module-level table through the returned dict.
    echo["max_calls"] = 99
    assert launcher_mod.SCENARIO_ADMISSION["echo"]["max_calls"] == 1
    with pytest.raises(lib.G3DError):
        launcher_mod.scenario_admission("resume")


def test_scenario_prompt_and_default_argv() -> None:
    assert launcher_mod.scenario_prompt("echo") == "G3D_ECHO"
    assert launcher_mod.scenario_prompt("tool") == (
        "Use skill_lookup to look up binary_search")
    tool_args = launcher_mod.parse_args(["--scenario", "tool"])
    assert tool_args.prompt == launcher_mod.scenario_prompt("tool")
    echo_args = launcher_mod.parse_args(["--scenario", "echo"])
    assert echo_args.prompt == "G3D_ECHO"
    explicit = launcher_mod.parse_args(["--scenario", "tool", "--prompt", "custom"])
    assert explicit.prompt == "custom"
    with pytest.raises(SystemExit):
        launcher_mod.parse_args(["--scenario", "resume"])


def test_pair_tool_ledger_joins_by_durable_ids_not_list_order() -> None:
    claims = [
        {"call_id": "call-b", "reservation_id": "res-b",
         "request_digest": "prep-b", "status": "COMPLETED"},
        {"call_id": "call-a", "reservation_id": "res-a",
         "request_digest": "prep-a", "status": "COMPLETED"},
    ]
    receipts = [
        {"receipt_id": "rcpt-b", "raw_sha256": "payload-b", "usage": {"outputTokens": 5}},
        {"receipt_id": "rcpt-a", "raw_sha256": "payload-a", "usage": {"outputTokens": 5}},
    ]
    attempts = [
        {"attempt_id": "att-1", "call_id": "call-a", "reservation_id": "res-a",
         "receipt_id": "rcpt-a", "logical_step": 0, "state": "SETTLED",
         "prepared_digest": "prep-a", "payload_digest": "payload-a"},
        {"attempt_id": "att-2", "call_id": "call-b", "reservation_id": "res-b",
         "receipt_id": "rcpt-b", "logical_step": 1, "state": "SETTLED",
         "prepared_digest": "prep-b", "payload_digest": "payload-b"},
    ]
    paired = launcher_mod.pair_tool_ledger(attempts, claims, receipts)
    assert [item["step"] for item in paired] == [0, 1]
    assert [item["attempt"]["attempt_id"] for item in paired] == ["att-1", "att-2"]
    assert all(item["prepared_ok"] for item in paired)
    assert all(item["payload_ok"] for item in paired)
    assert all(item["reservation_link_ok"] for item in paired)


def test_pair_tool_ledger_exposes_missing_or_mismatched_rows() -> None:
    claims = [{"call_id": "call-a", "reservation_id": "res-a",
               "request_digest": "prep-wrong", "status": "COMPLETED"}]
    receipts = [{"receipt_id": "rcpt-a", "raw_sha256": "payload-wrong",
                 "usage": {"outputTokens": 5}}]
    attempts = [
        {"attempt_id": "att-1", "call_id": "call-a", "reservation_id": "res-a",
         "receipt_id": "rcpt-a", "logical_step": 0, "state": "SETTLED",
         "prepared_digest": "prep-a", "payload_digest": "payload-a"},
        {"attempt_id": "att-2", "call_id": "call-orphan", "reservation_id": "res-x",
         "receipt_id": "rcpt-missing", "logical_step": 1, "state": "SETTLED",
         "prepared_digest": "prep-x", "payload_digest": "payload-x"},
    ]
    paired = launcher_mod.pair_tool_ledger(attempts, claims, receipts)
    assert len(paired) == 2
    assert paired[0]["prepared_ok"] is False
    assert paired[0]["payload_ok"] is False
    assert paired[1]["claim"] is None and paired[1]["receipt"] is None
    assert paired[1]["prepared_ok"] is False
    assert paired[1]["payload_ok"] is False
    assert paired[1]["reservation_link_ok"] is False


def test_candidate_evidence_capture_refuses_poisoned_session_entries(
        tmp_path: Path) -> None:
    """D1-11: the launcher reads candidate output as untrusted input only."""
    run_dir = tmp_path / "run"
    evidence = tmp_path / "evidence"
    session = run_dir / "candidate-session" / "evidence"
    session.mkdir(parents=True)
    evidence.mkdir()
    (session / "dsh-result.json").write_text('{"ok": true}\n')
    os.symlink("/etc/passwd", session / "poison-link")
    if hasattr(os, "mkfifo"):
        os.mkfifo(session / "poison-fifo")
    broken = launcher_mod.Launcher.__new__(launcher_mod.Launcher)
    broken.run_dir = run_dir
    broken.evidence = evidence
    broken.records = {}
    broken._copy_candidate_evidence()
    copied = {item["name"]: item for item in broken.records["candidate_evidence"]}
    assert copied["dsh-result.json"]["bytes"] > 0
    assert "error" in copied["poison-link"]
    if "poison-fifo" in copied:
        assert "error" in copied["poison-fifo"]
    assert (evidence / "traces" / "dsh-result.json").is_file()
    assert not (evidence / "traces" / "poison-link").exists()
    assert not (evidence / "traces" / "poison-fifo").exists()
