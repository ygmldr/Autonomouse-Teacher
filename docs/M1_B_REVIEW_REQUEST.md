# M1-B 维护者审阅请求（B-NEXT / B-PR0…B-PR5 最终交付）

| 字段 | 值 |
|---|---|
| 请求方 | B0 架构文档作者（B-NEXT 交付汇总；本请求不代替独立 Reviewer） |
| 请求日期 | 2026-11-21 UTC |
| 请求对象 | 维护者（最终签收人）+ LeadB（协调/合并） |
| 最终候选树（代码/测试） | **PR5 最终 commit `d9201e9421787f401320a8b9fd6f4c65ac3a5ffd`**（含最终独立评审文档、P1-1/P1-2 修复、939 测试树）；此前 merge `861d147…`（PR4 final `1de6ae6…` + PR5 分支）；本请求所在 docs 分支 `b-next/pr5-final-docs` 基于 `d9201e9`，只做文档勘误（不改代码/测试树） |
| 最终行为代码 / 证据生成 SHA | 行为代码 `12f6290…`（collector P1-1 修复）；P1-2 证据生成 `9c383e5…` / tree `333828d…`；P1-2 evidence commit `580be70…` |
| 最终独立评审 | `docs/M1_B_FINAL_INDEPENDENT_REVIEW.md`：**`PASS_WITH_ACTIONS`**（P0=0 / P1=3 / P2=6）；Owner 侧 P1-1/P1-2 证据修复完成（clean archive 939/0、证据重生成），P1-3 报告数字/哈希/状态勘误即本提交；**delta 复核 `PENDING`** |
| 默认最终结论（仅在全部 Gate 通过且 delta 关闭后） | **`PASS_FOR_M1B_OFFLINE_INTEGRATION_SCOPE`** |
| 结论边界 | 仅覆盖：离线、合成 fixtures、确定性/mock E2E、B-PR0…B-PR5 独立复跑证据；**不包含**真人学习收益/教学效果、联网研究/真实 JD/简历、真实 Provider/LLM、真实 OS 判题安全承诺、Live/LiveGate、生产可用性、M0 G4-H/G5/M0 决策 |
| 请求的裁定 | ① 签收 B0 合同收敛 ADR；② 确认最终集成 SHA 冻结与 GitHub PR/合并顺序；③ 决定 schema v2 与迁移策略；④ 在 **delta 复核关闭 P1** 后审阅是否接受 `PASS_FOR_M1B_OFFLINE_INTEGRATION_SCOPE`；⑤ 人类 Gate（真实用户 CODE/Provider/LiveGate/非 root 部署）保持独立批准 |
| 本文件状态 | `OWNER_REQUEST / 不构成 PASS`；最终数字/状态以 `docs/M1_B_EVALUATION_REPORT.md`（Owner 最终树）与 `docs/M1_B_FINAL_INDEPENDENT_REVIEW.md`（独立 Reviewer）为准 |

> **重要**：本请求不是“已集成完成/已验收”的声明。最终独立评审为 **`PASS_WITH_ACTIONS`**，不是无条件 PASS；P1-1/P1-2/P1-3 的 delta 复核仍 `PENDING`，维护者签收 `PENDING`。历史 `536 + 365` 不得相加（不存在“统一 901”）。

---

## 1. 请求的裁定与验收边界

### 1.1 期望结论

- 若原 final Reviewer 完成 **delta 复核**（P1-1/P1-2/P1-3 关闭），且协议 Gate G1–G8 无 STOP、B0-01…B5-01、X-01/X-02 均有本轮独立证据，则允许：
  **`PASS_FOR_M1B_OFFLINE_INTEGRATION_SCOPE`**。
- 任一 Gate 未过 / P1 未关闭 → 只能写 `PARTIAL_FOR_..._SCOPE` / `FAIL` / `BLOCKED`，并逐项列出未关闭证据（协议 §10）。
- 该结论**明确不包含**：真人学习收益/教学效果；联网研究、真实招聘网站/JD/简历；真实 Provider/LLM；真实 OS 判题安全承诺；Live/LiveGate/授权/生产可用；M0 G4-H/G5/M0 决策变更。

### 1.2 本请求希望维护者确认的 4 件事

