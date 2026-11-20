# M1-B 评测报告（B-PR5 最终树：统一 E2E + 独立测评证据）

| 字段 | 值 |
|---|---|
| 报告状态 | **FINAL_TREE_MEASURED（Owner 执行侧最终树实测）；独立 Reviewer 最终裁定待 Lead 指派 Reviewer 出具** |
| 报告版本 | `m1b.eval-report.v1`（2026-11-20 UTC） |
| 工作区 / 分支 | `/root/m1b/pr5` / `b-next/pr5-e2e-eval` |
| 最终集成树 | PR4 final `1de6ae6d3714ab815c47022e4c2cceee107db979`（`b-next/pr4-domain-ports`）合入 PR5 后的 merge commit **`861d147d…`**（`git rev-parse` 见 §13）；PR5 B5 实现提交 **`c420d19…`**；**PR5 最终 commit SHA 在本文档所在 commit 完成后由 Lead/报告回填**（文档不能引用自身 commit SHA；最终以 `git rev-parse b-next/pr5-e2e-eval` 为准） |
| 主基线 | `3e7afee077845a071cd364e93ab209cac20b2d5f` |
| 环境 | 干净 `TMPDIR=$(mktemp -d)`（串行、无并发测试）；Linux 6.17.13-2-pve；Python 3.11.15（`/root/Autonomous Teacher/.venv/bin/python`）；pytest 9.2.0；bubblewrap 0.9.0；TZ=UTC；PYTHONHASHSEED 由 collector 记录 |
| 证据包 | `docs/m1b_evidence/audit-index.jsonl`（append-only，含历史 16 条过渡快照记录 + 最终树条目；旧 EXECUTED_FAIL/NOT_RUN 记录保留） + `raw/**` + `e2e_b5_*.jsonl` + `e2e_b5_summary.json` |
| 证据标签 | 本报告为 `OWNER_REPORTED` + `DETERMINISTIC`（Owner 本地真实命令/哈希）；各 PR Reviewer 结论标 `REVIEWER_REPORTED`（引用其报告）；B-PR5 独立评审 = `PENDING`（Lead 指派）；`B4-01/02/03` 已由 PR4 独立评审 `VERIFIED` |
| 边界 | **Offline synthetic only, not real teaching effect.** 不构成真人学习收益、真实 Provider/网络/Live/生产授权；不改变 M0 G4-H/G5/LiveGate/M0 决策 |

---

## 0. 裁定摘要（最终树 + 引用的 Reviewer 状态）

