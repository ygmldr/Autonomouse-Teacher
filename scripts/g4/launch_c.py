#!/usr/bin/env python3
"""G4-C dual-principal launcher (trusted Controller + real DSH / hold Candidate).

Reuses the G3-D run layout, UID maps, mount/security flags and evidence
collectors from ``scripts/g3d/lib_g3d.py`` and the ``Launcher`` helpers, but:

* preflight is bound to the **G4 implementation commit** (stage ``base_sha``),
  not the frozen G3-D ``4bd4803``; the G3-D launcher would reject G4-A/C ``src``
  changes by construction (``git diff cf40c6b -- src`` non-empty);
* the trusted container runs ``/g4c/trusted_entry.py`` (a run-dir copy of
  ``scripts/g4/stage/trusted_entry_g4c.py``) so the frozen stage entrypoint is
  untouched;
* a trusted-launcher-owned ``g4c-policy.json`` carries the synthetic route
  contract, budget, epoch and the 15-component binding closure; the trusted
  entry recomputes it and wires ``binding_drift("pre_dispatch")`` + the G4-C
  send gate;
* ``podman exec`` probes can drive the real Candidate principal in ``hold``
  mode, and the trusted Controller can be restarted on the same durable state
  for crash/replay cases.

Every container is removed at the end and ``podman ps -a`` is re-checked empty.
No Key, no model, no external HTTP, ``--network none`` throughout.
"""
from __future__ import annotations

import argparse
import json
import os
from decimal import Decimal
from pathlib import Path
import sqlite3
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "g3d"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib_g3d as lib3d  # noqa: E402
import launch as g3d_launch  # noqa: E402
import lib_g4 as lib  # noqa: E402
import lib_g4c as libc  # noqa: E402

# Process-local path rebinding only: never touch artifacts/g3d.
lib3d.G3D_ROOT = libc.G4C_ROOT

PROBE_MARKER = "G4C_PROBE "


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", default="c01")
    parser.add_argument("--sub", default="")
    parser.add_argument("--scenario", default="echo")
    parser.add_argument("--session", default="g4c-s1")
    parser.add_argument("--prompt", default=None)
    parser.add_argument("--stage", default=None)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--evidence-dir", default=None)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--ready-timeout", type=float, default=30.0)
    parser.add_argument("--stop-grace", type=float, default=5.0)
    parser.add_argument("--keep-run", action="store_true")
    parser.add_argument("--candidate-mode", default="dsh",
                        choices=("dsh", "hold"))
    parser.add_argument("--hold-seconds", type=int, default=600)
    parser.add_argument("--label", default=None)
    parser.add_argument("--crash-hook", default=None)
    parser.add_argument("--test-delay-hook", default=None,
                        help="G4-F5 test-only delay window (before_reserve / "
                             "after_reserve_before_send)")
    parser.add_argument("--test-delay-ms", type=int, default=None,
                        help="G4-F5 test-only delay in milliseconds")
    parser.add_argument("--revocation", action="store_true",
                        help="G4-F5: wire the synthetic run-authorization "
                             "revocation input")
    parser.add_argument("--pre-revoke", action="store_true",
                        help="G4-F5: write the revocation document before the "
                             "candidate starts")
    parser.add_argument("--watch-revocation", default=None,
                        choices=(None, "after_reserve", "in_flight"),
                        help="G4-F5: revoke during a real DSH request at the "
                             "named window")
    parser.add_argument("--max-calls", type=int, default=None,
                        help="G4-C synthetic admission override (test only)")
    parser.add_argument("--deadline-ms", type=int, default=None,
                        help="G4-C synthetic admission deadline override "
                             "(test only; 100..30000)")
    parser.add_argument("--steps", default=None,
                        help="comma-separated hold-mode steps: probes, restart, kill-broker")
    args = parser.parse_args(argv)
    if args.prompt is None:
        args.prompt = g3d_launch.scenario_prompt(args.scenario)
    return args


F5_DSH_CASES = frozenset({
    "revocation-pre-reserve", "revocation-post-reserve",
    "revocation-in-flight", "timeout-pre-send", "timeout-post-send",
    "crash-after-authorize", "crash-after-consume",
})


