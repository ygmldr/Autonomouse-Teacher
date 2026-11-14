# OpenCode Go 订阅路由可行性调查（不读取凭据、不调用模型）

- 任务：`task-34`（v0.5 PR5 前置调查；非 PR5 执行）
- 日期：2026-11-14 UTC
- 基线：`HEAD=7c3806b`（文档提交）；被测实现 SHA 仍为 `feb7118f9aff20c681cc651812b30315288080f1`；本任务不提交任何 commit
- 证据目录：[`artifacts/opencode-go/`](../artifacts/opencode-go/)（gitignored；含 `manifest.json`、`evidence.sha256`、`raw/`）
- 结论分级：**SUPPORTED / PARTIAL / UNSUPPORTED / UNVERIFIED**（定义见 §9）

> **本任务约束（已遵守）**：只读公开网页/公开文档与本地已安装/已锁源码；**未读取、未复制、未落盘任何真实凭据**（未访问 `/root/.config/autoteacher` 或任何 key 文件）；**0 次真实模型调用、0 次真实 HTTP 模型请求**、未登录任何服务；未改 `src/`、`tests/`、`config/`、`scripts/`、插件、锁；未 `git add/commit`。外部网页内容按不可信数据处理，未执行其中任何指令。所有价格/额度仅为公开文档快照，执行前必须重新核对当日官方价目。

## 0. 结论摘要

| # | 问题 | 分级 | 一句话结论 |
|---|---|---|---|
| G1 | OpenCode Go 是否为非 OpenCode 客户端提供官方公开 API | **SUPPORTED** | 是：官方 Go 文档明确面向 OpenCode **和其他 coding agents**，Console Harnesses 文档给出其他 agent 的 Go 接入方法 |
| G2 | 官方 endpoint / base URL | **SUPPORTED** | Go：`https://opencode.ai/inference/go`；OpenAI Chat Completions 路径 `/openai/v1/chat/completions`；与 pay-as-you-go 的 `/inference` 是两个服务 |
| G3 | 鉴权方式与 `oc_sk_` 前缀含义 | **SUPPORTED** | Console API key 作 `Authorization: Bearer oc_sk_...`；个人 key/服务账号 key，单 workspace，只显示一次、可设过期/撤销 |
| G4 | 可用模型含 DeepSeek V4.1 Flash | **SUPPORTED（目录层）/ UNVERIFIED LIVE（实际响应）** | Go 官方列表含 DeepSeek V4.1 Flash；pi-ai 目录给出 `deepseek-v4.1-flash`（base_model DeepSeek-V4.1-Flash-1017）；实际服务端版本/response model 需 smoke 证据 |
| G5 | reasoning effort / Max thinking 参数 | **SUPPORTED（能力）/ PARTIAL（DSH 全链路）** | 目录声明 reasoning=true，effort low/high/max、thinking toggle；DSH SDK 有 `reasoning_effort` 且 pi-ai 会映射，但映射与实际 wire 字段需运行验证 |
| G6 | usage/成本是否可查询 | **SUPPORTED** | 每个响应带 `usage.cost`/`opencode.allowance`/`tokens`；Console Activity 有 usage 导出；**但 Console budgets 明确不计 Go in-plan usage** |
| G7 | 已锁 DSH Runtime 是否原生带 OpenCode Go provider | **SUPPORTED（静态证据）/ PARTIAL（插件字节）** | 锁定 0.2.2-rc.2 SEA 内嵌 pi-ai 1.3.0 的 `opencode-go` provider 资产（文件清单/字节大小与本地 pi-ai 1.3.0 一致）；内嵌 `dsh-llm-pi-ai` 插件字节大于本地 0.2.1-rc.2，需 `--dump-config` 确认 0.2.2-rc.2 配置面 |
| G8 | 可否配置自定义 base URL/API key/model/reasoning effort | **SUPPORTED** | `dsh-llm-pi-ai` 的 `providers.<route>.{apiKeyEnv,baseURL,models,modelOverrides,reasoning,...}` 官方配置目录有完整声明；Python SDK 有 `provider/model/reasoning_effort/env/patches` 字段 |
| G9 | DSH 是否满足 OpenCode Go 的 session 头要求 | **PARTIAL / UNVERIFIED** | pi-ai 正常路径会从 `options.sessionId` 生成 `x-opencode-session`；但 OpenCode 官方把 DSH 列为 **Known problematic**（部分 model path 缺失，discussion #5495） |
| G10 | 能否作为官方 DeepSeek 主路由/替代官方验收 | **UNSUPPORTED** | 第三方订阅网关，不是 DeepSeek 官方 API；`ROUTE_DECISION` 未批准，不能记官方 PASS 或 GO |
| G11 | ToS 是否允许本项目内部自动化使用 | **SUPPORTED（有严格条件）** | ToS：仅自身 internal use、非第三方代用；Go 检测滥用；不得转售/共享/批量注册；草稿/数据隐私按第三方模型条款 |
| G12 | rate limit / 硬额度 | **PARTIAL / UNVERIFIED** | 官方给 Go quota 窗口（5h 20%、weekly 50%、monthly 100% 的月度额度）与 429 行为；**每分钟 rate limit 未公开**；provider 侧并不存在“$10 使用硬上限” |
| G13 | 现在能否执行真实 smoke | **NOT DONE（按任务禁止）** | 本任务只给设计；执行需 PR1–PR4 完成 + 维护者外部批准 + 注入可撤销 key |

