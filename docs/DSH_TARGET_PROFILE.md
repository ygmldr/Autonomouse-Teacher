# DSH Target Profile 联调（PR2，无 Key）

- 任务 `task-38`；基线 `fdcfdc9`（PR1 冻结，父 `e8b6e45`）；本任务不 commit
- 结论：**目标 Profile 的 dump-config/静态路由/负测完成；真实 Runtime 只以 synthetic fixture 运行（RBG_BOOT + 1 次 fixture invocation，0 真实模型/HTTP/Key）；真实 DSH Live 与 PR5 仍 BLOCKED**

## 1. 目标 Profile（`config/dsh/target-*.patch.yml`）

- `target-runtime.patch.yml`：在锁定 `sdk-minimal` 上禁用真实 `llm-deepseek` 与全部危险工具/终端/compaction/upload 行；insert `runtime-budget-guard`（guard 版本、fixed synthetic broker policy `/target/runtime/broker-policy.json` + sha256）、`offline-test-only-provider`（`/target/runtime/fixture/lib/index.js`，route/model `offline-test-only`/`fixture-v1`）、`offline-public-skill`（`/target/runtime/skill/lib/index.js`）。无真实 Key/provider 可用路径；guard policy route 与 fixture 一致。
- `target-broker-policy.json`：v1/synthetic/单 route/显式价格/usage policy 的只读 broker 启动策略（sha256 `c67d2bbf…8129`，patch 内固定）。
- `target-runtime-opencode-go.patch.yml`：**STATIC-ONLY** 叠加 `llm-pi-ai` 的 `opencode-go` 路由：`apiKeyEnv: OPENCODE_API_KEY`（占位符，环境不注入）、无 `baseURL`、`reasoning: max`、`retryPolicy.maxRetries: 0`；不做网络/模型/Key 操作。
- guard/工具/route 的源码、README、SDK 17-case 证据见 PR0/PR1 文档；本 PR 只做目标 Runtime 侧联合验证。

## 2. dump-config 与 3 次重启

固定 digest rootfs OCI（`--rootfs`、network none、no exec /tmp+/work、uid 65534、ro root、pids/mem/cpu 限制；宿主未跑 pytest/TS/node）；stage 为当前 worktree 的只读拷贝（69+files，normalized tar `见 manifest`），目标 runtime 挂在 `/target`、repo `/project`、deps `/deps`。

| run | 命令 | exit | merged rows | 结果 |
|---|---|---|---|---|
| restart-1/2/3 | `dsh --profile sdk-minimal --patch target-runtime.patch.yml --dump-config`（独立容器/DSH_HOME） | 0/0/0 | 40 | `scripts/verify_runtime_profile.py` PASS×3 |
| opencode-go static | 同上 + `--patch target-runtime-opencode-go.patch.yml` | 0 | 41 | PASS（route 字段逐项断言） |

merged config 摘要：`llm-deepseek`、tool/terminal/subprocess/jobs/pty/compaction/image-offload/plugin-inventory 等 disabled；`session-log-deepseek.config.enabled=false`；guard 行含 policy/broker 固定路径与 sha；fixture/skill 行存在；`llm-pi-ai` 行含 `opencode-go`（无 baseURL、apiKeyEnv 占位、reasoning=max、maxRetries=0）。无 key 字段（verifier 扫描拒绝 API_KEY/TOKEN/SECRET 等名称字段）。

## 3. 合成运行与 RBG_BOOT/负测

synthetic probe：真实锁定 runtime + Python SDK + fixture + guard，`FIXTURE_JSON`，无真实模型/HTTP/key：

| scenario | RBG_BOOT | FIXTURE_INVOCATION | 结论 |
|---|---|---|---|
| target profile（guard valid） | 1 | 1 | 正常：先 reserve 后 fixture（RBG_RESERVE/SETTLE 各 1）；`real_model_calls=0,http_calls=0` |
| bad guard config（policy sha 错误） | 1 (BOOT_INVALID) | **0** | guard deny-all，provider 前拒绝（无需真实 provider） |
| no-guard variant | 0 | 1 | **F7 缺口复现**：guard 缺失时 synthetic fixture 仍被调用；因真实 provider 全禁用、无 Key/网络，无真实 dispatch，但这不能替代外部 egress/Key 边界；标记 gap，不伪造 PASS |

Profile 静态负测（dump+verifier，均 exit 20/FAIL）：no-guard → `MISSING_REQUIRED_ROW:runtime-budget-guard`；extra-provider（rogue llm-deepseek-api-key）→ `UNEXPECTED_PROVIDER_ROW`；bad broker policy sha → `GUARD_BROKER_POLICY_HASH_MISMATCH`；guard route mismatch → `GUARD_POLICY_ROUTE_MISMATCH`。
未完成/无法由公开 dump 验证：raw tool registry vs agent tool 的完整枚举（dump 仅给插件行；fixture 自身工具限制 + agent tool 事件为间接证据）；broker 不可用/无效只有 guard PR1 测试与 deny-all 静态负测，未在本 PR 的真实 runtime 中触发；真实 provider/网络行为不存在（0 调用）。

## 4. `scripts/verify_runtime_profile.py/.sh`

只读检查：merged rows/guard 名称与 config hash/route/model/工具与危险行 disabled/session-log/no unexpected rows/no key 字段；可选 `--require-opencode-go` 做静态字段断言；`--dump-file`/`--runtime-stderr` 复用已取日志；`--require-boot` 要求观察到的 `RBG_BOOT`。异常 exit 20，绝不作为 Live 开关。`.sh` 仅提供有 shell 的 reviewed 部署；锁定证据容器无 shell，直接以 `/opt/python/bin/python3.11` 调 `.py`。

## 5. 证据与残余 UNVERIFIED

- 证据目录 `artifacts/m0-runtime-integration/`：`manifest.json`（argv/exit/UTC/镜像身份/行数/负测）、`evidence.sha256`、`logs/`（dump/verify/probe/stdout/stderr）、`stage/`（只读输入与 guard/verifier/probe），验证 `cd artifacts/m0-runtime-integration && sha256sum -c evidence.sha256`。
- 残余：真实 provider/egress/Key 边界（PR4）未实现；真实 merged raw tool registry、loader 对 guard import 失败的具体行为（本 PR 复现 guard 缺失 gap 但未完成 OS 外部拒绝）；真实 broker 不可用/崩溃在真实 runtime 的时序；OpenCode Go 静态行不代表已批准/可用（无 Key、无网络、需 PR5）；无 Live/E1–E5 证据；guard/plugin ABI 与锁定 0.2.2-rc.2 已通过 dump/boot 但未做独立第三方审计。
