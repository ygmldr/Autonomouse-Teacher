# M1-B PR4 — Interview / Freshness → Canonical Teacher Core 移植映射设计

- **状态**：`DESIGN_ONLY`。本文档只做设计，**不包含任何实现、测试执行、fixture 修改或迁移脚本**。
- **PR**：B-PR4 `cf-interview-domain-ports`（Implementer-Teaching/Domain + Reviewer-Policy；LeadB 协调/审计）。
- **工作区**：`/root/m1b/ivmap`，分支 `b-next/pr4-interview-mapping`，基线 `work/m1a-mvp = 4706250`（`docs(m1a): independent M1-A offline MVP review — PASS_FOR_M1A_OFFLINE_MVP`）；共同基线 `main = 3e7afee`。
- **对照的 B 线冻结交付**：`work/m1-offline-design = 290c577`（`m1_offline`，独立 Review 为 `PASS_FOR_M1_OFFLINE_DESIGN_AND_EVALUATION_SCOPE`）。
- **目标**：在 **B0 合同裁决选择的 canonical 候选 `m1_teacher`（`m1a.v0`）** 上，为 Interview Coach / Freshness 设计“Domain Plugin + 端口”的迁移映射，使 B 线能力**只通过 teacher-visible 数据接入唯一 Core**，不双写 `LearnerState`、不把隐藏评分标签暴露给 Teacher、不让冲突/过期知识静默进入课程。
- **交付边界**：唯一新增文件即本文档；不修改 `m1_teacher/**`、`m1_offline/**`、`fixtures/**`、`tests/**`、M0 保护路径；不提交任何实现。实现落地在 B-PR4 后续 PR，且需先经 B0 ADR 冻结合同。

## 0. 证据分级与引用规则

本文引用两类材料，严格区分（遵循 `COMMON_REVIEW_AND_ROADMAP.md` §0 与 `TEST_EVIDENCE_MATRIX.csv`）：

| 标记 | 含义 | 本文用法 |
|---|---|---|
| `SOURCE_INSPECTED` | 本次直接读取了该仓库文件/代码 | 所有类型、接口、夹具字段、行号级引用 |
| `OWNER_REPORTED` | 源报告/文档自称的测试/运行结果，本次**未复跑** | 仅用于“历史测试数字”背景，不当作本 PR 的验收证据 |
| `DESIGN_ONLY` | 本文档提出的方案/契约 | 所有端口、映射表、测试矩阵条目 |
| `NOT_RUN` | 需要后续实现/执行，本轮没有运行 | §8 测试矩阵全部初始状态 |

**本 PR 不产生任何 PASS 结论。** 引用 `OWNER_REPORTED` 的既有测试数字（M1-A 536、M1-Offline 365，见 §0.1）只用于说明历史冻结状态，不代表合并后已重新验收，更不得相加声称“统一 901 tests”。

### 0.1 基线事实（SOURCE_INSPECTED）

| 项 | 值 | 来源 |
|---|---|---|
| A canonical 候选 | `work/m1a-mvp = 4706250`，`m1_teacher`，合同 `m1a.v0` | `docs/M1_ARCHITECTURE.md`、`m1_teacher/contracts/types.py` |
| B vertical 源 | `work/m1-offline-design = 290c577`，`m1_offline`，合同 `m1.offline.v0` | `/root/at-m1-offline/m1_offline/**` |
| A 历史测试数字 | 536 tests（`OWNER_REPORTED`，PR1 268 + PR2 100 + PR3 50 + PR4 75 + PR5 43） | `docs/M1_ARCHITECTURE.md` §9 |
| B 历史测试数字 | 365 tests（`OWNER_REPORTED`） | `COMMON_REVIEW_AND_ROADMAP.md` §1 |
| B4 初始状态 | `B4-01/02/03 = NOT_RUN` | `TEST_EVIDENCE_MATRIX.csv` |
| 两个实现关系 | 两套合同**尚未统一**，`m1_offline` 不是 `m1a` 的子模块 | `COMMON_REVIEW_AND_ROADMAP.md` B-04 |

### 0.2 本次读过的关键源码（SOURCE_INSPECTED）

- A 线：`m1_teacher/contracts/types.py`（947 行，全部记录/枚举/D12 冻结规则）、`contracts/domain.py`、`contracts/repository.py`、`session/engine.py`（状态机、`SessionPolicy`、hint 升级、`_hint_selection`、事件写入）、`learner/model.py`（唯一 mastery 写入启发式）、`learner/history.py`（`ASSESSED`/`MASTERY_UPDATED` 事件 payload、幂等键、rebuild）、`assessment/scorer.py`（独立评分器边界）、`domains/cf_binary_search.py`（`teaching_content` kind 白名单）、`extensions/interfaces.py`（`InterviewCoachPort`/`KnowledgeFreshnessPort` 现有 stub）、`docs/M1_ARCHITECTURE.md`、`docs/M1_NEXT_PHASE_PLAN.md`、`docs/M1_ADR_001_DOMAIN_CONTRACTS.md`。
- B 线：`m1_offline/types.py`、`interview/{coach,rubric}.py`、`freshness.py`、`teaching_policy.py`、`curriculum_planner.py`、`cf/teacher.py`、`evaluation/harness.py`、`fixtures/m1/interview/**`、`fixtures/m1/cf/**`、`docs/m1/INTERVIEW_COACH_SPEC.md`、`docs/m1/FRESHNESS_AND_SOURCE_POLICY.md`。
- 交接/矩阵：`/root/leadb_zip/{START_HERE,02_LEADB_AGENT_HANDOFF,AUDIT_REQUESTS,COMMON_REVIEW_AND_ROADMAP,TEST_EVIDENCE_MATRIX}.*`。

---

## 1. 设计不变量（任何映射不得违反）

1. **唯一 canonical Core**：B0 建议（尚未由维护者签收）以 `m1_teacher` 的 SQLite + Session Engine 为唯一业务状态与事件协议；`m1_offline` 只作为 **vertical 源**（CF Hint / Interview / Freshness / Evaluation）。PR4 的所有设计都以“**A Core 为唯一写者**”为前提；若 B0 最终另选 canonical，本文的端口边界仍成立，但落点需重估（见 §1.4）。
2. **唯一 Learner 写入者**：`LearnerSnapshot`/`MasteryEstimate` 只能由 `learner/model.py` 的 `MasteryModel` 通过 **OBSERVED** 证据写入（`apply_result`/`rebuild_snapshot` + `LearningHistory.apply_assessment`）。任何 Domain/Port/Coach 都**不得**直接写 snapshot、不得把 LLM 自述当掌握度。
3. **Teacher / Scorer 隔离**（A-ADR D3）：teacher-visible 记录不得含 `answer/expected/correct/solution` 字段；Interview 的 `rubric_points`、隐藏答案、4 维期望分数属于 **scorer-only**；注入文档属于不可信数据，**不得**进入 teacher-visible 记录。
4. **`m1a.v0` 冻结**（A-ADR D2/D12）：只允许**加法式**演进；本 PR 提出的扩展按“新模块/新 optional 字段带默认值/新枚举值/新端口”记录进 ADR，绝不原地改语义。B 线合同 `m1.offline.v0` 中的数据结构**不做原地修改**，只经适配器投影。
5. **无 Key / 无网络 / 合成数据**：不得访问真实招聘网站、真实个人简历、真实 Provider/LiveGate；Freshness 只用**静态、带时间戳的 synthetic knowledge**证明门禁，不声称“本周热点真实更新”。
6. **失败关闭（fail closed）**：任何无法无损表达、无法可靠校验、或可能把隐藏/冲突数据带进教学路径的映射，必须**拒绝并给出稳定拒绝码**（§3.9），不得静默降级、不得“先写进去再说”。
7. **单一事件表 + 可审计 Replay**：教学状态与理由必须能仅凭统一事件日志重建；禁止双事件体系。
8. **B4 前置依赖**：B1（可信判题）、B2（事务恢复）、B3（范围内幂等）未完成前，PR4 不面向不可信 CODE 开放；本文不重复 B1–B3 的实现设计，只在端口边界引用其约束。

### 1.2 术语

| 术语 | 含义 |
|---|---|
| canonical Core | `m1_teacher`：`SessionState` + `HistoryEvent` + `LearnerSnapshot` + `CurriculumPlan` + 唯一写者 |
| Domain Plugin | 实现 `DomainAdapter` 的只读域：提供 knowledge nodes/edges/objectives/teacher-visible items/teaching content |
| Port | 面向 Core 的窄接口：`AssessmentPort`（可信评分）、`KnowledgeSourcePort`（版本化知识+时效）、`TeacherPolicyPort`（教学策略/提示梯子） |
| Teacher-visible | 可进入 `m1_teacher/contracts/types.py` 记录、事件 payload、学生可见 UI/导出数据的字段 |
| Scorer-only | 只允许独立评分器进程/模块访问的隐藏材料（rubric points、隐藏题集、expected） |
| RECHECK | Freshness 的三态之一：需要人工复核，**禁止静默进入课程** |

### 1.3 B 线源码的定位（不复制第二个 Core）

- `m1_offline/interview/coach.py` 的模板化追问与 DATA_ONLY 注入防御逻辑 → 迁移为 **InterviewDomainPort 的 teaching content + 会话策略**（policy 侧），不保留自己的 `TeacherAction` 生命周期与“自评”。
- `m1_offline/interview/rubric.py` 的四维评分逻辑 → **迁移进 AssessmentPort 的可信 scorer 模块**（scorer-only，确定性、无 runtime），teacher 只拿到 `AssessmentResult`。
- `m1_offline/freshness.py` 的 `classify/apply` → 迁移进 **KnowledgeSourcePort**（KEEP/UPDATE/RECHECK 与来源分层门禁），教学侧只拿“是否可进入计划”的结论与审计引用。
- `m1_offline/types.py` 的 `LearnerState/LearnerModel/EvidenceEvent` → **不迁移为 canonical**；B 线仅作为 fixture/证据生产与历史对照。迁移期后 B 的 mastery 写入路径退役（见 §6.4）。

### 1.4 对 B0 裁决的依赖

本文所有落点假设 **canonical = `m1_teacher`**。这是 B0 的“建议候选”，最终由维护者签收 B0 ADR 后冻结；若改选 `m1_offline` 为 Core，则 §3 的映射方向反转、§4 的端口实现落在 B 线、§5 的事件表重建，需要单独的迁移证据与回滚设计。**本文不预设 B0 已通过**；对应条目在 PR4 实施前必须由 LeadB 确认 B0 裁决记录。

---

## 2. 目标 / 非目标

**目标**

1. 给出 Interview（问题/答案/四维 rubric/五阶段追问）、JD v1/v2、KnowledgeSource（`published_at`/`observed_at`/`valid_until`/`claim_status`）、Freshness（KEEP/UPDATE/RECHECK）到 `m1a.v0` 记录的**逐字段映射**与拒绝码。
2. 定义四个移植端口：`DomainAdapter`（Interview 域）、`AssessmentPort`（可信评分/隐藏答案归属）、`KnowledgeSourcePort`（版本化知识 + 三态时效）、`TeacherPolicyPort`（Hint Ladder 证据门、FULL_SOLUTION 默认禁止）。
3. 设计 Interview 教学闭环（多轮五阶段、LearnerState 影响、`ASK_CLARIFICATION`、JD 变更、冲突/过期不静默）；CF Hint Ladder 迁移；统一 Session/事件表/Replay。
4. 给出 PR4 测试矩阵草案（B4-01/02/03 + 回归 + 拒绝/负例），初始状态全部 `NOT_RUN`。
5. 明确不做项与未决问题，供 LeadB/Reviewer 决策。

**非目标（本 PR 不做）**

- 不实现端口/适配器/迁移脚本，不改任何代码与 fixture；不运行测试；不产出 PASS。
- 不修改 `m1a.v0` 冻结语义（扩展需 B0 ADR + 维护者签收；本文给出建议与备选）。
- 不解决 B1/B2/B3（Judge OS 隔离、事务恢复、scoped idempotency）；不重复其威胁模型。
- 不接入真实网络/招聘网站/简历/Provider/LiveGate；不做真实学习效果声明。

---

## 3. 数据映射表（m1.offline.v0 → m1a.v0）

### 3.1 映射状态图例与通用规则

| 状态 | 含义 | 处理 |
|---|---|---|
| `LOSSLESS` | 字段语义与类型均可直接投影 | 直接映射；进入 checksum |
| `LOSSLESS-ENCODED` | 需确定性编码/命名空间/格式规范化，但可逆 | 编码函数固定、带 checksum；可回读校验 |
| `SCORER-ONLY` | 数据属于隐藏评分材料或独立评分器，**不得**进入 teacher-visible 记录 | 迁入 AssessmentPort 私有存储；teacher 侧只见 opaque ref |
| `NEEDS-EXT` | `m1a.v0` 无可表达字段/枚举，需**加法式**扩展（新 optional 字段/新枚举值/新 extension 类型/新端口方法） | 在 B0 ADR 记录扩展，落地前该字段走拒绝或“显式默认 + 标记 uncalibrated”，不得静默丢失 |
| `REJECT` | 无法安全表达或语义冲突 | 失败关闭，抛稳定拒绝码（§3.9） |

通用规则：

1. **ID 命名空间**：所有跨线 ID 进入 Core 前加确定性前缀，防止与 CF/A 侧 ID 冲突：
   - `interview.node.<track>`、`interview.item.<question_id>`、`interview.action.<sha256:16>`、`interview.assessment.<result_id>`；
   - `jd:<jd_id>`、`knowledge:<source_id>`、`interview.answer.<answer_id>`（scorer-only）；
   - 事件 ID：`evt.<domain>.<type>.<sha256:16>`；同一本地 ID 对应不同内容哈希 → `MAP-E15`。
