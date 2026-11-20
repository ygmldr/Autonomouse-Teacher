# A-NEXT — Baseline Addendum V3（append-only：provenance/sha 澄清，P2-A0-1）

- **文档 ID**：`A-NEXT-BASELINE-ADDENDUM-V3-v1`
- **记录者**：A-PR0 Implementer-Docs（子 Agent；非 Lead、非 Independent Reviewer）
- **时间（UTC）**：`2026-11-20T20:22Z`
- **性质**：**append-only 澄清**（Reviewer batch-3 条件 `P2-A0-1`）。只新增本文件；**不改**任何既有文件字节。
  本文件不改变任何裁定/门状态，只修正 provenance/身份追溯，供 Packet v3 引用。
- **Reviewer 依据**：`docs/A_NEXT_INDEPENDENT_REVIEW.md` @ `docs/a-next-review` `273df27`
  （sha256 `4f5c5e30713d1383983e528778d9dc3c62f4ec8579146cb80524fedf799e33c5`）§12（`:1029-1112`），
  其中 §12.6 `P2-A0-1`（`:1085-1091`）、§12.7 裁定（`:1101`）：A-PR0 docs v2 更正（`86edfd7`）=
  **PASS（条件：P2-A0-1 披露修正）**；A0-02 = **PASS**；A0-04 = **PARTIAL / LOST**；A0-03 =
  `NOT_RUN`（真实部署）/ PASS(条件)（工具层）；A5 = **PARTIAL**。
- **状态常量（未变）**：`LiveGate=BLOCKED`、`G4-H=NOT_AUTHORIZED`、`G5=BLOCKED`、`G6=NOT_RUN`、
  `M0=DECISION_PENDING`、`E5_PRELIVE_FULL=BLOCKED_PENDING_HUMAN_DEPLOYMENT`。

## 1. sha 表述更正（P2-A0-1 核心）

`A_NEXT_BASELINE_ADDENDUM_V2.md:6-8` 原写“对象为…`A_NEXT_BASELINE.md`（v1，commit `e1fa0b9`；
文件 sha256 `597811ff…`）”，**该对应关系错误**（措辞不严谨，非内容造假）。实测更正：

| 对象（`docs/A_NEXT_BASELINE.md`） | commit | 文件 sha256（实测） | git blob（实测） |
|---|---|---|---|
| **v1 原字节** | **`e1fa0b9`** | **`5ebbe39c9dae980a34be1bb39779520fc0e2ca6176a320a0ff3b7888ae484ae7`** | **`265a2663f9d64c3c498ea3b671041b2277e72cc7`** |
| **就地更正后（当前字节）** | **`94c81a1`**（此后未再改） | **`597811ff288f09925ff23ec5efc4dd2e85058ab31fed54902ed478923dc41ff5`** | **`3cc3d6b030ff335d7e820f4fd42554c92d317532`** |

- `A_NEXT_BASELINE_ADDENDUM_V2.md` **字节未改**（sha256 `540f216b89947c4e5ea8f44f9c60527658ea4ea6ac3a38e4cdeccd2f67ef43e2`）；
  本 V3 是唯一更正载体。
- 复核命令：`git show e1fa0b9:docs/A_NEXT_BASELINE.md | sha256sum`（= `5ebbe39c…`）；
  `git show 94c81a1:docs/A_NEXT_BASELINE.md | sha256sum`（= `597811ff…`）；
  `git rev-parse e1fa0b9:docs/A_NEXT_BASELINE.md`（= `265a2663…`）。

## 2. 登记 `94c81a1` 的“就地修改”（pre-v2，当初未在版本记录中披露）

`94c81a1`（commit message：`docs(a-next): correct protected-file diff scope and add F-02 evidence line refs (no-key)`）
在 v1 三 docs 提交后、v2 之前，**就地对两个 v1 文档做了 13 行/文件 的更正**（未改写历史，`e1fa0b9` 与
`94c81a1` 两个提交均保留可见）：

| 文件 | e1fa0b9→94c81a1 numstat | 修改内容 |
|---|---|---|
| `docs/A_NEXT_BASELINE.md` | **+9 / −4**（合计 13 个变更行） | §5 受保护文件说明拆为 **A 组（main 已有受保护文件）/ B 组（work/g4r 历史新增 Review 冻结件）**：原“相对 main 未改动”对 B 组不成立（B 组相对 main 是新增，只是 A-PR0 未改动），更正为分组核对；§8 命令相应拆分 |
| `docs/A_NEXT_BRANCH_RECONCILIATION.md` | **+8 / −5**（合计 13 个变更行） | §4 H0 `F-02` 覆盖结论补充**实测证据行号**：`authorization.py:918/1074/1088/1095`、`test_r1_atomic_use_record.py:326,345`、`REVIEW_G4R_INDEPENDENT.md:163`、H0 定义 `work/m0-g4h0:…:325` |
| **合计** | **2 files / +17 / −9** | `git diff --numstat e1fa0b9 94c81a1` 实测 |

- 该更正的原因：A-PR0 自查发现“protected files vs main 未改动”对 G4-R Review 冻结件（相对 main 为新增）
  表述不准确；在分支冻结前做**同分支追加提交**更正（非 amend/rebase，非改历史）。**当时未在 v2 版本记录中
  披露该次就地修改**——这正是 P2-A0-1 要求补登记的内容；本文件完成披露。
- 后续 `fbea535`（事件文档）与 `86edfd7`（v2 addenda）**未再修改**上述两个 v1 文档（可核验：两文件在
  `94c81a1` 与当前 HEAD 的 blob 相同）。

## 3. 重申：`A_NEXT_REVIEW_STATUS_RECONCILIATION.md` v1 字节未被修改

