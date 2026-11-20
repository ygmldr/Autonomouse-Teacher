# M1-B 维护者审阅请求（B-NEXT / B-PR0…B-PR5 最终交付）

| 字段 | 值 |
|---|---|
| 请求方 | B0 架构文档作者（B-NEXT 交付汇总；本请求不代替独立 Reviewer） |
| 请求日期 | 2026-11-20 UTC |
| 请求对象 | 维护者（最终签收人）+ LeadB（协调/合并） |
| 最终集成快照（候选） | PR4 final `1de6ae6d3714ab815c47022e4c2cceee107db979` 合入 PR5 后的 merge commit **`861d147d…`**；B5 实现提交 `c420d19…`；PR5 最终 commit SHA 由 Lead 记录/回填 |
| 默认最终结论（仅在全部 Gate 通过时） | **`PASS_FOR_M1B_OFFLINE_INTEGRATION_SCOPE`** |
| 结论边界 | 仅覆盖：离线、合成 fixtures、确定性/mock E2E、B-PR0…B-PR5 独立复跑证据；**不包含**真人学习收益/教学效果、联网研究/真实 JD/简历、真实 Provider/LLM、真实 OS 判题安全承诺、Live/LiveGate、生产可用性、M0 G4-H/G5/M0 决策 |
| 请求的裁定 | ① 签收 B0 合同收敛 ADR；② 确认最终集成 SHA 冻结与 GitHub PR/合并顺序；③ 决定 schema v2 与迁移策略；④ 在独立评测报告完成后审阅是否接受 `PASS_FOR_M1B_OFFLINE_INTEGRATION_SCOPE`；⑤ 人类 Gate（真实用户 CODE/Provider/LiveGate/非 root 部署）保持独立批准 |
| 本文件状态 | `OWNER_REQUEST / 不构成 PASS`；所有最终数字/状态由独立 Reviewer 复跑填写 |

> **重要**：本请求不是“已集成完成/已验收”的声明。当前快照仍有 PR1/PR3/PR4 review-fix 待合入、PR4 P1 待修复、PR5 最终独立评测报告待产出；最终数字一律以 `docs/M1_B_EVALUATION_REPORT.md`（冻结 SHA 上实测）为准。历史 `536 + 365` 不得相加（不存在“统一 901”）。

---

## 1. 请求的裁定与验收边界

### 1.1 期望结论

- 若独立 Reviewer 在冻结 SHA 上全部通过协议 Gate G1–G8、无 STOP、且 B0-01…B5-01、X-01/X-02 均有本轮独立证据，则允许：
  **`PASS_FOR_M1B_OFFLINE_INTEGRATION_SCOPE`**。
- 任一 Gate 未过 → 只能写 `PARTIAL_FOR_..._SCOPE` / `FAIL` / `BLOCKED`，并逐项列出未关闭证据（协议 §10）。
- 该结论**明确不包含**：真人学习收益/教学效果；联网研究、真实招聘网站/JD/简历；真实 Provider/LLM；真实 OS 判题安全承诺；Live/LiveGate/授权/生产可用；M0 G4-H/G5/M0 决策变更。

### 1.2 本请求希望维护者确认的 4 件事

1. **签收 B0 合同收敛**：A `m1_teacher` canonical + B vertical + 四端口；D12 add-only 变更（见 §3.1）。
2. **冻结/合并**：按 §2 的分支与顺序创建实际 GitHub PR，合入 review-fix/评审文档后给最终 integration/freeze SHA。
3. **schema v2 与迁移策略**：`result_scopes` 为 add-only 但 DB forward-only（旧代码不能读 v2 DB）；确认是否随 B-NEXT 落地、真实 learner DB 是否永久禁止自动迁移（设计为禁止，仅 synthetic/只读副本演练）。
4. **人类 Gate**：真实用户 CODE、真实 Provider/LiveGate、非 root 部署、G4-H/G5 保持独立批准；不因本请求自动解除（见 §6/§7）。

---

## 2. 冻结候选、分支与评审文档

### 2.1 当前候选（以最终 push 为准）

