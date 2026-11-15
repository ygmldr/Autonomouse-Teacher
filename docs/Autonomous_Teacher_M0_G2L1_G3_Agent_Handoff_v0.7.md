# Autonomous Teacher M0 — G2-L1 安全收口与 G3 Provider Bridge 交接任务书

> **版本**：v0.7 · 2026-11-16  
> **状态**：待交给 Coding Agent；不是实施报告、验收 PASS 或 Live 授权  
> **工作范围**：先执行 **G2-L1-FIX**（离线小 PR），经独立复核及维护者明确确认后，再执行 **G3-SPIKE / G3-INTEGRATION**（无 Key、受控模拟）。**禁止自动进入 G4、G5、G6。**  
> **上位规范**：`docs/Autonomous_Teacher_M0_v04.md`（强制 M0 验收），`docs/Autonomous_Teacher_M0_Execution_Validation_Review_Playbook_v0.6.md`（G0–G6 流程）；本文件只对当前已完成 G0–G2 的**下一轮实现任务**做具体化，不覆盖、放宽前述规范。  
> **技术原则**：DeepSeek Harness（DSH）继续作为待验证主 Runtime；保留 AgentRuntime 业务 ABI；固定目标模型，不进行模型重新选型；G2 阶段既有 `PASS_FOR_DECLARED_G2_SCOPE` 保持原声明范围，不伪造新结论。

---

## 0. 给执行 Agent 的第一屏：现在做什么

**立即允许执行：G2-L1-FIX，一轮离线修复、定向回归、冻结与 Review Packet；然后 STOP。**

**后续仅在维护者明确批准 G3 后执行：真实 DSH Runtime + 公共 Provider 插件 + 受控 IPC + FakeProvider + Broker 的联合联调；完成后再次 STOP。**

**本次绝不允许：**接触真实 Key、调用真实 DeepSeek/OpenCode Go API、打开 LiveGate、删除现有 `SECURITY_BLOCKED`、在不可信候选环境注入凭据、直接把 DSH 放进有任意出网权限的容器、修改冻结历史证据、以 Mock/Fixture 结果冒充真实模型或真实 OS 网络证明。

### 建议按两个独立交接批次推进

| 批次 | 执行状态 | 目标 | 是否可自动开始 | 交付后是否停机交审 |
|---|---|---|---|---|
| **A：G2-L1-FIX** | **现在执行** | 去除无 Claim 放行路径、严格 Policy、必要的请求绑定、更新测试、报告 | 是：仅限无 Key 隔离 | **必须 STOP** |
| **B：G3-SPIKE / G3-INTEGRATION** | **待批准** | 真实 DSH SDK/工具/Session 经 Provider Bridge、IPC、Broker、FakeProvider；外部边界无 Key 演练 | **仅 A 独立 PASS + 维护者新批准后** | **必须 STOP** |
| C：G4 PreLive | 不属于本轮 | 独立可信控制器与操作系统安全部署，真实 E5 PreLive | 否 | 人审 |
| D：G5–G6 | 不属于本轮 | 实际模型/Usage/账单/评估/ADR | **单独的真人凭据与执行批准** | 人审 |

### 本轮绝对优先级

1. **P0**：`egress.py` 三条 legacy 路径不得被任何正式 Dispatch 入口当成许可；无 Claimer 必须 fail-closed。
2. **P0**：将合法的 Policy 描述符与实际可计费 Dispatch Permission 区分；`reserve.dispatch_allowed=True` **不是** `claim`。
3. **P0**：Bridge 准备发送的真实请求与 `call_id` / `request_digest` / Reservation Route/Model 必须由可信端重新绑定；尤其验证“Reservation=A，实际发送=B”。
4. **P1**：严格 JSON Policy 类型、避免 bool 冒充 int、修正测试残留 Broker 子进程与 Snapshot 错误归因。
5. **P1**：G3 通过公开 Provider 扩展运行真实 DSH/SDK/skill/Session，以零真实模型调用验证 IPC 与受控出口能否工作。

**不要再做**：重跑 G0–G2 所有旧实施任务、重写 Ledger、主动增加 RSI/Teacher 功能、做新的模型性能对比、为了增加用例数而扩大审计范围。

---

## 1. 已有事实、冻结基线与证据边界

### 1.1 已经发生的工作（无需重做）

- **G1**：最终独立审阅记载 `G1_FINAL_PASS_FOR_DECLARED_SCOPE_WITH_ERRATA`，原 `B-G1-1` 预算 Policy 绑定缺口经修复与 Addendum 关闭；限无 Key 离线范围。G1 修复身份 `4d715305022bdbaa437488a7224d33305324f034`。
- **G2**：独立审阅记载 `PASS_FOR_DECLARED_G2_SCOPE`；G2-BROKER `ada8e28d7afb6a5c7cbca0a16ae955ec3b22578b`，G2-EGRESS **最终代码** `32bea5bcf8d35d778a54c04cebb0ae08fb1f849c`。
- G2 已加入 `accounting/call_identity.py`，使用 canonical `call-` ID；Ledger/SQLite 中的持久 `budget_dispatch_claims` 以事务和唯一约束实现本地单次许可；Broker v1 新增 `claim`，但 `reserve` 为兼容保留旧 `dispatch_allowed` 字段。
- G2 独立测试包括真实 SQLite、真实 stdio Broker、两个进程争夺 Claim、SIGKILL/重启、重复 Claim 与 Observation 关联；**并非真实网络、真实模型或真实账单**。
- G2 审计明确遗留 **G2-L1**：`authorize()`/`require()`/无 Claimer 回退仍可能产生描述符级 `allowed=True`；此项在 G3 或 Live 接线前必须关闭。
- 当前整体：**M0 `DECISION PENDING`，Live/真实 Key/真实外呼仍 `BLOCKED`**。G2 本地一次 Claim ≠ 远端 exactly-once / 远端只有一次计费。

### 1.2 必须先在仓库中核验，而不是照抄旧行号

**让 Agent 在实际仓库内先确认如下文件存在、记录 SHA/Git blob，然后再改：**

```text
src/autoteacher_m0/accounting/call_identity.py
src/autoteacher_m0/accounting/ledger.py
src/autoteacher_m0/accounting/broker.py
src/autoteacher_m0/accounting/observation.py
src/autoteacher_m0/security/egress.py
src/autoteacher_m0/security/live_controller.py
src/autoteacher_m0/runtime/dsh_adapter.py
tests/integration/g2_closure/test_g2_closure.py
tests/integration/budget_bridge/
tests/integration/sandbox/
config/dsh/target-runtime.patch.yml
config/dsh/target-runtime-opencode-go.patch.yml
docs/ADR-002-unified-call-identity.md
docs/REVIEW_G2.md
```

