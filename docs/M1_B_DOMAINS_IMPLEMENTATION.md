# M1-B B-PR4 — Domains / Vertical 集成实现（Interview + Freshness 接入统一 Session/Replay + B4 E2E）

- **状态**：`IMPLEMENTED (B-PR4 + P1/P2 review response)`。在最终 PR1/PR2/PR3 合并树上，把 Interview/Freshness vertical 层接入 canonical `m1_teacher` Session 状态机，交付 B4-01/02/03 离线确定性 E2E，并关闭独立评审 P1-1/P1-2/P1-3。
- **工作区 / 分支**：`/root/m1b/pr4int`，`b-next/pr4-domain-ports`。
  - 早期基线：PR3 HEAD `3103a06`（PR2 事务 + PR3 scoped idempotency）；vertical merge `efe385d`（合并后 692 passed）。
  - 最终合并树：`11a4f72`（PR1 judge 资产 + PR2 最终事务/恢复/P1-P2 修复 + PR3；774 既有 + 85 新增 = 859 passed）→ 评审 `dfda203` → P1/P2 修复后本轮 **869 passed**。
- **设计/评审依据**：`docs/M1_B_INTERVIEW_FRESHNESS_MAPPING.md`（设计映射）、`docs/M1_B_INTERVIEW_FRESHNESS_IMPLEMENTATION.md`（vertical 层）、`docs/M1_B_TXN_RECOVERY.md`、`docs/M1_B_SCOPED_IDEMPOTENCY_IMPLEMENTATION.md`、`docs/M1_B_PR4_REVIEW.md`（独立评审）、`docs/M1_B_PR4_REVIEW_RESPONSE.md`（P1/P2 处置与关闭证据）。
- **边界**：无网络/真实简历/招聘 JD/Provider/LiveGate；合成数据；真实学习效果 **NOT_VERIFIED**；启发式阈值 **UNCALIBRATED_HEURISTIC**（运行时可见）；不修改 M0/security/bridge/config/g*/scripts/g4/LiveGate。

## 1. 交付范围（B4.1–B4.7 + 评审 P1/P2 对应）

| 任务要求 | 实现落点 | 状态 |
|---|---|---|
| B4.1 additive `VerticalPolicy`/`DomainTurnPolicy` 接缝；engine 有策略用策略、无策略保持 CF 行为 | `m1_teacher/session/vertical.py`（`VerticalPolicy` Protocol、context/value objects、`InterviewVerticalPolicy`、`InterviewJudgeScorer`）；`session/engine.py` additive hooks（构造参数 `vertical_policy=None`、启动/恢复门、动作选择、结果迁移、事件 payload 扩展）。无策略路径语义不变 | ✅ 实现 |
| B4.2 Interview 多轮 5 阶段 + 独立支持 ladder、FULL 默认禁止/证据门、LearnerState 影响、缺项目事实 `ASK_CLARIFICATION` | 5 阶段 Socratic 追问；interview-only support ladder L1..L3（与 CF ladder 命名/命名空间分离）；FULL 默认禁用 + human-approval/evidence 门（M1-B 无审批流程，显式请求 `MAP-E11`）；加速阈值（mastery≥0.25 & evidence≥2，会话开始冻结，标 UNCALIBRATED）；`requires_project_facts` 缺事实 → `ASK_CLARIFICATION`（不代填） | ✅ 实现 |
| B4.3 统一事件表 + Replay；Interview 轮次用既有事件类型；payload 带 vertical/domain/question/rubric-audit（4 维+digest）；**P1-3：真实 session replay** | 事件类型仅既有值 + D12 add-only `SOCRATIC_QUESTION`/`ASK_CLARIFICATION`/`TURN_ADVANCED`；`ACTION_TAKEN.vertical`、`ASSESSED/MASTERY_UPDATED.rubric_audit`；新增 `TeachingSessionEngine.replay_session_state()`/`verify_session_replay()`（phase/turn/pending/last action/plan/completion），CF+Interview+跨域均有测试；`next_state` 与 `TURN_ADVANCED` 记录内容动作确认；`verify_rebuild`/`rebuild_state` 仍对两域通过 | ✅ 实现 |
| B4.4 Rubric 证据：AssessmentPort 语义、4 维独立、开放题最多 PARTIAL、unknown facts NEEDS_REVIEW、EVAL_ERROR 不改 mastery、canonical MasteryModel 唯一写者 | `InterviewJudgeScorer` 适配冻结 `AssessmentScorer`；4 维 sidecar 仅进事件 payload；mastery 仅由 engine→LearningHistory→MasteryModel 写；NEEDS_REVIEW/EVAL_ERROR 不写 mastery（测试断言 snapshot 不变、`applied=False`、`mastery_unchanged=True`） | ✅ 实现 |
| B4.5 JD v1→v2 只影响新计划；过期/冲突/未授权/未来生效 knowledge 不静默进入教学（显式 MAP-E reason） | `validate_session_start` 在任何写入前执行 JD 门（`FRESHNESS_JD_GATE_BLOCKED` + MAP-E10）与 knowledge 门（`FRESHNESS_KNOWLEDGE_GATE_BLOCKED` + MAP-E08/E09）；KEEP 允许、仅 `UPDATE+已核验权威` 允许并把 version refs 写进 `PLAN_CREATED`；运行中 session 使用自身 JD 快照，不受新 JD/过期影响 | ✅ 实现 |
| B4.6 跨域 Session + 版本拒绝；**P1-1** 计划/JD 快照持久化；**P1-3** MAP-E12/E13 | CF pause → Interview session 同库共存，snapshot/seq 连续、resume 成功；interview 计划（accelerated/fixed stages）与 JD `{jd_id,version,content_digest}` 持久化到 `SESSION_STARTED/PLAN_CREATED`，restore 从事件重建；过期 JD 恢复用 session snapshot，缺失/损坏显式 fail-closed；continue/resume 校验 domain_id/domain_version/objective/session policy/vertical policy 版本 → `MAP-E12`/`MAP-E13` 零写入 | ✅ 实现（event-level `schema_version` 行 PARTIAL，见 §9） |
| B4.7 E2E 测试 | `tests/m1_teacher/test_b4_e2e.py`（9）、`test_b4_durability_replay.py`（9）、`test_vertical_policy.py`（17） | ✅ 通过（E2E-MOCK） |
| demo | `m1_teacher/demo_b4.py`，teacher-visible learner script 作为 learner 输入；`m1_teacher.demo` 默认输出未变 | ✅ 实现 |

