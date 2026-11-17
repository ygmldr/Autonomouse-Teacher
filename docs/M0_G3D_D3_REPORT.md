# M0 G3-D3 — 跨 Principal Crash / Cancel / Recovery / Streaming Gate 报告

> **状态（自评）**：`D3_GATE_PASS`。D3-01、D3-C01..C12、D3-REG-01..04 共 17 行全部真实执行并通过；所有 crash/cancel/deadline 注入均为真实进程/内核动作，所有 trusted 恢复均为**新的真实 Trusted 进程**读取同一 state 后由产品 `reconcile_on_startup` 处理；未发现 P0（未授权发送、重发、假结算、误 FREE）。
> **不是**：Independent Review、D4/D5、G3-D 总 PASS、Live、G4/G5、M0 GO。`OS_TRUST_BOUNDARY=B0-02=BLOCKED` 继续成立。
> **执行身份**：D3 Recovery/Regression Agent（与 D1/D2 实现者不同身份；自行编写 D3 探针与判据）。
> **日期**：2026-11-17 ｜ **工作树**：`/root/Autonomous Teacher`
> **实现提交**：`ef84f57db93f4d8f9bd00dcb8e31ae2075995ace`（父 `bb34931`）→ `dc8214e` → **最终 `cf40c6bfb84ceae98e795db19efa955aa3035991`**
> **产品基线**：`4bd48037d98e081c8fb96a246f3fbf3cf60eb38b`；`git diff 4bd4803 cf40c6b -- src` **为空**
> **Stage**：`artifacts/g3d/stage-20261117T221955Z`（manifest `644823d46adaef28810ba13bb97547371616177bbc4b8138b1eaed5d9a28eb03`；tree `e1ff14496e06dcb1c887badfb93b858012373be9fe739e61bb04587885e9f9c5`；candidate `6c850e4b…` 6549 files / trusted `3a004bee…` 57 files）
> **证据根**：`artifacts/g3d/d3/`（`artifacts/` 被 gitignore，不进入产品 commit）

---

## 0. 结论先行

| 项 | 结论 |
|---|---|
| **D3 Gate** | **`D3_GATE_PASS`（自评，待 Lead 审计）**。13 个 case/suite 全部 PASS；17/17 矩阵行 PASS；所有单 run `exit 0`。 |
| **D3-01 组合回归** | PASS：真实 DSH Echo + `ATTEMPT_STARTED` 前 crash/恢复 + receipt-before-settle crash/恢复，三子 run 14/17/21 checks 全过。 |
| **C01 正常** | PASS：Echo 1、Tool 2、Resume 两个真实 candidate 进程共享 session（14→24 行，`reason:"resume"` 1），未回放旧 Attempt；DSH usage 与 receipt 字段级相等。 |
| **C02..C06 崩溃窗口** | 全部 PASS：0 未授权 Claim/Fake；C05 重启恰好补 1 次 settle；C06 以 Broker OK 为权威、无二次 settle、无 `WORST_CASE_HELD`。 |
| **C07 取消** | PASS：发送前取消不产生 Attempt/Fake且 Reservation 保守 PENDING；发送后取消 receipt/费用保守；双连接只取消一条，另一条 finish。 |
| **C08 断连/SIGTERM** | PASS：半关闭、半流断连、Trusted SIGTERM；socket/进程清理，最终状态保守，无 Fees=0、无伪造 Cancel 成功。 |
| **C09 Deadline/Watchdog** | PASS：Broker SIGSTOP 2.5219s、Fake 无帧 3.5147s、首帧 stall 0.8085s 均在有界时间内返回 `DEADLINE_EXCEEDED`；Trusted 未永久阻塞。 |
| **C10 Streaming** | PASS：真实 DSH 首 chunk（monotonic 估算 `1856889.8140`）早于 Fake exit（`1856891.8185`）**2.0045s**；不是 buffered replay。 |
| **C11 并发/同 Claim** | 真实 DSH 并发 PASS（两个容器同时 running，两个合法独立请求）；same-claim 负例 PASS（受控双 Controller/UDS，输家 `ATTEMPT_ALREADY_STARTED`）。二者证据级别分开，**不拼成 real-DSH same-claim PASS**。 |
| **C12 10+ 重启/压力** | PASS：10 次真实 Trusted 重启均 `ADMISSION_REPLAYED`（reconcile 后），账面 1/1/1/1 不变；cgroup `pids.max=8` / `memory.max=134217728`，fork 7 后 `EAGAIN(11)`。 |
| **REG-01 固定 OCI** | PASS：exit 0，**916 tests / 0 failed / 0 errors / 7 skipped / 4 explicit known deselects**；JUnit `3937cd12…`。 |
| **REG-02 Node** | PASS：guard 19/19，skill build + 8/8；Node v22.23.2。 |
| **REG-03 清理/canonical** | PASS：0 容器、0 残留进程；rootfs/deps/stage 前后一致；仅移除空的 `rootfs/evidence` mount target。 |
| **REG-04 账务** | PASS：24 个 case 证据目录、25 个 attempt 对、0 problems；两对 Digest 分开成立。 |
| **0-Key / LiveGate** | Host key-like env 0；`run_live.sh` exit 3；`LiveGate` BLOCKED（4 reasons 不变）；所有容器 `--network none`；无真实模型/HTTP/付费请求。 |
| **P0** | 未发现未授权发送、自动重发、假结算、误 FREE；未发现 Candidate 读取 Trusted state。 |

