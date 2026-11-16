# M0 G3-B IPC v1 协议（B1 冻结实现说明）

- 状态：**B1 实现文档（离线/无 Key）**；依据 `docs/M0_G3B_DESIGN_FREEZE.md`（v1.1，sha256 `708772af…`）§5.1–§5.5/§7/§9。
- 协议标识：`at-m0/g3b-bridge/v1`；传输：**AF_UNIX SOCK_STREAM，固定路径 `/work/g3b/bridge.sock`**（编译期常量，不接受 env/argv/请求覆盖）。
- 适用：DSH 候选侧 `LlmAdapter` ↔ launcher-owned 可信 Controller（B2 实现）。B1 只拥有协议/传输/Adapter；**不实现 admission/Reserve/Claim/Attempt/Fake/settle**，不授予 Live。
- 本协议不是 OS 信任边界证明；同容器同 uid 的 B0-02 仍 **BLOCKED**。`PASS` 最高只能到 `PASS_FOR_G3B_NO_KEY_INTEGRATION_SCOPE`。

## 1. 帧与 Envelope

每帧一行 UTF-8 JSON（≤上限；以 `\n` 结束），严格字段：

```json
{"v":1,"kind":"request|ack|chunk|finish|error|cancel|receipt",
 "transport_id":"tr-<32hex>","seq":0,"payload":{},"hash":"<64hex>"}
```

- `v`：必须整数 `1`（拒绝 bool/其他版本）。
- `kind`：上列七类，拒绝未知。
- `transport_id`：`tr-` + 32 小写 hex；仅路由/关联，**不是**预算授权。
- `seq`：非负整数；客户端 request 必须 `seq=0`；服务端 ack 从 `1` 开始严格递增；客户端 cancel 的 seq 必须大于此前客户端帧。乱序/重复/回放拒绝。
- `payload`：每 kind 独立严格 Schema；未知/缺失字段拒绝。
- `hash`：`SHA-256(canonical_json(payload) 的 UTF-8 字节)`，64 小写 hex；可选出现在 frames 中；若出现必须与 payload 一致。仅帧完整性，**不是** call identity/prepared_digest/payload_digest。
- 解析顺序：**先按字节上限**，再 UTF-8/JSON；拒绝重复 JSON key、NaN/Infinity、非法 UTF-8、控制字符、非字符串 key、bool 冒充 int、超深嵌套、未知/缺失字段。
- canonical JSON：`json.dumps(sort_keys=True, separators=(",",":"), ensure_ascii=False, allow_nan=False)`；无尾 LF（帧另加 LF）。

## 2. 各 kind payload

### request（DSH Adapter → Controller）
精确字段（全部必填）：`sessionId`(str 1..512)、`provider`(str)、`model`(str)、`messages`(array)、`tools`(array)、`system`(str|null)、`maxTokens`(int 1..1024)、`stream`(true)、`purpose`(null|"conversation")。**没有 attemptOrdinal**；没有 call_id/reservation_id/digest/authorized/admission 字段；logical_step/attempt 由可信 Controller 分配。

### ack（Controller → Adapter）
`{"request_id":str,"accepted":true,"code":null}`。Controller/ipc_server 在 Envelope/framing/JSON/seq/request schema 成功后**一律先发 ack{accepted:true}**；ack 只表示“收到”，**不等于**预算获准/Claim 成功/已发送。所有 admission/route/budget/claim/prepared/tool 拒绝在 ack 后以 `error` 表达；**不得** ack{accepted:false}。framing/JSON/schema/seq 失败不 ack，直接 error（可写时）并关闭连接。v1 中 server 以 `request_id = transport_id` 作为单连接单请求关联 ID。

### chunk（Controller → Adapter）
`{"chunk": <StreamChunk 白名单>}`；类型仅：
`block-start`(index int≥0, blockType ∈ {text,reasoning,image,file,tool-call,tool-addition,tool-removal})、
`text-delta`/`reasoning-delta`(index, text str)、
`tool-call-delta`(index, id, name?, argumentsDelta)、
`block-end`(index, block 对象 type 白名单)、
`usage`(usage 对象；`inputTokens`/`outputTokens` 必填，total/cacheRead/cacheWrite/reasoning 可选，int≥0)。
**finish 不作为 chunk**；usage（若有）必须在 finish 之前；每 request 最多 256 chunks。