- 文件 sha256 = **`81ecae3ca5fc4ec6a9628d53e22651989772e8cc24c2d41ab0bcf55f4d6ce59b`**，
  git blob = **`5729eb740756475213470421b35e8efdf0754a53`**；在 `e1fa0b9` 与当前 HEAD **相同**，
  `git diff e1fa0b9..HEAD -- docs/A_NEXT_REVIEW_STATUS_RECONCILIATION.md` = **0 行**。
- v2 更正（`A_NEXT_REVIEW_STATUS_RECONCILIATION_V2_ADDENDUM.md`）是 **append-only 新文件**
  （sha256 `2004099ee8e10d86a6e8b1de7787f6b15ba0a991bcb7a4389c86ad2b861b46b3`），只追加 old→new，
  65 行 v1 表保留原值。
- 冻结 CSV（`741d7d55…`）与 G4-R Review（`0599856a…`）仍未被任何提交修改（`git diff fd1d3a6..HEAD` = 空）。

## 4. v2 更正内容不受本澄清影响（维持）

| case | v2 终态（不变） | 依据 |
|---|---|---|
| `R4-05`（SQLite backup provenance） | **`PARTIAL`**（reviewer final=`NO_DIRECT`；frozen PARTIAL 保留） | Reviewer §8.1 / §12.3 复核 correct |
| `R4-12`（Evidence path correction） | **`UNVERIFIED`**（reviewer final=`NO_DIRECT`；frozen PARTIAL 仅 Owner 记录） | Reviewer §12.3：“UNVERIFIED 属保守上界，未夸大” |
| `R4-13`（LiveGate reason snapshot） | **`PASS`** 维持 | R-REV5 livegate 快照一致性支撑 |

更正后行级计数维持 **23 PASS / 19 PARTIAL / 10 NOT_RUN / 3 UNVERIFIED / 4 NO_DIRECT / 6 N/A = 65**；
A0-04=`PARTIAL/LOST`、A0-03（真实部署）`NOT_RUN`、A5=`PARTIAL`、A0-02=**PASS（Reviewer）** 均不变。
本 V3 **不重新裁定任何行**，只修 provenance/披露。

## 5. v2 Packet “恢复副本 provenance” 措辞与 incident 统一（P3-A0-2）

Reviewer 建议（§12.6 `P3-A0-2`）：v2 Packet 来源措辞应与事件文档恢复源清单一致。现统一表述为（不修改旧字节）：

> **Packet v2 为恢复副本**：恢复来源为 **`/tmp/at-g4f-review/artifacts`（2026-11-19 副本）+ 各 worktree
> `artifacts` 副本（`g4r-packet-final`/`g4r-phase2`/`g4r-*`/`m0-g4h0*` 等）以 no-clobber 合并**；其中
> Packet v2 目录的可用副本来自 worktree `g4r-packet-final`。恢复后经 Reviewer 自建独立 verifier 复跑
> = `status=PASS`、`issues=[]`、`mutation_undetected=[]`（manifest `fe45d760…`/tree `4300a7c6…`/
> hashes `e7a67c77…`、43 files/0 symlink）。**恢复后 timestamps 不具证明力**；**不得声称“自冻结以来字节
> 从未被触碰/未恢复”**，不得写“全程 NO_DRIFT/证据完整”。backup tar
> `/root/a-next-artifacts-restored-20261121.tar`（sha256 `11172f02…159d42`）为**恢复后**快照，非事故前备份。

与 `A_NEXT_ENVIRONMENT_INCIDENT.md:99,157,161` 及 `A_NEXT_BASELINE_ADDENDUM_V2.md:36-37` 的既有措辞
**一致**（本次仅补全“来源清单”的完整表述；旧文件字节不变）。

## 6. 冻结声明

- 本文件是本分支在集成前的**最后一个 append-only 澄清**；commit 后 `docs/a-next-baseline` 冻结，等待
  `work/a-next` 集成（Lead 指定的 A-PR4 集成任务由 Integrator 负责；本任务不参与、不合并）。
- 不改既有字节；不 push/merge；0 真实 Key/Provider/HTTP/Live；不触碰 `m1_*`。

## 7. 自查（实测）

```text
git diff 86edfd7..HEAD --name-only            -> 仅 docs/A_NEXT_BASELINE_ADDENDUM_V3.md（预期）
既有文件 sha（HEAD 不变）：
  A_NEXT_BASELINE.md                              = 597811ff…（94c81a1 后未改）
  A_NEXT_REVIEW_STATUS_RECONCILIATION.md          = 81ecae3c…（e1fa0b9 后未改）
  A_NEXT_ENVIRONMENT_INCIDENT.md                  = 201c5984…（fbea535 后未改）
  A_NEXT_BASELINE_ADDENDUM_V2.md                  = 540f216b…（86edfd7 后未改）
  A_NEXT_REVIEW_STATUS_RECONCILIATION_V2_ADDENDUM.md = 2004099e…（86edfd7 后未改）
冻结件：CSV 741d7d55… / Review 0599856a… / g4r_review_evidence 未被改动
```

## 8. append-only 版本记录

| 版本 | UTC | 内容 |
|---|---|---|
| v1 | 2026-11-20T20:22Z | 初始澄清（P2-A0-1）：e1fa0b9 baseline sha=`5ebbe39c…`/blob `265a2663…`、94c81a1 后=`597811ff…`/blob `3cc3d6b0…`；登记 94c81a1 就地修改（2 文件各 13 行，+17/−9）；重申对账 v1 未改（`81ecae3c…`）；v2 更正内容/计数不变；Packet v2 恢复 provenance 措辞与 incident 统一（P3-A0-2）；冻结声明 |

> 本文件不构成任何 PASS/授权；A0/A5 等终态以 Reviewer 报告为准，集成与门决定属维护者/Lead。
