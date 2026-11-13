# Autonomous Teacher — M0 DeepSeek Harness 技术验证任务书

- 文档版本：v0.4（依据六项内部审计修正验收、依赖和安全边界）
- 日期：2026-11-14
- 项目性质：个人自用、开源、单开发者、低成本模型优先、长期探索 RSI
- 文档状态：**设计任务书；不是已执行的实验报告**
- 默认模型：**DeepSeek V4.1 Flash**；不开展低价模型横向选型
- DeepSeek 官方 API 型号：`deepseek-flash`（对应 V4.1 Flash 最新服务版本；记录实际请求时版本）
- OpenRouter 同模型可选路由：`deepseek/deepseek-v4.1-flash`（仅在已有 OpenRouter Key 时验证；不比较价格/能力）
- OpenCode Go：优先用于 Coding Agent 开发；仅在官方明确允许第三方 API 接入时作为 DSH Runtime 的可选渠道
- 执行对象：Coding Agent
- 最终决策：GO / CONDITIONAL GO / NO-GO；证据不足时先标记 **DECISION PENDING / BLOCKED**，不得强判

## 0. 任务声明（直接交给 Coding Agent）

你负责搭建并执行 **Autonomous Teacher 的 M0：DeepSeek Harness（DSH）技术可行性验证**。请先检查官方文档和实际安装版本，再编写验证代码和测试。不要预设文档中的接口始终不变，也不要擅自实现 M1 产品。

**总体目标**：证明或证伪 DSH 是否适合作为长期的 Agent Runtime，尤其是 **指定 DeepSeek V4.1 Flash** 的稳定调用、工具插件、Session 持久化、可重复的 A/B 实验，以及与未来 RSI 代码进化相容的安全隔离。

**执行原则**：
1. 优先使用公开、正式 SDK/API；禁止直接修改 DSH 上游核心源码来“让测试通过”。
2. 保留原始证据：版本、Git commit、配置（去密）、调用轨迹、失败日志、用量和费用。
3. `offline` 测试默认无模型调用；所有付费/联网测试必须显式 `--live` 启用。
4. 新旧策略比较必须使用同一测试输入与评分器；模型输出随机性应被记录，不假装完全可复现。
5. **所有代理生成代码默认未受信任**。动态候选（RSI 候选脚本、生成插件、实验中产生的可执行片段）只能在无真实凭据的独立隔离环境运行。拟进入可信基线的控制器/Adapter/插件必须通过人类维护者审查、冻结版本和安全准入后，才可在最小权限环境使用实验凭据；Agent 无权自行批准。详见 §5 E5。
6. 不允许 Agent 改写隐藏评估集、晋升门槛、成本限制和安全规则；对这些文件的修改必须经过独立人工审批并记录变更，不得在现行实验中悄悄放宽。
7. 如果框架能力不支持目标，记录 `BLOCKED`、可验证原因与替代方案，不编造结果。
8. 始终区分**选定主路由**、**同模型可选路由**和**同模型不同教学策略**；可选能力失败不自动改变核心验收结论。

**明确不在 M0 范围内**：低价模型排行/选型、自动模型路由、多模型质量基准、教学 Web UI、完整 Skill Graph、真正的 CF 判题平台接入、真实学习增益实验、自动教法研究、在线 RL、多 Agent 团队、自动合并 RSI 改动、生产级多租户。

## 1. 验证假设与通过标准

| 编号 | 假设 | 核心判断 |
|---|---|---|
| H1 | Python 应用可稳定调用 DSH | SDK 启动、关闭、异常处理、结构化包装均成功 |
| H2 | 指定 DeepSeek V4.1 Flash 在 DSH 中可靠运行 | 默认以 DeepSeek 官方 `deepseek-flash` 为主验收路由；仅经人工批准切换基线，才可由经验证的同模型 OpenRouter 路由承担同等验收（详见 §2.2） |
| H3 | 插件能力能满足教学工具需求 | 自定义 `skill_lookup` 工具可加载、调用、卸载/重启 |
| H4 | Session 适合长期学习轨迹 | 持久化、重启恢复、事件提取与隔离成功 |
| H5 | 新旧 Agent/Prompt 的离线评估可控 | 相同 fixture 独立运行、保存 trace、评分与比较 |
| H6 | 不可信代码能在外部沙盒安全测试 | 网络、凭据、目录访问、资源消耗受到限制 |
| H7 | 对个人开发者来说成本可控 | 所有 live 调用均可追踪，达到预算上限自动阻断 |

M0 不能证明“教学效果优于 ChatGPT”，也不能证明通用 RSI 收敛；它只证明**使后续研究可实施的基础设施**。

## 2. 技术架构（M0 最小形态）

```text
              CLI: m0.py / pytest
                       |
                Experiment Runner
                       |
    +------------------+------------------+
    |                  |                  |
 HarnessAdapter   EvalContract       BudgetGuard
    |                  |                  |
    |         Graders / Fixtures    UsageCollector
    |
 DeepSeekHarness (Python SDK; subprocess / JSON-RPC)
    |
 DSH Runtime (version-pinned profile + plugin)
    |----------------------|
  LLM route           skill_lookup tool
    |                      |
 DeepSeek V4.1 Flash    fixed local fixtures
 selected route only

  RunRecord + Sanitized Trace --> local SQLite / JSON artifacts

  Human-reviewed Trusted Controller (least privilege, credential boundary)
  Unreviewed candidate code --> separate Docker sandbox (NO API KEY, NO NETWORK)
```

**隔离边界**：
- `HarnessAdapter` 是唯一导入 `deepseek_harness` 的 Python 模块；不将 DSH Session/事件对象传递给业务核心。
- `EvalContract`、`BudgetGuard` 和 `PromotionGate` 由项目自身维护，未来可换 PydanticAI Runtime。
- **可信基线不是“由 Coding Agent 编写”的同义词**：必须经人工审查批准；候选代码不得在有凭据的控制器进程内通过 import、exec、插件热加载或 Shell 执行。
- 不把 `sdk-minimal` 的内置 Shell 当作安全沙盒；`cwd` 不是文件系统安全边界。
- M0 不需要 Next.js/FastAPI。先使用 CLI 及自动测试，减少无关工程量。

## 2.1 最小稳定接口

```python
from dataclasses import dataclass
from typing import Protocol, Any

@dataclass(frozen=True)
class RunRequest:
    case_id: str
    prompt: str
    candidate_id: str
    session_id: str
    provider: str
    model: str
    route_id: str  # 明确本次使用哪条已批准渠道

@dataclass
class RunRecord:
    run_id: str
    case_id: str
    candidate_id: str
    session_id: str
    route_id: str
    text: str
    status: str
    events: list[dict[str, Any]]
    input_tokens: int | None
    output_tokens: int | None
    estimated_cost_usd: float | None
    error_code: str | None

class AgentRuntime(Protocol):
    def run(self, request: RunRequest) -> RunRecord: ...
    def resume(self, session_id: str, prompt: str) -> RunRecord: ...
```

按已安装 SDK 实际 API 细节实现 Adapter；上述为**本项目定义的接口**，不宣称是 DSH 官方接口。

## 2.2 模型路由选择与 E1/GO 判定政策（规范性）

