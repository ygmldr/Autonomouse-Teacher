# M1-B B-PR3 独立验收 — Scoped Idempotency 与多学习者隔离

| 字段 | 值 |
| --- | --- |
| Reviewer | 独立 Reviewer（未参与实现；本 turn 只新增本文件并 commit，未改源码/测试/既有文档/既有 commit） |
| Worktree / branch / HEAD | `/root/m1b/review-pr3`，`b-next/pr3-review`，`25185b1935e8eda2d2d65e85699ce9ddd8eb7747`（内容 = PR1+PR2+PR3 合并树） |
| 合并父 | `3103a06`（B-PR3）+ `10fdaa9`（B-PR2，含 B-PR1 合并） |
| 基线 | `4706250`（M1-A `b-pr5`）；PR3 设计 `4a10eb0`；PR3 实现 `18b08fe/2f32f13/3103a06` |
| 日期 | 2026-11-20（UTC） |
| 结论 | **`PASS_WITH_ACTIONS`**（核心 B3-01/02、B-Q3 已验证；2 项 P1 为 legacy 兼容/公共 API 完整性，需关闭后才可升级为无条件 PASS） |
| 范围 | 只覆盖 B-PR3：scoped result_id、多 learner/session/item/turn 隔离、schema v2 add-only 迁移、legacy 适配；**不代表** B-PR1/B-PR2/B-PR4/B-PR5、B0 合同、整体集成或 M0/Live 状态 |
| 证据标签 | `INDEPENDENTLY_REEXECUTED_THIS_TURN` = 本 Reviewer 本轮实测；`OWNER_REPORTED` = Owner 文档/提交中的历史陈述；`STATIC_AUDIT` = 代码/文档静态核对；`NOT_RUN` = 本轮未执行 |
| 数据边界 | 全部 synthetic fixtures/临时 SQLite，无真实 PII、无 Key、无网络、未修改仓库；探针脚本只在 `/tmp`，不提交 |

---

## 1. 结论摘要

- **P0：无。** 未发现“返回他人 AssessmentResult”、静默 last-write-wins、跨 learner 写入对方 snapshot/事件、迁移改写历史行或 fail-open 的证据。
- **核心验收成立：** B3-01/B3-02/B-Q3 用独立探针（非 Owner 测试 helper）实测通过：跨 learner/session/item/turn 同 token 均稳定 `IDEMPOTENCY_CONFLICT`，目标 learner 的 events/snapshot/pending/turn 零变化，错误 details 只含 requester scope；同 scope 同 response 重试同一 result、零附加 event、mastery 仅一次；同 key 不同 response/item 稳定冲突且不返回旧成绩。
- **两份实现文档存在两处需要处理的过度声明/遗漏**（详见 §6）：
  - **P1-1**：`idempotency.canonical_response()` 对 dict/list 改用了 compact separators，而 pre-PR3 `_canonical_response()` 没有；导致**结构化 legacy response 的“可证明 digest”适配被误判为 `REQUEST_DIGEST_MISMATCH`**。新数据不受影响，但文档宣称的 legacy 兼容/默认 id 升级路径对结构化 response 不成立。
  - **P1-2**：`LearningHistory.apply_assessment()` 仍用全局 `get_event("evt.assessed.<result_id>")`。独立探针证明：A 使用某 token 后，B 以同一 token 调用该公共 API 时 **B 的 assessment 被静默丢弃**（跨 learner 影响，不泄漏 A 的成绩）。设计 §5.4 明确要求改 scoped 查找，实现报告 §1.2 却宣称“All result reads go through a scoped repository API”，且 §2.1 偏差清单未列此项。
- **P2（5 项）**：同 scope 并发同 response 两个进程都成功返回同一结果（设计 M16 允许“收敛”，但与本次验收字面“另一个显式 conflict”不同）；PAUSED/COMPLETE phase 门禁先于 scoped 快速路径；实现报告仍写 632/595 与最终 774 不一致；event-log legacy fallback 未校验 turn；schema v2 允许 v1 行 `turn_index=-1`（仅应用层避免）。

---

## 2. 工作树与变更范围审计（INDEPENDENTLY_REEXECUTED_THIS_TURN + STATIC_AUDIT）

```bash
cd /root/m1b/review-pr3
git status --porcelain          # 空，exit 0
git branch --show-current       # b-next/pr3-review
git rev-parse HEAD              # 25185b1935e8eda2d2d65e85699ce9ddd8eb7747
git diff --name-only 4706250..HEAD
```

