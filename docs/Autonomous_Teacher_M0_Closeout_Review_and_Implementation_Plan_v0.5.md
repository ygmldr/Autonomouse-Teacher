# Autonomous Teacher — M0 收尾：源码审计修复与下一阶段实施任务书

**版本**：v0.5（审阅建议，不是实现结果）  
**日期**：2026-11-14  
**目标读者**：项目维护者、Lead Coding Agent、Runtime/Accounting/Security/Verification Coding Agents  
**当前总决策**：**DECISION PENDING**  
**默认主路由**：DeepSeek 官方 API / DeepSeek V4.1 Flash（按当前仓库批准配置核实实际模型 ID）  
**策略**：继续单模型；OpenCode Go 优先用于开发，如未确认第三方 API 权限则不用于 DSH Runtime；不做模型选型。

> **一句话目标**：把已通过独立复核的「真实 DSH 引擎 + Synthetic Provider」从离线研究底座，收敛成一个**经过人工批准、凭据受保护、费用风险受控的最小真实模型端到端验证**，并据此对 DSH 作出 GO / CONDITIONAL GO / NO-GO / DECISION PENDING 决策。不得通过删除安全检查、给现有 `--live` 加开关或让 Agent 自行批准的方式达成。

---

## 0. 阅读须知、证据等级与变更控制

### 0.1 本文审阅依据

本文依据本次提供的十份实际文件及其中的历史声明：

| 文件 | 审查用途 |
|---|---|
| `M0_REPORT.md`（上传名 `M0_REPORT(1).md`） | M0 现状、各阶段验收和残余阻塞 |
| `README.md`（上传名 `README(1).md`） | 执行边界、命令、范围声明 |
| `REVIEW_PHASE5.md`（上传名 `REVIEW_PHASE5(1).md`） | 独立测试、审计声明和 V1 纠正 |
| `THREAT_MODEL.md`（上传名 `THREAT_MODEL(1).md`） | 无凭据执行边界、预 Live 缺口 |
| `plugins/runtime-budget-guard/src/index.ts` | 预算 Guard 源码，SHA-256 `1ccdb658413b06ed5ae5c625ae86b2487fd7a6af33abaff941332c6fdf5f1ba3` |
| `src/autoteacher_m0/accounting/broker.py` | 账本 Broker 协议，SHA-256 `9dce2f9397fa5e91d387af7422f94d81ba7116f94923cced55269e9a0b2fc3d3` |
| `src/autoteacher_m0/runtime/dsh_adapter.py` | Runtime Adapter，SHA-256 `888911490c936dff286af5ad823aae1007d88ab50213986c4b809d34b44cc68a` |
| `docs/RUNTIME_BUDGET_GUARD.md` | Guard 的真实能力边界，SHA-256 `1d0b62a23695020d5f7216f345d43942d05695e520c86603bb66e62dab56f11d` |
| `docs/SDK_OFFLINE_SESSIONS.md` | 真 DSH + Synthetic Provider 的 17-case 离线运行 |
| `docs/ADR-001-runtime.md` | GO 决策、主渠道政策和禁止越权规则 |

现有**被测实现**在报告中固定为 `feb7118f9aff20c681cc651812b30315288080f1`，本文不替换这个历史冻结 SHA。具体源码文件的上述哈希是本轮上传副本的内容身份；仓库内应用补丁时必须重新核对实际版本。

**尚未收到**：`ledger.py`、`budget.py`、`broker_usage.py`、相关 `tests/`、实际合并 Profile、生产 Controller/LiveGate、Provider 传输层及原始日志。下面对这些不可见部分只提“待验证假设”，不伪装成确认缺陷。

### 0.2 证据层级

- **A：项目 Mock**：测试业务包装、评分器、记录逻辑；不证明 DSH 引擎。
- **B：真实 DSH 引擎 + Synthetic Provider**：验证真实 SDK/RPC/Session/插件调用链；不证明真实模型、网络、Key、Usage、账单。
- **C：经过批准的 DeepSeek Live**：真实模型、实际工具、真实用量、Session 及账单对账。
- **D：真实学习者收益**：M1 及以后的人类学习评估；**不属于 M0**。

每个测试用例应分别记录 `scope=A/B/C`、源码 SHA、依赖锁、执行 argv/容器 ID、UTC 时间、exit code、原始日志和判定依据。任何离线 PASS **不能**自动转成 Live PASS。

### 0.3 本轮不做什么

不换框架、不比较低价模型、不开发 Web App、不扩展 Domain Research/RSI、不实现多 Agent 编排、不开放任意 Shell、不把 OpenCode Go 订阅假定为可供 DSH 使用的 API。不要重复构建一套与现有独立复核重叠的大规模 Mock 框架。

---

## 1. 审计结论与工作优先级

### 1.1 已有的正面证据，予以保留

第五阶段报告记录：独立复跑 **326 Python tests**（其中含 89 专用子集，不能另加）、**148 Broker 回归**、**17 SDK Synthetic Case**、**8 Cordis Registry Case**、**12 Guard Case + 18 Guard Selftest**，以及 Ruff、wheel 构建与无源码安装验证。这些结论在**其声明的离线范围**内可以接受；不是本文重新执行的测试。

特别值得保留的设计：框架无关的 `RunRequest/RunRecord/AgentRuntime`；唯一 DSH Adapter；实际 SDK + Synthetic Provider；预留在模型流之前、pending 不退款；明确的失败记录；无密钥容器隔离；外部人类审批而非批准文件自解锁。

### 1.2 总体阻塞，不要误写成“仅缺一个 API Key”

| 编号 | 项目 | 当前情况 | 进入 C 层之前的要求 |
|---|---|---|---|
| G0 | 可信控制器/人类授权 | 无 Live 放行路径 | 独立审查、签核、不可由 Agent 修改的执行权限 |
| G1 | 实际 DSH 运行配置 | Synthetic 通过；目标 Profile 未完成生产组合验证 | 同版本目标 Runtime 实际加载 Guard、`skill_lookup`；缺 Guard 时外部拒绝出网/Key |
| G2 | 真实计费边界 | Guard 仅覆盖 logical stream | 识别所有可计费 HTTP/Retry/Files 路径，或部署可验证的更小受限 Live 配置并明确账单上限仍未证明 |
| G3 | 真实模型/Usage | 0 次 Live | 主批准渠道真实调用、工具、结构化输出、Usage/请求身份/费用证据 |
| G4 | 总进程时间限制 | 仅有离线容器超时和 SDK request timeout | 独立外部 watchdog + kill/cleanup + 预算状态保守处理 |
| G5 | 完整 E5/隐藏评估权限 | 外部容器负测部分成立；生产 Controller/候选 Runner 仍缺 | 按 M0 v0.4 完成强制 E5-PreLive/E5-Full 或明确维持 BLOCKED |

