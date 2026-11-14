# M0 收尾 PR0 — 源码发现 F1–F10 固化（静态审计，基线 `7c3806b`）

- 版本：PR0-v1（2026-11-14 UTC）
- 执行者：`verify2`（独立非实现者；PR0 只做静态核对与文档/证据固化）
- 审计对象：仓库 `/root/Autonomous Teacher`
  - **最新文档归档 HEAD**：`7c3806b58af2bd49328bdd9bcc53e858a13c35e5`（“docs: archive independent phase-five audit and errata corrections”，父 `feb7118`）
  - **历史冻结实现**：`feb7118f9aff20c681cc651812b30315288080f1`（代码实现身份；本 PR0 不改写）
  - 引导文档：[Autonomous_Teacher_M0_Closeout_Review_and_Implementation_Plan_v0.5](<Autonomous_Teacher_M0_Closeout_Review_and_Implementation_Plan_v0.5.md>)
    （sha256 `b3d85071…`，未跟踪、原字节保留）
- **方法**：只做仓库源码静态阅读 + 独立 `sha256sum`/Git 身份核对；**未运行**项目 Python/pytest/TS、未启动容器、未访问网络/真实凭据、未读真实 Key。所有结论是**源码级确认**，不是运行 PASS；未知/需运行时证据的项标 `UNVERIFIED`，不得据此声称已突破预算或 Live 通过。
- 原始基线证据：[`artifacts/m0-closeout-baseline/`](../artifacts/m0-closeout-baseline/)（`manifest.json`/`manifest.sha256`/`commands.jsonl`/`source-inventory.tsv`/`outputs/`）。

## 0. 基线与源码身份（独立复算）

| 项目 | 值 |
|---|---|
| Git HEAD | `7c3806b58af2bd49328bdd9bcc53e858a13c35e5`（commit date `2026-11-14 12:38:05 +0000`） |
| HEAD tree | `acd3f10f5ddeaad5a298d6b969210cca5881f134` |
| 冻结实现 | `feb7118f9aff20c681cc651812b30315288080f1`（tree `aff0b64f…`；HEAD 父提交） |
| 工作树 | 仅 `?? docs/Autonomous_Teacher_M0_Closeout_Review_and_Implementation_Plan_v0.5.md`；tracked 无改动 |
| tracked 文件 | 122（src 33 / tests 18 / config 3 / plugins 29 / scripts 6 / fixtures 4 / docs 22 / 根文件 7） |
| `feb7118..HEAD` 变更 | 仅 6 个 docs 文件（M 5 + A `docs/REVIEW_PHASE5.md`）；**无 src/tests/config/plugins/scripts/锁变更** |
| v0.5 文件 | 47 127 bytes，sha256 `b3d85071ba883892cbe6863aefa2240ae7df9d962b15b4eab9c7f90a5d08675b` |
| 源码清单 | `artifacts/m0-closeout-baseline/source-inventory.tsv`（122 行，sha256 `6d6b9e50…`） |

**v0.5 §0.1 引用的 4 个源码哈希独立复算（全部匹配仓库实际值）：**

| 文件（仓库实际） | v0.5 声明 | 仓库实际 sha256 | 匹配 | 冻结 `feb7118` blob |
|---|---|---|---|---|
| `plugins/runtime-budget-guard/src/index.ts` | `1ccdb658…` | `1ccdb658413b06ed5ae5c625ae86b2487fd7a6af33abaff941332c6fdf5f1ba3` | ✅ | 同（未变） |
| `src/autoteacher_m0/accounting/broker.py` | `9dce2f93…` | `9dce2f9397fa5e91d387af7422f94d81ba7116f94923cced55269e9a0b2fc3d3` | ✅ | 同（未变） |
| `src/autoteacher_m0/runtime/dsh_adapter.py` | `88891149…` | `888911490c936dff286af5ad823aae1007d88ab50213986c4b809d34b44cc68a` | ✅ | 同（未变） |
| `docs/RUNTIME_BUDGET_GUARD.md` | `1d0b62a2…` | `1d0b62a23695020d5f7216f345d43942d05695e520c86603bb66e62dab56f11d` | ✅ | `8fa03fbe…`（frozen 后经 task30/31 授权 errata 更新；HEAD 已归档） |

> 结论：v0.5 引用的 4 个哈希与仓库一致；其中 docs 哈希对应归档后的 task30/31 errata 版本（HEAD `7c3806b`），不是 `feb7118` 冻结 blob。冻结实现代码文件未变。

## 1. 状态与优先级定义

