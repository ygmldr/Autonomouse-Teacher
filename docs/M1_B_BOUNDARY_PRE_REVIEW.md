# M1-B / B-PR0 独立静态预审（Contract / Ports / CI / Judge Boundary）

| 项 | 值 |
|---|---|
| 角色 | 独立 Reviewer（未参与 B-PR0 实现；本轮仅新增本文件并提交） |
| 被审 worktree | `/root/m1b/pr0`，分支 `b-next/pr0-convergence-adr`；审查开始 HEAD `7e3bb60003143a15dcddaee5010d710caf138204`；审查期间外部 merge `7fcbcfe07abd5d155262e3870ad5280639f3b621`（见 §1.1 工作树注记），本文件提交在其上；基线 `4706250` |
| 被审交付 | `docs/M1_B_CONVERGENCE_ADR.md`（562 行）、`docs/M1_B_PORTS.md`（537 行）、`docs/M1_B_CI_AND_DEMO.md`（402 行） |
| 关联评审对象 | `docs/M1_B_THREAT_MODEL_JUDGE.md`（B-PR1 设计；审查开始时仅在 `/root/m1b/tm`，审查期间由外部 merge `7fcbcfe` 加入本分支，两处 sha256 相同）；`/root/leadb_zip/{START_HERE,02_LEADB_AGENT_HANDOFF,AUDIT_REQUESTS,COMMON_REVIEW_AND_ROADMAP}.md`、`TEST_EVIDENCE_MATRIX.csv` |
| 源码基线 | A `m1a.v0@4706250`（本 worktree 同树）；B `m1.offline.v0@290c577`（`/root/at-m1-offline`，只读） |
| 审查时间 | 2026-11-20 UTC（本机 `Linux 6.17.13-2-pve`，Python `3.11.15`，pytest `9.2.0`，bwrap `0.9.0`） |
| 结论 | **`PRE_REVIEW_PASS_WITH_ACTIONS`** |
| Findings | **P0 = 0；P1 = 8；P2 = 13**（详见 §4） |
| 证据标签 | `SOURCE_INSPECTED`；`INDEPENDENTLY_REEXECUTED_THIS_TURN`（仅本轮真实执行的命令）；`NOT_RUN`；`UNVERIFIABLE` |

> **验收边界（先读）**：本结论是**静态预审**，**不是集成 PASS**；**B-PR1..B-PR5 均未验收**；
> `TEST_EVIDENCE_MATRIX.csv` 中 **`B0-01` 仍应视为 `NOT_RUN`**，`B1-01..B1-06` 也仍为 `NOT_RUN`。
> 本文件不修改任何源码/测试/fixture，不生成 Owner 证据，不把历史 `536`/`365` 合并成新验收。
> `LOCAL_PROBE` 只证明设计可行性，不等于验收。本文不含任何 hidden expected 内容。

---

## 0. 结论摘要

1. **Canonical 裁决方向成立**：ADR 以 `m1_teacher`（`m1a.v0`）为唯一 TeacherCore/事件协议/Mastery 写入者/
   Replay、以 `m1_offline` 为 CF/Interview/Freshness vertical，理由（持久化、session 状态机、结构化 Reason、
   知识图、可恢复 Replay）与源码事实一致；对 B 反选方案的代价也给了证据。**未发现需要推翻裁决的 P0**。
2. **“禁止双写 / 禁止自动迁移真实 DB”写得足够硬**：ADR §7.5 与 §8、PORTS §1/§4 都有明确禁令与信任分层；
   B vertical 被结构性地限制为纯函数端口（不可写 canonical）。**唯一例外**是 ADR §4.5/§7.2 给“维护者批准的
   一次性 mastery 导入”留了口子，会制造不可重建的 mastery（P1-05）。
3. **v1 adapter 的 additive/拒绝/checksum/rollback 四要素都有设计，但没有全部闭合**：`REJECT` 码齐全、
   rollback 条件可执行；但 `map_evidence_event()` 在 canonical `seq/id` 生成前就返回 `HistoryEvent`（P1-03），
   `source_sha256`/`migrated_sha256` 的 bundle 序列化未定义（P1-03），ADR 还保留“给冻结记录加可选字段”的
   后门（P1-04），与 `m1a.v0` 冻结/严格 `from_dict`/digest 冲突。
4. **事件协议尚缺 B→A 的具体映射表**：ADR 写“映射表见 §5.1”，但 §5.1 只有集合对比，没有 6 个 B kind 到
   12 个 A event_type 的逐项映射/payload 约束（P1-02）。这使 B-PR4/PR5 的事件迁移无法独立实现和验收。
5. **四端口覆盖基本完整**（CF hint/judge、Interview 5 阶段/rubric、Freshness KEEP/UPDATE/RECHECK 都有落点），
   但与 Judge 可信边界有三处实质冲突：`trusted_fixture_test_only` 由请求方提供（P1-01）、
   `KnowledgeClaim` 的 `untrusted/trust_tier/claim_status` 由 claim 自报（P1-06）、Interview 4 维 rubric
   没有 canonical 载体（P1-07）。
6. **CI 数字纪律合格**：536/365 分开冻结、明确“901 不存在”、全仓 M0 的 `6 failed / 1697 passed / 19 skipped`
   原样记录且未冒充 M1 回归。两条冻结命令本轮均复跑成功（A `536 passed`、B `365 passed`），A/B demo
   digest、A 证据三件套、B trace/.md 工件也与文档一致；B `eval_baseline_v1.json` 确因 `utc_timestamp`
   不具备字节确定性，文档已如实披露并排除出字节门禁。
7. **威胁模型总体合格**：request 无 expected/tests/scoring 路径、response 无 verdict/passed、默认
   `UNTRUSTED_CODE_EXECUTION_BLOCKED`、沙箱不可用绝不回退裸子进程、B1-01..06 映射完备、LOCAL_PROBE
   边界声明清楚。**但冻结的 bwrap 启动命令把 `--size` 放在 `--tmpfs` 之后，bwrap 0.9.0 直接报错**
   （P1-08）；另有 request_id 正则与示例不一致、协议通道 stdout/fd3 表述不一致（P2-05/P2-06）。
8. **结论**：`PRE_REVIEW_PASS_WITH_ACTIONS`。没有 P0；但 **P1-01/02/03/04/05/06/07 必须在对应 PR 动工前关闭**，
   **P1-08 在 B-PR1 的 OS 规格冻结前修正**。P1-04/P1-05 建议在 B0 签收前就修，因为它们直接触及
   “唯一写入者/冻结合同”的核心承诺。

---

## 1. 审查范围与方法

### 1.1 实际阅读/核对的范围

- 三份交付文档全文；威胁模型全文（707 行）；`START_HERE`、`02_LEADB_AGENT_HANDOFF` B0/B1/B4 段、
  `AUDIT_REQUESTS` B-Q1..B-Q5、`COMMON_REVIEW_AND_ROADMAP` B-01..B-04、`TEST_EVIDENCE_MATRIX.csv` B0/B1 行。
- A 源码：`m1_teacher/contracts/{types,domain}.py`、`knowledge/graph.py`、`learner/{model,history,repository}.py`、
  `session/engine.py`、`assessment/scorer.py`、`domains/cf_binary_search.py`、`demo.py`、`cli.py`。
- B 源码：`m1_offline/{types,memory,learner_model,runtime_port,teaching_policy,curriculum_planner,freshness}.py`、
  `cf/{judge,teacher}.py`、`interview/{coach,rubric}.py`、`evaluation/{harness,report,contamination}.py`、`demo.py`。
- 除源码外，还用 `git show --stat HEAD`、`git diff --name-only 3e7afee..HEAD`、`git status --porcelain` 核对了
  提交范围与只读性。

