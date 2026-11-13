# 第二阶段独立审计 — task13

## 1. 结论与历史边界

2026-11-13 UTC，reviewer在task12完成后get/claim task13，非实现者审阅并在已验证容器独立执行。**本阶段E1-02离线严格结构校验与最终离线回归PASS；M0整体仍DECISION PENDING，真实模型/Live仍BLOCKED。** 没有修改实现、上游、生产Gate/Adapter或原始历史证据，没有读取/注入真实Key，没有在宿主执行项目/probe Python或TS，没有模型/Session/prompt调用。

| 轮次 | 实现与证据 | 精确结论 |
|---|---|---|
| 首轮task5/6 | `d5db491bf3299c14b6af98f5cbe952ce56a1a991`；[首轮manifest](<../artifacts/integration/manifest.json>) SHA `711b02b4da8f066ed8483aca69a18e2eec0f11067e0d24a514a8c5dce9d19cc2` | 独立146 Python+8插件PASS；当时E1-02专门校验NOT RUN，保留为真实历史，不改成已执行 |
| 中间task10 | `c7bfdc1becdc006eb55a7da527c30b3bdd235ace`；[增量manifest](<../artifacts/e1-json/manifest.json>) | 新增E1-02实现/证据；本审计不把task10自身的计数与后续总数相加 |
| 本阶段task12/13 | `c155789557e525925435e7f8a8bf573856d80311`；[阶段二manifest](<../artifacts/phase2-integration/manifest.json>) SHA `c512d653f62b6604903890579ea85da48b2fef876f3b087ea96311e7c5c2d94b` | **独立235 Python PASS、89专门子集PASS、插件8 PASS、严格构建/wheel/安装CLI PASS**；89包含在235，不额外累计 |

首轮 [REVIEW](<REVIEW.md>) 原样保留。本轮仅写本审计、三份最终报告必要增量及允许的 [reviewer原始证据目录](<../artifacts/reviewer-phase2/manifest.json>)；后续文档归档SHA不替代实现SHA或人工审批。

## 2. 完整性与隔离

独立使用Git/jq/sha256sum/GNU tar核对：

- 阶段二manifest自身摘要匹配；82个源/输入文件在工作树、Git归档final-stage、冻结commit逐文件匹配；20个owner产物/日志摘要匹配。见 [source-and-artifacts](<../artifacts/reviewer-phase2/source-and-artifacts.log>)。
- 本轮rootfs **实际**归一化摘要 `25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0`。只排除已经独立确认是空目录的`./probe`，恢复首轮 `b4ca1b4f7279842bae18736a735469a575a7243dec0edabbc4d8e051c5dc68e8`。未删除目录或改rootfs来伪造匹配；旧摘要不直接冒充当前实际摘要。
- Python deps `e07729d7997944417b1c25531749b3e6e5e34aa4248f01dc8f370282082ecb98`、plugin deps `026a7a156830f102cea936bd6836d8f675d36f650ad5935cceb332f7ade292d2` 与既有锁定环境一致。见 [integrity](<../artifacts/reviewer-phase2/integrity.log>)。
- 首次对SDK子清单使用仓库根cwd，7项FAILED open/read，**不是checksum mismatch**；该审计者操作错误原样保留在integrity日志。按SDK清单自己的基目录重跑，7项全部OK，见 [修正核对](<../artifacts/reviewer-phase2/sdk-evidence-hashes.log>)。没有因失败跳过核验。
- 精确0.2.2-rc.2的8份npm tarball均匹配原哈希；独立对照8个关键引用文件的归档成员与解包源SHA一致。见 [static-source-hashes](<../artifacts/reviewer-phase2/static-source-hashes.log>)；发行版本一致不是二进制到Git build commit的密码学证明。

