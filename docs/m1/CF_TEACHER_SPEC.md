# CF Teacher（算法解题教学）离线能力规范 v0

- 文档状态：组件规范（SPEC），非结果报告。
- Schema 版本：`m1.offline.v0`（`m1_offline/types.py`，由 B 线 Teacher Core 拥有）。
- 组件：`m1_offline/cf/judge.py`（独立判题器 `CFJudge`）、`m1_offline/cf/teacher.py`（`CFTeacher`）、`fixtures/m1/cf/**`、`tests/m1_offline/test_cf_*.py`。
- 结论性质：**offline synthetic，not real teaching effect**。本文档所有"实际值"均只描述本 worktree 上真实执行得到的离线合成结果，不得外推为真实教学效果、真实学习者提升或真实模型能力。
- 证据等级口径（与 `docs/m1/EVALUATION_PROTOCOL.md` §3 一致）：`MEASURED` / `PLAN` / `NOT_RUN` / `UNVERIFIED`。本文中的 PASS 只在 `MEASURED` 语境使用。

---

## 1. 目标（Goals）

1. **离线可判题**：给定题目（公开 fixture）、学习者提交代码与**隐藏用例**，在不联网、不调用真实 Provider、不 import M0 的前提下给出可复现的通过/失败判定。
2. **判题独立性**：`AssessmentResult.passed` 只能来自独立判题器对隐藏用例的真实执行；教师文本、学习者自述（如 `submission["passed"]=true`）与公开用例不得影响判定。
3. **可解释诊断**：用真实判题输出 + 错误分类学给出 `error_codes`、`confidence`、`status`、`evidence_refs`；证据不足时返回 `UNKNOWN`/`NEEDS_REVIEW`，不得静默当成 AC。
4. **Hint Ladder 教学动作**：默认 `LIGHT_HINT`，按证据逐级升级；`FULL_SOLUTION` 仅限显式请求且证据门槛满足，绝不作为默认。
5. **证据驱动的学习闭环**：多轮"教学动作 → 学习者提交 → 独立评估 → 证据写入 LearnerModel → 下一任务"可运行、可解释；重复同一题不得伪造成跨技能迁移掌握度。
6. **负例 fail-closed**：语法错误、导入异常、缺失函数、超时、运行器崩溃、隐藏 fixture 缺失/不匹配、评测基础设施错误全部显式失败，不得计入成功。
7. **合成数据与许可清晰**：全部 fixture 自编 Synthetic、CC0-1.0、无个人数据、无真实网络端点；参考解必须通过自己的隐藏用例。

## 2. 非目标（Non-goals）

- 不评测/不声称任何真实模型、Provider 或 M0 Runtime 的能力；`RuntimePort` 仅作为离线抽象边界，本组件判题与提示选择**不依赖** runtime 文本。
- 不把离线合成模拟当作真实教学效果或学习者能力结论；不做真实学生实验。
- 不提供安全沙箱。`CFJudge` 是本地子进程 + 超时 + 临时目录，**不是**容器/seccomp/namespace/用户隔离，详见 §5.4。
- 不评测代码安全（恶意提交、资源耗尽、逃逸）与生产可靠性。
- 不伪造 PASS：未真实运行的项一律标 `NOT_RUN`；无可复核输出的项标 `UNVERIFIED`。

## 3. 组件与接口

### 3.1 模块

| 路径 | 职责 |
| --- | --- |
| `m1_offline/cf/judge.py` | `CFJudge` / `JudgeResult`：隔离子进程执行学习者代码，只对隐藏用例判分，fail-closed |
| `m1_offline/cf/teacher.py` | `CFTeacher`：`diagnose` / `next_action` / `assess`；集成 b-core `DiagnosticEngine`、`AdaptivePolicy` 与共享 types |
| `m1_offline/cf/__init__.py` | 导出 `CFJudge`、`JudgeResult`、`CFTeacher`、`SCORER_ID`、`CF_ERROR_CODES` 等 |
| `fixtures/m1/cf/problems/<id>.json` | 题目 + 公开用例 + 4 级 hint ladder + 参考解 |
| `fixtures/m1/cf/hidden/<id>.json` | 隐藏用例（唯一判分依据） |
| `fixtures/m1/cf/learners/<id>.json` | 合成学习者画像 + 典型错误轨迹（可复现的证据） |
| `tests/m1_offline/test_cf_{judge,teacher,negatives}.py` | 判题、诊断/提示/评估、负例与 fixture 诚实性测试 |