- 最终集成分支：`b-next/pr5-e2e-eval`，PR4 final `1de6ae6d…` 合入后的 merge commit **`861d147d…`**（B5 实现提交 `c420d19…`）；PR5 最终 commit SHA = 本 branch HEAD（Lead 记录/回填）。
- 该快照包含：PR0 文档 + PR1/PR2/PR3 review-fix tree + PR4 final（P1 修复）+ PR5 B5 统一 E2E/证据/评测报告。
- **最终冻结 SHA = `861d147d…`（集成树）+ PR5 最终 commit SHA**：所有最终证据必须绑定 40-hex SHA（不得用分支名代指）。

### 2.2 各 PR 分支、评审文档与结论

| PR | 分支（本轮 tip） | 评审文档（路径 @ 所在分支/commit） | 评审结论 | Review-fix 状态 |
|---|---|---|---|---|
| B-PR0 | `b-next/pr0-convergence-adr` @ `3001d99` | `docs/M1_B_BOUNDARY_PRE_REVIEW.md`（预审，在树）；响应 `docs/M1_B_PR0_REVIEW_RESPONSE.md`（`3001d99`） | `PRE_REVIEW_PASS_WITH_ACTIONS`（0 P0 / 8 P1 / 13 P2）→ 响应逐条处置；B0-01 独立合同验收仍 `NOT_RUN` | 文档修订已提交；最终需按协议 G1–G8 复核 |
| B-PR1 | 实现 `b-next/pr1-judge-worker` @ `fb6cf33`；修复/附录 `b-next/pr1-trusted-judge` @ `550ad37`（含 `8175233`/`af09cff`） | `docs/M1_B_PR1_REVIEW.md` @ `62c32c5`（分支 `b-next/pr1-review`）；`docs/M1_B_PR1_REVIEW_ADDENDUM.md` @ `af09cff` | 首轮 `PASS_WITH_ACTIONS`（P0=0，P1=4）；附录 `P1_ACTIONS_PARTIALLY_CLOSED`（P1-1/P1-4 closed；P1-3 机制关闭但 CI 未接线；P1-2 未关闭）；`550ad37` 补 P1-2 启动 fail-closed + P1-3 仓库安全 CI 脚本 | **待合入当前快照 + 独立复评**（B1-04 仍 `PARTIAL`，目标部署 `NOT_RUN`；真实 CODE `BLOCKED`） |
| B-PR2 | `b-next/pr2-session-txn` @ `7f9ce06`（含 `10fdaa9` 修复） | `docs/M1_B_PR2_REVIEW.md` @ `434f731`（在树） | `PASS_WITH_ACTIONS`（P0=0，P1=2 文档治理、P2=5）；B2-01/02/03 + B-Q2 **VERIFIED** | 修复 `10fdaa9` **已在当前树**（P1/P2 关闭） |
| B-PR3 | 实现 `18b08fe`/`2f32f13`/`3103a06`；评审 `b-next/pr3-review` @ `db636ea`；修复 `b-next/pr3-scoped-idempotency` @ `a5373f1`（含 `3ad85c2`） | `docs/M1_B_PR3_REVIEW.md` @ `db636ea`（分支 `b-next/pr3-review`） | `PASS_WITH_ACTIONS`（P0=0，P1=2、P2=5）；B3-01/B3-02 核心成立 | **P1/P2 修复待合入 + 复评**（P1-1 legacy digest 投影、P1-2 `history.apply_assessment` 全局查找） |
| B-PR4 | 实现 `b-next/pr4-interview-freshness` @ `e265b96`；评审 `b-next/pr4-domain-ports`/`b-next/pr4-review` @ `dfda203` | `docs/M1_B_PR4_REVIEW.md` @ `dfda203` | `PASS_WITH_ACTIONS`（P0=0，P1=3、P2=7）；B4-01/02/03 为 **VERIFIED（E2E-MOCK，带限制）**；B4-04 部分、B4-05 `NOT_RUN` | **修复尚未创建/合入**：P1-1 持久化 interview 阶段计划；P1-2 hidden reader/`reference_answers.json`；P1-3 session replay/版本拒绝（或降级声明） |
| B-PR5 | `b-next/pr5-e2e-eval` @ `861d147`/`c420d19`（最终树） | **`docs/M1_B_EVALUATION_REPORT.md`（Owner FINAL_TREE_MEASURED；938 passed/strict 0 skipped；final evidence hashes）**；协议 `docs/M1_B_EVALUATION_PROTOCOL.md` | 最终独立评审 **`PENDING`（Lead 指派）**；`B5-01` 待独立 Reviewer 复跑 | 报告 §13 已填 owner 最终数字；独立裁定由 Reviewer 给出 |

