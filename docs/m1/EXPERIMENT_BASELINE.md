# M1 Offline 实验基线（EXPERIMENT_BASELINE）

- 文档状态：真实运行基线（**MEASURED**，非计划值）。**版本：post-review fix（C2 candidate）** —— 审查冻结 commit `0bb13d2`，报表/文档修复于 `2026-11-19T18:48Z` 重新生成；最终 commit 由 Lead 记录在 `docs/parallel/STATUS.md`。
- 结论性质：**offline synthetic only, not real teaching effect**。所有数值只描述本 worktree 内的确定性离线合成模拟器；不得外推为真实教学效果、真实学习者提升或真实模型能力。
- 计划值（PLAN）与实际值的区分：目标覆盖数写为 PLAN，只有真实命令输出才标 MEASURED；未执行项一律 `NOT_RUN`，依赖外部系统/M0 能力的一律 `UNVERIFIED`。

## 1. 运行环境与来源（Provenance）

| 项 | 值 |
| --- | --- |
| UTC 日期 | `2026-11-19`（首次测量 `2026-11-19T18:14:29Z`；post-review 修复后 artifacts 重生成于 `2026-11-19T18:48Z`） |
| worktree / branch | `/root/at-m1-offline` / `work/m1-offline-design` |
| base commit（worktree 基线；**不是 HEAD**） | `3e7afee077845a071cd364e93ab209cac20b2d5f` |
| implementation commit（冻结审查 commit，artifact 在其之上生成） | `0bb13d27b069dfb71b31ce7e02f9cde41f9bb071`；post-review 修复尚未提交，最终 commit 见 `docs/parallel/STATUS.md`（Lead-owned） |
| 生成时工作树状态 | `working_tree_dirty=True`（未提交的 post-review 修复位于审查 commit 之上；artifact 的 `environment` 字段如实记录） |
| Python / pytest | `3.11.15`（`/root/Autonomous Teacher/.venv/bin/python`）/ `9.2.0` |
| 依赖指纹（可复现，算法见下） | `ad30fbdae1d7318d346b0625a1157df20f9139ef2ece00f7f118a1c9ced6abd0` |
| 依赖指纹算法 | 覆盖 `m1_offline/**/*.py` + `fixtures/m1/**/*`（共 109 文件，排除 `__pycache__`/`*.pyc`）：对每个文件取 `sha256(file_bytes)`，按相对 POSIX 路径排序生成 `"<sha256>  <relative/path>"` 清单行，指纹 = `sha256("\n".join(lines) + "\n")`（UTF-8）。一行复现命令见 §2 第 5 条。旧指纹 `b4bb2931…` 由未文档化脚本产生、**已废弃（superseded）**，不可复现，勿再引用。 |
| 说明 | b-core/b-cf/b-interview 已 frozen（Lead 确认），本文件的所有数值取自冻结后的工作树；Python 包以工作树内文件为准（未 pip install）。 |

## 2. 命令（Exact Commands）

```bash
# 1) 完整 M1 B 线测试（本 workstream 定义性验证）
cd /root/at-m1-offline
"/root/Autonomous Teacher/.venv/bin/python" -m pytest tests/m1_offline -q

# 2) 本 workstream 的 5 个评测测试文件
cd /root/at-m1-offline
"/root/Autonomous Teacher/.venv/bin/python" -m pytest \
  tests/m1_offline/test_closed_loop.py \
  tests/m1_offline/test_evaluation_protocol.py \
  tests/m1_offline/test_negatives.py \
  tests/m1_offline/test_contamination.py \
  tests/m1_offline/test_compare_v0_v1.py -q

# 3) 可运行 demo（离线、无 Key、确定性）
cd /root/at-m1-offline
"/root/Autonomous Teacher/.venv/bin/python" -m m1_offline.demo
# 生成/刷新确定性 trace 与报表：
"/root/Autonomous Teacher/.venv/bin/python" -m m1_offline.demo --write-artifacts

# 4) demo 确定性：连续两次运行，stdout 逐字节比较
"/root/Autonomous Teacher/.venv/bin/python" -m m1_offline.demo > /tmp/demo_a.txt 2>&1
"/root/Autonomous Teacher/.venv/bin/python" -m m1_offline.demo > /tmp/demo_b.txt 2>&1
diff /tmp/demo_a.txt /tmp/demo_b.txt && sha256sum /tmp/demo_a.txt /tmp/demo_b.txt

# 5) 可复现依赖指纹（P2-2；reviewer 一行命令，输出必须等于 §1 的指纹）
"/root/Autonomous Teacher/.venv/bin/python" -c "from m1_offline import REPO_ROOT; from m1_offline.evaluation.report import dependency_fingerprint; print(dependency_fingerprint(REPO_ROOT))"

# 6) 重新生成报表 artifacts（含 comparison.failure_cases 与精确 commit provenance）
"/root/Autonomous Teacher/.venv/bin/python" -m m1_offline.demo --write-artifacts
# contamination_v1.json 由 run_contamination_suite(...) + report.environment_snapshot() 生成（见 §8）
```

