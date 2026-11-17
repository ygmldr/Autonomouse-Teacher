# M0 G3-C Review Request（独立复核请求）

> **状态**：v1 独立复核结论为 `PARTIAL`（无 P0，3 个 P1）；PR1 已修复（`b2f6af0`）并更新 docs。现**请求 Lead 指派二次独立 Reviewer**。本文件不预设二次结论，不是 Live/GO 授权。
> **Base** `bb5bd0bf83e22130ed0d81c54f54a4673654cfe3`；**G0** `e107e22`；**v1 Implementation** `e6fde1cdf0bec9e957e98d569b257c8f17dfa363`（父 `3675a41`）；**PR1 Implementation** `b2f6af054555705192c4e1ae3019a68078764736`（父 `78be77c`）。
> **v1 复核输入**：`docs/REVIEW_G3C_INDEPENDENT.md`（339 行，sha256 `4744c61f1561c6f92634b29ef9a6a0f7ca82c4627aef31ba3d0163e4886d23b1`，原字节归档）+ `docs/M0_G3C_REVIEW_ERRATA.md`（append-only 处置记录）。
> **Docs**：包含本文件/Implementation Report/FINDINGS/Review Errata/matrix 的最终 docs 归档 commit；SHA 见 Packet v2 `manifest.json.docs_sha`。
> **Packet v2**：`artifacts/review-packet-g3c-b2f6af054555705192c4e1ae3019a68078764736/`（`manifest.json`/`diff.patch`/`docs-diff.patch`/`hashes.sha256`/`review/`/`matrix/`/`evidence/`/`docs/`/`reproduce/`/`security-nonclaims.md`）。
> **v1 Packet（冻结，只读）**：`artifacts/review-packet-g3c-e6fde1cdf0bec9e957e98d569b257c8f17dfa363/`，docs_sha `78be77c`；不得修改或重建。
> **矩阵**：`docs/Autonomous_Teacher_M0_G3C_G3D_Test_Evidence_Matrix_v1.0.csv`，69 行 = 53 PASS / 16 NOT_RUN（D 行）；PR1 后 `impl_sha` 指向 `b2f6af0`，旧 trace 的生成批次由 `argv.json`/`commands.jsonl` 追溯。
> **最高可请求裁定**：`PASS_FOR_G3C_NO_KEY_CONTRACT_RECOVERY_SCOPE`。**禁止**给出 G3-D/Live/G4/G5/M0 GO 裁定。

## 0. 二次复核上下文（v1 PARTIAL → PR1）

v1 Reviewer 对 `e6fde1c` / docs `78be77c` / Packet v1 的裁定是 **`PARTIAL`**，不是 PASS/FAIL/BLOCKED：产品语义未发现 P0，但三项 P1 必须先修正或缩小主张。v1 的原始报告与 Reviewer 证据不被本 PR 改写：

| v1 P1 | v1 问题 | PR1 处置位置 | 二次复核必须验证 |
|---|---|---|---|
| P1-1 | 真实 DSH 覆盖被高估；C1-01A 实为 raw-UDS replay，无 `dsh-result.json`；Findings 的 real-DSH 列表含 8 行 raw-UDS/reconcile/summary | docs `9ffa0b1`（Report/Findings/矩阵逐行标注）；`bea0fc3` 交叉引用；P1-1 是**更正/缩小主张**，没有新增 real-DSH replay | 53 行证据类型表；原 8 行与 C1-01A/C-END-01 的 argv/log/path；不得把 raw-UDS/reconcile/host pytest 写成 DSH |
| P1-2 | 两个 Controller 同时冷启动共享 AttemptJournal 时 `database is locked` 未处理崩溃（v1 6 次中 3 次） | impl `b2f6af0`：`busy_timeout` 先于 WAL、有界重试、per-socket `flock` singleton、受控退出 5/4/3；20 轮测试 `tests/integration/g3c/test_c3_05_twocontroller_coldstart.py` | 用自己的命令重跑 ≥20 轮；1 成功 + 1 受控拒绝、0 traceback、Fake=1、Attempt `SETTLED`；核对代码顺序与退出码 |
| P1-3 | 53 个 PASS 行中 25 个 `db_or_receipt_path` 不存在；C1-01A/C-END-01 无 argv/log | docs `9ffa0b1` 矩阵；审计 `artifacts/g3c/evidence/matrix-path-audit-pr1.txt`（before 25 missing → after 0）；D 行 16 条原字节未改 | 独立重跑路径存在性审计；核对 docs 矩阵与工作矩阵均 0 missing；D 行 SHA 不变；抽查 C1-01A/C-END-01/C2-04 |