- **CONFIRMED**：仓库源码直接可证（行为/顺序/缺失）→ 本 PR0 已确认。
- **CONDITIONAL**：源码行为成立，但安全/账本影响依赖未确认的外部条件。
- **UNVERIFIED**：需目标运行时/Live/原始 wire/部署权限证据，本 PR0 无法静态确认。
- **severity**：P0=阻断 Live；P1=进入 Live 前应处理或形成受测限制；P2=可延后 M1。**PR0 离线范围不存在 P0 代码缺陷阻断**；P0 只针对未来 Live 声称。
- 本 PR0 不写任何 PASS；表中 `UNVERIFIED` 保持未知。

## 2. F1–F10 汇总表

| ID | 标题 | v0.5 分类 | 本 PR0 状态 | Severity | v0.5 §6 回归 ID | 建议 owner | 改历史？ |
|---|---|---|---|---|---|---|---|
| F1 | 重试归因被硬编码 `retry:false`；steps/retry 语义 | Confirmed/账本 Conditional | **CONFIRMED** | P1 | T-RETRY-01, T-RETRY-02 | Accounting + Guard-plugin（PR1） | 否（新增测试/最小 diff） |
| F2 | Journal 配额先于 op 检查，可能阻塞既有 PENDING 收尾 | Confirmed/阈值 Conditional | **CONFIRMED** | P1 | T-JOURNAL-01/02/03 | Accounting（PR1） | 否（需 v1 兼容/版本化） |
| F3 | 后置 request digest，不能作为真实费用上限 | Confirmed | **CONFIRMED** | P0(Live)/P1(离线) | T-MUT-01/02 | Security/Controller（PR3/PR4）+ Guard 文档（PR1） | 否 |
| F4 | `SETTLE_UNCERTAIN` 只 log+shutdown，无立即 latch/不向上传递 | Confirmed | **CONFIRMED**（即时 latch 属性 UNVERIFIED） | P1 | T-SETTLE-01/02 | Accounting + Guard-plugin（PR1） | 否 |
| F5 | `encodeTaskId()` 非单射，可碰撞 | Confirmed/影响 Unverified | **CONFIRMED**（碰撞静态可证；真实 Session 碰撞 UNVERIFIED） | P1 | T-ID-01/02 | Guard-plugin（PR1） | 否（新 reservation 用新 ID） |
| F6 | Broker 故障日志固定“未派发”并转发未净化 stderr/诊断 | Confirmed/Key 泄漏 Unverified | **CONFIRMED**（行为；真实 Key 泄漏 UNVERIFIED） | P1 | T-LOG-01/02 | Guard-plugin（PR1） | 否（旧日志不改） |
| F7 | 仅靠 Guard 插件无法证明“缺插件时不可发包” | Confirmed（架构缺口） | **CONFIRMED 限制**（外部边界仍缺失） | P0(Live) | T-BOOT-01/02/03 | Security/Controller（PR2/PR3/PR4） | 否 |
| F8 | Guard 读配置→spawn→Broker 再读的 TOCTOU 时序 | 时序 Confirmed/可利用性 Unverified | **CONFIRMED 时序**（可利用性 UNVERIFIED） | P1 | T-BOOT-02（+T-BOOT-03） | Runtime + Security（PR2/PR3） | 否 |
| F9 | Adapter 的 Usage/模型/request ID 全 None；错误分类未校准 | Confirmed/真实 wire Unverified | **CONFIRMED 行为**（真实映射 UNVERIFIED） | P1 | T-USAGE-01/02 | Runtime + Accounting（PR3/PR4） | 否 |
| F10 | 无 Live 总 watchdog/进程树清理证据 | Confirmed | **CONFIRMED 缺失**（Live 要求 UNVERIFIED/BLOCKED） | P1 | T-WD-01/02 | Runtime + Security（PR3） | 否 |

> F1/F2 从 v0.5 的 “Conditional” 升级为 **CONFIRMED**：原因不是上传副本，而是本仓库已包含 `ledger.py`、`budget.py`、`broker.py`、`broker_usage.py`、`tests/`；下节直接引用仓库行号。**注意：静态确认 ≠ 运行 PASS；未运行任何测试。**

---

## 3. F1 — 重试归因硬编码与 steps/retry 真实语义（CONFIRMED，P1）

