# M0 G3-C Independent Review（独立复核）

> **Reviewer**：独立 G3-C Reviewer（未参与 G3-C 实现/证据生成，未复用 Owner 测试或结论句）。
> **日期**：2026-11-17（UTC）。
> **冻结身份**：Base `bb5bd0bf83e22130ed0d81c54f54a4673654cfe3`；G0 `e107e22d32ee0fd25c597a95ae447898f4a52a85`；Implementation `e6fde1cdf0bec9e957e98d569b257c8f17dfa363`；docs HEAD `78be77c3c63fce62527dccd7ec8c1458047d81bf`。
> **Packet**：`artifacts/review-packet-g3c-e6fde1cdf0bec9e957e98d569b257c8f17dfa363/`（`sha256sum -c` 1713/1713 OK，1715 files）。
> **范围**：C1 协议/错误语义/Admission；C2 Usage/Receipt/Observation/Recovery；C3 Cancel/Deadline/IPC 资源/增量 Streaming；无 Key 集成与回归；Packet/矩阵/证据索引。
> **不在范围**：G3-D0/D1/D2/D3（16 行 `NOT_RUN`；`OS_TRUST_BOUNDARY=B0-02=BLOCKED`）、真实 Provider/Key/模型/外网/Live、G4/G5/M0 GO。
> **最终裁定**：**`PARTIAL`**（见 §9）。这不是 G3-D/Live/G4/G5/M0 GO，也不是 OS 边界通过。

---

## 0. 结论摘要

1. **产品语义路径独立复核通过**：我在自己的 11 类恶意探针、14 次固定 rootfs 真实 DSH 复跑、15 例 SQLite/Receipt 对账中，没有发现 P0：没有未授权/重复发送，没有 Fake 已收却写成 FREE/NOT_DISPATCHED，没有假结算或二次 settle，没有丢失保守账本，没有失败后的成功 finish，也没有绕过 Claim 的发送路径。
2. **但 Owner 的“真实 DSH”证据覆盖与证据索引存在 P1 级缺陷**：
   - `docs/M0_G3C_IMPLEMENTATION_REPORT.md:83` 声称“真实 DSH replay ...（C1-01A）”，但在 **Owner 证据**中唯一含 `ATTEMPT_ALREADY_STARTED` 的证据是 **raw-UDS** 的 `artifacts/g3c/traces/probe-replay/probe-result.json`（`probes_c3.py --probe replay`，没有 `dsh-result.json`，没有 DSH）。C1-01A 行没有 argv/log，引用的 `artifacts/g3c/traces/C1-01A` 不存在。
   - `docs/M0_G3C_FINDINGS_AND_DISPOSITION.md:61` 的“真实 DSH 行”列表中有 8 行不是真实 DSH：C1-01A（summary/no run）、C1-04（raw-UDS）、C2-02D/E（container reconcile，无 DSH）、C3-01B/C（raw-UDS）、C3-02A/B（raw-UDS）。
   - 53 个 PASS 行中有 **25 行**的 `db_or_receipt_path` 指向不存在的占位路径（如 `artifacts/g3c/traces/C1-01A`、`C3-03A..G`、`artifacts/g3c/evidence/junit-g3c-only.xml`）；C1-01A 与 C-END-01 还没有 `command_argv`/`log_path`。
3. **两个真实 Controller 进程同时冷启动共享 AttemptJournal 时存在并发缺陷**：6 次同时冷启动中 3 次有一个进程在 `AttemptJournal.__init__` 的 `PRAGMA journal_mode=WAL`（`attempts.py:58`）抛出未处理的 `sqlite3.OperationalError: database is locked`。它没有造成第二次发送（Fake 仍 1），但不是 R2 要求的“第二个进程确定性拒绝”。预初始化 DB + barrier 后的 Claim 竞争是正确的：一个成功、另一个 `ATTEMPT_ALREADY_STARTED`。
4. **因此不能签 `PASS_FOR_G3C_NO_KEY_CONTRACT_RECOVERY_SCOPE`**：产品语义本身通过独立复验，但证据标注/索引和双进程冷启动必须先修正或缩小主张；按 Review Request 的枚举，这属于 `PARTIAL`，不是含糊的“全面 PASS”。
5. **未验证**：G3-D 全部 16 行仍 `NOT_RUN`；OS 边界仍 `BLOCKED`；真实 Key/模型/远端 exactly-once/账单未验证；真实 DSH replay 未由我复跑（只做了 raw-UDS replay）；双进程真实 DSH 同 Claim 未跑；host-level 22 行仍是宿主 pytest。

---

## 1. Reviewer 独立性 / 方法