**结论**：目前是 `DECISION PENDING`，不能 GO 或 CONDITIONAL GO，也不能因缺少 Live 证据直接宣称 DSH 不可用。

---

## 2. 源码发现：事实、风险、具体修复和回归测试

约定：**Confirmed** 表示上传源码直接可证；**Conditional** 表示源代码行为成立，但对安全/账本影响依赖未上传实现；**Unverified** 表示需要目标运行时证据。优先级 P0=阻断 Live；P1=进入 Live 之前应处理或形成受测限制；P2=可以延后至 M1 的非阻断改善。

### F1 [P1] 重试归因被硬编码为 `false`

**证据**：`index.ts:402–409` 的 `BrokerClient.reserve()` 无论实际请求身份如何，总是发送 `retry: false`；`broker.py:151–163,187–190` 验证并转交给 `BudgetLedger.reserve(retry=...)`。**代码事实：Confirmed；具体账本影响：Conditional（未读到 `ledger.py`）**。

**风险**：如果 `max_retries` 是按 `retry=True` 统计，现有中间件无法正确归因逻辑重试。文档 s9 的“两个独立 reservation”不等于“重试限额有效”。不要未经核查就说已经产生真实超支；当前仅 Synthetic。

**优先设计二选一**：

- **方案 A（推荐用于 M0）**：最小受限配置禁用 Provider 内部自动重试；所有 logical stream 均计为新的 `step/request`，只执行统一 `max_requests/max_steps` 容量控制；正式从验收声明中移除“通过该 `retry` 字段精确限制内层重试”的说法，新增证据验证真实 provider policy 也禁用隐藏重试。
- **方案 B（如确实需要 retry quota）**：仅用可信 Agent Loop 的显式 attempt metadata 标记重试；`retry` 不能由学生 Prompt 或候选插件自报；设计稳定的 `attempt_id/logical_call_id/attempt_index` 并在账本里验证序列与幂等性。

**至少新增测试**：`test_retry_flag_semantics`、`test_two_dispatches_consume_two_request_slots`、`test_max_retries_not_claimed_when_attempt_id_missing`、`test_replay_same_id_not_second_dispatch`。必须读 `ledger.py` 后选择方案并记录 ADR，不允许凭经验猜其计数语义。

**完成定义**：限额含义与代码/测试/文档三者一致；任何未可识别的重试要么被拒绝，要么被计入全局 request/step 成本，不能默默免费。

### F2 [P1] Journal 消息配额会阻塞已有 reservation 的收尾

**证据**：`broker.py:174–180` 在区分 `snapshot/reserve/settle/fail` 前，先查询已记录消息数并执行 `count >= max_messages -> MESSAGE_LIMIT`。**行为：Confirmed**。若 `journal_once` 把 `reserve` 记入账本，则配额耗尽会阻塞下一条 `settle/fail`；其具体阈值及 journaling 过程需 `ledger.py` 验证。

**风险**：已发出的模型请求无法正常结算，`PENDING` 占着预算，查询状态也可能被配额拒绝；这偏向 **可用性/对账完整性**，不等于直接超支。

**修复原则**：禁止新增 reservation **不能**等同于禁止关闭旧 reservation。建议从“所有 Broker 报文一个上限”改成“新建请求容量 + 预留的完成容量”：

1. `reserve` 进入前必须同时为未来 `settle/fail` 保留至少一次可用 journal slot；如果容量不足，直接拒绝 `reserve`。
2. 在无权接触新 provider 的情况下，已存在且合法的 `PENDING` reservation 的一次完成操作仍能被处理；不得开放无限制新 reservation。
3. `snapshot` 的可读性应独立于 reserve 配额，避免在故障时丧失观测；要有频率/大小/存储上界，防止无限查询造成磁盘 DoS。
4. 重复完成请求仍保持幂等，不能双扣/退款/重放 dispatch。

**至少新增测试**：`max_messages=1/2/3` 临界；`reserve` 之后额度用尽再 `settle`；耗尽后 `snapshot`；重复 settle；异常中断、重启后恢复 pending；并发试图抢占最后一个收尾配额。运行后检查 `budget_reservations`、`budget_broker_messages` 与合计不变量。

**完成定义**：额度满时新增调用 fail-closed，既有费用不被当成 0；必要的结算和恢复不会因为新建请求配额耗尽而无限期无法执行。

### F3 [P0 对 Live / P1 对离线] 后置请求摘要不能作为真实费用上限

**证据**：`index.ts:625–635` 先调用 `next()` 并 `yield` 结果，流结束后才比较 `requestDigest()`；摘要只覆盖 `index.ts:340–349` 选定字段，并非整个 SDK/Provider 请求。**行为：Confirmed**。

**风险**：在下游修改了 `maxTokens`、路由、工具或其他请求参数的情况下，篡改检测时真实请求可能已发出并已计费；以原上界 worst-case 结算不保证覆盖修改后的成本。错误结果还可能已交给消费者。当前 Synthetic 检测成功只是**事后发现**，不是完整的**事前约束**。

**修复方案**：

- 不允许未经审核的 RSI 候选插件与带 Key Provider 处于同一可信 Runtime/权限域。
- 在最靠近 Provider 发包的已审查 Adapter/网络代理上再做一次只读白名单验证；必要时由可信控制器**创建**不可变的 model/request 参数，禁止下游更改 `provider/model/maxTokens/attachments/retryPolicy/endpoint`。
- 用实际目标 SDK 的类型与 Transport 确认 Digest 完整性；增补字段列表及版本监控，不将 Digest 当作唯一防线。
- 若请求在 dispatch 后被篡改：保守保留费用、标记 `REQUEST_INTEGRITY_UNCERTAIN`；不把此次运行记为成功验收。

**至少新增测试**：恶意下游增大 `maxTokens`、替换 provider、加入 Files、改 tools schema；断言 **provider 边界发包前**被拦截，而不只是流结束后发现；如果框架公开扩展点做不到，应记为技术限制并以外部 egress/broker 边界补足。

**完成定义**：可信发包路径能验证最终发送参数；超额/未批准路由在 Provider HTTP 之前失败。否则不得对 Live 声称 Guard 是硬费用上限。

