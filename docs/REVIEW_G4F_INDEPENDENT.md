# M0 G4-F — 独立 Reviewer 报告（No-Key Closeout Scope）

- 报告 ID：`REVIEW-G4F-INDEPENDENT-20261119T1622Z`
- Reviewer：未参与 G4-F1..F6 实现、证据生成、矩阵/Packet 构建的独立 Agent
- 复核对象：`base bb2e914` → `impl e7d9296` → `code dbacb76` → `docs d12df41` → `build/head 0d5e5e0`
- Packet：`artifacts/review-packet-g4f-e7d92967ec0ece80de4a1a3705f637e8eb9bde99/`
- 复核窗口（UTC）：`2026-11-19T15:13Z` → `2026-11-19T16:22Z`
- 只写两处：本文件与 `artifacts/reviewer-g4f/`（gitignored）；**未 commit / 未 amend / 未 push**

---

## 0. 独立性声明与环境

1. 我未参与 G4-F1..F6 的实现、证据生成、矩阵填写或 Packet 构建，也未参与 F1–F5 的任何代码/测试/脚本编写。
2. 我未修改 `src/`、`scripts/`、`tests/`、`config/`、`plugins/`、Stage、rootfs/deps、历史证据/矩阵/Packet；主工作树 `git status --porcelain` 在复核前后为空（本报告与 `artifacts/reviewer-g4f/` 除外）。
3. 关键结论来自我自己的命令、自建 Probe、原始字节、SQLite 只读副本、Receipt、gate journal、dispatch-window JSONL、DSH trace/session JSONL 与独立对账。Owner 的 `summary.json`/`checks.json`/`matrix.json` **没有**被当作裁定输入；只使用其启动真实容器/记录的原始文件作为待复核数据。
4. L2 证据在 `impl e7d9296` 的独立 clean worktree `/root/at-g4f-impl` 中重跑；artifacts 使用 `/tmp/at-g4f-review/artifacts` 的固定副本（rootfs/deps/stage 均 canonical），main worktree 未运行任何写操作。
5. 环境：Host Python `3.11.15`（`/root/.local/bin/python3.11 -B`，`PYTHONDONTWRITEBYTECODE=1`）；Podman `4.9.3`；Node `v22.23.2`；DSH `0.2.2-rc.2` runtime `1cc41d5a…`；rootfs `25491e45…`；deps `e07729d7…`；stage `stage-20261119T142828Z` manifest `82e10c6f…` / tree `7d32ec1d…`。
6. 0 真实 Key / 0 真实模型 / 0 外部 HTTP/TCP / 0 `podman pull` / 0 Live；CLI 负例中的假 `DEEPSEEK_API_KEY` 只在被测子进程 env 中存在，未打印、未用于发送。
7. 结束时 `podman ps -a` 为空；`rootfs/deps/stage` 复算 canonical；无 `.env`；无 Key-like 环境变量。

---

## 1. 唯一裁定与状态常量

```text
PASS_FOR_G4F_NO_KEY_CLOSEOUT_SCOPE
```

范围限定：**仅限本机冻结环境、无 Key、无真实 Provider/计费/TLS/Live 的 G4-F 工程 closeout**。该裁定表示 F1–F6 的工程/隔离/合成账本/授权失败窗口/冻结材料在独立复核中未发现 P0/P1；**不构成** E5 PreLive Full、G4 Full、G4-H/G5/G6、Live 或 `M0_GO`。

固定状态常量（复核后不变）：

```text
G4-H             = NOT_AUTHORIZED
G5               = BLOCKED
G6               = NOT_RUN
LiveGate         = BLOCKED
M0               = DECISION_PENDING
E5_PRELIVE_FULL  = BLOCKED_PENDING_HUMAN_DEPLOYMENT
```

---

## 2. R0 — 身份、Packet、Stage、loaded modules、旧 Stage fail-closed

### 2.1 冻结身份

| 对象 | 期望 | 独立实测 | 结果 |
|---|---|---|---|
| HEAD | `0d5e5e0` | `0d5e5e09cd607aef6ba39608b8a3b33a0d2c7705` | 一致 |
| impl | `e7d9296` | `e7d92967ec0ece80de4a1a3705f637e8eb9bde99` | 一致 |
| code | `dbacb76` | `dbacb76f98a1a91559ff70e02bf544ace76ed7b5` | 一致 |
| docs | `d12df41` | `d12df4165108d59a2a4f08ba3ba93a35935df846` | 一致 |
| base | `bb2e914` | `bb2e9142a4e96e2b8fbe65bb99f1b4c045260251` | 一致 |
| build/head | `0d5e5e0` | 同 HEAD；d12df41 后仅 `2894667`/`0d5e5e0` 两个 builder 提交 | 一致 |
| main worktree | clean | `git status --porcelain -uall` 为空 | 一致 |

- `d12df41` 仅改 `docs/` 5 个文件（矩阵 + 4 份 docs），未改 `src/`；`d12df41..HEAD` 只有 packet builder 两个提交。
- `git diff --binary bb2e914..e7d9296 -- src scripts/g4 scripts/security config/g4 tests/integration/g4_f2 tests/integration/g4_f3 tests/integration/g4_f5 tests/security` 经 Packet 文档化替换（`<WORKSPACE>`/`<HOST_PYTHON>`/`<HOST_HOME>` 等）后与 `changes/implementation.diff` **逐字节相同**；未替换原始 diff 与 Packet 的差异全部来自该隐私替换，不是内容差异。
- `git diff --binary bb2e914..d12df41 -- docs` 经同样替换后与 `changes/docs.diff` 逐字节相同。
- protected files（`gates.py`/`run_live.sh`/`dsh_adapter.py`/`cli.py`）base→impl **零 diff**；当前字节 SHA-256 分别为 `3ed08634…`、`a8a2753f…`、`88891149…`、`31555386…`，与 base blob 和 Packet 记录一致。
- `git diff` 对照写入 `artifacts/reviewer-g4f/r0-identity/r0.json`；完整 diff 副本在 `/tmp/g4f-impl-code.diff`、`/tmp/g4f-docs-base.diff`（仅本会话临时证据）。