如实际目录不同，先记录映射；**不得**因文件名不同就自行重建或替换模块。历史审计对应的路径与当前工作树有可能不一致，必须以冻结 commit 为事实来源。若当前 HEAD 与 `32bea5b` 的代码字节不同，先 `git diff` 定位全部变化并向 Lead 报告；不要直接在未知 HEAD 继续。

### 1.3 本次附件交叉核对发现的具体代码位置

以下为已上传 G2 源码的静态事实；仓库中的真实行号以当前版本为准：

| 发现 ID | 上传代码的入口 | 状态 | 影响 |
|---|---|---|---|
| L1-a | `egress.py` `authorize()`：只做 `_evaluate/_record` | **已确认** | 未授予真实 Claim 也能产生 `allowed=True` |
| L1-b | `egress.py` `claim_dispatch()`：`claimer is None` 回退返回原 Decision | **已确认** | 将 Claimer 忘记注入会静默放行 |
| L1-c | `egress.py` `require()` 调 `authorize()` | **已确认** | 名称易被当成正式准入入口 |
| L1-d | `MockEgressTransport.dispatch()` 在无 Claimer 时调用 `authorize()` | **已确认** | Mock 回退可被未来 Bridge 错用 |
| L1-e | `policy_from_json()` 以 `bool()`/`int()` 转型 | **已确认** | `"false"` 可转成 `True`，bool/int 容易混淆 |
| BIND-1 | Broker `claim` 无 actual route/model 字段，Ledger 只验证 Reservation Route ∈ 允许集合 | **源码确认，跨模块风险** | 对多允许 Route，不能证明 Reservation=A 与待发送=B 一致 |
| BIND-2 | `request_digest` 在 `claim` 时仅检查格式/存储，尚未与 Bridge 实际待发送字节做端到端核对 | **G3 缺口** | 不可信客户端可声称任意形式合法 Digest |
| TEST-1 | `INT-11` 测试用 EgressBoundary 未配置 Claimer | **已确认** | 证明的是 Policy 拒绝，并非真实 Broker 跨路由拒绝 |
| TEST-2 | `INT-06` 中创建的 Broker Claimer / replay Broker 未完全收尾 | **已确认** | 测试可能残留进程，不利复验 |
| OBS-1 | `src/autoteacher_m0/security/egress.py` 的 `_streams` 以 `logical_stream_id` 汇总但仅保存首个 `reservation_id` | **静态风险** | 同一 stream 中多次独立 Reservation 的快照可能误导 |

**不要把 BIND-2 称为已验证的实际付费安全事故；它是 G3 必须消除的设计/集成缺口。**

---

## 2. 不变量：任何改动必须守住

| ID | 不变量 | 反例不能被 PASS 代替 |
|---|---|---|
| INV-01 | 没有外部人类批准/授权身份时，没有真实可计费外呼 | Markdown/flag/env 不构成授权 |
| INV-02 | 没有成功 Reservation，不进入 Provider 发送路径 | 仅合法 ID 文本不算 Reservation |
| INV-03 | 没有成功**持久 Claim**，不进入任何正式 Dispatch | `reserve.dispatch_allowed` 不算 Claim |
| INV-04 | 同一个 `(scope, call_id, reservation_id)` 本地至多获得一次发送许可 | 包括多 Broker、崩溃重启、丢失 ACK |
| INV-05 | Route/Model/Endpoint/消息/输出上界/工具/响应选项在待发送请求与已批准摘要不符时拒绝 | 不接受请求发送后校验 |
| INV-06 | 未知/缺失/冲突 Usage 或实际网络结果不得填零、退款、自动重试 | PENDING/保守结算必须留证据 |
| INV-07 | DSH/候选没有真实 Key/泛化网络/独立账本写入权限 | Provider Bridge 不能成为通用代理 |
| INV-08 | Guard 不存在或加载失败时，外部可信边界仍能拒绝未授权请求 | 不能依赖 Guard 内部 fallback |
| INV-09 | A/B 层合成与本地 HTTP 证据均不能被标为 C 层真实 DeepSeek Live | 真实 Token/账单不可凭空推断 |
| INV-10 | 保持原有 G1/G2 审计、历史 SHA、协议兼容和 Live 硬阻断 | 不修历史报告来制造结论 |
| INV-11 | 只能受信任的 Egress/Controller 提交可权威结算的 Observation | 同进程测试 capability 不等于跨进程授权 |
| INV-12 | Agent 不得为自己签发 Live 授权；已经批准的源码/锁/Profile 变化使旧授权失效 | 任何自动解锁必须阻断 |

---

# Part A — 现在执行：G2-L1-FIX（本轮唯一自动执行范围）

## 3. A0：冻结与 RED 测试（先证明旧问题）

### 3.1 操作

1. 检查 `git status --porcelain=v1 -uall`、`git rev-parse HEAD`、`git diff 32bea5b -- ...`。任何非预期改动不覆盖，先记录并报 Lead。
2. 记录源文件完整 SHA-256、依赖锁、测试镜像/容器、实际运行 UID、网络禁用、环境变量清单（**仅变量名，不输出值**）。
3. 新建 `docs/M0_G2L1_FINDINGS.md`，逐项记录 §1.3 发现的代码位置/可复现性/是否本 PR 修复。
4. **先写能够在旧代码上失败的负例测试**，至少覆盖 `L1-a/b/c/d`、Strict Policy、Reservation A/B Route/Model 不匹配、FakeProvider 不能绕过发送许可。
5. 只在已批准的无凭据、禁网、只读、non-root 容器环境运行回归；**不得为获取 RED 用例放宽 LiveGate**。

### 3.2 RED 最低证据

- 未注入 Claimer，但输入通过描述符校验时，旧 `claim_dispatch`/`require_claim` 的旧行为确实产生 `allowed=True`；新测试的预期为 deny。
- `policy_from_json({"allow_files":"false"})` 在旧实现中被当作 `True`，新测试应要求 TypeError/ValueError。
- `max_tokens=True`、`attempt_ordinal=True`、`stream=0` 等 bool/整数混淆必须被新严格接口拒绝。
- 两个 Route 均在允许集合，但 Reservation 绑定 A、实际请求 B：仅做集合验证不能证明一致性；把这个缺口通过明确的 `xfail` / fail-first 或设计测试固定下来，**不要为了 RED 修改生产批准设置**。

