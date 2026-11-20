# M1-B Ports Design（B-PR0）

| 字段 | 值 |
|---|---|
| 文档状态 | **DRAFT / DESIGN_ONLY**（未冻结；等待维护者签收；**未实现、未集成、未验证**） |
| 证据类别 | 仅 `SOURCE_INSPECTED`（冻结源码阅读）与 `DESIGN_ONLY`（端口/迁移设计提案） |
| 基线 | `main=3e7afee`；A 线 `work/m1a-mvp=4706250`；B 线 `work/m1-offline-design=290c577` |
| Canonical 前提 | 见 `docs/M1_B_CONVERGENCE_ADR.md` §6：`m1_teacher` 为唯一 TeacherCore；`m1_offline` 为 CF/Interview/Freshness vertical |
| 范围 | 设计并冻结 4 个移植端口：`DomainAdapterV1`、`AssessmentPort`、`KnowledgeSourcePort`、`TeacherPolicyPort`；每项的 I/O schema、错误语义、信任边界、确定性/roundtrip 规则、迁移 checksum、PR 落位 |
| 明确排除 | 不写实现代码；不修改 `m1a.v0`/`m1.offline.v0` 既有字段/枚举/方法；不联网、不接 Provider/Key；不迁移真实 learner DB |
| 交付状态 | 本文是 B-PR1..B-PR5 的接口输入；B-PR0 结束时状态 = 文档完成、等待独立 Reviewer 静态预审（**不声称 DONE/PASS 验收**） |

---

## 1. 端口总览与分层

```
┌───────────────────────────────────────────────────────────────────────┐
│ Trusted canonical TeacherCore (m1_teacher, m1a.v0)                     │
│  SessionEngine → DiagnosticEngine/CurriculumPlanner → LearningHistory  │
│  ── repo(SQLite: snapshots/events/sessions/goals)  ← 唯一写入者        │
│                                                                        │
│  Ports (本文件冻结；新增模块 m1_teacher/ports/**, additive only):      │
│    DomainAdapterV1   AssessmentPort   KnowledgeSourcePort              │
│    TeacherPolicyPort                                                   │
└───────────────▲───────────────────────▲──────────────────▲─────────────┘
                │ teacher-visible data   │ verdict (trusted)│ decisions
┌───────────────┴───────────────────────┴──────────────────┴─────────────┐
│ Vertical layer (m1_offline 资产 / 适配层；不可写 canonical 状态)       │
│  CF: hint ladder + judge logic   Interview: 5-stage ladder + rubric    │
│  Freshness: KEEP/UPDATE/RECHECK  RuntimePort(mock, vertical 内部)      │
└────────────────────────────────────────────────────────────────────────┘
```

信任分层（本阶段固定）：

| 层 | 组件 | 可信性 | 允许看到 hidden scoring/expected | 允许写 canonical 状态 |
|---|---|---|---|---|
| T0 Trusted Core | `SessionEngine`、`LearningHistory`、`MasteryModel`、`SqliteRepository`、canonical planner/diagnostic | 可信 | 否（只有 T1 scorer 边界内） | **是（唯一写入者）** |
| T1 Trusted Scorer | `TrustedJudgeSupervisor`/`AssessmentPort` 可信端、hidden spec、expected 比较、最终 verdict | 可信（B-PR1 重做） | **是（仅此层）** | 否（只产出 `AssessmentResult`） |
| T2 Untrusted Worker | `UntrustedExecutionWorker`（执行不可信 CODE） | **不可信** | **否** | 否 |
| T3 Vertical | CF/Interview/Freshness 适配层与 fixtures（synthetic） | 半可信输入（内容经校验） | 否 | **否** |
| T4 Untrusted input | interview `untrusted_docs`、未来外部知识/模型文本 | **不可信**（DATA_ONLY） | 否 | 否 |

端口原则：端口是**纯函数边界**——同一输入 + 同一版本 → 同一输出；端口不持久化、不产生副作用；
所有持久化仍由 T0 通过 repository 事务完成（B-PR2 冻结单事务/episode 合同）。

---

## 2. 端口通用规则

### 2.1 记录与版本

- 新增端口记录使用新 schema 版本 **`m1b.ports.v0`**（`BASE_SCHEMA_VERSION` 仍为 `m1a.v0`；端口记录是
  **additive 新类型**，不改变既有 `m1a.v0` 记录）。
- 端口记录用 dataclass 实现（B-PR1/B-PR4 新增模块，计划路径 `m1_teacher/ports/records.py`），继承/复用
  `m1_teacher.contracts.types` 的严格序列化风格：`schema_version` 首键、`to_dict/from_dict` 严格
  （未知字段/错版本/非法枚举/越界 → `ValidationError`）、`created_at` 由调用方注入（决定论测试用固定值）。
- 既有 v0 记录（`KnowledgeNode`、`AssessmentItem`、`AssessmentResult`、`TeachingAction`、`Reason`、
  `LearnerSnapshot`、`SessionState`、`LearnerGoal`、`HistoryEvent`、`EvidenceReference`）**原样复用**，
  不新增/删除字段。

### 2.2 错误语义统一（fail-closed）

- 端口输入非法 → `ValidationError` / 端口专属 `M1AError` 子类（`code` 见各端口）；
- 资源缺失（fixture/spec/vertical 未注册）→ `NotFoundError` 或端口码（如 `ASSESSMENT_SPEC_NOT_FOUND`）；
- 不允许静默降级为“空结果/通过”；未知枚举/未知字段一律拒绝；
- 端口码沿用 `m1a` 的错误码风格（大写下划线、append-only）：