### 2.2 Packet 177/173

- `sha256sum -c hashes.sha256`：**173/173 OK，exit 0**。
- 目录共 **177** 个普通文件、**0** symlink。
- 177 与 173 的差为 4 个未哈希文件：
  1. `hashes.sha256`（自哈希排除，设计如此）；
  2. `packet-integrity-report.txt`（设计排除）；
  3. `f4/sqlite-readonly/resume-attempts.sqlite3-shm`（32768 bytes）；
  4. `f4/sqlite-readonly/resume-attempts.sqlite3-wal`（0 bytes）。
- **P2-01**：后两个 SQLite sidecar 在 Packet 构建后（mtime 15:11Z，Packet created 15:09:08Z）出现，未进入 `hashes.sha256`，也不在 manifest `files.count=172` 中；用当前全量 payload 复算 tree 得到 `111c1361…`，与 manifest `e464b9b1…` **不匹配**；剔除这两个 sidecar 后复算恰为 `e464b9b1…`。WAL 为空、SHM 只有空 frame header，因此不含业务数据，hashed `.sqlite3` 仍完整；但“177/173 的未哈希 payload 只有元数据”这一说法不成立，冻结包的 payload tree 自校验已漂移。
- Packet 敏感模式独立扫描：`sk-`/AWS/GitHub/PEM/`/root` 宿主路径均为 0；`DEEPSEEK_API_KEY` 仅出现在 masked audit 记录中。`session.v4.jsonl` 只作为 F4 元数据路径出现，未包含原始用户 session。
- `env/zero-key.json` 的 `live_gate_reasons` 只有 1 项，而 manifest 与 `review/livegate.json` 有 4 项；两者均为 BLOCKED。**P2-07**。
- manifest nested 字段核对：`stage`（base/manifest/tree/trusted/candidate）与 2.3 复算一致；`contract.state_constants` 与第 1 节常量逐项相同（G4-H/G5/G6/LiveGate/M0/E5_PRELIVE_FULL）；`contract.reviewer=NOT_ASSIGNED`、`reviewer_status=PENDING_INDEPENDENT_REVIEW` 保持冻结；`evidence_levels` 与 R7 分级一致；`sqlite.files` 14 个只读副本均存在；`test_stats` 的 host/OCI/Node 计数与 Owner 记录一致（host 归因差异见 P2-08）。
- 旧 G3/G4 Packet 与 `docs/REVIEW_G4_INDEPENDENT.md` 未被修改（main worktree 除本报告外 clean；旧目录仅只读访问）。

### 2.3 Stage 与 loaded modules

- `stage-20261119T142828Z`：manifest `82e10c6ffe37…`、tree `7d32ec1d8b02…`、trusted tree `6d887bbf4c83…`、candidate tree `2459db9df83b…`——独立复算全部一致；`base_sha=head_at_build=e7d9296`。
- 从**真实 P2 运行**（`r5-windows/.../peercred/trusted-modules.json` 的容器 self-report `inspect.getfile`/`real_path`）读取 18 个模块，逐模块比较 `loaded_sha256 == HEAD blob == stage trusted 副本`：**18/18 全部一致**（`r0-identity/loaded-modules-check.json`）。实际加载来源是 `/project/src/...`（stage trusted），不是旧 G3-C/G3-D stage。
- 旧 stage fail-closed：
  - 旧 G4 stage `stage-20261119T135204Z` → preflight exit **2**，`stage_manifest_invalid, stage_base_not_head`；
  - 旧 G3-D stage `stage-20261117T221955Z` → 同 exit 2；
  - 复制并篡改 `trusted/run/trusted_entry.py` 的 stage → exit **2**，`stage_manifest_invalid`；
  - 三次均未启动任何容器（`podman ps -a` 为空），证据在 `r0-identity/stage-*/`。

---

## 3. R1 — 静态复验

