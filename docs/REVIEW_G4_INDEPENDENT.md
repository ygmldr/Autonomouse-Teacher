# M0 G4 — 独立 Reviewer 报告（No-Key PreLive Engineering Scope）

- 报告 ID：`REVIEW-G4-INDEPENDENT-20261118T2141Z`
- Reviewer：未参与 G4-00/A/B/C/D/E 实现、证据生成、矩阵填写或 Packet 构建的独立 Agent
- 复核对象：`base 017c747` → `impl a6f3e0a` → `code d3d429c` → docs/build/head `8e5ca7a`
- Packet：`artifacts/review-packet-g4-a6f3e0a27a516534803a1e3549dc60fbd107583c/`
- 复核窗口（UTC）：`2026-11-18T20:47Z` → `2026-11-18T21:41Z`
- 只写两处：本文件与 `artifacts/reviewer-g4/`（gitignored）；**未 commit / 未 amend / 未 push**
- 证据索引：`artifacts/reviewer-g4/RUN_INDEX.md`

---

## 0. 独立性声明（必须先读）

1. 我未参与 G4-00、G4-A/B/C/D 的任何实现、测试编写、证据生成、矩阵填写或 Review Packet 构建；未参与 G3-C/G3-D 的实现。
2. 我未修改 `src/`、`scripts/`、`tests/`、`config/`、`plugins/`、Stage、rootfs/deps、历史证据/矩阵/Packet；`git status --porcelain` 在复核前后为空（仅本报告为新建未跟踪文件）。
3. 本报告的关键结论来自我自己的命令、自建 Probe、原始字节/SQLite 只读副本与独立对账；**没有**把 Owner 的 `checks.json`/`summary.json` 状态文字当作判定。Owner 的 launcher/watchdog 仅作为“启动真实容器”的被执行对象；账本配对、摘要核对、重放、模块来源、OS 攻击与回归均为自建。
4. 运行环境：宿主 Python `/root/.local/bin/python3.11`（3.11.15）；Node `v22.23.2`；Podman 固定 rootfs `25491e45…`，`--network none`。G3-D 冻结 stage `e1ff1449…/644823d4…` 未加载、未修改。所有容器运行前后 `rootfs/deps/stage` canonical 未漂移；结束时 `podman ps -a` 为空。
5. 0 真实 Key / 0 真实模型 / 0 外部 HTTP/TCP / 0 `podman pull` / 0 Live；未读取或输出真实 Secret、用户 Session、宿主敏感目录。
6. 唯一允许的写入已遵守：`docs/REVIEW_G4_INDEPENDENT.md` 与 `artifacts/reviewer-g4/`。本报告**不是** Live 授权，**不是** E5-PreLive Full，**不是** G4-H/G5/G6 批准。

---

## 1. 结论（唯一裁定）

```text
PASS_FOR_G4_NO_KEY_PRELIVE_ENGINEERING_SCOPE
```

范围限定：**仅限本机冻结环境、无 Key、无真实 Provider、固定 rootfs、合成账本与已披露残余风险**。该裁定表示：

- G4-A/B/C/D 的无 Key 工程、隔离、合成账本、授权/发送校验与 E5 无 Key 子集，已由独立 Reviewer 复跑/复核；
- 未发现 P0，未发现 P1；
- 仍存在已披露的 UNVERIFIED / PARTIAL / human-required 项（§9、§10），不得合并为“G4 Full / E5 Full / 可 Live”。

固定状态常量（复核后不变）：

```text
G4-H          = NOT_AUTHORIZED
G5            = BLOCKED
G6            = NOT_RUN
LiveGate      = BLOCKED
M0            = DECISION_PENDING
E5_PRELIVE_FULL = BLOCKED_PENDING_HUMAN_DEPLOYMENT
```

---

## 2. 环境、冻结身份与工作树

| 对象 | 期望 | 复核实测 | 结果 |
|---|---|---|---|
| HEAD（复核开始/结束） | `8e5ca7a` | `8e5ca7a68210fed3368c45757779abf1de1be318` | 一致 |
| base | `017c747` | `017c747631cae1e7788014c4ef9e6056c141fecd` | 一致 |
| impl | `a6f3e0a` | `a6f3e0a27a516534803a1e3549dc60fbd107583c` | 一致 |
| code | `d3d429c` | `d3d429cf9d0cb1e9dbc68317928631db413be309` | 一致 |
| docs | `git log -1 -- docs` | `8e5ca7a`（subject: correct G4-E packet file count） | 一致 |
| 最后 src 提交 | `d8a8dc8` | `d8a8dc8`；`git diff d3d429c..HEAD -- src` 为空 | 一致 |
| 工作树 | clean | `git status --porcelain` 空 | 一致 |
| G4 stage | `9c9ce313…` / manifest `85353018…` | 重算一致 | 一致 |
| G3-D stage | `e1ff1449…` / `644823d4…` | 重算一致，未加载 | 一致 |
| rootfs / deps | `25491e45…` / `e07729d7…` | 全部容器运行前后重算一致 | 一致 |
| DSH runtime | `1cc41d5a…` / `0.2.2-rc.2` | runtime binary sha 一致 | 一致 |
| Node / adapter | `v22.23.2` / `2cb42461…` | rootfs node 一致；built JS 一致 | 一致 |

