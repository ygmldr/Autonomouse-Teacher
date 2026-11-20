# M0 G4-R — 独立复核归档勘误与 REV 状态登记（append-only）

- **文档 ID**：`M0-G4R-REVIEW-ERRATA-v1`
- **生成时间（UTC）**：`2026-11-20T17:30Z`
- **文档性质**：**append-only 归档勘误**。本文件只新增自身；**不修改**任何既有文件字节，尤其
  `docs/REVIEW_G4R_INDEPENDENT.md`（原字节 sha256 见 §0，复核前后必须一致）。不重打包 Packet、不改矩阵字节、
  不改 `src/tests/scripts/`。本文件不是授权、不是批准、不是部署证据、不是 Live 许可。
- **当前状态常量（未变）**：`G4-H=NOT_AUTHORIZED`、`G5=BLOCKED`、`G6=NOT_RUN`、`LiveGate=BLOCKED`、
  `M0=DECISION_PENDING`、`E5_PRELIVE_FULL=BLOCKED_PENDING_HUMAN_DEPLOYMENT`。

## 0. 适用对象与冻结身份（实测/引用）

| 对象 | 值 |
|---|---|
| base | `3e7afee077845a071cd364e93ab209cac20b2d5f` |
| 冻结 impl | `d33e0aabd1714a486325b745c436cb59855d6539`（`impl_git_commit`=`impl_sha`；`impl_content_sha256=5551078a284a40da9b6049c4f7bc5d3abfacfa8f364bc4949b44999257922e45`） |
| docs commits | `bc08bdd`（联合回归/终稿矩阵）、`64522d9`（R4 Packet v2 报告合并）、`9768933`（本 worktree HEAD = 独立 Review 报告/证据合并） |
| Reviewer 报告 | `docs/REVIEW_G4R_INDEPENDENT.md`；review 提交 `e72255d`；**文件 sha256（实测）**：`0599856aec247d0834a88a8967db81bd68965578a35eed37dbdf45322068446c` |
| Reviewer 证据 | `docs/g4r_review_evidence/`：**43 个文件（`find -type f` 实测）**；自建探针 2 个：`scripts/g4r_review/r_rev2_race_probe.py`、`scripts/g4r_review/r_rev5_packet_verifier.py` |
| 最终 Packet v2（gitignored，仓库外 worktree） | `/root/Autonomous Teacher/worktrees/g4r-packet-final/artifacts/review-packet-g4r-v2-d33e0aabd1714a486325b745c436cb59855d6539`；`frozen_utc=2026-11-20T17:22:37Z` |
| Packet v2 三 SHA | tree `4300a7c67a031136cd52f46b44d325db7a5dd14df82f409d25d6a2247737c1f6`；manifest `fe45d7602bd7a115cfdc3dd3a85e889c0f7b4fa642c03a54717c06f0bcf403a9`（sha256 实测一致）；hashes `e7a67c77b8e213fac32cb4aabeae56075dcf4982c0281479fae25cca1c4bdddb`（sha256 实测一致） |
| Packet v2 计数/矩阵 | 43 files / 0 symlink / payload 40 / hashes 41；矩阵 sha256 `741d7d5598cb9357c9ec9126ebcc277d504af93c0bc591af0d0c395b303d1382`（= 仓库 `docs/Autonomous_Teacher_M0_G4R_Test_Evidence_Matrix_v1.0.csv` 实测同值） |
| 最终 Stage | `stage-20261120T165407Z`：manifest `cc7ccb61bc4df76675b14e1f73bdd9209d3a13eeda7e79193e913ea284874d03`；tree `933f2c07a6c79415183a4d3f1db1ba19249b95d96ee88334bd43e71dd40d3882`；trusted `f10053d4107170b0b53362dbc9d1c0120d07dd7ee35339a315749de4b3431add`；candidate `131ab68e10f25d4aa893348754100c0fb0e221059b3fa79e3f7be9547c219006`；base/head=`d33e0aa`；旧 Stage `82e10c6f…` 仅 HISTORICAL |
| 环境 | rootfs `25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0`（清理后）；deps `e07729d7…`；DSH runtime `1cc41d5a…`（0.2.2-rc.2）；adapter JS `2cb42461…`；Node `v22.23.2`；Podman `4.9.3`；Python `3.11.15` |
| Packet 独占窗口 | `2026-11-20T17:05:50Z–17:08:20Z`（T0/T1 rootfs 均 `25491e45…`、`T0_T1_equal=true`、`frozen_rootfs_unchanged=true`） |

