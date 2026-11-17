# Autonomous Teacher — M0 G3-C / G3-D Agent 迭代执行与验收任务书

> **版本**：v1.0 ｜ **制定日期**：2026-11-17 ｜ **用途**：直接交接 Lead Agent / Implementation Agents / Independent Reviewer
>
> **唯一当前起点**：远程仓库 `ygmldr/Autonomouse-Teacher` 的 `main`，审计固定 SHA `bb5bd0bf83e22130ed0d81c54f54a4673654cfe3`。**执行时先重新检查远端 HEAD 和工作区**，若 SHA 不同，先生成差异/漂移报告并由 Lead 逐项核对；**不得盲目覆盖新增工作**。
>
> **现有正式裁定**：`PASS_FOR_G3B_NO_KEY_INTEGRATION_SCOPE`；`OS_TRUST_BOUNDARY=B0-02=BLOCKED`。这不是模型可用、账单准确、Live 或 M0 GO 的证明。
>
> **批准范围**：仅 G3-C 无 Key 修复、G3-D 无 Key OS 隔离及对应独立审阅；**不批准** G4/G5、真实 DeepSeek API、真实 Key/外部付费 HTTP、生产 Live、解除 LiveGate。所有合成测试使用 Fake Provider 与禁网环境。若测试必须越过这个边界，立即 STOP 并报维护者。

---

## 0. Lead Agent 第一屏：目标、必须交付、停止点

### 0.1 任务目标

在保留 G3-B 已通过的 DSH→公开 Cordis `LlmAdapter`→受限 UDS→Controller→SQLite Broker→Bound Claim→Durable Attempt→Fake Provider→Receipt→Settlement 链路前提下：

1. **G3-C** 修复已发现的协议与实现缺口：取消、错误契约、Admission 限额、真实 Deadline、Broker 阻塞、IPC 资源上界、Usage 事件透传、崩溃恢复与 Broker 状态一致性，以及独立 Reviewer 的 P2 收口。
2. **G3-D** 把“同容器同 UID 的逻辑模块分离”变成**由 Linux 内核实际实施的权限隔离**，允许候选 DSH 连通固定 IPC，但拒绝读取/修改 Broker DB、Policy、Admission、Attempt Journal、Receipt 和任何可信执行/凭据路径。
3. 复跑**真实 DSH SDK** 下的工具两轮、Session Resume、Crash、并发、无 Key Guard 缺失、Usage、Cancel、资源压力与候选攻击测试，并由不同身份 Reviewer 复核。

### 0.2 最重要的 STOP / GO 规则

- **G3-C 实施完毕后必须停止并提交 C-Review Packet**；可以并行做 G3-D *设计与隔离环境预研*，但不能自行把 G3-C 报告标为独立 PASS。
- **G3-D 实施完成后再次 STOP**；独立 Reviewer 只可签 `PASS_FOR_G3D_NO_KEY_OS_TRUST_BOUNDARY_SCOPE`（如实成立）或 FAIL/BLOCKED，不可签 G4/Live。
- 默认 **不修改** `src/autoteacher_m0/security/gates.py`、`src/autoteacher_m0/runtime/dsh_adapter.py`、`scripts/run_live.sh`、DSH 核心。若出现看似需要解除 LiveGate 的情况，禁止执行，直接报障碍。
- G3-B 历史 implementation `9040292`、Docs `b4a2d77`、Review Packet、33 行旧矩阵、Independent Review 及 Errata 都是**冻结历史**。不得覆盖或重写，使用新目录记录本轮证据。
- Lead 只做协调、分派、审阅和验证；实际源码改动必须委派给实现子 Agent，遵循根目录 `AGENTS.md`。

### 0.3 本轮完成后能主张的结论

- 若 C 通过：**无 Key 契约 / 恢复 / 资源行为验收通过**。不能主张 OS Boundary、真实 Supplier Usage/Invoice、远端 exactly-once。
- 若 D 也通过：**无 Key 已验证 OS 隔离**。这才是进入 G4 PreLive 设计/安全准入评审的*必要但不充分条件*。
- 若 D 的候选进程仍能修改任何可信 DB/Policy 或绕过 Controller 获得有效发送能力：D **FAIL/BLOCKED**，不能因为外部网络已禁用就签 PASS。

---

## 1. 执行基线与已确认事实

### 1.1 Git 身份

- 仓库：`https://github.com/ygmldr/Autonomouse-Teacher`
- 审阅冻结点：`bb5bd0bf83e22130ed0d81c54f54a4673654cfe3`（`main`，2026-11-17 查询）。
- G3-B Implementation：`90402929c710a046e23dd3a3c3dd108b641bc981`；B4 Docs：`b4a2d774d97242974fcadd21166292dd3b988339`。
- 固定运行时：DSH `0.2.2-rc.2` / Python `3.11.15` / Node `v22.23.2`，实际执行以当前锁/哈希可复算情况为准，不能引用旧版本的 PASS 代替新运行。
- 独立 Reviewer 原裁定：`PASS_FOR_G3B_NO_KEY_INTEGRATION_SCOPE`，且 `B0-02=BLOCKED`，33 项旧矩阵报告值 28 PASS / 2 PARTIAL / 2 UNVERIFIED / 1 BLOCKED；见 `docs/REVIEW_G3B_INDEPENDENT.md` 与 `docs/M0_G3B_REVIEW_ERRATA.md`。

### 1.2 已证实的代码事实（2026-11-17 静态审阅）