**固定的是模型，不是调用渠道。** `deepseek-flash`（DeepSeek 官方 API）与 `deepseek/deepseek-v4.1-flash`（OpenRouter）可能访问同一模型，但属于**不同渠道**，不能把其中一条渠道的成功冒充另一条渠道通过。`teacher_v0` 与 `teacher_v1` 则是**同一模型、同一选定渠道上的不同策略**，并非多模型测试。

- **默认主验收渠道 `primary_route`**：`deepseek-official / deepseek-flash`。E1 的 3/3 Smoke、真实工具调用、结构化输出和费用检测均对这条已选定渠道执行。
- **可选渠道 `optional_route`**：如已有合规 OpenRouter API Key，可另做同模型烟测；若其未被选为 `primary_route`，失败/不可验证只能记为 OPTIONAL FAIL / OPTIONAL BLOCKED，**不降低** E1 或总体 GO 结论，也不能作为 CONDITIONAL GO 的独立理由。
- **主渠道切换程序**：当官方 API 不可用时，先分别记录官方渠道错误原因（凭据/网络/服务/SDK 配置），再由**人类维护者显式批准** `ROUTE_DECISION.md` 中的基线变更。必须有证据表明目标路由确实指向规定的 DeepSeek V4.1 Flash；版本/别名映射不确定时不得擅称同模型。切换后，对新的 `primary_route` **完整重跑 E1 与受影响的 E2/E3/E4 Live 测试**，不得沿用其他渠道的 PASS。
- **批准后的结论**：新主渠道若完成所有强制验收，可对“采用该渠道的具体运行配置”给出 GO，但报告须标明 `GO (approved primary route: openrouter)`，并独立列出官方 API 的 FAIL / BLOCKED / NOT TESTED。此 GO **不代表官方直连已经通过**。
- **未批准或未验证的替代路由**：只能记录为建议/诊断证据，不满足 E1 必选门槛；如果因缺 API Key、网络或额度而无法运行，标 `BLOCKED`、最终 `DECISION PENDING`，**不是**直接判定 DSH 技术 NO-GO。发现确定性且不可接受的 DSH 缺陷，才能按 §10 判 NO-GO。
- `docs/ROUTE_DECISION.md` 至少记录：`requested_model`、`route_id`、供应商、模型版本证据、选择原因、人工批准者及日期、API 认证允许性、适用验收用例、所有已知渠道各自状态。**Agent 不得自己批准路由切换。** `ROUTE_DECISION.md` 是审计记录，不是单靠修改文件就能触发的权限开关；维护者应通过独立于 Coding Agent 的操作确认路由配置与凭据注入。

**判定优先级**：E1–E5 硬门槛 > 当前批准的 `primary_route` > 不被最终方案依赖的 optional routes。可选项目 FAIL 不会自动导致 CONDITIONAL GO；真正成为 M1 设计依赖时，必须事先批准成为正式验收目标并重做相关测试。

## 2.3 OpenCode Go 订阅使用策略（可选，不阻塞 M0）

**决策：模型仍固定为 DeepSeek V4.1 Flash；不进行模型横向选型。** 已有 OpenCode Go 订阅可优先用于 OpenCode Coding Agent 的编码、调试和测试任务，减少额外开发成本。**订阅能否作为 DeepSeek Harness 的模型 API 来源尚未验证**，不可把 OpenCode 客户端内可用等同于提供可供第三方调用的 API。

执行时按以下顺序处理：

1. 检查 OpenCode Go 当前官方订阅说明、可用模型、使用限额、认证方式及第三方客户端/API 访问条款，并记录查阅日期和官方链接。
2. 若官方明确提供兼容的第三方调用入口，且支持指定 DeepSeek V4.1 Flash，则在不提取客户端内部凭据、不模拟私有请求的前提下进行**可选** DSH 接入烟测：基本生成、工具调用、多轮会话和结构化输出。
3. 若未提供或不允许第三方 API 接入，则 **OpenCode Go 仅供 Coding Agent 开发**；E1 的 Runtime 实测继续使用 DeepSeek 官方 API `deepseek-flash`。
4. 若订阅包含的模型与 DeepSeek V4.1 Flash 不同，不替换既定 Runtime 模型，也不重新启动模型选型。
5. 记录订阅固定费用与本次 API 增量费用的区别。已有订阅不计为零成本 API 额度；只有可核实的调用额度才可用于预算抵扣。

**验收**：形成 `docs/opencode-go-access.md`，明确 `SUPPORTED / NOT_SUPPORTED / UNVERIFIED`、证据链接、限制与选定路由。当 OpenCode Go 未被正式批准为主验收渠道时，该渠道失败或不可验证均不影响 E1–E5 及总体 GO 的通过判断；若未来获批为主渠道，则按照 §2.2 全量验收，不能同时将其当成非阻塞项。


## 3. 仓库目录和文件交付

```text
autonomous-teacher/
├── README.md
├── pyproject.toml
├── uv.lock
├── .env.example
├── .gitignore
├── config/
│   ├── models.example.yaml         # 固定 DeepSeek V4.1 Flash
│   ├── budgets.yaml
│   └── dsh/
│       └── sdk-minimal.patch.yml
├── src/autoteacher_m0/
│   ├── cli.py
│   ├── settings.py
│   ├── runtime/
│   │   ├── base.py
│   │   ├── dsh_adapter.py
│   │   └── mock_adapter.py
│   ├── experiments/
│   │   ├── runner.py
│   │   ├── fixtures.py
│   │   ├── paired.py
│   │   └── report.py
│   ├── evaluation/
│   │   ├── contracts.py
│   │   ├── graders.py
│   │   └── leakage_checks.py
│   ├── accounting/
│   │   ├── usage.py
│   │   ├── pricing.py
│   │   └── budget.py
│   ├── storage/
│   │   ├── schema.py
│   │   └── artifacts.py
│   └── security/
│       └── docker_runner.py
├── plugins/
│   └── skill-lookup/                 # TypeScript/Cordis 插件及 manifest
├── fixtures/
│   ├── skills.json
│   ├── teacher_cases.jsonl
│   └── sandbox/
├── scripts/
│   ├── smoke.py
│   ├── run_live.sh
│   └── inspect_session.py
├── tests/
│   ├── unit/
│   ├── integration/
│   └── live/
├── artifacts/                       # gitignored: 运行记录
└── docs/
    ├── M0_RUNBOOK.md
    ├── M0_REPORT.md
    ├── ROUTE_DECISION.md            # 人类批准的主路由基线
    ├── SECURITY_APPROVALS.md       # 受信任代码审查与版本批准
    ├── ADR-001-runtime.md
    ├── THREAT_MODEL.md
    └── TROUBLESHOOTING.md
```

私有评估集放在**仓库之外**的 `AT_M0_PRIVATE_EVAL_DIR`（绝对路径、仅授予可信评分器读权限），不列入 Git 仓库、候选容器挂载和 DSH 可见工作区。仓库内只允许公开示例/Mock Fixtures。不能以 `.gitignore` 代替进程访问控制；候选不得接触隐藏标签和评分器实现。

## 4. 依赖与环境

