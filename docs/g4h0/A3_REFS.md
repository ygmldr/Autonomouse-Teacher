# A3 引用清单与既有文档差异/冲突登记

- **用途**：为 [`DEPLOYMENT_RUNBOOK.md`](DEPLOYMENT_RUNBOOK.md)、[`TRUST_BOUNDARY_DIAGRAM.md`](TRUST_BOUNDARY_DIAGRAM.md)、
  [`HUMAN_SIGNOFF_TEMPLATE.md`](HUMAN_SIGNOFF_TEMPLATE.md)、[`E5_PRELIVE_FULL_CHECKLIST.md`](E5_PRELIVE_FULL_CHECKLIST.md)
  提供统一引用索引，并显式登记与既有文档的差异、可能歧义与需维护者确认的冲突点。
- **基线**：`3e7afee077845a071cd364e93ab209cac20b2d5f`（行号以此为准；后续文档变动需 append 勘误）。
- **性质**：`DESIGN_PENDING_HUMAN`；不是授权、不是部署证据、不是 E5 Full PASS。

---

## 1. 引用清单（按主题）

| # | 文档 | 本套文档使用点 | 关键位置 |
|---|---|---|---|
| R-01 | `docs/LIVE_CONTROLLER_SECURITY_DESIGN.md` | 信任边界、授权字段、凭据边界、watchdog、仍 BLOCKED 项 | §1 `:27-36`；§2 `:38-60`；§3 `:62-87`；§4 `:89-110`；§5 `:121-132`；§6 `:134-145`；§8 `:169-179`；§9 `:181-194` |
| R-02 | `docs/SECURITY_APPROVALS.md` | 审批模板现状、禁止把 Markdown 当授权、人工部署要求 | `:3-10`；`:26-42`；`:44-59` |
| R-03 | `docs/BUDGET_BROKER.md` | bookkeeping 边界、startup policy、reserve/settle、错误码、PR1 容量/归因 | `:3-17`；`:19-72`；`:90-147`；`:162-169`；`:232-262`；`:422-460` |
| R-04 | `docs/E5_PRELIVE_NO_KEY_REPORT.md` | E5-P01..P05 no-key 子集结果、证据等级 | `:12-28`；`:34-45`；`:47-58`；`:70-89` |
| R-05 | `docs/M0_G4_A_AUTHORITY_CONTRACT.md` | 人类信任根职责、严格 JSON、5 根闭包、TOCTOU、预算权威源、单次消费、残余 | §2 `:64-70`；§5 `:105-123`；§7 `:147-174`；§8 `:178-226`；§10 `:247-273`；§11 `:277-286`；§13 `:326-344`；§14 `:350-367` |
| R-06 | `docs/M0_G4_C_EGRESS_CONTRACT.md` | 唯一发送路径、TrustedSendAuthorization、预算阈值、pre_dispatch、残余 | §0 `:23-35`；§1 `:39-118`；§2 `:121-178`；§3 `:181-207`；§4 `:210-247`；§7 `:313-325` |
| R-07 | `docs/M0_G4_D_E5_NO_KEY_REPORT.md` | watchdog 真实进程/absence/Kill 失败关闭、D05/D06/D07/D09/D15、E5 两列 | §2 `:67-121`；§3 `:124-153`；§4 `:157-186`；§5 `:188-202`；§6 `:206-230`；§7 `:234-244`；§10 `:289-298` |
| R-08 | `docs/M0_G4F_REVIEW_ERRATA.md` | 最终状态常量、冻结输入格式、P2 八项、E5 两列、Packet 冻结、待决定清单 | §1.1 `:12-19`；§1.2 `:21-34`；§2 `:57-98`；§4 `:128-166`；§4.3 `:152-158`；§5 `:170-185`；§6 `:191-227`；§9 `:263-275`；§10 `:279-301` |
| R-09 | `docs/REVIEW_G4F_INDEPENDENT.md` | 独立复核先例、F4 残余、E5-P04、证据等级、未验证项 | `:182-188`；`:238`；`:251-255`；`:272-278`；`:353-354` |
| R-10 | `docs/M0_G4_HUMAN_HANDOFF.md` | G4-H-01..06、供应商硬额度语义、P2 签收、E5 Full 人工执行 | `:10-22`；`:46-103`；`:107-142`；`:146-156` |
| R-11 | `docs/M0_G4F_HUMAN_HANDOFF.md` | H-01..H-12 人工项（Key、价格、信任根、F4、registry、hooks、撤销链） | `:11-26`；`:30-36` |
| R-12 | `docs/DSH_TARGET_PROFILE.md` | synthetic target profile、dump-config、静态 opencode-go 行、残余 UNVERIFIED | §1 `:6-11`；§2 `:13-22`；§3 `:24-35`；§5 `:41-44` |
| R-13 | `docs/BILLABLE_PATH_INVENTORY.md` | 计费路径 B1–B10、egress 原型、失败矩阵、UNVERIFIED | §1 `:9-22`；§2 `:24-52`；§3 `:54-64`；§4 `:66-73` |
| R-14 | `docs/OPENCODE_GO_ACCESS.md` | G5 最小 smoke 设计、Key 注入约束、失败/停止条件、session header 缺口 | §2.5 `:197-207`；§3 `:208-270`；§4 `:272-303` |
| R-15 | `docs/E4_MOCK_REPORT.md` | 预算守卫默认值、离线证据边界、container 限制示例 | `:3-10`；`:13-15`；`:55-62` |
| R-16 | `docs/M0_RUNBOOK.md` | 环境/工具基线、Live 恢复条件、artifacts 不能作为最终证据 | `:39`；`:51-56`；`:147-153` |
| R-17 | `docs/THREAT_MODEL.md` | 基础资产/角色/信任与 OS 负测参考 | `:29-43`；`:65-107`；`:108-163` |
| R-18 | `docs/Autonomous_Teacher_M0_v04.md` | E5-PreLive P01–P05、E5-Full E5-01..E5-09、门禁语义 | `:350-364`；`:366-395` |
| R-19 | `src/autoteacher_m0/security/gates.py` | `LiveGate` 恒 BLOCKED、无 authorize 路径、四类原因 | `:1-6`；`:63-86` |
| R-20 | `scripts/run_live.sh` | `exit 3` 硬停 | `:1-5` |
| R-21 | `docs/M0_G4_B_RUNTIME_INVENTORY.md` | merged registry 无权威导出、per-dispatch 兜底 | §4 `:155-181` |
| R-22 | 执行方案只读副本（仓库外 `Autonomous_Teacher_M0_M1_Parallel_Execution_Plan_v1.0.md`） | A3 交付范围、角色、验收矩阵 A-06/A-07、维护者决策卡 | §3；§4 A3；§8；§11 |

