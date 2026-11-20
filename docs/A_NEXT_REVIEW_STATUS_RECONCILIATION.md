# A-NEXT — 65 行 Review 状态对账（append-only，A0-02 / A-PR0）

- **文档 ID**：`A-NEXT-REVIEW-STATUS-RECONCILIATION-v1`
- **生成者**：A-PR0 Implementer-Docs（子 Agent；非 Lead、非 Independent Reviewer）
- **生成时间（UTC）**：`2026-11-20T19:36Z`–`19:52Z`
- **对账对象**：
  - 冻结矩阵：`docs/Autonomous_Teacher_M0_G4R_Test_Evidence_Matrix_v1.0.csv`（**65 数据行 + header**，
    sha256 实测 `741d7d5598cb9357c9ec9126ebcc277d504af93c0bc591af0d0c395b303d1382`；冻结时点
    = Packet v2 `frozen_utc 2026-11-20T17:22:37Z`，早于独立 Review）
  - Reviewer 终态：`docs/REVIEW_G4R_INDEPENDENT.md`（`M0-G4R-INDEPENDENT-REVIEW-v1`，sha256 实测
    `0599856aec247d0834a88a8967db81bd68965578a35eed37dbdf45322068446c`，review 提交 `e72255d`）
  - 冻结 impl：`d33e0aabd1714a486325b745c436cb59855d6539`；本分支起点 `work/g4r=fd1d3a6…`
- **性质**：**append-only 对账**。本文件是 post-Packet 追加，**不重打包 Packet、不改冻结 CSV / 旧 Packet /
  旧 Review 任何字节**（§6 以 `git`/`sha256` 证明）。不是 PASS、不是授权、不是 Reviewer 结论替代。
- **状态常量（未变）**：`LiveGate=BLOCKED`、`G4-H=NOT_AUTHORIZED`、`G5=BLOCKED`、`G6=NOT_RUN`、
  `M0=DECISION_PENDING`、`E5_PRELIVE_FULL=BLOCKED_PENDING_HUMAN_DEPLOYMENT`。

## 0. 方法与状态词汇（防止“把未审当 PASS”）

| 列 | 含义 |
|---|---|
| `frozen` | 冻结 CSV 的 `status` 列原值（Packet 冻结时点快照；含 Owner 自报与初始 `NOT_RUN`） |
| `reviewer final` | 从 Reviewer 报告映射的终态；仅当 Reviewer **明确覆盖该行为**时映射，否则为 `NO_DIRECT`（不升级、不降级，保留 frozen 原值的“未终审”语义） |
| `reviewer ran` | Reviewer 是否亲自执行：`YES`（自建/重跑）/ `PARTIAL`（读代码或原始文件，未重跑执行面）/ `NO` / `N/A`（人类项） |
| `NO_DIRECT` | Reviewer 报告未对该行作独立裁定；**不得**把 frozen `PASS` 当作 Reviewer PASS，也不得改成 NOT_RUN |
| 评级 | Reviewer 行级状态取自 §1（R-REV1）、§2（R-REV2）、§3（R-REV3）、§4（R-REV4）、§5（R-REV7）、§6（R-REV8）、§7（R-REV5）、§8（R-REV6） |

**映射规则（逐 phase）**：

