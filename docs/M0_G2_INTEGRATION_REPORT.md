# M0 G2-EGRESS/Integration 报告 — CallIdentity/Egress/Broker/Observation 离线闭环（无 Key）

- 任务：`task-66`（v0.6 G2-EGRESS/Integration）；基线 HEAD `ada8e28`（G2-BROKER freeze，父 `70cb574`）
- 结论：**Egress→Broker→Observation 离线闭环在真实 SQLite + 真实 stdio Broker 子进程 + 无 socket FakeProvider 上打通；INT-01…INT-18 全部有定向测试并通过；无真实 Key/模型/HTTP/socket 外呼；Live/E1–E5/LiveGate 仍 BLOCKED、DECISION PENDING，不签发 GO。**
- 本任务不 git add/commit；不修改 accounting 实现（只调用 task-65 冻结 API）、不改 guard/adapter/gates/run_live、不改历史证据。

## 1. 交付/变更

- `src/autoteacher_m0/security/egress.py`（仅此实现文件）：
  - **Canonical CallIdentity**：删除 egress 自派生 `eg-…` 作为结算 ID；`EgressRequest` 新增并强校验 `call_id`（`call-[0-9a-f]{48}`）与 `request_digest`（64 hex）；`eg-…` 仅保留为 `EgressDecision.legacy_egress_event_id` 日志字段，不参与 claim/settle。
  - **Broker claim 门**：`EgressBoundary(claimer=...)` + `claim_dispatch()/require_claim()`；dispatch 前向真实 stdio Broker 发 `claim`，claim 失败/重复/route 不符/未绑定/ broker down → `CLAIM_REJECTED:<code>` 且 0 dispatch；`authorize()` 仅保留给 descriptor/PR4a 回归路径。
  - `MockEgressTransport` 在配置 claimer 时走 claim 门；PR4a 失败矩阵/状态语义保留（旧测试已适配 canonical id，`eg-` 断言改为 legacy 字段）。
- `tests/integration/sandbox/test_egress_boundary.py`（适配 canonical id + legacy 日志断言 + invalid call_id/digest 用例）。
- `tests/integration/g2_closure/test_g2_closure.py`（新增，G2 闭环 INT 矩阵；真实 SQLite/stdio Broker/FakeProvider）。
- 证据：`artifacts/m0-g2-integration/`（manifest/evidence/argv/UTC/exit/image/absence）。

## 2. 闭环协议

1. 可信 Controller/harness 用 `derive_call_id(run_id, logical_step, attempt_index, request_digest)` 在 reserve 前生成 canonical `call-…`（ADR-002）。
2. 真实 stdio Broker `reserve`（带 `call_id`）返回 reservation 并持久绑定 call link。
3. Egress 只接收/校验 canonical call_id 与 digest；`claim_dispatch()` 调真实 stdio Broker `claim`（同一事务持久唯一 claim），成功才 dispatch。
4. `FakeProvider`（进程内/stdio 脚本，无 socket）返回 synthetic fixture 结果；harness 明确标记 synthetic。
5. 可信 harness 通过 `issue_trusted_egress_provenance` 签发同进程 capability，`deliver_observation(ledger, call_id, observation, …)` 将 observation 绑定到 reservation 并 settle（AUTHORITATIVE 需 provenance）。
6. 计数交叉：`network_attempts=0`（OCI 禁 socket；FakeProvider 不建 socket）、`dispatch_claim_count` 由 Broker snapshot 的 `claims`/`pending` 交叉断言、settlement 状态与 ledger 一致。

## 3. INT 矩阵（实际结果，全部定向测试通过）

