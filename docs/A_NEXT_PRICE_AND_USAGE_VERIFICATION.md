# A-NEXT — 价格与 Usage 核验稿（2026-11-19 研究快照；未获批、未真实调用）

- **文档 ID**：`A-NEXT-PRICE-AND-USAGE-VERIFICATION-v1`
- **性质**：对旧 A2 价格研究（`work/m0-g4h0:docs/g4h0/PRICE_AND_USAGE_VERIFICATION.md`，
  sha256 `40a7b7dda452e9fda6dfb60b91be43e1d32c4c9894dbd8b6c08b32edb9564fec`）的 **A-NEXT/G4-R 适配**。
  **不是**真实账单、不是报价承诺、不是部署/花费授权；无 Key、无请求、无账单调阅。
- **外部事实有效期**：**全部为 2026-11-19T17:47:09Z 公开价格页研究快照，未获批、未真实调用**；
  A6 本轮不重采，正式审批/G5 前必须重新核实（D-17/D-22；`config/budgets.yaml:11` `live_pricing_snapshot: REQUIRED_UNVERIFIED`）。
- **工作树/分支**：`/root/Autonomous Teacher/worktrees/a-next-handoff` / `docs/a-next-handoff`；
  canonical 基线 `work/g4r=fd1d3a6`；frozen src impl `d33e0aa`；base `3e7afee`。
- **来源**：旧 A2 `A2_SOURCES.md`（28 URL；sha256 `77a5ead5…f018`）；USD 价目 S02
  `https://api-docs.deepseek.com/quick_start/pricing/` @2026-11-19；CNY S03 同域 `/zh-cn/...`。
- 计算数字标注 `VERIFIED-DOC`（官方页面文字）/`ASSUMPTION`（假设）/`LOCAL_POLICY`（仓库工程目标）。

## 0. 摘要（G4-R 视角）

1. **G4-R 当前没有真实计费路径**：`config/dsh/target-runtime.patch.yml:4-5` 禁用官方 `llm-deepseek`，只跑
   synthetic `offline-test-only/fixture-v1`；synthetic price 是 `1/0.5/2 USD per 1M`（`pricing.py:50-54`、
   `target-broker-policy.json:22-33`，`mock=True`），**不是官方价格**。
2. 官方 flash 价格（2026-11-19 快照，未获批）：cache hit **$0.003/$0.006**（off/peak）、cache miss
   **$0.15/$0.30**、output **$0.60/$1.20** 每 1M tokens；off-peak=peak 50%；UTC 峰时周一至周五
   01:00–04:00、06:00–10:00。
3. 本地 `$3 soft / $10 hard / ≤50 requests` 是 **M0 工程目标**（`config/budgets.yaml:2-6`、
   `live_controller.py:53-57`），**不是供应商硬封顶**；供应商侧只有并发 429、余额 402、上下文/输出等协议约束。
4. 费用上界示例（ASSUMPTION）：50×S3（16k in/32k out）峰值 ≈ **$2.16**；本地累计 token 上限内理论上界
   ≈ **$1.47**（仅 flash、无扩展路径）；但仍不能承诺“不会超过 $10”。
5. **状态**：`PARTIAL / PASS_FOR_RESEARCH_SCOPE`；真实价格/usage/账单 `UNVERIFIED`；G5 `BLOCKED`。

## 1. 官方价格（2026-11-19 研究快照；未获批/未真实调用；需重核）

### 1.1 USD（1M tokens；S02 @2026-11-19）

| 模型 | 输入 cache hit（off/peak） | 输入 cache miss（off/peak） | 输出（off/peak） | 并发上限 |
|---|---|---|---|---:|
| `deepseek-flash` | **$0.003 / $0.006** | **$0.15 / $0.30** | **$0.60 / $1.20** | 2500 |
| `deepseek-v4-pro` | $0.022 / $0.044 | $0.66 / $1.32 | $1.98 / $3.96 | 500 |

- 来源：`https://api-docs.deepseek.com/quick_start/pricing/`，采集 **2026-11-19T17:47:09Z**；`VERIFIED-DOC`（历史快照）。
- 峰谷：周一至周五 01:00–04:00、06:00–10:00 UTC 为 peak（不含中国法定节假日）；其余含周末 off-peak；off=peak 50%。
- 计费口径：按输入+输出 token 数计费，`expense = tokens × price`；赠金/充值余额扣减（先赠金）；价格可变、保留调整权。
- 其它计费项（M0 不涉及）：Search/Fetch $0.75/1,000 成功请求；文件解析/OCR $0.225/1,000 页；TTS/ASR 见页面。
- **状态：2026-11-19 研究快照、未获批、未真实调用；正式审批前必须重核（D-17/D-22）。**

### 1.2 CNY（1M tokens；S03 @2026-11-19，未获批/未真实调用）

