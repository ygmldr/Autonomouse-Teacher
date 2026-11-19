# M1 Offline Teacher — 独立复核报告（B 线 B5/B8）

| 字段 | 值 |
| --- | --- |
| 任务 | 共享任务板 `task-5`（B5/B8 独立复核 + 并行文档） |
| Reviewer | `b-reviewer`（独立 Reviewer；**未参与** B 线任何实现，未修改实现/测试/fixtures/其它 docs） |
| 复核对象工作树 | `/root/at-m1-offline`（branch `work/m1-offline-design`） |
| base SHA | `3e7afee077845a071cd364e93ab209cac20b2d5f`（main；主工作树 `/root/Autonomous Teacher` HEAD 同值且 clean） |
| 第一轮 impl/docs SHA（冻结审查提交） | `0bb13d27b069dfb71b31ce7e02f9cde41f9bb071`（commit `2026-11-19T18:25:22+00:00`，145 个新增文件） |
| 复核后修复提交 C2（当前 HEAD） | `052d980d9a45558da8789c90725ae6c48f3f7a7d`（commit `2026-11-19T18:56:21+00:00`，`fix(m1-offline): post-review P1/P2 fixes — persisted failure cases, precise provenance, reproducible fingerprint, doc consistency`） |
| 复核文档提交 C3 | `pending`（本文件、`docs/parallel/STATUS.md`、`docs/parallel/DECISION_LOG.md` 由 Lead 在复核完成后统一提交；**未包含在 C2 中**） |
| 评审执行时间 | 2026-11-19 UTC：第一轮独立复现 18:26Z–18:47Z（@`0bb13d2`）；C2 复验 18:57Z–19:06Z（@`052d980d`） |
| 评审环境 | Linux `6.17.13-2-pve`；Python `3.11.15`（`/root/Autonomous Teacher/.venv/bin/python`）；pytest `9.2.0` |
| 证据来源 | **全部结论来自 Reviewer 自己运行的只读命令/探针**（探针在 `/tmp/b2_probe_core.py`、`/tmp/b2_probe_negatives.py`、`/tmp/b2_probe_c2fixes.py` 等；未采信 owner 的 PASS 文本）。C2 复验在 `git archive 052d980d \| tar -x -C /tmp/m1-c2-final` 的**干净副本**上进行（无未提交文档干扰） |
| 结论性质 | **offline synthetic only, not real teaching effect**。本报告不构成真实教学效果 PASS、不是 M1 上线、不改变 M0 G4-H/G5/LiveGate/M0 既有决策；B 线复核后 **STOP** |
| 评审方式 | 只读审计；仅写入本报告、`docs/parallel/STATUS.md`、`docs/parallel/DECISION_LOG.md`；未 commit |

---

## 0. 结论摘要

- **P0 = 0；P1 = 1（第一轮发现，C2 已修复并经 Reviewer 复验关闭）；P2 = 7（6 条在 C2 修复/文档化并经复验关闭；1 条为新披露的工件措辞精度问题，disclosed/deferred，不阻塞）**。
- B-01..B-08（按任务书 §8 权威定义）逐项裁定：**全部 `VERIFIED`**（矩阵与证据见 §2.I）。
- **最终裁定：`PASS_FOR_M1_OFFLINE_DESIGN_AND_EVALUATION_SCOPE`**
  —— 仅限 M1 Offline **设计与离线评测范围**；不是教学效果 PASS、不是 M1 上线、不改变 M0 任何决策。
- 两轮流程：第一轮在 `0bb13d2` 独立复现出 1 个 P1（失败案例清单工件指向错误）+ 6 个 P2；Lead 安排 owners 修复形成 C2；Reviewer 在 **clean C2** 上重新复现 A–J 并逐项验证 P1/P2，确认 **P1-1 与 P2-1..P2-6 全部关闭**、未出现新 P0/P1；新增 P2-7（report JSON 的“两跑字节一致”措辞过宽，仅 trace JSONL 真正逐字节确定）以 disclosed/deferred 记录。
- 复核后状态：B 线按任务书要求 **STOP**，等待维护者/人类决策（见 `docs/parallel/STATUS.md` §1.6/§4、`docs/parallel/DECISION_LOG.md` §4）。

> 边界声明（全文适用）：本报告所有数值与结论只描述本 worktree 内**确定性离线合成模拟器 + 合成 fixtures + 固定 seed** 的行为；
> 不是真实教学效果、不是真实学习者提升、不是真实模型/Provider 能力证据，不报告显著性，不用于任何上线授权。

---

## 1. 复核方法与命令

### 1.1 独立性

- Reviewer 未参与 `m1_offline/**`、`tests/m1_offline/**`、`fixtures/m1/**`、`docs/m1/**`、`docs/interfaces/**` 的编写；未复用 owner 的“PASS”结论。
- 全部测试、demo、评测、污染扫描、回放、v0/v1 对比均由 Reviewer 在冻结 SHA 上重新运行；报告数值均与 Reviewer 的命令输出核对。
- 不联网、不接触真实 Key/真实个人数据、不 `git commit/merge/push`；M0 主工作树全程只读。
- **C2 复验在干净副本上做**（`git archive C2 | tar -x`），避免第一轮遗留的未提交 review 文档影响文件计数与污染扫描；另在真实 C2 worktree（含 3 个未提交 review 文档）中复现了 artifact 的生成上下文（见 §1.4 与 §3 P2-1 备注）。

### 1.2 关键命令