命令/证据：`artifacts/reviewer-g4/r0-identity/git-identity.log`、`canonical-components.log`、`r8-regressions/final-state.log`。

最终状态：`podman ps -a` 空；`.env` 不存在；key-like 环境变量名 0；rootfs/deps/G4 stage/G3-D stage canonical 全部等于冻结值；HEAD 未变。

---

## 3. R0 — 身份、Packet、Stage 加载、旧 Stage fail-closed

### 3.1 Git diff 与 Packet 变更面

- `git diff --binary 017c747..a6f3e0a` 与 Packet `changes/implementation.diff` **61/61 文件逐字节相等**（无 sanitization 差异）。
- Packet `changes/docs.diff` 13 文件与 `git diff 017c747..8e5ca7a -- docs` 对比：仅为绝对路径脱敏（`<WORKSPACE>`、`<HOST_PYTHON>`、`<HOST_HOME>`、`<G4B_WORKTREE>`、`<CONDA_PYTHON>`）；反向替换后 **逐字节相等**。其中 4 个 docs 文件是 impl 之后的 G4-E 文档提交（`M0_G4_IMPLEMENTATION_REPORT` 等），属于 docs_sha `8e5ca7a` 的预期范围。
- 受保护文件（`AGENTS.md`、`SECURITY.md`、`docs/SECURITY_APPROVALS.md`、`run_live.sh`、`gates.py`、`dsh_adapter.py`、`cli.py`、`scripts/g3d/launch.py`、`scripts/g3d/build_stage.py`、G3-D 测试）base/impl/HEAD blob 完全相同；`git diff --name-only 017c747..a6f3e0a -- <protected>` 为空。
- `source_blobs` 41/41：磁盘 sha256 = `git show a6f3e0a:path` = Packet `source/<path>` sha256。
- 证据：`r0-identity/git-identity.log`。

### 3.2 Packet 完整性（独立重算，非引用 integrity report）

| 项 | 实测 |
|---|---|
| `sha256sum -c hashes.sha256` | **209/209 OK，rc=0** |
| Packet 文件数 | **211**（208 payload + `manifest.json` + `packet-integrity-report.txt`；`hashes.sha256` 自身不计） |
| payload tree（按 relpath 排序，排除 manifest.json） | **`70101edbe56e7d384c3858ee1e75f7516573f0106a8c7831d85de8a768901a27`**，与 manifest 一致 |
| symlink | 0 |
| SQLite 打开方式 | 只复制到 `/tmp` 只读打开；Packet/冻结证据中的 DB 未被原地打开 |
| 真实 Key / 用户 Session / 宿主 home | 0（`/root/.config`、`/root/.dsh`、`/root/Autonomous Teacher` 路径命中 0；`sk-` 0） |
| 已知伪阳性 | `DEEPSEEK_API_KEY=SENTINEL` 为测试符号常量，7 个文件命中属预期；无字面凭据 |

证据：`r0-identity/packet-hashcheck.log`、`packet-tree-and-secret-scan.log`。
**注意**：我第一次用“整行排序”重算 tree 得到不同值；按 manifest 声明的 relpath 排序后一致。这是我的脚本方法错误，不是 Packet 错误，已保留更正后的结果。

### 3.3 实际加载模块（真实 rootfs，非只列 Stage 文件）

在固定 rootfs 内以 `--network none --read-only --cap-drop ALL` 运行自建 Probe，挂载 G4 stage `trusted/` 到 `/project`、deps 到 `/deps`：

- `inspect.getfile` **17/17** 均指向 `/project/src/...`；
- 每个模块文件 sha256 == Packet `actual_loaded_modules` == `git show d3d429c:src/...`；
- `all_from_project_src=true`；G3-C 旧标记（`attempts.py 33017e75…`、stage tree `fcdb0de4…`）0 命中；
- Stage `trusted/src` 的 49 个 `.py` 文件与 `git show d3d429c:src` **49/49 字节相等**，与 HEAD 也相等。

证据：`r0-identity/module-probe.json`、`stage-src-vs-git.log`。

### 3.4 旧 Stage / 篡改 Stage fail-closed

| 尝试 | 结果 |
|---|---|
| 用 G3-C 旧 stage `fcdb0de4…`（无 manifest）验证 | `G4Error: stage manifest unreadable`，exit 4；真实 launcher 预检 exit 7，未创建容器 |
| 复制 G4 stage 到 `/tmp`，把 `trusted/src/.../attempts.py` 换成旧 `33017e75…`（mode 保持 0444） | 验证失败：`trusted:sha_mismatch`、`trusted:bytes_mismatch`、`trusted:tree_sha_mismatch` |
| 用该篡改 stage 启动真实 launcher | preflight exit **2**（`PREFLIGHT_IDENTITY`），未创建容器，`podman ps -a` 空 |

证据：`r0-identity/old-stage-validation.log`、`old-stage-run/`、`tampered-stage-run/`。
未复现 G3-C 的“stage 旧代码错位”。

### 3.5 旧 G3-C/G3-D Packet/Review 未改

