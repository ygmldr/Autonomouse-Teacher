# M1 Offline 实验基线（EXPERIMENT_BASELINE）

- 文档状态：真实运行基线（**MEASURED**，非计划值）。
- 结论性质：**offline synthetic only, not real teaching effect**。所有数值只描述本 worktree 内的确定性离线合成模拟器；不得外推为真实教学效果、真实学习者提升或真实模型能力。
- 计划值（PLAN）与实际值的区分：目标覆盖数写为 PLAN，只有真实命令输出才标 MEASURED；未执行项一律 `NOT_RUN`，依赖外部系统/M0 能力的一律 `UNVERIFIED`。

## 1. 运行环境与来源（Provenance）

| 项 | 值 |
| --- | --- |
| UTC 日期 | `2026-11-19`（首次测量 `2026-11-19T18:14:29Z`） |
| worktree | `/root/at-m1-offline` |
| branch | `work/m1-offline-design` |
| 基线 commit（HEAD，未提交变更位于工作树） | `3e7afee077845a071cd364e93ab209cac20b2d5f` |
| Python | `3.11.15`（`/root/Autonomous Teacher/.venv/bin/python`） |
| pytest | `9.2.0` |
| 依赖冻结指纹（`m1_offline/**.py` + `fixtures/m1/**` 共 109 文件，按相对路径+内容 SHA-256 排序后取 SHA-256） | `b4bb2931065ac3416e4c84783f8a2bfba5e55c0f1f905591aa9cc2c98179cdd2` |
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
```

## 3. 测试结果（MEASURED）

### 3.1 完整 M1 B 线测试套件

| 运行 | 命令 | 结果 | 证据 |
| --- | --- | --- | --- |
| 落盘前（本文件尚未存在，`test_baseline_document_exists_and_is_bounded` 按设计失败） | `pytest tests/m1_offline -q` | **1 failed, 360 passed in 19.67s** | `/tmp/b_eval_measure/pytest_full_predoc.txt`（临时目录，非常驻交付物） |
| 落盘后（本文件存在） | `pytest tests/m1_offline -q` | **361 passed in 16.96s**（exit 0，0 failed） | 上述命令的真实输出；`tests/m1_offline` 共 361 项全绿 |

### 3.2 本 workstream 的 5 个评测测试文件

| 运行 | 结果 |
| --- | --- |
| 落盘前（同上，仅基线文档存在性测试失败） | **1 failed, 71 passed in 9.69s** |
| 落盘后 | **72 passed in 7.49s**（exit 0，0 failed） |

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
- 失败案例数：**58**（每轮 fail 记录 `policy/seed/round/case_id/scorer_id/failure_modes`，清单在 `docs/m1/reports/eval_baseline_v1.json`）。
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
| C1_hidden_public_separation | **PASS** | hidden fixtures 21 个；公开扫描面 103 文件；overlap=[] |
| C2_hidden_leakage | **PASS** | 公开面 103 文件；隐藏-only needles 34 个；子串命中 **0**；滑动窗口哈希命中 **0** |
| C3_injection_not_in_system_prompt | **PASS** | 注入文档 4 份；needles 9；system instruction 块 1；命中 **0** |
| C4_no_network_or_real_data | **PASS** | 扫描 138 文件；网络 import / API Key / 真实邮箱 / 手机号 / SSN 形态命中 **0** |

- 结构化报告产物：`docs/m1/reports/contamination_v1.json`（只含计数/状态，不回显隐藏正文或隐藏 ID）。
- 额外的注入不变性：`InterviewCoach.system_instructions()` 与 `instruction_hash()` 在加载注入文档前后不变（`test_interview_injection_documents_stay_out_of_system_instructions`）。
- `NOT_RUN` 不是 PASS：C1–C4 当前均为可评估且 PASS；若隐藏 fixture 缺失则必须为 `NOT_RUN`（单测覆盖）。

## 9. 可运行 demo 与确定性（MEASURED）

| 项 | 实测 |
| --- | --- |
| `python -m m1_offline.demo` 退出码 | `0` |
| 连续两次 stdout 逐字节一致 | **是**（`diff` 无输出，退出码 0） |
| stdout SHA-256（两次） | `fd7228121359bf4732d9654f94f5e42409921b16b456a43d18e9e5a2acf2e224`（两次相同） |
| demo 内部双跑确定性检查 | `[determinism] trace_bytes_identical=True digest_match=True state_match=True -> PASS` |
| demo 输出闭环/回放/对照/污染四项 | `closed_loop=PASS replay=PASS determinism=PASS comparison=PASS contamination=PASS` |

确定性产物（`--write-artifacts`，两跑字节一致）：

| 产物 | 行数 | SHA-256 |
| --- | --- | --- |
| `docs/m1/traces/loop_v1_3rounds.jsonl` | 19 | `ed850c775f1745a6672b0dbfb41a169f9324a74ec9d7caef108709b98e1acf64` |
| `docs/m1/traces/loop_v0_3rounds.jsonl` | 19 | `4019c9465b860335c57a9826b5cd01e6f3bc8697fa3969e847139a1d5c54176f` |
| `docs/m1/reports/eval_baseline_v1.json` | — | `4e98c398d61c809572c463d32fb452414f9ee9547736bd860a6d639296c1a548` |
| `docs/m1/reports/eval_baseline_v1.md` | — | `e52bddf06b7b927cba369b41fb488b767d0892f8415c58a80d6f2b58140d46a3` |
| `docs/m1/reports/contamination_v1.json` | — | `3853d2496ec72b0c8fb851e5ea6194e6434d6700836ecb16989915358be0856e` |

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
| demo 确定性 | 连续两次一致 | 见 §9 | MEASURED |
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
6. 工作树在本文件生成时含未提交变更（HEAD 仍为基线 commit）；冻结指纹 `b4bb2931…` 覆盖 109 个依赖文件，用于复现校验。

## 13. 复现

```bash
cd /root/at-m1-offline
git rev-parse HEAD          # 3e7afee077845a071cd364e93ab209cac20b2d5f（基线；工作树含本 workstream 新增文件）
"/root/Autonomous Teacher/.venv/bin/python" -m pytest tests/m1_offline -q
"/root/Autonomous Teacher/.venv/bin/python" -m m1_offline.demo --write-artifacts
```

复现结果若与本文不一致，以新的真实运行结果为准并更新本文件，不得保留旧"通过"。
