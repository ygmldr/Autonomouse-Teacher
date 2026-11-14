# M0 收尾报告 — PR0–PR4 离线完成与独立审计归档

- 任务：`task-54`（最终 docs-only 收口）；日期：2026-11-14 UTC
- 最终实现 HEAD：`87f44e1227f38e454c4dc418b0e289df85721fb5`（V-PR3-1/Ruff hygiene）
- 总体判定：**DECISION PENDING**；LiveGate/P03/真实 egress/Key/账单仍 **BLOCKED**；**不签发 GO**
- 本文件只归档已发生的事实；不把离线/合成 PASS 写成 Live PASS，不改写历史冻结证据。

## 1. 结论摘要

PR0–PR4 的无 Key/禁网隔离离线工作已完成并冻结；5 份独立审计报告均给出 **PASS（仅限各自声明的离线/无 Key 范围）**，未发现阻断性实现/安全/隔离缺陷，但存在若干已关闭或已记录的证据准确性/lint 发现（§4）。真实 DeepSeek Live、E5-PreLive 整体、人类授权/凭据/OS egress 边界、真实 provider wire/usage/账单仍未完成或未验证，因此 PR5–PR7 与总体判定保持 **BLOCKED / DECISION PENDING**。

- 0 真实 Key、0 真实模型、0 真实外部 HTTP；OpenCode Go 凭据未使用。
- 5 份审计：PR1 `f4cbdfb0…`、PR2 `4937d9a3…`、PR3 `3fabb8d4…`、PR4A `429a02f9…`、PR4B `fd1a71a4…`（完整 hash 见 §3）。
- 所有项目代码/测试只在固定 digest 无 Key 禁网隔离 OCI 内执行；宿主未运行项目 Python/pytest/TS，未读 `/root/.config/autoteacher`。

## 2. Commit 链（实际冻结顺序）

| 阶段 | commit | 父 | 说明 |
|---|---|---|---|
| PR0 docs | `e8b6e45b19d9001231323c76bc71fa4886be3439` | `7c3806b` | v0.5 基线/审查发现/待裁定/路线图/OpenCode Go 调查/裁定记录 |
| PR1 | `fdcfdc965a4eaf092badcdaab4ad44fd06b68607` | `e8b6e45` | broker/guard 预算不变量 F1–F6（离线） |
| PR3 | `9b77a3786c72a0f509f4c21d34f27314a92f3563` | `fdcfdc9` | 可信 Live Controller 设计 + 无 Key 演练（不授予 Live） |
| PR2 | `7d2cd3e8612212574767f0ff0ed1d1e7686bc643` | `9b77a37` | 目标 Runtime/Profile dump-config/静态 OpenCode Go 路由 + F7 缺口记录 |
| PR4a | `8cf24766dd062f3b7038885de1c4f24eebd00559` | `7d2cd3e` | mock egress 边界/失败矩阵/billable-path inventory（无 Key） |
| PR4b | `c802a3292888394d65466510d3ad07ff82be89cf` | `8cf2476` | ProviderObservation/usage 映射/call identity（无 Key） |
| V-PR3-1/Ruff hygiene | `87f44e1227f38e454c4dc418b0e289df85721fb5` | `c802a32` | 8 文件 lint/证据 scope 修正（仅 docs/tests/未用 import；无行为变更） |
| 本次 docs 收口 | 由本提交记录 | `87f44e1` | 5 审计报告 + 本报告 + README/ROADMAP + RUNTIME_BUDGET_GUARD V-PR1-1 修正 |

> 注：PR2 与 PR3 可并行，实际冻结顺序为 PR1→PR3→PR2；`7d2cd3e` 是 PR2 freeze，也是 PR4a 的父。

## 3. 证据 manifest 与审计报告

| 阶段 | owner 证据 | hash / 说明 |
|---|---|---|
| PR0 | `artifacts/m0-closeout-baseline/manifest.json` | sha256 `d252c82b2157780f17fdf4cc2400191de34e5e4c405bca96de86062315012a7f`（docs 归档 `e8b6e45`） |
| PR1 | `artifacts/m0-closeout-fix-tests/manifest.json` + errata | manifest `df14f3c1…`；V-PR1-1 errata `9fc6fb93…`；docs 计数修正后 `docs/RUNTIME_BUDGET_GUARD.md` = `25f38621…` |
| PR2 | `artifacts/m0-runtime-integration/manifest.json` | `c6ea4e86…`；对冻结 commit `7d2cd3e` evidence 49/49（post-freeze worktree 48/49 属 V-PR2-1 修复漂移，见 O-PR2-1） |
| PR3 | `artifacts/m0-controller-no-key/manifest.json` | `b5c16f81…`（evidence 17/17）；V-PR3-1 errata `artifacts/m0-controller-no-key/manifest-errata.json` `8aed1f84…` |
| PR4A | `artifacts/m0-egress-validation/manifest.json` + errata | `b04afbc9…`（19/19 对冻结 blob）；V-PR4A-1 errata `92020bff…` |
| PR4B | `artifacts/m0-usage-mapping/manifest.json` | `de1bdb07…`（artifact-hashes 8/8；O-PR4B-1 命名观察见 §4） |