## 1. 公开事实（官方文档快照，2026-11-14）

### 1.1 订阅与定位
OpenCode Go 是 **订阅制**（Go **$10/月**、Go Plus **$40/月**、Go Teams **$20/成员/月**），
"Go works like any other provider in OpenCode. You subscribe to OpenCode Go and get your
API key."；Go 面向 **"OpenCode and other coding agents that produce similar types of
requests"**，并要求客户端发送稳定 session ID；流量会被滥用监控。
证据：<https://opencode.ai/docs/console/go/>（完整快照 `raw/opencode-docs-console-go.md`
的 "Go" / "Where can I use it?" 节）。

### 1.2 API endpoint、base URL、协议
- Pay-as-you-go 与 Go 是**不同 base URL**：`https://opencode.ai/inference` 与
  `https://opencode.ai/inference/go`（Console Harnesses 文档）。
- 同一网关支持 OpenAI Chat Completions、OpenAI Responses、Anthropic Messages、Gemini：
  例如 Go 的 `https://opencode.ai/inference/go/openai/v1/chat/completions`。
- 模型按 API family 服务；Open 模型（含 DeepSeek 系）走 Chat Completions。
- 免费模型仅 OpenCode 内部可用，其他客户端即使有 key 也收到 HTTP 403。
证据：<https://opencode.ai/docs/console/api/inference/>、<https://opencode.ai/docs/console/harnesses/#base-urls>；
快照见 `raw/web-pages-excerpts.md` §2/§3。

### 1.3 鉴权与 key 前缀
`Authorization: Bearer oc_sk_...`；key 分 personal key（成员身份/budget）与 service
account key（共享自动化）；每个 key 绑定一个 workspace，只在创建时完整展示一次，可设
过期（Never/1/7/30/custom）并可撤销。证据：<https://opencode.ai/docs/console/api/>（§1）。
本任务**没有**读取或生成任何 key。

### 1.4 模型与 DeepSeek V4.1 Flash
- 官方 Go 模型列表含 **DeepSeek V4.1 Flash**；要启用该模型需 workspace privacy 的
  Regions 设为 **Global**（默认受限于 Europe & United States）。
- OpenCode 维护的模型目录（models.dev provider=opencode）对
  `deepseek-v4.1-flash` 写明：`base_model = "deepseek/deepseek-v4.1-flash-1017"`（10 月
  17 日 build）、reasoning 支持、`thinking.type=enabled|disabled`、
  `reasoning_effort = low|high|max`、Chat Completions base URL
  `https://opencode.ai/inference/openai/v1`（pay-as-you-go 目录值）、
  cache implicit。
