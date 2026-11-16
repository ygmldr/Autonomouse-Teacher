# Autonomous Teacher — M0 后续推进任务书（G2-L1.1 → G6）

> **用途**：可直接放入仓库交给 Lead Agent / Coding Agent 执行，并用作维护者及独立 Reviewer 的统一验收依据。  
> **编制日期**：2026-11-16。**文档性质**：实施建议与交接契约，不是任何测试的 PASS 证明，也不是 Live 授权。  
> **建议仓库路径**：`docs/M0_NEXT_EXECUTION_PLAYBOOK.md`。  
> **规范优先级**：`Autonomous_Teacher_M0_v04.md` 的强制 E1–E5/§10 > 经维护者明确批准的 ADR、Request Binding Contract 与安全政策 > 本任务书的实施安排 > 历史报告。若冲突，**停止、记录冲突、请维护者裁定**，不得自行降低强制门槛。  
> **唯一主目标**：以最少额外工程完成 DSH 框架选型所需证据；不在 M0 开发 M1 教学产品。

---

## 0. 给执行 Agent 的一页指令

### 0.1 当前已知基线（不是让你重做）

- 现有 G2-L1-FIX **实现提交**：`2786e25a9e5bd590255026d76fc362abb16d0e7b`；关联 docs 提交：`19f5270141a3a8cb59049df73755a27751ee29f1`；后续独立审阅文档曾归档于 `c52b173`。这些是用户已提供报告的身份，**实际仓库状态由 G0 现场核实**。
- 已报告的独立结论：`PASS_FOR_DECLARED_G2L1_SCOPE`，不是 G3、PreLive 或 Live 的 PASS。该轮全量据报告为 **601 passed, 1 skipped**；新任务必须用新冻结字节重新运行，不照抄该数字。
- 已有且需继承：`call-<48hex>` CallIdentity、`PreparedProviderRequest`、canonical request digest、Broker `claim` 增量 `expected_route_id/expected_model` 成对字段、真实 SQLite 原子 Claim、`DispatchPermission` 本地单次消费、descriptor-only 与 send admission 区分。
- 已明确的残余：真实 Provider 异常归因错误；`schema_version` 未强制；跨模块 Unicode canonical 一致性待修；descriptor 诊断会影响 attempt 计数；Broker 无效 completion 的 journal 容量边界待验证；旧 v1 unbound claim 仍可使用；生产 Bound Claimer/Provider Bridge 未接线；真实 wire 与批准 Prepared 是否一致尚未验证。
- `LiveGate` / `HarnessAdapter` / `run_live.sh` 维持硬阻断；尚无经过批准的真实 API 请求、真实 Usage/Invoice、生产 OS Egress/Key Broker。

### 0.2 当前允许你做的事情

**本轮自动执行范围：G0 → G2-L1.1 → G3-A/B/C/D 的无凭据实验。**

1. **G0**：冻结、核实输入代码/证据身份，做差异和依赖清单，不改变行为。
2. **G2-L1.1**：只修已定位的局部缺陷并补定向 RED/GREEN；最小兼容变更。
3. **G3-A**：确认 DSH 锁定版本可使用公开 Provider 扩展实现受控 Bridge，不猜上游 ABI。
4. **G3-B/C/D**：用真实 DSH Runtime + 真实 SDK/Session/工具 + 受控 IPC + 可信 Broker + 模拟 Provider 跑通完整请求、事件、失败和恢复。**无 Key、无真实供应商调用**。
5. **每个 Gate 均出 Review Packet 并 STOP**：由维护者/独立 Reviewer 明确准入下一 Gate。不要自动进入 G4（真实 PreLive 部署）、G5（Live）或 G6（最终决策）。

### 0.3 绝对禁止

- 不读取、导入、转发、打印或测试真实 Key/Token；不扫描用户 Home 中的凭据目录。
- 不直接改开 `LiveGate`、`run_live.sh`、`HarnessAdapter._require_live_authorization()`；不使用 `--live`/环境变量/Markdown/自签文件解锁。
- 不对真实 DeepSeek / OpenCode Go / OpenRouter 发请求；不自动变更主 Route/Model 或偷偷 fallback。
- 不给 Candidate DSH/候选插件提供真实外网、管理 Socket、宿主敏感挂载、可信账本写权限或 Key Proxy 权限。
- 不把本地 Claim 称为远端 exactly-once，也不把模拟 Usage 称为真实账单或真实硬限额。
- 不为了 PASS 修改、删减、skip/xfail 掩盖失败测试；不覆写既有冻结 manifest/历史审计结论。
- 不将开发/测试日志、授权内容、调用正文、原始密钥或潜在私有学习数据无审查地上传到公开位置。

### 0.4 本轮成功的定义

**G2-L1.1 已修复且有定向 RED/GREEN 证据；真实 DSH 能通过受控 Provider Bridge 在无 Key 下完成至少一个真实 SDK/Session/工具的模拟闭环；Provider 发包责任、claim 身份、Request Binding、异常与状态持久化均可从原始 Trace 核对；Guard 缺失时仍无未经许可的模拟发送。**

---

## 1. 文件与事实锚点

### 1.1 在仓库中优先阅读（名字仅供定位，以 `git ls-files` 为准）

| 类别 | 文件 | 用途 |
|---|---|---|
| 规范 | `Autonomous_Teacher_M0_v04.md` | E1–E5 / GO / NO-GO 唯一强制基准 |
| 旧实施手册 | `Autonomous_Teacher_M0_Execution_Validation_Review_Playbook_v0.6.md` | G0–G6 方法和 Review Packet 约定，优先复用已有内容 |
| 已批准契约 | `docs/M0_REQUEST_BINDING_CONTRACT.md`；`docs/ADR-002-unified-call-identity.md` | CallIdentity / Prepared / Broker Claim binding |
| 当前 G2 结果 | `docs/M0_G2L1_FIX_REPORT.md`、`docs/M0_G2L1_FINDINGS.md`、`docs/REVIEW_G2L1.md` | 已完成与新增问题；不要重做 A0–A3 |
| 生产源码 | `src/autoteacher_m0/security/egress.py` | Policy / Permission / Trusted Transport |
| 账本源码 | `src/autoteacher_m0/accounting/{ledger,broker,observation,call_identity}.py` | durable reserve/claim/settle/usage 与身份 |
| 授权与隔离 | `src/autoteacher_m0/security/{authorization,ed25519,watchdog,live_controller,credential_boundary}.py` | G4 安全审阅（G3 不自动解锁） |
| DSH 集成 | `src/autoteacher_m0/runtime/dsh_adapter.py`、`plugins/runtime-budget-guard/` | 当前 SDK Adapter、Cordis 预算 Guard |
| Profile | `docs/DSH_TARGET_PROFILE.md`、`config/dsh/target-*.patch.yml` | 已验证 synthetic profile / 目标 ABI |
| 证据 | `artifacts/reviewer-g2l1/`、G2 manifest | 仅作历史复核；新测试生成独立证据 |

**重要**：本次上传没有提供真实 DSH Synthetic Provider 的 TS 实现及全部 G2 测试；开始 G3 前必须从**当前仓库**定位并实际阅读 Provider 插件、SDK fixture、`skill_lookup` 注册代码以及锁定依赖。不许根据本文杜撰 API 方法名或路径。

### 1.2 Evidence 层级（用于每份报告）

- **A**：项目自己的 MockRuntime/纯 Python 模拟。验证业务契约，不证明真实 DSH。
- **B**：真实锁定 DSH Engine + 官方 SDK/JSON-RPC/Session + synthetic Provider；可以包含真正的 stdio Broker、真实 SQLite/受控 IPC 与本地 Fake Provider，但不证明真实云 Provider。
- **C**：真实、经人工授权的模型 API 调用及可信 Provider 观测/账单；只有 G5 以后才可能具备。
- **部署安全证据**另列：真实 OS 身份、只读挂载、可执行的网络出口/Key 隔离、独立 Watchdog、实际工具 Registry；设计与 Mock 不能代替。

### 1.3 状态词汇

`NOT RUN / BLOCKED / FAIL / PASS_FOR_DECLARED_OFFLINE_SCOPE / PASS_FOR_G3_NO_KEY_SCOPE / E5_PRELIVE_PASS / LIVE_PASS / DECISION PENDING / GO / CONDITIONAL GO / NO-GO`。不得将前一种状态直接提升成后一种。

---

## 2. Gate 路线图与人工停机点