### 3.2 跨模块契约（b-eval 等按此 import；签名未擅自更改）

```python
from m1_offline.cf.judge import CFJudge, JudgeResult
from m1_offline.cf.teacher import CFTeacher

judge = CFJudge(timeout_s=3.0)                      # 单次执行硬预算（契约 < 5s）
verdict: JudgeResult = judge.evaluate(problem, hidden, code)

teacher = CFTeacher(runtime)                        # 兼容 RuntimePort 构造签名
diagnosis = teacher.diagnose(problem, submission, learner_state)      # DiagnosticResult
action = teacher.next_action(problem, learner_state, hint_level=None) # TeacherAction
assessment = teacher.assess(problem, submission, learner_state)       # AssessmentResult
```

补充约定（不改变上述签名）：

- `problem`：加载自 `problems/<id>.json` 的 dict；`hidden`：加载自 `hidden/<id>.json` 的 dict；`submission`：至少含 `{"code": str}`（另接受 `solution`/`source`/`answer` 键作为兜底）。
- `CFTeacher.__init__` 额外接受可选关键字参数 `fixtures_dir`（默认 `FIXTURES_DIR/"cf"`）与 `judge`（测试注入更快超时用）；位置参数 `runtime` 不变。
- `runtime` 只保存不使用：判题/评分/提示选择完全离线确定；`MockRuntimePort.calls` 在 `assess()`/`next_action()` 后保持 `0`（测试断言）。
- `ASSESSMENT.scorer_id == "independent_cf_judge_v0"`（独立判题器标识，对齐评测协议 §4.4）。
- `DiagnosticResult.status` 只使用共享枚举 `RESOLVED` / `UNKNOWN` / `NEEDS_REVIEW`；"AC"不是独立状态：隐藏用例全过 = `status="RESOLVED", error_codes=[]`，且一定来自判题输出。

### 3.3 依赖边界

- 只依赖 `m1_offline` 内的 b-core 公共面：`types`（共享记录）、`diagnostics.DiagnosticEngine`（规则分类）、`teaching_policy.AdaptivePolicy`（Hint Ladder 证据门槛）、`__init__` 的 `FIXTURES_DIR`/`load_json`。
- **禁止** import `autoteacher_m0` 或 `src` 下 M0 代码；**禁止**真实网络出站/真实 API Key/真实 Provider 调用（测试用 AST 扫描保证 `m1_offline/cf/*.py` 不出现 `autoteacher_m0`/`httpx`/`requests`/`urllib`/`socket`/`http`/`aiohttp` 导入）。

## 4. 错误分类学（Error Taxonomy）

`CFTeacher.diagnose` = 真实判题证据 + b-core 规则引擎 + CF 专属规则。全部 code 使用 snake_case；其中 `off_by_one / wrong_complexity / edge_case / conceptual_gap` 与 b-core `DiagnosticEngine.KNOWN_ERROR_CODES` 共享命名。

