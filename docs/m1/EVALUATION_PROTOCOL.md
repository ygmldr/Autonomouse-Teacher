# M1 Offline 评测协议（Evaluation Protocol）

- 文档状态：协议定义（PROTOCOL）。本文件只定义"如何评测"，**不是**结果报告。
- 结果报告见 `docs/m1/EXPERIMENT_BASELINE.md`（只允许填入真实执行得到的数值）。
- Schema 版本：`m1.offline.v0`（`m1_offline/types.py`）。
- 适用代码：本 worktree 的 `m1_offline/`（离线合成教师）与 `tests/m1_offline/`。
- 结论性质：**offline synthetic, not real teaching effect**。本文所有指标都只描述"离线合成模拟器内部行为"，不得外推为真实教学效果、真实学习者提升或真实模型能力。

---

## 1. 评测目标（Goals）

1. 证明离线教学闭环**真实可运行**：Goal → Baseline Diagnosis → Knowledge/Skill Gap → Teaching Action → Learner Response → Independent Assessment → Memory Update → Next Task，固定 seed 下可重复，至少 3 个完整轮次。
2. 证明闭环**可回放**：每个状态迁移都落成 `TraceEvent`（JSONL），可按 `event_id` / `loop_id` 完整重建学习状态，重建结果与在线运行一致。
3. 证明评测**独立于 Teacher**：评分由独立 scorer 模块 + fixture 中的隐藏用例/rubric 依据完成；Teacher 自评文本、模型漂亮的措辞、`simulated=True` 的 runtime 回答都**不是**准确率/掌握度依据。
4. 证明学习状态更新**证据驱动**：没有独立的评估证据（`EvidenceEvent`）时，掌握度不得提高；"听起来很好"的文本不得触发掌握度上涨。
5. 覆盖**失败负例**并 fail-closed：模型幻觉、拒绝回答、超时、工具失败、过期来源、学习者证据不足、重复任务，必须显式标记为失败/不成功，不得静默当作成功。
6. 提供 **teacher_v0（FixedPolicy）vs teacher_v1（AdaptivePolicy）** 的固定 case、固定 seed、盲评 rubric 对照协议，记录每维均分/方差与失败案例清单。
7. 提供 **公开/隐藏 fixture 分离**与污染/泄漏检查（子串 + 哈希检索）。
8. 提供可离线运行、确定性的 demo：`python -m m1_offline.demo`。

## 2. 非目标（Non-goals）

- 不评测、不声称任何真实模型/Provider 的能力；不做任何真实网络出站、真实 API Key、真实 Provider 调用。
- 不使用真实个人数据/简历数据；fixtures 全部为 Synthetic 或自编 CC0-1.0。
- 不声称 M0 已有"验收过的 Runtime API"。`RuntimePort` 是 M1 的**离线抽象**；M0 runtime 在本 worktree 视角一律 **UNVERIFIED**，不引用、不 import `autoteacher_m0`。
- 不把离线合成模拟得到的 v0/v1 差异当作"真实教学效果差异"或统计显著性结论。
- 不预填 PASS：未真实运行的项目一律标 `NOT_RUN`。

## 3. 证据等级（Evidence Levels）

| 等级 | 含义 | 允许的措辞 |
| --- | --- | --- |
| `MEASURED` | 本 worktree 上真实命令执行产出，记录命令/日期/worktree SHA/原始输出 | "实测为…" |
| `NOT_RUN` | 未执行或依赖未就绪 | "未运行（NOT_RUN）" |
| `UNVERIFIED` | 依赖外部系统或 M0 既有能力 | "UNVERIFIED，不据此下结论" |
| `PLAN` | 目标/计划覆盖数 | "计划值（PLAN）" |

`docs/m1/EXPERIMENT_BASELINE.md` 的每一行都必须带证据等级；`PASS`/`FAIL`/`PARTIAL` 只允许来自 `MEASURED`。

## 4. 评测器独立性（Evaluator Independence）

硬规则：

