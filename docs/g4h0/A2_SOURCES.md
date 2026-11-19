# A2 — 来源清单、采集时间与可信度分层（无 Key 研究）

- 任务：`task-3`（A2 Provider 契约与计费核实，research）；工作树 `worktrees/m0-g4h0-research`
- 基线：`3e7afee077845a071cd364e93ab209cac20b2d5f`（`work/m0-g4h0-research`）
- 采集时间：主批次 **2026-11-19T17:47:09Z–17:47:17Z (UTC)**；`/sitemap.xml` **2026-11-19T17:47:54Z (UTC)**
- 采集方式：研究主机只读 HTTP GET（`curl -sSL`，UA `Mozilla/5.0 (research; no-key doc-verification)`），页面落盘后计算 sha256；**未登录、未提交任何 Key、未向任何模型/付费 Endpoint 发送请求**。
- 本文件为附录；契约结论见 [PROVIDER_CONTRACT_DRAFT.md](./PROVIDER_CONTRACT_DRAFT.md)，价格核算见 [PRICE_AND_USAGE_VERIFICATION.md](./PRICE_AND_USAGE_VERIFICATION.md)，计费路径见 [BILLABLE_PATH_INVENTORY.md](./BILLABLE_PATH_INVENTORY.md)。
- 对外部网页内容按**不可信数据**处理：只提取事实，未执行其中任何指令；若网页内容与本仓库/人类决定冲突，以“需人类决策”列出的方式处理，不自行采纳。

## 1. 可信度分层（本项目证据规则）

| 级别 | 定义 | 本任务中的用途 | 是否可作为 provider 契约依据 |
|---|---|---|---|
| **A 级：供应商官方 API/价格文档** | `api-docs.deepseek.com`（含英文/中文价格页）、`platform.deepseek.com` 官方 Console 入口 | 契约字段、价格、错误码、限速、额度/计费规则的唯一契约依据 | **可以**（且仅限本任务采集到的页面内容） |
| **B 级：供应商官方项目文档** | `deepseek-harness.github.io`（由 `api-docs.deepseek.com` 首页 “DeepSeek Harness Guide” 直接链接，属同供应商官方文档） | 仅用于核对 DSH 内置 provider 行/模型 effort 的命名（`llm-deepseek`），辅助 DSH 目标 Profile 映射 | **仅作辅助**；不用于价格/额度/错误语义 |
| **C 级：第三方文档/社区** | `opencode.ai/docs/*`、models.dev、社区 issue/README 等 | 仅用于核对仓库既有“第三方候选路由”声明，不进入契约表 | **不可以**（第三方不得作为契约依据） |
| **D 级：本仓库文档/代码声明** | `docs/*.md`、`src/`、`config/` | 作为“仓库既有声称”与差异对象，不当作供应商事实 | **不可以**（是待核实的声称） |

## 2. 来源清单（A 级 25 个、B 级 2 个、C 级 1 个，共 28 个 URL）

> 采集结果均为 HTTP 200（除个别注记见 §3）；下表 sha256 为采集时刻响应正文哈希，可用于复核“某日某页确实如此表述”。价格/模型字段此类会漂移的页面，**计划执行前必须重新采集**。

