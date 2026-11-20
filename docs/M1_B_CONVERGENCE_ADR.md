# M1-B Contract Convergence ADR（B-PR0）

| 字段 | 值 |
|---|---|
| 文档状态 | **DRAFT / DESIGN_ONLY**（未冻结；等待维护者签收） |
| 本阶段性质 | **纯设计 + 源码审计**。本文**未实现任何代码、未集成、未验证**；不包含新测试通过声明 |
| 证据类别 | 仅 `SOURCE_INSPECTED`（本 worktree 阅读冻结源码）与 `DESIGN_ONLY`（设计提案）；所有“应该/将/需要”均为设计意图，**当前未实现** |
| 基线 | `main = 3e7afee077845a071cd364e93ab209cac20b2d5f` |
| A 线（canonical 候选） | `work/m1a-mvp` = **`4706250643fd42d48d69ddad7159e011955fa9fd`**（含 `m1_teacher`，独立 Review 结论 `PASS_FOR_M1A_OFFLINE_MVP`，536 tests 冻结参考） |
| B 线（vertical 候选） | `work/m1-offline-design` = **`290c5770461bb5af2a38c6e6d24ee76350bcb410`**（含 `m1_offline`，独立 Review 结论 `PASS_FOR_M1_OFFLINE_DESIGN_AND_EVALUATION_SCOPE`，365 tests 冻结参考） |
| 历史数字纪律 | **536 与 365 是两条独立分支上的历史冻结参考，不可相加，也不存在“统一 901 tests”**；新集成必须重新独立验收（见 §10） |
| 硬边界 | 离线、无 Key、无真实 Provider/网络、无真实学习者数据、不触碰 M0/security/bridge/config/g*/scripts/g4*/LiveGate |
| 相关交付 | 同批 `docs/M1_B_PORTS.md`（端口与迁移）、`docs/M1_B_CI_AND_DEMO.md`（冻结 CI/Demo/静态隔离命令） |

---

## 0. 阅读者摘要（TL;DR）

1. **唯一 canonical 裁决（建议，待维护者签收）**：以 **A 线 `m1_teacher`（`m1a.v0` + SQLite + Session Engine）**
   作为唯一 TeacherCore 业务状态、事件协议、Learner Mastery 写入者与可审计 Replay；B 线 `m1_offline`
   作为 **CF Hint / Interview / Freshness vertical（Domain Plugin / KnowledgeSource）**，通过端口接入，
   **不得直接写 LearnerState/Snapshot/Event Log，不得读取隐藏评分标签**。
2. **禁止双写**：不存在“两套 LearnerState 各自写入、再合并”的方案；部署前禁止双写、禁止自动迁移真实
   learner 数据库；只允许维护者离线运行的 v1 compatibility adapter（additive、可校验、可回滚）。
3. **既有包合约不原地改语义**：A/B 两侧既有类型/协议字段不重命名、不删除；新能力只做 additive 扩展，
   并记录版本（`m1a.v0` 保持冻结；B 线类型留在 vertical 边界内，不进入 TeacherCore 事件协议）。
4. **源码核对到的 Top 5 合同冲突**（详见 §11）：B 无持久化/会话状态机；B 无结构化 `Reason`；两套事件
   模型无 `seq`/session 绑定；`AssessmentResult` 语义不同（`status` vs `passed/dimensions`）且 B 判题器
   把 hidden expected 放进 `JudgeResult.failures`；`result_id` 全局查重（A 线 B-03 缺陷）与 B 线无作用域
   幂等键，二者都未达到统一 idempotency 合同。
5. **本文件不声称新集成已经可用**：所有 B0 成果为 `DESIGN_ONLY`；B0-01 证据矩阵状态仍为 `NOT_RUN`，
   由独立 Reviewer 静态预审后才进入 B-PR1。

---

## 1. 背景与目标

M1 阶段存在两条**并行、互不依赖**的实现线，均以 `main=3e7afee` 为共同基线，**不是连续 PR 链**：

- **A 线 `m1_teacher`（`m1a.v0`）**：frozen contracts + validated knowledge graph + CF domain adapter +
  证据驱动 mastery + append-only history + SQLite 持久化/重建 + diagnostic + planner + session state
  machine + independent scorer + E2E demo（`docs/M1_ARCHITECTURE.md`、`docs/M1_ADR_001_DOMAIN_CONTRACTS.md`）。
- **B 线 `m1_offline`（`m1.offline.v0`）**：Teacher Core 类型/记忆/学习者模型 + `RuntimePort` mock +
  TeachingPolicy/Hint Ladder + CurriculumPlanner + Diagnostics + CF Teacher/Judge + Interview Coach/Rubric +
  Freshness + 评测层（`docs/m1/TEACHER_CORE_ARCHITECTURE.md`、`docs/m1/ADR-TEACHER-CORE.md`）。

两条线各自独立 PASS，但**教学合同尚未统一**（来源：`/root/leadb_zip/COMMON_REVIEW_AND_ROADMAP.md` §1、§2 B-04）。
B0 的目标：在任何功能移植（B-PR1 Judge 边界、B-PR2 事务、B-PR3 幂等、B-PR4 两域整合、B-PR5 集成验收）
**之前**，冻结唯一合同并给出可审计迁移方案。

**本 ADR 的目标**

1. 逐字段对照两套 schema 的身份、知识、证据、评分、掌握度、原因、历史、运行时、领域接口、目标、
   scorer identity、时间戳/版本策略；
2. 做出唯一 canonical 裁决（含备选代价与不选理由）；
3. 给出 v1 compatibility adapter（只增）与迁移 checksum/rollback 设计；
4. 冻结“谁能写 LearnerState/Snapshot/Event Log”；
5. 固定历史测试数字口径，防止把两条线的测试数相加。

**非目标**

- 不实现任何代码、端口、迁移工具或测试；不修改 A/B 任一实现文件；
- 不把 B 线 vertical 直接合入 A 线；不合并 commit；
- 不声称真实教学效果、真实学习者或真实模型能力（一律 `NOT_VERIFIED`）；
- 不改变 M0/A 线安全边界与 LiveGate 状态。

---

## 2. 证据等级与审计口径

| 等级 | 本文中的含义 | 可用于 |
|---|---|---|
| `SOURCE_INSPECTED` | 在本 worktree 冻结 SHA 上阅读源码/文档得到的事实（含 `file:line` 引用） | 对照表、冲突描述、CI 命令事实 |
| `DESIGN_ONLY` | 本文提出的裁决/端口/迁移/rollback 方案，**当前未实现** | 决策提案、后续 PR 输入 |
| （未使用）`MEASURED` | 本轮 B-PR0 **不产生**新的测试/验收测量结论；只读运行结果记录在 `M1_B_CI_AND_DEMO.md`，仅作为命令冻结输出，不作为新验收 PASS | — |

历史 PASS 只引用各自分支的冻结 Review 结论，**不跨线继承**：
A 线 `PASS_FOR_M1A_OFFLINE_MVP`、B 线 `PASS_FOR_M1_OFFLINE_DESIGN_AND_EVALUATION_SCOPE`；新集成需要
新的独立 Reviewer 与新的验收范围。

---

## 3. 两条实现线概览（§3–§5 结论的量化基础）

| 维度 | A 线 `m1_teacher`（`m1a.v0`） | B 线 `m1_offline`（`m1.offline.v0`） |
|---|---|---|
| 源码规模（`find -name '*.py' \| wc -l` 汇总） | `m1_teacher/` **10,092 行**（26 文件） | `m1_offline/` **8,415 行**（21 文件） |
| 测试（历史冻结） | `tests/m1_teacher` **536 passed**（PR1 268 / PR2 100 / PR3 50 / PR4 75 / PR5 43） | `tests/m1_offline` **365 passed**（361 + 4 回归） |
| 类型层 | `m1_teacher/contracts/types.py` 16 个 `Record` 子类 + `*_VALUES` 枚举 + 严格 `from_dict` | `m1_offline/types.py` 16 个 `Record` 子类 + `*_VALUES` 枚举 + 严格 `from_dict` |
| 持久化 | SQLite `schema_meta.version==1` + 6 表（`m1_teacher/learner/repository.py:90-125`），WAL/FK/`BEGIN IMMEDIATE` | **无持久化 DB**；`LearningMemory` 内存 + JSONL 导出/导入（`m1_offline/memory.py:52-145`） |
| Learner State | 物化 `LearnerSnapshot`（可重建缓存）+ append-only `HistoryEvent`（事件为 source of truth） | 内存 `LearnerState`（`m1_offline/learner_model.py:56`）；`replay(events)` 可重建但无跨进程持久化 |
| Session/事务 | `SessionState` + `TeachingSessionEngine`（8 phases、pause/resume、EVAL_ERROR 隔离）；`m1_teacher/session/engine.py:210` | **无教学 session 状态机**；无 session 持久化/恢复 |
| 结构化解释 | `Reason{code,node_ids,detail,policy_version}`（`contracts/types.py:714`） | `rationale: str`（`types.py:549`）、`explanation: str`（`types.py:583`）、plan `rationale: list[str]`（`types.py:525`） |
| 领域抽象 | `DomainAdapter` + `DomainRegistry`（`contracts/domain.py:24/61`）+ `KnowledgeGraph`（`knowledge/graph.py:40`） | 无 DomainAdapter/Registry/KnowledgeGraph；CF/Interview/Freshness 由具体类直接暴露 |
| 领域覆盖 | 仅 CF binary search（`domains/cf_binary_search.py:275`） | CF + Interview + Freshness 三个 vertical（含评测层） |
| 运行时边界 | 无 `RuntimePort`（grep `RuntimePort` = 0 hit）；教师核心不调用模型 | `RuntimePort.send()`（`runtime_port.py:52/61`）+ `MockRuntimePort`（`runtime_port.py:78`，`simulated=True`） |
| Replay | `HistoryEvent` 按 learner `seq` 排序 + `MasteryModel.rebuild_snapshot`（`learner/model.py:358`）+ `LearningHistory.verify_rebuild`（`learner/history.py:357`） | `LearnerModel.replay(evidence)`（`learner_model.py:198`）+ `LearningMemory.replay(loop_id)`（`memory.py:92`）+ harness `replay_trace`（`evaluation/harness.py:1187`） |
| 证据类别 | `MOCK / DETERMINISTIC / HUMAN_REVIEWED / NOT_VERIFIED`（A 报告固定词汇） | `MEASURED / PLAN / NOT_RUN / UNVERIFIED`（`docs/m1/EVALUATION_PROTOCOL.md:34-37`） |

