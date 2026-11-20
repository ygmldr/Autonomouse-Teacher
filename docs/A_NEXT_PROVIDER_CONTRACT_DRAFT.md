# A-NEXT — Provider 契约适配稿（2026-11-19 研究快照；未获批、未真实调用）

- **文档 ID**：`A-NEXT-PROVIDER-CONTRACT-DRAFT-v1`
- **性质**：对旧 A2 官方文档研究稿（`work/m0-g4h0:docs/g4h0/PROVIDER_CONTRACT_DRAFT.md`，
  sha256 `ed720978235612dcb0515fbd15d19a22301fa4ca6fc35c0a18e3c8b5a6166f2b`）的 **A-NEXT/G4-R 适配**。
  **不是**部署授权、路由批准、E5/G4-H/G5 凭据；不得据此发送真实请求。
- **外部事实有效期**：全部为 **2026-11-19T17:47:09Z–17:47:17Z (UTC) 公开文档研究快照**，
  本轮 **未重新采集、未获批、未真实调用**。正式审批/G5 前必须按维护者指定日期重新核实（D-17/D-22）。
- **工作树/分支**：`/root/Autonomous Teacher/worktrees/a-next-handoff` / `docs/a-next-handoff`；
  canonical 基线 `work/g4r=fd1d3a6`；frozen src impl `d33e0aa`；base `3e7afee`。
- **来源**：旧 A2 `A2_SOURCES.md`（sha256 `77a5ead5d11704d2e1870c3d8a9eda52778e3b097076994dc5207d657429f018`）
  的 **28 个 URL + 采集时间 + sha256**；下列 `Sxx` 编号与该文件一致。可信度分层：A 级=官方
  `api-docs.deepseek.com`/`platform.deepseek.com`；B 级=官方 DSH 文档（仅辅助）；C 级=第三方（不作契约依据）；
  D 级=本仓库声明（不是供应商事实）。

## 0. 结论摘要

1. **官方契约（旧 A2 研究已核实，2026-11-19 快照，未获批）**：model `deepseek-flash`（服务别名，实际版本
   `DeepSeek-V4.1-Flash-1017`）；OpenAI 格式 base URL `https://api.deepseek.com`，`POST /chat/completions`；
   OpenAI 鉴权 `Authorization: Bearer <key>`；支持 streaming（SSE、`data: [DONE]`、末 chunk 携带 usage）；
   usage 含 `prompt_tokens`/`completion_tokens`/`prompt_cache_hit_tokens`/`prompt_cache_miss_tokens`/
   `completion_tokens_details.reasoning_tokens`；cache hit/miss 价格分列；并发上限 2500；429/5xx 语义有官方文字。
2. **G4-R 代码实际状态（本工作树实测）**：默认设置声明官方路由 `deepseek-official/deepseek-flash`
   （`settings.py:5-6`）；但 egress allowlist 硬编码**第三方** `opencode.ai:443` + `/inference/go/` +
   `("opencode-go","deepseek-v4.1-flash")`（`security/egress.py:31-34,101-124`）；`TrustedLiveController`
   以此为 `EXPECTED_EGRESS_POLICY`，若 approved route 不在其中返回 `ROUTE_NOT_IN_FROZEN_EGRESS_ALLOWLIST`
   （`live_controller.py:43,199-204`）；DSH target profile **禁用官方 `llm-deepseek`**、仅 synthetic
   `offline-test-only/fixture-v1`（`config/dsh/target-runtime.patch.yml:4-5,34-57`）。→ **BLK-01 未解**。
3. **usage 映射不兼容**：本地 `broker_usage.py` 要求 `inputTokens/cacheReadTokens/cacheWriteTokens` 三桶齐全；
   官方 Chat Completions 只给 total prompt + hit/miss，**无 cache-write 字段** → 官方 OpenAI 格式观测在现有
   schema 下会按 PARTIAL/worst-case 结算。见 §4 / BLK-15。
4. **结论状态**：`PARTIAL / PASS_FOR_RESEARCH_SCOPE`；路由/价格/usage 均需人类决策（D-15..D-18、D-22）。
   本文件不改变 `LiveGate=BLOCKED`、`G4-H=NOT_AUTHORIZED`、`G5=BLOCKED`、`M0=DECISION_PENDING`。

## 1. 仓库既有声明（G4-R/A-NEXT 本地侧，D 级证据）