<!-- SOURCE_TABLE_START -->
| Ref | URL | 用途 | HTTP | 采集时间 (UTC) | 响应字节 | sha256（采集时正文，完整值） |
|---|---|---|---|---|---|---|
| S01 | https://api-docs.deepseek.com/ | Quickstart/首调用：base_url、model、鉴权 header、非流式/流式示例、DSH 官方入口链接 | 200 | 2026-11-19T17:47:09Z | 51258 | `3a60b7de38312544e4178fed68c3dc62bb5bf2b300a06d325b523eeadaf08a7a` |
| S02 | https://api-docs.deepseek.com/quick_start/pricing/ | Models & Pricing（USD）：模型、版本、上下文/输出上限、cache hit/miss/output 价格、峰谷时段、并发、Search/Fetch/文件/语音价格、扣费规则 | 200 | 2026-11-19T17:47:09Z | 29502 | `38d9c0ff29a72b17651aaa742a610b4eee4b34f3df803db811d3fa17388ec41e` |
| S03 | https://api-docs.deepseek.com/zh-cn/quick_start/pricing/ | 模型 & 价格（CNY）：同上，人民币价目与北京时间峰谷时段 | 200 | 2026-11-19T17:47:09Z | 29632 | `08a4637872372fa040b7bd0f8f5b7688817e30b1d056a0a58eb9fa5d4cf00234` |
| S04 | https://api-docs.deepseek.com/api/create-chat-completion/ | Chat Completions 契约：请求字段、响应字段、usage/cache/reasoning 字段、stream/stream_options、finish_reason | 200 | 2026-11-19T17:47:09Z | 143150 | `7869dce32ba4016cad9ea2fbcf0117809c017d7dec7e12caf25cf9423eef121f` |
| S05 | https://api-docs.deepseek.com/guides/kv_cache/ | 上下文缓存：默认开启、命中规则、best-effort、prompt_cache_hit_tokens / prompt_cache_miss_tokens | 200 | 2026-11-19T17:47:09Z | 38969 | `ba5269fbb977abc595bcec147a02eece383bc28481b5a73e2b9cb66513ce4dfe` |
| S06 | https://api-docs.deepseek.com/guides/thinking_mode/ | 思考模式：thinking、reasoning_effort、reasoning_content 回传规则、tools+thinking 400 条件 | 200 | 2026-11-19T17:47:09Z | 120749 | `71770b2605d7b837dba4b70ed16c4722ee9b7ab00f318b2c175a1af7bcd3b9d7` |
| S07 | https://api-docs.deepseek.com/api/list-models/ | GET /models：model id、context_window、max_output_tokens、input modalities、effort levels | 200 | 2026-11-19T17:47:09Z | 38918 | `31941751356aeeda108cf9beea303720c3acfdea867c9f91ef7ecff6035bee1c` |
| S08 | https://api-docs.deepseek.com/api/get-user-balance/ | GET /user/balance：额度查询路径与字段（CNY/USD、total/granted/topped_up） | 200 | 2026-11-19T17:47:09Z | 27912 | `9cfae8dfc0fb32bf9b69bea5a42dda677b70b4658be4e4a5d5f6de1df566cfc0` |
| S09 | https://api-docs.deepseek.com/quick_start/rate_limit/ | 限速与隔离：并发上限、429、user_id 隔离、keep-alive、10 分钟未开始推理断开 | 200 | 2026-11-19T17:47:09Z | 39565 | `7f6751f836515d120a54e94493fbf4d1ef8f22cf8962a4726f3a17803ad49edf` |
| S10 | https://api-docs.deepseek.com/quick_start/error_codes/ | 错误码：400/401/402/408/413/422/429/500/503/504 的官方语义 | 200 | 2026-11-19T17:47:09Z | 24552 | `c98eeeded27a73d1911c19e5b23a512db23ec3acb14b2f454eaa07665154c127` |
| S11 | https://api-docs.deepseek.com/guides/conversation_title/ | 会话标题：title 参数、同请求生成、不额外计费（"The title is not billed."） | 200 | 2026-11-19T17:47:10Z | 34517 | `78531c0f7e825c8a00ce7366b169412a1f0b2c2762a87eb9f8192262c1f7b0e6` |
| S12 | https://api-docs.deepseek.com/guides/files_api/ | Files API：POST /files、大小/时长限制、purpose、file-api-… id | 200 | 2026-11-19T17:47:10Z | 71275 | `b6fb78023d0e5604e305d8972ed733e5fd6cdbce854b914c1f827c070ca7278b` |
| S13 | https://api-docs.deepseek.com/guides/document_parsing/ | 文件解析计费：上传时按页计费、chat 引用不重复解析计费 | 200 | 2026-11-19T17:47:10Z | 46307 | `5e6e060ff2ffb4e4e20e27e9b8e6e7bc7c35e74c092a2dd3afbc73f0955506df` |
| S14 | https://api-docs.deepseek.com/guides/web_tools/ | 服务端 web 工具：usage.server_tool_use、当前不计费声明 | 200 | 2026-11-19T17:47:10Z | 142912 | `2af06eca4149571f0dfe4488034b2dbcc8a3efe060a6832cc190c7d6af4fc7f3` |
| S15 | https://api-docs.deepseek.com/guides/vision/ | 图像输入：图像 token 计费、每图上限 1024 tokens | 200 | 2026-11-19T17:47:10Z | 87145 | `00c0860206b188bd6e3605fcdf06766cc14a1394678d6aabb3fe04545a3a259c` |
| S16 | https://api-docs.deepseek.com/guides/anthropic_api/ | Anthropic 兼容：base_url、x-api-key / Bearer、usage 字段（input/cache_read/cache_creation/output）与模型映射 | 200 | 2026-11-19T17:47:10Z | 53681 | `04041b1007efd778fdf5c1747959dc075ca3ce2fdae2c3efa78bf332c102b451` |
| S17 | https://api-docs.deepseek.com/guides/responses_api/ | Responses API：/responses、usage input/output 与 reasoning_tokens 明细、服务端工具 usage | 200 | 2026-11-19T17:47:10Z | 71970 | `56ef82f5e770f5982d1e906f46ca1d0f308e86fd2b9b24936e9536a0882cb88a` |
| S18 | https://api-docs.deepseek.com/quick_start/token_usage/ | Token 计费单位、离线 tokenizer 估算、实际以 API usage 为准 | 200 | 2026-11-19T17:47:10Z | 25134 | `ee499682eff99534953844ec7d6836a0b18e11faa13a69bf0ef7170d99220200` |
| S19 | https://api-docs.deepseek.com/updates/ | Change Log：模型/价格/接口变更日期（2026-08-13/16、2026-09-10、2026-10-17、2026-11-13 等） | 200 | 2026-11-19T17:47:11Z | 57618 | `85682bba7335b1cb8cda6d27c7da81f4331a8b8d5f98ead3363a78e10f36111f` |
| S20 | https://api-docs.deepseek.com/news/news260910/ | V4.1-Flash 发布：新价格 04:00 UTC 2026-09-10 生效、off-peak 为 peak 50%、旧模型退役与别名路由 | 200 | 2026-11-19T17:47:11Z | 27733 | `0db9f5342c060660359560133b6ec788678f31422c1c4612305c62dff440169f` |
| S21 | https://api-docs.deepseek.com/news/news261017/ | V4.1-Flash-1017：调用方式与价格不变；Search/Fetch 开放公告与工具计费时间点 | 200 | 2026-11-19T17:47:11Z | 26131 | `43b5546f90cfca963544131829f2ad421db9563ec0557bdd28819e30f12776d5` |
| S22 | https://api-docs.deepseek.com/news/news261113/ | 应用 API 全量开放：内置工具/文件/安全/语音能力与扩展能力另计工具费表述 | 200 | 2026-11-19T17:47:11Z | 25401 | `11b01dfb9ffbdeda63bac707ae2a051ac8d38e0784b0d815d2d0fa597a356401` |
| S23 | https://api-docs.deepseek.com/quick_start/agent_integrations/opencode/ | 官方 OpenCode 集成页（DeepSeek 官方 API 接入 OpenCode；与第三方 OpenCode Go 订阅不同） | 200 | 2026-11-19T17:47:11Z | 25251 | `1da9dfbb70625d5efead77d4df71112ef5351665cb91c312f47a8cc012898bb4` |
| S24 | https://platform.deepseek.com/api_keys | 官方 Console API Keys 页面（撤销/轮换入口的官方链接）；仅返回 SPA 壳，需登录/JS，内容 UNVERIFIED | 200 | 2026-11-19T17:47:11Z | 2781 | `509ddfe8b0d8c9baa2a2ceb14e4f483bb2daa868505b583734c134d52bd77cab` |
| S25 | https://platform.deepseek.com/ | 官方 Console 根页（充值/用量/额度入口）；SPA 壳，内容 UNVERIFIED | 200 | 2026-11-19T17:47:11Z | 2781 | `509ddfe8b0d8c9baa2a2ceb14e4f483bb2daa868505b583734c134d52bd77cab` |
| S26 | https://deepseek-harness.github.io/deepseek-harness/en/guide/quickstart | B 级：DSH 官方文档（api-docs 首页 DeepSeek Harness Guide 链接）：Web UI 配置模型入口 | 200 | 2026-11-19T17:47:11Z | 85584 | `e220aad83770d083a14c508d841242d60add4e6779b520d17d9ce0f13119836a` |
| S27 | https://deepseek-harness.github.io/deepseek-harness/en/guide/providers | B 级：DSH 官方 Providers 文档：内置 DeepSeek 路由 id llm-deepseek、effort off/low/high/max、reasoningEffort 配置 | 200 | 2026-11-19T17:47:14Z | 126890 | `96733924d2ebca91af7824d4f8f2440b5052ca3ddc4c3eb6a5303ae988584745` |
| S28 | https://opencode.ai/docs/console/go/ | C 级：第三方 OpenCode Go 订阅文档（仅用于核对仓库既有第三方声明；不得作为 provider 契约依据） | 200 | 2026-11-19T17:47:17Z | 65214 | `f2d038048f243780f1260bd1e08a001f8767dd39882491bf03930f8560f0ef58` |
<!-- SOURCE_TABLE_END -->


