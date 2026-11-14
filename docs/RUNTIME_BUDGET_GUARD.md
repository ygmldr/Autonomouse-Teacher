# Runtime budget guard — logical-stream pre-dispatch middleware（第四阶段 task22）

## 0. 结论与边界（先读）

本文件记录一个**真实公开 Cordis 插件**及其无 Key/禁网/非 root/只读/cap0/nnp/cgroup
受限容器内的联调证据：`plugins/runtime-budget-guard/` 在全局 `llm/stream` waterfall
最外层、provider 调用/迭代之前，向固定 scope 的 stdio bookkeeping broker 预留；只有
`dispatch_allowed=true` 才调用 `next()`；`finally` 对每个唯一 reservation 结算一次。
脚本化 fixture provider/orchestrator 与真实锁定 DSH Runtime/真实 Python SDK/RPC、真实
`skill_lookup` 工具注册链路一起运行；**没有真实模型、没有真实 Key、没有 HTTP、没有
LiveGate/生产路由改动**。

必须精确区分：

- 守卫是**logical stream 级**预留：一次 `ctx.llm.stream` dispatch = 一次 reservation。
  它**不是**对 provider 库内部 HTTP/wire 的每次计费 attempt 的保证；底层 transport 的
  隐藏 retry/二次 POST 未被本插件观测或拦截。
- text-only/拒绝 image/file/attachment 只是**关闭 Files 路径的前提**（让候选不产生
  文件内容、不触发 provider 的 Files 上传路径）；公开证据不证明底层 transport 无额外
  POST。
- broker 是 fixed-scope **bookkeeping**：`dispatch_allowed` 不是人类授权、不是 Key
  代理、不是 provider usage 认证、不能打开 Live。
- SDK fixture 的 usage（7/3 等）是 synthetic fixture 常量；settlement 金额是合成账本
  数字，不是真实账单。
- 本任务**不**代表 task22 的预算桥已接入生产/运行中 provider 循环；它是候选中间件 +
  离线证据，仍需集成冻结与独立审计。

## 1. 分层（A/B/C 不混用）

| 层 | 是什么 | 本任务证据 |
|---|---|---|
| A. 项目 Mock | 项目自身 MockRuntime/fixture 20 例等 | 未新增；沿用历史证据，未重标 |
| B. 真实引擎 + synthetic fixture | 锁定 DSH runtime 二进制 `1cc41d5a…`、真实 Python SDK 0.2.2rc2、真实 JSON-RPC/Session v4/工具注册；provider 是显式 `offline-test-only`/`fixture-v1`（15 次 sdk_run/16 次 synthetic invocation 的既有 17-case 证据） | 新中间件在真实 session 流上真实预留/结算（见 §6） |
| C. DeepSeek Live | 真实模型/Key/HTTP/生产 Adapter | **NOT RUN / BLOCKED**（`real_model_calls=0,http_calls=0`） |

## 2. 插件位置与顺序

`plugins/runtime-budget-guard/src/index.ts`（strict TS 5.9.3）导出 Cordis 插件
`name/inject=['llm']/apply`。`apply`：

1. 严格校验 profile 传入的固定 config（不是客户端消息）；
2. 读取 `broker.configPath` 字节、校验 `configSha256`、解析并核对 scope id /
   唯一 `offline-test-only`+`fixture-v1` route / price / fee / usage policy 与 guard
   policy 一致；
3. 懒创建**单个** broker 子进程客户端；注册 `ctx.effect` 在 dispose 时关闭 broker；
4. `ctx.on('llm/stream', async function* (options, next), { prepend: true })`。
   fixture provider 先加载、guard 后加载，因此 guard 的 prepend 位于 waterfall 最外层：
   真实运行 trace 中同一 stream 内 `RBG_RESERVE` 严格早于 `FIXTURE_INVOCATION`。

若 `apply` 的 config/hash/policy 校验失败，插件不抛异常退出（上游 loader 会记录 warning
后继续，导致无守卫运行），而是注册**deny-all middleware**：之后每个 stream 在 provider
之前 fail-closed（`RBG_GUARD_BOOT_INVALID`）。这被 selftest 的
`invalid-config-fail-closed` 实际验证（provider invocation=0）。

