# M1-B B-PR0 独立预审响应（Review Response）

| 字段 | 值 |
|---|---|
| 文档状态 | **DRAFT / DESIGN_ONLY**（修订响应；等待复审与维护者签收；**未实现、未集成、未验证**） |
| 被审对象 | `docs/M1_B_CONVERGENCE_ADR.md`、`docs/M1_B_PORTS.md`、`docs/M1_B_CI_AND_DEMO.md`（初版） |
| 评审报告 | `docs/M1_B_BOUNDARY_PRE_REVIEW.md`（独立 Reviewer；**本响应不修改/不删除它**；Reviewer 已以 `1a74530` commit，与本响应共存） |
| 评审结论 | `PRE_REVIEW_PASS_WITH_ACTIONS`：**P0 = 0，P1 = 8，P2 = 13** |
| 被审 HEAD | Reviewer 预审报告记录的 `7fcbcfe`（B-PR0 文档 commit `7e3bb60` + B-PR1 threat model `f0affa2`/merge）；当前分支 HEAD 已含 Reviewer 报告 commit `1a74530` |
| 本响应范围 | 仅文档修订（ADR / PORTS / CI）；**不改源码/测试/fixture/其它实现**；不改 Reviewer 报告；不改威胁模型（P1-08 已转办 b-cf） |
| 证据类别 | `SOURCE_INSPECTED`（阅读 Reviewer 报告与冻结源码）＋ `DESIGN_ONLY`（修订后的设计条款）；**本文不产生新验收 PASS** |
| 命令证据 | 本文引用 Reviewer 报告 §1.2 的 C1–C11 为其本人 `INDEPENDENTLY_REEXECUTED_THIS_TURN` 记录；本轮 B0 修订**未重新跑**这些命令，也不把它们写成新 PASS |
| 状态口径 | P1/P2 的“DOC_FIXED”仅表示**文档层已修订**；实现/验收关闭仍需对应 PR 的测试与 Reviewer（见 §3）。`TEST_EVIDENCE_MATRIX.csv` 的 B0-01 仍为 `NOT_RUN` |

---

## 0. 处置摘要

| 类别 | 数量 | 处置结果 |
|---|---|---|
| **P1**（必须在对应 PR 动工前关闭） | 8 | **7 项 DOC_FIXED**（P1-01..P1-07，均修订 ADR/PORTS 并给出验收项）；**1 项 TRANSFERRED**（P1-08 → b-cf 的 B-PR1 分支修 bwrap 命令顺序；本文与 Reviewer 文件均不改威胁模型） |
| **P2**（冻结/对应 PR 前修） | 13 | **8 项 DOC_FIXED**（P2-01/02/04/07/08/09/10/12）；**1 项 DESIGN_ADDED**（P2-03，canonical 审计落点写入 PORTS，B-PR4 实现）；**3 项 TRANSFERRED**（P2-05/P2-06/P2-11 → b-cf 威胁模型/B-PR1）；**1 项 PARTIAL + 运行时待验收**（P2-13：设计约束/CI 清单已加，运行时扫描仍 `NOT_RUN`，归 B-PR1/B1-06） |
| P0 | 0 | 无。 |

**仍未关闭（不得视为完成）**

1. **P1-01..P1-07 的实现验收**：本响应只完成文档/接口层修订；对应测试（B-PR1 的 negative capability、B-PR2 写 gate、
   B-PR4 事件映射/信任 registry/rubric sidecar/迁移 checksum）**仍 `NOT_RUN`**。
2. **P1-08**：转办 b-cf（B-PR1 分支）；其 bwrap 命令 must exit 0 + canary 仍需 B-PR1 实测。
3. **P2-05/P2-06/P2-11**：威胁模型文档内容（b-cf 维护）；本响应在 PORTS §3.2 记录“协议一致性冻结要求”作为转办依据。
4. **P2-13**：A `AssessmentItem.scoring_spec_ref` 的运行时导出扫描/投影更新仍归 B-PR1（B1-06）与后续实现；当前仅列入 CI 冻结验收清单（`NOT_RUN`）。
5. **B0-01 与 B1-01..06**：维持 `NOT_RUN`；本预审本身不是集成 PASS，本响应更不是。

---

## 1. P1 逐条处置

