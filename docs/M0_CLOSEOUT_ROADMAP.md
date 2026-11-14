# M0 收尾路线图（PR0–PR7，离线优先，人工门控）

- 版本：PR0-v1（2026-11-14 UTC）；执行者 `verify2`；依据 [v0.5 收尾计划](<Autonomous_Teacher_M0_Closeout_Review_and_Implementation_Plan_v0.5.md>)（sha256 `b3d85071…`，未跟踪原字节保留）
- 基线：HEAD `7c3806b58af2bd49328bdd9bcc53e858a13c35e5`（父/冻结实现 `feb7118`）；当前决策 **DECISION PENDING**，Live/P03/watchdog **BLOCKED**。
- 核心原则：**PR0–PR4 可在无 Key/禁网隔离内离线完成；PR5 起必须由维护者人工审批与真实凭据/外部边界，Agent 不得自动进入或自批。** 不得用 `--live` flag/Markdown/环境变量/Agent 自签解锁 Live；不得改写历史冻结证据。


## 当前状态（M0 收尾 docs 收口，2026-11-14）

PR0–PR4 已完成并冻结；PR5–PR7 待人类，不自动进入。总体 **DECISION PENDING**；Live/P03/真实 egress/Key/usage/账单仍 **BLOCKED**。

| 阶段 | 状态 | 冻结 commit / 证据 |
|---|---|---|
| PR0 | 已完成（docs 基线） | `e8b6e45`；`artifacts/m0-closeout-baseline/manifest.json` `d252c82b…` |
| PR1 | 已完成（离线 F1–F6） | `fdcfdc9`；manifest `df14f3c1…`；V-PR1-1 errata `9fc6fb93…` |
| PR3 | 已完成（无 Key 设计/演练） | `9b77a37`；manifest `b5c16f81…`；V-PR3-1 已修 |
| PR2 | 已完成（目标 Profile dump/F7 缺口） | `7d2cd3e`；manifest `c6ea4e86…`；V-PR2-1 已修 |
| PR4a | 已完成（mock egress/计费路径） | `8cf2476`；manifest `b04afbc9…`；V-PR4A-1 errata `92020bff…` |
| PR4b | 已完成（ProviderObservation/usage 映射） | `c802a32`；manifest `de1bdb07…` |
| Ruff/V-PR3-1 hygiene | 已完成 | `87f44e1`；HEAD repo-wide Ruff `All checks passed!` |
| PR5–PR7 | **待人类 / BLOCKED** | 见 [CLOSEOUT_REPORT](<M0_CLOSEOUT_REPORT.md>) §7–8 |

裁定与汇总见 [M0_CLOSEOUT_DECISIONS](<M0_CLOSEOUT_DECISIONS.md>) 与 [M0_CLOSEOUT_REPORT](<M0_CLOSEOUT_REPORT.md>)；本表的“已完成”仅指离线/无 Key 声明范围，不是 Live/E1–E5/GO。

## 0. 当前仓库状态映射（PR0 起点，静态核对）

| 领域 | 现状（证据） | 对路线图含义 |
|---|---|---|
| 冻结实现 | `feb7118`（phase5 插件+文档）；HEAD `7c3806b` 只归档 docs/审计 | 实现身份稳定；PR1 起必须新 commit，不得覆写 phase5 历史 |
| 离线验证基线 | 全量 326（含 89 子集）、broker 148、SDK 17、插件 8、guard 12+18 均在隔离内 PASS（B 层，`REVIEW_PHASE5`/`phase5 manifest 391767d3…`） | 可作为 PR1–PR4 回归基线；**不是 Live/C 层证据** |
| E1–E5 真实验收 | 整体 BLOCKED：无真实模型/Usage/费用；E5-P03 人类授权未实现；E5-05/07/08 及 image-runner E5-09 未完成（`M0_REPORT.md §4`：137-150） | PR5/PR6/PR7 的门槛；PR0–PR4 不能改变该结论 |
| 预算守卫 | logical-stream pre-adapter middleware 已交付（B 层）；broker 为 fixed-scope bookkeeping，非授权/Key 代理/usage 认证/账单上限 | PR1 修 F1–F6；PR3/PR4 补外部边界 |
| Broker/Ledger | `ledger.py`/`broker.py`/`budget.py`/`broker_usage.py` 齐全；F1/F2 语义已静态确认 | PR1 首选目标（无协议破坏或版本化兼容） |
| Adapter | `dsh_adapter.py` 所有 Live 入口 fail-closed（`SECURITY_BLOCKED`）；Usage/模型/请求 ID 全 None；错误分类仅 HTTP 形状 | PR2/PR3 联调与 ProviderObservation |
| Live 门 | `security/gates.py` 恒 BLOCKED；`scripts/run_live.sh` exit 3；`SECURITY_APPROVALS.md` PENDING | PR5 只能人工打开，PR3 不授予 Live |
| F1–F10 | PR0 已固化：[M0_REVIEW_FINDINGS](<M0_REVIEW_FINDINGS.md>)；2 个 Live P0（F3/F7）+ 其余 P1（静态） | PR1–PR4 输入 |
| 待裁定 | [OPEN_QUESTIONS](<OPEN_QUESTIONS.md>)（E5 范围、F1/F2 方案、PR1 测试入库、OpenCode Go、PR5 前置、E5 缺口、外部边界） | 部分 PR 的前置决策 |

