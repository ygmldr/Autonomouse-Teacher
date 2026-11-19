# M0 G4-F — 独立复核归档勘误与残余登记（append-only）

- **文档性质**：G4-F 最终归档的勘误、P2 残余、范围限定与历史状态登记。本文件为 **append-only**：后续如需修订，只在文件末尾追加新小节，不改写既有字节。
- **归档时间**：2026-11-19T16:33Z（UTC）。
- **归档提交**：`docs: archive G4-F independent review (PASS) and final errata (no-key)`。同一提交只包含三个文件：本文件（新增）、`docs/REVIEW_G4F_INDEPENDENT.md`（原字节归档）、`docs/Autonomous_Teacher_M0_G4F_Closeout_Test_Evidence_Matrix_v1.0.csv`（仅 `REV-01..REV-05` 五行）。
- **约束**：0 真实 Key / 0 真实模型 / 0 外网 / 0 Live；未 `podman pull`；未修改实现、测试、脚本、证据、Packet、Stage 或历史 docs 字节；未 amend、未 push。归档动作只写 `docs/` 三个文件。

---

## 1. 归档对象与冻结输入

### 1.1 Reviewer 身份、独立性与窗口

- **Reviewer**：Independent G4-F Reviewer（未署名独立复核 Agent），报告 ID `REVIEW-G4F-INDEPENDENT-20261119T1622Z`。
- **独立性声明**：未参与 G4-F1..F6 的任何实现、测试编写、证据生成、矩阵填写或 Review Packet 构建，也未参与 F1–F5 的代码/测试/脚本编写。关键结论来自 Reviewer 自建 Probe、自跑命令、原始字节、SQLite 只读副本、Receipt、gate journal、dispatch-window JSONL、DSH trace/session JSONL 与独立对账；Owner 的 `summary.json`/`checks.json`/`matrix.json` 未作为裁定输入。
- **复核窗口（UTC）**：`2026-11-19T15:13Z` → `2026-11-19T16:22Z`。
- **工作树**：主工作树 `/root/Autonomous Teacher`，复核前后 HEAD 均为 `0d5e5e09cd607aef6ba39608b8a3b33a0d2c7705`；L2 证据在 `impl e7d9296` 的独立 clean worktree `/root/at-g4f-impl` 中重跑，artifacts 使用 `/tmp/at-g4f-review/artifacts` 固定副本。
- **写入范围**：仅 `docs/REVIEW_G4F_INDEPENDENT.md` 与 gitignored `artifacts/reviewer-g4f/`；Reviewer 未修改矩阵、Packet、Stage、rootfs/deps、历史证据或任何历史 docs，未 commit / amend / push。
- **证据索引**：`artifacts/reviewer-g4f/RUN_INDEX.md`。

### 1.2 冻结输入（Reviewer 独立复算一致）

| 对象 | 冻结值 |
|---|---|
| HEAD / build | `0d5e5e09cd607aef6ba39608b8a3b33a0d2c7705` |
| implementation | `e7d92967ec0ece80de4a1a3705f637e8eb9bde99` |
| code | `dbacb76f98a1a91559ff70e02bf544ace76ed7b5` |
| docs | `d12df4165108d59a2a4f08ba3ba93a35935df846` |
| base | `bb2e9142a4e96e2b8fbe65bb99f1b4c045260251` |
| G4-F Stage | `artifacts/g4/c/stages/stage-20261119T142828Z`；manifest `82e10c6ffe37e401a58730e9abcaa691f19d6702a7276c03df625d5b4636e501`；tree `7d32ec1d8b02726ba52ef8303e8677b46384e9954559e838b31bb8c58f222068`；trusted tree `6d887bbf4c83ee87145bd5e71d97475a2c61cdbe97b101302650eb84cc1b5aec`；candidate tree `2459db9df83b9dedfa68c6c0210f5904f0c11601e57744a3d357c4884a06907c`；`base_sha = head_at_build = e7d9296` |
| rootfs | `25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0` |
| deps | `e07729d7997944417b1c25531749b3e6e5e34aa4248f01dc8f370282082ecb98` |
| DSH runtime | `1cc41d5a8745a5b9d47c8604e44f23eb8af2d8ca02b2afa0be101d5f71be6ea4`；版本 `0.2.2-rc.2` |
| Python / Podman / Node | `3.11.15` / `4.9.3` / `v22.23.2` |

### 1.3 Reviewer 报告

