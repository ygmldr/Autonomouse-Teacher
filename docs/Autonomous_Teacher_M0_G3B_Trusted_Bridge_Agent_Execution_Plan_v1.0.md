# Autonomous Teacher — M0 G3-B 可信调用闭环：Agent 执行、测试与独立审阅任务书

> **版本**：v1.0 · 2026-11-17 · 语言：简体中文  
> **执行范围**：**仅 G3-B；真实 DSH + 无 Key 受控 IPC + 真实 SQLite Broker + 模拟 Provider + Observation/Ledger**  
> **授权状态**：允许开展离线、无凭据、无外部网络的实现与验证；**未授权 G3-C、G3-D、G4、G5、G6、Live、真实 DeepSeek/OpenCode Go 调用**。G3-B 完成后必须 STOP，交 Review Packet。  
> **文件定位**：建议放入 `docs/M0_G3B_TRUSTED_BRIDGE_EXECUTION_PLAN.md`。本文件是执行指导，不替代 M0 v0.4 强制 E1–E5、已批准 ADR、Request Binding Contract 或真正的人工授权。

---

## 0. 给 Lead Agent 的最高优先级指令（先读）

你要解决的**唯一核心问题**是：在**真实 DeepSeek Harness Runtime 与 SDK**中，每一次 `LlmAdapter.stream()` / 实际模型请求，能否通过**不受候选 DSH 控制的**可信 Controller 做**规范化、Budget Reserve、Bound Claim、持久化 Attempt、Fake Provider 发送、可信 Observation 和保守结算**，全程不使用真实凭据和外部网络，并能在崩溃/重放/并发/工具轮次下保持正确。

请遵循以下规则：

1. **先读取现场源码并核实 Git HEAD**；不要把本任务书中的示意接口当作已经存在的 API。对当前实现先做“能力清单/差距表”，逐项复用 G2、G3-A 的现有能力，不重建账本、DSH Provider Framework 或测试框架。
2. **优先最小纵向切片**：真实 DSH SDK → `LlmAdapter.stream` →受控 IPC →可信 Controller →持久 SQLite Broker → Bound Claim →独立 Fake Provider → Observation → Settlement → DSH StreamChunk。单次请求先通过，再补 Tool Call、故障矩阵和并发。
3. **每个可计费 Attempt 唯一、独立**：一条 Reservation 对应一个可发送 Attempt；一个 Turn 可包含多个模型请求；工具结果返回后的第二次 `stream()` 必须再次 Reserve/Claim，不依赖 `request/header` 数量。
4. **候选 Runtime 不可控制安全根**：任何 DSH 插件、会话文本、Tool Output 或模型消息都不能直接写 Ledger、签发 Claim、修改可信 Policy、决定“AUTHORITATIVE”、设置授权额度或取得敏感变量。无 Key 是底线；跨 OS 边界尚未证明时，只能称“进程/接口集成 PASS”，不能称安全隔离 PASS。
5. **默认拒绝**：没有真实 Bound Claimer、身份不匹配、Guard 缺失且无独立授权、没有持久 Attempt 证据、超时不确定、重放/并发冲突、缺失 Usage、非法 Chunk、非法 Tool → 不发送或保守 Pending；不得静默回退到 `claim_dispatch()` 的旧 unbound 路径。
6. **本轮禁止联网**：禁止访问或读取真实 Key、使用真实模型、访问真实 DeepSeek/OpenCode Go、打开 `LiveGate`、修改 `scripts/run_live.sh` / `runtime/dsh_adapter.py` 的 Live 硬阻断、使用不受审的宿主运行环境来替代隔离容器。
7. **严格分层证据**：Python 单测 ≠ 真实 DSH SDK；进程内 Fake Provider ≠ 独立 IPC；本地模拟 Provider 的“wire” ≠ 真实外部 HTTP/账单；本地 Claim 至多一次 ≠ 远端 exactly-once。
8. **STOP**：完成本文 G3-B 验收和交付后立即停止，不能以“用户预计会同意”为由自动启动 G3-C / G4 / Live。

### 本轮成功的最小定义

- 在固定、禁网、无 Key 的受审容器中，真实 DSH SDK 使用锁定 `0.2.2-rc.2`（或经维护者重新审批的实际版本）执行至少一个完整的成功调用，所有中间阶段在同一 `call_id` 上可关联。
- 一次真实 `skill_lookup` 工具循环产生**两个**互异、可核对的 `call_id` / Reservation / Bound Claim / Attempt / Observation；真实工具结果被第二个模型请求携带。
- 针对缺失 Guard / Broker、假 Claim、无授权、重放、消息篡改、崩溃与未知费用，具备**真实进程或 SQLite** 的可重复负向证据；不得凭 Mock return `False` 宣称外部边界已证明。
- 从已获批、规范化的**不可变出站负载**发出 Fake Provider 请求，Fake Provider 原始字节收据与 Controller 的授权负载哈希一致。
- 独立 Review Packet 包括冻结源码、真实 DSH 运行日志、Broker DB 状态、原始 Receipt、可重跑命令和全部未验证项。

---

## 1. 事实基线：这些已经完成，请勿重做

下列结论来自已提交的**报告/前轮审阅材料**；实现前仍需在实际 Git 仓库现场确认 SHA、源码位置与测试可执行性。不要将报告叙述冒充你这轮新运行的结果。

### 1.1 已有 G2 能力

- G2-L1 相关实现曾冻结在 `2786e25a9e5bd590255026d76fc362abb16d0e7b`；其接口形成 `CallIdentity`、`PreparedProviderRequest`、`claim_dispatch_for_request`、`BoundBrokerClaimer`、`DispatchPermission`、`TrustedEgressTransport`。
- G2-L1.1 代码实现提交 `bf1e84dab9c74f1bec919633672dc29abfa7a77b`；独立审阅 `PASS_FOR_DECLARED_G2L11_SCOPE`，对 Python 离线/回归有限定范围 PASS。
- G2-L1.2 实现提交 `53d7ba54591798ff3cd6791ea881063351b74dcb`，对应报告 `M0_G2L12_HARDENING_REPORT.md`；报告称修复 cancellation、`run_id` 统一、Broker completion precheck 同事务、文档证据漂移，记录全量 `634 passed, 1 skipped`。**这不是本轮独立重跑的计数**。
- 现有 Broker 支持 SQLite 持久预算、Scoped Policy、Reserve、Bound Claim、Settlement、Call/Reservation 关联；旧 v1 unbound Claim 保留兼容，但**不得成为 G3-B 的可信发送路径**。
- `M0_REQUEST_BINDING_CONTRACT.md` 已批准 **Option A**：实际 Request Route/Model 必须同 Reservation 权威记录比较；`request_digest` / `call_id` 在可信端重算。

### 1.2 G3-A 可复用的真实证明

参考 `docs/M0_G3A_PROVIDER_BRIDGE_SPIKE_REPORT.md`；报告中原始运行对象：

| 能力 | G3-A 范围 | G3-B 不应重复 / 应补的内容 |
|---|---|---|
| 真实 DSH | 锁定 `0.2.2-rc.2`，Node SEA runtime `1cc41d5a8745a5b9d47c8604e44f23eb8af2d8ca02b2afa0be101d5f71be6ea4` | 保留真实 SDK/Runtime 和公开插件；不写伪 DSH |
| 扩展点 | Cordis `LlmAdapter` + `ctx.llm.registerAdapter()`，`stream()` 获取组装后的 `GenerateOptions` | 在每次 `stream()` 进入可信 Bridge 路径；不可从 `request/header` 推次数 |
| IPC | DSH 插件 `spawn()` Python 子进程，stdio NDJSON | 将 Fake 子进程通道重构为受监督、可断开/拒绝的可信 Controller 通道，确保 DSH 不能任意控制权威状态 |
| Tools | 真实 `skill_lookup` 插件执行，tool Turn 出现 2 次 Bridge Request | 两次均单独 Reserve/Claim/Attempt/Observation/Settlement |
| Streaming | 两个独立 Text Delta 保留；`block-start/end`、`usage`、`finish` | 在流式头/中段失败时保守处理，限制帧大小、总字节、内存、超时 |
| Session | 新 Worker 经 `resume_session` 恢复 DSH v4 JSONL | 验证恢复不重复 Claim，`run_id`/`call_id` 重放逻辑稳定 |
| Faults | EOF→`STREAM_CLOSED`；Fake error→`SERVER`；Runtime SIGTERM 后 Fake 被清理 | 要求外部 Attempt 状态先于发送持久化，不确定后无自动重试 |
| Usage | Synthetic 计数原样透传（示例 11 input、5 output、2 cache read） | 由可信 Fake 收据转 `ProviderObservation`，账本记账；不可据此推断真实发票 |
| Guard | 原生 Node 测试 15/15，但 Bridge profile **未加载 Guard** | G3-B 将 Guard+Bridge 组合验证，并证明缺失 Guard 时外部发送权独立拒绝 |
| 隔离 | Runtime/Fake 同容器、同 UID，仅子进程清理 | G3-B 至少把执行所有权与可信侧区分；真实 OS 独立强隔离若尚未实现，诚实列 G3-D / PreLive 阻断 |

