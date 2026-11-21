# M1-B 评测报告（B-PR5 最终树：统一 E2E + 独立测评证据）

| 字段 | 值 |
|---|---|
| 报告状态 | **FINAL_TREE_MEASURED + FINAL_REVIEW_P1_CLOSURE（Owner 执行侧）；最终独立评审 `PASS_WITH_ACTIONS`（P0=0/P1=3/P2=6），P1 修复待 Reviewer delta 复核** |
| 报告版本 | `m1b.eval-report.v1`（2026-11-21 UTC，final-review P1 closure） |
| 工作区 / 分支 | `/root/m1b/pr5` / `b-next/pr5-e2e-eval` |
| 最终集成树 | PR4 final `1de6ae6d3714ab815c47022e4c2cceee107db979` 合入 PR5 后的 merge commit **`861d147d…`**；最终行为代码 SHA **`12f6290c43523d5c3930915fe18810adca8609a4`**（P1-1 collector 修复）；P1-2 证据生成 SHA **`9c383e5870ba628c17cd695944878d2b631fd59d`**（tree `333828d…`，clean worktree）；**PR5 最终 commit SHA 在本文档所在 commit 完成后由 Lead/报告回填** |
| 主基线 | `3e7afee077845a071cd364e93ab209cac20b2d5f` |
| 环境 | 干净 `TMPDIR=$(mktemp -d)`（串行、无并发测试）；Linux 6.17.13-2-pve；Python 3.11.15（`/root/Autonomous Teacher/.venv/bin/python`）；pytest 9.2.0；bubblewrap 0.9.0；TZ=UTC；PYTHONHASHSEED 由 collector 记录 |
| 证据包 | `docs/m1b_evidence/audit-index.jsonl`（append-only，含历史 16 条过渡快照记录 + 最终树条目；旧 EXECUTED_FAIL/NOT_RUN 记录保留） + `raw/**` + `e2e_b5_*.jsonl` + `e2e_b5_summary.json` |
| 证据标签 | 本报告为 `OWNER_REPORTED` + `DETERMINISTIC`（Owner 本地真实命令/哈希）；各 PR Reviewer 结论标 `REVIEWER_REPORTED`；**B5-01 最终独立评审 = `PASS_WITH_ACTIONS`（P0=0/P1=3/P2=6）**，P1 修复已实现、待原 Reviewer delta 复核；`B4-01/02/03` 已由 PR4 独立评审 `VERIFIED` |
| 边界 | **Offline synthetic only, not real teaching effect.** 不构成真人学习收益、真实 Provider/网络/Live/生产授权；不改变 M0 G4-H/G5/LiveGate/M0 决策 |

---

## 0. 裁定摘要（最终树 + 引用的 Reviewer 状态）