- `gates.py`：无 `authorize()`/`approve()`/环境/文件批准入口；`LiveGate.inspect` 的第一条 reason 恒为 `EXTERNAL_HUMAN_AUTHORIZATION_BOUNDARY_NOT_DEPLOYED`，即使 baseline、tools、session-log 全部满足也返回 `BLOCKED`；`require_live` 抛 `SecurityBlocked`。
- `run_live.sh`：恒输出 `BLOCKED` 并 `exit 3`；与 base 字节相同。
- `dsh_adapter.py`：四个 live 入口 `_require_live_authorization`、`_new_harness`、`run`、`resume` 均先抛 `SECURITY_BLOCKED`，均在 SDK import/任何 socket 之前；与 base 字节相同。
- `cli.py`：`--live` 在 import SDK、目录创建、读取 approval 之前调用 `LiveGate.require_live()`，返回 exit 3；与 base 字节相同。
- `authorization.py`：严格 JSON/字段/路径/5 绑定根/预算镜像/单次消费；`O_CREAT|O_EXCL|O_NOFOLLOW` 创建 use record；并发只允许一个成功（但存在 P2-03 的 loser 错误码竞态，见下）。
- `egress.py`：`TrustedSendAuthorization` 无 JSON 构造入口；`consume` 一次性；`real_route` 恒 `BLOCKED`；无 Broker 写入（`budget_reservations`/`reserve`/`settle` 均不出现），只读复制 Broker `reserved_cost`/settlement；cost view 是 `billing_authority=false` 的 process-local 保守视图。
- `controller.py`：`dispatch_gate=None` 时保持 G3-C/D 行为；门开启时唯一发送路径为 `authorize → consume → dispatch`。per-dispatch 校验（route/model、tool name+schema、重复 tool、message tool-call/addition/removal、purpose、origin）全部在 Reserve/Claim 之前；dispatch journal 写入失败只计数、不改变 allow/deny（F2-R5 已披露）。
- `ipc_server.py`：`SO_PEERCRED` 在任何帧读取/ack 前校验；transport 的 origin 仅在部署声明 `expected_peer_uid` 时成为 fail-closed 条件（G4-C 配置即如此）。
- 代码中无 `requests`/`urllib`/`http.client`/`httpx`/`aiohttp`/`socket.create_connection`；`src/` 内唯一的 `socket` import 是 `ipc_server.py` 的 AF_UNIX。静态证据：`r1-static/static-audit.json`。

---

## 4. R2 — 自建 Scanner 负例（F1 独立验证）

在 `/tmp` 自建 git 仓库（不修改工作区、不使用 Owner 测试）：

- **31 个正例**：OpenAI `sk-`、AWS `AKIA`、GCP `AIza`、Slack token/webhook、GitHub/GitLab/npm/HF、JWT/JWE、Bearer、Basic、Azure AccountKey、PEM（无标签/RSA/EC/DSA/OPENSSH/ENCRYPTED/PGP BLOCK）、DB URL、连接串、URL query、KNOWN/GENERIC env、YAML/JSON 赋值；全部 exit 1 且对应 `kind` 命中。
- **哨兵夹带**：`SENTINEL<hex>`、`SENTINELsk-…`、`TEST_ONLY_<hex>`、`TEST_ONLY_<base64>`、`sentinel_abc123`、`ZzSENTINEL…`、`SENTINEL_`+长数字——全部 exit 1，`env-key-assignment` 命中。
- **26 个纯哨兵/占位符**（`SENTINEL`/`TEST_ONLY_NEVER_VALID_SECRET_SENTINEL`/`FAKE`/`PLACEHOLDER`/14 个前缀 + `_SELFTEST_VALUE`/`sk-FAKE…`/`Bearer abc...`）——exit **0**，`SECRET SCAN OK`。
- 正例输出**不含完整 Secret**；独立检查 31 个案例的完整值均未出现在 stdout/stderr。
- 历史仓库“提交 Secret 后删除”：带 `--json`/全历史 exit 1，`--no-history` exit 0，历史值未泄漏。
- 主工作树全历史 + 工作树 + commit message：`scanned_files=473, scanned_blobs=746, scanned_commits=168, findings=0`；impl worktree `467/746/168, findings=0`；`--self-test` PASS。
- 对 F1 测试做变异验证：把 `_is_env_test_sentinel` 改成恒 True → `test_sentinel_lookalikes_are_reported` **FAIL**；禁用检测器 → `test_positive_detectors` **FAIL**；把 `_mask` 改成返回原值并用 subprocess 运行 → `test_temporary_repo_positive_exit_1_and_masking` **FAIL**。说明测试是真断言，不是空转。
- 残余（F1-R4）：`_is_placeholder` 仍以 `fake/example/sample/none/null/abc…` 子串排除；极端构造的真实 token 可能被误排除。本轮历史审计 0 findings，未发现可利用真实值；属 scanner 启发式残余，不是 P0/P1。

证据：`r2-scanner/probe.json`、`mutation.json`、`mutation-mask.json`、`run.log`。

---

## 5. R3 — 真实 Candidate UID 65534 OS/raw-UDS 攻击

真实双 Principal（trusted root + Candidate UID map `0→65534`，candidate 内部 `os.getuid()==0`、`CapEff=0`、`NoNewPrivs=1`、`Seccomp=2`），`--network none`，固定 rootfs/deps/stage；Candidate 只挂 `/project` ro、`/deps` ro、`/work/session` rw、`/work/g3b` ro。

### 5.1 OS 攻击

| 目标 | 结果 |
|---|---|
| `/work/state`、`admission.json`、`g4c-policy.json`、`broker.sqlite3`、`attempts.sqlite3`、`revocations`、`g4c-revocation.json` | **ENOENT**（Candidate mount namespace 根本没有 trusted state） |
| `/work/session/../state`、`/root`、`/etc/shadow` | **ENOENT** |
| 写 `/work/state/...` | **ENOENT** |
| 写 `/project/...`、`/work/g3b/...` | **EROFS** |
| 写 `/work/session/...` | 允许（预期的 Candidate 自有 session） |
| `open("/work/g3b/bridge.sock")` | **ENXIO** |
| `connect("/work/g3b/bridge.sock")` | 成功（唯一可用 IPC） |
| 宿主同 UID 65534 访问 run state/policy/DB/socket | **EACCES**（run 目录 root 0700，文件 0400/0600；DAC 机制） |
| 宿主同 UID 65534 读 stage trusted code | 可读 0444（stage 是可信代码，不是秘密；不构成状态读写） |