> 结论：A 线提供**可恢复持久化 + 唯一写入者 + 审计 Replay + 会话状态机**；B 线提供**领域 vertical 覆盖 +
> Runtime 抽象 + Hint/Interview/Freshness 内容与规则**。二者是互补能力，不是同一份合同的两个副本。

---

## 4. 逐字段对照表

列约定：
- **A 位置 / B 位置**：`file:line`（冻结 SHA 上源码行号）。
- **可空性**：无默认值且构造必填 = `required`；`X \| None` = nullable。
- **序列化名**：两者均“字段名即 JSON key”，差异只在 `schema_version` 的位置/是否构造参数（见 4.12）。
- **迁移动作**：`PASS`（值语义可原样传递）、`MAP`（需映射函数/默认值/查表）、`REJECT`（不可表达，必须
  fail-closed 拒绝并在 manifest 记录），并给出计划中的拒绝码（`MIGRATION_*`，设计码，未实现）。
- 所有 A 记录均含 `created_at`（部分含 `updated_at`）；B 记录时间戳仅部分存在，空串在建构造时由
  `_fill_time()` 填成 `now_utc()`（`m1_offline/types.py:251-256`）。

### 4.1 身份键：LearnerId / SessionId / GoalId / EventId / ResultId / TaskId

| 字段 | A 线 `m1a.v0` | B 线 `m1.offline.v0` | 可空性 / 默认 | 序列化名 | 时间戳策略 | 版本策略 | 语义差异 | 迁移动作 |
|---|---|---|---|---|---|---|---|---|
| LearnerId | `HistoryEvent.learner_id`（`contracts/types.py:812`）；`LearnerSnapshot.learner_id`（`:770`）；`LearnerGoal.learner_id`（`:796`）；DB `learners.learner_id` PK（`learner/repository.py:93`） | `LearnerProfile.learner_id`（`m1_offline/types.py:409`）；`EvidenceEvent.learner_id`（`:428`）；`LearnerState.learner_id`（`:455`） | required，非空 str（两侧） | `learner_id` | 无 | 无 | A 有 learner 注册表/外键；B 仅有 profile 记录（内存）。两者都**没有真实鉴权/多租户边界**（M1-A 声明） | `PASS`（不透明 str 原样）；但导入时必须校验 A 侧 `learners` 行存在/创建，禁止把未知 learner 直接写入 |
| SessionId | `SessionState.session_id`（`contracts/types.py:824`）；`HistoryEvent.session_id`（`:813`）；DB `sessions.session_id` PK（`learner/repository.py:125`） | **不存在教学 session 标识**。仅有 `RuntimeRequest.session_id`（`types.py:640`）与 `RuntimeResponse.session_id`（`:660`），是 mock runtime 的请求作用域；`EvidenceEvent` **没有** `session_id`（`:426-435`） | A required；B 仅 runtime 作用域 | 同名但语义不同 | A session `updated_at`；B runtime 无 | A `sessions` 表无版本列（schema_meta 全局） | A = 跨轮持久状态机单元（pause/resume/重启恢复）；B = 单次 mock 请求作用域。**禁止把 B runtime request id 当 A session id** | `REJECT`（B 证据/Session 缺失 session 绑定）：`MIGRATION_MISSING_SESSION`；A session 只能由 canonical SessionEngine 新建 |
| GoalId | `LearnerGoal.goal_id`（`types.py:795`）；DB `goals.goal_id` PK（`learner/repository.py:116`） | `LearningGoal.goal_id`（`m1_offline/types.py:473`） | required 非空 str | `goal_id` | A/B 均有 created_at | 无 | A goal 绑定 `objective_id`（领域目标）；B goal 绑定 `target_skills[]`（任意技能 id），无 objective 概念 | `MAP`（B→A 需 objective 映射表；无映射→`MIGRATION_UNSUPPORTED_GOAL_MAPPING`） |
| EventId | `HistoryEvent.event_id`（`types.py:811`）PK；确定性格式 `evt.<learner_id>.<seq>`（`learner/history.py:193`） | `EvidenceEvent.event_id`（`m1_offline/types.py:427`）生产方自定；`TraceEvent.event_id`（`:684`） | required 非空 str | `event_id` | A/B 均 created_at | A 事件集枚举；B kind 枚举 | A 事件 id 由历史层生成 + `UNIQUE(learner_id, seq)`；B 无 seq、无 session、生产者自定 id；两者都以 event_id 幂等 | `REJECT`（直接 id 复用会与 A 生成规则冲突）：`MIGRATION_EVENT_ID_CONFLICT`；历史导入需改写为 A 事件并在 payload 保留 `source_event_id`+校验和 |
| ResultId | `AssessmentResult.result_id`（`types.py:692`）；幂等事件 id `evt.assessed.<result_id>`（`learner/history.py:109-118`） | `AssessmentResult.assessment_id`（`m1_offline/types.py:602`），确定性 `asmt_...`（`cf/teacher.py` 约 `:718`） | required 非空 str | 不同名 | created_at | 无 | A 用它做全局/待修复的幂等键（B-03 缺陷：跨 learner/session 查重）；B 无学习状态写入链 | `REJECT`（在 B-PR3 作用域修复完成前）：`IDEMPOTENCY_SCOPE_UNSAFE`；统一合同要求 composite key（learner, session, item, turn, result_id）+ request digest |
| TaskId / ItemId | `AssessmentItem.item_id`（`types.py:668`）；`AssessmentResult.item_id`（`:693`） | `LearningTask.task_id`（`types.py:496`）；`AssessmentResult.task_id`（`:603`）；`EvidenceEvent.task_id`（`:429`） | required | 不同名 | — | — | A 的“item”是领域适配器提供的具体评估题；B 的“task”是任务库条目（含 fixture_ref）。二者是不同粒度 | `MAP`（需 fixture/任务映射表；缺失→`MIGRATION_UNSUPPORTED_TASK_MAPPING`） |

### 4.2 KnowledgeNode vs SkillNode（+ PrerequisiteEdge）

| 字段 | A 线 `m1a.v0` | B 线 `m1.offline.v0` | 可空性 / 默认 | 序列化名 | 时间戳策略 | 版本策略 | 语义差异 | 迁移动作 |
|---|---|---|---|---|---|---|---|---|
| 节点主键 | `KnowledgeNode.node_id`（`contracts/types.py:582`） | `SkillNode.skill_id`（`types.py:340`） | required 非空 str | 不同名 | A created_at；B 无 | 无 | A 有全局唯一节点 + 领域 id；B 是技能图节点 | `MAP`（skill_id→node_id，需映射表；无映射→`MIGRATION_UNSUPPORTED_SKILL_MAPPING`） |
| 名称/描述 | `title`（`:584`，非空）、`description`（`:585`） | `name`（`:341`，非空）、`description`（`:344`，可空） | required | 不同名 | — | — | 基本对应 | `PASS`（字段改名映射） |
| 领域 | `domain_id`（`:583`） | `domain`（`:342`） | required | 不同名 | — | A 有 `domain_version`（adapter 级，`domains/cf_binary_search.py:573`）；B 无领域版本 | B 的 domain 是字符串标签，无版本/注册表 | `MAP`（domain 原样；domain_version 由 A adapter 决定；B→A 需人工声明 `MIGRATION_DOMAIN_VERSION_UNSPECIFIED` 或显式参数） |
| 难度 | `difficulty: int` 1..5（`:586`，`_range_meta(minimum=1, maximum=5)`） | **无对应字段** | A required | `difficulty` | — | — | B 无难度标签 | `REJECT`（不得编造）：`MIGRATION_UNSUPPORTED_FIELD:difficulty`；或由维护者提供显式 `skill_id→difficulty` 映射表（记录在 manifest） |
| 考核方式 | `assessment_mode` ∈ `DETERMINISTIC_JUDGE/RULE_RUBRIC/HUMAN_REVIEW_REQUIRED`（`:587`） | **无对应字段**（B 由 vertical 具体判定器决定） | A required | `assessment_mode` | — | — | B 无评估模式声明 | `REJECT`：`MIGRATION_UNSUPPORTED_FIELD:assessment_mode`；提供显式映射参数才可迁移 |
| 标签/内容引用 | `tags: list[str]` 默认 `[]`（`:588`）；`content_ref: str` 默认 `""`（`:589`） | **无对应字段**（B 的 content 在 fixtures/vertical 内部） | A default | `tags`,`content_ref` | — | — | B 无 tags/content_ref | `MAP`（默认空值 + 显式可选映射；记录 `lossy_default_filled`） |
| 前置关系 | 独立记录 `PrerequisiteEdge{source_node_id,target_node_id,kind ∈ HARD/SOFT,weight 0..1}`（`types.py:594-601`）；图校验/环检测在 `knowledge/graph.py:40` | `SkillNode.prerequisites: list[str]` 默认 `[]`（`types.py:343`） | A required；B default [] | `prerequisites`（B 内嵌） vs 独立 edge | — | — | A 有向 edge + HARD/SOFT + 权重 + DAG 校验；B 仅无向/未分级的 skill id 列表，无环校验、无权重 | `MAP`（保守映射为 `HARD` + `weight=1.0` 并在 manifest 记 `lossy:prerequisite_kind_defaulted`；或拒绝→`MIGRATION_UNSUPPORTED_PREREQUISITE_KIND`）。**不得**把 B 前置默认当成 SOFT |
| 时间戳 | `created_at`（`:590`） | 无时间戳字段 | A default now_utc | `created_at` | 见 4.12 | — | B SkillNode 无法追溯创建时间 | `MAP`（迁移时间由 manifest 记录，不从 B 记录伪造） |