> **工作树注记（外部变更，非本 Reviewer 操作）**：审查开始时 HEAD = `7e3bb60`；审查期间该 worktree 被外部
> merge `7fcbcfe`（`b-next/pr1-threat-model`）推进，新增 `docs/M1_B_THREAT_MODEL_JUDGE.md`（与
> `/root/m1b/tm/docs/M1_B_THREAT_MODEL_JUDGE.md` sha256 相同：`c8255d91…c709`）。本预审未参与该 merge，
> 未修改威胁模型；CI §4.3 中“B-PR0 相对 4706250 仅新增 3 个 `docs/M1_B_*.md`”的陈述在 `7e3bb60` 上成立，
> 在当前 HEAD 已多出威胁模型文件——这是外部合并的事实，不计为 PR0 文档缺陷，但复审该句时应更新计数。

### 1.2 本轮真实执行的命令（`INDEPENDENTLY_REEXECUTED_THIS_TURN`）

| # | 命令（工作目录） | 本轮输出 | 判定 |
|---|---|---|---|
| C1 | `cd /root/m1b/pr0 && "/root/Autonomous Teacher/.venv/bin/python" -m pytest tests/m1_teacher -q` | `536 passed in 18.10s`，exit 0 | 与冻结值 536 一致 |
| C2 | `cd /root/at-m1-offline && git status --porcelain && "/root/Autonomous Teacher/.venv/bin/python" -m pytest tests/m1_offline -q -p no:cacheprovider` | `git status` 空；`365 passed in 19.26s`，exit 0 | 与冻结值 365 一致；冻结树未写 |
| C3 | `cd /root/m1b/pr0 && ... -m m1_teacher.demo`（单跑，`/tmp`；与 CI 文档 digest/行数比对） | exit 0；53 行；`sha256=b08ceee915fb0363864e303ded71de4d547eae6d14f7aa693ba1537a810d491b`；stderr 0 | 与 CI 文档一致 |
| C4 | A `git archive 4706250` 副本中 `... -m m1_teacher.demo --write-evidence` | 三件工件哈希 `171cc654…43f1` / `5e84229e…a46b` / `23b871a3…af8ce` | 与 CI 文档一致 |
| C5 | `cd /root/at-m1-offline && ... -m m1_offline.demo`（单跑，`/tmp`；与 CI 文档 digest/行数比对） | exit 0；38 行；`sha256=2282caff40787317d8222401e2a7a0f9cdec6d9ac86d2ed8286927a0792df3cb`；stderr 0 | 与 CI 文档一致 |
| C6 | B `git archive 290c577` 副本中 `... -m m1_offline.demo --write-artifacts` 两次 | stdout 40 行、`sha256=ed9b9c16…76ed9`；trace `ed850c77…acf64` / `4019c946…4176f`；`.md` `c5d5f027…02de`；`.json` 两次不同 | 与 CI 文档一致；JSON 仅 `utc_timestamp` 不同 |
| C7 | `cd /root/m1b/pr0 && ... -m pytest tests/m1_teacher -q -k "hidden or isolation or scan or scanner or tamper or m0 or network"` | `26 passed, 510 deselected in 0.41s` | 与 CI 文档一致 |
| C8 | `cd /root/at-m1-offline && ... -m pytest tests/m1_offline/test_no_m0_import.py tests/m1_offline/test_contamination.py -q -p no:cacheprovider` | `25 passed in 1.30s` | 与 CI 文档一致 |
| C9 | `git diff --name-only 3e7afee..HEAD \| grep -E '<受保护路径>' \|\| echo NO_PROTECTED_PATH_CHANGES` | `NO_PROTECTED_PATH_CHANGES` | 无 M0/安全路径改动 |
| C10 | `bwrap --version`、`bwrap --help`、`bwrap …` 最小 canary | `bubblewrap 0.9.0`；按威胁模型原序报 `bwrap: --size must be followed by --tmpfs`（exit 1）；`--size 16777216 --tmpfs /tmp` 顺序则 exit 0、`uid=65534` | 见 P1-08；仅命令可行性，不是沙箱验收 |
| C11 | A/B 静态 grep（`scoring/`、`RuntimePort`、网络/M0 import） | A：`scoring/` 仅 2 处（`scorer.py:6,401`），`RuntimePort` 0，网络/M0 0；B：网络/M0 2 处均 docstring | 与 CI 文档一致 |

> C1 在 A worktree 运行会生成 gitignored 的 `__pycache__`/`.pytest_cache`（本 worktree 原本已有）；
> `git status --porcelain` 在本轮结束仍为空，tracked 树未变。C2/C5/C6 的 B 树全程只读（C5/C6 在 `/tmp`
> archive 副本内运行；C2 使用 `-p no:cacheprovider`，前后 `git status` 为空）。
> 文档记录的耗时（如 19.30s/21.96s）与本轮（18.10s/19.26s）不同是负载差异；耗时不是门禁。

### 1.3 未执行 / 不可核验（不得当作通过）

- **全仓 M0 套件**：`pytest tests -q`（约 335s）本轮 `NOT_RUN`（预算限制）；CI 文档记录的
  `6 failed, 1697 passed, 19 skipped` 本轮**未独立复跑**。该记录与原样失败清单不构成本文验收。
- **B1-01..B1-06 的动态安全验收**：全部 `NOT_RUN`；本轮只做静态核对 + 两条最小 bwrap 命令可行性探针。
- **LOCAL_PROBE 附录的脚本/日志 SHA-256**：`/tmp/m1b_probe` 不在本会话可见范围，`UNVERIFIABLE`；
  本文不据此判 PASS。
- **生产/CI 环境的 userns/bwrap 可用性与非 root 宿主部署**：`NOT_RUN`；威胁模型 §4.5 已自述。
- **人类批准、真实用户 CODE、真实 Provider/Key/网络、真实学习者数据**：均不在本轮范围。

---

## 2. `file:line` 声明抽查（24 条，含 21 VERIFIED / 3 STALE）

> 行号以 A `4706250`、B `290c577` 的冻结源码为准；`STALE` 指内容存在于附近但引用行号偏移，
> 不是事实相反。`WRONG`（本轮唯一一条）是 §3.6 的 bwrap 命令，不是 file:line。