2. **时间戳**（A-ADR D11）：A 只接受 UTC ISO-8601 秒级 `...Z`；B 夹具用 `+00:00`。`+00:00` → `Z` 属**规范化无损**（`LOSSLESS-ENCODED`）；亚秒精度、非 UTC offset、不可解析 → `MAP-E04`。`published_at`/`observed_at`/`valid_until` 语义必须**分开保留**（§3.6），不得全部折叠成 `created_at`。
3. **checksum / 迁移清单**：每条源记录生成 canonical JSON（`sort_keys=True, ensure_ascii=False, separators=(",",":")`）的 sha256；`MigrationManifest`（extension-only，不进 teacher-visible 记录）记录 `source_file_sha256 / adapter_version / imported_count / rejected_count / mapping_checksum`。任何 roundtrip 后 checksum 不一致 → `MAP-E21`，整批回滚（不原地改 v0 表）。
4. **未知键**：B fixture 的未知键按 A-ADR D6 风格**失败关闭**（`MAP-E02`/`MAP-E03`），不做“宽容忽略”。
5. **禁止双写**：任何映射只允许写入 canonical Core 的表；B 线数据库/文件不是运行时写入目标。迁移是**一次性、离线、只读源**的导入；部署前禁止自动迁移真实 learner db（`02_LEADB_AGENT_HANDOFF.md` B0.3）。

### 3.2 Interview 问题 → `KnowledgeNode` + `AssessmentItem`

B 源 fixture 字段（`fixtures/m1/interview/questions/<id>.json`，SOURCE_INSPECTED）：`schema_version, question_id, track, topic, question, rubric_points{factual_correctness, explanation_clarity, engineering_feasibility, evidence_sufficiency}, follow_up_ladder[5], requires_project_facts, synthetic, license`。

| B 字段 | 目标（m1a.v0） | 状态 | 规则 / 备注 |
|---|---|---|---|
| `question_id` | `AssessmentItem.item_id`、`KnowledgeNode.node_id` 的输入 | `LOSSLESS-ENCODED` | `interview.item.<question_id>`；node 按 `interview.node.<track>` 聚合 |
| `track` | `KnowledgeNode.domain_id` + `node_id` + `tags` | `LOSSLESS-ENCODED` | 一个 track 一个 `KnowledgeNode`（4 track）；`domain_id="interview_coach"`；`tags=["track:<track>"]` |
| `topic` | `KnowledgeNode.title` / `tags` | `LOSSLESS` | 可作为 title 或 tag；不得生成额外 node（避免知识图谱膨胀：题目→item，topic 只是节点元数据） |
| `question` | `AssessmentItem.prompt` | `LOSSLESS` | teacher-visible 题干 |
| `rubric_points`（4 维） | **不属于** `AssessmentItem` | `SCORER-ONLY` | 迁入 `InterviewScoringSpec`（§3.3）；`AssessmentItem.scoring_spec_ref` 只放 opaque 引用（如 `scorer://interview/<question_id>/rubric@v1`）。若试图写入 teacher-visible 字段 → `MAP-E05` |
| `follow_up_ladder[5]` | 教师可见追问内容 | `NEEDS-EXT` | `m1a.v0` `DomainAdapter.teaching_content` 只允许 `EXPLAIN/HINT_L1/HINT_L2/HINT_L3/REVIEW/PRACTICE`（A-ADR D6）；五阶段追问不是 hint rung。建议扩展 `InterviewDomainPort.follow_up_ladder(item_id) -> list[TeachingContent]`（新端口方法，additive），或新增 `teaching_content` kind `PROBE_CONCEPT/PROBE_HYPOTHESIS/...`（**建议前者**，避免污染通用 content kind 枚举）。未扩展前：导入拒绝 `MAP-E03`；不得把 ladder 塞进 `HINT_L3` 假装提示。 |
| `requires_project_facts` | 无对应字段 | `NEEDS-EXT` | 建议 additive：`AssessmentItem` 可选 `requires_project_facts: bool = False`（或 InterviewDomainPort 方法）。缺失时拒绝 `MAP-E03`，不得默认 `False` 静默放行（否则会替用户编造事实）。 |
| `synthetic` / `license` | fixture 元数据（不进入记录） | `LOSSLESS-ENCODED` | 记录进 MigrationManifest 与 domain_version 审计；非 CC0/synthetic → `MAP-E02`（许可不合规不得导入） |
| `schema_version="m1.offline.v0"` | — | 校验门槛 | 不等于已知版本 → `MAP-E01`；映射器版本与源版本绑定 |
| （无 `difficulty`） | `AssessmentItem.difficulty` 1..5 | `NEEDS-EXT` | B 无难度字段；建议访谈 fixture 增加可选 `difficulty`，否则用**显式常量默认 3 + 标记 uncalibrated**（写入 `Reason.detail`/manifest）；不得从题目长度之类隐式“猜”难度后当成校准值 |
| （无 `item_type`） | `AssessmentItem.item_type` | `NEEDS-EXT` | B 为开放式口头回答；`m1a.v0` 只有 `MCQ/CODE/SHORT_ANSWER`。建议 additive 增加 `OPEN_ANSWER`（D12 允许 append enum values）并配 `assessment_mode="RULE_RUBRIC"`、`deterministic=False`；未扩展前映射为 `SHORT_ANSWER` 属**语义降级**，必须在 `Reason.detail` 标记 `MAPPING_DEGRADED_OPEN_ANSWER`，且 Reviewer 可要求拒绝（`MAP-E03`） |
| （无 `answer`/隐藏题） | — | 边界 | 隐藏题集 `fixtures/m1/interview/hidden/**` 必须**不导入** teacher-visible 表；只作为 AssessmentPort/scorer 测试集；泄漏 → `MAP-E05` |

派生记录：

- `KnowledgeNode(interview.node.<track>)`: `title=track`、`description="面试域合成题库（synthetic/CC0）"`、`difficulty=3`（显式默认，uncalibrated 标记）、`assessment_mode="RULE_RUBRIC"`、`tags=["track:<track>","synthetic","cc0"]`、`content_ref=""`。
- `PrerequisiteEdge`：B 无难度/依赖边；**不生成**边（空图合法）；如后续 topic 依赖需要，必须显式 fixture 提供，不得由映射器臆造。
- `AssessmentItem(interview.item.<qid>)`: `node_ids=[interview.node.<track>]`、`item_type` 见上、`prompt`、`options=[]`、`function_name=None`、`max_score=1.0`、`deterministic=False`、`scoring_spec_ref="scorer://interview/<qid>/rubric@v1"`。

**可逆性校验（PR4 测试计划）**：对每个 question 断言 `prompt/question_id/domain/node` 反投影一致；rubric/ladder/requires_project_facts 只在扩展侧可回读；任何 teacher-visible dict 的 keys 不含 `rubric_points`/`follow_up_ladder`/`answer` 等隐藏字样。

### 3.3 Interview 答案 + 四维 rubric → AssessmentPort（scorer-only）+ `AssessmentResult`

B 源：`fixtures/m1/interview/answers/<id>.json`（envelope `answer:{text, evidence_refs, project_facts, quantitative_claims, misconceptions}`）+ `rubric.py` 的四维评分（`factual_correctness/explanation_clarity/engineering_feasibility/evidence_sufficiency`，0..1；`failure_modes`；确定性、无 runtime）。

| B 数据/字段 | 目标 | 状态 | 规则 |
|---|---|---|---|
| 原始答案 `answer.text` | 学生响应（learner-owned data） | `LOSSLESS-ENCODED` | 只经 `AssessmentPort` 输入、响应摘要写入 `RESPONSE_SUBMITTED.payload.response_digest`；完整文本进受控 `responses` 表（非隐藏答案、按 learner/session 隔离；导出时脱敏/仅本人可见）。**不得**进 teacher-visible 类型/隐藏表 |
| `answer.evidence_refs` | 评分器证据引用 | `SCORER-ONLY` | scorer 内部用于证据维度；teacher 可见 `AssessmentResult.evidence_refs` 只允许 `item:<item_id>`、`assessment:<result_id>`、公开来源摘要（去内容化） |
| `answer.project_facts` | 项目事实边界判定输入 | `SCORER-ONLY` + `NEEDS-EXT`（历史 payload） | 判定结果（“有/无可核验项目事实”）进入 AssessmentPort 状态；若需要跨轮保留，写入 `HistoryEvent.payload` 的 learner-owned 子结构（建议 key `interview_project_facts`，只存事实引用摘要，不存隐藏标签）。无事实时 scorer 返回 `NEEDS_REVIEW` 并携带 reason code `PROJECT_FACTS_REQUIRED`；教练随后发 `ASK_CLARIFICATION`（§4.2/§5.2），**不得**由映射器/教练代填事实 |
| `answer.quantitative_claims/misconceptions` | rubric 内部判定 | `SCORER-ONLY` | 无 teacher-visible 字段；失败模式以 code 形式返回（`unsourced_quantitative_claim` 等），不返回原文 |
| 四维分数 `dimensions{4}` | `AssessmentResult` 无 dimensions 字段 | `NEEDS-EXT` | A `AssessmentResult` 只有 `score/max_score`；建议 additive optional `dimensions: dict[str,float] | None = None`（键固定 4 个、值 0..1）并记 ADR。备选：sidecar `InterviewAssessmentDetail`（`AssessmentPort.assess_detail(result_id)`），由 `evidence_refs` 的 checksum 引用；两种方案二选一，见 §9-未决问题 |
| 加权总分 | `AssessmentResult.score/max_score` | `LOSSLESS-ENCODED` | 权重沿用 B 线 `factual 0.35 / clarity 0.20 / feasibility 0.20 / evidence 0.25`（`OWNER_REPORTED`：`m1_offline/interview/coach.py`）；`max_score=1.0`；`score` 必须有限且 0..1，越界 → `MAP-E16` |
| `passed` 布尔 | `AssessmentResult.status` | `LOSSLESS-ENCODED`（需映射表） | **不得**直接写 `status="CORRECT"`；按下表确定性映射；任何无法判定的分支必须 `NEEDS_REVIEW`，不得升级 |
| `failure_modes`（list[str]） | `AssessmentResult.failure_reason`（str）/ 无 list 字段 | `NEEDS-EXT` | 建议 additive optional `failure_modes: list[str] = []`；过渡期可 canonical JSON 字符串放 `failure_reason`（`LOSSLESS-ENCODED`，可回读），但 Reviewer 可要求正式字段 |
| `hidden_cases_passed/total` | `AssessmentResult` 无对应字段 | `NEEDS-EXT` | 只允许**聚合计数**（不含隐藏题内容）；建议 additive optional 字段或 sidecar；`total=0` 时不得伪造通过率 |
| `scorer_id` | `AssessmentResult.scorer_id` | `LOSSLESS` | 固定 `"interview.rubric.m1offline.v0"`（可信评分器身份）；缺失 → `MAP-E23` |
| `assessment_id` | `AssessmentResult.result_id` | `LOSSLESS-ENCODED` | `interview.assessment.<source id>`；同一 `(learner,item,response_digest,scorer_id)` 重放必须得到同 result_id（幂等，B3 范围外但接口要求）；冲突 → `MAP-E15` |
| `created_at` | `AssessmentResult.created_at` | `LOSSLESS-ENCODED` | 时间戳规范化；测试可用固定时钟 |

**status 映射表（AssessmentPort 的确定性规则；`DESIGN_ONLY`）**

| 条件（四维分数 + 边界） | status | 掌握度影响（A MasteryModel） |
|---|---|---|
| scorer 抛错/超时/规格缺失（基础设施） | `EVAL_ERROR` | **不更新**（非学习者证据） |
| 题目要求项目事实但无法核验 / rubric 无法判定（含糊、开放语义不足） | `NEEDS_REVIEW` | **不更新** |
| 加权 ≥ 0.65 且 factual ≥ 0.5 且无 unsourced 量化说法 | `CORRECT` | 按 `item.node_ids` 更新 |
| 加权 0.35..0.65，或存在部分正确但未达 CORRECT | `PARTIAL`（`score=weighted`） | 按 A 的 `partial_credit_threshold` 规则 |
| 加权 < 0.35 或 factual < 0.5 | `INCORRECT` | 允许下降，不得上升 |
| 命中 `MAPPED-DEGRADED` 语义（如 OPEN→SHORT_ANSWER） | `NEEDS_REVIEW`（默认） | 不更新 |

> 关键：`passed` 是 B 线的工程阈值，不是 canonical 掌握度；只有 `CORRECT/INCORRECT/PARTIAL` 且来源为 **OBSERVED** 才能进入 A mastery。`NEEDS_REVIEW`/`EVAL_ERROR` 与 B4-03 的 RECHECK 一样，**不产生学习证据**。

### 3.4 五阶段追问 ladder ↔ Hint Ladder（LIGHT→INVARIANT→STRUCTURE→FULL）

**先给结论：两者是正交维度，不能互相替代。**

- Interview 五阶段（`concept → hypothesis → complexity → experiment_design → online_triage`）是**追问深度/探究层次**，产出的是“下一个问题”，不是“给出多少答案”。
- Hint Ladder（`LIGHT_HINT → INVARIANT_HINT → STRUCTURE_HINT → FULL_SOLUTION`）是**干预强度**，产出的是“提示到哪一步”。
- 因此：**Interview 的任何阶段都不得映射为 `FULL_SOLUTION`**；五阶段追问也不得被压缩成 `HINT_L1..L3` 的三个 rung。