```bash
# 冻结/修复提交与范围
cd /root/at-m1-offline
git rev-parse HEAD                                 # C2
git diff --name-status 3e7afee..052d980d
git diff --name-status 0bb13d2..052d980d

# C2 干净副本（隔离未提交 review 文档）
rm -rf /tmp/m1-c2-final && mkdir -p /tmp/m1-c2-final
git archive 052d980d9a45558da8789c90725ae6c48f3f7a7d | tar -x -C /tmp/m1-c2-final

# 完整测试 + demo 双跑
cd /tmp/m1-c2-final
"/root/Autonomous Teacher/.venv/bin/python" -m pytest tests/m1_offline -q
"/root/Autonomous Teacher/.venv/bin/python" -m m1_offline.demo > /tmp/b_final_demo1.txt
"/root/Autonomous Teacher/.venv/bin/python" -m m1_offline.demo > /tmp/b_final_demo2.txt
diff /tmp/b_final_demo1.txt /tmp/b_final_demo2.txt && sha256sum /tmp/b_final_demo1.txt /tmp/b_final_demo2.txt
# 网络阻断运行（Reviewer 自建 sitecustomize 禁用 socket.*）
PYTHONPATH=/tmp/b_nonet "/root/Autonomous Teacher/.venv/bin/python" -m m1_offline.demo

# 子集与新增回归测试
"/root/Autonomous Teacher/.venv/bin/python" -m pytest \
  tests/m1_offline/test_closed_loop.py tests/m1_offline/test_evaluation_protocol.py \
  tests/m1_offline/test_negatives.py tests/m1_offline/test_contamination.py \
  tests/m1_offline/test_compare_v0_v1.py -q
"/root/Autonomous Teacher/.venv/bin/python" -m pytest \
  tests/m1_offline/test_compare_v0_v1.py::test_persisted_report_contains_comparison_failure_cases \
  tests/m1_offline/test_evaluation_protocol.py::test_dependency_fingerprint_is_reproducible_and_documented \
  tests/m1_offline/test_evaluation_protocol.py::test_report_artifacts_record_precise_commit_provenance \
  tests/m1_offline/test_evaluation_protocol.py::test_baseline_document_references_persisted_failure_cases -q

# P1/P2 独立复验（P1-1/P2-1..P2-6）
"/root/Autonomous Teacher/.venv/bin/python" /tmp/b2_probe_c2fixes.py   # 见 §6
# Reviewer A–J 只读探针
"/root/Autonomous Teacher/.venv/bin/python" /tmp/b2_probe_core.py
"/root/Autonomous Teacher/.venv/bin/python" /tmp/b2_probe_negatives.py
# 指纹一行复现
"/root/Autonomous Teacher/.venv/bin/python" -c "from m1_offline import REPO_ROOT; from m1_offline.evaluation.report import dependency_fingerprint; print(dependency_fingerprint(REPO_ROOT))"
```

### 1.3 第一轮（@`0bb13d2`）原始输出摘要

| 检查 | 实测 |
| --- | --- |
| `pytest tests/m1_offline -q`（0bb13d2） | `361 passed in 16.78s`（exit 0；0 failed/0 skipped） |
| 评测 5 文件 | `72 passed in 7.46s` |
| CF 三文件 / Interview 三文件 | `75 passed` / `49 passed` |
| demo 双跑 stdout | sha256 `fd7228121359bf4732d9654f94f5e42409921b16b456a43d18e9e5a2acf2e224`（两次一致；socket 阻断下同样一致），38 行，exit 0 |
| v1/v0 trace digest | `ed850c775f…` / `4019c9465b…`（从磁盘 JSONL 重算一致） |
| v0/v1 对照 | digest `cb6cb07d…`；14 catalog / seeds[0,1,2] / 72 轮 / 12 assessed / 58 failure cases；两次一致 |
| contamination（第一轮） | C1–C4 全 PASS；hidden=21、public=103、scanned=138、泄漏 0、注入 4、NOT_RUN=0 |
| CF / Interview / freshness | 14 题/112 隐藏/参考解 14/14；22/6/9/4/9/7；9/9 分类正确 |
| 第一轮结论 | 发现 P1-1 + P2-1..P2-6（见 §3），业务/机器证据均真实；**不给无保留 PASS**，交 Lead 修复后复验 |

### 1.4 C2 复验（@`052d980d`）原始输出摘要

| 检查 | 实测（clean C2 副本 / 真实 C2 worktree 注记） |
| --- | --- |
| `pytest tests/m1_offline -q`（clean C2） | **`365 passed in 17.04s`**（重跑一次 `365 passed in 16.54s`；exit 0；= 361 + 4 项 C2 新增回归测试） |
| 评测 5 文件 | `76 passed in 7.53s` |
| CF 三文件 / Interview 三文件 | `75 passed in 8.82s` / `49 passed in 0.07s` |
| 新增 4 项回归测试 | 4/4 passed（`test_persisted_report_contains_comparison_failure_cases`、`test_dependency_fingerprint_is_reproducible_and_documented`、`test_report_artifacts_record_precise_commit_provenance`、`test_baseline_document_references_persisted_failure_cases`） |
| demo 双跑（clean C2 副本） | sha256 **`1d57ca62…`**（两次一致；socket 阻断下同样一致），exit 0 |
| demo 双跑（C2 worktree + 3 个未提交 review 文档 = artifact 生成上下文） | sha256 **`2282caff40787317d8222401e2a7a0f9cdec6d9ac86d2ed8286927a0792df3cb`**（两次一致，与 `EXPERIMENT_BASELINE.md` §9 声明值完全一致） |
| artifact 端到端一致性 | `docs/m1/reports/eval_baseline_v1.json` 的 `comparison.failure_cases`（58 条）与 live `run_comparison(seeds=(0,1,2), max_rounds=12).failure_cases` **精确相等**；`run_digest`=`cb6cb07d…`、statistics、delta、total_rounds 全部与 live 相等；每项含 `policy/policy_version/seed/round/case_id/scorer_id/failure_modes/hidden_cases_passed/hidden_cases_total` |
| artifact provenance | `environment`：`base_sha=3e7afee…`、`implementation_commit=0bb13d2…`、`implementation_commit_note`、`working_tree_dirty=true`、`dependency_fingerprint=ad30fbd…`；**无 `git_sha`**（不再暗示 HEAD==base） |
| 依赖指纹 | `dependency_fingerprint(REPO_ROOT)` = `ad30fbdae1d7318d346b0625a1157df20f9139ef2ece00f7f118a1c9ced6abd0`（两次一致）；manifest=109 文件；文档含一行复现命令；旧 `b4bb2931…` 已标 superseded |
| canonical CF 回放 trace | `docs/m1/traces/cf_loop_canonical.jsonl`：19 事件、21,649 bytes、sha256 `6e3d96ae…`；**逐字节等于** `run_closed_loop(learner_fixture_name="learner_advanced", seed=0, max_rounds=3, loop_id="cf_loop_canonical_seed0").to_jsonl()`；用共享 `replay_trace` 重建 **3 assessments / 6 evidence**，final_state == 最后一个 memory 快照 |
| contamination（clean C2 副本） | C1–C4 全 PASS；hidden=21、public=**104**、scanned=**138**、泄漏 0、注入 4、NOT_RUN=0 |
| contamination（C2 worktree + review 文档 = artifact 上下文） | C1–C4 全 PASS；public=**105**、scanned=**139**（与 committed artifact 的计数完全一致） |
| git/范围 | HEAD=`052d980d`；`git diff 3e7afee..C2` = **146 文件全部为新增**（145 + `cf_loop_canonical.jsonl`）；`git diff 0bb13d2..C2` = **12 M + 1 A**，全部落在允许路径；M0 冻结区零改动；主工作树 HEAD `3e7afee` clean；真实 C2 worktree 仅 3 个未提交 review 文档 |
| 子集/断言回归 | `pytest` 全绿；P1-1/P2-1..P2-6 专项复验脚本输出 **ALL C2 FIX CHECKS PASS**（见 §6） |

