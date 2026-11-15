# G1 独立审计 — Security（AUTH-02/05/06/08、WD-03/04）与 Accounting（OBS-01/02/03/05/06、INT-15）

- 任务：`task-62`；日期：2026-11-15 UTC；审计者：`verify2`（非实现者；G1-SEC 由 task-60、G1-ACC 由 task-61 实现）
- 审计对象：
  - **G1-SEC** commit `842583dceb0f7c7b43191b6b4b4c6d9cf8da8b09`（父 `92c9f719f177d946f61ca748203c081b9a9cb952`，8 files）
  - **G1-ACC** commit `00df577f18fcef924d9cef2a7c7d08afcc3bca20`（父 `842583d`，5 files）；HEAD=`00df577`，worktree clean
  - owner 报告：`docs/M0_G1_SECURITY_REPORT.md` sha256 `0a8f6e18…`；`docs/M0_G1_ACCOUNTING_REPORT.md` sha256 `c20828ad…`
  - owner 证据：`artifacts/m0-g1-security/`（manifest `4ef23f69…`，evidence **36/36**）；`artifacts/m0-g1-accounting/`（manifest `cb780a39…`，evidence **16/16**）
- 结论：**FAIL_FOR_DECLARED_G1_SCOPE**（不签发 G1 PASS）。G1-SEC 的 A1/A2/A3/A8/WD、G1-ACC 的 OBS-01/02/03/05/06/INT-15 及其 fail-first/170 回归均通过独立复跑；但 **AUTH-08 的 budget policy 子项存在 1 个阻断缺口（B-G1-1）**：Controller 只把 `budget_scope` 传入授权解析，没有把 expected budget caps 作为策略绑定，也没有 budget-only mutation 测试；因此不能把 task-60 要求的“仅改 path/method/model/budget → Controller 拒绝 Policy 变化”写成全部通过。另有 2 项非阻断证据/报告问题（V-G1-1/V-G1-2）与 1 项需 G2 收口的条件（provenance 仍非真实来源认证）。**Live/E1–E5/真实 egress/Key/usage/账单仍 BLOCKED；DECISION PENDING，不签发 GO。**

## 1. 方法与隔离

- 从最终冻结 HEAD 生成独立 stage：`git archive 00df577`（**174 files**，archive sha256 `2bdfd4c0b47da0a21207f115949bc908d77024557cab333347b74d0e81a3cc65`）；G1 全部 11 个实现/测试文件 hash 与 owner manifest `deliverables`/变更列表逐字节一致。
- 为复核 fail-first，另建两个独立旧 stage：`git archive 92c9f71` 的完整树 + 来自 `00df577` 的新测试文件（实现源码=旧字节，测试=新字节）；因此 fail-first 是“旧实现 vs 新断言”的真实对照。
- 所有项目代码/测试只在固定 digest 无 Key/禁网 OCI 内运行：rootfs `25491e45…`、deps `e07729d7…`、`--network none`、`--http-proxy=false`、`--unsetenv-all`、uid 65534、只读 rootfs、cap-drop ALL、no-new-privileges、pids/mem/cpu 限制、`/tmp`/`/work` noexec tmpfs。宿主只做 git/hash/podman launcher；**未在宿主执行 ptyhon/pytest/TS**。
- 0 真实 Key、0 真实模型、0 真实 HTTP；未读 `/root/.config/autoteacher`；未启动真实 provider/egress。容器运行后 absence=0；rootfs/deps 已复核 canonical（`25491e45…`/`e07729d7…`）。

## 2. 范围与未解锁面

