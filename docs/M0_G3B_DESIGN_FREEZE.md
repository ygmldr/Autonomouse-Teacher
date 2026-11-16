# M0 G3-B — 设计冻结（B0 输出，供 B1/B2 并行实现）

> Gate：**G3-B / B0-01..B0-04**；Owner：broker-docs（B0）；实现者：B1/B2/B3/B4 独立 Agent
> 基线：`docs/M0_G3B_BASELINE.md`（HEAD `a507e25`，父 `64b057b`）；本文件**不是**测试 PASS、不是 OS 信任边界证明、不是 Live 授权。
> 任务书：`docs/Autonomous_Teacher_M0_G3B_Trusted_Bridge_Agent_Execution_Plan_v1.0.md`；证据矩阵：`docs/Autonomous_Teacher_M0_G3B_Review_Evidence_Matrix_v1.0.csv`（实际 33 个 ID）。
> **B1/B2 只能按本文件的接口/状态机/错误码/字节定义实现；任何变更回到 Lead 重新冻结。**

## 0. 签核状态与边界

- **B0 完成范围**：身份/环境/API 盘点、Route Tuple、Admission、传输/所有权、接口契约、测试分配。
- **B0-02 不可签 PASS**：同容器同 uid；只能 `PASS_FOR_IN_PROCESS_INTEGRATION_ONLY`，OS Trust Boundary `BLOCKED`。
- **禁止**：真实 Key/模型/外部 HTTP/Live；修改 `gates.py`/`dsh_adapter.py`/`scripts/run_live.sh`；修改 G2-L1/G3-A 历史证据/Packet；生产路径调用旧 unbound `claim_dispatch()`。
- 本文所有“已验证”只表示源码/只读探针一致；实现行为需 B1–B4 重新测试。

## 1. API Reality Matrix（现场源码）

### 1.1 DSH 公开 Adapter 与类型（target stage，真实 0.2.2-rc.2）

| 调用点 | 源码路径:行 | 契约 | 已测? | G3-B 适配 |
|---|---|---|---|---|
| `LlmAdapter` 抽象类 | target `@deepseek-ai/dsh-llm/src/index.ts:223` | 抽象 `stream(options): AsyncIterable<StreamChunk>`；可覆写 `providerRetryPolicy`/`resolveModel`/`providerInfo` | G3-A 已用 | B1 新 adapter 继承该类；只实现 `stream`/`providerRetryPolicy`/`resolveModel` |
| `ctx.llm.registerAdapter` | `src/index.ts:416` | `registerAdapter(providers: string[], adapter): AdapterRegistrationHandle`；重复 provider 抛 `DUPLICATE_ADAPTER` | G3-A 已用 | B1 注册 `["offline-test-only-g3b"]`；provider 名固定、无映射 |
| `GenerateOptions` | `src/types.ts:564-606` | 字段：`provider`、`model`、`reasoningEffort?`、`messages[]`、`system?`、`tools?`、`toolHistory?`、`temperature?`、`maxTokens?`、`stop?`、`signal?`、`sessionId?`、`purpose?` | G3-A 读取 `messages/tools/system/maxTokens/sessionId/signal` | B1 只读取这些字段；不读取/信任任何 `call_id/reservation/claim` 字段（GenerateOptions 无此字段） |
| `StreamChunk` | `src/types.ts:496-508` | `block-start`/`text-delta`/`reasoning-delta`/`tool-call-delta`/`block-end`/`usage`/`finish`；usage 在 finish 前；finish 终结 | G3-A 已用 | B1 规范化后只向 DSH 产生白名单 chunk；Controller 不直接注入 DSH 内部事件 |
| `providerRetryPolicy` | `src/index.ts:238` | 返回 `ResolvedRetryPolicy`；G3-A 返回 `maxRetries:0` | G3-A 已用 | B1 固定 `mode:'normal', maxRetries:0, retryableCodes:[]`；禁隐式 retry |
| `resolveModel` | `spikes/g3a-provider-bridge/src/index.ts:260-271` | 返回 provider/model/context/maxTokens 等 | G3-A 已用 | B1 仅接受 `offline-test-only-g3b/fixture-bridge-v1`；拒绝其他 route/model |
| G3-A Adapter 注册/stream/spawn | `spikes/g3a-provider-bridge/src/index.ts:247-497` | 真实 `stream` 入口；当前 `spawn(python, [fake])` at `:323` | G3-A PASS（限定） | **必须改**：G3-B adapter 不 spawn、不读 DB/Key；仅连接固定 UDS `/work/g3b/bridge.sock`；新增独立副本 `spikes/g3b-provider-bridge/` |

### 1.2 Egress / Prepared / Claim / Transport（当前 HEAD）

| 调用点 | 源码路径:行 | 契约/返回/异常 | 已测? | G3-B 适配 |
|---|---|---|---|---|
| `ClaimResult` | `security/egress.py:59-66` | `claimed: bool, code, reasons, claim: Mapping|None` | G2-L1 | B2 BrokerClaimer 返回该对象 |
| `BrokerClaimer.claim` | `egress.py:68-72` | 旧 unbound claim 接口 | G2 旧路径 | **G3-B 不调用** |
| `BoundBrokerClaimer.claim_bound` | `egress.py:75-80` | 需要 `expected_route_id/expected_model` | G2-L1 | B2 只实现/使用该协议 |
| `EgressRequest` | `egress.py:84-101` | 字段：`logical_stream_id,reservation_id,attempt_ordinal,route_id,model,host,port,method,path,stream,max_tokens,has_files,has_images,store,estimated_cost_usd,call_id,request_digest` | G2-L1 | B2 构造 immutable request；host/port/path 为 B0 冻结 Fake 逻辑目标 |
| `EgressPolicy` | `egress.py:105-118` | 默认 host `opencode.ai:443`、path `/inference/go/`、allowlist `("opencode-go","deepseek-v4.1-flash")` | G2 默认 | **禁止默认**；B2 构造 G3-B 自定义 policy（见 §2） |
| `PreparedProviderRequest` | `egress.py:123-154` | `_PREPARED_DIGEST_FIELDS`（`egress.py:157-162`）覆盖 22 字段；`call_id/request_digest` 不含在 digest | G2-L1 | B2 Controller 构造；字段严格校验 |
| `prepared_schema_error` | `egress.py:169-219` | 固定 `schema_version=='m0.prepared.v1'`；严格类型/路径/run_id/NaN/嵌套；返回错误码或 None | G2-L1.2（FIXED） | B2 在 claim 前调用 |
| `prepared_request_digest` | `egress.py:222-223` | SHA-256(canonical_json(payload)) | G2-L1 | B2 用于 `call_id` 与 claim |
| `prepared_call_id` | `egress.py:226-232` | `call-<48hex>`，与 `call_identity.derive_call_id` 一致（canonical_json 统一） | G2-L1.2（FIXED） | B2 只使用该值 |
| `DispatchPermission` | `egress.py:249-257` | 私有 capability；含 claim/call_id/digest/stream/reservation/attempt/route_model | G2-L1 | B2 不构造，只能由 boundary 签发 |
| `EgressBoundary.claim_dispatch_for_request` | `egress.py:543-605` | 校验 Prepared schema/digest/call_id/request 字段/expected reservation tuple/tool schema；失败 `EgressDecision(False,reasons)`，provider/claimer 0；成功调用 `_claim_with(expected_binding=...)` | G2-L1 | B2 唯一准入入口；旧 `claim_dispatch()`（`:528-535`）禁用 |
| `EgressBoundary.consume_permission` | `egress.py:685-701` | 进程内 object identity+字段匹配，一次消费；非跨进程密码学授权 | G2-L1 | 仅 `TrustedEgressTransport`/B2 trusted send 使用一次 |
| `TrustedEgressTransport.dispatch` | `egress.py:704-810` | 先 `consume_permission`；无 permission/无 provider → `PRE_DISPATCH_DENIED`；进入 provider 前先 `mark_dispatch_attempt_started`，异常返回 `ATTEMPT_STARTED`/`BILLABLE_UNKNOWN`；返回 `call_id,dispatched,classification,attempt_started,provider_invoked,claim,http_status,state,usage_known,worst_case_conservative,retry_attempted,provider_calls,provider_invocations,http_attempts,scenario` | G2-L1.2（T1 FIXED） | B2 用它执行唯一发送；**当前返回值不含 `sent_payload_digest`/receipt**（见 §1.3） |
| `_permission_matches` | `egress.py:671-683` | 校验 claim claimed + call/request/reservation/attempt/route_model 全匹配 | G2-L1 | B2 不绕过 |

