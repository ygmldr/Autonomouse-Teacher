# Autonomous Teacher — M0 验证报告

## 最新状态 — 第五阶段独立审计（2026-11-14 UTC）

**当前冻结实现 `feb7118f9aff20c681cc651812b30315288080f1`（父 `ec1128b`；仅 9 文件：预算守卫插件 + 文档/README/runbook，`src/`/`tests/`/`config/`/锁/Gate/Adapter diff 为空）：非实现者独立复核确认第五阶段离线候选交付在其声明的范围内成立。** 独立重跑全量 pytest **326 passed**（含 89 专门子集，不相加）、stdio 账本 **148 passed**、Ruff PASS、wheel 构建（SHA `07fcb9e5…` 与 owner 一致）与 wheel-only 无源码安装 CLI/E1 API、真实 Cordis 插件 strict build + **8/8** registry、SDK strict rebuild（6 产物逐字节一致）与 **17 用例 SDK suite**、guard strict build（日志与 owner 逐字节相同）、以及 **guard 12/12 case + in-process 18/18 selftest** 全部通过；宿主 data-only 语义校验 guard **28/28**、SDK **25/25** PASS。**预算守卫是 logical-stream（pre-adapter）预留/结算 middleware，不是 provider 库内部每次 HTTP/wire/billable attempt 的控制；text-only 只是关闭 Files 路径的前提；broker 是 fixed-scope bookkeeping，`dispatch_allowed` 不是授权/Key 代理/provider usage 认证/真实账单上限；task22 中间件仍是离线候选，未接入生产 Runtime/真实 provider。** 一项低严重度**文档声明超出已测证据（V1）**已由 owner task31 文档纠错关闭（无代码变更、无新 SHA、未重跑 suite；见 [REVIEW_PHASE5 §6.1](<REVIEW_PHASE5.md>)；docs sha256 `1d0b62a2…`、errata sha256 `362dedb3…`）；真实模型/E1/E2/E3/E5、P03 人类授权、外部 watchdog、真实 usage/逐 billable step 记账仍 **BLOCKED**，整体 **DECISION PENDING**。

来源：[第五阶段manifest](<../artifacts/phase5-integration/manifest.json>) SHA `391767d3b073d239fded57299c5149d91130a9e476a53b525f4f22f4e69b646f`；[独立 REVIEW_PHASE5](<REVIEW_PHASE5.md>)；[reviewer raw/evidence](<../artifacts/reviewer-phase5/manifest.json>)；[RUNTIME_BUDGET_GUARD](<RUNTIME_BUDGET_GUARD.md>)。当前状态详见 §11。首轮 d5/146、phase2 c155/235、phase3 5df4f3b/241、phase4 f674403/326+SDK17 均保留为真实历史，不倒填。

## 第四阶段状态历史（2026-11-14 UTC）

**当前冻结实现 `f674403d12a6b51249b772090b7b004013d4ceb1`：非实现者独立复核确认第四阶段离线交付在其声明的范围内成立。** 独立重跑全量 pytest **326 passed**（含 89 专门子集，不相加）、stdio 账本 **148 passed**、Ruff PASS、真实 Cordis 插件 strict build + **8/8** registry、wheel 构建（SHA `07fcb9e5…` 与 owner 一致）与 wheel-only 无源码安装 CLI/E1 API、SDK strict rebuild（6 产物逐字节一致）以及 **17 用例 SDK suite**（`sdk_run_calls15 / synthetic_adapter_invocations16 / real_model_calls0 / http_calls0 / resume_pairs3 / dual_home_bidirectional true`）全部通过；owner 声明计数（`326 / 89子集 / 148重放 / 8 / 17`）与日志一致，不同 scope 不相加。**SDK fixture 是真实锁定 DSH 引擎 + 显式 synthetic `offline-test-only` provider，不是模型、不是 E1b/E2 Live、不是生产 Adapter；stdio broker 只是固定 scope 的 bookkeeping，不是授权/Key 代理/真实账单上限，task22 公开 `llm/stream` 预算 middleware 未实现、未接线。** 真实模型/E1/E2/E3/E5、P03 独立人类授权、外部 watchdog 与真实 usage/逐 step 记账仍 **BLOCKED**，整体 **DECISION PENDING**；生产 Gate/Adapter/默认 primary 路由未改。

来源：[第四阶段manifest](<../artifacts/phase4-integration/manifest.json>) SHA `bfea6fa1d4cb3d144879b784aeb76c73f1fee3ef0842034b37dba939e90a2df5`；[独立 REVIEW_PHASE4](<REVIEW_PHASE4.md>)；[reviewer raw/evidence](<../artifacts/reviewer-phase4/manifest.json>)。当前状态详见 §10。首轮 d5/146、phase2 c155/235、phase3 5df4f3b/241 及其 SDK keyless 子集均保留为真实历史，不倒填。

## 第三阶段状态历史（2026-11-13 UTC）

**当前冻结实现 `5df4f3bdbecdf0683533ef7f0a176513713436cd`：独立241 Python PASS（含89专门子集，不相加）、插件8 PASS、Ruff/wheel/无源码真实安装CLI与E1 API脚本PASS。** 同原1cc SDK binary配精确RO40c34 native cache，无preload且scratch noexec不变，已实际initialize-ready、观察registered schemas[]、graceful0及负握手cleanup。exact本地OCI manifest62d/config56db的独立OS命令与candidate元数据target实测通过。**这些是限定新增子集，不是完整H1/Session/模型/Runner.run生命周期或跨机load验证；整体仍DECISION PENDING / Live BLOCKED。**

来源：[第三阶段manifest](<../artifacts/phase3-integration/manifest.json>) SHA `f4021242729f03ffe8ed86bb783d88192515e03f80ea7185b08d4c910d03df60`；[独立REVIEW_PHASE3](<REVIEW_PHASE3.md>)；[reviewer新raw](<../artifacts/reviewer-phase3/manifest.json>)。当前状态详见§9。首轮d5/146、phase2 c155/235及旧无cacheSDK BLOCKED均保留为真实历史，不倒填。

## 第二阶段状态历史（2026-11-13 UTC）

**最新实现 `c155789557e525925435e7f8a8bf573856d80311`：独立235 Python PASS（含89专门E1-02子集，不相加）、8插件PASS、严格构建/独立wheel重建/真实安装CLI与新增结构API脚本PASS。** E1-02离线状态由首轮NOT RUN变为本轮实测PASS；真实模型JSON仍BLOCKED。第三方无KeySDK初始化已尝试但native binding阻塞，只有version/config与失败cleanup等通过；公开预算hooks只是静态可行性，桥未实现。整体仍 **DECISION PENDING / Live BLOCKED**。

新证据：[阶段二manifest](<../artifacts/phase2-integration/manifest.json>) SHA `c512d653f62b6604903890579ea85da48b2fef876f3b087ea96311e7c5c2d94b`；[独立阶段二审计](<REVIEW_PHASE2.md>)及[本轮reviewer原始证据](<../artifacts/reviewer-phase2/manifest.json>)。详见§8。

