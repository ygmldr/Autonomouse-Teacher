# M0 G4-F3 — 费用权威语义与 unknown-cost held（No-Key）

- **任务**：G4-F 指令 F3 —— `TrustedSendGate.snapshot().worst_case_held_usd` 恒 0（P2-5）根因处置；
  冻结“Broker 唯一费用权威 / egress 保守视图”语义并实现、测试、取证。
- **基线**：`bb2e914`（工作区 clean，起点已核实）。
- **实现提交**：见 §8（本文件随 docs 提交）。
- **性质**：**no-key / no-model / no-network / no-live**。0 真实 Key、0 模型调用、0 外部 HTTP/TCP、
  0 真实计费；未执行 `podman pull`；全部 synthetic fixture；`LiveGate` 仍 BLOCKED。
- **明确不声明**：本文件不构成 G4 Full / E5-PreLive Full / G5 / Live 授权，不改变
  `G4-H-01..06 = BLOCKED`、`M0 = DECISION_PENDING`。

---

## 0. 结论摘要（先冻结，后实现）

| 项 | 冻结结论 |
|---|---|
| 费用权威 | **Broker `budget_reservations` 的 Reservation/Settlement 是唯一费用权威**；Attempt/Receipt/Usage 只是证据 |
| egress 角色 | `TrustedSendGate` 的 `known_cost_usd`/`worst_case_held_usd` 是**进程内只读保守视图**，不参与最终计费、不反向修改 Broker |
| unknown-cost | 无 usage / 部分 usage / timeout / hang / disconnect / EOF / provider 异常 / 取消 / 超时 / 崩溃 → `held = 保守上界（>0）`，视图状态对齐 Broker `PENDING`；**永不 0 / FREE** |
| 释放时点 | 只有**Broker 权威终态 + 合法 cost**（`OK` / `FAILED`；含 `ALREADY_SETTLED`/`ALREADY_FAILED` 归档）才 `held→0` 且 `known += cost`，且每 reservation 最多一次 |
| 双计 | 同 reservation 重复 authorize/consume/status/settlement 不重复累加；replay 不产生新 hold/settle |
| 崩溃 | 进程内视图随进程消失；新进程以 Broker 状态 reconcile，PENDING → held=`reserved_cost`，终态 → known；Broker 始终是权威 |
| 协议 | **未新增/未修改 Broker 协议 op**，未改 Reserve/Claim/Settle/Fail 语义，未改 G3-C/D 账本状态机 |

---

## 1. 权威链（Authority Chain）

```text
Broker (唯一费用权威)
  budget_reservations: PENDING → cost = reserved_cost（保守上界）
                       OK/FAILED → cost = usage 权威时 actual，否则 estimated
  budget_scopes / settlement_json / snapshot  → 权威 committed/reserved/spent
        │
        │  只读转交（reservation_status / settle|fail reply / reconcile）
        ▼
TrustedSendGate 费用视图（保守、只读、进程内）
  known_cost_usd   = Σ 已由 Broker 终态确认的 cost（OK 与 FAILED 都计入 committed）
  worst_case_held_usd = Σ 尚未由 Broker 终态确认的 reservation 的持有额
  视图不是计费输入；不含 usage→价格换算；不回写 Broker
        │
        │  证据（绝不是费用权威）
        ▼
Attempt Journal / Fake Receipt / Usage Observation
  记录“发生过什么”，供恢复与审计；不得据此把 PENDING 改写成 FREE
```

1. **Broker 是唯一费用权威**：`BudgetLedger.reserve()` 在持久事务中写入
   `cost = reserved_cost`；`settle()/fail()` 在持久事务中写最终 `cost` 与 `blocked`。
   `snapshot()` 的 `spent_usd/reserved_usd/committed_usd` 都来自该表。
2. **Attempt/Receipt/Usage 是证据**：`attempts.sqlite3`、Fake receipt、
   `ProviderObservation` 描述发送是否发生、usage 是否完整；它们决定调用
   `settle` 还是 `fail`，但绝不自行给出最终费用。
3. **`TrustedSendGate` 是保守视图**：`known/held` 只从 Broker 的
   `reserved_cost` / settlement `cost_usd` / `status` 复制；不含价格表、
   不做 usage 计价。视图即使全部丢失（崩溃），也只影响可观测性，
   不影响已持久化的费用。
