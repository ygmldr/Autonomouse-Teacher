# M1-A Offline Adaptive Teacher MVP — Independent Review (B-PR5 final)

| 字段 | 值 |
|---|---|
| Task | Shared board `task-12` (M1-A B-PR5 independent review) |
| Reviewer | `m1a-reviewer` (independent; **did not participate** in any M1-A implementation) |
| Worktree (frozen) | `/root/at-m1a-mvp`, branch `work/m1a-mvp` |
| Base / main | `main@3e7afee077845a071cd364e93ab209cac20b2d5f`; main worktree `/root/Autonomous Teacher` clean |
| B-PR5 reviewed commit (**C5**) | `d4f10f3b32ee115759e2f9409c033b7ec8d76f6c` (5-PR implementation chain final) |
| Reviewer-fix commit (**C6**) | `3010426d9557fa1042f9c06cfef491758e1dce72` — `fix(m1a): make evidence manifest fully deterministic (review P1-1)`（在 C5 之上，仅 P1-1 修复；已推送 `work/m1a-mvp` 与 `b-pr5`） |
| Implementation chain | PR1 `c0c6ee5` → PR2 `b3d9c8c` → PR3 `38e9d2d` → PR4 `933ccde` → PR5 `d4f10f3` → **fix `3010426`**（linear，0 merge commits） |
| Review execution | 2026-11-20 UTC；双轮：C5 初评 + **C6 fix 复验**；均在 clean archive 副本上进行（`git archive <sha> | tar -x -C /tmp/m1a-c{5,6}-review`），不受未提交/隐藏状态影响 |
| Environment | Linux `6.17.13-2-pve`；Python `3.11.15`（`/root/Autonomous Teacher/.venv/bin/python`）；pytest `9.2.0`；ruff `0.17.5` |
| Evidence rule | 所有结果均由 Reviewer 自己的命令/探针产生，不采信 owner 的 PASS 文本；owner 声明的 hash 若不可复现即作为 finding 记录（P1-1 即因此被发现并修复） |
| Files written by Reviewer | 仅本文件（`docs/M1_INDEPENDENT_REVIEW.md`，未 commit，由 Lead 以 C7 提交）；探针在 `/tmp`；未修改实现/测试/fixtures/其它 docs |

---

## 0. 最终裁定与结论摘要

| 项 | 结果 |
|---|---|
| **P0 findings** | **0** |
| **P1 findings** | **1 → FIXED-IN-C6 & VERIFIED（已关闭）**：`e2e_summary.json` 原先含 wall-clock 日期与动态 `git rev-parse HEAD`，导致文档声明的 SHA 在冻结树不可复现；C6 以固定 `artifact_manifest` 修复，Reviewer 在 clean C6 上复验通过 |
| **P2 findings** | **0**（§5 的 context notes 均为已声明限制/预期上下文，不是缺陷） |
| Review checklist R1–R10 | **全部 PASS**（R6/R7 在 C6 修复后 PASS） |
| B1–B8 capability blocks | **全部 VERIFIED**（§4） |
| LeadB 指令 §7 完成条件 | **全部满足**（§5）；唯一 open item 已由 C6 关闭 |
| **最终裁定** | **`PASS_FOR_M1A_OFFLINE_MVP`** |

> **边界**：此裁定仅覆盖**离线、合成、确定性**的 M1-A MVP（synthetic CC0-1.0 fixtures + MOCK 学生结果 + 本地状态机/局部子进程判题）。**不是**真实教学效果 PASS、**不是** M1 上线/联网/真实 Provider 授权、**不改变** M0 G4-R/G5/LiveGate/M0 决策；H-01/H-02/H-03/I-01 仍 **BLOCKED**。

---

## 1. 方法与命令

### 1.1 独立性

- Reviewer 未参与 `m1_teacher/**`、`tests/m1_teacher/**`、`fixtures/m1_teacher/**`、`docs/M1_*` 的任何编写；未把 owner 声明当作验收证据。
- 复核在**精确冻结 SHA 的 clean archive 副本**上执行（C5 与 C6 各一次），真实工作树只读检查；期间无网络、无 API Key、无真实学习者数据、无 M0 写入、无 `git commit/merge/push`。
- C5 初评发现 1 个 P1（evidence-summary 不可复现）→ Lead 安排 owner 最小修复并冻结 C6 → Reviewer 在 clean C6 上复验 P1-1 并回归 A–H 关键项。

### 1.2 关键命令（Reviewer 实跑）