- `docs/REVIEW_G3D_INDEPENDENT.md` sha256 = `a16dd453…`，等于 G4 Packet `previous_review.report_sha256`；
- G3-D Packet `hashes.sha256` 复核 **rc=0**；G3-D/G3-C Packet manifest mtime 均早于 G4 冻结点；
- `docs/REVIEW_G3C_INDEPENDENT*.md` 受 git 跟踪且工作树 clean；G3-C/G3-D 证据无 G4 后新文件。

证据：`r0-identity/old-artifacts-immutability.log`。

---

## 4. R1 — 静态复验

| 检查 | 结果 |
|---|---|
| `gates.py` 恒 BLOCKED | `LiveGate.inspect` 无条件加入 `EXTERNAL_HUMAN_AUTHORIZATION_BOUNDARY_NOT_DEPLOYED`，返回值字面量 `"BLOCKED"`；无 `authorize()`/`approve()` |
| `run_live.sh` exit 3 | 字节与 base/impl/HEAD 相同；实测 exit 3 |
| `dsh_adapter.py` 四个 live 入口 | `run/resume/_new_harness/_require_live_authorization` 均先抛 `SECURITY_BLOCKED`；`run()` 首行即 require |
| `cli.py --live` | 先 `LiveGate.require_live()`，再返回 3；无 SDK/目录/审批文件读取 |
| `authorization.py` | strict JSON（重复 key/NaN/Infinity/未知字段/bool/float）、外部可信文件 `O_NOFOLLOW`+`fstat`、5 个绑定根、`budget_drift`、单次消费 `O_CREAT|O_EXCL|O_NOFOLLOW`；`billable_send_authorized` 构造 True 即 `ValueError` |
| `ed25519.py` | 非 bytes/长度/非 canonical/小阶/torsion/mixed-order/`S>=L` 全部 `False`，无 traceback；验证只处理公钥 |
| `egress.py` | `TrustedSendAuthorization` 无 `from_mapping/from_json`；`TrustedSendGate.consume` 只接受本进程 `authorize()` 生成对象的**对象身份**；默认 `real_provider` 契约 `send_problems` 恒非空；无第二网络 Transport |
| `watchdog.py` | `/proc` 与 `lstat` absence 语义；`rm -f` rc 不作为 absence；podman 查询失败抛 `WatchdogViolation` |
| `controller.py dispatch_gate=None` | diff 为纯增量：仅多 `send_authorization=None` 与 `if gate is not None`；G3-C/D 默认路径不变；门开启时唯一发送链为 `authorize → transport.dispatch → provider 回调内 consume → Fake` |
| 第二条 provider 路径 / 可开 Live 的 env/flag/JSON | `security/`+`bridge/` 中唯一 env 读取是 `G3B_TEST_MODE=1`+`G3B_CRASH_HOOK` 的测试崩溃钩子（只会 fail-closed，不能开 Live）；`src/` 无 `requests/httpx/urllib/http.client/AF_INET` 网络客户端 |

证据：`r1-static/entrypoint-bytes.log`、`gate-introspection.log`。

---

## 5. R2 — 自建 Auth fuzz（自建 Fixture，不复用 Owner 测试）

自建 `r2_auth_fuzz.py`：独立镜像 repo 的 15 组件闭包、独立 TEST_ONLY 种子、独立签名/变异/调用；**58 个 case，0 失败**。

覆盖与结果：

- 合法合成签名：`approved=True`、`signature_valid=True`，但 `billable_send_authorized=False`；
- 失效签名、未注册 key、轮换后旧 key、算法改成 rsa、签名被篡改：全部 deny；
- Ed25519：identity、order-2、order-4、两个 order-8、`B+T` mixed-order、非 canonical `y>=Q`、`S=L`、`S>L`、短/长/非 bytes 签名：全部 `False`；
- 严格 JSON：顶层/嵌套重复 key、NaN、Infinity、Markdown、未知顶层字段、float/bool 限额、数字字符串、未知 route/model、额外/空工具、预算越界、deadline 越界：全部 deny；
- 时间/撤销：过期、not-before、revoked、runtime SHA mismatch、observed drift：全部 deny；
- 可信文件：repo 内文件、symlink、group-writable、candidate uid 拥有文件/目录：全部 deny；
- 单次消费：第一次成功；同 epoch 重放 `AUTHORIZATION_REPLAYED`；跨 epoch `AUTHORIZATION_EPOCH_MISMATCH`；
- 计数器：58 个 case 中 `billable_send_authorized` 全部 False；无异常 traceback。

证据：`r2-auth/r2-results.json`、`r2-run.log`。
种子泄漏：Candidate stage、rootfs、deps 中均无 seed 的原始字节/十六进制；但 **Packet `source/tests` 与 `changes/implementation.diff` 含 `TEST_ONLY_SEED = bytes.fromhex("5a"*32)` 的可重建推导**（见 P2-1）。

---

## 6. R3 — 真实 Candidate UID/Mount 攻击（L2-OS）

在真实双主体 hold run 中，以真实 Candidate 命名空间执行自建 Probe：

