# PROVIDER_CONTRACT_DRAFT — DeepSeek 官方 API（M0/A2，无 Key 研究稿）

- 任务：`task-3`（A2 Provider 契约与计费核实，research）；工作树 `worktrees/m0-g4h0-research`，分支 `work/m0-g4h0-research`，基线 `3e7afee`
- **性质**：公开官方文档研究稿。**不是**部署授权、路由批准、E5/G4-H/G5 通过凭据；不得据此发送真实请求。
- 本轮边界：**无真实 Key、无登录、0 真实模型/HTTP 计费调用**；只做官方公开页面只读采集（采集时间见 [A2_SOURCES.md](./A2_SOURCES.md)，主批次 2026-11-19T17:47:09Z–17:47:17Z UTC）。
- 判定用词：`VERIFIED`＝本次采集的官方页面直接写明；`INFERRED`＝由官方字段/示例推出但无直接句子，**不作契约依据**；`UNVERIFIED`＝官方页面未提供/不可达/需账户或实测，不得填猜测值。
- 来源编号 `Sxx` 对应 [A2_SOURCES.md](./A2_SOURCES.md) §2 的 URL + 采集时间 + sha256；文中另给 URL 简写与采集时间。
- 目标路由的最终 provider/model/endpoint/费率仍须**维护者在 G4-H1/G5 前明确确认**（执行方案 §4 A2）。

## 0. 结论摘要

1. **官方契约层（DeepSeek 官方 API）已可核实的核心项**：model id `deepseek-flash`（服务别名，实际版本 DeepSeek-V4.1-Flash-1017）；OpenAI 格式 base URL `https://api.deepseek.com`，`POST /chat/completions`；OpenAI 格式鉴权 `Authorization: Bearer <key>`；支持 streaming（SSE，`data: [DONE]`，末 chunk 携带 usage）；usage 有 `prompt_tokens`/`completion_tokens`/`prompt_cache_hit_tokens`/`prompt_cache_miss_tokens`/`completion_tokens_details.reasoning_tokens` 等；cache hit/miss 单价；429/5xx 语义与并发上限 2500 均有官方文字。
2. **本仓库存在两条互相冲突的“目标路由”声明**（见 §1/§2/§15）：
   - (a) **官方主路由声明**：`settings.py`、`config/models.example.yaml`、`docs/ROUTE_DECISION.md`、`docs/Autonomous_Teacher_M0_v04.md` → `deepseek-official / deepseek-flash`（设计默认，**未批准、未实测**）。
   - (b) **第三方网关声明**：`docs/BILLABLE_PATH_INVENTORY.md` 与 `src/autoteacher_m0/security/egress.py` 把 egress allowlist 固定为 `opencode.ai:443` + `/inference/go/` + route/model `opencode-go/deepseek-v4.1-flash`；`config/dsh/target-runtime-opencode-go.patch.yml` 是 STATIC-ONLY 叠加。
   - 当前 DSH 目标 Profile（`config/dsh/target-runtime.patch.yml`）**显式禁用 `llm-deepseek`**，只启用 synthetic fixture route；**不存在任何官方 DeepSeek provider 可用路径**。
   → 结论：**provider/route 选择是 HUMAN DECISION，本文件不替人类选择**。A2 的“目标 provider 契约”按官方主路由声明起草；OpenCode Go 属第三方，按 C 级来源处理，不能作为契约依据。
3. **与仓库既有声明的关键差异**（详见 §15）：egress 白名单 host/path/route/model 与官方主路由不一致；仓库 usage 映射要求 3 个互斥 input 桶（含 `cacheWriteTokens`），而官方 Chat Completions **不返回 cache write tokens**；仓库无任何真实 wire 证据（本轮亦无）。
4. **A2/A-05 建议状态**：`PARTIAL / PASS_FOR_RESEARCH_SCOPE`——官方文档层契约与价格已核实并记录差异；但“目标路由选定 + 官方价格快照人工签收 + usage 映射 v2 + 真实 wire/账单证据”仍未完成，不能记为 A-05 PASS。

## 1. 仓库既有声明（本地侧，D 级证据，不是供应商事实）

| # | 声明项 | 仓库证据（file:line） | 声称值 |
|---|---|---|---|
| L1 | 目标 provider / route id | `src/autoteacher_m0/settings.py:5` | `PRIMARY_ROUTE = "deepseek-official"`（本地标签） |
| L2 | 目标 model id | `src/autoteacher_m0/settings.py:6` | `MODEL = "deepseek-flash"` |
| L3 | 运行默认参数 | `src/autoteacher_m0/settings.py:18-21` | `max_tokens=1024`, `timeout_seconds=30.0`, `max_steps=8`, `max_retries=1` |
| L4 | route/model 变更约束 | `src/autoteacher_m0/settings.py:30-34` | 必须等于冻结常量，否则 `ValueError`；steps≤8、retries≤1 |
| L5 | 选定模型/主路由/回退 | `config/models.example.yaml:2-14` | requested_model `DeepSeek V4.1 Flash`；primary `deepseek-official/deepseek-flash`；`approval: PENDING_INDEPENDENT_HUMAN_REVIEW`；`automatic_fallback: false`；`actual_alias_mapping: UNVERIFIED_LIVE` |
| L6 | 路由决策记录 | `docs/ROUTE_DECISION.md:7-15` | 同上；`human approver/approval date = NONE/NONE — NOT APPROVED`；实际响应型号/请求 ID/版本映射 `UNVERIFIED LIVE` |
| L7 | 官方主路由与 OpenCode Go 的关系 | `docs/Autonomous_Teacher_M0_v04.md:7-10, 121-126` | 默认主验收渠道官方 `deepseek-official/deepseek-flash`；OpenCode Go 仅“可选开发订阅调查”，不能当零成本 Runtime API；主渠道切换须人工批准并全量重验 |
| L8 | 真实路由模板（冻结） | `docs/M0_G4_C_EGRESS_CONTRACT.md:95-104` | `route_id=deepseek-official provider=deepseek model_id=None 端点/路径/版本/流式/tokenizer 全部 None`，`activation=BLOCKED_REQUIRES_HUMAN_VERIFICATION` |
| L9 | egress allowlist | `docs/BILLABLE_PATH_INVENTORY.md:24-31`；`src/autoteacher_m0/security/egress.py:31-34, 99-124` | host `opencode.ai`:443、path 前缀 `/inference/go/`、route/model 仅 `opencode-go/deepseek-v4.1-flash`、`max_tokens≤1024`、`max_attempts≤4`（**第三方网关，不是官方**） |
| L10 | DSH 目标 Profile | `config/dsh/target-runtime.patch.yml:4-5, 11-12, 34-55`；`docs/DSH_TARGET_PROFILE.md:8-11, 22, 30-34` | `llm-deepseek` disabled；compaction/image-offload/工具禁用；`offline-test-only/fixture-v1` synthetic route + guard（policy sha `c67d2bbf…8129`，purposes `[conversation]`，maxProviderRetries 0，maxOutputTokens 1024）；`target-runtime-opencode-go.patch.yml` 仅 STATIC-ONLY |
| L11 | synthetic 价格 fixture | `src/autoteacher_m0/accounting/pricing.py:50-54`；`config/dsh/target-broker-policy.json:22-33`；`docs/BUDGET_BROKER.md:40-55` | `input=1 / cached=0.5 / output=2` USD per 1M，`source="synthetic offline fixture"`，`mock=True`，`captured_at 2026-11-14T00:00:00Z`（**不是真实价格**，不得当报价） |
| L12 | 本地预算/限额 | `config/budgets.yaml:1-13`；`src/autoteacher_m0/security/live_controller.py:46-57`；`docs/Autonomous_Teacher_M0_v04.md:436-446` | soft $3 / hard $10 / soft-call $0.10 / hard-call $0.20 / ≤50 requests / ≤8 steps / ≤1 retry / 2.5M input / 600k output tokens；`live_pricing_snapshot: REQUIRED_UNVERIFIED`；`$10 是工程硬顶，不是供应商硬限`（`M0_G4_A_AUTHORITY_CONTRACT.md:29, 361`） |
| L13 | DSH 官方 provider 行命名（辅助） | `deepseek-harness.github.io/.../guide/providers` S27（B 级） | 内置 DeepSeek 路由 id `llm-deepseek`；模型 effort `off/low/high/max`；`llm-deepseek.reasoningEffort` 可设默认；直连 adapter 由 `llm-deepseek` 配置面拥有 |
| L14 | 本轮现状 | `docs/E5_PRELIVE_NO_KEY_REPORT.md:15-24, 79`；`docs/M0_G4F_HUMAN_HANDOFF.md:14-16` | 无真实 Key、0 模型/0 HTTP；H-01/H-02（真实 Key/价格与 usage 对账）为 `PENDING_HUMAN_ACTION` |