| ID | 源码入口（基于冻结 SHA；行号可能随补丁变化） | 现状 / 影响 |
|---|---|---|
| SRC-01 | `bridge/controller.py:98-130,333-351` | `RESPONSE_OBSERVED` 只持久化 receipt metadata，未持久化可信 Usage；重启时可能 fallback `fail`，且 `ALREADY_SETTLED` 被误解为 held |
| SRC-02 | `bridge/ipc_server.py:293-299` / `controller.py:187-188` | `cancel(transport_id,reason)` 与 `cancel(self)` 签名不符，异常吞掉，取消是 no-op |
| SRC-03 | `bridge/controller.py:217-235` / `fake/fake_provider.py:81-113` | Fake 内部独立 `{kind:'usage'}` 被 Controller `continue` 丢弃，Broker 的 Usage 与 DSH 的 StreamChunk Usage 不是同一条证据 |
| SRC-04 | `bridge/controller.py:132-138,238-265` / `bridge/admission.py:105-118` | 输出上限与 Admission `max_output_tokens` 未严格绑定；输入预留固定式 `min(1024, max_input_tokens)` 无可信 token 计量保证；`deadline_ms` 未下沉到整个调用链 |
| SRC-05 | `bridge/broker_client.py:42-54` | `timeout_s` 属性未对阻塞 `stdout.readline()` 生效 |
| SRC-06 | `bridge/ipc_server.py:39-70,105-116,194-208` | 首帧可无限等待，服务线程无限追加，Deadline 不能中断同步阻塞调用 |
| SRC-07 | `bridge/ipc_server.py:268,302-307` | `_last_frame_bytes` 为共享状态，不应作为多连接的响应字节计数依据 |
| SRC-08 | `bridge/controller.py:238-244` | 无效请求在 `_prepare` 之前消耗 `max_calls` |
| SRC-09 | `bridge/protocol.py:26-40` | 缺少 Broker `CALL_ID_CONFLICT`、`IDEMPOTENCY_CONFLICT` 等的显式协议映射；错误可能退化为 `UNKNOWN_FIELD` |
| SRC-10 | `bridge/controller.py:359-363`, `fake/fake_provider.py:109-110` | `finish(error)` 不带必需 `failure{code,message}`，违背 `protocol.py:271-287` |
| SRC-11 | `bridge/fake_backend.py:52-80` | 用 `subprocess.run(stdout=PIPE)` 收完后统一解析，不是在线 Streaming，输出缓冲无同等逐帧限制 |
| SRC-12 | `bridge/attempts.py:133-137` | `next_logical_step(run_id)` 目前不使用 run_id（仅检查真实调用路径是否依赖；不要为未使用函数擅自重构） |

> SRC-01/02/08/09/10 与独立 Reviewer 发现存在重叠；SRC-03/04/05/06/07/11 是新增静态审阅重点。**所有动态结果必须在本轮新冻结的真实测试环境中重新取得，不能将静态审阅写成已成功复现。**

### 1.3 既有证据允许沿用的部分

- G3-A 已证明公开 DSH `LlmAdapter`、真实 SDK、Tool Loop 和 Session 恢复的基础可行性；G3-B 已通过无 Key 功能链路的独立限定验收。
- 保留真实 Broker v1 的 Reserve/Bound Claim/Settle/Fail/Journal 语义，保留 G2-L1.2 的 Cancellation 基础修复。
- 不复制 G3-B 全部历史 Packet；只从最终冻结代码重新跑**受改动影响的**回归，并在新的证据矩阵中交叉引用旧结论。

---

## 2. 设计约束与不可破坏的不变量

### 2.1 身份和信任

**T-01** `CallIdentity` 只能来自可信 Controller；候选 DSH 请求不得自带可授予权限的 `call_id` / reservation / digest / admission / claim。

**T-02** 每一个真实进入 Adapter `stream()` 的独立 Provider 请求，都有独立 Reserve、Bound Claim、持久 Attempt。**一次 Tool Turn 可以有两次 Provider 调用；不得依赖 `request/header` 的数量计费。**

**T-03** Fake 只接收 Controller 批准的实际 bytes：`sha256(approved_payload_bytes) == sent_digest == fake_receipt.raw_sha256`，且 nonce/call/route/长度/持久身份可关联；`prepared_digest` 与出站字节摘要是两种不同摘要，禁止混用。

**T-04** 任何 Claim、Permission 均不得跨进程任意伪造；旧 unbound claim 接口仅供遗留兼容测试，**不进入实际可信发送路径**。

**T-05** G3-D 候选进程不可信，不可直接触及可信 DB/Policy/Admission/Journal/Receipt/执行文件、网络出口或 Key。文件权限、容器描述、白名单文字均不是 OS 拒绝的证据。

### 2.2 费用、恢复与取消

**A-01** 没有持久的 `ATTEMPT_STARTED`，不能发送；有 Attempt 而缺可信结果，不能自动重发。

**A-02** 已进入 Provider 的异常、Cancel、Timeout、Crash、EOF/Usage 缺失不得标记为“未发送/免费”；至少保留保守预算或 PENDING/UNCERTAIN。

**A-03** `RESPONSE_OBSERVED` 要么已持久记录可以复验的完整 Observation/Usage + Receipt provenance，要么仅保守持有，**不能宣称精确幂等 settle**。

**A-04** Broker Reservation 的实际状态是结算权威；Journal `SETTLED`/`WORST_CASE_HELD` 必须与 Broker 最终状态一致。不能把 `ALREADY_SETTLED` 当作“已失败”。

**A-05** Retry Policy 仍为 `maxRetries=0`；任何不确定发送都不得由 SDK/Controller/Launcher 自动重试。新 Admission 可用于 **恢复操作**，不得据此重新发送同一 `call_id`。

**A-06** 本阶段仍为 synthetic Usage；不得将其当作真实供应商的账单，也不验证远端 Exactly Once。

### 2.3 IPC 与资源

**R-01** Frame/JSON/Seq/Hash/错误码验证仍然严格，超时必须是从请求生命周期起算的可执行真实 Deadline，而不是仅检查循环时间。

**R-02** 活跃连接数、队列、线程、子进程、Frame 大小、累计输出、Chunk 数、日志量、临时文件均必须有上界。

**R-03** Cancel 必须进入对应 `transport_id` 的控制状态；不同请求之间相互隔离，不允许全局布尔量取消所有请求。

**R-04** DSH 能收到合法的 `chunk:usage`（完整 synthetic Usage 时），也能在 Usage 缺失或非法时得到**错误终态**；Broker 结算证据与 DSH 流事件分开断言。

---

## 3. Agent 分工、Git 流程与审阅规则

### 3.1 角色

| 身份 | 职责 | 禁止 |
|---|---|---|
| Lead Agent | 核实 HEAD、冻结范围、分派并行工作、协调接口、逐项合并和复跑；制定裁定请求 | 直接修改项目源文件；单独给自己的实现签独立 PASS |
| C-RECOVERY Agent | Usage/Receipt/Observation、Broker↔Journal 幂等恢复、崩溃场景 | 修改 DSH 核心/LiveGate |
| C-IPC Agent | 错误码/Finish/Cancel/Deadline/Broker 超时/限流/增量读 | 更改冻结外部路由为真实 Provider |
| C-ADMISSION Agent | Admission enforcement、额度、并发/重放和测试证据 | 随意变更 BudgetLedger 不变量或放宽 Policy |
| D-ISOLATION Agent | 独立 Linux 主体/挂载/命名空间/UDS 权限、隔离启动器、攻击实验 | 启动真实 Key/网络调用 |
| Independent Reviewer | 从冻结 Commit 与新原始证据进行恶意复验，签限定范围结论 | 修改实现代码或复用 Owner 测试文字充当独立复验 |