| 项 | 状态 | 来源/证据 |
|---|---|---|
| M1-A 历史冻结 | `PASS_FOR_M1A_OFFLINE_MVP`（536 tests @ C6 `3010426…`） | `REVIEWER_REPORTED`：`docs/M1_INDEPENDENT_REVIEW.md`（历史引用） |
| M1-Offline 历史冻结 | `PASS_FOR_M1_OFFLINE_DESIGN_AND_EVALUATION_SCOPE`（365 tests @ C2 `052d980d…`） | `REVIEWER_REPORTED`：M1-Offline `REVIEW_M1_OFFLINE.md`（不在本树，历史引用） |
| B-PR0 预审 | `PRE_REVIEW_PASS_WITH_ACTIONS`（P0=0 / P1=8 / P2=13；B0-01 仍 `NOT_RUN`） | `REVIEWER_REPORTED`：`docs/M1_B_BOUNDARY_PRE_REVIEW.md`、`docs/M1_B_PR0_REVIEW_RESPONSE.md` |
| B-PR1 安全评审 | `PASS_WITH_ACTIONS` → 修复复核 `P1_ACTIONS_PARTIALLY_CLOSED`（P1-1/P1-4 `CLOSED`；P1-3 CI gate 已合入（`scripts/m1b/run_safety_ci.sh` + `tests/m1_teacher/judge_os_gate.py`，strict 938 passed/0 skipped）；P1-2 非 root principal `NOT CLOSED`） | `REVIEWER_REPORTED`：`docs/M1_B_PR1_REVIEW.md`、`docs/M1_B_PR1_REVIEW_ADDENDUM.md`；final tree 含修复 |
| B-PR2 事务评审 | `PASS_WITH_ACTIONS`；B2-01/02/03 + B-Q2 `VERIFIED`；review-fix tree 已合入（goal failpoint/D12 记录等） | `REVIEWER_REPORTED`：`docs/M1_B_PR2_REVIEW.md`；final tree = PR4 final 合入树 |
| B-PR3 幂等评审 | `PASS_WITH_ACTIONS`；B3-01/02 + B-Q3 `VERIFIED`；review-fix tree 已合入（legacy digest/公共 API scoped 查找等） | `REVIEWER_REPORTED`：`docs/M1_B_PR3_REVIEW.md`；final tree 含修复 |
| B-PR4 独立评审 | `PASS_WITH_ACTIONS`（P0=0 / P1=3 / P2=7）；B4-01 `VERIFIED`、B4-02 `VERIFIED`（重启计划持久化修复后）、B4-03 `VERIFIED`（E2E-MOCK）；响应 `M1_B_PR4_REVIEW_RESPONSE.md` 记录 P1-1..P1-3 关闭（P1-3 event-level schema 版本 = PARTIAL 明示） | `REVIEWER_REPORTED`：`docs/M1_B_PR4_REVIEW.md` + 响应文档；final tree 含修复 |
| B-PR5 统一 E2E/评测 | Owner 最终树实测完成（本报告）；`B5-01` 最终独立评审 **`PENDING`（Lead 指派）** | Owner 最终树证据包；独立评审未出 |
| X-01 无范围漂移 | Owner 侧 `DETERMINISTIC` 检查通过（final diff vs main = **235 files**；保护路径 **0 命中**） | collector entry `X-01-scope-diff`（final 条目）；Reviewer 需重跑 |
| X-02 无 Key/网络/付费 | Owner 侧 `DETERMINISTIC` 检查通过（网络 import **0**；`autoteacher_m0` 仅隔离断言/注释；无 Key/Provider；LiveGate 仍 BLOCKED） | collector entry `X-02-network-scan`（final 条目）；Reviewer 需重跑 |
| **Owner 侧最终结论** | **`PENDING_INDEPENDENT_REVIEW`**（所有本地门通过；独立 Reviewer 关闭 B-PR5/B5-01 后，默认只允许 `PASS_FOR_M1B_OFFLINE_INTEGRATION_SCOPE`） | 本报告 §10/§11/§13 |

---

## 1. 方法与独立性

- 本报告命令全部由 Owner 在**最终集成树的干净 `TMPDIR`**中真实执行（串行、无其它测试并发）；原始 stdout/stderr 摘要、exit code、环境、sha256 见 `docs/m1b_evidence/raw/<run_id>/`，执行记录见 `docs/m1b_evidence/audit-index.jsonl`。
- 引用各 PR Reviewer 结论时标 `REVIEWER_REPORTED`；**不冒充本轮独立复跑**。B-PR5 的 `INDEPENDENTLY_REEXECUTED` 保持 `PENDING`，等待独立 Reviewer。
- 所有教学/学生/面试/JD/知识数据均为 synthetic fixtures（`hidden=false` teacher-visible learner script / synthetic JD/resume）；无真实个人数据、无网络/API Key/Provider/LiveGate。
- 历史 `536`（M1-A）与 `365`（M1-Offline）只作各自分支历史冻结参考，**未相加**；最终套件独立计数（§3）。

## 2. 环境

| 项 | 值 |
|---|---|
| TMPDIR | `mktemp -d` 独立目录（每个 run 独立；无并发测试） |
| OS | Linux `6.17.13-2-pve`（x86_64） |
| Python / pytest | 3.11.15 / 9.2.0（`/root/Autonomous Teacher/.venv/bin/python`） |
| bubblewrap | 0.9.0（PR1 OS 沙箱动态测试可运行） |
| TZ / LANG / LC_ALL | `UTC` / `C.UTF-8` / `C.UTF-8` |
| 网络 / Key / Provider | 无（AST 扫描 0 网络 import；collector 子进程 env 剥离凭据；未配置 provider） |

## 3. 最终集成套件实测（938 tests，clean TMPDIR）

