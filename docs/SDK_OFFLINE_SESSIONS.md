# SDK 离线会话闭环 — 真实 DSH 引擎 + 显式 offline-test-only fixture

## 0. 结论与适用范围

2026-11-13 UTC，在既有只读容器边界内，用**锁定版本的真实 DSH 引擎**与**真实 Python SDK**
跑通了一个**显式命名的离线测试专用 provider**（`offline-test-only` / `fixture-v1`），
并通过真实 JSON-RPC 驱动了真实 Cordis 工具注册表、Session JSONL、跨进程恢复、
双 home 同 Session ID 命名空间和受控中断恢复。最终原始日志
[`artifacts/sdk-fixture/suite-context-aware.log`](../artifacts/sdk-fixture/suite-context-aware.log)
末尾 summary 精确为：

```json
{"cases":17,"dual_home_bidirectional":true,"http_calls":0,"kind":"summary","production_adapter_used":false,
 "real_model_calls":0,"resume_pairs":3,"sdk_run_calls":15,"status":"PASS-real-engine-synthetic-fixture-only",
 "synthetic_adapter_invocations":16}
```

**这是引擎/会话/工具链路的 synthetic fixture 证据，不是真实模型证据。** 它不签发
E1/E2/E3 的完整验收，不签发 E2 Live / E1b / Live，不构成生产 Adapter 或 Gate 可用性，
也不改变总体 `DECISION PENDING`（另见 [M0_REPORT](M0_REPORT.md)、[ADR-001](ADR-001-runtime.md)）。

本文件只补齐文档与机器清单，不修改实现、断言、生产 Gate/Adapter、上游源码或旧的失败证据。
机器可核对版本见 [manifest.json](../artifacts/sdk-fixture/manifest.json) 与
[evidence.sha256](../artifacts/sdk-fixture/evidence.sha256)。

## 1. 三层证据必须分开记录

| 层级 | 是什么 | 本次是否新增 | 证据位置 |
|---|---|---|---|
| A. 项目 Mock | 项目自身 `MockRuntime`/固定 Mock 响应；**无 DSH 子进程、无 SDK JSON-RPC、无真实 Session** | 未新增；仍是 E4/CLI Mock 证据 | [E4_MOCK_REPORT](E4_MOCK_REPORT.md)、[REVIEW_PHASE2](REVIEW_PHASE2.md)、`artifacts/phase2-integration/` |
| B. 真实 DSH 引擎 + 合成 fixture | 真实锁定引擎二进制 + 真实 Python SDK + 显式 `offline-test-only` LlmAdapter；真实 Session/工具注册表/事件；**无模型、无网络、无 Key** | **本次新增**（本文件） | [`suite-context-aware.log`](../artifacts/sdk-fixture/suite-context-aware.log)、[`build-context-aware.log`](../artifacts/sdk-fixture/build-context-aware.log) |
| C. 真实 DeepSeek Live | 获批主路由上真实 V4.1 Flash 的 E1/E2/E3 必选验收 | **未做，仍 BLOCKED** | [M0_REPORT](M0_REPORT.md)、[SECURITY_APPROVALS](SECURITY_APPROVALS.md)、[ROUTE_DECISION](ROUTE_DECISION.md) |