| # | 声明项 | 本工作树证据（file:line） | 声称值 |
|---|---|---|---|
| L1 | 默认 provider/route | `src/autoteacher_m0/settings.py:5` | `PRIMARY_ROUTE = "deepseek-official"`（本地标签） |
| L2 | 默认 model id | `src/autoteacher_m0/settings.py:6` | `MODEL = "deepseek-flash"` |
| L3 | 运行默认参数 | `src/autoteacher_m0/settings.py:18-21` | `max_tokens=1024`、`timeout_seconds=30.0`、`max_steps=8`、`max_retries=1` |
| L4 | route/model 变更约束 | `settings.py:30-34` | 必须等于冻结常量，否则 `ValueError`；steps≤8、retries≤1 |
| L5 | 选定模型/主路由/回退 | `config/models.example.yaml:1-15` | requested `DeepSeek V4.1 Flash`；primary `deepseek-official/deepseek-flash`；`approval: PENDING_INDEPENDENT_HUMAN_REVIEW`；`automatic_fallback: false`；`actual_alias_mapping: UNVERIFIED_LIVE` |
| L6 | 路由决策记录 | `docs/ROUTE_DECISION.md:7-15` | 同上；`human approver/approval date = NONE/NONE — NOT APPROVED`；模型版本映射 `UNVERIFIED LIVE` |
| L7 | egress 真实 allowlist | `src/autoteacher_m0/security/egress.py:31-34,101-124` | host `opencode.ai`:443、path 前缀 `/inference/go/`、route/model 仅 `opencode-go/deepseek-v4.1-flash`、`max_tokens≤1024`、`max_attempts≤4`（**第三方，不是官方**） |
| L8 | Controller 路由一致性校验 | `src/autoteacher_m0/security/live_controller.py:43,199-204` | `EXPECTED_EGRESS_POLICY = EgressPolicy()`；approved route ∉ allowlist → `ROUTE_NOT_IN_FROZEN_EGRESS_ALLOWLIST` |
| L9 | DSH target profile | `config/dsh/target-runtime.patch.yml:4-5,11-14,34-57`；`config/dsh/target-runtime-opencode-go.patch.yml:1-16` | `llm-deepseek`/compaction/image-offload 等 disabled；仅 synthetic `offline-test-only/fixture-v1` + guard（purposes `[conversation]`，maxProviderRetries 0，maxOutputTokens 1024）；OpenCode Go 仅 STATIC-ONLY 第三方 overlay（无 Key/网络） |
| L10 | synthetic 价格 fixture | `src/autoteacher_m0/accounting/pricing.py:50-54`；`config/dsh/target-broker-policy.json:22-33`；`docs/BUDGET_BROKER.md:40-55` | `input=1 / cached=0.5 / output=2` USD/1M，`source="synthetic offline fixture"`，`mock=True`，`captured_at 2026-11-14T00:00:00Z`（**不是真实价格**） |
| L11 | 本地预算/限额 | `config/budgets.yaml:1-13`；`security/live_controller.py:53-58`；`config/dsh/target-runtime.patch.yml:42-45` | soft $3 / hard $10 / soft-call $0.10 / hard-call $0.20 / ≤50 requests / ≤8 steps / ≤1 retry / 2.5M input / 600k output；`live_pricing_snapshot: REQUIRED_UNVERIFIED` |
| L12 | synthetic bridge route（非真实 provider） | `src/autoteacher_m0/bridge/controller.py:69-75`；`bridge/admission.py:10-19` | ROUTE `offline-test-only-g3b` / MODEL `fixture-bridge-v1`；`SYNTHETIC_FIXTURE_ONLY=True`；purposes `{None,"conversation"}`；admission 场景为合成白名单 |
| L13 | DSH 官方 provider 行命名（B 级辅助） | 旧 A2 S26/S27（B 级，2026-11-19 采集） | 内置 DeepSeek 路由 id `llm-deepseek`；模型 effort `off/low/high/max`；`llm-deepseek.reasoningEffort` 可配 |
| L14 | 本轮无真实调用 | `security/live_controller.py:66-70,249-287`；`gates.py:63-86`；`scripts/run_live.sh`；`dsh_adapter.py:101-110` | 恒 `EXTERNAL_*_NOT_DEPLOYED`；LiveGate BLOCKED；run_live exit 3；无真实 Key/模型/HTTP |

## 2. 官方契约（2026-11-19 研究快照；每行 = 快照 + 未获批/未真实调用 + 需重核）

