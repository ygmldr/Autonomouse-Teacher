# A-NEXT — Review 状态对账 V2 更正（append-only，Stage-2 batch-1）

- **文档 ID**：`A-NEXT-REVIEW-STATUS-RECONCILIATION-V2-ADDENDUM-v1`
- **记录者**：A-PR0 Implementer-Docs（子 Agent；非 Lead、非 Independent Reviewer）
- **时间（UTC）**：`2026-11-20T20:16Z`
- **性质**：**append-only v2 更正**。对象为已提交的 `docs/A_NEXT_REVIEW_STATUS_RECONCILIATION.md`
  （v1，commit `e1fa0b9`；文件 sha256 `81ecae3ca5fc4ec6a9628d53e22651989772e8cc24c2d41ab0bcf55f4d6ce59b`，
  git blob `5729eb740756475213470421b35e8efdf0754a53`）。**v1 字节不改**；本文件只追加更正。
- **依据（Reviewer 阶段 2 batch-1）**：`docs/A_NEXT_INDEPENDENT_REVIEW.md` @ commit `1b2558b`
  （文件 sha256 `a005ace4495d96c2b4befc524d56e9204d02390111575c9b1a4fb37591f2662f`；batch-1 主体见 `e6ee40f`，
  sha256 `d0b246d3797ada9869084ef4a6ffeb657d8f368f7bb681f762f2857de78e236a`）§8.1（`:526-536`）、§8.5（`:632-639`）。
- **Reviewer 结论**：A-PR0 docs = **PARTIAL**（数据/append-only/F-02 属实；2 行过度归因 PASS）；更正后经复核
  可升 PASS——**升 PASS 不是本文件可以自行宣称的**。
- **状态常量（未变）**：`LiveGate=BLOCKED`、`G4-H=NOT_AUTHORIZED`、`G5=BLOCKED`、`G6=NOT_RUN`、
  `M0=DECISION_PENDING`、`E5_PRELIVE_FULL=BLOCKED_PENDING_HUMAN_DEPLOYMENT`。

## 1. 被更正的两行（old → new；v1 原行保留为历史）

| case | v1 frozen（不改） | v1 reviewer（历史值，不改） | **V2 行级终态** | Reviewer 依据 | 证据 |
|---|---|---|---|---|---|
| `R4-05`（SQLite backup provenance） | `PARTIAL` | `PASS`（错误归因到 `r_rev5_packet_verify`） | **`PARTIAL`**：reviewer final = `NO_DIRECT`（无直接证据）；frozen `PARTIAL` 保留；provenance 未被验证 | `A_NEXT_INDEPENDENT_REVIEW.md:526-528`（“被映射为 PASS——无 Reviewer 直接证据…应改为 `NO_DIRECT`/`PARTIAL`（保留 frozen PARTIAL）并注明”） | `r_rev5_packet_verify.json` 字段不含 provenance；见 §2 |
| `R4-12`（Evidence path correction） | `PARTIAL` | `PASS`（同上，错误归因） | **`UNVERIFIED`**：reviewer final = `NO_DIRECT`；frozen `PARTIAL` 仅为 Owner 记录；path-correction 无 Reviewer 证据 | `A_NEXT_INDEPENDENT_REVIEW.md:529-532`（“R-REV5 verifier 证据 JSON 只有 `packet/status/expected_impl_sha/mutation_undetected/issues` 键，不含 path-correction 校验…不等于该行 PASS”） | 见 §2 |
| `R4-13`（LiveGate reason snapshot equality） | `PARTIAL` | `PASS` | **`PASS` 维持**（不变） | `A_NEXT_INDEPENDENT_REVIEW.md:532`（有 R-REV5 livegate 快照一致性支撑，保留 PASS 可接受） | R-REV5 §7 livegate 快照行 |

**更正口径说明（防止“过度更正”或“更正不足”）**：