- locked 运行时的 pi-ai 1.3.0 目录值（`opencode-go` route）给出：
  `id=deepseek-v4.1-flash`，`baseUrl=https://opencode.ai/inference/go/v1`，
  `api=openai-completions`，`reasoning=true`，`thinkingLevelMap` 仅 low/high/max 有
  wire 值（`off/minimal/medium/xhigh` 为 null），`contextWindow=1000000`，
  `maxTokens=384000`，input text+image，cost `0.15/0.6`、cacheRead `0.003`，
  `compat.maxTokensField=max_tokens`、`thinkingFormat=deepseek`、
  `requiresReasoningContentOnAssistantMessages=true`。
  证据：`raw/models-dev-opencode-deepseek-v4.1-flash.toml`、
  `raw/pi-ai-1.3.0-data-opencode-go.json`（`jq '.["openai-completions"]["chat:deepseek-v4.1-flash"]'`）。
- **UNVERIFIED LIVE**：Go 网关实际返回的 response model/build、请求 ID、以及它与
  DeepSeek 官方 `deepseek-flash` 别名是否同一版本映射，均未验证（本任务禁止调用）。

### 1.5 reasoning effort / Max thinking
- 官方目录：`reasoning=true`，effort 仅 low/high/max；`thinking.type` 可显式开关。
- OpenCode 文档的 variant/settings 机制（`reasoningEffort`）见
  <https://opencode.ai/docs/models/>（§5 快照）：variant 名称来自模型目录，未知 variant
  会报错；不是所有模型都有 low/high/max。
- 结论：**模型/网关层支持 max thinking 的目录声明是 SUPPORTED**；但
  "DSH `reasoning_effort='max'` → 运行时 → pi-ai thinkingLevel → wire
  `reasoning_effort=max`/`thinking.type=enabled`" 的整链路只有静态代码路径，**未运行**，
  标 PARTIAL/UNVERIFIED。

### 1.6 usage / 成本查询与 Go quota
- 每个响应（含 streaming 的最终 usage 事件）包含 `usage.cost`、
  `opencode.billing_source`、`opencode.list_cost`、`opencode.allowance`、`opencode.tokens`；
  Go in-plan 的 `cost` 为 0，`allowance` 才是消耗的额度美元数。
- Console Activity 可按日/模型/人查看并导出 7/30/90 天 CSV。
- **关键限制**：官方 Budgets 文档明确 **"Go usage within the plan — No"**（不计入
  Console budgets）；只有 "Go extra usage paid from credits" 才计入。即 **Console budget
  不能限制 Go in-plan 使用量**。证据：`raw/web-pages-excerpts.md` §2/§4。
- Go quota：每个模型有月度额度（DeepSeek V4.1 Flash **$100/月**额度）、5 小时用量
  **20%**、每周 **50%**、每月 **100%**；达到后请求被拒绝（或 Extra Usage 时改用余额）；
  **Go/Go Plus 的 Extra Usage 默认关闭，Go Teams 默认开启**。证据：
  `raw/opencode-docs-console-go.md` 的 "Usage limits" / "Usage beyond limits" 节。
- 本任务无法从外部验证该维护者 workspace 的 Extra Usage 开关、地区设置或 key 状态；
  这些必须由维护者在 Console 内确认（UNVERIFIED）。

### 1.7 价格（官方 Go 文档快照）
| 项目 | Off-Peak | Peak |
|---|---:|---:|
| DeepSeek V4.1 Flash input / 1M tokens | $0.15 | $0.30 |
| DeepSeek V4.1 Flash output / 1M tokens | $0.60 | $1.20 |
| cached read / 1M tokens | $0.003 | $0.006 |

Peak 时段：周一至周五 **01:00–04:00 与 06:00–10:00 UTC**；其余（含周末）Off-Peak。
DeepSeek V4.1 Flash 的 Go 月度额度 **$100**（额度按上表计价消耗）。证据：完整快照
`raw/opencode-docs-console-go.md`（"Usage limits" 表格与 Peak hours 注释）。

### 1.8 客户端要求、允许使用与 ToS
- 客户端应：发送典型 coding agent 流量；**以自己的 user-agent 标识**；每个会话发送稳定
  的 `x-opencode-session`。流量会被滥用监控。
- 官方 "Validated clients" 不含 DSH；官方 **"Known problematic clients"** 明确列出
  **DeepSeek Harness**："Session information arrives on some model paths, but is missing
  on others. We recognize its native header; the remaining work is to send it across all
  adapters. Discussion #5495."
