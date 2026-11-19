# M1 Offline Teacher — B 线并行状态（STATUS）

| 字段 | 值 |
| --- | --- |
| 更新时间 | 2026-11-19（UTC；C2 复核后定稿） |
| 维护者 | `b-reviewer`（本文件随 B5/B8 独立复核交付；Lead 统一提交） |
| 工作树 | `/root/at-m1-offline`（branch `work/m1-offline-design`） |
| base SHA | `3e7afee077845a071cd364e93ab209cac20b2d5f`（main；主工作树 clean） |
| 第一轮冻结 impl/docs SHA | `0bb13d27b069dfb71b31ce7e02f9cde41f9bb071`（commit `2026-11-19T18:25:22+00:00`） |
| **当前 SHA（复核后修复 C2）** | **`052d980d9a45558da8789c90725ae6c48f3f7a7d`**（commit `2026-11-19T18:56:21+00:00`；`fix(m1-offline): post-review P1/P2 fixes — persisted failure cases, precise provenance, reproducible fingerprint, doc consistency`） |
| 复核文档提交 C3 | `pending`（本文件、`docs/m1/REVIEW_M1_OFFLINE.md`、`docs/parallel/DECISION_LOG.md`；Lead 在复核完成后统一提交；未包含在 C2） |
| 当前 B 线状态 | **REVIEWED + STOP**（离线设计与评测范围，`PASS_FOR_M1_OFFLINE_DESIGN_AND_EVALUATION_SCOPE`；等待维护者/人类决策；不接真实 Runtime） |

---

## 1. 六项同步（Current SHA / Done / Evidence / Blocked / Next / Human Decision）

### 1.1 Current SHA

- `base`: `3e7afee077845a071cd364e93ab209cac20b2d5f`
- `impl/docs frozen（第一轮）`: `0bb13d27b069dfb71b31ce7e02f9cde41f9bb071`（145 个新增文件）
- `post-review fix（C2，当前 HEAD）`: `052d980d9a45558da8789c90725ae6c48f3f7a7d`（相对 `0bb13d2`：12 M + 1 A，全部在允许路径；M0 冻结区零改动）
- `review docs（C3）`: `not yet committed`（3 个 review/parallel docs；由 Lead 提交）
- 主工作树 `/root/Autonomous Teacher`: HEAD `3e7afee…`，`git status` clean；B 线未写入主工作树。

### 1.2 Done

- B1 Teacher Core（types/schema、Learner Model、Hint Ladder、Curriculum Planner、Learning Memory、Mock Runtime Port）— 完成并冻结于 `0bb13d2`。
- B2 CF Teacher（14 题 / 112 隐藏用例 / 3 学习者 / 本地 judge / 诊断 / Hint Ladder）— 完成并冻结。
- B3 Interview Coach（22 题 / 6 JD / 4 注入 / 9 答案 / 7 hidden + 独立 rubric + 项目事实边界）— 完成并冻结。
- B4 Freshness（9 组 KEEP/UPDATE/RECHECK + 时间语义 + 课程写入门禁）— 完成并冻结。
- **B5/B8 独立复核（两轮）**：第一轮 @`0bb13d2` 发现 P1-1 + P2-1..P2-6；Lead 安排 owners 修复形成 **C2**；Reviewer 在 clean C2 上完整重跑 A–J 并逐项复验，确认 **P1-1 与 P2-1..P2-6 全部关闭**、无新 P0/P1；新增 P2-7（report JSON 含生成时间戳）以 disclosed/deferred 记录。
- **交付文档**：`docs/m1/REVIEW_M1_OFFLINE.md`（最终裁定 `PASS_FOR_M1_OFFLINE_DESIGN_AND_EVALUATION_SCOPE`）、本文件、`docs/parallel/DECISION_LOG.md`。
- 未运行项均标 NOT_RUN/UNVERIFIED（见 §3）。

### 1.3 Evidence（Reviewer 实测；完整证据见 REVIEW_M1_OFFLINE.md §1/§2/§6）

