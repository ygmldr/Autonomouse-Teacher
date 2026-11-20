# M1-B CI / Static Isolation / Demo — Frozen Commands（B-PR0）

| 字段 | 值 |
|---|---|
| 文档状态 | **DRAFT / DESIGN_ONLY**（命令冻结提案；等待维护者签收） |
| 证据类别 | 仅 `SOURCE_INSPECTED`（代码/文档阅读 + 本 worktree 只读命令输出）与 `DESIGN_ONLY`（冻结/门禁提案）；**本文不构成新验收 PASS** |
| 基线 | `main=3e7afee`；A 线 `work/m1a-mvp=4706250`（本 worktree `/root/m1b/pr0` 的基线）；B 线 `work/m1-offline-design=290c577` |
| 运行环境 | Linux `6.17.13-2-pve`；Python `3.11.15`（`/root/Autonomous Teacher/.venv/bin/python`）；pytest `9.2.0`；无网络、无 API Key、无真实 Provider、无真实学习者数据 |
| 明确声明 | **B 线冻结命令是两个子集**：`tests/m1_teacher`（A 线）与 `tests/m1_offline`（B 线）。**全仓 M0 套件不在本线验收范围**；如引用须原样标注失败项（见 §5）。 |
| 历史数字纪律 | A 历史 `536 passed`、B 历史 `365 passed` 各自冻结、**不可相加**（不存在“统一 901 tests”）；新集成套件另计并重新独立验收（见 §6） |
| 交付状态 | B-PR0 结束 = 文档完成、等待独立 Reviewer 静态预审；**不自称 DONE/PASS** |
| 独立预审响应 | 本修订回应 `docs/M1_B_BOUNDARY_PRE_REVIEW.md`：P2-04（冻结命令 SHA/树断言）、P2-13（teacher-visible item 路径运行时扫描列为 B-PR1 冻结验收项）已修订；处置见 `docs/M1_B_PR0_REVIEW_RESPONSE.md`。仍为 DESIGN_ONLY，未重新声明验收 PASS |

---

## 1. 冻结范围（本文件只冻结“命令与判据”，不冻结实现）

1. 两条线各自的 **CI suite 命令**、**Demo 命令**、**期望输出类别**（submitted count / demo digest ≠ 通过声明）；
2. **静态隔离检查**：hidden scoring 只能被 trusted scorer/judge 读取；teacher-visible 输出不含 expected；
   无网络/无 Key；M0 保护路径 diff 检查；
3. 历史测试数字口径与“不相加”纪律；
4. 运行约束：只读运行方式（`-p no:cacheprovider` + `PYTHONDONTWRITEBYTECODE=1`；B 线 `--write-artifacts`
   必须使用 archive 副本，见 §4.3）。

> 这些命令的输出**只证明“在特定冻结树上命令可复跑、输出是什么”**；是否 PASS 由对应 PR 的独立 Reviewer
> 按各自验收矩阵判定（`/root/leadb_zip/TEST_EVIDENCE_MATRIX.csv` 当前全部 `NOT_RUN`）。

---

## 2. A 线（`m1_teacher`）冻结命令

工作目录（下称 `$A`）：`/root/m1b/pr0`（分支 `b-next/pr0-convergence-adr`，基线 `4706250`；A 线实现与
`work/m1a-mvp` 同树）。
解释器：`/root/Autonomous Teacher/.venv/bin/python`。

### 2.1 套件（冻结）

```bash
cd /root/m1b/pr0
# P2-04：pin A 实现树（代码/测试/fixtures/证据自 4706250 起零 diff）+ 前后只读断言
test "$(git diff --name-only 4706250 -- m1_teacher tests/m1_teacher fixtures/m1_teacher docs/m1a_evidence | wc -l)" = "0" \
  || { echo "A_IMPL_TREE_DRIFT"; exit 2; }
git status --porcelain
"/root/Autonomous Teacher/.venv/bin/python" -m pytest tests/m1_teacher -q
git status --porcelain
```

