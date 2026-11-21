# M1-B 最终实现报告（B-NEXT / B-PR0…B-PR5）

| 字段 | 值 |
|---|---|
| 文档状态 | **`OWNER_REPORTED`（实现汇总 + Owner 侧证据；不是最终独立验收，不是无条件 PASS）** |
| 文档版本 | `m1b.impl-report.v3`（2026-11-21 UTC；addendum2 后最终一致性补丁） |
| 工作区 / 分支 | `/root/m1b/pr5wrap` / `b-next/pr5-wrap`；**基线 = PR5 `d43b02c`**（含首轮评审 `5d5ebf8`、delta `a09e56e`、addendum2 `d43b02c` 与 P1-1/P1-2 修复、939 测试树）；代码/测试树仍为 `d9201e9`。最终 push SHA 由 Lead 记录（`PENDING_LEAD_MERGE`） |
| 被汇总范围 | B-PR0 合同收敛 → B-PR1 可信判题 → B-PR2 事务/恢复 → B-PR3 scoped 幂等 → B-PR4 双域 ports → B-PR5 统一 E2E/证据 |
| 最终数字归属 | **最终树实测（本报告标注 FINAL_TREE_MEASURED）：939 passed（私有 TMPDIR）、strict `M1B_REQUIRE_OS_SANDBOX=1 -rs` 939 passed / 0 skipped；clean archive（无 `.git`）full/strict 939 passed / 0 skipped。最终 SHA/证据哈希/独立评审状态以 `docs/M1_B_EVALUATION_REPORT.md` §13/§14 与 `docs/M1_B_FINAL_INDEPENDENT_REVIEW.md` 为准** |
| 证据词汇 | 按评估协议 §1 冻结词汇。本文件只使用 `OWNER_REPORTED`（本线实现/本报告作者本轮实测，未经独立 Reviewer 复跑）、`REVIEWER_REPORTED`（引用评审报告原文）、`HISTORICAL_FROZEN`（历史冻结参考）、`NOT_RUN`、`BLOCKED`、`NOT_VERIFIED`、`UNVERIFIED`；**不使用 `INDEPENDENTLY_REEXECUTED`**（该标签只能由独立 Reviewer 本轮真实复跑获得） |
| 边界 | 仅离线、合成 fixtures、确定性/mock E2E；**不包含**真人学习收益、真实招聘/JD/简历、联网研究、真实 Provider/LLM、LiveGate、生产可用性；M0 保护路径零变更 |

> **核心声明**：最终独立评审链已闭合——首轮 `5d5ebf8` **`PASS_WITH_ACTIONS`**（P0=0/P1=3/P2=6）→ delta `a09e56e` P1-1/P1-2 `CLOSED`、P1-3 errata → addendum2 `d43b02c` **`P1_ACTIONS_CLOSED`（仅余 P2 文档项）**；**总体裁定建议 `PASS_FOR_M1B_OFFLINE_INTEGRATION_SCOPE`（仅限离线合成集成范围）**，最终标签/签收由 Lead/维护者记录。仍不是真实效果/Provider/Live/生产或人类 Gate 的无条件 PASS。
> 不得把本文数字写成最终 PASS，不得把历史 `536 + 365` 相加（不存在“统一 901”）；`NOT_RUN/BLOCKED/UNVERIFIED/NOT_VERIFIED` 一律保留原状态。

---

## 0. 结论摘要（最终树 `FINAL_TREE_MEASURED`，基线 `d9201e9`）

| 项 | 最终值 | 标签 |
|---|---|---|
| 最终候选树（代码/测试） | **最终 push SHA = `PENDING_LEAD_MERGE`（由 Lead 记录；本 docs-only 提交后统一 push）**；代码/测试基线 = `d9201e9`（+ PR5 文档 merge `db5ce03`/`d43b02c` 评审链）；此前 merge `861d147…`（PR4 final `1de6ae6…`）、行为代码 SHA `12f6290…` | — |
| 测试收集数 | **939 collected** | `OWNER_REPORTED`（本轮 `--collect-only`） |
| 测试构成 | **939 = PR4 final 913 + PR5 26（B5 11 + collector 15）**；文件级归组 = 536 基线 + PR1 173 + PR2 63 + PR3 46 + PR4 95 + PR5 26；历史 M1-A 536 只作基线参考，final tree 中 5 个 M1-A 测试文件随 D12/去 flake 更新过，不能称“536 原样未改” | `OWNER_REPORTED`（本轮 collect-only 归组） |
| 全量套件（私有 `TMPDIR`） | **`939 passed in 103.57s`，exit 0，0 skipped** | `OWNER_REPORTED`（本轮实测） |
| 全量套件（strict `M1B_REQUIRE_OS_SANDBOX=1 -q -rs`） | **`939 passed in 102.72s`，0 skipped** | `OWNER_REPORTED`（本轮实测） |
| clean archive（`git archive HEAD`，无 `.git`） | full **`939 passed in 115.42s`**；strict **`939 passed in 116.50s`，0 skipped**（P1-1 修复后；旧 937+1 为修复前历史） | `OWNER_REPORTED`（本轮实测） |
| A demo 双跑 | 逐字节相同；`sha256=b08ceee915fb0363864e303ded71de4d547eae6d14f7aa693ba1537a810d491b`；53 行 / 5,798 bytes | `OWNER_REPORTED`（本轮实测；与历史一致） |
| B4 demo（`--json`）双跑 | 逐字节相同；**`sha256=b3231658a4ac12a49cd2ac57f4a3e8d9719fbf7476ca36a54e4d8f9eea72d905`；513 行 / 15,340 bytes**（旧树哈希/尺寸为 PR4-fix 前历史值，不用于 final） | `OWNER_REPORTED`（本轮实测；与 Evaluation Report §9 一致） |
| B5 E2E demo 双跑 | 逐字节相同；`sha256=4d0e0c851f4ff4d745127932aa62fcfabeca47da2f7d23ae434cae1ab300a2fc`；27 行 / 4,168 bytes | `OWNER_REPORTED`（本轮实测） |
| `ruff check m1_teacher tests/m1_teacher` | `All checks passed!` | `OWNER_REPORTED`（本轮实测） |
| X-01（范围） | **最终代码/测试树相对 `main`：302 files，302 A / 0 M / 0 D；相对 M1-A `4706250`：243 files；保护前缀 0 命中**。口径（P2-7）：302/243 = 不含评审 addendum 的最终代码/测试树（`d9201e9`/`db5ce03`）；addendum2 复核 HEAD `1eb40a9` = 303/244；本 wrap 分支提交 addendum2 文件后 `main...HEAD` = 304/245（+1 为 addendum2 自身），最终 push 以 Lead 记录为准 | `OWNER_REPORTED`（本轮 `git diff`） |
| 证据包最终哈希 | `audit-index.jsonl` `a11ce429…`（38 条）、`audit-index.json` `8db87530…`、B5 `e2e_b5_summary.json` `a07cfe7e…`；cf/interview/cross/freshness 四文件不变（见 §6.4） | `OWNER_REPORTED`（本轮 `sha256sum`） |
| 最终独立评审 | **评审链已闭合**：`5d5ebf8` `PASS_WITH_ACTIONS`（P0=0/P1=3/P2=6）→ `a09e56e` P1-1/P1-2 `CLOSED`、P1-3 errata → **`d43b02c` addendum2 `P1_ACTIONS_CLOSED`（P1-3 5/5 CLOSED，仅余 P2 文档项）**；B5-01 建议 `PASS_WITH_ACTIONS`，总体建议 `PASS_FOR_M1B_OFFLINE_INTEGRATION_SCOPE`（仅离线合成范围） | `REVIEWER_REPORTED`（`docs/M1_B_FINAL_INDEPENDENT_REVIEW_ADDENDUM_2.md`）+ Owner 修复证据 |
| 最终裁定 | **建议总体 `PASS_FOR_M1B_OFFLINE_INTEGRATION_SCOPE`（仅限离线合成集成范围）**；B5-01 建议 `PASS_WITH_ACTIONS`（仅余 P2 文档项）；最终标签/签收由 Lead/维护者记录。**不是真实效果/Provider/Live/生产/人类 Gate 的无条件 PASS** | `REVIEWER_REPORTED` + Owner 证据 |