| error_code | 含义 | 触发信号（真实判题证据） | 默认 status | confidence（实现值） |
| --- | --- | --- | --- | --- |
| `syntax_error` | 代码无法编译 | 子进程导入解出 `SyntaxError`（fail-closed，0/0 用例） | `RESOLVED` | 0.95 |
| `runtime_error` | 模块级异常/函数缺失/用例抛异常 | `import_error`/`missing_function`；或失败用例消息为 `raised <Exc>` | `RESOLVED` | 0.85（fatal 时 0.90） |
| `wrong_complexity` | 复杂度过高（小用例通过、大用例超时） | 全量执行超时，且同一代码在非 large 隐藏用例上通过 | `RESOLVED` | 0.80 |
| `time_limit_exceeded` | 整体超时（非复杂度可归因，如死循环） | 全量超时，且非 large 用例复跑同样超时 | `RESOLVED` | 0.70 |
| `wrong_answer` | 结果错误 | 执行完成、存在 mismatch 失败用例，且未被更具体规则归类 | `RESOLVED` | 0.70（引擎 `NEEDS_REVIEW` 时封顶 0.60） |
| `off_by_one` | 差一错误 | **所有**可解析 mismatch 的数值差恰为 1（保守判定，任一解析失败/非数值则禁用） | `RESOLVED` | 0.60（引擎 `NEEDS_REVIEW` 封顶） |
| `edge_case` | 边界遗漏 | 仅 edge 标记隐藏用例失败，其他用例通过（引擎规则 `edge_case`） | `RESOLVED` | 0.80 |
| `conceptual_gap` | 概念性缺口 | 引擎规则：该学习者在任务技能上历史错误 ≥2 且可见失败率 ≥50% | `RESOLVED` | 0.65 |
| `empty_submission` | 未提交可执行代码 | `submission` 中无 `code/solution/source/answer` | `UNKNOWN` | 0.20 |
| `fixture_error` | 隐藏 fixture 缺失/非法/不匹配，或判题基础设施错误 | `hidden_ref` 不可加载；`CFJudge` 返回 `invalid_input`/`runner_error` | `NEEDS_REVIEW` | 0.10 |
| （无 code） | 失败但规则无法归类 | 引擎 `NEEDS_REVIEW` 且 CF 规则未补充 code | `NEEDS_REVIEW` | 0.35 |

规则说明：

- **不误判 AC**：只有 `CFJudge.evaluate(hidden).passed is True` 才产生 `error_codes=[]` 的 `RESOLVED`；空提交、fixture 缺失、learner 声称通过都不会产生 AC。
- 混合缺陷（如既超时又答案错）按主导证据归类；例如"小用例答案错 + 大用例超时"→ `time_limit_exceeded`，不强行归因为 `wrong_complexity`。
- `evidence_refs` 必含 `hidden:<problem_id>`、`judge:<JUDGE_VERSION>`、`cases:<passed>/<total>`，以及（有失败时）用例级信息经 `cases_passed/total` 与失败清单体现；`explanation` 给出 failed kinds、计数与分类理由。
- 诊断是**教学决策输入**，不是掌握度真值：掌握度只能由独立评估产生的 `EvidenceEvent` 驱动（见 §7）。

## 5. Judge 隔离设计与限制

### 5.1 执行模型

1. 每次评估创建新的临时目录（`tempfile.mkdtemp(prefix="m1_cf_judge_")`），写入 `solution.py` 与 `judge_runner.py`，`cwd=tempdir`。
2. 父进程以 `sys.executable -I -B judge_runner.py <result_path>` 启动子进程；隐藏用例 payload 通过 **stdin** 传入，不落盘（临时目录内不存在隐藏期望值文件）。
3. 子进程在最小环境变量下运行（`PATH`、`PYTHONIOENCODING=utf-8`、`PYTHONHASHSEED=0`、`PYTHONDONTWRITEBYTECODE=1`、`PYTHONNOUSERSITE=1`，可选 `LANG/LC_ALL/TMPDIR`），不继承 `PYTHONPATH` 等无关变量。
4. 子进程按 JSON canonical 形式比较实际返回值与期望值（`json.dumps(..., sort_keys=True, allow_nan=False)`）；不可序列化/NaN 一律视为不匹配。
5. 用例级异常（学习者函数抛错）被捕获为该用例失败（`error=None`, failure 形如 `case-03 kind=edge raised IndexError: ...`），不使整次判题崩溃。
6. 墙钟预算：`effective_timeout = min(CFJudge.timeout_s, hidden.timeout_s)`（下限 0.05s）；超时后父进程对子进程**进程组**发送 `SIGKILL`（POSIX），回收输出并返回 `error="timeout"`。
7. 判题结果 JSON 由子进程写入 `result_path`；父进程读取并解释。stdout/stderr 仅作为截断 ≤400 字符的 `stdout_excerpt` 保留（学习者 print 可见）。
8. 临时目录在 `finally` 中删除；判题器本身不发起任何网络请求。

### 5.2 fail-closed 矩阵

