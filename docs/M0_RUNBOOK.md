# M0 Runbook — foundation baseline

## 1. 实际状态与禁止事项

采样时间：2026-11-13 UTC（任务书日期为 2026-11-14，不能据此伪造次日测试/价格）。当前为 **DECISION PENDING**。基础代码默认未受信任；宿主未运行本项目的 Python、pytest、import，也没有模型调用、真实凭据读取、自动安全批准或路由批准。

严格只使用无凭据、禁网、non-root、只读 rootfs、cap-drop、no-new-privileges、CPU/内存/PID/墙钟限制的独立容器运行生成代码。只将具体公开输入/代码复制到临时只读快照，不挂载仓库根目录（可能含真实 `.env`、Git、评分器/控制策略）；真实 DSH home、个人目录、socket 和隐藏评估源均不挂载。`cwd`、不同 DSH home、`.gitignore` 均不是 OS 安全边界。

## 2. 工具/依赖基线与可核验证据

| 项目 | 实际观察 | 证据/区别 |
|---|---|---|
| Git | 2.43.0 | `git --version` exit 0 |
| Git 初始文档 SHA | b37ddce96810610a8ec768dccd1873cc139e6a9f | 仅原始 AGENTS 与 v03/v04 文档；不是安全批准 SHA |
| uv | 0.11.6 | `uv --version` |
| 宿主默认 Python | 3.12.3 | 只执行版本检查，不用它验收 3.11 项目 |
| uv 已有可信 Python | CPython 3.11.15 | `/root/.local/share/uv/python/cpython-3.11.15-linux-x86_64-gnu`，仅定位/复制/依赖工具使用 |
| Node / pnpm | 22.23.2 / 12.14.0 | 版本检查；插件自身构建证据由插件任务提供 |
| 本机 npm DSH | 0.2.1-rc.2 | `dsh --version`；未修改上游或当前 DSH GUI |
| 项目锁定 SDK / runtime-bin | 0.2.2rc2 / 0.2.2rc2 | [锁文件](<../uv.lock>)，wheel Runtime **未初始化验证** |
| 第三方离线测试依赖 | pytest 9.2.0 / pytest-asyncio 1.5.0 / ruff 0.17.5 | 官方 PyPI hash-pinned wheels |
| Pydantic / core | 2.14.3 / 2.50.4 | 3.11 wheel，哈希见锁 |
| 其他依赖 | httpx 0.28.1 / PyYAML 6.0.3 / python-dotenv 1.2.4 | dotenv 依赖被要求保留，但应用不自动加载任何 `.env` |
| build backend | hatchling 1.30.1 | [官方版本元数据](https://pypi.org/pypi/hatchling/1.30.1/json)，基础 wheel 已在隔离容器构建成功；pathspec 1.1.1 / trove-classifiers 2026.9.21.13 同锁 |
| 上游 master 观察 SHA | 39163dd30f703a79079e2d2446545cff3c453738 | [官方 commit](https://github.com/deepseek-ai/deepseek-harness/commit/39163dd30f703a79079e2d2446545cff3c453738)，当时 master 为 0.2.2-rc.3，**不是**已安装 npm 或 wheel 的可证发行 commit |

`uv lock --python 3.11 --default-index https://pypi.org/simple` 和 `uv lock --check --python 3.11` 成功，最终锁定 Python `==3.11.*` 与 27 个包（含项目/平台条件包）；运行依赖安装选取 Linux 25 个第三方包，含 build backend 及其传递依赖。锁定不表示依赖已过安全人工审查。

官方 SDK wheel SHA256：`ad14f1b1fccb29f7d97e5a7e0ee9dbb96d8af11292308bba66bf19a623d31899`。仅用可信 curl 下载与 unzip 静态读取，从未将下载源码当成本项目执行。

离线依赖准备（只安装可信第三方 wheels，不构建/导入本项目）：

```sh
uv export --frozen --no-emit-project --format requirements-txt --output-file artifacts/foundation/requirements.txt
uv pip install --python 3.11 --target artifacts/foundation/deps --only-binary :all: \
  --require-hashes --index-url https://pypi.org/simple -r artifacts/foundation/requirements.txt
```

以上工具最终成功安装 25 个第三方包。下载原始 wheel、依赖目录、测试日志都在 gitignored artifacts，不能作为提交源代码或安全批准。

## 3. 官方 SDK 实际接口（静态核对，不是执行证据）

资料：[官方 PyPI 元数据/README](https://pypi.org/pypi/deepseek-harness-sdk/json)、[Python SDK Guide](https://deepseek-harness.github.io/deepseek-harness/en/guide/python-sdk)。从上述**锁定 wheel**静态阅读 `deepseek_harness/api.py` 与 models：

- `DeepSeekHarness(config=None, **kwargs)` → `DeepSeekHarnessConfig`。
- 支持 `dsh_home`, `cwd`, `runtime_cwd`, `profile`, `provider`, `model`, `max_tokens`, `patches`、初始化/协议响应/退出 timeout。
- `with DeepSeekHarness(...)` 会启动 Runtime，退出调用 `close()`；不在模块导入时构造。
- `harness.run(input, session_id=...)` 返回 `RunResult(session_id, final_response, finish_reason, events, notifications)`。
- **恢复用 `harness.resume_session(id)` 然后 `session.run(prompt)`**。`start_session(id)` 只是 lazy handle，不能用来声称恢复成功。
- Root events 是 JSON dict；notifications 是 SDK dataclass，不跨 [公共契约](<../src/autoteacher_m0/contracts.py>) 泄漏。
- 官方默认型号仍示例 `deepseek-v4-flash`，项目按任务书显式传 `deepseek-flash`；别名的服务实际版本尚未 Live 验证，绝不自动退回历史型号。
- `RunResult` **没有保证的 token/cost/model-version 字段**。项目缺失值保留 None，不推断零费用；真实事件 usage schema/提供商请求ID待验证。
- `request_timeout_seconds` 只限制协议 response wait，不限制后续整个 run 活动。SDK 没有已核实的精确 billable-step 上限参数；项目不传虚构 `max_steps`，也不宣称只靠线程 timeout 可控制账单。
- SDK 默认继承调用者环境；`sdk-minimal` 具有 Shell，不能当安全沙盒。关闭 session-log 的 [隐私 patch](<../config/dsh/sdk-minimal.patch.yml>) **不是**危险工具白名单，也未验证 wheel Runtime 的实际合并配置。

因此 [HarnessAdapter](<../src/autoteacher_m0/runtime/dsh_adapter.py>) 在 `run`、`resume`、`_new_harness` 入口均无条件 `SECURITY_BLOCKED`。其后 SDK 生命周期映射目前不可达。**这不是人类一批准即可运行的完整 Live 控制器**：外部不可伪造授权、凭据注入边界、安全 Profile/工具注册表、外部进程 watchdog、每次可计费步骤预算预留与真实 usage 结算都仍需工程实现、隔离验证与重新人工批准。不得为了拿到 PASS 删除阻断。

## 4. 项目 ABI 与集成约定

[contracts](<../src/autoteacher_m0/contracts.py>) v1：

- `RunRequest(case_id,prompt,candidate_id,session_id,provider,model,route_id)` frozen。
- `RunRecord(run_id,case_id,candidate_id,session_id,route_id,text,status,events,input_tokens=None,output_tokens=None,estimated_cost_usd=None,error_code=None,metadata={})`。
- 同步 `AgentRuntime.run(request)` / `resume(session_id,prompt)`；错误 `RuntimeFailure.code` 为稳定分类字符串。
- 运行状态 `SUCCESS/ERROR/BLOCKED/INTERRUPTED` 不等于实验 `PASS/FAIL/BLOCKED/SKIPPED`。
- 事件信封 `{type,sequence,data}`；SDK 原始事件先规范化/脱敏。Mock `metadata.mode='mock'`，usage 为 synthetic；仅 Mock 无账单费用可为 0。
- [ArtifactStore](<../src/autoteacher_m0/storage/artifacts.py>) `save/load`；`sanitize(value,*,sentinels=())`；[RunStore](<../src/autoteacher_m0/storage/schema.py>) SQLite `save/load/close`。文件名/索引拒绝敏感标识，文本过滤已知密钥模式；无法保证检测任意未知秘密，凭据必须从进程环境排除。

CLI当前已完成task-5跨模块接入：`inspect-runtime`只读包元数据/LiveGate诊断；`smoke --mock`使用基础Mock及synthetic BudgetGuard记账；`paired --mock`对接 `experiments.cli.run_paired(*,artifact_dir:Path)->Path` 生成20×2公开Mock，`report`对接 `render_report(*,artifact_dir:Path,experiment:str)->Path` 只读已有JSON再生报告。`--live`先于文件创建/SDK初始化经LiveGate返回exit3，即便将来gate错误返回仍硬关闭。`--budget-usd`只为未来已批准Live控制器保留，不授予权限；Mock使用固定synthetic预算，不把此参数冒称实际账单约束。

## 5. 离线执行与结果表

所有下述 Python/pytest/lint 必须在 security 已核验隔离中执行（CPython 3.11，具体 mount 仅公开快照与只读第三方 deps）：

```sh
python -m pytest tests/unit/runtime tests/unit/storage tests/unit/cli tests/integration/runtime -q -p no:cacheprovider
python -m autoteacher_m0.cli inspect-runtime
python -m autoteacher_m0.cli smoke --mock --artifact-dir /work/smoke
python -m autoteacher_m0.cli smoke --live  # 预期 exit 3 + SECURITY_BLOCKED，绝非联网测试
```

| 项目 | 当前证据状态 |
|---|---|
| 完整阅读两层 AGENTS/v0.4、发布 ABI、初始 Git 基线 | 完成，工具结果与 SHA 可核对 |
| 官方 SDK wheel 哈希/静态接口核对 | 完成；不是 SDK 初始化 PASS |
| 3.11 依赖解析/哈希 wheel 安装 | PASS（仅可信工具） |
| 项目 Runtime/storage/CLI 离线单测与Mock integration | **PASS：34 passed in 0.08s**；最终配置重跑 exit 0，CPython3.11.15受限Podman；[首轮日志](<../artifacts/foundation/tests.log>) / [最终日志](<../artifacts/foundation/tests-final.log>) |
| Scoped Ruff | **PASS：All checks passed!**；[日志](<../artifacts/foundation/lint.log>) |
| CLI metadata / Mock 3 smoke / Live fail-closed断言 | **PASS（离线包装逻辑）**；[日志](<../artifacts/foundation/cli.log>)，SDK未初始化，E1仍BLOCKED |
| Foundation wheel构建 | **PASS**：隔离运行 hatchling；[wheel](<../artifacts/foundation/build-output/autoteacher_m0-0.1.0-py3-none-any.whl>) SHA256 `05395a70472702558416fba0f0b2dfc1b9ecc5ea13268d0ec5d23a04a50e41cc`；[日志](<../artifacts/foundation/build.log>)；不等于跨模块最终包验收 |
| Mock JSONL 恢复/双 home 逻辑 namespace | 上述34测试内自动断言PASS；只验证Mock，与 DSH E3 区分 |
| Reviewer独立容器脱敏修复复核 | 三项原形复现/修后回归与碰撞条目保留PASS，原始stdout由reviewer发Lead；不推导任意未知secret可检测 |
| E1a/E1b 真实 SDK/模型 | BLOCKED，安全控制器与审批缺失 |
| E2 真工具调用 / E3 真实恢复 | BLOCKED，不以 fake SDK shape/Mock 替代 |
| E4 Live / E5 PreLive | BLOCKED，无独立人类审批/可信基线 |

安全成员早期探测 Docker/Podman 不存在；官方 apt 安装 Podman4.9.3 后 pull 受代理 socket permission denied 阻塞，未绕过。随后 security 用仅复制公开系统 runtime 的本地 rootfs 验证 OS 限制，并复制可信 CPython3.11.15 提供测试环境，未复制真实 `/etc`/home/凭据。本任务实际使用：`--network none --http-proxy=false --unsetenv-all --read-only --read-only-tmpfs=false --cap-drop ALL --security-opt no-new-privileges --user 65534:65534 --pids-limit 32 --memory 512m --memory-swap 512m --cpus 1`；仅 `/tmp`32m与`/work`64m可写tmpfs，noexec/nosuid/nodev；Podman内部timeout60s/外部timeout75s。只读mount是显式复制的 foundation公开stage 与hash-pinned第三方deps；构建另只允许一个空产物目录可写。独立容器名 `at-m0-foundation-tests`、`-lint`、`-cli`、`-build`。具体rootfs安全证据由 [威胁模型](<THREAT_MODEL.md>) 独立记录。该环境不授予可信代码身份或 Live 权限；最终跨模块回归另属 task-5。

## 6. Task-5 全模块集成与冻结复验

全模块owner均明确停写并授权仅显式源码/测试/公开fixture/锁/允许证据/doc清单进入Git。集成者不代改其他owner模块。已完成预检：

| 验证 | 真实预检结果 | 原始证据 |
|---|---|---|
| 全部unit+integration（含外部OS probe与4个system tests） | **146 PASS，0.54s，exit0** | [日志](<../artifacts/integration/preflight-tests.log>) |
| 全快照Ruff | All checks passed，exit0 | [日志](<../artifacts/integration/preflight-lint.log>) |
| 真实插件严格tsc/只读fixture构建/官方Cordis registry | 三条command exit0，8/8 PASS | [日志](<../artifacts/integration/preflight-plugin.log>) |
| 完整Python wheel | hatchling exit0；含公开20例package data | [日志](<../artifacts/integration/preflight-build.log>) |
| 真正wheel安装+安装后entrypoint检查 | uv --no-index/--no-deps实际安装成功；origin=/work/site；inspect/smoke/paired/report latest与ID全部exit0；20cases/40独立runs | [日志](<../artifacts/integration/preflight-installed-retry.log>) |

安装测试容器**不挂source checkout**，cwd=/work，启动PYTHONPATH仅/deps；安装后的子进程PYTHONPATH仅/work/site:/deps。使用真实uv安装而不是直接从zip/source import，验证console entrypoint与包内public fixture。第一轮验证脚本曾错误将rootfs空的/project/src mountpoint当作源码存在，预检exit1保留于 [失败日志](<../artifacts/integration/preflight-installed.log>)；仅修正本任务verifier为检查实际.py/包不存在，重跑成功，未放宽无源码挂载约束。

最终验证必须在**冻结实现提交以后**重跑。实现SHA、Git归档的显式公开源清单/逐文件SHA、整体清单SHA、固定锁/工具/rootfs哈希、完整容器argv、开始/结束UTC、每条退出码与日志、安装后20×2 JSON/SQLite/Markdown产物哈希将记录于外部gitignored integration manifest。容器不挂.git、不继承宿主完整环境；原单模块产物git_sha=UNRECORDED保持原样，新manifest仅关联此次新生成证据，不补造历史来源。最终汇总由独立reviewer依据该manifest审计撰写。

验证脚本为 [verify_installed](<../scripts/verify_installed.py>)；外部只解码四个固定白名单public artifact payload并核验长度/SHA，不在宿主执行生成代码。构建只对一个空独立wheel产物目录开放写mount；测试与安装结果通过stdout取回。Python容器memory512MiB/pids32/cpu1，compiler容器memory1GiB与Node heap768MiB仅为构建需求，不提高candidate runner安全策略。OS probe额外挂security固定public probe input（仅已知宿主假路径，无哨兵内容），不挂真实凭据/私有集。

关键边界：插件ABI固定DSH0.2.1-rc.2，SDK-wheel0.2.2rc2尚未装载插件/验证实际Profile；空白ID只被项目语义验证拒绝，原生schema不支持minLength，E2-03严格验收仍需人类判断。image-based ContainerRunner与Dockerfile构建仍因无镜像/registry权限BLOCKED；真实OS负向测试仅证明已记录local-rootfs配置，不推导其镜像实现已通过。持久BudgetLedger可用不等于SDK隐藏steps均受逐请求约束。Live、人类独立授权P03、真实SDK/Session仍BLOCKED，总体DECISION PENDING。

## 7. 第二阶段增量与环境冻结

首轮实现 `d5db491bf3299c14b6af98f5cbe952ce56a1a991`、首轮文档与 [manifest](<../artifacts/integration/manifest.json>)保持其历史真实性；不把后续结果倒填到首轮NOT RUN。task10新实现 `c7bfdc1becdc006eb55a7da527c30b3bdd235ace` 只新增专门E1-02纯验证/内部固定Mock重试、测试与 [专用探针](<../scripts/e1_json_probe.py>)。已运行的 [task10增量manifest](<../artifacts/e1-json/manifest.json>)：89项专门测试PASS、115项runtime回归PASS（包含89，不能累加），Ruff/专用probe PASS。真实模型E1-02仍BLOCKED。

[结构化输出API](<../src/autoteacher_m0/runtime/structured_output.py>)为 `E1Output` / `validate_e1_json(text)` / `run_e1_mock_validation(*,responses=None,max_retries=0)`：严格额外字段/精确skill/StrictBool后要求true；4096 UTF8字节，拒重复键/NaN/根数组/围栏等；固定错误无raw值/Pydantic detail/exception chain。只接受fixture数据，不接production Runtime/record/callback；最多2attempts且只无效结构可重试，安全/执行失败终止。它不实现provider内部重试，不是生产授权入口。

[task11官方SDK调查](<SDK_OFFLINE_PROBE.md>)在原锁定runtime0.2.2rc2中真正尝试constructor/start/close；native CLI报告0.2.2-rc.2，但embedded metadata0.0.0-dev与build commit未知不可混同。初始化因native binding不可用而BLOCKED，实际root cause（noexec/缺payload/ABI/dependency）未区分；未调用run/Session.run/模型。只有版本/merged配置和failed-start cleanup、missing-binary负向用例PASS；诊断外层exit0绝非initialize成功，实际registry observer亦未到达。

同版本官方npm源码显示全局 `llm/stream` waterfall在adapter前，可静态设计logical-stream预算预留；`agent/pre-step`可拒step，compaction另走stream，same-step retry需另计。**不是已经完成预算桥**：内部 `files.retry`可在一次stream里追加POST；完整history/tool结果text-only allowlist和冻结middleware等条件未实现动态验证；request-field扩展prepare异常会omit而不fail-closed，不能作预算拒绝关口。真实usage/逐HTTP上界/外部watchdog/独立授权仍未解决，生产Adapter/Gate保持原样。

本阶段实际rootfs归一tar SHA为 `25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0`，**不同于首轮**。唯一差异是Podman为task11的bind目标自动新增空 `/probe` mode1755目录；只读归档排除唯一 `./probe` 后精确恢复首轮 `b4ca1b4f7279842bae18736a735469a575a7243dec0edabbc4d8e051c5dc68e8`，runtime文件未改；目录保留，不删除来强行匹配旧hash。Python依赖仍 `e07729d7997944417b1c25531749b3e6e5e34aa4248f01dc8f370282082ecb98`。所有owner已停止rootfs相关输入变化，phase2将重新读取摘要并记录实际值，不把“源码未改”误作“rootfs hash未变”。

Task12流程：新集成提交冻结后Git archive显式公开源，重新跑全量pytest/Ruff、既有插件严格构建+registry、完整wheel真实安装四类CLI，并在无source mount/cwdwork/仅site+deps PYTHONPATH下验证新包API与独立脚本。新增 [phase2 verifier](<../scripts/verify_installed_phase2.py>)复用原verifier而不改原字节；输出新增一份固定白名单E1-02包验收JSON。测试计数取自实际日志，不预填，也不把task10的89与115相加；SDK初始化调查只作为单独独立有限证据引用，不由此宣称H1/模型或生产Adapter成功。新的独立manifest记录冻结SHA、实际argv/UTC/exit/源与产物hash、当前rootfs/deps及空目录差异证明；旧两轮manifest与原始日志完全保留。之后由task13独立审计/报告增量。

## 8. 第三阶段：精确原生只读缓存与本地OCI有限验收

前述首轮/第二阶段历史与其manifest不变；最新两个独立交付为 [SDK原生诊断](<SDK_NATIVE_DIAGNOSTIC.md>) 与 [本地OCI验证](<LOCAL_OCI_VALIDATION.md>)。第三阶段另冻新实现SHA和独立phase3 manifest，所有生成代码仍仅无Key禁网隔离执行，生产Gate/Adapter/默认官方模型路由保持原样。

SDK仍是锁定0.2.2rc2 wheel与原二进制SHA `1cc41d5a8745a5b9d47c8604e44f23eb8af2d8ca02b2afa0be101d5f71be6ea4`，没有用系统/其他发行替代。新证据把旧attempts展开为具体noexec临时缓存路径mapping失败；随后从同exe的公开SEA asset读取并与官方0.1.9 loader/native/package metadata四成员逐字节匹配。精确payload SHA `40c34d27d8339e246a8f7415a06152935496cdc06555ea8fce0e052011acc70f`，只读0444，官方 `NARB_NATIVE_CACHE_DIR=/probe/native-cache` 且原loader完整性验证保持。最终无NODE_OPTIONS/preload配置实际ready、真实registered-tool schemas=[]、正常close runtime0、maxTokens0握手拒绝/清理、missingbin负例通过；不调用Session/run/模型。只对应独立受限新配置，不回填旧默认配置失败，不签发完整H1/E1/Session/模型/生产Adapter成功，也不批准Live。

本地OCI从仅公开Python3.11.15与白名单动态库/合成passwd的独立子树导入，**不挂/不改共享rootfs/deps**。执行candidate pin为 `localhost/autoteacher-local-oci@sha256:62d3569ec38e27ed16fa3147515c1c78d993bb7df831cc1fe29811f3fe64667b`，config/content ID为 `56db1e2ad5ab29d3f39304d4fc9d0584d90e6bb90ffb657f31f3c5b77f9a7715`；离线base manifest为 `64c125c83fa76c2f92c9f004aceea2ff4d7aac07f80297668ab7fe0c550110b0`。浮动tag只可供构建发现identity，执行必须严格manifest pin/--pull=never。新增六项测试仅证明既有严格local name@digest与原策略相同、拒tag/configID/坏digest/参数注入，Runner实现不改。

现有 [Dockerfile](<../Dockerfile.m0>) 的candidate target仅5条元数据指令，三FROM参数均明确本地base digest、skip-unused-stages/pullnever/networknone/timestamp0，已有限离线构建；python-test与plugin-test依赖stages没有执行，不能算通过。已有command()在容器内只导出argv DATA后由worker/Lead独立审核、人工调用可信engine，精确image-OS探针exit0且独立ps确认空；**真实ContainerRunner.run的宿主controller进程/timeout/cleanup端到端仍NOT RUN**，不能由mock cleanup或手工image命令冒充。

无压缩OCI save的manifest/config/layer字节hash与执行身份吻合；普通gzip export会产生不同有效manifest，不能混同。**offline load / 跨机器原repository@digest roundtrip NOT RUN**。保存内容相同不证明接收engine会恢复同RepoDigest关联/元数据/执行语义；未来需独立目标、实际loaded身份与重新审过的执行pin，不能拿稳定config ID推导原manifest可迁移。

Task17将从新SHA公开stage实际重跑完整pytest（89为子集，计数以日志为准）、Ruff、真实插件、完整wheel/无源码安装CLI及E1包API/脚本；Python路径可使用上述精确local candidate镜像，Node仍使用既有只读公开Node rootfs，两者分别记录。可在原精确只读配置重放有限SDK ready/close探针与已审image OS/metadata-only build，仍不扩展到Session/provider/模型或真实Runner.run。shared rootfs实际25491e45与deps e07729要实测，独立image/subset/OCI对象身份单列，不混用；所有原始logs、argv、UTC/exit、锁/输入源/产物hash关联独立phase3 manifest。旧history与原始证据不覆盖，之后由task18独立复核。P03/可信控制器/预算桥/真实usage/Live watchdog与完整强制Live门槛仍未完成，总体DECISION PENDING。

## 9. 恢复 Live 验证的条件

1. 完成离线隔离回归；固定源码 Git SHA、全部依赖、插件与配置哈希；审核实际工具清单与上传设置。
2. 实现外部独立授权/受限控制器、账单 worst-case reservation/每步约束、外部 kill watchdog、真实事件 usage/错误分类、隔离日志。
3. 由独立人类维护者审查、冻结、批准具体版本，亲自另行注入低额度可撤销实验 Key。审计 Markdown 文件不是授权开关。
4. 默认官方主路由独立验证 `deepseek-flash` 的实际版本、请求ID与价格快照，不读取内部客户端凭据/不自动 fallback。
5. 在获批主渠道重新执行完整 E1–E5 必需项。缺证据继续 DECISION PENDING，不签 GO/CONDITIONAL GO，也不将凭据缺失误判技术 NO-GO。
