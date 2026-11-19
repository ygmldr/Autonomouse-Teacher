# Interview Coach 离线能力规格（M1 Offline Teacher）

- 版本：`m1.offline.v0`（schema version 与 `m1_offline/types.py` 一致）
- 所有者：B 线 `b-interview`（task-3）
- 代码：`m1_offline/interview/{__init__,coach,rubric}.py`
- Fixtures：`fixtures/m1/interview/{questions,jds,knowledge,injection,answers,hidden}/`
- 策略文档：`docs/m1/FRESHNESS_AND_SOURCE_POLICY.md`
- 状态：**OFFLINE-ONLY / SYNTHETIC**。没有任何真实 Provider、真实网络、真实简历/招聘数据参与；M0 Runtime API 一律 **UNVERIFIED**。

## 1. 目标

1. 在完全离线、确定性的条件下验证“面试教练”三层能力：
   - **追问**：按 概念 → 假设 → 复杂度 → 实验设计 → 线上定位 的苏格拉底式梯子推进；
   - **评分**：用独立、确定性的四维 Rubric 评估回答，评分器不调用 Runtime、不用教练自己生成的话当证据；
   - **边界**：不替学习者虚构项目规模、提升百分比、业务成绩；缺少项目事实时先追问。
2. 验证“知识时效性/来源可信度”最小闭环：`KEEP / UPDATE / RECHECK` 分类、发布时间与观测时间的区分、冲突/过期不静默污染课程。
3. 验证 Prompt Injection 防御：不可信文档只能作为引用数据（DATA_ONLY），不能改变系统指令、权限、评分或追问行为。
4. 为 `b-eval` 提供可被 import、可重复运行的 Coach/Rubric/Freshness 接口。

## 2. 非目标

- 不接真实 LLM/Provider（`RuntimePort` 仅 Mock，且本模块**不调用**它）。
- 不使用真实简历、真实招聘 JD、真实公司/人名；所有 fixture 为自编 Synthetic、许可 CC0-1.0。
- 不做真实“本周热点”数据更新，不声称知识库已与真实外部世界同步。
- 不做人类评分校准；`passed` 阈值是离线工程阈值，不是招聘结论。
- 不修改 `m1_offline/types.py`（b-core 单写者）；若未来需要新字段，先走 schema 变更流程。

## 3. 追问梯子（Follow-up Ladder）

`InterviewCoach.LADDER_STAGES = ("concept", "hypothesis", "complexity", "experiment_design", "online_triage")`。
阶段由“对话中学习者回答轮数”确定：`stage = min(max(learner_turns - 1, 0), 4)`；超过 5 轮后**封顶在线上定位**，不会自造新阶段。

| # | stage | 中文标签 | 意图 | `rationale` 必须说明 |
|---|-------|----------|------|----------------------|
| 1 | `concept` | 概念澄清 | 先定义概念，避免错误前提 | 阶段序号/名称、为什么先固定概念 |
| 2 | `hypothesis` | 可证伪假设 | 把概念落到可验证假设 | 区分事实/假设/猜测 |
| 3 | `complexity` | 复杂度与量级 | 数据量、延迟、成本量级 | 防止空泛方案 |
| 4 | `experiment_design` | 实验设计 | 离线指标 + 线上 A/B、样本、护栏 | 实验可执行性 |
| 5 | `online_triage` | 线上定位 | 观测面与故障定位顺序 | 工程闭环能力 |

实现约定：

- `follow_up()` 返回 `TeacherAction(kind="SOCRATIC_QUESTION")`，`content` 取自 fixture 的 `follow_up_ladder[stage]`，**只提问不给答案**。
- `TeacherAction.hint_level` 属于“教学提示梯子”（合法范围 1..4），与面试追问梯子不是一回事，因此这里保持 `None`；阶段信息写入 `rationale`（形如 `追问梯子第 3/5 阶段「复杂度与量级」`）。
- `target_skill_ids` 由 track/topic 确定性生成；`evidence_refs` 只引用题目 fixture，不引用教练自己生成的内容。

## 4. 四维 Rubric（独立评分器）