- 变更共 **54 个唯一文件**：`docs/` 14、`fixtures/m1_teacher/judge/` 4、`m1_teacher/` 17、`tests/m1_teacher/` 19。这些包含 PR1（judge/worker/sandbox、fixtures）与 PR2（txn/recovery、crash/concurrency tests）；符合合并树预期，不是 PR3 单独新增。
- 受保护前缀扫描 **零命中**：`src/autoteacher_m0/`、`security/`、`bridge/`、`config/g*`、`scripts/g4*`、`LiveGate`、`plugins/`。命令 `git diff --name-only 4706250..HEAD | grep -Ei '(^|/)(security|bridge|config|g[0-9]|g4|LiveGate|plugins)(/|$)|^src/'` 返回 exit 1（无匹配）。
- **PR3 自身范围**（`git diff --name-only 4a10eb0..3103a06`）恰好 8 个文件：
  - 新增：`m1_teacher/idempotency.py`、`tests/m1_teacher/test_scoped_idempotency.py`、`tests/m1_teacher/test_scope_migration.py`、`docs/M1_B_SCOPED_IDEMPOTENCY_IMPLEMENTATION.md`；
  - 修改：`m1_teacher/contracts/errors.py`、`m1_teacher/learner/history.py`、`m1_teacher/learner/repository.py`、`m1_teacher/session/engine.py`。
- 冻结面：`m1_teacher/contracts/types.py`、`assessment/scorer.py`、`demo.py`、`cli.py` 在 PR3 scope 内 **零 diff**；`contracts/errors.py` 仅新增 3 个 code 常量（append-only），异常类默认 code 未变。
- schema v1 DDL 集合在 `4a10eb0` 与 `3103a06` 之间 **完全相同**（脚本比对 `_RESULT_SCOPES_SQL` 之前的全部 `CREATE TABLE/INDEX`）；PR3 只新增 `result_scopes` 表与 2 个索引。
- 未删除测试文件、未新增 dependency/网络/凭据；新增 2 个测试文件无 `skip`/`xfail`。

---

## 3. 独立复跑（INDEPENDENTLY_REEXECUTED_THIS_TURN）

环境：`/root/Autonomous Teacher/.venv/bin/python`（Python 3.11.15，pytest 9.2.0），worktree `/root/m1b/review-pr3`，无网络/无 Key。下表 E1–E7 均为 **`INDEPENDENTLY_REEXECUTED_THIS_TURN`**。

| # | 命令（摘要） | Exit | 实测输出 |
| --- | --- | --- | --- |
| E1 | `pytest tests/m1_teacher -q` | **0** | **`774 passed in 88.63s (0:01:28)`**（日志 `/tmp/pr3_full_pytest.log`） |
| E2 | `pytest tests/m1_teacher/test_scoped_idempotency.py -q` | 0 | `26 passed in 2.80s`（wall 3.05s） |
| E3 | `pytest tests/m1_teacher/test_scope_migration.py -q` | 0 | `11 passed in 1.30s`（wall 1.52s） |
| E4 | `pytest tests/m1_teacher/test_crash_recovery.py -q` | 0 | `35 passed in 17.50s`（wall 17.72s） |
| E5 | `pytest tests/m1_teacher/test_concurrency.py -q` | 0 | `9 passed in 3.12s`（wall 3.38s） |
| E6 | `ruff check m1_teacher tests/m1_teacher` | 0 | `All checks passed!` |
| E7 | `python -m m1_teacher.cli --student a --json --max-turns 3 --pause-after-turns 2` | 0 | 仅 `m1a.learner.student_a`；无 Reviewer 探针/他人标识 |

- **Owner 声称的 774 = 737 + 37 可对上**：新测试 26（scoped）+11（migration）=37；HEAD 全量为 774。PR2 基线 `10fdaa9` 单独复跑收集到 **737 tests**，但在本机同时有另一无关 suite 运行，3 个 PR1 judge-negative tests 因共享 `/tmp` worker 目录扫描失败（734 passed / 3 failed）；失败项在 HEAD 全量运行中全部通过，且失败原因与 PR3 无关（见 §7 环境说明）。因此 737 的“数量”为 `INDEPENDENTLY_REEXECUTED_THIS_TURN`，其“全绿”只作为 `OWNER_REPORTED`/环境受限记录，不当作 PR3 证据。
- 本 turn 未发现断言 weakened/skip：新测试文件内无 `pytest.mark.skip/xfail`；行为测试真实调用 engine/repository 并检查 DB/事件/snapshot，不是 grep 自证。