| ID | Reviewer 要求（摘要） | 处置 | 修订位置 | 状态 |
|---|---|---|---|---|
| P1-01 | `trusted_fixture_test_only` 不能由请求/调用方自报；外部默认 blocked | 从 `AssessmentJob` schema **删除**该字段；能力只来自 `AssessmentPort` 在 T1 构造时注入的可信部署/构造配置（不可序列化、不可由 learner/caller 设置）；若 job 出现该字段 → 严格 schema 拒绝；明确负例测试（伪造 → blocked、不 spawn worker、mastery 不变） | PORTS §3.2（Job 表 + P1-01 修订说明）；ADR §4.11（Scorer identity 行）、§8.2（导出投影段） | **DOC_FIXED**；实现验收 B-PR1 |
| P1-02 | 补 B `EvidenceEvent.kind` → A `event_type` 逐项映射（6→12，含 payload/拒绝码） | 新增 ADR §5.1.1：E1–E6 六行映射表（ANSWER/CODE_SUBMISSION/EXPLANATION/INTERVIEW_RESPONSE → `RESPONSE_SUBMITTED`；ASSESSMENT → `ASSESSED`+`MASTERY_UPDATED` 一对二；HINT_REQUEST → `ACTION_TAKEN`），每行给出前置条件、payload 必填键、mastery 影响、拒绝码；明确不可映射/未来 kind → `MIGRATION_UNSUPPORTED_EVENT_KIND`（REJECT，非 MAP）；与 b-interview 映射文档 §7.2/§3.9 对齐 | ADR §5.1.1；PORTS §5.2 M3（staging 指向该表） | **DOC_FIXED**；实现验收 B-PR4/PR5（逐 kind 单测） |
| P1-03 | adapter 不得在 seq/id 生成前返回 `HistoryEvent`；定义 bundle 序列化与 checksum 计算顺序，写库前可复算 | 将 `map_evidence_event` 改为返回 **`m1b.migration.evidence.v0` staging DTO**（不含 event_id/seq）；ADR §7.3.1–§7.3.5 定义 canonical JSON、四类 bundle（source/staging/migrated/manifest）排序键、确定性 id/seq 分配规则、写前投影/写后回读、manifest 单一 schema；`migrated_sha256` 由 projected bundle 在写库前计算；rollback 增加回读相等硬门 | ADR §7.2（map_evidence_event 行）、§7.3.1–7.3.5、§7.4；PORTS §5.2 M3、§5.3 | **DOC_FIXED**；实现验收 B-PR4/PR5 |
| P1-04 | 移除“给冻结记录加可选字段”的后门；改 additive 模块/端口/sidecar | 删除 ADR §7.1 的可选字段例外，明确 **v0 类型零 diff**：不允许给 `m1a.v0` 记录/枚举/协议新增任何字段（含带默认值字段）；扩展只允许新 `m1b.*` 记录/端口/sidecar，或显式 `m1a.v1` 记录+迁移（非 B-PR0 范围）；写入 §6.6 冻结条件 | ADR §7.1、§6.6；PORTS §2.1、§6.2 | **DOC_FIXED**；评审：`m1_teacher/contracts/**` diff 必须为 0 |
| P1-05 | 删除 mastery 直接导入例外；只能导入证据后由 A `MasteryModel` 重算 | ADR §4.5 改为**永久拒绝**直接 mastery/state 导入（无“维护者批准例外”）；§7.2 M6 标记“永久禁用”；§7.4 把 `verify_rebuild=true` 设为迁移后硬门；Q8 明确直接 mastery 导入永久拒绝 | ADR §4.5、§7.2（map_mastery_state 行）、§7.4、§12 Q8；PORTS §5.2 M6 | **DOC_FIXED**；实现验收 B-PR2/B-PR4（负例 + 重算一致性） |
| P1-06 | `KnowledgeClaim` 的 `untrusted/trust_tier/claim_status` 不得自报，改由可信 registry/配置持有 | PORTS §3.3 将三类字段从 claim schema 移除（标 ~~删除线~~），新增 **`KnowledgeTrustProfile`（可信 registry 记录，不随 claim 传输）**：`registry_version/source_patterns/trust_tier/untrusted_default/allowed_claim_statuses/max_confidence/may_update_curriculum`；`KnowledgeSourcePort` 构造时注入可信 registry；registry 外来源 → `RECHECK` + `curriculum_eligible=false`；claim 伪造信任字段 → `PORT_UNTRUSTED_INPUT_REJECTED`/`MAP-E07`；`KnowledgeDecision` 增加派生字段 `derived_trust_tier/untrusted/registry_version/provenance_digest` | PORTS §3.3（claim/registry/decision/规则/错误码）；ADR §4.9；PORTS §5.2 M9 | **DOC_FIXED**；实现验收 B-PR4 |
| P1-07 | Interview 4 维 rubric 缺 canonical 载体；冻结 sidecar schema 并与 b-interview 映射 §4 对齐 | 新增 PORTS §3.2.1 **`RubricResult`/`AssessmentAudit`（`m1b.ports.v0`）**：`scorer_id/rubric_id/rubric_version/dimensions{4 键+weight+rationale_code}/aggregate_score/passed_threshold(0.65)/failure_modes/evidence_refs/created_at`；持久化位置 = `ASSESSED.payload.assessment_audit` + `assessment_audit_digest`；审计-only、不直接写 mastery；引用 `/root/m1b/ivmap/docs/M1_B_INTERVIEW_FRESHNESS_MAPPING.md` §3.3/§4.3 与其 `MAP-E**` 码（E05/E13/E16/E21/E22/E23 等）；ADR §4.4 结果语义行同步 | PORTS §3.2.1；ADR §4.4 | **DOC_FIXED**；实现验收 B-PR4 |
| P1-08 | bwrap 冻结命令 `--size` 必须在 `--tmpfs` 之前；B-PR1 canary 断言 | **TRANSFERRED**：按 Lead 指令由 b-cf 在 B-PR1 分支修 `docs/M1_B_THREAT_MODEL_JUDGE.md`（本响应对应 Reviewer 文件与威胁模型均**未修改**；本文件不复制/持有该命令，避免出现第二份“冻结规格”）。转办验收：B-PR1 命令 exit 0、`/tmp` 16MiB 受限断言、旧序命令被测试拒绝 | 转办位置：B-PR1 / `docs/M1_B_THREAT_MODEL_JUDGE.md`（b-cf 分支）；本响应 §3 记录 | **TRANSFERRED**（b-cf；待 B-PR1 关闭） |