| 观察 | 实测 |
|---|---|
| uid/gid | Candidate 容器内 `uid=0`（uid_map `0 65534 1`），gid_map `0 65534 1` + `2000 2000 1` |
| capabilities | `CapEff/CapPrm/CapBnd=0`，`NoNewPrivs=1`，`Seccomp=2` |
| mount | `/project` ro、`/deps` ro、`/work/g3b` ro、`/work/session` rw、`/` ro；`/work/state` 不存在 |
| 可信状态读取 | `/work/state/{attempts.sqlite3,broker.sqlite3,g4c-policy.json,controller.json,authorization.json,trusted-keys.json,revocations.json,bridge.sock,broker.sock}` 全部 **ENOENT** |
| 可信状态写入 | `/work/state/*` ENOENT；`/project/*` **EROFS**；`/work/g3b/bridge.sock` **ENXIO** |
| 旧 G3-B 四类 | 读 DB/写 DB/写 Policy/直连 Broker 路径均不可达（ENOENT/EROFS）；候选只能写自己的 `/work/session` |
| 协议直连 | 垃圾帧/空行 `REQUEST_INVALID`；未批准工具 `ADMISSION_TOOL_SCHEMA_MISMATCH`；错 model `ROUTE_MISMATCH`；额外工具 `ADMISSION_TOOL_SCHEMA_MISMATCH`；self-auth `UNKNOWN_FIELD`；超大 token `BAD_TYPE` —— 均无 attempt/receipt |
| 网络 | `AF_INET` connect/bind/udp 全部 **EACCES**，DNS 失败 |
| 同 UID 已知路径（宿主 uid 65534） | 当前 run 与旧 run 的 `state` DB/policy/controller/receipt、socket、目录列出全部 **EACCES**；`/tmp` 下 root 0700 trusted fixture 亦 EACCES |
| socket | mode `0660 root:2000`；Candidate 通过 `--group-add 2000` 可连接，协议层按 UID 校验并接受/拒绝 |
| 账本 | 攻击前后 `g3b_attempts=0`、`budget_reservations=0`、无 Fake counter |

证据：`r3-os/r3-hold-report.json`、`candidate-probe.raw.txt`、`host-uid-probe.raw.txt`、`hold-run/mountinfo/*`、`socket-stat`。
**未主张**已有 per-run OS 身份：拒绝依赖 mount namespace + root 0700 DAC；P2-RUN-IDENTITY 仍待人类决策。

---

## 7. R4 — 真实 DSH 两轮账本复验（L2-REAL-DSH）

在固定 rootfs、`--network none`、G4 双主体、冻结 stage 下独立运行：

| run | 结果 | 账本 |
|---|---|---|
| c01 Echo | launcher exit 0 | 1 Reservation / 1 Claim / 1 Attempt `SETTLED` / 1 Receipt / 1 Settlement；Fake=1 |
| c02 Tool 两轮 | launcher exit 0 | 2 Reservation / 2 Claim / 2 Attempt `SETTLED` / 2 Receipt / 2 Settlement；Fake=2 |

自建 `r4_ledger_audit.py` 只读复制 SQLite，独立解析（不信任 `checks.json`）：

```text
c01 call-5abe9190…  prepared == claim, payload == receipt, receipt_id/length/reservation match
c02 call-0cb62b73…  prepared 6da31263… == claim 6da31263…；payload 0d3c65b7… == receipt 0d3c65b7…
c02 call-4cb9079a…  prepared d88f6844… == claim d88f6844…；payload 9987b957… == receipt 9987b957…
两个 call_id 不同；两套账本独立；两个 Prepared/Payload 摘要对分别映射
```

DSH 原始 session trace（candidate-session 的 `session.v4.jsonl`）：step [1,2]、2 个 assistant usage、1 个 `tool/call`、`tool/result` 在 step 2 之前；与 2 个 Receipt/Fake=2 一致；额外 provider 请求 0。
**限制**：冻结 Fake 只记录 payload 的 `raw_sha256/length`，不保存原始 payload 字节，因此“第二个请求正文包含第一轮 skill_lookup 结果”只能由 DSH trace 顺序（tool result 后才有 step 2 的 provider 调用）与 DSH 会话状态证明，不能做 payload 字节级包含证明；标为 L2 语义证据，非字节级。

**真实重放**（自建 hold-run Probe，raw UDS，同一业务身份两次）：
第一次 `ack+chunks+finish`；第二次 `ack+error ATTEMPT_ALREADY_STARTED`；尝试数=1、身份=1、intent=1、receipt=1、Fake=1、attempt `SETTLED`；**无第二次发送**。
Durable replay 另以真实 run DB 副本调用 `claim_request_identity`/`begin_attempt`/`record_intent`，均 `ATTEMPT_ALREADY_STARTED`，行数不变。

**Session Resume L2**：未运行新的 DSH resume 会话语义（G4-C 无真实 resume case）；只验证了 durable identity/replay 层与真实重放。标 `UNVERIFIED`（见 §10）。

证据：`r4-dsh/c01-audit.json`、`c02-audit.json`、`c02-tool-pass/traces/dsh-result.json`、`replay/replay-report.json`。

---

## 8. R5 — 故障、账本保守性与清理