### 3.2 推荐集成方式

- 先 `git status --porcelain -uall`、`git rev-parse HEAD`、`git ls-tree`；记录**远端和本地** SHA。开发可以在同仓库分支或独立 worktree；避免共享 mutable stage，避免两个 Agent 同时操作同一 SQLite/Socket。
- C Agent 可以并行写不重叠文件，交叉文件（尤其 `controller.py`）必须由 Lead 协调先后 cherry-pick，防止覆盖。
- 每个补丁做到：`source + focused tests + RED/GREEN + proof of no live`；小型独立 commit。不为补丁重新复制 700 文件旧 Packet。
- G3-C 提交单独 Review Packet 并 STOP；D 可基于已合并的 C Freeze 工作。
- 新版本不得伪造旧 RED：旧行为难以稳定重现的竞态记录为 `NO_DETERMINISTIC_RED`，用锁/事务/压测证据代替。

### 3.3 冻结记录

每个 Gate 至少记录：`base_sha`、`impl_sha`、`docs_sha`、`git diff --binary` hash、容器镜像 digest、Node/Python/DSH 锁、测试命令完整 argv、UTC、exit、源码/依赖 stage hash、Fake receipts+Broker DB+Attempt DB 的一致性摘要、0 Key/0 外部 HTTP 的证据，以及 Reviewer 的独立 SHA。

---

## 4. G0 — 只读预检 / 基线冻结

**目标**：确保本计划针对的实际源码与部署环境仍存在，不把“当前 HEAD 更改”覆盖回旧版。

1. 核对 `git remote -v`、本地/远端 `main` 和当前 `HEAD`；如远端不再是 `bb5bd0b`，列出与本方案相关文件的 Git Diff，逐条标记 `ALREADY_FIXED` / `STILL_OPEN` / `CHANGED_REQUIRE_REVIEW`。
2. 读取 `AGENTS.md`、`docs/M0_G3B_REVIEW_ERRATA.md`、`docs/REVIEW_G3B_INDEPENDENT.md`、`docs/M0_G3B_IPC_PROTOCOL.md` 和安全记账契约。
3. 检查禁用的 Real Provider 和 LiveGate；执行静态 grep + 现有 Gate 定向测试，不读取本机真实 Key。
4. 可用则复跑基础 Python/Node 无 Key 测试，至少保证 baseline tests 不被误认为 C 本轮的新成果。明确记录历史报告中的 665 pass/1 skip 是**旧证据**。
5. 冻结 G0 Report：`docs/M0_G3C_G0_BASELINE.md`、偏差表、测试环境指纹。

**验收 G0**：最新源码身份明确；不存在无解释漂移；本轮禁网/无 Key 测试环境存在；不把旧 B0-02 BLOCKED 修改为 PASS。**失败 STOP**。

---

## 5. G3-C1 — 协议、错误语义与 Admission 限额

### C1-01：错误码语义一致

**源头**：`bridge/protocol.py:26-40`；`bridge/controller.py:365-367`；`accounting/broker.py`。

- 明确 Broker 的 `CALL_ID_CONFLICT`、`IDEMPOTENCY_CONFLICT`、`ALREADY_SETTLED`、`ALREADY_FAILED`、`INVALID_USAGE` 等与 IPC 的映射表；必要时以**有限、冻结**的 `BROKER_*` 抽象代码映射，不暴露敏感详情。
- 接收到未知 Broker Code 应 fail-closed 为语义明确 `INTERNAL` / `BROKER_ERROR`（若正式加入 Protocol），**不得当成客户端 `UNKNOWN_FIELD`**。
- 只扩充必要的静态枚举，不让上游任意字符串成为成功回应。
- 校正 G3-B `B3-05` 冲突场景：失败侧确定拒绝，精确代码和 Fake 计数都应断言。

**测试**：`C1-01A` 同一 call_id 同 payload replay；`C1-01B` 同一 call_id 不同 digest；`C1-01C` Reservation 不匹配；`C1-01D` 合法拒绝 Error Envelope 能被 Python/TS 两侧解析。

### C1-02：Finish(error) 永远 Schema 正确

**源头**：`controller.py:359-363`、`fake_provider.py:109-110`、`protocol.py:271-287`。

- 为 Controller 生成标准 `finish.reason={kind:'error',failure:{code,message}}`；不得从 Fake 直接无校验地透传损坏的 Frame。
- 受损/非法 Usage 不得被美化为成功；允许终端 `error` Envelope 取代 `finish(error)`，但需统一、可测试且与 DSH adapter 约定一致。
- Fake 的 `error`、`partial_usage`、`no_usage`、`eof` 均独立断言具体 DSH 终态及 Broker 账本。

### C1-03：Admission 执行而非只解析

**源头**：`admission.py` 和 `controller.py:132-138,238-264`。

- `max_output_tokens`：检查 `requested <= admission.max_output_tokens`，并检查 Route 上限；超限必须在 Reserve/Claim/Fake 前拒绝。
- `max_calls`：将“无效请求”和“实际合法准入的 Model Call”拆成计数；不允许无效 Schema/Route 吞掉已授权额度。并发时用锁或可信事务原子扣配额；绝不能无限重放新请求。单个 Admission 的调用次数仍有总上限。
- `max_attempts`：每个 `call_id` 真实发送最多一次；不能仅靠当前 Controller 进程内计数。
- `deadline_ms`：Controller/IPC 的有效 Deadline 取 `min(admission.deadline_ms, 绝对上界)`；计入 Broker、Fake、响应写出与清理，并测试低于 30s 的限制确实生效。
- `max_input_tokens`：原代码 `min(1024, max_input_tokens)` 不是可信 Token 上界。**无 Key 阶段**至少将该估计明确标记 `synthetic_fixture_only`，按可信上界保守预留或拒绝；如无法从已锁定模型/Tokenizer/上下文上界证明请求输入 Token 上界，则不得声称可以安全地按该输入量进行真实付费准入。**接真实模型前**必须有独立认证的输入 bound/Tokenizer 校验，或采用供应商约束下可证明的最坏上界；不要用简单字符数、字节数/4、样例 Fake Usage 冒充保证。

**测试**：`C1-03A` admission 128 / request 512 → 0 Reserve/0 Fake；`C1-03B` 非法请求不吞额度；`C1-03C` 合法请求达到配额后拒绝；`C1-03D` 并发同配额不超用；`C1-03E` 小 deadline 实际生效；`C1-03F` 输入上界不可信时 fail closed 或使用受审保守界。

### C1-04：请求重放与业务冲突

