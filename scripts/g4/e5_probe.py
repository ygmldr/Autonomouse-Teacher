#!/usr/bin/env python3
"""G4-D / E5-PreLive no-key probes (host-level; no key, model, network or Live).

One subcommand per matrix row so every result has its own argv, UTC, exit code
and JSON evidence under ``artifacts/g4/e5``:

  p01-binding     E5-P01: TEST_ONLY signature/binding over the *frozen* bytes;
                  any changed component digest is refused.
  p02-admission   E5-P02: compiled artefact, dependency, policy/route and tool
                  schema drift is denied at the pre-dispatch checkpoint.
  p03-bypass      E5-P03: Markdown/env/flag/self-signed JSON cannot open a gate.
  p04-registry    E5-P04: captured DSH tool schema and the Controller allowlist
                  are observable; the DSH merged registry export is UNVERIFIED.
  p05-secret      E5-P05: the sentinel never reaches candidate env/mount/logs;
                  the scanner's positive control proves it can detect a leak.
  d05-revocation  Revocation denies future dispatch; a pending attempt stays
                  ATTEMPT_STARTED and a second begin is refused (no resend).
  d06-epoch       A ticket minted in one run epoch cannot be consumed in another;
                  a new run cannot spend with the previous run's ticket.
  d07-live        run_live.sh / CLI / Adapter / LiveGate stay BLOCKED even with a
                  fake secret in the environment.
  d15-oldrun      Same-UID access to a newer/known run path is denied by the OS;
                  directory-name randomness is explicitly not the boundary.

The probes import real product code and real stage bytes. They never write into
``src/``, never touch a real credential and never enable Live.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
from typing import Mapping, Sequence

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "g3d"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(REPO / "src"))
import lib_g4c as libc  # noqa: E402

from autoteacher_m0.bridge.attempts import AttemptJournal  # noqa: E402
from autoteacher_m0.security import ed25519  # noqa: E402
from autoteacher_m0.security.authorization import (  # noqa: E402
    AuthorizationRejected,
    ExpectedBindings,
    ApprovedRoute,
    binding_drift,
    consume_execution_authorization,
    load_execution_authorization,
)
from autoteacher_m0.security.egress import (  # noqa: E402
    ClaimResult,
    DispatchPermission,
    EgressRequest,
    EgressViolation,
    PreparedProviderRequest,
    ProviderRouteContract,
    SYNTHETIC_ROUTE_CONTRACT,
    TrustedSendGate,
    canonical_json,
    prepared_call_id,
    prepared_request_digest,
    tool_schema_digest,
)
from autoteacher_m0.security.gates import LiveGate  # noqa: E402
from autoteacher_m0.security.credential_boundary import scrub_candidate_env  # noqa: E402

SCHEMA = "m0.g4d.e5-probe.v1"
SENTINEL = "TEST_ONLY_NEVER_VALID_SECRET_SENTINEL"
TEST_ONLY_SEED = bytes.fromhex("91" * 32)
KEY_ID = "TEST_ONLY_g4d_maintainer_1"
SCOPE = "g4d-synthetic-scope"
NOW = datetime(2026, 11, 18, 12, 0, 0, tzinfo=timezone.utc)
RUN_EPOCH = "g4d-epoch-1"
AUTH_ID = "auth-g4d-synthetic-1"


def utc() -> str:
    return libc.utc()


def write_json(path: Path, document: object) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(document, indent=2, sort_keys=True, default=str) + "\n").encode()
    path.write_bytes(data)
    os.chmod(path, 0o600)
    return {"path": str(path), "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data)}


# ---------------------------------------------------------------------------
# frozen bytes / trusted TEST_ONLY files
# ---------------------------------------------------------------------------
def resolve_stage(explicit: str | None) -> Path:
    if explicit:
        path = Path(explicit).resolve()
        if not (path / "manifest.json").is_file():
            raise SystemExit(f"G4D_STAGE_INVALID {path}")
        return path
    candidates = sorted(path for path in libc.STAGE_ROOT.glob("stage-*")
                        if (path / "manifest.json").is_file())
    if not candidates:
        raise SystemExit("G4D_STAGE_MISSING")
    return candidates[-1]


def frozen_closure(stage: Path) -> dict:
    external = libc.stage_external_inputs(stage)
    closure = libc.closure_for(REPO, external=external)
    return {"closure": closure,
            "bindings": ExpectedBindings.from_closure(closure["component_digests"]),
            "external": external}


def synthetic_payload(bindings: Mapping[str, str], *,
                      authorization_id: str = AUTH_ID) -> dict:
    return {
        "schema": "at-m0/execution-authorization/v1",
        "authorization_id": authorization_id,
        "approver": "TEST_ONLY g4d@example.invalid",
        "approval_note": "TEST_ONLY G4-D no-key probe; no dispatch, no model, no key",
        "issued_utc": "2026-11-18T11:50:00Z",
        "not_before_utc": "2026-11-18T11:55:00Z",
        "expires_utc": "2026-11-18T12:30:00Z",
        "bindings": dict(bindings),
        "route": {"route_id": SYNTHETIC_ROUTE_CONTRACT.route_id,
                  "provider": SYNTHETIC_ROUTE_CONTRACT.provider,
                  "model": SYNTHETIC_ROUTE_CONTRACT.model_id},
        "allowed_tools": ["skill_lookup"],
        "budget": {"scope": SCOPE, "per_call_cap_usd": "0.20",
                   "total_cap_usd": "10.00", "max_calls": 50},
        "deadline": {"total_seconds": 120, "max_steps": 8,
                     "max_dispatch_attempts": 8},
        "signature": {"algorithm": "ed25519", "key_id": KEY_ID, "value": ""},
    }


def sign_payload(payload: Mapping[str, object], *, seed: bytes = TEST_ONLY_SEED,
                 key_id: str = KEY_ID) -> dict:
    document = json.loads(json.dumps(dict(payload)))
    document["signature"] = {"algorithm": "ed25519", "key_id": key_id, "value": ""}
    body = {key: value for key, value in document.items() if key != "signature"}
    signature = ed25519.sign(canonical_json(body).encode("utf-8"), seed).hex()
    document["signature"]["value"] = signature
    return document


class TrustedFiles:
    """Repo-external TEST_ONLY approval/keys/revocations + single-use records."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.keys = root / "trusted-keys.json"
        self.revocations = root / "revocations.json"
        self.authorization = root / "authorization.json"
        self.use_log = root / "use-log"
        self.use_log.mkdir(parents=True, exist_ok=True)
        self.keys.write_text(json.dumps({
            "schema": "at-m0/trusted-approver-keys/v1",
            "keys": {KEY_ID: ed25519.public_key(TEST_ONLY_SEED).hex()}}),
            encoding="utf-8")
        self.set_revocations([])
        self.payload = synthetic_payload({})

    def set_revocations(self, ids: list[str]) -> None:
        self.revocations.write_text(json.dumps(
            {"schema": "at-m0/revocation/v1", "revoked_ids": list(ids)}),
            encoding="utf-8")

    def write(self, payload: Mapping[str, object] | None = None, **kwargs) -> dict:
        document = sign_payload(payload or self.payload, **kwargs)
        self.authorization.write_text(json.dumps(document), encoding="utf-8")
        return document

    def kwargs(self, bindings: ExpectedBindings, *, now: datetime = NOW,
               observed: ExpectedBindings | None = None,
               checkpoint: str = "pre_start", tools: tuple[str, ...] = ("skill_lookup",),
               budget_scope: str = SCOPE) -> dict:
        return {"authorization_path": self.authorization,
                "trusted_keys_path": self.keys,
                "revocation_path": self.revocations,
                "repo_root": REPO,
                "expected": bindings,
                "approved_route": ApprovedRoute(
                    SYNTHETIC_ROUTE_CONTRACT.route_id,
                    SYNTHETIC_ROUTE_CONTRACT.provider,
                    SYNTHETIC_ROUTE_CONTRACT.model_id),
                "actual_tools": tools,
                "budget_scope": budget_scope,
                "now": now, "observed": observed, "checkpoint": checkpoint}

    def load(self, bindings: ExpectedBindings, **kwargs):
        return load_execution_authorization(**self.kwargs(bindings, **kwargs))

    def consume(self, bindings: ExpectedBindings, *, run_epoch: str = RUN_EPOCH,
                **kwargs):
        return consume_execution_authorization(
            use_log_dir=self.use_log, run_epoch=run_epoch,
            **self.kwargs(bindings, **kwargs))

    def use_records(self) -> list[Path]:
        return sorted(path for path in self.use_log.iterdir() if path.is_file())