补充历史：task15 的真实引擎 keyless 子集（initialize/close/空 registry）见
[SDK_NATIVE_DIAGNOSTIC](SDK_NATIVE_DIAGNOSTIC.md)；更早的 keyless 失败见
[SDK_OFFLINE_PROBE](SDK_OFFLINE_PROBE.md) 与 [REVIEW_PHASE2 §5](REVIEW_PHASE2.md#L58-L72)。
那两轮都没有 Session/run/工具调用；本轮才有，但仍属于 B 层。

## 2. 运行身份、窗口与退出码

| 项 | 实际值 | 依据 |
|---|---|---|
| 引擎二进制 | `/deps/deepseek_harness_runtime/runtime/deepseek-harness-sdk-runtime-linux-x64`，SHA-256 `1cc41d5a8745a5b9d47c8604e44f23eb8af2d8ca02b2afa0be101d5f71be6ea4` | 日志 `isolation` 行 + [suite.py#L24-L26](../artifacts/sdk-fixture/stage/suite.py#L24-L26) 的容器内断言 |
| Python SDK / runtime wheel | `0.2.2rc2` / `0.2.2rc2`（`deepseek_harness_sdk`、`deepseek_harness_runtime_bin` 的 METADATA） | `artifacts/foundation/deps/*.dist-info` |
| Runtime CLI | `0.2.2-rc.2`（`--version` stdout） | [`system-inspect.log`](../artifacts/sdk-fixture/system-inspect.log) 末行 |
| Native cache | `/probe/native-cache/.../linux-x64-gnu-napi-v9.node`，SHA-256 `40c34d27...acc70f`，mode `0444`（只读） | 日志 `isolation` 前断言、[SDK_NATIVE_DIAGNOSTIC](SDK_NATIVE_DIAGNOSTIC.md) |
| pkg cache | `/probe/pkg-cache/pkg/dfa6d586.../...`，`system.node` SHA-256 `dfa6d586...b21487`；4857 个文件逐个 `sha256sum -c` OK | [`pkg-cache-files.sha256`](../artifacts/sdk-fixture/pkg-cache-files.sha256)、[`pkg-cache-hash-check.log`](../artifacts/sdk-fixture/pkg-cache-hash-check.log) |
| 共享 rootfs | 归一化 GNU tar SHA-256 `25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0`（含既有空 `./probe`） | 本轮只读重算；与 [LOCAL_OCI_VALIDATION](LOCAL_OCI_VALIDATION.md)、[REVIEW_PHASE3](REVIEW_PHASE3.md) 一致 |
| 共享 Python deps | 归一化 tar SHA-256 `e07729d7997944417b1c25531749b3e6e5e34aa4248f01dc8f370282082ecb98` | 同上 |
| 构建窗口（UTC） | `2026-11-13T23:33:14.805Z` → `2026-11-13T23:33:32.250Z`，job 退出码 **0** | 作者会话 job/settled 记录（见 §4 命令来源）；[`build-context-aware.log`](../artifacts/sdk-fixture/build-context-aware.log) mtime `23:33:31.890Z` |
| 通过运行窗口（UTC） | `2026-11-13T23:36:05.244Z` → `2026-11-13T23:36:46.643Z`，job 退出码 **0** | 同上；日志内部事件时间 `23:36:06.465Z`–`23:36:46.215Z`；文件 mtime `23:36:46.526Z` |
| 用例退出码 | 17/17 `exit_code:0`；17/17 `data.runtime_exit_code:0`；`merged-config` exit 0 | 见 §3.2 |
| 外层退出码说明 | 本次日志自身只记录内层 exit；外层 `podman` job 退出码 0 来自作者会话 job 记录，非日志字段。没有把“外层 0”当作断言通过的唯一理由：日志含完整 summary 且全部内部断言通过。 | 见 §4 |

容器名：构建 `at-m0-sdk-fixture-build`，通过运行 `at-m0-sdk-fixture-suite`。

## 3. 实际覆盖：17 个 case、3/3 跨进程恢复、双 home、真实工具事件

### 3.1 用例与记录结果

suite 在当前 fixture 源码（`source.kind='user'` 过滤修正后）上一次性顺序执行 17 个 case，
每个 case 由独立 `worker.py` 进程驱动一个新的真实运行时进程；case 结果由运行日志
`kind:"case"` 行逐条记录。下表数字全部可从该日志用 §3.4 的命令重算。

| # | case | 合成脚本输入 | 实际断言与结果 |
|---:|---|---|---|
| 1 | `json-pydantic` | `FIXTURE_JSON` | SDK 返回字符串精确为 `{"skill_id":"binary_search","ready":true}`；worker 只把该字符串送进**既有**项目严格校验 `autoteacher_m0.runtime.structured_output.validate_e1_json`，Pydantic dump 精确等于 `{'skill_id':'binary_search','ready':True}`；exit 0，1 次 SDK run，1 次 synthetic invocation |
| 2 | `actual-tool-event` | `FIXTURE_TOOL` | 真实引擎在 `request/header.tools` 中出现真实注册的 `skill_lookup` schema；脚本 provider 发出 1 个 `tool-call`；真实 tools 执行器调用真实插件并产生 `tool/result`（`isError=false`，文本逐字节等于公开 `skills.json` 的 `binary_search` 条目）与最终合成回包；2 次 synthetic invocation（工具轮 + 回包轮） |
| 3–8 | `resume-{0,1,2}-save` / `-new-process` | remember / recall | 3 对跨**新 worker 进程**的 save→recall：`REMEMBERED:PUBLIC_RESUME_i_a7f3` 后新进程 `RECALLED:PUBLIC_RESUME_i_a7f3`；同对 worker PID 不同（30/44、58/72、86/100），Session ID 相同 |
| 9–12 | `home-A/B-save` / `home-A/B-resume` | remember / recall | 两个独立 `DSH_HOME` 使用**相同 Session ID** `same-session-id`；A 只回忆出 A nonce（`RECALLED:PUBLIC_HOME_A_9k2m`），B 只回忆出 B nonce；彼此日志不含对方 nonce（双向 nonce 断言） |
| 13 | `unknown-resume` | `resume_session(nonexistent)` | 明确 `JsonRpcError: session "nonexistent-public-session" not found`；0 次 run/0 次 invocation；suite 断言未创建任何历史 JSONL |
| 14 | `corrupt-save` | remember | 正常写入 1 个公开测试 Session JSONL；随后对**已关闭的**一次性公开日志做显式损坏故障注入，记录 before/after SHA-256 |
| 15 | `corrupt-resume` | `resume_session(corrupt)` | 明确 `JsonRpcError`（corrupt session log: header line is not valid JSON）；0 次 run；不把失败当成功 |
| 16 | `controlled-interruption` | `FIXTURE_INTERRUPT nonce=…` | 等 nonce **真实落盘**后向 runtime 发 SIGTERM；SDK 抛 `TransportClosedError`（phase `active-input`）；pre-recovery Session 日志含 header/inbox/turn/step 与未完成的 `INCOMPLETE_FIXTURE_STREAM`（无 finish/usage），turn/end 为 `aborted/disposed`；suite 断言“中断不得伪装成功” |
| 17 | `interrupted-recovery` | recall | 新进程 `resume_session` 后追加 turn 2，`RECALLED:PUBLIC_INTERRUPT_82nm`；最终 Session JSONL 同时保留中断 turn 1 痕迹与恢复 turn 2（`request/header.reason="resume"`） |

### 3.2 汇总数字与逐项来源

| 数字 | 值 | 日志依据 |
|---|---:|---|
| cases | 17 | `len(results)`；`kind:"case"` 行 = 17 |
| resume_pairs | 3 | suite 循环 3 次；save/recall 的 PID 对均不同 |
| dual_home_bidirectional | true | A/B final_response 互斥包含对方 nonce（同时 9 个 Session JSONL 中 A/B home 文件各只含自己的 nonce） |
| sdk_run_calls | 15 | 17 case 中 `unknown-resume` 与 `corrupt-resume` 为 0 次（其余：json/tool/resume×6/home×4/corrupt-save/interruption/recovery 各 1） |
| synthetic_adapter_invocations | 16 | 15 次 run 每次 ≥1 次 provider stream；`actual-tool-event` 因工具回包多 1 次（14 个单调用 case ×1 + 1 个双调用 case ×2 = 16） |
| real_model_calls / http_calls | 0 / 0 | 每个 case 的 `data`、每个 invocation、registry 均断言 0；provider 无 HTTP 实现 |
| guard_rejection_selftests | 17 | 每个 case 的 `diagnostics` 均含 `FIXTURE_GUARD_SELFTEST status=PASS`（真实 `llm/stream` waterfall 对非真实路由先拒绝、adapter 未执行） |
| worker_pid | 2,16,…,227 各不同 | 每个 case 是新 worker 进程；3 对 resume 的 save/recall 也是不同进程 |
| runtime_exit_code | 17×0 | 每个 case 的 `data.runtime_exit_code`；正常 close 后 `_proc is None` |
| Session JSONL 数 | 9 | json/tool/resume×3/home×2/corrupt/interrupted 各 1；日志逐文件记录 SHA-256 与 base64，本文已重算 base64 的 SHA-256 全部匹配 |
| merged-config rows / disabled | 39 / 13 | dump-config exit 0；13 个危险/真实 provider/tool 行为 `disabled:true`，`session-log-deepseek.config.enabled=false`，插入两个 `file:///probe/runtime/...` 测试插件行 |

### 3.3 关键证据点

- **JSON 走既有 E1 严格校验**：worker 只导入项目既有
  [`structured_output.py`](../src/autoteacher_m0/runtime/structured_output.py)（stage 拷贝与
  `src/` 逐字节相同，SHA-256 `79b30c9d…268182`），把 SDK 返回的 str 交给
  `validate_e1_json`；没有 SDK 对象进入业务核心。这里只覆盖正向合法 JSON 路径；
  负例/边界由 [REVIEW_PHASE2 §4](REVIEW_PHASE2.md#L45-L56) 的专门测试覆盖，本轮未重跑。
- **真实注册的 `skill_lookup` 工具**：工具来自此前已审查的
  [`plugins/skill-lookup/src/index.ts`](../plugins/skill-lookup/src/index.ts)
  （stage 内 `build-input/skill-source/index.ts` 与它逐字节相同，SHA-256 `a618fb02…15346`），
  在容器内用官方 `dsh-tools`/Cordis ABI 编译；运行时通过真实 `ctx.tools.register` 注册，
  request/header 的 schema、`tool/call`、`tool/result`、`callId` 关联与 `isError=false`
  都是真实引擎产物。**“要不要调用工具”是脚本 provider 按 `FIXTURE_TOOL` 决定的，
  不是模型选择**；因此只能证明工具注册/分发/执行/事件/结果链路，不能记 E1b/E2 Live。
- **synthetic 标记贯穿**：`registerAdapter` 前显式要求 `AUTOTEACHER_OFFLINE_FIXTURE=1`
  且真实 provider 列表为空；`request/header`、assistant source、invocation、registry
  全部标记 `offline-test-only`/`fixture-v1`/`synthetic:true`；usage 固定 7/3/10 是夹具值，
  不是 tokenizer 计量或账单。
- **Session 是真实 DSH JSONL v4**：会话目录为
  `<dsh_home>/sessions/<workspace 编码>/<session-id>/session.v4.jsonl`；跨进程 resume 走
  SDK 的官方 `resume_session`，不是自造回放。
- **双 home 只证明 API/命名空间逻辑隔离**：与 E3-04 同义，不证明 OS 文件访问隔离（那是 E5；
  本轮未新增 E5 结论）。

### 3.4 只读核对命令（无需重新执行）

```sh
cd "artifacts/sdk-fixture"
jq -s '[.[]|select(.kind=="case")]|length' suite-context-aware.log                      # 17
jq -s '[.[]|select(.kind=="case")|.data.sdk_run_calls]|add' suite-context-aware.log     # 15
jq -s '[.[]|select(.kind=="case")|.data.synthetic_adapter_invocations]|add' suite-context-aware.log   # 16
jq -s '[.[]|select(.kind=="case")|.data.real_model_calls]|add' suite-context-aware.log  # 0
jq -s '[.[]|select(.kind=="case")|.data.http_calls]|add' suite-context-aware.log        # 0
jq -s '[.[]|select(.kind=="case")|.exit_code]|unique' suite-context-aware.log           # [0]
jq -r 'select(.kind=="summary")|.status' suite-context-aware.log                        # PASS-real-engine-synthetic-fixture-only
# Session 日志内嵌 base64 与记录 sha256 逐条核对
jq -r 'select(.kind=="session-log")|[.sha256,.base64]|@tsv' suite-context-aware.log |
  while IFS=$'\t' read -r sha b64; do
    [ "$(printf '%s' "$b64"|base64 -d|sha256sum|cut -d' ' -f1)" = "$sha" ] || exit 1
  done; echo OK
```

## 4. 精确复现命令

**命令来源与可核对性**：`artifacts/sdk-fixture/` 本身只保存运行输出，不保存外层 `podman`
argv。下面的精确 argv 是从本次运行作者会话的 job 记录中只读取回的（DSH session store：
`/root/.dsh/sessions/--root-Autonomous~0020Teacher--/c54ba4eb-c885-4314-b851-a5def2a73b89/session.v4.jsonl.zstd`，
SHA-256 `ac460917…74e0d`，job `bash-b1d344e8009b4421` 与 `bash-a60c4b9ad5214aba`），
并与日志 `isolation` 行逐项对照：uid/mounts/cgroup/环境变量名/二进制 SHA 完全一致。
外层 job 退出码 0 也来自同一 job 记录，不是日志字段。**不要为了复现重新加宽隔离或注入 Key。**

### 4.1 重新构建（如需；通过运行的 BUILT_FILE 精确字节已保存在日志中）

在仓库根目录执行（`cp`/`chmod` 是宿主上的可信文件操作；编译只在容器内）：

```sh
set -euo pipefail
cd "/root/Autonomous Teacher"
cp plugins/offline-fixture/src/index.ts artifacts/sdk-fixture/stage/build-input/src/index.ts
chmod a+r artifacts/sdk-fixture/stage/build-input/src/index.ts
timeout 110s podman run --rm --name at-m0-sdk-fixture-build --rootfs \
  --network none --http-proxy=false --unsetenv-all \
  --env PATH=/usr/bin --env HOME=/work \
  --read-only --read-only-tmpfs=false --cap-drop ALL --security-opt no-new-privileges \
  --user 65534:65534 --pids-limit 32 --memory 1g --memory-swap 1g --cpus 1 \
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=32m,mode=1777 \
  --tmpfs /work:rw,noexec,nosuid,nodev,size=128m,mode=1777 \
  --workdir /work --timeout 100 --systemd=false \
  --mount 'type=bind,src=/root/Autonomous Teacher/artifacts/sdk-fixture/stage,dst=/probe,ro=true' \
  '/root/Autonomous Teacher/artifacts/security/rootfs' \
  /usr/bin/node /probe/build.mjs > artifacts/sdk-fixture/build-context-aware.log 2>&1
```

预期：`BUILD_EXIT 0` 两次 + 6 条 `BUILT_FILE`，其中
`fixture/lib/index.js` = `9871486f…cdef`、`skill/lib/index.js` = `521bc0f1…3b0b`、
`skill/lib/skills.json` = `6988fc43…5300`。日志是 stdout+stderr 重定向，容器不写宿主。

### 4.2 通过运行（从 build 日志解码出只读 runtime 产物后，在容器内执行 suite）

```sh
set -euo pipefail
cd "/root/Autonomous Teacher"
for file in fixture/lib/index.js fixture/lib/index.d.ts; do
  jq -erR --arg p "$file" 'select(startswith("BUILT_FILE ")) | sub("^BUILT_FILE ";"") | fromjson
    | select(.path==$p) | .base64' artifacts/sdk-fixture/build-context-aware.log |
    base64 --decode > "artifacts/sdk-fixture/stage/runtime/$file"
done
chmod a+r artifacts/sdk-fixture/stage/worker.py artifacts/sdk-fixture/stage/suite.py
timeout 160s podman run --rm --name at-m0-sdk-fixture-suite --rootfs \
  --network none --http-proxy=false --unsetenv-all \
  --env PATH=/opt/python/bin:/usr/bin \
  --env HOME=/work/user-home \
  --env PYTHONPATH=/deps:/probe/validator \
  --env PYTHONDONTWRITEBYTECODE=1 \
  --env TMPDIR=/tmp \
  --env DSH_RUNTIME_MODE=exe \
  --env DSH_RESOURCE_CACHE=/work/resources \
  --env NARB_NATIVE_CACHE_DIR=/probe/native-cache \
  --env PKG_NATIVE_CACHE_PATH=/probe/pkg-cache \
  --env NO_COLOR=1 \
  --env AUTOTEACHER_OFFLINE_FIXTURE=1 \
  --read-only --read-only-tmpfs=false --cap-drop ALL --security-opt no-new-privileges \
  --user 65534:65534 --pids-limit 32 --memory 512m --memory-swap 512m --cpus 1 \
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=32m,mode=1777 \
  --tmpfs /work:rw,noexec,nosuid,nodev,size=128m,mode=1777 \
  --workdir /work --timeout 150 --systemd=false \
  --mount 'type=bind,src=/root/Autonomous Teacher/artifacts/sdk-fixture/stage,dst=/probe,ro=true' \
  --mount 'type=bind,src=/root/Autonomous Teacher/artifacts/foundation/deps,dst=/deps,ro=true' \
  '/root/Autonomous Teacher/artifacts/security/rootfs' \
  /opt/python/bin/python3.11 /probe/suite.py > artifacts/sdk-fixture/suite-context-aware.log 2>&1
```

预期：exit 0；首行 `kind:"isolation"`；17 条 `kind:"case"` 全 exit 0；1 条
`merged-config` exit 0；末行 summary 与 §0 完全相同。若任一断言失败，suite 会以非零退出
并留下 traceback——**不得把不完整/失败日志当通过证据**。

### 4.3 边界约束（复现时必须保持）

仅容器内执行（宿主不跑项目 Python/pytest 或生成的 TS/JS）；`--network none`、
`--unsetenv-all`、无真实 Key、非 root、只读 root/输入、cap-drop ALL、
no-new-privileges、无 socket/私密 home/私有评估/可写可执行 mount；`/tmp`、`/work`
保持 `noexec,nosuid,nodev`；`/probe` 与 `/deps` 只读且复用既有目标目录。
`offline-test-only` 插件显式 opt-in，未设置该环境变量即拒绝启动。

## 5. 明确边界（不可从本轮结果推导）

1. **不是模型**：provider 是确定性脚本夹具，按提示词返回固定文本/工具调用；没有
   DeepSeek API、没有 HTTP 客户端、没有真实 Key、没有费用。`fixture-v1` 不是任何真实模型别名。
2. **工具结果不是模型选择**：`tool-call` 由脚本在 `FIXTURE_TOOL` 下产生；真实的是注册表、
   schema 投影、分发、执行、事件与结果渲染。不能写成“模型调用了 skill_lookup”，也不能记
   E1b、E2 Live 或 E2 完整 PASS（E2 离线插件结论另见 [PLUGIN_NOTES](PLUGIN_NOTES.md)）。
3. **不能记 E1/E3 完整 PASS**：E1 要求获批主路由上的真实模型输出与费用；E3 的引擎级恢复/
   双 home 子集虽被真实执行，但完整 E3 验收（含真实交互/错误语义/事件映射）仍待维护者按
   任务书判定；本轮不自行提升为 E3 PASS，更不是 E5 文件系统隔离。
4. **不是生产 Adapter/Gate**：worker 直接使用 SDK 公共 API；未构造
   [`HarnessAdapter`](../src/autoteacher_m0/runtime/dsh_adapter.py)（仍无条件
   `SECURITY_BLOCKED`），未改 Gate/模型配置；`production_adapter_used:false`。
5. **SDK 对象不进业务核心**：只有 `result.final_response` 字符串进入既有
   `validate_e1_json`；SDK 事件/notifications/session 对象不被业务模块导入或保存为契约。
   这符合 [REVIEW_PHASE2 §4](REVIEW_PHASE2.md#L45-L56) 的接口边界约定。
6. **不是 Live 授权**：没有 E5-PreLive 人工批准、没有真实凭据注入、没有联网；Live Gate/
   真实 E1/E2/E4 仍 BLOCKED，总体 `DECISION PENDING` 不变。不得用本文件绕过任何安全审批。
7. **不是费用/预算桥**：usage 是夹具常量；本轮不触碰
   [BUDGET_BROKER](BUDGET_BROKER.md) 的持久账本、预留或真实账单，也不证明 SDK 内部
   agent steps 的逐请求预算约束。
8. **不是教学效果或 RSI 证据**：17 个技术用例不是 20 例公开评估集，不比较策略质量。

## 6. 失败历史（原样保留，不覆盖、不改写）

本轮之前的失败与修正都保留在独立日志中。它们是为了证明“通过不是靠放宽隔离/伪造结果”，
不得删除，也不得把失败轮次的数字并入最终 PASS 计数。

| 日志 | 实际症状 | 处理与保留含义 |
|---|---|---|
| [`build-first.log`](../artifacts/sdk-fixture/build-first.log) | `tsc` exit 2，`TS2307` 找不到 `@deepseek-ai/dsh-package-manifest` 类型 | 容器内依赖闭包不全；后续在 stage 内补齐/链接同一锁定依赖后再构建。失败轮保留。 |
| [`suite-first.log`](../artifacts/sdk-fixture/suite-first.log) | `JsonRpcError: no adapter registered for provider "offline-test-only"`；插件导入 `ERR_MODULE_NOT_FOUND`（`@deepseek-ai/dsh-llm`/`dsh-tools`） | 插件从 `/probe/runtime/...` 运行时找不到 stage 内 `node_modules`；修正为只读链接/拷贝同一依赖，非放宽边界。 |
| [`json-diag.log`](../artifacts/sdk-fixture/json-diag.log) | runtime `turn/end` 错误：`/work/user-home/.cache/pkg/.../node-addon-system.../system.node: failed to map segment from shared object` | 可写 `noexec` 临时缓存仍无法映射 native；随后从锁定 SEA 导出精确只读 `/probe/pkg-cache` 并设置 `PKG_NATIVE_CACHE_PATH`，未放开 `noexec`、未改 binary。 |
| [`suite-system-cache.log`](../artifacts/sdk-fixture/suite-system-cache.log) | `AssertionError: ('SDK_RUN_NOT_SUCCESS','error')`；invocation 的 `command` 是 `<system-reminder>...`，引擎回 `OFFLINE_FIXTURE_UNKNOWN_SCRIPT` | **runtime-context 误选**：早期 provider 取“最后一条 user 消息”，把 DSH 注入的 runtime-context 快照当成用户输入。修正为只接受 `message.source.kind === 'user'` 的真实用户文本（见 [index.ts#L48](../plugins/offline-fixture/src/index.ts#L48)），并重建 fixture；失败轮保留。 |
| [`suite-linked-deps.log`](../artifacts/sdk-fixture/suite-linked-deps.log) | worker 在 `validate_e1_json` 处失败，strict E1-02 拒绝 SDK 返回串；该轮未输出 raw final_response | 一次迭代失败，说明“能启动”不等于“严格 JSON 契约通过”；未把该轮当 PASS，也未从后续通过反推其原因是模型/网络。 |
| 旧 pkg/native 失败历史 | task15 之前的 keyless initialize 在未预置 native cache 时 BLOCKED（`No usable native binding found`） | [SDK_NATIVE_DIAGNOSTIC](SDK_NATIVE_DIAGNOSTIC.md)、[SDK_OFFLINE_PROBE](SDK_OFFLINE_PROBE.md)、[REVIEW_PHASE2 §5](REVIEW_PHASE2.md#L58-L72)。本轮预置官方精确只读 cache 后通过，但结论仍只限 keyless synthetic 子集。 |

**既有文件不一致提示（审计项）**：[`implementation.sha256`](../artifacts/sdk-fixture/implementation.sha256)
是 23:13 UTC（runtime-context 修正**之前**）的临时快照，其中
`plugins/offline-fixture/src/index.ts` = `48b776a6…87df`、
`stage/runtime/fixture/lib/index.js` = `e0b07dde…c606`；23:31–23:36 修正/重建后当前值为
`366447f1…e954` / `9871486f…cdef`。因此该文件**不能**作为最终身份清单；最终身份以
[`build-context-aware.log`](../artifacts/sdk-fixture/build-context-aware.log) 的
`BUILT_FILE`（与当前 stage 逐字节相同）和 [manifest.json](../artifacts/sdk-fixture/manifest.json)
为准。原文件按“保留历史、不覆盖”原则未改。

## 7. 证据索引与哈希

| 文件 | SHA-256 |
|---|---|
| [`suite-context-aware.log`](../artifacts/sdk-fixture/suite-context-aware.log) | `c4cd15108e72a313bc438e9b0dc528a83f31349151406d2ae6261c92556eef99` |
| [`build-context-aware.log`](../artifacts/sdk-fixture/build-context-aware.log) | `cd44b06fe07c194c5d35ced4596f34a6ab256e3b7f30db8e338ea08ace0e1a52` |
| [`stage/suite.py`](../artifacts/sdk-fixture/stage/suite.py) | `d44314047945347389cd5f679478749df5f3ce1e8da8e73a1450458971b9d5da` |
| [`stage/worker.py`](../artifacts/sdk-fixture/stage/worker.py) | `3fca9ef3328f7e5ca3b4b3b09b2ebb1e8ea03aab4af174bb74100dc4bfe7257c` |
| [`stage/build.mjs`](../artifacts/sdk-fixture/stage/build.mjs) | `8b839972eeac98dbb9a1a2cc41f01598f3ad82d00f7e0ac16909977ddec7dcdb` |
| [`stage/runtime/experiment.patch.yml`](../artifacts/sdk-fixture/stage/runtime/experiment.patch.yml) | `ca2ea3629e8bfb1f6f2e59fedb6795e43423e6f4b7577acb0a12f51280761b56` |
| [`plugins/offline-fixture/src/index.ts`](../plugins/offline-fixture/src/index.ts) | `366447f124a3f153e880ad9178e645e14043c7a948cb63cb14e0ab9170e2e954` |
| [`plugins/offline-fixture/package.json`](../plugins/offline-fixture/package.json) | `95ab5017e217dbaf3c7498c48891d4a1c08b12ad1c42471a4375856a3262eb15` |
| [`plugins/offline-fixture/cordis.patch.yml`](../plugins/offline-fixture/cordis.patch.yml) | `0fb369928fe2b2ee8b1faf064617103cdddc998bed37d5a3ab8fba1d1702f7f3` |
| [`plugins/skill-lookup/src/index.ts`](../plugins/skill-lookup/src/index.ts) | `a618fb029faf7606b64549d6f0ea82259af1a2c5fb2dce27119b7d1b22115346` |
| [`stage/runtime/fixture/lib/index.js`](../artifacts/sdk-fixture/stage/runtime/fixture/lib/index.js) | `9871486f24d754d683e781f9194af87ca62bfd44201d9324e6f6d2ccee28cdef` |
| [`stage/runtime/skill/lib/index.js`](../artifacts/sdk-fixture/stage/runtime/skill/lib/index.js) | `521bc0f1126d895de84ebe61fd58c978a5bcae9b4c334f1fd417faee88483b0b` |
| [`stage/runtime/skill/lib/skills.json`](../artifacts/sdk-fixture/stage/runtime/skill/lib/skills.json) | `6988fc43029688fbe60fa401e7fe460a59441717afc88c7664958299b1835300` |
| [`stage/validator/.../structured_output.py`](../artifacts/sdk-fixture/stage/validator/autoteacher_m0/runtime/structured_output.py) | `79b30c9d8683e4b6e38bed9c52ec1649d8bd80202deae0df19baa347ed268182` |

完整输入/产物/源码/日志清单与逐项说明在
[manifest.json](../artifacts/sdk-fixture/manifest.json)；可执行校验在
[evidence.sha256](../artifacts/sdk-fixture/evidence.sha256)：

```sh
cd artifacts/sdk-fixture && sha256sum -c evidence.sha256
```

补注：stage 内 validator 拷贝与项目 `src/autoteacher_m0/` 对应文件逐字节相同（已只读核对），
所以这里的 JSON 校验确实是现有 E1 严格实现，而不是另写一份宽松校验。

## 8. 与 M0 决策的关系

- 本轮只新增 B 层事实：真实引擎/SDK/RPC/Session/工具注册与执行/跨进程恢复/双 home/
  受控中断在 **synthetic offline fixture** 下工作；这为后续真实 Live 集成降低了
  引擎侧不确定性，但**不替代**任何需要真实模型/凭据/人工审批的强制项。
- E1（真实主路由、3/3 smoke、真实工具、错误/费用）仍 **BLOCKED**；E2 离线插件已有结论但
  E2 Live 仍 **BLOCKED**；E3/E4/E5 的强制验收状态不变；总体仍 `DECISION PENDING`。
- 不得据此写 GO/CONDITIONAL GO、不得启用 LiveGate、不得把 synthetic usage 当真实费用，
  也不得把本文件当作安全批准或人类路由决策。
