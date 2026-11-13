# ADR-001 — DSH Runtime 选型暂缓，保留离线可替换边界

> 第二阶段更新：最新实现`c155789557e525925435e7f8a8bf573856d80311`已独立235 Python（含89专门子集）+8插件及安装CLI回归通过，离线E1-02缺口已补。SDK无Keyinitialize实际尝试仍受native binding阻塞；公开预算hooks仍是静态可行性，桥未实现。**决策继续DECISION PENDING，不解锁Live。** 本文原有下列证据保持首轮d5db491历史，增量见文末与[REVIEW_PHASE2](<REVIEW_PHASE2.md>)。

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