| 情形 | JudgeResult |
| --- | --- |
| 隐藏用例全部通过 | `passed=True, error=None, failures=[]` |
| 部分/全部用例答案错误 | `passed=False, error=None, failures=[...]`（逐用例可解释） |
| 语法错误 | `passed=False, error="syntax_error", cases_passed=0` |
| 模块导入异常 | `passed=False, error="import_error"` |
| 未定义目标函数 | `passed=False, error="missing_function"` |
| 超时 | `passed=False, error="timeout", cases_passed=0` |
| 运行器崩溃/结果文件损坏/用例数不符 | `passed=False, error="runner_error"` |
| 入参非法（空隐藏集、problem_id 与 hidden 不匹配、code 非字符串等） | `passed=False, error="invalid_input"` |

### 5.3 确定性与隐藏用例专用性

- 相同 `(problem, hidden, code)` 多次调用返回**逐字段相同**的 `JudgeResult`（测试 `test_result_is_deterministic_for_identical_input`）。
- 判分**只**读取调用方传入的 `hidden["tests"]`：篡改/清空 `problem["public_tests"]`、篡改 `problem["reference_solution"]` 都不改变判定（测试覆盖两个方向）。
- 隐藏 fixture 与题目的 `problem_id` 不一致时 `invalid_input` fail-closed。

### 5.4 隔离限制（重要，不声称安全）

本地子进程**不是**安全沙箱，明确不具备：

- 文件系统隔离（学习者代码可读写进程可见路径、`/tmp`、repo 文件）；
- 网络隔离（学习者可自行发起网络请求；judge 只保证自身不发起网络）；
- 容器/seccomp/namespace/用户隔离、CPU/内存 rlimit（只有墙钟超时）；
- 进程树回收保证（若学习代码派生出脱离进程组的孙进程，可能残留）；
- 非 POSIX 平台仅 kill 主进程的降级行为（本仓库评测环境为 Linux/POSIX）。

因此 **只允许**用离线合成、自编 CC0-1.0 fixture 与合成学习者提交做评测；**禁止**用真实学习者、真实简历/个人数据或不可信第三方代码。另注意：调用方可以对传入的 `hidden` dict 做"篡改后判分"，judge 无法区分；隐藏 fixture 的不可变性是数据信任边界（fixture 在磁盘上是可信输入，测试保证每个隐藏用例都能被参考解通过）。

### 5.5 实测预算

| 指标 | 计划值 | 实际值（MEASURED，2026-11-19） |
| --- | --- | --- |
| 单次 judge 执行上限 | < 5s | 最坏 2.006s（隐藏 `timeout_s=2.0` 的复杂度超时用例）；参考解最大 0.077s（`cf_dp_lcs`） |
| 单测试上限 | < 30s | 最慢单测 4.63s（10 条学习者错误轨迹逐条真实判题） |

## 6. Fixture 契约、来源与许可

### 6.1 结构与字段

- `problems/<id>.json`：`schema_version`、`problem_id`、`title`、`statement`、`skills[]`、`difficulty(1-5)`、`function_name`、`public_tests[{args,expected}]`、`hidden_ref`、`hint_ladder{LIGHT_HINT,INVARIANT_HINT,STRUCTURE_HINT,FULL_SOLUTION}`、`reference_solution`（Python 源码字符串）、`synthetic:true`、`license:"CC0-1.0"`、`complexity_expectation`（记录用）。
- `hidden/<id>.json`：`schema_version`、`problem_id`、`timeout_s`、`tests[{args,expected,kind}]`、`synthetic:true`、`license:"CC0-1.0"`。`kind ∈ {edge,normal,large}` 仅用于诊断，不改变判分语义（全部隐藏用例都必须通过才算 passed）。
- `learners/<id>.json`：`learner_id`、`display_name`、`baseline_level`、`profile`（可直接构造 b-core `LearnerProfile`）、`mastery`/`error_counts`（画像种子）、`error_traces[{trace_id,task_id,kind,expected_error_class,observed_score,payload{code,note},created_at}]`、`synthetic:true`、`license:"CC0-1.0"`。

### 6.2 来源与许可

