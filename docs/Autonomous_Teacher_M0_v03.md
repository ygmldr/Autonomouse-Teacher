# Autonomous Teacher — M0 DeepSeek Harness 技术验证任务书

- 文档版本：v0.3（增加 OpenCode Go 订阅接入策略）
- 日期：2026-11-14
- 项目性质：个人自用、开源、单开发者、低成本模型优先、长期探索 RSI
- 文档状态：**设计任务书；不是已执行的实验报告**
- 默认模型：**DeepSeek V4.1 Flash**；不开展低价模型横向选型
- DeepSeek 官方 API 型号：`deepseek-flash`（对应 V4.1 Flash 最新服务版本；记录实际请求时版本）
- OpenRouter 同模型可选路由：`deepseek/deepseek-v4.1-flash`（仅在已有 OpenRouter Key 时验证；不比较价格/能力）
- OpenCode Go：优先用于 Coding Agent 开发；仅在官方明确允许第三方 API 接入时作为 DSH Runtime 的可选渠道
- 执行对象：Coding Agent
- 最终决策：GO / CONDITIONAL GO / NO-GO

## 0. 任务声明（直接交给 Coding Agent）

你负责搭建并执行 **Autonomous Teacher 的 M0：DeepSeek Harness（DSH）技术可行性验证**。请先检查官方文档和实际安装版本，再编写验证代码和测试。不要预设文档中的接口始终不变，也不要擅自实现 M1 产品。

**总体目标**：证明或证伪 DSH 是否适合作为长期的 Agent Runtime，尤其是 **指定 DeepSeek V4.1 Flash** 的稳定调用、工具插件、Session 持久化、可重复的 A/B 实验，以及与未来 RSI 代码进化相容的安全隔离。

**执行原则**：
1. 优先使用公开、正式 SDK/API；禁止直接修改 DSH 上游核心源码来“让测试通过”。
2. 保留原始证据：版本、Git commit、配置（去密）、调用轨迹、失败日志、用量和费用。
3. `offline` 测试默认无模型调用；所有付费/联网测试必须显式 `--live` 启用。
4. 新旧策略比较必须使用同一测试输入与评分器；模型输出随机性应被记录，不假装完全可复现。
5. 任何代理生成的代码只能在**独立隔离容器**运行；不允许读取 API Key、测试集秘密或宿主机私人目录。
6. 不允许 Agent 改写隐藏评估集、晋升门槛、成本限制和安全规则。
7. 如果框架能力不支持目标，记录 `BLOCKED`、可验证原因与替代方案，不编造结果。

**明确不在 M0 范围内**：低价模型排行/选型、自动模型路由、多模型质量基准、教学 Web UI、完整 Skill Graph、真正的 CF 判题平台接入、真实学习增益实验、自动教法研究、在线 RL、多 Agent 团队、自动合并 RSI 改动、生产级多租户。

## 1. 验证假设与通过标准

| 编号 | 假设 | 核心判断 |
|---|---|---|
| H1 | Python 应用可稳定调用 DSH | SDK 启动、关闭、异常处理、结构化包装均成功 |
| H2 | 指定 DeepSeek V4.1 Flash 在 DSH 中可靠运行 | 官方 `deepseek-flash` 路由的结构化输出、工具调用、计费与错误处理验证；OpenRouter 同模型路由仅可选 |
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
 OpenAI-compatible

  RunRecord + Sanitized Trace --> local SQLite / JSON artifacts

  Candidate code --> separate Docker sandbox (NO API KEY, NO NETWORK)