| 检查 | 结果 |
|---|---|
| G1-SEC 仅改 8 文件 | `ed25519.py`、`authorization.py`、`live_controller.py`、`watchdog.py`、`test_authorization.py`、`test_watchdog.py`、`test_live_controller_no_key.py`、`docs/M0_G1_SECURITY_REPORT.md`；无 accounting/egress/gates/adapter/run_live 改动 |
| G1-ACC 仅改 5 文件 | `observation.py`、`broker_usage.py`、`test_provider_observation.py`、`test_observation_broker.py`、`docs/M0_G1_ACCOUNTING_REPORT.md`；无 ledger/broker/`__init__.py`/security/egress/历史证据改动 |
| `git diff --check` | 0 |
| LiveGate / `security/gates.py` / `runtime/dsh_adapter.py` / `scripts/run_live.sh` | 相对 `92c9f71` **0 改动**；`gates.py` 仍恒 BLOCKED、`run_live.sh` 仍硬停 exit 3、adapter `_require_live_authorization()` 仍抛 `SECURITY_BLOCKED` |
| 历史证据 | phase5 `391767d3…`、PR1 `df14f3c1…`、PR2 `c6ea4e86…`、PR3 `b5c16f81…`、PR4a `b04afbc9…`、PR4b `de1bdb07…` 字节未改 |
| owner evidence | G1-SEC 36/36 OK；G1-ACC 16/16 OK；owner 报告 hash 与 Lead 给定锚一致 |
| 真实 Key/模型/HTTP | 两份 owner manifest 均 `real_key_model_http_calls=0`/`real_model_calls=0`/`http_calls=0`/`keys_read=0`；独立运行无网络；未读凭据 |

## 3. 独立重跑（固定 digest 无 Key OCI；argv/UTC/exit 见 `artifacts/reviewer-g1/raw/commands.jsonl`）

| 用例 | 独立结果 | owner 声称 | 一致性 |
|---|---|---|---|
| security targeted `-k auth02/auth05/auth06/auth08/wd03/wd04` | **30 passed, 40 deselected**，exit 0 | 30 passed | 一致 |
| full security+sandbox `tests/unit/security tests/integration/sandbox` | **157 passed, 1 skipped**，exit 0 | 157 passed, 1 skipped | 一致（skip 为既有 `/input` 探针契约） |
| accounting targeted（`test_provider_observation.py` 新 OBS/INT 选择集） | **7 passed, 29 deselected**，exit 0 | —（owner 未单列） | 独立补充 |
| full accounting+budget_bridge `tests/unit/accounting tests/integration/budget_bridge` | **170 passed**，exit 0 | 170 passed | 一致 |
| fail-first（旧实现 + 新测试，security targeted） | **26 failed, 4 passed, 40 deselected**，exit 1 | 26/4/40 | 一致 |
| fail-first（旧 accounting 实现 + 新测试） | **2 collection errors**，exit 2 | 2 collection errors | 一致 |
| Ruff scoped `src scripts tests` | **All checks passed!**，exit 0 | All checks passed | 一致 |
| Ruff repo-wide `.` | **All checks passed!**，exit 0 | All checks passed | 一致 |

> 审计证据中的 argv/UTC/exit/stdout/stderr 均为本次新运行；未预填数字。首次尝试因相对路径（`tests/...` + `--workdir /work`）导致 pytest 找不到用例（exit 4），修正为 `/project/...` 后得到上表；该失败尝试保留在 `raw/commands.jsonl` 中，不计入最终结论。

## 4. 语义核验（源码 + 测试）

### AUTH-02（identity/小阶/非规范公钥）
- `ed25519.py:78-94` `_decode_point` 强制 `y<q`、`x<q`、重编码一致（canonical）；`:97-117` `_is_small_order`/`_in_prime_order_subgroup`/`is_valid_public_key` 拒绝 identity/小阶并要求 `[L]P=O`；`:155-175` `verify` 对 A/R 均做 canonical + 小阶 + prime-order 检查。
- `authorization.py:218-233` trusted key 加载调用 `is_valid_public_key`，非严格点直接拒绝。
- 回归：`test_auth02_identity_public_key_is_rejected`、`test_auth02_noncanonical_identity_point_is_rejected`、`test_auth02_low_order_public_key_is_rejected`、`test_auth02_rfc8032_positive_vector_still_verifies` 均通过；RFC8032 正向向量仍通过，伪造 identity 签名不再验证。

### AUTH-05（整数强类型）
- `authorization.py:134-138` `_require_int` 用 `type(value) is int`；`:362,384-386` 替换所有 budget/deadline 的 `int(...)` 转换。
- `test_auth05_integer_coercion_is_rejected` 10 个参数（`"10"`/`10.5`/`True` 等）全部拒绝，返回 `BUDGET_VALUES_INVALID`/`DEADLINE_VALUES_INVALID`。

