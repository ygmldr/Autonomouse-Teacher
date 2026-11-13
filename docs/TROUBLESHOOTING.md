# M0 故障排查与安全复验

首轮历史适用实现：`d5db491bf3299c14b6af98f5cbe952ce56a1a991`；第二阶段当前实现：`c155789557e525925435e7f8a8bf573856d80311`。当前仍 **DECISION PENDING，Live BLOCKED**。下列原有记录保留首轮范围，新增E1-02/SDK诊断/环境差异见文末第二阶段补充。事实/命令来源：[Runbook](<M0_RUNBOOK.md>)、[威胁模型](<THREAT_MODEL.md>)、[首轮manifest](<../artifacts/integration/manifest.json>)、[首轮审计](<REVIEW.md>)、[阶段二审计](<REVIEW_PHASE2.md>)。

## 先守边界

- 不在宿主执行项目Python/pytest/import/TS/build或候选代码。版本查询、Git/哈希、官方依赖工具与外部容器launcher不等于项目代码执行。
- 不读真实Key或私人env排查；不挂宿主home/socket/私有集，不用root/privileged/扩大mount补救失败，不将仓库根目录整棵暴露给候选。
- 使用已验证的显式公开只读stage、锁定deps与无Key rootfs；只在容器tmpfs产生临时输出。完整安全argv见manifest；镜像pull被权限拒绝时不要换代理绕过。
- 源/依赖/配置变化需要owner新提交、新SHA与回归。文档、env、指纹或`--live`不是权限开关。

## 症状与处理

| 症状 | 已知原因 / 正确处理 | 不应采取的措施 |
|---|---|---|
| CLI `--live` exit3 / SECURITY_BLOCKED | **预期行为**；独立授权与安全控制器、SDK/预算/watchdog工程仍未完成。见 [审批记录](<SECURITY_APPROVALS.md>) 和 [报告](<M0_REPORT.md>) | 改MD/env/猴补gate/删除raise来调用模型 |
| Adapter `run/resume/_new_harness`被阻断 | 三入口均硬关闭，后续SDK映射不可达；安装依赖/人类写一句批准不够 | 把静态映射标记SDK lifecycle PASS |
| 依赖安装了但真实SDK没有结果 | 本轮未初始化Runtime；metadata中的版本只是安装证据 | 调用模型“试一下”或读取内部客户端Key |
| Podman image pull exit125、proxy socket permission denied | 本轮原始受限环境无镜像；image runner/Dockerfile保持BLOCKED。已验证的本地公开rootfs只提供独立离线测试边界 | 改代理/registry绕过权限，或退为宿主执行 |
| 指定vfs出现storage database mismatch | 已有存储使用overlay；如实记录，由环境维护者处理；本轮没有改数据库绕过 | 随意删engine状态或猜路径清理 |
| 非root读取源文件PermissionError | tool写文件初始可为0600；让对应owner准备仅公开文件的worker stage并a+rX，再只读挂载 | chmod整个仓库/私人home，降为root |
| Python minor不符 / 包安装失败 | 项目锁定3.11.x；用受控可信3.11.15与hash锁定官方wheels；容器内运行项目 | 用宿主3.12替代验收、无锁latest或未审sdist/hooks |
| Node/V8 OOM，tsc测试未开始 | 512MiB首轮失败已留证；编译在批准的有界1GiB容器、heap768MiB重跑成功 | 取消所有资源上限，或把compiler资源放宽推广到候选策略 |
| strict tsc TS2307 `dsh-attachment`缺失 | 官方发布的dsh-llm声明引用未随peer闭包带出的附件包；已显式锁官方dsh-attachment0.2.1-rc.2 dev依赖，最终严格构建通过 | skipLibCheck、伪造声明/ABI或修改上游隐藏问题 |
| 空白skill_id未被wire schema拒绝 | 原生DSL无minLength/pattern；项目语义层返回官方INVALID_ARGS，已测试 | 把项目语义拒绝称native schema PASS，或偷偷改验收标准 |
| 插件离线8PASS却无法声称真实工具验收 | registry/fiber/process测试没有模型；SDK-wheel0.2.2rc2与插件ABI0.2.1-rc.2真实装载组合未测 | 只看回答出现skill_lookup或复制fixture就宣告E1b/E2 Live |
| Mock恢复成功但担心跨home读取 | Mock只证项目正常API命名空间；真实DSH恢复未测，恶意绝对路径访问由E5外部容器独立测试 | 把cwd/不同home当OS隔离 |
| SQLite/JSON仍出现假敏感串 | 检查known形状、字符串、字典键、索引及文件名；最终三项修复测试已通过。未知secret不能靠regex穷举，先排除凭据输入 | 向测试传真实Key或把正则测试当凭据边界 |
| requests耗尽/失败请求仍计费 | 正确保护：重试/失败也占request/step；超时不证明供应商未计费，缺usage按保守上界结算 | 失败自动退款、将None当0或重建scope重置总量 |
| Ledger重启仍有pending | 正确保护：崩溃预留仍按全上界占预算；由可信控制器明确核实后实际/保守结算 | 自动清空pending/删除库/换scope继续花费 |
| Ledger提示policy differs | 同scope已固化限额，不允许重启静默放宽；须独立人工变更程序和新审查 | 偷改预算或新库冒充全局同scope |
| 预算实际超过预留后blocked | 如实记账并关闭后续请求；排查隐藏context/steps/reasoning/extrafee的上界与真实usage | clipping实际值、当成零、仅提高上限掩盖 |
| report最新实验找不到 / ARTIFACT_ERROR | 先在隔离内运行paired Mock，确认对应artifact root与ID；latest只搜索该根 | 将缺产物标PASS或改成访问任意路径 |
| 所有Mock得分1、delta0 | 固定公开脚本有意符合规则；只证管线，不证明策略无差异或教育增益 | 用这些数值做模型/教学排名 |
| 明确错误评分器或模糊代码输出 | EVAL_ERROR/null或NEEDS_REVIEW是预期，pair可INCOMPLETE；关系规则仍需人类语义盲审 | 将异常当0分吞掉、把模糊样本自动满分 |
| 安装后找不到20例fixture | 最终wheel已包含public package data，loader优先包资源；在无源码mount/cwdwork真实安装复验 | 仅设source PYTHONPATH让测试假通过 |
| installed verifier误认source存在 | rootfs可能有空/project/src挂载点；检查实际.py/包是否可见，不以空目录存在作为源码证据 | 为消除断言把源码挂进安装验收 |