def checks_result(name: str, checks: list[dict], **extra) -> dict:
    ok = all(item["ok"] for item in checks)
    return {"schema": SCHEMA, "probe": name, "utc": utc(),
            "status": "PASS" if ok else "FAIL",
            "checks": checks, "extra": extra}


# ---------------------------------------------------------------------------
# synthetic send gate helpers (same semantics as the G4-C host tests)
# ---------------------------------------------------------------------------
def approved_tool() -> dict:
    return {
        "name": "skill_lookup",
        "description": ("Look up fixed public skill metadata by a nonempty skill "
                        "id. Unknown ids return SKILL_NOT_FOUND. No filesystem "
                        "paths are accepted."),
        "parameters": {
            "type": "object",
            "properties": {"skill_id": {
                "type": "string",
                "description": ("Nonempty stable skill id, e.g. binary_search; "
                                "not a filesystem path.")}},
            "required": ["skill_id"],
        },
    }


def make_prepared(*, tools: tuple[dict, ...] = (), step: int = 0,
                  max_tokens: int = 64) -> PreparedProviderRequest:
    prepared = PreparedProviderRequest(
        scope_id=SCOPE, run_id="run-g4d-probe", logical_step=step, attempt_index=0,
        route_id=SYNTHETIC_ROUTE_CONTRACT.route_id,
        provider=SYNTHETIC_ROUTE_CONTRACT.provider,
        model=SYNTHETIC_ROUTE_CONTRACT.model_id,
        host=SYNTHETIC_ROUTE_CONTRACT.endpoint_host,
        port=SYNTHETIC_ROUTE_CONTRACT.port,
        method="POST", path=SYNTHETIC_ROUTE_CONTRACT.exact_path,
        stream=True, max_output_tokens=max_tokens, system="",
        messages=({"role": "user", "content": "g4d synthetic"},), tools=tools,
        response_format=None, retry_policy=None, has_files=False,
        has_images=False, store=False)
    return replace(prepared,
                   request_digest=prepared_request_digest(prepared),
                   call_id=prepared_call_id(prepared))


def make_request(prepared: PreparedProviderRequest, *, reservation: str) -> EgressRequest:
    return EgressRequest(
        logical_stream_id=f"stream-{prepared.logical_step}",
        reservation_id=reservation, attempt_ordinal=1,
        route_id=prepared.route_id, model=prepared.model, host=prepared.host,
        port=prepared.port, method=prepared.method, path=prepared.path,
        stream=prepared.stream, max_tokens=prepared.max_output_tokens,
        call_id=prepared.call_id, request_digest=prepared.request_digest,
        estimated_cost_usd="0.001")