## 2. 目标 provider 与 model 语义

| 项目 | 官方值 | 来源（URL + 采集时间） | 判定 | 与仓库声明差异 |
|---|---|---|---|---|
| 供应商 | DeepSeek（官方 API，非第三方网关） | S01 `https://api-docs.deepseek.com/` @17:47:09Z | VERIFIED | 仓库主路由标签 `deepseek-official` 是**本地标签**，不是官方产物的字段名 |
| 当前模型名（请求 model 值） | `deepseek-flash` | S02 `.../quick_start/pricing/` @17:47:09Z；S04 `.../api/create-chat-completion/` @17:47:09Z；S07 `.../api/list-models/` @17:47:09Z | VERIFIED | 与 L2/L5/L6 一致（`deepseek-flash`） |
| 模型显示名/实际版本 | display `DeepSeek-V4.1-Flash`；version `DeepSeek-V4.1-Flash-1017` | S02；S07 | VERIFIED（文档层） | 仓库 L5/L6 声称 "DeepSeek V4.1 Flash / alias mapping UNVERIFIED_LIVE"：**别名映射现已有官方文字**（见下条），但真实响应仍需实测 |
| 别名/退役语义 | `deepseek-v4-flash`、`deepseek-v4-flash-vision-exp` 仍被接受，但对应模型已退役，请求由 `DeepSeek-V4.1-Flash-1017` 服务并按 Flash 价格计费；旧名 `deepseek-chat`/`deepseek-reasoner` 已于 2026-07-24 停用 | S02；S19 `.../updates/` @17:47:11Z（2026-04-24、2026-09-10 条目） | VERIFIED | 仓库未使用这些旧名；无冲突 |
| 上下文窗口 | 1,048,576 tokens（页面写 1M） | S07（`context_window: 1048576`）；S02（CONTEXT LENGTH 1M） | VERIFIED | 仓库未固定此值；L3 `max_tokens=1024` 远小于上限 |
| 最大输出 | `max_tokens` ∈ [1, 393216]（页面写 MAXIMUM 384K）；不设时：非思考 8K、思考 64K、`reasoning_effort=max` 128K | S04（`max_tokens` 描述）；S07（`max_output_tokens: 393216`）；S02（MAX OUTPUT 384K） | VERIFIED | 仓库 DSH guard `maxOutputTokens=1024` 与 egress `MAX_OUTPUT_TOKENS=1024` 更保守，不冲突 |
| 输入/输出模态 | input text+image；output text（仅 `deepseek-flash` 支持 image） | S07 | VERIFIED | 仓库 egress deny images/files；不在 M0 范围 |
| thinking/effort | 支持非思考与思考（**默认思考开启**）；`reasoning_effort`: `none` 关闭、`low/high/max` 开启，默认 `high`；`minimal`→low，`medium/xhigh`→high | S01；S04；S06 `.../guides/thinking_mode/` @17:47:09Z | VERIFIED | 仓库 DSH 主路由声明未固定 effort；第三方 overlay 用 `reasoning: max`；本地 DSH 文档（B 级）称 DeepSeek 模型提供 off/low/high/max |
| 模型列表 | `GET /models` 返回 id/owned_by/name/context_window/max_output_tokens/modalities/effort/api_capabilities | S07 | VERIFIED（schema） | 仓库无 /models 校验逻辑；UNVERIFIED 项：真实返回 |
| 并发上限 | `deepseek-flash` 2500（account 级，与 key 无关）；超过 → HTTP 429；可申请扩容（不额外收费） | S09 `.../quick_start/rate_limit/` @17:47:09Z；S02 | VERIFIED | 仓库无供应商并发声明；本地 50 请求上限远低于并发上限 |

## 3. Endpoint / base URL / path / 协议

