# M1-B B-PR2 独立验收 — Session/History 事务化与真实 Crash Recovery

- **Reviewer**: 独立 Reviewer（未参与实现；本轮只新增本文件并 commit，未改任何源码/测试/既有文档/既有 commit）
- **Worktree / Branch / SHA**: `/root/m1b/pr2`，`b-next/pr2-session-txn` @ `998e6d2`，base `4706250`（`work/m1a-mvp`）
- **评审时状态**: `git status --porcelain` 为空；`git log 4706250..HEAD` 仅 `2f091ee`（feat）+ `998e6d2`（de-flake）
- **日期**: 2026-11-20（UTC）
- **结论**: **`PASS_WITH_ACTIONS`**
- **范围限定**: 这是 **B-PR2 范围内**的独立验收，只覆盖 B2-01/02/03 与 B-Q2；**不代表** B-PR1/3/4/5、B0 合同收敛或整体集成通过；**不改变** M0/Live 状态；无 Key、无外部网络、全部合成 fixtures。
- **证据标签**: `INDEPENDENTLY_REEXECUTED_THIS_TURN` = 本 Reviewer 本轮在本 worktree 重新执行；`OWNER_REPORTED` = Owner 文档/commit message 中的历史陈述（本轮未复现者）；`STATIC_AUDIT` = 代码/文档静态核对。所有 crash 证据均为子进程真实 `SIGKILL`；评分器为 `MOCK` synthetic。

---

## 1. 结论摘要

核心事务/恢复实现**成立**：单个 `BEGIN IMMEDIATE` 提交事件+快照+session，session 内容摘要 CAS，事务 A/B 两阶段边界，真实 SIGKILL 故障注入覆盖 21 个写点，恢复幂等且与不中断提交收敛到同一内容哈希。595 tests 两轮全绿，536 M1-A 基线由 base 归档独立复跑确认，crash matrix 32 行/3 状态/哈希与 Owner 文档完全一致。

但存在 **2 项 P1（均为合同/文档治理，不是产品行为缺陷）** 和 **5 项 P2（防御纵深/文档精度）**，故结论为 `PASS_WITH_ACTIONS`，而非无条件 PASS：

- **P1-1**：新增 `ASSESSMENT_PREPARED` 属 ADR-M1-001 D12 允许的 additive enum，但 D12 要求“必须记录到本 ADR 与 architecture change log”，本 PR 两处均未记录；只改了 freeze test 与自身文档。
- **P1-2**：Owner 文档 §10.2 “crash failpoints cover every repository write point” 量化过宽：`before_goal`/`after_goal` 钩子存在但无任何 crash 用例，`learners` 行写入无钩子；goal 完成只有进程内测试。
- **P2**：恢复审计 `ERROR` 事件可被仓库层误认为“已终结”，在“已不一致”状态下可绕过 INV-4（需直接调用 repository API，engine 路径不可达）；`_record_recovery_error` 的 seq 重试分支是死代码；§8 对 tampered pending 的错误码描述不准；旧版本代码无法读新 DB（降级未文档化）；“无断言被删除”的字面表述不实（实为替换为更强断言）。

---

## 2. 变更范围与工作树审计（STATIC + 本轮命令）

```
$ cd /root/m1b/pr2 && git status --porcelain
(空)
$ git diff --name-only 4706250..HEAD
docs/M1_B_TXN_RECOVERY.md
m1_teacher/contracts/types.py
m1_teacher/learner/__init__.py
m1_teacher/learner/history.py
m1_teacher/learner/repository.py
m1_teacher/session/__init__.py
m1_teacher/session/engine.py
tests/m1_teacher/{test_concurrency,test_contracts,test_crash_recovery,
                 test_diagnostic_engine,test_e2e_resume_idempotency,
                 test_turn_transaction,txn_child,txn_support}.py
```

