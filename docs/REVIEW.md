# 独立审计 — M0 v0.4

## 1. 结论、身份与冻结范围

- 审计者：reviewer，非实现者；2026-11-13 UTC。完整阅读 [AGENTS](<../AGENTS.md>) 与 [v0.4 全文](<Autonomous_Teacher_M0_v04.md>)，先做 task8 只读审计，再在 task5 完成后领取 task6。没有修改实现、测试、预算、安全策略或上游代码，没有读取真实 Key，没有模型/Live 调用，没有在宿主执行项目 Python/pytest/import/TS。
- 冻结实现：`d5db491bf3299c14b6af98f5cbe952ce56a1a991`；本审计文档不是人工安全批准，也不覆盖将来的代码变化。
- **离线设施回归 PASS；M0 总体 DECISION PENDING。** E1–E5 的完整强制门槛尚未满足，不签发 GO / CONDITIONAL GO，也不把缺少实现、审批或实验证据误判为 DSH 技术 NO-GO。
- 不是“只差一份批准文件”：独立授权/凭据边界、受限可信控制器、真实 SDK/usage 验证、逐 billable-step 记账与外部 watchdog 等仍待实现或部署验证。现有 LiveGate 与 Adapter 无条件拒绝 Live，必须保留。

## 2. 独立核验的来源与完整性

主证据为 [integration manifest](<../artifacts/integration/manifest.json>) 与 [manifest 摘要](<../artifacts/integration/manifest.sha256>)。审计者用系统 Git、jq、sha256sum、GNU tar 做只读检查，未调用项目代码：

| 检查 | 独立结果 |
|---|---|
| manifest 自身 SHA-256 | `711b02b4da8f066ed8483aca69a18e2eec0f11067e0d24a514a8c5dce9d19cc2`，匹配 |
| manifest 中 74 个公开源/输入文件 | 工作树、Git 归档 final-stage、`git show <冻结SHA>:<path>` 三者逐文件均与 manifest 匹配 |
| manifest 中 14 个原始产物/日志 | 全部 SHA 匹配；没有重写历史产物补造来源 |
| rootfs 归一化 tar | `b4ca1b4f7279842bae18736a735469a575a7243dec0edabbc4d8e051c5dc68e8` |
| Python deps 归一化 tar | `e07729d7997944417b1c25531749b3e6e5e34aa4248f01dc8f370282082ecb98` |
| plugin node_modules 归一化 tar | `026a7a156830f102cea936bd6836d8f675d36f650ad5935cceb332f7ade292d2` |
| 安装输入中的 verifier / uv / wheel | 分别匹配冻结脚本、manifest 工具摘要、最终 wheel 摘要 |

归一化算法为 manifest 指定的 `tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner -cf - -C PATH . | sha256sum`。本地复制的公开 runtime rootfs 不是已发布的 digest-pinned 镜像。

所有独立运行均采用 security 已验证的 Podman `--rootfs` 边界：禁网、不继承代理/宿主环境、UID/GID 65534、cap-drop ALL、no-new-privileges、只读根与只读公开输入、PID/CPU/内存/墙钟限制。仅容器自己的 `/tmp`、`/work` tmpfs 可写；本轮没有宿主可写 bind mount，也没有挂载 Git、真实 home、真实凭据、socket 或私有评估源。运行公共控制器/测试的容器可读公开评分器，这**不是**敌对候选的保密部署。

## 3. 审计者独立执行，不是转述 owner PASS

完整命令与 stdout/退出状态保存在本会话工具执行记录；以下是独立运行摘录。现存 owner 日志另列为交叉核验，不能冒充本轮独立日志。未向宿主另写测试产物；生成数据库、安装目录与构建输出均随容器 tmpfs 丢弃。

