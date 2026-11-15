# ADR-002：统一 CallIdentity 与持久原子 dispatch claim

- 状态：Accepted（G2-BROKER，无 Key 离线阶段）
- 日期：2026-11-15
- 背景 commit：G1 冻结 `70cb574`（实现基准父子链 `4d71530 → 70cb574`）；本 ADR 与实现同处 G2-BROKER 未提交工作树。
- 决策范围：accounting/CallIdentity 与 broker claim；**不涉及**真实 Key/HTTP/Live 解锁，不把离线 claim 说成远端 exactly-once。

## 1. 背景与问题

G1/PR4b 已有 `observation.CallIdentity`（`call-<48hex>`）与 PR4b 可选 `reserve.call_id` + `budget_call_links`，但存在两个缺口：
1. identity 定义分散在 `observation.py`，egress 旧实现可自行派生 `eg-...` 事件 ID，存在把它当结算 ID 使用的风险；没有单一 canonical 模块/校验责任。
2. Broker 只有 reserve 的“预算预留”，没有持久、原子、单次使用的 dispatch claim；无法证明“同一 call_id 在本地至多获得一次可计费发送许可”，也无法在崩溃重启后阻止 replay 二次许可。

## 2. 决策

### 2.1 唯一 canonical identity

新增 `src/autoteacher_m0/accounting/call_identity.py`，为唯一 canonical 定义：

```text
call_id = "call-" + SHA256(canonical_json({
  "v": 1,
  "run_id": <trusted run id>,
  "logical_step": <int>,
  "attempt_index": <int>,
  "request_digest": <sha256 hex of canonical request bytes>
}))[:48]
```

- `request_digest` 覆盖模型/渠道/消息/工具/输出上界等影响计费关键字节；日志只保存 digest，不保存原文。
- `reservation_id` **不参与** call_id 计算，避免“先预留还是先算 ID”的循环依赖。
- `observation.py` 保留兼容 re-export（`CallIdentity`/`derive_call_id`），旧 import 不破坏；`call_identity.py` 是唯一实现来源。
- 校验：`CALL_ID_PATTERN = ^call-[0-9a-f]{48}$`；`REQUEST_DIGEST_PATTERN = ^[0-9a-f]{64}$`；`run_id` 有界且禁止控制字符；负/超大 step/attempt 拒绝。

### 2.2 生成与校验责任

| 角色 | 责任 |
|---|---|
| Trusted Controller / Bridge | 预留前生成并复核 `run_id/logical_step/attempt_index/request_digest/call_id`；拒绝不可信文本指定的 run_id |
| Broker | **只接受** canonical `call_id`；reserve 的可选 `call_id` 与 claim 的 `call_id` 非 canonical → `INVALID_CALL_ID`；校验 call_id 与 reservation 的 durable link |
| Egress | 只接收并校验 canonical call_id（不自行派生结算 ID）；旧 `eg-...` 仅可作 `legacy_egress_event_id` 日志字段，**不参与** reserve/claim/settle/observation |
| Observation | 沿用同一 canonical call_id 关联结算；不另造 ID |

### 2.3 Broker `claim`（additive v1 op）

请求：`{"v":1,"id":<msg>,"op":"claim","call_id":"call-<48hex>","reservation_id":<id>,"request_digest":"<64hex>"}`。

同一 SQLite 事务内依次验证并写入：

1. scope 存在且未 blocked；
2. reservation 存在、状态 `PENDING`、reserved cost 未超 per-call（授权/预算上界）；
3. `call_id` 与 reservation 的 durable call link 一致（未绑定 → `UNBOUND_CALL`；指向其他 reservation → `CALL_LINK_MISMATCH`）；
4. `(scope_id, call_id)` 无既有 claim；同一 call 已 claim 且 reservation/digest 相同 → 幂等 `ALREADY_CLAIMED`（`dispatch_allowed=false`）；digest 不同 → `CALL_ID_CONFLICT`；
5. `(scope_id, reservation_id)` 无其他 call 的 claim（`RESERVATION_ALREADY_CLAIMED`）；
6. 写入独立表 `budget_dispatch_claims`（`PRIMARY KEY(scope_id, call_id)`，`UNIQUE(scope_id, reservation_id)`），状态 `CLAIMED`。