**证据读法**：v1 报告的结论/行号只适用于 docs `78be77c`；当前 docs 已含 PR1 修正。PR1 的 20 轮冷启动、矩阵审计和回归数字是 **Owner 运行**，二次 Reviewer 必须独立复跑，不能只引用 Owner 的 JSON/日志。PR1 没有新增 real-DSH replay，也没有做双真实 DSH 同 Claim；不得把 P1-1 的标注修正解释为“real-DSH replay 已补齐”。

## 0.1 Reviewer 身份与范围

- **实现者/Owner 与 Reviewer 必须分离**。二次 Reviewer 必须从冻结的 Git Blob + Packet v2 原始字节复核，不得只复述本请求/报告/矩阵/errata 文字，也不得复用 v1 Reviewer 或 Owner 的结论句子作为自己的判定。
- **二次复核重点**：P1-1 的证据类型/真实 DSH 标注、P1-2 的 20 轮双 Controller 冷启动、P1-3 的矩阵路径审计；同时保留 v1 的 R1/R2/R4 语义复核，不能因为 P1 修复就跳过产品语义。
- **不得把 v1 `PARTIAL` 或 Owner 的 PR1 修复文字直接改写为 PASS**；最终裁定必须由二次 Reviewer 自己的命令/证据支撑。
- **本轮范围**：G3-C1 协议/错误语义/Admission；G3-C2 Usage/Receipt/Observation/Recovery；G3-C3 Cancel/Deadline/IPC 资源/增量 Streaming；无 Key 集成证据与全量回归。
- **不在范围**：G3-D0/D1/D2/D3（OS 主体隔离/候选攻击/内核拒绝）、真实 Provider/Key/模型/外网/Live、G4/G5/M0 GO。
- 证据中 **host-level（宿主 pytest，非真实 DSH）** 行已在矩阵逐行标注；Reviewer 不得把它们合并成“真实 DSH 通过”。
- Fake usage/cost 是 `synthetic_fixture_only=true` 的合成证据，不是供应商 token/账单；本地 Claim/Receipt 不等于远端 exactly-once。

## 1. R0–R5 复核任务

### R0 — 身份、漂移与范围

1. 独立执行 `git rev-parse`/`git cat-file`/`git log`，确认 Base/G0/v1 impl/PR1 impl/docs 与 Packet v2 `manifest.json` 一致；`git diff --binary bb5bd0b..b2f6af0` 的 sha256 与 `diff.patch` 一致；`git diff --binary bb5bd0b..<docs_sha>` 的 sha256 与 `docs-diff.patch` 一致。
2. `sha256sum -c hashes.sha256` 在 Packet v2 根目录 100% 通过；`manifest.file_count` 与磁盘文件数一致；`docs_sha` 指向的最终 docs commit 包含 Report/Review Request/Findings/Review Errata/matrix，且 `review/REVIEW_G3C_INDEPENDENT.md` 与 docs blob 原字节一致（sha256 `4744c61f…`）。
3. 确认未修改/复制 G3-B packet、33 行矩阵、`docs/REVIEW_G3B_INDEPENDENT.md`、G3-B errata、Packet v1；确认 `src/autoteacher_m0/security/gates.py`、`src/autoteacher_m0/runtime/dsh_adapter.py`、`scripts/run_live.sh` 与冻结值一致（sha256 见报告 §11；注意实际路径含 `src/autoteacher_m0/`）。
4. 确认 LiveGate 未解锁：`run_live.sh` exit 3、`LiveGate.inspect(live_requested=True)` = `BLOCKED`、无 Key 环境变量/`.env`。
5. 确认 docs matrix：69 行、D 行 16 条 `NOT_RUN` 且与 v1 冻结字节一致、3 条补充 C 用例（C1-02/C1-04/C2-04）已标注来源；工作矩阵 `C-END-02` 的回归后更正有原始日志支撑；PR1 路径审计 `missing_paths=0`。
6. 确认 `impl_sha=b2f6af0` 与旧 trace 生成批次 `e6fde1c` 的可追溯区分（`argv.json`/`commands.jsonl`），不得把旧 trace 说成 PR1 新运行。