1. **签收 B0 合同收敛**：A `m1_teacher` canonical + B vertical + 四端口；D12 add-only 变更（见 §3.1）。
2. **冻结/合并**：将 `b-next/pr5-final-docs`（文档勘误）合入 PR5 最终树后，记录最终 integration/freeze SHA（40 hex）；创建实际 GitHub PR 并确认合并顺序。
3. **schema v2 与迁移策略**：`result_scopes` 为 add-only 但 DB forward-only（旧代码不能读 v2 DB）；确认是否随 B-NEXT 落地、真实 learner DB 是否永久禁止自动迁移（设计为禁止，仅 synthetic/只读副本演练）。
4. **人类 Gate**：真实用户 CODE、真实 Provider/LiveGate、非 root 部署、G4-H/G5 保持独立批准；不因本请求自动解除（见 §6/§7）。

---

## 2. 冻结候选、分支与评审文档

### 2.1 当前候选（以最终 push 为准）

- 代码/测试候选：**`d9201e9`**（PR5 final；含 `861d147`、`c420d19`、`9c383e5`、`12f6290`、`8f8d00e` 系列）。
- 文档分支：`b-next/pr5-final-docs`（基于 `d9201e9`；本请求 + `docs/M1_B_IMPLEMENTATION_REPORT.md` + 少量 P2 精度勘误；不改代码/测试/证据数据）。
- **最终冻结 SHA = 本分支合入 PR5 后的 merge commit（40 hex，Lead/维护者记录）**；不得用分支名代指。代码行为树仍为 `d9201e9`。
- 该快照包含：PR0 文档 + PR1/PR2/PR3/PR4 review-fix（含 PR4 P1 修复 `49cf45b`/`1de6ae6`）+ PR5 B5 统一 E2E/证据/评测报告/最终独立评审。

### 2.2 各 PR 分支、评审文档与结论

| PR | 分支（最终树来源） | 评审文档（路径） | 评审结论 | Review-fix / 当前状态 |
|---|---|---|---|---|
| B-PR0 | `b-next/pr0-convergence-adr` @ `3001d99` | `docs/M1_B_BOUNDARY_PRE_REVIEW.md`；响应 `docs/M1_B_PR0_REVIEW_RESPONSE.md`（在树） | `PRE_REVIEW_PASS_WITH_ACTIONS`（0 P0 / 8 P1 / 13 P2）→ 响应逐条处置；最终评审判 **B0-01 = `PARTIAL`**（正式合同签收 `NOT_RUN`） | 文档修订在树；维护者签收 `PENDING` |
| B-PR1 | 实现 `b-next/pr1-judge-worker` @ `fb6cf33`；修复/附录 `b-next/pr1-trusted-judge` @ `550ad37`（含 `8175233`/`af09cff`） | `docs/M1_B_PR1_REVIEW.md`、`docs/M1_B_PR1_REVIEW_ADDENDUM.md`（均在树） | 首轮 `PASS_WITH_ACTIONS`（P0=0，P1=4）；附录 `P1_ACTIONS_PARTIALLY_CLOSED`；**final tree**：P1-1/P1-4 `CLOSED`；**P1-2 分栏**：实现启动 fail-closed 已存在（`M1B_REQUIRE_NONROOT_SANDBOX`，本机 LOCAL_ONLY）/ 非 root 目标部署 `NOT_RUN`（B1-04 `PARTIAL`）；**P1-3 脚本已接线、`.github` job `NOT_CONFIGURED`（PARTIAL）** | 修复已在 final tree；真实 CODE `BLOCKED` |
| B-PR2 | `b-next/pr2-session-txn` @ `7f9ce06`（含 `10fdaa9`） | `docs/M1_B_PR2_REVIEW.md`（在树） | `PASS_WITH_ACTIONS`（P0=0，P1=2 文档治理、P2=5）；B2-01/02/03 + B-Q2 **VERIFIED**；final tree crash matrix **34 行 9/21/2/2** | 修复 `10fdaa9` 已合入 |
| B-PR3 | `18b08fe`/`2f32f13`/`3103a06`；评审 `b-next/pr3-review` @ `db636ea`；修复 `b-next/pr3-scoped-idempotency` @ `a5373f1`（含 `3ad85c2`） | `docs/M1_B_PR3_REVIEW.md`（在树） | `PASS_WITH_ACTIONS`（P0=0，P1=2、P2=5）；B3-01/B3-02 核心成立；P1-1 legacy digest / P1-2 `apply_assessment` scoped 修复均 `CLOSED` | 修复已合入 final tree |
| B-PR4 | `b-next/pr4-interview-freshness` @ `e265b96`；评审 `b-next/pr4-domain-ports` @ `dfda203`；修复 `49cf45b`/`1de6ae6` | `docs/M1_B_PR4_REVIEW.md`、`M1_B_PR4_REVIEW_RESPONSE.md`（在树） | `PASS_WITH_ACTIONS`（P0=0，P1=3、P2=7）；**P1 修复已合入**：P1-1 会话计划持久化、P1-2 hidden reader 守卫、P1-3 session replay/版本拒绝（`CLOSED（实现面；event-level schema_version 行 PARTIAL）`）；B4-01/02/03 **VERIFIED（E2E-MOCK）**；B4-04 `PARTIAL`、B4-05 `PARTIAL` | 修复已合入；持久 review queue `NOT_IMPLEMENTED` |
| B-PR5 | `b-next/pr5-e2e-eval` final `d9201e9` | **`docs/M1_B_FINAL_INDEPENDENT_REVIEW.md`**（在树）；`docs/M1_B_EVALUATION_REPORT.md`（Owner final tree）；`docs/M1_B_EVALUATION_PROTOCOL.md` | **final review = `PASS_WITH_ACTIONS`（P0=0 / P1=3 / P2=6）**；Owner 侧 P1-1（clean archive）/P1-2（证据绑定）修复完成、P1-3 文档勘误为本提交；**delta 复核 `PENDING`**；**B5-01 在 delta 前保持 `PARTIAL`** | 独立裁定待 delta addendum（命名由 Reviewer/Lead 确定，**未预填**） |