## 1. PR 总览与门禁

| PR | 目标 | 依赖 | 是否离线 | 交付 | 退出/验收门 | 退路 | Owner 角色 | 人审门 |
|---|---|---|---|---|---|---|---|---|
| **PR0** | 固化来源/缺口/F1–F10 | 无 | 是（本次） | `docs/M0_REVIEW_FINDINGS.md`、`docs/OPEN_QUESTIONS.md`、`docs/M0_CLOSEOUT_ROADMAP.md`、`artifacts/m0-closeout-baseline` | 所有文件/SHA 对应；F1/F2 语义不猜；未解释标 UNVERIFIED | 无 | Verification（verify2） | 无（但需 Lead 接受） |
| **PR1** | Broker/Guard 协议修复（F1–F6） | PR0 | 是 | 最小代码 diff、定向测试、协议说明、离线运行日志 | F1–F6 定向测试 PASS；失败时不出现“无预留 dispatch”；148/12/18 历史 scope 可复验 | F1 不可观测 retry → 先用方案 A 禁用并记录限制 | Accounting + Runtime + Guard-plugin | 无（离线），需独立复核 |
| **PR2** | 目标 DSH Runtime/插件一致性联调 | PR0；PR1 集成 | 是（无 Key synthetic） | `docs/DSH_TARGET_PROFILE.md`、profile 验证脚本、Synthetic manifest/trace | 目标 Runtime 重启加载 ≥3 次；工具真实注册；Guard 缺失/错误 config/Broker down 外部拒绝 | 插件 ABI 不兼容 → 官方同版/公开扩展点/记录成本；侵入式 Fork 需评估 NO-GO | Runtime + Security | 无（无 Key）；Guard 缺失负测证据独立复核 |
| **PR3** | 可信 Live Controller 设计与无 Key 故障验证 | PR0；可与 PR2 并行 | 是（**不授予 Live**） | `docs/LIVE_CONTROLLER_SECURITY_DESIGN.md`、无 Key 测试、`E5_PRELIVE_NO_KEY_REPORT.md` | 负向用例拒绝并留证；授权不可由 Agent 改；Profile 与实际一致；**此 PR 完成仍不代表 Live 批准** | 若无法建立独立授权/凭据边界 → Live BLOCKED/技术 NO-GO 候选 | Security/Controller | **PR3 结束提交人工审阅；不得自动进 PR5** |
| **PR4** | 真正请求/费用边界（mock egress，无真 Key） | PR1/2/3 | 是 | `docs/BILLABLE_PATH_INVENTORY.md`、`docs/PROVIDER_USAGE_MAPPING.md`、mock-egress 测试/日志、失败矩阵 | 所有计费路径列入清单；未预留/超限/未批准在发包前拒绝；每个外呼稳定 ID；区分 local hard bound vs provider invoice cap | 若隐藏计费请求不可控 → 用受控一处性/低权限转发，真实硬预算标未通过 | Security/Controller + Runtime | 无真 Key；设计需维护者预审 |
| **PR5** | 人工审批后的最小 Live 实验 | PR1–4 + 安全审核 + 可撤销低额度凭据 | **否（禁止 Agent 自行执行）** | `artifacts/live-m0/manifest.json`、脱敏 Trace、受信账单核验、`E1_E2_E3_LIVE_REPORT.md` | LIVE-00 负测 → LIVE-01 3/3 → JSON → 工具 3/3 → Session 3/3 → 安全错误；Usage/费用可核；任一前置缺失 → BLOCKED | 官方 API 不可用 → 人类事前批准同模型备用路由并重跑受影响验收；不自动切换 | 维护者 + 受信 Controller | **仅维护者主动触发；人类外部授权** |
| **PR6** | E4 配对实验 + E5-Full 收尾 | PR5；与 Live 无关 E5 子项可提前 | 部分（E5 离线子项）；E4 真实 6 对需 PR5 | `E4_PAIR_REPORT.md`、`E5_FULL_REPORT.md`、原始 manifest | 20 Mock 可复现；6 真实配对完整记录、评估器独立；E5 必选项完成或显式 BLOCKED | E5 无解 → 维持 BLOCKED/维护者改规范（不得删测） | Verification + Security | E5 需维护者部署/范围裁定（Q1/Q7） |
| **PR7** | 独立验收、ADR 与冻结 | PR0–6 必选范围 | 否（含 Live 证据） | 新冻结 SHA、独立复核报告、更新 `M0_REPORT`/`ADR`（仅增量）、最终决策 | 非实现者用冻结字节重跑关键测试；交叉核 Live trace/Usage/费用/授权；逐项 E1–E5 PASS/FAIL/BLOCKED/NOT RUN；不覆写历史 | 证据不足 → 保持 DECISION PENDING；安全缺口 → NO-GO | Verification（独立）+ Lead + 维护者 | **最终人类签核** |