```

**隔离边界**：
- `HarnessAdapter` 是唯一导入 `deepseek_harness` 的 Python 模块；不将 DSH Session/事件对象传递给业务核心。
- `EvalContract`、`BudgetGuard` 和 `PromotionGate` 由项目自身维护，未来可换 PydanticAI Runtime。
- 不把 `sdk-minimal` 的内置 Shell 当作安全沙盒；`cwd` 不是文件系统安全边界。
- M0 不需要 Next.js/FastAPI。先使用 CLI 及自动测试，减少无关工程量。

## 2.2 OpenCode Go 订阅使用策略（可选，不阻塞 M0）

**决策：模型仍固定为 DeepSeek V4.1 Flash；不进行模型横向选型。** 已有 OpenCode Go 订阅可优先用于 OpenCode Coding Agent 的编码、调试和测试任务，减少额外开发成本。**订阅能否作为 DeepSeek Harness 的模型 API 来源尚未验证**，不可把 OpenCode 客户端内可用等同于提供可供第三方调用的 API。

执行时按以下顺序处理：

1. 检查 OpenCode Go 当前官方订阅说明、可用模型、使用限额、认证方式及第三方客户端/API 访问条款，并记录查阅日期和官方链接。
2. 若官方明确提供兼容的第三方调用入口，且支持指定 DeepSeek V4.1 Flash，则在不提取客户端内部凭据、不模拟私有请求的前提下进行**可选** DSH 接入烟测：基本生成、工具调用、多轮会话和结构化输出。
3. 若未提供或不允许第三方 API 接入，则 **OpenCode Go 仅供 Coding Agent 开发**；E1 的 Runtime 实测继续使用 DeepSeek 官方 API `deepseek-flash`。
4. 若订阅包含的模型与 DeepSeek V4.1 Flash 不同，不替换既定 Runtime 模型，也不重新启动模型选型。
5. 记录订阅固定费用与本次 API 增量费用的区别。已有订阅不计为零成本 API 额度；只有可核实的调用额度才可用于预算抵扣。

**验收**：形成 `docs/opencode-go-access.md`，明确 `SUPPORTED / NOT_SUPPORTED / UNVERIFIED`、证据链接、限制与选定路由。该渠道失败或不可验证均不影响 E1–E5 的通过判断。

### 2.1 最小稳定接口

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

@dataclass
class RunRecord:
    run_id: str
    case_id: str
    candidate_id: str
    session_id: str
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
│   ├── hidden_cases/                # 本地私有、不要发送给候选 Agent
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
    ├── ADR-001-runtime.md
    ├── THREAT_MODEL.md
    └── TROUBLESHOOTING.md
```

其中 `fixtures/hidden_cases/` 应只供可信 EvalRunner 读取，真实代码仓库若需开源，公开的是示例开发测试，不是可被候选查看的正式隐藏题；私有真实测评集应独立存放，不随插件工作区挂载。

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
- 通过环境变量注入实验专用、低额度 API Key，不保存到 Git、日志或候选工作区。
- 显式传入彼此独立的绝对路径：`cwd` 为 disposable workspace，`dsh_home` 为 disposable Harness home。
- `sdk-minimal` 的 Session JSONL 存放在 `<dsh_home>/sessions/`。
- 为避免额外发送会话日志，创建并校验以下 Cordis patch（若所安装版本的插件 ID/配置不同，需先检查合并配置）：

```yaml
- id: session-log-deepseek
  config:
    enabled: false
```

- 测试中明确记录当前 Profile、合并后的插件树和安全配置。不要通过“修改工作目录”误以为完成了 Shell 沙盒隔离。
- **模型选型冻结**：默认仅走 DeepSeek 官方 API：`deepseek-flash`。若开发者已有 OpenRouter Key，可验证同一个 V4.1 Flash 的 OpenRouter 路由 `deepseek/deepseek-v4.1-flash`，这不是模型横评，也不是 GO 的必需条件。
- DeepSeek `deepseek-flash` 为服务别名，官方可更新其所指向的版本。Trace 必须记录模型请求 ID、Provider、可获取时的实际模型版本与验证日期，避免模型漂移污染后续实验。
- 若 DSH 默认 Profile 的 Model ID、API 参数与现行官方接口不兼容，先采用公开配置接口适配，不能因教程仍用历史 `deepseek-v4-flash` 而盲目沿用旧 ID。

## 5. 五个实验：步骤、用例、验收标准

### E1 — SDK 生命周期与 DeepSeek V4.1 Flash 接入（唯一主模型）