**最终独立评审文档路径**：`docs/M1_B_FINAL_INDEPENDENT_REVIEW.md`（最终 Reviewer；**本请求不修改**）；**delta 复核附录待生成**（建议路径 `docs/M1_B_FINAL_INDEPENDENT_REVIEW_ADDENDUM.md`，以原 Reviewer/Lead 交付为准）。Owner 侧最终树证据在 `docs/M1_B_EVALUATION_REPORT.md`（b-eval 所有）与 `docs/m1b_evidence/`。

> 当前 `b-next/pr5-final-docs` 只做文档勘误；最终冻结 SHA 以 Lead 合入后的 merge commit 为准（`d9201e9` 为代码/测试基线）。

---

## 3. 请维护者审阅的材料

### 3.1 合同与设计

- `docs/M1_B_CONVERGENCE_ADR.md`：A/B 全字段对照、唯一 canonical、四端口、迁移/rollback/checksum、写入者合同。
- `docs/M1_B_PORTS.md`：四端口 schema/信任边界/错误码；FULL_SOLUTION 受限；知识信任 registry。
- `docs/M1_ADR_001_DOMAIN_CONTRACTS.md` §6/§6b：D12 change-log；`docs/M1_ARCHITECTURE.md` §12。
- D12 add-only 事实：`HISTORY_EVENT_TYPE += ASSESSMENT_PREPARED`（B-PR2）、`TURN_ADVANCED`（B-PR4 fix）；`TEACHING_ACTION_KIND += SOCRATIC_QUESTION, ASK_CLARIFICATION`（B-PR4）；schema v2 `result_scopes` 表（B-PR3）为 add-only DDL/迁移，DB forward-only。

### 3.2 实现与测试

- `m1_teacher/assessment/judge/**`、`m1_teacher/assessment/scorer.py`（PR1 信任边界）；`scripts/m1b/run_safety_ci.sh`（PR1 安全 CI 入口）。
- `m1_teacher/learner/repository.py`、`m1_teacher/session/engine.py`（PR2 事务/恢复；PR3 schema v2/幂等；PR4 replay）。
- `m1_teacher/idempotency.py`（PR3 scoped 幂等）。
- `m1_teacher/session/vertical.py`、`m1_teacher/domains/interview.py`、`m1_teacher/knowledge/freshness.py`、`m1_teacher/assessment/interview_judge.py`、`m1_teacher/demo_b4.py`、`m1_teacher/e2e_b5.py`（PR4/PR5 双域闭环）。
- `scripts/m1b/collect_evidence.py`、`docs/M1_B_EVIDENCE_PACKET.md`、`docs/M1_B_EVALUATION_REPORT_TEMPLATE.md`（PR5 证据/评测入口）。
- `tests/m1_teacher/**`（最终树 **939** = 536 基线 + PR1 173 + PR2 63 + PR3 46 + PR4 95 + PR5 26；= PR4 final 913 + PR5 26；strict `M1B_REQUIRE_OS_SANDBOX=1 -rs` 939 passed/0 skipped）。