| 项 | 状态 | 来源/证据 |
|---|---|---|
| M1-A 历史冻结 | `PASS_FOR_M1A_OFFLINE_MVP`（536 tests @ C6 `3010426…`） | `REVIEWER_REPORTED`：`docs/M1_INDEPENDENT_REVIEW.md`（历史引用） |
| M1-Offline 历史冻结 | `PASS_FOR_M1_OFFLINE_DESIGN_AND_EVALUATION_SCOPE`（365 tests @ C2 `052d980d…`） | `REVIEWER_REPORTED`：M1-Offline `REVIEW_M1_OFFLINE.md`（不在本树，历史引用） |
| B-PR0 预审 | `PRE_REVIEW_PASS_WITH_ACTIONS`（P0=0 / P1=8 / P2=13；B0-01 仍 `NOT_RUN`） | `REVIEWER_REPORTED`：`docs/M1_B_BOUNDARY_PRE_REVIEW.md`、`docs/M1_B_PR0_REVIEW_RESPONSE.md` |
| B-PR1 安全评审 | `PASS_WITH_ACTIONS` → 修复复核 `P1_ACTIONS_PARTIALLY_CLOSED`；**最终树状态**：P1-1 `CLOSED`、P1-4 `CLOSED`、**P1-3 脚本已接线（`scripts/m1b/run_safety_ci.sh`）但 `.github` job `NOT_CONFIGURED`**、**P1-2 实现 fail-closed 已存在 / 非 root 目标部署验收 `NOT_RUN`（B1-04 仍 `PARTIAL`）** | `REVIEWER_REPORTED`：`docs/M1_B_PR1_REVIEW.md`、`docs/M1_B_PR1_REVIEW_ADDENDUM.md`；final tree 含修复 |
| B-PR2 事务评审 | `PASS_WITH_ACTIONS`；B2-01/02/03 + B-Q2 `VERIFIED`；review-fix tree 已合入（goal failpoint/D12 记录等） | `REVIEWER_REPORTED`：`docs/M1_B_PR2_REVIEW.md`；final tree = PR4 final 合入树 |
| B-PR3 幂等评审 | `PASS_WITH_ACTIONS`；B3-01/02 + B-Q3 `VERIFIED`；review-fix tree 已合入（legacy digest/公共 API scoped 查找等） | `REVIEWER_REPORTED`：`docs/M1_B_PR3_REVIEW.md`；final tree 含修复 |
| B-PR4 独立评审 | `PASS_WITH_ACTIONS`（P0=0 / P1=3 / P2=7）；**P1 修复已合入 final tree**（`49cf45b`/`1de6ae6`）：P1-1 会话计划持久化、P1-2 hidden reader 守卫、P1-3 版本拒绝/事件schema 部分（PARTIAL 明示）；B4-01/02/03 均 `VERIFIED`（E2E-MOCK；B4-02 以重启计划持久化修复为前提） | `REVIEWER_REPORTED`：`docs/M1_B_PR4_REVIEW.md` + `M1_B_PR4_REVIEW_RESPONSE.md`；final tree 含修复 |
| B-PR5 统一 E2E/评测 | Owner 最终树实测完成（本报告）；`B5-01` 最终独立评审 **`PENDING`（Lead 指派）** | Owner 最终树证据包；独立评审未出 |
| X-01 无范围漂移 | Owner 侧 `DETERMINISTIC` 检查通过：**最终树 vs main = 302 files（302 A/0 M/0 D）**，vs M1-A = **243 files**；Reviewer 在 `c3eb736` 实测为 268 files（之后 P1 证据/文档/P1 修复新增 34 文件），保护路径 **0 命中** | collector entry `X-01-scope-diff`（final 条目）；Reviewer 需重跑 |
| X-02 无 Key/网络/付费 | Owner 侧 `DETERMINISTIC` 检查通过（网络 import **0**；`autoteacher_m0` 仅隔离断言/注释；无 Key/Provider；LiveGate 仍 BLOCKED） | collector entry `X-02-network-scan`（final 条目）；Reviewer 需重跑 |
| **最终独立评审（B5-01）** | **`PASS_WITH_ACTIONS`**（P0=0 / P1=3 / P2=6；报告 `docs/M1_B_FINAL_INDEPENDENT_REVIEW.md`，待 Reviewer commit 合入）；P1-1/P1-2/P1-3 修复见 §3.4/§8.1/§13 | `REVIEWER_REPORTED` + 本报告修复证据 |
| **Owner 侧结论（修复后）** | **`PASS_WITH_ACTIONS → P1_CLOSED_PENDING_DELTA_REVIEW`**（不预填无条件 PASS；delta Reviewer 关闭 P1 后才允许 `PASS_FOR_M1B_OFFLINE_INTEGRATION_SCOPE`） | 本报告 §10/§11/§13 |

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

## 3. 最终集成套件实测（939 tests，clean TMPDIR）

### 3.1 全量命令与输出

```bash
cd /root/m1b/pr5
export TMPDIR=$(mktemp -d)
PY="/root/Autonomous Teacher/.venv/bin/python"
"$PY" -m pytest tests/m1_teacher -q
# exit 0 -> 939 passed in 102.72s (0:01:42)          [P1-1 fix 后 worktree 实测]
M1B_REQUIRE_OS_SANDBOX=1 "$PY" -m pytest tests/m1_teacher -q -rs
# exit 0 -> 939 passed; 0 skipped                    [strict OS-sandbox 模式]
"$PY" -m ruff check m1_teacher tests/m1_teacher
# All checks passed!
```

### 3.2 计数构成（独立计数；历史数字不相加）

| 来源 | tests | 说明 |
|---|---:|---|
| M1-A 历史基线（历史冻结参考） | 536 | `REVIEWER_REPORTED` 历史值（`4706250`：独立 Reviewer 实测 536 passed）；**final tree 中 5 个 M1-A 测试文件随 D12/去 flake 更新过，故不能声称“536 原样未改”**（P2-4）；计数仍为 536 |
| PR4 final 树（`1de6ae6…`） | 913 | Lead 冻结值；含 PR1/PR2/PR3 review-fix tree 与 PR4 final（913 = 536 + 377 PR1/PR2/PR3/PR4 新增/修复测试） |
| B-PR5 新增（PR5 分支） | 26 | B5 统一 E2E `test_b5_e2e` 11 + 证据收集器 `test_evidence_collector` 15（含 P1-1 no-.git 回归） |
| **最终集成套件合计** | **939** | 913 + 26 = 939；`pytest --collect-only` 独立确认 939 |
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