- `R4-05`：R-REV5 覆盖了 SQLite 的“只读/immutable 打开 + quick_check”，**不覆盖备份来源 provenance**；
  故 reviewer 直接状态为 `NO_DIRECT`，行级终态采用 Reviewer 明确建议的 **`PARTIAL`**（frozen PARTIAL 保留）。
- `R4-12`：R-REV5 与 Reviewer 正文均未做“矩阵 evidence path 修正”验证（Reviewer 仅在 P2-02 观察中提到
  F2-07 旧路径缺失/实际路径存在，**不等于该行 PASS**）；frozen `PARTIAL` 是 Owner 记录，不是 Reviewer 结论
  → 行级终态取更严格的 **`UNVERIFIED`**。
- 其余 63 行**不改**；`REV-01..08`、`R4-01/02/03/04/06`、`R4-09/10` 等映射保持 v1 值（v1 表字节未动）。

## 2. Reviewer 证据字段核查（为什么两行不能算 PASS）

`docs/g4r_review_evidence/r_rev5_packet_verify.json`（sha256
`42c6eaec1f38db721fd9af8afec8fe2e7f5acd383c090dac73d61aae14e9caa2`）**顶层键实测恰为**：

```text
expected_impl_sha, issues, mutation_undetected, packet, status
值：expected_impl_sha=d33e0aabd1714a486325b745c436cb59855d6539
    issues=[]；mutation_undetected=[]；status=PASS
    packet=/root/Autonomous Teacher/worktrees/g4r-packet-final/artifacts/review-packet-g4r-v2-d33e0aabd1714a486325b745c436cb59855d6539
```

- **不存在** `provenance`、`backup_source`、`path_correction`、`matrix_paths` 等字段；也**不记录** R4-05 的
  “SQLite 备份是否来自一致快照/工作副本”或 R4-12 的“矩阵 evidence path 是否全部存在”。
- 对应日志：`r_rev5_packet_verify.log`（sha256 `adeefbfebdaefeb93976cc69a58450520ed98b5e0ff6a4df7fb7cb0b27d5de5e`）。
- 结论：v1 对 R4-05/R4-12 的 `PASS` 属**过度归因**（用 Packet 全树验证替代了两项独立验证）；更正后不得
  再以 R-REV5 作为这两行的 PASS 依据。Reviewer 报告 `:164-165` 亦明确 R4-05/R4-12/R4-13 “需 Stage-2 逐 ID 复核”。

## 3. 更正后汇总（行级；其余 63 行不变）

| 维度 | PASS | PARTIAL | NOT_RUN | UNVERIFIED | NO_DIRECT | N/A | 合计 |
|---|---|---|---|---|---|---|---|
| v1 映射（历史） | 25 | 18 | 10 | 2 | 4 | 6 | 65 |
| **V2 更正后** | **23** | **19** | **10** | **3** | **4** | **6** | **65** |

推导：`-2 PASS`（R4-05/R4-12）→ `+1 PARTIAL`（R4-05）+ `+1 UNVERIFIED`（R4-12）；其余不变。
**不得**写成“最终矩阵全 PASS”；`R2 L2 PARTIAL`、`R4-09/10 NOT_RUN`、`R5 NOT_RUN`、`G4-H N/A(HUMAN)` 等
保留不变。冻结 CSV 的 frozen 分布仍为 `29/14/12/4/6`（未改字节，仅行级 reviewer 映射更正）。

## 4. Stage-2 batch-1 条件式结论登记（便于集成后追踪）

来源：`docs/A_NEXT_INDEPENDENT_REVIEW.md:632-639`（§8.5 汇总）与 §8.2/§8.3/§8.4；`e6ee40f`。