### 5.2 raw-UDS 协议攻击（严格纯负例）

真实 Candidate 通过真实 UDS 发送 12 个负例：

- unapproved tool name、modified approved schema、extra tool、duplicate tool、message `tool-call`/`tool-addition`/`tool-removal` → `ADMISSION_TOOL_SCHEMA_MISMATCH`；
- purpose `title`/`judge`/`compaction` → `BAD_TYPE`；purpose omitted → `REQUEST_INVALID`；
- 自授权字段 `authorized` → `UNKNOWN_FIELD`。

纯负例后账本：**Reservations=0、Claims=0、Attempts=0、Intents=0、g3b_request_identities=0、Receipts=0、Fake=0**；7 条进入 Controller 的 tool 负例在 dispatch-window 均为 `rejected, reserved=false, dispatched=false`；policy 文件 SHA-256 `73eb3987…` 与 launcher 写入值一致；Broker/attempts DB 无业务行。随后批准正例和 replay：

- 批准 `skill_lookup` → ack+chunk+chunk+finish；
- 同业务身份 replay → `ATTEMPT_ALREADY_STARTED`，无新 reservation/attempt/Fake；
- 第二个业务身份（session 不同）→ 正常 1 个新 reservation/attempt/receipt；最终 2/2/2，Fake=2；没有重复发送。
- 说明：同一 prepared provider payload 在不同 session 下 call_id 可相同（step 相同），但业务 identity 不同；replay 的拒绝发生在 `claim_request_identity`，没有进入 Reserve。不是双发送。

证据：`r3-os/campaign-20261119T152540Z.json`、`r3-os/neg-only-20261119T152859Z.json`；peercred/caps/mountinfo 在 `r3-os/campaign-*/` 与 `r5-windows/.../peercred/`。

---

## 6. R4 — 真实 DSH Tool / Echo / Session Resume / 账本

所有 L2 运行使用真实 DSH `0.2.2-rc.2`、真实 trusted Controller/Broker/Fake、`--network none`、固定 rootfs/deps/stage；SQLite 复制到 `/tmp` 只读打开，不使用 Owner checks 作为结论。

### 6.1 Echo 与 Tool 两轮

| run | Res/Claim/Attempt/Intent/Receipt/Fake | 独立结论 |
|---|---:|---|
| Echo | **1/1/1/1/1/1** | dispatch=1=assistant=receipt；call/reservation/receipt 唯一；`prepared_digest==claim.request_digest`；`attempt.payload_digest==receipt.raw_sha256`；usage 映射 `input_used=13`（11+2+0）、`output_used=5`；title 1 次 `source.kind=fallback` |
| Tool 两轮 | **2/2/2/2/2/2** | 2 个不同 call_id/reservation/attempt/receipt；两组 digest 链均相等；Broker 2×OK，各结算一次；dispatch=2=assistant=2=receipt；title 1 次 fallback；无额外 provider 请求 |

- 两轮 Tool 的 DSH assistant usage 与两份 receipt usage 字段级相等；Broker settlement `input_tokens=13/output=5`，cost `0.001022` 各一次。
- dispatch-window 的 origin 为 `{kind:"unix_peer", uid:65534, gid:65534, pid:0}`；tool `skill_lookup` 的 schema/approved SHA 均为 `c984bef0…`；journal `reserved/dispatched/settled=true`。
- Evidence：`r4-resume-ledger/f2-echo/`、`f2-tool/`、`r4-audit.json`、`usage-equality.json`。

### 6.2 真实 Session Resume（正向）

`run_g4_f4.py --keep-run` 在 `e7d9296` stage 上重跑，独立解析 phase DB / receipt / session JSONL：

- turn1 `start_session` → turn2 `resume_session`（同一 `g4f-f4-s1`），两个独立 Candidate 容器；turn1 session 14 行/3597 bytes，turn2 24 行/6005 bytes，`resume_marker_count=1`。
- 账本：turn1 1/1/1/1/1；turn2 **累计** 2/2/2/2/2；旧 attempt 行在 turn2 后逐字段不变；两个 call_id/reservation_id/receipt_id 两两不同；Broker 2×RESERVED + 2×SETTLED，无 FAILED/RELEASED；每 reservation 恰一次 settlement。
- usage：两请求 DSH assistant usage == 各自新 receipt usage（`11/2/0/5/0/18`）；Broker `input_used=13`、`output_used=5`、cost `0.001022`。
- 上下文：turn2 session 包含 turn1 的 user/assistant 历史；`request/header` 有 `reason=resume`；turn2 provider payload 长度 1875 > turn1 1509、digest 不同。仅证明“语义重放 + 只发新请求”，**不做字节级包含证明**（F4-R1）。
- 旧 attempt 不变、旧 receipt 不变、无二次结算、Fake counter 1→2（只增 1）。

### 6.3 crash-resume 负例

- trusted crash hook 后：1 reservation PENDING、1 attempt `ATTEMPT_STARTED`、Fake=0、0 Receipt；recovery 后 attempt 变 `SETTLEMENT_UNCERTAIN`（reason `NO_RECEIPT_AFTER_CRASH`），reservation 仍 PENDING；resume turn2 未新增 attempt/reservation/receipt，Fake 仍 0；DSH turn2 失败于 `G3B_BRIDGE_CONNECT_FAILED`。
- 该负例只证明“无存活 Controller 时 resume 不重发”；candidate crash + live Controller 子场景仍 UNVERIFIED（F4-R2）。

