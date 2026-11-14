# ADR-001 — DSH Runtime 选型暂缓，保留离线可替换边界

> **第五阶段当前更新：** 实现`feb7118f9aff20c681cc651812b30315288080f1`新增公开 Cordis `llm/stream` 最外层 logical-stream 预算预留/结算候选中间件，并以真实锁定 DSH 引擎/真实 Python SDK/RPC/Session/工具链 + 显式 synthetic `offline-test-only` provider/scripted fixture 在隔离内验证（guard 12/12、selftest 18/18、全量326/89/148/插件8/SDK17/wheel安装等独立复核通过）。**它不是 per-HTTP/wire/billable attempt 控制，不是授权/Key 代理/真实账单上限；task22 中间件尚未接入生产 Runtime/真实 provider，Live/P03/watchdog 仍 BLOCKED。** 一项文档声明准确性观察（V1）已由 owner task31 文档纠错关闭（无代码变更、无新 SHA、未重跑 suite），非代码缺陷。决策不变：DECISION PENDING。第五阶段增量见文末与[REVIEW_PHASE5](<REVIEW_PHASE5.md>)。

> **第四阶段当前更新：** 实现`f674403d12a6b51249b772090b7b004013d4ceb1`新增锁定真实DSH引擎/真实Python SDK/RPC/Session/工具链路 + 显式synthetic `offline-test-only` provider的17用例离线会话证据，以及stdio账本桥148回归；非实现者独立复核全量326、89子集、148重放、插件8、SDK strict rebuild/17用例、wheel安装CLI均在其声明范围内通过。**这些仍是B层synthetic/本地bookkeeping证据，不是模型、E1b/E2 Live、生产Adapter或真实预算guard；task22 `llm/stream`预算middleware原为未实现未接线，第五阶段已交付离线候选。决策不变：DECISION PENDING，Live BLOCKED。** 第四阶段增量见文末与[REVIEW_PHASE4](<REVIEW_PHASE4.md>)。

> **第三阶段当前更新：** 实现`5df4f3bdbecdf0683533ef7f0a176513713436cd`独立241 Python（含89子集）+8插件及镜像安装回归PASS；同原binary+精确只读native cache的无preload SDK启动/registered schemas[]/graceful0子集通过，exact本地OCI的OS命令/candidate metadata target通过。**M0仍DECISION PENDING，Live关闭**；未执行Session/模型/生产Adapter/Runner.run E2E或跨机load。下文前两阶段原状态保持历史，第三阶段增量见文末与[REVIEW_PHASE3](<REVIEW_PHASE3.md>)。

> 第二阶段历史更新：最新实现`c155789557e525925435e7f8a8bf573856d80311`已独立235 Python（含89专门子集）+8插件及安装CLI回归通过，离线E1-02缺口已补。SDK无Keyinitialize实际尝试仍受native binding阻塞；公开预算hooks仍是静态可行性，桥未实现。**决策继续DECISION PENDING，不解锁Live。** 本文原有下列证据保持首轮d5db491历史，增量见文末与[REVIEW_PHASE2](<REVIEW_PHASE2.md>)。

- 日期：2026-11-13 UTC。
- 状态：**DECISION PENDING / 待补强制证据**；不是 GO、CONDITIONAL GO 或技术 NO-GO。
- 规范：[M0 v0.4](<Autonomous_Teacher_M0_v04.md>)；实测报告：[M0_REPORT](<M0_REPORT.md>)；独立审计：[REVIEW](<REVIEW.md>)。
- 冻结实现：`d5db491bf3299c14b6af98f5cbe952ce56a1a991`；来源：[manifest](<../artifacts/integration/manifest.json>)，SHA `711b02b4da8f066ed8483aca69a18e2eec0f11067e0d24a514a8c5dce9d19cc2`。文档归档提交不是新的实现或人类安全批准。

## 背景

M0验证的是DSH作为长期运行底座的可行性，不是开发M1教学产品，不比较模型、不证明学习收益/RSI收敛。指定模型固定DeepSeek V4.1 Flash；默认设计primary是官方deepseek-official/deepseek-flash。实现默认未受信任，未经独立人类审查与真实安全部署不得接触实验凭据。

