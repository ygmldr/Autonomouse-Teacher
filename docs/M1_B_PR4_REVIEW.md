# M1-B B-PR4 独立评审 — CF/Interview/Freshness 双域统一闭环与 Domain Ports

- **评审身份**：独立 Reviewer（未参与实现；仅新增本文件并 commit）。
- **评审时间**：2026-11-20 UTC。
- **仓库 / 工作区**：`/root/m1b/review-pr4`；分支 `b-next/pr4-review`。
- **HEAD**：`11a4f7217735d6fc4a0799acdd1371cf25b4358c`（`merge(m1b): stack final B-PR1/PR2/PR3 under B-PR4 domain ports`）。
- **对照基线**：`4706250643fd42d48d69ddad7159e011955fa9fd`（`work/m1a-mvp` / B 线历史冻结交付）；PR4 合并树同时包含最终 PR1+PR2+PR3。
- **范围限定**：仅评审 PR4（两域 vertical/ports、B4-01/02/03）在本合并树上的离线、合成、确定性证据；不评审 Live/真实 Provider/真实简历/JD/联网研究；不构成真实学习效果结论。
- **证据标记**：`INDEPENDENTLY_REEXECUTED_THIS_TURN`（本轮真实复跑）/ `OWNER_REPORTED`（仅引用他人声称）/ `NOT_RUN`（未执行）。本文所有实测数字均附命令或产物路径。

## 0. 结论

**`PASS_WITH_ACTIONS`**（仅限 B-PR4 离线集成范围）。

- **P0 = 0**：未发现跨学习者泄漏、真实网络/Key/Provider 调用、受保护路径变更、可伪造判题通过或数据破坏。
- **P1 = 3**：多轮 interview 计划不随会话持久化（重启后阶段漂移/重开）；hidden 读取 allow-list 被 `demo_b4.py` 实际突破且静态守卫可绕过；“统一 Replay 重建 snapshot/session / 版本不兼容明确拒绝”的文档声明超出实现。
- **P2 = 7**：见 §7。
- **B4 状态**：B4-01 **VERIFIED**；B4-02 **VERIFIED（会话内，E2E-MOCK；重启缺陷见 P1-1）**；B4-03 **VERIFIED（E2E-MOCK；无持久复核队列见 P2-2）**。
- **不可从本报告推出的结论**：真实教学/学习收益 **NOT_VERIFIED**；无真实网络、真实简历/JD、Provider、LiveGate；所有启发式阈值 **UNCALIBRATED**；B4 只到 `E2E-MOCK + DETERMINISTIC`。

## 1. 独立复跑（INDEPENDENTLY_REEXECUTED_THIS_TURN）

环境：`/root/Autonomous Teacher/.venv/bin/python`（Python 3.11.15 / pytest 9.2.0 / ruff 0.17.5）；工作区如上。

| # | 命令（cwd=/root/m1b/review-pr4） | 实测 | 判定 |
|---|---|---|---|
| 1 | `python -m pytest tests/m1_teacher -q` | **859 passed in 81.59s**，0 failed / 0 skipped / 0 error | PASS |
| 2 | `python -m pytest tests/m1_teacher/test_b4_e2e.py -q` | **9 passed in 4.98s** | PASS |
| 3 | `python -m pytest tests/m1_teacher/test_vertical_policy.py -q` | **16 passed in 1.27s** | PASS |
| 4 | `python -m pytest tests/m1_teacher/test_interview_domain.py test_interview_fixtures.py test_interview_judge.py test_freshness_service.py -q` | **60 passed in 0.22s** | PASS |
| 5 | `python -m pytest test_b4_e2e.py test_vertical_policy.py -q`（复跑） | **25 passed in 5.58s** | PASS |
| 6 | `ruff check m1_teacher tests/m1_teacher` | `All checks passed!`，exit 0 | PASS |
| 7 | `python -m m1_teacher.demo_b4 --json` ×2，`cmp` + `sha256sum` | 两次逐字节相同；`sha256=6b7bb66e36a38bd640d5b47d206d8fee24a446df9b42dbe76d20dd8cc50bef83`（15,108 bytes），exit 0；与 Owner 文档 §7 声称值一致 | PASS |
| 8 | `git status --porcelain` | 空（复跑前后均干净） | PASS |
| 9 | 基线测试集合复算（`git archive 25185b1` → collect-only） | **774 collected**；与 HEAD 的 859 节点集比较：基线 774 个节点 **0 缺失**，HEAD 新增 85（60 vertical + 16 + 9） | PASS |
| 10 | `git diff --name-only 4706250..HEAD` | 96 文件，仅 `docs/ fixtures/ m1_teacher/ tests/`；无 M0/security/bridge/config/g*/scripts/g4/LiveGate/plugins | PASS |