**STOP**：本 Agent 不进入 D4/独立复核，不 push/amend；等待 Lead 审计。

---

## 1. 身份、Stage 与运行环境

### 1.1 Git / 代码身份

| 项 | 值 |
|---|---|
| 起始 HEAD | `bb3493153656d0d06e2abdf713dd4a3450eb3295`，clean |
| D3 实现提交 | `ef84f57db93f4d8f9bd00dcb8e31ae2075995ace`，父 `bb34931` |
| OCI/测试修正提交 | `dc8214e0963018a3fa2ab26676d6a0f911841f3c` |
| 最终 HEAD | `cf40c6bfb84ceae98e795db19efa955aa3035991` |
| `src/` 改动 | **0**（`git diff 4bd4803 cf40c6b -- src` 为空） |
| 冻结面 | `spikes/`、`plugins/`、`scripts/g3c/`、`tests/integration/g3c`、`tests/integration/g3_bridge`、G3-C 历史证据/矩阵未改；D1-A `test_d1_socket_boundary.py` 保持基线字节 |
| 新增/修改 | `scripts/g3d/{d3_runner.py,run_d3_suite.py,d3_probes/**,lib_g3d.py,launch.py,build_stage.py,stage/candidate_entry.py}`、`tests/integration/g3d/test_d3_contract.py` |

### 1.2 Stage / Runtime

| 项 | 值 |
|---|---|
| 目录 | `artifacts/g3d/stage-20261117T221955Z` |
| Manifest SHA-256 | `644823d46adaef28810ba13bb97547371616177bbc4b8138b1eaed5d9a28eb03` |
| 整体 tree | `e1ff14496e06dcb1c887badfb93b858012373be9fe739e61bb04587885e9f9c5` |
| Candidate / Trusted tree | `6c850e4b1fb746314df2ebccfca7789179412e6797f35d78d53dfe2f239a0dc7` / `3a004bee14b412151f21abf2964c84d08528b4dc0c83835b694cf29784f33272` |
| 文件数 | trusted 57 / candidate 6549（含 6 个 `run/d3-probes/*.py`） |
| Adapter | `builtJs.sha256=2cb42461…`，`deterministic_match=true`，DSH SDK `0.2.2rc2`，Node `v22.23.2` |
| 产品来源 | `git archive 4bd4803`（Trusted）；Candidate 显式白名单 |
| Runtime | rootfs `25491e45…`、deps `e07729d7…`、Python 3.11.15、SQLite 3.50.4 |

Stage 构建时 HEAD = `cf40c6b`，工作树 clean；Stage 构建记录见 `artifacts/g3d/stage-20261117T221955Z/stage-summary.json`。