`InterviewRubric` 只依赖 Python 标准库，不 import Runtime；相同输入产生逐字节一致的分数/反馈/失败模式。

| 维度 | 打分信号（互相独立） | 主要失败模式 |
|------|----------------------|--------------|
| `factual_correctness` | 题目 `rubric_points[dim]` 的 token 组覆盖率；`misconceptions` 扣分 | `incorrect_concept`、`misconceived_claim` |
| `explanation_clarity` | 长度、句子数、结构连接词、分段、模糊措辞惩罚 | `vague_explanation` |
| `engineering_feasibility` | 约束/量级 token 覆盖 + 具体数字量级加分 − 不可行设计标记扣分 | `infeasible_engineering_design` |
| `evidence_sufficiency` | `evidence_refs`、结构化 `quantitative_claims`（是否带来源）、`project_facts`、无来源量化说法惩罚 | `unsourced_quantitative_claim`、`missing_project_facts`、`insufficient_evidence` |

其他约定：

- 每个维度输出 `[0,1]` 浮点；`score()` 返回四个维度，`feedback()` 返回确定性人类可读列表，`failure_modes()` 返回规范化失败模式码。
- **无证据的虚构数字**（如“CTR 提升 37%”“P99 从 820ms 降到 190ms”但 `evidence_refs=[]`）只压低 `evidence_sufficiency` 并触发 `unsourced_quantitative_claim`，不改变事实维度关键词覆盖——维度相互独立。
- `InterviewCoach.assess_answer()` 只调用注入的 Rubric（可用测试替身证明调用参数就是原始 question/answer），`scorer_id` 记录来源（默认 `InterviewRubric:m1.offline.v0`）。
- 综合分权重：`factual 0.35 / clarity 0.20 / feasibility 0.20 / evidence 0.25`；`passed = score >= 0.65 且 factual >= 0.5`（离线工程阈值，非招聘结论）。

## 5. 项目事实边界（Project-Fact Boundary）

- 题目 fixture 用 `requires_project_facts: true` 标记“必须基于真实项目经历”的题（如延迟优化、A/B 实验经历）。
- 当此类题目在对话中**缺少可核验项目事实**（角色 + 具体规模/指标 + 来源），`follow_up()` 返回 `TeacherAction(kind="ASK_CLARIFICATION")`：
  要求学习者补充：项目/角色、线上规模量级、负责部分与优化前后指标、可核验来源；并明确“缺失项直接说没有”。
- 教练**不得**替学习者补全规模、提升百分比、业务成绩：澄清话术与追问模板中不出现任何具体提升数字。
- 学习者可用 `coach.record_project_fact(learner_id, fact)` 显式登记自有事实（按 learner 隔离）；登记后才能继续梯子。
- 评分侧：题目要求项目事实而回答 `project_facts=[]` 时，`missing_project_facts` + `evidence_sufficiency` 惩罚；`a-missingfacts-004` fixture 显式声明“没有参与过线上延迟优化项目”，用于验证询问而非编造。

## 6. 不可信文档与 Prompt Injection 防御

- `untrusted_docs` 一律视为 **DATA_ONLY**：每条文档被压平为**单行**并以
  `> [UNTRUSTED_DATA:<doc_id>] <content>` 形式追加在动作 `content` 末尾的
  “不可信参考数据”引用块中；换行替换为 ` ↵ `，伪造的引用标记无法单独成行。
- 注入内容**只能**出现在引用块行内：任何含恶意指令的行都必须以 `> [UNTRUSTED_DATA:` 开头。
- `system_instructions()` 返回深拷贝，注入前后 canonical sha256 不变；`permissions` 恒为
  `network=False / real_provider=False / curriculum_update=False / untrusted_document_authority="none"`。
- 注入文档不进入 `evidence_refs`、不作为评分证据、不改变 `kind`/`rationale`/梯子阶段。
- 非法输入 fail closed：`untrusted_docs` 非 list、元素非 dict、`content` 非 str 均 `TypeError`。

## 7. 来源可信度分层

完整规则见 `docs/m1/FRESHNESS_AND_SOURCE_POLICY.md`。要点：

