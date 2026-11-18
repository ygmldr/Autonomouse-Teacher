# M0 G4 — 独立复核归档勘误与残余登记（append-only）

- **文档性质**：G4 最终归档的勘误、P2 残余、范围限定与历史状态登记。本文件为 **append-only**：后续如需修订，只在文件末尾追加新小节，不改写既有字节。
- **归档时间**：2026-11-18T21:54Z（UTC）。
- **归档提交**：`docs: archive G4 independent review (PASS) and final errata (no-key)`。同一提交只包含三个文件：本文件（新增）、`docs/REVIEW_G4_INDEPENDENT.md`（原字节归档）、`docs/Autonomous_Teacher_M0_G4_PreLive_Test_Evidence_Matrix_v1.0.csv`（仅 `G4-E-06..E-10` 五行）。
- **约束**：0 真实 Key / 0 真实模型 / 0 外网 / 0 Live；未 `podman pull`；未修改实现、测试、脚本、证据、Packet、历史 docs 或历史矩阵字节；未 amend、未 push。归档动作只写 `docs/` 三个文件。

---

## 1. 归档对象与冻结输入

### 1.1 Reviewer 身份、独立性与窗口

- **Reviewer**：Independent G4 Reviewer（未署名独立复核 Agent），报告 ID `REVIEW-G4-INDEPENDENT-20261118T2141Z`。
- **独立性声明**：未参与 G4-00、G4-A/B/C/D/E 的任何实现、测试编写、证据生成、矩阵填写或 Review Packet 构建；未参与 G3-C/G3-D 实现。关键结论来自 Reviewer 自建 Probe、自跑命令、原始字节/SQLite 只读副本与独立对账，未把 Owner 的 `checks.json`/`summary.json` 状态文字当作判定。
- **复核窗口（UTC）**：`2026-11-18T20:47Z` → `2026-11-18T21:41Z`。
- **工作树**：`/root/Autonomous Teacher`；复核开始/结束 HEAD 均为 `8e5ca7a68210fed3368c45757779abf1de1be318`。
- **写入范围**：仅 `docs/REVIEW_G4_INDEPENDENT.md` 与 gitignored `artifacts/reviewer-g4/`；Reviewer 未修改矩阵、Packet、Stage、rootfs/deps、历史证据或任何历史 docs，未 commit / amend / push。
- **证据索引**：`artifacts/reviewer-g4/RUN_INDEX.md`。

### 1.2 冻结输入（Reviewer 独立复算一致）

| 对象 | 冻结值 |
|---|---|
| base | `017c747631cae1e7788014c4ef9e6056c141fecd` |
| implementation | `a6f3e0a27a516534803a1e3549dc60fbd107583c` |
| code | `d3d429cf9d0cb1e9dbc68317928631db413be309` |
| docs / HEAD | `8e5ca7a68210fed3368c45757779abf1de1be318` |
| G4 Stage | `artifacts/g4/c/stages/stage-20261118T193401Z`；manifest `853530183d75f6c1813621ec0c67575aa26553d4f2bf213ae40910e10817de48`；tree `9c9ce31312ad060a9734b01d98d4ce9c5e64a2064f54ef32abc77e025358762b` |
| G3-D Stage | tree `e1ff14496e06dcb1c887badfb93b858012373be9fe739e61bb04587885e9f9c5`；manifest `644823d46adaef28810ba13bb97547371616177bbc4b8138b1eaed5d9a28eb03`；未被 G4 修改/加载 |
| rootfs | `25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0` |
| deps | `e07729d7997944417b1c25531749b3e6e5e34aa4248f01dc8f370282082ecb98` |
| DSH runtime | `1cc41d5a…`，版本 `0.2.2-rc.2` |
| Node / adapter | `v22.23.2` / built JS `2cb424616b7380bff61f8ce760e229a0c1d2b32c4a5f2954cdf66c3937bf74ba` |
| Python | `3.11.15` |

### 1.3 Reviewer 报告

| 项 | 值 |
|---|---|
| 路径 | `docs/REVIEW_G4_INDEPENDENT.md` |
| 大小 | 32398 B |
| sha256 | `fc9e9880fa4aa658937da1a9a196dc018857b98a87f6ba63f481a2e210ca2601` |
| 归档方式 | 新文件、**原字节** `git add`；提交前后 sha256 必须保持上述值 |
| 只读约束 | 归档方未修改报告字节；报告本身不是 Live 授权，不是 E5 Full，不是 G4-H/G5/G6 批准 |