**Trusted transport 的 payload 证据缺口（B0 明示）**：当前 `TrustedEgressTransport.dispatch` 返回字段（`:799-810`）**没有** `sent_payload_digest`/`raw_length`/`receipt`，它只接收 `EgressRequest` 与 provider callable，不能携带精确发送字节。G3-B 的 Controller 仍可用该 transport 完成 permission 单次消费与 attempt-start 语义：provider callable 必须绑定**发送前固定的 `payload_bytes`**（Controller 闭包），`FakeBackend.send_exact_bytes` 在写 stdin 前记录 `sent_payload_digest` 并返回 receipt；Controller 再把 `approved_payload_digest`、该 `sent_payload_digest`、receipt 的 `raw_sha256` 做三方等值断言（B2-06）。若 Lead/Reviewer 要求 digest 由 transport 返回/校验，则需 additive 扩展 `dispatch`（O-2 选项②，修改 `security/egress.py`，需批准）。

### 1.3 Broker 5 op / Ledger / Observation / Usage 兼容性（关键）

Broker 协议为 stdio NDJSON；`v=1`；`snapshot/reserve/claim/settle/fail`：

| op | 源码 | 请求（严格 key） | 响应/语义 |
|---|---|---|---|
| snapshot | `broker.py:150-151,211-213` | `{v,id,op}` | `ok:true, code:SNAPSHOT, snapshot{requests,pending,spent_usd,reserved_usd,committed_usd,input_tokens,output_tokens,blocked,routes,claims}`；不写 journal |
| reserve | `broker.py:152-170,219-251` | `{v,id,op,task_id,route_id,model,purpose,input_tokens,output_tokens,retry, call_id?}` | route/model 必须匹配启动 policy（`_ROUTE/_MODEL`，`broker.py:23-24`）；成功 `code:RESERVED, dispatch_allowed:true, reservation_id, reservation`；`call_id` canonical 且 durable link；不是发送许可 |
| claim | `broker.py:171-190,320-332` | `{v,id,op,call_id,reservation_id,request_digest, expected_route_id?,expected_model?}` | `expected` 成对；成功 `code:CLAIMED, dispatch_allowed:true, claim{...}`；重复 `ALREADY_CLAIMED`（dispatch false）；冲突 `CALL_ID_CONFLICT`/`RESERVATION_ALREADY_CLAIMED`/`CALL_LINK_MISMATCH`/`UNBOUND_CALL`；不写 journal |
| settle/fail | `broker.py:191-198,253-301` | `{v,id,op,reservation_id,usage}` | `usage` 映射见下；成功 `code:SETTLED/FAILED, settlement{...}, usage_mapping`；unknown/already/invalid 由同事务 precheck 返回且**不写 journal**（T4 FIXED） |
| journal/capacity | `ledger.py:307-327`；`broker.py:204-228` | — | 同 id 幂等；reserve 容量 `count+pending+2<=max_messages`；snapshot/claim 不占 journal；settle/fail 合法完成才写 |

Ledger 真实 API：`bind_call` `ledger.py:135`、`claim_dispatch` `:199`、`claim_for_call` `:282`、`reserve` `:339`、`settle` `:384`、`snapshot` `:424`、`journal_once` `:307`、`observation_once` `:170`；`BudgetLedger` 以 SQLite append-only reservation + journal 为唯一账本。

**Observation → Broker settle 形状（B0 关键结论）**：

- `ProviderObservation.to_usage()`（`observation.py:235-279`）返回进程内 **`Usage` dataclass**（`usage.py`：`input_tokens/output_tokens/cached_input_tokens/estimated/actual_cost_usd/extra_fees_usd`）。
- Broker `settle/fail` 期望 **JSON `usage` mapping**（`broker_usage.py:56-61` 的 `USAGE_KEYS`：`inputTokens/cacheReadTokens/cacheWriteTokens/outputTokens/reasoningTokens/totalTokens/actual_cost_usd`）；`official_usage()`（`:69-97`）要求 `inputTokens` 是 **uncached**，cache 两个维度独立，`cacheReadTokens` 只在完整 input 时保留，缺失维度走 `max(reserved_bound, known)` 且 `estimated=True`。
- **直接不兼容**：`Usage` dataclass 不能直接作为 Broker JSON；且 `Usage` 已把 `input+cache_read+cache_write` 合并为 `input_tokens`、丢掉了 `cache_write`/`reasoning` 的原始维度，若把 `Usage.input_tokens` 映射成 `inputTokens` 会重复计数并丢失完整性语义。`to_usage()` 的 `actual_cost_usd` 也不能用于 synthetic。
- **最小适配（B0 实测通过）**：Controller 保留 **原始 observation 字段**（`input/cache_read/cache_write/output/reasoning/cost_estimate/cost_source/complete_or_uncertain`），按下列表构造 Broker `usage`；再调用 `settle`（完全 AUTHORITATIVE/complete）或 `fail`（PARTIAL/MISSING/UNKNOWN，保守 `FAILED`）。B0 在固定无 Key 容器内对 AUTH/PARTIAL/MISSING 三种形状验证：`ProviderObservation.to_usage(...)` 与 `official_usage(mapped_raw, ...)` 返回的 `Usage` **三个用例完全相等**（`estimated`、input/output/cached/fee 均一致）。因此 **无需新增 broker op**；仅需 Controller 适配层，`to_usage()` 用作交叉校验（预期值），不作为 Broker 输入。
  - `inputTokens = obs.input`
  - `cacheReadTokens = obs.cache_read`（仅当 route policy 允许 cache 折扣且完整；PARTIAL 时可为 None）
  - `cacheWriteTokens = obs.cache_write`
  - `outputTokens = obs.output`
  - `reasoningTokens = obs.reasoning`（inclusive 策略可省略；additional 必须保留）
  - 不发送 `actual_cost_usd`（synthetic；provider_invoice 在 G3-B 禁止）
  - `complete_or_uncertain != AUTHORITATIVE` → 使用 `fail` 而不是 `settle`；UNKNOWN 可传 `usage:null`/`{}`，Broker 会走 reserved bounds；空/部分不得填 0。