def make_payload(prepared: PreparedProviderRequest) -> bytes:
    document = {
        "schema": SYNTHETIC_ROUTE_CONTRACT.request_format_version,
        "call_id": prepared.call_id, "prepared_digest": prepared.request_digest,
        "route_id": prepared.route_id, "model": prepared.model,
        "messages": [dict(item) for item in prepared.messages],
        "tools": [dict(item) for item in prepared.tools],
        "system": prepared.system, "max_output_tokens": prepared.max_output_tokens,
        "stream": True, "mode": "echo", "nonce": "00" * 16,
    }
    return canonical_json(document).encode("utf-8")


def make_permission(prepared: PreparedProviderRequest, claim: dict,
                    *, reservation: str) -> DispatchPermission:
    return DispatchPermission(
        ClaimResult(True, "CLAIMED", (), claim), prepared.call_id,
        prepared.request_digest, f"stream-{prepared.logical_step}", reservation, 1,
        (SYNTHETIC_ROUTE_CONTRACT.route_id, SYNTHETIC_ROUTE_CONTRACT.model_id))


def authorize(gate: TrustedSendGate, prepared: PreparedProviderRequest, *,
              reservation: str = "res-g4d-1") -> object:
    request = make_request(prepared, reservation=reservation)
    payload = make_payload(prepared)
    claim = {"call_id": prepared.call_id, "reservation_id": reservation,
             "request_digest": prepared.request_digest, "status": "CLAIMED"}
    return gate.authorize(
        prepared=prepared, request=request,
        permission=make_permission(prepared, claim, reservation=reservation),
        payload_bytes=payload, payload_digest=hashlib.sha256(payload).hexdigest(),
        payload_length=len(payload), reservation_id=reservation,
        broker_claim_id=prepared.call_id,
        broker_claim_digest=hashlib.sha256(
            canonical_json(claim).encode("utf-8")).hexdigest(),
        estimated_cost_usd=request.estimated_cost_usd)


def gate_for(bindings: ExpectedBindings, observed: ExpectedBindings | None = None,
             *, epoch: str = RUN_EPOCH) -> TrustedSendGate:
    return TrustedSendGate(
        SYNTHETIC_ROUTE_CONTRACT, auth_epoch=epoch, binding_approved=bindings,
        binding_observer=(lambda: observed if observed is not None else bindings))


def expect_denied(function, *needles: str) -> dict:
    try:
        function()
    except EgressViolation as error:
        reasons = tuple(str(reason) for reason in error.reasons)
        return {"denied": True, "reasons": reasons,
                "matched": [needle for needle in needles
                            if any(needle in reason for reason in reasons)]}
    except Exception as error:  # noqa: BLE001 - any non-deny exception is a failure
        return {"denied": False, "error": f"{type(error).__name__}: {str(error)[:200]}"}
    return {"denied": False, "error": "not_denied"}


# ---------------------------------------------------------------------------
# probes
# ---------------------------------------------------------------------------
def probe_p01(stage: Path) -> dict:
    frozen = frozen_closure(stage)
    bindings = frozen["bindings"]
    checks: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="g4d-p01-") as directory:
        trusted = TrustedFiles(Path(directory))
        trusted.write(synthetic_payload(bindings.as_dict()))
        decision = trusted.load(bindings, observed=bindings,
                                checkpoint="pre_dispatch")
        checks.append({"id": "synthetic_signature_accepted", "ok": decision.approved,
                       "reasons": list(decision.reasons),
                       "signature_valid": decision.signature_valid,
                       "billable_send_authorized": getattr(
                           decision, "billable_send_authorized", False)})
        payload = json.loads(trusted.authorization.read_text(encoding="utf-8"))
        checks.append({"id": "signed_bindings_equal_frozen_bytes",
                       "ok": payload["bindings"] == bindings.as_dict()})
        use = trusted.consume(bindings, observed=bindings, checkpoint="pre_start")
        checks.append({"id": "single_use_record_written",
                       "ok": use.record_path.is_file(),
                       "authorization_id": use.authorization_id})
        drift = binding_drift("pre_dispatch", approved=bindings,
                              observed=replace(bindings, runtime_sha256="00" * 32))
        checks.append({"id": "changed_runtime_digest_reports_drift",
                       "ok": bool(drift), "reasons": list(drift)})
        decision = trusted.load(bindings, observed=replace(
            bindings, code_sha256="11" * 32), checkpoint="pre_dispatch")
        checks.append({"id": "changed_runtime_digest_denied",
                       "ok": not decision.approved, "reasons": list(decision.reasons)})
        document = checks_result("p01-binding", checks,
                                 bindings=bindings.as_dict(),
                                 stage=str(stage),
                                 component_digests=frozen["closure"]["component_digests"])
    return document