| 项目 | 官方值 | 来源 | 判定 | 与仓库差异 |
|---|---|---|---|---|
| OpenAI 兼容 base URL | `https://api.deepseek.com` | S01；S02 | VERIFIED | 仓库未把官方 base URL 固化到 egress（egress 固定 opencode.ai） |
| Chat Completions path | `POST /chat/completions` → `https://api.deepseek.com/chat/completions` | S01（curl 示例）；S04（`POST /chat/completions`） | VERIFIED | 同上；L8 模板所有端点字段为 None（BLOCKED） |
| Anthropic 兼容 base URL | `https://api.deepseek.com/anthropic`；`POST /v1/messages` | S01；S02；S16 `.../guides/anthropic_api/` @17:47:10Z | VERIFIED | 仓库未声明 DSH 使用哪种协议；UNVERIFIED |
| Responses API | `POST https://api.deepseek.com/responses` | S01 首页说明/标题页示例；S17 `.../guides/responses_api/` @17:47:10Z | VERIFIED | 同上 |
| FIM/前缀续写 beta | 需 `base_url="https://api.deepseek.com/beta"` | S04（assistant `prefix` 字段说明） | VERIFIED | 不在 M0 范围 |
| Models / Balance / Files | `GET /models`；`GET /user/balance`；`POST /files`（及 list/retrieve/delete） | S07；S08 `.../api/get-user-balance/` @17:47:09Z；S12 `.../guides/files_api/` @17:47:10Z | VERIFIED（schema） | 仓库无真实调用；M0 不涉及 |
| URL 规范化 | 文档页无结尾斜杠 → 302 到带斜杠（采集记录） | A2_SOURCES §3 | VERIFIED（本次采集行为） | 仅影响文档抓取，不影响 API |
| DSH 内置官方 provider 行的真实 base URL | 官方 DSH 文档只说 "default endpoint"（默认端点），未在本次页面显式给出 `api.deepseek.com` 字符串 | S26/S27（B 级）@17:47:11Z/17:47:14Z | **UNVERIFIED**（DSH 内部默认值未由本次采集证明；需 `--dump-config` 或源码证据） | 仓库 DSH 目标 Profile 已禁用 `llm-deepseek`，当前不影响；G4-H1 前须核实 |
| 与 OpenCode Go 的区别 | OpenCode Go 是第三方订阅网关（`opencode.ai/inference/go/...`），**不是** DeepSeek 官方 API；官方文档把 OpenCode 列为可接入 DeepSeek 官方 API 的客户端 | S01；S23 `.../quick_start/agent_integrations/opencode/` @17:47:11Z；C 级 S28 | VERIFIED（区别性质） | **仓库 egress/BILLABLE_PATH_INVENTORY 把两者混用**（见 §15 D-01/D-02） |

## 4. Streaming 支持

| 项目 | 官方值 | 来源 | 判定 | 与仓库差异 |
|---|---|---|---|---|
| 是否支持 | 支持；`stream` 默认 false | S04 | VERIFIED | 仓库 egress `EgressRequest.stream: bool = True`（egress.py:105）默认流式，未在真实 wire 验证 |
| 传输格式 | data-only SSE；以 `data: [DONE]` 结束 | S04 | VERIFIED | 仓库无 SSE 解析真实证据（合成 fixture/描述符层） |
| 流中 usage | 两种模式下**最后一个 chunk 都携带**整次请求 usage；`stream_options.include_usage=true` 时所有 chunk 带 `usage`（非最后为 null）；文档明确“**不单独发 usage-only chunk**”，usage 搭在最后内容 chunk 上 | S04（`stream_options.include_usage` 描述） | VERIFIED | 仓库预算结算要求 usage/上界；真实流式 usage 解析未验证 |
| 流式失败/中断 | `finish_reason` 可为 `insufficient_system_resource`/`aborted`；`stream_options` 未与 `stream:true` 同用 → 400 | S04 | VERIFIED | 仓库失败矩阵把这些归为 BILLABLE_UNKNOWN/worst-case（合理） |
| keep-alive | 非流式返回空行、流式返回 SSE 注释 `: keep-alive`；**10 分钟未开始推理服务器断开连接** | S09 | VERIFIED | 仓库 `timeout_seconds=30`（settings.py:19）并禁用 provider retry；无真实观测 |
| 生成标题（同一请求） | `title: {"enabled": true}` 时标题随回答一起生成，**不额外请求、不额外计费**；答案结束后最多等 5 秒标题 | S11 `.../guides/conversation_title/` @17:47:10Z | VERIFIED | 仓库未见 DSH title 路径证据；见 BILLABLE_PATH_INVENTORY |

## 5. 鉴权（header 位置与格式）

| 协议/项 | 官方值 | 来源 | 判定 | 与仓库差异 |
|---|---|---|---|---|
| OpenAI 格式 | HTTP header `Authorization: Bearer ${DEEPSEEK_API_KEY}`；`Content-Type: application/json` | S01（curl 示例：`-H "Content-Type: application/json"`、`-H "Authorization: Bearer ..."`） | VERIFIED | 仓库候选容器**永不持有真实 Key**（`LIVE_CONTROLLER_SECURITY_DESIGN.md:89-119`）；Key 由仓库外 launcher/Key Broker 注入（设计约束） |
| Anthropic 格式 | 二选一：`x-api-key: <API_KEY>` 或 `Authorization: Bearer <API_KEY>` | S16（"Authenticate with either x-api-key … or Authorization: Bearer …"；`x-api-key` Fully Supported） | VERIFIED | 同上 |
| 环境变量名（官方示例） | `DEEPSEEK_API_KEY` | S01 | VERIFIED | 仓库 DSH SDK 的 `base_url`/`api_key` 映射为 `DEEPSEEK_BASE_URL`/`DEEPSEEK_API_KEY`（`docs/OPENCODE_GO_ACCESS.md:180-195`，本地声明）；官方主路由凭据名应以此为准，UNVERIFIED 的是 DSH 实际注入路径 |
| Key 生命周期/前缀/撤销 API | 官方文档仅给“apply for an API key”入口与 Console 链接；**未在本次采集页面找到 key 前缀/长度/撤销 API 文档** | S01；S24/S25（Console SPA 壳，内容 UNVERIFIED） | **UNVERIFIED**（撤销/轮换 UI 细节）；“需登录 Console”为 VERIFIED | 仓库的 `oc_sk_` 前缀/撤销描述来自 OpenCode（第三方），**不能用于官方 Key** |

## 6. 请求字段（Chat Completions，官方支持项）

> 来源：S04 `https://api-docs.deepseek.com/api/create-chat-completion/` @2026-11-19T17:47:09Z（除非另注）。`VERIFIED` 指字段存在及语义有官方文字；`UNVERIFIED` 指未在本次文档找到。