| 审计 | 文件 sha256 | 结论（仅声明范围） |
|---|---|---|
| PR1 | `f4cbdfb00f2cfc400bab6c0dd3e6ea0c69d0777439b4b1820f560158415efd05` | `PASS_FOR_DECLARED_OFFLINE_PR1_SCOPE`；V-PR1-1 已 errata |
| PR2 | `4937d9a324442db86908e61dea7b1f77ef30a781b948597e2acf5ebcb21e12f9` | `PASS_FOR_DECLARED_NO_KEY_PR2_SCOPE_WITH_F7_GAP`；V-PR2-1 已修 |
| PR3 | `3fabb8d422f723ae457f0244876d390f12071b929ff77912ee535bb96af19250` | `PASS_FOR_DECLARED_NO_KEY_PR3_SCOPE_WITH_E5_BLOCKED`；V-PR3-1 已修 |
| PR4A | `429a02f9d36c43a8e8d19ce1093078f283b2039b53b023e39489772e9a574600` | `PASS_FOR_DECLARED_NO_KEY_PR4A_SCOPE_WITH_EGRESS_LIMITATION`；V-PR4A-1 errata |
| PR4B | `fd1a71a4d50f553445fef5d3f74acf40aecec15bf6abd07032111b47a13e65fb` | `PASS_FOR_DECLARED_NO_KEY_PR4B_SCOPE_WITH_REAL_WIRE_UNVERIFIED` |

## 4. 审计发现与状态

- **V-PR1-1（证据计数）**：`8 failed/130 passed` 实为 `9 failed/131 passed`；owner errata `9fc6fb93…`，`docs/RUNTIME_BUDGET_GUARD.md` 已修正（`25f38621…`，仅数字/errata 指向，无代码/新 SH 或 suite 重跑）。
- **V-PR2-1（PR2 lint）**：PR2 冻结 commit 的 `scripts/verify_runtime_profile.py` 2 个未用项已由 post-freeze `87f44e1` 清除；PR2 功能/证据结论不变。
- **V-PR3-1（Ruff scope）**：PR3 docs/manifest 泛写 Ruff 已改为 scoped 表述；PR1 测试 import 与 PR4a/PR2 历史 lint 已由 `87f44e1` 清除；本文件 §5 记录 HEAD `87f44e1` 的真实 repo-wide Ruff 结果。
- **V-PR4A-1（假 head hash）**：manifest `baseline.head` 为无效占位 SHA；errata `92020bff…` 更正为真实 PR3 `9b77a378…` 与 PR4a 父 `7d2cd3e`；旧 manifest 字节未改。
- **V-PR4A-2（PR4a lint）**：PR4a 路径 7 个未用 import/赋值已由 `87f44e1` 清除；冻结 commit 本身 lint 红的事实保留，不声称冻结 commit repo-wide PASS。
- **V-PR4B-1（继承 lint）**：PR4b 自身 scoped clean；其审计时跨 PR 的 13 项 repo-wide Ruff errors 已由 `87f44e1` 全部清除（见 §5）。`REVIEW_CLOSEOUT_PR4B.md` 正文是审计 `c802a32` 的历史结论，不改；其“87f44e1 仅部分修复”的当时表述以本报告 §5 的实际重跑结果为准。
- **O-PR2-1 / O-PR4A-1（evidence 漂移）**：冻结后授权 lint 修复导致 worktree 绑定的 evidence `sha256sum -c` 出现预期漂移；对冻结 commit blob 分别为 49/49 与 19/19，非篡改。
- **O-PR4B-1（证据命名）**：PR4b owner 使用 `artifact-hashes.sha256` 而非 `evidence.sha256` 命名；8/8 校验通过，但 stage/部分交付未纳入 checksum，属可改进的命名/范围观察，不影响结论。
- **O-PR4B-2（输入基线）**：PR4b 运行输入来自 `7d2cd3e` + worktree，冻结 commit `c802a32` 父为 `8cf2476`；独立审计已核对 accounting/tests 与 final commit 逐字节一致，证据有效。

## 5. Rebred lint 门（HEAD `87f44e1` 实际重跑）

在固定 digest 无 Key 禁网隔离 OCI（image `62d3569e…`、network none、ro、uid 65534；宿主未运行 ruff）对 **HEAD `87f44e1`** 重跑 repo-wide：

- 命令：`/opt/python/bin/python3.11 -B -m ruff check --no-cache .`（argv/UTC/exit/stdout/stderr 见 `artifacts/m0-controller-no-key/logs/vpr31-final-ruff.*`）
- 结果：**exit 0，`All checks passed!`**（UTC 2026-11-14T15:47:42Z）
- 结论：V-PR2-1、V-PR3-1、V-PR4A-2、V-PR4B-1 的继承 lint 已由 `87f44e1` 清除；HEAD `87f44e1` repo-wide Ruff 通过。`REVIEW_CLOSEOUT_PR2/PR3/PR4A/PR4B` 对其各自冻结 commit 的历史 lint 结论仍按原文保留（本报告只记录当前 HEAD 的实测状态）。