**PASS-A0：** 旧问题经测试确实触发；失败及环境/commit 已记录。`collection error` 只能用于旧实现没有新模块的明确场景，不能一律当作有效 fail-first。

## 4. A1：拆分描述符检查与真实发送准入（P0）

### 4.1 期望接口（名称可以按仓库惯例调整，但必须满足语义）

```python
# 无权限：只计算纯描述符规则，不增加发送许可
policy_result = boundary.evaluate_descriptor(prepared_request)

# 唯一正式准入入口：没有可信 claimer 就拒绝
permission = boundary.claim_dispatch(prepared_request)
assert permission.dispatch_permitted is True  # 仅持久 claim 成功才为 True

# 正式发送必须经受信任的组件执行
result = trusted_transport.dispatch(prepared_request, permission)
```

**接口硬要求：**

- `EgressBoundary` 默认构造不带 Claimer 时，正式 `claim_dispatch/require_claim/dispatch` 返回 `BROKER_CLAIMER_UNAVAILABLE`（或稳定等价错误），`allowed=False`，不会调用任何 Provider。
- 原 `authorize()/require()` **不能再返回可被正式发送路径识别为发送许可的对象**。推荐显式降级为 `evaluate_descriptor()`，返回独立 `PolicyEvaluation`；如保留旧符号，需明确标记为“non-dispatch diagnostic”，并在任何正式 Transport 的类型/调用检查中拒绝其结果。不要仅靠注释约束。
- 删除 Mock Transport 的无 Claimer 自动回退；如历史测试依赖纯规则模拟，提供**显式、仅 tests/scripts 可用**的 `PolicyOnlyFakeTransport`，名称包含 `policy_only`，不能被正式 Bridge import。
- Claim 失败、Broker 异常、超时、EOF、非法响应、部分响应、异常退出、Claim 重放、`claimed=False` 时均 fail-closed；错误码脱敏且稳定。
- **不得**以客户端传来的 `ClaimResult(claimed=True)` 直接触发正式发送。受信传输层从私有受信通道接收许可；这是 G3 的进程边界要求，A1 必须为其留出接口。
- `reserve.dispatch_allowed=True` 只表示预留阶段可进入下一步；任何代码不得用它直接启动 Provider。

### 4.2 建议先改哪里

- `src/autoteacher_m0/security/egress.py`
- `src/autoteacher_m0/security/__init__.py`（移除不安全的“正式发送”导出，或将诊断导出更名）
- `MockEgressTransport` 的旧测试与 `scripts/verify_egress_policy.py` 的直接调用；测试可保留旧 Policy 断言，但不能默认有发送权限。
- 增加静态调用点清单：`rg '\.authorize\(|\.require\(|claim_dispatch\(|MockEgressTransport' src tests scripts plugins`，由 Agent 列出**真实**调用位置及迁移结果。

### 4.3 验收

| ID | 用例 | 期望 |
|---|---|---|
| FIX-01 | 无 Claimer、描述符完全合法 | `dispatch=0`、`allowed=False` |
| FIX-02 | 仅 Reserve 成功，无 Claim | `dispatch=0` |
| FIX-03 | fake Reservation ID | `dispatch=0` |
| FIX-04 | Claimer 抛异常/卡住/EOF/回复损坏 | `dispatch=0`，不会走 legacy fallback |
| FIX-05 | Claim 重放、`ALREADY_CLAIMED` | 第二次 `dispatch=0` |
| FIX-06 | MockTransport 未配置 Claimer | 不得“为了模拟而发送”；仅显式 policy-only 测试可评估规则 |
| FIX-07 | 旧 `authorize/require` API | 不可生成能驱动正式发送的许可 |
| FIX-08 | 有真实 stdio Broker/SQLite Claim | FakeProvider **恰一次**通过可信 Dispatch 被调用 |

> `FIX-08` 的“恰一次”只指本地受控 FakeProvider 的调用计数，不是远端 Provider exactly-once。

## 5. A2：明确 Route/Model/Digest 绑定责任（P0，禁止猜测）

### 5.1 当前真实缺口

- `ledger.claim_dispatch(..., allowed_routes=set(self.routes))` 能证明 Reservation Route 在允许列表内，但**不能证明**本次 `EgressRequest.route_id/model` 与 Reservation Route 完全相同。
- `claim` v1 消息目前只有 `call_id`、`reservation_id`、`request_digest`；`request_digest` 的 64-hex 格式正确，并不等于已与待发送的模型请求字节核对。
- **先写一份最小 `docs/M0_REQUEST_BINDING_CONTRACT.md`，在改变 Broker 协议前由 Lead 审阅。** 不能通过“多加一个 route 字段”就声称完成所有内容绑定。

### 5.2 必须定义的可信 `PreparedProviderRequest`

由可信 Controller/Bridge 从最终有效模型请求构建不可变对象，至少绑定：`scope_id`、`run_id`、`logical_step`、`attempt_index`、`route_id`、`provider`、`model`、`host/port/method/path`、`stream`、`max_output_tokens`、system/messages/tool schemas/响应格式、retry policy、Files/images/store 标志、其他允许的计费选项和 Canonical Schema Version。**由受信端对规范化后的完整请求计算 SHA-256**；不能只信任候选送来的 Digest。

- 日志仅记录 SHA/类型/长度/字段白名单，不直接保存敏感消息或凭据。
- 在实际发送前，可信端再次比对真实发包参数与 `PreparedProviderRequest` 的 Digest、Route/Model 和单次许可身份。变更任何关键字段必须重新 Reserve + Claim（不得复用原许可）。
- 现有 `CallIdentity(run_id, logical_step, attempt_index, request_digest)` 与 `call-<48hex>` 保持 ADR-002；`reservation_id` 不参与 `call_id` 计算。
- 对多 Route 场景，Claim 的受信判断必须比较**实际请求 Route/Model == Reservation 保存的 Route/Model**。`in allowed_routes` 只是必要条件，不是充分条件。
- 若需要为 Broker v1 增加字段，先选兼容方案：旧 `snapshot/reserve/settle/fail` 语义不变；新可信 Bridge 使用显式绑定能力/协议协商；老客户端保持离线功能，但**不能因为兼容而获得无需 Claim 的 Live 发送权**。
- 允许在 A 阶段先实现可验证的受信 `PreparedRequest` 对照与假的 Broker 路由负例；若必须同时修改 broker/ledger schema 才能正确实现，需提供迁移测试，且必须保持旧 v1 兼容。