请求不可变性：处理前计算完整 request digest；`next()` 迭代结束后重新计算并比较；不一致
立即记录 `RBG_IMMUTABILITY_VIOLATION` 并把**当前** stream 置为 failed、按 worst-case
fail 结算该 reservation；当前实现没有跨后续 stream 的全局 latch（全局 fail-closed
latch 未实现/未验证）。
legit loop 请求本身 deep-frozen；selftest 用恶意内层 middleware 修改 `maxTokens` 实际
触发该检测（见 §6）。

## 3. Broker 子进程协议与生命周期

- 固定绝对 argv：`<fixed python> -B -m autoteacher_m0.accounting.broker --config
  <fixed absolute config>`；**无 shell、无客户端参数、无 route/model/金额来自客户端**。
- 固定 cwd；env 仅白名单：`PATH=/opt/python/bin:/usr/bin`、`HOME=/work`、
  `PYTHONPATH=/project/src:/deps`（来自 config 的固定绝对路径）、
  `PYTHONDONTWRITEBYTECODE=1`、`TMPDIR=/tmp`；不继承 runtime/Key/网络 env。
- NDJSON 单行 request/response，16384 字节 frame 上限，request 串行化；启动 probe 与
  单请求均有 bounded timeout（默认 8000/5000ms）。
- 子进程 error/exit/超时/非法 JSON/未匹配响应 → 永久 unavailable（不自动重启，fail-closed）；
  已发出的 reservation 保守保留。
- settlement 失败**不重试发放**：记录 `RBG_SETTLE_UNCERTAIN`、关闭 broker、后续 stream
  fail-closed；reservation 保守 pending（不会退款/释放）。
- broker 进程崩溃/重启的协议级持久性用独立脚本交叉验证（SIGKILL 后 pending reservation
  存活、重启后 fail 一次、pending=0；见 §6 s11），**不是**本插件的 live crash-recovery
  功能；插件崩溃后只会 fail-closed。

## 4. 准入、usage 与结算语义

**准入（provider 之前拒绝，fail-closed）**

- 固定 route/model：`provider === offline-test-only`、`model === fixture-v1`；注册的
  provider 集合必须**恰好**只有该 route（拒绝真实/额外 provider fallback）。
- `sessionId` 必须存在（稳定归因 → broker `task_id`，受 broker identifier 边界约束、
  字符归一化/截断）；`signal` 必须存在且未 aborted。
- `purpose`：未给出按 `conversation`；只允许 config 白名单 purposes
  `conversation/compaction/judge`；未知/缺失归因拒绝。
- `maxTokens` 必须是 1..1024 的安全整数（输出上界）；缺失/0/超界拒绝。
- 完整最终 history（含 tool result）只允许 `text/reasoning/tool-call/tool-addition/
  tool-removal` 块；拒 image/file/attachment/未知块；tool-call 只允许 `skill_lookup`
  （arguments ≤4096），tool schema 亦只允许 `skill_lookup`；assistant 历史必须来自
  允许的 provider/model 归因，tool result 必须有 tool 归因。
- provider adapter 的 retry policy：`mode==='always'` 或 `maxRetries>1` 拒绝
  （默认 5 不接受；fixture 0、test 1 通过）。
- 输入上界：完整 history/system/tools/stop 的 UTF-8 字节数 + 固定 overhead，超过
  `policy.maxInputTokens` 拒绝（broker 侧 max_input_tokens 为第二道上限）。
- reserve 返回非 `ok/dispatch_allowed` 或 broker 侧 `BUDGET_EXCEEDED`：在 provider
  之前抛错；scope blocked 后同一 scope 的新 reserve 会被 broker 拒绝（s4 实测重复
  normal stream；compaction/retry 产生的新 stream 未单独验证，见 §7）。

**结算映射**

- `usage` chunk → broker usage：`inputTokens` 按 uncached 直传，`cacheReadTokens`/
  `cacheWriteTokens` 分开直传，`outputTokens`/`reasoningTokens`/`totalTokens` 直传，
  `actual_cost_usd=null`；不推测/不拆分缺失字段。
- 只有收到 authoritative usage 且 finish 为 `stop`/`tool-calls`/`max-tokens` 才 settle
  实际值；无 usage、中断、abort、error、transport 不明、缺 finish → `fail`（worst-case：
  broker 按完整 reservation 计费，绝不退款）。