| # | 文档声明 | 实际核对 | 状态 |
|---|---|---|---|
| V1 | ADR：A `SCHEMA_VERSION="m1a.v0"`（`contracts/types.py:39`） | 39 行正是该常量 | VERIFIED |
| V2 | ADR：A 8 个 phase（`types.py:90-99`）、12 个 event type（`:101-118`） | 两段起始行与值集完全一致（DIAGNOSE…PAUSED；SESSION_STARTED…ERROR） | VERIFIED |
| V3 | ADR：A `AssessmentResult` 字段（`types.py:683-701`） | 683 类声明；692 `result_id`、693 `item_id`、694 `learner_id`、695 `status`、698 `scorer_id`、700 `evidence_refs` | VERIFIED |
| V4 | ADR：A `Reason`（`:714`）、`TeachingAction`（`:730`）、`LearnerSnapshot`（`:767`）、`LearnerGoal`（`:792`）、`HistoryEvent`（`:803`） | 五个类声明行全部命中；`HistoryEvent` 的 `event_id/learner_id/session_id/seq` 在 811-814 | VERIFIED |
| V5 | ADR：A `Record.schema_version` ClassVar（`:493`）；严格 `from_dict`（`:514-553`） | 493 行 `schema_version: ClassVar[str]`；514 起 `from_dict` 明确拒绝缺失/不匹配 `schema_version`（525-532） | VERIFIED |
| V6 | ADR：A SQLite 6 表在 `learner/repository.py:90-125` | `schema_meta` 90、`learners` 93、`snapshots` 98、`history_events` 104（含 `UNIQUE(learner_id,seq)`）、`goals` 116、`sessions` 125 | VERIFIED |
| V7 | ADR：A `rebuild_snapshot`（`model.py:358`）、`verify_rebuild`（`history.py:357`）、`append_event`（`:164`）、`apply_assessment`（`:210`）、事件 id `evt.<learner>.<seq>`（`:193`） | 全部命中；`assessed_event_id` 在 109 | VERIFIED |
| V8 | ADR/CI：A `engine.py` 210（engine）、450/469（pause/resume）、488（submit）、833（全局 `_find_existing_result`）、855（eval error）、1611 行 | 全部命中；833 方法只按 `result_id` 取历史事件，确实早于 learner/session 校验 | VERIFIED（同时证实 C3/B-03 根因） |
| V9 | ADR：A scorer 191（Protocol）、199（scorer_id）、201（score）、217（Deterministic）、534/548/556-561/564/586-595/621/638 | 全部命中：556-561 把含 `tests` 的 payload 从 stdin 送子进程；564 argv 带 `result_path`；621/638 信任 `cases[].passed` | VERIFIED（同时证实 B-01 根因） |
| V10 | ADR：A `DomainAdapter`（`domain.py:24`）、`DomainRegistry`（`:61`）、`KnowledgeGraph`（`graph.py:40`）、CF adapter（`cf_binary_search.py:275`）、`domain_version`（`:573`） | 全部命中；adapter 的 `teaching_content` 未知 kind 抛 `ValidationError` | VERIFIED |
| V11 | ADR/CI：A demo `FIXED_TIMESTAMP:103`、manifest version `:106`、证据目录 `:120`、`main:1310`；CLI `cli.py:138` | 全部命中 | VERIFIED |
| V12 | ADR：B `SCHEMA_VERSION`（`types.py:35`）、6 个 evidence kind（`:43-51`）、诊断状态（`:63`）、`_fill_time`（`:251`）、只读 property（`:271-275`）、宽松 `from_dict`（`:288-296`） | 全部命中；`from_dict` 仅在 `schema_version` 存在且不等时报错，缺失被容忍（288-296） | VERIFIED |
| V13 | ADR：B `SkillNode`（`:339-344`，含 `prerequisites:343`）、`KnowledgeSource`（`:357-365`）、`KnowledgeRevision`（`:382-390`） | 全部命中；`SkillNode` 无 difficulty/assessment_mode | VERIFIED |
| V14 | ADR：B `EvidenceEvent`（`:426-435`，无 session_id）、`LearnerState`（`:454-457`）、`LearningGoal`（`:472-477`）、`AssessmentResult`（`:601-611`）、`RuntimeRequest/Response`（`:638/658`）、`TraceEvent`（`:683-690`） | 全部命中；`EvidenceEvent` 只有 task_id，无 session_id | VERIFIED |
| V15 | ADR：B `LearningMemory`（`memory.py:52/77/92/97/109`）、`LearnerModel`（`learner_model.py:56/157/198`） | 全部命中；`append`/`replay` 语义与文档一致 | VERIFIED |
| V16 | ADR：B `RuntimePort`（`runtime_port.py:52/61`）、`MockRuntimePort`（`:78`）、`simulated=True`（`:94`）；policy version（`teaching_policy.py:157/220/265`）、planner（`:45`） | 全部命中；`simulated` property 恒 True | VERIFIED |
| V17 | ADR：B `FreshnessManager`（`freshness.py:179/186/348`）、`CFJudge`（`cf/judge.py:181`）、`JUDGE_VERSION`（`:41`）、`JudgeResult.failures` 含 expected（`:150-164`，runner 122/410-412）、`_interpret` 信任 passed（`:400/414`） | 全部命中；`failures` 文本确由 `args_repr/expected_repr/actual_repr` 拼接（410），父进程在 414 以 `passed_count == total` 定 PASS | VERIFIED（同时证实 B-Q5/B1-06 泄漏面） |
| V18 | ADR：B `CFTeacher`（`cf/teacher.py:133`）、hidden_ref 解析（`:176-192`）、diagnose/next_action/assess（`:213/551/660`）、fatal detail（`:283`）、`SCORER_ID`（`:69`）、Interview rubric（`rubric.py:48`）、5 阶段（`coach.py:50-56`） | 全部命中；`DiagnosisResult.explanation` 只在 fatal 分支取 `failures[0]` | VERIFIED |
| V19 | ADR：B harness `replay_trace`（`:1187`）、digest（`:1276`）、closed loop（`:1286`）；demo 路径（`:53-55`）；report 时间戳（`:152`）、`write_report`（`:393`）；contamination 模式（`:54-56`） | 全部命中；report 152 确为 `datetime.now(...)` 写入 `utc_timestamp` | VERIFIED |
| V20 | ADR：B CF dimensions = correctness/edge_case_accuracy/efficiency（`cf/teacher.py:700-703`）；确定性 `asmt_`（`:718`） | dimensions 实际在 **723-727**，`assessment_id=_stable_id("asmt_", …)` 在 **729-731**；700 是 `total=…`，718 是 `edge_accuracy=0.0` | **STALE**（2 处行号偏移 11-23 行，内容存在） |
| V21 | ADR：`EvidenceGate` 在 `teaching_policy.py:79` | `class EvidenceGate` 实际在 **53**；79 是 `max_level` 类方法 | **STALE**（引用落在类内部，不是类声明） |
| V22 | CI：A 静态隔离测试锚点 `test_e2e_resume_idempotency.py:487`、`test_assessment_scorer.py:486/431`、`test_domain_adapter.py:780`；子集 `26 passed/510 deselected` | 四个函数声明行全部命中；C7 复跑 26/510 一致 | VERIFIED |
| V23 | CI：A 三件证据哈希、B stdout/trace/md 哈希与 40 行 | C4/C6 全部复现；B `.json` 两次哈希不同、语义仅 `utc_timestamp` 差异 | VERIFIED |
| V24 | 威胁模型：A scorer `548/556-561/564/586-595/621/638`；B `judge.py:74/122/311/410/414`、`teacher.py:283`、`harness.py:1038` | 全部命中；`result_path` 在 A 548、B 74/218/311；`failures.append` 在 B 410-412 | VERIFIED |
| X1 | 威胁模型：bwrap 冻结命令 `--tmpfs /tmp --size 16777216`（§4.2） | bwrap 0.9.0：`--size` 必须**位于** `--tmpfs` 之前；原序 exit 1 `bwrap: --size must be followed by --tmpfs`；改为 `--size 16777216 --tmpfs /tmp` 后 exit 0、uid 65534 | **WRONG**（命令不可执行；详见 P1-08） |
| X2 | 威胁模型附录 LOCAL_PROBE 的脚本/日志 SHA-256 | 探针目录不在本会话可见范围 | **UNVERIFIABLE**（不据此判 PASS） |

> 结论：24 条 file:line 声明中 21 条 VERIFIED、3 条 STALE（V20 两处 + V21），没有发现事实相反的
> 源码引用；但 **V20/V21 会误导实现者**，应在 B-PR1/PR4 前修正（P2-10）。X1 是冻结命令的事实错误，
> 单独列为 P1-08。

---

## 3. 关键判断

### 3.1 唯一 canonical TeacherCore / 事件协议 / 唯一 Mastery 写入者 / 唯一 Replay

| 判断项 | 证据 | 结论 |
|---|---|---|
| 唯一 TeacherCore | ADR §6.1；A `m1_teacher` 的 SQLite/session/Reason/知识图；B 无持久化/session/结构化 Reason（V6/V8/V4） | **方向可执行**；A 是合理 canonical |
| 唯一事件协议 | ADR §5.1/§6.1；A `history_events` 有 `seq` + `UNIQUE(learner_id,seq)`；B `EvidenceEvent` 无 seq/session（V14） | **设计成立，但未冻结到可实施粒度**：缺 B kind→A event_type 的具体映射表（P1-02） |
| 唯一 Mastery 写入者 | ADR §5.2/§8；A `MasteryModel` + `LearningHistory.apply_assessment`；`upsert_snapshot` 只应由 History 调用（V7/V6） | **规范清楚**，但 repository 写方法仍是公开 API，缺机制性 gate（P2-01）；另有 mastery 导入例外（P1-05） |
| 唯一 Replay | ADR §5.3/§8；A `verify_rebuild` + `rebuild_snapshot`；B trace 仅 sidecar | **可执行**；需在 B-PR5 明确 canonical replay 只接受 A 事件表，B trace 仅哈希证据 |
| 禁止双写 | ADR §6.1/§7.5/§8；PORTS §1 T3“不可写 canonical” | **明确**；建议 B-PR2 用端口/构造注入做结构性阻断，而不是只靠文档禁令 |