生成代码仅在security已经验证的Podman `--rootfs`边界执行：`network none/http-proxy=false/unsetenv-all`、uid/gid65534、只读rootfs/公开输入、cap-drop ALL、no-new-privileges、pids32、CPU1、总timeout75s/外层90s、scratch noexec/nosuid/nodev。Python/SDK使用512MiB，compiler有界1GiB/heap768MiB；没有扩大candidate策略，没有宿主可写bind mount。新probe复用既有`/probe`目标，未新增目录掩盖环境差异。

## 3. 独立实际执行的证据

各测试的完整argv、开始/结束UTC、退出码与stdout/stderr均在本轮证据目录；[reviewer manifest](<../artifacts/reviewer-phase2/manifest.json>) 只归属这次新执行，不改写owner或首轮结果。

| 独立执行 | 原始证据 | 结果与限定 |
|---|---|---|
| 全量Python | [tests stdout](<../artifacts/reviewer-phase2/tests.stdout.log>) / [result](<../artifacts/reviewer-phase2/tests.result.json>) | **235 passed in0.88s，0 skipped，exit0**，包含实际外部OS负向probe |
| E1-02专门套件 | [dedicated stdout](<../artifacts/reviewer-phase2/dedicated_e1_02.stdout.log>) | **89 passed in0.25s，exit0**；235中的子集，不相加 |
| Ruff | [lint stdout](<../artifacts/reviewer-phase2/lint.stdout.log>) | All checks passed，exit0 |
| 原样独立结构脚本 | [probe stdout](<../artifacts/reviewer-phase2/probe.stdout.log>) | 11类无效vector、现有Mock JSON分支、一次retry与耗尽均PASS；真实模型字段仍BLOCKED |
| 真正插件 | [plugin stdout](<../artifacts/reviewer-phase2/plugin.stdout.log>) | strict tsc/copy均exit0；官方registry **8/8 PASS，0 skipped**；JS摘要仍`521bc0f1126d895de84ebe61fd58c978a5bcae9b4c334f1fd417faee88483b0b` |
| 独立wheel重建 | [build stdout](<../artifacts/reviewer-phase2/build.stdout.log>) | tmpfs中hatchling重建exit0，摘要`89768d4769795a09dbcc9405def464796aec40ee5fc0faac68a756790c2ac8f7`与owner新wheel匹配；不覆盖owner产物 |
| wheel-only真实安装 | [installed stdout](<../artifacts/reviewer-phase2/installed.stdout.log>) / [新安装证据](<../artifacts/reviewer-phase2/public/e1-02-installed.json>) | 真uv安装到/work/site；cwd/work，无source mount/源码PYTHONPATH；inspect/smoke/paired/report(id+latest)+installed新E1 API/standalone脚本全exit0 |
| 独立对抗断言 | [reviewer脚本](<../artifacts/reviewer-phase2/adversarial_probe.py>) / [stdout](<../artifacts/reviewer-phase2/adversarial.stdout.log>) | 5组补充边界PASS；是额外独立断言，不包装成新增pytest案例数 |
| 独立SDK无Key诊断 | [keyless stdout](<../artifacts/reviewer-phase2/keyless.stdout.log>) / [结构化语义](<../artifacts/reviewer-phase2/keyless-semantic.json>) | **initialize BLOCKED；失败cleanup/missing-bin PASS；outer0非初始化PASS**，见下节 |

安装stdout的五项固定白名单公开payload以可信jq/base64取回，核对大小和SHA后存 [本轮JSON](<../artifacts/reviewer-phase2/public/experiment.json>)、[SQLite](<../artifacts/reviewer-phase2/public/experiment.sqlite3>)、[comparison](<../artifacts/reviewer-phase2/public/comparison.md>)、[summary](<../artifacts/reviewer-phase2/public/installed-summary.json>) 与新E1证据。未解包任意路径或执行payload。新run/session UUID不同于owner；20×2结构及API0/synthetic$0.030316不变。数据是公开Mock，不是保留集秘密或模型费用。

## 4. 严格E1-02边界审阅