### 5.3 必须证明的反例

| ID | 预留 | 待发送 | 期望 |
|---|---|---|---|
| BIND-01 | Route A / Model A | Route B / Model B（两者都在 allowlist） | 拒绝；Provider=0 |
| BIND-02 | Message Hash X | 修改消息变成 Y | 拒绝；Provider=0 |
| BIND-03 | maxTokens=256 | 发送 512 | 拒绝；Provider=0 |
| BIND-04 | 已批准 POST/path | GET/路径绕过/重定向/不同 Host | 拒绝；Provider=0 |
| BIND-05 | 工具仅 `skill_lookup` | 新增未批准工具 schema | 拒绝；Provider=0 |
| BIND-06 | 同一 call/reservation | 重复 claim/重放 | 至多一次本地许可 |
| BIND-07 | 已批准 route/model/digest | 未更改 | 成功一次并正确关联 ledger |
| BIND-08 | 旧 `reserve.dispatch_allowed=True` | 跳过 Claim | Provider=0 |

**A2 的停止条件**：无法从受信任边界拿到最终待发送请求参数，或核对必须侵入修改 DSH 核心；记录最小复现，留给 G3 评估，不许伪造 PASS。

## 6. A3：严格 Policy Schema、运行期归因与测试清理（P1）

### 6.1 Strict Policy Loader

- `policy_from_json()` 仅接受已定义的完整/可选字段，各字段严格类型，禁止 `str()/int()/bool()` 隐式转型产生不同权限。
- `allow_files/allow_images/allow_store/require_reservation` 与 `stream` 必须为**真实 bool 类型**（`type(v) is bool`）；`max_tokens/max_attempts/port/attempt_ordinal` 必须为 `type(v) is int` 且范围合法；`True` 不得充当数字 1。
- 校验 `methods`、`approved_routes`、host_ports 的元素类型、长度、是否为空和重复项；不接受非法嵌套结构；未知字段拒绝。
- 单一权威 Policy：不能出现 Agent 可以把 `require_reservation=False` 传给正式可信 Controller 的配置路径；正式实例必须从维护者受信只读 Policy 加载。
- 路径必须按实际发包组件的 URL 规范处理；不允许 `prefix + ../` 或重定向绕过（真正网络环境的 DNS/TLS/SNI/重定向再在 G3-4 证明）。

### 6.2 快照/归因

- 当前 `_streams[logical_stream_id]` 仅记录首笔 Reservation；若一条 stream 有多个被允许的 call，应改成每 Attempt 独立记录，或定义为一个 Stream 只允许一笔 Reservation。**不能让 Snapshot 的 `reservation_id` 与已有 Attempt 事实矛盾。**
- 将诊断性 `policy_allowed` 与真实 `claim_granted`、`provider_dispatched` 分开，防止可视化审计误把 Policy 通过当作实际发送。
- 非发送 Deny 不应假造“已发生 billable attempt”；对未知结果继续保守持有。

### 6.3 G2 原测试修补

- `INT-11` 当前仅为纯 Policy 否决；保留为 Policy 层测试，另增真实 Claimer/Broker 对照的 `BIND-01`。
- `INT-01` 原逻辑在 Claim 后由测试直接调用 `FakeProvider.payload()`；为验证真实 gate，应增加一个统一的受信 Fake Dispatch 入口，该入口只在 Claim 确认后调用 Provider，并记录调用次数。
- `INT-06` 的 Broker/replay 子进程必须用 context manager 或 `try/finally` 清理；修复后检查没有 PID/容器残留。
- 不改变原测试的历史证据字节；不声称修复后测试可以替代真实 HTTP/DSH 验证。

### 6.4 A3 定向验收

`STRICT-01`：`"false"`、`"0"`、`0/1` 在布尔字段均拒绝；`STRICT-02`：`True`、`1.2`、`"256"` 在整数上界字段拒绝；`STRICT-03`：重复/空白/未知的 route/method/host 规则拒绝；`STRICT-04`：异常 URL/path 不得绕过；`TRACE-01`：一个 stream 两个 calls 的 `call_id ↔ reservation_id` 关联准确；`PROC-01`：每个子进程退出后无残留。

---

## 7. G2-L1-FIX 完成前必须运行的测试

### 7.1 测试层次

**T1. RED 定向负测**：旧实现上的必然失败（A0）；保存命令、stdout/stderr、exit、源 Hash。

**T2. 修复后 Targeted**：`FIX-01..08`、`BIND-01..08`、`STRICT-01..04`、`TRACE-01`、`PROC-01`，以及 G2 的 `INT-01/02/03/04/05/06/07/08/09/10/11/12/13/14/15/16/17/18`。注意矩阵条目与 pytest 用例可一对多，但 Manifest 必须提供映射。

**T3. 原 Broker/Guard 回归**：确认 `snapshot/reserve/settle/fail` 旧 v1 客户端行为与 `claim` 的兼容边界；确认重复消息/settlement/不确定 usage 不退化。

**T4. 既有安全和 accounting 全量回归**：按仓库真实路径/现有固定镜像运行一次真实集成子集 + 一次 Ruff repo-wide；若旧测试因 API 重命名需迁移，列出每个修改的原断言与语义，不得删除失败用例以获得绿色。

**T5. 独立新进程/新 DB 恢复**：至少验证两个 Broker 进程竞争一个 claim、kill/restart、ACK 丢失复用等 G2 既有证明未受损。

### 7.2 通过条件（全部必要）