| Interview 阶段 | 语义 | 可映射的 `TeachingAction` | 与 hint ladder 的关系 | 状态 |
|---|---|---|---|---|
| `concept` | 澄清概念定义 | `SOCRATIC_QUESTION`（建议新增枚举值）或 `HINT` + `Reason.code=INTERVIEW_PROBE_CONCEPT` | 不消耗 hint rung；不泄答案 | `NEEDS-EXT`（枚举值） |
| `hypothesis` | 可证伪假设 | 同上，`..._HYPOTHESIS` | 不消耗 rung | `NEEDS-EXT` |
| `complexity` | 复杂度/量级 | 同上，`..._COMPLEXITY` | 不消耗 rung | `NEEDS-EXT` |
| `experiment_design` | 实验设计 | 同上，`..._EXPERIMENT_DESIGN` | 不消耗 rung | `NEEDS-EXT` |
| `online_triage` | 线上定位 | 同上，`..._ONLINE_TRIAGE` | 不消耗 rung | `NEEDS-EXT` |
| （无对应） | 完整答案 | **禁止** | `FULL_SOLUTION` 只属于 hint ladder 且默认禁止 | `REJECT MAP-E11` |

- 五阶段**状态不落在 `SessionState`**（A 冻结字段只有 `phase/turn_index/pending_item_id`）：阶段由 `HistoryEvent` 中 `ACTION_TAKEN` 的 `Reason.code`（`INTERVIEW_PROBE_<STAGE>`）序列确定性推导，replay 可重建（§5.5）。这样避免新增 session 字段。
- `follow_up_ladder` 文本是 teacher-visible 内容，但**不得**包含 rubric points/隐藏答案；如夹具 ladder 泄露评分要点 → `MAP-E05`。
- 若 Core/Plan 必须用 hint 内容表达追问（过渡方案），只能映射为 `HINT` + `Reason.code=INTERVIEW_PROBE_*`，且必须在 `Reason.detail` 声明 `hint_level=None`、`no_full_solution`；**不得**用 `STRUCTURE_HINT` 冒充追问（会把探究深度与干预强度混为一谈）。

### 3.5 JD v1/v2 → 版本化岗位上下文（KnowledgeSourcePort）

B 源：`fixtures/m1/interview/jds/*.json` 字段 `schema_version, jd_id, role, company_synthetic, requirements[], skills[], valid_from, valid_until[, supersedes], synthetic, license`。

| B 字段 | 目标 | 状态 | 规则 |
|---|---|---|---|
| `jd_id` | KnowledgeSourcePort 的 `source_id` | `LOSSLESS-ENCODED` | `jd:<jd_id>`；版本序列把 `jd-rec-v1→v2` 映射为同一 source 的两个 revision（`supersedes` 记录父版本） |
| `valid_from` / `valid_until` | 版本有效期 | `NEEDS-EXT` | 注意：B 的 `valid_from` 是**岗位有效期起点**，不是“来源发布时间 `published_at`”。不得直接塞进 `published_at` 冒充发布时间。建议 KnowledgeSourcePort 的 JD 视图带显式 `timestamp_semantics="VALIDITY_WINDOW"`，或新增 `JdVersion{jd_id, valid_from, valid_until, supersedes, content_digest}` extension。把 `valid_from` 当 `published_at` → `MAP-E04`（语义错误拒绝） |
| `role` / `requirements` / `skills` | 岗位上下文内容 | `NEEDS-EXT` | `m1a.v0` 无 JD 类型；不得把 JD 变成 `KnowledgeNode`（会污染知识图谱/掌握度）。作为 KnowledgeSourcePort 的 domain context 返回给 **policy 选择 objective**，内容本身不进 teacher-visible 知识记录；如后续需要 UI 展示，走 section-scoped extension |
| `supersedes` | 版本链 | `LOSSLESS-ENCODED` | 与 KnowledgeRevision 的 old/new 对应；缺失时按 v1=首版处理（显式默认，不得猜） |
| `company_synthetic` / `synthetic` / `license` | 合规标记 | 校验门槛 | 非 `true`/非 CC0 → `MAP-E02`（拒绝导入）；所有 JD 合成，无真实公司/人名 |
| （无 `published_at/observed_at`） | 时效元数据 | `NEEDS-EXT` | 导入时必须注入 `observed_at`（导入时刻，确定性时钟）与来源层 `jd`；`published_at` 若无则留空并标记 `UNKNOWN`，**不得**伪造 |
| 版本变更 | `KnowledgeRevision`（UPDATE 或 RECHECK） | `LOSSLESS-ENCODED`（经 port） | v1→v2 且 v2 在有效期、无冲突、来源层允许 → `UPDATE`（但 JD 层 `may_update_curriculum=False`：**不得**直接改知识库/课程，只能用于**新建**计划的 objective 选择）；过期/重叠冲突 → `RECHECK`；详见 §3.7 |
| JD 变化的影响范围 | 课程（新计划）而非运行中会话 | 策略 | JD 版本变化**不得**修改运行中 `SessionState`/`LearnerGoal` 的 `objective_id`；只影响**新计划**与新会话；JD 变化 ≠ 题目热度（不产生 popularity 信号，不参与 mastery） |

### 3.6 `KnowledgeSource` → 版本化知识 provenance（KnowledgeSourcePort）

B 源字段（`m1_offline/types.py`）：`source_id, uri, publisher, published_at, observed_at, valid_until, confidence, claim_status ∈ VERIFIED|REPORTED|CONFLICT|EXPIRED|UNKNOWN`。

| B 字段 | 目标 | 状态 | 规则 |
|---|---|---|---|
| `source_id` | KnowledgeSourcePort 主键 | `LOSSLESS-ENCODED` | `knowledge:<source_id>`；同一 source 的多个版本共享 source_id，revision 由 (old_hash,new_hash,detected_at) 区分 |
| `uri` | provenance | `LOSSLESS` | 合成域名 `.invalid`；不得产生可访问网络请求（导入器只读本地 fixture） |
| `publisher` | provenance + 来源层推断输入 | `LOSSLESS` | 保留原文；层推断映射表见 `FRESHNESS_AND_SOURCE_POLICY.md`（official_document/paper/blog/jd/community/mirror/unknown） |
| `published_at` | provenance（**来源发布时间**） | `LOSSLESS` | 与 `observed_at` **必须分开保留**；不得折叠 |
| `observed_at` | provenance（**观测时间**） | `LOSSLESS` | 版本中发现/核对时间；replay 用固定时钟 |
| `valid_until` | provenance（有效期） | `LOSSLESS` | 可为 None；过期判断依据 |
| `confidence` | provenance（float 0..1） | `LOSSLESS` | 不参与 teacher 可见课程决策之外的权重计算；不得用于“自动提升掌握度” |
| `claim_status` | 时效/可信状态 | `NEEDS-EXT` | `m1a.v0` 无 claim_status 字段；`KnowledgeNode` 只有 tags/created_at。不得丢弃（否则 CONFLICT/EXPIRED 可能静默进入课程）→ 若目标记录不含该字段则 `MAP-E07`。建议 extension `KnowledgeProvenance{source_id, uri, publisher, published_at, observed_at, valid_until, confidence, claim_status, source_tier, content_digest, revision_ref}`（audit-only，teacher-visible 允许，不含答案） |
| （无）来源层 | `source_tier` | `NEEDS-EXT` | 复用 B 的 `SOURCE_TIERS` 分层；**JD 层 `may_update_curriculum=False`**；`signals_topic_popularity=False` |
| （无）内容哈希 | `content_digest` | `NEEDS-EXT` | B v0 用元数据指纹（uri+publisher+published_at+claim_status）近似；必须显式记录为 `approximate=True`，正文级变更需上游 digest；不得声称正文级无损 |
| 时间戳格式 | A 记录 | `LOSSLESS-ENCODED` | `+00:00`→`Z`；亚秒/非 UTC → `MAP-E04` |
| 未知枚举（claim_status/source_tier） | 稳定枚举 | `REJECT` | 未知值 → `MAP-E03`（不得默认 UNKNOWN 静默放行） |

**显式语义区分（必须写进 event/extension，不能只靠注释）**

- `published_at`：来源自己声明的发布时间（B 真实值如 `2026-05-10T00:00:00+00:00`）。
- `observed_at`：我们抓取/核对到它的时间（B 真实值如 `2026-11-01T09:00:00+00:00`）。
- `valid_until`：来源有效期；`observed_at > valid_until` 时 → `EXPIRED`/`RECHECK`。
- `published_at > observed_at`（未来时间/时钟异常）→ `RECHECK`（拒绝静默更新）。
- 两条时间线差异（observation lag、publish delta）必须写入 `KnowledgeRevision`-对应 extension 的 `notes`/`Reason.detail`，供审计与 replay。

### 3.7 `KnowledgeRevision`（KEEP/UPDATE/RECHECK）→ 计划/课程门禁

B 源：`KnowledgeRevision(revision_id, source_id, old_hash, new_hash, change_kind ∈ KEEP|RECHECK|UPDATE, detected_at, claim_status, notes)`；B 规则（`OWNER_REPORTED`，`m1_offline/freshness.py`）：

- 指纹相同 → KEEP；
- 发布更新 + 权威/置信度不降 → UPDATE；
- 冲突/过期/更旧/未来时间/低权威/歧义 → RECHECK；
- `apply()` 只分组；`curriculum_eligible` 仅 `UPDATE + VERIFIED + 层允许`。

| B change_kind | 目标（m1a.v0） | 状态 | 规则 |
|---|---|---|---|
| `KEEP` | 无课程动作 | `LOSSLESS`（no-op） | 不生成 PlanStep/不写课程；仅 KnowledgeSourcePort 审计表记录 `last_checked_at`；不得产生 event（防止污染教学事件流） |
| `UPDATE` | 新计划中的知识更新步骤（**不能原地改运行中计划/会话**） | `NEEDS-EXT` | 若 `claim_status=VERIFIED` 且层 `may_update_curriculum=True` 且无冲突：materialize 新的知识版本，并在**新计划**中以 `PlanStep(action_kind=REVIEW 或 RETEACH, rationale=Reason(code="KNOWLEDGE_UPDATE_APPLIED", detail=revision 摘要))` 体现；运行中 session 不得被改写 → 若尝试 → `MAP-E17`/`MAP-E08`。JD 层 UPDATE 不产生 PlanStep（只影响新 objective/plan 选择） |
| `RECHECK` | 复核队列，**禁止进入课程** | `LOSSLESS`（blocked） | 不产生 PlanStep；写入 `KnowledgeReviewQueue`（extension 表）；任何 planner/domain 尝试消费 → `MAP-E08`；冲突 → `MAP-E09`；过期 → `MAP-E10`(JD)/`MAP-E08`(知识) |
| `revision.claim_status` | 事件/Reason 审计 | `NEEDS-EXT` | 无对应 teacher-visible 字段时保留在 provenance extension；`CONFLICT/EXPIRED` 不得丢弃（`MAP-E07`） |
| `old_hash/new_hash` | 校验/幂等 | `NEEDS-EXT` | 无 teacher-visible 对应字段；保留在 provenance/audit extension；缺失 → `MAP-E07`（replay 无法证明去重） |
| `detected_at` | 事件/审计时间 | `LOSSLESS-ENCODED` | 时间戳规范化；作为 revision 的 `observed_at`（观测时间）保留 |
| `notes` | `Reason.detail`/审计 | `LOSSLESS-ENCODED` | 自由文本原样保留（非隐藏材料），标记 `source=port`；不得裁剪掉 `recheck_required`/`jd_change_does_not_imply_topic_popularity` 等机器标记 |
| `revision_id` | 事件引用/审计主键 | `LOSSLESS-ENCODED` | `knowledge.revision.<revision_id>` |

**课程门禁规则（设计，PR4 测试矩阵 B4-03 验证）**：

1. 任何 `RECHECK`（冲突/过期/未授权低权威/未来时间/歧义）**不得**进入 `CurriculumPlan`/`PlanStep`/teaching content；只能人工复核后由人类把新版本改为 VERIFIED + 授权，才可能成为 UPDATE。
2. 只有 `UPDATE + VERIFIED + source_tier.may_update_curriculum` 才能影响课程内容；JD/community/mirror/unknown 层永不改课程。
3. UPDATE 的应用对象是**新计划**；运行中会话保持原计划（可完成），不得热改教学内容（防止同一会话内前后矛盾）。
4. 全部知识决策留审计引用：`Reason.evidence_refs` 记录 `knowledge.revision.<id>`；teacher-visible 理由中不得出现正文级隐藏内容（知识正文本身是公开教学材料，允许；但权威冲突细节只给 code）。
5. 冲突/过期状态在事件与查询中**显式可见**，不得只存在内存。

### 3.8 其余记录的迁移映射（状态/事件/动作/目标）