- 全部题目、隐藏用例、提示阶梯文本、参考解、学习者画像与错误轨迹均由本 worktree 作者自编，**Synthetic + CC0-1.0**；不含真实个人/简历数据、不含真实姓名/邮箱/电话、不含 URL 或 API Key（`test_fixtures_contain_no_personal_data_or_network_endpoints` 用正则扫描保证）。
- 题目难度为自评 1–5；用于离线教学机制验证，不是标准题库。

### 6.3 实际规模（MEASURED）

| 维度 | 计划值（PLAN） | 实际值（MEASURED） |
| --- | --- | --- |
| 题目数 | ≥ 12 | **14** |
| 覆盖 | 数组、双指针、排序/二分、图基础、DP 入门 | 数组 3、双指针 3、排序/二分 3、图 2、DP 3 |
| 隐藏用例数 | 每题 ≥ 3 | **112**（edge 45 / normal 52 / large 15；每题最少 7） |
| 公开用例数 | 每题 ≥ 1 | **30** |
| 学习者画像 | ≥ 2（基础薄弱 + 进阶） | **3**（BEGINNER / INTERMEDIATE / ADVANCED） |
| 典型错误轨迹 | ≥ 6 | **10**（含边界、语法、运行异常、答案错、差一、复杂度、超时） |
| 参考解自测 | 全部通过自己的隐藏用例 | **14/14**（`test_reference_solution_passes_own_hidden_tests` 参数化实测） |
| 错误轨迹真实性 | 每条轨迹真实失败 | **10/10** 经 judge 复现为 `passed=False` 且错误类与标注一致（`test_learner_fixture_error_traces_are_real_failures`） |

## 7. Hint Ladder 规则与证据门槛

### 7.1 阶梯与默认值

共享枚举（`m1_offline/types.py`）：`HINT_LADDER = (LIGHT_HINT, INVARIANT_HINT, STRUCTURE_HINT, FULL_SOLUTION)`，`hint_level` 1..4，`kind == HINT_LADDER[hint_level-1]`。

| level | kind | 触发条件（CFTeacher） | 内容来源 |
| --- | --- | --- | --- |
| 1 | `LIGHT_HINT` | 默认；`evidence_count==0` 的硬地板（即使显式请求 L4） | `problem.hint_ladder.LIGHT_HINT` |
| 2 | `INVARIANT_HINT` | 该题技能/错误码历史错误数 ≥ 2（教师请求 L2），b-core 策略可再 +1 级 | `problem.hint_ladder.INVARIANT_HINT` |
| 3 | `STRUCTURE_HINT` | 历史错误数 ≥ 4（教师请求 L3）；或证据驱动的升级结果 | `problem.hint_ladder.STRUCTURE_HINT` |
| 4 | `FULL_SOLUTION` | **仅**显式 `hint_level=4` 且 b-core `EvidenceGate` 允许（`evidence_count ≥ 5` 且任务技能最佳掌握度 ≥ 0.70） | `problem.hint_ladder.FULL_SOLUTION` |

规则：

1. `next_action(problem, learner_state)` 未显式传 `hint_level` 时最多发出 L3；CFTeacher 在策略输出上额外硬钳制：非显式 L4 请求时，任何 >L3 的输出被降为 `STRUCTURE_HINT`（防御未来策略变更）。
2. b-core `AdaptivePolicy` 本身亦保证自适应升级不跨入 `FULL_SOLUTION`（仅显式 L4 请求可及）；CFTeacher 的钳制是第二道保险。两者都有测试覆盖（含"敌意策略总是返回 L4 也会被钳到 L3"的安全网测试）。
3. 新学习者（`evidence_count==0`）即使显式请求 L4 也只能得到 L1（硬地板，测试覆盖）。
4. `hint_level` 记录的是**实际发出**的等级；`rationale` 记录 requested level、证据门槛描述（`evidence_count`、best mastery、safety cap）、错误历史与内容来源，可审计。
5. `target_skill_ids` = 题目技能；`evidence_refs` 至少包含 `learner:<id>`、`policy:<version>`、`requested:L<n>`，有错误历史时附 `skill-error:<skill>=<count>`。

### 7.2 证据门槛（与 b-core 一致）