class G4CLauncher(g3d_launch.Launcher):
    def __init__(self, args: argparse.Namespace) -> None:
        super().__init__(args)
        self.crash_hook = args.crash_hook
        # G4-F5 added these launcher options.  Other G4 launchers (for example
        # ``run_g4_f4.py``) build their own argparse Namespace, so read them
        # defensively: a Namespace without the F5 options keeps the exact
        # pre-F5 behaviour, while the F5 runner's CLI still sets them.
        self.test_delay_hook = getattr(args, "test_delay_hook", None)
        self.test_delay_ms = getattr(args, "test_delay_ms", None)
        self.revocation_enabled = bool(getattr(args, "revocation", False))
        self.pre_revoke = bool(getattr(args, "pre_revoke", False))
        self.watch_revocation = getattr(args, "watch_revocation", None)
        self.dsh_revocation: dict | None = None
        self.revocations: list[dict] = []
        self.revocation_epoch: str | None = None
        self.restart_records: list[dict] = []
        self.g4c_policy: dict | None = None
        self.g4c_policy_sha256: str | None = None
        self.g4c_closure: dict | None = None
        self.g4c_bindings: dict | None = None

    # -- stage resolution ----------------------------------------------
    def _resolve_stage(self, explicit: str | None) -> Path:
        if explicit:
            path = Path(explicit).resolve()
            if not path.is_dir():
                raise lib3d.G3DError("stage directory missing",
                                     exit_code=lib3d.EXIT_STAGE_INVALID,
                                     detail={"stage": str(path)})
            return path
        candidates = sorted(
            path for path in libc.STAGE_ROOT.glob("stage-*")
            if path.is_dir() and (path / "manifest.json").is_file())
        if not candidates:
            raise lib3d.G3DError(
                "no G4-C stage found; run scripts/g4/build_stage_c.py first",
                exit_code=lib3d.EXIT_STAGE_INVALID)
        return candidates[-1]

    # -- preflight ------------------------------------------------------
    def preflight(self) -> None:
        self._ensure_evidence()
        problems: list[str] = []
        if os.geteuid() != 0:
            raise lib3d.G3DError("must run as host root",
                                 exit_code=lib3d.EXIT_BLOCKED_ENVIRONMENT)
        head = lib3d.git_text("rev-parse", "HEAD")
        status_entries = self._status_entries()
        allowed_dirty_prefixes = ("docs/", "scripts/g4/", "tests/integration/g4_c/")
        dirty_allowed = [row for row in status_entries
                         if row["path"].startswith(allowed_dirty_prefixes)]
        dirty_other = [row for row in status_entries
                       if not row["path"].startswith(allowed_dirty_prefixes)]
        if dirty_other:
            problems.append("unexpected_worktree_changes")
        base = head
        self._cleanup_rootfs_targets()
        canonical_pre = {
            "utc": lib.utc_now(),
            "rootfs": {"path": str(lib3d.ROOTFS),
                       "sha256": lib3d.sha256_tree(lib3d.ROOTFS),
                       "expected": lib3d.ROOTFS_CANON},
            "deps": {"path": str(lib3d.DEPS),
                     "sha256": lib3d.sha256_tree(lib3d.DEPS),
                     "expected": lib3d.DEPS_CANON},
        }
        canonical_pre["rootfs"]["ok"] = (canonical_pre["rootfs"]["sha256"]
                                         == lib3d.ROOTFS_CANON)
        canonical_pre["deps"]["ok"] = (canonical_pre["deps"]["sha256"]
                                       == lib3d.DEPS_CANON)
        if not canonical_pre["rootfs"]["ok"]:
            problems.append("rootfs_not_canonical")
        if not canonical_pre["deps"]["ok"]:
            problems.append("deps_not_canonical")
        stage_before = lib3d.sha256_tree(self.stage_dir)
        validation = libc.validate_stage_g4(self.stage_dir, base_sha=base,
                                            verify_git=True)
        if not validation["ok"]:
            problems.append("stage_manifest_invalid")
            self.record_error("STAGE_INVALID", "G4 stage validation failed",
                              problems=validation["problems"][:40])
        if validation.get("base_sha") != head:
            problems.append("stage_base_not_head")
        ps = self.cmd(["podman", "ps", "-a", "--format", "{{.Names}}"],
                      name="ps-preflight", timeout=30)
        running = [name for name in ps["stdout"].splitlines() if name.strip()]
        if running:
            problems.append("containers_present")
        livegate = self._livegate_record()
        if livegate.get("status") != "BLOCKED":
            problems.append("livegate_not_blocked")
        key_env = [name for name in os.environ
                   if any(marker in name.upper() for marker in lib3d.KEY_MARKERS)]
        if key_env:
            problems.append("key_like_env")
        self.records["canonical_pre"] = canonical_pre
        self.records["stage"] = {
            "path": str(self.stage_dir), "sha256": stage_before,
            "manifest_sha256": validation["manifest_sha256"],
            "base_sha": validation["base_sha"],
            "trusted_tree_sha256": validation["trusted_tree_sha256"],
            "candidate_tree_sha256": validation["candidate_tree_sha256"],
        }
        self.records["livegate"] = livegate
        git_info = {"utc": lib.utc_now(), "head": head, "base": base,
                    "status_entries": status_entries,
                    "allowed_dirty": dirty_allowed,
                    "unexpected_dirty": dirty_other,
                    "src_identical_to_head": True,
                    "stage_validation_ok": validation["ok"]}
        self.write_evidence_json("env/git.json", git_info)
        self.write_evidence_json("env/canonical-pre.json", canonical_pre)
        self.write_evidence_json("env/livegate.json", livegate)
        self.write_evidence_json("env/stage-validation.json", {
            key: value for key, value in validation.items() if key != "manifest"})
        lib3d.write_bytes_atomic(self.evidence / "env" / "stage-manifest.json",
                               (self.stage_dir / "manifest.json").read_bytes(),
                               mode=0o444)
        lib3d.write_bytes_atomic(self.evidence / "env" / "ps-preflight.txt",
                               ps["stdout"].encode(), mode=0o444)
        self.preflight_record = {"ok": not problems, "problems": problems,
                                 "utc": lib.utc_now(), "head": head}
        self.write_evidence_json("env/preflight.json", self.preflight_record)
        if problems:
            raise lib3d.G3DError("G4-C preflight failed",
                                 exit_code=lib3d.EXIT_PREFLIGHT_IDENTITY,
                                 detail={"problems": problems})

    @staticmethod
    def _cleanup_rootfs_targets() -> list[str]:
        """Remove only the empty mount-target dirs this G4-C run can create."""
        removed = []
        for name in ("g4c",):
            path = lib3d.ROOTFS / name
            try:
                if path.is_dir() and not path.is_symlink() and not any(path.iterdir()):
                    path.rmdir()
                    removed.append(name)
            except OSError:
                pass
        return removed

    @staticmethod
    def _status_entries() -> list[dict]:
        raw = lib3d.git_bytes("status", "--porcelain=v1", "-z", "-uall")
        parts = raw.split(b"\0")
        rows: list[dict] = []
        index = 0
        while index < len(parts):
            part = parts[index].decode("utf-8", "replace")
            index += 1
            if not part:
                continue
            xy, path = part[:2], part[3:]
            if xy and xy[0] in {"R", "C"}:
                index += 1
            rows.append({"xy": xy, "path": path})
        return rows

    def _livegate_record(self) -> dict:
        repo_src = str(libc.REPO / "src")
        if repo_src not in sys.path:
            sys.path.insert(0, repo_src)
        try:
            from autoteacher_m0.security.gates import LiveGate
            decision = LiveGate().inspect(live_requested=True)
            return {"status": decision.status,
                    "reasons": [str(reason) for reason in decision.reasons]}
        except BaseException as exc:  # noqa: BLE001 - preflight must record
            return {"status": "ERROR", "error": f"{type(exc).__name__}: {exc}"}

    # -- configs --------------------------------------------------------
    def write_configs(self) -> None:
        super().write_configs()
        if self.args.max_calls is not None:
            self._override_admission_max_calls(int(self.args.max_calls))
        # ``deadline_ms`` was added to the G4-C CLI after the G4-F2/F4 launcher
        # subclasses froze their own argparse Namespace; absent means "no
        # override", which is exactly the pre-existing G4-C behaviour.
        if getattr(self.args, "deadline_ms", None) is not None:
            self._override_admission_deadline(int(self.args.deadline_ms))
        contract = self._contract_mapping()
        external = libc.stage_external_inputs(self.stage_dir)
        closure = libc.closure_for(libc.REPO, external=external)
        approved = libc.expected_bindings(closure)
        fixture = libc.verify_stage_tool_schema(
            self.stage_dir, contract["allowed_tool_schema_digests"])
        if not fixture["ok"]:
            self.fail(lib3d.EXIT_STAGE_INVALID,
                      "stage tool fixture does not match the frozen contract",
                      fixture=fixture)
        epoch = f"g4c-{self.run_id}"
        if len(epoch) > 128:
            epoch = epoch[:120]
        revocation_policy = None
        if self.revocation_enabled:
            self.revocation_epoch = epoch
            revocation_policy = {
                "schema": "m0.g4c.revocation-policy.v1",
                "path": "/work/state/g4c-revocation.json",
                "authorization_id": epoch,
            }
        policy = libc.build_policy(contract=contract, closure=closure,
                                   approved=approved, auth_epoch=epoch,
                                   run_id=self.run_id,
                                   revocation=revocation_policy)
        if self.revocation_enabled:
            # Initial state: the synthetic run authorization is valid. The gate
            # re-reads this root-owned document at pre_reserve, pre_dispatch and
            # pre_send; every rewrite is recorded in the evidence index.
            self.write_revocation(revoked=self.pre_revoke,
                                  reason=("initial-pre-revoked" if self.pre_revoke
                                          else "initial"))
        policy_path = self.run_dir / "state" / "g4c-policy.json"
        record = libc.write_policy(policy_path, policy)
        self.g4c_policy = policy
        self.g4c_policy_sha256 = record["sha256"]
        self.g4c_closure = closure
        self.g4c_bindings = approved
        entry_dir = self.run_dir / "g4c-run"
        entry_dir.mkdir(mode=0o700, exist_ok=True)
        entry_target = entry_dir / "trusted_entry.py"
        entry_bytes = libc.TRUSTED_ENTRY.read_bytes()
        lib3d.write_bytes_atomic(entry_target, entry_bytes, mode=0o444,
                                 uid=0, gid=0)
        self.records["g4c"] = {
            "policy_sha256": record["sha256"],
            "policy_path": str(policy_path),
            "auth_epoch": epoch,
            "entry_sha256": libc.sha256_bytes(entry_bytes),
            "binding_approved": approved,
            "tool_fixture": fixture,
            "contract_route_id": contract["route_id"],
        }
        self.write_evidence_json("run/config-g4c-policy.json", policy)
        self.write_evidence_json("run/g4c-tool-fixture.json", fixture)

    def _contract_mapping(self) -> dict:
        repo_src = str(libc.REPO / "src")
        if repo_src not in sys.path:
            sys.path.insert(0, repo_src)
        from autoteacher_m0.security.egress import SYNTHETIC_ROUTE_CONTRACT
        mapping = SYNTHETIC_ROUTE_CONTRACT.to_mapping()
        stage_egress = (self.stage_dir / "trusted" / "src" / "autoteacher_m0" /
                        "security" / "egress.py")
        repo_egress = libc.REPO / "src" / "autoteacher_m0" / "security" / "egress.py"
        if libc.sha256_file(stage_egress) != libc.sha256_file(repo_egress):
            self.fail(lib3d.EXIT_STAGE_INVALID,
                      "stage egress.py differs from the running repository source")
        return mapping

    def write_revocation(self, *, revoked: bool, reason: str) -> dict:
        """Rewrite the synthetic run-authorization revocation document.

        This is a real root-owned state input read by the trusted gate; the
        document itself is not a fee/ledger authority and never mints a send.
        """
        if self.revocation_epoch is None:
            raise lib3d.G3DError("revocation is not enabled for this run")
        document = {
            "schema": "m0.g4c.revocation.v1",
            "authorization_id": self.revocation_epoch,
            "auth_epoch": self.revocation_epoch,
            "revoked": bool(revoked),
            "revoked_utc": lib.utc_now(),
            "reason": reason,
        }
        path = self.run_dir / "state" / "g4c-revocation.json"
        record = lib3d.write_json_atomic(path, document, mode=0o600, uid=0, gid=0)
        entry = {
            "utc": lib.utc_now(), "revoked": bool(revoked), "reason": reason,
            "sha256": record["sha256"], "bytes": record["bytes"],
            "path": str(path), "document": document,
        }
        self.revocations.append(entry)
        self.write_evidence_json(
            f"run/revocation-{len(self.revocations):02d}.json", entry)
        return entry

    def _revocation_path(self) -> Path:
        return self.run_dir / "state" / "g4c-revocation.json"

    def _revocation_is_revoked(self) -> bool:
        try:
            document = json.loads(self._revocation_path().read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        return document.get("revoked") is True

    def _start_dsh_revocation_watcher(self):
        """Revoke the synthetic authorization during a *real DSH* request.

        The watcher waits for the controller's post-Reserve marker (pre-send) or
        for the Fake receipt (post-wire), then writes the real revocation
        document from the host. No request bytes, no model and no network are
        involved; the DSH request is the ordinary synthetic-fixture turn.
        """
        if not self.watch_revocation:
            return None
        if not self.revocation_enabled:
            raise lib3d.G3DError("--watch-revocation requires --revocation")
        window = self.watch_revocation
        marker = self.run_dir / "state" / "g4f5-delay-marker.json"
        receipts = self.run_dir / "state" / "receipts"
        before = len(list(receipts.glob("rcpt-*.json"))) if receipts.is_dir() else 0

        def worker() -> None:
            try:
                def new_receipt():
                    if not receipts.is_dir():
                        return None
                    rows = sorted(receipts.glob("rcpt-*.json"))
                    return len(rows) if len(rows) > before else None
                if window == "after_reserve":
                    observed = self._wait_for(
                        lambda: marker.is_file() or None, timeout=90.0)
                else:
                    observed = self._wait_for(new_receipt, timeout=90.0)
                if not observed:
                    raise lib3d.G3DError(
                        f"DSH {window} window was not observed")
                record = self.write_revocation(
                    revoked=True, reason=f"dsh:{window}")
                self.dsh_revocation = {
                    "window": window, "observed": True,
                    "utc": lib.utc_now(), "revocation": record,
                    "container": self.candidate_name,
                }
                self.write_evidence_json("run/dsh-revocation.json",
                                         self.dsh_revocation)
            except BaseException as exc:  # noqa: BLE001 - evidence keeps failure
                self.record_error("DSH_REVOCATION_FAILED",
                                  f"{type(exc).__name__}: {exc}")

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        return thread

    def _override_admission_deadline(self, deadline_ms: int) -> None:
        if not 100 <= deadline_ms <= 30000:
            raise lib3d.G3DError("deadline_ms must be within 100..30000")
        path = self.run_dir / "state" / "admission.json"
        document = json.loads(path.read_text(encoding="utf-8"))
        document["limits"]["deadline_ms"] = deadline_ms
        record = lib3d.write_json_atomic(path, document, mode=0o400, uid=0, gid=0)
        self.records.setdefault("configs", {})["deadline_override"] = {
            "deadline_ms": deadline_ms, "sha256": record["sha256"],
            "reason": "G4-F5 synthetic deadline boundary test only"}
        lib3d.write_bytes_atomic(self.evidence / "run" / "config-admission.json",
                               lib3d.json_bytes(document), mode=0o444)

    def _override_admission_max_calls(self, max_calls: int) -> None:
        path = self.run_dir / "state" / "admission.json"
        document = json.loads(path.read_text(encoding="utf-8"))
        document["limits"]["max_calls"] = max_calls
        record = lib3d.write_json_atomic(path, document, mode=0o400, uid=0, gid=0)
        self.records.setdefault("configs", {})["admission_override"] = {
            "max_calls": max_calls, "sha256": record["sha256"],
            "reason": "G4-C synthetic budget boundary test only"}
        lib3d.write_bytes_atomic(self.evidence / "run" / "config-admission.json",
                               lib3d.json_bytes(document), mode=0o444)

    # -- trusted startup ------------------------------------------------
    def _start_trusted_instance(self, *, name: str, crash_hook: str | None,
                                key: str) -> dict:
        ready_path = self.run_dir / "state" / "ready"
        if key != "main" and ready_path.exists():
            ready_path.unlink()
        argv = libc.trusted_argv(
            podman="podman", rootfs=str(lib3d.ROOTFS),
            stage_trusted=str(self.stage_dir / "trusted"), deps=str(lib3d.DEPS),
            run_dir=str(self.run_dir), entry_dir=str(self.run_dir / "g4c-run"),
            name=name, crash_hook=crash_hook,
            test_delay_hook=self.test_delay_hook if key == "main" else None,
            test_delay_ms=self.test_delay_ms if key == "main" else None)
        problems = libc.trusted_argv_problems(
            argv, run_dir=str(self.run_dir), stage_dir=str(self.stage_dir / "trusted"))
        if problems:
            self.fail(lib3d.EXIT_STAGE_INVALID, "G4-C trusted argv invalid",
                      problems=problems)
        self._write_argv(f"trusted-{key}", argv)
        record = self.cmd(argv, name=f"podman-run-trusted-{key}", timeout=90)
        if record["exit"] != 0:
            self.fail(lib3d.EXIT_TRUSTED_START_FAILED,
                      "podman run for trusted failed",
                      exit=record["exit"], stderr=record["stderr"][-2000:])
        document = self.podman_inspect(name, label=f"inspect-trusted-{key}")
        if document is None or document["State"]["Status"] not in {"running", "created"}:
            self.fail(lib3d.EXIT_TRUSTED_START_FAILED,
                      "trusted container not running",
                      status=None if document is None else document["State"]["Status"])
        deadline = time.monotonic() + float(self.args.ready_timeout)
        ready_document = None
        ready_problems = ["ready_absent"]
        last_status = None
        while time.monotonic() < deadline:
            if ready_path.exists():
                try:
                    ready_raw = lib3d.read_regular_bytes(ready_path, max_bytes=1 << 14)
                    ready_document, ready_problems = libc.parse_ready_g4c(ready_raw)
                except (lib3d.G3DError, OSError) as exc:
                    ready_problems = [f"ready_unreadable:{type(exc).__name__}"]
                break
            last_status = self.podman_status(name)
            if last_status in {"exited", "stopped"}:
                break
            time.sleep(0.1)
        if ready_document is None:
            logs = self._container_logs(name, f"trusted-failure-{key}")
            self.fail(lib3d.EXIT_TRUSTED_START_FAILED,
                      "trusted ready file not observed before timeout",
                      ready_problems=ready_problems,
                      container_status=last_status or self.podman_status(name),
                      log_tail=logs[-3000:])
        document = self.podman_inspect(name, label=f"inspect-trusted-ready-{key}")
        assert document is not None
        pid = int(document["State"]["Pid"])
        socket_record = lib3d.lstat_record(self.run_dir / "ipc" / "bridge.sock")
        listening = lib3d.parse_proc_net_unix(pid)
        evaluation = lib3d.evaluate_ready(
            socket_record=socket_record, ready_document=ready_document,
            ready_problems=ready_problems, listening_entries=listening,
            container_running=document["State"]["Status"] == "running")
        if not lib3d.ready_allows_candidate(evaluation):
            logs = self._container_logs(name, f"trusted-failure-{key}")
            self.fail(lib3d.EXIT_TRUSTED_START_FAILED,
                      "trusted readiness gate failed",
                      evaluation=evaluation, log_tail=logs[-3000:])
        self.socket_records[f"{key}_before_candidate"] = socket_record
        self.write_evidence_json(f"socket-stat/{key}-before-candidate.json",
                                 socket_record)
        record_doc = {
            "schema": "m0.g4c.launcher.ready.v1",
            "utc": lib.utc_now(), "run_id": self.run_id, "instance": key,
            "trusted_container": name, "trusted_pid": pid,
            "ready": ready_document, "socket": socket_record,
            "evaluation": evaluation,
            "g4c_policy_sha256": self.g4c_policy_sha256,
        }
        self.write_evidence_json(f"run/{key}-launcher-ready.json", record_doc)
        self.runtime_identity[f"trusted-{key}"] = self._capture_identity(pid, "trusted")
        entry = {
            "name": name, "container_id": document.get("Id"), "pid": pid,
            "status": document["State"]["Status"], "argv": argv,
            "env_names": self._container_env_names(document),
            "network_mode": (document.get("HostConfig") or {}).get("NetworkMode"),
            "read_only": (document.get("HostConfig") or {}).get("ReadonlyRootfs"),
            "cap_drop": (document.get("HostConfig") or {}).get("CapDrop"),
            "security_opts": (document.get("HostConfig") or {}).get("SecurityOpt"),
        }
        self.write_evidence_json(f"run/inspect-trusted-{key}.json", document)
        return entry

    def start_trusted(self) -> None:
        self.records["trusted_utc_start"] = lib.utc_now()
        self.container_records["trusted"] = self._start_trusted_instance(
            name=self.trusted_name, crash_hook=self.crash_hook, key="main")

    def restart_trusted(self, *, reason: str) -> dict:
        """Recovery start with the *same* single-use admission.

        The Controller intentionally exits ``3`` (ADMISSION_REPLAYED) after its
        ``reconcile_on_startup`` pass; that pass is the recovery under test.
        No second serving instance is created, so the request replay that
        follows cannot send either a second Fake or a second Attempt.
        """
        name = self.trusted_name + "-r2"
        self.cmd(["podman", "rm", "-f", name], name="rm-stale-trusted-r2", timeout=60)
        # G4-F5: keep the *crashed/pre-restart* process's gate snapshot before
        # the recovery process overwrites /output/g4c-egress.json.
        pre_restart = self.run_dir / "evidence" / "g4c-egress.json"
        if pre_restart.is_file():
            lib3d.write_bytes_atomic(
                self.evidence / "run" / "g4c-egress-before-restart.json",
                lib3d.read_regular_bytes(pre_restart, max_bytes=8 << 20), mode=0o444)
        if self.revocation_enabled:
            self.write_revocation(revoked=self._revocation_is_revoked(),
                                  reason="before-restart")
        argv = libc.trusted_argv(
            podman="podman", rootfs=str(lib3d.ROOTFS),
            stage_trusted=str(self.stage_dir / "trusted"), deps=str(lib3d.DEPS),
            run_dir=str(self.run_dir), entry_dir=str(self.run_dir / "g4c-run"),
            name=name)
        problems = libc.trusted_argv_problems(
            argv, run_dir=str(self.run_dir), stage_dir=str(self.stage_dir / "trusted"))
        if problems:
            self.fail(lib3d.EXIT_STAGE_INVALID, "G4-C recovery argv invalid",
                      problems=problems)
        self._write_argv("trusted-recovery", argv)
        started = lib.utc_now()
        record = {"utc_start": started, "reason": reason, "container": name,
                  "argv": argv, "state": "starting"}
        self.restart_records.append(record)
        run = self.cmd(argv, name="podman-run-trusted-recovery", timeout=90)
        record["run_exit"] = run["exit"]
        if run["exit"] != 0:
            record["state"] = "run_failed"
            self.fail(lib3d.EXIT_TRUSTED_START_FAILED,
                      "recovery trusted podman run failed",
                      exit=run["exit"], stderr=run["stderr"][-2000:])
        wait = self.cmd(["podman", "wait", "--interval", "150ms", name],
                        name="podman-wait-trusted-recovery", timeout=120)
        if wait["timed_out"]:
            self.cmd(["podman", "kill", "-s", "KILL", name],
                     name="kill-trusted-recovery", timeout=30)
            self.cmd(["podman", "wait", "--interval", "150ms", name],
                     name="podman-wait-trusted-recovery-killed", timeout=30)
        document = self.podman_inspect(name, label="inspect-trusted-recovery")
        exit_code = None
        if document is not None:
            exit_code = int(document["State"].get("ExitCode", -1))
            record["status"] = document["State"].get("Status")
            record["finished_at"] = document["State"].get("FinishedAt")
            self.write_evidence_json("run/inspect-trusted-recovery.json", document)
        record["exit_code"] = exit_code
        record["admission_replayed_exit"] = exit_code == 3
        record["utc_end"] = lib.utc_now()
        record["state"] = "completed"
        logs = self._container_logs(name, "trusted-recovery-log")
        lib3d.write_bytes_atomic(self.evidence / "run" / "trusted-recovery.log",
                                 logs.encode(), mode=0o444)
        for source, target in (
                (self.run_dir / "evidence" / "g4c-egress.json",
                 "run/g4c-egress-recovery.json"),
                (self.run_dir / "evidence" / "trusted-modules.json",
                 "peercred/trusted-modules-recovery.json")):
            if source.is_file():
                lib3d.write_bytes_atomic(
                    self.evidence / target,
                    lib3d.read_regular_bytes(source, max_bytes=8 << 20),
                    mode=0o444)
        self.write_evidence_json("run/trusted-restart.json",
                                 {"restarts": self.restart_records})
        return record

    # -- candidate ------------------------------------------------------
    def start_candidate(self) -> None:
        mode = self.args.candidate_mode
        argv = lib3d.candidate_run_argv(
            podman="podman", rootfs=str(lib3d.ROOTFS),
            stage_candidate=str(self.stage_dir / "candidate"), deps=str(lib3d.DEPS),
            run_dir=str(self.run_dir), name=self.candidate_name,
            scenario=self.args.scenario, session=self.args.session,
            prompt=self.args.prompt, mode=mode,
            label=(self.args.label or self.case) if mode == "hold" else None,
            hold_seconds=int(self.args.hold_seconds))
        problems = lib3d.argv_contract_problems(
            argv, role="candidate", run_dir=str(self.run_dir),
            stage_dir=str(self.stage_dir / "candidate"))
        if problems:
            self.fail(lib3d.EXIT_STAGE_INVALID, "candidate argv violates contract",
                      problems=problems)
        self._write_argv("candidate", argv)
        self.records["candidate_utc_start"] = lib.utc_now()
        record = self.cmd(argv, name="podman-run-candidate", timeout=90)
        if record["exit"] != 0:
            self.fail(lib3d.EXIT_CANDIDATE_START_FAILED,
                      "podman run for candidate failed",
                      exit=record["exit"], stderr=record["stderr"][-2000:])
        document = self.podman_inspect(self.candidate_name, label="inspect-candidate")
        if document is None:
            self.fail(lib3d.EXIT_CANDIDATE_START_FAILED, "candidate inspect failed")
        pid = int(document["State"].get("Pid") or 0)
        if pid > 0:
            self.runtime_identity["candidate"] = self._capture_identity(pid, "candidate")
        self.container_records["candidate"] = {
            "name": self.candidate_name, "container_id": document.get("Id"),
            "pid": pid, "status": document["State"]["Status"], "argv": argv,
            "network_mode": (document.get("HostConfig") or {}).get("NetworkMode"),
            "read_only": (document.get("HostConfig") or {}).get("ReadonlyRootfs"),
            "uid_maps": (document.get("HostConfig") or {}).get("IDMappings"),
            "cap_drop": (document.get("HostConfig") or {}).get("CapDrop"),
        }
        self.write_evidence_json("run/inspect-candidate.json", document)
        if mode == "hold":
            self.records["candidate_hold"] = True
            self.records["candidate_exit_code"] = None
            return
        watcher = self._start_dsh_revocation_watcher()
        if document["State"]["Status"] == "running":
            wait_record = self.cmd(
                ["podman", "wait", "--interval", "200ms", self.candidate_name],
                name="podman-wait-candidate", timeout=float(self.args.timeout))
            if wait_record["timed_out"]:
                self.records["candidate_timeout"] = True
                self.record_error("CANDIDATE_TIMEOUT", "candidate exceeded timeout",
                                  timeout=self.args.timeout)
                self.cmd(["podman", "kill", "-s", "KILL", self.candidate_name],
                         name="kill-candidate-timeout", timeout=30)
                self.cmd(["podman", "wait", "--interval", "200ms",
                          self.candidate_name],
                         name="podman-wait-candidate-killed", timeout=30)
        if watcher is not None:
            watcher.join(timeout=60.0)
        final = self.podman_inspect(self.candidate_name, label="inspect-candidate-final")
        exit_code = None
        if final is not None:
            exit_code = int(final["State"].get("ExitCode", -1))
            self.container_records["candidate"].update({
                "status": final["State"]["Status"], "exit_code": exit_code,
                "finished_at": final["State"].get("FinishedAt")})
            self.write_evidence_json("run/inspect-candidate-final.json", final)
        self.records["candidate_exit_code"] = exit_code
        logs = self._container_logs(self.candidate_name, "candidate-log")
        lib3d.write_bytes_atomic(self.evidence / "run" / "candidate.log",
                               logs.encode(), mode=0o444)
        self._copy_candidate_evidence()

    # -- candidate-side probes -----------------------------------------
    def run_candidate_probe(self, phase: str, *, timeout: float = 20.0) -> dict:
        source = libc.PROBE_SOURCE.read_text(encoding="utf-8")
        argv = ["podman", "exec", self.candidate_name,
                "/opt/python/bin/python3.11", "-B", "-c", source, phase]
        record = self.cmd(argv, name=f"probe-{phase}", timeout=timeout)
        stdout = record.get("stdout") or ""
        stderr = record.get("stderr") or ""
        lib3d.write_bytes_atomic(self.evidence / "run" / f"probe-{phase}.log",
                               (stdout + stderr).encode(), mode=0o444)
        document = None
        for line in reversed(stdout.splitlines()):
            if line.startswith(PROBE_MARKER):
                try:
                    document = json.loads(line[len(PROBE_MARKER):])
                except json.JSONDecodeError:
                    document = None
                break
        if document is None:
            self.record_error("PROBE_OUTPUT_MISSING", f"phase {phase} produced no marker",
                              exit=record.get("exit"))
        else:
            self.write_evidence_json(f"traces/probe-{phase}.json", document)
        return {"phase": phase, "exit": record.get("exit"),
                "document": document, "stdout_tail": stdout[-2000:],
                "stderr_tail": stderr[-2000:]}

    # -- evidence collection -------------------------------------------
    def _copy_state_assets(self) -> None:
        super()._copy_state_assets()
        for name in ("g4c-policy.json", "g4c-send-journal.jsonl",
                     "dispatch-window.jsonl"):
            source = self.run_dir / "state" / name
            if not source.is_file():
                continue
            data = lib3d.read_regular_bytes(source, max_bytes=8 << 20)
            lib3d.write_bytes_atomic(self.evidence / "run" / name, data, mode=0o444)
            self.records.setdefault("g4c_assets", []).append(
                {"name": name, "sha256": lib3d.sha256_bytes(data), "bytes": len(data)})
        for name, target in (("g4c-binding-start.json", "traces/g4c-binding-start.json"),
                             ("g4c-egress.json", "run/g4c-egress.json")):
            source = self.run_dir / "evidence" / name
            if not source.is_file():
                continue
            data = lib3d.read_regular_bytes(source, max_bytes=4 << 20)
            lib3d.write_bytes_atomic(self.evidence / target, data, mode=0o444)

    def _analyse_logs(self) -> None:
        super()._analyse_logs()
        trusted_log = self.evidence / "run" / "trusted.log"
        text = trusted_log.read_text(encoding="utf-8", errors="replace") \
            if trusted_log.is_file() else ""
        markers = ("G4C_TRUSTED_START", "G4C_TRUSTED_READY", "G4C_TRUSTED_EXIT",
                   "G4C_TRUSTED_RESULT", "peer accepted", "bridge socket ready",
                   "Traceback", "G4C_POLICY")
        rows = [line for line in text.splitlines()
                if any(marker in line for marker in markers)]
        (self.evidence / "peercred" / "g4c-trusted-log-extract.txt").write_text(
            "\n".join(rows) + "\n", encoding="utf-8")

    def _modules_evidence(self) -> dict:
        path = self.evidence / "peercred" / "trusted-modules.json"
        if not path.is_file():
            return {"ok": False, "problems": ["module_evidence_missing"],
                    "modules": []}
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"ok": False, "problems": ["module_evidence_invalid"],
                    "modules": []}
        problems = []
        rows = []
        head = lib3d.git_text("rev-parse", "HEAD")
        for row in document.get("modules") or []:
            real = row.get("real_path") or ""
            relative = None
            if real.startswith("/project/"):
                relative = real[len("/project/"):]
            elif real.startswith("/project/src/"):
                relative = real[len("/project/"):]
            expected = None
            if relative and relative.startswith("src/"):
                try:
                    expected = lib3d.git_blob_sha256(head, relative)
                except lib3d.G3DError:
                    expected = None
            rows.append({"module": row.get("module"), "sha256": row.get("sha256"),
                         "expected_head_blob": expected,
                         "match": expected is not None
                         and expected == row.get("sha256")})
            if expected is None:
                problems.append(f"module_outside_src:{row.get('module')}")
            elif expected != row.get("sha256"):
                problems.append(f"module_sha_mismatch:{row.get('module')}")
        if not rows:
            problems.append("no_modules")
        return {"ok": not problems, "problems": problems, "modules": rows,
                "head": head}

    def _timing_rows(self) -> list[dict]:
        rows = []
        receipt_dir = self.evidence / "receipt"
        for path in sorted(receipt_dir.glob("timing-*.json")):
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            rows.append({"name": path.name, "marks": document.get("marks") or []})
        return rows

    # -- evaluation -----------------------------------------------------
    def evaluate(self) -> None:
        checks: list[dict] = []

        def check(check_id: str, ok: bool, **detail: object) -> None:
            checks.append({"id": check_id, "ok": bool(ok), **detail})

        snapshot = self._ledger_snapshot()
        receipts = snapshot["receipts"]
        counter = snapshot["fake_counter"]
        gate = self._gate_evidence()
        modules = self._modules_evidence()
        binding = self._read_json_evidence("traces/g4c-binding-start.json") or {}
        case = self.case
        check("modules_loaded_from_g4_head", modules["ok"], problems=modules["problems"])
        check("binding_start_evidence", bool(binding), keys=sorted(binding)[:10])
        check("fake_counter_matches_receipts",
              counter == len([r for r in receipts if r.get("receipt_id")]),
              counter=counter, receipts=len(receipts))
        if case in {"crash-before-send", "broker-down", "negatives"}:
            check("gate_no_authorization_before_crash", not gate["authorized"],
                  authorized=len(gate["authorized"]))
        elif case == "timeout-pre-send":
            check("gate_no_authorization_before_send", not gate["authorized"],
                  authorized=len(gate["authorized"]))
        else:
            check("gate_journal_present", gate["present"], path=gate["path"])
        if (self.args.candidate_mode == "dsh" and case in F5_DSH_CASES):
            self._evaluate_dsh_f5_case(check, snapshot, gate)
        elif case in {"c01", "c02"}:
            self._evaluate_dsh_case(check, snapshot, gate, modules)
        elif case == "negatives":
            self._evaluate_negative_case(check, snapshot, gate)
        elif case == "replay":
            self._evaluate_replay_case(check, snapshot, gate)
        elif case == "crash-before-send":
            self._evaluate_crash_case(check, snapshot, gate, expect_fake=0)
        elif case == "crash-after-receive":
            self._evaluate_crash_case(check, snapshot, gate, expect_fake=1)
        elif case == "broker-down":
            self._evaluate_broker_case(check, snapshot, gate)
        elif case == "quota":
            self._evaluate_quota_case(check, snapshot, gate)
        elif case == "c18":
            self._evaluate_stream_case(check, snapshot, gate)
        elif case in {"revocation-pre-reserve", "revocation-post-reserve",
                      "revocation-in-flight"}:
            self._evaluate_revocation_case(check, snapshot, gate)
        elif case == "timeout-pre-send":
            self._evaluate_timeout_pre_send(check, snapshot, gate)
        elif case == "timeout-post-send":
            self._evaluate_timeout_post_send(check, snapshot, gate)
        elif case in {"crash-after-authorize", "crash-after-consume"}:
            self._evaluate_ingress_crash_case(check, snapshot, gate)
        else:
            check("known_case", False, case=case)
        self.checks = checks
        self.write_evidence_json("checks/checks.json", {"checks": checks})
        if not all(item["ok"] for item in checks):
            if self.exit_code == lib3d.EXIT_OK:
                self.exit_code = lib3d.EXIT_CASE_FAILED
            self.failure = {"reason": "CHECK_FAILED",
                            "message": "one or more G4-C checks failed",
                            "detail": {"failed": [item["id"] for item in checks
                                                  if not item["ok"]]}}

    def _ledger_snapshot(self) -> dict:
        db_dir = self.evidence / "db"
        broker_path = db_dir / "broker.sqlite3"
        attempts_path = db_dir / "attempts.sqlite3"
        result: dict = {"reservations": [], "claims": [], "attempts": [],
                        "admissions": [], "intents": [], "identities": [],
                        "receipts": [], "fake_counter": None,
                        "integrity": {}}
        try:
            if broker_path.is_file():
                result["reservations"] = self._query(
                    broker_path,
                    "SELECT reservation_id,route_id,model,input_bound,output_bound,"
                    "status,input_used,output_used,cost,estimated,settlement_json "
                    "FROM budget_reservations ORDER BY rowid")
                result["claims"] = self._query(
                    broker_path,
                    "SELECT call_id,reservation_id,request_digest,status "
                    "FROM budget_dispatch_claims ORDER BY rowid")
                result["integrity"]["broker"] = self._query(
                    broker_path, "PRAGMA integrity_check")
            if attempts_path.is_file():
                result["attempts"] = self._query(
                    attempts_path,
                    "SELECT attempt_id,call_id,reservation_id,state,receipt_id,"
                    "reason,payload_digest,prepared_digest,run_id,logical_step,"
                    "input_bound_tokens,created_utc,updated_utc,settlement_json "
                    "FROM g3b_attempts ORDER BY created_utc, call_id")
                result["admissions"] = self._query(
                    attempts_path,
                    "SELECT admission_id,run_id,consumed_utc "
                    "FROM g3b_admissions ORDER BY consumed_utc")
                result["intents"] = self._query(
                    attempts_path,
                    "SELECT intent_id,call_id,reservation_id,state,reason "
                    "FROM g3b_send_intents ORDER BY created_utc")
                result["identities"] = self._query(
                    attempts_path,
                    "SELECT scope_id,identity_digest,call_id,logical_step "
                    "FROM g3b_request_identities ORDER BY created_utc")
                result["integrity"]["attempts"] = self._query(
                    attempts_path, "PRAGMA integrity_check")
        except sqlite3.Error as exc:
            self.record_error("DB_QUERY_FAILED", f"{type(exc).__name__}: {exc}")
        receipt_dir = self.evidence / "receipt"
        rows = []
        if receipt_dir.is_dir():
            for path in sorted(receipt_dir.glob("rcpt-*.json")):
                try:
                    document = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    rows.append({"name": path.name, "invalid": True})
                    continue
                rows.append({
                    "name": path.name, "sha256": lib3d.sha256_file(path),
                    "receipt_id": document.get("receipt_id"),
                    "raw_sha256": document.get("raw_sha256"),
                    "raw_length": document.get("raw_length"),
                    "nonce": document.get("nonce"),
                    "mode": document.get("mode"), "usage": document.get("usage"),
                    "utc_start": document.get("utc_start"),
                    "utc_end": document.get("utc_end"),
                    "synthetic": document.get("synthetic"),
                    "real_model_calls": document.get("real_model_calls"),
                    "http_calls": document.get("http_calls"),
                    "network_used": document.get("network_used"),
                })
        result["receipts"] = rows
        counter_path = receipt_dir / "received-count.json"
        if counter_path.is_file():
            try:
                result["fake_counter"] = json.loads(
                    counter_path.read_text(encoding="utf-8")).get("count")
            except (OSError, json.JSONDecodeError):
                result["fake_counter"] = None
        elif not rows:
            # The Fake writes the counter with its first receipt; no receipt
            # means the provider was never entered.
            result["fake_counter"] = 0
        self.write_evidence_json("db/snapshot.json", result)
        return result

    def _gate_evidence(self) -> dict:
        path = self.evidence / "run" / "g4c-send-journal.jsonl"
        result = {"present": path.is_file(), "path": str(path),
                  "authorized": [], "consumed": [], "denied": [],
                  "revocation": []}
        if path.is_file():
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    document = json.loads(line)
                except json.JSONDecodeError:
                    continue
                decision = document.get("decision")
                if decision in {"AUTHORIZED", "CONSUMED"}:
                    result[decision.lower()].append(document)
                elif decision == "REVOCATION_CHECK":
                    result["revocation"].append(document)
                else:
                    result["denied"].append(document)
        self.write_evidence_json("checks/gate-journal.json", result)
        return result

    def _evaluate_dsh_f5_case(self, check, snapshot, gate) -> None:
        """Real-DSH G4-F5 evidence: ledger + gate + recovery, no probes."""
        case = self.case
        result = self._read_json_evidence("traces/dsh-result.json") or {}
        reservations = snapshot["reservations"]
        claims = snapshot["claims"]
        attempts = snapshot["attempts"]
        receipts = snapshot["receipts"]
        dsh_failed = (result.get("error") is not None
                      or result.get("finish_reason") not in {None, "completed"})
        check("dsh_result_present", bool(result), keys=sorted(result)[:8])
        if case == "revocation-in-flight":
            check("dsh_request_completed", not dsh_failed,
                  error=result.get("error"),
                  finish_reason=result.get("finish_reason"),
                  response=result.get("final_response"))
        else:
            check("dsh_request_failed", dsh_failed,
                  error=result.get("error"),
                  finish_reason=result.get("finish_reason"),
                  response=result.get("final_response"))
        if case.startswith("revocation"):
            check("f5_dsh_revocation_enabled", self.revocation_enabled,
                  enabled=self.revocation_enabled)
        if case == "revocation-pre-reserve":
            check("dsh_revocation_pre_reserve_no_ledger",
                  not reservations and not claims and not attempts
                  and not snapshot["intents"] and not receipts
                  and snapshot["fake_counter"] == 0,
                  reservations=len(reservations), claims=len(claims),
                  attempts=len(attempts), receipts=len(receipts),
                  fake=snapshot["fake_counter"])
            check("dsh_revocation_pre_reserve_no_authorization",
                  not gate["authorized"] and self._revocation_pre_reserve_check(gate),
                  authorized=len(gate["authorized"]),
                  checks=len(gate["revocation"]))
            return
        if case in {"revocation-post-reserve", "crash-after-authorize",
                    "crash-after-consume"}:
            recovery = self._gate_snapshot("run/g4c-egress-recovery.json")
            check("dsh_post_reserve_pending_reservation",
                  len(reservations) == 1
                  and reservations[0].get("status") == "PENDING"
                  and self._money(reservations[0].get("cost")) > 0,
                  rows=[{key: row.get(key) for key in ("status", "cost")}
                        for row in reservations])
            check("dsh_post_reserve_durable_attempt",
                  len(attempts) == 1
                  and attempts[0].get("state") in {"SETTLEMENT_UNCERTAIN",
                                                   "ATTEMPT_STARTED"},
                  states=[row.get("state") for row in attempts])
            check("dsh_post_reserve_no_fake",
                  not receipts and snapshot["fake_counter"] == 0,
                  receipts=len(receipts), fake=snapshot["fake_counter"])
            check("dsh_post_reserve_recovery_held",
                  self._money(recovery.get("worst_case_held_usd")) > 0,
                  held=recovery.get("worst_case_held_usd"),
                  known=recovery.get("known_cost_usd"))
            check("dsh_post_reserve_single_claim", len(claims) == 1,
                  rows=len(claims))
            if case == "revocation-post-reserve":
                window = self._read_json_evidence("run/dsh-revocation.json") or {}
                check("dsh_revocation_mid_request",
                      window.get("window") == "after_reserve"
                      and bool((window.get("revocation") or {}).get("revoked")),
                      window=window.get("window"))
                check("dsh_revocation_gate_denial",
                      bool(self._revocation_denials(gate)))
            return
        if case == "revocation-in-flight":
            window = self._read_json_evidence("run/dsh-revocation.json") or {}
            check("dsh_in_flight_completed",
                  not dsh_failed and result.get("final_response") is not None,
                  response=result.get("final_response"))
            check("dsh_in_flight_single_settled",
                  len(reservations) == 1 and len(claims) == 1
                  and len(attempts) == 1
                  and attempts[0].get("state") == "SETTLED"
                  and snapshot["fake_counter"] == 1 and len(receipts) == 1,
                  reservations=len(reservations), claims=len(claims),
                  attempts=len(attempts), fake=snapshot["fake_counter"])
            check("dsh_in_flight_cost_not_free",
                  bool(reservations)
                  and self._money(reservations[0].get("cost")) > 0,
                  cost=reservations[0].get("cost") if reservations else None)
            check("dsh_in_flight_revocation_after_wire",
                  window.get("window") == "in_flight"
                  and bool((window.get("revocation") or {}).get("revoked")),
                  window=window.get("window"))
            return
        if case == "timeout-pre-send":
            marker = self.run_dir / "state" / "g4f5-delay-marker.json"
            check("dsh_timeout_pre_send_no_ledger",
                  not reservations and not claims and not attempts
                  and not receipts and snapshot["fake_counter"] == 0,
                  reservations=len(reservations), attempts=len(attempts),
                  receipts=len(receipts), fake=snapshot["fake_counter"])
            check("dsh_timeout_pre_send_no_authorization", not gate["authorized"],
                  authorized=len(gate["authorized"]))
            check("dsh_timeout_pre_send_real_delay", marker.is_file(),
                  marker=str(marker))
            return
        if case == "timeout-post-send":
            before = self._gate_snapshot("run/g4c-egress-before-restart.json")
            recovery = self._gate_snapshot("run/g4c-egress-recovery.json")
            check("dsh_timeout_post_send_fake_once",
                  snapshot["fake_counter"] == 1 and len(receipts) == 1,
                  fake=snapshot["fake_counter"], receipts=len(receipts))
            check("dsh_timeout_post_send_single_ledger",
                  len(reservations) == 1 and len(claims) == 1
                  and len(attempts) == 1,
                  reservations=len(reservations), claims=len(claims),
                  attempts=len(attempts))
            final = reservations[0] if reservations else {}
            check("dsh_timeout_post_send_not_free",
                  final.get("status") in {"PENDING", "OK", "FAILED"}
                  and (final.get("status") == "PENDING"
                       or self._money(final.get("cost")) > 0),
                  status=final.get("status"), cost=final.get("cost"))
            check("dsh_timeout_post_send_before_recovery_held",
                  self._money(before.get("worst_case_held_usd")) > 0,
                  held=before.get("worst_case_held_usd"),
                  known=before.get("known_cost_usd"))
            if recovery:
                check("dsh_timeout_post_send_recovery_not_free",
                      self._money(recovery.get("worst_case_held_usd")) > 0
                      or self._money(recovery.get("known_cost_usd")) > 0,
                      held=recovery.get("worst_case_held_usd"),
                      known=recovery.get("known_cost_usd"))
            else:
                check("dsh_timeout_post_send_gate_held",
                      self._money(gate.get("worst_case_held_usd")) > 0,
                      held=gate.get("worst_case_held_usd"))
            return
        check("known_f5_dsh_case", False, case=case)

    def _evaluate_dsh_case(self, check, snapshot, gate, modules) -> None:
        scenario = "tool" if self.case == "c02" else "echo"
        receipts = snapshot["receipts"]
        reservations = snapshot["reservations"]
        claims = snapshot["claims"]
        attempts = snapshot["attempts"]
        candidate_result = self._read_json_evidence("traces/dsh-result.json") or {}
        check("candidate_exit_zero", self.records.get("candidate_exit_code") == 0,
              exit=self.records.get("candidate_exit_code"))
        expected_calls = 2 if scenario == "tool" else 1
        check("reservation_count", len(reservations) == expected_calls
              and all(row["status"] == "OK" for row in reservations),
              rows=len(reservations))
        check("claim_count", len(claims) == expected_calls, rows=len(claims))
        check("attempt_count_settled",
              len(attempts) == expected_calls
              and all(row["state"] == "SETTLED" for row in attempts),
              states=[row["state"] for row in attempts])
        check("receipt_count", len(receipts) == expected_calls, rows=len(receipts))
        check("fake_counter", snapshot["fake_counter"] == expected_calls,
              counter=snapshot["fake_counter"])
        check("gate_authorized_count", len(gate["authorized"]) == expected_calls,
              rows=len(gate["authorized"]))
        check("gate_consumed_count", len(gate["consumed"]) == expected_calls,
              rows=len(gate["consumed"]))
        check("gate_no_denials", not gate["denied"], denials=gate["denied"][:2])
        pairs = []
        claim_by_call = {row["call_id"]: row for row in claims}
        reservation_by_id = {row["reservation_id"]: row for row in reservations}
        receipt_by_sha = {row["raw_sha256"]: row for row in receipts
                          if row.get("raw_sha256")}
        for attempt_row in attempts:
            claim = claim_by_call.get(attempt_row["call_id"])
            reservation = reservation_by_id.get(attempt_row["reservation_id"])
            receipt = receipt_by_sha.get(attempt_row["payload_digest"])
            pairs.append({
                "call_id": attempt_row["call_id"],
                "prepared_digest": attempt_row["prepared_digest"],
                "payload_digest": attempt_row["payload_digest"],
                "claim_digest": (claim or {}).get("request_digest"),
                "receipt_sha256": (receipt or {}).get("raw_sha256"),
                "reservation_ok": bool(reservation),
            })
        prepared_ok = bool(pairs) and all(
            pair["prepared_digest"] == pair["claim_digest"] for pair in pairs)
        payload_ok = bool(pairs) and all(
            pair["payload_digest"] == pair["receipt_sha256"] for pair in pairs)
        check("prepared_digest_equals_claim", prepared_ok, pairs=pairs)
        check("payload_digest_equals_receipt", payload_ok, pairs=pairs)
        usage_rows = []
        messages = ((candidate_result.get("event_summary") or {})
                    .get("assistant_messages") or [])
        messages = sorted((item for item in messages if isinstance(item, dict)),
                          key=lambda item: int(item.get("step") or 0))
        for message, receipt in zip(messages, receipts):
            dsh_usage = message.get("data_usage") or message.get("usage")
            usage_rows.append({"dsh": dsh_usage, "receipt": receipt.get("usage"),
                               "equal": isinstance(dsh_usage, dict)
                               and dsh_usage == receipt.get("usage")})
        check("dsh_usage_equals_receipt",
              len(usage_rows) == expected_calls and all(row["equal"] for row in usage_rows),
              rows=usage_rows)
        if scenario == "tool":
            two_cycle = g3d_launch.pair_tool_ledger(attempts, claims, receipts)
            check("two_independent_cycles",
                  len(two_cycle) == 2 and all(
                      item.get("prepared_ok") and item.get("payload_ok")
                      and item.get("reservation_link_ok") for item in two_cycle),
                  cycles=two_cycle)
            check("distinct_call_ids", len({row["call_id"] for row in attempts}) == 2,
                  call_ids=[row["call_id"] for row in attempts])
            check("tool_result_in_second_request",
                  len((candidate_result.get("event_summary") or {})
                      .get("tool_results") or []) >= 1,
                  summary=(candidate_result.get("event_summary") or {}))
        else:
            check("candidate_result_echo_ok",
                  candidate_result.get("final_response") == "ok"
                  and candidate_result.get("finish_reason") == "completed",
                  result={key: candidate_result.get(key) for key in
                          ("final_response", "finish_reason", "error")})
            # Streaming T1<T2 ordering is proven by the explicit ``c18``
            # stream_slow case; the plain echo receipt carries no first-chunk
            # timing mark by design.
        check("all_receipts_synthetic_no_network",
              all(row.get("synthetic") is True
                  and row.get("real_model_calls") == 0
                  and row.get("http_calls") == 0
                  and row.get("network_used") is False for row in receipts),
              rows=receipts)

    def _probe(self, phase: str) -> dict:
        return self._read_json_evidence(f"traces/probe-{phase}.json") or {}

    def _case_rows(self, document: dict) -> dict[str, dict]:
        return {case.get("label"): case for case in document.get("cases") or []}

    def _evaluate_negative_case(self, check, snapshot, gate) -> None:
        negatives = self._probe("negatives")
        rows = self._case_rows(negatives)
        expected = {
            "unapproved_tool_name": "ADMISSION_TOOL_SCHEMA_MISMATCH",
            "modified_approved_schema": "ADMISSION_TOOL_SCHEMA_MISMATCH",
            "extra_tool_alongside_approved": "ADMISSION_TOOL_SCHEMA_MISMATCH",
            "file_block": "REQUEST_INVALID",
            "self_authorization_field": "UNKNOWN_FIELD",
            "wrong_provider": "ROUTE_MISMATCH",
            "wrong_model": "ROUTE_MISMATCH",
            "max_tokens_over_admission": ("REQUEST_INVALID", "BAD_TYPE"),
        }
        problems = []
        for label, codes in expected.items():
            if isinstance(codes, str):
                codes = (codes,)
            row = rows.get(label) or {}
            got = row.get("error_code")
            ok = row.get("terminal") == "error" and (
                got in codes or (label == "self_authorization_field"
                                 and got in {"UNKNOWN_FIELD",
                                             "ADMISSION_SELF_AUTH_DENIED"}))
            if not ok:
                problems.append({"label": label, "expected": list(codes), "actual": got,
                                 "terminal": row.get("terminal")})
        check("negatives_all_rejected", not problems, problems=problems,
              seen=sorted(rows))
        check("negatives_left_ledger_empty",
              not snapshot["reservations"] and not snapshot["claims"]
              and not snapshot["attempts"] and snapshot["fake_counter"] == 0,
              reservations=len(snapshot["reservations"]),
              claims=len(snapshot["claims"]),
              attempts=len(snapshot["attempts"]),
              fake=snapshot["fake_counter"])
        network = self._probe("network")
        net_problems = []
        for row in network.get("checks") or []:
            if row.get("ok") is not True:
                net_problems.append(row)
        check("network_denied", network.get("ok") is True, problems=net_problems)
        check("network_no_external_connection",
              network.get("external_connection") is False,
              value=network.get("external_connection"))

    def _evaluate_replay_case(self, check, snapshot, gate) -> None:
        valid = self._probe("valid")
        replay = self._probe("replay")
        valid_cases = self._case_rows(valid)
        replay_cases = self._case_rows(replay)
        check("valid_request_finished",
              next(iter(valid_cases.values()), {}).get("terminal") == "finish",
              row=next(iter(valid_cases.values()), {}))
        check("replay_request_rejected",
              next(iter(replay_cases.values()), {}).get("terminal") == "error"
              and next(iter(replay_cases.values()), {}).get("error_code")
              in {"ATTEMPT_ALREADY_STARTED", "IDENTITY_REPLAYED", "CLAIM_REJECTED"},
              row=next(iter(replay_cases.values()), {}))
        check("replay_sent_at_most_once", snapshot["fake_counter"] == 1,
              fake=snapshot["fake_counter"])
        check("replay_single_ledger_set",
              len(snapshot["reservations"]) == 1
              and len(snapshot["claims"]) == 1
              and len(snapshot["attempts"]) == 1,
              reservations=len(snapshot["reservations"]),
              claims=len(snapshot["claims"]), attempts=len(snapshot["attempts"]))
        check("replay_gate_one_authorization",
              len(gate["authorized"]) == 1 and len(gate["consumed"]) == 1,
              authorized=len(gate["authorized"]), consumed=len(gate["consumed"]))

    def _evaluate_crash_case(self, check, snapshot, gate, *, expect_fake: int) -> None:
        valid = self._probe("valid")
        replay = self._probe("replay")
        check("crash_connection_failed",
              next(iter(self._case_rows(valid).values()), {}).get("terminal") != "finish",
              row=next(iter(self._case_rows(valid).values()), {}))
        check("crash_fake_count", snapshot["fake_counter"] == expect_fake,
              expected=expect_fake, actual=snapshot["fake_counter"])
        check("crash_attempt_durable_before_send",
              len(snapshot["attempts"]) == 1, attempts=len(snapshot["attempts"]))
        check("crash_admission_replayed_exit",
              any(record.get("admission_replayed_exit")
                  for record in self.restart_records),
              restarts=[record.get("exit_code")
                        for record in self.restart_records])
        replay_row = next(iter(self._case_rows(replay).values()), {})
        check("crash_replay_not_sent",
              replay_row.get("terminal") != "finish"
              and (replay_row.get("connected") is False
                   or replay_row.get("terminal") == "error"),
              row=replay_row)
        check("crash_replay_same_fake_count",
              snapshot["fake_counter"] == expect_fake, actual=snapshot["fake_counter"])
        check("crash_single_attempt_identity",
              len({row["call_id"] for row in snapshot["attempts"]}) == 1,
              call_ids=[row["call_id"] for row in snapshot["attempts"]])
        if expect_fake == 1:
            check("crash_receipt_reconciled_once",
                  len(snapshot["receipts"]) == 1, receipts=len(snapshot["receipts"]))
        check("crash_no_double_settlement",
              len(snapshot["reservations"]) == 1, reservations=len(snapshot["reservations"]))

    def _evaluate_broker_case(self, check, snapshot, gate) -> None:
        valid = self._probe("valid")
        row = next(iter(self._case_rows(valid).values()), {})
        check("broker_down_request_fails", row.get("terminal") == "error", row=row)
        check("broker_down_no_fake", snapshot["fake_counter"] == 0,
              counter=snapshot["fake_counter"])
        check("broker_down_no_attempt", not snapshot["attempts"],
              attempts=len(snapshot["attempts"]))
        check("broker_down_no_gate_authorization", not gate["authorized"],
              authorized=len(gate["authorized"]))
        check("broker_down_error_bounded",
              row.get("error_code") in {"BROKER_ERROR", "BROKER_UNAVAILABLE",
                                        "BROKER_TIMEOUT", "INTERNAL", "DEADLINE_EXCEEDED"},
              code=row.get("error_code"))

    def _evaluate_stream_case(self, check, snapshot, gate) -> None:
        candidate_result = self._read_json_evidence("traces/dsh-result.json") or {}
        check("stream_candidate_result",
              candidate_result.get("final_response") == "early",
              result={key: candidate_result.get(key) for key in
                      ("final_response", "finish_reason", "error")})
        check("stream_single_ledger",
              len(snapshot["reservations"]) == 1
              and len(snapshot["claims"]) == 1
              and len(snapshot["attempts"]) == 1,
              reservations=len(snapshot["reservations"]),
              claims=len(snapshot["claims"]),
              attempts=len(snapshot["attempts"]))
        check("stream_single_receipt", snapshot["fake_counter"] == 1,
              counter=snapshot["fake_counter"])
        timing = self._timing_rows()
        first = exit_mark = None
        for row in timing:
            names = {mark.get("name"): mark for mark in row.get("marks") or []}
            first = first or names.get("first_chunk_flushed")
            exit_mark = exit_mark or names.get("exit_after_finish")
        check("stream_chunk_before_fake_exit",
              bool(first) and bool(exit_mark)
              and first.get("monotonic", 0) < exit_mark.get("monotonic", 0),
              first=first, exit=exit_mark)
        check("stream_gate_consumed_once",
              len(gate["authorized"]) == 1 and len(gate["consumed"]) == 1,
              authorized=len(gate["authorized"]), consumed=len(gate["consumed"]))

    def _evaluate_quota_case(self, check, snapshot, gate) -> None:
        first = self._probe("valid")
        second = self._probe("over_quota")
        first_row = next(iter(self._case_rows(first).values()), {})
        second_row = next(iter(self._case_rows(second).values()), {})
        check("quota_first_finished", first_row.get("terminal") == "finish", row=first_row)
        check("quota_second_denied",
              second_row.get("terminal") == "error"
              and second_row.get("error_code") == "BUDGET_DENIED", row=second_row)
        check("quota_fake_sent_once", snapshot["fake_counter"] == 1,
              counter=snapshot["fake_counter"])
        check("quota_single_ledger_set",
              len(snapshot["reservations"]) == 1
              and len(snapshot["attempts"]) == 1,
              reservations=len(snapshot["reservations"]),
              attempts=len(snapshot["attempts"]))

    # -- G4-F5 revocation / timeout / in-flight crash -------------------
    @staticmethod
    def _money(value: object) -> Decimal:
        try:
            return Decimal(str(value))
        except Exception:  # noqa: BLE001 - evidence-only conversion
            return Decimal("0")

    def _step_record(self, name: str) -> dict:
        document = self._read_json_evidence("run/steps.json") or {}
        for item in document.get("steps") or []:
            if item.get("step") == name:
                return item.get("record") or {}
        return {}

    def _gate_snapshot(self, relative: str) -> dict:
        return self._read_json_evidence(relative) or {}

    def _revocation_denials(self, gate: dict) -> list[dict]:
        return [row for row in gate.get("revocation") or []
                if row.get("revoked") is True]

    def _revocation_pre_reserve_check(self, gate: dict) -> bool:
        return any(row.get("checkpoint") == "pre_reserve"
                   and row.get("reason") == "RUN_AUTHORIZATION_REVOKED"
                   for row in self._revocation_denials(gate))

    def _evaluate_revocation_case(self, check, snapshot, gate) -> None:
        case = self.case
        reservations = snapshot["reservations"]
        claims = snapshot["claims"]
        attempts = snapshot["attempts"]
        receipts = snapshot["receipts"]
        check("revocation_document_written", bool(self.revocations),
              rows=len(self.revocations))
        check("revocation_enabled_in_policy",
              bool((self.g4c_policy or {}).get("revocation")),
              policy=(self.g4c_policy or {}).get("revocation"))
        check("revocation_gate_observed_denial",
              bool(self._revocation_denials(gate)),
              rows=[{key: row.get(key) for key in
                     ("checkpoint", "reason", "state_sha256")}
                    for row in self._revocation_denials(gate)][:4])
        if case == "revocation-pre-reserve":
            row = next(iter(self._case_rows(self._probe("valid")).values()), {})
            check("revocation_pre_reserve_denied",
                  row.get("terminal") == "error"
                  and row.get("error_code") == "ADMISSION_SELF_AUTH_DENIED",
                  row=row)
            check("revocation_pre_reserve_no_reservation", not reservations,
                  rows=len(reservations))
            check("revocation_pre_reserve_no_claim_attempt_intent",
                  not claims and not attempts and not snapshot["intents"],
                  claims=len(claims), attempts=len(attempts),
                  intents=len(snapshot["intents"]))
            check("revocation_pre_reserve_no_receipt_or_fake",
                  not receipts and snapshot["fake_counter"] == 0,
                  receipts=len(receipts), fake=snapshot["fake_counter"])
            check("revocation_pre_reserve_no_send_authorization",
                  not gate["authorized"], authorized=len(gate["authorized"]))
            check("revocation_pre_reserve_checkpoint",
                  self._revocation_pre_reserve_check(gate),
                  rows=self._revocation_denials(gate)[:3])
            return
        if case == "revocation-post-reserve":
            first = next(iter(self._case_rows(self._probe("valid")).values()), {})
            second = next(iter(self._case_rows(self._probe("valid2")).values()), {})
            recovery = self._gate_snapshot("run/g4c-egress-recovery.json")
            check("revocation_post_reserve_denied",
                  first.get("terminal") == "error"
                  and first.get("error_code") == "ADMISSION_SELF_AUTH_DENIED",
                  row=first)
            check("revocation_post_reserve_single_pending_reservation",
                  len(reservations) == 1
                  and reservations[0].get("status") == "PENDING"
                  and self._money(reservations[0].get("cost")) > 0,
                  rows=[{key: row.get(key) for key in ("status", "cost", "estimated")}
                        for row in reservations])
            check("revocation_post_reserve_single_claim", len(claims) == 1,
                  rows=len(claims))
            check("revocation_post_reserve_attempt_uncertain",
                  len(attempts) == 1
                  and attempts[0].get("state") in {"SETTLEMENT_UNCERTAIN",
                                                   "ATTEMPT_STARTED"},
                  states=[row.get("state") for row in attempts])
            check("revocation_post_reserve_no_fake",
                  not receipts and snapshot["fake_counter"] == 0,
                  receipts=len(receipts), fake=snapshot["fake_counter"])
            check("revocation_post_reserve_no_authorized_send",
                  not gate["authorized"], authorized=len(gate["authorized"]))
            check("revocation_post_reserve_recovery_held",
                  self._money(recovery.get("worst_case_held_usd")) > 0
                  and self._money(recovery.get("known_cost_usd")) == 0,
                  held=recovery.get("worst_case_held_usd"),
                  known=recovery.get("known_cost_usd"))
            recovery_views = (recovery.get("cost_view") or {}).get("reservations") or []
            check("revocation_post_reserve_recovery_broker_pending",
                  len(recovery_views) == 1
                  and recovery_views[0].get("broker_status") == "PENDING",
                  views=recovery_views[:1])
            check("revocation_after_request_rejected",
                  second.get("terminal") == "error"
                  and second.get("error_code") == "ADMISSION_SELF_AUTH_DENIED",
                  row=second)
            check("revocation_after_request_no_new_ledger",
                  len(reservations) == 1 and len(claims) == 1
                  and len(attempts) == 1 and not receipts,
                  reservations=len(reservations), claims=len(claims),
                  attempts=len(attempts), receipts=len(receipts))
            check("revocation_post_reserve_no_double_settlement",
                  len(gate["authorized"]) == 0 and not gate["consumed"],
                  authorized=len(gate["authorized"]),
                  consumed=len(gate["consumed"]))
            return
        # revocation-in-flight
        first = next(iter(self._case_rows(self._probe("valid")).values()), {})
        second = next(iter(self._case_rows(self._probe("valid2")).values()), {})
        step = self._step_record("valid-revoke-in-flight")
        check("revocation_in_flight_request_completed",
              first.get("terminal") == "finish", row=first)
        check("revocation_in_flight_single_settled_ledger",
              len(reservations) == 1
              and reservations[0].get("status") in {"OK", "FAILED"}
              and len(claims) == 1 and len(attempts) == 1
              and attempts[0].get("state") == "SETTLED",
              reservations=[row.get("status") for row in reservations],
              attempts=[row.get("state") for row in attempts])
        check("revocation_in_flight_fake_once",
              snapshot["fake_counter"] == 1 and len(receipts) == 1,
              fake=snapshot["fake_counter"], receipts=len(receipts))
        check("revocation_in_flight_not_free",
              self._money(reservations[0].get("cost")) > 0,
              row={key: reservations[0].get(key)
                   for key in ("cost", "estimated")} if reservations else None)
        check("revocation_in_flight_observed_after_receipt",
              (step.get("window") == "in_flight")
              and isinstance(step.get("observed"), int)
              and step["observed"] >= 1
              and bool(step.get("revocation", {}).get("revoked")),
              step={key: step.get(key) for key in ("window", "observed")})
        check("revocation_in_flight_second_request_rejected",
              second.get("terminal") == "error"
              and second.get("error_code") == "ADMISSION_SELF_AUTH_DENIED",
              row=second)
        check("revocation_in_flight_no_second_ledger",
              len(reservations) == 1 and len(claims) == 1
              and len(attempts) == 1 and snapshot["fake_counter"] == 1,
              reservations=len(reservations), claims=len(claims),
              attempts=len(attempts), fake=snapshot["fake_counter"])
        check("revocation_in_flight_no_double_send",
              len(gate["authorized"]) == 1 and len(gate["consumed"]) == 1,
              authorized=len(gate["authorized"]),
              consumed=len(gate["consumed"]))

    def _evaluate_timeout_pre_send(self, check, snapshot, gate) -> None:
        row = next(iter(self._case_rows(self._probe("valid")).values()), {})
        check("timeout_pre_send_deadline_code",
              row.get("terminal") == "error"
              and row.get("error_code") == "DEADLINE_EXCEEDED", row=row)
        check("timeout_pre_send_no_reservation", not snapshot["reservations"],
              rows=len(snapshot["reservations"]))
        check("timeout_pre_send_no_attempt", not snapshot["attempts"],
              rows=len(snapshot["attempts"]))
        check("timeout_pre_send_no_receipt_or_fake",
              not snapshot["receipts"] and snapshot["fake_counter"] == 0,
              receipts=len(snapshot["receipts"]), fake=snapshot["fake_counter"])
        check("timeout_pre_send_no_authorization", not gate["authorized"],
              authorized=len(gate["authorized"]))
        marker = self.run_dir / "state" / "g4f5-delay-marker.json"
        check("timeout_pre_send_real_delay_observed", marker.is_file(),
              marker=str(marker))

    def _evaluate_timeout_post_send(self, check, snapshot, gate) -> None:
        first = next(iter(self._case_rows(self._probe("valid")).values()), {})
        replay = next(iter(self._case_rows(self._probe("replay")).values()), {})
        before = self._gate_snapshot("run/g4c-egress-before-restart.json")
        recovery = self._gate_snapshot("run/g4c-egress-recovery.json")
        reservations = snapshot["reservations"]
        attempts = snapshot["attempts"]
        check("timeout_post_send_deadline_code",
              first.get("terminal") == "error"
              and first.get("error_code") == "DEADLINE_EXCEEDED", row=first)
        check("timeout_post_send_fake_once",
              snapshot["fake_counter"] == 1 and len(snapshot["receipts"]) == 1,
              fake=snapshot["fake_counter"], receipts=len(snapshot["receipts"]))
        check("timeout_post_send_single_reservation",
              len(reservations) == 1, rows=len(reservations))
        check("timeout_post_send_attempt_uncertain",
              len(attempts) == 1
              and attempts[0].get("state") in {"SETTLEMENT_UNCERTAIN", "SETTLED"},
              states=[row.get("state") for row in attempts])
        check("timeout_post_send_held_before_recovery",
              self._money(before.get("worst_case_held_usd")) > 0
              and self._money(before.get("known_cost_usd")) == 0,
              held=before.get("worst_case_held_usd"),
              known=before.get("known_cost_usd"))
        check("timeout_post_send_replay_not_sent",
              replay.get("terminal") == "error"
              and snapshot["fake_counter"] == 1, row=replay)
        final_status = reservations[0].get("status") if reservations else None
        final_cost = self._money(reservations[0].get("cost")) if reservations else Decimal("0")
        check("timeout_post_send_broker_conservative",
              final_status in {"PENDING", "OK", "FAILED"}
              and (final_status == "PENDING" or final_cost > 0),
              status=final_status, cost=str(final_cost))
        check("timeout_post_send_recovery_not_free",
              (self._money(recovery.get("worst_case_held_usd")) > 0
               or self._money(recovery.get("known_cost_usd")) > 0),
              held=recovery.get("worst_case_held_usd"),
              known=recovery.get("known_cost_usd"))
        check("timeout_post_send_no_double_send",
              len(gate["authorized"]) == 1 and len(gate["consumed"]) == 1,
              authorized=len(gate["authorized"]),
              consumed=len(gate["consumed"]))

    def _evaluate_ingress_crash_case(self, check, snapshot, gate) -> None:
        row = next(iter(self._case_rows(self._probe("valid")).values()), {})
        replay = next(iter(self._case_rows(self._probe("replay")).values()), {})
        recovery = self._gate_snapshot("run/g4c-egress-recovery.json")
        reservations = snapshot["reservations"]
        attempts = snapshot["attempts"]
        check("ingress_crash_request_failed", row.get("terminal") != "finish", row=row)
        check("ingress_crash_fake_zero",
              snapshot["fake_counter"] == 0 and not snapshot["receipts"],
              fake=snapshot["fake_counter"], receipts=len(snapshot["receipts"]))
        check("ingress_crash_pending_reservation",
              len(reservations) == 1
              and reservations[0].get("status") == "PENDING"
              and self._money(reservations[0].get("cost")) > 0,
              rows=[{key: row.get(key) for key in ("status", "cost")}
                    for row in reservations])
        check("ingress_crash_durable_attempt",
              len(attempts) == 1
              and attempts[0].get("state") in {"SETTLEMENT_UNCERTAIN",
                                               "ATTEMPT_STARTED"},
              states=[row.get("state") for row in attempts])
        check("ingress_crash_recovery_held",
              self._money(recovery.get("worst_case_held_usd")) > 0
              and self._money(recovery.get("known_cost_usd")) == 0,
              held=recovery.get("worst_case_held_usd"),
              known=recovery.get("known_cost_usd"))
        check("ingress_crash_replay_not_sent",
              replay.get("terminal") != "finish"
              and snapshot["fake_counter"] == 0, row=replay)
        check("ingress_crash_no_second_reservation",
              len(reservations) == 1, rows=len(reservations))
        check("ingress_crash_gate_single_authorization",
              len(gate["authorized"]) == 1, authorized=len(gate["authorized"]))
        expected_consumed = 1 if self.case == "crash-after-consume" else 0
        check("ingress_crash_gate_consume_boundary",
              len(gate["consumed"]) == expected_consumed,
              expected=expected_consumed, consumed=len(gate["consumed"]))
        check("ingress_crash_no_double_settlement",
              len(snapshot["claims"]) == 1, claims=len(snapshot["claims"]))

    def kill_broker(self, *, reason: str = "broker-down") -> dict:
        """Kill the trusted Broker subprocess only (controller stays alive)."""
        code = (
            "import os,signal\n"
            "killed=[]\n"
            "for name in os.listdir('/proc'):\n"
            "    if not name.isdigit(): continue\n"
            "    try:\n"
            "        cmd=open('/proc/'+name+'/cmdline','rb').read()\n"
            "    except OSError: continue\n"
            "    if b'autoteacher_m0.accounting.broker' in cmd and int(name)!=os.getpid():\n"
            "        os.kill(int(name), signal.SIGKILL); killed.append(int(name))\n"
            "print('G4C_BROKER_KILLED '+str(killed))\n"
        )
        record = self.cmd(["podman", "exec", self.trusted_name,
                           "/opt/python/bin/python3.11", "-B", "-c", code],
                          name=f"kill-broker-{reason}", timeout=30)
        document = {"reason": reason, "utc": lib.utc_now(),
                    "exit": record.get("exit"),
                    "stdout": (record.get("stdout") or "").strip()[-500:],
                    "stderr": (record.get("stderr") or "").strip()[-500:]}
        self.write_evidence_json(f"run/kill-broker-{reason}.json", document)
        return document

    def _wait_for(self, predicate, *, timeout: float, interval: float = 0.05):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            value = predicate()
            if value:
                return value
            time.sleep(interval)
        return None

    def _probe_async(self, phase: str, *, timeout: float = 30.0) -> dict:
        holder: dict = {}

        def worker() -> None:
            try:
                holder["record"] = self.run_candidate_probe(phase, timeout=timeout)
            except BaseException as exc:  # noqa: BLE001 - evidence records failures
                holder["error"] = f"{type(exc).__name__}: {exc}"[:1000]

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        holder["thread"] = thread
        return holder

    def _join_probe(self, holder: dict, *, timeout: float) -> dict:
        thread = holder.pop("thread", None)
        if thread is not None:
            thread.join(timeout=timeout)
        return holder

    def _run_probe_then_revoke(self, phase: str, *, window: str,
                               timeout: float = 45.0) -> dict:
        """Run one real request and revoke the synthetic authorization mid-flight.

        ``window`` = ``after_reserve`` waits for the controller's test-only
        delay marker (post-Reserve, pre-send) before rewriting the revocation
        document; ``in_flight`` waits for the Fake receipt (post-wire) instead.
        Both are real external writes followed by the real gate re-read.
        """
        if not self.revocation_enabled:
            raise lib3d.G3DError("revocation window requested without --revocation")
        marker = self.run_dir / "state" / "g4f5-delay-marker.json"
        if marker.exists():
            marker.unlink()
        receipts = self.run_dir / "state" / "receipts"
        before = len(list(receipts.glob("rcpt-*.json"))) if receipts.is_dir() else 0
        holder = self._probe_async(phase, timeout=timeout)
        observed = None
        if window == "after_reserve":
            found = self._wait_for(
                lambda: marker.is_file() or None, timeout=30.0)
            observed = bool(found)
            if not observed:
                raise lib3d.G3DError("post-reserve delay marker was not observed")
        elif window == "in_flight":
            def new_receipt():
                if not receipts.is_dir():
                    return None
                rows = sorted(receipts.glob("rcpt-*.json"))
                return len(rows) if len(rows) > before else None
            found = self._wait_for(new_receipt, timeout=30.0)
            observed = found if isinstance(found, int) else None
            if observed is None:
                raise lib3d.G3DError("Fake receipt was not observed before revoke")
        else:
            raise lib3d.G3DError(f"unknown revocation window: {window}")
        record = self.write_revocation(
            revoked=True, reason=f"in-flight:{window}:{phase}")
        result = self._join_probe(holder, timeout=timeout)
        return {"window": window, "observed": observed,
                "revocation": record, "probe": result,
                "marker": (json.loads(marker.read_text(encoding="utf-8"))
                           if marker.is_file() else None)}

    def stop_trusted(self, *, reason: str = "f5-stop") -> dict:
        """Stop the serving trusted process before a real recovery start.

        SIGTERM first so the trusted entry can flush its final gate snapshot
        (the evidence of pre-recovery held/known); SIGKILL only as a fallback.
        """
        term = self.cmd(["podman", "kill", "-s", "TERM", self.trusted_name],
                        name=f"stop-trusted-term-{reason}", timeout=60)
        wait = self.cmd(["podman", "wait", "--interval", "150ms",
                         self.trusted_name],
                        name=f"stop-wait-trusted-{reason}", timeout=20)
        killed = False
        if wait.get("timed_out"):
            killed = True
            self.cmd(["podman", "kill", "-s", "KILL", self.trusted_name],
                     name=f"stop-trusted-kill-{reason}", timeout=60)
            wait = self.cmd(["podman", "wait", "--interval", "150ms",
                             self.trusted_name],
                            name=f"stop-wait-trusted-killed-{reason}", timeout=30)
        document = {"reason": reason, "utc": lib.utc_now(),
                    "term_exit": term.get("exit"),
                    "killed_fallback": killed,
                    "wait_exit": wait.get("exit"),
                    "wait_stdout": (wait.get("stdout") or "").strip()[-200:]}
        self.write_evidence_json(f"run/stop-trusted-{reason}.json", document)
        return document

    def run_steps(self, steps: list[str]) -> list[dict]:
        results = []
        for step in steps:
            step = step.strip()
            if not step:
                continue
            if step == "restart":
                results.append({"step": step,
                                "record": self.restart_trusted(reason=self.case)})
            elif step == "stop-trusted":
                results.append({"step": step,
                                "record": self.stop_trusted(reason=self.case)})
            elif step == "kill-broker":
                results.append({"step": step, "record": self.kill_broker()})
            elif step in {"revoke", "unrevoke"}:
                results.append({"step": step, "record": self.write_revocation(
                    revoked=(step == "revoke"), reason=f"step:{step}")})
            elif step == "valid-revoke-after-reserve":
                results.append({"step": step, "record": self._run_probe_then_revoke(
                    "valid", window="after_reserve")})
            elif step == "valid-revoke-in-flight":
                results.append({"step": step, "record": self._run_probe_then_revoke(
                    "valid", window="in_flight")})
            else:
                results.append({"step": step, "record": self.run_candidate_probe(step)})
        self.write_evidence_json("run/steps.json", {"steps": results})
        return results

    def collect(self) -> None:
        for record in self.restart_records:
            name = record["container"]
            logs = self._container_logs(name, f"restart-log-{name}")
            if logs:
                lib3d.write_bytes_atomic(self.evidence / "run" / f"{name}.log",
                                       logs.encode(), mode=0o444)
        super().collect()

    def cleanup(self) -> None:
        self._cleanup_rootfs_targets()
        ps = self.cmd(["podman", "ps", "-a", "--format", "{{.Names}}"],
                      name="cleanup-list-containers", timeout=30)
        for name in (ps.get("stdout") or "").splitlines():
            name = name.strip()
            if name.startswith((self.trusted_name + "-r",
                                self.candidate_name + "-r")):
                self.cmd(["podman", "rm", "-f", name],
                         name=f"cleanup-rm-prefix-{name}", timeout=60)
        for record in self.restart_records:
            name = record["container"]
            status = self.podman_status(name)
            if status is not None:
                self.cmd(["podman", "rm", "-f", name],
                         name=f"cleanup-rm-restart-{name}", timeout=60)
        super().cleanup()

    # -- evidence summary ----------------------------------------------
    def write_evidence(self) -> None:
        if not self.evidence_ready:
            return
        cleanup = self.records.get("cleanup") or {}
        canonical = cleanup.get("canonical") or {}
        summary = {
            "schema": "m0.g4c.run-summary.v1",
            "utc_start": self.started_utc,
            "utc_end": lib.utc_now(),
            "run_id": self.run_id,
            "case": self.case,
            "scenario": self.args.scenario,
            "candidate_mode": self.args.candidate_mode,
            "crash_hook": self.crash_hook,
            "status": "PASS" if self.exit_code == lib3d.EXIT_OK else "FAIL",
            "exit_code": self.exit_code,
            "failure": self.failure,
            "errors": self.errors,
            "stage": self.records.get("stage"),
            "configs": self.records.get("configs"),
            "g4c": self.records.get("g4c"),
            "containers": self.container_records,
            "restarts": self.restart_records,
            "checks": self.checks,
            "cleanup": {"ok": cleanup.get("ok"),
                        "problems": cleanup.get("problems")},
            "canonical": canonical,
            "synthetic": True,
            "provider_route_kind": "synthetic_only",
            "real_model_calls": 0,
            "real_external_http_calls": 0,
            "provider_keys_seen": 0,
            "billable_send_allowed": 0,
            "has_real_key": False,
            "live_gate_status": "BLOCKED",
        }
        self.write_evidence_json("summary.json", summary)
        failure_ids = [item["id"] for item in self.checks if not item["ok"]]
        text = [
            f"RUN_ID={self.run_id}", f"CASE={self.case}",
            f"STATUS={summary['status']}", f"EXIT={self.exit_code}",
            f"UTC_START={self.started_utc}", f"UTC_END={summary['utc_end']}",
            "CHECKS:",
            *[f"  {'PASS' if item['ok'] else 'FAIL'} {item['id']}"
              for item in self.checks],
            f"CHECK_FAILURES={failure_ids}",
            f"CLEANUP_OK={cleanup.get('ok')}",
        ]
        lib3d.write_bytes_atomic(self.evidence / "run" / "run-summary.txt",
                               ("\n".join(text) + "\n").encode(), mode=0o444)