| 项 | 值 |
|---|---|
| 路径 | `docs/REVIEW_G4F_INDEPENDENT.md` |
| 大小 | 34433 B |
| sha256 | `b17977d1ff8506de440996f7bd411149ae968cef6564391b74b28980468ddc4b` |
| 归档方式 | 新文件、**原字节** `git add`；提交前后 sha256 必须保持上述值 |
| 只读约束 | 归档方未修改报告字节；报告本身不是 Live 授权，不是 E5 Full，不是 G4-H/G5/G6 批准 |

### 1.4 Review Packet（只读，未重打包）

- 路径：`artifacts/review-packet-g4f-e7d92967ec0ece80de4a1a3705f637e8eb9bde99/`。
- 归档时复核：**177 files**、**0 symlink**、`sha256sum -c hashes.sha256` **173/173 OK**、manifest payload `files.count = 172`。
- payload tree：当前全量（含 2 个 post-build sidecar）为 `111c1361417ea6ee6958ecffebdb78164f655b082ae8cf911dca221f57794b5a`，manifest 为 `e464b9b1d6ab0bf4406ccc7868863d207f594fa898ee4affaa3e901d9f1caaa0`；剔除 sidecar 后复算恰为 `e464b9b1…`。详见 §4.1（P2-01）。
- `manifest.json`：`docs_sha = d12df41`、`impl_sha = e7d9296`、`code_sha = dbacb76`、`build_sha = head_at_packet = 0d5e5e0`、`provider_route_kind = synthetic_only`、`real_model_calls = 0`、`real_external_http_calls = 0`、`key_present = false`、`live_gate = BLOCKED`。
- **冻结字段**：`reviewer = NOT_ASSIGNED`、`reviewer_status = PENDING_INDEPENDENT_REVIEW` 是 Packet 冻结点的事实快照，不在本归档回写；post-packet verdict 由本 errata、矩阵 `REV-01..05` 与 `artifacts/reviewer-g4f/VERDICT.json` 记录。
- **冻结说明**：Reviewer 报告、本 errata 与矩阵 `REV-01..05` 最终化均为 **post-packet** 产物，不进入 Packet，不触发重打包；详见 §7。

---

## 2. 裁定与范围限定

### 2.1 唯一裁定

```text
PASS_FOR_G4F_NO_KEY_CLOSEOUT_SCOPE
P0 = 0
P1 = 0
P2 = 8
```

- 该裁定仅覆盖 **本机冻结环境、无 Key、无真实 Provider/计费/TLS/Live** 的 G4-F 工程 closeout。
- **不得**合并为 “G4 Full / E5-PreLive Full / 可 Live / 生产安全 / `M0_GO`”。

### 2.2 与裁定同义、不可省略的范围限定

本 PASS 仅限：

1. 固定 rootfs / deps / G4-F Stage / DSH runtime，SHA 见 §1.2；
2. **无真实 Key、无真实 Provider、无外部 HTTP/TCP、无 `podman pull`、无 Live**；
3. 合成账本、Fake Provider 与 synthetic fixture 价格；
4. 已披露的 P2 八项与 UNVERIFIED 项（§4、§5）；
5. 所有容器运行使用 `--network none --read-only --cap-drop ALL --security-opt no-new-privileges`，Candidate 使用 `--uidmap 0:65534:1`。

**不主张、也不得外推为**：

- 内核 / 容器运行时 0day 防护，或宿主 root 被攻陷后的安全；
- 真实人类信任根 / Key Broker / 可信 Egress / 真实 Provider / TLS / DNS / 账单 / 供应商硬额度；
- E5-PreLive Full、G4 Full、G4-H、G5、G6、`M0_GO`、任何 Live 授权或生产部署安全；
- 跨宿主 / 跨内核 / 跨 Runtime / 跨 Stage 的可移植性；
- exactly-once、真实 Invoice 或供应商侧撤销语义。

### 2.3 固定状态常量（归档后不变）

```text
G4-H            = NOT_AUTHORIZED
G5              = BLOCKED
G6              = NOT_RUN
LiveGate        = BLOCKED
M0              = DECISION_PENDING
E5_PRELIVE_FULL = BLOCKED_PENDING_HUMAN_DEPLOYMENT
```

---

## 3. 独立复核摘要（不采信 Owner 结论文字）

