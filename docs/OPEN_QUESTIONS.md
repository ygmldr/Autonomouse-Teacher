# M0 收尾 — 待裁定问题（OPEN QUESTIONS）

- 版本：PR0-v1（2026-11-14 UTC）；执行者 `verify2`
- 关联：[M0_REVIEW_FINDINGS](<M0_REVIEW_FINDINGS.md>)、[M0_CLOSEOUT_ROADMAP](<M0_CLOSEOUT_ROADMAP.md>)、[v0.5 计划](<Autonomous_Teacher_M0_Closeout_Review_and_Implementation_Plan_v0.5.md>)
- 性质：本文件只记录**需要维护者/Lead 明确裁定**或**需后续 PR 解决**的问题；不包含 Agent 自批、不改变 v0.4 验收规范、不声称任何未验证结论。
- 当前总决策不变：**DECISION PENDING；Live/P03/watchdog 等保持 BLOCKED**。

## Q1. 跨机 OCI / 全平台是否属于 v0.4 强制 E5？（最高优先，影响 PR6/PR7 验收口径）

- 现状证据：v0.4 §E5-Full 的强制用例清单为 E5-01…E5-09（`docs/Autonomous_Teacher_M0_v04.md:385-393`），其中**没有**“跨机 OCI 恢复/全平台”条目；但 [M0_REPORT](<M0_REPORT.md>) 在多处把“跨机 OCI 恢复/native 与 pkg cache 官方 export 重放”列为残余 **NOT RUN/BLOCKED**（如 `M0_REPORT.md:276,311`），历史阶段报告也把它列为未做项。
- 用户初步倾向：**仅本机**（不把跨机/全平台作为 M0 强制 E5）。
- 需裁定：Lead/维护者需明确记录：跨机/全平台是 (a) 不属于 M0 v0.4 强制 E5（则 PR6/PR7 只需记录本机范围与残余风险），还是 (b) 属于强制项（则必须补做并可能长期 BLOCKED）；若选 (a) 且与 v0.4 文字有冲突，按 v0.5 §3.2 只能由维护者**显式修订验收规范**，不能由 Agent 私自忽略。
- 阻塞：PR6（E5-Full 收尾）/PR7（最终判定）。
- 保守默认（未裁定前）：按 v0.4 原文 + M0_REPORT 真实范围记录跨机为 **UNVERIFIED/BLOCKED**，不写成 PASS。

## Q2. F1 修复方案：A（M0 推荐）还是 B？broker 协议 v1 兼容怎么做？

- 背景/证据：见 `M0_REVIEW_FINDINGS.md §3`（guard `retry:false`；ledger steps 含 retry 行；`max_retries` 在 guard 路径失效）。仓库已具备 `ledger.py`/`budget.py`/`broker.py`，F1 已从 v0.5 的 Conditional 升级 CONFIRMED。
- 选项：
  - **A（推荐用于 M0）**：最小受限配置禁用 Provider 内部自动重试；所有 logical stream 都计入统一 `max_requests/max_steps`；从措辞中移除“retry 字段精确限制内层重试”，新增“真实 provider policy 也禁用隐藏重试”的验证证据。多数情况下无需改 broker NDJSON 协议（guard 侧/配置/文档 + 测试）。
  - **B（若需要 retry quota）**：仅可信 Agent Loop 的显式 attempt metadata 可标记 retry（不能由学生 prompt/候选插件自报）；需定义 `attempt_id/logical_call_id/attempt_index` 并验证序列/幂等/归因。
- 需裁定：选 A 还是 B；若 B，broker v1 NDJSON 是否升版本/加 `capabilities` 握手（v0.5 PR1 明确不得静默破坏 Phase5 历史 fixture）。
- 阻塞：PR1；A 可先做，B 需先写协议 ADR。
- 保守默认：按 A 准备，任何“retry 限额有效”的对外声明在修复前撤回。

## Q3. F2 容量语义与 `max_messages` 取值

- 背景/证据：`M0_REVIEW_FINDINGS.md §4`。Broker 先查 journal 配额再分 op；测试配置 4096，broker 硬上限 100 000，guard 校验上界 1 000 000（不一致）。
- 需裁定：
  1. 是否采用“新 reservation 容量 + 既有 reservation 完成容量”分离（v0.5 建议）？reserve 前是否强制保留至少 1 个完成 slot？
  2. `snapshot` 是否独立于 reserve 配额（有界频率/大小/存储上界）？
  3. 统一后的 `max_messages` 目标值（4096？100 000？其他），以及 guard/broker 是否握手校验收敛；
  4. 配额是 per-scope lifetime（现实现）还是 per-run 重置语义；历史 DB 迁移/兼容策略。
