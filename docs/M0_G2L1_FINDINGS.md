# M0 G2-L1 FINDINGS（A0 RED 基线）

- 任务：`task-80` A0-RED；日期：2026-11-15 UTC；工作目录 `/root/Autonomous Teacher`
- 基线：HEAD `688ed018ea9a4b878f989571a26ab78ff55abb1d`（docs 收口）；**G2 实现基线 `32bea5b`**；`git diff 32bea5b..HEAD -- src tests config scripts plugins` 为空 → 本次 RED 面对的是 G2 旧代码字节。
- 性质：**只做 fail-first 测试/代码位置记录**；未改 `src/` 生产代码、未修 bug、未 commit；0 真实 Key/模型/HTTP/网络；未读取凭据。
- 新测试：`tests/integration/g2_closure/test_g2l1_red.py`（sha256 见 §5），仅 RED，不进入生产代码。
- OCI：`localhost/autoteacher-local-oci@sha256:62d3569e…`；stage `artifacts/g2l1/stage`（旧代码 + 新测试）；deps `/root/Autonomous Teacher/artifacts/foundation/deps`；`--network none`、read-only、uid 65534、cap-drop ALL/no-new-privileges；宿主未跑 pytest。

## 1. 环境 smoke（旧代码）

- argv：`tests/integration/g2_closure -q`（完整 argv 见 `artifacts/g2l1/argv/smoke.argv.json`）
- 结果：**17 passed in 7.35s，exit 0**（`artifacts/g2l1/logs/smoke.stdout.log`）→ OCI/stage/依赖环境 OK。

## 2. RED 选择集与真实计数

- 选择集：`tests/integration/g2_closure/test_g2l1_red.py -q -p no:cacheprovider --tb=short`
- argv：`artifacts/g2l1/argv/red.argv.json`
- 日志：`artifacts/g2l1/logs/red.stdout.log`、`red.stderr.log`
- **真实结果：`10 failed, 2 xfailed in 0.06s`，exit 1**（未预填；由日志实际计数）
- 失败用例（10）：
  - `test_l1b_claim_dispatch_without_claimer_denies`
  - `test_l1b_require_claim_without_claimer_raises`
  - `test_l1d_mock_transport_without_claimer_must_not_dispatch`
  - `test_l1e_policy_loader_rejects_bool_int_coercion[payload0..3]`（4 个参数）
  - `test_bool_int_confusion_is_denied[overrides0..2]`（3 个参数）
- 严格 xfail（2，设计固定，待 A1/A2 实现后应转 PASS；strict 下当前正确记为 xfailed）：
  - `test_l1a_l1c_descriptor_evaluation_is_not_send_permission`（A1 new API 不存在）
  - `test_bind01_reservation_route_model_must_bind_actual_request`（BIND-01 新绑定 API 不存在）

## 3. 逐项 finding / 代码位置 / 旧行为 / 复现 / 本 PR 状态

