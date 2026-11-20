# M1-B B-PR4 独立评审 P1/P2 处置与关闭证据

- **响应对象**：`docs/M1_B_PR4_REVIEW.md`（独立评审，HEAD `11a4f72`，`PASS_WITH_ACTIONS`，P0=0 / P1=3 / P2=7）。
- **响应分支 / 工作区**：`/root/m1b/pr4int`，`b-next/pr4-domain-ports`；先 fast-forward 合入评审文档（`dfda203`），再提交 P1/P2 修复。
- **范围限定**：仍为 PR4 离线、合成、确定性范围；不改变“真实教学效果 NOT_VERIFIED、无真实网络/简历/JD/Provider/LiveGate”的结论。
- **证据等级**：本文所有数字为 Owner 侧本轮真实复跑（`E2E-MOCK + DETERMINISTIC`）；独立 Reviewer 复跑仍需其自行执行，本文不代替独立验收。

## 1. P1 关闭摘要

| P1 | 结论 | 实现 | 关闭证据（本轮真实运行） |
|---|---|---|---|
| **P1-1** 阶段计划仅存在 policy 内存 | **CLOSED** | `SESSION_STARTED.payload.vertical` 持久化 `plan{stages,accelerated,objective_id,policy_version,thresholds,calibration_status}` 与 `jd_snapshot{jd_id,version,content_digest,valid_from,valid_until}`；`PLAN_CREATED` 同步携带；`InterviewVerticalPolicy.restore_session()` 从事件重建/校验计划；`TeachingSessionEngine._ensure_vertical_plan()` 在 `start_session(existing)/resume/current_action/submit/advance` 前恢复；缺失/损坏 → `VERTICAL_PLAN_SNAPSHOT_MISSING` / `VERTICAL_PLAN_SNAPSHOT_CORRUPT` / `VERTICAL_JD_SNAPSHOT_UNAVAILABLE`（不再写 `jd_ref=jd:rec@None`） | `tests/m1_teacher/test_b4_durability_replay.py::test_accelerated_plan_survives_restart_after_complexity`（新 engine/policy 同库重启 → `COMPLEXITY`，非 `HYPOTHESIS`）；`::test_completed_accelerated_session_restart_does_not_reopen_online_triage`（重启后无 `ONLINE_TRIAGE` 重开，仅 1 次 probe）；`::test_interview_pause_resume_restores_persisted_stage_plan`；`::test_expired_jd_restart_uses_session_snapshot_and_never_writes_none_ref`（过期 JD 重建 policy 仍 `jd:rec@v1`，全事件无 `@None`）；`::test_missing_or_corrupt_plan_snapshot_fails_closed` |
| **P1-2** hidden reader allow-list 不成立 | **CLOSED** | 新增 **teacher-visible** `fixtures/m1_teacher/vertical/interview/learner_scripts/answers.json`（synthetic MOCK learner answers，独立于 hidden rubric/reference）；`demo_b4.py` / B4 E2E / vertical-policy tests **只**读取该脚本；hidden rubrics/reference 仍只由 `assessment/scorer.py`、`assessment/interview_judge.py` 读取；`tests/m1_teacher/guard_support.py` 用 **AST/路径组件**检测 `**/scoring/**` 构造/引用（不再只匹配字面 `"scoring/"`），allow-list 仍恰好 `{scorer.py, interview_judge.py}`；泄漏扫描不再剥离 `canonical_response`，改为断言其逐值来自 learner script，并扫描全事件流无 hidden 路径/字段 | `test_b4_e2e.py::test_b4_modules_are_offline_and_hidden_readers_are_closed`（AST 守卫 + demo/E2E 零 hidden 引用）；`test_b4_02...`（全事件流无 `scoring/`、`reference_answers`、hidden 字段；`canonical_response` 逐值 ∈ learner script；`item.scoring_spec_ref` 为 opaque `rubric/*.json`）；`test_vertical_policy.py::test_rubric_audit_in_assessment_events_without_hidden_leak`（同样 no-strip 扫描）；`test_assessment_scorer.py` / `test_e2e_resume_idempotency.py` 的 allow-list 守卫升级为 AST/path 版本 |
| **P1-3** Replay/版本拒绝过度声明 | **CLOSED（实现面；event schema_version 行 PARTIAL）** | 新增 `TeachingSessionEngine.replay_session_state(session_id)` 与 `verify_session_replay(session_id)`：从统一事件重建 phase/turn_index/pending_item_id/last action/plan（含 persisted vertical plan 的 `advanced_answers`/`next_stage`/`ladder_completed`）/completion，并返回差异；为内容动作 acknowledgement 新增 D12 add-only 事件 `TURN_ADVANCED`（带 `next_state`），ASSESSED/ERROR/ACTION_TAKEN/PAUSED/RESUMED 也记录 `next_state`（均为 payload add-only）。`MAP-E12_DOMAIN_VERSION_MISMATCH`（domain_id/domain_version/objective 绑定）与 `MAP-E13_EVENT_VERSION_INCOMPATIBLE`（session policy / vertical policy / plan policy 版本）在 continue/resume/replay 前 fail-closed；零写入 | `test_b4_durability_replay.py::test_replay_session_state_rebuilds_cf_and_interview_sessions`（CF 真实 demo 路径 + `TURN_ADVANCED`）；`::test_replay_cross_domain_sessions_have_consistent_state`（CF pause → Interview → resume，两 session `verify=match`）；`::test_verify_session_replay_detects_tampered_persisted_state`（可证伪：篡改持久 session → `match=false` 精确差异）；`::test_version_incompatibility_rejected_with_zero_writes`（MAP-E13 session policy / MAP-E13 vertical policy / MAP-E12 domain_version 三种，均事件数/session/goal 零变化） |
| **P1-3 降级声明** | 设计表 `MAP-E13` 的 “event `schema_version`/fixture 版本未知 → 拒绝 replay” 一行 | **PARTIAL / 未完整实现**：M1-B 的 `HistoryEvent` payload 没有独立 `schema_version` 字段（repository schema 由 PR3 迁移负责），本轮未新增该字段/迁移；当前 MAP-E13 覆盖 session-policy / vertical-policy / plan-policy 版本，event-level schema 版本拒绝 **NOT_IMPLEMENTED**。README/实现文档已明确降级，不再声称“所有事件版本不兼容均拒绝”。 |