- 层级：`official_document(3) > paper(2) = engineering_blog(2) > jd(2) > community(1) > mirror(0) = unknown(0)`；
  仅 `official_document/paper/engineering_blog` 且 `UPDATE + VERIFIED` 才可能进入主课程。
- **JD 变化 ≠ 题目热度**：JD 只表示岗位要求变化，`FreshnessManager.classify()` 在 notes 中显式写
  `jd_change_does_not_imply_topic_popularity=true`，且 `SOURCE_TIERS["jd"]["may_update_curriculum"] = False`。
- 论文/官方文档/社区讨论分层描述与代码 `SOURCE_TIERS` 由测试做一致性断言（文档表格 rank 与代码 rank 对齐）。

## 8. Fixture 清单（计划值 vs 实际值）

| 类别 | 计划值 | 实际值 | 说明 |
|------|--------|--------|------|
| questions | ≥ 20 | 22 | 覆盖 recommendation_ctr / ml_fundamentals / engineering_metrics / system_design |
| jds | ≥ 6 | 6 | rec/ml/sys 各 2 个版本；v2 `supersedes` v1 |
| knowledge | ≥ 6 | 9 | KEEP 2 / UPDATE 2 / RECHECK 5（冲突、过期、更旧、低权威、未来时间） |
| injection | ≥ 3 | 4 | 指令覆盖、提权、伪权威、数据投毒 |
| answers | ≥ 8 | 9 | 正确 / 含糊 / 虚构数字 / 缺项目事实 / 部分正确 / 不可行 / 无来源 / 强回答 / 部分 |
| hidden | ≥ 6 | 7 | 与公开题集分离，公开文档与公开 trace 不包含 hidden id |

## 9. 评测指标（计划值 vs 实际值）

> 下表的“实际值”全部来自本机真实运行（2026-11-19，Python 3.11.15 / pytest 9.2.0），
> 未真实运行的项明确标 **NOT_RUN / UNVERIFIED**；不伪造 PASS。

| 指标 | 计划值 | 实际值（真实运行） | 验证方式 |
|------|--------|--------------------|----------|
| 追问梯子阶段顺序 概念→假设→复杂度→实验设计→线上定位 | 5/5 顺序正确 | **5/5 顺序正确**；第 6 次调用封顶在「线上定位」，不自造阶段 | `test_follow_up_ladder_progresses_in_order` |
| 项目事实缺失触发 ASK_CLARIFICATION | 是 | **是**：`a-missingfacts-004` 触发 `kind=ASK_CLARIFICATION`；非项目题继续 `SOCRATIC_QUESTION` | `test_missing_project_facts_trigger_clarification_not_fabrication` |
| 虚构数字 → 低 evidence + failure mode | 是 | **是**：`a-fabricated-003` 的 `evidence_sufficiency=0.0`、`score=0.4625`、`passed=false`，modes 含 `unsourced_quantitative_claim` + `missing_project_facts` | `test_fabricated_numbers_lower_evidence_only` + trace |
| Rubric 同输入同输出 | 是 | **是**：同一输入两次调用分数/反馈/失败模式完全一致；套件连续两次运行均全绿 | `test_rubric_is_deterministic_and_side_effect_free` |
| Rubric 不调用 Runtime（Mock 调用次数） | 0 次 | **0 次**（`MockRuntimePort.calls == 0`；rubric 源码无 runtime import） | `test_rubric_never_uses_runtime` |
| 注入后 system hash 不变 | 4/4 文档 | **4/4**：`system_hash_unchanged=true`，每个文档 1 行引用块，`doc_id_in_evidence_refs=false`；hash=`c336aec6…e416` | `test_injection_documents_cannot_change_system_instructions` + trace |
| KEEP/UPDATE/RECHECK 分类正确 | 9/9 | **9/9**（KEEP 2 / UPDATE 2 / RECHECK 5） | `test_classify_matches_expected_change_kinds` + trace |
| RECHECK 不进入课程 | 是 | **是**：可写课程来源仅 `doc:auc-001`、`paper:ns-001`；5 个 RECHECK 来源全部阻断且交集为空 | `test_apply_groups_revisions_and_blocks_silent_pollution` + trace |
| hidden 题集隔离 | 7 题不泄漏 | **7/7 未出现在**公开 questions、公开 spec、公开 trace | `test_hidden_questions_do_not_leak_into_public_artifacts` |
| 单测规模/耗时 | 全绿、每测试 < 30s | **49 passed in 0.07s**（三个文件一次性运行） | 见 §11 命令 |
| 人类评分校准 | 计划外（UNVERIFIED） | **NOT_RUN**：无人类面试官一致性评估 | — |
| 真实 Runtime / 真实数据 / 真实时效 | 计划外（UNVERIFIED） | **NOT_RUN**：全部 Mock + 合成 fixture | — |