### 3.1 全量命令与输出

```bash
cd /root/m1b/pr5
export TMPDIR=$(mktemp -d)
PY="/root/Autonomous Teacher/.venv/bin/python"
"$PY" -m pytest tests/m1_teacher -q
# exit 0 -> 938 passed in 102.76s (0:01:42)          [collector final: B5-01-full-suite]
M1B_REQUIRE_OS_SANDBOX=1 "$PY" -m pytest tests/m1_teacher -q -rs
# exit 0 -> 938 passed in 102.95s (0:01:42); 0 skipped  [collector final: B1-05-os-sandbox-gate]
"$PY" -m ruff check m1_teacher tests/m1_teacher
# All checks passed!
```

### 3.2 计数构成（独立计数；历史数字不相加）

| 来源 | tests | 说明 |
|---|---:|---|
| M1-A 历史基线（含于 final tree，未改） | 536 | `REVIEWER_REPORTED` 历史冻结参考；`tests/m1_teacher` 中仍全通过 |
| PR4 final 树（`1de6ae6…`） | 913 | Lead 冻结值；含 PR1/PR2/PR3 review-fix tree 与 PR4 final（913 = 536 + 377 PR1/PR2/PR3/PR4 新增/修复测试） |
| B-PR5 新增（PR5 分支） | 25 | B5 统一 E2E `test_b5_e2e` 11 + 证据收集器 `test_evidence_collector` 14 |
| **最终集成套件合计** | **938** | 913 + 25 = 938；`pytest --collect-only` 确认 938 |
| M1-Offline 历史冻结（另一分支） | 365 | `REVIEWER_REPORTED` 历史；**不在本树、未合并、不得相加**（无“901”） |

### 3.3 定向实测（最终树）

| 命令 | 实测 |
|---|---|
| `pytest tests/m1_teacher/test_b5_e2e.py -q` | **11 passed in 13.04s** |
| `pytest tests/m1_teacher/test_b4_e2e.py -q` | **9 passed in 4.76s** |
| `pytest tests/m1_teacher/test_b4_durability_replay.py -q` | **9 passed in 0.91s** |
| `pytest tests/m1_teacher/test_judge_correctness.py -q` | **33 passed in 21.27s**（14/14 参考解、hidden 112/112、负例分类） |
| `pytest tests/m1_teacher/test_crash_recovery.py -q` | **35 passed in 14.88s**（真实 SIGKILL crash matrix） |
| `pytest tests/m1_teacher/test_evidence_collector.py -q` | **14 passed in 1.28s** |
| `ruff check m1_teacher tests/m1_teacher` | `All checks passed!` |

> 过渡快照（`e2b6e85`+PR5 前次提交）的 884 tests 数值仅保留在 git 历史与旧 evidence 记录中；本报告最终数字以 938 为准。

## 4. B-PR5 统一 E2E 实测结果（最终树）

命令：`python -m m1_teacher.e2e_b5 --write-evidence`（exit 0；两次运行 stdout 与全部 evidence 字节一致）。