### 1.1 P1-03 checksum 闭合链（本响应核心修订摘要）

```
staging DTO（无 event_id/seq）
  → source_sha256 = sha256_hex(source_bundle, sorted)
  → deterministic projection（seq=base+order；event_id=evt.<learner>.<seq>；created_at=源显式值）
  → migrated_sha256 = sha256_hex(projected_migrated_bundle)      # 写库前可复算
  → manifest（counts/unsupported/lossy/checksums） → manifest_checksum
  → BEGIN IMMEDIATE 写库 → 回读复算 == migrated_sha256 → verify_rebuild 硬门
```

规则细节与拒绝码（`MIGRATION_MISSING_TIMESTAMP`、`MIGRATION_DUPLICATE_SOURCE_ORDER`、
`MAP-E21_MIGRATION_CHECKSUM_MISMATCH`、`MAP-E15/E18`）见 ADR §7.3/§7.4 与 PORTS §5.3。

### 1.2 P1-02 映射表要点（供 B-PR4 直接实现）

- **只有 E5 `ASSESSMENT`** 产生 mastery 证据（ASSESSED + MASTERY_UPDATED 一对二，相邻 seq，同事务）；
- E1–E4（ANSWER/CODE_SUBMISSION/EXPLANATION/INTERVIEW_RESPONSE）→ `RESPONSE_SUBMITTED`，
  仅审计、不更新 mastery；E6 `HINT_REQUEST` → `ACTION_TAKEN`（`event_role=LEARNER_HINT_REQUEST`）；
- 所有映射需显式 session 绑定（缺失 → `MIGRATION_MISSING_SESSION`）；B `event_id` 只写入
  `payload.source_event_id`，A `event_id/seq` 只能由 canonical `LearningHistory` 产生；
- 不得伪造 `SESSION_STARTED/PLAN_CREATED/DIAGNOSIS_COMPLETED/ITEM_PRESENTED/GOAL_COMPLETED` 等运行期事件。

### 1.3 P1-06 信任 registry 要点

- claim 只含内容/时间/摘要（含 advisory `confidence`，由 `max_confidence` 截断）；
- `trust_tier/untrusted/claim_status` 由可信 `KnowledgeSourceRegistry`（部署/构造配置）按 `(source_id, uri)`
  allow-list 派生；未登记来源 → `RECHECK` 且不可更新课程；claim 自报这些字段 → schema 拒绝；