**必须如实保留的负面事实（final tree）**

1. 最终独立评审链 **`P1_ACTIONS_CLOSED`**（addendum2 `d43b02c`；P1-1/P1-2 承 `a09e56e`，P1-3 5/5 CLOSED）；**仅余 P2 文档项**，总体建议 `PASS_FOR_M1B_OFFLINE_INTEGRATION_SCOPE`（仅离线合成范围），但最终标签/签收仍由 Lead/维护者记录；不构成真实效果/Provider/Live/生产 PASS。
2. 真实学习效果 **`NOT_VERIFIED`**；真实 Provider/网络/LiveGate **`BLOCKED`**；目标部署（非 root、断电、真实 CODE）**`NOT_RUN`/`UNVERIFIED`**。
3. clean archive 在 P1-1 修复后 **939 passed / 0 skipped**；修复前 `937 passed, 1 failed` 是历史（失败测试要求无 `.git` 时 `git_sha` 为 40-hex，与证据包契约冲突）。
4. 两条历史线（M1-A 536 / M1-Offline 365）是**各自独立冻结**的参考，不是本套件的组成；final tree 的 536 是基线计数，5 个 M1-A 测试文件已按 D12/去 flake 更新，不能写成“原样未改”。

---

## 1. 合同收敛裁决摘要

### 1.1 唯一 canonical 与 vertical 边界（B-PR0 产出）

| 角色 | 裁决 | 落点 |
|---|---|---|
| Canonical TeacherCore（状态/事件协议/mastery 唯一写入者/Replay） | **A 线 `m1_teacher`（`m1a.v0`，SQLite + Session Engine）** | `docs/M1_B_CONVERGENCE_ADR.md` |
| Vertical 能力（CF Hint / Interview / Freshness） | **B 线 `m1_offline` 作为插件，经四端口接入，只读 canonical** | `docs/M1_B_PORTS.md`、`docs/M1_B_INTERVIEW_FRESHNESS_MAPPING.md` |
| 端口 1：`DomainAdapterV1` | 知识/内容只读加载（B `SkillNode`→A `KnowledgeNode` 显式映射） | `m1_teacher/domains/`（PR4：`interview.py` 等） |
| 端口 2：`AssessmentPort` | trusted scorer 边界；CODE 默认 blocked；expected/verdict 只在 T1 | `m1_teacher/assessment/`（PR1） |
| 端口 3：`KnowledgeSourcePort` | Freshness 决策/信任 registry；不直接写课程/学习者状态 | `m1_teacher/knowledge/freshness.py` + `m1_teacher/session/vertical.py`（PR4） |
| 端口 4：`TeacherPolicyPort` | Hint/追问策略；FULL_SOLUTION 不可达；5 阶段 interview 动作 | `m1_teacher/session/vertical.py`（PR4） |
| 禁止项 | 双写 LearnerState、自动迁移真实 learner DB、给冻结记录加字段、B vertical 直接写 mastery/snapshot | ADR §7/§8、PORTS §4 |

### 1.2 D12 add-only 合同变更（已落 ADR change log）

`docs/M1_ADR_001_DOMAIN_CONTRACTS.md` §6b 为 append-only 变更日志；同时记录在 `docs/M1_ARCHITECTURE.md` §12。**只追加、不重命名/删除任何既有值**：

| 变更 | PR | 枚举/合同 | 兼容性 | 位置 |
|---|---|---|---|---|
| `HISTORY_EVENT_TYPE += ASSESSMENT_PREPARED` | B-PR2 | `m1a.v0` 事件枚举（冻结） | 旧 payload 不受影响；旧构建读新事件 fail-closed（forward-only） | ADR §6 item 9 + §6b；ARCHITECTURE §12 |
| `TEACHING_ACTION_KIND += SOCRATIC_QUESTION` | B-PR4 | `m1a.v0` 教学动作枚举 | 仅 vertical interview 使用；CF/A 路径不发出 | ADR §6b |
| `TEACHING_ACTION_KIND += ASK_CLARIFICATION` | B-PR4 | 同上 | 未知事实时追问；不含 `answer/expected/solution` | ADR §6b |
| `HISTORY_EVENT_TYPE += TURN_ADVANCED`（payload add-only，PR4 P1-3 replay 需要） | B-PR4 fix | `m1a.v0` 事件枚举 | 仅带 `next_state` payload；旧 payload 兼容 | ADR §6b（已登记）/ PR4 response；ARCHITECTURE §12 |
| **schema v2（add-only）`result_scopes` 表** | B-PR3 | SQLite schema，`SCHEMA_VERSION = 2` | `CREATE TABLE/INDEX IF NOT EXISTS` + v1→v2 迁移与 legacy backfill；不改既有表/列语义；v2 DB forward-only（旧代码 fail-closed） | `m1_teacher/learner/repository.py`；`docs/M1_B_SCOPED_IDEMPOTENCY_IMPLEMENTATION.md` §3.3/§3.4 |

### 1.3 冻结合同的“零 diff”保证

- `m1_teacher/contracts/types.py` 的 `m1a.v0` 记录形状、枚举既有成员、`from_dict/to_dict` 严格语义**未被原地修改**；PR2/PR4 只做 D12 追加（enum 成员）。
- final tree 中 5 个 M1-A 时代测试文件（`test_assessment_scorer`、`test_contracts`、`test_diagnostic_engine`、`test_e2e_resume_idempotency`、`test_fixtures_cf`）因 D12 新值/去 flake/边界收紧更新过；**计数仍为 536 基线，但不是“原样未改”**。
- 校验：`tests/m1_teacher/test_contracts.py` 在 final tree 通过；PR4 Reviewer 独立核实“仅追加枚举值、0 删除/重命名”。

---

## 2. 逐 PR 交付、证据与评审状态

### 2.1 计数总表（final tree 939，文件级归组）

| 来源 | tests | 说明 |
|---|---:|---|
| M1-A 历史基线 | **536** | `REVIEWER_REPORTED` 历史值（`4706250`：独立 Reviewer 实测 536 passed）；**final tree 中 5 个 M1-A 测试文件随 D12/去 flake 更新过，不能称“原样未改”**（P2-4）；计数仍按 536 计 |
| B-PR1 新增/修复后 | **173** | supervisor 36 + worker 27 + sandbox 17 + negatives 11 + correctness 33 + fixture_integrity 15 + hidden_leakage 16 + judge_ci_gate 18 |
| B-PR2 | **63** | turn_transaction 19 + crash_recovery 35 + concurrency 9 |
| B-PR3 | **46** | scoped_idempotency 31 + scope_migration 15（PR3 review-fix 后） |
| B-PR4 | **95** | interview_domain 14 + interview_fixtures 10 + interview_judge 14 + freshness 22 + vertical_policy 17 + b4_e2e 9 + b4_durability_replay 9 |
| B-PR5 | **26** | B5 E2E 11 + evidence_collector 15（含 P1-1 no-.git 回归） |
| **最终树合计** | **939** | = PR4 final 913（536 + 377 PR1/PR2/PR3/PR4 新增/修复） + PR5 26；不得与 M1-Offline 365 相加（无“901”） |

历史/评审侧的全量数字（**不同树/不同 HEAD，不得横向相加或混用**）：