**推荐环境**：Linux x64 + Docker Engine（Windows 开发者推荐 WSL2 Ubuntu）；Python 3.11（官方最低 3.10）、`uv`、Git。DSH 插件源码开发另需 Node.js、pnpm 和 TypeScript；纯 Python SDK 使用无需安装 Node.js。Docker 安全边界需依赖宿主安全配置，不应视为绝对安全。

**Python 依赖**：
- 必须：`deepseek-harness-sdk`、`pydantic>=2`、`pytest`、`pytest-asyncio`（如有 async）、`PyYAML`、`python-dotenv`、`httpx`、`ruff`。
- 建议：`typer`（CLI）、`rich`（报告输出）、`sqlalchemy` 或标准库 `sqlite3`（M0 用 sqlite3 即可）。
- 不引入：LangGraph、PydanticAI、LiteLLM、DSPy、OpenEvolve（M0 只验证 DSH，不堆叠框架）。

**锁版本**：使用 `uv lock` 锁 Python 版本，记录 `dsh --version`、SDK 版本、Node/pnpm 版本（若启用插件）、Docker 版本及上游 Git commit。禁止使用不锁定的 `latest` 做最终可复现验收。

**最短官方 SDK 验证参考命令**：

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install deepseek-harness-sdk
# 使用官方仓库提供的 python/sdk/examples/minimal.py 进行首次 smoke
```

**真实配置**：
- **未通过 E5-PreLive 安全审批前不得注入真实 API Key。** 审查批准后的受限控制器运行环境才能使用低额度实验凭据，且不保存到 Git、日志、会话内容或候选工作区。
- 显式传入彼此独立的绝对路径：`cwd` 为 disposable workspace，`dsh_home` 为 disposable Harness home。
- `sdk-minimal` 的 Session JSONL 存放在 `<dsh_home>/sessions/`。
- 为避免额外发送会话日志，创建并校验以下 Cordis patch（若所安装版本的插件 ID/配置不同，需先检查合并配置）：

```yaml
- id: session-log-deepseek
  config:
    enabled: false
