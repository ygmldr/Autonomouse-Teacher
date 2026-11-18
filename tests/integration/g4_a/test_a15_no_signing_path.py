"""G4-A-15: no signing seed or signing path is reachable from trusted runtime code."""
from __future__ import annotations

import ast
import dataclasses
import os
from pathlib import Path

from autoteacher_m0.security import ed25519
from autoteacher_m0.security.authorization import (
    AuthorizationDecision,
    ExecutionAuthorization,
)
from autoteacher_m0.security.live_controller import ControllerDecision
from g4a_support import REPO_ROOT, TEST_ONLY_SEED

PRUNED = {".git", "artifacts", "node_modules", ".venv", "dist", "build", "__pycache__",
          "spikes"}


def repo_files(*roots: str) -> list[Path]:
    found: list[Path] = []
    for root in roots:
        base = REPO_ROOT / root
        for directory, subdirectories, filenames in os.walk(base):
            subdirectories[:] = [name for name in subdirectories if name not in PRUNED]
            found.extend(Path(directory) / name for name in filenames)
    return found


def ed25519_attribute_uses() -> list[tuple[str, str, int]]:
    uses: list[tuple[str, str, int]] = []
    for path in repo_files("src"):
        if path.suffix != ".py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                    and node.value.id == "ed25519"):
                uses.append((path.relative_to(REPO_ROOT).as_posix(), node.attr, node.lineno))
    return uses


def test_a15_runtime_only_uses_verify_primitives() -> None:
    uses = ed25519_attribute_uses()
    assert uses, "authorization must still verify signatures"
    assert {attribute for _, attribute, _ in uses} == {"verify", "is_valid_public_key"}, uses
    assert {module for module, _, _ in uses} == {
        "src/autoteacher_m0/security/authorization.py"}, uses


def test_a15_signing_api_is_not_imported_by_runtime_modules() -> None:
    importers = set()
    for path in repo_files("src"):
        if path.suffix != ".py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.ImportFrom):
                names = [alias.name for alias in node.names]
                module = (node.module or "").split(".")[-1]
                if module == "ed25519":
                    names.append("ed25519")
            elif isinstance(node, ast.Import):
                names = [alias.name.split(".")[-1] for alias in node.names]
            if "ed25519" in names:
                importers.add(path.relative_to(REPO_ROOT).as_posix())
    assert importers == {"src/autoteacher_m0/security/authorization.py"}, importers


def test_a15_no_seed_field_or_private_key_field_exists() -> None:
    for dataclass_type in (ExecutionAuthorization, AuthorizationDecision, ControllerDecision):
        names = {field.name.lower() for field in dataclasses.fields(dataclass_type)}
        assert not names & {"seed", "private_key", "secret", "signing_key", "signature_key"}


def test_a15_verified_objects_never_carry_the_test_seed(trusted) -> None:
    decision = trusted.load()
    seed_hex = TEST_ONLY_SEED.hex()
    assert seed_hex not in repr(decision)
    assert seed_hex not in repr(decision.require())
    assert seed_hex not in repr(decision.reasons)
    assert TEST_ONLY_SEED not in decision.require().payload_bytes
    assert seed_hex not in trusted.authorization.read_text(encoding="utf-8")
    assert seed_hex not in trusted.keys.read_text(encoding="utf-8")


def test_a15_candidate_stage_and_command_have_no_key_material(trusted) -> None:
    assert [path for path in trusted.stage.rglob("*")] == []
    command = trusted.controller().candidate_command()
    joined = " ".join(command)
    assert str(trusted.trusted) not in joined
    assert "trusted-keys" not in joined
    assert "authorization" not in joined
    assert "revocation" not in joined
    assert "PRIVATE KEY" not in joined
    assert TEST_ONLY_SEED.hex() not in joined


def test_a15_no_private_key_markers_in_source_or_config() -> None:
    markers = (b"BEGIN PRIVATE KEY", b"BEGIN RSA PRIVATE KEY",
               b"BEGIN OPENSSH PRIVATE KEY")
    for path in repo_files("src", "config", "scripts", "plugins"):
        content = path.read_bytes()
        for marker in markers:
            assert marker not in content, (path, marker)


def test_a15_signing_primitive_is_offline_and_test_only() -> None:
    source = REPO_ROOT / "src" / "autoteacher_m0" / "security" / "ed25519.py"
    text = source.read_text(encoding="utf-8")
    assert "test-only" in text.lower()
    seed = bytes.fromhex("11" * 32)
    message = b"offline-test-only-roundtrip"
    signature = ed25519.sign(message, seed)
    assert ed25519.verify(ed25519.public_key(seed), message, signature) is True
    assert ed25519.verify(ed25519.public_key(seed), message + b"!", signature) is False


def test_a15_no_private_key_file_is_tracked_in_the_repository() -> None:
    suffixes = {".pem", ".p12", ".pfx", ".key"}
    candidates = [path for path in repo_files("src", "config", "scripts", "plugins",
                                              "docs", "tests")
                  if path.suffix in suffixes or path.name in {"id_rsa", "id_ed25519"}]
    assert candidates == []