4. **PR4a `EgressBoundary` 的 per-stream 计数**是 transport 证据计数
   （`record_outcome`），与 gate 视图相互独立，同样不是计费输入。
5. **禁止“第二套权威”**：egress 不读取/缓存价格、不按 token 估算金额、
   不因 usage 完整就自行把某笔调用标成最终费用；所有金额必须能追溯到
   Broker 的 `reserved_cost` 或 settlement `cost_usd`。

---

## 2. 视图状态模型

`TrustedSendGate` 以 `reservation_id` 为键，每个 reservation 至多一条视图：

| 视图状态 | 触发 | held | known | broker_status |
|---|---|---|---|---|
| `HELD` | `authorize()` 成功；`consume()`；Broker `PENDING` | `max(声明 cost, 保守上界)`；观察到 Broker 后取 `reserved_cost` | 0 | `PENDING` |
| `SETTLED_KNOWN` | Broker `OK` + 合法 cost / `ALREADY_SETTLED` | 0 | `+= cost`（一次） | `OK` |
| `SETTLED_CONSERVATIVE` | Broker `FAILED` + 合法 cost / `ALREADY_FAILED` | 0 | `+= cost`（一次） | `FAILED` |
| `HELD`（保留） | 终态但 cost 缺失/非法；Broker 不可用；状态冲突 | 保持原值（>0） | 0 | `PENDING`/`UNKNOWN` |

- **保守上界**：`authorize()` 未收到 Broker 上界时取
  `max(声明 estimated_cost_usd, SyntheticSendBudget.hard_call_usd)`；
  controller 接线后传入 Broker Reserve 返回的 `reserved_cost`（权威上界，
  任何合法 settlement 都不会超过它），视图取二者较小但非零的权威值。
- **FAILED 也计入 known**：Broker 的 FAILED settlement 仍写最终 `cost`
  （无 usage 时 `max(cost, reserved_cost)`），属 committed，不是退款；
  若把它排除，`known+held` 就会低于 Broker `committed_usd`。
- **状态冲突**：已终态的 reservation 再收到不同状态/不同 cost →
  记录 `BROKER_SETTLEMENT_CONFLICT` 事件，**不改变总额**（fail-closed，
  保持 first-writer 的权威结果，等待人工对账）。

---

## 3. unknown-cost 规则（冻结）

以下情形全部属于 **unknown-cost**，视图必须 `held > 0` 且保持未释放：

| 情形 | 证据状态（Attempt） | egress 视图 |
|---|---|---|
| 200 无 usage / 部分 usage | `BILLABLE_UNKNOWN` | `HELD` |
| timeout / hang / disconnect / EOF | `BILLABLE_UNKNOWN` | `HELD` |
| 5xx | `BILLABLE_UNKNOWN` | `HELD` |
| provider 抛异常 / 结果非法 / 进程中断 | `BILLABLE_UNKNOWN` | `HELD` |
| 取消（发送前/发送后）| `SETTLEMENT_UNCERTAIN` | `HELD`（Broker 未 settle） |
| deadline | `SETTLEMENT_UNCERTAIN` | `HELD` |
| crash（authorize/consume/settle ack 丢失） | 持久 Attempt/Intent 或仅 Broker PENDING | 新进程 reconcile 后 `HELD` |
| Broker 不可用 / 状态未知 | — | `HELD`（不释放） |
| settlement 回复丢失 | `SETTLEMENT_UNCERTAIN` | `HELD`；重读 Broker 终态后释放 |

**对齐**：`HELD` ↔ Broker `PENDING`（或 `reservation_status` 不可得 =
“不确定”）；`SETTLED_*` ↔ Broker `OK/FAILED`。不存在“egress 已释放但 Broker
仍 PENDING”的路径：释放只由 Broker 终态驱动。

**绝不 FREE**：以下都不会把 held 归零：
- 收到 200 但 usage 缺失；
- 收到 4xx（`NOT_BILLABLE_HTTP_ERROR` 只是 egress 证据分类，Broker 仍需 settle/fail；
  在 Broker 终态前 reservation 仍是 PENDING，视图仍 held）；