- 重试（v0.5 PR1）：M0 禁用 provider 内部自动重试（adapter `maxRetries` 必须为 0，
  `mode=always`/非零一律拒绝）；orchestrator 级重试是**新的 logical stream**，重新进入
  waterfall → 每次 dispatch 独立 reservation 并独立消耗 request/step slot（session s9
  实测 2 次 post-attempt reservation：第一次 worst-case、第二次实际结算；selftest 无该用例）。
  `retry:false` 仅归因，不声称能限制 provider 内部 retry。compaction/Judge 若走同一 `llm/stream` 也各自独立预留；compaction
  `purpose` 已在真实 Cordis public waterfall 验证（未触发真实 agent-loop compaction，见 §7）。

## 5. Config（profile 注入，非客户端）

```yaml
policy:
  provider: offline-test-only
  model: fixture-v1
  brokerScopeId: fixed-offline-scope
  maxOutputTokens: 1024
  maxInputTokens: 2500000
  maxProviderRetries: 0   # v0.5 PR1/M0: provider auto retry disabled (nonzero rejected)
  purposes: [conversation, compaction, judge]
broker:
  python: /opt/python/bin/python3.11
  pythonPath: /project/src:/deps
  configPath: /probe/config.json
  configSha256: "<broker startup policy bytes sha256>"
  cwd: /work
  requestTimeoutMs: 5000
  startupTimeoutMs: 8000
```

broker startup policy 必须是审阅过的 synthetic fixture policy（v1/synthetic/单 route/
显式价格+known fee+usage policy）。guard 在 spawn 前重新读文件并校验 hash/内容，因此
客户端/production route 无法改 scope/价格/限额。

## 6. 实际运行与证据（全部隔离内，只取日志实际值）

容器：既有 fixed rootfs `25491e45…`（before/after 实测相同）、deps `e07729d7…`、真实
runtime 二进制 `1cc41d5a…`、native cache `40c34d27…`（0444）、pkg-cache 4857/4857
逐个 sha256 通过；`/project` 挂载冻结实现 `f674403` 的 stage，容器内断言 4 个 broker
源文件 sha256 与 frozen delivery 完全一致；network none、uid 65534、ro root，
memory/pids/cpu/noexec 与既有 SDK fixture 相同。宿主机未执行项目 Python/pytest/node
生成代码；TS 仅在 rootfs 容器内编译。
注：task22 原始 manifest 的 `shared_rootfs_normalized_tar_sha256.after/match` 字段记录有误，
环境相等性请以 [manifest-errata.json](../artifacts/runtime-budget-guard/manifest-errata.json)
与 phase5 独立实测为准（本文件实现/断言/边界内容不变）。

**会话级（真实 DSH Runtime/SDK/RPC + 真实 offline fixture + skill_lookup + guard）**：

| case | 事实 |
|---|---|
| s1 normal | 1 fixture invocation；RESERVE 先于 FIXTURE_INVOCATION；1 reservation `OK` cost `0.001013`，input/output 7/3 |
| s2 tool round-trip | 2 fixture invocations → 2 connected reservations，均 `OK` |
| s3 concurrency | 2 sessions 并发 = 3 fixture invocations（其中一个 tool 两跳）→ 3 reservations/settlements，task_id 归因 2 个 session 稳定 |
| s4 denial | tiny broker per-call policy：2 次 run 都在 provider 前被 `BUDGET_EXCEEDED` 拒绝，fixture 0，scope blocked=1（单调） |
| s5 broker unavailable | 固定 python 路径不存在：provider 0，guard unavailable fail-closed |
| s6 policy drift | 预置不同 limits 的 DB：broker startup policy drift → provider 0 |
| s7 policy tamper | broker policy 字节被篡改：`BOOT_INVALID` deny-all，provider 0 |
| s8 no usage/error | scripted provider error 无 usage：1 reservation → `FAILED` 全额 reserved cost `0.003933`，不退款 |
| s9 transient retry | scripted transient error→success：2 次 provider attempt、2 reservations（1 FAILED worst-case + 1 OK `0.001013`） |
| s10 hard SIGTERM | 真实 fixture 流中被 SIGTERM：已预存 reservation `FAILED` 全额 `0.003949`；无退款 |
| s11 broker restart | 独立交叉验证：reserve pending `0.00112` → SIGKILL → 重启后 snapshot pending=1、fail 一次、最终 pending=0 |