```bash
# --- scope / chain ---
cd /root/at-m1a-mvp
git rev-parse HEAD                              # C6=3010426… (C5=d4f10f3…)
git diff --name-only 3e7afee..HEAD              # 75 files, all additions, only allowed paths
git rev-list --merges 3e7afee..HEAD             # 0
git log origin/work/m1a-mvp..HEAD               # 0 (pushed; b-pr5 also at C6)
git status --porcelain                          # clean (only reviewer doc untracked)

# --- clean frozen copies (C5 / C6) ---
rm -rf /tmp/m1a-c5-review && mkdir -p /tmp/m1a-c5-review
git archive d4f10f3b32ee115759e2f9409c033b7ec8d76f6c | tar -x -C /tmp/m1a-c5-review
rm -rf /tmp/m1a-c6-review && mkdir -p /tmp/m1a-c6-review
git archive 3010426d9557fa1042f9c06cfef491758e1dce72 | tar -x -C /tmp/m1a-c6-review
cd /tmp/m1a-c6-review
"/root/Autonomous Teacher/.venv/bin/python" -m pytest tests/m1_teacher -q        # 536 passed

# --- demo / CLI / evidence determinism (two independent processes) ---
"/root/Autonomous Teacher/.venv/bin/python" -m m1_teacher.demo > /tmp/m1a_c6_demo1.txt
"/root/Autonomous Teacher/.venv/bin/python" -m m1_teacher.demo > /tmp/m1a_c6_demo2.txt
diff /tmp/m1a_c6_demo1.txt /tmp/m1a_c6_demo2.txt && sha256sum /tmp/m1a_c6_demo1.txt
"/root/Autonomous Teacher/.venv/bin/python" -m m1_teacher.demo --write-evidence
sha256sum docs/m1a_evidence/*
"/root/Autonomous Teacher/.venv/bin/python" -m m1_teacher.cli --help
"/root/Autonomous Teacher/.venv/bin/python" -m m1_teacher.cli --student both --json
"/root/Autonomous Teacher/.venv/bin/python" -m m1_teacher.cli --demo
"/root/Autonomous Teacher/.venv/bin/python" -m ruff check <PR5+extensions files>
"/root/Autonomous Teacher/.venv/bin/python" -m ruff format --check <same>

# --- P1-1 re-verification: no-.git tree, different TZ/hashseed ---
cp -a /tmp/m1a-c6-review/m1_teacher /tmp/m1a-nogit-tree/m1_teacher
cp -a /tmp/m1a-c6-review/fixtures/m1_teacher /tmp/m1a-nogit-tree/fixtures/m1_teacher
cd /tmp/m1a-nogit-tree
TZ=Asia/Tokyo LANG=C PYTHONHASHSEED=random \
  "/root/Autonomous Teacher/.venv/bin/python" -m m1_teacher.demo --write-evidence
sha256sum docs/m1a_evidence/*   # == clean C6 hashes; A/B/summary byte-identical
# network-blocked run (sitecustomize denies socket.*)
PYTHONPATH=/tmp/b_nonet "/root/Autonomous Teacher/.venv/bin/python" -m m1_teacher.demo
# Reviewer independent probes
"/root/Autonomous Teacher/.venv/bin/python" /tmp/m1a_probe_evidence_c6.py
"/root/Autonomous Teacher/.venv/bin/python" /tmp/m1a_probe_engine_c6.py
```

### 1.3 原始输出摘要

| 检查 | C5（初评） | C6（复验，最终） |
|---|---|---|
| 完整测试 | `533 passed in 13.89s`（0 failed/skip） | **`536 passed in 14.46s`**（533+3 项 P1-1 回归测试；0 failed/skip） |
| demo stdout 双跑 | sha256 **`b08ceee9…`**，53 行，md5 `f92be523…` | **同值不变**（`b08ceee915fb0363864e303ded71de4d547eae6d14f7aa693ba1537a810d491b`，53 行） |
| `--write-evidence` A/B JSONL | `171cc654…` / `5e84229e…`，跨进程 byte-identical | **同值不变**；跨进程 + 无 .git 副本 + 不同 TZ/PYTHONHASHSEED 均 byte-identical |
| `--write-evidence` summary | `62f1ebd4…`（仅 pre-commit 上下文可复现 → **P1-1**） | **`23b871a3…`**（= 文档新 expected，可复现；见 §3） |
| CLI | `--help/--demo/--student a|b|both/--json/--db/--write-evidence` 正常；`--demo` == module demo | 同 |
| ruff | `All checks passed!` / `7 files already formatted` | 同 |
| 证据内容 | A/B JSONL 仅固定时间戳 `2026-11-20T00:00:00Z`；无 hidden 材料 | summary 固定 `artifact_manifest`（无 wall-clock/git 动态字段）；A/B 不变 |
| Fixtures | 8 节点/9 边；16 题（MCQ 8/CODE 5/SHORT 3；13 deterministic）；16 scoring specs；1 objective；2 students | 同（C6 未改 fixtures） |
| Scope | 75 文件全为新增、仅允许路径；0 merge；main clean | C6 相对 C5 仅 8 文件（4 docs + demo.py + 2 tests + summary），无 M0/冻结区；75 文件仍全为新增 |