```text
G0 当前仓库身份核实
  |
  v
G2-L1.1 局部修复（小 PR） --------> Lead 审核 + 独立复核 / STOP
  |
  v
G3-A DSH Provider Extension SPIKE ----> 技术选型 review / STOP
  |
  v
G3-B 可信 Controller <-> IPC <-> 模拟 Provider
  |
  v
G3-C 真实 DSH SDK + Guard + Tool + Session 端到端
  |
  v
G3-D 负向/崩溃/恢复/隔离测试 ---> 独立复核 / STOP
  |
  v
G4 PreLive 安全部署与人审（不是 Agent 自动执行）---> 人类授权 / STOP
  |
  v
G5 最小真实 DeepSeek 主渠道调用（需新的显式批准）--> 每组人工复核
  |
  v
G6 E4/E5-Full/冻结与框架 GO/NO-GO 决策
```

| 阶段 | 本文默认 Owner | Gate 完成标准 | 结束动作 |
|---|---|---|---|
| G0 | Lead / Verification | 实际 HEAD、代码身份和差异已核对 | 写 G0 基线，允许小补丁 |
| G2-L1.1 | Egress + Accounting Agent | 局部 P1 修复、定向测试/兼容回归均通过 | 冻结 SHA、Review Packet、**STOP** |
| G3-A | Runtime Agent | 公开 Provider API 与锁定版本兼容，路径选择有可运行 probe | Go/Stop 决议、**STOP** |
| G3-B | Runtime + Security | 独立 IPC 传输 + Broker bound claim + Fake Provider 一次闭环 | 提交 Trace、**STOP 可选** |
| G3-C | Runtime + Verification | 真实 DSH/SDK、stream/tool/session 串接；每次调用具备 request identity | 提交 B 层联调证据 |
| G3-D | Security + Verification | 负向故障/恢复/隔离通过，直连/Guard 缺失不绕过受控出站 | 独立复核、**STOP** |
| G4 | 维护者 + Security Reviewer | 独立 OS/Key/egress/watchdog 安全部署及 E5-PreLive PASS | **需维护者显式批准** |
| G5 | 维护者 + 受信 Controller | 主 Route 的 E1–E3 Live、Usage/费用证据 | 按批次人审，不自动扩大 |
| G6 | Lead + 独立 Reviewer | E4、E5-Full、所有 E1–E5 强制项和 ADR | 维护者最终签核 |

**允许并行**：G4 所需的文档和纯离线授权修复可以与 G3 并行，但不得使用凭据、部署授权或打开 Live。G3-A 的可行性判断应尽早完成，避免先投入大量新 Controller 代码。

---

## 3. 全程不变量与“立即停止”规则

### 3.1 强制不变量

- **I-01 预留**：无成功的真实、持久化 Reservation，不可进入 provider 调用入口。
- **I-02 声明 vs 权限**：PolicyEvaluation/`allowed=True` 不是发送许可；必须有 Broker Bound Claim + 单次消费 Permission。
- **I-03 可信身份**：`call_id` 来自可信运行上下文与完整 Prepared digest；不由候选文本自称。Egress/Accounting 对同一输入字节级一致。
- **I-04 请求一致**：实际传出的 method/host/path/route/model/messages/tools/system/response-format/token 上限/重试策略等必须与批准的 Prepared 请求有可审计绑定；仅校验 Route 不足。
- **I-05 本地至多一次准入**：相同 `call_id` 重放及跨进程竞争不能再发放第二个许可。**不宣称远端 exactly-once**。
- **I-06 失败保守**：进入 Provider 函数后的一切异常，至少视为“可能已计费”；不得报 `NOT_DISPATCHED` 或自动归零/退款/重试。
- **I-07 可靠记账**：未知/部分 Usage、结算不确定、账本失联时不能作为完整 PASS；预算仍被保守占用。
- **I-08 可信来源**：只有独立可信出口能提交权威 Observation；候选输出不能自己证明发票、实际 Route 或 Token。
- **I-09 隔离**：Candidate 无 Key/直连外网/宿主管理 Socket；Guard 缺失时独立出口仍应阻断未授权模拟或真实外呼。
- **I-10 批准身份**：代码、锁文件、Runtime/Plugin、实际 merged Profile、工具 Registry、路由或安全策略变动会使既有 Live 批准失效。
- **I-11 兼容**：旧 v1 接口保留只为历史离线/兼容；正式 Bridge **不得调用 legacy unbound claim**。
- **I-12 可复核**：每个 PASS 都能绑定 exact commit/artifact/命令/隔离配置/退出码/原始 trace；不是仅靠总结表格。

### 3.2 STOP 条件（任一发生立即停止并保留证据）

1. 未 Claim 或 Bound Claim 拒绝但实际 Provider 被调用。
2. 实际消息、工具 Schema、模型或请求身份与批准内容不符。
3. 相同 Call ID 在当前验证边界内得到两次实际发送许可。
4. 出现未记录、未受控的 Retry/二次 HTTP POST/Files 上传/其他内部辅助模型请求。
5. 模拟 Key/真实 Key 进入 Candidate 环境、输出、日志、日志上传插件或公开证据；真实 Key 一经接触立即停止。
6. Watchdog 不能终止超时运行或确认容器不存在；或 Controller/账本失效仍可继续启动外呼。
7. 需要修改 DSH 上游内部代码才能绕过公开接口限制，且没有维护者明确批准。
8. 任何无 Key Gate 触及真实 Provider 或产生任何真实计费调用。
9. 真实 Live 阶段超预算、超时、路由变化、授权过期、usage 不可信、账本无法确认费用。

STOP 后：标记 `BLOCKED` 或 `FAIL`，记录已知发送数量及最坏潜在费用、保留脱敏证据、撤销/隔离有关能力、由维护者决定是否恢复。不能改报告把问题消掉。

---

## 4. G0：核对实际仓库与冻结输入

### 4.1 执行前先看什么

- `git status --short`、`git rev-parse HEAD`、`git log -n 12 --oneline`、`git merge-base --is-ancestor 2786e25 HEAD`。
- `git diff --stat`、`git diff --check`、`git diff 2786e25..HEAD -- src tests config scripts plugins`。
- `git ls-files` 找到所有 G2 相关文件、DSH Provider/工具/Runtime 目标 Profile 与测试。
- 对 G2-L1 相关源码和 reviewer 结论逐一对应；如果实际 HEAD 已有补丁，先检查是否覆盖本文件问题，再决定不重复修改。
- 记录 `python`、Node、DSH Runtime、SDK、Cordis 插件、OCI rootfs、deps 锁定指纹；若无本地可验证的锁信息则标 UNVERIFIED。
- 审核已有测试名字和调用方式，禁止凭空引用不存在的测试脚本。

### 4.2 输出

`docs/M0_G0_CURRENT_BASELINE.md`，至少包括：

| 字段 | 要求 |
|---|---|
| observed HEAD / parent / dirty | 现场值，不沿用旧报告数字 |
| last G2-L1 implementation commit | 验证祖先关系；否则写原因 |
| all relevant paths | 当前仓库实际路径与 SHA |
| reviewed source | 当前证据充分处列出定位和行号 |
| already fixed / open | 一项项对照下一节 T1–T6 |
| toolchain / container | 可核指纹与缺失项 |
| constraints | no-key / no-network policy / 实际是否可运行 |

### 4.3 验收与停止

- PASS：能复原当前提交身份、列出待修问题、测试环境清楚、无未解释源码漂移。
- BLOCKED：缺失关键源码/真实 SDK 安装版本、无法确定冻结身份、发现安全门意外打开，或者已有分支冲突。
- 本 Gate **只记录**；不要在身份未清楚之前做修改。

---

## 5. G2-L1.1：最小补丁（不重新实现 G2）

### 5.1 工作包 T1 — Provider 异常的“可能已发送”归因（P1、强制）

**现有证据**：`egress.py` 的 `TrustedEgressTransport.dispatch` 中 `selected(request)` 抛异常会进入 `_denied()`；`provider_calls` 在成功返回后才增加，当前报告明确复现一次实际函数调用但归因为 `NOT_DISPATCHED`。位置为上次上传版本约 `:662–686`，以当前仓库行号为准。

**要求实施**：