### 3.3 证据与评审

- 实现汇总 `docs/M1_B_IMPLEMENTATION_REPORT.md`（Owner；最终数字指向 Evaluation Report）。
- Owner 最终树评测报告 `docs/M1_B_EVALUATION_REPORT.md`（b-eval 所有；§13 最终数字、§14 P1 关闭证据）。
- **最终独立评审** `docs/M1_B_FINAL_INDEPENDENT_REVIEW.md`（Reviewer 所有）；delta 附录待生成。
- PR 评审文档（§2.2，均在树）、PR0 响应、PR4 response、威胁模型、interview/freshness 映射、B-PR2 事务设计、B-PR3 幂等设计。
- 证据包：`docs/m1b_evidence/`（在树）；最终哈希见 §5。
- 冻结参考：`docs/M1_B_EVALUATION_REPORT_TEMPLATE.md` §4 历史冻结表；M1-A `536`、M1-Offline `365` 分别独立。

---

## 4. 复跑命令矩阵（供 Reviewer/维护者复核；Owner 实测仅作过渡标注，Gate 由 Reviewer 填）

> C-01..C-13 由独立 Reviewer 在冻结 SHA 的 clean archive 上本轮真实执行；期望值仅为参考，不得把 Owner 过渡值抄成 Reviewer 结论。

### 4.1 前置约定（C-00）

```bash
# 0) 冻结 SHA clean archive；私有 TMPDIR；无网络/无 Key；记录 python/pytest/OS/bwrap 版本。
rm -rf /tmp/m1b-final-review && mkdir -p /tmp/m1b-final-review
git -C <REPO> archive <FROZEN_40_HEX_SHA> | tar -x -C /tmp/m1b-final-review
cd /tmp/m1b-final-review
export TMPDIR=$(mktemp -d)
PY="/root/Autonomous Teacher/.venv/bin/python"
```

- C-00 通过条件：SHA 正确、无 `.git`/未提交文件、`TMPDIR` 私有、无网络/Key、环境变量记录齐全。
- **注意（final tree Owner 实测）**：共享 `/tmp` 残留 `m1b_judge_worker_*` 会使 judge 临时目录清理断言假失败（旧快照默认环境曾 `4 failed / 869 passed`）；final tree 用私有 TMPDIR 串行实测 **939 passed / 0 skipped**，clean archive 同样 **939 / 0 skipped**（P1-1 修复后）。Reviewer 必须使用私有 TMPDIR 或先清理残留。

### 4.2 回归与安全矩阵