### 1.3 证据分级

| 级别 | 本报告中的使用 |
|---|---|
| **Level A（真实内核/进程/容器）** | 所有 Candidate SIGKILL/断连、Broker `SIGSTOP`、Trusted `SIGTERM`、cgroup 压力、真实 UDS、真实两个 Candidate 容器并发。 |
| **Level B（真实产品 Controller/Broker/Fake/DSH 协议）** | 真实 DSH Echo/Tool/Resume/Stream、真实 crash hook + 真实 restart/reconcile、same-claim 双 Controller/UDS 负例。 |
| **Level C（Host 只读对账）** | DB/Receipt/Claim/Attempt/Digest 的 Host 读取与矩阵汇总；不替代 A/B。 |

每个 case 目录有 `LEVELS.json`，并在 `summary.json` 中记录 `kind`、快照与 restart；`d3_runner` 的 Host 判据对原始文档/DB 再做一次断言。

---

## 2. D3-01 与 C01..C12 逐项结果

### 2.1 D3-01 组合回归（suite）

| 子 run | Run ID | 结果 | 关键观测 |
|---|---|---|---|
| C01 Echo | `20261117T222013Z-d3-c01-echo-4c96b579` | PASS 14/14 | 真实 DSH 1 套 `OK/SETTLED`，counter=1，usage==receipt |
| C04 | `20261117T222020Z-d3-c04-1b3840c3` | PASS 17/17 | `ATTEMPT_STARTED` crash → 新 Trusted reconcile → `SETTLEMENT_UNCERTAIN`，Fake=0，无重发 |
| C05 | `20261117T222036Z-d3-c05-1c910136` | PASS 21/21 | receipt-before-settle crash → 新 Trusted 恰好 settle 1 次，第二次重启 0 次 |

`D3-01` 的 argv 是上述三个命令的顺序组合；证据：`artifacts/g3d/d3/d3-01/{summary.json,results.jsonl,01-echo,04,05}`。

### 2.2 D3-C01 正常 Echo / Tool / Resume

| 子 run | Run ID | 结果 | 账本 |
|---|---|---|---|
| Echo | `20261117T222052Z-d3-c01-echo-b51d168e` | PASS 14/14 | 1 Reservation `OK` / 1 Claim `COMPLETED` / 1 Attempt `SETTLED` / 1 Receipt / counter=1 |
| Tool | `20261117T222059Z-d3-c01-tool-987c21a7` | PASS 19/19 | 2 套独立账本，mode `{tool_once,tool_final}`，counter=2 |
| Resume | `20261117T222106Z-d3-c01-resume-02297c40` | PASS 13/13 | 两个真实 candidate 进程；session `14→24` 行，`reason:"resume"` 1；2 SETTLED；无旧 Attempt 重放 |

Echo 的 DSH usage `{inputTokens:11,cacheReadTokens:2,cacheWriteTokens:0,outputTokens:5,reasoningTokens:0,totalTokens:18}` 与 receipt **字段级相等**；Tool/Resume 的每个 receipt 都在 DSH 两段 usage 中找到字段级相等项。两对 Digest 分别成立：`prepared==claim.request_digest`、`payload==receipt.raw_sha256`，且两值不互等。

### 2.3 C02..C06 崩溃窗口