| 证据 | 实测结果（C2） |
| --- | --- |
| 完整离线测试 | **`365 passed`**（clean C2 副本，`16.54–17.04s`；0 failed/0 skipped；= 361 + 4 项新增回归测试） |
| 子集 | 评测 5 文件 `76 passed`；CF 3 文件 `75 passed`；Interview 3 文件 `49 passed` |
| 新增回归测试 | 4/4 passed（persisted failure_cases、fingerprint 可复现、precise provenance、baseline 文档指向） |
| demo 双跑确定性 | clean C2：`1d57ca62…` 两次一致；socket 全阻断下一致；artifact 生成上下文（C2 worktree + review docs）：`2282caff…` 两次一致 = `EXPERIMENT_BASELINE.md` 声明值 |
| 闭环回放 | v0/v1 各 3 轮/19 事件；event_id/loop_id 回放 state/assessments/steps 全等；trace digest `ed850c77…`/`4019c946…`；canonical CF trace 19 事件经共享 replayer 重建 3 assessments/6 evidence 且逐字节等于 live run |
| v0/v1 对照 | 14 case × seeds[0,1,2] × 12 轮 = 72 评估轮；digest `cb6cb07d…`；12 assessed；**58 failure_cases 已持久化于 artifact 且与 live `run_comparison()` 精确相等** |
| contamination | C1–C4 全 PASS（hidden=21、泄漏 0、注入 4、NOT_RUN=0；clean C2 104/138，artifact 上下文 105/139，均与对应文件集合一致） |
| 隔离/安全 | AST + 运行期零 M0/网络 import；API Key/PII 形态命中 0；prompt injection 不改 system hash；隐藏题面/id 无泄漏 |
| 垂直场景 | CF 14 题/112 隐藏/3 学习者/参考解 14/14 PASS；Interview 22/6/9/4/9/7；Freshness 9/9 分类正确、RECHECK 不入课程 |
| artifact | `eval_baseline_v1.json`（含 `comparison.failure_cases` 58 条）sha256 `25ed416a…`、`.md` `154ef1d8…`、`contamination_v1.json` `8b80a6f3…`、`cf_loop_canonical.jsonl` `6e3d96ae…`、loop traces `ed850c77…`/`4019c946…`，全部与文档声明一致 |
| 指纹/provenance | `dependency_fingerprint`=`ad30fbd…`（109 文件、一行命令可复现）；artifact env 为 `base_sha=3e7afee` + `implementation_commit=0bb13d2` + note + `working_tree_dirty`，无误导性 `git_sha` |
| 文档边界 | M0 能力一律 UNVERIFIED；接口 DRAFT/NOT_FROZEN；ADR Proposed；无 M1 GO/G4-H5/上线/真实教学效果越界表述 |

### 1.4 Blocked

- **本线无功能性 Blocked**：离线设计与评测范围内的验收项均已真实运行并由独立 Reviewer 复现；C2 修复已复验关闭。
- 跨线/人类门（不属于 B 线可解除）：
  - `H-01`（G4-H 正式风险签收与受信部署）— **BLOCKED（人类）**；
  - `H-02`（E5 PreLive Full 安全审查）— **BLOCKED（人类）**；
  - `H-03`（单次 G5 真实模型授权）— **BLOCKED（人类）**；
  - `I-01`（M1 接入正式 Runtime）— **BLOCKED**：需 M0 G6 GO/CONDITIONAL GO + 接口冻结 + 新变更审批；**不以本复核自动解锁**。

### 1.5 Next

1. Lead 终审并提交 **C3**（3 个 review/parallel docs）；`task-5` 由 Reviewer complete。
2. 维护者决策（见 §1.6/§4）：ADR-CORE-1..7 接受/拒绝、接口 v0 冻结、M1 是否/何时接 DSH 与真实 Runtime、CI 门禁、矩阵口径统一、P2-7 措辞（可选后续小改）。
3. 后续（未授权）：M1 真实 Runtime Adapter 与真实 Teacher MVP —— 必须在 M0 G6 GO/CONDITIONAL GO + 新审批之后另立变更；B 线当前 **STOP**。

### 1.6 Human Decision（需维护者/人类签署）