- 完成 Reviewer `B2-05 PARTIAL`：重放同一 request、相同 `call_id` 不同 `prepared_digest`、相同 Reservation 不同 Route/Tool/消息、不同 IPC `transport_id` 但业务身份相同。
- 断言所有重放路径下 Fake 收据总数不增加；拒绝类型准确；第一次已 Settled 不会被新的错误重试覆盖。
- 不允许新增新的快捷旁路绕开现有 `EgressBoundary.claim_dispatch_for_request()`。

**G3-C1 出口**：协议两侧一致；Admission 限制在实际调用中生效；重放负例通过。不要在 C1 单独宣称端到端 G3-C PASS。

---

## 6. G3-C2 — Usage / Receipt / Observation / Crash-Reconcile

### C2-01：把“账本用 Usage”和“SDK 流中的 Usage”统一起来

**源头**：`fake/fake_provider.py:81-113` 输出独立 `kind:'usage'`，`controller.py:217-235` 未转发该种类；`protocol.py:213-258` 支持 `chunk:{type:'usage'}`。

1. 明确 Fake 内部 `kind=usage` 的解析与合法性验证；**只能在可信 Controller 侧**把其转换成 `chunk:{type:'usage',usage:...}`，保证在 `finish` 前，最多一次。
2. SDK 收到的 synthetic Usage 要与 Broker 映射前的已验证 Usage 一致；不要凭 Broker 是否 SETTLED 推断 DSH 自动收到 Usage。
3. 缺少/不完整/非法 Usage 必须正常 fail-closed；不得把缺失填为 0，也不能给 Fake 产生额外伪造 Usage。
4. 结算前后发 Chunk 的先后次序必须解释清楚：SDK 不得因看到可见的 `usage` 而被误认为 Broker 已结算；异常期间不可返回成功 `finish`。

**测试**：`C2-01A` 真实 DSH Echo SDK `assistant/message.data.usage` 逐字段等于 Fake Usage；`C2-01B` Tool 两轮各有独立 Usage；`C2-01C` no/partial/invalid Usage 不产生成功结束；`C2-01D` 多个 Usage / usage after finish / 流顺序错拒绝。

### C2-02：重启后的持久 Settlement 真正幂等

**源头**：`controller.py:98-130,333-351`、`attempts.py:113-161`。

- 在 `RESPONSE_OBSERVED` 提交时，持久保存**已经验证的**完整 Receipt identity + normalized Usage/Observation（包含 schema、digest、费用政策版本、raw receipt sha256、nonce、call_id、reservation_id、route/model 等可复核关联），而非只有 metadata/usage 缺席。
- 为重启恢复设计**单一权威判定流程**：先核验 Attempt 身份、Receipt digest/nonce、Broker 的持久最终状态；根据 Reservation 的真实状态选择 settle、fail、已结算归档或保守悬挂。
- 如果 Broker 已结算、Attempt 未标记成功：必须恢复为与 Broker 一致的 `SETTLED`/`WORST_CASE_HELD`；不能仅凭 `ALREADY_SETTLED` 将成功结算误写成 held。
- 若当前 Broker v1 无法以可靠只读接口查询 Reservation 状态，允许**最小兼容扩展**（如已审查的 read-only status op 或受信 DB 层查询），不得在 Candidate 暴露 DB，也不得更改 v1 原始 settle/fail 行为。
- 需要清晰的 Crash Windows：`after_reserve_before_claim`、`after_claim_before_attempt`、`after_attempt_before_send`、`after_fake_receive_before_response`、`after_response_before_settlement`、`after_broker_settle_before_journal_mark`、`after_journal_mark_before_sdk_finish`。
- 完整可信 Usage 才可标记 authoritative；Receipt 文件不合法、被篡改、跨 call/nonce、与 payload digest 不符或 provenance 缺失 → `SETTLEMENT_UNCERTAIN` 或 Worst Case（按 policy），绝不未经证据精确结算。
- Broker Settle 本身可能已成功而 IPC 回复丢失；重发同一个**结算操作消息**须保留幂等语义，不能造成二次扣费。

**测试**：`C2-02A` 完整 Usage + after_response crash → 精确 settle 一次、Fake=1；`C2-02B` after_broker_settle_before_journal_mark → Broker/Attempt 状态一致、无 double charge；`C2-02C` receipt 缺失 → PENDING/UNCERTAIN、Fake 不重发；`C2-02D` 持久 Receipt 中 Usage 冲突/改 nonce → 拒绝精确 settle；`C2-02E` 两次重启 reconcile 幂等、无新的 Fake；`C2-02F` Broker 已 failed 的恢复仍是 held，不错误标记 OK。

### C2-03：Observation 冲突及数据模型

- 原 G3-B 契约使用 O-3：Controller 将可信 Observation 映射到已有 Broker `settle/fail`；旧 `budget_provider_observations` 表未写入**不单独算故障**。
- 本轮选定**单一权威持久位置**（Attempt Receipt/Observation Journal 或已接受的 Broker 内建表），明确 `call_id`、reservation_id、receipt/raw bytes digest、normalized usage/observation digest、trusted source/provenance。
- 独立验证相同 Observation 重放无副作用、同一 Call 不同 Observation Digest 冲突拒绝、不覆盖已 settle 结果；如果错误处理需要独立表则提供**最小** schema migration，不重做整个 ledger。

**测试**：`C2-03A` 相同 digest replay；`C2-03B` 相同 call/不同 digest；`C2-03C` 缺 source provenance；`C2-03D` Broker 和 Journal 汇总一致；`C2-03E` 使用旧 v1 客户端回归。

### C2-04：Recovery Admission 与 Logical Step

- 将启动恢复定义为可信 Launcher/Controller 专用阶段：**先恢复旧 Attempt 还是先消费新 Admission**，必须有冻结的明确次序；不得因为 `ADMISSION_REPLAYED` 导致旧持久状态永远无法恢复。
- 如果保留“新 Admission ID 才能恢复”，则采用明确的 trusted recovery admission，仅准读取/结算旧 Attempt，禁止开启相同 call_id 新发送。
- 核对 `AttemptJournal.next_logical_step(run_id)` 是否被实际运行路径使用。如果未使用，只记录 P2，不要顺手重构；若使用则修正其忽略 run_id 的问题并补两个 Run 交错测试。

**G3-C2 出口**：Crash 后持久结果与 Broker 权威状态一致；Usage 贯通 DSH 与 Broker；不存在重复 Fake 或账本低估。

---

## 7. G3-C3 — Cancel、真实 Deadline、IPC 资源边界、增量 Streaming

