# M1-B B-PR4 — Domains / Vertical 集成实现（Interview + Freshness 接入统一 Session/Replay + B4 E2E）

- **状态**：`IMPLEMENTED (B-PR4 integration layer)`。在 PR3 HEAD（`3103a06`）之上，把已冻结的 Interview/Freshness vertical 层接入 canonical `m1_teacher` Session 状态机，并交付 B4-01/02/03 的离线确定性 E2E。
- **工作区 / 分支**：`/root/m1b/pr4int`，`b-next/pr4-domain-ports`；基线 `b-next/pr3-idempotency` HEAD `3103a06`（PR2 事务 + PR3 scoped idempotency）。
- **合并**：先 `git merge b-next/pr4-interview-freshness`（vertical 层 `e265b96`；merge commit `efe385d`），合并后基线 **692 passed**（PR3 632 + vertical 60），无既有断言弱化。
- **设计依据**：`docs/M1_B_INTERVIEW_FRESHNESS_MAPPING.md`（移植映射/端口/拒绝码/PR4 矩阵）、`docs/M1_B_INTERVIEW_FRESHNESS_IMPLEMENTATION.md`（vertical 层实现）、`docs/M1_B_TXN_RECOVERY.md`、`docs/M1_B_SCOPED_IDEMPOTENCY_IMPLEMENTATION.md`。
- **边界**：仍无网络/真实简历/招聘 JD/Provider/LiveGate；合成数据；真实学习效果 **NOT_VERIFIED**；不修改 M0/security/bridge/config/g*/scripts/g4/LiveGate。

## 1. 交付范围（B4.1–B4.7 对应）

| 任务要求 | 实现落点 | 状态 |
|---|---|---|
| B4.1 additive `VerticalPolicy`/`DomainTurnPolicy` 接缝；engine 有策略用策略、无策略保持 CF 行为 | `m1_teacher/session/vertical.py`（`VerticalPolicy` Protocol、`VerticalActionContext`/`VerticalTransitionContext`/`VerticalSelection`/`VerticalTransition`）；`session/engine.py` 的 additive hooks（构造参数 `vertical_policy=None`、会话启动门、动作选择、结果迁移、事件 payload 扩展） | ✅ 实现；无策略路径由既有 674/632+ 测试与新增回归保证不变 |
| B4.2 Interview 多轮 5 阶段：LIGHT→INVARIANT→STRUCTURE→FULL 追问语义与 CF ladder 分离、FULL 默认禁止/证据门、追问受 LearnerState 影响、缺项目事实 `ASK_CLARIFICATION` 不代填 | `InterviewVerticalPolicy`：5 阶段 `SOCRATIC_QUESTION` 追问；interview-only support ladder L1..L3；`FULL` 默认禁用并需 human approval + evidence≥5（M1-B 无审批流程，显式请求直接 `MAP-E11` 拒绝）；`ACCELERATED_MASTERY_THRESHOLD=0.25` + `evidence_count>=2` 时跳过 concept probe（会话开始冻结）；`requires_project_facts` 缺事实 → `ASK_CLARIFICATION` | ✅ 实现（阈值标 UNCALIBRATED） |
| B4.3 统一事件表 + Replay：Interview 轮次用既有 HistoryEvent 类型；payload 带 vertical/domain/question/rubric-audit（4 维 sidecar+digest）；replay 重建 snapshot/session | 事件类型仅用既有 `HistoryEvent` 值；`ACTION_TAKEN.payload.vertical`（question/probe_stage/hint_level/reason_code/jd_ref）、`ASSESSED`/`MASTERY_UPDATED` payload 的 `rubric_audit`（4 维 + `spec_digest` + failure_modes）；`LearningHistory.assessment_event_drafts/apply_assessment` 新增 **optional** `payload_extra`（默认 None，旧 payload/回放不受影响）；`verify_rebuild`/`rebuild_state` 对两域均通过 | ✅ 实现 |
| B4.4 Rubric 证据：AssessmentPort 语义、4 维独立、开放题最多 PARTIAL、unknown facts NEEDS_REVIEW、EVAL_ERROR 不改 mastery、canonical MasteryModel 唯一写者 | `InterviewJudgeScorer`（将 scorer-side `InterviewRubricJudge` 适配到冻结 `AssessmentScorer.score`）；四维仍由 judge 独立计算并作为 sidecar 只进事件 payload；mastery 仅由 engine→`LearningHistory`→`MasteryModel` 写；NEEDS_REVIEW/EVAL_ERROR 不写 mastery（E2E 断言 snapshot 不变、`applied=False`、ERROR `mastery_unchanged=True`） | ✅ 实现 |
| B4.5 JD v1→v2 只影响新计划；过期/冲突/未授权/未来生效 knowledge 不得静默进入教学（显式 MAP-E reason） | `InterviewVerticalPolicy.validate_session_start` 在**任何写入前**执行：JD 门（`FRESHNESS_JD_GATE_BLOCKED` + `MAP-E10`、`RECHECK_JD_EXPIRED/NOT_YET_ACTIVE/CONFLICT`）与 knowledge 门（`FRESHNESS_KNOWLEDGE_GATE_BLOCKED` + MAP-E08/E09、`recheck_required`）；KEEP 允许、仅 `UPDATE+VERIFIED` 允许并把 version refs 写进 `PLAN_CREATED` payload；运行中 session 的 objective/plan 不受新 JD 影响 | ✅ 实现 |
| B4.6 跨域 Session：同 learner pause CF 后开 Interview session；snapshot/seq 一致；版本不兼容明确拒绝 | E2E 验证：CF session `pause` 后新 Interview session（不同 session_id）；learner snapshot 不变、事件 seq 全局连续、`verify_rebuild` 通过、resume CF 成功；跨域 vertical policy 与 engine domain 不匹配 → `VERTICAL_DOMAIN_MISMATCH`；objective/domain 不匹配 → `VerticalPolicy` 门拒绝 | ✅ 实现 |
| B4.7 E2E 测试 | `tests/m1_teacher/test_vertical_policy.py`（16 tests）、`tests/m1_teacher/test_b4_e2e.py`（9 tests） | ✅ 全部通过（离线 MOCK/E2E-MOCK） |
| demo | `m1_teacher/demo_b4.py`（`python -m m1_teacher.demo_b4 [--json]`），确定性输出，标注 MOCK/DETERMINISTIC/NOT_VERIFIED；`m1_teacher.demo` 未改动 | ✅ 实现 |