| phase | 映射规则 | 说明 |
|---|---|---|
| `R0-01..05` | `R-REV1`（PASS with env limitation）/ `R-REV7`（no-key）/ `NO_DIRECT`（R0-05 治理项） | Reviewer 独立复算环境/身份/冻结件；P1 限制保留 |
| `R1-01..06,08` | `R-REV2` PASS（L1-HOST） | Reviewer 自建探针覆盖线程/进程/epoch/腐败/crash/dir-fsync/FS 负例 |
| `R1-07` | `NO_DIRECT` | Reviewer 未重跑 G4-A a12 全量；不得升级 |
| `R2-01..09` | `R-REV3` PARTIAL | L1 代码 + Owner 原始 JSONL 独立解析 PASS；L2-REAL-DSH `NOT_RUN/UNVERIFIED` |
| `RG-*` | `R-REV4` PARTIAL / `UNVERIFIED`（RG-07/08）/ `NOT_RUN`（RG-05/09/10/12）/ `NO_DIRECT`（RG-03） | 机制独立复现；权威 registry/B03/E5-P04 `UNVERIFIED` |
| `R4-01..06,12,13` | `R-REV5` PASS | 自建遍历器 + 11/11 mutation；frozen `PARTIAL` 升级为 **限定 Packet 完整性** PASS |
| `R4-07,R4-09,R4-10` | `NO_DIRECT` / `NOT_RUN` | Reviewer 未重跑 A12 / Host full / OCI；frozen PASS 不升级 |
| `R4-08` | `R-REV8` PASS | ruff 定向/全仓检查 |
| `R4-11` | `R-REV7` PASS（no-key） | LiveGate/CLI/run_live/Adapter 负例 |
| `R5-01..03` | `R-REV6` `NOT_RUN` | 真实 DSH two-turn/replay 未执行；frozen `UNVERIFIED` 保留、不升级 |
| `REV-01..08` | 逐一对应 `R-REV1..R-REV8` | 见 §2 表 |
| `G4-H-01..06` | `N/A (HUMAN)` | 人类授权/部署项；Reviewer 不裁定；`BLOCKED` 不变 |

## 1. 总览计数（脚本按 CSV 逐行统计，非人工估算）

| 维度 | PASS | PARTIAL | NOT_RUN | UNVERIFIED | BLOCKED | 其他 | 合计 |
|---|---|---|---|---|---|---|---|
| **frozen CSV** | **29** | **14** | **12** | **4** | **6** | — | **65** |
| **reviewer mapped** | **25**（含 `PASS (env limitation)`/`PASS (no-key)`/`PASS (L1-HOST)`） | **18** | **10** | **2** | — | `NO_DIRECT` 4 + `N/A` 6 | **65** |

**frozen → reviewer 状态迁移（脚本统计）**：

```text
PASS       -> PASS 13 | PARTIAL 10 | NO_DIRECT 4 | NOT_RUN 2
PARTIAL    -> PASS 8  | PARTIAL 5  | UNVERIFIED 1
NOT_RUN    -> PASS 4  | PARTIAL 3  | NOT_RUN 5
UNVERIFIED -> UNVERIFIED 1 | NOT_RUN 3
BLOCKED    -> N/A 6
```

> 解读：frozen PASS 中有 10 行被 Reviewer 降为 PARTIAL（主要是 R2 L2 未重跑）、2 行降为 NOT_RUN
> （Host full / OCI 未由 Reviewer 执行）、4 行 `NO_DIRECT`；**任何“最终矩阵全 PASS”表述均不成立**。

## 2. 65 行逐 case_id 对账表