[插件历史日志与解决过程](<../plugins/skill-lookup/evidence/offline-summary.json>) 保留了OOM、TS2307及最终成功，不倒写成首轮即PASS。[安装预检失败](<../artifacts/integration/preflight-installed.log>) 也保留了verifier空目录误判，最终冻结验收和独立运行均通过。

## OS probe、超时与cleanup

1. 正常只挂公开源+deps时，OS测试会因缺 `/input/host_paths.json` 而 **SKIPPED**；这不是OS PASS。本次最终146回归额外挂固定公开probe input，实际用例运行且0 skipped。不要为“全绿”删除skip条件或改为读取宿主真实private文件。
2. cgroup配置必须读实际内核值，不能仅看CLI参数。本次独立负向probe读到512MiB/pids32/CPU1；security原始probe在256MiB配置运行，两者是不同有界执行，不相互混淆。
3. network失败可能表现为socket创建被宿主策略直接拒绝；只说明实际探针受阻，不推断所有socket家族的绝对安全。
4. 内存测试原始证据是oom_kill 0→1、child -9；Podman deadline原始launcher exit255/engine ExitCode -1，不假定所有平台都是137。CPU证明是实际quota，不是全部CPU滥用场景的形式证明。
5. **杀外层CLI不等于容器消失。** 超时后用官方engine按唯一已核对名称force rm，再独立 `ps --all` 确认absence；daemon错误、非0查询、残留或查询超时都应fail-closed交维护者检查。不要仅凭rm=1当not-found。
6. 修复后的 [ContainerRunner cleanup](<../src/autoteacher_m0/security/docker_runner.py#L146-L173>) 无论rm返回何值都查全部状态确认不存在，8项mock负向回归已纳入独立146。**它的image-based实际OS运行仍BLOCKED**；本地rootfs launcher的PASS不能替代。
7. Podman/conmon在init OOM时可在launcher cwd产生零字节oom标记；已知初始标记有独立metadata/重现实证并归档，见 [威胁模型](<THREAT_MODEL.md>)。不要对猜测/计算路径盲删，也不要执行生成文件。

## 最短安全复验路径

1. 核对 [manifest摘要](<../artifacts/integration/manifest.sha256>)、冻结SHA、74项源输入、rootfs/deps与产物摘要；完整独立方法在 [REVIEW](<REVIEW.md>)。
2. 用manifest已审查的tests/plugin/installed/lint argv重放，仅改唯一容器名，不扩大权限/mount。先保证公开stage可由uid65534读取。
3. 146 Python与8插件各自计数；OS单独重跑1例与146重复，不相加。build或安装失败保留退出码，不将实现存在当PASS。
4. 安装后测试只挂wheel/verifier/可信uv/deps；cwd/work，子进程PYTHONPATH只指/work/site与/deps。inspect/smoke/paired/report(id、latest)均需断言成功；原脚本见 [verify_installed](<../scripts/verify_installed.py>)。
5. 检查所有命名容器确实不存在、源和manifest未变。源码有任何变化，请owner新提交/重冻与重跑，不由审计者代改。

## 将来恢复Live前

必须另外完成独立授权/受保护可信部署、实际安全profile与禁上传、真实SDK与事件/usage映射、每可计费step的持久预算接线/价格和上下文上界、外部watchdog、候选镜像/私有评估权限部署；再由人类对具体SHA/config/命令/route审核，并亲自注入低额度可撤销Key。当前仓库没有一个“设变量即可开Live”的操作。

之后在获批primary完整重跑必需E1–E5并保留真实费用/失败日志，再重新独立审计和讨论选型。OpenRouter/OpenCode Go仍属未依赖optional；后者第三方API研究本轮未做，UNVERIFIED而非NOT_SUPPORTED，不影响本轮离线收尾。

## 第二阶段补充（c155789，历史不倒填）

[新manifest](<../artifacts/phase2-integration/manifest.json>)与[独立raw evidence](<../artifacts/reviewer-phase2/manifest.json>)对应235 Python（含89专门E1-02）+8插件、严格构建/独立wheel重建/无源码真安装CLI与新API/脚本PASS。235与89不能相加，也不能倒改首轮146及E1-02 NOT RUN。当前离线结构校验已实际PASS，真实模型JSON仍BLOCKED。

| 新症状 | 准确处理 | 禁止误读/绕过 |
|---|---|---|
| E1Output的ready=1/1.0/字符串/false失败 | 预期：StrictBool后要求is True；skill固定binary_search，extra拒绝。经validate_e1_json导出固定INVALID_OUTPUT | 改成宽松bool或仅Literal[True]放过1；导出原始Pydantic.errors/detail |
| 相同/转义后的重复JSON键失败 | 预期：解码后键去重，拒绝last-write-wins | json.loads默认覆盖后声称已验证唯一性 |
| 字符数没到4096但输出被拒 | 上界是UTF-8 bytes；4096含边界，超界在parser前拒绝；不提取fence/修坏JSON | 只数codepoints、取消cap或把坏输入当空对象 |
| Mock结构retry终止或无第三次 | 默认0，最多1次；只有成功本地Mock响应的INVALID_OUTPUT可重试，security/transport错误terminal，成功不继续 | 注入任意runtime/factory/production record，或当作provider retry/预算接线已完成 |
| keyless SDK外层exit0，但initialize字段BLOCKED | 诊断脚本0表示清理断言完成；必须读取summary=BLOCKED-initialize-cleanup-PASS和TransportClosedError/nativebinding错误 | 仅凭脚本0宣称H1/正常shutdown/真实registry PASS |
| native binding No usable native binding found | exact wheel在当前受限环境启动失败，attempts被压为[Object]，需独立定位EACCES/缺payload/依赖/ABI；read-only cache只是未验证方向 | 擅认noexec根因，放开可写可执行mount、root/privileged、换系统发行或宿主执行 |
| merged-config disabled/upload=false，但缺实际工具清单 | 配置断言已过，startup在observer加载前失败；actual registry未观察 | 把audit插件源码或config dump当实际registry/生产Live安全PASS |
| rootfs hash从b4ca变25491 | Podman为task11创建空/probe bind目标；当前实际摘要应25491，独立确认空目录并仅排除它恢复旧b4ca，deps未变 | 删除目录强行匹配历史、直接拿旧整体摘要为新执行背书 |
| SDK证据清单全是FAILED open/read | 检查相对路径清单的base cwd；本轮reviewer初跑错误保留，按artifacts/sdk-probe基目录重跑全部OK | 把open失败混成checksum mismatch或直接跳过验证 |
| 找到llm/stream prehook，是否可以接Key | 还不可以；它可拦logical stream，Files retry可同stream再POST。field extension异常仅omit，accept后置且吞错；先实现/离线测budget bridge/全history闭包/transport边界 | 用Python后置notification、idle/RPCtimeout、extension throw冒充逐HTTP fail-closed gate |

当前可继续的无Key工作包括exact native兼容定位、显式offline-test-only provider的真实SDK/RPC/Session/工具/恢复，以及预算桥的reserve-before-dispatch/deny/concurrency/retry/compaction/no-usage/crash断言。这些不是等待真实Key才能做的工作，也未因静态源码调查而自动完成。生产LiveGate/Adapter仍硬关闭；[SDK报告](<SDK_OFFLINE_PROBE.md>)与[REVIEW_PHASE2](<REVIEW_PHASE2.md>)区分实际诊断、静态可行性和未实现工程。
