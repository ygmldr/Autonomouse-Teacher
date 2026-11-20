"""A-NEXT packet v3 builder/verifier tests: positives, refusals, mutations."""

from __future__ import annotations

import json
import os
import subprocess

from a_next_packet_helpers import (
    IMPL,
    canonical_sha,
    copy_packet,
    make_tree,
    mutate_file,
    normalize_modes,
    output_json,
    run_script,
)


def _verify(packet, *args):
    return run_script("verify_packet_v3.py", "--packet-root", packet, "--allow-phase1", *args)


def _assert_fail(proc, expected_code: int, reason: str | None = None):
    document = output_json(proc)
    assert document["verdict"] == "FAIL", document
    assert proc.returncode == expected_code, (proc.returncode, document["reasons"])
    if reason is not None:
        assert reason in document["reasons"], document["reasons"]


# ---------------------------------------------------------------------------
# positives
# ---------------------------------------------------------------------------
def test_build_and_verify_final_packet(built_packet):
    packet = built_packet["packet"]
    proc = run_script("verify_packet_v3.py", "--packet-root", packet)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    document = output_json(proc)
    assert document["verdict"] == "PASS"
    assert document["payload_count"] == 3
    assert document["identity"]["impl_sha"] == IMPL
    assert len(document["content_sha256"]) == 64
    assert document["content_sha256"] != document["identity"]["impl_sha"]


def test_manifest_layers_identity_and_incident(built_packet):
    manifest = built_packet["manifest"]
    assert manifest["schema"] == "m0.a-next.review-packet.v3"
    identity = manifest["identity"]
    assert identity["impl_sha"] == IMPL
    assert len(identity["content_sha256"]) == 64
    assert identity["content_sha256"] != identity["impl_sha"]
    assert identity["content_sha256_kind"] == "payload_only_content_digest"
    assert manifest["layers"]["hashes"]["entry_count"] == 3 + 2
    assert manifest["inventory"]["payload_count"] == 3
    frozen = manifest["frozen_identity"]
    assert frozen["rootfs_snapshot"] == "PROVIDED"
    assert frozen["rootfs_canonical_t0"] == frozen["rootfs_canonical_t1"] == built_packet["frozen_sha"]
    assert frozen["t0_t1_equal"] is True
    incident = manifest["environment_incident"]
    assert incident["id"] == "INCIDENT_20261121"
    assert incident["restoration"]["source_backup_tar_sha256"].startswith("11172f02")
    assert incident["lost"]["v1_packet"]["status"] == "LOST_ORIGINAL_BYTES_UNVERIFIABLE"
    assert incident["claims_allowed"]["global_no_drift"] is False
    assert incident["claims_allowed"]["evidence_completeness"] is False
    assert "MUST NOT" in incident["disclosure"]


def test_layout_and_modes(built_packet):
    packet = built_packet["packet"]
    root_files = {path.name for path in packet.iterdir() if path.is_file()}
    assert root_files == {"manifest.json", "hashes.sha256", "README.md"}
    for root, _dirs, files in os.walk(packet):
        for name in files:
            mode = os.lstat(os.path.join(root, name)).st_mode & 0o777
            assert mode == 0o444, (name, oct(mode))
    hashes_lines = (packet / "hashes.sha256").read_text().splitlines()
    assert len(hashes_lines) == 3 + 2
    transport = subprocess.run(
        ["tar", "-cf", "-", "-C", str(packet), "."], stdout=subprocess.PIPE, check=True
    )
    assert len(transport.stdout) > 0


def test_verify_without_allow_phase1_final_packet_passes(built_packet):
    proc = run_script(
        "verify_packet_v3.py", "--packet-root", built_packet["packet"]
    )
    assert proc.returncode == 0, proc.stdout