| 模型 | 输入 cache hit（空闲/高峰） | 输入 cache miss（空闲/高峰） | 输出（空闲/高峰） |
|---|---|---|---|
| `deepseek-flash` | **¥0.02 / ¥0.04** | **¥1 / ¥2** | **¥4 / ¥8** |
| `deepseek-v4-pro` | ¥0.15 / ¥0.30 | ¥4.5 / ¥9.0 | ¥13.5 / ¥27.0 |

- 币种取决于账户（`GET /user/balance` 的 `currency`，2026-11-19 schema 快照）；本任务不核实维护者账户币种 → `UNVERIFIED`。下文统一 USD。

### 1.3 价格生效/变更日期（VERIFIED-DOC，快照）

| 日期/事件 | 官方文字/含义（2026-11-19 快照） |
|---|---|
| 2026-08-16T16:00Z | 采用 peak/off-peak 定价，峰价为谷价 2 倍（旧 A2 S19 Change Log） |
| 2026-09-10T04:00Z | V4.1-Flash 新价格生效；off-peak 为 peak 50%（S20） |
| 2026-10-17 | V4.1-Flash-1017 升级；“调用方式与价格不变”（S21） |
| 2026-11-19（采集日） | 页面仍为 §1.1/§1.2 数值；页面无价格表版本号/生效至字段 |

- **UNVERIFIED**：价格表版本/精确生效日（仅变更日志+页面快照）；web 工具/文件/OCR 等扩展计费当前状态（官方页面时间线冲突，旧 A2 D-08）。
- **状态：全部为 2026-11-19 研究快照、未获批、未真实调用；正式审批前重核。**

## 2. 计费公式与 usage 字段（VERIFIED-DOC + 代码事实）

```
estimated_cost_usd =
  (prompt_cache_miss_tokens × miss_price
 + prompt_cache_hit_tokens  × hit_price
 + completion_tokens        × output_price) / 1_000_000
```

- `prompt_tokens = prompt_cache_hit_tokens + prompt_cache_miss_tokens`（S04）。
- `completion_tokens` 含 `completion_tokens_details.reasoning_tokens` 明细（S04）；官方**无单独 reasoning 费率** → 保守按 output 含 reasoning（ASSUMPTION）。
- 官方 Chat Completions **无 `cost`/invoice 字段**、**无 cache-write 字段**；本地三桶映射不兼容（见 `A_NEXT_PROVIDER_CONTRACT_DRAFT.md` §4 / BLK-15）。
- 真实账单/usage 对账 `UNVERIFIED`（无 Console 访问、无真实请求）。
- **状态：字段/公式为 2026-11-19 文档快照、未获批、未真实调用。**

## 3. 假设集（全部 ASSUMPTION，不是官方事实）

| ID | 假设 |
|---|---|
| A1 | 模型=`deepseek-flash`，按峰值 USD 单价；off-peak 减半 |
| A2 | 输入为文本；token 数按估算，非 tokenizer 实测（官方 tokenizer 仅估算，实际以 API usage 为准） |
| A3 | 无 cache hit（保守）；另给 cache 友好场景（6k/8k hit） |
| A4 | reasoning tokens 计入 output（不单独加费）；官方无直接句 → INFERRED，真实账单 UNVERIFIED |
| A5 | 无 web 工具/文件/OCR/retry/辅助调用/额外费用（G4-R target profile 禁用这些路径） |
| A6 | 价格在测算期间不变（2026-11-19 快照）；不换算 CNY |
| A7 | 单次请求：S1=8k miss in/4k out；S2=2k miss+6k hit in/4k out；S3=16k miss in/32k out |
| A8 | 50 次重复同假设，且总 token 不超本地 2.5M in/600k out 上限 |

## 4. 费用上界示例：1 / 3 / 50 次请求（peak USD；ASSUMPTION）

| 场景（每次） | 单次峰值 | 1 次 | 3 次 | 50 次 | 50 次 off-peak（≈50%） |
|---|---:|---:|---:|---:|---:|
| **S1** 8,000 miss 输入 + 4,000 输出 | $0.0072 | $0.0072 | $0.0216 | **$0.3600** | ≈$0.1800 |
| **S2** 6,000 hit + 2,000 miss 输入 + 4,000 输出 | $0.005436 | $0.005436 | $0.016308 | **$0.2718** | ≈$0.1359 |
| **S3** 16,000 miss 输入 + 32,000 输出（Max thinking 极端） | $0.0432 | $0.0432 | $0.1296 | **$2.1600** | ≈$1.0800 |

明细：S1 `(8000×0.30+4000×1.20)/1e6=0.0072`；S2 `(2000×0.30+6000×0.006+4000×1.20)/1e6=0.005436`；
S3 `(16000×0.30+32000×1.20)/1e6=0.0432`。全部 **ASSUMPTION + 2026-11-19 快照 + 未获批/未真实调用**。