| 评审点 | HEAD | 实测 | 标签 |
|---|---|---|---|
| PR1 评审 | `6e20fd1` | `674 passed in 51.48s`，定向 172 passed | `REVIEWER_REPORTED`（`docs/M1_B_PR1_REVIEW.md` §1） |
| PR2 评审 | PR2 独立分支 | `595 passed`（该分支范围）；crash matrix 当时 32 行 | `REVIEWER_REPORTED`（`docs/M1_B_PR2_REVIEW.md` §3） |
| PR3 评审 | `db636ea` | `774 passed in 88.63s` | `REVIEWER_REPORTED`（`docs/M1_B_PR3_REVIEW.md` §3） |
| PR4 评审 | `11a4f72` | `859 passed in 81.59s`，0 failed/skipped | `REVIEWER_REPORTED`（`docs/M1_B_PR4_REVIEW.md` §1） |
| 最终独立评审 | `c3eb736` | `938 passed`（评审树）；clean archive `937+1`（修复前） | `REVIEWER_REPORTED`（`docs/M1_B_FINAL_INDEPENDENT_REVIEW.md`） |
| final tree（本轮文档基线） | `d9201e9` + 评审链 | **`939 passed in 103.57s`；strict 939/0 skipped；clean archive 939/0**；final review addendum2 `P1_ACTIONS_CLOSED` | `OWNER_REPORTED`（本报告作者本轮实测；final review addendum2 `REVIEWER_REPORTED`） |

### 2.2 B-PR0 — 合同收敛 ADR / 端口 / CI（文档交付）

| 项 | 内容 |
|---|---|
| 目标 | 冻结“A canonical + B vertical + 四端口”裁决、迁移/rollback/checksum 规则、CI/demo 命令；不实现 |
| 关键文件 | `docs/M1_B_CONVERGENCE_ADR.md`、`docs/M1_B_PORTS.md`、`docs/M1_B_CI_AND_DEMO.md`、`docs/M1_B_PR0_REVIEW_RESPONSE.md`；预审 `docs/M1_B_BOUNDARY_PRE_REVIEW.md` |
| 新增测试 | 0（文档-only） |
| 证据命令 | 静态评审 + 既有 A/B 基线命令；`git diff --name-only 4706250..3001d99` 仅 docs |
| 评审结论 | 预审 `PRE_REVIEW_PASS_WITH_ACTIONS`（0 P0 / 8 P1 / 13 P2）；响应 `3001d99` 逐条处置；最终评审判定 **B0-01 = `PARTIAL`**（正式合同签收仍 `NOT_RUN`） |
| 当前状态 | 文档修订在树；B0-01 维护者冻结/签收 `NOT_RUN` |

### 2.3 B-PR1 — 可信判题边界（TrustedJudgeSupervisor / UntrustedExecutionWorker）

| 项 | 内容 |
|---|---|
| 目标 | 不可信 CODE 默认 `UNTRUSTED_CODE_EXECUTION_BLOCKED`；expected/verdict 只在 T1；OS 围栏（bubblewrap）；hidden 不进入 worker；伪 PASS 全部 fail-closed |
| 关键文件 | `m1_teacher/assessment/judge/{supervisor,worker,worker_runner,sandbox,protocol}.py`；`m1_teacher/assessment/scorer.py`；`fixtures/m1_teacher/judge/**`；`tests/m1_teacher/test_judge_*.py`、`test_hidden_leakage_scan.py`；`scripts/m1b/run_safety_ci.sh` |
| 新增测试（final tree） | **173**（见 §2.1；PR1 评审时为 674 全量树中的 138，之后 P1 修复新增 TLE/gate/负例） |
| 证据命令/输出 | final tree：`M1B_REQUIRE_OS_SANDBOX=1 pytest tests/m1_teacher -q -rs` → **939 passed / 0 skipped**；`scripts/m1b/run_safety_ci.sh --allow-root-synthetic` 可用（本地 root 合成模式，不是部署证据）；定向 `test_judge_correctness 33`（14 参考解、112/112 hidden）、`test_judge_sandbox 17`、`test_judge_ci_gate 18`；默认 blocked/伪造 PASS 全拒（PR1 评审 12 协议伪造+6 内存伪造+真实 fd 伪造均非 PASS） |
| 评审文档/结论 | `docs/M1_B_PR1_REVIEW.md`：`PASS_WITH_ACTIONS`（P0=0，P1=4）；`docs/M1_B_PR1_REVIEW_ADDENDUM.md`：`P1_ACTIONS_PARTIALLY_CLOSED`；**final tree**：P1-1 `CLOSED`（默认 TLE）、P1-4 `CLOSED`（语义）、**P1-3 脚本已接线/`.github` job `NOT_CONFIGURED`（PARTIAL）**、**P1-2 实现启动 fail-closed 已存在（`M1B_REQUIRE_NONROOT_SANDBOX`，本机 LOCAL_ONLY）/ 非 root 目标部署验收 `NOT_RUN`（B1-04 仍 `PARTIAL`）** |
| 关键限制 | 真实用户 CODE 仍 **`BLOCKED`**（需人类批准 + 目标部署安全验收）；非 root 宿主本机 **`NOT_RUN`**（root + uid_map→0）；`.github/workflows` 安全 job **`NOT_CONFIGURED/NOT_RUN`**；P2 残余：`spec-sha256` 元数据、`ASSESSED.item.scoring_spec_ref` 路径、worker 可伪造 INFRA/RAISED 抑制学生证据（不能伪造 PASS） |

### 2.4 B-PR2 — 事务、崩溃恢复与单写者

| 项 | 内容 |
|---|---|
| 目标 | `commit_teaching_turn` 单事务（事件+snapshot+session+goal）；`session_version` CAS；真实 SIGKILL 恢复；at-least-once scorer vs exactly-once state；拒绝静默覆盖 |
| 关键文件 | `m1_teacher/learner/repository.py`、`m1_teacher/session/engine.py`、`tests/m1_teacher/{test_turn_transaction,test_crash_recovery,test_concurrency}.py`、`txn_support.py` |
| 新增测试 | **63**（19 + 35 + 9；final tree） |
| 证据命令/输出 | **final tree crash matrix = 34 行：9 rolled_back / 21 prepared / 2 goal-prepared / 2 committed**，全部行无半状态、`verify_rebuild` 由测试断言；`test_crash_recovery 35 passed`、`test_turn_transaction 19`、`concurrency 9`。PR2 评审时旧矩阵为 32 行（9/21/2，聚合 hash `77c620…`/`ec99d5…`/`bbd500…`），**仅历史引用，不是 final tree 数字** |
| 评审文档/结论 | `docs/M1_B_PR2_REVIEW.md`：`PASS_WITH_ACTIONS`（P0=0，P1=2 文档治理、P2=5）；B2-01/02/03 + B-Q2 **VERIFIED**（进程 kill 语义）；review-fix `10fdaa9` 已合入 |
| 关键限制 | 仅单机单文件 SIGKILL；断电持久性 **`UNVERIFIED`**；分布式/多主机并发 **`NOT_RUN`**；DB v2 forward-only（旧构建拒读） |

### 2.5 B-PR3 — Scoped 幂等与多 learner 隔离