> 采集时间统一 **2026-11-19T17:47:09Z–17:47:17Z UTC**（旧 A2 S01–S28；28 URL；完整 sha256 见旧
> `A2_SOURCES.md`）。状态 `VERIFIED-DOC` = 官方页面直接写明（仅文档层，不代表真实调用/当前有效）。

| 项目 | 官方值（快照） | 来源（URL + 采集日期） | 状态 | 与 G4-R 声明的差异 |
|---|---|---|---|---|
| 供应商 | DeepSeek 官方 API（非第三方网关） | `https://api-docs.deepseek.com/` @2026-11-19 | VERIFIED-DOC | 默认标签 `deepseek-official` 是本地标签，非官方字段名 |
| 请求 model 值 | `deepseek-flash` | `https://api-docs.deepseek.com/quick_start/pricing/`；`.../api/list-models/` @2026-11-19 | VERIFIED-DOC | 与 L2 一致 |
| 模型显示/版本 | `DeepSeek-V4.1-Flash` / `DeepSeek-V4.1-Flash-1017`；context 1,048,576；max output 393,216；input text+image | 同上 | VERIFIED-DOC | L5/L6 称 alias mapping `UNVERIFIED_LIVE`；文档层已明确别名，但无真实响应证据 |
| 别名/退役 | `deepseek-v4-flash`、`deepseek-v4-flash-vision-exp` 仍接受但退役，路由到 V4.1-Flash 并按 Flash 计费；`deepseek-chat`/`deepseek-reasoner` 已于 2026-07-24 停用 | `.../quick_start/pricing/`；`.../updates/` @2026-11-19 | VERIFIED-DOC | 仓库未使用旧名 |
| OpenAI 格式 base URL / path | `https://api.deepseek.com`；`POST /chat/completions` | `.../`；`.../api/create-chat-completion/` @2026-11-19 | VERIFIED-DOC | **egress allowlist 是 `opencode.ai:443` + `/inference/go/`（第三方），与官方 base/path 不一致（BLK-01）** |
| Anthropic 格式 | base `https://api.deepseek.com/anthropic`；`POST /v1/messages`；`x-api-key` 或 `Authorization: Bearer` | `.../guides/anthropic_api/` @2026-11-19 | VERIFIED-DOC | 仓库未声明 DSH 实际协议；UNVERIFIED |
| Responses API | `POST https://api.deepseek.com/responses` | `.../guides/responses_api/` @2026-11-19 | VERIFIED-DOC | 不在当前路由范围 |
| Streaming | `stream` 默认 false；data-only SSE；`data: [DONE]`；末 chunk 携带 usage（无单独 usage-only chunk）；`stream_options.include_usage` 需与 `stream:true` 同用 | `.../api/create-chat-completion/` @2026-11-19 | VERIFIED-DOC | 仓库 `egress.py` 默认 `stream=True`（L7 附近 105 行），无真实观测 |
| 鉴权（OpenAI） | `Authorization: Bearer ${DEEPSEEK_API_KEY}`；`Content-Type: application/json` | `https://api-docs.deepseek.com/` @2026-11-19 | VERIFIED-DOC | 候选容器无 Key（credential_boundary）；官方 Key 前缀/撤销 API 未文档化 |
| 请求字段 | `model`、`messages`（role: system/user/assistant/tool/latest_reminder）、`thinking{enabled/disabled}`、`reasoning_effort`（none/low/high/max，默认 high）、`max_tokens`（1..393216）、`stream`、`stream_options`、`temperature`（thinking 下无效）、`top_p`、`tools`（function + `deepseek_web_search`/`deepseek_read_url`）、`tool_choice`（thinking 下 required/具名→400）、`response_format`、`stop`、`logprobs/top_logprobs`、`user_id`、`title{enabled}`、`safety_check`；`frequency_penalty`/`presence_penalty` 已弃用 | `.../api/create-chat-completion/` @2026-11-19；标题：`.../guides/conversation_title/` | VERIFIED-DOC | 仓库真实请求 shape 未验证；第三方 overlay `reasoning:max` 不能外推官方 route |
| 响应/usage | `id`/`object`/`created`/`model`/`system_fingerprint`/`choices[]`/`usage`；`finish_reason` ∈ stop/length/content_filter/tool_calls/insufficient_system_resource/aborted；`prompt_tokens = prompt_cache_hit_tokens + prompt_cache_miss_tokens`；`prompt_tokens_details.cached_tokens`；`completion_tokens_details.reasoning_tokens`；`safety_tokens` 已含在 completion_tokens；`server_tool_use` 计数 | `.../api/create-chat-completion/`；`.../guides/responses_api/` @2026-11-19 | VERIFIED-DOC | **usage 三桶映射不兼容（见 §4）** |
| Cache | 默认开启 disk cache；best-effort、不保证 100%；`prompt_cache_hit_tokens`/`prompt_cache_miss_tokens`；**Chat Completions 无 cache-write token 字段**（Anthropic `cache_creation_input_tokens` 当前恒 0） | `.../guides/kv_cache/`；S04/S16 @2026-11-19 | VERIFIED-DOC | 仓库 `cacheWriteTokens` 无官方对应字段；fixture `cache_write=input_rate` 仅合成规则 |
| Reasoning | `thinking`/`reasoning_effort`；`reasoning_content`（非流式 message / 流式 delta）；带 `tools` 时历史 reasoning_content 必须回传，否则 400；reasoning_tokens 列在 completion/output 明细中（计费按 input+output token 总数；“reasoning 单独加费”无直接句 → 保守按 output 含 reasoning 计） | `.../guides/thinking_mode/`；S04/S17 @2026-11-19 | VERIFIED-DOC + INFERRED（口径） | 仓库 `included_in_output` fixture 与保守口径一致；真实账单未验证 |
| 错误/超时 | 400/401/402/408/413/422/429/500/503/504 有官方语义；并发超限→429（flash 并发 2500，account 级）；“未开始推理超 10 分钟服务器断开”；无文档化 Retry-After/幂等 key；5xx 建议 brief wait 后 retry | `.../quick_start/error_codes/`；`.../quick_start/rate_limit/` @2026-11-19 | VERIFIED-DOC；QPS 数值/Retry-After/重复计费 = UNVERIFIED | 仓库 `maxProviderRetries=0`；真实 429/5xx 行为未观测 |
| 价格 | flash（USD，1M）：cache hit off $0.003/peak $0.006；miss off $0.15/peak $0.30；output off $0.60/peak $1.20；峰值窗口周一至周五 01:00–04:00、06:00–10:00 UTC；off=peak 50%；CNY 价目另列 | `.../quick_start/pricing/`（USD）；`.../zh-cn/quick_start/pricing/`（CNY）@2026-11-19 | VERIFIED-DOC（快照） | 仓库 fixture 价 `1/0.5/2` 是合成；`live_pricing_snapshot: REQUIRED_UNVERIFIED`；价格可变 |
| 额度查询 | `GET /user/balance` → `is_available`、`balance_infos[{currency,total_balance,granted_balance,topped_up_balance}]` | `.../api/get-user-balance/` @2026-11-19 | VERIFIED-DOC（schema） | 仓库无真实查询；Console UI/导出 UNVERIFIED |
| 撤销路径 | 官方 “apply for an API key” → `platform.deepseek.com/api_keys`（Console SPA，需登录/JS；本次采集仅 SPA 壳） | `https://api-docs.deepseek.com/`；`https://platform.deepseek.com/api_keys` @2026-11-19 | 路径存在 VERIFIED-DOC；撤销 UI/生效时间 **UNVERIFIED** | 仓库无 Key 撤销实现；旧 A2 已记录 429/SPA 壳 |

