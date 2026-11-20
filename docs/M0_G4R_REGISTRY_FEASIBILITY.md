# M0 G4-R R3 — DSH 0.2.2-rc.2 权威 Tool Registry 可行性与受控 Spike（No-Key）

- **任务**：G4-R PR-R3 / RG-00..RG-12（`/root/handoffs/AT_G4R_v1.0/Autonomous_Teacher_G4R_Agent_Execution_Plan_v1.0.md` §1.1/§1.2/§2/§6/§9/§10）
- **实施者**：`a-g4r-registry`（RG 角色，独立于 Lead/Reviewer）
- **工作树/分支**：`/root/Autonomous Teacher/worktrees/g4r-registry` @ `feat/g4r-registry-spike`；**Parent SHA** = `3e7afee077845a071cd364e93ab209cac20b2d5f`（main）
- **日期（UTC）**：2026-11-20
- **性质**：**no-key / no-model / no-external-network / no-live**。0 真实 Key（未读取 `.env`/凭据）、0 真实 Provider 调用、0 外部 HTTP/TCP、0 下载/拉镜像、0 新依赖、未 patch 冻结 `artifacts/foundation/{deps,stage}` 或 Runtime binary、未修改主工作树。
- **不声明**：本文件不是 E5-PreLive Full、不是 B03/E5-P04 PASS、不是 G4-H/G5/G6 授权、不是 Live 批准。`LiveGate` 仍 `BLOCKED`、`G4-H=NOT_AUTHORIZED`、`G5=BLOCKED`。`config/g4/runtime-policy.json` 的 `registry_status` **保持 `UNVERIFIED_NO_AUTHORITATIVE_MERGED_EXPORT` 不变**。

---

## 0. 裁决（三选一，不主观打分）

> ## `API_AVAILABLE`

**裁决的精确含义**：冻结 DSH `0.2.2-rc.2` Runtime（binary sha256 `1cc41d5a…`）**提供公开的进程内插件 API/事件面**，足以在**不 patch Runtime binary、不新增依赖**的前提下，由经评审的 instrumentation plugin 获得：

1. 注册完成后的**完整** Tool Registry（name + canonical schema digest + registry_epoch）；
2. **每次 provider dispatch 前**的 effective tool face（实际 `GenerateOptions.tools`）并与批准集合逐项比对；
3. 注册变化事件（`tools/change`）与单调 epoch，用于发现 late register/unregister/schema drift；
4. 在该 hook 内**fail-closed 拒绝**未批准/额外/漂移/registry≠face 的 dispatch（在 adapter 之前）。

**同时成立的三条限制（必须与裁决一起引用，缺一即不可当作权威证据）：**

- **L-1 没有外部导出 API（ABSENT）**：CLI 只有 `--dump-config`（打印 Cordis entry 列表后 exit，不 boot，不 materialize `ctx.tools`）；SDK JSON-RPC 仅有 `initialize` / `session/prompt` / `session/resume` / `session/wait` / `shutdown`（见 §2.6），**没有** registry/tool-schema 导出方法。因此所谓 API 是“**进程内 Cordis 插件 API**”，不是“宿主/Controller 可直连的权威导出”。
- **L-2 证据等级上限为 `L1-INSTRUMENTED-OBSERVATION`**：snapshot 由 Runtime 进程内的插件**自报**（JSONL 文件），**不是 OS attestation**；Candidate/进程若可伪造该文件即可伪造 registry。SHA 只是完整性，不是身份认证。要达到 `L2-REGISTRY-RUNTIME` 必须由 Trusted Controller 绑定 runtime/stage/profile SHA + run id + registry_epoch + dispatch 序号，并把**缺失/重复/回滚/未绑定**的 snapshot 一律视为 deny（§4）。
- **L-3 不改变冻结状态**：B03/E5-P04 仍 `UNVERIFIED`；本 Spike 的观测**不是**独立 Reviewer 复验，不得被 Owner 文本提升为 PASS（RG-12 由 R5 Reviewer 独立裁定）。