### finish（Controller → Adapter）
`{"reason": FinishReason}`；`kind ∈ {stop,tool-calls,max-tokens,aborted,error,blocked}`；`aborted`/`error` 必须带 `failure{message,code}`；每 request **恰好一次**且为终帧。

### error（Controller → Adapter）
`{"code":<ERROR_CODES>,"message":安全短字符串,"retryable":false}`；不含 prompt/usage 原文/Key。error 为终帧。

### cancel（Adapter → Controller；独立线程投递）
`{"request_id":str,"reason":"aborted|timeout|controller_shutdown"}`；best-effort：收到不等于 Provider 停止/免费；跨发送边界后的 cancel 必须保守处理，不得自动重试。

### receipt（只读证据，不授予权限）
`receipt_id`、`raw_sha256`(64hex)、`raw_length`(int)、`mode`、`usage?`、`nonce`(32hex)、`utc`；仅由 Controller/Fake 链产生，Adapter 忽略/不透传。

## 3. 资源上限（强制）

| 限制 | 值 | 执行 |
|---|---:|---|
| request frame | 256 KiB (262 144) | ipc_server/protocol：先字节上限再 JSON |
| response frame | 64 KiB (65 536) | ipc_server 写出前 |
| 单请求总响应字节 | 1 MiB (1 048 576) | ipc_server |
| JSON 深度 | 32 | protocol |
| 流 chunk 数 | 256 | ipc_server |
| Controller deadline | 30 s | 服务端 monotonic deadline；超时 error 且不报成功 |
| UDS 读缓冲 | 64 KiB 增量、总 256 KiB | FrameReader；无换行不无限缓存 |
| pending streams | 2（默认串行 1） | 由 launcher/Controller 调度；B1 单连接单请求 |

## 4. 流序 / 生命周期

1. Adapter 校验 `GenerateOptions` 只含冻结 Tuple `offline-test-only-g3b/fixture-bridge-v1`，构造 request（seq=0），连接固定 UDS，发送一帧。
2. Controller 解析成功后先发 ack(seq=1、accepted:true)；Adapter **必须收到合法 ack 才继续**，但 ack≠发送许可。
3. Controller 只有在其受信 admission/Reserve/Claim/Attempt 决定后才可产生 chunk；chunk seq 由服务端从 2 起严格递增。
4. usage（若有）在 finish 前；finish 一次后 Adapter 结束生成器；之后任何 chunk/finish 拒绝。
5. 发送边界前的失败 → error + 0 Fake；发送边界后未知 → 不得成功 finish，Controller 在 attempt journal 标保守状态并返回 `SETTLEMENT_UNCERTAIN`/`BILLABLE_UNKNOWN`（B2 负责）。
6. EOF/截断帧/超时/非法帧 → fail-closed：Adapter 抛 `INVALID_RESPONSE`/`TIMEOUT`，不产出伪造 finish；服务端关闭连接。
7. AbortSignal：Adapter 发送 cancel（若尚未 finish）并销毁连接，抛 `ABORTED`；服务端独立 reader 调 Controller 的 `cancel(transport_id, reason)`（若实现）。不得自动重试。

## 5. 错误码（§5.4 冻结集合）