- **替代方案（仅作为 Lead 待签核 O-3）**：如果 B2 需要单一 `to_usage` 输出/新增 broker op（如 `settle_observation`），必须先由 Lead 批准；本设计默认 **Option A（Controller raw mapping，无协议变更）**。

`deliver_observation`（`observation.py:339-…`）需要 in-process `BudgetLedger` 与 trusted provenance；G3-B 为保持 Broker 唯一账本权威，**不采用**它作为主路径（可只用于 Controller 内部交叉验证/测试），除非 Lead 另行批准。

### 1.4 Plugins / SDK / G3-A 输入

| 调用点 | 源码 | 契约/用途 | 已测? | G3-B 适配 |
|---|---|---|---|---|
| Guard 注册 | `plugins/runtime-budget-guard/src/index.ts:739-775` | `apply(ctx, rawConfig)`；`ctx.on('llm/stream', ..., {prepend:true})`；reserve before `next()`, finally settle/fail；Hook `RBG_*` | 原生 15/15；未与 Bridge 组合 | B3 组合；Guard 只做预检/请求，**Broker 唯一 Reserve 权威**（见 O-4） |
| Guard policy 校验 | 同上 `:199-201,254-289` | provider 必须 `offline-test-only-*`，model `fixture-*`；route/model 必须等于 Broker policy | 原生 | 必须用 §2 Tuple；maxProviderRetries=0 |
| Skill 注册 | `plugins/skill-lookup/src/index.ts:87-92` | `ctx.tools.register(defineTool('skill_lookup'))`；固定 fixture schema | G3-A tool turn | B3 复用；Registry 必须来自真实 runtime，不用 dump-config 代替 |
| SDK spawn | `artifacts/foundation/deps/deepseek_harness/client.py:89-99` | `subprocess.Popen(args, stdin/out/err=PIPE,…)`，**无 `pass_fds`**；不继承额外 FD | G3-A | **继承 FD/pipe 不可行**；UDS 是唯一可行候选传输 |
| SDK API | `api.py:102-108` | `DeepSeekHarness` 拥有 runtime 子进程；`run/resume_session` | G3-A | B1/B3 复用；不传 Key/env 授权 |
| G3-A fake receipt | `fake/fake_provider.py:125-161` | raw stdin SHA256、mode、usage、nonce?（现版本无 nonce）、UTC、pid | G3-A | B2 新 G3-B fake 契约（§5.6）；nonce/raw_length/received-counter 必须新增 |
| G3-A worker/suite | `run/worker.py:122-180`、`run/suite.py:200-338` | 真实 harness、resume、tool、EOF/error/cancel、merged config | G3-A 6 cases | B1/B3 复制为 `spikes/g3b-provider-bridge/run/*`；移除插件 spawn fake；新增 G3-B 场景 |

## 2. 三层 Route/Model 统一（B0-03）

**冻结 Tuple**：

```text
route_id   = offline-test-only-g3b
provider   = offline-test-only-g3b      # DSH Adapter provider == budget route，无显示/预算映射
model      = fixture-bridge-v1
fake target= host "g3b-fake.local", port 9000, method POST, path "/v1/g3b/chat"
```

源码验证：

1. Broker `_ROUTE = ^offline-test-only(?:-[A-Za-z0-9_.-]{1,64})?$`（`broker.py:23`）→ `offline-test-only-g3b` **匹配**；`_MODEL = ^fixture-[A-Za-z0-9_.-]{1,64}$`（`:24`）→ `fixture-bridge-v1` **匹配**。
2. Guard 的 provider/model 正则（`runtime-budget-guard/src/index.ts:199-201`）与 Broker 相同 → 匹配；Guard policy 还需 route/model 等于 Broker policy（`:278`）。
3. DSH Adapter provider/model：`ctx.llm.registerAdapter(["offline-test-only-g3b"], ...)`；`resolveModel` 只接受 `offline-test-only-g3b/fixture-bridge-v1`；**provider 直接等于预算 route**，不做映射。
4. EgressPolicy（B2 构造，不修改默认常量）：
   ```python
   EgressPolicy(
     host_ports={"g3b-fake.local": frozenset({9000})},
     methods=frozenset({"POST"}),
     path_prefix="/v1/g3b/",
     approved_routes=frozenset({("offline-test-only-g3b", "fixture-bridge-v1")}),
     max_tokens=1024, max_attempts=1, require_reservation=True,
     allow_files=False, allow_images=False, allow_store=False)
   ```
   Controller 构造 `EgressRequest(route_id="offline-test-only-g3b", model="fixture-bridge-v1", host="g3b-fake.local", port=9000, method="POST", path="/v1/g3b/chat", stream=True, ...)`；Fake 是进程内/受信子进程，不建 socket/HTTP；“host/path”只是 policy 标识。
5. **禁止默认 OpenCode Go**：不得使用 `EgressPolicy()` 默认 host/path/allowlist；B2 必须显式构造上述 policy；B1/B2 在启动时断言 `approved_routes` 仅此 Tuple、host 不含 `opencode.ai`。
6. BIND-01 成立方式：测试 policy 可临时允许 A、B 两个 Tuple（均 allowlist），但 Controller 从 **Broker Reservation row** 取权威 `(A)`，调用 `claim_dispatch_for_request(..., expected_reservation_route_model=(A))`；若 prepared/request 为 B → `RESERVATION_REQUEST_MISMATCH`/`ROUTE_MISMATCH`，claim/provider 0；同时 Broker bound `claim` 带 `expected_route_id=A,expected_model=A`，实际 request B 在 Controller 已被拒绝；即使绕过 Controller，ledger 也拒绝。Fake 收据计数必须为 0。

## 3. Offline Run Admission（B0-04）

### 3.1 文件与所有权

- 固定路径（**编译期常量，不接受 env 覆盖**）：`/run/g3b/admission.json`（root:root, `0444`；目录 `/run/g3b` root:root `0555`）。
- 由 **trusted Launcher** 在候选 DSH 启动前写入；Controller 只读打开一次并校验；候选不能写该路径，不能通过请求字段/env 自授权。
- 如 Launcher 与候选同 uid/同写权限（当前容器）→ 该文件只能作为**结构约定**；OS 强制隔离 `BLOCKED`，B0-02 仍不可 PASS。