| 段 | 实测 |
|---|---|
| **CF（B4-01）** | `student_a`：7 CORRECT / 1 INCORRECT，binary mastery `0.30 -> 0.543571`，75 events，`verify_rebuild=True`；`student_b`：3 INCORRECT / 4 NEEDS_REVIEW，binary `0.00`，65 events，`verify_rebuild=True`；`paths_differ=True`；同一 SQLite journal |
| **Interview（B4-02）** | 2 learners：A（seeded 3 CORRECT = accelerated）v1 session probes `hypothesis→complexity→experiment_design→online_triage`（concept skip，4 probes）、final REVIEW；v2 新 JD session probes 0、hint L1、final ASSESS（新会话仅起头）；B（novice）完整 5 阶段 `concept→hypothesis→complexity→experiment_design→online_triage`、`ASK_CLARIFICATION` 1 次、interview hint `[1]`（FULL 从未出现）、rubric 4 维（`engineering_feasibility/evidence_sufficiency/explanation_clarity/factual_correctness`）、final REVIEW |
| **JD v1→v2** | `jd:rec` v1 session（27 events，REVIEW，journal sha256 `554c1153…`）在 v2 session 创建后**完全不变**；`affects_running_sessions=False`、`affects_new_plans=True`、`reason_code=JD_CHANGE_NEW_PLANS_ONLY`；旧 session before/after fingerprint 相等 |
| **跨域（同一 learner）** | CF 暂停于 turn 4 → interview session（2 sessions，domains `["cf_binary_search","interview_coach"]`）→ resume CF → final REVIEW；per-learner seq 连续、`verify_rebuild=True`、snapshot 同时含 `cf.*` 与 `interview.*` 节点；interview clarifications=1、jd=v2 |
| **Freshness（B4-03）** | 9 knowledge 场景：KEEP 2 / RECHECK 5 / UPDATE 2；5 个 RECHECK（expired/conflict/unauthoritative/future-dated/older）全部 `rejected=True`、`events_written=0`、`FRESHNESS_KNOWLEDGE_GATE_BLOCKED` + MAP-E08/E09；3 个 JD 时间窗（expired/not-yet-active/overlap-conflict）全部拒绝、0 events、`FRESHNESS_JD_GATE_BLOCKED` + MAP-E10；2 个 eligible UPDATE 可进入新计划（events=4）；`silent_imports=0`、`gate_enforced=True` |
| **Unified journal** | 5 learners（2 CF + 2 interview + 1 cross-domain）；事件数分别 75/65/45/42/89；全部 `seq_contiguous=True`、`verify_rebuild=True`；单 SQLite 文件；事件类型含 `SESSION_STARTED/PLAN_CREATED/ACTION_TAKEN/TURN_ADVANCED/ASSESSED/MASTERY_UPDATED/...` |
| **确定性** | `python -m m1_teacher.e2e_b5` 双跑 stdout 逐字节一致：sha256 `4d0e0c851f4ff4d745127932aa62fcfabeca47da2f7d23ae434cae1ab300a2fc`（27 行）；`demo_b4 --json` 双跑一致 sha256 `6b7bb66e…`（511 行，PR4 final 评审已复跑）；`e2e_b5 --write-evidence` 双跑 5 文件 byte-identical |
| **Mock provenance** | 学生/面试回答来自 teacher-visible `fixtures/.../learner_scripts/answers.json`（`hidden=false`、synthetic CC0-1.0）；hidden reference/rubrics 仅由 `assessment/scorer.py`、`assessment/interview_judge.py` 读取（PR4 P1-2 守卫在 final tree 通过） |

B4 本地 E2E：`pytest test_b4_e2e.py -q` → **9 passed in 4.76s**（B4-01/02/03 本地 E2E-MOCK）。
B5 统一 E2E：`pytest test_b5_e2e.py -q` → **11 passed in 13.04s**。

## 5. B4 / B5 验收矩阵（最终树）

| case_id | 目标 | 最终状态 | 证据 |
|---|---|---|---|
| B4-01 | 双 CF learner 同 canonical mastery/session journal | **`VERIFIED`**（PR4 独立评审；Owner 最终树复跑一致） | `docs/M1_B_PR4_REVIEW.md` §1；final tree CF E2E 9 passed + `e2e_b5_cf.jsonl` |
| B4-02 | 双 interview learner + JD v1→v2 不同证据化计划 | **`VERIFIED`（会话内；重启计划持久化 P1-1 已修复并复评）** | `docs/M1_B_PR4_REVIEW.md`；`test_b4_durability_replay.py` 9 passed；`e2e_b5_interview.jsonl` |
| B4-03 | freshness 拒绝 expired/conflict/unauthoritative | **`VERIFIED`（E2E-MOCK；持久 review queue P2-2 明示未实现）** | `docs/M1_B_PR4_REVIEW.md`；final tree `gate_enforced=True`、`silent_imports=0` |
| B5-01 | Reviewer 独立重跑旧两套 + 新集成套件并标 mock provenance | Owner 最终树证据已完成；**独立评审 `PENDING`（Lead 指派 Reviewer）** | 本报告 + `docs/m1b_evidence/audit-index.jsonl`（final entries） |

