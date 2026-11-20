# M1-B 评测报告（B-PR5 统一 E2E + 独立测评证据）

| 字段 | 值 |
|---|---|
| 报告状态 | **FINAL（Owner 执行侧）；独立 Reviewer 验收待完成** |
| 报告版本 | `m1b.eval-report.v1`（2026-11-20 UTC） |
| 工作区 / 分支 | `/root/m1b/pr5` / `b-next/pr5-e2e-eval` |
| 集成实现 SHA | `e2b6e85d8939b2411b2b6c6cc26538014c6f57e3`（本报告所有命令在该 SHA 的 worktree 上执行；PR1 fix cascade / PR4 final 由 Lead 后续合入，届时本报告数字须重生成） |
| 主基线 | `3e7afee077845a071cd364e93ab209cac20b2d5f` |
| 环境 | Linux 6.17.13-2-pve；Python 3.11.15（`/root/Autonomous Teacher/.venv/bin/python`）；pytest 9.2.0；bubblewrap 0.9.0；TZ=UTC、PYTHONHASHSEED 由命令/收集器记录 |
| 证据包 | `docs/m1b_evidence/audit-index.jsonl`（16 条 owner-executed 记录）+ `raw/**` + `docs/m1b_evidence/e2e_b5_*.jsonl` + `e2e_b5_summary.json` |
| 证据标签 | 本报告为 `OWNER_REPORTED` + `DETERMINISTIC`（本地真实命令/哈希）；各 PR Reviewer 结论标 `REVIEWER_REPORTED`（引用其报告）；B-PR4/B-PR5 独立评审 = `NOT_RUN` |
| 边界 | **Offline synthetic only, not real teaching effect.** 不构成真人学习收益、真实 Provider/网络/Live/生产授权；不改变 M0 G4-H/G5/LiveGate/M0 决策 |

---

## 0. 裁定摘要（Owner 侧 + 引用的 Reviewer 状态）

| 项 | 状态 | 来源/证据 |
|---|---|---|
| M1-A 历史冻结 | `PASS_FOR_M1A_OFFLINE_MVP`（536 tests @ C6 `3010426…`） | `REVIEWER_REPORTED`：`docs/M1_INDEPENDENT_REVIEW.md`（未并入本树，历史引用） |
| M1-Offline 历史冻结 | `PASS_FOR_M1_OFFLINE_DESIGN_AND_EVALUATION_SCOPE`（365 tests @ C2 `052d980d…`） | `REVIEWER_REPORTED`：M1-Offline `REVIEW_M1_OFFLINE.md`（不在本树，历史引用） |
| B-PR0 预审 | `PRE_REVIEW_PASS_WITH_ACTIONS`（P0=0 / P1=8 / P2=13；B0-01 仍 `NOT_RUN`） | `REVIEWER_REPORTED`：`docs/M1_B_BOUNDARY_PRE_REVIEW.md`、`docs/M1_B_PR0_REVIEW_RESPONSE.md` |
| B-PR1 安全评审 | `PASS_WITH_ACTIONS` → 修复复核 `P1_ACTIONS_PARTIALLY_CLOSED`（P1-1/P1-4 `CLOSED`；P1-3 机制关闭/CI 接线 `NOT_CONFIGURED`；P1-2 `NOT CLOSED`） | `REVIEWER_REPORTED`：`docs/M1_B_PR1_REVIEW.md`、`M1_B_PR1_REVIEW_ADDENDUM.md`（reviewer 分支，本树未含） |
| B-PR2 事务评审 | `PASS_WITH_ACTIONS`；B2-01/02/03 + B-Q2 `VERIFIED`；P1=2 / P2=5 | `REVIEWER_REPORTED`：`docs/M1_B_PR2_REVIEW.md` |
| B-PR3 幂等评审 | `PASS_WITH_ACTIONS`；B3-01/02 + B-Q3 `VERIFIED`；P1=2 / P2=5 | `REVIEWER_REPORTED`：reviewer 分支 `M1_B_PR3_REVIEW.md`（本树未含） |
| B-PR4 独立评审 | **`NOT_RUN`（进行中）**；owner `IMPLEMENTED + LOCAL_VERIFIED`（E2E-MOCK，9 tests） | Owner 本地证据；独立评审未出 |
| B-PR5 独立评审 | **`NOT_RUN`**（本 PR） | 本报告 + `docs/M1_B_REVIEW_REQUEST.md` |
| X-01 无范围漂移 | Owner 侧 `DETERMINISTIC` 检查通过（159 files diff；保护路径 0 命中） | `docs/m1b_evidence/audit-index.jsonl` entry `X-01-scope-diff`；Reviewer 需重跑 |
| X-02 无 Key/网络/付费 | Owner 侧 `DETERMINISTIC` 检查通过（网络 import 0 命中；无 Key/Provider；LiveGate 仍 BLOCKED） | collector entry `X-02-network-scan`；Reviewer 需重跑 |
| **Owner 侧默认结论** | **`PENDING_INDEPENDENT_REVIEW`**（所有本地门通过；默认结论仅在独立 Reviewer 关闭 B-PR4/B-PR5 后可用：`PASS_FOR_M1B_OFFLINE_INTEGRATION_SCOPE`） | 本报告 §10/§11 |