证据：`r4-resume-ledger/f4-keep/`（phase DB + session）、`r4-audit.json`。

---

## 7. R5 — Revocation / Timeout / In-flight 窗口

独立重跑 9 个真实双 Principal case（7 DSH + 2 hold raw-UDS；`r5-windows/f5-cases/`），逐 case 解析原始 DB、receipt、gate journal、dispatch-window：

| case | Res/Att/Receipt/Fake | 状态 | 结论 |
|---|---|---|---|
| `revocation-pre-reserve` (DSH) | 0/0/0/0 | — | gate `REVOCATION_CHECK pre_reserve RUN_AUTHORIZATION_REVOKED`；dispatch `rejected, reserved=false`；0 ledger/Fake |
| `revocation-post-reserve` (DSH) | 1/1/0/0 | PENDING / SETTLEMENT_UNCERTAIN | gate `REVOCATION_CHECK pre_dispatch` + `DENIED`；`reserved=true, dispatched=false`；recovery `held=0.002684, known=0` |
| `revocation-in-flight` (DSH) | 1/1/1/1 | OK / SETTLED | receipt 先落盘，撤销在 wire 后；Broker 1×OK、1×SETTLED；无重发/双结算；新请求无新增 |
| `timeout-pre-send` (DSH) | 0/0/0/0 | — | deadline 800ms + 2500ms pre-reserve delay；0 reservation/attempt/Fake |
| `timeout-post-send` (DSH) | 1/1/1/1 | PENDING / UNCERTAIN | Fake 收到字节后 stall；`dispatched=true, settled=false`；held=0.002698==reserved；不 FREE/不重发 |
| `crash-after-authorize` (DSH) | 1/1/0/0 | PENDING / UNCERTAIN | gate journal `AUTHORIZED` 1、`CONSUMED` 0；held>0；Fake=0 |
| `crash-after-consume` (DSH) | 1/1/0/0 | PENDING / UNCERTAIN | gate journal `AUTHORIZED` 1、`CONSUMED` 1；capability 已消费；Fake=0 |
| `crash-before-send` (hold) | 1/1/0/0 | PENDING / UNCERTAIN | 重放 `ATTEMPT_ALREADY_STARTED`；held=reserved；Fake 不增 |
| `crash-after-receive` (hold) | 1/1/1/1 | OK / SETTLED | receipt/Broker 结算一次；恢复未重发；Fake 仍 1 |

- 所有 case：无 `cost=0`、无双重 settlement、无第二次 Fake；`containers_after=[]`。
- `revocation-post-reserve` 的 recovery attempt reason 被写成 `RECEIPT_DOCUMENT_SCHEMA_INVALID`（不是原始 `RUN_AUTHORIZATION_REVOKED`）；状态/held 仍保守，gate journal/dispatch-window 保留原始原因。Owner 已披露（F5-R5），**P2-06**。
- `timeout-pre-send` 没有 dispatch-window 记录（Owner F5-R4 披露；证据来自 0 行 DB/Fake 与 DSH error）。**P2-05**。
- 可停止 vs 只能保守：pre-reserve / pre-send（未 Reserve）可停止；已 Reserve 未跨 wire 只能保守（PENDING/UNCERTAIN/held>0，不 settle/fail/重发）；已跨 wire（receipt 存在）只能按 Broker 终态结算一次，不撤回/不双结算。

证据：`r5-windows/f5-cases/`、`r5-windows/r5-audit.json`、`r5-windows/gate-summary.json`。

---

## 8. R6 — LiveGate / Key / Network / E5 两列

| 负例 | 独立结果 |
|---|---|
| `LiveGate.inspect` 全部证据满足（live_requested=True、actual==reviewed baseline、tools==`skill_lookup`、session_log_disabled=True） | `BLOCKED`，reason 仍含 `EXTERNAL_HUMAN_AUTHORIZATION_BOUNDARY_NOT_DEPLOYED`；`external_boundary_deployed=false` |
| `require_live` | 抛 `SECURITY_BLOCKED` |
| `/bin/sh scripts/run_live.sh` | exit **3**，BLOCKED 文本 |
| CLI `smoke --live`（含 `AT_M0_LIVE_APPROVED`/`AT_M0_ALLOW_LIVE`/`AT_M0_APPROVAL*`/假 `DEEPSEEK_API_KEY`） | exit **3**，`SECURITY_BLOCKED`；env/Markdown/自签 JSON 无 effect |
| Adapter 四入口 `_require_live_authorization`/`_new_harness`/`run`/`resume` | 全部 `RuntimeFailure code=SECURITY_BLOCKED` |
| `strace -f -e trace=network` on CLI/run_live | 无 socket/connect 系统调用 |
| 0 Key/外网 | 无 `.env`；无 Key-like env；`key_present=false`；`real_model_calls=0`、`real_external_http_calls=0`、`provider_keys_seen=0` |

E5 两列（独立复核）：