## 2. 架构：additive vertical seam

```
canonical engine (m1_teacher/session/engine.py)
  │  constructor: vertical_policy: VerticalPolicy | None = None   (None => CF 既有行为不变)
  ├─ start_session(): vertical.validate_session_start(...)  ← 写入前 JD/freshness/domain/objective 门
  │      SESSION_STARTED payload += domain_id/domain_version + vertical{plan, jd_snapshot, ...}
  │      PLAN_CREATED   payload += vertical{plan, jd_ref, knowledge_refs}
  ├─ 既有 session 加载: _validate_session_version_compatibility() + _ensure_vertical_plan()
  │      → vertical.restore_session(events) 从事件重建计划/JD 快照（不依赖 policy 内存）
  ├─ _select_action(): vertical.select_action(ctx) -> VerticalSelection | None
  │      None => 原 CF 选择逻辑（逐字节不变）
  ├─ _generate_and_persist(): ACTION_TAKEN payload += next_state + vertical metadata
  ├─ _plan_result_transition(): history drafts += rubric_audit（optional payload_extra）
  │      ASSESSED/MASTERY_UPDATED/ERROR/GOAL_COMPLETED payload += next_state（add-only）
  │      vertical.plan_transition(ctx) -> 多轮保持 pending/ASSESS 或完成→REVIEW
  ├─ advance_session(): TURN_ADVANCED event（add-only）记录内容动作 acknowledgment
  ├─ replay_session_state()/verify_session_replay(): 纯事件重建/比较
  └─ legacy _handle_*：同一 seam（protocol-only repo 也保持一致）
```

**契约变更（D12 add-only）**：

- `TEACHING_ACTION_KIND` += `SOCRATIC_QUESTION`、`ASK_CLARIFICATION`。
- `HISTORY_EVENT_TYPE` += `TURN_ADVANCED`（内容动作确认；`next_state` payload，供精确 session replay）。`ASSESSMENT_PREPARED` 来自 PR2。
- `LearningHistory.assessment_event_drafts/apply_assessment` 新增 **optional** `payload_extra`（默认 None，碰撞 fail-closed）。
- engine 构造参数新增 **optional** `vertical_policy=None`；PR2/PR3 事务、幂等、CAS 语义完全沿用。
- `docs/M1_ADR_001_DOMAIN_CONTRACTS.md` §6b 已记录全部 add-only 变更；`test_contracts.py` 冻结枚举期望同步。