补充静态扫描（SOURCE_INSPECTED）：`m1_teacher/**/*.py` 无 `requests/urllib/httpx/aiohttp/openai/anthropic/api_key` 等新增调用；`socket` 仅出现在 PR1 sandbox 的本地探测（`gethostname/if_nameindex`），非网络访问；vertical fixtures 全部 `synthetic=true`、`license=CC0-1.0`、URI 为 `.invalid` 合成域；diff 中无真实 secret/Key 值（仅文档中的禁用词）。**无真实网络/Provider/Key**。

## 2. 仓库、范围与合同变更

- 工作树干净；HEAD 与任务给定 `11a4f72` 一致；分支正确。
- 受保护路径：**0 变更**。M0（`src/autoteacher_m0`）、`security`、`bridge`、`config/g*`、`scripts/g4*`、LiveGate、`plugins` 均未触碰。
- PR4 自己的实现文件：`m1_teacher/session/vertical.py`（801）、`domains/interview.py`（716）、`knowledge/freshness.py`（1253）、`assessment/interview_judge.py`（723）、`demo_b4.py`（457）、fixtures/tests；engine/history/contracts 为 additive 变更。
- **D12 add-only 已核实**：`TEACHING_ACTION_KIND` 仅追加 `SOCRATIC_QUESTION`、`ASK_CLARIFICATION`；`HISTORY_EVENT_TYPE` 仅追加 `ASSESSMENT_PREPARED`。`docs/M1_ADR_001_DOMAIN_CONTRACTS.md` §6b change-log 同时记录两处（B-PR2 `ASSESSMENT_PREPARED`；B-PR4 两个 action kind）；`tests/m1_teacher/test_contracts.py` 仅同步冻结期望，未删除/重命名既有值。
- 无测试删除、无 `skip/xfail` 新增用于本次 PR4 语义（全量 0 skipped）；`test_crash_recovery`/`test_turn_transaction`/`test_scoped_idempotency` 等 PR1/2/3 套件仍在同一树中通过。
- 既有测试的显式修改仅限：`test_contracts.py` 枚举期望 +3 行；`test_assessment_scorer.py`/`test_e2e_resume_idempotency.py` 的 hidden reader allow-list 从“仅 scorer.py”扩为显式二元集合（理由：新增合法 scorer-side `interview_judge.py`）；`test_fixtures_cf.py` 将 PR1 judge corpus 从 teacher-visible 宽扫描中显式排除（另有 integrity suite）；`test_diagnostic_engine.py` 去掉既有 flaky 的 `created_at` 比较。均为记录在案的合理适配，未弱化教师可见断言。

## 3. 独立语义探针（/tmp 自写、只读；不提交）

探针：`/tmp/pr4_probe.py`（64 项检查，61 PASS / 3 FAIL；日志 `/tmp/pr4_probe_run.log`）。所有 DB/tmp 目录仅写在 `/tmp`，仓库保持干净。

