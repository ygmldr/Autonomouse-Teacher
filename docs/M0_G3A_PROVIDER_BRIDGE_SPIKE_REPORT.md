# M0 G3-A 无 Key Provider Bridge 可行性 Spike 报告

- 版本：G3-A-PROVIDER-BRIDGE-v1（2026-11-16 UTC）
- 执行者：G3-A 独立执行 agent（与实现者 `verify2` 分离）
- 任务基线：`ce899ec11b6ce4f02cd91afdf285ec23b593ccb3`
- 交付时观察到的 HEAD：`28e260ded339498945cfd0bf5eb530003aead1da`（任务期间其他工作新增 `53d7ba5`、`28e260d`；G3-A 文件均为未跟踪新增，未修改 `src/`/DSH 核心）
- 范围：**仅合成 fixture，无真实 Key、无模型、无 HTTP/外网、无 Live**
- 裁定：**PASS（限定范围）** — 见 §0 与 §9；**不是 G3-B/G4/G5/Live 授权，不是 GO**

## 0. 结论

在锁定版本真实 DSH `0.2.2-rc.2`（Node SEA runtime，SHA-256 `1cc41d5a…`）中，通过**公开 Cordis `LlmAdapter` 扩展**注册一个非真实 provider 路由 `g3a-bridge-test` / `bridge-v1`，把真实组装后的 `GenerateOptions` 经 **stdio NDJSON** 交给独立的 Python fake-provider 进程，并把它返回的 `StreamChunk` 交回 DSH；真实 DSH SDK/Session 收到了响应、工具调用与 synthetic usage，外部进程收到了完整请求，request identity 与原始字节 SHA-256 在 bridge trace、Python receipt、ack 三处一致。

本轮真实运行结果（新 UTC、新 argv、新日志，不复用旧证据）：

| 运行 | 结果 |
|---|---|
| Bridge 6-case 真实 SDK suite | **exit 0，PASS**；6 cases，7 次 bridge 请求，7 条 trace，0 model/0 HTTP |
| Guard 原生测试 | **exit 0，15/15 pass** |
| Skill Lookup 原生测试 | **exit 0，8/8 pass**（0.2.1-rc.2 声明测试依赖；见 §7 的 0.2.2 harness 限制） |
| 既有 synthetic provider suite（PR2 冻结 stage） | **exit 0，17 cases PASS**；15 run/16 synthetic invocation/0 model/0 HTTP |
| Adapter `AbortSignal` 补充测试（真实 `LlmRuntime`，非 SDK） | **exit 0，1/1 pass** |
| merged `--dump-config` | **exit 0**；`llm-deepseek` disabled、bridge/skill 行存在、guard 不在 profile |

**明确不能从本轮推导**：不是真实模型/Live 证据，不是生产 adapter，不是 Key/网络代理，不是费用/预算桥，不是 G3-B/G4/G5 的开工授权。总体上 M0 的 `DECISION PENDING` 不变。

## 1. 问题、范围与非目标

**问题**：锁定版本真实 DSH 能否通过公开 Provider 扩展，把模型请求交给外部受控 Bridge，并接收响应？

**范围**：

- 只新增 `spikes/g3a-provider-bridge/`、本报告、`artifacts/g3a-*`/`artifacts/review-packet-g3a-*`。
- 不改产品 `src/`、不改 DSH 核心、不改 PR2 冻结产物；不 commit。
- 真实 DSH 运行/Node 测试只在固定 rootfs 容器；宿主只做 Git/哈希/JSON/podman launcher。
- 0 真实 Key/模型/外部付费 HTTP；不读 `/root/.config/autoteacher`。

**非目标**：G3-B、G4、G5、Live、真实 DeepSeek 路由、真实 Key 注入、生产 adapter、预算/计费、教学效果或 RSI 证据。

## 2. 环境版本与哈希