---

## 4. 独立探针（B-Q3 / B3-01 / B3-02；只读、/tmp、不提交）

所有探针使用独立脚本与临时 DB；`student A/B`、session/item/result 均为 synthetic。脚本：
`/tmp/pr3_probe_core.py`、`/tmp/pr3_probe_concurrency.py` + `/tmp/pr3_probe_child.py`、`/tmp/pr3_probe_legacy.py`、`/tmp/pr3_probe_history_global.py`、`/tmp/pr3_probe_structured_legacy.py`。

### 4.1 (a) Student A 的 result_id 在 B 的活动 session 复用

做法：A 先提交到 `item.bs.mcq.001`，再推进到 `item.bs.mcq.002` 并用 `case.shared.probe` 提交；B 在独立 session 的 `item.bs.mcq.001` 上复用同一 token（response 不同）。

```text
B outcome: ConflictError code=IDEMPOTENCY_CONFLICT
           reason=RESULT_ID_SCOPE_MISMATCH
B events/snapshot/session unchanged: true
B pending/turn unchanged: true
B has ASSESSED/MASTERY_UPDATED: false
foreign leaks in error/logs: []
A state unchanged by B: true
```

结论：**不返回 A 的 AssessmentResult；B 零写入；details 仅含 B 自己的 `requested_scope`（learner/session/item/turn/result_id/digest）**。A 的 item 为 `.002`、B 的为 `.001`，错误中未出现 A 的 item/session/learner。

### 4.2 (b) 同 learner 跨 session / 同 session 跨 item / 同 token 不同 response

| 场景 | 实测 code / reason | 状态写入 | 旧成绩返回 |
| --- | --- | --- | --- |
| 同 learner、session1 已提交，session2 复用 token | `IDEMPOTENCY_CONFLICT / RESULT_ID_SCOPE_MISMATCH` | events/snapshot/session2 逐字段不变 | 否 |
| 同 session、item1→item2，复用 token | `IDEMPOTENCY_CONFLICT / ITEM_MISMATCH` | events/snapshot/session 不变 | 否 |
| 同 session/item/turn，同 token、response 改为 `"B (different)"` | `IDEMPOTENCY_CONFLICT / REQUEST_DIGEST_MISMATCH` | events/snapshot 不变；scorer 不再调用 | 否 |

三种场景均稳定失败关闭，且 `assert_conflict_details_are_requester_only` 类检查（本 Reviewer 独立版）通过。

### 4.3 (c) 同 scope 同 response 重试

```text
same_result: true
event_count_before/after: 8 / 8
scorer_calls_before/after: 1 / 1
ASSESSED count: 1; MASTERY_UPDATED count: 1; applied=true count: 1
snapshot_revision: 1
scope row after: 1 行，TERMINAL
verify_rebuild: true
```

结论：同一 result、零附加 event、零附加 snapshot/session 写入，mastery 只应用一次。

### 4.4 (d) 两进程并发

**同 scope（同 learner/session/item/token/response，3 轮，真实双进程 + 文件屏障）：**

| 轮次 | 返回码 | 结果 | 显式 conflict | DB 证据 |
| --- | --- | --- | --- | --- |
| 0/1/2 | `[0,0]` | 两者都返回 `case.concurrent.token` 同一结果 | **0** | 1 ASSESSED、1 MASTERY_UPDATED、1 TERMINAL scope、snapshot rev 1、`verify_rebuild=true` |

**跨 learner（同 token）：** 返回码 `[0,3]`；恰好 1 winner + 1 loser；loser `IDEMPOTENCY_CONFLICT / RESULT_ID_SCOPE_MISMATCH`；winner 的 learner/session 未出现在 loser 错误中；loser 无 ASSESSED/MASTERY，无 scope row；winner 只有 1 套终态证据。

**判读（重要）**：同 scope 的“恰好一个生效”成立（唯一终态/唯一 mastery），且不是静默 last-write-wins；但**不是**“另一个显式 conflict”，而是两个调用都返回同一 result 的文档化 M16 收敛语义。与本次验收提示的 (d) 字面要求不同，列为 **P2-1**，不据此否定 B3/B2 的隔离结论。

