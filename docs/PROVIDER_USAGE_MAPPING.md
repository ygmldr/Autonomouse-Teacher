# ProviderObservation / usage mapping and call identity（PR4b）

> 状态：**offline accounting contract（无 Key/无网络）**。本文定义“外呼事件 → 账本状态”的标准化映射与稳定 `call_id` 关联接口；**不**声称真实 provider wire、tokenizer、账单或 invoice 已核对。真实 wire/Usage 映射仍 **UNVERIFIED / Live BLOCKED**。

## 0. 结论与边界

- 新增 `src/autoteacher_m0/accounting/observation.py`：纯 Python dataclass `ProviderObservation`、`CallIdentity`、`deliver_observation`；**不导入任何 SDK 类型/不读凭据/不发网络**。
- 账本只接受**规范化后**的 observation；未知/缺失/部分 usage **不填 0**，按 worst-case 保留：`AUTHORITATIVE→SETTLED`、`PARTIAL/MISSING→WORST_CASE_HELD`、`UNKNOWN→SETTLEMENT_UNCERTAIN`（reservation 保持 PENDING，不退款、不重试结算）。
- broker NDJSON **v1 语义不变**；只增加 reserve 消息的可选 `call_id` 字段（旧客户端不发送时行为完全不变）与账本侧关联表。
- 本 PR 只做 accounting/guard 侧接口与离线测试；PR4a 的 egress 实现完成后由 Lead 组织交叉对接（egress 生成 `CallIdentity`、reserve 时带 `call_id`、返回后投递 observation）。未完成对接前，真实 request identity/usage 仍是 UNVERIFIED。

## 1. `ProviderObservation`（14 字段，无 SDK 类型）

| 字段 | 类型 | 说明 |
|---|---|---|
| `requested_route` | str (1..128, printable) | 请求时固定 route（必填） |
| `observed_route` | str \| None | provider/egress 实际观察到的 route，未知为 None |
| `model_reported` | str \| None | provider 返回的模型名/版本，未报告为 None |
| `provider_request_id` | str \| None | provider 返回的请求 ID（受限长度/可打印） |
| `usage_raw_hash` | 64-hex \| None | 原始 usage 字节/对象的 sha256（脱敏保存；AUTHORITATIVE/PARTIAL 必填） |
| `input` | int \| None | **uncached input tokens**（不是总数） |
| `cache_read` | int \| None | cache-read tokens |
| `cache_write` | int \| None | cache-write tokens |
| `output` | int \| None | 输出 tokens（inclusive reasoning 时含 reasoning） |
| `reasoning` | int \| None | reasoning tokens（是否额外计费由 route 政策决定，见 §3） |
| `cost_estimate` | decimal string \| None | provider invoice 或明确估计；未知为 None |
| `cost_source` | enum | `provider_invoice` / `synthetic_fixture_cost` / `local_estimate` / `unknown` |
| `error_kind` | enum | `none` / `timeout` / `http_4xx` / `http_5xx` / `transport` / `sdk_error` / `unknown` |
| `complete_or_uncertain` | enum | `AUTHORITATIVE` / `PARTIAL` / `MISSING` / `UNKNOWN` |

**无字段保持 `None`，禁止用 0 代替缺失值。** `from_mapping()` 只接受这 14 个 key：未知 key、缺失 key、bool/字符串冒充计数、非法 hash/enum、AUTHORITATIVE 缺必填维度、UNKNOWN 携带计数器等一律 `ObservationSchemaError`；错误信息不嵌入原始 payload。

## 2. 四类状态与账本映射（not zero-filled）

| `complete_or_uncertain` | 含义 | accounting_status | 账本动作 |
|---|---|---|---|
| `AUTHORITATIVE` | 完整可信 usage：input/cache_read/cache_write/output 均有值，`error_kind=none`，有 `usage_raw_hash` | `SETTLED` | 用映射后的实际 tokens/cost 结算（actual cost 仅当 `cost_source=provider_invoice`） |
| `PARTIAL` | 部分维度缺失（如只有输入） | `WORST_CASE_HELD` | 缺失维度用 reservation 上界；无 cache 折扣；`estimated=true`；按 FAILED 全额 worst-case 结算 |
| `MISSING` | 完全没有 usage（T-USAGE-01） | `WORST_CASE_HELD` | 用完整 reservation 上界，不填 0，不记成功费用 |
| `UNKNOWN` | schema/transport 未知，不能相信任何计数器 | `SETTLEMENT_UNCERTAIN` | **不结算**：reservation 保持 PENDING（不退款/不释放），上层验收必须失败；后续可人工/Controller 复核 |