**代码证据（仓库行号）**
- Guard 的 reserve 请求固定 `retry: false`：`plugins/runtime-budget-guard/src/index.ts:402-409`（`retry: false` 在 408 行）。
- Broker 校验并原样转发 retry：`src/autoteacher_m0/accounting/broker.py:151-163`（要求 `retry` 为 bool）、`183-190`（`retry=request["retry"]` 传入 ledger）。
- Ledger 真实语义：`src/autoteacher_m0/accounting/ledger.py:161-162` 用 `sum(row["task_id"] == task_id for row in rows)` 计 **steps**、仅对 `row["retry"]` 为真的行计 **retries**；`173-176` 先判 `steps >= max_steps`（“task step limit (retries included)”），再判 `retry and retries >= max_retries`。
- 与内存版 `BudgetGuard` 一致：`src/autoteacher_m0/accounting/budget.py:97-100`、`111-113`（step 计数包含 retry，retry 另计）。
- 冻结配置：`config/budgets.yaml:7-8`（`max_steps_per_task: 8`、`max_retries_per_task: 1`）；默认值 `budget.py:26-27`。
- Guard 的 `task_id` 来自 Session：`index.ts:329`、`index.ts:334-337`（`encodeTaskId(sessionId)`）→ 在 guard 路径下 `max_steps` 实际是**按派生 session task_id 的逻辑调用总上限**（不是每个 agent-run 单独计数，且 conversation/compaction/judge/tool 往返共享）。
- 现有测试佐证（未运行，仅静态阅读）：`tests/unit/accounting/test_ledger.py:138-150`（step 包含 retry 行、retry 单独计）；`tests/unit/accounting/test_accounting.py:82-94`；`tests/unit/accounting/test_broker.py:350-358`（转发 request/step/retry caps）。

**实际影响与量级（静态推导）**
- 由于 guard 恒 `retry:false`：`max_retries=1` 在 guard 路径下**永不被消耗/限制**；真实 retry 只会作为新 stream 再次 reserve，因此按 step/request 计入，**不会产生无预留 dispatch、也不会额外免费额度**。
- `max_steps=8` 是每个 guard 派生 task_id（≈Session）的总 logical-stream 上限：8 次 reserve 后第 9 次 `BudgetExceeded("task step limit (retries included)")`；随后 broker 把**整个 scope** `blocked=1`（`broker.py:191-194`，`ledger.py:165-166` 先查 blocked），后续所有 session/stream 被拒。方向 fail-closed，不会超预算；风险是可用性/语义与文档声明不一致。
- 结论：F1 不是“免费重试超支”风险；是**归因/限额语义错误 + 声明不可信**。修复必须按 v0.5 方案 A（M0 推荐：禁用 provider 内部自动重试，所有 logical stream 都计入统一 step/request 上限），或按方案 B 引入可信 attempt metadata（不能由候选/学生输入自报）。

**最小修复建议**：方案 A（M0 推荐）：显式把真实 provider 的重试策略固定在 `mode!=always && maxRetries<=0/1`，并在文档/报告中删除“通过 retry 字段精确限制内层 retry”的说法；在 guard/ledger 文档写明 steps 是 per-session/逻辑调用口径。方案 B 需先定义 `attempt_id/logical_call_id/attempt_index` 协议并保持 broker v1 兼容。
**回归**：T-RETRY-01、T-RETRY-02（另建议加“第 9 次同 session 调用被拒且 scope blocked 单调”用例）。
**历史**：不改历史；新增测试/字段，旧 fixture 保持可复验。
**残留 UNVERIFIED**：真实 Provider SDK 内部隐藏 retry 的实际行为（无 Live）。

---

## 4. F2 — Journal 消息配额先于 op 分派（CONFIRMED，P1）

**代码证据**
- `broker.py:174-180`：`_operate()` **先**统计 `budget_broker_messages` 数量，`count >= max_messages` 立即 `MESSAGE_LIMIT`，之后才区分 `snapshot/reserve/settle/fail`。
- 每条新消息占一行 journal：`ledger.py:121-139`（`journal_once` 插入一条 `budget_broker_messages`）；duplicate 不新增行。
- Broker 配置上限：`broker.py:97-99`（`max_messages > 100_000` 直接拒绝启动）。
- Guard 只做形状/上界校验：`index.ts:233`（`positiveInt(..., 1_000_000)`）——**允许到 1 000 000，但 Broker 实际硬上限 100 000**；落在 (100 000, 1 000 000] 的配置通过 guard 校验后在 broker 启动时 `STARTUP_BLOCKED`（fail-closed，但配置语义不一致）。
- 测试/运行配置：`tests/unit/accounting/test_broker.py:15` 与 `tests/integration/budget_bridge/test_stdio.py:15` 均 `max_messages: 4096`；第五阶段 guard 运行 stage 的 configs 也为 4096（见 `artifacts/runtime-budget-guard/stage/rbg/configs/*.json`，外部证据）。
- 现有 journal cap 测试：`tests/unit/accounting/test_broker.py:385-393`（`max_messages=1` 时第一条 reserve 成功、新 reserve → `MESSAGE_LIMIT`、重放不重新派发、pending 仍为 1）——**只覆盖“新 reserve 被拒/重放安全”，未覆盖 cap 后对既有 PENDING 的 settle/fail/snapshot**。