### F4 [P1] `SETTLE_UNCERTAIN` 无法通过正常运行结果显式传递

**证据**：`index.ts:640–650` 捕获结算异常后记录日志并执行 `broker.shutdown()`，没有重新抛出。**行为：Confirmed**。如果模型流在此之前完成，上层可能把它当作普通成功。也未证明 Broker 的后续 stream 有立即生效的显式 unavailable latch；需要实测。

**修复方案**：把 `model_completion_status` 与 `accounting_status` 拆开。推荐共享 schema：

```text
model_completion_status = SUCCESS | INTERRUPTED | ERROR | UNKNOWN
accounting_status       = RESERVED | SETTLED | WORST_CASE_HELD | SETTLEMENT_UNCERTAIN
final_acceptance        = model_completion_status == SUCCESS
                          AND accounting_status == SETTLED
                          AND audit_integrity == VERIFIED
```

- 用机器可解析的状态事件/结构化记录把结算未知传给可信 Controller，而不只是写 stderr；无法传递则主动使整个 run 的验收失败。
- 下一次模型 dispatch 必须被**立即**拒绝；明确 broker 生命周期 latch 与正常 shutdown 的区别。
- `PENDING` 不释放，先持久化审计状态再尝试停止；不重复提交非幂等 settle。

**至少新增测试**：Broker 在 Provider 完成后、回应 settle 前 SIGKILL；`settle` ack 丢失；守卫认为成功而审计器必须标记 `ACCOUNTING_UNCERTAIN`；同 scope 后续 stream 拒绝；Broker 恢复时同 ID 幂等核对。

### F5 [P1] `encodeTaskId()` 不是单射（可能碰撞）

**证据**：`index.ts:333–337` 通过替换非法字符与截断生成 `rbg-*`，例如 `a/b`、`a_b` 可能映射为同一字符串。**碰撞：Confirmed；是否损坏 Ledger 归因：Unverified**。

**修复方案**：使用来自可信 Session 记录的稳定标识，或固定前缀 + `sha256(canonical session ID)` 的规范化短摘要，保持 Broker ID 长度约束（如 64 十六进制字符）。区分 Session Identity 与 Run/Attempt Identity；避免把不同实验的同名 Session 当作相同 Budget Scope。

**至少新增测试**：替换字符碰撞、超长相同前缀、不同 Unicode、跨进程稳定性、不同 scope、同 Session 并行请求；确保生成标识稳定且区分。

### F6 [P1] Broker 故障日志具有误导性且转发未经净化的诊断

**证据**：`index.ts:566–578` 在任意 `#fail()` 中均打 `reservations_not_dispatched: true`，但错误可能发生在 Provider 已运行后的 settle；同时 `#stderrLines` 被写入 `BROKER_DIAGNOSTICS`，而多处 `reason` 可能包含下游错误文本。**行为：Confirmed；是否包含 Key：未发生 Live，未验证**。

**修复方案**：

- 使用准确的机器状态：`phase=BEFORE_DISPATCH | DISPATCHED | SETTLING | UNKNOWN`；维护 `reservation_id`、单调计数和响应状态，禁止固定宣称所有 reservation 均未派发。
- 对外只导出**允许列表中的错误码、数字、布尔值、哈希化 ID**。原始子进程 stderr/错误 message 仅能存在受访问控制、定期删除的受限诊断区，并且仍应应用密钥哨兵测试。
- 考虑 `RESERVE` 中的 `session_id` 是否可能包含个人数据；公开审计报告优先使用哈希标识。

**至少新增测试**：`reserve` 前异常、Provider 执行中异常、settle 异常，断言 `phase` 不撒谎；注入 `sk-FAKE-SECRET` 哨兵到 error/stderr/session id，确保公开 log/Trace/报告里不存在。

### F7 [P0] 仅依赖 Guard 插件本身无法证明“缺插件时无法发包”

**证据**：`RUNTIME_BUDGET_GUARD.md §2,§7` 承认上游 loader 可能在模块 import 失败后 warning 继续；插件对“`apply` 被调用后的无效 config”注册 deny-all，但**不能覆盖“Guard 模块根本没有加载”的情况**。

**修复方案（架构级）**：Guard 是第一层，**独立于 DSH 的可信 Live Controller / egress 边界**是第二层。让 DSH 在无直接真实 Key、无不受控外网的权限域运行；真正的 Key/外呼只由外部已审查 Broker/Proxy 持有。真实放行前检查目标 Profile 的插件名/版本/实际注册和 guard health，独立执行一次 Guard 缺失/崩溃负测。不能仅凭进程自己打印 `RBG_BOOT` 视为可信 attestation。

**验收**：删除 Guard 插件、插件语法损坏、`apply` 拒绝、Broker 不可用、Profile 动态注入其他 provider 时，**所有路径均无法产生可计费 provider 请求**；至少在外部网络/凭据边界可观察证明。若做不到，Live 保持 BLOCKED。

### F8 [P1] Guard → Broker 配置存在“读后启动”时序，应由部署权限保证不可变

**证据**：`index.ts:211–265` 在 Guard apply 时读取并哈希 Broker 配置；`index.ts:470–472` 稍后以文件路径启动 Broker，Broker 自行再次读取文件（`broker.py:276–285`）。若攻击者能在两次读取之间修改路径/文件，存在 TOCTOU 风险。**时序：Confirmed；实际是否可修改：取决于外部只读挂载/权限，未验证**。

**修复**：配置文件、父目录和路径解析处于可信只读挂载；不允许未受信代码访问/重命名；在外部 Controller 侧验证运行中挂载身份与完整 SHA。可选进一步消除双读竞态（将已经验证的只读文件描述符/字节通过受控通道传给 Broker）。

**验收**：尝试修改 config、替换 symlink、覆盖 DB 路径等负测均无法改变有效 Broker Policy；如果部署环境本身保证绝对只读，记录系统级证据而非不必要地重写协议。

### F9 [P1] Usage / 错误映射需要真实事件证据

**证据**：`dsh_adapter.py:58–92` 明确把 `input_tokens/output_tokens/estimated_cost_usd` 留 `None`，实际模型版本与 request ID 留 `None`；`classify_error()` 只处理 HTTP-shaped status，注释明确 SDK JSON-RPC 错误码未校准。**行为：Confirmed；真实 wire 映射：未测**。

