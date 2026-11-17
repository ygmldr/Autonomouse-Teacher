# M0 G3-C 实施报告（C-INT2 交付）

> **状态**：G3-C 实现与无 Key 证据已完成；独立 Review 结论 `PARTIAL`（无 P0，3 个 P1）。本版为 **PR1 修复后**更新：P1-2 代码/测试见 `b2f6af054555705192c4e1ae3019a68078764736`，P1-1/P1-3 为文档/矩阵证据索引修正。
> **不是** G3-D PASS，**不是** Live/G4/G5/M0 GO 授权；OS 信任边界仍 `BLOCKED`。
> **身份**：Base `bb5bd0bf83e22130ed0d81c54f54a4673654cfe3`（G3-B final + secret-scan）；G0 `e107e22`；原始 Implementation `e6fde1cdf0bec9e957e98d569b257c8f17dfa363`；**P1-2 fix** `b2f6af054555705192c4e1ae3019a68078764736`（父 `78be77c`）。
> **Docs commit**：包含本报告/Findings/矩阵修正的 docs commit（父 `b2f6af0`）；其 SHA 记录于本文件与 Lead 汇报。
> **矩阵**：`docs/Autonomous_Teacher_M0_G3C_G3D_Test_Evidence_Matrix_v1.0.csv`，69 行 = **PASS 53 / NOT_RUN 16**（D 行 16 项全部 NOT_RUN、原字节未改）。`impl_sha` 统一指向 PR1 fix `b2f6af0`；旧 trace 的生成身份仍可由 `commands.jsonl`/`argv.json` 追溯到 `e6fde1c`。
> **无 Key 声明**：0 真实 Key / 0 真实模型 / 0 外部付费 HTTP / 0 Live；所有真实 DSH 运行均在固定 rootfs、`--network none`、Fake Provider 下完成。

## 0. 结论摘要与 Gate 请求

1. **C1/C2/C3 在渲染的真实 DSH 0.2.2-rc.2 路径上闭环**：Echo（1 call/1 claim/1 receipt/1 settle/1 usage）、Tool 两轮（2 个独立 call/reservation/claim/attempt/receipt）、Session 新进程 Resume（turn 2，旧 Attempt 不重发）、Guard precheck 三种组合均有原始 trace。**注意**：C1-01A/C1-04/C3-01B/C/C3-02A/B 是 raw-UDS probe，C2-02D/E 是 container reconcile，C1-01D/C2-04 是 host pytest，均不是 real DSH；真实 DSH 行与逐 case 证据类型见 Findings §4。
2. **原 G3-B P1 已闭环**：P1-1（B3-08 保守 hold → 持久 Observation/Usage 的幂等 settle）与 P1-2（cancel 非功能 → 真实传播 + 失败关闭）都有定向测试与真实 trace；P2-1..P2-7 逐项处置见 `docs/M0_G3C_FINDINGS_AND_DISPOSITION.md`。
3. **C3-04A 曾 FAIL，已修复并重跑**：修复前 DSH 首 Chunk 在 Fake 退出后才到达（`T1=1794919997481 > T2=1794919997472`）；修复后 `T1=1794922997900 < T2=1794922999899`（lead 1999 ms），并保留旧 trace 不覆盖。
4. **全量回归实测（PR1 修复后 @ `b2f6af0`）**：host full **773 passed / 2 failed（既有宿主环境）/ 1 skipped**；g3c **110**、g3_bridge **31**、gates **14**、G2 **280**、Node **9/9**、Guard **19/19**、Ruff **All checks passed**；20 轮双 Controller 冷启动全部确定性（20× 1 成功 + 1 `CONTROLLER_SINGLETON_LOCKED`，0 traceback，Fake counter=1）；真实 DSH Echo/Tool 冒烟通过。原 `e6fde1c` 的 OCI full 768/2/1 记录保留，PR1 的 OCI 复跑见 §10.1。
5. **仍未证明/未做**：G3-D OS 边界（16 行 NOT_RUN）、真实 Provider token/账单、远端 exactly-once、Live；不得用本地 Claim/Fake usage 代替。
6. **请求裁定**：独立 Reviewer 按 §8.3 与本报告证据给出 `PARTIAL`/`PASS_FOR_G3C_NO_KEY_CONTRACT_RECOVERY_SCOPE` 等裁定；不得给出任何 G3-D/Live/GO 裁定。本轮不请求重新裁定，由 Lead 安排复核。
7. **Review P1 处置**：P1-1（真实 DSH 标注）与 P1-3（矩阵证据索引）已按本报告/Findings/矩阵修正；P1-2（双 Controller 冷启动）由 `b2f6af0` 的 `busy_timeout`→WAL 顺序、有界锁重试、显式 singleton 锁与受控退出修复，并以 20 轮实测证据 `artifacts/g3c/evidence/concurrency-coldstart-20261117T153229Z.json` 固化。

**矩阵口径**：归档的 v1.0 空矩阵（commit `7199058`）为 66 行；工作矩阵按任务书 §5/§6/§7 增补 `C1-02`（finish schema）、`C1-04`（replay/业务冲突）、`C2-04`（recovery admission）三个 case（原归档矩阵未列），并填 G0/C 共 53 行。docs 矩阵与工作矩阵采用同一 69 行口径；D 行 16 条保持原字节、全部 `NOT_RUN`；`reviewer_verdict` 留空，等待独立复核。

## 1. 身份与提交链

| 项 | 值 |
|---|---|
| Base（G3-B final + secret-scan） | `bb5bd0bf83e22130ed0d81c54f54a4673654cfe3` |
| G0 基线 commit | `e107e22`（`docs: add G3-C G0 baseline and drift report`，父 `7199058`） |
| 任务书归档 | `7199058`（父 `bb5bd0b`，原字节任务书 + 空矩阵） |
| Implementation（原始 G3-C） | `e6fde1cdf0bec9e957e98d569b257c8f17dfa363` |
| **P1-2 fix（PR1 impl）** | `b2f6af054555705192c4e1ae3019a68078764736`（父 `78be77c`） |
| A（协议/IPC/流式） | `9228995` |
| B（核心 admission/usage/recovery/cancel） | `28e47b9` |
| 证据脚手架 | `f84b121` / `854bab6` / `8f04b53` |
| C3-04A 修复 | `3675a41` |
| 证据 runner/analyze | `e6fde1c` |
| **PR1 docs commit** | 本报告/Findings/矩阵修正所在 commit（父 `b2f6af0`） |
| 分支/远端 | `main`；**未 push**（远端仍为 `bb5bd0b`） |

