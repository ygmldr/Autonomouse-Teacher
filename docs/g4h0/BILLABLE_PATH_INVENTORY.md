# BILLABLE_PATH_INVENTORY — M0/A2 计费路径清单（无 Key 研究）

- 任务：`task-3`（A2）；工作树 `worktrees/m0-g4h0-research`，分支 `work/m0-g4h0-research`，基线 `3e7afee`
- 性质：**本地声明侧 + 官方契约侧**的计费路径盘点；**不是**账单证明、不是硬预算证明、不是部署授权。
- 本轮证据边界：**M0 当前无真实 Key、0 真实模型调用、0 真实 HTTP/计费请求、无任何真实 usage/账单证据**。依据：
  - `docs/LIVE_CONTROLLER_SECURITY_DESIGN.md:12-13`：不读取真实凭据、不调用模型、不发起真实 HTTP；不使用真实 Key；
  - `docs/E5_PRELIVE_NO_KEY_REPORT.md:15-24, 79`：无真实 Key、0 模型/0 真实 HTTP、仅假 Key 与 mock；
  - `docs/M0_G4F_HUMAN_HANDOFF.md:14-16`：H-01 真实 Key/额度、H-02 价格/usage 对账均 `PENDING_HUMAN_ACTION`；`:5-7` 的门状态 `LiveGate=BLOCKED / G4-H=NOT_AUTHORIZED / G5=BLOCKED / E5_PRELIVE_FULL=BLOCKED / M0=DECISION_PENDING`；
  - `docs/M0_G4_00_BASELINE.md:6, 22`：0 真实 Key/0 模型/0 外部 HTTP/TCP/0 真实计费请求；
  - 本任务新增：仅公开文档只读采集（[A2_SOURCES.md](./A2_SOURCES.md)），0 请求到付费 Endpoint。
- 官方是否“可能计费”列：依据 [PROVIDER_CONTRACT_DRAFT.md](./PROVIDER_CONTRACT_DRAFT.md) 的 A 级来源；`VERIFIED`＝官方文档写明；`UNVERIFIED`＝无官方证据。
- 结论分类：**存在（真实）** / **存在（仅本地/合成）** / **不在范围（禁用/无路径）** / **UNVERIFIED**。

## 1. 计费路径总表

