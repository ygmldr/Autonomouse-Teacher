# M1-B 最终实现报告（B-NEXT / B-PR0…B-PR5）

| 字段 | 值 |
|---|---|
| 文档状态 | **`OWNER_REPORTED`（实现汇总 + Owner 侧证据；不是最终独立验收，不是 PASS）** |
| 文档版本 | `m1b.impl-report.v0`（2026-11-20 UTC） |
| 工作区 / 分支 | `/root/m1b/pr5` / `b-next/pr5-e2e-eval`（最终树 `861d147` + B5 `c420d19`；PR5 最终 commit SHA 回填） |
| 被汇总范围 | B-PR0 合同收敛 → B-PR1 可信判题 → B-PR2 事务/恢复 → B-PR3 scoped 幂等 → B-PR4 双域 ports → B-PR5 统一 E2E/证据 |
| 最终数字归属 | **最终树实测（本报告标注 FINAL_TREE_MEASURED）：938 passed（clean TMPDIR）、strict `M1B_REQUIRE_OS_SANDBOX=1 -rs` 938 passed/0 skipped；最终 SHA/evidence hashes 以 `docs/M1_B_EVALUATION_REPORT.md` §13 为准**（协议 `docs/M1_B_EVALUATION_PROTOCOL.md`）。PR1/PR2/PR3/PR4 review-fix tree 已合入 final tree；B-PR5 最终独立评审仍 `PENDING`（Lead 指派） |
| 证据词汇 | 按评估协议 §1 冻结词汇。本文件只使用 `OWNER_REPORTED`（本线实现/本轮文档作者实测，未经独立 Reviewer 复跑）、`HISTORICAL_FROZEN`（历史冻结参考）、`NOT_RUN`、`BLOCKED`、`NOT_VERIFIED`、`UNVERIFIED`；**不使用 `INDEPENDENTLY_REEXECUTED`**（该标签只能由独立 Reviewer 本轮真实复跑获得） |
| 边界 | 仅离线、合成 fixtures、确定性/mock E2E；**不包含**真人学习收益、真实招聘/JD/简历、联网研究、真实 Provider/LLM、LiveGate、生产可用性；M0 保护路径零变更 |

> **核心声明**：本报告证明“回答/汇总既有 Owner/Reviewer 证据 + 当前快照可复跑事实”，不替代独立评测；
> 不得把本文数字写成最终 PASS，不得把历史 `536 + 365` 相加（不存在“统一 901”）；
> `NOT_RUN/BLOCKED/UNVERIFIED/NOT_VERIFIED` 一律保留原状态。

---

## 0. 结论摘要（最终树 `FINAL_TREE_MEASURED`；原 `e2b6e85` 过渡快照数值仅保留于 §6.2 历史行）

| 项 | 最终值 | 标签 |
|---|---|---|
| 最终集成树 | PR4 final `1de6ae6d…` 合入 PR5 后 merge `861d147d…`；B5 实现提交 `c420d19…`；PR5 最终 commit SHA 回填 | — |
| 测试收集数 | **938 collected** | `OWNER_REPORTED`（`--collect-only`；clean TMPDIR） |
| 新集成套件（最终树） | **938 总计** = PR4 final 913（含 PR1/PR2/PR3 review-fix tree + PR4 final） + PR5 25（B5 11 + collector 14）；历史 M1-A 536 含于其中、未改；不得与 M1-Offline 365 相加 | `OWNER_REPORTED` + collector-only `EXECUTED_PASS`（非产品 PASS） |
| 全量套件（干净 `TMPDIR`，最终树） | **`938 passed in 102.76s`，exit 0，0 skipped** | `OWNER_REPORTED`（final tree 实测） |
| 全量套件（strict `M1B_REQUIRE_OS_SANDBOX=1 -rs`） | **`938 passed in 102.95s`，0 skipped** | `OWNER_REPORTED`（final tree 实测；PR1 gate 已合入） |
| 旧快照（`e2b6e85`）共享 `/tmp` 环境 | 曾出现 `4 failed, 869 passed`（judge 临时目录清理断言；干净 TMPDIR 下消失）——**历史事实，final tree 已用私有 TMPDIR 复跑无失败** | `OWNER_REPORTED`（旧快照） |
| A demo 双跑 | 逐字节相同；`sha256=b08ceee915fb0363864e303ded71de4d547eae6d14f7aa693ba1537a810d491b`；53 行 / 5,798 bytes | `OWNER_REPORTED`（本轮实测；与历史一致） |
| B4 demo（`--json`）双跑 | 逐字节相同；`sha256=6b7bb66e36a38bd640d5b47d206d8fee24a446df9b42dbe76d20dd8cc50bef83`；511 行 / 15,108 bytes | `OWNER_REPORTED`（本轮实测；与 PR4 Reviewer 记录一致） |
| `ruff check m1_teacher tests/m1_teacher` | `All checks passed!` | `OWNER_REPORTED`（本轮实测） |
| 相对基线 `4706250` 的变更面 | 100 个文件，全部位于 `docs/`、`fixtures/`、`m1_teacher/`、`tests/m1_teacher/`、`scripts/m1b/`；**M0/security/bridge/config/g*/scripts/g4*/plugins/LiveGate 零变更** | `OWNER_REPORTED`（本轮 `git diff --name-only` 过滤） |
| 最终裁定 | Owner 侧 `FINAL_TREE_MEASURED`；**独立 Reviewer 最终裁定 `PENDING`（Lead 指派）**；Owner 不预填 PASS | `PENDING` |

**当前必须如实保留的负面事实（final tree 更新后）**

1. 旧 `e2b6e85` 快照的 4 个 judge 失败是**共享 `/tmp` 环境污染导致的测试隔离缺陷**；final tree 在 `mktemp -d` 私有 TMPDIR 串行复跑 **938 passed / 0 skipped**。最终 Reviewer 必须使用干净 TMPDIR（或先清理残留），否则会出现假失败。
2. **PR1/PR2/PR3/PR4 review-fix tree 已合入 final tree**（PR4 final `1de6ae6d`）；PR5 最终评测报告（Owner 侧）已产出；**`B5-01` 最终独立评审 `PENDING`（Lead 指派）**。
3. 真实学习效果 **`NOT_VERIFIED`**；真实 Provider/网络/LiveGate **`BLOCKED`**；目标部署（非 root、断电、真实 CODE）**`NOT_RUN`/`UNVERIFIED`**。
4. 两条历史线（M1-A 536 / M1-Offline 365）是**各自独立冻结**的参考，不是本套件的组成；新套件计数必须独立统计。

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