## 3. 测试结果（MEASURED）

### 3.1 完整 M1 B 线测试套件

| 运行 | 命令 | 结果 | 证据 |
| --- | --- | --- | --- |
| 冻结审查 commit `0bb13d2`（post-review 修复前） | `pytest tests/m1_offline -q` | **361 passed in 16.76s**（exit 0，0 failed；reviewer 独立复核同绿） | 真实输出；本轮新增 4 项 post-review 回归测试之前 |
| post-review 修复后（C2 candidate，本文档最终状态） | 同上 | **365 passed in 16.66s**（exit 0，0 failed；+4 项：artifact failure_cases 一致性 1 + fingerprint/provenance/artifact-key 3） | 上述命令在本文档最终状态的真实输出；365 项全绿 |

### 3.2 本 workstream 的 5 个评测测试文件

| 运行 | 结果 |
| --- | --- |
| 冻结审查 commit（post-review 修复前） | **72 passed in 7.49s**（exit 0，0 failed） |
| post-review 修复后（最终状态） | **76 passed in 7.93s**（exit 0，0 failed；含 +4 项 post-review 回归测试） |

覆盖映射（测试文件 → 协议条款）：

| 测试文件 | 覆盖 |
| --- | --- |
| `tests/m1_offline/test_closed_loop.py` | ≥3 轮闭环、JSONL trace、按 event_id/loop_id 回放、无证据不涨掌握度、文本/自评不涨、两次运行逐字节一致、v0/v1 均可回放 |
| `tests/m1_offline/test_evaluation_protocol.py` | 评测器独立性（CF judge / InterviewRubric / CFTeacher.assess）、自评文本不影响判分、盲评签名无策略标识、v0/v1 协议结构/方差/可复现、文档边界 |
| `tests/m1_offline/test_negatives.py` | 幻觉、拒绝、超时、工具失败、过期来源、证据不足、重复任务、隐藏 fixture 缺失 —— 全部 fail-closed 或显式 marker |
| `tests/m1_offline/test_contamination.py` | 公开/隐藏分离、子串+哈希泄漏扫描、注入文档不进入 system instructions、隐藏 ID 不进入公开面、无网络/Key/真实数据形态 |
| `tests/m1_offline/test_compare_v0_v1.py` | 固定 case/seed、盲评、均分/方差、失败案例、可复现、结论措辞边界 |

## 4. 闭环运行结果（MEASURED）

命令：`python -m m1_offline.demo`（seed=0，`max_rounds=3`，确定性注入时钟）。

| 指标 | 计划值（PLAN） | 实测值（MEASURED） |
| --- | --- | --- |
| 完整轮次（v1） | ≥3 | **3** |
| 完整轮次（v0） | ≥3 | **3** |
| Trace 事件数（v1 / v0） | 4 基线步骤 + 5 步 × 3 轮 = 19 | **19 / 19** |
| 回放一致（assessments / evidence / state / 步骤序列） | 100% | **4/4 通过（两者均通过）** |
| 通过轮次（v1 / v0，隐藏用例全通过才计 passed） | — | **1 / 1** |
| 终止原因 | max_rounds 或显式 halt | `max_rounds`（无 halt）/ `max_rounds` |
| 失败标记 | 显式记录 | `['hidden_cases_failed']` |
| v1 trace digest | — | `ed850c775f1745a6672b0dbfb41a169f9324a74ec9d7caef108709b98e1acf64` |
| v0 trace digest | — | `4019c9465b860335c57a9826b5cd01e6f3bc8697fa3969e847139a1d5c54176f` |
| 最终掌握度（v1 与 v0 相同） | — | `{array-basics: 0.0875, dp-basics: 0.0, prefix-sums: 0.0, two-pointers: 0.0}` |
| 每轮任务 | — | round1 `cf_array_max_subarray`, round2 `cf_array_running_sum`, round3 `cf_array_sum_even` |