| ID | 代码位置（当前 G2 旧代码） | 旧行为（static + RED 复现） | RED 复现 | 本 PR 状态 |
|---|---|---|---|---|
| **L1-a** | `src/autoteacher_m0/security/egress.py:210-213` `authorize()` = `_evaluate` + `_record` | 仅描述符检查即可产生 `allowed=True`；不要求任何 Claim | 设计 xfail 固定：`evaluate_descriptor` 不存在；见 `test_l1a_l1c_*` | **OPEN**，A1 拆分 `evaluate_descriptor`/正式 `claim_dispatch`；本 PR 不修 |
| **L1-b** | `security/egress.py:215-225` `claim_dispatch()`：`:221-225` 当 `claimer is None` 直接返回原 descriptor decision | 忘记注入 Claimer 时静默允许 dispatch（allowed=True） | `test_l1b_claim_dispatch_without_claimer_denies` **FAILED** | **OPEN**，A1 fail-closed `BROKER_CLAIMER_UNAVAILABLE`；本 PR 不修 |
| **L1-c** | `security/egress.py:284-288` `require()` 调 `authorize()` | `require()` 名称像正式准入，但无 Claim 也放行/不抛 | `test_l1b_require_claim_without_claimer_raises` **FAILED** | **OPEN**，A1 让正式入口只走 claim-required 语义；本 PR 不修 |
| **L1-d** | `security/egress.py:317-324` `MockEgressTransport.dispatch()`：无 claimer 时 `authorize()` 回退 | 无 Claimer仍 `dispatched=True`；未来 Bridge 可误用 | `test_l1d_mock_transport_without_claimer_must_not_dispatch` **FAILED** | **OPEN**，A1 去回退或显式 policy-only；本 PR 不修 |
| **L1-e** | `security/egress.py:348-367` `policy_from_json()`：`:355-357` `int()`/`str()`；`:362-367` `int()`/`bool()` | `allow_files:"false"`→True、`allow_store:"0"`→True、`max_tokens:"256"`→int、`require_reservation:0`→False；无严格类型拒绝 | `test_l1e_policy_loader_rejects_bool_int_coercion[payload0..3]` **4 FAILED** | **OPEN**，A1 strict loader（type is bool/int，未知字段拒）；本 PR 不修 |
| **bool/int 混淆** | `security/egress.py:172-188` `_evaluate`：`isinstance(max_tokens,int)`、`attempt_ordinal < 1`、`stream in (True,False)` | `max_tokens=True`/`attempt_ordinal=True`/`stream=0` 均被接受 | `test_bool_int_confusion_is_denied[overrides0..2]` **3 FAILED** | **OPEN**，A1 严格 bool/int；本 PR 不修 |
| **BIND-1** | `accounting/ledger.py:199-273` `claim_dispatch` 只校验 Reservation 的 `(route_id,model) ∈ allowed_routes`；`claim` op（`broker.py:171-179`）只接受 call_id/reservation_id/request_digest | 多 allowed route 时，Reservation=A/Model=A 的 claim 不绑定实际待发送 Request=B/Model=B；`request_digest` 只格式/存储，未与实际待发送字节核对 | `test_bind01_*` **strict xfail**（旧 API 无绑定入口）；见 §6 | **OPEN**，A2 定义 `PreparedProviderRequest` 绑定；BIND-2 属 G3 wire 缺口；本 PR 不修 |
| **BIND-2** | `broker.py:171-179` + `ledger.py:213,257-273` | digest 只做 regex/durable 存储，未与 Bridge 实际字节做端到端核对 | 设计测试固定；旧 API 无 actual-bytes 绑定 | **OPEN/G3**；不得称“已验证付费事故”；A2 设计 + G3 消除；本 PR 不修 |
| **TEST-1** | `tests/integration/g2_closure/test_g2_closure.py:378-389` `test_int11_*`：`EgressBoundary(EgressPolicy(...))` 未配置 claimer | 测到的是 descriptor Policy 拒绝，不是真实 Broker/route claim 拒绝 | 记录于 findings；A3 迁移/补真实 claimer 版本 | **OPEN**，A3 测试修补；本 PR 不修 |
| **TEST-2** | `test_g2_closure.py:288-304` `test_int06_*`：`claimer = StdioBrokerClaimer(path)` 后 `claimer.close() if False else None`；`send(start_broker(path),...)` 未保留/关闭 replay broker 进程 | 可能残留进程/文件，不利复验 | 记录于 findings；A3 清理；本 PR 不修 | **OPEN**，A3 测试修补；本 PR 不修 |
| **OBS-1** | `security/egress.py:145-149` `_stream()` 以 `logical_stream_id` 为 key，记录首个 `reservation_id`；`:275-282` snapshot 按 stream 汇总 | 同一 stream 中多个独立 Reservation 的快照 reservation_id/attempt 归因可能误导（只保留首个） | 记录于 findings；A3 归因修复 | **OPEN**，A3 `_streams`/snapshot 归因；本 PR 不修 |

## 4. RED 测试设计说明（为何 xfail 而非修改旧代码）