1. 评估结果只能来自**独立 scorer**（`m1_offline/cf/judge.py` 的 `CFJudge`、`m1_offline/interview/rubric.py` 的 `InterviewRubric`，或 `m1_offline/evaluation/` 内的独立评分逻辑），不得来自 Teacher 模块。
2. 评分输入只允许：题目（公开）、隐藏用例/隐藏 rubric 依据、被测提交物。**不允许**输入：策略名（v0/v1）、Teacher 自评文本、Teacher 的 `TeacherAction.text`、runtime 的"已掌握"声明。
3. 盲评：`compare.py` 的评分函数签名中不出现 `policy`/`teacher`/`strategy` 形参；评分前把轨迹"脱敏"成 `BlindCaseView`（只含 case_id、submission、隐藏用例依据）。单测断言：同一提交物在不同策略元数据下评分完全一致，且签名中不含策略标识。
4. `AssessmentResult.scorer_id` 必须指向独立 scorer（例如 `independent_cf_judge_v0`），不得写 teacher 标识。
5. Teacher 自报的 `DiagnosticResult` 可以作为"教学决策输入"，但**不得**作为"学习者是否掌握"的评估真值；掌握度只能由 `EvidenceEvent`（来源为独立评估）驱动，见 §5.4。

## 5. 闭环协议（Closed Loop Protocol）

### 5.1 组件

- `MockRuntimePort`：完全本地、`simulated=True`、零网络；`script` 注入确定性回答；支持注入 `error`/`timeout`。`RuntimePort` 是抽象协议（UNVERIFIED 于 M0）。
- `LearnerModel(profile)`：持有掌握度状态；`apply_evidence(EvidenceEvent)` 按证据更新；`replay(events)` 由事件重建状态。
- `CurriculumPlanner.plan(goal, learner_state, available_tasks)`：产出 `CurriculumPlan`。
- `TeachingPolicy`：`FixedPolicy`（teacher_v0，固定动作/提示等级）与 `AdaptivePolicy`（teacher_v1，按诊断/差距自适应提示等级与任务顺序）。
- `LearningMemory`：`append/replay/to_jsonl/from_jsonl/delete`，持久化教学记忆。
- 独立 scorer：`CFJudge.evaluate(problem, hidden, code) -> JudgeResult`；隐藏用例只对 scorer 可见。

### 5.2 每轮步骤（固定顺序，每步至少一个 TraceEvent）

| step | 名称 | 输入 | 输出 |
| --- | --- | --- | --- |
| `goal` | Goal 建立 | `LearnerProfile` | `LearningGoal` |
| `diagnose` | Baseline Diagnosis | profile + 诊断题 | `DiagnosticResult`（含 knowledge/skill gaps） |
| `gap` | Gap 计算 | goal + diagnosis + learner_state | 差距清单（并写入 trace payload） |
| `plan` | 课程计划 | goal + learner_state + available_tasks | `CurriculumPlan` |
| `action` | Teaching Action | task + learner_state + diagnosis + hint_level | `TeacherAction` |
| `response` | Learner Response | action prompt + script | `RuntimeResponse`（模拟学习者回答） |
| `assess` | Independent Assessment | 题目 + 隐藏用例 + 提交物 | `AssessmentResult`（scorer_id 为独立 scorer） |
| `memory` | Memory Update | 评估证据 → `EvidenceEvent` | 更新后的 `LearnerState` + `LearningMemory` 记录 |
| `next_task` | Next Task | 更新后 state + plan | 下一轮 `LearningTask`（指派或终止原因） |

一轮 = 上述 9 步中实际执行的子集（`goal`/`diagnose` 只在首轮），但 `action → response → assess → memory → next_task` 必须完整出现。失败负例允许在 `response`/`assess` 后进入 `halt`（显式失败终止），`halt` 也是合法的 trace 事件，不得静默跳过。

### 5.3 轮次、确定性与终止条件