| 场景 | 实测 |
|---|---|
| Broker SIGKILL（`--steps kill-broker,valid`） | `BROKER_ERROR`；Fake=0；Attempt=0；Reservation=0；无 gate authorization |
| Trusted crash：发送前（`after_attempt_start_before_fake_send`） | 1 Attempt `SETTLEMENT_UNCERTAIN`（reason `NO_RECEIPT_AFTER_CRASH`），0 Receipt，Fake=0；Reservation `PENDING`，`reserved_cost=0.001619`；recovery start exit 3（`ADMISSION_REPLAYED`），replay 被拒，未重发 |
| Trusted crash：Fake 收据后（`after_fake_receive_before_response`） | 1 Attempt `SETTLED`，1 Receipt，1 结算（cost `0.001022`），Fake=1；无双重结算 |
| 外部 Watchdog kill（D01） | 24/24 checks PASS；target exit `-15`；2 容器 remove 后 `podman ps -a` 空；inspect rc=125；3 个 PID `/proc` 不存在；socket/run-dir/rootfs target `lstat` 不存在；run-dir 14 files/9 dirs 被删除并复查；`pending.json` = `PENDING_CONSERVATIVE`、`retry_allowed=false` |
| DB Fee=0 / FREE / 双发送 | 未发现：无 `FREE` 状态；已结算 reservation cost > 0；崩溃前无 Receipt；崩溃后仅 1 Receipt；所有未完成状态为 PENDING/UNCERTAIN |

说明：D01 触发原因是 `WATCHDOG_DEADLINE_AFTER_UP`（`--kill-after-up 4` 的 bounded 触发），不是产品失败；checks 全部通过。
证据：`r5-faults/broker-down/`、`crash-before-send/`、`crash-after-receive/`、`watchdog/watchdog-evidence/watchdog.json`、`pending.json`。

---

## 9. R6 — 入口负例与 E5 两列

### 9.1 Live 入口（独立执行）

| 入口 | 结果 |
|---|---|
| `LiveGate.inspect(live_requested=True, actual=reviewed, tools={"skill_lookup"}, log_disabled=True)` | **`status=BLOCKED`**，只剩 `EXTERNAL_HUMAN_AUTHORIZATION_BOUNDARY_NOT_DEPLOYED` |
| `LiveGate.require_live(...)` | `SecurityBlocked` / `SECURITY_BLOCKED` |
| `/bin/sh scripts/run_live.sh` + 全部注入 env | exit **3**，stderr `BLOCKED SECURITY_BLOCKED` |
| CLI `smoke --live` + 注入 `AT_M0_LIVE_APPROVED/ALLOW_LIVE/APPROVAL/APPROVAL_MD/DEEPSEEK_API_KEY` | exit **3**，JSON `BLOCKED/SECURITY_BLOCKED` |
| Adapter `run/resume/_new_harness/_require` | 全部 `RuntimeFailure:SECURITY_BLOCKED` |
| Repo 内 Markdown 批准 | `authorization must live outside the repository`，`approved=false`，`billable=false` |
| repo 内自签 JSON | 同上 deny |
| socket audit（四个入口） | 0 个 `socket.connect/getaddrinfo/urllib` 事件 |
| 静态网络客户端 | `src/` 仅 `AF_UNIX` IPC；无 `AF_INET`/HTTP client |

证据：`r6-negatives/r6-results.json`、`r6-run.log`。

### 9.2 E5-P01..P05 两列复核

| Gate | NO_KEY_SUBSET | FULL_STATUS | Reviewer 依据 |
|---|---|---|---|
| E5-P01 | **PASS** | `BLOCKED_PENDING_HUMAN_DEPLOYMENT` | R2 合成签名 + 5 绑定根；漂移 deny；外部人类签名未部署 |
| E5-P02 | **PASS** | `BLOCKED_PENDING_HUMAN_DEPLOYMENT` | R2 runtime SHA/闭包漂移；stage tamper fail-closed；部署后不可写未证 |
| E5-P03 | **PASS** | `BLOCKED_PENDING_HUMAN_DEPLOYMENT` | R6 Markdown/env/flag/self-sign 均不能开 gate；正式审批未上线 |
| E5-P04 | **UNVERIFIED** | `BLOCKED_PENDING_HUMAN_DEPLOYMENT` | 无可导出 merged registry；未知动态 tools 不可枚举（B03/D13） |
| E5-P05 | **PASS** | `BLOCKED_PENDING_HUMAN_DEPLOYMENT` | R3 无 Key/哨兵命中、无网络；D01 清理；真实 Key/TLS/账单未证 |

`E5_PRELIVE_FULL` 固定为 `BLOCKED_PENDING_HUMAN_DEPLOYMENT`；任何 subset PASS 不得写成 Full PASS。

---

## 10. R7 — 证据分级与未验证项

| 级别 | 本轮 Reviewer 实际证据 |
|---|---|
| L2-REAL-DSH | R4 c01/c02 真实双主体 + 真实 DSH + Fake；R4 replay；R5 broker/crash |
| L2-OS | R3 真实 Candidate UID/mount；host uid 65534 已知路径；D01 外部 kill/absence；OCI 957/0/24/34 |
| L1-HOST | R2 58-case auth fuzz；R6 入口负例；durable replay；host full；Node guard/skill；Ruff |
| L1-STATIC | git diff/protected files/source blobs；entrypoint 字节；权限/Watchdog 静态 |
| L1-PACKET | 209/209、payload tree、0 symlink、manifest/API |
| UNVERIFIED | B03 merged registry；B07 session-title 辅助调用；E5-P04；G4-C C16 DSH resume L2；Node adapter 9/9 |
| HUMAN-REQUIRED | G4-H-01..06；E5 Full；真实 Key/Provider/TLS/账单/硬额度；P2-DISK/USERNS/RUN-IDENTITY |

