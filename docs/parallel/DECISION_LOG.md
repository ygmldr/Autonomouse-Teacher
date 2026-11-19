# M1 Offline Teacher — 并行决策记录（DECISION_LOG）

| 字段 | 值 |
| --- | --- |
| 更新时间 | 2026-11-19（UTC；C2 复核后定稿） |
| 维护者 | `b-reviewer`（记录本轮复核涉及/确认的接口契约与边界决策；Lead 统一提交） |
| 工作树 | `/root/at-m1-offline`（branch `work/m1-offline-design`） |
| base SHA | `3e7afee077845a071cd364e93ab209cac20b2d5f` |
| impl/docs SHA（冻结） | `0bb13d27b069dfb71b31ce7e02f9cde41f9bb071` |
| 复核后修复 commit（C2，当前 HEAD） | `052d980d9a45558da8789c90725ae6c48f3f7a7d`（commit `2026-11-19T18:56:21+00:00`） |
| 复核文档提交（C3） | `pending`（Lead 统一提交；未包含在 C2） |
| 适用范围 | B 线 M1 Offline（`m1_offline/`、`tests/m1_offline/`、`fixtures/m1/`、`docs/m1/`、`docs/interfaces/`）；**不涉及 M0/A 线修改** |
| 能力状态 | M0 Runtime 能力一律 **UNVERIFIED**；本文不声明任何 Live API/真实 Provider 已实现或已验收 |

本文件记录三类内容：
1. 本轮**接口契约/实现边界决策**（D-*），状态 = `Accepted (B-line internal)` / `Proposed` / `Open`；
2. **ADR-CORE-1..7** 状态（全部 `Proposed`，需维护者接受）；
3. **A/B 两线边界决策**与**待人类决策清单**（HD-*）。

---

## 1. 接口契约与实现边界决策（本轮）

