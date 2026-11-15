# M0 Request Binding Contract（草案 v0.1，待 Lead 批准）

- 任务：`task-80` A2；日期：2026-11-15 UTC；状态：**APPROVED — Option A（Lead 审阅通过，2026-11-15）**
- 批准条件已纳入：成对 expected 字段、旧 v1 双向兼容、BIND-01 用真实 SQLite/stdio ledger 验证、canonical 细节与“claimer 调用前完成检查”。
- 范围：离线/无 Key 的请求绑定契约与 A 阶段可验证 egress 侧校验；**本草案不授权修改 broker/ledger 协议**。任何 broker/ledger 变更须 Lead 批准后另行实现并测试。
- 相关：`docs/ADR-002-unified-call-identity.md`、`docs/M0_G2L1_FINDINGS.md`、v0.7 §5/§6.4。

## 1. 目的与非目标

**目的**：消除“Reservation=A/Model=A、实际待发送=B/Model=B，两者都在 allowlist，claim 仍成功”的本地绑定缺口；明确受信请求摘要的唯一计算责任。

**非目标**：不声称远端/provider exactly-once；不做真实 wire/usage/账单验证；不替代 G3 外部 egress/Key Broker；不改 v1 旧 op 语义。

## 2. 受信 `PreparedProviderRequest` 字段

由可信 Controller/Bridge 在 reserve 后、send 前构造；候选/模型输出不得直接提供 `request_digest`。

| 字段 | 类型/约束 | 说明 |
|---|---|---|
| `schema_version` | str，固定 `"m0.prepared.v1"` | 规范化版本 |
| `scope_id` | str 非空 | accounting scope |
| `run_id` | str 非空 | 受信 run |
| `logical_step` | int >=0 | 逻辑 step |
| `attempt_index` | int >=0 | 逻辑 attempt |
| `route_id` | str 非空 | 实际待发送 Route |
| `provider` | str 非空 | provider id（如 `opencode-go`） |
| `model` | str 非空 | 实际待发送 Model |
| `host` | str 非空 | 实际 host |
| `port` | int 1..65535 | 实际 port |
| `method` | str 非空 | 实际 HTTP method |
| `path` | str 以 `/` 开头 | 实际 path |
| `stream` | bool | 实际 stream |
| `max_output_tokens` | int >=1 | 实际 max tokens |
| `system` | str（可空） | 实际 system 内容 |
| `messages` | tuple[Mapping,...] | 实际消息（canonical JSON 可序列化） |
| `tools` | tuple[Mapping,...] | 实际工具 schema（空表示无工具） |
| `response_format` | Mapping/None | 实际 response format |
| `retry_policy` | Mapping/None | 受信 retry policy（不参与远端 claim 唯一性） |
| `has_files` | bool | 实际文件使用 |
| `has_images` | bool | 实际图片使用 |
| `store` | bool | 实际 store |
| `call_id` | `call-<48hex>` | 由受信端按 ADR-002 生成 |
| `request_digest` | 64 hex | 受信端计算；不信任候选传入 |

## 3. 规范序列化与 SHA-256

- 取 `_PREPARED_DIGEST_FIELDS`（全部字段，**排除 `call_id`/`request_digest` 自身**；reservation_id 不属于 Prepared 字段），按 JSON `sort_keys=True`、`separators=(",",":")`、UTF-8、`ensure_ascii=False`。
- **明确拒绝**：float NaN/±Inf；非字符串 mapping keys（递归）；非 JSON 类型（bytes/自定义对象等）；非有限值由 `allow_nan=False` + `_canonical_value` 双重拒绝。
- `request_digest = sha256(canonical_bytes).hexdigest()`（64 hex）。
- `call_id = "call-" + sha256(canonical_json({"v":1,"run_id":...,"logical_step":...,"attempt_index":...,"request_digest":...}))[:48]`；**reservation_id 不参与 call_id 生成**（ADR-002 不变）。
- 计算责任：**受信 Controller/Bridge 计算并写入 PreparedProviderRequest**；egress 收到后必须用同一 canonical 函数重新计算，并同时核对 `prepared.call_id`/`prepared.request_digest`/`request.call_id`/`request.request_digest`。候选传入的 digest 只作为待核对值，不作为事实。
- ADR-002 完全一致：`call_id = "call-"+sha256(canonical_json({"v":1,"run_id","logical_step","attempt_index","request_digest"}))[:48]`；**reservation_id 不参与**。

## 4. claim 绑定语义

1. **必要条件**：Reservation 的 `(route_id,model)` 在 allowlist；`call_id` 已绑定 reservation；`request_digest` 格式合法。
2. **新增充分条件（A2 目标）**：实际请求的 Route/Model/Digest 必须与 Reservation 对应值一致；`allowed_routes` 仅是必要条件，不是证明。
3. **结算/发送绑定**：`claim_dispatch_for_request(prepared, request)` 必须在调用 claimer **之前**完成（任何一项失败 → deny，**claimer 调用数=0**）：
   - 重算 prepared digest；prepared.call_id 重算/核对；
   - prepared 与 `EgressRequest` 的 route/model/host/port/method/path/stream/max_tokens/flags/call_id/digest 逐项一致；
   - 若提供 `expected_reservation_route_model`（受信 reservation 视图），prepared 必须等于它；不一致 → `RESERVATION_REQUEST_MISMATCH`，claimer 调用数=0；
   - 若提供 `approved_tool_schemas`，prepared.tools 必须在其内；未批准/未知工具 → `TOOL_SCHEMA_NOT_APPROVED`，claimer 调用数=0；
   - 以上通过后才调用 claimer；失败不产生 `DispatchPermission`，provider 调用=0。