逐提交与「实施范围」：

```text
9228995 feat: G3-C protocol fixes, IPC bounds, deadlines and streaming (no-key)
28e47b9 feat: G3-C core admission, usage, recovery and cancel semantics (no-key)
f84b121 fix: G3-C integration evidence scaffolding and streaming fixtures (no-key)
854bab6 fix: G3-C integration evidence - separate test-only crash-hook env ...
8f04b53 fix: G3-C integration evidence - label host-only cases and never imply real-DSH
3675a41 fix: G3-C real-time streaming through IPC (C3-04A)
e6fde1c chore: G3-C C3-04 post-fix evidence runner and matrix analysis
b2f6af0 fix: G3-C deterministic two-controller cold start (no-key)
```

`git diff --stat bb5bd0b..e6fde1c`：41 files, +10053/−429；产品代码变更集中在 `src/autoteacher_m0/bridge/{protocol,ipc_server,broker_client,fake_backend,attempts,admission,controller}.py` 与 `src/autoteacher_m0/accounting/{broker,ledger}.py`；新增 `tests/integration/g3c/` 11 个文件、`spikes/g3b-trusted-bridge/run_c3/` 6 个 runner、`scripts/g3c/` 7 个脚本。未修改 `security/gates.py`、`runtime/dsh_adapter.py`、`scripts/run_live.sh`、G3-B packet/历史 matrix。

`b2f6af0`（P1-2 fix）：3 files, +662/−45；`attempts.py` 初始化顺序/有界重试/`AttemptJournalUnavailable`，`controller.py` 的 per-socket `flock` singleton 与受控退出（`CONTROLLER_SINGLETON_LOCKED` exit 5、`ATTEMPT_JOURNAL_UNAVAILABLE` exit 4、`ADMISSION_REPLAYED_AFTER_RECOVERY` exit 3），新增 `tests/integration/g3c/test_c3_05_twocontroller_coldstart.py`（20 轮双进程冷启动 + WAL 锁重试/耗尽 + journal-unavailable 受控退出）。

## 2. 范围与不批准事项

**本轮范围（已做）**：G3-C1 协议/错误语义/Admission；G3-C2 Usage/Receipt/Observation/Recovery；G3-C3 Cancel/Deadline/IPC 资源/增量 Streaming；无 Key 集成证据、回归、Packet、docs。

**明确不在范围（未做/不主张）**：

- G3-D0/D1/D2/D3 的 OS Principal 隔离、候选攻击、内核拒绝证据：**16 行 NOT_RUN**，`OS_TRUST_BOUNDARY` 仍 `BLOCKED`。
- 真实 Provider/API Key/模型调用/外网/账单：**0**；LiveGate 仍 `BLOCKED`，`run_live.sh` exit 3。
- G4/G5/Live/M0 GO：**未授权**；本报告不能作为任何放行依据。
- 真实 DSH 之外的宿主机安全审计、内核逃逸、供应链/插件审计。

## 3. SRC-01..SRC-12 处置表

| ID | 问题（G0 现场） | 本轮处置 | 实现位置（impl `e6fde1c`） | 动态证据 | 残余 |
|---|---|---|---|---|---|
| SRC-01 | `receipt_json` 无 usage，重启只保守 fail | **已修**：journal 持久完整 Observation 文档（含 usage/digest），reconcile 校验后按 Broker 权威状态 settle/fail | `controller.py:1075-1155,1254-1420`；`attempts.py:238-276` | C2-02A/B（after crash → `SETTLED`，broker OK，fake 不增）；C2-02F（partial → `WORST_CASE_HELD`） | 无 receipt/文档损坏 → `SETTLEMENT_UNCERTAIN`（C2-02D、C2-03C），这是有意的失败关闭 |
| SRC-02 | `cancel(self)` 签名不匹配、`_cancel` 从不检查 | **已修**：per-transport cancel 状态、checkpoint 传播、发送后取消保守结算 | `controller.py:242-298,602-760`；`ipc_server.py:471-516` | C3-01A/B/C/E；C3-01D（SIGTERM 清理）；C3-03G（错误签名记录不吞） | 发送后无法回滚 Provider；无 receipt 时 `SETTLEMENT_UNCERTAIN`；断连不是 durable cancel 信号 |
| SRC-03 | Fake `usage` 帧被 Controller 丢弃，账本与 DSH 可见 usage 不同源 | **已修**：frame usage 与 receipt usage 强制一致；DSH 侧发 `StreamChunk(type=usage)`；Observation/账本用同一 usage | `controller.py:913-1075` | C2-01A（`usage_equal=True`）；C1-02（五类坏 usage）；C2-01D | usage 为合成 fixture；不是供应商账单 |
| SRC-04 | `max_output_tokens`/`deadline_ms` 未执行，输入预留固定 1024 | **已修**：`max_output_tokens` 与请求比较；输入按 UTF-8 bytes 上界预留；admission deadline 进入 checkpoints 与 Broker/Fake 超时 | `controller.py:220,305-382,602-760`；`admission.py:105-119` | C1-03A/C/E/F；C3-02B（raw-UDS fake stall）、C3-02C（真实 DSH deadline） | 输入 token 是保守合成上界（非 tokenizer）；见 §14 |
| SRC-05 | Broker `timeout_s` 对阻塞 readline 无效 | **已修**：`select` + 单调 deadline + 回复字节上界；超时标记 client 不可信 | `broker_client.py:282-340` | C3-02A（`broker_requests=1`, elapsed 1.62 s, `BROKER_TIMEOUT`, fake=0） | 仅约束本地 Broker 子进程；不证明远端超时 |
| SRC-06 | 首帧无限等待、连接/线程无上界、deadline 不能中断 | **已修**：首帧 deadline、连接上限 8 + `TOO_MANY_CONNECTIONS`、线程回收、watchdog、响应帧/总量上限 | `ipc_server.py:45-120,124-255,286-470` | C3-03A/B/C/D/E/F/G；`probe-ipc-bounds`；C3-02D | 真实 DSH 下主要经单连接；资源压力为 host/容器定向探针 |
| SRC-07 | `_last_frame_bytes` 跨连接污染响应预算 | **已修**：预算改为每连接状态 | `ipc_server.py:107-123,286-470` | C3-03D/E（同一测试覆盖 per-connection 预算） | — |
| SRC-08 | 无效 Schema/Route 也消耗 `max_calls` | **已修**：`calls` 只在 prepare 成功且身份登记后递增，另有 `rejected_calls` | `controller.py:602-640` | C1-03B（无效请求不消耗）；C1-03C（第二次 `BUDGET_DENIED`，attempts=1） | — |
| SRC-09 | Broker 冲突码不在 IPC 错误集，降级 `UNKNOWN_FIELD` | **已修**：新增有限 `BROKER_*`/`DEADLINE_EXCEEDED`/`TOO_MANY_CONNECTIONS` 码与显式映射 | `protocol.py:26-85,328-460` | C1-01A/B/C/D；C1-04；Node adapter TAP #5 | 未扩大为任意 Broker 原始码透传（有意） |
| SRC-10 | finish(error) 缺 `failure{code,message}` | **已修**：terminal error 统一构造 schema 正确的 failure；绝不发成功 finish | `controller.py:1051-1074` | C1-02（五类终态）；C2-01C | — |
| SRC-11 | Fake 进程结束后一次性解析，非在线 streaming | **已修**：Fake 逐帧 yield + Controller worker/queue 逐帧转发；receipt-first 校验 | `fake_backend.py:223-340`；`controller.py:480-537` | C3-04A（T1<T2，lead 1999 ms）；C3-04B/C/E | 见 §14/§15 |
| SRC-12 | `next_logical_step(run_id)` 未使用 `run_id` | **不改（记录）**：确认不在运行路径；加注释并用测试锁定「运行时不得调用」 | `attempts.py:301-309` | C2-04c（monkeypatch 断言运行时不调用） | P2 残余；如未来接入必须重写并重新评审 |