| B 记录 | A 目标 | 状态 | 关键字段规则 |
|---|---|---|---|
| `SkillNode` | `KnowledgeNode` | `NEEDS-EXT` | `skill_id→node_id`（`interview.node.<track>` 或 CF 域各自命名空间）；`name→title`；`domain→domain_id`；`description→description`；`prerequisites[skill_id]` 无 A 字段 → 生成 `PrerequisiteEdge(kind="HARD")`（B 无 HARD/SOFT，默认 HARD 为**显式策略默认 + uncalibrated 标记**；需 fixtures 提供 SOFT 语义时 `NEEDS-EXT`）；无 `difficulty` → 显式默认 3 + uncalibrated；`assessment_mode` 需按域显式给出（Interview=`RULE_RUBRIC`，CF=`DETERMINISTIC_JUDGE`） |
| `LearnerProfile` | 无对应 | `NEEDS-EXT` | A 没有 profile 类型；`display_name/baseline_level` 只能作为 `learners` 表 additive 列/extension；缺失不阻塞教学（`baseline_level` 不得成为隐藏先验影响评分） |
| `LearnerState` | `LearnerSnapshot` + `MasteryEstimate` | `NEEDS-EXT` + **单写者约束** | `mastery dict[str,float]` → `masteries dict[str, MasteryEstimate]`：`value` 无损；A `confidence` 无 B 来源 → 迁移常量 0.0 + `migration_confidence_policy="ZERO_DEFAULT_UNCALIBRATED"`（不得用 B mastery 伪造 confidence）；`error_counts` 键空间（B skill/error code vs A 任意非空 str）需映射表并保序；`evidence_count` A 无全局字段 → 由各 `MasteryEstimate.evidence_count` 求和/由事件重算；`updated_at` 规范化。**迁移后 B 的 `LearnerModel` 停止写入 canonical**（`MAP-E25` 若检测到双写） |
| `EvidenceEvent`（含 `evidence_refs`） | `EvidenceReference` | `LOSSLESS-ENCODED` | `evidence_id` 命名空间 `evidence.<event_id>`；`source`：B 的观测评分/行为证据 → `OBSERVED`，B 的推断/自述 → `INFERRED`（**不得**用于 mastery 更新，A 仅接受 OBSERVED）；`event_id` 指向对应 `HistoryEvent`；`detail` 去隐藏内容（`MAP-E05`）；缺失 event 绑定 → `MAP-E02` |
| `EvidenceEvent` | `HistoryEvent` + `AssessmentResult` | `NEEDS-EXT` | `event_id` 加命名空间；`kind ∈ ANSWER/CODE_SUBMISSION/EXPLANATION/INTERVIEW_RESPONSE/ASSESSMENT/HINT_REQUEST` 在 A `HISTORY_EVENT_TYPE` 无对应值 → 建议 event payload 增加 `event_subtype`（additive payload key，不改记录结构）或映射为最接近的 `RESPONSE_SUBMITTED/ASSESSED` 子类型；`payload` → HistoryEvent.payload（JSON-safe）；`observed_score` → 嵌入 `AssessmentResult.score`（若该 evidence 无对应 assessment → `MAP-E02` 缺必填）；`error_codes` → `failure_reason`/额外 payload；`provenance` → 审计 extension；`created_at` 规范化 |
| `TraceEvent` | `HistoryEvent` | `LOSSLESS-ENCODED`（映射表） | `loop_id→session_id`；`round→payload.round`；`step` 映射：`diagnose→DIAGNOSIS_COMPLETED`、`plan→PLAN_CREATED`、`action→ACTION_TAKEN`、`response→RESPONSE_SUBMITTED`、`assess→ASSESSED`、`memory→MASTERY_UPDATED`、`halt→payload.halt_reason`（终态事件 `GOAL_COMPLETED/REVIEW`）；`payload.seq` 必须存在且连续，缺失/重复 → `MAP-E14`；`timestamp→created_at`；`event_id` 前缀 `evt.<loop>.<sha>` |
| B `rationale` / `notes` / `error_codes` | `Reason` | `LOSSLESS-ENCODED` | B 无 `Reason` 对象 → 构造 `Reason(code=<稳定域 code>, node_ids=<映射节点>, detail=<rationale/notes 文本>, policy_version=<policy>)`；文本保留但必须去隐藏材料（`MAP-E05`）；code 映射见 §5.6，未知 code → `MAP-E03` |
| B `LoopResult` / 会话进度（`TraceEvent` 序列） | `SessionState` | `LOSSLESS-ENCODED` | `session_id` 由 loop_id 命名空间化；`learner_id/goal_id/objective_id` 由映射上下文提供；`phase` 由回合进度映射到 `SESSION_PHASE`（DIAGNOSE/TEACH/PRACTICE/ASSESS/UPDATE/REVIEW/PAUSED/COMPLETE）；`turn_index` 由 round/seq 推导；`pending_item_id` 由当前 action 的 item 推导；B 的 PAUSED 语义保留；无法映射的 halt → REVIEW/COMPLETE + reason；phase/turn 不一致 → `MAP-E17` |
| `TeacherAction` | `TeachingAction` | `NEEDS-EXT` + `REJECT` 分支 | `action_id` 命名空间；`kind` 映射见 §6.1（`SOCRATIC_QUESTION`/`ASK_CLARIFICATION` 无 A 枚举 → 建议 additive 增加；`FULL_SOLUTION` → `MAP-E11` 禁止默认）；`content→content`；`rationale→Reason.detail`；`hint_level` A `TeachingAction` 无字段 → 建议 additive optional `hint_level: int | None`（或编码进 `Reason.code="HINT_LEVEL_n"`，lossy-encoded）；`target_skill_ids→node_ids`；`evidence_refs` 保留但必须去隐藏材料（`MAP-E05`） |
| `AssessmentResult`（CF/Interview） | `AssessmentResult`（m1a） | 混合 | 同 §3.3；CF 的 `hidden_cases_*` 聚合计数、`dimensions`（correctness/edge_case_accuracy/efficiency）需 extension；`failure_modes` 需 extension；status 映射同上；隐藏 expected 不进 `failure_reason`（B 已知限制 `expected_repr` 需在 AssessmentPort 内清洗，`MAP-E05`） |
| `DiagnosticResult` | `DiagnosisResult` | `NEEDS-EXT` | A `status ∈ READY|INSUFFICIENT_EVIDENCE`；B `status ∈ RESOLVED|UNKNOWN|NEEDS_REVIEW` → `RESOLVED→READY`、`UNKNOWN→INSUFFICIENT_EVIDENCE`、`NEEDS_REVIEW→INSUFFICIENT_EVIDENCE` + `Reason.code="DIAG_NEEDS_REVIEW"`（**显式降级**，不得当 READY）；`confidence/error_codes/task_id` 无 A 字段 → extension；`target_node_id/selected_item_id/hypothesis/evidence_refs` 可映射 |
| `LearningGoal` | `LearnerGoal` + `LearningObjective` | `NEEDS-EXT` | B `goal_id/learner_id/target_skills` → A `LearnerGoal` 需 `objective_id`：经 KnowledgeGraph/objective registry 由 target_skills 解析出 objective（解析失败 → `MAP-E02`）；`deadline_days/weekly_minutes` A `LearnerGoal` 无字段 → extension/表列；`target_skills→objective.target_node_ids` 必须校验 node 存在 |
| `LearningTask` | `PlanStep`（+`LearningObjective`） | `NEEDS-EXT` | `task_id→PlanStep.step_id` 命名空间；`goal_id` A PlanStep 无该字段（由 plan 关联）→ payload/extension；`skill_ids→node_ids` 必须全部存在；`task_type` B ∈ `CF_PROBLEM|INTERVIEW_QUESTION|REVIEW|READING` vs A `PlanStep.phase`/`action_kind` 枚举不同 → 映射表（CF_PROBLEM→PRACTICE/ASSESS；INTERVIEW_QUESTION→PRACTICE/ASSESS；REVIEW→REVIEW；READING→TEACH/EXPLAIN）；`difficulty` A PlanStep 无字段 → extension 或丢弃需显式标记；`fixture_ref→item_id` 解析失败 → `MAP-E02`；`ordinal→ordinal` |
| `CurriculumPlan`（B） | `CurriculumPlan`（A） | `NEEDS-EXT` | `plan_id/goal_id/policy_version` 可映射；B `tasks→A steps` 需 `PlanStep.rationale` 为 `Reason` 对象：B 的 `rationale: list[str]` → `Reason(code="PLAN_RATIONALE", detail=join)` 属 lossy 文本保留（`LOSSLESS-ENCODED`）；A 需要 `learner_id/objective_id`（B 无）→ 由 goal/objective 解析；B plan 无 objective → `NEEDS-EXT` |
| `Provenance` | 审计 extension | `NEEDS-EXT` | A 无 Provenance 类型；只进 manifest/audit 表，不伪造进 `created_at` |
| `RuntimeRequest/Response` | — | 不迁入 | 仅 Mock 边界文档；不得把 runtime 输出写进 canonical 状态（`MAP-E25` 若出现） |

### 3.9 稳定拒绝码（fail-closed）

全部拒绝码在 PR4 实现时以结构化错误（`M1AError` 子类或 port-local `PortMappingError`）暴露，包含 `code/detail/ref`，且**不写任何部分状态**（导入批次回滚）。建议稳定码：

| code | 触发条件 | 处理 |
|---|---|---|
| `MAP-E01_SCHEMA_VERSION_UNSUPPORTED` | 输入记录 `schema_version` 不在支持集合（如 `m1.offline.v1`、未知） | 拒绝整批；提示支持版本 |
| `MAP-E02_REQUIRED_FIELD_MISSING` | 必填字段缺失/空；fixture 许可非 synthetic/CC0 | 拒绝该记录 |
| `MAP-E03_ENUM_VALUE_UNSUPPORTED` | 枚举值不在 A/B 已知集合（track/kind/status/claim_status/event_subtype/objective 映射失败） | 拒绝；不默认映射 |
| `MAP-E04_TIMESTAMP_UNSUPPORTED` | 非 UTC offset、亚秒、不可解析、`published_at` 被误用为 `valid_from` 等语义错误 | 拒绝 |
| `MAP-E05_HIDDEN_MATERIAL_LEAK_BLOCKED` | 尝试把 rubric_points/隐藏题/expected/answer key 写入 teacher-visible 记录、事件、诊断、trace | 拒绝并告警；记安全事件 |
| `MAP-E06_UNTRUSTED_DOC_AS_TEACHER_DATA` | 注入文档（`fixtures/m1/interview/injection/**`）出现在 teacher-visible 记录或事件 payload | 拒绝；文档只允许 DATA_ONLY 测试集 |
| `MAP-E07_KNOWLEDGE_PROVENANCE_LOSS` | claim_status/confidence/hash/publisher 等 provenance 被静默丢弃，或目标记录无字段承载 | 拒绝（禁止静默降级） |
| `MAP-E08_KNOWLEDGE_RECHECK_BLOCKED` | RECHECK 知识被 planner/domain 尝试写入计划/课程 | 拒绝；进入复核队列 |
| `MAP-E09_KNOWLEDGE_CONFLICT_BLOCKED` | claim_status=CONFLICT 或来源冲突被当作 UPDATE/课程内容 | 拒绝；复核队列 |
| `MAP-E10_JD_EXPIRED_OR_CONFLICT` | JD 已过 `valid_until` / 版本重叠冲突仍被用于新计划 | 拒绝新计划；运行中会话可继续 |
| `MAP-E11_FULL_SOLUTION_FORBIDDEN` | 默认路径或无人类授权尝试 `FULL_SOLUTION`；Interview 任何阶段映射完整答案 | 拒绝；仅显式 human-approved Gate（B1 之外的人工批准）可放行 |
| `MAP-E12_DOMAIN_VERSION_MISMATCH` | adapter `domain_version` 与 session/plan 绑定版本不一致（会话中途升级域名） | 拒绝；必须 pause+新 session |
| `MAP-E13_EVENT_VERSION_INCOMPATIBLE` | 事件 payload 的 schema/domain/policy 版本不兼容 | 拒绝 replay/写入；不部分应用 |
| `MAP-E14_EVENT_SEQ_INVALID` | `HistoryEvent.seq` 缺失/重复/不连续（B TraceEvent payload 无 seq） | 拒绝导入该事件 |
| `MAP-E15_DUPLICATE_OR_CONFLICTING_ID` | 同一命名空间 ID 对应不同内容哈希/不同实体 | 拒绝；不得 last-write-wins |
| `MAP-E16_SCORE_OUT_OF_RANGE` | 分数/权重越界（非有限、<0、>1、max_score≤0） | 拒绝该 assessment |
| `MAP-E17_UNSUPPORTED_SESSION_TRANSITION` | 运行中会话被要求热改 objective/JD/知识内容；跨域切换未 pause；pending item 状态不符 | 拒绝；给出合法路径 |
| `MAP-E18_LEARNER_ID_MISMATCH` | event/result/snapshot 的 learner_id 与 session/目标不一致 | 拒绝；防跨学习者污染 |
| `MAP-E19_PROJECT_FACT_FABRICATION` | 教练/映射器试图写入未由学习者提供的项目事实/规模/提升百分比 | 拒绝；改发 `ASK_CLARIFICATION` |
| `MAP-E20_SECOND_WRITER_CONFLICT` | 检测到 B 线 `LearnerModel`/`LearnerState` 或 Domain 直接写 canonical snapshot | 拒绝；单写者校验失败即 STOP（安全事件） |
| `MAP-E21_MIGRATION_CHECKSUM_MISMATCH` | roundtrip/migration checksum 不一致 | 整批回滚，保留源与被拒清单 |
| `MAP-E22_SCORING_NOT_INDEPENDENT` | 评分结果由 coach 自身文本/LLM 自述产生，或 scorer 读取 teacher 会话状态/隐藏期望被绕过 | 拒绝；评分必须仅依赖 AssessmentPort 的隐藏 spec + response |
| `MAP-E23_SCORER_UNAVAILABLE` | AssessmentPort 不可用/规格缺失/异常 | 返回 `EVAL_ERROR`，**不更新 mastery**；不得降级为 CORRECT/NEEDS_REVIEW 混淆 |
| `MAP-E24_SCORING_REF_MISSING` | `AssessmentItem.scoring_spec_ref` 为空/指向 teacher-visible 内容 | 拒绝 item 导入（否则题目无法可信评分） |
| `MAP-E25_MASTERY_WRITE_FORBIDDEN` | 非 canonical 写入者尝试更新 mastery/snapshot | 拒绝；审计告警（与 E20 同域，区分触发点） |