```

- 测试中明确记录当前 Profile、合并后的插件树和安全配置。不要通过“修改工作目录”误以为完成了 Shell 沙盒隔离。
- **模型选型冻结**：仅采用 DeepSeek V4.1 Flash。默认主渠道 `deepseek-official / deepseek-flash`；OpenRouter 同模型渠道默认可选。允许主渠道切换的唯一规则是 §2.2 的人工审批和完整重验，不允许自动 fallback 或自动降低成功门槛。
- DeepSeek `deepseek-flash` 为服务别名，官方可更新其所指向的版本。Trace 必须记录模型请求 ID、Provider、可获取时的实际模型版本与验证日期，避免模型漂移污染后续实验。
- 若 DSH 默认 Profile 的 Model ID、API 参数与现行官方接口不兼容，先采用公开配置接口适配，不能因教程仍用历史 `deepseek-v4-flash` 而盲目沿用旧 ID。

## 5. 五个实验：步骤、用例、验收标准

### E1 — SDK 生命周期与 DeepSeek V4.1 Flash 接入（唯一主模型）

**目标**：确认 Python → DSH → 当前获批 `primary_route` → DeepSeek V4.1 Flash → Python 的稳定性。**不进行多模型选型**。E1 分为基础部分和联调部分，避免对 E2 形成错误的串行依赖。

**E1a — SDK 基础烟测（在 E2 前）**：
1. 锁定 SDK/Runtime 版本；先以 Mock/不带凭据的方式检查初始化、参数映射、退出、异常模型、日志脱敏和预算守卫。
2. 通过 E5-PreLive 安全准入、获得维护者对可信控制器的批准后，用获批 `primary_route` 实测基本回复与 JSON/Pydantic 校验。保存 Session ID、路由、实际模型版本（若可获得）、SDK 版本和费用证据。
3. 验证 401、429、5xx、超时、无效模型 ID 的外层错误分类与有界重试（默认 Mock 注入）。

**E1b — 工具联调（E2 最小插件可用后）**：
4. 使用 E2 注册的真实 `skill_lookup` 工具，由模型产生工具调用；必须检查真实工具事件，不能只检查回答中提到 `skill_lookup`。
5. 在同一获批 `primary_route` 完成 6 个小任务、3/3 连续 Smoke、结构化输出、工具结果及调用成本统计。真实插件联调日志可同时作为 E2 的部分证据，但必须分别满足各自断言。
6. 只在用户已经拥有合规渠道且明确愿意测试时，额外测试同模型 OpenRouter 或 OpenCode Go；可选渠道不得造成 M0 延期。不得进行自动跨渠道回退。

**测试用例**：
- `E1-01`：主渠道简单问答输出固定标识 `M0_SMOKE_OK`；3 次独立执行。
- `E1-02`：返回 JSON `{ "skill_id": "binary_search", "ready": true }`，由本项目 Pydantic 校验。
- `E1-03`：E2 可用后，真实调用 `skill_lookup`，验证工具事件与结构化结果。
- `E1-04`：无效 Key / Model ID 有明确错误类型，且不暗中切到其它模型/渠道。
- `E1-05`：预估超预算时自动阻止发起请求。
- `E1-06`：限时、步数和重试上限有效；内部自主 steps 不可精确约束时必须在报告中注明并启用外部总停机保护。
- `E1-07`：路由溯源测试。所有证据包含 `route_id`；替代渠道 PASS 不得自动标记官方渠道 PASS。

**验收**：`E1a=PASS` 且 `E1b=PASS`，并在**当前批准主渠道**完成连续 3/3 Smoke、至少一次真实工具调用、JSON 结构校验、错误显式暴露及成本追踪。**不要求第二个 Provider、第二个模型、自动路由或可选渠道通过。** 如主渠道切换，必须按 §2.2 完整重验；无 Key/网络时记 `BLOCKED`，不伪造 PASS，也不自动判 DSH NO-GO。

### E2 — 自定义教学插件及扩展能力

**目标**：实现一个很小的真实工具，而非只让 Agent 使用 Bash 读文件。

**插件规范**：`skill_lookup(skill_id: string) -> SkillInfo`，其中 `SkillInfo = {id, title, prerequisites, objectives, source_version}`。数据来自只读的 `fixtures/skills.json`，对未知 ID 返回明确的 not-found 结果。

**步骤**：
1. 阅读官方 First Plugin、Build a Tool 教程，用 `@deepseek-ai/cordis` 和 `@deepseek-ai/dsh-tools` 构造 TS 插件。插件**初始仍为待审查代码**，通过静态/离线审查后才能进入有凭据的可信 Runtime。
2. 按官方方法构建/安装插件，绑定 `sdk-minimal` 或其他适当 Profile；必要时为插件管理安装 pnpm。
3. 先离线验证插件在工具注册表中的声明、schema 和固定 Fixtures，形成可用于 E1b 的最小插件；随后在批准的可信控制器中验证模型可见并可以调用。
4. 重启 Runtime，确认插件可用；测试插件被移除后工具不存在（或输出明确插件状态），不残留重复注册。
5. 把工具调用事件导入项目 Trace 格式。

**测试用例**：
- `E2-01`：`binary_search` 返回指定前置知识。
- `E2-02`：未知技能返回已定义错误，不抛出非预期异常。
- `E2-03`：空字符串/错误类型被 schema 拒绝。
- `E2-04`：重启后插件行为与首次一致。
- `E2-05`：关闭或卸载插件后不再被 Agent 调用；若该机制依赖重启，记录这一限制。

**验收**：全部确定性单元测试通过；经 E5-PreLive 安全审批后，真实 Agent 工具调用至少 3/3 成功；插件扩展不修改 DSH 上游源码；记录开发耗时、调试路径及版本兼容问题。E2 离线插件 PASS 不等于 E2 Live 联调 PASS。

### E3 — Session 持久化、恢复、逻辑隔离、轨迹收集

**目标**：证明 DSH 可作为学习会话执行层，特别验证**正常 Session API/存储命名空间不会串数据**。**E3 不负责证明恶意代码的文件访问隔离**；那是 E5 的外部容器与宿主权限测试。

**步骤**：
1. 创建独立 `session_id`、home 与 workspace，发送消息并完成落盘。
2. 关闭 SDK 进程；在新进程通过官方支持的恢复方法恢复会话并继续交互。
3. 检查 JSONL 的事件顺序、工具事件、模型渠道和 Token usage（若可用）。
4. 检查未知、损坏、已占用 Session 的显式行为/错误。
5. 使用两个独立 DSH_HOME、相同 Session ID，通过**正常、受支持的 Session 创建/恢复 API**分别保存 nonce A/B；确认 A 不会加载 B 的历史，B 不会加载 A 的历史。只证明逻辑命名空间隔离。
6. 受控中断任务，记录恢复后的状态；验证旧 Shell 子进程不会随历史事件恢复。
7. E5 中另行放置已知路径的宿主假日志，模拟敌对候选的直接文件读取尝试；绝不能将此安全能力从 E3 的 API 隔离结果中推导。

**测试用例**：
- `E3-01`：关闭和重启后的上下文恢复 3/3 成功。
- `E3-02`：错误 Session ID 的行为明确，不得将隐式新建误报为恢复成功。
- `E3-03`：事件序列可解析，且关键事件可映射到 `RunRecord`。
- `E3-04`：同名 Session ID + 不同 DSH_HOME，在正常 API 路径下不会串历史（nonce A/B 双向断言）。
- `E3-05`：受控中断后不产生虚假的成功状态。
- `E3-06`：脱敏导出 Trace 不含模拟密钥哨兵字符串。

**验收**：正常 API 恢复 3/3；事件可解析、错误/中断语义清楚、跨 home **正常会话 API** 不混用。**不同 home 或 cwd 不是 OS 权限边界**，即使 E3 PASS，也不代表候选代码无法通过绝对路径读取别的 home；必须独立通过 E5。事件回放不承诺 LLM 字节级确定性。

### E4 — 新旧教学策略的配对评估（RSI 基础）

**目标**：建立将来 Improvement Engine 所需的候选对照实验能力。

**固定案例**：准备 20 个虚构学生错误诊断场景（例如二分答案的单调性误解、边界 off-by-one、忽略溢出、错误复杂度判断），其中开发集 12、保留集 8；不得把保留集直接放进 Agent Prompt。

**候选（两个候选必须使用同一个 DeepSeek V4.1 Flash 型号、同一个获批 `primary_route`，只比较教学策略）**：
- `teacher_v0`：直接指出问题并解释。
- `teacher_v1`：先诊断误解，优先引导学生解释或构造反例，避免直接泄露完整解法。

**步骤**：
1. 把每个场景表示为 `EvalContract`，包含公开输入、隐含错误标签、必要动作、禁止动作和评分器版本。
2. 两个版本分别用独立、全新 Session 处理相同输入；固定模型、获批 `primary_route`、采样参数（如果可配置）、工具、知识来源和 Token 上限。任何跨渠道差异均不属于 `teacher_v0` vs `teacher_v1` 的教学策略对照。
3. 尽量使用规则/标准答案评分：标签是否正确、输出是否包含不允许的完整代码、工具是否按契约调用；可选一个独立 LLM Judge 但必须记录其不确定性与成本。
4. Mock 模式对 20 个案例完整运行，并在离线模式重复验证评估器。Live 模式仅对代表性子集（如 6 个案例 × 2 个候选）做配对调用；需要评估输出变异时，在预算范围内对 2 个案例复测。不要假定固定 Seed 必然可用。
5. 保存逐案例差分、失败原因、调用轨迹、成本、评估分数，并自动生成 `comparison.md`。
6. 将开发集和保留集分开分析；不要在一轮里根据保留集结果修改候选后继续反复优化同一保留集。

**测试用例**：
- `E4-01`：Mock Runtime 的同输入同输出实验可重现。
- `E4-02`：两个候选都生成独立 `run_id`、`session_id`、`candidate_id`。
- `E4-03`：评估器故意返回错误时应标记 `EVAL_ERROR`，不能按 0 分掩盖。
- `E4-04`：提示泄露测试能抓住明确的完整答案模式。
- `E4-05`：同一案例两个版本调用费用均被记录。
- `E4-06`：任意候选不能读取隐藏标签或评分器代码。

**验收**：`mock` 模式对全部 20 个案例完全自动化、无 API 调用；Live 模式对至少 6 个配对案例生成真实结果及至少一种可解释的逐案例指标；评分器独立于候选；输出有汇总报告及全部可追溯记录。不要用离线评估结果声称已经验证真人的学习增益。

### E5 — 代码信任边界、可信控制器审批、候选沙盒与失败注入

**目标**：建立可审计的**控制平面 / 候选执行平面**分离。Coding Agent 生成的代码不会因为位于 `src/`、被称为 Adapter，或运行在宿主机就自动获得信任。

#### E5-PreLive：所有 Live 测试的前置安全门槛（必须先于 E1a 的真实调用）

1. **代码分类**：
   - **始终按不可信候选执行**：实验时生成/修改的脚本、动态代码、RSI 候选、待审查新插件、模型输出的执行指令。不得与真实 API Key、宿主私人目录、私有评分集同环境运行。
   - **可申请晋升为可信基线**：固定版本的 Python 控制器、`HarnessAdapter`、运行参数配置、最小 `skill_lookup` 插件，以及锁定依赖。进入可信基线必须经过人工审查批准，而不是 Coding Agent 自行判断。
2. **人工准入流程**：Coding Agent 先在无真实凭据的隔离环境完成离线测试；向维护者提交 Git SHA、变更 diff、依赖锁、实际 DSH Profile/工具清单、危险执行能力检查、日志脱敏与密钥流向说明。**人类维护者**检查后在 `docs/SECURITY_APPROVALS.md` 记录批准的具体 SHA、配置哈希、可运行命令、允许的权限和有效范围。**此 Markdown 文件仅为审计记录，不能作为自动授权凭据**：维护者必须在独立于 Coding Agent 的受控执行会话中确认哈希，亲自解锁/注入低额度测试 Key；Coding Agent 即使修改审批文件也不得取得真实 Key。任何改动上述基线的提交都需重新审批。测试报告必须包含可核对的批准证据；缺少审批即 `BLOCKED`。
3. **可信控制器的最小权限**：仅持有受额度约束、可撤销的实验 Key；在独立受限环境运行（不要求一定在宿主机），不挂载私人数据、Docker socket 或隐藏评估源。Key 只注入必须调用 API 的最小进程，不进 Prompt、Trace、代码仓库或容器镜像；使用独立 Key 及供应商侧限额降低外部调用风险。
4. **防权限继承**：有凭据进程不得执行/`import`/`exec` 动态候选；不得把候选路径配置为可加载插件目录；不得调用允许任意 Shell 的 DSH 工具。**先检查已合并的 DSH Profile/实际工具注册表**：如果无法可靠关闭危险 Shell/写文件/网络执行能力，则不得把真实 Key 注入该 Runtime，先换受限 Profile 或改用隔离、不可见密钥的远端代理架构并重新审查。
5. **安全准入用例**：`E5-P01` 审批文件的 SHA/配置哈希与实际运行内容一致；`E5-P02` 任何未审批文件变更导致 Live Gate 关闭；`E5-P03` Agent 即使更改 `SECURITY_APPROVALS.md` 也无法触发凭据注入或绕过独立的人工授权；`E5-P04` DSH 可用工具白名单不包含未批准 Shell/代码执行工具；`E5-P05` 输出日志、子进程环境、工作目录及插件读取路径不含候选可访问的真实 Key。

**E5-PreLive 通过只表示最低上线前准入已完成，不等于完整 E5 安全实验通过。** 任一安全关口不满足，禁止真实 API 调用；仅运行 Mock/离线测试。

#### E5-Full：不可信候选的外部执行隔离

候选代码仅运行在独立 Docker 容器（或具有经验证的同等隔离能力的独立执行环境）。推荐默认配置：无真实凭据、无网络、非 root、只读根文件系统、无 Docker socket、禁特权、最小 capabilities、CPU/内存/进程/运行时间限制、只读测试输入挂载、单独可写临时目录；容器安全强度受主机和内核配置影响。

**独立 Docker 示例**（仅示意，运行前需检查镜像和 Linux/WSL2 宿主权限）：

```bash
docker run --rm \
  --network none --read-only \
  --cap-drop ALL --security-opt no-new-privileges \
  --pids-limit 64 --memory 512m --cpus 1 \
  --user 65534:65534 \
  --tmpfs /tmp:rw,nosuid,size=64m \
  --tmpfs /work:rw,nosuid,uid=65534,gid=65534,mode=0700,size=64m \
  --mount type=bind,src="$(pwd)/fixtures/sandbox",dst=/input,readonly \
  python:3.11-slim sh -lc 'cp -r /input/. /work/ && cd /work && python exercise.py'