1. 将结果分为 `PRE_DISPATCH_DENIED`（没有调用 Provider）与 `ATTEMPT_STARTED`（已经进入 Provider 函数；可能计费），另区分响应完成/部分/未知。
2. **在调用 Provider 之前**记录一次 attempt-start（至少在可信本地日志/状态中）；跨进程 crash 恢复不能把它当作未发生。若持久化机制当前不存在，G2-L1.1 先保证内存诊断不误报，并将持久化前置列为 G3 硬门槛。
3. Provider callable 抛异常（包括已执行后断连、无效返回结构、usage 解析失败）时，标为 `BILLABLE_UNKNOWN` / equivalent，保存 worst-case reservation，禁自动重试；不能重复消费原 Permission。
4. `provider_calls` / `dispatch_count` 命名与定义必须清楚：函数进入次数 ≠ 已证实的网络 HTTP Attempt 次数。错误信息只输出安全枚举/类型，不包含 Provider 原始敏感文本。
5. 取消、`KeyboardInterrupt`、controller 终止等特殊异常要保留中断语义和清理流程，不能被通用异常处理悄悄吞掉。

**定向测试**：

| ID | 输入 | 正确断言 |
|---|---|---|
| `L11-ATT-01` | 无 Permission、假 Permission | Provider function calls=0；`NOT_DISPATCHED` |
| `L11-ATT-02` | Claim 成功后 Provider 调用前拒绝 | Provider calls=0；不记可计费 attempt |
| `L11-ATT-03` | Provider 内部计数 +1 后抛 `RuntimeError` | call count=1；状态可能计费/held，**不是** `NOT_DISPATCHED` |
| `L11-ATT-04` | Provider 返回非 Mapping/无 Usage | 调用已发生；状态不确定、保守、无重试 |
| `L11-ATT-05` | 同 Permission 再次 Dispatch | 第二次 Provider calls=0 |
| `L11-ATT-06` | timeout/cancel/interrupt + cleanup | 资源清理，账本不保守退款，终止语义明确 |

**退出**：上述定向测试修复前 RED、修复后 GREEN；无新绕过；旧 G2 FIX-01..08 和 BIND-01..08 保持通过。

### 5.2 工作包 T2 — 统一 `call_id` Canonicalization（P1、强制）

**已见问题**：Egress 的 `canonical_json` 明确 `ensure_ascii=False`；先前上传 `observation.py` 中的 `CallIdentity.call_id` 通过默认 `json.dumps` 使用 `ensure_ascii=True`。`run_id` 允许非 ASCII，两个模块可能对同一身份给出不同 ID。当前仓库有 `accounting/call_identity.py`，开始修改前**必须先读该文件**，判断是否已经统一。

**目标**：单一实现负责 `canonical_json`、`derive_call_id`；其他模块 import，不各自计算。遵循已批准 `M0_REQUEST_BINDING_CONTRACT`：UTF-8、sort_keys、紧凑 separators、`ensure_ascii=False`、严格类型、拒绝 NaN/Inf、64-hex digest、`call-<48hex>`；不将 Reservation ID 纳入 call_id。

| ID | 测试 | PASS |
|---|---|---|
| `L11-ID-01` | ASCII run ID / same inputs | Egress 与 Accounting 输出完全一致；Broker 接受同一 ID 并成功关联 |
| `L11-ID-02` | 中文/非 ASCII run ID | 三方同一个 ID |
| `L11-ID-03` | 跨进程计算 | 字节级一致 |
| `L11-ID-04` | attempt、digest、step 单字段变化 | 产生不同 ID |
| `L11-ID-05` | bool 混入 step、NaN/Inf、非法 JSON | 规范拒绝 |
| `L11-ID-06` | 旧 v1 fixture/存量已绑定 call | 不静默改写历史 ID 或重用不兼容历史数据；需要显式迁移策略时 STOP |

### 5.3 工作包 T3 — Prepared Schema 与严格字段类型（P1、强制）

**已见问题**：`schema_version='m0.prepared.v0'` 可以在新 digest 重算后被旧实现接受；部分 Prepared 字段没有根据契约严格约束。

- 验证 `schema_version == 'm0.prepared.v1'`，拒绝未知版本，不自动兼容未来版本。
- 严格验证 Scope、Run、Step、Attempt、Provider、Route、Method、Host/Port、Path、`stream`、`max_output_tokens`、Tools、Messages、response-format、retry-policy；不允许 bool 被当作 int。
- `Prepared` 有 mutable nested Mapping 的风险：受信构造后应冻结或在发送前重新序列化/比较；不要仅依靠 frozen dataclass 的浅层不可变性。
- `approved_tool_schemas` 的输入策略、Tools schema 的实际批准来源必须显式；正式运行时不能默认为“空批准集合”后错误放行或忽略。
- 任何 schema/digest/mutation 拒绝都要在 Claimer **调用前**发生，且 provider calls=0。

| ID | 测试 | PASS |
|---|---|---|
| `L11-PREP-01` | v0/unknown schema version | 拒绝、claimer=0 |
| `L11-PREP-02` | `logical_step=True`, `port=True`, `stream=0` | 严格拒绝 |
| `L11-PREP-03` | 规范化消息或工具 schema 变化 | digest 不同，旧 Permission 不可用 |
| `L11-PREP-04` | nested mapping 创建后被修改 | 在发送前发现/拒绝或使用不可变快照 |
| `L11-PREP-05` | max tokens / method / path / host / model 变化 | claim 前拒绝 |

### 5.4 工作包 T4 — Journal 容量与完成操作（P2、最小修改）

**需先核实**：`broker.py` 的未知 reservation `settle/fail` 会产生 `UNKNOWN_RESERVATION`，若新 message ID 被 journaled，可能反复占用日志空间而不消耗 PENDING；并非费用绕过。先写 fail-first 测试，再决定修法。

- 保证已合法保留的 PENDING **在 reserve 配额满时仍能 settle/fail**。
- 无效 completion、未知 reservation、无效 usage 的日志增长必须有明确上界；不能因为 `max_messages` 导致无限追加。
- 保持重复消息 ID 响应幂等、不二次结算；如果改变否决响应的持久化语义，报告给出兼容性说明。
- Snapshot 在容量满时仍可读；不以阻断所有操作作为“修复”。

| ID | 测试 | PASS |
|---|---|---|
| `L11-JRN-01` | 大量 unique unknown-reservation completions | journal 条数受界 |
| `L11-JRN-02` | journal cap 下合法 PENDING settle/fail | 完成成功 |
| `L11-JRN-03` | 同 message ID 重放 | 响应一致、不二次扣账 |
| `L11-JRN-04` | 新 ID 重复已结算 reservation | 不无限创建 journal 行 |

若无法在不改旧 v1 协议的前提下兼顾上述性质，STOP 并提交 2 个最小方案给维护者，不得自行引入大规模迁移。

### 5.5 工作包 T5 — Descriptor 计数与快照归因（P2）

**已见问题**：`EgressBoundary.evaluate_descriptor()` 会记录 Policy 检查，通过时仍增加 `_streams[stream].attempts`，而 `_evaluate()` 依此判断 `max_attempts`。仅诊断多次可耗掉 Attempt 配额。

- `policy_checks`、`policy_allowed`、`claims_granted`、`dispatch_attempted`、`provider_invocations` 分离；发送上界以可信 claim/授权状态为准。
- 既有 `snapshot.attempts` 如有消费者，先统计消费者和兼容性；明确废弃/保留旧字段的只读含义。`attempts_detail` 仍为逐 Reservation/Call 的权威归因。
- 同一 logical stream 含多个 reservation 时，顶层首次 reservation 字段不可被当作唯一真实关联。

| ID | 测试 | PASS |
|---|---|---|
| `L11-DIAG-01` | 同一合法 descriptor 检查多次 | 不影响后续正式可发送次数 |
| `L11-DIAG-02` | 单次成功 Claim/Dispatch | 业务 attempt 计数恰 1 |
| `L11-DIAG-03` | 同 stream 两 reservation | per-attempt detail 归属正确，legacy 字段文档清楚 |

### 5.6 工作包 T6 — 兼容与源码级回归

必须复核：

- BIND-01 A→B（两个均在 allowlist）: `ROUTE_MISMATCH`，无 Claim、provider=0。
- BIND-06 replay、INT-05 双 Broker 并发、INT-06 SIGKILL 重启、INT-17 同 reservation 二次 Call。
- `claim_dispatch_for_request` 仍要求 `claim_bound`；旧不具备该方法 → 显式 `CLAIM_BINDING_UNSUPPORTED`。
- 老 `snapshot/reserve/settle/fail` v1 客户端保留；旧 unbound claim 只能作为历史兼容测试存在，不能进入正式 Bridge。
- `LiveGate` / Adapter / `run_live.sh` 原字节或行为保持 BLOCKED。
- `tests/` 全量、Ruff repo-wide、当前官方插件/SDK B 层定向回归（实际脚本必须从仓库发现）。