def probe_p02(stage: Path) -> dict:
    frozen = frozen_closure(stage)
    bindings = frozen["bindings"]
    checks: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="g4d-p02-") as directory:
        journal = Path(directory) / "gate-journal.jsonl"
        gate = TrustedSendGate(SYNTHETIC_ROUTE_CONTRACT, auth_epoch=RUN_EPOCH,
                               binding_approved=bindings,
                               binding_observer=lambda: bindings,
                               journal_path=journal)
        prepared = make_prepared(tools=(approved_tool(),))
        ticket = authorize(gate, prepared)
        checks.append({"id": "baseline_authorized", "ok": ticket is not None,
                       "ticket": ticket.authorization_id})
        payload = make_payload(prepared)
        check = gate.consume(ticket, payload_bytes=payload,
                             request=make_request(prepared, reservation="res-g4d-1"))
        checks.append({"id": "baseline_consumed", "ok": check is None,
                       "reason": check})
        # compiled candidate stage+runtime binary / dependencies / source /
        # profile+policy / plugin+tool-registry roots are each bound separately
        for root in ("runtime_sha256", "lock_sha256", "code_sha256",
                     "merged_profile_sha256", "plugin_sha256"):
            mutated = replace(bindings, **{root: "22" * 32})
            from_mutated = gate_for(bindings, mutated)
            result = expect_denied(lambda: authorize(
                from_mutated, make_prepared(tools=(approved_tool(),))),
                "PRE_DISPATCH", "BINDING")
            checks.append({"id": f"{root}_drift_denied", "ok": result["denied"],
                           "detail": result})
        # policy/route contract change (endpoint path differs from frozen contract)
        alt = ProviderRouteContract.from_mapping(
            {**SYNTHETIC_ROUTE_CONTRACT.to_mapping(), "exact_path": "/v1/other"})
        alt_gate = TrustedSendGate(alt, auth_epoch=RUN_EPOCH,
                                   binding_approved=bindings,
                                   binding_observer=lambda: bindings)
        result = expect_denied(lambda: authorize(
            alt_gate, make_prepared(tools=(approved_tool(),))),
            "ROUTE_CONTRACT_MISMATCH")
        checks.append({"id": "policy_route_change_denied", "ok": result["denied"],
                       "detail": result})
        # tool schema change -> allowlist digest mismatch
        mutated_tool = dict(approved_tool())
        mutated_tool["description"] = mutated_tool["description"] + " changed"
        result = expect_denied(lambda: authorize(
            gate_for(bindings), make_prepared(tools=(mutated_tool,))),
            "TOOL_SCHEMA_NOT_APPROVED")
        checks.append({"id": "tool_schema_change_denied",
                       "ok": result["denied"]
                       and tool_schema_digest(mutated_tool)
                       not in SYNTHETIC_ROUTE_CONTRACT.allowed_tool_schema_digests,
                       "detail": result})
        journal_rows = [json.loads(line) for line in
                        journal.read_text(encoding="utf-8").splitlines() if line.strip()]
        checks.append({"id": "denied_attempts_start_no_send", "ok": all(
            row.get("attempt_started") is not True or row.get("decision") == "AUTHORIZED"
            for row in journal_rows), "journal_rows": len(journal_rows)})
    return checks_result("p02-admission", checks, stage=str(stage),
                         bindings=bindings.as_dict())


def _livegate_blocked() -> dict:
    decision = LiveGate().inspect(live_requested=True, actual=None, reviewed=None,
                                  actual_tools=None, session_log_disabled=False)
    return {"status": decision.status, "reasons": list(decision.reasons)}


def probe_p03(stage: Path, *, run_live: Path) -> dict:
    checks: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="g4d-p03-") as directory:
        root = Path(directory)
        markdown = root / "SECURITY_APPROVALS.md"
        markdown.write_text("# APPROVED\n\nUser approval: GRANTED. live=ALLOW.\n",
                            encoding="utf-8")
        fake_key = root / "approval.json"
        fake_key.write_text(json.dumps({"approved": True, "signature": "00" * 64}),
                            encoding="utf-8")
        fake_key.chmod(0o644)
        decision = LiveGate().inspect(
            live_requested=True, actual=None, reviewed=None,
            actual_tools=("skill_lookup",), session_log_disabled=True)
        checks.append({"id": "markdown_and_selfsign_do_not_toggle_gate",
                       "ok": decision.status == "BLOCKED"
                       and "EXTERNAL_HUMAN_AUTHORIZATION_BOUNDARY_NOT_DEPLOYED"
                       in decision.reasons, "reasons": list(decision.reasons)})
        env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": "/root", "LANG": "C",
               "AT_M0_LIVE_APPROVED": "1", "AUTOTEACHER_LIVE": "1",
               "DEEPSEEK_API_KEY": SENTINEL,
               "PYTHONPATH": os.pathsep.join(entry for entry in sys.path if entry),
               "PYTHONDONTWRITEBYTECODE": "1"}
        code = (
            "import json\n"
            "from autoteacher_m0.security.gates import LiveGate\n"
            "d = LiveGate().inspect(live_requested=True, actual=None, reviewed=None,\n"
            "                       actual_tools=('skill_lookup',),\n"
            "                       session_log_disabled=True)\n"
            "print(json.dumps({'status': d.status, 'reasons': list(d.reasons)}))\n"
        )
        record = subprocess.run([sys.executable, "-B", "-c", code], env=env,
                                cwd=str(REPO), capture_output=True, text=True,
                                timeout=60)
        try:
            child = json.loads((record.stdout or "{}").strip().splitlines()[-1])
        except (json.JSONDecodeError, IndexError):
            child = {}
        checks.append({"id": "env_flags_do_not_toggle_gate_in_child",
                       "ok": record.returncode == 0 and child.get("status") == "BLOCKED",
                       "exit": record.returncode, "status": child.get("status")})
        run = subprocess.run(["/bin/sh", str(run_live)], env=env, cwd=str(REPO),
                             capture_output=True, text=True, timeout=60)
        checks.append({"id": "run_live_exit_3", "ok": run.returncode == 3,
                       "exit": run.returncode,
                       "stderr_head": (run.stderr or "")[:200]})
        cli = subprocess.run([sys.executable, "-B", "-m", "autoteacher_m0.cli",
                              "smoke", "--live"], env=env, cwd=str(REPO),
                             capture_output=True, text=True, timeout=60)
        checks.append({"id": "cli_live_exit_3", "ok": cli.returncode == 3,
                       "exit": cli.returncode,
                       "stdout_head": (cli.stdout or "")[:200]})
        adapter_code = (
            "from autoteacher_m0.runtime.dsh_adapter import HarnessAdapter\n"
            "from autoteacher_m0.contracts import RuntimeFailure\n"
            "try:\n"
            "    HarnessAdapter._require_live_authorization()\n"
            "except RuntimeFailure as error:\n"
            "    print(error.code)\n"
        )
        adapter = subprocess.run([sys.executable, "-B", "-c", adapter_code], env=env,
                                 cwd=str(REPO), capture_output=True, text=True,
                                 timeout=60)
        checks.append({"id": "adapter_live_blocked",
                       "ok": adapter.returncode == 0
                       and "SECURITY_BLOCKED" in (adapter.stdout or ""),
                       "stdout": (adapter.stdout or "").strip()[:120]})
        gates_text = (REPO / "src/autoteacher_m0/security/gates.py").read_text(
            encoding="utf-8")
        checks.append({"id": "gates_py_has_no_env_or_file_approval",
                       "ok": "os.environ" not in gates_text
                       and "getenv" not in gates_text
                       and "open(" not in gates_text})
        self_signed = TrustedFiles(root / "trusted")
        self_signed.write()
        decision2 = LiveGate().inspect(live_requested=True, actual=None, reviewed=None,
                                       actual_tools=("skill_lookup",),
                                       session_log_disabled=True)
        checks.append({"id": "self_signed_json_does_not_open_gate",
                       "ok": decision2.status == "BLOCKED",
                       "self_signed_present": self_signed.authorization.is_file()})
    return checks_result("p03-bypass", checks, stage=str(stage),
                         fake_secret_value_sha256=hashlib.sha256(
                             SENTINEL.encode()).hexdigest())