| 字段 | 官方语义（摘要） | 判定 | 与仓库/DSH 声明差异 |
|---|---|---|---|
| `model` | 必填；枚举 `deepseek-flash`、`deepseek-v4-pro` | VERIFIED | settings 固定 `deepseek-flash`；第三方 route 用 `deepseek-v4.1-flash`（不同渠道标识） |
| `messages` | 必填，≥1；role：`system`/`user`/`assistant`/`tool`/`latest_reminder`；content 支持字符串或 content parts（text/image_url/file） | VERIFIED | 仓库 target Profile 工具/图像禁用；无真实消息形状证据 |
| `thinking` | `{type: enabled\|disabled}`；与 `reasoning_effort` 同时出现时以 `thinking` 优先 | VERIFIED | 仓库 broker 用 synthetic fixture，无真实 thinking 字段 |
| `reasoning_effort` | `none/low/high/max`，默认 high；`minimal`→low、`medium/xhigh`→high | VERIFIED | 仓库 DSH overlay `reasoning: max`（第三方 route）；官方 route 未固定 |
| `max_tokens` | 1..393216；默认 8K（非思考）/64K（思考）/128K（effort=max） | VERIFIED | 仓库 `max_tokens=1024`（settings.py:18）、guard/egress 1024 |
| `stream` | 默认 false；true 走 SSE | VERIFIED | egress 默认 True |
| `stream_options` | 需与 `stream:true` 同用；`include_usage` 语义见 §4；否则 400 | VERIFIED | 仓库未在真实请求使用 |
| `temperature` | 0..2，默认 1；**thinking 模式下无效** | VERIFIED | 仓库无真实参数验证 |
| `top_p` | >0..≤1；`deepseek-flash` 思考模式默认 1.0 且 <0.95 视为 0.95；非思考固定 1.0 忽略传入值 | VERIFIED | 同上 |
| `tools` | function 工具 + 服务端 web 工具 `deepseek_web_search`/`deepseek_read_url`；函数名唯一 | VERIFIED | 仓库工具白名单仅 `skill_lookup`（授权契约）；无真实 tool calling 证据 |
| `tool_choice` | `none/auto/required` 或指定函数；**thinking 模式下 required/指定函数 → 400**；声明 web 工具时 required 视为 auto | VERIFIED | 同上 |
| `response_format` | `{type: text\|json_object}`；JSON 模式需提示词要求 JSON，失败时非 JSON 内容替换为空格；`finish_reason=length` 可能截断 | VERIFIED | 仓库 experiments 有结构化输出 fixture；真实 JSON 模式未验证 |
| `stop` | 最多 16 个序列，每个非空 ≤512 bytes | VERIFIED | 未使用 |
| `logprobs`/`top_logprobs` | logprobs 默认 false；top_logprobs 0..20 | VERIFIED | 未使用 |
| `user_id` | 字符串（建议 ASCII 字母数字 `_` `-`，≤512 bytes；勿含隐私）；用于内容安全/KVCache 隔离/调度隔离 | VERIFIED | 仓库未使用；若 Live 使用需隐私评估 |
| `title` | `{enabled: true}` 返回会话标题（不额外请求/计费） | VERIFIED | 仓库未见 DSH title 路径；UNVERIFIED |
| `safety_check` | `{level: low\|high}`；high 增加安全审查，`safety_tokens` 计入 completion_tokens | VERIFIED | 仓库未使用；真实风险控制未评估 |
| `frequency_penalty`/`presence_penalty` | **已弃用**：传入不生效 | VERIFIED | 无冲突 |
| `seed`/`n` | 本次采集的 Chat Completions 字段未列出（未找到官方支持文字） | **UNVERIFIED**（不假设支持） | 仓库未使用 |
| 未知字段/非法值 | 文档给出 400 Invalid Format / 422 Invalid Parameters 错误码 | VERIFIED（错误码表 S10） | 仓库无真实 400/422 观测 |

## 7. 响应字段与 usage

| 字段/层级 | 官方值（摘要） | 来源 | 判定 |
|---|---|---|---|
| 顶层 | `id`、`object="chat.completion"`、`created`、`model`、`system_fingerprint`、`choices[]`、`usage` | S04 | VERIFIED（schema+示例） |
| `choices[].message` | `role`、`content`、`reasoning_content`（思考模式）、`tool_calls`、`annotations`（web 工具引用）、`server_tool_calls`（DeepSeek 扩展）、`title`（title 开启时）、`refusal`（图像安全拦截时）、`logprobs` | S04 | VERIFIED |
| `choices[].finish_reason` | `stop`/`length`/`content_filter`/`tool_calls`/`insufficient_system_resource`/`aborted` | S04 | VERIFIED |
| `usage.prompt_tokens` | prompt token 总数；**等于 `prompt_cache_hit_tokens + prompt_cache_miss_tokens`** | S04 | VERIFIED |
| `usage.completion_tokens` | 生成 completion token 数 | S04 | VERIFIED |
| `usage.total_tokens` | prompt+completion | S04；示例 7+11=18 | VERIFIED |
| `usage.prompt_tokens_details.cached_tokens` | 命中上下文缓存的 prompt token 数；**与 `prompt_cache_hit_tokens` 相同** | S04 | VERIFIED |
| `usage.prompt_cache_hit_tokens` / `prompt_cache_miss_tokens` | 命中/未命中 cache 的输入 token 数（均在 chat completion 页显式字段） | S04；S05 | VERIFIED |
| `usage.completion_tokens_details.reasoning_tokens` | 模型用于推理的 token 数（推理 token 明细） | S04 | VERIFIED（字段）；**“按输出计费”无直接句 → INFERRED，见 §9** |
| `usage.completion_tokens_details.safety_tokens` | 安全审查 token，**已包含在 completion_tokens 内**；仅 `safety_check=high` 时出现 | S04 | VERIFIED |
| `usage.server_tool_use` | 服务端 web 工具计数 `tool_search`/`tool_fetch`/`tool_image_search`；全为 0 时省略 | S14；S17 | VERIFIED |
| Responses/Anthropic 的 usage 命名差异 | Responses：`input_tokens`/`output_tokens`/`input_tokens_details.cached_tokens`/`output_tokens_details.reasoning_tokens`；Anthropic：`input_tokens`（**不含 cache 命中**）/`cache_read_input_tokens`/`cache_creation_input_tokens`（当前为 0）/`output_tokens`，总输入=input+cache_read+cache_creation | S17；S16（"input_tokens excludes cache hits … total input = input_tokens + cache_read_input_tokens + cache_creation_input_tokens"） | VERIFIED |
| 响应中的计费美元字段 | chat completion usage **未包含 `cost`/invoice 金额字段**；官方计费按 token 数×单价，从余额扣减 | S02；S04 | VERIFIED（无 cost 字段）；实际账单需 Console 对账（UNVERIFIED） |
| **与仓库 usage 映射的冲突** | 仓库 `broker_usage.official_usage` 要求 input/cacheRead/cacheWrite **三个互斥桶**都非 None 才算 `complete_input`（`src/autoteacher_m0/accounting/broker_usage.py:3, 69-98`；`src/autoteacher_m0/accounting/observation.py:36-46, 258`）；官方 Chat Completions **只给 total prompt + hit + miss，无 cache write 字段** | S04；S05 | **差异 D-03**：官方 OpenAI 格式观测在仓库现有 schema 下会被判为 PARTIAL/缺维度 → 按 worst-case 结算；需 v2 映射（miss→input、hit→cache_read、cache_write 不在该协议出现） |

## 8. Cache 计费字段