```

**完整测试用例**：
- `E5-01`：候选尝试读取/枚举宿主环境中预置的**假 Key**、其他 DSH_HOME 的已知绝对路径和私有假 Session 日志；均不可读。**这项是文件系统安全测试，不属于 E3。**
- `E5-02`：候选尝试外部网络连接失败。
- `E5-03`：候选尝试在允许的 `/work`、`/tmp` 之外写入失败。
- `E5-04`：死循环、内存滥用、进程数滥用均受到外部限制；失败后容器退出。
- `E5-05`：候选无法访问/篡改仓库外的私有评估集、评分器、控制策略和预算限制。
- `E5-06`：一次恶意/崩溃候选失败后，新独立容器仍能执行下一实验，可信控制器状态完整。
- `E5-07`：验证 DSH 实际合并权限配置、Session-log 上传状态；不得将默认 `danger-full-access` 或不同 home 误当安全隔离。
- `E5-08`：审查批准后的控制器发生一行代码/依赖/插件配置变化，Live Gate 默认关闭，直到维护者重新批准。
- `E5-09`：候选不能使用 docker.sock、privileged、宿主敏感 bind mount 或可信进程子执行渠道继承权限。

**验收**：E5-PreLive 全部通过，且 E5-Full 关键负向安全测试全部通过，附隔离配置、原始断言和已知残余风险；不能得出“已达到生产级绝对安全”的结论。未通过时不能 GO，不允许通过删减测试或扩大候选权限解决。

## 6. Evaluation Contract 与最小测试数据

每个测试用例必须具备可机器解析的契约：

```json
{
  "case_id": "mono-001",
  "category": "misconception_diagnosis",
  "student_input": "所有题都可以二分答案，因为复杂度是 O(log n)",
  "expected_concepts": ["feasibility", "monotonicity"],
  "expected_misconceptions": ["assumes_monotonicity"],
  "forbidden": ["complete_solution_code"],
  "max_cost_usd": 0.10,
  "evaluator_version": "m0-eval-v1"
}
```

`expected_concepts` 不应通过简单的关键字出现直接判为正确；评分器应验证概念关系，至少在人工抽查案例中确认。`forbidden` 中的“泄露完整解法”也不能只用字符串匹配，最低要求是一组具代表性的确定性负例，并对边界案例标记 `NEEDS_REVIEW`。

**建议测试数据分布**：20 个场景中，单调性误解 5、边界错误 5、复杂度/先修误解 4、代码/溢出错误 4、信息不足或误判风险 2。至少 2 个案例的合理行为应该是“信息不足，先追问”，避免策略只会给确定答案。

## 7. Trace、持久化、费用和报告

**每次运行保存**：
- `experiment_id`, `run_id`, `case_id`, `candidate_id`, `session_id`, `route_id`（区分官方直连与其他渠道）。
- UTC 时间，测试集版本，Git SHA，SDK/Runtime/Profile，插件版本，模型提供商和模型 ID。
- Prompt 指纹、公开输入、输出和评分（经过敏感信息过滤）。
- 工具调用名称、参数摘要、结果摘要、事件引用及失败原因。
- 成功/失败的 Token 用量（如果提供）、价格表版本、**实际费用**（提供商返回时）或**估计费用**（无法获取实际值时）。
- 错误类型如 `PROVIDER_ERROR`, `BUDGET_EXCEEDED`, `TOOL_ERROR`, `INVALID_OUTPUT`, `EVAL_ERROR`, `TIMEOUT`, `SECURITY_BLOCKED`。

**成本公式**：

`estimated_cost = (uncached_input_tokens * price_input + output_tokens * price_output + cached_input_tokens * price_cached_input) / 1_000_000 + provider_extra_fees`

模型价格必须按当前提供商展示的具体型号快照读取；缓存、推理 Token、模型不同倍率和费用折扣按实际计费方式处理。若账单返回实际成本，以账单为准。Token 计数缺失时采用保守估计并在报告中标记 `estimated`；不允许当作零成本。

**渠道成本原则**：OpenCode Go 订阅优先承担 Coding Agent 开发工作；Runtime API 费用按实际可用渠道单独计量。未经官方确认不得将订阅视为可供 DSH 免费调用的 API。

**建议 M0 预算**（工程上限，不是模型实时售价；由于固定使用 V4.1 Flash，不做大规模模型对比）：

| 项目 | 软预算 | 硬预算 / 约束 |
|---|---:|---|
| 总测试 | US$3 | US$10；超过后拒绝新增 live 请求 |
| 单个调用 | US$0.10 | US$0.20 预估上限，超限不启动 |
| 单次 Agent 任务 | — | 最多 8 次模型 step，最多 1 次自动重试 |
| 总请求数量 | — | 最多 50 次 live 模型调用（如需扩展必须显式批准） |
| Token 保护 | — | 全量累计约 250 万输入 + 60 万输出 Token 上限，达到任一上限即停止 |

**计费要求**：只针对 DeepSeek V4.1 Flash 读取执行当日官方 API 价格及峰谷/缓存规则，计算预计费用，不需要其它模型的价格表。保留之前设定的软预算 US$3、硬预算 US$10，并以预充值低额度凭证作为第二道限额。

**成本防失控**：`BudgetGuard` 在请求**前**估算最坏消耗；请求**后**按实际/估计消耗记账。若运行时无法约束内部自主 steps，应采取外层超时、进程终止和预充值低额度实验 Key；禁止假称仅靠 Python 超时能精确限制供应商账单。

**最终报告图表/表格**：
- 每个实验测试矩阵：PASS / FAIL / BLOCKED / SKIPPED。
- DeepSeek V4.1 Flash 在**当前获批主渠道**上的 SDK 兼容性、失败率、费用/延迟统计；按渠道分别列出官方直连与可选路由的 PASS / FAIL / BLOCKED / NOT TESTED，不合并为同一结论。
- 自定义插件安装与调用证据。
- Session 恢复与事件数据质量。
- A/B 配对的逐案例差分、变异性和失败例子。
- 可信控制器的人工审批记录、沙盒攻击模拟结果、E3 逻辑隔离与 E5 文件系统隔离的分别结论、未关闭的风险。
- 关键代码位置、CLI 命令及环境复现步骤。

## 8. 统一自动测试与 CI

**默认命令语义**（由 Coding Agent 实现，不代表仓库已存在）：

```bash
uv sync
uv run ruff check .
uv run pytest tests/unit -q
uv run pytest tests/integration -q
uv run python -m autoteacher_m0.cli inspect-runtime
uv run python -m autoteacher_m0.cli smoke --mock
uv run python -m autoteacher_m0.cli paired --mock
# 只有显式批准后才联网/付费
uv run python -m autoteacher_m0.cli smoke --live --budget-usd 1
uv run python -m autoteacher_m0.cli paired --live --budget-usd 5
uv run python -m autoteacher_m0.cli report --experiment latest
```

测试分三类：
- Unit（必须离线）：schema、日志脱敏、成本计算、评分器、失败处理、预算截断。
- Integration（尽量离线）：Mock Runtime、Plugin 构建可行性、Session JSONL 解析、Docker 沙盒。
- Live（仅人工显式开启，且通过 E5-PreLive）：**指定 DeepSeek V4.1 Flash 的已批准主路由**、真实工具调用、真实持久化与同模型/同路由的配对策略实验；同模型的其他渠道仅可选。不开展多模型测试。

推荐 CI 只自动执行离线测试；不把任何 API Key 或真实用户学习数据引入公共 CI。任何公开 CI 也不得将“审批文件存在”视为可自行获得真实凭据的授权。每个测试都要明确 Assert，不能只打印结果。

## 9. 里程碑、顺序与依赖（修复 E1/E2 依赖）

1. **T0：环境基线 + 路由冻结**：锁依赖、建立 MockRuntime/预算守卫、记录 DSH Profile；记录默认官方主渠道，OpenCode Go 订阅状态单独调查且不阻塞。交付 `M0_RUNBOOK.md` 和 `docs/ROUTE_DECISION.md`（未切换时记录默认基线即可）。
2. **T0-S：Live 安全准入**：在无密钥环境进行代码/依赖/插件审查，完成 §E5-PreLive，**必须有人类维护者审核 SHA/配置并批准**，否则所有 Live 用例保持 `BLOCKED`。交付 `SECURITY_APPROVALS.md`。
3. **T1a：E1 SDK 基础 Smoke**：完成 SDK 初始化、退出、错误分类、Pydantic JSON 校验和获批主路由基本调用；**不要求此时存在 `skill_lookup`**。交付 `dsh_adapter.py` 与 `E1a` 记录。
4. **T2a：E2 最小可用插件**：先通过离线单测、插件注册、参数 schema 和审批；交付最小 `skill_lookup` 插件。
5. **T1b + T2b：完整联调验收**：执行 E1 的真实工具调用与 3/3 主路由 Smoke，以及 E2 插件 3/3 真实调用、重启/卸载用例；统一保存 Trace，分别写 E1/E2 结论。
6. **T3：Session**：E3 Session API 逻辑隔离与恢复/轨迹，不将其解释为文件系统隔离；交付 Trace Normalizer。
7. **T4：Experiment Runner**：E4 Mock/Live 配对评估；同一模型、同一批准主路由比较 `teacher_v0`/`teacher_v1`。
8. **T5：E5 完整沙盒验收**：在 E5-PreLive 基础上执行 E5-Full 的敌对文件访问、网络、资源、权限继承等负向测试，交付 `THREAT_MODEL.md`。
9. **T6：决策报告**：形成 E1–E5 独立结论、路由切换记录、人工审批证据和 `ADR-001-runtime.md`。

允许 T3/T4 的 Mock 实现、T5 沙盒开发与费用记录并行。**E1a 的基础 Smoke ≠ E1 完整 PASS；E2 离线插件可用 ≠ E2 完整 PASS。** 因额度、网络、审批受阻的必需 Live 用例记 `BLOCKED`；不得通过绕开安全 Gate 来补齐。

## 10. 框架选型 Go / No-Go 门槛（规范性）

**分开记录两类状态**：

- **实验状态**：每项测试 `PASS / FAIL / BLOCKED / SKIPPED`；未运行不是 PASS。
- **Runtime 选型结论**：`GO / CONDITIONAL GO / NO-GO / DECISION PENDING`。`DECISION PENDING` 不是第四种技术好坏判断，只表示强制证据不足，尚不能作出最终选型结论。

### GO（可作为 M1 主 Runtime）

同时满足：
1. E1 完整通过：**当前人类批准的 `primary_route`** 上的指定 DeepSeek V4.1 Flash 3/3 Smoke、真实工具、输出校验、错误处理和预算追踪。默认主渠道为 DeepSeek 官方 API；发生切换时必须留下 §2.2 的事前批准与完整重验，且只对批准后的配置给 GO。
2. E2 自定义插件通过官方公开接口实现并完成 3/3 真实调用，不修改上游核心。
3. E3 正常 API Session 重启恢复与事件抽取通过，不把其当作文件系统权限证明。
4. E4 Mock + 主渠道 Live 配对测试通过，能产出独立可审计的差异报告。
5. E5 **PreLive + Full** 安全门槛通过；已审查控制器和无凭据候选严格分离。
6. SDK/Runtime 版本固定、成本上限可执行、已批准配置可复现。

**重要例子**：五项强制实验全部 PASS、官方 API 为主渠道且可选 OpenRouter/OpenCode Go 失败 → **GO**；不得仅因可选渠道失败降为 CONDITIONAL GO。若经人工批准将 OpenRouter 设为主渠道，且所有强制测试全部重跑并通过 → **GO（仅针对批准的 OpenRouter 配置）**，不得写“官方 API 已通过”。

### CONDITIONAL GO

**只能是强制安全、独立评估与运行可靠性门槛全部通过，但存在将来 M1 实际依赖的非关键工程限制**（例如插件开发需要维护少量公开兼容代码、部分原生非关键观测字段需在外层补齐，且该补偿已测试通过）。每项条件必须记录残余风险、明确责任、修复动作和可核实的停止条件。**完全可选、M1 不依赖的渠道失败不属于条件。** 不得用 CONDITIONAL GO 绕过 E5 安全 FAIL 或关键测试 BLOCKED。

### NO-GO

出现证据充分且无法通过可维护的公开扩展/外部隔离解决的实质性缺陷，例如：
- SDK/插件接口无法稳定使用，必须长期维护侵入式 Fork。
- Session 严重不可恢复或运行状态/错误无法可靠区分。
- 不可信候选无法有效隔离，且无可接受的外部隔离方案。
- 无法限制模型调用数量/费用，产生不可接受的无上限成本风险。
- 对单开发者而言长期维护成本不可接受，且没有足够可验证价值。

### DECISION PENDING（证据不足，暂停最终决策）

强制项受缺 Key、网络、订阅政策、预算、人工审批或未完成集成阻塞，而尚无技术性失败证据时：报告 `BLOCKED` 和恢复验证条件，**不签发 GO / CONDITIONAL GO，也不冒然判 NO-GO**。若现有信息已能实证确认不可修复的核心问题，则转 NO-GO。

### 一致性判定示例

| 事实场景 | E1 | 总体结论 |
|---|---|---|
| 主渠道和 E2–E5 通过，未选用的 OpenCode Go 失败 | PASS | GO |
| 主渠道和 E2–E5 通过，未选用的 OpenRouter 未测试 | PASS | GO |
| 官方渠道失败，但人工批准 OpenRouter 为主渠道且全量重验通过 | PASS（OpenRouter） | GO，仅对获批配置；官方单列 FAIL |
| 官方渠道因无 Key 被阻塞，且未批准替代主渠道 | BLOCKED | DECISION PENDING |
| E5 安全测试确定性失败，外部隔离也无解 | 视 E1 而定 | NO-GO |
| 所有必需项 PASS，但已验证可补偿的非关键维护问题未关闭 | PASS | CONDITIONAL GO（有具体条件） |

## 11. 退路（Fallback Matrix）

| 问题 | 一级退路 | 二级退路 |
|---|---|---|
| DeepSeek 官方 `deepseek-flash` 接入异常 | 单独诊断网络、Key、额度、SDK 配置并记录原路由状态 | 仅经人工审批 §2.2 的同模型主渠道切换，且完整重跑强制 Live 验收；未获批则 `DECISION PENDING`，不自动判 PASS 或 NO-GO |
| Python SDK 接口不稳定 | 锁定可运行 SDK 版本，缩小 Adapter API 面 | DSH TypeScript Runner，通过 JSON-RPC / 自建本地协议与 Python 通信 |
| DSH Plugin 复杂度太高 | 教学工具先留在 Python 服务，通过受控桥接调用 | M1 改用 PydanticAI，DSH 留作 RSI 实验 Runtime |
| Event Log 不适合业务存储 | Python 独立 SQLite 学习数据和 Trace | 标准化事件采集插件，不直接依赖 DSH 内部 Session schema |
| 原生沙盒不够安全 | 在无凭据环境使用独立 Docker Runner、只读输入与禁网 | 若仍无法隔离，使用更强隔离 VM/远程执行环境；安全 Gate 失败不得 GO，不得让候选代码继承可信控制器凭据 |
| 成本/可靠性不稳定 | 减少 Agent steps、缩小上下文或增加缓存 | Mock 驱动开发、人工触发 live；不进行模型横向选型 |
| DSH 总体 NO-GO | 保留全部 EvalContract、RunRecord、测试集和报告接口 | PydanticAI Runtime Adapter；RSI 实验仍可研究 DSH |

**不允许**为了通过 M0 而删除安全隔离、降低必需的错误处理或把未验证模型能力写成已支持。

## 12. 开发完成定义（Definition of Done）

所有任务完成后，Coding Agent 必须交付：

- [ ] 可安装并锁版本的项目，附最短可复制运行说明。
- [ ] `HarnessAdapter` 与 `MockRuntime`，业务代码不耦合 DSH 内部类型。
- [ ] 可运行的 `skill_lookup` DSH 插件与测试。
- [ ] DeepSeek V4.1 Flash 的实测结果，或明确阻塞证据；不要求其他模型。
- [ ] Session 持久化、恢复和可解析 Trace 的测试结果。
- [ ] 至少 20 个虚构教学场景的配对评估设施及报告。
- [ ] Docker 独立执行器和负向安全测试。
- [ ] 本地预算守卫、按调用使用量记录及成本汇总。
- [ ] `M0_REPORT.md` 含 PASS/FAIL/BLOCKED、失败原因及证据路径；官方/第三方渠道分别报告。
- [ ] `ROUTE_DECISION.md` 记录批准的主渠道和所有切换；`SECURITY_APPROVALS.md` 记录维护者对可信控制器 SHA/配置的审批，候选不得访问真实凭据。
- [ ] E3 正常 Session API 的逻辑隔离与 E5 敌对文件访问的安全隔离分别报告。
- [ ] `ADR-001-runtime.md` 给出 GO/CONDITIONAL GO/NO-GO 或 `DECISION PENDING` 的有据结论和理由；可选渠道失败不能单独触发降级。
- [ ] 仍然需要人工判断的风险与待办清单。

**报告中绝不可出现**：“Agent 自我改进有效”“教学成绩优于 GPT”“DSH 安全可信”等未由 M0 实验证明的结论。

## 13. Coding Agent 执行指令模板

> 你正在实现 Autonomous Teacher 的 M0 DSH 技术验证。本文档是唯一的 M0 功能范围基线。
>
> 1. 首先核对官方 SDK/插件 API、安装版本和预览版破坏性变更；如与文档不同，以已安装版本为准，并在 `docs/M0_RUNBOOK.md` 记录差异。
> 2. 从环境基线、MockRuntime、统一 RunRecord 和 BudgetGuard 开始，实现离线单测；人类维护者批准 E5-PreLive 后才能执行需要真实凭据的测试。
> 3. 每个 E1–E5 实验必须包含步骤、至少一个自动化 Assert、结果和错误证据；必须区分 PASS、FAIL、BLOCKED、SKIPPED。E1 拆为先于插件的 E1a 和插件就绪后的 E1b，不能提前宣告整个 E1 PASS。
> 4. 不实现 M1 教育产品，不私自更改评估标准；Coding Agent 写的任何代码未经人类审批均不可信，不能自行赋予控制器真实凭据，候选永不继承控制器的权限。
> 5. 预算默认软上限 $3、硬上限 $10；没有有效预算守卫前禁止大规模 live 调用。
> 6. 结束时提交可复现代码、运行命令、测试报告、`ROUTE_DECISION.md`、`SECURITY_APPROVALS.md` 与 ADR；如果强制证据因非技术原因不足，则写 `DECISION PENDING`，不能用自我评价代替证据。

## 13.1 v0.4 内部审计修订记录

| 审计项 | 修订落点 | 结果 |
|---|---|---|
| 1. Live 仍写多模型 | §8、§E1 | 改为唯一固定模型，区分渠道与教学策略 |
| 2. 可选渠道是否影响 GO | §2.2、§10 | 非依赖的可选渠道失败不降级；依赖渠道须正式获批并重验 |
| 3. E1/E2 先后依赖 | §E1、§E2、§9 | E1a → E2a → E1b/E2b，基础 Smoke 与完整验收分开 |
| 4. OpenRouter 能否替代官方验收 | §2.2、§10、§11 | 只有人工批准成为主渠道并完整重跑，才可对该配置 GO |
| 5. 控制器可信边界 | §0、§E5、§9 | Agent 代码默认待审查；人类批准 SHA/配置后才有凭据权限 |
| 6. DSH_HOME 是逻辑还是安全隔离 | §E3、§E5 | E3 验 API/命名空间；E5 验敌对文件访问和 OS 隔离 |

## 14. 官方参考资料（以实际锁定版本为准）

1. DeepSeek Harness GitHub：<https://github.com/deepseek-ai/deepseek-harness>
2. Python SDK Guide：<https://deepseek-harness.github.io/deepseek-harness/en/guide/python-sdk>
3. Python SDK README：<https://github.com/deepseek-ai/deepseek-harness/blob/master/python/sdk/README.md>
4. DSH Architecture：<https://deepseek-harness.github.io/deepseek-harness/en/reference/>
5. First plugin：<https://deepseek-harness.github.io/deepseek-harness/en/develop/basic/>
6. Tool plugin：<https://deepseek-harness.github.io/deepseek-harness/en/develop/basic/tool>
7. Session subsystem：<https://deepseek-harness.github.io/deepseek-harness/en/reference/subsystems/session>
8. Configure models：<https://deepseek-harness.github.io/deepseek-harness/en/guide/providers>
9. Sandbox subsystem：<https://deepseek-harness.github.io/deepseek-harness/en/reference/subsystems/sandbox>
10. Session log upload configuration：<https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/session/session-log-deepseek/README.md>
11. OpenRouter 官方价格和计费说明：<https://openrouter.ai/support>

---

**M0 完成判定**：我们不是要得到“DSH 很强”的印象，而是要拿到足够的证据，判断它能否在一人可维护、低价 Token 可控、评估可独立、候选代码可隔离的前提下，成为未来 Autonomous Teacher 和 RSI 的运行底座。

## 附录 A：最小 SDK Smoke 示例（需先配置测试 Key）

下列代码仅展示 SDK 的基本调用形状，不执行不可信代码。**先完成 E5-PreLive 人工批准并确认已禁用危险工具**，再创建空的 `/tmp/at-m0-workspace` 并在受限控制器环境设置获批准主渠道 API 凭据；`sdk-minimal.patch.yml` 应包含前述禁用 Session-log 上传的配置。注意：**这不是安全沙盒**，不能在里面执行来自模型的任意 Shell 代码。

```python
from pathlib import Path
from deepseek_harness import DeepSeekHarness