`docs/M1_ADR_001_DOMAIN_CONTRACTS.md` §6b 为 append-only 变更日志（第 273–282 行附近）；同时记录在
`docs/M1_ARCHITECTURE.md` §12 change log（PR2 条目）。**只追加、不重命名/删除任何既有值**：

| 变更 | PR | 枚举/合同 | 兼容性 | 位置 |
|---|---|---|---|---|
| `HISTORY_EVENT_TYPE += ASSESSMENT_PREPARED` | B-PR2 | `m1a.v0` 事件枚举（冻结） | 旧 payload 不受影响；旧构建读新事件会 fail-closed（forward-only） | ADR §6 item 9 + §6b；ARCHITECTURE §12 |
| `TEACHING_ACTION_KIND += SOCRATIC_QUESTION` | B-PR4 | `m1a.v0` 教学动作枚举 | 仅 vertical interview 使用；CF/A 路径不发出 | ADR §6b |
| `TEACHING_ACTION_KIND += ASK_CLARIFICATION` | B-PR4 | 同上 | 未知事实时追问；不含 `answer/expected/solution` | ADR §6b |
| **schema v2（add-only）`result_scopes` 表** | B-PR3 | SQLite schema，`SCHEMA_VERSION = 2` | `CREATE TABLE/INDEX IF NOT EXISTS` + v1→v2 迁移与 legacy backfill；不改既有表/列语义；v2 DB 不能被旧代码读取（forward-only） | `m1_teacher/learner/repository.py`；`docs/M1_B_SCOPED_IDEMPOTENCY_IMPLEMENTATION.md` §3.3/§3.4 |

> 注：ADR §5 仍保留一句“Additive extensions expected later (all allowed under D12): optional fields on records with defaults…” 的旧措辞，与 P1-04 的“v0 类型零 diff（不得加可选字段）”原则存在**文档内部张力**；本报告不据此改变实现，但最终文档合入时应统一措辞（见 §7 残余项）。

### 1.3 冻结合同的“零 diff”保证

- `m1_teacher/contracts/types.py` 的 `m1a.v0` 记录形状、枚举既有成员、`from_dict/to_dict` 严格语义**未被原地修改**；PR2/PR4 只做上述 D12 追加（enum 成员），`test_contracts.py` 冻结期望仅做 +1/+2 行同步，无删除/重命名。
- 校验（Owner 侧）：`tests/m1_teacher/test_contracts.py` 169 tests 在当前快照通过；PR4 Reviewer 独立核实“仅追加 3 个枚举值、0 删除”。

---

## 2. 逐 PR 交付、证据与评审状态

### 2.1 计数总表（最终树 938，文件级归组；旧 e2b6e85 快照仅历史）

| 来源 | 测试数 | 说明 |
|---|---|---|
| M1-A 历史基线 | **536** | 历史冻结（`m1a` 分支 tip `4706250`）；Reviewer 在 clean archive 独立确认 `536 passed in 16.41s`（PR2 评审 E8） |
| B-PR1 新增 | **138** | supervisor 36 + worker 23 + sandbox 11 + negatives 11 + correctness 27 + fixture_integrity 15 + hidden_leakage_scan 15 |
| B-PR2 新增 | **63** | turn_transaction 19 + crash_recovery 35 + concurrency 9 |
| B-PR3 新增 | **37** | scoped_idempotency 26 + scope_migration 11 |
| B-PR4 新增 | **85** | interview_domain 14 + interview_fixtures 10 + interview_judge 14 + freshness 22 + vertical_policy 16 + b4_e2e 9 |
| B-PR5 新增 | **14** | evidence_collector 14 |
| **最终树合计** | **938** | PR4 final 913 + PR5 25；不得与 B 线历史 365 相加（无“901”）；严格模式 938 passed / 0 skipped |

历史/评审侧的全量数字（**不同树/不同 HEAD，不得横向相加或混用**，均按原报告标签引用）：

| 评审点 | HEAD | 实测 | 标签 |
|---|---|---|---|
| PR1 评审 | `6e20fd1` | `674 passed in 51.48s`，定向 172 passed | `REVIEWER_REPORTED`（`docs/M1_B_PR1_REVIEW.md` §1） |
| PR2 评审 | PR2 独立分支 | `595 passed`（该分支范围）；crash matrix 32 行 | `REVIEWER_REPORTED`（`docs/M1_B_PR2_REVIEW.md` §3） |
| PR3 评审 | `db636ea` | `774 passed in 88.63s` | `REVIEWER_REPORTED`（`docs/M1_B_PR3_REVIEW.md` §3） |
| PR4 评审 | `11a4f72` | `859 passed in 81.59s`，0 failed/skipped | `REVIEWER_REPORTED`（`docs/M1_B_PR4_REVIEW.md` §1） |
| PR5 最终树 | `861d147` + `c420d19` | **`938 passed in 102.76s`**（clean TMPDIR）；strict `938 passed / 0 skipped` | `OWNER_REPORTED`（final tree 实测） |

### 2.2 B-PR0 — 合同收敛 ADR / 端口 / CI（文档交付）

| 项 | 内容 |
|---|---|
| 目标 | 冻结“A canonical + B vertical + 四端口”裁决、迁移/rollback/checksum 规则、CI/demo 命令；不实现 |
| 关键文件 | `docs/M1_B_CONVERGENCE_ADR.md`、`docs/M1_B_PORTS.md`、`docs/M1_B_CI_AND_DEMO.md`、`docs/M1_B_PR0_REVIEW_RESPONSE.md`；预审 `docs/M1_B_BOUNDARY_PRE_REVIEW.md` |
| 新增测试 | 0（文档-only；不改实现/测试） |
| 证据命令 | 静态评审 + 既有 A/B 基线命令（见 §6.2 O-01/O-02 与模板 C-01/C-02）；`git diff --name-only 4706250..3001d99` 仅 docs |
| 评审结论 | 预审 `PRE_REVIEW_PASS_WITH_ACTIONS`（0 P0 / 8 P1 / 13 P2）；响应 `3001d99` 逐条处置（7 项 P1 文档修订、P1-08 转办 b-cf；P2 修复/转办见响应文档） |
| 当前状态 | 文档修订在树；B0-01 独立合同验收 **`NOT_RUN`**（最终 Reviewer 仍需按协议门 G1–G8 审查） |

### 2.3 B-PR1 — 可信判题边界（TrustedJudgeSupervisor / UntrustedExecutionWorker）

