# Autonomous Teacher — M0

依据 [v0.4 任务书](<docs/Autonomous_Teacher_M0_v04.md>) 的离线优先技术验证设施，不是教学产品。当前总体 **DECISION PENDING**；没有真实模型调用，也没有人类安全/路由批准。

## 最终文档入口

- [G0–G2 closeout](<docs/M0_G2_CLOSEOUT_REPORT.md>)：G0/G1/G2 离线工作已完成并冻结（G1 `842583d`/`00df577`/`4d71530`，docs `70cb574`；G2 `ada8e28`/`32bea5b`）；G2 独立审计 [REVIEW_G2](<docs/REVIEW_G2.md>) 结论 **PASS_FOR_DECLARED_G2_SCOPE**（仅限离线/无 Key 声明范围），G1 为 PASS_WITH_ERRATA（见 [post-freeze errata](<docs/M0_G1_ERRATA_POSTFREEZE.md>)）；**G2-L1**（legacy authorize 未强制 claim）是 G3/Live 前必须收口的前置，V-G2-1 为证据身份注记；**G3+ 未授权**，Live/E1–E5/LiveGate/真实 Key/egress/usage/账单仍 **BLOCKED**、总体 **DECISION PENDING**，不签发 GO；OpenCode Go 凭据未使用、0 真实调用/0 预算消耗。
- [M0 收尾报告](<docs/M0_CLOSEOUT_REPORT.md>)：PR0–PR4 离线工作已完成并冻结（`e8b6e45`→`fdcfdc9`→`9b77a37`→`7d2cd3e`→`8cf2476`→`c802a32`→`87f44e1`，详见报告 §2）；5 份独立审计（[PR1](<docs/REVIEW_CLOSEOUT_PR1.md>)、[PR2](<docs/REVIEW_CLOSEOUT_PR2.md>)、[PR3](<docs/REVIEW_CLOSEOUT_PR3.md>)、[PR4A](<docs/REVIEW_CLOSEOUT_PR4A.md>)、[PR4B](<docs/REVIEW_CLOSEOUT_PR4B.md>)）PASS **仅限各自声明的离线/无 Key 范围**；V-PR1-1/V-PR4A-1 已 errata，V-PR2-1/V-PR3-1/V-PR4A-2/V-PR4B-1 的继承 lint 已由 `87f44e1` 清除（HEAD repo-wide Ruff 实测 `All checks passed!`）。真实 Live/P03/egress/Key/usage/账单仍 **BLOCKED**、总体 **DECISION PENDING**，不签发 GO；PR5 前置见报告 §8。
- [当前 M0 验证报告](<docs/M0_REPORT.md>)：顶部与§11为第五阶段独立审计增量；§10保留第四阶段历史，§9保留第三阶段历史，§8保留第二阶段历史，§1–7保留首轮E1-02 NOT RUN，不倒填结果，Live仍BLOCKED。
- [第四阶段冻结证据](<artifacts/phase4-integration/manifest.json>)（gitignored外部证据）：真实锁定DSH引擎/真实Python SDK + 显式`offline-test-only`合成provider的17用例SDK离线会话、stdio账本148回归重放、真实插件严格构建与wheel无源码安装CLI/API，均在既有no-Key禁网隔离内执行；实际计数、argv/UTC/exit与产物hash见该manifest（不预填）。
- [SDK离线会话闭环](<docs/SDK_OFFLINE_SESSIONS.md>)：真实引擎/Session/工具注册与执行链路，但provider是synthetic fixture，**不是**DeepSeek Live模型证据；[stdio账本桥协议](<docs/BUDGET_BROKER.md>)仅是固定scope的bookkeeping，不是授权/Key代理/真实账单上限，task22运行中预算middleware已作为离线候选交付（[预算守卫](<docs/RUNTIME_BUDGET_GUARD.md>)）但仍未接入生产/真实 provider。
- [最新第五阶段独立审计](<docs/REVIEW_PHASE5.md>)：非实现者在固定 digest 无 Key 禁网 OCI 内独立复核，**PASS 仅限其声明的离线范围**、0 代码/隔离/安全阻断缺陷：全量 pytest 326（含89专门子集，不相加）、broker 148、Ruff、wheel 构建与无源码安装 CLI/E1 API、插件8/8、SDK 17用例、guard strict build、guard 12/12 case + in-process 18/18 selftest 均独立重跑通过；宿主 data-only 语义校验 guard 28/28、SDK 25/25 PASS。**guard 仍是 logical-stream（pre-adapter）bookkeeping middleware，不是每 HTTP/wire/billable attempt 控制，也不是授权/Key 代理/真实账单上限；task22 未接入生产 Runtime/真实 provider，Live/P03 BLOCKED、DECISION PENDING 不变。** 低严重度文档声明准确性 V1 已由 task31 文档纠错关闭（无代码变更/无新实现SHA/未重跑 suite），另有 task30 rootfs errata 指向；详见 [REVIEW_PHASE5 §6.1](<docs/REVIEW_PHASE5.md#L131-L152>)。
- [第四阶段独立审计（历史）](<docs/REVIEW_PHASE4.md>)：非实现者在既有no-Key禁网固定digest容器内独立复核，**PASS仅限其声明的离线范围**、无阻断缺陷：全量pytest 326（含89专门子集，不相加）、stdio账本148重放、插件8/8、wheel构建与无源码安装CLI/E1 API、SDK strict rebuild与17用例suite，以及历史证据/manifest hash交叉核对。**不是真实模型/E1b/E2 Live/生产Adapter；broker只是bookkeeping且task22 middleware仅交付离线候选、未接线；DECISION PENDING与Live BLOCKED不变。**
- [运行时预算守卫（离线 middleware）](<docs/RUNTIME_BUDGET_GUARD.md>)：公开 Cordis `llm/stream` 最外层 logical-stream 预留/结算 middleware，向固定 scope stdio broker bookkeeping；`dispatch_allowed` 非授权/Key 代理/真实账单上限。仅在无 Key 禁网隔离内配合显式 synthetic provider/scripted fixture 验证，**尚未接入生产 Runtime/真实 provider/Live**；第五阶段集成回归的实际计数/argv/UTC/exit/hash 见外部 [phase5 manifest](<artifacts/phase5-integration/manifest.json>)（不预填）；独立复核见 [REVIEW_PHASE5](<docs/REVIEW_PHASE5.md>)，task22 原 manifest 的 rootfs errata 见 [manifest-errata.json](<artifacts/runtime-budget-guard/manifest-errata.json>)。
- [第三阶段历史独立审计](<docs/REVIEW_PHASE3.md>)：241项全量（含89项专门子集）、插件8项、安装CLI/API、精确只读缓存下的SDK启动子集及本地OCI有限验证通过。
- [第二阶段历史独立审计](<docs/REVIEW_PHASE2.md>)：235项全量（含89项子集）；当时默认无cache SDK初始化BLOCKED，历史与原文保留。
- [首轮历史独立审计](<docs/REVIEW.md>)：首轮来源/产物哈希与146项离线回归；原文保持不变。
- [Runtime 决策记录](<docs/ADR-001-runtime.md>)：DECISION PENDING及重新决策条件，不是安全或路由批准。
- [故障排查](<docs/TROUBLESHOOTING.md>)：已发生的问题、隔离复验与不可绕过的安全边界。

首轮历史证据对应 `d5db491bf3299c14b6af98f5cbe952ce56a1a991`，第二阶段对应 `c155789557e525925435e7f8a8bf573856d80311`；第三阶段冻结实现为 `5df4f3bdbecdf0683533ef7f0a176513713436cd`；第四阶段冻结实现为 `f674403d12a6b51249b772090b7b004013d4ceb1`，其确切源/锁/运行环境/产物清单与实际计数见[phase4冻结证据](<artifacts/phase4-integration/manifest.json>)，独立复核见[第四阶段审计](<docs/REVIEW_PHASE4.md>)。第五阶段冻结实现为 `feb7118f9aff20c681cc651812b30315288080f1`（父 `ec1128b`；相对父提交仅预算守卫插件+文档，src/tests/config/锁/Gate/Adapter 未改），证据/计数见[phase5证据](<artifacts/phase5-integration/manifest.json>)、独立复核见[第五阶段审计](<docs/REVIEW_PHASE5.md>)；本次文档归档commit SHA另记，仅补最新入口、task30 rootfs errata 指向与 task31 V1 文档收窄（无代码变更/无新实现SHA/未重跑 suite），不替代已测实现SHA，也不改原始manifest以匹配README的新字节。独立授权/受限控制器、Live watchdog与真实usage/逐step记账仍待工程；OpenCode Go第三方API接入仅optional UNVERIFIED。

## 第二阶段增量（与首轮历史分开）

- [专门JSON/Pydantic接口](<src/autoteacher_m0/runtime/structured_output.py>)：严格校验E1-02精确字段/类型、拒绝额外字段；只接受固定内部Mock与响应fixture数据，结构错误至多一次重试，不能注入生产Runtime或解锁Live。
- task10冻结 `c7bfdc1becdc006eb55a7da527c30b3bdd235ace` 已在无Key隔离中验证 **89项专门用例、115项runtime回归（包含89项，不能相加）**；[独立增量证据](<artifacts/e1-json/manifest.json>)保留新SHA、实际环境与原始输出。
- [官方SDK独立无模型探针/预算hook调查](<docs/SDK_OFFLINE_PROBE.md>)：真实initialize被native binding故障阻塞；只有配置/版本和失败清理、missing-binary负向用例通过，外层退出0不是H1通过。公开pre-adapter hook仅静态可行，内部files.retry额外POST等缺口尚未实现解决。
- [第二阶段安装验收脚本](<scripts/verify_installed_phase2.py>)在无源码挂载的wheel-only容器中扩展原四类CLI检查，另验包内结构化API和[专用脚本](<scripts/e1_json_probe.py>)；只可在既有无Key禁网边界中执行。

第二阶段[冻结证据](<artifacts/phase2-integration/manifest.json>)与[独立审计](<docs/REVIEW_PHASE2.md>)实测 **235项Python全量通过，含89项E1-02专门子集（不能相加）**；插件8项、严格构建、独立wheel重建与无源码真安装CLI/API/专用脚本通过。SDK实际initialize仍native binding BLOCKED，仅失败cleanup/missing-bin等通过；预算hooks仅静态调查，不是已实现桥。首轮历史章节/manifest与task10原始证据保留。真实模型JSON、生产Live、P03、DSH恢复和预算桥仍未通过。

## 第三阶段增量（已独立复核，限定覆盖）

- [精确只读原生缓存诊断](<docs/SDK_NATIVE_DIAGNOSTIC.md>)：相同锁定wheel/原`1cc41d…`二进制，官方SEA四成员逐字节匹配，精确`40c34d…`原生payload经只读`NARB_NATIVE_CACHE_DIR`、无preload，实现独立无KeySDK ready、实际registered schemas `[]`、graceful exit0及错误清理。**只对应这套新配置的有限子集**；旧默认未预置缓存的失败历史不改，H1/Session/模型/生产Adapter与Live仍未验收。
- [本地离线OCI验证](<docs/LOCAL_OCI_VALIDATION.md>)：既有Runner严格`name@sha256`和安全参数未变；精确`62d356…`镜像下已审command-DATA的OS负向探针与candidate元数据target离线构建有证据。**未执行真实ContainerRunner.run生命周期；python-test/plugin-test依赖target未验；offline load/跨机原pin恢复NOT RUN。** 无压缩archive manifest/config字节与执行身份相同，不等于已完成迁移重放。

[第三阶段冻结证据](<artifacts/phase3-integration/manifest.json>)与[独立审计](<docs/REVIEW_PHASE3.md>)实测241项Python全量、包含其中的89项专门子集、插件8项，以及wheel/无源码真安装CLI/API/脚本通过；不同轮次或重叠子集不能相加。新配置SDK ready/registered schemas[]/graceful0和本地exact-image OS/candidate元数据target已通过，仍不声明完整H1、Session/模型、生产Adapter、预算桥、Runner.run端到端或跨机load通过；Gate/模型路由不改，旧默认失败及d5/c7/c155历史证据保留。

## 第四阶段增量（SDK离线闭环与stdio账本桥，非Live；已独立复核，仅声明离线范围）

- [SDK离线会话闭环](<docs/SDK_OFFLINE_SESSIONS.md>)固化**B层**证据：锁定真实DSH引擎二进制 + 真实Python SDK/RPC + 显式`offline-test-only`/`fixture-v1`合成LlmAdapter，覆盖严格E1 JSON、真实`skill_lookup`注册/分发/事件、3/3跨进程save→recall、双独立home同Session ID命名空间、未知/损坏Session负例与受控中断恢复。provider由脚本决定、无HTTP/无Key，**不能记真实模型、E1/E2/E3 Live或生产Adapter通过**。
- [stdio账本桥协议](<docs/BUDGET_BROKER.md>)固化固定scope、持久SQLite的NDJSON bookkeeping broker；`dispatch_allowed`仅是首次记账记录，不是授权、Key代理或provider usage认证。独立审计发现的旧pending保留费被启动新费追溯重定价缺陷已修复为使用reservation行持久`known_fee`/`price_json`并新增16项回归（历史132+16=148，单次调用不重复计数）；旧`08572a…`manifest/原始证据原样保留，修正证据见[manifest-fixed](<artifacts/budget-broker/manifest-fixed.json>)，独立复核见[closure](<artifacts/reviewer-broker-pre/after-fix/closure.json>)（75/75）。
- 第四阶段隔离复验（真实实现SHA由phase4 manifest记录）：受限无Key禁网OCI内全量pytest+Ruff、专门E1-02子集、真实插件strict build、完整wheel构建与无源码真安装CLI/E1 API脚本，以及SDK 17用例与broker 148回归的实际重放/交叉核对，均只按日志实际去重计数。**stdio broker与SDK fixture都不代表运行中的预算guard已接线：第五阶段已交付公开`llm/stream`预留/结算候选middleware并完成独立隔离回归，但它仍未接入生产Runtime/真实provider/Live，见[预算守卫](<docs/RUNTIME_BUDGET_GUARD.md>)。** 真实模型/E1/E2/E3/E5、P03独立授权、Live watchdog与真实usage/逐step记账仍BLOCKED，总体DECISION PENDING；生产Gate/Adapter/默认primary路由不改。

## 安全边界

**所有本仓库生成代码仍未受信任。禁止在有凭据的宿主直接运行、import 或 pytest。** 即使是 Mock、lint 或以下 CLI，也只在无凭据独立隔离容器执行。绝不挂载真实 `.env`、个人 home、私有评估源、DSH home 或 Docker socket；不要将仓库根目录整棵挂载给候选。`.gitignore` 不是访问控制。

当前 `HarnessAdapter` 是官方 SDK 接口的**静态映射 + 无条件拒绝 Live 的基线**，不是“人类一批准即可使用”的完成版 Live 控制器。CLI `--live` 和 [Live 脚本](<scripts/run_live.sh>) 都返回 `SECURITY_BLOCKED` / exit 3；审批文档、环境变量或参数不会解锁。仍需实现外部独立授权、凭据边界、安全合并 Profile、外部进程 watchdog、真实预算/usage 集成，并重新人工审查。

## 依赖与复现

- Python **3.11.x**；[项目定义](<pyproject.toml>) 拒绝其他 minor，依赖与哈希见 [锁文件](<uv.lock>)，显式官方 PyPI。
- SDK `0.2.2rc2` + 同版本 runtime-bin；本机已有 npm DSH `0.2.1-rc.2` 是**另一发行版本**，不冒充 wheel Runtime。
- SDK 官方源码/元数据已静态核对，安装依赖不等于 H1 验证通过。
- 基础34测试通过；集成预检 **146 tests PASS、全量Ruff PASS、插件严格构建+真实官方注册表8/8 PASS**。完整wheel已在无源码挂载、`cwd=/work`、无源码PYTHONPATH的隔离容器内实际安装，四个CLI命令及包内20例资源验证通过。均为无凭据受限Podman/CPython3.11.15执行；最终冻结回归另见Runbook与原始manifest。
- 完整证据、版本与已知阻塞见 [Runbook](<docs/M0_RUNBOOK.md>)。由 security 成员提供的隔离操作步骤须先审核再执行。

以下命令**仅在已验证的无凭据隔离环境内**使用；并非宿主操作指令：

```sh
uv sync --frozen --python 3.11
uv run ruff check .
uv run pytest tests/unit -q
uv run pytest tests/integration -q
uv run python -m autoteacher_m0.cli inspect-runtime
uv run python -m autoteacher_m0.cli smoke --mock
uv run python -m autoteacher_m0.cli paired --mock
uv run python -m autoteacher_m0.cli report --experiment latest
```

`paired --mock` 生成20例×两策略的JSON/SQLite/比较报告（12开发+8公开模拟保留，非隐藏集）；`report`读取已有产物而不重跑。只打包公开fixture到wheel的package data。`--budget-usd`为未来获批Live控制器预留参数，不能解锁Live；Mock使用标记为synthetic的固定价目与预算守卫，API账单为零但synthetic费用单列。

离线测试与 `smoke --mock` 的 PASS 只证明项目 Mock/包装逻辑。**不代表 E1 SDK smoke、E2模型真实工具调用、E3 DSH恢复、Live配对或完整E5 PASS。** 插件原生schema不支持非空字符串：空白ID由项目语义校验拒绝，不能冒称原生schema验收通过。插件测试针对DSH0.2.1-rc.2 ABI，尚未在SDK-wheel0.2.2rc2 Runtime装载验证。原registry权限拒绝不变，但本地离线pinned OCI已补有限image-OS/candidate-target证据；真实Runner.run端到端、依赖targets与archive跨机恢复仍未验证，不能由rootfs或image-command结果外推。

## 公共接口

[项目契约](<src/autoteacher_m0/contracts.py>) ABI `m0-runtime-v1`：`RunRequest`、`RunRecord`、同步 `AgentRuntime.run/resume`、`RuntimeFailure.code`、`ErrorCode`。业务不暴露 SDK 对象；[Adapter](<src/autoteacher_m0/runtime/dsh_adapter.py>) 是唯一 SDK 导入位置。[MockRuntime](<src/autoteacher_m0/runtime/mock_adapter.py>) 独立 home 中的 JSONL 仅模拟持久化，不证明真实 DSH 或 OS 安全隔离。

[ArtifactStore](<src/autoteacher_m0/storage/artifacts.py>) 提供 JSON 保存/读取及 `sanitize`；[RunStore](<src/autoteacher_m0/storage/schema.py>) 提供 SQLite 索引。输出 usage/cost 缺失保留 `None`；只有显式标记的 Mock 成本为零。已知密钥形状/假哨兵会脱敏，但未知秘密不能靠正则完整检测，必须在执行边界排除真实凭据。

[路由记录](<docs/ROUTE_DECISION.md>) 保持默认官方 `deepseek-official / deepseek-flash`，没有自动 fallback、自动批准或真实型号版本验证。配置示例不授予权限。隐藏评估标签须位于仓库外，并仅授予独立可信评分器；候选不可读取评分器和预算/晋升控制策略。