**判定**：canonical 裁决本身可执行、方向正确；真正阻塞“冻结”的是事件映射表、adapter 的 seq/checksum、
以及冻结记录的 optional-field 后门（P1-02/03/04）。这些是文档/接口层修复，不需要推翻 A canonical。

### 3.2 禁止双写 / 禁止自动迁移真实 DB

- ADR §7.5 明确列了五条硬门：真实 DB 自动迁移禁止、A/B 双写禁止、双跑禁止、迁移工具禁止联网/Provider/Key、
  输出只允许脱敏 synthetic 证据。PORTS §1 的 T0..T4 又把 vertical 定义为不可写 canonical 的纯函数层；
  §5 再次声明只允许 synthetic fixture/脱敏副本。**这两条要求是明确的，且与 handoff B0 第 3 点一致。**
- **例外/弱化点**：
  1. ADR §4.5 “若维护者未来授权单向导入” + §7.2 `map_mastery_state` 的“维护者批准的一次性 offline 导入例外”，
     允许把 B 的 `mastery: dict[str,float]` 直接变成 A 的 `MasteryEstimate`（confidence/evidence_count 缺省）。
     这会制造**无法由事件重放**的 snapshot，`verify_rebuild` 不可能通过，也绕开“唯一写入者 = 证据驱动”；
     列为 **P1-05**。
  2. ADR Q8 问“迁移工具是否允许接触真实 learner DB（仅维护者离线、备份后）”。B0 的要求是“禁止自动迁移”，
     手工、离线、备份后的迁移不必然违规；但必须在签收时把“手工例外”的条件写成可审计的 runbook，
     否则 Q8 会被误读为允许对真实 DB 直接跑 adapter。建议：在 Q8 答案中明确“默认禁止；任何真实 DB 操作
     必须人类批准 + 备份 + 只读副本演练 + 回滚演练”，并把它排除出 B-PR4/5 的自动验收。

**判定**：双写/自动迁移禁令合格；mastery 导入例外必须关闭或改写为“导入证据后由 A 重算”（P1-05）。

### 3.3 v1 compatibility adapter（additive / 拒绝不可表达 / checksum / rollback）

| 要素 | 设计现状 | 判定 |
|---|---|---|
| additive only | ADR §7.1 新增模块；PORTS §6.2 明确不改 `m1_teacher/contracts/**`、`m1_offline/types.py` | **部分合格**：ADR §7.1 又允许“TeacherCore 记录新增带默认值的可选字段”，与 `m1a.v0` 冻结、A 严格 `from_dict`、`to_dict` 全字段输出、证据 digest 冲突（P1-04） |
| 可拒绝不可表达字段 | ADR §7.2 每个 map 函数有 `MIGRATION_*` 拒绝码；PORTS §5.1 定义 lossless/lossy/unsupported，严格模式整批中止 | **方向合格**，但同一字段在不同表里既 `MAP` 默认填充又 `UNSUPPORTED_FIELD`（tags/content_ref；dimensions 既 sidecar 又 unsupported）——需统一（P2-08） |
| 迁移 checksum | ADR §7.3 / PORTS §5.3-5.4：canonical JSON + `source_sha256`/`migrated_sha256`/`manifest_checksum` | **不闭合**：bundle 的排序/分隔/包含哪些记录未定义；`map_evidence_event` 在 seq/id 生成前返回 `HistoryEvent`，`migrated_sha256` 无法在写库前复算（P1-03）；`created_at` 注入时间会改变 digest（P2-07） |
| rollback | ADR §7.4 六条：schema version、`verify_rebuild`、checksum 复算、重复 migration key、id/session 冲突、备份还原 | **可执行**；但第 3 条依赖未定义的 bundle checksum；第 2 条只有在 P1-05 关闭后才可信 |
| 不自动迁移真实 DB | ADR §7.5；PORTS §5 | **合格**（见 §3.2 的 Q8 备注） |

**判定**：adapter 设计方向正确、拒绝码齐全；但“可校验/可回滚”目前只有格式，没有可独立复算的输入定义，
**不能作为 B0 的完成证据**，必须补 P1-03/P1-04/P2-07/P2-08。

### 3.4 四端口覆盖与 Judge 可信边界

| 能力 | 端口落点 | 覆盖判断 | 与 Judge 边界的冲突/缺口 |
|---|---|---|---|
| CF Hint（LIGHT→INVARIANT→STRUCTURE→FULL） | `TeacherPolicyPort`（§3.4 映射表）+ `DomainAdapterV1.hint_ladders` | 覆盖；默认 LIGHT、FULL 被 `hint_level_cap=3` 阻塞 | FULL 内容放在 teacher-visible `VerticalAssets`，只靠“默认不可发出”约束，导出/日志仍可能带全文（P2-09） |
| CF Judge | `AssessmentPort`（§3.2）+ T1/T2 分层 | 覆盖；worker 只拿单 case 输入，expected 留 T1 | `trusted_fixture_test_only` 在 `AssessmentJob` 请求里，由调用方提供（P1-01）；`item_digest` 也由调用方算（P2-02） |
| Interview 5 阶段追问 | `TeacherPolicyPort` + `follow_up_ladders` | 覆盖；`SOCRATIC_QUESTION` 映射到 HINT，阶段写在 `Reason.code` 字符串 | 阶段不是结构化字段（P2-09 同类）；`ASK_CLARIFICATION→DIAGNOSE` 仍开放（Q6） |
| Interview rubric | `AssessmentPort`（`response_kind=TEXT`） | **部分覆盖**：只能输出 `AssessmentResult` 五态/聚合，4 维 rubric 无 canonical 载体 | **P1-07**；`dimensions` 被 ADR 判为不可表达，B4 的“4 维独立”无法进入统一事件/Replay |
| Freshness KEEP/UPDATE/RECHECK | `KnowledgeSourcePort` + `knowledge_claims` | 覆盖分类规则与 `curriculum_eligible` | `untrusted/trust_tier/claim_status` 由 claim 自报（P1-06）；决策如何写入 canonical 计划/事件未定义（P2-03） |

**信任边界核对**：

- **domain 不得读隐藏答案**：`DomainAdapterV1.assessment_items()` 返回 v0 `AssessmentItem`（无 answer 字段），
  hidden spec 只在 `AssessmentPort` T1；文字设计正确。**但** A `AssessmentItem.scoring_spec_ref` 在
  teacher-visible 记录里携带 `scoring/item...json` 路径（`types.py:678`，fixtures 实际值；adapter 在
  `cf_binary_search.py:535-537` 读取），CI 的“仅 scorer 引用 scoring/”只是源码 grep，不是运行时导出扫描。
  这是**路径**而非 expected 内容，列为 **P2-13**；B1-06 的运行时扫描应覆盖 item payload。
- **worker 不得拿 expected**：威胁模型 §3.2 禁止字段、§3.3 响应无 verdict/passed、§4.2 只挂
  `/usr /lib /lib64 /bin /worker /tmp /proc /dev`，方向正确；**但** bwrap 命令本身有 P1-08，
  且 `--clearenv` 未固定 `PYTHONHASHSEED`（P2-11），在修复前不能把“沙箱可用”当作既定事实。