| case_id | frozen | reviewer final | reviewer ran | reviewer 证据（SHA 见 §5） |
|---|---|---|---|---|
| R0-01 | PASS | PASS (env limitation) | YES | r_rev1_canonical_env* |
| R0-02 | PASS | PASS (env limitation) | YES | r_rev1_canonical_env* |
| R0-03 | PASS | PASS (no-key) | YES | r_rev7_env_scan |
| R0-04 | PASS | PASS (env limitation) | YES | r_rev1_canonical_env* |
| R0-05 | PASS | NO_DIRECT | NO | — |
| R1-01 | PASS | PASS (L1-HOST) | YES | r_rev2_race_probe_final |
| R1-02 | PASS | PASS (L1-HOST) | YES | r_rev2_race_probe_final |
| R1-03 | PASS | PASS (L1-HOST) | YES | r_rev2_race_probe_final |
| R1-04 | PASS | PASS (L1-HOST) | YES | r_rev2_race_probe_final |
| R1-05 | PASS | PASS (L1-HOST) | YES | r_rev2_race_probe_final |
| R1-06 | PASS | PASS (L1-HOST) | YES | r_rev2_race_probe_final |
| R1-07 | PASS | NO_DIRECT | NO | — |
| R1-08 | PASS | PASS (L1-HOST) | YES | r_rev2_race_probe_final |
| R2-01 | PASS | PARTIAL | NO | （代码+Owner JSONL） |
| R2-02 | PASS | PARTIAL | NO | （代码+Owner JSONL） |
| R2-03 | PASS | PARTIAL | NO | （代码+Owner JSONL） |
| R2-04 | PASS | PARTIAL | NO | （代码+Owner JSONL） |
| R2-05 | PASS | PARTIAL | NO | （代码+Owner JSONL） |
| R2-06 | PASS | PARTIAL | NO | （代码+Owner JSONL） |
| R2-07 | PASS | PARTIAL | NO | （代码+Owner JSONL） |
| R2-08 | PASS | PARTIAL | NO | （代码+Owner JSONL） |
| R2-09 | PASS | PARTIAL | NO | （代码+Owner JSONL） |
| RG-00 | PASS | PARTIAL | YES | r_rev4_registry_observe2 |
| RG-01 | PARTIAL | PARTIAL | YES | r_rev4_registry_observe2 |
| RG-02 | PARTIAL | PARTIAL | YES | r_rev4_registry_observe2 |
| RG-03 | PASS | NO_DIRECT | NO | r_rev4_registry_observe2 |
| RG-04 | PARTIAL | PARTIAL | YES | r_rev4_registry_observe2 |
| RG-05 | NOT_RUN | NOT_RUN | NO | r_rev4_registry_observe2 |
| RG-06 | PARTIAL | PARTIAL | YES | r_rev4_registry_observe2 |
| RG-07 | PARTIAL | UNVERIFIED | PARTIAL | r_rev4_registry_attack |
| RG-08 | UNVERIFIED | UNVERIFIED | PARTIAL | r_rev4_registry_attack |
| RG-09 | NOT_RUN | NOT_RUN | NO | r_rev4_registry_observe2 |
| RG-10 | NOT_RUN | NOT_RUN | NO | r_rev4_registry_observe2 |
| RG-11 | PARTIAL | PARTIAL | YES | r_rev4_registry_observe2 |
| RG-12 | NOT_RUN | NOT_RUN | NO | r_rev4_registry_observe2 |
| R4-01 | PARTIAL | PASS | YES | r_rev5_packet_verify |
| R4-02 | PARTIAL | PASS | YES | r_rev5_packet_verify |
| R4-03 | PARTIAL | PASS | YES | r_rev5_packet_verify |
| R4-04 | PARTIAL | PASS | YES | r_rev5_packet_verify |
| R4-05 | PARTIAL | PASS | YES | r_rev5_packet_verify |
| R4-06 | PARTIAL | PASS | YES | r_rev5_packet_verify |
| R4-07 | PASS | NO_DIRECT | NO | — |
| R4-08 | PASS | PASS | YES | r_rev8_ruff_scope |
| R4-09 | PASS | NOT_RUN | NO | r_rev8_g4r_targeted_final |
| R4-10 | PASS | NOT_RUN | NO | r_rev8_g4r_targeted_final |
| R4-11 | PASS | PASS (no-key) | YES | r_rev7_livegate |
| R4-12 | PARTIAL | PASS | YES | r_rev5_packet_verify |
| R4-13 | PARTIAL | PASS | YES | r_rev5_packet_verify |
| R5-01 | UNVERIFIED | NOT_RUN | NO | （未执行） |
| R5-02 | UNVERIFIED | NOT_RUN | NO | （未执行） |
| R5-03 | UNVERIFIED | NOT_RUN | NO | （未执行） |
| REV-01 | NOT_RUN | PASS (env limitation) | YES | r_rev1_* |
| REV-02 | NOT_RUN | PASS (L1-HOST) | YES | r_rev2_race_probe_final |
| REV-03 | NOT_RUN | PARTIAL | NO | （代码+原始JSONL） |
| REV-04 | NOT_RUN | PARTIAL | YES | r_rev4_registry_* |
| REV-05 | NOT_RUN | PASS | YES | r_rev5_packet_verify |
| REV-06 | NOT_RUN | NOT_RUN | NO | （未执行） |
| REV-07 | NOT_RUN | PASS (no-key) | YES | r_rev7_* |
| REV-08 | NOT_RUN | PARTIAL | YES | r_rev8_* |
| G4-H-01 | BLOCKED | N/A (HUMAN) | N/A | — |
| G4-H-02 | BLOCKED | N/A (HUMAN) | N/A | — |
| G4-H-03 | BLOCKED | N/A (HUMAN) | N/A | — |
| G4-H-04 | BLOCKED | N/A (HUMAN) | N/A | — |
| G4-H-05 | BLOCKED | N/A (HUMAN) | N/A | — |
| G4-H-06 | BLOCKED | N/A (HUMAN) | N/A | — |

