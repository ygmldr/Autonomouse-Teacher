# M0 G1 errata — B-G1-1 修复、实现身份与报告笔误更正

- 任务：`task-68`（B-G1-1 修复）；基线 HEAD `00df577`；日期：2026-11-15 UTC
- 触发：`docs/REVIEW_G1.md`（sha256 `3c082720…`）独立审计结论 **FAIL_FOR_DECLARED_G1_SCOPE**；唯一阻断项 B-G1-1，另有 V-G1-1/V-G1-2/V-G1-3。
- 本文件为 errata，不修改 `docs/M0_G1_SECURITY_REPORT.md` 与旧 `artifacts/m0-g1-security/manifest.json` 的字节；旧报告/manifest 保持冻结原样。

## 1. V-G1-1：实现 commit 身份更正

旧 `docs/M0_G1_SECURITY_REPORT.md:3` 与 `artifacts/m0-g1-security/manifest.json` 的 `implementation_sha` 写成
G1 前基线 `87f44e1`。正确的映射为：

| 阶段 | commit | 说明 |
|---|---|---|
| G0/实现基线 | `87f44e1227f38e454c4dc418b0e289df85721fb5` | G1 前基线，不是 G1 实现 |
| G1-SEC | `842583dceb0f7c7b43191b6b4b4c6d9cf8da8b09` | task-60 冻结（父 `92c9f71`） |
| G1-ACC | `00df577f18fcef924d9cef2a7c7d08afcc3bca20` | task-64 冻结（父 `842583d`） |
| B-G1-1 fix | 待冻结（task-69 占位） | `live_controller.py` expected budget policy + sandbox budget-only mutation tests |

G1-SEC/G1-ACC 的 owner report 与 manifest 旧字节不改；本 errata 为审计与后续引用的正式更正。

## 2. V-G1-2：报告笔误更正

`docs/M0_G1_SECURITY_REPORT.md:49` 的“未做 A4/A5/A13”为笔误：**A4/AUTH-08 已在同一 G1-SEC 报告中修复并测试**（含完整 EgressPolicy 校验）；**A5 属 G1-ACC 范围**；A13 尚未实施。以本 errata 为准，旧报告字节不改。

## 3. V-G1-3：provenance 能力边界（G2 条件）

`TrustedEgressProvenance` 是同进程 capability/公开工厂，**不是**密码学来源认证，也不等于 provider 认证。
G2 必须把签发/工厂限制在可信 egress/Controller 边界，并审计所有 import 点；在真实 provider_invoice/usage 来源认证前不得声称账单已核对。该条件不阻断 G1 其余已核项，但 G2 报告必须显式收口。

## 4. B-G1-1：AUTH-08 budget policy 修复

**旧缺口**：Controller 仅接收 `budget_scope`，无 expected budget caps；有效签名但预算字段被改（host/path/method/route 不变）的授权在 Controller 层不会产生 policy 违规；AUTH-08 测试仅覆盖 EgressPolicy 8 字段，无 budget-only mutation。

**修复**：`security/live_controller.py` 引入固定 expected budget policy：
- 来源：`config/budgets.yaml` 的 hard 上限与 v0.6 §9.5 —— `hard_call_usd=0.20`、`hard_total_usd=10.0`、`max_live_requests=50`；
- fields：`scope`（取自 Controller `budget_scope`）、`per_call_cap_usd=0.20`、`total_cap_usd=10.00`、`max_calls=50`；
- 不接受授权自报；将解析出的 `ExecutionAuthorization.budget` 与 expected 逐字段比较，不匹配返回 `approved=False` 并 append `BUDGET_POLICY_MISMATCH:<field>`；
- Controller 仍 inspect-only/恒 BLOCKED、不新增 Live 入口；批准预算本身通过 budget 校验时，Controller 仍因外部前置（授权边界/egress/Key/watchdog 等）保持 BLOCKED。

**测试**（`tests/integration/sandbox/test_live_controller_no_key.py`，保留原 8 个 EgressPolicy 字段测试）：
- budget-only mutation：签名仍有效，仅改 per_call/total/max_calls（6 组）→ Controller 拒绝并含 `BUDGET_POLICY_MISMATCH`；
- expected 预算被改的对照：显式 expected budget 与授权不一致 → 拒绝；
- 批准预算对照：authorization_approved=True 但整体仍 BLOCKED，且无 budget mismatch（防止误以为解锁）。
- fail-first（旧 live_controller + 新测试）：**7 failed / 1 passed / 13 deselected**；修复后 targeted **16 passed**；全量 security+sandbox **165 passed / 1 skipped**；Ruff scoped/repo-wide 均 All checks passed。
- 原始日志/argv/UTC/exit/镜像/absence：`artifacts/m0-g1-fix-bg11/`（manifest/evidence）。

## 5. Accounting 侧 errata 引用

G1-ACC 侧 errata 由 broker-docs 创建，本任务不覆盖：
`artifacts/m0-g1-accounting/manifest-errata.json` sha256 `55af59d497a7dde68088f3fbbc29be8411639aafe5e0a7bf27a132a3685c5607`，
记录 G1-ACC=`00df577`、G1-SEC=`842583d`、G0 baseline=`87f44e1` 与 V-G1-3；以该文件及其 errata.sha256 为准。

## 6. 状态与边界

- B-G1-1 修复完成，等待 task-69 冻结与 task-70 独立复验；在复验通过前 G1 不宣布 PASS。
- Live/E1–E5/真实 egress/Key/usage/账单仍 BLOCKED；总体 **DECISION PENDING**，不签发 GO；0 真实 Key/模型/HTTP。