| 复核域 | 结果 | 关键事实（Reviewer 独立复算/复跑） |
|---|---|---|
| **R0 身份 / Packet / Stage** | PASS | HEAD/impl/code/docs/base 全部一致；Packet 173/173、177 files/0 symlink；diff 与 Packet 记录在文档化 host-path sanitization 后逐字节相同；protected files 零 diff；18/18 模块 == HEAD blob == stage trusted；旧 G4 / 旧 G3-D / 篡改 stage 均 preflight exit 2 且未启动容器 |
| **R1 静态复验** | PASS | 无 `authorize()`/`approve()`/环境/文件批准入口；`LiveGate.inspect` 恒 `BLOCKED`；`require_live` 抛 `SECURITY_BLOCKED`；`run_live.sh` exit 3；Adapter 四入口先 `SECURITY_BLOCKED`；`cli.py --live` 先 `require_live`；strict JSON / 5 绑定根 / 单次消费 / `real_route` 恒 `BLOCKED`；`src/` 无 HTTP 客户端 |
| **R2 自建 Scanner** | PASS | 31 个正例 / 26 个严格哨兵负例全部符合预期；0 完整 Secret 泄漏；self-test PASS；主工作树全历史 + 工作树 + commit message `473 files/746 blobs/168 commits, findings=0`；变异测试可使检测/掩码测试失败，证明断言非空转 |
| **R3 真实 Candidate OS/raw-UDS** | PASS | 真实 UID 65534、`CapEff=0`、`NoNewPrivs=1`、`--network none`；`/work/state` ENOENT、`/project` EROFS、`bridge.sock` open ENXIO、宿主同 UID EACCES；12 个纯 raw-UDS 负例全部拒绝且 Reservations/Claims/Attempts/Intents/Receipts/Fake 全为 0；随后批准 + replay 为 2/2/2/2、Fake=2，无重复发送 |
| **R4 真实 DSH Echo/Tool/Resume/账本** | PASS | Echo 1/1/1/1/1（Fake=1）；Tool 两轮 2/2/2/2/2（Fake=2）；digest/usage 字段级相等、无额外 provider 请求；真实 resume turn1 1、turn2 累计 2/2/2/2/2，旧 attempt 不变、每 reservation 恰一次 settlement；crash-resume 1 PENDING / 1 UNCERTAIN / 0 receipt / Fake=0 |
| **R5 Revocation/Timeout/In-flight** | PASS | 9/9 真实双 Principal L2 case；无可停止场景误发；已 Reserve 未跨 wire 保持 PENDING/UNCERTAIN/held>0；已跨 wire 按 Broker 终态结算一次；无 `cost=0`、无双发送、无双结算、无第二次 Fake；`containers_after=[]` |
| **R6 LiveGate / Key / Network / E5** | PASS | 全部证据满足仍 `BLOCKED`（`EXTERNAL_HUMAN_AUTHORIZATION_BOUNDARY_NOT_DEPLOYED`）；`run_live`/CLI `--live` exit 3；Adapter 4/4 `SECURITY_BLOCKED`；strace 0 socket/connect；0 `.env`、0 Key-like env、0 真实模型、0 外部 HTTP；E5 两列见 §5 |
| **R7 矩阵 / 证据分级 / 原始解析** | PASS | 46 行独立清点；逐行 evidence path 检查仅 `F2-07` 的 `f6/.../tool-window.json` 缺失（P2-02）；F3 L2 账本从只读 DB 副本独立复算；分级未拼成“全链 PASS” |
| **R8 回归 / 清理** | PASS（环境类失败已分类） | Host run2 1352/4/1（run1 1351/5/1，失败集合不同，P2-08）；fixed OCI filtered **1018/26/43/0**；Node **36/36**；Ruff product+G4-F PASS，F1 测试 1 个既有 F841（P2-04）；scanner 0 findings；`podman ps -a` 空、rootfs/deps/stage canonical、无 `.env`/Key env |

补充：

- Reviewer 的 L2 数据来自真实容器运行与只读 DB 副本；Owner 的 `summary.json`/`checks.json` 只作为启动/记录文件，不作为裁定文字。
- Reviewer **未重跑** OCI raw 与 OCI uid-0 replay（依赖 Owner 原始日志）；filtered OCI 为独立复现的权威计数。
- A12 并发错误码竞态为 Reviewer **新发现**（P2-03），见 §4.3。

---

## 4. P2 八项逐条处置

**总则**：以下 P2 均**不阻断**本轮限定范围 PASS；需维护者知情/决定的项不得默认视为已签收，UNVERIFIED 项不得被引用为已证明。本 errata **不代签**任何 P2。