> **生成上下文说明（非 finding，Lead 已确认）**：committed artifact 与 demo stdout hash `2282caff…` 生成于“C2 代码 + 3 个未提交 review 文档”的 fix worktree；干净 C2 副本没有这 3 个文档，因此 contamination 公开面计数为 104/138、demo stdout 为 `1d57ca62…`。两者均**逐次确定性**（各跑两次一致），差异仅来自公开面文件集合；C3 提交 review 文档后，干净树将回到与 artifact 一致的文件集合（Reviewer 已在当前 C2 worktree 复现出 `2282caff…` 与 105/139）。

---

## 2. 逐项独立复现与裁定（A–J）

### A. Git / 范围 / M0 冻结区

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| B 线 HEAD 是否为 C2 `052d980d…` | **是** | `git rev-parse HEAD` |
| `git diff 3e7afee..C2` 是否只含允许新路径 | **是**：146 文件全部为**新增**（`docs/interfaces` 1、`docs/m1/*.md` 8、`docs/m1/reports` 3、`docs/m1/traces` 5、`fixtures/m1` 88、`m1_offline` 21、`tests/m1_offline` 20），无删除/修改既有文件 | `git diff --name-status`；路径全部落在 `docs/m1/`、`docs/interfaces/`、`m1_offline/`、`tests/m1_offline/`、`fixtures/m1/` |
| C2 相对第一轮冻结 SHA 的改动面 | **13 文件（12 M + 1 A）**：`report.py`、`demo.py`、2 个 tests、6 个 docs、2 个 reports JSON/MD、`cf_loop_canonical.jsonl`；全部在允许路径内 | `git diff --name-status 0bb13d2..C2` |
| 是否零改动 M0 冻结区 | **是**：无 `src/`、`bridge/`、`accounting/`、`security/`、`plugins/`、`config/`、`scripts/`、`README`、`AGENTS.md`、`pyproject.toml`、`uv.lock`、`.github/` 等；主工作树 HEAD 仍 `3e7afee…` 且 clean | 路径审计 + 主工作树 `git status` |
| 工作树状态 | HEAD=C2；仅有 Reviewer 的 3 个未提交 docs（`docs/m1/REVIEW_M1_OFFLINE.md`、`docs/parallel/STATUS.md`、`docs/parallel/DECISION_LOG.md`），由 Lead 作为 C3 提交 | `git status --porcelain` |

### B. 测试（真实运行与抽查）

- clean C2：`365 passed in 17.04s`（重跑 `365 passed in 16.54s`）；0 failed/0 skipped；测试数 = 361 + 4 项 C2 新增回归测试。
- 子集：评测 5 文件 `76 passed`；CF 3 文件 `75 passed`；Interview 3 文件 `49 passed`；4 个新增测试定向运行 4/4 passed。
- 抽查 4 个测试文件确认非空断言/占位（另交叉抽查）：
  - `tests/m1_offline/test_no_m0_import.py`：AST 静态扫描 + fresh subprocess `sys.modules` 双重隔离检查。
  - `tests/m1_offline/test_negatives.py`：N1–N7 失败负例矩阵，逐项断言“不得静默成功”。
  - `tests/m1_offline/test_closed_loop.py`：3 轮闭环、JSONL 往返、按 event_id/loop_id 回放、无证据不涨、文本/幻觉不涨、两次运行 byte-identical、v0/v1 均可回放。
  - `tests/m1_offline/test_contamination.py`：合成临时树正/负对照（泄漏必被发现、缺失隐藏集必为 NOT_RUN）、reformat 规避检测、报告不回显隐藏文本。
  - 全仓无 `pytest.mark.skip/xfail`、无空测试。

### C. 可运行演示与确定性（无网络 / 无 Key / 无真实 Provider）

- clean C2：`python -m m1_offline.demo` 连续两次 stdout **逐字节一致**（sha256 `1d57ca62…`，`diff` 空，exit 0）；socket 全阻断（`sitecustomize` 禁用 `socket.socket/create_connection/getaddrinfo`）下仍 exit 0 且 sha256 相同 → 运行期无 socket 网络调用。
- 真实 C2 worktree（含 3 个未提交 review 文档）：双跑一致 `2282caff…`，与 `EXPERIMENT_BASELINE.md` §9 声明一致。
- 静态：`m1_offline/**/*.py`（21 文件）AST 无 `httpx/requests/urllib/aiohttp/socket/http/ssl/...` import；fresh subprocess 导入后 `sys.modules` 无 `autoteacher_m0/src/httpx/requests/aiohttp/httpcore/boto3/openai/anthropic`。
- demo 输出显式边界：`[boundary] offline synthetic simulation; not real teaching effect`、`no network / no API key / no real provider / no real personal data`；conclusion 含 `no significance is claimed`。
- 扫描 API Key/真实邮箱/电话/SSN 形态：129 文件，命中 0。

### D. 隔离与安全（公开/隐藏、注入、污染）