---

## 4. 端口方案（Interview/Freshness 如何接入）

### 4.1 端口总览

```
+--------------------------------------------------------------------+
|                       canonical Teacher Core (m1_teacher)          |
|  Session Engine / Learner Model / History / Planner / Scorer       |
|  - single writer: LearnerSnapshot, HistoryEvent, SessionState       |
|  - consumes ONLY teacher-visible records                            |
+-----------^------------------^------------------^-------------------+
            |                  |                  |
   +--------+-------+  +-------+--------+  +------+-------------+
   | DomainPlugin   |  | AssessmentPort |  | KnowledgeSourcePort|
   | (Interview /   |  | (trusted       |  | (versioned knowledge|
   |  CF via        |  |  scoring:      |  |  + KEEP/UPDATE/    |
   |  DomainAdapter)|  |  hidden rubric)|  |  RECHECK + JD)     |
   +----------------+  +----------------+  +--------------------+
            ^                  ^                  ^
   +--------+------------------+------------------+-------------------+
   | TeacherPolicyPort (action selection, hint ladder evidence gates) |
   +-----------------------------------------------------------------+
                (all four: read-only toward core records; no direct
                 snapshot writes; no hidden-material exposure)
```

### 4.2 Interview 作为 Domain Plugin / DomainAdapter

**A 侧现状（SOURCE_INSPECTED）**：`DomainAdapter` 已有 `knowledge_nodes/prerequisite_edges/objectives/assessment_items/teaching_content/validate`；`extensions/interfaces.py` 只有 `InterviewCoachPort.start/assess_answer` stub（fail closed `EXTENSION_NOT_IMPLEMENTED`）。B-PR4 建议新增 **additive extension 模块** `m1_teacher/extensions/interview_domain.py`（PR4 后续实现；本文不写代码），包含：

```text
@runtime_checkable
class InterviewDomainPort(DomainAdapter, Protocol):
    domain_id: str                    # "interview_coach"
    domain_version: str               # 独立域版本，随 JD/题库变更 bump
    def interview_items(self) -> list[AssessmentItem]
    def follow_up_ladder(self, item_id: str) -> list[FollowUpProbe]   # 5 条 teacher-visible 追问
    def requires_project_facts(self, item_id: str) -> bool
    def jd_versions(self) -> list[JdContextView]                      # 只读岗位上下文
```

规则（全部 `DESIGN_ONLY`，实现必须 test-enforced）：

1. **只读且无副作用**：所有方法返回新列表/值对象，不得写 learner/session/event/snapshot；任何写尝试 → `MAP-E20/E25`。
2. **只暴露 teacher-visible 数据**：不得返回 `rubric_points`、隐藏题、expected、answer；`follow_up_ladder` 只含教师可念出的追问句；隐藏内容由 AssessmentPort 持有。
3. **确定性**：稳定排序（node_id/item_id/JD version）；无时钟读取（时间戳由调用方传入/固定时钟）；同一输入同输出。
4. **`validate()` fail-closed**：id 唯一、所有 item 的 `node_ids` 存在、`scoring_spec_ref` 非空且被 AssessmentPort 登记、item_type/assessment_mode 合法、五阶段 ladder 恰好 5 条且 stage 名固定、`requires_project_facts` 显式、JD `valid_until` 可解析、无真实个人数据/无网络 uri 可解析为可访问资源（只允许 `.invalid`）。
5. **域版本**：`domain_version` 由题库/JD/rubric 版本共同决定；`SessionState`/`CurriculumPlan` 记录所用域版本；不匹配 → `MAP-E12`。
6. **注册**：走 `DomainRegistry.register()`；与 CF 域并存，`list_domains()` 排序稳定；重复 `domain_id` → `ConflictError`（A 现状）。
7. **能力边界**：域**不得**读 `LearnerSnapshot`（无法判断学生掌握度）；需要 learner-state 影响追问时，由 Core 通过 `TeacherPolicyPort` 的只读上下文传入（决策在 policy，不在 domain）。
8. **隐藏题集隔离**：`fixtures/m1/interview/hidden/**` 不进入任何 adapter 的 allow-list；Provider 侧静态扫描禁止 adapter 目录出现 `hidden/` 路径引用。

**缺口与现状对照**：

| 能力 | A 现状 | PR4 设计 | 状态 |
|---|---|---|---|
| 题目 metadata | `AssessmentItem` 可用 | 直接用 | `LOSSLESS` |
| 追问 ladder 5 阶段 | `teaching_content` kind 白名单不支持 | `InterviewDomainPort.follow_up_ladder`（新方法） | `NEEDS-EXT` |
| 项目事实边界 | 无字段 | `requires_project_facts`（新方法/optional 字段） | `NEEDS-EXT` |
| 多轮会话 | 冻结 `SessionState` 仅 pending_item | 用事件日志推导阶段（§5.2） | `LOSSLESS`（事件侧） |
| 4 维评分 | `AssessmentResult` 无 dimensions | AssessmentPort sidecar/optional 字段 | `NEEDS-EXT` |
| 注入防御 | 无 | 注入文档只进 DATA_ONLY 测试集，不进 event/records；`MAP-E06` | `LOSSLESS`（边界设计） |

### 4.3 AssessmentPort（可信评分；rubric/隐藏答案归属）

**归属原则**：rubric 规格、隐藏题集、期望答案、四维权重**只属于 AssessmentPort 的 scorer 侧**（独立模块/进程，PR4 后续实现；B-PR1 的 Judge Worker 安全边界在其完成后适用）。Teacher Core、Domain Plugin、Coach 模板文本**都不可读**。

```text
@runtime_checkable
class AssessmentPort(Protocol):
    scorer_id: str                      # e.g. "interview.rubric.m1offline.v0"
    def assess(self, item: AssessmentItem, learner_id: str,
               response: str | dict, *, result_id: str | None = None) -> AssessmentResult
    def detail(self, result_id: str) -> InterviewAssessmentDetail | None  # optional sidecar
```

硬性契约：

1. **输入只看** teacher-visible `AssessmentItem` + learner response + 隐藏 spec（由 scorer 自己按 `scoring_spec_ref` 读取）；**不看**会话文本、教练内容、LearnerState（避免自评/标签利用）。
2. **输出只回** `AssessmentResult`（+ 聚合计数）；`failure_reason` 只允许稳定聚合错误码/非泄露原因，禁止 `expected_repr`/隐藏用例内容（B 已知限制 `m1_offline/cf/judge.py` 的 `args_repr/expected_repr` 必须在移植时清洗；扫描 messages/trace/JSON 而不只源码 AST）。secret 泄漏尝试 → `MAP-E05` 并 STOP。
3. **独立性**：Interview 评分器不得用 coach 生成文本当证据（B 线已按此设计：`InterviewRubric` stdlib-only、不调用 Runtime；本设计将其读法保留）；LLM/教练自述不能直接产生 `CORRECT`。
4. **确定性**：同输入同输出；固定 seed/固定时钟；不联网、不调用真实 Provider。
5. **NEEDS_REVIEW 语义**：无法确定性判定（开放语义、项目事实缺失、注入干扰）→ `NEEDS_REVIEW`，**不更新 mastery**；不得用 LLM 猜成 CORRECT。
6. **EVAL_ERROR 语义**：scorer 自故障/规格缺失 → `EVAL_ERROR`，不改变 LearnerSnapshot/error_counts（A 现状 `mastery only from CORRECT/INCORRECT/PARTIAL`），可重试/`ERROR` 事件。
7. **身份/幂等**：`scorer_id` 固定入 `AssessmentResult`；`(learner_id,item_id,response_digest,scorer_id)` 决定 result_id，重试同结果；scoped idempotency 依赖 B3，PR4 只消费其契约。
8. **隐藏计数**：`hidden_cases_*` 只暴露聚合数字（若扩展），隐藏用例内容永不进入 teacher-visible JSON/trace/log。

B 线 `InterviewRubric.failure_modes`（`unsourced_quantitative_claim/missing_project_facts/...`）只以 code 形式进入 `failure_reason`（去原文），`feedback` 文本（含“例如提升百分比”）只能出现在 **scorer 内部测试**，不得回给 teacher 作为评分依据。

### 4.4 KnowledgeSourcePort（版本化知识 + 三态时效 + JD）

```text
@runtime_checkable
class KnowledgeSourcePort(Protocol):
    def get_source(self, source_id: str) -> KnowledgeSourceView | None
    def list_revisions(self, source_id: str) -> list[KnowledgeRevisionView]
    def classify(self, old: KnowledgeSourceView, new: KnowledgeSourceView) -> KnowledgeRevisionView
    def curriculum_eligible(self, revision: KnowledgeRevisionView) -> bool
    def latest_jd(self, jd_id: str, *, now: str) -> JdContextView | None   # 只返回有效且未冲突版本
    def pending_rechecks(self) -> list[KnowledgeRevisionView]
```

规则：

1. **三态语义固定**：`KEEP`=无需动作；`UPDATE`=可进入**新计划**（且仅 `VERIFIED + 层允许`）；`RECHECK`=进入复核队列，**禁止**进入计划/课程/掌握度。
2. **时间语义**：`published_at`（来源发布时间）、`observed_at`（观测时间）、`valid_until` 分别保留；未来时间、观测晚于有效期、更旧来源、低权威来源、冲突 → RECHECK（B 规则表 `OWNER_REPORTED`，`m1_offline/freshness.py`；映射时逐条断言）。
3. **来源分层**：official_document(3) > paper/blog(2) > jd(2) > community(1) > mirror/unknown(0)；只有前 3 类且 `UPDATE+VERIFIED` 可能改课程；**JD 层 `may_update_curriculum=False`**；**JD 变化 ≠ 题目热度**（不产生 popularity/掌握度信号；notes 保留 `jd_change_does_not_imply_topic_popularity=true`）。
4. **课程门禁**：`curriculum_eligible` 是唯一放行函数；`apply()`/writer 只能用其输出生成新计划；conflict/expired 永不静默；复核队列有审计记录。
5. **静态离线**：不抓取真实网页；无后台刷新；fixtures 自带 `published_at/observed_at/valid_until`，只证明门禁/审计机制。真实热点 Research 是未来经人类批准的新工作项（`02_LEADB_AGENT_HANDOFF.md` B4.5）。
6. **JD 提供方式**：`latest_jd` 只返回 `now ∈ [valid_from, valid_until]` 且无重叠冲突的版本；过期/冲突返回 None → 新计划拒绝（`MAP-E10`）；运行中会话不受影响。
7. **许可/合成**：所有 knowledge/JD fixture synthetic/CC0；真实个人简历/招聘数据禁止（`MAP-E02`）。

### 4.5 TeacherPolicyPort（Hint Ladder 证据门与追问策略）

```text
@runtime_checkable
class TeacherPolicyPort(Protocol):
    policy_version: str
    def select_action(self, ctx: PolicyContext) -> TeachingAction
    def max_hint_level(self, *, evidence_count: int, error_streak: int,
                       requested_level: int, human_approved_full: bool) -> int
```

规则：

1. **默认最低干预**：默认 `LIGHT`（hint level 1 / interview probe 概念层），新学习者 `evidence_count==0` 强制最低级。
2. **升级只认观测证据**：连续 `INCORRECT`/`PARTIAL` 评估证据 → 逐级升级；`NEEDS_REVIEW`/`EVAL_ERROR` 不计入升级证据（也不是错误）。B `EvidenceGate`（0→L1，1→L2，2–4→L3，≥5→L4 explicit-only）与 A `SessionPolicy`（`hint_escalation_threshold=1`，`max_hint_level=3`）合并为一个 canonical gate，阈值参数化并标 `UNCALIBRATED`。
3. **FULL_SOLUTION 默认禁止**：需要（a）显式 API 请求 `requested_level=4`（b）人类批准标志 `human_approved_full=True`（付费/真实用户路径下由未来审批系统提供；M1-B 仍无）；（c）证据达到 gate（≥5 观测）三重条件；任一缺失 → 最高 L3 或 `MAP-E11`。Interview 域根本不提供 full solution 内容。
4. **掌握度防火墙**：policy 不得直接写 mastery；只能通过 AssessmentResult（CORRECT/INCORRECT/PARTIAL + OBSERVED）交给 core；LLM/教练自述的“已掌握/很好”不产生任何 mastery 增量（B 线同样约束：`submission["passed"]` 被忽略；`OWNER_REPORTED`）。
5. **uncalibrated 声明**：所有启发式阈值（证据门、升级阈值、interview 阶段选择规则）在 `Reason.detail`/policy metadata 标 `UNCALIBRATED_HEURISTIC`，不得声称学习效果。
6. **解释性**：每个动作必须带 `Reason(code,node_ids,detail,policy_version)`；reason codes 稳定、可测（§5.5）。
7. **可替换策略**：`FixedPolicy`(teacher_v0)/`AdaptivePolicy`(teacher_v1) 等作为该端口后实现，`policy_version` 进入 plan/session/event payload，支持 rollback=版本切换+重放（B 线已有 policy_version 设计，`OWNER_REPORTED`）。

### 4.6 端口边界能力表（实现时的 test-enforced 静态检查）

