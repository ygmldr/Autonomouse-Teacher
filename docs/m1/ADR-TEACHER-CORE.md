# ADR — M1 Offline Teacher Core

| 字段 | 值 |
| --- | --- |
| ADR 状态 | `Proposed`（未冻结；由 B-Lead / 维护者决定是否接受） |
| 日期 | 2026-11-19 |
| 决策范围 | B 线 M1 Offline Teacher（`m1_offline/`）；不涉及 M0/A 线修改 |
| 相关文档 | `docs/m1/PRODUCT_SCOPE.md`, `docs/m1/TEACHER_CORE_ARCHITECTURE.md`, `docs/interfaces/teacher_runtime_boundary_v0.md` |
| 能力状态 | M0 Runtime 能力一律 UNVERIFIED；本 ADR 不声明任何 Live API 已实现 |

本 ADR 使用精简格式：**背景（Context）→ 决策（Decision）→ 备选（Alternatives）→ 后果（Consequences）**。
编号 ADR-CORE-1..7；状态均为 `Proposed`，待维护者决策。

---

## ADR-CORE-1：独立隔离包（`m1_offline/` 不依赖 M0）

### 背景
M0 是离线优先的 DSH 可行性证据工程，Live Runtime/LiveGate 能力状态未验收。M1 若直接复用 M0
代码，会把"未验收的运行时能力"当作既有事实，且让教学层与运行时耦合、难以独立评审与回放。

### 决策
M1 Teacher Core 实现为仓库内**独立包** `m1_offline/`：

- 禁止 `import autoteacher_m0` 或 `src` 下 M0 模块（静态 AST + fresh subprocess 双重测试）。
- 不修改 M0 的 `src/autoteacher_m0/**`、`plugins/**`、`config/**`、`scripts/**`、LiveGate、
  M0 测试/配置。
- M1 的依赖仅 stdlib（+ pytest 仅测试）；不依赖真实 Provider SDK。
- M1 通过**抽象 RuntimePort**（ADR-CORE-2）而非 M0 具体实现来使用"运行时"。

### 备选
- A. 直接 import/reuse M0 Runtime：实现快，但把未验收能力引入教学层，边界不可审计。放弃。
- B. fork M0 代码进 M1：产生双份维护与历史/凭据泄漏风险。放弃。
- C. 独立包 + 抽象边界（采纳）。

### 后果
- ✅ M1 可独立运行、测试、评审；M0 状态保持 UNVERIFIED 不被污染。
- ✅ 未来若 A 线冻结 Runtime 接口，M1 只需新增 adapter，不改 Teacher Core。
- ⚠️ 需要自建类型/契约/测试双份边界检查（成本已由 `test_no_m0_import.py` 覆盖）。
- ⚠️ 不能声称"M0 能力已被 M1 使用/验证"。

---

## ADR-CORE-2：Mock Runtime Port（零网络、确定性、`simulated=True`）

### 背景
M1 必须离线、可回放、零真实调用；但教学闭环需要"模型响应"这一环节来演示/评测。若不留运行时
边界，教学层会直接拼字符串，无法替换、无法证明零网络。

### 决策
定义 `RuntimePort` 协议（`send(RuntimeRequest) -> RuntimeResponse`）与默认实现
`MockRuntimePort(script=None, seed=0)`：

- 零网络：模块不 import 网络栈；测试静态+运行时双重验证。
- 确定性：同 `(seed, request)` → 同响应；生成文本/usage 由 sha256 派生。
- 脚本回放：`responses`（request_id 精确匹配）/`queue`/`default`/`error`/`raise`。
- `simulated=True`：所有响应显式标记 mock，避免被误当真实 provider 证据。
- 真实 adapter 未来只能新增实现，不得修改 Teacher Core；是否启用属 M0/A 线决策（UNVERIFIED）。