**修复**：在保留无 SDK 类型泄漏的前提下，做标准化 `ProviderObservation`：`requested_route`,`observed_route`,`model_reported`,`provider_request_id`,`usage_raw_hash`,`input/cache/output/reasoning`, `cost_estimate`,`cost_source`,`error_kind`,`complete/uncertain`。原始事件在可信隔离环境内存储并脱敏；无字段仍为 `None`，不要填 0。

**验收**：真实成功、401、429、5xx、timeout、缺 Usage/部分 Usage、工具轮调用都能分类；最终以 Provider 账单或可靠计费记录核对，不能因 SDK final text 返回而认为 Usage 可靠。

### F10 [P1] Live 受限实验还缺独立 total watchdog 与进程清理证据

**证据**：`dsh_adapter.py:125–165` 的运行路径不可达，且代码注释明确 `request_timeout_seconds` 不是整体执行活动上界。`THREAT_MODEL.md` 的离线容器资源限制不能替代 Live 整体时间限制。

**修复**：可信 Controller 设定**总运行时长、step 上限、进程树杀死、容器清理、账本最坏情况保留**；超时后不能重试同一个不明状态的 billable attempt。测试 SDK hung、provider half-open、工具无限循环、broker deadlock、kill between reserve and commit。

**验收**：所有故障均在外部时间上限内停止，进程/容器无残留，下一次实验需要新的明确批准；无法证明 provider 没计费时，预算保持 pending/worst-case。

---

## 3. 缺失证据与应暂停的工作

### 3.1 最需要补看的源码

1. `src/autoteacher_m0/accounting/ledger.py` + `budget.py`：F1/F2 的最终语义，`max_steps`、`max_retries`、pending、journal 边界。
2. `src/autoteacher_m0/accounting/broker_usage.py` + `pricing.py`：Usage 映射、reasoning/cache 字段、已知额外费用。
3. `tests/` 下 Guard/Broker/Adapter/Gate 用例：确认失败前测试、避免重复造轮子。
4. 实际 DSH merged Profile 和加载脚本：运行时注册、默认工具、upload 状态。
5. Phase5 原始 `manifest.json` + 12-case guard 原始日志及 SDK 17-case 日志：原始执行顺序/事件校验。

缺少这些时，Coding Agent 可以先完成 PR0 的证据收集和静态修复建议，但**不得**自称已经审计完整真实预算系统。

### 3.2 暂停/延后

- 不再增加无直接目标的新 Mock 套件，除非覆盖 F1–F10 的特定失败用例。
- 不再反复重算所有历史冻结阶段以扩大“PASS 总数”；仅针对变更影响域做回归，最终统一独立复核。
- 不引入新的模型/路由选择、DSPy/GEPA/OpenEvolve、实时自改代码、前端、多领域课程。
- 复杂跨机 OCI 恢复与全平台支持可延后，但如果 M0 v0.4 将其列为强制验收，必须由维护者**显式修订验收规范**，不能由 Agent 私自忽略。

---

## 4. 推荐目标架构（C 层最小可验证部署）

```text
        Maintainer (human approval; independent of candidate repo)
                    |
                    v
  +------------------------------------------+
  | Trusted Experiment Controller            |
  | fixed SHA/profile/route/limits/timeouts  |
  | no candidate self-approval               |
  +------------------------------------------+
           | request only           | secure credentials
           v                        v
  +-----------------------+   +---------------------------+
  | DSH Runtime           |   | Independent Egress/Key    |
  | reviewed plugins only |-->| Broker / Approved Proxy   |---> DeepSeek API
  | skill_lookup + Guard  |   | route, budget, request    |
  | NO real API Key       |   | identity, external stop   |
  +-----------------------+   +---------------------------+
           |                         |
           v                         v
  +-----------------------+   +---------------------------+
  | Session/Events Store  |   | Provider Usage & Cost DB  |
  | no private eval input |   | pending != zero          |
  +-----------------------+   +---------------------------+
           \_________________________/
                        |
                        v
          Independent Report / ADR Decision

  [Isolated candidate runner: no key, no proxy credential,
   no host bind mounts, no hidden graders, no Docker socket]
```

**重要约束**：以上是**建议的目标架构**，不是声称 DSH 已经支持上述所有连接。若所选 Provider/SDK 强制在 DSH Runtime 环境直接获取 Key，则需在独立受限的可信 Runtime 域执行并验证 egress，或将 Proxy 用官方受支持接口接入；若既不能分离 Key/权限又无法证明 Guard 缺失时阻止可计费外呼，则保持 Live BLOCKED，必要时停止 DSH 路线。

### 4.1 权限矩阵

| 能力 | 候选/RSI 容器 | 可信 DSH 容器 | 可信 Controller/Proxy |
|---|---|---|---|
| 真实 API Key | 禁止 | 首选禁止 | 仅这里持有、最小授权 |
| 任意 Shell | 无 | 不开放工具 | 维护者部署时允许，不转授给 Agent |
| 外网 | 禁止 | 默认禁网/只能访问获批 Proxy | 仅获批 API endpoint |
| 对账/预算 DB 写权限 | 禁止 | 通过固定协议提交预留/Usage，不直接写库 | 独占 |
| 私有评估标签 | 禁止 | 禁止 | 评估器独立持有 |
| DSH Session | 只能访问公共合成 fixture | 固定本次 Session namespace | 按最低权限收集 Trace |
| 插件/配置修改 | 允许生成候选，不影响当前进程 | 不得热替换未签核代码 | 只有维护者批准新不可变版本 |

### 4.2 启动顺序（不可交换）

1. 维护者审阅并冻结代码、依赖、Profile、完整插件/Tool Registry 与路由配置。
2. Controller 验证哈希、权限、禁止上传与禁用危险工具；外部 Proxy/Key Broker 验证路由与费用限制。
3. 仅先运行**无 Key Synthetic** 健康检查，包含 Guard 缺失/无效/未触发时的外部拒绝。
4. 维护者在**独立受控环境**批准固定版本的短时 Live 实验；审批不得由仓库 Markdown、CLI flag、环境变量单独完成。
5. 建立低额度可撤销 Key/限制供应商支出，启动外部 watchdog，开放经过准入的最小请求路径。
6. 做最小 C 层用例，完成即回收权限。任何快照/输入/依赖变更先停止，再重新审批。

---

## 5. 实施工作包：每个 PR 的输入、实现、验证、验收和退路

### PR0 — 固化来源与缺口定位（无 Key、无网络）

**依赖**：无；**阻塞 Live**：是（完成审查所必需）。