**实际影响与量级**
- 每个 reserve/settle/fail/snapshot = 1 条 journal 消息；因此 cap 后**已有 PENDING 的合法完成操作与观测查询都会被 `MESSAGE_LIMIT` 拒绝**（静态可证）。后果是 pending 占预算无法正常收尾、对账完整性/可用性风险；不是直接超支。
- 量级：测试配置 4096 条 journal；最小 stream=2 条（reserve+settle），≈2048 个逻辑 stream。冻结 ledger 上限 `max_requests=50`（`config/budgets.yaml:6`）→ 单 scope 最多 50 个 reservation ≈100 条消息，远低于 4096；guard 本身不发 snapshot。因此**在冻结 limits 下单 scope 实际上很难触达 4096 的 journal cap**（约 40 倍余量）；风险主要在：提高 request 上限、长期复用同一 scope/快照轮询、或自定义配置。Broker 的 100 000 硬上限与 guard 1 000 000 上界不一致是确定缺陷。
- 若在 Live 前把 `max_requests` 提到 4096/更高，或外部 Controllor 做 snapshot 轮询，F2 会变成真实可用性/对账问题。

**最小修复建议**：按 v0.5：把“新建 reservation 容量”与“既有 reservation 完成容量”分离；reserve 进入前为未来 settle/fail 保留至少 1 个 journal slot；snapshot 可读性与 reserve 配额隔离并有频率/大小/存储上界；重复完成保持幂等；统一 guard/broker 的 `max_messages` 实际可用上界（或显式版本/能力握手）。
**回归**：T-JOURNAL-01、T-JOURNAL-02、T-JOURNAL-03。
**历史**：不覆写历史；若修改 broker 协议需 `protocol_version`/capabilities 并保留 v1 兼容 fixture（phase5 148 broker 回归仍可复验）。
**残留 UNVERIFIED**：不同 max_messages/limits 组合下的真实运行时行为（本 PR0 未运行）。

---

## 5. F3 — 后置请求摘要不是真实费用上限（CONFIRMED，P0 Live / P1 离线）

**代码证据**
- `index.ts:340-349` `requestDigest()`：仅对 `provider/model/messages/system/tools/toolHistory/maxTokens/sessionId/purpose/stop` 计算 SHA-256；**不覆盖** retry policy、endpoint、完整 SDK/transport 参数等。
- 中间件顺序：`index.ts:615-635` 先 `broker.reserve(...)`，再 `next()` 并迭代；**流结束后**（631-635）才重新计算 digest 比较并记 `IMMUTABILITY_VIOLATION`。
- 预留上界来自准入时参数：`index.ts:269-288`（input bound UTF-8 bytes+256）、`index.ts:300-301`（outputBound=options.maxTokens）；reservation 在 provider 之前提交。
- 结算侧不重新执行 per-call 上限：`ledger.py:191-226`，只在 `exceeded` 时置 `blocked=1`（未来请求），已发生的超出照实记录（不可回滚）。

**实际影响与量级**
- 下游恶意/缺陷 middleware 可在 guard 准入后修改 `maxTokens`、provider/model 之外可影响请求的字段（或加入 Files/attachments、换 endpoint 等等），**真实请求可能已发出并计费**，digest 只做事后检测；预存 worst-case 仅按原上界，**不能保证覆盖修改后成本**。单次被篡改 dispatch 的理论超支上限由下游修改幅度/Provider 计费决定，guard 无二次硬切。
- 这是“检测”不是“事前约束”；与 v0.5 P0 一致：**Live 前必须有更靠近发包点的已审查 Adapter/egress/Key 边界或可信 Controller 创建不可变参数**。当前离线 synthetic 无真实费用影响，不能把 selftest 的 mutation detection 当 Live 费用上限。
- 现有 selftest 只验证“事后检测+当前 stream worst-case settle”（V1 已关闭的措辞即如此）；**未验证 provider 前拦截**。

**最小修复建议**：按 v0.5 §PR4：Provider 发包前在已审查的 Adapter/egress 做只读白名单/参数复核；可信 Controller 生成不可变参数；digest 保留为审计而非唯一防线；若 dispatch 后被篡改，标记 `REQUEST_INTEGRITY_UNCERTAIN` 且不记成功验收。
**回归**：T-MUT-01、T-MUT-02。
**历史**：否（新增审计/边界层；旧日志不改）。
**残留 UNVERIFIED**：真实 SDK/transport 最终发送参数、Provider 内部 Files/retry 行为。

---

## 6. F4 — `SETTLE_UNCERTAIN` 未向上传递且无立即 latch（CONFIRMED；即时 latch UNVERIFIED，P1）