> 所有 CF/interview 结果均为 MOCK 合成数据；状态机/回放/rubric 算术为 `DETERMINISTIC`；真实教学效果 `NOT_VERIFIED`。不得把本地绿色当作独立验收。

## 6. B1 / B2 / B3 状态（最终树 + Reviewer 引用）

| case_id | 目标 | 最终状态 | 残余限制 |
|---|---|---|---|
| B1-01 | untrusted CODE fail-closed，不可数据路径开启 | `VERIFIED (LOCAL_ONLY)`（PR1 review；final tree 含修复，strict 938/0 skipped） | 真实用户 CODE 仍 **BLOCKED** |
| B1-02 | hidden expected 不进入 worker 内存/argv/log | `VERIFIED (LOCAL_ONLY)` | target-deploy 复核 `NOT_RUN` |
| B1-03 | 不可信 worker 不能伪造可信 PASS | `VERIFIED (LOCAL_ONLY)` | 同上 |
| B1-04 | OS confinement：网络/宿主秘密/逃逸/资源 | **`PARTIAL`**（P1-2 非 root principal `NOT CLOSED`；本地 `LOCAL_ONLY`） | 非 root principal 目标部署 `NOT_RUN` |
| B1-05 | 判题正确性/可用性 | **`PARTIAL`**（112/112 hidden、33 passed；默认 TLE 分类 P1-1 已修复；目标部署 latency/resource 验收 `NOT_RUN`） | target-deploy latency/resource `NOT_RUN` |
| B1-06 | hidden 泄漏扫描 | `VERIFIED (LOCAL_ONLY)`（final tree `test_hidden_leakage_scan` 15 passed；B5 证据无 hidden 内容） | target-deploy 运行时导出复核 `NOT_RUN` |
| B2-01/02/03 | 原子 turn commit / crash replay / 并发语义 | `VERIFIED`（PR2 review；final tree 含 review-fix；crash 35 passed） | P2 项（恢复 ERROR 事件等）记录于 PR2 review |
| B3-01/02 | scoped result_id / 跨 learner 隔离 | `VERIFIED`（PR3 review；final tree scope migration 15 + scoped 31 passed） | P2 项记录于 PR3 review |

## 7. X-01 / X-02 结果（最终树 Owner 侧）

| case_id | 检查 | 命令 | 实测（Owner） | 标签 |
|---|---|---|---|---|
| X-01 | M1 提交不修改 `src/autoteacher_m0/`、`security/`、`bridge/`、`config/g*`、`scripts/g4*`、LiveGate；A 线不改 M1 | `git diff --name-only 3e7afee..HEAD` + 保护前缀 grep | **235 files** changed；保护路径 **0 命中**（NO_PROTECTED_HITS） | `DETERMINISTIC` + `OWNER_REPORTED`；Reviewer 重跑 |
| X-02 | 无真实 Key/外部网络/付费请求；LiveGate 仍 BLOCKED | AST 扫描 `m1_teacher/ tests/m1_teacher/ scripts/m1b/`；socket 阻断 demo/cli 测试 | 网络 import **0**；`autoteacher_m0` 仅隔离断言/注释（0 import）；无 Key/Provider；LiveGate 未变 | `DETERMINISTIC` + `OWNER_REPORTED`；Reviewer 重跑 |

## 8. 证据包（最终树）

`docs/m1b_evidence/`（collector 生成，`schema m1b.audit-index.v0`）：

| 内容 | 实测 |
|---|---|
| `audit-index.jsonl` | **append-only**：旧 16 条过渡快照记录保留（含旧 EXECUTED_FAIL/NOT_RUN 并标注旧窗口；其前缀 sha256 仍为 `11a9f5c3…`）+ 11 条最终树新条目，共 **27 条**；final hash `4b9a0d0e…`（§13） |
| `raw/<run_id>/` | 每 run 的 `evidence.json` + `stdout.log` + `stderr.log`（合成数据、无 Key/PII/hidden expected） |
| `e2e_b5_*.jsonl` | `cf` / `interview` / `cross_domain` / `freshness`；final hashes 见 §9 |
| `e2e_b5_summary.json` | 固定 artifact_manifest（`implementation_commit=c420d19…`，`generated_at=2026-11-20T00:00:00Z`，`base_sha=3e7afee…`）；final hash 见 §9 |