- ToS（2026-11-08 effective）：仅限自身 internal use、非代第三方使用；不得转售/提供
  服务给第三方、不得批量注册绕过限制、不得过度负载/逆向；第三方模型按其 retention
  条款。证据：`raw/web-pages-excerpts.md` §7。
- 隐私（官方 Go 文档）：DeepSeek V4.1 Flash 标注 "Not used / 0 days\*"（ZDR 协议按月续），
  但仍经过 OpenCode 第三方网关；DeepSeek V4.1 Flash 需要 workspace Regions=Global。
  本项目只应使用**公开假数据**，不得发送真实学生数据/密钥/私有评估内容。

## 2. 与已锁 DSH Runtime 的兼容性（本地源码 + 锁定二进制证据）

### 2.1 身份
- Python SDK：`deepseek_harness` **0.2.2rc2**（`artifacts/foundation/deps/deepseek_harness_sdk-0.2.2rc2.dist-info`）；
  Runtime CLI `0.2.2-rc.2`，binary SHA `1cc41d5a…`。
- 锁定 runtime 的 SEA 资产清单（从 `artifacts/sdk-fixture/binary-strings.txt` 中提取，只含
  清单路径/大小，文件内容被压缩未解出）列出内嵌：
  `@earendil-works/pi-ai/dist/providers/opencode-go.js`（1,194B）、
  `opencode-headers.js`（939B）、`opencode-go.models.js`（631B）、
  `data/opencode-go.json`（17,403B）、`@deepseek-ai/dsh-llm-pi-ai/lib/index.js`
  （137,008B）等；见 `raw/locked-runtime-sea-opencode-assets.txt`。
- 本地 DSH npm 0.2.1-rc.2 的 pi-ai **1.3.0** 中，上述 opencode 相关文件**字节大小逐一相同**
  （`opencode-go.js` 1,194、`opencode-headers.js` 939、`opencode-go.models.js` 631、
  `data/opencode-go.json` 17,403、`package.json` 2,720），因此锁定 SEA 内嵌的
  pi-ai provider 资产与本地 pi-ai 1.3.0 高度一致（**字节大小一致，非完整哈希验证**）。
- 但 `dsh-llm-pi-ai` 插件：锁定 SEA 内嵌 **137,008B**，本地 0.2.1-rc.2 为 125,589B，
  说明插件本体跨版本有变化；不得把本地 0.2.1-rc.2 的配置细节当成 0.2.2-rc.2 的字节证据。

### 2.2 pi-ai 的 `opencode-go` provider（本地 1.3.0 源码，随锁定资产同尺寸）
`raw/pi-ai-1.3.0-opencode-go.js` 第 10–21 行：
- provider `id: "opencode-go"`，name `"OpenCode Go"`；
- 鉴权：`envApiKeyAuth(..., ["OPENCODE_API_KEY"])`（**env 变量名是 `OPENCODE_API_KEY`**）；
- 模型：`OPENCODE_GO_MODELS`（来自 `data/opencode-go.json`）；
- 四个 API 全部包 `withOpenCodeSessionHeader(...)`。
`raw/pi-ai-1.3.0-opencode-headers.js` 第 1–21 行：只当 `options.sessionId` 存在且
headers 里没有 `x-opencode-session` 时，才加入
`x-opencode-session: <sessionId>`；已有则不覆盖（正常对话可带，缺 sessionId 的手工请求不带）。