| ID | 残余 | 归档处置 | 后续建议 |
|---|---|---|---|
| **P2-01** | Packet 的 2 个 post-build SQLite sidecar 未哈希，全量 payload tree 漂移 | **接受并冻结披露**：sidecar 是 Packet 构建后 SQLite 只读副本产生的 `-wal`/`-shm`，WAL 0 字节、SHM 32768 字节仅空 frame header，**无业务数据**；已哈希 `.sqlite3` 完整。Packet **不重打包** | 维护者决定是否生成 v2：删除 sidecar 后重建 `hashes.sha256`/tree，或显式排除 sidecar；v1 保持不可变 |
| **P2-02** | 矩阵 `F2-07` 的 `f6/.../tool-window.json` 路径不存在；实际为 `artifacts/g4f/f2/tool-window.json` | **接受并记录**：结论仍可由 F6 summary 与 Reviewer 独立 Tool run 验证；本归档按约束**只改 `REV-01..05`**，未修改 `F2-07` 行 | 在仓库矩阵后续修订或 Packet v2 中修正路径；不影响 F2-07 PASS 的证据实质 |
| **P2-03** | G4-A `a12` 并发 consume 错误码竞态（新发现） | **接受；非 P0/P1；fail-closed**。恰一次 consume，无发送/计费，无双重消费；loser 可能得 `AUTHORIZATION_USE_RECORD_INVALID` 而非 `AUTHORIZATION_REPLAYED`。详见 §4.3 | 后续修复：原子写 use record（临时文件 + link/rename）或 reader 对空/部分文件重试，并补稳定性测试 |
| **P2-04** | `tests/security/test_scan_git_secrets.py` 既有 F841（`material` 未使用） | **接受；需维护者知情**：F6-06 已披露；product + G4-F test scope Ruff PASS，不影响扫描器行为 | 清理测试变量；非阻断 |
| **P2-05** | F5 `timeout-pre-send` 无 dispatch-window 记录 | **接受；观察缺口**：0 reservation/attempt/Fake 的 DB 证据 + DSH error 仍支持“未发送”结论；Owner F5-R4 已披露 | 后续在 dispatch-window 中记录 pre-send 拒绝/超时事件；不改变本轮结论 |
| **P2-06** | F5 recovery 将 revocation attempt reason 重写为 `RECEIPT_DOCUMENT_SCHEMA_INVALID` | **接受；需维护者知情**：gate journal 与 dispatch-window 保留原始 `RUN_AUTHORIZATION_REVOKED`；状态/held 保守，未导致重发或双结算；Owner F5-R5 已披露 | 后续修复 recovery 的原因保持/映射；不影响本轮账本结论 |
| **P2-07** | Packet `env/zero-key.json` 只列 1/4 LiveGate reasons | **接受并冻结披露**：manifest 与 `review/livegate.json` 有 4 项，二者均为 `BLOCKED`；属证据一致性瑕疵 | Packet v2 补齐 4 项；v1 不原地改 |
| **P2-08** | Host full 失败集合与 Owner 归因不同：run2 计数 1352/4/1 但 a12 替换 target-profile | **接受并记录**：计数复现、集合不同；a12 归 P2-03；target-profile 是独立 worktree config mode（0644）环境差异；run1 为 1351/5/1 | 后续在归档脚本中固定 config mode；不要把不同失败集合写成同一归因 |

### 4.1 P2-01 SQLite sidecar 与 Packet 冻结（特别记录）

- 两个未哈希文件：`f4/sqlite-readonly/resume-attempts.sqlite3-shm`（32768 B）与 `resume-attempts.sqlite3-wal`（0 B），mtime `2026-11-19T15:11:07Z`，晚于 Packet created `2026-11-19T15:09:08Z`。
- 它们不在 `hashes.sha256`，也不在 manifest `files.count=172`；WAL 为空，SHM 只有空 frame header，不含业务行。
- 全量 payload tree `111c1361…` ≠ manifest `e464b9b1…`；剔除两个 sidecar 后恰为 `e464b9b1…`。
- **处置**：这是 **post-build SQLite 副产物导致的证据卫生漂移**，不是密钥、账本或实现内容篡改；已哈希 `.sqlite3` 仍完整。**Packet 冻结，不重打包**；不删除、不改写 Packet 内文件。是否在 v2 清理由维护者决定。

### 4.2 P2-02 F2-07 证据路径（特别记录）

- 矩阵 F2-07 的 `artifacts/g4f/f6/integration/f2/tool-window.json` 不存在；实际文件为 `artifacts/g4f/f2/tool-window.json`（12:34Z，F2 owner run）。
- F6 summary 仍可验证同一 3 dispatch / title fallback 结论；Reviewer 独立 Tool 两轮亦支持该结论。
- 本归档按硬约束**只改 `REV-01..05`**，因此 F2-07 行保持原字节；该路径修正列入维护者/后续修订清单（§9）。

### 4.3 P2-03 A12 并发 consume 错误码竞态（新发现，特别记录）