G3-A 报告的 `6 cases / 7 Bridge requests / 7 traces` 是**合成 Provider 可行性证据**，其中工具轮两次请求只对应一个 `request/header`。已知单 Turn SDK cancel 公开方法未证实；M0 允许以独立 Worker kill/resume 作为备选，但要保留不确定账单并证明清理。

### 1.3 本轮要现场确认的最新版身份

用户提供的历史后续提交（必须 `git rev-parse` / `merge-base` 核实，不得直接假设存在于当前工作树）：

- G2-L1.2 implementation：`53d7ba5`，docs：`28e260d`。
- G3-A Spike implementation：`64b057b`，docs：`a507e25`。
- G3-A 报告生成时记录 `HEAD=28e260d`，且当时未 commit；后续提交应核实父子关系、`spikes/g3a-provider-bridge/` 的实际 Git blob 与 Packet 的一致性。
- `docs/Autonomous_Teacher_M0_v04.md` 是 E1–E5/GO 判定正式基准；本文件不取代它。

**G0 输出**：`docs/M0_G3B_BASELINE.md` 写明 `git rev-parse HEAD`、工作树是否 clean、Code Tree SHA、DSH/SDK/Node/Python 版本和哈希、G3-A Spike 的真实路径、所有复用模块的公开入口/当前限制、v0.4 强制条款映射与当前尚未验证项目。若需修改依赖/版本，先作独立变更并经 Lead 批准，禁止静默升级。

---

## 2. 工作组织：仅五个实施包，禁止无限扩展

| Work Package | 负责人建议 | 工作内容 | 完成后必须留什么 |
|---|---|---|---|
| B0 | Lead/Integrator | 冻结代码与环境、审查 G3-A Adapter、盘点 G2 Broker 真实 API、找出运行边界 | `M0_G3B_BASELINE.md`、接口映射、可复验启动命令 |
| B1 | Runtime/Protocol Agent | 最小 IPC v1、真实 DSH Adapter 转发、Frame/Stream/Cancel/错误语义 | `protocol.md`、Schema、真实 SDK→Controller 假收据 |
| B2 | Security/Accounting Agent | Trusted Controller、CallIdentity、Reserve→Bound Claim→Attempt 持久化→Fake Send→Observation | 一条完整 Ledger Trace、失败前拒绝用例 |
| B3 | Integration/Chaos Agent | Tool 2-call、Session、重放、崩溃恢复、并发、Guard 缺失、资源上界 | 完整负例矩阵、SQLite/进程证据 |
| B4 | Reviewer Prep Agent | 全量回归、打包、Freeze、Review Packet、STOP | 不含 Key 的审阅包与 handoff |

Lead 可以并行 B1 协议与 B2 数据库调查，但**合并版本必须以统一的请求/状态机为准**，不得让各 Agent 各自发明 `call_id`、预算状态或错误枚举。建议 B0 完成后允许 B1/B2 并行；B3 必须等待两者最小链路合并。

### 2.1 默认修改范围

优先在 `src/autoteacher_m0/bridge/`（新模块，如实际仓库布局不同则选择等价路径）、G3-A 插件的独立可审查副本、`tests/integration/g3_bridge/`、有限 `accounting` API 扩展中实现；复用 `security/egress.py` 与 `accounting/{broker,ledger,call_identity,observation}.py`。

**禁止**不必要的 G2 大重构、引入新数据库或 ORM、新通用 Agent 框架、重新设计整个 SDK、无限重试机制、真实网络 Proxy、密钥管理产品化。任何新协议/DB schema 迁移须有版本号、旧 v1 兼容负例及 Lead 同意记录。

### 2.2 决策分级

- **无需额外批准**：纯无 Key 单测、禁网容器、独立 Fake Provider、保守账本、严格 IPC/Schema、无 Key 的 DSH 合成 SDK 集成。
- **需要 Lead 在 G3-B 内签核设计**：新增 Broker 协议 op/持久状态迁移、可信 Controller 与 Runtime OS 边界方案、和已批准 Option A 的兼容变更、修改冻结测试环境。
- **本轮无法授权**：任何真实 Key/供应商 HTTP，打开 LiveGate，部署可付费外呼，宽松网络策略，修改官方主渠道，G4/G5/G6。

---

## 3. 威胁模型和进程所有权（在编码前画清楚）

### 3.1 组件与信任等级

| 组件 | 角色 | 信任级别及限制 |
|---|---|---|
| Student / Teacher prompt / Tool Result | 可导致模型请求内容变化 | **不可信数据**；不能签发预算或 Route |
| DSH Runtime / Plugin Adapter | 抽取真实请求并转发给 Controller | **不作为授权根**；无 Key、无直接外网、无 DB 写入凭据 |
| Launcher | 固定启动受限容器/进程与可信控制面 | **可信**：冻结代码、目录、env、FD 连接和 Policy |
| Trusted Controller | 校验、规范化、生成 `PreparedProviderRequest`/`call_id`，协调状态机 | **可信控制面**；不得由 DSH 自行启动/替换并赋予权威 |
| Broker/Ledger | 真实持久 Reserve/Claim/Settlement 记录 | **唯一账本权威**；候选进程不可修改 DB 文件 |
| Trusted Egress | 只能凭一次性已持久 Claim 发送已批准负载 | **发送权限所在边界**，G3-B 仅连接 Fake |
| Fake Provider | 受信/可脚本化的模拟响应、原始字节收据 | **合成证据**，不声称真实外网费率/Usage |
| Reviewer | 独立执行和反向核查 | 不信任 Owner 的 PASS 文本 |

### 3.2 所有权约束

**重要**：G3-A 中 DSH 插件自己 `spawn(fake_provider.py)` 的机制，证明了 stdio 可行，**不证明**子进程可信。G3-B 的可信 Controller 不能仅因为同样是 Python 子进程就被称为可信。

首选实现：由可信 Launcher 在候选启动前创建 Controller/Broker 所属进程及其 IPC 端点（例如父进程持有的 pipe/受限 FD），再把**只允许提交模型请求**的受控连接传给 DSH Adapter。DSH 不能指定另一个 Controller 可执行文件、DB 路径、Policy、Key 路径或环境变量；不允许 shell 动态命令。Linux namespace/不同 uid、只读挂载与 socket/FD 权限需由运行证据证明，不能凭架构图自证。

如果受现有 rootfs/Podman 机制限制，G3-B 暂时只能在同一个沙盒内做 Controller+DSH **结构性闭环**，则允许该子任务报告 `PASS_FOR_IN_PROCESS_INTEGRATION_ONLY`，但本 Gate 的**可信边界类测试必须标 `BLOCKED/UNVERIFIED`**，不得在报告中写“DSH 无法绕过控制面已经通过”。可以将 OS 分离留待 G3-D，但需给出可执行迁移方案和阻断项。

### 3.3 数据流的精确定义

```text
真正的 DSH SDK / Session / Tool Registry
        │  每次 LlmAdapter.stream(options)；含 tool 后第二次调用
        ▼
DSH Adapter (untrusted, no Key, no network, request-only IPC)
        │ request payload + correlation id；不能提供权威 claim/usage
        ▼
Trusted Controller (external/launcher-owned)
        │ validate + immutable Prepared + canonical bytes
        │ derive call_id / request_digest；verify Tool Registry
        ├──► SQLite Broker Reserve(call_id, scope, bounds, route/model)
        │         └── reservation_id + durable link
        ├──► Bound Claim(call_id, reservation_id, request_digest, expected route/model)
        │         └── one-use grant, durable Claim
        ├──► durable ATTEMPT_STARTED / INTENT (before send boundary)
        │         └── crash leaves conservative pending, no automatic retry
        ├──► TrustedEgressTransport(permission, immutable bytes)
        │         └── Fake Provider (separate process, raw byte receipt)
        │                  └── trusted synthetic observations/stream frames
        └──► Observation validate / ledger settle or conservatively hold
                  └── validated StreamChunk → DSH Session / SDK result
```