root = Path('/tmp/at-m0').resolve()
workspace = root / 'workspace'
home = root / 'dsh-home'
workspace.mkdir(parents=True, exist_ok=True)
home.mkdir(parents=True, exist_ok=True)
patch = Path('config/dsh/sdk-minimal.patch.yml').resolve()

with DeepSeekHarness(
    dsh_home=str(home),
    cwd=str(workspace),
    profile='sdk-minimal',
    provider='deepseek-official',  # 仅为默认主渠道示例；切换需记录并审批
    model='deepseek-flash',  # DeepSeek 官方 API 模型名；DSH SDK 适配方式需实测
    max_tokens=1024,
    patches=(str(patch),),
) as harness:
    result = harness.run('Reply with M0_SMOKE_OK.', session_id='m0-smoke-001')
    print(result.final_response)
```

这段示例来自官方 SDK 调用形式的简化组合。`deepseek-flash` 是 DeepSeek 当前公开的 V4.1 Flash API 别名，但 DSH SDK 对该别名的传入方式仍须实测。Coding Agent 必须把该型号作为唯一默认模型配置，增加超时、费用门槛、日志脱敏与测试断言。

## 附录 B：插件接口示例（以官方 Build a Tool 指南为准）

以下展示预期的工具 ABI，而非要求照搬为最终文件。真实实现需按照锁定版本的插件打包方式完成注册、卸载与测试。

```typescript
import type { Context } from '@deepseek-ai/cordis'
import { defineTool } from '@deepseek-ai/dsh-tools'