### 2.3 DSH 的 provider 配置面（官方 config catalog + 本地插件源码）
官方生成文档 `@deepseek-ai/dsh-llm-pi-ai` 的 Config 声明（`raw/dsh-config-catalog-llm-pi-ai-excerpt.md`）：
```ts
export interface Config { providers: Record<string, PiAiProviderProfile> }
export interface PiAiProviderProfile {
  apiKeyEnv?: string        // credential reference（env 名），secret 不进配置文件
  displayName?: string
  api?: string              // 省略则用目录协议
  baseURL?: string          // 省略则用目录 endpoint
  models?: PiAiModelProfile[]      // 省略则用安装目录；显式列表会替换目录
  modelOverrides?: Record<string, PiAiModelOverride>
  compat?: PiAiCompatProfile
  reasoning?: ModelThinkingLevel   // pi-ai 的 off/minimal/low/medium/high/xhigh/max
  thinkingBudgets?: ...
  headers?: Record<string,string>
  retryPolicy?: RetryPolicyConfig
  ...
}
```
本地 dsh-llm-pi-ai 0.2.1-rc.2 `lib/index.js`：`opencode-go` 的内置 env 映射为
`["OPENCODE_API_KEY"]`（L2733–2734）；适配器把 `options.sessionId` 传给 pi-ai（L1987）、
并传入 `headers: requestHeaders(profile.headers)`（L1989），因此 pi-ai 的 session-header
wrapper 能拿到 sessionId。
DSH 官方 Providers 指南也明确"Add a third-party provider … installed catalog supplies the
endpoint, protocol, and model list"，以及 `cordis.patch.yml` 的 profile 覆盖方式。

### 2.4 Python SDK 配置面（锁定 wheel 0.2.2rc2 源码）
`artifacts/foundation/deps/deepseek_harness/api.py`：
- `DeepSeekHarnessConfig`（L14–L41）：`provider`、`model`、`reasoning_effort`、`max_tokens`、
  `profile`、`patches`、`dsh_home`、`env`、`base_url`、`api_key`、超时等。
- env 注入（L124–L127）：`base_url` → **`DEEPSEEK_BASE_URL`**，
  `api_key` → **`DEEPSEEK_API_KEY`**（注意：这两个是 DeepSeek 专用名字，不是
  `OPENCODE_API_KEY`）。
- initialize payload（L155–L170）：`{cwd, provider, model, reasoningEffort?, maxTokens?}`。
证据：`raw/locked-sdk-0.2.2rc2-source-excerpts.md`。

**结论**：选择 `provider="opencode-go"` + `model="deepseek-v4.1-flash"` 的路由在
SDK/运行时接口上成立；鉴权应通过 env `OPENCODE_API_KEY`（或把该 route 的
`apiKeyEnv` 配成 `DEEPSEEK_API_KEY` 以复用 SDK 的 `api_key` 字段）。**不要**直接传
`base_url=`/`api_key=` 并期望它们作用于 OpenCode Go——它们只映射到 `DEEPSEEK_*`。
另：不要设置 route `baseURL`，让 pi-ai 目录的 Go endpoint 生效（pi-ai 1.3.0 目录已给出
`https://opencode.ai/inference/go/v1`）。

### 2.5 session header 兼容性（关键 PARTIAL）
- 正常路径：DSH agent loop 产生 sessionId → `llm-pi-ai` 传给 pi-ai → `withOpenCodeSessionHeader`
  注入 `x-opencode-session`（本地源码证据见 §2.2/§2.3）。所以**普通对话理论上可带**。
- 风险路径：缺 sessionId 的手工组装请求不会带该头；OpenCode 官方已把 DSH 列入 Known
  problematic（"missing on some model paths"）。社区插件 README 指出的典型触发是
  DSH 内置 auto-review 的 `classifyRisk()`（不带 sessionId），会 400
  `MissingSessionID`（社区证据见 `raw/community-evidence-excerpts.md` §B；非官方）。
- 因此 **G9 = PARTIAL/UNVERIFIED**：不能仅凭本地静态代码断言"OpenCode Go 全链路可用"；
  PR5 smoke 必须关闭 auto-review/实验性附属请求，观察是否出现 MissingSessionID，并把
  "header 是否已发送/哪些路径缺失"记录为 UNVERIFIED 或 FAIL，而不是猜 PASS。

## 3. 接入已锁 DSH Runtime 所需配置（占位符，不含真实值）