- 上述负例均有**真实 Provider Dispatch Count = 0**（来自可信 Dispatch 包装器/测试服务端，而不是只靠 `decision.allowed=False` 推断）。
- 成功用例真实 FakeProvider Dispatch Count = 1，单个 `call_id` 只获得一个新 Claim。
- 任意 Broker 断开、不可信路由、无 Claimer、错误 Schema 不会触发回退或第二次发送。
- Reservation/Call/Claim/Observation 在新进程下仍关联同一身份；缺失 Usage 保守处理。
- 旧 Broker v1 及 G2 测试回归 PASS；测试进程/容器无残留，代码 Ruff PASS。
- **LiveGate/Adapter/run_live 保持原硬拒绝行为**；无真实 Key/模型/外部 HTTP。
- 实现与测试 commit 分离不是强制，但每个实际执行都绑定唯一准确的源 Tree Hash；不编造 PASS 数量。
- **A 阶段最低必过集**：`FIX-01..08`、`BIND-01/06/07/08`、`STRICT-01..04`、`TRACE-01`、`PROC-01`、既有 G2 INT 回归与 Ruff 必须 PASS；其余 `BIND-02..05` 允许明确标 `G3_DEPENDENCY`，但不得写 A PASS。

**若部分 `BIND-*` 依赖 G3 的真实 Provider 请求字节**：可明确标 `G3_DEPENDENCY/BLOCKED`，A 阶段只允许 Claim 接口修复与可信请求绑定设计完成，不得把整组写 PASS。Lead 必须说明剩余项属于 G3 的执行前提，否则不批准 G3 进入能触发发送的步骤。

## 8. A 阶段 Review Packet（Agent 完成后立即停止）

必须生成：

```text
artifacts/review-packet-G2L1-<implementation-sha>/
  README.md                       # 精确范围、基线/当前状态、要 reviewer 决定什么
  CHANGELOG.md                    # 一项发现 -> 修改 -> 测试 -> 风险
  diff.patch                      # git diff <base>..<implementation_sha>
  sources/                        # 修改后的源文件，必要时包含相关未改依赖
  tests/                          # 所有新增或修改测试文件
  docs/
    M0_G2L1_FINDINGS.md
    M0_REQUEST_BINDING_CONTRACT.md
    M0_G2L1_FIX_REPORT.md
  evidence/
    manifest.json                 # base/source/docs/container/lock Hash、scope、时间
    commands.jsonl                # argv、cwd、隔离参数、UTC、exit、log 名称
    hashes.sha256                 # 覆盖包内的实际文件（不包含自引用）
    logs/                         # RED/GREEN/全量/Ruff/并发/崩溃/进程 absence
    matrix.json                   # 每个 FIX/BIND/STRICT/INT 对应实际测试与证据
  blockers.md                     # PASS/FAIL/BLOCKED/UNVERIFIED，含 Owner 和下一步
```

**强制要求：**

- `base_commit` 应绑定 G2 最终实现 `32bea5b`（或清楚解释后来有何变化）；`implementation_commit` 为实际修复代码；文档提交另外记录 `docs_commit`。不要只写一个模糊的 HEAD。
- Review Packet 根目录固定为 `artifacts/review-packet-G2L1-<implementation-sha>/`（`artifacts/` 已被 gitignore），不要将该目录提交到 Git。
- `diff.patch` 必须完整可用；若运行产生的 artifact 大，提供脱敏后的相关原始日志与 hash，而不是只有 `pytest passed` 这句话。
- 记录每个测试实际运行了哪些用例、deselected/skipped 的具体理由；不得把不同 suite 的数量简单相加。
- 运行环境应继续采用真实冻结的无凭据隔离 OCI；不在宿主执行不可信候选代码。
- 所有源信息都在 Repo 或 Review Packet；不要提交 `.env`、任何真实 API Key、私有评估资料、宿主 Home、原始可能含 Secret 的日志。

### A 阶段独立审阅操作

Reviewer（不得与实现者同一身份）执行：

1. **重建身份**：从 `base_commit` 和 `implementation_commit` 取 Git blob，对 `diff.patch`、Manifest、关键源码哈希做交叉比对；确认无越权触及 `src/autoteacher_m0/security/gates.py`、`src/autoteacher_m0/runtime/dsh_adapter.py`、`scripts/run_live.sh`。
2. **静态追踪**：从所有可能的 Provider Dispatch 入口逆向找 Claim；搜索 `authorize()/require()/claim_dispatch()/MockEgressTransport.dispatch()` 全部调用点；找有无 fallback；比较 Route/Model/Digest 的受信来源。
3. **独立 RED/GREEN**：新 stage、原始固定无 Key 容器，复跑至少 `FIX-01/02/04/05/06/07/08`、`BIND-01/02/03/08`、`STRICT-01/02`、`INT-05/06/11/17`。
4. **负例服务端计数**：不只检查返回值，实际确认 FakeProvider 调用数、Broker claims、数据库事务、待结算成本；重启之后再核对。
5. **兼容**：旧 v1 reserve/snapshot/settle/fail、重复 ID 与 journal 容量、保守 unknown usage；对未来可能发生的 DSH 真实请求不可用的项标 G3 依赖。
6. **发表裁定**：`PASS_FOR_DECLARED_G2L1_SCOPE`、`FAIL_FOR_DECLARED_SCOPE` 或 `BLOCKED`；明确哪些 BIND 项尚待 G3；独立结果不得由实施者替写。

**只有独立 Reviewer 确认 P0 入口已关闭，维护者才可明确授权后续 G3。**

---

# Part B — 待维护者批准后执行：G3 Provider Bridge（无 Key）

## 9. B0：G3 独立启动前置

需同时满足：

- A 阶段 P0 问题已关闭；Review Packet/独立审阅完成；无影响发送许可的 FAIL。
- **维护者**另行发布**明确的 G3 无 Key 执行批准**，批准范围限固定 DSH SDK/Runtime 与本地 FakeProvider/受控 IPC；Lead 只能准备、核对与转呈材料，不能自行批准 G3。仅有本任务书不能等于执行批准。
- 真实 `gates.py`、Adapter、Live Script 仍严格拒绝 Live；无真实 Key/真实供应商网络。
- 已准备独立受控实验环境：DSH 候选进程无任意网络、无真实 Key；IPC 端由可信 Controller 限制；G3 后期本地 HTTP 验证需单独受限网络环境。

### G3 最重要的问题

> 在不改 DSH 上游内核、不向 DSH 暴露真实凭据、不开放任意公网的前提下，真实 DSH + Python SDK + `skill_lookup` + Session 是否可以通过**公开 Provider 插件接口**和受控 IPC 跑完真实引擎事件、一次性 Claim、FakeProvider 响应与持久结算？

若不行，报告具体公开 API/ABI 障碍，而不是无期限补丁。

## 10. B1：DSH Provider 扩展能力 Spike（先小、后大）

### 10.1 只读确认真实固定版本