**未裁决为 `PATCH_REQUIRED` 的理由**：所需 API/事件（`tools.definitions()/schemas()`、`tools/change`、`llm/stream` waterfall、`register()` disposer）均存在于 Runtime 自带 `@deepseek-ai/dsh-tools@0.2.2-rc.2` / `@deepseek-ai/dsh-llm@0.2.2-rc.2` / `@deepseek-ai/cordis@4.1.0` 的公开源码与 d.ts 中；实测仅通过 `--patch` 插入 file:// 插件即生效，**不需要 fork/patch Runtime binary**。因此不建议 fork；若维护者要求外部直连导出，那才是新的 `PATCH_REQUIRED`（当前不成立）。

**未裁决为 `NO_TRUSTWORTHY_EXPORT` 的理由**：Runtime 内确有可导出完整集合的公开入口（实测），且通过插件 + Controller 绑定可形成可审计链路（trust boundary 见 §4）；但“可信”取决于绑定通道是否实现，因此在绑定实现前其证据等级被封顶为 L1（L-2）。

---

## 1. 问题复述：为什么 `--dump-config` 与 request-only 观测都不是 registry

| 候选“证据” | 实际是什么 | 为什么不够 |
|---|---|---|
| `dsh --dump-config` | 合并后的 **Cordis plugin entries** 列表（39 条），`--dump-config` 打印后 exit，**不 boot、不实例化** | entry ≠ 运行期 `ctx.tools`；`!!js` 未求值（merged dump 中仍是惰性 `!!js …`）；动态/延迟注册不可见。G4-B §4 已证明，本轮实测再次证实（§2.2/§3）。 |
| Provider `request.tools`（F2 `dispatch-window` / bridge request） | **每次真正发送时**的 tool 面 | 只能证明“发出去的集合”，不能证明 registry 里没有**未被选中/未发送的隐藏 tool**；请求构造后到 wire 前仍有 route projection 等步骤。 |
| `runtime-policy.json` approved_tools | 批准集合（应然） | 不是 Runtime 实然值。 |
| **本 Spike：`ctx.tools` + `llm/stream`** | 注册表**完整集合** + 每次 dispatch 的 effective face + epoch | 仍是进程内自报（L-2），需 Controller 绑定与独立 Reviewer 复验。 |

---

## 2. R3-S0 只读架构查验（证据 + 源码位置）

证据根：`artifacts/g4r/registry/s0-identity.txt`（gitignored，只读采集）。源码对象：冻结 Runtime 自带依赖版本的**同版本包**（Stage `node_modules` 内 `@deepseek-ai/dsh-tools@0.2.2-rc.2`、`dsh-llm@0.2.2-rc.2`、`cordis@4.1.0`；tarball `deepseek-ai-dsh-tools-0.2.2-rc.2.tgz` sha256 `1af6bb58…`）。冻结 Runtime binary 内嵌 **326 个 `@deepseek-ai/*` 包名**（strings 核验），包含 `@deepseek-ai/dsh-tools`、`dsh-llm`、`dsh-agent`、`dsh-agent-loop`、`dsh-session*`、`dsh-system-prompt` 等。

### 2.1 `ctx.tools` 的真实类型与能力 —— **存在（API）**

`@deepseek-ai/dsh-tools@0.2.2-rc.2` `src/index.ts`：

- `class ToolsService extends Service`，`constructor(ctx) { super(ctx, 'tools') }` → Cordis 服务名 **`tools`**；`declare module '@deepseek-ai/cordis' { interface Context { tools: ToolsService } }`，并导出别名 `ToolRuntime`。
- 能力（公开方法）：`register(definition, options) -> disposer`（唯一注册入口，重复名在同 layer 抛错，`run_code` 保留禁注册）；`restrict(filter)`（仅 scoped context，allow/deny 交集）；`get/executable(name, scope?, toolSet?)`；`resolve(context) -> ResolvedToolSet`（按 step 求值 `when` 条件，返回该 step 的 admission 集合）；`definitions(scope?, toolSet?)`；**`schemas(scope?, toolSet?) -> ToolSchema[]`**（只投影 model-facing `name/description/parameters/deferLoading`）；`setExecutor`；`execute`；`guard/checkGuards`。
- 作用域：`ScopedLayers` + `ScopeKey`（Agent/preset scope）；scoped 工具 shadow global；global 视图由 `definitions()`/`schemas()` 无 scope 参数取得；effective 集合还受 **step admission**（`ResolvedToolSet`）影响 → 不能把 global 列表当作最终 per-dispatch 值，必须在 dispatch 点取。
- 事件（`src/events.ts`，均为 public typed Cordis events）：`tools/pre-execute`、`tools/execute`、`tools/post-execute`、`tools/result`，以及 **`tools/change`（“A tool was registered or unregistered, or a scoped restriction changed”，emit 模式，unfiltered）** → 注册 epoch 的唯一公开来源。

