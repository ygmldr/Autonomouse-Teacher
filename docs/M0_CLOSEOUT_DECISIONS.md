# M0 收尾 — Lead/维护者裁定记录（DECISIONS）

- 任务：`task-37`（v0.5 PR0 文档归档；docs-only，无源码/测试/配置修改）
- 日期：2026-11-14 UTC
- 基线：`HEAD=7c3806b58af2bd49328bdd9bcc53e858a13c35e5`；被测实现 SHA 仍为
  `feb7118f9aff20c681cc651812b30315288080f1`（本文件所在 docs-only commit **不是**测试基线）
- 关联：[`OPEN_QUESTIONS.md`](OPEN_QUESTIONS.md)、[`M0_CLOSEOUT_ROADMAP.md`](M0_CLOSEOUT_ROADMAP.md)、
  [`M0_REVIEW_FINDINGS.md`](M0_REVIEW_FINDINGS.md)、
  [`Autonomous_Teacher_M0_Closeout_Review_and_Implementation_Plan_v0.5.md`](Autonomous_Teacher_M0_Closeout_Review_and_Implementation_Plan_v0.5.md)
- 本文件不含真实凭据；不构成 Live 授权。

## 裁定汇总

| ID | 对应问题 | 裁定 | 状态 |
|---|---|---|---|
| D1 | Q1 | 验证范围=本机；跨机 OCI/全平台不属 v0.4 强制项 | **ACCEPTED** |
| D2 | Q2 | F1 采用 v0.5 方案 A；broker 优先 v1 兼容 | **ACCEPTED** |
| D3 | Q3 | F2 reserve/PENDING 容量分离；guard 上界对齐 100,000 | **ACCEPTED** |
| D4 | Q4 | PR1 定向测试允许入库 | **ACCEPTED** |
| D5 | Q5 | OpenCode Go = INTERNAL-TEST-ONLY 可选内部路由候选 | **ACCEPTED** |
| D6 | Q10 | PR0 文档独立 docs-only 归档；实现 SHA 仍 feb7118 | **ACCEPTED** |
| — | Q6–Q9、Q11 | 保持 OPEN，延后到 PR3/PR5 或对应 PR | **OPEN（不假装关闭）** |

## D1（Q1）— 验证范围与跨机/全平台

本次收尾的验证范围 = **本机**。跨机 OCI / 全平台不属于 M0 v0.4 §E5-01..09 的强制项
（v0.4 原文无该条），因此 **不要求**为通过 PR6/PR7 而显式修订验收规范；PR6/PR7 将该
范围作为**残余风险**记录。若未来要改变该口径，必须由维护者显式修订验收规范，不得由
Agent 自行放宽或删除测试。

## D2（Q2）— F1 重试归因

采用 v0.5 **方案 A**：

1. 禁用 provider 内部自动重试（不得依赖重试字段精确限制内层重试）；
2. 所有 logical stream 计入统一的 step/request 计数与记账；
3. 移除“retry 字段可精确限制内层重试”的声明（文档/注释需与实现一致）。

broker **优先保持 v1 兼容**；若实现必须改 schema，必须同时提供
`protocol_version`/`capabilities` 协商、兼容解析路径和新的定向测试，不得静默破坏 v1 客户端。

## D3（Q3）— F2 容量语义与 max_messages

采用“**新建 reserve 容量**”与“**既有 PENDING 完成容量**”分离的语义：新 reserve 不得被
既有 PENDING 的收尾路径无限挤占；snapshot 独立有界。guard 的 `max_messages` 校验上界与
broker 实际硬上限 **100,000** 对齐；M0 profile 保持 **4096** 不变。

## D4（Q4）— PR1 定向测试入库

PR1 的定向测试允许提交入库（`plugins/runtime-budget-guard/tests` 与 `tests/` 下），以保持
可复验性；测试必须能先失败、再随修复通过，并记录在对应 PR 证据中。不得把测试文件之外的
实现改动混入 docs-only 提交（本文件所在提交仅 docs）。

## D5（Q5）— OpenCode Go 路由定位

OpenCode Go 仅作为 **INTERNAL-TEST-ONLY** 的可选内部路由候选：

- **不得**冒充官方 DeepSeek 主路由，**不得**替代 E1–E5 强制 Live 验收；
- 维护者已授权在本机内部受限测试，按 **US$10 硬上限 / US$3 软上限 / ≤50 次 Live 调用**
  记录用量；
- 真实 Key 存于仓库外，仅由 launcher 在运行时注入，**绝不**进入 Git、日志、公开证据或
  子代理 prompt；
- 凭据连通性 smoke 必须在 PR1–PR4 门禁满足后**另行审批**执行，本文件不构成执行授权。

技术调查证据见 [`OPENCODE_GO_ACCESS.md`](OPENCODE_GO_ACCESS.md)（分级结论；
官方/第三方边界与 UNVERIFIED 项以该文件为准）。

## D6（Q10）— 文档/证据身份

PR0 文档（v0.5 任务书原文、审查发现、待裁定问题、路线图、OpenCode Go 调查、本裁定记录）
作为**独立 docs-only commit** 归档；实现 SHA 仍为 `feb7118`，**文档 commit 不得冒充测试
基线**；v0.5 用户提供文件按**原字节**保留，不修改其结论/要求来适配实现。

## 仍未关闭（OPEN）

Q6（PR5 人类前置清单）、Q7（E5-PreLive/E5-Full 缺口）、Q8（F3/F7 外部 egress/Key 边界）、
Q9（F8/F10 部署只读与总 watchdog 责任）、Q11（F4/F5/F6/F9 验收口径）保持 **OPEN**，分别
延后到 PR3/PR5 或对应 PR；本文件不替维护者做这些决定，也不把未验证项写成 PASS。