## 2. 架构：additive vertical seam

```
canonical engine (m1_teacher/session/engine.py)
  │  constructor: vertical_policy: VerticalPolicy | None = None   (None => 既有 CF 行为不变)
  ├─ start_session(): vertical.validate_session_start(...)  ← 写入前 JD/freshness/domain 门
  │      SESSION_STARTED payload += vertical metadata
  │      PLAN_CREATED   payload += vertical metadata (jd_ref / knowledge_refs)
  ├─ _select_action(): vertical.select_action(ctx) -> VerticalSelection | None
  │      None => 原 CF 选择逻辑（逐字节不变）
  ├─ _generate_and_persist(): ACTION_TAKEN payload += vertical action metadata
  ├─ _plan_result_transition(): history drafts += rubric_audit（optional payload_extra）
  │      vertical.plan_transition(ctx) -> VerticalTransition | None  （多轮：保持 pending item/ASSESS，或完成→REVIEW）
  └─ legacy _handle_observed_result/_handle_needs_review：同一 seam（protocol-only repo 也保持一致）

InterviewVerticalPolicy (vertical.py)
  ├─ InterviewDomainAdapter（teacher-visible 题库/5 阶段追问/教学目标；绝不读 hidden）
  ├─ InterviewRubricJudge（scorer-side；4 维 sidecar；开放题 PARTIAL；EVAL_ERROR 隔离）
  ├─ KnowledgeFreshnessService（KEEP/UPDATE/RECHECK、JD window、MAP-E 门禁）
  └─ 状态全部来自 events（pending item + ASSESSED/ACTION_TAKEN/ASSESSMENT_PREPARED）
     → 不新增 SessionState 字段、不直接写 learner/event/snapshot
```