- 固定 seed（默认 `seed=0`）与固定 clock：trace timestamp 由确定性注入时钟生成（固定 epoch + 固定步进），因此同一输入两次运行的 trace **逐字节一致**；该性质由 demo 双跑 SHA-256 对比与单测断言。
- 最少 3 个完整轮次（计划值 PLAN ≥3；实际值以 EXPERIMENT_BASELINE 为准）。
- 终止条件任一：(a) 达到 `max_rounds`（默认 3/5）；(b) goal 的目标技能全部达到掌握阈值；(c) 显式失败终止（fail-closed）。
- 任何异常/超时/工具失败都必须转成显式失败事件，不得吞掉后仍计为成功。

### 5.4 证据驱动的掌握度规则（可测试）

掌握度只允许因 `EvidenceEvent` 变化，且事件必须携带**独立评估结果**。落地契约以 `m1_offline/types.py` 为准：

- **合法枚举**（`EVIDENCE_KIND_VALUES`，大写）：`ANSWER` | `CODE_SUBMISSION` | `EXPLANATION` | `INTERVIEW_RESPONSE` | `ASSESSMENT` | `HINT_REQUEST`。任何其他 kind 值都会被 schema 校验拒绝（`SchemaError`），不能进入事件流。
- 只有 `kind ∈ {ANSWER, CODE_SUBMISSION, EXPLANATION, INTERVIEW_RESPONSE, ASSESSMENT}` **且 `observed_score is not None`** 的事件才允许改变掌握度（`LearnerModel.SCORED_EVIDENCE_KINDS`）；`observed_score` 必须来自独立评估。闭环 harness 只发出 `kind="ASSESSMENT"` 的事件，其 `observed_score` = 独立隐藏用例判分的通过比例。
- `HINT_REQUEST` 是合法 kind 但不计分（不在 `SCORED_EVIDENCE_KINDS` 内），即使携带 score 也不得改变掌握度。
- **非枚举概念类别**：`self_report` / `model_text` / `teacher_text` **不是**合法事件 kind，只用于描述"未绑定独立评估的模型/教师自述或漂亮措辞"。它们必须被 schema 拒绝（无法被表示为证据事件）；即便用合法 kind（如 `EXPLANATION`）承载同样的文本，只要 `observed_score is None`，掌握度也不得改变。
- `passed=False` / `error` 的评估不得提高掌握度；可按规则下调或保持不变。
- 无证据（`events == []`）时 `LearnerModel.state()` 等于初始 `LearnerState`（无涨点）；带 score 的评估把 mastery 拉向该分数，失败评估只能下调或保持。

可测试判定：`test_closed_loop.py` 中 (a) 无证据不涨；(b) 无 score 的文本/自述（含 `EXPLANATION`+`observed_score=None`）不涨；(c) assessment 失败不涨；(d) assessment 通过才涨；`HINT_REQUEST` 带 score 也不涨。

## 6. Trace 与回放规范

### 6.1 TraceEvent

`TraceEvent(event_id, loop_id, round, step, payload, timestamp)`，JSONL 一行一个事件：

- `event_id`：`f"{loop_id}:e{seq:04d}"`，`seq` 从 0 单调递增。
- `loop_id`：一次闭环运行（run）内唯一，如 `loop_v1_seed0`。
- `round`：0 起始的轮次号；`goal`/`diagnose`/`gap`/`plan` 属于 round 0。
- `step`：§5.2 的步骤名（另允许 `halt`）。
- `payload`：可 JSON 序列化的步骤产物（含 `seq` 便于校验顺序），不得含隐藏用例正文（只允许 case_id / 通过计数 / 哈希）。
- `timestamp`：确定性注入时钟的 ISO-8601 字符串。

### 6.2 落盘与回放

- 可选 `--trace <path>`：harness 将事件逐行写 JSONL（UTF-8、`ensure_ascii=False`、字段排序固定），未指定路径时仅内存保留。
- `replay_trace(events)`：按文件顺序（并校验 `seq` 连续）重建：轮次数、每轮 assessment 结果、最终 `LearnerState`。
- 支持按事件/循环回放：`replay_trace(events, loop_id=...)`、`replay_trace(events, until_event_id=...)`。
- 断言：`replay(trace).final_state == live.final_state`，`replay(trace).assessment_ids == live.assessment_ids`，`replay(trace).step_sequence == live.step_sequence`。不一致即 FAIL。