## 2. 各 PR 详细门禁与验收

### PR0（本次，已交付）
- 交付：F1–F10 状态/证据/影响/修复/回归/owner/历史影响（[M0_REVIEW_FINDINGS](<M0_REVIEW_FINDINGS.md>)）；待裁定项（[OPEN_QUESTIONS](<OPEN_QUESTIONS.md>)）；本路线图；基线 manifest（HEAD/status/v0.5 sha/4 源哈希比对/tracked 清单 122/hash/rootfs/deps/podman/tools/UTC/argv+exit）。
- 验收：静态确认 F1/F2 语义；F1/F2 升级 CONFIRMED；未解释项 UNVERIFIED；不写 PASS；未运行测试/容器/Live。
- 未决：Q1（E5 范围）、Q2/Q3（PR1 方案）、Q4（测试入库）等见 OPEN_QUESTIONS。

### PR1 — Broker/Guard 修复（离线）
- **输入**：PR0 发现；`index.ts`、`accounting/{ledger,budget,broker,broker_usage}.py`、`tests/unit/accounting`、`tests/integration/budget_bridge`。
- **实现**（v0.5 最小集）：F1 明确 retry 政策（推荐方案 A）；F2 完成容量/新请求容量分离 + 有界 snapshot/recovery；F4 `accounting_status`+fail-closed latch；F5 哈希化稳定 ID；F6 阶段化日志/错误码 allowlist/密钥哨兵；F3 保留后置 digest 仅作审计、不宣称事前拦截。
- **接口注意**：若改 broker NDJSON → 显式 `protocol_version`/`capabilities` 或兼容解析，不得静默破坏 phase5 历史 fixture；历史冻结日志不改。
- **验证**：T-RETRY/T-JOURNAL/T-SETTLE/T-ID/T-LOG 定向测试全 PASS；deny/unavailable/settle 失败路径无 provider dispatch；148 broker、12 guard、18 selftest 历史 scope 可复验（或通过兼容 fixture 解释预期变更）。
- **退路**：retry 内层不可观测 → 方案 A 先禁用并记录受测限制，不预测内层行为。
- **Owner**：Accounting（F1/F2/F4 账本/协议）+ Runtime（F4/F6）+ Guard-plugin（F5/F6）；Verification 独立复核。

### PR2 — 目标 Runtime 联调（离线）
- **输入**：PR0/PR1；锁定 SDK Runtime（wheel `0.2.2rc2`/CLI `0.2.2-rc.2`）；npm 插件 ABI `0.2.1-rc.2` 与目标 Runtime 兼容性未确认。
- **交付**：`docs/DSH_TARGET_PROFILE.md`；`scripts/verify_runtime_profile.*`（无凭据环境）；Synthetic manifest/trace。
- **验收**：目标 Runtime ≥3 次重启加载；实际 ToolSet/Provider registry/merged profile 有证据；Guard 缺失/import 失败/错误 config/broker down/额外 provider 时无计费外呼（synthetic 网络计数哨兵）；记录二进制/插件哈希。
- **退路**：公开插件 ABI 不兼容 → 官方同版/公开扩展点/TS Runner；长期侵入式 Fork → 评估技术 NO-GO。
- **Owner**：Runtime + Security。