> **引用约定**：本 errata 位于 `worktrees/g4r-errata` 分支 `docs/g4r-review-errata` @ `9768933`；Packet v2
> 位于 gitignored 的其它 worktree（只读引用，未复制、未改写）。行号/路径按当前树。

## 1. 裁定归档（Reviewer 最终裁定，逐字归档）

```text
PASS_FOR_G4R_NO_KEY_REMEDIATION_SCOPE
P0 = 0
P1 = 1（环境/证据完整性，非源码）→ RESOLVED_WITH_LIMITATIONS（记录保留）
P2 = 2 open（P2-01、P2-02）+ 1 CLOSED（P2-03）
```

- **明确不成立**：`PASS_FOR_G4R_NO_KEY_SCOPE_WITH_B03_RUNTIME_SNAPSHOT_VERIFIED` —— B03/E5-P04 仍
  `UNVERIFIED`；R3 的 `API_AVAILABLE` 只是 L1 机制可行，不构成权威 merged registry。
- **范围限制**：仅覆盖本机、无 Key、无真实 Provider/HTTP/TCP 的 G4-R 修复/工程范围。**不表示**：
  E5-PreLive Full PASS、E5-P04 PASS、B03 关闭、G4-H1/H2 已部署、G5 已获批、G6 GO、M0 GO、Live/生产安全。
- **依据摘要**：R1/R2/R3/R4 no-key 修复与 L1-HOST 负例经 Reviewer 自建探针/独立解析复验成立（R-REV2 PASS）；
  delta `5bf9b8b→d33e0aa` 为 test/tooling-only（4 文件、`src/` 零 diff、collection 1420/exit0）；
  R-REV5 最终 Packet 由 Reviewer 自建独立遍历器复算一致且 11/11 mutation 注入全部检出；P1 rootfs 已缓解并
  写入 limitations。

## 2. P0/P1/P2 逐项归档

| ID | 级别 | 内容 | 归档状态 | 处置要求 |
|---|---|---|---|---|
| P0 | — | 无 | `0` | — |
| P1-01 | P1（环境/证据完整性） | 冻结 rootfs 工件被并发 OCI 运行污染：根因是直接 `podman run --rootfs artifacts/security/rootfs`（指向冻结工件）；两次污染窗口 `16:52–16:53Z`、`16:55–16:59Z`；漂移哈希 `0340fb78…`/`a6737150…`/`e1a8fcf9…`（冻结 `25491e45…`）；`16:54:07Z` Stage 构建时仍 canonical；Integration Stage 重建 `16:52` 已 fail-closed 检出（`rootfs is not canonical before build`） | **`RESOLVED_WITH_LIMITATIONS`**（清理 `17:01:49Z` 恢复 `25491e45…`；Reviewer `17:26:37Z` 独立复算一致；Packet 绑定独占窗口；R-REV1 PASS with env limitation） | 流程强制：**禁止**对冻结 rootfs 直接 `--rootfs`；OCI/L2 使用 rootfs 可写副本并在独占窗口串行；不得写“全程 NO_DRIFT” |
| P2-01 | P2（evidence integrity，低） | `_read_use_record` 校验 schema/epoch 但不校验 body `authorization_id` == 路径 `sha256(id)`；Reviewer 探针实测“schema 合法但属其它授权 id 的记录”判 `AUTHORIZATION_REPLAYED`（保守拒绝，无第二成功） | **OPEN** | 无授权放宽；审计上错配记录与真实 replay 不可区分。建议读取时交叉校验 body id，不符 → `INVALID` |
| P2-02 | P2（scope gap） | production `src/` 内 `consume_execution_authorization()` **无 Controller/launcher 调用方**（仅测试/`scripts/g4` 探针），R1 修复为模块级；dispatch 前链路端到端单次授权强制未接线 | **OPEN** | 不得把模块级 PASS 外推 Live 链 PASS；G4-H1 前需接线并 L2 复验 |
| P2-03 | P2 | delta 前 `tests/g4r_packet/support.py` 裸 import 与 `g4_f2/support.py` 名称遮蔽（2 collection error）；builder 拒绝 40-hex git commit | **`CLOSED`**（delta `d33e0aa` 修复；Reviewer 独立复验：collection 1420/exit0、builder/verifier identity 三字段、delta ruff 通过；最终 Packet 构建/校验使用 40-hex impl id 成功） | 已关闭；不重开 |
| 观察-1 | 文档 nit | `deadline_before_controller` 在 `controller_entered=true` 时携带真实 `dispatch_seq=1`（命名略易误读） | 记录 | 可选改名/加注；无安全语义问题 |
| 观察-2 | 设计边界 | `nlink>2` 拒绝、`nlink==2` 容忍；`AUTHORIZATION_USE_LOG_DURABILITY_UNKNOWN` fail-closed 码当前无 Controller 消费方 | 记录 | 接线时须映射为“不确定/不发送” |

