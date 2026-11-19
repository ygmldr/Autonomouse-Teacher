# M1 Offline Teacher — Teacher Core Architecture (v0 draft)

| 字段 | 值 |
| --- | --- |
| 文档状态 | `DRAFT` / `NOT_FROZEN` |
| 版本 | v0（2026-11-19） |
| 适用范围 | `m1_offline/` 包（B 线）；不涉及 M0 修改 |
| 证据 | 本文所述实现均有 b-core 真实测试证据；端到端闭环验收由 B-Lead/评审复核 |
| 能力声明 | M0 Runtime 能力状态一律 UNVERIFIED；本架构只用 MockRuntimePort，声明 M0 已实现任何 API 均不成立 |

## 1. 设计目标

1. **独立隔离包**：`m1_offline/` 不 import `autoteacher_m0`，不改 M0 代码/LiveGate/配置。
2. **离线 mock-only**：所有模型调用经 `RuntimePort`，默认实现为确定性 `MockRuntimePort`；零网络。
3. **证据驱动**：学习者状态只能由 `EvidenceEvent` 更新；模型文本/自评不构成掌握证据。
4. **可解释**：每个教学动作（`TeacherAction`）/计划（`CurriculumPlan`）/诊断（`DiagnosticResult`）都带 rationale/explanation。
5. **可回放**：教学循环由 `TraceEvent` 事件流记录，可按 `loop_id` 顺序重放、可 JSONL 持久化。
6. **fail-closed**：非法枚举/未知字段/跨学习者证据/未分类诊断/损坏 JSONL 都显式失败或降级为 UNKNOWN/NEEDS_REVIEW，绝不静默猜测。
7. **确定性**：固定 seed 的 Mock Runtime、固定规则策略/规划器/诊断器 → 同输入同输出（时间戳字段除外，回放用事件时间）。

## 2. B1 模块职责表（九模块 + 横切评测层）

> 说明：B1 九模块为 B 线 Teacher Core 的职责分解，其中 7 个由 b-core 实现、2 个垂直教学模块由
> b-cf / b-interview 实现；b-eval 的评测层是横切验证层（不计入九模块，但覆盖全部模块）。

| # | 模块 | 文件 | 职责 | 关键不变量 | 所有者 |
| --- | --- | --- | --- | --- | --- |
| 1 | 契约/类型层 | `m1_offline/types.py` | 16 个 Record 类型、schema_version、枚举、JSON 无损往返、时间/校验规则 | 字段=构造参数；`to_dict` 首键 `schema_version`；`from_dict` 严格 | b-core |
| 2 | 运行时边界 | `m1_offline/runtime_port.py` | `RuntimePort` 协议 + 确定性 `MockRuntimePort`（回放/生成/错误注入） | `simulated=True`；零网络；同 seed 同输出 | b-core |
| 3 | 学习者模型 | `m1_offline/learner_model.py` | 证据 → mastery/error_counts/evidence_count；replay | 无证据不涨；带 `error_codes` 的失败证据只降/不升；重复观测递减且不迁移；同 event_id 幂等 | b-core |
| 4 | 教学策略 | `m1_offline/teaching_policy.py` | `TeachingPolicy` 接口、`FixedPolicy`(v0)、`AdaptivePolicy`(v1)、Hint Ladder 安全门 | 默认 LIGHT；升级需证据（≥2 错 +1 级、≥4 错 +2 级，受门限）；FULL 仅显式 L4；绝不默认 FULL_SOLUTION | b-core |
| 5 | 课程规划 | `m1_offline/curriculum_planner.py` | Goal+State+任务库 → 可解释计划（复习/新知平衡、预算） | rationale 覆盖每个决策；deterministic；policy_version 可回滚 | b-core |
| 6 | 事件记忆 | `m1_offline/memory.py` | TraceEvent append/replay/JSONL 往返/按学习者删除 | 顺序保真；事实/推断保留 kind/source；删除返回数量 | b-core |
| 7 | 诊断引擎 | `m1_offline/diagnostics.py` | 规则式错误分类（5 类）+ 置信度/状态 | 已知错误码需显式信号；歧义 → UNKNOWN/NEEDS_REVIEW | b-core |
| 8 | CF Teacher | `m1_offline/cf/`（judge.py/teacher.py） | 本地 subprocess judge（隐藏用例）+ 多轮 CF 教学 | AC/pass 只来自 judge；hint 阶梯安全；无网络 | b-cf |
| 9 | Interview Coach + Freshness | `m1_offline/interview/`、`m1_offline/freshness.py` | 多轮追问阶梯、独立 rubric 评分、知识新鲜度/冲突/RECHECK | 教练不自评；项目事实缺失须澄清；过期/冲突不静默入课 | b-interview |
| 横切 | 评测/闭环层 | `m1_offline/evaluation/`、`m1_offline/demo.py` | 闭环 harness、v0/v1 对比、污染/负例检查、可回放 demo | 独立评分器；public/hidden 分离；无证据不涨 mastery；结论限定 synthetic | b-eval |