| 能力 | Domain | Assessment | Knowledge | Policy | Core |
|---|---|---|---|---|---|
| 读隐藏 rubric/expected | 禁止 | **允许（唯一）** | 禁止 | 禁止 | 禁止 |
| 读 LearnerSnapshot | 禁止 | 禁止 | 禁止 | 只读上下文 | **唯一写者** |
| 写 HistoryEvent | 禁止 | 禁止 | 禁止 | 禁止 | **唯一写者** |
| 写 SessionState | 禁止 | 禁止 | 禁止 | 禁止 | **唯一写者** |
| 写课程/计划 | 禁止 | 禁止 | 只给 eligibility | 只给动作建议 | **唯一写者**（planner） |
| 网络 | 禁止 | 禁止 | 禁止 | 禁止 | 禁止 |
| 真实 Provider | 禁止 | 禁止 | 禁止 | 禁止 | 禁止 |

---

## 5. Interview 教学闭环设计

### 5.1 会话与阶段映射（复用 A 状态机）

Interview 作为一个 objective（`LearningObjective.target_node_ids=[interview.node.<track>]`，`success_criteria` 用掌握度/证据门槛）纳入 A 的 `SessionState` 状态机：

| A phase | Interview 用途 | 动作/事件 |
|---|---|---|
| `DIAGNOSE` | 可选：先用 1–2 个问题探测基线 | `DIAGNOSE` item action；`DIAGNOSIS_COMPLETED` |
| `TEACH` | 呈现主问题 + 项目事实边界 + JD 上下文 | `ACTION_TAKEN`（kind `EXPLAIN` 或 `SOCRATIC_QUESTION`） |
| `PRACTICE`/`ASSESS` | 学习者回答 → AssessmentPort 评分 → 追问 | `RESPONSE_SUBMITTED` → `ASSESSED`；追问动作 `ACTION_TAKEN`（`SOCRATIC_QUESTION`/`ASK_CLARIFICATION`） |
| `UPDATE` | 仅 CORRECT/INCORRECT/PARTIAL 更新 mastery | `MASTERY_UPDATED` |
| `REVIEW` | 五阶段完成后复盘/下一题 | `REVIEW`/`GOAL_COMPLETE` |
| `PAUSED`/`COMPLETE` | 跨域切换/结束 | `SESSION_PAUSED`/`GOAL_COMPLETED` |

**多轮实现要点（DESIGN_ONLY）**：

- 主问题在 `PRACTICE/ASSESS` 阶段以 `pending_item_id=interview.item.<qid>` 呈现；同一题目的多轮追问**不改变 pending item**（仍是同一 item 的多轮证据），每次回答产生一次 `RESPONSE_SUBMITTED` + `ASSESSED`。
- A 现有 engine 一次 submit 后推进 phase；PR4 需 additive 扩展 **`InterviewTurnPolicy`**：允许在同一 pending item 上重复“回答→追问→回答”直到 5 阶段/通过/超限；实现方式二选一（由 B0/Lead 决定）：(a) 新增 core hook（`DomainTurnPolicy`）在 `submit_response` 后返回 next action；(b) 会话层用一个 extension 状态机包住 engine（不改冻结 engine 语义）。**不得**绕过事件写入直接改 SessionState。
- 上限：单题最多 5 轮追问 + 每阶段最多 1 次；超限 → `REVIEW`/`GOAL_COMPLETE`，事件记录 `interaction_limit_reached`。
- 跨域：切换学科必须 `pause_session` 后新建 session（§5.4），不得复用同一 `SessionState` 改 domain。

### 5.2 五阶段追问 + LearnerState 影响（确定性规则）

**阶段推进**（`DESIGN_ONLY` 规则，实现时参数化 + 标 UNCALIBRATED）：

1. 每轮评分后，若 `status ∈ {CORRECT, PARTIAL}` 且加权达到该阶段阈值 → 下一阶段；若 `INCORRECT` → 停留当前阶段（最多重复 1 次，再停留则记录 `stuck` 并给概念级提示）；若 `NEEDS_REVIEW/EVAL_ERROR` → 先澄清/重试（不推进、不计错误）。
2. 阶段顺序固定：`concept → hypothesis → complexity → experiment_design → online_triage`；**不得跳级**；“加速”只能由 policy 基于证据（例如 mastery≥0.7 且连续 2 次 CORRECT 时允许在实验设计/线上定位层减少重复，但必须记录 reason code）。
3. 达到目标：5 阶段走完且最后 2 轮 `CORRECT`，或加权 ≥ 0.8 且无 `NEEDS_REVIEW` → `GOAL_COMPLETE`；否则 `REVIEW` 记录未通过阶段（可再次练习）。

**LearnerState 只读影响**（Core 通过 `PolicyContext` 传入，domain 不直接读 snapshot）：

| 状态信号 | 确定性策略 | 理由 code |
|---|---|---|
| `evidence_count == 0` | 强制从 `concept` 开始，最多 LIGHT 干预 | `INTERVIEW_STAGE_CONCEPT` + `POLICY_NO_EVIDENCE_FLOOR` |
| 连续 `INCORRECT >= 2` | 停留当前阶段；给更具体的概念提示（仍不泄答案）；不升级到 full | `INTERVIEW_STAGE_STUCK` |
| 已掌握节点（mastery≥0.7） | 允许跳过重复的概念解释，但**不跳阶段**；阶段内追问简化 | `INTERVIEW_ACCELERATED` |
| 项目事实缺失（题目 `requires_project_facts` 且历史 payload 无事实引用） | 立即 `ASK_CLARIFICATION`，不评分、不推进 | `PROJECT_FACTS_REQUIRED` |
| `NEEDS_REVIEW` 多数 | 降低开放语义评分依赖：改问更具体子问题；仍不猜 | `INTERVIEW_NEEDS_REVIEW_PROBE` |

**`ASK_CLARIFICATION` 硬边界**：

- 触发：题目要求真实项目经历，但学习者未提供可核验项目事实（规模/指标/来源/角色）。
- 动作：`TeachingAction(kind="ASK_CLARIFICATION")`（需 additive 枚举扩展），内容只请求事实（项目/角色、规模量级、指标与来源、缺失可直说），**不含**任何示例数字/提升百分比。
- 禁止：教练/映射器/LLM 代填“提升 37%”“P99 从 820ms 到 190ms”等；发现 → `MAP-E19`。
- 学习者补充事实后：事实以 learner-owned 引用写入 history payload（`interview_project_facts`），继续阶段；不把事实写进隐藏评分表。

**多轮追问内容来源**：`InterviewDomainPort.follow_up_ladder`（teacher-visible，固定 5 条）；内容不含 rubric 要点/隐藏答案（`MAP-E05`）。

### 5.3 JD 版本变更的影响

- 新计划选择：`KnowledgeSourcePort.latest_jd(jd_id, now)` 返回当前有效版本；plan 的 `policy_version`/`evidence_refs` 固定记录 `jd:<id>@<version_digest>`；JD v1→v2 只影响**之后创建的**计划/会话。
- 运行中会话：`LearnerGoal.objective_id` 不因 JD 变更热改（`MAP-E17`）；可在 REVIEW 记录“岗位上下文已更新，建议新计划”。
- 过期/冲突：JD `valid_until < now` 或无有效版本 → 拒绝新计划（`MAP-E10`）；冲突重叠 → `RECHECK`，人类复核前不选。
- 不产生题目热度：JD 更新不得改变题目排序/热度；不写 mastery；不产生 popularity 事件（设计断言；B 线 `SOURCE_TIERS["jd"]["signals_topic_popularity"]=False`，`OWNER_REPORTED`）。

### 5.4 课程污染防护（Interview + Freshness 联合）

1. 计划生成前必须过 `KnowledgeSourcePort` 门禁：所有被引用的知识版本 `curriculum_eligible=True`；任一 `RECHECK` 引用 → 拒绝计划（`MAP-E08`）。
2. JD 仅作为 objective 选择上下文；不进入 teaching content 的知识节点；不产生热度。
3. `UPDATE` 只能用于新计划；运行中计划不热改；旧计划保留 policy/知识版本指纹，可审计。
4. 所有知识引用以 `Reason.evidence_refs=["knowledge.revision.<id>"]` 出现在计划/动作中；冲突/过期原因以稳定 code 暴露（不泄露正文）。
5. Recheck 队列是**唯一**的冲突/过期去处；人工复核通过后由人工/受控流程把版本标 VERIFIED（不在本 PR 实现）。

### 5.5 统一事件序列（Interview 单题 5 轮示例，`DESIGN_ONLY`）

```
SESSION_STARTED(session, learner, goal, objective, domain="interview_coach", domain_version)
PLAN_CREATED(plan_id, objective_id, policy_version, knowledge_digests[], jd_ref)
DIAGNOSIS_COMPLETED(diagnosis)                                  # 可选
ITEM_PRESENTED/ACTION_TAKEN(kind=SOCRATIC_QUESTION/EXPLAIN, question, reason=INTERVIEW_MAIN)
RESPONSE_SUBMITTED(item, response_digest, turn=1)
ASSESSED(result{status, score, dimensions[ext], failure_modes[ext], scorer_id})
MASTERY_UPDATED(applied, snapshot_revision)                     # 仅 CORRECT/INCORRECT/PARTIAL
ACTION_TAKEN(kind=SOCRATIC_QUESTION, reason=INTERVIEW_PROBE_CONCEPT, stage=1)
RESPONSE_SUBMITTED(turn=2) → ASSESSED → MASTERY_UPDATED ...
... 阶段 2..5 重复；缺失项目事实时 ACTION_TAKEN(kind=ASK_CLARIFICATION, reason=PROJECT_FACTS_REQUIRED)
REVIEW/GOAL_COMPLETED(final_reason)
```

- 所有事件：`event_id` 幂等、`seq` 单调、`created_at` 固定时钟、payload 含 `schema_version/domain/domain_version/policy_version`；隐藏内容绝不入 payload。
- **实现一致性（PARTIAL，B4-05）**：上述 payload 版本字段为设计目标；当前实现只对 session/vertical/plan policy 三类版本做 MAP-E12/E13 fail-closed，**event-level `schema_version` 的消费/拒绝为 `NOT_IMPLEMENTED`**（见 `docs/M1_B_FINAL_INDEPENDENT_REVIEW.md` §8 B4-05 / `docs/M1_B_EVALUATION_REPORT.md` §7）。不得把本行写成已实现 PASS。
- 事件表和字段规范见 §6。

### 5.6 教学理由（Reason codes）

| code | 场景 |
|---|---|
| `INTERVIEW_MAIN_QUESTION` | 开场主问题 |
| `INTERVIEW_PROBE_CONCEPT/HYPOTHESIS/COMPLEXITY/EXPERIMENT_DESIGN/ONLINE_TRIAGE` | 五阶段追问 |
| `INTERVIEW_STAGE_STUCK` | 连续错误停留 |
| `INTERVIEW_ACCELERATED` | 证据充分，阶段内简化 |
| `PROJECT_FACTS_REQUIRED` | `ASK_CLARIFICATION` |
| `RUBRIC_PASSED_GOAL_COMPLETE` | 综合达标结束 |
| `KNOWLEDGE_UPDATE_APPLIED` | 新计划采用 VERIFIED UPDATE |
| `KNOWLEDGE_RECHECK_QUEUED` | 复核队列（不进入教学） |
| `JD_VERSION_SELECTED` / `JD_EXPIRED_BLOCKED` | JD 版本选择/拒绝 |
| `HINT_LEVEL_1/2/3`（+`HINT_LEVEL_4_HUMAN_APPROVED`） | CF/通用提示梯子 |
| `POLICY_NO_EVIDENCE_FLOOR`、`UNCALIBRATED_HEURISTIC` | 证据门/未校准声明 |

`Reason.policy_version` 必须等于产生动作的策略版本；replay 时校验。

---

## 6. CF Hint Ladder 迁移

### 6.1 两套现状对照（SOURCE_INSPECTED）

| 维度 | A 线 `m1_teacher` | B 线 `m1_offline` | 收敛设计 |
|---|---|---|---|
| 提示层级 | domain `teaching_content` 支持 `HINT_L1/HINT_L2/HINT_L3`；`SessionPolicy.max_hint_level=3`；`hint_escalation_threshold=1`；engine `_hint_selection` 按连续 INCORRECT streak 升级 | `HINT_LADDER=("LIGHT_HINT","INVARIANT_HINT","STRUCTURE_HINT","FULL_SOLUTION")`，level 1..4；`EvidenceGate` 按 evidence_count 阶梯（0→L1，1→L2，2–4→L3，≥5→L4 仅显式请求）；`CFTeacher` 默认 clamp 到 STRUCTURE | canonical 只在 **TeacherPolicyPort** 保留一个证据门实现；A 的 L1–L3 内容 kind 作为渲染来源；B 的等级命名作为对外语义；FULL 默认禁止 |
| 升级证据 | 连续 INCORRECT 计数（streak≥1 升一级，max 3） | evidence_count 分层 + error 重复（B `AdaptivePolicy` 另有 repeat-errors≥2/≥4 升 1/2 级） | 统一 gate：`max_level = f(evidence_count, error_streak, requested, human_approved_full)`；参数化、可注入、版本化 |
| FULL 处理 | A 无 FULL 内容 kind（域内容白名单没有）；`SessionPolicy.max_hint_level<=3` 强制 | B 允许显式 L4 请求（仍有 EvidenceGate 上限）；`CFTeacher` 非显式请求时 clamp 到 STRUCTURE | FULL 永不默认；仅 `requested=4 + human_approved_full + evidence≥gate` 三重条件；否则 `MAP-E11` |
| 掌握度 | A `MasteryModel` 唯一写入，只吃 OBSERVED CORRECT/INCORRECT/PARTIAL | B `LearnerModel` 自己写 `LearnerState`（`mastery/error_counts/evidence_count`） | 迁移后 A 唯一写者；B 模型退役为测试/证据生产；双写检测 → `MAP-E20/E25` |
| 阈值校准 | 启发式常量，文档标注非 BKT/未校准（A 架构 §10） | 启发式常量，文档标注 uncalibrated（B hints/evidence gate） | 全部标 `UNCALIBRATED_HEURISTIC`；禁止学习效果声明 |