### 4.5 (e) legacy / 迁移（使用真正由旧 worktree 产生的 v1 DB）

用 `/root/m1b/pr2`（`10fdaa9`，PR2）与 `/root/at-m1a-mvp`（`4706250`，M1-A）各自生成真实 schema-v1 DB，再复制到 `/tmp`、用 HEAD 打开；不是把新 engine 生成的 DB 降级。

| 变体 | 打开结果 | 行级证据 | 重放 |
| --- | --- | --- | --- |
| PR2 v1，string response，digest 可证明 | 成功，version 1→2，新增 `result_scopes` | `history_events/snapshots/sessions/goals` 行哈希 **open 前后相同**；`verify_rebuild=true` | 同 learner/session/item/token/response → 返回旧 result；`zero_write=true`，scorer 0 次；scope row `turn_index=0, origin=legacy, digest=legacy:559a…` |
| PR2 v1，删除 RESPONSE_SUBMITTED/ASSESSMENT_PREPARED（digest 不可证明） | 成功迁移；scope row `turn_index=-1, request_digest=legacy:unproven` | 数据行哈希不变 | `IDEMPOTENCY_CONFLICT / LEGACY_DIGEST_UNPROVEN`，零写入 |
| 同 migrate 后跨 learner 重放 | — | — | `IDEMPOTENCY_CONFLICT / LEGACY_SCOPE_MISMATCH`；错误中无 A 的 learner/session；B 状态不变 |
| schema version 99 / 3 | `ValidationError`（unsupported on-disk schema version） | version 保持 99/3；**未创建** `result_scopes`（无半迁移） | — |
| terminal event payload 损坏为 `{not-json` | `ValidationError`，整笔迁移 rollback | version 保持 1；无 `result_scopes` | — |
| M1-A `4706250` v1（无 ASSESSMENT_PREPARED） | 成功迁移 | 行哈希不变；`verify_rebuild=true` | 同 learner 成功返回旧 result、零写入；跨 learner 拒绝 |

**P1-1 反例（同一 legacy 机制，dict response）**：PR2 v1 DB 用 response `{"answer":"A","why":"because"}` 提交；迁移行 digest 为旧投影 `legacy:622f5b364e154174`；HEAD 重放同一 dict：

```text
ConflictError code=IDEMPOTENCY_CONFLICT
reason=REQUEST_DIGEST_MISMATCH
requested request_digest=196301ef1cf9b606…（compact 投影）
scope row digest=legacy:622f5b364e154174（旧投影）
zero_write=true
```

即“digest 可证明却被拒绝”。原因见 §6/P1-1。

### 4.6 (f) 泄漏与 CLI/日志扫描

- 所有冲突的 `details` 键严格为 `{reason, requested_scope, policy_version}`；`requested_scope` 只含请求方值；`message/str/to_dict` 中无对方 learner/session/item/分数/response 文本。
- 探针在冲突调用期间挂接 root logging handler，捕获日志为空；B 的 events 全为 B。
- CLI `--student a --json` 输出只含 `m1a.learner.student_a`，未出现任何探针 learner/token。
- 残余风险：严格冲突策略仍带来“token 是否已被使用”的存在性预言机（设计 §8.3 已记录，不含 owner 数据）；本 PR 不声称消除。

### 4.7 公共 API 反例（P1-2）

独立脚本：A 先 `LearningHistory.apply_assessment(A, ..., result_id=TOKEN)`；B 再以同一 TOKEN 调用 `apply_assessment(B, ...)`：

```text
A events: [ASSESSED, MASTERY_UPDATED]
B events after apply: []
B snapshot before/after: null
B returned revision: 0
B assessment dropped: true
global event id: evt.assessed.review.history.shared.token
```

B 的结果被静默丢弃（不是泄漏 A 的成绩，但正是“跨 learner token 影响”这一类缺陷）。`apply_assessment` 不在 scoped `submit_response` 的事务路径上，当前 engine 事务路径不可达；但它是公共 API、legacy engine 仍在使用，且设计明确要求改 scoped。

---

## 5. 设计与实现一致性（STATIC_AUDIT + 运行证据）