事件步骤序列（v1，19 事件）：
`goal → diagnose → gap → plan → (action → response → assess → memory → next_task) × 3`。

闭环中的"学习者回答"是**模拟学习者**经 `MockRuntimePort` 返回的合成提交（`simulated=True`），"独立评估"由 `CFJudge` 在本地子进程对隐藏用例判分；教师策略从不给自己打分。

## 5. 证据驱动规则（MEASURED，测试断言）

| 规则 | 实测结果 | 证据测试 |
| --- | --- | --- |
| 无证据：`LearnerModel.state().mastery == {}` 且 delta=0 | 通过（0 涨点） | `test_closed_loop.py::test_no_evidence_no_mastery` |
| 纯文本/自述（`EXPLANATION` 且 `observed_score=None`）不涨掌握度 | 通过（delta=0） | 同上 |
| `HINT_REQUEST` 即使带 score 也不涨（不计分 kind） | 通过（delta=0） | 同上 |
| 只有 `ASSESSMENT` + score 才涨 | 通过（涨点 >0） | 同上 |
| harness 无基线证据时诊断 `NEEDS_REVIEW`、mastery 为空、显式 `insufficient_evidence` | 通过 | `test_closed_loop.py::test_harness_diagnose_without_evidence_claims_no_mastery` |
| "All tests pass / 全部通过" 文本 + 错误代码：判分失败、显式 `hallucination_suspected`、掌握度不涨 | 通过 | `test_closed_loop.py::test_hallucinated_success_text_does_not_raise_mastery` |

## 6. teacher_v0 vs teacher_v1 对照（MEASURED）

协议：固定 14 题合成 case catalog（`fixtures/m1/cf/problems` + 隐藏判分 `fixtures/m1/cf/hidden`），固定 seeds `[0,1,2]`，每条轨迹 12 轮，共 2 策略 × 3 seeds = 6 条轨迹 / **72 个已评估轮**；盲评 rubric（`blind_rubric_v0`，只接收脱敏轨迹，不含策略名/教师文本）；`mastery_threshold` 冻结为 1.01 仅用于对照固定轮数（对照控制项，不是学习结论）。

| 维度 | teacher_v0 mean | teacher_v0 variance | teacher_v1 mean | teacher_v1 variance | delta (v1-v0) |
| --- | --- | --- | --- | --- | --- |
| correctness（隐藏用例通过比例均值） | 0.248512 | 0.004634 | 0.304067 | 0.001465 | +0.055555 |
| rounds_to_first_success（越早越高，归一到 [0,1]） | 0.916667 | 0.004630 | 0.916667 | 0.004630 | +0.000000 |
| hint_efficiency（干预越轻越高） | 0.750000 | 0.000000 | 0.522222 | 0.000189 | -0.227778 |
| independence（低干预通过占比） | 1.000000 | 0.000000 | 0.500000 | 0.018519 | -0.500000 |

- 实际评估题数：**catalog 14 题，实际被评估 12 题**（每条 12 轮轨迹各覆盖 12 个不同 case；剩余 2 题未在固定 12 轮内出现，未评估，不虚报）。
- 失败案例数：**58**。完整 per-failure 清单**已持久化**在 `docs/m1/reports/eval_baseline_v1.json` 的 **`comparison.failure_cases`**（58 条；每项含 `policy/policy_version/seed/round/case_id/scorer_id/failure_modes/hidden_cases_passed/hidden_cases_total`）。同一 artifact 的 `comparison.statistics` 记录每维均分/方差、`comparison.delta_v1_minus_v0`、`comparison.run_digest`、`comparison.conclusion`；单测 `test_persisted_report_contains_comparison_failure_cases` 断言 artifact 与真实运行一致（`run_digest`、条数、必填字段），防止"文档说有清单、artifact 里没有"。
- 对照 run digest：`cb6cb07da2a68622f2ccceac560093f36d4385ad13632c8ce12ccdff02d1645e`（两次独立运行一致，见 `test_compare_v0_v1.py`）。
- 结论措辞（实测输出）：`Offline synthetic simulation only. ... This is not real teaching effect: no significance is claimed and no real-world effectiveness is demonstrated.` —— **不得**据此宣称 v1 优于 v0；上表只是模拟器内部行为差异。

## 7. 失败负例矩阵（MEASURED）