| 项 | 实际值 | 依据 |
|---|---|---|
| 固定 rootfs | normalized tar **`25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0`** | 运行前/清理后重算一致；`tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner` |
| rootfs 运行前漂移 | **`9d1d4e84…`**（多出空 `/var`、`/var/tmp`，mtime 17:36，非本任务创建） | 现场核实后只删除空目录，恢复 canonical；未删除/改写任何非空文件 |
| Python deps | normalized tar **`e07729d7997944417b1c25531749b3e6e5e34aa4248f01dc8f370282082ecb98`** | 清理宿主导入探测产生的 `yaml/__pycache__` 后重算一致 |
| Node（rootfs） | `v22.23.2`，`/usr/bin/node` SHA-256 `3517c2df0b2f8cd7f422b4b8450ef81c6889f08eb03e281d6de9079b15e6a327` | 容器内 `node --version`；`sha256sum` |
| Python（rootfs） | `3.11.15`，`/opt/python/bin/python3.11` SHA-256 `cd947cb6d5b3f8589a2a4708198dc104474e47876c6b8215ab8b410592ab7cc1` | 容器内/receipt `python` 字段 |
| 真实 DSH runtime | `0.2.2-rc.2`，SHA-256 **`1cc41d5a8745a5b9d47c8604e44f23eb8af2d8ca02b2afa0be101d5f71be6ea4`**，182,717,632 bytes | `--version`；容器内 suite 断言 |
| Python SDK / runtime wheel | `0.2.2rc2` / `0.2.2rc2` | `artifacts/foundation/deps/*.dist-info` |
| 冻结 DSH target stage | normalized tar **`f8f7520364cd07084012783fd6c3c99707aac8d5b0851253375e05d6ca14901b`**，6530 files | 只读重算 |
| 冻结 `runtime/node_modules` | normalized tar **`2884de23…`**，19 个 `@deepseek-ai` 包 | 与 stage 内拷贝逐项一致 |
| `runtime/skill` | normalized tar `636bb021…` | 与冻结 target 一致 |
| native cache / pkg cache | `eb8a1da2…` / `6c4dc150…`，pkg cache **4857** files | 与冻结 target 一致 |
| native binding | `40c34d27…acc70f`，mode `0444` | suite 容器内断言 |
| pkg `system.node` | `dfa6d586…b21487` | suite 容器内断言 |
| 构建 TypeScript | `5.9.3`（`plugins/offline-fixture/node_modules`；与冻结 target 的 package.json hash 相同） | build meta |

隔离参数（所有真实运行）：`--network none`、`--http-proxy=false`、`--unsetenv-all`、uid 65534、`--read-only`、`cap-drop ALL`、`no-new-privileges`、`/tmp` 与 `/work` noexec tmpfs、pids/mem/cpu 限制。suite 首行 `isolation` 记录了 uid/mount flags/环境变量名/cgroup。

**环境侧写处理（审计注意）**：podman `--rootfs` 会为不存在的 bind-mount target 在 rootfs 内创建空目录；本轮构建在 `/src`、`/spike`、`/npm`、`/fixtures`、`/out` 留下空目录，并写入了空 `/etc/resolv.conf`，已逐一核验为空后删除；`/var` 同样为空并删除。宿主侧一次只读依赖探测生成了 `deps/yaml/__pycache__`，已删除。最终 rootfs/deps 恢复 canonical；历史证据未被覆盖或改写。详见 `artifacts/g3a-provider-bridge/env/identity.json`。

## 3. 公开 Provider 扩展 API 证据（锁定源码）

以下均来自冻结 stage `artifacts/m0-runtime-integration/stage/target/runtime/node_modules/@deepseek-ai/dsh-llm`（`0.2.2-rc.2`，package.json SHA-256 `88e094f5…`），不是猜测：