## 10. 已知限制 / UNVERIFIED

- **Runtime 完全 UNVERIFIED**：`RuntimePort` 仅 Mock；Coach 构建时注入 runtime 以满足架构边界，但所有方法**不调用**它。真实模型生成质量、真实多轮对话稳定性均未验证。
- **真实数据 UNVERIFIED**：无真实简历/JD/公司；`company_synthetic: true`。无法声称对真实招聘市场的覆盖。
- **时效数据 UNVERIFIED**：没有真实外部抓取；所谓“更新/冲突”全部是合成时间戳，不能宣称“本周热点已真实更新”。
- **内容指纹 v0 限制**：`KnowledgeSource` 无正文/摘要哈希字段，内容指纹退化为 `(uri, publisher, published_at, claim_status)` 的 sha256；正文级变更需要上游传入 digest（UNVERIFIED）。
- **人类评分未校准（NOT_RUN）**：四维分数与 `passed` 是工程判定，未经人类面试官一致性评估。
- **隐藏题集隔离是离线约束**：测试只断言 hidden id 不出现在公开 fixtures/公开文档/公开 trace；真实考试环境的访问控制未实现（UNVERIFIED）。
- `b-eval` 的跨模块闭环验证由 b-eval 负责；本模块只保证契约接口与自身测试。

## 11. 复现命令与真实结果

```bash
cd /root/at-m1-offline && "/root/Autonomous Teacher/.venv/bin/python" -m pytest \
  tests/m1_offline/test_interview_coach.py \
  tests/m1_offline/test_interview_rubric.py \
  tests/m1_offline/test_freshness.py -q
```

另可重放本模块的真实离线 trace（确定性；不含 hidden 题集；`runtime_calls=0`）：

- `docs/m1/traces/interview_demo.jsonl`：25 行 JSONL，由真实代码运行生成，
  sha256=`7d95d8449bd4e6f819552da62297dc37014fe0504f3bec8fbedfa8e048fdcada`。

## 12. 验证记录（真实运行，非计划值）

- 运行时间/环境：2026-11-19；Python 3.11.15；pytest 9.2.0；工作树 `/root/at-m1-offline`。
- 命令：见 §11。
- 真实输出：

```text
.................................................                        [100%]
49 passed in 0.07s
```

- 逐文件测试数：`test_interview_coach.py` 19、`test_interview_rubric.py` 13、`test_freshness.py` 17（共 49）。
- 可重复性：同一命令连续运行两次均 `49 passed`；rubric/coach/freshness 均为确定性计算（固定输入、无时钟/随机源参与判定）。
- Trace 生成：25 行；`runtime_audit = {"runtime_calls": 0, "real_provider_calls": 0, "offline_only": true, "simulated": true}`；
  注入审计 `system_hash_unchanged=true`（4/4 文档）；freshness 汇总 `KEEP=2, UPDATE=2, RECHECK=5`。
- Lint：`ruff check` 对 `m1_offline/interview m1_offline/freshness.py` 与本模块三个测试文件全部通过。
- NOT_RUN / UNVERIFIED：真实 Runtime、真实简历/JD/热点数据、人类评分校准、跨模块 `b-eval` 闭环（由 b-eval 负责）、
  真实抓取调度与课程数据库写入（仅实现策略门禁）。