已完整读 [structured_output](<../src/autoteacher_m0/runtime/structured_output.py>)、[专门unit](<../tests/unit/runtime/test_structured_output.py>)、[专门integration](<../tests/integration/runtime/test_e1_json_mock.py>)、[结构脚本](<../scripts/e1_json_probe.py>) 与 [phase2安装verifier](<../scripts/verify_installed_phase2.py>)。

- `E1Output`固定skill=`binary_search`；strict/extra-forbid/frozen，`StrictBool`后再要求`is True`。整数1/1.0、字符串、false/null/容器均被拒，不依赖会接受Python-equal 1的`Literal[True]`。
- wrapper仅收精确str、完整单个JSON对象；不修复、不截取Markdown/fence；4KiB上界同时检查UTF-8 bytes，精确4096合法pad可过，超界在parser前拒绝。独立以spy断言多字节超界不会进入JSON parser，不仅因extra字段而失败。
- duplicate JSON成员在解码后的键上拒绝，独立补测unicode-escaped重复键；NaN/Infinity、错shape/缺失/额外字段/错skill/无效UTF-8表示/深嵌套有负例。
- 原始JSON、Pydantic错误detail与异常链不从wrapper导出；安全错误固定INVALID_OUTPUT/固定消息。独立假哨兵在错误字符串、字段字典和标准traceback中均不可见，cause/context为空。直接绕过wrapper使用Pydantic错误对象不是约定的导出API。
- `run_e1_mock_validation`自己构造现有MockRuntime，仅允许tuple字符串fixture DATA与整数0/1 retry。没有任意runtime/request/record/factory注入入口。缺省不retry；只有成功本地Mock响应的INVALID_OUTPUT可retry一次；安全/认证/超时/执行失败均terminal，成功不消耗剩余重试。结果不保存坏响应原文。
- 该retry是无API的结构修复故障注入；不是SDK/provider transient retry、不接真实预算、不实现所有billable attempts。未修改生产[Gate](<../src/autoteacher_m0/security/gates.py>)或[Adapter](<../src/autoteacher_m0/runtime/dsh_adapter.py>)；相应摘要与首轮一致。

本轮未发现需要owner改实现的新离线缺陷。结论仅为**新实现的离线E1-02边界实际通过**，不倒填首轮NOT RUN，不满足获批主路由上的真实E1-02。

## 5. SDK第三方keyless probe：初始化仍BLOCKED

完整阅读task11 [SDK_OFFLINE_PROBE](<SDK_OFFLINE_PROBE.md>)，审阅probe/patch/audit源并核哈希；随后在同样边界独立重跑原样probe，不修改生产Adapter、不请求模型或Session。

| 观测 | 独立实测语义 |
|---|---|
| wheel SDK/runtime版本 | 0.2.2rc2；native exe实际`0.2.2-rc.2`，binary SHA`1cc41d5a8745a5b9d47c8604e44f23eb8af2d8ca02b2afa0be101d5f71be6ea4`；embedded metadata另报0.0.0-dev，不伪造build commit |
| version/config | 官方CLI exit0；12项disabled与upload=false合并配置断言通过，**仅config** |
| initialize | TransportClosedError，runtime host preparation因`No usable native binding found for node-addon-require-builtin-linux-x64-gnu (auto)`失败；**BLOCKED** |
| 失败清理 | _proc清空、initialized=false、reader/stderr线程退出、waitpid无子进程、幂等close PASS |
| missing binary | FileNotFoundError负例与清理PASS |
| 正常initialize→graceful shutdown、maxTokens错误握手、actual registry | 未到达/未观察，不能计PASS |
| 外层exit0 | 诊断断言通过；summary精确为`BLOCKED-initialize-cleanup-PASS`，**不是H1通过** |

原始诊断的`attempts:[Object]`不能判明noexec/EACCES、缺payload、缺依赖或ABI不兼容。不能把noexec当已证根因，也未验证read-only native cache解决方案。没有新增可写可执行mount、改隔离flags或切宿主执行。