> 表内 `reviewer 证据` 为 Reviewer 报告中的证据文件简称（`r_rev*` 位于 `docs/g4r_review_evidence/`，共 43 份）；
> `—` 表示该行无 Reviewer 直接证据（frozen 状态保留为 Owner 记录/未终审）。Owner `source_evidence` 多在
> gitignored `artifacts/g4r/**`（本树无该目录），**不能**在本树复核，属已知限制（§7）。

## 3. 关键状态变化解读（Reviewer 终态）

| 组 | frozen → reviewer | 依据 |
|---|---|---|
| `REV-01..08` | `NOT_RUN` → `PASS/PASS/PARTIAL/PARTIAL/PASS/NOT_RUN/PASS/PARTIAL` | Reviewer §10 矩阵；R-REV1/2/5/7 PASS，R-REV3/4/8 PARTIAL，R-REV6 NOT_RUN |
| `R4-01..06`（Packet v2 全树/mutation） | `PARTIAL` → `PASS` | R-REV5 自建遍历器：43/0/40/41、tree `4300a7c6…`、manifest `fe45d760…`、hashes `e7a67c77…`、11/11 mutation 检出；**限定 Packet 完整性**，不等于实现 PASS |
| `R4-12/13`（路径改/ livegate reasons） | `PARTIAL` → `PASS` | R-REV5 matrix/livegate 快照一致性复核 |
| `R4-09`（Host full）、`R4-10`（OCI） | `PASS` → `NOT_RUN` | R-REV8：Host full/OCI **NOT_RUN（Reviewer）**；OCI 另涉 P1 rootfs 漂移，Integration 计数不得冒充 |
| `R2-01..09`（恢复/观测） | `PASS` → `PARTIAL` | R-REV3：L1 代码/原始文件 PASS；L2/端到端 `UNVERIFIED`（P2-02） |
| `R5-01..03`（candidate crash 组合） | `UNVERIFIED` → `NOT_RUN` | R-REV6 `NOT_RUN`；不升级、不伪造 |
| `RG-05/09/10/12` | `NOT_RUN` → `NOT_RUN` | R-REV4 明确仍 `NOT_RUN` |
| `RG-07` | `PARTIAL` → `UNVERIFIED` | R-REV4：无权威可信通道；RG-05/07/08/12 仍 UNVERIFIED/NOT_RUN |
| `R1-07`（G4-A a12）、`R4-07`（A12 稳定性） | `PASS` → `NO_DIRECT` | Reviewer 未重跑 g4_a/A12；R-REV2 只覆盖机制子集，不能替代 |
| `G4-H-01..06` | `BLOCKED` → `N/A (HUMAN)` | 人类授权/部署项，Reviewer 不裁定；`BLOCKED` 不变 |