## 3. Interview 多轮五阶段设计要点

- **主问题**：`SOCRATIC_QUESTION` / `INTERVIEW_MAIN_QUESTION`；`requires_project_facts` 时 content 附加边界提示（不编造事实）。
- **五阶段追问**：`concept → hypothesis → complexity → experiment_design → online_triage`，reason `INTERVIEW_PROBE_<STAGE>`；只提问不给答案；阶段/推进状态来自事件。
- **LearnerState 影响（确定性）**：会话开始时若目标节点 mastery ≥ `0.25` 且 `evidence_count ≥ 2` → 冻结为跳过 concept 的 4 阶段；两个相同种子 learner 走相同序列。阈值标 `UNCALIBRATED_HEURISTIC`，运行时 payload/reason 可见。
- **项目事实边界**：`requires_project_facts` 且答案无 learner-owned facts → judge `NEEDS_REVIEW:PROJECT_FACTS_REQUIRED` → `ASK_CLARIFICATION`（要项目/角色/规模量级/指标来源；无示例数字）；learner 补充事实后继续；重复缺失允许有限次 clarify 后回退，不代填。
- **Interview support ladder**：连续 `INCORRECT` → `HINT` reason `INTERVIEW_HINT_LEVEL_1/2/3`（LIGHT→INVARIANT→STRUCTURE）；cap 由证据量决定；`FULL` 只在显式 human approval + evidence≥5 才可能（M1-B 无审批流程，`request_full_solution()` 必抛 `MAP-E11`）。
- **终止规则（准确表述，替代旧“8 轮上限”）**：完成条件为 `advancing answers ≥ 1 + len(stages)`；推进只认 `CORRECT/PARTIAL`，`INCORRECT` 触发 support ladder、`NEEDS_REVIEW`/clarification/hint 不推进。完整 5 阶段通常 6 轮，加速 4 阶段通常 5 轮；没有独立“8 轮计数器”。完成后 pending 清空、phase=REVIEW；是否 GOAL_COMPLETE 仍由 canonical planner 的客观 success criteria 决定。
- **CF vs Interview ladder 命名**：CF 沿用 A 线 `HINT_L1..L3`（无 FULL 入口，结构上 fail-closed）；B 线的 `LIGHT/INVARIANT/STRUCTURE` 仅用于 interview support ladder，`cf_hint_ladder_shared=false`。B4.3 的统一 “LIGHT→FULL” 命名未在 CF 落地（P2-7 文档化接受）。

## 4. 统一事件 / Replay / 版本

- **事件类型**：不新增语义事件（仅 D12 add-only 的 action kinds + `TURN_ADVANCED`）；Interview 轮次 = `RESPONSE_SUBMITTED` → `ASSESSMENT_PREPARED` → `ASSESSED`/`MASTERY_UPDATED` → `ACTION_TAKEN`。PR2 transaction A/B、scoped idempotency、CAS 保留。
- **payload 扩展**：
  - `SESSION_STARTED.payload`: `domain_id/domain_version`；`vertical.{plan{stages,accelerated,objective_id,policy_version,thresholds,calibration_status}, jd_snapshot{jd_id,version,content_digest,valid_from,valid_until}, question_id, target_node_id, jd_ref, knowledge_refs, interview_hint_ladder, full_solution_enabled}`。
  - `PLAN_CREATED.payload.vertical`: plan + jd_snapshot + jd_ref + knowledge_refs。
  - `ACTION_TAKEN.payload`: `next_state{phase,turn_index,pending_item_id}` + `vertical{...reason_code,probe_stage,hint_level,calibration_status,jd_ref,plan_stages,...}`。
  - `ASSESSED`/`MASTERY_UPDATED.payload`: `rubric_audit{question_id,scorer_id,status,open_answer,dimensions{4},failure_modes[],spec_digest}` + `vertical` + `next_state`（terminal drafts）。
  - `TURN_ADVANCED.payload.next_state`: 内容动作确认后的 phase/turn/pending。