| 任务项 | 探针内容 | 结果 |
|---|---|---|
| **(a) LearnerState 影响** | 同一 JD（`jd:rec`）、同一题（`q-ml-001`）、同一响应序列，仅 learner A 预置 3 条 canonical `CORRECT` 观测证据（mastery 0.3667 / evidence 3），learner B 无证据 | **PASS**：A 序列 `HYPOTHESIS→COMPLEXITY→EXPERIMENT_DESIGN→ONLINE_TRIAGE`（跳过 concept）；B 为固定 5 阶段；同 seed 重跑投影逐字段相同 |
| (a) 自述防火墙 | 同一答案文本追加 `passed=true, mastery=1.0, self_reported_mastery=1.0, claimed_status=CORRECT` 等字段 | **PASS**：status/score/最终 snapshot 与无自述版本完全一致；mastery 仅由 canonical `ASSESSED` 的 `PARTIAL` 证据写入 |
| **(b) 5 阶段固定** | 无证据 learner 全程正确回答 | **PASS**：`concept→hypothesis→complexity→experiment_design→online_triage`，恰好 5 个 probe，无跳级 |
| (b) 缺项目事实 | `q-eng-001`（`requires_project_facts=true`）首答无 facts | **PASS**：`NEEDS_REVIEW:PROJECT_FACTS_REQUIRED` → 下一动作 `ASK_CLARIFICATION/PROJECT_FACTS_REQUIRED`；clarity 文本无编造百分比/P99/规模（正则扫描 0 命中），并明确“不会替你编造”；补充 learner-owned facts 后继续进入 concept |
| (b) FULL 门 | `full_solution_allowed` / `request_full_solution` / `human_approved_full=True` / 全事件扫描 | **PASS**：默认 false；显式请求抛 `MAP-E11_FULL_SOLUTION_FORBIDDEN`；M1-B 无审批流程，构造 `True` 直接被拒；全流程无 `INTERVIEW_HINT_LEVEL_4` |
| (b) ladder 分离 | 对比 classic CF（无 vertical policy）与 interview | **PASS**：CF 事件仅 `HINT_LEVEL_n` 且无 `vertical` payload；interview hint 为 `INTERVIEW_HINT_LEVEL_1..3`、`cf_hint_ladder_shared=false`；命名空间不交叉 |
| **(c) JD v1→v2** | 同一 learner 先在 v1 窗口开 session 并跑 2 轮，再在 v2 窗口开新 session | **PASS**：原 session 行/事件流逐字节不变；新 session `jd_version=v2`、`jd_ref=jd:rec@v2`；原 plan 仍 `@v1` |
| (c) JD fail-closed | expired / not-yet-active / overlap-conflict / unknown | **PASS**：均 `FRESHNESS_JD_GATE_BLOCKED`，`RECHECK_JD_EXPIRED / NOT_YET_ACTIVE / CONFLICT / UNKNOWN` + `MAP-E10`；**0 event / 0 session / 0 goal** |
| (c) knowledge 门禁 | 9 场景分类（KEEP2/UPDATE2/RECHECK5）；5 个 RECHECK 逐个启动 | **PASS**：KEEP2/UPDATE2/RECHECK5；覆盖 `RECHECK_CONFLICT/EXPIRED/FUTURE_DATED/OLDER_SOURCE/UNAUTHORITATIVE_SOURCE`；全部在写入前 `FRESHNESS_KNOWLEDGE_GATE_BLOCKED`，0 event/session；eligible UPDATE 以 provenance ref 进入新 plan |
| **(d) 统一事件/Replay** | CF session → pause → 同 learner Interview session → resume CF → 跑完 interview | **PARTIAL**：单一 `history_events` 表、跨 session seq 连续、snapshot 不变、`verify_rebuild`/`rebuild_state` 一致均 **PASS**；但只有 learner snapshot replay，无 session 状态 replay；见 P1-1/P1-3 |
| (d) 版本不兼容 | engine/policy domain 不匹配；objective/domain 不匹配 | **PASS（仅已实现面）**：`VERTICAL_DOMAIN_MISMATCH` / `VERTICAL_OBJECTIVE_MISMATCH` 拒绝；设计中的 event `schema/domain/policy` 版本拒绝（MAP-E12/E13）未实现，见 P1-3 |
| **(e) hidden 隔离** | 全包路径扫描 + demo/event/result/plan 导出扫描 | **FAIL（关键）**：`demo_b4.py` 是第三个 hidden 读取者（P1-2）；`ASSESSED.item.scoring_spec_ref` 把 `scoring/q-*.json` 路径写进 teacher-visible 事件（P2-1）；rubric 期望体/参考回答原文未出现在 demo JSON 或规范导出中（除外 P1-2 的 `ASSESSMENT_PREPARED.canonical_response`） |
| **(f) B4-01** | 两 CF learner 同库跑既有 deterministic E2E | **PASS**：同一 canonical journal；action/mastery 路径不同；两 learner 均 `verify_rebuild=true`；每条 `ACTION_TAKEN` 都有 reason code+detail |
| **(f) B4-02** | 两 interview learner + JD v1/v2 + 4 维 rubric | **PASS**：A 加速 4 阶段、B 完整 5 阶段；4 维 `rubric_audit` + 64-hex spec digest；`NEEDS_REVIEW`/hint 行为符合预期；无 FULL |
| **(f) B4-03** | 上述 JD/knowledge 门禁 | **PASS**：见 (c) |