统计：**已修 11 / 记录性残留 1（SRC-12）/ 无 ALREADY_FIXED 误报**。

**P1-2 并发冷启动（Review P1-2，`b2f6af0`）**：`AttemptJournal` 先 `PRAGMA busy_timeout` 后 `journal_mode=WAL`；WAL/DDL 初始化对可重试锁错误做有界重试（默认 10 s，0.05 s 间隔），只对 `SQLITE_BUSY/SQLITE_LOCKED` 归类为可重试，真实错误原样抛出；两个初始化器竞争同一 `ADD COLUMN` 的良性 `duplicate column name` 视为成功。重试耗尽抛出 `AttemptJournalUnavailable`。`controller.main` 在启动最前面按 socket 路径持 `flock` singleton（运行期持有，进程崩溃由内核释放），第二个冷启动在启动 Broker/Fake/journal 之前固定输出 `CONTROLLER_SINGLETON_LOCKED` 并 exit 5；journal 重试耗尽关闭 Broker/Fake、不绑定 socket，固定输出 `ATTEMPT_JOURNAL_UNAVAILABLE` 并 exit 4；`ADMISSION_REPLAYED_AFTER_RECOVERY` 仍 exit 3。20 轮实测：20/20 为 1 成功 + 1 受控 singleton 拒绝，0 traceback，Fake counter 恒 1，Attempt 恒 `SETTLED`（证据 `artifacts/g3c/evidence/concurrency-coldstart-20261117T153229Z.json`）。

## 4. G3-C1：协议、错误语义与 Admission

**C1-01 错误码语义一致。** `protocol.ERROR_CODES` 增补 Broker 抽象码；`BROKER_ERROR_CODE_MAP` 把 `CALL_ID_CONFLICT/IDEMPOTENCY_CONFLICT/ALREADY_SETTLED/ALREADY_FAILED/INVALID_USAGE/INTERNAL_ERROR` 映射为有限码；error payload 通过 `validate_error_payload`。**C1-01A 是 raw-UDS replay 探针，不是 real DSH**：`spikes/g3b-trusted-bridge/run_c3/probes_c3.py --probe replay`（`artifacts/g3c/traces/probe-replay/probe-result.json`；该目录**没有** `dsh-result.json`）在固定 rootfs 内直接驱动 Controller + 真实 SQLite Broker + Fake，首请求 `ack/chunk/chunk/finish`，重放 `ack/error`，code `ATTEMPT_ALREADY_STARTED`，Fake counter 不增；C1-01 矩阵的 expected evidence 本来就是 “new raw test stdout/trace + freeze SHA + independent replay”，不要求 real DSH。C1-01A 与 C1-04 引用同一份 `probe-result.json`（C1-04 是详细 replay/reservation 冲突行，C1-01A 是同一 raw-UDS replay 结论的汇总；C1-01B/C 是 host-level）。Python 8/8 映射测试、TS adapter `BROKER_*` 码测试通过（C1-01D，host pytest + Node TAP）。

**C1-02 Finish(error) 永远 Schema 正确。** `_terminal_events` 对非 authoritative 流只发 `finish(error, failure={code,message})`；五个真实 DSH 终态（error/no_usage/partial/invalid/eof）全部 `finish=error`，Broker `FAILED`/journal `WORST_CASE_HELD`，无成功 finish。

**C1-03 Admission 执行而非只解析。** 原子 quota（`_quota_lock`）；无效 Schema/Route/Tool 请求不消耗 `max_calls`（C1-03B）；达到上限后真实第二请求 `BUDGET_DENIED` 且 attempts=1（C1-03C）；最大输出/输入边界分别拒绝（C1-03A/F）；admission deadline 触发 `DEADLINE_EXCEEDED`，状态 `SETTLEMENT_UNCERTAIN`（C1-03E）；并发 host 测试不超 quota（C1-03D）。

**C1-04 请求重放/业务冲突。** durable identity 以 `(scope_id, business_digest)` 绑定 `call_id`；同 call/同 payload replay 返回 `ATTEMPT_ALREADY_STARTED`，不同 digest/Reservation 不匹配拒绝，已 settle 不被覆盖；Fake 不增。证据类型：**C1-04 与 C1-01A 引用同一份 raw-UDS `probe-replay/probe-result.json`（非 DSH）**；C1-01B/C 为 host-level；C1-01D 为 host pytest + Node TAP。该 raw-UDS 探针在固定 rootfs 内使用真实 Controller/Broker/Fake/SQLite，只是没有 DSH 客户端。

## 5. G3-C2：Usage / Receipt / Observation / Crash-Reconcile

**C2-01 Usage 统一。** 每个 Attempt 持久 `m0.g3c.observation.v1` 文档，含 receipt、usage、observation、`usage_digest`、`journal_digest`；Fake 内部 `usage` 帧与 receipt usage 必须 canonical 相等，否则 `FAKE_RECEIPT_MISMATCH`；DSH 在 finish 前收到 `chunk.type=usage`。Echo `usage_equal=True, state=SETTLED, broker=OK`；Tool 两轮各自 usage（turns=2，modes `tool_once/tool_final`，tool_results=1）；坏 usage 不产生成功 finish/免费结算（C2-01C/D、C1-02）。