### 3.2 精确 JSON Schema（严格，未知字段拒绝）

```json
{
  "schema": "m0.g3b.admission.v1",
  "admission_id": "adm-<32 lowercase hex>",
  "scope_id": "fixed-offline-scope",
  "run_id": "<1..128 UTF-8 chars, no control chars>",
  "synthetic": true,
  "route": {
    "route_id": "offline-test-only-g3b",
    "provider": "offline-test-only-g3b",
    "model": "fixture-bridge-v1"
  },
  "tool_schemas": [
    {"name": "skill_lookup", "sha256": "<64 lowercase hex of approved schema bytes>"}
  ],
  "limits": {
    "max_calls": 8,
    "max_attempts": 1,
    "max_input_tokens": 2500000,
    "max_output_tokens": 1024,
    "deadline_ms": 30000
  },
  "fake_scenario": "ok_usage",
  "expiry_utc": "2026-11-17T00:00:00Z",
  "launcher": {"uid": 65534, "container": true, "admission_nonce": "<32 lowercase hex>"}
}
```

- `fake_scenario` 由 Launcher/测试配置固定：`ok_usage|partial_usage|no_usage|error|eof|timeout|cancel|tool_once|tool_final`；代理/模型文本不能选择计费/场景（见 §5.9）。
- `tool_schemas` 是**批准清单快照**；DSH 传来的 tool schema 只作待比对数据，不是权威。
- `max_attempts=1` 是 M0 单 Attempt 的边界；`max_calls` 按每次 `stream()` 计数（Controller 权威，不依赖 `request/header`）。

### 3.3 缺失/过期/伪造/自授权拒绝

Controller 固定错误码（Envelope error）：`ADMISSION_MISSING`、`ADMISSION_INVALID`、`ADMISSION_EXPIRED`、`ADMISSION_SCOPE_MISMATCH`、`ADMISSION_ROUTE_NOT_ALLOWED`、`ADMISSION_TOOL_SCHEMA_MISMATCH`、`ADMISSION_LAUNCHER_MISMATCH`、`ADMISSION_REPLAYED`、`ADMISSION_SELF_AUTH_DENIED`。规则：

- 文件缺失/不可读/parse 失败/未知字段/类型不符 → 拒绝，Fake 0。
- `expiry_utc` 早于 Controller 当前 UTC → 拒绝。
- `admission_id` 在 Controller 的 trusted SQLite `g3b_admissions` 中已消费 → `ADMISSION_REPLAYED`（新容器/新 admission 由 Launcher 生成）。
- 请求 payload 中出现 `authorized/admission/scope_id/provider/model override` 等字段 → 未知字段拒绝；Adapter 请求 Schema 不允许这些字段。
- 候选进程 env 中的 `G3B_*`/`AUTOTEACHER_*` 变量全部忽略；Controller 只读固定路径 + 固定编译常量。
- `launcher.uid` 必须等于实际 Controller 期望 uid（容器内 65534）；若 Launcher 无法提供 root-owned 文件 → 只记结构证据，OS 边界 BLOCKED。

## 4. 进程 / FD / DB 所有权与传输决策

### 4.1 所有权（ASCII）

```text
Host / trusted Launcher (outside candidate control)
  ├─ creates fixed container rootfs mounts, /run/g3b/admission.json (root 0444), /work/g3b dir
  ├─ starts Broker (stdio, SQLite /work/g3b/broker.sqlite3) as trusted process
  ├─ starts Controller (trusted Python) as trusted process; Controller binds UDS /work/g3b/bridge.sock
  │    └─ Controller starts Fake Provider child (fixed path, stdin/stdout, receipt dir /work/g3b/receipts)
  └─ starts DSH Runtime (candidate boundary) with fixed profile
        └─ DSH Adapter (untrusted) connects ONLY to /work/g3b/bridge.sock
             request/ack/chunk/finish/error/cancel/receipt frames; 无 DB/Key/spawn/网络
Broker SQLite: only Broker + Controller (same trusted side) write; candidate must not have write path.
```

### 4.2 传输决策：primary UDS fixed path

- **Primary**：DSH Adapter → fixed `net.connect('/work/g3b/bridge.sock')`（`node:net`，路径为编译期常量，**不接受 env/argv/请求覆盖**）。Controller 绑定前确保目录/权限，`socket` 文件 mode 0600（同 uid 时仅结构约束）。
- B0 探针：固定 rootfs 内 AF_UNIX bind/connect 成功（Node 与 Python 均 `OK`），AF_INET 被拒绝；这证明 UDS 在当前容器**可行**，但**不证明**同 uid 的安全隔离。
- **禁止**：Adapter spawn Controller/Broker/Fake、打开 TCP/HTTP、使用 `opencode.ai` 默认、读取 Broker DB/Policy/Key、传递额外 FD（SDK `client.py:89` 无 `pass_fds`，继承 FD 不可行）。
- **Fallback（仅在 UDS 被环境拒绝且 Lead 批准时）**：Adapter 以固定路径 `spawn(['/opt/python/bin/python3.11','-B','/work/g3b/controller_stdio.py'])`，stdio 帧；路径/argv 编译期常量、无任意命令；结构性弱于 UDS（候选可决定启动/杀死），必须标 `TRUST_BOUNDARY_WEAKER/BLOCKED`，不得写 trust PASS。切换条件：B1 实测 UDS bind/connect 失败（EACCES/EAFNOSUPPORT/ENOENT）且 fallback 经 Lead 书面同意。

### 4.3 同容器同 uid 的结论

- DSH、Controller、Broker、Fake 均为 `65534:65534`；同 uid 可读（甚至写）彼此可达路径，除非 Launcher 以不同 uid/namespace 运行。Podman `--rootfs` 单容器无法提供不同主体隔离。
- 因此 **B0-02 = BLOCKED**；B3 不得用文件权限/路径测试声称“候选无法读 Controller DB/Policy”。G3-B 只允许 `PASS_FOR_IN_PROCESS_INTEGRATION_ONLY`；OS Trust Boundary 留 G3-D/G4。
- 若 Lead 要求更强的结构性证据：Launcher 可用不同 uid/独立容器（需额外部署，B0 不建议在 G3-B 内扩大）；本设计不自动实施。

## 5. 冻结接口契约（B1/B2 依据）

### 5.1 模块与签名（B1/B2 新增；不得互相猜）