| 通用码 | 含义 |
|---|---|
| `PORT_INPUT_INVALID` | 端口入参 schema/类型不合法 |
| `PORT_NOT_CONFIGURED` | 端口实现未注入（fail closed，不返回空默认） |
| `PORT_VERSION_UNSUPPORTED` | schema_version/vertical_version 不兼容 |
| `PORT_UNTRUSTED_INPUT_REJECTED` | T4 不可信输入试图承担指令/评分职责 |
| `PORT_ACTION_KIND_UNSUPPORTED` | vertical 请求 canonical 不接受的 action kind |
| `PORT_FULL_SOLUTION_BLOCKED` | 未满足显式批准+证据门时请求 FULL_SOLUTION |

### 2.3 确定性 / roundtrip 规则（可测）

1. **序列化往返**：`Record.from_dict(record.to_dict()) == record`，且
   `canonical_json(to_dict())` 逐字节稳定（见 §6.1 canonical JSON 规则）。
2. **决定论**：同一输入（固定 `created_at`/seed/policy_version）→ 输出字段逐字节相同；端口不得读取
   墙钟、随机数、环境变量、网络；任何时间字段由调用方显式提供。
3. **幂等输入**：同一 `job_id`/`claim_id`/`context_id` + 同一输入 digest 重放 → 同一输出
   （端口本身无状态；幂等持久化由 B-PR3/Repository 负责）。
4. **无隐藏泄漏**：端口输出 JSON 不得包含 expected/answer/correct/solution 内容（B-PR1 泄漏扫描冻结项
   B1-06）；`AssessmentPort` 输出仅 `AssessmentResult` 五态 + 聚合计数/错误码。
5. **失败可分类**：每条失败路径有稳定错误码，不得用空字符串/布尔 false 代替错误。

---

## 3. 四个冻结端口

### 3.1 `DomainAdapterV1`（vertical 领域插件；扩展 v0 DomainAdapter）

**目的**：在**不改** v0 `DomainAdapter` 的前提下，让 CF/Interview/Freshness vertical 以统一方式提供
知识/目标/题目/教学内容/vertical 资产；canonical core 只依赖端口，不 import B 线具体类。

**位置（计划）**：`m1_teacher/ports/domain_adapter.py`；`DomainAdapterV1` 是 v0 `DomainAdapter`
（`m1_teacher/contracts/domain.py:24`）的 **additive 扩展**（新 Protocol，v0 保持冻结）。

**Protocol 签名（DESIGN_ONLY）**

```python
@runtime_checkable
class DomainAdapterV1(Protocol):
    # v0 兼容（签名/语义不变）
    domain_id: str
    domain_version: str
    def knowledge_nodes(self) -> list[KnowledgeNode]: ...
    def prerequisite_edges(self) -> list[PrerequisiteEdge]: ...
    def objectives(self) -> list[LearningObjective]: ...
    def assessment_items(self, node_id: str | None = None) -> list[AssessmentItem]: ...
    def teaching_content(self, node_id: str, kind: str) -> str: ...
    def validate(self) -> None: ...

    # 新增（additive；v0 调用方无需感知）
    vertical_id: str        # "cf_binary_search" | "interview_coach" | "knowledge_source"
    vertical_version: str   # vertical 自身内容/策略版本（如 "m1.offline.cf.v0"）
    def capabilities(self) -> tuple[str, ...]:
        """("assessment:deterministic","hint_ladder","interview_ladder","freshness") 子集。"""
    def vertical_assets(self) -> VerticalAssets:
        """vertical 专属、teacher-visible 的内容资产（见下 schema）。"""
```

**`VerticalAssets` dict schema（`m1b.ports.v0`）**

| 字段 | 类型 | 必填 | 约束 | 说明 |
|---|---|---|---|---|
| `schema_version` | str | 是 | `"m1b.ports.v0"` | 端口记录版本 |
| `vertical_id` | str | 是 | 非空，匹配 adapter | 与 `DomainAdapterV1.vertical_id` 一致 |
| `hint_ladders` | dict[str, dict] | 否 | 键=node_id；值含 `LIGHT/INVARIANT/STRUCTURE/FULL` 四个非空 str（FULL 可选存在但默认不可发出） | CF Hint Ladder 内容 |
| `follow_up_ladders` | dict[str, list[dict]] | 否 | 键=item_id；值为 stages 列表（`stage`/`prompt`/`rationale_code`，5 阶段：`concept→hypothesis→complexity→experiment_design→online_triage`） | Interview 追问内容 |
| `knowledge_claims` | list[KnowledgeClaim] | 否 | 见 §3.3 schema；仅 freshness vertical 提供 | 知识来源候选 |
| `untrusted_doc_refs` | list[str] | 否 | 仅引用 fixture 路径/ID；**内容为 DATA_ONLY** | Interview 注入文档引用 |
| `created_at` | str | 是 | 调用方注入 UTC ISO-8601 `Z` | 决定论 |

- **禁止** `VerticalAssets` 携带 hidden scoring/expected/answer 内容；校验器必须对 canonical JSON 做
  forbidden-token 扫描（`FORBIDDEN_TEACHER_FIELD_TOKENS` + `expected/answer/correct/solution`）。
- `teaching_content(node_id, kind)` 仍只返回 teacher-visible 模板（沿用 A 契约：未知 kind → `ValidationError`；
  未知 node → `NotFoundError`）。
- `assessment_items()` 只返回 teacher-visible `AssessmentItem`（v0 无 answer 字段）；hidden spec 由
  `AssessmentPort` 私有持有，不经 adapter 暴露。

**错误语义**

| code | 触发 |
|---|---|
| `PORT_DOMAIN_INVALID` | adapter 自检失败（图/目标/内容不一致） |
| `PORT_VERSION_UNSUPPORTED` | `vertical_version` 与 core 支持范围不符 |
| `PORT_UNTRUSTED_INPUT_REJECTED` | `VerticalAssets` 出现 hidden/答案形字段或 DATA_ONLY 内容被当作指令 |
| `ValidationError`/`NotFoundError` | 沿用 v0 语义（未知 kind/node、非法 enum、缺失 fixture） |