### 2.2 Cordis 插件 apply / ready / start barrier —— **部分存在；全局 ready barrier ABSENT**

`@deepseek-ai/cordis@4.1.0`（`src/fiber.ts`、`src/registry.ts`、`src/events.ts`）：

- Fiber 状态机：`PENDING → LOADING → ACTIVE / FAILED → UNLOADING → DISPOSED`；依赖未就绪的插件停在 PENDING。
- 就绪等待的公开机制是 **`ctx.inject(deps, callback)`**（`registry.ts` L176/L300）与静态 `export const inject = [...]`；插件 apply 在依赖服务均 ACTIVE 后运行。**没有**公开的全局 `ready`/`start` 事件（grep `'ready'` 仅命中 “already”；`internal/status`/`internal/service` 属 `internal/` 命名空间，不作为稳定 API）。
- **实测**：probe 插件 `inject = ['tools','llm']` 在服务就绪后 apply，随后仍持续观察到 `tools/change`（epoch 0→1→2…）→ **“apply 完成”≠“注册完成”**；完整集合必须等 “最后一次注册” 之后的点（本 Spike 用每个 `llm/stream` dispatch 点 + `tools/change` 持续跟踪，而不是启动快照一次性断言）。

### 2.3 异步 / 热重载 / 动态注册 —— **存在**

- 注册是 Cordis effect：`register()` 返回 disposer，unload/reload 时自动撤销；`this.layers.effect(..., 'tools.register()')`。
- loader 支持配置更新/HMR（`internal/update` waterfall；`cordis-plugin-loader` 的 entry update/reload）；阶段内 `dsh-hmr` 类插件可触发热更新。插件可**任意时刻**调用 `tools.register()`（本轮 probe 在运行时 late register 成功，见 §3 RG-02/RG-04）。
- 实测到同一 boot 内既有注册（skill_lookup）也有卸载（进程收尾时 registry 逐步清空，epoch 递增）→ 动态注册真实存在，因此 epoch 必须**在 dispatch 前**核对，不能只在启动时。

### 2.4 `!!js` 求值时机 —— **加载期求值，非 dump 期**

`@deepseek-ai/cordis-plugin-loader` `lib/index.js`：`evaluate = new Function("ctx","expr", …)`（L233）；`resolveJsExpr` 递归替换 `!!js` 节点（L238–247）；`Entry.disabled` 为 `!!js` 时在 **load/update 时**求值（L346–353）。`--dump-config` 输出保留惰性 `!!js` 文本（本轮 dump 中 `!!js Number(...)` / `!!js dshHomePath(...)` 原样可见）→ **dump 的内容不是求值后的插件图**。实测 probe 仅通过 patch insert 即被加载，说明求值发生在 boot 的 entry apply 阶段。

### 2.5 `LlmAdapter.generate(options.tools)` 的 effective registry 来源 —— **`systemPrompt.assemble()` → ToolsService**

- `@deepseek-ai/dsh-llm@0.2.2-rc.2`：`GenerateOptions.tools?: ToolSchema[]`（`src/types.ts` L582，注释 “adapters map to the provider's `tools` field”）；`LlmRuntime.stream()` 经 **`ctx.waterfall(this,'llm/stream', options, () => adapterStream(...))`**（`src/index.ts` L1185–1195）；事件声明 `'llm/stream'(this: LlmRuntime, options: GenerateOptions, next)`，注释明确 “Waterfall around every streaming model call (retry, replay, routing)”，“LOOP-built request … deep-frozen (mutation throws)” → **只读观测点，不可被观测者改写请求**。
- `dsh-tools` 构造时向 system-prompt 注册 tools provider：`ctx.systemPrompt.tools(({scope, toolSet}) => … this.definitions(scope, toolSet) …)`；`@deepseek-ai/dsh-system-prompt` 的 `tools(provider)`（L552）→ `assemble()` 汇总成 `assembly.tools`。
- agent-loop（最近可用源码 `0.2.1-rc.2`，区别已在 §7 声明）：`preStep` 调 `systemPrompt.assemble(...)`；`step()` 用 `assembly.tools` 判断 `toolsChanged()` 并构造 request 调 `llm.stream(request)`（L1059/L1084）；最终 wire tools 还会在 `adapterStream` 内做 route projection（`projectToolUpdates`）。
- **结论**：effective registry 的权威取值点是 `ToolsService.schemas(scope, toolSet)`；实际进入 provider 的最终 face 在 `llm/stream` 的 `options.tools` 可见（投影前）。二者都必须在 dispatch 点核对（`registry == face == approved`）。