---

## 2. 逐项独立复现（A–H）

### A. Git / 范围 / M0 隔离 — **PASS**

| 检查 | 结果 | 证据 |
|---|---|---|
| HEAD == Lead 记录 SHA | **PASS** | C5=`d4f10f3…`；C6=`3010426…`；`origin/work/m1a-mvp`、`origin/b-pr5` 均 == C6 |
| Diff vs `3e7afee` 仅允许新路径（+ B-PR5 允许更新 `docs/M1_ARCHITECTURE.md`） | **PASS** | base..C6 = 75 文件全为新增：`docs/M1_*.md` 6、`docs/m1a_evidence` 3、`m1_teacher` 26、`tests/m1_teacher` 17、`fixtures/m1_teacher` 23；无 `src/`、`plugins/`、`config/`、`scripts/`、`artifacts/`、其它 tests、`pyproject.toml`、`AGENTS.md` 等 |
| 零 M0 / 冻结区改动 | **PASS** | 路径审计（base..C6、C5..C6 均无 M0 路径）；主工作树 HEAD `3e7afee` 且 clean |
| 线性历史 / 无 merge / 无篡改 | **PASS** | 6 commits，`git rev-list --merges` = 0，0 unpushed |
| `m1a.v0` 契约未变（PR1 后仅 additive） | **PASS** | `git log -- m1_teacher/contracts/types.py` → 只有 PR1 `c0c6ee5`；PR5/C6 改动仅 CLI/demo/extensions/tests/docs/evidence |
| worktree clean | **PASS** | 仅本 review doc 未跟踪（按 Lead 指令由 C7 提交） |

### B. 测试 — **PASS**

- clean C6：**`536 passed`**（exit 0，0 failed/skip）。逐文件收集：169/41/38/20（PR1=268）、48/27/25（PR2=100）、16/19/15（PR3=50）、34/22/19（PR4=75）、**18/13/12（PR5=43）**；与 C6 文档 `536 (268+100+50+75+43)` 一致。
- 无空断言/占位：全仓无 `assert True`/纯 `pass` 测试；唯一条件 `skipif`（`test_domain_adapter.py:51` 的 real-fixtures guard）在冻结 fixtures 下条件为 False，无静默跳过。`scorer.py` 两处 `pass` 为异常清理，不是测试占位。
- 抽查关键测试（真实规则断言）：
  - `test_planner_policy.py`：HARD 前置补救先于目标教学（ordinal 断言）、SOFT 默认不强制/可 opt-in、review 间隔门控、连续失败→REASSESS、max-relearn 切换、不完整目标不 GOAL_COMPLETE、step/id 确定性、阈值可注入并改变行为、hidden/network 静态隔离；
  - `test_e2e_student_ab.py`：A/B first action/plan/phase/diagnosis/recommendation 差异 + 原因码、mastery 证据驱动、pause/resume、同状态计划复现、JSONL/summary 字节可复现（C6 后）、独立 policy 测试；
  - `test_assessment_scorer.py`：MCQ/CODE/SHORT 判定、EVAL_ERROR 隔离（missing/corrupted/unsafe spec）、结果不泄漏 hidden 字段、only-scorer 引用 hidden 路径、无 M0/网络 import；
  - `test_e2e_resume_idempotency.py`：重复 result_id/history event 幂等、pause→new engine+same SQLite→resume 相等、raising scorer/missing spec 仅 EVAL_ERROR、hidden delete/tamper 不变、`verify_rebuild`；
  - `test_cli_smoke.py`：真实子进程运行 shipped modules、demo 无 wall-clock、跨进程 byte-identical、CLI==module、JSON 模式、evidence 可复现（C6 后含 summary 与 no-.git 断言）。

### C. Demo / CLI / 证据确定性（离线）— **PASS（C6 后）**

| 检查 | 结果 |
|---|---|
| `python -m m1_teacher.demo` 两个独立进程 | **byte-identical**，sha256 `b08ceee9…`（= 文档），53 行，exit 0；stdout 仅固定时间戳 |
| `--write-evidence` 两次 | **A/B JSONL + summary 三工件 byte-identical**；A/B `171cc654…`/`5e84229e…`（不变），summary `23b871a3…`（= 新文档 expected） |
| 无 .git 干净副本 + 不同 TZ/PYTHONHASHSEED 重生成 | **三工件逐字节一致**于 clean C6 archive 运行结果（P1-1 修复的关键证明） |
| CLI `--help/--demo/--student a|b|both/--json/--db/--write-evidence` | 全部正常；`--demo` 输出与 module demo 完全一致；db 路径不打印 |
| 离线 | **PASS**：`sitecustomize` 阻断 `socket.socket/create_connection/getaddrinfo` 后 demo 仍 exit 0 且 stdout 一致；AST 无网络/M0 import；scorer 子进程 env 仅最小 allow-list（PATH/编码/locale/tmp），不含凭据 |
| 无 Key / 真实数据 | **PASS**：`m1_teacher/`、`fixtures/m1_teacher/`、`docs/m1a_evidence/`、`docs/M1_*.md` 无 API-key/真实邮箱/电话形态 |

