# M1-B B-PR3 作用域化幂等与多学习者隔离设计（DESIGN_ONLY）

| 字段 | 值 |
| --- | --- |
| 文档状态 | `DESIGN_ONLY`（不包含实现、不改代码/测试/fixture；实现与测试在 B-PR3 编码 PR 完成） |
| 版本 | v0 draft（2026-11-21） |
| 基线 | `4706250`（M1-A `b-pr5`，frozen；worktree `/root/m1b/pr3design`，branch `b-next/pr3-idempotency-design`） |
| 并行依赖 | B-PR2（`m1a-learner`，`/root/m1b/pr2` 未提交实现：`commit_teaching_turn`、`session_version` CAS、`ASSESSMENT_PREPARED`、recovery）；本设计按**兼容 PR2 方向**编写，最终以 PR2 合并后的接口为准 |
| 关联证据 | B-Q3（全局 result_id 负例）、B3-01（Scoped result ID）、B3-02（Same key different payload）、B2-01/02/03（原子提交/恢复/并发） |
| 证据等级 | 本文全部为 `DESIGN_ONLY`；"现状缺陷"部分含 `SOURCE_INSPECTED` 代码路径与一次本地只读 `PROBE`（合成 id、无 PII、不进测试套件）；**没有任何 PASS 声明**；B3-01/02 在实现并独立复跑前保持 `NOT_RUN` |
| 非声明 | M1-A/M1-B **没有真实 auth**；本文不声称"多租户安全"或"已修复"。身份由受信上层传入；M1-B 只能提供数据访问层的租户隔离/幂等约束，不能替代鉴权。无网络、无 Key、无真实用户数据。 |

---

## 0. 决策摘要（供 Lead 快速审阅）

1. **冻结幂等键**：`scope = (learner_id, session_id, item_id, turn_id, result_id)`，外加 `request_digest = sha256(canonical(response))`；`turn_id` 取接受提交时的 `SessionState.turn_index`。
2. **同一 scope + 同一 digest** → 返回同一 `AssessmentResult`，零附加事件、零状态写入；**同一 scope + 不同 digest/item** → 稳定 `IDEMPOTENCY_CONFLICT`（新错误码），不返回旧成绩、不改状态。
3. **不同 learner/session 复用同一 result_id → `IDEMPOTENCY_CONFLICT`**（`RESULT_ID_SCOPE_MISMATCH`），绝不读出对方 `AssessmentResult`；裁决理由见 §3.3。
4. **事件 id 修复采用"payload 作用域 + 索引表 + 读路径 learner 过滤"方案（方案 A）**，保留 `evt.assessed.<result_id>` 既有形状与历史事件；`history_events` 不改写、不重写、不迁移行。新增 `result_scopes` 索引表（schema v2，add-only）作为唯一写路径/查找路径。若未来需要"跨 scope 复用同一 result_id"，再启用方案 B（v2 scoped event id，§4.2）。
5. **与 PR2 的关系**：幂等快速路径在事务外做 scoped 读；权威判定在事务内由 `result_scopes` 唯一约束 + `session_version` CAS + 终态事件唯一性兜底；外部 scorer 始终在事务外（at-least-once scorer，exactly-once 状态应用）。
6. **引擎 API 仅加不破**：`submit_response` 增加可选 `caller_learner_id`（默认 `None`，用于受信上层传入已认证学习者；不匹配则 fail-closed），并为显式 `result_id` 的旧式 replay 提供受控 legacy 适配；无 auth 的事实仍写入限制。

---

## 1. 现状缺陷证据（frozen base `4706250`）

> 本节目的：证明"全局 result_id 查重 → 跨 learner/session 读取/静默丢弃"是真实代码路径，不是理论假设；同时严格区分"读到别人结果"与"改写别人状态"，不夸大。

### 1.1 代码路径（file:line，base `4706250`）

1. **入口与"幂等优先"顺序**（`m1_teacher/session/engine.py:488-527`）：
   - `:502` 仅检查 `PAUSED`；`:504-509` 检查 item 存在；
   - `:512-518` **显式 `result_id` 路径**：先 `_find_existing_result(result_id)`，命中即 `return existing`；
   - `:519-527` **之后**才校验 `pending_item_id`/当前 phase。
   因此查重发生在 learner/session/item/turn/pending/response 任何绑定校验之前。
2. **全局查重实现**（`engine.py:833-850`）：`_find_existing_result(result_id)` 依次 `repository.get_event(assessed_event_id(result_id))`、`repository.get_event(f"evt.evalerror.{result_id}")`，把 payload `["result"]` 反序列化为 `AssessmentResult` 并返回；**签名只有 result_id，没有 learner/session/item/turn/digest**。
3. **事件 id 构造**（`m1_teacher/learner/history.py:81-82,109-118`）：`ASSESSED_EVENT_PREFIX="evt.assessed."`、`MASTERY_UPDATED_EVENT_PREFIX="evt.mastery."`；`assessed_event_id(result_id) = "evt.assessed." + result_id`，与 learner/session **无关**。
4. **全局主键**（`m1_teacher/learner/repository.py:104-112` DDL）：`history_events(event_id TEXT PRIMARY KEY, ..., UNIQUE(learner_id, seq))`；`get_event(event_id)`（`:583-595`）是 `WHERE event_id = ?` 的全局查询，无 learner 过滤；`append_event`（`:510-521`）对重复 `event_id` 返回 `False`（静默去重）。
5. **默认 result_id 路径**（`engine.py:528-539,783-790`）：未显式提供时 `_default_attempt_result_id = "result:<session_id>:<turn_index>:<item_id>:<sha256(canonical(response))[:16]>"`；虽然包含 session/turn/item/digest，但生成后仍走同一个全局 `_find_existing_result`，且同一 session 内同题不同 response 的 digest 不同 → 不同 id；题目相同、turn 前移后 id 不同 → 依赖 pending/phase 校验兜底。
6. **写入路径的确定性事件 id**（`engine.py:708-730`；`history.py:266-292`）：`ASSESSED`/`MASTERY_UPDATED`/`RESPONSE_SUBMITTED`/`ERROR` 均以 result/attempt 相关字符串作全局 `event_id` 写入；`_handle_observed_result`（`engine.py:938-...`）先调用 `LearningHistory.apply_assessment`，后者在 `history.py:266` 用 `get_event(assessed_event_id(result_id))` 做"已应用"判断（同样全局）。
7. **异常路径**：`_score_safely`（`engine.py:812-831`）把 scorer 异常转成 `EVAL_ERROR`，`_handle_eval_error`（`:855-895`）写 `evt.evalerror.<result_id>` 的 `ERROR` 事件；scorer 正常但写出错误 identity 时 `_fallback_result` 复用同一 `result_id` → 与后续重试共享同一全局 key。`_find_existing_result` 同时把 `evt.evalerror.<result_id>` 当成"已存在结果"命中。
8. **当前测试固化了缺陷语义**（`tests/m1_teacher/test_session_engine.py:420-440`、`tests/m1_teacher/test_e2e_resume_idempotency.py:237-270`）：显式 `result_id` 第一次用 response `"A"`，第二次用 `"A (different text)"`，断言第二次 `to_dict()` 等于第一次。**新语义下该用例必须改为 `IDEMPOTENCY_CONFLICT`**（见 §7）；这是"设计改变已知预期"的显式清单项，不是隐藏破坏。

### 1.2 真实只读探针（synthetic id；不修改仓库、不进测试套件）

在 base `4706250` 的 worktree 上，用仓库自带 `m1_teacher.demo.build_components` + `SqliteRepository` + 一个返回固定 `CORRECT` 的测试 scorer，跑 `/tmp/m1b_pr3_probe.py`（只读；临时 DB；全部 synthetic id）：

```text
cd /root/m1b/pr3design && PYTHONPATH=/root/m1b/pr3design \
  "/root/Autonomous Teacher/.venv/bin/python" /tmp/m1b_pr3_probe.py
```

关键观察（原样输出节选）：

```json
{
  "A": {
    "event_count": 7,
    "session_id": "session:probe.learner.A:goal.probe.learner.A",
    "result": {"result_id": "case.shared.result.1", "learner_id": "probe.learner.A",
               "item_id": "item.bs.mcq.001", "status": "CORRECT"},
    "terminal_event_id": "evt.assessed.case.shared.result.1",
    "snapshot_revision": 1
  },
  "B_reuse": {
    "session_id": "session:probe.learner.B:goal.probe.learner.B",
    "requested_item_id": "item.bs.mcq.001",
    "returned": {"result_id": "case.shared.result.1", "learner_id": "probe.learner.A",
                 "item_id": "item.bs.mcq.001", "status": "CORRECT"},
    "returned_is_A_result": true,
    "events_before": 4, "events_after": 4,
    "pending_before": "item.bs.mcq.001", "pending_after": "item.bs.mcq.001",
    "turn_before": 0, "turn_after": 0,
    "snapshot_b": true
  },
  "A_conflict_probe": {
    "requested_item_id": "item.bs.mcq.002",
    "returned": {"result_id": "case.shared.result.1", "learner_id": "probe.learner.A",
                 "item_id": "item.bs.mcq.001", "status": "CORRECT"},
    "returned_first_result_verbatim": true
  }
}
```

读法（严格结论）：
- **跨学习者读取**：learner B 的提交返回了 learner A 的 `AssessmentResult`（`returned_is_A_result=true`），这正是 `engine.py:512-518 → 833-850 → repository.get_event` 的全局路径；
- **B 的证据被静默丢弃**：B 的事件数 `4 → 4`、`pending_item_id` 与 `turn_index` 不变、无 snapshot → B 的提交既没有评分入账也没有推进 session（不是"写坏了 B 的状态"，而是"B 的提交被吞掉 + 读到 A 的成绩"）；
- **同 session/turn、同 result_id、不同 item/不同 response**：第二次提交（请求 item.bs.mcq.002、不同 response）仍原样返回第一次的 `item.bs.mcq.001` 结果（`returned_first_result_verbatim=true`），即 B3-02 的"同 key 不同 payload 静默返回旧成绩"；
- **全局键证据**：终端事件 id 为 `evt.assessed.case.shared.result.1`，与 learner 无关（`history.py:109-118`）。