**目标**：确认 Python → DSH → DeepSeek V4.1 Flash → Python 的稳定性。**不开展任何低价模型选型，不增加额外模型作为通过前提。**

**步骤**：
1. 安装固定版本 SDK，使用官方 `sdk-minimal` 在隔离 home/workspace 做 Smoke，核对当前 SDK 对 `deepseek-flash` 的支持与配置方式。
2. 配置官方 DeepSeek API 的 `deepseek-flash`，调用成功后保存最终响应、Session ID、错误类型、实际版本（如可获得）及 SDK/Runtime 版本。
3. 要求返回本项目的 JSON Schema，使用 Pydantic 校验；如果 DSH 不能原生强约束，明确记录能力缺口，允许项目级验证/有限重试。
4. 调用一次 E2 的确定性工具 `skill_lookup`；真实检查工具调用事件而不是只看答案文字。
5. 运行 6 个小任务，记录延迟、输入/输出 Token、缓存计费（若有）、总费用与失败率。不需要任何其他模型。
6. 测试 401、429、5xx、超时、无效模型 ID 的错误分类与重试上限，使用 Mock 注入即可覆盖异常路径；谨慎避免制造实际付费失败请求。
7. 如果开发者已持有 OpenRouter Key，可以额外验证 `deepseek/deepseek-v4.1-flash` 同模型路由；不得为此延期 M0 或横向比较新模型。

**测试用例**：
- `E1-01`：简单问答，输出包含固定标识 `M0_SMOKE_OK`。
- `E1-02`：返回 JSON `{ "skill_id": "binary_search", "ready": true }`，由 Pydantic 校验。
- `E1-03`：一次工具调用的事件中确实出现 `skill_lookup` 且返回预期结构。
- `E1-04`：无效 Key / Model ID 产生明确有类型的错误，禁止静默切换模型。
- `E1-05`：预估超预算时自动停止后续调用。
- `E1-06`：重试失败不可无限循环，后台 Agent step 数及费用受到外层约束。

**验收**：DeepSeek V4.1 Flash 官方路由 3/3 连续 Smoke 成功；至少一次真实工具调用成功；JSON 结构经本项目 Pydantic 验证；配置错误明确暴露；能够查到或保守估算每个请求的用量与费用。**不要求第二个 Provider、第二个模型、复杂路由或自动模型回退。**

### E2 — 自定义教学插件及扩展能力

**目标**：实现一个很小的真实工具，而非只让 Agent 使用 Bash 读文件。

**插件规范**：`skill_lookup(skill_id: string) -> SkillInfo`，其中 `SkillInfo = {id, title, prerequisites, objectives, source_version}`。数据来自只读的 `fixtures/skills.json`，对未知 ID 返回明确的 not-found 结果。

**步骤**：
1. 阅读官方 First Plugin、Build a Tool 教程，用 `@deepseek-ai/cordis` 和 `@deepseek-ai/dsh-tools` 构造 TS 插件。
2. 按官方方法构建/安装插件，绑定 `sdk-minimal` 或其他适当 Profile；必要时为插件管理安装 pnpm。
3. 展示插件在实际 `ctx.tools` 注册后模型可见并可以调用，验证输入参数和输出 schema。
4. 重启 Runtime，确认插件可用；测试插件被移除后工具不存在（或输出明确插件状态），不残留重复注册。
5. 把工具调用事件导入项目 Trace 格式。

**测试用例**：
- `E2-01`：`binary_search` 返回指定前置知识。
- `E2-02`：未知技能返回已定义错误，不抛出非预期异常。
- `E2-03`：空字符串/错误类型被 schema 拒绝。
- `E2-04`：重启后插件行为与首次一致。
- `E2-05`：关闭或卸载插件后不再被 Agent 调用；若该机制依赖重启，记录这一限制。

**验收**：全部确定性单元测试通过；真实 Agent 工具调用至少 3/3 成功；插件扩展不修改 DSH 上游源码；记录开发耗时、调试路径及版本兼容问题。

### E3 — Session 持久化、恢复、隔离、轨迹收集