**Owner / 信任**：T3 vertical（半可信输入）；禁止写 canonical 状态；不得读 hidden scoring。
**确定性/roundtrip**：`VerticalAssets` 往返无损；相同 fixture 树 → `canonical_json` sha256 稳定；
`validate()` 不产生副作用；不得枚举目录读取非白名单文件（沿用 A CF adapter 的 allow-list 设计）。

---

### 3.2 `AssessmentPort`（可信评分边界；B-PR1 核心）

**目的**：统一“一道题 + 学习者作答 → `AssessmentResult`”的**可信**入口，取代 A 当前
`DeterministicScorer`（`m1_teacher/assessment/scorer.py:217`）与 B `CFJudge`（`m1_offline/cf/judge.py:181`）
两套各自执行不可信代码的现状（COMMON B-01）。本端口把 **expected/hidden 与 verdict 放在可信端**。

**位置（计划）**：`m1_teacher/ports/assessment.py`；实现由 B-PR1 交付（`TrustedJudgeSupervisor` +
`UntrustedExecutionWorker`）。

**Protocol 签名（DESIGN_ONLY）**

```python
@runtime_checkable
class AssessmentPort(Protocol):
    scorer_id: str                      # 不可伪造的 trusted scorer 身份（含版本）
    def assess(self, job: AssessmentJob) -> AssessmentResult: ...
```

**`AssessmentJob` dict schema（`m1b.ports.v0`）**

| 字段 | 类型 | 必填 | 约束 | 说明 |
|---|---|---|---|---|
| `schema_version` | str | 是 | `"m1b.ports.v0"` | — |
| `job_id` | str | 是 | 非空；建议确定性（`sha256(canonical_inputs)`） | 幂等键的一部分（B-PR3 再绑定 scope） |
| `learner_id` / `session_id` / `item_id` | str | 是 | 非空 | scope 三元组；B-PR3 扩展 `turn_id`/`attempt` |
| `turn_id` | int | 是 | ≥0 | 会话轮次（B-PR2/B-PR3 使用） |
| `attempt` | int | 是 | ≥1 | 同一轮重试计数（EVAL_ERROR 重试可见） |
| `response_kind` | str | 是 | `CODE` / `MCQ` / `SHORT_ANSWER` / `TEXT` | 与 `ITEM_TYPE` 对齐 |
| `response` | str | 是 | 非空；长度上限由 trusted 层校验（如 64 KiB） | learner 作答原文；worker 只收到它 + 单 case 输入 |
| `item_digest` | str | 是 | `sha256(canonical_json(item.to_dict()))` | 防篡改/防学科漂移 |
| `trusted_fixture_test_only` | bool | 是 | M1 阶段**必须 true** | 表示调用仅用于 synthetic fixture/内部测试；false → `UNTRUSTED_CODE_EXECUTION_BLOCKED` |
| `timeout_s` | float | 否 | `0 < t <= 5.0` | 单次执行硬预算（§B1 要求） |
| `created_at` | str | 是 | 调用方注入 | 决定论 |

> `AssessmentJob` **不得**携带 expected/tests/hidden spec/answer。hidden spec 仅由 T1 可信端按
> `(domain_id, item_id, scoring_spec_ref)` 读取；`scoring_spec_ref` 仍留在 trusted 侧，不进入 worker。

**输出**：v0 `AssessmentResult`（`m1_teacher/contracts/types.py:683`，五态
`CORRECT/INCORRECT/PARTIAL/NEEDS_REVIEW/EVAL_ERROR`；`scorer_id` = trusted 身份；`evidence_refs` 只含
`item:<id>`/`spec-sha256:<前16>`/聚合计数，不含 expected）。可附加 `AssessmentAudit`（可选 sidecar，
仅 trusted 可写、仅聚合计数/错误码）。

**信任边界（强制）**

| 组件 | 可见 | 不可见/禁止 |
|---|---|---|
| `TrustedJudgeSupervisor`（T1） | hidden spec、expected、scoring config、learner code、最终 verdict | 外界不可调用其内部比较函数 |
| `UntrustedExecutionWorker`（T2） | 单个 case 的输入、目标函数名/签名、learner code、受限环境 | **expected/hidden spec/answer、可信结果文件路径、主机私有目录、网络** |
| worker 的 `actual`/异常/退出码 | 作为**不可信**证据返回 T1 | 不得作为最终 PASS |
| teacher-visible 输出 | `AssessmentResult`（状态+聚合） | hidden 用例内容/expected/worker 原始输出 |

**错误语义 / 状态映射（B-PR1 冻结）**

| 情形 | `AssessmentResult.status` | `failure_reason`（示例稳定码） | 说明 |
|---|---|---|---|
| trusted 端基础设施错误（spec 缺失/损坏、worker 启动失败、超时清理失败） | `EVAL_ERROR` | `JUDGE_INFRA_ERROR:<code>` | 不计学习者错误、不降 mastery |
| learner 代码超时 | `INCORRECT` | `STUDENT_TLE` | 学生 TLE，区别于 infra |
| 语法/导入/缺函数 | `INCORRECT` | `STUDENT_RE` / `STUDENT_SYNTAX_ERROR` / `STUDENT_MISSING_FUNCTION` | 由 T1 比较/分类 |
| 用例结果错误 | `INCORRECT`/`PARTIAL` | `CASES_FAILED:<n>/<m>` | 聚合计数，不泄露 expected |
| 开放题无法可靠判定 | `NEEDS_REVIEW` | `SEMANTIC_UNVERIFIABLE` | 不得假装 CORRECT |
| 不可信 CODE 接口未启用（B-PR1 前默认） | `EVAL_ERROR` | `UNTRUSTED_CODE_EXECUTION_BLOCKED` | 硬阻断默认支持 |
| 入参非法/越界 | 抛 `ValidationError`/`PORT_INPUT_INVALID` | — | fail-closed，不产出结果 |