证据等级：`PROBE`（真实运行、合成数据、只读；脚本在 `/tmp`，不随本 PR 提交；不是测试证据，不作为 B3-01/02 的验收 PASS）。

### 1.3 根因链（按写/读顺序）

```text
result_id 由调用方提供（显式）或 engine 默认生成（含 session/turn/item/digest16）
   └─ 终端事件 id = "evt.assessed." + result_id          # history.py:109-118
   └─ history_events.event_id TEXT PRIMARY KEY          # repository.py:104-112：全局唯一
提交
   └─ submit_response 幂等优先：_find_existing_result(result_id)   # engine.py:512-518
        └─ repository.get_event(event_id) 全局 WHERE   # repository.py:583-595
        └─ 反序列化 payload["result"] → 直接返回        # engine.py:833-850
   └─ 之后才校验 learner/session/pending/item/turn/digest（顺序倒置）
```

三个独立缺陷叠加：(a) 幂等键只有 `result_id`，没有 learner/session/item/turn/response 绑定；(b) 读路径全局、无 learner 过滤；(c) 事件 id 以 `result_id` 为全局主键，跨 scope 同 key 时产生事件层"重复/静默去重"。三者任一单独存在都不足以安全；修复必须同时覆盖"键的绑定 + 读的过滤 + 写的兜底"。

### 1.4 异常重试 / 重放行为（现状）

| 场景 | 现状行为（base `4706250`） | 风险 |
| --- | --- | --- |
| scorer 抛异常 → `EVAL_ERROR`，客户端重试同 result_id | `_find_existing_result` 命中 `evt.evalerror.<result_id>` → 返回旧 `EVAL_ERROR` 结果，**即使 session 仍在 pending**；`_handle_eval_error` 的重试/`retry_exhausted` 逻辑被短路 | 重试无法重新评分或推进 session（B2 恢复语义被幂等旁路） |
| 显式 result_id 首次成功，第二次用不同 response/item | 返回第一次结果，不校验 digest/item（探针 `A_conflict_probe`） | 客户端重复提交被误认为"幂等成功"，掩盖冲突（B3-02） |
| 默认 result_id 重试（同 session/turn/item/digest） | 命中同一全局 event id → 返回旧结果，跳过 pending 修复 | 若崩溃在"已写 ASSESSED、未清 pending"之间（B2），重试直接返回旧结果而不修复状态 |
| 两个 learner 使用同一 result_id | B 返回 A 结果（探针 `B_reuse`）；若 A 尚未写终端事件而 B 先提交，B 写的事件 id 会让 A 的后续写入被 `append_event` 静默 `False`（丢失证据） | 跨租户读取 + 证据丢失（B3-01/B-Q3） |
| 同 result_id 并发双提交（同 scope） | 两个调用都可能通过 `_find_existing_result`（尚未写入），各自评分/写事件；第二个写终态事件时 `append_event` 返回 `False`；`_handle_*` 内 `apply_assessment` 的已存在判断会返回当前 snapshot，最终"结果看似成功但事件只写了一份"；不同步路径下还可能覆盖 session | 并发语义不明确、证据归属不可靠（B2-03 交叉项） |
| 显式结果重放在另一 session | 同上，直接返回旧结果（无 session 校验） | 跨 session 读取（B3-01） |

> 不含 auth 前提的额外事实：`start_session(session_id=...)` 允许调用方显式传 session id（`engine.py:319-357`），`load_session` 只按 id 查（`engine.py:659-667`）。所以"已知他人 session_id 即可加载"是 M1-A 的既有模型边界；B-PR3 的 scope 修复不能替代鉴权，见 §8。

### 1.5 影响边界（不夸大）

- **已证实（探针/代码路径）**：跨 learner 读取他人 `AssessmentResult`；同一 scope 不同 payload 静默返回旧成绩；B 的提交被静默跳过（证据丢失）；事件 id 全局主键是以上行为的根因之一。
- **未证明**（不得声称）：没有观察到 `LearnerSnapshot`/mastery 被跨 learner 直接改写（`apply_assessment` 按 learner 取/写 snapshot，且 `save_session` 属于单一 session）；"数据库行被物理污染"也未见证据。故本文使用"跨租户读取 + 证据丢失 + 幂等语义不可靠"描述，而不是"任意改写他人掌握度"。
- 训练层/Mastery 只从 observed evidence 更新的既有不变量不应因本设计放宽。

---

## 2. 冻结幂等键与绑定

### 2.1 定义

```text
turn_id  = 接受本次提交时 SessionState.turn_index（int >= 0）
result_id = 调用方显式提供；或 engine 默认生成（见 §2.3）
scope    = (learner_id: str, session_id: str, item_id: str, turn_id: int, result_id: str)
request_digest = sha256(canonical_response(response))    # 64 hex，见 §2.2
```

约束：

- `scope` 是幂等与冲突判定的**唯一键空间**；任何查找都必须带完整 scope，禁止只按 `result_id` 查结果。
- `session_id` 必须属于 `learner_id`（session owner 校验；M1-A 由 `SessionState.learner_id` 携带，B-PR3 增加显式 owner 断言，见 §5.4）。
- `turn_id` 是"提交被接受时"的 turn；同一 pending item 的 turn 在评分成功前不变（PR2 `_validate_turn_transition` 保证 PREPARED 不推进 turn）。
- `item_id` 必须等于当前 `pending_item_id`，且 `AssessmentResult.item_id` 必须与之一致（已有 `_score_safely` 校验，PR3 保留）。
- `result_id` 是**scope 内**幂等令牌：同一 scope 内唯一；不同 scope 之间不复用（严格冲突策略，§3.3）。
- 返回值仍为冻结的 `AssessmentResult`（无 scope 字段；scope 元数据存于事件 payload / `result_scopes` 表），避免 contracts 字段变更。

### 2.2 request_digest（规范）

- **两套投影并存（独立评审 P1-1 修正）**：
  - 新写入：`canonical_response` 对 `dict/list` 用 `json.dumps(..., ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)`（compact）；`str` 按 `str(response)`。`request_digest = sha256(canonical_response(response))`。
  - legacy 比较：pre-PR3 engine 的 `_canonical_response` **没有** `separators`（默认 `", "`/`": "` 空格），因此旧 `response_digest`/旧默认 id 必须用 `legacy_canonical_response` / `legacy_request_digest` 重算后再比较；不得混用两套投影，否则结构化 response 的可证明 digest 会被误判为 mismatch。
- 存储 **完整 64-hex** `request_digest`；当前 `RESPONSE_SUBMITTED`/`ASSESSMENT_PREPARED` payload 的 `response_digest` 是前 16 hex（`engine.py:542-548`；PR2 `_prepare_attempt` 同），PR3 保留该字段作为兼容展示，但 scope 判定以完整 digest 为准；legacy 事件只能用 16-hex 前缀比较（§4.5），且该前缀按 legacy 投影计算。
- **不**把 session/turn/result_id 混进 digest：它们已由 scope 绑定，重复计算会破坏"同 scope 同 digest"的清晰语义。
- digest 只对 response 内容敏感：同一 response 的字符串/结构化等价表示必须得到同一 digest（排序键 + 无 NaN）。

### 2.3 result_id：默认生成与调用方校验

**默认生成（engine，v1）**：未显式传入时由 engine 生成，包含 scope 分量与 digest，保证同一次提交的重试得到同一 id，不同 turn/session 不混淆：

```text
result_id(default) = "result.v1." + sha256(canonical_json({
    "learner_id": ..., "session_id": ..., "item_id": ..., "turn_id": ..., "request_digest": ...
}))[:32]
```

（保留 base 旧格式 `result:<session>:<turn>:<item>:<digest16>` 仅用于历史数据/兼容读取，不用于新写入；见 §4.5。）

**调用方显式提供时的校验（fail-closed，`ValidationError` code=`INVALID_RESULT_ID`）**：