- **期望输出类别**：树断言 exit 0（`A_IMPL_TREE_DRIFT` 不出现）；`N passed`（全绿，0 failed/skip）；
  前后 `git status --porcelain` 无 tracked 变更（`__pycache__`/`.pytest_cache` 已 gitignore）。
- **本 worktree 实测**（`SOURCE_INSPECTED`，2026-11-20）：**`536 passed in 19.30s`**（wall 19.59s）。
- **Lead 另测**：`536 passed in 16.47s`；**Reviewer 预审复跑**：`536 passed in 18.10s`（同命令，负载差异；
  计数才是门禁）。历史来源：`docs/M1_IMPLEMENTATION_REPORT.md` §3/§7、`docs/M1_INDEPENDENT_REVIEW.md` §1.2。

### 2.2 Demo（冻结）

```bash
cd /root/m1b/pr0
"/root/Autonomous Teacher/.venv/bin/python" -m m1_teacher.demo > /tmp/m1b_a_demo_1.txt
"/root/Autonomous Teacher/.venv/bin/python" -m m1_teacher.demo > /tmp/m1b_a_demo_2.txt
cmp /tmp/m1b_a_demo_1.txt /tmp/m1b_a_demo_2.txt
sha256sum /tmp/m1b_a_demo_1.txt
wc -l /tmp/m1b_a_demo_1.txt
```

- **期望输出类别**：exit 0；两次 stdout 逐字节相同；**demo digest（sha256）固定**；行数固定。
- **本 worktree 实测**：`stdout byte-identical`、**`sha256=b08ceee915fb0363864e303ded71de4d547eae6d14f7aa693ba1537a810d491b`**、
  **53 行**、stderr 0 字节；exit 0。
- 该 digest 与历史报告（`docs/M1_IMPLEMENTATION_REPORT.md` §3：`sha256=b08ceee9…d491b`）一致 →
  在当前树上可复现（`SOURCE_INSPECTED` 复跑证据，不是新验收）。
- demo 末尾自带边界声明：`offline synthetic only, not real teaching effect`、`MOCK / DETERMINISTIC /
  NOT_VERIFIED` 分类行。

### 2.3 可复现证据工件（冻结，可选）

在 **archive 副本**中执行 `--write-evidence`（避免在冻结树内写 tracked 文件）：

```bash
rm -rf /tmp/m1b-pr0-copy && mkdir -p /tmp/m1b-pr0-copy
cd /root/m1b/pr0 && git archive 4706250 | tar -x -C /tmp/m1b-pr0-copy
cd /tmp/m1b-pr0-copy
"/root/Autonomous Teacher/.venv/bin/python" -m m1_teacher.demo --write-evidence
sha256sum docs/m1a_evidence/e2e_student_a.jsonl \
          docs/m1a_evidence/e2e_student_b.jsonl \
          docs/m1a_evidence/e2e_summary.json
```

- **期望输出类别**：exit 0；三件工件 sha256 **等于**冻结树已提交值。
- **本 worktree 实测**（本文撰写时）：三件工件哈希与仓库已提交完全一致：
  `171cc654f65129af803dbcd97ebffd50a2da97e8c616d3868570a9b7cb9443f1`（student_a）、
  `5e84229ec452b2abad5243fa731f58cde38f76baee5240b01d01a3759eeda46b`（student_b）、
  `23b871a3743f6100d23130dc72f3796129cbb8bb0b97baa4492d54e3a96af8ce`（summary）。
- 固定时间戳/清单：`FIXED_TIMESTAMP="2026-11-20T00:00:00Z"`（`m1_teacher/demo.py:103`）、
  `ARTIFACT_MANIFEST_VERSION="m1a.evidence.manifest.v1"`（`:106`）、证据目录 `docs/m1a_evidence`
  （`:120`）；wall-clock/git 不进入 summary（A 线 P1-1 修复后设计）。

### 2.4 CLI 冒烟（冻结，可选）

```bash
cd /root/m1b/pr0
"/root/Autonomous Teacher/.venv/bin/python" -m m1_teacher.cli --help
```