最终树 collector entries（`status` 为执行状态，非产品 PASS）：`B5-01-full-suite`（938 passed / 103.43s）、`B1-05-os-sandbox-gate`（938 passed / 103.10s，0 skipped）、`B4-01-02-03-e2e`（18 passed：B4 E2E 9 + durability 9）、`B5-01-e2e`（11 passed）、`B1-05-certification`（33 passed / 112 hidden）、`B2-01-02-03-crash`（35 passed）、`B5-01-demo-double-run`（identical True）、`B4-01-demo-double-run`（identical True）、`X-01-scope-diff`、`X-02-network-scan`、`B5-01-evidence-artifacts`（全部 EXECUTED_PASS；旧 16 条保留）。

## 9. 证据类与最终哈希

| Artifact | SHA-256（最终树） |
|---|---|
| `e2e_b5_cf.jsonl` | `526f9dfdc63b2b0781db7e3b11abba6cbb870616f0d5368679d93309f19f0cf1` |
| `e2e_b5_cross_domain.jsonl` | `c02723ec42e8ec76f3806719ffc6eb81fa38b677623cb982fd519e2eee35925c` |
| `e2e_b5_freshness.jsonl` | `8a25de6e641313327e24f886abb1577105faae973da129f9ad49336b2a890332` |
| `e2e_b5_interview.jsonl` | `8f3a16fc51771288c855fa94ab4cec978cf82c0864dd2aedf033c525d2f8452d` |
| `e2e_b5_summary.json` | `b6e67eb71d4d1f9d4c20fe82a62e9b2eb620735be933746c33cee6a694f8fad4` |
| B5 demo stdout（27 行） | `4d0e0c851f4ff4d745127932aa62fcfabeca47da2f7d23ae434cae1ab300a2fc` |
| B4 demo `--json` stdout（511 行） | `6b7bb66e36a38bd640d5b47d206d8fee24a446df9b42dbe76d20dd8cc50bef83` |
| `audit-index.jsonl` / `audit-index.json` | `4b9a0d0e013a5b78f39f3c604cf5dfe6c0a25346f5ef5562cd4381857e06dbec` / `05b4b9ebbed76cdef862cf638283a6a8fb65a2830cc4c6faccf7042d424d883c` |

证据类标注：CF/interview/JD/freshness 输入与模拟结果 = `MOCK`；状态机/回放/哈希/门禁 = `DETERMINISTIC`；**学习效果/真实 Provider/网络/Live = `NOT_VERIFIED`/`NOT_RUN`**；本报告不含 `HUMAN_REVIEWED` 结论（由独立 Reviewer 出具）。

## 10. NOT_RUN / UNVERIFIED / BLOCKED（最终树残余）

1. **B-PR5/B5-01 最终独立评审：`PENDING`（Lead 指派 Reviewer）**；本报告不预填最终 PASS。
2. B-PR1 P1-2（宿主非 root principal）`NOT CLOSED`；B1-04 `PARTIAL`；真实用户 CODE **`BLOCKED`**。
3. B1-05 目标部署 latency/resource/非 root 验收 `NOT_RUN`；B1-02/03/06 target-deploy 复核 `NOT_RUN`。
4. B2/B3 的残余 P2（恢复 ERROR 事件语义、legacy digest 边界等）以各自 review 文档为准，最终树未重判。
5. 真实教学效果、真实学习者、真实模型/Provider、联网研究、真实 JD/简历：`NOT_VERIFIED`/`NOT_RUN`。
6. 非 root 部署、断电/掉盘持久性、真实 auth/多租户隔离、target OS 沙箱验收：`NOT_RUN`。
7. B-PR0 `B0-01` 最终合同签收、PR1/PR2/PR3 review-fix 的独立复评结论：按各 Reviewer 文档/Lead 记录，本报告只引用 `REVIEWER_REPORTED`。

## 11. 默认 / 最终结论边界

