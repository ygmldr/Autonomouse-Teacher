# M0 G3-C Findings and Disposition

> 逐条映射：SRC-01..SRC-12、G3-B Independent Reviewer P1-1/P1-2/P2-1..P2-7、C3-04A、host-level vs real-DSH、G3-D 未做事项。
> 身份：Base `bb5bd0b`；G0 `e107e22`；impl `e6fde1c`。状态标签：`FIXED_CLOSED`（修复且有动态证据）、`FIXED_RESIDUAL`（修复但保留明确残余）、`DOCUMENTED_RESIDUAL`（不改/记录）、`ENV_LIMITATION`（环境限制）、`NOT_DONE`（范围外）。
> 本文件不代替独立 Reviewer 裁定；所有 `PASS` 均为 Owner 侧无 Key 证据判定。

## 1. SRC-01..SRC-12

| ID | 状态 | 本轮修复/处置 | 证据 | 残余 / 为什么可接受 |
|---|---|---|---|---|
| SRC-01 usage 丢失、重启只 hold | `FIXED_CLOSED` | `mark_response_observed` 持久完整 `m0.g3c.observation.v1` 文档（usage/observation/digest）；reconcile 校验 `journal_digest`、读 Broker `reservation_status`，authoritative → `settle`，partial/invalid → `fail` | C2-02A/B（after crash → `SETTLED`，fake 不增）；C2-02F（partial → `WORST_CASE_HELD`）；C2-02E（两次 reconcile 幂等） | 文档缺失/损坏/无 receipt → `SETTLEMENT_UNCERTAIN`（C2-02D、C2-03C）。这是有意的失败关闭，不低计、不重发 |
| SRC-02 cancel 非功能 | `FIXED_CLOSED` | `cancel(*, transport_id, reason)` + per-transport 状态 + checkpoint；发送前零发送，发送后按 receipt 结算/uncertain；错误签名记录不吞 | C3-01A/B/C/E；C3-01D；C3-03G | 发送后无法回滚 Provider；断连不是 durable cancel（见 §4）。cancel 是 best-effort、账务保守，符合冻结契约 |
| SRC-03 Fake usage 与账本不同源 | `FIXED_CLOSED` | Fake `usage` 帧与 receipt usage 强制 canonical 相等；DSH 收到 `chunk.type=usage`；Observation/账本同源 | C2-01A（`usage_equal=True`）；C2-01D；C1-02（五类坏 usage） | usage 是 synthetic fixture，不是真实账单 |
| SRC-04 admission 边界未执行 | `FIXED_CLOSED` | `max_output_tokens` 比较；输入 UTF-8 bytes 上界；`deadline_ms` 进入 checkpoint/Broker/Fake 超时 | C1-03A/C/E/F；C3-02B/C | 输入 token 为保守合成上界（可能高估），非 tokenizer |
| SRC-05 Broker 无读超时 | `FIXED_CLOSED` | `select` + 单调 deadline + 回复长度上界；超时标记 client 不可信 | C3-02A（1 次请求、1.62 s、`BROKER_TIMEOUT`、fake=0） | 只覆盖本地 Broker 子进程；远端超时未验证 |
| SRC-06 首帧/连接/线程无界 | `FIXED_CLOSED` | 首帧 deadline、连接上限 8、`TOO_MANY_CONNECTIONS`、线程回收、watchdog、响应上限 | C3-03A/B/C/D/E/F/G；`probe-ipc-bounds`；C3-02D | 资源压力证据主要在 host/容器定向探针，不是真实 DSH 高并发 |
| SRC-07 跨连接响应预算污染 | `FIXED_CLOSED` | 每连接状态 `_ConnectionContext`；预算不共享 | C3-03D/E | — |
| SRC-08 max_calls 被无效请求消耗 | `FIXED_CLOSED` | `calls` 在 prepare 成功 + 身份登记后递增；`rejected_calls` 独立 | C1-03B（无效不消耗）；C1-03C（第二次 `BUDGET_DENIED`） | — |
| SRC-09 Broker 冲突码降级 `UNKNOWN_FIELD` | `FIXED_CLOSED` | 有限新增码 `BROKER_*`/`DEADLINE_EXCEEDED`/`TOO_MANY_CONNECTIONS` + 显式映射 + Envelope 校验 | C1-01A/B/C/D；C1-04；Node adapter TAP #5 | 有意不透传任意 Broker 原始码，避免协议面扩大 |
| SRC-10 finish(error) schema 不合法 | `FIXED_CLOSED` | `_terminal_events` 统一 `finish(error, failure{code,message})`；非 authoritative 绝不发成功 finish | C1-02（五类终态）；C2-01C | — |
| SRC-11 非增量 streaming | `FIXED_CLOSED` | Fake 逐帧 yield；Controller worker + 有界队列 + IPC generator；receipt-first 后转发 | C3-04A（T1<T2，lead 1999 ms）；C3-04B/C/E | 见 §3；仅有 `stream-slow` 这一条真实 DSH 正向增量证据 |
| SRC-12 `next_logical_step` 不用 `run_id` | `DOCUMENTED_RESIDUAL` | **未改**。确认只被测试引用，不在运行路径；加注释 + 测试锁定运行时不得调用 | C2-04c（monkeypatch 抛错仍成功） | P2 非运行路径；如未来接入必须重写 SQL 并重新评审。任务书允许先确认运行路径 |
| SRC-12（判定） | 维护者决定 | 若要求“零残余”，需新增 commit 修复并重跑 C2-04；当前 G3-C 不以此作为 PASS 前提 | — | 当前处置：记录为 P2 残余，不扩大范围 |

