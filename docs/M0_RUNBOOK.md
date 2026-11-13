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

CLI 基础交付为 `inspect-runtime` 和 `smoke --mock`；`--live` 所有命令返回 exit 3，且先于任何文件创建/SDK初始化。`paired` / `report` 在 task-1 显式 BLOCKED，由后续依赖 task-5 对接 `experiments.cli.run_paired(*,artifact_dir:Path)->Path` 与 `render_report(*,artifact_dir:Path,experiment:str)->Path`。不提前等待跨模块完成或越权编辑。

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

## 6. 恢复 Live 验证的条件

1. 完成离线隔离回归；固定源码 Git SHA、全部依赖、插件与配置哈希；审核实际工具清单与上传设置。
2. 实现外部独立授权/受限控制器、账单 worst-case reservation/每步约束、外部 kill watchdog、真实事件 usage/错误分类、隔离日志。
3. 由独立人类维护者审查、冻结、批准具体版本，亲自另行注入低额度可撤销实验 Key。审计 Markdown 文件不是授权开关。
4. 默认官方主路由独立验证 `deepseek-flash` 的实际版本、请求ID与价格快照，不读取内部客户端凭据/不自动 fallback。
5. 在获批主渠道重新执行完整 E1–E5 必需项。缺证据继续 DECISION PENDING，不签 GO/CONDITIONAL GO，也不将凭据缺失误判技术 NO-GO。