**探针 3 个 FAIL 的定性**：
1. `extra`：加速会话在 **engine/policy 重启**后下一追问变为重复 `HYPOTHESIS`（应为 `COMPLEXITY`）；已完成的加速会话重启后 `current_action` 重新产出 `ONLINE_TRIAGE`；用过期 JD 新建 policy 指向既有 session 时 `ASSESSED.vertical.jd_ref` 写成 `jd:rec@None`。
2/3. hidden reader allow-list 与 hidden path 出现于事件（对应 P1-2/P2-1）。

## 4. 测试质量审计

**真实 E2E**：B4-01 走 `demo.run_student_path`（内部 `TeachingSessionEngine` + SQLite + pause/restart + `verify_rebuild`），不是 scorer mock 端到端；B4-02 走真实 `TeachingSessionEngine.start_session/current_action/submit_response` + `SqliteRepository` + PR2 事务/PR3 幂等路径；判断结果为真实 `InterviewRubricJudge`（scorer-side）。**PASS**。

**断言可证伪性**：多数关键断言可证伪（固定 fixture id、事件数、零写入、reason code、snapshot 相等、sha256）。薄弱点：
- `test_vertical_version_and_objective_mismatch_rejected` 末尾 `assert "VERTICAL" in code or code == "VALIDATION_ERROR"` 几乎不可失败（P2-4）。
- B4-02 的 `_teacher_visible_events` 先剥离 `canonical_response/response` 再扫描，导致 hidden 参考回答被写入 canonical event 时扫描看不见（P1-2/P2-5）。
- hidden reader 守卫只匹配字面 `"scoring/"`；`demo_b4.py` 用分片路径构造读写同一 hidden 目录而不命中（P1-2/P2-4）。
- 无 interview 多轮 **pause/restart** 测试；cross-domain 测试只覆盖 CF pause→Interview→resume CF，未覆盖 Interview pause→CF→回到 Interview（P1-1）。
- B4-05（event/fixture version 拒绝）无测试（P1-3）。

**既有 774 测试**：在 `25185b1` 收集恰为 774；与 HEAD 859 节点集比较 **0 缺失**，且 HEAD 全量 859 passed → 既有测试保持通过（INDEPENDENTLY_REEXECUTED_THIS_TURN）。无测试删除/跳过。

**D12 与 ADR**：add-only 与 change-log 均核实（§2）。

## 5. 文档声明 vs 实际