- 类型必须 `str`，长度 `1..128`，字符集 `^[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}$`；拒绝 `/`、`\`、空白、控制字符、NUL、`..` 段、Unicode 控制/格式字符（防日志注入/路径歧义；即便内部 event id 另有编码，也不接受可疑 id）。
- 一旦调用方用某 `result_id` 提交成功，**重试必须复用同一 id**；换 id 视为新的逻辑提交（§3.2 裁决）。
- 不允许调用方通过 `result_id` 指定/覆盖 owner、session、item、turn（这些来自当前 session 状态与调用参数）。

### 2.4 attempt 与 PR2 `ASSESSMENT_PREPARED` 的关系

PR2 已引入 durable attempt（`m1_teacher/session/engine.py`，PR2 工作树）：

- `attempt_id = "attempt:<session_id>:<turn_index>:<item_id>"`（PR2 `_attempt_id`）；
- 事务 A 写 `RESPONSE_SUBMITTED`（`evt.responsesubmitted.<attempt_id>`）+ `ASSESSMENT_PREPARED`（`evt.assessmentprepared.<attempt_id>`），payload 含 `attempt_id/learner_id/session_id/item_id/turn_index/result_id/response_digest/canonical_response/session_version`；
- 事务 B 写终态 `ASSESSED`/`MASTERY_UPDATED`（或 `ERROR`），`_terminal_result` 读回。

B-PR3 的绑定规则（**同一 attempt 重试必须命中同一 PREPARED/terminal**）：

```text
attempt_scope = (learner_id, session_id, item_id, turn_id)          # 不含 result_id/digest
attempt_id_v1 = "attempt.v1." + sha256(canonical_json(attempt_scope))[:32]
```

- 同一 `attempt_scope` 重试：必须复用同一 `attempt_id` → 命中同一 `ASSESSMENT_PREPARED` 或同一 TERMINAL；若 PREPARED 存在而 TERMINAL 缺失 → 走 PR2 `recover_session` 语义（re-score 后提交终态），**不得**把它当作新 attempt 再次写事件。
- 同一 `attempt_scope` 但 `result_id` 或 `request_digest` 不同 → `IDEMPOTENCY_CONFLICT`（reason `ATTEMPT_PAYLOAD_MISMATCH`），在评分/写事件前拒绝。
- `attempt_id` 与 `result_id` 的关系：attempt 是"教学轮次"的身份，result 是该 attempt 的评分产物身份；一个 attempt 恰好一个 terminal result_id。**这是"同一教学轮次只能沉淀一份 observed evidence"的结构性保证。**
- PREPARED payload 必须携带 `scope`（见 §4.4）；`learner_id` 必须等于 session owner（PR2 已校验事件 learner/session 与 commit 参数一致，PR3 增加 scope owner 校验）。
- PR2 的 `session_version`（session 内容 digest CAS）与 attempt 正交：attempt 防重复评分，session_version 防并发丢更新；PR3 同时使用（§5.6）。

### 2.5 不变量（PR3 实现必须保持）

1. **I1 幂等读**：同 scope + 同 digest + TERMINAL → 返回同一 result，零事件、零 snapshot/session 写入。
2. **I2 冲突不返回旧成绩**：同 scope + 不同 digest/item，或跨 scope 同 result_id → `IDEMPOTENCY_CONFLICT`，不返回任何已存 result，不写状态。
3. **I3 跨租户不可读**：任何返回给调用方的 `AssessmentResult.learner_id` 必须等于请求 scope 的 learner_id；错误 details 不含他人 learner/session/item/response。
4. **I4 单轮次单证据**：同一 `attempt_scope` 至多一个 terminal `ASSESSED`/`ERROR`，至多一次 mastery 变更。
5. **I5 历史只读**：`history_events` 已有行不被更新/删除/重写；新增仅 append；rebuild/replay 对旧/新事件的输出一致（除新增 payload 字段可被忽略）。
6. **I6 失败关闭**：repository 不支持 scoped API、legacy scope 不可证明、result_id 非法、并发冲突未收敛时，宁可报稳定错误，不得静默返回猜测结果。

---

## 3. 冲突矩阵与行为表

表列含义：`返回旧成绩` = 是否把已存 `AssessmentResult` 返回；`写事件/快照` = 是否产生新的历史事件或 snapshot/session 写入；`状态` = 现有 result/session/snapshot 是否变化。

### 3.1 主矩阵

| # | 情形（请求 scope 相对已存记录） | 行为 | 返回旧成绩 | 写事件/状态 | 错误码 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| M1 | 同 scope、同 digest、已 TERMINAL | 直接返回已存 result | 是（本 scope 的） | 否 | — | 标准重试；零附加事件（I1） |
| M2 | 同 scope、同 digest、仅 PREPARED（无终态） | 继续/恢复 attempt：按 PR2 recovery re-score 后提交终态；返回终态 result | 否（提交后返回新终态；若并发下已终态则返回终态） | 提交一次终态 + 一次 snapshot/session | — | at-least-once scorer；成功后重试落到 M1 |
| M3 | 同 scope、同 result_id、不同 digest | 拒绝 | 否 | 否 | `IDEMPOTENCY_CONFLICT`（`REQUEST_DIGEST_MISMATCH`） | B3-02 核心 |
| M4 | 同 scope、同 result_id、不同 item_id | 拒绝 | 否 | 否 | `IDEMPOTENCY_CONFLICT`（`ITEM_MISMATCH`） | item 已绑定 scope |
| M5 | 同 learner、同 session、同 result_id、不同 turn_id（旧 turn 已消费） | 拒绝 | 否 | 否 | `IDEMPOTENCY_CONFLICT`（`TURN_MISMATCH`） | 每个 turn 一个提交 |
| M6 | 同 learner、同 session、同 result_id，但 request 目标 item 与当前 pending 不一致 | 拒绝 | 否 | 否 | `IDEMPOTENCY_CONFLICT`（`SESSION_STATE_MISMATCH`）或既有 `ConflictError`（无 pending） | 先 scope 后状态；都 fail-closed |
| M7 | 跨 learner，同 result_id（任意 digest/item） | 拒绝 | **否（绝不返回他人结果）** | 否 | `IDEMPOTENCY_CONFLICT`（`RESULT_ID_SCOPE_MISMATCH`） | §3.3 裁决；详情不含他人数据 |
| M8 | 同 learner、跨 session，同 result_id | 拒绝 | 否 | 否 | `IDEMPOTENCY_CONFLICT`（`RESULT_ID_SCOPE_MISMATCH`） | 同上 |
| M9 | 不同 scope（不同 learner/session），content 相同但**重新生成** result_id | 视为各自独立 attempt（若各自 session 有 pending item） | 否 | 各自写入自己的事件/快照 | — | 两个不同 logical submission；不是 duplicate |
| M10 | 同 learner、同 session、同 item、**已消费 turn**，content 相同但显式 result_id 不同 | 拒绝（不做 content 隐式去重） | 否 | 否 | `IDEMPOTENCY_CONFLICT`（`TURN_ALREADY_ASSESSED`） | 裁决见 §3.2 |
| M11 | 同 learner、同 session、同 item、**新 turn**（合法重复练习），content 相同 | 允许新 attempt（新 turn/result_id） | 否 | 写入新证据 | — | 重复练习是教学场景，必须允许 |
| M12 | legacy 全局 id 重放：同 learner+session+item+result_id，scope 可证明，digest 前缀匹配 | 显式 legacy 适配：返回旧 result | 是（本 learner 的 legacy 结果） | 否 | — | §4.5；`legacy_adopted` 审计标志 |
| M13 | legacy 全局 id 重放：learner/session/item 任一不匹配 | 拒绝 | 否 | 否 | `IDEMPOTENCY_CONFLICT`（`LEGACY_SCOPE_MISMATCH`） | 旧事件仍可读，但不得跨 scope |
| M14 | legacy 事件存在但 digest 无法证明（无 RESPONSE_SUBMITTED / 前缀无从比较） | 默认拒绝（fail-closed）；仅显式 `allow_legacy_unknown_digest=True`（受控迁移工具）才适配 | 条件性 | 否 | `IDEMPOTENCY_CONFLICT`（`LEGACY_DIGEST_UNPROVEN`）或 `LEGACY_IDEMPOTENCY_UNSUPPORTED` | 不猜测 |
| M15 | result_id 非法（空/超长/路径字符/控制字符） | 拒绝 | 否 | 否 | `ValidationError`（`INVALID_RESULT_ID`） | 在任何查找/评分前 |
| M16 | 并发双提交同 scope（同 digest） | 收敛：一个写入终态，另一个读到同 scope 后返回同一 result（或收敛重试） | 是（最终） | 至多一次终态+一次状态 | 竞争期可能 `SESSION_VERSION_CONFLICT`/`DUPLICATE_SCOPE`，但必须可安全重试并收敛 | §5.6 |
| M17 | 并发双提交同 result_id、不同 scope | 一个成功；另一个 `IDEMPOTENCY_CONFLICT`（`RESULT_ID_SCOPE_MISMATCH`） | 否 | 至多一个 scope 写入 | 见上 | 依靠 `result_scopes` 唯一键 + CAS |
| M18 | repo 不支持 scoped API 且 caller 尝试显式 result_id 重试 | 拒绝（fail-closed） | 否 | 否 | `UnsupportedOperationError`（`IDEMPOTENCY_UNSUPPORTED`） | 不得回退到全局 `get_event` |

> 错误码统一用 `ConflictError(code="IDEMPOTENCY_CONFLICT", details={"reason": <上图枚举>, "requested_scope": {...}}) `；`details` 只含**请求方**自己的 scope 与 policy 版本，不含他人数据（§6 T-7 扫描验证）。`INVALID_RESULT_ID` 用 `ValidationError`；能力缺失用 `UnsupportedOperationError`。既有 `ConflictError`/`SESSION_VERSION_CONFLICT`/`DUPLICATE_EVENT`/`EVENT_SEQ_CONFLICT` 语义不改，只新增专用 code。
>
> **实现澄清（P2-1）**：M16 的"收敛"即验收语义——同 scope、同 payload 的并发双提交是 **convergent retry**：两个调用最终都返回**同一份**已存 result，DB 恰好一份终态/一次 mastery；只有不同 payload 或跨 scope 才是 explicit `IDEMPOTENCY_CONFLICT`。测试名：`test_concurrent_same_scope_same_response_converges_to_one_result`。
>
> **实现澄清（P2-2）**：同一 scope 的 TERMINAL 快速查找在 `PAUSED`/`COMPLETE` phase 门禁**之前**执行，因此"提交成功但客户端丢响应、随后 session 完成/暂停"的同 token 重试仍返回已存 result（零写入）；非本 scope 调用仍被 phase 门禁拒绝。

### 3.2 裁决：CONTENT 相同但显式 result_id 不同

**裁决：按"不同幂等令牌"处理，不按 content 隐式去重。**

- 若两个 result_id 对应**同一个已消费 turn**（M10）：拒绝 `IDEMPOTENCY_CONFLICT/TURN_ALREADY_ASSESSED`。理由：
  1. `result_id` 是调用方声明的"这次逻辑提交"的身份；换 id 意味着调用方认为这是另一次提交，而状态机（一 turn 一次提交）无法承载第二次评分；
  2. 用 content 匹配做隐式去重会把"客户端丢失 result_id 的 bug"伪装成幂等成功，且 content 不是可靠身份（同答案可能对应不同题目/上下文/时间）；
  3. 拒绝比静默返回旧成绩更可解释，且不会造成重复 mastery 证据。
- 若两个 result_id 对应**不同 scope/turn/session**（M9/M11）：合法，各自独立 attempt 与证据（这是正常练习/不同会话）。
- 客户端若需要"安全重试"，必须复用同一 `result_id`（默认路径下由确定性默认 id 保证；显式路径下由调用方负责）。

### 3.3 裁决：不同 learner/session 使用同一 result_id

**裁决：`IDEMPOTENCY_CONFLICT`（`RESULT_ID_SCOPE_MISMATCH`）；绝不返回对方结果、绝不写入任何状态。**

理由：
1. 严格保证 I3（跨租户不可读）；探针已证明当前实现会返回对方结果，必须先堵死；
2. `result_id` 在产品语义上作为调用方幂等令牌，全局冲突会显式暴露客户端 bug/攻击面（存在性预言机风险低：只暴露"该 token 被用过"，不含任何 owner 数据；见 §8 残余风险）；
3. 与 PR2 未提交实现的方向一致（`engine.py`（PR2）`_lookup_result_for_retry` 已按 learner/item/session 抛 `IDEMPOTENCY_CONFLICT`），减少合并冲突；
4. 备选"每 scope 各自允许同 token"（见 §4.2 方案 B）会消除存在性预言机，但需要 v2 事件 id 命名空间与迁移，代价更大；列为未来可选项，需 Lead 决策（§8 Q2）。

不变量：发生该冲突时，`learner B` 的 snapshot/session/事件与 `learner A` 的所有行都保持不变；错误对象与日志中不得出现 A 的 learner/session/item/result 内容。

### 3.4 旧式全局 result_id 的重放/迁移

- **迁移（读旧数据）**：不做"重写旧事件"；v1→v2 schema 迁移只新增 `result_scopes` 索引行（可 lazy/幂等），历史 `history_events` 行字节不变（§4.5）。
- **重放（旧 event id 命中）**：只允许经 **legacy 适配器**，且必须满足 learner+session+item+result_id 匹配 + digest 前缀可证明（M12）；否则 M13/M14 fail-closed。
- **新写入**：一律经 scoped 写路径（`result_scopes` + 事务）；不得再写"仅全局 result_id 可定位"的歧义记录。
- 旧 `result:<session>:<turn>:<item>:<digest16>` 格式的默认 id 只作为历史数据存在；新默认 id 使用 §2.3 的 v1 格式，避免 `<session_id>` 中特殊字符进入事件 id 语义（现有 session id 由调用方/默认生成，变更需兼容旧数据读取）。

---

## 4. 事件 id 作用域化与历史兼容（add-only）

### 4.1 问题本质

`evt.assessed.<result_id>` / `evt.mastery.<result_id>` 以 `result_id` 作为全局主键：同一 `result_id` 在不同 learner/session 下会生成**同一** `event_id`，从而 (a) 后来者被 `append_event` 静默 `False`（证据丢失）；(b) 先前者可被任意 scope 通过全局 `get_event` 读到（跨读取）。同时 `evt.assessmentprepared.<attempt_id>`（PR2）与 `RESPONSE_SUBMITTED` 也是全局 key——`attempt_id` 含 session id，冲突概率低但同样依赖 session 全局唯一性。

### 4.2 方案对比

| 方案 | 做法 | 优点 | 缺点/风险 | 选择 |
| --- | --- | --- | --- | --- |
| **A. payload scope + 索引表 + learner 过滤读（推荐）** | event id 保持 `evt.assessed.<result_id>` 形状（作为全局"result_id 唯一"守卫）；新增 `result_scopes` 表唯一键 `result_id`；所有结果读取走 `find_result_in_scope(scope)` / `get_event_for_learner`；scope mismatch → conflict | 历史事件零重写；PR2 既有事件 id 不变；rebuild/replay/导出不变；实现面积小；与"严格冲突策略"一致 | 全局 PK 仍是物理键，若未来要"跨 scope 复用 result_id"需方案 B；冲突暴露 token 已用（低风险存在性预言机） | ✅ 本次（B-PR3 v1） |
| **B. v2 scoped event id + 双读适配** | 新写入 `evt.assessed.v2.<sha256(scope)[:32]>`（含 learner/session/item/turn/result_id），同时保留 legacy 双读与 adoption | 跨 scope 同 token 可共存；无存在性预言机；租户键物理隔离 | 事件 id 变化影响导出/哈希/审计与 PR2 PREPARED 命名；需要双读/迁移/adoption 全链路测试；历史与新增并存复杂度高 | 未来可选（需 Lead 决策，§8 Q2） |
| C. 仅按 learner 过滤读，保留全局 PK | 读路径 `WHERE event_id=? AND learner_id=?` | 最小改动 | 写入仍会因全局 PK 静默丢失证据（B3-01 的"数据丢失"一半未解决）；并发下不可解释 | ❌ 不充分 |

**结论**：采用 A。关键点：**隔离由"读/写都经过 scope 校验的 API"保证，而不是靠 event id 字符串命名空间**；`event_id` 保持历史形状以最小化兼容成本。A 已足以满足 B3-01/B3-02 的"不可读出他人结果、同 key 不同 payload 必须冲突"。

### 4.3 方案 A 的数据结构

新增表（schema v2，**add-only**，`CREATE TABLE IF NOT EXISTS`；不修改 `history_events`）：

```sql
CREATE TABLE IF NOT EXISTS result_scopes (
    result_id          TEXT PRIMARY KEY,            -- 全局唯一令牌（严格冲突策略的守卫）
    scope_version      TEXT NOT NULL,               -- "m1b.scope.v1"
    learner_id         TEXT NOT NULL,
    session_id         TEXT NOT NULL,
    item_id            TEXT NOT NULL,
    turn_id            INTEGER NOT NULL CHECK (turn_id >= 0),
    request_digest     TEXT NOT NULL,               -- 64 hex sha256(canonical(response))
    status             TEXT NOT NULL CHECK (status IN ('PREPARED','TERMINAL')),
    terminal_event_id  TEXT,                        -- TERMINAL 时必填
    terminal_event_type TEXT,                       -- 'ASSESSED' | 'ERROR'
    attempt_id         TEXT NOT NULL,
    origin             TEXT NOT NULL DEFAULT 'v1',  -- 'v1' 新写入 | 'legacy' 迁移回填
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_result_scopes_scope
    ON result_scopes(learner_id, session_id, item_id, turn_id);
CREATE INDEX IF NOT EXISTS idx_result_scopes_session
    ON result_scopes(learner_id, session_id, status);
```

- **写**：事务 A（PREPARED）`INSERT INTO result_scopes`（若已存在则按 §5.6 冲突/恢复逻辑处理）；事务 B 更新同一行 `status='TERMINAL', terminal_event_id=..., updated_at=...`，并写终态 `history_events`；两者与 snapshot/session 在同一 `commit_teaching_turn` 事务内（PR2 扩展，见 §5.5）。
- **读**：`find_result_in_scope(scope)` 以**完整 scope 五元组 + request_digest** 查询（digest 用于区分终态后不同请求）；命中 TERMINAL 才返回终态事件 payload 中的 `result`，且返回前再次校验 `AssessmentResult.learner_id == scope.learner_id`、`item_id == scope.item_id`，否则 `ValidationError/IDEMPOTENCY_CONFLICT`。
- **冲突探测**：`find_result_scope_owner(result_id)` 只返回元数据（`learner_id/session_id/item_id/turn_id/request_digest/status`），**不返回 result payload**；调用方比较该元数据与请求 scope，决定 `RESULT_ID_SCOPE_MISMATCH` / `REQUEST_DIGEST_MISMATCH` / `TURN_MISMATCH`；错误 details 只放请求方 scope + reason（不写 owner 字段）。
- **保留** `history_events.event_id` 全局主键作为写入兜底：即便 scope 表被绕过，同一 result_id 的第二条终态事件会触发 `DUPLICATE_EVENT`，映射为 `IDEMPOTENCY_CONFLICT`（绝不返回旧结果）。
- **不变量**：`result_scopes.result_id` 全局唯一 ⇒ 与现有 `evt.assessed.<result_id>` 全局 PK 一致；两者在同一事务内保持一致，任一失败 rollback。

### 4.4 事件 payload 的 scope（additive）

新写入的 `ASSESSED` / `MASTERY_UPDATED` / `ERROR` / `ASSESSMENT_PREPARED` / `RESPONSE_SUBMITTED` payload 增加（**追加字段，不删/不改现有字段**）：

```json
{
  "scope": {
    "scope_version": "m1b.scope.v1",
    "learner_id": "...", "session_id": "...", "item_id": "...",
    "turn_id": 0, "result_id": "...", "request_digest": "<64 hex>"
  }
}
```

- 旧事件没有该字段：读取方必须容忍缺失（`payload.get("scope")` 为 `None`），并走 legacy 适配（§4.5）。
- `AssessmentResult` 冻结节不增加字段（避免 schema/序列化变更与隐藏材料边界再讨论）；scope 属于事件/索引层元数据。
- `history.rebuild_state`/`applied_result_ids` 现有逻辑只读 `payload.result_id/result/item`，不受新增字段影响；新字段可被忽略 → rebuild/replay 兼容。

### 4.5 历史事件、rebuild/replay 与已提交 M1-A 数据兼容

**原则**：add-only；旧事件可读；不重写旧事件；不要求数据库整体重建。

1. **schema 迁移 v1→v2**：打开旧库时（`schema_meta.version == 1`）在迁移事务中 `CREATE TABLE IF NOT EXISTS result_scopes` + 索引，版本写 2；**只新增表**，不修改 `history_events`/`snapshots`/`sessions` 行。迁移幂等（重复打开无事发生）；迁移失败整体 rollback、旧版本仍可读（fail-closed，不半迁移）。
2. **legacy 回填（索引，不重写事件）**：迁移时（或 lazy 首次查询时）扫描该库所有 `ASSESSED`/`ERROR` 事件，为每个事件写入 `origin='legacy'` 的 scope 行：
   - `learner_id = event.learner_id`；`session_id = event.session_id`；`item_id/result_id` 取自 payload；
   - `turn_id`：若同 learner/session 的 `RESPONSE_SUBMITTED` 事件 payload 含 `result_id` 且能唯一匹配 → 取该 payload 的 `attempt`；否则 `turn_id = -1`（UNKNOWN，表允许 `-1` 仅 legacy 行；v1 行禁止）；
   - `request_digest`：若找到对应 `RESPONSE_SUBMITTED` 的 16-hex `response_digest` → 存 `legacy:<16hex>` 标记（非 64-hex 时单独列/前缀标记），否则 `legacy:unproven`；
   - `status='TERMINAL'`、`terminal_event_id=event.event_id`、`origin='legacy'`；
   - `INSERT OR IGNORE` 幂等；**不删除、不更新已有 v1 行**。
3. **legacy 读取（受控适配）**：`find_result_in_scope` 在 v1 行 miss 后，查询 legacy 行但必须满足 learner+session+item+result_id 全等；digest 比较：
   - 若 legacy request_digest 可映射（`legacy:<16hex>`）→ 与当前 `sha256(canonical(response))[:16]` 比较，相等才返回；不等 → `IDEMPOTENCY_CONFLICT/REQUEST_DIGEST_MISMATCH`；
   - 若 `legacy:unproven` → 默认 `IDEMPOTENCY_CONFLICT/LEGACY_DIGEST_UNPROVEN`；只有显式迁移/受控工具参数 `allow_legacy_unknown_digest=True` 才返回旧结果并记录 audit（不用于普通提交路径）。
   - legacy 结果返回前同样校验 `AssessmentResult.learner_id == scope.learner_id`（防 payload 被篡改）。
4. **rebuild/replay**：`LearningHistory.rebuild_state`/`verify_rebuild` 按 `list_events(learner)` + payload 工作，事件 id 形状不变、payload 追加字段被忽略 → 旧库与新库均通过；`applied_result_ids` 仍按 payload result_id 去重（同 learner 内）。跨 learner 隔离由事件查询 `list_events(learner_id)` 本身保证。
5. **证据导出/哈希**：demo/CLI JSONL 与新事件 payload 会多出 `scope` 字段 → 新基线会变化，这是**预期的 add-only 变化**；M1-A 冻结基线（`docs/m1_teacher` 证据、旧 review 报告）保持不变，不被重算/重写；PR3 报告需注明"新基线 vs 历史基线"。
6. **默认 result_id 旧格式**：历史事件可能含 `result:<session>:<turn>:<item>:<digest16>`；新默认 id 用 §2.3 的 `result.v1.<hash>`；legacy 适配不依赖 id 格式，只依赖 scope 行/payload。
7. **迁移测试要求**（PR3 实现时）：由 v1 fixture DB（含多 learner、跨 session、错误/EVAL_ERROR、prepared 缺终端）→ 打开升级 → 断言：行数不变、旧事件字节与 `event_id` 不变、rebuild/verify_rebuild 全真、legacy 重放同 learner 成功 / 跨 learner 拒绝、重复迁移幂等、旧代码读取新库失败关闭（版本更高则 fail-closed）。

### 4.6 为什么不直接改成 v2 scoped event id（记录否决理由）

- PR2 已在未提交实现里围绕 `evt.assessmentprepared.<attempt_id>`/`evt.assessed.<result_id>` 构建了 recovery/failpoint/tests；立即改 id 命名空间会与 PR2 冲突并扩大合并面。
- 严格冲突策略下，`result_id` 全局唯一本身是可接受的产品语义；隔离需求由读/写 API 的 scope 校验满足，无需物理命名空间。
- v2 scoped id 留作方案 B；若 Lead 决定"允许跨 scope 复用同 token"（§8 Q2），再做兼容迁移并作为独立 PR。

---

## 5. API 变更点（PR3 实现清单，本 PR 不实现）

### 5.1 错误类型与细节（contracts/errors.py 说明性变更）

- 新增文档化错误码常量（不改 `ConflictError.code` 默认值 `"CONFLICT"`，沿用现有 `M1AError(code=...)` override 能力）：
  - `IDEMPOTENCY_CONFLICT`（`ConflictError`）——同一 scope 冲突或跨 scope 同 token；
  - `INVALID_RESULT_ID`（`ValidationError`）；
  - `IDEMPOTENCY_UNSUPPORTED`（`UnsupportedOperationError`，repository 能力缺失）。
- `details` schema（**不得包含他人数据**）：
  ```json
  {"reason": "REQUEST_DIGEST_MISMATCH | ITEM_MISMATCH | TURN_MISMATCH | TURN_ALREADY_ASSESSED |
              RESULT_ID_SCOPE_MISMATCH | LEGACY_SCOPE_MISMATCH | LEGACY_DIGEST_UNPROVEN |
              ATTEMPT_PAYLOAD_MISMATCH | CONCURRENT_RETRY_EXHAUSTED",
   "requested_scope": {"learner_id": "...", "session_id": "...", "item_id": "...",
                       "turn_id": 0, "result_id": "..."},
   "policy_version": "m1b.idempotency.v1"}
  ```
  禁列：他人 learner_id/session_id/item_id/result_id/response/hash、完整他人 scope 行、任何可反推的他人 PII/内容（本项目无真实 PII，但规则适用于合成数据）。
- `M1AError.to_dict()` 现有输出（code/message/details）保持；新增测试扫描 message/details/导出 JSON，断言不含 foreign 标识（§6 T-7）。

### 5.2 新增纯函数模块 `m1_teacher/session/idempotency.py`（实现 PR 创建）

```python
SCOPE_VERSION = "m1b.scope.v1"
IDEMPOTENCY_POLICY_VERSION = "m1b.idempotency.v1"

def validate_result_id(result_id: str) -> str: ...            # 非法 -> ValidationError(INVALID_RESULT_ID)
def request_digest(response: str | dict) -> str: ...          # 64-hex, new compact projection
def legacy_request_digest(response: str | dict) -> str: ...   # 64-hex, pre-PR3 default-separator projection (legacy only)
def make_scope(learner_id, session_id, item_id, turn_id, result_id) -> ResultScope: ...
def default_result_id(learner_id, session_id, item_id, turn_id, response) -> str
def default_attempt_id(learner_id, session_id, item_id, turn_id) -> str
def scope_digest(scope: ResultScope) -> str                    # 若未来方案 B/索引使用
```

`ResultScope`/`ScopedTerminal` 为普通 frozen dataclass（放本模块或 `contracts/idempotency.py`，**不修改** `contracts/types.py` 的冻结记录）。

### 5.3 Repository 扩展（additive；协议可选实现）

在 `m1_teacher/contracts/repository.py`（或新 `m1_teacher/learner/idempotency.py`）增加文档化 Protocol `ScopedIdempotencyRepository`（不修改既有 `LearnerRepository` 协议，保持协议实现向后兼容）：

```python
class ScopedIdempotencyRepository(Protocol):
    def supports_scoped_idempotency(self) -> bool: ...
    def find_result_in_scope(self, scope: ResultScope) -> AssessmentResult | None: ...
    def find_scope_owner(self, result_id: str) -> ScopeMetadata | None: ...   # metadata only, no result payload
    def get_event_for_learner(self, learner_id: str, event_id: str) -> HistoryEvent | None: ...
```

`SqliteRepository` 增加实现（schema v2 + 上述表）；`commit_teaching_turn`（PR2）扩展可选参数：

```python
def commit_teaching_turn(
    self, *, learner_id, session_id, expected_session_version,
    events, snapshot=None, next_session, goal=None,
    scope: ResultScopeWrite | None = None,          # 新增；None 时保持 PR2 旧行为
) -> list[bool]
```

- `scope.action ∈ {"PREPARE", "TERMINAL"}`（或 `status`），事务内：
  - `PREPARE`：`INSERT INTO result_scopes(...)`；已存在 → 若同 scope 同 digest 继续（幂等）否则 `ConflictError(IDEMPOTENCY_CONFLICT)`；不同 scope 同 result_id → `ConflictError(IDEMPOTENCY_CONFLICT/RESULT_ID_SCOPE_MISMATCH)`；
  - `TERMINAL`：`UPDATE ... WHERE result_id=? AND status='PREPARED' AND request_digest=?`；影响行数 ≠ 1 → conflict（含并发/恢复语义）。
- `get_event(event_id)` 保留（底层/诊断用），但 **engine 与 history 的结果读取路径不得再使用它**；`get_event_for_learner` 用于 legacy 适配。
- 无该扩展的 repository：engine `supports_scoped_idempotency == False` 时不提供强幂等保证；显式 `result_id` 重试/提交一律 `IDEMPOTENCY_UNSUPPORTED`（除首次尝试外无法判别），文档化降级；默认 result_id 路径仍要求扩展，否则同样拒绝并提示（fail-closed）。

### 5.4 Engine（`submit_response` 目标流程）

以 PR2 事务化为前提（PR2 合并后），目标流程（伪代码）：

```text
submit_response(session_id, item_id, response, *, result_id=None, caller_learner_id=None):
  state = load_session(session_id)
  # 0) 可选受信身份断言（不做 auth，只拒绝明显不匹配）
  if caller_learner_id is not None and caller_learner_id != state.learner_id:
      raise ConflictError(code="SCOPE_OWNERSHIP_MISMATCH")
  # 1) ID/参数校验（在任何查找/评分前）
  validate item/pending/phase (既有规则)
  validate_result_id(result_id) if explicit
  turn_id = state.turn_index
  digest = request_digest(response)
  attempt_id = default_attempt_id(state.learner_id, session_id, item_id, turn_id)
  # 2) 显式 result_id：scoped 快速路径
  if result_id is not None:
      scope = make_scope(state.learner_id, session_id, item_id, turn_id, result_id)
      found = repo.find_result_in_scope(scope)
      if found: return found                      # I1；绝不全局查
      owner = repo.find_scope_owner(result_id)    # metadata only
      if owner: raise IDEMPOTENCY_CONFLICT(...)   # 跨 scope / M3-M10
  # 3) attempt 路径：PREPARED/TERMINAL 绑定
  prepared = repo.get_event_for_learner(learner, prepared_event_id(attempt_id))
  if prepared:
      validate prepared scope (learner/session/item/turn/digest/result_id)
      terminal = repo.find_result_in_scope(prepared.scope)
      if terminal: return terminal
      # 否则进入 recovery/继续 commit（PR2）
  else:
      result_id_final = explicit or default_result_id(...)
      scope = make_scope(..., result_id_final)
      # 事务 A：RESPONSE_SUBMITTED + ASSESSMENT_PREPARED + result_scopes(PREPARED)
  # 4) 事务外 scoring（PR2 语义，at-least-once）
  result = score_safely(...)
  # 5) 事务 B：终态事件 + snapshot + session + result_scopes(TERMINAL)（CAS）
  return commit_result_turn(...)   # 冲突 DUPLICATE_EVENT -> 必须 scoped 复核，绝不无条件返回 terminal
```

需改动的既有函数（base line 供对照）：`_find_existing_result` 删除/私有化为 `_find_existing_result_in_scope`（`engine.py:833-850`）；显式/default/score 后三处调用（`:516, :531, :537`）全部替换；`_default_attempt_result_id`（`:783-790`）改为 §2.3 版本；`_handle_eval_error`（`:855-895`）的 `evt.evalerror.<result_id>` 写入与 scope 行/终态绑定；`_handle_observed_result`（`:938-...`）经 `apply_assessment`/事务 B 写 scope；`LearningHistory.apply_assessment`（`history.py:210-330`）的 `get_event(assessed_event_id(...))`（`:266`）改为 scoped 查找；`assessed_event_id`/`mastery_updated_event_id`（`history.py:109-118`）保留旧函数（历史/测试用）并新增 scope-aware 版本；`known_result_ids`（`:374`）语义不变（per learner）。

> **实现状态（评审 P1-2）**：`LearningHistory.apply_assessment` 的重复判定已改为 learner-filtered/scoped 查找（`get_event_for_learner` + `find_scope_owner` 元数据）：同一 learner+session+item 的重复 apply 仍幂等；命中其他 learner/session/item 或 engine 管理的 PREPARED attempt 时抛稳定 `IDEMPOTENCY_CONFLICT`（不静默丢弃、不返回他人成绩）；无 scoped 扩展的协议-only repo 保留文档化的 legacy fallback，但异主事件仍冲突。
**PR2 未提交实现（`/root/m1b/pr2`）需同步加固的点**：`_terminal_result`（约 `:1177`）仍全局读；`_lookup_result_for_retry`（约 `:1193`）先全局读并解析他人 payload 再抛冲突；`_commit_result_turn` 的 `DUPLICATE_EVENT` 捕获（约 `:902-929`）**无条件返回全局 terminal**（并发窗口可能返回他人结果）→ 必须改为 scoped 复核；legacy fallback `_find_existing_result`（约 `:1772`）仍全局；`history.assessment_event_drafts`（约 `:248`）仍产出 legacy id（PR3 可保持 id 形状，但 scope 写入走事务 B）。合并顺序建议：PR2 先合并/冻结，PR3 rebase 后在这些位置替换为 scoped API，避免双改冲突。

### 5.5 与 PR2 `commit_teaching_turn` / session_version CAS 的关系

- **幂等快速路径在事务外**：`find_result_in_scope` 是只读查询，不占写锁；不得把外部 scorer 放进任何事务（PR2 已如此设计）。
- **权威判定在事务内**：`result_scopes` 唯一约束（result_id PK + 状态 CAS）+ `session_version` CAS + 终态 `event_id` 全局唯一三者共同兜底；事务内出现任何冲突 → rollback（不写事件/snapshot/session）。
- **并发同 scope**：两个请求都可能通过事务外快速路径（尚无记录），随后事务 A 只允许一个 `INSERT result_scopes` 成功；失败者在事务后重读 `find_result_in_scope`：
  - 同 digest 且 TERMINAL → 返回同一结果（M16 收敛）；
  - 同 digest 且 PREPARED → 走恢复/继续提交（PR2 `recover_session` 语义），不重复评分入账；
  - 不同 digest → `IDEMPOTENCY_CONFLICT`。
- **并发不同 scope 同 result_id**：`result_scopes.result_id` PK 保证至多一个 scope 写入；失败者 `find_scope_owner` 得元数据（无 payload）→ `RESULT_ID_SCOPE_MISMATCH`；不得返回对方结果。
- **恢复（PR2）**：`recover_session` 对每个 PREPARED attempt 重新评分前，必须用 `find_result_in_scope` 确认该 scope 未被其他 writer 终结；终结后重试走 M1；恢复不得产生第二条终态或第二次 mastery。
- **exactly-once 主张边界**：状态应用 exactly-once（由唯一约束/CAS 保证），scorer 调用是 at-least-once（崩溃恢复可能重调）；**不**作"远程 exactly-once 评分"承诺（与 PR2 文档一致）。

### 5.6 兼容与降级

- 老版 repository（无 `ScopedIdempotencyRepository`）：engine 检测 `supports_scoped_idempotency` 为假 → `submit_response` 显式 result_id 路径 fail closed（`IDEMPOTENCY_UNSUPPORTED`）；新写入仍可走默认路径但同样要求能力（否则拒绝并提示升级）；文档化 M1-A legacy 模式仅用于只读/演示，不承诺幂等。
- 新 engine + 旧 DB（schema v1）：打开时自动 v2 迁移（§4.5）；迁移前只读预览可由 CLI `--check-migration` 提供（PR5 可选）。
- 旧 engine + 新 DB（schema v2）：`schema_meta.version` 高于支持版本 → fail-closed（现有 `SqliteRepository` 行为），不猜测。
- legacy 投影（P1-1）：旧库的结构化 response 一律用 `legacy_request_digest` 比较；新写入仍用 compact 投影。测试使用由 base `4706250` 真实 engine 生成并提交的 v1 fixture（`fixtures/m1_teacher/migration/pr3_v1_structured_legacy.sqlite`），不是"新 engine 生成后降级"。
- legacy event-log fallback（P2-4）：当 `result_scopes` 索引行缺失时，fallback 除 learner/session/item/result_id/digest 外还校验 attempt turn（允许 `-1`/当前 turn/刚消费的前一 turn），旧 turn 重用 token 仍冲突。
- schema 防御（P2-5）：`result_scopes` 增加表级 `CHECK (origin = 'legacy' OR turn_index >= 0)`；读取 `_scope_metadata` 亦做同样应用层校验（兼容早期 v2 表未带新 CHECK 的情况）。

---

## 6. 威胁 / 负例矩阵（B-Q3 / B3-01 / B3-02）

所有用例只使用 synthetic learner/session/item/response id；不含真实 PII/Key/网络。证据类别：实现前 **设计期望**；实现后 **DETERMINISTIC/NEGATIVE**（独立 Reviewer 复跑）。不得把本表当 PASS。

| ID | 用例 | 注入/前提 | 期望行为（PR3 目标） | 不得发生 | 验证方式（PR3 测试） |
| --- | --- | --- | --- | --- | --- |
| T-1（B-Q3/B3-01） | Student A result_id 在 B 活动 session 复用 | A 提交并 commit；B 新 session 使用同 `result_id` | `IDEMPOTENCY_CONFLICT`（`RESULT_ID_SCOPE_MISMATCH`）；B 的 snapshot/事件/session 均不变；错误 details 无 A 标识 | 返回 A 的 `AssessmentResult`；写 B 事件/推进 B session | `test_scoped_idempotency.py::test_cross_learner_result_id_is_never_read_or_written` + 捕获异常 details 扫描 |
| T-2（B3-01） | 跨 session 同 id（同 learner） | A session1 提交；A session2 复用同 id | 同 T-1 冲突 | 返回 session1 结果；写 session2 状态 | `test_cross_session_result_id_conflict` |
| T-3（B3-02） | 同 scope 同 result_id、不同 response | 同 session/item/turn，response 改文本/结构 | `IDEMPOTENCY_CONFLICT`（`REQUEST_DIGEST_MISMATCH`）；不返回旧成绩；不改状态 | 静默返回首次结果（当前 test_session_engine:420 语义需更新） | `test_same_key_different_response_conflicts`（更新既有用例） |
| T-4（B3-02） | 同 scope 同 result_id、不同 item | 已消费 turn 后改用另一 item | `IDEMPOTENCY_CONFLICT`（`ITEM_MISMATCH`/`SESSION_STATE_MISMATCH`） | 返回旧 item 结果 | `test_same_key_different_item_conflicts` |
| T-5（B-Q3） | 异常重试/重放 | scorer 抛错 → `EVAL_ERROR`；客户端重试同 result_id | 返回同一 `EVAL_ERROR` result、零附加事件；**不**绕过 pending/retry 状态机（不产生新终态/新 mastery） | 重复评分入账；跳过 session 推进 | `test_eval_error_retry_is_scoped_and_zero_extra_events` |
| T-6（B2-01 交叉） | 评分后崩溃、重启后重试 | PR2 failpoint（`M1B_CRASH_FAILPOINT`）在 A/B 写点 | 恢复后返回同一结果；事件仅一套；mastery 只应用一次；`verify_rebuild` 真 | 重复 mastery/双终态/返回旧结果而不修复 | 复用 PR2 `test_crash_recovery.py` + scope 断言 |
| T-7（B3-02） | 日志/错误 details 泄漏扫描 | 触发 M3-M10 各冲突 | 捕获返回 result、异常 `str/details/to_dict`、trace/日志、导出的 JSONL，断言不含 foreign learner/session/item/result_id/response 文本 | 任何 foreign 标识出现 | `test_conflict_errors_do_not_leak_foreign_scope`（扫描序列化输出） |
| T-8（B-Q3） | 伪造/篡改 result_id 含路径字符 | `../`, `/`, `\`, NUL, 超长, 空格, Unicode 控制符 | `ValidationError(INVALID_RESULT_ID)`；事件 id/payload 不含原始危险串（或按编码规则安全存放）；无文件系统操作 | 路径穿越/日志注入/超长键 | `test_invalid_result_ids_rejected_before_any_write` + fuzz 列表 |
| T-9（B3-01 交叉） | 并发同 key 双提交（同 scope，两线程/两进程） | 两个 threads/process 同时 submit 同 session/item/response | 至多一个终态事件、一次 mastery；两者最终得到同一 result 或一方稳定冲突（可重试收敛）；session_version/CAS 生效 | 双 mastery、双 ASSESSED、静默 last-write-wins | `test_concurrent_same_scope_converges_to_single_evidence`（真实线程 + WAL busy timeout；进程级可选） |
| T-10（B3-01） | 并发同 key、不同 learner | 两 learner 同时使用同 result_id | 一个成功，另一个 `RESULT_ID_SCOPE_MISMATCH`；无外读 | 两个 scope 均写成功且事件 id 冲突丢失 | `test_concurrent_cross_learner_result_id_single_winner` |
| T-11（迁移） | 旧式全局 id 重放 | v1 DB 含 legacy ASSESSED；同 learner 重试、跨 learner 重试 | 同 learner：legacy 适配返回旧结果（digest 可证明）且零写入；跨 learner：冲突不返回 | 重写旧事件；跨 learner 读取；把旧事件重复计数 | `test_result_scope_migration.py::test_legacy_replay_same_learner_total_and_cross_learner_denied` |
| T-12（迁移） | v1→v2 迁移幂等/字节不变 | 已有 v1 DB fixture（多 learner、跨 session、ERROR、pending/prepared） | schema v2；`history_events` 行数与 `event_id`/payload 字节不变；重复迁移幂等；rebuild 全真 | 迁移修改/删除历史行；重复插入索引行 | `test_migration_is_additive_and_idempotent` + 行/字节对比 |
| T-13（隐私/隔离） | 错误 details 构造 | 所有冲突类型参数化 | details 只含 `{reason, requested_scope, policy_version}`；requested_scope 只含请求方自己的值 | 含 owner 数据 | T-7 同族参数化 |
| T-14（隔离扫描） | 模块无全局结果读回退 | AST/文本扫描 `m1_teacher/session`、`m1_teacher/learner` | 结果读取路径不得直接调用 `repository.get_event(...)`（仅 legacy 适配器与诊断允许，且带 learner 参数）；无网络/M0 import | 新增全局读回退 | `test_no_unscoped_result_lookup_in_engine_source` |

补充 B-Q3 取证格式建议（实现 PR 交付时）：对每个 T 用例输出 `case_id, git_sha, command, exit_code, status, evidence_path, sha256, limitation` 的 `audit-index.json` 片段；原始证据只含 synthetic 数据。

---

## 7. PR3 测试矩阵与验收映射（实现阶段）

> 本文为设计；以下为**实现 PR 必须新增/更新的测试清单草案**。全部状态 `NOT_RUN`（本设计 PR 不新增/运行测试），不得伪称已实现。

### 7.1 新增/测试文件（草案）

| 测试文件 | 用例（草案名） | 覆盖 | 证据类别（实现后） |
| --- | --- | --- | --- |
| `tests/m1_teacher/test_scoped_idempotency.py` | `test_same_scope_same_digest_returns_same_result_zero_events`；`test_same_scope_different_digest_conflicts`；`test_same_scope_different_item_conflicts`；`test_cross_learner_result_id_is_never_read_or_written`；`test_cross_session_result_id_conflict`；`test_invalid_result_ids_rejected_before_any_write`；`test_turn_consumed_with_new_result_id_conflicts` | M1-M15；B3-01/02 | DETERMINISTIC + NEGATIVE |
| `tests/m1_teacher/test_multilearner_isolation.py` | `test_two_learners_same_result_token_isolated_results`；`test_two_learners_same_item_parallel_sessions_no_cross_snapshot`；`test_conflict_errors_do_not_leak_foreign_scope`；`test_result_json_never_contains_foreign_learner` | T-1/T-7/T-13；B3-01 | NEGATIVE + DETERMINISTIC |
| `tests/m1_teacher/test_result_scope_migration.py` | `test_migration_is_additive_and_idempotent`；`test_legacy_replay_same_learner_total_and_cross_learner_denied`；`test_rebuild_after_migration_is_true`；`test_legacy_unknown_digest_requires_explicit_opt_in` | M12-M14、T-11/T-12 | DETERMINISTIC |
| `tests/m1_teacher/test_concurrent_idempotency.py` | `test_concurrent_same_scope_converges_to_single_evidence`；`test_concurrent_cross_learner_result_id_single_winner`；`test_session_version_cas_blocks_lost_update` | M16/M17、T-9/T-10、B2-03 交叉 | CONCURRENCY/DETERMINISTIC |
| `tests/m1_teacher/test_no_unscoped_result_lookup.py` | `test_no_unscoped_result_lookup_in_engine_source` | T-14 | STATIC |
| 更新既有 | `tests/m1_teacher/test_session_engine.py::test_duplicate_submit_with_same_result_id_is_idempotent`（保持，同 digest 路径）；`test_e2e_resume_idempotency.py::test_duplicate_result_id_updates_mastery_once`（改为：同 response 重试 → 同结果；不同 response → conflict，拆成两个用例） | B3-02 语义变更显式化 | DETERMINISTIC |

> **实现落地（评审后）**：测试按 Lead 指定合并为 `tests/m1_teacher/test_scoped_idempotency.py`（31 个用例，含 P1-2/P2-2/P2-1）与 `tests/m1_teacher/test_scope_migration.py`（15 个用例，含 P1-1/P2-4/P2-5）；上面草案中的其余文件名不再单独创建，用例映射见实现报告 §5.2/§5.3 与 §8。

### 7.2 与证据矩阵映射

| 证据矩阵项 | 本设计对应 | 验收判据（实现后由 Reviewer 复核） |
| --- | --- | --- |
| B3-01 Scoped result ID（NEGATIVE） | §2、§3.1 M7/M8、T-1/T-2/T-10 | 对跨 learner/session/item/turn 同 key 请求，任何 API/日志/错误都不返回他人 `AssessmentResult`；目标 learner 状态不变；测试命令 raw 输出与 reporter 独立复跑 |
| B3-02 Same key different payload（NEGATIVE） | §3.1 M3-M5/M10、T-3/T-4 | 稳定 `IDEMPOTENCY_CONFLICT`（固定 code+reason）；不返回旧成绩；零状态写入 |
| B2-01/B2-02 交叉（COLD-CRASH） | §5.5、T-6 | 崩溃恢复后同 scope 重试收敛到单一终态；不重复 mastery；PR2 测试保持绿（新 scope 断言） |
| B2-03 交叉（CONCURRENCY） | §5.5、M16/M17、T-9/T-10 | 并发冲突显式化/CAS 生效；不静默 last-write-wins |
| B0-01 合同 | §4.4/§5.3 | 不改冻结记录字段；`HistoryEvent` payload add-only；schema v2 迁移 add-only |

### 7.3 运行命令（实现后使用；本设计 PR 不运行）

```bash
cd /root/m1b/pr3design
"/root/Autonomous Teacher/.venv/bin/python" -m pytest tests/m1_teacher -q
"/root/Autonomous Teacher/.venv/bin/python" -m pytest \
  tests/m1_teacher/test_scoped_idempotency.py \
  tests/m1_teacher/test_multilearner_isolation.py \
  tests/m1_teacher/test_result_scope_migration.py \
  tests/m1_teacher/test_concurrent_idempotency.py -q
"/root/Autonomous Teacher/.venv/bin/python" -m ruff check m1_teacher tests/m1_teacher
```

**证据边界**：实现前的负例测试应先在 base `4706250` 上复现为 **FAIL**（证明缺陷），修复后转 **PASS**；本设计不提供 PASS。任何"跨租户安全已修复"的说法必须附带独立 Reviewer 复跑与 B3-01/02 的 raw evidence。

---

## 8. 风险、未决问题与需要 Lead 决策的事项

### 8.1 明确的能力边界（不可宣称）

1. **无真实 auth**：M1-A/M1-B 没有认证/授权层；`learner_id` 由受信上层传入，`session_id` 可被知道它的人加载（`engine.py:659-667`、`start_session(session_id=...)` `:319-357`）。本设计只做**数据访问层的 scope 校验**，不能阻止"持有合法上层凭据的调用方传入他人 learner/session 参数"；因此**绝不能声称多租户安全**。若要真正多租户，需要 A/B 线之外的鉴权边界（未来工作项）。
2. **单 writer 假设**：PR2 文档声明单 learner/session 单写者；并发测试证明串行化/冲突语义，但多写者的性能与公平性不在本阶段保证。
3. **at-least-once scorer**：崩溃恢复可能重复调用外部 scorer；状态应用 exactly-once，但**不承诺远程评分副作用 exactly-once**。
4. **合成数据**：所有测试/证据为 synthetic/CC0-1.0；不得用真实用户数据验证。
5. **M0/Live**：不涉及、不修改；M0 能力状态 UNVERIFIED 不变。

### 8.2 未决问题（需 Lead/维护者决策）

| # | 问题 | 选项/建议 | 影响 |
| --- | --- | --- | --- |
| Q1 | 跨 learner/session 复用同一 `result_id` 的裁决 | 建议 **冲突**（§3.3，兼容 PR2）；备选"每 scope 独立 token"（方案 B，需 v2 event id） | B3-01 语义、PR2 合并冲突、测试预期 |
| Q2 | 是否现在实施 v2 scoped event id（方案 B） | 建议 **v1 不改 event id**（方案 A），将来如产品要求允许跨 scope 同 token 再做 | 迁移/导出/PR2 工作量 |
| Q3 | `caller_learner_id` 是否在 PR3 就加入 `submit_response`（可选参数） | 建议加（默认 None，fail-closed 校验），PR4/PR5 CLI 传当前 learner；不加则 scope 仍只能靠 session owner 字段 | API 兼容性、攻击面 |
| Q4 | legacy 未知 digest 的迁移/重放策略 | 建议默认拒绝 + 显式 opt-in 工具（§4.5 M14）；是否允许产品路径 opt-in 需维护者决定 | 旧数据可用性 vs 严格性 |
| Q5 | PR2 与 PR3 的合并顺序/职责 | 建议 PR2 先冻结合并，PR3 rebase 后实现 scope 层（§5.4 的 PR2 加固点清单）；若并行，需冻结 `commit_teaching_turn` 签名 | 冲突/返工风险 |
| Q6 | `result_scopes` 表由 PR2 还是 PR3 引入 | 建议 PR3 引入（schema v2），PR2 保持 schema v1；避免 PR2 范围膨胀 | 迁移责任/测试归属 |
| Q7 | 是否允许"同 turn 同 content 换 id"自动返回旧结果 | 建议拒绝（§3.2）；若产品要求容错，需要额外 audit 与显式 opt-in | 客户端 SDK 行为 |
| Q8 | 错误 details 是否允许含 `result_id` 哈希前缀用于关联支持工单 | 建议只含请求方 scope 与 reason；哈希前缀可选项需隐私评审 | 可诊断性 vs 泄漏面 |

### 8.3 残余风险

- **存在性预言机**：严格冲突策略下，调用方可能从 `IDEMPOTENCY_CONFLICT` 得知某 `result_id` 已被使用（不含 owner 数据）；由于 token 是调用方生成且非秘密，判为低风险；方案 B 可消除，列 Q2。
- **全局 event id PK 仍存在**：方案 A 依赖"严格冲突 + scope 索引 + 过滤读"保证语义；若未来出现绕过索引的写路径（例如手工 SQL/迁移工具），仍需 CI 静态断言（T-14）与迁移审查。
- **历史 legacy 回填的 turn/digest 推断**：旧事件信息不全时只能标记 `legacy:unproven` 并默认拒绝重放；会影响极旧客户端的"丢失 result_id 重试"，需产品确认可接受。
- **数据库升级不可逆**：v2 schema 写入后旧引擎 fail-closed（版本更高），回滚需备份；PR3 需提供迁移前备份/只读检查命令（PR5 可选）。
- **性能**：每次提交多一次 scoped 查询 + 一次索引写入；WAL 下单事务开销可接受，但需 PR3 性能基准（小规模、离线）记录。
- **日志/导出兼容**：新 payload 字段会改变 demo/导出 JSONL 的字节（历史基线保持不变）；新基线需在 PR3/PR5 重新登记（evidence category `DETERMINISTIC`）。

### 8.4 STOP 条件（任一出现即停止并升级）

1. 任何路径把他人 `AssessmentResult` 返回给调用方（即使 details 被裁剪）；
2. 同 scope 不同 payload 静默返回旧成绩；
3. 同一 attempt 产生两条终态事件或两次 mastery 变更；
4. 迁移修改/删除/重写 `history_events` 既有行，或 rebuild/verify_rebuild 在迁移后失败；
5. 为通过测试而放宽断言、把 `NOT_RUN` 改 `PASS`、或在测试中引入真实 Provider/Key/网络/真实个人数据；
6. PR2 与 PR3 的接口/迁移责任未冻结即并行大改。

---

## 9. 附：本文引用的关键基线/实现位置索引

| 主题 | 位置（base `4706250`，除注明 PR2 外） |
| --- | --- |
| submit_response 入口/幂等顺序 | `m1_teacher/session/engine.py:488-563`（`:512-518` 显式幂等；`:519-527` 之后才校验；`:528-539` 默认路径与评分后复查） |
| 全局结果查重 | `m1_teacher/session/engine.py:833-850`（`_find_existing_result`） |
| 默认 result_id | `m1_teacher/session/engine.py:783-790` |
| EVAL_ERROR / NEEDS_REVIEW / OBSERVED 分支 | `m1_teacher/session/engine.py:855-...`（`_handle_eval_error` `:855`、`_handle_needs_review` `:896`、`_handle_observed_result` `:938`） |
| 报告/事件写入 | `m1_teacher/session/engine.py:708-730`（`_append_event`/`_record_deterministic_events`） |
| 事件 id 前缀/构造 | `m1_teacher/learner/history.py:81-82,109-118`；`engine.py:112-113`（evalerror/goalcompleted） |
| apply_assessment 全局已存在判断 | `m1_teacher/learner/history.py:210-330`（`:266`） |
| rebuild / known ids | `m1_teacher/learner/history.py:340-380` |
| SQLite 全局 PK/约束 | `m1_teacher/learner/repository.py:104-112`；`get_event` `:583-595`；`append_event` `:510-521`；`list_events` `:597-...`；`save_session` `:665-677`；`load_session` `:679-694` |
| 冻结记录 | `m1_teacher/contracts/types.py`：`AssessmentResult` `:683-711`（无 session/turn 字段）；`HistoryEvent` `:803-818`；`SessionState` `:821-833` |
| 错误基类/code override | `m1_teacher/contracts/errors.py:35-83`（`ConflictError` `:85-88`） |
| 现有幂等测试 | `tests/m1_teacher/test_session_engine.py:420-440`；`tests/m1_teacher/test_e2e_resume_idempotency.py:237-270` |
| PR2 未提交实现（供兼容参考） | `/root/m1b/pr2`：`session/engine.py` `_commit_result_turn` `:902`（`:924` 全局 terminal 返回）、`_find_prepared_payload_for_result` `:1155`、`_terminal_result` `:1177`、`_lookup_result_for_retry` `:1193`、legacy `_find_existing_result` `:1772`；`learner/history.py` `assessment_event_drafts` `:248`、`:385` 全局已存在判断；`learner/repository.py` `commit_teaching_turn` `:771`、`session_version`、`ASSESSMENT_PREPARED`/failpoints |

**本文档不包含实现，也不包含任何 PASS/NOT_RUN 状态变更；B3-01/B3-02 保持 `NOT_RUN` 直至实现 PR 与独立 Reviewer 复跑。**

---

## 10. 实现后独立评审行动关闭（P1/P2）

独立评审 commit `db636ea`（报告 `docs/M1_B_PR3_REVIEW.md`，结论 `PASS_WITH_ACTIONS`）提出 P1=2、P2=5；实现分支的关闭方式如下（证据见 `docs/M1_B_SCOPED_IDEMPOTENCY_IMPLEMENTATION.md` §8 与真实 pytest 输出）：

| 编号 | 处置 | 验收测试 |
| --- | --- | --- |
| P1-1 legacy 投影 | 新增 `legacy_canonical_response`/`legacy_request_digest`（pre-PR3 默认分隔符投影），legacy row/event/默认 id 全部按旧投影比较；新写入仍 compact；真实 base `4706250` v1 fixture 入库 | `test_real_pre_pr3_structured_legacy_replays_with_old_projection`、`test_pre_pr3_structured_default_id_uses_old_projection` |
| P1-2 apply_assessment 全局查重 | 改为 learner-filtered/scoped 查重；异 learner/session/item/PREPARED 稳定 `IDEMPOTENCY_CONFLICT`，不静默丢弃 | `test_apply_assessment_cross_learner_token_is_explicit_conflict`、`test_apply_assessment_same_scope_replay_stays_idempotent`、`test_apply_assessment_same_token_other_session_conflicts` |
| P2-1 并发语义 | 文档明确 M16 = convergent retry（同一 result、1 份终态），测试命名对齐并断言两进程结果完全相同 | `test_concurrent_same_scope_same_response_converges_to_one_result` |
| P2-2 phase 门禁顺序 | 同 scope TERMINAL 快速查找前移到 `PAUSED`/`COMPLETE` 之前，保留非本 scope 的 phase 拒绝 | `test_same_token_retry_after_complete_returns_stored_result`、`test_same_token_retry_after_paused_returns_stored_result` |
| P2-3 报告计数 | 实现报告改为最终树真实计数，632/595 标注为历史基线 | 本 doc §7.1 注 + 实现报告 §5.1 |
| P2-4 legacy fallback turn | `_legacy_event_lookup` 增加 attempt turn 校验（-1/当前/前一 turn） | `test_legacy_event_fallback_enforces_turn_rule` |
| P2-5 schema v1 turn | 表级 `CHECK (origin = 'legacy' OR turn_index >= 0)` + 应用层校验 | `test_schema_rejects_v1_rows_with_unknown_turn` |