### C3-01：修复 Cancel 契约并证明信号实际生效

**源头**：`ipc_server.py:270-300` 发送 `controller.cancel(transport_id,reason)`，`controller.py:187-188` 接收 `cancel(self)`。

- 修改为 `cancel(transport_id, reason)`，由 Controller 维护**每请求独立** `CancellationState`，绑定正运行的 transport_id 与 attempt/call。不能使用跨请求共享 `_cancel` Event 影响别的流。
- Cancel Reader 与 Controller 同步阻塞工作之间必须有能生效的检查点；避免仅设置 Event 却从未在 `_handle_payload()` / `_before_send` / Stream 执行路径读取。
- **发送前** Cancel：0 Fake，拒绝发送；已经 Claim 的许可不得在未来被重用；Resv 状态按保守 policy 释放/保留，记录原因。
- **发送边界后** Cancel：中止尽力而为，费用保持 Unknown/held，不声称免费、不重试；如果 Provider 已返回可信 Usage、应按正常可信数据或受审政策完成结算。
- 重复 Cancel、未知 transport_id、另一个客户端尝试取消其它连接、Cancel 与 Finish 并发等需无跨流误伤。
- 保留 SDK 不能公开单独取消 Turn 的现实限制：G3-C 验收要分 `Adapter.signal`、`Transport cancel`、`SDK process SIGTERM` 三层。不能用后一层 PASS 冒充前两层。

**测试**：`C3-01A` Pre-Send Cancel Fake0；`C3-01B` During-Fake Cancel 有受审状态；`C3-01C` 两并发请求只取消一个；`C3-01D` SIGTERM/断连之后子进程清理；`C3-01E` 错误签名必须测试失败而不是吞掉。

### C3-02：真正的 Deadline / Broker Timeout

**源头**：`ipc_server.py:194-208`、`broker_client.py:42-54`、`fake_backend.py:52-80`。

- 单次请求构造 monotonic `deadline` 并向所有阻塞边界传入*剩余时间*；Controller 处理在同步调用中也必须能被外部 Watchdog 限制，不得只靠 `while` 前检查。
- Broker Client 对 `stdout.readline()` 使用真正的 bounded read / select / IO worker 超时，并在 timeout 后将 Broker 通道视为状态不确定，停止后续信任该连接；不得隐式重发 Reserve/Claim/Settle。
- Fake Provider 读/写/退出也要服从该 Deadline；超时后收集能获得的 Receipt，判断 Attempt 是否已经开始，并保守写 Journal；进程树清理可确认。
- 区分 Client timeout、Server Deadline、Broker timeout、Fake timeout；每一类都 fail-closed，并记录可解释错误，不返回成功 finish。

**测试**：`C3-02A` Broker 子进程活着却永远不写 stdout；`C3-02B` Fake 卡住且已有 Receipt；`C3-02C` Admission deadline 100/300ms，实际壁钟上界有容差且无永挂；`C3-02D` Controller 崩溃后 Watchdog 清理；`C3-02E` Broker 回包丢失/延迟不得重复 Reserve/Claim。

### C3-03：UDS 连接和内存/线程容量

**源头**：`ipc_server.py:39-70,105-116,268,302-307`；`spikes/g3b-trusted-bridge/src/index.ts` 的 `FrameQueue`。

- 第一帧读取必须有总 Deadline，不能无限处理 `socket.timeout`；包括空连接、每隔 N 秒 1 byte 的慢连接。
- 限制**活跃连接数**，拒绝过载而不创建无限线程；完成后回收/清理线程注册；不要仅依赖 `listen(2)` 充当服务线程并发上限。
- 将共享 `_last_frame_bytes` 转为**每连接局部**计数；不要让相邻请求的 Ack 字节污染响应大小统计。
- Adapter `FrameQueue` 必须限制缓冲的帧行数和累计 bytes，并且保持 `totalBytes`, `MAX_CHUNKS`、消息深度、响应单帧与总字节约束。对超出阈值的流主动断开并清理。
- 增加超过 Frame、无 LF、坏 UTF-8、重复 JSON key、非法 seq、超深嵌套、多个 finish、错误响应后继续发送等负例；确保所有拒绝均无额外 Fake 发送。

**测试**：`C3-03A` 空连接/半关闭；`C3-03B` 慢发送；`C3-03C` 超过最大活动连接数；`C3-03D` 大量响应 Chunk/慢消费者；`C3-03E` 两并发请求互不污染字节预算；`C3-03F` 大响应/异常帧内存上界；`C3-03G` 取消后无僵尸线程。

### C3-04：增量 Streaming（与 Buffered Fake 分开标注）

**源头**：`fake_backend.py:52-80` 的 `subprocess.run(stdout=PIPE)`。

- 真实输出路径改为有界、可取消、支持逐条读取的实现；可以使用 `Popen` + async/reader thread + bounded queue，但不得无限 `communicate()` 缓冲。
- 保留已有 Fake Receipt-first fsync 设计；所有帧经 Controller/Protocol 验证，再持续推给 DSH。
- 单个结果无法持久证明送达 DSH 并不意味着 Provider 未发送；收到部分 Chunk 然后崩溃时仍需保守记账。
- **必须证明首个 Chunk 在 Fake 进程退出前到达 SDK**，否则只能声称 buffered replay，不得标记 real-time streaming PASS。
- 使用慢生产者 + 慢消费者 + Cancel 场景测背压，证明峰值内存、队列长度、FD/child/thread 数不随消息无限增长。

**测试**：`C3-04A` 首个 Chunk T1 < Fake 退出 T2；`C3-04B` 256 chunk 上限；`C3-04C` 1 MiB 累计输出上限；`C3-04D` consumer stall bounded；`C3-04E` 途中断流保守且无 success finish。

### C3-05：并发测试与 Trace 质量

- `run/concurrency.py` 增加基于 UDS ready/barrier 的确定性同步，不要依赖 `sleep(0.x)` 幸运时间差。
- 记录 crash/reconcile **第一次与第二次**状态文件，避免后一次覆盖前一次；保留旧 Packet 不改。
- 每个测试输出 `call_id → reservation_id → claim → attempt_id → receipt → observation_digest → broker_status` 的可追溯行。

**G3-C3 出口**：取消、超时、流式输出和资源限制都有动态证据；本轮不能把 `PARTIAL`/`UNVERIFIED` 文字直接改为 PASS，必须见到原始 trace。

---

## 8. G3-C 集成测试与 Review Gate

### 8.1 最小成功集（仍然真实 DSH，无 Key）