- **L1-a/L1-c**：新接口 `evaluate_descriptor()` 尚不存在；用 `xfail(strict=True)` 固定“描述符评估≠正式发送许可；正式 `require_claim` 必须持 Claimer”的目标语义。A1 实现后移除/更新 xfail，必须真正 PASS。
- **BIND-01**：旧 API 没有 request-bound claim 入口；用 strict xfail 固定“Reservation=A/Model=A vs 实际 request=B/Model=B 必须 0 dispatch”的反例；A2 实现 API 后转为真实 fail/pass 断言。
- 其余 L1-b/L1-d/L1-e/bool 用例**没有 xfail**；在旧代码上必须是真实 failed（当前 10 failed），不得用 skip/xfail 掩盖。

## 5. 工件与身份

- 新测试文件：`tests/integration/g2_closure/test_g2l1_red.py`
- stage：`artifacts/g2l1/stage`；stage-identity：`artifacts/g2l1/stage-identity.txt`
  - stage file count=6133；normalized tar sha256=`e706c0bb7704e960b82398f2d78e348569bad91aa5a20e9a960236a254a6baaa`
  - image=`localhost/autoteacher-local-oci@sha256:62d3569e…`；deps e07729d7…
- 本 findings 文件：`docs/M0_G2L1_FINDINGS.md`
- 未改 `src/`；`git status` 仅新 test/findings（及其它既有审计文档，本任务未 commit）。

## 5A. A1+A3 修复后状态（GREEN，2026-11-15）

本节取代 §3 的 A0 表列 `本 PR 状态`；A0 RED 历史保留在 §2–§4。

| ID | 状态 | 修复/证据 |
|---|---|---|
| L1-a | **FIXED** | `evaluate_descriptor()` 返回 `PolicyEvaluation`（无 claim/permission）；`authorize()` 为诊断别名；正式 dispatch 只接受 `DispatchPermission`。证据：`test_g2l1_red.py::test_l1a_l1c_descriptor_evaluation_is_not_send_permission`（已移除 xfail，真实 PASS）、`test_g2l1_fix.py::test_fix01`。 |
| L1-b | **FIXED** | 无 Claimer 时 `claim_dispatch()` 返回 `allowed=False` + `BROKER_CLAIMER_UNAVAILABLE`，无 permission；`require_claim()` 抛 `EgressViolation`。证据：`test_fix02`、red L1-b 用例。 |
| L1-c | **FIXED** | `require()` 仅 descriptor 诊断（policy deny 才抛）；`require_claim()` 是正式准入入口。证据：`test_fix01`/`test_fix02`、red L1-c。 |
| L1-d | **FIXED** | `MockEgressTransport` 不再无 Claimer 回退 `authorize()`；`TrustedEgressTransport.dispatch()` 只接受真实 `DispatchPermission`（`isinstance` + `claim.claimed is True` + request 身份字段匹配 + 单次消费）。证据：`test_fix05/06/07`、sandbox matrix。 |
| L1-e | **FIXED** | `policy_from_json()` 严格类型/未知字段/范围/路由/host_ports/path_prefix；`allow_*`/`require_reservation` 必需 `type is bool`，`max_tokens/max_attempts` 必需 `type is int` 且范围合法。证据：`STRICT-01/02/03` 全 PASS。 |
| bool/int 混淆 | **FIXED** | `_evaluate` 严格 `type(stream) is bool`、`type(max_tokens) is int`、`type(attempt_ordinal) is int`、flag 类型；`max_tokens=True`/`attempt_ordinal=True`/`stream=0` 拒绝。证据：`STRICT-04`（8 参数）PASS。 |
| BIND-1/BIND-2 | **OPEN（A2）** | 未改 broker/ledger 协议；BIND-01 设计 xfail 保留（`test_bind01_reservation_route_model_must_bind_actual_request`）。A2 定义 `PreparedProviderRequest` 绑定；BIND-2 仍 G3 wire 缺口。 |
| TEST-1 | **PARTIAL** | INT-11 仍以无 claimer 的 descriptor policy 拒绝为主；真实跨 Route/Model broker 绑定等待 A2（BIND-01 xfail）。未删除原断言；见 `test_g2_closure.py:378-389`。 |
| TEST-2 | **FIXED** | INT-06 replay broker 进程改为 try/finally `stop(replay_proc)`，不再泄漏；回归通过。见 `test_g2_closure.py:288-307`。 |
| OBS-1 | **FIXED** | `LogicalStreamEgress.attempts_detail` 逐 attempt 记录 call_id/reservation_id/policy_allowed/claim_granted/provider_dispatched；snapshot 输出 detail，多 Reservation 不再只保存首个。证据：`TRACE-01`、`snapshot()` 字段。 |