- 取消/超时/断连；
- Broker 状态查询失败；
- settlement 回复丢失；
- 进程崩溃（新进程从 Broker PENDING 重建 held）。

---

## 4. 更新 / 释放时点（冻结）

| 时点 | held | known | 说明 |
|---|---|---|---|
| `authorize()` 成功 | `+=` 本 reservation 的保守上界 | 不变 | 第一处可能“已发出”的时点；必须在发送前置持有 |
| `authorize()` 拒绝 | 不变 | 不变 | 被拒调用不产生 hold（含 per-call / hard-total / claim 拒绝） |
| `consume()` 成功 | 不变 | 不变 | 能力已消费，发送可能已发生；只加审计事件 |
| `consume()` 失败（过期/重放/字节不符） | 不变 | 不变 | reservation 仍 PENDING；不释放 |
| `record_outcome()`（transport 证据） | per-stream `worst_case_held_usd` 幂等 `+=` | per-stream `known_cost_usd` 幂等 `+=` | 仅证据计数；同一 attempt 重复调用只记一次 |
| Broker `PENDING` 只读状态 | 置为本 reservation 的 `reserved_cost`（权威上界；>0） | 不变 | reconcile/status；用于崩溃后与 Broker 对齐 |
| Broker `OK` + cost | 归零 | `+= cost`（一次） | 正常 settle；`ALREADY_SETTLED` 走同一归档 |
| Broker `FAILED` + cost | 归零 | `+= cost`（一次） | fail 仍 committed；`ALREADY_FAILED` 同 |
| Broker 终态但 cost 缺失/非法 | **不归零** | 不变 | `BROKER_COST_UNKNOWN`；保守 |
| 同 reservation 重复终态 | 不变 | 不变 | `ALREADY_RECORDED`；同状态同金额幂等 |
| 同 reservation 冲突终态/金额 | 不变 | 不变 | `BROKER_SETTLEMENT_CONFLICT`；审计 |
| reconcile（新进程） | 由 Broker 状态重建 | 由 Broker 状态重建 | 只覆盖 durable intent/attempt 记录的 reservation |
| crash / replay | 视进程内丢失；Broker 不变 | 同左 | 重放 `ATTEMPT_ALREADY_STARTED` 时不进入 reserve/authorize |
| 并发 authorize | 锁内 check+hold 原子 | 不变 | 不重复、不超 `hard_total`；Broker 自身仍串行权威 |

**并发语义**：gate 内 `check(known+held+cost ≤ hard_total)` 与 `hold` 在同一把锁内完成；
Broker 的 Reserve 由 SQLite `BEGIN IMMEDIATE` 串行。gate 的检查只是发送前
admission（fail-closed），不是费用权威；Broker 拒绝时 controller 不会调用
`authorize()`，因此不会产生 hold。

---

## 5. `snapshot` 字段语义（冻结）

`TrustedSendGate.snapshot()` 保留既有 schema 字符串 `m0.g4c.send-gate.v1` 与
既有字段（additive 变更），并新增 `cost_view`：

| 字段 | 语义 |
|---|---|
| `known_cost_usd` | **Broker 已确认终态**的 cost 之和（OK+FAILED）；不是 authorize 估算、不是 usage 计价 |
| `worst_case_held_usd` | **未由 Broker 终态确认**的 reservation 保守持有额之和；`>0` 表示仍有未决费用 |
| `committed_usd`（`cost_view`） | `known_cost_usd + worst_case_held_usd`，与 Broker `committed_usd` 在同 reservation 集合上可对账 |
| `cost_view.schema` | `m0.g4c.cost-view.v1` |
| `cost_view.authority` | 恒 `broker_reservation_settlement` |
| `cost_view.role` | 恒 `conservative_read_only_view`；`billing_authority=false` |
| `cost_view.scope` | `process_local`（崩溃即消失，Broker 不受影响） |
| `cost_view.reconciled_with_broker` | 最近一次 Broker 状态观察的 `true/false` 与来源；未接线时 `false` |
| `cost_view.held_reservations` / `settled_reservations` / `unresolved_reservations` | 视图计数（按 reservation 去重） |
| `cost_view.reservations[]` | 每个 reservation 的 `state/held_usd/known_usd/broker_status/held_source/updated_utc/transitions` |
| `cost_view.events[]` | 有界转移审计（authorize/consume/status/settlement/replay/conflict） |
| `cost_view.invariants` | `known_nonnegative/held_nonnegative/no_free/no_duplicate_settlement/check_under_lock` 的自检布尔 |
| `sends_authorized` / `consumed` / `issued` | 既有语义不变 |