### 4.3 证据事件：A `HistoryEvent` vs B `EvidenceEvent` + `TraceEvent`

| 字段 | A 线 | B 线 | 可空性 / 默认 | 序列化名 | 时间戳策略 | 版本策略 | 语义差异 | 迁移动作 |
|---|---|---|---|---|---|---|---|---|
| 事件主键 | `HistoryEvent.event_id`（`types.py:811`） | `EvidenceEvent.event_id`（`m1_offline/types.py:427`） | required | `event_id` | A created_at；B created_at（空→now） | — | 见 4.1 | `REJECT`（id 冲突）→ 新 A 事件 + `source_event_id` payload |
| 归属 | `learner_id`（`:812`）+ `session_id`（`:813`） | `learner_id`（`:428`）+ `task_id`（`:429`）；**无 session_id** | required | 不同 | — | — | A 事件属于 learner+session；B 事件属于 learner+task | `MAP`（task→item 映射+显式 session 绑定；缺失→`MIGRATION_MISSING_SESSION`） |
| 顺序 | `seq: int >=0`（`:814`）；DB `UNIQUE(learner_id, seq)`（`repository.py:104`） | **无 seq**；顺序 = 生产者 append 顺序（`_applied_event_ids` 去重，`learner_model.py:178` 附近） | A required | `seq` | — | — | A 可在 DB 中严格重排/重放；B 仅内存顺序 + JSONL 行序 | `MAP`（按 manifest 中的 source order 重新赋 seq；映射结果必须可重复生成相同 checksum） |
| 类型 | `event_type` ∈ `HISTORY_EVENT_TYPE_VALUES` 12 值（`types.py:101-118`） | `kind` ∈ `EVIDENCE_KIND_VALUES` 6 值（`types.py:43-51`） | required | 不同名 | — | — | A 是教学/会话事件流（含 SESSION_STARTED/PLAN_CREATED/…/GOAL_COMPLETED/ERROR）；B 是证据类型（ANSWER/CODE_SUBMISSION/…/HINT_REQUEST） | `MAP`（映射表见 §5.1；不可映射值→`MIGRATION_UNSUPPORTED_EVENT_KIND`） |
| 载荷 | `payload: dict` JSON（`:816`） | `payload: dict`（`:431`）+ `observed_score: float\|None`（`:432`）+ `error_codes: list[str]`（`:433`）+ `provenance: Provenance\|None`（`:434`） | A default `{}`；B payload 必填 | `payload` | — | — | B 把“分数/错误码/来源”提升为一级字段；A 放在 payload | `MAP`（B 一级字段写入 A payload 的 `migrated_v0` 子对象；保留 provenance 的 `experiment_id/source/created_at`） |
| 来源 | A `EvidenceReference`（`:744`，`source ∈ OBSERVED/INFERRED`，`event_id` 指针，`detail`） | B `Provenance`（`types.py:327`，`experiment_id` 必填，`source`，`created_at`） | — | 不同名 | A created_at；B created_at | — | A 的证据来源是枚举 + 事件指针；B 是实验/来源标签 | `MAP`（provenance.source→`EvidenceReference.detail` 文本；无法表达的字段→`MIGRATION_UNSUPPORTED_FIELD:provenance.*`） |
| 循环追踪 | A 用事件流本身（session/event）；无独立 loop 表 | B `TraceEvent`（`types.py:683`：event_id/loop_id/round/step/payload/timestamp），用于评测 loop 回放 | — | 不同 | — | — | B 的 TraceEvent 是 vertical/评测遥测，不是 canonical 教学事件 | `REJECT`（不进入 canonical 事件表）：`UNSUPPORTED_TRACE_EVENT_MIGRATION`；仅作为 sidecar 证据保留（如 trace 文件 sha256 写入 manifest） |
| 幂等 | DB `event_id` PK + `append_event` 返回 False（`learner/history.py:164`）；测试覆盖重复事件 | `_applied_event_ids` 内存 set（`learner_model.py:157-196` 内） | — | — | — | — | 两侧均“同 id 幂等”，但 A 跨进程持久、B 仅进程内 | `PASS`（概念一致）；跨线导入必须由 A 侧重新生成事件 id，禁止复用 B event_id 直接写入 |

### 4.4 AssessmentResult

| 字段 | A 线 `m1a.v0`（`contracts/types.py:683-701`） | B 线 `m1.offline.v0`（`m1_offline/types.py:601-611`） | 可空性 / 默认 | 序列化名 | 时间戳 | 版本 | 语义差异 | 迁移动作 |
|---|---|---|---|---|---|---|---|---|
| 主键 | `result_id`（`:692`） | `assessment_id`（`:602`） | required | 不同名 | A created_at；B 无时间戳 | — | 见 4.1 | `REJECT`（id 作用域修复前） |
| 题目/任务 | `item_id`（`:693`） | `task_id`（`:603`） | required | 不同名 | — | — | item vs task 粒度 | `MAP` |
| Learner | `learner_id`（`:694`） | `learner_id`（`:604`） | required | 同名 | — | — | 一致 | `PASS` |
| Scorer | `scorer_id`（`:698`，kw-only required） | `scorer_id`（`:605`） | required | 同名 | — | — | B 值为 `independent_cf_judge_v0`（`cf/teacher.py:69`）或 `InterviewRubric:…`（`interview/rubric.py:48`）；A 由 scorer 实现提供 | `MAP`（scorer_id 原样保留；跨线不得混合 scorer 语义，见 4.11） |
| 结果语义 | `status` ∈ `CORRECT/INCORRECT/PARTIAL/NEEDS_REVIEW/EVAL_ERROR`（`:695`）+ `score: float\|None`（`:696`）+ `max_score`（`:697`） | `passed: bool`（`:606`）+ `score: float`（`:607`，0..1）+ `dimensions: dict[str,float]`（`:608`）+ `failure_modes: list[str]`（`:609`）+ `hidden_cases_passed/total`（`:610/611`） | A status required, score nullable；B passed/score/dimensions required | 不同 | — | — | A 表达“独立评估状态”，明确区分 `NEEDS_REVIEW`/`EVAL_ERROR`；B 是 bool 通过 + 多维度分数（CF 的 dimensions = correctness/edge_case_accuracy/efficiency，`cf/teacher.py:700-703`） | `MAP`（passed=True→`CORRECT`+score；passed=False→`INCORRECT`；B 无 `NEEDS_REVIEW/EVAL_ERROR/PARTIAL` 语义 → 需 vertical 适配层显式产生新状态；`dimensions`/`hidden_cases_*` 不可映射 → 保留在 A `HistoryEvent.payload.migrated_v0`，拒绝码 `MIGRATION_UNSUPPORTED_FIELD:dimensions`） |
| 证据引用 | `evidence_refs: list[str]`（`:700`） | 无对应字段（`dimensions`/`failure_modes` 承担解释） | default [] | `evidence_refs` | — | — | A 指向事件/隐藏 spec 摘要（如 `spec-sha256:`），B 无 | `MAP`（B failure_modes→A payload；不得把 hidden expected 写入 evidence_refs） |
| 失败原因 | `failure_reason: str`（`:699`，默认空） | 无对应字段 | default "" | `failure_reason` | — | — | A 用码/计数；B 用 `failure_modes` + `dimensions` | `MAP`（failure_modes 序列化到 A `failure_reason` 有损 → 建议 payload sidecar + `MIGRATION_LOSSY_FIELD` 记录） |

### 4.5 Mastery / LearnerState

| 字段 | A 线 `m1a.v0` | B 线 `m1.offline.v0` | 可空性 / 默认 | 序列化名 | 时间戳 | 版本 | 语义差异 | 迁移动作 |
|---|---|---|---|---|---|---|---|---|
| 容器 | `LearnerSnapshot.masteries: dict[str,MasteryEstimate]`（`types.py:771`） | `LearnerState.mastery: dict[str,float]`（`m1_offline/types.py:456`） | A default {}；B required | 不同名 | A created/updated；B updated_at（空→now） | — | A 每节点带 confidence/evidence_count；B 每节点仅 float，evidence_count 是全局 | `REJECT`（默认禁止双写/自动迁移）：`MIGRATION_LEARNER_STATE_DENIED`。若维护者未来授权单向导入：`confidence`/`evidence_count` 无源→必须显式缺省并记 `lossy_unknown_fields`，不得伪造置信度 |
| 单节点掌握 | `MasteryEstimate{node_id,value:0..1,confidence:0..1,evidence_count:>=0,created_at,updated_at}`（`types.py:755-763`） | `LearnerState.mastery[node]`（无结构） | A required | `node_id/value/confidence/evidence_count` | A created+updated；B global updated_at | — | A 有不确定性建模（heuristic），B 无 | `REJECT`（同上） |
| 错误计数 | `LearnerSnapshot.error_counts: dict[str,int]`（`:775`，非负） | `LearnerState.error_counts: dict[str,int]`（`:457`） | default {} | 同名 | — | — | A 键约定为错误码（B 线文档记录“两种键约定”问题 Q2，`docs/m1/ADR-TEACHER-CORE.md` 未决问题 Q2）；B 同类 | `MAP`（概念可映射；但键语义未统一，需维护者裁定 Q2 后再迁移） |
| 已完成题目 | `LearnerSnapshot.completed_item_ids: list[str]`（`:774`） | **无对应字段** | default [] | `completed_item_ids` | — | — | B 无完成题记录 | `MAP`（从 A→B 导出时丢弃并记 `lossy_dropped`；B→A 需从 EvidenceEvent task_id 推导，禁止臆造） |
| 版本/修订 | `revision: int >=0`（`:778`） | **无对应字段** | default 0 | `revision` | A updated_at；B updated_at | — | A 支持乐观并发/缓存重建；B 无 | `MAP`（导入时由 A 重新生成 revision；不得复制） |
| 写入语义 | 只接受 OBSERVED 证据；`NEEDS_REVIEW`/`EVAL_ERROR` 完全不变（`learner/model.py:264-360` 文档 + 实现） | 同证据驱动，`error_codes` 失败证据只降不升（`learner_model.py:157-196`） | — | — | — | — | 两侧**思想一致**（可以合并为同一 canonical 规则），但数值公式不同 | `DESIGN_ONLY`：canonical 用 A 公式；B 公式仅 vertical 内部实验值，不写 canonical 状态 |