> **以下§1–7保留首轮d5db491的历史范围、计数和NOT RUN事实；§8保留第二阶段c155789历史；§9保留第三阶段5df4f3b历史；§10保留第四阶段f674403历史。最新第五阶段状态见§11。不把新结果倒填到旧执行中；各阶段 REVIEW、manifest与原始产物保持原样。**

## 1. 决策与执行范围

**DECISION PENDING；所有 Live 验收保持 BLOCKED。** 本报告不是 GO、CONDITIONAL GO 或 DSH 技术 NO-GO。已完成并独立复验离线设施；没有执行模型调用，没有注入/读取真实 API Key，没有修改 DSH 上游。

- 基线：[v0.4 任务书](<Autonomous_Teacher_M0_v04.md>)；实际执行/审计日期 **2026-11-13 UTC**，不能把任务书的 2026-11-14 日期当成实验或价目采样日期。
- 实现冻结 SHA：`d5db491bf3299c14b6af98f5cbe952ce56a1a991`。报告/审计文档后续归档提交与实现 SHA 分开记录。
- 来源锚：[manifest](<../artifacts/integration/manifest.json>)，SHA-256 `711b02b4da8f066ed8483aca69a18e2eec0f11067e0d24a514a8c5dce9d19cc2`；[摘要文件](<../artifacts/integration/manifest.sha256>)。
- 非实现者独立审计：[REVIEW](<REVIEW.md>)。审计者逐项核对 74 个公开源/输入文件在工作树、冻结 Git 对象和 final-stage 三者一致，核对 14 个原始产物摘要，并独立复跑最终测试。任何实现/依赖/配置变化都须新 SHA 与重新验证。

阻塞**不只是缺少人工批准**：[HarnessAdapter](<../src/autoteacher_m0/runtime/dsh_adapter.py>) 的 Live 映射目前不可达；独立授权服务/凭据边界、可信受限部署、真实 SDK/usage 接入、每个可计费步骤预算约束和外部 watchdog 仍待工程实现及验证。编辑批准文件、设置环境变量或传 `--live` 不会解锁。

## 2. 实测基线与复现

| 项目 | 已核对版本 / 状态 |
|---|---|
| Python / uv / Git | 3.11.15 / 0.11.6 / 2.43.0 |
| 项目 SDK / runtime-bin | deepseek-harness-sdk **0.2.2rc2** / runtime-bin **0.2.2rc2**；已安装，未启动 Runtime |
| 插件官方 ABI | npm DSH/dsh-tools **0.2.1-rc.2**，Cordis **4.0.5**；与 wheel Runtime 是不同发行版本，组合未测 |
| Node / TypeScript | 22.23.2 / 5.9.3；strict，skipLibCheck=false |
| Python 测试与校验 | pytest 9.2.0、pytest-asyncio 1.5.0、ruff 0.17.5、Pydantic 2.14.3/core 2.50.4 |
| 隔离引擎 | Podman 4.9.3 / crun 1.14.1；Linux/LXC，本地公开 runtime rootfs |
| 依赖锁 | [uv.lock](<../uv.lock>) SHA `db189d41886a425480ef21e92e29935f5af078d5f67786541b1fba86d5d29155`；[npm lock](<../plugins/skill-lookup/package-lock.json>) SHA `8ed939c93d14fecf838a35e0122717b931f5bdb7d55af7023a5cb1ef3d3e1c73` |
| 发行 Git commit | 观察到的上游 master 不冒充安装发行 commit；静态来源与差异见 [Runbook](<M0_RUNBOOK.md>) |

rootfs SHA `b4ca1b4f7279842bae18736a735469a575a7243dec0edabbc4d8e051c5dc68e8`；Python deps SHA `e07729d7997944417b1c25531749b3e6e5e34aa4248f01dc8f370282082ecb98`；plugin deps SHA `026a7a156830f102cea936bd6836d8f675d36f650ad5935cceb332f7ade292d2`，算法与逐 argv 命令在 manifest；审计者独立重算匹配。本地 rootfs 不是已发布的不可变镜像。

所有项目代码/测试/构建仅在无凭据、禁网、非 root、只读输入/rootfs、cap-drop/no-new-privileges、有 CPU/内存/PID/时间限制的容器运行；宿主只用可信系统工具做哈希、Git、依赖准备和证据收集。审计独立复跑没有宿主可写 mount。Python 使用 512MiB、pids32、CPU1；插件 compiler 使用有界 1GiB/Node heap768MiB，不放宽 candidate runner 资源策略。

只在上述已核验边界内执行的命令语义：

```sh
python -B -m pytest -p no:cacheprovider tests/unit tests/integration -q
python -B -m ruff check --no-cache .
node --max-old-space-size=768 node_modules/typescript/bin/tsc -p tsconfig.json
node scripts/copy-fixture.mjs
node --test test/plugin.test.mjs
# 安装验收在独立wheel-only容器：真实uv安装到/work/site后调用其console entrypoint
# inspect-runtime / smoke --mock / paired --mock / report --experiment <id或latest>
```

