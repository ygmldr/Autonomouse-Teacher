# A-NEXT — Baseline Addendum V2（append-only：A0-04/A0-03/A5 与 batch-1 条件）

- **文档 ID**：`A-NEXT-BASELINE-ADDENDUM-V2-v1`
- **记录者**：A-PR0 Implementer-Docs（子 Agent；非 Lead、非 Independent Reviewer）
- **时间（UTC）**：`2026-11-20T20:16Z`
- **性质**：**append-only v2 addendum**。对象为已提交 `docs/A_NEXT_BASELINE.md`（v1，commit `e1fa0b9`；
  文件 sha256 `597811ff288f09925ff23ec5efc4dd2e85058ab31fed54902ed478923dc41ff5`，git blob
  `3cc3d6b030ff335d7e820f4fd42554c92d317532`）。**v1 字节不改**；本文件只追加更正与登记。
- **依据**：
  - Reviewer 阶段 2 batch-1：`docs/A_NEXT_INDEPENDENT_REVIEW.md` @ `1b2558b`（sha256
    `a005ace4495d96c2b4befc524d56e9204d02390111575c9b1a4fb37591f2662f`；batch-1 主体 `e6ee40f`）§8.2–§8.5
    （`:538-639`）与 §9（事件影响 `:674+`）。
  - 环境事故：`docs/A_NEXT_ENVIRONMENT_INCIDENT.md`（本分支 commit `fbea535`，sha256
    `201c59846a6b50f17a5541165ed8907ae19aeae569a4ac4b5054f222c2ed4150`）。
  - Reviewer v2 更正要求：`docs/A_NEXT_REVIEW_STATUS_RECONCILIATION_V2_ADDENDUM.md`（同批新增）。
- **状态常量（未变）**：`LiveGate=BLOCKED`、`G4-H=NOT_AUTHORIZED`、`G5=BLOCKED`、`G6=NOT_RUN`、
  `M0=DECISION_PENDING`、`E5_PRELIVE_FULL=BLOCKED_PENDING_HUMAN_DEPLOYMENT`。

## 1. A0-04（Packet/Review 冻结）→ 由 `PASS` 更正为 `PARTIAL / LOST`

| 项 | v1 值（历史，不改字节） | V2 更正 | 依据 |
|---|---|---|---|
| A0-04 | **PASS（只读哈希核对）**：“v1/v2 Packet、G4-F 旧件、G4-R Review 字节与登记值一致；本任务零写入” | **`PARTIAL / LOST`** | `A_NEXT_ENVIRONMENT_INCIDENT.md` §6 L-01、§7.1；Reviewer `A_NEXT_INDEPENDENT_REVIEW.md:@1b2558b` §9.2/§9.4 |

**更正理由（不淡化）**：

1. **v1 Packet 原始字节已丢失**：`artifacts/review-packet-g4f-e7d92967ec0ece80de4a1a3705f637e8eb9bde99/`
   （原 177 files / 0 symlink）在 `INCIDENT_20261121` 中被删除；全盘 scoped 搜索无副本、备份 tar
   （`/root/a-next-artifacts-restored-20261121.tar`，sha256 `11172f02…159d42`）无该目录。
   → 状态：**`LOST_IN_INCIDENT_20261121`**。
2. v1 Packet 的记录值（`manifest 4aed2a92…1d7f2`、`hashes 421b07ae…9d3d`、177 files/173-173）
   仅为仓库文档的 **`DOC_RECORDED` 历史登记**；**不得**再作为可复算证据，也**不得**生成新包冒充 v1。
3. **v2 Packet 仍可独立核验（保留 PASS）**：恢复后路径经 Reviewer 自建独立 verifier 复核（本记录亦复跑）：
   `status=PASS`、`issues=[]`、`mutation_undetected=[]`、`manifest fe45d760…`、`tree 4300a7c6…`、
   `hashes e7a67c77…`、43 files/0 symlink/payload 40/hashes 41。但必须注明：
   v2 是**恢复副本**（来自 worktree `g4r-packet-final` 副本，恢复后 timestamps 不具证明力），
   **不得声称“自冻结以来字节从未被触碰/未恢复”**。