| 项 | 内容 |
|---|---|
| 目标 | 不可信 CODE 默认 `UNTRUSTED_CODE_EXECUTION_BLOCKED`；expected/verdict 只在 T1；OS 围栏（bubblewrap）；hidden 不进入 worker；伪 PASS 全部 fail-closed |
| 关键文件 | `m1_teacher/assessment/judge/{supervisor,worker,worker_runner,sandbox,protocol}.py`；`m1_teacher/assessment/scorer.py`；`fixtures/m1_teacher/judge/**`；`tests/m1_teacher/test_judge_*.py`、`test_hidden_leakage_scan.py` |
| 新增测试 | **138**（当前树）；Owner 初始 worker 分支记录 `596 = 536 + 60`，后续 fixture/correctness 合入后 674（`OWNER_REPORTED`） |
| 证据命令（Owner/Reviewer 已跑） | `pytest tests/m1_teacher -q`；定向 `test_judge_supervisor/worker/sandbox/negatives/correctness/fixture_integrity/hidden_leakage_scan`；`test_judge_correctness.py`（14 参考解、112/112 hidden cases）；攻击模板矩阵（stack-frame 读 expected、argv/result 伪造、宿主 sentinel、stdout 伪造 PASS、`os._exit`、fork、infinite loop、tmpfs 写入）全部非 PASS |
| 实际输出摘要 | 当前快照：judge 相关文件集合共 138 tests（本轮 collect-only 归组；本轮未单独重跑该子集）；PR1 Reviewer 在 `6e20fd1`：全量 `674 passed in 51.48s`，定向 `172 passed`；B1-01/02/03/06 `VERIFIED (LOCAL_ONLY)`；B1-04/05 `PARTIAL` |
| 评审文档/结论 | `docs/M1_B_PR1_REVIEW.md`（`62c32c5`，分支 `b-next/pr1-review`）：**`PASS_WITH_ACTIONS`**，P0=0，P1=4；`docs/M1_B_PR1_REVIEW_ADDENDUM.md`（`af09cff`）：**`P1_ACTIONS_PARTIALLY_CLOSED`**（P1-1/P1-4 CLOSED；P1-3 机制关闭但 CI 未接线；P1-2 未关闭） |
| Review-fix 状态 | **已合入 final tree（PR4 final `1de6ae6d`）**：PR1 修复 `8175233`/`550ad37` 的 P1-1/P1-3/P1-4 及 P1-2 文档/报告部分；PR1 addendum 复核为 `P1_ACTIONS_PARTIALLY_CLOSED`（P1-2 非 root principal 仍 `NOT CLOSED`）；final tree strict `938 passed / 0 skipped` |
| 关键限制 | 真实用户 CODE 仍 **`BLOCKED`**（需人类批准 + 目标部署安全验收）；非 root 宿主 principal 本机 **`NOT_RUN`**（当前 root + uid_map→0）；`.github/workflows` 安全 job 未配置（`NOT_CONFIGURED/NOT_RUN`）；P2 残余：`spec-sha256` 元数据、`ASSESSED.item.scoring_spec_ref` 路径、worker 可伪造 INFRA/RAISED 抑制学生证据（不能伪造 PASS） |

### 2.4 B-PR2 — 事务、崩溃恢复与单写者

| 项 | 内容 |
|---|---|
| 目标 | `commit_teaching_turn` 单事务（事件+snapshot+session+goal）；`session_version` CAS；真实 SIGKILL 恢复；at-least-once scorer vs exactly-once state；拒绝静默覆盖 |
| 关键文件 | `m1_teacher/learner/repository.py`（commit 事务/CAS/恢复审计）、`m1_teacher/session/engine.py`（两阶段 `ASSESSMENT_PREPARED`）、`tests/m1_teacher/{test_turn_transaction,test_crash_recovery,test_concurrency}.py`、`txn_support.py` |
| 新增测试 | **63**（19 + 35 + 9；当前树） |
| 证据命令/输出 | Owner 文档：crash matrix 9 rolled_back / 21 prepared / 2 committed，所有行 `verify_rebuild=True`；Reviewer 独立复跑（`docs/M1_B_PR2_REVIEW.md` §3）：全量 `595 passed`、crash matrix 32 行、并发 9 passed、E8 基线 536 passed；matrix 聚合 hash `77c62048e9c34a12`（rolled_back）/`ec99d57baf55a6e6`（prepared）/`bbd500fbb1ca734b`（committed） |
| 评审文档/结论 | `docs/M1_B_PR2_REVIEW.md`（`434f731`）：**`PASS_WITH_ACTIONS`**，P0=0，P1=2（均为文档治理，非产品缺陷）、P2=5；B2-01/02/03 + B-Q2 **VERIFIED**（进程 kill 语义） |
| Review-fix 状态 | 修复 `10fdaa9`（P1-1/P1-2 + P2-1..5）**已在当前快照**；`M1_ADR_001`/`M1_ARCHITECTURE` 的 D12 留痕随该修复进入树 |
| 关键限制 | 仅单机单文件 SIGKILL；断电持久性 **`UNVERIFIED`**；分布式/多主机并发 **`NOT_RUN`**；`ASSESSMENT_PREPARED` 使 DB forward-only（旧构建拒读，已文档化） |

### 2.5 B-PR3 — Scoped 幂等与多 learner 隔离

| 项 | 内容 |
|---|---|
| 目标 | 复合键 `(learner_id, session_id, item_id, turn_id, result_id)` + request digest；同 token 不同 payload → `IDEMPOTENCY_CONFLICT`；跨 learner/session 不可读旧结果；schema v2 add-only |
| 关键文件 | `m1_teacher/idempotency.py`、`m1_teacher/learner/{repository,history}.py`、`m1_teacher/session/engine.py`、`tests/m1_teacher/{test_scoped_idempotency,test_scope_migration}.py`、`fixtures/m1_teacher/migration/**` |
| 新增测试 | **37**（26 + 11；当前树） |
| 证据命令/输出 | PR3 Reviewer：全量 `774 passed in 88.63s`；`test_scoped_idempotency.py 26 passed`；`test_scope_migration.py 11 passed`；独立探针验证同键幂等/不同 payload 冲突/跨 learner 不可读/目标 learner 零变化；schema v2 DDL `result_scopes(result_id PK, scope_version, learner_id, session_id, …)` + 索引 + v1→v2 迁移/backfill |
| 评审文档/结论 | `docs/M1_B_PR3_REVIEW.md`（`db636ea`，分支 `b-next/pr3-review`）：**`PASS_WITH_ACTIONS`**，P0=0，P1=2、P2=5；B3-01/B3-02 核心验收成立 |
| Review-fix 状态 | **已合入 final tree（PR4 final `1de6ae6d` 含 PR1/PR2/PR3 review-fix tree）**：legacy 结构化 response digest 兼容（P1-1）、`LearningHistory.apply_assessment()` scoped 查找（P1-2）随 review-fix 合入；final tree `test_scope_migration` 15 + `test_scoped_idempotency` 31 passed |
| 关键限制 | legacy 默认 id 升级路径仅 string response 已证明；`turn_index=-1` 仅 legacy 行（防御纵深）；v2 DB forward-only |