```text
src/autoteacher_m0/bridge/__init__.py
  PROTOCOL = "at-m0/g3b-bridge/v1"; MAX_REQUEST_BYTES=262144; MAX_RESPONSE_BYTES=65536
  class BridgeError(Exception): code: str

src/autoteacher_m0/bridge/protocol.py
  @dataclass(frozen=True) Envelope: v:int; kind:str; transport_id:str; seq:int; payload:dict; hash:str|None
  parse_envelope(line: bytes) -> Envelope            # strict; rejects unknown keys/dup keys/NaN/bool-int
  encode_envelope(env: Envelope) -> bytes
  canonical_payload_bytes(payload: dict) -> bytes    # canonical_json UTF-8, no LF
  payload_digest(payload_bytes: bytes) -> str
  validate_request_payload(payload: dict) -> None
  validate_chunk_payload(payload: dict) -> None
  ERROR_CODES: frozenset[str]

src/autoteacher_m0/bridge/ipc_server.py
  class BridgeServer(controller, socket_path="/work/g3b/bridge.sock"):
      serve_forever() -> None
      handle_connection(conn) -> None
      # per-connection seq/request framing; bounded readline before JSON decode

src/autoteacher_m0/bridge/admission.py
  @dataclass(frozen=True) Admission
  load_admission(path="/run/g3b/admission.json") -> Admission
  validate_admission(admission, *, now_utc, expected_uid) -> None

src/autoteacher_m0/bridge/attempts.py
  class AttemptJournal:
      def __init__(self, sqlite_path="/work/g3b/attempts.sqlite3")
      def reconcile_on_startup(self) -> list[dict]
      def begin_attempt(self, *, scope_id, call_id, reservation_id, prepared_digest,
                        payload_digest, payload_length) -> str   # commit before send
      def mark_response_observed(self, attempt_id, *, receipt_id, receipt_json) -> None
      def mark_settled(self, attempt_id, *, settlement_json) -> None
      def mark_worst_case(self, attempt_id, *, reason) -> None
      def state_for_call(self, call_id) -> str | None

src/autoteacher_m0/bridge/fake_backend.py
  @dataclass(frozen=True) FakeReceipt: receipt_id; raw_sha256; raw_length; mode; usage; nonce; utc; path
  class FakeBackend:
      def __init__(self, python="/opt/python/bin/python3.11", script="/probe/fake/fake_provider.py",
                   workdir="/work/g3b", timeout_ms=10000)
      def start(self) -> None
      def send_exact_bytes(self, payload_bytes: bytes) -> FakeReceipt   # stdout receipt, no retry
      def received_count(self) -> int
      def close(self) -> None

src/autoteacher_m0/bridge/controller.py
  class TrustedController:
      def __init__(self, admission, broker: BrokerClient, fake: FakeBackend,
                   attempts: AttemptJournal, egress_factory)
      def handle_envelope(self, env: Envelope) -> Iterator[Envelope]  # request->ack/chunk/.../finish
      def _prepare(self, request_payload) -> PreparedProviderRequest
      def _broker_reserve(self, prepared, call_id, input_bound, output_bound) -> dict
      def _broker_claim(self, prepared, reservation_id) -> dict
      def _attempt_and_send(self, prepared, claim, payload_bytes) -> FakeReceipt
      def _settle_or_hold(self, observation, reservation_id) -> dict
```

Adapter/Spike (B1，独立可审查副本)：

```text
spikes/g3b-provider-bridge/src/index.ts
  export const provider = 'offline-test-only-g3b'; export const model = 'fixture-bridge-v1'
  class BridgeAdapter extends LlmAdapter:
      stream(options): AsyncGenerator<StreamChunk>   # net.connect('/work/g3b/bridge.sock'); no spawn
      resolveModel(provider, model)                   # only frozen tuple
      providerRetryPolicy()                           # maxRetries 0
  apply(ctx): ctx.llm.registerAdapter([provider], new BridgeAdapter())
spikes/g3b-provider-bridge/fake/fake_provider.py   # G3-B receipt contract (§5.6)
spikes/g3b-provider-bridge/run/worker.py            # real harness worker; no spawn fake
spikes/g3b-provider-bridge/run/suite.py             # B3 scenarios
```

B1/B2 **不得**修改 DSH 核心、`gates.py`、`dsh_adapter.py`、`run_live.sh`；不得在 adapter 中 `spawn`。

### 5.2 Envelope Schema（`at-m0/g3b-bridge/v1`）

每帧一行 UTF-8 JSON（≤上限），严格字段，未知/重复 key、NaN/Inf、bool 冒充 int、非法 UTF-8、控制字符、过深嵌套拒绝：

```json
{"v":1,"kind":"request|ack|chunk|finish|error|cancel|receipt",
 "transport_id":"tr-<32hex>","seq":0,"payload":{},"hash":"<64hex>"}
```

| kind | payload 精确字段（全部必填除标注） |
|---|---|
| request | `sessionId`(str 1..128), `provider`(str), `model`(str), `messages`(array), `tools`(array), `system`(str|null), `maxTokens`(int 1..1024), `stream`(bool true), `attemptOrdinal`(int 1..), `purpose`(null/conversation)；**禁止** call_id/reservation_id/digest/authorized/admission 字段 |
| ack | `request_id`(str), `accepted`(bool), `code`(enum or null) |
| chunk | `chunk` object = 精确 `StreamChunk` 白名单；`usage` 只能在 `finish` 前 |
| finish | `reason` object = 精确 FinishReason（`kind` 白名单 `stop/tool-calls/max-tokens/error/aborted/blocked`）；只一次 |
| error | `code` enum, `message`(安全短字符串，不含原文), `retryable`(false) |
| cancel | `request_id`(str), `reason` in `aborted|timeout|controller_shutdown` |
| receipt | `receipt_id`, `raw_sha256`, `raw_length`, `mode`, `usage`(object|null), `nonce`, `utc`；只读证据，不授予权限 |

`hash` 定义：对 `canonical_json(payload)` 的 UTF-8 字节 SHA-256；仅用于帧完整性，不代替 `payload_digest`（见 §5.5）。

**时序语义（冻结）**：

- `ack` 只表示受信端收到并完成基本解析，**不等于** Budget 获准、Claim 成功或已发送；`request` 后允许 Controller 先 `ack{accepted:false}`（admission/schema 拒绝）或 `ack{accepted:true}` 再进入 reserve/claim；真正的发送许可只能由 Broker claim + durable attempt 决定。
- `chunk.seq` 在单 request 内严格递增（从 0）；只允许 §5.2 白名单 chunk；`usage`（如果有）必须在 `finish` 之前；`finish` 每 request 恰好一次且为终帧。
- EOF/超时/进程异常：尚未进入发送边界 → `error` + Fake 0；已进入发送边界/unknown → 不得报成功 finish，Controller 必须在 attempt journal 标保守状态并在响应中 `error`（`BILLABLE_UNKNOWN`/`SETTLEMENT_UNCERTAIN`）。
- `cancel` 是 best-effort：收到 cancel 不等于 Provider 停止或免费；跨发送边界后的 cancel 必须保守处理；不得自动重试。
- 流中失败后只能 `error` 终帧；已向 DSH 发出的成功 Finish 不能回滚，但账本必须已在 finish 前完成或明确标记 uncertain。

### 5.3 资源上限（强制，由 Controller/parser/Fake 执行）