**最终独立评审文档路径**：本轮请求的最终评测报告为 `docs/M1_B_EVALUATION_REPORT.md`（模板 `docs/M1_B_EVALUATION_REPORT_TEMPLATE.md`，由独立 Reviewer 在冻结 SHA 上填充）；若 LeadB/维护者另指定独立评审文档（如 `docs/M1_B_INDEPENDENT_REVIEW.md`），以该指定路径为准，但最终裁定仍必须引用本评测报告与证据包。

> 评审文档与修复分支**尚未全部合入**当前候选快照；因此当前 `e2b6e85` 不是最终冻结 SHA，审阅请求必须在修复合并后重新固定 SHA 并重跑矩阵。

---

## 3. 请维护者审阅的材料

### 3.1 合同与设计

- `docs/M1_B_CONVERGENCE_ADR.md`：A/B 全字段对照、唯一 canonical、四端口、迁移/rollback/checksum、写入者合同。
- `docs/M1_B_PORTS.md`：四端口 schema/信任边界/错误码；FULL_SOLUTION 受限；知识信任 registry。
- `docs/M1_ADR_001_DOMAIN_CONTRACTS.md` §6/§6b：D12 change-log；`docs/M1_ARCHITECTURE.md` §12。
- D12 add-only 事实（已核实）：`HISTORY_EVENT_TYPE += ASSESSMENT_PREPARED`（B-PR2）；`TEACHING_ACTION_KIND += SOCRATIC_QUESTION, ASK_CLARIFICATION`（B-PR4）；schema v2 `result_scopes` 表（B-PR3）为 add-only DDL/迁移，DB forward-only。

### 3.2 实现与测试

- `m1_teacher/assessment/judge/**`、`m1_teacher/assessment/scorer.py`（PR1 信任边界）。
- `m1_teacher/learner/repository.py`、`m1_teacher/session/engine.py`（PR2 事务/恢复；PR3 schema v2/幂等）。
- `m1_teacher/idempotency.py`（PR3 scoped 幂等）。
- `m1_teacher/session/vertical.py`、`m1_teacher/domains/interview.py`、`m1_teacher/knowledge/freshness.py`、`m1_teacher/assessment/interview_judge.py`、`m1_teacher/demo_b4.py`（PR4 双域闭环）。
- `scripts/m1b/collect_evidence.py`、`docs/M1_B_EVIDENCE_PACKET.md`、`docs/M1_B_EVALUATION_REPORT_TEMPLATE.md`（PR5 证据/评测入口）。
- `tests/m1_teacher/**`（最终树 **938** = PR4 final 913 + PR5 25（B5 11 + collector 14）；strict `M1B_REQUIRE_OS_SANDBOX=1 -rs` 938 passed/0 skipped；以评测报告 §13 为准）。

### 3.3 证据与评审

- 本报告 `docs/M1_B_IMPLEMENTATION_REPORT.md`（Owner 汇总；最终数字以 `docs/M1_B_EVALUATION_REPORT.md` §13 最终树实测为准）。
- PR 评审文档（按 §2.2 路径；部分在分支）、PR0 响应、威胁模型、interview/freshness 映射、B-PR2 事务设计、B-PR3 幂等设计、B-PR4 vertical 实现记录。
- 证据包：`scripts/m1b/collect_evidence.py` 生成的 `audit-index.jsonl` + `raw/`（建议最终位置 `/root/m1b_evidence/B5-01/`，以 Reviewer 报告为准）。
- 冻结参考：`docs/M1_B_EVALUATION_REPORT_TEMPLATE.md` §4 历史冻结表；M1-A `536`、M1-Offline `365` 分别独立。