> 过渡快照（`e2b6e85` 等）的旧数值仅保留在 git 历史/旧 evidence 记录中；本报告最终数字以 **939** 为准（P1-1 回归测试 +1）。

### 3.4 clean archive 交叉复跑（P1-1 修复后）

```bash
rm -rf /tmp/m1b-archive && mkdir -p /tmp/m1b-archive
git archive <FINAL_SHA> | tar -x -C /tmp/m1b-archive      # no .git
cd /tmp/m1b-archive
export TMPDIR=$(mktemp -d)
"$PY" -m pytest tests/m1_teacher -q                       # 939 passed
M1B_REQUIRE_OS_SANDBOX=1 "$PY" -m pytest tests/m1_teacher -q -rs   # 939 passed, 0 skipped
```

实测（P1-1 修复后，`git archive 9c383e5…` 生成的无 `.git` archive）：全量 **939 passed in 104.85s**；strict **939 passed in 102.93s / 0 skipped**（修复前为 `937 passed, 1 failed`，失败项为 collector 测试要求 `git_sha` 40-hex；现在无 `.git` 时明确 `git_sha=null`/`git_available=false`，见 `docs/M1_B_EVIDENCE_PACKET.md` §3.1）。

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
| **确定性** | `python -m m1_teacher.e2e_b5` 双跑 stdout 逐字节一致：sha256 `4d0e0c851f4ff4d745127932aa62fcfabeca47da2f7d23ae434cae1ab300a2fc`（27 行）；`demo_b4 --json` 双跑一致 sha256 `b3231658a4ac12a49cd2ac57f4a3e8d9719fbf7476ca36a54e4d8f9eea72d905`（**513 行 / 15,340 bytes**，final tree 实测；旧 511 行/15,108 bytes 为旧树）；`e2e_b5 --write-evidence` 双跑 5 文件 byte-identical |
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
| B1-01 | untrusted CODE fail-closed，不可数据路径开启 | `VERIFIED (LOCAL_ONLY)`（PR1 review；final tree strict 939/0 skipped） | 真实用户 CODE 仍 **BLOCKED** |
| B1-02 | hidden expected 不进入 worker 内存/argv/log | `VERIFIED (LOCAL_ONLY)` | target-deploy 复核 `NOT_RUN` |
| B1-03 | 不可信 worker 不能伪造可信 PASS | `VERIFIED (LOCAL_ONLY)` | 同上 |
| B1-04 | OS confinement：网络/宿主秘密/逃逸/资源 | **`PARTIAL`**（P1-2：**实现 fail-closed 已存在**；**非 root 目标部署验收 `NOT_RUN`**；本地 `LOCAL_ONLY`） | 非 root principal 目标部署 `NOT_RUN` |
| B1-05 | 判题正确性/可用性 | **`PARTIAL`**（112/112 hidden、33 passed；默认 TLE 分类 P1-1 已修复；**目标部署 latency/resource 验收 `NOT_RUN`**） | target-deploy latency/resource `NOT_RUN` |
| B1-06 | hidden 泄漏扫描 | `VERIFIED (LOCAL_ONLY)`（final tree `test_hidden_leakage_scan` 15 passed；B5 证据无 hidden 内容） | target-deploy 运行时导出复核 `NOT_RUN` |
| B2-01/02/03 | 原子 turn commit / crash replay / 并发语义 | `VERIFIED`（PR2 review；final tree 含 review-fix；crash 35 passed） | P2 项（恢复 ERROR 事件等）记录于 PR2 review |
| B3-01/02 | scoped result_id / 跨 learner 隔离 | `VERIFIED`（PR3 review；final tree scope migration 15 + scoped 31 passed） | P2 项记录于 PR3 review |

## 7. X-01 / X-02 结果（最终树 Owner 侧）