- **Replay**：`replay_session_state(session_id)` 仅消费事件重建 phase/turn/pending/last action/plan（含 `advanced_answers`/`next_stage`/`ladder_completed`）/completed；`verify_session_replay(session_id)` 与持久 session 比较并返回差异（篡改测试可证伪）。`LearningHistory.rebuild_state/verify_rebuild` 继续重建 LearnerSnapshot；两套 replay 均为真实 API。
- **版本拒绝**：`_validate_session_version_compatibility()` 在 continue/resume/replay 前检查 `SESSION_STARTED` 的 `domain_id/domain_version/objective_id/session_policy_version` 与 vertical payload 的 `domain_id/policy_version`；不匹配 → `MAP-E12_DOMAIN_VERSION_MISMATCH` / `MAP-E13_EVENT_VERSION_INCOMPATIBLE`，零写入。**event-level `schema_version`/fixture 版本未知拒绝未实现**（payload 无该字段，repository schema 归 PR3）；设计表中该行声明为 PARTIAL。
- **determinism**：固定 ids/seed/clock；测试/demo 投影去除时间戳后逐字节相等；demo 两次运行同 sha。

## 5. JD / Freshness 门禁（P1-1 修订）

- **新 session 启动前 fail-closed**（`validate_session_start`，在 `upsert_goal`/save/events 之前）：JD 唯一有效窗口（过期/未生效/重叠/未知 → `FRESHNESS_JD_GATE_BLOCKED` + MAP-E10），knowledge RECHECK → `FRESHNESS_KNOWLEDGE_GATE_BLOCKED` + MAP-E08/E09；被拒时 0 event / 0 session / 0 goal。
- **运行中 session 恢复**：不再重新解析默认 JD；`restore_session` 使用 `SESSION_STARTED` 的 `jd_snapshot{jd_id,version,content_digest}`，因此 JD 中途过期/切版本也不影响既有 session，且绝不会写 `jd_ref=jd:rec@None`。快照缺失/损坏 → `VERTICAL_JD_SNAPSHOT_UNAVAILABLE`；计划缺失/损坏 → `VERTICAL_PLAN_SNAPSHOT_MISSING` / `VERTICAL_PLAN_SNAPSHOT_CORRUPT`。
- **JD v1→v2**：只影响新 session/新 plan；既有 session payload/计划不变。
- 数据为 synthetic 静态时间戳；无真实抓取/调度/热点真实更新声明。

## 6. B4-01/02/03 + B4-04/05 本地证据

> 证据等级：**E2E-MOCK + DETERMINISTIC**（合成数据、无网络）；独立 Reviewer 对本轮修复的复跑仍 **NOT_RUN**；真实教学效果 **NOT_VERIFIED**。

| case | 内容 | 本地证据 | 结果 |
|---|---|---|---|
| **B4-01** | 2 CF learner 统一 canonical mastery/session journal | `test_b4_01_two_cf_learners_share_canonical_mastery_and_session_journal`；不同 action/mastery/plan 路径；seq 连续/事件类型合法；两 learner `verify_rebuild` 一致；CF 事件无 vertical 字段 | 通过 |
| **B4-02** | 2 interview learner + JD v1→v2 + 5 阶段 + clarify + 4 维 rubric | `test_b4_02_two_interview_learners_five_stage_jd_and_rubric`；A 加速跳过 concept，B 完整 5 阶段 + clarify + hint L1；4 维 audit + 64-hex digest；teacher-visible learner script 为输入；全事件流无 hidden 路径/字段；FULL 不出现 | 通过 |
| **B4-03** | EXPIRED/CONFLICT/UNAUTHORITATIVE 不进入教学；JD 过期/未生效拒绝 | `test_b4_03_freshness_and_jd_gates_block_before_teaching`：9 场景 KEEP2/UPDATE2/RECHECK5；5 个 RECHECK 与 2 个 JD 时间窗全部写入前拒绝；eligible UPDATE 进计划 refs | 通过 |
| **B4-04**（跨域/暂停恢复） | CF pause → Interview → resume；interview pause/restart 恢复计划；不再漂移 | `test_cross_domain_pause_and_interview_session_continuity`、`test_interview_pause_resume_restores_persisted_stage_plan`、`test_accelerated_plan_survives_restart_after_complexity` | 通过 |
| **B4-05**（版本拒绝） | MAP-E12/E13 展开；不匹配显式错误码、零写入 | `test_version_incompatibility_rejected_with_zero_writes`（MAP-E13 session policy / MAP-E13 vertical policy / MAP-E12 domain_version）；`test_vertical_version_and_objective_mismatch_rejected`（精确 `VERTICAL_OBJECTIVE_MISMATCH`，零事件） | 通过（event schema_version 行 PARTIAL，见 §9） |