| 文档声明 | 实际 | 判定 |
|---|---|---|
| “859 passed”（Owner 主张，任务转述） | 本轮实测 859 passed / 0 failed / 0 skipped | **准确** |
| `docs/M1_B_DOMAINS_IMPLEMENTATION.md` §7“717 passed / 692 既有” | 这是 PR4 中间分支（`3cd2431`）的数字；最终合并树为 774 既有 + 85 新 = **859** | 过时（P2-6） |
| “replay 重建 snapshot/session”（同文档 B4.3） | 只有 `LearningHistory.rebuild_state/verify_rebuild` 重建 **LearnerSnapshot**；无 session phase/pending/action 的 replay API 或校验 | **夸大**（P1-3） |
| “版本不兼容明确拒绝”（B4.6） | 仅 engine/policy 的 domain/objective 不匹配；MAP-E12/E13 未实现；event payload 无版本校验 | **部分**（P1-3） |
| “hidden-scoring reader allow-list 仍为 `{scorer.py, interview_judge.py}`”（§2/§8） | `demo_b4.py` 运行时读取 `rubrics/scoring/reference_answers.json`，守卫未覆盖 | **不成立**（P1-2） |
| “对话开始冻结加速计划”（§3） | 仅冻结在 policy 进程内存；重启丢失且无事件记录 | **不成立/不持久**（P1-1） |
| “状态全部来自 events”（§2） | 加速阶段计划/`_stages_by_session` 不在 events；其余 pending/score 状态确实来自事件 | 部分（P1-1） |
| “阻塞决策有复核队列/审计记录”（设计 B4-03a；实现文档承认未做持久队列） | 实现为 0 写入 fail-closed + 异常 reason；无持久 review queue，blocked 尝试不可 replay | 设计未实现（P2-2） |
| “uncalibrated 标注在 Reason.detail/policy metadata”（设计 §4.5） | `m1_teacher` 运行时代码中 `UNCALIBRATED` 出现 **0 次**；只有文档声明 | 文档承诺未落到运行时（P2-3） |
| “CF Hint Ladder LIGHT→INVARIANT→STRUCTURE→FULL”（B4.3 字面） | CF 仍为 A 线 `HINT_LEVEL_1..3`；LIGHT/INVARIANT/STRUCTURE 命名只用于 interview support ladder；CF 无 `requested=4` 入口 | 行为等价但命名/统一 port 未实现（P2-7） |
| “8 轮上限”（§3） | 实际由 `1+len(stages)` 个 advancing 回答结束（通常 6 轮；clarify/hint 不推进）；无独立 8 轮计数器 | 表述不精确（P2-6） |

## 6. B4-01/02/03 独立证据状态

| case | 状态 | 独立证据 | 限制 |
|---|---|---|---|
| **B4-01** 统一 CF 闭环 | **VERIFIED**（E2E-MOCK + DETERMINISTIC） | 探针 (f)：同一 SQLite、两 learner、同一 canonical mastery/journal；action/mastery 路径不同；`verify_rebuild` 双通过；每条 CF 动作有 reason code+detail；全量套件 9 项 B4 E2E 通过 | 合成学生；非真实学习效果 |
| **B4-02** Interview 闭环 | **VERIFIED**（E2E-MOCK，会话内） | 探针 (a)(b)(f)：5 阶段固定顺序、LearnerState 加速（同题同 JD 隔离验证）、`ASK_CLARIFICATION` 不编造、4 维 rubric + digest、JD v1/v2 新 session 隔离、无 FULL；`test_b4_02`/`test_vertical_policy` 16+9 通过 | 重启后阶段漂移（P1-1）；E2E 以 hidden 参考回答作为 learner 输入（P2-5） |
| **B4-03** Freshness 门禁 | **VERIFIED**（E2E-MOCK） | 探针 (c)：KEEP2/UPDATE2/RECHECK5；5 个 RECHECK（conflict/expired/future/older/unauthoritative）与 4 类 JD 门（expired/not-yet-active/conflict/unknown）全部写入前拒绝，0 event/0 session/0 goal，显式 MAP-E code；eligible UPDATE 进新 plan | 无持久复核队列/审计事件（P2-2）；无真实抓取/时效调度 |