既有 `known_cost_usd` 旧语义（authorize 时把估算值计入）**废止**：authorize 只产生
held；已知费用必须来自 Broker 终态。该变更只影响 egress 视图，不改变 Broker 账本。

---

## 6. 不变量（实现与测试共同强制）

1. **I1**：`known >= 0`、`held >= 0`，金额为有限 Decimal；`held+known` 永不因异常为负。
2. **I2**：每 reservation 只有一条视图；一次 Broker 终态最多计入 known 一次。
3. **I3**：任一“已 authorize 且未获 Broker 终态”的 reservation，`held > 0`（unknown-cost 不 FREE）。
4. **I4**：释放只能由 Broker `OK/FAILED` + 合法 cost 触发；状态查询失败/回复丢失/冲突不释放。
5. **I5**：snapshot 的 `known/held/committed` 恒等于各视图求和（不存在独立累加器漂移）。
6. **I6**：视图是 process-local；崩溃后新进程不得把“看不到”当作“已结算”，必须以 Broker 状态重建。
7. **I7**：`authorize` 的硬顶检查与持有在同一锁内；超限时拒绝且不产生 hold（不超卖）。
8. **I8**：replay（同 call 第二次请求）在 controller 层 `ATTEMPT_ALREADY_STARTED` 即被拒绝，
   不触发 reserve/claim/authorize，因此 held/known 与 Broker 均不增加。

---

## 7. 范围与“不改”声明

- 只改：`src/autoteacher_m0/security/egress.py`（视图/记账/snapshot）、
  `src/autoteacher_m0/bridge/controller.py`（只读转交 Broker 状态/终态，最小接线）、
  新增 `tests/integration/g4_f3/`。
- **未改**：`gates.py`、`scripts/run_live.sh`、`runtime/dsh_adapter.py`、DSH 核心、
  G4-A/G4-C 冻结契约文件、Broker 协议 op、Reserve/Claim/Settle/Fail 语义、
  G3-C/G3-D 账本状态机、历史测试/证据。
- **未新增** Broker 协议 op（不枚举全 scope pending；只对 durable intent/attempt
  记录的 reservation 做只读 `reservation_status`）。
- 残余见 §9。

---

## 8. 实现与提交

### 8.1 改动面（最小 additive）

- **实现提交**：`3edf48c5dbab03e3a09f16748685c9d3918892ac`，
  父 `b97bf7285bdca7d8e1bbe5910955d5c14b00f4e8`（起点 `bb2e914`；期间并行 G4-F1 的
  2 个 docs/fix 提交进入共享 HEAD，未包含本包文件）。
- **未 amend / 未 push / 未 stage 他人文件**。

| 文件 | 改动 |
|---|---|
| `src/autoteacher_m0/security/egress.py` | `SendCostView` + `TrustedSendGate` 费用视图：`_hold_bound`、`_hold_reservation_locked`、`_settle_reservation_locked`、`record_broker_status`、`record_broker_settlement`、`cost_view`、`snapshot().cost_view`；`authorize(worst_case_usd=…)`；check+hold 同锁；`record_outcome` 每 attempt 幂等 |
| `src/autoteacher_m0/bridge/controller.py` | 只读转交：Reserve 的 `reservation.cost_usd` → `authorize(worst_case_usd=)`；`reservation_status` 回复 → `record_broker_status`；settle/fail 回复 → `record_broker_settlement`；`reconcile_on_startup` 对 pending attempt 做一次 view-only 状态观察。均为 try/except 包裹，视图记账异常不改变请求结果 |
| `tests/integration/g4_f3/` | 23 个 host 测试（15 gate 语义 + 8 真实 Broker/Fake controller 链） |
| **未改** | `gates.py`、`run_live.sh`、`dsh_adapter.py`、`cli.py`、Broker 协议/`Reserve/Claim/Settle/Fail`、`accounting/{broker,ledger}.py`（零改动）、G3-C/D 账本状态机、历史测试/证据/Packet |