- **15 个唯一文件**：feat `2f091ee` = **14 files, +4513/−76**（含新增文档）；de-flake `998e6d2` = **2 files, +22/−5**（既有文档再修改 + 新增触及 `test_diagnostic_engine.py`）。与交接包数字一致。
- 受保护前缀 `src/autoteacher_m0/|security/|bridge/|config/g*|scripts/g4*|LiveGate|plugins/` **零命中**；`m1_teacher/contracts/{repository,errors}.py`、domain/knowledge/assessment、fixtures **零修改**；无新增依赖/网络/凭据；diff 密钥模式扫描 0 命中。
- 未删除任何测试文件；新增测试无 `skip`/`xfail`，未用 mock 替换断言；`tests/` 总删除行 = **4**（diagnostic 的 3 行旧断言块、e2e 的 1 行旧调用参数，均为等价或更强替换，见 §6）。
- `test_contracts.py` 的 `_expected_enums()` 仅 **+2 行**（append 新值），未改其他冻结项。

---

## 3. 实测命令与结果（INDEPENDENTLY_REEXECUTED_THIS_TURN）

环境：`/root/Autonomous Teacher/.venv/bin/python`（Python 3.11.15），worktree `/root/m1b/pr2`，无网络/无 Key。命令均在本 worktree 直接执行，exit code 为 pytest 原始退出码。下表中 E1–E9 全部为 **`INDEPENDENTLY_REEXECUTED_THIS_TURN`**；Owner 文档中的历史计时（crash `14.10s`、full suite `34.42–37.62s`、base `16.77s`）为 **`OWNER_REPORTED`**——本轮复跑同量级，但未逐秒复现（见下表），不影响计数结论。

| # | 命令（摘要） | Exit | 实测输出 |
|---|---|---|---|
| E1 | `pytest tests/m1_teacher -q`（第 1 次） | 0 | `595 passed in 33.51s` |
| E2 | `pytest tests/m1_teacher -q`（第 2 次） | 0 | `595 passed in 34.35s` |
| E3 | `pytest tests/m1_teacher/test_turn_transaction.py -q` ×2 | 0,0 | `17 passed in 0.76s` / `0.70s` |
| E4 | `M1B_MATRIX_OUT=... pytest tests/m1_teacher/test_crash_recovery.py -q` ×2 | 0,0 | `33 passed in 13.34s` / `13.28s`；matrix 各 32 行 |
| E5 | `pytest tests/m1_teacher/test_concurrency.py -q` ×2 | 0,0 | `9 passed in 2.70s` / `2.73s` |
| E6 | `pytest ...::test_behaviour_unchanged_without_hidden_scoring_directory -q` ×30 | 0×30 | **30/30 passed**（27×0.03s，3×0.04s） |
| E7 | `ruff check m1_teacher tests/m1_teacher` | 0 | `All checks passed!` |
| E8 | base `4706250` 只读归档后 `pytest tests/m1_teacher -q` | 0 | **`536 passed in 16.41s`**（独立确认基线，非引用 Owner） |
| E9 | Reviewer 独立探针（`/tmp/pr2_probe/`，未提交） | 0 | 8/8 checks PASS，含 21 failpoints × 真实 SIGKILL |

**E4 matrix 复算**（两轮完全一致，逐行聚合）：

- `rolled_back`：9 cases，hash **`77c62048e9c34a12`**，4 events，pending 原 item、turn 0、无 snapshot；
- `prepared`：21 cases，hash **`ec99d57baf55a6e6`**，6 events（含 1 `ASSESSMENT_PREPARED`、1 `RESPONSE_SUBMITTED`），pending 原 item、turn 0；
- `committed`：2 cases，hash **`bbd500fbb1ca734b`**，8 events、snapshot rev 1、`cf.array.basics=0.2`、pending `None`、turn 1；
- 32 rows 全部 `verify_rebuild == True`；文档 §5 的 9/21/2 分组与逐行事件类型/计数/mastery 均对上（示例 JSON 仅把 `case_id` 写成 `case`，值一致）。

---

## 4. Reviewer 独立探针（不复用 Owner 测试 helper）

探针自行构造 schema、直接以 `sqlite3` 读取持久状态，并用独立内容哈希（去掉 wall-clock 与 CAS 字段）。驱动子进程源码位于 `/tmp/pr2_probe/probe.py`，断言在 `/tmp/pr2_probe/review_probe.py`；**只读/临时，未提交**。

### 4.1 崩溃原子性 + 恢复收敛：(a)(b)(c)(f) 合并验证

对 **21 个 failpoint** 各起一个真实子进程，在事务内 `SIGKILL`（退出码 `-9`），再由新进程打开同一 SQLite：