本轮已核验的事实：

1. 无凭据、禁网、非root、只读公开输入/rootfs且资源受限的Podman容器内，非实现者独立复跑 **146 Python tests PASS（无skip）、Ruff PASS**。
2. 真正官方Cordis/dsh-tools ABI的插件严格tsc、fixture构建及 **8/8 registry tests PASS**，包括重启/卸载。不用手写ABI或模型模拟冒充真实插件。
3. 完整wheel在不挂源码、cwd/work的容器由真实uv安装后，inspect/smoke/paired/report(id+latest)通过；public package data 20例、40独立run/session可用。
4. project-owned预算/持久scope会计、Mock Session、脱敏、规则评分与20×2公开配对设施通过；实际rootfs负向OSprobe有独立执行证据，资源压力/恢复有security原始证据。

尚未核验或未实现的事实同样关键：

- SDK0.2.2rc2真实生命周期、模型调用、usage/错误事件与DSH真实Session恢复未运行。
- 插件ABI0.2.1-rc.2与SDK-wheel0.2.2rc2的实际profile/加载组合未运行。
- 原生schema接受空白ID，只由项目语义层拒绝；E2-03精确标准差异需维护者判断。
- 独立授权/凭据broker、受保护可信控制器、安全合并profile/危险工具禁用/实际session-log关闭、Live watchdog、每billable-step预算接线与真实费用结算仍待实现/部署验证。
- image-based candidate runner与Dockerfile未运行；本地rootfs不是不可变发布镜像。真实私有评估权限部署与Live≥6对也未验证。

## 决策

### 现在接受的限定工程选择

- 保留 [RunRequest/RunRecord/AgentRuntime](<../src/autoteacher_m0/contracts.py>) 项目ABI，不让DSH类型跨越业务边界；[Adapter](<../src/autoteacher_m0/runtime/dsh_adapter.py>) 保持唯一SDK导入位置。
- 保留项目自有 [EvalContract](<../src/autoteacher_m0/evaluation/contracts.py>)、[BudgetGuard](<../src/autoteacher_m0/accounting/budget.py>)、[持久账本](<../src/autoteacher_m0/accounting/ledger.py>) 与 [产物存储](<../src/autoteacher_m0/storage/artifacts.py>)。可继续无凭据离线开发，不等于进入可信基线。
- 保持所有Live入口fail-closed。安全记录、路由记录、指纹、环境变量、CLI flag都不是授权凭据；不新增Agent可自行approve的接口。
- 只将本轮结果称为**离线设施交付通过**，不把依赖已安装、不可达SDK映射、Mock namespace或registry事件提升为真实Runtime验证。

### 暂不作出的选择

**不决定DSH已经适合M1主Runtime，也不决定放弃DSH。** 没有满足强制E1–E5门槛，不能GO；关键安全/运行证据BLOCKED不能用CONDITIONAL GO绕过。当前未发现证据充分、不可通过公开扩展或外部隔离解决的DSH核心缺陷，不能仅因缺凭据/实现/部署而NO-GO。

## 备选方案与未采用理由

| 方案 | 当前处理 |
|---|---|
| 立即GO，用现有代码直接注入Key | 拒绝：真实SDK、独立授权、预算接线/watchdog和实际工具边界都未完成；不是“只差批准” |
| 将offline PASS记为CONDITIONAL GO | 拒绝：规范不允许以条件跳过关键BLOCKED |
| 因无Live证据直接NO-GO | 拒绝：证据不足不等于DSH确定性不可修复 |
| 为通过测试修改DSH上游、伪造工具ABI、宿主运行候选 | 拒绝：破坏验证目标与安全边界；本轮未这样做 |
| SDK不稳时改公开TS Runner/JSON-RPC | 留作有证据时的替代；本轮未实施或验收 |
| 将来换PydanticAI Runtime | 退路而非本轮实现；保留项目ABI与评估/预算数据以降低切换成本 |
| 自动切到OpenRouter/OpenCode Go | 拒绝：路由与模型映射需独立人类批准、事前记录和完整重验；不做自动fallback |

## 渠道政策