---

## 1. 方法与独立性

- 本报告的命令**全部由 Owner 在本 worktree 真实执行**，原始 stdout/stderr 摘要、exit code、环境原始记录与 sha256 见 `docs/m1b_evidence/raw/<run_id>/`；执行记录见 `docs/m1b_evidence/audit-index.jsonl`（collector 规则：`EXECUTED_PASS` 只是执行成功，不是产品 PASS）。
- 引用各 PR 的 Reviewer 结论时明确标 `REVIEWER_REPORTED`；**不冒充本轮独立复跑**。B-PR4/B-PR5 的 `INDEPENDENTLY_REEXECUTED` 字段保持 `NOT_RUN`，等待独立 Reviewer。
- 所有教学/学生/面试/JD/知识数据均为 synthetic fixtures；无真实简历、真实 JD、真实个人数据；无网络/API Key/Provider/LiveGate。
- 历史 `536` 与 `365` 只作各自分支的历史冻结参考，**未相加**（不存在“901 tests”）；当前新集成套件独立计数（§3）。

## 2. 环境

| 项 | 值 |
|---|---|
| OS | Linux `6.17.13-2-pve`（x86_64） |
| Python | 3.11.15（`/root/Autonomous Teacher/.venv/bin/python`） |
| pytest | 9.2.0 |
| bubblewrap | 0.9.0（PR1 OS 沙箱动态测试可运行） |
| TZ / LANG / LC_ALL | `UTC` / `C.UTF-8` / `C.UTF-8` |
| 网络 / Key / Provider | 无（AST 静态扫描 0 网络 import；collector 子进程 env 剥离凭据；未配置任何 provider） |

## 3. 当前集成套件实测（884 tests）

### 3.1 全量命令与输出

```bash
cd /root/m1b/pr5
"/root/Autonomous Teacher/.venv/bin/python" -m pytest tests/m1_teacher -q
# exit 0 -> 884 passed in 93.34s (0:01:33)      [collector B5-01-full-suite]
# exit 0 -> 884 passed in 96.66s (0:01:36)      [owner final worktree re-run at report time]
"/root/Autonomous Teacher/.venv/bin/python" -m pytest tests/m1_teacher -q -rs
# exit 0 -> 884 passed in 91.96s (0:01:31)      [collector B1-05-os-sandbox-gate 重跑]
# 注：本 SHA 尚未包含 PR1 CI-gate 修复；M1B_REQUIRE_OS_SANDBOX 被记录但此树未强制接线（见 §8 限制）
"/root/Autonomous Teacher/.venv/bin/python" -m ruff check m1_teacher tests/m1_teacher
# All checks passed!
```

### 3.2 计数构成（独立计数；历史数字不相加）