| 对象 | 提交 SHA | Reviewer 裁定 | 允许集成 | 条件（必须满足后才能视为完成） |
|---|---|---|---|---|
| A-PR0 文档（baseline/branch/review-status） | `e1fa0b9` | **PARTIAL** | 可以（docs），需先 v2 更正 | ① 本文件 + `A_NEXT_BASELINE_ADDENDUM_V2.md` 完成 2 行更正与 v1 LOST 标注；② 更正后由 Reviewer 复核，**复核前不得自称 PASS**（Reviewer 措辞“更正后本项可升 PASS”是条件，不是自动生效） |
| A-PR0 工具（OCI/rootfs/CI hygiene） | `16a4187`（`chore/a-next-oci-hygiene`） | **PASS（条件）** | 是（工具） | ① canonical 环境确认后，在**真实树**复跑 `rootfs_guard`/`oci_guard`；② 在集成树复跑 `pytest tests/a_next_hygiene`（batch-1 为 **38 passed**，基于 16a4187 工作树）；③ **不得宣称 OS 只读**（Reviewer 实测 `mount.read_only=false`）；④ 事件后证据须标注 rootfs/deps 恢复自经哈希验证副本（backup tar sha `11172f02…`），不得称连续原始链。参考 `docs/A_NEXT_ENV_HARDENING.md`（sha256 `d0d1e36e72c630616b46139ccf53308cef8cd66ff54a4ac093f64a681551fac4`） |
| A-PR1 / A1 实现（P2-01 body id） | `e6f3aa6`（`fix/a-next-auth-record`） | **PASS（条件）** | 是（安全加严、no-key） | ① **A1 先冻结 → A2 rebase → 合并后**复跑 `tests/integration/a_next_auth` + `tests/integration/g4r_auth`；② A1 报告 §6.4“提交后 HEAD 复跑”以 Reviewer 在 `e6f3aa6` 的独立结果（39 passed）为准，分支再改须重绑；③ A6 的 BLK-08/D-14 在 A1 合入后 append-only 更新；④ **条件完成前不得宣称“P2-01 已在 canonical 线关闭”**；P2-02 仍 OPEN |
| A6 文档（human handoff/runbook/provider/price） | `13e39a4`（`docs/a-next-handoff`） | **PASS（条件）** | 是（docs） | ① A1 合并后 append-only 更新 BLK-08/D-14（保留旧行）；② 保持 D-01..D-22 全部 `UNSIGNED`、18 项 BLK 不减项；③ 按 INCIDENT_20261121 要求追加事件披露（新 BLK 项/扩展 D-08、D-10，Runbook 补恢复/备份/防再发）；④ 不得凭本包宣称任何门通过 |
| A0-03（rootfs 防写/不可变） | 工具 `16a4187` | 工具层 **PASS（条件）**；真实部署 **NOT_RUN** | 工具同 A-PR0 工具 | 真实部署只读 **HUMAN_REQUIRED / NOT_RUN**；事件后任何 OCI/L2 证据须注明恢复来源；不得写“全程 NO_DRIFT” |
| A0-02（65-case 对账终态） | 本 v2 更正 | **PARTIAL → 待复核**（Reviewer：更正后本项可升 PASS） | 同 A-PR0 文档 | 本文件仅做更正；升 PASS 需 Reviewer 复核确认 |

## 5. 不变项 / 不主张

- **不改**：`docs/A_NEXT_REVIEW_STATUS_RECONCILIATION.md` v1 字节、冻结 CSV、旧 Packet、旧 Review、任何
  `src/tests/scripts`（本文件只新增自身）。
- 不主张：A-PR0 docs 已 PASS、A0-02 已终态、任何门通过、v1 Packet 可核验、E5/G4-H/G5/G6/M0 通过。
- 不代填/代签任何 ACCEPT/FIX/BLOCK/DEFER；Reviewer 条件与维护者决定分开记录。
- **STOP**：等待 Reviewer 对 v2 更正复核、等待维护者决定集成与后续 Packet v3。

## 6. append-only 版本记录

| 版本 | UTC | 内容 |
|---|---|---|
| v1 | 2026-11-20T20:16Z | 初始更正：R4-05 PASS→PARTIAL、R4-12 PASS→UNVERIFIED、R4-13 维持 PASS；证据字段核查；更正后计数；batch-1 条件式结论登记 |