### R1 — 静态复验（从可发送入口反向追踪）

1. **发送许可链**：以 Fake 实际 stdin/receipt 为起点，逐条确认到 Controller 的路径必须经过 `_prepare_checked` → durable intent → Reserve → bound Claim → `ATTEMPT_STARTED`；确认无 legacy `claim_dispatch`/descriptor-only/G3-A 直 spawn 旁路（`controller.py:602-760`）。
2. **Admission 实际限额**：核对 `max_calls` 在 prepare 成功后递增（无效请求不消耗）、`max_output_tokens` 与请求比较、输入上界、`deadline_ms` 的 checkpoint 与 Broker/Fake 超时；确认候选自授权字段被拒（`ADMISSION_SELF_AUTH_DENIED`）。
3. **错误语义/Finish schema**：核对 `protocol.ERROR_CODES`、`BROKER_ERROR_CODE_MAP`、`validate_error_payload`、`_terminal_events`；确认任何非 authoritative 流只发 `finish(error,failure{code,message})`，不会出现成功 finish。
4. **Cancel/Deadline 状态机**：核对 per-transport cancel 注册/清理、checkpoint、发送前/后取消分支、`SETTLEMENT_UNCERTAIN` 条件、`_cancel_reader` 不吞异常、SIGTERM 清理；确认 cancel 不会泄漏到复用 transport id 的下一流。
5. **Recovery/Observation**：核对 `receipt_json` 完整文档 + `journal_digest` 校验、Broker `reservation_status` 权威性、settle/fail 幂等、篡改/缺失/冲突的失败关闭；确认 reconcile 先于 admission 登记。
6. **IPC/流式资源**：核对首帧 deadline、连接上限、线程回收、每连接字节预算、stream chunk 上限、有界队列与 backpressure、receipt-first 后才转发 chunk、`MAX_*` 常量。
7. **测试本身**：核对新增测试不是空断言/过度 mock；确认 `LogiCAL_TRACE` 只读映射、旧 trace 未被覆盖、host-only 标注与 `impl_sha` 填写。

### R2 — 独立恶意探针（至少 6 类；不得复用 Owner 结论）

Reviewer 必须自行构造并记录 argv/UTC/exit/原始输出，至少覆盖：

1. **无 Claim/伪造 Reservation/篡改 Prepared/Route·Model·Tool Schema 不符** → 期望 Fake=0，无 `ATTEMPT_STARTED` 后的发送。
2. **同一 call_id 同 payload 重放 + 不同 digest** → 期望首请求一次发送，重放确定性拒绝（`ATTEMPT_ALREADY_STARTED`/`BROKER_*`），Fake counter 不增。
3. **两个真实进程同一 call/同一 quota 竞争** → 期望至多一个 Claim/Fake 收据，第二个确定性拒绝而非 `UNKNOWN_FIELD`。
4. **Crash 窗口**：`after_claim_before_attempt`、`after_attempt_before_send`、`after_response_before_settlement`、`after_broker_settle_before_journal_mark` → 期望不重发；有 receipt 才 settle，无 receipt `SETTLEMENT_UNCERTAIN`。
5. **Bad/partial/missing usage、伪造 receipt digest、重复/冲突 Observation** → 期望无免费结算/成功 finish；冲突不覆盖已有 settlement。
6. **UDS 畸形帧/慢连接/首帧超时/连接上限/响应预算** → 期望受控错误、资源有界、非法首帧不进入 Controller。
7. **Cancel（含错误签名/重复/未知 id）** → 期望 pre-send 零 Fake、post-send 保守结算或 uncertain、错误签名不被静默吞掉。
8. **断连/中断** → 期望不产生成功 finish；不把“生成器 close 的 abort”当作 durable cancel 证据。
9. **P1-2 双进程冷启动（二次复核必做）** → Reviewer 自己构造 ≥20 轮两个 Controller 同时冷启动（同一 workdir/socket/journal）：期望每轮 1 个成功 + 1 个受控拒绝（`CONTROLLER_SINGLETON_LOCKED` exit 5，或按实现的 3/4 受控码），0 traceback，Fake counter=1，Attempt `SETTLED`；不得只引用 Owner 的 `concurrency-coldstart-*.json`。记录自己的 argv/UTC/exit/日志。

