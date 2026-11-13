# Autonomous Teacher — M0 验证报告

## 最新状态 — 第二阶段增量（2026-11-13 UTC）

**最新实现 `c155789557e525925435e7f8a8bf573856d80311`：独立235 Python PASS（含89专门E1-02子集，不相加）、8插件PASS、严格构建/独立wheel重建/真实安装CLI与新增结构API脚本PASS。** E1-02离线状态由首轮NOT RUN变为本轮实测PASS；真实模型JSON仍BLOCKED。第三方无KeySDK初始化已尝试但native binding阻塞，只有version/config与失败cleanup等通过；公开预算hooks只是静态可行性，桥未实现。整体仍 **DECISION PENDING / Live BLOCKED**。

新证据：[阶段二manifest](<../artifacts/phase2-integration/manifest.json>) SHA `c512d653f62b6604903890579ea85da48b2fef876f3b087ea96311e7c5c2d94b`；[独立阶段二审计](<REVIEW_PHASE2.md>)及[本轮reviewer原始证据](<../artifacts/reviewer-phase2/manifest.json>)。详见§8。

> **以下§1–7保留首轮d5db491的历史范围、计数和NOT RUN事实，不是把当前新结果倒填到旧执行中。当前增量以本节与§8为准；首轮REVIEW/manifest/原始产物保持原样。**

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