### 4.6 Reason / 解释

| 字段 | A 线 | B 线 | 可空性 / 默认 | 语义差异 | 迁移动作 |
|---|---|---|---|---|---|
| 结构化原因 | `Reason{code:str 非空, node_ids:list[str]=[], detail:str="", policy_version:str=""}`（`contracts/types.py:714-726`）；被 `TeachingAction.reason`（`:737`）、`PlanStep.rationale`（`:844`）、`DiagnosisResult.reason`（`:872`）使用 | **无结构化 Reason 类型**：`TeacherAction.rationale: str`（`types.py:549`）、`CurriculumPlan.rationale: list[str]`（`:525`）、`DiagnosticResult.explanation: str`（`:583`） | A 可在同结构里带 policy_version；B 仅为文本 | A 可机器审计（code+node_ids+policy）；B 文本不可稳定解析 | `MAP`（B 文本→A `Reason.detail`；`code` 需由 B-PR4 vertical 适配器显式给出（如 `HINT_LADDER_LEVEL_2`），无码场景→`REASON_CODE_UNSPECIFIED` 记录；**禁止**从自由文本猜 code） |
| 版本 | `policy_version` 字段（A，`:725`） | B `policy_version` 类属性（`teaching_policy.py:157/220/265`；planner `:45`） | A 可选默认 ""；B ClassVar | A 把版本放进记录（可回放审计）；B 在类上 | `MAP`（B policy_version→A Reason.policy_version 原样） |
| 诊断状态 | `DIAGNOSIS_STATUS_VALUES = READY / INSUFFICIENT_EVIDENCE`（`types.py:116`） | `DIAGNOSTIC_STATUS_VALUES = RESOLVED / UNKNOWN / NEEDS_REVIEW`（`types.py:63`） | — | **枚举语义不同**：A 是“能否给出下一诊断题”，B 是“错误分类完成度” | `MAP`（B `RESOLVED`→A `READY` 仅当 vertical 适配层能给出 canonical 目标节点；`UNKNOWN/NEEDS_REVIEW`→A `INSUFFICIENT_EVIDENCE`；反向不可无损） |

### 4.7 History / 事件表与持久化

| 维度 | A 线 | B 线 | 迁移动作 |
|---|---|---|---|
| 存储 | SQLite：`schema_meta`（`:90`）、`learners`（`:93`）、`snapshots`（`:98`）、`history_events`（`:104`，`UNIQUE(learner_id,seq)`）、`goals`（`:116`）、`sessions`（`:125`）；WAL/FK/`BEGIN IMMEDIATE` | 无 DB；`LearningMemory` 内存列表 + JSONL 导出/导入（`memory.py:97/109`）；`docs/m1/traces/*.jsonl` 是评测产物 | `PASS`（概念：append-only 事件 + 重建）；B 侧先作为 sidecar 证据，不迁入 canonical 表 |
| 事件表 schema | `event_id PK / learner_id / session_id / seq / event_type / payload_json / created_at`；`event_type` 受 12 值枚举校验；写入由 `LearningHistory`（`history.py:121`）统一生成 id/seq | `TraceEvent(event_id, loop_id, round, step, payload, timestamp)`；EvidenceEvent 单独 | `DESIGN_ONLY`：canonical 仅采用 A 表；B TraceEvent → sidecar `docs/m1/traces/` 保留 hash |
| 重建一致性 | `MasteryModel.rebuild_snapshot`（`learner/model.py:358`）+ `LearningHistory.verify_rebuild`（`history.py:357`），A 测试覆盖 pause/restart + 重建相等 | `LearnerModel.replay(events)`（`learner_model.py:198`）+ harness `replay_trace`（`evaluation/harness.py:1187`） | `PASS`（概念一致）；canonical 以 A 的 DB 重放为准 |
| 跨进程恢复 | 有（新 engine + 同一 SQLite，pause/resume 测试） | 无（内存模型/JSONL 需调用方自行重载） | canonical = A；B vertical 不拥有恢复能力 |

### 4.8 RuntimePort

| 维度 | A 线 | B 线 | 迁移动作 |
|---|---|---|---|
| 协议 | **无 RuntimePort**（`grep -RIn "RuntimePort" m1_teacher` = 0 hit） | `RuntimePort` Protocol：`send(RuntimeRequest) -> RuntimeResponse`（`runtime_port.py:52,61`）；mock 实现 `MockRuntimePort`（`:78`），所有响应 `simulated=True`（`:94` 附近） | `DESIGN_ONLY`：RuntimePort 留在 **B vertical 内部**，不进入 canonical TeacherCore；A canonical 教学决策不依赖模型文本 |
| 请求/响应 Record | 无 | `RuntimeRequest{request_id,session_id,messages,tools,metadata}`（`types.py:638-643`）；`RuntimeResponse{request_id,session_id,text,tool_events,usage,error,simulated}`（`:658-665`） | `REJECT`（不迁移到 canonical 事件协议）：`UNSUPPORTED_RUNTIME_RECORD`；仅 vertical 内部使用 |
| 零网络/Key | A 教师核心零网络（静态扫描无网络 import，见 CI 文档）；mock 由 E2E 测试脚本代替 | 明确 mock-only（`docs/m1/ADR-TEACHER-CORE.md` ADR-CORE-2/7）；无网络 import | 两侧一致：M1-B 继续无网络/无 Key |

### 4.9 DomainAdapter / Vertical 接口

| 维度 | A 线 | B 线 | 迁移动作 |
|---|---|---|---|
| 领域适配器 | `DomainAdapter` Protocol：`domain_id`、`domain_version`、`knowledge_nodes()`、`prerequisite_edges()`、`objectives()`、`assessment_items(node_id=None)`、`teaching_content(node_id, kind)`、`validate()`（`contracts/domain.py:24-57`）；`DomainRegistry`（`:61`，重复→ConflictError，缺失→NotFoundError） | **无 DomainAdapter/Registry**；CF 用 `CFTeacher`（`cf/teacher.py:133`），Interview 用 `InterviewCoach`（`interview/coach.py:173`），Freshness 用 `FreshnessManager`（`freshness.py:179`） | `DESIGN_ONLY`：canonical = A `DomainAdapter`；B 三个 vertical 通过新增 `DomainAdapterV1`/vertical 适配层接入（见 `M1_B_PORTS.md`）；B 现有类不改 |
| 知识来源 | 无 `KnowledgeSource` 记录；知识内容由 adapter 的 `teaching_content` 提供 | `KnowledgeSource{source_id,uri,publisher,published_at,observed_at,valid_until,confidence,claim_status}`（`types.py:357-365`）；`KnowledgeRevision`（`:382-390`）；`FreshnessManager.classify`（`freshness.py:186`）KEEP/UPDATE/RECHECK | `DESIGN_ONLY`：新增 `KnowledgeSourcePort` 适配 B 记录；Freshness 决策只影响 planner 的候选材料，不直接写学习者状态 |
| 评分边界 | `AssessmentScorer` Protocol（`assessment/scorer.py:191`）；`DeterministicScorer`（`:217`）是唯一 hidden-scoring reader；teacher 组件不读 hidden | `CFJudge`（`cf/judge.py:181`）独立判题，但 `JudgeResult.failures`（`:150-164`）包含 `expected=...`（runner 生成 `expected_repr`）；`CFTeacher` 同进程持有该结果 | `DESIGN_ONLY`：B-PR1 重做可信边界（TrustedJudgeSupervisor/UntrustedExecutionWorker，见 `M1_B_PORTS.md` §3）；在实现前不得对不可信 CODE 开放 |

### 4.10 Goal

| 字段 | A 线 `LearnerGoal`（`types.py:792-799`） | B 线 `LearningGoal`（`m1_offline/types.py:472-477`） | 语义差异 | 迁移动作 |
|---|---|---|---|---|
| 主键 | `goal_id` required | `goal_id` required | 一致 | `PASS` |
| 拥有者 | `learner_id` | `learner_id` | 一致 | `PASS` |
| 目标锚点 | `objective_id`（必填，指向 `LearningObjective`，`types.py:608`） | `target_skills: list[str]`（必填，技能 id 列表） | A 目标=领域 objective（含 success_criteria/target_node_ids）；B 目标=技能集合 + 预算/期限 | `MAP`（B→A 需 objective 映射表；A→B 可从 objective.target_node_ids 反推；无映射→`MIGRATION_UNSUPPORTED_GOAL_MAPPING`） |
| 计划参数 | `status ∈ ACTIVE/COMPLETED/PAUSED`（默认 ACTIVE） | `deadline_days: int\|None`、`weekly_minutes: int=180` | B 有时间预算；A 无 | `MAP`（B 预算字段 default/drop 记录 `lossy_dropped:deadline_days,weekly_minutes`；A 状态在 B 无对应→vertical 适配层映射） |
| 时间戳/版本 | `created_at` | 无 created_at、无 goal 版本 | — | `MAP` |

### 4.11 Tool / Scorer identity