- DSH SDK Echo（1 model call，1 Claim，1 Receipt，1 Broker settle，SDK Usage 可见）。
- DSH SDK Tool/Skill Lookup（至少 2 model calls，各自独立 Reserve/Claim/Attempt/Receipt/Usage；第二个请求带真实 Tool Result）。
- Session 新进程 Resume（历史 Session 可恢复，Broker/Journal 不混淆）。
- Guard precheck 存在与不存在的组合（外层准入结果独立，不对 Guard 做安全放行的单点信任）。
- G2 回归、G3-B 33 行关键路径回归、真实 DSH Node 适配器原生测试、Python 全量回归及静态检查。

### 8.2 高风险负例

- 无 Claim 或伪造 Reservation / 篡改 Prepared 内容 / Route/Model/Tool Schema 不符 → **Fake=0**。
- `after_claim_before_attempt` 与 `after_attempt_before_send` Crash；Provider Received 但无 Settlement；Broker Settlement 成功但 Attempt 尚未标记 → 状态正确、无重发。
- Bad/partial/missing Usage，伪造 Receipt digest，重复/冲突 Observation → 不得免费、不覆盖已有 Settlement。
- Invalid UDS Frame、未完成连接、无限阻塞的 Broker/Fake、双进程竞争单次 Claim → 无未授权 Fake、资源有界。

### 8.3 G3-C PASS 规则

必须满足：

1. 所有原 G3-B P1（Receipt/Settlement、Cancel）闭环完成；协议错误语义、Finish schema 与 Admission 实际限额一致。
2. 新增静态发现的 Usage 透传、Broker Deadline、首帧 Deadline、资源上界与增量输出均有**独立动态**证据。
3. 不存在 Fake 已收到却被写成 `NOT_DISPATCHED/FREE`；任意不确定发送不自动重试。
4. 完整 DSH Echo/Tool/Resume 通过，且 Broker/Attempt/Receipt 的关联正确；全量已有回归无意外失败。
5. 独立 Reviewer 复核 Commit 与关键测试，并给出 `PASS_FOR_G3C_NO_KEY_CONTRACT_RECOVERY_SCOPE` 或 FAIL/PARTIAL/BLOCKED。不能用实现者自述代替独立复验。

**若资源控制或真正流式读取的实现范围过大**：Lead 可以将其拆成单独 C3 微批次，但 `B3-10/B3-11` 不能在最终 G3-C 验收中默认为 PASS；必须保持 UNVERIFIED/PARTIAL 并提交维护者决定。

---

## 9. G3-D0 — OS 安全边界设计冻结（可与 C 修复并行预研）

### 9.1 明确威胁模型

候选 DSH 可运行不可信插件/任务指令，可以尝试：访问文件、打开 Socket、连接 Broker、伪造 Admission、注入环境变量、复用 FD、读取 `/proc`、创建软链接、重启自身、调用内置工具。只需在受测攻击能力范围内证明 OS 实际拒绝，不声称抵御内核逃逸/宿主 root/硬件攻击。

### 9.2 必须冻结的 OS Principal 设计

- **Candidate 主体**：Rootless / 无 Linux capabilities、独立 UID / User Namespace / Mount Namespace / PID Namespace、只读代码与依赖、禁止外部网络，且仅有固定 IPC 访问权。Candidate 中没有 Broker Policy、DB、Admission、Receipt、Future Key 或可信 Launcher 控制路径。
- **Trusted Controller 主体**：单独 OS UID/命名空间或独立容器，维护 Admission、Attempt、Broker、Fake；仅对 Candidate 暴露一个最小 UDS IPC endpoint（通过共享 socket 挂载或独立代理）。本阶段不持有任何 Key。
- **可信存储**：Broker SQLite / WAL / SHM、Policy、Admission、Receipt、Attempt、可执行路径和配置全部放在 Candidate 未挂载或 Kernel 拒绝的目录中；不可仅以同 UID 的 `chmod 600` 作为结论。
- **Socket**：如果 Candidate 与 Controller 不同 UID，按实际运行时 UID/GID 映射，使用受审 UNIX socket 权限/专用 group/代理，并检查 `SO_PEERCRED`（可获得时）；**允许连 Socket 不等于允许 Broker DB 或任意 Controller method**。
- **进程监管**：Launcher 独立于 Candidate；Controller/Fake 的生命周期由可信 Supervisor 或 OS 机制管理；Candidate 崩溃不能留下可被后续 Candidate 接管的 FD/Socket/文件。

### 9.3 G3-D 方案签核问题

D Agent 先提交 `docs/M0_G3D_OS_BOUNDARY_DESIGN.md`，包含：PID/UID/Namespace 映射、bind mounts、ro/rw 目录、UDS 连接权限、文件/进程可见性、nspawn/podman/OCI 参数、网络设备与路由、可信 Key 未来放置位置**仅作为路径设计**、攻击脚本、回滚和清理过程。

若不能在当前机器/Runner 上建立实际两主体隔离，不得变成 mock 的“安全通过”，必须报 `BLOCKED_NEEDS_ENVIRONMENT`。

---

## 10. G3-D1 — OS 隔离实现及正向连通

1. 从 G3-C 完成并验收的代码冻结点新建 D 分支；**候选进程与可信 Controller 不能再使用同一 OS UID/同一可写挂载集合**。
2. 创建固定的无 Key OCI/Podman 启动与清理脚本，使用一次性运行层；避免多 Agent 共享 Rootfs 造成哈希漂移。
3. Candidate 仅挂载自身 SDK/DSH/Plugin/Session 临时目录及经授权的 UDS；Trusted 侧持有 Broker/Attempt/Admission/Fake/Policy/Receipt 的读写位置。
4. 权限设计下，Candidate 通过 `LlmAdapter` 可以正常连接 UDS；Trusted Controller 可以完成 Broker Bound Claim 与 Fake Receipt；生成同样的 Echo/Tool/Resume Trace。
5. 进程退出必须清理 socket/挂载/子进程/孤儿进程，并保留实际 OS 负例证明。

**D1 不能只展示文件权限表；必须提供 Candidate 发起的攻击命令和内核实际返回的 errno/exit。**

---

## 11. G3-D2 — 恶意候选攻击测试

全部攻击**从真正的 Candidate 身份/容器内**执行；禁止从可信 Controller 的 UID 伪造 Candidate 结果。