### 1.4 Review Packet（只读，未重打包）

- 路径：`artifacts/review-packet-g4-a6f3e0a27a516534803a1e3549dc60fbd107583c/`。
- 归档时复核：**211 files**、`sha256sum -c hashes.sha256` **209/209 OK**、208 payload、0 symlink；`packet_payload_tree_sha256 = 70101edbe56e7d384c3858ee1e75f7516573f0106a8c7831d85de8a768901a27`。
- `manifest.json`：`docs_sha = 8e5ca7a`、`head_at_packet = 8e5ca7a`、`impl_sha = a6f3e0a`、`code_impl_sha = d3d429c`、`provider_route_kind = synthetic_only`、`real_model_calls = 0`、`real_external_http_calls = 0`、`key_present = false`、`live_gate = BLOCKED`。
- **冻结说明**：Reviewer 报告与本次 errata 均为 **post-packet** 产物，不进入 Packet，不触发重打包；详见 §7。

---

## 2. 裁定与范围限定

### 2.1 唯一裁定

```text
PASS_FOR_G4_NO_KEY_PRELIVE_ENGINEERING_SCOPE
```

- **P0 = 0；P1 = 0；P2 = 8**（逐项见 §4）。
- 该裁定仅覆盖 G4-A/B/C/D 的无 Key 工程、隔离、合成账本、授权/发送校验与 E5 无 Key 子集，且已由独立 Reviewer 复跑/复核。
- **不得**合并为 “G4 Full / E5-PreLive Full / 可 Live / 生产安全”。

### 2.2 与裁定同义、不可省略的范围限定

本 PASS 仅限 **本机冻结环境**：

1. 固定 rootfs / deps / G4 Stage / DSH runtime，SHA 见 §1.2；
2. **无真实 Key、无真实 Provider、无外部 HTTP/TCP、无 `podman pull`、无 Live**；
3. 合成账本与 Fake Provider；
4. 已披露的 P2 残余与 UNVERIFIED 项（§4、§5）；
5. 所有容器运行使用 `--network none --read-only --cap-drop ALL --security-opt no-new-privileges`，Candidate 使用 `--uidmap 0:65534:1`。

**不主张、也不得外推为**：

- 内核 / 容器运行时 0day 防护，或宿主 root 被攻陷后的安全；
- 真实人类信任根 / Key Broker / 可信 Egress / 真实 Provider / TLS / DNS / 账单 / 供应商硬额度；
- E5-PreLive Full、G4 Full、G5、G6、M0 GO、任何 Live 授权或生产部署安全；
- 跨宿主 / 跨内核 / 跨 Runtime / 跨 Stage 的可移植性；
- exactly-once 或真实 Invoice 语义。

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
| **R0 身份 / Packet / Stage** | PASS | HEAD/base/impl/code/docs 一致；Packet 209/209、payload tree、0 symlink；真实容器 `inspect.getfile` 17/17 指向 `/project/src` 且 sha == `d3d429c`；旧 Stage/篡改 Stage fail-closed（preflight exit 7 / 2） |
| **R1 静态复验** | PASS | `gates.py` 恒 BLOCKED；`run_live.sh` exit 3；Adapter 四个 live 入口先 `SECURITY_BLOCKED`；`cli.py --live` 先 `require_live`；strict JSON / 5 绑定根 / 单次消费 / real route 恒 BLOCKED |
| **R2 自建 Auth fuzz** | PASS | 58 个自建 case、0 失败；`billable_send_authorized` 全 False；Ed25519 小阶/mixed-order/非 canonical/`S>=L`、严格 JSON、可信文件、重放/跨 epoch 全部 deny |
| **R3 真实 Candidate OS 攻击** | PASS | uid_map `0:65534:1`、`CapEff=0`、`NoNewPrivs=1`；`/work/state` ENOENT、`/project` EROFS、socket ENXIO；旧 G3-B 四类不可达；AF_INET EACCES；同 host uid 65534 对真实 run 路径 EACCES；攻击前后账本 0/0 |
| **R4 真实 DSH 两轮 + 重放** | PASS；resume L2 UNVERIFIED | c01 1/1/1/1/1（Fake=1）；c02 2/2/2/2/2（Fake=2）；两套 call_id / 摘要对独立对账；真实重放第二次 `ATTEMPT_ALREADY_STARTED`、Fake 不增；DSH resume 未跑 → C16 PARTIAL |
| **R5 故障 / Watchdog** | PASS | broker-down 0/0；crash-before `SETTLEMENT_UNCERTAIN`/0 receipt；crash-after `SETTLED`/1 receipt；watchdog 24/24、`podman ps -a` 空、不存在性 `lstat` 语义、`pending.json` `PENDING_CONSERVATIVE` |
| **R6 Live / Key 硬负例** | PASS | LiveGate / `require_live` / `run_live.sh` / CLI / Adapter / Markdown / 自签 JSON 全部 BLOCKED 或 deny；socket audit 0 事件；0 Key / 0 外网 / 0 真实模型 |
| **R7 证据分级** | completed | L2-REAL-DSH、L2-OS、L1-HOST、L1-STATIC、L1-PACKET 分级；UNVERIFIED/human-required 单列 |
| **R8 回归** | PASS（环境限制已分类） | Host full 1285 = 1280 passed / 4 failed（4 项均 host-only 环境或 frozen-src，逐项归因）/ 1 skipped；OCI filtered **957 passed / 24 skipped / 34 deselected / 0 failed，exit 0**；Node guard 19/19、skill 8/8、adapter UNVERIFIED；Ruff scoped 0 |