### 6.2 对应关系（B → A 目标）

| B 等级 | B 内容来源（CF problem `hint_ladder`） | A 目标 `teaching_content` kind | `Reason.code` | 默认 | 备注 |
|---|---|---|---|---|---|
| `LIGHT_HINT` (1) | `problem.hint_ladder["LIGHT_HINT"]` | `HINT_L1` | `HINT_LEVEL_1` | 是（最低干预） | 默认起点 |
| `INVARIANT_HINT` (2) | `problem.hint_ladder["INVARIANT_HINT"]` | `HINT_L2` | `HINT_LEVEL_2` | 需证据 | 连续 INCORRECT ≥1 或 evidence≥1（策略参数化） |
| `STRUCTURE_HINT` (3) | `problem.hint_ladder["STRUCTURE_HINT"]` | `HINT_L3` | `HINT_LEVEL_3` | 需更多证据 | 最高默认级别 |
| `FULL_SOLUTION` (4) | `problem.hint_ladder["FULL_SOLUTION"]` | **无对应 kind** | `HINT_LEVEL_4_HUMAN_APPROVED` | **禁止默认** | 三重条件；否则 `MAP-E11` |

- A 的 `HINT_L1..L3` 只作为**渲染内容**，不承载 B 的四级语义；对外 hint level 语义统一在 `TeachingAction.hint_level`（建议 additive 字段）或 `Reason.code` 中。
- Interview 的五阶段追问**不在**此表内（§3.4）：它们是 SOCRATIC probe，不消耗 hint rung；Interview 域不提供 FULL 内容。

### 6.3 升级证据门（canonical 规则，`DESIGN_ONLY`）

```
effective_level = min(
    requested_level,                                   # default 1; explicit request for CF/interview hint
    evidence_cap(evidence_count, error_streak),        # B EvidenceGate 语义
    hard_max)                                          # hard_max = 3, unless FULL triple condition
if requested_level == 4:
    allowed = human_approved_full and evidence_count >= FULL_MIN_EVIDENCE(=5) and policy allows
    if not allowed: reject MAP-E11 (never silently downgrade to 3 in safety-critical paths; 可返回 3 并标记 refused_full)
```

- `FULL_MIN_EVIDENCE=5`、`STRUCTURE_MIN_EVIDENCE=2`、`LIGHT_MAX_EVIDENCE=0`（B `EvidenceGate` 常量，`OWNER_REPORTED`）作为**可配置默认**进入 policy config；A `hint_escalation_threshold=1`/`max_hint_level=3` 作为另一组默认。合并时保留两组参数但只暴露一个 `policy_version`；变更需新 policy 版本 + replay 证据。
- 升级只由 **AssessmentResult 的观测状态**驱动：`INCORRECT` 连续计数、`PARTIAL` 按 ratio 处理、`NEEDS_REVIEW/EVAL_ERROR` 不计数；`CORRECT/PARTIAL` 重置 streak（A `_consecutive_incorrect` 语义，SOURCE_INSPECTED）。
- **uncalibrated**：上述阈值全部标 `UNCALIBRATED_HEURISTIC`，并在报告/Reason 中说明“非学习效果证据”。

### 6.4 掌握度完整性（禁止 LLM 自证）

1. 唯一写入者：canonical `MasteryModel`（A）。B `LearnerModel`/`LearnerState` 迁移后**不得**再写 canonical；`MAP-E20/E25` 检测双写。
2. 唯一证据来源：`AssessmentPort` 返回的 `CORRECT/INCORRECT/PARTIAL` + `EVIDENCE_SOURCE=OBSERVED`（A `MasteryModel.apply_result` 强制）；`NEEDS_REVIEW`/`EVAL_ERROR` 不改变 snapshot/error_counts（A 现状，SOURCE_INSPECTED）。
3. 禁止“LLM 自称掌握”：教练/解释文本、自评 JSON、`submission["passed"]=True` 等都不进入掌握度；B `CFTeacher` 已忽略提交者自报 passed（`OWNER_REPORTED`），移植时保留该行为并增加端口级断言。
4. B 的 `LearnerState.error_counts` 键空间（skill id/error code）在迁移时显式映射，不改变 A 的错误计数语义；A `INCORRECT` 用 `result.failure_reason or item_id` 作 key——迁移需给出映射表，否则拒绝（`MAP-E02`）。

---

## 7. 统一 Session / 事件表 / Replay

### 7.1 单写者与表归属

| 表（A 现有 SQLite schema v1，SOURCE_INSPECTED） | 写入者 | 本 PR4 设计 |
|---|---|---|
| `schema_meta` / `learners` | Core（唯一） | 不变 |
| `snapshots` | Core `MasteryModel`（唯一） | 不变；B 模型禁止写（`MAP-E20`） |
| `history_events` | Core `LearningHistory`（唯一，append-only） | Interview/CF 事件统一写入；payload 承载域细节 |
| `goals` | Core | Interview/CF goal 共用 |
| `sessions` | Core `SessionState`（唯一） | 域绑定 `(learner_id, goal_id, objective_id)`；跨域需新 session |
| **新增（extension）**：`knowledge_sources` / `knowledge_revisions` / `knowledge_review_queue` | KnowledgeSourcePort（唯一） | 只读给 core；RECHECK 队列 |
| **新增（extension）**：`interview_project_facts`（或 event payload 子结构） | Assessment/Interview 域（learner-owned refs） | 只存事实引用摘要，不存隐藏标签、不自造 |
| **新增（extension，可选）**：`assessment_details`（dimensions/failure_modes 聚合） | AssessmentPort（scorer 侧） | teacher-visible 聚合；隐藏 spec 独立存储 |

禁止：B 线 DB/本地 JSON 作为运行时写入目标；两个 LearnerState 双写；Domain 直接 SQL 读写 core 表。

### 7.2 事件映射表（B → A `HistoryEvent`）

| B 事件/步骤 | A `event_type` | payload 关键字段 | 状态 |
|---|---|---|---|
| `TraceEvent(step="diagnose")` | `DIAGNOSIS_COMPLETED` | `diagnosis`（含 reason/evidence_refs） | `LOSSLESS-ENCODED` |
| `TraceEvent(step="plan")` | `PLAN_CREATED` | `plan_id/objective_id/policy_version/knowledge_digests/jd_ref` | `LOSSLESS-ENCODED` |
| `TraceEvent(step="action")` | `ACTION_TAKEN` | `action` dict、`stage`/`hint_level`、`reason_code` | `LOSSLESS-ENCODED` |
| `TraceEvent(step="response")` | `RESPONSE_SUBMITTED` | `item_id/response_digest/response_kind/turn` | `LOSSLESS-ENCODED` |
| `TraceEvent(step="assess")` | `ASSESSED` | `result`（teacher-visible 部分）+ `item`（自包含）；隐藏 spec 只用 opaque ref | `SCORER-ONLY` 边界 |
| `TraceEvent(step="memory")` | `MASTERY_UPDATED` | `result_id/status/applied/snapshot/policy_version` | `LOSSLESS-ENCODED` |
| `TraceEvent(step="halt")` | `GOAL_COMPLETED`/`REVIEW`/`ERROR`（按 halt_reason） | `halt_reason` | `NEEDS-EXT`（映射表 + reason code） |
| `EvidenceEvent(kind=ANSWER/...)` | `ASSESSED` 或 `RESPONSE_SUBMITTED` + `event_subtype` | `event_subtype`、`observed_score`、`error_codes` | `NEEDS-EXT`（payload subtype；不改记录结构） |
| B `ReplayResult` | A replay 结果（见 §7.5） | 校验 digest/state | `LOSSLESS-ENCODED` |

**版本字段（每个事件 payload 必带）**：

```json
{
  "schema_version": "m1a.v0",
  "domain_id": "interview_coach",
  "domain_version": "0.1.0",
  "policy_version": "m1a.teacher_policy.interview.v0",
  "knowledge_digests": ["knowledge.revision.<id>:<sha256:16>"],
  "jd_ref": "jd:jd-rec-v2@<digest>",
  "event_subtype": "INTERVIEW_RESPONSE"   // 仅在 NEEDS-EXT 场景
}
```

- 事件 payload 的 `schema_version` 必须是 `m1a.v0`；未知 `domain_version/policy_version` → `MAP-E13`，**禁止部分 replay**。
- 事件顺序由 `seq` 定序；`event_id` 幂等；`created_at` 由固定时钟/评估结果提供（replay 不读墙钟）。

### 7.3 跨域任务切换（Interview ↔ CF）

1. Session 绑定 `(learner_id, goal_id, objective_id, domain_id)`；同一 learner 可同时存在多个 session（A `SessionRepository.list_sessions`），但**同一 SessionState 不换域**。
2. 切换流程：`pause_session(old)` → 写 `SESSION_PAUSED`（payload 含 pending_item/phase/turn） → `start_session(new goal/objective, new session_id)` → 新 session 从 `DIAGNOSE/COMPLETE` 开始；learner snapshot 全局共享（不随域清空）。
3. 跨域切换时若旧 session 有 pending item：必须先作答或显式放弃（`SESSION_PAUSED` 允许挂起 pending；恢复后继续）；禁止静默丢弃 pending。
4. 跨域数据隔离：事件/assessment 的 `learner_id/session_id` 不可混用（`MAP-E18`）；result/item 命名空间前缀防止串域。
5. Replay 必须支持“按 learner 全局 + 按 session 分段”：global snapshot 由所有 ASSESSED 事件重建；单 session 状态由该 session 事件重建；跨域切换前后事件序列连续。

### 7.4 版本不兼容明确拒绝

| 场景 | 拒绝码 | 行为 |
|---|---|---|
| 事件 `schema_version != m1a.v0` | `MAP-E13` | 拒绝写入/replay；不部分应用 |
| domain_version 与 session/plan 绑定值不一致（会话中途换域版本） | `MAP-E12` | 拒绝；要求 pause + 新 session |
| policy_version 未知/回放时与当时不一致且无迁移器 | `MAP-E13` | 拒绝 replay，提示所需 policy 版本 |
| B fixture `m1.offline.v0` 之外的版本 | `MAP-E01` | 拒绝导入 |
| 未知枚举/未知 reason code | `MAP-E03` | 拒绝（禁止 default 猜测） |
| 迁移/roundtrip checksum 不一致 | `MAP-E21` | 整批回滚 |

**迁移与回退**：一次性离线导入（只读源，写新表），不原地改 v0；回退 = 丢弃新增表/删除导入行，不改 core 表；部署前禁止自动迁移真实 learner db（B0.3）。

### 7.5 Replay 算法（统一日志重建）

1. 读取事件：按 `(learner_id, seq)` 升序；校验 `event_id` 唯一、`seq` 连续（`MAP-E14`）、payload 版本兼容（`MAP-E13`）。
2. 重建 `LearnerSnapshot`：A `MasteryModel.rebuild_snapshot(learner_id, events, items_by_id)` 重放 self-contained `ASSESSED`（payload 内嵌 `result`+`item`），去重 `result_id`；校验与持久 snapshot **字段级相等**（含 revision/updated_at）。
3. 重建 Session 轨迹：按事件顺序重放 `SESSION_STARTED/ACTION_TAKEN/RESPONSE_SUBMITTED/ASSESSED/SESSION_PAUSED/SESSION_RESUMED/GOAL_COMPLETED`；`phase/turn/pending_item` 与持久 `SessionState` 一致；interview 的追问 stage 由 `ACTION_TAKEN.reason_code` 序列推导。
4. 重建 assessment 列表：`ASSESSED.payload.result` → `AssessmentResult.from_dict`（严格）；`scorer_id/scorer digest` 校验；隐藏 spec 不参与 replay（replay 只用结果，不重跑评分；如需重评分，必须用同一隐藏 spec 版本与哈希）。
5. 重建知识上下文：`PLAN_CREATED`/`ACTION_TAKEN` 中的 `knowledge_digests/jd_ref` 必须能在 KnowledgeSourcePort 解析且状态仍为 VERIFIED；解析失败 → replay 报告 UNVERIFIED，不伪造可用。
6. **确定性**：两次 replay 的 canonical JSONL digest（sha256）相同；禁止读墙钟/随机；固定 seed。
7. Replay 失败语义：任一步校验失败 → 整体 replay 失败（fail closed），禁止“尽量恢复”产生半状态；错误码 + 原始事件 id 输出（不含隐藏内容）。
8. B 线 `replay_trace`（`OWNER_REPORTED`：`m1_offline/evaluation/harness.py`，按 `payload.seq` 连续/loop_id 过滤重建）作为**行为参照**迁移为统一 replay 的测试用例；B 不再拥有独立 replay 运行时。

---

## 8. PR4 测试矩阵草案（B4-01/02/03 + 回归）

> **全部条目初始状态 `NOT_RUN`**（本文档只做设计；本轮未实现、未执行、未产生任何测试结果）。Evidence level 采用 `TEST_EVIDENCE_MATRIX.csv` 词汇；不得把计划当 PASS。表内“计划断言”是后续 Implementer 的验收标准。