**代码证据**
- `index.ts:422-439` settle 只对 `reply.ok && code∈{SETTLED,FAILED}` 视为成功，否则抛 `GuardUnavailable("RBG_SETTLE_REJECTED_...")`。
- `index.ts:640-651` `finally` 中捕获 settle 异常：`log('SETTLE_UNCERTAIN', ...)` 后 `await broker.shutdown()`，**不重新抛出**；流本身可能已正常结束 → 上层可能看到成功。
- `shutdown()`（`index.ts:441-455`）设置 `#shuttingDown=true`、拒绝 pending、关闭 stdin，1.5s 后 SIGKILL；但**没有设置 `#unavailable`**。`#unavailable` 只在 `#fail()`（`index.ts:566-568`）设置；`request()` 只检查 `#unavailable`（391-395），`#send()` 只检查 child 存在/`#unavailable`（531-533）。
- 因而下一条 stream：`reserve()`→`#ensureStarted()`（`#started` 仍 true）→`#send()` 向已 end 的 stdin 写 → error 回调（543-549）→`#fail()` 设置 unavailable。**方向 fail-closed，但不是 shutdown 时立即生效的显式 latch**，依赖异步写错误路径；若上层只看模型结果，可能漏掉 accounting 状态。

**实际影响与量级**
- 已预存 reservation 保持 PENDING（不退款，预算仍占用）；`SETTLE_UNCERTAIN` 只写 guard stderr，不是机器可解析的 RunRecord/accounting_status。模型流成功与账本结算失败可能被上层混同。
- 现有 phase5 证据：s10 硬 SIGTERM 只证明“已预存 reservation 不退”，未证明所有 settle 异常时序下上层验收正确；selftest 只验证 abort 的 worst-case settle。

**最小修复建议**：按 v0.5：拆 `model_completion_status` 与 `accounting_status`（`RESERVED/SETTLED/WORST_CASE_HELD/SETTLEMENT_UNCERTAIN`），机器可解析地交给可信 Controller；结算不明不得记 Run PASS；下一 dispatch 立即拒绝（显式 broker lifecycle latch，区分正常 shutdown）；PENDING 不释放。
**回归**：T-SETTLE-01、T-SETTLE-02。
**历史**：否。
**残留 UNVERIFIED**：真实运行时 latch 是否在所有 settle 失败时序下立即可见；broker ack 丢失/重启竞态。

---

## 7. F5 — `encodeTaskId()` 非单射（CONFIRMED；真实 Session 碰撞影响 UNVERIFIED，P1）

**代码证据**：`index.ts:334-338`
```ts
const cleaned = sessionId.replace(/[^A-Za-z0-9_.:-]/g, '_').replace(/^[^A-Za-z0-9]+/, '')
const payload = (cleaned || 'session').slice(0, MAX_SESSION_ID - 4)   // 92
return `rbg-${payload}`
```
**碰撞例（静态可证）**
- `a/b` → `a_b`；`a_b` → `a_b` → **同一 task_id**。
- `-x` → `_x` → 去前导 → `x`；`x` → `x` → 同一。
- `é`/`è`/`/` 等全非法字符 → cleaned 空 → fallback `rbg-session`；多个不同 Session 全部碰撞。
- 任意两个 Session 前 92 个规范化字符相同 → 截断后碰撞；`:`、`.`、`-`、`_` 与非法字符替换也会混淆。

**实际影响与量级**
- 碰撞后 ledger 用同一 `task_id` 统计 `steps`/`retries`（`ledger.py:161-162,173-176`）→ 不同 Session 共享 8-step/1-retry 预算归因，可能**过早拒绝**（fail-closed，不会超预算），DB 行归因错误；scope 级 blocked 一旦触发影响所有 session。
- 真实 Session ID 是否实际产生碰撞未验证（需目标 Runtime 的 Session 命名规则）；但代码层面的映射显然有损，不能作为“稳定唯一 ID”。

**最小修复建议**：用固定前缀 + `sha256(canonical session identity)` 的短摘要（如 64 hex），或使用可信 Session 记录中的稳定 ID；区分 Session Identity 与 Run/Attempt Identity；保持 broker `_ID` 长度约束（`broker.py:21` 96 字符）。
**回归**：T-ID-01、T-ID-02。
**历史**：不改旧 reservation；新 reservation 可用新 ID。
**残留 UNVERIFIED**：真实 Session ID 的实际形式/碰撞概率。

---

## 8. F6 — 故障日志固定“未派发”并转发未净化诊断（CONFIRMED；真实 Key 泄漏 UNVERIFIED，P1）