**任务**：
- 确认仓库 HEAD、当前六份源码与本文哈希的差异；维护完整 `SOURCE_INVENTORY.json`，区分最新文档归档 commit 与被测实现 commit。
- 补读 `ledger.py` / `budget.py` / `broker_usage.py`、关键测试和 Profile；为 F1–F10 建立 `findings.json`，字段含 severity / confirmed or conditional / relevant evidence / owner / remediation / regression / status。
- 只运行已经验证的无 Key、禁网容器中的离线测试；不得用宿主直接 import 未审查代码。

**交付**：`docs/M0_REVIEW_FINDINGS.md`、`artifacts/m0-closeout-baseline/manifest.json`、`docs/OPEN_QUESTIONS.md`。  
**验收**：所有文件与 SHA 对应；F1/F2 的 Ledger 语义不再猜测；未解释的行为标 `UNVERIFIED`，不写 PASS。

### PR1 — Broker/Guard 协议修复（无 Key）

**依赖**：PR0；**可与 PR2 设计并行**。

**最小改动**：
1. F1 明确 retry policy（推荐 M0 全部关闭自动重试，logical stream 都计数）；若选择 attempt metadata，先写协议再实现。
2. F2 将新预留容量与旧预留的完成容量分开，保留有界 snapshot/recovery。
3. F4 加 `accounting_status` 和 fail-closed latch，保证结算不明不会被归为完整成功。
4. F5 哈希化且稳定的 session/task ID。
5. F6 分阶段日志、错误码 allowlist、密钥哨兵脱敏。
6. F3 的事后 Digest 保留为审计；不可再描述成强制阻止了下游已发请求。

**接口注意**：如果改变 `broker.py` 的 v1 NDJSON 请求/响应，应显式升级协议版本或提供兼容解析，不得静默破坏 Phase5 历史 fixture；应新增 `protocol_version`/`capabilities` 握手测试。历史冻结日志不可改写。

**交付**：`plugins/runtime-budget-guard/`、`accounting/` 相关最小 diff、协议说明、定向回归测试、独立运行日志。  
**验收**：F1–F6 对应定向测试完整 PASS；Guard/Broker 失败时从不出现“无预留 dispatch”；保留历史 148 Broker/12 Guard/18 Selftest 的可复验能力，必要时通过兼容 fixture 解释预期变更。  
**退路**：若 F1 涉及 SDK 内部不可观测 retry，先禁用 retry 并用真实请求边界补强，不强行预测内层行为。

### PR2 — 目标 DSH Runtime 与插件一致性联调（仍然无 Key）

**依赖**：PR0；PR1 的相关改动集成后复验。

**任务**：
- 以实际计划用于 Live 的**唯一** SDK Runtime 版本（目前记录 Python wheel `0.2.2rc2`，实际 CLI `0.2.2-rc.2`）构建并加载 `skill_lookup`、Guard 与合成 Provider。注意 npm 插件 ABI 历史 `0.2.1-rc.2` 不等于目标 Runtime 已兼容。
- 从真实合并配置读取注册 Provider、实际 ToolSet、模型和上传参数，区别 raw registry 和实际 Agent 可调用工具。
- 实现外部健康验证：插件缺失、Guard import 失败、错误 config、Broker down、超限、恶意额外 provider 时，必须无可计费外呼；Synthetic 先用网络计数哨兵模拟这些失败。
- 保留 `sdk-minimal` 无额外能力的版本边界，不通过侵入式 Fork 偷改 Runtime。

**交付**：`docs/DSH_TARGET_PROFILE.md`、`scripts/verify_runtime_profile.*`（在无凭据已审查环境内使用）、Synthetic 集成 manifest/trace。  
**验收**：不少于 3 次目标 Runtime 重启加载成功；工具实际注册/执行；Guard 配置无效或缺模块时，外部边界仍阻止请求；记录二进制/插件哈希。  
**退路**：若公开插件 ABI 在目标 Runtime 不兼容，可尝试官方同版发布/公开扩展点/受支持 TS Runner；记录修复所需维护成本。若必须长期维护侵入式核心 Fork，考虑技术 NO-GO 候选。

### PR3 — 可信 Live Controller 设计及无 Key 故障验证

**依赖**：PR0；可与 PR2 并行。**不授予 Live 权限**。

**任务**：
- 定义不可由 Agent 自行签发的 `ExecutionAuthorization`：精确 code SHA、锁文件 SHA、Runtime/plugin SHA、merged Profile SHA、批准主路由、允许工具、预算 scope、单次上限、模型、时限、过期与撤销。
- 部署/演练独立授权与凭据边界，审核具体 mount/env/process tree；杜绝传 `--live`、修改 `SECURITY_APPROVALS.md` 或自签文件后获得 Key。
- 外部 watchdog：总 deadline、每 step 上限、进程清理、崩溃恢复 pending。
- 注入**假**凭据和假私有标签，测试凭据/文件/日志、权限继承、防守卫缺失。
- 禁止真实 Agent 候选运行路径触及 Key Proxy 或任何允许任意请求的通用 URL 代理。

**交付**：`docs/LIVE_CONTROLLER_SECURITY_DESIGN.md`、可信 Controller 代码及部署清单（待人类审阅）、`E5_PRELIVE_NO_KEY_REPORT.md`。  
**验收**：所有负向用例拒绝且留下审计证据；授权不能被 Agent 修改；Profile 与实际运行一致；**此 PR 完成仍不代表 Live 已批准**。

### PR4 — 真正的请求/费用边界（先模拟网络，不注入真 Key）

**依赖**：PR1/2/3。

**任务**：
- 使用 Mock HTTP/本地受控 egress 观测一个 logical-stream 对应的真实 HTTP attempt、retry、cache/Files/compaction 行为；所有计费或可能计费路径都要列为 `BILLABLE_PATH_INVENTORY.md`。
- 在可观察的最靠近发包位置加固定路由、请求额度、参数上界、请求身份与账本预留；任何另开连接都被网络策略拒绝。
- 缺 Usage、SDK transport hang、重试返回不确定时按 worst-case 保留，账单最终核验另行记录。
- 明确 **local hard accounting bound** 与 **provider-issued invoice cap** 不是同一概念。供应商侧能设硬额度就额外配置并记录证明；若只有软提醒不能宣称硬限额。
- 每次 Live call 最多一次经维护者批准的有限尝试；未知结果不得自动重试。