- decision 输出派生字段 + `provenance_digest`，供审计与 planner 门禁。

### 1.4 P1-07 rubric sidecar 要点

- 4 维固定键与默认权重 `0.35/0.20/0.20/0.25`（`Σweight==1`，1e-9 容差），`rubric_version` 必需；
- 只由 trusted scorer 产生；审计-only；持久化 `ASSESSED.payload.assessment_audit` + digest；
- 不给冻结 `AssessmentResult` 加字段（与 P1-04 一致）。

---

## 2. P2 逐条处置

| ID | Reviewer 要求（摘要） | 处置 | 修订位置 | 状态 |
|---|---|---|---|---|
| P2-01 | 唯一写入者需机制 gate，而非仅文档 | ADR §8.1：B-PR2 提供唯一写入口 `commit_teaching_turn`；repository 写方法私有/`WriteAuthority` 令牌；端口/vertical 不注入 repository；绕过 → `MAP-E20`/`MAP-E25`（安全事件 STOP）+ 负例测试。PORTS §4 同步 | ADR §8.1；PORTS §4 | **DOC_FIXED**（机制实现 B-PR2） |
| P2-02 | `item_digest` 由调用方计算不可信 | PORTS §3.2：T1 必须用自身 trusted item **重算并比对**，job 值仅日志/提示；不匹配 → `PORT_INPUT_INVALID`/`JUDGE_INFRA_ERROR`；B-PR1 负例 | PORTS §3.2（item_digest 行）；ADR §8.2 同域约束 | **DOC_FIXED**（实现 B-PR1） |
| P2-03 | Freshness 决策无 canonical 审计落点 | PORTS §3.3 增加 **canonical 审计落点**：`PLAN_CREATED.payload.knowledge_decision{decision_id,claim_id,change_kind,curriculum_eligible,reason,registry_version,decision_digest}`（或 sidecar digest），planner 采用/拒绝都必须写入；Replay 可重建 | PORTS §3.3 规则；ADR §9 B-PR4 行 | **DESIGN_ADDED**（实现/验收 B-PR4） |
| P2-04 | 冻结命令未 pin SHA/未断言工作树 | CI §2.1：新增 A 实现树零 diff 断言（`git diff --name-only 4706250 -- m1_teacher tests/m1_teacher fixtures/m1_teacher docs/m1a_evidence` 为空）+ 前后 `git status --porcelain`；CI §3.1：`test "$(git rev-parse HEAD)" = "290c577…"` + 前后只读断言 | CI §2.1/§3.1 | **DOC_FIXED**（CI 脚本采纳待实施） |
| P2-05 | `request_id` 正则与示例冲突 | **TRANSFERRED** b-cf：威胁模型文档内容（本响应不改 Reviewer/威胁模型文件）；PORTS §3.2 增加“协议一致性冻结要求”作为转办依据（正则与示例一致、schema 测试接受文档示例） | PORTS §3.2 协议一致性段；转办 B-PR1/b-cf | **TRANSFERRED**（b-cf） |
| P2-06 | stdout vs fd3 通道表述不一致 | **TRANSFERRED** b-cf（同 P2-05）；PORTS §3.2 记录冻结要求：response 只走专用 fd（如 fd3），stdout/stderr 仅 excerpt | PORTS §3.2 协议一致性段；转办 B-PR1/b-cf | **TRANSFERRED**（b-cf） |
| P2-07 | 迁移 canonical JSON 含注入时间，digest 不稳 | ADR §7.3.3 规则 5：A 记录时间戳 = 源记录显式值；源缺失 → `MIGRATION_MISSING_TIMESTAMP`（拒绝，不注入墙钟）；manifest `created_at` 是操作者固定配置，只进 `manifest_checksum`，不进 `migrated_sha256`；PORTS §5.3 同步 | ADR §7.3.3/§7.3.4；PORTS §5.3 | **DOC_FIXED** |
| P2-08 | 同字段迁移动作自相矛盾 | 统一判定：`tags` → LOSSY（默认[]+记录）；`content_ref`/`difficulty`/`assessment_mode` → REJECT（仅维护者批准显式映射时按 LOSSY）；`dimensions`/`hidden_cases_*`/`failure_modes` → LOSSY sidecar（不允许时 `MAP-E07`），不再标 `MIGRATION_UNSUPPORTED_FIELD:dimensions` | ADR §4.2/§4.4/§7.2；PORTS §5.2 M1/M4 | **DOC_FIXED** |
| P2-09 | FULL hint 全文在 teacher-visible assets | PORTS §3.1：`hint_ladders` 仅保留 `LIGHT/INVARIANT/STRUCTURE`；新增 `restricted_full_solution_refs`（仅不透明引用，不含全文）；§3.4 明确 FULL 不得进入默认导出，仅显式人类批准路径可凭引用取用（`MAP-E11`） | PORTS §3.1/§3.4；ADR §4.9/§9 | **DOC_FIXED**（实现/验收 B-PR4） |
| P2-10 | 3 处行号 STALE / 历史缩写不一致 | 修正 ADR `cf/teacher.py:723-727`（dimensions）、`:729-731`（`asmt_`）；PORTS `EvidenceGate` 改为“类 `teaching_policy.py:53`；`max_level` `:79`”；CI §2.2 历史缩写 `…091b` → `…d491b` | ADR §4.1/§4.4；PORTS §3.4；CI §2.2 | **DOC_FIXED** |
| P2-11 | worker 解释器/哈希种子未固定 | **TRANSFERRED** b-cf（威胁模型 §4.2/§4.3）；PORTS §3.2 记录冻结要求：`PYTHONHASHSEED=0`、`PYTHONDONTWRITEBYTECODE=1`、pin worker Python 版本并写入 scorer_id/protocol | PORTS §3.2 协议一致性段；转办 B-PR1/b-cf | **TRANSFERRED**（b-cf） |
| P2-12 | 两份 manifest schema 不一致 | 统一为 **ADR §7.3.5 单一权威 schema**：`counts.records`（按 record type）+ `lossless/lossy/unsupported`；旧两套 `counts` 字段删除；PORTS §5.4 改为指针，不再定义第二套 | ADR §7.3.5；PORTS §5.4 | **DOC_FIXED** |
| P2-13 | A teacher-visible item 携带 `scoring/` 路径；B1-06 需运行时扫描 | 设计约束已加：ADR §8.2 + PORTS §4（导出/UI/trace 前替换为不透明 `spec_ref_id` 或剥除；T1 从 trusted item 解析，不从导出 JSON 读）；CI §4.1 增加“运行时导出扫描（item payload/事件 JSON/诊断/demo 输出）”冻结验收项，明确当前 `NOT_RUN`、不得用 grep 替代 | ADR §8.2；PORTS §4；CI §4.1（P2-13 段）与 §8 I-7 | **PARTIAL / DOC_CONSTRAINT_ADDED**（运行时扫描与投影实现 = B-PR1/B1-06，`NOT_RUN`） |