| 限制 | 初值 | 执行位置 |
|---|---:|---|
| 单个 request frame | 256 KiB | ipc_server 先按字节截断，再 JSON 解析；超限 `FRAME_TOO_LARGE` |
| 单个 response frame | 64 KiB | ipc_server 写出前检查；超限 error/关闭 |
| 单请求总 IPC 字节 | 1 MiB | Controller per-request counter |
| JSON 递归深度 | 32 | protocol parser |
| 最多流 chunk | 256 | Controller；超出 `CHUNK_LIMIT` |
| 最大 pending streams | 2（默认串行 1） | Controller server 队列 |
| Controller deadline | 30 s | Controller monotonic timer；超时 cancel+保守 |
| Fake step timeout | 10 s | FakeBackend subprocess/pipe timeout |
| cleanup grace | 1 s | Controller/Fake close；随后 SIGKILL |
| UDS frame read buffer | 64 KiB 增量，总 256 KiB | ipc_server；无换行不无限缓存 |

### 5.4 错误码枚举（B1/B2 统一；§5.2 error.code）

`PROTOCOL_VERSION`, `UNKNOWN_KIND`, `UNKNOWN_FIELD`, `DUPLICATE_KEY`, `BAD_TYPE`, `NAN_OR_INF`, `FRAME_TOO_LARGE`, `RESPONSE_FRAME_TOO_LARGE`, `TOTAL_BYTES_EXCEEDED`, `DEPTH_EXCEEDED`, `SEQ_OUT_OF_ORDER`, `REQUEST_INVALID`, `ADMISSION_MISSING`, `ADMISSION_INVALID`, `ADMISSION_EXPIRED`, `ADMISSION_SCOPE_MISMATCH`, `ADMISSION_ROUTE_NOT_ALLOWED`, `ADMISSION_TOOL_SCHEMA_MISMATCH`, `ADMISSION_LAUNCHER_MISMATCH`, `ADMISSION_REPLAYED`, `ADMISSION_SELF_AUTH_DENIED`, `PREPARED_SCHEMA_INVALID`, `PREPARED_DIGEST_MISMATCH`, `BUDGET_DENIED`, `ROUTE_MISMATCH`, `CLAIM_DENIED`, `CLAIM_BINDING_UNSUPPORTED`, `ATTEMPT_JOURNAL_UNAVAILABLE`, `ATTEMPT_ALREADY_STARTED`, `FAKE_UNAVAILABLE`, `FAKE_IO_ERROR`, `FAKE_RECEIPT_MISMATCH`, `USAGE_INVALID`, `SETTLEMENT_UNCERTAIN`, `CANCELLED`, `INTERNAL`. 所有 error 不携带原始 prompt/usage 文本/Key。

### 5.5 `prepared_digest` vs `payload_digest`

- `prepared_digest = SHA-256(canonical_json(prepared_payload(prepared)))`，字段为 `_PREPARED_DIGEST_FIELDS`（`egress.py:157-162`），用于 `request_digest`/`call_id`/Broker claim；不含 `call_id/request_digest` 自身。
- `payload_digest = SHA-256(payload_bytes)`，其中：

```text
payload_bytes = UTF-8(canonical_json(fake_payload))   # 无尾部 LF；ensure_ascii=False
fake_payload = {
  "schema":"m0.g3b.fake.v1", "call_id":..., "prepared_digest":...,
  "route_id":"offline-test-only-g3b", "model":"fixture-bridge-v1",
  "messages":[...], "tools":[...], "system":..., "max_output_tokens":...,
  "stream":true, "mode":"ok_usage|partial_usage|...", "nonce":"<32hex>"
}
```

- Controller 在 claim **前** 固定 `payload_bytes`/`approved_payload_digest`；`FakeBackend.send_exact_bytes` 写 `payload_bytes + b"\n"`；Fake 读取一行后去掉**恰好一个 LF**，对剩余 bytes 计算 `raw_sha256/raw_length`（`transport_encoding:"utf-8+lf"`）。
- 证据等式（B2-06）：

```text
controller.approved_payload_digest
  == trusted_egress.sent_payload_digest          # FakeBackend 写 stdin 前/写时记录
  == fake_provider.received_payload_digest        # receipt.raw_sha256
```

且另一条链独立成立：`call_id -> prepared_digest -> reservation_id -> bound_claim -> attempt_id -> receipt_id`。Envelope 包装/transport_id/seq **不得**计入 `payload_digest`。`prepared_digest ≠ payload_digest` 是预期（不同覆盖对象），不得混淆。

### 5.6 Fake Provider 契约

- 可执行固定路径 `/probe/fake/fake_provider.py`（只读挂载）；由 **Controller** 启动（不是 DSH Adapter）；`argv = [FIXED_PYTHON,'-B',FIXED_FAKE]`；env 只允许固定 `G3B_RECEIPT_DIR=/work/g3b/receipts`、`G3B_FAKE_NONCE=<hex>`、`PATH`/`HOME`；无 Key/网络。
- stdin 只读**一行**（≤1 MiB），超限拒绝并以 exit 2 结束；写 receipt 前计算 `raw_sha256/raw_length`；收据原子写：`tmp -> fsync -> os.replace -> fsync(dir)`；receipt 固定字段：

```json
{"schema":"m0.g3b.fake.receipt.v1","receipt_id":"rcpt-<32hex>","raw_sha256":"<64hex>",
 "raw_length":<int>,"transport_encoding":"utf-8+lf","mode":"<admission scenario>",
 "usage":{"inputTokens":11,"cacheReadTokens":2,"cacheWriteTokens":0,"outputTokens":5,"reasoningTokens":0,"totalTokens":18} | null,
 "nonce":"<32hex>","utc_start":"...Z","utc_end":"...Z","pid":<int>,"synthetic":true,
 "real_model_calls":0,"http_calls":0,"network_used":false}
```

- 独立 received-counter：`/work/g3b/receipts/received-count.json`，每次收到一行先文件锁/原子递增并 fsync；B3 的“Fake 0/1”必须读该 counter + receipt，不以 Controller/DSH 自报为准。
- 模式（由 admission 固定，不由候选文本选择）：`ok_usage`（block-start+2 text-delta+block-end+usage+finish stop）、`partial_usage`（usage 只有 inputTokens，finish stop）、`no_usage`（无 usage，finish stop）、`tool_once`（tool-call delta）、`tool_final`（最终结果，含 tool 消息）、`eof`（无 finish 退出）、`error`（finish error）、`timeout`（延迟超过 deadline）、`cancel`（慢流，等 cancel）。
- Fake 不解析业务内容、不访问文件系统（除 receipt/counter 固定目录）；不写 Ledger；不签发 claim。

### 5.7 Attempt Journal（B2 Controller-owned，SQLite）

路径固定 `/work/g3b/attempts.sqlite3`；连接 `PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL; PRAGMA foreign_keys=ON; PRAGMA busy_timeout=10000`。Additive schema v1（不修改 Broker DB/旧表）：