| Case | Run ID | 结果 | Crash 快照 | 恢复后 |
|---|---|---|---|---|
| **C02** | `20261117T222407Z-d3-c02-3445c203` | PASS 11/11 | Candidate 连接后、发送前 `SIGKILL(137)`：0 Reservation/Claim/Attempt/Receipt/Counter | 同一 Trusted 仍 running，随后真实 DSH Echo 1 套 `SETTLED`(0.001022) |
| **C03** | `20261117T222424Z-d3-c03-16457539` | PASS 17/17 | hook `after_claim_before_attempt_start`：claim=1、Attempt=0、Receipt=0；Reservation `PENDING 0.00155`；intent `CLAIMED` | 新 Trusted 退出 3（reconcile 后 `ADMISSION_REPLAYED_AFTER_RECOVERY`），intent `HELD_UNCERTAIN/CRASH_BEFORE_SEND_NO_EVIDENCE`；无 Fake、无重发 |
| **C04** | `20261117T222440Z-d3-c04-e092597a` | PASS 17/17 | hook `after_attempt_start_before_fake_send`：Attempt `ATTEMPT_STARTED`、intent `CONSUMED`、Receipt=0、Reservation `PENDING 0.00155` | 新 Trusted：Attempt `SETTLEMENT_UNCERTAIN/NO_RECEIPT_AFTER_CRASH`；receipt/counter 不增；无自动发送 |
| **C05** | `20261117T222455Z-d3-c05-3a107d84` | PASS 21/21 | hook `after_response_before_settlement`：Attempt `RESPONSE_OBSERVED`、Receipt=1、Broker `PENDING`、broker messages=1 | 新 Trusted 验证 receipt+usage，settle 1 次（messages 1→2，Broker `OK 0.001022`，Attempt `SETTLED`）；第二次重启 settle 0 次，Receipt/counter 仍 1 |
| **C06** | `20261117T222511Z-d3-c06-6f10ba1a` | PASS 20/20 | hook `after_broker_settle_before_journal_mark`：Broker `OK 0.001022`（messages=2），Attempt `RESPONSE_OBSERVED` | 新 Trusted 以 Broker OK 为权威，直接 `SETTLED`；messages 仍 2（无二次 settle）；无 `WORST_CASE_HELD`；第二次重启不变 |

### 2.4 C07 取消

| 子 run | Run ID | 结果 | 观测 |
|---|---|---|---|
| before_send | `20261117T222115Z-d3-c07-before-1161f57a` | PASS 8/8 | Broker `SIGSTOP` 后请求进入 Reserve；cancel 后 Broker 恢复；client 收 `CANCELLED`；Attempt=0、Fake=0、Claim=0；Reservation `PENDING 0.00155`；intent `HELD_UNCERTAIN/PRE_SEND_ABORT:_Cancelled` |
| after_send | `20261117T222130Z-d3-c07-after-75c25b6f` | PASS 5/5 | slow_usage receipt 已落盘后 cancel；client `CANCELLED`；Attempt `SETTLED`，Reservation `OK 0.001022`，Receipt=1；**无 Fee=0** |
| two_streams | `20261117T222146Z-d3-c07-two-1b84e02a` | PASS 6/6 | 两个 UDS 连接：A 被取消（`CANCELLED`），B `finish`；2 Claim/2 Receipt，均 `SETTLED 0.001022` |

说明：产品 Controller 对 payload 处理是**单飞**（`_send_lock`），因此“双流”是两个连接、一个 active + 一个 queued，而不是两个并发 Provider 调用；取消一个后另一个独立完成。

### 2.5 C08 断连 / 半关闭 / SIGTERM

| 子 run | Run ID | 结果 | 观测 |
|---|---|---|---|
| half_close | `20261117T222202Z-d3-c08-half-55cb36b0` | PASS 5/5 | `shutdown(SHUT_WR)` 后请求仍完成；1 Receipt、`SETTLED 0.001022`，无 FREE |
| disconnect_mid_stream | `20261117T222219Z-d3-c08-disconnect-9b486a66` | PASS 5/5 | 客户端中途关闭；1 Receipt、`SETTLED 0.001022`；无伪造成功/Fee=0 |
| Trusted SIGTERM | `20261117T222237Z-d3-c08-sigterm-6fcfb566` | PASS 4/4 | 流进行中 SIGTERM；Trusted 退出、socket 消失；0 orphan broker/fake/controller；最终 Attempt `ATTEMPT_STARTED`、Reservation `PENDING 0.00155`、Receipt=1（保守，不伪造 Cancel 保证/Fee=0） |

### 2.6 C09 真实 Deadline / Watchdog