- 我从冻结的 Git blob、Packet 原始字节和**自己新建的探针/运行**复核；没有导入或复用 `tests/integration/g3c` 的测试模块，没有修改任何产品代码/测试/脚本/已有 docs/artifacts/Packet。
- 我的探针与运行只写在 `artifacts/reviewer-g3c/` 与 `docs/REVIEW_G3C_INDEPENDENT.md`；`artifacts/` 在 `.gitignore` 中（`artifacts/`），所以证据目录需要 Lead 归档时显式加入。
- 宿主命令统一 `PYTHONDONTWRITEBYTECODE=1 ... /root/.local/bin/python3.11 -B`；容器统一固定 rootfs、`--network none --http-proxy=false --unsetenv-all`、`--read-only --read-only-tmpfs=false`、`--user 65534:65534`、`--cap-drop ALL --security-opt no-new-privileges`。
- 真实 DSH 只用固定 rootfs 里的 `worker_c3.py`/`reconcile_c3.py` 驱动；raw-UDS 探针从不写成 DSH；host pytest 从不写成 real-DSH。
- **未使用任何真实 Key/模型/外部付费 HTTP**；所有 Fake usage 是 `synthetic_fixture_only`，不是供应商账单。

---

## 2. R0 — 身份、漂移、范围（独立命令）

| 检查 | 结果 | 证据 |
|---|---|---|
| `git rev-parse` HEAD/base/G0/impl/docs | `78be77c…` / `bb5bd0b…` / `e107e22…` / `e6fde1c…` / `78be77c…` | `r0-identity/identity.txt` |
| commit parents | G0 父 `7199058`；impl 父 `3675a41`；docs 父 `dd4bf40` | 同上 / `manifest.json` |
| `git diff --binary bb5bd0b..e6fde1c \| sha256sum` | `6b33cd74bfee871f2e805ad1fc0db4077121d325085f4c9713007247db3fcd80` = `manifest.diff_sha256` | `identity.txt` |
| Packet `sha256sum -c hashes.sha256` | 1713/1713 OK，exit 0；复核前后各一次 | `/tmp/g3ccheck.out`；`identity.txt` |
| Packet `file_count` | 1715 = 磁盘 1715；1713 payload + `hashes.sha256` + `packet-integrity-report.txt` | `identity.txt` |
| `docs_sha` | `78be77c` 含四份 docs/matrix；Packet docs 字节 == Git blob；Packet matrix == docs matrix | `matrix-protected.txt` |
| 受保护产品文件 | `src/autoteacher_m0/security/gates.py`、`src/autoteacher_m0/runtime/dsh_adapter.py`、`scripts/run_live.sh` 三处 base=impl=worktree；`git diff` 空 | `R0.md`、`identity.txt` |
| G3-B packet / 33 行矩阵 / REVIEW_G3B / errata | G3-B packet `sha256sum -c` 706/706；docs 文件 `git diff` 空 | `R0.md`；`/tmp/g3bcheck.out` |
| 矩阵 69 行 | 53 PASS / 16 NOT_RUN；53 行 `impl_sha=e6fde1c…`；`reviewer_verdict` 全空；D 行 16 条原样 `NOT_RUN`，与归档 66 行矩阵的 D 行 **raw line 完全一致** | `matrix-protected.txt` |
| LiveGate | `run_live.sh` exit **3**（`SECURITY_BLOCKED`）；`LiveGate().inspect(live_requested=True)` = `BLOCKED` | `r0-identity/livegate.txt` |
| Key/`.env` | Key env 数量 0；`.env` 不存在 | `network-key-scan.txt` |
| 网络/外部 HTTP | Owner 74 条 + Reviewer 14 条容器 argv 全部 `--network none --http-proxy=false`；静态网络面仅 `AF_UNIX`（其余为注释）；Fake receipt `http_calls=0` | `network-key-scan.txt` |
| canonical | rootfs `25491e45…`、deps `e07729d7…`、stage `fcdb0de4…`，前后一致 | `final-canonical.txt` |
| `podman ps -a` | 空 | `final-canonical.txt`；R3/OCI/Node summary |

**R0 发现（程序性，不是产品 P0）**：
- Review Request 写的 `security/gates.py`、`runtime/dsh_adapter.py` 路径在仓库中不存在；实际文件在 `src/autoteacher_m0/security/gates.py` 与 `src/autoteacher_m0/runtime/dsh_adapter.py`。我用实际路径核对了 SHA，未改文件。
- `LiveGate` 的 reasons 与 Owner 文字不完全相同（我未传 baseline 参数，额外得到 `BASELINE_EVIDENCE_MISSING` 等）；状态仍为 `BLOCKED`，不影响 no-Live 结论。

---

## 3. R1 — 静态复验（发送入口反向追踪）

完整逐项记录见 `r1-static/R1_STATIC.md`。核心结论：**发送链唯一、必须有 Claim、失败关闭；未发现旁路。**

### 3.1 发送许可链

- Fake 唯一可执行入口：`controller.py:861-870`（`fake.stream`）与 `controller.py:882`（`send_exact_bytes` 兼容 fallback）。`rg` 未发现其他 Fake spawn/`Popen`。
- 顺序（`controller.py:602-813`）：quota → `_prepare_checked`（`305-380`）→ durable identity（`620-628`）→ Broker Reserve（`647-650`）→ `record_intent`（`651-654`）→ `claim_dispatch_for_request`（`666-673`）→ `begin_attempt`（`683-689`）→ `before_send` checkpoint（`691`）→ `TrustedEgressTransport.dispatch`（`756`）→ receipt/observation/settle（`767-806`）→ terminal（`813`）。
- `TrustedEgressTransport.dispatch` 先 `consume_permission`（`egress.py:751-756`），permission 必须由 `EgressBoundary.claim_dispatch_for_request` 创建（`egress.py:543-605`）；legacy `claim_dispatch` 不被 Controller 使用（只有 `egress.py:528` 的兼容 API 与 `_claim_with` 内部）。
- 结论：无 legacy/descriptor-only/直 spawn 旁路；伪造/复制的 `DispatchPermission`、篡改 reservation 均在 provider 前失败（p1 实测）。