`LlmAdapter.stream(options)` 调用次数必须与 Controller 的模型 Attempt 日志相关联；`request/header` 仅用于上下文观测，**绝不能用来推导计费次数**。

---

## 4. B0：仓库现状、方案设计与版本冻结

### B0-01：代码盘点

优先实际阅读并记录：

- `spikes/g3a-provider-bridge/src/index.ts`：真实 `LlmAdapter.stream` 接口、`GenerateOptions` 读取、Chunk 归一、子进程管理、`AbortSignal`、日志。
- `spikes/g3a-provider-bridge/fake/fake_provider.py`：原始字节收据、错误脚本与合成 Usage。
- `spikes/g3a-provider-bridge/run/suite.py`、`run/worker.py`：真实 SDK、Session 和 Tool 的最小可运行命令。
- `src/autoteacher_m0/accounting/call_identity.py`：唯一 canonical 编码、Unicode、`run_id` 校验。
- `src/autoteacher_m0/accounting/{broker,ledger}.py`：Reserve、Claim、Settlement、事务、schema、锁/重放。
- `src/autoteacher_m0/security/egress.py`：`PreparedProviderRequest`、`BoundBrokerClaimer`、`DispatchPermission`、`TrustedEgressTransport`。
- `src/autoteacher_m0/accounting/observation.py`：`ProviderObservation`、Completeness、`deliver_observation()` 与保守费用。
- `plugins/runtime-budget-guard`、`plugins/skill-lookup`：Merged Profile 与实际注册表发现方式；不可将 `--dump-config` 当真实 Registry 的全部证明。
- `security/credential_boundary.py`、`security/docker_runner.py`、`security/watchdog.py`：仅用于限制与复用，不提前启用 Live。

输出 **API Reality Matrix**：`调用点 | 源码位置 | 当前返回/异常契约 | 是否已测 | G3-B 适配方案`。如果某接口不存在，先确认是否可在公开扩展上实现，不得假称存在；不允许私改 DSH 核心。

### B0-02：环境和审计基线

- 冻结 DSH `0.2.2-rc.2`（若实际版本不同，暂停说明原因）、Node、Python、运行依赖 SHA。
- 使用隔离的、已审的 Node+Python rootfs；真实项目代码只在隔离环境执行；`--network none`；`--unsetenv-all`，无 Key。
- 不在共享 rootfs 直接做可写 mount target；使用不可变只读基底 + 临时工作层 / `overlay` / 事先在冻结构建中创建挂载点。记录启动前后 SHA，不通过人工删除非空文件来“修复”证据。
- 读取 v0.4 的 E1–E5 准入要求，记录哪些属于 G3-B、哪些到 G4/G5 才能验证。

### B0-03：解决三个现有 Route 命名空间的真实冲突（重要）

当前各层**默认并不直接兼容**，务必现场核查：

- G3-A Adapter 注册 `g3a-bridge-test / bridge-v1`（只服务 G3-A Spike）。
- G2 离线 `BookkeepingBroker` 的 `_ROUTE` 仅接受 `offline-test-only` 或 `offline-test-only-*`，`_MODEL` 仅接受 `fixture-*`；不允许用真实供应商 Route 冒充 Synthetic。
- G2 `EgressPolicy` 的默认 allowlist 是 `opencode-go / deepseek-v4.1-flash`，默认 Host/Path 也面向 OpenCode Go，**不能直接用于 G3-B 的 Fake 发送**。

**推荐**为 G3-B 创建一套**独立 synthetic-only 固定 Route Policy**，例如 `offline-test-only-g3b / fixture-bridge-v1`，使用本地 Fake Transport 的受信目标标识，并让 DSH Adapter、Controller、Broker、Egress 全部在同一个 Approved Tuple 上达成一致。若公开 DSH 扩展必须保留独立的显示路由，请定义**显式、单射、获批准、在 Controller 复核的内部映射**，记录输入显示 Route 与真实预算 Route 的双重身份；禁止静默重写。

必须用 BIND-01 的 Reservation A/实际 B 负例验证两层都存在 allowlist 时仍拒绝；必须用 `--network none` 和实际禁网探测证明任何残余 `opencode.ai` 默认配置没有被调用。不要为过离线测试而修改未来官方主 Route 的全局默认值。

### B0-04：离线授权不是 DSH 自己签发

为 G3-B 设立由受信 Launcher 装配的**固定 Offline Run Admission**：Scope、`run_id`、允许的 synthetic Route/Model、`skill_lookup` Tool Schema Hash、Token/Call/Step 上限、期限/进程身份。候选 DSH 只能提交待审核请求，不能设置 `authorized=true`、选择预算 Scope、改授权文件或注入自己的 Controller 代码。

Guard 与 Bridge 组合时，**Broker 是唯一 Budget 记账权威**：要么 Guard 发起同一 Reservation 的受信请求并由 Controller 检查绑定，要么 Guard 做无副作用的预检而 Controller 执行唯一 Reserve；禁止两者各自为同一 Model Attempt 预留并分别扣账。必须用同一个 Tool Turn 的实际 Ledger 行数测试此性质。

F7 负例应有两个版本：（a）Guard 缺失但 Launcher 没有下发 Run Admission → 可信 Controller 拒绝，Fake 0；（b）Guard 缺失但 Launcher 有有效且范围固定的 Admission → 仍需逐次 Bound Claim，**不得将 Guard 存在本身作为唯一安全授权**。是否采取更严格的 Guard-must-present 策略由 Lead 显式选择，写入 Policy/测试，不临场猜测。

**B0 PASS**：真实文件、版本、命令可定位；三层 Route/Model 已通过显式 Synthetic Policy 统一；有一张可信进程/FD/DB 所有权图和 Offline Run Admission；已决定是否能够做独立 OS 进程隔离；无 Key 安全基线可复现。身份不明或容器没有锁定就 **BLOCKED**。

---

## 5. B1：最小 IPC v1（不要创造通用 RPC 框架）

### 5.1 选型与所有权

首选 `stdio`/受限 pipe，保证**DSH 端不能直接启动或替换可信 Controller**；消息从 Adapter 指向受信进程，返回规范化的响应帧。若采用 Unix Domain Socket，需证明候选 namespace 仅能连接该端点、无法操作文件系统及控制侧，且与既有“socket() denied”的安全政策兼容；不能因图省事开放候选任意网络。

**G3-A 已实测** Python stdio 的原始 JSON 行。G3-B 允许重用其帧解析与 chunk 正规化，但必须增加容量、版本、序号、未知状态以及信誉边界校验。

### 5.2 建议的最小协议（示意，提交前与实际代码约定对齐）

协议名示例：`at-m0/g3b-bridge/v1`。**这只是建议，不表示仓库已经有该接口。**

每个 Envelope 至少包含：

| 字段 | 要求 |
|---|---|
| `v` | 整数 1；拒绝 bool、未知版本 |
| `kind` | `request` / `ack` / `chunk` / `finish` / `error` / `cancel` / `receipt`（每类严格白名单） |
| `transport_id` | 当前 IPC 关联标识；只作路由，不作预算授权 |
| `seq` | 非负整数且严格递增；回放/乱序拒绝 |
| `payload` | 每类独立 Schema，未知字段拒绝，嵌套 JSON 严格检查 |
| `hash` | 需要时对精确定义的原始字节或 canonical payload 计算；说明对象/边界，不混用 |

Envelope 验证必须拒绝：重复 JSON Key、UTF-8 错误、NaN/Infinity、未知 kind、意外额外字段、bool/int 混淆、非法长度、控制字符、非法 Buffer、过深嵌套。输出到 DSH 的 Chunk 只能来自合法 Schema，不能让子进程直接提供任意 DSH 内部事件。

### 5.3 必须固定的资源界限

M0 建议初始默认（可在 B0 经 Lead 明确确定后调整；不得悄悄调高）：

| 限制 | 建议初值 | 为什么 |
|---|---:|---|
| 单个 IPC Request Frame | 256 KiB | 覆盖最小教学消息，不允许无限 prompt |
| 单个 Response Frame | 64 KiB | 防止一次 Chunk 占尽内存 |
| 单次请求总 IPC 字节数 | 1 MiB | 限制恶意/失控流输出 |
| 最大 JSON 递归深度 | 32 | 防深度嵌套 DoS |
| 最多 streaming chunk | 256 | 防无限流 |
| 最大 pending streams | 2（优先串行基准） | 首先证明正确性，之后测背压 |
| Controller request deadline | 30s（Fake） | 本地模拟足够，不用长超时掩盖挂死 |
| 单次 Fake Provider step | 10s（Fake） | 限制故障路径 |
| 清理 grace | 1s | 统一 Watchdog 语义 |