> 附：设计矩阵 B4-04 只部分覆盖（CF→Interview→CF；interview 重启不成立）；B4-05 **NOT_RUN**（无 MAP-E12/E13 实现）。

## 7. Findings

### P1-1（功能性/持久性）Interview 多轮阶段计划只存在 policy 内存，重启后漂移且可能重开已完成会话
- 证据：`m1_teacher/session/vertical.py:317`（`_stages_by_session` 进程内 dict）、`:404-405`（仅 `validate_session_start` 时写入）、`:575-586`（重启后 `_stages` 回退为完整 5 阶段）；`m1_teacher/session/engine.py:524-546`（既有 session 直接 return，不重新走 `validate_session_start`）。
- 实测：同库/同 learner 的加速会话（主问题 + hypothesis 后重启）下一动作仍为 `INTERVIEW_PROBE_HYPOTHESIS`（期望 `COMPLEXITY`）；已完成的加速会话重启后 `current_action` 重新发出 `ONLINE_TRIAGE`；过期 JD 重建 policy 后 `ASSESSED.vertical.jd_ref = jd:rec@None`。`jd_ref@None` 同时意味着“过期 JD 写入前 fail-closed”只在**新 session** 成立。
- 影响：B4.2“多轮 5 阶段”在会话内正确，但“Replay/跨域不中断/状态全部来自 events”的持久性主张不成立；会破坏可审计性与确定性恢复。
- 必须动作：把阶段计划/加速决策持久化到 `SESSION_STARTED.payload.vertical`（或从事件确定性重算），恢复时以事件为准；`start_session` 对既有 session 校验/恢复 vertical 元数据；增加“加速/pause/新 engine + 同 DB 恢复/完成后再 `current_action`”回归测试；恢复时不得写 `@None`。

### P1-2（hidden 边界/声明）hidden reader 不是恰好两个模块；`demo_b4.py` 读取 scoring 目录且守卫可绕过
- 证据：`m1_teacher/demo_b4.py:85-95` 读取 `vertical/interview/rubrics/scoring/reference_answers.json`，并在 `:294`、`:323-333` 直接作为 learner responses；`tests/m1_teacher/test_assessment_scorer.py:493-507`、`test_e2e_resume_idempotency.py:506-517`、`test_b4_e2e.py:685-690` 仅以字面 `"scoring/"` 扫描，`demo_b4.py` 用路径分片规避。
- 后果：这些 hidden 参考回答文本被作为 `ASSESSMENT_PREPARED.canonical_response` 持久化进 canonical event log（探针在 demo DB 中确认 11 条）；`test_b4_e2e.py:64/76-85` 在“teacher-visible”投影中先剥掉 `canonical_response/response`，因此泄漏扫描看不到它。
- 影响：Owner 声称 “hidden allow-list 恰好 `{scorer.py, interview_judge.py}`” 不成立；hidden 材料被非 scorer-side 的 CLI/demo 模块读取。当前为 synthetic 且 demo JSON 不外泄原文，故不是真实数据泄漏，但属于明确的边界/证据诚信缺陷。
- 必须动作：把 `reference_answers.json` 移出运行时 hidden scoring 目录（test-only fixture）或将其显式纳入 allow-list 并说明；“无第三模块读取 scoring/”的守卫改为路径组件/AST/运行时文件打开监控（不能只匹配字面串）；重跑 hidden 泄漏扫描时不得剥离 `canonical_response`，或明确声明该字段为 learner-owned 且 demo 输入不得来自 hidden。