## 3. 已冻结的跨模块 API（v0）

其他 Agent 只读消费以下签名（改动须先经 B-Lead 契约决策）：

```python
# m1_offline/__init__.py
REPO_ROOT: pathlib.Path               # worktree 根（parents[1]）
FIXTURES_DIR: pathlib.Path            # REPO_ROOT / "fixtures" / "m1"
SCHEMA_VERSION = "m1.offline.v0"
def load_json(path: str | Path) -> dict   # 相对路径按 REPO_ROOT 解析；非 JSON object 报错
def now_utc() -> str                  # "YYYY-MM-DDTHH:MM:SSZ" UTC

# m1_offline/types.py
class Record:                          # 基类：schema_version 属性 + to_dict/to_json/from_dict/from_json
SCHEMA_VERSION = "m1.offline.v0"
# 16 个 Record：Provenance, SkillNode, KnowledgeSource, KnowledgeRevision, LearnerProfile,
#   EvidenceEvent, LearnerState, LearningGoal, LearningTask, CurriculumPlan, TeacherAction,
#   DiagnosticResult, AssessmentResult, RuntimeRequest, RuntimeResponse, TraceEvent

# m1_offline/runtime_port.py
class RuntimePort(Protocol): def send(request: RuntimeRequest) -> RuntimeResponse
class MockRuntimePort(script: dict | None = None, seed: int = 0)
# script: {"responses": {request_id: entry}, "queue": [entry...], "default": entry,
#          "error": str, "raise": bool|str}; entry: {"text","tool_events","usage","error","raise"}

# m1_offline/learner_model.py
class LearnerModel(profile: LearnerProfile):
    def state() -> LearnerState
    def apply_evidence(event: EvidenceEvent) -> LearnerState
    def replay(events: list[EvidenceEvent]) -> LearnerState
    def register_task_skills(task_id: str, skill_ids: list[str]) -> None
    def task_skills(task_id: str) -> tuple[str, ...]

# m1_offline/teaching_policy.py
class TeachingPolicy:
    def choose(task: dict, learner_state: LearnerState,
               diagnosis: DiagnosticResult | None, hint_level: int) -> TeacherAction
class FixedPolicy(TeachingPolicy)        # policy_version = "teacher_v0"
class AdaptivePolicy(TeachingPolicy)     # policy_version = "teacher_v1"
class EvidenceGate: max_level(state, skill_ids=None) -> int  # 1..4

# m1_offline/curriculum_planner.py
class CurriculumPlanner:
    policy_version = "planner_v0"
    def plan(goal: LearningGoal, learner_state: LearnerState,
             available_tasks: list[LearningTask]) -> CurriculumPlan

# m1_offline/memory.py
class LearningMemory:
    def append(event: TraceEvent) -> None
    def replay(loop_id: str) -> list[TraceEvent]
    def to_jsonl(path) -> int            # 返回写入行数
    @classmethod from_jsonl(path) -> LearningMemory
    def delete(learner_id: str) -> int   # 返回删除事件数

# m1_offline/diagnostics.py
class DiagnosticEngine:
    def diagnose(task: dict, submission: dict, learner_state: LearnerState) -> DiagnosticResult
KNOWN_ERROR_CODES = ("off_by_one", "wrong_complexity", "wrong_data_structure",
                     "edge_case", "conceptual_gap")
```