### 5.7 G2-L1.1 交付物与决策

**只交付一个小型功能 PR**，源码改动以目标问题最小范围为准；可另设 docs-only commit，但不能混淆测试实现身份。

1. `docs/M0_G2L11_FIX_REPORT.md`（逐 Finding：原行为、证据、修复、测试、残余）。
2. `artifacts/review-packet-g2l11-<sha>/`：`manifest.json`、真实 `diff.patch`、冻结源码、定向测试、完整 argv/UTC/exit、RED/GREEN 和最终回归日志。
3. 清晰的 `L11-ATT/ID/PREP/JRN/DIAG` PASS/FAIL/BLOCKED 矩阵；不能仅提供总通过数。
4. 新实现 SHA、父 SHA，兼容性及数据库迁移（若有）说明；来源文件及测试结果 SHA。
5. `docs/M0_G2L11_REVIEW_REQUEST.md`（Review Packet 模板见 §11）。

**进入 G3-A 条件**：全部 P1 问题修复通过；P2 有 PASS 或维护者批准的明确非阻断残余；没有新的安全旁路；独立 Reviewer 接受 G2-L1.1 scope。此时必须 STOP，等待维护者发起 G3-A。

---

## 6. G3-A：真实 DSH Provider Extension 的小范围可行性实验

**目标**：尽早回答“锁定版本 DSH 能否通过公开扩展接口把模型请求交给外部受控 Provider Bridge”，防止花大量时间再造 Orchestrator。

### 6.1 先阅读并记录公开 API，而非凭想象开发

1. 查当前仓库中 `offline-test-only-provider` 的 TS 源码、Cordis 插件入口、`llm/stream` Handler 与 `StreamChunk` schema。
2. 对应锁定 DSH Runtime/SDK 的真实依赖和 package exports；记录版本与字节哈希，不擅自升级或 monkey-patch。
3. 核对 tool-call、tool-result、reasoning、response-format、streaming finish、Usage、AbortSignal 的实际事件类型和顺序；没有证据的能力标 `UNVERIFIED`。
4. 判断是否可以只新增 **自定义 Provider 插件**，不修改 DSH 上游源码、不接触危险工具或私有插件接口。
5. 记录真实 SDK Session 的创建、跨进程恢复、失效处理方式；确认 Provider 接口与 Session SDK 层分开。
6. 检查目标 merged Profile 里 Guard 插件的加载顺序、失败行为及实际工具 Registry 检查手段（dump-config 不等于完整工具注册）。

### 6.2 候选路径与优先级

1. **优先：公开 TS/Cordis Provider Adapter** 将规范请求通过 stdio/受控 IPC 发给可信 Bridge。DSH 不持凭据，IPC 只暴露固定请求/事件 schema，不提供任意 URL/命令代理。
2. 若官方 SDK 已提供受支持的外部受控 Provider Transport，可用其公开方式；保留真实 SDK/Session，不在 Agent 侧重写调度循环。
3. 如果以上不可行，研究官方公开 Runner 或标准 JSON-RPC 可否低成本适配 `AgentRuntime` 接口。
4. **禁止自动走私有源码 patch / 任意 monkey-patch**。若该类修改不可避免，提交技术 NO-GO 候选与替代方案成本，交维护者裁定。

### 6.3 最小 SPIKE（应可被实际跑起来）

- **先做最短 ABI SPIKE**：真实 DSH SDK/Runtime + 已验证的 `offline-test-only-provider`，只测试能否将一个规范请求及流式事件经公开接口交给独立受控 IPC 端点并接回。此时仅使用现有离线 Guard/fixture 约束，不把它称为生产 Bound Broker 接线；不执行新的可计费发送。
- 外部 Fake Provider 返回固定文本及 Synthetic Usage，SDK 正常结束；只测试 **一个**完整请求，优先复用现有 Fixture Provider 代码。
- IPC 崩溃/EOF 时 SDK 得到显式失败，不自动切换真实 Provider。
- **Bound Broker、完整 Reservation/Claim/Permission 接线是 G3-B 的硬门槛**；G3-A 不能以缺少该接线为由先实现整个 G3-B。
- Guard 缺失情况下外部 Bridge 的 fail-closed 由 G3-D 正式验证；G3-A 先记录与旧现象一致的风险，不声称已关闭。
- 真实 DSH 启动/销毁过程的进程清理和 Trace 必须可审计。

### 6.4 G3-A Go/Stop

| 结果 | 决策 |
|---|---|
| 公开扩展点实测支持请求、事件与取消 | `G3A_PASS`，推进 G3-B |
| 部分事件不直接支持、存在公开可维护适配 | 记录最小补偿与测试，再审决定 |
| 只能靠大幅修改上游私有内部 | `G3A_BLOCKED/TECHNICAL_NO_GO_CANDIDATE`，不自动 Fork |
| 缺 SDK Runtime/插件源码/无法确认 ABI | `BLOCKED`，不把猜想写成 PASS |

**Gate 交付**：`docs/G3A_PROVIDER_API_SPIKE.md`、最小 TS 代码、真实 SDK/Engine 运行 log、API/export/schema 证据、成本/复杂度比较、Review Packet。**此处可以停机评估 DSH，不应等整个 G3 完成才知道框架是否能用。**

---

## 7. G3-B：可信 IPC 与请求/账本闭环（无 Key）

### 7.1 唯一推荐数据流

```text
DSH Engine / SDK / Session (candidate boundary; no Key, no direct network)
    |
    |  public Provider Adapter
    v
restricted IPC message (untrusted input)
    |
    v
Trusted Bridge / Controller (separate authority)
    |  parse/normalize request, freeze actual bytes/semantics
    |  recompute Prepared digest + call_id
    |  check approved route/model/tools/max tokens/retry policy
    v
SQLite/stdio Broker: reserve(call_id) --> reservation_id
    |
    v
Bound Broker claim(call_id, reservation_id, digest, expected route/model)
    |
    v
single-use permission -> Controlled Transport -> Fake Provider
    |
    v
trusted Observation -> Ledger settlement / Conservative pending
    |
    v
streamed response/events back to DSH
```

**关键细节**：外部 Controller 不得直接相信 Candidate 提供的 `Prepared`、`call_id` 或 `reservation_id`；必须自己构造或独立规范化，并按审批状态限制 Route/Tool 等字段。`Broker` 目前为 synthetic 固定路由账本，**不能通过切换配置把它包装成 Live 许可**。

### 7.2 IPC 最小协议建议

请求：`protocol`, `call_id`, `prepared_hash`, `approved_scope`, `route_id`, `model`, `payload`（实际消息/工具/系统/输出上限）、`request_type`, `deadline`, `trace_id`。响应：`protocol`, `call_id`, `event_seq`, `event_type`, `payload`, `final_status`, `usage_completeness`。此外建立取消/结束事件；大小、帧数、顺序、EOF 均有上限。

**注意**：具体字段必须以真实 DSH Provider API 为准，此处仅给最小业务语义，Agent 应提交契约草案，经 Lead 审阅后才能冻结。IPC 不应接受可执行代码、任意命令、任意文件路径、任意 URL/Host/Port 或未批准模型。

### 7.3 Byte-level / Semantic Wire Binding

- `PreparedProviderRequest` 覆盖所有可影响 Provider 行为、费用与权限的字段。`request_digest` 由可信端基于同一完整 payload 计算，不依赖 Candidate 自称摘要。
- Provider Adapter 的原始字段 -> Bridge 的规范字段映射要完整；若 SDK 私自增加 Headers/Files/Retry/辅助模型调用，则记录并拒绝未批准路径。
- Fake Provider 侧保存**可信传输实际收到的规范请求**（脱敏、限长），比对批准 Prepared 的字段及 digest；**不要只比 Route/Model**。
- 如果用 JSON wire，原始字节可能因空格/键顺序而不同：要区分“批准的 canonical semantics 与 wire 解析后一致”和“逐字节相同”，只有证据支持才主张 byte-identical。
- 发包前实现一次 request hash 和已批准字段核查，避免中间件在预留后修改 `maxTokens`/messages/tools。