**交付**：`docs/BILLABLE_PATH_INVENTORY.md`、`docs/PROVIDER_USAGE_MAPPING.md`、mock-egress 测试/日志、完整失败矩阵。  
**验收**：无法越过外部 egress/Key 边界直接发请求；在所有覆盖的错误路径里，未预留/超预算/未批准配置一律在发包前被拒绝；每个外呼事件有稳定可关联 ID。  
**退路**：如果官方 Provider SDK 内部不可控的额外计费请求无法被可靠限制，可优先采用受支持的低权限转发代理或固定一次性短会话，并将“真实硬预算”标为未通过；不得伪称全额上线级保障。

### PR5 — 人工审批后的最小 Live 实验

**依赖**：PR1–4、安全审核、真实可撤销低额度凭据。**只能由维护者主动触发**。

**严格前置**：独立签核冻结实现及部署、主路由 DeepSeek Flash ID 核对、Provider 当日价目留档、禁危险工具/上传、可靠守卫加载、可计费请求控制/低额度、watchdog、确认无其他外呼、真实日志脱敏。任何条件缺失 → `BLOCKED`。

**用例与顺序**：
1. `LIVE-00` 健康检查（无凭据）：缺 Guard/错误 Profile/错误路由一律拒绝。
2. `LIVE-01` 只读基本 Smoke 3/3，固定同一模型与主批准渠道，独立 Session，不自动换路由。
3. `LIVE-02` 严格 JSON/Pydantic 合约：`{"skill_id":"binary_search","ready":true}`，明确策略为模型生成→项目解析。
4. `LIVE-03` 模型**实际发起** `skill_lookup` 工具调用；检查 `tool-call`、`tool/result`、最终回答和模型轮次。
5. `LIVE-04` 真实跨进程 Session 3/3 save/recall、unknown ID、受控中断（允许在预算范围内）。
6. `LIVE-05` 安全错误：未经审批路由/超预算在外呼前拒绝；真实 401/429/5xx 若不可安全低成本触发，可以用经验证的外部网络错误注入并明确 **synthetic error**，不把它写成 Live 真实异常 PASS。
7. `LIVE-06` 原始 Usage、Provider 请求身份、缓存/输出费用、总消费和可能不一致状态记录。

**预算**：延续 M0 v0.4 **US$3 软预算、US$10 硬预算目标、50 次 Live 模型调用上限**。对真实供应商账单的严格硬约束必须有独立 provider-side/egress-side 证据；若不能做到，低额度受限实验可以作为研发诊断，但不得自动满足完整 GO 的真实硬费用验收。

**交付**：`artifacts/live-m0/manifest.json`、脱敏 Trace、受信账单核验、`docs/E1_E2_E3_LIVE_REPORT.md`。  
**验收**：E1 3/3，E2 模型真实调用工具至少 3/3（与 M0 v0.4 一致），E3 恢复 3/3，路由/身份/Usage 可追踪，真实 Provider 调用与错误不混淆。  
**退路**：如果官方 API 不可用，按已有 `ROUTE_DECISION` 由人类**事前批准**同模型 OpenRouter 主路由并重跑受影响全部 Live 验收；不自动切换，更不将 OpenCode Go 订阅等同于第三方 API 许可。

### PR6 — E4 独立配对实验及完整 E5 收尾

**依赖**：PR5；E5-Full 中与 Live 无关的子项可提前完成。

**E4**：
- 已有 20 个 Mock 配对用例继续保留；额外加入明确优劣关系的 counterfactual fixtures（例如正确诊断 vs 错误诊断），确保评估器能出现期望的**非零**分差；不能用伪答案泄露来伪造有效提升。
- 同一模型/同一获批路由/同一预算配置下，至少 **6 对真实** `teacher_v0` 与 `teacher_v1`，使用独立 Session、随机或平衡顺序、同一 Case、独立评分与报告。
- 输出每对 `scores/evidence/cost/usage`；无法得到可信 Usage 则该条费用测试不 PASS。Mock 对照通过不证明人类学习增益。

**E5-Full**：对候选无法访问其他 home、真实 Key/假 Key、私有测试标签、网络、Docker socket、被禁写目录、超限资源、崩溃后的干净恢复、完整 merged Profile 等逐条完成。若现有 `ContainerRunner.run()` 仍未端到端运行，而该条是规范强制项，应继续 BLOCKED 或由维护者调整规范；不能将 rootfs 命令结果冒充候选 Runner.run 成功。

**交付**：`E4_PAIR_REPORT.md`、`E5_FULL_REPORT.md`、相关原始 manifest、失败路径测试。  
**验收**：20 案 Mock 全部可复现、6 对 Live 有完整对照记录、评估器独立/能识别明显优劣；E5 必选项均完成并记录残余风险。

### PR7 — 独立验收、选型 ADR 与冻结

**依赖**：PR0–6 所有必选范围。

- 新冻结 SHA，禁止覆写旧 Phase5 history；记录所有修复 PR 的 SHA 与实际测试日志。
- 独立非实现者使用相同已冻结字节重跑关键 Python/Broker/插件/SDK/Guard tests，并交叉核对 Live trace/Usage/费用和授权证据。
- 更新 `docs/M0_REPORT.md`、`docs/ADR-001-runtime.md`，逐项列出每个 E1–E5 的 `PASS/FAIL/BLOCKED/NOT RUN`，不能把不同测试子集相加。
- 仅此时根据下述政策决定框架去留。

---

## 6. 测试矩阵（可直接映射到 pytest/node 用例）