4. **旧 v1 兼容**：旧 `snapshot/reserve/settle/fail` 字段/语义不变；旧客户端不发送新字段时仍按旧行为；**旧客户端不得因省略字段获得无需 Claim 的发送权**。新字段/新 op 必须 additive、可选、有默认拒绝语义。

## 5. 最小协议方案（建议，待 Lead 批准）

**建议采用 Option A（ledger 权威比较）**：
- `claim` op 增加可选 `expected_route_id`、`expected_model`（成对出现；旧客户端可省略）。
- broker/ledger `claim_dispatch(..., expected_route_id=None, expected_model=None)`：若提供，与 reservation row 的 `(route_id,model)` 比较，不一致 → `ROUTE_MISMATCH`（不写 claim、不 dispatch）；同时将 `request_digest`/expected fields 写入/返回 claim 审计字段。
- claim 成功响应可 additive 返回 `route_id/model`（供 egress/审计核对），不改变旧字段。
- 迁移：G2 `StdioBrokerClaimer` 升级为发送 expected route/model 的 `PreparedClaimer`；旧 claimer 仍可跑旧测试；新 egress 对“不支持绑定的旧 claimer”可显式降级为 deny（`CLAIM_BINDING_UNSUPPORTED`）或仅在测试中显式 policy-only，不能静默发送。

**Option B（claim 响应返回 reservation route/model，egress 比较）**：不强制 ledger 比较，旧客户端更兼容；但依赖 egress 客户端正确比较，且旧客户端忽略响应即可绕过，安全性弱于 A。**不推荐作为唯一防线**。

**Option C（claim 表增加 route/model 并唯一约束）**：更强但协议/表迁移大；可作 G3 方向，不是本轮最小方案。

## 6. A 阶段可验证 vs G3_DEPENDENCY

| 项 | A 阶段可验证 | G3_DEPENDENCY |
|---|---|---|
| Prepared 字段/规范 JSON/digest 重算 | ✅ egress/unit | — |
| prepared↔request 逐字段绑定（含 tools schema 输入） | ✅ egress + fake/real claimer | 远端 wire 一致性 |
| expected reservation route/model 比较 | ✅ egress 若调用方提供受信 reservation 视图 | broker/ledger 权威读取 reservation 并 ROUTE_MISMATCH（Option A 批准后） |
| claim 重放/重复至多一次 | ✅ 现有 real SQLite/stdio claim | 远端 provider exactly-once |
| 真实 provider wire/usage/invoice/账单 | — | ❌ G3/Live |
| tool schema 的正式审批/注册表 | ⚠️ A 可做输入校验/负例 | G3 策略来源/注册表 |
| 旧 v1 客户端兼容 | ✅ 旧 op 回归 | 旧真实客户端未验证 |

## 7. BIND-01..08 映射

| ID | 场景 | A 阶段 | G3 |
|---|---|---|---|
| BIND-01 | Reservation=A/Model=A vs 实际 B/Model=B（均 allowlist） | egress 侧 expected reservation 比较 → deny，provider=0 | ledger 权威 ROUTE_MISMATCH（Option A） |
| BIND-02 | 消息/摘要变更 | digest 重算不一致 → deny，provider=0 | 远端 wire digest |
| BIND-03 | maxTokens 256→512 | prepared↔request 字段不一致 → deny，provider=0 | provider 实际 tokens |
| BIND-04 | method/path/host 绕过 | prepared↔request 不一致 → deny，provider=0 | wire 请求 |
| BIND-05 | 未批准 tools schema | egress approved_tool_schemas 负例 → deny，provider=0 | 正式 tool 审批注册表 |
| BIND-06 | 重复 claim/重放至多一次 | real SQLite/stdio claim 测试 | 远端 exactly-once |
| BIND-07 | 未修改成功一次并正确关联 ledger | real SQLite/stdio + FakeProvider | 真实账单 |
| BIND-08 | 只有 reserve.dispatch_allowed 无 claim | 无 permission → provider=0 | — |

## 8. 批准与实施状态

- Lead 已批准 **Option A** 及 4 个必须条件：成对 expected 字段；broker/ledger 写入前与 reservation row 比较（`ROUTE_MISMATCH`，不写 claim、0 dispatch）；claim 成功响应 additive 返回 route/model；claim 表不新增迁移。
- 实施：egress `PreparedProviderRequest`/canonical digest/`claim_dispatch_for_request` + `BoundBrokerClaimer`；broker/ledger additive expected 字段；BIND-01 真实 SQLite/stdio ledger 测试；旧 v1 客户端不带 expected 字段仍成功（明确残余）；新 egress 对无 bound claimer 显式 `CLAIM_BINDING_UNSUPPORTED` deny。
- `claim_dispatch_for_request()` 在任何 claimer 调用前完成重算/逐字段比对；失败 claimer 调用数=0。
- BIND-02..05 的 egress 负例为 A 可证；真实 wire digest、正式 tool 注册表、远端 exactly-once 仍 **G3_DEPENDENCY**，不写 PASS。