| 项 | 内容 |
|---|---|
| 目标 | 复合键 `(learner_id, session_id, item_id, turn_id, result_id)` + request digest；同 token 不同 payload → `IDEMPOTENCY_CONFLICT`；跨 learner/session 不可读旧结果；schema v2 add-only |
| 关键文件 | `m1_teacher/idempotency.py`、`m1_teacher/learner/{repository,history}.py`、`m1_teacher/session/engine.py`、`tests/m1_teacher/{test_scoped_idempotency,test_scope_migration}.py`、`fixtures/m1_teacher/migration/**` |
| 新增测试 | **46**（scoped 31 + migration 15；final tree） |
| 证据命令/输出 | `test_scoped_idempotency 31`、`test_scope_migration 15` 通过；PR3 评审独立探针验证同键幂等/不同 payload 冲突/跨 learner 不可读/目标 learner 零变化；schema v2 `result_scopes(result_id PK, scope_version, learner_id, session_id, …)` + 索引 + v1→v2 迁移/backfill；v2 DB forward-only |
| 评审文档/结论 | `docs/M1_B_PR3_REVIEW.md`：`PASS_WITH_ACTIONS`（P0=0，P1=2、P2=5）；B3-01/B3-02 核心成立；review-fix `3ad85c2`/`a5373f1` 已合入 final tree（P1-1 legacy digest、P1-2 `apply_assessment` scoped 查找均 `CLOSED`） |
| 关键限制 | legacy 默认 id 升级路径仅 string response 已证明；`turn_index=-1` 仅 legacy 行（防御纵深）；v2 DB forward-only |

### 2.6 B-PR4 — CF/Interview/Freshness 双域统一闭环与 domain ports

| 项 | 内容 |
|---|---|
| 目标 | B vertical 经四端口接入 canonical；Interview 5 阶段 + 4 维 rubric + `ASK_CLARIFICATION`；JD v1→v2 只影响新计划；freshness 门禁写入前 fail-closed；统一事件/session replay |
| 关键文件 | `m1_teacher/session/vertical.py`、`m1_teacher/domains/interview.py`、`m1_teacher/knowledge/freshness.py`、`m1_teacher/assessment/interview_judge.py`、`m1_teacher/demo_b4.py`、`fixtures/m1_teacher/vertical/**`、`tests/m1_teacher/{test_interview_*,test_freshness_service,test_vertical_policy,test_b4_e2e,test_b4_durability_replay}.py` |
| 新增测试 | **95**（14+10+14+22+17+9+9；final tree）；PR4 final 全部测试为 913（0 missing） |
| 证据命令/输出 | B4 E2E **9** + durability/replay **9** = 18 passed；B4 demo 双跑 `sha256=b3231658…`、513 行 / 15,340 bytes；JD v1→v2 新计划隔离；freshness KEEP2/UPDATE2/RECHECK5；session `replay_session_state`/`verify_session_replay` 与 MAP-E12/E13 三类版本拒绝（零写入）；`test_b4_durability_replay` 覆盖加速计划重启、完成后不重开、pause/resume、过期 JD、缺失/损坏、replay、篡改、版本拒绝 |
| 评审文档/结论 | `docs/M1_B_PR4_REVIEW.md`：`PASS_WITH_ACTIONS`（P0=0，P1=3、P2=7）；**P1 修复已合入 final tree（`49cf45b`/`1de6ae6`）**：P1-1 会话计划持久化 `CLOSED`、P1-2 hidden reader 清理/守卫 `CLOSED`、P1-3 session replay/版本拒绝 `CLOSED（实现面；event-level schema_version 行 PARTIAL）`；B4-01/02/03 **VERIFIED（E2E-MOCK）**；B4-04 `PARTIAL`、B4-05 `PARTIAL`（event-level schema_version `NOT_IMPLEMENTED`） |
| 关键限制 | 持久复核队列/审批 UI **`NOT_IMPLEMENTED`**（P2-2）；`FULL_SOLUTION` 结构上不可达；阈值 `UNCALIBRATED`；真实学习效果 `NOT_VERIFIED`；B4-05 event-level schema_version 仍 PARTIAL |

### 2.7 B-PR5 — 统一 E2E、证据包与最终评测入口

| 项 | 内容 |
|---|---|
| 目标 | 新统一 E2E/demo；证据包收集器（append-only audit index）；评测协议/报告模板；最终独立评测入口 |
| 关键文件 | `scripts/m1b/collect_evidence.py`、`docs/M1_B_EVIDENCE_PACKET.md`、`docs/M1_B_EVALUATION_PROTOCOL.md`、`docs/M1_B_EVALUATION_REPORT.md`、`tests/m1_teacher/{test_b5_e2e,test_evidence_collector}.py`；E2E/demo：`m1_teacher/demo_b4.py`、`m1_teacher/e2e_b5.py` |
| 新增测试 | **26**（B5 E2E 11 + collector 15；final tree） |
| 证据命令/输出 | B5 E2E `11 passed`；collector `15 passed`（含 P1-1 no-.git 回归）；B5 E2E 双跑 `sha256=4d0e0c85…`（27 行 / 4,168 bytes）；证据包 5 文件 byte-identical；最终 `audit-index.jsonl` 38 条（旧 27 + P1-2 新增 11）；详见 §6.4/§6.5 |
| 评审文档/结论 | **评审链：`docs/M1_B_FINAL_INDEPENDENT_REVIEW.md` `5d5ebf8` `PASS_WITH_ACTIONS`（P0=0/P1=3/P2=6）→ delta `a09e56e` P1-1/P1-2 `CLOSED`、P1-3 errata → addendum2 `d43b02c` `P1_ACTIONS_CLOSED`（P1-3 5/5 CLOSED，仅余 P2 文档项）**；**B5-01 建议 `PASS_WITH_ACTIONS`；总体建议 `PASS_FOR_M1B_OFFLINE_INTEGRATION_SCOPE`（仅离线合成范围）**；最终标签由 Lead/维护者记录 |
| 关键限制 | 收集器只记录执行事实（`EXECUTED_PASS` ≠ 产品 PASS）；证据包旧 27 条（16 过渡 + 11 `c420d19` 窗口）作为历史保留；最终 11 条绑定 `9c383e5`/tree `333828d`；网络隔离需 Reviewer 环境负责；delta 结论未出前不能给无条件 PASS |

---

## 3. 信任边界摘要（B-PR1）

### 3.1 组件与数据流

- **T1 `TrustedJudgeSupervisor`**：唯一持有 hidden expected 与最终 verdict；只向 worker 发送 `code/function_name/args`；对 worker 返回做严格 schema + canonical 比较，任何未知字段/伪造 `passed/verdict` → `JUDGE_INFRA_ERROR`。
- **T2 `UntrustedExecutionWorker`**：在 bwrap 内执行 learner code；响应只允许 `actual_canonical/status` 等 6 字段，**无 passed/verdict/score/expected**；stdout/stderr 只作 excerpt。
- **T3 vertical**：`VerticalAssets` 只含 teacher-visible 内容（LIGHT/INVARIANT/STRUCTURE hint；FULL 不进默认导出，仅受限引用）。
- **默认策略**：`DeterministicScorer` 对 CODE 默认返回 `EVAL_ERROR:UNTRUSTED_CODE_EXECUTION_BLOCKED`，不执行、不调用 worker、mastery 不变；demo/CLI 无请求级开关；trusted fixture 能力只来自可信构造参数（P1-01）。
- **沙箱冻结命令**：`bwrap --unshare-all --die-with-parent --new-session --clearenv --cap-drop ALL`，只读挂载最小 rootfs，`--proc /proc --dev /dev`，私有 tmpfs，uid/gid 65534，`--hostname`；无 `--share-net`、无 `--dev-bind`、无宿主目录；canary 自检失败即 `JUDGE_SANDBOX_UNAVAILABLE`（fail-closed）；rlimits + 墙钟超时 + 进程组 SIGKILL + 有界输出。
- **非 root 启动门**：`M1B_REQUIRE_NONROOT_SANDBOX=1` 时 canary 校验宿主 euid/uid_map，失败 fail-closed；本机 root/uid_map `65534 0 1` → `LOCAL_ONLY`，**目标部署非 root 复跑 `NOT_RUN`**。
- **安全 CI**：`scripts/m1b/run_safety_ci.sh` 已在 final tree：默认 `M1B_REQUIRE_OS_SANDBOX=1 M1B_REQUIRE_NONROOT_SANDBOX=1`，跑 `pytest tests/m1_teacher -q -rs` 并断言 exit 0 / 0 skipped；`.github/workflows` 安全 job 仍 **`NOT_CONFIGURED/NOT_RUN`**（需维护者/CI owner 接线）。