## 2. P2 处置

| P2 | 处置 | 说明 / 证据 |
|---|---|---|
| **P2-1** teacher-visible `ASSESSED.item.scoring_spec_ref` 暴露 hidden 路径 | **FIXED** | interview `questions.json` 的 ref 改为 opaque `rubric/q-*.json`；judge 内部解析 opaque → 隐藏目录（legacy 相对 ref 仍可读以兼容旧测试）。B4 测试断言 `ref.startswith("rubric/")` 且全事件流无 hidden 路径标记。 |
| **P2-2** Freshness 阻塞决策无持久复核队列/审计事件 | **NOT_IMPLEMENTED（已显式披露）** | 仍为“写入前 fail-closed + 显式 `FRESHNESS_*_GATE_BLOCKED` reason/map_code”，被拒尝试 0 事件；不写教学状态。本 PR4 不加 schema 迁移/队列，留待 PR5；实现文档 B4-03 状态与限制中明确标注，不声称有持久 review queue。 |
| **P2-3** 运行时无 `UNCALIBRATED` 标注 | **FIXED** | 运行时新增 `CALIBRATION_STATUS="UNCALIBRATED_HEURISTIC"`：session/plan/action payload 携带 `calibration_status`、`thresholds`；所有 `Reason.detail` 追加 `calibration=UNCALIBRATED_HEURISTIC`。测试 `test_vertical_policy.py::test_runtime_calibration_markers_and_thresholds`。 |
| **P2-4** 弱断言与守卫盲区 | **FIXED（可修部分）** | `test_vertical_version_and_objective_mismatch_rejected` 改为精确断言 `VERTICAL_OBJECTIVE_MISMATCH` 且零事件/零 session；hidden 守卫升级 AST/path；新增 interview restart/pause、MAP-E12/E13 负例、replay 篡改可证伪断言。B4-04（interview 方向跨域）与 B4-05（版本拒绝）现均有测试（见 P1-1/P1-3）。 |
| **P2-5** B4-02 E2E/demo 以 hidden 参考回答作为 learner 输入 | **FIXED** | demo/E2E 改用 `learner_scripts/answers.json`；hidden reference answers 只保留在原有 scorer-side judge tests（`test_interview_judge.py` 等）中用于 judge 单测，不再作为 learner 输入；泄漏扫描不剥离 `canonical_response` 并逐值比对 learner script。 |
| **P2-6** 中间分支数字与 “8 轮” 表述过时 | **FIXED** | `docs/M1_B_DOMAINS_IMPLEMENTATION.md` 更新为最终合并树实测数字；终止规则改为准确表述：主问题 + `len(stages)` 个推进回答（通常 5/6 轮）后完成，`INCORRECT`/`NEEDS_REVIEW`/clarify/hint 不推进，无独立 “8 轮计数器”。 |
| **P2-7** CF ladder 命名/统一 port 未实现 | **文档化接受（PARTIAL）** | CF 仍为 A 线 `HINT_L1..L3`；`LIGHT/INVARIANT/STRUCTURE` 仅用于 interview support ladder；CF 结构上无 `requested=4`/FULL 入口（fail-closed，不是显式拒绝）。实现文档明确说明“B4.3 的 LIGHT→FULL 统一命名未在 CF 上落地”，不声称统一 TeacherPolicyPort。 |

