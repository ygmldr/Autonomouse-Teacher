# Teacher ↔ Runtime Boundary (v0 draft, read-only concept doc)

| 字段 | 值 |
| --- | --- |
| 文档状态 | `DRAFT` / `NOT_FROZEN`（只读抽象接口文档；供 A 线（Runtime）与 B 线（Teacher）对齐） |
| 版本 | v0（2026-11-19） |
| 作者/所有者 | B 线 b-core 起草；接口冻结需 A 线 + B 线 + 维护者共同确认 |
| A 线状态 | **尚未冻结**：本文所有类型/事件均为抽象需求，不代表 A 线已实现或已同意 |
| M0 能力状态 | **一律 UNVERIFIED**：本文不声称 M0 已实现/已验收任何 Runtime API、LiveGate、Provider Bridge、session/tool/usage/cancel 能力 |
| 实现状态 | B 线仅在 `m1_offline/runtime_port.py` 提供 mock-only 实现（`MockRuntimePort`，零网络、`simulated=True`） |

> **诚实边界声明（必读）**：本文描述的是 B 线（Teacher）对"运行时/模型调用边界"的**抽象需求**，
> 用于未来 A 线接口冻结时对齐。它不是 A 线的实现文档，也不是 M0 的能力验收证据。任何把本文
> 当作"M0 已有 Live API / 已验收"的引用都是**错误引用**。

---

## 1. 目的与范围

- **目的**：给 B 线教学层一个稳定、可替换、可回放、可审计的模型调用边界；让 A 线在冻结 Runtime
  接口时有明确的消费者需求清单。
- **范围内**：抽象类型（请求/响应/工具事件/session 恢复/用量/错误/取消/追踪字段）与 B→A 教学
  能力需求、版本与冻结规则。
- **范围外**：真实 Provider SDK、凭据管理、计费、网络/出口策略、M0 LiveGate 实现、真实教学效果。
- **当前实现**：B 线只使用 `MockRuntimePort`（`m1_offline/runtime_port.py`）；A 线/M0 侧无任何
  代码在本仓库被 B 线调用或验证。

## 2. 抽象类型与事件（仅语义约定，非 wire format）

> 说明：字段名是**抽象名**，不是已冻结的 JSON schema；A 线实现可使用不同物理命名，但语义需
> 可映射。所有"必须/MUST"均为 B 线需求，A 线是否支持为 UNVERIFIED。

### 2.1 `send_message`（请求/响应）

| 抽象字段 | 方向 | 必需性 | 语义 |
| --- | --- | --- | --- |
| `request_id` | T→R | MUST | 幂等键；重发同 id 应返回同逻辑结果或明确冲突 |
| `session_id` | T→R | MUST | 会话标识；与 `session_resume` 配合 |
| `messages[]` | T→R | MUST | `{role, content}` 序列；role ∈ SYSTEM/USER/ASSISTANT/TOOL（抽象） |
| `tools[]` | T→R | MAY | 工具名列表；空表示不使用工具 |
| `metadata{}` | T→R | MAY | 教学上下文（loop_id/round/experiment_id）；不得含真实个人数据 |
| `text` | R→T | MUST | 模型/模拟输出文本 |
| `tool_events[]` | R→T | MAY | 见 2.2；顺序 = 发生顺序 |
| `usage{}` | R→T | MAY | 见 2.4 |
| `error` | R→T | MAY | 见 2.5；与成功文本互斥（error 非空时 text 可为空） |
| `simulated` | R→T | MUST | `true` = mock/模拟；B 线要求一切离线调用显式为 true |

### 2.2 `tool_event`（工具事件）