### 4.1 本地 token 上限内理论上界（ASSUMPTION）

- 全量上限 2.5M 输入 + 600k 输出，全部 flash 峰值、全 cache miss：
  `2.5M×0.30/1e6 + 0.6M×1.20/1e6 = $0.75+$0.72 = **$1.47**`（off-peak≈$0.735；全 cache hit 更低）。
- 本地单次极端：1M 输入（miss）+384K 输出峰值 `$0.30+$0.4608=$0.7608`，**超本地单次 hard-call $0.20** → 必须靠预估计/拒绝策略，不得用模型上限当预算。
- 若改用 v4-pro 价格：2.5M×1.32/1e6+0.6M×3.96/1e6=$3.30+$2.376=**$5.676**（超 $3 soft、低于 $10 hard）——**v4-pro 不在目标内**，仅敏感性说明。
- **状态：以上均为研究快照+假设，未获批、未真实调用。**

## 5. 与本地 `$3 soft / $10 hard / ≤50 requests` 的对照（G4-R 代码事实）

| 项目 | G4-R 证据 | 解释 |
|---|---|---|
| 本地限额值 | `config/budgets.yaml:2-10`；`security/live_controller.py:53-58`；`config/dsh/target-runtime.patch.yml:42-45`；`config/dsh/target-broker-policy.json:7-16` | soft $3 / hard $10 / soft-call $0.10 / hard-call $0.20 / ≤50 requests / 2.5M in / 600k out / 8 steps / 1 retry；guard `maxProviderRetries=0`、`maxOutputTokens=1024` |
| 性质 | 同上 + `config/budgets.yaml:11` `live_pricing_snapshot: REQUIRED_UNVERIFIED` | **本地工程目标**（`LOCAL_POLICY`）；代码常量是冻结契约，`config/budgets.yaml` 是声明镜像 + 漂移检测（`live_controller.py:143-197`） |
| 供应商侧强制 | 仅：并发 2500→429；余额不足→402；上下文 1M/输出 393216 等协议约束 | **没有** `$3/$10/50` 对应机制；不得称“绝对硬封顶”、不得承诺“不会超过 $10” |
| 单次 hard-call | `$0.20` × 50 = `$10`（hard），**无余量** | 任何未知辅助调用/重试/扩展计费都可能突破；G5 首次建议 ≤3 请求 |
| 未知/部分 usage | 本地 worst-case 保守占用（`docs/BUDGET_BROKER.md` 语义） | 不当作 0；与官方无 invoice 字段的事实相容 |

**结论**：`$3/$10/50` 是 M0 工程目标与本地 fail-closed 策略；真实花费安全依赖“预充值低额度 + 本地强制 + 人工 Kill Switch + 执行日复核价格”，而不是供应商硬限额。

## 6. 无法验证项（本轮不能给出官方证据）

1. 维护者账户实际结算币种/真实扣费账单（无登录、无请求）。
2. 真实 tokenizer/usage/cache 命中率。
3. reasoning tokens 是否与 completion_tokens 单列计费（INFERRED）。
4. 官方当前有效价格与生效日精确对应（仅 2026-11-19 快照；需重核）。
5. 429 QPS/Retry-After/重复计费/断连计费；完整请求超时。
6. web 工具/文件/OCR/语音扩展计费当前状态（官方页面冲突）。
7. 供应商预算/额度 API（本次 sitemap 未见；不能断言不存在）。
8. DSH 直连官方 provider 的协议（OpenAI vs Anthropic）及其对 usage 映射的影响。
9. 任何真实费用是否 ≤ 本文件上界（需真实账单+Console 对账，属人类 H-02/D-17）。

## 7. 建议 / 人类决策引用

1. D-17：G5 当日重采官方价格/模型/usage 字段，维护者签收；本文件 2026-11-19 快照过期不得直接用于预算。
2. D-18：H1 前完成 usage mapping v2（官方 OpenAI 格式 hit/miss、无 cache-write；Anthropic 格式三桶可映射）。
3. D-15/D-16：先选定并统一 provider 路由与 egress allowlist，再谈价格/预算（当前 BLK-01）。
4. D-12：G5 首次真实授权应远小于 50 次（建议 ≤3），并保留“未知/超时=worst-case”的 fail-closed 结算。
5. 本文件与 `A_NEXT_PROVIDER_CONTRACT_DRAFT.md` 一起归档；**不构成任何 G4-H/G5/Live 批准**。

## 8. 声明

全部外部价格/模型/usage 事实为 **2026-11-19 研究快照、未获批、未真实调用**；
本文件不是账单、不是报价承诺、不是部署/花费授权；`LiveGate=BLOCKED`、`G5=BLOCKED`、`M0=DECISION_PENDING` 不变。