## 3. 本轮真实运行证据

环境：`/root/Autonomous Teacher/.venv/bin/python`（Python 3.11.15 / pytest 9.2.0）；工作区 `cd /root/m1b/pr4int`。

```text
pytest tests/m1_teacher -q
913 passed in 88.37s

pytest tests/m1_teacher/test_b4_durability_replay.py -q
9 passed

pytest tests/m1_teacher/test_b4_e2e.py tests/m1_teacher/test_vertical_policy.py -q
26 passed

ruff check m1_teacher tests/m1_teacher
All checks passed!

python -m m1_teacher.demo_b4 --json  (×2, cmp)
identical; sha256 b3231658a4ac12a49cd2ac57f4a3e8d9719fbf7476ca36a54e4d8f9eea72d905
```

demo 摘要（真实输出）：B4-01 `paths_differ=true`；B4-02 `learner_input_source=teacher-visible learner_scripts/answers.json`、`learner_script_sha256=bd81292ad08357ff…`、`jd_versions=[v2,v1]`、`paths_differ=true`、`full_solution_emitted=false`、A 跳过 concept / B 完整 5 阶段 + clarify 1 + hint L1；B4-03 `decision_counts={KEEP:2,UPDATE:2,RECHECK:5}`、`silent_imports=0`。

兼容性：`python -m m1_teacher.demo --json` / 默认文本输出与合并前逐字节一致（sha256 `0ac438a33c964fdc47014b71bf93870066b56d17d2e8316df940a8f143bd4da3`）；`demo.py` 仅将 additive `TURN_ADVANCED` 从历史 `event_count` 投影排除，未改变默认输出/哈希语义。

## 4. 测试计数构成

| 来源 | 数量 |
|---|---|
| 更新后 PR3 final 基线（PR1/PR2/PR3 review-fix tree） | 818 |
| vertical 层（interview domain/fixtures/judge/freshness） | 60 |
| B4 E2E + vertical policy（本轮之前） | 25 |
| B4 durability/replay/version 新测试 | 9 |
| P2-3 calibration 运行时测试 | 1 |
| **合计** | **913** |

（818+60+25+9+1=913，与合并更新 PR3 后的全量实测一致。）

> **Post-merge 补充（PR3 final 合入后）**：真实 pre-PR3 v1 fixture 的 `SESSION_STARTED` payload 没有 `domain_id/domain_version`（来自 base `4706250`），初版 MAP-E12 检查把缺字段误判为 mismatch，导致 `test_scope_migration.py::test_real_pre_pr3_structured_legacy_replays_with_old_projection` 回归。已改为 **legacy v0 双缺失放行**（仅比较“记录存在”的 domain/policy 字段，legacy 标记只进 replay 输出不写库）；显式 mismatch 的 MAP-E12/E13 测试保留。合入后全量 **913 passed**（`M1B_REQUIRE_OS_SANDBOX=1`，0 skipped），`test_scope_migration` 15 passed。

## 5. 仍未关闭 / 不可声称项

- **Independent Reviewer re-run**：本轮修复仍需独立 Reviewer 复跑确认；本文仅为 Owner 侧证据。
- **P2-2**：持久复核队列/审计事件 NOT_IMPLEMENTED（已披露）。
- **P1-3 event schema_version 行**：PARTIAL（见 §1）。
- **P2-7**：CF 统一 ladder port 未实现（文档化接受）。
- **真实学习效果 / 真实网络 / 简历 / JD / Provider / LiveGate**：NOT_VERIFIED / NOT_RUN；阈值仍 **UNCALIBRATED_HEURISTIC**（现在运行时可见）。
- **隐藏题集（B 线 hidden/）**：仍未转换为 vertical hidden 评测集；本轮使用公开题库 + scorer-side hidden spec/reference 单测。
- **B4-03 持久审计**：无 review queue（同上）。