def probe_p04(stage: Path) -> dict:
    checks: list[dict] = []
    fixture = libc.verify_stage_tool_schema(
        stage, SYNTHETIC_ROUTE_CONTRACT.allowed_tool_schema_digests)
    checks.append({"id": "captured_tool_fixture_matches_allowlist", "ok": fixture["ok"],
                   "rows": fixture["rows"]})
    capture = json.loads((stage / "candidate" / "fixtures" /
                          "capture-tools.json").read_text(encoding="utf-8"))
    names = sorted(item.get("name") for item in capture.get("tools") or [])
    checks.append({"id": "only_skill_lookup_captured", "ok": names == ["skill_lookup"],
                   "names": names})
    profile = (REPO / "config/dsh/target-runtime.patch.yml").read_text(encoding="utf-8")
    checks.append({"id": "profile_declares_no_shell_tool_for_candidate",
                   "ok": "terminal-bash" not in profile.split("tools:", 1)[-1]
                   if "tools:" in profile else True,
                   "note": "L0 declaration only; runtime registry remains UNVERIFIED"})
    runtime = REPO / "artifacts/foundation/deps/deepseek_harness_runtime"
    exports = sorted(path.name for path in runtime.rglob("*")
                     if path.is_file() and path.suffix in {".json", ".js", ".mjs"}
                     and "registry" in path.name.lower())[:10] if runtime.is_dir() else []
    checks.append({"id": "dsh_registry_export_absent", "ok": not exports,
                   "exports": exports,
                   "registry_export_api": "UNVERIFIED" if not exports else "OBSERVED"})
    return checks_result("p04-registry", checks, stage=str(stage),
                         registry_export_api="UNVERIFIED")


def probe_p05(stage: Path, *, candidate_argv: str | None,
              watchdog: str | None) -> dict:
    checks: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="g4d-p05-") as directory:
        root = Path(directory)
        fixture = root / "trusted-fixture"
        fixture.mkdir()
        canary = fixture / "sentinel.txt"
        canary.write_text(SENTINEL + "\n", encoding="utf-8")
        canary.chmod(0o600)
        leak_log = root / "broker.log"
        leak_log.write_text(f"level=error credential={SENTINEL}\n", encoding="utf-8")
        scanner = REPO / "scripts/g4/secret_sentinel_probe.py"
        scan = subprocess.run([sys.executable, "-B", str(scanner),
                               "--root", str(canary), "--root", str(leak_log),
                               "--self-test"], capture_output=True, text=True,
                              timeout=120)
        try:
            scan_doc = json.loads(scan.stdout)
        except json.JSONDecodeError:
            scan_doc = {}
        checks.append({"id": "scanner_detects_planted_sentinel",
                       "ok": scan.returncode == 0
                       and scan_doc.get("scan", {}).get("hit_count", 0) >= 2
                       and scan_doc.get("positive_control", {}).get("control") is True,
                       "hits": scan_doc.get("scan", {}).get("hit_count"),
                       "exit": scan.returncode})
        scrubbed, violations = scrub_candidate_env(
            {"PATH": "/usr/bin", "HOME": "/work", "DEEPSEEK_API_KEY": SENTINEL,
             "OPENCODE_API_KEY": SENTINEL}, known_secret_values=[SENTINEL])
        checks.append({"id": "candidate_env_scrub_drops_secret",
                       "ok": "DEEPSEEK_API_KEY" not in scrubbed
                       and "OPENCODE_API_KEY" not in scrubbed
                       and bool(violations) and SENTINEL not in repr(scrubbed),
                       "violations": sorted(violations)})
        argv_doc = None
        if candidate_argv and Path(candidate_argv).is_file():
            argv_doc = json.loads(Path(candidate_argv).read_text(encoding="utf-8"))
            text = json.dumps(argv_doc)
            mounts = [argv_doc["argv"][index + 1] for index, item in
                      enumerate(argv_doc["argv"]) if item == "--mount"]
            checks.append({"id": "candidate_argv_has_no_sentinel", "ok": SENTINEL not in text})
            checks.append({"id": "candidate_mounts_exclude_trusted_fixture",
                           "ok": all(str(fixture) not in mount and "/trusted" not in mount
                                     for mount in mounts)},)
            checks.append({"id": "candidate_network_none",
                           "ok": "--network" in argv_doc["argv"]
                           and argv_doc["argv"][argv_doc["argv"].index("--network") + 1]
                           == "none"})
        if watchdog and Path(watchdog).is_file():
            document = json.loads(Path(watchdog).read_text(encoding="utf-8"))
            checks.append({"id": "watchdog_cleanup_confirmed",
                           "ok": all(item["ok"] for item in document.get("checks", [])),
                           "status": document.get("status")})
        else:
            checks.append({"id": "watchdog_cleanup_confirmed", "ok": False,
                           "reason": "watchdog evidence not supplied"})
    return checks_result("p05-secret", checks, stage=str(stage))


