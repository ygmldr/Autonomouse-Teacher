# G3-A 无 Key 公开 Provider Bridge Spike

**范围：仅合成 fixture。无真实 Key、无模型、无 HTTP/外网、无 Live 授权。**

本目录是 G3-A 独立执行 agent 的最小实验实现：在真实锁定 DSH `0.2.2-rc.2`
Node SEA runtime 中，通过**公开 Cordis `LlmAdapter` 扩展**注册
`g3a-bridge-test` / `bridge-v1` 路由；adapter 把真实组装后的
`GenerateOptions` 经 **stdio + NDJSON** 交给独立 Python 进程
(`fake/fake_provider.py`)，再把该进程返回的 `StreamChunk` 校验后交回 DSH。

- 不修改产品 `src/`、不修改 DSH 核心、不修改 PR2 冻结产物。
- 证据运行全部在固定 `artifacts/security/rootfs` 容器内，`--network none`、
  uid 65534、只读 root、cap drop ALL、no-new-privileges；宿主不执行项目
  Node/TS/Python 代码。
- 本 spike **不是**生产 adapter、不是 Key/网络代理、不是 G3-B/G4/G5/Live
  授权。

## 文件

| 路径 | 作用 |
|---|---|
| `src/index.ts` | 公开 `LlmAdapter` 插件；路由/请求校验、spawn Python、NDJSON 帧校验、signal/abort、trace |
| `fake/fake_provider.py` | 独立 synthetic provider；写 receipt、回显/工具调用/EOF/错误/慢流；Linux PDEATHSIG |
| `config/bridge.patch.yml` | 目标 profile overlay；禁用真实 provider/tool，插入 bridge + 已审查 `skill_lookup` |
| `run/worker.py` | 每个 case 启动真实 Python SDK 与会话；收集原始 trace/receipt/session |
| `run/suite.py` | 6 个真实 SDK case（echo/recall/tool/eof/error/cancel）+ merged-config 断言 |
| `scripts/build.mjs` | 容器内用锁定 `dsh-llm` 类型编译 bridge |
| `scripts/build-skill.mjs` | 容器内用 0.2.2 类型重建 `skill_lookup` 产物（与 PR2 冻结产物 hash 相同） |
| `test/adapter-signal.test.mjs` | 补充：真实 `LlmRuntime` + `options.signal` 取消（非 SDK） |
| `scripts/run-suite.sh` / `run-native-tests.sh` | 容器运行脚本；只调用 podman |

## 构建/运行（仅容器）

先在仓库根目录构建 bridge 和 skill（挂载的 `/src`、`/spike` 等**仅容器内**
路径；podman 会在 rootfs 内创建空 mount target，运行后需清理，见报告）：

```sh
./spikes/g3a-provider-bridge/scripts/build.sh
./spikes/g3a-provider-bridge/scripts/run-suite.sh
./spikes/g3a-provider-bridge/scripts/run-native-tests.sh
```

`run-suite.sh` 要求 `artifacts/g3a-provider-bridge/stage/` 已由构建脚本准备
（含冻结 `runtime/node_modules`、`skill`、`native-cache`、`pkg-cache` 的只读
拷贝）。日志/阶段产物写入 `artifacts/g3a-provider-bridge/`，review packet 在
`artifacts/review-packet-g3a-<sha>/`。

## 协议

bridge → Python（一行 JSON）：

```json
{"v":1,"type":"request","requestId":"<uuid>","provider":"g3a-bridge-test","model":"bridge-v1",
 "sessionId":"...","maxTokens":256,"mode":"echo|recall|tool|tool-final|eof|error|slow",
 "messages":[...],"tools":[...],"system":null,"receiptPath":"...","eventsPath":"..."}
```

Python → bridge（NDJSON）：`ack` → `chunk`（标准 `StreamChunk`）→ `done` /
`cancelled`。bridge 只接受 canonical chunk 形状，校验 `requestId`，并记录
`requestSha256`；Python receipt 与 bridge trace 的 request identity 必须一致。

## 边界

- 支持的 route/model 只有 `g3a-bridge-test` / `bridge-v1`；非该路由、辅助
  purpose、>1024 maxTokens、image/file block、非 `skill_lookup` 工具会被拒绝。
- usage 是固定 synthetic 值 (`11/5/cacheRead 2/total 18`)，不是 tokenizer、
  账单或预算。
- 真实模型/Key/HTTP/Live 未执行；SDK 无 per-turn cancel API，取消证据是
  runtime SIGTERM + adapter `options.signal` 两条路径分别记录。