| # | 路径 | 官方是否可计费（A 级来源） | 仓库 / DSH 目标 Profile 证据 | 当前 M0 状态 | 结论 |
|---|---|---|---|---|---|
| P1 | **主对话 provider attempt**（`llm/stream` → chat completion） | **是**：按 input+output token×价格计费（S02）；无 `cost` 字段，靠余额扣减 | 官方主路由声明：`src/autoteacher_m0/settings.py:5-6, 14-21`；`config/models.example.yaml:2-7`；`docs/ROUTE_DECISION.md:7-15`；但 DSH target profile **禁用** `llm-deepseek`（`config/dsh/target-runtime.patch.yml:4-5`），只启用 synthetic fixture（`:34-45, 54-55`）；guard policy route=`offline-test-only/fixture-v1`（`config/dsh/target-broker-policy.json:18-20`） | **无真实路径**：target profile 只跑 synthetic fixture（`docs/DSH_TARGET_PROFILE.md:8-11, 30-31`；`real_model_calls=0,http_calls=0`） | **存在（真实）但当前禁用**；本地合成替代 |
| P2 | **provider 内部自动重试** | 官方 5xx 建议 brief wait 后 retry，但**无幂等/去重机制文档** → 重试可能重复计费（UNVERIFIED 行为） | guard 拒绝 `maxProviderRetries>0`（`config/dsh/target-runtime.patch.yml:44`；`docs/BILLABLE_PATH_INVENTORY.md:14`）；DSH settings `max_retries=1`（`settings.py:21`）与 ≤1 retry 预算（`config/budgets.yaml:8`）；egress `MAX_ATTEMPTS_PER_STREAM=4`（`egress.py:34`） | 无真实重试：synthetic/mock `retry_attempted=False`（`docs/BILLABLE_PATH_INVENTORY.md:54-64`） | **存在（真实风险）但被本地配置限制**；真实 adapter 是否完全遵守 UNVERIFIED（F3 残留） |
| P3 | **工具轮次（第二个 attempt）** | **是**：tool call 回灌是新的 chat completion 请求（S04 支持 tools/tool_calls；每次请求计费） | 每次 logical stream 独立 reserve（`docs/BUDGET_BROKER.md:96-104`；`docs/BILLABLE_PATH_INVENTORY.md:15`）；工具白名单仅 `skill_lookup`（`docs/LIVE_CONTROLLER_SECURITY_DESIGN.md:79-81`）；DSH target profile 禁用 tool/terminal/subprocess 等（`config/dsh/target-runtime.patch.yml:15-32`） | 无真实 tool 轮；synthetic fixture 工具路径已测（未联测真实路由） | **存在（真实）但当前禁用**；registry 完整性 UNVERIFIED（E5-P04/B03） |
| P4 | **cache hit / cached tokens** | **是**：cache hit 有独立单价（S02）；不额外 dispatch | fixture 假设 implicit cache（`docs/BILLABLE_PATH_INVENTORY.md:16`）；broker usage 有 cacheRead（`docs/PROVIDER_USAGE_MAPPING.md:12-31`）；reserve 按 max(input, cached) 不假设折扣（`src/autoteacher_m0/accounting/pricing.py:44-47`） | 无真实 cache 观测：官方字段已核实（S04/S05），但无真实响应 | **存在（真实）**；真实命中字段/比率 UNVERIFIED；官方 Chat 无 cache write 字段（D-03） |
| P5 | **上下文压缩/摘要（compaction）** | 无专属端点/费率；若通过 chat completion 实现，则按普通 token 计费（**INFERRED**，官方无 compaction 文档） | broker 有 purpose=`compaction`（`src/autoteacher_m0/accounting/broker.py:25, 159-170`；`docs/BUDGET_BROKER.md:96-104`）；guard policy 仅 `purposes: [conversation]`（`config/dsh/target-runtime.patch.yml:45`）；DSH target profile `compaction-basic` disabled（`:11-12`）；`docs/BILLABLE_PATH_INVENTORY.md:18` | 无真实 compaction：target profile 禁用；仓库 B6 列“可能计费、未触发” | **存在（仅架构/记账词汇）**；真实触发/次数/计费 UNVERIFIED |
| P6 | **标题生成** | 官方 `title: {"enabled": true}` 与回答同请求生成，**不额外请求、不额外计费**（S11） | 仓库 B7 把 “Judge/session-title” 计为未知路径（`docs/BILLABLE_PATH_INVENTORY.md:19`）；DSH 文档/仓库未见 title 调用证据；target profile 无 title 行 | 无真实标题调用 | **若用官方 title 字段：不另外计费（VERIFIED）**；**若由 DSH 单独发请求生成标题：按普通 chat completion 计费（UNVERIFIED 是否发生）** |
| P7 | **Judge / 评测调用** | 无专属端点/费率；若走 chat completion 则按 token 计费（INFERRED；官方无 judge 文档） | broker purpose=`judge`（`broker.py:25`；`docs/BUDGET_BROKER.md:96-104`）；`docs/BILLABLE_PATH_INVENTORY.md:18-19`；B 线评测要求 Judge 独立（`docs/Autonomous_Teacher_M0_v04.md:335`） | M0 无真实 Judge 调用；离线评测不含真实 provider（README/ADR 声明） | **存在（仅本地/未来）**；真实调用次数/成本 UNVERIFIED |
| P8 | **文件/上传（Files API、附件、图像）** | **是**：`POST /files` 上传时按页计费（解析成功才计费；chat 引用不重复解析计费）；图像 token 计入请求 token（S12/S13/S15） | egress 显式 deny `FILES_NOT_PERMITTED`/`IMAGES_NOT_PERMITTED`（`docs/BILLABLE_PATH_INVENTORY.md:17, 28`；`egress.py:107-109, 128`）；DSH target profile `image-offload` disabled（`config/dsh/target-runtime.patch.yml:13-14`）；无 upload 插件 | 无真实调用；原型描述符级 deny | **不在范围**（当前无路径、被 deny）；真实 Files 二次 POST/计费行为 UNVERIFIED |
| P9 | **Embedding** | 本次采集的官方文档 sitemap（70 URL）**没有 embeddings 端点**；官方文档未发布 embedding API → **无法证实存在**（不能断言不存在） | 仓库全量 grep `embedding` 无命中（`src/`、`tests/`、`config/`、`docs/*.md` 无调用路径）；target profile 无 embedding 行 | 无调用、无路径 | **不在范围**；官方是否提供 embedding：**UNVERIFIED（未发布/未核实）** |
| P10 | **自动回退（fallback）** | 官方未声明“跨模型/跨渠道自动 fallback”；旧模型名→新模型的服务端映射是**别名路由**，不是错误回退（S02/S19/S20） | `config/models.example.yaml:14` `automatic_fallback: false`；`docs/ROUTE_DECISION.md:15` “禁止自动切换渠道/模型”；`settings.py:30-31` 禁止 route/model 变更；egress 单 route/model（`egress.py:121-123`） | 无回退路径；Live 全 BLOCKED | **不在范围（本地禁用）**；DSH 内部是否隐式 fallback：**UNVERIFIED** |
| P11 | **插件/辅助 DSH 流量（auto-review、session-log、plugin inventory 等）** | 若产生 provider 请求 → 按普通 token 计费（INFERRED）；官方无 DSH 内部请求文档 | DSH target profile 禁用 `llm-deepseek`、`session-log-deepseek`、plugin-inventory、compaction、image-offload、工具/终端等（`config/dsh/target-runtime.patch.yml:4-32`）；verifier 拒绝 unexpected provider rows（`docs/DSH_TARGET_PROFILE.md:34`）；`docs/OPENCODE_GO_ACCESS.md:197-206` 引社区证据（C 级）称 DSH auto-review `classifyRisk()` 可能缺 session header → 第三方问题，**非官方** | 无真实插件流量；target profile 无真实 provider | **当前不在范围（禁用）**；真实 Live profile 是否存在隐藏辅助请求：**UNVERIFIED**（必须用 per-dispatch guard + 外部 egress 兜底） |
| P12 | **重连/stream resume/超时/断连 → 重复 POST** | 官方无幂等 key/去重文档；断连后是否继续计费未说明（UNVERIFIED） | `docs/BILLABLE_PATH_INVENTORY.md:20`（B8）；egress `max_attempts≤4`（`egress.py:34`）；watchdog PENDING conservative（`docs/LIVE_CONTROLLER_SECURITY_DESIGN.md:121-132`） | 无真实断连观测；mock 归 BILLABLE_UNKNOWN | **存在（真实风险）**；真实重复计费 UNVERIFIED |
| P13 | **独立 Search/Fetch/OCR/ASR/TTS API** | **是**：Search/Fetch $0.75/1k 成功请求；文件解析/OCR $0.225/1k 页；TTS/ASR 另列（S02/S13/S14） | 仓库无这些调用路径；DSH target profile 工具禁用；M0 不使用 | 无调用、无路径 | **不在范围** |
| P14 | **超时/无 usage/部分 usage 的结算** | 官方 5xx/timeout 不提供“是否已计费”保证（UNVERIFIED）；本地按 worst-case | `docs/BILLABLE_PATH_INVENTORY.md:21`（B9）；broker settle 缺失维度用最坏上界（`docs/BUDGET_BROKER.md:131-143`）；`docs/PROVIDER_USAGE_MAPPING.md:33-46` | mock 场景已测（worst-case held>0）；真实 settlement 联动未验证 | **存在（保守记账）**；真实计费真相 UNVERIFIED |

