# M0 G0–G2 closeout errata — F-FINAL-1/2/3（非阻断文档准确性）

- 任务：`task-78`（最终 docs 一致性复核后的最小 errata）；日期：2026-11-15 UTC
- 触发：最终复核结论 **`G0_G2_DOCS_CONSISTENT_WITH_AUDITS`**，含 3 个非阻断文档问题；依据
  `artifacts/reviewer-g0-g2-final/closure.json` sha256
  `0e29ecc64ac378f39b22b71d2f55d296963a85d8b8a1895f2d777ba4fef9367b`.
- 性质：**只读补充记录**；不修改已审计的 `docs/M0_G2_CLOSEOUT_REPORT.md` 正文（其 sha256 `8be3815b…` 保持不变），
  不修改实现/测试/证据/旧审计正文；本文件为后续引用依据。

## 1. F-FINAL-1：task 号标注（commit hash/链正确）

| 位置 | 原文 | 错误 | 正确值 |
|---|---|---|---|
| `docs/M0_G2_CLOSEOUT_REPORT.md:16` | G1-ACC `00df577` …（task-64） | 把 **task-64（freeze 任务）** 当作 G1-ACC 实现任务 | G1-ACC 实现任务为 **`task-61`**；`task-64` 是后续 freeze 任务 |
| `docs/M0_G2_CLOSEOUT_REPORT.md:19` | G2-BROKER `ada8e28` …（task-74，父 `70cb574`） | 把 **task-74（freeze 任务）** 当作 G2-BROKER 实现任务 | G2-BROKER 实现任务为 **`task-65`**；`task-74` 是 freeze 任务；G2-EGRESS 实现任务为 `task-66`（`32bea5b`） |

`ada8e28`、`00df577`、`32bea5b` 等 commit hash 与链本身正确，无需更正。

## 2. F-FINAL-2：G1 状态精确字符串

- 原文（`docs/M0_G2_CLOSEOUT_REPORT.md:30`）：`PASS_FOR_DECLARED_G1_SCOPE_WITH_ERRATA`
- 最终 G1 closure 的精确字符串：**`G1_FINAL_PASS_FOR_DECLARED_SCOPE_WITH_ERRATA`**
- 二者语义一致（G1 离线 PASS + errata），差异仅为措辞/精确标签；最终引用以 closure 字符串为准。
  依据：G1 审计/errata 文件 `docs/REVIEW_G1.md`、`docs/REVIEW_G1_ADDENDUM.md`、`docs/M0_G1_ERRATA_POSTFREEZE.md`，
  以及最终 closure 记录。

## 3. F-FINAL-3：实现 HEAD 与 docs HEAD 区分

- 原文（`docs/M0_G2_CLOSEOUT_REPORT.md:23`）：`当前 HEAD 32bea5b（G2 实现最终 commit）`
- 更正：应区分两类 HEAD：
  - **G2 实现 HEAD**：`32bea5bcf8d35d778a54c04cebb0ae08fb1f849c`（G2-EGRESS 冻结实现；父 `ada8e28`）；
  - **docs HEAD（已审计 closeout）**：`f78ed6341fdd20a13f58cf826c61fd7c6b440cf7`（`docs: archive G2 audit and G0-G2 closeout`，父 `32bea5b`）。
  - 本 errata 本身是 `f78ed63` 之上的再一个 docs-only commit；其 SHA 见 git log，后文不应把该 docs SHA 当作实现 HEAD。
- 引用实现/复验时应使用 `32bea5b`；引用 closeout 文档时使用 `f78ed63`（本 errata 后 docs HEAD 再前进一个 commit）。

## 4. 影响评估（不改变任何结论）

上述 3 项均为文档准确性/措辞问题，**不影响任何审计结论或安全边界**：

- G0：Lead 接受 baseline/source inventory；G1：**PASS_WITH_ERRATA**（含上述精确字符串）；G2：**`PASS_FOR_DECLARED_G2_SCOPE`**（仅离线/无 Key）。
- G2-L1（legacy `authorize()/require()` 未强制 claim，G3/Live 前收口）、V-G2-1（实现 commit 身份注记）与残余限制均不变。
- **G3+ 未授权**；Live/E1–E5/LiveGate/真实 Key/egress/usage/账单仍 **BLOCKED**；总体 **DECISION PENDING**，**不签发 GO**。
- OpenCode Go 凭据未使用、0 真实调用/0 预算消耗（US$3 soft / US$10 hard / ≤50 次均未消耗）。
- 旧 closeout 报告与审计/证据字节未改；本 errata 仅补充更正记录。

## 5. 参考

- 最终复核：`artifacts/reviewer-g0-g2-final/closure.json` `0e29ecc6…`（status `G0_G2_DOCS_CONSISTENT_WITH_AUDITS`）
- 已审计 closeout：[`M0_G2_CLOSEOUT_REPORT.md`](<M0_G2_CLOSEOUT_REPORT.md>) `8be3815b…`（正文不改）
- G2 审计：[`REVIEW_G2.md`](<REVIEW_G2.md>) `dc71fda8…`；G1 审计：[`REVIEW_G1.md`](<REVIEW_G1.md>) `3c082720…`、[errata](<M0_G1_ERRATA_POSTFREEZE.md>) `9ba17660…`