`tests/m1_offline/test_negatives.py` 全绿（结果见 §3）。每种负例均断言"不得静默成功"：

| # | 负例 | 触发（离线合成） | 实测结果 |
| --- | --- | --- | --- |
| N1 | 模型幻觉 | 错误代码 + "All tests pass/全部通过/无需测试" | 判分失败；`hallucination_suspected` 显式 marker；掌握度不涨 |
| N2 | 拒绝回答 | `"Sorry, I can't help with that request."` | 判分失败；`refusal` marker；不计成功 |
| N3 | 超时 | 注入 `TimeoutError` / `MockRuntimePort(raise)` / error response | `halt_reason=runtime_timeout` 等；0 assessment；无静默成功 |
| N4 | 工具失败 | 非法 Python 提交（语法错误） | `tool_error` 显式 marker；`passed=False`；掌握度不涨 |
| N5 | 过期/冲突来源 | `FreshnessManager.classify` 过期/冲突 fixture | 全部 `RECHECK`；`curriculum_eligible=False`；`apply` 不写 UPDATE |
| N6 | 学习者证据不足 | 无基线证据运行 | 诊断 `NEEDS_REVIEW` + `insufficient_evidence`；mastery 为空 |
| N7 | 重复任务 | 强制第二轮重复同一 task | `halt_reason=duplicate_task`；只 1 次 assessment；不重复计成功 |
| 额外 | 隐藏 fixture 缺失 | 合成 `hidden=None` 的 case | `hidden_fixture_missing` 显式 marker；`passed=False` |

## 8. 污染 / 泄漏检查（MEASURED）

命令入口：`m1_offline.evaluation.contamination.run_contamination_suite(REPO_ROOT, injection_texts=..., system_instructions=<real InterviewCoach.system_instructions()>)`。

| check | 结果 | 实测计数 |
| --- | --- | --- |
| C1_hidden_public_separation | **PASS** | hidden fixtures 21 个；公开扫描面 105 文件；overlap=[] |
| C2_hidden_leakage | **PASS** | 公开面 105 文件；隐藏-only needles 34 个；子串命中 **0**；滑动窗口哈希命中 **0** |
| C3_injection_not_in_system_prompt | **PASS** | 注入文档 4 份；needles 9；system instruction 块 1；命中 **0** |
| C4_no_network_or_real_data | **PASS** | 扫描 139 文件；网络 import / API Key / 真实邮箱 / 手机号 / SSN 形态命中 **0** |

- 结构化报告产物：`docs/m1/reports/contamination_v1.json` —— `contamination.checks[]` 含 C1–C4 状态与计数、`contamination.status_counts`、`environment`（同 §1 provenance 字段）；只含计数/状态，不回显隐藏正文或隐藏 ID。
- 额外的注入不变性：`InterviewCoach.system_instructions()` 与 `instruction_hash()` 在加载注入文档前后不变（`test_interview_injection_documents_stay_out_of_system_instructions`）。
- `NOT_RUN` 不是 PASS：C1–C4 当前均为可评估且 PASS；若隐藏 fixture 缺失则必须为 `NOT_RUN`（单测覆盖）。

## 9. 可运行 demo 与确定性（MEASURED）

| 项 | 实测 |
| --- | --- |
| `python -m m1_offline.demo` 退出码 | `0` |
| 连续两次 stdout 逐字节一致 | **是**（`diff` 无输出，退出码 0） |
| stdout SHA-256（两次） | `2282caff40787317d8222401e2a7a0f9cdec6d9ac86d2ed8286927a0792df3cb`（两次相同；相对 post-review 前的 `fd7228…` 变化的原因是审查 commit `0bb13d2` 新增了公开面文件（reviewer 文档/规范 trace），使 contamination 计数 103→105、138→139，属于真实状态变化而非代码不确定性） |
| demo 内部双跑确定性检查 | `[determinism] trace_bytes_identical=True digest_match=True state_match=True -> PASS` |
| demo 输出闭环/回放/对照/污染四项 | `closed_loop=PASS replay=PASS determinism=PASS comparison=PASS contamination=PASS` |

确定性产物（`--write-artifacts`，两跑字节一致）：