| # | 对象 | 命令（模板；cwd=`/tmp/m1b-final-review`） | 期望/历史参考（仅参考） | Owner 过渡状态 |
|---|---|---|---|---|
| C-01 | M1-A 历史基线（独立复跑） | `git archive 4706250 \| tar -x -C /tmp/m1a-base && cd /tmp/m1a-base && "$PY" -m pytest tests/m1_teacher -q` | `536 passed`（历史冻结；final tree 中 5 个 M1-A 测试文件已更新，**不能称“536 原样未改”**） | `NOT_RUN`（本轮由 Reviewer 执行） |
| C-02 | M1-Offline 历史基线（独立复跑） | `cd /root/at-m1-offline && env PYTHONDONTWRITEBYTECODE=1 "$PY" -m pytest tests/m1_offline -q -p no:cacheprovider` | `365 passed`（历史冻结；**不加入 C-03 计数**） | `NOT_RUN` |
| C-03 | 新 B 集成套件（最终树全部测试） | `TMPDIR=$(mktemp -d) "$PY" -m pytest tests/m1_teacher -q -p no:cacheprovider`；strict 加 `M1B_REQUIRE_OS_SANDBOX=1 -q -rs` | **final tree 939 passed / 0 skipped**；clean archive（无 `.git`）full/strict **939 / 0 skipped**；历史 536/365 不相加 | `OWNER_REPORTED`（final tree） |
| C-04 | 分 PR 计数/归组 | `pytest tests/m1_teacher --collect-only -q` + 按文件归组 | **939 = 536 基线 + PR1 173 + PR2 63 + PR3 46 + PR4 95 + PR5 26**（= PR4 final 913 + PR5 26）；每 skip 须写理由 | `OWNER_REPORTED` |
| C-05 | Judge 安全负例/正确性 | `pytest tests/m1_teacher/test_judge_supervisor.py test_judge_worker.py test_judge_sandbox.py test_judge_negatives.py test_judge_correctness.py test_judge_fixture_integrity.py test_hidden_leakage_scan.py test_judge_ci_gate.py -q` | B1-01..06 负例矩阵；默认 blocked；伪造 PASS 全拒；112/112 hidden cases；无 sentinel 泄漏 | `NOT_RUN` |
| C-06 | 安全 CI gate（OS 证据不可 skip） | `PYTHON="$PY" ./scripts/m1b/run_safety_ci.sh`（默认 `M1B_REQUIRE_OS_SANDBOX=1 M1B_REQUIRE_NONROOT_SANDBOX=1`，断言 exit 0 + 0 skipped）；本地 root 合成可用 `--allow-root-synthetic`（**不是部署安全证据**） | 脚本已在 final tree；strict 直接运行 **939 passed / 0 skipped**；`.github` job **`NOT_CONFIGURED`**（需 CI owner 接线）；非 root 目标部署 `NOT_RUN` | `NOT_RUN`（Owner 过渡：脚本可用，`.github` 未配置） |
| C-07 | 事务/崩溃/恢复 | `M1B_MATRIX_OUT=/tmp/m1b_matrix_final.jsonl "$PY" -m pytest tests/m1_teacher/test_crash_recovery.py -q`；另跑 `test_turn_transaction.py test_concurrency.py` | B2-01/02/03 + B-Q2；真实 SIGKILL；**matrix 34 行 9/21/2/2**；重复恢复 0 events；旧 32 行/旧 hash 仅历史 | `NOT_RUN` |
| C-08 | Scoped 幂等/迁移 | `"$PY" -m pytest tests/m1_teacher/test_scoped_idempotency.py tests/m1_teacher/test_scope_migration.py -q`（并复跑 PR3 评审负例） | B3-01/B3-02；同键幂等、异 payload 冲突、跨 learner/session 不可读；legacy v1→v2 迁移；final tree 31+15=46 passed | `NOT_RUN` |
| C-09 | B4 双域 E2E / JD / freshness / durability | `"$PY" -m pytest tests/m1_teacher/test_b4_e2e.py tests/m1_teacher/test_b4_durability_replay.py tests/m1_teacher/test_vertical_policy.py tests/m1_teacher/test_interview_domain.py tests/m1_teacher/test_interview_fixtures.py tests/m1_teacher/test_interview_judge.py tests/m1_teacher/test_freshness_service.py -q` | B4-01/02/03；JD v1→v2 新计划隔离；RECHECK/JD 门零写入；4 维 rubric；无 FULL；session replay/版本拒绝；B4-04/05 限制保留 | `NOT_RUN` |
| C-10 | Demo 双跑（A / B4 / B5） | `"$PY" -m m1_teacher.demo` ×2、`demo_b4 --json` ×2、`e2e_b5` ×2；各自 `cmp` + `sha256sum` + `wc -lc` | A：`b08ceee9…`，53 行 / 5,798 bytes；B4：**`b3231658…`，513 行 / 15,340 bytes**；B5：**`4d0e0c85…`，27 行 / 4,168 bytes**；均逐字节相同 | `OWNER_REPORTED`（本轮实测一致） |
| C-11 | 证据收集器 + 证据包校验 | 按 `docs/M1_B_EVIDENCE_PACKET.md` §7 用 `scripts/m1b/collect_evidence.py` 登记/校验（raw sha256/append-only/物化视图/无 hashless PASS/artifact manifest）；clean archive 场景验证 `--git-sha/--tree-sha` 绑定 | 最终 `audit-index.jsonl` 38 条（旧 27 历史 + 新 11 clean）；哈希见 §5；每个结论有 case_id/command/sha256/limitation | `OWNER_REPORTED`（final tree；Reviewer 需复算） |
| C-12 | 静态/边界扫描 | `git diff --name-status main...HEAD`、`git diff --name-only 4706250..HEAD`（保护路径 0）；网络 import grep；`scoring/`/`hidden` 运行时导出扫描（非仅 AST）；`ruff check m1_teacher tests/m1_teacher` | **X-01：302 files vs main（302 A/0 M/0 D）、243 files vs M1-A；保护前缀 0 命中**；无 M0/network/Key；teacher-visible 无 hidden 内容；ruff clean | `OWNER_REPORTED`（final tree） |
| C-13 | 最终评测/评审报告填充 | 按 `docs/M1_B_EVALUATION_REPORT_TEMPLATE.md` 填 C-01..C-12；引用 `docs/M1_B_FINAL_INDEPENDENT_REVIEW.md` 与 delta 附录 | 只有 delta P1 关闭 + 全 Gate 通过才允许 `PASS_FOR_M1B_OFFLINE_INTEGRATION_SCOPE`；否则 `PARTIAL/FAIL/BLOCKED` | `NOT_RUN`（delta `PENDING`） |