| 独立运行 | 容器名 / 工具 job | 观察结果 |
|---|---|---|
| 全 Python unit + integration | `at-m0-reviewer-final-python` / `bash-5425fe1f73ba432c` | **146 passed in 0.69s，0 skipped，exit 0**；挂载公开 OS probe 输入，未跳过 OS 用例 |
| 严格插件构建与官方 registry 测试 | `at-m0-reviewer-final-plugin` / `bash-8d682f4780c94b19` | strict tsc exit 0，fixture copy exit 0，**8/8 PASS，0 skipped，exit 0**；不是 fake registry 或模型调用 |
| 真正安装 wheel 后 CLI | `at-m0-reviewer-final-installed` / `bash-ed4efa3dbf24423a` | uv 实际安装成功；inspect / smoke / paired / report(id、latest) 全部 exit 0；verifier 最终 exit 0 |
| 运行时与依赖摘要 | `bash-e4f2ed90f49b4fee` | 上节三项归一化摘要、verifier/uv/wheel 匹配，exit 0 |
| 独立 Ruff + 单独显示 OS probe | `at-m0-reviewer-final-os-lint` | `All checks passed!`；`OS_NEGATIVE_ASSERTIONS_PASSED`；**1 passed in 0.01s，exit 0**；此 1 例与 146 中 OS 用例重复，不另加总 |

Python 容器 memory/swap 512 MiB、pids 32、CPU 1；插件编译容器 memory/swap 1 GiB、Node heap 768 MiB、pids 32、CPU 1。编译资源不代表提高 candidate runner 策略。外层 timeout 90s，Podman timeout 75s。

独立 OS 输出确认：UID 65534；`memory.max=536870912`、`pids.max=32`、`cpu.max=100000 100000`；[实际负向探针](<../fixtures/sandbox/exercise.py>) 断言 capabilities=0、NoNewPrivs=1、已知宿主假 Key/双 home 假 Session/假私有标签不可读、socket 不可见、根与输入不可写、scratch 可写、外网连接失败或 socket 创建被拒。仅涉及假哨兵；不探测真实私人文件。

安装验收使用 [冻结 verifier](<../scripts/verify_installed.py>) 原样运行。容器 cwd 是 `/work`，只挂 wheel/verifier/可信 uv 与第三方 deps，**无 source checkout mount，PYTHONPATH 无源码路径**；安装 origin `/work/site/autoteacher_m0/__init__.py`，控制台 entrypoint 确实存在。20 个 package-data 案例产生 40 个独立 run/session、20 对；本轮实验 ID `mock-13240045-d1c0-45ad-8dd8-9e29925d2728`，与 owner 运行不同。两种 report selector 指向同一报告；API 账单 `$0`、synthetic 估算 `$0.030316`，SDK 未初始化。

插件独立构建得到 JS SHA `521bc0f1126d895de84ebe61fd58c978a5bcae9b4c334f1fd417faee88483b0b`、fixture SHA `6988fc43029688fbe60fa401e7fe460a59441717afc88c7664958299b1835300`，与 manifest 匹配。实际使用官方 Cordis Context、ToolRuntime、SystemPrompt、defineTool；覆盖注册、参数/结果、fiber restart、两个 OS 进程、dispose/remount。没有启动模型。

### 复跑方法（只在同一已核验隔离环境执行）

