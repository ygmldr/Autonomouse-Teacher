# PRICE_AND_USAGE_VERIFICATION — DeepSeek 官方 API（M0/A2，无 Key 研究）

- 任务：`task-3`（A2）；工作树 `worktrees/m0-g4h0-research`，分支 `work/m0-g4h0-research`，基线 `3e7afee`
- **性质**：公开官方价格页快照 + 假设性费用上界测算。**不是**真实账单、不是报价承诺、不是部署/花费授权；无 Key、无请求、无账单调阅。
- 采集时间：**2026-11-19T17:47:09Z（UTC）**（USD 价格 S02、CNY 价格 S03；来源定义见 [A2_SOURCES.md](./A2_SOURCES.md)）
- 目标模型：`deepseek-flash`（官方服务别名，实际版本 `DeepSeek-V4.1-Flash-1017`）——选择前提是“官方主路由”声明（见 [PROVIDER_CONTRACT_DRAFT.md](./PROVIDER_CONTRACT_DRAFT.md) §1/§15 D-01）；该路由**尚未获批**。
- 所有计算数字标注 `ASSUMPTION`（假设）或 `VERIFIED`（官方页面直接给出）。

## 1. 官方价格（VERIFIED，2026-11-19 采集）

### 1.1 美元价目（USD，1M tokens；S02）

| 模型 | 输入 cache hit（off-peak / peak） | 输入 cache miss（off-peak / peak） | 输出（off-peak / peak） | 并发上限 |
|---|---|---|---|---:|
| `deepseek-flash` | **$0.003 / $0.006** | **$0.15 / $0.30** | **$0.60 / $1.20** | 2500 |
| `deepseek-v4-pro` | $0.022 / $0.044 | $0.66 / $1.32 | $1.98 / $3.96 | 500 |

- 来源：S02 `https://api-docs.deepseek.com/quick_start/pricing/` @2026-11-19T17:47:09Z。
- 峰谷：**周一至周五 01:00–04:00、06:00–10:00 UTC 为 peak**（不含中国法定节假日）；其余时间含周末为 off-peak；off-peak = peak 的 50%。来源同上（S02 脚注；S03 用北京时间 09:00–12:00、14:00–18:00 表述，等价）。
- 计费口径：按模型输入+输出 token 数计费；`expense = tokens × price`；从赠金/充值余额扣减（先赠金）。来源 S02 “Deduction Rules”。
- 价格可变动、保留调整权；页面建议定期查看。来源 S02 末段。
- 其它计费项（M0 不涉及，列明防止误算）：Search API $0.75/1,000 成功请求、Fetch API $0.75/1,000；文件解析/OCR $0.225/1,000 页；TTS/ASR 见页面。来源 S02/S13。

### 1.2 人民币价目（CNY，1M tokens；S03）

| 模型 | 输入 cache hit（空闲/高峰） | 输入 cache miss（空闲/高峰） | 输出（空闲/高峰） |
|---|---|---|---|
| `deepseek-flash` | **¥0.02 / ¥0.04** | **¥1 / ¥2** | **¥4 / ¥8** |
| `deepseek-v4-pro` | ¥0.15 / ¥0.30 | ¥4.5 / ¥9.0 | ¥13.5 / ¥27.0 |

- 来源：S03 `https://api-docs.deepseek.com/zh-cn/quick_start/pricing/` @2026-11-19T17:47:09Z。
- **币种说明**：英文页显示 `$`、中文页显示 `元`；结算币种取决于账户（CNY/USD 见 `GET /user/balance` 的 `currency`，S08）。本任务不核实维护者账户实际币种 → **UNVERIFIED（账户币种）**。下文测算统一用 USD。

### 1.3 价格生效日期与变更记录（VERIFIED 文字）

| 日期/事件 | 官方文字 | 来源 |
|---|---|---|
| 2026-08-16T16:00Z | 采用 peak/off-peak 定价，峰价为谷价 2 倍 | S19（2026-08-13 Change Log） |
| 2026-09-10T04:00Z | V4.1-Flash 新价格生效；off-peak 为 peak 50% | S20（"New pricing takes effect at 04:00 UTC on Sept 10, 2026"）；S19 |
| 2026-10-17 | V4.1-Flash-1017 升级；“API calling method and pricing remain unchanged” | S21；S19 |
| 2026-11-19（采集日） | 当前页面仍为 §1.1/§1.2 数值；页面无“价格表版本号/生效至”字段 | S02；S03 |