### 2.6 B-PR4 — CF/Interview/Freshness 双域统一闭环与 domain ports

| 项 | 内容 |
|---|---|
| 目标 | B vertical 经四端口接入 canonical；Interview 5 阶段 + 4 维 rubric + `ASK_CLARIFICATION`；JD v1→v2 只影响新计划；freshness 门禁写入前 fail-closed；统一事件/Replay |
| 关键文件 | `m1_teacher/session/vertical.py`、`m1_teacher/domains/interview.py`、`m1_teacher/knowledge/freshness.py`、`m1_teacher/assessment/interview_judge.py`、`m1_teacher/demo_b4.py`、`fixtures/m1_teacher/vertical/**`、`tests/m1_teacher/{test_interview_*,test_freshness_service,test_vertical_policy,test_b4_e2e}.py` |
| 新增测试 | **85**（14+10+14+22+16+9）；PR4 增量说明：既有 774 + 新增 85 = 859（PR4 Reviewer 复算，0 缺失节点） |
| 证据命令/输出 | PR4 Reviewer：`859 passed in 81.59s`、0 skipped；`test_b4_e2e.py 9 passed`；`test_vertical_policy.py 16 passed`；B4 demo 双跑 `sha256=6b7bb66e…`（15,108 bytes）；独立探针覆盖双 CF learner、双 interview learner、JD v1→v2、freshness KEEP2/UPDATE2/RECHECK5、零静默写入 |
| 评审文档/结论 | `docs/M1_B_PR4_REVIEW.md`（`dfda203`，分支 `b-next/pr4-domain-ports`）：**`PASS_WITH_ACTIONS`**，P0=0，P1=3、P2=7；B4-01 **VERIFIED**、B4-02 **VERIFIED（会话内，重启缺陷 P1-1）**、B4-03 **VERIFIED（无持久复核队列 P2-2）**；B4-04 部分、B4-05 **`NOT_RUN`** |
| Review-fix 状态 | **修复尚未创建/合入**（本轮快照分支 tip `dfda203` 仅为评审文档）。必须动作：P1-1 持久化 interview 阶段计划/修 `jd_ref@None`、P1-2 移走/隔离 `reference_answers.json` 且泄漏扫描不剥离 `canonical_response`、P1-3 实现 session replay + event/policy 版本拒绝（或降级文档声明）；P2-1/P2-5 建议同批修 |
| 关键限制 | 重启后阶段漂移；E2E 以 hidden 参考回答作为 learner 输入（答案键循环性）；无复核队列/审计事件；`scoring_spec_ref` 暴露 hidden 路径；阈值 `UNCALIBRATED`；真实学习效果 `NOT_VERIFIED` |

### 2.7 B-PR5 — 统一 E2E、证据包与最终评测入口

| 项 | 内容 |
|---|---|
| 目标 | 新统一 E2E/demo；证据包收集器（append-only audit index）；评测协议/报告模板；最终独立评测入口 |
| 关键文件 | `scripts/m1b/collect_evidence.py`、`docs/M1_B_EVIDENCE_PACKET.md`、`docs/M1_B_EVALUATION_REPORT_TEMPLATE.md`、`tests/m1_teacher/test_evidence_collector.py`；E2E 相关：`m1_teacher/demo_b4.py`、`tests/m1_teacher/test_b4_e2e.py` |
| 新增测试 | **14**（evidence collector；当前快照新增）；B4 E2E 9 个在 PR4 范围内已计入 |
| 证据命令/输出 | final tree `pytest tests/m1_teacher -q`（clean TMPDIR）→ **`938 passed in 102.76s`**；strict `M1B_REQUIRE_OS_SANDBOX=1 -q -rs` → **938 passed / 0 skipped**；collector final entries 见 `docs/m1b_evidence/audit-index.jsonl`（append-only；旧 smoke 记录保留）；包结构 = `README.md + audit-index.jsonl + audit-index.json + raw/<run_id>/{evidence.json,stdout.log,stderr.log}` |
| 评审文档/结论 | **最终树评测报告已产出（`docs/M1_B_EVALUATION_REPORT.md`，FINAL_TREE_MEASURED）**；B5-01 最终独立评审 `PENDING`（Lead 指派）；默认结论仅当全部门通过时才允许 `PASS_FOR_M1B_OFFLINE_INTEGRATION_SCOPE`；测评协议 `docs/M1_B_EVALUATION_PROTOCOL.md`（分支 `b-next/pr5-eval-protocol@09e1dd9`，DESIGN）。**B5-01 = `NOT_RUN`** |
| 关键限制 | 收集器只记录“命令执行事实”，`EXECUTED_PASS` ≠ 产品 PASS；未知 `evidence_class` 默认 `NOT_VERIFIED`；collector 不是沙箱；网络隔离需 Reviewer 环境负责；最终报告不能预填 PASS |

---

## 3. 信任边界摘要（B-PR1）

### 3.1 组件与数据流

- **T1 `TrustedJudgeSupervisor`**：唯一持有 hidden expected 与最终 verdict；只向 worker 发送 `code/function_name/args`；对 worker 返回做严格 schema + canonical 比较，任何未知字段/伪造 `passed/verdict` → `JUDGE_INFRA_ERROR`。
- **T2 `UntrustedExecutionWorker`**：在 bwrap 内执行 learner code；响应只允许 `actual_canonical/status` 等 6 字段，**无 passed/verdict/score/expected**；stdout/stderr 只作 excerpt。
- **T3 vertical**：`VerticalAssets` 只含 teacher-visible 内容（LIGHT/INVARIANT/STRUCTURE hint；FULL 不进默认导出，仅受限引用）。
- **默认策略**：`DeterministicScorer` 对 CODE 默认返回 `EVAL_ERROR:UNTRUSTED_CODE_EXECUTION_BLOCKED`，不执行、不调用 worker、mastery 不变；demo/CLI 无请求级开关；trusted fixture 能力只来自可信构造参数（P1-01）。
- **沙箱冻结命令（实现与威胁模型 §4.1 一致）**：`bwrap --unshare-all --die-with-parent --new-session --clearenv --cap-drop ALL`，只读挂载最小 rootfs，`--proc /proc --dev /dev`，私有 tmpfs，uid/gid 65534，`--hostname`；无 `--share-net`、无 `--dev-bind`、无宿主目录；canary 自检失败即 `JUDGE_SANDBOX_UNAVAILABLE`（fail-closed）；rlimits + 墙钟超时 + 进程组 SIGKILL + 有界输出。
- **证据缺口**：本机以 root 启动 bwrap，沙箱内 uid 65534 映射宿主 0 → “独立非 root OS principal”**未满足**；`M1B_REQUIRE_NONROOT_SANDBOX=1` 启动校验在 PR1 修复分支实现，但目标部署非 root 复跑 **`NOT_RUN`**。