- 读取锁定 `deepseek_harness` SDK 0.2.2rc2、真实 Runtime CLI、Cordis 插件版本的**实际离线安装包**（按仓库固定 wheel/rootfs/deps 字节）；记录 ABI、Provider 生命周期、流式事件与 `tool-call/usage/finish/abort` 接口。
- 优先复用现有真实 `offline-test-only` / fixture 插件公共模式；**不得通过修改 DSH 内核、冒充 Fixture 直接返回答案** 来“实现 Bridge”。
- 生成 `docs/G3_PROVIDER_ABI_SPIKE.md`：哪些事件可经公共接口获得、缺哪些字段、取消语义、重启机制、可能需要的兼容层和限制。

### 10.2 最小运行里程碑

1. 实际 DSH SDK 初始化 + Bridge Provider 插件注册，严格固定 Synthetic 配置。
2. Bridge Provider 通过**真实进程间 IPC**把请求交给隔离的 FakeProvider 进程，得到至少一次结构化响应；保留原始脱敏事件顺序。
3. Streaming / JSON / Tool Call 与 SDK/Session Resume 分别验证，不要一开始把所有功能塞进大型异步实现。
4. 不引入真实 Provider Client、真实 Key、公共任意 URL 代理。

### 必须交付的 IPC schema 草案

```text
v / message_type / correlation_id / run_id / call_id /
request_digest / reservation_id / route_id / model /
normalized_request / payload_size / deadline / cancel_reason
```

- 固定消息类型：`PREPARE`, `RESERVE`, `CLAIM`, `PROVIDER_REQUEST`, `STREAM_CHUNK`, `USAGE`, `FINISH`, `CANCEL`, `ERROR`（具体可缩减，但不能存在通用 `EXEC` / `OPEN_URL` / `READ_FILE`）。
- 固定字段、严格长度和 Schema、超时、半包、重复 ID、额外字段拒绝；不允许未经审核的候选向可信 Controller 注入授权或真实 Key。
- 流式输出具备背压与取消；发送日志只保留摘要、事件类型、长度和受信请求 ID。
- 若 IPC 需要 Unix Socket，必须解释为何不使用 stdio/pipe、Socket 权限如何防越权、候选依旧不能获得任意公网权限。

## 11. B2：G2 预算链路接入真实 DSH 工具轮

针对每一个 DSH `llm/stream` 的实际可计费 Attempt：

1. 可信 Bridge 从实际最终模型请求构造 `PreparedProviderRequest`。
2. 可信 Controller 在外呼前重新计算 digest/CallIdentity，并与 Route Policy/工具/余额核对。
3. Broker `reserve(call_id=...)`，检查预算与 `reservation_id`；不可把 reserve `dispatch_allowed` 当发送许可。
4. 独立调用 Broker `claim`，受信 Egress 校验 `claim` 与最终请求参数一致；无 Claim 不得发给 FakeProvider。
5. 在允许的受限通道中向 FakeProvider 发送一次；工具结果回灌后若需要第二次模型生成，**新的 logical step + 新的 Reservation/Call/Claim**。
6. 可信端产生 Observation；权威来源只来自可信 Controller/Egress；错误/缺失/部分 Usage 保留保守状态。
7. SDK Session 保存/恢复时，Ledger Scope/CallIdentity 和 Tool events 不混用、不重放发送许可。

必须实测 FakeProvider 调用次数、Broker DB 的 Claim/Reservation/Observation 和 SDK Tool/Session 事件。**禁止仅观察 `decision.allowed=True` 便报“Bridge 通了”。**

## 12. B3：失败关闭与受限网络证明

### 12.1 不需要真实 Socket 的 IPC/进程故障

- Guard 插件缺失或加载失败，外部 Broker/Egress 没有可信批准仍拒绝。
- Reserve 成功但缺 Claim，FakeProvider 调用数为 0。
- 一旦 Claim 后崩溃/超时/EOF，Claim 保留且重试不得再次获得许可；不能声称远端必然未计费。
- 修改 route/model/messages/tools/max_tokens/endpoint 后摘要不一致，发送前拒绝。
- IPC 错误 JSON、截断消息、重复 ID、乱序 usage、错误 finish、异常退出、背压卡住、timeout/cancellation 全部有受控停止或保守行为。
- Controller 崩溃/Watchdog 超时后 PID/容器 absence 有可信外部观察，而非仅日志宣称已清理。

### 12.2 真实本地 HTTP 模拟验证（另建受限网络环境）

当前固定 OCI `socket()` 被拒，这只能证明当前容器不能直接联网，**不能**用它证明 Egress 代理能发送请求。G3 必须单独部署审过的、完全无真实 Key 的本地 HTTP 测试服务：

- 可信 Egress 可以到该本地 Fake HTTP Server（且只能访问明确批准的本地目标）；DSH/候选不能直接访问。
- 真实测量 HTTP 请求次数、目标路径、方法、重定向、DNS/Host/SNI/请求 body，拒绝私自改路由和跳转。
- 代理宕机/认证失败/防火墙配置错误，不得回退直连。
- 禁止仅为通过测试而在不可信 DSH 容器上打开 `--network=host`、挂高权限 Docker/Podman Socket 或挂真实凭据。
- 如当地环境无法运行受控本地 HTTP，BR-10 必须记 `BLOCKED`；**不能**由模拟 descriptor 代替 PASS。

## 13. G3 必须逐项交付的 BR-01..12 验收矩阵

沿用 v0.6 编号，不自行删除或降低：

| Case | 执行证据 | PASS 条件 |
|---|---|---|
| BR-01 | 真实固定 DSH CLI / Python SDK / Bridge Provider 日志 | 初始化/退出及至少 3 次独立重启；无核心 Fork |
| BR-02 | 真实 DSH tool-call/tool-result 事件 | `skill_lookup` 在 SDK 真实链路中被注册、调用、回灌 |
| BR-03 | 严格结构化 JSON | 项目 Schema 验证通过，错误 JSON 被拒绝 |
| BR-04 | 3 对跨进程 Session Resume | 同一 Session 恢复；不同 home 不发生逻辑混用 |
| BR-05 | 真实 Bridge stream / usage/finish trace | 顺序、来源与缺失字段可追踪；未知不填零 |
| BR-06 | 无 Guard Plugin 变体 | 没有可信批准时受控出口对所有未批准请求拒绝 |
| BR-07 | 实际 merged Profile + Tool Registry | 执行时工具与 route/model 和审核配置完全一致；不只 dump-config |
| BR-08 | Controller/Broker/IPC 故障注入 | 无后续发送，DB 仍保留不确定/已 Claim 状态 |
| BR-09 | 超时/取消/崩溃/Watchdog | 真实进程终止与容器 absence 证明；不自动重复发送 |
| BR-10 | 受限本地 Fake HTTP Server + OS 隔离证据 | Egress 可访问获批目标，候选 direct-connect 失败 |
| BR-11 | 同一 Claim 的第二次发送尝试 | 拒绝，FakeProvider 只收到一次许可内尝试 |
| BR-12 | 总成本/调用矩阵 | 真实模型请求=0、真实供应商费用=0，合成账本与 FakeProvider 计数一致 |