## 7. 真实运行输出（最终树实测）

环境：`/root/Autonomous Teacher/.venv/bin/python`（Python 3.11.15 / pytest 9.2.0）；工作区 `/root/m1b/pr4int`。

```bash
# 最终全量回归（P1/P2 修复后）
$ "/root/Autonomous Teacher/.venv/bin/python" -m pytest tests/m1_teacher -q
869 passed in 78.12s

# 定向
$ pytest tests/m1_teacher/test_b4_durability_replay.py -q
9 passed
$ pytest tests/m1_teacher/test_b4_e2e.py tests/m1_teacher/test_vertical_policy.py -q
26 passed

# 静态检查
$ ruff check m1_teacher tests/m1_teacher
All checks passed!

# 确定性 demo（两次运行逐字节相同）
$ python -m m1_teacher.demo_b4 --json > run1.json
$ python -m m1_teacher.demo_b4 --json > run2.json
$ cmp -s run1.json run2.json && echo identical
identical
sha256(run1.json) = b3231658a4ac12a49cd2ac57f4a3e8d9719fbf7476ca36a54e4d8f9eea72d905
```

demo 摘要（真实输出）：B4-01 `paths_differ=true`；B4-02 `learner_input_source=teacher-visible vertical/interview/learner_scripts/answers.json`、`learner_script_sha256=bd81292ad08357ff…`、`jd_versions=[v2,v1]`、`paths_differ=true`、`full_solution_emitted=false`、A 跳过 concept / B 完整 5 阶段 + clarify 1 + hint L1；B4-03 `decision_counts={KEEP:2,UPDATE:2,RECHECK:5}`、`silent_imports=0`。

**测试计数构成**：774（PR3 final 基线）+ 60（vertical）+ 25（B4 E2E/policy）+ 9（durability/replay/version）+ 1（P2-3 calibration）= **869**。

## 8. 对既有测试/断言的保护（P1-2 强化）

- 既有 774 测试全部保持通过（PR1 opt-in/泄漏、PR2 事务/崩溃矩阵、PR3 scoped idempotency/并发）。
- hidden-scoring reader allow-list **恰好** `{scorer.py, interview_judge.py}`：`tests/m1_teacher/guard_support.py` 用 AST/路径组件检测 `**/scoring/**`（含分片路径构造），三条守卫测试（`test_assessment_scorer.py`、`test_e2e_resume_idempotency.py`、`test_b4_e2e.py`）均断言 allow-list 精确等于该集合；`demo_b4.py`/B4 E2E/vertical-policy tests 不引用 hidden 路径，learner 输入来自 teacher-visible learner script。
- 泄漏扫描**不再剥离** `canonical_response`：断言每个 `ASSESSMENT_PREPARED.canonical_response` 逐值属于 learner script，且完整事件流不含 hidden 路径/字段/文件夹名。
- 既有测试唯一显式修改：`test_contracts.py` 枚举冻结期望追加 D12 值；两条 guard 从字面串升级 AST（语义更严格）；`test_interview_fixtures/test_interview_domain` 断言 opaque `rubric/*.json` ref（配合 P2-1）；无断言弱化/删除。
- `m1_teacher.demo` 默认 JSON/文本输出与合并前**逐字节一致**：`demo.py` 仅把 additive `TURN_ADVANCED` 从历史 `event_count` 投影中排除（`sha256=0ac438a3…` 不变），未改默认输出/哈希语义。

## 9. 仍 NOT_RUN / 限制 / 声明降级