**契约变更（D12 add-only，已记录）**：

- `TEACHING_ACTION_KIND` 追加 `SOCRATIC_QUESTION`、`ASK_CLARIFICATION`（`m1_teacher/contracts/types.py`）；既有值/顺序不变；`docs/M1_ADR_001_DOMAIN_CONTRACTS.md` §6b 追加 change log；`tests/m1_teacher/test_contracts.py` 冻结枚举期望同步追加。
- `LearningHistory.assessment_event_drafts/apply_assessment` 新增 **optional** `payload_extra`（默认 `None`；不得覆盖 canonical key，碰撞 fail-closed）。既有事件 payload schema 与回放不变。
- engine 构造参数新增 **optional** `vertical_policy=None`；其余签名/语义不变（PR2/PR3 事务、幂等、session version CAS 全部沿用）。

## 3. Interview 多轮五阶段设计要点

- **主问题**：`SOCRATIC_QUESTION`，reason `INTERVIEW_MAIN_QUESTION`；`requires_project_facts` 时 content 附加边界提示（不编造事实）。
- **五阶段追问**（teacher-visible）：`concept → hypothesis → complexity → experiment_design → online_triage`，reason `INTERVIEW_PROBE_<STAGE>`；只提问不给答案；stage 从事件推导，无新 session 字段。
- **LearnerState 影响（确定性）**：会话开始时若目标节点 mastery ≥ `0.25` 且 `evidence_count ≥ 2` → 冻结为“跳过 concept”的 4 阶段（加速）；两个相同种子的 learner 走完全相同序列；该阈值标 `UNCALIBRATED_HEURISTIC`。
- **项目事实边界**：题目 `requires_project_facts` 且答案无 learner-owned facts → judge `NEEDS_REVIEW:PROJECT_FACTS_REQUIRED` → 策略发 `ASK_CLARIFICATION`（要求项目/角色、规模量级、指标与来源；无任何示例数字）；事实由 learner 提供后才继续推进；重复 2 次仍缺失则回退到通用重试（不代填）。
- **Interview support ladder（与 CF 语义分离）**：连续 `INCORRECT` 时发 `HINT`，reason `INTERVIEW_HINT_LEVEL_1/2/3`（LIGHT→INVARIANT→STRUCTURE）；cap 由证据量决定（0→L1，1→L2，≥2→L3）；`FULL` 只在显式 human approval + evidence≥5 才可能，M1-B 无审批流程 → `request_full_solution()` 必抛 `MAP-E11_FULL_SOLUTION_FORBIDDEN`；E2E 扫描确认 `_4` 从未出现。
- **8 轮上限**（主问题+5 阶段+clarification/hint 不计入推进）：推进计数只认 `CORRECT/PARTIAL`；`INCORRECT` 触发 support ladder，不推进；`NEEDS_REVIEW` 不算推进；完成后 pending 清空、phase=REVIEW（是否 GOAL_COMPLETE 仍由 canonical planner 的客观 success criteria 决定）。

## 4. 统一事件 / Replay

- 事件类型不新增（仅既有 `HISTORY_EVENT_TYPE`）；Interview 轮次 = `RESPONSE_SUBMITTED` → `ASSESSMENT_PREPARED` → `ASSESSED`/`MASTERY_UPDATED` → `ACTION_TAKEN`。PR2/PR3 的 transaction A/B、scoped idempotency、CAS 完全保留。
- **payload 扩展**：
  - `SESSION_STARTED.payload.vertical`: `domain_id/policy_version/question_id/target_node_id/jd_id/jd_version/jd_ref/requires_project_facts/knowledge_refs/interview_hint_ladder/full_solution_enabled`。
  - `PLAN_CREATED.payload.vertical`: `jd_ref/knowledge_refs/question_id`。
  - `ACTION_TAKEN.payload.vertical`: `domain_id/policy_version/question_id/reason_code/probe_stage/hint_level/interview_ladder="SOCRATIC_PROBE"/cf_hint_ladder_shared=false`。
  - `ASSESSED`/`MASTERY_UPDATED.payload`: `vertical` + `rubric_audit{question_id,scorer_id,status,open_answer,dimensions{4},failure_modes[],spec_digest}`（**只有 4 维分数与 spec sha256，无 rubric 期望体**）。