| ID | 决策 | 状态 | 依据/证据 | 影响 |
| --- | --- | --- | --- | --- |
| D-01 | 使用**独立包** `m1_offline/`（仅 stdlib + pytest 测试依赖），禁止 import `autoteacher_m0`/`src`，不修改 M0 任何文件 | **Accepted (B-line internal)**；ADR-CORE-1 `Proposed` | ADR-CORE-1；`test_no_m0_import.py`（AST + fresh subprocess）；Reviewer 独立复现零 M0/网络 import | 教学层可独立运行/评审；M0 保持 UNVERIFIED 不被污染；未来只需新增 Runtime adapter |
| D-02 | 定义 `types.py` v0 契约（`SCHEMA_VERSION="m1.offline.v0"`，16 个 Record：Provenance/SkillNode/KnowledgeSource/KnowledgeRevision/LearnerProfile/EvidenceEvent/LearnerState/LearningGoal/LearningTask/CurriculumPlan/TeacherAction/DiagnosticResult/AssessmentResult/RuntimeRequest/RuntimeResponse/TraceEvent），全部带 `schema_version` 与必填校验/JSON 无损往返 | **Accepted (B-line internal)**；对外冻结待人类 | ADR-CORE-1；`test_schema.py` 57 项；ARCH §3/§5；Reviewer 核对 16 类与文档一致 | 跨模块可消费的稳定 v0；非法枚举/未知字段 fail-closed（`SchemaError`） |
| D-03 | 运行时使用**抽象 `RuntimePort`**（`send(RuntimeRequest)->RuntimeResponse`）+ 默认 `MockRuntimePort(script, seed)`：零网络、确定性、`simulated=True`、支持 error/timeout 注入 | **Accepted (B-line internal)**；ADR-CORE-2 `Proposed` | ADR-CORE-2；`test_runtime_port.py` 14 项；Reviewer socket 全阻断 demo 复现一致 | Teacher Core 不绑定具体 Provider；真实 adapter 未来新增实现，属 A 线/维护者决策（UNVERIFIED） |
| D-04 | **Hint Ladder** 固定四级 `LIGHT_HINT→INVARIANT_HINT→STRUCTURE_HINT→FULL_SOLUTION`（1..4），默认 L1；FULL_SOLUTION 仅显式 L4 + 证据门可及；自适应升级永不默认跨入 FULL_SOLUTION | **Accepted (B-line internal)**；ADR-CORE-4 `Proposed` | ADR-CORE-4；`teaching_policy.py`；`test_teaching_policy.py` 24 项 + CFTeacher 安全钳制；Reviewer 独立探针（默认 L1 / L4 薄证据→L1 / 证据足→L4 / 自适应≤L3） | 教学强度可审计、可测试；门槛值为工程启发式（Q1 待校准） |
| D-05 | **证据驱动 Learner Model**：仅独立评估产生、带 `observed_score` 的合法 evidence 可改 mastery；`error_codes` 失败证据 fail-closed（只降/不升）；同题重复递减、不跨技能迁移；同 event_id 幂等；replay 确定性 | **Accepted (B-line internal)**；ADR-CORE-3 `Proposed` | ADR-CORE-3；`learner_model.py`；`test_learner_model.py` 20 项；Reviewer 独立探针（无证据/纯文本/HINT_REQUEST/失败/幂等） | “模型说得好听/重复同题”不会让掌握度上涨；数值为 synthetic proxy，无效度声明 |
| D-06 | **评测器独立**：assessment 只能来自独立 scorer（`CFJudge` / `InterviewRubric` / 独立 blind rubric）；teacher 不计算/不注入分数；`scorer_id` 独立；盲评签名不含 policy/teacher/strategy | **Accepted (B-line internal)**；ADR-CORE-5 `Proposed` | ADR-CORE-5；`cf/judge.py`、`interview/rubric.py`、`evaluation/compare.py`；`test_evaluation_protocol.py`/`test_compare_v0_v1.py`；Reviewer 签名与 scorer_id 探针 | v0/v1 对比不自我确认；失败案例可追溯；仍属合成规则，不外推真实效果 |
| D-07 | **public / hidden 分离**：`fixtures/m1/*/hidden/` 为隐藏面，teacher 只读公开面；隐藏题面/答案/ID 不得出现在公开 docs/traces/源码；contamination C1–C4 强制扫描（含测试代码网络 import，NOT_RUN ≠ PASS） | **Accepted (B-line internal)**；ADR-CORE-6 `Proposed` | ADR-CORE-6；`evaluation/contamination.py`；`test_contamination.py` 19 项；Reviewer 独立重跑 + 独立泄漏扫描 | 评测可信度提高；仅为离线工程纪律，不构成真实考试安全 |
| D-08 | **枚举统一大写字符串**（如 `ANSWER/CODE_SUBMISSION/EXPLANATION/INTERVIEW_RESPONSE/ASSESSMENT/HINT_REQUEST`、`VERIFIED/REPORTED/CONFLICT/EXPIRED/UNKNOWN`、`KEEP/RECHECK/UPDATE`、`RESOLVED/UNKNOWN/NEEDS_REVIEW`）；非法值 `SchemaError` | **Accepted (B-line internal)** | `types.py`；`EVALUATION_PROTOCOL.md` §5.4；Reviewer enum/文档一致性检查（唯一缺口 `PRACTICE` → 已由 Lead 安排文档化，P2-5） | 跨模块枚举语义稳定；文档需随枚举同步（P2-5 修复） |
| D-09 | **teacher_v0（FixedPolicy）vs teacher_v1（AdaptivePolicy）** 固定 case/seed/轮数对照：14 题 catalog、seeds `[0,1,2]`、每条 12 轮、盲评 rubric、记录每维均值/方差与**失败案例清单** | **Accepted (B-line internal)**；ADR-CORE-5 | `evaluation/compare.py`；`test_compare_v0_v1.py` 11 项；Reviewer 复现 digest `cb6cb07…`、72 轮、58 失败案例 | 只给“模拟器内部行为差异”，不报告显著性、不得宣称 v1 更好（本轮实测 v1 在 independence/hint_efficiency 更低，如实呈现） |
| D-10 | **Trace/回放契约**：`TraceEvent(event_id, loop_id, round, step, payload, timestamp)`，event_id=`{loop_id}:e{seq:04d}`，seq 连续；`replay_trace` 按 event_id/loop_id 重建 state/assessments/step_sequence；确定性注入时钟 | **Accepted (B-line internal)**（b-eval loop schema） | `evaluation/harness.py`；`test_closed_loop.py` 15 项；Reviewer 回放探针 | b-eval 闭环完全可回放；CF 域审计 trace 的 payload schema 与共享 replayer 不互通（P2-6，Lead 决定 ACCEPT + b-cf 文档化；或由 `cf_loop_canonical.jsonl` 补齐 canonical 形态） |
| D-11 | **Freshness 规则**：`published_at`（来源发布时间）与 `observed_at`（观测时间）显式区分；`CONFLICT/EXPIRED/未来时间/更旧/低权威` → `RECHECK`（fail-closed），仅 `UPDATE+VERIFIED+可写层级` 可能进入课程；JD 变化 ≠ 题目热度 | **Accepted (B-line internal)** | `freshness.py`；`test_freshness.py` 17 项；`FRESHNESS_AND_SOURCE_POLICY.md`；Reviewer 9/9 分类复现 | 过期/冲突不静默污染课程；正文级指纹 v0 限制已记录（UNVERIFIED） |
| D-12 | **Prompt Injection 视为不可信数据**：注入文档只能进入用户内容位并带 `UNTRUSTED_DATA` 引用标记；不得改变 `system_instructions`/权限/评分规则（`instruction_hash` 不变） | **Accepted (B-line internal)**；ADR-CORE-7 相关 | `interview/coach.py`；`test_interview_coach.py`；Reviewer hash 前后不变探针 | 离线注入负例集可复现；真实联网后的注入防护仍需新设计（UNVERIFIED） |
| D-13 | **Demo/评测结论措辞边界**：所有输出/文档必须含 `offline synthetic only, not real teaching effect`；禁止“证明/显著/真实提升/v1 更好”等外推；未运行项标 NOT_RUN | **Accepted (B-line internal)**；ADR-CORE-7 | `demo.py`、`compare.py`（`assert_no_overclaim`）、`REVIEW`/`STATUS`；Reviewer 反向验证 guard 会抛错 | 报告可信、可审计；不构成真实教学效果结论 |
| D-14 | **评测/闭环/demo 归属 b-eval**，只读消费 b-core/b-cf/b-interview 契约；跨模块修改须先经 B-Lead 契约决策 | **Accepted (B-line internal)** | `TEACHER_CORE_ARCHITECTURE.md` §3；task-1..task-4 写范围隔离；Reviewer diff 审计（145 文件全为新增、无越界修改） | 边界清晰、可回滚；本轮无跨线整合 |