### 4.3 计数纪律

- C-03 必须是**本树**计数；C-01/C-02 是**历史独立**参考，不得相加；最终树计数在 `M1_B_EVALUATION_REPORT.md` 单独列出。
- 每个 skip/fail 都要写理由与 evidence class；0 skipped 不能靠静默过滤获得。
- `536` 是历史基线计数；final tree 中 5 个 M1-A 测试文件已按 D12/去 flake 更新，不能写成“536 原样未改”。

---

## 5. 证据包位置与 hash 校验方式

- **最终包（在树）**：`docs/m1b_evidence/`；结构 = `audit-index.jsonl`（append-only 权威索引，38 条）+ `audit-index.json`（物化视图，entry_count=38）+ `raw/<run_id>/{evidence.json,stdout.log,stderr.log}` + B5 5 个 evidence 文件 + summary。
- **最终哈希（Owner 本轮 `sha256sum` 与 Evaluation Report §13 一致）**：
  - `audit-index.jsonl`：**`a11ce42948d5dd43563a1bf6befa8bb7c8600ba3b73f9df32e345b07bc66ea80`**
  - `audit-index.json`：**`8db875301cc10f5af3af4f038b42d50a43a9291ac50c96719f7fd9ce37fc34e5`**
  - `e2e_b5_summary.json`：**`a07cfe7ec06208bc3271e01eaaf62a6145c753bf175b23c844658c756d444053`**
  - `e2e_b5_cf.jsonl` `526f9dfd…`、`e2e_b5_interview.jsonl` `8f3a16fc…`、`e2e_b5_cross_domain.jsonl` `c02723ec…`、`e2e_b5_freshness.jsonl` `8a25de6e…`（四文件不变）
- **append-only 语义**：旧 27 条（16 过渡 + 11 `c420d19` 窗口）字节保留；final 11 条（28–38）由 P1-2 在 clean worktree 生成（`git_sha=9c383e5…`、`tree_sha=333828d…`、generation-start clean=true）；旧 27 条前缀 sha `4b9a0d0e…` 不变。
- **每条记录必含**：`case_id`、`branch`、`git_sha`（或 `null` + `git_available=false` + `git_sha_source`）、`command`/`command_argv`、`environment`、`utc`、`exit_code`、`status`、`raw_evidence_path`、`sha256`、`limitation`（非 PASS 必填）。
- **校验**（`docs/M1_B_EVIDENCE_PACKET.md` §7）：raw sha256 ↔ 索引；append-only 旧行字节不变；`audit-index.json` 与 jsonl 一致；无 command-less/hashless PASS；artifact manifest sha256 一致；clean archive 下 `--git-sha/--tree-sha` 绑定。
- **禁止**：无 hash 的“PASS”；把 `EXECUTED_PASS` 当产品 PASS；`NOT_RUN/BLOCKED` 改写成 PASS；历史 536/365 相加；缺失失败/负面样例（协议 §11.4）。

---

## 6. 已知限制、STOP 清单与不可声称项

### 6.1 不可声称（必须保留在最终报告）