- **Replay**：`LearningHistory.rebuild_state/verify_rebuild` 只消费 `ASSESSED` 的 `result`+`item`，忽略 additive keys；E2E 对 CF/Interview 两域均断言 `snapshot.to_dict() == rebuild_state(...).to_dict()`；跨域 session 事件按 `(learner_id, seq)` 连续，不同 session 并行存在。
- **determinism**：固定 fixture ids、固定 seed、固定 clock 常量（`FIXED_TIMESTAMP`）；测试用 `_strip_timestamps` 后两次运行投影逐字节相等；demo 两次运行 JSON sha256 相同。

## 5. JD / Freshness 门禁

- **启动前 fail-closed**（`validate_session_start`，在 `upsert_goal`/`save_session`/事件写入之前）：
  - JD：仅唯一有效窗口版本可为新 session 选择；过期/未生效/重叠冲突 → `FRESHNESS_JD_GATE_BLOCKED`（details 带 `map_code=MAP-E10_JD_EXPIRED_OR_CONFLICT` 与 `reason_code`）。
  - knowledge decisions：`RECHECK`（冲突/过期/低权威/未来时间/更旧）→ `FRESHNESS_KNOWLEDGE_GATE_BLOCKED`（details 带 `MAP-E08/MAP-E09` + `recheck_required=true`）；`KEEP` 放行（无需课程动作）；`UPDATE+VERIFIED+权威层` 放行并写入 `PLAN_CREATED.payload.vertical.knowledge_refs`。
  - 测试断言被拒时 `repository.list_events(learner)==[]` 且 `load_session(...) is None`（**零静默写入**）。
- **JD v1→v2**：同一 learner 在两个时间点分别开 session，`SESSION_STARTED.vertical.jd_version` 分别为 `v1`/`v2`；先开的 session objective/计划不变（只影响新计划）。
- 数据为 synthetic 静态带时间戳（`published_at`/`observed_at`/`valid_until`/`claim_status`）；无真实抓取/调度，不声称热点真实更新。

## 6. B4-01/02/03 映射与本地证据

> 证据等级：本轮为 **E2E-MOCK + DETERMINISTIC**（合成数据、无网络）；矩阵 `TEST_EVIDENCE_MATRIX.csv` 的独立 Reviewer 复跑仍为 **NOT_RUN**；真实教学效果 **NOT_VERIFIED**。不得把本地 pytest 绿色当作 B5 独立验收。

| case | 内容 | 本地实现证据 | 结果 |
|---|---|---|---|
| **B4-01** | 2 个 synthetic CF learner 走统一 canonical mastery/session journal | `test_b4_01_two_cf_learners_share_canonical_mastery_and_session_journal`：同一 SQLite 库中 `student_a`/`student_b` 两条既有 demo 路径；不同 action/mastery/plan 路径；事件 seq 连续、事件类型合法；两 learner 各自 `verify_rebuild` 与 `rebuild_state` 一致；CF 事件无 vertical 字段（向后兼容） | 本地 9 passed（E2E-MOCK） |
| **B4-02** | 2 个 synthetic interview learner + JD v1→v2 + 5 阶段 + ASK_CLARIFICATION + 4 维 rubric + 不同证据化计划 | `test_b4_02_two_interview_learners_five_stage_jd_and_rubric`：learner A（3 条 seed CORRECT，mastery 加速，跳过 concept，jd v2）vs learner B（JD v1、缺项目事实→clarify、INCORRECT→interview hint L1、完整 5 阶段）；A session 在 B 启动后状态不变；rubric_audit 4 维 + 64-hex spec digest；隐藏期望体/参考回答/`rubrics/` 路径不出现在 teacher-visible 事件；FULL 从未出现 | 本地 9 passed（E2E-MOCK） |
| **B4-03** | EXPIRED/CONFLICT/UNAUTHORITATIVE 不得进入教学；JD 过期/未生效明确拒绝 | `test_b4_03_freshness_and_jd_gates_block_before_teaching`：9 场景 = KEEP 2/UPDATE 2/RECHECK 5；5 个 RECHECK 逐个启动被拒（MAP-E08/E09）；2 个 JD 时间窗被拒（MAP-E10）；零事件/零 session；eligible UPDATE 进入新计划 refs | 本地 9 passed（E2E-MOCK） |
| 跨域 | CF pause → Interview session → resume；snapshot/seq 一致；版本拒绝 | `test_cross_domain_pause_and_interview_session_continuity`、`test_vertical_version_and_objective_mismatch_rejected` | 本地通过 |
| hidden / 无网络 / 确定性 | hidden 结构不泄漏；new modules 无网络/M0 import；hidden-scoring reader allow-list 仍为 `{scorer.py, interview_judge.py}`；两次运行投影一致；demo 两次输出相同 sha256 | `test_b4_modules_are_offline_and_hidden_readers_are_closed`、`test_b4_interview_flows_are_deterministic`、`test_demo_b4_is_deterministic_and_boundary_labelled`、`test_b4_teaching_action_kinds_used_are_contract_valid` | 本地通过 |