| case_id | 检查 | 命令 | 实测（Owner） | 标签 |
|---|---|---|---|---|
| X-01 | M1 提交不修改 `src/autoteacher_m0/`、`security/`、`bridge/`、`config/g*`、`scripts/g4*`、LiveGate；A 线不改 M1 | `git diff --name-only 3e7afee..HEAD` + 保护前缀 grep；`git diff --name-only main...HEAD` | **final tree：302 files（302 A/0 M/0 D）vs main；243 files vs M1-A**（reviewer 在 `c3eb736` 实测 268；P1 修复/证据新增 34）；保护路径 **0 命中** | `DETERMINISTIC` + `OWNER_REPORTED`；Reviewer 重跑 |
| X-02 | 无真实 Key/外部网络/付费请求；LiveGate 仍 BLOCKED | AST 扫描 `m1_teacher/ tests/m1_teacher/ scripts/m1b/`；socket 阻断 demo/cli 测试 | 网络 import **0**；`autoteacher_m0` 仅隔离断言/注释（0 import）；无 Key/Provider；LiveGate 未变 | `DETERMINISTIC` + `OWNER_REPORTED`；Reviewer 重跑 |

## 8. 证据包（最终树）

`docs/m1b_evidence/`（collector 生成，`schema m1b.audit-index.v0`）：

| 内容 | 实测 |
|---|---|
| `audit-index.jsonl` | **append-only**：旧 27 条（含 16 条过渡快照 + 11 条 c420d19 窗口 final）全部字节保留（前 27 行 sha256 仍为 `4b9a0d0e…`；旧 16 条前缀仍为 `11a9f5c3…`）+ P1-2 新增 11 条 clean-worktree 条目，共 **38 条**；final hash `a11ce429…`（§8.1/§13） |
| `raw/<run_id>/` | 每 run 的 `evidence.json` + `stdout.log` + `stderr.log`（合成数据、无 Key/PII/hidden expected） |
| `e2e_b5_*.jsonl` | `cf` / `interview` / `cross_domain` / `freshness`；final hashes 见 §9 |
| `e2e_b5_summary.json` | 固定 artifact_manifest（`implementation_commit=c420d19…`，`generated_at=2026-11-20T00:00:00Z`，`base_sha=3e7afee…`）；final hash 见 §9 |

最终树 collector entries（P1-2 重新生成后以新条目为准；`status` 为执行状态，非产品 PASS）：`B5-01-full-suite`（939 passed）、`B1-05-os-sandbox-gate`（939 passed，0 skipped）、`B4-01-02-03-e2e`（18 passed：B4 E2E 9 + durability 9）、`B5-01-e2e`（11 passed）、`B1-05-certification`（33 passed / 112 hidden）、`B2-01-02-03-crash`（35 passed）、`B5-01-demo-double-run`（identical True）、`B4-01-demo-double-run`（identical True）、`X-01-scope-diff`、`X-02-network-scan`、`B5-01-evidence-artifacts`（全部 EXECUTED_PASS；旧条目保留）。

## 9. 证据类与最终哈希

| Artifact | SHA-256（最终树） |
|---|---|
| `e2e_b5_cf.jsonl` | `526f9dfdc63b2b0781db7e3b11abba6cbb870616f0d5368679d93309f19f0cf1` |
| `e2e_b5_cross_domain.jsonl` | `c02723ec42e8ec76f3806719ffc6eb81fa38b677623cb982fd519e2eee35925c` |
| `e2e_b5_freshness.jsonl` | `8a25de6e641313327e24f886abb1577105faae973da129f9ad49336b2a890332` |
| `e2e_b5_interview.jsonl` | `8f3a16fc51771288c855fa94ab4cec978cf82c0864dd2aedf033c525d2f8452d` |
| `e2e_b5_summary.json`（P1-2 生成，manifest `implementation_commit=12f6290…`） | `a07cfe7ec06208bc3271e01eaaf62a6145c753bf175b23c844658c756d444053` |
| B5 demo stdout（27 行） | `4d0e0c851f4ff4d745127932aa62fcfabeca47da2f7d23ae434cae1ab300a2fc` |
| B4 demo `--json` stdout（513 行 / 15,340 bytes） | `b3231658a4ac12a49cd2ac57f4a3e8d9719fbf7476ca36a54e4d8f9eea72d905` |
| `audit-index.jsonl` / `audit-index.json`（P1-2 后 38 条） | `a11ce42948d5dd43563a1bf6befa8bb7c8600ba3b73f9df32e345b07bc66ea80` / `8db875301cc10f5af3af4f038b42d50a43a9291ac50c96719f7fd9ce37fc34e5` |

