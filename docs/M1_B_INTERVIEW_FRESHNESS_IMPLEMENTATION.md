# M1-B B-PR4 — Interview / Freshness Vertical 实现说明

- **状态**：`IMPLEMENTED (vertical additive layer)`。本轮只实现 **additive vertical 数据层与端口**；engine/session 的多轮五阶段接入、B4 E2E 依赖 PR3 合并后再做。
- **分支 / 工作区**：`b-next/pr4-interview-freshness`，`/root/m1b/pr4`；基线 `work/m1a-mvp = 4706250`，先 merge 了设计分支 `b-next/pr4-interview-mapping`（`2b8f3c3`，含 `docs/M1_B_INTERVIEW_FRESHNESS_MAPPING.md`）。
- **设计依据**：`docs/M1_B_INTERVIEW_FRESHNESS_MAPPING.md`（移植映射、端口、拒绝码、PR4 测试矩阵草案）。
- **本轮不做**：不修改 `session/engine.py`、`learner/**`、`assessment/scorer.py`、`contracts/**` 的冻结语义；不碰 M0；无网络/真实简历/JD/Provider/Live。engine 五阶段会话集成与 B4-01/02/03 E2E 仍 **NOT_RUN**（见 §8）。

## 1. 交付范围

### 1.1 新增 fixtures（canonical `m1a.v0` 可消费；全部 synthetic / CC0-1.0）

来源：B 线冻结交付 `work/m1-offline-design = 290c577` 的 `fixtures/m1/interview/**`，一次性离线转换为静态 JSON（生成脚本不提交；转换结果即提交物）。

```
fixtures/m1_teacher/vertical/
├── interview/
│   ├── questions.json                 # teacher-visible：4 节点 / 4 软依赖边 / 4 目标 / 4 节点教学内容
│   │                                  # + 22 道题（prompt、难度、5 阶段追问提示、requires_project_facts）
│   ├── jds.json                       # 8 个 JD 版本（rec/ml/sys 各 v1+v2，+ 1 组合成重叠冲突演示）
│   ├── knowledge_sources.json         # 18 个知识版本（9 组 old/new），带时间戳语义/claim_status/来源层/内容指纹
│   ├── rubrics/scoring/               # scorer-only 隐藏材料：22 份 rubric 规格 + reference_answers.json
│   └── untrusted/injection_docs.json  # 4 条 DATA_ONLY 注入文档（仅测试数据，adapter 不加载）
└── freshness/
    └── scenarios.json                 # 9 条 KEEP/UPDATE/RECHECK + 7 条 JD window 场景 + 1 条 JD change 场景
```

关键转换约束：

- **teacher-visible 与 hidden 严格分离**：`questions.json` 只含题面/难度/技能节点/5 阶段追问提示；四维 rubric 期望、四维分数权重、隐藏答案全部只在 `rubrics/scoring/`。Teacher adapter 的 allow-list 只有 `questions.json`，测试物理移除 `rubrics/` 后 adapter 行为完全一致。
- **时间语义显式**：每个 knowledge 版本独立保留 `published_at`（来源发布时间）、`observed_at`（观测时间）、`valid_until`；时间戳统一 `...Z` 秒级；版本 ID 采用 `source_id::observed_at`（fixtures 不含 URL scheme / `@` / 真实身份形状，符合仓库 fixture 政策）。
- **内容指纹 v0 限制**：`content_hash = sha256(uri, publisher, published_at, claim_status)`（`KnowledgeSource` 无正文字段；设计文档已披露）。KEEP 场景两版本指纹相同；UPDATE 不同。
- **JD 语义**：JD 只是岗位要求版本上下文；`valid_from/valid_until` 是有效期窗口而**不是** `published_at`；v2 通过 `supersedes` 链接 v1 并携带确定性 `delta`；JD 不产生题目热度、不写 mastery。
- **注入文档**：4 条（指令覆盖/提权/伪权威/数据投毒），标记 `DATA_ONLY`，仅作为不可信测试数据；teacher-visible 文件从不引用。

fixtures 全树 JSON sha256（排序后整体）：`060e621ae81ca5bada2c8a09e0f6803529cd11b4fb4b011f04e049f346ade58f`。

### 1.2 新增模块（additive；未修改冻结合同）