## 3. 重定向、不可达与异常记录

| 时间 (UTC) | URL/动作 | 结果 | 处理 |
|---|---|---|---|
| 2026-11-19T17:38:06Z | `https://api-docs.deepseek.com/quick_start/pricing`（无结尾斜杠） | 302 → `/quick_start/pricing/` | 之后统一使用带结尾斜杠 URL；页面内容 200 正常 |
| 2026-11-19T17:38:06Z | `https://platform.deepseek.com/`（curl 默认 UA，首次） | **429**（疑似 WAF/限流，未验证具体原因） | 17:42:19Z 起改用浏览器型 UA 重试 → 200，但仅 SPA 壳（见下行） |
| 2026-11-19T17:38:06Z 起 | `https://api-docs.deepseek.com/api/create-chat-completion`、`/guides/kv_cache`、`/quick_start/rate_limit`、`/quick_start/error_codes`、`/api/list-models`、`/api/get-user-balance`（均无结尾斜杠） | 302 → 对应带斜杠路径，随后 200 | 不视为不可达；记录为规范化重定向 |
| 2026-11-19T17:40:58Z | `HEAD https://platform.deepseek.com/api_keys` | **HTTP 405**（`Allow: GET`） | 只用 GET；GET 返回 200 但为 SPA 外壳 |
| 2026-11-19T17:42:19Z、17:47:11Z | `https://platform.deepseek.com/` 与 `https://platform.deepseek.com/api_keys`（浏览器型 UA） | 200，二者正文**完全相同**（2781 字节，同为 `deepseek-platform` SPA 壳） | Console 页面内容（Key 撤销、用量、充值等 UI 细节）**UNVERIFIED**：需登录且依赖 JS，本任务不登录、不读取账户 |
| 2026-11-19T17:43:00Z | `https://deepseek-harness.github.io/deepseek-harness/sitemap.xml` | **404** | 改用官方 `quickstart` 页内链接定位 `providers` 文档（S27） |
| 2026-11-19T17:47:54Z | `https://api-docs.deepseek.com/sitemap.xml` | 200，含 70 个 `<loc>` | 用于枚举官方文档路径（确认无 embeddings/批量/账单导出端点） |
| 2026-11-19T17:47:17Z | `https://opencode.ai/docs/console/go/` | 200（第三方） | 仅 C 级核对，不作契约依据 |