- A 事务 9 点（`after_begin`、`after_session_check`、before/after 两次 `event_insert`、`before_session`、`before_commit`、`after_commit`）；
- B 事务 12 点（`after_begin`、`after_session_check`、before/after 两次 `event_insert`、`before/after_snapshot`、`before/after_session`、`before_commit`、`after_commit`）。

| 观察 | 结果 |
|---|---|
| post-crash 逻辑态 | `rolled_back` 8、`prepared` 12、`committed` 1 |
| 半状态（ASSESSED 但无 snapshot/session 未前进；或 snapshot 无 ASSESSED；或 pending 与 turn 不一致） | **0 例**；`PRAGMA integrity_check` 全部 `ok`；seq 唯一升序；无跨 learner/session 事件 |
| 崩溃后恢复 | 8×`ALREADY_CONSISTENT`（0 events，随后重试提交成功）、12×`RECOVERED`（+2 events）、1×`ALREADY_CONSISTENT`（0 events） |
| 恢复后内容哈希 vs 不中断 | **21/21 全部等于** Reviewer 参考哈希 **`0cf1f4bc5c9497d6`**（含 A 回滚后重试、prepared 恢复、已提交三路） |
| 重复恢复 | 第二轮全部 `ALREADY_CONSISTENT`、`events_appended=0`、event count 与哈希不变 |
| `verify_rebuild` | 恢复后 `True`，且 `rebuild_state == persisted snapshot`；**反向对照**：篡改 snapshot mastery 值后 `verify_rebuild` 返回 `False`（证明检查非空转） |

补充：scorer 窗口真实 `SIGKILL`（子进程 scorer 自杀）→ prepared 态 → `RECOVERED`（+2）→ 再次恢复 0 events，event count 8 不变（(c) 独立路径）。

### 4.2 并发 (d)

同一 session、两个真实进程、不同 response（`A`/`B`）、文件屏障同时放行，重复 3 轮：

- 每轮**恰好 1 个成功**；败者返回显式 `ConflictError(code=IDEMPOTENCY_CONFLICT)`，**未返回旧成绩**；
- 最终 DB：恰好 1 个 `ASSESSED`、1 个 `MASTERY_UPDATED`、turn +1、pending `None`、snapshot rev 1；
- 3/3 轮一致，无 silent last-write-wins。

### 4.3 跨 learner/session 隔离 (e)

同一 DB：learner A 两个 session、learner B 一个 session；在 A 的第一 session 提交后：

- A：12 events，全部 `learner_id=A` 且 session ∈ {A1,A2}；A2 的 pending/turn/phase **逐字段不变**，A2 无 `ASSESSED`/`MASTERY_UPDATED`；
- B：4 events、snapshot `null`、pending/turn 不变（0 污染）；
- 全局 `learners`/`sessions` 行只含预期对象。

### 4.4 非法/旧 schema 与损坏 JSON fail-closed (g)

| 注入 | 结果 |
|---|---|
| `schema_meta.version ∈ {0,2,99}` 后打开仓库 | `ValidationError`（“unsupported on-disk schema version”） |
| `snapshots.snapshot_json='{not-json'` 后读取 | `ValidationError` |
| prepared 事件 `payload_json='{not-json'` 后恢复 | 恢复子进程 rc=3，`ValidationError` |
| prepared 事件缺 `canonical_response`（合法 JSON） | 恢复子进程 rc=3，`ValidationError` |
| 旧代码（base `4706250`）读取 PR2 写出的 DB | `ValidationError`（`event_type: 'ASSESSMENT_PREPARED'` 非法）→ 见 P2-4 |

### 4.5 Legacy 边界（防“假保证”）

protocol-only repository 包装器：`supports_transactional_turns is False`；提交走旧多写路径（事件中**无** `ASSESSMENT_PREPARED`，有 `ASSESSED`）；`recover_session` 抛 `UnsupportedOperationError(code=RECOVERY_UNSUPPORTED)`。与 §9 描述一致。

### 4.6 额外负例（tampered pending）

篡改 session 的 `pending_item_id` 后恢复：`status=FAILED`、`error_codes=[RECOVERY_STATE_INCONSISTENT]`、追加 1 个审计 `ERROR`、session 不被改动、再次调用 `events_appended=0`（sticky，不伪造完成）。