### D. 教学闭环真实性（从原始证据 JSONL 复现）— **PASS**

通过 `git show 3010426:docs/m1a_evidence/*` 独立解析全部事件，逐条验证 `M1_EVALUATION_REPORT` §1–§3：

- **A/B 路径差异真实且可解释**：A 诊断 `TARGET_EVIDENCE_GAP`（target `cf.complexity.log`，item `item.bs.mcq.007`）；B 诊断 `HARD_PREREQUISITE_GAP`（target `cf.sort.sortedness`，item `item.bs.mcq.002`）。初始 plan 不同（`plan:f7bf9747…` vs `plan:d3fee62a…`），均 8 步且每步带 structured `Reason`（code/node_ids/detail/policy_version）。**B 的 sortedness remediation（TEACH/RETEACH `REMEDIATE_HARD_PREREQUISITE`，ordinal 0）先于目标教学；A 无 RETEACH/REASSESS，直接从 binary 目标教学开始。** phase trace 不同（39 vs 36 entries）。
- **Assessment 结果**（原始）：A 8 次 = CORRECT 7 / INCORRECT 1；B 7 次 = INCORRECT 3 / NEEDS_REVIEW 4。Mastery 链：A `cf.search.binary` 0.30→0.543571（evidence 2→8，confidence 0.75→0.996094）、complexity 0→0.20、boundary 0→0；B binary 保持 0.00（3 次观测全 INCORRECT）、sortedness 0.00（2 次）。A/B final mastery 不同。
- **掌握度只在证据下变化**：逐事件检查所有 `INCORRECT`/`NEEDS_REVIEW` 的 mastery update 未抬高任何节点（0 violations；`NEEDS_REVIEW` 的 `applied=false`），只有 CORRECT 更新抬高（A 共 7 次）；raw `mastery_updated` 的 status 字段与 assessments 一致。
- **教学决策随学生表现变化**：A 的最终 next-recommendation 因 `cf.search.boundary` **连续 2 次 INCORRECT** 产生 `REASSESS_STUCK_NODE`（同时继续 binary practice）；B 因 sortedness 连续 2 次、binary 连续 3 次 INCORRECT 产生 `REASSESS_STUCK_NODE` 后再教学新节点。这些 reason 来自真实 session 结果，不是脚本化文本。
- **证据真实性**：A 的 committed `plan_id`/steps 可从未 seed 历史经确定性 planner 精确重算一致（证明 evidence 由真实代码产生）；A/B `line` 字段均从 0 连续编号。
- **Pause→restart**：A/B `interrupt_resume_check` 全 true（snapshot/plan/paused_plan/pending 相等，restart 前后 `verify_rebuild=True`）；phase REVIEW→PAUSED→REVIEW。
- **幂等 / EVAL_ERROR / 模型算术**（Reviewer 独立构造，另见 §2.E）：
  - 重复 `result_id`：assessment 相等、revision 不变、无额外 history event；
  - raising scorer：`EVAL_ERROR`、learner snapshot `to_dict()` 不变、无 ASSESSED/INCORRECT、ERROR payload `mastery_unchanged=True`；
  - 真实 `DeterministicScorer` + 删除 scoring spec：`EVAL_ERROR×3`、phase REVIEW、`retry_exhausted=True`、无 mastery 变化；
  - 全 INCORRECT session：所有 mastery 保持 `0.0`，error counters 记录；
  - 掌握度算术精确匹配冻结公式 `min(1, Σ correct_step/(1+evidence_before))`，confidence 递推一致（Reviewer 独立算例：1 INCORRECT + 4 CORRECT → value 0.256667 / confidence 0.953125 / evidence 5）；
  - `NEEDS_REVIEW`/`EVAL_ERROR` 对 model 是 no-op（snapshot byte-identical）；
  - goal completion 只来自观测证据（mastered snapshot → `GOAL_COMPLETE`；空 snapshot → `GOAL_NOT_COMPLETE`）。

### E. 策略独立性（规则而非“能跑”）— **PASS**