## 4. 数据流（离线闭环，≥3 轮，目标形态）

```
Goal(LearningGoal) ──┐
                     v
              CurriculumPlanner ──> CurriculumPlan(tasks, rationale, policy_version)
                     │
                     v
             LearningTask(fixture_ref) ──> Learner 作答/提交（synthetic）
                     │
        ┌────────────┴─────────────┐
        v                          v
 DiagnosticEngine             本地独立 judge（b-cf；隐藏用例；subprocess 隔离）
 (task, submission, state)          │
        │ DiagnosticResult           v
        │                     AssessmentResult(独立 scorer)
        └────────────┬─────────────┘
                     v
            EvidenceEvent(provenance, observed_score, error_codes)
                     │
        ┌────────────┴──────────────┐
        v                           v
  LearnerModel.apply_evidence   LearningMemory.append(TraceEvent)
        │                           │
        v                           v
  LearnerState(mastery,       replay(loop_id) / JSONL 持久化
  error_counts, evidence)           │
        │                           v
        v                     评测层（b-eval）：独立评分/对比/污染检查/负例
  TeachingPolicy.choose ──> TeacherAction(rationale, hint_level)
        │
        └──> 下一轮（RuntimePort(Mock) 仅用于生成模拟文本，不产生掌握证据）
```

关键约束：**模型生成的文本永远不直接更新 mastery**；mastery 只接受带 `observed_score` 的
`EvidenceEvent`（`ANSWER/CODE_SUBMISSION/EXPLANATION/INTERVIEW_RESPONSE/ASSESSMENT`），且必须
来自独立 judge/rubric 的评分产物。带 `error_codes` 的失败证据是 fail-closed 的：只允许把 mastery
下调到观测值或保持不变，**不允许上调**（失败不能证明进步）；越强的提示干预必须由更多证据支撑，
且 `FULL_SOLUTION` 只接受显式 L4 请求。

## 5. 类型 / schema_version / provenance 规则

1. **Record 基类**：所有记录继承 `Record`；`schema_version` 是只读属性（`m1.offline.v0`），
   序列化在 `to_dict()` 第一个键，不占用构造参数（保持共享契约字段名/顺序不变）。
2. **无损往返**：`to_dict()`（递归支持嵌套 Record/`list[Record]`/`list[dict]`）→ `json.dumps`
   → `from_dict`；`to_json()`/`from_json()` 为一等便利接口。`from_dict` 严格拒绝未知字段与
   `schema_version` 不匹配，缺失必填字段报 `SchemaError`。
3. **枚举**：枚举使用大写字符串 + 常量校验（非 Python Enum，便于 JSON/跨模块直接比较）：
   `claim_status`、`change_kind`、`baseline_level`、`EvidenceEvent.kind`、`task_type`、
   `TeacherAction.kind`、`DiagnosticResult.status`；非法值 `SchemaError`。
4. **时间**：时间字段为 UTC ISO-8601 字符串（`YYYY-MM-DDTHH:MM:SSZ`，`now_utc()`）；可选时间字段
   默认 `now_utc()`；显式时间原样保留 → replay 确定性。`published_at`/`observed_at`/`valid_until`
   由 freshness 层解释，types 层只保证格式/类型。
5. **provenance**：`EvidenceEvent.provenance: Provenance | None`；`Provenance.experiment_id` 必填，
   `source` 记录来源（synthetic fixture / mock runtime / judge），`created_at` 默认 UTC。
   任何进入学习者模型/记忆的事件都应带可追溯来源；无 provenance 的 synthetic 单元测试数据必须
   显式标注 synthetic（fixtures 层责任）。