### R3 — 真实 DSH 复跑（固定 rootfs，无 Key）

必须在 `artifacts/security/rootfs`（`25491e45…`）+ `artifacts/foundation/deps`（`e07729d7…`）内、`--network none` 下独立重跑：

1. Echo（`worker_c3.py --label <reviewer>-echo`）→ 1 call/1 claim/1 receipt/1 settle/usage。
2. Tool 两轮（`--scenario tool`）→ 2 个独立 call/reservation/claim/attempt/receipt，第二请求带真实 tool result。
3. 新进程 Resume → 历史 session 恢复，旧 Attempt 不重发。
4. 至少一个 Crash + reconcile、一个 Cancel、一个 Deadline/timeout、一个 Streaming（`stream_slow`）。
5. 记录 Reviewer 自己的 `reviewer-*` trace/日志/UTC/exit；不得沿用 Owner 的 `*-fixed` 或 `pr1/*` 文件冒充新运行。
6. 复跑后检查 `podman ps -a` 空、无残留 broker/fake/controller 进程；rootfs/deps canonical 不变。
7. **P1-1 证据类型核验（二次复核必做）**：逐行核对 53 个 PASS 行——real DSH 必须同时有 `dsh-result.json` 与 DSH 事件；raw-UDS 不得写成 DSH；container reconcile 不得写成 DSH；host pytest 不得写成 DSH。重点复核原 8 行（C1-01A、C1-04、C2-02D/E、C3-01B/C、C3-02A/B）与 C-END-01 summary 的子 trace 链接。
8. **P1-3 矩阵路径审计（二次复核必做）**：独立解析 docs 矩阵 + 工作矩阵的 `db_or_receipt_path`/`log_path`/`command_argv`，确认 missing=0；核对 D 行 16 条与 v1 冻结字节一致；抽查 C1-01A/C-END-01/C2-04。

### R4 — DB/Receipt 对账

对每个 `call_id` 独立交叉核对：

- Reservation → Claim → Attempt → Receipt → Observation → Usage/Settlement 是否一一映射；Tool 两轮是否各自独立；Usage/Cost 是否只来自 trusted receipt。
- Pending/`SETTLEMENT_UNCERTAIN` 是否保守计入（不免费、不低计）；已 Settlement 的 replay 是否不新发请求、不二次 settle。
- Fake receipt 的 `raw_sha256/raw_length` 是否等于 Controller approved/sent payload digest；digest 覆盖哪些字节（frame/prepared/payload）是否与文档一致。
- 是否出现 **Fake 已收到却被写成 `NOT_DISPATCHED/FREE`**（P0）；crash 是否诚实标 Unknown/Pending。
- 对账 **只读 Packet 复制后的 SQLite**：**禁止**用 `sqlite3` CLI 打开 Packet 内 sqlite 副本（G3-B 曾因 `mode=ro` 改 `-shm` 导致 hash 漂移）；只做 `sha256sum` 校验与只读副本查询。

### R5 — 范围裁定