**未验证项（明确列出）**

1. **DSH Session Resume 的 L2 连续性**：未跑真实 resume 会话；只证明 durable identity 拒绝旧业务身份 + 真实 raw-UDS 重放不发送。G4-C16 仍 PARTIAL。
2. **B03 merged DSH tool registry**：DSH 0.2.2-rc.2 无权威导出 API；仅 Controller per-dispatch 白名单兜底。
3. **B07 session-title**：未禁用；本轮 0 额外请求，但不能证明任意未来会话不会产生辅助调用。
4. **E5-P04**：同上，无 merged registry。
5. **Node adapter 9/9**：Reviewer 未重跑（测试硬编码 `/probe` 容器布局）；guard/skill 27/27 已重跑。
6. **OCI raw 27-failure 精确复现**：我的 raw run 使用世界可读的 repo 副本，含 root-only 测试，得到 1078 passed/181 env failures/26 skipped；按冻结 stage 契约规范化后 filtered 精确得到 957/24/34/0。Owner 的 raw 1008/27 选择集与我的 raw 选择集不同，不能把 27 当作唯一环境计数。

---

## 11. R8 — 回归、Node、Ruff 与终态

### 11.1 Host full（宿主真实产品代码）

```text
PYTHONPATH=src:artifacts/foundation/deps /root/.local/bin/python3.11 -B \
  -m pytest tests -q -p no:cacheprovider
→ 1285 collected：1280 passed / 4 failed / 1 skipped（exit 1）
```

四项失败逐项独立归因：

| 测试 | 归因 | 复核 |
|---|---|---|
| `g3d::test_runner_does_not_modify_product_src` | frozen-src 断言：`git diff 4bd4803 -- src` 有 6 个 G4-A/C 授权改动 | 预期失败，不改历史测试 |
| `g4_d::test_d15_same_uid_known_path...` | 宿主 3.11 解释器在 0700 home 下，降权后不可穿越 | 用 `/opt/miniconda3/envs/quant/bin/python` 重跑 **1 passed** |
| `runtime::test_target_profile_static...` | host checkout 0644 vs OCI stage 0444 | OCI filtered 中通过 |
| `sandbox::test_all_live_entrypoints_remain_blocked` | 子进程硬编码 `/project/src:/deps` | OCI filtered 中通过；独立 LiveGate probe exit 3 |

### 11.2 固定 OCI

| 运行 | 结果 |
|---|---|
| raw（uid 65534，世界可读副本，无 artifacts fixture，0644 mode） | 1078 passed / 181 failed / 26 skipped；181 全为环境类（root-only trusted dir、git/tar//bin/sh/bash 缺失、缺 `/project/artifacts` fixture、0644 mode） |
| **filtered（按冻结 stage 契约规范化副本 + 31 个环境 deselect）** | **957 passed / 24 skipped / 34 deselected / 0 failed，exit 0** |
| Root replay（Owner 声明 294/0/2） | Reviewer 未单独重跑 294 项；g4_a/unit auth 由 host 223 项 + OCI raw 分类覆盖 |

规范化内容：副本 `config/dsh/*.yml`、`target-broker-policy.json`、`verify_runtime_profile.py` 设为 0444；`artifacts/foundation/deps -> /deps` 只读 symlink；未改任何产品字节（与 repo 逐文件 sha256 相等）。

**证据卫生发现**：Owner 的 `oci-env-deselects.json` 只列 30 个 node id，但声称 34 deselect；其中 `test_digest_sidecar_contract` 未列，却必须 deselect（rootfs 无 git）才能得到 0 failed。我的 filtered run 显式加入该项后得到 957/24/34。这是 P2 证据记账问题，不是产品失败。

### 11.3 Node

| 套件 | 结果 |
|---|---|
| guard `guard-pr1.test.mjs` + `precheck.test.mjs` | **19 pass / 0 fail**（host，`RBG_TEST_PYTHON=/root/.local/bin/python3.11`；容器固定路径 `/opt/python/...` 在宿主不存在） |
| skill `plugin.test.mjs` | **8 pass / 0 fail** |
| adapter `adapter-signal.test.mjs` | **未重跑（UNVERIFIED）**；硬编码 `/probe/lib/index.js` 容器布局 |

### 11.4 Ruff 0.17.5

- scoped（`src/autoteacher_m0` + G4 tests + `scripts/g4`）：**All checks passed!**（exit 0）
- repo-wide：**37 findings**（绝大多数 `spikes/`；`src/tests` 0），与 Owner 一致；不属 G4 范围。

### 11.5 终态