**Owner / 信任**：T1（可信）；
**确定性/roundtrip**：`AssessmentResult`沿用 v0 roundtrip；同一 job（去 `created_at`）→ 同 result
（infra 错误除外，且必须记录错误码）；hidden spec 的 sha256 写入 `evidence_refs`，不进正文。

### 3.3 `KnowledgeSourcePort`（Freshness / 知识时效；B-PR4 接入）

**目的**：把 B `FreshnessManager.classify`（`m1_offline/freshness.py:186`）的 KEEP/UPDATE/RECHECK
语义接入 canonical 课程候选，但**绝不**直接改课程/学习者状态；只有 planner 显式采用且
`curriculum_eligible()` 为 true 的知识才可能进入下一步计划。

**位置（计划）**：`m1_teacher/ports/knowledge_source.py`；由 B-PR4 的 freshness 适配层实现。

**Protocol 签名（DESIGN_ONLY）**

```python
@runtime_checkable
class KnowledgeSourcePort(Protocol):
    policy_version: str
    def classify(self, previous: KnowledgeClaim, current: KnowledgeClaim) -> KnowledgeDecision: ...
    def curriculum_eligible(self, decision: KnowledgeDecision) -> bool: ...
```

**`KnowledgeClaim` dict schema**

| 字段 | 类型 | 必填 | 约束 |
|---|---|---|---|
| `schema_version` | str | 是 | `"m1b.ports.v0"` |
| `claim_id` | str | 是 | 非空、稳定 |
| `source_id` / `uri` / `publisher` | str | 是 | 非空；synthetic fixture 使用 `.invalid` 域名 |
| `published_at` / `observed_at` | str | 是 | UTC ISO-8601 `Z`；显式区分“来源发布时间”与“观测时间” |
| `valid_until` | str \| None | 否 | UTC ISO-8601 `Z` |
| `confidence` | float | 是 | `[0,1]` |
| `claim_status` | str | 是 | `VERIFIED/REPORTED/CONFLICT/EXPIRED/UNKNOWN`（沿用 B `CLAIM_STATUS_VALUES`） |
| `trust_tier` | str | 是 | `official_document/paper/engineering_blog/jd/community/mirror/unknown` |
| `content_ref` | str | 是 | 本地 fixture 引用（**不得**是网络 URL 抓取指令） |
| `content_digest` | str | 是 | `sha256(canonical content)`；用于 KEEP 判定 |
| `untrusted` | bool | 是 | 外部/注入来源为 true（DATA_ONLY） |
| `created_at` | str | 是 | 调用方注入 |

**`KnowledgeDecision` dict schema**

| 字段 | 类型 | 必填 | 约束 | 说明 |
|---|---|---|---|---|
| `schema_version` | str | 是 | `"m1b.ports.v0"` | — |
| `decision_id` | str | 是 | 确定性 id | — |
| `claim_id` | str | 是 | 对应 current claim | — |
| `change_kind` | str | 是 | `KEEP/UPDATE/RECHECK` | 沿用 B `CHANGE_KIND_VALUES` |
| `curriculum_eligible` | bool | 是 | 仅 `UPDATE`+`VERIFIED`+权威 tier 才可为 true | 防静默污染 |
| `reason` | `Reason`（v0） | 是 | `code ∈ {KEEP_UNCHANGED, UPDATE_AUTHORITATIVE_NEWER, RECHECK_CONFLICT, RECHECK_EXPIRED, RECHECK_FUTURE_TIMESTAMP, RECHECK_UNAUTHORITATIVE, RECHECK_ORDERING}` | 结构化，可审计 |
| `evidence_refs` | list[str] | 否 | `source:<id>`/`digest:<sha16>` | 不泄露内容 |
| `policy_version` | str | 是 | freshness 策略版本 | — |
| `created_at` | str | 是 | 调用方注入 | — |

**规则（fail-closed，顺序冻结；对齐 B 策略文档 §2）**

1. `current.observed_at` < `current.published_at`（未来/时钟异常）→ `RECHECK`（`RECHECK_FUTURE_TIMESTAMP`）；
2. 任一 `claim_status=CONFLICT` → `RECHECK`；3. 任一 `EXPIRED` → `RECHECK`；
4. `current.observed_at > previous.valid_until`（旧版过期后观测）→ `RECHECK`；
5. `current.observed_at > current.valid_until`（新版自身过期）→ `RECHECK`；
6. `current.published_at < previous.published_at`（镜像/乱序/更旧）→ `RECHECK`；
7. `content_digest` 相同 → `KEEP`；
8. 更新更权威/更可信且 `VERIFIED` → `UPDATE`（`curriculum_eligible=true` 仅当 tier 可更新课程）；
9. 其他歧义 → `RECHECK`。
- `KEEP` 不产生课程变更；`RECHECK` 永远 `curriculum_eligible=false`；
- `untrusted=true` 的 claim 只能产生 `RECHECK`/不可更新课程（DATA_ONLY）；
- **端口不写课程/学习者状态**；是否将 update 纳入计划由 canonical planner 在显式步骤中决定并记录 Reason。

**错误语义**：`KNOWLEDGE_SOURCE_INVALID`（schema/时间格式）、`KNOWLEDGE_SOURCE_FUTURE_TIMESTAMP`、
`KNOWLEDGE_SOURCE_CONFLICT`、`KNOWLEDGE_SOURCE_EXPIRED`、`KNOWLEDGE_SOURCE_UNAUTHORITATIVE`、
`KNOWLEDGE_SOURCE_RECHECK_REQUIRED`；`untrusted` 内容试图充当指令 →
`PORT_UNTRUSTED_INPUT_REJECTED`。

**Owner / 信任**：T3（半可信；内容经 digest/校验）；**确定性**：同一对 claim（固定 created_at）→
同 decision，canonical JSON sha256 稳定。