### GREEN 证据（固定无 Key OCI）

- focused（RED + FIX + sandbox）：**76 passed, 1 xfailed**（仅保留 BIND-01 strict xfail），exit 0；日志 `artifacts/g2l1/logs/a1-focus.stdout.log`。
- G2/security/sandbox 回归：**234 passed, 1 skipped, 1 xfailed**，exit 0；日志 `artifacts/g2l1/logs/a1-regression-final.stdout.log`。
- `scripts/verify_egress_policy.py`：**status=PASS**，exit 0；日志 `artifacts/g2l1/logs/a1-script.stdout.log`。
- Ruff scoped：`ruff check src tests scripts` → **All checks passed!**（`a1-ruff.stdout.log`）。
- denied 场景 provider dispatch=0：`test_fix03`（claim false/raise/bad reply）、`test_fix04`（descriptor deny 不调用 claimer）、`test_fix05`（无/伪造 permission → provider.calls=0）、`test_fix07`（permission 绑定不匹配 → 0）、`test_fix08` 真实 stdio replay 后 provider.calls 仍 1（无第二次 dispatch）。
- 贪心/异常/重放均 fail-closed；permission 单次消费；provider 只由 `TrustedEgressTransport.dispatch` 在 claim 成功后调用。

### 修改文件（A1+A3）

- `src/autoteacher_m0/security/egress.py`（PolicyEvaluation/DispatchPermission/TrustedEgressTransport/strict loader/OBS-1）
- `src/autoteacher_m0/security/__init__.py`（安全导出）
- `scripts/verify_egress_policy.py`（新诊断/policy-only + trusted claim matrix）
- `tests/integration/sandbox/test_egress_boundary.py`（新语义）
- `tests/integration/g2_closure/test_g2l1_red.py`（L1-a/L1-c 去 xfail；BIND-01 保留 xfail）
- `tests/integration/g2_closure/test_g2l1_fix.py`（FIX-01..08、STRICT-01..04、TRACE-01、PROC-01）
- `tests/integration/g2_closure/test_g2_closure.py`（TEST-2 INT-06 清理）
- `docs/M0_G2L1_FINDINGS.md`（本节）
- 未改 broker/ledger；BIND-1/2 保持 OPEN/A2。

## 5B. A1-审计补齐（G1/G2/G3）后状态（GREEN-2）

Lead 审计 A1 发现 3 个缺口；本轮已修，A1 初始 GREEN 计数（§5A）由本节最终计数取代：

| 审计缺口 | 状态 | 修复/证据 |
|---|---|---|
| **G1（P0，安全绕过）** | **FIXED** | `DispatchPermission` 仍为公开 frozen dataclass，但 `EgressBoundary` 维护私有 `_issued_permissions` 登记（仅 `claim_dispatch()` 成功后写入）；`TrustedEgressTransport` 不再只做 isinstance/字段比较，而是调用 `boundary.consume_permission(permission, request)`：校验对象身份+字段+未消费，成功后立即注销。因此直接构造/复制篡改/跨 boundary/二次消费均 0 provider 调用。**明确：这是进程内 capability 登记，不是跨进程密码学授权；G3 外部边界要求不变。** 证据：`test_fix09_forged_tampered_cross_boundary_and_replayed_permission_never_dispatch`（伪造 forced dispatch=False、provider.calls=0；tampered/跨 boundary/二次均 0）。 |
| **G2（P1，STRICT-03）** | **FIXED** | `policy_from_json` 现在拒绝重复 methods（含大小写归一后重复）、method 前后空白、host 前后空白、同一 host 重复 port；`test_strict03b_policy_loader_rejects_duplicates_and_whitespace` 覆盖 4 个负例。 |
| **G3（P1，STRICT-04 路径绕过）** | **FIXED** | `_invalid_path()` 拒绝：非 `/` 开头、非 policy prefix、`..` 段/子串、反斜杠、`%2e`/`%2E`（casefold）、控制字符（<32/127）。`test_strict04b_path_traversal_backslash_encoding_and_control_denied` 覆盖 traversal、`..` 段、backslash、编码点段、NUL、相对路径；assert claim denied/permission None/provider.calls=0。 |