**目标**：证明可以把 DSH 作为学习会话执行层，但不依赖它做全部业务数据存储。

**步骤**：
1. 创建独立 `session_id` 与 home/workspace，发送第一条消息并完成落盘。
2. 关闭 Python SDK 进程；新进程中用 `resume_session(saved_session_id)` 恢复后继续交互。
3. 检查 JSONL 日志事件顺序、消息恢复、模型路由与工具事件、Token usage（若适配器提供）。
4. 检查未知、损坏、已占用 Session 的显式错误。
5. 用不同 home 启动两个实例，验证无法互相读取历史。
6. 用受控方式中断一次任务，检查断电/崩溃后恢复机制的实际保证范围。
7. 验证旧进程的 Shell 子进程状态并不因 Session 恢复而恢复；记录此限制。

**测试用例**：
- `E3-01`：保存 nonce，重启后能从历史上下文正确回忆。
- `E3-02`：无效 Session ID 不得默默新建 Session。
- `E3-03`：事件 `seq` 单调，能解析完整记录。
- `E3-04`：不同 DSH_HOME 的同名 ID 完全隔离。
- `E3-05`：中断后的恢复不产生虚假的成功报告。
- `E3-06`：泄漏扫描器在导出 trace 中找不到假密钥样本。

**验收**：正常关闭并恢复 3/3；事件结构可提取并映射到统一 `RunRecord`；失败/中断语义清楚；数据不会跨 home 混用。注意：Event-sourced replay 是历史重建，不保证重新运行 LLM 的字词级确定性。

### E4 — 新旧教学策略的配对评估（RSI 基础）

**目标**：建立将来 Improvement Engine 所需的候选对照实验能力。

**固定案例**：准备 20 个虚构学生错误诊断场景（例如二分答案的单调性误解、边界 off-by-one、忽略溢出、错误复杂度判断），其中开发集 12、保留集 8；不得把保留集直接放进 Agent Prompt。

**候选（两个候选使用同一个 DeepSeek V4.1 Flash 型号）**：
- `teacher_v0`：直接指出问题并解释。
- `teacher_v1`：先诊断误解，优先引导学生解释或构造反例，避免直接泄露完整解法。

**步骤**：
1. 把每个场景表示为 `EvalContract`，包含公开输入、隐含错误标签、必要动作、禁止动作和评分器版本。
2. 两个版本分别用独立、全新 Session 处理相同输入；固定模型、采样参数（如果可配置）、工具、知识来源和 Token 上限。
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

### E5 — 安全隔离、失败注入、回滚准备

**目标**：让将来生成的代码只在封闭测试环境运行，确认 DSH 默认权限不能绕过安全约束。

**两种完全不同的执行环境**：
1. **可信控制器**：Python/DSH 只运行受控的 smoke 与工具调用，使用低额度实验凭据；应尽量关闭不必要 Shell。特别警惕 `sdk-minimal` 默认 `danger-full-access`。
2. **不可信候选容器**：执行 Agent 生成的脚本和未来的 RSI 候选，不含任何真实密钥，默认禁网、非 root、只读根文件系统、CPU/内存/进程/超时受限，只挂载复制后的测试素材。

**独立 Docker 示例**（仅演示隔离思路，实际执行前检查 Linux/WSL2、镜像和权限）：

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

**测试用例**：
- `E5-01`：脚本尝试读取宿主环境中的假 API Key，结果不可见。
- `E5-02`：尝试外网连接失败。
- `E5-03`：尝试写出 `/work` 与 `/tmp` 之外失败。
- `E5-04`：无限循环或过量内存被资源/时间限制终止。
- `E5-05`：失败候选无法更改可信 `EvalContract` 和隐藏测试。
- `E5-06`：一次候选失败后控制器仍能启动下一次实验。
- `E5-07`：检查 DSH Profile 的权限与 session-log 上传设置，避免默认设置被误当成安全隔离。