- 逐项给出 `PASS / FAIL / PARTIAL / BLOCKED`，附确切 `file:line`、命令、期望/实际、证据路径；不得只给汇总或“整体 PASS”。
- 最终枚举只能是：**`PASS_FOR_G3C_NO_KEY_CONTRACT_RECOVERY_SCOPE`** / **FAIL** / **PARTIAL** / **BLOCKED**。
- 若认为 SRC-12、P2-4、断连 cancel、OCI 两项环境失败或 host-level 覆盖不足影响结论，请明确写成 PARTIAL/BLOCKED 的条件，不要用模糊表述。
- **不得**给出 `PASS_FOR_G3D_...`、Live、G4/G5/M0 GO 或任何生产授权；G3-D 的 16 行保持 NOT_RUN。

## 2. 可复现命令

### 2.1 身份与 Packet（宿主，只读）

```bash
cd "/root/Autonomous Teacher"
git rev-parse HEAD                         # 最终 docs commit（见 Packet v2 manifest.docs_sha）
git rev-parse bb5bd0b e107e22 e6fde1c b2f6af0
git diff --check bb5bd0b b2f6af0
git diff --binary bb5bd0b b2f6af0 | sha256sum   # 对比 manifest.diff_sha256
git diff --binary bb5bd0b <docs_sha> | sha256sum # 对比 manifest.docs_diff_sha256
cd artifacts/review-packet-g3c-b2f6af054555705192c4e1ae3019a68078764736
sha256sum -c hashes.sha256
python3 -c "import json;m=json.load(open('manifest.json'));print(m['base_sha'],m['g0_sha'],m['impl_sha'],m['docs_sha'],m['file_count'],m['previous_review']['verdict'])"
```

### 2.2 宿主 Python（必须 `-B`，禁止写 bytecode）

```bash
cd "/root/Autonomous Teacher"
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="src:artifacts/foundation/deps"
/root/.local/bin/python3.11 -B -m pytest tests/integration/g3c -q -p no:cacheprovider
/root/.local/bin/python3.11 -B -m pytest tests/integration/g3_bridge -q -p no:cacheprovider
/root/.local/bin/python3.11 -B -m pytest tests/unit/security/test_gates.py -q -p no:cacheprovider
/root/.local/bin/python3.11 -B -m pytest tests/unit/accounting tests/integration/g2_closure -q -p no:cacheprovider
/root/.local/bin/python3.11 -B -m pytest tests/ -q -p no:cacheprovider
/root/.local/bin/python3.11 -B -m ruff check src tests spikes/g3b-trusted-bridge/run_c3
```

预期：g3c **110** / g3_bridge **31** / gates **14** / G2 **280** 全 PASS；host full **773 passed + 2 个既有宿主环境失败（可写 config mode、硬编码 `/project`）+ 1 skipped**（776 collected；exit 1 是这两个环境失败）；Ruff 通过。实际以 Reviewer 自己的运行日志为准；若计数不同，请记录差异原因。

### 2.3 固定 rootfs（Node/DSH/OCI）

```bash
cd "/root/Autonomous Teacher"
bash scripts/g3c/run-node-tests.sh    # 9/9 adapter + 19/19 guard，rootfs canonical
bash scripts/g3c/run-oci-full.sh      # 实测 773 passed / 2 failed / 1 skipped（PR1 @ b2f6af0）

# P1-2：Reviewer 自己的 ≥20 轮双 Controller 冷启动（改 UTC/label；不要覆盖 Owner 证据）
UTC=$(date -u +%Y%m%dT%H%M%SZ)
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:artifacts/foundation/deps \
  G3C_COLDSTART_EVIDENCE=artifacts/reviewer-g3c/coldstart-$UTC.json \
  G3C_COLDSTART_LOG_DIR=artifacts/reviewer-g3c/coldstart-$UTC \
  /root/.local/bin/python3.11 -B -m pytest \
  tests/integration/g3c/test_c3_05_twocontroller_coldstart.py -q -p no:cacheprovider
```

预期：OCI 2 个失败为冻结 rootfs 环境限制（无 `pgrep`；`/tmp` noexec 使 slow-broker wrapper 无法执行），不是产品断言失败；PR1 后 OCI full 计数为 **773/2/1**（不是 v1 的 768）。若 Reviewer 用不同挂载参数得到不同结果，请记录自己的 argv/结果并说明差异。冷启动期望 20/20：1 成功 + 1 受控 singleton 拒绝、0 traceback、Fake counter=1、Attempt `SETTLED`。