**代码证据**
- `index.ts:566-578` `#fail()`：无论故障发生在 reserve 前、provider 迭代中还是 settle 阶段，都 `log('UNAVAILABLE', { reason, reservations_not_dispatched: true })`——**固定宣称**所有 reservation 未派发。
- `reason` 可能包含下游错误文本：`474`（spawn error message）、`486`（child error message）、`488`（exit code/signal）、`538`（timeout）、`548/555`（write failed），`log()`（364-366）原样写 stderr。
- Broker 子进程 stderr 被原样缓存并转发：`index.ts:481-485`（最多 64 行、每行截 512 字符）；`#fail` 时 `BROKER_DIAGNOSTICS` 输出 `stderr_lines`（573-575）。
- 另外 `RESERVE` 日志原样记录 `session_id`（`index.ts:414-418`），可能含个人可识别信息。

**实际影响与量级**
- 公开/证据日志中可能出现 broker Python traceback、路径、下游错误 message、Session ID；当前无 Live/Key，**未验证**是否含 Key 或敏感凭据，但按静态风险应视为未净化诊断。固定 `reservations_not_dispatched: true` 在 provider 已运行后的 settle 故障中语义错误，会误导审计归因。
- 量级：最多 64×512 字节/次 fail；不影响预算安全，但影响事故判定/脱敏合规。

**最小修复建议**：按 v0.5：机器状态 `phase=BEFORE_DISPATCH|DISPATCHED|SETTLING|UNKNOWN` + 单调计数/`reservation_id`；对外只导出 allowlist 错误码/数字/布尔/哈希化 ID；原始 stderr 仅受限诊断区并做密钥哨兵测试；`session_id` 公开审计用哈希。
**回归**：T-LOG-01、T-LOG-02。
**历史**：旧日志不可改；新日志字段变更需在 manifest 记录。
**残留 UNVERIFIED**：真实 error/stderr 中是否含 Key/私有数据（无 Live）。

---

## 9. F7 — Guard 插件无法覆盖“模块根本没加载”（CONFIRMED 架构缺口，P0 Live）

**代码/文档证据**
- Guard 的 `apply()`（`index.ts:587-654`）只能在模块被调用时：config 失败则注册 deny-all middleware（591-600）；成功则注册真实 middleware（615-653）。
- **模块 import/加载失败时 `apply()` 不会执行**，插件无法自救；文档已承认：[RUNTIME_BUDGET_GUARD](<RUNTIME_BUDGET_GUARD.md>) §2（第 50 行）“若 apply 的 config/hash/policy 校验失败，插件不抛异常退出（上游 loader 会记录 warning 后继续，导致无守卫运行），而是注册 deny-all middleware”；§7 第 3 条（190-192 行）“插件模块 import 失败（语法/加载错误）上游 loader 会 warning 后继续；本插件对 config 错误已 fail-closed，但无法阻止 loader 跳过整个模块的极端情况。集成必须显式断言 RBG_BOOT（或 deny-all BOOT_INVALID）后才能放行 traffic”。
- 当前仓库没有外部 egress/Key 边界实现：LiveGate 恒 BLOCKED（`src/autoteacher_m0/security/gates.py:63-86`），`scripts/run_live.sh:1-5` 直接 exit 3；无真实 Key/网络控制层。

**实际影响与量级**
- 仅靠 guard 插件无法证明“缺插件时无法发包”；若 DSH 进程能直接访问真实 Key/外网，loader 跳过插件即无预算前置。对 Live 是 P0 架构阻断；离线 synthetic 无费用影响。
- 上游 loader 的“warning 后继续”行为来自文档/上游实现描述，本 PR0 未独立复验（node_modules 不在 tracked 源码）→ 该细节标记为文档依据；但“插件不能控制自身未加载”是确定架构事实。

**最小修复建议**：按 v0.5：独立于 DSH 的可信 Live Controller/egress/Key Broker 为第二层；DSH 无真实 Key、默认禁网/只能访问获批 proxy；真实放行前检查目标 Profile 的插件注册/版本/`RBG_BOOT` 或 BOOT_INVALID，并做 Guard 缺失负测；不能仅凭进程自报 `RBG_BOOT` 当 attestation。
**回归**：T-BOOT-01/02/03（外部 egress 可观察证明）。
**历史**：否（新增外部边界/负测）。
**残留 UNVERIFIED**：上游 loader 实际行为、目标 Runtime 的插件加载失败模式；无外部边界则 Live 保持 BLOCKED。

---

## 10. F8 — Guard“读配置→spawn→Broker 再读”的 TOCTOU 时序（CONFIRMED 时序；可利用性 UNVERIFIED，P1）