### 7.4 Accounting 绑定与状态

- `call_id`、`reservation_id`、`request_digest`、`route/model`、`logical_step/attempt` 作为一次调用的审计键。
- Controller 必须真正使用 `BoundBrokerClaimer`/受支持的 stdio Broker 接口，不使用旧 `claim_dispatch()` unbound 路径。
- Claim 成功但未执行：仍占用许可和保守预算，不自动返还；控制器重启后的状态要能从 durable ledger/claim 恢复。
- 进入 Provider callable 前，将 `ATTEMPT_STARTED` 视为最早“可能已发送”的状态；Provider 返回/抛错后有相应结果，严禁用“未收到 Usage”判断未发送。
- `ProviderObservation` 的 `AUTHORITATIVE` 必须来自可信 Bridge；Synthetic Usage 仅标 `synthetic_fixture_cost`；`UNKNOWN` 保持 PENDING；不假装真实 Tokenizer/Invoice 已核实。
- 一个已批准的本地 Attempt 不保证真实远端一次计费；重试默认关闭，恢复不复发已 claim 许可。

### 7.5 G3-B 验收矩阵

| ID | 场景 | 必须证明 |
|---|---|---|
| `G3B-01` | 正常一次请求 | IPC→reserve→bound claim→fake provider→observation→ledger 全链有 trace；每项身份一致 |
| `G3B-02` | Broker 不可用 | Fake Provider calls=0、错误明确 |
| `G3B-03` | Scope/route/model 错误 | 0 claim 或 ledger route mismatch；0 provider |
| `G3B-04` | `max_tokens`/messages/tools 预留后改变 | 最终发送前拒绝，0 provider |
| `G3B-05` | 同 Call ID 并发/重放 | 本地至多一次已批准 Provider 入口，后续 duplicate deny |
| `G3B-06` | Claim 后 Bridge crash | durable claim/pending 保留，不自动发送/退款 |
| `G3B-07` | Provider 内部调用后异常 | 记录可能已发送，费用 conservatively held，无 retry |
| `G3B-08` | Fake Usage 缺失/部分/冲突 | 不按零结算，状态符合 observation 契约 |
| `G3B-09` | Unicode CallIdentity | 每层关联相同 |
| `G3B-10` | 外部 fake client 伪造 reserve/claim | 不能取得或重复使用可信发送许可 |
| `G3B-11` | IPC EOF/截断/乱序/超大帧 | 失败关闭、不会 hang/误发或泄露 |
| `G3B-12` | 已批准的单次重新启动 | 从真实 SQLite 同一 scope 恢复，禁止重复发包 |

**不要求**：真实外网、真实 Provider、真实账单、正式 Live 授权。若请求身份或费用模型无法映射，标 `G3_DEPENDENCY`，不伪造 PASS。

---

## 8. G3-C：真实 DSH SDK / Tool / Session 的联合验证

### 8.1 组合必须真实，不得混淆 A/B 层

必须实际运行锁定版本的 DSH Runtime、Python SDK、JSON-RPC/Session、公开 Provider 插件和 `skill_lookup`，而不是单独测试 Python Controller。Plugin `RBG_BOOT`、Reserve、Claim、Bridge、Tool 事件应在同一次运行 Trace 中可关联。

### 8.2 验收用例

| ID | 真实引擎场景 | PASS |
|---|---|---|
| `G3C-01` | 简单 text streaming | SDK 得到完整、顺序正确的 chunk；结尾明确；一次本地可计费 attempt |
| `G3C-02` | 严格 JSON 输出 | SDK 产出的 fixture JSON 能按 M0 schema 校验 |
| `G3C-03` | 模拟模型发出 `skill_lookup` tool-call | DSH 真正执行注册工具，返回工具结果，随后独立 reserve/claim 的下一个模型轮次 |
| `G3C-04` | 跨进程 Session 3/3 | 保存→退出→新进程恢复同一历史；不是默默新建 |
| `G3C-05` | 双 DSH_HOME 相同 Session ID | 不串历史；nonce 双向验证 |
| `G3C-06` | Stop/AbortSignal/SDK RPC 超时 | Bridge 收到取消或超时保护，资源/预算状态一致 |
| `G3C-07` | Provider 5xx/timeout/无 usage | SDK 明确错误，保守预算，无自动重试 |
| `G3C-08` | 禁止工具或额外 provider | 未批准工具不可调用；实际注册表与授权表一致 |
| `G3C-09` | Session-log/upload/compaction | 未批准自动上传/额外模型请求，或显式 BLOCKED；不假定固定 Profile 已全证 |
| `G3C-10` | 三次独立 Runtime 启动 | Plugin/Provider/Tool/Guard 顺序与身份一致，无未解释 loader warning |

### 8.3 工具 Registry 的真实证明

`dump-config` 只说明配置行。必须从真实运行时 registry（若公开 API 支持）或注册/拒绝事件给出实际可调用工具集合，并至少负测一个未授权工具不能被调用。若 API 无法完整枚举，则明确限制并给出外部 Tool Boundary 的拒绝证据；不能只凭配置 YAML 标记 P04 PASS。

### 8.4 失败处理

- 无法获取某个必需 SDK 事件时，不要编造 `RunRecord` 字段；填 `None` 或 `UNKNOWN` 并标出 M0 影响。
- 必须修改上游内部才能拿到 Session/Tool/Usage 时，提交 `DSH_PUBLIC_API_GAP`、替代设计和维护成本，让维护者决定是否停止。
- 不做自动跨渠道回退；不为了跑通一个用例而启用危险 Tool。

---

## 9. G3-D：独立边界与故障验证（仍无真实凭据）

### 9.1 最重要的 F7 负例

**Guard 插件完全缺失**：DSH Synthetic Provider 可被调用的事实已在 PR2 重现。G3 必须证明：只要没有可信 Controller/Broker 的批准，**实际受控出口/Fake Provider 调用仍为 0**。既然 Guard 不存在，不能指望 Guard 自己拒绝。

### 9.2 双隔离验证

- **Candidate 环境**：无 Key、无直接 Socket/公网、无可信账本写权限、无 Controller 管理 Socket、只读输入、非 root、cap drop 和外部 CPU/memory/PID 限制。
- **可信端**：可信 Broker/Controller 以独立 OS 权限/容器运行；只公开受限 IPC；若测试本地 HTTP Fake Provider，只允许可信端在受控隔离网络内连本地模拟服务，不开放公网。
- 单纯在 `--network none` 的 Candidate OCI 中执行 `socket()` 被拒绝只证明 Candidate 禁网；不等于外部出口已实现。必须分别展示两侧的网络/IPC/权限证据。
- 重启、EOF、Broker down、Controller down、超时、恶意流式消息都必须在受限资源内停止；不能把代理进程挂死当 PASS。

### 9.3 负向矩阵

| ID | 负向场景 | PASS |
|---|---|---|
| `G3D-01` | Guard 不加载（真实 DSH） | 未获可信 claim 的 Fake Provider calls=0 |
| `G3D-02` | Guard config hash 错误 | 0 未批准调用，清晰报错 |
| `G3D-03` | 未批准 route/model/path/method | 出口拒绝，不能 fallback |
| `G3D-04` | Candidate 直接连接外部 Socket/模拟 Controller 端口 | 无法绕过可信 IPC；OS 证据而非仅代码检查 |
| `G3D-05` | Candidate 读取假 Key、其他 Home、私有评估标签 | 全部不可读、不泄露 |
| `G3D-06` | 候选进程 crash/SIGKILL | Claim/Reservation 状态持久，第二次启动不重复发送 |
| `G3D-07` | Controller/watchdog 崩溃或中断 | 实际进程树与容器被清理，未完成外呼保守挂账 |
| `G3D-08` | 额外 tool/Provider/插件注入 | 实际 registry/外部政策阻止未批准能力 |
| `G3D-09` | 双 Broker/双 Bridge 并发 | 同 call_id 至多一个本地许可 |
| `G3D-10` | 额外 POST/隐藏 retry 尝试 | 外部出站计数能识别并阻断没有单独预算许可的 Attempt |

### 9.4 G3 最终评估