### P1-3（声明/覆盖）“统一 Replay（snapshot+session）”与“版本不兼容明确拒绝”未实现
- 证据：`m1_teacher/learner/history.py:515-547` 仅重建 `LearnerSnapshot`；全仓无 `rebuild_session`/`replay_session`。设计 `docs/M1_B_INTERVIEW_FRESHNESS_MAPPING.md:307-308,683-685` 的 `MAP-E12/MAP-E13` 在 `m1_teacher` 中 **0 命中**；replay 不校验 event `schema_version/domain_version/policy_version`。
- 实测：`verify_rebuild`/`rebuild_state` 在 CF/Interview/跨域后均通过（这部分真实）；但 session 的 phase/pending/action 轨迹只能由测试手工重放，不是产品 API；event payload 中伪造的版本字段不会被拒绝（无消费点）。
- 必须动作：要么实现并测试 session replay 与版本校验（MAP-E12/E13），要么把文档/B4.6 宣称降级为“snapshot-only replay + domain/objective policy 拒绝”。不得把“只有 snapshot replay”写成“snapshot/session replay”。

### P2-1（hidden 引用）teacher-visible `ASSESSED.item.scoring_spec_ref` 暴露 hidden 路径
- `m1_teacher/learner/history.py:377` 的 `ASSESSED.payload.item` 含 `scoring/q-*.json`（探针在 demo DB 中确认每域题均出现）；设计 §3.2 要求 opaque ref（如 `scorer://...`）。
- 非内容泄漏（仅路径/题目 id），但违反“teacher-visible 不含 hidden 目录/引用”的设计意图，且现有测试只查 `"rubrics/"` 不查 `"scoring/"`。
- 动作：改用不透明的 `scorer://` 引用或在导出层剥离；测试补 `scoring/` 检查。

### P2-2（审计）Freshness 阻塞决策无持久复核队列/审计事件
- 实现为“写入前 fail-closed + 异常 reason”，被拒尝试 **0 event**；无 `knowledge_review_queue`/决策事件，无法 replay 该次拒绝。设计 B4-03a 要求“复核队列有记录”，实现文档 §6.5 自认未做。
- 动作：至少写独立 audit 事件（不进教学事件流）或在交付范围中显式标注为 NOT_IMPLEMENTED。

### P2-3（uncalibrated 落地）运行时未标 `UNCALIBRATED_HEURISTIC`
- `m1_teacher` 全包 `grep -i uncalibrated` = 0；`Reason.detail`/policy payload 只有普通文本与 `policy_version`。文档说会标，但运行时没有。
- 动作：在 policy metadata/Reason detail 注入 `UNCALIBRATED_HEURISTIC`（或在报告与验收中明确“仅文档标注”）。

### P2-4（测试质量）弱断言与守卫盲区
- `tests/m1_teacher/test_b4_e2e.py:616` 的 `"VERTICAL" in code or code == "VALIDATION_ERROR"` 基本不可证伪；应精确断言 `VERTICAL_OBJECTIVE_MISMATCH`。
- hidden reader 守卫是字面串扫描（P1-2），非路径/AST/运行时。
- B4-05 无测试；B4-04 只测 CF 方向。
- 动作：收紧断言、补 interview restart/pause 与 MAP-E12/E13 负例。

### P2-5（证据局限）B4-02 E2E/demo 以 hidden 参考回答作为 learner 输入
- 这使“learner 回答→4 维评分”的高分路径带有答案键循环性；虽然只用于 MOCK 机制证明，但不能作为评分真实性的证据。泄漏扫描又剥离 `canonical_response`，掩盖了 hidden 文本进入事件。
- 动作：改用独立的 synthetic learner responses（非答案键）做 E2E；另设 scorer-only 测试使用参考回答。

### P2-6（文档一致性）中间分支数字与“8 轮”表述过时
- `docs/M1_B_DOMAINS_IMPLEMENTATION.md` §7 的 692/717 是 `3cd2431` 中间分支；最终树为 774+85=859。§3“8 轮上限”实际是 `1+len(stages)` 个推进回答。
- 动作：文档标注最终合并树数字与真实终止规则；不要把中间分支证据当最终证据。