**C2-02 重启后持久 Settlement 幂等。** reconcile 先读 Broker `reservation_status` 权威状态，再校验 receipt 文档 `journal_digest` 与字段；authoritative usage → `settle`，partial/invalid → `fail`；重复 reconcile 不改 settlement、不二次 reserve/claim（C2-02E）；篡改 receipt usage → `SETTLEMENT_UNCERTAIN` 且 Broker 仍 PENDING，不覆盖（C2-02D）；partial 失败 → `WORST_CASE_HELD`（C2-02F）；after_response/after_broker_settle 崩溃在两个窗口都恢复为 `SETTLED`（C2-02A/B）；`ATTEMPT_STARTED` 无 receipt → `SETTLEMENT_UNCERTAIN`，不重发（C2-02C）。**证据类型**：C2-02A/B/C/F 的 crash 半是 real DSH（`worker_c3.py` 生成），reconcile 半是 container reconcile（`reconcile_c3.py`，非 DSH）；C2-02D/E 是纯 container reconcile。

**C2-03 Observation 冲突与数据模型。** Attempt journal 是唯一权威 observation 位置：同 observation replay 无副作用；不同 digest 触发 `OBSERVATION_CONFLICT`；缺 provenance 拒绝 settle；Broker/Journal 摘要一致；legacy v1 client 回归（C2-03A..E，均 host-level）。

**C2-04 Recovery Admission 与 Logical Step。** 冻结顺序：先 reconcile 旧 Attempt，再消费/登记 Admission；`ADMISSION_REPLAYED_AFTER_RECOVERY` 时已恢复的 Attempt 保持 `SETTLED`、Fake 仍为 1、旧 call 不重发；新 admission 下同一业务请求 `ATTEMPT_ALREADY_STARTED`，真正新请求仍可执行；`next_logical_step` 被测试锁定为运行时不可调用（C2-04a/b/c）。

## 6. G3-C3：Cancel、Deadline、IPC 资源与增量 Streaming

**C3-01 Cancel 契约生效。** `cancel(transport_id, reason)` 只影响单个 transport；pre-send checkpoint 取消 → 无 Fake 发送；发送后取消 → 若 receipt 完整则按权威 usage 保守结算，否则 `SETTLEMENT_UNCERTAIN`；重复/未知/错误签名 cancel 不静默吞掉（日志 + `cancel_failures`）；SIGTERM 清理 socket 与 Broker 子进程。真实/容器证据：C3-01A（host pytest controller 1/1 + Node AbortSignal TAP，**host-level**）、C3-01B/C（固定 rootfs 内 raw-UDS probe，真实 Broker/Fake，`CANCELLED`，无成功 finish；**非 DSH**）、C3-01D（real DSH SIGTERM 后无残留 DSH/Broker 进程）、C3-01E（host pytest）。

**C3-02 真实 Deadline / Broker Timeout。** Broker 阻塞不回包的 raw-UDS probe：1 次请求、1.62 s 后 `BROKER_TIMEOUT`、Fake=0（C3-02A，固定 rootfs 内 `probes_c3.py --probe broker-hang`，**非 DSH**）；Fake 卡住的 raw-UDS probe：`DEADLINE_EXCEEDED`，attempts `SETTLEMENT_UNCERTAIN`（C3-02B，**非 DSH**）；admission 100/300 ms：真实 DSH 终态 `DEADLINE_EXCEEDED`，无成功 finish（C3-02C、C1-03E）；IPC watchdog 与 settle 回复丢失幂等为 host-level（C3-02D/E）。

**C3-03 UDS 连接与内存/线程容量。** 首帧 deadline、慢字节连接中断、活跃连接上限（`TOO_MANY_CONNECTIONS`）、每连接响应/总字节预算、非法首帧不进入 Controller、错误 cancel 签名不吞；`BridgeServer` host 测试使用真实 socket/线程，容器内 `probe-ipc-bounds` 复验（C3-03A..G）。

**C3-04 增量 Streaming。** Fake 逐行读取并按帧 yield；Controller 单飞 worker 把已校验 chunk 放入有界队列（8 帧），IPC 逐帧 yield；receipt 先落地、再转发首 chunk（失败关闭）；terminal usage/finish 在 settle 之后。C3-04A 修复前后见 §7。`MAX_STREAM_CHUNKS`/响应字节上限、截断帧、消费者停摆均有界（C3-04B/C/D/E）。

**C3-05 并发与 Trace 质量。** 并发 cancel 探针两条连接互不串扰（C3-01C 同时保留另一条成功流）；每 case 独立 trace 目录 + `argv.json` + `db-snapshot.json`；`commands.jsonl` 74 条命令、`correlation-g3c.jsonl` 57 行关联、51 个 DSH trace、12 个 reconcile trace。

## 7. C3-04A 修复前后 T1/T2（同一 impl 后置证据）

定义：`T1` = DSH SDK 收到首个 chunk 的事件时间；`T2` = Fake 子进程 `exit_after_finish` 标记时间；`lead_ms = T2 − T1`。判据：真实增量流必须 `T1 ≤ T2`。

| 运行 | Fake first chunk (ms) | Fake exit `T2` (ms) | DSH first chunk `T1` (ms) | `T1<T2` | lead | 结果 |
|---|---:|---:|---:|---|---:|---|
| 修复前 `stream-slow` | 1794919995471 | 1794919997472 | 1794919997481 | **False** | −9 ms | **FAIL**（Controller 缓冲直到 settle，首 chunk 在 Fake 退出后） |
| 修复后 `stream-slow-fixed` | 1794922997899 | 1794922999899 | 1794922997900 | **True** | +1999 ms | **PASS**（首 chunk 在 Fake 仍运行时到达 DSH） |

修复提交 `3675a41`：`handle_envelope` 改为 worker thread + 有界 `queue` + IPC generator 逐帧 yield；`_publish_event` 在取消/超时后丢弃非 terminal 帧而不是无界缓冲；`finally` 中 close 生成器会 abort 并对仍存活的 worker 调 `cancel(stream_closed)`。旧 trace `artifacts/g3c/traces/stream-slow` 与旧矩阵 `evidence-matrix-g3c.before-c3-04a-fix.csv` **原字节保留**，未被覆盖；新证据使用 `*-fixed` 命名。