---

## 5. Owner 文档核对（P1 候选逐项）

| 文档主张 | 独立核对 | 判定 |
|---|---|---|
| 595 passed / +17/+33/+9 / 536 基线 | E1/E2/E3/E4/E5/E8 复跑；Owner 计时为 `OWNER_REPORTED` | **一致**（本轮 33.51s/34.35s、base 16.41s；时间有数秒波动，属正常） |
| 32 matrix rows / 3 状态 / 三个哈希 | E4 两轮复算 | **完全一致** |
| 9/21/2 分组、事件类型/计数/mastery/snapshot rev | 逐行聚合 | **一致** |
| 失败码 `DB_BUSY`/`SESSION_VERSION_CONFLICT`/`DUPLICATE_EVENT`/`EVENT_SEQ_CONFLICT`/`SNAPSHOT_REVISION_CONFLICT`/`INCONSISTENT_PENDING` + `RECOVERY_*` | 代码 + 测试 + 探针 | **一致**（`DB_BUSY` 由 Owner 测试覆盖并复跑通过） |
| 回退路径非原子、`RECOVERY_UNSUPPORTED` | 探针 4.5 | **一致** |
| exactly-once state / at-least-once scorer 边界、无远程 exactly-once 承诺 | §7 与实现/探针 | **一致，无夸大** |
| 单 writer/单机产品约束 | §8 明示；探针 4.2/4.3 | **一致** |
| §10.2 “cover every repository write point” | `before_goal`/`after_goal` 无任何测试使用；`learners` 行写入无钩子；goal 完成仅进程内测试 | **过宽 → P1-2** |
| §8 “tampered pending … fail closed (`ValidationError`)” | 探针 4.6 返回 FAILED 报告而非 `ValidationError` | **不准 → P2-3** |
| §9 “additive / 无断言删除” | D12 要求在 ADR+change log 留痕（未做）；tests 删除 4 行（等价/更强替换） | **P1-1 / P2-5** |
| §10 限制 1–9 | 1,3,4,5,6,7,8,9 准确；2 过宽；缺“旧代码读不了新 DB” | **P1-2 / P2-4** |

---

## 6. 既有测试改动审计（是否弱化）

| 文件 | 改动 | 判定 |
|---|---|---|
| `test_contracts.py` | `_expected_enums()` 追加 `ASSESSMENT_PREPARED`（+2 行） | **不是弱化**；D12 允许 additive enum，但 D12 同时要求记录到 ADR/architecture change log——见 P1-1 |
| `test_e2e_resume_idempotency.py` | 旧断言“同 `result_id` + 不同 response 静默返回旧成绩”替换为：同 key 同 response 零新事件；同 key 不同 response 稳定 `IDEMPOTENCY_CONFLICT` 且状态不变 | **变强**，并顺带关闭 B3 类静默缺陷；不是掩盖旧缺陷。注意该行为变更落在 PR2（原属 B3 范围），PR3 Reviewer 应知悉“该缺陷已在 PR2 关闭” |
| `test_diagnostic_engine.py` | 只排除 load-time `created_at`，其余 objective 语义字段全比较；30/30 稳定 | **合理 de-flake**，非弱化（`created_at` 是第二精度 wall-clock 元数据） |

静态证据：无 `skip`/`xfail`；`tests/` 删除行共 4 行，均为被更强/等价断言替换；新增测试 17+33+9=59，595−59=536 与 base 独立复跑一致。

---

## 7. 验收映射（B2-01/02/03 + B-Q2）