### 2.6 session-title / compaction / subagent / judge 独立 provider stream —— **冻结 profile 下：ABSENT / disabled；所有流仍经同一 `llm/stream`**

- 冻结 merged entry 列表（G4-B 证据 `artifacts/g4/runtime/merged-config.yml`，sha256 `0d525f44…`，**39 条**；含 patch insert `g3b-trusted-bridge-provider`、`offline-public-skill`）：`llm`、`tools`、`tool-executor-native`、`agent`、`agent-loop`、`session-title`、`mcp-resources` 等存在；`compaction-basic`、`image-offload`、`tool-fs`、`tool-working-directory`、`terminal-bash/pwsh`、`persistent-bash/pwsh`、`pty`、`subprocess`、`jobs`、`llm-deepseek`、`plugin-package-inventory-deepseek` 均 `disabled: true`；`session-log-deepseek` `config.enabled: false`。**没有任何 `subagent` / `judge` / `agent-team` entry（ABSENT）**。
- 所有 provider 流（含辅助 `purpose`）都走 `LlmRuntime.stream()` → `llm/stream` waterfall，因此在同一进程内可被同一 hook 观测/拒绝；`GenerateOptions.purpose` 携带辅助调用分类。冻结的桥接 adapter 在 UDS 前拒绝非 `conversation/null` purpose（F2 已证）。F2 历史证据：冻结配置下真实 run 0 额外 provider 请求，`session/title` 2 次均 `source.kind=fallback`；本轮 probe 输出中亦见 `session/title` 事件 `source: fallback`。
- 残余：`session resume` / `compaction` / `new Room` 的 effective registry 需在各自 API 场景下另行观测（本轮 **NOT_RUN**，见 RG-07）。

### 2.7 冻结身份（S0 环境 SHA）

| 项 | 实测值（只读） |
|---|---|
| Runtime binary | `/root/Autonomous Teacher/artifacts/foundation/deps/deepseek_harness_runtime/runtime/deepseek-harness-sdk-runtime-linux-x64`；sha256 `1cc41d5a8745a5b9d47c8604e44f23eb8af2d8ca02b2afa0be101d5f71be6ea4`；182,717,632 B |
| Runtime version | `0.2.2-rc.2`（`--version` exit 0，隔离环境） |
| SDK / runtime wheel | `deepseek-harness-sdk 0.2.2rc2`、`deepseek-harness-runtime-bin 0.2.2rc2` |
| profile | `sdk-minimal`（materialized profile 由 Runtime 内嵌模板在隔离 `DSH_HOME` 下生成） |
| frozen overlay（patch） | `config/g3d/candidate/bridge.patch.yml` sha256 `0cf5d340830856450540a4d74b2ae0d555d1ba40150a6e7942c8d7222dbe7d7b` |
| merged plugin IDs | 39（只读证据 `merged-config.yml` sha256 `0d525f44ef3ada744a306cd471c6a7370a7e7a673b7dfd912978b0836a5ae6cf`） |
| 实际加载 bridge build | Stage `runtime/bridge/lib/index.js` sha256 `2cb424616b7380bff61f8ce760e229a0c1d2b32c4a5f2954cdf66c3937bf74ba` == `runtime-policy.json stage_binding.adapter_built_js_sha256`（一致） |
| 实际加载 skill build | Stage `runtime/skill/lib/index.js` sha256 `521bc0f1126d895de84ebe61fd58c978a5bcae9b4c334f1fd417faee88483b0b` == repo `plugins/skill-lookup/lib/index.js`（一致） |
| dsh-tools（同版本源码/构建） | `lib/index.js` sha256 `bf71a6ce…`；`src/index.ts` sha256 `5d95d7f4…`；tarball `1af6bb58…` |
| cordis | `4.1.0`；`package.json` sha256 `70be1056…` |
| 批准 schema | `skill_lookup` = `c984bef0ae31771da16a12ef2e7972b289cde6014b7f8ad12349f16c4f77b704`（`config/g4/runtime-policy.json` approved_tools） |
| 环境 | Python 3.12.3（host probe 驱动）、Node v22.23.2、podman 4.9.3（本 task 未使用容器/podman） |
| no-key/no-network | probe 子进程 `unshare -n`（空 netns）+ `env -i HOME/DSH_HOME=<tmp> PATH/TERM`；0 key env 名；bridge adapter 自报 `httpCalls:0, realModelCalls:0` |