### 3.2 B1-01…B1-06 状态（独立评审口径 + 修复分支）

| case | 状态 | 依据/限制 |
|---|---|---|
| B1-01 Untrusted code blocked | **VERIFIED (LOCAL_ONLY)** | 默认 scorer/supervisor/engine 全 blocked；无 worker 调用、快照不变；真实用户 CODE 仍 **BLOCKED** |
| B1-02 Hidden expected isolation | **VERIFIED (LOCAL_ONLY)** | worker 调用字段最小化；帧/argv/env/FS/宿主路径探针无 expected；112/112 hidden cases 通过 |
| B1-03 Result forgery | **VERIFIED (LOCAL_ONLY)** | 12 协议伪造 + 6 内存伪造 + 真实协议 fd 伪造均非 PASS；P2：可伪造 INFRA/RAISED 抑制学生证据（不能伪造 PASS） |
| B1-04 Judge confinement | **PARTIAL** | uid/gid 65534、pid/net/uts/ipc、ro FS、tmpfs、rlimit、超时、无残留、fail-closed 已测；宿主 uid_map 65534→0、非 root principal 与目标部署 `NOT_RUN`；启动强制在修复分支（`550ad37`）待合入/复评 |
| B1-05 Correctness | **PARTIAL → 修复分支自述 CLOSED** | 112/112、WA/RE/TLE（0.5s）、determinism；默认 2.0s 死循环曾误判 INFRA（P1-1），修复 `8175233` 后自述默认 TLE 正确（`OWNER_REPORTED`，待独立复评/合入） |
| B1-06 Hidden leakage scan | **VERIFIED (LOCAL_ONLY)** | result/history/CLI/demo 运行时扫描无 sentinel；P2 残余：`spec-sha256:<16>` 元数据与 `ASSESSED.item.scoring_spec_ref` 路径（PR4 P2-1）、`demo_b4.py` 读 scoring 目录（PR4 P1-2） |

### 3.3 安全 CI gate 现状

- 当前快照 **不含** `M1B_REQUIRE_OS_SANDBOX` 实现（`grep` 命中 0）；普通 `pytest` 在 bwrap 不可用时仍会 skip OS 动态证据。
- PR1 修复 `scripts/m1b/run_safety_ci.sh` **已合入 final tree**：默认要求 `M1B_REQUIRE_OS_SANDBOX=1`/非 root 断言，并跑 `pytest tests/m1_teacher -q -rs`；本报告 final tree 用 `M1B_REQUIRE_OS_SANDBOX=1 ... -q -rs` 实测 **938 passed / 0 skipped**。`.github/workflows` 的实际 job 接线仍由维护者/CI owner 负责（本报告不声称仓库 CI 已接线）。
- PR1 修复分支自述：修复树 `709 passed`；缺 bwrap 模拟下 0 skipped、fail 而非 skip（`OWNER_REPORTED`，待独立复评）。

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
- **单写者**：`SqliteRepository.commit_teaching_turn` 是唯一教学提交入口；端口/vertical 不注入 repository（PR2 权责矩阵 + PR4 测试）。
- **一致性边界**：scorer **at-least-once**（可重跑），state **exactly-once**（唯一终态/唯一 mastery）；`recover_session()` 幂等（重复恢复 0 events）。

### 4.2 崩溃/恢复证据（PR2）

- 真实 `SIGKILL` failpoints 覆盖 W1/W2/W3/W3b 前后；PR2 Reviewer 复跑 matrix 32 行 ×2 轮一致：9 rolled_back / 21 prepared / 2 committed，全部 `verify_rebuild=True`，聚合 hash `77c62048e9c34a12` / `ec99d57baf55a6e6` / `bbd500fbb1ca734b`。
- B2-01/02/03 + B-Q2 均 **VERIFIED**（进程 kill 语义）；断电持久性 `UNVERIFIED`，多机/分布式 `NOT_RUN`。

### 4.3 Scoped 幂等（PR3）

- 作用域：`(learner_id, session_id, item_id, turn_id, result_id)` + request digest；同 token 同 payload 幂等（唯一 result、零附加 event、mastery 一次）；同 token 不同 payload → `IDEMPOTENCY_CONFLICT`；跨 learner/session 同 token 不可读旧结果。
- **schema v2（add-only）**：`SCHEMA_VERSION = 2`；`result_scopes` 表 + `idx_result_scopes_scope`/`idx_result_scopes_session`；`CREATE ... IF NOT EXISTS` 幂等；v1→v2 migration 从 append-only legacy events backfill 元数据；`supports_scoped_idempotency()`；scope 行与教学提交同事务；v2 DB forward-only（旧构建 fail-closed）。
- B3-01/B3-02 **VERIFIED**；Reviewer P1-1（结构化 legacy digest 投影）与 P1-2（`LearningHistory.apply_assessment()` 仍全局 `get_event`，跨 learner 静默丢弃不泄漏）修复在 `3ad85c2`/`a5373f1`，**待合入/复评**。
- 当前快照没有跨 learner 泄漏证据；但最终 Reviewer 必须复跑 B3 负例（协议 B3 门）。

---

## 5. 双域统一闭环摘要（B-PR4 / B4-01…B4-03）