- **独立 Reviewer 复跑**：本轮 P1/P2 修复为 Owner 侧证据；独立复跑仍 **NOT_RUN**。
- **MAP-E13 event-level schema_version**：设计表中 “event `schema_version != m1a.v0` → 拒绝 replay” 一行 **PARTIAL / NOT_IMPLEMENTED**（`HistoryEvent.payload` 无独立 schema_version 字段，repository schema 由 PR3 迁移负责）。当前 MAP-E13 覆盖 session-policy/vertical-policy/plan-policy 版本。
- **P2-2 持久复核队列/审计事件**：**NOT_IMPLEMENTED**；阻塞决策仍为“写入前 fail-closed + 显式 reason/map_code”，0 事件可 replay；留待 PR5。
- **P2-7 CF 统一 ladder port**：**PARTIAL/文档化**：CF 仍 A 线 `HINT_L1..L3`，B 线命名（LIGHT/INVARIANT/STRUCTURE）只用于 interview；CF 无 FULL 显式请求入口（结构上不可达）。
- 真实学习效果、真实网络/招聘网站/个人简历/JD/Provider/API Key/LiveGate/付费请求：**NOT_VERIFIED / NOT_RUN**；阈值 **UNCALIBRATED_HEURISTIC**（运行时可见）。
- 隐藏题集（B 线 `hidden/`）未转换为 vertical hidden 评测集；隐藏 reference answers 仅用于 scorer-side judge 单测，不作为 learner 输入。
- 无 UI/人工审批工作流；`FULL_SOLUTION` 在 M1-B 结构上不可达（比“默认禁止”更严格）。
- 事件 `created_at` 仍为 wall-clock 历史语义；确定性测试/demo 投影去除时间戳后比较。

## 10. 文件清单（本轮 P1/P2 增改）

新增：
- `fixtures/m1_teacher/vertical/interview/learner_scripts/answers.json`（teacher-visible synthetic learner script；非 hidden answer key）。
- `tests/m1_teacher/guard_support.py`（AST/路径组件 hidden-reader 守卫）。
- `tests/m1_teacher/test_b4_durability_replay.py`（P1-1 计划持久化/重启/pause/JD 快照 + P1-3 replay/版本拒绝，9 tests）。
- `docs/M1_B_PR4_REVIEW_RESPONSE.md`（P1/P2 处置与关闭证据）。

修改（add-only/文档）：
- `m1_teacher/session/vertical.py`：plan/JD snapshot 持久化与 restore、payload 签名、UNCALIBRATED 标记。
- `m1_teacher/session/engine.py`：`_validate_session_version_compatibility`、`_ensure_vertical_plan`、`replay_session_state`/`verify_session_replay`、`next_state`/`TURN_ADVANCED`、版本拒绝钩子。
- `m1_teacher/contracts/types.py`：D12 `TURN_ADVANCED`。
- `m1_teacher/assessment/interview_judge.py`：opaque `rubric/*.json` ref 解析（legacy 兼容）。
- `fixtures/.../questions.json`：`scoring_spec_ref` → opaque；`tests/m1_teacher/test_interview_fixtures.py`/`test_interview_domain.py` 断言。
- `m1_teacher/demo_b4.py`：learner script 输入，移除 hidden reference answers 读取。
- `tests/m1_teacher/test_b4_e2e.py`/`test_vertical_policy.py`：learner script + no-strip 泄漏扫描 + P2-1/P2-3/P2-4 断言 + guard_support。
- `tests/m1_teacher/test_assessment_scorer.py`/`test_e2e_resume_idempotency.py`：AST/path 守卫。
- `docs/M1_ADR_001_DOMAIN_CONTRACTS.md` §6b：`TURN_ADVANCED` change log。
- `docs/M1_ARCHITECTURE.md`：事件枚举行 + B-PR4 P1-1/P1-3 change log。
- `docs/M1_B_INTERVIEW_FRESHNESS_IMPLEMENTATION.md`：hidden allow-list/demo learner script 段落更新。
- `m1_teacher/demo.py`：历史 `event_count` 投影排除 additive `TURN_ADVANCED`，保证冻结默认 JSON/文本输出逐字节不变。
- `docs/M1_B_DOMAINS_IMPLEMENTATION.md`：本文件（最终数字/声明降级/8 轮规则等）。

## 11. 复现

```bash
cd /root/m1b/pr4int
"/root/Autonomous Teacher/.venv/bin/python" -m pytest tests/m1_teacher -q              # 869 passed
"/root/Autonomous Teacher/.venv/bin/python" -m pytest tests/m1_teacher/test_b4_durability_replay.py -q  # 9 passed
"/root/Autonomous Teacher/.venv/bin/python" -m pytest tests/m1_teacher/test_b4_e2e.py tests/m1_teacher/test_vertical_policy.py -q  # 26 passed
"/root/Autonomous Teacher/.venv/bin/python" -m m1_teacher.demo_b4 --json                # 确定性 B4 摘要
```

---

*本文只说明 B-PR4（含 P1/P2 评审修复）在离线/合成/确定性范围内的实际实现与实测；未运行项一律标注 NOT_RUN/PARTIAL，合成与启发式证据不构成真实教学效果或独立验收结论。*