| 来源 | tests | 说明 |
|---|---:|---|
| M1-A 历史冻结参考（`work/m1a-mvp` @ C6） | 536 | `REVIEWER_REPORTED` 历史；本树内对应文件仍保留并通过 |
| B-PR1 trusted judge 新增 | 138 | `test_judge_*` 123 + `test_hidden_leakage_scan` 15 |
| B-PR2 transaction/recovery 新增 | 63 | `test_turn_transaction` 19 + `test_crash_recovery` 35 + `test_concurrency` 9 |
| B-PR3 scoped-idempotency 新增 | 37 | `test_scoped_idempotency` 26 + `test_scope_migration` 11 |
| B-PR4 垂直域/B4 新增 | 85 | `test_vertical_policy` 16 + `test_b4_e2e` 9 + vertical 60 |
| B-PR5 统一 E2E + collector 新增 | 25 | `test_b5_e2e` 11 + `test_evidence_collector` 14 |
| **当前集成套件合计** | **884** | 536+138+63+37+85+25 = 884；`pytest --collect-only` 确认 884 |
| M1-Offline 历史冻结（另一分支） | 365 | `REVIEWER_REPORTED` 历史；**不在本树、未合并、不得相加** |

## 4. B-PR5 统一 E2E 实测结果（真实数字）

命令：`python -m m1_teacher.e2e_b5 --write-evidence`（exit 0；两次运行 stdout 与全部 evidence 字节一致）。

| 段 | 实测 |
|---|---|
| **CF（B4-01）** | `student_a`：7 CORRECT / 1 INCORRECT，binary mastery `0.30 -> 0.543571`，55 session events，`verify_rebuild=True`；`student_b`：3 INCORRECT / 4 NEEDS_REVIEW，binary `0.00`，`verify_rebuild=True`；两条路径 first action/plan/mastery 不同；同一 SQLite journal |
| **Interview（B4-02）** | 2 learners：A（seeded 3 CORRECT = accelerated）v1 session probes `hypothesis→complexity→experiment_design→online_triage`（concept skip）；B（novice）完整 5 阶段 `concept→hypothesis→complexity→experiment_design→online_triage`、`ASK_CLARIFICATION` 1 次、interview hint `[1]`（FULL 从未出现）、rubric 4 维（`engineering_feasibility/evidence_sufficiency/explanation_clarity/factual_correctness`）、final REVIEW |
| **JD v1→v2** | `jd:rec` v1 session（27 events，REVIEW，journal sha256 `554c1153…`）在 v2 新会话（12 events，ASSESS，journal sha256 `e6b644bb…`）创建后**完全不变**；`affects_running_sessions=False`、`affects_new_plans=True`、`reason_code=JD_CHANGE_NEW_PLANS_ONLY`；delta 含 added/removed requirements/skills |
| **跨域（同一 learner）** | CF 暂停于 turn 4 → interview session（2 sessions，domains `["cf_binary_search","interview_coach"]`）→ resume CF → final REVIEW；per-learner seq 连续（`seq_contiguous=True`），`verify_rebuild=True`，snapshot 同时含 `cf.*` 与 `interview.*` 节点 |
| **Freshness（B4-03）** | 9 knowledge 场景：KEEP 2 / RECHECK 5 / UPDATE 2；5 个 RECHECK（expired/conflict/unauthoritative/future-dated/older）全部 `rejected=True`、`events_written=0`、`FRESHNESS_KNOWLEDGE_GATE_BLOCKED` + MAP-E08/E09；3 个 JD 时间窗（expired/not-yet-active/overlap-conflict）全部拒绝、0 events、`FRESHNESS_JD_GATE_BLOCKED` + MAP-E10；2 个 eligible UPDATE 可进入新计划（events=4）；`silent_imports=0`、`gate_enforced=True` |
| **Unified journal** | 5 learners（2 CF + 2 interview + 1 cross-domain）；每个 learner `seq_contiguous=True`、`verify_rebuild=True`；事件类型含 `SESSION_STARTED/PLAN_CREATED/ACTION_TAKEN/ASSESSED/MASTERY_UPDATED/...`；单 SQLite 文件 |
| **确定性** | `python -m m1_teacher.e2e_b5` 双跑 stdout 逐字节一致：sha256 `2d6ce1d2…`，27 行；`demo_b4 --json` 双跑一致 sha256 `6b7bb66e…`，511 行；evidence 双跑全部同 hash |

B4 专属 E2E：`pytest tests/m1_teacher/test_b4_e2e.py -q` → **9 passed in 4.88s**（`B4-01/02/03` 本地 E2E-MOCK）。
B5 专属 E2E：`pytest tests/m1_teacher/test_b5_e2e.py -q` → **11 passed in 13.92s**。

## 5. B4 / B5 验收矩阵（当前状态）