### 8.1 B4 主项

| case_id | 目标 | 计划设置（synthetic fixtures） | 计划断言 | evidence | 状态 |
|---|---|---|---|---|---|
| **B4-01** | 统一 CF 闭环（Two synthetic CF learners） | 2 个 learner fixture（weak/intermediate/advanced 取 2，如 `learner_weak_beginner` + `learner_advanced`）；CF 14+ 题；canonical core session/event 表 | 同 canonical mastery 与 session journal；两 learner 动作序列/计划不同且可解释；`seq` 连续/事件幂等；snapshot 由事件 rebuild 字段级相等；hint 升级只由观测证据；无 B 线双写 | E2E-MOCK | NOT_RUN |
| B4-01a | CF Hint Ladder 升级证据门 | 连续 INCORRECT 脚本 | L1→L2→L3 按 gate 升级；`FULL_SOLUTION` 默认绝不出现；无人类批准时 `requested=4` 被拒（`MAP-E11`） | NEGATIVE + E2E-MOCK | NOT_RUN |
| B4-01b | CF 错误/异常不污染 mastery | 死循环 TLE / 语法 RE / expected 伪造 | `EVAL_ERROR` 不改变 snapshot/error_counts；`INCORRECT` 才允许下降；B1 完成后才开放 CODE 正向路径 | NEGATIVE | NOT_RUN |
| **B4-02** | Interview 闭环（Two synthetic learners, JD v1→v2） | 2 个 interview learner fixture：A 有项目事实，B 缺项目事实；JD v1/v2；4 维 rubric | A 5 阶段按序推进且每动作有 Reason；B 缺事实 → `ASK_CLARIFICATION` 且内容不含编造数字；补充事实后继续；4 维分独立、确定性；`NEEDS_REVIEW` 无 mastery 变化；scorer_id 来自 AssessmentPort | E2E-MOCK | NOT_RUN |
| B4-02a | JD v1→v2 影响 | 同一 learner 先后 v1/v2 计划 | 运行中 session objective 不变；新计划引用 v2；v1/v2 移植 checksum 可回读；JD 变更不产生题目热度/掌握度变化 | DETERMINISTIC | NOT_RUN |
| B4-02b | 项目事实边界/不代填 | 缺事实回答、构图/诱导输入 | 不得出现“提升 37%/规模”等教练编造；`MAP-E19` 负例；事实只来自 learner 引用 | NEGATIVE | NOT_RUN |
| **B4-03** | Freshness 门禁（expired/conflict/unauthorized cannot silently enter teaching） | B 线 9 组 knowledge fixture（KEEP2/UPDATE2/RECHECK5）；JD 层 | 9/9 分类与 B 线一致；RECHECK 绝不进计划/课程（`MAP-E08/09`）；JD 层 UPDATE 不改课程；审计 notes 含 published_at/observed_at 差异；两次运行确定性 | E2E-MOCK | NOT_RUN |
| B4-03a | 课程污染防护 | RECHECK 被 planner 引用的人为场景 | 计划生成被拒；无事件写入课程；复核队列有记录；replay 不显示知识写入 | NEGATIVE | NOT_RUN |
| B4-03b | UPDATE 授权链 | 官方文档 UPDATE+VERIFIED | 仅新计划 materialize；运行中计划不变；旧计划可审计版本指纹 | DETERMINISTIC | NOT_RUN |

### 8.2 跨域 / 版本 / 隔离 / 合规（PR4 必测）

| case_id | 目标 | 计划设置 | 计划断言 | evidence | 状态 |
|---|---|---|---|---|---|
| B4-04 | 跨域切换不中断 Session 状态 | Interview 会话（暂停/pending）→ CF 新会话 → 回到 Interview | 旧 session 可 resume 且 pending 保持；learner snapshot/revision 连续；事件 `seq` 全局连续；跨域结果不串 | E2E-MOCK | NOT_RUN |
| B4-05 | 版本拒绝 | 伪造 `m1.offline.v1` 事件/fixture、未知枚举、domain_version 中途变更 | `MAP-E01/03/12/13` 稳定拒绝；无部分写入；错误信息不含隐藏内容 | NEGATIVE | NOT_RUN |
| B4-06 | hidden 不泄漏 | 隐藏题集（7 题）+ hidden scoring + 注入文档（4 条） | teacher-visible 类型/事件 payload/trace/日志/导出 JSON/诊断中无 rubric points/隐藏 id/expected；注入文档只作为 DATA_ONLY 测试数据，不进入事件；静态扫描 + 运行时扫描 | NEGATIVE | NOT_RUN |
| B4-07 | 无网络/真实数据/Provider | 静态扫描 + 运行时 mock | 无 `httpx/requests/urllib/socket` 等网络 import；无真实招聘站点/简历/人名；runtime 调用 0 次（mock）；fixtures synthetic/CC0 | STATIC + OS（仅离线） | NOT_RUN |
| B4-08 | 单写者/双写检测 | 尝试让 B model 与 A model 同时写 snapshot | `MAP-E20/E25` 拒绝并审计；事件/快照无重复 mastery | NEGATIVE | NOT_RUN |
| B4-09 | 迁移 checksum/roundtrip | B 线 interview/knowledge fixtures 全量映射 | LOSSLESS 字段 roundtrip 一致；NEEDS-EXT 字段可回读；拒绝码用例覆盖；manifest checksum 两次运行一致 | DETERMINISTIC | NOT_RUN |
| B4-10 | 隔离/回归 | 既有 A 套件 + 新集成套件 | A 现有测试（`OWNER_REPORTED` 536）不被修改且通过；B 历史 365 保留历史冻结，不合并计数；新增集成 suite 单独报告；无 M0 import/修改 | DETERMINISTIC + STATIC | NOT_RUN |

### 8.3 测试设计约束（Reviewer 检查点）

1. 不能用 mock 抛异常替代真实 crash（B2）；不能把计划矩阵写成 PASS；每个负例给出稳定 code 与“无部分状态”断言。
2. hidden 泄漏扫描必须扫描**运行时导出的 JSON/trace/日志**，不只 AST/源码字符串（B-Q5）。
3. 所有证据标注 `MOCK/DETERMINISTIC/HUMAN_REVIEWED/NOT_VERIFIED` 之一；本 PR 只允许 `DESIGN_ONLY`/`NOT_RUN`。
4. 冻结 PR4 实现 SHA 后再跑 B4-01..10；报告单独列出“本 PR 新增/合并/历史引用”的数字，不把 536+365 相加。
5. 真实恶意代码/OS 隔离示例只在 B1 的隔离 Worker 内执行，不在主机直跑。

---

## 9. 明确不做（硬边界）

1. 不做真实招聘网站抓取、真实个人简历/招聘 JD 数据、真实候选人评估；所有 JD/知识/题目为 synthetic/CC0-1.0（合成域名 `.invalid`）。
2. 不做真实网络/Provider/LiveGate/API Key/付费请求；不声称“本周热点已真实更新”；Freshness 仅用静态带时间戳 synthetic knowledge 证明门禁。
3. 不实现双写、不自动迁移真实 learner DB、不改 `m1_offline` 运行时/数据库作为第二 Core；B 线产物只作为只读 vertical 源与历史证据。
4. 不修改 `m1a.v0` 冻结语义；扩展必须走 B0 ADR + 维护者签收；本文只提建议（列 §10 待裁决）。
5. 不做 B1/B2/B3 的工作（Judge OS 隔离/事务 crash recovery/scoped idempotency）；PR4 在这些修复完成后才能进入集成验收。
6. 不做真实学习效果/教学有效性声明；掌握度阈值/证据门标 `UNCALIBRATED`；开放式评分最多 `NEEDS_REVIEW`。
7. 不做生产鉴权/多租户/真实用户隔离承诺；不把 M1-B 结果表述为产品可用性。
8. 不执行任何真实测试、不产生 PASS；本 PR 仅设计文档 + commit。

---

## 10. 未决问题（需 LeadB/Reviewer 裁决）

| # | 问题 | 建议方案 | 备选/影响 |
|---|---|---|---|
| Q1 | `SOCRATIC_QUESTION`/`ASK_CLARIFICATION` 在 `m1a` 无枚举值 | 按 D12 **加法式**新增两个 `TEACHING_ACTION_KIND` 值（记录 ADR） | 备选：映射为 `HINT`+Reason code（语义降级，UI/审计难区分；需 `MAPPED-DEGRADED` 标记） |
| Q2 | Interview 4 维分数/失败模式/隐藏计数无 A 字段 | AssessmentPort sidecar（不改 v0），`evidence_refs` 引用 checksum；或 additive optional 字段（推荐，若 UI/报告需要） | sidecar 更保守但查询/导出需 join；QA 需确认 b-eval/报告消费方式 |
| Q3 | `TeachingAction.hint_level` 无 A 字段 | additive optional `hint_level: int | None`（D12） | 备选 Reason code 编码（lossy）；影响 CF/Interview 可解释性 |
| Q4 | Interview 多轮追问如何与冻结 engine 的“一 item 一次 submit”调和 | additive `DomainTurnPolicy`/interview session adapter（core hook），不改冻结语义 | 备选：每个追问轮次建模为独立 item（丢失上下文/多轮语义，不推荐） |
| Q5 | JD 时间语义（`valid_from` vs `published_at`） | KnowledgeSourcePort JD 视图带 `timestamp_semantics="VALIDITY_WINDOW"`，禁止塞 `published_at` | 备选：新增 `JdVersion` extension 类型（更清晰但新增类型面） |
| Q6 | `OPEN_ANSWER` item type 缺失 | 加法式新增 item_type 值；否则映射 `SHORT_ANSWER` 需显式降级标记 | 影响回答语义/评分模式 |
| Q7 | B 线 mastery/learner model 退役节奏 | 迁移后 A 单写；B 模型仅测试/证据 | 若 B0 另选 canonical，需反转并重写本文 §3/§5 |
| Q8 | 复核队列的人工流程/授权 | KnowledgeSourcePort 提供队列 + `curriculum_eligible` 门禁；人工审批流程未来实现（UNVERIFIED） | 本 PR 不实现审批，只保证“不能静默” |

---

## 11. 完成定义（本 PR4 设计交付的验收）

> 本节勾选的是**设计文档内容项**是否已覆盖，**不是**测试 PASS；所有测试条目见 §8 并保持 `NOT_RUN`。

- [x] `docs/M1_B_INTERVIEW_FRESHNESS_MAPPING.md` 唯一新增文件，`DESIGN_ONLY` 状态声明、无实现/测试改动。
- [x] 数据映射：Interview 问题/答案/4 维 rubric/5 阶段追问、JD v1/v2、KnowledgeSource、Freshness 三态逐字段覆盖，含 LOSSLESS/NEEDS-EXT/REJECT 与稳定拒绝码。
- [x] 四端口方案（DomainAdapter/AssessmentPort/KnowledgeSourcePort/TeacherPolicyPort），含隐藏材料归属、单写者、FULL 默认禁止、uncalibrated 声明。
- [x] Interview 闭环（多轮五阶段、LearnerState 影响、`ASK_CLARIFICATION`、JD 版本、冲突/过期不静默、Replay）。
- [x] CF Hint Ladder LIGHT→INVARIANT→STRUCTURE→FULL 与 A `HINT_L1..L3` 对应、升级证据门、FULL 三重门、掌握度防火墙。
- [x] 统一 Session/事件表/Replay、跨域切换、版本拒绝。
- [x] PR4 测试矩阵草案（B4-01/02/03 + 回归/负例），全部 `NOT_RUN`，不使用伪造 PASS。
- [x] 明确不做与未决问题清单。
- [ ] 独立 Reviewer（Reviewer-Policy）静态审查与 LeadB 裁决（本 PR 之后）。

## 12. 参考（索引）

- A：`docs/M1_ARCHITECTURE.md`、`docs/M1_ADR_001_DOMAIN_CONTRACTS.md`、`docs/M1_NEXT_PHASE_PLAN.md`、`docs/M1_EVALUATION_REPORT.md`、`m1_teacher/contracts/**`、`m1_teacher/session/engine.py`、`m1_teacher/learner/{model,history}.py`、`m1_teacher/assessment/scorer.py`、`m1_teacher/domains/cf_binary_search.py`、`m1_teacher/extensions/interfaces.py`。
- B：`/root/at-m1-offline/m1_offline/types.py`、`m1_offline/interview/{coach,rubric}.py`、`m1_offline/freshness.py`、`m1_offline/teaching_policy.py`、`m1_offline/cf/teacher.py`、`m1_offline/evaluation/harness.py`、`docs/m1/INTERVIEW_COACH_SPEC.md`、`docs/m1/FRESHNESS_AND_SOURCE_POLICY.md`、`fixtures/m1/interview/**`、`fixtures/m1/cf/**`。
- 交接：`/root/leadb_zip/{START_HERE.md,02_LEADB_AGENT_HANDOFF.md,AUDIT_REQUESTS.md,COMMON_REVIEW_AND_ROADMAP.md,TEST_EVIDENCE_MATRIX.csv}`。
- 数据矩阵：`TEST_EVIDENCE_MATRIX.csv` 的 `B4-01/B4-02/B4-03`（初始 `NOT_RUN`）。

---

*本文档只做设计（DESIGN_ONLY），不含实现或实测结论；所有测试条目为计划值并标记 `NOT_RUN`，引用他人测试数字均标 `OWNER_REPORTED`，不构成本轮验收证据。*
