# M1 Offline Teacher — Product Scope (v0 draft)

| 字段 | 值 |
| --- | --- |
| 文档状态 | `DRAFT` / `NOT_FROZEN` |
| 版本 | v0（2026-11-19） |
| 负责范围 | B 线（M1 Offline Teacher）产品边界与验收矩阵；本文件由 b-core 起草，B-Lead 验收 |
| 证据状态 | 本文件中的验收矩阵初始状态一律 `NOT_RUN`；只有 B-Lead 依据真实命令输出才能改为 `PASS`/`PARTIAL` |
| 能力声明 | M0 Runtime 能力状态一律 UNVERIFIED；本文件不声明任何 Live Provider / M0 API 已实现或已验收 |
| 数据 | 全部使用 Synthetic 或自编 CC0-1.0 数据；禁止真实个人数据、真实简历、真实 API Key |

## 1. 产品问题（这不是通用 ChatBot）

M1 Offline Teacher 要回答的产品问题是：

> 在**完全离线、无真实 Provider、无真实 API Key、零网络出站**的前提下，能否构建一个
> **可教学、可解释、可回放、可评测**的 AI 教学引擎（Teacher Core），并以两个垂直场景
> （CF Teacher、Interview Coach）证明其能力边界？

它**不是**通用聊天机器人，也不是"把 Prompt 包一层 UI"。它必须满足四条产品级约束：

1. **教学不是聊天**：每个教学动作（action）必须由学习者状态 + 证据 + 策略驱动，并解释"为什么现在给这一步"。
2. **证据驱动**：没有证据不得提升掌握度；模型输出的"听起来像学会了"不构成证据。
3. **可回放**：任意一次教学循环必须能由事件流（trace）确定性重放，用于评测与审计。
4. **诚实边界**：离线 synthetic 环境只能证明"机制/闭环/可评测"，**不能**证明真实教学效果；所有外推结论必须标注限制。

## 2. 用户场景与用户故事

### 2.1 场景 A：CF Teacher（算法竞赛教练）

用户画像：synthetic learner（`learner-001`，`BEGINNER`/`INTERMEDIATE`/`ADVANCED` 三档基线），
在离线沙箱中做题；题目为自编 CC0-1.0 题目与隐藏用例。

用户故事：

- **US-CF-1 诊断**：作为学习者，我提交代码/答案后，系统给出**规则可解释**的错误分类（如
  `off_by_one`、`wrong_complexity`、`wrong_data_structure`、`edge_case`、`conceptual_gap`），
  无法判断时明确返回 `UNKNOWN` 或 `NEEDS_REVIEW`，而不是瞎猜。
- **US-CF-2 提示阶梯**：作为学习者，我默认只得到 `LIGHT_HINT`；只有我已有证据（尝试次数、
  掌握度）时，提示才允许逐级升级 `LIGHT_HINT → INVARIANT_HINT → STRUCTURE_HINT →
  FULL_SOLUTION`；系统绝不默认直接给完整答案。
- **US-CF-3 判定边界**：作为学习者，我是否通过只由**独立本地 judge** 对隐藏用例的判定决定
  （AC/WA/TLE/RE），教练不得用"看起来对"代替 judge 结论。
- **US-CF-4 不迁移幻觉**：作为学习者，同一道题重复做对不会被当成其他知识点的掌握（无证据的
  迁移能力一律不记）；重复观测只带来递减的巩固收益。
- **US-CF-5 复习节奏**：作为学习者，我的学习计划同时包含**复习**（已掌握但需保持）与**新知**
  （目标技能未掌握），占比可解释、可回滚（`policy_version`）。

### 2.2 场景 B：Interview Coach（面试教练 + 知识新鲜度）

用户画像：synthetic 求职者（无真实简历/公司/项目数据），在离线多轮对话中练习面试回答；
JD、知识来源、题目均为自编 synthetic 数据。

用户故事：

- **US-IC-1 多轮追问阶梯**：作为求职者，我得到的追问按
  `concept → hypothesis → complexity → experiment-design → online-triage` 阶梯推进，而不是一次问完。
- **US-IC-2 独立评分**：作为求职者，我的回答由**独立 rubric 评分器**按
  `factual_correctness / explanation_clarity / engineering_feasibility / evidence_sufficiency`
  四个维度确定性打分；教练不得自评自夸。
- **US-IC-3 项目事实边界**：作为求职者，当问题涉及我未提供的项目事实（规模、百分比、真实
  经历）时，教练必须**提问澄清（ASK_CLARIFICATION）**，不得编造或替我说出经历。