def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if os.geteuid() != 0:
        sys.stderr.write("G4C_LAUNCH_NEEDS_HOST_ROOT\n")
        return lib3d.EXIT_BLOCKED_ENVIRONMENT
    try:
        launcher = G4CLauncher(args)
    except lib3d.G3DError as exc:
        sys.stderr.write(f"LAUNCH_FAILED {exc.reason}: {exc}\n")
        return exc.exit_code
    try:
        launcher.preflight()
        launcher.create_run()
        launcher.write_configs()
        launcher.start_trusted()
        try:
            launcher.start_candidate()
            if args.steps:
                launcher.run_steps([step for step in args.steps.split(",") if step])
            launcher.collect()
            launcher.evaluate()
        except lib3d.G3DError as exc:
            launcher.failure = {"reason": exc.reason, "message": str(exc),
                                "detail": exc.detail}
            launcher.exit_code = exc.exit_code
            launcher.collect()
            launcher.evaluate()
    except lib3d.G3DError as exc:
        launcher.failure = {"reason": exc.reason, "message": str(exc),
                            "detail": exc.detail}
        launcher.exit_code = exc.exit_code
        launcher.record_error(exc.reason, str(exc), **exc.detail)
        try:
            launcher.collect()
        except Exception:  # noqa: BLE001 - never lose evidence
            pass
    except Exception as exc:  # noqa: BLE001
        launcher.failure = {"reason": "INTERNAL",
                            "message": f"{type(exc).__name__}: {exc}"}
        launcher.exit_code = lib3d.EXIT_CASE_FAILED
        launcher.record_error("INTERNAL", f"{type(exc).__name__}: {exc}")
    try:
        launcher.cleanup()
    except Exception as exc:  # noqa: BLE001
        launcher.record_error("CLEANUP_EXCEPTION", f"{type(exc).__name__}: {exc}")
        if launcher.exit_code == lib3d.EXIT_OK:
            launcher.exit_code = lib3d.EXIT_CLEANUP_RESIDUAL
    try:
        launcher.write_evidence()
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"EVIDENCE_WRITE_FAILED {type(exc).__name__}: {exc}\n")
        if launcher.exit_code == lib3d.EXIT_OK:
            launcher.exit_code = lib3d.EXIT_EVIDENCE_INTEGRITY
    print(json.dumps({"run_id": launcher.run_id,
                      "status": "PASS" if launcher.exit_code == 0 else "FAIL",
                      "exit": launcher.exit_code,
                      "evidence": str(launcher.evidence),
                      "failure": launcher.failure}, sort_keys=True))
    return launcher.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