- `EvidenceGate`：无证据 → 上限 L1；证据 <2 或最佳掌握度 <0.35 → 上限 L2；证据 <5 或最佳掌握度 <0.70 → 上限 L3；否则上限 L4。
- 重复错误升级：历史错误 ≥2 加 1 级，≥4（sustained）加 2 级，均受上限与 L3 默认钳制。
- 错误历史兼容两种键：按技能（fixture 种子）或按错误码（`LearnerModel` 约定），取更强信号，避免真实评估产生的错误码被忽略。

## 8. 教学动作与学习闭环

### 8.1 一轮闭环（CF 线）

```
problem(fixture) ──► CFTeacher.diagnose(problem, submission, state)
                         │  真实 judge 输出 → error_codes/status/confidence/evidence_refs
                         ▼
                   CFTeacher.next_action(problem, state, hint_level)
                         │  b-core AdaptivePolicy 选级 + 题目专属 hint 文本（可解释 rationale）
                         ▼
                   学习者（合成脚本 / MockRuntimePort 模拟）提交代码
                         ▼
                   CFTeacher.assess(problem, submission, state)
                         │  独立 judge 对隐藏用例执行 → AssessmentResult(scorer_id=independent_cf_judge_v0)
                         ▼
                   LearnerModel.apply_evidence(EvidenceEvent)
                         │  仅带独立评估分数的 CODE_SUBMISSION/ASSESSMENT 事件可移动 mastery
                         ▼
                   CurriculumPlanner.plan(goal, state, tasks) → 下一任务
```

### 8.2 证据驱动与"无迁移"保证

- `assess()` 本身不修改 learner state；只有 `EvidenceEvent` 经 `LearnerModel.apply_evidence()` 才更新 mastery/error_counts/evidence_count（测试断言：无事件时 state 不变）。
- 事件 payload 的技能集合绑定 task→skill；同一题重复答对只按 `REPEAT_CREDIT_FACTOR=0.25` 递减计分，且**绝不**给未绑定技能涨 mastery（测试 `test_repeating_one_problem_does_not_transfer_mastery`）。
- 失败评估不涨 mastery：当 `observed_score` 低于当前 mastery 时按同一规则下调（测试使用全错提交确保分数为 0）。

### 8.3 多轮模拟教学（MEASURED）

`test_multi_round_loop_actions_change_next_task` 使用 3 个通过轮次 + 1 个下一任务动作：

- 每轮记录 1 个 `TeacherAction`（kind/hint_level/rationale/target_skill_ids 可解释，content 来自题目 hint ladder），共 **4** 个动作；随后 3 次独立评估均 `passed=True`，写入 3 条 `EvidenceEvent`。
- 3 次不同题目的通过证据把 `array-basics` 掌握度推过 planner 复习阈值（0.70），第 4 次规划的首选任务从 `cf_array_sum_even` 变为 `cf_array_running_sum`，并出现 `REVIEW:` 规划理由——**证据改变了下一任务选择**。
- 失败路径：连续 2 次真实失败评估写入证据后，`next_action` 从 L1 升到 L2（`test_loop_failure_evidence_escalates_hint`），且始终 ≤ L3。

### 8.4 Trace 格式与回放兼容性（P2-6 披露）

本节说明两份 CF 闭环 trace 的**格式差异与用途边界**；两者不可混用，也不得把非 canonical trace 当作闭环回放证据。

**（1）`docs/m1/traces/cf_teaching_loop.jsonl` —— CF 域审计格式（非 canonical 回放格式）**

- 由 CF Teacher 域内脚本生成（15 个 `TraceEvent`，loop id `cf_loop_v1_seed0`，固定时间戳；两次生成 SHA-256 一致：`cd3de838d05bf6d8e22a209614c5137ad4029726ed7d78aff7882a6c2ba931c4`；4 个教学动作、3 次评估全通过、最终 mastery `{"array-basics":0.725375,"dp-basics":0.35,"prefix-sums":0.35}`）。
- 该格式把每轮 assessment 字段**平铺**在 `assess` payload 顶层（`assessment_id/passed/score/hidden_cases_passed/hidden_cases_total/failure_modes`），而不是共享回放器期望的 `payload["assessment"]`（`AssessmentResult.to_dict()`）；`memory` 事件也不带 `payload["evidence"]`。其优点是 `event_id`/`seq`/`step` 齐全、按 event_id 可**人工审计**、且含每轮 mastery 快照。
- **兼容性限制（独立评审 P2-6，接受为已披露限制）**：用 b-eval 共享回放器 `m1_offline.evaluation.harness.replay_trace(events)` 读取该文件时，会**返回 0 条 assessment、空 evidence、`final_state=None` 且不抛异常**（静默空结果）。因此它**不是** canonical 闭环回放证据，不能用于"回放一致性"断言；B-05 的闭环回放结论不依赖该文件。