- **US-IC-4 知识新鲜度**：作为求职者，当知识来源过期（`valid_until` 已过）、冲突
  （`CONFLICT`）或状态未知时，系统必须标 `RECHECK`/`EXPIRED` 而不是静默污染课程内容；
  `published_at` 与 `observed_at` 必须分开记录。
- **US-IC-5 注入防护**：作为系统，来自 JD/网页片段的指令一律视为**不可信数据**，不得改写
  系统指令、权限或评分规则（离线 prompt-injection 负例集）。

## 3. 非目标（明确不做）

1. 不接入真实 Provider / 真实 API Key / 真实网络（httpx、requests、socket 等一律禁止出站）。
2. 不实现或声称实现 M0 Live Runtime / LiveGate / Provider Bridge 的验收能力；相关能力一律 `UNVERIFIED`。
3. 不做通用聊天机器人、不做开放域问答产品、不做"AI 导师自动批改真实作业"的生产系统。
4. 不收集/存储真实个人数据、真实简历、真实公司内部信息。
5. 不声明真实教学效果（learning gain）——离线 synthetic 闭环只能证明机制与可评测性。
6. 不做 Web 产品化（UI/账号/多租户/计费/上线），Demo 仅限 `python -m m1_offline.demo` 离线运行。
7. 不做心理学/测量学意义上的能力评估效度声明。
8. 不修改 M0 代码/测试/LiveGate/配置；M1 是独立隔离包。

## 4. 不可接受行为清单（fail-closed 红线）

| # | 不可接受行为 | 期望行为 | 执行机制（计划/已落地） |
| --- | --- | --- | --- |
| 1 | 无证据直接给 `FULL_SOLUTION` | 默认 `LIGHT_HINT`；完整答案必须显式请求且有证据门槛 | `teaching_policy.EvidenceGate` + 测试 |
| 2 | 新学习者被默认当成已掌握 | `evidence_count == 0` 时 mastery 为空，策略封顶 L1 | `learner_model` + 测试 |
| 2b | 失败/带错误码的观测被当成进步 | 带 `error_codes` 的证据只降/不升 mastery | `learner_model` + 测试 |
| 3 | 同题重复做对 → 认证其他技能 | 任务绑定技能集；重复收益递减；超出绑定技能不记 | `learner_model` 转移守卫 + 测试 |
| 4 | 伪造 `PASS` / 自评通过 | 通过只来自独立 judge 的隐藏用例；未真实运行标 `NOT_RUN` | 文档纪律 + b-cf/b-eval 测试 |
| 5 | 教练自己给自己打分 | 评分器独立（rubric/scorer 与 teacher 分离） | b-interview/b-eval 验收 |
| 6 | 真实网络出站 / 真实 Key | 全部 mock；静态+运行时零网络检查 | `test_no_m0_import.py` + Runtime Port 测试 |
| 7 | import M0 代码或依赖 M0 Runtime | 独立包，禁止 `autoteacher_m0` import | `test_no_m0_import.py` |
| 8 | 声称 M0 已有 Live API/已验收 | 一律 `UNVERIFIED` + 抽象接口文档 | `docs/interfaces/teacher_runtime_boundary_v0.md` |
| 9 | 使用真实个人/简历数据 | 仅 synthetic / CC0-1.0；无真实身份字段 | fixtures 许可声明 + 评审 |
| 10 | 知识过期/冲突仍静默进入课程 | `EXPIRED`/`CONFLICT` → `RECHECK`，不静默污染 | freshness（b-interview） |
| 11 | 把 prompt-injection 当指令执行 | 一律按不可信数据处理 | injection 负例（b-interview） |
| 12 | 不可回放/不可解释的教学动作 | 每个 action 带 rationale + trace event；事件可按 event_id 回放 | `memory` + `teaching_policy` |
| 13 | 编造测试结果/覆盖率 | 只记录真实命令输出；计划值单列 | 文档纪律 |
| 14 | 删除学习者数据时残留推断数据 | `delete(learner_id)` 同时删除 FACT 与 INFERENCE 并返回数量 | `memory.delete` + 测试 |

## 5. 数据与许可 / 隐私策略

- **数据来源**：所有 fixture（题目、隐藏用例、JD、知识更新、问答语料、学习者画像）必须为
  **自编 synthetic** 或 **CC0-1.0** 许可；不得引入第三方受限数据集、真实简历、真实公司资料。
- **许可标注**：每个 fixture 目录/文件需在 spec 或目录 README 标注 `license: CC0-1.0`（或
  "self-authored synthetic"）与来源说明；B 线统一由 fixtures 所有者维护。
- **个人数据**：学习者 id（如 `learner-001`）为 synthetic；禁止真实姓名、邮箱、电话、公司、
  项目规模等可识别信息。任何"项目事实"缺失时，Interview Coach 必须提问澄清而非编造。