### 备选
- A. 无端口、直接内联文本：无法替换/审计。放弃。
- B. 直接调用真实 Provider：违反离线/无 Key 约束。放弃。
- C. 协议 + mock 实现（采纳）。

### 后果
- ✅ 闭环/回放/负例（错误注入）可测；零网络可证明。
- ✅ 与 docs/interfaces/teacher_runtime_boundary_v0.md 的抽象 B→A 需求对齐。
- ⚠️ mock 输出不代表真实模型质量；所有结论限定 synthetic。
- ⚠️ live adapter 的凭据/出站策略属于 A 线，M1 不实现、不验收。

---

## ADR-CORE-3：证据驱动 Learner Model（无证据不涨、重复不迁移）

### 背景
教学系统最常见失败模式是"把模型说得好听当成学会"或"同题重复当成能力迁移"。M1 的核心产品
主张是证据驱动；如果 mastery 可由模型文本直接更新，整个可解释/可回放主张失效。

### 决策
`LearnerModel` 只接受 `EvidenceEvent`：

- 只有 `observed_score` 存在且 kind ∈ `ANSWER/CODE_SUBMISSION/EXPLANATION/INTERVIEW_RESPONSE/
  ASSESSMENT` 才更新 mastery；`HINT_REQUEST`/无分数事件只计数。
- **失败证据 fail-closed**：带 `error_codes` 的观测视为失败/部分失败，只允许下调或保持
  mastery，绝不上调（失败不能证明进步）；无 error 码的观测才按滑动平均双向更新。
- 无证据 → mastery 为空；无 skill 映射 → 只计数不涨。
- 每个 task 绑定技能集（首事件 `payload.skill_ids` 或显式 `register_task_skills`）；超出绑定集的
  技能**永不记分**（防跨技能迁移幻觉）。
- 同 task 重复观测收益递减（`REPEAT_CREDIT_FACTOR=0.25`），只巩固不迁移。
- 同 `event_id` 幂等（at-least-once 投递不重复计）。
- `replay(events)` 从干净模型按序重放，`updated_at` 取最后事件时间 → 确定性。

### 备选
- A. 用模型文本/自评更新 mastery：违背产品红线。放弃。
- B. 完整 IRT/BKT 心理测量模型：数据不足且无法验证效度，超出 M1 范围。放弃（记录为未来）。
- C. 有界滑动平均 + 证据规则（采纳）。

### 后果
- ✅ 可审计、可回放、可测试；"无证据不涨/重复不迁移"有测试证据。
- ⚠️ 数值是 synthetic proxy，**无效度声明**；不用于真实能力评估结论。
- ⚠️ 错误计数键约定存在两种（error code 或 skill）；跨模块消费方以 max(两种) 解释（教学策略/
  诊断已这样处理并在文档注明）。

---

## ADR-CORE-4：Hint Ladder（默认 LIGHT、升级需证据、绝不默认 FULL_SOLUTION）

### 背景
教学产品若默认直接给完整答案，会剥夺学习机会且不可解释；但若不敢升级又无法帮助卡住的学习者。
需要显式的、可审计的干预强度阶梯。

### 决策
`teaching_policy` 定义固定阶梯与安全门：

- 阶梯：`LIGHT_HINT → INVARIANT_HINT → STRUCTURE_HINT → FULL_SOLUTION`（1..4）。
- 默认 `hint_level=1` → `LIGHT_HINT`；`FULL_SOLUTION` 是最后手段，**只接受显式 L4 请求**；
  自适应升级本身永不跨入 FULL_SOLUTION。
- `EvidenceGate`（按证据量，不要求成功）：无证据封顶 L1；1 条证据 L2；2–4 条 L3；≥5 条才允许 L4。
  **无论请求什么 level，都不能越过证据门**。