完整可重放容器 argv、输入路径和安全参数见 [manifest commands](<../artifacts/integration/manifest.json#L317-L623>)；独立重放方法见 [REVIEW](<REVIEW.md>)。不能把普通宿主 `pytest` 或改 cwd 当作等价隔离。

## 3. 原始证据与独立复验

| 检查 | owner 冻结结果与证据 | 非实现者独立结果 |
|---|---|---|
| Python unit + integration | [final-tests](<../artifacts/integration/final-tests.log>)：146 PASS，exit0 | **146 PASS，0 skipped，0.69s，exit0**，含实际外部OS负向用例 |
| 全量 Ruff | [final-lint](<../artifacts/integration/final-lint.log>)：PASS | `All checks passed!`，exit0 |
| 插件 strict tsc + fixture + 官方 registry | [final-plugin](<../artifacts/integration/final-plugin.log>)：build exit0，8/8 PASS | **严格构建exit0 + 8/8 PASS，0 skipped，exit0** |
| wheel 构建 | [final-build](<../artifacts/integration/final-build.log>)：hatchling exit0；[wheel](<../artifacts/integration/final-wheel/autoteacher_m0-0.1.0-py3-none-any.whl>) SHA `8258fc8a8d63da1b8e411bf1294573f62f29be587b86ee17e85359e22e8193ff` | 核对原日志/产物与冻结摘要；没有冒称独立重建 wheel |
| 安装后真实 CLI | [final-installed](<../artifacts/integration/final-installed.log>)：uv真实安装，四类CLI全部exit0 | **同一wheel重新真实安装成功；inspect/smoke/paired/report(id+latest)全exit0**；cwd/work，无source挂载/源码PYTHONPATH |
| 外部 OS 负向 probe | [OS日志](<../artifacts/security/os-probe.log>)与[探针](<../fixtures/sandbox/exercise.py>) | 单独显示输出再次PASS：uid65534、memory512MiB、pids32、CPU1、caps0/nnp1、假敏感路径不可读 |
| 资源滥用与恢复 | [PID](<../artifacts/security/resource-pids.log>)、[内存](<../artifacts/security/memory-final.log>)、[timeout](<../artifacts/security/state-timeout.log>)、[恢复](<../artifacts/security/resource-recovery.log>) | 审计者交叉核读原始证据，**未独立重跑全部资源攻击**；不混入独立146计数 |

146 Python 与 8 Node 是不同套件；单独重跑 OS 的 1 PASS 与 Python 146 中该例重复，不累计成额外覆盖。测试耗时不是模型延迟。独立工具 job/具体结果、修复闭环与容器清理确认在 REVIEW；owner 日志不是独立执行日志的别名。

## 4. E1–E5 验收矩阵

PASS 均按表中限定范围，BLOCKED 是强制证据未具备而非自动判技术失败。未运行不算 PASS。

### E1 — SDK / 固定主模型：整体 BLOCKED

| 用例 | Offline/Mock | 获批主渠道真实验收 |
|---|---|---|
| E1-01 3次smoke | Mock 3/3 PASS，非SDK调用 | BLOCKED |
| E1-02 JSON/Pydantic结构 | NOT RUN：有Mock JSON响应分支和已安装Pydantic，但未见专门E1-02结构校验回归；其他JSON报告测试不替代此项 | BLOCKED；没有模型JSON响应或真实结构验收 |
| E1-03 真实工具 | 官方离线registry另见E2，不冒充模型发起事件 | BLOCKED |
| E1-04 错误分类/无fallback | HTTP形状故障注入、固定路由拒绝逻辑PASS | BLOCKED；真实401/429/5xx/无效型号未测 |
| E1-05 预算前置 | 预留、费用、cap、并发/持久scope组件PASS | BLOCKED；真实SDK dispatch尚未接线 |
| E1-06 timeout/steps/retries | 项目预算重试/step逻辑及外部rootfs deadline有证据 | BLOCKED；SDK隐藏steps、Live总watchdog未实现验证 |
| E1-07 route溯源 | mock记录明确route=mock，配置拒绝未批路由 | BLOCKED；真实请求ID/实际模型版本未采集 |

E1a 的离线基础部分不等于 E1a 全部通过；E1b 完全未运行。Adapter 唯一 SDK import 被不可达门控保护；安装/静态映射/fake Result 不是 H1 的真实生命周期证据。

### E2 — 插件：离线设施 PASS，整体 BLOCKED

| 用例 | 已执行证据 | 未满足的严格验收 |
|---|---|---|
| E2-01/02 固定技能/未知ID | genuine official registry PASS，确切结构/渲染/事件 | 模型3/3真实调用BLOCKED |
| E2-03 类型/空串 | wrong type/missing由native schema拒绝；空白由项目ToolArgsError拒绝 | **native wire接受空白**，DSL无minLength/pattern，不能写成原生schema拒空PASS；需维护者判断精确标准差异 |
| E2-04 重启 | fiber restart×3与两个新OS进程registry一致PASS | full DSH Runtime/profile重启未测 |
| E2-05 卸载 | dispose后get/schema/prompt无工具、dispatch UNKNOWN_TOOL、remount无重复PASS | CLI profile安装/移除与SDK-wheel组合未测 |

实际使用官方 `defineTool/Context/ToolRuntime`，非手写 ABI shim。插件绑定 ABI 0.2.1-rc.2，不能假定与 SDK-wheel0.2.2rc2 已验证兼容。无上游修改。详见 [插件证据](<PLUGIN_NOTES.md>) 与 [结构化摘要](<../plugins/skill-lookup/evidence/offline-summary.json>)。

### E3 — Session：Mock设施 PASS，真实DSH整体 BLOCKED

| 用例 | 已执行范围 | DSH真实状态 |
|---|---|---|
| E3-01/02 恢复/错误ID | 项目Mock JSONL重载和错误ID行为PASS | BLOCKED；真实进程重启恢复3/3未测 |
| E3-03 事件映射 | project envelope/fake SDK-shaped值规范化PASS，usage缺失保留None | BLOCKED；实际DSH事件/usage字段未核 |
| E3-04 同ID不同home | Mock API双向nonce namespace PASS | BLOCKED；真实DSH正常API命名空间未测 |
| E3-05 中断语义 | fake finish_reason不冒成功的包装逻辑PASS | BLOCKED；真实SDK中断/恢复未测 |
| E3-06 Trace脱敏 | JSON/SQLite/键/假哨兵回归PASS | 不保证识别任意未知秘密；真实DSH导出未测 |

E3 是正常 API 逻辑隔离；即便将来通过，也不能推导恶意代码读绝对路径受限。外部容器的文件系统证据归 E5。

### E4 — 配对评估：公开Mock PASS，整体 BLOCKED

| 用例 | 已执行范围 / 状态 |
|---|---|
| E4-01/02 | 固定同输入Mock可重复；两策略20×2 fresh runtime/session/run，PASS |
| E4-03 | 故障/无效grader返回EVAL_ERROR、score=null，不用0掩盖；失败pair不造delta，PASS |
| E4-04 | 确定性完整答案负例LEAK；片段/歧义NEEDS_REVIEW，PASS；不是语义完备证明 |
| E4-05 | 两臂逐调用usage与synthetic成本均记录，PASS；无真实账单 |
| E4-06 | API输入最小化PASS；真实隐藏标签/评分器保密部署NOT RUN，不能由Python对象分离或公开测试容器推导 |
| Live至少6对与复测变异性 | BLOCKED；无模型采样/随机性证据 |

### E5 — 安全：外部rootfs部分实测PASS，整体 BLOCKED

| 用例 | 实际覆盖与状态 |
|---|---|
| E5-P01/P02 | 指纹/变更导致阻断逻辑PASS；审计完整源快照匹配；并非部署可信基线已获人工批准 |
| E5-P03 | MD/env/flag均不能解锁的逻辑PASS；**独立不可伪造的人类授权服务/受保护部署未实现，BLOCKED** |
| E5-P04/P05 | runner显式env/公开输入/无socket等逻辑与rootfs probe有证据；真实有凭据控制器的合并工具白名单、最小注入与流向BLOCKED |
| E5-01/02/03 | 独立rootfs实际负向probe PASS：假Key/已知跨home假日志/假私有标签不可读；外网失败；非scratch写入失败 |
| E5-04 | security实际PID、cgroup OOM kill、Podman deadline证据PASS；审计者核读。不是Live watchdog已完成 |
| E5-05 | rootfs假私有标签不可见有证据；真实私有评分源/策略部署与权限仍NOT RUN |
| E5-06 | 新容器scratch无旧状态、恢复探针PASS；不证明每种可信控制器状态完整 |
| E5-07 | 实际合并DSH权限/危险Shell禁用/session-log上传关闭BLOCKED；配置文件本身不是运行证据 |
| E5-08 | 代码/依赖/配置变更关闭gate的逻辑PASS；外部可信部署/再准入未实施 |
| E5-09 | rootfs socket/敏感挂载不可见；runner无继承env/危险flags/cleanup负向回归PASS；image-based runner OS执行仍BLOCKED |

[威胁模型](<THREAT_MODEL.md>) 清楚区分上述外部 launcher 与未运行的 [image runner](<../src/autoteacher_m0/security/docker_runner.py>)/[Dockerfile](<../Dockerfile.m0>)。registry受权限阻塞、无本地镜像；不扩大权限或改成宿主执行补齐。命名空间/kernel/LXC/engine属于TCB，不能宣称生产级绝对安全。

## 5. Mock 配对结果、usage 与费用

来源：[最终JSON](<../artifacts/integration/final-public/experiment.json>)、[SQLite](<../artifacts/integration/final-public/experiment.sqlite3>)、[比较报告](<../artifacts/integration/final-public/comparison.md>)。这批 owner 产物由冻结 manifest 关联；审计者的独立安装运行生成了不同UUID的新批次，观察同样结构与数值。

| 指标 | 结果及限定 |
|---|---|
| 数据 / evaluator | public-mock-v1 / m0-eval-v1；20公开虚构案例，12开发+8公开模拟保留，不是私有隐藏集 |
| 运行 | 40个独立run/session，20对，40 SCORED；固定脚本，不是模型 |
| 两策略得分 | 每例v0=1、v1=1、delta=0；12/12开发、8/8模拟保留均可比 |
| usage | input 13,252，output 8,532，**synthetic计量单位**，非供应商tokenizer/模型用量 |
| 成本 | API/model调用0，因此此次增量API账单$0；synthetic账本$0.030316，mock-price-v1，不是实时DeepSeek价格 |
| 模型元数据 | model仅标签deepseek-flash，route=mock，SDK/Profile NOT_USED；实际模型版本/请求ID不存在 |
| 来源字段 | 产物git_sha=UNRECORDED保持原样；不倒填历史，由manifest关联本批冻结证据 |

成本默认软$3/硬$10、每call硬$0.20、最多50requests、任务8steps/1retry、累计250万输入/60万输出在项目组件测试中可核对；更严格case cap生效。失败/缺usage不当0，known fee不丢失，actual total bill不重复加费，超预留如实记账后阻断；固定SQLite scope覆盖跨进程/重启/route累计。但 Live dispatch、真实价格/计费reasoning/上下文压缩/Judge与内部steps没有接入，**不能宣称已限制供应商真实账单**。订阅费不抵扣未证明的API额度。

固定脚本全分/零差分仅证明配对/评分管线；不能声称teacher_v1更优、真人学习增益或RSI有效。真实语义盲审、保留集治理、真实Live配对尚未做。

## 6. 渠道分别报告

| 渠道 | 角色 | 当前状态 |
|---|---|---|
| 官方 deepseek-official / deepseek-flash | 设计默认primary | BLOCKED；未批准/部署/调用，实际型号与版本未验证 |
| OpenRouter / deepseek/deepseek-v4.1-flash | optional，未启用 | NOT TESTED；不替代官方结果，不作为降级的独立理由 |
| OpenCode Go | optional开发订阅渠道调查 | 第三方API接入UNVERIFIED；没有客户端凭据提取/私有协议模拟；专项接入调查文档尚未交付 |

没有路由切换或Agent自批。未来人类事前批准新主渠道后，须确认指定模型并在该渠道完整重跑E1与受影响E2/E3/E4，不沿用其他渠道PASS。证据见 [路由记录](<ROUTE_DECISION.md>)；可选渠道不影响尚未满足的强制门槛，也不单独产生CONDITIONAL GO。

## 7. 缺陷闭环、残余工作与恢复条件

审计发现的 quoted-JSON/SQLite索引/字典键三项脱敏缺陷均由foundation修复；Lead发现known fee丢失由evaluation修复；guard生命周期缺口补持久scope账本；cleanup任意rc1被视成功由security改为独立engine absence确认。最终独立测试覆盖修复，详情/文件位置/修前证据限定见 [REVIEW](<REVIEW.md>)。没有让审计者代改实现。

**优先级与责任边界：**

1. **未来控制器/安全owner + 人类维护者**：实现独立授权与受保护凭据边界、冻结完整不可变清单、确认实际profile/tool registry/session-log、禁止有凭据进程import/exec动态候选；MD不是权限开关。
2. **runtime/accounting owner**：验证真实SDK生命周期、事件/usage、model/request ID；将持久账本接入每一个可计费step/retry/压缩/Judge，固定预算scope/价格/完整context/output上界；实现外部watchdog与进程树终止，供应商低额度凭据作第二道限额。
3. **plugin/runtime owner + 维护者**：验证两个发行版本真实组合与profile装卸；处理E2-03原生非空schema精确差异，不能悄改任务书门槛。
4. **security owner + 维护者**：准备独立验证且digest固定镜像，重跑image runner与Dockerfile部署负向测试；真实私有评估源/评分器/控制策略不得进入候选可见面。
5. **人类维护者**：完成真正安全审查、批准具体SHA/config/命令/route，另受控会话亲自注入低额度可撤销Key；此时也只能启动补充验收，不因批准自动将结果改PASS。
6. **实验执行者**：在获批primary完成全部E1–E5必需证据及真实费用，按渠道分别保存；不满足继续BLOCKED/DECISION PENDING。独立审计后才能重议决策。

原始artifact目录被Git忽略，须维护者另行完整保留manifest、输入锁/快照、rootfs/依赖来源、原始日志/产物与摘要；只有文档没有原始证据不算可复现归档。文档入口由foundation后续task9更新，不改变本报告冻结实现结论。

**当前可接受交付：可安装的离线验证设施、真正官方ABI插件的离线证据、Mock配对/持久化/预算组件与有限外部隔离证据。当前不可交付承诺：可安全直接开Live的DSH控制器、DSH选型GO或真实教学效果证明。**

## 8. 第二阶段：E1-02新实现与SDK无Key诊断（独立task13）

### 来源、环境与计数

- 本轮冻结实现 `c155789557e525925435e7f8a8bf573856d80311`，中间E1-02实现为 `c7bfdc1becdc006eb55a7da527c30b3bdd235ace`。二者与首轮 `d5db491...` 分别归档，首轮146+8与当时E1-02 NOT RUN不改写。
- [新manifest](<../artifacts/phase2-integration/manifest.json>) 自身SHA `c512d653f62b6604903890579ea85da48b2fef876f3b087ea96311e7c5c2d94b`，82项源/输入在工作树/归档/commit一致，20项owner产物摘要一致；审计者独立核验，并保存自己的全新日志/产物。
- rootfs本轮实际SHA **`25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0`**。首次keyless bind自动增加空/probe目录；独立确认其为空且仅排除此目录精确恢复首轮b4ca摘要。不删除/伪造环境，旧摘要不冒充当前实际值。Python/plugin deps与首轮一致。
- 仍采用无Key禁网nonroot/read-only/cap0/nnp/noexec tmpfs与有界资源的Podman；没有宿主项目执行或生产Gate放行。

| 本轮独立执行 | 结果 | reviewer新证据 |
|---|---|---|
| 全unit+integration | **235 PASS、0 skipped、0.88s、exit0**，含OS负向probe | [tests](<../artifacts/reviewer-phase2/tests.stdout.log>) |
| 专门E1-02 | **89 PASS、0.25s、exit0**；89包含于235，不能与全量相加 | [dedicated](<../artifacts/reviewer-phase2/dedicated_e1_02.stdout.log>) |
| Ruff / standalone结构probe | All checks passed / 11类无效vector与成功、retry、耗尽断言PASS | [lint](<../artifacts/reviewer-phase2/lint.stdout.log>) / [probe](<../artifacts/reviewer-phase2/probe.stdout.log>) |
| 插件strict tsc+fixture+official registry | 构建exit0、**8/8 PASS**，不代表模型发起工具调用 | [plugin](<../artifacts/reviewer-phase2/plugin.stdout.log>) |
| 独立wheel重建 | 容器tmpfs生成，SHA **`89768d4769795a09dbcc9405def464796aec40ee5fc0faac68a756790c2ac8f7`**，与owner新wheel相同 | [build](<../artifacts/reviewer-phase2/build.stdout.log>) |
| 新wheel真实uv安装 | cwd/work、无source挂载/源码PYTHONPATH；inspect/smoke/paired/report(id+latest)与installed E1Output API/脚本均通过 | [installed](<../artifacts/reviewer-phase2/installed.stdout.log>) / [E1安装证据](<../artifacts/reviewer-phase2/public/e1-02-installed.json>) |
| 独立补充对抗断言 | strictbool/escaped duplicates/byte-before-parser/safe error/retry/no injection PASS；不是新增pytest计数 | [adversarial](<../artifacts/reviewer-phase2/adversarial.stdout.log>) |

### E1-02当前准确状态

[严格实现](<../src/autoteacher_m0/runtime/structured_output.py>) 与89专门测试不再是只存在的Mock JSON分支：固定skill=`binary_search`，StrictBool拒绝整数1/1.0与字符串，且ready必须true；extra forbid、重复解码键拒绝、仅单个完整JSON、4KiB UTF-8 byte上界、nonstandard constant/坏shape/无效边界拒绝，错误固定INVALID_OUTPUT且不保留输入detail或异常链。独立探针还证明多字节超界在parser前被拒。

本地Mock缺省不retry，只对成功Mock响应的INVALID_OUTPUT允许一次retry；成功不继续、执行/安全/认证/超时错误terminal；fixtures只收tuple字符串，不收任意Runtime/request/record/factory。已独立验证。**此为无模型的结构校验与本地retry，不是SDK/provider重试或付费预算桥。** E1-02 offline PASS-new-increment，获批主渠道真实E1-02仍BLOCKED。

### 第三方SDK无Key生命周期新事实

[task11报告](<SDK_OFFLINE_PROBE.md>) 已完整核读并独立原样重跑probe；[独立raw log](<../artifacts/reviewer-phase2/keyless.stdout.log>) 与[语义摘要](<../artifacts/reviewer-phase2/keyless-semantic.json>) 显示：

- native exe version0.2.2-rc.2/config dump exit0，12项disabled与upload=false合并断言通过；是**该无Key诊断profile的config证据**，不是生产安全registry/实际工具加载PASS。
- `DeepSeekHarness.start()`确实尝试initialize，但runtime host preparation发生 `No usable native binding found for node-addon-require-builtin-linux-x64-gnu (auto)`，TransportClosedError、runtime1；**初始化BLOCKED**。
- failed-start _proc清空、线程退出、waitpid无children、幂等close与missing-bin FileNotFoundError负例PASS。正常初始化后graceful shutdown、maxTokens无效握手、实际registry未到达。
- 外层诊断exit0只表示诊断断言完成；summary仍为 **BLOCKED-initialize-cleanup-PASS**。不能称H1/E1a或真实Session通过。没有run/Session/prompt/model调用，没有改生产Adapter/Gate。
- attempts压缩为[Object]，根因未区分noexec/EACCES/缺payload/缺依赖/ABI。只读native cache是未验证方向，不以放宽隔离来绕过。

### 预算公开hook增量与仍可离线完成的工程

exact0.2.2-rc.2原始tar/source静态核实 `llm/stream` 确为pre-adapter waterfall，`agent/pre-step`可reject，compaction独立走全局stream。但DeepSeek Files stale-ID retry可在同一stream内再次POST，request-field extension prepare异常只omit而非fail-closed、accept在POST后且吞错。**静态可行性不是已实现的逐计费attempt预算桥**；Python后置notification、RPC/idle timeout也不能替代。

后续仍可在无Key环境推进：独立定位exact native binding blocker并验证不放宽权限的兼容方案；实现显式offline-test-only provider驱动真实SDK/RPC/Session/工具/恢复；实现并确定性测试同scope预算桥的reserve-before-dispatch、拒绝单调性、重试/压缩/Judge/reentry/concurrency/no-usage/crash结算及transport上界。全history/tooloutput text-only闭包尚未实现验证，不能因初始prompt纯文本就认为Files路径已关闭。

新公开Mock仍20×2、synthetic input13,252/output8,532、synthetic$0.030316、API/model调用0，不能把三轮样本或测试重跑相加成真实模型用量。参考 [本轮比较](<../artifacts/reviewer-phase2/public/comparison.md>) 与 [独立审计](<REVIEW_PHASE2.md>)。所有独立授权/可信控制器/真实usage/总watchdog/image runner/私有评估权限/强制Live门槛仍适用，**DECISION PENDING保持不变**。

## 9. 第三阶段 — 精确native只读cache与本地OCI独立验收

### 新基线与实际覆盖

本轮实现 **`5df4f3bdbecdf0683533ef7f0a176513713436cd`**；[manifest](<../artifacts/phase3-integration/manifest.json>) SHA `f4021242729f03ffe8ed86bb783d88192515e03f80ea7185b08d4c910d03df60`。84项源/输入三方逐文件匹配，31项owner产物摘要匹配；Runner/Gate/Adapter与模型代码未变，Git范围内仅6个local-pin测试、Dockerfile状态注释和文档增量。首轮及phase2历史不倒填。

| 独立实际执行 | 结果 | 新raw |
|---|---|---|
| exact OCI image中全量Python | **241 passed in1.67s，0 skipped，exit0** | [tests](<../artifacts/reviewer-phase3/tests.stdout.log>) |
| 专门E1-02 | **89 passed in0.26s**，包含在241中，不相加 | [dedicated](<../artifacts/reviewer-phase3/dedicated_e1_02.stdout.log>) |
| Ruff/结构脚本/Node插件 | lint和E1 probe断言通过；共享Node rootfs严格构建+官方registry **8/8 PASS** | [lint](<../artifacts/reviewer-phase3/lint.stdout.log>) / [plugin](<../artifacts/reviewer-phase3/plugin.stdout.log>) |
| wheel/真实安装 | exactimage中tmpfs重建wheel仍SHA **89768d4769795a09dbcc9405def464796aec40ee5fc0faac68a756790c2ac8f7**；无源码挂载、cwd/work的真uv安装后四类CLI、report双selector、E1包API/脚本全过 | [build](<../artifacts/reviewer-phase3/build.stdout.log>) / [installed](<../artifacts/reviewer-phase3/installed.stdout.log>) |
| SDK exact四成员与新ROcache启动 | 独立SEA匹配4equal+summaryPASS；最终无preload实际ready、registered schemas[]、graceful0、负握手/缺binary清理PASS | [exact proof](<../artifacts/reviewer-phase3/native_proof.stderr.log>) / [SDK语义](<../artifacts/reviewer-phase3/sdk_native-semantic.json>) |
| 旧无cache差分control | initialize仍BLOCKED/cleanupPASS，历史未改写 | [control](<../artifacts/reviewer-phase3/sdk_unseeded_control.stdout.log>) |
| exactimage OS负向命令 | 手工审核后literal engine CLI exit0，独立ps查询0/空 | [image OS](<../artifacts/reviewer-phase3/image_os_negative.stdout.log>) |
| candidate元数据target/OCI save | 本地candidate五条指令重建同manifest/config；另独立无压缩save核manifest/config/layer字节 | [candidate build](<../artifacts/reviewer-phase3/candidate_metadata_build.stdout.log>) / [OCI check](<../artifacts/reviewer-phase3/oci-content-check.log>) |

共享rootfs仍 **25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0**、Python deps仍e077、Node deps仍026a；独立Python-only clone当前树为 **e680bbe32f75253b87bd5123c0327272d1c46d80d166125f5fdee04e54579d7f**。二者与原导入raw tar/OCI layer **aed8d7ef3f3c7fbabb601ed99d5e705e39dc1f779c8486f1865e340dfba94641**是不同对象，不能混称同一rootfs身份。native stage整树归一化SHA c063c129475eb14267de957e3cc9eec30f425fe1b44d004a1a977d1b5e665ef3。详情见[阶段三审计](<REVIEW_PHASE3.md>)及[reviewer manifest](<../artifacts/reviewer-phase3/manifest.json>)。

### 新通过的SDK启动子集与仍未通过的H1/E1/E3

仍使用原exe **1cc41d5a8745a5b9d47c8604e44f23eb8af2d8ca02b2afa0be101d5f71be6ea4** / SDK/runtime wheels0.2.2rc2，未换系统DSH。独立在该SEA exe中执行只读matcher，确认loader实现、loader metadata、native metadata与native payload四个成员与官方0.1.9包逐byte一致；native为295392 bytes、SHA **40c34d27d8339e246a8f7415a06152935496cdc06555ea8fce0e052011acc70f**。这不是仅版本相等或整个binary Git build commit已知。

使用原loader公开 `NARB_NATIVE_CACHE_DIR=/probe/native-cache` 指向匹配、0444、只读挂载的payload；保留原hash/ABI校验，无dlopen/模块解析patch，无可写可执行mount。最终成功probe没有NODE_OPTIONS/preload，实际mountinfo保留/tmp与/work noexec。SDK初始化握手ready和真实registered-definition observer的schemas[]已显式断言，正常close原runtime exit0，线程/子进程清理及maxTokens0 JsonRpcError负例通过。早期无cache失败日志不改写；新差分control也仍失败。task15详细mapping-error诊断与本轮exact-cache成功是具体配置增量，不泛推所有ABI/权限问题。

**因此SDK keyless startup/registered-definition/close子集从受阻变为新配置实测PASS；完整H1/E1a、真实模型、Session创建/恢复、per-agent resolved ToolSet、生产Adapter与有凭据部署仍未执行/批准。** schemas[]不证明另一个profile或实际Session的工具权限；sdk-minimal底层danger-full-access标签也未被本次诊断提升为可信。见[SDK_NATIVE_DIAGNOSTIC](<SDK_NATIVE_DIAGNOSTIC.md>)。

### 本地OCI关闭的缺口与NOT RUN边界

真实执行qualified manifest为 **localhost/autoteacher-local-oci@sha256:62d3569ec38e27ed16fa3147515c1c78d993bb7df831cc1fe29811f3fe64667b**，config ID为56db1e2ad5ab29d3f39304d4fc9d0584d90e6bb90ffb657f31f3c5b77f9a7715；不是浮动tag或config ID冒充manifest。base另为64c125.../c83e44...，普通gzip导出base又是不同manifest，不拿来替代执行pin。

独立先读inspect/全部argv/public input与fixture，再literal执行唯一name的无Key候选OS命令：pull never、netnone、非root65534、ro/cap0/nnp、pids32/mem256MiB/CPU1、nofile64/IPCnone、两个16MiB noexec tmpfs、唯一public只读mount、outer20s/engine10s；假Key/跨home/假private标签/controller源不可读、socket不可见、写入/网络受阻与实际cgroup断言通过，独立ps0/空。Dockerfile candidate target只有五条元数据指令，本地pinned base离线build同identity。

- **ContainerRunner.run()实际subprocess/timeout/cleanup E2E仍NOT RUN**；手工engine命令/command DATA不代替controller生命周期，不能为补测host跑未审项目或给候选socket。
- **offline load/另一engine或跨机原qualified pin往返仍NOT RUN**；独立save/hash只证归档字节同当前manifest，接收端RepoDigest关联/重编码/元数据/行为另需验证。
- Dockerfile python-test/plugin-test依赖stages仍NOT RUN；本次Node build使用共享rootfs，不是依赖target通过。本次image OS负向probe不代替全部资源攻击/恢复矩阵。

当前还可无Key推进offline-test-only provider下真实SDK/RPC/Session/工具/恢复与预算桥故障注入、受控独立平面下Runner lifecycle、离线依赖target与OCI接收端roundtrip。公开prehook/Files retry/extension omission调查仍是静态结论，未因native ready或image OS通过而实现每billable attempt预算/usage/watchdog。P03独立授权、可信凭据部署、private eval权限与全部强制Live门槛仍缺；**DECISION PENDING保持不变，不是只差Key或批准。**

## 10. 第四阶段 — SDK离线会话闭环与stdio账本桥（独立task24，2026-11-14 UTC）

### 基线与独立覆盖

第四阶段实现 **`f674403d12a6b51249b772090b7b004013d4ceb1`**（父提交 `e0ce9c8`），相对父提交仅17文件：离线fixture插件、SDK离线会话/ broker文档、accounting 4实现文件、2测试与README/runbook增量；生产 Gate/Adapter/默认primary/config/锁/Dockerfile **diff为空**。非实现者用 `git archive` 从该提交重建94文件公开stage（tar SHA `408ee068…`、归一化 `67fffd66…`），逐文件核对 Git blob 与 owner `final-stage` 后，在既有固定digest无Key禁网OCI（`62d356…`，nonroot/只读/cap0/nnp/cgroup受限）独立重跑：

| 独立重跑（审计者新argv/新日志） | 结果 | 唯一说明 |
|---|---|---|
| 全量 pytest `tests/unit tests/integration` | **326 passed in 4.26s，exit0** | 与owner 326一致；不预填 |
| 专门 E1-02 子集 | **89 passed in 0.20s，exit0** | 326子集，不相加 |
| stdio账本148回归重放 | **148 passed in 3.96s，exit0** | stage内 broker/test 字节=前轮独立闭环 fixed源码；132历史+16修复回归 |
| Ruff | **All checks passed!**，exit0 | 与owner lint日志逐字节相同 |
| wheel构建 | exit0，wheel SHA **`07fcb9e5…`与owner一致** | 构建日志与owner逐字节相同 |
| wheel-only无源码安装CLI/E1 API | exit0；安装/CLI/API/脚本 markers与5个payload自校验通过 | 与owner语义一致 |
| 真实Cordis插件strict build+8 registry | exit0；3 isolated命令exit0；**TAP 8/8 pass**；built产物hash=阶段3冻结值 | 紧构建输入经hash核验 |
| SDK fixture strict rebuild | exit0；**6个BUILT_FILE hash与task20/phase4期望一致**；日志与task20 build日志逐字节相同 | 从冻结插件源重新tsc |
| SDK 17用例suite | exit0；summary `cases17/sdk_run15/synthetic16/real_model0/http0/resume_pairs3/dual_home true` | 25项数据语义检查+与owner日志case级parity PASS |

交叉核对：phase4 manifest `bfea6fa1…`/`artifact-hashes 53/53`/`key-hashes 42/42`/wheel/plugin-built/installed-input 均 OK；重放输入归一化 hash 与历史一致（`final-stage 67fffd66…`、`sdk-build input ad041386…`、`sdk-replay f438c048…`=task20 stage、rootfs `25491e45…`、deps `e07729d7…`、插件node deps `026a7a15…`）；SDK runtime/validator/suite/worker/native cache hash与task20 manifest一致；pkg cache **4857/4857 OK**；owner安装产物5/5与日志一致、独立重跑的 `installed-summary.json`逐字节相同（其余4个仅随机UUID/时间戳不同，归一化后语义相同）；运行后容器 exact-name/全局查询为空。历史证据未改写：integration `711b02b4…`、phase2 `c512d653…`、phase3 `f4021242…` 及 sdk-fixture 65/65、budget-broker evidence-fixed 24/24、reviewer-phase3 83/83、broker closure 75/75 均校验通过。

### SDK fixture（B层）与stdio broker边界（不可夸大）

- **B层=真实锁定DSH引擎二进制`1cc41d5a…` + 真实Python SDK0.2.2rc2 + 真实JSON-RPC/Session v4/工具注册表/执行器 + 显式确定性`offline-test-only`/`fixture-v1`脚本provider。** provider无HTTP/无模型/无非确定输出，必须`AUTOTEACHER_OFFLINE_FIXTURE=1`且真实provider列表为空才注册；16次invocation全部`real_model_calls=0/http_calls=0`。真实的是引擎/会话/工具链路，不是模型。
- **工具事件非模型选择**：`tool-call`由脚本在`FIXTURE_TOOL`下产生；真实的是`request/header`中已注册`skill_lookup` schema、真实分发/执行、`callId`关联与`tool/result`（`isError=false`，结果等于公开`skills.json`的`binary_search`条目）。不能记“模型调用了工具”或 E1b/E2 Live。
- **语义与日志一致**：3/3跨新worker进程save→recall（同Session ID、不同PID、nonce精确回显）；双独立home同Session ID双向nonce隔离；unknown/corrupt resume为明确`JsonRpcError`且0 run；受控SIGTERM后`TransportClosedError(active-input)`、turn1 `aborted/disposed`、无usage/finish、turn2 resume恢复并保留中断痕迹。双home只证API/命名空间逻辑隔离（非E5文件系统隔离），17用例不是E4真实评估/教学效果证据。
- **不是运行中预算guard**：stdio broker 148重放通过且沿用前轮已闭环的持久`known_fee`/`price_json`修复；但`dispatch_allowed`只是首次记账，broker未被runtime/Gate/Adapter导入，仓库无task22 `plugins/runtime-budget-guard`，公开`llm/stream`预留/结算middleware不存在。README/runbook/SDK/broker文档均明确此限制。
- **无Key/无Live**：容器env白名单、suite/worker环境断言、invocation计数、`.env.example`不含Key、HarnessAdapter仍硬`SECURITY_BLOCKED`（父提交以来未改）、LiveGate未动。

### 审计结论、观察与未完成项

**未发现阻断性实现缺陷**；第四阶段在其声明范围内通过。观察O1：phase4 `results.jsonl`/`run_records`保留了最初4个用例的 operator tooling 失误（嵌套podman argv，exit125，容器创建前失败）记录，但这4个失败尝试日志随后被成功重跑覆盖（仅build attempt1单独保留）；manifest已如实说明非项目代码失败，建议后续冻结保留失败尝试独立日志。残余风险均为范围性：B层synthetic无真实模型/usage/费用；task22接线、逐HTTP/retry/compaction预算、人类授权、外部watchdog、SDK内部隐藏transport语义、guest tmpfs持久性、跨机OCI恢复与native/pkg cache官方export重放仍NOT IMPLEMENTED/NOT RUN。

**决策不变：DECISION PENDING；所有 Live 保持 BLOCKED；不签发 GO/CONDITIONAL GO，不把 synthetic fixture 当模型证据、不把 broker 当授权或真实账单上限、不启用 LiveGate。** 详见[独立 REVIEW_PHASE4](<REVIEW_PHASE4.md>)与[reviewer证据清单](<../artifacts/reviewer-phase4/evidence.sha256>)。

## 11. 第五阶段 — runtime budget guard 离线候选集成（独立task28，2026-11-14 UTC）

### 基线与独立覆盖

第五阶段实现 **`feb7118f9aff20c681cc651812b30315288080f1`**（父 `ec1128b`），相对父提交仅 9 文件：`plugins/runtime-budget-guard/`（公开 Cordis 插件）、`docs/RUNTIME_BUDGET_GUARD.md` 与 README/runbook 增量；`src/`、`tests/`、`config/`、`Dockerfile.m0`、`pyproject.toml`、`uv.lock`、`scripts/`、`fixtures/` **diff 为空**。非实现者用 `git archive` 独立重建 121 文件公开 stage（tar SHA `7bde63cc…`、归一化 `c68b3a1b…`、inventory 121/121），在既有固定 digest 无 Key 禁网 OCI（`62d356…`，nonroot/只读/cap0/nnp/cgroup 受限）独立重跑：

| 独立重跑（审计者新argv/新日志） | 结果 | 说明 |
|---|---|---|
| 全量 pytest `tests/unit tests/integration` | **326 passed in 4.30s，exit0** | 与owner一致，不预填 |
| 专门E1-02子集 | **89 passed，exit0** | 326子集，不相加 |
| stdio账本148回归 | **148 passed，exit0** | 独立scope，不相加 |
| Ruff | **All checks passed!** | — |
| wheel构建 | exit0；SHA **`07fcb9e5…` 与owner一致** | — |
| wheel-only无源码安装CLI/E1 API | exit0；安装/CLI/API/脚本markers全过，5/5 payload自校验 | summary逐字节同，其余4产物归一化语义同 |
| 插件strict build+8 registry | exit0；3 isolated exit0；**TAP 8/8** | built hash=历史冻结值 |
| SDK strict rebuild | exit0；2×BUILD_EXIT 0、6 BUILT_FILE一致 | 日志与task20逐字节同`cd44b06f…` |
| SDK 17用例suite | exit0；summary 17/15/16/0/0/3/dual_home true | 25/25宿主语义校验+owner parity PASS |
| guard strict build | exit0；3 BUILT_FILE一致（index.js `3c184a62…` 等） | 日志与owner逐字节同`92ea7c57…` |
| guard 12-case suite + 18/18 selftest | exit0；12/12 case、18/18 selftest、10 worker exit0 | summary与owner同；28/28宿主语义校验（本次/phase5/owner日志均PASS） |

交叉核对：phase5 manifest `391767d3…` 与 11 个 argv hash 全部相符；guard owner manifest `05224052…` 未改写，artifact-hashes **42/42**、stage-additions **45/45**、plugin-source **5/5**、guard-built **3/3**（delivered-files 6/7 唯一差异为 post-freeze 文档 errata 指针）；plugin source（git blob `1ccdb658…`）、guard built（`3c184a62…`）、phase4 冻结 stage/sdk-replay/sdk-build input/plugin stage、rootfs `25491e45…`、deps `e07729d7…`、guard node_modules `cab77a60…` 均与记录一致；native `40c34d27…`(0444)、pkg cache 4857/4857；审计者全部运行前后 canonical rootfs/deps 实测不变，`/var`、`/var/tmp` 不存在；运行后容器 exact-name/全局查询为空、image pin 一致、无后台 job。历史四阶段 manifest/证据（含phase4 53/53+42/42、reviewer-phase4 168/168、sdk-fixture 65/65、budget-broker fixed 24/24、broker closure 75/75、reviewer-phase3 83/83）全部校验通过且未改写。

### 预算守卫边界（不可夸大）

- **logical-stream 级，不是每 HTTP/wire/billable attempt**：一次 `ctx.llm.stream` dispatch = 一次 reservation；provider 库内部隐藏 retry/二次 POST 未被观测/拦截；text-only/拒绝 image/file/attachment 只是关闭项目 Files 路径的**前提**。文档与 owner manifest `non_claims/not_verified` 已列出，未越界。
- **pre-adapter 预留与 deny 前不进入 provider**：`await broker.reserve` 在 `next()` 之前，仅 `dispatch_allowed=true` 继续；s1 trace 为 `RBG_BOOT→RBG_RESERVE→FIXTURE_INVOCATION→RBG_SETTLE`；s4/s5/s6/s7 fixture=0，denied counter 不变。
- **固定 argv/无 shell/env 白名单/16KiB帧/settle exactly-once/fail-closed**：`spawn(fixed python, ['-B','-m','autoteacher_m0.accounting.broker','--config',fixed], {cwd, env:5项白名单, shell:false})`；broker policy hash 在 spawn 前校验；broker 不可用/漂移/篡改/子进程错误/超时/非法帧 → deny-all 或 unavailable fail-closed；`finally` 每个唯一 reservation 结算一次，无 usage/中断/error/非权威 finish → worst-case `fail` 全额保留且不退款；s8/s9/s10/s11 与 selftest 的 SQLite 行、RESERVE/SETTLE 计数与日志一致。
- **broker 非授权/非 Key 代理/非 usage 认证/非账单上限**：`dispatch_allowed` 仅首次记账；守卫未给 broker 增加授权/凭据/usage 认证能力；synthetic usage/cost 是夹具常量，`real_model_calls=0,http_calls=0`、无 Key/网络；task22 中间件未接入生产 Runtime/真实 provider，生产 Gate/Adapter/primary 未改。

### 观察、V1 与决策

- **V1（低严重度文档声明准确性，非代码/隔离缺陷；已关闭）**：[RUNTIME_BUDGET_GUARD](<RUNTIME_BUDGET_GUARD.md>) 原有三处声明强于已测证据——§2 mutation 检测后“后续流 fail-closed”（代码只对当前 stream worst-case settle，无全局 latch 且无测试）；§4 blocked-scope 单调拒绝“包括 compaction/retry 新 stream”（实际只测重复 normal stream）；§4 “selftest/session 均验证 2 次 post-attempt reservation”（实际只有 session s9 验证）。核心安全性质仍成立（后续 stream 仍先 reserve，拒绝/不可用时 provider 不进入，不存在无预留 dispatch）。**owner 已于 task31 完成文档纠错（无代码/测试变更、无新 SHA、未重跑 suite）：docs sha256 `1d0b62a2…`、errata `362dedb3…`，三处已收窄为与证据一致的准确表述且未削弱 reserve-before-provider/deny-before-provider；verify2 轻量复核确认 V1 CLOSED（见 [REVIEW_PHASE5 §6.1](<REVIEW_PHASE5.md>)）。**
- **O1（owner 证据 errata，Lead 已知）**：task22 owner manifest 的 rootfs `after/match` 字段自相矛盾（after `9d1d4e84…` 却 match=true，来自早期 build attempt 后被删除的空 `/var/tmp`）；旧 manifest 字节未改，`manifest-errata.json`（`83ec2433…`）记录正确 before/after 均为 `25491e45…`；第五阶段独立实测确认 canonical rootfs 前后均 `25491e45…`。仅作证据记录准确性观察，不引用旧 after/match，不影响 guard 代码/测试结论。
- **O2（标注澄清）**：guard harness summary 的 `real_runtime 7/7/$0.007198` 含 s11 restart 交叉验证写入 s1 DB 的 1 条 `FAILED $0.00112` 行；文档 §6 的会话聚合 `10 reservations = 7 OK + 3 FAILED / $0.018904` 是排除 s11 的独立正确 scope，两者不可相加/混称。
- **决策不变：DECISION PENDING；所有 Live 保持 BLOCKED；不签发 GO/CONDITIONAL GO，不把 logical-stream guard 当 per-HTTP/真实账单上限，不把 synthetic fixture 当模型证据，不启用 LiveGate。** 详见[独立 REVIEW_PHASE5](<REVIEW_PHASE5.md>)与[reviewer证据清单](<../artifacts/reviewer-phase5/evidence.sha256>)。