def test_content_sha_is_independent_of_impl_sha(tmp_path, staging, frozen_rootfs):
    identity = []
    for impl in ("a" * 40, "b" * 40):
        out = tmp_path / "artifacts" / f"review-packet-a-next-v3-{impl}"
        proc = run_script(
            "build_packet_v3.py",
            "--staging-dir",
            staging,
            "--impl-sha",
            impl,
            "--no-git-check",
            "--out-dir",
            out,
            "--frozen-rootfs",
            frozen_rootfs,
            "--expected-rootfs-sha",
            canonical_sha(frozen_rootfs),
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr
        manifest = json.loads((out / "manifest.json").read_text())
        identity.append(manifest["identity"])
    assert identity[0]["content_sha256"] == identity[1]["content_sha256"]
    assert identity[0]["impl_sha"] != identity[1]["impl_sha"]


def test_content_sha_changes_with_payload(tmp_path, built_packet):
    altered = tmp_path / "altered-staging"
    make_tree(
        altered,
        {
            "README.txt": "packet payload changed\n",
            "cases/r1/index.json": '{"case":"r1"}\n',
        },
    )
    impl = "c" * 40
    out = tmp_path / "artifacts" / f"review-packet-a-next-v3-{impl}"
    proc = run_script(
        "build_packet_v3.py",
        "--staging-dir",
        altered,
        "--impl-sha",
        impl,
        "--no-git-check",
        "--out-dir",
        out,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["identity"]["content_sha256"] != built_packet["manifest"]["identity"]["content_sha256"]


def test_phase1_packet_requires_allow_flag(tmp_path, staging):
    out = tmp_path / "artifacts" / ("review-packet-a-next-v3-" + IMPL)
    build = run_script(
        "build_packet_v3.py",
        "--staging-dir",
        staging,
        "--impl-sha",
        IMPL,
        "--no-git-check",
        "--out-dir",
        out,
    )
    assert build.returncode == 0, build.stdout + build.stderr
    strict = run_script("verify_packet_v3.py", "--packet-root", out)
    assert strict.returncode == 44
    allowed = _verify(out)
    assert allowed.returncode == 0


def test_git_verified_build(tmp_path, staging):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    make_tree(repo, {"f.txt": "x\n"})
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "base"],
        check=True,
    )
    sha = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    out = tmp_path / "artifacts" / f"review-packet-a-next-v3-{sha}"
    proc = run_script(
        "build_packet_v3.py",
        "--staging-dir",
        staging,
        "--impl-sha",
        sha,
        "--repo",
        repo,
        "--out-dir",
        out,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["identity"]["git_commit_verified"] is True


# ---------------------------------------------------------------------------
# builder refusals
# ---------------------------------------------------------------------------
def _build(staging, tmp_path, *extra):
    out = tmp_path / "artifacts" / ("review-packet-a-next-v3-" + IMPL)
    return run_script(
        "build_packet_v3.py",
        "--staging-dir",
        staging,
        "--impl-sha",
        IMPL,
        "--no-git-check",
        "--out-dir",
        out,
        *extra,
    )


def _assert_build_refused(proc, code: str):
    assert proc.returncode == 40, proc.stdout + proc.stderr
    document = output_json(proc)
    assert document["verdict"] == "BUILD_REFUSED"
    assert document["code"] == code, document


def test_builder_refuses_symlink_staging(tmp_path, staging):
    os.symlink(staging / "README.txt", staging / "link.txt")
    _assert_build_refused(_build(staging, tmp_path), "SYMLINK_REFUSED")


def test_builder_refuses_hardlink_staging(tmp_path, staging):
    os.link(staging / "README.txt", staging / "hard.txt")
    _assert_build_refused(_build(staging, tmp_path), "HARDLINK_REFUSED")


def test_builder_refuses_special_file(tmp_path, staging):
    os.mkfifo(staging / "fifo")
    _assert_build_refused(_build(staging, tmp_path), "SPECIAL_FILE_REFUSED")


def test_builder_refuses_sidecar(tmp_path, staging):
    (staging / ".DS_Store").write_text("")
    _assert_build_refused(_build(staging, tmp_path), "SIDECAR_REFUSED")


def test_builder_refuses_invalid_impl_sha(tmp_path, staging):
    out = tmp_path / "artifacts" / ("review-packet-a-next-v3-" + IMPL)
    proc = run_script(
        "build_packet_v3.py",
        "--staging-dir",
        staging,
        "--impl-sha",
        "not-a-sha",
        "--no-git-check",
        "--out-dir",
        out,
    )
    _assert_build_refused(proc, "IMPL_SHA_INVALID")


def test_builder_refuses_content_sha_attestation_mismatch(tmp_path, staging):
    proc = _build(staging, tmp_path, "--content-sha", "0" * 64)
    _assert_build_refused(proc, "CONTENT_SHA_ATTESTATION_MISMATCH")


def test_builder_refuses_rootfs_t0_mismatch(tmp_path, staging, frozen_rootfs):
    proc = _build(
        staging,
        tmp_path,
        "--frozen-rootfs",
        frozen_rootfs,
        "--expected-rootfs-sha",
        "0" * 64,
    )
    _assert_build_refused(proc, "ROOTFS_T0_MISMATCH")


def test_builder_refuses_existing_out_dir(tmp_path, staging):
    first = _build(staging, tmp_path)
    assert first.returncode == 0, first.stdout
    second = _build(staging, tmp_path)
    _assert_build_refused(second, "OUT_DIR_EXISTS")


def test_builder_refuses_non_identity_out_dir(tmp_path, staging):
    proc = run_script(
        "build_packet_v3.py",
        "--staging-dir",
        staging,
        "--impl-sha",
        IMPL,
        "--no-git-check",
        "--out-dir",
        tmp_path / "not-a-packet",
    )
    _assert_build_refused(proc, "OUT_DIR_NOT_NEW_IDENTITY")


def test_builder_refuses_unverified_commit(tmp_path, staging):
    out = tmp_path / "artifacts" / ("review-packet-a-next-v3-" + IMPL)
    proc = run_script(
        "build_packet_v3.py",
        "--staging-dir",
        staging,
        "--impl-sha",
        IMPL,
        "--repo",
        tmp_path,
        "--out-dir",
        out,
    )
    _assert_build_refused(proc, "IMPL_SHA_NOT_IN_REPO")


# ---------------------------------------------------------------------------
# verifier mutations (each must FAIL)
# ---------------------------------------------------------------------------
def _copy(built_packet, tmp_path, name):
    packet = copy_packet(built_packet["packet"], tmp_path / name)
    normalize_modes(packet)
    return packet


def test_verifier_rejects_unlisted_extra_file(built_packet, tmp_path):
    bad = _copy(built_packet, tmp_path, "bad-extra")
    (bad / "payload" / "evil.txt").write_text("evil\n")
    normalize_modes(bad)
    _assert_fail(_verify(bad), 45, "EXTRA_ENTRY")


def test_verifier_rejects_root_sidecar(built_packet, tmp_path):
    bad = _copy(built_packet, tmp_path, "bad-sidecar")
    (bad / ".DS_Store").write_text("")
    normalize_modes(bad)
    _assert_fail(_verify(bad), 46, "SIDECAR_REFUSED")


def test_verifier_rejects_symlink(built_packet, tmp_path):
    bad = _copy(built_packet, tmp_path, "bad-symlink")
    normalize_modes(bad)
    os.symlink(bad / "payload" / "README.txt", bad / "payload" / "link.txt")
    _assert_fail(_verify(bad), 47, "SYMLINK_REFUSED")


def test_verifier_rejects_hardlink(built_packet, tmp_path):
    bad = _copy(built_packet, tmp_path, "bad-hardlink")
    normalize_modes(bad)
    os.link(bad / "payload" / "README.txt", bad / "payload" / "hard.txt")
    _assert_fail(_verify(bad), 47, "HARDLINK_REFUSED")


def test_verifier_rejects_mode_change(built_packet, tmp_path):
    bad = _copy(built_packet, tmp_path, "bad-mode")
    os.chmod(bad / "payload" / "README.txt", 0o666)
    _assert_fail(_verify(bad), 48, "MODE_MISMATCH")


def test_verifier_rejects_payload_hash_mismatch(built_packet, tmp_path):
    bad = _copy(built_packet, tmp_path, "bad-content")
    mutate_file(bad / "payload" / "README.txt", lambda path: path.write_text("tampered\n"))
    _assert_fail(_verify(bad), 41, "HASH_MISMATCH")


def test_verifier_rejects_deleted_payload_file(built_packet, tmp_path):
    bad = _copy(built_packet, tmp_path, "bad-missing")
    os.chmod(bad / "payload", 0o755)
    (bad / "payload" / "review" / "summary.md").unlink()
    os.chmod(bad / "payload", 0o555)
    _assert_fail(_verify(bad), 45, "MISSING_ENTRY")


def test_verifier_rejects_hashes_tamper(built_packet, tmp_path):
    bad = _copy(built_packet, tmp_path, "bad-hashes")
    hashes = bad / "hashes.sha256"
    lines = hashes.read_text().splitlines()
    digest, relpath = lines[0].split("  ", 1)
    lines[0] = f"{'0' * 64}  {relpath}"
    mutate_file(hashes, lambda path: path.write_text("\n".join(lines) + "\n"))
    _assert_fail(_verify(bad), 41, "HASH_MISMATCH")


def test_verifier_rejects_readme_tamper(built_packet, tmp_path):
    bad = _copy(built_packet, tmp_path, "bad-readme")
    mutate_file(bad / "README.md", lambda path: path.write_text(path.read_text() + "x"))
    _assert_fail(_verify(bad), 41, "HASH_MISMATCH")


def test_verifier_rejects_content_sha_manifest_tamper(built_packet, tmp_path):
    bad = _copy(built_packet, tmp_path, "bad-content-sha")
    manifest = json.loads((bad / "manifest.json").read_text())
    manifest["inventory"]["content_sha256"] = "0" * 64
    normalize_modes(bad)
    mutate_file(
        bad / "manifest.json",
        lambda path: path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n"),
    )
    _assert_fail(_verify(bad), 42, "CONTENT_SHA_MISMATCH")


def test_verifier_rejects_schema_tamper(built_packet, tmp_path):
    bad = _copy(built_packet, tmp_path, "bad-schema")
    manifest = json.loads((bad / "manifest.json").read_text())
    manifest["schema"] = "m0.a-next.review-packet.v2"
    mutate_file(
        bad / "manifest.json",
        lambda path: path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n"),
    )
    _assert_fail(_verify(bad), 43, "SCHEMA_MISMATCH")


def test_verifier_rejects_duplicate_manifest_keys(built_packet, tmp_path):
    bad = _copy(built_packet, tmp_path, "bad-duplicate")
    text = (bad / "manifest.json").read_text()
    text = text.replace('{\n  "environment_incident"', '{\n  "schema": "x",\n  "environment_incident"', 1)
    mutate_file(bad / "manifest.json", lambda path: path.write_text(text))
    _assert_fail(_verify(bad), 43, "DUPLICATE_JSON_KEY")


def test_verifier_rejects_missing_incident(built_packet, tmp_path):
    bad = _copy(built_packet, tmp_path, "bad-incident")
    manifest = json.loads((bad / "manifest.json").read_text())
    manifest.pop("environment_incident")
    mutate_file(
        bad / "manifest.json",
        lambda path: path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n"),
    )
    _assert_fail(_verify(bad), 44, "INCIDENT_DISCLOSURE_MISSING")


def test_verifier_rejects_forbidden_global_no_drift_claim(built_packet, tmp_path):
    bad = _copy(built_packet, tmp_path, "bad-claim")
    manifest = json.loads((bad / "manifest.json").read_text())
    manifest["environment_incident"]["claims_allowed"]["global_no_drift"] = True
    mutate_file(
        bad / "manifest.json",
        lambda path: path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n"),
    )
    _assert_fail(_verify(bad), 44, "CLAIM_GLOBAL_NO_DRIFT_FORBIDDEN")


def test_verifier_rejects_v1_recovered_claim(built_packet, tmp_path):
    bad = _copy(built_packet, tmp_path, "bad-v1")
    manifest = json.loads((bad / "manifest.json").read_text())
    manifest["environment_incident"]["lost"]["v1_packet"]["status"] = "RECOVERED_VERIFIED"
    mutate_file(
        bad / "manifest.json",
        lambda path: path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n"),
    )
    _assert_fail(_verify(bad), 44, "V1_CLAIM_INVALID")


def test_verifier_rejects_extra_root_directory(built_packet, tmp_path):
    bad = _copy(built_packet, tmp_path, "bad-emptydir")
    (bad / "extra-dir").mkdir()
    normalize_modes(bad)
    _assert_fail(_verify(bad), 45, "EMPTY_DIRECTORY")


def test_verifier_expected_impl_mismatch(built_packet):
    proc = _verify(built_packet["packet"], "--expected-impl-sha", "b" * 40)
    _assert_fail(proc, 43, "IMPL_SHA_MISMATCH")


def test_verifier_expected_content_mismatch(built_packet):
    proc = _verify(built_packet["packet"], "--expected-content-sha", "0" * 64)
    _assert_fail(proc, 42, "CONTENT_SHA_MISMATCH_EXPECTED")


def test_verifier_json_out(built_packet, tmp_path):
    json_out = tmp_path / "verify.json"
    proc = run_script(
        "verify_packet_v3.py",
        "--packet-root",
        built_packet["packet"],
        "--allow-phase1",
        "--json-out",
        json_out,
    )
    assert proc.returncode == 0
    assert json.loads(json_out.read_text())["verdict"] == "PASS"