**未新增 Broker 协议 op**：`reservation_status` 已是既有只读 op；本包只消费其回复。
`accounting/` 的“只读权威查询”能力已足够，不需要 additive 改动，因此没有改账本代码。

### 8.2 语义修正（P2-5 根因）

| 旧行为（`bb2e914`） | 新行为（`3edf48c`） |
|---|---|
| `authorize()` 把 `estimated_cost_usd` 直接加到 `_known_usd`（未结算的估算被当成 known） | `authorize()` 只创建 `HELD` 视图；金额 = `max(声明 cost, 传入上界)`，未传上界时用 `hard_call_usd`；`known=0` |
| `_held_usd` 从未累加 → `snapshot().worst_case_held_usd` 恒 `0` | `held` = 所有未获 Broker 终态的 reservation 的保守上界之和；unknown-cost 必 `>0` |
| known/held 是互不相关的累加器，可能与视图漂移 | 每次转移后由视图重算（`_refresh_cost_totals`），snapshot 字段恒等于各 view 求和 |
| 无 per-reservation 去重；重复 authorize/settle 可能双计 | 每 `reservation_id` 一条 view；终态每 reservation 只入账一次；重复 → `ALREADY_RECORDED`；冲突 → `BROKER_SETTLEMENT_CONFLICT` 且不改金额 |
| 无并发保护（check-then-add 可竞态） | 硬顶检查与 hold 在同一 `RLock` 内；并发 authorize 不超卖、不重复 |
| egress 不知道 Broker 状态 | `reservation_status` / settle/fail 回复只读复制到视图；`PENDING→HELD`、`OK/FAILED→known`；Broker 不可用/成本缺失 → 保持 hold |
| 终态无 cost 时可能被当作 0 | `BROKER_COST_UNKNOWN`，hold 不释放 |
| 已结算 reservation 可再次 authorize | `RESERVATION_ALREADY_SETTLED` 拒绝，且不产生新 hold/journal |
| transport `record_outcome` 重放会重复累加 | 以 `(call_id,reservation_id,attempt_ordinal)` 幂等；未知保持 `BILLABLE_UNKNOWN` |

**新增 snapshot（additive，schema 仍为 `m0.g4c.send-gate.v1`）**：

```json
"cost_authority": "broker_reservation_settlement",
"cost_view": {
  "schema": "m0.g4c.cost-view.v1",
  "authority": "broker_reservation_settlement",
  "role": "conservative_read_only_view",
  "billing_authority": false,
  "scope": "process_local",
  "reconciled_with_broker": true,
  "broker_view_source": "broker_status",
  "known_cost_usd": "...", "worst_case_held_usd": "...", "committed_usd": "...",
  "held_reservations": 0, "settled_reservations": 1, "unresolved_reservations": 0,
  "reservations": [{"reservation_id": "...", "state": "SETTLED_KNOWN",
                    "broker_status": "OK", "held_usd": "0",
                    "known_usd": "...", "held_source": "consume",
                    "known_source": "broker_completion", "transitions": 3}],
  "events": [{"kind": "HOLD|CONSUME|SETTLEMENT_OK|SETTLEMENT_FAILED|...",
              "utc": "...", "reservation_id": "...", "detail": {}}],
  "invariants": {"known_nonnegative": true, "held_nonnegative": true,
                 "no_free_unresolved": true, "one_view_per_reservation": true,
                 "totals_equal_view_sum": true}
}
```

字段语义见 §5。`known_cost_usd` 与 `worst_case_held_usd` 的**名称保留、语义按 §5 更正**：
既不参与计费，也不写回 Broker。

### 8.3 controller 接线边界

- Reserve：只读取 `reply["reservation"]["cost_usd"]` 并作为 `worst_case_usd` 传给
  `authorize()`；该值来自 Broker 的持久 reservation 行，不是 egress 自行定价。