## 7. v0/v1 对照协议（teacher_v0 vs teacher_v1）

- v0 = `FixedPolicy`：固定提示等级（默认 `LIGHT_HINT`）、固定任务顺序；v1 = `AdaptivePolicy`：根据诊断/差距调整提示等级（Hint Ladder）与任务顺序。
- 固定 case 集：取公开 fixture 中的合成任务（`fixtures/m1/cf/`），case 顺序、seed、模拟学习者参数完全一致；两策略使用**同一批** case 与**同一**模拟学习者脚本。
- 盲评：评分只看到脱敏提交物 + 隐藏用例依据；评分维度在评分前固定，不因策略而变。
- 维度（计划值 PLAN；实际以基线为准）：`correctness`（隐藏用例通过率）、`rounds_to_first_success`（越少越好，计分时取反向归一）、`hint_efficiency`（达成目标所用提示升级次数，越少越好）、`independence`（无最高提示即通过的比例）。每维记录均值与**跨 seed/跨 case 的方差**。
- 失败案例清单：每个 fail 的 case 记录 `case_id / policy / round / failure_mode / scorer_id`，不隐藏。
- 输出措辞硬约束：必须包含 `offline synthetic simulation; not real teaching effect`，禁止出现"证明/显著提升/真实效果"等外推措辞；`test_compare_v0_v1.py` 对输出文本做断言。
- 允许 v0 与 v1 结果相同或 v0 更好；报告必须如实呈现，不得为"v1 更优"调参或挑选 seed。

## 8. 失败负例矩阵（Failure Negative Matrix）

每种负例都必须有 ① 触发方式 ② 期望行为（fail-closed 或显式标记） ③ 断言点。

| # | 负例 | 触发方式（离线、Synthetic） | 期望行为 | 关键断言 |
| --- | --- | --- | --- | --- |
| N1 | 模型幻觉（声称完成但实际错误） | mock 回答自信声称"已全部实现/无需测试"，提交物隐藏用例失败 | Assessment `passed=False`；状态不改涨；trace `assess` payload 标 `hallucination_suspected=True`；显式失败标记 | 不因文本涨掌握度；`failure_modes` 含 `hidden_cases_failed` |
| N2 | 拒绝回答 | mock 回答 "I can't help with that." | 显式 `refusal` 标记；该轮不计成功；不涨掌握度；可继续或终止，但 trace 有记录 | `failure_modes` 含 `refusal` |
| N3 | 超时 | `MockRuntimePort(timeout=True)` 或注入 `TimeoutError` | 捕获为显式 `timeout` 失败事件；fail-closed；不重试成"成功" | `failure_modes` 含 `timeout`；assessment 不 passed |
| N4 | 工具失败 | `CFJudge` 执行失败/非法代码/运行器错误 | `JudgeResult.error` 非空、`passed=False`；assessment 带 `tool_error` 标记 | 不得把 error 当 passed；掌握度不涨 |
| N5 | 过期来源 | `FreshnessManager.classify/apply` 将旧版本知识判为 `stale/expired` | 过期知识不得作为有效教学依据；注入过期来源时显式 `stale_source` 标记并屏蔽/降权 | 分类结果与 `KnowledgeRevision` 版本一致；过期来源不进入有效上下文 |
| N6 | 学习者证据不足 | 无 EvidenceEvent 或证据不足阈值 | Diagnosis/策略显式 `insufficient_evidence`；不涨掌握度；请求补充证据而不是直接宣称掌握 | `state` 不变；标记存在 |
| N7 | 重复任务 | 连续两轮指派同一 task_id | 显式 `duplicate_task` 标记；第二次不重复计成功、不重复涨掌握度 | 第二轮 `assessment` 不计入；标记存在 |

补充硬规则：任何负例都不得静默成功（测试断言每条负例的 trace 中至少有一个显式失败标记或 `halt` 事件）。