| ID | 攻击 / 期望 | 核验依据 |
|---|---|---|
| D2-01 | Candidate 读取 Broker `.sqlite3`, `-wal`, `-shm` → 拒绝 / 不可见 | 原始 errno、容器 UID/Namespace、mountinfo |
| D2-02 | 写 Broker DB 或修改任一行 → 拒绝；Broker hash 和数据行不变 | 攻击前后快照、日志 |
| D2-03 | 读取/修改 Policy、Admission、Attempt Journal、Receipt → 拒绝 | 文件不挂载或内核拒绝、Hash 不变 |
| D2-04 | Candidate 直接启动 `python -m autoteacher_m0.accounting.broker` 并操作真实可信 DB → 无法触及可信文件 | 环境、工作目录、真实 DB 路径证明 |
| D2-05 | 绕过 Controller 使用旧 v1 Unbound Claim，尝试到达可信 Fake → 无 Fake 收据 | Broker/Controller 授权日志 + 收据计数 |
| D2-06 | 伪造 Admission/Policy/Route/Tool 或 UDS payload → Controller 拒绝 Fake 0 | 协议 error 与 Fake/ledger |
| D2-07 | 尝试直连外部 TCP/HTTP、DNS、Unix 任意 Socket → 实际拒绝 | OS 网络/Socket 错误、无外部 HTTP |
| D2-08 | 尝试读取信任侧 `/proc/<pid>/environ`、FD、cwd、root → 拒绝/不可见 | pid namespace 与权限证据 |
| D2-09 | Candidate 任意工具执行/Guard 不加载 → 未授权外呼仍被 Controller 拦截 | DSH 错误、Fake 0 |
| D2-10 | Candidate Ctrl-C/SIGKILL/Crash、UDS 断连、重启 → Controller 的 Attempt/账本保守一致 | Reconcile/Socket/进程清理 |
| D2-11 | 成功正向 DSH Echo/Tool/Resume，验证没有因隔离导致误伤 | SDK events、Tool result、Receipt、DB |
| D2-12 | 并发多个 Candidate/慢请求，不能逃过资源配额 | 并发 barrier、资源峰值 |

如 Runner 具有限制无法执行某项攻击，应标 `BLOCKED` 并说明原因；**缺少证据不能记 PASS**。尤其必须重现旧 Reviewer 的四个成功绕过操作，并证明它们现在被内核拒绝。

---

## 12. G3-D3 — 跨主体故障与组合回归

- 双 Container/UID 下从真实 DSH 执行 Echo（1 Call）和 Tool（2 Call）；Session 新进程恢复；Guard precheck 分支及 Guard 缺失均使用 Controller 决策，不倚赖 Candidate 内 Guard 放行。
- 在可信与候选不同步崩溃的不同窗口验证 Journal/Receipt 的持久语义、无重发、Broker 状态一致。
- 拒绝候选对 Broker DB/Policy 的直接调用后，必须仍允许合法 UDS 正向调用；否则只能说明“全部禁用了”，不是可信 Bridge 实验通过。
- 验证 Container 启停后无残余 UDS、WAL 对外可见、Key env（本轮必须不存在）、额外可见挂载、任何孤儿 Broker/Fake/Watchdog。
- 独立 Reviewer 使用固定 Git SHA、OCI Digest/挂载配置及新的攻击脚本复验 D2-01..D2-12 中的高风险项。

**G3-D 通过条件**：内核拒绝实际攻击 + 正向链路仍可用 + 使用同一冻结 SHA 可复现 + 无 Key/HTTP + no-live 不变量不变。

---

## 13. 统一验收证据与判定语义

### 13.1 每个 Test Case 需要的 Evidence

```text
case_id, gate, status, test_type, base_sha, impl_sha, test_sha,
container_image_digest, rootfs_hash, deps_hash, runtime_version,
command_argv, UTC_start, UTC_end, exit_code,
source_or_diff_ref, logs_ref, trace_ref, db_snapshot_ref,
receipt_ref, fake_received_before, fake_received_after,
expected_outcome, observed_outcome, independent_reviewer, notes
```

状态只允许 `PASS` / `FAIL` / `PARTIAL` / `BLOCKED` / `UNVERIFIED` / `NOT_RUN` / `N/A_WITH_JUSTIFICATION`；对无法证明的结论不得写 PASS。任何 `BROKER PENDING` 都要在预算报告按保守规则计算。

### 13.2 关键跨系统关联格式

每条实际 Model Call 最低形成以下不可缺失的关联：

```json
{
  "run_id": "...",
  "logical_step": 0,
  "call_id": "call-...",
  "prepared_digest": "...",
  "reservation_id": "...",
  "bound_claim": "CLAIMED",
  "attempt_id": "att-...",
  "attempt_started_durable": true,
  "outbound_payload_digest": "...",
  "fake_receipt_raw_sha256": "...",
  "observation_digest": "...",
  "broker_reservation_status": "OK|FAILED|PENDING",
  "journal_final_state": "SETTLED|WORST_CASE_HELD|SETTLEMENT_UNCERTAIN"
}
```

这些字段以**可信控制面实际持久化结果**为准，不得由 DSH 假消息代填。原始 Prompt/Key 不必明文出现在审阅包；采用受审的摘要与必要的脱敏样例。

### 13.3 停止条件（触发即 STOP）

- 发现任何未获 Bound Claim 的 Fake 发送、Claim 重放造成第二次发送、无 Attempt 却开始 Fake、修改已结算账本的非法回滚。
- 有 Fake 收据，但 Controller/账本报告 `NOT_DISPATCHED` 或零成本；后续重启自动重发 uncertain Call。
- G3-D Candidate 实际可写可信 DB/Policy/Admission，或可绕过 Controller 触发实际可信发送路径。
- 测试出现真实 Key、供应商付费 HTTP、真实模型调用、LiveGate 自动解锁或越权的主机访问。
- Artifact 源码/测试/镜像 SHA 无法核实，或实现者改了冻结 Review Packet。

---

## 14. 新 Review Packet 要求（精简但可独立复验）

### 14.1 G3-C Packet

```text
artifacts/review-packet-g3c-<impl_sha>/
  README.md
  manifest.json                # base/impl/docs/test SHA、OCI digest、scope、no-key
  hashes.sha256
  diff.patch                   # 只含本轮变更；Git 现场可复算
  review-request.md
  findings-and-disposition.md # 每个 SRC/Reviewer finding 的修复/残余
  evidence-matrix.csv         # 全部新 Case 原始状态
  tests/                      # 相关新增测试（优先可从 Git 重建）
  traces/                     # Echo/Tool/Resume、reconcile1+2、cancel、usage、负例
  ledger/                     # SQLite只读一致性快照/查询结果与 schema
  receipts/                   # Fake receipt raw sha/长度/usage digest
  logs/                       # 完整命令、UTC、exit、stderr、no-Key断言
  env/                        # runtime/rootfs/deps/Node/Python/DSH锁与哈希
  reviewer-reproduction.md
  security-nonclaims.md       # OS Boundary BLOCKED；无 Live/真账单证明
```