4. 受影响的旧表述（只在旧文档字节中保留，不修改）：`A_NEXT_BASELINE.md:105-106`（v1 哈希行）、
   `:137`（A0-04 PASS 行）、`A_NEXT_REVIEW_STATUS_RECONCILIATION.md` §4/§5 的 v1 行。按事件记录与
   `A_NEXT_REVIEW_STATUS_RECONCILIATION_V2_ADDENDUM.md`，凡涉及 v1 处一律按 `LOST_IN_INCIDENT_20261121` 解读。

## 2. A0-03（rootfs 防写/不可变）→ 维持 `NOT_RUN`（真实部署层）；工具层 `PASS(条件)`

| 层 | V2 状态 | 说明 |
|---|---|---|
| 真实部署防写 / OS 只读 / 人类部署 | **`NOT_RUN`（不变）** | 无真实部署；`HUMAN_REQUIRED`。不得宣称 rootfs 在部署态不可写 |
| 工具层（`chore/a-next-oci-hygiene` @ `16a4187`） | **`PASS（条件）`** | Reviewer §8.2：9 files / +2244，仅 docs+`scripts/a_next/**`+`tests/a_next_hygiene/**`，无 `src/`/冻结件改动；Reviewer 亲跑 `pytest tests/a_next_hygiene` = **38 passed**，fake-tree 探针退出码符合文档；条件见 §4 |

**事件相关补充（必须随任何 A4/L2/OCI 证据标注）**：

- 恢复后 rootfs canonical = `25491e45…2fe9c0`、deps = `e07729d7…2ecb98`，与冻结值一致；但 provenance =
  **2026-11-21 从经哈希验证的副本合并恢复**（backup tar sha `11172f02…`），**不是原始 in-place 连续链**。
- **Stage 身份必须独立重算/复核**后才能用于 A4/L2；旧 Stage 引用的证据集合已部分丢失（见 §3）。
- 任何 OCI/L2 记录必须写：`rootfs/deps restored 2026-11-21 from hash-verified copies (backup tar sha 11172f02…), not original in-place chain`。
- **不得写“全程 NO_DRIFT”**；Reviewer 实测 `mount.read_only=false`（工具层 PASS 不等于 OS 只读）。

## 3. A5（Packet/证据卫生）→ 降为 `PARTIAL`

| 项 | V2 状态 | 证据/原因 |
|---|---|---|
| A5 整体（Packet/证据卫生） | **`PARTIAL`** | ① v1 Packet 原始字节 `LOST_IN_INCIDENT_20261121`；② `artifacts/g4f/**` 恢复后 **0 files**（G4-F 原始运行证据 LOST）；③ `artifacts/g4/**` 仅 `c/` 部分恢复（13,246 files），`d/`、`e5/` 等不存在；④ `artifacts/g4r/**` 仅 2,982 files（多副本合并，完整性不可证明）；⑤ `artifacts/security/**` 部分文件为副本 provenance；⑥ 顶层 3 个 symlink（`g3a-provider-bridge`/`g3c`/`g3d`）自指悬空；⑦ backup tar 为**恢复后**快照，不能恢复事故前 v1 |
| 仍成立的部分 | — | Packet v2 独立 verifier PASS（Reviewer R-REV5 + 本记录复跑，`issues=[]`/`mutation_undetected=[]`）；Git 跟踪的冻结 CSV（`741d7d55…`）/G4-R Review（`0599856a…`）字节未受影响 |
| 未来 Packet v3 要求 | — | 必须披露本事件与恢复来源（含 backup tar sha、恢复清单）、附恢复证据；旧 v1 只读引用改为 `LOST_IN_INCIDENT_20261121`；不得声称“全部 Packet/证据可核验” |