## 3. REV-01..08 最终状态（以 Reviewer 报告为准）与 Packet 快照差异

| Case | 对象 | 最终状态（Reviewer） | 说明 |
|---|---|---|---|
| `R-REV1` | 证据链/SHA/delta/冻结保护/加载身份 | **PASS（with env limitation）** | delta test/tooling-only 成立；受保护零 diff；v1 Packet 未改；加载 6/6 + Stage trusted 52/52 == git `d33e0aa`；清理后 rootfs/deps/runtime/stage 全部一致（P1 已 `RESOLVED_WITH_LIMITATIONS`，不写“全程 NO_DRIFT”） |
| `R-REV2` | 单次授权并发/crash/腐败/fail-closed | **PASS（L1-HOST）** | Reviewer 自建探针 exit 0；附 P2-01 nit |
| `R-REV3` | 两层观测/recovery first_cause | **PARTIAL** | L1 代码 + 原始 JSONL 独立解析 PASS；L2/端到端接线 `UNVERIFIED`；P2-02 |
| `R-REV4` | Registry API/信任边界/config | **PARTIAL** | `API_AVAILABLE` 机制独立复现；权威性/B03/E5-P04 `UNVERIFIED`；config 未改 |
| `R-REV5` | 最终 Packet v2 独立遍历 + 变异注入 | **PASS** | 43/0/40/41、tree `4300a7c6…`、manifest `fe45d760…`、hashes `e7a67c77…` 独立复算一致；11/11 mutation 检出；原 Packet 不变；v1 未改写 |
| `R-REV6` | 真实双 Principal/DSH 两轮 + Replay | **`NOT_RUN`** | 环境/时间不允许；Owner RG-05 亦 `NOT_RUN`；Packet 内 L2 计数为 Integration 产出，Reviewer 未独立重跑 |
| `R-REV7` | 无 Key / 恒 BLOCKED | **PASS（本机无 Key 范围）** | LiveGate/run_live/CLI/Adapter/env/新增代码负例 |
| `R-REV8` | Host/OCI/Node/Ruff/Scanner | **PARTIAL** | 定向 69 passed+1 skip / packet+f2 41+1 / unit 396 / ruff/scanner PASS；OCI/Node/Host full `NOT_RUN` |

> **Packet 快照差异（重要）**：冻结 Packet v2 内矩阵（`matrix/G4R_Test_Evidence_Matrix.csv`，sha256
> `741d7d55…` = 仓库矩阵同值）的 `REV-01..08` 行仍为 **`NOT_RUN`**——这是 **Packet 冻结时点（17:22:37Z，
> 早于独立 Review）** 的事实快照，不是评审结论错误。本 errata 是 **post-packet、append-only 追加**：
> **不重打包 Packet、不改矩阵字节**；REV 最终状态以上表（Reviewer 报告 §10）为准。
> 复核命令示例：`sha256sum docs/REVIEW_G4R_INDEPENDENT.md` 必须仍为
> `0599856aec247d0834a88a8967db81bd68965578a35eed37dbdf45322068446c`。

## 4. P1 环境事件摘要（记录保留，不得写“全程 NO_DRIFT”）

- **漂移链（冻结值 `25491e45…`）**：`25491e45 → 0340fb78（16:52–16:53）→ 25491e45（16:53:34 清理）→
  a6737150/e1a8fcf9（16:55–16:59）→ clean 25491e45（17:01:49 清理恢复；Reviewer 17:26:37Z 独立复算）`。