[ROUTE_DECISION](<ROUTE_DECISION.md>) 保持默认官方主渠道、未批准执行。OpenRouter未测试；OpenCode Go第三方API调查本轮未开展，UNVERIFIED，不能推断NOT_SUPPORTED或免费额度。二者均为未依赖optional，不独立降低整体结论；也不能为官方渠道补PASS。若将来经人类批准改primary，GO仅针对完整重验后的具体渠道配置，官方状态另列。

## 后果、风险与重新决策条件

好处：离线组件有真实可重现证据；预算、评估与存储不被SDK内部类型锁死；没有因证明愿望而让候选继承凭据。

代价：仍需工程和人类部署工作，尚不能以现有CLI开展付费模型实验；本地rootfs与engine/kernel/LXC是TCB，不能宣称生产级安全。规则评分与公开模拟保留集只测管线，不测真实教学质量；原始artifact被Git忽略，需单独保全。

重新打开本ADR的必要输入：

1. 冻结新的完整代码/依赖/config/profile/tool清单；实现并独立验证受保护授权/凭据边界、无动态候选继承权限。
2. 验证真实SDK/usage/模型与请求版本，逐billable-step预留/结算、完整上下文与输出上界、总进程watchdog、固定持久预算scope和供应商侧限额。
3. 验证实际合并profile/上传禁用/插件跨版本组合；明确处理原生非空schema差异；验证真正候选镜像部署与私有评估权限。
4. 人类维护者对具体SHA/config/权限/命令审查批准，独立受控会话注入专用低额度可撤销凭据。
5. 在获批primary完整重跑E1–E5必需项，保留原始Trace/账单/失败证据并再次独立审计。只有全部强制项满足才可讨论GO；非关键已验证可补偿限制才可能CONDITIONAL GO；证据充分的不可接受且不可维护修复问题才NO-GO。

没有这些输入，状态保持 **DECISION PENDING**，不得通过修改本ADR或审批Markdown改变执行权限。

## 第二阶段补充 — 不改变选型决策

新冻结实现`c155789557e525925435e7f8a8bf573856d80311`与[新manifest](<../artifacts/phase2-integration/manifest.json>) SHA`c512d653f62b6604903890579ea85da48b2fef876f3b087ea96311e7c5c2d94b`，与首轮d5db491/146+8分开。独立235 Python通过，其中89是专门E1-02子集；插件8、严格构建、独立重建wheel、无源码真安装CLI/API/脚本均通过。StrictBool/fixed skill/extra/duplicate/UTF-8 bytebound/安全错误与最多一次data-only Mock retry已实测，**首轮E1-02 NOT RUN仍是历史，不倒填。**

[第三方SDK报告](<SDK_OFFLINE_PROBE.md>)与独立复跑显示，version/config与失败cleanup/missing-bin负例通过，但initialize因native binding失败BLOCKED，真实registry/正常shutdown/Session仍未到达。outer0不是生命周期通过；生产Adapter和Gate未改变。

公开Cordis pre-adapter `llm/stream` 可作为logical stream预算入口，但Files内部可同stream再POST、field-extension准备异常不fail-closed；预算桥、全history/tooloutput闭包、每attempt上界、外部Live watchdog未实现验证。不能把“Python没有prehook”夸大为无法扩展，也不能把“找到了prehook”夸大成已限制账单。

下一步优先做可离线工程：在相同安全边界定位exact native兼容问题（不擅认noexec根因），验证只读cache等方案；实现显式offline-test-only provider驱动真实SDK/RPC/Session和budget-bridge故障注入。它们即使通过也仍属synthetic，不代替获批primary上的Live强制证据。详见[阶段二审计](<REVIEW_PHASE2.md>)与[当前报告§8](<M0_REPORT.md>)。

rootfs本轮实际摘要25491e45开头，新增空/probe目录的排除证明恢复首轮b4ca；不是当前环境仍与旧整体摘要相同。证据来源与环境演进必须一同保留。本补充不授予人类安全/路由批准，GO/CONDITIONAL GO/NO-GO门槛不变。

## 第三阶段补充 — 新子集证据成立，决策不变