G3 还必须包含 §5 的 BIND-01..08 中那些之前因缺真实请求字节而被标 `G3_DEPENDENCY` 的用例。

### G3 技术路线判定与停机条件

**继续 DSH**：BR-01..12 全部强制项在公开扩展上可复现，未引入侵入式核心 Fork，工具、Session、Usage、取消与预算链路均完整。

**技术阻塞/考虑替代 Runtime**：公开 Provider/SDK 接口无法以可维护成本表达关键事件或外部 IPC；必须把真实 Key/任意公网开放给候选；需要大量不可维护的私有 Fork；或失败关闭问题无法用可信边界解决。应整理最小复现与维护成本，比较官方 TS Runner、公开 JSON-RPC、PydanticAI 等与现有 `AgentRuntime` ABI 适配的代价，而不是直接为了通过验收改写结果。

**没有真实 Key**只是测试阶段约束，不能单凭此给 DSH 技术 NO-GO。

---

## 14. G3 Review Packet 与独立审阅流程

完成 G3 后生成：

```text
review-packet-G3-<implementation-sha>/
  README.md
  ADR-003-provider-bridge.md
  M0_G3_PROVIDER_ABI_SPIKE.md
  M0_G3_PROVIDER_BRIDGE_REPORT.md
  diff.patch
  sources/                    # Bridge/Controller/egress/accounting/Runtime config 相关字节
  tests/                      # BR-01..12 对应 pytest/TS/脚本
  schema/                     # IPC schema、Route Policy、Merged Profile（无 Key）
  evidence/
    manifest.json
    commands.jsonl
    hashes.sha256
    matrix.json               # BR case ID -> fixture -> actual logs -> PASS/FAIL/BLOCKED
    logs/                     # DSH RPC、tool、Session、IPC、DB、网络/OS 否定探针
    sanitized-snapshots/      # DB claims/reservations/accounting；不含敏感消息
  blockers.md
```

**Review 时四个角色必须分离**：Implementer 出代码和 evidence；Lead 核对范围/ABI/权衡；Independent Reviewer 用冻结字节在相同受限环境复跑至少 BR-02/06/08/10/11（含 OS 网络探针）；维护者只根据实际证据决定是否批准下一步 G4。**Agent 不准自行宣告 G4/Live 已获授权**。

Reviewer 最终必须回答：

1. 真实 SDK/DSH 是否真的经过 Bridge 发出可计费意图，而非脚本自己构造假事件？
2. 是否存在任何 `authorize()/require()` 等纯 Policy 路径被正式发送逻辑导入？
3. 有没有 `reserve.dispatch_allowed` 被当成 `claim`？
4. 受信者是否重新计算最后待发送请求 Digest，并核对 Route/Model/Token/Tool/Endpoint？
5. 重放、并发、失联、超时后是否可能第二次取得许可或自动重试？
6. 可信 Egress 的 Observation 是否能被候选伪造并解锁预算？
7. 是否通过真实 DSH Session/Tool/Usage 的事件证据，不只是配置 Dump？
8. 无 Guard、无 Claimer、无 Broker、无 Proxy 时 FakeProvider 接收次数分别多少？
9. OS 是否能阻止 DSH 直连，且单独允许可信 Egress 访问已批准本地 Fake HTTP？
10. 是否存在真实 Key、真实供应商 HTTP 或费用？如有立即 FAIL 并披露事件。
11. Freeze commit、文件/依赖哈希和实际运行日志是否对得上，是否有 skipped/xfail？
12. 哪些证据仅覆盖 Mock/B 层，哪些仍属于 G4/G5 `BLOCKED`？

审阅结论必须是：`PASS_FOR_DECLARED_G3_SCOPE` / `FAIL_FOR_DECLARED_SCOPE` / `BLOCKED`，含阻断项和可复验路径。G3 成功**只允许申请 G4 人审**，不是 Live 的 GO。

---

## 15. 质量与交付约束（所有阶段）

### 15.1 修改最小化

- A 阶段优先只改 `security/egress.py`、必要的 `security/__init__.py`、调用者和测试；如需 Broker/Ledger Schema 变动，必须独立证明旧 v1 兼容并保留迁移脚本/回归。
- 不修改 `src/autoteacher_m0/security/gates.py`、`src/autoteacher_m0/runtime/dsh_adapter.py`、`scripts/run_live.sh` 的硬阻断行为；不改历史冻结 Manifest/审计正文。只需追加真实 Errata。
- G3 可以新增 Bridge 插件/IPC schema/定向测试/隔离脚本；不得把新的“正式发送”能力挂到旧 MockTransport 默认入口上。
- 任何重要源码修改都要说明安全理由与非目标；不要整仓重构。

### 15.2 日志安全与可复核性

- `argv` 只写参数名或无敏感值的测试选项；如果现实命令含 secret，必须脱敏并在受信环境保留独立哈希核对，不进入 Review Packet。
- Review Packet 必须给出原始退出码、UTC、环境/镜像/锁哈希、完整测试选择表达式、真实计数。不能用模型写的叙述代替执行日志。
- 对被跳过或阻塞的测试逐项说明，不允许改 `skip`、删除测试或收窄选择集来制造全绿。
- 每一段测试说明是 RED、GREEN、Independent Re-run 还是历史 Evidence；不同类型不可混用。

### 15.3 立即 STOP 的条件

以下任一情况发生，本任务自动停止并报告，不允许“继续跑完剩余用例”：