| 项目 | 官方值 | 来源 | 判定 | 与仓库差异 |
|---|---|---|---|---|
| 是否默认开启 | Context Caching on Disk 对所有用户默认开启，无需改代码 | S05 | VERIFIED | 仓库 fixture 假设 implicit cache（BILLABLE_PATH_INVENTORY B4），仅形状 |
| 命中条件 | 前缀需已“持久化”为 cache prefix unit；按请求边界/公共前缀/固定 token 间隔持久化；需**完整匹配** cache prefix unit；best-effort，不保证 100% 命中；缓存构建需数秒；闲置后数小时~数天清空 | S05 | VERIFIED | 同上 |
| 计费字段 | 响应 `usage.prompt_cache_hit_tokens`、`prompt_cache_miss_tokens`；`prompt_tokens = hit + miss` | S04；S05 | VERIFIED | 见 D-03 |
| 是否报告 cache write tokens | **Chat Completions 文档未定义 cache write tokens 字段**（Anthropic 兼容格式的 `cache_creation_input_tokens` 当前恒为 0） | S04；S16 | VERIFIED（缺字段） | 仓库 `cacheWriteTokens` 语义无官方对应字段 → 不得把 0 当事实；`cache_write=input_rate` 仅 fixture 规则（BUDGET_BROKER.md:58-62） |
| cache 单价 | 见 S02 价格表（`1M INPUT TOKENS (CACHE HIT)` 与 `(CACHE MISS)` 分开，peak/off-peak） | S02；S03；[PRICE_AND_USAGE_VERIFICATION.md](./PRICE_AND_USAGE_VERIFICATION.md) | VERIFIED | 仓库无真实价格；fixture 0.5/1/2 为 synthetic |
| user_id 与 cache 隔离 | `user_id` 可用于 KVCache 隔离（隐私） | S09 | VERIFIED | 仓库未使用 user_id；若 Live 需评估隐私 |
| 仓库 reserve 策略 | 预留按 `max(input, cached)`，不假设 cache 折扣 | `src/autoteacher_m0/accounting/pricing.py:44-47` | （本地策略）合理 | 与官方 cache 折扣方向一致；真实 cache hit 率 UNVERIFIED |

## 9. Reasoning 字段与计费口径

| 项目 | 官方值 | 来源 | 判定 |
|---|---|---|---|
| 开关 | `thinking: {type: enabled\|disabled}`；默认（两者都省略）**开启思考** | S04；S06 | VERIFIED |
| effort | `reasoning_effort: none/low/high/max`；默认 high；不接受其他值（minimal/medium/xhigh 被兼容映射） | S04；S06 | VERIFIED |
| 输出位置 | 非流式：`choices[0].message.reasoning_content`；流式：`delta.reasoning_content` | S04；S06 | VERIFIED |
| tools+thinking 回传要求 | 带 `tools` 的请求必须把历史 `reasoning_content` 完整回传，否则 **400**；不带 tools 时 reasoning_content 不需回传（传了也被忽略） | S06 | VERIFIED |
| 计费口径 | 官方计费按“输入+输出 token 总数”；usage 把 `reasoning_tokens` 放在 `completion_tokens_details`（Chat）/`output_tokens_details`（Responses）内 | S02；S04；S17 | VERIFIED（字段归属）；“reasoning 按输出计费/是否与 completion_tokens 双重计数”**无直接句 → INFERRED**，不得单独作为费用上界依据；保守上界应按 output 含 reasoning 计（与仓库 `included_in_output` fixture 一致） |
| safety_tokens | 已包含在 completion_tokens 内（safety_check=high 时出现） | S04 | VERIFIED |
| 仓库声明 | `usage_policy.reasoning` 仅允许 `included_in_output` / `additional_output`，无规则不得使用 route | `docs/BUDGET_BROKER.md:58-72`；`config/dsh/target-broker-policy.json:30-33` | 本地策略，保持 |

## 10. 429 / 5xx / timeout / retry 语义

| 场景 | 官方语义 | 来源 | 判定 | 与仓库/DSH 差异 |
|---|---|---|---|---|
| 429 | “Rate Limit Reached”：请求过快或超过并发/QPS 限制；请合理 pacing；模型速率限制见 Rate Limit 页 | S10 `.../quick_start/error_codes/` @17:47:09Z | VERIFIED | 仓库 guard 关闭 provider 内部重试（`maxProviderRetries=0`），但 DSH settings `max_retries=1`（settings.py:21）是另一层；真实 429 未观测 |
| 429 的 Retry-After / 数值 QPS | 官方限速页只给**并发上限**（flash 2500）；未公布每分钟 QPS 数值；错误码页提到“并发或 QPS 限制”但无数字；**未在采集页面找到 Retry-After 头文档** | S09；S10 | 数值 QPS/Retry-After：**UNVERIFIED** | 仓库无重试退避设计细节；BILLABLE_PATH_INVENTORY 已列 429=NOT_BILLABLE_HTTP_ERROR（本地判断） |
| 500 | Server Error；建议 brief wait 后 retry | S10 | VERIFIED | 仓库失败矩阵：5xx → BILLABLE_UNKNOWN/worst-case（保守合理） |
| 503 | Server Overloaded；建议 retry | S10 | VERIFIED | 同上 |
| 504 | Gateway Timeout（示例为 OCR/文档上传 API）；建议 retry later/更小文件 | S10 | VERIFIED | 聊天推理是否可能 504：UNVERIFIED |
| 408/413 | 文件上传太慢/过大（OCR/语音 API） | S10 | VERIFIED | 不在 M0 范围 |
| 402 | Insufficient Balance：余额耗尽 | S10 | VERIFIED | **供应商侧唯一可“硬停”的经济机制是余额不足**（见 §11/§12） |
| 401/400/422 | 认证失败/请求体格式错/参数错 | S10 | VERIFIED | — |
| 超时 | 预推理超过 10 分钟服务器断开连接；无“完整回答超时”数字；keep-alive 空行/SSE 注释 | S09 | VERIFIED（10 分钟预推理）；完整请求超时：UNVERIFIED | 仓库 settings `timeout_seconds=30`；真实网络超时行为未观测 |
| 重试/幂等 | 官方文档建议 5xx “retry after a brief wait”，但**未提供幂等 key/请求去重机制文档**；因此客户端重试可能重复计费（UNVERIFIED 具体计费行为） | S10；S04（无 idempotency 字段） | UNVERIFIED（重复计费行为） | 仓库“不自动重试 billable attempt”的方向正确；`settings.max_retries=1` 与 guard 0 retry 的关系需在 G4-H1 前澄清 |
| 取消 | 流式可中断（文档提到 aborted finish_reason）；但客户端断开后服务端是否继续计费/停止生成**未说明** | S04；S09 | UNVERIFIED | 仓库 watchdog 设计按 PENDING conservative 处理，方向正确 |