证据类标注：CF/interview/JD/freshness 输入与模拟结果 = `MOCK`；状态机/回放/哈希/门禁 = `DETERMINISTIC`；**学习效果/真实 Provider/网络/Live = `NOT_VERIFIED`/`NOT_RUN`**；本报告不含 `HUMAN_REVIEWED` 结论（由独立 Reviewer 出具）。

## 10. NOT_RUN / UNVERIFIED / BLOCKED（最终树残余）

1. **B-PR5/B5-01 最终独立评审：`PASS_WITH_ACTIONS`（P0=0/P1=3/P2=6）；P1-1/P1-2/P1-3 已修复，delta 复核 `PENDING`**；本报告不预填无条件 PASS。
2. B-PR1 P1-2：**实现 fail-closed 已存在**；**非 root 目标部署验收 `NOT_RUN`**；B1-04 `PARTIAL`；真实用户 CODE **`BLOCKED`**。
3. B1-05 目标部署 latency/resource/非 root 验收 `NOT_RUN`；B1-02/03/06 target-deploy 复核 `NOT_RUN`。
4. B2/B3 的残余 P2（恢复 ERROR 事件语义、legacy digest 边界等）以各自 review 文档为准，最终树未重判。
5. 真实教学效果、真实学习者、真实模型/Provider、联网研究、真实 JD/简历：`NOT_VERIFIED`/`NOT_RUN`。
6. 非 root 部署、断电/掉盘持久性、真实 auth/多租户隔离、target OS 沙箱验收：`NOT_RUN`。
7. B-PR0 `B0-01` 最终合同签收、PR1/PR2/PR3 review-fix 的独立复评结论：按各 Reviewer 文档/Lead 记录，本报告只引用 `REVIEWER_REPORTED`。

## 11. 默认 / 最终结论边界

- Owner 最终树所有本地门通过；最终独立评审结论为 **`PASS_WITH_ACTIONS`**（P0=0，P1=3），**P1 修复已实现，delta Reviewer 复核 `PENDING`**。
- delta Reviewer 关闭 P1 后，默认只允许：**`PASS_FOR_M1B_OFFLINE_INTEGRATION_SCOPE`**；在此之前不得声称无条件 PASS。
- 该结论仅覆盖：离线、合成 fixtures、确定性/mock E2E、独立复跑证据齐全的 M1-B 集成范围。
- **明确不包含**（不得暗示）：真人学习收益/教学效果；联网研究/招聘网站/真实 JD/简历；真实 Provider/LLM 能力；真实 OS 判题安全承诺；Live/LiveGate/授权/生产可用；M0 G4-H/G5/LiveGate/M0 决策变更。
- 人类 Gate 不在本报告范围：H-01/H-02/H-03、G5、LiveGate、M0 决策保持各自状态；B 线无权解除。

## 12. 复现命令（Reviewer 用最终冻结 SHA）