## 2. G3-B Independent Reviewer findings

| ID | G3-B 问题 | 本轮状态 | 处置与证据 | 残余 / 可接受性 |
|---|---|---|---|---|
| P1-1 | B3-08 只保守 `WORST_CASE_HELD`，非幂等 settle | `FIXED_CLOSED` | Observation/usage 持久化 + reconcile 校验 + Broker 权威状态 → 幂等 `settle`；C2-02A/B/E | receipt 缺失/损坏仍 uncertain（有意的保守）；不低计、不重发 |
| P1-2 | cancel no-op，TypeError 被吞 | `FIXED_CLOSED` | 新 cancel 契约、传播、错误签名日志；C3-01A/B/C/E、C3-03G | 发送后不可回滚 Provider；断连非 durable cancel |
| P2-1 | Broker 冲突码 `UNKNOWN_FIELD`，B3-05 `CLAIM_DENIED` 未复现 | `FIXED_CLOSED` | 新增 `BROKER_*` 码 + 映射；replay 得 `ATTEMPT_ALREADY_STARTED`；C1-01A-D、C1-04 | 未再声称 B3-05 的 `CLAIM_DENIED` 原文；以新码为准 |
| P2-2 | 非 authoritative finish 缺 `failure` | `FIXED_CLOSED` | `_terminal_events` 统一 failure；C1-02 | — |
| P2-3 | `max_calls` 被无效请求消耗 | `FIXED_CLOSED` | 递增位置后移 + `rejected_calls`；C1-03B/C | — |
| P2-4 | observation 表未使用 | `DOCUMENTED_RESIDUAL` | 设计取舍：Attempt journal 的 `m0.g3c.observation.v1` 文档为唯一权威 observation（含 digest、冲突拒绝）；`budget_provider_observations` 仍不写入 | 若维护者要求专用表，需 G3-D/后续轮次做双写/迁移；当前有 C2-03A-E 冲突与一致性测试 |
| P2-5 | B3-07 reconcile 快照被第二次覆盖 | `FIXED_CLOSED`（证据结构） | G3-C 每个 case 独立 `reconcile1/2` 目录（`reconcile-after-response_before_settlement`、`reconcile2-after-response`），不再覆盖；C2-02E | 旧 G3-B trace 未改；新证据可追溯 |
| P2-6 | 并发 harness 启动抖动 | `DOCUMENTED_RESIDUAL` | 新 probes 顺序/显式 barrier 运行；C3-01C 并发 cancel 成功 | 未复现旧 15 s socket 等待；不是产品修复，若 Reviewer 要求需重建原场景 |
| P2-7 | recovery 需新 admission，契约未文档化 | `FIXED_CLOSED` | 冻结“先 reconcile、后登记 admission”；`ADMISSION_REPLAYED_AFTER_RECOVERY` exit 3；C2-04a/b/c | 启动顺序是 launcher 契约，已在控制台错误与测试中固定 |
| P2-8 | Reviewer 工具 `-shm` 事件（非 Owner finding） | N/A | 本轮 Packet 构建/复核明确禁止 `sqlite3` CLI 打开副本 | — |

## 3. C3-04A 修复前后

| 项 | 修复前 | 修复后 |
|---|---|---|
| trace | `traces/stream-slow`（保留） | `traces/stream-slow-fixed` |
| Fake first chunk (ms) | 1794919995471 | 1794922997899 |
| Fake exit `T2` (ms) | 1794919997472 | 1794922999899 |
| DSH first chunk `T1` (ms) | 1794919997481 | 1794922997900 |
| `T1<T2` | **False**（lead −9 ms） | **True**（lead +1999 ms） |
| 判定 | **FAIL**（“buffered until settlement”，不得称为 real-time） | **PASS**（首 chunk 在 Fake 运行时到达 DSH） |
| 矩阵 | `evidence-matrix-g3c.before-c3-04a-fix.csv` 原样 | 现行工作矩阵 / docs 矩阵 C3-04A |
| 修复 | — | `3675a41`：worker thread + 有界 queue + generator 逐帧 yield；receipt-first；cancel/backpressure 处理 |

**注意**：旧 trace 与旧矩阵从未被覆盖；`*-fixed` 是后置证据。`C3-04B/C/E` 及 `echo/tool/usage/crash/reconcile/sigterm` 在修复后重跑；其余未受影响的证据保留原名。

## 4. host-level vs real-DSH 标注

矩阵中以下行明确是**宿主 pytest（真实 socket/Broker/Fake 子进程，但不是真实 DSH）**，不得写成 real-DSH：