| D-15 | **artifact 持久化契约（C2 新增）**：`eval_baseline_v1.json` 必须持久化 `comparison`（含 `failure_cases` 58 条、statistics、delta、run_digest、conclusion），并由回归测试断言 artifact == live `run_comparison()`；`--write-artifacts` 同步更新 | **Accepted (B-line internal, C2)**；P1-1 修复 | `evaluation/report.py`、`demo.py`；`test_persisted_report_contains_comparison_failure_cases`、`test_baseline_document_references_persisted_failure_cases`；Reviewer 复验精确相等 | 失败案例不再是"只存在于内存/仅文档声称"，维护者可直接审阅 artifact；不改变评测实现逻辑 |
| D-16 | **artifact provenance 契约（C2 新增）**：`environment` 使用 `base_sha`（恒 3e7afee）+ `implementation_commit`（生成时 HEAD=0bb13d2）+ `implementation_commit_note`（最终 commit 见 STATUS）+ `working_tree_dirty`，**禁止**误导性 `git_sha`；依赖指纹附算法/一行命令 | **Accepted (B-line internal, C2)**；P2-1/P2-2 修复 | `report.environment_snapshot()`；`test_report_artifacts_record_precise_commit_provenance`、`test_dependency_fingerprint_is_reproducible_and_documented` | 工件 provenance 精确、可复现；不暗示 HEAD==base |
| D-17 | **CF trace 双格式契约（C2 新增）**：`cf_teaching_loop.jsonl` = CF 域审计格式（event_id/seq/step/mastery 快照，非 canonical，不得作回放证据）；`cf_loop_canonical.jsonl` = canonical TraceEvent 格式（共享 `replay_trace` 可重建 3 assessments/6 evidence，逐字节等于 live run）；限制写入 CF_SPEC §8.4 | **Accepted (B-line internal, C2)**；P2-6 文档化修复 | `docs/m1/CF_TEACHER_SPEC.md` §8.4；`docs/m1/traces/cf_loop_canonical.jsonl`（19 事件、sha256 `6e3d96ae…`）；Reviewer 回放复验 | 消除"静默 0 assessment"误导；B-05 官方回放证据仍以 loop_v0/v1 为准 |
| D-18 | **枚举 `PRACTICE` 保留值说明（C2 文档补记）**：`TEACHER_ACTION_KIND_VALUES` 保留 `PRACTICE`，当前 v0/v1 策略均不发出；启用需契约决策并同步策略/测试/文档（`types.py` 不变） | **Accepted (B-line internal, C2)**；P2-5 修复 | `TEACHER_CORE_ARCHITECTURE.md`、`docs/interfaces/teacher_runtime_boundary_v0.md`；Reviewer 文档一致性探针 | 消除 enum/文档不一致；不改变 schema 行为 |