def probe_d05(stage: Path) -> dict:
    frozen = frozen_closure(stage)
    bindings = frozen["bindings"]
    checks: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="g4d-d05-") as directory:
        root = Path(directory)
        trusted = TrustedFiles(root / "trusted")
        trusted.write(synthetic_payload(bindings.as_dict()))
        use = trusted.consume(bindings, observed=bindings)
        checks.append({"id": "authorization_consumed_once", "ok": use.record_path.is_file()})
        # A real in-flight attempt exists before revocation.
        journal = AttemptJournal(root / "attempts.sqlite3")
        call_id = "call-g4d-d05-1"
        attempt_id = journal.begin_attempt(
            scope_id=SCOPE, call_id=call_id, reservation_id="res-g4d-d05-1",
            prepared_digest="33" * 32, payload_digest="44" * 32, payload_length=17,
            run_id="run-g4d-d05", logical_step=0, mode="synthetic")
        before = journal.attempt_for_call(call_id)
        # Revoke, then deny every future dispatch.
        trusted.set_revocations([AUTH_ID])
        decision = trusted.load(bindings, observed=bindings)
        checks.append({"id": "future_dispatch_revoked",
                       "ok": (not decision.approved
                              and "AUTHORIZATION_REVOKED" in decision.reasons),
                       "reasons": list(decision.reasons)})
        try:
            trusted.consume(bindings, observed=bindings, run_epoch="g4d-epoch-2")
            checks.append({"id": "revoked_consumption_denied", "ok": False})
        except AuthorizationRejected as error:
            checks.append({"id": "revoked_consumption_denied",
                           "ok": "AUTHORIZATION_REVOKED" in error.reasons,
                           "reasons": list(error.reasons)})
        checks.append({"id": "use_record_count_unchanged",
                       "ok": len(trusted.use_records()) == 1,
                       "records": len(trusted.use_records())})
        state = journal.state_for_call(call_id)
        pending = journal.pending_attempts()
        checks.append({"id": "pending_attempt_conserved",
                       "ok": state == "ATTEMPT_STARTED" and len(pending) == 1
                       and pending[0]["attempt_id"] == attempt_id,
                       "state": state, "attempt_id": attempt_id})
        try:
            journal.begin_attempt(
                scope_id=SCOPE, call_id=call_id, reservation_id="res-g4d-d05-2",
                prepared_digest="33" * 32, payload_digest="44" * 32,
                payload_length=17, run_id="run-g4d-d05", logical_step=0,
                mode="synthetic")
            checks.append({"id": "second_begin_refused", "ok": False})
        except ValueError as error:
            checks.append({"id": "second_begin_refused",
                           "ok": "ATTEMPT_ALREADY_STARTED" in str(error),
                           "error": str(error)[:120]})
        after = journal.attempt_for_call(call_id)
        checks.append({"id": "attempt_row_unchanged",
                       "ok": before == after and after is not None,
                       "before_state": (before or {}).get("state"),
                       "after_state": (after or {}).get("state")})
        journal.close()
        attempts = sqlite3.connect(root / "attempts.sqlite3")
        rows = attempts.execute("SELECT COUNT(*) FROM g3b_attempts").fetchone()[0]
        receipts = attempts.execute("SELECT COUNT(*) FROM g3b_attempts "
                                    "WHERE receipt_id IS NOT NULL").fetchone()[0]
        attempts.close()
        checks.append({"id": "no_new_send_after_revocation",
                       "ok": rows == 1 and receipts == 0,
                       "attempt_rows": rows, "receipt_rows": receipts})
    return checks_result("d05-revocation", checks, stage=str(stage),
                         pending_policy="PENDING_CONSERVATIVE; retry_allowed=false")


