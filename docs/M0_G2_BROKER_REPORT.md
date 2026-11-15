# M0 G2-BROKER 报告：统一 CallIdentity 与持久原子 dispatch claim（无 Key）

> 任务：task-65。基准：G1 冻结 `70cb574`（G1-SEC `842583d` → G1-ACC `00df577` → B-G1-1 `4d71530` → G1 docs `70cb574`）。本文只记录**离线无 Key**实现与证据；真实 provider wire/HTTP/账单与 Live 仍 **UNVERIFIED/BLOCKED**。未提交 Git。

## 0. 交付摘要

| 文件 | 变化 |
|---|---|
| `src/autoteacher_m0/accounting/call_identity.py` | **新增** canonical `CallIdentity`/`derive_call_id`/`validate_call_id`；`call-<48hex>` + request_digest 校验；`eg-` 非 canonical 拒绝。 |
| `src/autoteacher_m0/accounting/observation.py` | 最小改：identity 实现迁出并兼容 re-export；`ObservationSchemaError` 与 canonical 模块共用；observation 结算成功时把对应 claim 标记 `COMPLETED`。 |
| `src/autoteacher_m0/accounting/ledger.py` | **新增** additive `budget_dispatch_claims` 表、`claim_dispatch()` 单事务校验+唯一写入、`claim_for_call()`、`mark_claim_completed()`、`snapshot.claims`。无旧表/旧语义改动。 |
| `src/autoteacher_m0/accounting/broker.py` | **新增** additive v1 op `claim`（不写 journal、DB 唯一约束）；reserve 的 `call_id` 收紧为 canonical；settle/fail 后 claim 标记完成。旧 op 行为不变。 |
| `tests/unit/accounting/test_call_identity.py` | 身份 canonical/稳定/单射/legacy `eg-` 拒绝/兼容 re-export。 |
| `tests/integration/budget_bridge/test_g2_dispatch_claim.py` | 真实 SQLite + 真实 stdio Broker 子进程：INT-01/04/05/06/07/08/12/13/14/18 定向测试。 |
| `docs/ADR-002-unified-call-identity.md` | 决策/责任/协议/兼容/开放项。 |
| `docs/M0_G2_BROKER_REPORT.md` | 本报告。 |
| `artifacts/m0-g2-broker/` | argv/UTC/exit、fail-first/pass 日志、镜像/rootfs/deps、容器 absence、manifest/evidence。 |

**未改**：security/egress/guard/adapter/LiveGate/run_live、历史证据、G1 冻结文件字节、package/lock。

## 1. 问题/旧行为

- canonical identity 仅存在于 `observation.py`，没有单一模块；egress 旧 `eg-...` 事件 ID 与结算 ID 边界未在 broker 强制。
- Broker 只有 reserve 预算预留，没有任何持久“单次发送许可”：崩溃重启/replay 无法证明同一 `call_id` 的第二次 dispatch 被拒绝；`snapshot` 无 claim 可观察。
- 无 claim 表/唯一约束，多进程并发无法由 DB 强制“一 call 一 attempt”。

## 2. 修复

1. **canonical identity 模块**：`call_identity.py` 成为唯一实现；`observation.py` re-export 保持旧 import 兼容；broker 对 `reserve.call_id` 与 `claim.call_id` 强制 `call-[0-9a-f]{48}`；`eg-...` 仅可作为 legacy 日志字段（broker 拒绝为 `INVALID_CALL_ID`）。
2. **持久 claim**：`claim_dispatch` 在单事务内验证 scope 未 blocked、reservation PENDING、route 在批准集合、reserved cost 未超 per-call、call link 一致、未 claim；随后写 `budget_dispatch_claims`（`PRIMARY KEY(scope_id,call_id)` + `UNIQUE(scope_id,reservation_id)`）。重复同 claim → `ALREADY_CLAIMED`（`dispatch_allowed=false`）；同 call 不同 digest → `CALL_ID_CONFLICT`；同 reservation 换 call → `RESERVATION_ALREADY_CLAIMED`；未绑定 → `UNBOUND_CALL`；跨 reservation → `CALL_LINK_MISMATCH`。
3. **一次 Attempt**：claim 成功返回唯一 `dispatch_allowed=true`；崩溃后 claim 行保持 `CLAIMED`、reservation 保持 `PENDING`（保守 UNCERTAIN）；settle/fail 幂等并把 claim 标记 `COMPLETED`；不自动 retry/退款。
4. **不占 journal**：claim 有独立表/事务，不写 `budget_broker_messages`，不消耗固定 message 容量；这是 additive v1 op，旧客户端不发送它，旧行为不变。`snapshot` 增加 additive `claims`。
5. **observation 集成**：同一 call_id 关联 claim/observation；可信 observation 结算后 claim 完成；UNKNOWN → pending。