export const name = 'autoteacher-skill-lookup'
export const inject = ['tools']

export function apply(ctx: Context) {
  ctx.tools.register(defineTool({
    name: 'skill_lookup',
    description: 'Return verified skill metadata by skill id.',
    parameters: {
      skill_id: { type: 'string', required: true, description: 'Stable skill id' },
    },
    output: {
      schema: { type: 'string' },
      render: (_args, value) => [{ type: 'text', text: value }],
    },
    async execute(args) {
      // 真实版本请用只读的受控 fixtures；不要直接相信模型提供的文件路径。
      const skills: Record<string, object> = {
        binary_search: {
          id: 'binary_search', title: 'Binary Search',
          prerequisites: ['monotonicity'], objectives: ['recognize predicate'],
          source_version: 'm0-fixture-v1',
        },
      }
      return JSON.stringify(skills[args.skill_id] ?? { error: 'SKILL_NOT_FOUND' })
    },
  }))
}
```

验收时必须验证的是模型实际通过工具注册表调用了 `skill_lookup`，而不是根据 Prompt 自行生成了与工具结果相同的文字。

## 附录 C：必要的反例与已知边界

- **Shell 默认危险**：`sdk-minimal` 的 Shell 对可见的宿主目录有广泛访问能力；仅设置 `cwd` 无法阻止读取其他路径。Live 前必须通过 E5-PreLive，检查可用工具注册表及配置，无法可靠限制时不注入真实 Key。
- **Session 恢复有限**：SDK 可以恢复历史事件，但已退出的 Shell、浏览器等外部进程不会随之恢复。
- **Replay 有多种含义**：事件日志可重新导出过去发生了什么；重新调用 LLM 仍受采样、模型版本和提供商行为影响，不提供字节级确定性。E4 必须使用新 Session 重跑并记录波动。
- **成本不能只算响应 Tokens**：要计入重试、上下文压缩、额外 Judge、服务商差异；`dsh_session_log` 是额外请求字段，官方说明它不消耗模型输入 Token，但涉及隐私/请求体大小，仍建议在 M0 关闭。
- **模型适配不能想当然**：DeepSeek 官方 `deepseek-flash` 是默认主路由；经人工批准的同模型第三方渠道可在**完整重验**后替代为主路由。两条渠道状态严格分开，且未使用的可选渠道不影响 GO。
- **M0 的评估不是教学实验**：一个离线 Teacher 赢了另一个离线 Teacher，只代表在这组固定测试案例/评分规则上更符合要求，不能证明更能帮助真人学习。
