# G1 最终收口 — errata post-freeze 只读复核

- 任务：`task-72`；日期：2026-11-15 UTC；审计者：`verify2`（只读复核，不重跑代码测试）
- 依据：冻结实现 HEAD **`4d715305022bdbaa437488a7224d33305324f034`**（父 `00df577`）；原审计 `docs/REVIEW_G1.md`（`3c082720…`）；增量复验 `docs/REVIEW_G1_ADDENDUM.md`（`6618edfd…`）；post-freeze errata：
  - `docs/M0_G1_ERRATA_POSTFREEZE.md` sha256 **`9ba176605e1bd1963bc0dac8799d428ed5d1d13d661bed207b13dd96fa530bf9`**
  - `artifacts/m0-g1-security/manifest-errata-postfreeze.json` sha256 **`4fc1ba4e8bfbe59df1a6d19bc030269d99a83f4910296eae8659a60e8f96a8fa`**
  - `artifacts/m0-g1-security/manifest-errata-postfreeze.sha256` sha256 `ad94c8cad24b39cee2565f8378a1ee4cafe0073fcaf468e8864acbd813b7e8e7`（`sha256sum -c` **OK**）

## 0. 最终结论

**`G1_FINAL_PASS_FOR_DECLARED_SCOPE_WITH_ERRATA`**（仅限 G1 声明的离线/无 Key 范围）。B-G1-1 功能关闭；V-G1-4 已由 post-freeze errata 关闭；O-G1-1 已按选择集差异记录（另见 §4 非阻断注释）。**Live/E1–E5/LiveGate/真实 egress/Key/usage/账单仍 BLOCKED；总体 DECISION PENDING，不签发 GO。**

## 1. 实现身份与 fix commit

| 项 | 值 |
|---|---|
| HEAD | `4d715305022bdbaa437488a7224d33305324f034` |
| HEAD 父 | `00df577f18fcef924d9cef2a7c7d08afcc3bca20`（G1-ACC） |
| 实现链 | G0 baseline `87f44e1` → G1-SEC `842583d` → G1-ACC `00df577` → B-G1-1 fix **`4d71530`** |
| fix message | `fix: G1 close AUTH-08 budget policy gap (B-G1-1)` |
| fix 文件 hash | `live_controller.py` `3f11e4e0…`；`test_live_controller_no_key.py` `0b71f3c7…`（与 post-freeze doc/manifest 一致） |
| 原 G1-SEC/G1-ACC 身份 | G1-SEC `842583d`、G1-ACC `00df577`、G0 baseline `87f44e1`（post-freeze errata 记录正确） |

## 2. Task-70 结果复核（与 reviewer addendum 一致）

| 项 | 记录值 | 复核 |
|---|---|---|
| B-G1-1 | PASS（功能关闭） | 与 `REVIEW_G1_ADDENDUM`/fix evidence 一致 |
| AUTH-08 | **16 passed / 5 deselected** | 一致 |
| 旧代码 fail-first | 核心 **7 个新增用例失败**；auditor 选择 7 failed/9 passed/5 deselected | 一致 |
| full security+sandbox | **165 passed / 1 skipped** | 一致（skip 为既有 `/input`） |
| Ruff | scoped/repo-wide All checks passed | 一致 |
| reviewer 增量 | `docs/REVIEW_G1_ADDENDUM.md` `6618edfd…`；manifest `622ef3e9…`；evidence `0fa852cc…`（**370/370**） | hash 一致 |
| owner fix 证据 | manifest `9f92b3db…`；evidence `80d2ff59…`（40/40） | hash 一致 |

## 3. V-G1-4 关闭与旧字节冻结

- V-G1-4（旧 errata 未记录 fix commit）已由 post-freeze errata 记录 **`4d71530`（父 `00df577`）**；最终文件中不再以 `PENDING_FREEZE_TASK_69` 作为“当前状态”（旧 errata 的历史占位字节按不改旧证据原则保留）。
- 旧字节复核未变：
  - 旧 errata `artifacts/m0-g1-security/manifest-errata.json` = `9128621e…`
  - 旧 manifest `artifacts/m0-g1-security/manifest.json` = `4ef23f69…`
  - 旧 report `docs/M0_G1_SECURITY_REPORT.md` = `0a8f6e18…`
  - 旧 doc errata `docs/M0_G1_ERRATA.md` = `6f85565c…`
  - accounting errata `artifacts/m0-g1-accounting/manifest-errata.json` = `55af59d4…`
  - 原 reviewer `docs/REVIEW_G1.md` = `3c082720…`、reviewer evidence = `eae77001…`/`61696b82…`（未改）
- `manifest-errata-postfreeze.sha256` 自校验 **OK**；旧 G1-SEC evidence **36/36 OK**、fix evidence **40/40 OK**、accounting 旧 evidence **16/16 OK**。

## 4. O-G1-1（信息性）与一处非阻断证据注释

post-freeze errata 将 O-G1-1 解释为选择集差异：owner `-k "budget_only or explicit_expected_budget or approved_budget"`（8 selected → 7 failed/1 passed/13 deselected）vs auditor `-k "auth08 or budget_only or explicit_expected_budget or approved_budget"`（16 selected → 7 failed/9 passed/5 deselected）；两者核心 **7 个新失败**一致。

**非阻断证据注释**：冻结的 owner fix evidence `artifacts/m0-g1-fix-bg11/argv/fail-first-final.argv.json` 实际记录的是**broad selection**（含 `auth08`），与我们 task-70 的 16-selected/7-9-5 结果对应；owner 8-selected/7-1-13 的 narrower selection 未在该 argv 文件中体现，可能来自更早/另一运行。两者都不影响 B-G1-1 功能关闭与 G1 结论；建议 owner 在后续 errata/证据说明中修正该选择的 argv/count 对应关系（无需重跑代码）。本项不阻断 G1 final PASS。

## 5. 只读复核命令与边界

- 只读命令：`sha256sum`, `sha256sum -c`, `git rev-parse/show/status`, `grep`，以及核对 reviewer/fix/旧证据 manifest 的 hash；**未运行 pytest/项目代码/容器，未读凭据，0 真实 Key/模型/HTTP**。
- worktree：HEAD `4d71530`；仅新增未跟踪 docs（`REVIEW_G1.md`、`REVIEW_G1_ADDENDUM.md`、`M0_G1_ERRATA_POSTFREEZE.md`）与 gitignored artifacts；`git diff --cached`=0；**未 commit/stage**。
- LiveGate/gates/adapter/run_live 仍 BLOCKED；E1–E5/Log/Live 不变；DECISION PENDING，不签发 GO。

## 6. 证据索引

- post-freeze errata：`docs/M0_G1_ERRATA_POSTFREEZE.md` `9ba17660…`；`manifest-errata-postfreeze.json` `4fc1ba4e…` + sha `ad94c8ca…`（self-check OK）。
- 增量复验：`docs/REVIEW_G1_ADDENDUM.md` `6618edfd…`；`artifacts/reviewer-g1/addendum-4d71530/manifest.json` `622ef3e9…`；`evidence.sha256` `0fa852cc…`（370/370）；stage `f9f0a747…`。
- owner fix：`artifacts/m0-g1-fix-bg11/`（manifest `9f92b3db…`、evidence `80d2ff59…`）。
- 收口机器可读记录：`artifacts/reviewer-g1/closure.json`。