### 3.2 Admission

- `calls` 只在 prepare 成功 + 身份登记后递增（`controller.py:616-628`）；invalid 只增 `rejected_calls`（`617-619`）。
- `max_output_tokens` 与请求比较（`309-314`）；输入用 canonical UTF-8 字节上界（`341-352`）；`deadline_ms` 进入 checkpoints、Broker 与 Fake（`220-221,399,646,852-898`）。
- 自授权字段被拒并映射 `ADMISSION_SELF_AUTH_DENIED`（`405-413`）；route/model/tool schema 均校验（`307-308,325-340`）。
- `admission.py:70-123` 校验 launcher uid/container/scope/expiry；`AttemptJournal.register_admission` 原子消费（`attempts.py:98-105`）。

### 3.3 错误码与 Finish schema

- `protocol.ERROR_CODES` 固定（`protocol.py:26-46`）；`BROKER_ERROR_CODE_MAP` 六个 raw code（`50-57`）；`normalize_broker_error_code` 未知→`BROKER_ERROR`（`60-74`）；`validate_error_payload` 强制 enum（`443-446`）。
- Controller `broker_protocol_code` 有限映射（`controller.py:105-121`）；forged Broker code 的映射由 p2 记录。
- `validate_finish_payload`：error/aborted 必须 `failure{code,message}`（`protocol.py:305-323`）；`_terminal_events` 对非 authoritative 只发 `finish(error)`（`controller.py:1051-1074`）。
- `finish.failure.code` 是诊断文本（如 `USAGE_MISSING`），不是 error-envelope enum；这与冻结 finish schema 一致，不作为缺陷。

### 3.4 Cancel / Deadline

- per-transport `_CancelState` + 有界 prune（`controller.py:242-298`）；terminal 后新流重新建 state，不继承旧 cancel。
- checkpoints：admission/prepare/before-after reserve/after claim/before send（`611,629,646,657,675,691`），provider 前与 Fake 帧间也检查（`713-716`；`fake_backend.py:262-265,281-284`）。
- pre-send cancel → 0 Fake；post-send 有完整 receipt → 保守 settle/fail，再发 `CANCELLED`，不发成功 finish（`757-813`）。
- 错误签名 `TypeError`/`ValueError` 不被吞；IPC 记录 `cancel_failures`（`ipc_server.py:500-512`）。
- SIGTERM：`server.shutdown()` + finally 关闭 Broker/Fake/Attempts（`controller.py:1551-1561`）。

### 3.5 Recovery / Observation

- `mark_response_observed` 持久完整 `m0.g3c.observation.v1`；同 `journal_digest` 幂等，不同 digest `OBSERVATION_CONFLICT`（`attempts.py:238-263`）。
- `_verify_receipt_document` 重算 `journal_digest`，校验 call/reservation/attempt/prepared/payload/length/route/model/provenance/completeness/`usage_digest`/`observation_digest`，并比对 receipt 文件（`controller.py:1408-1496`）。
- `reconcile_on_startup` 先查 Broker `reservation_status`；无 receipt 的 `ATTEMPT_STARTED` → `SETTLEMENT_UNCERTAIN`；Broker OK/FAILED 权威，不覆盖（`1254-1342`）；`ALREADY_SETTLED` + OK 标 `SETTLED` 而非 held（`1235-1243`）。
- `main` 先 reconcile 再消费新 admission（`1537-1544`）；replayed admission 退出 3。

### 3.6 IPC / 流式资源

- `FrameReader` 先字节界后 JSON、首帧/请求 deadline、stop event（`ipc_server.py:45-105`）；连接上限 8（`37,199-208`），超限 `TOO_MANY_CONNECTIONS`（`270-278`）；每连接 budget/chunk count（`107-121,438-447`）；响应帧/总量上限（`427-447`）；watchdog（`407-425`）；cancel reader（`471-514`）。
- Fake 逐帧读取，64 KiB/帧、1 MiB 总量、256 帧上限（`fake_backend.py:26-29,223-353`）；receipt 原子写先于帧；`last_receipt` 在 receipt 存在后设置（`277-280`）。
- Controller 在 `on_fake_frame` 先检查 `last_receipt` 再转发（`694-711`）；worker/queue 8 帧、有界 join、close 时 cancel、失败后绝不成功 finish（`383-478`）。

### 3.7 测试自身