## 7. 真实运行输出（本机实测）

环境：`/root/Autonomous Teacher/.venv/bin/python`（Python 3.11.15 / pytest 9.2.0）；工作区 `/root/m1b/pr4int`。

```bash
# 合并 vertical 层后的基线（PR3 632 + vertical 60）
$ "/root/Autonomous Teacher/.venv/bin/python" -m pytest tests/m1_teacher -q
692 passed in 36.76s

# 本轮新增定向测试（2 次/3 次稳定）
$ pytest tests/m1_teacher/test_vertical_policy.py -q
16 passed in 1.11s
$ pytest tests/m1_teacher/test_b4_e2e.py -q          # 连续 3 次
9 passed in 4.63s
9 passed in 4.19s
9 passed in 4.17s

# 最终全量回归
$ "/root/Autonomous Teacher/.venv/bin/python" -m pytest tests/m1_teacher -q
717 passed in 45.98s          # = 692 既有 + 25 新增；0 failed

# 静态检查
$ ruff check <new/changed files>
All checks passed!

# 确定性 demo（两次运行逐字节相同）
$ python -m m1_teacher.demo_b4 --json > run1.json
$ python -m m1_teacher.demo_b4 --json > run2.json
$ cmp -s run1.json run2.json && echo identical
identical
sha256(run1.json) = 6b7bb66e36a38bd640d5b47d206d8fee24a446df9b42dbe76d20dd8cc50bef83
```

demo B4 摘要（真实输出节选）：B4-01 `paths_differ=true`（两 CF learner 不同 action/mastery 路径）；B4-02 `jd_versions=[v2,v1]`、`paths_differ=true`、`full_solution_emitted=false`、A probes `HYPOTHESIS..ONLINE_TRIAGE`、B probes `CONCEPT..ONLINE_TRIAGE` + clarify 1 + hint level 1、两 learner `verify_rebuild=true`；B4-03 `decision_counts={KEEP:2,UPDATE:2,RECHECK:5}`、`silent_imports=0`、5 个 blocked 启动全部 `FRESHNESS_KNOWLEDGE_GATE_BLOCKED`。

## 8. 对既有测试/断言的保护

- 既有 **692** 测试全部保持通过（含 PR1 的 opt-in/泄漏测试、PR2 事务/崩溃矩阵、PR3 scoped idempotency/并发）。
- PR1 的隐藏评分读取 allow-list 语义保持 **封闭**：仍为 `{scorer.py, interview_judge.py}`；新增 `session/vertical.py` 不引用隐藏路径；`test_assessment_scorer.py`/`test_e2e_resume_idempotency.py` 的适配来自 vertical 阶段且合并后保留；无第三处引用。
- 唯一被修改的既有测试：`tests/m1_teacher/test_contracts.py` 的枚举冻结期望追加两个 D12 additive 值（其余断言不变）。
- 无策略时的 engine 路径：`vertical_policy=None` 时所有新增分支跳过；既有 CF 测试与 B4-01 CF 测试均断言事件 payload 不含 vertical 字段。
- 不修改 `assessment/scorer.py`、`learner/**` 既有语义（history 仅新增 optional 参数）、`contracts/**` 冻结语义（除 D12 append enum + ADR 记录）、M0/security/bridge/config/g*/scripts/g4/LiveGate。

