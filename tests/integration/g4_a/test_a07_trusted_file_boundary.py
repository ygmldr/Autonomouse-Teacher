"""G4-A-07: trusted files must be repo-external, private and not candidate-writable."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from autoteacher_m0.security import authorization as authorization_module
from g4a_support import NOW, TEST_ONLY_SEED


class _DeniedOS:
    """Proxy that denies every low-level open, simulating an unreadable file."""

    def __getattr__(self, name):
        return getattr(os, name)

    def open(self, *args, **kwargs):  # noqa: A003 - deliberate fault injection
        raise PermissionError(13, "Permission denied")


def _assert_invalid(trusted, **kwargs) -> None:
    decision = trusted.load(**kwargs)
    assert decision.approved is False
    assert decision.signature_valid is False
    assert any(reason.startswith("EXTERNAL_AUTHORIZATION_INVALID")
               for reason in decision.reasons), decision.reasons
    assert trusted.use_records() == []


def test_a07_in_repo_trusted_files_are_unusable(trusted) -> None:
    repo = trusted.repo
    for label, source in (("authorization", trusted.authorization),
                          ("keys", trusted.keys),
                          ("revocations", trusted.revocations)):
        target = repo / f"copied-{label}.json"
        target.write_bytes(source.read_bytes())
        if label == "authorization":
            _assert_invalid(trusted, authorization=target)
        elif label == "keys":
            _assert_invalid(trusted, keys=target)
        else:
            _assert_invalid(trusted, revocations=target)


def test_a07_symlinked_trusted_files_are_unusable(trusted, tmp_path: Path) -> None:
    for label, source in (("authorization", trusted.authorization),
                          ("keys", trusted.keys),
                          ("revocations", trusted.revocations)):
        link = tmp_path / f"link-{label}.json"
        link.symlink_to(source)
        if label == "authorization":
            _assert_invalid(trusted, authorization=link)
        elif label == "keys":
            _assert_invalid(trusted, keys=link)
        else:
            _assert_invalid(trusted, revocations=link)


@pytest.mark.parametrize("mode", [0o666, 0o646, 0o662])
def test_a07_group_or_world_writable_file_fails_closed(trusted, mode: int) -> None:
    trusted.keys.chmod(mode)
    try:
        _assert_invalid(trusted, keys=trusted.keys)
    finally:
        trusted.keys.chmod(0o644)
    assert trusted.load().approved is True


def test_a07_writable_trusted_directory_fails_closed(trusted) -> None:
    trusted.trusted.chmod(0o777)
    try:
        _assert_invalid(trusted, authorization=trusted.authorization)
    finally:
        trusted.trusted.chmod(0o755)
    assert trusted.load().approved is True


def test_a07_non_regular_file_fails_closed(trusted) -> None:
    directory = trusted.trusted / "keys-directory"
    directory.mkdir()
    _assert_invalid(trusted, keys=directory)


def test_a07_unreadable_file_fails_closed(trusted, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(authorization_module, "os", _DeniedOS())
    _assert_invalid(trusted, authorization=trusted.authorization)


@pytest.mark.skipif(os.geteuid() != 0, reason="candidate-uid ownership probe needs root")
def test_a07_candidate_owned_files_fail_closed(trusted) -> None:
    for label, source in (("keys", trusted.keys),
                          ("authorization", trusted.authorization)):
        source.chmod(0o644)
        os.chown(source, 65534, 65534)
        try:
            _assert_invalid(trusted, **{label: source})
        finally:
            os.chown(source, 0, 0)
    assert trusted.load().approved is True


def test_a07_candidate_stage_placement_is_reported_by_controller(trusted) -> None:
    copied = {}
    for label, source in (("authorization", trusted.authorization),
                          ("keys", trusted.keys),
                          ("revocations", trusted.revocations)):
        target = trusted.stage / source.name
        target.write_bytes(source.read_bytes())
        copied[label] = target
    decision = trusted.controller(**copied).inspect(now=NOW)
    assert decision.status == "BLOCKED"
    assert decision.billable_send_authorized is False
    for label in ("APPROVAL", "KEYS", "REVOCATION"):
        assert f"TRUSTED_{label}_PATH_INSIDE_CANDIDATE_STAGE" in decision.reasons, \
            decision.reasons


def test_a07_world_writable_stage_is_rejected_by_the_loader_too(trusted) -> None:
    key_copy = trusted.stage / "trusted-keys.json"
    key_copy.write_bytes(trusted.keys.read_bytes())
    trusted.stage.chmod(0o777)
    try:
        _assert_invalid(trusted, keys=key_copy)
    finally:
        trusted.stage.chmod(0o755)


def test_a07_no_private_key_material_in_stage_or_decision(trusted) -> None:
    seed_hex = TEST_ONLY_SEED.hex()
    decision = trusted.load()
    assert seed_hex not in repr(decision)
    assert TEST_ONLY_SEED not in decision.require().payload_bytes
    assert seed_hex not in trusted.authorization.read_text(encoding="utf-8")
    stage_files = [path for path in trusted.stage.rglob("*") if path.is_file()]
    assert stage_files == []
    assert b"PRIVATE KEY" not in trusted.keys.read_bytes()
    assert json.loads(trusted.keys.read_text(encoding="utf-8")).keys() == {"schema", "keys"}