**Reviewer 最终裁定（引用，不改造）**：`PASS_FOR_G4R_NO_KEY_REMEDIATION_SCOPE`；
`P0=0`、`P1=1`（rootfs 环境类 → `RESOLVED_WITH_LIMITATIONS`）、`P2=2 open（P2-01/P2-02）+ P2-03 CLOSED`；
`B03/E5-P04 = UNVERIFIED`；`R-REV6 = NOT_RUN`。**不得**写成 E5 Full/G4-H/G5/G6/M0 通过。

## 4. 证据 SHA（实测；供独立复核）

| 对象 | 路径 | sha256 |
|---|---|---|
| 冻结 65 行矩阵 | `docs/Autonomous_Teacher_M0_G4R_Test_Evidence_Matrix_v1.0.csv` | `741d7d5598cb9357c9ec9126ebcc277d504af93c0bc591af0d0c395b303d1382` |
| Reviewer 报告 | `docs/REVIEW_G4R_INDEPENDENT.md` | `0599856aec247d0834a88a8967db81bd68965578a35eed37dbdf45322068446c` |
| Reviewer 证据目录（43 文件）清单摘要 | `docs/g4r_review_evidence/`（`sha256sum * \| sort` 后再 sha256） | `8326e4ca4c6f79c0ebf9e73edbf2db87dc982901207bd97935c97dd72fc3a02a` |
| R-REV1 证据链/受保护 | `docs/g4r_review_evidence/r_rev1_delta_and_protected_final.log` | `456f047182ca4547588eaab0bddfa1be46e33d9ae70d45f5ada56c85235453d9` |
| R-REV2 并发探针日志/JSON | `docs/g4r_review_evidence/r_rev2_race_probe_final.log` / `.json` | `e6f26d6768589e6a76fa81cc52bd239b8f517ef0b886b41b3e8220f9690a34c1` / `017adc4e77d09fd1ad416b08c28d5a728b4c86b3caf884e4c18464a73f3bec11` |
| R-REV4 observe/attack | `docs/g4r_review_evidence/r_rev4_registry_observe2.summary.json` / `r_rev4_registry_attack.summary.json` | `4b47d5777dd288cce18d90139b4ba9d49dd5dc0618d33dbd37f70a633f459920` / `01adcf5fb629facd21e4b13e06af96a6d062b27b20c3acd8e06be32934b798c2` |
| R-REV5 Packet 验证 | `docs/g4r_review_evidence/r_rev5_packet_verify.json` / `.log` | `42c6eaec1f38db721fd9af8afec8fe2e7f5acd383c090dac73d61aae14e9caa2` / `adeefbfebdaefeb93976cc69a58450520ed98b5e0ff6a4df7fb7cb0b27d5de5e` |
| R-REV7 LiveGate | `docs/g4r_review_evidence/r_rev7_livegate.log` | `823c0105c81cb23f30c81ead1580fc4836ee3c3280985c90aa5baf06d49e213f` |
| R-REV8 定向 | `docs/g4r_review_evidence/r_rev8_g4r_targeted_final.log` | `87999af3ae745a741a40a8c2c37d97e084e8601baf79400b862ab18dc07b6f86` |
| Packet v2 三 SHA | tree / manifest / hashes | `4300a7c6…37c1f6` / `fe45d7602bd7a115cfdc3dd3a85e889c0f7b4fa642c03a54717c06f0bcf403a9`（manifest 文件 sha256 实测）/ `e7a67c77b8e213fac32cb4aabeae56075dcf4982c0281479fae25cca1c4bdddb`（hashes 文件 sha256 实测） |
| Final Stage 四 SHA | manifest / tree / trusted / candidate | `cc7ccb61…` / `933f2c07…` / `f10053d4…` / `131ab68e…`（Reviewer §1.4/§7 复算） |

> 完整性：`docs/g4r_review_evidence/` **43 个文件（`find -type f` 实测）**，与 Reviewer 报告登记一致；
> 交接背景写“45 份”，以实测 43 为准（差异原因未由本 Agent 追查，记录为 `NOTE`）。