---

## 2. 与既有文档的差异（非冲突，已在本套文档中说明）

| # | 差异 | 说明 |
|---|---|---|
| DF-01 | PR3 设计把 Ed25519 托管/Key Broker/Egress 列为“后续 PR/人类项”；本套 A3 文档把它们展开为**可执行部署 Runbook + 信任边界 + 签核模板** | 执行方案 A3 明确要求；不改变 PR3 的 BLOCKED 结论 |
| DF-02 | `E5_PRELIVE_NO_KEY_REPORT.md:34-45` 与 errata 把 E5-P05 NO_KEY_SUBSET 记为 `PASS`；本清单把其中“watchdog 执行腿未独立重跑”单列为子项 `PARTIAL` | 更严格的证据登记，不推翻 errata；整体 Full 仍 BLOCKED（`docs/M0_G4F_REVIEW_ERRATA.md:180`） |
| DF-03 | PR3 §3.2 budget 约束写 `per_call_cap ≤ total_cap ≤ 10`、`max_calls ∈ [1,50]`；Runbook §7 另列 soft/hard **call** 线（0.10/0.20）与工程 tokens/steps 目标 | 分别来自 G4-A 冻结常量（`docs/M0_G4_A_AUTHORITY_CONTRACT.md:249-254`）与 E4 默认；层次不同（授权文档字段 vs 本地策略目标），不构成矛盾 |
| DF-04 | Runbook 统一把 `$3/$10/≤50` 表述为“M0 工程目标”，不用“硬封顶” | 对齐 G4 人工交接与 SECURITY_APPROVALS 的口径（`docs/M0_G4_HUMAN_HANDOFF.md:87-103,146-156`；`docs/SECURITY_APPROVALS.md:52-53`） |
| DF-05 | 本套文档的证据目录为**仓库外** `<TRUSTED_DEPLOY_ROOT>/evidence/`；既有 no-key 文档引用 `artifacts/`（gitignored） | `docs/M0_RUNBOOK.md:39` 已说明 artifacts 不能作最终部署证据；两者并存，不互相替代 |
| DF-06 | `docs/M0_RUNBOOK.md` 是 foundation 基线 runbook；本套是 G4-H0 受信部署 runbook | Runbook §12/§13 已交叉引用；`scripts/run_live.sh` 的提示文字未改（不得改） |
| DF-07 | Packet v1 存在 P2-01 sidecar/P2-02 路径/P2-07 reasons 缺陷；本套文档要求“接受并记录或发布 v2” | 与 errata §4 一致，不重打包、不改 v1 字节 |
| DF-08 | E5-Full 中 `E5-06`（crash 候选后新容器可执行）在 no-key 证据中只有 F4 部分恢复场景 | 与 errata/Reviewer 的 UNVERIFIED 结论一致（`docs/M0_G4F_HUMAN_HANDOFF.md:23`） |

---

## 3. 需维护者确认的冲突/歧义点（当前不阻塞文档，但阻塞真实部署）