- **UNVERIFIED**：价格表版本标识/精确生效日（只有变更日志与页面快照；无独立价格 API/版本字段）。
- 官方页面间冲突：web 工具计费时间线（2026-10-31 开始计费 vs 2026-11-18 起不再计费）见 [PROVIDER_CONTRACT_DRAFT.md](./PROVIDER_CONTRACT_DRAFT.md) §15 D-08；本测算不使用 web 工具，故不影响本文件。

## 2. 计费公式与 usage 字段（VERIFIED）

```
estimated_cost_usd =
  (prompt_cache_miss_tokens × miss_price
 + prompt_cache_hit_tokens  × hit_price
 + completion_tokens        × output_price) / 1_000_000
```

- `prompt_tokens = prompt_cache_hit_tokens + prompt_cache_miss_tokens`（S04 显式）。
- `completion_tokens` 含 `reasoning_tokens` 明细（`completion_tokens_details.reasoning_tokens`，S04）；**官方没有单列 reasoning 费率** → 保守计费时把 reasoning 计入 output（ASSUMPTION A4）。
- 官方 Chat Completions **无 `cost`/invoice 金额字段**（S04）；`cache_write` 无官方字段（S04/S05）。
- 真实账单/对账仍 UNVERIFIED（无 Console 访问、无真实请求）。

## 3. 假设集（全部为 ASSUMPTION，不是官方事实）

| ID | 假设 | 说明 |
|---|---|---|
| A1 | 模型 = `deepseek-flash`，按峰值单价计算 | 峰值是上界；off-peak 减半 |
| A2 | 输入 = 文本消息；token 数按“中文/英文估算”，不是 tokenizer 实测 | 官方 tokenizer 仅能估算，实际以 API usage 为准（S18） |
| A3 | 无 cache hit（最保守）；另给 cache 友好场景（6k/8k hit） | cache 命中率无保证（S05 best-effort） |
| A4 | reasoning tokens 计入 output（不单独加费） | 官方 usage 把 reasoning 放在 completion 明细；**INFERRED**，真实账单 UNVERIFIED |
| A5 | 无 web 工具、无 Files/OCR、无 retry/辅助调用、无额外费用 | M0 target profile 禁用这些路径（见 BILLABLE_PATH_INVENTORY） |
| A6 | 价格在测算期间不变（2026-11-19 快照）；不换算 CNY | 价格可变；执行日需重采 |
| A7 | 单次请求 token 假设：S1=8k miss in/4k out；S2=2k miss+6k hit in/4k out；S3=16k miss in/32k out（“Max thinking 极端”近似） | 用于 1/3/50 次示例；都与 1M 上下文/384K 上限不冲突 |
| A8 | 50 次请求均按相同假设重复，且总 token 不超本地 2.5M in/600k out 上限 | 本地累计 token 限制见 `config/budgets.yaml:9-10` |

## 4. 费用上界示例：1 / 3 / 50 次请求（peak USD；ASSUMPTION）

| 场景（每次请求） | 单次峰值 | 1 次 | 3 次 | 50 次 | 50 次 off-peak（≈50%） |
|---|---:|---:|---:|---:|---:|
| **S1** 8,000 miss 输入 + 4,000 输出 | $0.0072 | $0.0072 | $0.0216 | **$0.3600** | ≈$0.1800 |
| **S2** 6,000 hit + 2,000 miss 输入 + 4,000 输出 | $0.005436 | $0.005436 | $0.016308 | **$0.2718** | ≈$0.1359 |
| **S3** 16,000 miss 输入 + 32,000 输出（Max thinking 极端） | $0.0432 | $0.0432 | $0.1296 | **$2.1600** | ≈$1.0800 |

计算明细（S1 峰值）：`(8000×0.30 + 4000×1.20)/1e6 = 0.0024 + 0.0048 = $0.0072`；S2：`(2000×0.30 + 6000×0.006 + 4000×1.20)/1e6 = 0.0006+0.000036+0.0048 = $0.005436`；S3：`(16000×0.30 + 32000×1.20)/1e6 = 0.0048+0.0384 = $0.0432`。

### 4.1 本地 token 上限内的理论上界（ASSUMPTION）

若把 `config/budgets.yaml:9-10` 的**全量累计** token 上限（2.5M 输入 + 600k 输出）全部按 `deepseek-flash` 峰值、全部 cache miss 计算：

`2,500,000 × $0.30/1e6 + 600,000 × $1.20/1e6 = $0.75 + $0.72 = **$1.47**`（off-peak ≈ $0.735；若输入全部 cache hit 则远低）。