### AUTH-06（非法 approver 不崩溃）
- `authorization.py:285-305` 将 approver 与时间解析拆开；失败分别给 `APPROVER_INVALID`/`AUTHORIZATION_TIME_INVALID`，并设安全默认（`approver=""`、时间=moment），返回 `approved=False`，不再走未赋值变量。
- `test_auth06_bad_approver_or_time_is_fail_closed` 5 个参数（含非法 approver 123/"")全部安全拒绝，无 `UnboundLocalError`。

### AUTH-08（完整 Egress/Route Policy + 仍 BLOCKED）
- `live_controller.py:37-47` 定义完整 `EGRESS_POLICY_FIELDS`（host_ports/methods/path_prefix/approved_routes/max_tokens/max_attempts/require_reservation/allow_files/allow_images/allow_store）；`:130-132` 逐字段比较并给出 `EGRESS_POLICY_FIELD_MISMATCH:<field>`；`:135-158` 仍 inspect-only，`status=BLOCKED`、`require_live` 抛 `SecurityBlocked`。
- `test_auth08_complete_egress_policy_mismatch_blocks` 8 参数（methods/path_prefix/approved_routes/max_tokens/require_reservation/files/images/store）均把 Controller 保持 BLOCKED；`boundary_deployed=False`。
- 说明：AUTH-08 的“budget”维度仍由 `authorization.py` 的独立 `BudgetLimits`/binds 校验，不属于 `EgressPolicy` 字段；测试覆盖对应的 route/model/tools/budget 授权路径（既有回归通过）。

### WD-03/04（异常/清理 fail-closed + absence）
- `watchdog.py:242-310`：异常/超时/step/dispatch 等路径统一 kill tree → 尝试 cleanup；cleanup 异常/超时/非 Mapping → `WatchdogViolation`（`SECURITY_BLOCKED`），不改报成功；`:303-310` `finally` 兜底 kill。
- `test_wd03_cleanup_failure_after_exception_is_security_blocked`、`test_wd03_exception_path_still_runs_cleanup_and_kills_tree`、`test_wd04_cleanup_failure_on_normal_completion_is_not_success` 全部通过；进程 absence 断言通过。
- 残余：测试使用 fake/hung 子进程与 synthetic cleanup；真实容器 `rm`/`ps` absence、真实 OS supervisor 权限未验证（owner 已声明）。

### OBS-01/02（reasoning 显式 policy）
- `observation.py:171-186` `validate_for_policy`：`inclusive` 时 reasoning 是 output 子集（`reasoning>output` 拒绝）；`additional` 允许独立 reasoning，但 AUTHORITATIVE 必须显式携带 reasoning，缺失不得当 0。`:238-282` `to_usage` 要求显式 `reasoning_policy`，additional 独立计入 output。
- `test_obs01_additional_reasoning_can_exceed_output_and_is_measured`（reasoning=9>output=3，受信结算 0.001035）、`test_obs02_inclusive_reasoning_greater_than_output_is_rejected`（保持 PENDING）通过。

### OBS-03（PARTIAL/MISSING 不低于保守上界）
- `observation.py:270-280`：PARTIAL/MISSING 一律 `total_input=max(reserved_input, known_input)`、`total_output=max(reserved_output, known_output)`、`cache_read=0`、`estimated=True`、`actual_cost_usd=None`（partial invoice actual 不被采用）；UNKNOWN 保持 reserved bounds。
- `test_obs03_partial_never_below_conservative_bound` 5 种形状（only input/only cache_read/完整 input+缺 output/完整 input+缺 output+provider_invoice/MISSING+provider_invoice）全部交付 `WORST_CASE_HELD`、`cost_usd == reserved 0.00112`、pending→0；`test_t_usage_01_missing_usage_holds_full_reservation` 通过。