- **teacher-visible 输出**：PORTS §4 权责矩阵与威胁模型 §8 一致（只聚合 code/count），设计合格；
  实现验收仍必须做运行时 sentinel 扫描，不能只看 AST（威胁模型 §8.3 已明确）。

**判定**：四端口覆盖 CF/Interview/Freshness 的“教学动作/证据/知识”三条主线，但 Interview rubric 的
4 维结果与 Freshness 决策的 canonical 落点缺失；与 Judge 可信边界存在两个 caller-controlled 字段
（P1-01/P1-06），必须在 B-PR1/PR4 前修。

### 3.5 CI 文档数字纪律与冻结命令

- **数字纪律**：CI §6 与 ADR §10 都明确“536/365 各自冻结、不可相加、不存在统一 901”；CI §5 把全仓
  M0 的 `6 failed, 1697 passed, 19 skipped` 原样记录，并声明“不是本线验收、不得写成全仓全绿”。
  `TEST_EVIDENCE_MATRIX.csv` 的 B0-01/B1-01..06 均 `NOT_RUN`；三份文档没有自称 DONE/PASS。**合格。**
- **冻结命令可执行性**：C1/C2 两条主命令本轮均复跑成功；C3-C8 的 demo/工件/子集也与文档一致；
  C9 受保护路径无改动；C11 静态 grep 与文档一致。**合格。**
- **可复现性缺口**：
  1. 命令块只写工作目录，不写 `git rev-parse HEAD` 断言；worktree 漂移时“冻结命令”会在另一棵树上静默运行
     （P2-04）。建议在 CI 脚本首行 `test "$(git rev-parse HEAD)" = "<sha>"`，并在前后 `git status --porcelain`。
  2. A 线 `-q` 未带 `-p no:cacheprovider`/`PYTHONDONTWRITEBYTECODE=1`；虽然 A worktree 可写且缓存被 gitignore，
     但“只读证明”只在 B 线成立（P2-04 同类，文档已说明 A 可写，故不单列）。
  3. 全仓 M0 的 6 failed 未由本轮复跑（`NOT_RUN`）；文档的“与 Lead 早前实测一致”不能替代独立复跑。
     这不是文档错误，但报告引用时必须保留 `NOT_RUN` 标签。

**判定**：CI 文档的数字纪律与命令冻结**通过静态预审**；需要补 SHA 断言与运行时 hidden-path 扫描（P2-04/P2-13）。

### 3.6 威胁模型静态评审要点

| 检查点 | 结论 | 证据/备注 |
|---|---|---|
| request 不含 expected/tests/scoring 路径 | **满足** | §3.2 唯一字段 `schema_version/request_id/function_name/args/timeout_ms/stdout_limit/stderr_limit`；禁止字段明确列出 expected/tests/hidden/result_path 等；附录 B 示例无这些字段 |
| response 无 verdict/passed | **满足** | §3.3 仅 `status/actual_canonical/exception_type/stdout_excerpt/stderr_excerpt`；禁止 `passed/verdict/score/correct/expected`；§3.5 只由 T1 比较 |
| 默认 `UNTRUSTED_CODE_EXECUTION_BLOCKED` | **满足** | §5.1 默认对所有对外/开放路径；§3.5 blocked 不写 mastery；§9 B1-01 映射 |
| 沙箱不可用绝不回退裸子进程 | **满足（文字）** | §4.4“禁止的降级”明确“绝不回退到裸 subprocess.run”“绝不跳过 isolation”；需在 B-PR1 用 fake bwrap 失败路径测试 |
| B1-01..06 映射完备 | **满足** | §9 六行逐项对应矩阵 B1-01..06，当前均 `NOT_RUN`；B1-01 是真实用户 CODE 的 BLOCKER 写明 |
| LOCAL_PROBE 只算设计可行性 | **满足** | §0/§13/附录 A.5 多处声明“不是 PR1 验收”；本文不据此判 PASS |
| bwrap 规格可执行 | **不满足** | §4.2 的 `--tmpfs /tmp --size 16777216` 被 bwrap 0.9.0 拒绝（C10）；应为 `--size 16777216 --tmpfs /tmp`（P1-08） |
| 协议自洽 | **部分** | `request_id` 正则 `^[a-f0-9]{16,64}$` 与示例 `req_...` 冲突（P2-05）；§3.1 stdout 与 §4.3 fd3 分工需冻结（P2-06）；解释器 3.12 vs 仓库 3.11.15、无 `PYTHONHASHSEED`（P2-11） |

**判定**：威胁模型的**安全设计方向与 B1 映射合格**，可以作为 B-PR1 动工输入；但冻结命令有一个事实错误
（P1-08），协议有三处需在实现前锁死的细节（P2-05/06/11）。**它不是 B1 验收，也不改变 B1-01..06 = NOT_RUN。**

---

## 4. Findings

### 4.1 P0（0 项）

**无。** 依据：(a) 三份文档没有把历史 `536/365` 相加或冒充新 PASS，也没有把 B1/B0 写成已完成；
(b) canonical 裁决、双写/自动迁移禁令、四端口名称与信任分层没有出现“必须推翻”的矛盾；
(c) 两条冻结命令与 demo/工件均可复跑。当前问题是**接口/协议/可复算性缺口**，均可在文档或对应 PR 关闭，
不构成“停止 B-PR0”的 P0。

### 4.2 P1（8 项，必须在对应 PR 动工前关闭）