| 子 run | Run ID | 结果 | 注入 | 耗时 / 结果 |
|---|---|---|---|---|
| Broker SIGSTOP | `20261117T222253Z-d3-c09-broker-f8a7a4ba` | PASS 8/8 | 找到真实 broker 子进程并 `SIGSTOP`；请求在 Reserve 阻塞 | **2.5219s** 返回 `DEADLINE_EXCEEDED`；Trusted 仍 running；0 Reservation/Attempt/Receipt；仅 durable request-identity 行 |
| Fake no-frame | `20261117T222310Z-d3-c09-fake-f0c4d152` | PASS 7/7 | 真实 Fake `timeout`：receipt 已写、35s 无帧 | **3.5147s** 返回 `DEADLINE_EXCEEDED`；Attempt `SETTLEMENT_UNCERTAIN`、Reservation `PENDING 0.00155`、Receipt=1；未 settle |
| 首帧 Stall | `20261117T222328Z-d3-c09-stall-32de1fd6` | PASS 7/7 | 真实 Fake `slow_usage`：receipt 后 1.2s 才首帧，admission deadline=800ms | **0.8085s** 返回 `DEADLINE_EXCEEDED`；同样保守 uncertain |

### 2.7 C10 Streaming 首 Chunk 先于 Fake 退出

Run `20261117T222527Z-d3-c10-aa646faf`，PASS 17/17。

| 时间量 | 值 |
|---|---|
| DSH `stream_time0[0]` | `1794954332813` ms（真实 DSH runtime 的首 chunk 时间） |
| 换算为 host CLOCK_MONOTONIC（host realtime/monotonic 对） | `1856889.8140` |
| Fake `first_chunk_flushed.monotonic` | `1856889.8140` |
| Fake `exit_after_finish.monotonic` | `1856891.8185` |
| **T(first DSH chunk) < T(Fake exit)** | **是，提前 2.0045s** |
| Receipt mode / 账本 | `stream_slow`；1 Reservation/Claim/Attempt/Receipt，`SETTLED`；usage==receipt |
| Not buffered replay | `true` |

DSH `time0` 是 epoch ms；Host 用同一台机的 realtime/monotonic 采样换算，CLOCK_MONOTONIC 在容器间是同一内核时钟。该换算方式在 `stream/timing.json` 中完整记录，不把跨主机时钟排序当作结论。

### 2.8 C11 真实 DSH 并发与 same-claim 负例（证据分级）

| 子 run | Run ID | 结果 | 观测 |
|---|---|---|---|
| `d3-c11-real` | `20261117T222344Z-d3-c11-real-90c37567` | PASS 16/16 | 两个真实 Candidate 容器 **同时 running**；同 prompt、不同 session；2 个 identity（logical_step 0/1），`identity_digest` 与 `call_id` 两两不同；2 Claim/2 Attempt/2 Receipt，counter=2；两请求均 `SETTLED 0.001022` |
| `d3-c11-same` | `20261117T222351Z-d3-c11-same-7ffc3a8f` | PASS 14/14 | 受控双真实 Controller（两个 UDS：`bridge.sock`/`bridge2.sock`）+ 共享 AttemptJournal/Broker/Fake；两个客户端同 sessionId/messages/tools、均为 logical_step 0，同一业务 digest；**恰好 1 finish，1 `ATTEMPT_ALREADY_STARTED`**；1 Reservation/Claim/Attempt/Receipt，counter=1；2 个 admission 行 |

**证据级别与边界（不得合并）**：

- `d3-c11-real`：**Level A**（真实两个 Candidate OS 容器/同时运行）+ **Level B**（真实 DSH 协议）。因为 `sessionId` 属于 business digest，两个独立 DSH session 产生**不同** business digest，因此这是**两个合法独立请求**，不是“同请求重放”，更不是 real-DSH same-claim PASS。
- `d3-c11-same`：**Level B**（真实 Trusted Controller/UDS/Broker/AttemptJournal/Fake），但它是**受控 trusted Controller/UDS 同身份竞争负例**，不是两个真实 DSH 客户端。该负例证明不变量：至多一个 Claim/Attempt/Fake，输家得到精确稳定错误码 `ATTEMPT_ALREADY_STARTED`。
- 报告中**没有**把两者拼成“real-DSH same-claim”；`reg-04` 也只对两份独立证据分别对账。

