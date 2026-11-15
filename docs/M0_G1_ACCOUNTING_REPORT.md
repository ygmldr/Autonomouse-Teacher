# M0 G1-ACC — Observation/Usage 语义确定性修复（无 Key）

> 范围：v0.6 G1-ACC（A5/A6/A7；OBS-01/02/03/05/06 与 INT-15 离线部分）。本文只记录 **隔离 OCI 内离线证据**；真实 provider wire/usage/invoice 与 Live 仍 **UNVERIFIED / BLOCKED**。无真实 Key/模型/HTTP，未读 `/root/.config/autoteacher`，未改 egress/security/G2 broker claim/历史证据。

## 0. 交付摘要

| 文件 | 变化 |
|---|---|
| `src/autoteacher_m0/accounting/observation.py` | 显式 Route Billing Policy 参数化 reasoning；PARTIAL/MISSING 强制保守上界（无 cache 折扣、无部分 invoice actual）；`TrustedEgressProvenance` 来源认证、route/model 一致性校验；保留幂等/冲突/UNKNOWN_CALL/UNKNOWN→PENDING。 |
| `src/autoteacher_m0/accounting/broker_usage.py` | 新增 canonical reasoning policy 常量与 `UsagePolicy.reasoning_policy` 映射（`inclusive`/`additional`），不改变 agentUsage 解析语义。 |
| `tests/unit/accounting/test_provider_observation.py` | G1 定向回归（更新过时断言、新增 OBS/INT 用例）。 |
| `tests/integration/budget_bridge/test_observation_broker.py` | 仅更新因 G1 语义变化而过时的 deliver 调用断言（见 §5）；broker/ledger 未改。 |
| `docs/M0_G1_ACCOUNTING_REPORT.md` | 本报告。 |
| `artifacts/m0-g1-accounting/` | argv/UTC/exit、fail-first/iteration/pass 日志、stage 身份、镜像/rootfs/deps、manifest/evidence。 |

**未改**：`ledger.py`、`broker.py`（G2 claim）、`__init__.py`、egress/security 文件、历史证据、package/lock。仓库 worktree 中 `security/*`、`docs/M0_G1_SECURITY_REPORT.md` 等为并行 G1-SEC 任务产物，未触碰。

## 1. A5 / OBS-01 / OBS-02 — reasoning 口径显式策略化

**旧行为（已验证）**：`ProviderObservation.__post_init__` 对 AUTHORITATIVE 无条件执行 `reasoning > output → 拒绝`（隐含 inclusive 假设）；`to_usage(reasoning_in_output: bool = True)` 另有布尔参数，语义不统一；additional 模式下 reasoning>output 无法表示（独立计费 reasoning 无法通过 schema）。

**修复（observation.py）**：
- 结构校验不再包含 reasoning 约束；新增 `normalize_reasoning_policy()`（仅接受 `inclusive` / `additional`，无默认值）与 `ProviderObservation.validate_for_policy(policy)`：
  - `inclusive`：reasoning 是 output 的子集，`reasoning > output` 拒绝；reasoning 缺失允许（总 output 已包含）。
  - `additional`：reasoning 独立计费，允许 `reasoning > output`；AUTHORITATIVE 必须显式携带 reasoning 计数，**缺失不得当 0 通过**。
- `to_usage()` 与 `deliver_observation()` 均要求显式 `reasoning_policy`；`broker_usage.UsagePolicy.reasoning_policy` 提供由已验证 route policy 到 `inclusive/additional` 的唯一映射，避免手工猜口径。

**测试（fail-first→pass）**：
- `test_obs01_additional_reasoning_can_exceed_output_and_is_measured`：additional、reasoning=9>output=3 可表示并计量，受信结算 `0.001035`。
- `test_obs02_inclusive_reasoning_greater_than_output_is_rejected`：inclusive 下 schema 拒绝且 reservation 保持 PENDING、不结算。
- `test_additional_policy_requires_explicit_reasoning_count`：additional 缺 reasoning 拒绝；inclusive 允许。
- `test_reasoning_policy_and_cache_approval_must_be_explicit` / `test_route_policy_helpers_map_inclusive_and_additional`。