- **性质**：Reviewer 新发现，**不是 P0/P1**，不构成权限绕过、可计费出站、Key 泄漏、未授权 Fake、账本 FREE 或双发送。
- **复现**：`tests/integration/g4_a/test_a12_replay_epoch.py::test_a12_concurrent_consumption_admits_exactly_one`，standalone **2/30** 失败；full-host **2/2** 失败；失败随调度时序变化。
- **形态**：第二个 consumer 读到尚未写完的 use record，返回 `AUTHORIZATION_USE_RECORD_INVALID`，而测试/协议期望 `AUTHORIZATION_REPLAYED`。
- **安全姿态**：**fail-closed**。恰好一个 consume 成功；无发送、无计费、无双重消费；错误码分类不稳定，但不放宽授权。
- **后续修复建议**：use record 原子写（临时文件 + `link`/`rename`），或 reader 对空/部分文件短暂重试后归类为 replay；补充并发稳定性回归。该项列入 §9，不阻断本轮 no-key closeout。

### 4.4 P2-04 至 P2-08 记录

- **P2-04**：`tests/security/test_scan_git_secrets.py` 的 F841 为既有问题（F6-06 已披露）；Ruff product + G4-F test scope `All checks passed`；不影响 scanner 行为。
- **P2-05**：`timeout-pre-send` 无 dispatch-window 记录；0 行 DB/Fake 与 DSH error 仍可证未发送；属观察缺口。
- **P2-06**：recovery 将 revocation attempt reason 重写为 `RECEIPT_DOCUMENT_SCHEMA_INVALID`；gate journal/dispatch-window 保留 `RUN_AUTHORIZATION_REVOKED`；状态/held 保守。
- **P2-07**：`env/zero-key.json` 只列 1/4 LiveGate reasons；manifest 与 review livegate 有 4 项；均为 `BLOCKED`；属证据一致性修正。
- **P2-08**：Host run2 计数 1352/4/1 复现，但失败集合为 g3d frozen-src、a12、g4_d D15 host-env、sandbox PYTHONPATH；Owner 的 target-profile 项在 run2 通过，替换为 a12；run1 为 1351/5/1。**计数一致、集合不同**，不得写成同一归因。

---

## 5. E5 两列复核

Reviewer 独立复核 `E5-P01..P05` 的 NO_KEY_SUBSET 与 FULL_STATUS 两列：

| Gate | NO_KEY_SUBSET | FULL_STATUS | Reviewer 依据 |
|---|---|---|---|
| E5-P01 | **PASS** | `BLOCKED_PENDING_HUMAN_DEPLOYMENT` | `e5_probe p01-binding` 5/5：合成签名、冻结字节、单次记录、漂移拒绝 |
| E5-P02 | **PASS** | `BLOCKED_PENDING_HUMAN_DEPLOYMENT` | `p02` 10/10：五 root 漂移、route、tool schema、denied no-send |
| E5-P03 | **PASS** | `BLOCKED_PENDING_HUMAN_DEPLOYMENT` | `p03` 7/7：Markdown/env/self-sign/CLI/run_live/adapter/gates.py 无 env 批准 |
| E5-P04 | **UNVERIFIED** | `BLOCKED_PENDING_HUMAN_DEPLOYMENT` | probe 4/4 仅证明 capture fixture/allowlist 只有 `skill_lookup`，且 DSH registry export absent；无权威 merged registry |
| E5-P05 | **PASS** | `BLOCKED_PENDING_HUMAN_DEPLOYMENT` | Reviewer 重跑 p05 5/6（scanner 正控、env scrub、candidate argv 无 sentinel、mount 不含 trusted fixture、`--network none`）；D01/D02/D03 watchdog 原始证据独立重读 24/24、23/23、21/21，全部 PASS 且 `PENDING_CONSERVATIVE`；**watchdog 执行腿未由 Reviewer 重跑**，属 G4-D 历史证据 |
| E5-FULL | BLOCKED | `BLOCKED_PENDING_HUMAN_DEPLOYMENT` | 真实人类授权 / Key / Provider / TLS / 账单 / 部署后不可写未完成 |

- **P01/P02/P03/P05 仅 subset PASS；P04 为 UNVERIFIED。**
- **FULL 五项全部 `BLOCKED_PENDING_HUMAN_DEPLOYMENT`**；任何 subset PASS 不得写成 Full PASS，不得据此进入 G5/Live。
- 矩阵 `E5-FULL` 行保持 `BLOCKED` 原字节，不因 REV 行归档而改变。

---

## 6. 矩阵最终化

### 6.1 最终计数

| 时点 | 行数 | PASS | UNVERIFIED | NOT_RUN | BLOCKED | sha256 |
|---|---|---|---|---|---|---|
| 归档前 | 46 | 38 | 2 | 5 | 1 | `3587a2816a4f27ed9bf6bbd1be24fdc2e84620aae3363ad94675c7a7bf45e20b` |
| 归档后 | 46 | **43** | **2** | **0** | **1** | `0f4e25ae76632ff60e0c644d34a19bf6c602cf49e347112a1fb3be87a091dba3` |