- AST/运行期双重隔离同 §A/§C；`m1_offline/**` 无对 `autoteacher_m0` 或 `src` 的真实 import。
- **独立重跑 contamination suite**（Reviewer 自建 `injection_texts`/`system_instructions` 调用，不读 owner 报告）：clean C2 与 C2 worktree 两种上下文中 C1–C4 全 **PASS**、`NOT_RUN=0`、`overall_ok=True`：
  - C1：hidden fixtures **21**（14 CF + 7 interview），公开面 104（clean）/105（含 review 文档），overlap=[]；
  - C2：hidden-only needles 34，子串命中 **0**、滑动窗口哈希命中 **0**；
  - C3：注入文档 4、needles 9、system instruction 命中 **0**；
  - C4：网络 import/API Key/真实邮箱/手机号/SSN 命中 **0**，扫描 138（clean）/139 文件。
- **Reviewer 独立泄漏扫描**：隐藏-only 文本（扣除公开 fixtures 合法共享题面）69 needles → 公开 docs/traces/source 命中 **0**；7 条 hidden 面试题面与 `hidden-q-*` id 均不出现在公开面。
- **Prompt Injection**：4 份 `DATA_ONLY` 注入文档经 `untrusted_docs` 传入后，`instruction_hash` 不变（`c336aec6…`）、system instructions 无注入正文；注入只出现在用户内容位并带 `UNTRUSTED_DATA:<doc_id>` 引用标记（换行被压平，不能越出引用块）。
- **项目事实边界**：缺项目事实 → `ASK_CLARIFICATION`（rationale 禁止虚构规模/百分比/业务成绩）；`a-fabricated-003` 被独立 rubric 判 `passed=False`，`evidence_sufficiency=0.0`、`score=0.4625`，含 `unsourced_quantitative_claim`/`missing_project_facts` 等 failure mode（与文档一致）。
- **数据边界**：88/88 fixtures `synthetic=true` + `license=CC0-1.0`；合成域名 `.invalid`/`example.com`；无真实个人数据形态。

> 关于任务书 G 项“Driver 配置 synthetic/CC0-1.0”：M1 交付物中不存在名为 Driver 的 fixture/配置（全仓 grep 仅命中 M0 `scripts/g4/*` 与 M0 源码，均不在 B 线范围）。本报告按“fixture 来源/许可配置”解释并核验：88/88 `synthetic=true + CC0-1.0`。任务书中的确切指代 **UNVERIFIED/需 Lead 澄清**（不视为失败项）。

### E. 教学闭环真实性（≥3 轮 / 回放 / 证据驱动）

- v1/v0 各 3 轮完整闭环：`rounds=3 / events=19`，步骤序列精确为 `goal→diagnose→gap→plan→(action→response→assess→memory→next_task)×3`；event_id 唯一、loop_id 一致、确定性时钟。
- `replay_trace(events)`：final_state.mastery、assessment_ids、step_sequence 与在线运行**完全一致**；`until_event_id`（9 事件→1 assessment）与 `loop_id` 过滤均可用。
- 磁盘冻结 trace（`loop_v1_3rounds.jsonl` / `loop_v0_3rounds.jsonl`）逐行重建后 re-play 一致，digest 与文档一致。
- 证据驱动探针：无证据→mastery `{}`；`EXPLANATION+observed_score=None`（纯文本/自述）不涨；`HINT_REQUEST+score` 不涨；非枚举 kind `self_report` → `SchemaError`；独立 `ASSESSMENT+score` 涨（0→0.35）；带 `error_codes` 的失败观测即使 score=1.0 也不能推高；同 event_id 幂等。
- 闭环 trace 的 memory 证据 kind 全为 `ASSESSMENT`（来源独立 judge）；demo 3 轮中 2 轮失败且 mastery 保持 0，仅通过轮涨至 0.0875；存在显式失败标记 `hidden_cases_failed`。
- 失败案例：v0/v1 对照 **58** 条 failure case（Reviewer 独立复现并核对字段，见 §1.4/§6）；CF canonical trace 含 1 次失败评估（第 3 轮 0/10），fail-closed 且不涨 mastery。
- **CF canonical trace 回放**：`cf_loop_canonical.jsonl` 19 事件经共享 `replay_trace` 重建 3 assessments/6 evidence，且逐字节等于 live `run_closed_loop(...)` 输出（见 §1.4）；旧 `cf_teaching_loop.jsonl` 为 CF 域审计格式、不兼容共享回放器——已在 CF_SPEC §8.4 显式记录（P2-6）。

### F. 评分器独立性与 v0/v1 对照

- 闭环所有 `AssessmentResult.scorer_id == "independent_cf_judge_v0"`（≠ policy_version）；`CFTeacher.assess()` 完全委托隐藏用例 judge：错误代码 + `submission["passed"]=True` 自述仍 `passed=False`；只过公开用例的作弊解 `hidden_cases_passed=0/7`。
- Interview：`InterviewCoach.assess_answer()` 只调用 `InterviewRubric`（`scorer_id="InterviewRubric:m1.offline.v0"`），rubric 不调用 runtime。
- 盲评：`blind_score(trajectory)` 签名只有 `trajectory`；`BlindTrajectory/BlindRound` 无 policy/teacher/strategy 字段；`_assert_rubric_is_blind()` fail-closed；同盲轨迹两次评分一致。
- v0/v1：固定 14 题 catalog、固定 seeds `[0,1,2]`、每轨迹 12 轮（72 评估轮）、同一模拟学习者；12 个 case 实际被评估（2 题未在固定 12 轮出现，如实记录）；四维均值+方差+失败案例齐全；`run_digest`=`cb6cb07d…` 两次一致并与 artifact 一致。
- 结论文本含 `Offline synthetic simulation only. … not real teaching effect: no significance is claimed …`；`assert_no_overclaim()` 对“显著优于/真实效果”类文本确实抛错；未发现“v1 更好”类越界结论（实际 v1 在 independence/hint_efficiency 上低于 v0，报告如实呈现）。

### G. 垂直场景