- **隐私操作**：`LearningMemory.delete(learner_id)` 提供 synthetic 级"被遗忘权"原语，同时删除
  事实与推断事件并返回删除数量；`to_jsonl` 轨迹不含密钥/真实身份。
- **Secrets**：仓库/代码/文档/fixtures 中不得出现真实 API Key、token、cookie；`.env.example`
  不得包含真实值。M1 不读取任何真实凭据。
- **网络**：M1 包禁止任何真实网络出站（静态 AST 检查 + 运行时 monkeypatch 检查）；Provider
  调用仅经 `MockRuntimePort`，且响应 `simulated=True`。
- **M0 数据**：M0 能力/数据状态一律 `UNVERIFIED`；M1 不复制 M0 的真实运行数据。

## 6. 成功指标（全部为**计划值**；真实结果以命令输出为准）

> 规则：本节数值均为**计划目标（plan values）**，不是已经达成的 PASS；只有 B-Lead 复核真实
> 命令输出后，才能在验收矩阵中标记 VERIFIED/PARTIAL。任何"真实教学效果"不在此列。

| 指标 | 计划值（plan value） | 当前证据 / 状态 |
| --- | --- | --- |
| b-core 8 个测试文件真实通过 | 100% 通过，0 skip（计划值） | 真实运行 161 passed（见 §8 命令；非最终验收） |
| M1 包网络类 import 数 | 0（计划值） | 静态 AST + fresh subprocess 检查通过（b-core 测试） |
| M1 包 `autoteacher_m0` import 数 | 0（计划值） | 同上 |
| Hint Ladder 安全违规（无证据/默认 FULL_SOLUTION） | 0 次（计划值） | b-core 单元级覆盖通过；端到端 NOT_RUN |
| 无证据提升 mastery 的次数 | 0（计划值） | b-core 单元级覆盖通过 |
| 失败证据（带 error_codes）上调 mastery 的次数 | 0（计划值） | b-core 单元级覆盖通过 |
| 同题重复 → 跨技能迁移次数 | 0（计划值） | b-core 单元级覆盖通过 |
| 核心模块测试覆盖率 | ≥ 80%（计划值，B-Lead 决定是否测量） | NOT_RUN（未测量） |
| CF Teacher fixtures 数量 | ≥ 12 道题 + 隐藏用例（计划值） | b-cf 负责；验收 NOT_RUN |
| Interview 题库数量 | ≥ 20 题 + ≥ 6 版本 JD + ≥ 6 知识更新（计划值） | b-interview 负责；验收 NOT_RUN |
| 闭环轮次 | ≥ 3 轮且可回放（计划值） | b-eval 负责；验收 NOT_RUN |
| v0/v1 对比 | 固定 seed、可复现、明确 synthetic-only 结论（计划值） | b-eval 负责；验收 NOT_RUN |
| demo 确定性 | 连续 2 次 `python -m m1_offline.demo` 输出一致（计划值） | b-eval 负责；验收 NOT_RUN |
| 真实教学效果 | 不承诺（非目标） | 永远不声明 |

## 7. 交付物清单（B 线）

| 交付物 | 路径 | 所有者 | 状态 |
| --- | --- | --- | --- |
| 共享类型/契约 | `m1_offline/types.py` | b-core | 已落地，b-core 测试通过 |
| 包入口/常量 | `m1_offline/__init__.py` | b-core | 已落地 |
| Mock Runtime Port | `m1_offline/runtime_port.py` | b-core | 已落地，测试通过 |
| 证据驱动 Learner Model | `m1_offline/learner_model.py` | b-core | 已落地，测试通过 |
| 教学策略 / Hint Ladder | `m1_offline/teaching_policy.py` | b-core | 已落地，测试通过 |
| 课程规划器 | `m1_offline/curriculum_planner.py` | b-core | 已落地，测试通过 |
| 事件记忆 | `m1_offline/memory.py` | b-core | 已落地，测试通过 |
| 规则诊断引擎 | `m1_offline/diagnostics.py` | b-core | 已落地，测试通过 |
| CF Teacher（fixtures/judge/teacher） | `m1_offline/cf/`, `fixtures/m1/cf/` | b-cf | 开发中；验收 NOT_RUN |
| Interview Coach / Freshness | `m1_offline/interview/`, `m1_offline/freshness.py`, `fixtures/m1/interview/` | b-interview | 开发中；验收 NOT_RUN |
| 评测/闭环/demo | `m1_offline/evaluation/`, `m1_offline/demo.py` | b-eval | 开发中；验收 NOT_RUN |
| 本文件（产品范围） | `docs/m1/PRODUCT_SCOPE.md` | b-core | 已落地（v0 draft） |
| Teacher Core 架构 | `docs/m1/TEACHER_CORE_ARCHITECTURE.md` | b-core | 已落地（v0 draft） |
| 决策记录（ADR） | `docs/m1/ADR-TEACHER-CORE.md` | b-core | 已落地（Proposed） |
| Runtime 边界（只读抽象） | `docs/interfaces/teacher_runtime_boundary_v0.md` | b-core | 已落地（v0 draft, NOT_FROZEN） |