### 14.2 G3-D Packet

在 C Packet 上增量交付：Candidate/Trusted 各自的 `id`, `/proc/self/{uid_map,gid_map,mountinfo}`, OCI config、socket 权限、文件路径的 actual deny probes、完整退出清理快照、正向 DSH 调用证明、攻击复验脚本与误报解释。**不要复制整个 G3-B 历史 708 文件**。

### 14.3 独立 Reviewer 复核顺序

1. 核实代码/证据身份、变更范围及 LiveGate 冻结。
2. 从可发送的 Fake 入口逆向追踪许可与 Attempt；审阅 Cancel/Deadline/Recovery 状态机。
3. 独立构造至少一个新 Crash 窗口、一个错误 Usage、一个协议畸形帧、一个连线阻塞和一个跨主体文件写入攻击。
4. 复跑真实 DSH Echo/Tool/Resume；对每个 `call_id` 交叉检查 Broker/Attempt/Receipt/DSH Usage。
5. 给出逐项 `PASS/FAIL/PARTIAL/BLOCKED` 与确切 `file:line`、命令、预期/实际证据，不可只复制 Owner 的矩阵。

**明确分开两份 Verdict**：

- `PASS_FOR_G3C_NO_KEY_CONTRACT_RECOVERY_SCOPE`：契约与恢复范围。
- `PASS_FOR_G3D_NO_KEY_OS_TRUST_BOUNDARY_SCOPE`：OS 阻断与正向集成范围。

其中任何一项均**不能授权 G4/G5/Live**。当两者通过，Lead 仅向维护者请求*是否启动 G4 PreLive*的另一次明确决策。

---

## 15. 推荐实施次序（不制造多余关口）

| 顺序 | 工作 | 可否并行 | 何时停止 |
|---|---|---|---|
| 0 | G0 最新 HEAD / Runtime / Lock 确认 | 必须先 | 身份不清立即 STOP |
| 1 | C1 协议/Admission + C2 Recovery/Usage | 可由不同子 Agent 并行，协调 controller.py | 定向 RED/GREEN、代码评审 |
| 2 | C3 Cancel/Deadline/IPC/Streaming/资源 | 部分可与 C1/C2 并行，不同时改同一行 | B3-10/B3-11 必有证据或明示 BLOCKED |
| 3 | C Full / 独立 C Review | 必须在功能集成后 | **STOP，维护者签收** |
| 4 | D0 隔离设计与环境预研 | 可与 C 实施并行，但不能自称 PASS | D 方案冻结 |
| 5 | D1/D2/D3 实际 Linux 隔离 + 动态攻击/回归 | 基于 C 冻结 | 攻击失败/正向成功 |
| 6 | D 独立安全复核 | 独立身份 | **STOP，维护者决定下一步** |

允许 Lead 一次性编排多子任务，但**禁止自动越过独立 C/D review 的停止点**。如果本机不能做双 UID/mount namespace，G3-D 允许报告 BLOCKED 及需要的最小 Linux 权限，不应在没有环境的机器上用模拟结果冒充完成。

---

## 16. 发给 Lead Agent 的可直接复制指令

> 你现在负责 Autonomous Teacher M0 的下一迭代。请完整阅读本任务书、仓库 `AGENTS.md`、`docs/M0_G3B_REVIEW_ERRATA.md`、`docs/REVIEW_G3B_INDEPENDENT.md`、G3-B IPC / Security & Accounting Contract，并从 GitHub/本地 Git 实际 HEAD 核验冻结输入。你是 Lead，只编排与审计，实际代码变更委派给不同 Implementation Agents；所有测试须在无真实 Key、无网络、锁定环境执行。
>
> **先执行 G0 → G3-C1/C2/C3 → C Review Packet → STOP。** C Agent 可按非重叠文件并行；任何共享 `controller.py` 的修改必须顺序集成、做交叉回归。不得自行启动 G4/G5/Live。允许并行完成 G3-D0 的只读设计与环境可行性预研，但 G3-D 实际隔离请以 C 冻结代码为基线。
>
> 修复本任务书 SRC-01..SRC-11（SRC-12 先确认是否在运行路径使用），同时关闭 Independent Reviewer P1-1/P1-2 与 P2-1..P2-7 的相关问题；每项有 Source Diff、定向负例、实际状态、明确 Evidence 和未解决残余。尤其核实 B3-08 崩溃恢复幂等、Cancel 实际传播、Broker read timeout、Admission 实施上限、Fake Usage→DSH StreamChunk.usage、首帧 Deadline/资源上界、增量输出与真实背压。不得将被动 `UNKNOWN_FIELD` 或保守 hold 当作完整语义 PASS。
>
> 完成后冻结 impl_sha、提交 docs/M0_G3C_IMPLEMENTATION_REPORT.md 和 docs/M0_G3C_REVIEW_REQUEST.md、新的 Review Packet 与 Matrix，并 STOP 等待独立复核。再根据维护者授权继续 G3-D：建立不同 OS 主体，实际拒绝 Candidate 读写 Broker/Policy/Admission/Attempt/Receipt、越过 Controller 调用 Broker；同时保留合法 DSH Echo/Tool/Resume，并交独立 Reviewer。严禁使用真实 Key/模型/API、外网、生产 Live；所有不实证的部分标 PARTIAL/BLOCKED/UNVERIFIED。

---

## 17. Owner / Reviewer 最终收件清单

交付 G3-C 时仅需优先给维护者/外部审阅者：

1. `docs/M0_G3C_REVIEW_REQUEST.md` 与 `docs/M0_G3C_IMPLEMENTATION_REPORT.md`；
2. `git diff <base>..<impl>` 或冻结源码访问 SHA；
3. 新增 tests + `G3C_Review_Evidence_Matrix.csv`；
4. Echo/Tool/Resume/Crash/Cancel/Usage/Resource 原始 Trace 与 SQLite/Receipt 对账；
5. 独立 Review 报告与残余风险裁定。

G3-D 则追加 OS 隔离启动配置、真实 Candidate 攻击及内核拒绝证据、合法 UDS/真实 DSH 成功证据。**不需要重新打印 G3-B 历史全部报告，也不需要再发明新的 G0/G2 审计体系。**

### 结束原则

> **G3-C 修真实语义，G3-D 验操作系统拒绝。** 两者都通过后才讨论 G4；不因测试很多就自动认定 M0 GO，也不为追求完美框架无限推迟真正的端到端验证。