| 项 | NO_KEY_SUBSET | FULL_STATUS |
|---|---|---|
| E5-P01 | PASS（`e5_probe p01-binding` 5/5：合成签名、冻结字节、单次记录、漂移拒绝） | `BLOCKED_PENDING_HUMAN_DEPLOYMENT` |
| E5-P02 | PASS（p02 10/10：五 root 漂移、route、tool schema、denied no-send） | `BLOCKED_PENDING_HUMAN_DEPLOYMENT` |
| E5-P03 | PASS（p03 7/7：Markdown/env/self-sign/CLI/run_live/adapter/gates.py 无 env 批准） | `BLOCKED_PENDING_HUMAN_DEPLOYMENT` |
| E5-P04 | **UNVERIFIED**（p04 证明 capture fixture/allowlist 只有 skill_lookup，且 DSH registry export absent；无权威 merged registry） | `BLOCKED_PENDING_HUMAN_DEPLOYMENT` |
| E5-P05 | **PASS**（reviewer 重跑 p05 5/6：scanner 正控、env scrub、candidate argv 无 sentinel、mount 不含 trusted fixture、`--network none`；D01/D02/D03 watchdog 原始证据 24/24、23/23、21/21 checks 全部 PASS 且 `PENDING_CONSERVATIVE`，未由 reviewer 重新执行） | `BLOCKED_PENDING_HUMAN_DEPLOYMENT` |
| E5-FULL | BLOCKED | `BLOCKED_PENDING_HUMAN_DEPLOYMENT` |

- `F2-08`/E5-P04 仍 UNVERIFIED；`E5-FULL` 仍 BLOCKED；G4-H/G5/G6/M0 常量不变。
- 证据：`r6-negatives/livegate.json`、`strace-*`、`e5/p01..p05.json`。

---

## 9. R7 — 矩阵、证据分级与独立 SQLite/JSONL 解析

### 9.1 矩阵

- 46 行：**38 PASS / 2 UNVERIFIED / 5 NOT_RUN / 1 BLOCKED**，与 Owner 数字一致。
- `F2-08`（B03/E5-P04 registry）UNVERIFIED；`F4-06`（字节级 context / candidate-crash live）UNVERIFIED；`E5-FULL` BLOCKED→`BLOCKED_PENDING_HUMAN_DEPLOYMENT`；5 个 `REV-*` 原为 NOT_RUN。
- **REV-01..05 独立复核结论**：全部 **PASS**（R0/R1 Packet/stage/旧 stage；R2/R3 scanner/OS/raw-UDS；R4/R5 resume/账本/窗口；R6/R7 LiveGate/矩阵/原始解析；R8 回归/清理/分级）。矩阵本身**未被修改**，REV 行仍保留 NOT_RUN 以维持冻结字节。
- 逐行 evidence path 独立检查：仅 **F2-07** 的 `artifacts/g4f/f6/integration/f2/tool-window.json` 不存在；实际文件在 `artifacts/g4f/f2/tool-window.json`（12:34Z，F2 owner run），F6 summary 仍可验证同一 3 dispatch/title fallback 结论。**P2-02**。
- `F2-01`/`F3-08`/`F4-01`/`F6-02`/`F6-04` 的矩阵路径含描述性括号/brace，去掉描述后实际文件均存在；F6-05 的 `hashes.sha256`/`packet-integrity-report.txt` 在 Packet 根目录存在。

### 9.2 F3 L2 独立对账

从 F6 `f3-l2/runs/*` 复制 DB 到 `/tmp` 只读解析：

- c01：1 OK/1 SETTLED/1 receipt/Fake 1；gate known=`0.001022`、held=0。
- c02：2 OK/2 SETTLED/2 receipt/Fake 2；known=`0.002044`、held=0。
- replay：1/1/1/Fake 1；known 不变。
- crash-before-send：1 PENDING/1 UNCERTAIN/0 receipt/Fake 0；recovery held=`0.001619`==reserved、known=0。
- crash-after-receive：1 OK/1 SETTLED/1 receipt/Fake 1；recovery known=`0.001022`。
- quota：1 OK/Fake 1，无第二次 reserve；broker-down：0 reservation/Fake 0。

结论：F3-08 的 L2 账本与 held 语义可独立复算，Broker 仍是唯一费用权威。

### 9.3 分级

- **L2-REAL-DSH**：Echo、Tool 两轮、Resume（正向+crash-resume）、9 个 F5 case（7 DSH + 2 hold）。
- **L2-RAW-UDS**：R3 真实 Candidate UID 65534 raw-UDS 负例/正例。
- **L2-OS**：真实容器 OS probes、fixed OCI filtered、Node 36。
- **L1-HOST**：full host pytest、targeted suites、F3 host cases。
- **L1-STATIC**：scanner、diff/字节、静态 grep。
- **L1-PACKET**：Packet hash/tree/manifest/loaded modules。
- **UNVERIFIED**：B03/E5-P04 registry；F4 字节级 context 与 candidate-crash/live-controller；E5-P05 watchdog 的**执行**未由 reviewer 重跑（原始证据已重读）；外部 SIGKILL 全窗口；真实 Provider/TLS/账单。
- **HUMAN-REQUIRED**：E5 Full、G4-H、真实 Key/Provider/计费/部署。
- 本报告**没有**把上述级别拼成“全链 PASS”；PASS 仅覆盖 G4-F no-key closeout。

---

## 10. R8 — 回归、清理与证据卫生

### 10.1 Host

- 两次 full host（`tests/`，Python 3.11.15 + deps）：
  - run1（config 权限未修）：**1351 passed / 5 failed / 1 skipped**；失败 = g3d frozen-src、g4_d D15 host-env、runtime target-profile（worktree config 0644）、sandbox PYTHONPATH、**a12 concurrency flake**。
  - run2（`chmod 0444` config 后）：**1352 passed / 4 failed / 1 skipped**；失败 = g3d frozen-src、**a12 concurrency flake**、g4_d D15 host-env、sandbox PYTHONPATH。