```bash
cd /root/m1b/pr5
export TMPDIR=$(mktemp -d)
PY="/root/Autonomous Teacher/.venv/bin/python"
"$PY" -m pytest tests/m1_teacher -q                                   # 939 passed
M1B_REQUIRE_OS_SANDBOX=1 "$PY" -m pytest tests/m1_teacher -q -rs      # 939 passed, 0 skipped
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
| 最终集成树 merge commit（PR4 final 合入 PR5） | `861d147d…`（`1de6ae6d…` PR4 final + PR5 分支） |
| 最终行为代码 SHA（collector P1-1 修复） | `12f6290c43523d5c3930915fe18810adca8609a4` |
| **P1-2 证据生成 SHA / tree** | **`9c383e5870ba628c17cd695944878d2b631fd59d` / `333828d38fe8988df6d4a9ef98715b5d0e9f06e3`**；生成开始时 `git status --porcelain` 空 |
| P1-2 evidence 提交 / 本报告最终提交 | `580be70fd0f969706bce0f9c274c6f68ed08455c`（P1-2 evidence commit）/ **最终 PR5 commit = 本文档所在 commit（SHA 由 Lead/交付记录回填；`git rev-parse b-next/pr5-e2e-eval`）**；最终代码/测试 SHA = `8f8d00ed…`（review-doc 引号守卫修复） |
| artifact manifest `implementation_commit` | `12f6290…`（最后行为代码 SHA；生成 commit `9c383e5` 仅更新该常量与文档） |
| 最终树 `pytest tests/m1_teacher -q` | **939 passed in 103.11s**（Owner worktree，final SHA）；P1-2 生成时 **939 passed in 102.96s** |
| 最终树 strict `M1B_REQUIRE_OS_SANDBOX=1 … -q -rs` | **939 passed in 103.21s；0 skipped**（final SHA）；生成时 **939 passed in 103.03s，0 skipped** |
| clean archive（无 `.git`）全量 / strict | **939 passed in 104.85s / 939 passed in 102.93s（0 skipped）**（P1-1 修复后） |
| 定向 | B5 11 / B4 9 + durability 9 / certification 33（112/112） / crash 35 / collector 15 |
| B5 demo/evidence 双跑 | stdout sha256 `4d0e0c85…`（27 行）；5 文件 byte-identical（hashes §9） |
| `audit-index.jsonl`（append-only，38 条：旧 27 + 新 11） | `a11ce42948d5dd43563a1bf6befa8bb7c8600ba3b73f9df32e345b07bc66ea80` |
| `audit-index.json`（38 entries mirror） | `8db875301cc10f5af3af4f038b42d50a43a9291ac50c96719f7fd9ce37fc34e5` |
| 最终独立评审裁定 | `PASS_WITH_ACTIONS`（P0=0/P1=3/P2=6）；**P1 fixes → delta review `PENDING`** |


## 14. 最终评审 P1 关闭证据（Owner 侧；待 delta Reviewer 复核）

| P1 | 关闭动作 | 本轮真实证据 |
|---|---|---|
| **P1-1** clean archive 可移植性 | collector 无 `.git` 时记录 `git_sha=null`/`git_available=false`/`git_sha_source="unavailable"`；支持显式 `--git-sha/--tree-sha`；新增 no-git 回归测试；文档 §3.1；review doc 中引用旧短语触发 PR1 docs lint，守卫已改为忽略引号内历史引用（final SHA `8f8d00e…`） | `git archive 8f8d00e… \| tar -x`（无 `.git`）全量 **939 passed in 104.85s**（`sha256(/tmp/final_archive2_full.txt)=6681834dea5c3bfd28e077da48c9eeb757e252d522614ed628b2e952a3be8228`）；strict **939 passed in 102.93s，0 skipped**（`sha256(/tmp/final_archive2_strict.txt)=b34c2ab979df3e8db3a0b9080e3f9da107323a429bd6a53cc5bf417132203f07`）；回归测试 `test_collector_is_portable_in_a_no_git_archive_copy` 通过；旧失败 `test_collects_executed_pass_with_full_index_entry` 现接受 `git_available=false` |
| **P1-2** 证据绑定最终树 | 生成前 clean worktree（`git status --porcelain` 空）；生成 SHA/tree 记入 README+§13；append-only 新增 11 条（38 条总），旧 27 条字节保留；manifest `implementation_commit=12f6290…` | generation proof `sha256(/tmp/p12_generation_proof.txt)=d1a2070a53a85f5070f0f3dda629e0f4f597bdf84cbb5137a41a68de5ff05125`；`audit-index.jsonl` `a11ce429…`（38 条；old-27 prefix `4b9a0d0e…` 不变）；`audit-index.json` `8db87530…`；B5 summary `a07cfe7e…`；新条目 28–38 全部 `EXECUTED_PASS`、`git_sha=9c383e5…`、`tree_sha=333828d…`、generation-start clean=true；evidence commit `580be70…` |
| **P1-3** 报告数字/哈希/状态勘误 | X-01：reviewer 树 `c3eb736` 实测 268 files（268 A/0M/0D vs main；209 vs M1-A）；**final tree（P1 证据/修复后）实测 302 files / 243 vs M1-A，保护 0**；B4 demo 改 `b3231658…`/513 行/15,340B；分项计数改 939=913+26（B5 11 + collector 15）且合计一致；PR4 P1 标记“已合入”；PR1 P1-2 分栏、P1-3 脚本已接线/`.github` job `NOT_CONFIGURED`；clean archive 实测更新；PR5 最终评审状态更新 | 本报告 §3/§3.4/§5/§6/§7/§9/§13；collector `X-01-scope-diff` raw 实测 268/0 protected；`demo_b4` double-run hash `b3231658…`；`--collect-only` 939 |

> 残余：最终独立评审为 `PASS_WITH_ACTIONS`；本次仅 Owner 侧关闭 P1 证据，**delta Reviewer 复核结论 `PENDING`**；实现报告数字由 m1a-contracts 后续更新（Lead 指派）。不得据此声称无条件 `PASS_FOR_M1B_OFFLINE_INTEGRATION_SCOPE`。