### 2.9 C12 10+ 重启与资源压力

Run `20261117T222536Z-d3-c12-c68be9da`，PASS 62/62。

- 1 次真实 DSH Echo → 基线 1 Reservation/1 Claim/1 Attempt/1 Receipt/counter=1。
- **10 次**真实 Trusted 重启（每次新进程/新容器、同一 state）；每次 reconcile 后以 `ADMISSION_REPLAYED_AFTER_RECOVERY` 退出 3；每次快照 1/1/1/1 不变，0 新 Receipt/Claim。
- 每轮 `podman ps -a` 无残留；`rootfs/deps/stage` 每轮 canonical。
- 同 UID map 的 stress 容器：`pids.max=8`、`memory.max=134217728`、`cpu.max=100000 100000`；fork 7 个后 `EAGAIN(11)`；无 stress 容器残留。
- 最终账本仍 1/1/1/1，0 额外 Fake。

---

## 3. REG-01..04

| Case | 结果 | 实际观测 |
|---|---|---|
| **REG-01** 固定 OCI full | **PASS** | `exit 0`；**916 tests / 0 failed / 0 errors / 7 skipped / 4 explicit known deselects**。JUnit `artifacts/g3d/d3/reg-01/oci/junit-oci-full.xml`，sha256 `3937cd1283771bad787d8eb64cd54c6657154683c0d6f3b08c763f16745bb550`；argv/UTC/stdout/stderr 全部保存。 |
| **REG-02** Node Adapter/Guard/Skill | **PASS** | Node `v22.23.2`；`runtime-budget-guard` 19/19 exit 0；`skill-lookup` build exit 0、8/8 exit 0。Host 运行，不是 DSH candidate；adapter 的真实执行由 C01/C10/C11 Level B 覆盖。 |
| **REG-03** 清理/canonical | **PASS** | `podman ps -a` 空；0 `at-g3d-*` 容器；0 controller/broker/fake/candidate 残留；rootfs `25491e45…`、deps `e07729d7…`、stage `e1ff1449…` 前后一致；仅移除空的 `rootfs/evidence` mount target（root-owned/empty）；key-like env 0；`run_live.sh` exit 3；LiveGate BLOCKED（4 reasons）。 |
| **REG-04** 账务/Digest | **PASS** | 24 个 case 证据目录、25 个 attempt 对、0 problems；每个 `SETTLED` 对满足 `prepared==claim.request_digest`、`payload==receipt.raw_sha256`、两 Digest 不互等、Broker `OK` 且 cost>0；positive case 的 DSH usage==receipt usage。 |

### 3.1 REG-01 已知例外（显式分类，不是 PASS 隐瞒）

固定 OCI rootfs 无 `tar`/`git`，且以 uid 65534 运行；因此 4 个 host-root/tar 测试被**显式 `--deselect`**，每个都带 node id 与理由：

1. `test_manifest_tree_accepts_matching_stage`（rootfs 无 tar）
2. `test_manifest_tree_detects_unknown_extra_and_tamper`（rootfs 无 tar）
3. `test_manifest_tree_detects_symlink`（rootfs 无 tar）
4. `test_admission_launcher_uid_is_not_the_socket_peer_uid`（需要 host root 进程的 peer uid 0）

另有 7 skipped：5 个 root-only UDS/布局测试（rootfs 以 65534 运行）、1 个 `git` diff 测试、1 个既有“external public probe mount”skip。**0 个产品失败/错误**；Host pytest 已覆盖被 deselect 的 tar 树哈希与 root-only 契约。未修改 D1-A 冻结测试。

---

## 4. 不变量、P0 与账本对账