## 6. 预算hooks：核实公开可行路径，不冒充已实现桥

审计者以exact版本原始tarball/source静态交叉核对task11关键结论：

- [llm/stream waterfall](<../artifacts/sdk-probe/upstream/dsh-llm/src/index.ts#L1185-L1198>) 确实在adapterStream之前，可作**logical stream**的预留入口；不是Python事后notification。
- [agent/pre-step](<../artifacts/sdk-probe/upstream/dsh-agent-loop/src/agent.ts#L289-L317>) 可reject步骤，但不是每次账单调用计数。[compaction summarizer](<../artifacts/sdk-probe/upstream/dsh-compaction-basic/src/summarizer.ts#L152-L179>) 独立调用全局stream并带purpose=compaction；应另预留。provider retry默认5，配置normal maxRetries=1也不是全局attempt cap。
- [adapter内部while/POST](<../artifacts/sdk-probe/upstream/dsh-llm-deepseek/src/adapter.ts#L105-L167>) 可因[Files stale-ID retry](<../artifacts/sdk-probe/upstream/dsh-llm-deepseek/src/request-files.ts#L130-L143>) 在**同一个stream内部再次POST**。因此全局pre-stream hook不能自动等于逐HTTP/逐计费attempt授权。
- [request extension prepare](<../artifacts/sdk-probe/upstream/dsh-deepseek-llm-api-extensions/src/index.ts#L103-L125>) 吞异常并省略字段，[accept](<../artifacts/sdk-probe/upstream/dsh-llm-deepseek/src/request-extensions.ts#L49-L56>) 是POST后且吞错误，均不是fail-closed预算闸门。
- 固定adapter/route/middleware、最外层gate、全history/tooloutput严格text-only闭包等可以作为关闭特定Files路径的设计前提；尚未实现/动态验证，也不证明底层transport每个wire attempt或供应商计费。Python RPC/idle timeout也不等于总watchdog。

**账本组件可用 ≠ Cordis预算桥已交付。** 跨语言唯一reservation、固定持久scope、预留早于next/iteration、每stream/retry/compaction/Judge、no-usage保守结算、reentry/concurrency/crash/deny与transport上界仍需独立实现和离线测试。公开offline-test-only provider扩展方向已静态说明，但未实现真实SDK→RPC→Session/工具/恢复的确定性测试闭环；不得将未来方案提升为本轮PASS。

## 7. 后续可离线完成的工作与停止条件

1. 独立定位exact wheel native binding的具体失败尝试/共享依赖/载入约束；若尝试预置只读cache，必须验证exact embedded bytes/loader兼容与路径完整性，不绕过权限、不放开可写可执行目录。保留当前BLOCKED证据。
2. runtime可启动后，实现显式命名offline-test-only provider，真实SDK/RPC/Session驱动工具调用、重启/恢复/双home nonce与中断；标记synthetic，不作DeepSeek/Live证据。
3. 实现公开pre-stream预算桥及step/retry/compaction/Judge/transport保守限制与拒绝单调性，先用无Key确定性provider断言reserve-before-dispatch/deny-never-enter，再独立审计。静态hook调查不替代这项工程。
4. 独立授权/可信控制器/凭据边界、实际安全registry、image runner/Dockerfile、真正私有评估权限及所有强制Live证据仍需后续工程与维护者操作；不是只差批准或真实Key。

本阶段不签发GO/CONDITIONAL GO，也没有足够证据判不可修复NO-GO。保持Live硬关闭；所有独立命名容器已由官方engine查询确认不存在，82项当前源输入、首轮历史manifest/产物与实际rootfs摘要再次核对通过，首轮REVIEW字节未变，git diff --check通过。最终清理见 [final-check](<../artifacts/reviewer-phase2/final-check.log>)，证据入口为 [reviewer manifest](<../artifacts/reviewer-phase2/manifest.json>) 与 [完整证据摘要](<../artifacts/reviewer-phase2/evidence.sha256>)。