新实现`5df4f3bdbecdf0683533ef7f0a176513713436cd`与[phase3 manifest](<../artifacts/phase3-integration/manifest.json>) SHA`f4021242729f03ffe8ed86bb783d88192515e03f80ea7185b08d4c910d03df60`单列：非实现者独立241 Python（含89专门子集）、Node8、Ruff、相同89768 wheel重建与无源码真安装CLI/API脚本通过，source生产实现和Gate/Adapter/Runner未改。[REVIEW_PHASE3](<REVIEW_PHASE3.md>)给出全部新raw与精确覆盖。

原1cc executable的SEA四成员与官方loader/native0.1.9 bytes/size/SHA逐项相等后，原loader公开cache配置使用RO40c34匹配payload。无preload、无可写可执行mount、scratch noexec不变下实际initialize-ready/registered schemas[]/graceful0/无效握手cleanup通过。**接受这项keyless startup子集证据，不接受完整H1/生产Adapter/Session/模型/Live通过的外推。** 旧默认无cache配置仍BLOCKED，历史不改写；registry定义列表不是per-agent resolved ToolSet。

本地OCI exact manifest62d/config56db与raw layeraed独立核验；真实候选OS命令与Dockerfile candidate元数据target及无压缩archive bytes通过。**不把command执行当ContainerRunner.run() E2E，不把save/hash当load/跨机qualified pin roundtrip，也不把candidate五条metadata当python-test/plugin-test依赖stage通过。** 共享rootfs25491、独立clonee680、raw layer、image manifest/config分别记录，不因tag或目录名相似合并身份。

公开预算hooks仍是静态可行性：logical stream未必等于HTTP计费attempt，Files retry与field-extension异常omit边界仍在。下一步可离线实现显式offline-test-only provider驱动真实SDK/RPC/Session/工具/恢复、预算桥的预留/拒绝/结算故障注入、受控controller lifecycle及独立OCI接收端验证，不必等真实Key。独立授权/可信凭据部署、真实usage/费用/总watchdog、private评估权限和主渠道完整Live验收仍未完成。

故继续 **DECISION PENDING**；GO/CONDITIONAL GO的强制门槛、禁止Agent自批和既定默认路由不变。新keyless配置不是安全批准或自动放行项。

## 第四阶段补充 — B层会话证据成立，选型决策不变

新实现`f674403d12a6b51249b772090b7b004013d4ceb1`与[phase4 manifest](<../artifacts/phase4-integration/manifest.json>)（SHA`bfea6fa1d4cb3d144879b784aeb76c73f1fee3ef0842034b37dba939e90a2df5`）单列，父提交`e0ce9c8`；相对父提交仅离线fixture/accounting/docs/README/runbook 17文件，生产Gate/Adapter/默认primary/config/锁未改。非实现者独立复核：[REVIEW_PHASE4](<REVIEW_PHASE4.md>)与[reviewer-phase4证据](<../artifacts/reviewer-phase4/evidence.sha256>)。

**新增事实（B层）：** 真实锁定DSH引擎`1cc41d5a…`/真实Python SDK0.2.2rc2/真实JSON-RPC/Session v4/工具注册表与执行器，配合显式`offline-test-only`/`fixture-v1`确定性脚本provider，17用例覆盖严格E1 JSON、真实`skill_lookup`注册/分发/执行事件、3/3跨进程save→recall、双home同Session ID双向隔离、unknown/corrupt负例、受控SIGTERM中断与resume恢复；独立重跑summary与owner一致（`17/15/16/0/0/3`），25项语义检查与case级parity通过。SDK strict build从冻结插件源重新tsc，6产物与task20一致。

**接受与不接受：** 接受B层“真实引擎/SDK/RPC/Session/工具链路在synthetic provider下工作”这一事实；**不接受**其为真实模型、E1b/E2 Live、E3完整PASS、E5文件系统隔离、生产Adapter或真实usage/账单证据。双home只证API/命名空间逻辑隔离；工具`tool-call`由脚本决定，不是模型选择。

**stdio账本桥：** 148回归独立重放通过（132历史+16修复回归，沿用前轮已闭环的持久`known_fee`/`price_json`）；但它是固定scope持久bookkeeping，`dispatch_allowed`只是首次记账，不是授权/Key代理/provider usage认证/真实账单上限。`src/autoteacher_m0`的runtime/Gate/Adapter未导入它，**task22公开`llm/stream`预留/结算middleware未实现未接线**，不能当运行中预算guard。