- 独立重建规则：空 snapshot vs mastered snapshot → 仅证据驱动完成；构造 2 次连续 INCORRECT history → plan 先出 `REASSESS_STUCK_NODE`；构造 Student-B 型状态 → HARD 前置 remediation 的 ordinal 先于目标教学；
- **确定性**：同一 snapshot+history 上两个独立 planner 实例产生字节一致的 `CurriculumPlan.to_dict()`；两个 diagnostic 实例产生一致的 `DiagnosisResult.to_dict()`；
- 所有阈值可注入（`PlannerPolicy/DiagnosticPolicy/SessionPolicy/MasteryPolicy`），测试断言阈值改变会改变行为（Rule 6/7）→ 策略规则确实被测试，而非只验证“可执行”。

### F. 隐藏答案隔离 — **PASS**

| 检查 | 结果 |
|---|---|
| 静态扫描 `m1_teacher/**/*.py` 中 `scoring/` 引用 | **仅 `m1_teacher/assessment/scorer.py`**（唯一 hidden 读取者） |
| 公开 domain fixtures（assessment_items/teaching_content/knowledge_graph/objectives） | 无 `correct_option_index`/`required_concept_groups`/`expected`/`tests`/`solution` 字段 |
| 临时副本删除 scoring 目录 | teacher diagnosis + planner 输出**完全不变**（同 plan_id/to_dict）；MOCK 学生 E2E 仍可运行 |
| 临时副本将所有 scoring spec 改为 junk | teacher 输出**完全不变**；MOCK E2E 仍可运行 |
| 证据/文档泄漏扫描 | 47 个 hidden-only needle（完整 rubric group tuple、长 scoring explanation、test arg/expected 对）→ committed JSONL/summary/M1 docs **0 命中**；无 hidden 字段键 |
| Scorer 输出 | result dict 不含 `correct_option_index`/`required_concept_groups`/`explanation`/`tests`/`expected`/`scoring/`（测试 + Reviewer 探针） |

`assessment_items.json` 中的 `scoring_spec_ref` 是文档声明的 opaque reference（不含答案内容）。

### G. 证据诚实性 — **PASS（P1-1 已在 C6 修复并复验）**

- A/B JSONL、demo/CLI/ruff/536-tests 的 owner 声明均被 Reviewer 复现；C6 后 summary 的文档 expected hash（`23b871a3…`）也可复现。
- 证据分类正确：JSONL `["MOCK","DETERMINISTIC"]`；summary `classification` 明确 MOCK/DETERMINISTIC/NOT_VERIFIED 且 `HUMAN_REVIEWED=NOT_RUN`；docs 保留 `NOT_RUN`/`NOT_VERIFIED` 段与 `offline synthetic only, not real teaching effect` 边界；grep 未发现 `M1 GO`/`G4-R`/`G5`/production/真实效果越界声明。
- **C6 修复验证**：summary 现为固定 `artifact_manifest`（`manifest_version=m1a.evidence.manifest.v1`、固定 `generated_at=2026-11-20T00:00:00Z`、固定 `base_sha=3e7afee…`、固定 `implementation_commit=d4f10f3…`），无 `generated_at_utc_date`/`base_commit`/动态 git；`demo.py` 的 AST import 不含 `datetime`/`subprocess`/`time`/`random`/`os`，源码无 `datetime.now`/`rev-parse`/`_git_head`/`_utc_date`。docs 的 expected hash/provenance/测试数（536）已同步更新。
- 已知限制均为声明而非隐瞒：单一合成 domain、启发式未校准 mastery、MOCK 学生结果、judge 为本地子进程边界而非 OS 沙箱、开放式答案保守（≤PARTIAL/NEEDS_REVIEW）、next-phase 仅 contract stub、真实学习者/网络/Provider `NOT_RUN`/`NOT_VERIFIED`、multi-domain/interview/freshness/research `NOT_RUN`。
- M0 隔离描述准确：无 `autoteacher_m0` import、无网络 import、无 M0 文件改动、不复用 M0 DSH session 作为学生 DB。

### H. LeadB 指令 §7 完成条件 — **全部满足（§5 矩阵）**

---

## 3. Findings 与处置

### P0 — 无

未发现隐藏答案泄漏、伪造证据、教学闭环失效、M0/网络/Key 越界或核心循环不可复现等问题。

### P1-1（C5 发现 → **C6 修复 → C6 复验通过**）：`e2e_summary.json` 文档声明 SHA 在冻结树不可复现