- **期望输出类别**：exit 0，打印 usage；无网络/无 Key；不写文件。
- 参考：`m1_teacher/cli.py:138`（`main`），历史 smoke 见 `tests/m1_teacher/test_cli_smoke.py`。

---

## 3. B 线（`m1_offline`）冻结命令

工作目录（下称 `$B`）：`/root/at-m1-offline`（**冻结只读树**，分支 `work/m1-offline-design=290c577`）。
解释器：`/root/Autonomous Teacher/.venv/bin/python`。

### 3.1 套件（冻结）

```bash
cd /root/at-m1-offline
# P2-04：pin 冻结树 SHA + 前后只读断言
test "$(git rev-parse HEAD)" = "290c5770461bb5af2a38c6e6d24ee76350bcb410" \
  || { echo "B_FROZEN_TREE_MISMATCH"; exit 2; }
git status --porcelain
env PYTHONDONTWRITEBYTECODE=1 \
  "/root/Autonomous Teacher/.venv/bin/python" -m pytest tests/m1_offline -q -p no:cacheprovider
git status --porcelain
```

- **注意**：是 `tests/m1_offline` 子集，**不是** `tests/` 全仓（见 §5）。
- `-p no:cacheprovider` 避免 `.pytest_cache`；`PYTHONDONTWRITEBYTECODE=1` 避免 `__pycache__`，保证冻结树只读。
- **期望输出类别**：SHA 断言 exit 0；`N passed`（0 failed/skip）；前后 `git status --porcelain` 均为空。
- **本 worktree 实测**（`SOURCE_INSPECTED`，2026-11-20）：**`365 passed in 21.96s`**（wall 22.28s）；
  运行前后 `git status --porcelain` 均为空（冻结树未被写）。
- **Lead 另测**：`365 passed in 19.38s`；**Reviewer 预审复跑**：`365 passed in 19.26s`（同命令）。
- 历史来源：`docs/m1/REVIEW_M1_OFFLINE.md:103/136/323`（Reviewer clean C2：365 passed）。

### 3.2 Demo（冻结；默认无写入）

> 只读说明：为避免在冻结树产生任何缓存/写入，B demo 在 `290c577` 的 `git archive` 副本中执行
> （与冻结树内容一致）；默认路径**不写** tracked 文件。

```bash
cd /root/at-m1-offline
env PYTHONDONTWRITEBYTECODE=1 \
  "/root/Autonomous Teacher/.venv/bin/python" -m m1_offline.demo > /tmp/m1b_b_demo_1.txt
env PYTHONDONTWRITEBYTECODE=1 \
  "/root/Autonomous Teacher/.venv/bin/python" -m m1_offline.demo > /tmp/m1b_b_demo_2.txt
cmp /tmp/m1b_b_demo_1.txt /tmp/m1b_b_demo_2.txt
sha256sum /tmp/m1b_b_demo_1.txt
wc -l /tmp/m1b_b_demo_1.txt
```

- 默认**不写** tracked 文件（`--write-artifacts` 才写，见 §3.3）；本次 digest 在 archive 副本中测量。
- **期望输出类别**：exit 0；stdout 两次逐字节一致；**digest 固定**；行数固定；末行含
  `[boundary] offline synthetic … not real teaching effect`。
- **本 worktree 实测**（`SOURCE_INSPECTED`）：`stdout byte-identical`、
  **`sha256=2282caff40787317d8222401e2a7a0f9cdec6d9ac86d2ed8286927a0792df3cb`**、**38 行**、stderr 0；exit 0。
- 内容摘要（前几行）：`loop=teacher_v1 seed=0 rounds=3 events=19`、`trace_digest=ed850c77…`、
  `contamination=PASS`、`closed_loop/replay/determinism/comparison=PASS`、`[result] deterministic_output=true`。

### 3.3 Demo `--write-artifacts`（冻结；**必须**在 archive 副本运行）