6. **契约增补记录（可增不可减）**：相对共享契约 v0 的**新增**（非字段变更）：
   - 方法：`Record.to_json()/from_json()/schema_version`；`LearnerModel.register_task_skills()/task_skills()/profile`；
     `LearningMemory.events()/loop_ids()/__len__`；`EvidenceGate.describe()`；`hint_kind_for_level` 映射。
   - 常量：`SCHEMA_VERSION`、`SchemaError`、`*_VALUES`/`*_SET` 枚举常量、
     `HINT_LADDER/HINT_LEVEL_MIN/HINT_LEVEL_MAX`、`SCORED_EVIDENCE_KINDS`、`KNOWN_ERROR_CODES`、
     `COMPLEXITY_RANK`、`TRACE_EVENT_KINDS`。
   - 校验强度（不改字段）：confidence/score/mastery/dimensions ∈ [0,1]；`hidden_cases_passed <= total`；
     `difficulty ∈ [1,5]`；`hint_level ∈ [1,4]`（非空时）；id/timestamp 类字段非空；
     `LearningGoal.target_skills` 与 `LearningTask.skill_ids` 非空。
   - **未删除或重命名任何共享契约字段/类型。**

## 6. MockRuntimePort 设计与可替换性

- **协议**：`RuntimePort.send(RuntimeRequest) -> RuntimeResponse`；`@runtime_checkable`，可被
  `isinstance(port, RuntimePort)` 检查；未来 live adapter 必须实现同一协议。
- **确定性**：生成回复 = `sha256(seed, request_id, last_user_content)` 前缀；usage/tool_events
  默认也由请求确定性推导。同一 `(seed, request)` 重复调用输出完全一致。
- **脚本回放**：`responses`（按 request_id 精确匹配）→ `queue`（按序消费）→ `default` →
  确定性生成；支持 `text/tool_events/usage/error/raise` 注入。
- **错误注入**：`{"error": "..."}` 返回 `RuntimeResponse(error=...)`（`simulated=True`）；
  `{"raise": true}` 抛 `RuntimeError` 模拟传输层失败（用于 fail-closed 测试）。
- **simulated 标记**：所有响应 `simulated=True`；评测/演示必须展示该标记，禁止把 mock 输出当作
  真实 provider 证据。
- **零网络**：模块不 import 网络栈；测试用 monkeypatch 禁用 `socket.socket/create_connection/
  getaddrinfo` 后仍可完成调用。
- **可替换性**：替换为真实 provider 时只允许新增 adapter 实现 `RuntimePort`，不得修改 Teacher
  Core；是否启用 live 属于 M0/A 线范畴，状态 UNVERIFIED，且 M1 默认永不启用。
- **M0 隔离**：M1 不 import M0、不改 LiveGate、不假设 M0 的 session/tool/usage 语义；抽象接口见
  `docs/interfaces/teacher_runtime_boundary_v0.md`（v0 draft，A 线未冻结）。

## 7. 失败模式与 fail-closed 矩阵

| 失败模式 | 行为 | 证据 |
| --- | --- | --- |
| 未知/缺失必填字段、非法枚举 | `SchemaError`（ValueError 子类） | `test_schema.py` |
| `from_dict` 未知字段 / schema_version 不匹配 | `SchemaError`，不静默丢弃 | `test_schema.py` |
| 跨学习者证据进入 LearnerModel | `ValueError`（fail-closed） | `test_learner_model.py` |
| 无 skill 映射的 evidence | 计入 evidence_count/error_counts，但不改 mastery | `test_learner_model.py` |
| 重复 event_id | 幂等 no-op | `test_learner_model.py` |
| 带 error_codes 的失败证据企图提升 mastery | 封顶为不升（仅可下调/保持） | `test_learner_model.py` |
| 无证据却请求高 hint | 封顶 LIGHT_HINT（安全下限） | `test_teaching_policy.py` |
| 非显式 L4 的升级尝试 | 永不跨入 FULL_SOLUTION（显式 L4 + 证据门才允许） | `test_teaching_policy.py` |
| 诊断歧义/未知错误码/冲突 | `NEEDS_REVIEW`；无信号 → `UNKNOWN` | `test_diagnostics.py` |
| 规划器无可用任务 | 空计划 + `NO_AVAILABLE_TASKS` rationale，不伪造任务 | `test_curriculum_planner.py` |
| 预算不足 | 至少保留 1 个任务并记 `OVER_BUDGET_MINIMUM`；剔除项记 `BUDGET` | `test_curriculum_planner.py` |
| 损坏/未知字段 JSONL | `ValueError`（行号），不加载半截数据 | `test_memory.py` |
| 脚本化传输失败 | `MockRuntimePort` 抛 `RuntimeError`；调用方须捕获并降级 | `test_runtime_port.py` |
| 网络出站 | 结构上不可能（无网络 import）；测试双重验证 | `test_no_m0_import.py`, `test_runtime_port.py` |
| M0 依赖 | 禁止；静态+运行时检查 | `test_no_m0_import.py` |