- **首轮证据（C5）**：`m1_teacher/demo.py` 的 `_utc_date()`（wall-clock）与 `_git_head()`（`git rev-parse HEAD`）被写入 summary；`docs/M1_IMPLEMENTATION_REPORT.md:97` 与 `docs/M1_REVIEW_REQUEST.md:83` 声明 summary sha256 `62f1ebd4…`；`docs/M1_ARCHITECTURE.md:313` 声称 E2E artifacts 为 DETERMINISTIC/reproducible；测试只比较 A/B JSONL、从不比较 summary 字节。
- **首轮复现**：committed `62f1ebd4…`（base=933ccde，date=2026-11-20）；clean C5 archive（无 .git）重生成 `7d15266c…`（base=UNAVAILABLE）；带 .git 的 C5 副本重生成 `2593177b…`（base=d4f10f3）→ 冻结树无法复现文档 hash，且 summary 随日期/HEAD 变化。
- **C6 修复**（commit `3010426…`，仅 8 文件：`demo.py` + 2 tests + summary + 4 docs）：
  - `demo.py` 移除 `datetime`/`subprocess` 与 `_utc_date`/`_git_head`；新增固定常量 `BASE_COMMIT_SHA=3e7afee…`、`REVIEWED_IMPLEMENTATION_COMMIT=d4f10f3…`、`ARTIFACT_MANIFEST_VERSION=m1a.evidence.manifest.v1` 与 `artifact_manifest()`；
  - summary 改为固定 `artifact_manifest`（无 wall-clock、无 git 动态读取）；
  - 新增/强化回归测试：summary 跨运行字节一致、无 `.git` 干净副本重生成三工件逐字节一致、静态防 wall-clock/dynamic-git（`test_evidence_summary_is_identical_in_a_no_git_copy`、`test_demo_has_no_wall_clock_or_dynamic_git_provenance`、`test_cli_evidence_summary_is_identical_in_a_no_git_copy`），并扩展 `test_evidence_jsonl_is_reproducible_and_complete`/`test_cli_write_evidence_is_reproducible` 比较 summary 字节；
  - docs expected hashes/provenance/测试数更新为 C6。
- **C6 复验（Reviewer，clean C6 archive）**：
  - `pytest tests/m1_teacher -q` → **536 passed in 14.46s**（0 failed/skip；533+3 新测试）；
  - `--write-evidence` 两次：A `171cc654…`、B `5e84229e…`（不变）、summary **`23b871a3…`**，三工件逐字节一致；demo stdout 双跑 `b08ceee9…`（不变、53 行）→ 教学/决策逻辑未变；
  - 无 .git 干净副本 + `TZ=Asia/Tokyo`/`LANG=C`/`PYTHONHASHSEED=random` 重生成：三工件与 clean C6 archive 运行**逐字节一致**；重复运行一致；summary 内所有 timestamp 均等于固定值，无 `UNAVAILABLE`；
  - `demo.py` AST 导入与源码扫描确认无 wall-clock/git 动态来源；summary 无 `generated_at_utc_date`/`base_commit`；
  - docs 中 expected hash 与新值（`23b871a3…`）一致。
- **影响（修复前）**：文档 expected evidence hash 不可在冻结树复现（REVIEW_REQUEST §2 明确要求视为 regression）；summary 随 wall-clock/HEAD 漂移，与 “reproducible E2E artifacts” 表述不符。
- **处置：FIXED-IN-C6 & VERIFIED（CLOSED）**。C6 仅改 evidence provenance 与测试，不改教学逻辑；Reviewer 复验无新 P0/P1。

### Context notes（非 finding，已披露/预期，列为审计上下文）

1. **C5 文档中的 pre-commit provenance**：C5 初评时 C6 修复尚未提交，docs 写明 C6 “uncommitted at report time / Lead records the C6 SHA”；这与 P1-1 修复前状态一致，属预期上下文。
2. **Fixture provenance 为 README 级**：`fixtures/m1_teacher/README.md` §189-193 声明全部 synthetic + CC0-1.0、无真实数据；仅 `students/*.json` 有 per-file `synthetic`/`license` 字段，domain docs/scoring specs 没有。Architecture 限制 #8 已声明 provenance 由 README 提供，属已声明设计（非缺陷；若未来要求 per-file 元数据是 trivial additive change）。
3. **`--write-evidence` 会改写 tracked evidence artifacts**：文档化复现命令，按设计会弄脏工作树；Lead 负责提交/重生成，风险已声明。
4. **声明的限制均准确**：单 domain、启发式未校准 mastery、MOCK 学生结果、judge 非 OS 沙箱、开放式答案保守、stubs only、真实学习者/网络/Provider 未验证；multi-domain/interview/freshness/research `NOT_RUN`。未发现未声明限制。
5. **合同常量 provenance**：C6 把 `implementation_commit` 固定为 C5 `d4f10f3…`（reviewed implementation）并同时记录 `base_sha=3e7afee…`；这是有意为之的审计常量，不表示 artifact 由该 SHA 的 git 树自动生成（review request/implementation report 已说明）。