- **Stage 时序**：`stage-20261120T165407Z`（最终 Stage）在 `16:54:07Z` **canonical 时**构建成功；Integration
  Stage 重建于 `16:52` 已 fail-closed 检出 `rootfs is not canonical before build`（base=`d33e0aa`）。
- **独占窗口**：最终 Stage/Packet 的环境绑定来自 `17:05:50–17:08:20Z` 独占窗口；T0/T1 rootfs 均
  `25491e45…`、`T0_T1_equal=true`、OCI 使用 rootfs **可写副本**且 `frozen_rootfs_unchanged=true`。
- **流程修复结论（保留为部署/集成要求）**：
  1) **禁止**再对冻结 rootfs 直接 `podman --rootfs`；一律 `cp -a` 可写副本运行 OCI；
  2) L2/OCI 必须在独占窗口**串行**，前后采集 canonical 快照；失败即 fail-closed 停止；
  3) 任何引用 rootfs 的 Stage/Packet 必须引用清理后/独占窗口身份，并在 README/limitations 记录 drift/cleanup；
  4) **不得**写“全程 NO_DRIFT”，也不得外推生产环境或无独占窗口的持续一致性。
- **归因**：该缺陷属 R5 集成/OCI 流程（冻结工件可被 podman `--rootfs` 直接写），**不是** `d33e0aa/src`
  缺陷；E5 Full/真实部署前仍需按上述流程要求复核。

## 5. R-REV6 / L2 真实 DSH 范围的如实登记

- **`R-REV6`（真实双 Principal / DSH Tool 两轮 + Replay）= `NOT_RUN` / `UNVERIFIED`**
  （`BLOCKED_NEEDS_ENVIRONMENT`）。Owner R3 自报 RG-05 two-turn 亦 `NOT_RUN`；Reviewer 仅独立执行了
  `observe` / `attack-late-extra-bash` 两个 registry probe 模式，**未跑** two-turn/replay 与 usage/hash 逐字段对账。
- Packet 内的 L2 计数（独占窗口：f2 Echo 1 / Tool 2；f5 3/3；OCI 1052 passed 等）是 **Integration 产出**，
  Reviewer 仅作为 Packet 内容独立读取核对，**不据此判 PASS**；`R-REV3` 的 L2 与 timeout/revocation/in-flight
  容器内对账同样未由 Reviewer 复跑（`PARTIAL` + P2-02）。
- 任何“真实 DSH two-turn/Replay 已 PASS”“崩溃/掉电/跨 FS 已穷举”之类表述均不成立。

## 6. 维护者待决事项（全部未签核；Agent 不代签）

依据 `docs/M0_G4R_HUMAN_HANDOFF.md`（`M0-G4R-HUMAN-HANDOFF-v1`，sha256 实测
`c14862ca99ce99db568ebd05a5f288b3cbb666f3a03c423b0ec6914c5e5de2fd`）：

| 决策来源 | 内容 | 状态 | 维护者决定（空白） |
|---|---|---|---|
| `D-01` | 接受/不接受 G4-R 裁定与范围 | `PENDING_HUMAN_ACTION` | `[ ] ACCEPT [ ] PARTIAL [ ] BLOCK …` |
| `D-02` | 最终 Packet v2 是否采用（v1 保持不可变只读；拒绝静默扩 deselect/未哈希文件） | 同上 | `__________` |
| `D-03` | P2-03/04/05/06 修复签收（以独立复测为准） | 同上（P2-03 已由 Reviewer CLOSED；其余按 Reviewer 报告） | `__________` |
| `D-04` | B03 / E5-P04 Registry 残余（`UNVERIFIED` + per-dispatch 白名单补偿控制，或要求权威导出） | 同上 | `__________` |
| `D-05` | P2-RUN-IDENTITY / USERNS / DISK | 同上 | `__________` |
| `D-06` | F4-R1 / F5-R6 / F1-R4 / F2-R5 / B07 残余 | 同上 | `__________` |
| `D-07` | R5-01..03（F4-06 candidate crash + live Controller）`UNVERIFIED` | 同上 | `__________` |
| `D-08` | 环境漂移/清理事件确认（16:52–16:59Z、清理恢复、Stage fail-closed、副本政策；不得宣称全程 NO_DRIFT） | 同上 | `__________` |
| `D-09` | OCI deselect 差异（43→69，含 26 explicit `tests/integration/g4r_auth`）签收 | 同上 | `__________` |
| `D-10` | 历史 junit 误覆盖事件知悉/接受（已从 Packet 原字节恢复） | 同上 | `__________` |
| `D-11` | G4-H-01..06 人工项（含人类信任根/Key Broker/Egress/Watchdog） | 同上 | `__________` |
| `D-12` | G5 bounded real request 单次授权 | 同上 | `__________` |
| `D-13` | 其它开放风险（`M0_G4R_FINDINGS_AND_DISPOSITION.md` §4） | 同上 | `__________` |
| 本次新增 | **P2-01**（`authorization_id` 交叉校验）与 **P2-02**（consume 端到端接线）处置；B03/E5-P04；正式受信部署（G4-H1）与 G5 | 全部未签核 | `__________` |