- `tests/integration/g3c` 78 个测试函数 / 105 参数化用例全 PASS；`g3_bridge` 31、gates 14、G2 280、host full 768+2 env、OCI 768+2 env、Node 9/9、Guard 19/19、Ruff 全通过。
- 没有 `assert True`、`pytest.skip`/`xfail`；唯一 `monkeypatch` 是禁止 `subprocess.run` 以证明 streaming 不缓冲（`test_c3_04_streaming.py:248-253`）。测试使用真实 socket/子进程/SQLite，不是空断言或过度 mock。
- `impl_sha` 均为真实冻结 SHA；但矩阵路径错误使“从矩阵可追溯”不成立（见 §8 P1-3）。

---

## 4. R2 — 独立恶意探针（11 类，自建）

工具：`artifacts/reviewer-g3c/r2/probe_suite.py` / `probe_lib.py` / `crash_runner.py` / `reconcile_runner.py` / `concurrent_runner.py` / `hanging_broker.py`。**没有导入 Owner 的测试模块**；恶意 Fake 全部由 Reviewer 生成脚本。最终 `11/11` pass，UTC 2026-11-17T14:56:28Z–14:57:00Z；每例 argv/UTC/facts 在 `work/<case>/case.json`。

| 类 | 用例 | 关键结果 |
|---|---|---|
| 1 无 Claim/伪造 | `p1_no_claim` | 无 permission、复制 permission、篡改 reservation、篡改 Prepared、route/model/tool/image/self-auth 全部在 Fake 前拒绝；Fake 0；正确 code |
| 1b Admission | `p1b_admission` | invalid 不消耗 `max_calls`；第二次 `BUDGET_DENIED`；输出/输入超限 `BUDGET_DENIED`；Fake 0 |
| 2 Replay/冲突 | `p2_replay` | 同 payload 重放 `ATTEMPT_ALREADY_STARTED`，Fake 不增；不同 payload 是新 call；forged same-call/different-digest 被 Broker 拒；二次 settle `ALREADY_SETTLED`、cost 不变；Observation 冲突；重启 replay 仍拒 |
| 3 双进程 | `p2b_concurrent` | barrier + 预初始化 DB：1 个成功、1 个确定性 replay；1 receipt/1 attempt/1 reservation |
| 4 Crash/reconcile | `p3_crash` | 4 个 hook：无 receipt→`SETTLEMENT_UNCERTAIN`/PENDING；有 receipt→`SETTLED`/OK；两次 reconcile 状态不变；无重发；1 completion |
| 4b 篡改/FAILED | `p3b_tamper` | 篡改 receipt 文件 usage、篡改 journal `receipt_json` → `SETTLEMENT_UNCERTAIN`/PENDING/0 completion；Broker FAILED 保持 `WORST_CASE_HELD`/FAILED |
| 5 Cancel | `p4_cancel` | pre-send `CANCELLED` Fake 0；错误签名 TypeError/ValueError；during-Fake `CANCELLED`、attempt SETTLED、Broker OK、Fake 1；并发只取消一个；复用 transport 正常 |
| 6 Usage | `p5_usage` | missing/partial/invalid/multi/after-finish→`WORST_CASE_HELD`/FAILED/cost>0；mismatch→`FAKE_RECEIPT_MISMATCH`；no receipt→UNCERTAIN/PENDING；无成功 finish |
| 7 Streaming | `p6_streaming` | 首 chunk 早于 Fake exit 1500 ms（direct+UDS）；receipt 先于 chunk；254 帧成功、255+失败；1 MiB/>64 KiB 失败；stall 0.6 s 仅 10 帧；truncated 失败；断连保守 |
| 8 资源 | `p7_resources` | 空/慢首帧 `DEADLINE_EXCEEDED`；连接上限 `TOO_MANY_CONNECTIONS`；超大帧 `FRAME_TOO_LARGE`；Broker hang 1 请求 0 Fake/`BROKER_TIMEOUT`；Fake stall UNCERTAIN/PENDING；watchdog 0.702 s；无残留 |
| 9 Guard/坏配置 | `p8_guard` | missing/bad-uid/expired admission 非零退出且 Fake 从未 spawn；consumed admission exit 3；无残留 |

### 4.1 P0 证伪尝试

| P0 假设 | 结果 |
|---|---|
| 未授权/重复发送 | 无：无 Claim/伪造 permission/tampered prepared 均 0 Fake；replay/双进程至多 1 receipt |
| Fake 已收却 FREE/NOT_DISPATCHED | 无：receipt-backed 必为 SETTLED 或非终态 held/uncertain，且成本 > 0 |
| 假结算/二次 settle | 无：二次 settle `ALREADY_SETTLED`，cost 不变；每 reservation 1 completion |
| 丢失保守账本 | 无：unknown/partial → HELD/FAILED 或 PENDING，reserved cost > 0 |
| 失败后成功 finish | 无：所有失败路径 `finish(error)`/`error` |
| 绕过 Claim | 无：唯一 Fake 入口在 Controller，伪造 permission 被 `consume_permission` 拒 |

### 4.2 双进程冷启动缺陷（P1/P2，见 §8.2）