## 8. 任务书 §8.1 / §8.2 覆盖

### 8.1 最小成功集（真实 DSH、无 Key）

| 要求 | 证据 | 实际结果 |
|---|---|---|
| SDK Echo（1 call/1 claim/1 receipt/1 settle/usage） | `traces/echo-fixed`、`ledger/echo-fixed-db.json` | `ok/completed`；1 attempt `SETTLED`；usage 18（input 11 + cache 2 + output 5）；counter=1 |
| SDK Tool/Skill Lookup（≥2 calls，第二请求带 tool result） | `traces/tool-fixed` | 2 个独立 call/reservation/claim/attempt/receipt，均 `SETTLED`；`tool_results=1`；counter=2 |
| Session 新进程 Resume | `traces/resume-first`、`resume-second` | 第二进程 `turn=2`、`ok/completed`；2 attempts `SETTLED`；旧 attempt 不重发 |
| Guard precheck 存在/不存在组合 | `traces/guard-on`、`guard-off`、`guard-invalid`；Node guard 19/19 | guard-on/off 均成功且只有 Controller 一个 Broker child；guard-invalid 以 `RBG_GUARD_BOOT_INVALID` 失败关闭，无 attempt |
| G2、G3-B、Node、Python 全量回归 | 见 §10 / §10.1 | 280 / 31 / 9+19 / 768+768 @ e6fde1c；PR1 @ b2f6af0：280 / 31 / 9+19 / 773+773 |
| 静态检查 | `regression/ruff-check.log`；PR1 `logs/pr1-ruff.log` | `All checks passed!` |

**§8.1 证据类型说明**：Echo/Tool/Resume/guard-on/guard-off 是 real DSH；guard-invalid 是 Controller 启动失败关闭（无 DSH）；Node guard 19/19、Node adapter 9/9、G2/G3-B/Python 全量回归与 Ruff 是 host/容器定向测试或回归，**不是** real DSH。不得把本表整体读成“全部是真实 DSH”。

### 8.2 高风险负例（按类映射）

| 负例类 | 证据 | 结果（Fake/状态） |
|---|---|---|
| 无 Claim / 伪造 Reservation / 篡改 Prepared / Route/Tool Schema 不符 → Fake=0 | C1-01C、C1-03A/B/F、`traces/bad-admission`、`traces/guard-invalid`、`traces/no-controller` | 拒绝/无 admission；bad-admission controller exit 1 且无 attempt/receipt；guard-invalid 无 attempt；no-controller 无 attempt/receipt |
| after_claim_before_attempt / after_attempt_before_send Crash | C2-02C、C2-02A/B、crash/reconcile trace | 未发送 → `SETTLEMENT_UNCERTAIN`；有 receipt → `SETTLED`；无重发 |
| Provider received 但无 Settlement | C2-02A、C2-03C、C2-02D | reconcile 以 Broker 状态为准；无 receipt → uncertain；不覆盖 |
| Broker Settlement 成功但 Attempt 未标记 | C2-02B、C2-02E | 两次 reconcile 幂等；无第二次 reserve/claim |
| Bad/partial/missing usage、伪造 Receipt digest、冲突 Observation | C1-02、C2-01C/D、C2-02D、C2-03A/B | 无免费结算/成功 finish；partial → `WORST_CASE_HELD`；冲突拒绝 |
| Invalid UDS Frame、未完成连接、无限阻塞 Broker/Fake | C3-03A..G、C3-02A/B/C、C3-04D | 受控错误/超时；资源有界；无未授权 Fake |
| 双进程竞争单次 Claim | C1-01A/C1-04 raw-UDS replay、C1-03D host 并发 admission、C3-01C raw-UDS 并发 cancel；PR1 新增 20 轮双 Controller 冷启动（host + fixed OCI test） | 本地 durable 身份/配额 + per-socket singleton 保证至多一次发送；**未**单独做真实 DSH 双进程同 Claim 竞争，见 §14 |

## 9. C3-04A 之后的证据重跑与可追溯性

- 受影响真实 DSH 用例在 `3675a41` 后用新名称重跑：`echo/tool/usage-*/stream-*/sigterm/crash-*` → `*-fixed`；raw-UDS probe（`probe-*`）与 container reconcile（`reconcile-*`）也各自重跑，但它们不是 real DSH；`commands.jsonl` 追加而非截断。
- `analyze.py` 以 `LOGICAL_TRACE` 只读映射到 `*-fixed` trace，旧 trace 保留；工作矩阵 `evidence-matrix-g3c.csv` 生成于 `2026-11-17T13:56:26Z`（impl `e6fde1c`）。
- **回归后更正**：`C-END-02` 行已按 `2026-11-17T14:11Z–14:12Z` 的新一轮全量回归更新（host 768/2/1；OCI 768/2/1，失败为 `pgrep` 缺失与 `/tmp` noexec，不再沿用旧 `766`/`/bin/sh` 说明）；其余行未改。
- **PR1 证据索引修正（`b2f6af0` 之后）**：53 个 PASS 行中 25 个 `db_or_receipt_path` 占位路径已改为真实 junit/log/trace；C1-01A 填真实 raw-UDS argv/log 并明确 `raw-UDS (not DSH)`；C-END-01 填 echo/tool/resume 子 trace 与 argv/log；C2-04 junit 指向实际 `artifacts/g3c/evidence/junit-g3c.xml`；C1-01D/C2-04 补 `host-level (not DSH)`，C1-04/C3-01B/C/C3-02A/B 补 `raw-UDS (not DSH)`，C2-02D/E 补 `container reconcile`。D 行 16 条原字节未改，`reviewer_verdict` 仍留空。修正前后审计（25→0 missing；D 行 SHA 前后一致）见 `artifacts/g3c/evidence/matrix-path-audit-pr1.txt`。

## 10. 全量回归与工程验证（实际执行，非预填）

§10 表格是 **原始 `e6fde1c`** 的全量回归记录；PR1 修复（`b2f6af0`）后的重跑见 §10.1。原始日志在 `artifacts/g3c/regression/`。汇总：`regression/summary-regression.json`。