---

## 2. ADR-CORE-1..7 状态（全部 `Proposed`，需维护者接受）

来源：`docs/m1/ADR-TEACHER-CORE.md`。Reviewer 复核确认所有状态均为 `Proposed`（未冻结），并附独立实现/测试证据。

| ADR | 标题 | 状态 | Reviewer 复核结果 |
| --- | --- | --- | --- |
| ADR-CORE-1 | 独立隔离包（`m1_offline/` 不依赖 M0） | **Proposed** | 蒸馏有效：AST + subprocess 零 M0/网络 import；diff 无 M0 改动 |
| ADR-CORE-2 | Mock Runtime Port（零网络、确定性、`simulated=True`） | **Proposed** | 有效：确定性/错误注入/零网络均独立复现 |
| ADR-CORE-3 | 证据驱动 Learner Model（无证据不涨、重复不迁移） | **Proposed** | 有效：无证据/文本/失败/幂等探针全通过 |
| ADR-CORE-4 | Hint Ladder（默认 LIGHT、升级需证据、绝不默认 FULL） | **Proposed** | 有效：默认 L1、L4 需显式+证据门、自适应≤L3 |
| ADR-CORE-5 | 独立评测器（teacher 与 evaluator 分离） | **Proposed** | 有效：scorer_id 独立、盲评签名无策略标识、check 可运行 |
| ADR-CORE-6 | public / hidden 分离（防泄漏与污染） | **Proposed** | 有效：C1–C4 PASS、独立泄漏扫描 0 命中、NOT_RUN≠PASS 有测试 |
| ADR-CORE-7 | 不接真实 Provider（离线 mock-only，能力状态 UNVERIFIED） | **Proposed** | 有效：零网络/零 Key/无真实数据；真实能力全部 NOT_RUN/UNVERIFIED |

> 维护者动作：接受/拒绝 ADR-CORE-1..7；接受后是否冻结 v0 契约（见 §4 HD-1）。

---

## 3. A/B 两线边界决策（本轮，Reviewer 复核确认）

| ID | 决策 | 证据 |
| --- | --- | --- |
| X-01 | **B 线未修改 M0 冻结区**：`src/autoteacher_m0/**`、`bridge/`、`accounting/`、`security/`、LiveGate、`plugins/`、`config/`、`scripts/`、README/AGENTS/pyproject 等零改动 | `git diff --name-only 3e7afee..0bb13d2` 145 文件全为新增于允许目录；主工作树 clean 且 HEAD=`3e7afee` |
| X-02 | **B 线未接真实 Runtime/Provider/Key/网络**：全部 mock；真实 adapter 属未来 A 线冻结 + 维护者批准事项 | AST/运行期零网络 import；socket 阻断 demo 通过；无 Key/PII 形态；M0 能力 UNVERIFIED |
| X-03 | **B 线未使用真实个人/简历/JD/热点数据**：88/88 fixtures `synthetic=true` + `license=CC0-1.0`；合成域名 `.invalid` | Reviewer 逐文件校验；contamination C4 命中 0 |
| X-04 | **未做跨线整合**：无 M0 import、无 LiveGate 改动、无共享可信进程/可写安全状态；A 线 H-01/H-02/H-03 与 I-01 未被本线解锁 | diff 审计；STATUS §1.4/§3 |
| X-05 | **B 线当前 STOP**：复核后 Review 落盘即停止；任何后续动作（真实 Runtime/联网/上线）需新授权 | 本文件 + `STATUS.md`；任务书 B5“STOP”要求 |