| 项 | 交接要求 | 本轮证据 | 状态 |
|---|---|---|---|
| **B2-01** | Events+snapshot+session 同事务，或证明可恢复 | 单 `BEGIN IMMEDIATE`（`repository.py:872-951`）；21 failpoints 真实 SIGKILL 无半状态；回滚测试；33 crash tests 复跑 | **VERIFIED** |
| **B2-02** | 所有写窗口恢复后无重复 mastery、无 stale pending | 4.1：21/21 收敛同一哈希；1 个 `ASSESSED`/`MASTERY_UPDATED`；pending/turn 正确；`verify_rebuild=True`；重复恢复 0 events | **VERIFIED**（进程被杀窗口） |
| **B2-03** | 同 learner 并发要么串行要么显式 conflict，绝不静默覆盖 | 4.2 真实双进程 3/3 显式 `IDEMPOTENCY_CONFLICT`；Owner 的两 session/同请求/跨 learner/busy DB 测试复跑 9 passed | **VERIFIED**（单机单文件；分布式 NOT_RUN） |
| **B-Q2** | 五个写点前后注入进程退出，新进程开 SQLite，报告 Pending/Turn/Mastery/Event count/Hash，检查跨 learner/session 污染 | `RESPONSE_SUBMITTED`、`ASSESSED`、`MASTERY_UPDATED` 的 before/after insert、snapshot before/after、session before/after、commit before/after 全覆盖；matrix 32 行 ×2 轮；4.3 无污染；4.6 tampered pending 不误报完成 | **VERIFIED** |

**仍 NOT_RUN（不得写成 PASS）**：断电/主机崩溃级持久性（`synchronous=NORMAL`+WAL，仅进程 kill）；多主机/共享文件系统/分布式锁；真实远程 scorer 的 at-least-once 去重（本 PR 明确不作承诺）；长时间 soak/fuzz；真实 learner DB 的迁移/回滚（B0 范围）；B-PR1/3/4/5 与整体 E2E。

---

## 8. Findings（P0/P1/P2，含动作与验收）

### P0 — 无

未发现可通过受支持 API 触发的数据损坏、重复 mastery、伪造完成或静默覆盖。

### P1-1（合同治理，必须处理）— D12 要求的合同变更留痕缺失

- **证据（STATIC）**：ADR-M1-001 **D12** 允许 additive enum，但明确“Any change must be recorded in this ADR and in the architecture change log.”；`git diff --name-only 4706250..HEAD` 不含 `docs/M1_ADR_001_DOMAIN_CONTRACTS.md` / `docs/M1_ARCHITECTURE.md`；PR 只改了 `HISTORY_EVENT_TYPE_VALUES`、freeze test 与 `docs/M1_B_TXN_RECOVERY.md`。
- **影响**：freeze test 被同步修改后不再能证明该 additive 变更经过合同流程；后续 PR 可照此绕过 D12。无运行时行为缺陷。
- **动作**：在 ADR-M1-001 §6（或 §7）追加一条 `ASSESSMENT_PREPARED` additive delta，并在 `M1_ARCHITECTURE.md` change log 增加一行；或由 Lead 在书面签收中明确批准该合同增量。
- **验收**：`grep -n ASSESSMENT_PREPARED docs/M1_ADR_001_DOMAIN_CONTRACTS.md docs/M1_ARCHITECTURE.md` 有记录；`pytest tests/m1_teacher/test_contracts.py -q` 仍绿；无需改代码。

### P1-2（文档/覆盖夸大，必须处理）— “every repository write point” 不成立

- **证据（STATIC）**：`repository.py:935-938` 有 `before_goal`/`after_goal`，但 `grep -rn -e before_goal -e after_goal tests/` **零命中**；crash matrix 33 tests 无 goal 完成场景（goal 完成仅 `test_goal_completion_is_atomic_and_persists_goal_status` 进程内验证，无真实 SIGKILL）；`_ensure_learner_row` 的 `learners` 行插入也无 failpoint。Owner 文档 §2 的写点表也未列 goal。
- **影响**：文档给读者“goal 行写入也经过真实 crash 验证”的强印象，实际只有事务回滚推断；属证据强度夸大。
- **动作（二选一）**：(a) 增加 2 个真实 crash 用例（`before_goal`/`after_goal`，用 near-complete snapshot 触发 `GOAL_COMPLETED`），断言 goal/session/snapshot 原子；或 (b) 把 §10.2 改为“覆盖 assessment turn 的 events/snapshot/session 全部写点；goal 行由同一事务保证、仅进程内验证”，并在 §2 写点表注明 goal 未做 crash 注入。
- **验收**：改文档则 `grep` 措辞与 §5 一致；加测试则 `pytest ...test_crash_recovery.py -q` 通过且 matrix 行数相应增加。