会话级聚合：官方 broker DB 10 reservations = 7 `OK` + 3 `FAILED`（worst-case），合成
committed `$0.018904`；guard 日志 RESERVE/SETTLE 各 10；fixture invocations 7；
scripted provider invocations 3；`real_model_calls=0,http_calls=0`。

**in-process 真实 Cordis `LlmRuntime` + 真实 `llm/stream` waterfall selftest**：
18/18 cases PASS，5 个 admitted stream 全部 reserve+settle（3 settle、2 worst-case fail，
合成 committed `$0.006867`；purpose 4 conversation + 1 compaction）；拒绝/fail-closed
cases（image/file/未知 tool-call/route/model/maxTokens/session/purpose/provider-retry>1/
额外 provider registry/invalid config/mutation）均在 provider 之前拒绝或按 worst-case
处理；`denied-requests-never-entered-provider` 的 adapter counter 不变。selftest 的真实
provider 是显式 scripted test fixture（不是真实模型），仅用于公开 waterfall 断言。
最终一跑：10 worker + selftest，exit 0；12/12 case、18/18 selftest case、`real_model_calls=0`、
`http_calls=0`；机器清单/hash/argv/UTC 见
[artifacts/runtime-budget-guard/manifest.json](../artifacts/runtime-budget-guard/manifest.json)。

## 7. 明确 NOT VERIFIED / 残余风险

1. **每内部 HTTP/wire/billable attempt** 未被观测/拦截；只保证 logical `llm/stream`
   dispatch 的 reservation。Files stale-ID 同 stream 二次 POST 等 provider 内部行为仍
   属于未知 transport，本任务只以 text-only 拒绝 Files 路径作为**前提**，不外推已控。
2. **真实 agent-loop compaction / Judge 路由未触发**：仅验证 public `llm/stream` 上
   `purpose=compaction` 的独立预留与准入；完整 compaction/Judge 生命周期 NOT VERIFIED。
3. **插件模块 import 失败（语法/加载错误）** 上游 loader 会 warning 后继续；本插件对
   config 错误已 fail-closed，但无法阻止 loader 跳过整个模块的极端情况。集成必须
   显式断言 `RBG_BOOT`（或 deny-all BOOT_INVALID）后才能放行 traffic。
4. **session 级 graceful cancel 的 finally settle**：已用 in-process public API abort
   验证 worst-case settle；真实 Runtime 进程硬 SIGTERM 下，本插件只保证“已预存
   reservation 不会退款”（实测 FAILED/pending），未证明所有 kill 时序下 finally 必执行。
5. **live broker crash recovery** 不实现：崩溃即 fail-closed；仅协议级 restart 持久性
   做了独立交叉验证。
6. 不是授权/Key 代理/LiveGate；不改生产 Gate/Adapter/primary/route；不把 synthetic
   fee/usage 当真实账单；不签发 E1/E2/E3/E5 Live。
7. 本任务新增文件尚未 Git commit（按任务要求留待后续集成任务），因此无实现 commit SHA；
   当前 repo HEAD `ec1128b` + worktree 中 plugin/docs 为交付物，hash 见 manifest。
8. 未在真实 provider transport 上验证 `maxRetries≤1` 的实际进程行为（仅验证 adapter
   policy 准入 + scripted retry 的两次 reservation）。

## 8. 集成要求（后续 task/主 agent）

- profile 必须显式禁用所有真实 provider route，只 insert 显式 synthetic fixture route；
  用 `--dump-config` 和启动 `RBG_BOOT` 断言确认 guard 已加载。
- guard config/broker config 必须作为固定只读、hash-pinned 的 launcher 输入；不要在
  candidate/客户端消息里传 python/config/scope/price/limits。
- broker DB 必须是外部受保护、单 scope 的持久文件；candidate 不得直接访问 broker
  stdin/DB/进程。
- 把本中间件接入真实 provider 前，仍需独立审计 transport 隐藏 retry、Files 路径、
  真实 usage/账单、watchdog 与 Live 人工授权；task22 的 Live/真实模型调用仍 BLOCKED。
- 只要任何人把 provider 从 synthetic 切到真实/生产 route，必须重新评审并新增证据，
  不能沿用本文件的 synthetic 结论。

## 9. 历史与不覆盖声明