B demo 的 `--write-artifacts` 会写 tracked 路径：
`docs/m1/traces/loop_v1_3rounds.jsonl`、`docs/m1/traces/loop_v0_3rounds.jsonl`、
`docs/m1/reports/eval_baseline_v1.json`、`docs/m1/reports/eval_baseline_v1.md`
（`m1_offline/demo.py:53-55`、`:342+`；`write_report` 见 `evaluation/report.py:393`）。
在冻结树上直接运行会改动仓库文件，因此冻结命令如下：

```bash
rm -rf /tmp/m1b-bline && mkdir -p /tmp/m1b-bline
cd /root/at-m1-offline && git archive 290c5770461bb5af2a38c6e6d24ee76350bcb410 | tar -x -C /tmp/m1b-bline
cd /tmp/m1b-bline
env PYTHONDONTWRITEBYTECODE=1 \
  "/root/Autonomous Teacher/.venv/bin/python" -m m1_offline.demo --write-artifacts \
  > /tmp/m1b_b_artifacts_1.txt
sha256sum docs/m1/traces/loop_v1_3rounds.jsonl \
          docs/m1/traces/loop_v0_3rounds.jsonl \
          docs/m1/reports/eval_baseline_v1.json \
          docs/m1/reports/eval_baseline_v1.md
```

- **期望输出类别**：exit 0；stdout digest 固定；trace/报告工件可复算。
- **本 worktree 实测**（`SOURCE_INSPECTED`，archive 副本）：
  - stdout（`--write-artifacts`）：**`sha256=ed9b9c16a3ec92188e82a3e1d15aac1677c3c9915dbf0bb0591e7aa635c76ed9`**、40 行；
  - traces：`loop_v1_3rounds.jsonl = ed850c775f1745a6672b0dbfb41a169f9324a74ec9d7caef108709b98e1acf64`、
    `loop_v0_3rounds.jsonl = 4019c9465b860335c57a9826b5cd01e6f3bc8697fa3969e847139a1d5c54176f`（两次运行一致）；
  - `eval_baseline_v1.md = c5d5f027bda6d16c1e34e47e5b72b88a6d7b3cec26ae8da5ff87218e20ec02de`（两次一致）；
  - **`eval_baseline_v1.json` 两次运行不一致**：唯一差异是
    `environment.utc_timestamp`（例如 `2026-11-20T19:46:00Z` → `2026-11-20T19:46:04Z`），来源
    `m1_offline/evaluation/report.py:152`（`datetime.now(...)`）。
- **冻结判据（重要）**：B 线 `--write-artifacts` 的**字节级确定性门禁只覆盖 stdout + trace JSONL + `.md` 报告**；
  `eval_baseline_v1.json` 只做**语义确定性**（屏蔽 `environment.utc_timestamp` 后比较，或后续 PR 增加固定时钟）。
  在修复前，**不得**把该 JSON 的 sha256 写入“可复现工件”清单；修复属于 B-PR5 文档/工具范畴（本文件只记录，
  不实现）。

---

## 4. 静态隔离检查清单（冻结命令 + 期望输出类别）

以下命令均在各自冻结树上只读执行；输出“NONE/仅已知位置”为期望类别，任何额外命中都必须由 PR 解释或修复。

### 4.1 隐藏评分材料位置（hidden scoring 只允许 trusted scorer/judge 读取）

**A 线**

```bash
cd /root/m1b/pr0
grep -RIn "scoring/" m1_teacher --include='*.py'
```

- **本 worktree 实测**：仅 2 处，均在 trusted scorer 边界内：
  `m1_teacher/assessment/scorer.py:6`（docstring 说明 hidden spec 路径）、`scorer.py:401`（解析
  `scoring/...` ref 的实现注释）。其余 teacher 组件无 hidden 路径引用。
- 配套测试（冻结子集命令）：

```bash
cd /root/m1b/pr0
"/root/Autonomous Teacher/.venv/bin/python" -m pytest tests/m1_teacher -q \
  -k "hidden or isolation or scan or scanner or tamper or m0 or network"
```