| 测试 | 命令/日志 | 实测 | exit |
|---|---|---|---|
| host full | `regression/host-full.log`（`pytest tests/ -q -p no:cacheprovider`） | **768 passed / 2 failed / 1 skipped**（771 collected，117.36 s） | 1 |
| fixed OCI full | `regression/oci-full-runner.log`（`bash scripts/g3c/run-oci-full.sh`） | **768 passed / 2 failed / 1 skipped**（82.19 s） | 1 |
| `tests/integration/g3c` | `regression/g3c-tests.log` | **105 passed**（42.59 s） | 0 |
| `tests/integration/g3_bridge` | `regression/g3-bridge-tests.log` | **31 passed**（5.90 s） | 0 |
| `tests/unit/security/test_gates.py` | `regression/gates-tests.log` | **14 passed** | 0 |
| G2 accounting/closure | `regression/g2-tests.log` | **280 passed**（21.10 s） | 0 |
| Ruff | `regression/ruff-check.log` | **All checks passed!** | 0 |
| Node adapter（固定 rootfs） | `regression/node-adapter.log` | **9 tests / 9 pass / 0 fail** | 0 |
| Guard（固定 rootfs） | `regression/node-guard.log` | **19 tests / 19 pass / 0 fail** | 0 |

四个失败均为**环境性、非产品断言**，逐项记录：

1. host `test_target_profile_static.py::test_required_files_exist_and_are_read_only_text`：宿主 `config/dsh/*.yml` 为可写 mode（OCI 内 0444 时通过）。
2. host `test_live_controller_no_key.py::test_all_live_entrypoints_remain_blocked`：测试子进程硬编码 `PYTHONPATH=/project/src`，宿主无 `/project`（OCI 内通过）。
3. OCI `test_c3_01e_sigterm_cleans_socket_and_broker_child`：冻结 rootfs **不含 `pgrep`**，探针无法执行（宿主机通过）。
4. OCI `test_c3_02a_broker_alive_without_stdout_times_out_once`：`/tmp` 以 `noexec` 挂载，测试生成的 `slow-broker-wrapper` 无法 exec（宿主机通过）。

因此：host 2 失败与 G3-B/G0 记录的既有宿主环境限制一致；OCI 2 失败是冻结 rootfs 的工具/挂载限制（此前记录的「no `/bin/sh`」在本轮实际表现为 `pgrep` 缺失 + noexec；如实更正，不掩盖）。无产品语义断言失败。

### 10.1 PR1 修复后重跑（impl `b2f6af0`，2026-11-17T15:32Z–15:41Z）

全部在提交 `b2f6af054555705192c4e1ae3019a68078764736` 的干净工作区、宿主 CPython 3.11.15、`PYTHONDONTWRITEBYTECODE=1 ... -B` 下执行；原始日志在 `artifacts/g3c/logs/pr1-*.log` / `artifacts/g3c/pr1-oci/`。

| 测试 | 命令/日志 | 实测 | exit |
|---|---|---|---|
| host full | `artifacts/g3c/logs/pr1-host-full.log`；junit `artifacts/g3c/evidence/pr1-host-full-junit.xml` | **773 passed / 2 failed / 1 skipped**（776 collected，129.72 s；2 失败同 §10 的既有宿主环境限制） | 1 |
| fixed OCI full | `artifacts/g3c/pr1-oci/logs/oci-full.log`；junit `artifacts/g3c/pr1-oci/evidence/junit-oci-full.xml` | **773 passed / 2 failed / 1 skipped**（90.31 s；2 失败同 §10 的 `pgrep`/noexec 环境限制） | 1 |
| `tests/integration/g3c` | `artifacts/g3c/logs/pr1-g3c.log`；junit `artifacts/g3c/evidence/pr1-g3c-junit.xml` | **110 passed**（54.36 s；原 105 + 5 个 P1-2 新测试） | 0 |
| `tests/integration/g3_bridge` | `artifacts/g3c/logs/pr1-g3_bridge.log` | **31 passed**（5.82 s） | 0 |
| `tests/unit/security/test_gates.py` | `artifacts/g3c/logs/pr1-gates.log` | **14 passed** | 0 |
| G2 accounting/closure | `artifacts/g3c/logs/pr1-g2.log` | **280 passed**（20.83 s） | 0 |
| Ruff | `artifacts/g3c/logs/pr1-ruff.log` | **All checks passed!** | 0 |
| Node adapter（固定 rootfs） | `artifacts/g3c/pr1-node/logs/node-adapter.log` | **9 tests / 9 pass / 0 fail** | 0 |
| Guard（固定 rootfs） | `artifacts/g3c/pr1-node/logs/node-guard.log` | **19 tests / 19 pass / 0 fail** | 0 |
| 20 轮双 Controller 冷启动 | `artifacts/g3c/evidence/concurrency-coldstart-20261117T153229Z.json`；日志 `artifacts/g3c/logs/coldstart-20261117T153229Z/` | **20/20 确定性**：20× 1 成功 + 1 `CONTROLLER_SINGLETON_LOCKED`（exit 5），0 traceback，Fake counter=1，Attempt=`SETTLED`；另 3×20 轮压力复跑同结果 | 0 |
| 真实 DSH 冒烟 Echo | `artifacts/g3c/pr1/traces/echo/dsh-result.json`；日志 `artifacts/g3c/pr1/logs/echo.log` | `ok/completed`，1 attempt `SETTLED`，controller exit 0，DSH usage == receipt | 0 |
| 真实 DSH 冒烟 Tool | `artifacts/g3c/pr1/traces/tool/dsh-result.json`；日志 `artifacts/g3c/pr1/logs/tool.log` | 2 attempts `SETTLED`，2 assistant messages，1 tool-result，controller exit 0 | 0 |

说明：OCI full 在固定 rootfs 内执行了同一 20 轮双 Controller 冷启动测试（通过），覆盖 uid 65534、只读 rootfs、`--network none` 下的 singleton/WAL 行为；但它仍不是“两个真实 DSH 客户端同 Claim”的运行（worker 每个进程自带 Controller/admission），该残余见 §14.13。

环境/卫生：rootfs canonical 前后均为 `25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0`；deps 前后均为 `e07729d7997944417b1c25531749b3e6e5e34aa4248f01dc8f370282082ecb98`；OCI runner 前后 rootfs canonical；`podman ps -a` 空；无残留 Broker/Fake/Controller/DSH 进程。

环境/卫生复核：

- rootfs canonical 前后均为 `25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0`；
- deps canonical 前后均为 `e07729d7997944417b1c25531749b3e6e5e34aa4248f01dc8f370282082ecb98`；
- stage 最终 hash `fcdb0de442d455f89fe849c736679f831c15c50f76e3e4844d38f2963e3735b0`（13:40 build 的 `env/stage.json` 记录当时 `9817…`；13:41 fixed run 刷新 `stage/fixtures/capture-tools.json` 后为 `fcdb0…`，见 `env/fix-run-start.txt` 与 `regression/canonical-after.log`）；
- `podman ps -a` 空；无残留 Broker/Fake/Controller 进程；
- 每个容器 `--network none --http-proxy=false --unsetenv-all`、`--user 65534:65534`、`--cap-drop ALL`、`no-new-privileges`、只读 rootfs（除显式 tmpfs）。