---

## 4. 复跑命令矩阵（供 Reviewer/维护者复核；初始状态全部 `NOT_RUN`）

> 所有 C 行由独立 Reviewer 在冻结 SHA 的 clean archive 上本轮真实执行；Owner 快速验证数字只作过渡标注，不得进入 Gate。历史期望值仅参考，不得抄为本轮结果。

### 4.1 前置约定（C-00）

```bash
# 0) 冻结 SHA clean archive；私有 TMPDIR（避免共享 /tmp 的 judge 临时目录假失败）；
#    禁用网络/无 Key；git status 为空；记录 python/pytest/OS/bwrap 版本。
rm -rf /tmp/m1b-final-review && mkdir -p /tmp/m1b-final-review
git -C <REPO> archive <FROZEN_40_HEX_SHA> | tar -x -C /tmp/m1b-final-review
cd /tmp/m1b-final-review
export TMPDIR=$(mktemp -d)
PY="/root/Autonomous Teacher/.venv/bin/python"
```

- C-00 通过条件：SHA 正确、无 `.git`/未提交文件、`TMPDIR` 私有、无网络/Key、环境变量记录齐全。
- **注意（final tree 实测）**：共享 `/tmp` 残留 `m1b_judge_worker_*` 会使 judge 临时目录清理断言假失败（旧快照默认环境曾 `4 failed / 869 passed`）；final tree 用私有 TMPDIR 串行实测 **938 passed / 0 skipped**。最终 Reviewer 必须使用私有 TMPDIR 或先清理残留，且不得把该假失败写成产品回归。

### 4.2 回归与安全矩阵