| 产物 | 行数 | SHA-256 |
| --- | --- | --- |
| `docs/m1/traces/loop_v1_3rounds.jsonl` | 19 | `ed850c775f1745a6672b0dbfb41a169f9324a74ec9d7caef108709b98e1acf64` |
| `docs/m1/traces/loop_v0_3rounds.jsonl` | 19 | `4019c9465b860335c57a9826b5cd01e6f3bc8697fa3969e847139a1d5c54176f` |
| `docs/m1/reports/eval_baseline_v1.json` | — | `25ed416a07cf3b5aad0f0a86beb8f760477662f43d062b723746db2bd25f47af`（含 `comparison.failure_cases` 58 条 + `environment` 精确 provenance） |
| `docs/m1/reports/eval_baseline_v1.md` | — | `154ef1d862177298233a564e2a51247f37f74667e74d942862a1b48c1f4b5bee` |
| `docs/m1/reports/contamination_v1.json` | — | `8b80a6f391a09d92a43f4b5ce8a456f088b530d27ea254c133ad909b8e548ff8` |

## 10. 计划值 vs 实际值总表

| 指标 | 计划值（PLAN） | 实际值（MEASURED） | 证据等级 |
| --- | --- | --- | --- |
| 闭环完整轮次 | ≥3 | 3 | MEASURED |
| Trace 事件数 | 19（max_rounds=3） | 19 | MEASURED |
| 回放一致率 | 100% | 4/4 项一致（assessments/evidence/state/steps） | MEASURED |
| 无证据掌握度变化 | 0 | 0 | MEASURED |
| 文本/自述掌握度变化 | 0 | 0 | MEASURED |
| v0/v1 固定 case catalog | ≥12 | 14（实际评估 12） | MEASURED |
| v0/v1 seed 数 | ≥3 | 3 | MEASURED |
| v0/v1 评估轮数 | ≥12 | 72 | MEASURED |
| 每维均分/方差 | 记录 | 4 维 × 2 策略均记录（见 §6） | MEASURED |
| 失败案例数 | ≥1 | 58 | MEASURED |
| 失败负例覆盖 | 7/7 | 7/7 + 额外 1 项 | MEASURED |
| 污染检查 | 全 PASS | C1–C4 全 PASS（NOT_RUN=0） | MEASURED |
| 隐藏泄漏命中 | 0 | 0（子串 0 / 哈希 0） | MEASURED |
| demo 确定性 | 连续两次一致 | 见 §9（SHA-256 `2282caff…`） | MEASURED |
| 报表 failure_cases 持久化 | ≥1 且与运行一致 | 58 条，位于 `comparison.failure_cases`，单测校验 | MEASURED |
| 测试套件 | 全绿 | 见 §3 | MEASURED |

## 11. NOT_RUN（未执行，不得当作 PASS）

- **真实 Provider / live runtime 评测**：NOT_RUN —— 本 workstream 明确离线合成，禁止真实网络/Key/Provider 调用。
- **真实学习者学习效果 / 真实教学效果**：NOT_RUN —— 无法在离线合成环境中测量，且本文件不做任何外推。
- **大规模多种子统计推断（如显著性检验、置信区间）**：NOT_RUN —— 3 seeds 只用于记录方差，不构成统计结论；对照结论已明确 no significance claimed。
- **interview 线的多轮教学闭环端到端**：NOT_RUN（本 workstream 的闭环 harness 只覆盖 CF 教学线；interview 评测器独立性/注入/新鲜度分别由测试覆盖，未做 interview round-loop 集成）。
- **M0 Runtime API 验收**：UNVERIFIED —— `RuntimePort` 是 M1 的 mock 抽象，未验证任何 M0 live 能力。

## 12. 已知限制（Limitations）

1. 模拟学习者成功概率是显式写死的合成函数（能力先验 + 动作支持 - 难度惩罚，见 `harness.py: ACTION_SUPPORT`），**未经校准**，不代表真实学习者。
2. 模拟"学习者回答"= 公开参考解或确定性变异版本，不是真实模型输出；`simulated=True`。
3. `CFJudge` 是本地子进程 + 超时 + 临时目录，**不是** OS 安全沙箱（无容器/seccomp/namespace）；仅用于合成 CC0-1.0 fixtures。
4. 隐藏用例为合成生成；判分只覆盖 fixtures 中的题面契约。
5. v0/v1 的差异来自模拟器的动作支持参数与策略行为，已被显式标注为"模拟器内部差异"，不得解释为真实教学收益。
6. 工作树在本文件生成时含未提交的 post-review 修复（implementation commit `0bb13d2`，`working_tree_dirty=true`，见 artifact 的 `environment`）；可复现依赖指纹 `ad30fbd…` 覆盖 109 个依赖文件，旧 `b4bb2931…` 已废弃。