- Status/settle：只把 Broker 回复的 `status/reserved_cost/cost/settlement.cost_usd`
  交给 gate；gate 不解析 usage、不计算价格。
- `reconcile_on_startup`：对每个 pending attempt 增加一次**只读** `reservation_status`
  观察（返回值丢弃），只为让新进程的视图看到 PENDING；本地恢复状态机不变。
- 所有 relay 都在 `try/except` 内；视图记账失败不会改变请求成功/失败，也不会让
  Broker 的 settlement 丢失（见 `test_settlement_relay_is_never_the_request_outcome`）。

---

## 9. 证据与回归

### 9.1 Host（L1；真实 Broker/Fake 子进程，无容器）

runner：`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:artifacts/foundation/deps \
python3 -B artifacts/g4f/f3/host/runner.py`，exit 0，8/8 case 通过，
`utc_start=2026-11-19T11:31:19Z`，`utc_end=2026-11-19T11:31:21Z`；
`host/cases.json` sha256 `e5a4ff83…`。明细见 `artifacts/g4f/f3/EVIDENCE.md`。

| case | held（前→后） | known（前→后） | Broker |
|---|---|---|---|
| `ok_usage` | `0.001583`（consume 时）→ `0` | `0` → `0.001022` | 1 OK，spent=committed `0.001022` |
| `no_usage` | `0.001583` → `0` | `0` → `0.001583` | 1 FAILED，仍 committed `0.001583` |
| `lost_ack_reconcile` | `0.001583`（=reserved）→ `0` | `0` → `0.001022` | PENDING→OK，spent 与 gate known 一致 |
| `replay` | `0` → `0`（第二次 `ATTEMPT_ALREADY_STARTED`） | `0.001022` 不变 | requests 1、Fake 1、无二次结算 |
| `broker_denial` | `0` | `0` | requests 0、Fake 0 |
| `crash_after_reserve` | 新进程 `0.001228`（=reserved） | `0` | 1 PENDING、reserved `0.001228`、Fake 0 |
| `crash_after_attempt` | 新进程 `0.001228`（=reserved） | `0` | 1 PENDING、reserved `0.001228`、Fake 0 |
| `concurrent_authorize` | `0.005`（5 允许/3 `HARD_BUDGET_CEILING_EXCEEDED`） | `0` | 无 Broker；5 个唯一 view |

每条 host case 目录含：`case.json`（argv/UTC/exit/gate snapshot/Broker snapshot/
reservation_status/attempt rows/负例 frames）、`broker.sqlite3`、`attempts.sqlite3`、
`receipts/` 只读副本。

### 9.2 真实双 Principal 容器（L2）

命令：

```text
python3 -B scripts/g4/run_g4_c.py --out-dir artifacts/g4f/f3/l2 \
  --only c01,replay,crash-before-send,crash-after-receive,quota,broker-down
python3 -B scripts/g4/run_g4_c.py --out-dir artifacts/g4f/f3/l2 --only c02,negatives
```

stage `stage-20261119T113229Z`：`base_sha=head=3edf48c`、manifest `d911e9dc…`、
trusted tree `6479ad8d…`、stage tree `925c68ef…`；rootfs `25491e45…`、deps `e07729d7…`
（均 canonical）。

| case | UTC | exit | checks | gate known | gate held | Broker DB（只读副本） | Fake |
|---|---|---:|---:|---:|---:|---|---:|
| `c01` | 11:32:54→11:33:01 | 0 | 18/18 | `0.001022` | `0` | 1 OK，spent=committed `0.001022` | 1 |
| `replay` | 11:33:01→11:33:16 | 0 | 9/9 | `0.001022` | `0` | 1 OK，requests 1 | 1 |
| `crash-before-send` | 11:33:16→11:33:31 | 0 | 12/12 | `0` | `0.001619` | 1 PENDING，reserved=committed `0.001619` | 0 |
| `crash-after-receive` | 11:33:31→11:33:47 | 0 | 13/13 | `0.001022`（恢复进程，sends 0） | `0` | 1 OK，spent `0.001022` | 1 |
| `quota` | 11:33:47→11:34:02 | 0 | 8/8 | `0.001022` | `0` | 1 OK；over-quota 无第二次 reserve | 1 |
| `broker-down` | 11:34:02→11:34:17 | 0 | 9/9 | `0` | `0` | 0 reservation | 0 |
| `c02` | 11:35:23→11:35:29 | 0 | 20/20 | `0.002044` | `0` | 2 OK，committed=spent `0.002044` | 2 |
| `negatives` | 11:35:29→11:35:44 | 0 | 8/8 | `0` | `0` | 0 reservation | 0 |