| API | 位置 | 本轮实际使用 |
|---|---|---|
| `LlmAdapter` 抽象类；只有 `stream()` 是抽象方法，`providerInfo`/`providerRetryPolicy`/`resolveModel`/`prepareCall` 有默认实现 | `src/index.ts:223-318` | `BridgeAdapter extends LlmAdapter`，只覆写 `stream`、`resolveModel`、`providerRetryPolicy` |
| `ctx.llm.registerAdapter(providers, adapter)`；路由原子注册；`0.2.2-rc.2` 的 `LlmAdapter` 抽象契约 | `src/index.ts:416-470` | `ctx.llm.registerAdapter(['g3a-bridge-test'], new BridgeAdapter(...))` |
| `llm/stream` waterfall；`GenerateOptions` 完整请求 | `src/index.ts:63-78`，`src/types.ts:564-625` | bridge 在真实 `llm/stream` 下游被调用；插件本身是该 waterfall 的 adapter 终点 |
| canonical `StreamChunk`：`block-start`/`text-delta`/`reasoning-delta`/`tool-call-delta`/`block-end`/`usage`/`finish`；usage 必须在 finish 前；block index 关联 | `src/types.ts:491-506` | Python 返回的每一帧都经 `normalizeChunk()` 白名单重建，不直接转发任意 JSON |
| `FinishReasonMap`：`stop`/`tool-calls`/`max-tokens`/`aborted`/`error`；error/aborted 带 `LlmFailure` | `src/types.ts:163-179` | Python `stop`、`tool-calls`、`error` 均实际产生并被 DSH 记录 |
| `TokenUsage`：input/output 必填，cache/total/reasoning 可选 | `src/types.ts:182-207` | synthetic usage `11/5/cacheRead 2/total 18` 被 `assistant/message.data.usage` 原样保存 |
| runtime 对 adapter 抛错/中止的统一归一：`adapterFailureChunk` 生成 `finish {kind:'error'}` 或 `{kind:'aborted'}` | `src/index.ts:1083-1181`，`1203-1213` | EOF、fake error、SIGTERM/AbortSignal 三条路径均由该归一逻辑落成 DSH 事件 |
| `ToolSchema`：`name`/`description`/`parameters` JSON Schema | `src/types.ts:517-530` | `request/header.tools[0]` 为真实 `skill_lookup` schema；Python receipt 保存同一 schema |
| 工具注册：公开 `ctx.tools.register` / `defineTool` | `dsh-tools/src/index.ts:128`，`dsh-tools/src/schema.ts:555` | 真实 `skill_lookup` 插件在 bridge suite 中被真实调用 |
| 公开离线先例：`plugins/offline-fixture` 的 `LlmAdapter`/`registerAdapter`/`llm/stream` | `plugins/offline-fixture/src/index.ts:36-122` | 采用其“显式 opt-in + 路由校验 + synthetic 标记”模式，但**新增外部进程 transport** |

**实际事件顺序**（echo，来源于 DSH Session JSONL 与 SDK `result.events`）：

1. `agent/inbox/spliced` → `turn/start` → `step/start`
2. `system/message` → `user/message`（真实用户）→ `user/message`（runtime-context snapshot）
3. `request/header`（`provider=g3a-bridge-test, model=bridge-v1, maxTokens=256`，`tools=[skill_lookup]`，`reason=initial`）
4. 外部 Python 进程收到请求并写 receipt；bridge 记录 `request → spawn → ack → chunk×6 → finish`
5. `assistant/message`（`stream` 保留 2 个 `text-chunks`、block-end、usage、finish；`source.kind='model'`）
6. `step/end` → `turn/end {kind:'completed'}`

工具轮的真实事件顺序：`request/header` → assistant `tool-call` → `tool/call` → `tool/result`（`isError=false`，真实 `skills.json` 内容）→ 第二次 bridge 请求（`tool-final`，request/header **不会**为同一 turn 的第二个 step 再发一条事件）→ 最终 assistant `G3A_TOOL_RESULT:binary_search:3:false` → `turn/end completed`。

## 4. 实现

### 4.1 文件

| 路径 | 说明 |
|---|---|
| `spikes/g3a-provider-bridge/src/index.ts` | 公开 `LlmAdapter` 插件；`name`/`inject=['llm']`/`provider`/`model`/`apply` |
| `spikes/g3a-provider-bridge/fake/fake_provider.py` | 独立 Python synthetic provider；无 HTTP/Key/DSH import |
| `spikes/g3a-provider-bridge/config/bridge.patch.yml` | 目标 profile overlay；仅插入 `/probe/runtime/bridge/lib/index.js` 与 `/probe/runtime/skill/lib/index.js` |
| `spikes/g3a-provider-bridge/run/worker.py` | 真实 SDK 会话 worker；每个 case 独立进程 |
| `spikes/g3a-provider-bridge/run/suite.py` | 6 case + merged-config 断言 |
| `spikes/g3a-provider-bridge/scripts/build.mjs` | 容器内 bridge 编译 |
| `spikes/g3a-provider-bridge/scripts/build-skill.mjs` | 容器内 0.2.2 类型重建 skill（产物 hash 与 PR2 冻结值相同） |
| `spikes/g3a-provider-bridge/scripts/{build,run-suite,run-native-tests}.sh` | 容器运行脚本 |
| `spikes/g3a-provider-bridge/test/adapter-signal.test.mjs` | 补充 AbortSignal 测试（真实 `LlmRuntime`，非 SDK） |