`p2b` 的 barrier 结果正确；但**不做预初始化**的 6 次同时冷启动中 3 次有一个子进程在
`AttemptJournal.__init__` 的 `PRAGMA journal_mode=WAL`（`attempts.py:58`）抛出
`sqlite3.OperationalError: database is locked`，进程 exit 1；另一个进程正常发送 1 个 Fake。
没有重复发送，但第二个进程不是协议级确定性拒绝。
证据：`r2/p2c-startup-lock.log`。

---

## 5. R3 — 真实 DSH 复跑（固定 rootfs）

Runner：`artifacts/reviewer-g3c/r3-dsh/run_r3.sh`；14/14 容器 exit 0；
`commands.jsonl`（UTC 2026-11-17T14:31:39Z–14:34:01Z）；rootfs/deps/stage
前后 canonical；`podman ps -a` 空。完整表见 `r3-dsh/R3_RESULTS.md`。

| 用例 | DSH 结果 | 独立 SQLite 状态 |
|---|---|---|
| Echo | completed，final `ok` | 1 `SETTLED`，1 `OK`，1 receipt，counter 1；DSH usage == receipt |
| Tool 两轮 | completed，2 assistant messages，1 tool-call + 1 tool-result | 2 `SETTLED`（`tool_once`/`tool_final`），2 `OK`，counter 2 |
| Resume 新进程 | 第二进程 turn 2，completed | 2 `SETTLED`，2 `OK`，旧 Attempt 不重发 |
| SIGTERM | DSH 被杀，无成功 finish | `RESPONSE_OBSERVED`，Broker PENDING，1 receipt，无子进程 |
| Deadline 100 ms | error，wall ~1.9 s | `SETTLEMENT_UNCERTAIN`，PENDING，Fake 1 |
| Streaming `stream_slow` | completed | `SETTLED`，OK，Fake 1；T1=1794926025697，T2=1794926027697（lead 2001 ms） |
| Truncated stream | partial chunk + error | `WORST_CASE_HELD`，FAILED，Fake 1 |
| Crash after fake receive | controller exit 97 | `ATTEMPT_STARTED`，PENDING，Fake 1，1 receipt |
| Reconcile after receive | 新进程，无 DSH | `SETTLED`，OK，counter 1，无重发 |
| Crash before fake send | controller exit 97 | `ATTEMPT_STARTED`，PENDING，Fake 0 |
| Reconcile before send | 新进程 | `SETTLEMENT_UNCERTAIN`，PENDING，counter 0，无重发 |
| Guard invalid | error `RBG_GUARD_BOOT_INVALID` | 0 attempt，0 reservation，Fake 0 |
| Guard on | completed | `SETTLED`，OK |

**T1/T2**：`timing-*.json` 的 `first_chunk_flushed` = 1794926025696，`exit_after_finish` = 1794926027697；DSH `assistant/message.stream_time0` = 1794926025697。首 chunk 在 Fake 退出前 2001 ms 到达；receipt 在首 chunk 前已存在。这是 Reviewer 自己的 trace，不是 Owner 的 `*-fixed`。

**注意**：SIGTERM 运行的 attempt 终态是 `RESPONSE_OBSERVED`/PENDING，与 Owner `sigterm-fixed` 的 `WORST_CASE_HELD` 不同；这是时序相关，仍保守、无 success finish、可由 reconcile 处理，记为 P2 观察。

---

## 6. R4 — 数据/财务交叉核对

工具：`artifacts/reviewer-g3c/r4-crosscheck/crosscheck.py`。每个 work 目录复制到临时目录，在副本上 checkpoint WAL，再 `mode=ro` 查询；**从未原地打开 Packet SQLite**，Packet 复核后仍 1713/1713 OK。15/15 cases 0 errors（R3 9 例 + Packet 6 例）；完整 JSON 在 `crosscheck.json`。检查项：

- attempt → reservation → claim → receipt → observation → settlement → cost 一一对应；
- `journal_digest`、`observation_digest`、`usage_digest` 全部独立重算通过；
- receipt `raw_sha256 == payload_digest`，`raw_length == payload_length`，receipt 文件 nonce/hash 匹配；
- `SETTLED` ⇒ Broker OK；`WORST_CASE_HELD` ⇒ Broker FAILED；无 receipt 的非终态不是 FREE；非 settled 成本 > 0；
- 每 reservation 恰好 1 个 completion；无二次 settle；
- counter == receipt 文件数；
- 所有 completed+settled 的 Echo/Tool/Resume/Stream（Reviewer 和 Packet）DSH `assistant/message.data.usage` 与 receipt usage **逐字段相等**；
- Tool 两轮各自独立 reservation/claim/attempt/receipt；Resume 2 个独立链。

**Hash 覆盖**：Packet `hashes.sha256` 覆盖 payload+manifest；`diff_sha256` 覆盖 git diff；receipt `raw_sha256` 覆盖 Controller→Fake 的 payload 字节（等于 attempt payload_digest，不含 receipt 文件/DSH 帧/远端请求）；`journal_digest` 覆盖 Observation 文档除自身；`observation_digest` 覆盖 Observation 对象；`usage_digest` 覆盖 usage。payload 字节未保留，因此 `raw_sha256 == payload_digest` 是持久哈希的构造性一致，不是独立 preimage 检查；其余 digest 是独立重算。

---

## 7. 环境 / 回归 / 无 Key