| 不变量 | 证据 |
|---|---|
| 无未授权发送 | C02 kill 快照 0/0/0/0；C03 claim 后 crash 0 Attempt/0 Fake；C09 broker stop 0 Reservation/Attempt；same-claim 输家 0 Reserve/Claim/Attempt/Fake |
| 无自动重发 | C03/C04 新 Trusted 只 reconcile，不调用 Provider；C05/C06 重启消息数 +1/0，Receipt 不增；C12 10 次重启 Receipt 不增 |
| 无假结算/误 FREE | 所有有 cost 的行 cost>0；C03/C04/C08/C09 保持 `PENDING`/`SETTLEMENT_UNCERTAIN`；C06 不降级为 `WORST_CASE_HELD` |
| 至多一个 Claim/Attempt/Fake（同 identity） | C11 same-claim：1/1/1/counter=1，输家 `ATTEMPT_ALREADY_STARTED`；C03 `g3b_request_identities` 只 1 行 |
| 两对 Digest 分开 | REG-04 25 对全部 `prepared==claim.request_digest`、`payload==receipt.raw_sha256`、两值不同；不合并成单一 digest |
| Usage/Broker/Receipt 一一对应 | C01 Echo/Tool/Resume、C10、C11-real、C12 的 DSH usage 与 receipt usage 字段级相等；Broker `OK`/cost 与 Attempt `SETTLED` 成对 |
| Rootfs/Deps/Stage 稳定 | REG-03 pre/post 三 hash 相同；每 case `cleanup.canonical` true |
| 容器/进程/socket 清理 | REG-03 0 容器/0 残留；C08 SIGTERM socket 消失；每 run `cleanup.ok=true` |

**P0 检查**：未发现 Candidate 直接读写 Trusted state、直接 Broker/Controller/Fake 访问、绕过 Controller Claim、重复发送、假 `settle`/`SETTLED`、误 `FREE` 或 `cost=0` 成功。

---

## 5. 测试与静态检查（实际执行）

| 套件 | 命令（摘要） | 结果 |
|---|---|---|
| `tests/integration/g3d` | `PYTHONPATH=src:artifacts/foundation/deps python3.11 -B -m pytest -q -p no:cacheprovider tests/integration/g3d` | **144 passed** |
| `tests/integration/g3_bridge` | 同上 `tests/integration/g3_bridge` | **31 passed** |
| `tests/integration/g3c`（冻结） | 同上 `tests/integration/g3c` | **110 passed** |
| `tests/unit/security/test_gates.py` | 同上 | **14 passed** |
| Host 合计 | — | **299 passed / 0 failed** |
| Ruff 0.17.5 | `ruff check scripts/g3d tests/integration/g3d` | **All checks passed** |
| 固定 OCI full | 见 REG-01 argv | **916 tests / 0 failed / 7 skipped / 4 deselects / exit 0** |

日志：`artifacts/g3d/d3/tests/{g3d,g3_bridge,g3c,gates,ruff}.log`；OCI 证据在 `artifacts/g3d/d3/reg-01/`。

---

## 6. 0-Key / 0 外网 / LiveGate

- Host key-like env 名 **0**；无 `.env`（仅 `.env.example`）。
- `bash scripts/run_live.sh` = **exit 3**；`LiveGate().inspect(live_requested=True)` = **BLOCKED**（4 reasons 不变）。
- 所有 D3 容器 `--network none --http-proxy=false --unsetenv-all`；Candidate `AF_INET/AF_INET6` 仍 `EACCES`（D2 边界证据未退化）。
- 没有真实模型、外部 HTTP、付费请求；Fake receipt `real_model_calls=0, http_calls=0, network_used=false`。
- 未 `podman pull`；Stage 构建/运行使用已有固定 rootfs。

---

## 7. 清理、canonical 与 Stage 不漂移

- 每个 case 独立 `$RUN`/容器名；结束 `podman ps -a` 空、`at-g3d-*` 0、controller/broker/fake/candidate 进程 0、socket 0、run dir 删除。
- 最终：rootfs `25491e45…`、deps `e07729d7…`、stage `e1ff1449…` 与 suite 前一致。
- REG-01 OCI 会在共享 rootfs 创建一个空 `rootfs/evidence` mount target；Host 在确认 root-owned 且为空后仅 `rmdir` 该目录（D-G0 已记录的同类瞬时漂移），未删除/改写任何其它路径；`reg-03/result.json` 有 `rootfs_runtime_cleanup` 证据。
- 历史 `artifacts/g3d/runs/uds-*`（非本 D3 Agent 产生）保留，不作为本 Gate 的清理对象。