**CF Teacher（B-02 相关）**：14 题（数组 3、双指针 3、排序/二分 3、图 2、DP 3）、**112** 条隐藏用例（各题 7–10 条）、30 条公开用例、3 个学习者（BEGINNER/INTERMEDIATE/ADVANCED）、10 条错误轨迹、参考解 **14/14** 在全部隐藏用例 PASS（Reviewer 直接 `CFJudge.evaluate` 全量跑）。Hint Ladder 探针：默认 `LIGHT_HINT L1`；新学习者显式 L4 被证据门钳到 L1；满足证据门显式 L4 → `FULL_SOLUTION L4`；自适应升级（非显式 L4）→ `STRUCTURE_HINT L3`；诊断错误码 → `SOCRATIC_QUESTION/EXPLAIN`。诊断 UNKNOWN/NEEDS_REVIEW 由 diagnostics + 测试覆盖；judge 非 OS 沙箱已在文档声明。

**Interview Coach + Freshness（B-03/B-04 相关）**：22 题 / 6 JD（rec·ml·sys 各 v1+v2）/ 9 knowledge / 4 injection / 9 answers / 7 hidden（逐目录计数符合）；5 阶段追问 ladder；四维 rubric 确定性；9 条答案全部可评分、负例答案触发显式 failure mode；项目事实缺失 → ASK_CLARIFICATION；Freshness 9/9 与 `expected_change_kind` 一致（KEEP 2/UPDATE 2/RECHECK 5），expired/conflict/older/future → RECHECK 且 `curriculum_eligible=False`、`recheck_required=True`，`apply()` 只分组不写课程；`published_at`/`observed_at`/`valid_until`/`uri`/`confidence`/`claim_status` 均存在且显式区分。

### H. 文档与结论边界

| 检查 | 结果 |
| --- | --- |
| M0 Runtime 能力是否一律 UNVERIFIED | **是**：`ADR-TEACHER-CORE.md`、`PRODUCT_SCOPE.md`、`TEACHER_CORE_ARCHITECTURE.md`、`docs/interfaces/teacher_runtime_boundary_v0.md` 头部与正文均显式 `UNVERIFIED`，禁止“M0 已实现/已验收”引用 |
| 接口文档是否 DRAFT / NOT_FROZEN | **是**：`docs/interfaces/teacher_runtime_boundary_v0.md` 头部 `DRAFT / NOT_FROZEN`，A 线“尚未冻结” |
| ADR 是否 Proposed | **是**：`ADR-CORE-1..7` 全部 `Proposed`，含未决问题 Q1–Q7 与决策请求 |
| 是否出现越界表述（M1 GO / G4-H5 / 上线 / 真实教学效果 PASS / 显著提升 / 无证据 v1 更好） | **未发现**；`PASS` 仅用于 MEASURED 的 contamination/demo/测试语境；全文“真实教学效果”均带否定/边界限定；grep 无 `M1 GO`、`G4-H5`、`G4-H1`、“可以上线”等 |
| PLAN 值 vs MEASURED 值是否区分 | **是**：`EVALUATION_PROTOCOL.md` §10、`EXPERIMENT_BASELINE.md` §10、各 spec 的 PLAN/MEASURED 两列表；实测值经 Reviewer 复跑一致（365 passed、76/75/49 子集、digest、计数、artifact 哈希、canonical trace、failure_cases） |
| NOT_RUN 项是否如实标注 | **是**：真实 Provider/live runtime、真实学习效果、统计显著性、interview 端到端闭环、M0 Runtime 验收、人类评分校准、Windows、覆盖率等均标 NOT_RUN/UNVERIFIED（见 §2.J） |
| enum 文档与 `types.py` 是否一致 | **是（C2 后）**：`EVIDENCE_KIND/CLAIM_STATUS/CHANGE_KIND/TEACHER_ACTION_KIND/DIAGNOSTIC_STATUS/HINT_LADDER` 全部可在 docs 中对上；`PRACTICE` 已在 ARCHITECTURE + interface 文档记录为 reserved（P2-5 关闭） |
| artifact provenance 是否精确 | **是（C2 后）**：env 使用 `base_sha` + `implementation_commit` + `implementation_commit_note` + `working_tree_dirty`，不再使用暗示 HEAD 的 `git_sha`（P2-1 关闭） |
| 依赖指纹是否可复现 | **是（C2 后）**：`dependency_fingerprint()` = `ad30fbd…`，109 文件，算法/命令文档化，旧 `b4bb2931…` 标 superseded（P2-2 关闭） |

### I. 验收矩阵（按任务书第 8 节 B-01..B-08 权威定义逐项裁定）

> 说明：`docs/m1/PRODUCT_SCOPE.md` §8 的 B-01..B-08 行归属为 b-core 工作假设，与任务书 §8 不同；C2 已明确该表为 authoring snapshot/工作假设，权威 = 任务书 §8 + 本报告（P2-4 关闭）。本表按任务书 §8 裁定。

| ID | 验收对象（任务书 §8） | 裁定 | 独立证据（C2 复验） |
| --- | --- | --- | --- |
| B-01 | Teacher Core Schema 和 Mock Runtime Port（schema test / no M0 import） | **VERIFIED** | 365 passed（含 `test_schema.py` 57 项 16 Record 往返/枚举校验、`test_runtime_port.py` 14 项确定性/`simulated=True`/错误注入）；AST + fresh subprocess 零 M0/网络 import |
| B-02 | CF Teacher 诊断 + Hint Ladder（本地 Judge + 人工核定错误类型） | **VERIFIED** | CF 三文件 75 passed；14 题/112 隐藏/参考解 14/14；默认 L1、L4 需显式+证据门、自适应不跨 FULL；判分只来自隐藏用例；canonical trace 可回放 |
| B-03 | Interview Coach 多轮追问 + Rubric（公开/隐藏 Fixture + 独立评分） | **VERIFIED** | 22/6/9/4/9/7 语料；5 阶段追问；四维 rubric、scorer_id 独立；项目事实边界 ASK_CLARIFICATION；注入不改 system hash |
| B-04 | Freshness Manager 变化与过期/冲突（时间快照与来源 diff 测试） | **VERIFIED** | 9/9 分类正确（2/2/5）；expired/conflict/older/future → RECHECK 且不可入课程；published_at vs observed_at 显式区分；17 项测试通过 |
| B-05 | Teacher 长期闭环可重放（≥3 轮 Synthetic Simulation + 状态事件） | **VERIFIED** | v0/v1 各 3 轮/19 事件；event_id/loop_id 回放 state/assessments/steps 全等；冻结 trace digest 一致；canonical CF trace 19 事件经共享 replayer 重建 3 assessments/6 evidence；无证据/纯文本/幻觉不涨 |
| B-06 | 隐藏题、恶意文档、虚构经历负例（contamination/injection/unsupported claims） | **VERIFIED** | C1–C4 全 PASS（hidden=21、泄漏 0、注入 4、扫描 138/139）；N1–N7 fail-closed；7 hidden 题面/id 不泄漏；虚构数字被标记、缺事实先澄清 |
| B-07 | 可复现的 v0/v1 对比协议（固定 case、独立评测器、误差说明） | **VERIFIED** | 14 case/seeds[0,1,2]/72 轮；盲评签名无策略字段；四维均值+方差；**58 条 failure_cases 已持久化于 artifact 且与 live 精确一致**；digest `cb6cb07d…`；`not real teaching effect` + no significance claimed；无越界结论 |
| B-08 | 独立 M1 Offline Review，随后 STOP（源码/数据/trace 校验与 ADR） | **VERIFIED** | 本报告（两轮独立复核：@0bb13d2 + C2 复验；可复现命令/原始输出；P0/P1/P2；B-01..B-08 裁定；已知限制；STOP）；ADR 全部 Proposed；Reviewer 未修改实现，仅 3 个 docs |