| # | 决策 | 建议/输入 | 状态 |
| --- | --- | --- | --- |
| HD-1 | 是否接受 `ADR-CORE-1..7`（当前全部 `Proposed`） | 见 `docs/m1/ADR-TEACHER-CORE.md`；接受后才能冻结 v0 契约 | **PENDING（人类）** |
| HD-2 | 是否冻结 `docs/interfaces/teacher_runtime_boundary_v0.md`（当前 DRAFT/NOT_FROZEN） | 需 A 线 + B 线 + 维护者共同确认；A 线尚未冻结 | **PENDING（人类/A 线）** |
| HD-3 | M1 是否接 DSH / 何时接真实 Runtime | 前置：M0 Runtime GO/CONDITIONAL GO（G6）、接口冻结、新变更审批；本轮不做 | **BLOCKED（前置门未满足）** |
| HD-4 | B-01..B-08 验收口径统一（任务书 §8 vs PRODUCT_SCOPE §8 工作假设） | C2 已把 PRODUCT_SCOPE §8 标为 authoring snapshot/工作假设；权威 = 任务书 §8 + REVIEW 矩阵；建议 Lead 在 DECISION_LOG 定稿 | **PENDING（Lead/维护者）** |
| HD-5 | 是否将 `test_no_m0_import.py` / `test_contamination.py` 纳入合并前 CI 门禁 | ADR-CORE-6/Q7；建议纳入 | **PENDING（维护者）** |
| HD-6 | Hint 证据门槛（0.35/0.70/≥5 事件/重复阈值 2）是否后续用数据校准 | Q1；当前为工程启发式，不影响本轮离线结论 | **PENDING（维护者+教学负责人）** |
| HD-7 | 真实教学效果/真实学习者验证 | **NOT_RUN**，且非本轮目标；需独立真实实验与伦理/隐私审查 | **NOT PLANNED IN THIS ROUND** |
| HD-8 | 安全/合规：M1 是否允许未来联网抓取真实 JD/热点 | 本轮明确不做；任何联网/真实数据均需新审批 | **BLOCKED（未授权）** |
| HD-9 | P2-7（report JSON 含 `utc_timestamp`，“两跑字节一致”措辞过宽）是否后续精确化 | disclosed/deferred；不影响 trace/指标证据；建议后续措辞小改 | **PENDING（Lead 决定是否排期）** |

---

## 2. B-01..B-08 验收矩阵状态（按任务书第 8 节口径）

> 权威口径 = 任务书 §8；`PRODUCT_SCOPE.md` §8 为 b-core 工作假设（C2 已标注，P2-4 关闭）。
> 状态 = `VERIFIED / PARTIAL / UNVERIFIED / NOT_RUN / BLOCKED`；证据见 `REVIEW_M1_OFFLINE.md` §2.I/§6。

| ID | 验收对象 | 状态 | 证据摘要（C2） |
| --- | --- | --- | --- |
| B-01 | Teacher Core Schema 和 Mock Runtime Port | **VERIFIED** | 365 passed（schema 57 + runtime port 14 + no-M0-import 6 等）；AST/fresh-subprocess 零 M0/网络 |
| B-02 | CF Teacher 诊断 + Hint Ladder | **VERIFIED** | CF 75 passed；14/112/3/参考解 14/14；默认 L1、L4 需显式+证据门、自适应不跨 FULL；判分只来自隐藏用例 |
| B-03 | Interview Coach 多轮追问 + Rubric | **VERIFIED** | 22/6/9/4/9/7 语料；5 阶段追问；独立 rubric(4 维)；项目事实边界 ASK_CLARIFICATION；注入 hash 不变 |
| B-04 | Freshness Manager 变化与过期/冲突 | **VERIFIED** | 9/9 分类正确（KEEP 2/UPDATE 2/RECHECK 5）；expired/conflict→RECHECK 且不可入课程；published_at vs observed_at 显式 |
| B-05 | Teacher 长期闭环可重放 | **VERIFIED** | v0/v1 3 轮/19 事件；event_id/loop_id 回放全等；canonical CF trace 19 事件/3 assessments/6 evidence；无证据/纯文本/幻觉不涨 mastery |
| B-06 | 隐藏题、恶意文档、虚构经历负例 | **VERIFIED** | C1–C4 全 PASS（hidden=21/泄漏 0/注入 4/扫描 138/139）；N1–N7 fail-closed；虚构数字被标记、缺事实先澄清 |
| B-07 | 可复现的 v0/v1 对比协议 | **VERIFIED** | 固定 case/seed、盲评、方差；**58 failure_cases 已持久化且与 live 一致**；digest `cb6cb07d…`；`not real teaching effect` 边界 |
| B-08 | 独立 M1 Offline Review，随后 STOP | **VERIFIED** | 两轮独立复核（@0bb13d2 + C2 复验）、可复现命令/原始输出、P0/P1/P2、B 矩阵、已知限制、STOP |