- **对账**：`known == Broker spent == committed`（c01/c02/quota/replay/crash-after-receive）；
  `held == Broker reserved == committed`（crash-before-send，PENDING）；
  broker-down/negatives 全 0。
- **crash-before-send**：恢复进程没有任何新 authorize（`sends_authorized=0`），
  但 reconcile 把 Broker 的 PENDING `reserved_cost` 变成 `held=0.001619`；
  Fake=0、Broker 行仍 PENDING。这是“崩溃后 held 与 Broker 一致、不 FREE、不双发”的 L2 证据。
- **crash-after-receive**：第一进程已发送（Fake=1、Broker OK），恢复进程只从
  Broker 终态归档 `known=0.001022`，没有第二次发送/结算；`sends_authorized=0`
  是恢复进程自身计数，不是“未发送”。视图事件为 `HOLD`（view-only PENDING）→
  `HOLD`（branch status）→ `SETTLEMENT_OK`。
- **replay**：同 payload 第二次 `ATTEMPT_ALREADY_STARTED`；Broker requests=1、Fake=1、
  `spent` 不变；gate view 不变（sends=1、consumed=1）。
- **quota**：max_calls=1，第二次请求在 reserve 前被拒；Broker 只有 1 个 OK reservation，
  gate 只有 1 个 view。
- `containers_after=[]`（两次批次）、`rootfs_canonical=true`、`deps_canonical=true`、
  `real_model_calls=0`、`real_external_http_calls=0`；无 `podman pull`。

### 9.3 负例

- `broker_denial`（host）：Broker per-call 拒绝 → `BUDGET_DENIED`、requests 0、held/known 0、Fake 0。
- `no_usage`（host）：`USAGE_MISSING`、Broker FAILED 仍 committed、gate known 等于该 committed。
- `lost_ack_reconcile`（host）：`SETTLEMENT_UNCERTAIN`；结算回复丢失时 held 保持、
  Broker 仍 PENDING；恢复后按 Broker OK 释放。
- `broker-down`（L2）：Broker 被 kill 后请求失败，0 reservation、0 hold、Fake 0。
- `negatives`（L2）：8 项（route/tool/file/network）拒绝，0 reservation、Fake 0。
- `test_settlement_relay_is_never_the_request_outcome`（host）：视图记账抛错时请求仍成功，
  gate 保持保守 hold，不会伪造 known。

### 9.4 回归与静态检查

命令（`-B` + `PYTHONDONTWRITEBYTECODE=1`）：

```text
PYTHONPATH=src:artifacts/foundation/deps python3 -B -m pytest -q \
  tests/integration/g4_a tests/integration/g4_b tests/integration/g4_c \
  tests/integration/g4_d tests/integration/g4_f3 tests/integration/g3c \
  tests/integration/g3d tests/integration/g3_bridge tests/unit/security/test_gates.py
```

**结果：686 passed / 1 failed / 1 warning，exit 1（约 191 s）。**

- 唯一失败为**已知 frozen-src 断言**：
  `tests/integration/g3d/test_d3_contract.py::test_runner_does_not_modify_product_src`
  （`git diff 4bd4803 -- src` 非空；G4 授权改码导致，历史报告已登记，不改测试）。
- 本包新增 `tests/integration/g4_f3/`：**23 passed**（15 gate 语义 + 8 controller 链）。
- `g4_c`：78 passed；`g4_a`、`g4_b`、`g4_d`、`g3c`、`g3_bridge`、`gates` 全过。
- G4-B `test_real_anchor_is_the_frozen_baseline` 通过（deps 复算 canonical）。
- ruff（pinned 0.17.5）：
  `ruff check src/autoteacher_m0/security/egress.py src/autoteacher_m0/bridge/controller.py tests/integration/g4_f3`
  → **All checks passed**。