## 9. 污染 / 泄漏检查（Contamination & Leakage）

1. **公开/隐藏分离**：隐藏用例只存在于 `fixtures/m1/*/hidden*`（cf）与 `fixtures/m1/interview/hidden*`；公开文档、公开 trace、Teacher 可见 prompt 中不得出现隐藏题面/隐藏答案。
2. **子串检索**：从隐藏 fixture 提取规范化后的题面/答案关键串（长度阈值），在公开面（`docs/m1/**`、公开 fixtures、Teacher 可见模块源码常量、公开 trace 的 payload 文本）中做子串扫描。
3. **哈希检索**：对隐藏 fixture 的规范化文本取 SHA-256，与公开面文本窗口哈希比对，避免规避性改写导致的漏检；报告中只记录哈希前缀与位置，**不回显隐藏文本**。
4. **注入文档不泄漏系统指令**：interview 注入文档（不可信数据）的文本不得出现在 `system_instructions`/Teacher prompt 中；注入内容只能作为"数据"进入用户内容位置，且 trace/report 中标记为 untrusted。
5. **无真实数据/网络**：扫描 `m1_offline/**`、`fixtures/m1/**`、`tests/m1_offline/**` 中的网络客户端 import（httpx/requests/urllib/socket 等）、API Key 形态、真实邮箱/电话/简历字段；发现即 FAIL。
6. 输出为结构化 `ContaminationReport`（每项 check：id、description、status、details、evidence），写入 `docs/m1/reports/`（不含隐藏正文，也不回显隐藏题/隐藏集 ID）。
7. 检查实现（`m1_offline/evaluation/contamination.py`）：
   - `C1_hidden_public_separation`：隐藏 fixture 存在且与公开扫描面不相交；
   - `C2_hidden_leakage`：隐藏-only 文本（子串 + 滑动窗口 SHA-256，扣除公开 fixture 中本来就合法的共享题面）不得出现在公开文档 / trace / 报告 / teacher 可见源码；
   - `C3_injection_not_in_system_prompt`：interview 注入文档不得出现在 `system_instructions`（实现层另行验证 `instruction_hash()` 不因注入而变）；
   - `C4_no_network_or_real_data`：无网络客户端 import、无 API Key 形态、无真实邮箱/手机号/SSN 形态（合成域名 `example.com` 等豁免）。
   `NOT_RUN` 不是 PASS：缺少隐藏 fixture 或公开面时对应检查必须为 `NOT_RUN` 且 overall 不为 ok。

## 10. 指标定义与"计划值 vs 实际值"

| 指标 | 定义 | 计划值（PLAN） | 实际值来源 |
| --- | --- | --- | --- |
| 闭环完整轮次 | 完成的 `action→…→next_task` 轮数 | ≥3 | EXPERIMENT_BASELINE（MEASURED） |
| Trace 事件数 | JSONL 行数 | 4 个基线步骤 + 5 个轮内步骤 × 3 轮 = 19（PLAN，`max_rounds=3`） | 同上 |
| 回放一致率 | 回放状态/assessment/步骤序列 == 在线 | 100% | 同上 |
| 无证据掌握度变化 | 无 EvidenceEvent 时 state delta | 0 | 同上 |
| 非评估文本导致掌握度变化 | 仅无 score 的文本/自述事件时 state delta | 0 | 同上 |
| v0/v1 case 数 | 固定合成 case | ≥12（计划） | 同上 |
| v0/v1 seed 数 | 固定 seed 重复 | ≥3（计划） | 同上 |
| 每维均分/方差 | §7 四维，跨 seed/case | 记录即可，不设"更好"目标 | 同上 |
| 失败案例数 | §7 失败清单条数 | ≥1（负例应可复现出现） | 同上 |
| 负例覆盖 | §8 N1–N7 | 7/7 | 同上 |
| 污染检查项 | §9 的 check 数 | 全 PASS 才可报"检查通过" | 同上 |
| 隐藏泄漏命中 | §9 子串+哈希命中数 | 0 | 同上 |
| demo 确定性 | 连续两次运行输出 SHA-256 一致 | 一致 | 同上 |