---

## 3. 受控 Instrumented Spike（测试 copy，无 Key/无网络）

### 3.1 方法

- 新增公开 Cordis 插件 `scripts/g4r/registry_probe/probe_plugin/lib/index.js`：`inject=['tools','llm']`，apply 后 (a) `tools.definitions()/schemas()` 快照；(b) 监听 `tools/change` 维护单调 `epoch`；(c) 监听 **`llm/stream` waterfall**，记录每次 dispatch 的 `options.tools`（name+canonical digest）、同时抓取 registry，比较 `face == registry`、`face/registry ⊆ approved`；enforce 模式在 adapter 之前 `throw`（`G4R_REGISTRY_TOOL_FACE_DENIED`）。输出仅 name+digest+epoch+绑定字段（schema：`scripts/g4r/registry_probe/snapshot.schema.json`），**无 prompt/args/Secret/session 文本**。
- 运行器 `scripts/g4r/registry_probe/run_host_probe.py`：**测试 copy** 中把冻结 `config/g3d/.../bridge.patch.yml` 的 insert 路径改写为临时 Stage 的 `file://` 路径（唯一改动，不改冻结文件/Stage），再追加 probe patch；隔离 `HOME/DSH_HOME`，`unshare -n` 起冻结 Runtime，通过 stdin 送 SDK JSON-RPC（`initialize` + `session/prompt`）触发真实 dispatch。Runtime/Stage 只读；不装依赖、不下载、无容器。
- 证据根（gitignored）：`worktrees/g4r-registry/artifacts/g4r/registry/<UTC>-<mode>/`（`run-summary.json`、`probe-events.jsonl`、`runtime-stdout.log`、`runtime-stderr.log`）；身份证据 `s0-identity.txt`。

### 3.2 实测结果（命令见每 run 的 `run-summary.json` `command[]`；UTC 均为 2026-11-20）

| run（evidence 目录） | 目的 | 关键观测 | 结论 |
|---|---|---|---|
| `20261120T163039Z-observe` | 完整 registry + dispatch face | registry union = `[skill_lookup]`；dispatch face = `[skill_lookup]`；digest = `c984bef0…`（== policy）；`face_equals_registry=true`；`approved_face=true`；epoch 0→1（注册）→2（收尾卸载） | **RG-01 机制证据**（L1） |
| `20261120T163048Z-enforce` | 正例：批准集合被放行 | face/registry 均 approved；dispatch 到达 adapter（stdout 出现 `G3B_BRIDGE_CONNECT_FAILED`，因无桥接 UDS，属预期） | 正例对照 |
| `20261120T163057Z-attack-late-extra-bash` | RG-02/RG-04：启动后 late register 额外 `bash` | epoch 2 注册 `bash`；dispatch face = `[bash, skill_lookup]`；`approved_face=false`、`unknown=[bash]`；enforce 抛 `G4R_REGISTRY_TOOL_FACE_DENIED`；**stdout 无任何 `G3B_BRIDGE_*` 连接标记**（adapter 未被到达）；turn/end `reason=error` | **detected + denied pre-adapter**（L1） |
| `20261120T163107Z-attack-duplicate-name` | RG-03：同名重复注册 | Runtime 抛 `tool "skill_lookup" is already registered (for a per-agent variant, register through that agent's agent.ctx instead)`；registry 不变 | **拒绝重复**（L1） |
| `20261120T163116Z-attack-schema-drift` | RG-06：仅 description 变化 | `drift_tool` v1 digest `c7035790…` → v2 digest `c9a707bb…`（digest 改变）；dispatch 时 registry 含 `drift_tool` → `registry_unknown=[drift_tool]` | **digest 敏感、可检出**（L1） |
| `20261120T163358Z-attack-two-turn` | RG-05：两轮间注册 | 尝试了同一进程第 2 个 Session 的第二次 prompt，Runtime 未产生第 2 次 turn（仅 1 次 dispatch）；原因未定 | **NOT_RUN**（不虚报） |
| `20261120T163317Z-observe`（`--drop-probe-output`） | RG-11：observer failure | probe 输出路径不可写 → 0 条记录；Runtime 正常退出（runtime_exit 0）；无放行语义改变，但产生证据缺口 | **观测失败≠fail-open**；须由 Controller 将“缺 snapshot”判 deny |
| `20261120T163436Z-observe`（`--skip-frozen-patch`） | 隐藏工具风险演示 | 默认 `sdk-minimal` profile（未应用冻结 overlay）registry union = `[bash, read_image, working_directory]` | 证明“未出现在 provider request 的已注册工具真实存在”，F2 request-only 无法覆盖；冻结 overlay 的 disable 是必要条件 |