| 检查 | 结果 |
|---|---|
| host full | **768 passed / 2 failed / 1 skipped**；失败是既有宿主环境（config 可写、子进程硬编码 `/project/src`） |
| OCI full（固定 rootfs） | **768 / 2 / 1**；失败原因逐字确认：`pgrep` 不存在、`/tmp` noexec 导致 wrapper 无法 exec |
| `tests/integration/g3c` | 105 passed |
| `g3_bridge` / gates | 31 / 14 passed |
| G2 | 280 passed（Owner 证据；本轮未重跑 G2 全量，见未验证项） |
| Node adapter / guard | **9/9**, **19/19**（我在固定 rootfs 独立重跑） |
| Ruff | All checks passed |
| rootfs/deps/stage | canonical 前后 |
| `podman ps -a` | 空 |
| Key env / `.env` | 0 / absent |
| LiveGate | BLOCKED；`run_live.sh` exit 3 |

说明：我独立重跑了 host full、OCI full、Node、g3c、g3_bridge、gates、Ruff；**没有独立重跑 G2 280**（只核对了 Owner 的 junit/log 与 docs 数字），G2 的结论来自 Owner 证据加静态回归存在性，不作为我自己的 PASS 依据。

---

## 8. Findings（P0/P1/P2）

### P0 — 无

未发现未授权/重复发送、Fake 已收写成 FREE、假结算/二次 settle、丢失保守账本、失败后成功 finish、绕过 Claim。P0 证伪表见 §4.1；原始证据保留在 `r2/work/`、`r3-dsh/traces/`、`r4-crosscheck/`。

### P1-1 真实 DSH 覆盖被高估 / C1-01A 无 DSH 证据

- **声称**：`docs/M0_G3C_IMPLEMENTATION_REPORT.md:83` “真实 DSH replay：首请求 ... 重放 ...（C1-01A）”。
- **实际**：Owner 证据中唯一包含 `ATTEMPT_ALREADY_STARTED` 的证据是 `artifacts/g3c/traces/probe-replay/probe-result.json`，由 `probes_c3.py --probe replay` 产生；该目录**没有 `dsh-result.json`**，即没有 DSH 运行。C1-01A 矩阵行（`docs/Autonomous_Teacher_M0_G3C_G3D_Test_Evidence_Matrix_v1.0.csv:3`）的 `command_argv`/`log_path` 为空，`db_or_receipt_path=artifacts/g3c/traces/C1-01A` 不存在；C1-01A 的 observed 与 C1-04（raw-UDS，行 14）完全相同。
- **FINDINGS 列表**：`docs/M0_G3C_FINDINGS_AND_DISPOSITION.md:61` 把 C1-01A、C1-04、C2-02D/E、C3-01B/C、C3-02A/B 列入“真实 DSH”；实际分别是 summary/no-run、raw-UDS、container reconcile、raw-UDS、raw-UDS。共 **8/28 行**不是真实 DSH。
- **影响**：不是产品语义失败（我的 raw-UDS/host 探针证明 replay 语义正确），但违反 Review Request §0/§4 对 host-level/real-DSH 标注的要求；必须把 C1-01A/C1-04/C3-01B/C/C3-02A/B 标为 raw-UDS 或补真实 DSH 运行，C2-02D/E 标为 reconcile，C1-01A 若只是 C1-04 的汇总就删除独立 PASS 行。**这是不能签 PASS 的主要 P1。**

### P1-2 两个 Controller 同时冷启动共享 AttemptJournal 会未处理崩溃

- **代码**：`AttemptJournal.__init__` 在 `attempts.py:55-61` 先 `PRAGMA journal_mode=WAL`，之后才设置 `busy_timeout`；`controller.main` 直接构造（`controller.py:1531`），没有捕获 `sqlite3.OperationalError`。
- **复现**：6 次同时冷启动（`r2/p2c-startup-lock.log`）中 **3 次**一个进程 exit 1，traceback 为 `sqlite3.OperationalError: database is locked` at `attempts.py:58`；存活进程发送 1 个 Fake，counter 1，没有第二次发送。
- **影响**：不违反对“至多一个 Claim/Fake 收据”的安全属性，但不是 R2 要求的第二个进程确定性拒绝；双 Controller 同时启动不是受控错误。修法：先 `busy_timeout` 再 WAL、对锁重试、或捕获后以明确错误退出；若设计上只允许单 Controller，应在 launcher/契约中冻结并明确不把双进程启动视为支持场景。**这是第二个 PARTIAL 条件。**

### P1-3 矩阵证据索引 25/53 行不可解析