| 模块 | 行数 | 职责 |
|---|---|---|
| `m1_teacher/domains/interview.py` | 716 | `InterviewDomainAdapter`：实现冻结 `DomainAdapter`（`knowledge_nodes/prerequisite_edges/objectives/assessment_items/teaching_content/validate`）；只读、无 learner/session 写入、不读隐藏目录；additive helpers：`follow_up_ladder(item_id)`（5 阶段 teacher-visible 追问）、`requires_project_facts(item_id)`、`question_metadata(item_id)`、`build_interview_registry()`、`default_fixtures_root()`。 |
| `m1_teacher/knowledge/freshness.py` | 1253 | `KnowledgeFreshnessService`：结构化满足 `m1_teacher.extensions.KnowledgeFreshnessPort`（`classify(request)`），并提供 `classify_pair`、`curriculum_eligible`、`recheck_required`、`require_curriculum_eligible`、`active_jd`、`jd_change_impact`、`classify_all_scenarios`、`decisions_checksum`。KEEP/UPDATE/RECHECK + EXPIRED/CONFLICT/UNAUTHORITATIVE/FUTURE-DATED 全门禁，fail-closed 使用设计文档 MAP-E07/E08/E09/E10 码。 |
| `m1_teacher/assessment/interview_judge.py` | 723 | `InterviewRubricJudge`（**本 vertical 唯一隐藏 rubric 读取者**，scorer-side）：确定性四维评分（factual/clarity/feasibility/evidence，独立特征集）；开放题最多 `PARTIAL`；无法判定 → `NEEDS_REVIEW`；隐藏规格故障 → `EVAL_ERROR`（不当作学习者证据）；四维分数与 failure modes 放在 assessment-port sidecar `InterviewAssessmentDetail`，冻结 `AssessmentResult` 不新增字段。 |

边界（test-enforced）：

- Teacher 侧模块（domains/interview.py、knowledge/freshness.py）源码不引用隐藏评分路径；`m1_teacher/domains` + `knowledge` + `contracts` 现有静态扫描仍通过。
- 仅 `scorer.py` 与新 `interview_judge.py` 在显式封闭 allow-list 内可引用隐藏评分路径（见 §7 适配说明）。
- 所有模块无网络/无 M0 import、无 wall-clock 判定（评测使用固定 fixture 时钟/显式 `now`）、无 runtime/provider 调用。
- 未修改 `m1_teacher/__init__.py` / `domains/__init__.py`：避免与 PR2/PR3 并行改动冲突；调用方以显式模块路径 import，如需默认 registry 注册由后续 PR 统一加（additive）导出。

## 2. 与设计文档的对应（DESIGN → 实现）

| 设计项 | 实现落点 | 状态 |
|---|---|---|
| Interview 问题 → `KnowledgeNode`/`AssessmentItem` | `domains/interview.py` + `questions.json` | ✅ 实现（22 items / 4 nodes；teacher-visible） |
| 4 维 rubric/隐藏答案 → scorer-only + `AssessmentResult` | `assessment/interview_judge.py` + `rubrics/scoring/` | ✅ 实现；dimensions 用 sidecar（设计 Q2 保守方案） |
| 5 阶段追问 | `follow_up_ladder()` additive 方法（不扩展 DomainAdapter 协议） | ✅ 数据/接口实现；engine 会话接入 NOT_RUN |
| `requires_project_facts` 边界 | `questions.json` 字段 + adapter helper；judge 缺事实 → `NEEDS_REVIEW:PROJECT_FACTS_REQUIRED` | ✅ vertical 层实现（教练发 `ASK_CLARIFICATION` 的会话动作在 PR3 后接入） |
| `KnowledgeSource` 时间语义/claim_status | `knowledge_sources.json` + `KnowledgeFreshnessService` | ✅ 实现 |
| KEEP/UPDATE/RECHECK + 课程门禁 | `classify_pair` / `curriculum_eligible` / `require_curriculum_eligible` | ✅ 实现；RECHECK 全部不可进入课程 |
| JD v1→v2 仅影响新计划 | `active_jd` / `jd_change_impact` | ✅ 实现（窗口有效/过期/未生效/重叠冲突） |
| MAP-E 拒绝/门禁码 | 服务 fail-closed 分支（MAP-E07/08/09/10） | ✅ 实现 |
| 统一 Session/事件/Replay | — | ⛔ 本轮不做（engine/PR3 依赖） |
| B4-01/02/03 E2E | — | ⛔ NOT_RUN（本轮只做 vertical/数据层） |

## 3. 验证命令与真实输出（本轮实际运行）

环境：`/root/Autonomous Teacher/.venv/bin/python`（Python 3.11.15 / pytest 9.2.0）；工作区 `/root/m1b/pr4`。

### 3.1 本轮新增测试（4 个文件，60 tests）

```bash
cd /root/m1b/pr4 && "/root/Autonomous Teacher/.venv/bin/python" -m pytest \
  tests/m1_teacher/test_interview_domain.py \
  tests/m1_teacher/test_freshness_service.py \
  tests/m1_teacher/test_interview_fixtures.py \
  tests/m1_teacher/test_interview_judge.py -q
```

真实输出：

```text
............................................................             [100%]
60 passed in 0.22s
```