- `FixedPolicy`（teacher_v0）：非自适应，按阶梯 + 安全门输出 hint。
- `AdaptivePolicy`（teacher_v1）：诊断/证据自适应（REVIEW/ASK_CLARIFICATION/EXPLAIN/
  SOCRATIC_QUESTION/复习/重复错误升级：≥2 条错误升 1 级、≥4 条升 2 级，仍受证据门约束且不跨入
  FULL_SOLUTION），新学习者仍强制 LIGHT_HINT 安全下限。
- 每个 action 带 rationale（请求 rung、安全门、证据依据、"never by default" 安全说明），可审计。

### 备选
- A. 纯 Prompt 指令"先给提示"：不可测试、可被绕过。放弃。
- B. 全自适应无安全门：新学习者可能被直接灌完整答案。放弃。
- C. 固定阶梯 + 证据门 + 两版策略（采纳，支持 v0/v1 对比实验）。

### 后果
- ✅ 安全属性可单元测试；v0/v1 差异明确，可供评测层比较。
- ✅ 与 ADR-CORE-3 证据流一致（安全门只读 LearnerState）。
- ⚠️ 策略是规则系统，覆盖有限；未覆盖情形走 UNKNOWN/NEEDS_REVIEW/澄清。
- ⚠️ 门槛数值（0.35/0.70/重复阈值 2）是工程启发式，非学习科学结论，可维护者调整。

---

## ADR-CORE-5：独立评测器（teacher 与 evaluator 分离）

### 背景
若教练/教学策略自评，闭环评测会退化为自我确认。M1 的交付价值是"可评测性"，必须让评分独立于
被评对象。

### 决策
- 评测层（b-eval）与教学层分离：独立 scorer 文件与固定 rubric；teacher 不计算/不注入分数。
- `AssessmentResult` 由独立 scorer_id 产出；`EvidenceEvent.observed_score` 必须来自 judge/
  rubric 产物（b-cf 的本地隐藏用例 judge、b-interview 的 rubric）。
- 评测 harness 只消费教学层公开输出（action/trace/state），不依赖其内部实现。
- v0/v1 对比在固定 case/seed 下进行，报告只给 synthetic 结论。

### 备选
- A. teacher 内自带评分：实现简单但自我确认，评测无意义。放弃。
- B. 人工评分：M1 离线自动化无法承载。放弃。
- C. 独立评测层 + 固定 rubric/judge（采纳）。

### 后果
- ✅ 评测结论可追溯；failure modes 可复现。
- ⚠️ 仍需评审确认"独立"在代码层面成立（b-eval 测试/评审责任）。
- ⚠️ rubric/judge 本身是 synthetic 规则，不能外推真实教学效果。

---

## ADR-CORE-6：public / hidden 分离（防泄漏与污染）

### 背景
题目/答案/隐藏用例若对 teacher 可见，多轮教学可能"猜到答案"；评测若与训练/可见面混用，结果
失真。M1 需要最小但真实的分离纪律。

### 决策
- fixtures 中 `hidden/` 路径段标记隐藏集，teacher 只读 public 面；judge 仅用隐藏用例判定 AC/pass。
- 污染检查（b-eval `contamination.py`）扫描 public 面是否泄漏 hidden 片段、真实个人数据、网络
  import；隐藏内容证据只留 hash/偏移，不回显。
- `status` 三态 `PASS/FAIL/NOT_RUN`：输入缺失时 NOT_RUN，绝不静默 PASS。
- 严格规则同样适用于 `tests/m1_offline/**/*.py`（例如网络 import 扫描）——所有 Agent 的测试
  文件也必须满足，避免测试代码成为"绕过通道"。

### 备选
- A. 不分离（所有 fixtures 公开）：实现简单但污染/泄漏不可控。放弃。
- B. 加密隐藏集：密钥管理超出离线 demo 范围。放弃。
- C. 路径段 + 扫描器分离（采纳，最小可行）。