| case | 状态 | 证据摘要 | 限制 |
|---|---|---|---|
| B4-01 统一 CF 闭环 | **VERIFIED（E2E-MOCK + DETERMINISTIC）** | 同一 SQLite、两 learner、canonical mastery/journal；不同 action/mastery 路径；各自 `verify_rebuild` 通过；CF 动作有 Reason code | 合成学生；非真实学习效果 |
| B4-02 Interview 闭环 | **VERIFIED（会话内，E2E-MOCK）** | 5 阶段固定顺序；LearnerState 加速；`ASK_CLARIFICATION` 不编造；4 维 rubric + digest；JD v1/v2 新 session 隔离；无 FULL | 重启后阶段漂移（P1-1）；E2E 以 hidden 参考回答作为 learner 输入（P2-5） |
| B4-03 Freshness/JD 门禁 | **VERIFIED（E2E-MOCK）** | KEEP2/UPDATE2/RECHECK5；5 个 RECHECK（conflict/expired/future/older/un authoritative）与 4 类 JD 门（expired/not-yet-active/conflict/unknown）全部写入前拒绝，0 event/0 session/0 goal，显式 MAP-E08/E09/E10；eligible UPDATE 进新 plan refs | 无持久复核队列/审计事件（P2-2）；无真实抓取/调度 |

- **JD v1→v2**：同一 learner 在两个时间点分别开 session，`SESSION_STARTED.vertical.jd_version` 分别为 `v1`/`v2`；先开的 session objective/计划不变（只影响新计划）。
- **freshness 门禁**：启动前 fail-closed（`FRESHNESS_JD_GATE_BLOCKED` / `FRESHNESS_KNOWLEDGE_GATE_BLOCKED`，details 带 `map_code` 与 `reason_code`）；被拒尝试零静默写入；`UPDATE+VERIFIED+权威层` 才可进 `PLAN_CREATED.payload.vertical.knowledge_refs`。
- **统一事件/Replay**：所有域写同一 `history_events`（跨 session seq 连续、snapshot 不变、`verify_rebuild` 通过）；**Replay 目前只重建 learner snapshot，不重建 session phase/pending/action**；事件 `schema/domain/policy` 版本拒绝（MAP-E12/E13）未实现——PR4 P1-3 要求实现或降级声明。
- **demo/E2E**：`python -m m1_teacher.demo_b4 --json` 双跑逐字节相同，`sha256=6b7bb66e…`（15,108 bytes）；`test_b4_e2e.py` 9 tests；B4-04 仅部分覆盖（CF→Interview→CF；interview 重启不成立）、B4-05 **`NOT_RUN`**。

---

## 6. 证据与复跑

### 6.1 环境（本轮文档作者）

- 工作区 `/root/m1b/pr5docs`；`/root/Autonomous Teacher/.venv/bin/python`（Python 3.11.15 / pytest 9.2.0 / ruff 0.17.5）；Linux（bubblewrap 0.9.0 可用）；无网络、无 Key、无 Provider；所有 fixtures synthetic/CC0。
- 因为共享 `/tmp` 存在先前运行的 `m1b_judge_worker_*` 残留，**本轮全量命令需设置私有 `TMPDIR`**：
  `TMPDIR=$(mktemp -d) pytest tests/m1_teacher -q -p no:cacheprovider`。

### 6.2 历史快照（`e2b6e85`）复跑记录（保留供审计；最终树数字见 §6.5）

| # | 命令（cwd=`/root/m1b/pr5docs`） | 本轮实测 | 标签 |
|---|---|---|---|
| O-01 | `pytest tests/m1_teacher --collect-only -q` | 旧快照 `873 tests collected`；final tree **938 collected** | OWNER_REPORTED |
| O-02 | `TMPDIR=$T pytest tests/m1_teacher -q -p no:cacheprovider` | 旧快照 `873 passed in 84.51s`；final tree **`938 passed in 102.76s` / strict `938 passed 0 skipped`** | OWNER_REPORTED |
| O-03 | 默认 `/tmp` 同命令（未清理残留） | `4 failed, 869 passed in 89.24s`；失败 = 3×`test_judge_negatives`（`test_attack_templates_never_pass_and_never_leak_sentinels` / `test_attack_timeout_and_fork_are_killed_without_host_leftovers` / `test_ephemeral_tmpfs_write_has_no_host_effect`，均为临时目录清理断言）+ 1×`test_judge_worker.test_worker_timeout_is_bounded_and_cleaned_up`；`test_judge_sandbox.py -q` 单独跑 `11 passed in 0.77s` | OWNER_REPORTED（环境假失败，**不得**当作产品 PASS 或产品失败） |
| O-04 | `python -m m1_teacher.demo` ×2 + `cmp` + `sha256sum` | 逐字节相同；`b08ceee915fb…d491b`；53 行 | OWNER_REPORTED |
| O-05 | `python -m m1_teacher.demo_b4 --json` ×2 + `cmp` + `sha256sum` | 逐字节相同；`6b7bb66e36a3…bef83`；511 行 / 15,108 bytes | OWNER_REPORTED |
| O-06 | `python scripts/m1b/collect_evidence.py --out /tmp/m1b_evidence_smoke --case-id SMOKE-CONTRACTS --command "… pytest tests/m1_teacher/test_contracts.py -q" --evidence-class DETERMINISTIC` | `EXECUTED_PASS`；raw evidence `sha256=37d63c10…0befeb`；`audit-index.jsonl sha256=639dd18c…9b42d2` | OWNER_REPORTED（smoke；不是验收证据） |
| O-07 | `ruff check m1_teacher tests/m1_teacher` | `All checks passed!` | OWNER_REPORTED |
| O-08 | `git diff --name-only 4706250..HEAD` + 路径过滤 | 100 文件；全部 `docs/ fixtures/ m1_teacher/ tests/m1_teacher/ scripts/m1b/`；`NO_OUT_OF_SCOPE_PATHS` | OWNER_REPORTED |
| O-09 | `grep -RInE "autoteacher_m0\|import (httpx\|requests\|aiohttp\|urllib.request)" m1_teacher` | `NONE` | OWNER_REPORTED |
| O-10 | `M1B_REQUIRE_OS_SANDBOX=1 pytest tests/m1_teacher -q -rs`；`scripts/m1b/run_safety_ci.sh` | **final tree 已实现并实测：`938 passed in 102.95s`，0 skipped**（旧 e2b6e85 快照为 `NOT_CONFIGURED`，历史） | OWNER_REPORTED（final tree） |

### 6.3 历史冻结参考（只引用，不相加；最终 Reviewer 必须独立重跑并保留标签）

| 线 | 冻结点 | 历史命令 | 历史结果 | 标签 |
|---|---|---|---|---|
| M1-A `m1_teacher` | `4706250`（`m1a.v0`；M1-A 独立 Review `PASS_FOR_M1A_OFFLINE_MVP`） | clean archive 后 `pytest tests/m1_teacher -q` | `536 passed`（Reviewer 在 PR2 评审 E8 独立确认 `536 passed in 16.41s`）；demo `b08ceee9…`，53 行；evidence `171cc654…`/`5e84229e…`/`23b871a3…`（历史） | `HISTORICAL_FROZEN` |
| M1-Offline `m1_offline` | `290c577`（`m1.offline.v0`；Review clean C2） | `/root/at-m1-offline` 冻结树 `pytest tests/m1_offline -q -p no:cacheprovider` | `365 passed`；demo 历史 `1d57ca62…`（上下文相关） | `HISTORICAL_FROZEN`（本轮 **未重跑**；B 线不在当前树） |