```sql
CREATE TABLE IF NOT EXISTS g3b_attempts (
  attempt_id TEXT PRIMARY KEY,
  scope_id TEXT NOT NULL,
  call_id TEXT NOT NULL,
  reservation_id TEXT NOT NULL,
  prepared_digest TEXT NOT NULL,
  payload_digest TEXT NOT NULL,
  payload_length INTEGER NOT NULL,
  state TEXT NOT NULL CHECK(state IN
    ('RESERVED','CLAIMED','ATTEMPT_STARTED','RESPONSE_OBSERVED','SETTLED','WORST_CASE_HELD')),
  receipt_id TEXT, receipt_json TEXT, settlement_json TEXT, reason TEXT,
  created_utc TEXT NOT NULL, updated_utc TEXT NOT NULL,
  UNIQUE(scope_id, call_id), UNIQUE(scope_id, reservation_id)
);
CREATE INDEX IF NOT EXISTS g3b_attempts_state ON g3b_attempts(scope_id,state);
CREATE TABLE IF NOT EXISTS g3b_admissions (
  admission_id TEXT PRIMARY KEY, admission_sha256 TEXT NOT NULL,
  consumed_utc TEXT NOT NULL, run_id TEXT NOT NULL
);
```

- `begin_attempt()`：写/更新为 `ATTEMPT_STARTED`，提交并 fsync 后才允许进入发送边界；**先 commit 后 send**；失败不得发送。
- 状态转换：`RESERVED`（Broker reserve 后）→ `CLAIMED`（Broker claim 后）→ `ATTEMPT_STARTED`（发送前，durable）→ `RESPONSE_OBSERVED`（receipt 持久）→ `SETTLED`/`WORST_CASE_HELD`；无合法转换则 `ATTEMPT_ALREADY_STARTED` 拒绝，不重发。
- `reconcile_on_startup()`：读取同一 DB；`ATTEMPT_STARTED`/`RESPONSE_OBSERVED` 不自动发送；有 receipt 的可幂等结算（Broker `settle`/`fail`，不改已结算）；无 receipt 保持保守并报告 `SETTLEMENT_UNCERTAIN`；`RESERVED/CLAIMED` 不自动 Claim/Dispatch。
- 迁移声明：新增表，不动 Broker `budget_*`；旧 DB 打开时只 CREATE IF NOT EXISTS；回退只需不读取新表。

### 5.8 崩溃 Hook（仅测试/Launcher 启用）

固定名称：`after_reserve_before_claim`、`after_claim_before_attempt_start`、`after_attempt_start_before_fake_send`、`after_fake_receive_before_response`、`after_response_before_settlement`、`after_settlement_before_sdk_finish`。启用机制仅：Launcher 设置 `G3B_TEST_MODE=1` 且 `G3B_CRASH_HOOK=<name>`；生产/Profile 不含变量；候选请求/env 不能设置。Hook 在 durable 状态切换后执行 `os._exit(97)`/SIGKILL；B3 记录真实进程/SQLite 证据。

### 5.9 Controller ↔ Broker 映射与 Adapter 场景推导

- `reserve`：`task_id="g3b-"+sha256(run_id)[:32]`（Broker `_ID` 限制）；`route_id/provider/model` 为冻结 Tuple；`input_tokens` = Controller 保守输入上界（admission limits/min of canonical byte bound），`output_tokens` = `prepared.max_output_tokens`；`retry=false`；`call_id=prepared_call_id`。
- `claim`：`call_id,reservation_id,prepared.request_digest,expected_route_id=prepared.route_id,expected_model=prepared.model`；仅此路径，禁 legacy。
- `settle/fail`：按 §1.3 映射；完全 complete 且可信 synthetic → `settle`；任何 PARTIAL/MISSING/UNKNOWN → `fail`（`usage` 映射含已知维度；UNKNOWN 可 `None`/{}），Broker 保守 floor；不发送 `actual_cost_usd`。
- `snapshot`：只读对账；不用于授权。
- Adapter 场景：Adapter 只上报 GenerateOptions（messages/tools/provider/model/maxTokens/sessionId）；Fake mode 来自 **admission.fake_scenario**（Launcher/测试固定），不得从 prompt 文本或候选字段选择；重复 Attempt 由 Controller/Broker 拒绝。Tool 两轮由真实 DSH 产生两个 `stream()`，Controller 各分配新 `logical_step/attempt_index`（step+1）与新的 call/reservation/claim/attempt。

## 6. 测试分配矩阵（实际 33 条；任务描述曾称 43 行）

> 实际 CSV 只有 33 个 `case_id`（B0 4 + B1 4 + B2 10 + B3 12 + B4 3）。本冻结按 33 条分配；若 Lead 另有 43 条清单，需补充 CSV，不在本文件伪造。

| ID | 责任包/文件 | 真实边界/不得 mock |
|---|---|---|
| B0-01 | B0（本文件 + baseline） | git/hash/容器只读指纹；已完成 |
| B0-02 | B0/B3 `test_b0_boundary.py` | OS 权限/容器攻击探针；**同 uid 只能 BLOCKED** |
| B0-03 | B0/B1 `test_b0_route.py` | broker/egress/guard/DSH regex 静态 + 启动断言；真实免 mock |
| B0-04 | B0/B2 `test_b0_admission.py` | 伪造/缺失/env 自授权；Fake counter=0 |
| B1-01 | B1 `tests/integration/g3_bridge/test_b1_protocol.py` | 真实 DSH adapter→UDS controller echo；真实进程 |
| B1-02 | B1 同上 | 真实 UDS 超长/坏帧/重复 key；Controller 解析计数 |
| B1-03 | B1 同上 | 错误 v/kind/seq/finish 乱序；无成功 finish |
| B1-04 | B1/B3 | Fake EOF/error/delay/cancel；真实子进程/Fake receipt |
| B2-01 | B2 `test_b2_ledger_chain.py` | 真实 SQLite Broker + Fake receipt；5 个计数 |
| B2-02 | B2 同上 | Prepared 篡改前后 claim；Fake counter 0/不二次 |
| B2-03 | B2 同上 | Route A/B 均 allowlist；Broker ROUTE_MISMATCH，Fake 0 |
| B2-04 | B2 同上 | fake reservation/无 Claimer/legacy；Fake 0 |
| B2-05 | B2 同上 | Unicode/长 run_id/call_id 重放；跨进程一致 |
| B2-06 | B2 同上 | 三方 payload digest 等值 + prepared digest 独立 |
| B2-07 | B2 同上 | 无 durable attempt 即发送 → 拒绝，Fake 0 |
| B2-08 | B2 同上 | 成功 observation 与真实 ledger settle；来源/费用/route 一致 |
| B2-09 | B2 同上 | Missing/Partial/Invalid usage；pending/hold，不填 0 |
| B2-10 | B2 同上 | 相同 observation 幂等/冲突；账本不回退 |
| B3-01 | B3 `test_b3_tool_guard.py` | 真实 skill_lookup 两轮；2 套 reservation/claim/receipt |
| B3-02 | B3 同上 | 新进程 resume；不重发旧 pending |
| B3-03 | B3 `test_b3_guard.py` | 真实 Guard 装载 + Bridge；Broker 唯一预算 |
| B3-04 | B3 同上 | Guard 缺失/故障 + 无授权；Fake counter=0 |
| B3-05 | B3 `test_b3_crash_concurrency.py` | 两个真实 Broker/Worker 进程竞争；SQLite 原子 |
| B3-06 | B3 同上 | claim 后 send 前 SIGKILL；重启不重发 |
| B3-07 | B3 同上 | attempt 持久后 response 前 SIGKILL；保守 |
| B3-08 | B3 同上 | response 后 settlement 前 SIGKILL；幂等结算不再发送 |
| B3-09 | B3 同上 | tool 第二次 stream 无二次 header；仍单独预算/claim |
| B3-10 | B3 同上 | timeout/cancel/进程树清理；无孤儿/容器残留 |
| B3-11 | B3 同上 | 并发/背压/资源上限；帧/内存/进程限制 |
| B3-12 | B3 同上 | 未批准 tool/aux/File/Image/Store；发送前拒绝 |
| B4-01 | B4 `test_b4_gate_static.py` | LiveGate/Adapter/run_live blob/动态阻断 |
| B4-02 | B4 `test_b4_regression.py` | 全量 pytest/Ruff/Node Guard/Skill 真实计数 |
| B4-03 | B4 Packet 脚本 | Packet 源码与 Git blob/hash 一致 |