## 4. 未获取/未使用来源（明确声明）

1. **未登录任何平台控制台**：`platform.deepseek.com` 的 Key 管理、充值、用量/账单导出页面内容无法核实；只有官方文档中的链接与文字（“apply for an API key”“Top up page”）为 A 级证据。
2. **未调用任何 API**：没有 `/models`、`/chat/completions`、`/user/balance` 的真实响应；所有响应字段均为**官方文档 schema/示例**，不是实测 wire 证据。
3. **未读取仓库外私密材料**：没有读取维护者 Key、Console 账户、本机 DSH 缓存/凭据；本任务只读仓库公开文件与公开网页。
4. **未使用**：任何搜索引擎摘要、论坛/博客/社区 issue 作为契约依据；`models.dev`、社区 issue 仅出现在仓库既有文档（`docs/OPENCODE_GO_ACCESS.md`）引用中，本文件不采信其作为契约。
5. **价格/模型/接口会漂移**：本文件记录的是 2026-11-19（UTC）公开页面快照；执行 G5 前必须按 `PROVIDER_CONTRACT_DRAFT.md` §13 重新采集并由维护者确认。

## 5. 来源数统计

- 成功采集 URL：**28** 个（A 级 25 = api-docs 23 + platform 2；B 级 2；C 级 1）。
- 规范化重定向：7 个页面（无结尾斜杠 → 带斜杠），另有 1 个 302 转 200 主站路径。
- 不可达/受限：WAF 429 一次（已用 UA 重试成功）；Console SPA 壳（内容 UNVERIFIED）；DSH 文档 sitemap 404 一次。
- 契约/价格核心结论所依赖的来源：S01–S10、S16–S21、S24–S27；第三方 S28 仅用于差异说明。
