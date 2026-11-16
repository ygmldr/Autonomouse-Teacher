# M0 G2-L1.1 — Review Request / Handoff（§11 + §14 模板）

## Objective / Scope / Non-goals
- Objective: 最小补丁修复 G2-L1.1 T1–T6：provider after-entry 归因、canonical call_id、Prepared strict schema、journal 有界、descriptor 计数、兼容回归。
- Scope: 离线/无 Key G2-L1.1；fixed OCI；不改 gates/adapter/run_live；不进入 G3+。
- Non-goals: 真实 provider wire/usage/invoice/exactly-once、Live/GO、DSH Plugin/SDK B 层执行（本轮 UNVERIFIED）。

## Actual base, implementation and docs commits
- Base: `76f1c52d156d0c5e9e3834afc8d2ea35555e7626`（父 = G2-L1.1 Playbook+G0 docs）
- Implementation: `bf1e84dab9c74f1bec919633672dc29abfa7a77b`（父 `76f1c52`）
- Docs: 本 docs commit（见 git log；生成时不自引用自身 SHA）

## Files changed (with why)
- `src/autoteacher_m0/security/egress.py`: T1 attempt-start/classification, T3 Prepared strict, T5 counters/attribution.
- `src/autoteacher_m0/accounting/call_identity.py`: T2 single canonical JSON/derive.
- `src/autoteacher_m0/accounting/broker.py`: T4 invalid completion precheck (no journal growth).
- `tests/integration/g2_closure/test_g2l1_fix.py`: L11-ATT/ID/PREP/JRN/DIAG cases.
- `tests/integration/sandbox/test_egress_boundary.py`: descriptor diagnostics no longer consume claim quota.
- `scripts/verify_egress_policy.py`: updated attempt-quota semantics.
- docs: this request + fix report.

## Contract/API/schema migration and compatibility
- No DB migration; claim table unchanged. v1 ops unchanged; additive behavior only for invalid completion precheck and diagnostics.
- `dispatch_count` means **provider callable entry/attempt-start count (including calls that raise after entry)**; it is NOT confirmed HTTP/completed-response count. `provider_calls` is function-entry count. `dispatched=True` on after-entry exception means "may have been sent" with state BILLABLE_UNKNOWN; local bookkeeping is not remote exactly-once.
- `attempts` legacy snapshot remains successful-claim count; `attempts_detail` is authoritative.
- T2 canonicalization now single implementation in `call_identity.py`; ASCII IDs unchanged (same canonical JSON formatting for ASCII), legacy IDs are not rewritten.

## Findings (before → after; code line and test ID)
| ID | Before | After | Test |
|---|---|---|---|
| T1/L11-ATT-03 | provider entered then RuntimeError → NOT_DISPATCHED/provider_calls=0 | ATTEMPT_STARTED, BILLABLE_UNKNOWN, held/worst-case, calls=1 | L11-ATT-03 |
| T1/L11-ATT-04 | invalid result → NOT_DISPATCHED | ATTEMPT_STARTED/BILLABLE_UNKNOWN, no retry | L11-ATT-04 |
| T1/L11-ATT-06 | BaseException swallowed | KeyboardInterrupt re-raised after cleanup/attribution | L11-ATT-06 |
| T2/L11-ID-02 | Chinese run_id mismatch Accounting vs Egress | same call_id | L11-ID-01..06 |
| T3/L11-PREP-01 | v0 schema accepted | rejected before claimer | L11-PREP-01 |
| T4/L11-JRN-01 | unique unknown completion journals | 0 new journal rows | L11-JRN-01 |
| T5/L11-DIAG-01 | descriptor checks consume quota | no quota consumption; claim bound | L11-DIAG-01 |

## PASS / FAIL / BLOCKED / NOT RUN by exact test ID
- PASS: L11-ATT-01..06, L11-ID-01..06, L11-PREP-01..05, L11-JRN-01..04, L11-DIAG-01..03.
- PASS regression: full `tests/` 625 passed, 1 skipped; G2 BIND/INT subset included.
- BLOCKED/UNVERIFIED: DSH Plugin/SDK B-layer Node tests (`plugins/runtime-budget-guard`, `plugins/skill-lookup`) — OCI image has no node; not run; host Node not used.
- NOT RUN: any G3/G4/G5/G6, real provider/Key/HTTP/usage.

## Raw trace index and provider call count proof
- RED (exact base `76f1c52` + tests from `bf1e84d`): **8 failed / 16 passed** (`artifacts/g2l11/logs/red2.stdout.log`; behavior RED 6: ATT-03/04/06, ID-02, JRN-01, DIAG-01; API-shape RED 2: ATT-01, DIAG-02). The old `artifacts/g2l11/logs/red.stdout.log` (10 failed / 14 passed) used an earlier test version and is **superseded**, retained only as history; see `docs/M0_G2L11_ERRATA.md` and packet `logs/red2.stdout.log`.
- GREEN: `artifacts/g2l11/logs/green2.stdout.log` (24 passed).
- Full: `artifacts/g2l11/logs/impl-full.stdout.log` (625 passed, 1 skipped).
- Script/Ruff: `impl-script.stdout.log` (PASS), `impl-ruff.stdout.log` (All checks passed!).
- L11-ATT-03/04 assert provider entry count; output state BILLABLE_UNKNOWN; no retry.

## Security invariants / secret-scan / LiveGate status
- 0 real Key/model/external HTTP; no `/root/.config/autoteacher` access; fixed OCI network none; no Node B run.
- `gates.py`/`dsh_adapter.py`/`run_live.sh` unchanged vs base; LiveGate BLOCKED; no GO.
- Local claim is not remote exactly-once; FakeProvider synthetic.

## Independent reproducibility
- Base/impl/docs commits above; stage `git archive bf1e84d`, 198 files, normalized sha256 `ab95ffb46e070f3c166f9b1a22a9a18af6bc56aa3fe83f1397ba83abcbd201c1`.
- OCI image `localhost/autoteacher-local-oci@sha256:62d3569e…`; deps normalized `e07729d7…`; `--network none`, read-only, uid 65534, cap-drop ALL.
- Commands exact: see Review Packet `logs/` + `manifest.json` `executed_test_selection`.

## Residual risks (P0/P1/P2; G3 dependencies)
- P1: DSH Plugin/SDK B-layer UNVERIFIED (no node in OCI).
- P1: ATTEMPT_STARTED persistence across crash not implemented (memory diagnostic only; G3 gate).
- P2/T4: invalid completion fix is broker-local; no external billing proof.
- P2/T5: legacy `snapshot.attempts` semantics read-only compatibility; consumers should use attempts_detail.
- G3: real wire/digest, tool registry, remote exactly-once/usage/invoice, old v1 omission residual.

## Questions requiring maintainer decision
1. Accept T4/T5 minimal changes as non-blocking P2?
2. Require maintainer-provided Node environment for DSH Plugin/SDK B-layer before G3?
3. Confirm old v1 unbound residual is G3 migration, not G2-L1.1 blocker?

## Requested reviewer verdict (limited scope, no GO/Live request)
- Requested: accept G2-L1.1 implementation for declared offline scope, or file precise FAIL/BLOCKED items. Do **not** issue Live/GO; G3 not started.