- **本 worktree 实测**：**`26 passed, 510 deselected in 0.54s`**（0 failed）。
- 关键测试锚点：`test_teacher_code_references_hidden_scoring_only_in_scorer`
  （`tests/m1_teacher/test_e2e_resume_idempotency.py:487`）、`test_only_scorer_module_references_hidden_scoring_path`
  （`tests/m1_teacher/test_assessment_scorer.py:486`）、`test_teacher_source_has_no_hidden_scoring_path_references`
  （`tests/m1_teacher/test_domain_adapter.py:780`）、`test_results_do_not_leak_hidden_spec_material`
  （`tests/m1_teacher/test_assessment_scorer.py:431`）。

**P2-13 运行时导出扫描（B-PR1 冻结项，当前 `NOT_RUN`）**：上面的源码 grep 只证明“引用位置”，不等于运行时
导出安全。A `AssessmentItem.scoring_spec_ref`（`m1_teacher/contracts/types.py:678`）在 teacher-visible 记录中
可携带 `scoring/<item>.json` 路径（fixture 实际值）。B-PR1 必须在导出/UI/trace/诊断前把它替换为不透明
`spec_ref_id` 或剥除，并在 B1-06 增加**运行时导出扫描**（item payload、事件 JSON、诊断消息、demo 输出），
而不是只做 AST/grep。验收前该项保持 `NOT_RUN`，不得以本节的 grep 结果替代。

**B 线**

```bash
cd /root/at-m1-offline
grep -RIn "hidden/" m1_offline --include='*.py' | head
grep -n "expected_repr\|expected=" m1_offline/cf/judge.py
```

- **本 worktree 实测**：`hidden/` 命中 3 行，均在评测污染扫描器的扫描模式中
  （`m1_offline/evaluation/contamination.py:54-56`）——不是判题读取路径；判题读取 `hidden_ref` 的代码在
  `m1_offline/cf/teacher.py:176-192`（`hidden_ref` 解析，不在 grep 的 `hidden/` 字面形式内）。
- **已知泄漏面（B-Q5，必须由 B-PR1 解决）**：`m1_offline/cf/judge.py` runner 生成
  `args_repr/expected_repr/actual_repr`（`judge.py` `_RUNNER_SOURCE` 内），`JudgeResult.failures`
  （`m1_offline/cf/judge.py:150-164`）包含 `expected=...` 摘要；`CFTeacher` 与其同进程
  （`m1_offline/cf/teacher.py:283` 等使用 `failures`）。当前 `DiagnosticResult.explanation` 仅在 fatal
  分支拼接 failure 文本（`cf/teacher.py:283-292`），但 `JudgeResult` 本身是 teacher 可见对象。
  **B-PR1 验收项 B1-02/B1-06 完成前，不得把 B judge 用于不可信 CODE。**
- 配套测试（冻结子集命令）：

```bash
cd /root/at-m1-offline
env PYTHONDONTWRITEBYTECODE=1 \
  "/root/Autonomous Teacher/.venv/bin/python" -m pytest \
  tests/m1_offline/test_no_m0_import.py tests/m1_offline/test_contamination.py -q -p no:cacheprovider
```

- **本 worktree 实测**：**`25 passed in 1.31s`**。

### 4.2 无网络 / 无 M0 import（静态）

```bash
# A 线（期望：NONE）
cd /root/m1b/pr0
grep -RInE "autoteacher_m0|import (httpx|requests|urllib|socket|aiohttp|openai|anthropic)|from (httpx|requests|urllib|socket|aiohttp|openai|anthropic)" m1_teacher --include='*.py'

# B 线（期望：仅 docstring 文本，不是 import；由 test_no_m0_import.py AST 双重验证）
cd /root/at-m1-offline
grep -RInE "autoteacher_m0|import (httpx|requests|urllib|socket|aiohttp|openai|anthropic)|from (httpx|requests|urllib|socket|aiohttp|openai|anthropic)" m1_offline --include='*.py'
```