## 9. 仍 NOT_RUN / 限制

- **独立 Reviewer 复跑**：B4-01/02/03 的 `TEST_EVIDENCE_MATRIX.csv` 独立验收仍 **NOT_RUN**；本轮只提交 Owner 侧 E2E-MOCK 证据，不自我宣称 B5 PASS。
- **真实学习效果**：所有掌握度/路径/分数均为确定性启发式与合成输入，**NOT_VERIFIED**；阈值（加速 0.25/证据 2、hint cap、interview support ladder）标 UNCALIBRATED。
- **真实数据/网络**：无真实招聘网站/个人简历/JD、无真实 Provider/API Key/LiveGate/付费请求；freshness 为静态 synthetic 时间戳，无真实抓取/调度。
- **隐藏题集**：B 线 `fixtures/m1/interview/hidden/**` 仍未转换为 vertical hidden 评测集；本轮 hidden 评测使用公开题库 + scorer-only reference answers。
- **多轮范围**：实现“单题内 5 阶段多轮 + clarification/hint”；未实现任意多题会话编排/对话树/用户自由问答；完成后由 canonical planner 决定后续（可能进入其它题）。
- **人类交互 UI/审批**：无 UI、无人工审批工作流；`FULL_SOLUTION` 与知识人工复核仅以代码门禁表达，持久化 review queue/审批 UI 未实现。
- **B1/B2/B3 依赖**：开放不可信 CODE 判题、真实 crash 恢复演练、多租户鉴权仍按前序 PR 的限定范围；本轮不重复其安全声明。
- **确定性时钟**：engine 事件 `created_at` 仍为 wall-clock（历史语义），测试/demo 投影去除时间戳后比较；未改事件时间语义。

## 10. 文件清单（本轮）

新增：
- `m1_teacher/session/vertical.py`（801 行）：VerticalPolicy seam + InterviewVerticalPolicy + InterviewJudgeScorer。
- `m1_teacher/demo_b4.py`（457 行）：确定性 B4 demo（MOCK/DETERMINISTIC/NOT_VERIFIED）。
- `tests/m1_teacher/test_vertical_policy.py`（871 行，16 tests）。
- `tests/m1_teacher/test_b4_e2e.py`（726 行，9 tests）。

修改（additive）：
- `m1_teacher/contracts/types.py`（+6）：D12 additive `SOCRATIC_QUESTION`/`ASK_CLARIFICATION`。
- `docs/M1_ADR_001_DOMAIN_CONTRACTS.md`（+16）：§6b D12 change log。
- `tests/m1_teacher/test_contracts.py`（+3）：冻结枚举期望追加。
- `m1_teacher/learner/history.py`（+74/−17）：optional `payload_extra`（默认 None，碰撞 fail-closed）。
- `m1_teacher/session/engine.py`（+195/−35）：optional `vertical_policy` seam、启动门、动作/迁移/事件 payload 扩展（无策略路径不变）。

## 11. 复现

```bash
cd /root/m1b/pr4int
git merge b-next/pr4-interview-freshness          # vertical 层（已提交的 merge：efe385d）
"/root/Autonomous Teacher/.venv/bin/python" -m pytest tests/m1_teacher -q          # 717 passed
"/root/Autonomous Teacher/.venv/bin/python" -m pytest tests/m1_teacher/test_b4_e2e.py -q   # 9 passed
"/root/Autonomous Teacher/.venv/bin/python" -m m1_teacher.demo_b4 --json          # 确定性 B4 摘要
```

---

*本文件只说明本轮已实现/已实测的 integration + B4 E2E；未运行项一律 NOT_RUN，历史/合成证据不构成真实教学效果或独立验收结论。*
