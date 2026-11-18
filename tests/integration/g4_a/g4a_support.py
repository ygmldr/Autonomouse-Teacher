"""TEST_ONLY fixtures for the G4-A trusted approval contract.

Everything here is synthetic: a ``TEST_ONLY_`` Ed25519 seed mints rehearsal
authorizations, all files live in a pytest temporary directory, and nothing
contacts a model, provider, network socket or real credential. The seed must
never be copied into the candidate stage, the repository or a review packet.
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
from typing import Mapping

from autoteacher_m0.security import ed25519
from autoteacher_m0.security.authorization import (
    BINDING_COMPONENTS,
    ApprovedRoute,
    BudgetLimits,
    ExpectedBindings,
    consume_execution_authorization,
    load_execution_authorization,
)
from autoteacher_m0.security.live_controller import TrustedLiveController

REPO_ROOT = Path(__file__).resolve().parents[3]

NOW = datetime(2026, 11, 18, 12, 0, 0, tzinfo=timezone.utc)
TEST_ONLY_SEED = bytes.fromhex("5a" * 32)
ROTATED_SEED = bytes.fromhex("6b" * 32)
UNREGISTERED_SEED = bytes.fromhex("7c" * 32)
KEY_ID = "TEST_ONLY_g4a_maintainer_1"
ROTATED_KEY_ID = "TEST_ONLY_g4a_maintainer_2"
ROUTE = {"route_id": "opencode-go", "provider": "opencode-go",
         "model": "deepseek-v4.1-flash"}
SCOPE = "g4a-synthetic-rehearsal"
BASE_BUDGET = {"scope": SCOPE, "per_call_cap_usd": "0.20",
               "total_cap_usd": "10.00", "max_calls": 50}
BASE_DEADLINE = {"total_seconds": 120, "max_steps": 8, "max_dispatch_attempts": 8}
RUN_EPOCH = "epoch-g4a-1"

# Complete runtime-relevant input closure for the G4-A contract. Each component
# hashes an explicit tracked-file inventory; external build artefacts (runtime
# binary, dependency tree, candidate stage) are declared synthetic placeholders
# until G4-B freezes the authoritative build manifest.
COMPONENT_FILES: dict[str, tuple[str, ...]] = {
    "trusted_controller": (
        "src/autoteacher_m0/bridge/controller.py",
        "src/autoteacher_m0/bridge/ipc_server.py",
        "src/autoteacher_m0/bridge/admission.py",
        "src/autoteacher_m0/bridge/attempts.py",
        "src/autoteacher_m0/bridge/protocol.py",
        "src/autoteacher_m0/bridge/broker_client.py",
    ),
    "trusted_broker": (
        "src/autoteacher_m0/accounting/broker.py",
        "src/autoteacher_m0/accounting/broker_usage.py",
        "src/autoteacher_m0/accounting/budget.py",
        "src/autoteacher_m0/accounting/call_identity.py",
        "src/autoteacher_m0/accounting/ledger.py",
        "src/autoteacher_m0/accounting/observation.py",
        "src/autoteacher_m0/accounting/pricing.py",
        "src/autoteacher_m0/accounting/usage.py",
    ),
    "egress_boundary": (
        "src/autoteacher_m0/security/egress.py",
        "config/dsh/target-broker-policy.json",
    ),
    "candidate_adapter": (
        "src/autoteacher_m0/runtime/dsh_adapter.py",
        "src/autoteacher_m0/cli.py",
    ),
    "security_primitives": (
        "src/autoteacher_m0/security/__init__.py",
        "src/autoteacher_m0/security/authorization.py",
        "src/autoteacher_m0/security/credential_boundary.py",
        "src/autoteacher_m0/security/ed25519.py",
        "src/autoteacher_m0/security/gates.py",
        "src/autoteacher_m0/security/live_controller.py",
        "src/autoteacher_m0/security/watchdog.py",
    ),
    "dependency_lock": (
        "pyproject.toml",
        "uv.lock",
    ),
    "plugin_tree": (
        "plugins/offline-fixture/cordis.patch.yml",
        "plugins/offline-fixture/package-lock.json",
        "plugins/offline-fixture/package.json",
        "plugins/offline-fixture/src/index.ts",
        "plugins/offline-fixture/tsconfig.json",
        "plugins/runtime-budget-guard/package-lock.json",
        "plugins/runtime-budget-guard/package.json",
        "plugins/runtime-budget-guard/src/index.ts",
        "plugins/runtime-budget-guard/tsconfig.json",
        "plugins/skill-lookup/cordis.patch.yml",
        "plugins/skill-lookup/package-lock.json",
        "plugins/skill-lookup/package.json",
        "plugins/skill-lookup/src/index.ts",
        "plugins/skill-lookup/tsconfig.json",
    ),
    "tool_registry_schema": (
        "config/dsh/target-runtime.patch.yml",
    ),
    "merged_profile": (
        "config/dsh/sdk-minimal.patch.yml",
        "config/dsh/target-runtime.patch.yml",
        "config/dsh/target-runtime-opencode-go.patch.yml",
    ),
    "route_policy": (
        "config/dsh/target-runtime-opencode-go.patch.yml",
        "src/autoteacher_m0/settings.py",
    ),
    "budget_policy": (
        "config/budgets.yaml",
    ),
    "price_snapshot": (
        "config/models.example.yaml",
    ),
}
SYNTHETIC_COMPONENTS = ("candidate_stage", "runtime_binary", "runtime_dependencies")
assert set(COMPONENT_FILES) | set(SYNTHETIC_COMPONENTS) == set(BINDING_COMPONENTS)


def synthetic_component(name: str) -> str:
    """Declared TEST_ONLY stand-in for an external build artefact digest."""
    return hashlib.sha256(f"TEST_ONLY:{name}:v1".encode("utf-8")).hexdigest()


def canonical(payload: object) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("utf-8")


def component_digests(root: Path) -> dict[str, str]:
    """Recompute every closure component from one repository mirror."""
    from autoteacher_m0.security.authorization import inventory_digest

    digests: dict[str, str] = {}
    for component, relatives in COMPONENT_FILES.items():
        files = {relative: (root / relative).read_bytes() for relative in relatives}
        digests[component] = inventory_digest(files)
    for component in SYNTHETIC_COMPONENTS:
        digests[component] = synthetic_component(component)
    return digests


def base_payload(bindings: Mapping[str, str]) -> dict:
    return {
        "schema": "at-m0/execution-authorization/v1",
        "authorization_id": "auth-g4a-synthetic-1",
        "approver": "TEST_ONLY maintainer@example.invalid",
        "approval_note": "TEST_ONLY synthetic G4-A rehearsal; no key, no model, no dispatch",
        "issued_utc": "2026-11-18T11:50:00Z",
        "not_before_utc": "2026-11-18T11:55:00Z",
        "expires_utc": "2026-11-18T12:30:00Z",
        "bindings": dict(bindings),
        "route": dict(ROUTE),
        "allowed_tools": ["skill_lookup"],
        "budget": dict(BASE_BUDGET),
        "deadline": dict(BASE_DEADLINE),
    }


class TrustedFixture:
    """Repo mirror + repo-external trusted files + candidate stage, all synthetic."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.repo = root / "repo"
        self.trusted = root / "trusted"
        self.stage = root / "stage"
        self.use_log = root / "use-log"
        for directory in (self.repo, self.trusted, self.stage, self.use_log):
            directory.mkdir()
        self.mirror_repo()
        self.components = component_digests(self.repo)
        self.bindings = ExpectedBindings.from_closure(self.components)
        self.keys = self.trusted / "trusted-keys.json"
        self.revocations = self.trusted / "revocations.json"
        self.authorization = self.trusted / "authorization.json"
        self.set_keys({KEY_ID: ed25519.public_key(TEST_ONLY_SEED).hex()})
        self.set_revocations([])
        self.payload = base_payload(self.bindings.as_dict())
        self.write_signed(self.payload)

    # -- repository mirror -------------------------------------------------
    @staticmethod
    def _mirror_files() -> tuple[str, ...]:
        relatives: list[str] = []
        for entries in COMPONENT_FILES.values():
            relatives.extend(entries)
        return tuple(dict.fromkeys(relatives))

    def mirror_repo(self) -> None:
        for relative in self._mirror_files():
            source = REPO_ROOT / relative
            target = self.repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)

    @property
    def component_roots(self) -> dict[str, str]:
        return dict(self.bindings.as_dict())

    def recompute(self) -> ExpectedBindings:
        self.components = component_digests(self.repo)
        return ExpectedBindings.from_closure(self.components)

    def compute_now(self) -> ExpectedBindings:
        return ExpectedBindings.from_closure(component_digests(self.repo))

    def rewrite(self, relative: str, content: bytes) -> None:
        target = self.repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

    # -- trusted files -----------------------------------------------------
    def set_keys(self, keys: Mapping[str, str]) -> None:
        self.keys.write_text(json.dumps({"schema": "at-m0/trusted-approver-keys/v1",
                                         "keys": dict(keys)}), encoding="utf-8")

    def set_revocations(self, revoked_ids: list[str]) -> None:
        self.revocations.write_text(json.dumps(
            {"schema": "at-m0/revocation/v1", "revoked_ids": list(revoked_ids)}),
            encoding="utf-8")

    def sign(self, payload: Mapping[str, object], *, seed: bytes = TEST_ONLY_SEED,
             key_id: str = KEY_ID) -> dict:
        signed = copy.deepcopy(dict(payload))
        signed["signature"] = {"algorithm": "ed25519", "key_id": key_id,
                               "value": ed25519.sign(canonical(payload), seed).hex()}
        return signed

    def write_signed(self, payload: Mapping[str, object] | None = None, *,
                     seed: bytes = TEST_ONLY_SEED, key_id: str = KEY_ID) -> None:
        target = payload if payload is not None else self.payload
        self.authorization.write_text(json.dumps(self.sign(target, seed=seed, key_id=key_id)),
                                      encoding="utf-8")

    def write_raw(self, content: str | bytes) -> None:
        if isinstance(content, bytes):
            self.authorization.write_bytes(content)
        else:
            self.authorization.write_text(content, encoding="utf-8")

    def applied_payload(self) -> dict:
        return json.loads(self.authorization.read_text(encoding="utf-8"))

    # -- verification entry points ----------------------------------------
    def load_kwargs(self, *, now: datetime = NOW, actual_tools: tuple[str, ...] = ("skill_lookup",),
                    expected: ExpectedBindings | None = None,
                    route: ApprovedRoute | None = None, scope: str = SCOPE,
                    observed: ExpectedBindings | None = None,
                    authorization: Path | None = None, keys: Path | None = None,
                    revocations: Path | None = None, repo_root: Path | None = None) -> dict:
        return {
            "authorization_path": authorization or self.authorization,
            "trusted_keys_path": keys or self.keys,
            "revocation_path": revocations or self.revocations,
            "repo_root": repo_root or self.repo,
            "expected": expected or self.bindings,
            "approved_route": route or ApprovedRoute(**ROUTE),
            "actual_tools": actual_tools,
            "budget_scope": scope,
            "observed": observed,
            "now": now,
        }

    def load(self, **kwargs):
        return load_execution_authorization(**self.load_kwargs(**kwargs))

    def consume(self, *, run_epoch: str = RUN_EPOCH, now: datetime = NOW,
                use_log_dir: Path | None = None, **kwargs):
        load_kwargs = self.load_kwargs(now=now, **kwargs)
        return consume_execution_authorization(use_log_dir=use_log_dir or self.use_log,
                                               run_epoch=run_epoch, **load_kwargs)

    def controller(self, *, expected_budget: BudgetLimits | None = None,
                   egress=None, repo_root: Path | None = None,
                   authorization: Path | None = None, keys: Path | None = None,
                   revocations: Path | None = None, route: ApprovedRoute | None = None,
                   tools: tuple[str, ...] = ("skill_lookup",),
                   candidate_stage: Path | None = None) -> TrustedLiveController:
        kwargs = {
            "repo_root": repo_root or self.repo,
            "authorization_path": authorization or self.authorization,
            "trusted_keys_path": keys or self.keys,
            "revocation_path": revocations or self.revocations,
            "expected": self.bindings,
            "approved_route": route or ApprovedRoute(**ROUTE),
            "actual_tools": tools,
            "budget_scope": SCOPE,
            "candidate_stage": candidate_stage or self.stage,
        }
        if expected_budget is not None:
            kwargs["expected_budget"] = expected_budget
        if egress is not None:
            kwargs["egress"] = egress
        return TrustedLiveController(**kwargs)

    # -- use-log helpers ---------------------------------------------------
    def record_path(self, authorization_id: str) -> Path:
        digest = hashlib.sha256(authorization_id.encode("ascii")).hexdigest()
        return self.use_log / (digest + ".json")

    def use_records(self) -> list[Path]:
        return sorted(path for path in self.use_log.iterdir() if path.is_file())


def clean_subprocess_env() -> dict[str, str]:
    """Minimal environment for CLI/script negatives: no key-like or proxy variables."""
    import sys

    pythonpath = os.pathsep.join(entry for entry in sys.path if entry)
    return {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": str(REPO_ROOT),
            "LANG": "C", "PYTHONPATH": pythonpath,
            "PYTHONDONTWRITEBYTECODE": "1"}