### 3.1 Profile patch（`cordis.patch.yml` 路径由维护者 profile 决定）
```yaml
# PLACEHOLDER ONLY — never commit real keys. Merge into a reviewed profile patch.
# If the profile does not already mount llm-pi-ai, add the insert block;
# if it does, put `config:` on the existing row instead.
- id: llm-deepseek          # strongly recommended: disable official route for this
  disabled: true            # OpenCode-Go-only experiment; no automatic fallback.

- insert:
    - id: llm-pi-ai
      name: '@deepseek-ai/dsh-llm-pi-ai'
      config:
        providers:
          opencode-go:
            apiKeyEnv: OPENCODE_API_KEY   # credential ref only; secret injected at launch
            # baseURL: intentionally OMITTED. The pi-ai catalog supplies
            #   https://opencode.ai/inference/go/v1 (openai-completions).
            # models: omitted => installed catalog serves deepseek-v4.1-flash;
            #   to pin only this model, use:
            # models:
            #   - id: deepseek-v4.1-flash
            reasoning: max                    # requires catalog thinkingLevelMap max="max"
            retryPolicy:
              mode: normal
              maxRetries: 0                   # no hidden retries/billable duplicates in smoke
```
- 若 profile 已有 `llm-pi-ai` 行，使用 `- id: llm-pi-ai` + `config:` 的覆盖形式，不要重复
  insert 同名行（route 冲突会导致插件加载失败；见 dsh-llm-pi-ai README "registering a
  route another adapter already owns fails plugin loading"）。
- 若用官方 Providers 指南的 settings 轴（`~/.dsh/settings.yaml` 的 `llm-pi-ai:` 段），
  内容同样只需 `providers.opencode-go.apiKeyEnv`（社区做法见 raw §A，**非官方**）；
  SDK 场景推荐显式 patch 文件，便于 SHA 冻结与审计。

### 3.2 Python SDK 调用（占位符）
```python
from deepseek_harness import DeepSeekHarness

# OPENCODE_API_KEY is injected by the trusted controller at process launch.
# It MUST NOT appear in this repo, in the patch YAML, or in logs.
with DeepSeekHarness(
    provider="opencode-go",
    model="deepseek-v4.1-flash",
    reasoning_effort="max",
    max_tokens=256,                       # hard per-request cap for smoke
    profile="<approved-profile-name>",
    patches=("<absolute path to reviewed patch.yml>",),
    env={"OPENCODE_API_KEY": "<injected-by-launcher>"},
    dsh_home="<isolated dsh home>",
    cwd="<isolated workspace>",
    initialize_timeout_seconds=30,
    request_timeout_seconds=60,
    shutdown_timeout_seconds=2,
) as harness:
    result = harness.run("...fixed smoke prompt...", session_id="<non-secret fixed id>")
```
- **不要**在本路由使用 `base_url=`/`api_key=` kwarg（见 §2.4 的 DEEPSEEK_* 映射）。
- 记录 `route_id=opencode-go`、`provider=opencode-go`、`model=deepseek-v4.1-flash`；
  不写 `deepseek-official`。
- 启动前用 `dsh --profile <p> --dump-config`（或等价只读检查）断言：
  merged config 含 `opencode-go` 行、`llm-deepseek` 已禁用/无真实 key、无其他真实 route；
  若 profile 依赖的 `dsh-llm-pi-ai` 版本字段与 §2.3 不同，停止并先修订配置。

## 4. 最小“凭据连通性 smoke”设计（本任务不执行）

**前置（任何一项不满足 → BLOCKED，不得执行）**：PR1–PR4 完成；维护者独立审查并批准冻结
profile/实现 SHA；提供**可撤销、低额度**的 OpenCode Go key；Console 确认 Go 订阅有效、
DeepSeek V4.1 Flash 已启用（Regions=Global）、**Extra Usage 关闭**、无自动充值；项目侧
预算守卫/调用计数就绪；外部 egress 仅允许 `opencode.ai:443`（不是 `--network none`，需
专门受控容器/代理证据）；宿主不执行项目 Python/pytest；日志脱敏方案就绪。

**设计**：2 次最小调用，单次 `max_tokens<=32/128`，固定 prompt（如回显
`OPENCODE_GO_OK` + 一次严格 JSON），无工具、无文件、无真实学生数据、固定 synthetic
session id、`maxRetries=0`、总预算 < US$0.1。

1. `LIVE-GO-01`：SDK run → 断言 HTTP/协议成功（finish 正常）、final_response 含固定标记、
   events 中 request/header 的 provider=`opencode-go`/model=`deepseek-v4.1-flash`、
   usage 存在；若 `usage.opencode.billing_source=go`（或 cost=0 + allowance>0）则通过；
   记录 request id、usage tokens、allowance、UTC/argv/exit、日志 hash。