- `REV-01..REV-05` 五行由 `NOT_RUN` → `PASS`，正好 +5 PASS、−5 NOT_RUN。
- `F2-08`、`F4-06` 保持 `UNVERIFIED`；`E5-FULL` 保持 `BLOCKED`。
- 未新增/删除行；总行数 46 不变。

### 6.2 仅修改的五行的字段

`REV-01..REV-05` 五行统一填写：

- `status = PASS`；
- `reviewer_status = PASS`；
- `actual`：引用 Reviewer 独立结果（R0/R1 身份与 Packet；R2/R3 scanner 与真实 Candidate；R4/R5 DSH 与窗口；R6/R7 LiveGate/E5/矩阵；R8 回归与清理）；
- `command_argv`：Reviewer 自建 Probe / 复跑命令；
- `utc_start = 2026-11-19T15:13:00Z`、`utc_end = 2026-11-19T16:22:00Z`（Reviewer 复核窗口）；
- `exit_code = 0`；
- `impl_sha = e7d92967ec0ece80de4a1a3705f637e8eb9bde99`；
- `stage_sha = 82e10c6ffe37e401a58730e9abcaa691f19d6702a7276c03df625d5b4636e501`（G4-F stage manifest）；
- `loaded_source_sha`：保持 `18/18 modules == HEAD blobs; controller 0152fcde…`；
- `evidence_paths`：`docs/REVIEW_G4F_INDEPENDENT.md`、`artifacts/reviewer-g4f/RUN_INDEX.md`、`VERDICT.json`、`SUMMARY.json`，并按域追加 `r0-identity/`、`r1-static/`、`r2-scanner/`、`r3-os/`、`r4-resume-ledger/`、`r5-windows/`、`r6-negatives/`、`r7-levels/`、`r8-regressions/`；
- `ledger_receipt_paths`：REV-02 指向 `r3-os/neg-only-20261119T152859Z.json`；REV-03 指向 `r4-resume-ledger/r4-audit.json` 与 `r5-windows/gate-summary.json`；其余 `N/A_NO_DISPATCH`；
- `level`：由 `REVIEW-NOT-RUN` 改为对应证据级别（`L1-PACKET+L1-STATIC`、`L1-STATIC+L2-OS+L2-RAW-UDS`、`L2-REAL-DSH+L2-RAW-UDS`、`L1-STATIC+L1-PACKET`、`L1-HOST+L2-OS`）；
- `residual`：范围限定 + 相关 P2（P2-01..P2-08）与“不构成 Live/生产安全/M0_GO”声明。

### 6.3 列语义与不可变性

- `impl_sha` 为 implementation `e7d9296`；`stage_sha` 为 stage manifest `82e10c6f…`；`loaded_source_sha` 保留 18/18 模块加载身份与 controller SHA。
- `exit_code = 0` 指 Reviewer 复核/归档流程整体成功；`run_live.sh`/CLI 的 exit 3 是**预期 BLOCKED 负例**；Host full 的 4 个失败（exit 1）已分类记录，不改变五行 PASS 的限定范围。
- **其余 41 行逐字节未改**（`git diff` 为 5 insertions / 5 deletions，仅第 42–46 行）。
- 历史 G3-C/G3-D 矩阵、旧 G4 矩阵与旧 Reviewer 报告均未改：G4 报告 `fc9e9880…`、G4 矩阵 `c16d49b7…`、G4 errata `f990e6af…`。
- 仓库矩阵归档后 sha256 为 `0f4e25ae76632ff60e0c644d34a19bf6c602cf49e347112a1fb3be87a091dba3`；Packet 内矩阵副本仍为归档前字节（`38/2/5/1`），差异仅为五行 `REV-01..05`。
- **P2-02 未在矩阵内修正**：`F2-07` 行保持原路径字节，因本归档硬约束只允许修改 `REV-01..05`；该路径问题由本 errata 与 §9 记录，待后续修订。

---

## 7. Packet 冻结说明