这些限制必须由**受信 Controller 和 IPC parser 强制**。只在候选 Adapter 检查算不上安全门槛；Frame 要先按字节数限制再尝试 JSON 解码，不允许因无换行而无限缓存。

### 5.4 Stream / Error / Cancel 语义

- `ack` 只说明受信端收到了一个请求，不等于预算获准、已发送或已计费。
- `chunk` 按 DSH `StreamChunk` 白名单序列输出，`usage`（若有）在 `finish` 之前；`finish` 正常只能一次；非法序号/重复 finish 拒绝。
- EOF、超时、进程异常、未知 Frame 在未进入发送前为 `PRE_DISPATCH_DENIED`；一旦存在已持久化尝试开始或未知是否开始，必须保守 `BILLABLE_UNKNOWN` / `SETTLEMENT_UNCERTAIN`。
- SDK 无明确单 Turn Cancel 方法时，可杀**本次 Run 独立 Worker**；必须保留 Session 和 Broker 的正确状态，且无自动重试。Adapter `AbortSignal` 的功能可分别测试，不把 SDK 级取消写 PASS。
- 收到 `cancel` 不等于 Provider 一定停止或免费；跨越发送边界后的取消必须按不确定费用处理。

**B1 PASS**：真实 DSH Adapter 可以将一个合规请求发给受信进程并收到合法 StreamChunk；伪造/超大/未知/截断帧在 Controller 侧 fail-closed；真实 DSH `echo` 行为不退化。可先用无 Broker 的协议测试，但不得由此声称 G3-B 完成。

---

## 6. B2：唯一 CallIdentity、Bound Claim 与保守账本闭环

这是 G3-B 的核心，要求单次真实 SDK 模型请求与持久 Broker **真的联动**。

### 6.1 请求规范化：不信任 DSH 给的摘要

1. 从真实 `GenerateOptions` 抽取消息、工具 Schema、Max Tokens、Provider/Model、Stream 等必要信息；**不信任其提供的 `call_id`、`reservation_id`、费用或审批状态**。
2. Trusted Controller 根据固定受信 Policy，构造 `PreparedProviderRequest`；字段须满足 G2 当前严格 Schema。`run_id/logical_step/attempt_index` 由可信执行上下文分配，不能让 DSH 任意选择共享 Scope 或重复已有 Step。
3. 使用 `accounting.call_identity` 里的**唯一 canonical 编码和 CallIdentity 生成器**；`prepared_request_digest` 与 `call_id` 的材料必须与已批准 Option A 一致，保持 Unicode、bool/int 和嵌套 JSON 一致性。
4. Controller 应从已冻结的真实 Tool Registry/已批准 Schema 快照中验证 `skill_lookup`；DSH 发送的 Tool Schema 只能作为待比对数据，不能作为允许清单的权威。
5. 将 Prepared 数据**深拷贝/不可变序列化**；任何消息/工具/Token 参数变动必须导致重新计算并拒绝旧授权。不要用不受信任对象引用在 Claim 后再生成新发送内容。

### 6.2 两类 Hash，严禁混淆

必须同时有：

- **`prepared_digest`**：`PreparedProviderRequest` 规范字段的 SHA-256；用于授权、`call_id` 和 Broker Claim；按既有 Contract 计算，不等于 HTTP/IPC Raw JSON 字节 Hash。
- **`payload_digest`**：可信 Controller 根据不可变 Prepared 构建**实际交给 Fake Provider 的发送负载字节**，对该字节序列计算的 SHA-256。Fake Provider 记录接收的**同一原始字节** Hash；Controller 在发出前绑定 `approved_payload_digest`。

**必须证明：** `controller.approved_payload_digest == trusted_egress.sent_payload_digest == fake_provider.received_payload_digest`，同时 `call_id → prepared_digest → reservation_id → bound_claim → attempt_id` 有完整链路。不同 JSON 包装（Envelope、Transport ID、元数据）不得混入“出站负载”的 Hash 除非文档事先明确其属于哪些字节。

G3-B 的 `payload_digest` 是**模拟 Provider 的传输字节**证明，**不是已证实真实 HTTP 服务端收到的 Wire Hash**。真实 HTTP TLS、自动注入字段、供应商重试、缓存/账单验证属于后续阶段。

### 6.3 Persist-before-dispatch：跨进程崩溃不得丢失“不确定调用”

G2-L1.1 的 `ATTEMPT_STARTED` 原本只是内存诊断；G3-B 必须将发送意图持久化。

建议最小状态：

| 状态 | 持久化位置 | 语义 |
|---|---|---|
| `RESERVED` | Broker SQLite | 已预留费用，未获得发送许可 |
| `CLAIMED` | Broker SQLite | 此 `call_id` 唯一 Claim 已占用；未证明发送 |
| `ATTEMPT_STARTED` / `DISPATCH_INTENT_DURABLE` | 同一可信持久 DB 或带 fsync 保证的独立 WAL | 准备进入一次可计费边界；重启不可自动重发 |
| `RESPONSE_OBSERVED` | 可信受信存储 | 已得到 Fake Provider 的响应/收据（可为空或部分） |
| `SETTLED` | Broker SQLite | 可信合成 Usage 完成结算 |
| `WORST_CASE_HELD` / `SETTLEMENT_UNCERTAIN` | Broker SQLite + Controller 记录 | 不确定结果保守持有；具体 DB 状态不能只以日志字符串表示 |

**顺序要求**：必须在调用 `TrustedEgressTransport` 或任何可能引起 Fake 发送的函数**之前**，提交并确认持久 `ATTEMPT_STARTED`（SQLite 事务提交 + `synchronous=FULL` 或等效方式），且只有持久记录成功才能继续执行。**不得先发后记**。Crash 后不得凭一次新的 Replay 自动再次发送；允许从已保存的收据进行幂等后续结算，但不得重新发起未确认 Attempt。

该状态既不能仅存在于进程内数组，也不能只写到可能丢失的 stdout。若新建表，应声明 additive schema v1 的迁移/回退、并发约束、唯一索引、Scope 及不破坏旧 Reservation 的原则。

### 6.4 Broker Reserve 与 Bound Claim

- 每次 DSH `stream()` 的模型尝试都先完成 Budget Reserve；无预算、`route/model` 不受批准、输入/输出 Token 上界不合法 → **Fake 调用 0 次**。
- Reserve 带或绑定 `call_id`；保留原 `reservation_id`；调用 `claim_dispatch_for_request` 与 `BoundBrokerClaimer.claim_bound(...)`；**不允许**生产路径调用 `claim_dispatch()` 或旧无 expected 字段路径。
- Broker 必须权威核对 Reservation `(route_id, model)`、`request_digest`、Scope、Claim 未使用状态；Route A/Model A vs 实际 B/Model B（即使二者均在 allowlist）必须拒绝。
- 一个 Reservation 只对应一个模型 Attempt；tool 结果要求新模型调用时应分配新 Step/Identity 与新 Reservation。
- 只有受信 Launcher 注入的 Offline Run Admission 能让 Controller 开始 Reserve；候选自称已授权或设置同名环境变量不能改变权限。
- Claim 成功以后不允许无限重试或复用 Permission，含进程重启、重新进入 `stream()`、并发 Consumer。
- 不要用 `reserve.dispatch_allowed` 等于 `claim granted`；两者状态必须分开。

### 6.5 可信 Observation 与账单映射

- Fake Provider 的 `usage` 在本 Gate 是**synthetic fixture**。可信 Controller 应从已核验 Fake Receipt/应答构造 `ProviderObservation`，保持 `cost_source=synthetic_fixture_cost` 或等价标识；**不能**用 `provider_invoice`。
- `AUTHORITATIVE` 仅表示**可信合成 Fake 结果**在此测试中完整、格式正确；不能解读为真实供应商账单权威。
- 必须验证 requested/observed route、model、请求关联、Cache/Reasoning 计数规则；若现有 `ProviderObservation` 源码不能提供所需验证，应由受信 Controller 完成并留下证据，不可无条件按“字段齐全”自动 SETTLED。
- Usage 缺失/部分/不合法或发送是否发生未知 → `WORST_CASE_HELD` / `SETTLEMENT_UNCERTAIN`，不填零，不释放预留预算，不触发自动 Retry。若部分结果的费用以估算上限记账，明确区别于 `PENDING` 的账本状态。
- 相同 `call_id` 同一 Observation 重放应幂等，冲突 Observation 拒绝且不能写坏已完成账本。
- DSH 可能收到显示用的合成 Token Usage；**显示值与 Ledger 权威状态必须由 Controller 决定/核对**，不能只信 DSH 发回的事件。