## 3. G4-R 实际路由与官方契约的差异（A-NEXT 适配重点）

| ID | 差异 | 代码证据（本工作树） | 影响/处置 |
|---|---|---|---|
| A-01 | 默认官方路由 vs egress 第三方白名单 | `settings.py:5-6` 官方；`egress.py:31-34,101-124` 第三方；`live_controller.py:43,199-204` 要求 approved route ∈ egress allowlist | **BLK-01**：D-15/D-16 选定并统一；官方 route 需 `api.deepseek.com:443` + `/chat/completions`，第三方 route 不能记官方 PASS |
| A-02 | DSH target profile 无官方 route | `config/dsh/target-runtime.patch.yml:4-5` 禁 `llm-deepseek`；只 synthetic `offline-test-only/fixture-v1`；`target-runtime-opencode-go.patch.yml` STATIC-ONLY 第三方 | **BLK-14**：D-19；H1 若选官方需新增/审计 profile + 仓库外 Key/egress |
| A-03 | usage 三桶 vs 官方 hit/miss | `broker_usage.py:3,15,69-98`；`observation.py:38-46,258`；官方 S04/S05 无 cache-write | **BLK-15**：D-18 usage mapping v2；否则官方观测按 PARTIAL worst-case |
| A-04 | 无真实 provider transport | `egress.py:1-10` 自述 descriptor diagnostics、`TrustedEgressTransport` 仅注入接口；`live_controller` 无 run/execute | **BLK-04**：真实 Egress 部署（人类） |
| A-05 | synthetic bridge 不是真实 provider | `bridge/controller.py:69-75`：ROUTE `offline-test-only-g3b`、`SYNTHETIC_FIXTURE_ONLY=True`；`bridge/admission.py:19` | 不得把 synthetic bridge 当真实 route 证据 |
| A-06 | 价格快照未重核 | `config/budgets.yaml:11` `live_pricing_snapshot: REQUIRED_UNVERIFIED`；旧 A2 快照 2026-11-19 | **BLK-13**：D-17/D-22；G5 前重采 |