| INT | 场景 | 测试/结果 |
|---|---|---|
| INT-01 | 正常单次 reserve→claim→fake send→trusted observation→settle | `test_int01_closed_loop_settles_once` PASS；claims total 1/completed 1，network_attempts=0 |
| INT-02 | 非空假 reservation | `test_int02_fake_reservation_never_dispatches` PASS；CLAIM_REJECTED:UNKNOWN_RESERVATION，0 claim |
| INT-03 | 未绑定 call_id | `test_int03_unbound_call_never_dispatches` PASS；UNBOUND_CALL |
| INT-04 | 重复 claim | `test_int04_duplicate_claim_is_zero_dispatch` PASS；ALREADY_CLAIMED，单 license |
| INT-05 | 两 broker 进程并发同 ID | `test_int05_two_broker_processes_race_one_license` PASS；仅 1 CLAIMED，其余 0 dispatch |
| INT-06 | 崩溃/SIGKILL 后 replay | `test_int06_sigkill_restart_does_not_replay_dispatch` PASS；重启后 ALREADY_CLAIMED |
| INT-07 | 同 call 不同 digest | `test_int07_same_call_different_digest_conflicts` PASS；CALL_ID_CONFLICT |
| INT-08 | 同 stream 换 reservation | `test_int08_same_stream_new_reservation_is_a_new_claim` PASS；新 call/reservation 新 claim，stream attempts 计数正确 |
| INT-09 | 新 logical step（模拟工具回灌） | `test_int09_new_logical_step_gets_new_identity_and_claim` PASS；新 call_id/claim |
| INT-10 | no/partial usage 不填 0 | `test_int10_no_or_partial_usage_never_uses_zero` PASS；WORST_CASE_HELD，cost≠0 |
| INT-11 | route/model/path/method 不匹配 | `test_int11_route_path_method_mismatch_never_claims` PASS；egress 拒绝，0 claim |
| INT-12 | Broker down/超时 | `test_int12_broker_down_yields_zero_dispatch` PASS；BROKER_UNAVAILABLE，0 dispatch |
| INT-13/14 | observation 幂等/冲突 | `test_int13_14_observation_idempotent_and_conflict` PASS；replay duplicate=True；不同 payload conflict 拒绝 |
| INT-15 | 伪造 AUTHORITATIVE 不结算 | `test_int15_forged_authoritative_never_settles` PASS；UNAUTHORIZED_OBSERVATION，reservation pending |
| INT-16 | 输出上限下游篡改 | `test_int16_tampered_output_is_not_silently_accepted` PASS；reservation_exceeded/blocked，不静默接受 |
| INT-17 | 意外第二 Attempt 0 发包 | `test_int17_second_call_for_same_reservation_is_rejected` PASS；RESERVATION_ALREADY_CLAIMED |
| INT-18 | 重启余额/claim 不减少 | `test_int18_restart_does_not_reduce_balance_or_claims` PASS；restart 前后 spent/committed 不变 |

> 说明：INT-13/14 在一个测试中分别覆盖幂等与冲突；所有 INT 的 broker 行为均通过真实 stdio Broker 子进程 + 同一真实 SQLite 文件验证，未使用 in-process 假 Broker/SQLite。

## 4. 回归与静态检查

- G2 定向：`tests/integration/sandbox/test_egress_boundary.py tests/integration/g2_closure/test_g2_closure.py` → **42 passed**。
- 全量回归（security unit+sandbox、accounting unit+budget_bridge、g2_closure）→ **367 passed / 1 skipped**（skip 为既有 `/input` 探针契约）。
- Ruff：scoped 与 repo-wide 均 **All checks passed!**（固定 OCI）。
- 未改 accounting/guard/adapter/gates/run_live；`git diff --check=0`；无 stage/commit。

## 5. 边界与残余 UNVERIFIED（必须承接 G2-BROKER 报告）

1. **本地 claim ≠ 远端 exactly-once**：本 PR 证明的是本机持久 claim 表在 SQLite 事务内唯一、重复/并发/重启不产生第二个本地 license；没有也无法证明 provider 侧/远端 only-once；真实 wire/usage/账单仍 UNVERIFIED。
2. **claim 成功后未发送 = 保守**：claim 只许可本地一次 send，若进程在 send 前崩溃，reservation/claim 保持 pending/CLAIMED，不自动退款、不自动重试；计入 worst-case，需要外部 reconciliation（未实现）。
3. **provenance 能力边界**：`TrustedEgressProvenance` 仍是同进程 capability/工厂（V-G1-3），不是密码学来源认证；G2 只把它限制在可信 harness/Controller 路径，未部署真实可信 egress/Key Broker，也未审计所有外部 import 点（后续 PR 工作）。
4. **FakeProvider 是 synthetic fixture**：无 socket、无 SDK/真实模型；ok/no/partial/timeout/disconnect/error/tampered 都是脚本结果，不能当作 provider wire/账单证据。
5. **OCI 无 socket**：真实网络、TLS、代理、重试、cache、Files 行为仍未观测；`network_attempts=0` 只说明未尝试外呼，不是远端安全证明。
6. **AUTH-08/Controller**：仍 inspect-only/恒 BLOCKED；本 PR 未新增任何 Live 入口，LiveGate/真实 Key 仍 BLOCKED，总体 DECISION PENDING，不签发 GO。

## 6. 证据

- `artifacts/m0-g2-integration/manifest.json`、`evidence.sha256`、`logs/`（targeted/full/ruff 的 argv/UTC/exit/stdout/stderr）、image-inspect、container absence、stage identity。
- 文件 hash：`src/autoteacher_m0/security/egress.py` = `2d1dfca1…`；`tests/integration/sandbox/test_egress_boundary.py` = `a2590fee…`；`tests/integration/g2_closure/test_g2_closure.py` = `2aa504d5…`（详见 manifest）。
- 验证：`cd artifacts/m0-g2-integration && sha256sum -c evidence.sha256`。