### 3.2 B1-01…B1-06 状态（final review 口径）

| case | 状态 | 依据/限制 |
|---|---|---|
| B1-01 Untrusted code blocked | **VERIFIED (LOCAL_ONLY)** | 默认 blocked；无 worker 调用/快照不变；真实用户 CODE 仍 **BLOCKED** |
| B1-02 Hidden expected isolation | **VERIFIED (LOCAL_ONLY)** | worker 调用最小字段；112/112 hidden cases；target-deploy 复核 `NOT_RUN` |
| B1-03 Result forgery | **VERIFIED (LOCAL_ONLY)** | 12 协议伪造 + 6 内存伪造 + 真实 fd 伪造均非 PASS；不能伪造 PASS；P2：可伪造 INFRA/RAISED 抑制学生证据 |
| B1-04 Judge confinement | **PARTIAL** | bwrap uid/gid/net/pid/ro FS/rlimit/canary 本地通过；宿主 root、uid_map→0；非 root 目标部署 `NOT_RUN` |
| B1-05 Correctness | **PARTIAL** | 14/14 参考解、112/112 hidden、默认 TLE/慢解已修复（P1-1 CLOSED）；目标部署 latency/resource/非 root `NOT_RUN` |
| B1-06 Hidden leakage scan | **VERIFIED (LOCAL_ONLY)** | 运行时导出扫描无 hidden 内容；`ASSESSED.item.scoring_spec_ref` 已 opaque 化（PR4 P1-2/P2-1 修复）；target-deploy 复核 `NOT_RUN` |

### 3.3 PR1 评审 P1 关闭状态（分栏）

| P1 | 状态 | 证据 |
|---|---|---|
| P1-1 默认 TLE | **CLOSED** | `_is_timeout_kill`（负 exit / 124/137/152 + elapsed≥0.9×timeout）；2.0s 死循环 → TLE；慢正确解 PASS；`test_judge_correctness 33` 含断言 |
| P1-2 非 root principal | **实现侧 CLOSED（LOCAL_ONLY）/ 目标部署 `NOT_RUN`** | `M1B_REQUIRE_NONROOT_SANDBOX` + canary fail-closed；final review 探针 root host → `JUDGE_SANDBOX_UNAVAILABLE`、`cases_passed=0`；B1-04 仍 `PARTIAL` |
| P1-3 安全 CI 不可 skip | **PARTIAL：脚本已接线，`.github` job `NOT_CONFIGURED`** | `run_safety_ci.sh` final tree 可跑；`M1B_REQUIRE_OS_SANDBOX=1 -rs` 939 passed / 0 skipped；仓库 `.github` 无该 job |
| P1-4 环境变量措辞 | **CLOSED（语义）** | 实现不读 env 开关；docs lint 覆盖；historical changelog 措辞已在 final review P2 清理（见 §7-19） |

---

## 4. 事务 / 恢复 / 幂等摘要

### 4.1 写入点与原子提交

| 写点 | 事务 | 内容 | 失败后果 |
|---|---|---|---|
| W1 transaction A | 单 `BEGIN IMMEDIATE` | `RESPONSE_SUBMITTED` + `ASSESSMENT_PREPARED`（含 learner/session/item/turn、result_id、response digest/kind、canonical response、session CAS version） | rollback → 无持久化，可重试 |
| W2 external scorer | 无 DB 事务 | in-memory `AssessmentResult` | crash → attempt 保持 PREPARED，`recover_session()` 重打分 |
| W3 transaction B | 单 `BEGIN IMMEDIATE` | 终态 `ASSESSED`/`MASTERY_UPDATED`（或 `ERROR`）、snapshot、next session state | rollback → 回 W1 可恢复；commit → 恰好一次完成 |
| W3b goal write | 与 W3 同事务 | 可选 `GOAL_COMPLETED` + `goals` 行 | 与 mastery/session 原子 |

- **CAS**：`session_version(state) = sha256(canonical_json(state.to_dict()))[:16]`；提交时 stored==expected，否则 `SESSION_VERSION_CONFLICT`。不改冻结 `SessionState` 形状。
- **不变量**：事件/状态严格单调；`PREPARED` 与终态事件不能同事务；终态推进恰好一 turn；无 pending 时不得残留未终结 attempt；重复 event_id/seq 冲突显式报错；snapshot 严格递增 revision。
- **单写者**：`SqliteRepository.commit_teaching_turn` 是唯一教学提交入口；端口/vertical 不注入 repository。
- **一致性边界**：scorer **at-least-once**（可重跑），state **exactly-once**（唯一终态/唯一 mastery）；`recover_session()` 幂等（重复恢复 0 events）。

### 4.2 崩溃/恢复证据（PR2）

- **final tree**：crash matrix **34 行**：9 `rolled_back` / 21 `prepared` / 2 `goal-prepared` / 2 `committed`；全部无半状态、`verify_rebuild` 由测试断言；`test_crash_recovery 35 passed`、`test_turn_transaction 19`、`concurrency 9`。
- PR2 评审时旧矩阵为 **32 行**（9/21/2，聚合 hash `77c62048…`/`ec99d57b…`/`bbd500fb…`），**仅历史引用**，不是 final tree 数字（PR2 评审 §3）。
- B2-01/02/03 + B-Q2 均 **VERIFIED**（进程 kill 语义）；断电持久性 `UNVERIFIED`，多机/分布式 `NOT_RUN`。

### 4.3 Scoped 幂等（PR3）

- 作用域：`(learner_id, session_id, item_id, turn_id, result_id)` + request digest；同 token 同 payload 幂等（唯一 result、零附加 event、mastery 一次）；同 token 不同 payload → `IDEMPOTENCY_CONFLICT`；跨 learner/session 同 token 不可读旧结果。
- **schema v2（add-only）**：`SCHEMA_VERSION = 2`；`result_scopes` 表 + `idx_result_scopes_scope`/`idx_result_scopes_session`；`CREATE ... IF NOT EXISTS`；v1→v2 migration 从 append-only legacy events backfill 元数据；`supports_scoped_idempotency()`；scope 行与教学提交同事务；v2 DB forward-only。
- B3-01/B3-02 **VERIFIED**；PR3 review-fix（`3ad85c2`/`a5373f1`）已合入 final tree：P1-1 结构化 legacy digest 兼容、P1-2 `LearningHistory.apply_assessment()` scoped 查找均 `CLOSED`；final tree `test_scoped_idempotency 31` + `test_scope_migration 15` 通过。
- 当前 final tree 无跨 learner 泄漏证据；最终 Reviewer 仍须复跑 B3 负例（协议 B3 门）。

---

## 5. 双域统一闭环摘要（B-PR4 / B4-01…B4-05）