| # | 对象 | 命令（模板；cwd=`/tmp/m1b-final-review`） | 期望/历史参考（仅参考） | 本轮状态 |
|---|---|---|---|---|
| C-01 | M1-A 历史基线（独立复跑） | `git archive 4706250 \| tar -x -C /tmp/m1a-base && cd /tmp/m1a-base && "$PY" -m pytest tests/m1_teacher -q` | `536 passed`（历史冻结；Reviewer 曾独立确认 16.41s） | `NOT_RUN`（本轮由 Reviewer 执行） |
| C-02 | M1-Offline 历史基线（独立复跑） | `cd /root/at-m1-offline && env PYTHONDONTWRITEBYTECODE=1 "$PY" -m pytest tests/m1_offline -q -p no:cacheprovider` | `365 passed`（历史冻结；**不加入 C-03 计数**） | `NOT_RUN` |
| C-03 | 新 B 集成套件（最终树全部测试） | `TMPDIR=$(mktemp -d) "$PY" -m pytest tests/m1_teacher -q -p no:cacheprovider` | **final tree 938 passed**（clean TMPDIR）；strict `M1B_REQUIRE_OS_SANDBOX=1 -q -rs` 938 passed/0 skipped；历史 536/365 不相加 | `OWNER_REPORTED`（final tree） |
| C-04 | 分 PR 计数/归组 | `pytest tests/m1_teacher --collect-only -q` + 按文件归组 | **final tree 938 = PR4 final 913 + PR5 25（B5 11 + collector 14）**；每 skip 须写理由 | `OWNER_REPORTED` |
| C-05 | Judge 安全负例/正确性 | `pytest tests/m1_teacher/test_judge_supervisor.py test_judge_worker.py test_judge_sandbox.py test_judge_negatives.py test_judge_correctness.py test_judge_fixture_integrity.py test_hidden_leakage_scan.py -q` | B1-01..06 负例矩阵；默认 blocked；伪造 PASS 全拒；112/112 hidden cases；无 sentinel 泄漏 | `NOT_RUN` |
| C-06 | 安全 CI gate（要求 OS 证据不可 skip） | 合入 PR1 修复后：`PYTHON="$PY" ./scripts/m1b/run_safety_ci.sh`（默认 `M1B_REQUIRE_OS_SANDBOX=1 M1B_REQUIRE_NONROOT_SANDBOX=1`，断言 exit 0 + 0 skipped）；仅本地 root 合成可用 `--allow-root-synthetic`（**不是部署安全证据**） | 脚本在 PR1 修复分支 `550ad37`；当前快照 **`NOT_CONFIGURED`**（无脚本/env）；`.github` job 未配置，需维护者接线 | `NOT_RUN` / `NOT_CONFIGURED` |
| C-07 | 事务/崩溃/恢复 | `M1B_MATRIX_OUT=/tmp/m1b_matrix_final.jsonl pytest tests/m1_teacher/test_crash_recovery.py -q`；`pytest tests/m1_teacher/test_turn_transaction.py test_concurrency.py -q` | B2-01/02/03 + B-Q2；真实 SIGKILL；matrix 分组 9/21/2、hash 77c620…/ec99d5…/bbd500…；重复恢复 0 events | `NOT_RUN` |
| C-08 | Scoped 幂等/迁移 | `pytest tests/m1_teacher/test_scoped_idempotency.py tests/m1_teacher/test_scope_migration.py -q`（并复跑 PR3 评审负例） | B3-01/B3-02；同键幂等、异 payload 冲突、跨 learner/session 不可读；legacy v1→v2 迁移 | `NOT_RUN`（PR3 修复需先合入） |
| C-09 | B4 双域 E2E / JD / freshness | `pytest tests/m1_teacher/test_b4_e2e.py test_vertical_policy.py test_interview_domain.py test_interview_fixtures.py test_interview_judge.py test_freshness_service.py -q` | B4-01/02/03；JD v1→v2 新计划隔离；RECHECK/JD 门零写入；4 维 rubric；无 FULL | `NOT_RUN`（PR4 修复需先合入） |
| C-10 | Demo 双跑（A 与 B4） | `python -m m1_teacher.demo ×2 + cmp + sha256sum`；`python -m m1_teacher.demo_b4 --json ×2 + cmp + sha256sum` | A：`b08ceee9…`，53 行；B4：`6b7bb66e…`，511 行 / 15,108 bytes；两次逐字节相同 | `NOT_RUN`（Owner 过渡：本轮实测一致） |
| C-11 | 证据收集器 + 证据包校验 | 按 `docs/M1_B_EVIDENCE_PACKET.md` §7 用 `scripts/m1b/collect_evidence.py` 逐 C 行登记，然后执行其 §7 的 1–4 校验（raw sha256/append-only/物化视图/无 hashless PASS） | 每个结论有 case_id + command + sha256 + limitation；`NOT_RUN` 必须有 reason | `NOT_RUN` |
| C-12 | 静态/边界扫描 | `git diff --name-only 4706250..HEAD`（保护路径 0 变更）；`grep -RInE "autoteacher_m0\|import (httpx\|requests\|aiohttp\|urllib.request)" m1_teacher`；`scoring/`/`hidden` 运行时导出扫描（不是仅 AST）；`ruff check m1_teacher tests/m1_teacher` | 无 M0/network/Key；teacher-visible 无 hidden 内容/`scoring/` 路径（PR4 P2-1 修复后）；ruff clean | `NOT_RUN`（Owner 过渡：M0/网络扫描 NONE、ruff passed；`scoring_spec_ref` 残余待 PR4 修复） |
| C-13 | 最终评测报告填充 | 按 `docs/M1_B_EVALUATION_REPORT_TEMPLATE.md` §0–§12，填入 C-01..C-12 真实结果；B5-01/X-01/X-02 逐项判定 | 只有全 Gate 通过才允许 `PASS_FOR_M1B_OFFLINE_INTEGRATION_SCOPE`；否则 `PARTIAL/FAIL/BLOCKED` | `NOT_RUN` |

### 4.3 计数纪律

- C-03 必须是**本树**计数；C-01/C-02 是**历史独立**参考，不得相加；最终树计数在 `M1_B_EVALUATION_REPORT.md` 单独列出。
- 每个 skip/fail 都要写理由与 evidence class；0 skipped 不能靠静默过滤获得。

---

## 5. 证据包位置与 hash 校验方式