| 维度 | A 线 | B 线 | 语义差异 | 迁移动作 |
|---|---|---|---|---|
| Scorer 协议/身份 | `AssessmentScorer` Protocol（`scorer.py:191`），属性 `scorer_id: str`（`:199`），方法 `score(item, learner_id, response, *, result_id)`（`:201`）；结果 `AssessmentResult.scorer_id`（`types.py:698`） | 无统一 Protocol；CF：`JUDGE_VERSION="cf.hidden.judge.v0"`（`judge.py:41`）、`SCORER_ID="independent_cf_judge_v0"`（`cf/teacher.py:69`）；Interview：`SCORER_ID="InterviewRubric:m1.offline.v0"`（`rubric.py:48`） | A 是单一 trusted scorer 接口（当前实现有 B-01 安全缺陷）；B 是 vertical 各自 scorer 字符串常量 | `DESIGN_ONLY`：`AssessmentPort`（`M1_B_PORTS.md` §3.2）统一入口；scorer_id 作为不可伪造身份由 trusted 层产生；B vertical 的 scorer_id 保留为 `vertical:<id>:<version>` 命名空间 |
| 隐藏材料位置 | 仅 `m1_teacher/assessment/scorer.py` 引用 hidden scoring 路径（`scorer.py:6,401`；静态扫描证据见 CI 文档） | CF hidden 用例在 fixtures `hidden/`（`cf/teacher.py:176-192` 解析 hidden_ref）；`JudgeResult.failures` 含 expected 摘要；Interview 隐藏答案在 fixtures/answers | A 的 teacher-visible 类型无 answer 字段（AST 扫描 + 正向泄漏测试）；B 的 judge 输出字段本身含 expected 摘要，且与 teacher 同进程 | `DESIGN_ONLY`：B-PR1 必须保证 expected 只在 trusted supervisor；worker 只接收输入；teacher-visible 输出仅错误码/聚合计数（见 `M1_B_PORTS.md` §3.2/§4） |

### 4.12 时间戳与版本策略

| 维度 | A 线 `m1a.v0` | B 线 `m1.offline.v0` | 差异/风险 | 迁移动作 |
|---|---|---|---|---|
| schema_version | `SCHEMA_VERSION="m1a.v0"`（`contracts/types.py:39`）；`Record.schema_version` ClassVar（`:493`） | `SCHEMA_VERSION="m1.offline.v0"`（`m1_offline/types.py:35`）；只读 property（`:271-275`） | 两个不同 schema 名 | `DESIGN_ONLY`：canonical 保持 `m1a.v0`；B 记录在 vertical 边界内保留自身 schema，跨边界由 adapter 转换 |
| 版本位置 | `to_dict()` 首键 `schema_version`；**from_dict 必须含且等于**（严格，`:514-553`） | `to_dict()` 首键；from_dict 中 `schema_version` **可缺省**（仅当存在且不等才报错，`types.py:288-296`） | A 更严格；B 容忍缺省 | canonical 采用 A 严格规则；B→A 迁移必须显式注入 `schema_version`，不得依赖缺省 |
| 时间戳格式 | UTC ISO-8601 秒级 `Z`；`+00:00` 归一为 `Z`；亚秒/非 UTC 拒绝（A 契约规则） | UTC ISO-8601 秒级；空串→`now_utc()`；显式值原样保留（`types.py:251-256`） | A 强制/归一；B 未对显式值的格式做同等严格校验（仅 `_as_str`） | canonical 采用 A 规则；导入 B 数据时按 A 规则重新校验/归一，失败→`MIGRATION_INVALID_TIMESTAMP` |
| `created_at` 覆盖 | 所有 16 条 Record 都有 `created_at`（部分有 `updated_at`） | 部分记录有 created_at（Provenance/LearnerProfile/EvidenceEvent/CurriculumPlan…），`SkillNode/KnowledgeRevision/LearningTask/TeacherAction/…` 无 created_at；空值构造时补 now | B 的“记录级创建时间”不完整 | `DESIGN_ONLY`：迁移时缺失 created_at 以 manifest 的 migration time 记录，不伪造原记录时间 |
| 领域/策略版本 | `domain_version` 在 `knowledge_graph.json` 顶层一次声明（adapter `:573`）；policy_version 在记录内（`Reason`）或 Policy dataclass | `policy_version` 为策略类 ClassVar（`teaching_policy.py:157/220/265`、`curriculum_planner.py:45`）；无 domain_version | 版本放置位置不同 | `DESIGN_ONLY`：canonical 要求 domain_version 进入 adapter 元数据、policy_version 进入每次决策的 `Reason`；vertical 策略版本作为 `policy_version` 字符串注入 Reason |

---

## 5. 差异矩阵

### 5.1 事件类型集合与状态机差异

| 维度 | A 线 | B 线 | 结论 |
|---|---|---|---|
| 事件类型集合 | `HISTORY_EVENT_TYPE_VALUES` 12 值（`types.py:101-118`）：`SESSION_STARTED, PLAN_CREATED, DIAGNOSIS_COMPLETED, ITEM_PRESENTED, RESPONSE_SUBMITTED, ASSESSED, MASTERY_UPDATED, ACTION_TAKEN, SESSION_PAUSED, SESSION_RESUMED, GOAL_COMPLETED, ERROR` | `EVIDENCE_KIND_VALUES` 6 值（`types.py:43-51`）：`ANSWER, CODE_SUBMISSION, EXPLANATION, INTERVIEW_RESPONSE, ASSESSMENT, HINT_REQUEST`；另有 `TraceEvent.step` 自由字符串（harness 用 `diagnose/gap/action/response/assess/...`） | A 是**教学会话事件协议**；B 是**评估证据类型**。不能一一对应；B 证据类型需映射到 A `ASSESSED`/`ACTION_TAKEN` 等事件并携带 payload 语义 |
| 状态机 | `SESSION_PHASE_VALUES` 8 值（`types.py:90-99`）：`DIAGNOSE→TEACH→PRACTICE→ASSESS→UPDATE→REVIEW`，`COMPLETE/PAUSED`；显式转换条件见 `session/engine.py:210` 文档 + 实现（`submit_response` `:488`、pause/resume `:450/469`、EVAL_ERROR 隔离 `:855`） | **无 session 状态机**；有 vertical 流程：CF `diagnose/next_action/assess`（`cf/teacher.py:213/551/660`）、Interview 5 阶段追问阶梯（`interview/coach.py:50-57`，`concept→hypothesis→complexity→experiment_design→online_triage`）、评测 closed loop（`evaluation/harness.py:1286`） | canonical = A 8 阶段状态机；Interview 5 阶段阶梯作为 **vertical 内部内容策略**，映射为 A `TEACH`/`REVIEW` 下的 action 内容，不新增 session phase（若未来要通用化，只能 additive 扩展 `SESSION_PHASE_VALUES` 并记录） |
| 状态转移持久化 | `sessions` 表 + `SessionState.phase/pending_item_id/turn_index`（`types.py:821-832`） | 无持久状态；loop round 由评测 harness 内存推进 | canonical = A；B vertical 不持有 session 状态 |
| 暂停/恢复 | `SESSION_PAUSED/SESSION_RESUMED` 事件 + `pause_session/resume_session`（`session/engine.py:450/469`） + 新 engine 同 DB 恢复（测试） | 无（需 vertical 自管） | canonical = A |

### 5.2 写入者差异（谁能写什么）

| 数据 | A 线写入者（SOURCE_INSPECTED） | B 线写入者（SOURCE_INSPECTED） | M1-B 合同（DESIGN_ONLY） |
|---|---|---|---|
| Learner Mastery / Snapshot | 仅 `MasteryModel` 计算 + `LearningHistory.apply_assessment` 持久化（`learner/history.py:210`）；`SqliteRepository.upsert_snapshot`（`learner/repository.py:493`）受 History 调用 | 仅 `LearnerModel.apply_evidence`（`learner_model.py:157`）写内存 `LearnerState`；无持久化 | **唯一写入者 = A `LearningHistory` + `MasteryModel`**；B `LearnerModel` 降级为 vertical 内只读/实验组件，禁止写 canonical 状态 |
| Event Log | `LearningHistory.append_event/apply_assessment`（`history.py:164/210`），id/seq 由历史层生成；DB `history_events` append-only | `LearningMemory.append(TraceEvent)`（`memory.py:77`）写循环遥测；`EvidenceEvent` 由 vertical 构造，无统一日志 | canonical 事件日志 = A `history_events`；B TraceEvent 只作 sidecar 证据（JSONL + hash），不进入 canonical 表 |
| Session 状态 | `TeachingSessionEngine`（`session/engine.py:210`）经 `sessions` 表 | 无 | canonical 唯一 = A `TeachingSessionEngine` |
| AssessmentResult | A `AssessmentScorer`（唯一 hidden-reader）→ `SessionEngine` → `LearningHistory`；**teacher 组件不写评分** | B `CFJudge`/`InterviewRubric` 产出 `AssessmentResult`（vertical 内），由 harness/teacher 使用 | canonical 评分入口 = `AssessmentPort`（trusted）；结果只能经 SessionEngine/History 进入 canonical 状态；vertical 不得直接写 |
| Goal | A `upsert_goal`（`repository.py:641`）经 SessionEngine `start_session` | B 无持久化 goal | canonical = A goals 表 |
| Knowledge/内容 | A `DomainAdapter` 只读 | B fixtures/vertical 只读（`FreshnessManager.apply` 只分组，不写课程，`freshness.py:348`） | 两者都只读；知识更新只能经 `KnowledgeSourcePort` 决策 + planner 显式采用（不直接改 canonical 状态） |
| 隐藏评分材料 | 仅 A `assessment/scorer.py`（静态扫描仅 2 处路径引用） | CF judge/interview rubric；`JudgeResult.failures` 含 expected 摘要且与 teacher 同进程 | 仅 trusted Judge/Scorer 边界；teacher/policy/UI/导出 JSON 不得含 expected（B-PR1 验收项 B1-02/B1-06） |

### 5.3 回放能力差异