### 4.2 Bridge 行为

- **显式 opt-in**：`AUTOTEACHER_G3A_BRIDGE=1`；固定 Python `/opt/python/bin/python3.11`、固定 `/probe/...` fake 路径、trace/receipt 目录必须在 `/work/g3a/` 下；真实 provider 列表必须为空，否则拒绝注册。
- **路由/请求校验**：只接受 `g3a-bridge-test`/`bridge-v1`，辅助 `purpose` 拒绝，`sessionId`/`signal`/`maxTokens 1..1024` 必需；只允许 text/reasoning/tool-call/tool-addition/tool-removal，工具只允许 `skill_lookup`；image/file 拒绝。
- **transport**：`spawn('/opt/python/bin/python3.11', ['-B','/probe/bridge/fake_provider.py'], {shell:false, stdio:['pipe','pipe','pipe'], env: 白名单})`；一行 JSON 请求 + NDJSON 响应。
- **request identity**：bridge 用 `crypto.randomUUID()` 生成 `requestId`；对写入子进程的**原始行字节**计算 SHA-256；Python 对同一行计算并写入 receipt/ack；bridge trace 与 suite 断言三者相等。
- **chunk 校验**：`normalizeChunk()` 只接受 canonical 类型/字段；`requestId` 不匹配、未知 frame、非法 JSON、越界 index/usage 都转为 `LlmError`，不转发子进程任意对象。
- **终止/清理**：finish 后关闭 stdin 并等待子进程退出；超时/SIGKILL；`options.signal` abort 时写 `cancel` 帧并升级 SIGTERM/SIGKILL；Python 侧设置 Linux `PR_SET_PDEATHSIG=SIGTERM`，runtime 被 SIGTERM 时子进程不会成为孤儿。
- **trace**：`/work/g3a/<case>/bridge/bridge-<uuid>.jsonl` 记录 `request/spawn/ack/chunk/finish/abort-signal/cleanup` 与 `requestSha256`；Python receipt 记录完整 `messages`/`tools`/`roles`/pid/ppid/UTC。

### 4.3 Profile

`config/bridge.patch.yml` 与 `sdk-minimal` 组合；真实 `llm-deepseek`、session-log-deepseek、工具类/终端类行 disabled；插入 bridge 与既有 `offline-public-skill`。merged config（`--dump-config`）实际包含：

```yaml
- id: llm-deepseek
  disabled: true
- id: g3a-bridge-provider
  name: file:///probe/runtime/bridge/lib/index.js
- id: offline-public-skill
  name: file:///probe/runtime/skill/lib/index.js
```

**不包含** `runtime-budget-guard`：G3-A 只验证 Provider Bridge，不把 guard 组合结论混入本轮；guard 原生测试另列。

## 5. 真实命令与原始结果

### 5.1 构建

容器 argv（完整形态见 `scripts/build.sh`，日志 `artifacts/g3a-provider-bridge/logs/build-2.log`）：

```sh
podman run --rm --name g3a-bridge-build \
  --network none --http-proxy=false --unsetenv-all \
  --env PATH=/usr/bin --env HOME=/work --env G3A_BUILD_IN_CONTAINER=1 \
  --read-only --cap-drop ALL --security-opt no-new-privileges --user 65534:65534 \
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=32m,mode=1777 \
  --tmpfs /work:rw,noexec,nosuid,nodev,size=256m,mode=1777 \
  --mount type=bind,src=spikes/g3a-provider-bridge,dst=/src,ro=true \
  --mount type=bind,src=plugins/offline-fixture/node_modules,dst=/npm,ro=true \
  --mount type=bind,src=artifacts/g3a-provider-bridge/stage/runtime/bridge,dst=/out,rw=true \
  --rootfs artifacts/security/rootfs /usr/bin/node /src/scripts/build.mjs
```