---

## 4. B1–B8 capability matrix

| Block | Capability | Verdict | Evidence |
|---|---|---|---|
| B1 | Learning-domain contracts + knowledge graph | **VERIFIED** | `m1a.v0` 冻结于 PR1（之后 `types.py` 无改动）；8 节点/9 边 DAG、16 items/16 specs/1 objective；PR1 测试 268；Reviewer 核对 fixture 规模与契约历史 |
| B2 | Learner model（mastery/confidence/evidence/error types/rebuild） | **VERIFIED** | 确定性启发式；INCORRECT 永不抬升；CORRECT 精确公式；幂等；`verify_rebuild` true；PR2 测试 100 |
| B3 | Diagnostic engine（next item/hypothesis/reason/insufficient evidence） | **VERIFIED** | A/B 结构化 reason 差异；诊断确定性；PR3 测试 16 |
| B4 | Curriculum planner（prereq remediation/teach/practice/review/reassess/goal-complete/structured reasons） | **VERIFIED** | 规则级测试 + Reviewer 独立构造；HARD remedy 先于目标教学；review 间隔/REASSESS/goal completion；plan id 确定；PR3 测试 34 |
| B5 | Teaching-session state machine（skip/backtrack/re-entry/pause/resume） | **VERIFIED** | 原始 evidence phase 序列；pause→new engine+same SQLite→resume 全等；PR4 测试 41 |
| B6 | Independent assessment（CORRECT/INCORRECT/PARTIAL/NEEDS_REVIEW/EVAL_ERROR；judge isolation） | **VERIFIED** | 仅 scorer 读 hidden；公开 fixture 无答案；EVAL_ERROR 隔离；SHORT ≤PARTIAL/NEEDS_REVIEW；PR4 测试 34 |
| B7 | Memory/history/SQLite persistence & rebuild | **VERIFIED** | event log 为 source of truth；snapshot rebuild；重复 event 幂等；原子提交；PR2 测试 25 + Reviewer resume/幂等探针 |
| B8 | Offline demonstration（CLI/demo/full loop/interrupt/resume/next recommendation） | **VERIFIED（C6 后）** | demo/CLI 确定性；完整闭环；pause/resume；next recommendation 反映失败证据；三工件可复现 |

## 5. Review-request R1–R10 与 LeadB §7 条件

### R1–R10

| # | Item | Verdict | Evidence |
|---|---|---|---|
| R1 | Teaching logic: prereq-first remediation, diagnosis reasons, review/reassess/goal-complete, A/B paths explainably different | **PASS** | §2.D/E |
| R2 | Hidden-label isolation: only scorer references hidden scoring; static + delete/tamper probes; no answer material | **PASS** | §2.F |
| R3 | Idempotency: duplicate result/event → one mastery update | **PASS** | Reviewer probes + tests |
| R4 | Recovery: pause→new engine+same SQLite→resume equality; `verify_rebuild=True` | **PASS** | §2.D |
| R5 | EVAL_ERROR isolation: raising scorer + missing/broken spec; mastery unchanged; no INCORRECT; retry/REVIEW | **PASS** | §2.D |
| R6 | Determinism: demo stdout byte-identical; evidence byte-identical; no wall-clock/random decisions | **PASS（C6）** | demo `b08ceee9…` 双跑；三工件跨运行/无 .git/TZ byte-identical；demo.py 无 wall-clock/git 读取 |
| R7 | Evidence honesty: docs numbers reproducible; MOCK/DETERMINISTIC/NOT_VERIFIED correct; boundary; no real-learning claim | **PASS（C6）** | 536-tests/demo/CLI/ruff/全部 artifact hashes 复现；summary `23b871a3…` = docs；边界与 NOT_RUN 完整 |
| R8 | Boundaries: no M0 import/modification; no network/API key/LiveGate; `m1a.v0` unchanged | **PASS** | §2.A/F；socket-blocked run；AST；契约历史 |
| R9 | CLI/demo behaviour matches docs and stays offline | **PASS** | §2.C |
| R10 | Next-phase stubs contract-only and fail closed（`EXTENSION_NOT_IMPLEMENTED`；improvement log 拒绝 `real_effect_claim=True`） | **PASS** | Reviewer 实例化全部 stubs；log 拒绝真实效果声明 |

### LeadB 指令 §7 完成条件