**故继续 DECISION PENDING，Live硬关闭。** 下一步无Key可做项：task22预算middleware的reserve-before-dispatch/deny/结算/重试/压缩/无usage/崩溃故障注入与独立验证；真实provider usage/逐billable step记账、外部watchdog、P03独立人类授权与主渠道E1–E5 Live验收仍缺。第四阶段通过不解锁LiveGate、不构成安全/路由批准。

## 第五阶段补充 — 预算守卫离线候选证据成立，选型决策不变

新实现`feb7118f9aff20c681cc651812b30315288080f1`（父`ec1128b`）与[phase5 manifest](<../artifacts/phase5-integration/manifest.json>)（SHA`391767d3b073d239fded57299c5149d91130a9e476a53b525f4f22f4e69b646f`）单列：仅新增`plugins/runtime-budget-guard/`、[RUNTIME_BUDGET_GUARD](<RUNTIME_BUDGET_GUARD.md>)与README/runbook增量；`src/`、`tests/`、`config/`、锁、Gate、Adapter、primary 路由均未改。非实现者独立复核：[REVIEW_PHASE5](<REVIEW_PHASE5.md>)与[reviewer-phase5证据](<../artifacts/reviewer-phase5/evidence.sha256>)。

**新增事实（B层 + 本地 bookkeeping）：** 一个真实公开 Cordis 插件在全局`llm/stream` waterfall 最外层、provider dispatch/迭代之前向固定 scope stdio broker 预留；仅`dispatch_allowed=true`进入 provider，`finally`对每个唯一 reservation 结算/fail 一次且不退款。独立隔离重跑：guard 12/12 case、in-process 18/18 selftest、全量326、89子集、148 broker、插件8、SDK17、wheel构建与无源码安装 CLI/API 及 guard strict build 全部通过；deny/config-tamper/broker-unavailable/no-usage/retry 两次 reservation/SIGKILL-restart pending/counts 与日志一致；real_model_calls=0、http_calls=0、无 Key/网络。

**边界（不夸大）：** 守卫只是 logical-stream（pre-adapter）预留，**不是**provider 库内部每次 HTTP/wire/billable attempt 的控制；text-only/拒绝 Files 路径只是关闭 Files 路径的**前提**，不证明底层 transport 无隐藏 retry/二次 POST；broker 是 fixed-scope bookkeeping，`dispatch_allowed`不是人类授权、Key 代理、provider usage 认证或真实账单上限；synthetic usage/cost 是夹具常量，不是真实账单。**task22 中间件仍未接入生产 Runtime/真实 provider；生产 Gate/Adapter/primary 未改，LiveGate 未开。**

**一项观察 V1（低严重度，文档声明准确性；已关闭）：** 文档 §2/§4 原有三处声明强于实际代码/日志（mutation 后“后续流 fail-closed”无全局 latch 且未测；blocked-scope 单调拒绝“含 compaction/retry 新 stream”未测；retry 两次 reservation 仅 session s9 验证、selftest 无该用例）。核心 reserve-before-provider/deny-before-provider 安全性质不受影响。**owner 已于 task31 文档纠错（docs sha256 `1d0b62a2…`、errata `362dedb3…`，无代码变更/无新 SHA/未重跑 suite），三处已收窄且未引入更强 claim，verify2 轻量复核确认 V1 CLOSED（[REVIEW_PHASE5 §6.1](<REVIEW_PHASE5.md>)）。** 另，task22 owner manifest 的 rootfs after/match 字段矛盾已由 task30 errata（`83ec2433…`，正确 before/after 均`25491e45…`）纠正，旧字节未改，仅作观察。

**故继续 DECISION PENDING，Live硬关闭。** 下一步：把候选 middleware 接入受控 runtime 前补齐 transport 隐藏 retry/Files/真实 usage 与逐 billable attempt 上界、compaction/Judge 全生命周期、kill 时序 settle、独立人类授权 P03 与外部 watchdog；这些仍 NOT RUN/BLOCKED。第五阶段通过不解锁 LiveGate、不构成安全/路由批准。