| 抽象字段 | 必需性 | 语义 |
| --- | --- | --- |
| `tool_call_id` | MUST | 与请求中工具调用一一对应的关联键 |
| `name` | MUST | 工具名（抽象：如 judge/sandbox/http-不得在 M1 使用） |
| `input` | MAY | 结构化参数（禁止真实个人数据） |
| `output` | MAY | 结构化结果或摘要（大对象应截断并给引用） |
| `status` | MUST | `OK` / `ERROR` / `TIMEOUT` / `CANCELLED`（抽象枚举） |
| `timestamp` | MAY | UTC ISO-8601；用于 trace 对齐 |

### 2.3 `session_resume`（会话恢复）

| 抽象字段 | 方向 | 必需性 | 语义 |
| --- | --- | --- | --- |
| `session_id` | T→R | MUST | 待恢复会话 |
| `last_event_id` | T→R | MAY | 从该事件之后继续（事件 id 由 2.7 定义） |
| `resume_token` | T→R | MAY | 不透明令牌；A 线可实现任意格式 |
| `resumed_from` | R→T | MAY | 实际起点（无则从头） |
| `replayed_events[]` | R→T | MAY | 恢复时补发的事件（若 A 线持有） |

需求：恢复必须**幂等**且**事件顺序可验证**；B 线可仅依赖 `last_event_id` 做去重/续传，不要求
A 线暴露内部状态。**当前 M0 是否支持 session_resume：UNVERIFIED，B 线不依赖该能力。**

### 2.4 `usage`（用量/记账）

| 抽象字段 | 必需性 | 语义 |
| --- | --- | --- |
| `prompt_tokens` | MAY | 输入 token（mock 中为合成值） |
| `completion_tokens` | MAY | 输出 token |
| `total_tokens` | MAY | 总量（若缺由 B 线按前两者推导，仅展示用途） |
| `source` | MUST（B 线要求） | `MOCK` / `REAL` / `UNKNOWN`；mock 必须标记 MOCK |
| `cost_estimate` | MAY | 仅当 `source=REAL` 且 A 线有预算语义时；M1 不使用 |

需求：用量字段只用于审计/回放展示，**不得**作为教学证据或评分输入。

### 2.5 `error`（错误语义）

抽象错误类别（B 线可据此 fail-closed/降级，具体 code 字符串 A 线可映射）：

| 类别 | 语义 | B 线预期行为 |
| --- | --- | --- |
| `TRANSPORT` | 连接/传输失败 | 重试或降级；不更新 mastery |
| `PROVIDER` | Provider 返回错误 | 记录 trace；不更新 mastery |
| `TIMEOUT` | 超时 | 取消/重试；不更新 mastery |
| `CANCELLED` | 已取消 | 终止本轮；不产生证据 |
| `INVALID_REQUEST` | 请求不合法 | 修复请求；不得静默重试 |
| `POLICY` | 策略/权限拒绝 | fail-closed，提示人工 |
| `UNKNOWN` | 未分类 | 按 UNKNOWN 处理并留痕 |

错误对象建议字段：`{category, message, retryable: bool, request_id, session_id}`。

### 2.6 `cancel`（取消语义）

- 抽象操作：`cancel(request_id)`；返回 `{cancelled: bool, reason?}`。
- 语义要求：**best-effort**；若请求已完成，取消不生效且不重复产生结果；取消后必须产生
  `CANCELLED` 终态事件（可审计）；重复取消幂等；不得因取消产生计费/副作用（M1 无计费）。
- 竞态：取消与完成并发时，以"至多一个终态"为准（B 线按 event_id 去重，不假设 A 线保证顺序）。
- **M0 cancel 能力状态：UNVERIFIED**；B 线当前 mock 通过 `{"raise": ...}` 模拟传输失败，不依赖
  真实取消。

### 2.7 `trace` 字段（教学追踪，B 线主键为 `event_id`）