1. **Packet 不重打包**：`docs_sha` 仍为 `d12df41`、`impl_sha = e7d9296`、`code_sha = dbacb76`、`build_sha = 0d5e5e0`；归档时 `sha256sum -c hashes.sha256` 仍为 **173/173 OK**，177 files、0 symlink。
2. **Reviewer 报告、本 errata、矩阵 `REV` 最终化为 post-packet 产物**：`docs/REVIEW_G4F_INDEPENDENT.md`（sha `b17977d1…`）与本文件均产生于 Packet 冻结之后，故不在 Packet 内，也不触发重打包。
3. **Packet 内矩阵副本仍为归档前字节**（38 PASS / 2 UNVERIFIED / 5 NOT_RUN / 1 BLOCKED）；仓库矩阵归档后为 **43/2/0/1**。差异**仅** `REV-01..05` 五行，属预期的“归档前进”，不是 Packet 完整性失败。
4. **P2-01 sidecar 漂移已记录**：全量 payload tree `111c1361…`、去 sidecar 后 `e464b9b1…`；Packet 内文件未删除、未改写、未重打包。
5. **旧 G3/G4 证据与 Packet 未改**：旧 G4 Reviewer 报告 sha256 `fc9e9880fa4aa658937da1a9a196dc018857b98a87f6ba63f481a2e210ca2601`、旧 G4 矩阵 `c16d49b78be88c3c805d795f6e522ef9788abef5f8c11820095140e1952735f0`、旧 G4 errata `f990e6affe6d03eee5ae9c7a5d780ea5bf2c4e3e87a72c6099207735d7ef18c2` 均保持不变；旧 Packet 只读访问。
6. **不修改冻结字段**：Packet `reviewer=NOT_ASSIGNED` / `reviewer_status=PENDING_INDEPENDENT_REVIEW` 保留为冻结点事实；post-packet verdict 由本 errata、矩阵与 `artifacts/reviewer-g4f/VERDICT.json` 记录。

---

## 8. 最终状态声明与不得外推

归档后状态常量（不得改写）：

```text
G4-H            = NOT_AUTHORIZED
G5              = BLOCKED
G6              = NOT_RUN
LiveGate        = BLOCKED
M0              = DECISION_PENDING
E5_PRELIVE_FULL = BLOCKED_PENDING_HUMAN_DEPLOYMENT
```

- **不得把本裁定写成 G4 Full / E5 Full / Live 授权 / 生产安全**；不得写成 `M0_GO`、`G4_PASS`、`G5_PASS`、`LIVE_APPROVED` 或任何等价表述。
- `PASS_FOR_G4F_NO_KEY_CLOSEOUT_SCOPE` 只表示：在本机冻结环境、无 Key、无真实 Provider、固定 rootfs/deps/stage、合成账本与已披露 P2 的前提下，G4-F1..F6 的工程/隔离/合成账本/授权失败窗口/冻结材料经独立复核未发现 P0/P1。
- **P2-01 sidecar 是 SQLite 副产物，不是业务数据**；P2-03 的错误码竞态 fail-closed，不构成发送/计费问题；两者都不能被外推为 Live 或生产安全。
- **G4-H-01..06 仍全部 `BLOCKED / NOT_AUTHORIZED`**；真实信任根、Key Broker、Egress、Provider/TLS/账单/硬额度均未部署、未验证。
- 本归档不修改、不追溯升级任何历史 G3/G4 状态；旧 G3/G4 矩阵、Review 与 Packet 保持原样。

---

## 9. 维护者待决定清单

| # | 待决定 | 说明 / 影响 |
|---|---|---|
| 1 | **G4-H 六项人工阻断（G4-H-01..06）** | G4-H-01 冻结提交/依赖/配置/路由/预算独立二次审阅；G4-H-02 人类信任根/公钥注册/轮换/撤销/私钥离线；G4-H-03 独立 Key Broker/可信 Egress；G4-H-04 官方模型/Endpoint/价格/Usage/额度核验；G4-H-05 P2 签收 + E5 Full 独立安全 Review；G4-H-06 一次范围严格限定的 G5 试验授权。全部未完成 |
| 2 | **P2-DISK / P2-USERNS / P2-RUN-IDENTITY 签收** | G4-H-05 的前置；接受则作为已知残余，或另立配额/加固/per-run 身份工作项并重新取证。本 errata 不代签 |
| 3 | **E5 Full 独立安全 Review 与签收** | 当前 `E5_PRELIVE_FULL=BLOCKED_PENDING_HUMAN_DEPLOYMENT`；P01/P02/P03/P05 仅 subset PASS，P04 UNVERIFIED；需人类部署信任根、真实 Key/Provider/TLS/账单/额度后逐项执行 |
| 4 | **真实 Provider / TLS / 账本与硬额度** | 真实 Key 注入、官方价格/Usage、TLS/DNS、供应商账单与硬额度、凭据轮换/撤销；G4-H-01..04 |
| 5 | **是否授权 G5 单次 bounded run** | 当前 `G5=BLOCKED`；需 G4-H-01..05 完成并由人类显式授权 G4-H-06；本裁定不授权 |
| 6 | **是否重打包 Packet v2 修正 P2-01/P2-02/P2-07** | 可选：清理 sidecar 并重建 hashes/tree、修正 F2-07 路径、补齐 4 项 LiveGate reasons；v1 必须保留不可变副本 |
| 7 | **是否修复 P2-03 A12 错误码分类与 P2-04 lint** | 建议修复 A12 use record 原子写/重试与错误码分类，补并发稳定性测试；清理 F1 测试 F841。非阻断本轮 PASS |