- **建议位置**：`/root/m1b_evidence/B5-01/`（Reviewer 在冻结 SHA 上生成；最终位置以 Reviewer 报告为准）。
- **结构**：`README.md`（边界声明）+ `audit-index.jsonl`（append-only 权威索引）+ `audit-index.json`（物化视图）+ `raw/<run_id>/{evidence.json,stdout.log,stderr.log}`。
- **每条记录必含**：`case_id`、`branch`、`git_sha`（40 hex）、`command`/`command_argv`、`environment`（TZ/LANG/LC_ALL/PYTHONHASHSEED/python/pytest/OS）、`utc`、`exit_code`、`status`、`raw_evidence_path`、`sha256`、`limitation`（非 PASS 必填）。
- **校验**（`docs/M1_B_EVIDENCE_PACKET.md` §7）：
  1. 每行 `raw_evidence_path` 的 `sha256` 与索引一致；
  2. append-only（旧行字节不变）；
  3. `audit-index.json` 与 `audit-index.jsonl` 条目一致；
  4. 无 command/无 sha256 的 `EXECUTED_PASS` 数量为 0；
  5. artifact manifest 的 sha256 与文件一致。
- **禁止**：无 hash 的“PASS”；把 `EXECUTED_PASS` 当产品 PASS；`NOT_RUN/BLOCKED` 改写成 PASS；历史 536/365 相加；证据包缺失失败/负面样例（协议 §11.4 要求保留至少 1 个失败样例）。

---

## 6. 已知限制、STOP 清单与不可声称项

### 6.1 不可声称（必须保留在最终报告）

1. 真实学习效果/教学收益 **`NOT_VERIFIED`**（全部确定性启发式 + synthetic 输入）。
2. 真实 Provider/LLM/联网研究/真实 JD/简历 **`BLOCKED`**；无 Key、无付费请求。
3. 真实 OS 判题安全承诺 / 生产可用性 **`UNVERIFIED`**；B1-04 目标部署非 root **`NOT_RUN`**；真实用户 CODE **`BLOCKED`**。
4. 断电持久性 **`UNVERIFIED`**（仅 SIGKILL 进程崩溃矩阵）；分布式/多主机并发 **`NOT_RUN`**。
5. `FULL_SOLUTION`、人工复核队列/审批 UI 未实现（结构上 fail-closed，不等于已交付）。
6. Session Replay、事件版本拒绝（MAP-E12/E13）未实现；当前仅 learner snapshot replay。
7. B4-05、真实 hidden 评测集转换均 `NOT_RUN`。
8. 阈值（加速 0.25/证据 2、hint cap、interview ladder）**`UNCALIBRATED`**。

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

### 6.3 当前已知实现/证据缺口（须在最终报告逐项裁决）

- PR1/PR3/PR4 review-fix 未合入当前候选快照；PR4 P1-1/P1-2/P1-3 尚未修复。
- 共享 `/tmp` 的 judge 临时目录隔离缺陷（干净 TMPDIR 可规避；最终 Reviewer 需固定该条件）。
- `ASSESSED.item.scoring_spec_ref` 的 `scoring/` 路径、`spec-sha256` 元数据、`demo_b4.py` hidden 读取（PR4 P1-2/P2-1、PR1 P2）。
- PR1 修复 `run_safety_ci.sh` 已合入 final tree；`.github` 安全 job 的实际接线仍由维护者/CI owner 负责（本请求不声称已配置）。
- 文档残留：ADR §5 可选字段措辞与 P1-04 零 diff 原则冲突；`docs/M1_ARCHITECTURE.md` §14 仍写 schema v1（实际 v2）；PR1/PR3/PR4 评审文档未合入。

---

## 7. 需要人类批准/决策的事项