`PROTOCOL_VERSION, UNKNOWN_KIND, UNKNOWN_FIELD, DUPLICATE_KEY, BAD_TYPE, NAN_OR_INF, FRAME_TOO_LARGE, RESPONSE_FRAME_TOO_LARGE, TOTAL_BYTES_EXCEEDED, DEPTH_EXCEEDED, SEQ_OUT_OF_ORDER, REQUEST_INVALID, ADMISSION_MISSING, ADMISSION_INVALID, ADMISSION_EXPIRED, ADMISSION_SCOPE_MISMATCH, ADMISSION_ROUTE_NOT_ALLOWED, ADMISSION_TOOL_SCHEMA_MISMATCH, ADMISSION_LAUNCHER_MISMATCH, ADMISSION_REPLAYED, ADMISSION_SELF_AUTH_DENIED, PREPARED_SCHEMA_INVALID, PREPARED_DIGEST_MISMATCH, BUDGET_DENIED, ROUTE_MISMATCH, CLAIM_DENIED, CLAIM_BINDING_UNSUPPORTED, ATTEMPT_JOURNAL_UNAVAILABLE, ATTEMPT_ALREADY_STARTED, FAKE_UNAVAILABLE, FAKE_IO_ERROR, FAKE_RECEIPT_MISMATCH, USAGE_INVALID, SETTLEMENT_UNCERTAIN, CANCELLED, INTERNAL`。

## 6. `hash` / digest 对象边界

- Envelope `hash`：仅 frame payload 完整性（本文件 §1）。
- `prepared_digest`：对 PreparedProviderRequest 的 canonical JSON SHA-256，用于 call_id/request_digest/Broker claim（B2；§5.5）。
- `payload_digest`：对 Fake payload bytes 的 SHA-256（B2/Fake；§5.5）；Envelope/transport_id/seq **不得**计入。
- 三者不得混用；B1 不定义/不计算 prepared/payload digest。

## 7. B1 ↔ B2 接口假设（冻结契约的实现解读）

- B2 Controller 需提供 `handle_envelope(env: Envelope) -> Iterable[Envelope]`；**不要重复发 ack**（server 已先发；重复 ack 被容忍但不发送第二次）。返回的 chunk/finish/error Envelope 的 seq/hash 由 server 重新分配；kind/payload 必须符合本文件。
- 可选 `cancel(transport_id: str, reason: str)`：server 的独立 cancel reader 调用它；未实现时 server 仅记录并停止该连接读取。
- B2 负责 admission/Reserve/Claim/Attempt/Fake/settle；B1 不导入 Broker/Controller/Fake，不读取 DB/Key。
- UDS 服务器由受信侧（launcher/Controller）绑定；Adapter 不 spawn 任何进程。B1 实测 UDS bind/connect 成功（宿主测试 + 固定 rootfs node 测试），AF_INET 仍被 rootfs 拒绝。

## 8. 版本与兼容性

- 当前唯一版本 `v=1`；未知 `v`/kind/字段直接拒绝；不静默降级。
- 任何字段/状态机/上限/错误码语义变更 → 回到 Lead 重新冻结，不允许 B1/B2 私自扩展。
- `at-m0/g3b-bridge/v1` 与 G3-A stdio `v=1` 是不同传输/所有者；G3-A 文件不改。

## 9. B1 实现与验证范围

- 实现：`src/autoteacher_m0/bridge/{__init__,protocol,ipc_server}.py`、`spikes/g3b-trusted-bridge/{src/index.ts,package.json,tsconfig.json,config/bridge.patch.yml,scripts/build.mjs,scripts/build.sh,test/adapter-signal.test.mjs,test/stub_controller.py}`、`tests/integration/g3_bridge/test_protocol.py`。
- 宿主 Python：`pytest tests/integration/g3_bridge/test_protocol.py` **18 passed**；host `ruff`（B1 文件）**All checks passed**。
- 固定 rootfs 容器（禁网/只读/65534/cap-drop）：`scripts/build.sh` 构建成功，rootfs before/after 归一化 tar 均 `25491e45…`；`node --test` **6 passed**（正常流/abort/坏帧/大帧/单 finish/注册）。
- stub Controller 仅用于测试信号/帧，不冒充可信 Controller，不作为 G3-B 账本/Claim/Fake 证据。
- 未做：真实 DSH SDK/Broker/Fake 闭环（B2/B3）、真实 provider wire/usage/invoice、Live/Key/HTTP、OS 信任边界；全部 UNVERIFIED/BLOCKED。