补充：

- Reviewer **未单独重跑** Owner 声明的 OCI uid0 replay 294 项；以 Host 223 项 auth 单测 + OCI raw 分类覆盖，不写成“294 全量重跑”。
- Host full 的 4 个失败与 OCI raw 的 181 个环境失败均如实保留；filtered OCI 是权威计数。
- 所有账本结论来自只读 DB 副本（复制到 `/tmp` 打开），未原地打开 Packet/证据 DB。

---

## 4. P2 八项逐条处置

**总则**：以下 P2 均**不阻断**本轮限定范围 PASS；需维护者知情/决定的项不得默认视为已签收，UNVERIFIED 项不得被引用为已证明。

| ID | 残余 | 归档处置 | 维护者动作 |
|---|---|---|---|
| **P2-1** | Packet `source/tests` 与 `changes/implementation.diff` 含 `TEST_ONLY_SEED = bytes.fromhex("5a"*32)` 的可重建推导（5a*32，无原始 seed） | **接受；需维护者知情**。合成测试种子，非 Candidate/运行时/真实 Key，未注册任何部署信任根；不能开 LiveGate。属证据卫生问题，不是密钥泄漏 | 建议未来 Packet 只保留该 fixture 的 hash，或显式标注 TEST_ONLY；是否在 v2 清理见 §9.5 |
| **P2-2** | Owner `oci-env-deselects.json` 只列 30 个 node id 却声称 34；漏列 `test_digest_sidecar_contract` | **接受并修正口径**：34 个 deselect **包含** `test_digest_sidecar_contract`；Reviewer 显式加入后得到 **957/24/34/0**。属证据记账修正，不是产品断言失败 | 后续重建 deselect 清单时补齐；Packet 内旧文件不原地改，见 §7 |
| **P2-3** | `G3B_TEST_MODE` / `G3B_CRASH_HOOK` 测试崩溃钩子仍在产品 controller | **接受；需维护者知情**。仅 launcher 可信 env 可触发，结果是 `os._exit` / fail-closed；不构成开 Live 或发送路径 | G4-H 评估移除或改为仅测试构建 |
| **P2-4** | P2-RUN-IDENTITY：同 UID 拒绝依赖 mount namespace + root `0700` DAC，不是 per-run OS 身份 | **接受现状并如实披露**；本裁定不主张 per-run OS 身份 | 维护者签收，或新增 per-run capability/独立 UID 并补测 |
| **P2-5** | `TrustedSendGate.snapshot().worst_case_held_usd` 恒为 0（`_held_usd` 未累加） | **接受；需维护者知情**。synthetic 路径预算仍由 known cost + hard cap 检查；不影响本轮 0-Live | 真实路由前补齐 held 语义并复验 |
| **P2-6** | G4-C 无真实 DSH resume L2；C16 仍 PARTIAL | **UNVERIFIED**；只证明 durable identity/replay 层与真实 raw-UDS 重放不发送，不外推 resume 连续性 | G5/G4-H 前补一次真实 resume，或明确维持 UNVERIFIED |
| **P2-7** | Packet `reviewer=NOT_ASSIGNED` / `reviewer_status=PENDING_INDEPENDENT_REVIEW` | **冻结字段说明**：这是 Packet 冻结时的预期值；Reviewer 报告与 verdict 为 post-packet 产物。**不修改 Packet**，本 errata 与矩阵记录 post-packet verdict | 决定是否重打包 v2（§9.5）；v1 保持原样 |
| **P2-8** | OCI raw 精确 27 failure 未复现（Reviewer 的 raw 选择集/副本不同，得 1078 passed / 181 env failures / 26 skipped） | **接受并披露**：181 全为环境类（root-only trusted dir、缺少 git/tar//bin/sh/bash、缺 `/project/artifacts` fixture、0644 mode）；filtered **957/24/34/0** 与 Owner 数字一致 | 知情即可；不要把 27 当作唯一环境计数 |