| ID | 证据 | 影响 | 要求动作 | 验收方式 |
|---|---|---|---|---|
| **P1-01** `trusted_fixture_test_only` 由调用方提供 | PORTS §3.2 把该 bool 放进 `AssessmentJob`（`:191`）；威胁模型 §5.1/§10.1 要求只能由 supervisor 内部显式 opt-in、不可由请求体/learner 文本开启 | 外部 caller 可在 job 里传 `true`，绕过 B1-01 的默认 BLOCKED 与“仅仓库内部 synthetic fixture”门槛（即使仍在沙箱内，也绕过人类 gate） | 从 `AssessmentJob` 删除该字段；改成 `AssessmentPort` 构造参数/不可序列化的能力位；外部请求一律 `UNTRUSTED_CODE_EXECUTION_BLOCKED`。若必须保留字段，则 supervisor 只接受服务端派生的 capability，忽略/拒绝客户端值 | B-PR1 负例：外部 job 伪造 `trusted_fixture_test_only=true` → blocked、不 spawn worker、mastery 不变；request schema/JSON 中该字段不存在或恒 false；grep 0 |
| **P1-02** 缺 B→A 事件类型映射表 | ADR §4.3 写“映射表见 §5.1”（`:147`），但 §5.1（`:244`）只有 6 vs 12 的集合对比与“不能一一对应”；没有 6 个 kind 到 event_type/payload 的逐项表 | B-PR4/PR5 无法确定 `ANSWER/CODE_SUBMISSION/EXPLANATION/INTERVIEW_RESPONSE/ASSESSMENT/HINT_REQUEST` 各落到哪个 A 事件；`MIGRATION_UNSUPPORTED_EVENT_KIND` 没有可判定的边界，事件协议事实上未冻结 | 在 ADR §5.1 增加 6 行映射：B kind → A `event_type`（可能一对多/仅 sidecar）+ 必填 payload 键 + session 绑定规则；不可映射的 kind 明确 `REJECT` 而非 `MAP` | 映射表覆盖 6/6；单测每个 kind（含不可映射负例）；B-PR4 评审按表逐项核对；`MIGRATION_UNSUPPORTED_EVENT_KIND` 有触发样例 |
| **P1-03** adapter 在 seq/id 生成前返回 `HistoryEvent`，checksum 不可复算 | ADR §7.2 `map_evidence_event(...) -> tuple[HistoryEvent, ...]`（`:384`）声明“由 canonical history 生成 id/seq”；但 A `HistoryEvent` 必填 `event_id/seq`（V4），且 §7.3 要在迁移时算 `migrated_sha256`（`:404-405`） | adapter 只能(a)自己造 id/seq（违反唯一写入者），或(b)返回不合法 `HistoryEvent`；迁移前无法计算 `migrated_sha256`，rollback 第 3 条不可验证 | 改为 staging DTO（如 `m1b.migration.evidence.v0`：`source_event_id/learner_id/session_binding/source_order/payload`），由 canonical history 按固定规则分配 id/seq；先对 staging 算 `source_sha256`，写库后对最终事件集算 `migrated_sha256` 并记录分配规则 | 同一 fixture 两次迁移得到同一 `migrated_sha256`；迁移后 `verify_rebuild=true`；staging 不含 `HistoryEvent` 必填字段缺失；负例：重复 source_order → 拒绝 |
| **P1-04** “给冻结记录加可选字段”的后门 | ADR §7.1 允许“TeacherCore 记录新增带默认值的可选字段 + 版本记录”（`:367-368`），但 §6.1 说 `m1a.v0` 冻结、既有字段不删不改（`:287-288`）；PORTS §2.1 说 v0 记录“原样复用，不新增/删除字段”（`:59-61`） | A `Record.to_dict()` 输出所有字段（V5），新增可选字段会改变所有记录 canonical JSON 与证据 digest；严格 `from_dict` 的未知字段/版本语义也被破坏。实现者会以为可以在 v0 上加字段 | 删除该例外：所有扩展放 `m1b.*` 新记录/端口或 sidecar；若确实需要字段，定义 `m1a.v1` 新记录 + 显式迁移，不修改 `m1a.v0`；在 §6.6 冻结条件中写明“v0 类型零 diff” | `git diff` 对 `m1_teacher/contracts/types.py` 为 0；A 历史证据哈希回归不变；ADR 全文无“optional field on v0”表述；B-PR2/4 评审检查 |
| **P1-05** mastery 导入例外会制造不可重建状态 | ADR §4.5 允许维护者授权时把 B `mastery` 直接导入并缺省 confidence/evidence_count（`:169`）；§7.2 `map_mastery_state` 默认拒绝但留“一次性 offline 导入例外”（`:387`）；A 的 mastery 只接受 OBSERVED 证据并靠事件重建（V7） | 导入的 float mastery 没有对应证据事件，`rebuild_snapshot`/`verify_rebuild` 不可能复现；违反“唯一 Mastery 写入者/证据驱动”，可虚增掌握度；rollback 也无法证明 | 对 canonical DB **永久拒绝**直接 mastery 导入；若需要 B 的掌握信息，只能导入其底层 `EvidenceEvent` 并由 A `MasteryModel` 重算；把 `verify_rebuild=true` 设为迁移后硬门 | 负例：直接 float mastery → `MIGRATION_LEARNER_STATE_DENIED`；证据重算用例：迁移后 snapshot 与重放一致；无任何 API 可写 `upsert_snapshot` 绕过 History |
| **P1-06** KnowledgeClaim 的信任字段自报 | PORTS §3.3 `KnowledgeClaim` 把 `untrusted`、`trust_tier`、`claim_status`、`confidence` 放进 claim（`:246-261`）；`curriculum_eligible` 只对“UPDATE+VERIFIED+权威 tier”为 true（`:271`）；但 T4 来源可构造 claim 自报 `untrusted=false`/`VERIFIED`/`official_document` | 不可信文档可自我升级为权威来源，触发 `curriculum_eligible=true`，污染课程候选；违反“untrusted 内容不得改指令”与 B4“绝不静默导入冲突/过期来源” | 信任字段必须由可信 ingestion/source registry 按 `source_id/uri` allow-list 赋值，claim 正文不得设置；`untrusted` 由 provenance 派生；对自报权威但不在 registry 的 source → `RECHECK`/拒绝；记录 provenance digest | B-PR4 负例：伪造 official/VERIFIED 的未知 source → `curriculum_eligible=false`；registry 外 source 全部 `RECHECK`；decision JSON 不含原文 |
| **P1-07** Interview 4 维 rubric 无 canonical 载体 | PORTS §3.2 输出仅 v0 `AssessmentResult` 五态/聚合（`:198-201`）；ADR §4.4 判 `dimensions` 不可映射（`:161`）；handoff B4 要求“4 维 rubric 独立” | B-PR4 无法把 rubric 的 4 维结果写入统一事件/Replay；要么丢失维度，要么塞进 payload 无 schema/无审计；B4 验收无落点 | 定义 `m1b.ports.v0` 的可信 `AssessmentAudit`/`RubricResult`（维度键、权重、rubric_version、aggregate），明确是否影响 mastery（建议仅审计、不直接写 mastery），并指定持久化位置（A `HistoryEvent.payload` 或 sidecar + digest） | B-PR4 测试：Interview rubric 输出 4 维、roundtrip/严格 from_dict、canonical 事件 payload 引用 audit digest；负例：无 rubric_version/维度缺失 → 拒绝 |
| **P1-08** bwrap 冻结命令 `--size` 位置错误 | 威胁模型 §4.2（`:304`）`--tmpfs /tmp --size 16777216`；bwrap 0.9.0 `--help`/man：“`--size` ... must be followed by `--tmpfs`”；C10 原序 exit 1，改为 `--size 16777216 --tmpfs /tmp` 后 exit 0、uid 65534 | 冻结的 OS 规格**按原文不可启动**；若实现者删掉 `--size` 保启动，`/tmp` 失去 16MiB 上限，B1-04 的 FSIZE/资源隔离出现缺口 | 修正为 `--size 16777216 --tmpfs /tmp`；在 B-PR1 canary 中断言 `/tmp` 为受限 tmpfs（写入超限失败/df 值）；把命令纳入可执行测试而非文档片段 | B-PR1 CI：命令 exit 0；`/tmp` 大小断言；learner 写入超 16MiB → 失败/受限；无 `--size` 的旧命令被测试拒绝 |

### 4.3 P2（13 项，应在冻结/对应 PR 前修）