## 2. DSH 目标 Profile 的“实际计费面”（`config/dsh/target-runtime.patch.yml`）

| 组件/行 | 配置 | 影响 |
|---|---|---|
| `llm-deepseek`（官方直连） | `disabled: true`（:4-5） | **官方 provider 路径不存在**；不会产生官方 API 计费 |
| `session-log-deepseek` | `enabled: false`（:6-8） | 不产生 session-log 上传/请求 |
| `plugin-package-inventory-deepseek` | `disabled: true`（:9-10） | 不做插件清单网络请求 |
| `compaction-basic` / `image-offload` | `disabled: true`（:11-14） | 无 compaction/image 辅助调用 |
| `tool-*` / `terminal-*` / `pty` / `subprocess` / `jobs` | `disabled: true`（:15-32） | 无工具/终端导致的额外模型轮次 |
| `runtime-budget-guard` | route=`offline-test-only`、model=`fixture-v1`、broker policy sha、`maxOutputTokens=1024`、`maxInputTokens=2500000`、`maxProviderRetries=0`、`purposes=[conversation]`（:34-53） | 只对 synthetic fixture 预留/结算；**不是**真实 provider 计费控制 |
| `offline-test-only-provider` / `offline-public-skill` | synthetic fixture / 本地 skill（:54-57） | 无真实模型调用 |
| `llm-pi-ai`（OpenCode Go overlay，STATIC-ONLY） | `apiKeyEnv: OPENCODE_API_KEY` 占位、无 baseURL、`reasoning:max`、`maxRetries:0`（`config/dsh/target-runtime-opencode-go.patch.yml:6-16`） | 静态配置证明；**无 Key/网络/真实调用**；且目标是**第三方**，不是官方主路由 |