### 后果
- ✅ 污染/泄漏可自动检查，评测可信度提高。
- ⚠️ 分离只是工程纪律，不构成真实考试安全；结论限定离线 synthetic。
- ⚠️ 扫描规则需随实现演进维护（例如测试代码中的网络 import 也会被拦截 — 已按此执行）。

---

## ADR-CORE-7：不接真实 Provider（离线 mock-only，能力状态 UNVERIFIED）

### 背景
本阶段目标是验证"离线教学机制与评测可行性"，而非上线。真实 provider 接入会引入密钥、计费、
网络、合规与不可复现等风险，且 M0/A 线的 Live 能力尚未验收。

### 决策
- M1 全程 mock-only：默认且唯一的运行时实现是 `MockRuntimePort`；真实 provider 调用不在范围内。
- 无 API Key、无 `httpx/requests/urllib/aiohttp/socket` 出站（静态 + 运行时检查）。
- 所有输出显式 `simulated=True`；文档/报告必须写 "offline synthetic only, not real teaching effect"。
- M0/A 线 Live 能力一律 UNVERIFIED；M1 不声明、不复用、不验收。
- 未来 live adapter 须另立 ADR/接口冻结（docs/interfaces/teacher_runtime_boundary_v0.md），并
  经维护者批准。

### 备选
- A. 接真实 Provider 做小规模验证：违反本阶段约束，且会污染"离线可复现"证据。放弃。
- B. 用本地开源小模型推理：依赖/硬件/许可不可控，且仍非"离线教学机制"必需。放弃（记录为未来）。
- C. 纯 mock + 抽象边界（采纳）。

### 后果
- ✅ 100% 离线、可复现、零密钥/零出站风险；评审可完全本地复跑。
- ⚠️ 不能回答"真实模型教学效果如何"；需后续阶段（A 线 Live + 人工评审）另行验证。
- ⚠️ 所有成功指标只能证明机制/闭环/评测，不证明学习增益。

---

## 未决问题（Open Questions）

| # | 问题 | 影响 | 建议决策者 |
| --- | --- | --- | --- |
| Q1 | Hint 阶梯证据门槛（0.35/0.70/≥5 事件/重复阈值 2）是否需要数据校准？ | 影响教学安全 vs 帮助效果 | 维护者 + 教学负责人 |
| Q2 | learner 错误计数键统一为 error code 还是 skill id？ | 跨模块语义一致性 | B-Lead（契约升级） |
| Q3 | public/hidden 的判定是否足够（仅路径段标记）？是否需要 fixture 级 manifest？ | 污染检查强度 | 维护者 + b-eval |
| Q4 | 评测 rubric 的维度权重与盲评流程由谁维护？ | v0/v1 对比可信度 | b-eval + 维护者 |
| Q5 | 未来 live adapter 的 Provider/预算/出站策略边界？ | A 线接口冻结前置 | A 线 + 维护者 |
| Q6 | `fixtures/m1/` 许可标注格式是否统一到 manifest？ | B-06/B-07 验收 | fixtures 所有者 + B-Lead |
| Q7 | M1 是否需要在 CI 中强制执行 contamination/无 M0 import 检查？ | 长期回归保护 | 维护者 |

## 需维护者决策项（Decision Requests）

1. **接受/拒绝 ADR-CORE-1..7 状态**（当前全部 `Proposed`）；接受后是否冻结 v0 契约。
2. **Q1 证据门槛**：是否按计划值先行，待评测阶段再校准；若调整，须同步测试与文档。
3. **Q2 错误计数键**：是否将 `LearnerState.error_counts` 语义写死为一种键（会触发契约版本升级）。
4. **Q7 CI 门禁**：是否把 `tests/m1_offline/test_no_m0_import.py`、
   `test_contamination.py`（含 tests 目录扫描）纳入合并前必跑。
5. **A/B 线接口冻结**：`docs/interfaces/teacher_runtime_boundary_v0.md` 何时从 draft 冻结；
   A 线未冻结前，M1 不得声称 M0 能力已实现或已验收。