**验收**：所有关键隔离测试通过；未发现真实凭据或私人目录暴露；安全文档明确指出：容器的强度取决于 Docker 主机与内核，文件沙盒也不自动约束网络；生产级隔离需后续单独审计。

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
- `experiment_id`, `run_id`, `case_id`, `candidate_id`, `session_id`。
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
- DeepSeek V4.1 Flash 单模型的 SDK 兼容性、失败率、费用/延迟统计；OpenRouter 同模型路由如未测试应注明非必需。
- 自定义插件安装与调用证据。
- Session 恢复与事件数据质量。
- A/B 配对的逐案例差分、变异性和失败例子。
- 沙盒攻击模拟结果、未关闭的风险。
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
- Live（仅人工显式开启）：官方路由、多模型、真实工具调用、真实持久化和配对实验。

推荐 CI 只自动执行离线测试；不把任何 API Key 或真实用户学习数据引入公共 CI。每个测试都要明确 Assert，不能只打印结果。

## 9. 里程碑、顺序与依赖

1. **T0：环境基线**：核实 OpenCode Go 订阅能否官方支持第三方 Runtime 调用并记录证据（不阻塞后续任务）；完成依赖锁定、隔离工作目录、配置脱敏、版本记录；把 `deepseek-flash` 锁为唯一默认模型；交付 `M0_RUNBOOK.md`。
2. **T1：SDK + 单模型调用**：完成 E1 DeepSeek V4.1 Flash 烟测、工具调用与 JSON 校验；交付 `dsh_adapter.py`。
3. **T2：Plugin**：完成 E2 `skill_lookup`；交付 plugin + E2 报告。
4. **T3：Session**：完成 E3 恢复/日志/错误；交付 Trace Normalizer。
5. **T4：Experiment Runner**：完成 E4 Mock/Live 配对评估与报告；交付 `EvalContract`/`comparison.md`。
6. **T5：Sandbox**：完成 E5 安全测试与威胁模型；交付 `THREAT_MODEL.md`。
7. **T6：决策报告**：汇总 GO/NO-GO 证据和后续 M1 架构 ADR；交付 `M0_REPORT.md` 和 `ADR-001-runtime.md`。

允许 T3、T5 和费用记录模块并行实现。任何一项 Live 测试因预算、网络或权限受阻时，先完成 Mock / 设计验证，明确写 `BLOCKED` 而不是跳过后判 PASS。

## 10. 框架选型 Go / No-Go 门槛

### GO（可作为 M1 主 Runtime）
必须同时满足：
- E1 **DeepSeek V4.1 Flash** 经官方允许的路由可靠调用；用量可估算，费用可限制。OpenCode Go 订阅接入不是 GO 条件。
- E2 自定义工具可通过标准插件接口实现，不修改 DSH 核心。
- E3 Session 重启恢复和事件记录能满足学习轨迹需要。
- E4 配对评估能持续运行，并产出可审计的 Trace、评分和差异报告。
- E5 通过外部沙盒安全测试；正式调用与候选代码隔离。
- SDK 版本兼容问题可通过锁版本或可维护的公开适配层解决。

### CONDITIONAL GO
只有非核心项目未通过，例如可选 OpenRouter 或 OpenCode Go 同模型路由异常、插件开发效率偏低、原生事件收集不完整但可通过外部记录补齐。必须列出阻塞条件、修复路径和实际增加的复杂度；不能无限期延后决策。

### NO-GO
出现以下任一重大失败：
- SDK/插件接口无法稳定使用，必须长期维护侵入式 Fork。
- 无法可靠恢复 Session、区分运行状态和错误。
- 不可信候选执行无法有效隔离，且没有可接受的外部沙盒。
- 任意任务可能无上限调用模型，无法通过外部机制停止/限额。
- 单人维护成本显著高于替代方案，且 DSH 的插件扩展价值无法验证。

## 11. 退路（Fallback Matrix）