- Owner 数字 1352/4/1 在 run2 复现，但失败集合不同：Owner 的 target-profile 项在 run2 通过，替换为 a12。**P2-08**。
- **P2-03（新发现）**：`tests/integration/g4_a/test_a12_replay_epoch.py::test_a12_concurrent_consumption_admits_exactly_one` 独立循环 **2/30 失败**（full suite 2/2 失败）；失败形态是第二个 consumer 读到尚未写完的 use record，返回 `AUTHORIZATION_USE_RECORD_INVALID` 而非 `AUTHORIZATION_REPLAYED`。恰好一个 consume 成功、无发送/计费/双消费；安全姿态 fail-closed，但证据/错误码稳定性不足。复现：`for i in ... pytest ...::test_a12_concurrent...`（见 `r8-regressions/host/a12-fail.log`）。
- targeted suites（g4_a/b/c/d、g4_f2/f3/f5、g3c、g3d、g3_bridge、security、gates）：**718 passed / 5 failed / 13 skipped**（首轮；g4_b 3 项因隔离 worktree 缺 `artifacts/g3d` stage，补 symlink 后 **g4_b 38/38 PASS**；target-profile 补 `chmod 0444` 后 4/4 PASS）。
- `tests/security` 7/7 PASS；g4_f2 30、g4_f3 23、g4_f5 12、g4_c 78、g4_a 223 等均在 full run 中通过。

### 10.2 OCI / Node / Ruff / Scanner

- **fixed OCI filtered**（固定 rootfs `25491e45…`、deps `e07729d7…`、`--network none --read-only --cap-drop ALL`、`--user 65534:65534`、**43 个显式 deselect**，含 `test_digest_sidecar_contract`）：**1018 passed / 26 skipped / 43 deselected / 0 failed**，70.55s；与 Owner filtered 计数一致。证据：`r8-regressions/oci-filtered/oci.log`、`run.json`。raw OCI（无 deselect）与 OCI uid-0 replay（351/8）未由 reviewer 重跑，依赖 Owner 原始日志（`artifacts/g4f/f6/integration/oci/oci-raw.log`、`oci-root-replay-filtered.log`）；这两项不改变 filtered 的产品测试覆盖结论。
- **Node**（固定 rootfs、真实 TAP）：adapter 9/9、guard 19/19、skill 8/8 → **36/36**；证据 `r8-regressions/node/*.log`。
- **Ruff 0.17.5**：product + G4-F tests scoped → **All checks passed**；单独扫 `tests/security/test_scan_git_secrets.py` 有 1 个 **F841**（`material` 未使用，F6-06 已披露）。**P2-04**。
- **Scanner**：self-test PASS；全历史/工作树 0 findings（168 commits）；独立负例见 R2。

### 10.3 清理与 canonical

- 主 rootfs/deps/stage 在复核前后均为 `25491e45…` / `e07729d7…` / `7d32ec1d…`；main worktree clean。
- L2/OCI/Node 在 `/tmp` 副本上运行；副本的 rootfs 曾被 podman 创建 mount-target 目录（`evidence`、`var`、`plugin`、`probe` 等），已清理并复算 canonical；**主 rootfs 未被改动**。
- `podman ps -a` 为空；无 `.env`；无 Key-like env；未执行 `podman pull`；未 commit/push。

---

## 11. P0 / P1 / P2

### P0（权限绕过 / 可计费出站 / Key 泄漏 / 未授权 Fake / 账本 FREE / 双发送）

**P0 = 0。**

逐类证伪尝试：

1. **真实 Key/网络**：全 `src/` 无 HTTP 客户端/网络 import；CLI/run_live strace 无 socket/connect；所有容器 `--network none`；无 `.env`/Key env；`provider_keys_seen=0`，`real_model_calls=0`，`real_external_http_calls=0`。
2. **LiveGate 放行**：全部证据满足仍 BLOCKED；env/Markdown/自签 JSON/CLI/CLI env/run_live/adapter 四入口全部拒绝；`gates.py`/`run_live.sh`/`dsh_adapter.py`/`cli.py` 与 base 字节相同。
3. **Candidate 读写可信状态**：真实 UID 65534 在 candidate mount namespace 中 `/work/state` ENOENT；宿主同 UID 对 run state/DB/socket EACCES；纯负例 0 reservation/attempt/receipt/Fake，policy hash 不变。
4. **未授权/重复 Fake**：未批准/改 schema/额外/重复/message tool refs/purpose/self-auth 全部在 Reserve 前拒绝；replay `ATTEMPT_ALREADY_STARTED`；Fake counter 只在批准请求后增加，单 reservation 最多 1 次 Fake。
5. **假结算/FREE/双发送**：Broker 是唯一费用权威；PENDING 时 gate held=reserved>0、known=0；OK/FAILED 才释放且每 reservation 一次；无 `cost=0`；crash/timeout/revocation 均不产生第二次 Fake 或第二次结算。
6. **旧 Stage/篡改**：旧 G3-D/G4 stage 与篡改 stage 均在 preflight exit 2，未启动容器。
7. **Packet 篡改**：173/173 hash 通过；diff 与 protected files 一致；sidecar 漂移是未哈希元数据/空 WAL，不构成密钥或账本篡改（P2-01）。

### P1（关键部署契约不一致 / 凭据边界失效 / 结算恢复错误 / 核心主张缺动态证据）

**P1 = 0。**