## 6. A/B/C 层边界

| 层 | 内容 | 当前证据状态 |
|---|---|---|
| A | 项目 Mock（无 SDK/真实 provider） | 项目 Mock/离线测试通过；只证明项目逻辑 |
| B | 真实锁定 DSH Runtime/SDK + 显式 `offline-test-only`/`fixture-v1` synthetic provider；真实 Session/JSON-RPC/工具注册 | PR2/PR3/PR4A/PR4B 的审计 PASS 属于此层或其无 Key 子集；**不是真实模型证据** |
| C | 真实 DeepSeek/第三方模型 Live | **NOT RUN / BLOCKED**：无真实 Key、无人类授权、无外部 egress/Key Broker、真实 usage/账单/模型映射未验证 |

OpenCode Go：仅作 **INTERNAL-TEST-ONLY** 可选内部路由候选，**不是**官方 DeepSeek 主路由，不得替代 E1–E5 强制 Live 验收。维护者已授权本机内部受限测试，额度记录上限 **US$10 硬上限 / US$3 软上限 / ≤50 次 Live 调用**；真实 Key 仅在仓库外 launcher 注入，绝不进入 Git/日志/公开证据/子代理 prompt；egress 设计仅 `opencode.ai:443`。凭据连通性 smoke 必须在 PR1–PR4 门禁满足后由维护者**最终另行批准**执行；本报告不构成执行授权。当前 key 未使用、无真实调用。

## 7. PR5–PR7 仍 BLOCKED 的原因

- **人类独立授权边界未部署**：E5-P03/PR3 设计未以独立 OS 身份部署，授权私钥/公钥托管、撤销、只读冻结仍需维护者外部执行；Controller/`LiveGate` 恒 BLOCKED。
- **外部 egress/Key Broker 未部署**：PR4a 只做描述符级 allowlist/deny + 失败矩阵；锁定 OCI 拒绝 socket，无法观测真实 provider wire/内部 retry/cache/Files/断连计费；不得声称真实硬预算。
- **F7 缺口未由外部边界闭合**：guard 缺失时 synthetic fixture 仍可被调用（PR2 已如实记录）；需要外部 egress/Key 边界而非仅插件。
- **真实 usage/账单/模型映射未验证**：PR4b 的 ProviderObservation 是离线映射；真实 provider invoice/usage 未核对，未知仍按 worst-case、不自动重试。
- **E5-PreLive 整体未 PASS**：真实 merged Profile/工具 registry/插件加载失败模式、真实 watchdog 部署、人类签核清单未完成；PR5–PR7 必须由维护者人工触发。
- **总体判定**：DECISION PENDING；任何替代渠道（如 OpenCode Go）成功都不能替代官方主路由/完整 E1–E5 重验。

## 8. 维护者 PR5 前置清单（人类动作）

1. 亲自身确认主渠道与模型准确 ID（默认官方 `deepseek-official/deepseek-flash`，不做模型选型）；如切换须事前批准并全量重验。
2. 独立审阅并冻结实现 SHA/依赖/merged Profile/工具清单/Secret 流向；在仓库外记录审批身份、日期、范围与撤销方式。
3. 提供低额度、专用、可撤销的 API 凭据（仅 launcher 注入，不进仓库/日志/候选环境）；如供应商侧有强制上限，留存证据。
4. 部署并验证外部 egress/Key Broker（含 OpenCode Go 仅 `opencode.ai:443` 的受控代理，若使用）与独立总 watchdog/进程树清理。
5. 确认 E5-PreLive/E5 范围；未满足项标 BLOCKED，不得删测或扩大权限绕过。
6. 仅在上述完成后主动触发最小 Live（PR5）；任何未知/超时/无 usage 结果按 worst-case held、不自动重试；P03/LiveGate 未人工打开前保持 BLOCKED。

## 9. 参考

- 决策记录：[M0_CLOSEOUT_DECISIONS.md](<M0_CLOSEOUT_DECISIONS.md>)（D1–D6；Q6–Q9/Q11 仍 OPEN）
- 路线图：[M0_CLOSEOUT_ROADMAP.md](<M0_CLOSEOUT_ROADMAP.md>)（当前状态表）
- 审计报告：[PR1](<REVIEW_CLOSEOUT_PR1.md>)、[PR2](<REVIEW_CLOSEOUT_PR2.md>)、[PR3](<REVIEW_CLOSEOUT_PR3.md>)、[PR4A](<REVIEW_CLOSEOUT_PR4A.md>)、[PR4B](<REVIEW_CLOSEOUT_PR4B.md>)
- 历史证据/errata 路径见 §3；本报告不替代各 PR manifest，亦不修改其字节。