## 13. 复现

```bash
cd /root/at-m1-offline
git rev-parse HEAD          # 审查/实现 commit（post-review 修复提交后为 C2 SHA；artifact 记录 implementation_commit=0bb13d2）
"/root/Autonomous Teacher/.venv/bin/python" -m pytest tests/m1_offline -q
"/root/Autonomous Teacher/.venv/bin/python" -m m1_offline.demo --write-artifacts
"/root/Autonomous Teacher/.venv/bin/python" -c "from m1_offline import REPO_ROOT; from m1_offline.evaluation.report import dependency_fingerprint; print(dependency_fingerprint(REPO_ROOT))"
```

artifact provenance 约定（P2-1）：`environment.base_sha` 恒为基线 `3e7afee…`；`environment.implementation_commit` 是生成 artifact 时的审查/实现 commit（当前 `0bb13d2…`），并附 `implementation_commit_note` 指向 `docs/parallel/STATUS.md` 记录的最终 commit；`environment.working_tree_dirty` 如实标记生成时是否有未提交修复。reports 中不再使用会误导的 `git_sha`（不暗示 HEAD==base）。

复现结果若与本文不一致，以新的真实运行结果为准并更新本文件，不得保留旧"通过"。

## 14. Post-review 修复记录（C2 candidate）

审查发现（frozen `0bb13d2`）与本次修复（仅限 b-eval scope）：

| finding | 修复内容 | 验证 |
| --- | --- | --- |
| **P1-1**（阻塞）：`EXPERIMENT_BASELINE.md` 声称 per-failure 清单在 `eval_baseline_v1.json`，但该 JSON 只有 16 个聚合 metric、无 failure_cases | `m1_offline/evaluation/report.py` 增加结构化 `sections`；`m1_offline/demo.py` 的 artifact 生成把 `comparison.failure_cases`（58 条，含 policy/seed/round/case_id/scorer_id/failure_modes 等）+ `comparison.statistics/delta/run_digest/conclusion` 持久化到 `docs/m1/reports/eval_baseline_v1.json`；§6 措辞改为精确指向该 key | 新单测 `test_persisted_report_contains_comparison_failure_cases`（artifact 条数/`run_digest`/必填字段与真实 `run_comparison()` 完全一致）；§6 引用被 `test_baseline_document_references_persisted_failure_cases` 校验 |
| **P2-1**：reports JSON 的 `environment.git_sha` 仍写 base `3e7afee`，暗示 HEAD==base | `report.environment_snapshot()` 改为 `base_sha`（恒 3e7afee）、`implementation_commit`（生成时 HEAD=0bb13d2）、`implementation_commit_note`（最终 commit 见 `docs/parallel/STATUS.md`）、`working_tree_dirty`、`dependency_fingerprint`，移除 `git_sha`；两个 reports JSON 重生成 | 新单测 `test_report_artifacts_record_precise_commit_provenance`（禁止 `git_sha`，校验 base/impl/note/dirty/fingerprint） |
| **P2-2**：`b4bb2931…` 依赖指纹不可复现 | `report.py` 新增 `dependency_manifest()` / `dependency_fingerprint()`（算法固定并文档化：109 文件、按相对 POSIX 路径排序的 `sha256  path` 清单、`sha256(manifest+"\n")`）；重算并替换为 `ad30fbdae1d7318d346b0625a1157df20f9139ef2ece00f7f118a1c9ced6abd0`；旧指纹标记 superseded；一行复现命令见 §2 第 5 条 | 新单测 `test_dependency_fingerprint_is_reproducible_and_documented`（两次计算一致、manifest 已排序、文档记录同一指纹与命令） |

重新生成的确定性 artifacts（本 §9 表已更新）：`eval_baseline_v1.json` `25ed416a…`、`eval_baseline_v1.md` `154ef1d8…`、`contamination_v1.json` `8b80a6f3…`；`loop_v1_3rounds.jsonl` `ed850c77…`、`loop_v0_3rounds.jsonl` `4019c946…` 未变（trace 内容不受报表修复影响）。demo 两次运行 stdout 仍逐字节一致（`2282caff…`）。

本文件在 C2 提交前生成；`implementation_commit=0bb13d2` 与 `working_tree_dirty=true` 是对该事实的如实记录，最终提交 SHA 以 `docs/parallel/STATUS.md` 为准。