| # | 事项 | 当前状态 | 建议决策者 |
|---|---|---|---|
| H-01 | 真实用户 CODE 开放（不可信代码判题） | **`BLOCKED`**：需人类批准 + 目标部署安全验收（非 root、bwrap、CI gate 接线） | 维护者 + 安全负责人 |
| H-02 | 真实 Provider/LLM/联网研究/LiveGate | **`BLOCKED`**：本线无 Key/网络；不在 M1-B 离线范围 | 维护者 |
| H-03 | 非 root 部署 principal 验收 | **`NOT_RUN`**：需专用非 root 服务账号或 setuid bwrap + 目标机复跑 | 维护者 + 部署负责人 |
| H-04 | G4-H/G5/M0 决策变更 | 不在本请求范围，保持原状态 | 维护者/上游线负责人 |
| H-05 | 签收 B0 合同收敛 ADR（A canonical + B vertical + 四端口） | 待签收 | 维护者 + LeadB |
| H-06 | 创建 GitHub PR 并确认合并顺序（PR0→PR5 + review-fix） | 当前仅本地分支 | 维护者/LeadB |
| H-07 | schema v2 / 迁移策略（forward-only；禁止真实 learner DB 自动迁移） | 实现为 add-only v2 + v1→v2 迁移；真实 DB 永久禁止自动迁移 | 维护者 + LeadB |
| H-08 | 最终 `PASS_FOR_M1B_OFFLINE_INTEGRATION_SCOPE` 签收 | `PENDING`（Owner final tree 证据已交付；待 Lead 指派独立 Reviewer 出具 B5-01 结论） | 维护者 |

---

## 8. 建议维护者动作（按顺序）

1. **签收 B0 ADR/端口/CI 文档**（H-05），确认“A canonical + B vertical + 四端口 + D12 add-only + schema v2”裁决。
2. **按栈顺序创建/审阅 GitHub PR**（H-06）：PR0 → PR1（含 `550ad37` 修复）→ PR2（含 `10fdaa9`）→ PR3（含 `a5373f1`）→ PR4（补 P1 修复）→ PR5（含证据收集器/模板/协议）→ 最终 integration。
3. **合入 review-fix 后重新冻结 SHA**，通知独立 Reviewer 在 clean archive 上按 §4 矩阵复跑（C-00..C-13），并生成 `docs/M1_B_EVALUATION_REPORT.md`。
4. **决定 schema v2/迁移策略**（H-07）：确认 forward-only 与“真实 learner DB 禁止自动迁移”；如需真实迁移，另立人类批准的 runbook。
5. **维持人类 Gate**（H-01..H-04）：真实 CODE、Provider/LiveGate、非 root 部署、G4-H/G5 不随本请求自动解除；CI 安全 job 由 CI owner 接线 `scripts/m1b/run_safety_ci.sh`。
6. **仅在最终评测报告全部 Gate 通过后**签收 H-08；若有 P0/P1、STOP、未关闭 Gate，则只能接受 `PARTIAL_FOR_..._SCOPE` 或 `BLOCKED`。

---

## 9. 请求的完成定义（Definition of Done）

- [ ] 维护者签收 H-05（B0 ADR）。
- [ ] 最终 integration/freeze SHA 已确定并由 Reviewer 记录（40 hex）。
- [ ] PR1/PR3/PR4 review-fix 与评审文档全部合入；PR4 P1-1..P1-3 关闭或明确降级。
- [ ] 独立 Reviewer 完成 C-01..C-13；`docs/M1_B_EVALUATION_REPORT.md` 填满真实数字/证据/限制。
- [ ] B0-01、B1-01..06、B2-01..03、B3-01/02、B4-01..03、B5-01、X-01/X-02 逐项有本轮独立证据；未通过项显式保留。
- [ ] 证据包 `audit-index.jsonl` 通过 §5 校验；失败/负面样例保留。
- [ ] 维护者确认 §6.1 不可声称项全部保留；历史 536/365 未相加；真实收益/Provider/Live 未混写。
- [ ] 人类 Gate（§7）保持原状态或由对应批准人单独签署。

> 本请求**不代表** M1-B 已验收或已可合并；Owner 最终树评测报告已产出（`FINAL_TREE_MEASURED`），但 B5-01 最终独立评审与维护者签收仍 `PENDING`，最终裁定由独立 Reviewer 给出。

---

## 10. 变更记录

| 日期（UTC） | 版本 | 变更 |
|---|---|---|
| 2026-11-20 | v0 | 初稿：审阅请求、候选 SHA/分支、复跑矩阵、证据包校验、限制/STOP/人类 Gate、维护者动作；未修改实现/测试/fixture |