| ID | 目标 | 覆盖级别 | 触发条件 | 关键 Assert | 关联 |
|---|---|---|---|---|---|
| T-RETRY-01 | retry 归因明确 | A/B | 同任务两次 dispatch | 总次数受限；不谎称内层 retry | F1 |
| T-RETRY-02 | 不可识别重试被保守限制 | B | retry metadata 缺失 | 不免费放行或自动重试 | F1 |
| T-JOURNAL-01 | 消息配额边界 | A | 额度在 reserve 后耗尽 | settle/fail 仍可完成既有任务 | F2 |
| T-JOURNAL-02 | 可观测性 | A | 禁止新的 reserve | snapshot/recovery 在有界限制下可用 | F2 |
| T-JOURNAL-03 | 崩溃重启 | A | pending 后 SIGKILL | 无退款、无二次 dispatch、可结算 | F2 |
| T-MUT-01 | 事前拦截 Token 篡改 | B + mock egress | 修改 `maxTokens` | Provider 外呼数 0 | F3 |
| T-MUT-02 | 事前拦截路由/Files | B + mock egress | 变更 provider/attachment | Provider 外呼数 0 | F3 |
| T-SETTLE-01 | ack 不明 | B | 模型结束后 Broker 超时 | accounting_status=UNCERTAIN；不宣布完整 PASS | F4 |
| T-SETTLE-02 | 后续请求 latch | B | 上例之后再发 stream | 新 dispatch 数 0 | F4 |
| T-ID-01 | 字符规范化碰撞 | A | `a/b` 对 `a_b` | taskId 不同 | F5 |
| T-ID-02 | 截断碰撞 | A | 长公共前缀不同尾部 | taskId 不同且稳定 | F5 |
| T-LOG-01 | 故障阶段准确 | A/B | 发包前/后/结算异常 | phase 正确，不误写 never dispatched | F6 |
| T-LOG-02 | 脱敏 | A/B | Key 哨兵在 stderr/message/Session | 公共日志不含哨兵 | F6 |
| T-BOOT-01 | Guard import 缺失 | B + mock egress | 移走 Guard module | 外部 egress/Key 边界拒绝 | F7 |
| T-BOOT-02 | Guard invalid config | B | 改 hash/路径 | 真 Provider 不执行，deny-all 或外部拒绝 | F7/F8 |
| T-BOOT-03 | Broker crash | B | broker died | 当前 pending 持久、未来 dispatch 0 | F7 |
| T-USAGE-01 | Usage 缺失 | B | provider 不送 usage | 不填 0、不记成功费用验收 | F9 |
| T-USAGE-02 | Usage 字段 | C | 真实 API 回复含 cache/reasoning | 按实际 schema 映射，未知字段保留 None | F9 |
| T-WD-01 | 外部超时 | B | SDK 不结束 | 进程清理，pending 保留 | F10 |
| T-WD-02 | 半途断网 | B | 外呼发起但 ack/finish 不明 | 不自动重试、不把账单视为 0 | F10 |
| T-LIVE-01 | 真模型 Smoke | C | 当前主路由 | 3/3，路由不变，费用有据 | E1 |
| T-LIVE-02 | 真模型工具 | C | 模型决定调用 `skill_lookup` | 真 tool-call/tool-result，3/3 | E1/E2 |
| T-LIVE-03 | 真 Session | C | 关闭并新进程恢复 | 3/3；逻辑隔离不等于 OS 隔离 | E3 |
| T-LIVE-04 | 策略配对 | C | 6 对 teacher v0/v1 | 独立 session、评分/成本逐对记录 | E4 |
| T-E5-01 | 不可信候选无法越权 | B/OS | 假 Key、其他 home、私有标签、网络、socket | 均被拒绝、并有原始 OS 证据 | E5 |

### 6.1 不变量（每次回归必须守住）

```text
I1: No approved code/profile/route/authorization -> no billable outbound request.
I2: No successful reservation -> no provider dispatch.
I3: Duplicate reservation/message ID -> never grants a second dispatch.
I4: Unknown or missing Usage -> not silently zero; conservatively pending/held.
I5: Accounting uncertain -> cannot be reported as full run PASS.
I6: Candidate/unreviewed plugin never inherits credential or evaluator authority.
I7: A/B Synthetic results never labeled C/Live.
I8: SDK types never leak into project core contracts.
I9: Optional route failure alone does not downgrade GO.
I10: Any changed approved byte -> old Live authorization invalidated.
```

---

## 7. 判定矩阵与 STOP 规则

### 7.1 GO / CONDITIONAL GO / NO-GO / PENDING

| 观察到的真实状态 | 结论 |
|---|---|
| E1–E5 全部强制项经批准渠道 PASS；无阻断性安全/费用缺口 | **GO（仅对已批准配置）** |
| 安全与必需功能均 PASS，仅有已验证的可补偿非关键限制 | **CONDITIONAL GO**：每项附责任人、限制、到期与停止条件 |
| 已证实无法在可维护成本内解决的核心 SDK/插件兼容问题；或不可补偿安全越界 | **NO-GO**（必须给出重复实验和不可接受原因） |
| 人类审批/Key/真实模型、Provider 用量、Guard 缺失负测、E5 必选项未完成 | **DECISION PENDING / BLOCKED** |
| 未采用的 OpenRouter/OpenCode Go 接入失败 | 不降低已满足的主渠道 GO；单列 OPTIONAL FAIL |
| 官方路由失败但经人类批准换成同模型 OpenRouter，完整复验成功 | **GO（仅针对新获批 OpenRouter 配置）**；官方失败单列 |

### 7.2 必须立即停止的条件

出现以下任一条件，当前 Live 会话必须停止、撤销可用凭据、保留证据并由维护者复核：

- Guard 插件未装载或外部 egress 允许绕过；
- 未预留但 Provider 已开始；
- 请求实际路由与批准路由不符；
- Unknown/uncertain settlement 后仍能启动新的 billable request；
- 真实 Secret 出现在候选环境、输出、Session 日志或公共 Artifact；
- Watchdog 不能终止超时 Runtime/工具进程；
- 真实成本/请求数达到维护者设定的限制，或无法界定剩余费用风险；
- 已审批源码/依赖/Profile/Tool Registry 发生变化。

STOP 后不得因“只剩几个用例”继续使用同一批准或凭据；必须先定位原因、修订代码与配置、重做隔离验证及重新授权。

---

## 8. 开发成本与额度控制

继续执行既定 **US$3 软预算 / US$10 硬预算目标 / 50 次 Live 模型调用上限**。这不是对 Provider 当前价格的陈述；执行前取官方当日价目及 route model ID、缓存/额外费用规则，并记录采样时间。

- PR0–4：**0 次真实 API 调用**，只用 Mock/Synthetic/本地受限 egress。
- PR5：先 3× Smoke → 结构化输出 → 工具 3× → Session 恢复；一旦某条核心链路失败，先修复，不继续把所有预算花在后续 Live。
- PR6：至少 6 对配对（12 次主实验；注意每次 Agent run 可能含多个可计费步骤，因此请求数按真实出站 attempt 计，而非只统计外层 `run()` 次数）。
- 提供每日/实验 scope cap、总 cap、单请求 output/context 上限、外部 Watchdog 与可撤销 Key。只有真实观察/代理层防护充分时才能声明硬上限；否则按受限验证记录实际最大风险并保持完整预算安全项 BLOCKED。
- OpenCode Go：作为 Coding Agent 开发订阅优先使用；除非明确官方支持第三方 API 且被批准为主渠道，否则不算 DSH 的免费或必需路由。