| case | 状态 | 证据摘要 | 限制 |
|---|---|---|---|
| B4-01 统一 CF 闭环 | **VERIFIED（E2E-MOCK + DETERMINISTIC）** | 同一 SQLite、两 learner、canonical mastery/journal；不同 action/mastery 路径；各自 `verify_rebuild` 通过；CF 动作有 Reason code | 合成学生；非真实学习效果 |
| B4-02 Interview 闭环 | **VERIFIED（E2E-MOCK；含重启/持久化）** | 5 阶段固定顺序；`SESSION_STARTED.payload.vertical.plan`/`jd_snapshot` 持久化；LearnerState 加速；`ASK_CLARIFICATION` 不编造；4 维 rubric + digest；JD v1/v2 新 session 隔离；无 FULL；durability 9 tests（加速计划重启、pause/resume、过期 JD、缺失/损坏、篡改） | E2E 仍为合成问答；非真实学习效果 |
| B4-03 Freshness/JD 门禁 | **VERIFIED（E2E-MOCK）** | KEEP2/UPDATE2/RECHECK5；5 个 RECHECK + JD 时间窗门禁写入前拒绝，0 event/0 session/0 goal，显式 MAP-E08/E09/E10；eligible UPDATE 进新 plan refs | 无持久复核队列/审计事件（P2-2 `NOT_IMPLEMENTED`）；无真实抓取/调度 |
| B4-04 跨域/换学科 | **PARTIAL** | CF→Interview→CF 跨域 replay 通过；Interview 方向重启/跨域覆盖仍有限 | 完整双向跨域 `NOT_RUN` |
| B4-05 版本不兼容拒绝 | **PARTIAL** | MAP-E12/E13 的 session/vertical/plan policy 三类已实现并测试；event-level `schema_version` 消费/拒绝 `NOT_IMPLEMENTED` | 不得写成 PASS；mapping 文档已加 PARTIAL 注记 |

- **JD v1→v2**：同一 learner 在两个时间点分别开 session，`SESSION_STARTED.vertical.jd_version` 分别为 `v1`/`v2`；先开的 session objective/计划不变（只影响新计划）。
- **freshness 门禁**：启动前 fail-closed（`FRESHNESS_JD_GATE_BLOCKED` / `FRESHNESS_KNOWLEDGE_GATE_BLOCKED`，details 带 `map_code` 与 `reason_code`）；被拒尝试零静默写入。
- **统一事件/Replay**：所有域写同一 `history_events`（跨 session seq 连续、snapshot 不变、`verify_rebuild` 通过）；`replay_session_state`/`verify_session_replay` 从事件重建 session phase/pending/plan 并检测篡改；MAP-E12/E13 版本拒绝已实现；**event-level `schema_version` 行 PARTIAL**（B4-05）。
- **demo/E2E**：`python -m m1_teacher.demo_b4 --json` 双跑逐字节相同，**`sha256=b3231658…`、513 行 / 15,340 bytes**；B4 E2E 9 + durability 9 = 18 tests；`python -m m1_teacher.e2e_b5` 双跑 `4d0e0c85…`（27 行）。

---

## 6. 证据与复跑

### 6.1 环境（本报告作者本轮）

- 工作区 `/root/m1b/pr5final-docs`（基线 `d9201e9`）；`/root/Autonomous Teacher/.venv/bin/python`（Python 3.11.15 / pytest 9.2.0 / ruff 0.17.5）；Linux 6.17.13-2-pve；bubblewrap 0.9.0；无网络、无 Key、无 Provider；fixtures synthetic/CC0。
- 每个 pytest 运行独立 `TMPDIR=$(mktemp -d)`，串行执行；`PYTHONDONTWRITEBYTECODE=1`。

### 6.2 最终树复跑命令（本轮实测，`OWNER_REPORTED`）

| # | 命令（cwd=`/root/m1b/pr5final-docs`） | 本轮实测 |
|---|---|---|
| O-01 | `TMPDIR=$(mktemp -d) pytest tests/m1_teacher --collect-only -q` | **939 tests collected** |
| O-02 | `TMPDIR=$(mktemp -d) pytest tests/m1_teacher -q -p no:cacheprovider` | **939 passed in 103.57s**，exit 0，0 skipped |
| O-03 | `M1B_REQUIRE_OS_SANDBOX=1 TMPDIR=$(mktemp -d) pytest tests/m1_teacher -q -rs -p no:cacheprovider` | **939 passed in 102.72s，0 skipped**（`-rs` 无 skip 行） |
| O-04 | `git archive HEAD \| tar -x`（无 `.git`）后 full / strict | full **939 passed in 115.42s**；strict **939 passed in 116.50s / 0 skipped**（P1-1 修复后；修复前 `937+1` 为历史） |
| O-05 | `python -m m1_teacher.demo` ×2 + `cmp` + `sha256sum` + `wc -lc` | identical；`b08ceee9…`；53 行 / 5,798 bytes |
| O-06 | `python -m m1_teacher.demo_b4 --json` ×2 + `cmp` + `sha256sum` + `wc -lc` | identical；**`b3231658…`；513 行 / 15,340 bytes** |
| O-07 | `python -m m1_teacher.e2e_b5` ×2 + `cmp` + `sha256sum` + `wc -lc` | identical；`4d0e0c85…`；27 行 / 4,168 bytes |
| O-08 | `python -m m1_teacher.e2e_b5 --write-evidence` ×2 + `diff -r` | 5 文件 byte-identical；与 `docs/m1b_evidence/` 一致 |
| O-09 | `sha256sum docs/m1b_evidence/audit-index.jsonl docs/m1b_evidence/audit-index.json docs/m1b_evidence/e2e_b5_*.jsonl docs/m1b_evidence/e2e_b5_summary.json` | 见 §6.4（audit-index `a11ce429…`/`8db87530…`；B5 summary `a07cfe7e…`） |
| O-10 | `ruff check m1_teacher tests/m1_teacher` | `All checks passed!` |
| O-11 | `git diff --name-status main...HEAD`；`git diff --name-only 4706250..HEAD`；保护前缀过滤 | **最终代码/测试树：302 files（302 A/0 M/0 D vs main）**；**243 files vs M1-A**；保护前缀 **0 命中**。口径（P2-7）：302/243 不含评审 addendum（`d9201e9`/`db5ce03`）；addendum2 复核 HEAD `1eb40a9` = 303/244；当前 wrap HEAD = 304/245（+1 addendum2 文件），最终 push 以 Lead 记录为准 |
| O-12 | `grep -RInE "autoteacher_m0\|import (httpx\|requests\|aiohttp\|urllib.request)" m1_teacher` | `NONE` |

### 6.3 历史冻结参考（只引用，不相加）

| 线 | 冻结点 | 历史命令 | 历史结果 | 标签 |
|---|---|---|---|---|
| M1-A `m1_teacher` | `4706250`（`m1a.v0`；独立 Review `PASS_FOR_M1A_OFFLINE_MVP`） | clean worktree/archive 后 `pytest tests/m1_teacher -q` | `536 passed`（Reviewer 独立确认）；demo `b08ceee9…`，53 行；evidence `171cc654…`/`5e84229e…`/`23b871a3…`（历史） | `HISTORICAL_FROZEN` |
| M1-Offline `m1_offline` | `290c577`（`m1.offline.v0`；Review clean C2） | `/root/at-m1-offline` 冻结树 `pytest tests/m1_offline -q -p no:cacheprovider` | `365 passed`；demo 历史 `1d57ca62…`（上下文相关） | `HISTORICAL_FROZEN`（不在本树；未被本轮重跑） |

> **禁止**：`536 + 365 = 901` 不是任何真实套件；final B 集成套件 **939**（= 913 + 26）是本树独立计数，不能与 365 相加。M1-A 536 是历史基线；final tree 中 5 个 M1-A 测试文件已更新（见 §1.3），不能写成“536 原样未改”。

### 6.4 证据包（B-PR5 final tree）