- **A 实测**：`NONE`（0 hit）。
- **B 实测**：2 hit，均为 docstring 文本（`m1_offline/cf/teacher.py:26`、`m1_offline/__init__.py:14`），
  不是 import；AST 级证据由 `tests/m1_offline/test_no_m0_import.py` 提供（含 fresh subprocess 检查）。
- 运行时无网络证据（历史 Reviewer 方法，本文件只冻结命令形态；需 `/tmp` 内的 sitecustomize 阻断 socket）：

```bash
# 示例（需先用 /tmp 构造 deny-socket 的 sitecustomize.py；不放入仓库）
# env PYTHONPATH=/tmp/m1b_nonet "/root/Autonomous Teacher/.venv/bin/python" -m m1_teacher.demo
# env PYTHONPATH=/tmp/m1b_nonet "/root/Autonomous Teacher/.venv/bin/python" -m m1_offline.demo
```

### 4.3 M0 保护路径 diff 检查（两线各自 worktree）

原则：M1 提交不得改 M0/安全/LiveGate 路径；A 线提交不得改 B 线代码，反之亦然。

```bash
# 语法：git diff --name-only <base>..HEAD | 过滤受保护路径；期望：无输出
cd /root/m1b/pr0
git diff --name-only 3e7afee..HEAD \
  | grep -E '^(src/autoteacher_m0/|plugins/|config/|scripts/|artifacts/|security/|bridge/|tests/(unit|integration|security)/|\.github/|pyproject\.toml|AGENTS\.md|README\.md|SECURITY\.md)' \
  || echo "NO_PROTECTED_PATH_CHANGES"

# 反向：B 线 worktree（若将来在 B 线提交）不得改 m1_teacher/ 等 A 线路径
cd /root/at-m1-offline
git diff --name-only 3e7afee..HEAD \
  | grep -E '^(m1_teacher/|tests/m1_teacher/|fixtures/m1_teacher/|docs/M1_)' \
  || echo "NO_CROSS_LINE_PATH_CHANGES"
```

- **本 worktree 实测**：`git diff --name-only 3e7afee..HEAD` 经上述受保护路径过滤后输出
  `NO_PROTECTED_PATH_CHANGES`；B-PR0 提交相对 A 线基线 `4706250` 仅新增 3 个 `docs/M1_B_*.md`。
  `/root/at-m1-offline` 在只读 pytest 运行前后 `git status --porcelain` 均为空（未产生任何修改）。
- 全仓 `tests/` 包含 M0 套件，**不属于本线验收**（见 §5）。

### 4.4 teacher-visible JSON 不回显 hidden expected（B-Q5 运行时扫描方向）

建议在 B-PR1 实现后冻结为测试（本文件只列命令形态，当前 B 线尚未满足）：

```bash
# 方向性命令：对 demo/诊断/导出 JSON 扫描 expected 内容（示例；需具体 case 语料）
grep -RIn "expected" /tmp/m1b_b_artifacts_1.txt || echo "no expected in demo stdout"
# 真实评测必须用 synthetic sentinel 值 + 运行时导出 JSON（不能只看 git 源码 AST）
```

- 现状（`SOURCE_INSPECTED`）：B demo stdout 未出现 `expected` 字样（measured via grep）；不构成
  B1-06 验收（需要 case 级 sentinel）。

---

## 5. 全仓 M0 套件（**不在本线验收范围**，仅原样记录）

Lead 要求：若引用全仓 `tests`，必须原样标注失败项，不得当作 M1 回归，也不得掩盖。

**命令**：

```bash
cd /root/at-m1-offline
env PYTHONDONTWRITEBYTECODE=1 \
  "/root/Autonomous Teacher/.venv/bin/python" -m pytest tests -q -p no:cacheprovider
```

**本 worktree 独立复跑结果（`SOURCE_INSPECTED`，2026-11-20；与 Lead 早前实测一致）**：

```
6 failed, 1697 passed, 19 skipped in 335.58s (0:05:35)
exit=1
```

失败用例（原样，均为 M0/环境相关，**不属于 B 线 M1 回归**）：