**（2）`docs/m1/traces/cf_loop_canonical.jsonl` —— canonical TraceEvent 回放格式**

- 由共享 `m1_offline.evaluation.harness.run_closed_loop(...)` 直接生成（`learner_fixture_name="learner_advanced"`、`max_rounds=3`、`seed=0`、`loop_id="cf_loop_canonical_seed0"`），事件序列为 `goal/diagnose/gap/plan` + 3 轮 `action/response/assess/memory/next_task`，共 **19** 个事件，`payload.seq` 连续。
- 每个 `assess` payload 携带 `payload["assessment"]`（`AssessmentResult.to_dict()`），每个 `memory` payload 携带 `payload["evidence"]`（`EvidenceEvent.to_dict()`），符合 EVALUATION_PROTOCOL §6 的回放契约。
- 验证（MEASURED，2026-11-19）：`replay_trace(events, learner_profile=..., loop_id="cf_loop_canonical_seed0")` 重建出 **3 条 assessment、6 条 evidence**；`assessment_ids` 与在线运行一致，`final_state == live.final_state`；两次生成 SHA-256 一致：`6e3d96aebbda434c3df2299f28b4bf542c2e1602501135eb20830209fdf58063`（21,649 bytes）。
- 复现注意：`replay_trace` 不传 `learner_profile` 时 `final_state=None`（仍可解析 assessment/evidence）；传入 `_profile_from_fixture(load_learner_fixture("learner_advanced"))` 后可得到最终 `LearnerState`。

**（3）canonical ≥3 轮闭环回放的官方证据仍以 b-eval 为准**：`docs/m1/traces/loop_v0_3rounds.jsonl` / `loop_v1_3rounds.jsonl` 与 `docs/m1/EVALUATION_PROTOCOL.md` §5/§6；`cf_loop_canonical.jsonl` 是同一 canonical 格式下针对 CF fixture（`learner_advanced`）的补充实例，用于证明 CF 线闭环同样可由共享回放器完整重建。

两份 trace 的 payload 均不含隐藏用例正文（只含 case 计数、哈希、分数与合成 fixture 元数据），满足协议 §5/§6 的泄漏约束。

## 9. 评测指标（计划值 vs 实际值）

| 指标 | 计划值（PLAN） | 实际值（MEASURED，2026-11-19） | 证据 |
| --- | --- | --- | --- |
| CF 题数 | ≥12 | 14 | fixture 清单 / `test_fixture_inventory_has_required_coverage` |
| 隐藏用例数 | 每题 ≥3 | 112（最少 7/题） | fixture 清单 |
| 学习者画像 | ≥2 | 3 | fixture 清单 |
| 错误轨迹 | ≥6 | 10 | fixture 清单 + 真实复现测试 |
| 三份测试文件 | 全绿 | **75 passed** | `pytest ... -q`（9.24s） |
| 单次 judge 执行 | <5s | 最坏 2.006s / 参考解 ≤0.077s | 计时脚本 |
| 单测试执行 | <30s | 最慢 4.63s | `pytest --durations=8` |
| 默认提示等级 | LIGHT_HINT | 新学习者实测 L1 | `test_new_learner_defaults_to_light_hint` |
| 默认 FULL_SOLUTION 次数 | 0 | 0（默认路径全部 ≤L3） | `test_full_solution_never_default` |
| 显式 L4 + 证据门槛 | 仅证据足够时出现 | 满足门槛→L4；证据薄/新学习者→≤L3/L1 | 对应测试 |
| 多轮教学动作 | ≥3 | 4（测试）/ trace 4 | 多轮测试 + trace |
| 证据影响下一任务 | 必须可观察 | 首选任务 A→B 且出现 REVIEW 理由 | 多轮测试 |
| 判题确定性 | 同输入同输出 | 逐字段相等（跨实例） | 确定性测试 |
| canonical trace 回放一致 | ≥3 轮、assessment/evidence/final_state 可重建 | 3 assessment / 6 evidence / `final_state` 相等（19 事件） | `cf_loop_canonical.jsonl` + 共享 `replay_trace` 实测 |