- 未发现凭据边界失效、未发现结算恢复错误、未发现未记账发送路径。
- Owner 的 4 项 host 失败均可归因（frozen-src、D15 0700-home、config mode、sandbox PYTHONPATH）；a12 是 fail-closed 的错误码竞态，不是发送/账本错误（P2-03）。

### P2（不影响本轮限定范围的证据/运维/测试稳定性）

| ID | 发现 | 影响 / 处置 |
|---|---|---|
| **P2-01** | Packet 的 2 个 SQLite sidecar 未哈希；manifest payload tree 已不匹配（去 sidecar 后匹配） | WAL 空、SHM 空 frame，无业务数据；建议重冻结或删除 sidecar 后重建 hashes/tree |
| **P2-02** | 矩阵 F2-07 的 `f6/.../tool-window.json` 路径不存在；实际在 `artifacts/g4f/f2/tool-window.json` | 结论仍可由 F6 summary/独立 Tool run 验证；修正矩阵路径即可 |
| **P2-03** | G4-A a12 并发 consume 错误码竞态：loser 可能 `AUTHORIZATION_USE_RECORD_INVALID` 而非 `AUTHORIZATION_REPLAYED`；2/30 standalone、2/2 full-host 失败 | 恰好一个 consume，fail-closed；无发送/计费。建议原子写 use record（临时文件 + link/rename）或 reader 对空/部分文件重试 |
| **P2-04** | `tests/security/test_scan_git_secrets.py` F841（F6-06 已披露） | 不影响扫描器行为；清理测试变量即可 |
| **P2-05** | F5 `timeout-pre-send` 无 dispatch-window 记录（F5-R4） | 0 行 DB/Fake + DSH error 仍可证；观察缺口 |
| **P2-06** | F5 recovery 把 revocation attempt reason 重写为 `RECEIPT_DOCUMENT_SCHEMA_INVALID`（F5-R5） | gate journal/dispatch-window 保留原始 `RUN_AUTHORIZATION_REVOKED`；状态/held 保守 |
| **P2-07** | Packet `env/zero-key.json` 只列 1/4 LiveGate reasons | manifest 与 review/livegate 有 4 项，均为 BLOCKED；证据一致性修正 |
| **P2-08** | Host full 失败集合与 Owner 归因不同：run2 计数 1352/4/1 但 a12 替换 target-profile | 计数一致、集合不同；a12 为 P2-03，target-profile 为 worktree config mode 环境差异 |

---

## 12. 明确未验证 / human-required

1. **E5 Full**：真实人类授权、真实 Key/Provider/TLS/账单/额度、外部 trust root、部署后不可写；**BLOCKED_PENDING_HUMAN_DEPLOYMENT**。
2. **G4-H / G5 / G6 / Live**：NOT_AUTHORIZED / BLOCKED / NOT_RUN / BLOCKED；本报告不签发。
3. **B03 / E5-P04**：DSH 0.2.2-rc.2 无权威 merged tool registry/schema 导出；只证明实际 per-dispatch tool 面可观测且受 Admission 白名单约束；**UNVERIFIED**。
4. **F4-R1/R2**：无字节级 context 包含证明；candidate crash + live Controller 自动重试子场景未覆盖。
5. **E5-P05 watchdog 腿**：reviewer 重跑 scanner/env/argv/mount/network 5 项；D01/D02/D03 watchdog 的原始 `watchdog.json`/`pending.json` 被独立重读（24/24、23/23、21/21 checks，全部 PASS，`PENDING_CONSERVATIVE`），但未由 reviewer 重新执行外部 watchdog 进程；这一执行层面的独立复跑仍属 G4-D 历史证据。
6. **F5-R6**：外部 SIGKILL 的纳秒级窗口未枚举；使用产品既有 `os._exit(97)` test-only crash hook。
7. **OCI raw / uid-0 replay**：raw 的 26 failed/43 errors 与 root replay 351/8 未由 reviewer 重跑；filtered 1018/26/43/0 已独立复现，raw 差异按 Owner 分类为环境类。
8. **F5-R4/R5**：观察缺口/reason 重写见 P2-05/P2-06。
9. **F1 启发式**：scanner 不是泄漏保证；`_is_placeholder` 极端构造可能误排除（F1-R4）；历史审计 0 findings。
10. **F2-B07**：仅冻结配置下 session-title fallback-only；未来配置/动态注册不可证明（F2-R1）。
11. **真实 Provider/计费**：0 Key/0 模型/0 外网；所有费用为 synthetic fixture。

---

## 13. 结论与 STOP

```text
PASS_FOR_G4F_NO_KEY_CLOSEOUT_SCOPE
P0 = 0
P1 = 0
P2 = 8
G4-H = NOT_AUTHORIZED
G5 = BLOCKED
G6 = NOT_RUN
LiveGate = BLOCKED
M0 = DECISION_PENDING
E5_PRELIVE_FULL = BLOCKED_PENDING_HUMAN_DEPLOYMENT
```

本裁定仅覆盖本机冻结环境、无 Key、无真实 Provider/计费/TLS/Live 的 G4-F closeout engineering scope。**不进入 G4-H/G5/G6**，不签发 Live 授权，不把无 Key 子集 PASS 映射为 E5 Full 或 `M0_GO`。STOP。

---

### 附：报告与证据 SHA-256

- 本报告：见交付消息中的 `sha256sum docs/REVIEW_G4F_INDEPENDENT.md`。
- 证据索引：`artifacts/reviewer-g4f/RUN_INDEX.md`；裁定 JSON：`artifacts/reviewer-g4f/VERDICT.json`。