`to_usage(reserved_input, reserved_output, known_fee, reasoning_in_output)` 的规则：
- `AUTHORITATIVE`：`input_total = input + cache_read + cache_write`；`cached = cache_read`；`output_total = output`（`reasoning_in_output=True`，否则 `output+reasoning`）；`estimated=False`；仅 `provider_invoice` 时使用 `cost_estimate` 作为 `actual_cost_usd`。
- `PARTIAL/MISSING`：任一 input 维度缺失 → 使用 `max(reserved_input, known)` 且 cache 折扣为 0；output/reasoning 不完整 → 使用 `max(reserved_output, known)`；`estimated=True`；`actual_cost_usd` 仅在可信 invoice 时使用。
- `UNKNOWN`：直接使用完整 reservation 上界，`estimated=True`、`actual_cost_usd=None`。
- `reasoning_in_output` 必须由调用方从**已验证的 route billing policy** 明确传入，不由 observation 猜测；`reasoning > output` 且 inclusive 规则时 schema 拒收。

## 3. 稳定 call identity 与 broker 关联

```text
CallIdentity(run_id, logical_step, attempt_index, request_digest)
call_id = "call-" + sha256(canonical_json({v:1, run_id, logical_step, attempt_index, request_digest}))[0:48]
```

- 相同身份字段 → 相同 `call_id`（跨进程稳定）；任一字段变化（含 attempt_index）→ 不同 ID；长度 53 ≤ broker ID 上限 96；格式 `[A-Za-z0-9][A-Za-z0-9_.:-]*`。
- **broker v1 兼容**：reserve 消息可选 `call_id`（旧客户端不传时字节语义不变）。带 `call_id` 时 broker 在**同一事务**内建立 `budget_call_links(scope_id, call_id → reservation_id)`；重复相同映射幂等；把同一 `call_id` 指向不同 reservation 返回 `CALL_ID_CONFLICT` 并回滚，fail-closed。
- `deliver_observation(ledger, call_id, observation, reasoning_in_output=...)`：先查 link，再按 §2 结算；同一 `call_id`+同 payload 重复投递幂等（`duplicate=true`，不二次结算），不同 payload → `observation identity conflict`；未绑定的 call_id → `UNKNOWN_CALL`（不猜测、不结算）。
- PR4a 对接契约（待 Lead 组织）：egress 侧在 reserve 前生成 `CallIdentity`（run/step/attempt/request digest 来自可信 Controller，不来自候选文本），reserve 带 `call_id`；HTTP 返回后在受控进程内投递 `ProviderObservation`；不得由候选插件直接写账本。

## 4. 离线测试证据（无 Key/无 HTTP）

新增：
- `tests/unit/accounting/test_provider_observation.py`：T-USAGE-01 缺失 usage；partial usage；cache/reasoning 映射（inclusive/additional）；AUTHORITATIVE 必填维度；UNKNOWN 不填零且 reservation 保持 PENDING；unknown/missing schema 拒收；`call_id` 稳定/单射/长度；重复 deliver 幂等、不同 payload conflict、未绑定 call_id、broker call_id 不可重定向。
- `tests/integration/budget_bridge/test_observation_broker.py`：真实 stdio broker reserve 携带 `call_id` → SIGKILL → 同 DB 投递 AUTHORITATIVE 结算；PARTIAL 全额 worst-case；UNKNOWN 保持 PENDING；重启后 snapshot 仍 pending。

隔离容器（固定 rootfs/deps、network none、nonroot、只读 root）执行：**fail-first 旧 accounting 代码 collection errors 2 → PR4b 全套 accounting+budget_bridge `159 passed`**。详细 argv/UTC/exit/镜像/rootfs/deps hash/产物 hash 见 `artifacts/m0-usage-mapping/manifest.json`。

## 5. 明确 UNVERIFIED / BLOCKED（不得外推）

- **真实 provider wire/usage schema**：未观察真实 API 响应；cache/reasoning 字段名、tokenizer、reasoning 计费规则、invoice 字段均 UNVERIFIED。
- **真实账单/invoice 核对**：`cost_source=provider_invoice` 的语义只在离线 contract/测试中出现；没有真实 invoice 证据，不能声称已核对真实费用。
- **真实 HTTP attempt/retry/Files/compaction**：本 PR 不观测、不拦截；每个真实外呼是否对应一个 `call_id` 仍依赖 PR4a egress 证明。
- **provider-issued invoice cap vs local hard accounting bound**：二者不是同一概念；本 PR 只做本地 reservation/结算语义，不提供 provider 侧硬额度证明。
- 无 Live/真实 Key/真实模型/真实 HTTP；总决策与 Live 仍 BLOCKED。历史 phase5/PR1–PR3 证据与字节未改。

## 6. 非目标

本 contract 不是授权层、Key 代理、LiveGate、OS 沙箱或账单核验器；`SETTLED` 只表示“按可信 observation 映射并记账”，不等于供应商账单已对账或 Live 已批准。