### 3.4 `TeacherPolicyPort`（教学策略/提示与追问决策；B-PR4 接入）

**目的**：把 B `TeachingPolicy`（`m1_offline/teaching_policy.py:154`，Fixed v0/Adaptive v1 与
`EvidenceGate`）与 Interview 追问策略统一成 canonical 可消费的**决策端口**：只输出 `TeachingAction` +
结构化 `Reason`，不产生副作用、不写状态。

**位置（计划）**：`m1_teacher/ports/teacher_policy.py`；B-PR4 实现 CF Hint/Interview 两个 vertical adapter。

**Protocol 签名（DESIGN_ONLY）**

```python
@runtime_checkable
class TeacherPolicyPort(Protocol):
    policy_version: str
    def decide(self, context: PolicyContext) -> PolicyOutcome: ...
```

**`PolicyContext` dict schema**

| 字段 | 类型 | 必填 | 约束 | 说明 |
|---|---|---|---|---|
| `schema_version` | str | 是 | `"m1b.ports.v0"` | — |
| `context_id` | str | 是 | 确定性 id | — |
| `vertical_id` | str | 是 | `cf_binary_search` / `interview_coach` | 策略所属 vertical（freshness 不产教学动作） |
| `learner_snapshot` | `LearnerSnapshot`（v0） | 是 | teacher-visible；无 hidden 字段 | 只读 |
| `session` | `SessionState`（v0） | 是 | phase/pending/turn | 只读 |
| `goal` | `LearnerGoal`（v0） | 是 | — | 只读 |
| `objective` | `LearningObjective`（v0） | 是 | — | 只读 |
| `candidate_node_ids` | list[str] | 是 | 来自 planner/诊断的候选 | — |
| `available_items` | list[`AssessmentItem`]（v0） | 是 | 无 answer 字段 | 只读 |
| `recent_events` | list[`HistoryEvent`]（v0） | 否 | 截断（≤ 最近 N 条） | 只读 |
| `hint_level_cap` | int | 是 | 1..3（canonical 默认 max 3）；4 仅显式批准后 | **安全门** |
| `allowed_action_kinds` | tuple[str,...] | 是 | canonical `TEACHING_ACTION_KIND_VALUES` 子集 | 越界 → reject |
| `untrusted_text_refs` | tuple[str,...] | 否 | 仅 DATA_ONLY 引用 | 不得作为指令 |
| `created_at` | str | 是 | 调用方注入 | 决定论 |

**`PolicyOutcome` dict schema**

| 字段 | 类型 | 必填 | 约束 | 说明 |
|---|---|---|---|---|
| `schema_version` | str | 是 | `"m1b.ports.v0"` | — |
| `outcome_id` | str | 是 | 确定性 id | — |
| `action` | `TeachingAction`（v0） | 是 | `kind ∈ allowed_action_kinds`；`reason.code` 非空 | 唯一输出动作 |
| `hint_level` | int \| None | 是 | 1..4；CF 必填，Interview 可为 None | level 写在结构化字段 |
| `evidence_gate` | str | 是 | `NONE/L1_EVIDENCE/L2_EVIDENCE/L3_EVIDENCE/FULL_EXPLICIT` | 便于审计 |
| `fallback_used` | bool | 是 | 无匹配规则时为 true（回退到安全动作，不允许沉默） | — |
| `reason` | `Reason`（v0） | 是 | 结构化解释（code/node_ids/detail/policy_version） | 与 action.reason 一致或更详细 |
| `created_at` | str | 是 | 调用方注入 | — |

**B action kind → canonical `TEACHING_ACTION_KIND` 映射（冻结建议）**

| B `TEACHER_ACTION_KIND_VALUES` | canonical `TeachingAction.kind` | `hint_level` | `Reason.code` 示例 |
|---|---|---|---|
| `LIGHT_HINT` | `HINT` | 1 | `HINT_LADDER_L1_LIGHT` |
| `INVARIANT_HINT` | `HINT` | 2 | `HINT_LADDER_L2_INVARIANT` |
| `STRUCTURE_HINT` | `HINT` | 3 | `HINT_LADDER_L3_STRUCTURE` |
| `FULL_SOLUTION` | `HINT` | 4 | `HINT_LADDER_L4_FULL_EXPLICIT`（仅显式批准+证据门） |
| `SOCRATIC_QUESTION` | `HINT` | None | `SOCRATIC_FOLLOWUP_<stage>`（Interview 5 阶段） |
| `ASK_CLARIFICATION` | `DIAGNOSE` | None | `ASK_CLARIFICATION_PROJECT_FACT` |
| `EXPLAIN` | `EXPLAIN` | None | `EXPLAIN_CONTENT` |
| `PRACTICE` | `PRACTICE` | None | `PRACTICE_ASSIGNMENT` |
| `REVIEW` | `REVIEW` | None | `REVIEW_SCHEDULED` |

- canonical `RETEACH/REASSESS/GOAL_COMPLETE/SESSION_PAUSE/SESSION_RESUME` 属于 core/session 职责，
  vertical **不得**发出 → `PORT_ACTION_KIND_UNSUPPORTED`；
- 默认必须 `LIGHT_HINT`；无证据时任何更强请求被证据门封顶（`EvidenceGate`，`teaching_policy.py:79`）；
- `FULL_SOLUTION` 在 canonical `hint_level_cap=3` 下不可发出 → `PORT_FULL_SOLUTION_BLOCKED`；
- 端口不修改 snapshot/session/event log；由 canonical engine 依据 outcome 生成持久事件。

**Owner / 信任**：T3（策略内容半可信；只输出 teacher-visible action）；**确定性**：固定 context + 固定
policy_version → 同 outcome（canonical JSON sha256 稳定）；`reason` 必须可审计；不得读取 hidden scoring。

---