- HEAD `8e5ca7a` 未变；`git status --porcelain` 空；rootfs/deps/G4 stage/G3-D stage canonical；
- `podman ps -a` 空；无 `.env`；key-like env 名 0；未执行 `podman pull`；
- 报告与证据只落在允许路径；未 commit/push。

证据：`r8-regressions/final-state.log`、`host/host-full.log`、`oci-filtered3/`、`node/`、`ruff.log`。

---

## 12. P0 / P1 / P2

### P0（权限绕过 / 可计费出站 / Key 泄漏 / 未授权 Fake / 账本 FREE / 双发送）

**0 项。**

逐个 P0 类别的证伪尝试：

1. **真实 Key/网络路径**：`src/` 无 HTTP client/AF_INET；R6 socket audit 0 事件；R3 Candidate AF_INET EACCES；repo `.env` 不存在、key-like env 0；Packet `sk-` 0；未运行真实 Provider。
2. **LiveGate 放行**：最强诊断证据（`live_requested=True`、baseline 相等、`skill_lookup`、log disabled）仍 `BLOCKED`；CLI/script/Adapter/Markdown/self-sign/env 全失败；字节未改。
3. **Candidate 读写可信状态**：真实 Candidate 容器 `/work/state` ENOENT、`/project` EROFS、socket ENXIO；同 host uid 65534 对真实已知 run 路径 EACCES；攻击前后账本 0/0。
4. **未授权/重复 Fake**：broker-down Fake=0/Attempt=0；真实重放第二次 `ATTEMPT_ALREADY_STARTED`、Fake 仍 1；非法协议请求全部 error。
5. **假结算/FREE/双发送**：崩溃前 Attempt `SETTLEMENT_UNCERTAIN`、0 Receipt、Reservation `PENDING`；崩溃后仅 1 Receipt/1 SETTLED；无 FREE；Watchdog kill 后 0 attempt；所有已结算 cost > 0。

### P1（关键部署契约不一致 / 凭据边界失效 / 结算恢复错误 / 核心主张缺动态证据）

**0 项。**
未发现：受保护入口变更、gate 语义绕过、Candidate 可写、Packet 哈希不符、真实 DSH 账本错配、崩溃后重发、watchdog 失效继续运行。

### P2（不影响本轮限定范围的证据/运维卫生）

| ID | 内容 | 影响/处置 |
|---|---|---|
| P2-1 | Packet `source/tests` 与 `changes/implementation.diff` 含 `TEST_ONLY_SEED = bytes.fromhex("5a"*32)` 的可重建推导（合成测试种子） | 非真实私钥、未注册到任何部署信任根、Candidate/rootfs/deps 均无 seed 原始字节；不能开 LiveGate。仍建议未来 Packet 只保留该 fixture 的 hash，不复制可重建种子的测试源码 |
| P2-2 | Owner `oci-env-deselects.json` 列 30 个 id 但声称 34；漏列 `test_digest_sidecar_contract` | Reviewer 显式加入后得到 957/24/34/0；证据记账修正，不是产品断言失败 |
| P2-3 | `G3B_TEST_MODE`/`G3B_CRASH_HOOK` 测试崩溃钩子仍在产品 controller 中 | 仅 launcher 可信 env 可触发，结果是 `os._exit`/fail-closed；不构成开 Live 或发送路径；建议 G4-H 评估是否移除 |
| P2-4 | P2-RUN-IDENTITY：同 UID 拒绝依赖 mount namespace + root 0700，不是 per-run OS 身份 | 本轮如实证明现状；人类须签收或加 per-run capability/UID |
| P2-5 | `TrustedSendGate.snapshot().worst_case_held_usd` 恒为 0（`_held_usd` 未被累加） | synthetic 路径预算仍由 known cost + hard cap 检查；不影响本轮 0-Live；真实路由前应补齐 held 语义 |
| P2-6 | G4-C 无真实 DSH resume L2；C16 仍 PARTIAL | 已在 E5/C16 披露；durable replay 层已验证；建议 G4-H/G5 前补一次真实 resume |
| P2-7 | Packet `reviewer=NOT_ASSIGNED` / `reviewer_status=PENDING_INDEPENDENT_REVIEW` | 冻结时预期；归档时应记录本报告 verdict，不修改冻结 Packet |
| P2-8 | OCI raw 精确 27 failure 未复现（我的 raw 选择集/副本不同，得 181 env failures） | 不隐藏；filtered 957/24/34/0 与 Owner 数字一致；raw 差异全部为环境类别 |

---

## 13. Packet Manifest / API 复核（独立取值）