- **G3 PASS（仅无 Key/B 层）**：真正的 DSH SDK + 公开 Provider + IPC + Broker + Tool + Session 联合运行；G3B/G3C/G3D 必选用例通过或有维护者批准的、与强制安全无关的有界残余；独立 Reviewer 可重跑。
- **G3 BLOCKED**：公开扩展无法支持请求/事件、实际请求不受控、工具/Session 受损、未知重试绕过、不可信 Caller 能写账本或绕过出口。
- **技术性 NO-GO 候选**：确定存在不可接受且维护成本过高的公开接口缺口，须附最小复现与替代路线评估；不可仅因缺真实 Key 或预算审批认定技术 NO-GO。

### 9.5 G3 Review Packet

`docs/G3_PROVIDER_BRIDGE_REPORT.md` + `artifacts/review-packet-g3-<sha>/`，必须含：

- Provider 插件的完整相关 TS 源码/ABI 证据、SDK 调用层代码、可信 IPC 实现、Bound Broker 接线代码。
- 真实 DSH 引擎 / SDK / Profile / Tool Registry 的版本与 SHA；纯 Fake Provider 的明确声明。
- 一条成功 Trace：从 `SDK_RUN` 到 `RBG_RESERVE`、`BROKER_RESERVE`、`BOUND_CLAIM`、`PROVIDER_ATTEMPT_STARTED`、`FAKE_PROVIDER_RESPONSE`、`OBSERVATION`、`LEDGER_STATUS`、`SDK_END`，有统一 call_id/reservation_id 或稳定关联字段。
- 一条 Guard 缺失、一次 Provider 异常、一次 claim crash/replay 的原始负向 Trace。
- 每项测试的 exact argv/退出码/运行边界、预期/实际 Provider 函数调用计数、证据 hash；不包含任何凭据。
- DSH 公开接口是否足以支撑 M1 的结论、剩余适配维护成本与是否需要 Fork 的事实。

---

## 10. G4：PreLive（只由维护者授权部署，Coding Agent 不可自动执行）

G3 完成仍不等于安全的真实模型接入。G4 必须补齐以下强制项目：

### 10.1 可信 Controller 的安全根

- 授权签名、公钥注册与撤销文件必须在 Agent 无法修改的独立 OS 权限域；检查签名验真、版本和绑定 SHA。此前代码审阅指出的 **Ed25519 异常/小阶公钥准入**必须修复并独立测试；仅换一个验签库不代替异常公钥负测。
- 严格授权 JSON 类型，不把 `True`/float/字符串宽松转成整数；任何解析失败都拒绝，且不把敏感内容放入错误消息。
- 只读冻结 code、依赖锁、Runtime、plugins、merged Profile、tool registry、route policy、budget policy；建立撤销和过期机制。
- 当前 `TrustedLiveController` 仍是 inspect-only 恒 BLOCKED；G4 要设计和审阅新可信执行入口，不得靠注释/flag 直接删除硬阻断。

### 10.2 实际 Key 与 Egress/OS 边界

- 专用、可撤销、低额度凭据只能由可信 launcher/Key Broker 持有；Candidate Runtime、Provider 插件、日志、工具、Agent prompt 均不得持有。
- DSH 无网络直连和凭据旁路；唯一外部出口在独立权限环境中对每个请求检查授权、已持久预留、bound claim、请求模型、Token/费用、次数/时限。
- 验证真实 Proxy 的故障模式：拒绝自动直连 fallback；发现额外 `POST`/Files/compaction/judge 请求；取消/超时保持最坏费用与 STOP。
- M0 正式主渠道按 v0.4 的已批准 `primary_route`，默认官方 DeepSeek V4.1 Flash；**准确 route/model/endpoint/API 契约在执行 Live 前由维护者核实**。OpenCode Go 仅可选 INTERNAL-TEST-ONLY，不能替代正式验收，除非经正式变更主渠道并完整重验。
- 供应商侧硬预算、可信本地预算、账单实际费用是三个不同保证；不能把 `$10` 政策阈值自动说成供应商侧真实硬限额。

### 10.3 Watchdog 与 E5-PreLive

- 全进程树生命周期由外部 Watchdog 控制，且无论正常/异常都执行容器级清理并确认不存在；测试 Controller 自身异常和 Cleanup 失败。
- 按 v0.4 `E5-P01`–`E5-P05` 一条条给出**真实部署证据**：身份 SHA、代码变更后 Gate 默认关闭、人类授权不能被 Agent 自签/改 Markdown 绕过、真实 Tool Registry 白名单、Key/日志/环境隔离。
- 在 PreLive 未 PASS 前不得注入真实 Key 或开启 Live；如果某一测试必须依赖真实 Key 则先给出不接触真实 Key 的负向证明和维护者明确补充审批。

### 10.4 签核清单

维护者亲自审阅：

1. 代码 SHA、工具 Registry、依赖、构建产物、配置与权限边界确实是本次计划使用的字节。
2. 独立安全 Reviewer 给出 E5-PreLive 全项 PASS / BLOCKED 证据。
3. Key/Route/Budget/Deadline/MaxSteps/MaxAttempts/撤销能力均已在可信边界部署验证。
4. 实际来源于可信 Controller 的授权不会被 Candidate/Agent 改写；Runtime 修改会触发重新批准。
5. 明确批准**一次特定范围的 G5 Live 任务**，而不是授权 Agent 任意后续调用。

**文档上的 APPROVED、仓库内 JSON、`--live` flag 均不能代替独立受信授权机制。** G4 的实现、部署和真凭据操作不得包含在本轮自动 Agent 任务中。

---

## 11. G5：正式主渠道的最小 Live（需要单独的维护者明确批准）

前置：G3 PASS + G4 E5-PreLive PASS + 真实外部 Key/Egress/Watchdog 部署 + 有效的受信授权。否则全项 BLOCKED。

| 顺序 | 验证 | 主要 PASS 条件 |
|---|---|---|
| LIVE-00 | 无授权/无 Key 负测 | 真实可计费发送=0 |
| LIVE-01 | 最小文本 Smoke（3/3） | 正式获批主路由，回复、错误、request_id/usage 可信记录 |
| LIVE-02 | 结构化 JSON | 满足 v0.4 的 Pydantic schema |
| LIVE-03 | `skill_lookup` 真调用（至少 3/3） | 实际工具事件、注册、响应与输出可追溯 |
| LIVE-04 | Session 关闭/重开 3/3 | 同一真实上下文恢复，而非隐式新建 |
| LIVE-05 | 受信错误路径 | 无效凭据/429/5xx 仅在安全可触发时实测；否则注入并标 Synthetic |
| LIVE-06 | Usage、计费、限制 | 每次 Call/Reservation/Provider ID/版本/Usage/估算或账单来源能对上；unknown 保守 STOP |

- 模型固定单一，不做多模型竞赛/自动 fallback。
- 预算沿既有 `$3` 软 / `$10` 政策硬上限目标 / ≤50 Live calls；**只有供应商/可信出口真实强制并提供证据时才可宣称硬预算已证明**。
- 分批执行：Smoke 后先看日志与余额，再 Tool/Session；不在一次批准下无限推进。
- 未知真实计费、route/model 不符、额外尝试、watchdog 失控立即停止，不自动重发。
- 证据标 C 层，包含脱敏原始 SDK/Provider/账本事件和真实费用核对的来源分类。

---

## 12. G6：E4 + E5-Full + 冻结和 Runtime 最终决策

### 12.1 E4

- 继续使用现有 20 个 Mock 配对用例，不因有新硬件/模型重做测试目标。
- 在获批同一主模型/Route 上至少完成 **6 对** `teacher_v0` / `teacher_v1`，独立 run/session/candidate，固定案例、随机/交叉顺序、独立评估器/隐藏标签、评分错误显式暴露、逐次费用记录。
- Mock 评估器满分或 Teacher 自评不能视为教学效果证据；E4 证明的是实验机制可用，不是现实学生成绩提高。

### 12.2 E5-Full

严格按 v0.4 `E5-01…E5-09`：假 Key/其他 home/私有标签、网络访问失败、写入限制、资源压力、私有评估器权限、失败后恢复、真实 DSH merged profile/日志、修改审批字节后关 Gate、无危险 socket/mount/privileged 继承。特别检查实际 `ContainerRunner.run()` 端到端，而不仅是 rootfs OS probe。

### 12.3 决策

| 结论 | 规则 |
|---|---|
| `GO` | E1–E5 全部强制项在获批主 Route/部署配置上 PASS，独立审阅已复核 |
| `CONDITIONAL GO` | 所有强制安全/可靠性/评估已 PASS，仅剩已验证可补偿的非关键工程限制 |
| `NO-GO` | 有实证支持的不可接受且维护成本过高/无法修复的 DSH 关键技术限制 |
| `DECISION PENDING` | 强制项未运行或仍 BLOCKED；缺 Key/审批/网络不是技术 NO-GO |