### 4.1 P2-2 OCI deselect 口径修正（特别记录）

- Owner 的 `artifacts/g4/e/regression/oci-env-deselects.json` 列出 **30** 个 node id，但同期声称 **34** 个 deselect。
- 缺失项为 `test_digest_sidecar_contract`：固定 rootfs 无 `git`，该测试在 OCI 内必须 deselect 才能得到 0 failed。
- Reviewer 在 filtered run 中显式加入该项，得到 **957 passed / 24 skipped / 34 deselected / 0 failed，exit 0**。
- **归档口径**：从此 G4 证据中“34 deselects”指包含 `test_digest_sidecar_contract` 的集合；这是 **证据记账修正**，不是产品失败，也不是把 30 说成 34 的含糊处理。

### 4.2 P2-7 Packet reviewer 字段冻结（特别记录）

- Packet 在 `8e5ca7a` 冻结点写入 `reviewer=NOT_ASSIGNED`、`reviewer_status=PENDING_INDEPENDENT_REVIEW`，这是“独立复核尚未发生”的事实快照。
- 独立复核完成后，**不回写冻结 Packet**；本 errata、矩阵 `G4-E-06..E-10` 的 `reviewer_verdict=PASS` 与 `artifacts/reviewer-g4/VERDICT.json` 共同构成 post-packet 记录。
- 因此 `docs_sha` 仍为 `8e5ca7a`，Packet 完整性不受影响；是否生成含 reviewer 字段的 v2 由维护者决定（§9.5）。

### 4.3 P2-1 test-only seed 非真实 Key（特别记录）

- `TEST_ONLY_SEED = bytes.fromhex("5a"*32)` 是测试源码中可重建的**合成**种子；Packet 以该表达式保留可重建推导，而非原始 seed 值。
- 该种子未注册到任何部署信任根，Candidate/rootfs/deps 中无原始字节/十六进制；不能用于签发真实授权，不能开 LiveGate。
- 仍建议未来 Packet 只保留 fixture hash 或显式 TEST_ONLY 标注，避免审计时被误读为密钥材料。

---

## 5. E5 两列复核

Reviewer 独立复核 `E5-P01..P05` 的 NO_KEY_SUBSET 与 FULL_STATUS 两列：

| Gate | NO_KEY_SUBSET | FULL_STATUS | Reviewer 依据 |
|---|---|---|---|
| E5-P01 | **PASS** | `BLOCKED_PENDING_HUMAN_DEPLOYMENT` | R2 合成签名 + 5 绑定根；漂移 deny；外部人类签名未部署 |
| E5-P02 | **PASS** | `BLOCKED_PENDING_HUMAN_DEPLOYMENT` | R2 runtime SHA/闭包漂移；stage tamper fail-closed；部署后不可写未证 |
| E5-P03 | **PASS** | `BLOCKED_PENDING_HUMAN_DEPLOYMENT` | R6 Markdown/env/flag/self-sign 均不能开 gate；正式审批未上线 |
| E5-P04 | **UNVERIFIED** | `BLOCKED_PENDING_HUMAN_DEPLOYMENT` | 无可导出 merged registry；未知动态 tools 不可枚举（B03/D13） |
| E5-P05 | **PASS** | `BLOCKED_PENDING_HUMAN_DEPLOYMENT` | R3 无 Key/哨兵命中、无网络；D01 清理；真实 Key/TLS/账单未证 |