### 6.6 本阶段刻意简化的政策

- `max_retries=0`；禁 Provider SDK 隐式重试；无法证明禁用时直接标 `BLOCKED`。
- 不支持 image、file、store、compaction、judge 等辅助付费通路；任何此类请求必须拒绝，并审查真实 Tool Registry/实际运行路径是否仍有隐藏 Provider Call。
- 不用模型的 Token 输出内容触发新的敏感工具；本轮仅 `skill_lookup`，其内容来自固定、无敏感信息的离线 fixture。
- 不因“Fake 不收费”而跳过预算或允许任意重放：本轮目的是验证真实预算安全协议。

**B2 PASS**：实际 SQLite/stdio Broker 与真实 Controller 在一个真实 DSH Run 中形成 Reserve→Bound Claim→持久 Attempt→Fake Receipt→Observation→Settlement 的端到端 Trace；所有身份关联一致，金额保守，重启安全，Fake 调用只来自可信发送路径。

---

## 7. B3：真实 DSH / Tool / Session / Guard / 故障联合验收

### 7.1 不重新实现已有 G3-A 用例

复用 G3-A `echo/recall/tool/eof/error/cancel` Worker 和 suite（或移入适配后的 G3-B suite）；**关键变化**是所有 Fake 请求都必须经过 B2 控制链，不再从插件直接 `spawn(fake_provider)` 绕开 Broker。可以保留旧 Spike 源码作为回归/历史证据，但 G3-B Profile 只加载新的 Bridge，避免多路 Provider 同时可用。

### 7.2 Guard + Bridge 组合（两种独立机制）

- 首先实际加载 `runtime-budget-guard`，输出真实 Boot/Registry 证据，验证 Reserve / Settle/Fail Hook 的执行顺序和日志脱敏。不得把原生 Guard 15/15 当成组合通过。
- **F7 类负例必须做**：在无 Guard 或 Guard 装载失败的 Profile 下，DSH 仍可能尝试模型请求，但可信 Controller/Broker 在无有效授权时应拒绝，**Fake Provider 外呼 0 次**。不能仅因候选 Provider 被禁网就把无授权安全边界写成 PASS；应测试真正的受信 Claim 检查。
- Guard 和 Controller 均可能记预算：**明确单一预算权威为 Broker**；避免 Guard 预留一次、Controller 再预留一次产生双扣。Guard 只能发起/请求、不能自行把未获准请求视为允许。提交时说明两者分工和实际行为。
- 检查 merged DSH Profile、实际 Tool Registry；不允许 `shell` / 文件写入 / 任意执行工具和未授权 real provider。只有 `skill_lookup` 是允许的教学工具；Bridge Provider 是基础设施而非可供 Agent 调用的工具。

### 7.3 Session 与工具多次调用

工具轮真实事件应可重建：

```text
Session.turn Start
  DSH stream #1 → call_id A → reserve A → bound claim A → attempt A → Fake tool-call
  DSH tool/call(skill_lookup) → tool/result
  DSH stream #2 → call_id B → reserve B → bound claim B → attempt B → Fake final
Session.turn End
```

断言：A≠B；Reservation A≠B；两个 Claim 均只一次；Ledger 记录两次；一个 `request/header` 也不能导致第二次漏账；两个 Fake Receipt 分别对应两份不可变消息（第二份含真实 Tool Result）。

Session 跨进程恢复后，新请求形成合法的新 `call_id`；旧 Session 历史保留但不能自动重发上次 Pending 的请求。需要恢复上次结果时应通过持久状态和事件重放，而不是重试外呼。

### 7.4 崩溃/并发必须用真实边界而非进程内数组

建议用显式 Crash Hook（仅测试构建，默认禁用）在持久状态切换后触发 `os._exit` / SIGKILL：

- `after_reserve_before_claim`
- `after_claim_before_attempt_start`
- `after_attempt_start_before_fake_send`
- `after_fake_receive_before_response`
- `after_response_before_settlement`
- `after_settlement_before_sdk_finish`

每项由新 Controller/Broker 进程重新打开同一个 SQLite DB，检查状态、预算上界、重复 Claim/Send、Session 及清理。**Crash Hook 不能部署到未来可信 Live Profile**。

至少一个并发测试必须使用**两个真实进程**抢同一 `call_id`/Reservation，带同步栅栏；串行调用两个实例不能当作并发压力通过。Fake Provider 的原始 Received Counter 是判定重复外呼的证据。

### 7.5 IPC 资源与取消

- 发送没有换行的超大帧；必须在达到字节上限时拒绝，不得无限缓存。
- 慢 Fake、慢 DSH Consumer、重复 Chunk、坏 UTF-8、未知 `seq`、半个 JSON 后 EOF、Usage 在 Finish 之后 → 明确错误、保守账本、受控清理。
- 模拟 DSH Worker 被 SIGTERM、Controller 被 SIGKILL、Fake Provider 卡死、Broker 子进程异常；验证进程/容器最终不存在与 Reservation 不被自动复用。
- 如果不能在同一 Runtime 存活情况下取消单 Turn，则明确 `UNVERIFIED`；测试 Worker 级 Kill/Resume 的替代手段，而不新增私有 DSH Patch。

---

## 8. G3-B 强制验收矩阵（逐条出原始证据）

**状态只允许** `PASS` / `FAIL` / `BLOCKED` / `NOT_RUN` / `UNVERIFIED`；每项附测试文件、命令、实际退出码、UTC、Trace/DB/Receipt 路径、源码 SHA。下面预定义**目标**，绝不是当前已通过的结果。

| ID | 场景与注入点 | 必须观测/断言 | 严重度 |
|---|---|---|---|
| B0-01 | Git/DSH/SDK/Node/Python 实际冻结 | SHA、父子提交、无未知漂移，受限环境一致 | Gate |
| B0-02 | Candidate 直接读取 Controller Policy/DB | OS/挂载/权限实际拒绝；若仅同 uid 不可证明则 BLOCKED | 安全 Gate |
| B0-03 | 三层 Synthetic Route/Model 同一性 | DSH、Broker、Egress 显式固定同一允许 Tuple；不存在默认 OpenCode Go 通道 | P0 |
| B0-04 | 无可信 Launcher Offline Admission | Fake 0；候选不能通过字段/env 自行授权 | P0 |
| B1-01 | 真 DSH SDK echo 经 Controller IPC | 收到完整消息/工具/MaxTokens，返回正确 StreamChunk | P0 |
| B1-02 | 超长帧/无换行/非法 UTF-8/NaN/重复字段 | Controller 拒绝，内存有界，Fake 0 | P0 |
| B1-03 | 错误 `v/kind/seq/finish`、乱序 Chunk | 规范化拒绝，出错后不显示成功 Finish | P1 |
| B1-04 | Fake EOF / Error / Delay / Cancel | DSH 收到正确失败或中断状态；账本保守 | P1 |
| B2-01 | 完整单次调用 | Reserve=Claim=Attempt=Receipt=Observation=1；成功 Settlement=1 | P0 |
| B2-02 | Prepared 改 messages/tools/maxTokens | Claim 前后篡改拒绝，Fake 0 或既有 Attempt 不被二次发送 | P0 |
| B2-03 | Route A 预留 / Route B 发送（均 allowlist） | Ledger `ROUTE_MISMATCH`；Fake 0 | P0 |
| B2-04 | fake reservation、无 Claimer、Legacy Claimer | Bound Claim 不成立；Fake 0 | P0 |
| B2-05 | `call_id`/Unicode/长 run_id/请求摘要重放 | 统一规范校验，跨进程一致；非法拒绝 | P1 |
| B2-06 | Controller/Fake 出站字节哈希 | 三方 Hash 等值；Prepared Hash 单独正确 | P0 |
| B2-07 | 没有持久 Attempt 记录就尝试发送 | 发送被拒，Fake 0；不能仅内存判断 | P0 |
| B2-08 | 成功 Observation 与真实 Ledger settle | 合成 Usage 来源明确、费用/Scope/Route 一致 | P0 |
| B2-09 | Missing / Partial / Invalid Usage | Pending/hold，不把未知当零，不重试 | P0 |
| B2-10 | 相同 Observation 重放/冲突 | 相同幂等，冲突拒绝，账本不回退 | P1 |
| B3-01 | 真实 `skill_lookup` Tool Turn | 两次 `stream()` → 两条不同 Reservation/Claim/Attempt/Receipt/Settlement | P0 |
| B3-02 | 新进程 `resume_session` | 历史保留，新调用不会重发旧 Pending | P1 |
| B3-03 | Guard 正常装载 + Bridge | 实际 Guard Boot/Registry/允许工具，Broker 为唯一预算权威 | P0 |
| B3-04 | Guard 缺失/故障 + 无 Controller 授权 | DSH 尝试不代表放行，Fake 0 | P0 |
| B3-05 | 两个实际 Broker/Worker 竞争 | SQLite 原子保证最多一个 Fake Attempt/Claim，第二个确定拒绝 | P0 |
| B3-06 | Claim 后、Send 前 SIGKILL | 重启不重发，原 Reservation 保守 | P0 |
| B3-07 | Attempt 持久化后、Response 前 SIGKILL | 不重发，Pending/Unknown 保守，Fake 计数与账本可核对 | P0 |
| B3-08 | Response 后、Settlement 前 SIGKILL | 恢复时能幂等结算已持久收据；绝不再发送 | P1 |
| B3-09 | Tool 第二次模型调用无二次 `request/header` | 仍然有单独预算和 Claim；不能漏计 | P0 |
| B3-10 | 超时、取消、进程树清理 | 无孤儿/容器残留；取消传播正确，账本不失真 | P1 |
| B3-11 | 受限并发、背压与资源上界 | 不超帧/内存/进程限制；拒绝或排队行为确定 | P1 |
| B3-12 | 未批准 Tool/辅助调用/File/Image/Store | 发送前拒绝；无隐式 Provider 支路 | P0 |
| B4-01 | LiveGate/Adapter/run_live 不变 | 动态阻断与源码 Blob/SHA 证据 | Gate |
| B4-02 | 全量回归、Ruff、Node Guard/Skill Native | 记录实际 pass/fail/skip/blocked，原始命令，不能编造计数 | Gate |
| B4-03 | Review Packet 身份与原始 Trace | Packet 中源码与 Git Blob 一致，hashes 校验完整 | Gate |