1. `tests/integration/g3d/test_d3_contract.py::test_runner_does_not_modify_product_src`
2. `tests/integration/g4_b/test_manifest_contract.py::test_build_is_deterministic_and_excludes_provenance`
3. `tests/integration/g4_b/test_manifest_contract.py::test_rows_are_sorted_and_record_mode_and_size`
4. `tests/integration/g4_b/test_manifest_contract.py::test_manifest_does_not_reference_itself`
5. `tests/integration/g4_d/test_d10_d15_e5_subset.py::test_d15_same_uid_known_path_is_denied_by_mode_not_name`
6. `tests/integration/runtime/test_target_profile_static.py::test_required_files_exist_and_are_read_only_text`

- Lead 早前实测同命令：`6 failed / 1697 passed / 19 skipped in 342s`（同一失败集合；耗时差异为负载）。
- 运行前后 `/root/at-m1-offline` `git status --porcelain` 为空（只读）。
- **纪律**：本线任何报告不得写成“全仓全绿”；M0 失败项保留原样交由 M0/A 线处理，M1-B 只保证
  `tests/m1_teacher` + `tests/m1_offline` 两个子集。

---

## 6. 历史测试数字与“不相加”纪律（冻结）

| 来源 | 命令 | 历史冻结值 | 本 B-PR0 只读复跑（参考，不是新验收） |
|---|---|---|---|
| A 线 `m1a` | `pytest tests/m1_teacher -q` | `536 passed`（Review/报告冻结） | `536 passed in 19.30s`（本 worktree）；Lead 另测 16.47s |
| B 线 `m1_offline` | `pytest tests/m1_offline -q` | `365 passed`（Review 冻结） | `365 passed in 21.96s`（冻结树只读）；Lead 另测 19.38s |
| 全仓 M0（非本线） | `pytest tests -q` | 不适用 | `6 failed / 1697 passed / 19 skipped`（§5，原样记录） |

- **`536 + 365 = 901` 不是任何真实套件**：两条线分开冻结、基线不同、验收范围不同、互不 import；
  不允许在报告/README/STATUS 中用 901 表示统一套件。
- B-PR1..B-PR5 的每个 PR 必须新增/更新自己的测试，并由独立 Reviewer 在**新集成树**上重新跑新的 suite；
  历史 536/365 只作参考值，不能被继承成新验收 PASS。
- 证据类别仍需按 `MOCK / DETERMINISTIC / HUMAN_REVIEWED / NOT_VERIFIED` 标注（A 线报告词汇）；
  当前 B-PR0 只有 `SOURCE_INSPECTED` + `DESIGN_ONLY`，无 `HUMAN_REVIEWED`。

---

## 7. 运行注意事项（操作冻结）

1. **只读树运行**：B 线 `pytest`/demo 必须带 `-p no:cacheprovider` + `PYTHONDONTWRITEBYTECODE=1`；
   demo `--write-artifacts` 只在 archive 副本执行（§3.3）。
2. **A 线工作树**：本 B-PR0 worktree 的 A 套件/demo 可写（非冻结树），但 demo 的 `--write-evidence`
   建议也使用 archive 副本，避免修改 tracked 证据文件（§2.3）。
3. **解释器固定**：所有命令使用 `/root/Autonomous Teacher/.venv/bin/python`（3.11.15 / pytest 9.2.0）；
   不同解释器/版本的结果不得混用。
4. **计时**：本文件记录的时间为特定机器/负载下的观测值；时间本身不是门禁，passed/failed 计数与
   digest 才是门禁。
5. **无网络**：任何命令不得隐含网络访问；如未来需要联网证据，只能另行人类批准的独立工作项。
6. **产物**：`/tmp` 下的 demo 输出/archive 副本不作为交付物；交付物只包括脱敏、可复算的日志片段
   （本文件即为命令与摘要记录）。

---

## 8. 已知问题/风险（`SOURCE_INSPECTED`，供后续 PR 处理）