- **P01/P02/P03/P05 仅 subset PASS；P04 为 UNVERIFIED。**
- **FULL 五项全部 `BLOCKED_PENDING_HUMAN_DEPLOYMENT`**；任何 subset PASS 不得写成 Full PASS，不得据此进入 G5/Live。
- B03 merged registry、B07 session-title、C16 resume、Node adapter 9/9 仍在 UNVERIFIED 列表，见 §9.4。

---

## 6. 矩阵最终化

### 6.1 最终计数

| 时点 | 行数 | PASS | PARTIAL | UNVERIFIED | NOT_RUN | BLOCKED | sha256 |
|---|---|---|---|---|---|---|---|
| 归档前 | 85 | 62 | 10 | 2 | 5 | 6 | `08351786946c872999facb610a666072412dfd5fbe63f810a0e1e85975ad32e9` |
| 归档后 | 85 | **67** | **10** | **2** | **0** | **6** | `c16d49b78be88c3c805d795f6e522ef9788abef5f8c11820095140e1952735f0` |

- G4-H 六行仍为 **BLOCKED**；未新增/删除行；85 行总数不变。
- `G4-E-06..E-10` 五行由 `NOT_RUN` → `PASS`，正好 +5 PASS、−5 NOT_RUN。

### 6.2 仅修改的五行的字段

`G4-E-06..E-10` 五行统一填写：

- `status = PASS`；
- `actual`：引用 Reviewer 独立结果（E06 58 cases/0 fail；E07 真实 Candidate OS 攻击/旧绕过 + c01/c02 账本对账；E08 watchdog/crash；E09 live/key 硬负例；E10 裁定 + 报告 sha + P0/P1=0）；
- `command_argv`：Reviewer 自建 Probe / 证据路径；
- `utc_start = 2026-11-18T20:47:00Z`、`utc_end = 2026-11-18T21:41:00Z`（Reviewer 复核窗口）；
- `exit_code = 0`；
- `impl_sha = d3d429cf9d0cb1e9dbc68317928631db413be309`（code SHA）；
- `stage_sha = 853530183d75f6c1813621ec0c67575aa26553d4f2bf213ae40910e10817de48`（G4 stage manifest）；
- `loaded_source_sha`：`17/17=git:d3d429c=git:HEAD` + rootfs `25491e45…` + deps `e07729d7…` + stage tree `9c9ce313…`；
- `evidence_paths`：`docs/REVIEW_G4_INDEPENDENT.md`、`artifacts/reviewer-g4/RUN_INDEX.md`、`artifacts/reviewer-g4/VERDICT.json`，并按域追加 `r2-auth/`、`r3-os/`、`r4-dsh/`、`r5-faults/`、`r6-negatives/`、`r1-static/`；
- `ledger_receipt_paths`：E07 指向 `r4-dsh/c01-audit.json`、`c02-audit.json`、`replay/replay-report.json`、`r3-hold-report.json`；E08 指向 `r5-faults/` 崩溃与 watchdog 证据；E06/E09/E10 为 `N/A_NO_DISPATCH`；
- `reviewer_verdict = PASS`；
- `residual`：范围限定 + 相关 P2（P2-1/P2-3/P2-4/P2-5/P2-6/P2-8）与“不构成 Live/生产安全”声明。

### 6.3 列语义与不可变性