## 4. 信任边界与泄漏面（按端口）

| 端口 | 输入来源 | 隐藏材料 | 输出可见性 | 防泄漏验收（B-PR1/4 冻结项） |
|---|---|---|---|---|
| `DomainAdapterV1` | T3 fixtures（synthetic） | 无（hidden 只在 scorer fixtures） | teacher-visible 节点/目标/题目/内容/assets | assets/内容 JSON 扫描 forbidden tokens；adapter 只读白名单文件 |
| `AssessmentPort` | T1 trusted job；T2 worker 只拿输入 | **T1 内** expected/spec | 仅 `AssessmentResult`（五态+聚合） | worker 无 expected；teacher/JSON/logs 无 expected（B1-02/B1-06） |
| `KnowledgeSourcePort` | T3/T4 claim 内容（DATA_ONLY） | 无 | `KnowledgeDecision`（KEEP/UPDATE/RECHECK+Reason） | untrusted 内容不得改指令/权限/评分；decision JSON 无原文大段内容 |
| `TeacherPolicyPort` | T0 只读快照 + T3 内容 + T4 refs | 无 | `PolicyOutcome`（action+Reason） | 输出 JSON 无 hidden/expected；FULL_SOLUTION 默认不可用 |

**权责矩阵（冻结）**

| 组件 | 写 learner state / snapshot / event log / session | 读 hidden scoring | 备注 |
|---|---|---|---|
| `SessionEngine`（T0） | **是（唯一入口组合）** | 否 | 经 repository 单事务（B-PR2） |
| `LearningHistory`/`MasteryModel`（T0） | **是（唯一状态写入者）** | 否 | — |
| `SqliteRepository`（T0） | **是（持久层）** | 否 | 单 writer 假设（B-PR2 确认/失败关闭） |
| `AssessmentPort` 可信端（T1） | 否 | **是（唯一）** | 只产出 `AssessmentResult` |
| `UntrustedExecutionWorker`（T2） | 否 | 否 | 仅执行；输出不可信 |
| CF/Interview/Freshness vertical（T3） | **否** | 否 | 只能经端口返回数据/决策 |
| Interview `untrusted_docs` / 外部知识（T4） | 否 | 否 | DATA_ONLY，不得提升为指令 |

---

## 5. 迁移数据项：lossless roundtrip、拒绝码与 checksum

> 本节是 `M1_B_CONVERGENCE_ADR.md` §7 的逐项细则；**全部 DESIGN_ONLY，未实现**。迁移只允许对
> synthetic fixture/脱敏副本运行；真实 learner DB 默认禁止自动迁移（§7.5 门）。

### 5.1 判定规则

1. **lossless**：存在双向映射 `f`/`f⁻¹` 使 `canonical_json(f⁻¹(f(record))) == canonical_json(record)`，
   且无字段丢失/默认值替换。满足才允许在 manifest 标 `lossless: true`。
2. **lossy**：字段有损但显式记录（`lossy: {field, action}`），不进入 canonical 状态的“数值”字段；
   只允许 sidecar 保留。
3. **unsupported**：无法表达且会影响教学/评估语义 → **显式拒绝**，不写 DB；严格模式下整批中止。

### 5.2 逐项表（B → A）

| # | 源（B `file:line`） | 目标（A `file:line`） | lossless? | 不可表达/有损字段 | 拒绝码 | 迁移动作 |
|---|---|---|---|---|---|---|
| M1 | `SkillNode`（`m1_offline/types.py:339`） | `KnowledgeNode`（`m1_teacher/contracts/types.py:579`） | 否 | `difficulty`(A 必填 1..5)、`assessment_mode`、`tags`、`content_ref` 无源；`skill_id→node_id` 需映射 | `MIGRATION_UNSUPPORTED_FIELD:difficulty / assessment_mode`、`MIGRATION_UNSUPPORTED_SKILL_MAPPING` | 需维护者显式映射表；无表→拒绝 |
| M2 | `SkillNode.prerequisites[]`（`types.py:343`） | `PrerequisiteEdge`（`types.py:594`） | 否 | 无 HARD/SOFT、无 weight；默认按 HARD 保守映射为 lossy | `MIGRATION_UNSUPPORTED_PREREQUISITE_KIND`（若要求显式 kind） | 默认 HARD/weight=1.0 + `lossy_defaulted`，或拒绝（Q3） |
| M3 | `EvidenceEvent`（`types.py:426`） | `HistoryEvent`（`types.py:803`） | 否 | 无 `session_id`/`seq`；`kind` 需映射；`observed_score/error_codes/provenance` 需 sidecar | `MIGRATION_MISSING_SESSION`、`MIGRATION_UNSUPPORTED_EVENT_KIND`、`MIGRATION_EVENT_ID_CONFLICT`、`MIGRATION_UNSUPPORTED_TASK_MAPPING` | 仅允许“证据→待写入输入”，由 canonical `LearningHistory` 生成新 id/seq；payload 保留 `migrated_v0` |
| M4 | `AssessmentResult`（`types.py:601`） | `AssessmentResult`（`types.py:683`） | 否 | `dimensions`、`hidden_cases_passed/total`、`passed`→五态需 vertical 语义；无 timestamps | `MIGRATION_UNSUPPORTED_FIELD:dimensions / hidden_cases_*`、`MIGRATION_UNMAPPED_STATUS` | 仅在完成 M3 的 vertical adapter 后可用；聚合计数进 payload sidecar |
| M5 | `LearningGoal`（`types.py:472`） | `LearnerGoal`（`types.py:792`） | 否 | `target_skills`→`objective_id` 需映射；`deadline_days/weekly_minutes` 丢弃 | `MIGRATION_UNSUPPORTED_GOAL_MAPPING`、`MIGRATION_LOSSY_FIELD:deadline_days / weekly_minutes` | 需 objective 映射表；无表→拒绝 |
| M6 | `LearnerState`（`types.py:454`） | `LearnerSnapshot`（`types.py:767`） | **否（默认拒绝）** | `mastery: float`→`MasteryEstimate`（confidence/evidence_count/created_at 无源）；无 revision | `MIGRATION_LEARNER_STATE_DENIED` | **默认永久拒绝**；仅维护者批准的一次性 offline 导入例外（Q8） |
| M7 | `TraceEvent`（`types.py:683`） | —（sidecar） | 否 | 非 canonical 事件协议 | `UNSUPPORTED_TRACE_EVENT_MIGRATION` | 仅 sidecar JSONL + sha256（manifest 记录）；不进 canonical 表 |
| M8 | `RuntimeRequest/RuntimeResponse`（`types.py:638/658`） | — | 否 | vertical 内部 mock 语义 | `UNSUPPORTED_RUNTIME_RECORD` | 不迁移；B-PR4 后仍在 vertical 内部 |
| M9 | `KnowledgeSource`/`KnowledgeRevision`（`types.py:357/382`） | `KnowledgeClaim`/`KnowledgeDecision`（§3.3） | 部分 | 字段名/结构扩展（claim_id、trust_tier、content_digest、untrusted）；B 无 content_digest | `MIGRATION_UNSUPPORTED_FIELD:content_digest`（可重算则 PASS） | vertical adapter 计算 digest；decision 交由 `KnowledgeSourcePort` |
| M10 | `TeacherAction`（`types.py:545`） | `TeachingAction`（`types.py:730`） | 否 | `rationale: str`→`Reason` 需显式 code；`hint_level`→`Reason`/`PolicyOutcome.hint_level` | `MIGRATION_UNSUPPORTED_FIELD:rationale`（无映射时）、`PORT_ACTION_KIND_UNSUPPORTED` | 仅经 `TeacherPolicyPort` 输出（§3.4 映射表） |