### J. 已知限制（文档如实列出，Reviewer 复核确认）

- 全部结果为 **offline synthetic**；模拟学习者由确定性合成函数生成、**未经校准**，不代表真实学习者（`EXPERIMENT_BASELINE.md` §12.1）。
- Runtime 为 **MockRuntimePort**（`simulated=True`），无真实 Provider/Key/网络；**真实 Provider / live runtime：NOT_RUN**。
- **真实教学效果 / 真实学习者提升：NOT_RUN**（且非目标）；不报告显著性/置信区间（统计推断 **NOT_RUN**）。
- `CFJudge` 是本地子进程 + 超时 + 临时目录，**不是 OS 安全沙箱**；只用于合成 CC0-1.0 fixtures。
- 隐藏 fixture 信任边界：judge 原样接收 hidden dict；真实考试级访问控制未实现（UNVERIFIED）。
- Freshness 内容指纹 v0 限制（无正文 digest；元数据相同则正文变更会判 KEEP）；真实抓取/调度 UNVERIFIED。
- 人类评分校准 **NOT_RUN**；Interview 端到端多轮教学闭环 **NOT_RUN**；Windows 进程组 **NOT_RUN**；覆盖率测量 **NOT_RUN**；M0 Runtime 能力 **UNVERIFIED**。
- artifact 生成上下文：`eval_baseline_v1.json`/`contamination_v1.json`/demo hash `2282caff…` 生成于“C2 代码 + 未提交 review 文档”的 fix worktree；干净 C2 副本对应计数 104/138、demo hash `1d57ca62…`；C3 提交后文件集合与 artifact 上下文一致。两种上下文均逐次确定性，差异仅来自公开面文件集合（非代码不确定性）。
- `--write-artifacts` 的 **trace JSONL 两跑逐字节一致**（已验证）；**report JSON 含 `environment.utc_timestamp`**，跨次运行该字段变化（P2-7，disclosed/deferred；不影响 trace 证据与指标值）。

---

## 3. Findings（两轮合并，含 C2 处置与复验）

### 3.1 汇总

| ID | 级别 | 标题 | 状态（C2 复验后） |
| --- | --- | --- | --- |
| P0 | — | 无 | — |
| P1-1 | P1 | `EXPERIMENT_BASELINE.md:120` 称失败案例清单在 `eval_baseline_v1.json`，第一轮该工件只有 16 条聚合 metrics（无逐条 failure_cases） | **FIXED IN C2，VERIFIED**：artifact `comparison.failure_cases`=58 且与 live `run_comparison()` 精确相等；文档改指 `comparison.failure_cases`；新增回归测试通过 |
| P2-1 | P2 | 第一轮 reports/基线 provenance 写 base SHA `3e7afee`（暗示 HEAD==base），未记录冻结 `0bb13d2` | **FIXED IN C2，VERIFIED**：env 使用 `base_sha` + `implementation_commit=0bb13d2` + note + `working_tree_dirty`；无 `git_sha` |
| P2-2 | P2 | 第一轮依赖冻结指纹 `b4bb2931…` 无法按文档算法复现 | **FIXED IN C2，VERIFIED**：`dependency_fingerprint()`=`ad30fbd…`（109 文件、算法/一行命令文档化、旧指纹标 superseded） |
| P2-3 | P2 | `PRODUCT_SCOPE.md` 实测数字/状态陈旧（161 vs 实际 165；“开发中/验收 NOT_RUN”） | **FIXED IN C2，VERIFIED**：改为 165 + authoring snapshot 声明 |
| P2-4 | P2 | `PRODUCT_SCOPE.md` §8 的 B-01..B-08 行归属与任务书 §8 权威定义不同 | **FIXED IN C2，VERIFIED**：标注 working assumption/authoring snapshot，权威 = 任务书 §8 + 本报告 |
| P2-5 | P2 | `TEACHER_ACTION_KIND_VALUES` 含 `PRACTICE`，docs 未记录且策略从不发出 | **FIXED IN C2，VERIFIED**：ARCHITECTURE + interface 文档记录为 reserved enum；`types.py` 未改 |
| P2-6 | P2 | CF 域审计 trace payload schema 与 b-eval `replay_trace` 不互通（静默返回 0 assessment） | **ACCEPTED（首轮披露）+ C2 文档化修复，VERIFIED**：CF_SPEC §8.4 明确限制与用途边界；新增 `cf_loop_canonical.jsonl`（19 事件，共享 replayer 重建 3 assessments/6 evidence，逐字节等于 live run） |
| P2-7 | P2 | （新发现，C2 复验）`EXPERIMENT_BASELINE.md` §9 “确定性产物（--write-artifacts，两跑字节一致）”措辞过宽：trace JSONL 确为逐字节确定，但 report JSON 含 `environment.utc_timestamp`，跨次运行该字段变化 | **DISCLOSED / DEFERRED**（不阻塞；建议后续把措辞精确为“trace JSONL 两跑逐字节一致；report JSON 除生成时间戳外确定”，或把 utc_timestamp 移出字节确定性承诺） |