---

## 3. NOT_RUN / UNVERIFIED（不得当作 PASS）

| 项 | 状态 | 说明 |
| --- | --- | --- |
| 真实 Provider / live runtime 评测 | **NOT_RUN** | 本线禁止真实网络/Key/Provider；MockRuntimePort `simulated=True` |
| 真实教学效果 / 真实学习者提升 | **NOT_RUN** | 离线 synthetic 无法测量；不报告、不推断、不承诺 |
| 统计显著性/置信区间 | **NOT_RUN** | 3 seeds 只记录方差；结论明确 no significance claimed |
| Interview 多轮端到端教学闭环 | **NOT_RUN** | 本轮 harness 只覆盖 CF 闭环；interview 评测器/注入/新鲜度分别有测试 |
| M0 Runtime API / LiveGate / Bridge 验收 | **UNVERIFIED** | M1 不 import、不声明、不复用 M0 能力；接口文档 DRAFT/NOT_FROZEN |
| CFJudge 作为 OS 安全沙箱 | **NOT_RUN（明确不提供）** | 仅子进程+超时+临时目录；只用于合成 fixtures |
| 人类评分校准 | **NOT_RUN** | 无人类面试官一致性评估 |
| Windows 平台进程组行为 | **NOT_RUN** | 评测环境 Linux/POSIX |
| 测试覆盖率测量 | **NOT_RUN** | 未测量（非本轮验收项） |
| report JSON 跨次逐字节一致 | **NOT_APPLICABLE / disclosed** | trace JSONL 逐字节一致；report JSON 含 `environment.utc_timestamp`（P2-7，disclosed/deferred） |
| M1 接入 DSH / 真实 Runtime（I-01） | **BLOCKED** | 需 M0 G6 GO/CONDITIONAL GO + 新审批；不以本复核解锁 |
| H-01/H-02/H-03 | **BLOCKED** | 人类签核/授权门；Agent 不得代签 |

---

## 4. 需要维护者/人类作出的决策（汇总）

1. 接受/拒绝 `ADR-CORE-1..7`（Proposed）并决定是否冻结 v0 契约（HD-1）。
2. `docs/interfaces/teacher_runtime_boundary_v0.md` 的冻结时点（HD-2；A 线未冻结）。
3. M1 是否接 DSH / 真实 Runtime 的路线与门禁（HD-3；前置 M0 G6）。
4. B-01..B-08 矩阵口径统一（HD-4；C2 已按任务书 §8 收口，Lead 可在 DECISION_LOG 定稿）。
5. CI 是否强制 `test_no_m0_import.py` + `test_contamination.py`（HD-5）。
6. Hint 证据门槛是否后续数据校准（HD-6）。
7. 真实教学效果/真实数据/联网研究的授权与伦理边界（HD-7/HD-8）。
8. P2-7 措辞精确化是否排期（HD-9；disclosed/deferred，不阻塞）。
9. C2 修复与最终 C3 提交的接受（Lead 终审）。

---

## 5. 边界与免责

- 本状态表的 `VERIFIED` 仅表示“在冻结/修复 SHA 的离线 synthetic 环境中，由独立 Reviewer 复现了确定性证据”；
  **不表示**真实教学效果、真实模型质量、M1 上线、M0 能力验收或任何人类审批。
- B 线当前 **STOP**；任何真实 Runtime/联网/真实数据/上线动作都必须新授权、新接口冻结、独立审查与可回滚计划。
- 本文件与 `docs/m1/REVIEW_M1_OFFLINE.md`、`docs/parallel/DECISION_LOG.md` 由 Lead 统一提交；不改变 M0 G4-H/G5/LiveGate/M0 决策。