---

## 3. 未关闭项与转办清单

| # | 项 | 归口 | 关闭判据 |
|---|---|---|---|
| 1 | P1-08 bwrap 命令顺序 | **b-cf（B-PR1 分支）** | 命令 exit 0；`/tmp` 受限断言；旧序被测试拒绝 |
| 2 | P2-05/P2-06/P2-11 协议细节 | **b-cf（威胁模型/B-PR1）** | 正则与示例一致；协议 fd 冻结测试；worker 确定性测试 |
| 3 | P1-01..P1-07 实现验收 | B-PR1/B-PR2/B-PR4 | 对应负例/单测 + Reviewer 复核（§1 验收列） |
| 4 | P2-01 写 gate 机制 | B-PR2 | 绕过负例；repository 写方法不可达/需 token |
| 5 | P2-03 知识决策审计、P2-09 FULL 受限 | B-PR4 | PLAN_CREATED payload 审计；默认导出无 FULL 文本（sentinel 扫描 0） |
| 6 | P2-04 CI 脚本采纳 | B-PR1..5 CI | 冻结命令在错误树 fail fast、正确树输出计数 |
| 7 | P2-13 运行时导出扫描 | B-PR1（B1-06） | teacher-visible JSON 0 个 `scoring/`；T1 仍可按 trusted ref 读取 spec |
| 8 | 全仓 M0 套件 | **不在 M1-B 验收范围** | 引用时原样保留 `6 failed / 1697 passed / 19 skipped`；不得写成全绿（Reviewer 预审本轮 `NOT_RUN`） |

> 所有 P1/P2 的 **DOC_FIXED** 只表示接口/文档层已修订，不等于实现或验收通过；B-PR0 的
> `TEST_EVIDENCE_MATRIX.csv` B0-01 仍为 `NOT_RUN`，B1-01..06 仍为 `NOT_RUN`。