- 包位置（在树）：`docs/m1b_evidence/`；结构 = `audit-index.jsonl`（append-only 权威索引）+ `audit-index.json`（物化视图）+ `raw/<run_id>/{evidence.json,stdout.log,stderr.log}` + B5 5 个 evidence 文件 + summary。
- **最终哈希（本轮 `sha256sum` 与 Evaluation Report §9/§13 一致）**：
  - `audit-index.jsonl`：**`a11ce42948d5dd43563a1bf6befa8bb7c8600ba3b73f9df32e345b07bc66ea80`**（38 条）
  - `audit-index.json`：**`8db875301cc10f5af3af4f038b42d50a43a9291ac50c96719f7fd9ce37fc34e5`**（entry_count=38）
  - `e2e_b5_summary.json`：**`a07cfe7ec06208bc3271e01eaaf62a6145c753bf175b23c844658c756d444053`**（manifest `implementation_commit=12f6290…`）
  - `e2e_b5_cf.jsonl` `526f9dfd…`、`e2e_b5_interview.jsonl` `8f3a16fc…`、`e2e_b5_cross_domain.jsonl` `c02723ec…`、`e2e_b5_freshness.jsonl` `8a25de6e…`（四文件不变）
- **P1-2 证据绑定修复**：append-only 旧 27 条（16 条过渡快照 + 11 条 `c420d19` 窗口记录）字节保留；新增第 28–38 条 clean-worktree 记录（`git_sha=9c383e5…`、`tree_sha=333828d…`、generation-start clean=true；旧 27 条前缀 sha `4b9a0d0e…` 不变）。最终索引/镜像哈希即上方 `a11ce429…`/`8db87530…`。
- **P1-1 clean archive 可移植性**：无 `.git` 时 collector 记录 `git_sha=null`/`git_available=false`/`git_sha_source="unavailable"`，支持显式 `--git-sha/--tree-sha`；回归 `test_collector_is_portable_in_a_no_git_archive_copy` 随全量通过；clean archive full/strict 均 939/0。
- 状态语义：`EXECUTED_PASS` 仅表示命令退出 0；`NOT_RUN` 必须有 reason；`evidence_class` 默认 `NOT_VERIFIED`，需 Reviewer 显式标注；无 hash 记录不得进入 PASS 判定。
- 校验方法：按 `docs/M1_B_EVIDENCE_PACKET.md` §7（raw sha256 ↔ 索引、append-only、物化视图一致、无 command-less/hashless PASS、artifact manifest 一致）。

### 6.5 最终数字与状态（FINAL_TREE_MEASURED）

- 最终候选代码/测试树：**`d9201e9`**（含评审链 `5d5ebf8`/`a09e56e`/`d43b02c`、P1-1/P1-2 修复、939 树）；**最终 push SHA = `PENDING_LEAD_MERGE`（由 Lead 记录）**；行为代码 SHA `12f6290…`；P1-2 证据生成 SHA `9c383e5…`/tree `333828d…`；PR4 final `1de6ae6…`/merge `861d147…` 为其前序。
- `pytest tests/m1_teacher -q`（私有 TMPDIR）→ **939 passed in 103.57s**；strict `M1B_REQUIRE_OS_SANDBOX=1 -q -rs` → **939 passed in 102.72s，0 skipped**；clean archive（无 `.git`）full **939 passed in 115.42s** / strict **939 passed，0 skipped**。
- 定向：B5 11 / B4 9 + durability 9 / certification 33（14 参考解、112/112 hidden） / crash 35（matrix 34 行 9/21/2/2） / scoped+migration 46；collector 15；ruff clean。
- 最终独立评审链：`5d5ebf8` `PASS_WITH_ACTIONS` → `a09e56e` P1-1/P1-2 `CLOSED`、P1-3 errata → **`d43b02c` addendum2 `P1_ACTIONS_CLOSED`（P1-3 5/5，仅余 P2 文档项）**；**总体建议 `PASS_FOR_M1B_OFFLINE_INTEGRATION_SCOPE`（仅离线合成范围）**；B5-01 建议 `PASS_WITH_ACTIONS`，最终标签/签收由 Lead/维护者记录。clean archive strict/证据哈希见 §6.4。
- 旧 `e2b6e85`/`c3eb736` 过渡快照数字仅保留为历史，不是 final tree 值；final 值以 §6.2/§6.5 的 939/939 与 `d9201e9` 为准。

---

## 7. 失败、限制与未验证项（原样保留）

| # | 项 | 状态/原因 | 来源 |
|---|---|---|---|
| 1 | 真实学习收益/教学效果 | **`NOT_VERIFIED`**：全部为确定性启发式 + synthetic 输入 | final review §9；DOMAINS §6 |
| 2 | 真实 Provider/联网/付费/LiveGate | **`BLOCKED`**：无 Key/网络；人类 Gate 未开 | 评估协议 §10/§12；final review §9 |
| 3 | 真实用户 CODE 开放 | **`BLOCKED`**：需人类批准 + 目标部署安全验收 | PR1 review/附录；final review §8 |
| 4 | 非 root 部署 principal | **`NOT_RUN`**：本机 root + uid_map 65534→0；实现侧 opt-in 启动门已存在/本地验证；B1-04 `PARTIAL` | final review §7/§8；PR1 addendum |
| 5 | 安全 CI job（`.github`） | **`NOT_CONFIGURED/NOT_RUN`**：仓库 `.github` 无测试/security workflow；`scripts/m1b/run_safety_ci.sh` 已在树，但需 CI owner 接线 | final review §8；本报告 O-03 |
| 6 | 断电持久性 | **`UNVERIFIED`**：仅真实 SIGKILL 进程崩溃矩阵 | TXN 文档/PR2 评审 |
| 7 | 分布式/多主机并发 | **`NOT_RUN`**：仅单机单文件 | PR2 评审 B2-03 |
| 8 | 持久 review queue/审批 UI | **`NOT_IMPLEMENTED`**（已披露，P2-2） | PR4 评审；final review §8 |
| 9 | event-level `schema_version` 拒绝 | **`NOT_IMPLEMENTED` / PARTIAL**（B4-05；session/vertical/plan 三类 MAP-E12/E13 已实现） | PR4 评审；final review §8 |
| 10 | `FULL_SOLUTION` / 人工审批路径 | 结构上不可达（fail-closed），无审批 UI；FULL 内容仅在受限引用 | PR4 评审 P2-7；DOMAINS §9 |
| 11 | B4-04 完整双向跨域 / 真实 hidden 评测集 | **`NOT_RUN` / 未转换** | final review §8/§9 |
| 12 | 阈值（加速 0.25/证据 2、hint cap、interview ladder） | **`UNCALIBRATED`**：无真实数据校准 | DOMAINS §9 |
| 13 | 真实 auth/多租户隔离 | **`NOT_RUN`**：learner_id 由上层传入，无真实鉴权 | final review §9 |
| 14 | B0-01 合同正式签收 | **`NOT_RUN`**（文档/预审响应在树，维护者冻结未执行） | final review §8 |
| 15 | 最终独立评审 delta/addendum2 | **`P1_ACTIONS_CLOSED`（`d43b02c`；P1-3 5/5 CLOSED）**；仅余 P2 文档项（P2-7 X-01 口径已加注、P2-8 状态已刷新、P2-9 占位由 Lead 记录）；总体建议 `PASS_FOR_M1B_OFFLINE_INTEGRATION_SCOPE`（仅离线合成范围），不构成真实效果/Provider/Live/生产 PASS | final review addendum2 §0/§4/§6；本报告 §6.5 |
| 16 | 旧证据条目 | 旧 27 条（16 过渡 + 11 `c420d19` 窗口）作为历史保留，不删除/不改写；final 11 条绑定 `9c383e5`/tree `333828d` | Evaluation Report §13；本报告 §6.4 |
| 17 | 全仓 M0 套件 | 本轮未跑（不在 B 线验收范围；历史 `6 failed/1697 passed/19 skipped` 不重跑、不引用为 PASS） | final review §9 |
| 18 | P2 文档精度残留 | 已在本提交处理：demo_b4 行列数、PR2 crash 34 行、536 基线措辞、ARCH §14 schema v1→v2、threat-model changelog 旧短语、mapping event schema_version PARTIAL 注记（详见 §7-19 与 review request） | 本轮 |
| 19 | 文档勘误边界 | 本提交只改 `M1_B_IMPLEMENTATION_REPORT.md`、`M1_B_REVIEW_REQUEST.md` 及少量 P2 精度文档（threat model changelog、mapping PARTIAL 注记、ARCHITECTURE §14）；**不改** `M1_B_EVALUATION_REPORT.md`（b-eval 所有）与任何 Reviewer 评审文档 | 本轮 |