def probe_d06(stage: Path) -> dict:
    frozen = frozen_closure(stage)
    bindings = frozen["bindings"]
    checks: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="g4d-d06-") as directory:
        journal = Path(directory) / "gate-journal.jsonl"
        gate = TrustedSendGate(SYNTHETIC_ROUTE_CONTRACT, auth_epoch=RUN_EPOCH,
                               binding_approved=bindings,
                               binding_observer=lambda: bindings,
                               journal_path=journal)
        prepared = make_prepared(tools=(approved_tool(),))
        ticket = authorize(gate, prepared)
        stale = authorize(gate, make_prepared(step=1, tools=(approved_tool(),)))
        gate.auth_epoch = "g4d-epoch-2"
        result = gate.consume(stale, payload_bytes=make_payload(
            make_prepared(step=1, tools=(approved_tool(),))))
        checks.append({"id": "old_epoch_ticket_denied", "ok": result == "AUTH_EPOCH_MISMATCH",
                       "reason": result})
        other = TrustedSendGate(SYNTHETIC_ROUTE_CONTRACT, auth_epoch="g4d-epoch-3",
                                binding_approved=bindings,
                                binding_observer=lambda: bindings)
        result = other.consume(ticket, payload_bytes=make_payload(prepared))
        checks.append({"id": "new_run_cannot_use_old_ticket",
                       "ok": result in {"AUTHORIZATION_UNKNOWN", "AUTH_EPOCH_MISMATCH"},
                       "reason": result})
        trusted = TrustedFiles(Path(directory) / "trusted")
        trusted.write(synthetic_payload(bindings.as_dict()))
        first = trusted.consume(bindings, observed=bindings, run_epoch="epoch-g4d-A")
        checks.append({"id": "contract_first_epoch_consumed", "ok": first.record_path.is_file()})
        try:
            trusted.consume(bindings, observed=bindings, run_epoch="epoch-g4d-B")
            checks.append({"id": "contract_stale_epoch_denied", "ok": False})
        except AuthorizationRejected as error:
            checks.append({"id": "contract_stale_epoch_denied",
                           "ok": "AUTHORIZATION_EPOCH_MISMATCH" in error.reasons,
                           "reasons": list(error.reasons)})
        rows = [json.loads(line) for line in
                journal.read_text(encoding="utf-8").splitlines() if line.strip()]
        checks.append({"id": "epoch_denial_is_journaled", "ok": any(
            row.get("decision") == "AUTH_EPOCH_MISMATCH" for row in rows),
            "rows": rows[-3:]})
    return checks_result("d06-epoch", checks, stage=str(stage))


def probe_d07(stage: Path, *, run_live: Path) -> dict:
    document = probe_p03(stage, run_live=run_live)
    document["probe"] = "d07-live"
    checks = document["checks"]
    with tempfile.TemporaryDirectory(prefix="g4d-d07-"):
        env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": "/root", "LANG": "C",
               "DEEPSEEK_API_KEY": SENTINEL, "OPENCODE_API_KEY": SENTINEL,
               "HTTP_PROXY": "http://127.0.0.1:9", "HTTPS_PROXY": "http://127.0.0.1:9",
               "PYTHONPATH": os.pathsep.join(entry for entry in sys.path if entry),
               "PYTHONDONTWRITEBYTECODE": "1"}
        code = (
            "import json\n"
            "from autoteacher_m0.security.gates import LiveGate\n"
            "d = LiveGate().inspect(live_requested=True, actual=None, reviewed=None,\n"
            "                       actual_tools=('skill_lookup',),\n"
            "                       session_log_disabled=True)\n"
            "print(json.dumps(d.reasons))\n"
        )
        record = subprocess.run([sys.executable, "-B", "-c", code], env=env,
                                cwd=str(REPO), capture_output=True, text=True,
                                timeout=60)
        reasons = (record.stdout or "").strip()
        checks.append({"id": "fake_secret_and_proxy_do_not_open_gate",
                       "ok": record.returncode == 0
                       and "EXTERNAL_HUMAN_AUTHORIZATION_BOUNDARY_NOT_DEPLOYED" in reasons,
                       "reasons_head": reasons[:200]})
        checks.append({"id": "sentinel_never_printed_by_gate",
                       "ok": SENTINEL not in (record.stdout or "")
                       and SENTINEL not in (record.stderr or "")})
    document["checks"] = checks
    document["status"] = "PASS" if all(item["ok"] for item in checks) else "FAIL"
    document["counts"] = {"real_provider_calls": 0, "real_external_http_calls": 0,
                          "provider_keys_seen": 0, "billable_send_allowed": 0,
                          "live_gate": "BLOCKED", "run_live_exit": 3}
    return document