## 5. 冻结字节未改证明（append-only）

```bash
cd "/root/Autonomous Teacher/worktrees/a-next-baseline"
# A-PR0 提交后：只允许新增 docs/A_NEXT_*.md；以下应为空
git diff --name-only fd1d3a6..HEAD -- \
  docs/Autonomous_Teacher_M0_G4R_Test_Evidence_Matrix_v1.0.csv \
  docs/REVIEW_G4R_INDEPENDENT.md docs/M0_G4R_REVIEW_ERRATA.md \
  docs/g4r_review_evidence src/autoteacher_m0/security/authorization.py \
  src/autoteacher_m0/bridge/controller.py
git hash-object docs/Autonomous_Teacher_M0_G4R_Test_Evidence_Matrix_v1.0.csv
# 预期 = 6fe675536a9277ae1fe07bf4e99b3c3f48052230（HEAD 中的 blob）
sha256sum docs/Autonomous_Teacher_M0_G4R_Test_Evidence_Matrix_v1.0.csv   # = 741d7d55…
sha256sum docs/REVIEW_G4R_INDEPENDENT.md                                 # = 0599856a…
```

**Packet（仓库外 gitignored；本轮只读）**：

| Packet | manifest sha256 | hashes sha256 | 说明 |
|---|---|---|---|
| v1（G4-F，未改写） | `4aed2a923ea3fae52ed3eac9d0c5838077242ed32045804d687dcef703a1d7f2` | `421b07ae3ad0eac2d36c032cd384d252dfda4ac521e193577aed56fc60ca9d3d` | 与 Reviewer §1.3 登记一致 |
| v2（G4-R 最终包） | `fe45d7602bd7a115cfdc3dd3a85e889c0f7b4fa642c03a54717c06f0bcf403a9` | `e7a67c77b8e213fac32cb4aabeae56075dcf4982c0281479fae25cca1c4bdddb` | 与 Reviewer §7 登记一致；**不重打包** |

矩阵在 Packet 内的副本 sha = `741d7d55…`（Reviewer §7 复算），与本仓库 `docs/…csv` 同值；
冻结 CSV 内的 `REV-01..08` 行仍为 `NOT_RUN`（Packet 冻结早于 Review），**本文件只作 append-only 对照**。

## 6. append-only 规则与版本记录

- 本文件 v1 写入后，任何后续更正**只在末尾追加**，不改既有字节；冻结 CSV/Packet/旧 Review 永不由本文件修改。
- 若后续 Reviewer/维护者更新终态，追加 `v2` 并在新小节记录 `changed_at / who / old→new / evidence sha`。

| 版本 | UTC | 内容 |
|---|---|---|
| v1 | 2026-11-20T19:52Z | 初次对账：65/65 行（frozen→reviewer final→evidence→ran）、计数、REV/关键变化、证据 SHA、冻结字节未改证明 |

## 7. 残余/未验证与 STOP

1. Owner `artifacts/g4r/**` 证据不在本树（gitignored），本表对未由 Reviewer 覆盖的行只能引用 CSV 记录；
   独立复核需维护者提供精简证据包（交接 `AUDIT_REQUESTS.md` 的 `audit-index.json` 格式）。
2. Reviewer 未重跑：Host full、OCI、Node TAP、G4-A a12 全量、R2 L2、R-REV6 真实 DSH two-turn/replay。
3. P2-01/P2-02 OPEN；P1 rootfs 环境限制保留（`RESOLVED_WITH_LIMITATIONS`）；B03/E5-P04 `UNVERIFIED`。
4. 交接背景写“证据 45 份”，实测 43 份（`NOTE`，未追查差异；不影响 43 份均可哈希/引用）。
5. **STOP**：本文件不主张任何 PASS/门通过；终态以 Reviewer 报告为准，合并/部署/G5 决定属维护者。