**降级原则**：教学动作永不因"不确定"而升级为更强制干预；评测永不把未运行项写成 PASS；
未分类错误默认走 `NEEDS_REVIEW`/`ASK_CLARIFICATION`，而不是 `FULL_SOLUTION`。

**提示强度与证据**：Hint 安全门只看证据量（不要求成功），因为"反复失败"本身是强证据；但
`FULL_SOLUTION` 必须由调用方显式请求 L4，自动升级永不跨入 FULL（见 ADR-CORE-4）。

## 8. 可回放事件模型

- **事件类型**：`TraceEvent(event_id, loop_id, round, step, payload, timestamp)`；payload 保留
  `kind`（`FACT/INFERENCE/ACTION/OBSERVATION/ERROR`）与 `source`，用于区分事实与推断。
- **顺序**：`LearningMemory.append` 保持追加顺序；`replay(loop_id)` 返回该循环事件的原序列表；
  `loop_id` 是回放主键。
- **持久化**：`to_jsonl(path)` 一行一个 `TraceEvent` JSON（含 schema_version、timestamp）；
  `from_jsonl(path)` 严格解析；往返无损（测试验证字节级 JSONL 一致性）。
- **确定性回放**：LearnerModel 的 `replay(events)` 从干净状态按序应用；`updated_at` 取最后一个
  事件的显式时间 → 同一事件序列重放得到相同 `LearnerState`（除显式时间缺失外）。
- **幂等/去重**：模型按 `event_id` 去重；评测层要求"按 event ID 回放"，避免 at-least-once 重复计。
- **事实 vs 推断**：记忆按 payload `kind/source` 原样保留；`delete(learner_id)` 同时删除事实与
  推断（synthetic 遗忘原语），返回删除数量。
- **删除语义**：按 `payload.learner_id`、`payload.learner_ids[]`、`payload.learner.learner_id`
  匹配；未知学习者返回 0 且不修改存储。

## 9. 与 M0 的隔离

- `m1_offline/**` 禁止 import `autoteacher_m0` 或 `src` 下 M0 代码（静态 AST + fresh subprocess 测试）。
- 不修改 M0 的 `src/autoteacher_m0/**`、`plugins/**`、`config/**`、`scripts/**`、LiveGate、
  M0 测试与文档。
- 不复制 M0 真实运行数据/凭据；不调用 M0 Runtime。
- M0 能力状态一律 **UNVERIFIED / 抽象**：本包只定义抽象 `RuntimePort` 与 mock 实现，不声称
  M0 的 session/tool/resume/usage/cancel 等能力已实现或已验收。
- B→A 教学能力需求（供 A 线未来对齐）见 `docs/interfaces/teacher_runtime_boundary_v0.md`。

## 10. 已知限制

1. Learner Model 是**有界滑动平均**（synthetic proxy），不是心理测量模型，无效度声明。
2. `MockRuntimePort` 只证明边界/确定性，不证明真实模型质量。
3. 教学策略/规划器/诊断器是**规则系统**，覆盖面有限；未覆盖情形显式 UNKNOWN/NEEDS_REVIEW。
4. 时间戳默认 `now_utc()`；跨运行严格逐字节复现需由调用方固定事件时间/seed（评测层责任）。
5. 本文件与实现只覆盖 B 线；M0/A 线能力需另立验收，当前 UNVERIFIED。