- `r1-static/matrix-path-audit.txt`：53 个 PASS 行中 25 行的 `db_or_receipt_path` 不存在。示例：C1-01A/C1-01B/C1-01C/C1-01D 指向 `artifacts/g3c/traces/<case_id>`（从未存在）；C2-04 指向 `artifacts/g3c/evidence/junit-g3c-only.xml`（实际是 `artifacts/g3c/evidence/junit-g3c.xml`）；C3-03A..G、C3-04D、C3-01A/E、C3-02D/E、C2-03A..E 也指向 `traces/<case_id>` 占位路径。
- C1-01A 与 C-END-01 的 `command_argv`/`log_path` 也为空；C-END-01 是 P0 优先级的“Echo+Tool+Resume”汇总行，却没有链接实际 `echo-fixed`/`tool`/`resume-second` trace。
- **影响**：实际 log/junit/trace 存在，且我用它们复现；但“从矩阵逐行可追溯”不成立。修复方式：把 `db_or_receipt_path` 改成实际的 `traces/<name>` / `regression/junit-*.xml`，并为 summary 行填 argv/log 与子 trace 引用。**这是第三个 PARTIAL 条件（证据索引，不是产品语义）。**

### P2

1. **C1-01A / C-END-01 空 argv/log**：两行都没有命令与日志；C1-01A 还是 C1-04 raw-UDS 的重复 summary。
2. **矩阵 host/raw/reconcile 标注缺口**：9 个 PASS 行未在 `observed` 写 `host-level (not DSH)` / raw/reconcile：C1-01D、C1-04、C2-02D、C2-02E、C2-04、C3-01B、C3-01C、C3-02A、C3-02B。C2-04 是宿主 pytest 却未标 host-level；C1-01D 也是宿主 pytest（+Node TAP）。
3. **C2-04 junit 路径拼写错误**：`junit-g3c-only.xml` → 实际 `artifacts/g3c/evidence/junit-g3c.xml`。
4. **SIGTERM 终态时序不确定**：我的 R3 SIGTERM 为 `RESPONSE_OBSERVED`/PENDING，Owner 的 `sigterm-fixed` 为 `WORST_CASE_HELD`；两者都保守，但“SIGTERM 后终态”不是确定性的，需在文档中明确需 reconcile，或让 shutdown 等结算完成。
5. **SRC-12 / P2-4 / 断连 / OCI 环境失败**：`next_logical_step` 仍不用 `run_id` 且不在运行路径；专用 observation 表仍未写；断连只是 best-effort close→cancel，不是 durable cancel；OCI 2 个测试因 `pgrep`/noexec 失败，host 2 个因可写 config/硬编码 `/project` 失败。均为已记录残余，不改变产品语义。
6. **`send_exact_bytes` fallback**：`controller.py:878-898` 的旧 Fake 兼容路径起 daemon 线程且不 join/取消；冻结 Fake 走 `stream` 所以不可达，但若未来替换 Fake 会重新引入超时后发送风险。
7. **`normalize_broker_error_code` 是未使用代码**，且会原样保留任何已在 `ERROR_CODES` 的字符串（包括 `UNKNOWN_FIELD`）；Controller 实际用 `broker_protocol_code`，风险有限，建议删除或收紧。
8. **Review Request 路径简写**：`security/gates.py`/`runtime/dsh_adapter.py` 实际在 `src/autoteacher_m0/…`；文档应写全路径。
9. **输入 token 是保守合成上界**：非 tokenizer，可能高估；Fake usage/cost 是 synthetic fixture，不是供应商账单。
10. **真实 DSH 覆盖仍有限**：只有 Echo/Tool/Resume/SIGTERM/Deadline/stream/crash/reconcile/guard；没有真实 DSH replay、双进程真实 DSH 同 Claim、真实 Provider。

---

## 9. 裁定与 §8.3 对应

**最终裁定：`PARTIAL`**（不是 PASS，也不是 FAIL/BLOCKED）。

理由：产品语义与安全属性在独立探针、真实 DSH 复跑和财务对账中通过（§8.3 1–4 的产品部分满足，§8.3 5 由本报告满足），但以下 P1 证据/并发缺陷必须先修正或缩小主张，不能签 `PASS_FOR_G3C_NO_KEY_CONTRACT_RECOVERY_SCOPE`：

1. **P1-1 真实 DSH 覆盖被高估**：C1-01A 的“真实 DSH replay”无 DSH 证据；FINDINGS 的 8 行 real-DSH 列表含 raw-UDS/reconcile/summary。修正或补跑后才能把“real DSH replay/cancel/broker-timeout”写成已验证。
2. **P1-2 双进程冷启动 `database is locked`**：3/6 未受控崩溃；安全属性（至多一个 Fake）保持，但不满足“第二个确定性拒绝”。修正 WAL/busy_timeout/受控错误，或把双 Controller 启动明确排除并文档化。
3. **P1-3 矩阵 25/53 PASS 行路径不可解析**：实际证据存在但索引不可追溯；修正 `db_or_receipt_path`/空 argv/log 后才满足 §13.1 的证据索引要求。

**不属于 PARTIAL 理由的项**（但必须保持）：
- 没有 P0；没有发现未授权/重复发送、假结算、丢失保守账本、成功 finish 或 Claim 绕过。
- G3-B P1-1（B3-08 → 持久 Observation + 幂等 settle）和 P1-2（cancel 非功能 → 执行）由我的 p3/p3b/p4 与 R3 证实闭环；P2-2/P2-3/P2-5/P2-7 也有独立证据；SRC-12/P2-4/断连/OCI 环境失败是已记录残余。
- host full 768/2/1、OCI 768/2/1 的 4 个失败均为文档化环境限制，不是产品断言失败。