结论：当前 DSH target profile 的**真实计费面为 0**（0 Key、0 provider、synthetic only）；真实调用只可能在 G4-H1/H2/G5 人类授权后通过新 profile/受信部署出现。

## 3. 与仓库既有 `BILLABLE_PATH_INVENTORY.md` 的关系与差异

| 项 | 仓库既有（PR4a） | 本文件（A2） | 差异/说明 |
|---|---|---|---|
| B1 主调用 | mock transport `ok_usage`=SETTLED；真实 wire 未观测 | 官方字段/价格已核实（文档层）；真实 wire 仍未观测 | 本文件新增官方侧；仓库的“未观测”结论保持不变 |
| B2 provider retry | guard 拒绝 >0；真实 adapter 是否遵守 UNVERIFIED | 官方无幂等/去重文档 → 重试重复计费风险 UNVERIFIED | 一致，补充官方证据 |
| B4 cache | cacheRead 未以真实 response 验证 | 官方字段 `prompt_cache_hit_tokens`/`prompt_cache_miss_tokens` 已核实；**无 cache write 字段** | 新增 D-03 映射冲突 |
| B5 Files | 原型 deny；真实行为 UNVERIFIED | 官方 `/files` 与按页计费、chat 引用不重复解析计费已核实 | 新增官方计费证据；仍不在 M0 范围 |
| B6 compaction | purposes 固定 conversation；真实触发未知 | 官方无 compaction 端点；target profile 禁用 | 一致 |
| B7 Judge/title | 计入未知；不假设 0 | **title 同请求不额外计费（官方）**；judge 若走 chat 则按 token 计费 | 修正 title 计费假设（D-12） |
| B8 重连/resume | BILLABLE_UNKNOWN + worst-case | 官方无幂等文档；断连计费 UNVERIFIED | 一致 |
| B9 超时/无 usage | worst-case held | 官方 5xx 不提供计费保证；本地最坏上界合理 | 一致 |
| B10 未批准 route | 描述符 deny | 官方契约 + DSH profile 禁用；LiveGate BLOCKED | 一致 |

## 4. 明确 UNVERIFIED / 不在范围（不得外推）

1. **真实 wire 层**：真实 HTTP attempt、provider 内部 retry、cache 标记、Files stale-ID 二次 POST、断连计费均未观测（仓库 F3/F9 残留；本轮无请求）。
2. **真实 usage/账单**：无真实 usage/发票/Console 对账；官方 Chat usage 无 `cost` 字段。
3. **真实辅助调用次数**：DSH Live profile 是否产生 title/judge/compaction/auto-review 等额外请求 UNVERIFIED；M0 target profile 已禁用可识别路径，但不能据此证明“任何 Live profile 都没有隐藏调用”。
4. **官方 Files/图像/OCR 计费完整性**：按页/按 token 规则有官方文字，但未真实调用。
5. **Embedding**：官方 sitemap 未见端点；不能断言不存在，只能标 UNVERIFIED/不在当前范围。
6. **供应商侧硬预算**：不存在 $3/$10/50 的供应商机制；详见 `PROVIDER_CONTRACT_DRAFT.md` §11/§12 与 `PRICE_AND_USAGE_VERIFICATION.md` §5。
7. **本清单不是账单/硬上限证明**：任何“不会超过 $10”“零额外调用”的结论都不成立；真实安全依赖预充值低额度 + 受控 egress/Key Broker + watchdog + 人工 Kill Switch + 独立审计。

## 5. 复验方式（无 Key）

- 契约/价格来源：按 [A2_SOURCES.md](./A2_SOURCES.md) §2 的 URL + 采集时间重新抓取；不要依赖本文件的二手转述。
- 仓库侧声明：`git grep -n` 对应 file:line（本文件已给行号；基线 `3e7afee`）。
- 当前门状态：`docs/M0_G4F_HUMAN_HANDOFF.md:5-7`、`docs/M0_G4_00_BASELINE.md:6-7`。
- 本文件不含任何真实 Key、账单、请求或 provider 响应；不得作为 G4-H/G5/Live 的通过证据。