## 11. 环境指纹

| 对象 | 值 |
|---|---|
| rootfs canonical | `25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0` |
| deps canonical | `e07729d7997944417b1c25531749b3e6e5e34aa4248f01dc8f370282082ecb98` |
| stage（最终） | `fcdb0de442d455f89fe849c736679f831c15c50f76e3e4844d38f2963e3735b0` |
| DSH runtime | `1cc41d5a8745a5b9d47c8604e44f23eb8af2d8ca02b2afa0be101d5f71be6ea4`，182,717,632 B，`--version` = `0.2.2-rc.2` |
| DSH SDK wheel | `0.2.2rc2`；adapter build `dshLlmVersion=0.2.2-rc.2`，`synthetic=true` |
| adapter build | `lib/index.js` sha256 `2cb42461…`（20321 B）；`lib/index.d.ts` `d72067d3…`（1076 B） |
| Python | 3.11.15（`/root/.local/bin/python3.11`） |
| Node | v22.23.2（固定 rootfs 内 `/usr/bin/node`） |
| podman | 4.9.3；`podman ps -a` 空 |
| OS / kernel | Ubuntu 24.04.4 LTS / Linux 6.17.13-2-pve x86_64（宿主） |
| 容器 | 固定 rootfs，uid 65534，只读 rootfs，`--network none` |

## 12. 0-Key / 0-外部 HTTP / LiveGate 证据

| 检查 | 证据 | 结果 |
|---|---|---|
| 宿主 Key 环境变量 | `regression/absent-key-livegate.log` | 仅列变量名，`KEY_ENV_COUNT=0`；`.env` 不存在 |
| `run_live.sh` | 同上 | `RUN_LIVE_EXIT=3`（`SECURITY_BLOCKED`） |
| `LiveGate.inspect(live_requested=True, …)` | 同上 | `GateDecision(status='BLOCKED', reasons=('EXTERNAL_HUMAN_AUTHORIZATION_BOUNDARY_NOT_DEPLOYED',))` |
| bridge/Fake/run_c3 静态网络面 | `regression/network-static.log` | 仅 `AF_UNIX`；AF_INET/HTTP/Key 模式 0 命中（唯一命中是注释中的 "no AF_INET/HTTP"） |
| 运行期容器 | `commands.jsonl` 74 条原始 argv + PR1 append；`evidence/absence.json` | 全部 `--network none --http-proxy=false`；`key_env_found=[]`；`unexpected_env_found=[]`；`fake_receipts_http_calls=0`；adapter socket 固定 `/work/g3b/bridge.sock` |
| 测试专用 crash hook | `absence.json` | 仅 `G3B_TEST_MODE/G3B_CRASH_HOOK` 被识别为 test-only，不属于意外环境 |
| 真实 DSH trace | 51 个原始 `dsh-result.json` + PR1 `artifacts/g3c/pr1/traces/{echo,tool}/dsh-result.json` | `env.key_env=[]`；`network_families` 仅容器 loopback 族；Fake receipt 为本地文件 |
| 容器/进程残留 | `regression/container-absence-before.log`、`canonical-after.log` | `podman ps -a` 空；无残留 broker/fake/controller |

## 13. 证据路径索引

| 内容 | 路径 |
|---|---|
| 本报告 / Review Request / Findings | `docs/M0_G3C_IMPLEMENTATION_REPORT.md`、`docs/M0_G3C_REVIEW_REQUEST.md`、`docs/M0_G3C_FINDINGS_AND_DISPOSITION.md` |
| 证据矩阵（docs） | `docs/Autonomous_Teacher_M0_G3C_G3D_Test_Evidence_Matrix_v1.0.csv`（69 行） |
| 工作矩阵 + 汇总 | `artifacts/g3c/evidence/evidence-matrix-g3c.csv`、`summary-g3c.json`、`absence.json`、`correlation-g3c.jsonl` |
| 命令 | `artifacts/g3c/commands.jsonl`（74 条原始命令 + 12 条 PR1 append = 86 条；含 argv/UTC/exit/rootfs/deps/stage/容器） |
| 真实 DSH/reconcile/probe trace | `artifacts/g3c/traces/`（75 目录；51 DSH + 12 reconcile + 6 类 raw-UDS probe） |
| 账本/收据导出 | `artifacts/g3c/ledger/`（63）、`artifacts/g3c/receipts/`（51） |
| 日志 | `artifacts/g3c/logs/`（原始 92 + `pr1-*` + `coldstart-*`） |
| 本轮全量回归 | `artifacts/g3c/regression/`（原始日志 + JUnit + summary）；PR1 重跑 `artifacts/g3c/logs/pr1-*.log`、`artifacts/g3c/pr1-oci/` |
| PR1 并发冷启动证据 | `artifacts/g3c/evidence/concurrency-coldstart-20261117T153229Z.json`、`artifacts/g3c/logs/coldstart-20261117T153229Z/` |
| PR1 矩阵路径审计 | `artifacts/g3c/evidence/matrix-path-audit-pr1.txt`（before 25 missing → after 0；D 行 16 条不变） |
| PR1 真实 DSH 冒烟 | `artifacts/g3c/pr1/traces/{echo,tool}/dsh-result.json`、`artifacts/g3c/pr1/logs/{echo,tool}.log` |
| 环境 | `artifacts/g3c/env/`（run-start/fix-run-start/stage.json + 本轮 canonical） |
| 旧 C3-04A 失败证据 | `artifacts/g3c/traces/stream-slow/`、`artifacts/g3c/evidence/evidence-matrix-g3c.before-c3-04a-fix.csv` |
| Packet | `artifacts/review-packet-g3c-e6fde1cdf0bec9e957e98d569b257c8f17dfa363/`（`manifest.json`/`diff.patch`/`hashes.sha256`/`matrix/`/`evidence/`/`docs/`/`reproduce/`/`security-nonclaims.md`） |

## 14. 残余、限制与必须维护者决定的事项