| # | Condition | Result | Evidence |
|---|---|---|---|
| 1 | 完整状态机可运行 | **PASS** | `DIAGNOSE→TEACH/PRACTICE→ASSESS→UPDATE→REVIEW→(PAUSED/COMPLETE)`；A/B 原始 phase trace；PR4 测试 |
| 2 | 学生状态真实更新 + 持久化 | **PASS** | SQLite snapshots/history_events/goals/sessions；append-only event log + `verify_rebuild=True`；raw mastery before/after |
| 3 | 不同学生不同路径 | **PASS** | A/B diagnosis/plan/phase/mastery/next recommendation 全不同且有原因码 |
| 4 | 诊断/规划/评分独立测试 | **PASS** | 独立测试文件（16/19/15 planner+diagnostic；34 scorer）含规则级断言 |
| 5 | 恢复/幂等/失败处理 | **PASS** | pause→restart 相等 + rebuild；重复 result/event 幂等；EVAL_ERROR 隔离；missing/unsafe spec fail-closed |
| 6 | 不调用真实模型/网络 | **PASS** | MOCK/synthetic only；socket 阻断下 demo 一致；AST 无网络；scorer env 最小；无 Key |
| 7 | 未改/绕过 M0 | **PASS** | scope diff + main clean；无 M0 import |
| 8 | 独立 Reviewer 复核 | **PASS** | 本文件（独立、冻结 SHA、自有探针、两轮复验） |
| 9 | Demo + 证据报告 | **PASS（C6）** | demo/CLI 确定性；三工件可复现；docs expected hashes 一致 |

---

## 6. 已知假设 / 未决问题 / 声明限制

1. 本复核只覆盖离线 M1-A MVP；真实模型/Provider/网络/LiveGate、真实学习者、Web UI、Interview/Freshness/Research 实现均为 out of scope，保持 `NOT_RUN`/`NOT_VERIFIED`（已声明）。
2. 证据分类语义：seeded prior 与 student outcomes 为 `MOCK`（synthetic response script），状态机/mastery 算术/id/回放为 `DETERMINISTIC`；JSONL 同时标注两 class，符合文档语义。
3. C5 文档中 `HUMAN_REVIEWED` 原为 `NOT_RUN`（等待独立复核）；本文件即该独立复核，Lead/owner 可在 C7/post-review 文档中更新 evidence-class 记录。
4. `CFBinarySearchDomainAdapter` 支持 `M1_TEACHER_FIXTURES` 路径覆盖（仅 fixture path，无凭据/网络）。
5. CODE 判题用本地子进程 + timeout + temp dir，是正确性/确定性边界，**不是** OS 沙箱；只用自编 synthetic fixtures（已声明）。
6. C6 的 `implementation_commit=d4f10f3…` 是固定 provenance 常量（reviewed implementation），不代表 artifact 在 git 树中自动可验；review request 已说明由 Lead 记录 C6 SHA。
7. 未决（非阻塞）：若未来要把 per-file fixture 许可元数据或 `HUMAN_REVIEWED` 写入 evidence manifest，应走 additive contract/ADR，不改 `m1a.v0`。

---

## 7. 复现附录（Reviewer 只读探针与输出）

- `/tmp/m1a_probe_evidence_c6.py`：committed C6 evidence 哈希、A/B 差异/phase/assessment/mastery 链、pause/resume、summary consistency、C6 artifact manifest 检查。
- `/tmp/m1a_probe_engine_c6.py`：contract/plan/diagnosis 确定性、mastery 算术、引擎幂等、EVAL_ERROR（raising+missing spec）、全错 session、pause/resume、hidden delete/tamper、网络/M0 AST、wall-clock 扫描、extension stubs、独立 policy 构造、socket 阻断运行。
- 干净副本：`/tmp/m1a-c5-review`（C5）、`/tmp/m1a-c6-review`（C6）、`/tmp/m1a-nogit-tree`（无 .git 的不同 TZ/hashseed 复现）。
- 输出：`/tmp/m1a_c6_demo1.txt`、`/tmp/m1a_c6_demo2.txt`（sha `b08ceee9…`）；`/tmp/m1a_c6_we1.txt`、`/tmp/m1a_c6_we2.txt`；evidence hashes A `171cc654…`、B `5e84229e…`、summary `23b871a3…`。
- C5 首轮探针（P1-1 发现）：`/tmp/m1a_probe_evidence.py`、`/tmp/m1a_probe_engine.py`；C5 vs C6 的 summary 复现对比见 §3。

---

### 边界声明

> **Offline synthetic only, not real teaching effect.** 本报告的全部 PASS 与数值只描述一个基于 synthetic CC0-1.0 fixtures、MOCK 学生结果和固定 seed/时间戳的确定性离线状态机。它不测量、不证明真实学习收益、教学效果或模型能力，也不授权任何真实 Provider/网络/LiveGate/上线/生产使用。M0 G4-R/G5/LiveGate/M0 决策不变；H-01/H-02/H-03/I-01 保持 **BLOCKED**。

**（最终版 — C6 复验通过；`PASS_FOR_M1A_OFFLINE_MVP`）**