| case_id | 目标 | Owner 本地状态 | 独立 Reviewer 状态 | 证据 |
|---|---|---|---|---|
| B4-01 | 双 CF learner 同 canonical mastery/session journal | `IMPLEMENTED_LOCAL_VERIFIED`（E2E-MOCK） | `NOT_RUN`（PR4 review 进行中） | `test_b4_e2e.py` 9 passed；`e2e_b5_cf.jsonl` 135 行 |
| B4-02 | 双 interview learner + JD v1→v2 不同证据化计划 | `IMPLEMENTED_LOCAL_VERIFIED`（E2E-MOCK） | `NOT_RUN` | `e2e_b5_interview.jsonl` 87 行；JD 结果见 §4 |
| B4-03 | freshness 拒绝 expired/conflict/unauthoritative | `IMPLEMENTED_LOCAL_VERIFIED`（E2E-MOCK） | `NOT_RUN` | `e2e_b5_freshness.jsonl` 18 行；`gate_enforced=True` |
| B5-01 | Reviewer 独立重跑旧两套 + 新集成套件并标 mock provenance | Owner 证据包已生成（16 entries） | **`NOT_RUN`（待独立 Review）** | `docs/m1b_evidence/audit-index.jsonl` + `docs/M1_B_REVIEW_REQUEST.md` |

> Mock provenance：所有 CF/interview 学生结果、JD/resume、knowledge 数据均为合成 fixtures/MOCK；状态机、id/seq、回放、rubric 算术为 `DETERMINISTIC`；真实教学效果 `NOT_VERIFIED`。不得把本地绿色当作 B5 独立验收。

## 6. B1 / B2 / B3 状态（引用 Reviewer + 本地套件）

| case_id | 目标 | 独立评审结论（`REVIEWER_REPORTED`） | 当前残余限制 |
|---|---|---|---|
| B1-01 | untrusted CODE fail-closed，不可数据路径开启 | `VERIFIED (LOCAL_ONLY)`（PR1 review） | 真实用户 CODE 仍 BLOCKED；人类批准 + 目标部署验收 `NOT_RUN` |
| B1-02 | hidden expected 不进入 worker 内存/argv/log | `VERIFIED (LOCAL_ONLY)` | 目标部署 Operational 验证 `NOT_RUN` |
| B1-03 | 不可信 worker 不能伪造可信 PASS | `VERIFIED (LOCAL_ONLY)`（可信端比较） | 同上 |
| B1-04 | OS confinement：网络/宿主秘密/逃逸/资源 | **`PARTIAL`**（宿主非 root principal 未满足；P1-2 `NOT CLOSED`） | 非 root principal / namespace 目标部署 `NOT_RUN` |
| B1-05 | 判题正确性/可用性 | **`PARTIAL`**（112/112 认证；默认 2.0s 死循环 TLE 已由 P1-1 修复；目标部署延迟/资源验收未做） | 目标部署 latency/resource 验收 `NOT_RUN` |
| B1-06 | hidden 泄漏扫描 | `VERIFIED (LOCAL_ONLY)` | 运行时导出扫描的 target-deploy 复核 `NOT_RUN` |
| B2-01/02/03 | 原子 turn commit / crash replay / 并发语义 | `VERIFIED`（PR2 review；真实 SIGKILL 21 failpoints，32-row matrix 与文档一致；595 tests 两轮绿） | P1 为合同/文档治理（ADR D12 记录、goal failpoint 范围措辞）；P2 5 项（恢复 ERROR 事件、seq 重试死代码等） |
| B3-01/02 | scoped result_id / 跨 learner 隔离 | `VERIFIED`（PR3 review；B-Q3） | P1 legacy 结构化 response digest 兼容、公共 API scoped 查找；P2 5 项 |

本地套件复核：`test_judge_correctness.py` 27 passed（14/14 参考解、hidden 112/112）；`test_crash_recovery.py` 35 passed；`test_scope_migration.py` 11、`test_scoped_idempotency.py` 26 passed（见 collector raw）。

## 7. X-01 / X-02 结果（Owner 侧）