**代码证据**
- `parseConfig()` 在 apply 时调用 `readFixedBrokerPolicy`（`index.ts:207`）；`readFixedBrokerPolicy`（`index.ts:211-266`）用 `readFileSync(path)` 读取、算 sha256、与 `configSha256` 比对、解析并记录 `fixed`（scope/dbPath/limits/route）。
- 之后才懒启动：`#ensureStarted()`（`index.ts:457-472`）`spawn(this.config.python, [... '--config', this.config.configPath], {cwd, env, shell:false})`；Broker 进程在 `broker.py:276-285` **再次** `Path(args[1]).open("rb")` 读取同一路径。
- 若两次读取之间文件被替换：guard 已校验旧字节，broker 启动读到新字节。Broker 的 DB 策略绑定（`ledger.py:99-119`，policy_json 必须与既有 DB 一致）可缓解：**已有 DB 且 policy 不同 → broker `ValueError` → `STARTUP_BLOCKED`（fail-closed）**；仅当 DB 不存在/路径被换时可让新 policy 生效。
- 缓解依赖部署：config/父目录必须可信只读挂载、候选不可写；当前 phase5 用 `ro=true` 挂载（见 phase5 argv/日志），但 Live 部署的只读性未验证。

**实际影响与量级**
- 时序确定存在；可被利用的前提是“攻击者能在 apply 后、spawn 前写 config 路径/替换文件且目标 DB 为新建/可换”，这属于部署权限假设，未验证。影响可能是替换 limits/scope（抬高预算）或让 broker 启动失败；guard 不会在 spawn 后再次校验实际 broker 读取的字节。
- 当前无 Live Key，离线阶段影响有限；对 Live 是 P1（缓冲/只读挂载可消除）。

**最小修复建议**：按 v0.5：固定只读挂载 + 部署侧校验文件/父目录身份；可选地把已校验的只读字节/fd 通过受控通道传给 Broker，消除双读竞态；外部 Controller 记录挂载身份与 SHA。
**回归**：T-BOOT-02（含 T-BOOT-03）。
**历史**：否。
**残留 UNVERIFIED**：Live 部署的实际只读/权限边界。

---

## 11. F9 — Adapter 的 Usage/模型/请求 ID 与错误分类（CONFIRMED 行为；真实 wire UNVERIFIED，P1）

**代码证据**
- `src/autoteacher_m0/runtime/dsh_adapter.py:58-93` `normalize_result`：`input_tokens=None`、`output_tokens=None`、`estimated_cost_usd=None`（86 行）；metadata `actual_model_version=None`、`provider_request_id=None`（88-89 行）；`usage_kind: "unavailable"`、`cost_kind: "unknown_not_zero"`（92 行）。
- `dsh_adapter.py:23-40` `classify_error`：仅处理 `RuntimeFailure`、`TimeoutError`、HTTP-shaped `status_code` 401/403/429/5xx；否则 `SDK_ERROR`；注释 32-33 行明确“SDK RPC error codes need a captured wire fixture before mapping; arbitrary JSON-RPC codes are not HTTP statuses”。
- Live 入口不可达：`HarnessAdapter._require_live_authorization()`（101-106 行）恒抛 `SECURITY_BLOCKED`；`run()`（125-145）开头即调用，故 **没有真实执行路径**。
- `sdk_options`（43-55 行）只传 SDK 选项，不含预算/Usage 集成。

**实际影响与量级**
- 当前项目核心 RunRecord 不含真实 Usage/模型版本/请求 ID；任何“真实 usage/账单”验收在 F9 修复前无法完成。错误分类面对真实 SDK JSON-RPC 错误码会落到 `SDK_ERROR`，无法区分 401/429/5xx/timeout；离线 HTTP-shaped 注入只证明映射函数形状，不是真实 wire 语义。
- 影响：Live 账单核对/错误归因不可行；对 M0 决策是 P1（进入 Live 前必须补 ProviderObservation/真实 wire 证据）。

**最小修复建议**：按 v0.5：在保留无 SDK 类型泄漏前提下新增标准 `ProviderObservation`（requested/observed route、model_reported、provider_request_id、usage_raw_hash、input/cache/output/reasoning、cost_estimate/source、error_kind、complete/uncertain）；无字段保持 None（不填 0）；真实事件在可信隔离存储并脱敏；用真实 Provider 账单核对。
**回归**：T-USAGE-01（B：缺 Usage）、T-USAGE-02（C：真实 cache/reasoning 字段）。
**历史**：否（新增字段/模块；旧 RunRecord 兼容）。
**残留 UNVERIFIED**：目标 SDK 实际 wire 字段/错误码、真实 Provider usage/账单。

---

## 12. F10 — 缺 Live 总 watchdog 与进程清理证据（CONFIRMED 缺失；Live 要求 BLOCKED，P1）