实际 exit **0**，关键输出：

```json
{"kind":"g3a-bridge-build","node":"v22.23.2","typescript":"Version 5.9.3",
 "dshLlmVersion":"0.2.2-rc.2","dshLlmPackageJsonSha256":"88e094f569429dea011cf9c05dbf63a09f55a07e50b5d6a6187ea150ada2c8bd",
 "inputSourceSha256":"57946f31bf073c213bc4b994bc7d48512582b2eb8765c99b70d4098ae720c123",
 "builtJs":{"sha256":"d5dbd3446c1b6baae3c2df376bc8ea03f19e1bb7ced6a32320f73f009eceab11","bytes":21720}}
```

skill 重建 exit **0**：source `a618fb02…15346`、built JS `521bc0f1…3b0b`、skills `6988fc43…5300`，与 PR2 冻结 target 的 skill 产物一致。

### 5.2 真实 DSH SDK bridge suite

```sh
podman run --rm --name g3a-suite-final \
  --network none --http-proxy=false --unsetenv-all \
  --env PATH=/opt/python/bin:/usr/bin --env HOME=/work/user-home --env PYTHONPATH=/deps \
  --env PYTHONDONTWRITEBYTECODE=1 --env TMPDIR=/tmp \
  --read-only --cap-drop ALL --security-opt no-new-privileges --user 65534:65534 \
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=32m,mode=1777 \
  --tmpfs /work:rw,noexec,nosuid,nodev,size=256m,mode=1777 \
  --mount type=bind,src=artifacts/g3a-provider-bridge/stage,dst=/probe,ro=true \
  --mount type=bind,src=artifacts/foundation/deps,dst=/deps,ro=true \
  --rootfs artifacts/security/rootfs /opt/python/bin/python3.11 /probe/run/suite.py
```

实际 exit **0**。逐 case（来自 `logs/suite-final.log` 的 `kind:"case"`）：

| case | SDK 结果 | final_response / error | bridge 请求 | trace | session |
|---|---|---|---:|---:|---:|
| echo | finish `completed` | `G3A_BRIDGE_ECHO:G3A_PUBLIC_ECHO_a7f3` | 1 | 1 | 1 |
| recall（新 worker 进程 resume） | `completed` | `G3A_BRIDGE_RECALL:G3A_PUBLIC_ECHO_a7f3` | 1 | 1 | 1 |
| tool | `completed` | `G3A_TOOL_RESULT:binary_search:3:false` | 2 | 2 | 1 |
| eof | `error` | `finish_reason=error`，`turn/end{code:STREAM_CLOSED}` | 1 | 1 | 1 |
| error | `error` | `turn/end{code:SERVER,message:G3A_FAKE_PROVIDER_ERROR}` | 1 | 1 | 1 |
| cancel（SIGTERM runtime） | `TransportClosedError` | `turn/end{kind:aborted,reason:disposed}`（Session 文件） | 1 | 1 | 1 |

summary 原文：

```json
{"cases":6,"bridge_requests":7,"bridge_traces":7,"echo_streaming_deltas":2,
 "tool_roundtrip":true,"session_resume":true,"eof_failure_surfaced":true,
 "error_finish_surfaced":true,"runtime_sigterm_child_reaped":true,
 "tool_schema_seen":true,"guard_in_profile":false,
 "real_model_calls":0,"http_calls":0,"network_enabled":false,
 "production_adapter_used":false,
 "status":"PASS-real-dsh-sdk-public-provider-bridge-synthetic-only"}
```

**request identity 实例**（echo）：bridge trace `requestSha256`、Python receipt `rawRequestSha256`、ack `rawRequestSha256` 均为 `a9dba4c825683543c26e9a785def41f094353ed0d5aae7c7a218c9697aa8f348`；Python pid 28，ppid 15（DSH runtime），`parentDeathSignalArmed=true`。7 次请求全部满足 `realModelCalls=0,httpCalls=0,networkUsed=false`。

**SSE/streaming 证据**：echo/recall 的 DSH `assistant/message.data.stream` 保留 `text-chunks: ["G3A_BRIDGE_","ECHO:G3A_PUBLIC_ECHO_a7f3"]`，即 Python 两个独立 `text-delta` 未被合成一个；bridge trace 对应 `chunk:text-delta` ×2。