2. `LIVE-GO-02`（可选）：严格 JSON prompt → 项目既有 strict Pydantic 校验；
   再记录 usage/allowance。

**失败/停止条件（任一触发即停，不重试）**：HTTP 401/403；400
`MissingSessionID`/`INVALID_REQUEST`；429 quota/budget；usage 缺失或 billing_source 为
`balance`；费用/额度超出预期上界；出现未知 egress/网络；日志出现 key 原文；无法有界关闭
进程/容器；profile 出现真实 DeepSeek route。失败只记录原始错误码/response id，不把
synthetic 错误注入写成真实 PASS。

**证据与边界**：记录 argv/UTC/exit/日志 hash、request id、usage（脱敏）、容器 absence；
key 注入只经 launcher env，不落盘；事后由维护者撤销 key/核对 Console usage。smoke 成功
只证明**该路由在该配置下可连通并产生可追踪 usage**；不证明官方主路由、不满足 E1–E5 Live，
也不解除 LiveGate。若 smoke 出现 MissingSessionID，应把 session-header 缺口标为
PARTIAL/FAIL 并停止后续 PR5 计划（除非维护者批准上游修复/受控 workaround 并重新审计）。

## 5. 成本与额度估算（公开价目快照；执行前重核）

**计费口径**：Go in-plan 的现金支出为订阅费（$10/月等）；请求消耗的是 **额度美元**
（DeepSeek V4.1 Flash 月度 $100、5h 20%、weekly 50%），响应 `usage.cost=0`、
`opencode.allowance` 增加。**Console budget 不能限制 Go in-plan 用量（官方明确），
provider 侧也不存在“$10 使用硬上限”**；若要严格 US$10 现金上限，只能依赖：订阅价固定 +
Extra Usage OFF + 项目侧调用计数/额度告警/人工批准。

估算公式（按目录 token 价，peak/off-peak 取较贵）：
`cost = (input_tokens×$0.30 + output_tokens×$1.20 + cache_read×$0.006) / 1e6`
（reasoning tokens 计入 output；cache write 在本文档模型为 0；价格见 §1.7。）

| 场景 | 估算 |
|---|---|
| smoke 2 次（每次 ≤8k input、≤512 output、≤1k reasoning） | ≤ 2×(0.0024+0.0018)= **≤$0.0084**；即使 8k reasoning 也 ≤$0.025 |
| 50 次 Live 上限 × 3k input / 1k output | ≈ **$0.105** |
| 50 × 8k input / 4k output | ≈ **$0.36** |
| 50 × 16k input / 8k output | ≈ **$0.72** |
| 50 × 16k input / 32k output（Max thinking 极端假设） | ≈ **$2.16** |
以上均为**额度美元**估算，不是现金账单；现金仍是订阅费，除非 Extra Usage 开启后走余额。
**Uncertainty**：reasoning token 数量、内部 retry/compaction/辅助调用（可能多次计费）、
实际 peak/off-peak 时段、未来价目变化均未知；smoke 的硬上限靠 `max_tokens`/调用次数/
项目预算守卫，不靠 provider 账单。

## 6. 风险、区别与决策影响

1. **第三方路由，不是官方主渠道**：OpenCode Go 是第三方订阅网关；即使可用，也不能记录为
   DeepSeek 官方 `deepseek-official / deepseek-flash` 的 PASS，不能替代 E1–E5 强制 Live
   验收。`ROUTE_DECISION` 中 OpenCode Go 仍为 optional/UNVERIFIED；任何主渠道变更必须
   维护者事前批准并完整重跑受影响验收（v0.5 §PR5 退路同样要求）。
2. **human approval / 账户与 key**：key 属维护者个人/工作区，`oc_sk_` 单 workspace、只
   显示一次、可过期/撤销；必须由维护者外部注入，Agent 不得读取/创建/复制 key，也不得
   接受 ToS/开通订阅。ToS 限自身 internal use、不得转售/代第三方使用；不得批量注册。
3. **数据隐私**：即使文档标 DeepSeek V4.1 Flash 0 天保留，内容仍经 OpenCode 网关/第三方
   处理；Regions/训练设置、ZDR 协议有效性需维护者确认；本项目只允许公开假数据，
   禁止真实学生数据、私有评估、密钥、个人 home 材料。