---

## 8. 依赖、合并顺序与保护路径

### 8.1 Stacked 关系（已集成 final tree）

| 层 | 分支/来源 | 当前 tip（本轮核对） | 内容 | final tree？ |
|---|---|---|---|---|
| PR0 | `b-next/pr0-convergence-adr` | `3001d99` | ADR/PORTS/CI/docs + 预审响应 | 是 |
| PR1 impl | `b-next/pr1-judge-worker` | `fb6cf33`（+ `8d7ede6`/`0fd3ed4`） | supervisor/worker/sandbox/scorer | 是 |
| PR1 review/fix | `b-next/pr1-review` / `b-next/pr1-trusted-judge` | `62c32c5` / `550ad37`（含 `8175233`、`af09cff`） | 评审 + P1/P2 修复 + safety CI | **是（已合入 final tree）** |
| PR2 | `b-next/pr2-session-txn` | `7f9ce06`（含 `10fdaa9`） | 事务/恢复/幂等 | 是 |
| PR3 impl/review/fix | 合并分支 / `b-next/pr3-review` / `b-next/pr3-scoped-idempotency` | `18b08fe`/`2f32f13`/`3103a06` / `db636ea` / `a5373f1`（含 `3ad85c2`） | scoped 幂等 + schema v2 + P1 修复 | 是 |
| PR4 impl/review/fix | `b-next/pr4-interview-freshness` / `b-next/pr4-domain-ports` / fixes | `e265b96` / `dfda203` / **`49cf45b`/`1de6ae6`** | vertical ports / interview / freshness / P1 修复 | 是 |
| PR5 | `b-next/pr5-e2e-eval` → final | **`d9201e9`**（含 `861d147`/`c420d19`/`9c383e5`/`12f6290` 系列） | 证据收集器 + 模板 + 统一 E2E + 最终评审/证据修复 | **是（本报告基线）** |
| 最终独立评审（首轮） | `docs/M1_B_FINAL_INDEPENDENT_REVIEW.md` | `5d5ebf8` | PASS_WITH_ACTIONS（P0=0/P1=3/P2=6） | 是（文档） |
| delta 复核（P1-1/P1-2） | `docs/M1_B_FINAL_INDEPENDENT_REVIEW_ADDENDUM.md` | `a09e56e` | P1-1/P1-2 `CLOSED`、P1-3 errata | 是（文档） |
| addendum2（P1-3） | `docs/M1_B_FINAL_INDEPENDENT_REVIEW_ADDENDUM_2.md` | `d43b02c` | **`P1_ACTIONS_CLOSED`（仅余 P2）** | 是（文档） |

### 8.2 合并顺序与冻结

1. PR0→PR1→PR2→PR3→PR4→PR5 已按 stacked 方式合入 final tree；PR4 P1 修复（`49cf45b`/`1de6ae6`）、PR1/PR3 review-fix 与 PR5 P1 证据修复均在树。
2. 当前 `b-next/pr5-final-docs` 仅做文档勘误（本提交）；**代码/测试树保持 `d9201e9` 不变**。
3. final Reviewer 已完成 delta `a09e56e` 与 addendum2 `d43b02c`（**`P1_ACTIONS_CLOSED`**，仅余 P2）；Lead 将本 docs-only 分支合入 PR5 后记录最终 push SHA（`PENDING_LEAD_MERGE`）。
4. 总体建议 `PASS_FOR_M1B_OFFLINE_INTEGRATION_SCOPE`（仅离线合成范围）；最终标签/签收由 Lead/维护者按流程记录，仍不构成真实效果/Provider/Live/生产 PASS。

### 8.3 M0 保护路径零变更

- final tree 相对 `main` = **302 文件（302 A / 0 M / 0 D）**；相对 M1-A = **243 文件**；全部位于 `docs/`、`fixtures/`、`m1_teacher/`、`tests/`、`scripts/m1b/`。口径（P2-7）：302/243 不含评审 addendum（`d9201e9`/`db5ce03`）；addendum2 复核 HEAD = 303/244；本 wrap 分支合并 addendum2 文件后为 304/245（以 Lead 最终 push 为准）。
- 保护前缀 `src/autoteacher_m0/`、`security/`、`bridge/`、`config/g*`、`scripts/g4*`、`.github/`、`plugins/`、LiveGate/账本/授权路径：**0 命中**。
- 本轮静态扫描：`m1_teacher` 无 M0 import、无网络库 import（`NONE`）；无真实 Key/Provider 调用；无 `.github` 变更。

---

## 9. 未决项汇总（交维护者/最终 Reviewer）

| 类别 | 项 |
|---|---|
| 必须人类批准 | 真实用户 CODE 开放；真实 Provider/LiveGate；非 root 部署验收；G4-H/G5/M0 决策 |
| 最终评测前必须完成 | ~~原 final Reviewer 的 delta 复核~~ **已完成（`a09e56e` + `d43b02c` `P1_ACTIONS_CLOSED`）**；剩余：维护者签收 B0 ADR、Lead 记录最终 push SHA（`PENDING_LEAD_MERGE`）、最终标签按流程记录 |
| 文档清理 | 已处理 P1-3/P2-1..P2-6 与 addendum2 P2-7（X-01 口径）/P2-8（状态刷新）/P2-9（`PENDING_LEAD_MERGE` 占位）文档项；不阻断 |
| 产品/测试缺口 | persistent review queue；event-level schema_version（B4-05 PARTIAL）；FULL_SOLUTION/审批 UI；真实 auth/多租户；断电/分布式；真实 hidden 评测集 |
| 最终裁定 | 见 `docs/M1_B_EVALUATION_REPORT.md` / `docs/M1_B_FINAL_INDEPENDENT_REVIEW.md` / `_ADDENDUM_2.md`：**addendum2 `P1_ACTIONS_CLOSED`，总体建议 `PASS_FOR_M1B_OFFLINE_INTEGRATION_SCOPE`（仅离线合成范围）**；本报告不把 `MOCK/DETERMINISTIC` 写成真实效果，不解除人类 Gate |

---

## 10. 变更记录

| 日期（UTC） | 版本 | 变更 |
|---|---|---|
| 2026-11-20 | v0 | 初稿：PR0–PR5 汇总；旧快照 `e2b6e85`；最终数字 TBD |
| 2026-11-20 | v1 | PR4 final 合入后过渡值（非 final；已由 v2 勘误覆盖） |
| 2026-11-21 | **v2** | final-tree 勘误（final review P1-3/P2）：939/913+26 计数、clean archive 939/0、X-01 302 vs main / 243 vs M1-A、B4 demo `b3231658…`/513/15,340、B5 `4d0e0c85…`、evidence final hashes、PR4 P1 已合入、PR1 P1-2 分栏/P1-3 脚本接线、PR2 crash 34 行、536 历史基线措辞 |
| 2026-11-21 | **v3** | **final consistency patch（addendum2 后）**：评审链 `5d5ebf8` → `a09e56e` → `d43b02c` **`P1_ACTIONS_CLOSED`**（仅余 P2）；总体建议 `PASS_FOR_M1B_OFFLINE_INTEGRATION_SCOPE`（仅离线合成范围）；最终 push SHA 写 `PENDING_LEAD_MERGE`；X-01 口径 302/243（不含 addendum）/303/244（addendum2 复核 HEAD）/304/245（当前 wrap，最终 push 为准）；仍不构成真实效果/Live/生产 PASS |