### 8.1 通过等级与不可替代项

- **`PASS_FOR_G3B_NO_KEY_INTEGRATION_SCOPE`**：B1–B4 的功能/持久账本/失败关闭**强制 P0 项**全部在真实 DSH + 真实 Broker + 进程/持久测试下通过；允许明确保留未落地的真实 OS 隔离项为 `BLOCKED`，但状态必须写成“集成范围 PASS、OS 安全范围未通过”。
- **`PASS_FOR_G3B_TRUST_BOUNDARY_SCOPE`**：除了上述，还要有不同 OS 可信主体/真实文件和 IPC 权限拒绝证据，证明 DSH 无法独立操控 Broker 或发送；如果只是同进程 capability，禁止此裁定。
- **`FAIL`**：任何 P0 负例出现无授权 Fake 发送、重复发送、丢失保守账本、Route/Tool 绑定绕过、错误记为成功，则该 Gate 不通过。可以保留局部 PASS，但不能签总体 PASS。
- **`BLOCKED`**：固定环境/权限不支持复现时写清障碍、恢复条件、不可替代项；不准缩减用例后宣称全项成功。
- **`UNVERIFIED`**：真实 provider HTTP/usage/invoice/billing、单 Turn SDK Cancel（若仅 Worker Kill）、真 OS 安全边界尚未演示、远端 exactly-once；这些未验证项不自动妨碍无 Key 功能集成，但**严禁用于 Live 证明**。

### 8.2 负向测试的“零调用”证明标准

以下三层指标必须互相对照：

1. `controller.denied_attempts` / `claim_denied` 的明确事件；
2. Broker DB 里**没有成功 Claim 或没有新的 Attempt**（视注入阶段而定）；
3. Fake Provider **独立收据**中的实际收到请求数 = 0（若发生在 Claim 之后，需按对应阶段解释；不得仅查看 Controller 的自报计数）。

如果 Fake 已经收到一次而控制面报告 `NOT_DISPATCHED`，则直接 FAIL；若进程 Crash 导致最终是否收到不明，应报告 Unknown 并保守入账，不能假造一次或零次。

---

## 9. 可供实现 Agent 参考的最小状态转换与一致性规则

### 9.1 正常流程（伪代码，不代表现有 API 名称）

```python
# All Controller-side operations below are trusted; illustrative only.
async def handle_dsh_model_attempt(dsh_options, trusted_run_context):
    prepared = validate_and_freeze_prepare(dsh_options, trusted_run_context)
    call_id = derive_from_shared_call_identity(prepared)
    payload_bytes = encode_immutable_fake_provider_payload(prepared)
    approved_payload_digest = sha256(payload_bytes)

    reservation = broker.reserve_bound(call_id, prepared, budget_policy)
    claim = broker.claim_bound(
        call_id=call_id,
        reservation_id=reservation.id,
        request_digest=prepared.request_digest,
        expected_route_id=prepared.route_id,
        expected_model=prepared.model,
    )
    if not claim.granted:
        return fail_closed_without_sending(claim)

    # Durable commit must finish before any code that could send to Fake Provider.
    durable_attempt_start(call_id, reservation.id, approved_payload_digest)
    receipt = await trusted_egress.send_exact_bytes_once(claim, payload_bytes)
    persist_receipt_before_acknowledging_success(receipt)
    observation = trusted_normalize_synthetic_observation(receipt, prepared)
    settle_or_hold_conservatively(call_id, reservation.id, observation)
    return normalize_dsh_stream_frames(receipt)
```

正确实现应使**流式 Chunk 可以按到达顺序转发**；但在向 DSH 报告最终成功/`finish stop` 前，必须确认可信 Observation/Settlement 的承诺关系。若中途已经流出文字而最终账本失败，必须以 Error/Unknown 结束，不得“先成功后补账”。

### 9.2 保守状态矩阵

| 中断位置 | 已获得 Claim？ | Fake 可能收到？ | 重启后怎么办？ |
|---|---|---|---|
| Reserve 前 | 否 | 否 | 未扣费，可正常发起新操作 |
| Reserve 后 / Claim 前 | 否 | 否 | 保留 PENDING 或按可信无发送证据执行已批准的保守取消；不得直接假释放 |
| Claim 后 / 持久 Attempt 前 | 是 | 按设计不应收到 | 不自动重新使用该 Claim；保守 Pending，等待人工/可信 reconciliation |
| `ATTEMPT_STARTED` durable / Fake Send 前 | 是 | 可能尚未收到 | 默认 Unknown/Pending，**不能自动重发** |
| Fake 已收到 / 返回前 | 是 | 是或未知 | Unknown/Pending，账本持有；无 retry |
| 已收到可信 Fake Receipt / Settlement 前 | 是 | 已知 | 若 Receipt 已持久，可执行幂等结算；不能再发 Fake 请求 |
| 已 Settlement / SDK Finish 前 | 是 | 已知 | 不再产生调用；只处理输出事件/会话恢复 |

**解释**：该矩阵刻意保守，允许一些“其实没发送”的 Claim 继续占预算；这是 M0 为安全选择的代价。后续如果开发可靠 reconciliation，也必须基于受信持久证据，而不是 Actor 自述。

---

## 10. 最小环境/测试执行约定

1. 真实 DSH 版本、SDK、Node/Python、TypeScript 构建依赖必须现场读取锁定文件，记录哈希；禁止把新源码挂到未经冻结的宿主运行时。
2. 运行时容器禁网、无 Key、无 host secret mount；readonly rootfs、non-root、no-new-privileges、cap-drop ALL、资源限制；写入仅 `/work` 等受限目录。若需要 Docker/Podman 的多容器 Pipe，请用受信 Launcher 连接，不可把宿主 Podman/Docker Socket 挂给 DSH。
3. Broker SQLite DB 和 Controller Policy 只能由可信一侧读写。若同 uid 同目录不能验证这一点，明确标记 OS 信任边界 `UNVERIFIED`。
4. Trace 使用 synthetic 内容、nonce、hash、token counts；若意外出现真实凭据，停止并隔离证据，按安全处理流程执行；不把敏感值写入报告/包。
5. 日志必须记录单次真实执行：UTC 起止、argv/env **键名**、exit code、镜像/hash、源 Tree SHA、唯一 run-id、Session ID、call_id、reservation_id、claim ID、attempt_id、`prepared_digest`、`payload_digest`、Fake Receipt ID、Observation Status、Ledger Snapshot。
6. 不允许单纯通过 `isolation: true` 字段证明安全；要实际探测无网络、无宿主秘密、无候选 DB 写权。测试专用恶意数据使用**假 Key**、假 Tool、不访问真实账户。
7. 原生 Node Guard、Skill、Bridge build、真实 DSH SDK suite 与 Python `pytest tests/` 分别跑；不将某一层的通过覆盖另一层。Skill 0.2.2 原生 harness 的既有兼容限制单独列 `BLOCKED`，不能借 0.2.1 测试直接标 0.2.2 Native PASS。