> 说明：`--dump-config` / stdout 中出现的 `session/title` 事件为 `source.kind=fallback`（与 G4-F2 一致）；上述 run 均未建立真实桥接 UDS，因此 **不存在业务账本/Reserve/Claim/Fake 证据**（RG-09/RG-10 未由本 task 覆盖）。

---

## 4. Snapshot schema 与信任边界

**Schema**：`scripts/g4r/registry_probe/snapshot.schema.json`（`g4r.registry.probe.v1`，`additionalProperties:false`）。字段：

```text
schema="g4r.registry.probe.v1", kind∈{registry_snapshot,dispatch_tool_face,attack_result,probe_error},
epoch(uint, monotonic), pid, utc, mode∈{observe,enforce}, attack,
[registry_snapshot]  why, definitions[name], schemas[{name,sha256}]
[dispatch_tool_face] purpose?, provider?, model?, tool_names[], tool_digests[{name,sha256}],
                     registry_names[], registry_digests[], face_equals_registry,
                     approved_face, approved_registry, unknown[], registry_unknown[]
```

- **只含** tool name、**canonical schema digest**（对 model-facing `{name,description,parameters,deferLoading}` 做 RFC 风格 canonical JSON 的 sha256）、ownership/scope 隐含于 snapshot 生成点、epoch、scope（本 Spike：global registry view + dispatch 的 step-admitted face）、runtime/stage/profile SHA（记录在 run-summary 与 schema `x-g4r-provenance`）、UTC。**不含** prompt、tool-call args、Secret、session 原文、provider payload。
- **信任边界（必须显式）**：
  1. **Candidate 自报 ≠ OS attestation**：插件在 Runtime 进程内运行，输出是可伪造的 JSONL；任何能写该文件/控制该进程的一方都能伪造/删改/重放 snapshot。SHA-256 只提供完整性，不提供身份。
  2. 仅当 **Trusted Controller**（容器外/可信 principal）绑定了 runtime/stage/profile SHA、run id、`registry_epoch`、dispatch 序号，并把 **缺失/重复/epoch 回退/未绑定** 视为 deny 时，才可把证据等级提升为 L2-REGISTRY-RUNTIME；当前没有该通道 → 本 Spike 最高等级 **L1-INSTRUMENTED-OBSERVATION**。
  3. 不把 observed request 当权威 registry：request.tools 是 dispatch face；registry 完整集合必须另取自 `definitions()/schemas()`，并校验 `registry == face == approved`。
  4. 运行环境必须重新 Freeze/记 SHA（Runtime/Stage/profile/patch/plugin），任何变更即 preflight FAIL；本轮为 test copy，未形成新冻结物。

---

## 5. RG-00..RG-12 状态（本轮证据；非 Reviewer 签核）