| 能力 | A 线 | B 线 | M1-B 合同 |
|---|---|---|---|
| 事件排序键 | 每 learner `seq`（DB `UNIQUE(learner_id,seq)`） | append 顺序（内存/JSONL 行序），无 seq | canonical = A `seq` |
| 跨进程回放 | 有：`rebuild_snapshot` + `verify_rebuild` + pause/restart 测试 | 无 DB；`LearnerModel.replay(events)` 需调用方先提供事件列表；JSONL 加载器严格但只是文件 | canonical = A |
| 回放等价校验 | `verify_rebuild`（`history.py:357`）比较物化 snapshot 与重放结果 | harness `replay_trace`（`evaluation/harness.py:1187`）+ trace digest（`:1276`） | canonical 使用 A verify；B trace digest 可作为 vertical 证据哈希写入 manifest |
| 幂等 | event_id PK + `append_event` 返回 bool；重复 result_id 不二次更新 mastery | event_id 内存去重；重复观测收益递减（`REPEAT_CREDIT_FACTOR`） | canonical = A 持久幂等；B 的“重复递减”是 vertical 教学启发式，不替代幂等 |
| 审计字段 | `Reason.policy_version`、事件 payload、snapshot revision | `Provenance.experiment_id/source`、TraceEvent round/step | canonical 审计字段 = A；B provenance 作为 payload sidecar 保留 |

---

## 6. 唯一 Canonical 裁决

### 6.1 决策（建议，待维护者签收后冻结）

- **TeacherCore 业务状态与事件协议**：`m1_teacher`（`m1a.v0`）为唯一 canonical。
- **唯一 Learner Mastery 写入者**：`m1_teacher/learner`（`MasteryModel` 计算、`LearningHistory` 持久化、
  `SqliteRepository` 事务）。
- **唯一可审计 Replay**：`m1_teacher` 的 append-only `history_events` + `MasteryModel.rebuild_snapshot`
  + `LearningHistory.verify_rebuild`。
- **唯一 Session 状态机/恢复**：`m1_teacher/session/engine.py`。
- **B 线定位**：`m1_offline` 作为 **vertical（Domain Plugin / KnowledgeSource）**——CF Hint/Judge 逻辑、
  Interview 追问/Rubric、Freshness 分类与来源策略——通过 `M1_B_PORTS.md` 定义的端口接入 canonical core。
- **禁止**：双写两套 LearnerState；B vertical 直接写 Snapshot/Event Log/Session；把 B 的
  `LearnerModel`/`AssessmentResult.passed`/`TraceEvent` 作为 canonical 状态或事件协议。
- **不原地改语义**：A/B 既有包类型、字段、方法签名不删不改；所有集成通过新增模块/适配层/端口完成
  （additive only），并记录版本。

### 6.2 选择 A 为 canonical 的理由（`SOURCE_INSPECTED`）

1. **可恢复持久化**：SQLite 6 表 + schema version 校验 + WAL/FK/`BEGIN IMMEDIATE`；B 无 DB。
2. **唯一写入者与重建校验**：`LearningHistory` + `verify_rebuild` + pause/restart 测试；B 的 LearnerState
   仅内存。
3. **完整教学会话状态机**：8 phase + pause/resume + EVAL_ERROR 隔离 + 幂等提交；B 无 session state。
4. **结构化可审计解释**：`Reason{code,node_ids,detail,policy_version}`；B 为自由文本。
5. **领域抽象与知识图**：`DomainAdapter`/`DomainRegistry`/`KnowledgeGraph`（HARD/SOFT + 环检测 + 目标校验）；
   B 无 adapter/graph。
6. **合同冻结与测试规模**：A 已有 freeze ADR + 16 条严格 Record + 536 tests（历史）；B 365 tests 也保留，
   但 536/365 不可相加（§10）。
7. **B 的独有资产不需要替代 core**：Hint Ladder/Interview/Freshness/Runtime mock 是内容与策略资产，可作为
   vertical 保留，不必重写。

### 6.3 备选方案：以 `m1_offline` 为 canonical（不采纳）

**优点**

- B 已覆盖 3 个 vertical（CF/Interview/Freshness）+ 评测层 + `RuntimePort` + Hint Ladder 安全门；
- 评测协议/证据分级（`MEASURED/PLAN/NOT_RUN/UNVERIFIED`）成熟，historical 365 tests；
- 若只做“内容教学 demo”，B 的 lesson 循环已足够。

**缺点 / 不选理由**

| 缺口 | 证据 | 若选 B 必须新增 | 代价（DESIGN_ONLY 估算，非实测） |
|---|---|---|---|
| 无持久化 Learner/Session DB | `m1_offline` 无 sqlite3/INSERT（`grep` 无持久化用法；仅 JSONL） | SQLite/等效存储、schema 迁移、事务 | 需重建 A 的 6 表 + `BEGIN IMMEDIATE` + 崩溃恢复；无法直接复用 A 的事务代码（A/B 记录不同） |
| 无 Session 状态机/恢复 | 无 `SESSION_PHASE`/pause/resume | 8 phase 状态机 + pending item + resume + EVAL_ERROR 隔离 | 需重建 A `session/engine.py`（1611 行）语义 |
| 无结构化 Reason | `rationale: str` | 结构化 Reason 类型 + 全调用链改造 | 影响 policy/planner/diagnostic/session 全链，且会破坏 B 既有记录 schema（需 v2） |
| 无领域适配器/知识图 | 无 DomainAdapter/KnowledgeGraph/Objectives | adapter + DAG + 校验 | 需重建 A `knowledge/` + `domains/` 抽象 |
| 无 `seq`/session 绑定事件表 | `EvidenceEvent` 无 seq/session_id | 新事件表 + 迁移 | 旧 JSONL 无法直接成为 canonical 日志（顺序/归属缺失） |
| 判题器/Teacher 同信任域 | `JudgeResult.failures` 含 expected；`TeacherAction` 与 judge 同进程 | 可信 Judge 边界 | B-PR1 本就要做；若 B 为 canonical，仍需重做且 A 已有 scorer 隔离测试可复用 |
| 现有 536 tests 资产无法直接延续 | 两套测试互不 import | 重写或移植 A 行为测试 | 无法把 536 当 B 的验收（§10） |

**结论**：把 B 升为 canonical 需要重建“持久化 + 会话 + 结构化解释 + 领域图 + 事件排序”五项 core 能力，
且会与 B 既有记录 schema 冲突（需 v2）；成本显著高于“B 作为 vertical 接入 A”。因此**不采纳**。

### 6.4 其他备选（不采纳）

| 方案 | 不采纳理由 |
|---|---|
| 双 canonical（A 管持久/会话，B 管 mastery，两库合并） | 违反“禁止双写两套 LearnerState”；mastery 出现两个 source of truth，无法审计/回滚。 |
| 重写第三套统一 schema（v2 全新） | 破坏“既有包合约不得原地改语义”；两条线 901（不存在的数字）式的重写风险；B0 时间盒内不可独立验收。 |
| 仅文档映射、不设唯一 canonical | B-PR2/PR3 会继续各自实现事务/幂等，冲突无法收敛；不满足 B0-01 验收（唯一 canonical state/event protocol）。 |

### 6.5 迁移成本证据（源码核对 + DESIGN_ONLY 估算）

| 证据 | A 线 | B 线 |
|---|---|---|
| 源码行数 | 10,092（`m1_teacher/` 26 文件） | 8,415（`m1_offline/` 21 文件） |
| 持久化表 | 6 张（`schema_meta/learners/snapshots/history_events/goals/sessions`），schema version 1 | 0 张 |
| 会话状态机 | 8 phase + pause/resume + EVAL_ERROR 隔离；`session/engine.py` 1,611 行 | 0 |
| 结构化 Reason | `Reason` 记录 + 被 3 类记录引用 | 0（自由文本） |
| 知识图/领域抽象 | `KnowledgeGraph`（273 行）+ `DomainAdapter`/`Registry` | 0 |
| 事件排序 | `UNIQUE(learner_id,seq)` + replay 校验 | 无 seq |
| 测试（历史冻结） | 536 | 365 |

> 这些是**源码事实与历史冻结数字**；若选 B canonical 的“需新增工作量”是 §6.3 的 `DESIGN_ONLY` 估算，
> 未实现、未测量，不得作为承诺工时。

### 6.6 冻结条件（维护者签收项）

维护者签收本 ADR 后，以下合同冻结（变更须走 v1 additive 流程）：

1. canonical TeacherCore = A `m1_teacher`；B vertical 边界与四端口见 `M1_B_PORTS.md`；
2. 唯一 LearnerState 写入者/事件协议/Session 表/Replay = A；
3. 禁止双写、禁止自动迁移真实 learner DB、禁止 vertical 直接写 canonical 状态；
4. 历史 536/365 各自冻结、不相加；
5. B-PR1..B-PR5 按 §12 顺序执行，且每个 PR 独立 Reviewer。

---

## 7. v1 Compatibility Adapter 设计（`DESIGN_ONLY`，未实现）

### 7.1 原则

- **additive only**：新增模块（建议路径 `m1_teacher/ports/`、`m1_teacher/verticals/`）与新增记录/端口；
  **不修改** `m1a.v0`/`m1.offline.v0` 既有字段/枚举/签名；若需 TeacherCore 记录新增字段，只允许“带默认值
  的可选字段 + 版本记录”。
- **单向收敛**：B→A 数据（evidence/assessment/goal/内容）经 adapter 转为 A 记录；A→B 只允许只读导出
  用于评测/展示，不允许回写。
- **禁止双写**：adapter 只生产“待写入输入”；真正写 canonical 状态仍只由 A `LearningHistory`/SessionEngine
  在单事务内完成。
- **真实 learner DB 不自动迁移**：迁移工具只能由维护者离线、对副本运行；生产 DB 迁移需单独人工批准、
  备份、回滚演练。
- **可校验**：任何迁移输出必须伴随 canonical JSON sha256 + manifest checksum；无法表达字段必须显式拒绝
  并记录，不许静默丢弃。

### 7.2 映射函数（B → A，示意签名）