真实 DSH 单例（示例，Reviewer 自行改 label/时间；先建 evidence 目录）：

```bash
mkdir -p artifacts/g3c/traces/reviewer-echo
# 容器内；stage 已含 /probe/run_c3/* 与 /probe/runtime/bridge/lib
podman run --rm --name reviewer-echo \
  --network none --http-proxy=false --unsetenv-all \
  --env PATH=/opt/python/bin:/usr/bin --env HOME=/work \
  --env PYTHONPATH=/probe/src:/deps --env PYTHONDONTWRITEBYTECODE=1 --env TMPDIR=/tmp \
  --read-only --cap-drop ALL --security-opt no-new-privileges --user 65534:65534 \
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=64m --tmpfs /work:rw,noexec,nosuid,nodev,size=512m \
  --workdir /work --mount "type=bind,src=$PWD/artifacts/g3c/stage,dst=/probe,ro=true" \
  --mount "type=bind,src=$PWD/artifacts/foundation/deps,dst=/deps,ro=true" \
  --mount "type=bind,src=$PWD/artifacts/g3c/traces/reviewer-echo,dst=/evidence,rw=true" \
  --rootfs "$PWD/artifacts/security/rootfs" \
  /opt/python/bin/python3.11 -B /probe/run_c3/worker_c3.py --label reviewer-echo --prompt G3C_ECHO --evidence /evidence
```

### 2.4 canonical / absence

```bash
tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner -cf - -C artifacts/security/rootfs . | sha256sum
tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner -cf - -C artifacts/foundation/deps . | sha256sum
podman ps -a --format '{{.Names}}'
```

预期：`25491e45…`、`e07729d7…`、空列表。

## 3. 必须签的裁定枚举

| 枚举 | 含义 |
|---|---|
| `PASS_FOR_G3C_NO_KEY_CONTRACT_RECOVERY_SCOPE` | 在无 Key/Fake Provider 范围内，C1/C2/C3 契约、恢复、取消、deadline、资源与增量流证据满足；D/OS 边界与 Live 不在内 |
| `FAIL` | 存在 P0/P1 语义或证据缺陷（例如 Fake 已收但报 FREE、crash 重发、recovery 覆盖已结算、伪造计数） |
| `PARTIAL` | 主要路径通过，但 Reviewer 认为某项残余（SRC-12/P2-4/断连/host-level 覆盖/OCI 环境失败等）必须先修或缩小主张 |
| `BLOCKED` | 因环境/证据不可复现或范围不足，无法完成本轮复核 |

裁定必须逐行附 `file:line`、命令、期望/实际与证据路径；**不得**只签“全部 PASS”。本请求不要求、也不允许签署任何 G3-D 或 Live 范围裁定。

**枚举口径（二次复核）**：v1 的最后一个独立裁定是 `PARTIAL`；PR1 修复不等于自动 PASS。二次 Reviewer 只有在独立复验 P1-1/P1-2/P1-3 与 R1/R2/R4 后才可给 `PASS_FOR_G3C_NO_KEY_CONTRACT_RECOVERY_SCOPE`；若仍有 P1/P2 残余影响主张，仍应给 `PARTIAL` 或 `BLOCKED`，不得用“Owner 已修”替代自己的证据。`FAIL` 用于发现 P0/P1 语义或证据缺陷（包括把 Fake 已收写成 FREE、crash 重发、recovery 覆盖已结算、伪造计数、把 raw-UDS/host 写成 DSH）。

## 4. 禁止事项