| ID | 证据 | 影响 | 要求动作 | 验收方式 |
|---|---|---|---|---|
| **P2-01** 唯一写入者仅是规范，缺机制 gate | ADR §8 写“其他组件只读、禁止直接 `upsert_snapshot`”（`:463`）；但 `SqliteRepository.upsert_snapshot`（`learner/repository.py:493`）与 `append_event` 仍是公开方法；PORTS §4 权责矩阵是文档约束 | 内部模块/未来 vertical 可绕过 History 直接写 snapshot/event，唯一写入者无法用测试证明 | B-PR2 把 `commit_teaching_turn` 设为唯一写 API；repository 写方法改为私有/需 writer token；端口/vertical 不注入 repository；负例测试 | 负例：从 vertical/诊断/planner 调用 `upsert_snapshot` 不可达或抛错；事件/snapshot 只能经 commit；代码评审 + 测试 |
| **P2-02** `item_digest` 由调用方计算 | PORTS §3.2 `item_digest` 是 job 字段（`:190`） | 调用方可传入与 trusted item 不一致的 digest，使“防篡改/防学科漂移”失效；T1 若直接信任该值，会评错题 | 明确 T1 必须从自身 item 重算 `item_digest` 并拒绝不匹配；job 中的值只作提示/日志 | B-PR1 负例：篡改 digest → `PORT_INPUT_INVALID`/`JUDGE_INFRA_ERROR`；正常 item 通过 |
| **P2-03** Freshness 决策无 canonical 审计落点 | PORTS §3.3 说 decision 不写状态、由 planner 显式采用（`:289`）；A 的 12 事件类型无“knowledge adopted”事件（V2） | “JD version 变更影响课程”无法在统一事件表/Replay 中审计；冲突/过期来源是否被采用只能靠外部日志 | 定义 `PLAN_CREATED.payload.knowledge_decision`（decision_id/claim_id/change_kind/curriculum_eligible/reason）或 sidecar digest；规定 planner 采用/拒绝时的必填字段 | B-PR4 测试：UPDATE 被采用、RECHECK 被拒均有事件 payload；Replay 后 decision 可复现；无 hidden 内容 |
| **P2-04** 冻结命令未 pin SHA / 未断言工作树 | CI §2.1/§3.1 命令只 `cd`（`:37-40`、`:109-113`）；文档写基线但命令不校验 | worktree 漂移时“冻结命令”在另一棵树运行，结果不可归因；复现证据失效 | 命令块首行加 `test "$(git rev-parse HEAD)" = "<期望 SHA>"`，前后 `git status --porcelain`；CI 脚本输出版本 | 命令在错误 SHA 上 fail fast；正确 SHA 输出 `536/365`；前后 status 空 |
| **P2-05** `request_id` 正则与示例冲突 | 威胁模型 §3.2 正则 `^[a-f0-9]{16,64}$`（`:229`），但示例为 `req_7c1f0b9a2d4e6f80`（`:217`），附录 B 也是 `req_...`（`:639`） | 严格实现按正则会拒绝文档自带示例；实现者可能放宽校验，削弱 request_id 防串 | 二选一：正则改为 `^req_[a-f0-9]{16,64}$`，或示例去掉 `req_` 前缀；request/response 示例同步 | B-PR1 schema 测试接受所有文档示例；非法 id 拒绝；示例与正则一致 |
| **P2-06** 协议通道 stdout vs fd3 表述不一致 | 威胁模型 §3.1 说“stdin 请求、stdout 读单行”（`:208`）；§4.3 说先 dup 到 fd3、再把 1/2 重定向（`:327`） | 按 §3.1 实现时 learner `print` 可写 stdout 伪响应；按 §4.3 实现时又需额外 fd 传递；协议冻结不唯一 | 冻结为“响应只走专用 fd（如 fd3），stdout/stderr 仅 excerpt”；写明 supervisor `pass_fds`/worker dup 步骤；§3.1 同步 | B-PR1 测试：learner 打印 `{"passed":true}` 不进协议；伪 fd3 写入被 schema 拒绝；正常响应只读 fd3 |
| **P2-07** 迁移 canonical JSON 含注入时间，digest 不稳定 | ADR §4.12 缺失 `created_at` 用 manifest 迁移时间（`:233`）；§7.3 digest 用 `to_dict()`（`:402`）；PORTS §5.3 要求时间显式注入（`:433`） | 同一 fixture 在不同时间迁移会得到不同 `migrated_sha256`，与“可复算/可回滚”矛盾；若固定时间又需明确规则 | 规定迁移时间固定为 manifest `created_at` 并纳入 digest，或从 digest 排除 `created_at/updated_at`；在 manifest 记录规则 | 两次独立迁移（不同 wall clock）→ `migrated_sha256` 相同；文档示例复算一致 |
| **P2-08** 同一字段的迁移动作自相矛盾 | ADR §4.2 tags/content_ref 是 `MAP`+默认空（`:136`），§7.2 又把 `:tags`/`:content_ref` 列为 `UNSUPPORTED_FIELD`（`:382`）；§4.4 dimensions 说“保留 payload”+`UNSUPPORTED_FIELD:dimensions`（`:161`），§7.3 说 unsupported 非空即整批中止（`:435`） | 实现者无法判定 tags/content_ref/dimensions 是 lossy sidecar 还是拒绝；严格模式下可能整批失败，或静默丢字段 | 统一判定表：可 sidecar 保留的字段归 `lossy`（显式 action），不可表达且影响教学语义的归 `unsupported`；tags 可 lossy 默认空，content_ref/difficulty/assessment_mode 拒绝；dimensions 明确 sidecar/lossy | 每个字段只有一个判定；严格/宽松模式负例符合 §7.3；manifest 的 `unsupported`/`lossy` 计数可复算 |
| **P2-09** FULL hint 全文在 teacher-visible assets | PORTS §3.1 `hint_ladders` 明确含 `FULL`（`:133`），仅“默认不可发出”；§4 说 assets teacher-visible（`:377`） | 即使 policy cap=3，FULL 文本仍可能被导出/日志/UI 读取，等于把完整答案放在 teacher-visible 数据面；与“默认不泄完整答案”目标有差距 | 把 FULL 放受限资产（不进入 `VerticalAssets` 默认导出），或标记 `restricted` 并从 trace/JSON/UI 导出中剔除；只允许 `FULL_EXPLICIT` 路径按引用取用 | B-PR4 测试：默认导出/诊断/trace 不含 FULL 文本；显式批准路径可取且记录 Reason；sentinel 扫描 0 |
| **P2-10** 行号 STALE / 历史缩写不一致 | ADR `cf/teacher.py:700-703` 的 dimensions 实际 723-727（V20）；`:718` 的 `asmt_` 实际 729-731；`teaching_policy.py:79` 的 `EvidenceGate` 实际 53（V21）。另：CI §2.2 的历史简写 `…091b` 与实际后缀 `…d491b` 不一致（同页完整 hash 正确） | 实现者按行号定位会读错代码，评审引用不可复核；不影响事实结论但降低文档可信度 | 修正为准确行号/函数名；对全文档做一次 `file:line` lint（至少覆盖 §4/§5/§11） | 抽查 10 条随机引用命中；CI 可选加链接检查；B-PR0 复审 |
| **P2-11** worker 解释器/哈希种子未固定 | 威胁模型 §4.2 用 `/usr/bin/python3`（`:294` 记录 3.12.3），仓库/venv 是 3.11.15；`--clearenv`（`:301`）未设 `PYTHONHASHSEED` | 同一 learner 代码在 set/dict 迭代上可能产生不同 `actual_canonical`；跨解释器 canonical JSON/浮点表示差异会造成非确定性 WA/PASS，违反 I6 | 在 bwrap 命令/worker env 固定 `PYTHONHASHSEED=0`、`PYTHONDONTWRITEBYTECODE=1`，并 pin worker Python 版本；把版本写入 scorer_id/protocol | B-PR1 测试：同一输入两次 actual 逐字节相同；set 迭代样例稳定；scorer_id 含解释器版本 |
| **P2-12** 两份 migration manifest schema 不一致 | ADR §7.3 `counts` 为 `{skills,edges,goals,assessment_results,evidence_events}`（`:418`）；PORTS §5.4 `counts` 为 `{records,lossless,lossy,unsupported}`（`:447`），但两者都叫 `m1b.migration.v0` | 同一 manifest 版本有两种不兼容字段；工具/rollback 无法统一解析，checksum 复算口径不同 | 合并为一个 schema（保留两组计数或分版本），在 ADR/PORTS 二选一引用；给出示例 JSON + 解析测试 | 同一 manifest 被两侧解析器接受；字段缺失/多余按版本拒绝；checksum 复算一致 |
| **P2-13** A teacher-visible item 携带 `scoring/` 路径 | A `AssessmentItem.scoring_spec_ref`（`types.py:678`）由 adapter 从 fixture 读入（`cf_binary_search.py:535-537`），实际值为 `scoring/item...json`；CI §4.1 的“仅 2 处源码引用”只是 grep（`:194-199`） | hidden scoring 的**路径**（非 expected 内容）出现在 teacher-visible 记录/可能导出；B1-06 若只做源码扫描会漏掉；与威胁模型 §8.1“禁止 scoring 路径”不一致 | 把 `scoring_spec_ref` 限制在 T1（teacher-visible 导出前剥除/替换为不透明 id），或在 B1-06 运行时扫描中覆盖 item payload 并声明“路径非机密但不得导出”；补测试 | B-PR1 运行时导出扫描覆盖 `AssessmentItem`；teacher-visible JSON 0 个 `scoring/`；T1 仍能按 ref 读取 spec |

---

## 5. 必须修复动作清单（给 LeadB / 维护者）

**A. B0 签收前（文档层，建议本轮修订）**