P0 不得 mock 的项：B1-01/02、B2-01/02/03/04/06/07、B3-01/03/04/05/06/07/09、B4-01/03；至少真实进程/真实 SQLite/Fake counter 证据。

## 7. 待 Lead 签核开放决策（5 条，未自决）

| ID | 决策 | 选项 | 推荐 |
|---|---|---|---|
| O-1 | 主传输 | UDS fixed `/work/g3b/bridge.sock` vs Adapter spawn controller stdio fallback | **UDS**（B0 探针 Node/Python 均 AF_UNIX OK；fallback 仅环境拒绝时经批准，标 weaker/BLOCKED） |
| O-2 | 精确字节/`sent_payload_digest` | ① B2 用 `TrustedEgressTransport.dispatch` + FakeBackend 闭包/外部 receipt（不改 egress）；② additive 扩展 `dispatch` 接收 payload/返回 digest（改 security/egress.py） | **① 最小**（B2-06 用 receipt 三方相等）；若 Reviewer 要求 transport 内建 digest → ② 需 Lead 另行批准 |
| O-3 | Observation→settle | ① Controller 原始字段映射到现有 `settle/fail`（B0 实测三种形状等值，无新 op）；② 新增 broker `settle_observation` op | **①**（不改 Broker 协议；`to_usage` 仅交叉校验） |
| O-4 | Guard+Bridge 预算 | ① Guard 仅无副作用预检，Controller/Broker 唯一 Reserve；② Guard 发起 Reserve 且 Controller 绑定校验（不二次扣账）；③ Guard-must-present 策略 | **①**（最简单、单一账本权威；Guard 仍可在缺失时由 Controller 拒绝） |
| O-5 | OS 边界裁定 | ① 接受同 uid 结构闭环，B0-02/G3-B trust 标 BLOCKED，G3-D 再补；② G3-B 内扩为不同 uid/namespace/多容器（显著扩大） | **①**（本轮范围；不得写 PASS_FOR_G3B_TRUST_BOUNDARY_SCOPE） |

## 8. 风险清单

1. **UDS 可行性/权限**：B0 探针显示 AF_UNIX 与 Node UDS 可用；但同 uid 下候选可连接/发现 socket；权限仅结构，非安全边界。若 UDS 被更严 seccomp 拒绝，需 fallback（O-1）且信任更弱。
2. **observation/settle 形状**：直接传 `ProviderObservation.to_usage()` 会丢 cache_write/reasoning/完整性；必须 Controller 原始字段映射（O-3）；映射错误会导致费用低估/重复计数，B2 必须有 AUTH/PARTIAL/MISSING 三方对照。
3. **Guard 双扣**：Guard 内置 reserve；若 Guard 与 Controller 各自 Reserve 会双计；按 O-4 仅一个 Reserver；B3 用同一 tool turn ledger 行数验证。
4. **Tool 二次调用身份**：DSH 可能对一次 `request/header` 产生两次 `LlmAdapter.stream`；必须以每次 stream 独立 call_id/reservation/claim/attempt；不能依赖 header 计数。
5. **崩溃语义**：ATTEMPT_STARTED 必须 commit 后 send；reconcile 不自动重发；无 receipt 保守 PENDING。任何“先发后记”都是 P0 FAIL。
6. **Packet 身份漂移**：B4 Packet 必须绑定 base/impl/docs SHA；source 与 Git blob 一致；G3-A 历史 packet 不重写；本冻结文件的接口若被 B1/B2 改动，必须回到 Lead 重新冻结。
7. 真实 wire/usage/invoice、远端 exactly-once、单 turn cancel、生产 BoundBrokerClaimer：G3-B 内仍 UNVERIFIED/BLOCKED，不得写入 PASS。
8. 本文件实际证据矩阵 33 条 vs 任务描述 43 行：需 Lead 确认；本文件不编造缺失条目。

## 9. B1/B2 并行边界与 STOP

- **B1**：`bridge/protocol.py`、`bridge/ipc_server.py`、`spikes/g3b-provider-bridge/src/index.ts`、`fake/fake_provider.py`（wire/receipt 契约）、`run/worker.py`、`run/suite.py` skeleton；只按 §5.2/§5.5/§5.6 实现；不写 Broker/Controller 状态机。
- **B2**：`bridge/controller.py`、`admission.py`、`attempts.py`、`fake_backend.py`、Broker client mapping/observation adapter；只按 §3/§4/§5.7/§5.9 实现；不修改 B1 文件/协议字段。
- **B3**：integration/chaos；**B4**：Packet/regression；B3 必须等 B1+B2 最小链路合并；B4 只读冻结字节。
- 任一接口变更 → Lead 重新签核；完成 B0 文档并提交后 **STOP**，不进入 B1/B2 实现（由 Lead 另行派发）。

## 10. B0 未做/UNVERIFIED

- 未运行 pytest/Node/项目代码；仅只读容器探针（UDS/版本/no-key）与源码静态核对。
- 未实现 B1/B2；接口为设计冻结，需实现验证。
- 未证明 OS 信任边界；未证明真实 DSH 经 UDS 全链；未证明 Guard+Bridge 组合；未证明 Fake 收据/Packet 实现正确。
- 真实 Provider HTTP/usage/invoice/Live：全部 UNVERIFIED/BLOCKED。