**Usage**：`assistant/message.data.usage` 精确为
`{"inputTokens":11,"outputTokens":5,"cacheReadTokens":2,"cacheWriteTokens":0,"reasoningTokens":0,"totalTokens":18}`（echo、recall、tool 两次调用相同）。这是 fixture 常量，不是 tokenizer/账单。

**Session**：recall case 由**新的 worker 进程** `resume_session('g3a-echo')`；Python receipt 的 `messageCount=5`、`roles=[system,user,user,assistant,user]`，包含前一轮 assistant 与两个真实用户消息，最终从历史中召回 nonce。Session 文件为真实 DSH v4 JSONL。

### 5.3 原生测试（固定容器）

| 测试 | 命令 | 结果 |
|---|---|---|
| Guard | `/usr/bin/node --test /probe/native/guard/tests/guard-pr1.test.mjs`（`RBG_TEST_PYTHON=/opt/python/bin/python3.11`） | exit **0**，15 pass / 0 fail |
| Skill Lookup | `/usr/bin/node --test /probe/native/skill-lookup/test/plugin.test.mjs`（挂载插件声明的 `plugins/skill-lookup/node_modules`，0.2.1-rc.2） | exit **0**，8 pass / 0 fail |
| Synthetic Provider（PR2 继承 suite） | `/opt/python/bin/python3.11 /probe/suite.py`（`/probe`=PR2 冻结 stage，`AUTOTEACHER_OFFLINE_FIXTURE=1`） | exit **0**，17 cases；summary `PASS-real-engine-synthetic-fixture-only`；15 run/16 invocations/0 model/0 HTTP |
| Bridge adapter signal（补充） | `/usr/bin/node --test /probe/runtime/bridge/test/adapter-signal.test.mjs` | exit **0**，1/1；`finish.reason.kind='aborted'`，child exit 0 |

### 5.4 merged config

`runtime --profile sdk-minimal --patch /probe/config/bridge.patch.yml --dump-config` exit **0**；断言 `llm-deepseek.disabled=true`、`session-log-deepseek.config.enabled=false`、`plugin-package-inventory-deepseek.disabled=true`、bridge/skill 行存在、无 `runtime-budget-guard`、无启用 `llm-pi-ai`。原始 stdout 在 `logs/suite-final.log` 的 `kind:"merged-config"` 行。

## 6. 支持矩阵（实际验证 / 限定）

| 能力 | 状态 | 证据与说明 |
|---|---|---|
| 公开 Provider 扩展注册 | **PASS** | `ctx.llm.registerAdapter`；真实 runtime 加载 `/probe/runtime/bridge/lib/index.js`；`request/header` 使用 bridge 路由 |
| 请求经 Bridge 传递 | **PASS** | Python receipt 保存完整 `messages`/`tools`/`maxTokens`/`sessionId`；原始行 SHA 三处一致 |
| 响应经 Bridge 返回 DSH | **PASS** | echo/recall/tool final response 与 DSH `assistant/message` 完全一致 |
| 流式 chunks | **PASS** | 2 个独立 `text-delta`；DSH stream 保留 `text-chunks` 两项；block-start/block-end/usage/finish 顺序合法 |
| Tool Schema | **PASS** | `request/header.tools[0].name='skill_lookup'`；schema 原样到达 Python receipt |
| Tool call / result 往返 | **PASS（synthetic 选择）** | Python 脚本产生 tool-call；真实 DSH 执行真实 `skill_lookup`，`tool/result isError=false`；第二次请求携带真实 tool message。**不是模型自主选择工具** |
| Session 续接 | **PASS** | 新 worker 进程 `resume_session`；5 条组装消息含 prior assistant；召回 nonce |
| 异常：子进程 EOF | **PASS（error 语义）** | 无 finish → DSH `turn/end{kind:error,code:STREAM_CLOSED}`；无成功 final，无 usage |
| 异常：子进程 error finish | **PASS（error 语义）** | `finish {kind:'error',failure:{code:'SERVER'}}` → DSH `turn/end{kind:error,code:SERVER}` |
| 取消：runtime SIGTERM | **PASS（runtime 级）** | 活跃 slow stream 时 SIGTERM runtime；bridge trace 出现 `abort-signal` + `cleanup aborted=true exitCode=0`；Python 子进程被 PDEATHSIG 回收（`fake_alive_after_runtime_term=false`）；Session `turn/end{aborted,reason:disposed}` |
| 取消：单 turn、runtime 存活 | **UNVERIFIED** | SDK `DeepSeekHarness`/`Session` 无 cancel/abort 方法；无法通过公开 SDK 在不终止 runtime 的情况下取消单个 turn |
| 取消：adapter `options.signal` | **PASS（补充，非 SDK）** | 真实 `LlmRuntime` + `AbortController`：首个 chunk 后 abort → 最终 `finish{kind:'aborted'}`，child exit 0 |
| Usage 透传 | **PASS（synthetic 常量）** | DSH `assistant/message.data.usage` 与 Python usage 完全一致；不是真实计量 |
| 并发请求/背压 | **UNVERIFIED** | 未测多 stream 并发、慢消费者、超大 frame |
| image/file/reasoning/tool addition | **UNVERIFIED/不支持** | bridge 显式拒绝 image/file；reasoning 允许但未测；tool-addition 未测 |
| 真实模型/Key/HTTP/Live | **NOT RUN（BLOCKED）** | 未授权；0 网络/0 HTTP/0 Key |
| 生产 adapter / 费用桥 / 安全沙箱 | **NOT CLAIMED** | spike 不是生产 adapter；bridge 子进程与 runtime 同容器同 uid，不是额外 OS 沙箱 |