> **禁止**：`536 + 365 = 901` 不是任何真实套件，也不存在“统一 901”；最终 B 集成套件 `938`（PR4 final 913 + PR5 25；含历史 M1-A 536 基线）是**本树**数字，不能与 365 相加。

### 6.4 证据包（B-PR5 交付）

- 收集器：`scripts/m1b/collect_evidence.py`（append-only `audit-index.jsonl` + 派生物化视图 `audit-index.json` + `raw/<run_id>/`；`--command` 必填才可能 `EXECUTED_PASS`，无 hash 记录永远不是证据）。
- 格式与校验：`docs/M1_B_EVIDENCE_PACKET.md` §2/§3/§7（索引字段、状态语义、哈希/append-only/无 hashless-PASS 校验脚本、物化视图重建）。
- 建议最终包位置：`/root/m1b_evidence/B5-01/`（由 Reviewer 在冻结 SHA 上运行收集器生成；最终位置以 Reviewer 报告为准）。每个 C 行必须登记 `case_id/command/environment/exit_code/raw_evidence_path/sha256/limitation`。
- 状态语义：`EXECUTED_PASS` 仅表示命令退出 0；`NOT_RUN` 必须有 reason；`evidence_class` 默认 `NOT_VERIFIED`，需 Reviewer 显式标注。

### 6.5 最终数字（FINAL_TREE_MEASURED）

最终集成树 = PR4 final `1de6ae6d3714ab815c47022e4c2cceee107db979` 合入 PR5 后的 merge commit `861d147d…`；B5 实现提交 `c420d19…`；PR5 最终 commit SHA 由本报告 commit 后回填（`git rev-parse b-next/pr5-e2e-eval`）。最终数字：

- `pytest tests/m1_teacher -q`（clean TMPDIR）→ **938 passed in 102.76s**；strict `M1B_REQUIRE_OS_SANDBOX=1 -q -rs` → **938 passed in 102.95s，0 skipped**；
- 定向：B5 11 / B4 9 / B4 durability 9 / judge certification 33（112/112） / crash 35 / collector 14；ruff clean；
- 最终 counts/hashes/证据包详见 `docs/M1_B_EVALUATION_REPORT.md` §13；B5 独立评审 `PENDING`（Lead 指派），本报告不预填 PASS；
- 若 LeadB/维护者另指定独立评审文档（如 `docs/M1_B_INDEPENDENT_REVIEW.md`），以该指定为准，但最终报告必须引用本实现报告与证据包；
- 旧 `e2b6e85` 过渡快照数值仅供历史参考；final tree 以 **938 passed / strict 0 skipped** 为准（`docs/M1_B_EVALUATION_REPORT.md` §13）。

---

## 7. 失败、限制与未验证项（必须原样保留）

| # | 项 | 状态/原因 | 来源 |
|---|---|---|---|
| 1 | 真实学习收益/教学效果 | **`NOT_VERIFIED`**：全部为确定性启发式 + synthetic 输入 | PR4 评审 §9；DOMAINS §6 |
| 2 | 真实 Provider/联网/付费/LiveGate | **`BLOCKED`**：无 Key/网络；人类 Gate 未开 | 评估协议 §10/§12；PR1 评审 |
| 3 | 真实用户 CODE 开放 | **`BLOCKED`**：需人类批准 + 目标部署安全验收 | PR1 评审/附录 |
| 4 | 非 root 部署 principal | **`NOT_RUN`**：本机 root + uid_map 65534→0；启动 fail-closed 仅在 PR1 修复分支 | PR1 附录 §3.2 |
| 5 | 安全 CI job（`.github`） | **`NOT_CONFIGURED/NOT_RUN`**：仓库无测试/security workflow；修复分支只有 `run_safety_ci.sh` | PR1 附录 §3.3；本轮 grep |
| 6 | 断电持久性 | **`UNVERIFIED`**：仅进程 SIGKILL 矩阵 | TXN 文档/PR2 评审 |
| 7 | 分布式/多主机并发 | **`NOT_RUN`**：仅单机单文件 | PR2 评审 B2-03 |
| 8 | `FULL_SOLUTION` / 人工复核队列 | 结构上不可达（fail-closed），但**无持久 review queue/审批 UI**；FULL 内容仅在受限引用 | PR4 评审 P2-2/P2-7；DOMAINS §9 |
| 9 | Session Replay / 事件版本拒绝 | 仅 snapshot replay；session replay 与 MAP-E12/E13 **未实现**（PR4 P1-3） | PR4 评审 |
| 10 | 隐藏参考回答作为 E2E learner 输入 | 答案键循环性；不能作为评分真实性证据（PR4 P2-5） | PR4 评审 |
| 11 | `ASSESSED.item.scoring_spec_ref` 暴露 `scoring/` 路径 | hidden 路径元数据残留（PR4 P2-1/P1-2）；PR1 B1-06 残余 | PR4 评审 |
| 12 | `spec-sha256:<16>` evidence 元数据 | 单 case/低熵场景可作离线字典校验面（PR1 P2） | PR1 评审 |
| 13 | worker 可伪造 INFRA/RAISED | 不能伪造 PASS，但可抑制负面学生证据（PR1 P2） | PR1 评审 |
| 14 | 阈值（加速 0.25/证据 2、hint cap、interview ladder） | **`UNCALIBRATED`**：无真实数据校准 | DOMAINS §9 |
| 15 | B4-05 / 版本不兼容拒绝 | **`NOT_RUN`** | PR4 评审 §6 |
| 16 | 共享 `/tmp` 测试隔离 | 已用 `mktemp -d` 独立 TMPDIR 串行复跑：938 passed/0 skipped；最终 Reviewer 必须使用干净 TMPDIR/串行 | 本轮 final tree 实测；PR3 评审也记录同类 |
| 17 | PR1/PR2/PR3/PR4 review-fix 合入 | 已合入 final tree（PR4 final `1de6ae6d`；最终树 938） | 本报告 §6.5；PR4 review/response |
| 18 | PR5 独立评测 | Owner 最终树评测报告已产出；`B5-01` 最终独立评审 **`PENDING`（Lead 指派）** | `docs/M1_B_EVALUATION_REPORT.md` §13 |
| 19 | 文档残留 | ADR §5 “optional fields …” 与 P1-04 零 diff 原则措辞冲突；`docs/M1_ARCHITECTURE.md` §14 仍写 `schema_meta.version == 1`（实际 v2）；PR1/PR3/PR4 评审文档未合入树；PR1 附录文本仍列 P1-2/P1-3 未关闭（修复分支后补 commit 已实现，待复评/合入） | 本轮静态核对 |