---

## 8. 残余与未验证（不得写成 PASS）

1. **C11 same-claim 是受控 trusted 负例，不是 real-DSH same-claim**：DSH 公共接口不提供相同 sessionId/相同逻辑 step 的两个并发客户端；两个真实 DSH 独立请求因 `sessionId` 进入 business digest 而是不同身份。不得把两者合并成本 Gate 的 real-DSH same-claim PASS。
2. **C07 “双流”是单飞 Controller 下的两个连接**（一个 active、一个 queued），不是两个并发 Provider 调用；取消是 best-effort 契约。
3. **C09 Broker 只 SIGSTOP，不重启**：容器 teardown 会回收 stopped broker；本 case 不证明 Broker 进程级 crash/restart 的恢复语义（Broker DB 的所谓 crash 恢复由 C05/C06 的 Controller reconcile 覆盖，但不是 Broker 自身重启）。
4. **C08 SIGTERM 故意留下** `ATTEMPT_STARTED`/`PENDING` + receipt；未在本 case 证明重启后的自动结算（C05/C06 覆盖其它窗口）。
5. **C10 时间换算**：DSH `time0` 为 epoch ms，Host 用 realtime/monotonic 采样换算；CLOCK_MONOTONIC 是同一 Host 内核，不跨主机。
6. **OCI 4 个 deselect、7 个 skip**：rootfs 无 tar/git、uid 65534；已在 REG-01 显式分类，Host pytest 覆盖 tar/root 契约，但 OCI 本身没有执行这 4 个测试。
7. **C12 的重启不服务新请求**：10 次重启均在 reconcile 后以 `ADMISSION_REPLAYED` 退出；这是“恢复旧状态”而不是“继续接单”。要接新请求需新 admission，未在本 case 证明。
8. **Node 测试是 Host 运行**：不是 DSH candidate 内 Node；真实 adapter 执行由 C01/C10/C11 的真实 DSH 覆盖。
9. **无独立 Reviewer**：本报告只是 D3 执行 Agent 自评；D4 Reviewer 必须自建关键负例并核对原始证据。
10. **Local-only**：单机 rootful Podman 4.9.3 + crun 1.14.1 + LXC kernel；不可外推到其它 Runner；内核/运行时 0day、宿主 root、供应链不在本 Gate 主张内。
11. **LiveGate 仍 BLOCKED**：本 Gate 不授予 Live/G4/G5；`OS_TRUST_BOUNDARY=B0-02=BLOCKED` 不变。

---

## 9. 证据索引（`artifacts/g3d/d3/`）

```text
canonical-pre.json / cases.json / final.json / summary rollups
d3-01/ d3-c01/ d3-c07/ d3-c08/ d3-c09/ d3-c11/   suite summary/results
d3-c02/ … d3-c12/                                 单 run summary/checks/state/probes/recover
reg-01/ {result.json,oci-full.{stdout,stderr}.txt,oci/junit-oci-full.xml,project/}
reg-02/ {result.json,guard-tests.stdout.txt,skill-tests.stdout.txt}
reg-03/ result.json
reg-04/ result.json
tests/ {g3d,g3_bridge,g3c,gates,ruff}.log
```

每个 case 子目录含：`summary.json`、`checks.json`、`LEVELS.json`、`env/`（git/preflight/canonical/stage/livegate）、`run/`（argv/inspect/logs）、`uid-map/`、`mountinfo/`、`socket-stat/`、`state/{pre,crash,restart-*,final}.json`、`db/`、`receipt/`、`recover/` 或 `probes/`、`cleanup/`。

---

**STOP**：D3 Gate 材料已交付；本 Agent 不进入 D4、不独立复核、不 push、不 amend。等待 Lead 审计。