### 5.3 Canonical JSON sha256（复述冻结规则）

```
canonical_json(x) = json.dumps(x, ensure_ascii=False, sort_keys=True,
                              separators=(",", ":"), allow_nan=False)
digest(x) = sha256(canonical_json(x).encode("utf-8"))
```

- 对端口记录/migration 输入输出统一使用；camel/snake 不转换（保持 A 风格字段名）；
- 时间字段必须显式注入（同一 fixture 复跑 digest 不变）；
- 禁止把 `created_at=now` 的运行时对象直接纳入 digest 断言；测试固定时间。

### 5.4 迁移 checksum 记录格式（`m1b.migration.v0`，复述并冻结）

```json
{
  "manifest_version": "m1b.migration.v0",
  "source_line": "m1.offline.v0",
  "target_line": "m1a.v0",
  "source_branch_sha": "<frozen B SHA>",
  "target_branch_sha": "<frozen A SHA>",
  "tool_version": "m1b.migrate.DESIGN_ONLY",
  "created_at": "<operator supplied UTC ISO-8601>",
  "counts": {"records": 0, "lossless": 0, "lossy": 0, "unsupported": 0},
  "unsupported": [{"record_type": "...", "record_id": "...", "field": "...", "code": "MIGRATION_*"}],
  "lossy": [{"record_type": "...", "record_id": "...", "field": "...", "action": "sidecar:payload.migrated_v0"}],
  "checksums": {
    "source_sha256": "<digest(canonical source bundle)>",
    "migrated_sha256": "<digest(canonical migrated bundle)>",
    "manifest_checksum": "<digest(manifest without manifest_checksum)>"
  }
}
```

- 任一 `unsupported` 非空 + 严格模式 → 中止；`lossy` 必须显式 action；
- `manifest_checksum` 复算不一致 → 拒绝；重复 migration key → 拒绝（幂等校验在 B-PR2/B-PR3 落实）；
- manifest 不得包含 hidden expected、Key、真实个人数据。

---

## 6. 跨版本兼容策略（additive only，冻结）

1. **端口记录版本**：`m1b.ports.v0`；变更规则同 `m1a.v0`：只增（新增可选带默认字段、新增枚举值、
   新增方法需新 Protocol 后缀版本），不删/不改名/不改语义。
   新增字段必须 `from_dict` 可缺省（默认值），旧 payload 仍合法。
2. **v0 合同不动**：`m1_teacher/contracts/**`、`m1_offline/types.py` 不原地修改；端口记录/协议放在
   新模块（`m1_teacher/ports/**`、`m1_teacher/verticals/**`），由 B-PR1/B-PR4 新建。
3. **端口版本协商**：core 读取 `vertical_version`/`policy_version`；不认识的次版本 → `PORT_VERSION_UNSUPPORTED`
   （fail closed），不得猜测兼容。
4. **PR 落位**：

| PR | 端口工作 | 产出 |
|---|---|---|
| B-PR1 `trusted-judge-worker` | 实现 `AssessmentPort` 可信端 + worker 协议；`AssessmentJob`/审计 schema；错误码；默认阻断不可信 CODE | 端口实现 + 威胁模型 + 泄漏扫描 |
| B-PR2 `session-transaction-and-recovery` | 不新增端口；冻结 canonical 写入者/事务/episode 语义（`commit_teaching_turn`） | 事务/恢复实现 + 崩溃矩阵 |
| B-PR3 `scoped-idempotency` | 在 `AssessmentPort` job 上增加/冻结 scope（`turn_id`/`attempt`/请求 digest）；result id 复合键 | scoped 幂等实现 + 负例 |
| B-PR4 `cf-interview-domain-ports` | 实现 `DomainAdapterV1`（CF/Interview/Freshness 适配）+ `TeacherPolicyPort`（Hint/Interview 策略）+ `KnowledgeSourcePort`（Freshness） | vertical 适配层 + 映射 |
| B-PR5 `unified-e2e-and-blind-evaluation` | 仅使用端口做两域 E2E/Replay/评测；生成新 suite/报告 | E2E + 证据 + 独立评审输入 |