### PR3 — 可信 Controller 设计（无 Key，停止点）
- **输入**：PR0；可并行 PR2。
- **交付**：`docs/LIVE_CONTROLLER_SECURITY_DESIGN.md`；无 Key 故障验证；`E5_PRELIVE_NO_KEY_REPORT.md`。
- **任务**：不可由 Agent 自签的 `ExecutionAuthorization`（code SHA/锁/Runtime/插件/profile/route/工具/预算/时限/过期/撤销）；独立授权与凭据边界；外部 watchdog；假凭据/假私有标签注入负测；禁止候选触及 Key Proxy/通用 URL 代理。
- **验收**：全部负向用例拒绝并留审计证据；授权不可由 Agent 修改；Profile 与实际一致；**完成不代表 Live 批准**。
- **退路/停止**：无法建立独立授权/凭据边界 → Live 保持 BLOCKED；技术 NO-GO 候选评估。
- **人审门**：**PR3 结束提交人工审阅，不得自动进入 PR5/索取真实密钥。**

### PR4 — 请求/费用边界（mock egress，无真 Key）
- **输入**：PR1/2/3。
- **交付**：`docs/BILLABLE_PATH_INVENTORY.md`、`docs/PROVIDER_USAGE_MAPPING.md`、mock-egress 测试/日志、失败矩阵。
- **任务**：Mock HTTP/本地受控 egress 观察 logical stream 对应的真实 HTTP attempt/retry/cache/Files/compaction；列出所有计费/可能计费路径；最靠近发包处固定路由/额度/参数上界/请求身份/账本预留；缺 usage/SDK hang/重试不确定 → worst-case；明确 local hard accounting bound ≠ provider invoice cap；每次 Live call 最多一次批准尝试。
- **验收**：无法越过外部 egress/Key 边界直接发请求；未预留/超预算/未批准在发包前拒绝；每个外呼稳定可关联 ID。
- **退路**：隐藏计费不可控 → 受支持低权限转发/固定一次性短会话，并标“真实硬预算未通过”。

### PR5 — 最小 Live（维护者主导）
- **前置**：PR1–4 + 安全审核 + 真实可撤销低额度凭据 + Q6 清单全部完成；任一缺失 BLOCKED。
- **用例顺序**：LIVE-00 健康检查（无凭据）→ LIVE-01 3/3 smoke → LIVE-02 严格 JSON → LIVE-03 模型实际 `skill_lookup` → LIVE-04 跨进程 Session 3/3 → LIVE-05 安全错误（真实 401/429/5xx 若不可安全触发，可外部注入并注明 synthetic error）→ LIVE-06 Usage/请求身份/费用/不一致状态。
- **预算**：延续 US$3 软/US$10 硬目标/50 次 Live 调用上限；真实硬约束需 provider/egress 证据；做不到则低额度实验仅研发诊断，不自动满足完整 GO 费用验收。
- **禁止**：Agent 自行执行、CLI/MD/env 解锁、自动换路由。

### PR6 — E4 配对 + E5-Full
- **E4**：20 Mock 保留；加明确优劣 counterfactual fixtures；至少 6 对真实 `teacher_v0/v1`，独立 Session/顺序/评分/成本；无法可信 Usage 则该费用项不 PASS；Mock 对照不证明人类学习增益。
- **E5-Full**：按 v0.4 E5-01…E5-09 逐条（假 Key/其他 home/私有标签/网络/socket/写限制/资源/崩溃恢复/merged profile）；若 `ContainerRunner.run()` 未端到端且规范强制 → 保持 BLOCKED 或维护者改规范；不得用 rootfs 命令结果冒充 Runner.run。
- **范围**：跨机/全平台按 Q1 裁定。

### PR7 — 独立验收/ADR/冻结
- 新冻结 SHA；禁止覆写旧 phase5 history；记录所有修复 PR SHA/实际日志。
- 独立非实现者用冻结字节重跑关键 Python/Broker/插件/SDK/Guard tests；交叉核 Live trace/Usage/费用/授权。
- 更新 `M0_REPORT`/`ADR-001` 仅增量：逐项 E1–E5 PASS/FAIL/BLOCKED/NOT RUN；不同子集不相加；最终按 v0.4 §10 判定矩阵给出 GO/CONDITIONAL GO/NO-GO/PENDING。
- 不满足安全/费用/授权 → 保持 PENDING/BLOCKED，不得用 CONDITIONAL GO 绕过 E5 FAIL。

## 3. 全路线不变量（每 PR 必守）