---

## 4. 本响应对三份文档的修订索引

| 文档 | 修订要点（P1/P2） |
|---|---|
| `docs/M1_B_CONVERGENCE_ADR.md` | 预审响应表头行；§4.2（难度/考核方式/标签/内容引用统一判定，P2-08）；§4.3（映射表指针，P1-02）；§4.4（dimensions→lossy sidecar + RubricResult 指针，P1-07/P2-08；stale ref，P2-10）；§4.5（永久拒绝 mastery 导入，P1-05）；§4.9（trust registry，P1-06）；§4.11（trusted capability，P1-01）；§4.1（stale ref，P2-10）；新增 §5.1.1 映射表（P1-02）；§5.2 写 gate/导出投影说明（P2-01/P2-13）；§6.6 v0 零 diff（P1-04）；§7.1/§7.2/§7.3/§7.4（P1-03/P1-04/P1-05/P2-07/P2-12）；§8.1/§8.2（P2-01/P2-13）；§12 Q8（P1-05）；变更记录 |
| `docs/M1_B_PORTS.md` | §2.1 v0 零 diff（P1-04）；§3.1 FULL 受限资产（P2-09）；§3.2 能力位删除/可信构造配置（P1-01）、item_digest 重算（P2-02）、协议一致性转办（P2-05/06/11）；新增 §3.2.1 RubricResult（P1-07）；§3.3 信任 registry（P1-06）+ canonical 审计落点（P2-03）；§3.4 FULL 受限（P2-09）；§4 写 gate/导出投影（P2-01/P2-13）；§5.2 M1/M3/M4/M6/M9/M10（P1-03/P1-05/P2-08）；§5.3 checksum 闭合（P1-03/P2-07）；§5.4 manifest 指针（P2-12）；§6.2 v0 零 diff（P1-04）；§7 P-11..P-15 验收项；§8 Q2/Q3 更新 |
| `docs/M1_B_CI_AND_DEMO.md` | 预审响应表头行；§2.1 A 实现树零 diff + 前后只读断言（P2-04）；§3.1 B SHA pin + 前后只读断言（P2-04）；§4.1 运行时导出扫描冻结项（P2-13）；§2.2 历史缩写修正（P2-10）；§8 I-7；变更记录 |

**未改动**：`docs/M1_B_BOUNDARY_PRE_REVIEW.md`（Reviewer 文件，原样保留，已由其 `1a74530` commit）、
`docs/M1_B_THREAT_MODEL_JUDGE.md`（b-cf 维护，P1-08 转办）、任何源码/测试/fixture/实现。

---

## 5. 证据、边界与声明

1. **无新 PASS**：本响应是文档修订；不声称 P1/P2 已“关闭验收”，不声称 B0-01/B1-01..06 通过。
2. **命令证据引用**：Reviewer 报告 §1.2 的 C1–C11 为其在本轮真实执行的记录（A 536 / B 365 / demo digests /
   工件哈希 / 静态 grep 等）；本响应**未重新执行**这些命令，不把其输出升级为新的集成验收。
3. **数字纪律**：历史 536/365 仍各自冻结、不可相加（不存在 901）；全仓 M0 的
   `6 failed, 1697 passed, 19 skipped` 原样属于 M0/A 线，不在本线验收范围。
4. **实现未动**：本轮未修改任何 `.py`/fixture/测试；未接触 M0/security/bridge/config/g*/scripts/g4*/LiveGate；
   无网络/无 Key/无真实学习者数据。
5. **评审文件独立**：`docs/M1_B_BOUNDARY_PRE_REVIEW.md` 由 Reviewer 保留（`1a74530`）；本响应仅引用，不修改/不删除；
   若 Reviewer 后续更新该文件，其结论以其原文为准。
6. **剩余风险**：P1 的实现验收与 P2-13 运行时扫描是下一阶段的实打实测试项；任何“文档已改=安全已修”的解读
   都是错误的。

---

## 6. 变更记录

| 日期（UTC） | 版本 | 变更 |
|---|---|---|
| 2026-11-20 | v1.0 | 响应 `PRE_REVIEW_PASS_WITH_ACTIONS`：P1-01..07 文档修订、P1-08 转办；P2-01/02/03/04/07/08/09/10/12/13 处置与转办清单；未改实现/测试/Reviewer 文件；仍为 DESIGN_ONLY |