最终 `ADR-001-runtime.md`、`M0_REPORT.md` **只追加新阶段证据与结论，不覆写旧冻结历史**。

---

## 13. 每个 Gate 必须怎样测试、留证据、保证能复验

### 13.1 执行环境

- G0 可做只读 Git/文件审计。G2/G3 项目 Python/TS/SDK/fixture 只能在维护者已审核的无凭据受限环境中执行；如果当前仓库的隔离 launcher 有不同名字，以实际经审查脚本为准。
- 始终记录 OCI image digest、rootfs/deps hash、运行 UID、网络策略、只读挂载、capabilities、cgroup、内存/CPU/PIDs、stderr/stdout、容器/子进程 absence。
- 不为了本地 HTTP Fake Provider 简单关闭 Candidate 的网络限制。应在可信侧的**单独**本地模拟网络环境验证出站行为。
- 分别记录单测、真实 SQLite/stdio、真实 DSH SDK、权限负测；不把不同测试子集的 PASS 数字相加。

### 13.2 基本测试清单（命令仅为示意，须在隔离环境执行）

```bash
# 这些是隔离容器内的命令示意，不可作为直接在宿主运行未审代码的指令。
python -m pytest tests/integration/g2_closure -q -p no:cacheprovider --tb=short
python -m pytest tests/integration/sandbox -q -p no:cacheprovider --tb=short
python -m pytest tests/unit/accounting tests/unit/security -q -p no:cacheprovider --tb=short
python -m pytest tests -q -p no:cacheprovider --tb=short
python -m ruff check --no-cache .
# DSH/Cordis/SDK/Provider 构建和运行请从项目锁定脚本发现真实命令，
# 不允许为了本报告填表而编造未运行的脚本或版本。
```

### 13.3 每个测试 case 的证据表

| 字段 | 内容 |
|---|---|
| `test_id` | 文档中的 ID（如 `L11-ATT-03`、`G3C-04`） |
| `scope/layer` | A / B / C / OS |
| `source_sha` | 实际执行的精确实现身份 |
| `argv / cwd / UTC / duration / exit` | 原始运行信息 |
| `preconditions` | 使用的 Profile/Route/Key 状态和容器策略 |
| `expected` | 调用数、拒绝点、Ledger 状态、输出事件 |
| `observed` | **真实**计数、日志片段定位、持久 DB 读数 |
| `status` | PASS / FAIL / BLOCKED / NOT RUN |
| `evidence_paths` | 原始 stdout/stderr/trace/hash/packet 位置 |
| `limits` | Synthetic/Wire/Invoice 未验证说明 |

### 13.4 每个 Gate 必须实现的 fail-first 验证

- 对修补型问题：先在精确基线跑新增用例 RED，再在改动 SHA 跑 GREEN；独立报告须能复验同样行为。若旧基线无法安全执行，报告注明并提供静态必现/可信的替代负测，不伪造 RED。
- 对新集成能力：先展示旧路径无法通过的诊断/缺口，再以一个最小 E2E 场景证明链路工作；不要用给所有函数打 Mock 后 `assert True` 冒充 B 层实测。
- 保留明确的 negative control，例如 Guard missing/Claim missing、route mismatch、Provider after-dispatch exception、重放、跨进程恢复。
- 每轮独立 Reviewer 应在新 stage/新数据库/不同进程执行关键负例，不复用 Owner 缓存或复验所需的未公开 Key。

---

## 14. Review Packet — 如何让维护者和 ChatGPT 真正审阅，而非只读摘要

### 14.1 标准交付目录

```text
artifacts/review-packet-<gate>-<impl-sha>/
  README.md                         # 范围/如何运行/未验证项
  manifest.json                     # SHA / commit / image / deps / timestamps
  hashes.sha256                     # 覆盖整个 Packet 非自引用文件
  diff.patch                        # git diff <base> <impl>
  source-file-list.txt              # 修改路径与 blob SHA
  source/                            # 关键被审代码，不含秘密
  tests/                             # 新增/迁移的定向测试
  protocols/                         # ADR、API 与 schema 变更
  traces/                            # 1 正常、>=3 必选负例、恢复/并发
  logs/                              # stdout/stderr/exit/完整 argv
  evidence-matrix.csv                # 每个 ID 对应日志及 PASS/FAIL/BLOCKED
  security-nonclaims.md              # 没有证明的事
  reviewer-reproduction.md           # 全部实际可复验命令和环境构建
  packet-integrity-report.txt         # 独立 checksum 校验结果
```

项目文件可以采用仓库现有的其他结构，但必须具有等价信息。不要附敏感凭据、供应商原始 Secret、私有评估标签或未经审查的用户内容。

### 14.2 `manifest.json` 最小字段

```json
{
  "schema": "m0.review-packet.v1",
  "gate": "G2-L1.1",
  "base_commit": "<actual 40hex>",
  "implementation_commit": "<actual 40hex>",
  "docs_commit": "<actual 40hex or null>",
  "working_tree_clean": true,
  "container_image_digest": "<observed or UNVERIFIED>",
  "dependencies_sha256": "<observed or UNVERIFIED>",
  "source_tree_hash": "<observed or UNVERIFIED>",
  "mode_normalization": "<exact staging chmod/mode procedure>",
  "executed_test_selection": "<exact command, not a test count>",
  "evidence_start_utc": "<actual>",
  "evidence_end_utc": "<actual>",
  "real_model_calls": 0,
  "real_external_http_calls": 0,
  "scope_claim": "PASS_FOR_DECLARED_OFFLINE_SCOPE or BLOCKED",
  "known_limitations": ["<real gaps>"]
}
```

示例中的 `<...>` 都是占位，不是可用于审计的真实值。任何无法核实的字段用 `UNVERIFIED`，不得虚构哈希、提交时间或网络计数。

### 14.3 实施者交接报告（应单独生成 `docs/<gate>_HANDOFF.md`）

```markdown
# M0 Gate <ID> — Implementation Handoff

## Objective / Scope / Non-goals
## Actual base, implementation and docs commits
## Files changed (with why, one line per file)
## Contract/API/schema migration and compatibility
## Findings (before → after; code line and test ID)
## PASS / FAIL / BLOCKED / NOT RUN by exact test ID
## Raw trace index and provider call count proof
## Security invariants / secret-scan / LiveGate status
## Independent reproducibility (commands, environment, hashes)
## Residual risks (P0/P1/P2; G3/G4/G5 dependency)
## Questions requiring maintainer decision
## Requested reviewer verdict (limited scope, no GO/Live request)
```

### 14.4 独立 Reviewer 执行顺序（不得直接相信 Owner PASS）

1. **身份**：确认 Git ancestor、base/impl/docs commit、完整 diff、文件来源、stage normalized content tree；不把 mode 差异误判为源码差异，也不忽略未解释差异。
2. **静态路径**：从唯一 Provider dispatch 入口**逆向**找到 Bound Claim、真实 Broker ledger、Approved Policy、Permission 单次消费、Provider callable、Observation 及异常处理。
3. **差异审阅**：逐 Finding 检查修改前旧语义、修改后新语义和负例；找未覆盖的旁路和旧入口。
4. **独立 RED/GREEN**：新 stage、全新 SQLite DB/独立 Broker 进程重跑关键用例，记录 argv/exit，不只看 Owner summary。
5. **并发/崩溃**：至少验证竞争 Claim、SIGKILL 后恢复、重复回执/重复发送、异常后保守账本。
6. **真实 Runtime**（G3）：用真实 DSH/SDK+Fake Provider 重跑 streaming/tool/session/Guard missing；检查源码确实通过公开接口。
7. **隔离/凭据**：核对运行容器/IPC/网络/Key 未接触及停机后的 absence；不运行真实 Live。
8. **审计证据**：检查 Packet 内 checksum 的完整性、raw log 与 Test Matrix 一一对应；记录任何不一致为 Evidence finding，不自动当成代码安全漏洞。
9. **发布 verdict**：`PASS_FOR_DECLARED_SCOPE / PASS_WITH_NONBLOCKING_FINDINGS / FAIL / BLOCKED`，分 P0/P1/P2 和必须修/可延期的不同范围。

### 14.5 独立审阅模板