| 抽象字段 | 必需性 | 语义 |
| --- | --- | --- |
| `event_id` | MUST | 全局唯一、稳定、可回放主键 |
| `loop_id` | MUST | 教学循环 id（B 线 memory 回放键） |
| `round` | MUST | 循环内轮次（从 0 起） |
| `step` | MUST | 抽象步骤名（如 plan/act/submit/diagnose/assess/memory_update） |
| `timestamp` | MUST | UTC ISO-8601（B 线格式 `YYYY-MM-DDTHH:MM:SSZ`） |
| `payload{}` | MUST | 结构化负载；必须可 JSON 序列化 |
| `payload.kind` | SHOULD | `FACT` / `INFERENCE` / `ACTION` / `OBSERVATION` / `ERROR`（区分事实与推断） |
| `payload.source` | SHOULD | 来源标签（synthetic fixture / mock runtime / judge / rubric） |
| `actor` | SHOULD | `TEACHER` / `RUNTIME` / `LEARNER` / `EVALUATOR` |
| `simulated` | SHOULD | 该事件是否来自 mock 运行时 |
| `redaction` | MAY | 脱敏说明/是否含受限字段 |

B 线现状：`m1_offline/types.py::TraceEvent` 与 `m1_offline/memory.py` 已实现
`event_id/loop_id/round/step/payload/timestamp`，并通过 `LearningMemory.append/replay/
to_jsonl/from_jsonl` 做顺序回放与持久化；`delete(learner_id)` 同时删除事实与推断事件。

## 3. B→A 教学能力需求清单（抽象；状态一律 UNVERIFIED）

> 优先级：P0 = B 线教学闭环需要（当前由 mock 满足）；P1 = 未来 live 对齐需要；P2 = 加分项。
> "A 线状态"列一律 UNVERIFIED，表示 B 线**不声称** A 线已支持。

| ID | 需求 | 优先级 | B 线理由 | A 线状态 |
| --- | --- | --- | --- | --- |
| R-01 | 稳定 `request_id` 幂等 + 可回放事件 id | P0 | 闭环回放/去重/审计 | UNVERIFIED |
| R-02 | 结构化 `tool_event` 序列（顺序保真） | P0 | CF judge/工具调用可审计 | UNVERIFIED |
| R-03 | 显式 `simulated`/`source` 标记 | P0 | 防止 mock 被当真实证据 | UNVERIFIED |
| R-04 | 错误分类（2.5 表）与可重试语义 | P0 | fail-closed/降级路径可测 | UNVERIFIED |
| R-05 | 取消语义（2.6） | P1 | 用户中断/预算保护 | UNVERIFIED |
| R-06 | usage 记账（2.4） | P1 | 成本/预算审计 | UNVERIFIED |
| R-07 | session_resume（2.3） | P1 | 长会话恢复 | UNVERIFIED |
| R-08 | trace 字段完整（2.7） | P1 | 教学决策可解释/可回放 | UNVERIFIED |
| R-09 | 零网络默认关闭（任何真实调用需显式启用+审批） | P0 | M1 离线红线 | UNVERIFIED |
| R-10 | 真实调用不得携带真实个人数据/密钥到教学层 | P0 | 隐私/安全 | UNVERIFIED |
| R-11 | 流式增量输出（可选） | P2 | 教学交互体验 | UNVERIFIED |
| R-12 | 模型侧不暴露隐藏评测用例 | P0 | public/hidden 分离 | UNVERIFIED |

## 4. 与 B 线 mock 实现的映射（当前唯一已实现部分）

| 抽象 | B 线 mock 映射 | 说明 |
| --- | --- | --- |
| `send_message` | `RuntimePort.send(RuntimeRequest) -> RuntimeResponse` | `simulated=True`；零网络 |
| 请求字段 | `request_id/session_id/messages/tools/metadata` | 已冻结在 `types.RuntimeRequest` |
| 响应字段 | `request_id/session_id/text/tool_events/usage/error/simulated` | 已冻结在 `types.RuntimeResponse` |
| 确定性 | `MockRuntimePort(script, seed)` | 同 `(seed, request)` → 同响应 |
| 错误注入 | script `{"error": ...}` / `{"raise": ...}` | 对应 2.5 TRANSPORT/PROVIDER 负例 |
| trace | `TraceEvent` + `LearningMemory` | 对应 2.7；JSONL 持久化 |