| case_id | 检查 | 命令 | 实测（Owner） | 标签 |
|---|---|---|---|---|
| X-01 | M1 提交不修改 `src/autoteacher_m0/`、`security/`、`bridge/`、`config/g*`、`scripts/g4*`、LiveGate；A 线不改 M1 | `git diff --name-only 3e7afee..HEAD` + 保护前缀 grep | 159 files changed；保护路径 **0 命中**（NO_PROTECTED_HITS） | `DETERMINISTIC` + `OWNER_REPORTED`；Reviewer 重跑 |
| X-02 | 无真实 Key/外部网络/付费请求；LiveGate 仍 BLOCKED | AST 扫描 `m1_teacher/ tests/m1_teacher/ scripts/m1b/`；socket 阻断 demo/cli 测试 | 网络 import **0**；`autoteacher_m0` 仅出现在隔离断言/注释（13 文本提及，0 import）；无 Key/Provider；LiveGate 未变 | `DETERMINISTIC` + `OWNER_REPORTED`；Reviewer 重跑 |

## 8. 证据包

`docs/m1b_evidence/`（collector 生成；schema `m1b.audit-index.v0`）：

| 内容 | 实测 |
|---|---|
| `audit-index.jsonl` | **16 entries**；sha256 `11a9f5c3820fffa9250a82837b27c555bb0e649d67c0317d2d68e8fb560dfb25` |
| `audit-index.json` | mirror；sha256 `827625b8fbdae6f4e52b10872abaa149c2df163220893a722ff25387da1cb108` |
| `raw/<run_id>/` | 16 个 run 的 `evidence.json` + `stdout.log` + `stderr.log`（合成数据、无 Key/PII/hidden expected） |
| `e2e_b5_*.jsonl` | `cf` 135 行 / `interview` 87 行 / `cross_domain` 86 行 / `freshness` 18 行；hash 见 §9 |
| `e2e_b5_summary.json` | 固定 artifact_manifest；sha256 `387dbfab36b6b6c335dda487becd840babc3808c304d3c5bbcd6b8dfcf3ec123` |

关键 collector entries（`status` 为执行状态，非产品 PASS）：`B5-01-full-suite` EXECUTED_PASS（884 passed）；`B1-05-os-sandbox-gate` 首次 EXECUTED_FAIL（并发 judge suite 的 `/tmp` 前缀冲突：`4 failed, 880 passed`；重跑 `884 passed in 91.96s` EXECUTED_PASS）；`B4-01-02-03-e2e` 9 passed；`B5-01-e2e` 11 passed；`B1-05-certification` 27 passed（112/112）；`B2-01-02-03-crash` 35 passed；`B5-01-demo-double-run` identical True；`B4-01-demo-double-run` identical True；`X-01-scope-diff` / `X-02-network-scan` EXECUTED_PASS；`B5-01-evidence-artifacts` 5 artifacts hashed。

## 9. 证据类与关键哈希

| Artifact | SHA-256 |
|---|---|
| `e2e_b5_cf.jsonl` | `8de98500bb69582bf932dceb25d4938a10ad991c72ccd2dbf18a94a2d5a20626` |
| `e2e_b5_cross_domain.jsonl` | `7c8c5b14f26ae75aba465b94a24bcb5623c01498dd720f710efc60a57f452bef` |
| `e2e_b5_freshness.jsonl` | `efa33f18516f55529df0086acb57e1b5ddae0414bf611516c55ddc5a11fd2608` |
| `e2e_b5_interview.jsonl` | `44b1a07199936efcd6acd15707c89885645d82ce04f713cb12bdbf0f05604f36` |
| `e2e_b5_summary.json` | `387dbfab36b6b6c335dda487becd840babc3808c304d3c5bbcd6b8dfcf3ec123` |
| `audit-index.jsonl` / `.json` | `11a9f5c3…` / `827625b8…` |
| B5 demo stdout | `2d6ce1d293aee434ad7e778e27c0eeeef673ea2c95d3b68794def4f76635361d` |
| B4 demo stdout | `6b7bb66e36a38bd640d5b47d206d8fee24a446df9b42dbe76d20dd8cc50bef83` |

证据类标注：CF/interview/JD/freshness 输入与模拟结果 = `MOCK`；状态机/回放/哈希/门禁 = `DETERMINISTIC`；**学习效果/真实 Provider/网络/Live = `NOT_VERIFIED`/`NOT_RUN`**；无 `HUMAN_REVIEWED` 结论在本报告中（独立 Review 由 Reviewer 出具）。