**计划值不是结果**：上表"计划值"列只表示验收目标；实际值必须由 `MEASURED` 运行填入 EXPERIMENT_BASELINE，未跑的填 `NOT_RUN`，不得用计划值冒充实际值。

## 11. 不得外推的边界（Non-extrapolation）

- 本协议结果仅对"本 worktree 的离线合成模拟器 + 固定 fixtures + 固定 seed"成立。
- 模拟学习者由确定性脚本/概率模型生成，**不代表**真实人类学习者；隐藏用例是合成题，**不代表**真实教学场景的题目质量。
- v0/v1 的差异是策略在合成环境中的行为差异，**不是**真实教学效果差异；不报告 p 值/显著性，不做"提升 X%"式外推。
- `simulated=True` 的 runtime 回答不是真实模型输出；M0 Runtime API 一律 UNVERIFIED。
- 隐藏用例/隐藏答案不得出现在任何交付物、报告、trace、teacher 可见上下文中。

## 12. 实现映射（Implementation Map）

| 协议对象 | 实现 | 对应测试 |
| --- | --- | --- |
| 闭环 / Trace / 回放 | `m1_offline/evaluation/harness.py`（`run_closed_loop`、`replay_trace`、`trace_digest`） | `tests/m1_offline/test_closed_loop.py` |
| 评测器独立性 | `CFJudge`（`m1_offline/cf/judge.py`）、`InterviewRubric`（`m1_offline/interview/rubric.py`） | `test_evaluation_protocol.py` |
| v0/v1 对照 + 盲评 | `m1_offline/evaluation/compare.py`（`blind_score` 只接收 `BlindTrajectory`） | `test_compare_v0_v1.py` |
| 失败负例 | harness 显式 failure marker / `halt` 事件；`FreshnessManager` 的 RECHECK fail-closed | `test_negatives.py` |
| 污染 / 泄漏 | `m1_offline/evaluation/contamination.py` | `test_contamination.py` |
| 报表（MEASURED / NOT_RUN） | `m1_offline/evaluation/report.py` | demo 产物 `docs/m1/reports/` |
| 可运行 demo | `m1_offline/demo.py`（`python -m m1_offline.demo`） | 双跑 stdout SHA-256 一致 |

实现细节约定：

- v0/v1 对照的固定 case 来自 `fixtures/m1/cf/problems/`（14 个合成题），隐藏判分来自 `fixtures/m1/cf/hidden/`；两策略共用同一模拟学习者与同一组随机数（common random numbers），`seed ∈ {0,1,2}`，每条轨迹固定 12 轮（`mastery_threshold` 冻结 >1.0 仅用于对照取固定轮数，是对照控制项而非学习结论）。
- Trace JSONL 的一个事件 = 协议 §5.2 的一个步骤；payload 只存通过计数/哈希/评估结果，不存隐藏用例正文或判分 failure 原文（失败信息可能含隐藏输入）。
- demo 默认不写文件；`--write-artifacts` 才把确定性 trace 与基线报告写到 `docs/m1/traces/`、`docs/m1/reports/`。

## 13. 复现（Reproduction）

```bash
cd /root/at-m1-offline
"/root/Autonomous Teacher/.venv/bin/python" -m pytest \
  tests/m1_offline/test_closed_loop.py \
  tests/m1_offline/test_evaluation_protocol.py \
  tests/m1_offline/test_negatives.py \
  tests/m1_offline/test_contamination.py \
  tests/m1_offline/test_compare_v0_v1.py -q
"/root/Autonomous Teacher/.venv/bin/python" -m m1_offline.demo
```

- 记录：命令、UTC 日期、worktree `git rev-parse HEAD`、python 版本、各测试 pass/fail 数。
- 复现结果与 EXPERIMENT_BASELINE 不一致时，以新一次真实运行为准并更新基线，不得保留旧"通过"。