本任务不修改已冻结的 SDK fixture/ broker 源、历史 manifest/raw evidence、生产
Gate/Adapter/primary 或任务书；只新增独立 plugin、docs 与本 artifacts。既有 task20
（17-case）、task21（132+16=148、独立 closure 75/75）、phase4（326 全量、manifest
`bfea6fa1…`）证据原样保留。本文件中的数量来自最终隔离日志，不与历史轮次相加。

## 10. v0.5 PR1 增量（F1/F3/F4/F5/F6，2026-11-14）

本节记录 PR1 的行为增量与定向测试；**不改变**核心 `reserve-before-provider` /
`deny-before-provider` 性质，不改 phase5 冻结字节与历史结论。guard 源码现为 v0.5 PR1
（旧冻结 blob `1ccdb658…` / 旧构建 lib `3c184a62…` 仍可从 git 历史重建用于复验）。

- **F1**：M0 profile 必须 `maxProviderRetries=0`；adapter `providerRetryPolicy` 为
  `mode=always` 或 `maxRetries>0` 一律拒绝（`RBG_PROVIDER_RETRY_POLICY_UNSAFE`）。
  每个 logical stream（含 orchestrator 级重试/compaction）都是独立 waterfall entry，
  独立 reserve 并独立消耗 request/step slot；`retry:false` 仅归因，不再声称限制
  provider 内部 retry。provider 内部真实隐藏 retry 行为仍 **UNVERIFIED**（无 Live）；
  M0 以“禁用而非计数”消除它。
- **F3**：`requestDigest` 保留为**事后审计**：流结束后 digest 不一致 →
  `RBG_REQUEST_INTEGRITY_UNCERTAIN`，当前 stream 按 worst-case settle、调用失败；
  明确**不是发包前拦截**，不能据此声称已控制真实计费请求。真正事前拦截留 PR3/PR4。
- **F4**：拆 `model_completion_status`（COMPLETED/ERROR/ABORTED/BLOCKED/UNKNOWN）与
  `accounting_status`（RESERVED/SETTLED/WORST_CASE_HELD/SETTLEMENT_UNCERTAIN）；
  每次 stream 输出机器可读 `RBG_RESULT`。settle 未知/失败 → accounting 为
  SETTLEMENT_UNCERTAIN、抛错使上层验收失败、显式 fail-closed latch（后续 dispatch =
  provider 调用 0）；PENDING 不释放、不退款、不重试结算。
- **F5**：`encodeTaskId = "rbg-" + sha256(NFC(sessionId)).hex[0:64]`（≤96 字符），
  稳定单射；旧 reservation 保留旧 ID，新 reservation 使用新 ID。
- **F6**：`RBG_*` 公开日志只输出 allowlist 错误码/数字/布尔/哈希 ID（session /
  reservation / 路径均哈希）；故障 `RBG_UNAVAILABLE` 使用
  `phase=BEFORE_DISPATCH|DISPATCHED|SETTLING|UNKNOWN` + dispatched 计数，删除固定
  `reservations_not_dispatched:true`；raw broker stderr 仅在 launcher 显式设置
  `RBG_RAW_DIAGNOSTICS_PATH` 时写入 0600 受限文件，公开日志只含 count/bytes/sha256。
  `sk-FAKE-SECRET` 哨兵测试覆盖 error/stderr/session/公开日志。
- **F2（guard 侧）**：broker policy `max_messages` 校验上界对齐 broker 硬上限
  100,000（M0 profile 仍 4096）；guard 不内建 snapshot。

**新增测试**：`plugins/runtime-budget-guard/tests/guard-pr1.test.mjs`
（15 cases，真实 Cordis `LlmRuntime` public waterfall + committed fake NDJSON broker
fixture + scripted providers；15/15 pass；旧 lib 下 13 failed/2 passed 的 fail-first
证据保留）。Python 侧新增
`tests/unit/accounting/test_broker_capacity_f1_f2.py` 与
`tests/integration/budget_bridge/test_stdio_capacity_f2.py`（旧 broker 8 failed/3 passed；
修复后 accounting + budget_bridge 全套 131 passed）。argv/UTC/exit/镜像身份/产物 hash
见 `artifacts/m0-closeout-fix-tests/manifest.json`。

**未变/未验证**：per-internal-HTTP/Files/wire attempt 仍不观测；无 Live/真实
Key/HTTP（real_model=0、http=0）；真实 agent-loop compaction/Judge 未触发；mutation
仍可能已发包后才检测；历史 phase5 证据与 docs 历史字节不改；Live 仍 BLOCKED。