1. 任何真实 Key 被读取、挂载、打印或传给候选。
2. Agent 企图自行解锁 LiveGate、绕过人类授权、放宽网络/容器权限。
3. 未成功 Claim 的请求到达任何正式 Provider/FakeHTTP 可计费路径。
4. 同一 Claim 在本地获得第二次发送许可；已批准请求被未授权修改。
5. Broker/Controller/Proxy 故障时发生直连回退或自动重试。
6. Watchdog 无法证明候选或容器已退出；存在未受控运行进程。
7. G3 需要在未批准情况下下载/调用真实供应商网络、安装未经审查的核心 Fork。
8. 关键源/锁/Profile/插件字节与本轮批准冻结身份不一致，且无人复核。

发现后保留原始脱敏证据、冻结进度、通知维护者；**不得自行降低硬验收标准**。

---

## 16. 给 Coding Agent 的可复制首轮指令（复制本节即可）

> 你是 Autonomous Teacher M0 的实现 Agent。请阅读本文件全文及仓库 v0.4 正式规范、v0.6 实施手册、G1 最终 closure、G2 独立审计、ADR-002 与真实冻结 G2 源码。  
> **本轮仅执行 Part A：G2-L1-FIX，禁止自动进入 Part B/G3、G4 或任何 Live。**  
> 首先记录基线/真实 SHA，核对 `32bea5b` 与当前工作树；对 `egress.py` 的旧 `authorize()/require()`、无 Claimer `claim_dispatch()`、MockTransport fallback、宽松 Policy JSON 等写 fail-first 回归。  
> 将描述符 Policy Check 与持久 Broker Claim Dispatch Permission 严格分离。无 Claimer、只有 Reserve、伪造 Reservation、错误 Route/Model/Digest、重复 Claim 都必须产生 **0 次可信 FakeProvider Dispatch**。为未来 G3 定义受信 `PreparedProviderRequest` 的完整请求摘要、Route/Model 绑定与受信来源，并以真实 Broker/SQLite 定向测试证明可验证部分。保留 v1 兼容与历史证据，不更改任何 Live 硬阻断。  
> 运行定向 RED/GREEN、G2 与 Broker/Guard/安全回归、Ruff；修复子进程清理与快照归因。  
> 提交最小 Git Diff、新 implementation SHA、`docs/M0_REQUEST_BINDING_CONTRACT.md`、`docs/M0_G2L1_FIX_REPORT.md`、全部改动的源码/测试与 `review-packet-G2L1-<sha>/`。Evidence 必须含真实 argv/UTC/exit、SHA-256、测试选择集、正负例调用次数、失败/skip/未验证项。  
> **交付后立即停止。** 不进入 G3；等待维护者与独立 Reviewer 对该 Review Packet 给出裁定。任何无法从当前仓库证明的事实要标为 `UNVERIFIED`，不要猜测或补造通过结果。

### 实施者完成时回报的最小模板

```markdown
# G2-L1-FIX Implementation Handoff
- Base implementation commit:
- Implementation commit:
- Docs commit (if different):
- Tree/dependency/image hashes:
- Changed files and justification:
- RED tests: <case -> argv/log/exit>
- GREEN tests: <case -> argv/log/exit>
- Regression test selection and exact counts:
- Provider dispatch counts on denied cases:
- Broker reserve/claim/settlement summaries:
- Protocol compatibility:
- Unverified/BLOCKED / outstanding G3 dependencies:
- Security non-claims (no real Key/network/model):
- Review packet location / sha256:
- STOP confirmation: G3/G4/Live not started
```

---

## 17. 维护者审阅与下一阶段批准方式

**本文件不是批准签名**，也不能改变真正的 `ExecutionAuthorization`。完成 Part A 后，维护者应只依据独立 Review Packet 和 Reviewer 结论做以下选择：

- **A PASS**：确认 `G2-L1` 无 Claimer 回退、错误路由/摘要绑定与测试真正关闭；**单独授权 G3 无 Key Spike**，指定固定源码/工具/容器版本、允许的本地进程/IPC 路径和不允许的网络。
- **A FAIL**：指示实现者只修确切 blocker，提交最小增量；不重跑 G1/G2 全部历史工程。
- **A BLOCKED**：必要来源/安全环境不足，保持 BLOCKED，交由维护者提供审查环境或选择可维护的替代方案。

完成 Part B 后再审 G3 的全部 BR-01..12。如果 G3 PASS，才讨论 G4 人类部署和 E5-PreLive，仍然不允许使用真实 Key。真实 DeepSeek 模型验收属于单独 G5，需要额外审批与低额度可撤销凭据、实际外部计费约束。**无论 G2-L1 或 G3 完成，M0 总体仍按 v0.4 强制项评判，不能直接 GO。**

---

## 18. 源码与已有报告索引（便于 Agent 对照）

- v0.4 正式验收：`docs/Autonomous_Teacher_M0_v04.md`。
- v0.6 G0–G6 流程：`docs/Autonomous_Teacher_M0_Execution_Validation_Review_Playbook_v0.6.md`，特别是第 8、13–15、17 节。
- G1 最终审阅：`docs/REVIEW_G1_CLOSURE.md`（含 post-freeze errata）；原 G1 FAIL 和 Addendum 是历史链，不应被误当当前状态。
- G2 事实与遗留：`docs/REVIEW_G2.md` 的 §4–6；G2 完成仅限其声明的离线范围。
- G2 身份/Claim 契约：`docs/ADR-002-unified-call-identity.md`。
- 源码：`src/autoteacher_m0/security/egress.py`（legacy fallback、Policy loader）、`src/autoteacher_m0/accounting/{call_identity,broker,ledger,observation}.py`。
- 测试：`tests/integration/g2_closure/test_g2_closure.py`（INT-01..18）、`tests/integration/budget_bridge/`。
- 目标 DSH 配置与残余 F7：`docs/DSH_TARGET_PROFILE.md`、`docs/REVIEW_CLOSEOUT_PR2.md`。
- 真实 Egress 尚未部署的证据：`docs/BILLABLE_PATH_INVENTORY.md`、`docs/REVIEW_CLOSEOUT_PR4A.md`。
- 当前其他 G4/G5 阻塞与预算策略：`docs/M0_CLOSEOUT_DECISIONS.md`、`docs/M0_CLOSEOUT_REPORT.md`、`docs/LIVE_CONTROLLER_SECURITY_DESIGN.md`。

**结语：先完成 G2-L1 的最小且可复核修复，再用 G3 的真实引擎 + IPC + FakeProvider 实验判断 DSH 是否值得继续。不要靠 Mock 测试数量和文档长度替代这两个决策关口。**