---

## 11. 明确的 STOP / ESCALATION 条件

任何一项出现，Lead 应立即暂停相关工作包，保留失败证据并标记 `BLOCKED/FAIL`，**不得为了交付绕过或悄悄禁用该测试**：

- DSH 未经 Reserve/Bound Claim 成功触发一次 Fake Provider 调用；或者旧 v1 Unbound 路径能拿到正式发送 Permission。
- 同一 `call_id` 两次 Fake Send、相同 Reservation 两次可计费 Attempt、重复/冲突 Observation 导致双结算或低估。
- `request/header` 的次数被错误用于计费，导致 Tool Roundtrip 第二次模型调用漏记。
- `ATTEMPT_STARTED` 在发送前未持久化或崩溃重启后自动重发不确定请求。
- Claim 前后消息/工具/Route/Model/Output 上限可以变更而仍发送未批准的负载。
- Controller 的 Broker DB/Policy 可被候选 DSH 进程写入，而报告仍称“强信任边界 PASS”。
- 任何真实 Key、供应商外部 HTTP、未批准 Shell/容器 Socket、可付费 Provider 被意外启用。
- 合并 Profile 启用 `llm-deepseek` 或其他真实付费 Route；无法确认真实可用工具注册表；`LiveGate` 被改动或解锁。
- 不确定 Usage 被当 0、错误标成成功、取消被吞掉导致进程存活或费用被错误释放。
- 无法证明测试操作属于指定冻结代码、源码与 Packet Blob 不一致、环境漂移未被解释。

出现严重 P0 时：**保留 Crash/Trace/DB，不要抹掉失败记录；提交单独 Findings 和最小复现，等待维护者决定修复还是换 Runtime**。若无 Key G3-B 方案必须依赖修改 DSH 内部私有 API、无法关闭隐式模型分支，则先提交 `TECHNICAL_BLOCKER_ADR.md`，而不是无限打补丁。

---

## 12. 交付目录与 Review Packet（严格，但避免无意义重复）

### 12.1 Git 提交规则

建议分成：

- Commit A：`G3B-B0/B1`（协议、Adapter、最小 Controller；无真实网络）。
- Commit B：`G3B-B2`（Bound Broker + Attempt 持久化 + Observation）。
- Commit C：`G3B-B3`（真实 DSH SDK 用例、注入与并发测试）。
- Commit D：`G3B-DOCS`（报告、证据索引、Review Request，**不改代码**）。

不强制恰好四个 Commit，但必须记录**实际 Base/Implementation/Docs SHA**，且 Docs-only 勘误不能悄悄改源代码或历史证据。G3-A 的历史 Packet 不重写，未来 Reviewer 可以通过 `git diff base..impl` 审计本轮新逻辑。

### 12.2 必须生成的文档

1. `docs/M0_G3B_BASELINE.md`：现场 SHA / ABI/版本/目录/环境/OS 所有权及 G3-A 差距。
2. `docs/M0_G3B_IPC_PROTOCOL.md`：协议 Schema、长度、时间、流序、取消、错误、哈希对象、版本与兼容性。
3. `docs/M0_G3B_SECURITY_AND_ACCOUNTING_CONTRACT.md`：CallIdentity、Reservation、Claim、Attempt、Wire Binding、Observation、Ledger、失败状态与 Authority 来源。
4. `docs/M0_G3B_IMPLEMENTATION_REPORT.md`：具体实现、测试、证据、残余与未运行项。
5. `docs/M0_G3B_REVIEW_REQUEST.md`：对独立 Reviewer 的问题、身份、最小重跑指令和 STOP 决策请求。

### 12.3 Packet 内容（推荐目录）

```text
artifacts/review-packet-g3b-<implementation-sha>/
  README.md
  manifest.json
  hashes.sha256
  diff.patch
  source/                 # 本轮有改动或核心安全路径的原始源码副本
  tests/                  # 重点用例 + 独立并发/崩溃注入
  protocols/              # B1/B2 冻结 Schema/状态机
  traces/
    success-one-call/
    success-tool-two-calls/
    denied-no-claim/
    denied-guard-missing/
    denied-mutated-request/
    crash-claimed/
    crash-after-attempt-start/
    crash-after-receipt/
    concurrent-claim/
    usage-missing/
  ledger/                 # 脱敏 SQLite 快照或可复建记录 + PRAGMA/状态查询
  logs/
    build.*  sdk.*  node.*  pytest.*  ruff.*  negatives.*
    commands.jsonl        # 每条命令的真实 argv/UTC/exit/环境身份
  env/
    code-tree.txt
    runtime-hashes.txt
    image-and-deps.txt
    isolation-probes.txt
    container-absence.txt
  evidence-matrix.csv
  security-nonclaims.md
  reviewer-reproduction.md
  packet-integrity-report.txt
```

文件名可根据真实项目布局调整，但**内容不能缺**。`manifest` 至少写 `base_sha`、`implementation_sha`、`docs_sha`、`runtime_version`、`sdk_version`、`node_version`、`python_version`、`image_or_rootfs_sha`、`deps_sha`、`stage_sha`、`tests_executed`、`blocked_cases`、`real_model_calls=0`、`external_http_calls=0`、`key_present=false`、`date_utc`。

- `diff.patch` 必须与冻结 Base→Impl `git diff` 字节一致（保留 `--binary`）。
- `source/`、`tests/` 必须能与 Impl Git Blob 对应；目录 Hash 的归一化模式、mtime、所有权事前定义，不在事后修数。
- 原始 Trace 不得由报告摘抄“重新生成”。日志中理论 Request Count 必须与 Fake Receipt 实际数量交叉匹配。
- 修改或勘误历史 evidence 时**append-only**，新 Manifest 明确声明新旧版本和当前权威文件；不要出现“报告称有 tar 但 tar 未交付”。
- 别把“Guard 原生 15/15”当作“Guard+Bridge 组合通过”。
- 若 SQLite 原始 DB 含敏感会话字段，保留隔离环境中原始 DB Hash，Packet 用脱敏可重建快照与字段精确哈希；切勿把真实私有内容打包。

### 12.4 Handoff 标准格式

每个问题都有一个实际可定位行号、可执行的复现步骤和真实退出结果；建议 Report 章节顺序：

```text
0. TL;DR 与明确 Gate 裁定（不签 Live/GO）
1. Actual Git/Runtime/Container Identity（源于现场）
2. Security Trust Boundary / 可信组件所有权
3. Architecture Diff（G3-A 复用 / G3-B 新增）
4. Frozen IPC Protocol & State Machine
5. Real DSH SDK → Broker → Fake → Ledger Positive Trace
6. Guard/Tool/Session Combined Trace
7. Negative / Crash / Concurrency Matrix（逐 ID）
8. Actual Test Commands & Results（不可预填）
9. Cost/Usage/Observation Conservative Semantics
10. Source Diff & Compatibility / v1 Residual
11. Blocked/Unverified & G3-C/G3-D/G4 Dependency
12. STOP + Requested Reviewer Verdict
```

---

## 13. 独立 Reviewer 应该怎样审（请与实现者分开）

**独立 Reviewer 的工作不是给 Owner 报告盖章，而是尝试证伪核心性质。** 不要求重做所有历史审计；重点重跑本轮新增的受控发送链路。

### R0 — 身份复核

- 独立 `git rev-parse`、`git diff --check`、`git diff --binary base impl` 对比 Packet；审查代码新增/变动文件（尤其 Adapter 的发请求入口、Controller、SQLite Broker、Attempt WAL、Observation、Watchdog）。
- 确认真实 DSH `0.2.2-rc.2` 二进制/构建输出/插件 Blob 与 Manifest 对齐；不被本轮临时 Node 模块替换。
- 复验没有真实 Key/HTTP，LiveGate/Adapter/run_live 与批准的既有冻结值一致。

### R1 — 追踪所有可能发送的入口