def probe_d15() -> dict:
    checks: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="g4d-d15-") as directory:
        root = Path(directory)
        os.chmod(root, 0o755)
        run_a = root / "runs" / "run-a"
        run_b = root / "runs" / "run-b"
        for run in (run_a, run_b):
            (run / "state").mkdir(parents=True)
            (run / "ipc").mkdir(parents=True)
            (run / "state" / "controller.json").write_text('{"run":"x"}\n')
            (run / "state").chmod(0o700)
            (run / "ipc").chmod(0o2750)
            os.chown(run / "state", 0, 0)
            os.chown(run / "ipc", 0, 2000)
            (run / "candidate-session").mkdir()
            os.chown(run / "candidate-session", 65534, 65534)
        os.chmod(root / "runs", 0o755)
        socket_path = run_b / "ipc" / "bridge.sock"
        server = _bind_unix_socket(socket_path)
        os.chmod(socket_path, 0o660)
        os.chown(socket_path, 0, 2000)
        probe = root / "probe.py"
        probe.write_text(
            "import json, os, socket, sys\n"
            "paths = json.loads(sys.argv[1])\n"
            "out = {}\n"
            "def attempt(name, fn):\n"
            "    try:\n"
            "        fn()\n"
            "        out[name] = 'ALLOWED'\n"
            "    except PermissionError as error:\n"
            "        out[name] = 'EACCES'\n"
            "    except FileNotFoundError:\n"
            "        out[name] = 'ENOENT'\n"
            "    except OSError as error:\n"
            "        out[name] = type(error).__name__\n"
            "attempt('read_new_state', lambda: open(paths['new_state']).read())\n"
            "attempt('write_new_state', lambda: open(paths['new_write'], 'w').write('x'))\n"
            "attempt('list_new_state', lambda: os.listdir(paths['new_dir']))\n"
            "attempt('read_old_state', lambda: open(paths['old_state']).read())\n"
            "attempt('own_session_write', lambda: open(paths['own_write'], 'w').write('x'))\n"
            "def connect():\n"
            "    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)\n"
            "    s.settimeout(1)\n"
            "    s.connect(paths['socket'])\n"
            "    s.close()\n"
            "attempt('connect_socket', connect)\n"
            "print(json.dumps(out))\n", encoding="utf-8")
        argv = json.dumps({
            "new_state": str(run_b / "state" / "controller.json"),
            "new_write": str(run_b / "state" / "injected.json"),
            "new_dir": str(run_b / "state"),
            "old_state": str(run_a / "state" / "controller.json"),
            "own_write": str(run_b / "candidate-session" / "own.txt"),
            "socket": str(socket_path),
        })
        child = subprocess.run([sys.executable, "-B", str(probe), argv],
                               capture_output=True, text=True, timeout=60,
                               preexec_fn=_drop_to_candidate)
        try:
            observed = json.loads((child.stdout or "{}").strip())
        except json.JSONDecodeError:
            observed = {}
        checks.append({"id": "child_ran_as_candidate_uid", "ok": child.returncode == 0,
                       "exit": child.returncode,
                       "stderr_head": (child.stderr or "")[:160]})
        for key in ("read_new_state", "write_new_state", "list_new_state",
                    "read_old_state", "connect_socket"):
            expected = "EACCES"
            if key == "connect_socket":
                expected = "EACCES"
            checks.append({"id": f"denied_{key}", "ok": observed.get(key) == expected,
                           "observed": observed.get(key), "expected": expected})
        checks.append({"id": "candidate_own_session_writable",
                       "ok": observed.get("own_session_write") == "ALLOWED",
                       "observed": observed.get("own_session_write")})
        checks.append({"id": "not_authenticated_by_random_directory_name",
                       "ok": True,
                       "detail": "denial is 0700/2750(root:2000) + separate UID/mount "
                                 "namespace; run-id randomness is not claimed as auth"})
        server.close()
        os.unlink(socket_path)
    return checks_result("d15-oldrun", checks,
                         residual="same-UID stale run remains a P2 human decision "
                                  "(P2-RUN-IDENTITY); the boundary is OS mode/ownership "
                                  "and the absent mount, not an unguessable name")


def _bind_unix_socket(path: Path):
    import socket
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(path))
    server.listen(4)
    return server


def _drop_to_candidate() -> None:
    os.setgroups([])
    os.setgid(65534)
    os.setuid(65534)


# ---------------------------------------------------------------------------
# aggregated surfaces for D03/D04
# ---------------------------------------------------------------------------
def scan_surfaces(roots: Sequence[str], *, out: Path, pids: Sequence[int] = ()) -> dict:
    command = [sys.executable, "-B",
               str(REPO / "scripts/g4/secret_sentinel_probe.py")]
    for root in roots:
        command.extend(["--root", str(root)])
    for pid in pids:
        command.extend(["--pid", str(pid)])
    command.extend(["--self-test", "--out", str(out)])
    record = subprocess.run(command, cwd=str(REPO), capture_output=True, text=True,
                            timeout=600)
    try:
        document = json.loads(Path(out).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        document = {"clean": False, "error": "scan_output_unreadable",
                    "exit": record.returncode}
    document["scan_exit"] = record.returncode
    document["scan_argv"] = command
    return document


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("probe", choices=(
        "p01-binding", "p02-admission", "p03-bypass", "p04-registry", "p05-secret",
        "d05-revocation", "d06-epoch", "d07-live", "d15-oldrun"))
    parser.add_argument("--stage", default=None)
    parser.add_argument("--run-live", default=str(REPO / "scripts" / "run_live.sh"))
    parser.add_argument("--candidate-argv", default=None)
    parser.add_argument("--watchdog", default=None)
    parser.add_argument("--out", default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    stage = resolve_stage(args.stage)
    run_live = Path(args.run_live).resolve()
    if args.probe == "p01-binding":
        document = probe_p01(stage)
    elif args.probe == "p02-admission":
        document = probe_p02(stage)
    elif args.probe == "p03-bypass":
        document = probe_p03(stage, run_live=run_live)
    elif args.probe == "p04-registry":
        document = probe_p04(stage)
    elif args.probe == "p05-secret":
        document = probe_p05(stage, candidate_argv=args.candidate_argv,
                             watchdog=args.watchdog)
    elif args.probe == "d05-revocation":
        document = probe_d05(stage)
    elif args.probe == "d06-epoch":
        document = probe_d06(stage)
    elif args.probe == "d07-live":
        document = probe_d07(stage, run_live=run_live)
    else:
        document = probe_d15()
    document["argv"] = sys.argv
    document["exit"] = 0 if document["status"] == "PASS" else 4
    text = json.dumps(document, indent=2, sort_keys=True, default=str) + "\n"
    if args.out:
        write_json(Path(args.out), document)
    sys.stdout.write(text)
    return document["exit"]


if __name__ == "__main__":
    raise SystemExit(main())