```markdown
# Independent Review: <gate> (<exact SHA>)
## 1. Declared vs independently verified scope
## 2. Identity / provenance / hashes / environment
## 3. Source-level dispatch/settlement trace with line locations
## 4. Independently executed tests and raw logs
## 5. Findings (ID, severity, precondition, actual consequence, evidence)
## 6. Old-client compatibility and new Bridge path
## 7. Security and accounting invariant matrix
## 8. What has NOT been proven
## 9. Gate decision and precise next-step conditions
```

### 14.6 用户把什么上传给 ChatGPT 才最有用

**G2-L1.1 至少**：`docs/M0_G2L11_FIX_REPORT.md`、`diff.patch`、被修改的实际源码文件、5 组定向测试、`evidence-matrix.csv`、关键 RED/GREEN/全量日志、独立审阅报告。**G3 至少**：Provider Adapter TS、IPC/Controller/Bound Broker wiring、prepared canonical/schema、工具注册代码、三份端到端 Trace（成功、Guard 缺失、Provider 异常）与完整文件身份。

若上传限制只能选 3 类：**(1) 核心源码 Diff，(2) 最关键负例原始 Trace，(3) Reviewer 复核报告**。单独的“全部 PASS”总结不足以审计。

---

## 15. Lead Agent 每次派任务的管理规则

1. **单目的 PR**：G2-L1.1 的确定性补丁与 G3 新架构实验分开 commit/Review Packet，禁止一次把历史冻结、源码和 Live 改动混在一起。
2. **明确 Owner**：Accounting/Broker、Runtime/Provider、Security/IPC、Verification 分别负责；无独立 reviewer 时不能使用“独立复核”标签。
3. **冻结一组真实字节**：先 commit 实现、再对 exact commit 出 evidence、再单独 docs/errata；不得声称 post-freeze 新 HEAD 自动继承旧全量 PASS。
4. **有明确暂停点**：每一 Gate 的任务结束后 STOP；只有维护者批准新的 Gate 才继续；G4/G5 必须进一步走真实的人类授权。
5. **不追逐测试数量**：只增加针对具体 bug、权限不变量、端到端缺口的用例；不能因为总数增长就升级结论。
6. **不无意义扩大 M0**：不开发多模型路由、自博弈、RAG、教学规划或完整 RSI；这些是 M1 以后。
7. **评估工程成本**：任何修改迫使维护不可控 DSH Fork、无法测试的隐藏 Provider Wire 或新的可信执行入口风险都交维护者做 Stop/Go 判断。

---

## 16. 可直接复制给 Lead Agent 的总 Prompt

> **开始任务：Autonomous Teacher M0 后续推进，执行本文件 G0→G2-L1.1→G3（无 Key）**。  
> 正式验收规范为 `Autonomous_Teacher_M0_v04.md`；本文件是实施/审阅手册；已批准 Request Binding Contract 与 ADR-002 保持有效；G2-L1-FIX 实现 `2786e25...` 与独立 `REVIEW_G2L1.md` 是历史起点，不重做。  
> 先核实实际 HEAD、当前源码和旧证据，输出 G0 baseline。如果相关问题已在 HEAD 解决，提供源码/测试证据后跳过重复改动。  
> 第一轮只处理 G2-L1.1：Provider 进入后异常不得记为 NOT_DISPATCHED、call_id 跨模块 Canonical 一致、Prepared schema/字段严格、Journal 容量、只读 descriptor 不消耗发送配额；每项修复前 RED、修复后 GREEN，附全量/兼容测试，冻结 SHA、提交 Review Packet，然后 STOP 等待维护者/独立 Reviewer。  
> 获得 G3-A 单独批准后，先研究真实锁定 DSH 公开 Provider 插件/SDK 的真实 ABI 并做一个最小可运行 SPIKE。禁止猜 API、改上游私有实现。若可行，再在 G3-B/C/D 以真实 DSH SDK/Session/`skill_lookup` + 受控 IPC + 实际 SQLite/stdio Bound Broker + Fake Provider 运行完整无 Key 流程，验证完整 Prepared/Wire 绑定、并发/异常/重启/Guard 缺失与隔离。G3 完成后再次 STOP，交独立复核。  
> **禁止真实 API Key、真实模型/HTTP、自动 Live、主路由切换、历史证据覆盖、自签授权或放宽安全门槛**。不要实施 G4/G5/G6，除非维护者另行明确授权；真实 Live 必须具备独立受信授权和 PreLive PASS。  
> 交付实际源码 Diff、原始日志、真实计数、每项测试的 PASS/FAIL/BLOCKED 与 SHA、未验证项、成本/维护性分析。任何阻断宁可保留 BLOCKED，也不编造 PASS。

---

## 17. 当前明确的技术债与其应当关闭的位置

| 问题 | 当前位置 | 最晚关闭 Gate | 不允许的误述 |
|---|---|---|---|
| Provider after-entry exception 误记 NOT_DISPATCHED | 已审源码/独立 Review F-2 | G2-L1.1 | `provider_calls=0` = 没计费 |
| Unicode canonical `call_id` 分叉 | 跨上传模块核查 | G2-L1.1 | 只修前缀算统一 |
| Prepared v0 schema 可通过 | Review F-1 | G2-L1.1 | digest 验证 = schema 已验证 |
| 无效 Journal completion 增长 | 待定向验证 | G2-L1.1（非阻断须批准） | `max_messages` 全局有硬界 |
| Descriptor 诊断消耗 attempt | 源码可见 | G2-L1.1 | policy check = 真实 attempt |
| `EgressRequest` 与完整 Provider Wire 不对应 | 已声明 G3 dependency | G3-B/C | 仅 Route/Model 绑定 = Wire 完整一致 |
| 生产 BoundBrokerClaimer/TrustedTransport 未接线 | Review F-9 | G3-B | 单元测试 = 生产发送路径 |
| Guard 缺失时真实独立外呼阻断 | PR2 F7 gap | G3-D / G4 实部署 | 插件内 deny-all 能保护“无插件” |
| 权威 ProviderObservation 可信来源 | PR4b contract 层 | G3 受信 Bridge / G5 真实 | schema-valid = invoice-valid |
| 小阶公钥/Ed25519 准入 | 已知安全审查问题 | G4 PreLive | 换库必定足够 |
| Watchdog 故障 cleanup | 已知安全审查问题 | G4 PreLive（G3-D rehearsal） | kill 发出 = 容器已消失 |
| 官方 DeepSeek 路由、实际工具注册与费用 | Live 未验证 | G4/G5 | OpenCode Go 内测 = 主渠道 PASS |
| E4 六对 / E5-Full | 尚未执行 | G6 | Mock 20例 = 教学效果证明 |

---

## 18. 最小验收表（Lead/维护者每轮都填写）

| Gate | 必选结果 | 源码 SHA | Evidence/Trace | Reviewer Verdict | 维护者批准下一步 |
|---|---|---|---|---|---|
| G0 | 身份基线、差异核对 | 待填写 | 待填写 | 待填写 | 是/否 |
| G2-L1.1 | T1/T2/T3；T4/T5 有界；兼容全量 | 待填写 | 待填写 | 待填写 | 是/否 |
| G3-A | 真实 DSH Provider SPIKE | 待填写 | 待填写 | 待填写 | 是/否 |
| G3-B | IPC / Bound Broker / Fake Provider | 待填写 | 待填写 | 待填写 | 是/否 |
| G3-C | SDK + Tool + Session | 待填写 | 待填写 | 待填写 | 是/否 |
| G3-D | F7/故障/隔离 | 待填写 | 待填写 | 待填写 | 是/否 |
| G4 | E5-PreLive/OS/Key/watchdog | 待填写 | 待填写 | 待填写 | **必须人类** |
| G5 | E1–E3 Live/Usage/账单 | 待填写 | 待填写 | 待填写 | **必须人类** |
| G6 | E4/E5-Full/ADR | 待填写 | 待填写 | 待填写 | **最终人类签核** |

**本文件不包含任何真实验收结果。** 运行后由实施者填表、独立审阅者证实、维护者决定是否进入下一关。

---

## 19. 验收时一句话提醒

> **M0 的目标不是增加报告数量，而是用最少的可信证据证明：真实 DSH 能在可审计、可停止、可控预算的边界内驱动同一固定模型，且工具、Session、评估与异常路径满足 v0.4；达标则冻结 GO 进入 M1，未达标则基于真实阻塞决定修复还是换 Runtime。**