> 以上全部 `PENDING_HUMAN_ACTION`；Agent 只登记建议，**不代签任何 ACCEPT/APPROVED/AUTHORIZED**。

## 7. 外推禁止项与状态常量

**不得据此宣称**：`E5_PRELIVE_FULL PASS`、`E5-P04 PASS`、`B03 关闭`、`G4-H1/H2 已部署`、`G5 已获批`、
`G6 GO`、`M0 GO`、生产安全、真实 Provider/TLS/账单/额度已验证、真实 DSH two-turn/Replay PASS。
状态常量保持：`G4-H=NOT_AUTHORIZED`、`G5=BLOCKED`、`G6=NOT_RUN`、`LiveGate=BLOCKED`、
`M0=DECISION_PENDING`、`E5_PRELIVE_FULL=BLOCKED_PENDING_HUMAN_DEPLOYMENT`。

## 8. 证据索引与复验

| 内容 | 路径/命令 |
|---|---|
| Reviewer 报告（原字节，禁改） | `docs/REVIEW_G4R_INDEPENDENT.md`；`sha256sum` = `0599856a…446c`；review 提交 `e72255d` |
| Reviewer 证据（43 文件） | `docs/g4r_review_evidence/`（`r_rev1_*`…`r_rev8_*`） |
| 自建探针（2） | `scripts/g4r_review/r_rev2_race_probe.py`、`r_rev5_packet_verifier.py` |
| Packet v2 | 仓库外 gitignored 路径（见 §0）；`sha256sum manifest.json hashes.sha256` 实测与 §0 一致；43 files/0 symlink/payload 40/hashes 41 |
| Stage 身份 | `artifacts/g4r/logs/stage-build-final-20261120T165407Z.log`；Packet `stage` 段四 SHA（见 §0） |
| 环境/漂移链 | Packet `README.md`/`manifest.limitations`；`artifacts/g4r/integration/integration-env.json` |
| 人工交接/决策 | `docs/M0_G4R_HUMAN_HANDOFF.md`（`D-01..D-13`）；`docs/M0_G4R_FINDINGS_AND_DISPOSITION.md` §4 |
| 矩阵 | `docs/Autonomous_Teacher_M0_G4R_Test_Evidence_Matrix_v1.0.csv`（sha256 `741d7d55…`；REV 行仍 `NOT_RUN`，见 §3） |

## 9. append-only 版本记录

| 版本 | UTC | 内容 |
|---|---|---|
| v1 | 2026-11-20T17:30Z | 初次归档：最终裁定/P0/P1/P2、REV-01..08 最终状态与 Packet 快照差异、P1 环境事件摘要、R-REV6 NOT_RUN、维护者待决与禁止外推 |

> 后续更正只在文件末尾追加新小节，不改写既有字节；`docs/REVIEW_G4R_INDEPENDENT.md` 永不由本 errata 修改。

## 10. STOP / 不主张

- 本文件**不主张**：G4-R 裁定升级、E5/ B03/G4-H/G5/G6/M0 任何门通过、真实部署或 Live；不主张 P1 被“修复”
  （仅 `RESOLVED_WITH_LIMITATIONS`）；不主张 R-REV6/L2 已执行；不主张 Packet 内 REV 行已是最终状态（它们仍为
  `NOT_RUN` 快照，最终状态见 §3）。
- **STOP**：等待维护者按 `M0_G4R_HUMAN_HANDOFF.md` 与本文 §6 决策；Agent 不代签、不推进下一门。