`C1-01B`、`C1-01C`、`C1-03B`、`C1-03D`、`C2-03A..E`、`C2-04`、`C3-01A`、`C3-01E`、`C3-02D`、`C3-02E`、`C3-03A..G`、`C3-04D`（共 22 行）。

其余真实 DSH 行（`C1-01A`、`C1-02`、`C1-03A/C/E/F`、`C1-04`、`C2-01A..D`、`C2-02A..F`、`C3-01B/C/D`、`C3-02A/B/C`、`C3-04A/B/C/E`、`C-END-01`）在固定 rootfs 容器内由 `spikes/g3b-trusted-bridge/run_c3/worker_c3.py` 驱动真实 DSH 0.2.2-rc.2 + Fake Provider + 真实 SQLite Broker 产生；仍**不是**真实模型/远端 Provider。

**断连 cancel 限制**：客户端无 cancel 帧断连时，IPC 关闭生成器会 abort，并仅在 worker 仍存活时调用 `cancel(transport_id, "stream_closed")`；没有独立的 durable“断连”事件/对账记录，provider 也不能回滚。因此不得把断连当作 cancel 契约的完整覆盖（已写入报告 §14、Review Request R2.8）。

## 5. G3-D 未做事项（16 行 NOT_RUN）

| 组 | 行数 | 状态 | 说明 |
|---|---:|---|---|
| G3-D0 设计冻结 | 1（D0-01） | `NOT_RUN` | D0 设计文档为只读输入（`docs/M0_G3D_OS_BOUNDARY_DESIGN.md`，1326 行，原字节另 commit 归档）；本 Agent 不实现、不签核 |
| G3-D1 OS 隔离/正连 | 1（D1-01） | `NOT_RUN` | 未创建不同 OS 主体、未做 candidate 拒绝/正向 DSH |
| G3-D2 恶意候选 | 12（D2-01..12） | `NOT_RUN` | 未执行读 Broker/Policy/Admission/Attempt/Receipt、越权 Claim、socket/文件攻击等 |
| G3-D3 跨主体故障 | 1（D3-01） | `NOT_RUN` | 未执行 dual-principal crash/cancel/replay/watchdog |
| G3-D Review | 1（D-REVIEW-01） | `NOT_RUN` | 无独立 D Review |

结论：`OS_TRUST_BOUNDARY=B0-02=BLOCKED` 继续成立；G3-C 文档/矩阵不得被解释为 D 的通过证据。

## 6. 环境失败与处置

| 失败 | 位置 | 性质 | 处置 |
|---|---|---|---|
| host `test_required_files_exist_and_are_read_only_text` | `tests/integration/runtime/test_target_profile_static.py` | 宿主 `config/dsh/*.yml` 可写；OCI 内 0444 通过 | 既有宿主环境限制；未改宿主代码/权限；如实记录 |
| host `test_all_live_entrypoints_remain_blocked` | `tests/integration/sandbox/test_live_controller_no_key.py` | 子进程硬编码 `PYTHONPATH=/project/src`，宿主无 `/project`；OCI 内通过 | 既有 G3-B 环境限制；不掩盖、不改测试断言 |
| OCI `test_c3_01e_sigterm_cleans_socket_and_broker_child` | `tests/integration/g3c/test_c1_03_admission.py` | 冻结 rootfs 无 `pgrep`，探针无法启动 | 产品语义在宿主通过；建议后续改为不依赖外部 `pgrep`（维护者决定） |
| OCI `test_c3_02a_broker_alive_without_stdout_times_out_once` | `tests/integration/g3c/test_c3_02_deadline.py` | `/tmp` noexec，`slow-broker-wrapper` 无法 exec | 宿主通过；建议后续把 wrapper 放到可执行 tmpfs 或改用 `python -c`（维护者决定） |

这四项均非产品断言失败；OCI 计数实际为 768 passed / 2 failed / 1 skipped（不是旧记录 766/2）。工作矩阵 `C-END-02` 与 docs 矩阵已按新回归更新，旧 `evidence-matrix-g3c.before-c3-04a-fix.csv` 保留旧数字。

## 7. 需维护者/Reviewer 明确决定的事项

1. SRC-12 是否接受为 P2 记录性残余（不在运行路径）。
2. P2-4 专用 observation 表是否必须双写；当前以 Attempt journal 文档为权威。
3. OCI 两项测试可移植性是否在本轮后修复（不影响 C 语义，但影响“OCI 全绿”）。
4. 断连 cancel 是否需要 durable 事件（当前仅 best-effort abort）。
5. 是否接受 `input token` 为合成保守上界，而非 tokenizer 精确值。
6. 是否要求 Packet 附 D0 设计文档副本（当前按“不复制 G3-B/历史”原则不复制；D0 原字节由独立 docs commit 归档）。

以上 1–6 均不应被默认解释为 PASS；请 Reviewer 在裁定中逐项表明是否影响 `PASS_FOR_G3C_NO_KEY_CONTRACT_RECOVERY_SCOPE`。