## 10. NOT_RUN / UNVERIFIED / BLOCKED（真实缺口）

1. B-PR4 独立 Review：`NOT_RUN`（进行中）；B-PR5 独立 Review：`NOT_RUN`（本 PR 待审）。
2. B-PR1 P1-2（宿主非 root principal）`NOT CLOSED`；B1-04 `PARTIAL`；真实用户 CODE **`BLOCKED`**。
3. B-PR1 P1-3 CI 强制接线 `NOT_CONFIGURED`（本 SHA 未含修复；安全 CI 的 `M1B_REQUIRE_OS_SANDBOX=1` 需在最终树重跑）。
4. 真实教学效果、真实学习者、真实模型/Provider、联网研究、真实 JD/简历：`NOT_VERIFIED`/`NOT_RUN`。
5. 非 root 部署、断电/掉盘持久性、真实 auth/多租户隔离、target OS 沙箱验收：`NOT_RUN`。
6. B-PR2 的 2 P1（ADR D12 记录、goal failpoint 范围措辞）与 B-PR3 的 2 P1（legacy digest 兼容、公共 API scoped 查找）在 review 文档中记录；修复/复评状态以各 PR 最终分支为准，本报告未重判。
7. PR1 fix cascade / PR4 final 合入后的数字需重新生成（本报告 SHA `e2b6e85` 为当前集成树）。

## 11. 默认 / 最终结论边界

- **Owner 侧默认结论：`PENDING_INDEPENDENT_REVIEW`**。所有本地门通过且未触发 STOP，但独立 Reviewer 尚未对 B-PR4/B-PR5 出具结论。
- 独立 Reviewer 关闭全部 Gate 后，才允许写：**`PASS_FOR_M1B_OFFLINE_INTEGRATION_SCOPE`**。
- 该结论仅覆盖：离线、合成 fixtures、确定性/mock E2E、独立复跑证据齐全的 M1-B 集成范围。
- **明确不包含**（不得暗示）：真人学习收益/教学效果；联网研究/招聘网站/真实 JD/简历；真实 Provider/LLM 能力；真实 OS 判题安全承诺；Live/LiveGate/授权/生产可用；M0 G4-H/G5/LiveGate/M0 决策变更。
- 人类 Gate 不在本报告范围：H-01/H-02/H-03、G5、LiveGate、M0 决策保持各自状态；B 线无权解除。

## 12. 复现命令（Reviewer 用；最终 SHA 由 Lead 发布）

```bash
cd /root/m1b/pr5
PY="/root/Autonomous Teacher/.venv/bin/python"
"$PY" -m pytest tests/m1_teacher -q                                   # 884 passed
"$PY" -m pytest tests/m1_teacher/test_b5_e2e.py -q                    # 11 passed
"$PY" -m pytest tests/m1_teacher/test_b4_e2e.py -q                    # 9 passed
"$PY" -m pytest tests/m1_teacher/test_judge_correctness.py -q         # 112/112 certification
"$PY" -m pytest tests/m1_teacher/test_crash_recovery.py -q            # real SIGKILL matrix
"$PY" -m m1_teacher.e2e_b5 > /tmp/e2e1; "$PY" -m m1_teacher.e2e_b5 > /tmp/e2e2; cmp /tmp/e2e1 /tmp/e2e2
"$PY" -m m1_teacher.e2e_b5 --write-evidence
sha256sum docs/m1b_evidence/e2e_b5_*.jsonl docs/m1b_evidence/e2e_b5_summary.json
# audit packet: docs/m1b_evidence/audit-index.jsonl + raw/**; validate with
"$PY" - <<'PY'
import hashlib, json
from pathlib import Path
out = Path("docs/m1b_evidence")
for line in (out / "audit-index.jsonl").read_text().splitlines():
    entry = json.loads(line)
    raw = out / entry["raw_evidence_path"]
    assert hashlib.sha256(raw.read_bytes()).hexdigest() == entry["sha256"]
print("audit-index OK", len(entries) if (entries := (out / "audit-index.jsonl").read_text().splitlines()) else 0)
PY
```

> 若在最终冻结 SHA 上任何 hash/count 与 §8/§9 不一致：按 regression 处理，不得沿用本报告 PASS 值。