## 8. 验收矩阵映射（B-01..B-08，初始 NOT_RUN）

> 说明：B-01..B-08 的**行归属**为本文件的工作假设（b-core 起草），最终以 B-Lead 验收矩阵为准。
> 列 "本地证据" 仅记录已完成真实命令的运行结果，**不等于**验收结论；"验收状态"列在 B-Lead
> 复核前一律为 `NOT_RUN`。命令：`cd /root/at-m1-offline && "/root/Autonomous Teacher/.venv/bin/python"
> -m pytest <files> -q`。

| ID | 验收项 | 交付物/证据文件 | 本地证据（真实运行，非验收） | 验收状态（初始） |
| --- | --- | --- | --- | --- |
| B-01 | 独立离线包与隔离：无 M0 import、无网络 import、零网络出站 | `m1_offline/__init__.py`, `tests/m1_offline/test_no_m0_import.py` | 2 个 test 文件通过（静态 AST + fresh subprocess） | NOT_RUN |
| B-02 | 类型/契约层：schema_version、全类型 JSON 无损往返、枚举/必填校验、provenance | `m1_offline/types.py`, `tests/m1_offline/test_schema.py` | `test_schema.py` 通过（16 类型往返 + fail-closed） | NOT_RUN |
| B-03 | Mock Runtime Port：确定性、`simulated=True`、错误注入、零网络 | `m1_offline/runtime_port.py`, `tests/m1_offline/test_runtime_port.py` | `test_runtime_port.py` 通过 | NOT_RUN |
| B-04 | 证据驱动 Learner Model + 规则诊断：无证据不涨、失败不涨、重复不迁移、UNKNOWN/NEEDS_REVIEW | `m1_offline/learner_model.py`, `m1_offline/diagnostics.py`, `test_learner_model.py`, `test_diagnostics.py` | 2 个 test 文件通过 | NOT_RUN |
| B-05 | 教学策略/Hint Ladder + 课程规划/记忆：默认 LIGHT、升级需证据、rationale/balance/policy_version、jsonl/delete | `m1_offline/teaching_policy.py`, `curriculum_planner.py`, `memory.py`, 对应 3 个测试 | 3 个 test 文件通过 | NOT_RUN |
| B-06 | CF Teacher 端到端：≥12 synthetic 题 + 隐藏用例、独立 judge、多轮教学动作、spec | `m1_offline/cf/**`, `fixtures/m1/cf/**`, `docs/m1/CF_TEACHER_SPEC.md`, b-cf 测试 | 未运行（b-cf 交付后由 B-Lead 复跑） | NOT_RUN |
| B-07 | Interview Coach + Freshness：≥20 题、多轮追问、独立 rubric、项目事实边界、新鲜度、注入负例 | `m1_offline/interview/**`, `m1_offline/freshness.py`, `fixtures/m1/interview/**`, b-interview 文档/测试 | 未运行（b-interview 交付后复跑） | NOT_RUN |
| B-08 | 离线评测闭环：≥3 轮闭环、按 event_id 回放、独立评测器、public/hidden 分离、污染/负例、v0/v1 对比、demo、诚实结论 | `m1_offline/evaluation/**`, `m1_offline/demo.py`, `docs/m1/EVALUATION_PROTOCOL.md`, b-eval 测试 | 未运行（b-eval 交付后复跑） | NOT_RUN |

## 9. 风险与依赖

- **依赖**：B-04/B-05 的跨模块 API 已由 b-core 冻结在 v0（见架构文档 §3）；b-cf/b-interview/b-eval
  只读消费，如需变更须先经 B-Lead 决定契约升级。
- **风险 1**：fixtures 许可/来源若未标注，B-06/B-07/B-08 验收无法通过 → 由 fixtures 所有者补齐。
- **风险 2**：`fixtures/m1/` 目前由其他 Agent 创建；b-core 只引用 `FIXTURES_DIR` 常量，不写 fixtures。
- **风险 3**：M0/Live 能力被误读为已验收 → 所有文档强制 `UNVERIFIED` 标注。
- **风险 4**：真实教学效果不可由本环境证明 → 所有结论限定 "offline synthetic only"。