逐文件：`test_interview_domain.py` 14 / `test_freshness_service.py` 22 / `test_interview_fixtures.py` 10 / `test_interview_judge.py` 14。

### 3.2 现有 536 测试回归 + 新增合计

```bash
cd /root/m1b/pr4 && "/root/Autonomous Teacher/.venv/bin/python" -m pytest tests/m1_teacher -q
```

真实输出：

```text
596 passed in 14.58s
```

（改动前基线实测：`536 passed in 16.66s`；本轮 536 + 60 = 596，无现有测试语义被破坏，见 §7 的显式适配。）

### 3.3 静态检查

```bash
"/root/Autonomous Teacher/.venv/bin/ruff" check \
  m1_teacher/domains/interview.py m1_teacher/knowledge/freshness.py \
  m1_teacher/assessment/interview_judge.py \
  tests/m1_teacher/test_interview_domain.py tests/m1_teacher/test_freshness_service.py \
  tests/m1_teacher/test_interview_fixtures.py tests/m1_teacher/test_interview_judge.py
```

真实输出：`All checks passed!`；`python -m compileall` 通过。

## 4. 测试覆盖摘要（本轮实际覆盖）

- **DomainAdapter 合法性**：协议实例化、4 节点/4 边/4 目标/22 items、difficulty/item_type/assessment_mode、确定性序列化（固定 fixture 时间戳）、按节点过滤、未知节点/kind fail-closed、目标经 `KnowledgeGraph.validate_objective`。
- **teacher-visible 无隐藏材料**：序列化扫描、物理移除 `rubrics/` 后 adapter 行为一致、adapter allow-list 仅 `questions.json`、corrupt fixture（schema/未知键/ladder 乱序）fail-closed。
- **5 阶段追问**：恰好 5 阶段、固定顺序 concept→hypothesis→complexity→experiment_design→online_triage、每阶段 teacher-visible prompt、错误 id fail-closed。
- **4 维 rubric 独立**：clarity/evidence/factual/feasibility 单轴扰动，只移动对应维度；misconception 只扣 factual；确定性（同输入同 result_id/score）。
- **开放题保守**：完美长回答仍 `PARTIAL`（不会 `CORRECT`）；过短 → `NEEDS_REVIEW`；缺项目事实 → `NEEDS_REVIEW:PROJECT_FACTS_REQUIRED`；低事实覆盖 → `INCORRECT`。
- **EVAL_ERROR**：损坏/缺失 hidden spec → `EVAL_ERROR`、`score=None`、无 sidecar、无隐藏内容；非法 item/response fail-closed。
- **hidden 不泄漏**：AssessmentResult + sidecar JSON 不含 rubric 期望 token/参考回答/隐藏目录路径；failure_reason 只允许状态码前缀。
- **freshness 三态/门禁**：9 条知识场景全部按 expected 分类；KEEP 指纹相同；UPDATE 仅 VERIFIED+权威层；EXPIRED/CONFLICT/UNAUTHORITATIVE/FUTURE-DATED/OLDER 全部 RECHECK；`require_curriculum_eligible` 对非 eligible 抛 `FRESHNESS_CURRICULUM_BLOCKED`（带 MAP-E code）。
- **published_at vs observed_at**：notes 显式记录两条时间线与 lag/delta；`detected_at == observed_at` 且不同于 published_at。
- **JD 门禁**：v1→v2 生效窗口、过期、未生效、重叠冲突；JD change 仅影响新计划（`affects_running_sessions=False`），delta 与 fixture 一致，supersedes 链非法 → `FRESHNESS_JD_CHAIN_INVALID`。
- **确定性/离线**：freshness decisions checksum 两次实例一致；服务/评测器无网络或 M0 import、无 learner writer 方法、无 wall-clock 依赖。
- **fixtures**：schema/version/CC0/synthetic、ID 唯一、时间戳/哈希格式、JD delta 重算、knowledge content_hash 重算、无 URL scheme/@/email/真实数据形状、JSON round-trip。

## 5. Provenance / 许可

- 上游：B 线 `work/m1-offline-design = 290c577`（Interview/Freshness 合成 fixtures）；A 线 canonical：`work/m1a-mvp = 4706250`。
- 所有题目/JD/知识/答案/注入文档为自编 synthetic、CC0-1.0；无真实公司、真实人名、真实个人简历/招聘数据。
- 知识时效为**静态带时间戳**数据，只证明 KEEP/UPDATE/RECHECK 门禁与审计机制，不声称真实外部热点已更新，也不含网络刷新调度。
- 证据等级：本文件引用的 pytest 输出为 `DETERMINISTIC`（离线可复跑）；fixtures 为 `MOCK`（合成数据）；无 `HUMAN_REVIEWED` 结论；真实教学效果保持 `NOT_VERIFIED`。