### 3.2 详细说明（证据 / 复现 / 影响 / 处置）

**P1-1 失败案例清单的工件指向错误（C2 已修复并复验）**

- 第一轮证据：`docs/m1/EXPERIMENT_BASELINE.md:120` 称“清单在 `docs/m1/reports/eval_baseline_v1.json`”，但该 JSON keys 为聚合 metrics（16 条），无逐条 failure_cases；协议要求见 `docs/m1/EVALUATION_PROTOCOL.md:18,124`。
- 复现（C2）：`python -c "import json;d=json.load(open('docs/m1/reports/eval_baseline_v1.json'));print(sorted(d));print(len(d['comparison']['failure_cases']))"` → 含 `comparison` 且 58 条。
- C2 修复与复验：artifact 的 `comparison.failure_cases` 与 live `run_comparison(seeds=(0,1,2), max_rounds=12).failure_cases` **精确列表相等**；`run_digest`/statistics/delta/total_rounds 与 live 相等；每项含 `policy/policy_version/seed/round/case_id/scorer_id/failure_modes/hidden_cases_passed/hidden_cases_total`；`test_persisted_report_contains_comparison_failure_cases`、`test_baseline_document_references_persisted_failure_cases` 通过。**关闭。**

**P2-1 provenance（C2 已修复并复验）**

- 第一轮证据：`EXPERIMENT_BASELINE.md:14,17,209,215` 与两个 report JSON 的 `environment.git_sha=3e7afee`。
- C2 复验：`environment` = `{base_sha: 3e7afee…, implementation_commit: 0bb13d2…, implementation_commit_note, working_tree_dirty: true, dependency_fingerprint: ad30fbd…}`；无 `git_sha`；`test_report_artifacts_record_precise_commit_provenance` 通过。**关闭。**

**P2-2 依赖指纹（C2 已修复并复验）**

- 第一轮：`b4bb2931…` 无法按“相对路径+内容 SHA256 排序”的文档算法复现（Reviewer 试 10+ 种合理实现均不匹配）。
- C2：`dependency_fingerprint(REPO_ROOT)` = `ad30fbdae1d7318d346b0625a1157df20f9139ef2ece00f7f118a1c9ced6abd0`（两次一致）；manifest 109 文件（21 py + 88 fixtures）；算法与一行复现命令写入 `EXPERIMENT_BASELINE.md` §1/§2；旧指纹标 superseded；`test_dependency_fingerprint_is_reproducible_and_documented` 通过。**关闭。**

**P2-3 / P2-4 PRODUCT_SCOPE（C2 已修复并复验）**

- C2 复验：无 `161 passed`，改为 165 + authoring snapshot 声明；§8 明确“权威定义以任务书 §8 + REVIEW_M1_OFFLINE 为准”；无“开发中；验收 NOT_RUN”。**关闭。**

**P2-5 PRACTICE 枚举（C2 文档化修复并复验）**

- C2 复验：`TEACHER_CORE_ARCHITECTURE.md` 与 `docs/interfaces/teacher_runtime_boundary_v0.md` 均记录 `PRACTICE` 为 reserved/保留值（当前策略不发出）；`types.py` 未改；enum/文档一致性探针通过。**关闭。**

**P2-6 CF trace 互通性（ACCEPTED + C2 文档化修复，复验通过）**

- 首轮证据：`cf_teaching_loop.jsonl` 的 assess payload 字段平铺，`replay_trace`（`harness.py:1241`）读取 `payload["assessment"]` → 静默 0 assessment/空 mastery。
- C2 复验：CF_SPEC §8.4 明确两份 trace 的格式差异、用途边界与“非 canonical 不得作回放证据”；新增 `cf_loop_canonical.jsonl`：19 事件，`replay_trace` 重建 3 assessments/6 evidence，final_state == 最后一个 memory 快照，且**逐字节等于** live `run_closed_loop(learner_fixture_name="learner_advanced", seed=0, max_rounds=3, loop_id="cf_loop_canonical_seed0").to_jsonl()`；sha256 `6e3d96ae…` 与文档一致。B-05 官方回放证据仍以 loop_v0/v1 为准。**该 P2 以 disclosed limitation 关闭。**

**P2-7 report JSON 字节确定性措辞（新发现，disclosed/deferred）**

- 证据：`EXPERIMENT_BASELINE.md` §9 “确定性产物（`--write-artifacts`，两跑字节一致）”。Reviewer 在 throwaway pristine copy 中连续两次 `--write-artifacts`（间隔 2s）：`docs/m1/traces/loop_v1_3rounds.jsonl` 逐字节一致（sha256 `ed850c77…`），但 `docs/m1/reports/eval_baseline_v1.json` 仅差 `environment.utc_timestamp`（`19:05:36Z` vs `19:05:42Z`）；`eval_baseline_v1.md` 无时间戳差异。
- 影响：trace 证据（核心回放证据）确定性成立；report JSON 的“字节一致”承诺对含时间戳工件不成立（指标值/指纹/失败清单本身确定性，已验证）。不阻塞设计/评测结论。
- 处置：**DISCLOSED / DEFERRED**（Lead 指示：其余 P2 可记录 disposition；不强制本轮修复）。建议后续措辞精确化。

---

## 4. 已知假设与未决问题

1. **artifact 生成上下文**：committed report/contamination artifact 与 demo hash `2282caff…` 生成于“C2 代码 + 未提交 review 文档”的 fix worktree；干净 C2 副本对应 104/138 与 `1d57ca62…`；Reviewer 已在真实 C2 worktree（含 3 个 review 文档）复现出 artifact 的 105/139 与 `2282caff…`，证明差异仅来自公开面文件集合，不是代码不确定性（Lead 已确认该上下文，非 finding）。
2. **任务书 G 项 “Driver 配置”**：B 线无名为 Driver 的工件；本报告按 fixture 来源/许可配置解释（88/88 synthetic+CC0-1.0）；若另有含义属任务书歧义，需 Lead 澄清（UNVERIFIED）。
3. **B-01..B-08 编号口径**：本报告按任务书 §8；PRODUCT_SCOPE §8 为工作假设（C2 已标注权威口径，P2-4 关闭）。
4. **v0/v1 case 覆盖**：14 题 catalog 中 12 题在固定 12 轮内被评估（文档如实记录，未虚报）。
5. **MockRuntimePort 边界**：只证明“可替换边界 + 零网络 + 确定性”，不代表任何真实模型质量；live adapter 必须另立 ADR/接口冻结并由维护者批准。
6. **评审工具非安全审计**：contamination 是工程扫描，不是安全审计；CFJudge 不是 OS 沙箱；均按文档如实声明。
7. **C2 后的文档冻结**：P2-7 为 disclosed/deferred；其余 P2 已关闭。Reviewer 不修改实现/其它 docs；如需后续措辞修复，由 Lead 决定是否新提交。