### GREEN-2 证据（固定无 Key OCI）

- focused（RED + FIX + sandbox）：**88 passed, 1 xfailed**，exit 0；唯一 xfail 仍为 BIND-01/A2；日志 `artifacts/g2l1/logs/a1-audit-focus2.stdout.log`。
- G2/security/sandbox 回归：**246 passed, 1 skipped, 1 xfailed**，exit 0；日志 `artifacts/g2l1/logs/a1-audit-regression.stdout.log`。
- `scripts/verify_egress_policy.py`：**status=PASS**，exit 0；`artifacts/g2l1/logs/a1-audit-script.stdout.log`。
- Ruff scoped：**All checks passed!**；`artifacts/g2l1/logs/a1-audit-ruff.stdout.log`。
- G1/G2/G3 证据均来自上述 focused 运行中的真实 passed 用例；denied/tampered/forged/replay 的 provider.calls 由 `CountProvider` 实际计数为 0/1（非静态声明）。
- BIND-1/BIND-2 仍 **OPEN/A2**，BIND-01 strict xfail 保留；未改 broker/ledger 协议。

## 5C. A2 请求绑定（Option A 批准后）状态（GREEN-3）

Lead 已批准 **Option A**；broker/ledger 已按批准做 **additive** 变更（未改 claim 表结构、未 commit）。以下状态取代 §5B 的 BIND 行：

| 项 | 状态 | 证据 |
|---|---|---|
| **BIND-01** | **FIXED（A 阶段可证）** | 真实 SQLite + 真实 stdio Broker + 两个 allowlist route/model：Reservation=A/Model=A、实际请求=B/Model=B → ledger 返回 `ROUTE_MISMATCH`、无 claim 记录、provider=0。测试 `test_bind01_reservation_a_actual_b_route_mismatch_ledger`。 |
| **BIND-02** | **FIXED（egress 侧）/ 远端 G3_DEPENDENCY** | Prepared 消息变更 → recompute digest 不一致 → deny、claimer/provider=0。测试 `test_bind02_prepared_message_digest_change_denied`；真实 wire 字节一致性仍 G3。 |
| **BIND-03** | **FIXED（egress 侧）** | Prepared max_output_tokens 512 vs 实际 256 → `MAX_TOKENS_MISMATCH` deny、claimer=0。测试 `test_bind03_max_tokens_mismatch_denied`。 |
| **BIND-04** | **FIXED（egress 侧）** | method/path/host 任一不一致 → deny、claimer=0。测试 `test_bind04_method_path_host_bypass_denied`。 |
| **BIND-05** | **FIXED（egress 侧）/ 正式审批 G3_DEPENDENCY** | prepared.tools 非空且不在 `approved_tool_schemas` → `TOOL_SCHEMA_NOT_APPROVED` deny、claimer=0。测试 `test_bind05_unapproved_tool_schema_denied`；正式 tool 注册表/审批属 G3。 |
| **BIND-06** | **FIXED（本地 claim）** | 真实 SQLite/stdio bound claim：首次成功、重复 claim 至多一次；第二轮 deny、provider 仍 1。测试 `test_bind06_duplicate_bound_claim_at_most_once`；远端 exactly-once 仍 G3。 |
| **BIND-07** | **FIXED（本地 claim）** | 未修改 prepared/request 成功且 ledger `claims.total=1`；FakeProvider 真实计数 1。测试 `test_bind07_unmodified_success_once_and_ledger_link`；真实账单/usage 仍 G3。 |
| **BIND-08** | **FIXED** | 仅 `reserve.dispatch_allowed=True`、未 claim → 无 permission、provider=0、claims=0。测试 `test_bind08_reserve_dispatch_allowed_without_claim_zero_dispatch`。 |
| **BIND-1（概念项）** | **FIXED（本地/egress+ledger 权威）** | 新路径 `claim_dispatch_for_request` + `BoundBrokerClaimer` + ledger expected route/model 比较；BIND-01 真实覆盖。 |
| **BIND-2（概念项）** | **G3_DEPENDENCY** | prepared digest 由受信端计算并重算，但实际 provider wire 字节/远端 digest 未验证；不得写成“远端 exactly-once 已验证”。 |
| **TEST-1** | **PARTIAL（真实 claimer 版本已补）** | INT-11 原始 descriptor 断言保留；BIND-01 新增真实 stdio claimer 跨 route/model 拒绝。 |
| **TEST-2** | **FIXED** | INT-06 replay broker 进程已 try/finally 清理（见 §5A），回归通过。 |
| **v1 旧客户端兼容** | **PASS（明确残余）** | 旧 claim 不带 expected 字段仍成功（`test_v1_old_claim_without_expected_fields_still_succeeds`）；新 egress 对无 `claim_bound` 的 claimer 显式 `CLAIM_BINDING_UNSUPPORTED` deny、provider=0（`test_v1_new_egress_rejects_unbound_claimer`）。**旧客户端省略字段的 binding 缺口仍在，不能称“所有 claim 已强制绑定”。** |