> **补充（B 线内部契约，非 A 线能力）**：`m1_offline.types.TeacherAction.kind` 的取值包含
> `LIGHT_HINT`、`INVARIANT_HINT`、`STRUCTURE_HINT`、`FULL_SOLUTION`、`SOCRATIC_QUESTION`、
> `EXPLAIN`、`PRACTICE`、`REVIEW`、`ASK_CLARIFICATION`；其中 **`PRACTICE` 为 reserved/保留值**
> （类型契约保留，当前策略不发出）。该枚举属于 B 线内部教学动作契约，不影响本文的运行时字段
> 语义，也不构成 A 线能力声明（A 线未冻结、M0 能力一律 `UNVERIFIED`）。

## 5. 版本与冻结规则

1. **版本**：本文为 `v0 draft`（`NOT_FROZEN`）。抽象类型名/语义在冻结前可变；B 线内部契约
   （`m1_offline/types.py`, `SCHEMA_VERSION=m1.offline.v0`）独立版本化，不因本文变动自动升级。
2. **冻结前置条件**（全部满足才可标 `FROZEN`）：
   - A 线提供对应的接口评审并明确支持/拒绝 R-01..R-12（逐条状态非 UNVERIFIED）；
   - B 线至少 2 名消费者（Teacher Core + 评测层）按本文语义实现并通过可回放测试；
   - 维护者批准；冻结决定记入 `docs/m1/ADR-TEACHER-CORE.md` 或后续 ADR。
3. **变更规则**：
   - 冻结后：新增**可选**字段/事件 → 小版本（v0.x，向后兼容）；删除/重命名/改语义 →
     **v1**（破坏性，需迁移说明与双版本并行期）；
   - 任何变更先改本文并标注 `CHANGELOG`，再改实现；不得实现先行。
4. **不声称规则**：无论冻结与否，**不得**以本文为证据声称 M0/A 线已实现任何能力；M0 能力状态
   一律 UNVERIFIED。B 线文档/报告引用本文时必须保留"v0 draft / A 线未冻结 / M0 UNVERIFIED"标注。
5. **只读**：本文件是只读抽象接口文档；实现细节不得写回本文（实现见
   `docs/m1/TEACHER_CORE_ARCHITECTURE.md` 与代码）。

## 6. 未决问题（待 A 线/维护者）

| # | 问题 | 影响 |
| --- | --- | --- |
| BQ1 | 事件 `event_id` 由 B 线还是 A 线生成？重试时是否稳定？ | 回放/去重正确性 |
| BQ2 | `tool_event` 的顺序保证（严格有序 vs 仅每组有序）？ | trace 可审计性 |
| BQ3 | `session_resume` 的最小语义（仅 token vs 事件补发）？ | 长会话恢复成本 |
| BQ4 | 错误分类映射表由谁维护？重试策略在 A 还是 B？ | fail-closed 行为一致性 |
| BQ5 | `usage` 的 source 枚举与预算语义何时冻结？ | 成本审计/评测 |
| BQ6 | 真实 Provider 的启用审批/出站策略？ | 安全与合规（A 线范畴） |
| BQ7 | 本文件何时冻结为 v0 正式版？ | B 线 adapter 开发排期 |

## 7. 参考（仓库内）

- `m1_offline/runtime_port.py` — mock-only 实现（`RuntimePort` 协议）。
- `m1_offline/types.py` — `RuntimeRequest` / `RuntimeResponse` / `TraceEvent` 契约。
- `m1_offline/memory.py` — trace 回放/JSONL/删除。
- `docs/m1/TEACHER_CORE_ARCHITECTURE.md` — B 线模块与失败模式。
- `docs/m1/ADR-TEACHER-CORE.md` — ADR-CORE-2/7（mock runtime、不接真实 Provider）。