1. **P1-04**：删除 ADR §7.1 的“给 v0 加可选字段”例外，改为“v0 零 diff；扩展只在新 `m1b.*` 记录/端口”。
2. **P1-05**：把 mastery 导入例外改为“只导入证据并由 A `MasteryModel` 重算”；`verify_rebuild` 作为硬门。
3. **P1-02**：在 ADR §5.1 补 6→A event_type 的逐项映射表（或明确 REJECT + sidecar）。
4. **P1-03**：把 `map_evidence_event` 改为 staging DTO + 确定性 id/seq 分配规则；定义 checksum bundle。
5. **P1-06**：把 KnowledgeClaim 的 trust 字段改为可信 registry 派生。
6. **P1-07**：定义 Interview rubric 的 `AssessmentAudit`/sidecar schema 与持久化位置。
7. **P2-08/P2-12**：统一 migration 判定表与 manifest schema；修正 P2-10 的行号。

**B. B-PR1 动工前（安全/OS，必须）**

1. **P1-01**：从 `AssessmentJob` 删除/禁用 `trusted_fixture_test_only`，改为内部 capability。
2. **P1-08**：修正 bwrap `--size` 顺序并加入 canary；命令必须 exit 0。
3. **P2-05/P2-06/P2-11**：冻结 request_id 正则、协议 fd、worker 解释器/`PYTHONHASHSEED`。
4. **P2-13**：把 `AssessmentItem.scoring_spec_ref` 的运行时导出纳入 B1-06 扫描/剥除。
5. 上述关闭前，B1-01..06 保持 `NOT_RUN`，不得以“命令跑通”替代安全验收。

**C. B-PR4/PR5 前**

- 逐项关闭 P2-02/P2-03/P2-09，并在 B-PR4 评审中按 P1-02/P1-06/P1-07 的验收表核对。
- B-PR5 只使用端口做两域 E2E/Replay；不得把 B `LearnerModel`/`TraceEvent` 当 canonical。
- 历史 536/365 仍分开引用；新 suite 单独计数、独立 Reviewer。

**D. 不阻塞本预审结论的事项**

- 三份文档可以按当前内容进入 B-PR0 文档合并/评审记录；但上述 P1 必须在对应 PR 的实现/验收前关闭。
- 全仓 M0 的 6 failed 仍归 M0/A 线处理，不由 M1-B 修复或掩盖。

---

## 6. 复跑命令（供复核；本轮已执行，输出见 §1.2）

```bash
# A suite（期望 536 passed；A worktree 可写，缓存 gitignored）
cd /root/m1b/pr0
"/root/Autonomous Teacher/.venv/bin/python" -m pytest tests/m1_teacher -q

# B suite（冻结只读；期望 365 passed；前后 git status 为空）
cd /root/at-m1-offline
git status --porcelain
"/root/Autonomous Teacher/.venv/bin/python" -m pytest tests/m1_offline -q -p no:cacheprovider

# A demo（期望 exit 0、53 行、sha256 b08ceee9…d491b）
cd /root/m1b/pr0
"/root/Autonomous Teacher/.venv/bin/python" -m m1_teacher.demo > /tmp/m1b_a_demo_check.txt
sha256sum /tmp/m1b_a_demo_check.txt && wc -l /tmp/m1b_a_demo_check.txt

# B demo（期望 exit 0、38 行、sha256 2282caff…df3cb）
cd /root/at-m1-offline
env PYTHONDONTWRITEBYTECODE=1 "/root/Autonomous Teacher/.venv/bin/python" -m m1_offline.demo \
  > /tmp/m1b_b_demo_check.txt
sha256sum /tmp/m1b_b_demo_check.txt && wc -l /tmp/m1b_b_demo_check.txt
```

> 以上输出是**命令冻结输出**，不是 B0/B1 验收 PASS。复跑时间会因负载不同；计数与 digest 才是门禁。
> 全仓 M0 命令（`pytest tests -q`）本轮 `NOT_RUN`；引用 CI §5 时必须原样保留 `6 failed / 1697 passed /
> 19 skipped`，并注明不是 M1-B 子集。

---

## 7. 声明、证据分级与遗留

1. **这不是集成 PASS**：本文只做了 B-PR0 三份设计文档的静态预审 + 两条冻结命令/若干只读命令的复跑；
   **B-PR1..B-PR5 均未验收**；**B0-01 仍应视为 `NOT_RUN`**；B1-01..06 仍 `NOT_RUN`。
2. **历史数字**：A `536 passed`、B `365 passed` 是各自分支的冻结参考；`536 + 365 = 901` 不是任何真实套件，
   本文不把它当新验收，也不把任一历史 PASS 跨线继承。
3. **全仓 M0**：CI 文档记录的 `6 failed, 1697 passed, 19 skipped` 本轮**未独立复跑**（`NOT_RUN`）；
   该记录不改变 M0/A 线的失败归属，也不被本文当作 M1-B 回归。
4. **LOCAL_PROBE**：威胁模型附录的探针只证明“本机设计可行性”；脚本/日志 SHA-256 在本会话
   `UNVERIFIABLE`；不据此声称 B1-04/B1-05 通过。bwrap canary 只验证了命令可启动与 uid，不验证完整隔离。
5. **无敏感内容**：本文不含 hidden expected、真实学习者数据、Key、Provider 凭据；引用的源码行仅用于
   合同核对；未复制任何 hidden fixture 内容。
6. **只读性**：本轮对 `/root/m1b/pr0` 仅新增本文件；`git status --porcelain` 最终只显示
   `docs/M1_B_BOUNDARY_PRE_REVIEW.md`（以及被 gitignore 的缓存，若存在）。审查期间的 `7fcbcfe` merge
   由外部执行（threat-model 分支并入），不是本 Reviewer 的提交；对 `/root/at-m1-offline`
   的 pytest/demo 运行前后 `git status --porcelain` 均为空（C2/C5/C6 使用 archive 副本或只读参数）。
7. **Reviewer 独立性**：本预审未参与三份文档或威胁模型的撰写；未修改任何源码/测试/fixture；
   结论只基于本轮 SOURCE_INSPECTED + 实际命令输出。

### 7.1 证据分级汇总

| 等级 | 本文中的使用 |
|---|---|
| `SOURCE_INSPECTED` | 三份文档、威胁模型、A/B 源码的 `file:line` 核对；§2 的 24 条声明 |
| `INDEPENDENTLY_REEXECUTED_THIS_TURN` | C1-C11（仅本轮真实执行；输出见 §1.2） |
| `NOT_RUN` | 全仓 M0 套件、B1-01..06 动态验收、生产 userns/bwrap、人类批准、B-PR1..5 |
| `UNVERIFIABLE` | LOCAL_PROBE 脚本/日志哈希；Lead 的另测耗时；目标部署环境 |

### 7.2 本预审未覆盖

- B-PR1 的实际 worker 协议实现、沙箱逃逸测试、运行时 sentinel 扫描；
- B-PR2 的事务/崩溃矩阵与 `SIGKILL` 故障注入；
- B-PR3 的 composite idempotency 负例；
- B-PR4 的 CF/Interview/Freshness 真实适配与教学策略校准；
- B-PR5 的两域 E2E/盲评/新 suite、报告；
- M0/A 线安全与 LiveGate 的任何改动。

---

## 8. 版本与变更记录

| 日期（UTC） | 版本 | 变更 |
|---|---|---|
| 2026-11-20 | v1.0 | B-PR0 独立静态预审：24 条 file:line 抽查（21 VERIFIED / 3 STALE）、canonical/双写/adapter/端口/CI/威胁模型判断、8 P1 + 13 P2、命令复跑与 NOT_RUN 声明 |

**结论重申：`PRE_REVIEW_PASS_WITH_ACTIONS`；P0=0，P1=8，P2=13；B0-01 仍 `NOT_RUN`，B-PR1..5 未验收。**