---

## 7. 可测验收清单（后续 PR 的测试输入；本文件不声称已通过）

| ID | 验收点 | 归属 PR |
|---|---|---|
| P-01 | 四个端口 Protocol 均为 `runtime_checkable`，实现可被 `isinstance` 检查；v0 adapter/scorer 不被破坏 | B-PR1/B-PR4 |
| P-02 | 端口记录 roundtrip 严格（未知字段/错版本/坏枚举 fail closed），canonical JSON sha256 稳定 | B-PR1/B-PR4 |
| P-03 | `AssessmentPort`：worker 无 expected/answer；伪造 `passed`/结果文件/argv/输出 JSON 不能改 trusted verdict；teacher-visible 导出无 expected | B-PR1 |
| P-04 | `AssessmentPort`：infra 错误 → `EVAL_ERROR` 且不降 mastery；TLE 与 infra 可区分 | B-PR1 |
| P-05 | `DomainAdapterV1`：CF/Interview/Freshness assets 校验/白名单/无 hidden；`validate()` 无副作用 | B-PR4 |
| P-06 | `KnowledgeSourcePort`：KEEP/UPDATE/RECHECK 规则 + 过期/冲突/未来时间/更旧/digest 相同；`curriculum_eligible` 只对权威 UPDATE 为 true；untrusted 不改指令 | B-PR4 |
| P-07 | `TeacherPolicyPort`：默认 LIGHT；无证据封顶；FULL 默认不可发出（`PORT_FULL_SOLUTION_BLOCKED`）；B action kind 映射正确；输出结构化 Reason | B-PR4 |
| P-08 | 写入权：vertical/scorer/UI **不能**写 canonical snapshot/events/sessions（负例测试） | B-PR2/B-PR4 |
| P-09 | 迁移：lossless 判定/unsupported 拒绝/manifest checksum 复算/rollback 条件负例 | B-PR4/B-PR5 |
| P-10 | 两域 E2E 共用同一事件表/Replay（CF + Interview），无重复 mastery、状态可恢复 | B-PR5 |

---

## 8. 未决问题（需维护者/LeadB 决策）

| # | 问题 | 影响 | 建议决策者 |
|---|---|---|---|
| Q1 | 是否签收四个端口名称/签名/错误码为 B-PR1..5 的冻结接口？ | 后续 PR 无法开工 | 维护者 + LeadB |
| Q2 | `AssessmentPort` 是否在 B-PR1 立即实现 OS 隔离 worker，还是先“默认硬拒绝不可信 CODE + 内部 trusted fixture 入口”？ | B1-01 验收路径 | LeadB + Human（OS 沙箱批准） |
| Q3 | `FULL_SOLUTION`（L4）是否永远不进入 canonical（cap=3）？若允许，需要什么人类批准/证据门？ | 教学安全 | 维护者 + 教学负责人 |
| Q4 | `SkillNode.prerequisites` 迁移默认 `HARD` 还是要求显式 kind 映射（Q2/Q3 in ADR）？ | 先修补救语义 | 教学负责人 |
| Q5 | `KnowledgeSourcePort` 的 tier 白名单与 `curriculum_eligible` 条件是否与 B 策略完全一致，还是 canonical 更严格？ | 内容准入 | 维护者 |
| Q6 | `TeacherPolicyPort` 是否允许 Interview 的 `ASK_CLARIFICATION` 映射到 canonical `DIAGNOSE`（可能占用诊断名额）？ | session 状态语义 | LeadB（B-PR4） |
| Q7 | 端口记录是否需要在 `docs/M1_ARCHITECTURE.md` 增设版本章节（additive）？ | 文档一致性 | LeadB |
| Q8 | B 线 `runtime_port` 在 B-PR4 后是否允许被 external caller 使用？（canonical 仍不调用模型） | B4 E2E 边界 | LeadB + 维护者 |

---

## 9. 参考（SOURCE_INSPECTED）

- A：`m1_teacher/contracts/{types,domain,repository}.py`、`knowledge/graph.py`、
  `learner/{model,history,repository}.py`、`assessment/scorer.py`、`session/engine.py`、
  `domains/cf_binary_search.py`、`extensions/interfaces.py`、`docs/M1_ARCHITECTURE.md`、
  `docs/M1_ADR_001_DOMAIN_CONTRACTS.md`。
- B：`m1_offline/types.py`、`memory.py`、`learner_model.py`、`runtime_port.py`、`teaching_policy.py`、
  `curriculum_planner.py`、`diagnostics.py`、`cf/{judge,teacher}.py`、`interview/{coach,rubric}.py`、
  `freshness.py`、`evaluation/{harness,report}.py`、`docs/m1/TEACHER_CORE_ARCHITECTURE.md`、
  `docs/m1/ADR-TEACHER-CORE.md`、`docs/m1/CF_TEACHER_SPEC.md`、`docs/m1/INTERVIEW_COACH_SPEC.md`、
  `docs/m1/FRESHNESS_AND_SOURCE_POLICY.md`。
- 交接：`/root/leadb_zip/02_LEADB_AGENT_HANDOFF.md`（B0/B1/B2/B3/B4/B5、PR 分工）、
  `AUDIT_REQUESTS.md`（B-Q1/B-Q2/B-Q3/B-Q4/B-Q5）、`TEST_EVIDENCE_MATRIX.csv`。

---

## 10. 变更记录

| 日期（UTC） | 版本 | 变更 |
|---|---|---|
| 2026-11-20 | B-PR0 初稿 | DRAFT/DESIGN_ONLY：四端口签名/schema/信任边界/错误码、B→A 映射与拒绝码、canonical JSON sha256 + migration manifest、写入者矩阵、B-PR1..5 落位、可测验收清单、未决问题 |