在上述决定作出前，默认状态为：**P2 已登记但未全部获维护者正式签收**；`F2-08`/`F4-06` 与 E5-P04 为 **UNVERIFIED**；**G4-H/G5/G6/Live 未授权**；**M0 仍 DECISION_PENDING**。

---

## 10. 归档记录与不可变性

### 10.1 同提交文件（仅 3 个）

1. `docs/REVIEW_G4F_INDEPENDENT.md`（新增；原字节；34433 B；sha256 `b17977d1ff8506de440996f7bd411149ae968cef6564391b74b28980468ddc4b`）；
2. `docs/M0_G4F_REVIEW_ERRATA.md`（本文件，新增；append-only）；
3. `docs/Autonomous_Teacher_M0_G4F_Closeout_Test_Evidence_Matrix_v1.0.csv`（仅 `REV-01..REV-05` 五行；归档后 sha256 `0f4e25ae76632ff60e0c644d34a19bf6c602cf49e347112a1fb3be87a091dba3`）。

### 10.2 提交约束

- **提交信息**：`docs: archive G4-F independent review (PASS) and final errata (no-key)`。
- 父提交应为 `0d5e5e09cd607aef6ba39608b8a3b33a0d2c7705`；**不 amend / 不 push / 不 stage 其他文件**。
- 提交后工作区应为 clean（`git status --porcelain -uall` 0 行）；`artifacts/` 仍被 gitignore，Reviewer 证据不进入提交。
- **报告字节不变**：提交前后 `docs/REVIEW_G4F_INDEPENDENT.md` sha256 必须始终为 `b17977d1…`；若未来发现不一致，以本文件追加勘误处理，不得静默改写。
- 归档时环境复核：rootfs `25491e45…`、deps `e07729d7…`、stage manifest `82e10c6f…`/tree `7d32ec1d…`、Packet 173/173 均未漂移；`podman ps -a` 空；0 真实 Key / 0 外网 / 0 Live。

### 10.3 append-only 版本记录

| 版本 | UTC | 内容 |
|---|---|---|
| v1 | 2026-11-19T16:33Z | 初次归档：Reviewer 报告原字节归档、矩阵 `REV-01..05 → PASS`、P2 八项 / E5 两列 / Packet 冻结 / 最终状态 / 维护者待决定清单登记 |

---

## 附录 A：复核证据索引

| 内容 | 路径 |
|---|---|
| Reviewer 报告 | `docs/REVIEW_G4F_INDEPENDENT.md` |
| Run 索引 | `artifacts/reviewer-g4f/RUN_INDEX.md` |
| 裁定 JSON | `artifacts/reviewer-g4f/VERDICT.json` |
| 摘要 JSON | `artifacts/reviewer-g4f/SUMMARY.json` |
| R0 身份 / Packet / Stage / loaded modules | `artifacts/reviewer-g4f/r0-identity/` |
| R1 静态审计 | `artifacts/reviewer-g4f/r1-static/` |
| R2 自建 Scanner | `artifacts/reviewer-g4f/r2-scanner/` |
| R3 真实 Candidate OS / raw-UDS | `artifacts/reviewer-g4f/r3-os/` |
| R4 真实 DSH Echo/Tool/Resume/账本 | `artifacts/reviewer-g4f/r4-resume-ledger/` |
| R5 Revocation/Timeout/In-flight | `artifacts/reviewer-g4f/r5-windows/`（报告/RUN_INDEX 记作 `r5-audit.json`，实际落盘为 `gate-summary.json` 与 `r5-audit.log`） |
| R6 LiveGate/Key/Network/E5 | `artifacts/reviewer-g4f/r6-negatives/` |
| R7 矩阵 / 分级 / 原始解析 | `artifacts/reviewer-g4f/r7-levels/` |
| R8 回归 / 清理 | `artifacts/reviewer-g4f/r8-regressions/`（`final-state.json`、`host/`、`oci-filtered/`、`node/`） |
| Packet | `artifacts/review-packet-g4f-e7d92967ec0ece80de4a1a3705f637e8eb9bde99/` |
| Stage | `artifacts/g4/c/stages/stage-20261119T142828Z/` |