| 主题 | 核对结果 |
| --- | --- |
| 纯模块位置 | 设计建议 `session/idempotency.py`；实现放 `m1_teacher/idempotency.py` 以避免 `session.__init__ → engine → repository` 的 import cycle。实现报告 §2.1 已列偏差，合理；不影响接口。 |
| scope 五元组 + digest | 实现与设计一致；`ResultScope` frozen/validate；`result_id` 字符集/长度校验；默认 id `result.v1.<32hex>`。 |
| schema v2 | `result_scopes` add-only；`result_id` PK；TERMINAL 需 `result_event_id`；v1 DDL 未变；打开 v1 自动迁移并回填，失败整体 rollback；未知版本 fail-closed。 |
| 事务内写入 | `commit_teaching_turn(scope=...)` 在同一个 `BEGIN IMMEDIATE` 内写 events + scope row + snapshot + session；冲突 rollback。E4/E5 与独立 probe 的零写入证据支持。 |
| 结果读路径 | `find_result_in_scope` 只对完整 v1 scope 返回；`find_scope_owner` 只返回 metadata；`get_event_for_learner` 过滤 learner；engine 的 scoped result helpers 不再用全局 `get_event` 取结果（AST 测试 + 本 Reviewer 静态扫描）。**例外：`history.apply_assessment` 仍全局（P1-2）**；`_prepared_payload` 的 degraded-repo fallback 与 `_record_recovery_error`/goal 的全局读属 attempt/audit 元数据，不返回 AssessmentResult。 |
| 事件 payload | `scope` 为 additive；`assessment_event_drafts` 校验 scope 与 learner/session/item/result 一致；`verify_rebuild` 忽略新增字段（probe c 与 E4 全真）。 |
| legacy | string response 的 provable/unprovable、跨 learner、未知 schema、损坏 JSON 均符合设计；**dict/list 的 digest 投影不一致**（P1-1）。 |
| PR2 语义保持 | E1 全绿 774；E4 35 crash、E5 9 concurrency 全绿；未发现 PR3 改变 PR2 的 recovery/原子提交行为。 |
| 测试真实性 | 新测试直接驱动 engine/repository，真实双进程（`subprocess` + barrier），白盒断言 `result_scopes`/事件/快照；无 skip/xfail；AST/purity 测试只是补充层，不是唯一证据。 |
| 既有测试改动 | PR3 的 3 个 commit **未修改任何既有测试**；`test_e2e_resume_idempotency.py` 的更强冲突断言来自 PR2 commit `2f091ee`，`test_session_engine.py` 未变且保持通过。实现报告“PR2 已加强、PR3 未改测试”属实。 |
| 测试缺口 | 项目内 v1 fixture 由**新 engine 生成后降级**（drop table/set version 1/剥 scope 字段），不是旧 engine 产物；因此无法捕获 P1-1。Reviewer 已用真正旧 DB 补证。 |

---

## 6. 文档声明 vs 实际（过度声明/遗漏）

| # | 文档声明 | 实际 | 判定 |
| --- | --- | --- | --- |
| D1 | `idempotency.py` docstring：与 engine 一直使用的投影相同，故 legacy digest 前缀可比（:99-102）；设计 §2.2 要求复用 `_canonical_response`（无 separators） | `canonical_response` 对 dict/list 增加 `separators=(",", ":")`，旧投影为默认空格分隔；结构化 legacy response 同请求重放被 `REQUEST_DIGEST_MISMATCH` 拒绝；`legacy_default_result_id` 同样用新投影，旧默认 id 升级查找会 miss | **过度声明/功能遗漏 → P1-1** |
| D2 | 实现报告 §1.2：“All result reads go through a scoped repository API”；§2.1 偏差清单未提 `history.py` | `history.py:411` 仍 `get_event(assessed_event_id(...))`；设计 §5.4 明确要求改 scoped；独立 probe 证明 B 被静默丢弃 | **过度声明/遗漏 → P1-2** |
| D3 | 实现报告 §5.1/§7：`632 passed`，baseline `595 passed`，reviewer 应 expect 632 | 最终合并树实测 **774 passed**；632/595 是 PR1 合并前的历史数字，未标注为历史基线 | **P2-3（文档精度；非虚报，实际更高）** |
| D4 | 实现报告 §2.1.7：默认 id 升级可在旧库 adopt | 对 string response 成立；对 dict/list 因 D1 的投影差异不成立 | 并入 P1-1 |
| D5 | 实现报告 §3.4 / §6：`turn_index=-1` 仅 legacy 行 | DDL 只写 `CHECK (turn_index >= -1)`，未约束 `origin='legacy' OR turn_index>=0`；当前应用层确实只写 v1>=0 | **P2-5（防御纵深/文档精度）** |
| D6 | 实现报告 §4 step 6：legacy turn 必须是 -1/相等/just-consumed previous | `_legacy_result_from_owner` 如此；但 `_legacy_event_lookup`（index 行缺失时的 fallback）只校验 learner/session/item/digest，未校验 turn | **P2-4（fallback 边界）** |
| D7 | “No test was weakened or removed”；B3-01/02 未改 matrix | PR3 未改既有测试、未删断言、matrix 确未改；PR2 的 e2e 更强断言不属 PR3 | 属实 |
| D8 | 无 auth、单 writer、at-least-once scorer、合成数据、schema 写入后旧引擎 fail-closed | 与代码/探针一致；旧引擎读 v2 会因未知枚举/版本失败关闭 | 属实 |