- 阻塞：PR1（F2 定向测试与实现）。
- 保守默认：至少按“新建配额满时必须仍能完成既有 PENDING 的 settle/fail”修复；在未修前冻结 limits 下不声称该路径已验证。

## Q4. PR1 定向测试是否入库（commit）及取证方式

- 背景：本 PR0 只写 docs/artifacts；`artifacts/` 被 gitignore（`.gitignore:12`）。PR1 需要新增 F1–F6 定向测试（v0.5 §6 的 T-RETRY-01/02、T-JOURNAL-01/02/03、T-SETTLE-01/02、T-ID-01/02、T-LOG-01/02 等）。
- 需裁定：新测试放 `tests/unit/accounting/`、`tests/integration/budget_bridge/` 还是 `tests/security/`（v0.5 §11 建议）；是否必须随修复 commit 入库；运行证据仍落 gitignored artifacts 并配 manifest.sha256；是否要求历史 148/12/18 既有 scope 保留可复验（yes，不应删改）。
- 阻塞：PR1 交付形态/PR7 独立复跑。
- 保守默认：测试随代码入库（非 artifacts 独有），历史测试不删不改，新证据用 artifacts + manifest hash。

## Q5. OpenCode Go 的定位（不得冒充官方 DeepSeek 主路由）

- 现状证据：`docs/ROUTE_DECISION.md:23` 明确 OpenCode Go 仅“可选开发订阅调查”，第三方 API 可接入性 **UNVERIFIED**；“不能当作零成本 Runtime API”；v0.4 §2.3 亦为可选、不阻塞 M0。
- 需裁定：是否允许其仅用于**内部开发测试路由**（不进入 DSH Runtime/不作为 Live 主渠道）；若未来想转正为主渠道，必须先取得官方支持/第三方 API 许可证据、Lead+维护者书面批准、并重跑 E1 及受影响 E2–E4（不能沿用别的渠道 PASS）。
- 阻塞：无（非阻塞）；若误用会污染 Live 证据/验收，属 STOP 条件。
- 保守默认：仅内部开发；不得写入 M0 Live 主路由证据，不得与官方 DeepSeek 主路由混称。

## Q6. PR5 人类前置清单（必须先由维护者完成，Agent 不得代做）

依据 v0.5 §9/PR5、[SECURITY_APPROVALS.md](<SECURITY_APPROVALS.md>)、[THREAT_MODEL.md](<THREAT_MODEL.md>)：

1. 确认主渠道与精确模型 ID（默认 DeepSeek 官方/Flash），并核对供应商当日价目/缓存/额外费用规则、采样时间。
2. 在仓库外独立审查并签核：完整 Git SHA、依赖锁、merged Profile、插件/Tool Registry、主路由、预算/时限；提供完整 inventory 与 SHA。
3. 部署独立于候选的人类授权/凭据边界（LiveGate 允许路径），确保 `--live`/MD/环境变量/Agent 自签不能解锁。
4. 准备**低额度、专用、可撤销** Key；供应商侧硬支出上限若有则设置并留证（软提醒≠硬限额）。
5. 外部 egress/Key Broker/Proxy：固定路由、请求额度、参数上界、请求身份、可计费路径拦截；DSH Runtime 不持有真实 Key。
6. 外部 watchdog：总 deadline、step 上限、进程树 kill、容器清理、崩溃恢复 pending 保守处理。
7. 日志/存储脱敏：无真实 Key/私有评估标签进入公共 artifact；`SESSION_LOG_UPLOAD` 关闭证据。
8. 所有前置完成 → 只能**人工批准一次受限 Live 实验**；Agent 不得自动进入 PR5。
- 阻塞：PR5+；缺任一项 → `BLOCKED`。
- 当前状态：全部 PENDING/BLOCKED。

## Q7. 现有 E5-PreLive / E5-Full 缺口（PR6 前必须闭合或显式改规范）

依据 [M0_REPORT](<M0_REPORT.md>) §4 E5 表（`M0_REPORT.md:137-150`）与 [THREAT_MODEL](<THREAT_MODEL.md>)：