## 11. 供应商对外宣称的硬限额（A 级证据，`SUPPLIER_HARD`）

| # | 限额 | 官方数值/机制 | 是否供应商侧强制 | 来源 |
|---|---|---|---|---|
| SH-1 | 并发上限 | `deepseek-flash` 2500（account 级，与 key 无关）；超过返回 HTTP 429；可申请扩容（无额外费用） | **是**（429） | S09；S02 |
| SH-2 | 余额不足 | 余额耗尽 → HTTP 402 Insufficient Balance；扣费先赠金后充值金 | **是**（402 拒绝） | S10；S02（Deduction Rules） |
| SH-3 | 上下文窗口 | 1,048,576 tokens；超限请求报错（具体错误码页未逐条列出，UNVERIFIED 具体码） | 是（服务端约束） | S07；S02 |
| SH-4 | 单次输出上限 | `max_tokens` 1..393216；服务端拒绝越界（400/422 语义） | 是 | S04；S07 |
| SH-5 | 思考模式约束 | thinking 下 `tool_choice=required/指定函数` → 400；带 tools 未回传 reasoning_content → 400 | 是 | S04；S06 |
| SH-6 | 文件/图像限制 | 上传大小：图片 64MiB、文档 100MiB、文本/表格/电子书 32MiB；上传时长限制；图像每图 ≤1024 tokens；file 解析页数计费 | 是（API 校验） | S12；S13；S15 |
| SH-7 | 无月度花费/预算硬上限 | 官方文档**未发布**按账户的月度美元上限或预算 API；仅有余额扣减与并发上限；价格可随时调整（页面声明） | **否（未宣称）** | S02（"Product prices may vary and DeepSeek reserves the right to adjust them"）；S08（balance） |
| SH-8 | 速率 QPS/RPM | 未公开具体数值 | **否（未宣称）** | S09；S10 |
| SH-9 | Retry-After/幂等/去重 | 未文档化 | **否（未宣称）** | S10 |
| SH-10 | Key 撤销/过期 | Console 入口存在（S24），但撤销 API/立即生效语义未文档化 | **UNVERIFIED** | S24/S25 |

## 12. 本地策略限额（`LOCAL_POLICY`，工程目标，不是供应商侧上限）

| # | 限额 | 值 | 证据 | 说明 |
|---|---|---|---|---|
| LP-1 | 总预算 | soft **US$3** / hard **US$10** | `config/budgets.yaml:2-3`；`src/autoteacher_m0/security/live_controller.py:52-56`；`docs/Autonomous_Teacher_M0_v04.md:436-446` | **工程目标**；`M0_G4_A_AUTHORITY_CONTRACT.md:29,361` 明确 “$10 是工程硬顶，不是供应商侧上限”；无供应商侧强制机制 |
| LP-2 | 单次调用 | soft $0.10 / hard $0.20 | 同上 | 估算上界，超限不启动 |
| LP-3 | live 请求数 | ≤50 | 同上 | 需扩展时显式批准 |
| LP-4 | step / retry | ≤8 steps / ≤1 retry | `config/budgets.yaml:7-8`；`settings.py:20-21` | 与 DSH guard `maxProviderRetries=0` 叠加（provider 内部 retry 关闭） |
| LP-5 | token 保护 | 累计 ≤2.5M input / ≤600k output | `config/budgets.yaml:9-10`；`docs/Autonomous_Teacher_M0_v04.md:444` | 保守工程上限 |
| LP-6 | DSH guard | route/model `offline-test-only/fixture-v1`；`maxOutputTokens=1024`；`maxInputTokens=2500000`；`maxProviderRetries=0`；purposes `[conversation]` | `config/dsh/target-runtime.patch.yml:34-45` | **仅 synthetic fixture 可用**；量产真实 route 未接 |
| LP-7 | egress 原型 | host opencode.ai:443、POST、path `/inference/go/`、route/model `opencode-go/deepseek-v4.1-flash`、max_tokens≤1024、max_attempts≤4 | `src/autoteacher_m0/security/egress.py:31-34, 99-124`；`docs/BILLABLE_PATH_INVENTORY.md:24-31` | 描述符层拒绝，**非真实 proxy/OS 强制**；且目标是**第三方网关** |
| LP-8 | LiveGate | 恒 BLOCKED；`--live`/Markdown/环境变量不能解锁 | `src/autoteacher_m0/security/live_controller.py`；`docs/LIVE_CONTROLLER_SECURITY_DESIGN.md:134-145`；`docs/M0_G4F_HUMAN_HANDOFF.md:5-7` | 不因本文件改变 |

> **关键结论**：供应商侧强制只有 SH-1/SH-2/SH-3/SH-4/SH-5/SH-6（协议/额度/余额），**没有** “$3/$10/50 次” 对应的供应商侧强制。G4-H1/G5 前若需要真实花费硬约束，只能依赖：预充值低额度凭证（人类操作）+ 本地 guard/egress（需真实 OS 层强制与独立审计）+ 人工 Kill Switch；不得宣称“provider 账单不会超过 $10”。

## 13. 价格与生效日期（摘要；完整核算见 [PRICE_AND_USAGE_VERIFICATION.md](./PRICE_AND_USAGE_VERIFICATION.md)）

| 项目 | 官方值 | 来源 | 判定 |
|---|---|---|---|
| 计费口径 | 按模型输入+输出 token 总数计费；`expense = tokens × price`；从充值/赠金余额扣减（先赠金） | S02 | VERIFIED |
| `deepseek-flash` USD（1M tokens） | cache hit：off-peak $0.003 / peak $0.006；cache miss：off $0.15 / peak $0.30；output：off $0.60 / peak $1.20 | S02 | VERIFIED（2026-11-19 采集） |
| `deepseek-flash` CNY（1M tokens） | cache hit：off ¥0.02 / peak ¥0.04；cache miss：off ¥1 / peak ¥2；output：off ¥4 / peak ¥8 | S03 | VERIFIED（2026-11-19 采集） |
| peak 时段 | 周一至周五 01:00–04:00、06:00–10:00 UTC（不含中国法定节假日）；其余含周末 off-peak；off-peak = peak 的 50% | S02；S03（北京时间 09:00–12:00、14:00–18:00，等价 UTC） | VERIFIED |
| 当前价格生效/变更日期 | 峰谷机制 2026-08-16T16:00Z 生效；V4.1-Flash 价格 2026-09-10T04:00Z 生效；2026-10-17 明确“调用方式与价格不变”；页面在 2026-11-19 采集时仍为该价 | S19（2026-08-13/16、2026-09-10 条目）；S20（“New pricing takes effect at 04:00 UTC on Sept 10, 2026”）；S21（“API calling method and pricing remain unchanged”） | VERIFIED（生效日期文字）；页面未给“价格表版本号” → UNVERIFIED |
| 价格可变性 | 官方声明价格可能变化、保留调整权，建议按实际用量充值并定期查看 | S02 | VERIFIED |
| 其它计费项（M0 不涉及） | Search/Fetch 独立 API：$0.75/1,000 次成功请求；文件解析/OCR：$0.225/1,000 页；TTS/ASR 另列；服务端 web 工具计费状态存在官方页面间**时间线冲突**（见 D-08） | S02；S13；S14 | VERIFIED（价格条目存在）；web 工具体计费口径按最新页面=S14 "not billed" 并标注冲突 |
| 仓库 synthetic 价格 | $1 / $0.5 / $2 per 1M（mock） | `pricing.py:50-54`；`target-broker-policy.json:22-33` | **不是真实价格**；不得引用为报价 |