### 9.5 真实计数

```text
real_provider_calls       = 0
real_external_http_calls  = 0
provider_keys_seen        = 0
billable_send_allowed     = 0
live_gate                 = BLOCKED
run_live_exit             = 3   (未变；本包未改 run_live.sh)
containers_after          = []  (L2 两批次)
podman_pull               = 0
```

---

## 10. 残余与边界（不夸大）

| ID | 残余 | 影响 / 处置 |
|---|---|---|
| **F3-R1** | L2 的 unknown-cost 只覆盖 crash→Broker PENDING（crash-before-send）；无 usage/timeout/断连的 L2 场景 | G4-C launcher 的 scenario→fake_scenario 映射没有 no_usage/timeout 入口，新增会改 launcher/测试钩子（超出 F3 写域）。这些路径在 L1 host 用真实 Fake 子进程覆盖；L2 用 crash PENDING 覆盖“held>0 且与 Broker 一致”。 |
| **F3-R2** | 视图是 process-local；Broker Reserve ack 与 intent 落盘之间的极小窗口不可枚举 | 该窗口内进程崩溃时，新进程没有 durable 记录可 reconcile，视图可能**低估** held；Broker 仍以 PENDING 全额占用，不会被超卖。未新增 Broker op 枚举全 scope pending（避免改协议）。 |
| **F3-R3** | `known_cost_usd` 含 FAILED settlement 的 committed cost | 这是“已知已提交费用”，不是“成功调用费用”；报告与 snapshot 已按 committed 表述，避免误读。 |
| **F3-R4** | 未接 Broker 上界的独立 gate 调用（测试/未来调用方）以 `hard_call_usd` 作为保守上界 | 偏保守（0.20 vs 实际 reserved ~0.0016），可能提前触发 `HARD_BUDGET_CEILING_EXCEEDED`；容器路径始终传 Broker `reserved_cost`，不受影响。 |
| **F3-R5** | Broker 不可用时 reconcile 无法建立/校验 hold | 已有 hold 不释放；新 reservation 可能无法入视图；`reconciled_with_broker=false` 可见。Broker 仍是权威。 |
| **F3-R6** | `record_broker_status` 信任 stdio/UDS 上 Broker 的回复，无独立签名 | 与既有 `reservation_status`/settle 回复同一信任边界；不是新增信任假设。 |
| **F3-R7** | 4xx `NOT_BILLABLE_HTTP_ERROR` 在 gate 视图仍保持 hold 直到 Broker 终态 | 有意保守；真正非计费 4xx 需由 Broker fail 归档后释放（真实路径会 settle/fail）。 |
| **F3-R8** | `_broker_status` 的 view-only 观察会让 reconcile 多一次只读 round-trip/行 | 只读、有 deadline；不改变恢复状态机。broker-down 时返回不可用并保持保守。 |
| **F3-R9** | L2 证据在 `artifacts/`（gitignored），不随提交分发 | 与 G4 历史一致；报告记录 argv/UTC/exit/DB/receipt/路径与 sha256。 |
| **F3-R10** | 未验证真实 Provider/真实计费/供应商额度 | 与 G4-H-04 一致，仍 BLOCKED；synthetic 费率不是真实价格。 |

---

## 11. P2-5 处置结论

- **P2-5 的“`snapshot().worst_case_held_usd` 恒 0”已消除**：authorize 即持有保守上界，
  unknown/崩溃/状态不可用保持持有，Broker 终态才释放；host 与真实双 Principal 容器均有
  `held>0` 证据（`crash-before-send` L2：`held=0.001619 == Broker reserved`）。
- **没有形成第二套费用权威**：gate 的 known/held 只复制 Broker 的 `reserved_cost`/`cost_usd`/`status`；
  不读价格表、不按 usage 计价、不写回 Broker；`accounting/` 零改动。
- **边界**：本结论限定于 synthetic fixture + 本轮 L1/L2 证据；不构成真实 Provider/计费验证，
  不改变 `LiveGate=BLOCKED`、`G4-H=BLOCKED`、`M0=DECISION_PENDING`。
- **STOP**：等待 Lead/独立 Reviewer 复核；不自行宣布 G4 PASS 或 Live 授权。