- G4 CSV 的列名为 `impl_sha,stage_sha,loaded_source_sha`（不同于 G3-D 矩阵的 `code_sha,stage_sha,env_sha`）。本归档的映射是：`impl_sha` = code `d3d429c`；`stage_sha` = G4 stage manifest `85353018…`；`loaded_source_sha` = 17/17 模块加载身份 + rootfs/deps/stage_tree 环境 SHA。这样既保留“实际加载代码”语义，也显式记录 env SHA。
- `exit_code = 0` 指 Reviewer 自建 Probe/归档流程的总体退出码；`run_live.sh`/CLI 的 exit 3 是**预期 BLOCKED 负例**；Host full 的 4 个 host-only 环境失败及 exit 1 记录在 Reviewer 报告 §11.1，不改变本五行 PASS 的限定范围。
- **其余 80 行逐字节未改**（`git diff` 为 5 insertions / 5 deletions，仅第 76–80 行）；历史 G3-C/G3-D 矩阵未改：G3-D `178a091541a30b684f3134fc3537bd8310b3d76345a6e70f8829928b98118ceb`、G3-C `6f21d56242815f7bfc0a88d9c94cd1c7c33c7a640646c98b51c060da45345d44`。
- 矩阵文件在归档编辑后权限恢复为 `0400`（本地冻结态）；git index mode 仍为 `100644`，不产生模式变更。

---

## 7. Packet 冻结说明

1. **Packet 不重打包**：`docs_sha` 仍为 `8e5ca7a68210fed3368c45757779abf1de1be318`；归档时 `sha256sum -c hashes.sha256` 仍为 **209/209 OK**，211 files、0 symlink。
2. **Reviewer 报告与 errata 为 post-packet 产物**：`docs/REVIEW_G4_INDEPENDENT.md`（sha `fc9e9880…`）与 `docs/M0_G4_REVIEW_ERRATA.md` 均产生于 Packet 冻结之后，故不在 Packet 内，也不触发重打包。
3. **Packet 内矩阵副本仍为归档前字节**（62 PASS / 10 PARTIAL / 2 UNVERIFIED / 5 NOT_RUN / 6 BLOCKED）；仓库矩阵归档后为 67/10/2/0/6。差异**仅** `G4-E-06..E-10` 五行，属预期的“归档前进”，不是 Packet 完整性失败。
4. **旧 G3-C/G3-D Packet/Review 未改**：`docs/REVIEW_G3D_INDEPENDENT.md` sha256 = `a16dd453386a23b51566f474dc4bc4166a6823fa586d85e3a49bb38adfc07a45`（等于 G4 Packet `previous_review.report_sha256`）；G3-D/G3-C Packet 与 Review 未由本归档修改；G3-C/G3-D 历史矩阵字节未改。
5. **不修改冻结字段**：Packet `reviewer=NOT_ASSIGNED` / `reviewer_status=PENDING_INDEPENDENT_REVIEW` 保留为冻结点事实；post-packet verdict 由本 errata、矩阵与 `artifacts/reviewer-g4/VERDICT.json` 记录。

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
- `PASS_FOR_G4_NO_KEY_PRELIVE_ENGINEERING_SCOPE` 只表示：在本机冻结环境、无 Key、无真实 Provider、固定 rootfs、合成账本与已披露 P2 的前提下，G4-A/B/C/D 无 Key 工程与 E5 无 Key 子集经独立复核未发现 P0/P1。
- **P2-1 合成测试种子不是真实 Key，不能开 LiveGate**；P2-3 测试钩子不能开 Live；P2-7 的 Packet reviewer 字段是冻结值，不是复核结论。
- G4-H-01..06 仍全部 `BLOCKED / NOT_AUTHORIZED`；真实信任根、Key Broker、Egress、Provider/TLS/账单/硬额度均未部署、未验证。
- 本归档不修改、不追溯升级任何历史 G3 状态；旧 G3 矩阵、G3-C/D Review 与 Packet 保持原样。

---

## 9. 维护者待决定清单

| # | 待决定 | 说明 / 影响 |
|---|---|---|
| 1 | **P2-DISK / P2-USERNS / P2-RUN-IDENTITY 签收** | G4-H-05 的前置；接受则作为已知残余，或另立配额/加固/per-run 身份工作项并重新取证。本 errata 不代签 |
| 2 | **G4-H-01..06 六项** | 真实信任根与人类签名、独立 Key Broker / Egress、官方 Provider/价格/Usage/硬额度核验、E5 Full 独立 Review、冻结输入二次审阅；全部未完成 |
| 3 | **是否授权 G5 单次 bounded run** | 当前 `G5=BLOCKED`、`G4-H-06=NOT_AUTHORIZED`；需人类显式授权，且前置 G4-H-01..05 完成 |
| 4 | **C16 / DSH resume L2 与 Node adapter 9/9 补测** | 当前 C16 PARTIAL、DSH resume UNVERIFIED、adapter 9/9 UNVERIFIED；补测可转已证明，不补测则维持 UNVERIFIED |
| 5 | **是否将 Packet 重打包为含 reviewer 字段的 v2** | 当前 v1 冻结、`docs_sha=8e5ca7a`、`reviewer=NOT_ASSIGNED`；若重打包需保留 v1 不可变副本，并处理 P2-1 测试种子与 P2-2 deselect 清单 |
| 6 | （建议）P2-3 测试钩子移除 / P2-5 `held_usd` 语义 / OCI deselect 清单修正 | 非阻断本轮 PASS；建议在 G4-H/G5 前排期 |