## 2. A6 / OBS-03 — PARTIAL/MISSING 不低于保守上界

**旧行为（PR4b）**：PARTIAL 在 input 三维完整时会保留 cache_read 折扣；PARTIAL/MISSING 在 `cost_source=provider_invoice` 时会把 `cost_estimate` 放入 `actual_cost_usd`，而 ledger 只对“无 actual 的 estimated”施加 `max(cost, reserved)` 地板 → 完整 input + 缺失 output + 声称 provider_invoice 的路径可能以低于保守 bound 的费用结算（残余路径）。

**修复（observation.py）**：
- PARTIAL/MISSING：`total_input = max(reserved_input, known_input)`、`total_output = max(reserved_output, known_output)`，`cache_read=0`，`estimated=True`，`actual_cost_usd=None`（即使 cost_source=provider_invoice 也不采用部分 invoice 金额）。
- cache 折扣仅在 **AUTHORITATIVE** 且调用方显式传入 `cache_discount_approved=True`（来自已验证 route policy）时应用；未批准则不折扣。PARTIAL/MISSING 一律不折扣。
- broker 侧 reserve/write 语义未改；`known_fee` 仍由 reservation 固化传入，保守金额含 fee。

**测试**：`test_obs03_partial_never_below_conservative_bound` 参数化 5 种形状（only input、only cache_read、完整 input+缺 output、完整 input+缺 output+provider_invoice actual、MISSING+provider_invoice actual），逐一断言交付为 `WORST_CASE_HELD`、`settlement.cost_usd == "0.00112"`（= 100 input + 10 output 的 reserved cost）、`status=FAILED`、pending→0；`test_partial_usage_holds_worst_case_not_zero`、`test_t_usage_01_missing_usage_holds_full_reservation`、`test_authoritative_cache_discount_requires_route_approval`。

## 3. A7 / OBS-05 / OBS-06 / INT-15（离线部分）— 可信来源认证

**旧行为（PR4b）**：`deliver_observation` 仅凭 `call_id` link 找 reservation，然后直接信任 caller 传入的 `ProviderObservation`；AUTHORITATIVE/`provider_invoice` 可由任意调用者构造并获得结算；无 route/model/来源校验。

**修复（observation.py）**：
- 新增 `TrustedEgressProvenance`（含私有 seal 的 capability）与 `issue_trusted_egress_provenance()` 工厂；直接构造或伪造 dict/对象 → `ObservationSchemaError("untrusted provenance")`。G1 只定义并强制接口，**G2 才由可信 egress/Controller 在受信边界调用工厂**（工厂本身不是签名认证；它用于把“来源认证”强制成显式 API 参数，杜绝默认信任 caller）。
- `deliver_observation`：
  - `AUTHORITATIVE` 或 `cost_source=provider_invoice` 且无 provenance → 返回 `UNAUTHORIZED_OBSERVATION`，**不结算**，reservation 保持 PENDING；该拒绝不写入 observation 幂等表，后续受信 egress 仍可合法结算同一 call（可审计升级）。
  - 期望 route/model 来自 durable reservation/link：`requested_route`/`observed_route`/`model_reported` 与 reservation 不一致 → `ROUTE_MISMATCH`（SETTLEMENT_UNCERTAIN、不结算、不写幂等表）；provenance 自身 route/model 与 observation 或 reservation 不一致同样拒绝。
  - 受信 `provider_invoice` 且完整 AUTHORITATIVE 才允许 `actual_cost_usd`；未受信 invoice 一律拒绝（OBS-06，绝不伪称真实账单）。
  - `PARTIAL/MISSING/UNKNOWN` 无 provenance 仍可投递，但只能走 §2 保守路径；UNKNOWN 保持 PENDING/SETTLEMENT_UNCERTAIN。