- 禁止使用真实 Key/真实模型/外部 HTTP/生产 Live；禁止解锁 `gates.py`/`run_live.sh`；禁止用宿主 Node 替代固定 rootfs。
- 禁止修改、覆盖、移动 Owner 的 trace/log/matrix/receipt/ledger；复核只能在 Reviewer 自己的目录写 `reviewer-*` 证据。
- 禁止用 `sqlite3` CLI 打开 Packet 内 SQLite 副本（会因 `-shm` 改变字节）；只读副本或仅 `sha256sum`。
- 禁止把 Owner 的矩阵/报告文字当作自己的复核结论，禁止复制粘贴式“独立复验”；禁止把 v1 `PARTIAL`、PR1 的“已修复”或 Owner 的 20 轮 JSON 直接改写为二次 PASS。
- 禁止修改 v1 报告/本请求/errata 的既有文字、Packet v1、Packet v2 payload；二次复核只能在 Reviewer 自己的 `artifacts/reviewer-g3c/` 写新证据。
- 禁止 push、amend、重写历史；禁止改 G3-B packet/33 行矩阵/独立 Review/G3-B errata。
- 禁止把 host-level 测试写成 real-DSH；禁止把 raw-UDS/container reconcile 写成 real-DSH；禁止把 Fake synthetic usage 写成真实账单；禁止把 16 个 D NOT_RUN 写成通过。

## 5. 非主张清单

- 不主张 OS 隔离/信任边界通过；`OS_TRUST_BOUNDARY=B0-02=BLOCKED`。
- 不主张 G3-D/G4/G5/Live/M0 GO、生产可用、真实 Provider exactly-once、计费准确、限流/远端超时。
- 不主张对 DSH runtime/插件/内核的完整安全审计；Guard 19/19、adapter 9/9 仅定向测试。
- 不主张历史 G3-B 裁定被改变；不主张本 Packet 含 D0 实现或 G3-B 历史文件。
- 不主张 host full 的 2 个宿主环境失败已被修复（它们是既有环境限制，不是本轮产品缺陷）；也不掩盖 OCI 的 2 个环境失败。
- 不主张 PR1 已被二次复核为 PASS：本请求发出时二次复核尚未执行；v1 的最后独立裁定仍是 `PARTIAL`。
- 不主张 PR1 补齐了 real-DSH replay 或双真实 DSH 同 Claim；P1-1 只是更正/缩小主张，P1-2 覆盖 Controller/socket/Broker/Fake/SQLite 级冷启动。
- 不主张 v1 报告/errata 的文字被修改；v1 报告原字节 sha256 `4744c61f…`，packet v1 冻结 1713/1713。

## 6. 证据索引（Packet 内）

| 内容 | Packet v2 路径 |
|---|---|
| Manifest / 校验 | `manifest.json`（含 `previous_review`）、`hashes.sha256`、`packet-integrity-report.txt` |
| Diff | `diff.patch`（`bb5bd0b..b2f6af0`，含新文件）；`docs-diff.patch`（`bb5bd0b..<docs_sha>`，含 docs 变更） |
| v1 复核 | `review/REVIEW_G3C_INDEPENDENT.md`（原字节，339 行）、`review/REVIEW_ERRATA.md`、`review/RUN_INDEX.md`、`review/V1_EVIDENCE_INDEX.md` |
| Docs | `docs/M0_G3C_IMPLEMENTATION_REPORT.md`、`docs/M0_G3C_REVIEW_REQUEST.md`、`docs/M0_G3C_FINDINGS_AND_DISPOSITION.md`、`docs/M0_G3C_REVIEW_ERRATA.md`、matrix |
| 矩阵 | `matrix/Autonomous_Teacher_M0_G3C_G3D_Test_Evidence_Matrix_v1.0.csv`、`matrix/evidence-matrix-g3c.csv`、`matrix/matrix-path-audit-pr1.txt` |
| 证据 | `evidence/env/`、`evidence/commands.jsonl`、`evidence/traces/`、`evidence/logs/`（含 coldstart-*）、`evidence/ledger/`、`evidence/receipts/`、`evidence/evidence/`（含 `concurrency-coldstart-*.json`、`matrix-path-audit-pr1.txt`）、`evidence/regression/`、`evidence/pr1/`（含 `pr1/traces/{echo,tool}`） |
| 复现 | `reproduce/`（R0–R5、P1-1/2/3 专项、canonical/DSH 命令） |
| 安全非主张 | `security-nonclaims.md` |