| # | 冲突/歧义 | 现状 | 建议 |
|---|---|---|---|
| C-01 | P2-03 并发消费错误码竞态：执行方案建议 **G4-H1 前修复**；G4-F errata 判定**不阻断 no-key closeout** | fail-closed，无发送/计费，但错误码不稳定（`docs/M0_G4F_REVIEW_ERRATA.md:152-158`；执行方案 A1） | 真实受信部署（G4-H1）前修复或维护者书面接受；未修复不得把并发/撤销演练写 PASS |
| C-02 | P2-05 `timeout-pre-send` 无 dispatch-window 记录；P2-06 撤销 reason 被 recovery 重写 | 观察缺口，未导致重发/双结算（`docs/M0_G4F_REVIEW_ERRATA.md:134-135,160-166`） | 部署前补记录/修正映射，或在 Risk Disposition 中明示接受 |
| C-03 | E5-P04 / merged registry `UNVERIFIED` | DSH 无权威导出 API；现仅 per-dispatch 白名单兜底（`docs/M0_G4_B_RUNTIME_INVENTORY.md:155-181`） | 人类决定：技术闭环（提供导出）或明示接受残余并写补偿控制 |
| C-04 | P2-RUN-IDENTITY / USERNS / DISK 未签收 | 影响同 UID 旧 run 与内核攻击面 | G4-H-05 前置；签收或另立加固工作项 |
| C-05 | host `RLIMIT_NPROC` 对 root 无效 | D09 `PARTIAL`，只有容器 cgroup `pids.max` 证据 | 以 cgroup 限制为部署依据并明文签收 NPROC 残余 |
| C-06 | 撤销链无独立签名、root-owned 输入 | F5-R2 已登记（`docs/M0_G4F_HUMAN_HANDOFF.md:22`） | 决定是否要求签名撤销链；Runbook §4.5 已给出流程但未实现 |
| C-07 | 测试种子 `TEST_ONLY_` 与正式根的命名/注册隔离 | 代码拒绝未注册 key，但命名空间隔离是部署侧约定 | 在 `trusted-keys.json` 注册流程中显式拒绝 `test-only-*`；写入手册并演练 |
| C-08 | 内部 `per_call_usd`（broker fixture 示例 0.20）与 G4-A 常量 `hard_call_usd=0.20`/`soft_call_usd=0.10` | 数值相容，但属不同层（broker policy vs controller 常量） | 部署时明确两处均由同一维护者策略冻结，并在授权中逐字段绑定 |
| C-09 | `docs/OPENCODE_GO_ACCESS.md §4` 建议 2 次 smoke；执行方案建议 G5 ≤3 次请求 | 两者相容（2 ≤ 3） | G5 授权写 ≤3 次，实际执行按 OpenCode §4 的 2 次最小设计；任何额外请求需新授权 |
| C-10 | 真实 Provider route 未批准；`target-runtime-opencode-go.patch.yml` 为 STATIC-ONLY | 若维护者未来选择 OpenCode Go，仍需供应商契约/额度/TLS/账单核验与 AB 测试（A2） | 不得把静态 profile 行当“已批准路由”；Runbook §6 已限制 |
| C-11 | 历史文档行号会随其它 A 线交付物变动 | 本索引以 `3e7afee` 为准 | 后续 docs 提交若移动这些行，append 勘误并更新引用，不改历史结论 |
| C-12 | 本套文档引用的 A 线并行交付物（`BASELINE.md`、`RISK_DISPOSITION.md`、`PROVIDER_CONTRACT_DRAFT.md` 等）可能不在本分支 | Runbook §3 已把缺失标为 BLOCKED，不用推测补齐 | 由 Lead 汇总时确认各交付物归属分支与 SHA |

---

## 4. 与既有文档“不冲突”的明确保证

- **未改变任何现有语义**：`LiveGate` 恒 `BLOCKED`、`run_live.sh` exit 3、CLI/Adapter 拒绝、授权 5 根绑定、
  单次消费、`TrustedSendAuthorization` 一次性、broker 的 `dispatch_allowed` 含义、Packet 不可变。
- **未把任何设计/待人类项写成已实现**：本套文档中 `VERIFIED/PARTIAL` 仅指仓库内已有证据；所有部署组件
  标 `BLOCKED`/`DESIGN_PENDING_HUMAN`/`HUMAN_REQUIRED`。
- **未新增真实 Key/凭据/网络/个人数据**；示例均为占位符。
- 如后续独立 Reviewer 发现本套文档与既有结论矛盾，按 append-only 方式在本文件末尾追加勘误，不改历史字节。

## 5. append-only 版本记录

| 版本 | UTC | 内容 |
|---|---|---|
| v1 | 2026-11-19T17:50Z | 初始引用索引、差异 DF-01..08、待确认 C-01..12 登记 |