### P2-1（防御纵深）— 恢复审计 `ERROR` 可被仓库层当作“已终结”，绕过 INV-4

- **证据（本轮探针）**：正常 prepared 态清 pending → `ValidationError INCONSISTENT_PENDING`；先经 tampered pending 让恢复写入 `RECOVERY_STATE_INCONSISTENT` ERROR（payload 含同一 `result_id`），再调用 `commit_teaching_turn(events=[], next_session.pending=None)` → **提交成功**，最终 `pending=None, assessed=0`；随后 `recover_session` 返回 `FAILED/RECOVERY_STATE_INCONSISTENT`，session 卡死。
- **根因**：仓库 `_terminal_result_ids()` 把任意 `ASSESSED`/`ERROR` payload 的 `result_id` 视为终结；engine `_terminal_result()` 只认 `evt.assessed.*`/`evt.evalerror.*`。两者不一致。
- **可达性**：需 (i) 已处于 recovery 失败/不一致状态，(ii) 调用方直接用 repository API 提交“清 pending 且无 terminal 事件”；engine 自身不会发出这种提交。**非受支持路径可达**。
- **动作**：`_assert_no_unresolved_prepared`/`_terminal_result_ids` 忽略 `stage="RECOVERY"` 的审计 `ERROR`（或改为按确定性 terminal event_id 判定），并加回归测试：恢复失败后清 pending 必须 `INCONSISTENT_PENDING`。
- **验收**：新增回归测试红→绿；现有 crash/concurrency 套件保持绿。

### P2-2（代码健壮性）— `_record_recovery_error` 的 `EVENT_SEQ_CONFLICT` 重试分支是死代码

- **证据（STATIC）**：`append_event()` 调 `_check_seq_conflict(conn, event)` 使用默认 `code="CONFLICT"`（`repository.py:557-560, 986-996`），而 `engine.py:1498-1500` 只对 `EVENT_SEQ_CONFLICT` 重试；并发恢复争用 seq 时会直接抛 `ConflictError` 出 `recover_session`，而不是返回 `RecoveryReport`。
- **影响**：仍 fail-closed、不会假完成；但“可解释恢复报告”在极端并发下退化为异常，且该分支实际不可达。
- **动作**：在 `append_event` 调用处传 `code="EVENT_SEQ_CONFLICT"`（或捕获 `CONFLICT`），补一个 seq 争用恢复测试。
- **验收**：故障注入下 `recover_session` 返回报告（或明确文档化该冲突），分支可达且测试覆盖。

### P2-3（文档精度）— §8 对 tampered pending 的错误码描述不准

- **证据（本轮探针）**：tampered pending → `recover_session` rc=0、`status=FAILED`、`error_codes=["RECOVERY_STATE_INCONSISTENT"]`、追加 1 个 `ERROR`；**不是** `ValidationError`。§6 的描述是对的，§8 括注 `(ValidationError)` 错。
- **动作**：把 §8 该句改为“schema 版本/损坏 JSON → `ValidationError`；tampered pending → `RecoveryReport(FAILED, RECOVERY_STATE_INCONSISTENT)` + 1 审计 ERROR，session 不变”。
- **验收**：文档与探针输出逐字一致。

### P2-4（兼容性）— 旧版本代码无法读取 PR2 写出的 DB，文档未声明

- **证据（本轮探针）**：用 base `4706250` 代码打开 PR2 DB → `ValidationError: HistoryEvent.event_type: 'ASSESSMENT_PREPARED' ...`。原因是冻结 enum 校验。
- **影响**：回滚到旧 build 后该 learner 的 history/session 不可读；§9 只称“additive”，未说“forward-only / 无降级”。
- **动作**：§9/§10 增加“DB 前向不兼容：含 `ASSESSMENT_PREPARED` 的库只能由 PR2+ 读取；回滚前需导出/迁移”，或提供 B0 要求的 compatibility adapter。
- **验收**：文档有该限制；可选加一个 base-version 读取失败被记录的测试。

### P2-5（文档精度）— “No assertion was deleted” 字面不实