| # | 问题 | 影响 | 处理 |
|---|---|---|---|
| I-1 | B `--write-artifacts` 的 `eval_baseline_v1.json` 含运行时 `environment.utc_timestamp`（`evaluation/report.py:152`） | 该 JSON 不满足字节级可复现；不得纳入 digest 门禁 | B-PR5 增加固定时钟/屏蔽字段；本文件只冻结 stdout/trace/md 的字节门禁 |
| I-2 | B `JudgeResult.failures` 含 `expected_repr`，与 teacher 同进程（`cf/judge.py:150-164`、`cf/teacher.py:283`） | hidden expected 可能进入 teacher 可见对象/日志 | B-PR1 可信 Judge 边界（`TEST_EVIDENCE_MATRIX.csv` B1-02/B1-06） |
| I-3 | A `result_id` 全局查重（`session/engine.py:833`） | 跨 learner/session 幂等隔离缺陷（B-03） | B-PR3 scoped idempotency |
| I-4 | 全仓 M0 套件 6 failed（§5） | 若被引用可能误读为 M1 回归 | 原样标注、分开处理 |
| I-5 | B 默认 demo 可重复，但 B 线无持久化 DB/session | 不能承担 canonical 验收 | B-PR2/B-PR4（ADR canonical 裁决） |
| I-6 | 两线历史 536/365 易被相加 | 评审口径污染 | 本文件 §6 冻结“不相加”纪律 |
| I-7 | A teacher-visible `AssessmentItem.scoring_spec_ref` 携带 `scoring/...` 路径（`contracts/types.py:678`） | 源码 grep 无法覆盖运行时导出；B1-06 若只做 AST 会漏 | B-PR1 导出投影 + 运行时 item payload 扫描（P2-13，当前 `NOT_RUN`） |

---

## 9. 参考（SOURCE_INSPECTED）

- A：`m1_teacher/demo.py`（`FIXED_TIMESTAMP:103`、`ARTIFACT_MANIFEST_VERSION:106`、`EVIDENCE_DIR:120`、
  `main:1310`）、`m1_teacher/cli.py:138`、`m1_teacher/assessment/scorer.py:6/401`、`docs/M1_IMPLEMENTATION_REPORT.md`、
  `docs/M1_INDEPENDENT_REVIEW.md`、`tests/m1_teacher/test_{assessment_scorer,domain_adapter,e2e_resume_idempotency}.py`。
- B：`m1_offline/demo.py:53-55/342`、`m1_offline/evaluation/report.py:152/393`、
  `m1_offline/cf/judge.py:150-164`、`m1_offline/cf/teacher.py:176-192/283`、`m1_offline/evaluation/contamination.py:54-56`、
  `docs/m1/REVIEW_M1_OFFLINE.md`。
- 交接：`/root/leadb_zip/02_LEADB_AGENT_HANDOFF.md`（B0 第 4 点：冻结两条线 CI/静态隔离/Demo 命令）、
  `AUDIT_REQUESTS.md`（B-Q1/B-Q2/B-Q3/B-Q5）、`TEST_EVIDENCE_MATRIX.csv`（B 线 18 项，初始 `NOT_RUN`）。

---

## 10. 变更记录

| 日期（UTC） | 版本 | 变更 |
|---|---|---|
| 2026-11-20 | B-PR0 初稿 | DRAFT/DESIGN_ONLY：冻结 A/B 两线 suite + demo + 证据命令、digest/计数记录、静态隔离与 M0 diff 检查清单、全仓 M0 套件原样记录（6 failed）、历史数字不相加纪律、已知问题 I-1..I-6 |
| 2026-11-20 | B-PR0 P1 复审修订 | P2-04：冻结命令加入 A 实现树零 diff / B SHA pin + 前后只读断言；P2-13：teacher-visible item 路径的运行时导出扫描列为 B-PR1 冻结验收项（当前 NOT_RUN）；其余 P1 修订见 ADR/PORTS 与 `M1_B_PR0_REVIEW_RESPONSE.md`；仍为 DESIGN_ONLY，未改实现/测试 |