## 4. Stage-2 batch-1 Reviewer 条件式结论登记（便于集成后追踪）

来源：`docs/A_NEXT_INDEPENDENT_REVIEW.md:@1b2558b` §8.2（`:538-571`）、§8.3（`:573-605`）、§8.4（`:607-631`）、
§8.5（`:632-639`）、§9.4/§9.5（`:700+`）。**以下均为条件式；不表示已满足、不表示任何门通过。**

| 对象 | 提交 SHA | Reviewer 裁定 | 条件（摘要；详见 Reviewer §8） |
|---|---|---|---|
| A-PR0 文档 | `e1fa0b9` | **PARTIAL**（需 v2 更正） | 本 addendum + Review-Status V2 更正完成 2 行过度归因；更正后由 Reviewer 复核（复核前不得自称 PASS） |
| A-PR0 工具 | `16a4187` | **PASS（条件）** | canonical 环境确认后真实树复跑 `rootfs_guard`/`oci_guard`；集成树复跑 `pytest tests/a_next_hygiene`（batch-1 38 passed）；不得宣称 OS 只读；事件后输入须标注恢复 provenance |
| A-PR1/A1 实现 | `e6f3aa6` | **PASS（条件）** | A1 先冻结→A2 rebase→合并后复跑 `tests/integration/a_next_auth` + `g4r_auth`（Reviewer e6f3aa6 结果 39 passed 为准，分支再改须重绑）；A6 BLK-08/D-14 更新；条件完成前不得称“P2-01 已在 canonical 线关闭”；P2-02 仍 OPEN |
| A6 文档 | `13e39a4` | **PASS（条件）** | A1 合并后 append-only 更新 BLK-08/D-14；D-01..D-22 保持 `UNSIGNED`；18 BLK 不减项；追加 INCIDENT_20261121 披露（新 BLK 项/扩展 D-08、D-10，Runbook 补恢复/备份/防再发）；不得凭包宣称门通过 |
| A0-04 | 本 addendum | **PARTIAL / LOST**（v1 LOST；v2 PASS） | 见 §1；Packet v3 需新身份并披露事件 |
| A0-03 | 工具 `16a4187` | 工具层 **PASS（条件）**；真实 **NOT_RUN** | 见 §2；`HUMAN_REQUIRED` 不变 |
| A5 | — | **PARTIAL** | 见 §3；Packet v3 披露 + 恢复证据为必要条件 |
| A0-02 | Review-Status V2 | **PARTIAL → 待复核**（Reviewer：更正后可升 PASS） | 由 Reviewer 对 `A_NEXT_REVIEW_STATUS_RECONCILIATION_V2_ADDENDUM.md` 复核 |

## 5. 不变项 / 不主张 / append-only

- **不改**：`docs/A_NEXT_BASELINE.md` v1 字节、冻结 CSV/Packet/旧 Review、任何 `src/tests/scripts`；
  本文件只新增自身。冻结字节证明沿用 v1 与 Review-Status v1 §5（CSV `741d7d55…`、Review `0599856a…`）。
- 不主张：A0-04 通过、A0-03 真实部署可写保护、A5 证据完整、Packet v1 可核验、任何门/PASS/部署/Live。
- 不写“全程 NO_DRIFT/证据完整/已全部恢复”；不代填/代签 ACCEPT。
- **STOP**：等待 Reviewer 复核 v2 更正、维护者决定 integration/Packet v3；后续任务以本 addendum 与
  `A_NEXT_ENVIRONMENT_INCIDENT.md` 为输入。

## 6. append-only 版本记录

| 版本 | UTC | 内容 |
|---|---|---|
| v1 | 2026-11-20T20:16Z | A0-04 PASS→PARTIAL/LOST（v1 LOST；v2 PASS 保留）；A0-03 维持 NOT_RUN（工具层 PASS 条件）；A5→PARTIAL；batch-1 条件式结论登记；事件/恢复 provenance 要求 |