以 Fake Provider 的实际函数/IPC Receive 为起点**反向追踪**：每条到达路线是否必须经过 Bound Claim + Durable Attempt？检查旧 `claim_dispatch`、`require_claim`、`authorize` / Descriptor-only、G3-A 直 spawn Fake、默认 Real Provider、Compaction/Judge、Retry/Cache/Files 是否可能绕开新管道。

### R2 — 独立恶意探针（至少六类，不直接复用 Owner 测试结论）

1. **Tool 两次调用但只有一个 `request/header`**：Reviewer 亲自核对 2× Reserve/Claim/Attempt/Fake Receipt。
2. **Claim 后 Prepared Payload 篡改**：额外 Tool、Prompt、Route 或 MaxTokens 变化；0 未批准发送。
3. **重复/崩溃 Claim**：两个真实进程（同步栅栏），最多一次 Fake 收据。
4. **Crash after attempt-start**：新进程恢复不得自动重发，仍保守账本。
5. **Guard 缺失/未加载**：无外部授权时 Fake 收据 0，且真实 DSH 仍有尝试证据。
6. **缺失 Usage/非法 Chunk/EOF/Cancel**：不会出现零成本假结算或成功 Finish。

建议增加 Unicode、长 `run_id`、相同 `call_id` 不同 payload、异常后重复 Observation 和未批准 Tool Registry 的定向独立 Probe。

### R3 — OS 边界（不要按结构图投票）

独立运行候选进程的 Fake Attack：打开 Broker DB 路径、篡改 Policy 文件、尝试对 Controller 控制 FD/可执行路径执行未授权写入、发出未经核验的 Claim、打开直接网络 Socket。只有**实际操作系统阻止**才可得 `TRUST_BOUNDARY_PASS`。如无法实现不同 UID/namespace，必须 `BLOCKED`，可以与功能性集成 PASS 并存。

### R4 — 数据/财务交叉核对

Reviewer 查询 SQLite 实际行：一条 `call_id` 是否可映射 Reservation/Claim/Attempt/Observation/费用；Tool 两条是否分开；Pending 是否保守计入；已 Settlement 的重放不会新发请求。核对 Fake 原始 Receipt 字节与 `approved_payload_digest`，指出每个 Hash 到底覆盖什么。

### R5 — 复跑与裁定

- 在独立冻结 stage 运行重点真实 DSH SDK Case、G2 核心、Python 全量、Node Guard/Skill/Bridge、至少一组真实 Crash/并发用例。
- 用 `PASS_FOR_G3B_NO_KEY_INTEGRATION_SCOPE`、`PASS_FOR_G3B_TRUST_BOUNDARY_SCOPE`、`FAIL` 或 `BLOCKED` 对**不同范围**分别裁定，不能使用含糊的“全面 PASS”。
- 公开报告中不得包含任何密钥/敏感内容；报告重点放在可复验真实日志与必要的有限修改建议，不得无限扩大 E5/Live 审计。

**独立 Reviewer 必须在 G3-B 实现提交冻结后执行；实现者不能以自己负责的测试代替独立复验。**

---

## 14. G3-B 结束后的路线（仅依赖说明，不自动执行）

- **G3-C**：对真实 SDK/Tool/Session/Guard 的多轮联合验证做补强，包括特殊状态、长会话和真实 Registry；若 G3-B 的组合用例已经充分覆盖，可缩小或合并该 Gate，经 Lead 明确批准后再做。
- **G3-D**：补齐真正的不同 OS 主体、候选禁网/无 DB 权限、真实 Launcher/Watchdog 故障隔离、独立外部授权拒绝；这是可信外呼的关键前提。
- **G4 PreLive**：经维护者授权后执行外部签名公钥准入、Ed25519 验证、可执行 Controller/Key/Network Egress 部署、E5-P01–P05；**本轮未授权**。历史审计中可信公钥准入问题需在真正部署前完成验证和修复。
- **G5 Live**：严格按 v0.4 当前批准的**官方 DeepSeek V4.1 Flash** 主路由、审批、预算 `$3` soft / `$10` policy hard goal、最多 50 live attempts，在受限环境真实验证 E1/E2/E3；无足够的供应商额度/可信出口机制不能声称实际供应商账单硬上限。
- **G6 决策**：补齐 E4 模拟 20 例/Live 配对、E5-Full、独立评审后才 GO / CONDITIONAL GO / NO-GO；缺失强制证据时保持 `DECISION PENDING`。

历史强制验收基准：`Autonomous_Teacher_M0_v04.md`。本 Gate 成功不等于 M0 全部结束，也不等于 Autonomous Teacher 已具备实际教学能力。

---

## 15. 可直接复制给 Lead Agent 的执行指令

> **角色**：Autonomous Teacher M0 G3-B Lead/Integrator。  
> **任务**：执行仓库内 `docs/M0_G3B_TRUSTED_BRIDGE_EXECUTION_PLAN.md` 全部 G3-B 允许事项。  
> **基线**：先核实当前 HEAD、G2-L1.2 `53d7ba5`、G3-A `64b057b` 及关联 docs/源文件身份，不以旧报告的观察 HEAD 替代实际代码。  
> **必须阅读**：M0 v0.4 强制标准、G3-A Spike Report、G2-L1.2 Hardening Report、已批准 M0 Request Binding Contract、当前 G2 Accounting/Egress/Observation 源码、G3-A TS Adapter / Fake / 真实 SDK suite。  
> **执行顺序**：B0（冻结+API 盘点）→ B1（IPC v1）→ B2（Controller + Bound Broker + Durable Attempt + Fake + Observation）→ B3（真实 DSH Tool 两调用 / Guard / Crash / Replay / Concurrency）→ B4（全量测试+Packet）。  
> **硬约束**：0 Key、0 真实模型、0 外部 HTTP、禁网、候选不读/写可信 Budget DB、没有 Broker Claim 不发送、不调用旧 unbound 生产路径、不修改 DSH 核心或 LiveGate、未获批准不开展 G3-C/G3-D/G4/G5/G6。  
> **测试**：完成本文第 8 节各项并逐 ID 出证据，主要验证 Tool 两次独立模型调用、请求字节绑定、Persist-before-dispatch、崩溃保守账本、Guard 缺失、两个真实进程并发。  
> **验收**：区分功能集成 PASS 与 OS Trust Boundary PASS；任何未证实内容写 BLOCKED/UNVERIFIED；不得把本地 Fake 的 Hash/Usage 当作真实 Provider HTTP/发票/远端 exactly-once。  
> **交付**：`docs/M0_G3B_BASELINE.md`、`docs/M0_G3B_IPC_PROTOCOL.md`、`docs/M0_G3B_SECURITY_AND_ACCOUNTING_CONTRACT.md`、`docs/M0_G3B_IMPLEMENTATION_REPORT.md`、`docs/M0_G3B_REVIEW_REQUEST.md`、冻结 Commit、Review Packet 与独立可运行的原始 Trace。  
> **STOP**：G3-B 自测完成后立即停止，提交 Review Packet 给维护者和独立 Reviewer；未经维护者单独批准不进入后续 Gate，不启动 Live。

---

## 16. 给维护者的验收/发回修复决策表

| Reviewer 结果 | 维护者应做什么 |
|---|---|
| G3-B 核心单次闭环或 Tool 两次账本关联不通过 | **不接受 G3-B**；要求限范围 Bug Fix + Red/Green，不开展下一 Gate |
| 只在内存中记录 Attempt，SIGKILL 后重发 | **不接受 G3-B**；持久化是 P0 |
| 模拟 Fake 负例可绕过 Bound Claim/Tool/Route | **不接受 G3-B**；修复权限边界 |
| 功能性测试 PASS，但不同 OS 主体尚未实现 | 接受 `PASS_FOR_G3B_NO_KEY_INTEGRATION_SCOPE`，OS Trust Boundary 继续 BLOCKED；安排 G3-D，不解锁 Live |
| 功能和 OS 边界均真实 PASS，残余均为后续真实供应商相关 | 接受两个限定 PASS；**另行决定**是否授权 G3-C/G3-D，不自动执行 |
| Source/Hash/日志身份漂移 | 暂停归档，要求 append-only 勘误和独立复验，不改写历史记录 |
| 发现 DSH 必须修改私有核心才能完成协议 | 记录 NO-GO 风险，要求 Fallback 比较，而不是无限适配 |

**本轮唯一授权成果**：可以对 G3-B 的无 Key 集成与可信边界测试给出**限定范围**裁定。**本轮没有任何形式的 Live、真实付费请求或 M0 最终 GO 授权。**