| 函数（新增模块） | 输入 | 输出 | 可表达性 | 拒绝码（fail-closed） |
|---|---|---|---|---|
| `map_skill_node(skill: SkillNode, *, mapping: SkillMapping) -> KnowledgeNode` | B `SkillNode`（`types.py:339`）+ 显式映射表 | A `KnowledgeNode`（`types.py:579`） | 部分（difficulty/assessment_mode/tags/content_ref 无源） | `MIGRATION_UNSUPPORTED_FIELD:difficulty`、`...:assessment_mode`、`...:tags`、`...:content_ref`、`MIGRATION_UNSUPPORTED_SKILL_MAPPING` |
| `map_prerequisites(skills: list[SkillNode]) -> list[PrerequisiteEdge]` | B 内嵌 `prerequisites[]` | A `PrerequisiteEdge`（`types.py:594`） | 有损（kind/weight 无源） | `MIGRATION_UNSUPPORTED_PREREQUISITE_KIND`（默认保守 HARD 或显式映射，二选一，需维护者裁定） |
| `map_evidence_event(event: EvidenceEvent, *, session_binding: SessionBinding, item_mapping) -> tuple[HistoryEvent, ...]` | B `EvidenceEvent`（`types.py:426`） | A `HistoryEvent`（`types.py:803`），由 canonical history 生成 id/seq | 部分（无 session/无 seq；kind 需映射） | `MIGRATION_MISSING_SESSION`、`MIGRATION_UNSUPPORTED_EVENT_KIND`、`MIGRATION_EVENT_ID_CONFLICT`、`MIGRATION_UNSUPPORTED_TASK_MAPPING` |
| `map_assessment_result(b: BAssessmentResult, *, item: AssessmentItem, learner_id, result_scope) -> AssessmentResult` | B `AssessmentResult`（`types.py:601`） | A `AssessmentResult`（`types.py:683`） | 部分（dimensions/hidden_cases_* 不可表达；passed→status 需 vertical 状态语义） | `MIGRATION_UNSUPPORTED_FIELD:dimensions`、`...:hidden_cases_passed/total`、`MIGRATION_UNMAPPED_STATUS` |
| `map_goal(goal: LearningGoal, *, objective_mapping) -> LearnerGoal` | B `LearningGoal`（`types.py:472`） | A `LearnerGoal`（`types.py:792`） | 部分（target_skills→objective_id 需映射；deadline/weekly 丢弃） | `MIGRATION_UNSUPPORTED_GOAL_MAPPING`、`MIGRATION_LOSSY_FIELD:deadline_days / weekly_minutes` |
| `map_mastery_state(state: LearnerState) -> None`（**默认禁用**） | B `LearnerState`（`types.py:454`） | 不产出 canonical 写入 | 不可表达（confidence/evidence_count/revision 无源） | `MIGRATION_LEARNER_STATE_DENIED`（默认永久拒绝；仅维护者批准的一次性 offline 导入例外，且必须带显式完善映射与 manifest） |
| `map_trace_events(events) -> sidecar`（**不迁移**） | B `TraceEvent`（`types.py:683`） | 仅 sidecar JSONL + sha256 | 不可表达（非 canonical 事件协议） | `UNSUPPORTED_TRACE_EVENT_MIGRATION` |
| `map_runtime_records(...)`（**不迁移**） | B `RuntimeRequest/Response`（`types.py:638/658`） | 不进入 canonical | 不迁移（vertical 内部） | `UNSUPPORTED_RUNTIME_RECORD` |

### 7.3 Canonical JSON 与迁移 checksum 格式

**Canonical JSON 规则（用于所有 sha256）**

```
canonical_json(record) =
  json.dumps(record.to_dict(), ensure_ascii=False, sort_keys=True,
             separators=(",", ":"), allow_nan=False)
sha256_hex(canonical_json)
```

- `record.to_dict()` 必须已含 `schema_version`（A 严格序列化）；
- 嵌套 Record/列表/字典递归规范化；`None`/`""` 保留（不省略键）；
- 迁移前后各算一次 sha256：`source_sha256`（B 记录 canonical JSON，若 B 记录可无损序列化）、
  `migrated_sha256`（A 记录 canonical JSON）。

**迁移 manifest 记录（新增 `m1b.migration.v0`；示意 JSON，未实现）**

```json
{
  "manifest_version": "m1b.migration.v0",
  "source_line": "m1.offline.v0",
  "target_line": "m1a.v0",
  "source_branch_sha": "290c5770461bb5af2a38c6e6d24ee76350bcb410",
  "target_branch_sha": "4706250643fd42d48d69ddad7159e011955fa9fd",
  "tool_version": "m1b.migrate.DESIGN_ONLY",
  "created_at": "<operator supplied UTC ISO-8601; 由维护者固定>",
  "counts": {"skills": 0, "edges": 0, "goals": 0, "assessment_results": 0, "evidence_events": 0},
  "unsupported": [
    {"record_type": "SkillNode", "record_id": "skill.x",
     "field": "difficulty", "code": "MIGRATION_UNSUPPORTED_FIELD"}
  ],
  "lossy": [
    {"record_type": "EvidenceEvent", "record_id": "evt.x",
     "field": "provenance.source", "action": "sidecar:payload.migrated_v0"}
  ],
  "checksums": {
    "source_sha256": "<sha256 of canonical source bundle>",
    "migrated_sha256": "<sha256 of canonical migrated bundle>",
    "manifest_checksum": "<sha256(canonical_json(manifest without manifest_checksum))>"
  }
}
```

- 任何 `unsupported` 非空 + 严格模式 → 迁移整体中止（不写 DB）；
- 宽松模式只允许 `lossy`（有显式 action），`unsupported` 永远不允许进入 canonical DB；
- manifest 只含合成 fixture/脱敏数据；不得包含真实个人数据、Key、hidden expected。

### 7.4 Rollback 条件（`DESIGN_ONLY`）

1. migrated DB 的 `schema_meta.version` 不等于 A 当前版本（1）→ 拒绝启动/回滚；
2. `verify_rebuild` 失败（事件重放 ≠ 物化 snapshot）→ 回滚；
3. manifest `migrated_sha256`/`manifest_checksum` 复算不一致 → 回滚；
4. 同一 migration 重复执行（manifest idempotency key 已存在）→ 拒绝（不允许部分重复写入）；
5. 发现任何 B 证据事件 id/session 绑定冲突 → 中止并保留原 DB；
6. 回滚方式：停止服务 → 还原迁移前备份 DB（含 manifest 记录）→ 复算备份 sha256 → 只读启动验证
   `verify_rebuild` 通过 → 记录回滚事件。**禁止**在原 DB 上做逆向字段修补。

### 7.5 部署期禁令（硬门）

- 真实 learner DB 自动迁移：**禁止**；
- A/B 双写：**禁止**（即使“先写两边再对账”也不允许）；
- 双跑（A/B 同时对同一真实学习者写状态）：**禁止**；只允许对合成 fixture/只读副本做双跑对比；
- 迁移工具接触网络/Provider/Key：**禁止**；只允许本地离线运行；
- 迁移输出进入 git：只允许脱敏 synthetic 证据 + checksum/manifest（`docs/`/`artifacts` 按项目规范）。

---

## 8. 写入者合同（Who writes what，冻结建议）

| 对象 | 唯一允许写入者 | 其他组件 |
|---|---|---|
| `LearnerSnapshot`/mastery/error_counts/revision | A `MasteryModel`（计算）+ `LearningHistory.apply_assessment`（持久化） | B vertical、diagnostic、planner、scorer、UI **只读**；禁止直接 `upsert_snapshot` |
| `HistoryEvent` 事件日志 | A `LearningHistory`（id/seq 生成）+ `SessionEngine`（会话事件） | 任何外部组件不得 append；导入必须经 migration adapter 且 manifest 审计 |
| `LearnerGoal` | A `SessionEngine.start_session` / repository（经 history/service） | vertical 不得写 goal |
| `SessionState`（phase/pending/turn） | A `TeachingSessionEngine` | vertical/UI 只读；UI 通过 engine API |
| `AssessmentResult` | trusted `AssessmentPort`（scorer）产出；由 A `SessionEngine` 消费并交给 `LearningHistory` | teacher/policy/vertical 不得伪造/修改 verdict；不得读 hidden expected |
| Knowledge/内容（nodes/edges/objectives/items/teaching content） | A `DomainAdapter`（只读加载） | `KnowledgeSourcePort` 只给“是否可进入课程”的决策；实际采用由 planner/engine 显式步骤完成 |
| Freshness 分类结果 | `KnowledgeSourcePort`（B Freshness 逻辑适配）输出决策记录 | 不得直接改写 canonical 课程/学习者状态 |
| Trace/评测遥测 | B vertical/评测层，写入 sidecar JSONL + sha256 | 不进入 canonical 事件表 |

> 当前 A 线已有实现与本合同一致（`SOURCE_INSPECTED`）；B 线尚不满足（无 canonical 写入链），因此
> B-PR4 接入前必须先完成 B-PR1/2/3。

---

## 9. 迁移与集成顺序（B-PR1..B-PR5 映射）

| PR | 与合同收敛的关系 | 使用本文/端口文档 |
|---|---|---|
| B-PR1 `trusted-judge-worker` | 重做 `AssessmentPort` 信任边界；worker 不含 expected；可信端比较 expected；hidden 泄漏扫描 | `M1_B_PORTS.md` §3.2/§4；本 ADR §4.11/§5.2 |
| B-PR2 `session-transaction-and-recovery` | 落实 A canonical 的原子提交/恢复合同（`commit_teaching_turn` 设计）；只能有一个写入者 | 本 ADR §5.2/§8；`M1_B_PORTS.md` §5 |
| B-PR3 `scoped-idempotency` | 落实 composite idempotency key + request digest；修复 B-03 全局 result_id 问题 | 本 ADR §4.1/§11-C3；`M1_B_PORTS.md` §3.2 |
| B-PR4 `cf-interview-domain-ports` | 实现 `DomainAdapterV1`/`KnowledgeSourcePort`/`TeacherPolicyPort`，接入 B vertical（CF Hint/Interview/Freshness） | `M1_B_PORTS.md` §3/§4/§5 |
| B-PR5 `unified-e2e-and-blind-evaluation` | 统一事件表/Replay 的两域 E2E + 独立评测 + 新报告（新 suite 单独计数） | 本 ADR §10；`M1_B_CI_AND_DEMO.md` |

---

## 10. 历史测试数字与验收纪律