### OBS-05/06/INT-15（伪造/无 provenance/route mismatch）
- `observation.py:322-354` `TrustedEgressProvenance` + `issue_trusted_egress_provenance`；直接构造/伪造 dict/错误 seal 被拒；`:372-475` `deliver_observation` 要求显式 reasoning_policy/cache 批准，AUTHORITATIVE 或 `provider_invoice` 无 provenance → `UNAUTHORIZED_OBSERVATION` 不结算、reservation 保持 PENDING；route/model/requested/observed/provenance 与 durable reservation 不一致 → `ROUTE_MISMATCH` 不结算；拒绝不写幂等表，受信后同 call 可合法升级；受信 provider_invoice 才记录 actual。
- 测试：`test_int15_*`、`test_obs06_*`、`test_obs05_route_or_model_mismatch_is_not_settled`、`test_forged_provenance_and_mismatched_call_id_are_rejected`、`test_untrusted_partial_remains_allowed_and_conservative` 全部通过；幂等/冲突/UNKNOWN_CALL 回归通过。

## 5. 发现

### B-G1-1（阻断 G1 验收；AUTH-08 budget 子项未实现/未测试）
task-60 明确要求 AUTH-08 覆盖“仅改 path/method/model/**budget** 而 host 不变 → Controller 拒绝 Policy 变化”。当前实现/测试只覆盖 EgressPolicy：
- `src/autoteacher_m0/security/live_controller.py:64-92` 构造器只有 `budget_scope`（字符串），没有 expected `BudgetLimits`；`:94-106` 仅把 `budget_scope` 传给 `load_execution_authorization`；`:130-132` 只逐字段比较 `EgressPolicy`（host_ports/methods/path_prefix/approved_routes/max_tokens/max_attempts/require_reservation/allow_files/allow_images/allow_store），**没有 budget caps 字段**。
- `src/autoteacher_m0/security/authorization.py:246-250,351-374` 只校验 budget 的 scope/范围/上限（`<=10` 等），**不与被批准/期望的 per-call/total/max_calls 值比较**。因此一份新签名的、范围内但改变了 budget caps 的授权不会产生 budget policy 违规。
- `tests/integration/sandbox/test_live_controller_no_key.py:219-238` 的 8 个 AUTH-08 参数是 methods/path_prefix/approved_routes/max_tokens/require_reservation/files/images/store，**没有 budget-only mutation**；`test_auth08_*` 全部通过只证明 EgressPolicy 字段覆盖，不能证明 task-60 的 budget 要求。
- Controller 整体仍 `status=BLOCKED`（外部授权/egress/watchdog 未部署）不改变这一点：AUTH-08 要求的是对 policy 变化的**具体拒绝检测**，当前没有该检测/测试。
- 修复建议（owner，不在本次审计内改）：把 expected budget caps（scope + per_call_cap_usd + total_cap_usd + max_calls）作为 Controller 构造参数/期望策略，逐项比较并产生 `BUDGET_POLICY_MISMATCH:<field>`；补一个 budget-only mutation 的新测试；或由 Lead 明确将 budget 维度从 AUTH-08 移出并更新 v0.6/task-60 验收，二者不能作为已通过。
- 这是 **P1 阻断项**（v0.6 §12 AUTH-08 为 P1；但 task-60 的 G1 交付明确要求 AUTH-08，故 G1 整体不得 PASS）。其余 A1/A2/A3/WD/OBS 测试均通过，修复应是最小增量。

### V-G1-1（中低，证据身份；非阻断）
owner 的 G1-SEC 报告/manifest 把“实现 SHA”写成 G1 之前的 **`87f44e1`**：
- `docs/M0_G1_SECURITY_REPORT.md:3`：`实现 SHA 仍 87f44e1`
- `artifacts/m0-g1-security/manifest.json:7`：`"implementation_sha": "87f44e1227…"`
- `artifacts/m0-g1-accounting/manifest.json:9`：`implementation baseline 87f44e1`

但 G1 实际实现提交是 **G1-SEC `842583d`** 与 **G1-ACC `00df577`**；HEAD=`00df577`。G1 的证据/报告应绑定 G1 代码提交（或至少同时记录 `baseline 87f44e1` 与 `implementation_commits 842583d/00df577`）。这是**证据身份/可追溯性问题，不是功能或安全缺陷**；建议 owner 通过 **新 errata 文件**（不重写旧字节）补正，并在 G2 review packet 中使用正确实现 SHA。审计本身已按 frozen commits 绑定。

### V-G1-2（低，报告自相矛盾；非阻断）
`docs/M0_G1_SECURITY_REPORT.md:49` 写“未做 G1 其余项（A4/A5/A13 的完整语义）”，但同报告第 26 行已将 **A4/AUTH-08** 标记为已修复，且 A5 属并行 G1-ACC（已实现）。该句应为笔误（很可能想写 A5/A6/A7 或 A13）；建议 errata 修正文档，不影响代码/测试结论。

### V-G1-3（条件，G1→G2 收口；非阻断）
G1 的 `TrustedEgressProvenance` 是**同进程 capability 对象 + 工厂函数**，不是密码学来源认证：任何能 import `autoteacher_m0.accounting.observation` 的代码都可调用 `issue_trusted_egress_provenance()` 取得“受信” provenance；G1 测试只证明直接构造/伪造 seal 被拒。owner 已如实声明“G2 才由可信 egress/Controller 在受信边界签发并需审计 import 点”。因此：
- **G1 离线条件通过**（显式 API 契约与 negative tests 成立）；
- **不得把 G1 解释为真实来源认证/真实 wire/invoice 已验证**；G2 必须把工厂限制在可信 egress/Controller 进程边界、审计所有 import/调用点，并结合 claim/attempt 持久化。此项进入 `OPEN_BLOCKERS.md` 的 G2 条件。

### 其他观察
- fail-first 证据真实：独立旧实现对照得到 security **26 failed/4 passed** 与 accounting **2 collection errors**，与 owner 日志一致；owner `pass1-3` 迭代日志保留未删，最终 `pass4`/170 与独立重跑一致。
- owner 的 `G1-SEC` 全量 157/1、`G1-ACC` 170 与独立重跑一致；测试未删除，旧断言更新有说明（AUTH-08/cleanup/provenance 新语义）。
- 历史证据与本审计前基线 byte 未改；LiveGate/gates/adapter/run_live 未解锁；无真实 Key/模型/HTTP。

## 6. 残余 UNVERIFIED / BLOCKED（不夸大）

0. **G1 整体因 B-G1-1（AUTH-08 budget 子项）不通过**；修复并独立复验 budget-only mutation 后才能重开 G1 PASS 评审。其余已核项不能替代该缺口。
1. 真实 Live/Key/模型/HTTP、真实 egress/Key Broker、E5-P01–P05 仍 **BLOCKED**；`LiveGate`/adapter/run_live 未改动。
2. AUTH-02 仍是纯 Python RFC8032 参考实现，非常数时间、无独立侧信道/密码学审计；只完成严格准入与负测。
3. AUTH-08 仍 inspect-only；真实 egress/Key Broker 未部署，G1 不新增 Live 入口。
4. WD-03/04 使用 fake/hung 子进程与 synthetic cleanup；真实容器/OS supervisor/absence 未验证。
5. `TrustedEgressProvenance` 是 API capability（V-G1-3），不是真实来源认证；真实 provider_invoice/账单/usage 未核对。
6. G1 未做 G2 的 A9–A11、broker claim、统一 call ID、真 SQLite/stdio Broker/FakeProvider 跨进程闭环；G1 的 PASS 不得写成 G2/Live PASS。

## 7. 证据索引

- 独立 stage：`artifacts/reviewer-g1/stage.tar`（sha256 `2bdfd4c0…`，174 files）+ `stage/`；旧实现对照 `stage-old-sec/`、`stage-old-acc/`。
- 运行：`artifacts/reviewer-g1/logs/` 与 `raw/commands.jsonl`（argv/UTC/exit/stdout/stderr hash）；容器 absence=0。
- 审计产物：`artifacts/reviewer-g1/manifest.json`、`evidence.sha256`。
- owner 交叉核对：`artifacts/m0-g1-security/`（36/36）、`artifacts/m0-g1-accounting/`（16/16）；报告 hash `0a8f6e18…`/`c20828ad…`。