4. **session/header 与客户端标识**：OpenCode 官方列 DSH 为 known problematic；缺
   `x-opencode-session` 的请求会 400。正常 agent loop 理论可带，但 auto-review/附属请求
   风险未验证；社区 workaround（fetch wrapper）**未审计不得采用**。user-agent 应以客户端
   身份发送（DSH attribution header 是否被 Go 接受为"自有 UA"未验证）。
5. **额度/账单不可控点**：Console budgets 不计 Go in-plan usage；Go Teams 默认 Extra
   Usage 开；内部 retry/辅助调用可能产生未知次数请求；peak 价格更高；rate limit 未公开；
   model list/price 可随时变化。项目侧必须自带调用计数/上限/拒绝，不得声称 provider 硬
   预算证明。
6. **模型身份**：目录 base_model 为 DeepSeek-V4.1-Flash-1017，不等于官方 API 的
   `deepseek-flash` 映射；请求/响应中的实际 model/build 需 smoke 记录；不能写"与官方
   Flash 完全同一版本/PASS"。
7. **实现边界**：本任务未改任何实现；guard 中间件（task22/phase5）只是离线 logical-stream
   bookkeeping，未接入真实 provider，LiveGate 仍未打开；任何 PR5 前必须满足 v0.5 前置。
8. **UNVERIFIED 清单**：实际 endpoint/连接性、实际 model id/response 版本、reasoning max
   的 wire 行为、usage/allowance 字段真实返回、session-header 全路径、rate limit、Extra
   Usage/地区设置、key 状态、价格有效期。未验证的项不得写成 PASS。

## 7. 建议的下一步（不越权）

1. 本调查结果可作为 v0.5 PR5 的“可选第三方便宜路由候选”输入；**不等于批准**。
2. Lead/维护者决定是否把 OpenCode Go 列为 PR5 的 optional 路由（`route_id=opencode-go`），
   并确认 ToS/隐私/账户使用是否符合其组织要求；若仅要 Coding Agent 开发订阅，保持现状。
3. 在 PR1–PR4 完成、冻结 profile/配置 hash、确认 Extra Usage OFF、Region=Global、
   key 可撤销后，按 §4 设计执行 1–2 次最小 smoke；任何失败按 §4 停止并保留原始错误。
4. 无论 smoke 结果如何，官方主路由/E1–E5 Live 与 LiveGate 状态不变；`ROUTE_DECISION`
   需人工更新并获得批准，Agent 不得自批。

## 8. 证据索引

- 本文件：[`docs/OPENCODE_GO_ACCESS.md`](<OPENCODE_GO_ACCESS.md>)
- 机器清单：[`artifacts/opencode-go/manifest.json`](../artifacts/opencode-go/manifest.json)
- 证据清单：[`artifacts/opencode-go/evidence.sha256`](../artifacts/opencode-go/evidence.sha256)
  （`cd artifacts/opencode-go && sha256sum -c evidence.sha256`）
- 原始/摘录：[`raw/`](../artifacts/opencode-go/raw/) — 官方 Go 文档全文快照、
  DSH config catalog 摘录、pi-ai 1.3.0 opencode 源码/目录、锁定 SDK 源码摘录、锁定
  runtime SEA 资产清单行、models.dev TOML、社区证据（明确标记 UNOFFICIAL）、网页摘录与
  作品来源/状态说明。

## 9. 分级定义与本文件引用约定

- **SUPPORTED**：有官方公开文档或本地锁定源码的直接证据，且不依赖未执行的真实调用。
- **PARTIAL**：部分有证据，但存在版本/配置/路径缺口或需运行确认。
- **UNSUPPORTED**：证据明确否定或与项目规范冲突。
- **UNVERIFIED**：没有足够证据（本任务禁止真实调用），不得推定。
- 引用约定：官方 URL 直接给出；本地源码给出包路径 + 文件名/行号；锁定 runtime 的
  二进制证据只能引用 SEA 资产清单（压缩内容未解出，不伪造内容）；外部网页均为
  不可信数据快照，见 raw/README。