## 3. 协议兼容（broker v1）

- `snapshot/reserve/settle/fail`：字段/响应/幂等/容量语义不变；旧客户端不发 `call_id` 时行为与 PR1/PR4b 完全一致。
- `reserve.call_id` 为 PR4b 已有可选字段；G2 起若发送则必须 canonical（拒绝 `eg-`/任意字符串），不影响不发该字段的旧客户端。
- 新增 `claim` op 与 `snapshot.claims` 均为 additive；无需 `protocol_version` 升版。claim 不写 journal，因此不改变 F2 的 reserve 容量分配。
- 旧 `eg-...` 不作为任何结算/claim ID；仅在 egress legacy 日志字段可保留（不在本任务实现）。

## 4. 测试与 INT 矩阵（固定 digest、无 Key、禁网 OCI）

- **fail-first**（旧 broker + 新测试，全部在隔离 OCI）：
  - identity 单测：**1 collection error**（`No module named call_identity`）；
  - claim 集成：**9 failed**（旧 broker 不识别 claim，全部 `INVALID_MESSAGE`/无 claim 字段）。
- **实现后 targeted**：`14 passed`（5 identity + 9 claim）。
- **实现后全仓回归**：`510 passed, 1 skipped`（含 accounting、budget_bridge、PR1/phase5 相关历史测试；唯一 skip 为既有环境 skip）。
- **Ruff**：scoped changed files `All checks passed!`（仓库无新增 lint 错误；本证据仅 scoped）。
- 覆盖：INT-01 单次 claim→settle→claim completed；INT-04 重复 claim 不再授权；INT-05 两个真实 broker 进程并发仅一个 `dispatch_allowed=true`；INT-06 claim 后 SIGKILL/重启 replay 不二次授权且可保守 settle；INT-07 同 call 不同 digest → `CALL_ID_CONFLICT`；INT-08 同 stream 换 reservation → `CALL_LINK_MISMATCH`/`UNBOUND_CALL`；INT-12 blocked scope / broker 断开不授权；INT-13/14 observation 幂等/冲突与 claim completed；INT-18 重启余额/统计不无故减少；legacy `eg-` 拒绝。
- 测试使用真实 SQLite 文件 + 真实 `python -m ...broker` stdio 子进程；并发用两个真实进程；无 in-process mock 替身 Broker/SQLite。

## 5. 证据（artifacts/m0-g2-broker/）

- `manifest.json` + `manifest.sha256`；`evidence.sha256` 覆盖 manifest 与 raw 文件；raw 含 `commands.jsonl`（完整 host argv/UTC/exit）、`failfirst*.log`、`targeted1/2`、`full1/2/3`、`ruff*`、`container-absence.txt`、`git-state.txt`。
- 固定 rootfs `25491e45…`、deps `e07729d7…`；`--network none`、uid 65534、read-only rootfs、cap drop ALL、no-new-privileges、tmpfs noexec；0 真实 Key/模型/HTTP，未读 `/root/.config/autoteacher`。
- 未 stage/commit；工作树保留 G2-BROKER 实现 + 文档 + artifacts，供后续易审。

## 6. 边界与残余 UNVERIFIED

1. **本地 claim ≠ 远端 exactly-once**：claim 只保证本地至多一次“可发送许可”；HTTP 已发出但响应丢失/远端已扣费仍未知，禁止自动重发，必须保守 UNCERTAIN/人工对账。
2. **真实 provider wire/usage/invoice** 未验证；FakeProvider/真实 HTTP/socket 不在本 task（属 G2-EGRESS）。
3. **G2-EGRESS 接线未做**：egress 必须在任何传输调用前调用真实 stdio broker `claim`，否则“一次 Attempt”性质不成立；Controller/Bridge 生成 canonical identity 的真实实现属 G5。
4. **授权状态**：本 task 的 broker 侧“授权状态”指 synthetic offline scope 未 blocked + 批准 route + budget bound；真实 Controller 授权/签名/版本校验属 G2-EGRESS/G5。
5. **claim 未写 journal**：这是有意设计（避免容量/F2 语义变化），但 claim 审计依赖独立表；G2 审计应确认该表备份/恢复与 observation 关联。
6. 未改 `broker.py` 的旧 journal 语义；若未来需要多 Attempt retry，必须显式新 reservation/new step，而非复用同 claim。
7. 未提交/未 stage；后续由 sdk-docs/broker-docs 冻结（以 Lead 指示为准）。