- Owner 最终树所有本地门通过且未触发 STOP；**最终裁定由独立 Reviewer 给出**。
- 独立 Reviewer 关闭全部 Gate 后，默认只允许：**`PASS_FOR_M1B_OFFLINE_INTEGRATION_SCOPE`**。
- 该结论仅覆盖：离线、合成 fixtures、确定性/mock E2E、独立复跑证据齐全的 M1-B 集成范围。
- **明确不包含**（不得暗示）：真人学习收益/教学效果；联网研究/招聘网站/真实 JD/简历；真实 Provider/LLM 能力；真实 OS 判题安全承诺；Live/LiveGate/授权/生产可用；M0 G4-H/G5/LiveGate/M0 决策变更。
- 人类 Gate 不在本报告范围：H-01/H-02/H-03、G5、LiveGate、M0 决策保持各自状态；B 线无权解除。

## 12. 复现命令（Reviewer 用最终冻结 SHA）

```bash
cd /root/m1b/pr5
export TMPDIR=$(mktemp -d)
PY="/root/Autonomous Teacher/.venv/bin/python"
"$PY" -m pytest tests/m1_teacher -q                                   # 938 passed
M1B_REQUIRE_OS_SANDBOX=1 "$PY" -m pytest tests/m1_teacher -q -rs      # 938 passed, 0 skipped
"$PY" -m pytest tests/m1_teacher/test_b5_e2e.py -q                    # 11 passed
"$PY" -m pytest tests/m1_teacher/test_b4_e2e.py tests/m1_teacher/test_b4_durability_replay.py -q
"$PY" -m pytest tests/m1_teacher/test_judge_correctness.py -q         # 112/112 certification
"$PY" -m pytest tests/m1_teacher/test_crash_recovery.py -q            # real SIGKILL matrix
"$PY" -m m1_teacher.e2e_b5 > /tmp/e2e1; "$PY" -m m1_teacher.e2e_b5 > /tmp/e2e2; cmp /tmp/e2e1 /tmp/e2e2
"$PY" -m m1_teacher.e2e_b5 --write-evidence
sha256sum docs/m1b_evidence/e2e_b5_*.jsonl docs/m1b_evidence/e2e_b5_summary.json
# audit packet validate: docs/m1b_evidence/audit-index.jsonl + raw/** (sha256 per entry)
```

> 在最终冻结 SHA 上任何 hash/count 与 §9/§13 不一致：按 regression 处理，不得沿用本报告 PASS 值。

## 13. 最终树证据与 SHA（回填）

| 项 | 最终值 |
|---|---|
| 最终集成树 merge commit（PR4 final 合入 PR5） | `861d147d…`（`git rev-parse 861d147`；父：`1de6ae6d3714ab815c47022e4c2cceee107db979` PR4 final + PR5 `e3394ae`） |
| PR5 B5 实现提交 | `c420d19390d87e0d3faa3f716c7b2a3904c36891`（e2e_b5 改为 teacher-visible learner script；artifact manifest `implementation_commit`） |
| **PR5 最终 commit SHA** | **本报告所在 commit 完成后回填**（`git rev-parse b-next/pr5-e2e-eval`；由 Lead/报告记录） |
| 最终树 `pytest tests/m1_teacher -q` | **938 passed in 102.76s**（clean TMPDIR） |
| 最终树 strict `M1B_REQUIRE_OS_SANDBOX=1 … -q -rs` | **938 passed in 102.95s；0 skipped** |
| 定向 | B5 11 / B4 9 / B4 durability 9 / certification 33（112/112） / crash 35 / collector 14 |
| B5 demo/evidence 双跑 | stdout sha256 `4d0e0c85…`（27 行）；5 个 evidence 文件 byte-identical（hashes §9） |
| `audit-index.jsonl`（append-only：旧 16 条前缀 sha256 保持 `11a9f5c3…` 不变 + 11 条 final 条目，共 27 条） | `4b9a0d0e013a5b78f39f3c604cf5dfe6c0a25346f5ef5562cd4381857e06dbec` |
| `audit-index.json`（27 entries mirror，content == jsonl） | `05b4b9ebbed76cdef862cf638283a6a8fb65a2830cc4c6faccf7042d424d883c` |
| 最终 Reviewer 裁定 | `PENDING`（Lead 指派；只允许 §11 的结论类型） |