| 字段 | 值 | 核对 |
|---|---|---|
| `schema_version` | `m0.g4.review-packet.v1` | OK |
| `base_sha` | `017c747…` | OK |
| `impl_sha` | `a6f3e0a…` | OK |
| `code_impl_sha` | `d3d429c…` | OK |
| `docs_sha` / `build_sha` | `8e5ca7a…` | = `git log -1 -- docs` |
| `head_at_packet` | `8e5ca7a…` | = 当前 HEAD |
| `stage_manifest_sha256` / `stage_tree_sha256` | `85353018…` / `9c9ce313…` | 重算一致 |
| `g3d_stage_manifest_sha256` / `tree` | `644823d4…` / `e1ff1449…` | 重算一致 |
| `rootfs_sha256` / `deps_sha256` | `25491e45…` / `e07729d7…` | 重算一致 |
| `runtime_sha` / version | `1cc41d5a…` / `0.2.2-rc.2` | runtime binary sha 一致 |
| `adapter_built_js_sha256` | `2cb42461…` | built JS 一致 |
| `actual_loaded_modules` | 17 个，全部 `/project/src` | 真实容器 `inspect.getfile` 17/17 一致 |
| `source_blobs` | 41 | 磁盘/git/Packet 三方一致 |
| `provider_route_kind` | `synthetic_only` | 一致 |
| `real_model_calls` / `real_external_http_calls` | 0 / 0 | 我的 socket audit/容器网络证据一致 |
| `provider_keys_seen` / `key_present` | 0 / false | 一致 |
| `live_gate` / `run_live_exit` | `BLOCKED` / 3 | 实测一致 |
| `e5` | P04 subset UNVERIFIED；五项 full BLOCKED | 一致 |
| `case_statuses` / `matrix` | 85 行；62/10/2/5/6 | 一致 |
| `g4h_status` / `g5` / `g6` / `m0` | NOT_AUTHORIZED / BLOCKED / NOT_RUN / DECISION_PENDING | 一致 |

Packet 的 `packet_payload_tree_sha256=70101edb…` 在按声明方法（relpath 排序）重算后一致；`sha256sum -c` 209/209。

---

## 14. Reviewer 对矩阵 E06..E10 的填写（不修改 CSV）

| case | 期望 | Reviewer 实际 | 状态 | 证据 |
|---|---|---|---|---|
| G4-E-06 | Reviewer self-authored findings and run logs | 58 个自建 auth case；真实 Candidate 7 类协议攻击；真实 DSH c01/c02；真实 replay；broker/crash/watchdog；全部原始日志在 `artifacts/reviewer-g4/` | **PASS** | `r2-auth/`、`r3-os/`、`r4-dsh/`、`r5-faults/`、`r6-negatives/` |
| G4-E-07 | Reviewer probes and read-only ledger reconciliation | SQLite 复制到 `/tmp` 只读解析；c01 1 套、c02 2 套；两对摘要逐项；Fake counter/DSH trace 一致 | **PASS** | `r4-dsh/*-audit.json` |
| G4-E-08 | No fake FREE or extra dispatch | 无 FREE；崩溃前 PENDING/UNCERTAIN；崩溃后单次结算；重放不增 Fake；broker-down 0 发送 | **PASS** | `r5-faults/`、`r4-dsh/replay/` |
| G4-E-09 | All live paths BLOCKED and no real key | LiveGate/CLI/run_live/Adapter 全 BLOCKED；0 Key/0 外网/0 真实模型 | **PASS** | `r6-negatives/`、`r0-identity/` |
| G4-E-10 | Signed-off no-key verdict; P0/P1/Risks | 本报告；P0=0、P1=0、P2=8 | **PASS** | 本文件 |

（CSV 本身未改；Lead/归档方若需把上述状态写入矩阵，应由 Lead 在授权范围内完成。）

---

## 15. 残余风险与 human-required

1. **真实人类信任根/Key/Provider/TLS/DNS/账单/供应商硬额度**：全部未部署、未验证；E5 Full 仍 `BLOCKED_PENDING_HUMAN_DEPLOYMENT`。
2. **G4-H-01..06**：全部 `BLOCKED / NOT_AUTHORIZED`；`G5=BLOCKED`、`G6=NOT_RUN`、`M0=DECISION_PENDING`。
3. **P2-DISK / P2-USERNS / P2-RUN-IDENTITY**：仍待维护者签收；本报告不构成签收。
4. **B03/B07/E5-P04/C16**：如上 UNVERIFIED/PARTIAL。
5. **P2-1 测试种子**：合成、不可用于部署；建议归档前清理 Packet 中可重建种子的测试源码，或明确标注 TEST_ONLY。
6. **P2-3 测试崩溃钩子**：建议 G4-H 评估移除或改为仅测试构建。
7. **OCI raw 与 Owner 精确计数差异**：已披露；filtered 数字一致。

---

## 16. STOP

本报告给出且仅给出：

```text
PASS_FOR_G4_NO_KEY_PRELIVE_ENGINEERING_SCOPE
```

并明确：

```text
G4-H = NOT_AUTHORIZED
G5   = BLOCKED
G6   = NOT_RUN
LiveGate = BLOCKED
M0   = DECISION_PENDING
E5_PRELIVE_FULL = BLOCKED_PENDING_HUMAN_DEPLOYMENT
```

不进入 G4-H/G5/G6；不签发 Live 授权；不把本裁定映射为任何真实 Key、Provider、计费或部署许可。**STOP。**

---

### 附：本报告与证据哈希

- 报告：`docs/REVIEW_G4_INDEPENDENT.md`（sha256 见交付消息）
- 证据索引：`artifacts/reviewer-g4/RUN_INDEX.md`
- 复核窗口：2026-11-18T20:47Z → 2026-11-18T21:41Z
- 环境终态：HEAD `8e5ca7a`；worktree clean；`podman ps -a` 空；rootfs/deps/stage canonical；0 Key/0 外网/0 Live。
