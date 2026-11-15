# M0 G1 post-freeze errata — fix commit / task-70 复验 / O-G1-1 说明

- 任务：`task-71`（G1 post-freeze errata，V-G1-4 / O-G1-1）；日期：2026-11-15 UTC
- 性质：**只读补充记录**；不改代码/测试/旧证据字节；不 stage/commit。
- 背景：B-G1-1 已由 `task-70`（verify2）独立复验功能关闭；G1 仅因旧 errata 未记录 fix commit（V-G1-4）而暂记
  `PASS_PENDING_ERRATA`。本文件补记 fix 身份与最终状态。

## 1. 实现身份（正确 commit 映射）

| 阶段 | commit | 说明 |
|---|---|---|
| G0 baseline（G1 前） | `87f44e1227f38e454c4dc418b0e289df85721fb5` | 不是 G1 实现 |
| G1-SEC | `842583dceb0f7c7b43191b6b4b4c6d9cf8da8b09` | task-60 冻结（父 `92c9f71`） |
| G1-ACC | `00df577f18fcef924d9cef2a7c7d08afcc3bca20` | task-64 冻结（父 `842583d`） |
| **B-G1-1 fix** | **`4d715305022bdbaa437488a7224d33305324f034`** | task-68 修复冻结（父 `00df577`）；message `fix: G1 close AUTH-08 budget policy gap (B-G1-1)` |

fix 文件 hash：`src/autoteacher_m0/security/live_controller.py` sha256
`3f11e4e04ccf037c4c28a8cb6f9bbcde12306f4fcc085e3da73a79fabb30b39e`；
`tests/integration/sandbox/test_live_controller_no_key.py` sha256
`0b71f3c7fd35dd7856cbe8464dace2a34e02a3e2164d40043727b6436c1683c0`。

旧 errata `docs/M0_G1_ERRATA.md`（sha256 `6f85565cc83e5239edaf3f1b4a448775fd1f05de2d8823ff9ae52be527acf8c8`）由 fix commit
自身提交，无法自记录自身 hash；本文件为 post-freeze 补充，**旧字节不改**。

## 2. task-70 增量复验结果（verify2）

- **B-G1-1：功能关闭（PASS）**；expected budget `0.20/10.00/50` 与 `config/budgets.yaml` 一致，批准预算对照
  `authorization_approved=True` 但整体仍 BLOCKED（不构成 Live 解锁）。
- AUTH-08 新测试：**16 passed / 5 deselected**（8 个 EgressPolicy 字段 + 6 组 budget-only mutation + explicit
  expected 对照 + 批准预算对照）。
- 旧代码 fail-first：**核心 7 个新增用例失败**（真实旧行为）；审计选择集 **7 failed / 9 passed / 5 deselected**。
- full `tests/unit/security tests/integration/sandbox`：**165 passed / 1 skipped**（既有 `/input` skip）。
- Ruff scoped 与 repo-wide：**All checks passed!**
- 审计依据：`docs/REVIEW_G1_ADDENDUM.md` sha256
  `6618edfd78e48d2632209e5c6928f39fbcb6948ac94738c8b57cf6baa0f67b52`；
  `artifacts/reviewer-g1/addendum-4d71530/manifest.json` `622ef3e9793f64440947737f8bf8e3ca9b97a441a37d4efc4b7a597d44d631ac`；
  `evidence.sha256` `0fa852cc9735d97c30df77ba24dcaf3f5aee175e18e9366d0f2ce67b42321429`（**370/370**）。
- owner fix 证据：`artifacts/m0-g1-fix-bg11/manifest.json` `9f92b3db…`、`evidence.sha256` `80d2ff59…`（40/40）。

## 3. O-G1-1：fail-first 计数差异说明（信息性）

owner 与 auditor 的“核心 7 个新增用例失败”完全一致；差异仅来自 `-k` 选择集与 deselection，不是功能缺陷：

| 运行 | 选择 | selected | failed/passed/deselected |
|---|---|---|---|
| owner fix manifest | `-k "budget_only or explicit_expected_budget or approved_budget"`（仅新增 budget/control） | 8 | **7 failed / 1 passed / 13 deselected** |
| auditor task-70 | `-k "auth08 or budget_only or explicit_expected_budget or approved_budget"`（含原 8 个 EgressPolicy 用例） | 16 | **7 failed / 9 passed / 5 deselected** |

`artifacts/m0-g1-fix-bg11/manifest.json` 的 `7/1/13` 对其更窄选择集准确，无需改写；本文件记录差异原因。

## 4. 最终状态与边界

- **G1：`PASS_FOR_DECLARED_G1_SCOPE_WITH_ERRATA`**（仅限离线/无 Key 声明范围；B-G1-1 关闭；
  V-G1-1/V-G1-2/V-G1-4、O-G1-1 已记录）。
- **Live/E1–E5/LiveGate/真实 egress/Key/usage/账单仍 BLOCKED；总体 DECISION PENDING，不签发 GO。**
- 旧 `artifacts/m0-g1-security/manifest.json`（`4ef23f69…`）、旧 report（`0a8f6e18…`）、旧 errata
  `manifest-errata.json`（`9128621e…`）与 accounting errata（`55af59d4…`）**字节均未改**。
- 机器可读版本：`artifacts/m0-g1-security/manifest-errata-postfreeze.json` + `.sha256`（自校验）。

## 5. 参考

- reviewer 增量：[`REVIEW_G1_ADDENDUM.md`](<REVIEW_G1_ADDENDUM.md>)；原审计：[`REVIEW_G1.md`](<REVIEW_G1.md>)。
- 旧 errata：[`M0_G1_ERRATA.md`](<M0_G1_ERRATA.md>)；fix 证据：[`artifacts/m0-g1-fix-bg11/`](../artifacts/m0-g1-fix-bg11/)。