- **证据**：`git diff 4706250..HEAD -- tests/` 共删除 4 行：diagnostic 的 3 行旧 assert 块被替换为等价的逐字段比较（除 `created_at`）；e2e 的 1 行旧调用参数被替换（同 `result_id`/不同 response 的调用移入 `pytest.raises`），e2e 的“同 response 返回同一 dict”断言**保留并加强**（零新事件）。无弱化、无 skip、无 mock 通过。
- **动作**：把 commit message/§9 的“none deleted / 无断言删除”改为“唯一的断言替换（diagnostic wall-clock 相等）是等价替换；e2e 幂等断言保留并加强；无弱化/跳过/mock 通过”。
- **验收**：措辞与 diff 一致；测试语义不变。

---

## 9. 实现抽查要点（STATIC_AUDIT）

- `commit_teaching_turn`：参数 fail-closed 复验 → `BEGIN IMMEDIATE`（失败 `DB_BUSY`）→ session CAS（`SESSION_VERSION_CONFLICT`）→ 状态转移校验（`INVALID_SESSION_TRANSITION`）→ 事件插入（`DUPLICATE_EVENT`/`EVENT_SEQ_CONFLICT`）→ 严格递增 snapshot（`SNAPSHOT_REVISION_CONFLICT`）→ goal → session → 无 pending 时的 orphan PREPARED 校验（`INCONSISTENT_PENDING`）→ `COMMIT`；任意异常 `ROLLBACK`。顺序与文档一致。
- `session_version = sha256(canonical compact JSON(session.to_dict()))[:16]`；事务 A 用严格递增 `updated_at` 保证同秒内 CAS 也变化；`SessionState` 无新字段。
- `submit_response`：A（`RESPONSE_SUBMITTED`+`ASSESSMENT_PREPARED`，含 canonical response/digest/kind）→ 事务外 scorer → B（terminal+snapshot+session+goal）；B 的 CAS/重复冲突会回查确定性 terminal，命中则零事件返回，否则显式抛出。
- `recover_session`：先查终结 → 校验 pending/turn 匹配 → 事务外重评分并要求同一 identity → 走同一原子提交；失败写确定性审计 ERROR、保持 pending、绝不伪造完成；重复调用零事件。与 §6 一致。
- failpoint 默认关闭（`M1B_CRASH_FAILPOINT` 未设置时立即返回）；仅在测试子进程显式开启。

---

## 10. 结论与边界

**`PASS_WITH_ACTIONS`**：B-PR2 的核心验收项 B2-01/02/03 与 B-Q2 均 **VERIFIED**（进程 kill 语义），事务原子性、恢复收敛、幂等、并发显式冲突、跨域隔离与 fail-closed 均有本轮独立证据支撑；无 P0。

放行条件为完成 **P1-1、P1-2**（均为文档/合同治理，不改产品行为），并建议随 PR 处理 **P2-1..P2-5**（其中 P2-1 建议至少在 PR3 前加固）。在 P1 完成前，本 PR 可继续作为 B-PR2 候选，但不应被引用为“合同流程完备”或“goal 写点已 crash 验证”。

本结论仅覆盖 B-PR2 范围；不表示 B-PR1（Judge/OS 沙箱）、B-PR3（scoped idempotency）、B-PR4（两域闭环）、B-PR5（统一 E2E/评测）通过，不改变 M0/LiveGate/费用账本状态，也不构成任何真实学习效果、真实远程 scorer 或联网能力的声明。

---

## 11. 证据索引（本轮原始输出位置，均在 /tmp，不入库）

- `/tmp/pr2_full_suite_run1.log` / `run2.log`：595 passed（33.51s / 34.35s）
- `/tmp/m1b_matrix_run1.jsonl` / `run2.jsonl`：各 32 行 crash matrix
- `/tmp/pr2_base/base_suite.log`：base 归档 536 passed
- `/tmp/pr2_probe/probe.py`、`review_probe.py`、`inv4_probe.py`、`tamper_pending.py`、`downgrade_probe.py`：Reviewer 独立探针（只读/临时）
- `/tmp/pr2_probe/probe_run_full.log`：8/8 checks PASS（21 failpoints，所有最终哈希 `0cf1f4bc5c9497d6`）

**Evidence class**: `DETERMINISTIC`（事务/恢复/并发断言）+ `MOCK`（synthetic student/scorer）；无真实学习者数据、无隐藏 expected、无凭据。