## 6. 已知限制

1. **开放题评分是确定性关键词/结构 rubric**：最多 `PARTIAL`，不是语义评分；阈值未用人类评分校准，标 `UNCALIBRATED_HEURISTIC`；不能声称学习效果。
2. **隐藏材料读取边界**：`interview_judge.py` 是新增 scorer-side 读取者；仍只有显式 allow-list 内两个 scorer 模块可引用隐藏路径（见 §7）。
3. **知识内容指纹 v0**：无正文哈希，仅元数据指纹；正文级变更有赖上游 digest（设计文档已披露）。
4. **freshness 协议 `classify(request)` 信息不全**：单次观测无 digest，故 fail-closed 返回 RECHECK；完整分类使用 `classify_pair`。真实抓取/调度器不存在。
5. **人工复核队列只实现门禁语义**：`require_curriculum_eligible` 阻断 + decisions 审计；持久化 review queue/审批 UI 未实现。
6. **JD 只覆盖 synthetic 窗口**：窗口边界按日期包含式判断；真实 JD/招聘站点不接入。
7. **engine 未接入**：多轮五阶段、LearnerState 影响的追问策略、`ASK_CLARIFICATION` 会话动作、统一事件/Replay 均待 PR3 合并后实现。
8. **hidden 题集（B 线 hidden/）本轮未转换**：只转换公开 22 题与隐藏评分规格；隐藏题集访问控制/评测留待 E2E 阶段。
9. 未修改包 `__init__` 导出；`build_interview_registry()` 可构造单域 registry，默认 `build_default_registry()` 的多域注册留给后续 additive PR。

## 7. 对现有测试的显式适配（需 Reviewer 知悉）

PR4 新增了第二个独立 **scorer-side** 模块（`assessment/interview_judge.py`），而 B-PR1 的两条静态隔离守卫测试硬编码“只有 `scorer.py` 可以引用隐藏评分路径”。为避免弱化审计，本轮**没有隐藏路径字符串**，而是把守卫改为**显式封闭 allow-list**：

- `tests/m1_teacher/test_assessment_scorer.py::test_only_scorer_module_references_hidden_scoring_path`
- `tests/m1_teacher/test_e2e_resume_idempotency.py::test_teacher_code_references_hidden_scoring_only_in_scorer`

改动：新增 `_HIDDEN_SCORING_READERS = frozenset({"scorer.py", "interview_judge.py"})`，判定从 `path.name != "scorer.py"` 改为 `path.name not in _HIDDEN_SCORING_READERS`。**任何第三个模块引用隐藏路径仍会失败**；teacher 侧 `domains/knowledge/contracts` 的原始守卫（`test_domain_adapter.py`）未修改且通过。除此之外没有修改任何现有测试（其余 534 条保持原样通过）。

## 8. 仍 NOT_RUN（本轮不声称完成）

| 项 | 状态 | 说明 |
|---|---|---|
| B4-01 统一 CF 闭环（2 learners） | `NOT_RUN` | vertical 层已备好数据/端口；E2E 待 engine/PR3 |
| B4-02 Interview 闭环（2 learners/JD v1→v2 会话） | `NOT_RUN` | 多轮五阶段/`ASK_CLARIFICATION` 会话接入未实现 |
| B4-03 Freshness 进入教学闭环 E2E | `NOT_RUN` | service 门禁已实现，Planner/Engine 接线待后续 PR |
| 统一 Session/事件表/Replay | `NOT_RUN` | PR3 合并后 |
| hidden 题集访问控制/E2E 评测 | `NOT_RUN` | 本轮只转换公开 22 题与隐藏评分规格 |
| 真实 Provider/网络/真实简历/JD/Live | `BLOCKED` | 项目边界明确禁止 |
| 依赖 B1/B2/B3 的开放 CODE 判题/事务/幂等 | 未变 | 属前置 PR，本轮不改 |

## 9. 复现

```bash
cd /root/m1b/pr4
"/root/Autonomous Teacher/.venv/bin/python" -m pytest \
  tests/m1_teacher/test_interview_domain.py \
  tests/m1_teacher/test_freshness_service.py \
  tests/m1_teacher/test_interview_fixtures.py \
  tests/m1_teacher/test_interview_judge.py -q      # 60 passed
"/root/Autonomous Teacher/.venv/bin/python" -m pytest tests/m1_teacher -q   # 596 passed
"/root/Autonomous Teacher/.venv/bin/ruff" check m1_teacher/domains/interview.py \
  m1_teacher/knowledge/freshness.py m1_teacher/assessment/interview_judge.py  # All checks passed!
```

---

*本文件只说明本轮已实现/已实测的 vertical 层；未运行项一律标 `NOT_RUN`，引用历史测试数字不构成新验收结论。*