---

## 4. 待人类/维护者决策清单（HD）

| # | 决策 | 建议/输入 | 状态 |
| --- | --- | --- | --- |
| HD-1 | 接受/拒绝 `ADR-CORE-1..7`；接受后是否冻结 v0 契约 | ADR 全部 Proposed；Reviewer 复核 7/7 实现与证据成立 | **PENDING（人类）** |
| HD-2 | `docs/interfaces/teacher_runtime_boundary_v0.md` 何时从 `DRAFT/NOT_FROZEN` 冻结 | 需 A 线 + B 线 + 维护者共同确认；A 线未冻结 | **PENDING（人类/A 线）** |
| HD-3 | M1 是否接 DSH / 何时接真实 Runtime | 前置：M0 Runtime G6 GO/CONDITIONAL GO、接口冻结、新变更审批；本轮不做 | **BLOCKED（前置未满足）** |
| HD-4 | B-01..B-08 验收口径统一（任务书 §8 vs PRODUCT_SCOPE §8 工作假设） | Lead 已安排 b-core 修复 PRODUCT_SCOPE（P2-4）；建议以任务书 §8 + 本 REVIEW 矩阵为准 | **PENDING（Lead/维护者）** |
| HD-5 | Hint 证据门槛（0.35/0.70/≥5 事件/重复阈值 2）是否需数据校准 | Q1；当前工程启发式，不影响离线结论 | **PENDING（维护者+教学负责人）** |
| HD-6 | 错误计数键统一（error code vs skill id，Q2） | 跨模块语义一致性；变更需契约升级 | **PENDING（B-Lead/维护者）** |
| HD-7 | public/hidden 判定是否升级为 fixture manifest（Q3） | 当前路径段标记；强度 vs 成本 | **PENDING（维护者+b-eval）** |
| HD-8 | 评测 rubric 权重与盲评流程维护者（Q4） | v0/v1 对比可信度 | **PENDING（b-eval+维护者）** |
| HD-9 | CI 是否强制 `test_no_m0_import.py`/`test_contamination.py`（Q7） | 建议纳入合并前必跑 | **PENDING（维护者）** |
| HD-10 | 真实教学效果/真实数据/联网研究授权与伦理边界 | NOT_RUN；任何真实数据/联网需新审批与独立审查 | **BLOCKED（未授权）** |
| HD-11 | P2-7 措辞是否后续精确化（report JSON 含 `utc_timestamp`） | disclosed/deferred；不影响 trace/指标证据；建议排期小改 | **PENDING（Lead 决定）** |

---

## 5. 本轮复核发现（P1/P2）处置记录（两轮合并 + C2 复验结论）