[manifest 的 commands 字段](<../artifacts/integration/manifest.json#L317-L623>) 记录了逐 argv 的完整命令。审计者实际以同样参数运行 tests/plugin/installed，只替换容器名；另在同样的 tests 容器条件内执行 Ruff 和 `pytest -s` 单独显示 OS 输出。下列只读解析不使用 eval，不运行 build 条目或开放宿主写挂载；复跑前须重新核对摘要、命令和输入，不把 manifest 当权限凭据：

```bash
sha256sum -c artifacts/integration/manifest.sha256
replay_offline() {
  case "$1" in tests|plugin|installed|lint) ;; *) return 2;; esac
  mapfile -d '' -t argv < <(jq -j --arg mode "$1" \
    --arg name "at-m0-reviewer-repeat-$1" \
    '.commands[$mode].argv | .[index("--name") + 1] = $name | .[] | . + "\u0000"' \
    artifacts/integration/manifest.json)
  "${argv[@]}"
}
replay_offline tests
replay_offline plugin
replay_offline installed
replay_offline lint
# 如外层超时，不能只杀CLI便认为容器消失：用官方engine force rm并独立ps确认absence。
```

## 4. 重点审计与缺陷闭环

此前 task8 完整只读审阅 contracts、settings、accounting、security gates/runner、runtime/storage；交叉审阅 eval/paired/report 与真正插件 ABI。问题仅发送 Lead 和 owner，修复均由 owner 实施。

| 问题 / 风险等级 | 修前证据与修复 | 最终状态 |
|---|---|---|
| Trace quoted JSON 敏感键文本漏过滤 / 高 | 旧 regex 对 `{"api_key":"INVENTED_ONLY"}` 保留假值；foundation 增加引用键支持 | task8 容器最小忠实旧逻辑复现 + 修后导入通过；本轮 [storage 回归](<../tests/unit/storage/test_storage.py>) 在 146 内通过 |
| SQLite 原始索引列漏脱敏 / 高 | 旧 SQL 将原始敏感 session ID 写入索引，JSON 虽已脱敏；现在索引/文件名拒绝会被脱敏的 ID，避免碰撞 | 同上；[RunStore](<../src/autoteacher_m0/storage/schema.py#L23-L33>) 与 [safe_id/sanitize](<../src/autoteacher_m0/storage/artifacts.py>) 已核 |
| 字典 key 本身 secret/sentinel 泄漏 / 高 | 旧 sanitize 只处理键对应值，假 `sk-` 键仍落 Trace；现在对键本身过滤并分配不碰撞替代键 | task8 独立容器已检验 3 条目保留与 sentinel key；最终 storage 回归通过 |
| 失败/部分 usage 丢失已知 extra fee / 高（Lead 先发现） | evaluation 的 reservation 保留 fee，缺失与部分 usage 不退款，权威实际总账单不重复加费 | task8 独立容器确认；最终 [accounting 回归](<../tests/unit/accounting/test_accounting.py>) 通过 |
| 单 experiment guard 不等于全局预算 / Live 准入阻塞 | 新增固定 scope 的持久 [BudgetLedger](<../src/autoteacher_m0/accounting/ledger.py>)；pending 保留、BEGIN IMMEDIATE、逐 reservation 保存原路由价格、重启政策不可静默放宽 | task8 独立 16 OS 进程争用 5 cap、跨 route、restart、费用、重复结算均通过；最终 [ledger 回归](<../tests/unit/accounting/test_ledger.py>) 通过；**未接入 SDK Live** |
| 任意 cleanup rc=1 被当作不存在 / 高可靠性风险 | 旧 image runner 未区分 not-found 与 daemon/权限失败；security 改为每次 rm 后独立官方 ps 精确查询，非0/残留/timeout/OSError 都阻断 | [修复](<../src/autoteacher_m0/security/docker_runner.py#L146-L173>) 已静态核对；8 项 mock cleanup 回归包含在最终 146 内通过；不冒称 image runner OS 执行过 |

修前复现使用已经完整读取的旧 regex/SQL/字典逻辑的最小忠实重现，**不是**对未冻结旧仓库执行过全套测试的声明。最终所有上述实现已纳入冻结 SHA，审计者独立复跑没有发现新的离线设施阻断缺陷。

预算重点另覆盖在途费用/Token预留、恰到硬上限、重试计 request/step、double settlement、保守缺失量、actual invoice、超预留如实记账后 fail-closed、线程/进程竞争、跨路由累计、更严 case cap。SQLite 路径、scope、完整价格/上下文上界必须由未来可信控制器固定；换库/换 scope 或让候选写库不能算预算保护。默认 CLI Mock 使用 experiment guard，不能称它实现了跨 Live 实验的全局约束。

## 5. 验收边界与剩余门槛

| 领域 | 已验证 | 仍不能宣称 |
|---|---|---|
| E1 / H1–H2 | 静态官方 wheel ABI映射、Mock smoke 3/3、错误包装/预算/脱敏逻辑 PASS | 真实 SDK 初始化/退出/模型 3/3/JSON/真实错误与usage/版本溯源 BLOCKED；不可达 Adapter 映射不是 SDK 运行 |
| E2 / H3 | 官方 npm ABI 的严格构建与 registry 8/8 PASS | 模型发起工具调用3/3、完整 Runtime profile 安装/移除、SDK-wheel 0.2.2rc2 与插件 ABI 0.2.1-rc.2 联调 BLOCKED |
| E2-03 精确差异 | missing/wrong-type 是 native schema 拒绝；空白是项目语义验证返回 INVALID_ARGS | 原生 DSL 无 minLength/pattern，不能把空串测试称 native wire 拒绝；严格验收需维护者明确判断 |
| E3 / H4 | 项目 Mock JSONL、双 home 正常 API namespace、错误/中断包装 PASS | 真正 DSH 进程重启恢复3/3、真实JSONL/工具事件映射/同ID双home API隔离 BLOCKED；home/cwd 不是OS边界 |
| E4 / H5 | 20×2公共Mock、独立session/run、JSON/SQLite/md、故障 EVAL_ERROR/null、关系规则和明确泄露负例 PASS | Live≥6对、真人学习收益、真正隐藏集/评分器保密部署、独立人类语义盲审均未验证 |
| E5 / H6 | gate始终拒绝；伪MD/env不能开启；实际外部rootfs负向probe PASS | P03独立授权服务/受保护可信部署、实际合并危险工具禁用、session-log实际关闭、凭据流向、image runner/Dockerfile OS执行仍BLOCKED |
| H7 | 费用/预留/并发/持久scope组件及synthetic记账 PASS | 当日真实价目、SDK所有billable steps/重试/压缩/Judge真实计费、输出/上下文上界、外部Live watchdog与真实结算未完成 |

公开标签与规则只在公开 Mock 测试平面使用；候选 API 只收 RunRequest，但 Python 对象分离不是敌对代码隔离。本轮 OS probe 的假 private labels 不可读，不证明已部署真实私有评估工作流。脱敏是已知模式与假哨兵的防御，不保证识别任意未知秘密。

[官方默认路由记录](<ROUTE_DECISION.md>) 仍为 deepseek-official/deepseek-flash，实际模型版本与批准均未验证；无自动 fallback。OpenRouter 未测、OpenCode Go 第三方接入 UNVERIFIED 是非依赖 optional，不因其未通过降低主渠道结论，也不能借它们替代未运行的主渠道。

## 6. owner 证据交叉核验与残余风险

- owner 的 [146测试](<../artifacts/integration/final-tests.log>)、[lint](<../artifacts/integration/final-lint.log>)、[插件](<../artifacts/integration/final-plugin.log>)、[build](<../artifacts/integration/final-build.log>)、[安装验收](<../artifacts/integration/final-installed.log>) 与 [最终比较](<../artifacts/integration/final-public/comparison.md>) 已核读/核摘要；以上不是本轮独立 stdout 文件。
- [威胁模型](<THREAT_MODEL.md>) 中内存 OOM kill、PID耗尽、Podman deadline、fresh scratch恢复的实际日志是 security 执行，本审计者交叉核验，不冒称全部独立重跑；本轮独立重跑的是上述外部负向 OS probe。
- kernel/LXC/Podman/可信依赖属于 TCB；本地 rootfs 与命名空间不是绝对隔离。无可用镜像/registry 权限，生产 image runner 和 Dockerfile 验收不能由 rootfs 结果推导。
- source / manifest / artifact 摘要用于来源关联，不代表已获维护者安全审查。公开 Mock 产物中 git_sha 保持 UNRECORDED，由独立 manifest 关联这一次冻结运行，不倒填历史 SHA。
- 所有四个独立测试容器退出后，已用官方 engine `ps --all` 精确名称查询确认均不存在；再次核对 manifest 自身与 74 个工作树输入摘要全部不变，`git diff --check` 通过，工作树仅新增本审计文档。代码变化需要新 SHA 与重新回归；文档归档提交不冒充冻结实现提交。

**审计建议：接受已证实的离线设施交付，继续保持 Live fail-closed；在独立工程与人工准入及真实 E1–E5 必需证据完成前，维持 DECISION PENDING。**