- 既有幂等/冲突/UNKNOWN_CALL 语义保留：`observation_once` 对已结算/UNKNOWN 结果按 call_id 幂等；不同 payload 冲突；未绑定 call → UNKNOWN_CALL。

**测试**：
- `test_int15_untrusted_authoritative_does_not_settle_then_trusted_can_upgrade`
- `test_obs06_untrusted_provider_invoice_is_rejected`（受信后 actual 金额被记录为 `cost_kind=actual`）
- `test_obs05_route_or_model_mismatch_is_not_settled`（requested/observed/model/ provenance 四类 mismatch）
- `test_forged_provenance_and_mismatched_call_id_are_rejected`
- `test_untrusted_partial_remains_allowed_and_conservative`
- `test_authoritative_delivery_settles_and_duplicate_is_idempotent`、`test_unknown_observation_stays_pending_uncertain`、`test_delivery_requires_bound_call_identity`

## 4. broker v1 兼容 / blast radius

- **未改** `broker.py`、`ledger.py`、`__init__.py`、NDJSON 字段/op、claim/call_id 关联表；broker v1 与历史 append-only DB 语义不变。G2 的 claim 工作与 egress 接线不在本任务。
- `deliver_observation` 为 in-process accounting API（无网络/凭据），不计入 broker v1 协议；签名变化已更新本仓库内唯一调用方（`tests/unit/accounting`、`tests/integration/budget_bridge`）。
- 旧 PR4b 测试中“无 provenance 的 AUTHORITATIVE 直接得到 SETTLED”以及 `to_usage`/`deliver_observation` 的旧参数形式**因 G1 语义变化而过时**：已更新断言而非删除用例（OBS/INT 新断言替代），并在 test 文件注释保留原因；历史审计/证据字节未改。

## 5. 执行环境与测试计数（fail-first → PASS）

- 环境：固定 digest rootfs（`25491e45…`）+ `/deps`（`e07729d7…`），`--network none`、`--http-proxy=false`、`--unsetenv-all`、uid 65534、`--read-only`、cap drop ALL、no-new-privileges、pids 64、512m、tmpfs `/tmp`+`/work` noexec；宿主未跑 pytest。
- **fail-first（旧 accounting 代码 + 新测试）**：2 collection errors（`ImportError: issue_trusted_egress_provenance` / 新 API 缺失），exit 2（`raw/failfirst2.log`）。
- **PASS（G1 实现 + 全套 accounting/budget_bridge）**：**170 passed**，exit 0（`raw/pass4.log`；迭代日志 `pass1-3.log` 记录本地修复过程中的 2 个测试构造错误，最终 pass 为准）。
- 0 真实模型/HTTP/Key；容器 absence 与 git 状态见 artifact raw/manifest。

## 6. 残余 UNVERIFIED / 未做

1. **真实 provider wire/usage schema、cache/reasoning 字段、invoice 字段**仍未观察；`provider_invoice` 只在离线 contract/测试中有受信 provenance，不能声称真实账单已核对。
2. **provenance 工厂不是密码学签名**：G1 只把“来源认证”变成必须显式由受信边界提供的 capability；G2 必须在可信 egress/Controller 进程边界签发并接线，且需独立审计工厂调用点，防止候选代码直接 import。
3. **route/model 校验依赖 durable reservation**；request_digest 与 reservation 的持久绑定（attempt/claim）仍留 G2/INT-07/17。
4. **真实 HTTP attempt/retry/Files/compaction 与 provider-side invoice cap** 未在本任务验证；本地 hard accounting bound 与 provider 硬额度仍是不同概念。
5. 未改 `broker.py`/`ledger.py`；若 G2 需要 claim/attempt 持久化，由 G2 任务按协议版本化处理。
6. 未提交 Git（按任务要求）；`security/*`、`docs/M0_G1_SECURITY_REPORT.md` 等并行 G1-SEC worktree 文件未触碰。