| ID | 级别 | 摘要 | 第一轮处置 | C2 复验状态（2026-11-19） |
| --- | --- | --- | --- | --- |
| P1-1 | P1 | `EXPERIMENT_BASELINE.md` 声称失败案例清单在 `eval_baseline_v1.json`，第一轮该工件只有聚合 metrics | **FIX IN C2**（b-eval 持久化 58 条 failure_cases + 修正文档 + 新增断言） | **FIXED & VERIFIED**：artifact `comparison.failure_cases` 与 live `run_comparison()` 精确相等；回归测试通过 |
| P2-1 | P2 | report provenance 写 base SHA（暗示 HEAD==base），未记录冻结 commit | **FIX IN C2**（`base_sha` + `implementation_commit` + note + `working_tree_dirty`，去 `git_sha`） | **FIXED & VERIFIED** |
| P2-2 | P2 | 依赖指纹 `b4bb2931…` 不可按文档算法复现 | **FIX IN C2**（`dependency_fingerprint()` + 文档化算法/一行命令；旧值 superseded） | **FIXED & VERIFIED**：`ad30fbd…`，109 文件，两算一致 |
| P2-3 | P2 | `PRODUCT_SCOPE.md` 数字/状态陈旧（161 vs 实际 165；“开发中/验收 NOT_RUN”） | **FIX IN C2**（b-core 改为 165 + authoring snapshot） | **FIXED & VERIFIED** |
| P2-4 | P2 | `PRODUCT_SCOPE.md` §8 的 B-01..B-08 行归属与任务书 §8 不同 | **FIX IN C2**（b-core 标注工作假设；权威 = 任务书 §8 + REVIEW） | **FIXED & VERIFIED** |
| P2-5 | P2 | `TEACHER_ACTION_KIND_VALUES` 的 `PRACTICE` 未文档化 | **FIX IN C2**（b-core 文档化为 reserved enum，不改代码） | **FIXED & VERIFIED** |
| P2-6 | P2 | CF 域审计 trace payload schema 与共享回放器不互通（静默 0 assessment） | **ACCEPT（disclosed）** + b-cf 文档化限制 | **DOCUMENTED & VERIFIED**：CF_SPEC §8.4 + 新增 `cf_loop_canonical.jsonl`（19 事件，共享 replayer 重建 3 assessments/6 evidence，逐字节等于 live run） |
| P2-7 | P2 | （C2 复验新发现）`--write-artifacts` “两跑字节一致”措辞过宽：trace JSONL 确定，但 report JSON 含 `environment.utc_timestamp` | **DISCLOSED / DEFERRED**（不阻塞；建议后续措辞精确化） | trace JSONL 逐字节一致已验证；report JSON 差异仅 `utc_timestamp` |

> Reviewer 原则：只把“文档/证据工件与冻结实测不一致”列为 P1/P2；不因风格问题强制修复；所有关闭结论以 C2 clean-tree 复验为准（详见 `REVIEW_M1_OFFLINE.md` §6）。

## 6. 变更记录

| 日期/时间（UTC） | 变更 | 记录人 |
| --- | --- | --- |
| 2026-11-19T18:25:22Z | B 线实现/测试/fixtures/文档冻结为 commit `0bb13d2`（145 新增文件） | Lead/owners |
| 2026-11-19T18:26Z–18:47Z | 独立 Reviewer 只读复现 @`0bb13d2`（tests/demo/replay/compare/contamination/verticals）；发现 P1-1 + P2-1..P2-6 | b-reviewer |
| 2026-11-19T18:47Z | Lead 处置 P1/P2：P1-1、P2-1..P2-5 修复，P2-6 接受披露；安排 C2 后复验 | Lead |
| 2026-11-19T18:56:21Z | **C2 提交**：`052d980d9a45558da8789c90725ae6c48f3f7a7d`（13 文件：12 M + 1 A；owner 修复 + 报告 artifacts + canonical trace） | Lead/owners |
| 2026-11-19T18:57Z–19:06Z | Reviewer 在 **clean C2** 副本上复跑 A–J；专项复验 P1-1/P2-1..P2-6 全部通过；新发现 P2-7（disclosed/deferred） | b-reviewer |
| 2026-11-19T19:0xZ | 最终裁定：`PASS_FOR_M1_OFFLINE_DESIGN_AND_EVALUATION_SCOPE`；B 线 STOP | b-reviewer |
| `pending` | C3：Lead 提交 3 个 review/parallel docs（本文件、REVIEW、STATUS） | Lead |

---

## 7. 边界声明

- 所有决策与复核结论仅覆盖 **B 线 M1 Offline 设计/离线评测范围**；**不构成**真实教学效果、真实模型能力、M1 上线或 M0 能力验收。
- M0 能力保持 **UNVERIFIED**；A 线 H-01/H-02/H-03 与 I-01 保持 **BLOCKED**；B 线不改变 M0 G4-H/G5/LiveGate/M0 决策。
- 本文件由 Lead 统一提交；Reviewer 不直接修改实现/其它 docs。