| case | 状态 | 证据/理由 | 残余 |
|---|---|---|---|
| RG-00 真实 API/生命周期文档化 | **PASS** | §2 源码+实测；无权威导出（CLI/SDK ABSENT）也记录 | 源码版本来源需 Reviewer 独立核（Stage 0.2.2 包 + 0.2.1 agent-loop 注记） |
| RG-01 完整 effective snapshot == 仅批准 tool | **PARTIAL** | 2 次 observe+enforce：registry union=face=approved=`[skill_lookup]`，digest 与 policy 一致（L1） | 非 L2 attestation；单 turn；Reviewer 独立复验未做 |
| RG-02 隐藏/额外 tool（已注册但不在请求） | **PARTIAL** | late-register `bash` 被 registry 与 dispatch 同时检出并 pre-adapter 拒绝（L1）；默认 profile 演示 hidden tools | 真实第三方隐藏注册未复现；依赖观测插件在场 |
| RG-03 同名不同 schema / 覆盖歧义 | **PASS（机制）** | Runtime 内置 duplicate 拒绝并给出明确错误 | 仅 global layer；scoped shadow 语义未做攻击 |
| RG-04 startup snapshot 后、dispatch 前 late register | **PARTIAL** | epoch 1→2 漂移 + dispatch 检出 + enforce deny（pre-adapter） | 未覆盖“注册后立即 unregister”竞争窗口 |
| RG-05 dispatch 后、下一次 dispatch 前重注册 | **NOT_RUN** | 两轮驱动未获得第 2 次 turn（SDK app 在该 harness 下未开第二轮）；按代码每 `llm/stream` 独立拦截（runtime-budget-guard 同机制） | 需真实 SDK 会话两轮/Reviewer 复验 |
| RG-06 description/required 变化→digest 变化 | **PARTIAL** | description 变化 digest `c7035790…→c9a707bb…`，dispatch 检出 `registry_unknown` | 未测 `required` 单字段变体（同一 digest 机制覆盖） |
| RG-07 session resume/new Room/compaction/title/subagent | **PARTIAL** | 冻结 profile：compaction/image-offload/tool-fs/terminal 等 disabled；subagent/judge/agent-team ABSENT；所有 provider 流经同一 `llm/stream`；title 观测为 fallback | resume/compaction/new Room 的 effective registry 未跑（NOT_RUN）；未来配置不可外推 |
| RG-08 伪造/重放/错 SHA snapshot | **UNVERIFIED（设计已给）** | 明确信任边界：自报文件可伪造，SHA 非身份；要求 Controller 绑定+缺失即 deny | 无 trusted channel，本轮无法证明拒绝伪造；raw-UDS snapshot 攻击未做 |
| RG-09 正常 Tool 两轮 + Echo 账本 | **NOT_RUN** | 本 Spike 无桥接 UDS/Controller/Fake，无业务账本（不虚报） | 由联合回归（R5/Integration）覆盖 |
| RG-10 未授权 tool raw UDS 负例 | **NOT_RUN** | 同上；由 F2/R5 既有证据覆盖，本 task 不重复充当 PASS |  |
| RG-11 不可观测/observer failure → fail closed | **PARTIAL** | observer 写失败 → 0 记录、Runtime 不受影响；证明“观测失败是证据缺口” | “缺 snapshot 必须 deny”需 Controller 策略实现；否则仍是 fail-open 风险 |
| RG-12 独立 source-to-hook 复算 | **NOT_RUN** | 必须由 R5 Independent Reviewer 独立复算，Owner 不得自签 |  |

**Gate 结论**：`REGISTRY_RUNTIME_SNAPSHOT_VERIFIED_FOR_FROZEN_SCOPE` **尚未成立**（需 L2 绑定 + Reviewer RG-12）；当前为 **`API_AVAILABLE` 机制可行 + Registry 权威性仍 UNVERIFIED**，符合计划 §6.5 的“两种合法终点”中的 `REGISTRY_UNVERIFIED_WITH_CONTROLS_DOCUMENTED` 方向（控制已文档化并实测，权威性待绑定/复验）。

---

## 6. 若不可行/未绑定的 fail-closed 兜底与残余风险（路线 B）

1. **保持冻结状态**：`B03 = UNVERIFIED`、`E5-P04 NO_KEY = UNVERIFIED`；`config/g4/runtime-policy.json` 的 `registry_status` 不改（本 task 已核：git diff 为空）。
2. **配置/环境身份绑定**：preflight 固定 Runtime SHA/version、Stage manifest/tree、profile+patch SHA、插件集合、`!!js` 求值环境；任何变更 → FAIL（既有 `verify_manifest.py`/`require_manifest_match()` 链）。
3. **per-dispatch 批准集合**：Controller 继续对 `request.tools` 的每个 name+canonical schema SHA 做白名单（Reserve/Claim 之前）；未批准/额外/重复/消息内引用/辅助 purpose 一律拒绝。这只能支持“未经批准的工具不会进入可计费 Fake send”，**不是**“内部 registry 只有一个 tool”。
4. **残余风险（必须由维护者决定）**：
   - 隐藏内部工具即使不进入 provider 发送，也可能在 Candidate 内部执行；本轮默认 profile 演示 `bash/read_image/working_directory` 存在（冻结 overlay 下被 disable，但“未来配置/插件变更”不可外推）。
   - 观测插件自报不可作 OS attestation；无 trusted channel 时不能关闭 B03/E5-P04。
   - 不把 observed request 当权威 registry；不把 test copy 结果归到旧冻结环境。