## 4. usage 映射不兼容（详细）

- 官方 OpenAI Chat Completions：`prompt_tokens = prompt_cache_hit_tokens + prompt_cache_miss_tokens`；`prompt_tokens_details.cached_tokens` 与 hit 相同；**无 cache write 字段**（旧 A2 S04/S05）。
- 官方 Anthropic 格式：`input_tokens` **不含 cache 命中**；总输入 = `input_tokens + cache_read_input_tokens + cache_creation_input_tokens`（`cache_creation` 当前恒 0）（S16）。
- 本地：`broker_usage.py:3,15,69-98` 要求 `inputTokens`（uncached）、`cacheReadTokens`、`cacheWriteTokens` 三个互斥桶**全部非 None** 才算完整；`observation.py:38-46,258` 同；缺失维度按 worst-case。
- 结论：若 G5 选**官方 OpenAI 格式**，现有 schema 会把真实观测判为 `PARTIAL`（缺 cache_write），预算读数偏保守且无法与官方 usage 对账；若选 **Anthropic 格式**，三桶可映射（cache_creation=0）。这需要 D-18 批准修复/适配，不能由 Agent 自行“填 0”。

## 5. BLOCKER（详见 `A_NEXT_HUMAN_HANDOFF.md` §4）

- **BLK-01** 默认路由与 egress allowlist 不一致（本节 §3 A-01）。
- **BLK-02/03/04/05** 真实信任根/Key Broker/Egress/Watchdog 未部署；**BLK-06** LiveGate 恒 BLOCKED。
- **BLK-13** 真实 wire/usage/账单未验证；**BLK-14** DSH target profile 无官方 route；**BLK-15** usage 映射不兼容。
- **BLK-10/11/12** B03/E5-P04 `UNVERIFIED`、E5-Full 未授权、G5 未授权。
- 其余 BLK-07..BLK-09、BLK-16..BLK-18 见 Handoff。

## 6. UNVERIFIED（不得填猜测值）

1. 真实 `/models`、`/chat/completions`、`/user/balance` 响应；真实 tokenizer 计数。
2. 真实 usage/账单/invoice 对账；reasoning tokens 是否与 completion_tokens 单列计费（INFERRED）。
3. 官方 Key 前缀/格式/撤销/轮换 API 与生效时间。
4. 429 QPS 数值、Retry-After、重复计费/断连计费语义。
5. 完整请求超时（已核实“预推理 10 分钟断开”，推理中途超时未说明）。
6. DSH 官方直连 provider 的默认 endpoint/协议/key env（B 级文档未给 base URL 字符串）。
7. DSH target profile 的真实 wire/merged tool registry（B03/E5-P04）。
8. 价格表版本/精确生效日；未来价格变动；web 工具/文件/OCR 扩展计费当前状态（官方页面时间线冲突）。
9. 维护者账户币种（CNY/USD）与实际结算。

## 7. 人类决策引用（不代签）

- D-15 Provider 主路由选择（官方/第三方/双路由）。
- D-16 Egress allowlist 与 route 统一。
- D-17 官方价格快照重核/签收；D-18 usage mapping v2；D-22 快照有效期/重验责任人。
- D-19 DSH target profile 是否启用官方 `llm-deepseek`。
- D-12 G5 单次授权、D-11 人类部署；全部 `UNSIGNED`（见 `A_NEXT_HUMAN_HANDOFF.md`）。

## 8. 声明

本文件不改变任何门状态、不授权真实调用、不构成 A-05 PASS 或官方契约批准。所有外部事实为
**2026-11-19 研究快照、未获批、未真实调用**；正式审批（尤其 G5）前必须重新采集官方资料并逐项签收。