1. 真实学习效果/教学收益 **`NOT_VERIFIED`**（全部确定性启发式 + synthetic 输入）。
2. 真实 Provider/LLM/联网研究/真实 JD/简历 **`BLOCKED`**；无 Key、无付费请求。
3. 真实 OS 判题安全承诺 / 生产可用性 **`UNVERIFIED`**；B1-04 目标部署非 root **`NOT_RUN`**；真实用户 CODE **`BLOCKED`**。
4. 断电持久性 **`UNVERIFIED`**（仅 SIGKILL 进程崩溃矩阵）；分布式/多主机并发 **`NOT_RUN`**。
5. `FULL_SOLUTION`、持久 review queue/审批 UI 未实现（结构上 fail-closed，不等于已交付）；event-level `schema_version` 拒绝 `NOT_IMPLEMENTED`（B4-05 `PARTIAL`）。
6. B4-04 完整双向跨域、真实 hidden 评测集转换均 `NOT_RUN`。
7. 阈值（加速 0.25/证据 2、hint cap、interview ladder）**`UNCALIBRATED`**。
8. **最终独立评审 = `PASS_WITH_ACTIONS`，不是无条件 PASS；delta 复核 `PENDING`**；B0-01 正式签收 `NOT_RUN`；真实 auth/多租户 `NOT_RUN`。

### 6.2 立即 STOP 条件（任一命中即停止复跑，协议 §12.1）

1. 发现真实 API Key/凭证、真实 Provider/SDK/付费请求。
2. 任何外部网络访问（运行期或测试）。
3. 未批准修改保护路径：`src/autoteacher_m0/`、`security/`、`bridge/`、`config/g*`、`scripts/g4*`、LiveGate/账本/授权路径。
4. 证据分类错误（`MOCK` 当真实收益、`OWNER_REPORTED` 当 `INDEPENDENTLY_REEXECUTED`、`NOT_RUN/BLOCKED/UNVERIFIED` 改 PASS、536+365 相加）。
5. 无哈希/不可复现证据当 PASS；artifact hash 与声明不符且未解释。
6. 跨 learner/session 数据泄漏或可能泄漏。
7. 可伪造 PASS 的 CODE Judge 默认暴露给不可信输入；hidden expected 进入 Worker/Teacher 可见输出。
8. 在主机直接执行恶意/sentinel PoC（非隔离 Worker）。
9. 删除/跳过/弱化断言、修改冻结测试期望/fixtures 以“通过”。
10. 试图解锁 LiveGate／触发真实模型授权／改变 M0 G4-H/G5/M0 决策。

### 6.3 当前已知缺口（须在最终报告逐项裁决）

- 最终独立评审 P1-1/P1-2 已由 Owner 修复并附证据；P1-3 报告数字/哈希/状态勘误即本提交；**原 Reviewer 的 delta 复核 `PENDING`**（B5-01 保持 `PARTIAL`）。
- `.github` 安全 job **`NOT_CONFIGURED/NOT_RUN`**；`run_safety_ci.sh` 已在树，需 CI owner 接线；非 root 目标部署 `NOT_RUN`。
- 持久 review queue/审批 UI `NOT_IMPLEMENTED`；event-level `schema_version` 拒绝 `NOT_IMPLEMENTED`（B4-05 `PARTIAL`）。
- 旧证据 27 条保留为历史（不得删除）；final 11 条绑定 clean SHA/tree；Reviewer delta 需复算哈希与绑定。
- 文档残留：ADR §5 “optional fields…” 旧措辞（未在本文档范围改动，需维护者复核）；`docs/M1_ARCHITECTURE.md` §14 已在本提交更新为 v2（见 §2.2 同批 P2 精度修正）。

---

## 7. 需要人类批准/决策的事项

| # | 事项 | 当前状态 | 建议决策者 |
|---|---|---|---|
| H-01 | 真实用户 CODE 开放（不可信代码判题） | **`BLOCKED`**：需人类批准 + 目标部署安全验收（非 root、bwrap、CI gate 接线） | 维护者 + 安全负责人 |
| H-02 | 真实 Provider/LLM/联网研究/LiveGate | **`BLOCKED`**：本线无 Key/网络；不在 M1-B 离线范围 | 维护者 |
| H-03 | 非 root 部署 principal 验收 | **`NOT_RUN`**：需专用非 root 服务账号或 setuid bwrap + 目标机复跑 | 维护者 + 部署负责人 |
| H-04 | G4-H/G5/M0 决策变更 | 不在本请求范围，保持原状态 | 维护者/上游线负责人 |
| H-05 | 签收 B0 合同收敛 ADR（A canonical + B vertical + 四端口） | 待签收（B0-01 `PARTIAL`） | 维护者 + LeadB |
| H-06 | 创建 GitHub PR 并确认合并顺序（PR0→PR5 + review-fix + docs 勘误） | 当前仅本地分支 | 维护者/LeadB |
| H-07 | schema v2 / 迁移策略（forward-only；禁止真实 learner DB 自动迁移） | 实现为 add-only v2 + v1→v2 迁移；真实 DB 永久禁止自动迁移 | 维护者 + LeadB |
| H-08 | 最终 `PASS_FOR_M1B_OFFLINE_INTEGRATION_SCOPE` 签收 | **`PENDING`**：final review `PASS_WITH_ACTIONS`；Owner P1-1/P1-2 修复 + P1-3 文档勘误已交付；**待原 Reviewer delta 复核** | 维护者 |