- 结论（ASSUMPTION A1/A4/A5）：在“只有官方 `deepseek-flash` 主调用、无扩展计费路径、价格不变”的前提下，**本地 token 上限对应的费用上界约 $1.47，低于 $3 soft**。这不代表实际花费，也不代表供应商侧有硬上限。
- 若使用 `deepseek-v4-pro` 价格（$1.32 miss / $3.96 output）：`2.5M×1.32/1e6 + 0.6M×3.96/1e6 = $3.30 + $2.376 = $5.676`（超过 $3 soft，仍低于 $10 hard）——但 **v4-pro 不在本任务目标内**（且官方页面存在 v4-pro 路由/价格冲突，见 D-09），仅为敏感性说明。
- 单次请求极端：1M 输入（miss）+ 384K 输出，峰值 = `$0.30 + $0.4608 = $0.7608`，**超过本地单次 hard-call $0.20** → 本地单次上限与模型物理上限不匹配，G4-H1 前必须靠预估计/拒绝策略保证，不得用“模型上限”当预算。

## 5. 与 `$3 soft / $10 hard / ≤50 requests` 的对照

| 项目 | 值/来源 | 解释 |
|---|---|---|
| `$3` soft / `$10` hard / `≤50 requests` | `config/budgets.yaml:2-6`；`src/autoteacher_m0/security/live_controller.py:46-57`；`docs/Autonomous_Teacher_M0_v04.md:436-446` | **M0 工程目标（本地策略）**，由本地代码/配置/人工签核约束 |
| 是否有供应商侧强制 | **没有** `$3/$10/$50` 对应的供应商机制 | 供应商侧仅有：并发 2500 → 429（S09）、余额不足 → 402（S10）、上下文/输出/文件等协议限制（S04/S07/S12） |
| provider 侧可用“硬停”机制 | 预充值低额度凭证 → 余额耗尽后 402；并发 429 | 但“低额度”是**人类操作**（v04:446 “以预充值低额度凭证作为第二道限额”）；Agent 不参与 Key 注入 |
| 单次 hard-call $0.20 | `config/budgets.yaml:5` | 50 × $0.20 = $10（hard），**刚好无余量**；任何未知辅助调用/重试/扩展计费都可能突破，需显式扣除或降为更小值（执行方案 §4 A3 建议 G5 首次 ≤3 请求） |
| 上界示例 vs soft | 50×S3 = $2.16 < $3；50×S1=$0.36 | 合理 token 假设下 soft 有余量；但这不是保证 |
| 上界示例 vs hard | 最坏本地 token 上限 $1.47 < $10 | 仅在 A1/A4/A5 假设下成立；**不能宣称“不会超过 $10”**（无供应商强制） |

**结论**：`$3/$10/50` 是 M0 工程目标与本地 fail-closed 预算策略，**不是**供应商对外宣称的硬限额；不得在报告、Runbook 或人类签核材料中称其为“绝对硬封顶”。真实花费安全依赖“预充值低额度 + 本地强制 + 人工 Kill Switch + 执行日复核价格”。

## 6. 无法验证项（本轮不能给出官方证据）

1. 维护者账户实际结算币种（CNY/USD）与实际扣费账单（无登录、无请求）。
2. 真实 tokenizer 计数与实际 usage（本文件全为假设输入）。
3. 真实 cache 命中率与 cache 计费（官方 best-effort，无真实响应）。
4. reasoning tokens 是否与 completion_tokens 双重/单独计费（无直接句；INFERRED）。
5. web 工具/文件/OCR/语音等扩展计费当前状态（官方页面时间线冲突，D-08）。
6. 429 QPS 数值、Retry-After、重复计费行为、断连后计费。
7. 价格表版本/精确生效日；未来价格变动。
8. 供应商是否提供额度/预算 API（本次 sitemap 未见；不能断言不存在）。
9. DSH 直连官方 provider 的实际请求 shape（OpenAI vs Anthropic 协议）对 usage 字段/映射的影响。
10. 任何真实费用是否低于/等于本文件上界（需真实账单 + Console 对账，属 H-02）。

## 7. 建议

1. 维护者按 `PROVIDER_CONTRACT_DRAFT.md` §17 HD-02 签收本价格快照（USD，2026-11-19），G5 执行日再重采并重算。
2. G4-H1 前完成 usage 映射 v2（D-03），否则官方 OpenAI 格式的 usage 会被本地 schema 判为 PARTIAL（worst-case），预算读数偏高且无法对账。
3. G5 首次真实授权建议远小于 50 次（执行方案 §4 A3 提议最多 3 次请求），并保留“未知/超时=worst-case”的 fail-closed 结算。
4. 本文件与 [A2_SOURCES.md](./A2_SOURCES.md) 一起归档；本文件不构成任何 G4-H/G5/Live 批准。