---

## 7. Findings（P0/P1/P2，动作 + 验收）

### P0
无。

### P1-1（legacy 兼容 + 文档过度声明）— 结构化 response 的 legacy digest 不可比

**证据**：`m1_teacher/idempotency.py:96-113` 对 dict/list 使用 compact separators；pre-PR3 engine（`4706250`/PR2）使用 `json.dumps(..., ensure_ascii=False, sort_keys=True, allow_nan=False)`（空格分隔）。独立 probe：PR2 v1 DB 以 `{"answer":"A","why":"because"}` + `review.legacy.token.1` 提交；迁移 scope row `legacy:622f5b364e154174`；HEAD 重放同一 dict 得到 `REQUEST_DIGEST_MISMATCH`，而同一 DB 的 string response 重放成功。`legacy_default_result_id` 也用 compact 投影，旧默认 id（旧投影）无法被找到。

**影响**：仅 legacy/升级路径；新写入不受影响；fail-closed，不泄漏数据。但使“可证明 digest → 显式适配”和“默认 id upgrade adopt”对结构化 response 不成立，且与实现文档/docstring 的“兼容”声明矛盾。

**动作**：为 legacy 比较保留旧投影（例如 `legacy_request_digest()` 使用无 separators 的 `json.dumps`；`legacy_default_result_id` 使用旧投影），或同时接受两种 16-hex 前缀并在 scope 行记录投影版本；新增由 PR2/base 真实生成的 v1 fixture（含 dict/list response）。**验收**：同 dict response 重放返回旧 result、zero_write、scorer 0 次；不同 dict 仍 `REQUEST_DIGEST_MISMATCH`；跨 learner 仍 `LEGACY_SCOPE_MISMATCH`；全量 774+ 绿。

### P1-2（公共 API 完整性 + 文档过度声明）— `LearningHistory.apply_assessment` 仍全局查重

**证据**：`m1_teacher/learner/history.py:411` `existing = self._repository.get_event(assessed_event_id(result.result_id))`；设计 `docs/M1_B_SCOPED_IDEMPOTENCY.md:467` 明确要求改为 scoped；实现报告 §1.2 宣称所有结果读取走 scoped API，§2.1 偏差清单未列。独立 probe：A 先 apply 后，B 用同一 token apply，B 的事件/快照均未产生（返回 revision 0），B 的 assessment 被静默丢弃。

**影响**：当前 `submit_response` 事务路径不调用该 API，scoped engine 路径不可达；但它是公共 API，legacy engine `_handle_observed_result` 仍使用；跨 learner token 会造成静默证据丢失，属于 B3 同类风险的未清理路径，且文档声明不实。

**动作**：用 `get_event_for_learner(learner_id, ...)`（或 scoped API）替代；若 existing 属于其他 learner，抛稳定 `IDEMPOTENCY_CONFLICT`/`RESULT_ID_SCOPE_MISMATCH`，不得静默返回/丢弃；新增负例（A/B 同 token 调 `apply_assessment`）。**验收**：B 得到显式冲突、A 状态不变；同 learner 重复 apply 仍幂等；全量绿；实现报告更新偏差/限制。

### P2-1（验收语义/文档）— 同 scope 并发同 response 未返回显式 conflict