## 7. 失败矩阵 / 迭代记录（保留，不把失败当成功）

| 轮次/现象 | 实际错误 | 处理 | 是否证据 |
|---|---|---|---|
| recall 首次 suite | `JsonRpcError: session "g3a-echo" not found` | 我方 worker 把 recall 的 home 错设为 `/work/g3a/recall`；改为复用 echo home 后重跑 | 失败日志保留在 `logs/suite-first.log`/`suite-second.log`；不作 PASS 证据 |
| tool 首次断言 | `request_headers(tool)` 只有 1 条 | DSH 对同一 turn 的第二个 step 不再发 `request/header`；bridge 实际有 2 次请求/2 trace。断言改为 1 header + 2 receipts | 失败日志保留 |
| cancel 首次 | trace 无 `ack` | `G3A_BRIDGE_READY` 在请求写入前发出，suite 过早 SIGTERM；增加 `G3A_BRIDGE_STREAMING`（首个 chunk 后）再杀，确保真正活跃流 | 失败日志保留 |
| Skill 原生测试（0.2.2 依赖） | `invalid config: $.mode expected nullable but got native`（`ToolRuntime` 0.2.2 配置不接受测试 harness 的 `mode:'native'`） | 使用插件 package.json 声明的 0.2.1-rc.2 测试依赖；8/8 pass。**这是测试 harness 版本限制，不是插件在 0.2.2 runtime 的失败**；0.2.2 下插件产物由 bridge tool case 实际执行 | 记录为 BLOCKED（0.2.2 原生 test harness），不伪造 PASS |
| 首次 bridge build | `TS2307`/CommonJS 模式错误 | 容器内把依赖复制到真实 `node_modules` 目录、复制 `package.json` 启用 ESM；重跑 exit 0 | 构建失败日志保留 |
| rootfs/deps 漂移 | rootfs `9d1d4e84`（空 `/var`）、deps `0358…`（宿主 `yaml/__pycache__`）、podman mount target 空目录/resolv.conf | 只删除空目录/零字节文件；恢复 rootfs `25491e45`、deps `e077`；未覆盖任何历史证据 | 环境记录见 `env/identity.json` |

## 8. BLOCKED / UNVERIFIED（不得写成 PASS）