## 14. 额度查询与撤销路径

| 项目 | 官方路径/字段 | 来源 | 判定 |
|---|---|---|---|
| 余额查询 API | `GET /user/balance`（相对 base `https://api.deepseek.com`；文档示例未写完整 URL，按 base 推导）→ `is_available`、`balance_infos[{currency (CNY/USD), total_balance, granted_balance, topped_up_balance}]` | S08 | VERIFIED（schema）；完整 URL 拼接为 INFERRED（官方 base + path） |
| 充值/账单/用量导出 | 官方文档仅提及 “Top up page”/Console 链接（`platform.deepseek.com`）；**本次采集未见公开的用量/账单导出 API 文档** | S02（Top up 提法）；S24/S25 | **UNVERIFIED**（Console UI 细节/导出能力需登录核实） |
| Key 创建/撤销 | 官方 Quickstart 的 “apply for an API key” 链接到 `https://platform.deepseek.com/api_keys`；Console 页为 SPA 壳（2781B，登录+JS 才能看到内容） | S01；S24；A2_SOURCES §3 | 路径存在：VERIFIED；撤销流程/生效时间/权限：**UNVERIFIED** |
| 账户/项目额度上限设置 | 无官方公开文档 | S08；S24 | **UNVERIFIED**（不得假设存在） |
| 仓库对应机制 | 本地 broker 无 reset/refund endpoint；`dispatch_allowed` 只是记账许可，不是授权/Key 代理 | `docs/BUDGET_BROKER.md:105-115, 413-420` | 本地声明；与官方额度无关 |

## 15. 与仓库既有声明差异表（A2 核心交付之一）

| ID | 差异 | 仓库声明（证据） | 官方事实（来源） | 影响/处置建议 |
|---|---|---|---|---|
| D-01 | **“目标 provider” 双声明冲突**：官方主路由 vs 第三方网关 | `settings.py:5-6`、`config/models.example.yaml:2-7`、`ROUTE_DECISION.md:7-15` 声明官方 `deepseek-official/deepseek-flash`；`BILLABLE_PATH_INVENTORY.md:24-31`、`egress.py:31-34,99-124` 把 egress 固定为 `opencode.ai:443 /inference/go/ / opencode-go/deepseek-v4.1-flash` | 官方 API 是 `https://api.deepseek.com` + `deepseek-flash`；OpenCode Go 是第三方订阅网关（S01/S23/S28） | **HUMAN DECISION**：G4-H1/G5 前必须二选一（或明确双路由隔离），并重跑受影响 egress/授权/预算验收；不得把 OpenCode Go 的成功当官方渠道 PASS |
| D-02 | **DSH 目标 Profile 无官方 route** | `target-runtime.patch.yml:4-5` 禁用 `llm-deepseek`，仅 synthetic fixture；`DSH_TARGET_PROFILE.md:8-11` 明确 “无真实 Key/provider 可用路径” | 官方 route 存在（S01），但仓库 target profile 未启用 | 当前是**设计使然**（无 Key 阶段）；G4-H1 若选官方 route，需新增/审计 `llm-deepseek` 行 + Key Broker + egress 到 `api.deepseek.com:443` |
| D-03 | **usage 输入桶映射不兼容** | `broker_usage.py:3,69-98` 要求 input/cacheRead/cacheWrite 三桶齐全才算完整；`observation.py:36-46,258` 同 | 官方 Chat Completions：`prompt_tokens = prompt_cache_hit_tokens + prompt_cache_miss_tokens`；**无 cache write 字段**；Anthropic 格式才给 `cache_creation_input_tokens`（当前恒 0）（S04/S05/S16） | 现 schema 会把官方 OpenAI 格式观测判为 PARTIAL（worst-case），并可能把“缺失”当 0（禁止）；需实现 **official-route usage mapping v2**（miss→input、hit→cache_read、cache_write=None），并补测试；Anthropic 协议路径则可映射三桶 |
| D-04 | **真实 Key/价格/额度仍 UNVERIFIED 与文档声明一致** | `M0_G4F_HUMAN_HANDOFF.md:14-16`（H-01/H-02）；`BUDGET_BROKER.md:17` “prices are synthetic fixtures” | 本轮为公开文档研究，仍无真实 Key/账单（见 §0） | 保持 H-01/H-02 为 `PENDING_HUMAN_ACTION`；不得把本文档当真实计费证据 |
| D-05 | **$3/$10/50 的“硬上限”措辞风险** | `v04:436-446`、`live_controller.py:46-57`、`M0_G4_A_AUTHORITY_CONTRACT.md:29`（已注明工程硬顶） | 供应商无 $ 月度硬上限，只有并发 429 与余额 402（S09/S10/S02） | 文档/告警中统一称 “M0 工程目标”；若人类要求真实硬封顶，只能预充值低额度 Key + 外部强制 |
| D-06 | **synthetic 价格与官方价格量级差异** | fixture `1 / 0.5 / 2` USD/1M（pricing.py）；官方 flash `0.30 / 0.006 / 1.20` peak（S02） | 官方价目显著更低且分峰谷/缓存 | 不得用 fixture 价格做 G5 预算；改用官方快照（本任务 PRICE 文档）+ 当日复核 |
| D-07 | **OpenCode Go 价格/额度不能外推官方** | `OPENCODE_GO_ACCESS.md:32-37, 86-110, 303-325` 给出 Go $10/mo、$100 月度额度、5h 20%/weekly 50% 等 | 那是 OpenCode 第三方订阅条款（C 级 S28）；官方 DeepSeek 无此额度概念，只有余额/并发 | 若未来选 OpenCode Go，需以第三方文档+维护者账户确认；**不能**记成官方 API 限额或官方 PASS |
| D-08 | **官方页面间 web 工具计费时间线冲突** | 仓库 BILLABLE_PATH_INVENTORY B7 把 title/judge 等计入未知；无 web 工具声明 | S21（2026-10-17 新闻）：服务端 Search/Fetch “billing starts Oct 31, 2026 16:00 UTC”；S02/S14（2026-11-19 采集）：服务端 tool calls “不再计费”（自 2026-11-18 12:00 北京时间）；S22（2026-11-13）：扩展能力另计工具费 | M0 不使用 web 工具（target profile 工具禁用）；若未来启用，必须在执行当日重新确认计费状态并记录冲突 |
| D-09 | **V4-Pro 路由/价格冲突（官方页面内）** | 仓库不使用 v4-pro | S20（2026-09-10）：自 2026-09-14T04:00Z 起 v4-pro 请求按 V4.1-Flash 价格服务；S02/S07（2026-11-19）：仍列 `deepseek-v4-pro` 独立价格与 model id | 对官方主路由（flash）无影响；如未来使用 v4-pro，需重新核实（UNVERIFIED） |
| D-10 | **DSH 直连 provider 行/默认 endpoint 未在本轮 A 级来源中核实** | 仓库 `settings.py` 用 `deepseek-official` 标签；`DSH_TARGET_PROFILE.md` 用 `llm-deepseek`/`llm-pi-ai` 行 | B 级 DSH 官方文档：内置 DeepSeek 路由 id `llm-deepseek`，模型 effort off/low/high/max，`reasoningEffort` 可配（S27）；**未给 base URL 字符串** | 属 DSH 实现细节；G4-H1 前需 `--dump-config`/源码证据确认默认 endpoint 与 key env，不得假设 |
| D-11 | **Key 命名/前缀** | 仓库测试用假 `oc_sk_...`（OpenCode 格式） | 官方文档示例仅 `DEEPSEEK_API_KEY` env；未给官方 key 前缀 | 官方 route 不得使用 `oc_sk_` 假值作“真实格式”证据；Key 脱敏规则需覆盖官方 key 形态（UNVERIFIED 具体格式） |
| D-12 | **title/judge/compaction 计费假设** | `BILLABLE_PATH_INVENTORY.md:18-19` 把 compaction/judge/title 计入可能计费未知路径 | 官方 `title` 明确不额外计费（S11）；judge/compaction 无专属端点/费率，若通过 chat completion 则按 token 计费 | 若未来启用，以“普通 chat completion token 计费”建模；title 不额外计费；仍以真实观测为准 |