**明确不签**：
- 不签 `PASS_FOR_G3D_*`、Live、G4/G5/M0 GO 或任何生产授权。
- 不改变 G3-B 历史裁定；`OS_TRUST_BOUNDARY=B0-02=BLOCKED` 继续成立；16 个 D 行仍 `NOT_RUN`。

---

## 10. 未验证 / 明确未主张

- **G3-D 全部 16 行 NOT_RUN**：无 OS Principal 隔离、候选攻击、内核 errno、双主体故障证据；OS 边界仍 `BLOCKED`。
- **真实 Provider/Key/模型/外网**：0；没有远端 exactly-once、真实 token/账单、限流/远端超时。
- **真实 DSH replay**：我没有跑；raw-UDS replay 语义通过，但 C1-01A 的 real-DSH 声明不成立。双进程真实 DSH 同 Claim 也没有跑；只有 host Controller 双进程。
- **host-level 22 行**仍是宿主 pytest（真实 socket/子进程，但不是 DSH），不得合并为 real-DSH。
- **G2 280** 只核对 Owner junit/log，未独立重跑。
- **SIGTERM 终态**不是确定性；需 reconcile。
- **DSH runtime/插件/内核**没有完整安全审计；Guard 19/19、adapter 9/9 只是定向测试。
- **Fake usage/cost** 是 synthetic fixture，不是供应商账单；本地 Claim/Receipt 不等于远端 exactly-once。
- **Packet 内 SQLite** 只通过复制到临时目录后查询；没有原地打开。

---

## 11. 环境指纹与复算

| 对象 | 值 |
|---|---|
| rootfs canonical | `25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0` |
| deps canonical | `e07729d7997944417b1c25531749b3e6e5e34aa4248f01dc8f370282082ecb98` |
| stage（Reviewer copy） | `fcdb0de442d455f89fe849c736679f831c15c50f76e3e4844d38f2963e3735b0` |
| DSH runtime | `1cc41d5a8745a5b9d47c8604e44f23eb8af2d8ca02b2afa0be101d5f71be6ea4`，0.2.2-rc.2 |
| Python | 3.11.15（`/root/.local/bin/python3.11`） |
| `podman ps -a` | 空 |
| Packet | 1715 files；`sha256sum -c` 1713/1713 OK |

复算命令：

```bash
cd "/root/Autonomous Teacher"
git rev-parse HEAD bb5bd0b e107e22 e6fde1c 78be77c
git diff --binary bb5bd0b e6fde1c | sha256sum
cd artifacts/review-packet-g3c-e6fde1cdf0bec9e957e98d569b257c8f17dfa363
sha256sum -c hashes.sha256
cd "/root/Autonomous Teacher"
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:artifacts/foundation/deps \
  /root/.local/bin/python3.11 -B -m pytest tests/ -q -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:artifacts/foundation/deps \
  /root/.local/bin/python3.11 -B artifacts/reviewer-g3c/r2/probe_suite.py
bash artifacts/reviewer-g3c/r3-dsh/run_r3.sh
bash artifacts/reviewer-g3c/r3-dsh/run_oci_full.sh
bash artifacts/reviewer-g3c/r3-dsh/run_node_tests.sh
/root/.local/bin/python3.11 -B artifacts/reviewer-g3c/r4-crosscheck/crosscheck.py
```

证据索引：`artifacts/reviewer-g3c/RUN_INDEX.md`；R2 `r2/summary.json`；R3 `r3-dsh/summary.txt`；R4 `r4-crosscheck/crosscheck.json`；命令日志 `r3-dsh/commands.jsonl`；环境 `r0-identity/final-canonical.txt`。

---

## 12. 给 Lead 的下一步（不改产品/证据）

1. 修正 `docs/M0_G3C_IMPLEMENTATION_REPORT.md:83` 与 `docs/M0_G3C_FINDINGS_AND_DISPOSITION.md:61` 的真实 DSH 标注：C1-01A 改为 summary/raw-UDS 或删除；C1-04、C3-01B/C、C3-02A/B 标 raw-UDS；C2-02D/E 标 reconcile；C1-01D/C2-04 标 host。
2. 修正矩阵 `db_or_receipt_path` 的 25 个占位路径，填 C1-01A/C-END-01 的 argv/log，并把 C2-04 的 junit 指向实际文件。
3. 修 `attempts.py` 的 WAL/busy_timeout/重试或受控退出，重跑双进程冷启动；或将“双 Controller 同时启动”明确排除并文档化。
4. 如要签 PASS，需在上述修正后重新冻结 docs/Packet；产品代码/Packet 的现有语义证据不需要重做（除非修 P1-2）。
5. 归档 `artifacts/reviewer-g3c/`（仓库 `.gitignore` 忽略 `artifacts/`，需 force-add/打包），不要修改 Owner Packet；本 Reviewer 不 commit/push。

---

*本报告只对 Reviewer 自己的命令、探针、容器运行和 SQLite 副本负责；不把 Owner 的文字当作独立复验，不签任何 G3-D/Live/G4/G5/M0 GO。*