- A 线历史冻结：`m1a` 分支 `536 passed`（`tests/m1_teacher`；PR1 268 + PR2 100 + PR3 50 + PR4 75 + PR5 43；
  来源 `docs/M1_IMPLEMENTATION_REPORT.md`、`docs/M1_INDEPENDENT_REVIEW.md`）。
- B 线历史冻结：`m1_offline` 分支 `365 passed`（`tests/m1_offline`；来源 `docs/m1/REVIEW_M1_OFFLINE.md:103/136/323`）。
- **536 + 365 = 901 不是任何真实套件**：两条线基线不同、验收范围不同、互不 import；新集成必须跑
  **新的独立 suite**（B-PR5 生成新的 evaluation report），并在报告中分别标注历史参考与新测量。
- 证据分级：历史 PASS 只是各自范围的冻结结论；B0 本文为 `SOURCE_INSPECTED` + `DESIGN_ONLY`；
  B-PR1..5 的每个 PR 需要独立 Reviewer、独立证据（`MOCK/DETERMINISTIC/HUMAN_REVIEWED/NOT_VERIFIED`），
  不接受“合并两个旧包 = 已集成”。

---

## 11. 合同冲突 Top 清单（按严重度/阻塞性）

| # | 冲突 | 证据（SOURCE_INSPECTED） | 影响 | 处置 |
|---|---|---|---|---|
| C1 | **两套 LearnerState/mastery 模型 + 无统一写入者** | A：`LearnerSnapshot`（`types.py:767`）/`MasteryModel`（`learner/model.py:264`）；B：`LearnerState`（`types.py:454`）/`LearnerModel`（`learner_model.py:56`）；B 无持久化 | 若双写会产生两个 source of truth，无法审计/恢复 | canonical = A；B model 降级为 vertical 实验组件；禁止双写（§8） |
| C2 | **B 无事件 seq/session/持久化日志** | B `EvidenceEvent` 无 `seq`/`session_id`（`types.py:426-435`）；无 sqlite；A `history_events` 有 `UNIQUE(learner_id,seq)` + sessions | 无法把 B 事件直接作为 canonical 事件流；重放/恢复不可用 | B→A 事件迁移需重构 id/seq/session（§7.2）；B TraceEvent 仅 sidecar |
| C3 | **幂等键作用域不安全** | A：`_find_existing_result(result_id)` 全局查重（`session/engine.py:833`，COMMON B-03）；B：无学习写入链但 assessment_id 生成规则不同 | 跨 learner/session 可读到别人的评分结果；同 key 不同 payload 语义未定 | B-PR3 统一 composite key `(learner_id, session_id, item_id, turn_id, result_id)` + request digest；未修复前禁止跨线导入 result |
| C4 | **Judge/Scorer 信任边界不成立，且 B judge 输出含 hidden expected** | A：`scorer.py:534-620` 把含 expected 的 tests 传给导入用户代码的进程，trusted 父进程读取结果文件 `passed`（COMMON B-01）；B：`judge.py:56-150` runner 生成 `expected_repr`，`JudgeResult.failures`（`:150-164`）含 expected，`CFTeacher` 同进程持有（`cf/teacher.py:283` 等） | 不可信 CODE 可伪造 PASS/读取 expected；B 的 teacher 可见诊断路径可间接暴露 | B-PR1：TrustedJudgeSupervisor/UntrustedExecutionWorker；在完成前对不可信 CODE 默认 `UNTRUSTED_CODE_EXECUTION_BLOCKED`；teacher-visible JSON 仅聚合错误码 |
| C5 | **Session 提交非原子** | A `submit_response` 顺序写 `RESPONSE_SUBMITTED`→ASSESSED/MASTERY_UPDATED→snapshot→save_session（`session/engine.py:488-560`），各步可独立提交（COMMON B-02） | 崩溃可出现已评分但 pending 未清除，重试因 result 已存在而跳过修复 | B-PR2：单事务 `commit_teaching_turn` 或持久 recovery intent；真实 SIGKILL 故障矩阵 |
| C6 | **B 无结构化 Reason/policy_version-in-record** | A `Reason`（`types.py:714`）；B `rationale:str`/`explanation:str`（`types.py:549/583`） | 决策不可机器审计、policy 版本不可追踪 | canonical 用 A `Reason`；B vertical 适配器显式产生 code/policy_version（禁止从文本猜） |
| C7 | **领域模型重复** | A `KnowledgeNode`+`PrerequisiteEdge`+`LearningObjective`+`DomainAdapter`（`types.py:579/594/608`，`domain.py:24`，`graph.py:40`）；B `SkillNode`+内嵌 prerequisites，无 objective/adapter/graph | 两套知识模型无法同时作为课程权威 | canonical = A；B SkillNode 仅经 mapping adapter 进入（§7.2）或作为 vertical 内部内容不进入 core |
| C8 | **Schema/时间戳严格度不一致** | A `SCHEMA_VERSION` 必填严格（`types.py:514-553`）、时间戳秒级 Z 归一；B from_dict 容忍缺省 schema_version（`types.py:288-296`）、显式时间戳只查 str、部分记录无时间戳 | 同一 JSON 在两侧接受度不同，迁移会静默差异 | canonical 采用 A 严格规则；迁移前显式注入/校验 + `MIGRATION_INVALID_TIMESTAMP` |
| C9 | **RuntimePort 只在 B；A 无模型运行时边界** | A `grep RuntimePort` = 0；B `runtime_port.py:52` | 若把 B vertical 直接搬入 A，会引入 A 没有的 runtime 依赖 | RuntimePort 保留在 B vertical 内部（mock-only）；canonical TeacherCore 不依赖模型文本（A 现状） |
| C10 | **Replay 语义不同** | A：`seq`+DB+`verify_rebuild`（`history.py:357`）；B：memory JSONL+trace digest（`evaluation/harness.py:1187/1276`） | 两套“可回放”不可互换 | canonical = A；B trace digest 仅 vertical 证据哈希 |

---

## 12. 未决问题（Open Questions，需维护者/LeadB 决策）

| # | 问题 | 影响 | 建议决策者 |
|---|---|---|---|
| Q1 | 是否签收本 ADR（A canonical + B vertical）？ | 未签收则 B-PR1..5 无法冻结接口 | 维护者 + LeadB |
| Q2 | B→A 的 `SkillNode.difficulty/assessment_mode` 无源：拒绝迁移，还是允许维护者提供显式映射表？ | 决定 B 内容能否进入 canonical 课程 | 维护者 + 教学负责人 |
| Q3 | B 内嵌 `SkillNode.prerequisites` 迁为 A edge 时，默认 `HARD` 还是显式要求 kind 映射？ | 影响先修补救策略正确性 | 教学负责人 |
| Q4 | B 的 `AssessmentResult.passed` 如何映射 A 的五态（尤其 `NEEDS_REVIEW/EVAL_ERROR/PARTIAL`）？ | 影响掌握度更新正确性 | LeadB（B-PR4） |
| Q5 | `error_counts` 键约定（error code vs skill id）是否统一？（B ADR Q2） | 跨线迁移语义 | B-Lead/维护者 |
| Q6 | B vertical 的 `RuntimePort` 是否允许在 B-PR4 后被 external caller 使用？（canonical 仍不调用模型） | 影响 B4 E2E 中“模型文本”的角色 | LeadB + 维护者 |
| Q7 | 历史的 536/365 是否需要在 README/STATUS 中同时展示为“各自独立”？ | 防止再次“901”误读 | LeadB |
| Q8 | 迁移工具是否允许接触真实 learner DB（仅维护者离线、备份后）？ | 影响 B-PR4/5 数据导入范围 | 维护者（人类批准） |

---

## 13. 参考（SOURCE_INSPECTED）

**A 线**
`m1_teacher/contracts/types.py`、`contracts/domain.py`、`contracts/repository.py`、
`knowledge/graph.py`、`learner/{model,history,repository}.py`、`diagnostic/engine.py`、
`planner/planner.py`、`assessment/scorer.py`、`session/engine.py`、
`domains/cf_binary_search.py`、`extensions/interfaces.py`、`demo.py`、`cli.py`；
`docs/M1_ARCHITECTURE.md`、`docs/M1_ADR_001_DOMAIN_CONTRACTS.md`、`docs/M1_IMPLEMENTATION_REPORT.md`、
`docs/M1_EVALUATION_REPORT.md`、`docs/M1_INDEPENDENT_REVIEW.md`、`docs/M1_NEXT_PHASE_PLAN.md`。

**B 线**
`m1_offline/types.py`、`memory.py`、`learner_model.py`、`runtime_port.py`、`teaching_policy.py`、
`curriculum_planner.py`、`diagnostics.py`、`cf/judge.py`、`cf/teacher.py`、`interview/coach.py`、
`interview/rubric.py`、`freshness.py`、`evaluation/{harness,compare,contamination,report}.py`、`demo.py`；
`docs/m1/TEACHER_CORE_ARCHITECTURE.md`、`docs/m1/ADR-TEACHER-CORE.md`、`docs/m1/CF_TEACHER_SPEC.md`、
`docs/m1/INTERVIEW_COACH_SPEC.md`、`docs/m1/FRESHNESS_AND_SOURCE_POLICY.md`、
`docs/m1/EVALUATION_PROTOCOL.md`、`docs/m1/REVIEW_M1_OFFLINE.md`。

**交接与联合审阅**
`/root/leadb_zip/START_HERE.md`、`02_LEADB_AGENT_HANDOFF.md`、`AUDIT_REQUESTS.md`、
`COMMON_REVIEW_AND_ROADMAP.md`、`TEST_EVIDENCE_MATRIX.csv`（B0-01 初始 `NOT_RUN`）。

---

## 14. 变更记录

| 日期（UTC） | 版本 | 变更 |
|---|---|---|
| 2026-11-20 | B-PR0 初稿 | DRAFT/DESIGN_ONLY：逐字段对照、差异矩阵、canonical 裁决（A）、备选分析、v1 adapter/checksum/rollback、写入者合同、历史数字纪律、冲突 Top 清单、未决问题 |