1. **host-level ≠ real DSH**：C1-01B/C、C1-01D、C1-03B/D、C2-03A..E、C2-04、C3-01A/E、C3-02D/E、C3-03A..G、C3-04D 的证据是宿主 pytest（真实 socket/Broker/Fake 子进程），矩阵中逐行标注 `host-level (not DSH)`；不得写成真实 DSH。C1-04、C3-01B/C、C3-02A/B 是固定 rootfs 内的 **raw-UDS probe**（`probes_c3.py`，真实 Controller/Broker/Fake，无 DSH 客户端）；C2-02D/E 是 **container reconcile**（`reconcile_c3.py`）；C2-02A/B/C/F 的 crash 半是 real DSH、reconcile 半是 container reconcile。以上均不得合并为 real-DSH。
2. **D 行未做**：16 行 `NOT_RUN`；OS 边界仍 `BLOCKED`，无 candidate 攻击/内核拒绝证据。
3. **input token 为合成上界**：按 UTF-8 字节上界换算，`synthetic_fixture_only=true`；不是 tokenizer 精确计数，可能高估（保守），不得据此主张真实计费准确。
4. **断连不是 durable cancel**：客户端无 cancel 帧直接断连时，IPC 关闭生成器会 abort 并按 `stream_closed` 尝试 cancel，但没有独立、持久、可对账的“客户端断连”cancel 证据；provider 端也不可回滚。
5. **Recovery 依赖 receipt 文件/Broker 状态**：receipt 缺失或损坏 → `SETTLEMENT_UNCERTAIN`；Broker 不可达 → uncertain；不会自动重发，但也不会自动给出 settle 成功结论。
6. **post-send cancel 不保证退款/中止**：以已落地 receipt 的 authoritative usage 结算，否则 uncertain；不得主张“取消即免费”。
7. **OCI 2 项环境失败**：冻结 rootfs 无 `pgrep`、`/tmp` noexec 导致两个定向测试在 OCI 失败；宿主通过。属测试可移植性限制，需维护者决定是否在后续轮次改为不依赖外部工具/可执行 tmp。
8. **SRC-12 未修**：`next_logical_step` 仍不使用 `run_id`，但不在运行路径；如未来接入必须重写并复审。
9. **P2-4 专用 observation 表未使用**：当前以 Attempt journal 的 Observation 文档为唯一权威位置（含 digest/冲突拒绝）；`budget_provider_observations` 仍未写入。属于设计取舍 + 残余，须在 G3-C 裁定中确认可接受。
10. **G3-B P2-6 harness 启动抖动**：新 probes 以顺序/显式 barrier 运行，未复现旧的 15 s socket 等待；不是产品修复，若 Reviewer 要求应重建原始并发场景。
11. **真实 DSH 只验证到 adapter/controller/Fake 边界**：未验证真实 Provider 网络、远端幂等、账单；Fake usage/cost 是 synthetic fixture。
12. **Packet 不含 D0 设计文档**：D0 为只读输入，随独立 docs commit 归档；Packet 不复制 G3-B packet/artifacts。
13. **C1-01A 不是 real DSH**：C1-01A 是 raw-UDS replay 探针（`spikes/g3b-trusted-bridge/run_c3/probes_c3.py --probe replay`，`artifacts/g3c/traces/probe-replay/probe-result.json`，无 `dsh-result.json`），与 C1-04 共用同一份证据；任务书 C1-01 的 expected evidence 只要求 “new raw test stdout/trace + freeze SHA + independent replay”。本报告与 Findings 已删除“真实 DSH replay”措辞；如需 real-DSH replay 必须另跑并新增 trace，不能用本探针冒充。
14. **未做 real-DSH 双进程同 Claim**：PR1 的 20 轮双进程冷启动是 Controller/socket/Broker/Fake/SQLite 级（宿主 + 固定 rootfs OCI 测试），验证的是启动确定性与 singleton；真实 DSH 双客户端同 Claim 需要新的 barrier runner（`worker_c3.py` 每进程自带 Controller/admission，不能直接复用），本轮未新增。真实 DSH 冒烟只复跑 Echo/Tool；Resume/SIGTERM/Deadline/stream 等旧 trace 来自 `e6fde1c`，PR1 未逐条重跑。

## 15. 明确未主张

- **未主张** OS 隔离/信任边界通过；`OS_TRUST_BOUNDARY=B0-02=BLOCKED` 继续成立。
- **未主张** G3-D、G4、G5、Live、M0 GO 或任何生产可用性；本报告只请求 `PASS_FOR_G3C_NO_KEY_CONTRACT_RECOVERY_SCOPE`。
- **未主张** 真实 Provider 的 exactly-once、计费准确性、限流/超时行为；本地 Claim/Receipt 不等于远端证明。
- **未主张** 对 DSH runtime/插件/内核的完整安全审计；Guard 19/19 与 adapter 9/9 只是定向测试。
- **未主张** 历史 G3-B 裁定被本轮改变；G3-B packet/33 行矩阵/独立 Review/errata 未被修改或复制。

## 16. 复算入口

```bash
cd "/root/Autonomous Teacher"
git rev-parse HEAD                      # b2f6af054555705192c4e1ae3019a68078764736（PR1 fix）
git rev-parse b2f6af0^                  # 78be77c
git status --porcelain -uall            # 仅本任务 docs/scripts（提交前）
git diff --stat bb5bd0b..b2f6af0

# 宿主（禁止写 bytecode）
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:artifacts/foundation/deps \
  /root/.local/bin/python3.11 -B -m pytest tests/ -q -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:artifacts/foundation/deps \
  /root/.local/bin/python3.11 -B -m pytest tests/integration/g3c -q -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:artifacts/foundation/deps \
  /root/.local/bin/python3.11 -B -m pytest tests/integration/g3_bridge -q -p no:cacheprovider

# P1-2 20 轮双 Controller 冷启动（证据模式）
UTC=$(date -u +%Y%m%dT%H%M%SZ)
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:artifacts/foundation/deps \
  G3C_COLDSTART_EVIDENCE=artifacts/g3c/evidence/concurrency-coldstart-$UTC.json \
  G3C_COLDSTART_LOG_DIR=artifacts/g3c/logs/coldstart-$UTC \
  /root/.local/bin/python3.11 -B -m pytest \
  tests/integration/g3c/test_c3_05_twocontroller_coldstart.py -q -p no:cacheprovider

# 固定 rootfs / OCI（节点/DSH/全量）
bash scripts/g3c/run-node-tests.sh
bash scripts/g3c/run-oci-full.sh

# canonical
tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner \
  -cf - -C artifacts/security/rootfs . | sha256sum
tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner \
  -cf - -C artifacts/foundation/deps . | sha256sum
```