来自 v0.5 §6.1，PR1–PR7 每次回归必须守住：
- I1 未批准 code/profile/route/authorization → 无可计费外呼。
- I2 无成功 reservation → 无 provider dispatch。
- I3 重复 reservation/message ID → 绝不第二次 dispatch。
- I4 unknown/missing Usage → 不静默为零，保守 pending/held。
- I5 accounting uncertain → 不得报完整 PASS。
- I6 候选/未审查插件不继承凭据或评估器权限。
- I7 A/B synthetic 结果不得标 C/Live。
- I8 SDK 类型不泄漏到项目核心契约。
- I9 optional route 失败本身不降级 GO。
- I10 任一已批准字节变化 → 旧 Live 授权失效。

**Stop 规则**（v0.5 §7.2）：Guard 未装载/egress 可绕过；未预留但 provider 已开始；实际路由≠批准路由；unknown/uncertain settlement 后仍能启动可计费请求；真实 Secret 出现在候选环境/输出/日志/artifact；watchdog 不能终止超时 Runtime/工具；成本/请求数达限或无法界定剩余费用；已批准源码/依赖/Profile/Tool Registry 变化。任一发生 → 停止、撤销凭据、保留证据、人工复核；不得因“只剩几个用例”继续。

## 4. 依赖图与并行度

```text
PR0 (本PR，静态基线)
 ├── PR1 (Broker/Guard 修复，离线) ──┐
 │                                   ├── PR4 (mock egress/费用边界，离线) ── PR5* ── PR6* ── PR7*
 ├── PR2 (目标 Runtime 联调，离线) ──┤        *PR5+ 需维护者人工授权/真实凭据/外部边界
 └── PR3 (可信 Controller 设计，离线；停止点供人审)
```

- PR1 与 PR2 可部分并行；PR3 与 PR2 并行；PR4 依赖 PR1/2/3；PR5 依赖 PR1–4 + 人工门。
- **PR0–PR4 允许 Agent 无问答执行（0 真实 API 调用）**；PR5 起必须人工。
- 每 PR 结束：Lead 审核 + 独立证据（manifest/hash/argv/UTC/exit）；PR7 最终独立审计。

## 5. 交付目录映射（按 v0.5 §11）

| PR | 交付路径（建议沿用仓库结构） |
|---|---|
| PR0 | `docs/M0_REVIEW_FINDINGS.md`、`docs/OPEN_QUESTIONS.md`、`docs/M0_CLOSEOUT_ROADMAP.md`、`artifacts/m0-closeout-baseline/` |
| PR1 | `plugins/runtime-budget-guard/`、`src/autoteacher_m0/accounting/` 最小 diff、`tests/unit/accounting/`、`tests/integration/budget_bridge/`、协议说明、`artifacts/m0-closeout-fix-tests/` |
| PR2 | `docs/DSH_TARGET_PROFILE.md`、`scripts/verify_runtime_profile.*`、`artifacts/m0-runtime-integration/` |
| PR3 | `docs/LIVE_CONTROLLER_SECURITY_DESIGN.md`、`E5_PRELIVE_NO_KEY_REPORT.md`、无 Key 测试/部署清单 |
| PR4 | `docs/BILLABLE_PATH_INVENTORY.md`、`docs/PROVIDER_USAGE_MAPPING.md`、mock-egress 证据、`artifacts/m0-egress-validation/` |
| PR5 | `artifacts/live-m0/manifest.json`、脱敏 Trace、受信账单核验、`docs/E1_E2_E3_LIVE_REPORT.md`（仅批准后） |
| PR6 | `docs/E4_PAIR_REPORT.md`、`docs/E5_FULL_REPORT.md` |
| PR7 | 新冻结 manifest/独立复核报告；`docs/M0_REPORT.md`、`docs/ADR-001-runtime.md` 增量 |

## 6. 当前阻塞与下一步

- **立即可做（离线，不需要人类凭据）**：按 [OPEN_QUESTIONS](<OPEN_QUESTIONS.md>) 裁定 F1/F2 方案后进入 PR1；Q4 测试入库策略需先定。
- **人工门（维护者）**：Q1（E5 范围）、Q5（OpenCode Go 定位，非阻塞）、Q6（PR5 前置）、Q7（E5 缺口闭合）、Q8/Q9（外部边界/watchdog 责任）。
- **不可做**：任何真实模型/Key/HTTP、LiveGate 打开、用 CONDITIONAL GO 绕过 E5、改历史冻结证据、让 Agent 自批或自签授权。
- 当前判定：**DECISION PENDING；Live BLOCKED**；PR1–PR4 完成也不自动改变该判定，必须 PR5–PR7 证据与人工签核。