1. **真实模型 / Key / 外部 HTTP / Live**：未执行且未授权；BLOCKED。
2. **DSH 单 turn 取消**：SDK 公开 API 无 cancel；UNVERIFIED。仅验证 runtime SIGTERM 与 adapter `signal` 两条路径。
3. **并发流、背压、帧大小上限、慢消费者**：UNVERIFIED。
4. **image/file block、reasoning、tool-addition/removal**：未测；image/file 被 bridge 显式拒绝。
5. **缺失 usage / 非法 usage 的 DSH 行为**：未测；本轮只测合法 synthetic usage。
6. **guard + bridge 组合**：本轮 profile 不含 guard；F7 类“guard 缺失仍 dispatch”问题未被本 spike 解决。guard 原生 15/15 只证明 guard 自身测试。
7. **子进程 OS 级隔离**：bridge 子进程与 runtime 同容器、同 uid，仅 PDEATHSIG；不是额外沙箱/密钥隔离。
8. **恶意/损坏子进程 frame 的模糊测试**：只有严格 schema 校验与少量负例，未做 fuzz。
9. **生产打包/跨环境可复现**：未做；构建依赖容器内 stage 路径。
10. **真实 provider 路由/重试/HTTP 错误映射**：无 HTTP，未验证。
11. **Skill 0.2.2 原生 test harness**：BLOCKED（0.2.2 `ToolRuntime` config 变化）；不是插件产物失败。
12. **G3-B/G4/G5/Live**：未授权、未执行；不得以本报告作为开工/GO 依据。

## 9. 维护者决策点

1. 是否接受 **G3-A PASS（限定：公开 Provider Bridge + 合成 fixture + 0 Key/0 HTTP）**，并明确它不解锁 Live/GO？
2. 是否要求先补 **DSH/SDK 单 turn 取消 API**（或明确的 RPC cancel 语义）才进入 G3-B？
3. 是否要求 bridge 子进程使用**更窄的 OS 边界**（独立 uid/namespace/只读 argv allowlist/无继承敏感 env）而非当前同容器同 uid？
4. 是否要求 bridge 与 `runtime-budget-guard` 的组合验证（reserve-before-dispatch、settle/fail）作为下一阶段前置？
5. 是否固定 Bridge 协议版本/帧大小上限/超时/重连/并发语义，再允许任何外部受控 Bridge 试点？
6. 是否授权 G3-B（本 agent **不**自行进入）；本轮到 G3-A 报告与审计包为止。

## 10. 证据索引与哈希

完整机器可读清单：`artifacts/review-packet-g3a-28e260ded339498945cfd0bf5eb530003aead1da/manifest.json`、`hashes.sha256`、`diff/`、`source/`、`traces/`、`logs/`、`env/`。

关键文件：

| 文件 | SHA-256 |
|---|---|
| `spikes/g3a-provider-bridge/src/index.ts` | `57946f31bf073c213bc4b994bc7d48512582b2eb8765c99b70d4098ae720c123` |
| `spikes/g3a-provider-bridge/fake/fake_provider.py` | 见 packet `hashes.sha256` |
| `artifacts/g3a-provider-bridge/stage/runtime/bridge/lib/index.js` | `d5dbd3446c1b6baae3c2df376bc8ea03f19e1bb7ced6a32320f73f009eceab11` |
| `artifacts/g3a-provider-bridge/stage/runtime/bridge/build-meta.json` | 见 packet |
| `logs/suite-final.log` | 见 packet `hashes.sha256` |
| `logs/native-guard.log` | 见 packet |
| `logs/native-skill.log` | 见 packet |
| `logs/native-synthetic-suite.log` | 见 packet |
| `logs/native-bridge-signal.log` | 见 packet |
| `env/identity.json` | `403c9c39ba4e179733e57fa67a1a89037c7378989dd7a00cbbbe414de07f8841` |

原始 trace 已从 suite log 的 base64 逐条解码到 `artifacts/g3a-provider-bridge/traces/{bridge,fake,sessions}/`，并用 `*.sha256` 交叉校验；它们不是重新构造的事件。

## 11. 裁定与 STOP

**G3-A 裁定：PASS（限定范围）** — 真实 DSH `0.2.2-rc.2` 能通过公开 Cordis Provider/LlmAdapter 扩展，把真实组装的模型请求交给外部受控 Python stdio Bridge，并把流式响应、工具调用、usage、session 续接、EOF/error 与 runtime SIGTERM 取消语义交回 DSH；全程 0 真实 Key/0 模型/0 HTTP/0 外网。

**不包含**：Live、真实模型、真实 Key、生产 adapter、费用/预算、G3-B/G4/G5。**本报告不签发 GO/CONDITIONAL GO，不签发 LiveGate。执行到此 STOP。**