---

## 8. 建议维护者动作（按顺序）

1. **签收 B0 ADR/端口/CI 文档**（H-05），确认“A canonical + B vertical + 四端口 + D12 add-only + schema v2”裁决。
2. **合入文档勘误分支**（H-06）：将 `b-next/pr5-final-docs`（本请求 + 实现报告 + P2 精度修正）合入 PR5 最终树；按 PR0→PR5 顺序创建/审阅 GitHub PR（PR1 含 `550ad37`、PR2 `10fdaa9`、PR3 `a5373f1`、PR4 `49cf45b`/`1de6ae6`、PR5 `d9201e9`）。
3. **请求原 final Reviewer 的 delta 复核**：对 P1-1（clean archive/collector 可移植性）、P1-2（证据绑定最终树）、P1-3（报告数字/哈希/状态 errata）逐项关闭，产出 delta 附录；B5-01 在此之前保持 `PARTIAL`。
4. **决定 schema v2/迁移策略**（H-07）：确认 forward-only 与“真实 learner DB 禁止自动迁移”；如需真实迁移，另立人类批准的 runbook。
5. **维持人类 Gate**（H-01..H-04）：真实 CODE、Provider/LiveGate、非 root 部署、G4-H/G5 不随本请求自动解除；CI 安全 job 由 CI owner 接线 `scripts/m1b/run_safety_ci.sh`。
6. **仅在 delta 复核关闭 P1 且全 Gate 通过后**签收 H-08；否则只能接受 `PARTIAL_FOR_..._SCOPE` / `BLOCKED`。

---

## 9. 请求的完成定义（Definition of Done）

- [ ] 维护者签收 H-05（B0 ADR）。
- [ ] 最终 integration/freeze SHA 已确定并由 Reviewer 记录（40 hex；代码树 `d9201e9` + docs 勘误 merge）。
- [ ] PR1/PR3/PR4 review-fix 与评审文档全部合入；PR4 P1-1..P1-3 关闭或明确降级（final tree 已合入）。
- [ ] 原 final Reviewer 完成 **delta 复核（P1-1/P1-2/P1-3）**；B5-01 结论更新。
- [ ] `docs/M1_B_EVALUATION_REPORT.md` 与 `docs/M1_B_FINAL_INDEPENDENT_REVIEW.md` 的数字/哈希/状态一致；证据包 §5 校验通过。
- [ ] B0-01、B1-01..06、B2-01..03、B3-01/02、B4-01..03、B5-01、X-01/X-02 逐项有独立证据；未通过项显式保留。
- [ ] 维护者确认 §6.1 不可声称项全部保留；历史 536/365 未相加；真实收益/Provider/Live 未混写。
- [ ] 人类 Gate（§7）保持原状态或由对应批准人单独签署。

> 本请求**不代表** M1-B 已验收或已可合并；最终独立评审为 `PASS_WITH_ACTIONS`，delta 复核与维护者签收仍 `PENDING`，最终裁定由原 Reviewer delta 与维护者共同给出。

---

## 10. 变更记录

| 日期（UTC） | 版本 | 变更 |
|---|---|---|
| 2026-11-20 | v0 | 初稿：审阅请求、候选 SHA/分支、复跑矩阵、证据包校验、限制/STOP/人类 Gate、维护者动作 |
| 2026-11-21 | **v1** | **final-tree / final-review P1-3 勘误**：候选树 `d9201e9`、939 计数与 clean archive 939/0、B4/B5 demo 最终哈希与字节数、证据包最终哈希（38 条）、PR4 P1 修复“已合入 49cf45b/1de6ae6”、PR1 P1-2 分栏/P1-3 脚本接线、PR2 crash 34 行、X-01 302/243、评审文档清单含 `M1_B_FINAL_INDEPENDENT_REVIEW.md` 与 delta `PENDING`；C-06/C-10 等期望值更新；仍为 OWNER_REQUEST，不构成 PASS |