### P2-7（B4.3 字面覆盖）CF ladder 命名/统一 TeacherPolicyPort 未实现
- CF 路径仍是 `HINT_LEVEL_1..3`（`engine._hint_selection` + 既有 `test_session_transitions`）；LIGHT→INVARIANT→STRUCTURE 只用于 interview support ladder；CF 无 `requested=4`/`MAP-E11` 入口（结构上无法发出 FULL，算 fail-closed，但不是 B4.3 字面要求的“显式请求被拒”）。
- 动作：要么在文档中明确“CF 沿用 A 线 ladder，B 命名仅 interview”，要么实现统一 policy port 与 CF 的 L4 拒绝测试。

## 8. 必须动作（合并前/后续 PR）

1. **P1-1**：持久化/恢复 interview 阶段计划；修 `jd_ref@None`；补重启回归。复验：加速会话在全新 engine+policy 上继续得到 `COMPLEXITY→...`，完成后 `current_action` 不再产 probe。
2. **P1-2**：移走/隔离 `reference_answers.json` 或显式允许并披露；守卫可证明“无第三模块读取 scoring/”；泄漏扫描不剥离 `canonical_response`（或声明其数据来源）。
3. **P1-3**：实现 session replay + event/policy 版本拒绝，或降级文档/验收声明；B4-05 补测。
4. P2-1..P2-7 可随 PR4 后续或 PR5 处理；其中 P2-1/P2-5 建议与 P1-2 同批修。

**复验最低集合**：`pytest tests/m1_teacher -q`；`test_b4_e2e.py`/`test_vertical_policy.py`；新增 restart/durability、hidden-reader、MAP-E12/13 负例；`demo_b4` 双跑 sha256；ruff。

## 9. 限制与不可声称项

- 本报告仅覆盖 **B-PR4 / 合并树 `11a4f72` / 离线合成**；不覆盖 B-PR5 独立评测、真实判题 OS 边界（见 PR1 报告）、真实崩溃矩阵（见 PR2）、真实多租户鉴权。
- **真实学习效果 NOT_VERIFIED**；所有 mastery/路径/分数为确定性启发式 + 合成输入；阈值 **UNCALIBRATED**。
- **无真实网络/招聘网站/个人简历/JD/Provider/API Key/LiveGate/付费请求**；freshness 为静态 synthetic 时间戳，无真实抓取/调度。
- 隐藏题集（B 线 `hidden/`）未转换为 vertical hidden 评测集；本轮 hidden 评测使用公开题库 + scorer-only specs/参考回答（见 P2-5）。
- 无 UI/人工审批；`FULL_SOLUTION` 在 M1-B 结构上不可达（比“默认禁止”更严格）。
- 探针不提交；其日志/DB 仅在 `/tmp`，不作为仓库证据。

## 10. 证据索引

| 项 | 路径/值 |
|---|---|
| 全量测试日志 | `/tmp/pr4_full_run1.log`（859 passed in 81.59s） |
| 定向测试日志 | `/tmp/pr4_targeted.log`（25 passed in 5.58s） |
| ruff 日志 | `/tmp/pr4_ruff.log`（All checks passed） |
| demo 输出 | `/tmp/pr4_demo_run1.json`、`/tmp/pr4_demo_run2.json`；sha256 `6b7bb66e36a38bd640d5b47d206d8fee24a446df9b42dbe76d20dd8cc50bef83` |
| 独立探针（不提交） | `/tmp/pr4_probe.py`；日志 `/tmp/pr4_probe_run.log`（64 checks；61 PASS / 3 FAIL） |
| 基线节点集 | `/tmp/base_nodes.txt`（774） vs `/tmp/head_nodes.txt`（859）；缺失 0 / 新增 85 |
| HEAD | `11a4f7217735d6fc4a0799acdd1371cf25b4358c` |
| 基线 | `4706250643fd42d48d69ddad7159e011955fa9fd` |

---

*本报告只对 B-PR4 的离线/合成/确定性范围作独立验收；P0=0、P1=3、P2=7。除明确标注 `INDEPENDENTLY_REEXECUTED_THIS_TURN` 的项目外，其余为静态源码/文档审阅或 `OWNER_REPORTED`。真实教学效果、真实网络/简历/JD/Provider/Live 均不在本报告结论内。*