独立双进程 3/3 轮均为两个 success + 同一 result；DB 只有 1 份终态/mastery。设计 M16 明确允许“一个写入、另一个读到同一 scope 后返回同一 result”，因此不是数据缺陷；但本次验收提示 (d) 的字面要求是“另一个显式 conflict”。**动作**：在 PR3 验收文字/实现报告中明确“同 payload 并发是 convergent retry；不同 payload/跨 scope 才是 explicit conflict”，或若 Lead 要求严格，则让第二名在事务 A 失败时直接抛 `IDEMPOTENCY_CONFLICT`（需评估重试语义）。**验收**：文档与测试明确该语义；DB 仍恰好一套证据；跨 learner 并发仍 1 winner/1 conflict。

### P2-2（幂等边界）— PAUSED/COMPLETE phase 门禁先于 scoped 快速路径

`engine.py:795-797` 的 PAUSED/COMPLETE 检查在 `:811` 的 scoped 快速路径之前。若最后一次提交使 session 进入 COMPLETE（或之后被 PAUSE），客户端因丢响应重试同一显式 token 会得到 phase `ConflictError`，而不是 I1/M1 的已存 result。**动作**：将同一 scope 的 TERMINAL 查找前移（或对 COMPLETE/PAUSED 增加“仅同 scope 重试”例外），并加测试；或明确文档化“phase 变化后不保证 idempotent replay”。**验收**：同上重试返回同一 result、零写入；非本 scope 的调用仍拒绝。

### P2-3（文档）— 实现报告测试计数过期

报告 §5.1/§7 的 `632/595` 与最终合并树 `774` 不一致（632 为 PR1 合并前历史）。**动作**：更新为最终树 `774 passed`（并注明 632/595 的历史基线），或明确标注“历史分支数字”；§7 checklist 的 `expect 632` 改为 774。**验收**：文档命令/数字与本 turn 输出一致。

### P2-4（legacy fallback）— `_legacy_event_lookup` 未校验 turn

`engine.py:1417-1458` 的 event-log fallback 只匹配 learner/session/item/result_id/digest，不校验 turn（报告/设计称 legacy turn 需 -1/相等/just-consumed）。仅在 index 行缺失（如手工删表/异常恢复）时可达，仍是 fail-open 到“旧 turn 结果”的边界。**动作**：从匹配的 RESPONSE_SUBMITTED/ASSESSMENT_PREPARED 解析 turn 并执行同样的 -1/equal/previous 规则，或把该 fallback 限制为迁移/诊断路径。**验收**：旧 turn 重用 token 得到 conflict；同 just-consumed 重试仍成功。

### P2-5（防御纵深）— schema 未约束 v1 行 `turn_index=-1`

`repository.py:284` 只有 `CHECK (turn_index >= -1)`；报告称 -1 仅 legacy。当前写入路径 v1 总是 >=0，故无运行时缺陷。**动作**：增加 `CHECK (origin='legacy' OR turn_index >= 0)`（需迁移兼容评估）或至少在文档/测试中声明依赖应用层。**验收**：直接插入 v1 + -1 被 DB 拒绝，或文档明确接受该风险。

---

## 8. B3 / B-Q3 逐项状态（独立证据）

| 项 | 状态 | 依据 |
| --- | --- | --- |
| **B3-01** Scoped result ID（跨 learner/session/item/turn 同 key 不能取他人结果） | **VERIFIED** | §4.1/§4.2/§4.4 跨 learner 与跨 learner 并发；目标状态零写入；错误 details 无 foreign；`RESULT_ID_SCOPE_MISMATCH`/`ITEM_MISMATCH` 稳定 |
| **B3-02** Same key different payload 必须冲突、不返回旧成绩 | **VERIFIED** | §4.2 不同 response/item；§4.5 legacy 不同 digest；零写入、旧成绩不返回 |
| **B-Q3** 全局 result_id 负例（A/B、跨 session、同 id 不同 response/item；无 PII） | **VERIFIED** | §4.1/§4.2/§4.4；全部 synthetic；错误/日志/CLI 无 foreign |
| B3-01/02 legacy 结构化 response 适配 | **PARTIAL** | §4.5 P1-1：digest 可证明但被误判冲突 |
| B2-01/02/03 交叉 | **PARTIAL / NO REGRESSION** | E1 774 绿；E4 35 crash、E5 9 concurrency 绿；PR2 独立 crash matrix 本轮 **NOT_RUN**（属 PR2 范围） |
| (d) 同 scope 并发“另一个显式 conflict” | **PARTIAL（对提示字面）** | §4.4 两个 success/同一 result；设计 M16 允许；见 P2-1 |
| 迁移/未知版本/损坏 fail-closed | **VERIFIED** | §4.5 |
| 新数据同 scope 幂等重试 | **VERIFIED** | §4.3 |
| `LearningHistory.apply_assessment` 跨 learner 隔离 | **PARTIAL** | §4.7 P1-2 |