- **一条 reservation 在 M0 只许可一次 Attempt**；没有自动 retry/退款/释放。
- claim 成功但未发送：claim 行保持 `CLAIMED`、reservation 保持 `PENDING` → 保守视为 **SETTLEMENT_UNCERTAIN**；settle/fail 仍幂等，settle/fail 后 claim 标记 `COMPLETED`。
- 并发：SQLite `BEGIN IMMEDIATE` + DB 唯一约束保证只有一个进程拿到 `dispatch_allowed=true`；另一方得到 `ALREADY_CLAIMED`/conflict，不产生第二个许可。
- 崩溃/重启：claim 行持久；重放同一 claim 不授权；`snapshot` 增加 additive `claims:{total,pending,completed}` 可观察。
- claim **不写入 message journal**：它有自己的唯一表/事务，不消耗固定完成容量，也不会因 journal replay 变成第二许可；这是 v1 内的 additive op，旧 v1 客户端从不发送它，行为不变。
- 明确错误码：`INVALID_CALL_ID`、`INVALID_REQUEST_DIGEST`、`UNKNOWN_SCOPE`、`SCOPE_BLOCKED`、`UNKNOWN_RESERVATION`、`RESERVATION_NOT_PENDING`、`ROUTE_BLOCKED`、`BUDGET_BOUND_BLOCKED`、`UNBOUND_CALL`、`CALL_LINK_MISMATCH`、`ALREADY_CLAIMED`、`CALL_ID_CONFLICT`、`RESERVATION_ALREADY_CLAIMED`、`CLAIM_RACE_LOST`。

### 2.4 与 Observation/结算的集成

- claim 通过同一 `(scope_id, call_id)` 与 `budget_call_links`/`budget_provider_observations` 关联；`ledger.claim_for_call()` 可查询；`snapshot.claims` 可观察。
- 可信 observation 结算成功后，对应 claim 标记 `COMPLETED`（同一事务/嵌套 savepoint）；UNKNOWN observation 保持 claim `CLAIMED` + reservation `PENDING`。
- 不填 0、不退款、不自动重试；claim 不是远端计费证明。

## 3. v1 兼容策略

- `snapshot/reserve/settle/fail` 旧字段与语义不变；`reserve.call_id` 仍是可选字段（老客户端不发时行为与 PR1/PR4b 相同）。
- 新能力仅通过 additive `claim` op 暴露；不静默改变旧字段含义，不需要改旧客户端。
- 唯一可见变化：`reserve.call_id` 若发送则必须 canonical（PR4b 已引入该字段；G2 起拒绝 `eg-`/任意字符串为非 canonical 身份，属于收紧未授权 ID，不影响不发该字段的旧客户端）。
- `snapshot` 增加 additive `claims` 对象；旧读取方忽略未知键即可。

## 4. 后果与开放项

- 正向：本地“一次发送许可”可审计、可重启验证；identity 单一来源；伪造/误用 `eg-` 不再能作为结算 ID。
- 代价：一次 reservation 只有一个 Attempt；需要额外 retry 时必须新 step/新 reservation（符合 M0 关闭自动 retry 的方向）。
- **UNVERIFIED/开放**：真实 HTTP 发送、ACK 丢失、远端是否已扣费仍不可由本地 claim 保证；真实 provider wire/usage/invoice 未验证；G2-EGRESS 必须把 claim 放在任何 socket/传输调用之前，并把可信 observation 与 claim 状态串联；真实验签/Controller 生成 identity 的集成属 G5。