---

## 8. 依赖、合并顺序与保护路径

### 8.1 Stacked 关系（B-PR0 → B-PR5）

| 层 | 分支 | 当前 tip（本轮核对） | 内容 | 在当前快照？ |
|---|---|---|---|---|
| PR0 | `b-next/pr0-convergence-adr` | `3001d99` | ADR/PORTS/CI/docs + 预审响应 | 是 |
| PR1 impl | `b-next/pr1-judge-worker` | `fb6cf33`（+ worker `8d7ede6`、fixtures `0fd3ed4`） | supervisor/worker/sandbox/scorer 改造 | 是 |
| PR1 review | `b-next/pr1-review` | `62c32c5` | 独立安全评审（PASS_WITH_ACTIONS） | 否（文档在分支） |
| PR1 fixes | `b-next/pr1-trusted-judge` | `550ad37`（含 `8175233` + 附录 `af09cff`） | P1-1..P1-4/P2 修复 + 安全 CI 脚本 + 启动 fail-closed | **否 → 待合入** |
| PR2 | `b-next/pr2-session-txn` | `7f9ce06`（含 `10fdaa9` 修复 + PR1 早期修复） | 事务/恢复/幂等 | 是（`10fdaa9` 在树） |
| PR3 impl | 合并于 PR2/PR3 分支 | `18b08fe`/`2f32f13`/`3103a06` | scoped 幂等 + schema v2 | 是 |
| PR3 review/fix | `b-next/pr3-review` / `b-next/pr3-scoped-idempotency` | `db636ea` / `a5373f1`（含 `3ad85c2`） | 评审 PASS_WITH_ACTIONS；P1 修复 + legacy fixture | **否 → 待合入** |
| PR4 impl | `b-next/pr4-interview-freshness` / `b-next/pr4-domain-ports` | `e265b96` / `dfda203`（评审文档） | vertical ports / interview / freshness / B4 E2E | 是（实现 via `11a4f72`） |
| PR4 review/fix | `b-next/pr4-review` | `dfda203` | PASS_WITH_ACTIONS（P1=3）；**fix 未创建** | **否 → 待修复合入** |
| PR5 | `b-next/pr5-e2e-eval` / `b-next/pr5-docs` | `e2b6e85` | 证据收集器 + 模板 + 统一 E2E + 合并栈 | 是（当前快照） |
| PR5 eval protocol（未合入） | `b-next/pr5-eval-protocol` | `09e1dd9` | 测评协议 DESIGN | **否** |
| 最终评测 | final tree (`861d147`/`c420d19`) | **`FINAL_TREE_MEASURED`** | `docs/M1_B_EVALUATION_REPORT.md` §13 + final evidence hashes | **已产生（Owner）；独立评审 PENDING** |

### 8.2 合并顺序与冻结

1. 合入 PR1 review-fix（`550ad37`）与评审/附录文档；
2. 合入 PR3 review-fix（`a5373f1`）与评审文档；
3. 完成并合入 PR4 三项 P1 修复 + 评审文档；
4. 合入 PR5 评测协议（`09e1dd9`）与最终证据/模板缺口；
5. 生成 **integration 分支**，clean archive 冻结 SHA；独立 Reviewer 按协议 §3/§4 跑 C 矩阵，填 `docs/M1_B_EVALUATION_REPORT.md`；
6. 只有全部门通过（G1–G8、无 STOP、B0-01..B5-01 与 X-01/02 完成）才允许 `PASS_FOR_M1B_OFFLINE_INTEGRATION_SCOPE`。

### 8.3 M0 保护路径零变更

- `git diff --name-only 4706250..e2b6e85` = 100 文件，全部位于 `docs/`、`fixtures/`、`m1_teacher/`、`tests/m1_teacher/`、`scripts/m1b/`；**没有** `src/autoteacher_m0/`、`security/`、`bridge/`、`config/g*`、`scripts/g4*`、LiveGate/账本/授权路径、`plugins/`。
- 本轮静态扫描：`m1_teacher` 无 M0 import、无网络库 import（`NONE`）；无真实 Key/Provider 调用；无 `.github` 变更。
- PR1 评审/PR4 评审/PR2 评审均独立核实过各自范围保护路径 0 变更。

---

## 9. 未决项汇总（交维护者/最终 Reviewer）

| 类别 | 项 |
|---|---|
| 必须人类批准 | 真实用户 CODE 开放（B-PR1 目标部署 + 人类批准）；真实 Provider/LiveGate；非 root 部署验收；G4-H/G5/M0 决策 |
| 最终评测前必须完成 | PR1/PR3/PR4 review-fix 合入；PR4 P1-1..P1-3；PR5 评测协议+最终报告；最终集成 SHA 冻结；C-01..C-16 独立复跑 |
| 文档清理 | ADR §5 可选字段措辞 vs P1-04；ARCHITECTURE §14 schema v1→v2；PR1/PR3/PR4 评审文档合入；PR1 附录状态与修复 commit 对齐 |
| 产品/测试缺口 | session replay + MAP-E12/E13；persistent review queue；FULL_SOLUTION 路径；hidden 参考回答从 E2E 输入移出；`scoring_spec_ref` opaque 化；共享 `/tmp` 测试隔离 |
| 最终裁定 | 见 `docs/M1_B_EVALUATION_REPORT.md`（Owner `FINAL_TREE_MEASURED`；独立 Reviewer `PENDING`）；本报告不预填 PASS，不把 `MOCK/DETERMINISTIC` 结果写成真实效果 |

---

## 10. 变更记录

| 日期（UTC） | 版本 | 变更 |
|---|---|---|
| 2026-11-20 | v0 | 初稿：汇总 PR0–PR5 实现/证据/评审状态；当前快照 `e2b6e85`；最终数字标记 TBD |
| 2026-11-20 | v1 | PR4 final 合入后最终树实测：938 passed / strict 938 passed 0 skipped；final SHA `861d147` + B5 `c420d19`；证据包 final hashes；独立评审 PENDING；未改实现/测试/fixture |