### GREEN-3 证据（固定无 Key OCI）

- focused（RED + FIX/BIND/STRICT/TRACE/PROC + sandbox）：**98 passed**，exit 0；A0 的 BIND-01 设计 xfail 占位已移除，A2 真实覆盖为 `test_g2l1_fix.py::test_bind01_reservation_a_actual_b_route_mismatch_ledger`。
- 回归（g2_closure + sandbox + unit/security）：**256 passed, 1 skipped**，exit 0。
- `scripts/verify_egress_policy.py`：**status=PASS**，exit 0。
- Ruff scoped：**All checks passed!**
- 日志/argv：`artifacts/g2l1/logs/a2-focus.stdout.log`、`a2-regression.stdout.log`、`a2-script.stdout.log`、`a2-ruff.stdout.log`；`artifacts/g2l1/argv/a2-*.argv.json`。
- denied/tampered/forged/replay 的 provider 计数来自测试内 CountProvider 实际调用（BIND-02/03/04/05/08 均 0；BIND-06 重放后仍 1；BIND-07 成功 1）。

### 修改文件（A2）

- `src/autoteacher_m0/security/egress.py`（PreparedProviderRequest/canonical digest/claim_dispatch_for_request/BoundBrokerClaimer 协议）
- `src/autoteacher_m0/security/__init__.py`（导出）
- `src/autoteacher_m0/accounting/broker.py`（claim 可选 expected 字段；成对校验；成功响应 route/model；additive）
- `src/autoteacher_m0/accounting/ledger.py`（claim_dispatch expected 比较 → ROUTE_MISMATCH；claim 表不变）
- `tests/integration/g2_closure/test_g2l1_fix.py`（BIND-01..08、v1 兼容、Prepared 辅助）
- `docs/M0_REQUEST_BINDING_CONTRACT.md`（批准状态/细节）
- `docs/M0_G2L1_FINDINGS.md`（本节）
- 未改 gates/adapter/run_live；未 commit。

### G3_DEPENDENCY 清单（不写 PASS）

1. 真实 provider wire 字节/digest 与 PreparedProviderRequest 的远端一致性。
2. 正式 tool schema 注册/审批表（A 仅做输入负例）。
3. 远端/provider exactly-once、usage/invoice/账单。
4. 旧 v1 客户端省略 expected 字段的 binding 残余缺口。

## 6. 状态与 STOP

- A0-RED 完成；L1-a..e、BIND-1/2、TEST-1/2、OBS-1 均记录代码位置/旧行为/复现/待修状态。
- **本 PR 不修复任何项**；A1/A2/A3 待 Lead 确认后执行。A0 当前处于 **RED**，不是 GREEN，不得报告 security 修复完成。
- 0 真实 Key/网络/模型；未改 gates.py/dsh_adapter.py/run_live.sh；未 commit。