---

## 5. 最终裁定

**`PASS_FOR_M1_OFFLINE_DESIGN_AND_EVALUATION_SCOPE`**

- 前提确认：P0=0；第一轮唯一 P1（P1-1）已在 C2 修复并由 Reviewer 在 clean C2 上复验关闭；P2-1..P2-6 全部修复/文档化并复验关闭；P2-7 为 disclosed/deferred 的工作措辞问题，不影响结论；C2 复验未出现新 P0/P1。
- 关键证据均在冻结/修复 SHA 上由 Reviewer **独立复现**：365 passed、demo 双跑确定性（含网络阻断）、零 M0/网络/Key、闭环与 canonical trace 回放、独立评分与盲评、v0/v1 固定 case/seed/digest/58 failure cases 持久化且与 live 一致、contamination、垂直场景规模与参考解、artifact 哈希/指纹/provenance、文档边界。
- **本裁定明确不表示**：

  1. 真实教学效果或真实学习者提升（**NOT_RUN**，不声称、不推断）；
  2. M1 上线/产品化/接入真实 Runtime（未发生；`I-01 BLOCKED`，需 M0 G6 GO/CONDITIONAL GO + 新审批）；
  3. M0 能力（G4-H/G5/LiveGate/M0 决策）的任何变化（M0 能力一律 **UNVERIFIED**，全部保持原状）；
  4. 对 A 线或人类审批的任何替代（H-01/H-02/H-03 仍 BLOCKED）。

- B 线按任务书要求 **STOP**：本报告落盘后 Reviewer 不再修改实现；等待 Lead 终审与维护者决策（见 `docs/parallel/STATUS.md`、`docs/parallel/DECISION_LOG.md`）。

---

## 6. C2 复验记录（P1/P2 关闭证据）

| 项 | 复验命令/方式 | 结果 |
| --- | --- | --- |
| 完整测试 | clean C2：`pytest tests/m1_offline -q` | `365 passed`（16.54–17.04s，0 failed/0 skipped） |
| 新增回归测试 | 4 个测试定向运行 | `4 passed` |
| P1-1 artifact=failure_cases | `/tmp/b2_probe_c2fixes.py`（P1-1 段） | 58 条，字段齐全，与 live `run_comparison().failure_cases` 精确相等；digest/statistics/delta 相等 |
| P2-1 provenance | 同上 | base_sha/implementation_commit/note/dirty/fingerprint 正确，无 git_sha |
| P2-2 fingerprint | 一行命令 + 探针 | `ad30fbd…`，两算一致，109 文件，文档化，旧指纹 superseded |
| P2-3/P2-4 PRODUCT_SCOPE | 探针文本检查 | 165 + authoring snapshot + 权威=任务书 §8+REVIEW |
| P2-5 PRACTICE | 探针文本检查 + types.py | docs 记录 reserved；types.py 未改 |
| P2-6 CF trace | 探针回放 | canonical trace 19 事件/3 assessments/6 evidence，逐字节等于 live run；legacy 限制文档化 |
| artifact 哈希 | fresh pristine extract `sha256sum` | `eval_baseline_v1.json` `25ed416a…`、`.md` `154ef1d8…`、`contamination_v1.json` `8b80a6f3…`、`cf_loop_canonical.jsonl` `6e3d96ae…`、loop traces `ed850c77…`/`4019c946…` — 全部与文档声明一致 |
| demo 确定性 | 两上下文各双跑 + socket 阻断 | clean C2 `1d57ca62…` 两次一致；C2 worktree `2282caff…` 两次一致（= artifact 声明）；网络阻断一致 |
| contamination | 两上下文重跑 | 均 C1–C4 PASS、NOT_RUN=0；clean 104/138；worktree+docs 105/139（= artifact 计数） |
| A–J 只读探针 | `/tmp/b2_probe_core.py`、`/tmp/b2_probe_negatives.py` | 全部 PASS（含 hint ladder、N1–N7、注入 hash、泄漏扫描、enum/文档一致性、垂直场景、freshness） |

---

## 7. Reviewer 只读探针与原始输出位置

- `/tmp/b2_probe_core.py`：A（AST/运行期隔离、Key/PII 扫描）、B（闭环/回放/证据规则）、C（v0/v1 盲评/对照）、D（contamination/注入）、E（垂直场景/新鲜度）。
- `/tmp/b2_probe_negatives.py`：Hint Ladder 安全门、N1–N7 负例、项目事实边界、trace 微泄漏、共享文本感知的独立泄漏扫描、enum/文档一致性。
- `/tmp/b2_probe_c2fixes.py`：P1-1/P2-1..P2-6 C2 专项复验（artifact=failure_cases、provenance、fingerprint、PRODUCT_SCOPE、PRACTICE、canonical trace、新增测试）。
- `/tmp/b_nonet/sitecustomize.py`：socket 全阻断运行期探针。
- 原始输出：`/tmp/b_final_demo1.txt`、`/tmp/b_final_demo2.txt`、`/tmp/b_final_demo_nonet.txt`（clean C2，sha256 `1d57ca62…`）；`/tmp/b_c2worktree_demo1.txt`/`b_c2worktree_demo2.txt`（C2 worktree，sha256 `2282caff…` = artifact 声明）；`/tmp/ff_r1.json`、`/tmp/ff_r2.json`（P2-7 两次 `--write-artifacts` 差异仅 `utc_timestamp`）。
- 干净副本：`/tmp/m1-c2-final`（git archive C2 解包，用于无干扰复验；复验后可删）。

（报告完）