## 16. UNVERIFIED 清单（不得填猜测值）

1. **真实 wire 证据**：无 `/models`、`/chat/completions`、`/user/balance` 的真实响应；所有字段来自官方 schema/示例，非实测。
2. **真实计费/账单**：无真实 invoice、无 Console 账单/用量导出内容；`usage`↔`billed` 的对账未做。
3. **Key 撤销/轮换/前缀**：Console UI 细节与撤销生效时间；官方 key 格式。
4. **429 QPS 数值、Retry-After 头、重复计费语义**：官方未公开/未文档化。
5. **完整请求超时语义**：只核实“预推理 10 分钟断开”；推理中途超时/断连计费未说明。
6. **DSH 官方直连 provider 的默认 endpoint/协议/key env**：B 级文档未显式给出，需 dump-config/源码。
7. **DSH 目标 Profile 的真实 wire/工具注册表**：仓库已有 UNVERIFIED 声明（`DSH_TARGET_PROFILE.md:44`），本轮未新增证据。
8. **价格表版本/生效日精确对应**：只有变更日志日期与页面快照；无“价格表 version/hash”字段。
9. **web 工具/文件/OCR 等扩展计费的当前状态**：官方页面间时间线冲突（D-08），需执行当日复核。
10. **v4-pro 当前是否仍独立计费**：官方 news 与当前 price/model 页面冲突（D-09）。
11. **官方是否提供额度/账单 API**：本次 sitemap 70 个 URL 中无账单/用量端点；不能断言“不存在”，只能记为未公开发布/未核实。
12. **图片/文件 token 精确计费**：图像 ≤1024 tokens/图有官方文字，但精确公式需 calculator/实测；M0 不使用。

## 17. 对 A2 / A-05 的结论与人类决策项

**研究结论（建议状态）**：`PARTIAL — PASS_FOR_RESEARCH_SCOPE`。

- 已完成：官方 provider/model/endpoint/path/streaming/鉴权/请求/响应/usage/cache/reasoning/错误/限速/价格/生效日期/余额查询路径的**文档级核实**，每条有 URL+采集时间+VERIFIED/UNVERIFIED；供应商硬限额与本地策略限额已分表；与仓库既有声明的 12 项差异已记录。
- 未完成（A-05 不能记 PASS 的原因）：
  1. 目标路由（官方 vs OpenCode Go）未由维护者确认（D-01）；当前 DSH target profile 无官方 route（D-02）。
  2. 官方价格快照需维护者签收（H-02）且执行当日重采。
  3. usage 映射 v2（D-03）未实现/未测试；现有 schema 对官方 OpenAI 格式不完整。
  4. 无任何真实 wire/账单证据（本轮按任务禁止）。
- **本文件不改变**：`LiveGate=BLOCKED`、`G4-H=NOT_AUTHORIZED`、`G5=BLOCKED`、`E5_PRELIVE_FULL=BLOCKED`、`M0=DECISION_PENDING`。

**需要人类决策（建议提交维护者）**：

| ID | 决策 | 选项/建议 |
|---|---|---|
| HD-01 | 目标主路由最终选谁 | A) 官方 `deepseek-official/deepseek-flash`（与 v0.4/ROUTE_DECISION 一致，推荐作为主验收）；B) OpenCode Go 第三方（需重新评估 ToS/额度/隐私，且不能记官方 PASS）；C) 双路由隔离 |
| HD-02 | 是否接受本文件价格快照作为 G5 预算依据 | 需维护者确认采集日/币种（USD/CNY）/峰谷假设，并承诺执行当日重采；$3/$10/50 继续称“M0 工程目标” |
| HD-03 | usage 映射 v2 修复范围 | 在 G4-H1 前批准小补丁（不改冻结 Packet）：新增 official-route usage schema（hit/miss/cache_write 处理）并补测试；否则官方 route 不可结算 |
| HD-04 | Key/额度/撤销的人类流程 | 按 `M0_G4F_HUMAN_HANDOFF.md` H-01/H-03：仓库外 Key Broker、可撤销低额度 key、Console 用量核对；Agent 不参与 Key 获取/注入 |
| HD-05 | 是否要求 DSH 直连 endpoint/key env 的源码级证据 | 若选官方 route，**要求**：G4-H1 前提供 `--dump-config`/源码证据证明默认 endpoint 与 key env，不得假设 |