在上述决定作出前，默认状态为：**P2 已登记但未全部获维护者正式签收**；C16/DSH resume/Node adapter 等为 **UNVERIFIED**；**G4-H/G5/G6/Live 未授权**；**M0 仍 DECISION_PENDING**。

---

## 10. 归档记录与不可变性

### 10.1 同提交文件（仅 3 个）

1. `docs/REVIEW_G4_INDEPENDENT.md`（新增；原字节；32398 B；sha256 `fc9e9880fa4aa658937da1a9a196dc018857b98a87f6ba63f481a2e210ca2601`）；
2. `docs/M0_G4_REVIEW_ERRATA.md`（本文件，新增；append-only）；
3. `docs/Autonomous_Teacher_M0_G4_PreLive_Test_Evidence_Matrix_v1.0.csv`（仅 `G4-E-06..E-10` 五行；归档后 sha256 `c16d49b78be88c3c805d795f6e522ef9788abef5f8c11820095140e1952735f0`）。

### 10.2 提交约束

- **提交信息**：`docs: archive G4 independent review (PASS) and final errata (no-key)`。
- 父提交应为 `8e5ca7a68210fed3368c45757779abf1de1be318`；**不 amend / 不 push / 不 stage 其他文件**。
- 提交后工作区应为 clean（`git status --porcelain -uall` 0 行）；`artifacts/` 仍被 gitignore，Reviewer 证据不进入提交。
- **报告字节不变**：提交前后 `docs/REVIEW_G4_INDEPENDENT.md` sha256 必须始终为 `fc9e9880…`；若未来发现不一致，以本文件追加勘误处理，不得静默改写。
- 归档时环境复核：rootfs `25491e45…`、deps `e07729d7…`、G4 stage tree `9c9ce313…`/manifest `85353018…`、G3-D stage tree `e1ff1449…` 均未漂移；`podman ps -a` 空；0 真实 Key / 0 外网 / 0 Live。

### 10.3 append-only 版本记录

| 版本 | UTC | 内容 |
|---|---|---|
| v1 | 2026-11-18T21:54Z | 初次归档：Reviewer 报告原字节归档、矩阵 `G4-E-06..E-10 → PASS`、P2 八项/ E5 两列 / Packet 冻结 / 最终状态 / 维护者待决定清单登记 |

---

## 附录 A：复核证据索引

| 内容 | 路径 |
|---|---|
| Reviewer 报告 | `docs/REVIEW_G4_INDEPENDENT.md` |
| Run 索引 | `artifacts/reviewer-g4/RUN_INDEX.md` |
| 裁定 JSON | `artifacts/reviewer-g4/VERDICT.json` |
| R0 身份 / Packet / Stage | `artifacts/reviewer-g4/r0-identity/` |
| R1 静态 | `artifacts/reviewer-g4/r1-static/` |
| R2 Auth fuzz | `artifacts/reviewer-g4/r2-auth/` |
| R3 真实 Candidate OS | `artifacts/reviewer-g4/r3-os/` |
| R4 真实 DSH / 重放 | `artifacts/reviewer-g4/r4-dsh/` |
| R5 故障 / Watchdog | `artifacts/reviewer-g4/r5-faults/` |
| R6 Live 负例 | `artifacts/reviewer-g4/r6-negatives/` |
| R7 证据分级 | `artifacts/reviewer-g4/r7-levels/` |
| R8 回归 / 终态 | `artifacts/reviewer-g4/r8-regressions/` |
| 原始日志 | `artifacts/reviewer-g4/logs/` |
| 本勘误 | `docs/M0_G4_REVIEW_ERRATA.md` |