5. **不建议 fork Runtime**：无必要；若未来要求外部直连导出/签名通道，应作为新工作项（PATCH_REQUIRED 重新评估，含撤销/回滚：移除 instrumented profile/Stage、恢复原冻结 SHA、重新 preflight）。
6. **不修改** `config/g4/runtime-policy.json`、`artifacts/foundation/deps|stage`、旧 Packet/Reviewer 报告。

---

## 7. 交付物、命令与变更表

**新增/变更（仅本分支，`git commit` 范围）**

| 路径 | 内容 |
|---|---|
| `scripts/g4r/registry_probe/probe_plugin/lib/index.js` | 公开 Cordis instrumented probe（observe/enforce + 3 类负例注入） |
| `scripts/g4r/registry_probe/run_host_probe.py` | 隔离运行器（冻结 patch 测试 copy 改写、unshare -n、SDK JSON-RPC 驱动、evidence 写入） |
| `scripts/g4r/registry_probe/snapshot.schema.json` | `g4r.registry.probe.v1` snapshot JSON Schema |
| `tests/g4r_registry/test_registry_probe.py` | 5 单测 + 1 runtime 集成测试（无 runtime 时 BLOCKED/skip，不伪造 PASS） |
| `docs/M0_G4R_REGISTRY_FEASIBILITY.md` | 本文件（含 R3 报告摘要） |

**命令与结果**（全部 UTC 2026-11-20，host，`unshare -n`）：

| 命令 | 结果 |
|---|---|
| `python3 scripts/g4r/registry_probe/run_host_probe.py --stage /tmp/.../g3c/stage --mode observe` | exit 0；1 dispatch；`[skill_lookup]`；见 run `20261120T163039Z-observe` |
| `… --mode enforce` | exit 0；approved face 放行；run `20261120T163048Z-enforce` |
| `… --mode attack-late-extra-bash` | exit 0；deny pre-adapter；run `20261120T163057Z-…` |
| `… --mode attack-duplicate-name` | exit 0；duplicate rejected；run `20261120T163107Z-…` |
| `… --mode attack-schema-drift` | exit 0；digest 变化；run `20261120T163116Z-…` |
| `… --mode observe --drop-probe-output` | runner exit 4（evidence gap）；runtime_exit 0；run `20261120T163317Z-observe` |
| `… --mode observe --skip-frozen-patch` | exit 0；registry union `[bash, read_image, working_directory]`；run `20261120T163436Z-observe` |
| `… --mode attack-two-turn --turns 2` | 仅 1 dispatch → RG-05 NOT_RUN；run `20261120T163358Z-attack-two-turn` |
| `"/root/Autonomous Teacher/.venv/bin/python" -m pytest tests/g4r_registry -q`（Python 3.11.15，经主工作树 `.venv`；host 探针驱动 `python3` 为 3.12.3） | `5 passed, 1 skipped`；`G4R_RUN_RUNTIME=1 G4R_STAGE=…` 时 `6 passed` |
| `--version` on frozen runtime（`env -i` + `unshare -n`） | `0.2.2-rc.2` exit 0 |

**未验证项（明确 UNVERIFIED/NOT_RUN）**：RG-05、RG-07 的 resume/compaction/new-Room、RG-08 的 trusted-channel 伪造拒绝、RG-09/10 联合账本、RG-12 独立复算；以及“未来任意配置/动态注册”的绝对性。**本文件不把任何未验证项写成 PASS。**

**需要维护者/独立 Reviewer 决定**：是否接受 `API_AVAILABLE` 机制并批准实现“instrumented profile + Controller 绑定”路线（需新冻结 SHA、Reviewer 独立复算、RG-12）；是否维持 B03/E5-P04 = UNVERIFIED；是否要求外部可信导出（将变为 PATCH_REQUIRED 新工作项）。Agent 不代签。