复现命令：

```bash
cd /root/at-m1-offline
"/root/Autonomous Teacher/.venv/bin/python" -m pytest \
  tests/m1_offline/test_cf_judge.py \
  tests/m1_offline/test_cf_teacher.py \
  tests/m1_offline/test_cf_negatives.py -q
# 统计/闭环 trace 生成（确定性）：见交付报告中的脚本说明
```

## 10. 已知限制与 UNVERIFIED

### 10.1 已知限制

- **不是安全沙箱**：见 §5.4；只能用于离线合成数据。
- **复杂度诊断是启发式**：`wrong_complexity` 由"小用例通过 + 大用例墙钟超时"推断，不做静态复杂度证明；受机器负载影响（本机参考解最大 0.077s，与 2s 超时有 ~25× 余量，但极端负载仍可能误判）。
- **隐藏 fixture 信任边界**：judge 对调用方传入的 hidden dict 原样判分；磁盘 fixture 被篡改不可检测（由 "全部隐藏用例可被参考解通过" 测试与代码评审保障）。
- **混合缺陷归类取主导证据**：如同时超时与答案错，按主导信号只给一个主类（可能附 `runtime_error`），不是完整缺陷列表。
- **学习者模型是合成代理**：b-core `LearnerModel` 为 bounded running average，不是心理测量模型；掌握度数值仅用于机制验证。
- **提示文本为自编合成内容**：不是来自真实课程/教材，FULL_SOLUTION 为参考解文本，仅用于机制演示。
- **依赖 b-core 接口版本**：`AdaptivePolicy`/`DiagnosticEngine`/`types` 由 B 线 Teacher Core 维护；本规范按当前 checkout 的实际行为与测试编写，若其接口/行为变更需重跑本组件测试。
- **POSIX 定向**：进程组 kill 依赖 POSIX；Windows 会降级为仅 kill 主进程（未在 Windows 验证）。

### 10.2 UNVERIFIED / NOT_RUN

| 项 | 状态 | 说明 |
| --- | --- | --- |
| 真实教学效果 / 真实学习者提升 | `NOT_RUN`（且非目标） | 无真实学习者实验，禁止外推 |
| 真实 Provider / 大模型能力 | `NOT_RUN`（且非目标） | 零网络、零真实 Key；runtime 为 `simulated=True` 的 mock |
| M0 Runtime 既有 API 能力 | `UNVERIFIED` | M1 视角不 import/不声称 M0 已验收能力；`RuntimePort` 仅为抽象边界 |
| 安全沙箱/资源隔离 | `NOT_RUN`（明确不提供） | 见 §5.4，不是安全边界 |
| 恶意代码/资源耗尽/逃逸测试 | `NOT_RUN` | 非目标；judge 只做超时 fail-closed |
| 真实题库/标准复杂度标注 | `UNVERIFIED` | 题目与难度均为自编合成 |
| Windows 平台进程组行为 | `NOT_RUN` | 评测环境为 Linux/POSIX |
| 跨 seed/跨 case 的统计显著性 | `NOT_RUN` | 方差/显著性比对属 b-eval 计划范围，本组件只提供确定性行为证据 |

## 11. 变更记录

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v0 | 2026-11-19 | 初版：CFJudge + CFTeacher + 14 题/112 隐藏用例/3 学习者 fixture + 75 项测试 + 闭环 trace |
| v0.1 | 2026-11-19 | docs-only 补充（P2-6）：新增 §8.4 披露 `cf_teaching_loop.jsonl` 为 CF 域审计格式、共享 `replay_trace` 对其静默返回空结果；新增 canonical 回放 trace `cf_loop_canonical.jsonl` 并记录回放验证；无代码/测试变更 |