---

## 9. 需要维护者提供的最少决策

本任务允许 Agent **无需问答**先执行 PR0–PR4 的无凭据工作，但进入 PR5 之前需要维护者亲自处理：

1. 确认真实实验使用的主渠道及模型准确 ID（默认 DeepSeek 官方/Flash，不进行模型比价）。
2. 独立审查冻结的代码/依赖/合并 Profile/工具清单/Secret 流向，并以**仓库外**受控方式作人工授权。
3. 准备低额度、专用、可撤销的 API 凭据；如供应商有真正强制支出上限，设置并留存证据。
4. 检查 Live Runtime/Proxy/沙盒的外部 OS 权限及网络隔离；不要把 `.gitignore`、不同 `DSH_HOME`、文档审批文件当作安全隔离。
5. 确认是否接受当前 M0 v0.4 的全部强制 E5 条款；如要修改，只能先**人工显式更新规范**并说明安全代价，而不是让 Coding Agent 擅自删测。

---

## 10. Coding Agent 交接说明（可直接复制）

> 你是 Autonomous Teacher M0 Closeout 的 Lead Agent。请阅读本文件和现有 `M0 v0.4`、`M0_REPORT`、`REVIEW_PHASE5`、`THREAT_MODEL`。当前最新历史冻结实现 SHA 为 `feb7118f9aff20c681cc651812b30315288080f1`，不要修改已冻结历史证据。
>
> 目标是完成 PR0→PR7 的最小可验证交付，**不是**开发 M1、模型选型或自主 RSI。模型固定 DeepSeek V4.1 Flash，OpenCode Go 仅作为优先开发订阅而非默认 Runtime 凭据。
>
> **先做 PR0**：核对上传源码身份，实际检查 `ledger.py`、`budget.py`、`broker_usage.py`、tests 和 merged Profile；根据源码将 F1–F10 分类为 `CONFIRMED / CONDITIONAL / UNVERIFIED`。不得根据本文的可能风险擅自声称已实际突破预算。
>
> 在**无真实凭据、禁网、非 root、只读输入、资源限制的经验证容器**内实施 PR1–PR4，保持 SDK 的业务隔离、fail-closed 以及历史证据可追溯。每项修改先提交能失败的定向用例，再补实现；对可能不兼容的协议/Schema 变化记录版本与回归。
>
> **禁止**使用 CLI flag、环境变量、Markdown 安全审批文件或 Agent 自签内容解锁 Live。只有当 PR1–PR4 完成，且维护者在外部可信环境完成真实人工审查及专用凭据授权后，才可申请 PR5 的有限 Live 验证。执行 Agent 不得自行运行任何需要真实 API Key 的步骤。
>
> 报告必须区分 A 项目 Mock、B 真实引擎 Synthetic、C 真实 DeepSeek Live；分别保存 code/config/lock SHA、命令、UTC、exit、事件日志、usage、账本状态、失败原因。未知费用保持未知，不能视为 0。没有证据的条目标记 `BLOCKED`，不强判 GO/NO-GO。
>
> 按 PR0→PR7 顺序交付：`SOURCE_INVENTORY`、修复 diff + 定向测试、目标 Runtime Profile 和 Guard 缺失负测、可信 Controller 的无 Key 测试、billable path inventory、获批 Live Trace/费用、E4/E5 报告、最终 ADR。只针对需要改变的范围增加测试；避免无目标的阶段扩展和测试数量堆砌。
>
> 在 PR3 完成时停止并提交审阅，**不要**自动进入 PR5 或索取真实密钥。若发现 DSH 无公开可靠方法实现必要外呼/权限边界，形成技术证据并提出精简退路（官方 TS Runner/公开 JSON-RPC 或 PydanticAI Adapter）；不要维护侵入式 DSH Fork 来勉强通过测试。

---

## 11. 推荐的最终交付目录

以下是建议新增文件，实际应尽量沿用现有结构，避免同时创建两套相互冲突的控制器：

```text
docs/
  M0_REVIEW_FINDINGS.md
  M0_CLOSEOUT_ROADMAP.md                # 本文可作为初版
  DSH_TARGET_PROFILE.md
  LIVE_CONTROLLER_SECURITY_DESIGN.md
  BILLABLE_PATH_INVENTORY.md
  PROVIDER_USAGE_MAPPING.md
  E5_PRELIVE_NO_KEY_REPORT.md
  E1_E2_E3_LIVE_REPORT.md               # 仅批准后填写
  E4_PAIR_REPORT.md                     # 仅有数据后填写
  E5_FULL_REPORT.md
  ADR-001-runtime.md                    # 仅签核新版本后更新结论
artifacts/
  m0-closeout-baseline/
  m0-closeout-fix-tests/
  m0-runtime-integration/
  m0-egress-validation/
  live-m0/                              # 仅批准后生成，敏感文件受控
src/autoteacher_m0/
  accounting/                           # 保留现有 Broker/Ledger；有限修改
  runtime/                              # 保留唯一 SDK Adapter
plugins/runtime-budget-guard/          # 修复原插件，不重写为第二套
scripts/
  verify_runtime_profile.*              # 受限验证，非开 Live 的隐藏开关
  verify_egress_policy.*
tests/
  unit/
  integration/
  security/
```

### 11.1 交付检查清单

- [ ] PR0：核对 SHA、补充 Ledger/Usage/测试/Profile 审计，给出真实的差异清单。
- [ ] PR1：F1–F6 对应定向测试和语义修复，通过后无 Key 独立复核。
- [ ] PR2：目标 Runtime 同时加载插件并通过 Guard 缺失/恶意 Provider 负测。
- [ ] PR3：可信 Controller 设计、凭据模拟、外部 watchdog 与无 Key 安全负测。
- [ ] PR4：billable path inventory、外部 egress/预算控制证据。
- [ ] 维护者独立审批冻结版本、真实凭据和明确时间/费用上限。
- [ ] PR5：获批主路由 C 层 E1/E2/E3 真实调用、Session、Tool、Usage/成本证据。
- [ ] PR6：E4 六对 Live 对照、E5 完整强制验收。
- [ ] PR7：独立审计、各项真实状态、最终 ADR，不覆写历史。

**终点原则**：当 PR5–7 完成，我们评估的是“这个 Harness 在固定配置下是否足够可靠、安全且可维护，值得继续做 M1 Teacher”，而不是证明 DSH 本身绝对安全，也不是证明教学策略有真实学习收益。