| 项 | 现有真实状态 | 缺口/需谁 |
|---|---|---|
| E5-P01/P02 | 指纹/变更阻断逻辑 PASS；非部署可信基线人工批准 | 需外部部署 + 人工签核 |
| E5-P03 | **BLOCKED**：独立不可伪造的人类授权服务/受保护部署未实现 | 维护者部署（PR3/PR5） |
| E5-P04/P05 | 逻辑/rootfs probe 有证据；真实有凭据控制器的合并工具白名单、最小注入与流向 BLOCKED | 维护者 + PR2/PR3 |
| E5-01/02/03 | rootfs 实际负向 probe PASS（假 Key/跨 home/假私有标签不可读；外网失败；非 scratch 写失败） | 保持；Live 部署需重验 |
| E5-04 | PID/cgroup OOM/podman deadline 证据 PASS | 注意：这不是 Live watchdog |
| E5-05 | rootfs 假私有标签不可见有证据；真实私有评分源/策略部署 NOT RUN | 需真实部署（PR6） |
| E5-06 | 新容器 scratch/恢复探针 PASS；不证明所有可信控制器状态 | 需更完整恢复矩阵 |
| E5-07 | 合并 DSH 权限/危险 Shell/session-log 上传 BLOCKED | 目标 Profile 验证（PR2/PR3） |
| E5-08 | 逻辑 PASS；外部可信部署/再准入未实施 | 维护者 |
| E5-09 | rootfs socket/敏感挂载/无继承 env/cleanup 回归 PASS；**image-based runner OS 执行 BLOCKED** | 需真实 OS runner（PR6） |
| 跨机/全平台 | 见 Q1；M0_REPORT 记录 NOT RUN | 维护者裁定范围 |

- 阻塞：PR6/PR7；未闭合不得 GO/CONDITIONAL GO。

## Q8. F3/F7：外部 egress/Key 边界是否可落地？否则技术 NO-GO 评估

- 背景：F3（后置 digest 非事前费用上限）、F7（缺插件时无法证明不发包）都要求“独立于 DSH 的可信 Controller/egress/Key Broker”。当前 `LiveGate` 恒 BLOCKED、无该边界。
- 需裁定：是否允许/能够部署外部受控 egress/Key 代理（维护者环境、官方受支持接入方式）；若 DSH/SDK 强制 Runtime 直接持有 Key、无法证明 Guard 缺失时阻断开外呼：
  - 选项 A：按 v0.5 目标架构补外部 Proxy/Controller（推荐）；
  - 选项 B：保持 Live BLOCKED，评估替代（官方 TS Runner/公开 JSON-RPC/PydanticAI Adapter）或技术 NO-GO 候选，不得维护侵入式 Fork 硬过。
- 阻塞：PR3/PR4/PR5；无边界不得声称“真实硬费用上限”。

## Q9. F8/F10：部署只读与总 watchdog 的责任归属

- 背景：F8 TOCTOU 需要 config/父目录只读挂载且候选不可写；F10 需外部总 deadline/进程树清理。两者都不是当前仓库代码能单独证明的。
- 需裁定：由维护者部署环境负责证明（mount 身份/SHA、watchdog 实现与测试），还是要求 PR2/PR3 在仓库内提供受限 launcher 侧脚本；验收证据落在哪个 manifest/报告。
- 阻塞：PR2/PR3/PR5。

## Q10. 文档/证据身份与提交

- 现状：HEAD `7c3806b` 已归档 phase5 审计/errata；v0.5 文件未跟踪且按原字节保留（sha256 `b3d85071…`）；本 PR0 新增 3 docs + `artifacts/m0-closeout-baseline/`（gitignored）。`docs/RUNTIME_BUDGET_GUARD.md` 当前 `1d0b62a2…` 与 frozen `feb7118` blob `8fa03fbe…` 不同（task30/31 授权 errata），HEAD 已包含该新版本。
- 需裁定：PR0 三份新文档由谁 commit 到仓库（Agent 按约束不 git add/commit）；是否允许今后写 `M0_REPORT`/`ADR` 增量；v0.5 保持 untracked 还是由维护者另存正式文件。
- 阻塞：无（不影响 PR1 技术执行）；影响证据审计可追溯性。

## Q11. F4/F5/F6/F9 的验收口径（是否需要真实运行时证据）

- F4：需要 broker settle 异常/立即 latch 的运行时负测（T-SETTLE-01/02）；F5：真实 Session ID 碰撞需目标 Runtime 证据；F6：Key/敏感信息哨兵测试需在无 Key synthetic 与未来 Live 边界分别做；F9：真实 wire usage/错误映射只能在 PR4 mock egress/PR5 真实 provider 采集。
- 需裁定：这些是 PR1 离线可完成还是必须等 PR2/PR4 目标 Runtime；哪些可先以 A/B 层证据加“受测限制”进入 CONDITIONAL GO。
- 阻塞：PR1–PR4 排期/验收口径。

---
*本文件不改变任何验收结论；未决项在裁定前一律按保守状态记录（BLOCKED/UNVERIFIED），不得写成 PASS 或 GO 依据。*