**仍 NOT_RUN（不得写成 PASS）**：真实 auth/多租户安全、真实 Provider/网络/Key、分布式/多主机并发、host power-loss 持久性、真实 learner DB 迁移/回滚、B-PR4/PR5 与整体集成、M0/LiveGate/费用账本。所有证据仅 PR3 范围内、单机单文件、synthetic。

---

## 9. 限制与非声明

1. **无真实认证/授权**：`caller_learner_id` 只是受信上层断言；知道他人 session_id 的调用方仍可加载该 session（M1-A 既有边界）。本 PR 只提供数据访问层 scope 校验，**不声称多租户安全**。
2. **单 writer 假设不变**：并发测试证明单机单文件串行化/显式冲突语义，不证明多 writer 吞吐/公平性。
3. **scorer at-least-once**：崩溃窗口可能重复调用外部 scorer；状态应用 exactly-once 由唯一 scope/terminal event/CAS 保证，不承诺远程评分副作用 exactly-once。
4. **合成数据**：全部 fixtures/证据 synthetic/CC0；无真实 PII、无隐藏内容。
5. **范围**：仅 B-PR3 的独立验收；不改变 B-PR1/B-PR2/B-PR4/B-PR5/B0 或 M0/Live 状态；结论不得引用为整体集成 PASS。
6. **环境说明**：E1 的 774 全绿在本轮开始阶段取得；随后 PR2 基线 737 的单独复跑观察到另一无关 PR1 suite 正在运行，其 `/tmp` worker 目录被 judge-negative 测试的全局扫描捕获，导致 3 项环境性失败（734 passed/3 failed）；该 3 项在 HEAD 全量 E1 中通过。不影响 PR3 结论，但说明 judge-negative 测试的 `/tmp` 全局扫描对并发环境敏感（PR1 范围，非 PR3）。

---

## 10. 证据索引（本地 /tmp，不提交）

| 证据 | 路径/命令 |
| --- | --- |
| 全量 pytest | `/tmp/pr3_full_pytest.log`（774 passed，exit 0） |
| 分文件日志 | `/tmp/pr3_test_scoped_idempotency.py.log`、`/tmp/pr3_test_scope_migration.py.log`、`/tmp/pr3_test_crash_recovery.py.log`、`/tmp/pr3_test_concurrency.py.log` |
| ruff | `/tmp/pr3_ruff.log`（All checks passed） |
| 独立 core 探针 | `PYTHONPATH=/root/m1b/review-pr3 python /tmp/pr3_probe_core.py` → 26 checks，0 failed，exit 0 |
| 独立并发探针 | `... /tmp/pr3_probe_concurrency.py` → d1 3 轮、d2 1 winner/1 conflict，exit 0 |
| 独立 legacy 探针 | `... /tmp/pr3_probe_legacy.py` → 6 变体，exit 0；使用 `/root/m1b/pr2` 与 `/root/at-m1a-mvp` 生成的 v1 DB |
| P1-1 反例 | `... /tmp/pr3_probe_structured_legacy.py`（REQUEST_DIGEST_MISMATCH） |
| P1-2 反例 | `... /tmp/pr3_probe_history_global.py`（B assessment dropped） |
| CLI JSON | `/tmp/pr3_cli_a.json`（仅 student_a） |

**复核命令（只读，可复现）**：

```bash
cd /root/m1b/review-pr3
"/root/Autonomous Teacher/.venv/bin/python" -m pytest tests/m1_teacher -q
"/root/Autonomous Teacher/.venv/bin/python" -m ruff check m1_teacher tests/m1_teacher
PYTHONPATH=/root/m1b/review-pr3 "/root/Autonomous Teacher/.venv/bin/python" /tmp/pr3_probe_core.py
PYTHONPATH=/root/m1b/review-pr3 "/root/Autonomous Teacher/.venv/bin/python" /tmp/pr3_probe_legacy.py
```

**本文件 commit message**：`docs(m1b): B-PR3 independent scoped-idempotency review (no-key)`。本文件未修改任何源码/测试/既有文档；探针脚本不提交；未 amend 既有 commit。