| 问题 | 一级退路 | 二级退路 |
|---|---|---|
| DeepSeek 官方 `deepseek-flash` 接入异常 | 检查 DSH 公共 Provider 配置及 SDK 参数兼容 | 仅在必要时使用 OpenRouter 同模型路由；如 DSH 无法解决则选择替代 Runtime，不换模型 |
| Python SDK 接口不稳定 | 锁定可运行 SDK 版本，缩小 Adapter API 面 | DSH TypeScript Runner，通过 JSON-RPC / 自建本地协议与 Python 通信 |
| DSH Plugin 复杂度太高 | 教学工具先留在 Python 服务，通过受控桥接调用 | M1 改用 PydanticAI，DSH 留作 RSI 实验 Runtime |
| Event Log 不适合业务存储 | Python 独立 SQLite 学习数据和 Trace | 标准化事件采集插件，不直接依赖 DSH 内部 Session schema |
| 原生沙盒不够安全 | 独立 Docker Runner、只读输入与禁网 | 更强的隔离 VM/远程执行环境；M0 禁止执行不可信代码 |
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
- [ ] `M0_REPORT.md` 含 PASS/FAIL/BLOCKED、失败原因及证据路径。
- [ ] `ADR-001-runtime.md` 给出 GO/CONDITIONAL GO/NO-GO 决策和理由。
- [ ] 仍然需要人工判断的风险与待办清单。

**报告中绝不可出现**：“Agent 自我改进有效”“教学成绩优于 GPT”“DSH 安全可信”等未由 M0 实验证明的结论。

## 13. Coding Agent 执行指令模板

> 你正在实现 Autonomous Teacher 的 M0 DSH 技术验证。本文档是唯一的 M0 功能范围基线。
>
> 1. 首先核对官方 SDK/插件 API、安装版本和预览版破坏性变更；如与文档不同，以已安装版本为准，并在 `docs/M0_RUNBOOK.md` 记录差异。
> 2. 从环境基线、MockRuntime、统一 RunRecord 和 BudgetGuard 开始，实现离线单测；再执行需要付费的测试。
> 3. 每个 E1–E5 实验必须包含步骤、至少一个自动化 Assert、结果和错误证据；必须区分 PASS、FAIL、BLOCKED、SKIPPED。
> 4. 不实现 M1 教育产品，不私自更改评估标准，不执行未隔离的不可信代码，不在代码或日志里存放真实密钥。
> 5. 预算默认软上限 $3、硬上限 $10；没有有效预算守卫前禁止大规模 live 调用。
> 6. 结束时提交可复现代码、运行命令、测试报告及 ADR，并明确推荐：DSH GO、CONDITIONAL GO 或 NO-GO。不能用自我评价代替可检查的测试证据。

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

下列代码用于验证 SDK 的基本调用，不执行不可信代码。运行前创建空的 `/tmp/at-m0-workspace`，设置官方 API 凭据；`sdk-minimal.patch.yml` 应包含前述禁用 Session-log 上传的配置。注意：**这不是安全沙盒**，不能在里面执行来自模型的任意 Shell 代码。

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
    provider='deepseek-official',
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

- **Shell 默认危险**：`sdk-minimal` 的 Shell 对可见的宿主目录有广泛访问能力；仅设置 `cwd` 无法阻止读取其他路径。即使使用独立 Harness home，也不是文件访问隔离。
- **Session 恢复有限**：SDK 可以恢复历史事件，但已退出的 Shell、浏览器等外部进程不会随之恢复。
- **Replay 有多种含义**：事件日志可重新导出过去发生了什么；重新调用 LLM 仍受采样、模型版本和提供商行为影响，不提供字节级确定性。E4 必须使用新 Session 重跑并记录波动。
- **成本不能只算响应 Tokens**：要计入重试、上下文压缩、额外 Judge、服务商差异；`dsh_session_log` 是额外请求字段，官方说明它不消耗模型输入 Token，但涉及隐私/请求体大小，仍建议在 M0 关闭。
- **模型适配不能想当然**：以 DeepSeek 官方 `deepseek-flash` 实测为验收基础。第三方 Gateway 的兼容问题只在用户已提供现成 OpenRouter 配置时才需要处理。
- **M0 的评估不是教学实验**：一个离线 Teacher 赢了另一个离线 Teacher，只代表在这组固定测试案例/评分规则上更符合要求，不能证明更能帮助真人学习。