**代码证据**
- `src/autoteacher_m0/runtime/dsh_adapter.py:50-51` `sdk_options` 传 `request_timeout_seconds`（单请求超时），不是总运行上限。
- `dsh_adapter.py:125-130` `run()` 注释明确：`request_timeout_seconds is NOT a total activity bound. Before unlocking, add an independent external process watchdog and reserve worst-case cost.`；且该路径当前不可达（101-106/126 行 `_require_live_authorization`）。
- 仓库 `src/`、`scripts/` 无总 deadline/进程组 kill/watchdog 实现（grep 仅该注释与 offline 容器文档）；[THREAT_MODEL](<THREAT_MODEL.md>) 的 `podman --timeout`/outer timeout（THREAT_MODEL.md:94-95）仅是**离线容器**限制，不能替代 Live 总时限。
- Live 状态：`LiveGate` 恒 `BLOCKED`（`security/gates.py:63-86`），`scripts/run_live.sh` exit 3；`docs/SECURITY_APPROVALS.md:1-24` 明确无独立人类授权/凭据边界。

**实际影响与量级**
- Live 若直接接入 DSH Runtime/SDK，SDK hang、provider half-open、工具无限循环、broker deadlock 等无外部总时限/进程树清理 → 无法保证“超时后停止且不明费用保持 pending/worst-case”的验收；在无 watchdog 前任何 Live 都不应批准。
- 影响：P1（Live 前置），当前离线有既有容器 timeout 但**不能等同**。

**最小修复建议**：按 v0.5：可信 Controller 设定总运行时长、step/请求上限、进程树杀死、容器清理、账本 worst-case 保留；超时后不得重试同一不明状态 billable attempt；测试 SDK hung/半开/无限循环/broker deadlock/kill between reserve and commit。
**回归**：T-WD-01、T-WD-02。
**历史**：否。
**残留 UNVERIFIED/BLOCKED**：Live watchdog 与计费不确定性处理。

---

## 13. 跨发现不变量与量级速查

| 项 | 静态事实 | 量级/含义 |
|---|---|---|
| retry 归因 | guard `retry:false`；ledger steps 计数包含 retry 行 | max_retries=1 在该路径失效；8 次 logical stream/session 上限；第 9 次 → scope blocked（fail-closed） |
| journal | broker 先查 `max_messages` 再分 op | 测试配置 4096；broker 硬上限 100 000；guard 校验到 1 000 000（不一致）；冻结 `max_requests=50` 时约 100 消息/scope，4096 有约 40× 余量；cap 后既有 pending 的 settle/fail/snapshot 都会被拒 |
| digest | 流结束后比较，字段有限 | 非事前拦截；被篡改请求可能已计费；Live 必须外置发包边界 |
| settle 失败 | 只 log SETTLE_UNCERTAIN + shutdown；`#unavailable` 不在 shutdown 设置 | 不向上传递；无立即 latch；下一条请求靠写错误路径 fail-closed |
| task_id | 字符替换+截断+前缀 | `a/b` 与 `a_b` 碰撞；不同 Session 可共享 step/retry 归因（fail-closed 方向） |
| 故障日志 | 固定 `reservations_not_dispatched:true`；stderr 原样转发 | 语义可能错误；Key 泄漏未验证；session_id 原样记录 |
| Guard 缺失 | 模块加载失败时 apply 不执行 | 需外部 egress/Key 边界；Live P0 |
| TOCTOU | apply 读哈希 → spawn → broker 再读 | 已有 DB 时策略绑定可 fail-closed；新建 DB/可写路径可能被替换 |
| Usage | Adapter 全 None；错误分类仅 HTTP 形状 | 真实 wire/账单未验证；Live 账单不可核 |
| watchdog | 无总时限/进程树清理 | Live 不可批准；离线容器 timeout 不可替代 |

**明确不声称**：本 PR0 没有运行测试，没有产生/突破任何真实预算，没有 Live/真实模型/真实 Usage；所有“实际影响”是源码静态推导，运行验证留给 PR1–PR5 的定向测试与独立复核。

## 14. 建议裁定（交 Lead/维护者，详见 OPEN_QUESTIONS）

1. F1 选方案 A（M0 推荐）还是 B（需协议/attempt metadata）——影响 PR1 设计与 broker v1 兼容。
2. F2 容量语义/上限统一方案（完成配额 vs 新请求配额；guard/broker `max_messages` 取值）。
3. F3/F7 外部 egress/Key 边界是否可实现；不可实现则 Live BLOCKED，必要时技术 NO-GO 候选。
4. F8/F10 部署只读与总 watchdog 由谁（Controller/维护者）提供与验证。
5. E5 范围（跨机 OCI/全平台）需维护者显式裁定（见 OPEN_QUESTIONS）。
6. PR1 回归测试入库与提交策略。

---
*证据索引：`artifacts/m0-closeout-baseline/manifest.json`（基线身份/命令 argv+exit/哈希）；本文件所有 file:line 均基于 HEAD `7c3806b` 的 tracked 源码（实现文件与 `feb7118` 相同）。*
